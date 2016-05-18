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
""" Base interface for user functions such as auth and account admin
"""
import abc
import base64
import functools
import re
from hashlib import sha1

from services.pluginreg import PluginRegistry
from services.util import email_to_idn
from services.exceptions import NoEmailError, NoUserIDError  # NOQA


# A valid (non-email-address) username must match this regex.
VALID_USERNAME_RE = re.compile("^[a-zA-Z0-9._-]+$")


def extract_username(username):
    """Extracts the user name.

    Takes the username and if it is an email address, munges it down
    to the corresponding 32-character username
    """
    if '@' not in username:
        if not VALID_USERNAME_RE.match(username):
            raise ValueError("Invalid username: %r" % (username,))
        return username
    username = email_to_idn(username).lower()
    hashed = sha1(username).digest()
    return base64.b32encode(hashed).lower()


class User(dict):
    """
    A holding class for user data. One day it might be more, so better
    to put a class wrapper around it
    """

    def __init__(self, username=None, userid=None):
        self['username'] = username
        self['userid'] = userid


class ServicesUser(PluginRegistry):
    """Abstract Base Class for the authentication APIs.

    All user authentication is done by passing in a "credentials" dict.
    All backends must support credentials consisting of "username" and
    "password" keys.  They may also support other schemes such as digest
    access authentication or BrowserID.
    """

    @abc.abstractmethod
    def get_user_id(self, user):
        """Returns the id for a user name.

        Args:
            user: the user object. Will be updated as a side effect

        Returns:
            user id. None if not found.
        """

    @abc.abstractmethod
    def create_user(self, username, password, email):
        """Creates a user

        Args:
            - username: the username associated with the user
            - password: the password associated with the user
            - email: the email associated with the user

        Returns:
            a User object if the creation was successful, or False if not
        """

    @abc.abstractmethod
    def authenticate_user(self, user, credentials, attrs=None):
        """Authenticates a user.

        Args:
            user: a user object.  Will be updated as a side-effect
            credentials: a dict containing the user's auth credentials
            attrs: a list of other attributes desired

        Returns:
            None in case of failure.  The user id in case of success.

        Side Effects:
            Updates the user object with requested attributes if they
            aren't already defined.
        """

    @abc.abstractmethod
    def get_user_info(self, user, attrs):
        """Returns user info

        Args:
            user: the user object
            attrs: the pieces of data requested

        Returns:
            user object populated with attrs
        """

    @abc.abstractmethod
    def update_field(self, user, credentials, key, value):
        """Change the value of a field in the user record

        Args:
            user: user object
            credentials: a dict containing authentication credentials
            key: name of the field.
            value: value to put in the field

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def admin_update_field(self, user, key, value):
        """
        Change the value of a field in the user record. Does this as admin.
        This assumes that a reset code or something similar has already
        been verified by the application, or the function is being called
        internally.

        Args:
            user: user object
            key: name of the field.
            value: value to put in the field

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def update_password(self, user, credentials, new_password):
        """
        Change the user password.

        Args:
            user: user object
            credentials: a dict containing authentication credentials
            new_password: new password for the user

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def admin_update_password(self, user, new_password, code=None):
        """
        Change the user password. Does this as admin. This assumes that a reset
        code or something similar has already been verified by the application.

        Args:
            user: user object
            new_password: new password
            code: a reset code, if one needs to be proxied to a backend

        Returns:
            True if the change was successful, False otherwise
        """

    @abc.abstractmethod
    def delete_user(self, user, credentials=None):
        """
        Deletes a user.

        Args:
            user: the user object
            credentials: a dict containing authentication credentials, if
                         they need to be proxied to a backend

        Returns:
            True if the deletion was successful, False otherwise
        """


def _password_to_credentials(func):
    """Decorator to turn a raw password into a credentials dict.

    This is a backwards-compatability hook to deal with code that passes
    a raw password into the User backend instead of a credentials dict.
    It transforms the password into a username/password dict before passing
    it on to the wrapped method.
    """
    @functools.wraps(func)
    def wrapped_method(self, user, credentials=None, *args, **kwds):
        if isinstance(credentials, basestring):
            username = user.get("username")
            credentials = {"username": username, "password": credentials}
        return func(self, user, credentials, *args, **kwds)
    return wrapped_method
