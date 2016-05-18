#!/Users/tarek/Dev/hg.mozilla.org/server-devtools/bin/python
import os
import sys
import tempfile
import tarfile
import shutil
import subprocess
import argparse
from tarfile import ReadError
from ConfigParser import ConfigParser
import collections
import re
import urllib
import urllib2
import getpass

import distutils2.version
from distutils2.index.simple import Crawler, DEFAULT_SIMPLE_INDEX_URL


def get_temp_dir():
    user = getpass.getuser()
    return tempfile.mkdtemp(prefix='pypi2rpm-%s-' % user)


def _is_d2(location=os.curdir):
    """Returns True if the project is a Distutils2 Project"""
    setup_cfg = os.path.join(location, 'setup.cfg')
    if not os.path.exists(setup_cfg):
        return False
    f = open(setup_cfg)
    try:
        return '[metadata]' in f.read()
    finally:
        f.close()


def get_release(project_name, version=None,
                index_url=DEFAULT_SIMPLE_INDEX_URL,
                download_cache=None):
    if os.path.exists(project_name):
        return project_name

    if (project_name.startswith('http://') or
        project_name.startswith('https://')):
        filename = project_name.split('/')[-1]

        if download_cache is not None:
            filename = os.path.join(download_cache, filename)

        content = urllib2.urlopen(project_name).read()

        with open(filename, 'w') as f:
            f.write(content)

        return os.path.abspath(filename)

    c = Crawler(index_url=index_url, prefer_final=True)
    project = c.get_releases(project_name)
    if version is None:
        release = project[0]
    else:
        if version not in project.get_versions():
            print 'Unknown version'
            return None
        release = project.get_release(version)

    dist = release.get_distribution(prefer_source=True)
    target_url = dist.url['url']

    if download_cache is not None:
        target_file = os.path.join(download_cache,
                                   urllib.quote(target_url, ''))

        if os.path.exists(target_file):
            return target_file

    temp_path = get_temp_dir()
    try:
        path = release.download(temp_path)
        if download_cache is not None:
            os.rename(path, target_file)
            path = target_file
        return path
    finally:
        if download_cache is not None:
            shutil.rmtree(temp_path)


_MAJOR, _MINOR = sys.version_info[0], sys.version_info[1]
_PYTHON = 'python%d%d' % (_MAJOR, _MINOR)


def _d1_sdist2rpm(dist_dir):
    # grab the name and create a normalized one
    popen = subprocess.Popen('%s setup.py --name' % sys.executable,
                                stdout=subprocess.PIPE, shell=True)
    name = [line for line in popen.stdout.read().split('\n') if line != '']
    name = name[-1].strip().lower()

    if not name.startswith('python'):
        name = '%s-%s' % (_PYTHON, name)
    elif name.startswith('python-'):
        name = '%s-%s' % (_PYTHON, name[len('python-'):])

    # run the bdist_rpm2 command
    tmppath = get_temp_dir()
    try:
        cmd = ('--command-packages=pypi2rpm.command bdist_rpm2 '
            '--binary-only '
            '--tmppath %s' % tmppath)

        if dist_dir is not None:
            cmd += ' --dist-dir=%s' % dist_dir
        else:
            cmd += ' --dist-dir=%s' % os.getcwd()

        call = '%s setup.py %s --name=%s --python=%s' % \
                (sys.executable, cmd, name, os.path.basename(sys.executable))
        print(call)
        res = subprocess.call(call, shell=True)
    finally:
        shutil.rmtree(tmppath)

    if res != 0:
        print('Could not create RPM')
        sys.exit(1)


def _d2_sdist2rpm(dist_dir):
    setup_cfg = ConfigParser()
    setup_cfg.read('setup.cfg')
    name = setup_cfg.get('metadata', 'name')
    name = name.strip().lower()
    if not name.startswith('python-'):
        name = 'python-%s' % name

    cmd = '-m distutils2.run bdist_rpm2 --binary-only'
    if dist_dir is not None:
        cmd += ' --dist-dir=%s' % dist_dir
    # run the bdist_rpm2 command
    os.system('%s %s --name=%s' % (sys.executable, cmd, name))


#
# Archive management, extracted from py3k's shutil
#
try:
    import bz2    # NOQA
    _BZ2_SUPPORTED = True
except ImportError:
    _BZ2_SUPPORTED = False


def get_unpack_formats():
    """Returns a list of supported formats for unpacking.

    Each element of the returned sequence is a tuple
    (name, extensions, description)
    """
    formats = [(name, info[0], info[3]) for name, info in
               _UNPACK_FORMATS.items()]
    formats.sort()
    return formats


def _check_unpack_options(extensions, function, extra_args):
    """Checks what gets registered as an unpacker."""
    # first make sure no other unpacker is registered for this extension
    existing_extensions = {}
    for name, info in _UNPACK_FORMATS.items():
        for ext in info[0]:
            existing_extensions[ext] = name

    for extension in extensions:
        if extension in existing_extensions:
            msg = '%s is already registered for "%s"'
            raise shutil.RegistryError(msg % (extension,
                                       existing_extensions[extension]))

    if not isinstance(function, collections.Callable):
        raise TypeError('The registered function must be a callable')


def register_unpack_format(name, extensions, function, extra_args=None,
                           description=''):
    """Registers an unpack format.

    `name` is the name of the format. `extensions` is a list of extensions
    corresponding to the format.

    `function` is the callable that will be
    used to unpack archives. The callable will receive archives to unpack.
    If it's unable to handle an archive, it needs to raise a ReadError
    exception.

    If provided, `extra_args` is a sequence of
    (name, value) tuples that will be passed as arguments to the callable.
    description can be provided to describe the format, and will be returned
    by the get_unpack_formats() function.
    """
    if extra_args is None:
        extra_args = []
    _check_unpack_options(extensions, function, extra_args)
    _UNPACK_FORMATS[name] = extensions, function, extra_args, description


def unregister_unpack_format(name):
    """Removes the pack format from the registery."""
    del _UNPACK_FORMATS[name]


def _ensure_directory(path):
    """Ensure that the parent directory of `path` exists"""
    dirname = os.path.dirname(path)
    if not os.path.isdir(dirname):
        os.makedirs(dirname)


def _unpack_zipfile(filename, extract_dir):
    """Unpack zip `filename` to `extract_dir`
    """
    try:
        import zipfile
    except ImportError:
        raise ReadError('zlib not supported, cannot unpack this archive.')

    if not zipfile.is_zipfile(filename):
        raise ReadError("%s is not a zip file" % filename)

    zip = zipfile.ZipFile(filename)
    try:
        for info in zip.infolist():
            name = info.filename

            # don't extract absolute paths or ones with .. in them
            if name.startswith('/') or '..' in name:
                continue

            target = os.path.join(extract_dir, *name.split('/'))
            if not target:
                continue

            _ensure_directory(target)
            if not name.endswith('/'):
                # file
                data = zip.read(info.filename)
                f = open(target, 'wb')
                try:
                    f.write(data)
                finally:
                    f.close()
                    del data
    finally:
        zip.close()


def _unpack_tarfile(filename, extract_dir):
    """Unpack tar/tar.gz/tar.bz2 `filename` to `extract_dir`
    """
    try:
        tarobj = tarfile.open(filename)
    except tarfile.TarError:
        raise ReadError(
            "%s is not a compressed or uncompressed tar file" % filename)
    try:
        tarobj.extractall(extract_dir)
    finally:
        tarobj.close()

_UNPACK_FORMATS = {
    'gztar': (['.tar.gz', '.tgz'], _unpack_tarfile, [], "gzip'ed tar-file"),
    'tar':   (['.tar'], _unpack_tarfile, [], "uncompressed tar file"),
    'zip':   (['.zip'], _unpack_zipfile, [], "ZIP file")}


if _BZ2_SUPPORTED:
    _UNPACK_FORMATS['bztar'] = (['.bz2'], _unpack_tarfile, [],
                                "bzip2'ed tar-file")


def _find_unpack_format(filename):
    for name, info in _UNPACK_FORMATS.items():
        for extension in info[0]:
            if filename.endswith(extension):
                return name
    return None


def unpack_archive(filename, extract_dir=None, format=None):
    """Unpack an archive.

    `filename` is the name of the archive.

    `extract_dir` is the name of the target directory, where the archive
    is unpacked. If not provided, the current working directory is used.

    `format` is the archive format: one of "zip", "tar", or "gztar". Or any
    other registered format. If not provided, unpack_archive will use the
    filename extension and see if an unpacker was registered for that
    extension.

    In case none is found, a ValueError is raised.
    """
    if extract_dir is None:
        extract_dir = os.getcwd()

    if format is not None:
        try:
            format_info = _UNPACK_FORMATS[format]
        except KeyError:
            raise ValueError("Unknown unpack format '{0}'".format(format))

        func = format_info[0]
        func(filename, extract_dir, **dict(format_info[1]))
    else:
        # we need to look at the registered unpackers supported extensions
        format = _find_unpack_format(filename)
        if format is None:
            raise ReadError("Unknown archive format '{0}'".format(filename))

        func = _UNPACK_FORMATS[format][1]
        kwargs = dict(_UNPACK_FORMATS[format][2])
        func(filename, extract_dir, **kwargs)


def sdist2rpm(sdist, dist_dir=None, version=None):
    """Creates a RPM distro out of a Python project."""
    old_dir = os.getcwd()
    if dist_dir is None:
        dist_dir = old_dir

    if os.path.isfile(sdist):
        tempdir = get_temp_dir()
        os.chdir(tempdir)
        unpack_archive(sdist, extract_dir=tempdir)
        sdist = os.listdir(os.curdir)[0]
    else:
        tempdir = None

    if version is None:
        version = ''

    os.chdir(sdist)
    try:
        if not _is_d2():
            _d1_sdist2rpm(dist_dir)
        else:
            _d2_sdist2rpm(dist_dir)

        if dist_dir is None:
            dist_dir = old_dir

        # looking for a file named sdist.arch.rpm
        name = sdist.lower()
        if not name.startswith('python'):
            name = '%s-%s' % (_PYTHON, name)
        elif name.startswith('python-'):
            name = '%s-%s' % (_PYTHON, name[len('python-'):])

        found = []
        for file_ in os.listdir(dist_dir):
            if file_.startswith(name):
                found.append(os.path.join(dist_dir, file_))

        if len(found) > 1:
            # preferring noarch
            for rel in found:
                if 'noarch' in found:
                    return rel
        else:
            return found[0]
    finally:
        os.chdir(old_dir)
        if tempdir is not None and os.path.exists(tempdir):
            shutil.rmtree(tempdir)


_PREDICATE = re.compile(r"(?i)^\s*([a-z_][\sa-z0-9A-Z_-]"
                         "*(?:\.[a-z_]\w*)*)(.*)")
distutils2.version._PREDICATE = _PREDICATE


def main(project, dist_dir, version, index_url, download_cache):
    if os.path.isfile(project) or os.path.isdir(project):
        project = os.path.abspath(project)

    release = get_release(project, version, index_url, download_cache)
    if release is None:
        return 1

    try:
        res = sdist2rpm(release, dist_dir, version)
        if res is None:
            print 'Failed.'
            return 1
        print '%s written' % res
        return 0
    finally:
        if os.path.isdir(project):
            return

        if download_cache is None:
            if os.path.isfile(project):
                return
            shutil.rmtree(os.path.dirname(release))


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--dist-dir', type=str, default=None,
                        help='target directory for RPM files')
    parser.add_argument('--version', type=str, default=None,
                        help='version to build')
    parser.add_argument('--index', type=str, default=DEFAULT_SIMPLE_INDEX_URL,
                        help='PyPI Simple Index')
    parser.add_argument('--download-cache', type=str, default=None,
                        help='Download cache')
    parser.add_argument('project', help='project name at PyPI or path')
    args = parser.parse_args()
    sys.exit(main(args.project, args.dist_dir, args.version, args.index,
                  args.download_cache))
