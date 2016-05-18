"""distutils

The main package for the Python Distribution Utilities 2.  Setup
scripts should import the setup function from distutils2.core:

    from distutils2.core import setup

    setup(name=..., version=..., ...)

Third-party tools can use parts of Distutils2 as building blocks
without causing the other modules to be imported:

    import distutils2.version
    import distutils2.pypi.simple
    import distutils2.tests.pypi_server
"""
__all__ = ['__version__']

__revision__ = "$Id: __init__.py 78020 2010-02-06 16:37:32Z benjamin.peterson $"
__version__ = "1.0a3"


# when set to True, converts doctests by default too
run_2to3_on_doctests = True
# Standard package names for fixer packages
lib2to3_fixer_packages = ['lib2to3.fixes']
