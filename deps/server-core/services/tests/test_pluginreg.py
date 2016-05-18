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
import abc

from services.config import Config
from services.pluginreg import PluginRegistry, load_and_configure


class ClassInterface(PluginRegistry):
    """Abstract"""
    @abc.abstractmethod
    def foo(self):
        pass


class ImplementsCorrectly(object):
    def foo(self):
        pass


class ImplementsBadly(object):
    def bar(self):
        pass


class Dummy(object):
    def __init__(self, foo=None, **kw):
        self.foo = foo


class Buggy(object):
    def __init__(self):
        raise IOError('boom')


class Cool(object):
    pass


class TestPlugin(unittest.TestCase):

    def test_get(self):
        self.assertRaises(KeyError, PluginRegistry.get, 'xxx')

        PluginRegistry.register(Buggy)
        self.assertRaises(IOError, PluginRegistry.get,
                    'services.tests.test_pluginreg.Buggy')

        name = 'services.tests.test_pluginreg.Cool'
        PluginRegistry.register(Cool)
        p = PluginRegistry.get(name)
        self.assertTrue(isinstance(p, Cool))

    def test_load_direct(self):
        from services.tests.test_pluginreg import Dummy
        bad_config = Config({'backend': 'xxx'})
        good_config = Config({'test.backend':
                              'services.tests.test_pluginreg.Dummy',
                              'test.foo': 'bar'})
        self.assertRaises(KeyError, load_and_configure, bad_config)
        obj = load_and_configure(good_config, 'test')
        self.assertTrue(isinstance(obj, Dummy))
        self.assertTrue(obj.foo == 'bar')

        missing_interface = {'interface': 'services.tests.test_pluginreg.Nope'}
        bad_interface = {'backend':
                         'services.tests.test_pluginreg.ImplementsBadly',
                         'interface':
                         'services.tests.test_pluginreg.ClassInterface'}
        good_interface = {'backend':
                         'services.tests.test_pluginreg.ImplementsCorrectly',
                         'interface':
                         'services.tests.test_pluginreg.ClassInterface'}
        obj = load_and_configure(good_interface)
        self.assertTrue(isinstance(obj, ImplementsCorrectly))
        self.assertRaises(TypeError, load_and_configure, bad_interface)
        self.assertRaises(ImportError, load_and_configure, missing_interface)

    def test_invariant(self):
        from services.tests.test_pluginreg import Dummy
        config = {'backend': 'services.tests.test_pluginreg.Dummy',
                  'foo': 'bar'}
        obj = load_and_configure(config)
        self.assertTrue(isinstance(obj, Dummy))

        # second call, same config dict, should work
        obj = load_and_configure(config)
        self.assertTrue(isinstance(obj, Dummy))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestPlugin))
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
