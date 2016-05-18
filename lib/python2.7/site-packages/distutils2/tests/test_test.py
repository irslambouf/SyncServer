import os
import re
import sys
import shutil
import unittest as ut1

from copy import copy
from os.path import join
from operator import getitem, setitem, delitem
from StringIO import StringIO
from distutils2.core import Command
from distutils2.tests import unittest
from distutils2.tests.support import TempdirManager, LoggingCatcher
from distutils2.command.test import test
from distutils2.dist import Distribution
from distutils2._backport import pkgutil

try:
    any
except NameError:
    from distutils2._backport import any

EXPECTED_OUTPUT_RE = r'''FAIL: test_blah \(myowntestmodule.SomeTest\)
----------------------------------------------------------------------
Traceback \(most recent call last\):
  File ".+/myowntestmodule.py", line \d+, in test_blah
    self.fail\("horribly"\)
AssertionError: horribly
'''

here = os.path.dirname(os.path.abspath(__file__))

class TestTest(TempdirManager,
               LoggingCatcher,
               unittest.TestCase):

    def setUp(self):
        super(TestTest, self).setUp()

        distutils2path = os.path.dirname(os.path.dirname(here))
        self.old_pythonpath = os.environ.get('PYTHONPATH', '')
        os.environ['PYTHONPATH'] = distutils2path + os.pathsep + self.old_pythonpath

    def tearDown(self):
        pkgutil.clear_cache()
        os.environ['PYTHONPATH'] = self.old_pythonpath
        super(TestTest, self).tearDown()

    def assert_re_match(self, pattern, string):
        def quote(s):
            lines = ['## ' + line for line in s.split('\n')]
            sep = ["#" * 60]
            return [''] + sep + lines + sep
        msg = quote(pattern) + ["didn't match"] + quote(string)
        msg = "\n".join(msg)
        if not re.search(pattern, string):
            self.fail(msg)

    def prepare_dist(self, dist_name):
        pkg_dir = join(os.path.dirname(__file__), "dists", dist_name)
        temp_pkg_dir = join(self.mkdtemp(), dist_name)
        shutil.copytree(pkg_dir, temp_pkg_dir)
        return temp_pkg_dir

    def safely_replace(self, obj, attr, new_val=None, delete=False, dictionary=False):
        """Replace a object's attribute returning to its original state at the
        end of the test run. Creates the attribute if not present before
        (deleting afterwards). When delete=True, makes sure the value is del'd
        for the test run. If dictionary is set to True, operates of its items
        rather than attributes."""
        if dictionary:
            _setattr, _getattr, _delattr = setitem, getitem, delitem
            def _hasattr(_dict, value):
                return value in _dict
        else:
            _setattr, _getattr, _delattr, _hasattr = setattr, getattr, delattr, hasattr

        orig_has_attr = _hasattr(obj, attr)
        if orig_has_attr:
            orig_val = _getattr(obj, attr)

        if delete is False:
            _setattr(obj, attr, new_val)
        elif orig_has_attr:
            _delattr(obj, attr)

        def do_cleanup():
            if orig_has_attr:
                _setattr(obj, attr, orig_val)
            elif _hasattr(obj, attr):
                _delattr(obj, attr)

        self.addCleanup(do_cleanup)

    def test_runs_unittest(self):
        module_name, a_module = self.prepare_a_module()
        record = []
        a_module.recorder = lambda *args: record.append("suite")

        class MockTextTestRunner(object):
            def __init__(*_, **__): pass
            def run(_self, suite):
                record.append("run")
        self.safely_replace(ut1, "TextTestRunner", MockTextTestRunner)

        dist = Distribution()
        cmd = test(dist)
        cmd.suite = "%s.recorder" % module_name
        cmd.run()
        self.assertEqual(record, ["suite", "run"])

    def test_builds_before_running_tests(self):
        dist = Distribution()
        cmd = test(dist)
        cmd.runner = self.prepare_named_function(lambda: None)
        record = []
        class MockBuildCmd(Command):
            build_lib = "mock build lib"
            def initialize_options(self): pass
            def finalize_options(self): pass
            def run(self): record.append("build run")
        dist.cmdclass['build'] = MockBuildCmd

        cmd.ensure_finalized()
        cmd.run()
        self.assertEqual(record, ['build run'])

    def _test_works_with_2to3(self):
        pass

    def test_checks_requires(self):
        dist = Distribution()
        cmd = test(dist)
        phony_project = 'ohno_ohno-impossible_1234-name_stop-that!'
        cmd.tests_require = [phony_project]
        record = []
        cmd.announce = lambda *args: record.append(args)
        cmd.ensure_finalized()
        self.assertEqual(1, len(record))
        self.assertIn(phony_project, record[0][0])

    def prepare_a_module(self):
        tmp_dir = self.mkdtemp()
        sys.path.append(tmp_dir)
        self.addCleanup(lambda: sys.path.remove(tmp_dir))

        self.write_file((tmp_dir, 'distutils2_tests_a.py'), '')
        import distutils2_tests_a as a_module
        return "distutils2_tests_a", a_module

    def prepare_named_function(self, func):
        module_name, a_module = self.prepare_a_module()
        a_module.recorder = func
        return "%s.recorder" % module_name

    def test_custom_runner(self):
        dist = Distribution()
        cmd = test(dist)

        record = []
        cmd.runner = self.prepare_named_function(lambda: record.append("runner called"))
        cmd.ensure_finalized()
        cmd.run()
        self.assertEqual(["runner called"], record)

    def prepare_mock_ut2(self):
        class MockUTClass(object):
            def __init__(*_, **__): pass
            def discover(self): pass
            def run(self, _): pass
        class MockUTModule(object):
            TestLoader = MockUTClass
            TextTestRunner = MockUTClass
        mock_ut2 = MockUTModule()
        self.safely_replace(sys.modules, "unittest2", mock_ut2, dictionary=True)
        return mock_ut2

    def test_gets_unittest_discovery(self):
        mock_ut2 = self.prepare_mock_ut2()
        dist = Distribution()
        cmd = test(dist)
        self.safely_replace(ut1.TestLoader, "discover", lambda: None)
        self.assertEqual(cmd.get_ut_with_discovery(), ut1)

        del ut1.TestLoader.discover
        self.assertEqual(cmd.get_ut_with_discovery(), mock_ut2)

    def test_calls_discover(self):
        self.safely_replace(ut1.TestLoader, "discover", delete=True)
        mock_ut2 = self.prepare_mock_ut2()
        record = []
        mock_ut2.TestLoader.discover = lambda self, path: record.append(path)
        dist = Distribution()
        cmd = test(dist)
        cmd.run()
        self.assertEqual(record, [os.curdir])

def test_suite():
    return unittest.makeSuite(TestTest)

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
