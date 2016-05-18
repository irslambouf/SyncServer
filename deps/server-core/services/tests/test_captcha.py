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
#   Toby Elliott (telliott@mozilla.com)
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

try:
    from recaptcha.client import captcha   # NOQA
    _NO_CAPTCHA_LIB = False
except ImportError:
    _NO_CAPTCHA_LIB = True

from services.captcha import ServicesCaptcha
from services.tests.support import patch_captcha
from webob import Request


class TestCaptcha(unittest.TestCase):

    def test_captcha(self):
        key = 'foobarbaz'
        config = {'use': True, 'private_key': 'a', 'public_key': key,
                  'override': 'test'}

        if _NO_CAPTCHA_LIB:
            self.assertRaises(ImportError, ServicesCaptcha, config)
            return

        captcha = ServicesCaptcha(config)   # NOQA

        req = Request.blank('/')
        req.method = 'POST'
        req.body = 'recaptcha_challenge_field=foo&recaptcha_response_field=bar'

        patch_captcha(True)
        self.assertTrue(captcha.check(req))

        patch_captcha(False)
        self.assertFalse(captcha.check(req))

        self.assertTrue(key in captcha.form())

        req.headers['X-Captcha-Override'] = 'test'
        self.assertTrue(captcha.check(req))

        req.headers['X-Captcha-Override'] = 'test2'
        self.assertFalse(captcha.check(req))
