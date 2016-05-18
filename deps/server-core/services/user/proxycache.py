# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Sync Server
#
# The Initial Developer of the Original Code is the Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2011
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Ryan Kelly (rfkelly@mozilla.com)
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****
"""Mozilla Authentication via a caching proxy.

This authentication class provides a local cache proxy of the auth data
from anothe system.  It talks to the server-whoami API to authenticate and
retrieve user account details, and caches successful credentials in memcached
to speed up future requests.

We plan to use it for a quick deployment of some server-storage nodes into
AWS.  It probably shouldn't be used in other scenarios without careful
consideration of the tradeoffs.

The use of a local cache has some subtle implications, which are fine for
this deployment but deserve to be called out explicitly:

    * Password changes will not be picked up straight away.  If the user
      changes their password through account-portal but leaves it unchanged
      in the sync client, the old password will continue to work until we
      decide to refresh the cache.  The timeout for this can be set in the
      config file, and even a very low timeout would still dramatically
      reduce the costs of password checking.

    * Authentication failures, however, are always treated as a cache miss.
      So if the user puts their new password into the sync client, it will
      work right away - it fails auth in the cache, is treated as a miss, and
      hits the main store where it's found to be correct.

    * Similarly, node re-assignments will not be picked up straight away.
      You'll have to wait for the cache timeout to expire before the node
      starts giving 401s to unassigned users.

"""

import os
import time
import json
import hmac
import Queue
import hashlib
import contextlib

from services.user import _password_to_credentials
from services.user.proxy import ProxyUser
from services.exceptions import BackendError

from metlog.holder import CLIENT_HOLDER
from metlog.decorators.stats import timeit as metlog_timeit

import pylibmc


METLOG_PREFIX = "services.user.proxycache"


class ProxyCacheUser(object):
    """Caching Proxy User backend, using memcache in front of the main user db.

    This is a special-purpose User backend for doing authentication in some
    external infrastructure, such as AWS.  It uses memcache to keep a local
    local cache of the remote, authoritative auth data, which is populates
    on-demand by hitting the special server-whoami web API.

    Some implementation notes:

        * Only the authenticate_user() method is implemented, since this is
          the only one used by server-storage.  All other methods will raise
          an error if you try to use them.

        * Successfully-authed credentials are hmac-ed into an opaque 'token'
          and written to memcached to speed up future requests.  The token
          is a hmac of the username, password, and a "counter" based on the
          on the current timestamp.  The counter is used to provide a little
          bit of perturbation into what's otherwise a deterministic hash.

        * Cracking passwords from this cached data would thus involve:
              * being able to read the cached keys out of memcached
              * knowing the secret server-side hmac key
              * knowing roughly the time at which the keys were written
              * brute-forcing HMAC-SHA256


    """

    def __init__(self, whoami_uri, secret_key=None, cache_servers=None,
                 cache_prefix="ProxyCacheUser/", cache_timeout=60*60, **kw):
        self.proxy = ProxyUser(whoami_uri)
        # Use a randomly-generated secret key if none is specified.
        # This is secure, but will reduce the re-usability of the cache.
        if secret_key is None:
            secret_key = os.urandom(32)
        elif len(secret_key) < 32:
            raise ValueError("secret_key should be at least 256 bit")
        self.hmac_master = hmac.new(secret_key, "", hashlib.sha256)
        # Default to memcached running on localhost if no server specified.
        if isinstance(cache_servers, str):
            cache_servers = [cache_servers]
        elif cache_servers is None:
            cache_servers = ['127.0.0.1:11211']
        self.cache_prefix = cache_prefix
        self.cache_timeout = int(cache_timeout)
        self.cache_client = pylibmc.Client(cache_servers)
        self.cache_pool = BottomlessClientPool(self.cache_client)

    @_password_to_credentials
    def authenticate_user(self, user, credentials, attrs=None):
        username = user.get("username")
        if username is None:
            return None
        password = credentials.get("password")
        if not password:
            return None

        # The auth caching token includes a timestamp-derived counter, so
        # there are several possibile tokens that could be active in the cache.
        tokens = list(self._generate_possible_tokens(username, password))

        # Look for all of those tokens in the cache with a single get.
        # If any one of them exists, the auth is OK.
        cached_user_data = self._cache_get(*tokens)
        if cached_user_data is not None:
            user.update(cached_user_data)
            # Check that we got all the requested attributes.
            # If not, we'll have to fall back to the proxy API to fetch them.
            for attr in attrs:
                if attr not in user:
                    break
            else:
                CLIENT_HOLDER.default_client.incr(METLOG_PREFIX + "cache_hit")
                return user["userid"]

        # Not cached, call through to the proxy.
        userid = self.proxy.authenticate_user(user, credentials, attrs)
        if userid is None:
            return None
        CLIENT_HOLDER.default_client.incr(METLOG_PREFIX + "cache_miss")

        # Now we know the account is good, write it into the cache
        # using the most recent token as key.
        cached_user_data = {"userid": userid}
        if attrs:
            for attr in attrs:
                cached_user_data[attr] = user[attr]
        self._cache_set(tokens[0], cached_user_data)

        return userid

    def _generate_possible_tokens(self, username, password):
        """Generate possible auth-caching tokens for these credentials.

        The token is a HMAC of the username, the password, and a "counter"
        derived from the current timestamp.  The counter is used to add a
        little bit of perturbation into what's otherwise a deterministic
        hash.  It is the number of cache_timeout intervals that have elapsed
        since the unix epoch, i.e. counter = floor(cur_time / cache_timeout).

        We allow both the current counter value and the previous one when
        when checking for valid cached credentials.  The TTLs in memcache
        will ensure that we're not using old data once it has expired.
        """
        template = "%s:%s:%d"
        counter = int(time.time() / self.cache_timeout)
        hasher = self.hmac_master.copy()
        hasher.update(template % (username, password, counter))
        yield hasher.digest().encode('base64').strip()
        counter = counter - 1
        hasher = self.hmac_master.copy()
        hasher.update(template % (username, password, counter))
        yield hasher.digest().encode('base64').strip()

    @metlog_timeit
    def _cache_get(self, *keys):
        """Get an item from the cache.

        If multiple arguments are given, attempt to load all those keys and
        return data from the first one successfully found.
        """
        keys = [self.cache_prefix + key for key in keys]
        with self.cache_pool.reserve() as mc:
            try:
                values = mc.get_multi(keys)
            except pylibmc.Error, err:
                raise BackendError(str(err))
            for key in keys:
                if key in values:
                    return json.loads(values[key])
            return None

    @metlog_timeit
    def _cache_set(self, key, value):
        """Set an item in the cache.  It gets a default ttl."""
        key = self.cache_prefix + key
        with self.cache_pool.reserve() as mc:
            try:
                if not mc.set(key, json.dumps(value), self.cache_timeout):
                    raise BackendError('memcached error')
            except pylibmc.Error, err:
                raise BackendError(str(err))

    # All other methods are disabled on the proxy.
    # Only authenticate_user() is allowed.

    def get_user_id(self, user):
        raise BackendError("Disabled in ProxyCacheUser")

    def get_user_info(self, user, attrs=None):
        raise BackendError("Disabled in ProxyCacheUser")

    def create_user(self, username, password, email):
        raise BackendError("Disabled in ProxyCacheUser")

    def update_field(self, user, credentials, key, value):
        raise BackendError("Disabled in ProxyCacheUser")

    def admin_update_field(self, user, key, value):
        raise BackendError("Disabled in ProxyCacheUser")

    def update_password(self, user, credentials, new_password):
        raise BackendError("Disabled in ProxyCacheUser")

    def admin_update_password(self, user, new_password, code=None):
        raise BackendError("Disabled in ProxyCacheUser")

    def delete_user(self, user, credentials=None):
        raise BackendError("Disabled in ProxyCacheUser")


class BottomlessClientPool(pylibmc.ClientPool):
    """Memcached client pool that can gros as big as needed.

    This is a customized pylibmc.ClientPool that will never block waiting
    for a connection.  Instead, it will just create a new one on demand.
    This seems superior to using ThreadMappedPool for our use case, since
    we will never ask for more connections than there are active threads,
    we may wind up with less total connections, and we don't have to worry
    about cleaning up internal state when a thread exits.
    """

    def __init__(self, mc=None, n_slots=0):
        self._mc = mc
        pylibmc.ClientPool.__init__(self, mc, n_slots)

    @contextlib.contextmanager
    def reserve(self):
        try:
            mc = self.get(False)
        except Queue.Empty:
            mc = self._mc.clone()
        try:
            yield mc
        finally:
            self.put(mc)
