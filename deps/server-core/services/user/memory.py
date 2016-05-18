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
""" Dummy Authentication
"""
import random
from services.user import User, _password_to_credentials
from services.exceptions import BackendError


class MemoryUser(object):
    """Dummy authentication.

    Will store the user ids in memory.
    """

    def __init__(self, allow_new_users=True, **kw):
        self.allow_new_users = allow_new_users
        self._users = {}

    def get_user_id(self, user):
        """Returns user id"""
        user_id = user.get('userid')
        if user_id is not None:
            return user_id

        user_name = user.get('username')

        if user_name in self._users:
            user_id = self._users[user_name].get('userid')
            user['userid'] = user_id
            return user['userid']

        return None

    def create_user(self, user_name, password, email):
        """Creates a user"""
        if not self.allow_new_users:
            raise BackendError("Creation of new users is disabled")

        user = User()
        if user_name in self._users:
            return False
        id_ = random.randint(1, 2000)
        ids = self._users.values()
        while id_ in ids:
            id_ = random.randint(1, 2000)

        self._users[user_name] = {'userid': id_, 'password': password,
                                  'mail': email, 'username': user_name,
                                  'primaryNode': ''}

        user['username'] = user_name
        user['userid'] = id_
        user['mail'] = email
        return user

    @_password_to_credentials
    def authenticate_user(self, user, credentials, attrs=None):
        """Authenticates a user given a username and auth credentials.

        Returns the user id in case of success, None in case of failure.
        """

        username = credentials.get("username")
        if username is None:
            return None
        if username not in self._users:
            return None
        if user.get("username") not in (None, username):
            return None

        data = self._users[username]

        if data['password'] != credentials.get('password'):
            return None

        user['username'] = username
        user['userid'] = data['userid']
        if attrs is not None:
            for attr in attrs:
                user[attr] = data.get(attr)

        return data['userid']

    def get_user_info(self, user, attrs):
        user_name = user.get("username")
        if user_name not in self._users:
            return user

        data = self._users[user_name]
        for attr in attrs:
            user[attr] = data.get(attr)
        return user

    @_password_to_credentials
    def update_field(self, user, credentials, key, value):
        """Updates the value for a user field"""

        if not self.authenticate_user(user, credentials):
            return False
        user_name = user.get("username")
        if user_name not in self._users:
            return False

        self._users[user_name][key] = value
        user[key] = value

        return True

    def admin_update_field(self, user, key, value, code=None):
        """Updates the value for a user field"""

        user_name = user.get("username")
        if user_name not in self._users:
            return False

        self._users[user_name][key] = value
        user[key] = value

        return True

    @_password_to_credentials
    def update_password(self, user, credentials, new_password):
        """Updates the password"""
        if not self.authenticate_user(user, credentials):
            return False
        return self.update_field(user, credentials, 'password', new_password)

    def admin_update_password(self, user, new_password):
        """Updates the password"""
        return self.admin_update_field(user, 'password', new_password)

    @_password_to_credentials
    def delete_user(self, user, credentials=None):
        """Removes a user"""

        if credentials is not None:
            if not self.authenticate_user(user, credentials):
                return False

        user_name = user.get("username")
        if user_name in self._users:
            del self._users[user_name]
            return True
        return False
