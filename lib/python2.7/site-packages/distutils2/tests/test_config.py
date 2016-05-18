# -*- encoding: utf8 -*-
"""Tests for distutils.config."""
import os
import sys
from StringIO import StringIO

from distutils2.tests import unittest, support, run_unittest


SETUP_CFG = """
[metadata]
name = RestingParrot
version = 0.6.4
author = Carl Meyer
author_email = carl@oddbird.net
maintainer = Éric Araujo
maintainer_email = merwok@netwok.org
summary = A sample project demonstrating distutils2 packaging
description = README
keywords = distutils2, packaging, sample project

classifier =
  Development Status :: 4 - Beta
  Environment :: Console (Text Based)
  Environment :: X11 Applications :: GTK; python_version < '3'
  License :: OSI Approved :: MIT License
  Programming Language :: Python
  Programming Language :: Python :: 2
  Programming Language :: Python :: 3

requires_python = >=2.4, <3.2

requires_dist =
  PetShoppe
  MichaelPalin (> 1.1)
  pywin32; sys.platform == 'win32'
  pysqlite2; python_version < '2.5'
  inotify (0.0.1); sys.platform == 'linux2'

requires_external = libxml2

provides_dist = distutils2-sample-project (0.2)
                unittest2-sample-project

project_url =
  Main repository, http://bitbucket.org/carljm/sample-distutils2-project
  Fork in progress, http://bitbucket.org/Merwok/sample-distutils2-project

[files]
packages = one
           src:two
           src2:three

py_modules = haven

scripts =
  script1.py
  scripts/find-coconuts
  bin/taunt

package_data =
  cheese = data/templates/*

data_files =
  bitmaps = bm/b1.gif, bm/b2.gif
  config = cfg/data.cfg
  /etc/init.d = init-script

# Replaces MANIFEST.in
sdist_extra =
  include THANKS HACKING
  recursive-include examples *.txt *.py
  prune examples/sample?/build
"""

class ConfigTestCase(support.TempdirManager,
                     unittest.TestCase):

    def setUp(self):
        super(ConfigTestCase, self).setUp()
        self.addCleanup(setattr, sys, 'stdout', sys.stdout)
        self.addCleanup(os.chdir, os.getcwd())

    def test_config(self):
        tempdir = self.mkdtemp()
        os.chdir(tempdir)
        self.write_file('setup.cfg', SETUP_CFG)

        # try to load the metadata now
        sys.stdout = StringIO()
        sys.argv[:] = ['setup.py', '--version']
        old_sys = sys.argv[:]
        try:
            from distutils2.core import setup
            dist = setup()
        finally:
            sys.argv[:] = old_sys

        # sanity check
        self.assertEqual(sys.stdout.getvalue(), '0.6.4' + os.linesep)

        # check what was done
        self.assertEqual(dist.metadata['Author'], 'Carl Meyer')
        self.assertEqual(dist.metadata['Author-Email'], 'carl@oddbird.net')
        self.assertEqual(dist.metadata['Version'], '0.6.4')

        wanted = ['Development Status :: 4 - Beta',
                'Environment :: Console (Text Based)',
                "Environment :: X11 Applications :: GTK; python_version < '3'",
                'License :: OSI Approved :: MIT License',
                'Programming Language :: Python',
                'Programming Language :: Python :: 2',
                'Programming Language :: Python :: 3']
        self.assertEqual(dist.metadata['Classifier'], wanted)

        wanted = ['distutils2', 'packaging', 'sample project']
        self.assertEqual(dist.metadata['Keywords'], wanted)

        self.assertEqual(dist.metadata['Requires-Python'], '>=2.4, <3.2')

        wanted = ['PetShoppe',
                  'MichaelPalin (> 1.1)',
                  "pywin32; sys.platform == 'win32'",
                  "pysqlite2; python_version < '2.5'",
                  "inotify (0.0.1); sys.platform == 'linux2'"]

        self.assertEqual(dist.metadata['Requires-Dist'], wanted)
        urls = [('Main repository',
                 'http://bitbucket.org/carljm/sample-distutils2-project'),
                ('Fork in progress',
                 'http://bitbucket.org/Merwok/sample-distutils2-project')]
        self.assertEqual(dist.metadata['Project-Url'], urls)


        self.assertEqual(dist.packages, ['one', 'two', 'three'])
        self.assertEqual(dist.py_modules, ['haven'])
        self.assertEqual(dist.package_data, {'cheese': 'data/templates/*'})
        self.assertEqual(dist.data_files,
            [('bitmaps ', ['bm/b1.gif', 'bm/b2.gif']),
             ('config ', ['cfg/data.cfg']),
             ('/etc/init.d ', ['init-script'])])
        self.assertEqual(dist.package_dir['two'], 'src')


def test_suite():
    return unittest.makeSuite(ConfigTestCase)

if __name__ == '__main__':
    run_unittest(test_suite())
