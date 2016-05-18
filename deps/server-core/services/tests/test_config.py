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
#   Rob Miller (rob@mozilla.com)
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
import tempfile
import os
from StringIO import StringIO

from services.config import (SvcConfigParser, EnvironmentNotFoundError,
                             Config)


_FILE_ONE = """\
[DEFAULT]
extends = %s

[one]
foo = bar
num = -12
st = "o=k"
lines = 1
        two
        3

env = some ${__STUFF__}

[two]
a = b
"""

_FILE_TWO = """\
[one]
foo = baz
two = "a"

[three]
more = stuff
"""

_FILE_THREE = """\
[DEFAULT]
extends = no-no,no-no-no-no,no-no-no-no,theresnolimit

[one]
foo = bar
"""

_FILE_FOUR = """\
[global]
foo = bar
baz = bawlp

[auth]
a = b
c = d

[storage]
e = f
g = h

[multi:once]
storage.i = j
storage.k = l

[multi:thrice]
storage.i = jjj
storage.k = lll
"""

_EXTRA = """\
[some]
stuff = True

[other]
thing = ok
"""


class ConfigTestCase(unittest.TestCase):

    def setUp(self):
        os.environ['__STUFF__'] = 'stuff'
        fp, filename = tempfile.mkstemp()
        f = os.fdopen(fp, 'w')
        f.write(_FILE_TWO)
        f.close()
        self.file_one = StringIO(_FILE_ONE % filename)
        self.file_two = filename
        self.file_three = StringIO(_FILE_THREE)

        fp, filename = tempfile.mkstemp()
        f = os.fdopen(fp, 'w')
        f.write(_FILE_FOUR)
        f.close()
        self.file_four = filename

    def tearDown(self):
        if '__STUFF__' in os.environ:
            del os.environ['__STUFF__']
        os.remove(self.file_two)

    def test_reader(self):
        config = SvcConfigParser(self.file_one)

        # values conversion
        self.assertEquals(config.get('one', 'foo'), 'bar')
        self.assertEquals(config.get('one', 'num'), -12)
        self.assertEquals(config.get('one', 'st'), 'o=k')
        self.assertEquals(config.get('one', 'lines'), [1, 'two', 3])
        self.assertEquals(config.get('one', 'env'), 'some stuff')

        # getting a map
        map = config.get_map()
        self.assertEquals(map['one.foo'], 'bar')

        map = config.get_map('one')
        self.assertEquals(map['foo'], 'bar')

        del os.environ['__STUFF__']
        self.assertRaises(EnvironmentNotFoundError, config.get, 'one', 'env')

        # extends
        self.assertEquals(config.get('three', 'more'), 'stuff')
        self.assertEquals(config.get('one', 'two'), 'a')

    def test_nofile(self):
        # if a user tries to use an inexistant file in extensios,
        # pops an error
        self.assertRaises(IOError, SvcConfigParser, self.file_three)

    def test_config(self):
        cfg_in = {'one': '1', 'two': 'bla', 'three': 'false'}
        config = Config(cfg_in)

        self.assertTrue(config['one'])
        self.assertEqual(config['two'], 'bla')
        self.assertFalse(config['three'])

        # config also reads extra config files.
        __, filename = tempfile.mkstemp()
        try:
            with open(filename, 'w') as f:
                f.write(_EXTRA)

            cfg_in = {'one': '1', 'two': 'file:%s' % filename}
            config.load_config(cfg_in)
            self.assertTrue(config['some.stuff'])
            self.assertEquals(config['other.thing'], 'ok')
        finally:
            os.remove(filename)

    def test_config_merge(self):
        config = Config(cfgfile=self.file_four)
        global_ = {'foo': 'bar', 'baz': 'bawlp'}
        self.assertEqual(config.get_section(''), dict())
        self.assertEqual(config.get_section('global'), global_)

        self.assertEqual(config['auth.a'], 'b')
        self.assertEqual(config['auth.c'], 'd')
        self.assertEqual(config.get_section('auth'),
                         {'a': 'b', 'c': 'd'})

        storage = {'e': 'f', 'g': 'h'}
        self.assertEqual(config['storage.e'], 'f')
        self.assertEqual(config['storage.g'], 'h')
        self.assertEqual(config.get_section('storage'),
                         storage)

        storage_once = {'i': 'j', 'k': 'l'}
        storage_once.update(storage)
        once_merged = config.merge('multi:once')
        self.assertEqual(once_merged.get_section('storage'),
                         storage_once)

        storage_thrice = {'i': 'jjj', 'k': 'lll'}
        storage_thrice.update(storage)
        thrice_merged = config.merge('multi:thrice')
        self.assertEqual(thrice_merged.get_section('storage'),
                         storage_thrice)

        # merge cache should guarantee same result
        config['storage.m'] = 'n'
        config['multi:thrice.storage.o'] = 'ppp'
        thrice_merged = config.merge('multi:thrice')
        self.assertEqual(thrice_merged.get_section('storage'),
                         storage_thrice)

        # but not after merge cache is cleared
        config.clear_merge_cache()
        thrice_merged = config.merge('multi:thrice')
        self.assertNotEqual(thrice_merged.get_section('storage'),
                            storage_thrice)
        storage_thrice.update(dict(m='n', o='ppp'))
        self.assertEqual(thrice_merged.get_section('storage'),
                         storage_thrice)
