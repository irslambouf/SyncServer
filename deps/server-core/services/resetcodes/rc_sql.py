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
#   Toby Elliott (telliott@mozilla.com)
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
""" Reset code manager.

Stores the reset codes in a SQL Table, per user name.

The storage can be overriden.
"""
import datetime

from sqlalchemy.ext.declarative import declarative_base, Column
from sqlalchemy import String, DateTime
from sqlalchemy.sql import bindparam, select, insert, delete, and_

from services.util import safe_execute, create_engine
from services.resetcodes import ResetCode
from services.exceptions import BackendError


_Base = declarative_base()


class ResetCodes(_Base):
    __tablename__ = 'reset_codes'

    username = Column(String(32), primary_key=True, nullable=False)
    product = Column(String(32), primary_key=True, nullable=False)
    reset = Column(String(32))
    expiration = Column(DateTime())

reset_codes = ResetCodes.__table__

_USER_RESET_CODE = select([reset_codes.c.expiration, reset_codes.c.reset],
                        and_(reset_codes.c.username == bindparam('user_name'),
                             reset_codes.c.product == bindparam('product')))


class ResetCodeSQL(ResetCode):
    """ Implements the reset code methods for a sql backend
    """
    def __init__(self, engine=None, product='auth', create_tables=False,
                 expiration=21600, sqluri=None, **kw):
        self._engine = engine
        if self._engine is None:
            self._engine = create_engine(sqluri)

        self.product = product
        self.expiration = expiration
        if self._engine is not None:
            reset_codes.metadata.bind = self._engine
            if create_tables:
                reset_codes.create(checkfirst=True)

    #
    # Private methods
    #
    def _get_reset_code(self, user_id):
        res = self._engine.execute(_USER_RESET_CODE,
                                   user_name=user_id, product=self.product)
        res = res.fetchone()

        if res is None or res.reset is None or res.expiration is None:
            return None

        if isinstance(res.expiration, basestring):
            exp = datetime.datetime.strptime(res.expiration,
                                             '%Y-%m-%d %H:%M:%S.%f')
        else:
            exp = res.expiration

        if exp < datetime.datetime.now():
            # expired
            self._delete_reset_code(user_id)
            return None

        return res.reset

    def _set_reset_code(self, user_id):
        code = self._generate_reset_code()
        query = delete(reset_codes).where(
                                   and_(reset_codes.c.username == user_id,
                                        reset_codes.c.product == self.product))
        self._engine.execute(query)

        expiration_time = datetime.datetime.now() + \
                            datetime.timedelta(seconds=self.expiration)

        query = insert(reset_codes).values(reset=code,
                                           expiration=expiration_time,
                                           product=self.product,
                                           username=user_id)

        res = safe_execute(self._engine, query)

        if res.rowcount != 1:
            raise BackendError('adding a reset code to the reset table failed')

        return code

    def _delete_reset_code(self, user_id):
        query = delete(reset_codes).where(reset_codes.c.username == user_id)
        res = safe_execute(self._engine, query)
        return res.rowcount > 0

    #
    # Public methods
    #
    def generate_reset_code(self, user, overwrite=False):
        user_id = self._get_user_id(user)
        if not overwrite:
            stored_code = self._get_reset_code(user_id)
            if stored_code is not None:
                return stored_code

        return self._set_reset_code(user_id)

    def verify_reset_code(self, user, code):
        user_id = self._get_user_id(user)
        if not self._check_reset_code(code):
            return False

        stored_code = self._get_reset_code(user_id)
        if stored_code is None:
            return False

        return stored_code == code

    def clear_reset_code(self, user):
        user_id = self._get_user_id(user)
        if self._engine is None:
            raise NotImplementedError()
        return self._delete_reset_code(user_id)
