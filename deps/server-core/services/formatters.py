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
# The Original Code is Weave Basic Object Server
#
# The Initial Developer of the Original Code is
# Mozilla Labs.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#	Toby Elliott (telliott@mozilla.com)
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
#
# This library contains functions associated with formatting our responses
# into appropriate outputs, as well as generic functions to detect which
# format might be needed.
#
# Support functions for templating and l10n should go in here as well

from webob import Response
import simplejson as json
import struct


def text_response(data, **kw):
    """Returns Response containing a plain text"""
    return Response(str(data), content_type='text/plain', **kw)


def json_response(data, **kw):
    """Returns Response containing a json string"""
    return Response(json.dumps(data, use_decimal=True),
                               content_type='application/json', **kw)


def html_response(data, **kw):
    """Returns Response containing a plain text"""
    return Response(str(data), content_type='text/html', **kw)


def newlines_response(lines, **kw):
    """Returns a Response object containing a newlines output."""
    def _convert(line):
        line = json.dumps(line, use_decimal=True).replace('\n', '\u000a')
        return '%s\n' % line

    data = [_convert(line) for line in lines]
    return Response(''.join(data), content_type='application/newlines', **kw)


def whoisi_response(lines, **kw):
    """Returns a Response object containing a whoisi output."""

    def _convert(line):
        line = json.dumps(line, use_decimal=True)
        size = struct.pack('!I', len(line))
        return '%s%s' % (size, line)

    data = [_convert(line) for line in lines]
    return Response(''.join(data), content_type='application/whoisi', **kw)


def convert_response(request, lines, **kw):
    """Returns the response in the appropriate format, depending on the accept
    request."""
    try:
        content_type = request.accept.best_match(('application/json',
                                                  'application/newlines',
                                                  'application/whoisi'))
    except (ValueError, AssertionError):
        # Bad input from the client could trigger either of these errors.
        content_type = None

    if content_type == 'application/newlines':
        return newlines_response(lines, **kw)
    elif content_type == 'application/whoisi':
        return whoisi_response(lines, **kw)

    # default response format is json
    # TODO: technically we should return "406 Not Acceptable" here.
    return json_response(lines, **kw)
