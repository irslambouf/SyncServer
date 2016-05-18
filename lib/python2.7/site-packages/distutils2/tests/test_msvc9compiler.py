"""Tests for distutils.msvc9compiler."""
import sys
import os

from distutils2.errors import DistutilsPlatformError
from distutils2.tests import unittest, support

_MANIFEST = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1"
          manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false">
        </requestedExecutionLevel>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.VC90.CRT"
         version="9.0.21022.8" processorArchitecture="x86"
         publicKeyToken="XXXX">
      </assemblyIdentity>
    </dependentAssembly>
  </dependency>
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.VC90.MFC"
        version="9.0.21022.8" processorArchitecture="x86"
        publicKeyToken="XXXX"></assemblyIdentity>
    </dependentAssembly>
  </dependency>
</assembly>
"""

_CLEANED_MANIFEST = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1"
          manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false">
        </requestedExecutionLevel>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <dependency>

  </dependency>
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.VC90.MFC"
        version="9.0.21022.8" processorArchitecture="x86"
        publicKeyToken="XXXX"></assemblyIdentity>
    </dependentAssembly>
  </dependency>
</assembly>"""


class msvc9compilerTestCase(support.TempdirManager,
                            unittest.TestCase):

    @unittest.skipUnless(sys.platform == "win32", "runs only on win32")
    def test_no_compiler(self):
        # makes sure query_vcvarsall throws
        # a DistutilsPlatformError if the compiler
        # is not found
        from distutils2.compiler.msvccompiler import get_build_version
        if get_build_version() < 8.0:
            # this test is only for MSVC8.0 or above
            return
        from distutils2.compiler.msvc9compiler import query_vcvarsall
        def _find_vcvarsall(version):
            return None

        from distutils2 import msvc9compiler
        old_find_vcvarsall = msvc9compiler.find_vcvarsall
        msvc9compiler.find_vcvarsall = _find_vcvarsall
        try:
            self.assertRaises(DistutilsPlatformError, query_vcvarsall,
                             'wont find this version')
        finally:
            msvc9compiler.find_vcvarsall = old_find_vcvarsall

    @unittest.skipUnless(sys.platform == "win32", "runs only on win32")
    def test_reg_class(self):
        from distutils2.compiler.msvccompiler import get_build_version
        if get_build_version() < 8.0:
            raise unittest.SkipTest("requires MSVC 8.0 or later")

        from distutils2.compiler.msvc9compiler import Reg
        self.assertRaises(KeyError, Reg.get_value, 'xxx', 'xxx')

        # looking for values that should exist on all
        # windows registeries versions.
        path = r'Control Panel\Desktop'
        v = Reg.get_value(path, u'dragfullwindows')
        self.assertTrue(v in (u'0', u'1', u'2'))

        import _winreg
        HKCU = _winreg.HKEY_CURRENT_USER
        keys = Reg.read_keys(HKCU, 'xxxx')
        self.assertEqual(keys, None)

        keys = Reg.read_keys(HKCU, r'Control Panel')
        self.assertTrue('Desktop' in keys)

    @unittest.skipUnless(sys.platform == "win32", "runs only on win32")
    def test_remove_visual_c_ref(self):
        from distutils2.compiler.msvccompiler import get_build_version
        if get_build_version() < 8.0:
            raise unittest.SkipTest("requires MSVC 8.0 or later")

        from distutils2.compiler.msvc9compiler import MSVCCompiler
        tempdir = self.mkdtemp()
        manifest = os.path.join(tempdir, 'manifest')
        f = open(manifest, 'w')
        try:
            f.write(_MANIFEST)
        finally:
            f.close()

        compiler = MSVCCompiler()
        compiler._remove_visual_c_ref(manifest)

        # see what we got
        f = open(manifest)
        try:
            # removing trailing spaces
            content = '\n'.join([line.rstrip() for line in f.readlines()])
        finally:
            f.close()

        # makes sure the manifest was properly cleaned
        self.assertEqual(content, _CLEANED_MANIFEST)


def test_suite():
    return unittest.makeSuite(msvc9compilerTestCase)

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
