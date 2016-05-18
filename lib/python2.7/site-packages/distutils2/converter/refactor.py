"""distutils2.converter.refactor

"""
try:
    from lib2to3.refactor import RefactoringTool
    _LIB2TO3 = True
except ImportError:
    # we need 2.6 at least to run this
    _LIB2TO3 = False

_DISTUTILS_FIXERS = ['distutils2.converter.fixers.fix_imports',
                     'distutils2.converter.fixers.fix_setup_options']