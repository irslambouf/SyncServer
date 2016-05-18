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
""" SQL Authentication

Users are stored with digest password (ssha256)
"""
import datetime
import urlparse

from sqlalchemy import create_engine
from sqlalchemy.interfaces import PoolListener
from sqlalchemy.sql import bindparam, select, insert, update, delete
from sqlalchemy.pool import NullPool

from metlog.holder import CLIENT_HOLDER
from services.util import validate_password, ssha256, safe_execute
from services.auth.resetcode import ResetCodeManager
from services.resetcodes import ResetCode

# sharing the same table than the sql storage
from services.auth.sqlmappers import users

_SQLURI = 'pymysql://sync:sync@localhost/sync'

_USER_ID = select([users.c.id], users.c.username == bindparam('user_name'))

_USER_NAME = select([users.c.username], users.c.id == bindparam('uid'))

_USER_INFO = select([users.c.username, users.c.email],
                    users.c.id == bindparam('user_id'))

_USER_AUTH = select([users.c.id, users.c.password_hash, users.c.status],
                    users.c.username == bindparam('user_name'))

_USER_PASSWORD = select([users.c.id, users.c.password_hash],
                         users.c.id == bindparam('user_id'))

_USER_RESET_CODE = select([users.c.reset_expiration, users.c.reset],
                          users.c.id == bindparam('user_id'))


class SetTextFactory(PoolListener):
    """This ensures strings are not converted to unicode on queries
    when using SQLite
    """
    def connect(self, dbapi_con, con_record):
        dbapi_con.text_factory = str


class SQLAuth(ResetCodeManager):
    """SQL authentication."""

    def __init__(self, sqluri=_SQLURI, pool_size=20, pool_recycle=60,
                 create_tables=False, no_pool=False, **kw):
        sqlkw = {'logging_name': 'weaveserver'}
        if sqluri.startswith('sqlite'):
            sqlkw['listeners'] = [SetTextFactory()]
        else:
            if not no_pool:
                sqlkw['pool_size'] = int(pool_size)
                sqlkw['pool_recycle'] = int(pool_recycle)
            driver = urlparse.urlparse(self.sqluri).scheme.lower()
            if "mysql" in driver:
                sqlkw['pool_reset_on_return'] = False
        if no_pool or sqluri.startswith('sqlite'):
            sqlkw['poolclass'] = NullPool

        engine = create_engine(sqluri, **sqlkw)
        users.metadata.bind = engine
        if create_tables:
            users.create(checkfirst=True)
        self.sqluri = sqluri
        self.logger = CLIENT_HOLDER.default_client
        ResetCodeManager.__init__(self, engine, create_tables=create_tables)

    def _get_username(self, uid):
        """Returns the id for a user name"""
        user = safe_execute(self._engine, _USER_NAME, uid=uid).fetchone()
        if user is None:
            return None
        return user.username

    def get_user_id(self, user_name):
        """Returns the id for a user name"""
        user = safe_execute(self._engine, _USER_ID,
                            user_name=user_name).fetchone()
        if user is None:
            return None
        return user.id

    def create_user(self, user_name, password, email):
        """Creates a user. Returns True on success."""
        password_hash = ssha256(password)
        query = insert(users).values(username=user_name, email=email,
                                     password_hash=password_hash, status=1)
        res = safe_execute(self._engine, query)
        return res.rowcount == 1

    def authenticate_user(self, user_name, password):
        """Authenticates a user given a user_name and password.

        Returns the user id in case of success. Returns None otherwise."""
        user = safe_execute(self._engine, _USER_AUTH,
                            user_name=user_name).fetchone()
        if user is None:
            return None

        if user.status != 1:  # user is disabled
            return None

        if validate_password(password, user.password_hash):
            return user.id

    def get_user_info(self, user_id):
        """Returns user info

        Args:
            user_id: user id

        Returns:
            tuple: username, email
        """
        res = safe_execute(self._engine, _USER_INFO,
                           user_id=user_id).fetchone()
        if res is None:
            return None, None

        return res.username, res.email

    def update_email(self, user_id, email, password=None):
        """Change the user e-mail

        Args:
            user_id: user id
            email: new email

        Returns:
            True if the change was successful, False otherwise
        """
        query = update(users).where(users.c.id == user_id)
        res = safe_execute(self._engine, query.values(email=email))
        return res.rowcount == 1

    def update_password(self, user_id, password, old_password):
        """Change the user password

        Args:
            user_id: user id
            password: new password
            old_password: the old password

        Returns:
            True if the change was successful, False otherwise
        """
        # XXX check the old password
        #
        password_hash = ssha256(password)
        query = update(users).where(users.c.id == user_id)
        res = safe_execute(self._engine,
                           query.values(password_hash=password_hash))
        return res.rowcount == 1

    def admin_update_password(self, user_id, password, key):
        """Change the user password

        Args:
            user_id: user id
            password: new password

        Returns:
            True if the change was successful, False otherwise
        """
        # using a key, therefore we should check it
        if self._get_reset_code(user_id) == key:
            self.clear_reset_code(user_id)
        else:
            self.logger.error("bad key used for update password")
            return False

        password_hash = ssha256(password)
        query = update(users).where(users.c.id == user_id)
        res = safe_execute(self._engine,
                           query.values(password_hash=password_hash))
        return res.rowcount == 1

    def delete_user(self, user_id, password=None):
        """Deletes a user

        Args:
            user_id: user id
            password: user password, if needed

        Returns:
            True if the deletion was successful, False otherwise
        """
        if password is not None:
            # we want to control if the password is good
            user = safe_execute(self._engine, _USER_PASSWORD,
                                user_id=user_id).fetchone()
            if user is None:
                return False

            if not validate_password(password, user.password_hash):
                return False

        query = delete(users).where(users.c.id == user_id)
        res = safe_execute(self._engine, query)
        return res.rowcount == 1

    def get_user_node(self, user_id, assign=True):
        """Returns the node of the user"""
        # the sql auth backend does not handle nodes.
        return None

    #
    # Reset code managment
    #
    def clear_reset_code(self, user_id):
        query = update(users).where(users.c.id == user_id)
        code = expiration = None
        res = safe_execute(self._engine, query.values(id=user_id, reset=code,
                           reset_expiration=expiration))
        return res.rowcount == 1

    def _get_reset_code(self, user_id):
        res = self._engine.execute(_USER_RESET_CODE, user_id=user_id)
        res = res.fetchone()

        if res is None or res.reset is None or res.reset_expiration is None:
            return None

        if isinstance(res.reset_expiration, basestring):
            exp = datetime.datetime.strptime(res.expiration,
                                             '%Y-%m-%d %H:%M:%S.%f')
        else:
            exp = res.reset_expiration

        if exp < datetime.datetime.now():
            # expired
            self.clear_reset_code(user_id)
            return None

        return res.reset

    def _set_reset_code(self, user_id):
        rc = ResetCode()
        code = rc._generate_reset_code()
        expiration = datetime.datetime.now() + datetime.timedelta(hours=6)
        query = update(users).values(reset=code, reset_expiration=expiration)
        res = safe_execute(self._engine, query.where(users.c.id == user_id))
        if res.rowcount != 1:
            self.logger.debug('Unable to add a new reset code')
            return None  # XXX see if appropriate
        return code
