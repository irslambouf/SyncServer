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
# Portions created by the Initial Developer are Copyright (C) 2011
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
import smtplib
from email import message_from_string
from services.emailer import valid_email, send_email


class TestEmailer(unittest.TestCase):

    def test_valid_email(self):
        self.assertFalse(valid_email('tarek'))
        self.assertFalse(valid_email('tarek@moz'))
        self.assertFalse(valid_email('tarek@192.12.32334.3'))

        self.assertTrue(valid_email('tarek@mozilla.com'))
        self.assertTrue(valid_email('tarek+sync@mozilla.com'))
        self.assertTrue(valid_email('tarek@127.0.0.1'))

    def test_send_email(self):
        # let's patch smtplib and collect mails that are being produced
        # and load them into message objects

        class FakeMailer(object):

            mails = []

            def __init__(self, *args, **kw):
                pass

            def sendmail(self, sender, rcpts, msg):
                self.mails.append((sender, rcpts, msg))

            def quit(self):
                pass

        subject = u"Hello there"
        body = u"ah yeah"
        old = smtplib.SMTP
        smtplib.SMTP = FakeMailer
        try:
            # e-mail with real names
            send_email(u'Tarek Ziadé <tarek@mozilla.com>',
                       u'John Doe <someone@somewhere.com>',
                       subject, body)

            # let's load it
            mail = message_from_string(FakeMailer.mails[-1][-1])
            self.assertEqual(mail['From'],
                             '=?utf-8?q?Tarek_Ziad=C3=A9?= ' +
                             '<tarek@mozilla.com>')

            self.assertEqual(mail['To'],
                            'John Doe <someone@somewhere.com>')

            # simple e-mail
            send_email(u'<tarek@mozilla.com>',
                       u'<someone@somewhere.com>',
                       subject, body)

            # let's load it
            mail = message_from_string(FakeMailer.mails[-1][-1])
            self.assertEqual(mail['From'], '<tarek@mozilla.com>')
            self.assertEqual(mail['To'], '<someone@somewhere.com>')

            # basic e-mail
            send_email(u'tarek@mozilla.com',
                       u'someone@somewhere.com',
                       subject, body)

            # let's load it
            mail = message_from_string(FakeMailer.mails[-1][-1])
            self.assertEqual(mail['From'], 'tarek@mozilla.com')
            self.assertEqual(mail['To'], 'someone@somewhere.com')

            # XXX That should not happen
            # now what happens if we get strings
            send_email('tarek@mozilla.com', 'someone@somewhere.com',
                       subject, body)

            # let's load it
            mail = message_from_string(FakeMailer.mails[-1][-1])
            self.assertEqual(mail['From'], 'tarek@mozilla.com')
            self.assertEqual(mail['To'], 'someone@somewhere.com')

            send_email('Tarek Ziadé <tarek@mozilla.com>',
                       'someone@somewhere.com', subject, body)

            # let's load it
            mail = message_from_string(FakeMailer.mails[-1][-1])
            self.assertEqual(mail['From'],
                             '=?utf-8?q?Tarek_Ziad=C3=A9?= ' +
                             '<tarek@mozilla.com>')
            self.assertEqual(mail['To'], 'someone@somewhere.com')
        finally:
            smtplib.SMTP = old
