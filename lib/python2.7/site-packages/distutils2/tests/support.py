"""Support code for distutils2 test cases.

Four helper classes are provided: LoggingCatcher, TempdirManager,
EnvironGuard and WarningsCatcher. They are written to be used as mixins,
e.g. ::

    from distutils2.tests import unittest
    from distutils2.tests.support import LoggingCatcher

    class SomeTestCase(LoggingCatcher, unittest.TestCase):

If you need to define a setUp method on your test class, you have to
call the mixin class' setUp method or it won't work (same thing for
tearDown):

        def setUp(self):
            super(SomeTestCase, self).setUp()
            ... # other setup code

Read each class' docstring to see its purpose and usage.

Also provided is a DummyCommand class, useful to mock commands in the
tests of another command that needs them (see docstring).
"""

import os
import shutil
import tempfile
import warnings
from copy import deepcopy

from distutils2 import log
from distutils2.dist import Distribution
from distutils2.log import DEBUG, INFO, WARN, ERROR, FATAL
from distutils2.tests import unittest

__all__ = ['LoggingCatcher', 'WarningsCatcher', 'TempdirManager',
           'EnvironGuard', 'DummyCommand', 'unittest']


class LoggingCatcher(object):
    """TestCase-compatible mixin to catch logging calls.

    Every log message that goes through distutils2.log will get appended to
    self.logs instead of being printed. You can check that your code logs
    warnings and errors as documented by inspecting that list; helper methods
    get_logs and clear_logs are also provided.
    """

    def setUp(self):
        super(LoggingCatcher, self).setUp()
        self.threshold = log.set_threshold(FATAL)
        # when log is replaced by logging we won't need
        # such monkey-patching anymore
        self._old_log = log.Log._log
        log.Log._log = self._log
        self.logs = []

    def tearDown(self):
        log.set_threshold(self.threshold)
        log.Log._log = self._old_log
        super(LoggingCatcher, self).tearDown()

    def _log(self, level, msg, args):
        if level not in (DEBUG, INFO, WARN, ERROR, FATAL):
            raise ValueError('%s wrong log level' % level)
        self.logs.append((level, msg, args))

    def get_logs(self, *levels):
        """Return a list of caught messages with level in `levels`.

        Example: self.get_logs(log.WARN, log.DEBUG) -> list
        """
        def _format(msg, args):
            if len(args) == 0:
                return msg
            return msg % args
        return [_format(msg, args) for level, msg, args
                in self.logs if level in levels]

    def clear_logs(self):
        """Empty the internal list of caught messages."""
        del self.logs[:]


class LoggingSilencer(object):
    "Class that raises an exception to make sure the renaming is noticed."

    def __init__(self, *args):
        raise DeprecationWarning("LoggingSilencer renamed to LoggingCatcher")


class WarningsCatcher(object):

    def setUp(self):
        self._orig_showwarning = warnings.showwarning
        warnings.showwarning = self._record_showwarning
        self.warnings = []

    def _record_showwarning(self, message, category, filename, lineno,
                            file=None, line=None):
        self.warnings.append({"message": message, "category": category,
                              "filename": filename, "lineno": lineno,
                              "file": file, "line": line})

    def tearDown(self):
        warnings.showwarning = self._orig_showwarning


class TempdirManager(object):
    """TestCase-compatible mixin to create temporary directories and files.

    Directories and files created in a test_* method will be removed after it
    has run.
    """

    def setUp(self):
        super(TempdirManager, self).setUp()
        self._basetempdir = tempfile.mkdtemp()

    def tearDown(self):
        super(TempdirManager, self).tearDown()
        shutil.rmtree(self._basetempdir, os.name in ('nt', 'cygwin'))

    def mktempfile(self):
        """Create a read-write temporary file and return it."""
        fd, fn = tempfile.mkstemp(dir=self._basetempdir)
        os.close(fd)
        return open(fn, 'w+')

    def mkdtemp(self):
        """Create a temporary directory and return its path."""
        d = tempfile.mkdtemp(dir=self._basetempdir)
        return d

    def write_file(self, path, content='xxx'):
        """Write a file at the given path.

        path can be a string, a tuple or a list; if it's a tuple or list,
        os.path.join will be used to produce a path.
        """
        if isinstance(path, (list, tuple)):
            path = os.path.join(*path)
        f = open(path, 'w')
        try:
            f.write(content)
        finally:
            f.close()

    def create_dist(self, pkg_name='foo', **kw):
        """Create a stub distribution object and files.

        This function creates a Distribution instance (use keyword arguments
        to customize it) and a temporary directory with a project structure
        (currently an empty directory).

        It returns the path to the directory and the Distribution instance.
        You can use TempdirManager.write_file to write any file in that
        directory, e.g. setup scripts or Python modules.
        """
        # Late import so that third parties can import support without
        # loading a ton of distutils2 modules in memory.
        from distutils2.dist import Distribution
        tmp_dir = self.mkdtemp()
        pkg_dir = os.path.join(tmp_dir, pkg_name)
        os.mkdir(pkg_dir)
        dist = Distribution(attrs=kw)
        return pkg_dir, dist


class EnvironGuard(object):
    """TestCase-compatible mixin to save and restore the environment."""

    def setUp(self):
        super(EnvironGuard, self).setUp()
        self.old_environ = deepcopy(os.environ)

    def tearDown(self):
        for key, value in self.old_environ.iteritems():
            if os.environ.get(key) != value:
                os.environ[key] = value

        for key in os.environ.keys():
            if key not in self.old_environ:
                del os.environ[key]

        super(EnvironGuard, self).tearDown()


class DummyCommand(object):
    """Class to store options for retrieval via set_undefined_options().

    Useful for mocking one dependency command in the tests for another
    command, see e.g. the dummy build command in test_build_scripts.
    """

    def __init__(self, **kwargs):
        for kw, val in kwargs.iteritems():
            setattr(self, kw, val)

    def ensure_finalized(self):
        pass


class TestDistribution(Distribution):
    """Distribution subclasses that avoids the default search for
    configuration files.

    The ._config_files attribute must be set before
    .parse_config_files() is called.
    """

    def find_config_files(self):
        return self._config_files


def create_distribution(configfiles=()):
    """Prepares a distribution with given config files parsed."""
    d = TestDistribution()
    d.config.find_config_files = d.find_config_files
    d._config_files = configfiles
    d.parse_config_files()
    d.parse_command_line()
    return d

