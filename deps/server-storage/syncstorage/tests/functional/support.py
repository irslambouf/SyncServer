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
""" Base test class, with an instanciated app.
"""
import os
import unittest
import random
import urlparse

from webtest import TestApp
import wsgiproxy.app

from syncstorage.tests.support import initenv, cleanupenv
from syncstorage.wsgiapp import make_app


class WSGIProxyApp(wsgiproxy.app.WSGIProxyApp):

    def setup_forwarded_environ(self, environ):
        super(WSGIProxyApp, self).setup_forwarded_environ(environ)
        # Auth checks don't work if HTTP_HOST contains a standard port num.
        if environ["wsgi.url_scheme"] == "https":
            if environ["HTTP_HOST"].endswith(":443"):
                environ["HTTP_HOST"] = environ["HTTP_HOST"].rsplit(":", 1)[0]
        elif environ["wsgi.url_scheme"] == "http":
            if environ["HTTP_HOST"].endswith(":80"):
                environ["HTTP_HOST"] = environ["HTTP_HOST"].rsplit(":", 1)[0]


class TestWsgiApp(unittest.TestCase):

    def setUp(self):
        # loading the app
        self.appdir, self.config, self.storage, self.auth = initenv()
        # we don't support other storages for this test
        self.sql_driver = self.storage.sqluri.split(':/')[0]
        assert self.sql_driver in ('mysql', 'sqlite', 'pymysql')
        test_remote_url = os.environ.get("TEST_REMOTE")
        if test_remote_url is not None:
            self.distant = True
            test_remote_url_p = urlparse.urlparse(test_remote_url)
            self.app = TestApp(WSGIProxyApp(test_remote_url), extra_environ={
                "HTTP_HOST": test_remote_url_p.netloc,
                "wsgi.url_scheme": test_remote_url_p.scheme or "http",
                "SERVER_NAME": test_remote_url_p.hostname,
                "REMOTE_ADDR": "127.0.0.1",
            })
        else:
            self.distant = False
            self.app = TestApp(make_app(self.config))
        self._setup_user()

    def tearDown(self):
        self._teardown_user()
        if not self.distant:
            # Remove any generated log files.
            cef_logs = os.path.join(self.appdir, 'test_cef.log')
            if os.path.exists(cef_logs):
                os.remove(cef_logs)
            # Delete or truncate database we may have touched.
            if self.sql_driver != "sqlite":
                for storage in self.app.app.app.storages.itervalues():
                    storage._engine.execute('truncate users')
                    storage._engine.execute('truncate collections')
                    storage._engine.execute('truncate wbo')
        cleanupenv()

    def _setup_user(self):
        self.user_name = 'test_user_%d' % random.randint(1, 100000)
        self.password = 'x' * 9
        self.auth.create_user(self.user_name, self.password,
                              'tarek@mozilla.com')

    def _teardown_user(self):
        user_id = self.auth.get_user_id(self.user_name)
        self.storage.delete_storage(user_id)
        if not self.auth.delete_user(user_id, self.password):
            raise ValueError('Could not remove user "%s"' % self.user_name)
