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
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#   Ryan Kelly (rkelly@mozilla.com)
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
"""
repoze.who IAuthenticator plugin that auths to services auth backend.
"""

try:
    from zope.interface import implements
    from repoze.who.interfaces import IAuthenticator
except:
    # failing at import time is bad for test discovery
    implements = lambda x: None  # NOQA
    IAuthenticator = None        # NOQA

from metlog.holder import CLIENT_HOLDER
from metlog_cef import AUTH_FAILURE

from services.user import User, extract_username


class BackendAuthPlugin(object):
    """IAuthenticator plugin using the services auth backend.

    This is a repoze.who IAuthenticator plugin that checks user credentals
    against the services auth backend.  You have to have a backend configured
    for your application or this won't work.
    """

    implements(IAuthenticator)

    def __init__(self, config=None, backend=None):
        self.config = config
        self.backend = backend
        self.logger = CLIENT_HOLDER.default_client

    def authenticate(self, environ, identity):
        # Normalize the username for our backend.
        # Some repoze.who plugins use "login" instead of "username".
        username = identity.get("username")
        if username is None:
            username = identity.get("login")
            if username is None:
                return None
        orig_username = username
        identity["username"] = username = extract_username(username)

        # Normalize the password, if any, to be unicode.
        # It it's not valid utf8 then authentication fails.
        password = identity.get("password")
        if password is not None and not isinstance(password, unicode):
            try:
                identity["password"] = password.decode("utf8")
            except UnicodeDecodeError:
                return None

        # Decide whether it's a new-style or old-style auth backend.
        if hasattr(self.backend, 'generate_reset_code'):
            user = self._authenticate_oldstyle(environ, username, identity)
        else:
            user = self._authenticate_newstyle(environ, username, identity)

        # Log the error if that failed.
        if user is None:
            err_username = username
            if username != orig_username:
                err_username += ' (%s)' % (orig_username,)
            self.logger.cef('User Authentication Failed', 5,
                            environ, self.config, err_username, AUTH_FAILURE)
            return None

        # Success!  Store any loaded attributes into the identity dict.
        identity.update(user)
        return user["username"]

    def _authenticate_oldstyle(self, environ, username, identity):
        """Authenticate against an old-style auth backend."""
        password = identity.get("password")
        if password is None:
            return None

        if hasattr(self.backend, 'check_node') and self.backend.check_node:
            host = environ.get('HTTP_HOST')
            user_id = self.backend.authenticate_user(username, password, host)
        else:
            user_id = self.backend.authenticate_user(username, password)

        if user_id is None:
            return None
        return User(username, user_id)

    def _authenticate_newstyle(self, environ, username, identity):
        """Authenticate against a new-style auth backend."""
        user = User(username)
        if not self.backend.authenticate_user(user, identity, ['syncNode']):
            user = None
        else:
            if self.config.get('auth.check_node'):
                if user.get('syncNode') != environ.get('HTTP_HOST'):
                    user = None
        return user


def make_plugin():
    """BackendAuthPlugin helper for loading from ini files."""
    plugin = BackendAuthPlugin()
    return plugin
