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
import unittest
import time

from services.pluginreg import load_and_configure
from services.auth import User

from webob import Response
from services.auth import NoEmailError
from services.resetcodes import AlreadySentError
from services.respcodes import ERROR_NO_EMAIL_ADDRESS
from services.tests.support import check_memcache
from services.exceptions import BackendError

from nose.plugins.skip import SkipTest


class TestResetCodeManager(unittest.TestCase):

    def _tests(self, mgr):
        user = User()
        user['userid'] = 1

        code = mgr.generate_reset_code(user)
        self.assertEqual(code, mgr.generate_reset_code(user))
        code2 = mgr.generate_reset_code(user, True)
        self.assertNotEqual(code, code2)

        self.assertFalse(mgr.verify_reset_code(user, code))
        self.assertTrue(mgr.verify_reset_code(user, code2))

        time.sleep(1)
        self.assertFalse(mgr.verify_reset_code(user, code2))

        code3 = mgr.generate_reset_code(user, True)
        self.assertTrue(mgr.verify_reset_code(user, code3))
        mgr.clear_reset_code(user)
        self.assertFalse(mgr.verify_reset_code(user, code3))

        self.assertFalse(mgr.verify_reset_code(user, None))

    def test_reset_code_sql(self):

        config = {'backend': 'services.resetcodes.rc_sql.ResetCodeSQL',
                  'sqluri': 'sqlite:///:memory:',
                  'create_tables': True,
                  'expiration': 1}
        storage = load_and_configure(config)
        self._tests(storage)

        def _no_result(*args, **kwargs):
            class NoRows(object):
                def __init__(self):
                    self.rowcount = 0
            return NoRows()

        import services.resetcodes.rc_sql as rc_sql
        old_safe = rc_sql.safe_execute
        rc_sql.safe_execute = _no_result
        user = User()
        user['userid'] = 1
        self.assertRaises(BackendError, storage.generate_reset_code,
                          user, True)
        rc_sql.safe_execute = old_safe

    def test_reset_code_memcache(self):
        if check_memcache() is False:
            raise SkipTest()

        config = {'backend':
                        'services.resetcodes.rc_memcache.ResetCodeMemcache',
                  'nodes': ['127.0.0.1:11211'],
                  'debug': 1,
                  'expiration': 1}

        self._tests(load_and_configure(config))

    def test_reset_code_sreg(self):
        try:
            import wsgi_intercept
            from wsgi_intercept.urllib2_intercept import install_opener
            install_opener()
        except ImportError:
            return

        def _fake_response():
            return Response('0')

        def _no_email_response():
            r = Response()
            r.status = '400 Bad Request'
            r.body = str(ERROR_NO_EMAIL_ADDRESS)
            return r

        config = {'backend': 'services.resetcodes.rc_sreg.ResetCodeSreg',
                  'sreg_location': 'localhost',
                  'sreg_path': '',
                  'sreg_scheme': 'http'}

        mgr = load_and_configure(config)
        user = User()
        user['userid'] = 1
        user['username'] = 'telliott'

        wsgi_intercept.add_wsgi_intercept('localhost', 80, _fake_response)
        self.assertRaises(AlreadySentError, mgr.generate_reset_code, user)

        wsgi_intercept.add_wsgi_intercept('localhost', 80, _no_email_response)
        self.assertRaises(NoEmailError, mgr.generate_reset_code, user)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestResetCodeManager))
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
