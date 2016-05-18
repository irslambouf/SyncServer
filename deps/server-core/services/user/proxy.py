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
"""Mozilla Authentication via a simple HTTP proxy.

This authentication class provides a simple HTTP-based proxy to a remove
authentication database.  It talks to the server-whoami API to fulfill all
authentication requests.

We plan to use it for a quick deployment of some server-storage nodes into
AWS.  It probably shouldn't be used in other scenarios without careful
consideration of the tradeoffs.

"""

import json

from services.http_helpers import get_url
from services.exceptions import BackendError

from services.user import _password_to_credentials

from metlog.holder import CLIENT_HOLDER


METLOG_PREFIX = "services.user.proxy"


class ProxyUser(object):
    """Proxy User backend, that auths by talking to server-whoami.

    This is a special-purpose User backend for doing authentication in some
    external infrastructure, such as AWS.  It fulfills all authentication
    requests by hitting the special server-whoami web API.
    """

    def __init__(self, whoami_uri, **kw):
        self.whoami_uri = whoami_uri.rstrip("/")

    @_password_to_credentials
    def authenticate_user(self, user, credentials, attrs=None):
        password = credentials.get("password")
        if not password:
            return None

        username = user.get("username")
        if username is None:
            return None

        code, headers, body = get_url(self.whoami_uri, "GET",
                                      user=username, password=password)
        if code == 401:
            return None
        if code != 200:
            logger = CLIENT_HOLDER.default_client
            logger.error("whoami API unexpected behaviour")
            logger.error("  code: %r", code)
            logger.error("  headers: %r", headers)
            logger.error("  body: %r", body)
            raise BackendError("whoami API unexpected behaviour")

        try:
            user_data = json.loads(body)
        except ValueError:
            logger = CLIENT_HOLDER.default_client
            logger.error("whoami API produced invalid JSON")
            logger.error("  code: %r", code)
            logger.error("  headers: %r", headers)
            logger.error("  body: %r", body)
            raise BackendError("whoami API produced invalid JSON")

        user.update({
            "userid": user_data["userid"],
            "username": username,
            "syncNode": user_data.get("syncNode", ""),
        })
        return user["userid"]

    # All other methods are disabled on the proxy.
    # Only authenticate_user() is allowed.

    def get_user_id(self, user):
        raise BackendError("Disabled in ProxyUser")

    def get_user_info(self, user, attrs=None):
        raise BackendError("Disabled in ProxyUser")

    def create_user(self, username, password, email):
        raise BackendError("Disabled in ProxyUser")

    def update_field(self, user, credentials, key, value):
        raise BackendError("Disabled in ProxyUser")

    def admin_update_field(self, user, key, value):
        raise BackendError("Disabled in ProxyUser")

    def update_password(self, user, credentials, new_password):
        raise BackendError("Disabled in ProxyUser")

    def admin_update_password(self, user, new_password, code=None):
        raise BackendError("Disabled in ProxyUser")

    def delete_user(self, user, credentials=None):
        raise BackendError("Disabled in ProxyUser")
