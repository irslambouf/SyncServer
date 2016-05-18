# -*- coding: utf-8 -*-

"""Tests for distutils2.dist."""
import os
import StringIO
import sys
import textwrap

import distutils2.dist
from distutils2.dist import Distribution, fix_help_options
from distutils2.command.cmd import Command
from distutils2.errors import DistutilsModuleError, DistutilsOptionError
from distutils2.tests import TESTFN, captured_stdout
from distutils2.tests import support, unittest
from distutils2.tests.support import create_distribution


class test_dist(Command):
    """Sample distutils2 extension command."""

    user_options = [
        ("sample-option=", "S", "help text"),
        ]

    def initialize_options(self):
        self.sample_option = None

    def finalize_options(self):
        pass


class DistributionTestCase(support.TempdirManager,
                           support.LoggingCatcher,
                           support.WarningsCatcher,
                           support.EnvironGuard,
                           unittest.TestCase):

    def setUp(self):
        super(DistributionTestCase, self).setUp()
        self.argv = sys.argv, sys.argv[:]
        del sys.argv[1:]

    def tearDown(self):
        sys.argv = self.argv[0]
        sys.argv[:] = self.argv[1]
        super(DistributionTestCase, self).tearDown()

    def test_debug_mode(self):
        self.addCleanup(os.unlink, TESTFN)
        f = open(TESTFN, "w")
        try:
            f.write("[global]\n")
            f.write("command_packages = foo.bar, splat")
        finally:
            f.close()

        files = [TESTFN]
        sys.argv.append("build")

        __, stdout = captured_stdout(create_distribution, files)
        self.assertEqual(stdout, '')
        distutils2.dist.DEBUG = True
        try:
            __, stdout = captured_stdout(create_distribution, files)
            self.assertEqual(stdout, '')
        finally:
            distutils2.dist.DEBUG = False

    def test_command_packages_unspecified(self):
        sys.argv.append("build")
        d = create_distribution()
        self.assertEqual(d.get_command_packages(), ["distutils2.command"])

    def test_command_packages_cmdline(self):
        from distutils2.tests.test_dist import test_dist
        sys.argv.extend(["--command-packages",
                         "foo.bar,distutils2.tests",
                         "test_dist",
                         "-Ssometext",
                         ])
        d = create_distribution()
        # let's actually try to load our test command:
        self.assertEqual(d.get_command_packages(),
                         ["distutils2.command", "foo.bar", "distutils2.tests"])
        cmd = d.get_command_obj("test_dist")
        self.assertTrue(isinstance(cmd, test_dist))
        self.assertEqual(cmd.sample_option, "sometext")

    def test_command_packages_configfile(self):
        sys.argv.append("build")
        f = open(TESTFN, "w")
        try:
            print >> f, "[global]"
            print >> f, "command_packages = foo.bar, splat"
            f.close()
            d = create_distribution([TESTFN])
            self.assertEqual(d.get_command_packages(),
                             ["distutils2.command", "foo.bar", "splat"])

            # ensure command line overrides config:
            sys.argv[1:] = ["--command-packages", "spork", "build"]
            d = create_distribution([TESTFN])
            self.assertEqual(d.get_command_packages(),
                             ["distutils2.command", "spork"])

            # Setting --command-packages to '' should cause the default to
            # be used even if a config file specified something else:
            sys.argv[1:] = ["--command-packages", "", "build"]
            d = create_distribution([TESTFN])
            self.assertEqual(d.get_command_packages(), ["distutils2.command"])

        finally:
            os.unlink(TESTFN)

    def test_write_pkg_file(self):
        # Check DistributionMetadata handling of Unicode fields
        tmp_dir = self.mkdtemp()
        my_file = os.path.join(tmp_dir, 'f')
        cls = Distribution

        dist = cls(attrs={'author': u'Mister Café',
                          'name': 'my.package',
                          'maintainer': u'Café Junior',
                          'summary': u'Café torréfié',
                          'description': u'Héhéhé'})

        # let's make sure the file can be written
        # with Unicode fields. they are encoded with
        # PKG_INFO_ENCODING
        dist.metadata.write_file(open(my_file, 'w'))

        # regular ascii is of course always usable
        dist = cls(attrs={'author': 'Mister Cafe',
                          'name': 'my.package',
                          'maintainer': 'Cafe Junior',
                          'summary': 'Cafe torrefie',
                          'description': 'Hehehe'})

        dist.metadata.write_file(open(my_file, 'w'))

    def test_bad_attr(self):
        Distribution(attrs={'author': 'xxx',
                            'name': 'xxx',
                            'version': 'xxx',
                            'url': 'xxxx',
                            'badoptname': 'xxx'})

        self.assertEqual(len(self.warnings), 1)
        self.assertIn("Unknown distribution",
                      self.warnings[0]['message'].args[0])

    def test_empty_options(self):
        # an empty options dictionary should not stay in the
        # list of attributes
        Distribution(attrs={'author': 'xxx',
                            'name': 'xxx',
                            'version': 'xxx',
                            'url': 'xxxx',
                            'options': {}})

        self.assertEqual(len(self.warnings), 0)

    def test_non_empty_options(self):
        # TODO: how to actually use options is not documented except
        # for a few cryptic comments in dist.py.  If this is to stay
        # in the public API, it deserves some better documentation.

        # Here is an example of how it's used out there:
        # http://svn.pythonmac.org/py2app/py2app/trunk/doc/
        # index.html#specifying-customizations
        dist = Distribution(attrs={'author': 'xxx',
                                   'name': 'xxx',
                                   'version': 'xxx',
                                   'url': 'xxxx',
                                   'options': {'sdist': {'owner': 'root'}}})

        self.assertIn('owner', dist.get_option_dict('sdist'))

    def test_finalize_options(self):

        attrs = {'keywords': 'one,two',
                 'platform': 'one,two'}

        dist = Distribution(attrs=attrs)
        dist.finalize_options()

        # finalize_option splits platforms and keywords
        self.assertEqual(dist.metadata['platform'], ['one', 'two'])
        self.assertEqual(dist.metadata['keywords'], ['one', 'two'])

    def test_get_command_packages(self):
        dist = Distribution()
        self.assertEqual(dist.command_packages, None)
        cmds = dist.get_command_packages()
        self.assertEqual(cmds, ['distutils2.command'])
        self.assertEqual(dist.command_packages,
                          ['distutils2.command'])

        dist.command_packages = 'one,two'
        cmds = dist.get_command_packages()
        self.assertEqual(cmds, ['distutils2.command', 'one', 'two'])

    def test_announce(self):
        # make sure the level is known
        dist = Distribution()
        args = ('ok',)
        kwargs = {'level': 'ok2'}
        self.assertRaises(ValueError, dist.announce, args, kwargs)

    def test_find_config_files_disable(self):
        # Bug #1180: Allow users to disable their own config file.
        temp_home = self.mkdtemp()
        if os.name == 'posix':
            user_filename = os.path.join(temp_home, ".pydistutils.cfg")
        else:
            user_filename = os.path.join(temp_home, "pydistutils.cfg")

        f = open(user_filename, 'w')
        try:
            f.write('[distutils2]\n')
        finally:
            f.close()

        def _expander(path):
            return temp_home

        old_expander = os.path.expanduser
        os.path.expanduser = _expander
        try:
            d = distutils2.dist.Distribution()
            all_files = d.find_config_files()

            d = distutils2.dist.Distribution(attrs={'script_args':
                                            ['--no-user-cfg']})
            files = d.find_config_files()
        finally:
            os.path.expanduser = old_expander

        # make sure --no-user-cfg disables the user cfg file
        self.assertEqual(len(all_files) - 1, len(files))

    def test_special_hooks_parsing(self):
        temp_home = self.mkdtemp()
        config_files = [os.path.join(temp_home, "config1.cfg"),
                        os.path.join(temp_home, "config2.cfg")]

        # Store two aliased hooks in config files
        self.write_file((temp_home, "config1.cfg"),
                        '[test_dist]\npre-hook.a = type')
        self.write_file((temp_home, "config2.cfg"),
                        '[test_dist]\npre-hook.b = type')

        sys.argv.extend(["--command-packages",
                         "distutils2.tests",
                         "test_dist"])
        dist = create_distribution(config_files)
        cmd = dist.get_command_obj("test_dist")

        self.assertEqual(cmd.pre_hook, {"a": 'type', "b": 'type'})

    def test_hooks_get_run(self):
        temp_home = self.mkdtemp()
        config_file = os.path.join(temp_home, "config1.cfg")
        hooks_module = os.path.join(temp_home, "testhooks.py")

        self.write_file(config_file, textwrap.dedent('''
            [test_dist]
            pre-hook.test = testhooks.log_pre_call
            post-hook.test = testhooks.log_post_call'''))

        self.write_file(hooks_module, textwrap.dedent('''
        record = []

        def log_pre_call(cmd):
            record.append('pre-%s' % cmd.get_command_name())

        def log_post_call(cmd):
            record.append('post-%s' % cmd.get_command_name())
        '''))

        sys.argv.extend(["--command-packages",
                         "distutils2.tests",
                         "test_dist"])

        d = create_distribution([config_file])
        cmd = d.get_command_obj("test_dist")

        # prepare the call recorders
        sys.path.append(temp_home)
        from testhooks import record

        self.addCleanup(setattr, cmd, 'run', cmd.run)
        self.addCleanup(setattr, cmd, 'finalize_options',
                        cmd.finalize_options)

        cmd.run = lambda: record.append('run')
        cmd.finalize_options = lambda: record.append('finalize')

        d.run_command('test_dist')

        self.assertEqual(record, ['finalize',
                                  'pre-test_dist',
                                  'run',
                                  'post-test_dist'])

    def test_hooks_importable(self):
        temp_home = self.mkdtemp()
        config_file = os.path.join(temp_home, "config1.cfg")

        self.write_file(config_file, textwrap.dedent('''
            [test_dist]
            pre-hook.test = nonexistent.dotted.name'''))

        sys.argv.extend(["--command-packages",
                         "distutils2.tests",
                         "test_dist"])

        d = create_distribution([config_file])
        cmd = d.get_command_obj("test_dist")
        cmd.ensure_finalized()

        self.assertRaises(DistutilsModuleError, d.run_command, 'test_dist')

    def test_hooks_callable(self):
        temp_home = self.mkdtemp()
        config_file = os.path.join(temp_home, "config1.cfg")

        self.write_file(config_file, textwrap.dedent('''
            [test_dist]
            pre-hook.test = distutils2.tests.test_dist.__doc__'''))

        sys.argv.extend(["--command-packages",
                         "distutils2.tests",
                         "test_dist"])

        d = create_distribution([config_file])
        cmd = d.get_command_obj("test_dist")
        cmd.ensure_finalized()

        self.assertRaises(DistutilsOptionError, d.run_command, 'test_dist')


class MetadataTestCase(support.TempdirManager, support.EnvironGuard,
                       support.LoggingCatcher, unittest.TestCase):

    def setUp(self):
        super(MetadataTestCase, self).setUp()
        self.argv = sys.argv, sys.argv[:]

    def tearDown(self):
        sys.argv = self.argv[0]
        sys.argv[:] = self.argv[1]
        super(MetadataTestCase, self).tearDown()

    def test_simple_metadata(self):
        attrs = {"name": "package",
                 "version": "1.0"}
        dist = Distribution(attrs)
        meta = self.format_metadata(dist)
        self.assertTrue("Metadata-Version: 1.0" in meta)
        self.assertTrue("provides:" not in meta.lower())
        self.assertTrue("requires:" not in meta.lower())
        self.assertTrue("obsoletes:" not in meta.lower())

    def test_provides_dist(self):
        attrs = {"name": "package",
                 "version": "1.0",
                 "provides_dist": ["package", "package.sub"]}
        dist = Distribution(attrs)
        self.assertEqual(dist.metadata['Provides-Dist'],
                         ["package", "package.sub"])
        meta = self.format_metadata(dist)
        self.assertTrue("Metadata-Version: 1.2" in meta)
        self.assertTrue("requires:" not in meta.lower())
        self.assertTrue("obsoletes:" not in meta.lower())

    def _test_provides_illegal(self):
        # XXX to do: check the versions
        self.assertRaises(ValueError, Distribution,
                          {"name": "package",
                           "version": "1.0",
                           "provides_dist": ["my.pkg (splat)"]})

    def test_requires_dist(self):
        attrs = {"name": "package",
                 "version": "1.0",
                 "requires_dist": ["other", "another (==1.0)"]}
        dist = Distribution(attrs)
        self.assertEqual(dist.metadata['Requires-Dist'],
                         ["other", "another (==1.0)"])
        meta = self.format_metadata(dist)
        self.assertTrue("Metadata-Version: 1.2" in meta)
        self.assertTrue("provides:" not in meta.lower())
        self.assertTrue("Requires-Dist: other" in meta)
        self.assertTrue("Requires-Dist: another (==1.0)" in meta)
        self.assertTrue("obsoletes:" not in meta.lower())

    def _test_requires_illegal(self):
        # XXX
        self.assertRaises(ValueError, Distribution,
                          {"name": "package",
                           "version": "1.0",
                           "requires": ["my.pkg (splat)"]})

    def test_obsoletes_dist(self):
        attrs = {"name": "package",
                 "version": "1.0",
                 "obsoletes_dist": ["other", "another (<1.0)"]}
        dist = Distribution(attrs)
        self.assertEqual(dist.metadata['Obsoletes-Dist'],
                         ["other", "another (<1.0)"])
        meta = self.format_metadata(dist)
        self.assertTrue("Metadata-Version: 1.2" in meta)
        self.assertTrue("provides:" not in meta.lower())
        self.assertTrue("requires:" not in meta.lower())
        self.assertTrue("Obsoletes-Dist: other" in meta)
        self.assertTrue("Obsoletes-Dist: another (<1.0)" in meta)

    def _test_obsoletes_illegal(self):
        # XXX
        self.assertRaises(ValueError, Distribution,
                          {"name": "package",
                           "version": "1.0",
                           "obsoletes": ["my.pkg (splat)"]})

    def format_metadata(self, dist):
        sio = StringIO.StringIO()
        dist.metadata.write_file(sio)
        return sio.getvalue()

    def test_custom_pydistutils(self):
        # fixes #2166
        # make sure pydistutils.cfg is found
        if os.name == 'posix':
            user_filename = ".pydistutils.cfg"
        else:
            user_filename = "pydistutils.cfg"

        temp_dir = self.mkdtemp()
        user_filename = os.path.join(temp_dir, user_filename)
        f = open(user_filename, 'w')
        try:
            f.write('.')
        finally:
            f.close()

        try:
            dist = Distribution()

            # linux-style
            if sys.platform in ('linux', 'darwin'):
                os.environ['HOME'] = temp_dir
                files = dist.find_config_files()
                self.assertTrue(user_filename in files)

            # win32-style
            if sys.platform == 'win32':
                # home drive should be found
                os.environ['HOME'] = temp_dir
                files = dist.find_config_files()
                self.assertTrue(user_filename in files,
                             '%r not found in %r' % (user_filename, files))
        finally:
            os.remove(user_filename)

    def test_fix_help_options(self):
        help_tuples = [('a', 'b', 'c', 'd'), (1, 2, 3, 4)]
        fancy_options = fix_help_options(help_tuples)
        self.assertEqual(fancy_options[0], ('a', 'b', 'c'))
        self.assertEqual(fancy_options[1], (1, 2, 3))

    def test_show_help(self):
        # smoke test, just makes sure some help is displayed
        dist = Distribution()
        sys.argv = []
        dist.help = 1
        dist.script_name = 'setup.py'
        __, stdout = captured_stdout(dist.parse_command_line)
        output = [line for line in stdout.split('\n')
                  if line.strip() != '']
        self.assertTrue(len(output) > 0)

    def test_description(self):
        desc = textwrap.dedent("""\
        example::
              We start here
            and continue here
          and end here.""")
        attrs = {"name": "package",
                 "version": "1.0",
                 "description": desc}

        dist = distutils2.dist.Distribution(attrs)
        meta = self.format_metadata(dist)
        meta = meta.replace('\n' + 7 * ' ' + '|', '\n')
        self.assertTrue(desc in meta)

    def test_read_metadata(self):
        attrs = {"name": "package",
                 "version": "1.0",
                 "description": "desc",
                 "summary": "xxx",
                 "download_url": "http://example.com",
                 "keywords": ['one', 'two'],
                 "requires_dist": ['foo']}

        dist = Distribution(attrs)
        metadata = dist.metadata

        # write it then reloads it
        PKG_INFO = StringIO.StringIO()
        metadata.write_file(PKG_INFO)
        PKG_INFO.seek(0)

        metadata.read_file(PKG_INFO)
        self.assertEqual(metadata['name'], "package")
        self.assertEqual(metadata['version'], "1.0")
        self.assertEqual(metadata['summary'], "xxx")
        self.assertEqual(metadata['download_url'], 'http://example.com')
        self.assertEqual(metadata['keywords'], ['one', 'two'])
        self.assertEqual(metadata['platform'], [])
        self.assertEqual(metadata['obsoletes'], [])
        self.assertEqual(metadata['requires-dist'], ['foo'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DistributionTestCase))
    suite.addTest(unittest.makeSuite(MetadataTestCase))
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
