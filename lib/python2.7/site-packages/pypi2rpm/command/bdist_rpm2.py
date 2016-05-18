# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is "pypi2rpm"
#
# The Initial Developer of the Original Code is Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****
import string
import os
import sys

from distutils.command.bdist_rpm import bdist_rpm
from distutils.errors import (DistutilsPlatformError, DistutilsOptionError,
                              DistutilsFileError, DistutilsExecError)

from distutils.file_util import write_file


class bdist_rpm2(bdist_rpm):

    user_options = bdist_rpm.user_options + [
            ('name=', None, 'Name of the package'),
            ('spec-file=', None, 'Use an existing spec file'),
            ('tmppath=', None, 'Temporary path for builds (_tmppath variable)')
            ]

    def __init__ (self, dist):
        self.distribution = dist
        self.initialize_options()
        self._dry_run = None
        self.verbose = dist.verbose
        self.force = None
        self.help = 0
        self.finalized = 0
        self.tmppath = None

    def initialize_options(self):
        bdist_rpm.initialize_options(self)
        self.name = None
        self.spec_file = None

    def _make_spec_file(self):
        """Generate the text of an RPM spec file and return it as a
        list of strings (one per line).
        """
        if self.spec_file is not None:
            f = open(self.spec_file)
            try:
                return f.read().split('\n')
            finally:
                f.close()

        # XXX find a cleaner way (wrapper ?)
        try:
            pythonname = self.distribution.get_name()
        except AttributeError:
            pythonname = self.distribution.metadata['Name']

        try:
            version = self.distribution.get_version()
        except AttributeError:
            version = self.distribution.metadata['Version']

        try:
            summary = self.distribution.get_description()
        except AttributeError:
            summary = self.distribution.metadata['Summary']

        # definitions and headers
        spec_file = [
            '%define name ' + self.name,
            '%define pythonname ' + pythonname,
            '%define version ' + version.replace('-','_'),
            '%define unmangled_version ' + version,
            '%define release ' + self.release.replace('-','_'),
            '',

            '\\\n'.join(['%define __os_install_post'
                       , '%( rpm --eval %%__os_install_post)'
                       , "( cd $RPM_BUILD_ROOT; find . -type f | sed -e 's/^.//') > INSTALLED_FILES"]) ,

            'Summary: ' + summary,
            ]

        # put locale summaries into spec file
        # XXX not supported for now (hard to put a dictionary
        # in a config file -- arg!)
        #for locale in self.summaries.keys():
        #    spec_file.append('Summary(%s): %s' % (locale,
        #                                          self.summaries[locale]))

        spec_file.extend([
            'Name: %{name}',
            'Version: %{version}',
            'Release: %{release}',])

        # XXX yuck! this filename is available from the "sdist" command,
        # but only after it has run: and we create the spec file before
        # running "sdist", in case of --spec-only.
        if self.use_bzip2:
            spec_file.append('Source0: %{pythonname}-%{unmangled_version}.tar.bz2')
        else:
            spec_file.append('Source0: %{pythonname}-%{unmangled_version}.tar.gz')

        try:
            license = self.distribution.get_license()
        except AttributeError:
            license = self.distribution.metadata['License']

        spec_file.extend([
            'License: ' + license,
            'Group: ' + self.group,
            'BuildRoot: %{_tmppath}/%{pythonname}-%{version}-%{release}-buildroot',
            'Prefix: %{_prefix}', ])

        if not self.force_arch:
            # noarch if no extension modules
            if not self.distribution.has_ext_modules():
                spec_file.append('BuildArch: noarch')
        else:
            spec_file.append( 'BuildArch: %s' % self.force_arch )

        for field in ('Vendor',
                      'Packager',
                      'Provides',
                      'Requires',
                      'Conflicts',
                      'Obsoletes',
                      ):
            val = getattr(self, string.lower(field))
            if isinstance(val, list):
                spec_file.append('%s: %s' % (field, string.join(val)))
            elif val is not None:
                spec_file.append('%s: %s' % (field, val))


        try:
            url = self.distribution.get_url()
        except AttributeError:
            url = self.distribution.metadata['Home-Url']

        if url != 'UNKNOWN':
            spec_file.append('Url: ' + url)

        if self.distribution_name:
            spec_file.append('Distribution: ' + self.distribution_name)

        if self.build_requires:
            spec_file.append('BuildRequires: ' +
                             string.join(self.build_requires))

        if self.icon:
            spec_file.append('Icon: ' + os.path.basename(self.icon))

        if self.no_autoreq:
            spec_file.append('AutoReq: 0')

        try:
            description = self.distribution.get_long_description()
        except AttributeError:
            description = self.distribution.metadata['Description']


        spec_file.extend([
            '',
            '%description', description
            ])

        # rpm scripts
        # figure out default build script
        if self.distribution.script_name != 'run.py':
            # XXX find a better d2 marker
            def_setup_call = "%s %s" % (self.python,
                                        os.path.basename(sys.argv[0]))
        else:
            def_setup_call = "%s -m distutils2.run" % self.python

        def_build = "%s build" % def_setup_call
        if self.use_rpm_opt_flags:
            def_build = 'env CFLAGS="$RPM_OPT_FLAGS" ' + def_build

        # insert contents of files

        # XXX this is kind of misleading: user-supplied options are files
        # that we open and interpolate into the spec file, but the defaults
        # are just text that we drop in as-is.  Hmmm.

        script_options = [
            ('prep', 'prep_script', "%setup -n %{pythonname}-%{unmangled_version}"),
            ('build', 'build_script', def_build),
            ('install', 'install_script',
             ("%s install "
              "--root=$RPM_BUILD_ROOT "
              "--record=INSTALLED_FILES") % def_setup_call),
            ('clean', 'clean_script', "rm -rf $RPM_BUILD_ROOT"),
            ('verifyscript', 'verify_script', None),
            ('pre', 'pre_install', None),
            ('post', 'post_install', None),
            ('preun', 'pre_uninstall', None),
            ('postun', 'post_uninstall', None),
        ]

        for (rpm_opt, attr, default) in script_options:
            # Insert contents of file referred to, if no file is referred to
            # use 'default' as contents of script
            val = getattr(self, attr)
            if val or default:
                spec_file.extend([
                    '',
                    '%' + rpm_opt,])
                if val:
                    spec_file.extend(string.split(open(val, 'r').read(), '\n'))
                else:
                    spec_file.append(default)

        # files section
        spec_file.extend([
            '',
            '%files -f INSTALLED_FILES',
            '%defattr(-,root,root)',
            ])

        if self.doc_files:
            spec_file.append('%doc ' + string.join(self.doc_files))

        if self.changelog:
            spec_file.extend([
                '',
                '%changelog',])
            spec_file.extend(self.changelog)

        return spec_file

    def finalize_package_data (self):
        self.ensure_string('group', "Development/Libraries")
        try:
            vendor = "%s <%s>" % (self.distribution.get_contact(),
                                  self.distribution.get_contact_email())
        except AttributeError:
            vendor = "%s <%s>" % (self.distribution.metadata['Author'],
                                  self.distribution.metadata['Author-Email'])

        self.ensure_string('vendor', vendor)
        self.ensure_string('packager')
        self.ensure_string_list('doc_files')
        if isinstance(self.doc_files, list):
            for readme in ('README', 'README.txt'):
                if os.path.exists(readme) and readme not in self.doc_files:
                    self.doc_files.append(readme)

        self.ensure_string('release', "1")
        self.ensure_string('serial')   # should it be an int?

        self.ensure_string('distribution_name')

        self.ensure_string('changelog')
        self.changelog = self._format_changelog(self.changelog)

        for name in ('icon', 'prep_script', 'build_script', 'install_script',
                     'clean_script', 'verify_script', 'pre_install',
                     'post_install', 'pre_uninstall', 'post_uninstall'):

            self.ensure_filename(name)

        for name in ('provides', 'requires', 'conflicts', 'build_requires',
                     'obsoletes'):
            self.ensure_string_list(name)

        self.ensure_string('force_arch')

    def finalize_options (self):
        self.set_undefined_options('bdist', ('bdist_base', 'bdist_base'))
        if self.rpm_base is None:
            if not self.rpm3_mode:
                raise DistutilsOptionError, \
                      "you must specify --rpm-base in RPM 2 mode"
            self.rpm_base = os.path.join(self.bdist_base, "rpm")

        if self.python is None:
            if self.fix_python:
                self.python = sys.executable
            else:
                self.python = "python"
        elif self.fix_python:
            raise DistutilsOptionError, \
                  "--python and --fix-python are mutually exclusive options"

        if os.name != 'posix':
            raise DistutilsPlatformError("don't know how to create RPM "
                   "distributions on platform %s" % os.name)
        if self.binary_only and self.source_only:
            raise DistutilsOptionError(
                  "cannot supply both '--source-only' and '--binary-only'")

        # don't pass CFLAGS to pure python distributions
        if not self.distribution.has_ext_modules():
            self.use_rpm_opt_flags = 0

        self.set_undefined_options('bdist', ('dist_dir', 'dist_dir'))
        if self.name is None:
            try:
                self.name = self.distribution.get_name()
            except AttributeError:
                self.name = self.distribution.metadata['Name']
        self.ensure_filename('spec_file')
        self.finalize_package_data()

    def get_source_files(self):
        return []

    def run(self):
        # make directories
        if self.spec_only:
            spec_dir = self.dist_dir
            self.mkpath(spec_dir)
        else:
            rpm_dir = {}
            for d in ('SOURCES', 'SPECS', 'BUILD', 'RPMS', 'SRPMS'):
                rpm_dir[d] = os.path.join(self.rpm_base, d)
                self.mkpath(rpm_dir[d])
            spec_dir = rpm_dir['SPECS']

        # Spec file goes into 'dist_dir' if '--spec-only specified',
        # build/rpm.<plat> otherwise
        try:
            name = self.distribution.get_name()
        except AttributeError:
            name = self.distribution.metadata['Name']

        spec_path = os.path.join(spec_dir, "%s.spec" % name)
        self.execute(write_file,
                     (spec_path,
                      self._make_spec_file()),
                     "writing '%s'" % spec_path)

        if self.spec_only: # stop if requested
            return

        # Make a source distribution and copy to SOURCES directory with
        # optional icon.

        try:
            saved_dist_files = self.distribution.dist_files[:]
        except AttributeError:
            # no dist_files attibut in old distutils version (python 2.4 for instance)
            saved_dist_files = []

        try:
            sdist = self.reinitialize_command('sdist')
        except AttributeError:
            sdist = self.distribution.get_command_obj('sdist')


        if self.use_bzip2:
            sdist.formats = ['bztar']
        else:
            sdist.formats = ['gztar']

        self.run_command('sdist')
        try:
            self.distribution.dist_files = saved_dist_files
        except AttributeError:
            pass

        source = sdist.get_archive_files()[0]
        source_dir = rpm_dir['SOURCES']
        self.copy_file(source, source_dir)

        if self.icon:
            if os.path.exists(self.icon):
                self.copy_file(self.icon, source_dir)
            else:
                raise DistutilsFileError, \
                      "icon file '%s' does not exist" % self.icon


        # build package
        rpm_cmd = ['rpm']
        if os.path.exists('/usr/bin/rpmbuild') or \
           os.path.exists('/bin/rpmbuild'):
            rpm_cmd = ['rpmbuild']
        if self.source_only: # what kind of RPMs?
            rpm_cmd.append('-bs')
        elif self.binary_only:
            rpm_cmd.append('-bb')
        else:
            rpm_cmd.append('-ba')
        if self.rpm3_mode:
            rpm_cmd.extend(['--define',
                             '_topdir %s' % os.path.abspath(self.rpm_base)])

        if self.tmppath:
            rpm_cmd.extend(['--define',
                            "_tmppath %s" % os.path.abspath(self.tmppath)])

        if not self.keep_temp:
            rpm_cmd.append('--clean')
        rpm_cmd.append(spec_path)
        # Determine the binary rpm names that should be built out of this spec
        # file
        # Note that some of these may not be really built (if the file
        # list is empty)
        nvr_string = "%{name}-%{version}-%{release}"
        src_rpm = nvr_string + ".src.rpm"
        non_src_rpm = "%{arch}/" + nvr_string + ".%{arch}.rpm"
        q_cmd = r"rpm -q --qf '%s %s\n' --specfile '%s'" % (
            src_rpm, non_src_rpm, spec_path)

        out = os.popen(q_cmd)
        binary_rpms = []
        source_rpm = None
        while 1:
            line = out.readline()
            if not line:
                break
            l = string.split(string.strip(line))
            assert(len(l) == 2)
            binary_rpms.append(l[1])
            # The source rpm is named after the first entry in the spec file
            if source_rpm is None:
                source_rpm = l[0]

        status = out.close()
        if status:
            raise DistutilsExecError("Failed to execute: %s" % repr(q_cmd))

        self.spawn(rpm_cmd)

        if not self.dry_run:
            if not os.path.isdir(self.dist_dir):
                raise DistutilsFileError('%s is not a dir' % self.dist_dir)

            if not self.binary_only:
                srpm = os.path.join(rpm_dir['SRPMS'], source_rpm)
                assert(os.path.exists(srpm))
                self.move_file(srpm, self.dist_dir)

            if not self.source_only:
                for rpm in binary_rpms:
                    rpm = os.path.join(rpm_dir['RPMS'], rpm)
                    if os.path.exists(rpm):
                        self.move_file(rpm, self.dist_dir)
