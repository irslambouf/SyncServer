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
import traceback

from webtest import TestApp

from syncreg.tests.support import initenv, cleanupenv
from syncreg.wsgiapp import make_app
from services.user import extract_username
from services.user import User
from services.pluginreg import load_and_configure
from syncreg import logger


class TestWsgiApp(unittest.TestCase):

    def setUp(self):
        # loading the app
        self.appdir, self.config, self.auth = initenv()
        self.app = TestApp(make_app(self.config))

        # adding a user if needed
        self.email = 'test_user%d@mozilla.com' % random.randint(1, 1000)
        self.user_name = extract_username(self.email)
        self.user = User(self.user_name)
        self.user_id = self.auth.get_user_id(self.user)
        self.password = 'x' * 9

        if self.user_id is None:
            self.auth.create_user(self.user_name, self.password, self.email)
            self.user_id = self.auth.get_user_id(self.user)

        # for the ldap backend, filling available_nodes
        if self.auth.__class__.__name__ == 'LDAPAuth':
            query = ('insert into available_nodes (node, ct, actives) values '
                     ' ("weave:localhost", 10, 10)')
            self.auth._engine.execute(query)

        try:
            self.nodes = load_and_configure(self.config, 'nodes')
        except KeyError:
            logger.debug(traceback.format_exc())
            logger.debug("No node library in place")
            self.nodes = None

        try:
            self.reset = load_and_configure(self.config, 'reset_codes')
        except Exception:
            logger.debug(traceback.format_exc())
            logger.debug("No reset code library in place")
            self.reset = None

    def tearDown(self):
        self.auth.delete_user(self.user, self.password)
        cef_logs = os.path.join(self.appdir, 'test_cef.log')
        if os.path.exists(cef_logs):
            os.remove(cef_logs)

        # Clear out the database.
        if "sqlite" not in self.auth.sqluri:
            self.auth._engine.execute('truncate users')
            self.auth._engine.execute('truncate collections')
            self.auth._engine.execute('truncate wbo')
            if self.auth.get_name() == 'ldap':
                self.auth._engine.execute('truncate available_nodes')

        # Remove any sqlite db files that we created.
        cleanupenv()
