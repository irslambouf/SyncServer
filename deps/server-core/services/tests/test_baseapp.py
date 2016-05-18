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
import base64
import os.path
import threading
from time import sleep

from services.baseapp import SyncServerApp
from services.util import BackendError
from services.events import (subscribe, REQUEST_STARTS, REQUEST_ENDS,
                             unsubscribe, APP_ENDS)
from services.wsgiauth import Authentication
from services.tests.support import make_request

from webob.exc import HTTPUnauthorized, HTTPServiceUnavailable, HTTPNotFound


class _Foo(object):
    def __init__(self, app):
        self.app = app

    def index(self, request):
        return str(request.config['one.two'])

    def secret(self, request):
        return 'here'

    def boom(self, request):
        raise BackendError(server='http://here', retry_after=10)

    def boom2(self, request):
        raise BackendError(server='http://here')

    def boom3(self, request):
        raise BackendError(server='http://here', retry_after=0)

    def user(self, request):
        return '|%s|' % request.user.get('username', None)

    def missing(self, request):
        raise HTTPNotFound(request)


class Mod1(object):
    pass


class Mod2(object):
    pass


heredir = os.path.dirname(__file__)
metlog_cfg_path = os.path.join(heredir, 'metlog_test.ini')


class TestBaseApp(unittest.TestCase):

    urls = [('POST', '/', 'foo', 'index'),
            ('GET', '/secret', 'foo', 'secret', {'auth': True}),
            ('GET', '/user/{username:[a-zA-Z0-9._-]+}', 'foo', 'user'),
            ('GET', '/missing', 'foo', 'missing'),
            ('GET', '/boom', 'foo', 'boom'),
            ('GET', '/boom2', 'foo', 'boom2'),
            ('GET', '/boom3', 'foo', 'boom3')]
    controllers = {'foo': _Foo}
    config = {'host:here.one.two': 1,
              'one.two': 2,
              'auth.backend': 'services.auth.dummy.DummyAuth',
              'app.modules': ['mod1', 'mod2', 'metlog_loader'],
              'mod1.backend': 'services.tests.test_baseapp.Mod1',
              'mod2.backend': 'services.tests.test_baseapp.Mod2',
              'cef.use': 'true',
              'cef.file': 'syslog',
              'cef.vendor': 'mozilla',
              'cef.version': '0',
              'cef.device_version': '1.3',
              'cef.product': 'weave',
              'metlog_loader.backend': 'services.metrics.MetlogLoader',
              'metlog_loader.config': metlog_cfg_path,
              }
    auth_class = None

    def setUp(self):
        self.app = SyncServerApp(self.urls, self.controllers, self.config,
                                 auth_class=self.auth_class)

    def test_host_config(self):
        request = make_request("/", method='POST', host='localhost')
        res = self.app(request)
        self.assertEqual(res.body, '2')

        request = make_request("/", method='POST', host='here')
        res = self.app(request)
        self.assertEqual(res.body, '1')

    def test_auth(self):
        """Test authentication using the specific auth class."""
        # we don't have any auth, this should just work
        request = make_request("/secret", method='GET')
        res = self.app(request)
        self.assertEqual(res.body, 'here')

    def test_retry_after(self):
        config = {'global.retry_after': 60,
                  'auth.backend': 'services.auth.dummy.DummyAuth',
                  'app.modules': ['metlog_loader'],
                  'metlog_loader.backend': 'services.metrics.MetlogLoader',
                  'metlog_loader.config': metlog_cfg_path,
                  }
        urls = [('GET', '/boom', 'foo', 'boom'),
                ('GET', '/boom2', 'foo', 'boom2'),
                ('GET', '/boom3', 'foo', 'boom3')]

        controllers = {'foo': _Foo}
        app = SyncServerApp(urls, controllers, config,
                            auth_class=self.auth_class)

        request = make_request("/boom", method="GET", host="localhost")
        try:
            app(request)
        except HTTPServiceUnavailable, error:
            self.assertEqual(error.headers['Retry-After'], '10')
        else:
            raise AssertionError()

        # default retry_after value
        request = make_request("/boom2", method="GET", host="localhost")
        try:
            app(request)
        except HTTPServiceUnavailable, error:
            self.assertEqual(error.headers['Retry-After'], '60')
        else:
            raise AssertionError()

        # no retry-after (set to -1)
        request = make_request("/boom3", method="GET", host="localhost")
        logger = app.logger
        old = logger.error
        errors = []

        def _error(msg):
            errors.append(msg)
        logger.error = _error

        try:
            try:
                app(request)
            except HTTPServiceUnavailable, error:
                self.assertFalse('Retry-After' in error.headers)
            else:
                raise AssertionError()
        finally:
            logger.error = old

        self.assertTrue(errors[1].startswith('GET /boom'))
        for value in app.get_infos(request).values():
            self.assertTrue(value in errors[1])

    def test_heartbeat_debug_pages(self):

        config = {'global.heartbeat_page': '__heartbeat__',
                  'global.debug_page': '__debug__',
                  'app.modules': ['metlog_loader'],
                  'metlog_loader.backend': 'services.metrics.MetlogLoader',
                  'metlog_loader.config': metlog_cfg_path,
                  'auth.backend': 'services.auth.dummy.DummyAuth'}
        urls = []
        controllers = {}

        # testing the default configuration
        app = SyncServerApp(urls, controllers, config,
                            auth_class=self.auth_class)

        # a heartbeat returns a 200 / empty body
        request = make_request("/__heartbeat__")
        res = app(request)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(res.body, '')

        # we can get heartbeats with a HEAD call
        request = make_request("/__heartbeat__", method="HEAD")
        res = app(request)
        self.assertEqual(res.status_int, 200)
        self.assertEqual(res.body, '')

        # the debug page returns a 200 / info in the body
        request = make_request("/__debug__")
        res = app(request)
        self.assertEqual(res.status_int, 200)
        self.assertTrue("'REQUEST_METHOD': 'GET'" in res.body)

        # now let's create an app with extra heartbeating
        # and debug info
        class MyCoolApp(SyncServerApp):

            def _debug_server(self, request):
                return ['DEEBOOG']

            def _check_server(self, request):
                raise HTTPServiceUnavailable()

        # testing that new app
        app = MyCoolApp(urls, controllers, config, auth_class=self.auth_class)

        # a heartbeat returns a 503 / empty body
        request = make_request("/__heartbeat__")
        self.assertRaises(HTTPServiceUnavailable, app, request)

        # the debug page returns a 200 / info in the body
        request = make_request("/__debug__")
        res = app(request)
        self.assertEqual(res.status_int, 200)
        self.assertTrue("DEEBOOG" in res.body)

    def test_user(self):
        # the debug page returns a the right username in the body
        request = make_request("/user/testuser")
        res = self.app(request)
        self.assertEqual(res.status_int, 200)
        self.assertTrue("|testuser|" in res.body)

    def test_notfound(self):
        # test that non-existent pages raise a 404.
        # this one has no match, so it will return early
        request = make_request("/nonexistent")
        self.assertEquals(self.app(request).status, "404 Not Found")
        # this one has a match, will raise from below the auth handler
        request = make_request("/missing")
        self.assertRaises(HTTPNotFound, self.app, request)

    def test_methodnotallowed(self):
        request = make_request("/", method="OST")
        self.assertEquals(self.app(request).status, "405 Method Not Allowed")

    def test_route_match_with_empty_path(self):
        request = make_request("", method="OST")
        self.assertEquals(self.app(request).status, "404 Not Found")

    def test_events(self):

        pings = []

        def starts(request):
            pings.append('starts')

        def ends(response):
            pings.append('ends')

        subscribe(REQUEST_STARTS, starts)
        subscribe(REQUEST_ENDS, ends)
        try:
            config = {'global.heartbeat_page': '__heartbeat__',
                      'global.debug_page': '__debug__',
                      'auth.backend': 'services.auth.dummy.DummyAuth'}
            urls = []
            controllers = {}
            app = SyncServerApp(urls, controllers, config,
                                auth_class=self.auth_class)
            request = make_request("/user/__hearbeat__")
            app(request)
        finally:
            unsubscribe(REQUEST_STARTS, starts)
            unsubscribe(REQUEST_ENDS, ends)

        self.assertEquals(pings, ['starts', 'ends'])

    def test_crash_id(self):
        # getting a 50x should generate a crash id
        request = make_request("/boom")
        try:
            self.app(request)
        except HTTPServiceUnavailable, err:
            self.assertTrue('application error: crash id' in str(err))
        else:
            raise AssertionError('Should raise')

    def test_graceful_shutdown(self):

        pings = []

        def end():
            pings.append('app ends')

        subscribe(APP_ENDS, end)
        try:
            config = {'global.heartbeat_page': '__heartbeat__',
                      'global.debug_page': '__debug__',
                      'auth.backend': 'services.auth.dummy.DummyAuth',
                      'global.graceful_shutdown_interval': 1,
                      'global.hard_shutdown_interval': 1}

            urls = []
            controllers = {}
            app = SyncServerApp(urls, controllers, config,
                                auth_class=self.auth_class)

            # heartbeat should work
            request = make_request("/__heartbeat__")
            app(request)

            # let's "kill it" in a thread
            class Killer(threading.Thread):
                def __init__(self, app):
                    threading.Thread.__init__(self)
                    self.app = app

                def run(self):
                    self.app._sigterm(None, None)

            killer = Killer(app)
            killer.start()
            sleep(0.2)

            # in the meantime, /heartbeat should return a 503
            request = make_request("/__heartbeat__")
            self.assertRaises(HTTPServiceUnavailable, app, request)

            # but regular requests should still work
            request = make_request("/")
            app(request)

            # sleeping
            sleep(1.)

            # now / should 503 too
            request = make_request("/")
            self.assertRaises(HTTPServiceUnavailable, app, request)

            killer.join()

        finally:
            unsubscribe(APP_ENDS, end)

        # and we should have had a event ping
        self.assertEquals(pings, ['app ends'])

    def test_nosigclean(self):
        # check that we can deactivate sigterm/sigint hooks
        pings = []

        def end():
            pings.append('app ends')

        subscribe(APP_ENDS, end)
        try:
            config = {'global.heartbeat_page': '__heartbeat__',
                      'global.debug_page': '__debug__',
                      'auth.backend': 'services.auth.dummy.DummyAuth',
                      'global.clean_shutdown': False}

            urls = []
            controllers = {}
            app = SyncServerApp(urls, controllers, config,
                                auth_class=self.auth_class)

            # heartbeat should work
            request = make_request("/__heartbeat__")
            app(request)

        finally:
            unsubscribe(APP_ENDS, end)

        # and we should have had no ping
        self.assertEquals(pings, [])

    def test_modules_loaded(self):
        mod1 = self.app.modules['mod1']
        mod2 = self.app.modules['mod2']
        self.assertEqual(mod1.__class__, Mod1)
        self.assertEqual(mod2.__class__, Mod2)


class TestBaseApp_Auth(TestBaseApp):

    auth_class = Authentication

    def test_auth(self):
        # it should ask us to authenticate using HTTP-Basic-Auth
        request = make_request("/secret", method='GET')
        try:
            self.app(request)
        except HTTPUnauthorized, error:
            self.assertEqual(error.headers['WWW-Authenticate'],
                             'Basic realm="Sync"')
        else:
            raise AssertionError('Excepted a failure here')

        # it should accept credentials using HTTP-Basic-Auth
        auth = 'Basic %s' % base64.b64encode('tarek:tarek')
        request.environ['HTTP_AUTHORIZATION'] = auth
        res = self.app(request)
        self.assertEqual(res.body, 'here')


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestBaseApp))
    suite.addTest(unittest.makeSuite(TestBaseApp_Auth))
    return suite


if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
