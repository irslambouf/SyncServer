"""Utilities to support packages."""

# NOTE: This module must remain compatible with Python 2.3, as it is shared
# by setuptools for distribution with Python 2.3 and up.

import os
import sys
import imp
import os.path
from csv import reader as csv_reader
from types import ModuleType
from distutils2.errors import DistutilsError
from distutils2.metadata import DistributionMetadata
from distutils2.version import suggest_normalized_version, VersionPredicate
import zipimport
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import re
import warnings


__all__ = [
    'get_importer', 'iter_importers', 'get_loader', 'find_loader',
    'walk_packages', 'iter_modules', 'get_data',
    'ImpImporter', 'ImpLoader', 'read_code', 'extend_path',
    'Distribution', 'EggInfoDistribution', 'distinfo_dirname',
    'get_distributions', 'get_distribution', 'get_file_users',
    'provides_distribution', 'obsoletes_distribution',
    'enable_cache', 'disable_cache', 'clear_cache'
]


def read_code(stream):
    # This helper is needed in order for the :pep:`302` emulation to
    # correctly handle compiled files
    import marshal

    magic = stream.read(4)
    if magic != imp.get_magic():
        return None

    stream.read(4) # Skip timestamp
    return marshal.load(stream)


def simplegeneric(func):
    """Make a trivial single-dispatch generic function"""
    registry = {}

    def wrapper(*args, **kw):
        ob = args[0]
        try:
            cls = ob.__class__
        except AttributeError:
            cls = type(ob)
        try:
            mro = cls.__mro__
        except AttributeError:
            try:

                class cls(cls, object):
                    pass
                mro = cls.__mro__[1:]
            except TypeError:
                mro = object,   # must be an ExtensionClass or some such  :(
        for t in mro:
            if t in registry:
                return registry[t](*args, **kw)
        else:
            return func(*args, **kw)
    try:
        wrapper.__name__ = func.__name__
    except (TypeError, AttributeError):
        pass    # Python 2.3 doesn't allow functions to be renamed

    def register(typ, func=None):
        if func is None:
            return lambda f: register(typ, f)
        registry[typ] = func
        return func

    wrapper.__dict__ = func.__dict__
    wrapper.__doc__ = func.__doc__
    wrapper.register = register
    return wrapper


def walk_packages(path=None, prefix='', onerror=None):
    """Yields ``(module_loader, name, ispkg)`` for all modules recursively
    on *path*, or, if *path* is ``None``, all accessible modules.

    :parameter path: should be either ``None`` or a list of paths to look for
                     modules in.
    :parameter prefix: is a string to output on the front of every module name
                       on output.

    Note that this function must import all packages (NOT all
    modules!) on the given path, in order to access the ``__path__``
    attribute to find submodules.

    *onerror* is a function which gets called with one argument (the
    name of the package which was being imported) if any exception
    occurs while trying to import a package.  If no onerror function is
    supplied, ``ImportErrors`` are caught and ignored, while all other
    exceptions are propagated, terminating the search.

    Examples:

    * list all modules python can access::

        walk_packages()

    * list all submodules of ctypes::

        walk_packages(ctypes.__path__, ctypes.__name__+'.')

    """

    def seen(p, m={}):
        if p in m:
            return True
        m[p] = True

    for importer, name, ispkg in iter_modules(path, prefix):
        yield importer, name, ispkg

        if ispkg:
            try:
                __import__(name)
            except ImportError:
                if onerror is not None:
                    onerror(name)
            except Exception:
                if onerror is not None:
                    onerror(name)
                else:
                    raise
            else:
                path = getattr(sys.modules[name], '__path__', None) or []

                # don't traverse path items we've seen before
                path = [p for p in path if not seen(p)]

                for item in walk_packages(path, name + '.', onerror):
                    yield item


def iter_modules(path=None, prefix=''):
    """Yields ``(module_loader, name, ispkg)`` for all submodules on path,
    or, if *path* is ``None``, all top-level modules on ``sys.path``.

    :parameter path: should be either None or a list of paths to look for
                     modules in.
    :parameter prefix: is a string to output on the front of every module name
                       on output.

    """

    if path is None:
        importers = iter_importers()
    else:
        importers = map(get_importer, path)

    yielded = {}
    for i in importers:
        for name, ispkg in iter_importer_modules(i, prefix):
            if name not in yielded:
                yielded[name] = 1
                yield i, name, ispkg


#@simplegeneric
def iter_importer_modules(importer, prefix=''):
    ""
    if not hasattr(importer, 'iter_modules'):
        return []
    return importer.iter_modules(prefix)

iter_importer_modules = simplegeneric(iter_importer_modules)


class ImpImporter(object):
    """:pep:`302` Importer that wraps Python's "classic" import algorithm

    ``ImpImporter(dirname)`` produces a :pep:`302` importer that searches that
    directory. ``ImpImporter(None)`` produces a :pep:`302` importer that
    searches the current ``sys.path``, plus any modules that are frozen
    or built-in.

    Note that :class:`ImpImporter` does not currently support being used by
    placement on ``sys.meta_path``.
    """

    def __init__(self, path=None):
        self.path = path

    def find_module(self, fullname, path=None):
        # Note: we ignore 'path' argument since it is only used via meta_path
        subname = fullname.split(".")[-1]
        if subname != fullname and self.path is None:
            return None
        if self.path is None:
            path = None
        else:
            path = [os.path.realpath(self.path)]
        try:
            file, filename, etc = imp.find_module(subname, path)
        except ImportError:
            return None
        return ImpLoader(fullname, file, filename, etc)

    def iter_modules(self, prefix=''):
        if self.path is None or not os.path.isdir(self.path):
            return

        yielded = {}
        import inspect

        filenames = os.listdir(self.path)
        filenames.sort()  # handle packages before same-named modules

        for fn in filenames:
            modname = inspect.getmodulename(fn)
            if modname == '__init__' or modname in yielded:
                continue

            path = os.path.join(self.path, fn)
            ispkg = False

            if not modname and os.path.isdir(path) and '.' not in fn:
                modname = fn
                for fn in os.listdir(path):
                    subname = inspect.getmodulename(fn)
                    if subname == '__init__':
                        ispkg = True
                        break
                else:
                    continue    # not a package

            if modname and '.' not in modname:
                yielded[modname] = 1
                yield prefix + modname, ispkg


class ImpLoader(object):
    """:pep:`302` Loader that wraps Python's "classic" import algorithm """

    code = source = None

    def __init__(self, fullname, file, filename, etc):
        self.file = file
        self.filename = filename
        self.fullname = fullname
        self.etc = etc

    def load_module(self, fullname):
        self._reopen()
        try:
            mod = imp.load_module(fullname, self.file, self.filename, self.etc)
        finally:
            if self.file:
                self.file.close()
        # Note: we don't set __loader__ because we want the module to look
        # normal; i.e. this is just a wrapper for standard import machinery
        return mod

    def get_data(self, pathname):
        return open(pathname, "rb").read()

    def _reopen(self):
        if self.file and self.file.closed:
            mod_type = self.etc[2]
            if mod_type == imp.PY_SOURCE:
                self.file = open(self.filename, 'rU')
            elif mod_type in (imp.PY_COMPILED, imp.C_EXTENSION):
                self.file = open(self.filename, 'rb')

    def _fix_name(self, fullname):
        if fullname is None:
            fullname = self.fullname
        elif fullname != self.fullname:
            raise ImportError("Loader for module %s cannot handle "
                              "module %s" % (self.fullname, fullname))
        return fullname

    def is_package(self, fullname):
        fullname = self._fix_name(fullname)
        return self.etc[2] == imp.PKG_DIRECTORY

    def get_code(self, fullname=None):
        fullname = self._fix_name(fullname)
        if self.code is None:
            mod_type = self.etc[2]
            if mod_type == imp.PY_SOURCE:
                source = self.get_source(fullname)
                self.code = compile(source, self.filename, 'exec')
            elif mod_type == imp.PY_COMPILED:
                self._reopen()
                try:
                    self.code = read_code(self.file)
                finally:
                    self.file.close()
            elif mod_type == imp.PKG_DIRECTORY:
                self.code = self._get_delegate().get_code()
        return self.code

    def get_source(self, fullname=None):
        fullname = self._fix_name(fullname)
        if self.source is None:
            mod_type = self.etc[2]
            if mod_type == imp.PY_SOURCE:
                self._reopen()
                try:
                    self.source = self.file.read()
                finally:
                    self.file.close()
            elif mod_type == imp.PY_COMPILED:
                if os.path.exists(self.filename[:-1]):
                    f = open(self.filename[:-1], 'rU')
                    self.source = f.read()
                    f.close()
            elif mod_type == imp.PKG_DIRECTORY:
                self.source = self._get_delegate().get_source()
        return self.source

    def _get_delegate(self):
        return ImpImporter(self.filename).find_module('__init__')

    def get_filename(self, fullname=None):
        fullname = self._fix_name(fullname)
        mod_type = self.etc[2]
        if self.etc[2] == imp.PKG_DIRECTORY:
            return self._get_delegate().get_filename()
        elif self.etc[2] in (imp.PY_SOURCE, imp.PY_COMPILED, imp.C_EXTENSION):
            return self.filename
        return None


try:
    import zipimport
    from zipimport import zipimporter

    def iter_zipimport_modules(importer, prefix=''):
        dirlist = zipimport._zip_directory_cache[importer.archive].keys()
        dirlist.sort()
        _prefix = importer.prefix
        plen = len(_prefix)
        yielded = {}
        import inspect
        for fn in dirlist:
            if not fn.startswith(_prefix):
                continue

            fn = fn[plen:].split(os.sep)

            if len(fn) == 2 and fn[1].startswith('__init__.py'):
                if fn[0] not in yielded:
                    yielded[fn[0]] = 1
                    yield fn[0], True

            if len(fn) != 1:
                continue

            modname = inspect.getmodulename(fn[0])
            if modname == '__init__':
                continue

            if modname and '.' not in modname and modname not in yielded:
                yielded[modname] = 1
                yield prefix + modname, False

    iter_importer_modules.register(zipimporter, iter_zipimport_modules)

except ImportError:
    pass


def get_importer(path_item):
    """Retrieve a  :pep:`302` importer for the given path item

    The returned importer is cached in ``sys.path_importer_cache``
    if it was newly created by a path hook.

    If there is no importer, a wrapper around the basic import
    machinery is returned. This wrapper is never inserted into
    the importer cache (``None`` is inserted instead).

    The cache (or part of it) can be cleared manually if a
    rescan of ``sys.path_hooks`` is necessary.
    """
    try:
        importer = sys.path_importer_cache[path_item]
    except KeyError:
        for path_hook in sys.path_hooks:
            try:
                importer = path_hook(path_item)
                break
            except ImportError:
                pass
        else:
            importer = None
        sys.path_importer_cache.setdefault(path_item, importer)

    if importer is None:
        try:
            importer = ImpImporter(path_item)
        except ImportError:
            importer = None
    return importer


def iter_importers(fullname=""):
    """Yield :pep:`302` importers for the given module name

    If fullname contains a '.', the importers will be for the package
    containing fullname, otherwise they will be importers for sys.meta_path,
    sys.path, and Python's "classic" import machinery, in that order.  If
    the named module is in a package, that package is imported as a side
    effect of invoking this function.

    Non :pep:`302` mechanisms (e.g. the Windows registry) used by the
    standard import machinery to find files in alternative locations
    are partially supported, but are searched AFTER ``sys.path``. Normally,
    these locations are searched BEFORE sys.path, preventing ``sys.path``
    entries from shadowing them.

    For this to cause a visible difference in behaviour, there must
    be a module or package name that is accessible via both sys.path
    and one of the non :pep:`302` file system mechanisms. In this case,
    the emulation will find the former version, while the builtin
    import mechanism will find the latter.

    Items of the following types can be affected by this discrepancy:
        ``imp.C_EXTENSION, imp.PY_SOURCE, imp.PY_COMPILED, imp.PKG_DIRECTORY``
    """
    if fullname.startswith('.'):
        raise ImportError("Relative module names not supported")
    if '.' in fullname:
        # Get the containing package's __path__
        pkg = '.'.join(fullname.split('.')[:-1])
        if pkg not in sys.modules:
            __import__(pkg)
        path = getattr(sys.modules[pkg], '__path__', None) or []
    else:
        for importer in sys.meta_path:
            yield importer
        path = sys.path
    for item in path:
        yield get_importer(item)
    if '.' not in fullname:
        yield ImpImporter()


def get_loader(module_or_name):
    """Get a :pep:`302` "loader" object for module_or_name

    If the module or package is accessible via the normal import
    mechanism, a wrapper around the relevant part of that machinery
    is returned.  Returns None if the module cannot be found or imported.
    If the named module is not already imported, its containing package
    (if any) is imported, in order to establish the package ``__path__``.

    This function uses :func:`iter_importers`, and is thus subject to the same
    limitations regarding platform-specific special import locations such
    as the Windows registry.
    """
    if module_or_name in sys.modules:
        module_or_name = sys.modules[module_or_name]
    if isinstance(module_or_name, ModuleType):
        module = module_or_name
        loader = getattr(module, '__loader__', None)
        if loader is not None:
            return loader
        fullname = module.__name__
    else:
        fullname = module_or_name
    return find_loader(fullname)


def find_loader(fullname):
    """Find a :pep:`302` "loader" object for fullname

    If fullname contains dots, path must be the containing package's
    ``__path__``. Returns ``None`` if the module cannot be found or imported.
    This function uses :func:`iter_importers`, and is thus subject to the same
    limitations regarding platform-specific special import locations such as
    the Windows registry.
    """
    for importer in iter_importers(fullname):
        loader = importer.find_module(fullname)
        if loader is not None:
            return loader

    return None


def extend_path(path, name):
    """Extend a package's path.

    Intended use is to place the following code in a package's
    ``__init__.py``::

        from pkgutil import extend_path
        __path__ = extend_path(__path__, __name__)

    This will add to the package's ``__path__`` all subdirectories of
    directories on ``sys.path`` named after the package.  This is useful
    if one wants to distribute different parts of a single logical
    package as multiple directories.

    It also looks for ``*.pkg`` files beginning where ``*`` matches the name
    argument.  This feature is similar to ``*.pth`` files (see ``site.py``),
    except that it doesn't special-case lines starting with ``import``.
    A ``*.pkg`` file is trusted at face value: apart from checking for
    duplicates, all entries found in a ``*.pkg`` file are added to the
    path, regardless of whether they are exist the filesystem.  (This
    is a feature.)

    If the input path is not a list (as is the case for frozen
    packages) it is returned unchanged.  The input path is not
    modified; an extended copy is returned.  Items are only appended
    to the copy at the end.

    It is assumed that sys.path is a sequence.  Items of sys.path that
    are not (unicode or 8-bit) strings referring to existing
    directories are ignored.  Unicode items of sys.path that cause
    errors when used as filenames may cause this function to raise an
    exception (in line with ``os.path.isdir()`` behavior).
    """

    if not isinstance(path, list):
        # This could happen e.g. when this is called from inside a
        # frozen package.  Return the path unchanged in that case.
        return path

    pname = os.path.join(*name.split('.')) # Reconstitute as relative path
    # Just in case os.extsep != '.'
    sname = os.extsep.join(name.split('.'))
    sname_pkg = sname + os.extsep + "pkg"
    init_py = "__init__" + os.extsep + "py"

    path = path[:] # Start with a copy of the existing path

    for dir in sys.path:
        if not isinstance(dir, basestring) or not os.path.isdir(dir):
            continue
        subdir = os.path.join(dir, pname)
        # XXX This may still add duplicate entries to path on
        # case-insensitive filesystems
        initfile = os.path.join(subdir, init_py)
        if subdir not in path and os.path.isfile(initfile):
            path.append(subdir)
        # XXX Is this the right thing for subpackages like zope.app?
        # It looks for a file named "zope.app.pkg"
        pkgfile = os.path.join(dir, sname_pkg)
        if os.path.isfile(pkgfile):
            try:
                f = open(pkgfile)
            except IOError, msg:
                sys.stderr.write("Can't open %s: %s\n" %
                                 (pkgfile, msg))
            else:
                for line in f:
                    line = line.rstrip('\n')
                    if not line or line.startswith('#'):
                        continue
                    path.append(line) # Don't check for existence!
                f.close()

    return path


def get_data(package, resource):
    """Get a resource from a package.

    This is a wrapper round the :pep:`302` loader get_data API. The package
    argument should be the name of a package, in standard module format
    (``foo.bar``). The resource argument should be in the form of a relative
    filename, using ``'/'`` as the path separator. The parent directory name
    ``'..'`` is not allowed, and nor is a rooted name (starting with a
    ``'/'``).

    The function returns a binary string, which is the contents of the
    specified resource.

    For packages located in the filesystem, which have already been imported,
    this is the rough equivalent of::

        d = os.path.dirname(sys.modules[package].__file__)
        data = open(os.path.join(d, resource), 'rb').read()

    If the package cannot be located or loaded, or it uses a :pep:`302` loader
    which does not support :func:`get_data`, then ``None`` is returned.
    """

    loader = get_loader(package)
    if loader is None or not hasattr(loader, 'get_data'):
        return None
    mod = sys.modules.get(package) or loader.load_module(package)
    if mod is None or not hasattr(mod, '__file__'):
        return None

    # Modify the resource name to be compatible with the loader.get_data
    # signature - an os.path format "filename" starting with the dirname of
    # the package's __file__
    parts = resource.split('/')
    parts.insert(0, os.path.dirname(mod.__file__))
    resource_name = os.path.join(*parts)
    return loader.get_data(resource_name)

##########################
# PEP 376 Implementation #
##########################

DIST_FILES = ('INSTALLER', 'METADATA', 'RECORD', 'REQUESTED',)

# Cache
_cache_name = {} # maps names to Distribution instances
_cache_name_egg = {} # maps names to EggInfoDistribution instances
_cache_path = {} # maps paths to Distribution instances
_cache_path_egg = {} # maps paths to EggInfoDistribution instances
_cache_generated = False # indicates if .dist-info distributions are cached
_cache_generated_egg = False # indicates if .dist-info and .egg are cached
_cache_enabled = True


def enable_cache():
    """
    Enables the internal cache.

    Note that this function will not clear the cache in any case, for that
    functionality see :func:`clear_cache`.
    """
    global _cache_enabled

    _cache_enabled = True

def disable_cache():
    """
    Disables the internal cache.

    Note that this function will not clear the cache in any case, for that
    functionality see :func:`clear_cache`.
    """
    global _cache_enabled

    _cache_enabled = False

def clear_cache():
    """ Clears the internal cache. """
    global _cache_name, _cache_name_egg, cache_path, _cache_path_egg, \
           _cache_generated, _cache_generated_egg

    _cache_name = {}
    _cache_name_egg = {}
    _cache_path = {}
    _cache_path_egg = {}
    _cache_generated = False
    _cache_generated_egg = False


def _yield_distributions(include_dist, include_egg):
    """
    Yield .dist-info and .egg(-info) distributions, based on the arguments

    :parameter include_dist: yield .dist-info distributions
    :parameter include_egg: yield .egg(-info) distributions
    """
    for path in sys.path:
        realpath = os.path.realpath(path)
        if not os.path.isdir(realpath):
            continue
        for dir in os.listdir(realpath):
            dist_path = os.path.join(realpath, dir)
            if include_dist and dir.endswith('.dist-info'):
                yield Distribution(dist_path)
            elif include_egg and (dir.endswith('.egg-info') or
                                  dir.endswith('.egg')):
                yield EggInfoDistribution(dist_path)


def _generate_cache(use_egg_info=False):
    global _cache_generated, _cache_generated_egg

    if _cache_generated_egg or (_cache_generated and not use_egg_info):
        return
    else:
        gen_dist = not _cache_generated
        gen_egg = use_egg_info

        for dist in _yield_distributions(gen_dist, gen_egg):
            if isinstance(dist, Distribution):
                _cache_path[dist.path] = dist
                if not dist.name in _cache_name:
                    _cache_name[dist.name] = []
                _cache_name[dist.name].append(dist)
            else:
                _cache_path_egg[dist.path] = dist
                if not dist.name in _cache_name_egg:
                    _cache_name_egg[dist.name] = []
                _cache_name_egg[dist.name].append(dist)

        if gen_dist:
            _cache_generated = True
        if gen_egg:
            _cache_generated_egg = True


class Distribution(object):
    """Created with the *path* of the ``.dist-info`` directory provided to the
    constructor. It reads the metadata contained in ``METADATA`` when it is
    instantiated."""

    # Attribute documenting for Sphinx style documentation, see for more info:
    #   http://sphinx.pocoo.org/ext/autodoc.html#dir-autoattribute
    name = ''
    """The name of the distribution."""
    metadata = None
    """A :class:`distutils2.metadata.DistributionMetadata` instance loaded with
    the distribution's ``METADATA`` file."""
    requested = False
    """A boolean that indicates whether the ``REQUESTED`` metadata file is
    present (in other words, whether the package was installed by user
    request or it was installed as a dependency)."""

    def __init__(self, path):
        if _cache_enabled and path in _cache_path:
            self.metadata = _cache_path[path].metadata
        else:
            metadata_path = os.path.join(path, 'METADATA')
            self.metadata = DistributionMetadata(path=metadata_path)

        self.path = path
        self.name = self.metadata['name']

        if _cache_enabled and not path in _cache_path:
            _cache_path[path] = self

    def _get_records(self, local=False):
        RECORD = os.path.join(self.path, 'RECORD')
        record_reader = csv_reader(open(RECORD, 'rb'), delimiter=',')
        for row in record_reader:
            path, md5, size = row[:] + [None for i in xrange(len(row), 3)]
            if local:
                path = path.replace('/', os.sep)
                path = os.path.join(sys.prefix, path)
            yield path, md5, size

    def get_installed_files(self, local=False):
        """
        Iterates over the ``RECORD`` entries and returns a tuple
        ``(path, md5, size)`` for each line. If *local* is ``True``,
        the returned path is transformed into a local absolute path.
        Otherwise the raw value from RECORD is returned.

        A local absolute path is an absolute path in which occurrences of
        ``'/'`` have been replaced by the system separator given by ``os.sep``.

        :parameter local: flag to say if the path should be returned a local
                          absolute path

        :type local: boolean
        :returns: iterator of (path, md5, size)
        """
        return self._get_records(local)

    def uses(self, path):
        """
        Returns ``True`` if path is listed in ``RECORD``. *path* can be a local
        absolute path or a relative ``'/'``-separated path.

        :rtype: boolean
        """
        for p, md5, size in self._get_records():
            local_absolute = os.path.join(sys.prefix, p)
            if path == p or path == local_absolute:
                return True
        return False

    def get_distinfo_file(self, path, binary=False):
        """
        Returns a file located under the ``.dist-info`` directory. Returns a
        ``file`` instance for the file pointed by *path*.

        :parameter path: a ``'/'``-separated path relative to the
                         ``.dist-info`` directory or an absolute path;
                         If *path* is an absolute path and doesn't start
                         with the ``.dist-info`` directory path,
                         a :class:`DistutilsError` is raised
        :type path: string
        :parameter binary: If *binary* is ``True``, opens the file in read-only
                           binary mode (``rb``), otherwise opens it in
                           read-only mode (``r``).
        :rtype: file object
        """
        open_flags = 'r'
        if binary:
            open_flags += 'b'

        # Check if it is an absolute path
        if path.find(os.sep) >= 0:
            # it's an absolute path?
            distinfo_dirname, path = path.split(os.sep)[-2:]
            if distinfo_dirname != self.path.split(os.sep)[-1]:
                raise DistutilsError("Requested dist-info file does not "
                    "belong to the %s distribution. '%s' was requested." \
                    % (self.name, os.sep.join([distinfo_dirname, path])))

        # The file must be relative
        if path not in DIST_FILES:
            raise DistutilsError("Requested an invalid dist-info file: "
                "%s" % path)

        # Convert the relative path back to absolute
        path = os.path.join(self.path, path)
        return open(path, open_flags)

    def get_distinfo_files(self, local=False):
        """
        Iterates over the ``RECORD`` entries and returns paths for each line if
        the path is pointing to a file located in the ``.dist-info`` directory
        or one of its subdirectories.

        :parameter local: If *local* is ``True``, each returned path is
                          transformed into a local absolute path. Otherwise the
                          raw value from ``RECORD`` is returned.
        :type local: boolean
        :returns: iterator of paths
        """
        for path, md5, size in self._get_records(local):
            yield path

    def __eq__(self, other):
        return isinstance(other, Distribution) and self.path == other.path

    # See http://docs.python.org/reference/datamodel#object.__hash__
    __hash__ = object.__hash__


class EggInfoDistribution(object):
    """Created with the *path* of the ``.egg-info`` directory or file provided
    to the constructor. It reads the metadata contained in the file itself, or
    if the given path happens to be a directory, the metadata is read from the
    file ``PKG-INFO`` under that directory."""

    name = ''
    """The name of the distribution."""
    metadata = None
    """A :class:`distutils2.metadata.DistributionMetadata` instance loaded with
    the distribution's ``METADATA`` file."""
    _REQUIREMENT = re.compile( \
        r'(?P<name>[-A-Za-z0-9_.]+)\s*' \
        r'(?P<first>(?:<|<=|!=|==|>=|>)[-A-Za-z0-9_.]+)?\s*' \
        r'(?P<rest>(?:\s*,\s*(?:<|<=|!=|==|>=|>)[-A-Za-z0-9_.]+)*)\s*' \
        r'(?P<extras>\[.*\])?')

    def __init__(self, path):
        self.path = path

        if _cache_enabled and path in _cache_path_egg:
            self.metadata = _cache_path_egg[path].metadata
            self.name = self.metadata['Name']
            return

        # reused from Distribute's pkg_resources
        def yield_lines(strs):
            """Yield non-empty/non-comment lines of a ``basestring``
            or sequence"""
            if isinstance(strs, basestring):
                for s in strs.splitlines():
                    s = s.strip()
                    if s and not s.startswith('#'): # skip blank lines/comments
                        yield s
            else:
                for ss in strs:
                    for s in yield_lines(ss):
                        yield s

        requires = None
        if path.endswith('.egg'):
            if os.path.isdir(path):
                meta_path = os.path.join(path, 'EGG-INFO', 'PKG-INFO')
                self.metadata = DistributionMetadata(path=meta_path)
                try:
                    req_path = os.path.join(path, 'EGG-INFO', 'requires.txt')
                    requires = open(req_path, 'r').read()
                except IOError:
                    requires = None
            else:
                zipf = zipimport.zipimporter(path)
                fileobj = StringIO.StringIO(zipf.get_data('EGG-INFO/PKG-INFO'))
                self.metadata = DistributionMetadata(fileobj=fileobj)
                try:
                    requires = zipf.get_data('EGG-INFO/requires.txt')
                except IOError:
                    requires = None
            self.name = self.metadata['Name']
        elif path.endswith('.egg-info'):
            if os.path.isdir(path):
                path = os.path.join(path, 'PKG-INFO')
                try:
                    req_f = open(os.path.join(path, 'requires.txt'), 'r')
                    requires = req_f.read()
                except IOError:
                    requires = None
            self.metadata = DistributionMetadata(path=path)
            self.name = self.metadata['name']
        else:
            raise ValueError('The path must end with .egg-info or .egg')

        provides = "%s (%s)" % (self.metadata['name'],
                                self.metadata['version'])
        if self.metadata['Metadata-Version'] == '1.2':
            self.metadata['Provides-Dist'] += (provides,)
        else:
            self.metadata['Provides'] += (provides,)
        reqs = []
        if requires is not None:
            for line in yield_lines(requires):
                if line[0] == '[':
                    warnings.warn('distutils2 does not support extensions '
                                  'in requires.txt')
                    break
                else:
                    match = self._REQUIREMENT.match(line.strip())
                    if not match:
                        raise ValueError('Distribution %s has ill formed '
                                         'requires.txt file (%s)' %
                                         (self.name, line))
                    else:
                        if match.group('extras'):
                            s = (('Distribution %s uses extra requirements '
                                  'which are not supported in distutils') \
                                         % (self.name))
                            warnings.warn(s)
                        name = match.group('name')
                        version = None
                        if match.group('first'):
                            version = match.group('first')
                            if match.group('rest'):
                                version += match.group('rest')
                            version = version.replace(' ', '') # trim spaces
                        if version is None:
                            reqs.append(name)
                        else:
                            reqs.append('%s (%s)' % (name, version))
            if self.metadata['Metadata-Version'] == '1.2':
                self.metadata['Requires-Dist'] += reqs
            else:
                self.metadata['Requires'] += reqs

        if _cache_enabled:
            _cache_path_egg[self.path] = self

    def get_installed_files(self, local=False):
        return []

    def uses(self, path):
        return False

    def __eq__(self, other):
        return isinstance(other, EggInfoDistribution) and \
               self.path == other.path

    # See http://docs.python.org/reference/datamodel#object.__hash__
    __hash__ = object.__hash__


def _normalize_dist_name(name):
    """Returns a normalized name from the given *name*.
    :rtype: string"""
    return name.replace('-', '_')


def distinfo_dirname(name, version):
    """
    The *name* and *version* parameters are converted into their
    filename-escaped form, i.e. any ``'-'`` characters are replaced
    with ``'_'`` other than the one in ``'dist-info'`` and the one
    separating the name from the version number.

    :parameter name: is converted to a standard distribution name by replacing
                     any runs of non- alphanumeric characters with a single
                     ``'-'``.
    :type name: string
    :parameter version: is converted to a standard version string. Spaces
                        become dots, and all other non-alphanumeric characters
                        (except dots) become dashes, with runs of multiple
                        dashes condensed to a single dash.
    :type version: string
    :returns: directory name
    :rtype: string"""
    file_extension = '.dist-info'
    name = _normalize_dist_name(name)
    normalized_version = suggest_normalized_version(version)
    # Because this is a lookup procedure, something will be returned even if
    #   it is a version that cannot be normalized
    if normalized_version is None:
        # Unable to achieve normality?
        normalized_version = version
    return '-'.join([name, normalized_version]) + file_extension


def get_distributions(use_egg_info=False):
    """
    Provides an iterator that looks for ``.dist-info`` directories in
    ``sys.path`` and returns :class:`Distribution` instances for each one of
    them. If the parameters *use_egg_info* is ``True``, then the ``.egg-info``
    files and directores are iterated as well.

    :rtype: iterator of :class:`Distribution` and :class:`EggInfoDistribution`
            instances
    """
    if not _cache_enabled:
        for dist in _yield_distributions(True, use_egg_info):
            yield dist
    else:
        _generate_cache(use_egg_info)

        for dist in _cache_path.itervalues():
            yield dist

        if use_egg_info:
            for dist in _cache_path_egg.itervalues():
                yield dist


def get_distribution(name, use_egg_info=False):
    """
    Scans all elements in ``sys.path`` and looks for all directories
    ending with ``.dist-info``. Returns a :class:`Distribution`
    corresponding to the ``.dist-info`` directory that contains the
    ``METADATA`` that matches *name* for the *name* metadata field.
    If no distribution exists with the given *name* and the parameter
    *use_egg_info* is set to ``True``, then all files and directories ending
    with ``.egg-info`` are scanned. A :class:`EggInfoDistribution` instance is
    returned if one is found that has metadata that matches *name* for the
    *name* metadata field.

    This function only returns the first result found, as no more than one
    value is expected. If the directory is not found, ``None`` is returned.

    :rtype: :class:`Distribution` or :class:`EggInfoDistribution` or None
    """
    if not _cache_enabled:
        for dist in _yield_distributions(True, use_egg_info):
            if dist.name == name:
                return dist
    else:
        _generate_cache(use_egg_info)

        if name in _cache_name:
            return _cache_name[name][0]
        elif use_egg_info and name in _cache_name_egg:
            return _cache_name_egg[name][0]
        else:
            return None


def obsoletes_distribution(name, version=None, use_egg_info=False):
    """
    Iterates over all distributions to find which distributions obsolete
    *name*.

    If a *version* is provided, it will be used to filter the results.
    If the argument *use_egg_info* is set to ``True``, then ``.egg-info``
    distributions will be considered as well.

    :type name: string
    :type version: string
    :parameter name:
    """
    for dist in get_distributions(use_egg_info):
        obsoleted = (dist.metadata['Obsoletes-Dist'] +
                     dist.metadata['Obsoletes'])
        for obs in obsoleted:
            o_components = obs.split(' ', 1)
            if len(o_components) == 1 or version is None:
                if name == o_components[0]:
                    yield dist
                    break
            else:
                try:
                    predicate = VersionPredicate(obs)
                except ValueError:
                    raise DistutilsError(('Distribution %s has ill formed' +
                                          ' obsoletes field') % (dist.name,))
                if name == o_components[0] and predicate.match(version):
                    yield dist
                    break


def provides_distribution(name, version=None, use_egg_info=False):
    """
    Iterates over all distributions to find which distributions provide *name*.
    If a *version* is provided, it will be used to filter the results. Scans
    all elements in ``sys.path``  and looks for all directories ending with
    ``.dist-info``. Returns a :class:`Distribution`  corresponding to the
    ``.dist-info`` directory that contains a ``METADATA`` that matches *name*
    for the name metadata. If the argument *use_egg_info* is set to ``True``,
    then all files and directories ending with ``.egg-info`` are considered
    as well and returns an :class:`EggInfoDistribution` instance.

    This function only returns the first result found, since no more than
    one values are expected. If the directory is not found, returns ``None``.

    :parameter version: a version specifier that indicates the version
                        required, conforming to the format in ``PEP-345``

    :type name: string
    :type version: string
    """
    predicate = None
    if not version is None:
        try:
            predicate = VersionPredicate(name + ' (' + version + ')')
        except ValueError:
            raise DistutilsError('Invalid name or version')

    for dist in get_distributions(use_egg_info):
        provided = dist.metadata['Provides-Dist'] + dist.metadata['Provides']

        for p in provided:
            p_components = p.rsplit(' ', 1)
            if len(p_components) == 1 or predicate is None:
                if name == p_components[0]:
                    yield dist
                    break
            else:
                p_name, p_ver = p_components
                if len(p_ver) < 2 or p_ver[0] != '(' or p_ver[-1] != ')':
                    raise DistutilsError(('Distribution %s has invalid ' +
                                          'provides field: %s') \
                                           % (dist.name, p))
                p_ver = p_ver[1:-1] # trim off the parenthesis
                if p_name == name and predicate.match(p_ver):
                    yield dist
                    break


def get_file_users(path):
    """
    Iterates over all distributions to find out which distributions uses
    *path*.

    :parameter path: can be a local absolute path or a relative
                     ``'/'``-separated path.
    :type path: string
    :rtype: iterator of :class:`Distribution` instances
    """
    for dist in get_distributions():
        if dist.uses(path):
            yield dist
