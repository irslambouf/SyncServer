# -*- encoding: utf8 -*-
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
#   Rob Miller (rmiller@mozilla.com)
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

from webob import Response
from webob.exc import HTTPUnauthorized, HTTPException

from services.config import Config
from services.wsgiauth import Authentication
from services.auth.dummy import DummyAuth
from services.user.memory import MemoryUser
from services.tests.support import make_request, initenv, cleanupenv


class BadPasswordAuthTool(DummyAuth):
    """Auth backend that refuses passwords containingg the letters b, a, d.

    This Auth backend will accept any usernames and passwords except those
    that contain the letters "b", "a", and "d" in any order.  It makes it easy
    to test a variety of passwords without having to re-configure each time.

    For successful auth, the user id is always 1.
    """

    def __init__(self, **kwds):
        self.check_node = kwds.pop("check_node", False)
        super(BadPasswordAuthTool, self).__init__(**kwds)

    def authenticate_user(self, username, password, host=None):
        for value in (username, password):
            if "b" in value and "a" in value and "d" in value:
                return None
        if host is not None and host != "localhost":
            return None
        return 1


class BadPasswordUserTool(MemoryUser):
    """User backend that refuses passwords containing the letters b, a, d.

    This User backend will accept any usernames and passwords except those
    that contain the letters "b", "a", and "d" in any order.  It makes it easy
    to test a variety of passwords without having to re-configure each time.

    For successful auth, the user id is always 1.
    """

    def authenticate_user(self, user, credentials, *args):
        for value in (user["username"], credentials["password"]):
            if "b" in value and "a" in value and "d" in value:
                return None
        user["userid"] = 1
        user["syncNode"] = "localhost"
        return 1


class AuthAPITestCases(object):
    """TestCases for the public Authentication API.

    This test case suite can be used to test the basic functionality of
    any Authentication class.  They use only the public API i.e. the
    "check" and "acknowledge" methods.

    If the auth class does not understand HTTP-Basic-Auth credentials, you
    can override the set_credentials() method to implement whatever scheme
    it requires.

    Note that this is *not* a unittest.TestCase suite; you will need to mix
    it into an appropriate TestCase suite in order to use it.
    """

    auth_class = None

    BASE_CONFIG = {'cef.version': '0.0',
                   'cef.vendor': 'test',
                   'cef.device_version': '0.0',
                   'cef.product': 'test',
                   'cef.file': 'test',
                   'auth.backend':
                        'services.tests.test_wsgiauth.BadPasswordAuthTool'}

    def make_config(self, items=None):
        config = self.BASE_CONFIG.copy()
        if items:
            config.update(items)
        return Config(config)

    def set_credentials(self, request, username, password):
        """Set the given user credentials on the request.

        This default implementation sets HTTP-Basic-Auth credentials.
        Override it if your Authentication subclass needs something else.
        """
        password = password.encode("utf8")
        token = 'Basic ' + base64.b64encode('%s:%s' % (username, password))
        request.headers["Authorization"] = token

    def setUp(self):
        #  Check that we're not running from the base class.
        assert self.auth_class is not None
        initenv()

    def tearDown(self):
        cleanupenv()

    def test_check_method(self):
        config = self.make_config()
        auth = self.auth_class(config)

        #  check() should pass through requests where no auth is required
        req = make_request('/1.0/tarek/info/collections')
        auth.check(req, {})

        #  check() should demand auth when required by the match.
        req = make_request('/1.0/tarek/info/collections')
        self.assertRaises(HTTPException, auth.check, req, {"auth": "True"})

        #  check() should fail auth when the password is bad
        req = make_request('/1.0/tarek/info/collections')
        self.set_credentials(req, "user", "badpwd")
        self.assertRaises(HTTPException, auth.check, req, {"auth": "True"})

        #  check() should pass through when the password is good
        req = make_request('/1.0/tarek/info/collections')
        self.set_credentials(req, "user", "goodpwd")
        auth.check(req, {"auth": "True"})
        self.assertEquals(req.user["username"], "user")
        self.assertEquals(req.user["userid"], 1)

        #  check() should fail auth if username doesn't match the match
        match = {"auth": "True", "username": "user1"}
        req = make_request('/1.0/tarek/info/collections')
        self.set_credentials(req, "user2", "goodpwd")
        self.assertRaises(HTTPException, auth.check, req, match)

        #  check() should pass through if username matches the match
        match = {"auth": "True", "username": "user1"}
        req = make_request('/1.0/tarek/info/collections')
        self.set_credentials(req, "user1", "goodpwd")
        auth.check(req, match)

    def test_acknowledge_method(self):
        config = self.make_config()
        auth = self.auth_class(config)

        # Actually there's not much to test here.
        # Just make sure it doesn't raise anything.
        req = make_request('/1.0/tarek/info/collections')
        resp = Response(status="200 OK", request=req)
        auth.acknowledge(req, resp)

        req = make_request('/1.0/tarek/info/collections')
        self.set_credentials(req, "user", "goodpwd")
        auth.check(req, {"auth": "True"})
        resp = Response(status="200 OK", request=req)
        auth.acknowledge(req, resp)

    def test_unusual_passwords(self):
        config = self.make_config()
        auth = self.auth_class(config)

        # Check that passwords containing unusual characters still work.
        unusual_chars = u":!@= \t\n\N{GREEK SMALL LETTER ALPHA}\N{SNOWMAN}"
        for char in unusual_chars:

            # works at start of good pwd
            req = make_request('/1.0/tarek/info/collections')
            self.set_credentials(req, "user", char + "goodpwd")
            auth.check(req, {"auth": "True"})

            # works at end of good pwd
            req = make_request('/1.0/tarek/info/collections')
            self.set_credentials(req, "user", "goodpwd" + char)
            auth.check(req, {"auth": "True"})

            # works in middle of good pwd
            req = make_request('/1.0/tarek/info/collections')
            self.set_credentials(req, "user", "good" + char + "pwd")
            auth.check(req, {"auth": "True"})

            # fails at start of bad pwd
            req = make_request('/1.0/tarek/info/collections')
            self.set_credentials(req, "user", char + "badpwd")
            self.assertRaises(HTTPException, auth.check, req, {"auth": "True"})

            # fails at end of bad pwd
            req = make_request('/1.0/tarek/info/collections')
            self.set_credentials(req, "user", "badwd" + char)
            self.assertRaises(HTTPException, auth.check, req, {"auth": "True"})

            # fails in middle of bad pwd
            req = make_request('/1.0/tarek/info/collections')
            self.set_credentials(req, "user", "bad" + char + "pwd")
            self.assertRaises(HTTPException, auth.check, req, {"auth": "True"})

    def test_syncNode_checking(self):
        config = self.make_config({"auth.check_node": True})
        auth = self.auth_class(config)

        #  check() should pass for requests to "localhost"
        req = make_request("/1.0/tarek/info/collections", host="localhost")
        self.set_credentials(req, "user", "goodpwd")
        auth.check(req, {"auth": "True"})

        # check() should fail if request to the wrong node
        req = make_request("/1.0/tarek/info/collections", host="badnode")
        self.set_credentials(req, "user", "goodpwd")
        self.assertRaises(HTTPException, auth.check, req, {"auth": "True"})


class HTTPBasicAuthAPITestCases(AuthAPITestCases):
    """TestCases for the public Authentication API using HTTP-Basic-Auth.

    This test case suite can be used to test the functionality of any
    Authentication class that interprets HTTP-Basic-Auth headers. It uses
    only the public API i.e. the "check" and "acknowledge" methods.

    Note that this is *not* a unittest.TestCase suite; you will need to mix
    it into an appropriate TestCase suite in order to use it.
    """

    def test_bad_utf8_password(self):
        config = self.make_config()
        auth = self.auth_class(config)

        password = u'И'.encode('cp866')
        token = 'tarek:%s' % password
        token = 'Basic ' + base64.b64encode(token)
        req = make_request('/1.0/tarek/info/collections',
                           {'HTTP_AUTHORIZATION': token})
        self.assertRaises(HTTPUnauthorized, auth.check, req, {"auth": "True"})

    def test_malformed_auth_headers(self):
        config = self.make_config()
        auth = self.auth_class(config)

        req = make_request('/1.0/tarekbad',
                            {'HTTP_AUTHORIZATION': 'Basic ',
                             'REQUEST_METHOD': 'TEST',
                             'PATH_INFO': 'TEST'})
        self.assertRaises(HTTPUnauthorized, auth.check, req, {"auth": "True"})

        req = make_request('/1.0/tarekbad',
                            {'HTTP_AUTHORIZATION': 'Basic invalid_b64',
                             'REQUEST_METHOD': 'TEST',
                             'PATH_INFO': 'TEST'})
        self.assertRaises(HTTPUnauthorized, auth.check, req, {"auth": "True"})

        req = make_request('/1.0/tarekbad',
                            {'HTTP_AUTHORIZATION': 'Basic ' +
                              base64.b64encode('malformed_creds'),
                             'REQUEST_METHOD': 'TEST',
                             'PATH_INFO': 'TEST'})
        self.assertRaises(HTTPUnauthorized, auth.check, req, {"auth": "True"})


class TestAuthentication(HTTPBasicAuthAPITestCases, unittest.TestCase):
    """Tests for base Authentication class."""

    auth_class = Authentication

    def test_authenticate_user(self):

        config = self.make_config()
        auth = self.auth_class(config)

        token = 'Basic ' + base64.b64encode('tarek:tarek')
        req = make_request('/1.0/tarek/info/collections', {})
        res = auth.authenticate_user(req, {})
        self.assertEquals(res, None)

        # authenticated by auth
        req = make_request('/1.0/tarek/info/collections',
                           {'HTTP_AUTHORIZATION': token})
        res = auth.authenticate_user(req, {})
        self.assertEquals(res, 1)

        # weird tokens should not break the function
        bad_token1 = 'Basic ' + base64.b64encode('tarektarek')
        bad_token2 = 'Basic' + base64.b64encode('tarek:tarek')
        req = make_request('/1.0/tarek/info/collections',
                           {'HTTP_AUTHORIZATION': bad_token1})
        self.assertRaises(HTTPUnauthorized, auth.authenticate_user, req,
                          config)

        req = make_request('/1.0/tarek/info/collections',
                           {'HTTP_AUTHORIZATION': bad_token2})
        self.assertRaises(HTTPUnauthorized, auth.authenticate_user, req,
                          config)

        # check a bad request to an invalid user.
        req = make_request('/1.0/tarekbad',
                           {'HTTP_AUTHORIZATION': 'Basic ' +
                            base64.b64encode('tarekbad:tarek'),
                            'REQUEST_METHOD': 'TEST',
                            'PATH_INFO': 'TEST'})
        self.assertRaises(HTTPUnauthorized, auth.authenticate_user, req,
                          config)


class TestAuthentication_NewStyleAuth(TestAuthentication):

    BASE_CONFIG = TestAuthentication.BASE_CONFIG.copy()
    BASE_CONFIG["auth.backend"] = \
                        'services.tests.test_wsgiauth.BadPasswordUserTool'


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestAuthentication))
    suite.addTest(unittest.makeSuite(TestAuthentication_NewStyleAuth))
    return suite


if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
