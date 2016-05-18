"""Tests for distutils.command.bdist."""

from distutils2.tests import run_unittest

from distutils2.command.bdist import bdist
from distutils2.tests import unittest, support

class BuildTestCase(support.TempdirManager,
                    unittest.TestCase):

    def test_formats(self):

        # let's create a command and make sure
        # we can fix the format
        pkg_pth, dist = self.create_dist()
        cmd = bdist(dist)
        cmd.formats = ['msi']
        cmd.ensure_finalized()
        self.assertEqual(cmd.formats, ['msi'])

        # what format bdist offers ?
        # XXX an explicit list in bdist is
        # not the best way to  bdist_* commands
        # we should add a registry
        formats = ['zip', 'gztar', 'bztar', 'ztar', 'tar', 'wininst', 'msi']
        formats.sort()
        found = cmd.format_command.keys()
        found.sort()
        self.assertEqual(found, formats)

def test_suite():
    return unittest.makeSuite(BuildTestCase)

if __name__ == '__main__':
    run_unittest(test_suite())
