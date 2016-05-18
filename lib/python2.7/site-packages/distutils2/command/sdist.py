"""distutils.command.sdist

Implements the Distutils 'sdist' command (create a source distribution)."""


import os
import string
import sys
from glob import glob
from warnings import warn
from shutil import rmtree
import re

try:
    from shutil import get_archive_formats
except ImportError:
    from distutils2._backport.shutil import get_archive_formats

from distutils2.core import Command
from distutils2.errors import (DistutilsPlatformError, DistutilsOptionError,
                               DistutilsTemplateError)
from distutils2.manifest import Manifest
from distutils2 import log
from distutils2.util import convert_path

def show_formats():
    """Print all possible values for the 'formats' option (used by
    the "--help-formats" command-line option).
    """
    from distutils2.fancy_getopt import FancyGetopt
    formats = []
    for name, desc in get_archive_formats():
        formats.append(("formats=" + name, None, desc))
    formats.sort()
    FancyGetopt(formats).print_help(
        "List of available source distribution formats:")

# a \ followed by some spaces + EOL
_COLLAPSE_PATTERN = re.compile('\\\w\n', re.M)
_COMMENTED_LINE = re.compile('^#.*\n$|^\w*\n$', re.M)

class sdist(Command):

    description = "create a source distribution (tarball, zip file, etc.)"

    user_options = [
        ('template=', 't',
         "name of manifest template file [default: MANIFEST.in]"),
        ('manifest=', 'm',
         "name of manifest file [default: MANIFEST]"),
        ('use-defaults', None,
         "include the default file set in the manifest "
         "[default; disable with --no-defaults]"),
        ('no-defaults', None,
         "don't include the default file set"),
        ('prune', None,
         "specifically exclude files/directories that should not be "
         "distributed (build tree, RCS/CVS dirs, etc.) "
         "[default; disable with --no-prune]"),
        ('no-prune', None,
         "don't automatically exclude anything"),
        ('manifest-only', 'o',
         "just regenerate the manifest and then stop "),
        ('formats=', None,
         "formats for source distribution (comma-separated list)"),
        ('keep-temp', 'k',
         "keep the distribution tree around after creating " +
         "archive file(s)"),
        ('dist-dir=', 'd',
         "directory to put the source distribution archive(s) in "
         "[default: dist]"),
        ('check-metadata', None,
         "Ensure that all required elements of metadata "
         "are supplied. Warn if any missing. [default]"),
        ('owner=', 'u',
         "Owner name used when creating a tar file [default: current user]"),
        ('group=', 'g',
         "Group name used when creating a tar file [default: current group]"),
        ]

    boolean_options = ['use-defaults', 'prune',
                       'manifest-only', 'keep-temp', 'check-metadata']

    help_options = [
        ('help-formats', None,
         "list available distribution formats", show_formats),
        ]

    negative_opt = {'no-defaults': 'use-defaults',
                    'no-prune': 'prune' }

    default_format = {'posix': 'gztar',
                      'nt': 'zip' }

    def initialize_options(self):
        # 'template' and 'manifest' are, respectively, the names of
        # the manifest template and manifest file.
        self.template = None
        self.manifest = None

        # 'use_defaults': if true, we will include the default file set
        # in the manifest
        self.use_defaults = 1
        self.prune = 1
        self.manifest_only = 0
        self.formats = None
        self.keep_temp = 0
        self.dist_dir = None

        self.archive_files = None
        self.metadata_check = 1
        self.owner = None
        self.group = None
        self.filelist = None

    def _check_archive_formats(self, formats):
        supported_formats = [name for name, desc in get_archive_formats()]
        for format in formats:
            if format not in supported_formats:
                return format
        return None

    def finalize_options(self):
        if self.manifest is None:
            self.manifest = "MANIFEST"
        if self.template is None:
            self.template = "MANIFEST.in"

        self.ensure_string_list('formats')
        if self.formats is None:
            try:
                self.formats = [self.default_format[os.name]]
            except KeyError:
                raise DistutilsPlatformError, \
                      "don't know how to create source distributions " + \
                      "on platform %s" % os.name

        bad_format = self._check_archive_formats(self.formats)
        if bad_format:
            raise DistutilsOptionError, \
                  "unknown archive format '%s'" % bad_format

        if self.dist_dir is None:
            self.dist_dir = "dist"

        if self.filelist is None:
            self.filelist = Manifest()


    def run(self):
        # 'filelist' contains the list of files that will make up the
        # manifest
        self.filelist.clear()

        # Check the package metadata
        if self.metadata_check:
            self.run_command('check')

        # Do whatever it takes to get the list of files to process
        # (process the manifest template, read an existing manifest,
        # whatever).  File list is accumulated in 'self.filelist'.
        self.get_file_list()

        # If user just wanted us to regenerate the manifest, stop now.
        if self.manifest_only:
            return

        # Otherwise, go ahead and create the source distribution tarball,
        # or zipfile, or whatever.
        self.make_distribution()

    def get_file_list(self):
        """Figure out the list of files to include in the source
        distribution, and put it in 'self.filelist'.  This might involve
        reading the manifest template (and writing the manifest), or just
        reading the manifest, or just using the default file set -- it all
        depends on the user's options.
        """
        template_exists = os.path.isfile(self.template)
        if not template_exists:
            self.warn(("manifest template '%s' does not exist " +
                        "(using default file list)") %
                        self.template)

        self.filelist.findall()

        if self.use_defaults:
            self.add_defaults()
        if template_exists:
            self.filelist.read_template(self.template)
        if self.prune:
            self.prune_file_list()

        self.filelist.write(self.manifest)

    def add_defaults(self):
        """Add all the default files to self.filelist:
          - README or README.txt
          - test/test*.py
          - all pure Python modules mentioned in setup script
          - all files pointed by package_data (build_py)
          - all files defined in data_files.
          - all files defined as scripts.
          - all C sources listed as part of extensions or C libraries
            in the setup script (doesn't catch C headers!)
        Warns if (README or README.txt) or setup.py are missing; everything
        else is optional.
        """
        standards = [('README', 'README.txt')]
        for fn in standards:
            if isinstance(fn, tuple):
                alts = fn
                got_it = 0
                for fn in alts:
                    if os.path.exists(fn):
                        got_it = 1
                        self.filelist.append(fn)
                        break

                if not got_it:
                    self.warn("standard file not found: should have one of " +
                              string.join(alts, ', '))
            else:
                if os.path.exists(fn):
                    self.filelist.append(fn)
                else:
                    self.warn("standard file '%s' not found" % fn)

        optional = ['test/test*.py', 'setup.cfg']
        for pattern in optional:
            files = filter(os.path.isfile, glob(pattern))
            if files:
                self.filelist.extend(files)

        for cmd_name in self.distribution.get_command_names():
            try:
                cmd_obj = self.get_finalized_command(cmd_name)
            except DistutilsOptionError:
                pass
            else:
                self.filelist.extend(cmd_obj.get_source_files())

    def prune_file_list(self):
        """Prune off branches that might slip into the file list as created
        by 'read_template()', but really don't belong there:
          * the build tree (typically "build")
          * the release tree itself (only an issue if we ran "sdist"
            previously with --keep-temp, or it aborted)
          * any RCS, CVS, .svn, .hg, .git, .bzr, _darcs directories
        """
        build = self.get_finalized_command('build')
        base_dir = self.distribution.get_fullname()

        self.filelist.exclude_pattern(None, prefix=build.build_base)
        self.filelist.exclude_pattern(None, prefix=base_dir)

        # pruning out vcs directories
        # both separators are used under win32
        if sys.platform == 'win32':
            seps = r'/|\\'
        else:
            seps = '/'

        vcs_dirs = ['RCS', 'CVS', r'\.svn', r'\.hg', r'\.git', r'\.bzr',
                    '_darcs']
        vcs_ptrn = r'(^|%s)(%s)(%s).*' % (seps, '|'.join(vcs_dirs), seps)
        self.filelist.exclude_pattern(vcs_ptrn, is_regex=1)


    def make_release_tree(self, base_dir, files):
        """Create the directory tree that will become the source
        distribution archive.  All directories implied by the filenames in
        'files' are created under 'base_dir', and then we hard link or copy
        (if hard linking is unavailable) those files into place.
        Essentially, this duplicates the developer's source tree, but in a
        directory named after the distribution, containing only the files
        to be distributed.
        """
        # Create all the directories under 'base_dir' necessary to
        # put 'files' there; the 'mkpath()' is just so we don't die
        # if the manifest happens to be empty.
        self.mkpath(base_dir)
        self.create_tree(base_dir, files, dry_run=self.dry_run)

        # And walk over the list of files, either making a hard link (if
        # os.link exists) to each one that doesn't already exist in its
        # corresponding location under 'base_dir', or copying each file
        # that's out-of-date in 'base_dir'.  (Usually, all files will be
        # out-of-date, because by default we blow away 'base_dir' when
        # we're done making the distribution archives.)

        if hasattr(os, 'link'):        # can make hard links on this system
            link = 'hard'
            msg = "making hard links in %s..." % base_dir
        else:                           # nope, have to copy
            link = None
            msg = "copying files to %s..." % base_dir

        if not files:
            log.warn("no files to distribute -- empty manifest?")
        else:
            log.info(msg)
        for file in files:
            if not os.path.isfile(file):
                log.warn("'%s' not a regular file -- skipping" % file)
            else:
                dest = os.path.join(base_dir, file)
                self.copy_file(file, dest, link=link)

        self.distribution.metadata.write(os.path.join(base_dir, 'PKG-INFO'))

    def make_distribution(self):
        """Create the source distribution(s).  First, we create the release
        tree with 'make_release_tree()'; then, we create all required
        archive files (according to 'self.formats') from the release tree.
        Finally, we clean up by blowing away the release tree (unless
        'self.keep_temp' is true).  The list of archive files created is
        stored so it can be retrieved later by 'get_archive_files()'.
        """
        # Don't warn about missing metadata here -- should be (and is!)
        # done elsewhere.
        base_dir = self.distribution.get_fullname()
        base_name = os.path.join(self.dist_dir, base_dir)

        self.make_release_tree(base_dir, self.filelist.files)
        archive_files = []              # remember names of files we create
        # tar archive must be created last to avoid overwrite and remove
        if 'tar' in self.formats:
            self.formats.append(self.formats.pop(self.formats.index('tar')))

        for fmt in self.formats:
            file = self.make_archive(base_name, fmt, base_dir=base_dir,
                                     owner=self.owner, group=self.group)
            archive_files.append(file)
            self.distribution.dist_files.append(('sdist', '', file))

        self.archive_files = archive_files

        if not self.keep_temp:
            if self.dry_run:
                log.info('Removing %s' % base_dir)
            else:
                rmtree(base_dir)

    def get_archive_files(self):
        """Return the list of archive files created when the command
        was run, or None if the command hasn't run yet.
        """
        return self.archive_files

    def create_tree(self, base_dir, files, mode=0777, verbose=1, dry_run=0):
        need_dir = {}
        for file in files:
            need_dir[os.path.join(base_dir, os.path.dirname(file))] = 1
        need_dirs = need_dir.keys()
        need_dirs.sort()

        # Now create them
        for dir in need_dirs:
            self.mkpath(dir, mode, verbose=verbose, dry_run=dry_run)

