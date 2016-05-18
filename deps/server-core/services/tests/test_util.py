# -*- coding: utf-8 -*-
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
import unittest
import time
import urllib2
import socket
import StringIO
import sys
import warnings
from test.test_support import check_warnings

from services.util import (function_moved, bigint2time, time2bigint,
                           batch, validate_password, ssha,
                           ssha256, valid_password, get_source_ip,
                           CatchErrorMiddleware, round_time)
from services.exceptions import BackendError
from services.tests.support import initenv, cleanupenv


def return2():
    return 2


def returnNum(num):
    return num


class FakeResult(object):
    headers = {}
    body = '{}'

    def getcode(self):
        return 200

    def read(self):
        return self.body


class TestUtil(unittest.TestCase):

    def setUp(self):
        initenv()
        self.oldopen = urllib2.urlopen
        urllib2.urlopen = self._urlopen

    def tearDown(self):
        urllib2.urlopen = self.oldopen
        cleanupenv()

    def _urlopen(self, req, timeout=None):
        url = req.get_full_url()
        if url == 'impossible url':
            raise ValueError()
        if url == 'http://dwqkndwqpihqdw.com':
            msg = 'Name or service not known'
            raise urllib2.URLError(socket.gaierror(-2, msg))

        if url in ('http://google.com', 'http://goodauth'):
            return FakeResult()
        if url == 'http://badauth':
            raise urllib2.HTTPError(url, 401, '', {}, None)
        if url == 'http://timeout':
            raise urllib2.URLError(socket.timeout())
        if url == 'http://error':
            raise urllib2.HTTPError(url, 500, 'Error', {}, None)
        if url == 'http://newplace':
            res = FakeResult()
            res.body = url + ' ' + req.headers['Authorization']
            return res
        if url == 'http://xheaders':
            res = FakeResult()
            headers = req.headers.items()
            headers.sort()
            res.body = str(headers)
            return res

        raise ValueError(url)

    def test_function_move(self):
        @function_moved('services.tests.test_util.return2')
        def return1():
            return 1

        @function_moved('services.tests.test_util.return2',
                        follow_redirect=False)
        def return3():
            return 3

        @function_moved('foo.bar.baz', follow_redirect=True)
        def bad_redirect():
            pass

        @function_moved('services.tests.test_util.returnNum')
        def new_function_profile():
            pass

        @function_moved('services.tests.test_util.returnNum', False)
        def return4():
            return returnNum(4)

        with warnings.catch_warnings(record=True) as w:
            #  Re-enable any warnings that might be suppressed.
            #  The context manager will undo this for us at the end.
            warnings.simplefilter("default")

            result = return1()
            self.assertEqual(result, 2)
            self.assertEqual(len(w), 1)
            self.assertTrue("moved to services.tests.test_util.return2"
                            in str(w[-1].message))

            result = return3()
            self.assertEqual(result, 3)
            self.assertTrue("moved to services.tests.test_util.return2"
                            in str(w[-1].message))

            self.assertRaises(ImportError, bad_redirect)
            self.assertRaises(TypeError, new_function_profile)
            self.assertEqual(return4(), 4)

    def test_bigint2time(self):
        self.assertEquals(bigint2time(None), None)

        # make sure we always get two-digits Decimals
        # even if the time ms is 0
        def check(value):
            res = bigint2time(time2bigint(round_time(value)))
            res = str(res)
            self.assertTrue('.' in res)
            self.assertEqual(len(str(res).split('.')[-1]), 2)

        for value in (1297417122.0, 1297417122.1, 97417122.18765):
            check(value)

    def test_time2bigint(self):
        now = time.time()
        two_digits = bigint2time(time2bigint(now))
        self.assertAlmostEqual(float(two_digits), now, places=1)

    def test_batch(self):
        self.assertEquals(len(list(batch(range(250)))), 3)
        self.assertEquals(len(list(batch(range(190)))), 2)
        self.assertEquals(len(list(batch(range(24, 25)))), 1)

    def test_validate_password(self):
        one = ssha('one')
        two = ssha256('two')
        self.assertTrue(validate_password('one', one))
        self.assertTrue(validate_password('two', two))

    def test_valid_password(self):
        self.assertFalse(valid_password(u'tarek', u'xx'))
        self.assertFalse(valid_password(u't' * 8, u't' * 8))
        self.assertTrue(valid_password(u'tarek', u't' * 8))
        self.assertFalse(valid_password(u'café' * 3, u'café' * 3))

    def test_get_source_ip(self):
        environ = {'HTTP_X_FORWARDED_FOR': 'one'}
        environ2 = {'REMOTE_ADDR': 'two'}
        environ3 = {'HTTP_X_FORWARDED_FOR': 'three, four,five',
                    'REMOTE_ADDR': 'no'}
        environ4 = {}
        self.assertEqual(get_source_ip(environ), 'one')
        self.assertEqual(get_source_ip(environ2), 'two')
        self.assertEqual(get_source_ip(environ3), 'three')
        self.assertEqual(get_source_ip(environ4), None)

    def test_middleware_exception(self):

        class BadClass(object):
            from webob.dec import wsgify

            @wsgify
            def __call__(self, request):
                raise Exception("fail!")

        def hello():
            return "hello"

        def fake_start_response(*args):
            pass

        app = CatchErrorMiddleware(BadClass(), hook=hello)

        errs = []

        def _error(err):
            errs.append(err)

        app.logger.error = _error

        old_std = sys.stdout
        sys.stdout = StringIO.StringIO()
        try:
            with check_warnings(quiet=True):
                result = app({}, fake_start_response)
        finally:
            sys.stdout = old_std

        self.assertEqual(result[0], "hello")
        self.assertEqual(len(errs), 2)
        # the first error logged is a md5 hash
        self.assertEqual(len(errs[0]), 32)

        # let's try the new style hooks
        def hello2(info):
            return str(info)

        app = CatchErrorMiddleware(BadClass(), hook=hello2)
        old_std = sys.stdout
        sys.stdout = StringIO.StringIO()
        try:
            result = app({}, fake_start_response)
        finally:
            sys.stdout = old_std

        self.assertTrue('crash_id' in result[0])

        # let's test the response
        app = CatchErrorMiddleware(BadClass())
        errs = []
        app.logger.error = _error
        old_std = sys.stdout
        sys.stdout = StringIO.StringIO()
        try:
            result = app({}, fake_start_response)
        finally:
            sys.stdout = old_std

        self.assertTrue(
            result[0].startswith('"application error: crash id'))

    def test_round_time(self):

        # returns a two-digits decimal of the current time
        res = round_time()
        self.assertEqual(len(str(res).split('.')[-1]), 2)

        # can take a timestamp
        res = round_time(129084.198271987)
        self.assertEqual(str(res), '129084.20')

        # can take a str timestamp
        res = round_time('129084.198271987')
        self.assertEqual(str(res), '129084.20')

        # bad values raise ValueErrors
        self.assertRaises(ValueError, round_time, 'bleh')
        self.assertRaises(ValueError, round_time, object())

        # changing the precision
        res = round_time(129084.198271987, precision=3)
        self.assertEqual(str(res), '129084.198')

    def test_request(self):

        class BackEndFails(object):
            from webob.dec import wsgify

            @wsgify
            def __call__(self, request):
                raise BackendError("meh", request=request)

        def hello():
            return "hello"

        def fake_start_response(*args):
            pass

        app = CatchErrorMiddleware(BackEndFails())
        errs = []

        def _error(err):
            errs.append(err)

        app.logger.error = _error
        old_std = sys.stdout
        sys.stdout = StringIO.StringIO()
        try:
            app({'REQUEST_METHOD': 'GET',
                 'PATH_INFO': '/meh',
                 'HTTP_HOST': 'blah.com'},
                fake_start_response)
        finally:
            sys.stdout = old_std

        self.assertTrue('GET /meh' in errs[1])
