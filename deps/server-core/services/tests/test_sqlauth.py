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
import os
import unittest
import datetime

from sqlalchemy.sql import text
from sqlalchemy.pool import NullPool

from services.tests.support import initenv, cleanupenv
from services.auth.sql import SQLAuth
from services.auth import ServicesAuth
from services.util import ssha, BackendError, safe_execute

ServicesAuth.register(SQLAuth)


class TestSQLAuth(unittest.TestCase):

    def setUp(self):
        self.appdir, self.config, self.auth = initenv()
        # we don't support other storages for this test
        driver = self.auth.sqluri.split(':/')[0]
        assert driver in ('mysql', 'pymysql', 'sqlite')

        # lets add a user tarek/tarek
        password = ssha('tarek')
        query = text('insert into users (username, password_hash, status) '
                     'values (:username, :password, 1)')
        self._safe_execute(query, username='tarek', password=password)
        self.user_id = self._safe_execute('select id from users where'
                                            ' username="tarek"').fetchone().id

    def tearDown(self):
        self._safe_execute('delete from users')
        cleanupenv()

    def _safe_execute(self, *args, **kwds):
        return safe_execute(self.auth._engine, *args, **kwds)

    def test_authenticate_user(self):
        if not isinstance(self.auth, SQLAuth):
            # not supported yet
            return

        self.assertEquals(self.auth.authenticate_user('tarek', 'xxx'), None)
        user_id = self.auth.authenticate_user('tarek', 'tarek')
        self.assertEquals(user_id, self.user_id)

    def test_reset_code(self):
        if not isinstance(self.auth, SQLAuth):
            # not supported yet
            return

        self.assertFalse(self.auth.verify_reset_code(self.user_id, 'x'))

        # normal behavior
        code = self.auth.generate_reset_code(self.user_id)
        self.assertFalse(self.auth.verify_reset_code(self.user_id, 'BADCODE'))
        self.assertTrue(self.auth.verify_reset_code(self.user_id, code))

        # reseted
        code = self.auth.generate_reset_code(self.user_id)
        self.auth.clear_reset_code(self.user_id)
        self.assertFalse(self.auth.verify_reset_code(self.user_id, code))

        # expired
        code = self.auth.generate_reset_code(self.user_id)
        expiration = datetime.datetime.now() + datetime.timedelta(hours=-7)

        query = ('update users set reset_expiration = :expiration '
                 'where id = %d' % self.user_id)
        self._safe_execute(text(query), expiration=expiration)
        self.assertFalse(self.auth.verify_reset_code(self.user_id, code))

    def test_status(self):
        if not isinstance(self.auth, SQLAuth):
            # not supported yet
            return
        # people with status '0' are disabled
        self._safe_execute('update users set status=0')
        self.assertEquals(self.auth.authenticate_user('tarek', 'tarek'), None)

    def test_no_create(self):
        # testing the create_tables option
        testsdir = os.path.dirname(__file__)
        conf = os.path.join(testsdir, 'tests_nocreate.ini')
        appdir, config, auth = initenv(conf)

        try:
            # this should fail because the table is absent
            self.assertRaises(BackendError, auth.authenticate_user,
                              'tarek', 'tarek')
        finally:
            cleanupenv(conf)

    def test_no_pool(self):
        # checks that sqlite gets the NullPool by default
        testsdir = os.path.dirname(__file__)
        conf = os.path.join(testsdir, 'tests_nocreate.ini')
        appdir, config, auth = initenv(conf)
        try:
            self.assertTrue(isinstance(auth._engine.pool, NullPool))
        finally:
            cleanupenv(conf)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestSQLAuth))
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
