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

from webob import Request

from services.formatters import (json_response, newlines_response,
                                whoisi_response, text_response,
                                convert_response)


class TestFormatters(unittest.TestCase):

    def test_response_conversions(self):
        data = {'some': 'data'}
        resp = text_response(data)
        self.assertEquals(resp.body, "{'some': 'data'}")
        self.assertEquals(resp.content_type, 'text/plain')

        data = "abc"
        resp = whoisi_response(data)
        self.assertEquals(resp.body,
                '\x00\x00\x00\x03"a"\x00\x00\x00\x03"b"\x00\x00\x00\x03"c"')
        self.assertEquals(resp.content_type, 'application/whoisi')

        request = Request({})
        request.accept = 'application/whoisi'
        resp = convert_response(request, data)
        self.assertEquals(resp.body,
                '\x00\x00\x00\x03"a"\x00\x00\x00\x03"b"\x00\x00\x00\x03"c"')
        self.assertEquals(resp.content_type, 'application/whoisi')

        resp = newlines_response(data)
        self.assertEquals(resp.body, '"a"\n"b"\n"c"\n')
        self.assertEquals(resp.content_type, 'application/newlines')

        request = Request({})
        request.accept = 'application/newlines'
        resp = convert_response(request, data)
        self.assertEquals(resp.body, '"a"\n"b"\n"c"\n')
        self.assertEquals(resp.content_type, 'application/newlines')

        data = {'some': 'data'}
        resp = json_response(data)
        self.assertEquals(resp.body, '{"some": "data"}')
        self.assertEquals(resp.content_type, 'application/json')

        request = Request({})
        resp = convert_response(request, data)
        self.assertEquals(resp.body, '{"some": "data"}')
        self.assertEquals(resp.content_type, 'application/json')
