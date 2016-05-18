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
"""Pass-Through Authentication for Loadtest Users

This authentication class provides pass-through authentication for loadtesting
purposes.  All usernames are assumed to be of the form "cuserXXXX" where XXXX
is an integer.  The auth accepts any password and uses XXXX as the userid.

Obviously this should not be used in a production setting...

"""

from services.user import User, _password_to_credentials


class LoadTestUser(object):

    def __init__(self, **kw):
        pass

    @_password_to_credentials
    def authenticate_user(self, user, credentials, attrs=None):
        username = user.get("username")
        if username is None:
            return None
        if not username.startswith("cuser"):
            return None
        try:
            userid = int(username[5:])
        except ValueError:
            return None
        user["userid"] = userid
        user["syncNode"] = "-"
        return userid

    # All other methods are disabled.
    # Only authenticate_user() is allowed.

    def get_user_id(self, user):
        raise BackendError("Disabled in LoadTestUser")

    def get_user_info(self, user, attrs=None):
        raise BackendError("Disabled in LoadTestUser")

    def create_user(self, username, password, email):
        raise BackendError("Disabled in LoadTestUser")

    def update_field(self, user, credentials, key, value):
        raise BackendError("Disabled in LoadTestUser")

    def admin_update_field(self, user, key, value):
        raise BackendError("Disabled in LoadTestUser")

    def update_password(self, user, credentials, new_password):
        raise BackendError("Disabled in LoadTestUser")

    def admin_update_password(self, user, new_password, code=None):
        raise BackendError("Disabled in LoadTestUser")

    def delete_user(self, user, credentials=None):
        raise BackendError("Disabled in LoadTestUser")
