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
""" Authentication tool
"""
import re
import string

from services.util import randchar
from services.user import NoUserIDError


class AlreadySentError(Exception):
    """Raised to indicate the backend has handled the reset code request"""
    pass


class InvalidCodeError(Exception):
    """Raised to indicate a reset code problem"""
    pass


_RE_CODE = re.compile('[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}')


class ResetCode(object):
    """Base Class for the reset code APIs."""

    def _get_user_id(self, user):
        user_id = user.get("userid", None)
        if not user_id:
            raise NoUserIDError()
        return user_id

    def _generate_reset_code(self):
        """Generates a reset code

        Returns:
            reset code
        """
        chars = string.ascii_uppercase + string.digits

        def _4chars():
            return ''.join([randchar(chars) for i in range(4)])

        code = '-'.join([_4chars() for i in range(4)])
        return code

    def _check_reset_code(self, code):
        """Verify a reset code

        Args:
            code: reset code

        Returns:
            True or False
        """
        if code is None:
            return False

        return _RE_CODE.match(code) is not None

    def generate_reset_code(self, user, overwrite=False):
        """Returns the a reset code for user.

        Args:
            user: the user object. Must have a value for user[userid]. Some
                implementations may require user[userName]
            overwrite: if set to False, returns the current key if already
                generated

        Returns:
            The reset code, or None if there's a problem.
        """
        raise NotImplementedError()

    def verify_reset_code(self, user, code):
        """
        Validates that the code provided exists and is valid for the user.

        Args:
            user: the user object. Must have a value for user[userid]. Some
                implementations may require user[userName]
            code: the code to be validated

        Returns:
            True (valid) or False (not)
        """
        raise NotImplementedError()

    def clear_reset_code(self, user):
        """
        Removes a code associated with the user

        Args:
            user: the user object. Must have a value for user[userid]. Some
                implementations may require user[userName]

        Returns:
            True if no problem occurred
        """
        raise NotImplementedError()
