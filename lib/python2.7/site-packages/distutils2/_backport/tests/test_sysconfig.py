"""Tests for sysconfig."""

import os
import sys
import subprocess
import shutil
from copy import copy, deepcopy
from ConfigParser import RawConfigParser
from StringIO import StringIO

from distutils2._backport import sysconfig
from distutils2._backport.sysconfig import (
        _expand_globals, _expand_vars, _get_default_scheme, _subst_vars,
        get_config_var, get_config_vars, get_path, get_paths, get_platform,
        get_scheme_names, _main, _SCHEMES)

from distutils2.tests import unittest
from distutils2.tests.support import EnvironGuard
from test.test_support import TESTFN, unlink
try:
    from test.test_support import skip_unless_symlink
except ImportError:
    skip_unless_symlink = unittest.skip(
        'requires test.test_support.skip_unless_symlink')

class TestSysConfig(EnvironGuard, unittest.TestCase):

    def setUp(self):
        super(TestSysConfig, self).setUp()
        self.sys_path = sys.path[:]
        self.makefile = None
        # patching os.uname
        if hasattr(os, 'uname'):
            self.uname = os.uname
            self._uname = os.uname()
        else:
            self.uname = None
            self._uname = None
        os.uname = self._get_uname
        # saving the environment
        self.name = os.name
        self.platform = sys.platform
        self.version = sys.version
        self.maxint = sys.maxint
        self.sep = os.sep
        self.join = os.path.join
        self.isabs = os.path.isabs
        self.splitdrive = os.path.splitdrive
        self._config_vars = copy(sysconfig._CONFIG_VARS)

    def tearDown(self):
        sys.path[:] = self.sys_path
        if self.makefile is not None:
            os.unlink(self.makefile)
        self._cleanup_testfn()
        if self.uname is not None:
            os.uname = self.uname
        else:
            del os.uname
        os.name = self.name
        sys.platform = self.platform
        sys.version = self.version
        sys.maxint = self.maxint
        os.sep = self.sep
        os.path.join = self.join
        os.path.isabs = self.isabs
        os.path.splitdrive = self.splitdrive
        sysconfig._CONFIG_VARS = copy(self._config_vars)
        super(TestSysConfig, self).tearDown()

    def _set_uname(self, uname):
        self._uname = uname

    def _get_uname(self):
        return self._uname

    def _cleanup_testfn(self):
        path = TESTFN
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)

    # TODO use a static list or remove the test
    #def test_get_path_names(self):
    #    self.assertEqual(get_path_names(), sysconfig._SCHEME_KEYS)

    def test_nested_var_substitution(self):
        # Assert that the {curly brace token} expansion pattern will replace
        # only the inner {something} on nested expressions like {py{something}} on
        # the first pass.

        # We have no plans to make use of this, but it keeps the option open for
        # the future, at the cost only of disallowing { itself as a piece of a
        # substitution key (which would be weird).
        self.assertEqual(_subst_vars('{py{version}}', {'version': '31'}), '{py31}')

    def test_get_paths(self):
        scheme = get_paths()
        default_scheme = _get_default_scheme()
        wanted = _expand_vars(default_scheme, None)
        wanted = sorted(wanted.items())
        scheme = sorted(scheme.items())
        self.assertEqual(scheme, wanted)

    def test_get_path(self):
        # xxx make real tests here
        for scheme in _SCHEMES.sections():
            for name, _ in _SCHEMES.items(scheme):
                get_path(name, scheme)

    def test_get_config_vars(self):
        cvars = get_config_vars()
        self.assertIsInstance(cvars, dict)
        self.assertTrue(cvars)

    def test_get_platform(self):
        # windows XP, 32bits
        os.name = 'nt'
        sys.version = ('2.4.4 (#71, Oct 18 2006, 08:34:43) '
                       '[MSC v.1310 32 bit (Intel)]')
        sys.platform = 'win32'
        self.assertEqual(get_platform(), 'win32')

        # windows XP, amd64
        os.name = 'nt'
        sys.version = ('2.4.4 (#71, Oct 18 2006, 08:34:43) '
                       '[MSC v.1310 32 bit (Amd64)]')
        sys.platform = 'win32'
        self.assertEqual(get_platform(), 'win-amd64')

        # windows XP, itanium
        os.name = 'nt'
        sys.version = ('2.4.4 (#71, Oct 18 2006, 08:34:43) '
                       '[MSC v.1310 32 bit (Itanium)]')
        sys.platform = 'win32'
        self.assertEqual(get_platform(), 'win-ia64')

        # macbook
        os.name = 'posix'
        sys.version = ('2.5 (r25:51918, Sep 19 2006, 08:49:13) '
                       '\n[GCC 4.0.1 (Apple Computer, Inc. build 5341)]')
        sys.platform = 'darwin'
        self._set_uname(('Darwin', 'macziade', '8.11.1',
                        ('Darwin Kernel Version 8.11.1: '
                         'Wed Oct 10 18:23:28 PDT 2007; '
                         'root:xnu-792.25.20~1/RELEASE_I386'), 'PowerPC'))
        os.environ['MACOSX_DEPLOYMENT_TARGET'] = '10.3'

        get_config_vars()['CFLAGS'] = ('-fno-strict-aliasing -DNDEBUG -g '
                                       '-fwrapv -O3 -Wall -Wstrict-prototypes')

        sys.maxint = 2147483647
        self.assertEqual(get_platform(), 'macosx-10.3-ppc')
        sys.maxint = 9223372036854775807
        self.assertEqual(get_platform(), 'macosx-10.3-ppc64')


        self._set_uname(('Darwin', 'macziade', '8.11.1',
                         ('Darwin Kernel Version 8.11.1: '
                          'Wed Oct 10 18:23:28 PDT 2007; '
                          'root:xnu-792.25.20~1/RELEASE_I386'), 'i386'))
        get_config_vars()['MACOSX_DEPLOYMENT_TARGET'] = '10.3'
        os.environ['MACOSX_DEPLOYMENT_TARGET'] = '10.3'

        get_config_vars()['CFLAGS'] = ('-fno-strict-aliasing -DNDEBUG -g '
                                       '-fwrapv -O3 -Wall -Wstrict-prototypes')

        sys.maxint = 2147483647
        self.assertEqual(get_platform(), 'macosx-10.3-i386')
        sys.maxint = 9223372036854775807
        self.assertEqual(get_platform(), 'macosx-10.3-x86_64')

        # macbook with fat binaries (fat, universal or fat64)
        os.environ['MACOSX_DEPLOYMENT_TARGET'] = '10.4'
        get_config_vars()['CFLAGS'] = ('-arch ppc -arch i386 -isysroot '
                                       '/Developer/SDKs/MacOSX10.4u.sdk  '
                                       '-fno-strict-aliasing -fno-common '
                                       '-dynamic -DNDEBUG -g -O3')

        self.assertEqual(get_platform(), 'macosx-10.4-fat')

        get_config_vars()['CFLAGS'] = ('-arch x86_64 -arch i386 -isysroot '
                                       '/Developer/SDKs/MacOSX10.4u.sdk  '
                                       '-fno-strict-aliasing -fno-common '
                                       '-dynamic -DNDEBUG -g -O3')

        self.assertEqual(get_platform(), 'macosx-10.4-intel')

        get_config_vars()['CFLAGS'] = ('-arch x86_64 -arch ppc -arch i386 -isysroot '
                                       '/Developer/SDKs/MacOSX10.4u.sdk  '
                                       '-fno-strict-aliasing -fno-common '
                                       '-dynamic -DNDEBUG -g -O3')
        self.assertEqual(get_platform(), 'macosx-10.4-fat3')

        get_config_vars()['CFLAGS'] = ('-arch ppc64 -arch x86_64 -arch ppc -arch i386 -isysroot '
                                       '/Developer/SDKs/MacOSX10.4u.sdk  '
                                       '-fno-strict-aliasing -fno-common '
                                       '-dynamic -DNDEBUG -g -O3')
        self.assertEqual(get_platform(), 'macosx-10.4-universal')

        get_config_vars()['CFLAGS'] = ('-arch x86_64 -arch ppc64 -isysroot '
                                       '/Developer/SDKs/MacOSX10.4u.sdk  '
                                       '-fno-strict-aliasing -fno-common '
                                       '-dynamic -DNDEBUG -g -O3')

        self.assertEqual(get_platform(), 'macosx-10.4-fat64')

        for arch in ('ppc', 'i386', 'x86_64', 'ppc64'):
            get_config_vars()['CFLAGS'] = ('-arch %s -isysroot '
                                           '/Developer/SDKs/MacOSX10.4u.sdk  '
                                           '-fno-strict-aliasing -fno-common '
                                           '-dynamic -DNDEBUG -g -O3'%(arch,))

            self.assertEqual(get_platform(), 'macosx-10.4-%s'%(arch,))

        # linux debian sarge
        os.name = 'posix'
        sys.version = ('2.3.5 (#1, Jul  4 2007, 17:28:59) '
                       '\n[GCC 4.1.2 20061115 (prerelease) (Debian 4.1.1-21)]')
        sys.platform = 'linux2'
        self._set_uname(('Linux', 'aglae', '2.6.21.1dedibox-r7',
                    '#1 Mon Apr 30 17:25:38 CEST 2007', 'i686'))

        self.assertEqual(get_platform(), 'linux-i686')

        # XXX more platforms to tests here

    def test_get_config_h_filename(self):
        config_h = sysconfig.get_config_h_filename()
        self.assertTrue(os.path.isfile(config_h), config_h)

    def test_get_scheme_names(self):
        wanted = ('nt', 'nt_user', 'os2', 'os2_home', 'osx_framework_user',
                  'posix_home', 'posix_prefix', 'posix_user')
        self.assertEqual(get_scheme_names(), wanted)

    @skip_unless_symlink
    def test_symlink(self):
        # On Windows, the EXE needs to know where pythonXY.dll is at so we have
        # to add the directory to the path.
        if sys.platform == 'win32':
            os.environ['Path'] = ';'.join((
                os.path.dirname(sys.executable), os.environ['Path']))

        # Issue 7880
        def get(python):
            cmd = [python, '-c',
                   'import sysconfig; print(sysconfig.get_platform())']
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=os.environ)
            return p.communicate()
        real = os.path.realpath(sys.executable)
        link = os.path.abspath(TESTFN)
        os.symlink(real, link)
        try:
            self.assertEqual(get(real), get(link))
        finally:
            unlink(link)

    @unittest.skipIf(sys.version < '2.6', 'requires Python 2.6 or higher')
    def test_user_similar(self):
        # Issue 8759 : make sure the posix scheme for the users
        # is similar to the global posix_prefix one
        base = get_config_var('base')
        user = get_config_var('userbase')
        for name in ('stdlib', 'platstdlib', 'purelib', 'platlib'):
            global_path = get_path(name, 'posix_prefix')
            user_path = get_path(name, 'posix_user')
            self.assertEqual(user_path, global_path.replace(base, user))

    def test_main(self):
        # just making sure _main() runs and returns things in the stdout
        self.addCleanup(setattr, sys, 'stdout', sys.stdout)
        sys.stdout = StringIO()
        _main()
        self.assertGreater(len(sys.stdout.getvalue().split('\n')), 0)

    @unittest.skipIf(sys.platform == 'win32', 'does not apply to Windows')
    def test_ldshared_value(self):
        ldflags = sysconfig.get_config_var('LDFLAGS')
        ldshared = sysconfig.get_config_var('LDSHARED')

        self.assertIn(ldflags, ldshared)

    def test_expand_globals(self):
        config = RawConfigParser()
        config.add_section('globals')
        config.set('globals', 'foo', 'ok')
        config.add_section('posix')
        config.set('posix', 'config', '/etc')
        config.set('posix', 'more', '{config}/ok')

        _expand_globals(config)

        self.assertEqual(config.get('posix', 'foo'), 'ok')
        self.assertEqual(config.get('posix', 'more'), '/etc/ok')

        # we might not have globals after all
        # extending again (==no more globals section)
        _expand_globals(config)

def test_suite():
    return unittest.makeSuite(TestSysConfig)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
