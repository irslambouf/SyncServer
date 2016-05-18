# -*- coding: utf-8 -*-
"""Tests for PEP 376 pkgutil functionality"""
import sys
import os
import csv
import imp
import tempfile
import shutil
import zipfile
try:
    from hashlib import md5
except ImportError:
    from distutils2._backport.hashlib import md5

from test.test_support import TESTFN
from distutils2.tests import unittest, run_unittest

from distutils2._backport import pkgutil

try:
    from os.path import relpath
except ImportError:
    try:
        from unittest.compatibility import relpath
    except ImportError:
        from unittest2.compatibility import relpath

# Adapted from Python 2.7's trunk

# TODO Add a test for getting a distribution that is provided by another
# distribution.

# TODO Add a test for absolute pathed RECORD items (e.g. /etc/myapp/config.ini)


class TestPkgUtilData(unittest.TestCase):

    def setUp(self):
        super(TestPkgUtilData, self).setUp()
        self.dirname = tempfile.mkdtemp()
        sys.path.insert(0, self.dirname)
        pkgutil.disable_cache()

    def tearDown(self):
        super(TestPkgUtilData, self).tearDown()
        del sys.path[0]
        pkgutil.enable_cache()
        shutil.rmtree(self.dirname)

    def test_getdata_filesys(self):
        pkg = 'test_getdata_filesys'

        # Include a LF and a CRLF, to test that binary data is read back
        RESOURCE_DATA = 'Hello, world!\nSecond line\r\nThird line'

        # Make a package with some resources
        package_dir = os.path.join(self.dirname, pkg)
        os.mkdir(package_dir)
        # Empty init.py
        f = open(os.path.join(package_dir, '__init__.py'), "wb")
        try:
            pass
        finally:
            f.close()
        # Resource files, res.txt, sub/res.txt
        f = open(os.path.join(package_dir, 'res.txt'), "wb")
        try:
            f.write(RESOURCE_DATA)
        finally:
            f.close()
        os.mkdir(os.path.join(package_dir, 'sub'))
        f = open(os.path.join(package_dir, 'sub', 'res.txt'), "wb")
        try:
            f.write(RESOURCE_DATA)
        finally:
            f.close()

        # Check we can read the resources
        res1 = pkgutil.get_data(pkg, 'res.txt')
        self.assertEqual(res1, RESOURCE_DATA)
        res2 = pkgutil.get_data(pkg, 'sub/res.txt')
        self.assertEqual(res2, RESOURCE_DATA)

        del sys.modules[pkg]

    def test_getdata_zipfile(self):
        zip = 'test_getdata_zipfile.zip'
        pkg = 'test_getdata_zipfile'

        # Include a LF and a CRLF, to test that binary data is read back
        RESOURCE_DATA = 'Hello, world!\nSecond line\r\nThird line'

        # Make a package with some resources
        zip_file = os.path.join(self.dirname, zip)
        z = zipfile.ZipFile(zip_file, 'w')
        try:
            # Empty init.py
            z.writestr(pkg + '/__init__.py', "")
            # Resource files, res.txt, sub/res.txt
            z.writestr(pkg + '/res.txt', RESOURCE_DATA)
            z.writestr(pkg + '/sub/res.txt', RESOURCE_DATA)
        finally:
            z.close()

        # Check we can read the resources
        sys.path.insert(0, zip_file)
        res1 = pkgutil.get_data(pkg, 'res.txt')
        self.assertEqual(res1, RESOURCE_DATA)
        res2 = pkgutil.get_data(pkg, 'sub/res.txt')
        self.assertEqual(res2, RESOURCE_DATA)
        del sys.path[0]

        del sys.modules[pkg]


# Adapted from Python 2.7's trunk


class TestPkgUtilPEP302(unittest.TestCase):

    class MyTestLoader(object):

        def load_module(self, fullname):
            # Create an empty module
            mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
            mod.__file__ = "<%s>" % self.__class__.__name__
            mod.__loader__ = self
            # Make it a package
            mod.__path__ = []
            # Count how many times the module is reloaded
            mod.__dict__['loads'] = mod.__dict__.get('loads', 0) + 1
            return mod

        def get_data(self, path):
            return "Hello, world!"

    class MyTestImporter(object):

        def find_module(self, fullname, path=None):
            return TestPkgUtilPEP302.MyTestLoader()

    def setUp(self):
        super(TestPkgUtilPEP302, self).setUp()
        pkgutil.disable_cache()
        sys.meta_path.insert(0, self.MyTestImporter())

    def tearDown(self):
        del sys.meta_path[0]
        pkgutil.enable_cache()
        super(TestPkgUtilPEP302, self).tearDown()

    def test_getdata_pep302(self):
        # Use a dummy importer/loader
        self.assertEqual(pkgutil.get_data('foo', 'dummy'), "Hello, world!")
        del sys.modules['foo']

    def test_alreadyloaded(self):
        # Ensure that get_data works without reloading - the "loads" module
        # variable in the example loader should count how many times a reload
        # occurs.
        import foo
        self.assertEqual(foo.loads, 1)
        self.assertEqual(pkgutil.get_data('foo', 'dummy'), "Hello, world!")
        self.assertEqual(foo.loads, 1)
        del sys.modules['foo']


class TestPkgUtilDistribution(unittest.TestCase):
    # Tests the pkgutil.Distribution class

    def setUp(self):
        super(TestPkgUtilDistribution, self).setUp()
        self.fake_dists_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'fake_dists'))
        pkgutil.disable_cache()

        self.distinfo_dirs = [os.path.join(self.fake_dists_path, dir)
            for dir in os.listdir(self.fake_dists_path)
            if dir.endswith('.dist-info')]

        def get_hexdigest(file):
            md5_hash = md5()
            md5_hash.update(open(file).read())
            return md5_hash.hexdigest()

        def record_pieces(file):
            path = relpath(file, sys.prefix)
            digest = get_hexdigest(file)
            size = os.path.getsize(file)
            return [path, digest, size]

        self.records = {}
        for distinfo_dir in self.distinfo_dirs:
            # Setup the RECORD file for this dist
            record_file = os.path.join(distinfo_dir, 'RECORD')
            record_writer = csv.writer(open(record_file, 'w'), delimiter=',',
                quoting=csv.QUOTE_NONE)
            dist_location = distinfo_dir.replace('.dist-info', '')

            for path, dirs, files in os.walk(dist_location):
                for f in files:
                    record_writer.writerow(record_pieces(
                                           os.path.join(path, f)))
            for file in ['INSTALLER', 'METADATA', 'REQUESTED']:
                record_writer.writerow(record_pieces(
                    os.path.join(distinfo_dir, file)))
            record_writer.writerow([relpath(record_file, sys.prefix)])
            del record_writer # causes the RECORD file to close
            record_reader = csv.reader(open(record_file, 'rb'))
            record_data = []
            for row in record_reader:
                path, md5_, size = row[:] + \
                                   [None for i in xrange(len(row), 3)]
                record_data.append([path, (md5_, size,)])
            self.records[distinfo_dir] = dict(record_data)

    def tearDown(self):
        self.records = None
        for distinfo_dir in self.distinfo_dirs:
            record_file = os.path.join(distinfo_dir, 'RECORD')
            open(record_file, 'w').close()
        pkgutil.enable_cache()
        super(TestPkgUtilDistribution, self).tearDown()

    def test_instantiation(self):
        # Test the Distribution class's instantiation provides us with usable
        # attributes.
        # Import the Distribution class
        from distutils2._backport.pkgutil import distinfo_dirname, Distribution

        here = os.path.abspath(os.path.dirname(__file__))
        name = 'choxie'
        version = '2.0.0.9'
        dist_path = os.path.join(here, 'fake_dists',
            distinfo_dirname(name, version))
        dist = Distribution(dist_path)

        self.assertEqual(dist.name, name)
        from distutils2.metadata import DistributionMetadata
        self.assertTrue(isinstance(dist.metadata, DistributionMetadata))
        self.assertEqual(dist.metadata['version'], version)
        self.assertTrue(isinstance(dist.requested, type(bool())))

    def test_installed_files(self):
        # Test the iteration of installed files.
        # Test the distribution's installed files
        from distutils2._backport.pkgutil import Distribution
        for distinfo_dir in self.distinfo_dirs:
            dist = Distribution(distinfo_dir)
            for path, md5_, size in dist.get_installed_files():
                record_data = self.records[dist.path]
                self.assertTrue(path in record_data.keys())
                self.assertEqual(md5_, record_data[path][0])
                self.assertEqual(size, record_data[path][1])

    def test_uses(self):
        # Test to determine if a distribution uses a specified file.
        # Criteria to test against
        distinfo_name = 'grammar-1.0a4'
        distinfo_dir = os.path.join(self.fake_dists_path,
            distinfo_name + '.dist-info')
        true_path = [self.fake_dists_path, distinfo_name, \
                     'grammar', 'utils.py']
        true_path = relpath(os.path.join(*true_path), sys.prefix)
        false_path = [self.fake_dists_path, 'towel_stuff-0.1', 'towel_stuff',
            '__init__.py']
        false_path = relpath(os.path.join(*false_path), sys.prefix)

        # Test if the distribution uses the file in question
        from distutils2._backport.pkgutil import Distribution
        dist = Distribution(distinfo_dir)
        self.assertTrue(dist.uses(true_path))
        self.assertFalse(dist.uses(false_path))

    def test_get_distinfo_file(self):
        # Test the retrieval of dist-info file objects.
        from distutils2._backport.pkgutil import Distribution
        distinfo_name = 'choxie-2.0.0.9'
        other_distinfo_name = 'grammar-1.0a4'
        distinfo_dir = os.path.join(self.fake_dists_path,
            distinfo_name + '.dist-info')
        dist = Distribution(distinfo_dir)
        # Test for known good file matches
        distinfo_files = [
            # Relative paths
            'INSTALLER', 'METADATA',
            # Absolute paths
            os.path.join(distinfo_dir, 'RECORD'),
            os.path.join(distinfo_dir, 'REQUESTED'),
            ]

        for distfile in distinfo_files:
            value = dist.get_distinfo_file(distfile)
            self.assertTrue(isinstance(value, file))
            # Is it the correct file?
            self.assertEqual(value.name, os.path.join(distinfo_dir, distfile))

        from distutils2.errors import DistutilsError
        # Test an absolute path that is part of another distributions dist-info
        other_distinfo_file = os.path.join(self.fake_dists_path,
            other_distinfo_name + '.dist-info', 'REQUESTED')
        self.assertRaises(DistutilsError, dist.get_distinfo_file,
            other_distinfo_file)
        # Test for a file that does not exist and should not exist
        self.assertRaises(DistutilsError, dist.get_distinfo_file, \
                          'ENTRYPOINTS')

    def test_get_distinfo_files(self):
        # Test for the iteration of RECORD path entries.
        from distutils2._backport.pkgutil import Distribution
        distinfo_name = 'towel_stuff-0.1'
        distinfo_dir = os.path.join(self.fake_dists_path,
            distinfo_name + '.dist-info')
        dist = Distribution(distinfo_dir)
        # Test for the iteration of the raw path
        distinfo_record_paths = self.records[distinfo_dir].keys()
        found = [path for path in dist.get_distinfo_files()]
        self.assertEqual(sorted(found), sorted(distinfo_record_paths))
        # Test for the iteration of local absolute paths
        distinfo_record_paths = [os.path.join(sys.prefix, path)
            for path in self.records[distinfo_dir].keys()]
        found = [path for path in dist.get_distinfo_files(local=True)]
        self.assertEqual(sorted(found), sorted(distinfo_record_paths))


class TestPkgUtilPEP376(unittest.TestCase):
    # Tests for the new functionality added in PEP 376.

    def setUp(self):
        super(TestPkgUtilPEP376, self).setUp()
        pkgutil.disable_cache()
        # Setup the path environment with our fake distributions
        current_path = os.path.abspath(os.path.dirname(__file__))
        self.sys_path = sys.path[:]
        self.fake_dists_path = os.path.join(current_path, 'fake_dists')
        sys.path.insert(0, self.fake_dists_path)

    def tearDown(self):
        sys.path[:] = self.sys_path
        pkgutil.enable_cache()
        super(TestPkgUtilPEP376, self).tearDown()

    def test_distinfo_dirname(self):
        # Given a name and a version, we expect the distinfo_dirname function
        # to return a standard distribution information directory name.

        items = [# (name, version, standard_dirname)
            # Test for a very simple single word name and decimal
            # version number
            ('docutils', '0.5', 'docutils-0.5.dist-info'),
            # Test for another except this time with a '-' in the name, which
            # needs to be transformed during the name lookup
            ('python-ldap', '2.5', 'python_ldap-2.5.dist-info'),
            # Test for both '-' in the name and a funky version number
            ('python-ldap', '2.5 a---5', 'python_ldap-2.5 a---5.dist-info'),
            ]

        # Import the function in question
        from distutils2._backport.pkgutil import distinfo_dirname

        # Loop through the items to validate the results
        for name, version, standard_dirname in items:
            dirname = distinfo_dirname(name, version)
            self.assertEqual(dirname, standard_dirname)

    def test_get_distributions(self):
        # Lookup all distributions found in the ``sys.path``.
        # This test could potentially pick up other installed distributions
        fake_dists = [('grammar', '1.0a4'), ('choxie', '2.0.0.9'),
            ('towel-stuff', '0.1')]
        found_dists = []

        # Import the function in question
        from distutils2._backport.pkgutil import get_distributions, \
                                                 Distribution, \
                                                 EggInfoDistribution

        # Verify the fake dists have been found.
        dists = [dist for dist in get_distributions()]
        for dist in dists:
            if not isinstance(dist, Distribution):
                self.fail("item received was not a Distribution instance: "
                    "%s" % type(dist))
            if dist.name in dict(fake_dists).keys() and \
               dist.path.startswith(self.fake_dists_path):
                found_dists.append((dist.name, dist.metadata['version'],))
            else:
                # check that it doesn't find anything more than this
                self.assertFalse(dist.path.startswith(self.fake_dists_path))
            # otherwise we don't care what other distributions are found

        # Finally, test that we found all that we were looking for
        self.assertListEqual(sorted(found_dists), sorted(fake_dists))

        # Now, test if the egg-info distributions are found correctly as well
        fake_dists += [('bacon', '0.1'), ('cheese', '2.0.2'),
                       ('banana', '0.4'), ('strawberry', '0.6'),
                       ('truffles', '5.0'), ('nut', 'funkyversion')]
        found_dists = []

        dists = [dist for dist in get_distributions(use_egg_info=True)]
        for dist in dists:
            if not (isinstance(dist, Distribution) or \
                    isinstance(dist, EggInfoDistribution)):
                self.fail("item received was not a Distribution or "
                          "EggInfoDistribution instance: %s" % type(dist))
            if dist.name in dict(fake_dists).keys() and \
               dist.path.startswith(self.fake_dists_path):
                found_dists.append((dist.name, dist.metadata['version']))
            else:
                self.assertFalse(dist.path.startswith(self.fake_dists_path))

        self.assertListEqual(sorted(fake_dists), sorted(found_dists))

    def test_get_distribution(self):
        # Test for looking up a distribution by name.
        # Test the lookup of the towel-stuff distribution
        name = 'towel-stuff' # Note: This is different from the directory name

        # Import the function in question
        from distutils2._backport.pkgutil import get_distribution, \
                                                 Distribution, \
                                                 EggInfoDistribution

        # Lookup the distribution
        dist = get_distribution(name)
        self.assertTrue(isinstance(dist, Distribution))
        self.assertEqual(dist.name, name)

        # Verify that an unknown distribution returns None
        self.assertEqual(None, get_distribution('bogus'))

        # Verify partial name matching doesn't work
        self.assertEqual(None, get_distribution('towel'))

        # Verify that it does not find egg-info distributions, when not
        # instructed to
        self.assertEqual(None, get_distribution('bacon'))
        self.assertEqual(None, get_distribution('cheese'))
        self.assertEqual(None, get_distribution('strawberry'))
        self.assertEqual(None, get_distribution('banana'))

        # Now check that it works well in both situations, when egg-info
        # is a file and directory respectively.
        dist = get_distribution('cheese', use_egg_info=True)
        self.assertTrue(isinstance(dist, EggInfoDistribution))
        self.assertEqual(dist.name, 'cheese')

        dist = get_distribution('bacon', use_egg_info=True)
        self.assertTrue(isinstance(dist, EggInfoDistribution))
        self.assertEqual(dist.name, 'bacon')

        dist = get_distribution('banana', use_egg_info=True)
        self.assertTrue(isinstance(dist, EggInfoDistribution))
        self.assertEqual(dist.name, 'banana')

        dist = get_distribution('strawberry', use_egg_info=True)
        self.assertTrue(isinstance(dist, EggInfoDistribution))
        self.assertEqual(dist.name, 'strawberry')

    def test_get_file_users(self):
        # Test the iteration of distributions that use a file.
        from distutils2._backport.pkgutil import get_file_users, Distribution
        name = 'towel_stuff-0.1'
        path = os.path.join(self.fake_dists_path, name,
            'towel_stuff', '__init__.py')
        for dist in get_file_users(path):
            self.assertTrue(isinstance(dist, Distribution))
            self.assertEqual(dist.name, name)

    def test_provides(self):
        # Test for looking up distributions by what they provide
        from distutils2._backport.pkgutil import provides_distribution
        from distutils2.errors import DistutilsError

        checkLists = lambda x, y: self.assertListEqual(sorted(x), sorted(y))

        l = [dist.name for dist in provides_distribution('truffles')]
        checkLists(l, ['choxie', 'towel-stuff'])

        l = [dist.name for dist in provides_distribution('truffles', '1.0')]
        checkLists(l, ['choxie'])

        l = [dist.name for dist in provides_distribution('truffles', '1.0',
                                                         use_egg_info=True)]
        checkLists(l, ['choxie', 'cheese'])

        l = [dist.name for dist in provides_distribution('truffles', '1.1.2')]
        checkLists(l, ['towel-stuff'])

        l = [dist.name for dist in provides_distribution('truffles', '1.1')]
        checkLists(l, ['towel-stuff'])

        l = [dist.name for dist in provides_distribution('truffles', \
                                                         '!=1.1,<=2.0')]
        checkLists(l, ['choxie'])

        l = [dist.name for dist in provides_distribution('truffles', \
                                                         '!=1.1,<=2.0',
                                                          use_egg_info=True)]
        checkLists(l, ['choxie', 'bacon', 'cheese'])

        l = [dist.name for dist in provides_distribution('truffles', '>1.0')]
        checkLists(l, ['towel-stuff'])

        l = [dist.name for dist in provides_distribution('truffles', '>1.5')]
        checkLists(l, [])

        l = [dist.name for dist in provides_distribution('truffles', '>1.5',
                                                         use_egg_info=True)]
        checkLists(l, ['bacon', 'truffles'])

        l = [dist.name for dist in provides_distribution('truffles', '>=1.0')]
        checkLists(l, ['choxie', 'towel-stuff'])

        l = [dist.name for dist in provides_distribution('strawberry', '0.6',
                                                         use_egg_info=True)]
        checkLists(l, ['strawberry'])

        l = [dist.name for dist in provides_distribution('strawberry', '>=0.5',
                                                         use_egg_info=True)]
        checkLists(l, ['strawberry'])


        l = [dist.name for dist in provides_distribution('strawberry', '>0.6',
                                                         use_egg_info=True)]
        checkLists(l, [])


        l = [dist.name for dist in provides_distribution('banana', '0.4',
                                                         use_egg_info=True)]
        checkLists(l, ['banana'])

        l = [dist.name for dist in provides_distribution('banana', '>=0.3',
                                                         use_egg_info=True)]
        checkLists(l, ['banana'])


        l = [dist.name for dist in provides_distribution('banana', '!=0.4',
                                                         use_egg_info=True)]
        checkLists(l, [])

    def test_obsoletes(self):
        # Test looking for distributions based on what they obsolete
        from distutils2._backport.pkgutil import obsoletes_distribution
        from distutils2.errors import DistutilsError

        checkLists = lambda x, y: self.assertListEqual(sorted(x), sorted(y))

        l = [dist.name for dist in obsoletes_distribution('truffles', '1.0')]
        checkLists(l, [])

        l = [dist.name for dist in obsoletes_distribution('truffles', '1.0',
                                                          use_egg_info=True)]
        checkLists(l, ['cheese', 'bacon'])


        l = [dist.name for dist in obsoletes_distribution('truffles', '0.8')]
        checkLists(l, ['choxie'])

        l = [dist.name for dist in obsoletes_distribution('truffles', '0.8',
                                                          use_egg_info=True)]
        checkLists(l, ['choxie', 'cheese'])

        l = [dist.name for dist in obsoletes_distribution('truffles', '0.9.6')]
        checkLists(l, ['choxie', 'towel-stuff'])

        l = [dist.name for dist in obsoletes_distribution('truffles', \
                                                          '0.5.2.3')]
        checkLists(l, ['choxie', 'towel-stuff'])

        l = [dist.name for dist in obsoletes_distribution('truffles', '0.2')]
        checkLists(l, ['towel-stuff'])

    def test_yield_distribution(self):
        # tests the internal function _yield_distributions
        from distutils2._backport.pkgutil import _yield_distributions
        checkLists = lambda x, y: self.assertListEqual(sorted(x), sorted(y))

        eggs = [('bacon', '0.1'), ('banana', '0.4'), ('strawberry', '0.6'),
                ('truffles', '5.0'), ('cheese', '2.0.2'),
                ('nut', 'funkyversion')]
        dists = [('choxie', '2.0.0.9'), ('grammar', '1.0a4'),
                 ('towel-stuff', '0.1')]

        checkLists([], _yield_distributions(False, False))

        found = [(dist.name, dist.metadata['Version'])
                for dist in _yield_distributions(False, True)
                if dist.path.startswith(self.fake_dists_path)]
        checkLists(eggs, found)

        found = [(dist.name, dist.metadata['Version'])
                for dist in _yield_distributions(True, False)
                if dist.path.startswith(self.fake_dists_path)]
        checkLists(dists, found)

        found = [(dist.name, dist.metadata['Version'])
                for dist in _yield_distributions(True, True)
                if dist.path.startswith(self.fake_dists_path)]
        checkLists(dists + eggs, found)


def test_suite():
    suite = unittest.TestSuite()
    load = unittest.defaultTestLoader.loadTestsFromTestCase
    suite.addTest(load(TestPkgUtilData))
    suite.addTest(load(TestPkgUtilDistribution))
    suite.addTest(load(TestPkgUtilPEP302))
    suite.addTest(load(TestPkgUtilPEP376))
    return suite


def test_main():
    run_unittest(test_suite())


if __name__ == "__main__":
    test_main()
