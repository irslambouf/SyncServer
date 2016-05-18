"""Tests for distutils.manifest."""
import os
import sys
import logging

from distutils2.tests import run_unittest
from distutils2.tests import unittest, support
from distutils2.manifest import Manifest

_MANIFEST = """\
recursive-include foo *.py   # ok
# nothing here

#

recursive-include bar \\
  *.dat   *.txt
"""

class ManifestTestCase(support.TempdirManager,
                       unittest.TestCase):

    def test_manifest_reader(self):

        tmpdir = self.mkdtemp()
        MANIFEST = os.path.join(tmpdir, 'MANIFEST.in')
        f = open(MANIFEST, 'w')
        try:
            f.write(_MANIFEST)
        finally:
            f.close()
        manifest = Manifest()

        warns = []
        def _warn(msg):
            warns.append(msg)

        old_warn = logging.warning
        logging.warning = _warn
        try:
            manifest.read_template(MANIFEST)
        finally:
            logging.warning = old_warn

        # the manifest should have been read
        # and 3 warnings issued (we ddidn't provided the files)
        self.assertEqual(len(warns), 3)
        for warn in warns:
            self.assertIn('warning: no files found matching', warn)



def test_suite():
    return unittest.makeSuite(ManifestTestCase)

if __name__ == '__main__':
    run_unittest(test_suite())
