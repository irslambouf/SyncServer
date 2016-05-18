"""Tests for distutils.emxccompiler."""
import sys
import os

from distutils2.tests import run_unittest
from distutils2.tests import captured_stdout

from distutils2.compiler.emxccompiler import get_versions
from distutils2.util import get_compiler_versions
from distutils2.tests import unittest, support

class EmxCCompilerTestCase(support.TempdirManager,
                           unittest.TestCase):

    pass

def test_suite():
    return unittest.makeSuite(EmxCCompilerTestCase)

if __name__ == '__main__':
    run_unittest(test_suite())
