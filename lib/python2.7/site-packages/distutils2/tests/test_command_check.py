"""Tests for distutils.command.check."""

from distutils2.command.check import check
from distutils2.metadata import _HAS_DOCUTILS
from distutils2.tests import unittest, support
from distutils2.errors import DistutilsSetupError

class CheckTestCase(support.LoggingCatcher,
                    support.TempdirManager,
                    unittest.TestCase):

    def _run(self, metadata=None, **options):
        if metadata is None:
            metadata = {}
        pkg_info, dist = self.create_dist(**metadata)
        cmd = check(dist)
        cmd.initialize_options()
        for name, value in options.items():
            setattr(cmd, name, value)
        cmd.ensure_finalized()
        cmd.run()
        return cmd

    def test_check_metadata(self):
        # let's run the command with no metadata at all
        # by default, check is checking the metadata
        # should have some warnings
        cmd = self._run()
        self.assertTrue(len(cmd._warnings) > 0)

        # now let's add the required fields
        # and run it again, to make sure we don't get
        # any warning anymore
        metadata = {'home_page': 'xxx', 'author': 'xxx',
                    'author_email': 'xxx',
                    'name': 'xxx', 'version': 'xxx'
                    }
        cmd = self._run(metadata)
        self.assertEqual(len(cmd._warnings), 0)

        # now with the strict mode, we should
        # get an error if there are missing metadata
        self.assertRaises(DistutilsSetupError, self._run, {}, **{'strict': 1})

        # and of course, no error when all metadata fields are present
        cmd = self._run(metadata, strict=1)
        self.assertEqual(len(cmd._warnings), 0)

    @unittest.skipUnless(_HAS_DOCUTILS, "requires docutils")
    def test_check_restructuredtext(self):
        # let's see if it detects broken rest in long_description
        broken_rest = 'title\n===\n\ntest'
        pkg_info, dist = self.create_dist(description=broken_rest)
        cmd = check(dist)
        cmd.check_restructuredtext()
        self.assertEqual(len(cmd._warnings), 1)

        pkg_info, dist = self.create_dist(description='title\n=====\n\ntest')
        cmd = check(dist)
        cmd.check_restructuredtext()
        self.assertEqual(len(cmd._warnings), 0)

    def test_check_all(self):

        metadata = {'home_page': 'xxx', 'author': 'xxx'}
        self.assertRaises(DistutilsSetupError, self._run,
                          {}, **{'strict': 1,
                                 'all': 1})

    def test_check_hooks(self):
        pkg_info, dist = self.create_dist()
        dist.command_options['install'] = {
            'pre_hook': ('file', {"a": 'some.nonextistant.hook.ghrrraarrhll'}),
        }
        cmd = check(dist)
        cmd.check_hooks_resolvable()
        self.assertEqual(len(cmd._warnings), 1)
        

def test_suite():
    return unittest.makeSuite(CheckTestCase)

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
