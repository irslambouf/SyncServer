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
""" Authentication tool
"""
import urlparse
import json

from metlog.holder import CLIENT_HOLDER
from services.exceptions import BackendError
from services.http_helpers import get_url
from services.auth import NoEmailError
from services.resetcodes import ResetCode, NoUserIDError, AlreadySentError
from services.respcodes import ERROR_NO_EMAIL_ADDRESS


class ResetCodeSreg(ResetCode):

    def __init__(self, sreg_location, sreg_path, sreg_scheme='https',
                 product='auth', **kw):

        self.sreg_location = sreg_location
        self.sreg_scheme = sreg_scheme
        self.sreg_path = sreg_path
        self.product = product
        self.logger = CLIENT_HOLDER.default_client

    def generate_reset_code(self, user, overwrite=False):
        """Returns the a reset code for user.

        Args:
            user: the user object. Must have a value for user[userid]
            overwrite: if set to False, returns the current key if already
                generated

        Returns:
            The reset code, or None if there's a problem.
        """

        username = user.get('username', None)
        if not username:
            raise NoUserIDError()

        status, body = self._proxy('GET',
                             self._generate_url(username,
                                               'password_reset_code'))
        if status == 200 and body == 0:
            raise AlreadySentError()

        if status == 400:
            if body == ERROR_NO_EMAIL_ADDRESS:
                raise NoEmailError()

        raise BackendError()

    def verify_reset_code(self, user, code):
        """WARNING! If you are using sreg, we're assuming that you're passing
        the reset code into sreg, and do not do validation of it here. """
        return True

    def clear_reset_code(self, user):
        """WARNING! If you are using sreg, we're assuming that you're clearing
        the reset code in sreg, and do not do it here. """
        return True

    def _generate_url(self, username, additional_path=None):
        path = "%s/%s" % (self.sreg_path, username)
        if additional_path:
            path = "%s/%s" % (path, additional_path)

        url = urlparse.urlunparse([self.sreg_scheme, self.sreg_location,
                                  path,
                                  None, None, None])
        return url

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
