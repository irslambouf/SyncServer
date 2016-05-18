"""distutils.util

Miscellaneous utility functions.
"""


import os
import posixpath
import re
import string
import sys
import shutil
import tarfile
import zipfile
from copy import copy
from fnmatch import fnmatchcase
from ConfigParser import RawConfigParser

from distutils2.errors import (DistutilsPlatformError, DistutilsFileError,
                               DistutilsByteCompileError, DistutilsExecError)
from distutils2 import log
from distutils2._backport import sysconfig as _sysconfig

_PLATFORM = None


def newer(source, target):
    """Tells if the target is newer than the source.

    Return true if 'source' exists and is more recently modified than
    'target', or if 'source' exists and 'target' doesn't.

    Return false if both exist and 'target' is the same age or younger
    than 'source'. Raise DistutilsFileError if 'source' does not exist.

    Note that this test is not very accurate: files created in the same second
    will have the same "age".
    """
    if not os.path.exists(source):
        raise DistutilsFileError("file '%s' does not exist" %
                                 os.path.abspath(source))
    if not os.path.exists(target):
        return True

    return os.stat(source).st_mtime > os.stat(target).st_mtime


def get_platform():
    """Return a string that identifies the current platform.

    By default, will return the value returned by sysconfig.get_platform(),
    but it can be changed by calling set_platform().
    """
    global _PLATFORM
    if _PLATFORM is None:
        _PLATFORM = _sysconfig.get_platform()
    return _PLATFORM


def set_platform(identifier):
    """Sets the platform string identifier returned by get_platform().

    Note that this change doesn't impact the value returned by
    sysconfig.get_platform() and is local to Distutils
    """
    global _PLATFORM
    _PLATFORM = identifier


def convert_path(pathname):
    """Return 'pathname' as a name that will work on the native filesystem.

    i.e. split it on '/' and put it back together again using the current
    directory separator.  Needed because filenames in the setup script are
    always supplied in Unix style, and have to be converted to the local
    convention before we can actually use them in the filesystem.  Raises
    ValueError on non-Unix-ish systems if 'pathname' either starts or
    ends with a slash.
    """
    if os.sep == '/':
        return pathname
    if not pathname:
        return pathname
    if pathname[0] == '/':
        raise ValueError("path '%s' cannot be absolute" % pathname)
    if pathname[-1] == '/':
        raise ValueError("path '%s' cannot end with '/'" % pathname)

    paths = pathname.split('/')
    while os.curdir in paths:
        paths.remove(os.curdir)
    if not paths:
        return os.curdir
    return os.path.join(*paths)


def change_root(new_root, pathname):
    """Return 'pathname' with 'new_root' prepended.

    If 'pathname' is relative, this is equivalent to
    "os.path.join(new_root,pathname)".
    Otherwise, it requires making 'pathname' relative and then joining the
    two, which is tricky on DOS/Windows and Mac OS.
    """
    if os.name == 'posix':
        if not os.path.isabs(pathname):
            return os.path.join(new_root, pathname)
        else:
            return os.path.join(new_root, pathname[1:])

    elif os.name == 'nt':
        (drive, path) = os.path.splitdrive(pathname)
        if path[0] == '\\':
            path = path[1:]
        return os.path.join(new_root, path)

    elif os.name == 'os2':
        (drive, path) = os.path.splitdrive(pathname)
        if path[0] == os.sep:
            path = path[1:]
        return os.path.join(new_root, path)

    else:
        raise DistutilsPlatformError("nothing known about "
                                     "platform '%s'" % os.name)

_environ_checked = 0


def check_environ():
    """Ensure that 'os.environ' has all the environment variables needed.

    We guarantee that users can use in config files, command-line options,
    etc.  Currently this includes:
      HOME - user's home directory (Unix only)
      PLAT - description of the current platform, including hardware
             and OS (see 'get_platform()')
    """
    global _environ_checked
    if _environ_checked:
        return

    if os.name == 'posix' and 'HOME' not in os.environ:
        import pwd
        os.environ['HOME'] = pwd.getpwuid(os.getuid())[5]

    if 'PLAT' not in os.environ:
        os.environ['PLAT'] = _sysconfig.get_platform()

    _environ_checked = 1


def subst_vars(s, local_vars):
    """Perform shell/Perl-style variable substitution on 'string'.

    Every occurrence of '$' followed by a name is considered a variable, and
    variable is substituted by the value found in the 'local_vars'
    dictionary, or in 'os.environ' if it's not in 'local_vars'.
    'os.environ' is first checked/augmented to guarantee that it contains
    certain values: see 'check_environ()'.  Raise ValueError for any
    variables not found in either 'local_vars' or 'os.environ'.
    """
    check_environ()

    def _subst(match, local_vars=local_vars):
        var_name = match.group(1)
        if var_name in local_vars:
            return str(local_vars[var_name])
        else:
            return os.environ[var_name]

    try:
        return re.sub(r'\$([a-zA-Z_][a-zA-Z_0-9]*)', _subst, s)
    except KeyError, var:
        raise ValueError("invalid variable '$%s'" % var)


def grok_environment_error(exc, prefix="error: "):
    """Generate a useful error message from an EnvironmentError.

    This will generate an IOError or an OSError exception object.
    Handles Python 1.5.1 and 1.5.2 styles, and
    does what it can to deal with exception objects that don't have a
    filename (which happens when the error is due to a two-file operation,
    such as 'rename()' or 'link()'.  Returns the error message as a string
    prefixed with 'prefix'.
    """
    # check for Python 1.5.2-style {IO,OS}Error exception objects
    if hasattr(exc, 'filename') and hasattr(exc, 'strerror'):
        if exc.filename:
            error = prefix + "%s: %s" % (exc.filename, exc.strerror)
        else:
            # two-argument functions in posix module don't
            # include the filename in the exception object!
            error = prefix + "%s" % exc.strerror
    else:
        error = prefix + str(exc[-1])

    return error

# Needed by 'split_quoted()'
_wordchars_re = _squote_re = _dquote_re = None


def _init_regex():
    global _wordchars_re, _squote_re, _dquote_re
    _wordchars_re = re.compile(r'[^\\\'\"%s ]*' % string.whitespace)
    _squote_re = re.compile(r"'(?:[^'\\]|\\.)*'")
    _dquote_re = re.compile(r'"(?:[^"\\]|\\.)*"')


def split_quoted(s):
    """Split a string up according to Unix shell-like rules for quotes and
    backslashes.

    In short: words are delimited by spaces, as long as those
    spaces are not escaped by a backslash, or inside a quoted string.
    Single and double quotes are equivalent, and the quote characters can
    be backslash-escaped.  The backslash is stripped from any two-character
    escape sequence, leaving only the escaped character.  The quote
    characters are stripped from any quoted string.  Returns a list of
    words.
    """
    # This is a nice algorithm for splitting up a single string, since it
    # doesn't require character-by-character examination.  It was a little
    # bit of a brain-bender to get it working right, though...
    if _wordchars_re is None:
        _init_regex()

    s = s.strip()
    words = []
    pos = 0

    while s:
        m = _wordchars_re.match(s, pos)
        end = m.end()
        if end == len(s):
            words.append(s[:end])
            break

        if s[end] in string.whitespace: # unescaped, unquoted whitespace: now
            words.append(s[:end])       # we definitely have a word delimiter
            s = s[end:].lstrip()
            pos = 0

        elif s[end] == '\\':            # preserve whatever is being escaped;
                                        # will become part of the current word
            s = s[:end] + s[end + 1:]
            pos = end + 1

        else:
            if s[end] == "'":           # slurp singly-quoted string
                m = _squote_re.match(s, end)
            elif s[end] == '"':         # slurp doubly-quoted string
                m = _dquote_re.match(s, end)
            else:
                raise RuntimeError("this can't happen "
                                   "(bad char '%c')" % s[end])

            if m is None:
                raise ValueError("bad string (mismatched %s quotes?)" % s[end])

            (beg, end) = m.span()
            s = s[:beg] + s[beg + 1:end - 1] + s[end:]
            pos = m.end() - 2

        if pos >= len(s):
            words.append(s)
            break

    return words


def execute(func, args, msg=None, verbose=0, dry_run=0):
    """Perform some action that affects the outside world.

    eg. by writing to the filesystem).  Such actions are special because
    they are disabled by the 'dry_run' flag.  This method takes care of all
    that bureaucracy for you; all you have to do is supply the
    function to call and an argument tuple for it (to embody the
    "external action" being performed), and an optional message to
    print.
    """
    if msg is None:
        msg = "%s%r" % (func.__name__, args)
        if msg[-2:] == ',)':        # correct for singleton tuple
            msg = msg[0:-2] + ')'

    log.info(msg)
    if not dry_run:
        func(*args)


def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))


def byte_compile(py_files, optimize=0, force=0, prefix=None, base_dir=None,
                  verbose=1, dry_run=0, direct=None):
    """Byte-compile a collection of Python source files to either .pyc
    or .pyo files in the same directory.

    'py_files' is a list of files to compile; any files that don't end in
    ".py" are silently skipped. 'optimize' must be one of the following:
      0 - don't optimize (generate .pyc)
      1 - normal optimization (like "python -O")
      2 - extra optimization (like "python -OO")
    If 'force' is true, all files are recompiled regardless of
    timestamps.

    The source filename encoded in each bytecode file defaults to the
    filenames listed in 'py_files'; you can modify these with 'prefix' and
    'basedir'.  'prefix' is a string that will be stripped off of each
    source filename, and 'base_dir' is a directory name that will be
    prepended (after 'prefix' is stripped).  You can supply either or both
    (or neither) of 'prefix' and 'base_dir', as you wish.

    If 'dry_run' is true, doesn't actually do anything that would
    affect the filesystem.

    Byte-compilation is either done directly in this interpreter process
    with the standard py_compile module, or indirectly by writing a
    temporary script and executing it.  Normally, you should let
    'byte_compile()' figure out to use direct compilation or not (see
    the source for details).  The 'direct' flag is used by the script
    generated in indirect mode; unless you know what you're doing, leave
    it set to None.
    """
    # nothing is done if sys.dont_write_bytecode is True
    if hasattr(sys, 'dont_write_bytecode') and sys.dont_write_bytecode:
        raise DistutilsByteCompileError('byte-compiling is disabled.')

    # First, if the caller didn't force us into direct or indirect mode,
    # figure out which mode we should be in.  We take a conservative
    # approach: choose direct mode *only* if the current interpreter is
    # in debug mode and optimize is 0.  If we're not in debug mode (-O
    # or -OO), we don't know which level of optimization this
    # interpreter is running with, so we can't do direct
    # byte-compilation and be certain that it's the right thing.  Thus,
    # always compile indirectly if the current interpreter is in either
    # optimize mode, or if either optimization level was requested by
    # the caller.
    if direct is None:
        direct = (__debug__ and optimize == 0)

    # "Indirect" byte-compilation: write a temporary script and then
    # run it with the appropriate flags.
    if not direct:
        from tempfile import mkstemp
        script_fd, script_name = mkstemp(".py")
        log.info("writing byte-compilation script '%s'", script_name)
        if not dry_run:
            if script_fd is not None:
                script = os.fdopen(script_fd, "w")
            else:
                script = open(script_name, "w")

            try:
                script.write("""\
from distutils2.util import byte_compile
files = [
""")

                # XXX would be nice to write absolute filenames, just for
                # safety's sake (script should be more robust in the face of
                # chdir'ing before running it).  But this requires abspath'ing
                # 'prefix' as well, and that breaks the hack in build_lib's
                # 'byte_compile()' method that carefully tacks on a trailing
                # slash (os.sep really) to make sure the prefix here is "just
                # right".  This whole prefix business is rather delicate -- the
                # problem is that it's really a directory, but I'm treating it
                # as a dumb string, so trailing slashes and so forth matter.

                #py_files = map(os.path.abspath, py_files)
                #if prefix:
                #    prefix = os.path.abspath(prefix)

                script.write(",\n".join(map(repr, py_files)) + "]\n")
                script.write("""
byte_compile(files, optimize=%r, force=%r,
             prefix=%r, base_dir=%r,
             verbose=%r, dry_run=0,
             direct=1)
""" % (optimize, force, prefix, base_dir, verbose))

            finally:
                script.close()

        cmd = [sys.executable, script_name]
        if optimize == 1:
            cmd.insert(1, "-O")
        elif optimize == 2:
            cmd.insert(1, "-OO")

        env = copy(os.environ)
        env['PYTHONPATH'] = ':'.join(sys.path)
        try:
            spawn(cmd, dry_run=dry_run, env=env)
        finally:
            execute(os.remove, (script_name,), "removing %s" % script_name,
                    dry_run=dry_run)

    # "Direct" byte-compilation: use the py_compile module to compile
    # right here, right now.  Note that the script generated in indirect
    # mode simply calls 'byte_compile()' in direct mode, a weird sort of
    # cross-process recursion.  Hey, it works!
    else:
        from py_compile import compile

        for file in py_files:
            if file[-3:] != ".py":
                # This lets us be lazy and not filter filenames in
                # the "install_lib" command.
                continue

            # Terminology from the py_compile module:
            #   cfile - byte-compiled file
            #   dfile - purported source filename (same as 'file' by default)
            cfile = file + (__debug__ and "c" or "o")
            dfile = file
            if prefix:
                if file[:len(prefix)] != prefix:
                    raise ValueError("invalid prefix: filename %r doesn't "
                                     "start with %r" % (file, prefix))
                dfile = dfile[len(prefix):]
            if base_dir:
                dfile = os.path.join(base_dir, dfile)

            cfile_base = os.path.basename(cfile)
            if direct:
                if force or newer(file, cfile):
                    log.info("byte-compiling %s to %s", file, cfile_base)
                    if not dry_run:
                        compile(file, cfile, dfile)
                else:
                    log.debug("skipping byte-compilation of %s to %s",
                              file, cfile_base)


def rfc822_escape(header):
    """Return a version of the string escaped for inclusion in an
    RFC-822 header, by ensuring there are 8 spaces space after each newline.
    """
    lines = header.split('\n')
    sep = '\n' + 8 * ' '
    return sep.join(lines)

_RE_VERSION = re.compile('(\d+\.\d+(\.\d+)*)')
_MAC_OS_X_LD_VERSION = re.compile('^@\(#\)PROGRAM:ld  '
                                  'PROJECT:ld64-((\d+)(\.\d+)*)')


def _find_ld_version():
    """Finds the ld version. The version scheme differs under Mac OSX."""
    if sys.platform == 'darwin':
        return _find_exe_version('ld -v', _MAC_OS_X_LD_VERSION)
    else:
        return _find_exe_version('ld -v')


def _find_exe_version(cmd, pattern=_RE_VERSION):
    """Find the version of an executable by running `cmd` in the shell.

    `pattern` is a compiled regular expression. If not provided, default
    to _RE_VERSION. If the command is not found, or the output does not
    match the mattern, returns None.
    """
    from subprocess import Popen, PIPE
    executable = cmd.split()[0]
    if find_executable(executable) is None:
        return None
    pipe = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    try:
        stdout, stderr = pipe.stdout.read(), pipe.stderr.read()
    finally:
        pipe.stdout.close()
        pipe.stderr.close()
    # some commands like ld under MacOS X, will give the
    # output in the stderr, rather than stdout.
    if stdout != '':
        out_string = stdout
    else:
        out_string = stderr

    result = pattern.search(out_string)
    if result is None:
        return None
    return result.group(1)


def get_compiler_versions():
    """Returns a tuple providing the versions of gcc, ld and dllwrap

    For each command, if a command is not found, None is returned.
    Otherwise a string with the version is returned.
    """
    gcc = _find_exe_version('gcc -dumpversion')
    ld = _find_ld_version()
    dllwrap = _find_exe_version('dllwrap --version')
    return gcc, ld, dllwrap


def newer_group(sources, target, missing='error'):
    """Return true if 'target' is out-of-date with respect to any file
    listed in 'sources'.

    In other words, if 'target' exists and is newer
    than every file in 'sources', return false; otherwise return true.
    'missing' controls what we do when a source file is missing; the
    default ("error") is to blow up with an OSError from inside 'stat()';
    if it is "ignore", we silently drop any missing source files; if it is
    "newer", any missing source files make us assume that 'target' is
    out-of-date (this is handy in "dry-run" mode: it'll make you pretend to
    carry out commands that wouldn't work because inputs are missing, but
    that doesn't matter because you're not actually going to run the
    commands).
    """
    # If the target doesn't even exist, then it's definitely out-of-date.
    if not os.path.exists(target):
        return True

    # Otherwise we have to find out the hard way: if *any* source file
    # is more recent than 'target', then 'target' is out-of-date and
    # we can immediately return true.  If we fall through to the end
    # of the loop, then 'target' is up-to-date and we return false.
    target_mtime = os.stat(target).st_mtime

    for source in sources:
        if not os.path.exists(source):
            if missing == 'error':      # blow up when we stat() the file
                pass
            elif missing == 'ignore':   # missing source dropped from
                continue                #  target's dependency list
            elif missing == 'newer':    # missing source means target is
                return True             #  out-of-date

        if os.stat(source).st_mtime > target_mtime:
            return True

    return False


def write_file(filename, contents):
    """Create a file with the specified name and write 'contents' (a
    sequence of strings without line terminators) to it.
    """
    try:
        f = open(filename, "w")
        for line in contents:
            f.write(line + "\n")
    finally:
        f.close()


def _is_package(path):
    """Returns True if path is a package (a dir with an __init__ file."""
    if not os.path.isdir(path):
        return False
    return os.path.isfile(os.path.join(path, '__init__.py'))


def _under(path, root):
    path = path.split(os.sep)
    root = root.split(os.sep)
    if len(root) > len(path):
        return False
    for pos, part in enumerate(root):
        if path[pos] != part:
            return False
    return True


def _package_name(root_path, path):
    """Returns a dotted package name, given a subpath."""
    if not _under(path, root_path):
        raise ValueError('"%s" is not a subpath of "%s"' % (path, root_path))
    return path[len(root_path) + 1:].replace(os.sep, '.')


def find_packages(paths=(os.curdir,), exclude=()):
    """Return a list all Python packages found recursively within
    directories 'paths'

    'paths' should be supplied as a sequence of "cross-platform"
    (i.e. URL-style) path; it will be converted to the appropriate local
    path syntax.

    'exclude' is a sequence of package names to exclude; '*' can be used as
    a wildcard in the names, such that 'foo.*' will exclude all subpackages
    of 'foo' (but not 'foo' itself).
    """
    packages = []
    discarded = []

    def _discarded(path):
        for discard in discarded:
            if _under(path, discard):
                return True
        return False

    for path in paths:
        path = convert_path(path)
        for root, dirs, files in os.walk(path):
            for dir_ in dirs:
                fullpath = os.path.join(root, dir_)
                if _discarded(fullpath):
                    continue
                # we work only with Python packages
                if not _is_package(fullpath):
                    discarded.append(fullpath)
                    continue
                # see if it's excluded
                excluded = False
                package_name = _package_name(path, fullpath)
                for pattern in exclude:
                    if fnmatchcase(package_name, pattern):
                        excluded = True
                        break
                if excluded:
                    continue

                # adding it to the list
                packages.append(package_name)
    return packages

def resolve_name(name):
    """Resolve a name like ``module.object`` to an object and return it.

    Raise ImportError if the module or name is not found.
    """
    parts = name.split('.')
    cursor = len(parts)
    module_name, rest = parts[:cursor], parts[cursor:]

    while cursor > 0:
        try:
            ret = __import__('.'.join(module_name))
            break
        except ImportError:
            if cursor == 0:
                raise
            cursor -= 1
            module_name = parts[:cursor]
            rest = parts[cursor:]
            ret = ''

    for part in parts[1:]:
        try:
            ret = getattr(ret, part)
        except AttributeError:
            raise ImportError

    return ret

def splitext(path):
    """Like os.path.splitext, but take off .tar too"""
    base, ext = posixpath.splitext(path)
    if base.lower().endswith('.tar'):
        ext = base[-4:] + ext
        base = base[:-4]
    return base, ext


def unzip_file(filename, location, flatten=True):
    """Unzip the file (zip file located at filename) to the destination
    location"""
    if not os.path.exists(location):
        os.makedirs(location)
    zipfp = open(filename, 'rb')
    try:
        zip = zipfile.ZipFile(zipfp)
        leading = has_leading_dir(zip.namelist()) and flatten
        for name in zip.namelist():
            data = zip.read(name)
            fn = name
            if leading:
                fn = split_leading_dir(name)[1]
            fn = os.path.join(location, fn)
            dir = os.path.dirname(fn)
            if not os.path.exists(dir):
                os.makedirs(dir)
            if fn.endswith('/') or fn.endswith('\\'):
                # A directory
                if not os.path.exists(fn):
                    os.makedirs(fn)
            else:
                fp = open(fn, 'wb')
                try:
                    fp.write(data)
                finally:
                    fp.close()
    finally:
        zipfp.close()


def untar_file(filename, location):
    """Untar the file (tar file located at filename) to the destination
    location
    """
    if not os.path.exists(location):
        os.makedirs(location)
    if filename.lower().endswith('.gz') or filename.lower().endswith('.tgz'):
        mode = 'r:gz'
    elif (filename.lower().endswith('.bz2')
          or filename.lower().endswith('.tbz')):
        mode = 'r:bz2'
    elif filename.lower().endswith('.tar'):
        mode = 'r'
    else:
        mode = 'r:*'
    tar = tarfile.open(filename, mode)
    try:
        leading = has_leading_dir([member.name for member in tar.getmembers()])
        for member in tar.getmembers():
            fn = member.name
            if leading:
                fn = split_leading_dir(fn)[1]
            path = os.path.join(location, fn)
            if member.isdir():
                if not os.path.exists(path):
                    os.makedirs(path)
            else:
                try:
                    fp = tar.extractfile(member)
                except (KeyError, AttributeError), e:
                    # Some corrupt tar files seem to produce this
                    # (specifically bad symlinks)
                    continue
                if not os.path.exists(os.path.dirname(path)):
                    os.makedirs(os.path.dirname(path))
                destfp = open(path, 'wb')
                try:
                    shutil.copyfileobj(fp, destfp)
                finally:
                    destfp.close()
                fp.close()
    finally:
        tar.close()


def has_leading_dir(paths):
    """Returns true if all the paths have the same leading path name
    (i.e., everything is in one subdirectory in an archive)"""
    common_prefix = None
    for path in paths:
        prefix, rest = split_leading_dir(path)
        if not prefix:
            return False
        elif common_prefix is None:
            common_prefix = prefix
        elif prefix != common_prefix:
            return False
    return True


def split_leading_dir(path):
    path = str(path)
    path = path.lstrip('/').lstrip('\\')
    if '/' in path and (('\\' in path and path.find('/') < path.find('\\'))
                        or '\\' not in path):
        return path.split('/', 1)
    elif '\\' in path:
        return path.split('\\', 1)
    else:
        return path, ''


def spawn(cmd, search_path=1, verbose=0, dry_run=0, env=None):
    """Run another program specified as a command list 'cmd' in a new process.

    'cmd' is just the argument list for the new process, ie.
    cmd[0] is the program to run and cmd[1:] are the rest of its arguments.
    There is no way to run a program with a name different from that of its
    executable.

    If 'search_path' is true (the default), the system's executable
    search path will be used to find the program; otherwise, cmd[0]
    must be the exact path to the executable.  If 'dry_run' is true,
    the command will not actually be run.

    If 'env' is given, it's a environment dictionary used for the execution
    environment.

    Raise DistutilsExecError if running the program fails in any way; just
    return on success.
    """
    if os.name == 'posix':
        _spawn_posix(cmd, search_path, dry_run=dry_run, env=env)
    elif os.name == 'nt':
        _spawn_nt(cmd, search_path, dry_run=dry_run, env=env)
    elif os.name == 'os2':
        _spawn_os2(cmd, search_path, dry_run=dry_run, env=env)
    else:
        raise DistutilsPlatformError(
              "don't know how to spawn programs on platform '%s'" % os.name)


def _nt_quote_args(args):
    """Quote command-line arguments for DOS/Windows conventions.

    Just wraps every argument which contains blanks in double quotes, and
    returns a new argument list.
    """
    # XXX this doesn't seem very robust to me -- but if the Windows guys
    # say it'll work, I guess I'll have to accept it.  (What if an arg
    # contains quotes?  What other magic characters, other than spaces,
    # have to be escaped?  Is there an escaping mechanism other than
    # quoting?)
    for i, arg in enumerate(args):
        if ' ' in arg:
            args[i] = '"%s"' % arg
    return args


def _spawn_nt(cmd, search_path=1, verbose=0, dry_run=0, env=None):
    executable = cmd[0]
    cmd = _nt_quote_args(cmd)
    if search_path:
        # either we find one or it stays the same
        executable = find_executable(executable) or executable
    log.info(' '.join([executable] + cmd[1:]))
    if not dry_run:
        # spawn for NT requires a full path to the .exe
        try:
            if env is None:
                rc = os.spawnv(os.P_WAIT, executable, cmd)
            else:
                rc = os.spawnve(os.P_WAIT, executable, cmd, env)

        except OSError, exc:
            # this seems to happen when the command isn't found
            raise DistutilsExecError(
                  "command '%s' failed: %s" % (cmd[0], exc[-1]))
        if rc != 0:
            # and this reflects the command running but failing
            raise DistutilsExecError(
                  "command '%s' failed with exit status %d" % (cmd[0], rc))


def _spawn_os2(cmd, search_path=1, verbose=0, dry_run=0, env=None):
    executable = cmd[0]
    if search_path:
        # either we find one or it stays the same
        executable = find_executable(executable) or executable
    log.info(' '.join([executable] + cmd[1:]))
    if not dry_run:
        # spawnv for OS/2 EMX requires a full path to the .exe
        try:
            if env is None:
                rc = os.spawnv(os.P_WAIT, executable, cmd)
            else:
                rc = os.spawnve(os.P_WAIT, executable, cmd, env)

        except OSError, exc:
            # this seems to happen when the command isn't found
            raise DistutilsExecError(
                  "command '%s' failed: %s" % (cmd[0], exc[-1]))
        if rc != 0:
            # and this reflects the command running but failing
            log.debug("command '%s' failed with exit status %d" % (cmd[0], rc))
            raise DistutilsExecError(
                  "command '%s' failed with exit status %d" % (cmd[0], rc))


def _spawn_posix(cmd, search_path=1, verbose=0, dry_run=0, env=None):
    log.info(' '.join(cmd))
    if dry_run:
        return

    if env is None:
        exec_fn = search_path and os.execvp or os.execv
    else:
        exec_fn = search_path and os.execvpe or os.execve

    pid = os.fork()

    if pid == 0:  # in the child
        try:
            if env is None:
                exec_fn(cmd[0], cmd)
            else:
                exec_fn(cmd[0], cmd, env)
        except OSError, e:
            sys.stderr.write("unable to execute %s: %s\n" %
                             (cmd[0], e.strerror))
            os._exit(1)

        sys.stderr.write("unable to execute %s for unknown reasons" % cmd[0])
        os._exit(1)
    else:   # in the parent
        # Loop until the child either exits or is terminated by a signal
        # (ie. keep waiting if it's merely stopped)
        while 1:
            try:
                pid, status = os.waitpid(pid, 0)
            except OSError, exc:
                import errno
                if exc.errno == errno.EINTR:
                    continue
                raise DistutilsExecError(
                      "command '%s' failed: %s" % (cmd[0], exc[-1]))
            if os.WIFSIGNALED(status):
                raise DistutilsExecError(
                      "command '%s' terminated by signal %d" % \
                      (cmd[0], os.WTERMSIG(status)))

            elif os.WIFEXITED(status):
                exit_status = os.WEXITSTATUS(status)
                if exit_status == 0:
                    return   # hey, it succeeded!
                else:
                    raise DistutilsExecError(
                          "command '%s' failed with exit status %d" % \
                          (cmd[0], exit_status))

            elif os.WIFSTOPPED(status):
                continue

            else:
                raise DistutilsExecError(
                      "unknown error executing '%s': termination status %d" % \
                      (cmd[0], status))


def find_executable(executable, path=None):
    """Tries to find 'executable' in the directories listed in 'path'.

    A string listing directories separated by 'os.pathsep'; defaults to
    os.environ['PATH'].  Returns the complete filename or None if not found.
    """
    if path is None:
        path = os.environ['PATH']
    paths = path.split(os.pathsep)
    base, ext = os.path.splitext(executable)

    if (sys.platform == 'win32' or os.name == 'os2') and (ext != '.exe'):
        executable = executable + '.exe'

    if not os.path.isfile(executable):
        for p in paths:
            f = os.path.join(p, executable)
            if os.path.isfile(f):
                # the file exists, we have a shot at spawn working
                return f
        return None
    else:
        return executable


DEFAULT_REPOSITORY = 'http://pypi.python.org/pypi'
DEFAULT_REALM = 'pypi'
DEFAULT_PYPIRC = """\
[distutils]
index-servers =
    pypi

[pypi]
username:%s
password:%s
"""

def get_pypirc_path():
    """Returns rc file path."""
    return os.path.join(os.path.expanduser('~'), '.pypirc')


def generate_pypirc(username, password):
    """Creates a default .pypirc file."""
    rc = get_pypirc_path()
    f = open(rc, 'w')
    try:
        f.write(DEFAULT_PYPIRC % (username, password))
    finally:
        f.close()
    try:
        os.chmod(rc, 0600)
    except OSError:
        # should do something better here
        pass


def read_pypirc(repository=DEFAULT_REPOSITORY, realm=DEFAULT_REALM):
    """Reads the .pypirc file."""
    rc = get_pypirc_path()
    if os.path.exists(rc):
        config = RawConfigParser()
        config.read(rc)
        sections = config.sections()
        if 'distutils' in sections:
            # let's get the list of servers
            index_servers = config.get('distutils', 'index-servers')
            _servers = [server.strip() for server in
                        index_servers.split('\n')
                        if server.strip() != '']
            if _servers == []:
                # nothing set, let's try to get the default pypi
                if 'pypi' in sections:
                    _servers = ['pypi']
                else:
                    # the file is not properly defined, returning
                    # an empty dict
                    return {}
            for server in _servers:
                current = {'server': server}
                current['username'] = config.get(server, 'username')

                # optional params
                for key, default in (('repository',
                                       DEFAULT_REPOSITORY),
                                     ('realm', DEFAULT_REALM),
                                     ('password', None)):
                    if config.has_option(server, key):
                        current[key] = config.get(server, key)
                    else:
                        current[key] = default
                if (current['server'] == repository or
                    current['repository'] == repository):
                    return current
        elif 'server-login' in sections:
            # old format
            server = 'server-login'
            if config.has_option(server, 'repository'):
                repository = config.get(server, 'repository')
            else:
                repository = DEFAULT_REPOSITORY

            return {'username': config.get(server, 'username'),
                    'password': config.get(server, 'password'),
                    'repository': repository,
                    'server': server,
                    'realm': DEFAULT_REALM}

    return {}


def metadata_to_dict(meta):
    """XXX might want to move it to the Metadata class."""
    data = {
        'metadata_version' : meta.version,
        'name': meta['Name'],
        'version': meta['Version'],
        'summary': meta['Summary'],
        'home_page': meta['Home-page'],
        'author': meta['Author'],
        'author_email': meta['Author-email'],
        'license': meta['License'],
        'description': meta['Description'],
        'keywords': meta['Keywords'],
        'platform': meta['Platform'],
        'classifier': meta['Classifier'],
        'download_url': meta['Download-URL'],
    }

    if meta.version == '1.2':
        data['requires_dist'] = meta['Requires-Dist']
        data['requires_python'] = meta['Requires-Python']
        data['requires_external'] = meta['Requires-External']
        data['provides_dist'] = meta['Provides-Dist']
        data['obsoletes_dist'] = meta['Obsoletes-Dist']
        data['project_url'] = [','.join(url) for url in
                                meta['Project-URL']]

    elif meta.version == '1.1':
        data['provides'] = meta['Provides']
        data['requires'] = meta['Requires']
        data['obsoletes'] = meta['Obsoletes']

    return data

# utility functions for 2to3 support

def run_2to3(files, doctests_only=False, fixer_names=None, options=None,
                                                                explicit=None):
    """ Wrapper function around the refactor() class which
    performs the conversions on a list of python files.
    Invoke 2to3 on a list of Python files. The files should all come
    from the build area, as the modification is done in-place."""

    #if not files:
    #    return

    # Make this class local, to delay import of 2to3
    from lib2to3.refactor import get_fixers_from_package, RefactoringTool
    fixers = []
    fixers = get_fixers_from_package('lib2to3.fixes')


    if fixer_names:
        for fixername in fixer_names:
            fixers.extend([fixer for fixer in get_fixers_from_package(fixername)])
    r = RefactoringTool(fixers, options=options)
    if doctests_only:
        r.refactor(files, doctests_only=True, write=True)
    else:
        r.refactor(files, write=True)

class Mixin2to3:
    """ Wrapper class for commands that run 2to3.
    To configure 2to3, setup scripts may either change
    the class variables, or inherit from this class
    to override how 2to3 is invoked.
    """
    # provide list of fixers to run.
    # defaults to all from lib2to3.fixers
    fixer_names = None

    # options dictionary
    options = None

    # list of fixers to invoke even though they are marked as explicit
    explicit = None

    def run_2to3(self, files, doctests_only=False):
        """ Issues a call to util.run_2to3. """
        return run_2to3(files, doctests_only, self.fixer_names,
                        self.options, self.explicit)
