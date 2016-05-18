# -*- encoding: utf-8 -*-
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
#   Ryan Kelly (rkelly@mozilla.com)
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

from nose.plugins.skip import SkipTest

from services.whoauth import WhoAuthentication, HAVE_REPOZE_WHO
from services.whoauth.backendauth import BackendAuthPlugin
from services.tests.test_wsgiauth import HTTPBasicAuthAPITestCases


class TestWhoAuthentication(HTTPBasicAuthAPITestCases, unittest.TestCase):
    """Tests for WhoAuthentication class in default configuration."""
    auth_class = WhoAuthentication

    def setUp(self):
        if not HAVE_REPOZE_WHO:
            raise SkipTest
        super(TestWhoAuthentication, self).setUp()

    # Unfortunately repoze.who forcibly decodes all basic-auth passwords into
    # unicode, falling back to latin1 if the utf8 is invalid.  That makes this
    # test rather pointless.
    def test_bad_utf8_password(self):
        pass


class TestWhoAuthentication_NewStyleAuth(TestWhoAuthentication):
    """Tests for WhoAuthentication class using new-style auth backend."""
    BASE_CONFIG = TestWhoAuthentication.BASE_CONFIG.copy()
    BASE_CONFIG["auth.backend"] = \
                        'services.tests.test_wsgiauth.BadPasswordUserTool'

WHO_CONFIG = {
    "who.plugin.basic.use": "repoze.who.plugins.basicauth:make_plugin",
    "who.plugin.basic.realm": "Sync",
    "who.plugin.backend.use": "services.whoauth.backendauth:make_plugin",
    "who.authenticators.plugins": "backend",
    "who.identifiers.plugins": "basic",
    "who.challengers.plugins": "basic",
    }

class TestWhoAuthentication_FromConfig(TestWhoAuthentication):
    """Tests for WhoAuthentication class loaded from a config file"""
    BASE_CONFIG = TestWhoAuthentication.BASE_CONFIG.copy()
    BASE_CONFIG.update(WHO_CONFIG)


class GenericPlugin(BackendAuthPlugin):
    """Simulate a generic repoze.who plugin that doesn't know our needs.

    This class delegates to the usual BackendAuth plugin, but pretends that
    it doesn't know how to populate "userid" or "username" fields in the
    identity dict.  It tests the ability of the WhoAuthenticator class to
    synthesize these properties as needed.
    """

    def authenticate(self, environ, identity):
        username = BackendAuthPlugin.authenticate(self, environ, identity)
        if username is not None:
            identity.pop("username", None)
            identity.setdefault("uid", identity.pop("userid", None))
        return username
    
WHO_CONFIG_GENERICPLUGIN = {
    "who.plugin.basic.use": "repoze.who.plugins.basicauth:make_plugin",
    "who.plugin.basic.realm": "Sync",
    "who.plugin.backend.use": "services.tests.test_whoauth:GenericPlugin",
    "who.authenticators.plugins": "backend",
    "who.identifiers.plugins": "basic",
    "who.challengers.plugins": "basic",
    }


class TestWhoAuthentication_GenericPlugin(TestWhoAuthentication):
    """Tests for WhoAuthentication class using a generic auth plugin."""
    BASE_CONFIG = TestWhoAuthentication.BASE_CONFIG.copy()
    BASE_CONFIG.update(WHO_CONFIG_GENERICPLUGIN)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestWhoAuthentication))
    suite.addTest(unittest.makeSuite(TestWhoAuthentication_NewStyleAuth))
    suite.addTest(unittest.makeSuite(TestWhoAuthentication_FromConfig))
    return suite


if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
