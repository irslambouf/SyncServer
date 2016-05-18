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
#   Tarek Ziade (tarek@mozilla.com)
#   Toby Elliott (telliott@mozilla.com)
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
""" Mozilla Authentication using a two-tier system
"""
import simplejson as json
import urlparse

from services.http_helpers import get_url
from services.user.mozilla_ldap import LDAPUser
from services.user import User, _password_to_credentials
from services.resetcodes import InvalidCodeError
from services.respcodes import ERROR_INVALID_WRITE, ERROR_INVALID_RESET_CODE
from services.exceptions import BackendError


class SregUser(LDAPUser):
    """LDAP authentication with a proxy back for admin binds."""

    def __init__(self, ldapuri, sreg_location, sreg_path, sreg_scheme=None,
                 **kw):

        super(SregUser, self).__init__(ldapuri, **kw)

        self.sreg_location = sreg_location
        self.sreg_scheme = sreg_scheme
        self.sreg_path = sreg_path

    def create_user(self, username, password, email):
        """Creates a user. Returns user on success, false otherwise."""
        if not self.allow_new_users:
            raise BackendError("Creation of new users is disabled")

        payload = {'password': password, 'email': email}
        url = self._generate_url(username)
        status, body = self._proxy('PUT', url, payload)
        if status != 200:
            if body == ERROR_INVALID_WRITE:
                return False
            msg = 'Unable to create the user via sreg. '
            msg += 'Received body:\n%s\n' % str(body)
            msg += 'Received status: %d' % status
            raise BackendError(msg, server=url)

        # the result is the username on success
        if body == username:
            user = User()
            user['username'] = username
            user['email'] = email
            return user
        else:
            return False

    def admin_update_password(self, user, new_password, key=None):
        """Change the user password.

        Uses the admin bind or the user bind if the old password is provided.

        Args:
            user_id: user id
            password: new password
            key: the reset code if needed for proxying

        Returns:
            True if the change was successful, False otherwise
        """
        payload = {'reset_code': key, 'password': new_password}
        username = user.get('username')
        if username is None:
            return False

        url = self._generate_url(username, 'password')
        status, body = self._proxy('POST', url, payload)
        if status == 200:
            return body == 0
        elif status == 400:
            if body == ERROR_INVALID_RESET_CODE:
                raise InvalidCodeError()

        msg = 'Unable to change the user password via sreg. '
        msg += 'Received body:\n%s\n' % str(body)
        msg += 'Received status: %d' % status
        raise BackendError(msg, server=url)

    @_password_to_credentials
    def delete_user(self, user, credentials=None):
        """Deletes the user

        Args:
            user_id: user id
            credentials: user authentication credentials

        Returns:
            True if the change was successful, False otherwise
        """
        if credentials is None:
            return False
        password = credentials.get("password")
        if password is None:
            return False

        payload = {'password': password}
        username = user.get('username')
        if username is None:
            return False

        url = self._generate_url(username)
        status, body = self._proxy('DELETE', url, payload)
        if status != 200:
            msg = 'Unable to delete the user via sreg. '
            msg += 'Received body:\n%s\n' % str(body)
            msg += 'Received status: %d' % status
            raise BackendError(msg, server=url)

        return body == 0

    def _proxy(self, method, url, data=None, headers=None):
        """Proxies and return the result from the other server.

        - scheme: http or https
        - netloc: proxy location
        """
        if data is not None:
            data = json.dumps(data)

        status, headers, body = get_url(url, method, data, headers)

        if body:
            try:
                body = json.loads(body)
            except Exception:
                self.logger.error("bad json body from sreg (%s): %s" %
                                                        (url, body))

        return status, body

    def _generate_url(self, username, additional_path=None):
        path = "%s/%s" % (self.sreg_path, username)
        if additional_path:
            path = "%s/%s" % (path, additional_path)

        url = urlparse.urlunparse([self.sreg_scheme, self.sreg_location,
                                  path,
                                  None, None, None])
        return url
