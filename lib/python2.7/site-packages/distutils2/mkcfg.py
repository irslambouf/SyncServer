#!/usr/bin/env python
#
#  Helper for automating the creation of a package by looking at you
#  current directory and asking the user questions.
#
#  Available as either a stand-alone file or callable from the distutils2
#  package:
#
#     python -m distutils2.mkcfg
#  or:
#     python mkcfg.py
#
#  Written by Sean Reifschneider <jafo@tummy.com>
#
#  Original TODO list:
#  Look for a license file and automatically add the category.
#  When a .c file is found during the walk, can we add it as an extension?
#  Ask if there is a maintainer different that the author
#  Ask for the platform (can we detect this via "import win32" or something?)
#  Ask for the dependencies.
#  Ask for the Requires-Dist
#  Ask for the Provides-Dist
#  Detect scripts (not sure how.  #! outside of package?)

import os
import sys
import re
import shutil
from ConfigParser import RawConfigParser
from textwrap import dedent
# importing this with an underscore as it should be replaced by the
# dict form or another structures for all purposes
from distutils2._trove import all_classifiers as _CLASSIFIERS_LIST

_FILENAME = 'setup.cfg'

_helptext = {
    'name': '''
The name of the program to be packaged, usually a single word composed
of lower-case characters such as "python", "sqlalchemy", or "CherryPy".
''',
    'version': '''
Version number of the software, typically 2 or 3 numbers separated by dots
such as "1.00", "0.6", or "3.02.01".  "0.1.0" is recommended for initial
development.
''',
    'description': '''
A short summary of what this package is or does, typically a sentence 80
characters or less in length.
''',
    'author': '''
The full name of the author (typically you).
''',
    'author_email': '''
E-mail address of the package author (typically you).
''',
    'do_classifier': '''
Trove classifiers are optional identifiers that allow you to specify the
intended audience by saying things like "Beta software with a text UI
for Linux under the PSF license.  However, this can be a somewhat involved
process.
''',
    'package': '''
You can provide a package name contained in your project.
''',

    'home_page': '''
The home page for the package, typically starting with "http://".
''',
    'trove_license': '''
Optionally you can specify a license.  Type a string that identifies a common
license, and then you can select a list of license specifiers.
''',
    'trove_generic': '''
Optionally, you can set other trove identifiers for things such as the
human language, programming language, user interface, etc...
''',
}

# XXX everything needs docstrings and tests (both low-level tests of various
# methods and functional tests of running the script)


def ask_yn(question, default=None, helptext=None):
    question += ' (y/n)'
    while True:
        answer = ask(question, default, helptext, required=True)
        if answer and answer[0].lower() in 'yn':
            return answer[0].lower()

        print '\nERROR: You must select "Y" or "N".\n'


def ask(question, default=None, helptext=None, required=True,
        lengthy=False, multiline=False):
    prompt = '%s: ' % (question,)
    if default:
        prompt = '%s [%s]: ' % (question, default)
        if default and len(question) + len(default) > 70:
            prompt = '%s\n    [%s]: ' % (question, default)
    if lengthy or multiline:
        prompt += '\n   >'

    if not helptext:
        helptext = 'No additional help available.'

    helptext = helptext.strip("\n")

    while True:
        sys.stdout.write(prompt)
        sys.stdout.flush()

        line = sys.stdin.readline().strip()
        if line == '?':
            print '=' * 70
            print helptext
            print '=' * 70
            continue
        if default and not line:
            return default
        if not line and required:
            print '*' * 70
            print 'This value cannot be empty.'
            print '==========================='
            if helptext:
                print helptext
            print '*' * 70
            continue
        return line


def _build_classifiers_dict(classifiers):
    d = {}
    for key in classifiers:
        subDict = d
        for subkey in key.split(' :: '):
            if not subkey in subDict:
                subDict[subkey] = {}
            subDict = subDict[subkey]
    return d

CLASSIFIERS = _build_classifiers_dict(_CLASSIFIERS_LIST)


class MainProgram(object):
    def __init__(self):
        self.configparser = None
        self.classifiers = {}
        self.data = {}
        self.data['classifier'] = self.classifiers
        self.data['packages'] = []
        self.load_config_file()

    def lookup_option(self, key):
        if not self.configparser.has_option('DEFAULT', key):
            return None
        return self.configparser.get('DEFAULT', key)

    def load_config_file(self):
        self.configparser = RawConfigParser()
        # TODO replace with section in distutils config file
        self.configparser.read(os.path.expanduser('~/.mkcfg'))
        self.data['author'] = self.lookup_option('author')
        self.data['author_email'] = self.lookup_option('author_email')

    def update_config_file(self):
        valuesDifferent = False
        # FIXME looking only for those two fields seems wrong
        for compareKey in ('author', 'author_email'):
            if self.lookup_option(compareKey) != self.data[compareKey]:
                valuesDifferent = True
                self.configparser.set('DEFAULT', compareKey,
                                      self.data[compareKey])

        if not valuesDifferent:
            return

        fp = open(os.path.expanduser('~/.mkcfgpy'), 'w')
        try:
            self.configparser.write(fp)
        finally:
            fp.close()

    def load_existing_setup_script(self):
        raise NotImplementedError
        # Ideas:
        # - define a mock module to assign to sys.modules['distutils'] before
        # importing the setup script as a module (or executing it); it would
        # provide setup (a function that just returns its args as a dict),
        # Extension (ditto), find_packages (the real function)
        # - we could even mock Distribution and commands to handle more setup
        # scripts
        # - we could use a sandbox (http://bugs.python.org/issue8680)
        # - the cleanest way is to parse the file, not import it, but there is
        # no way to do that across versions (the compiler package is
        # deprecated or removed in recent Pythons, the ast module is not
        # present before 2.6)

    def inspect_file(self, path):
        fp = open(path, 'r')
        try:
            for line in [fp.readline() for _ in range(10)]:
                m = re.match(r'^#!.*python((?P<major>\d)(\.\d+)?)?$', line)
                if m:
                    if m.group('major') == '3':
                        self.classifiers['Programming Language :: Python :: 3'] = 1
                    else:
                        self.classifiers['Programming Language :: Python :: 2'] = 1
        finally:
            fp.close()

    def inspect_directory(self):
        dirName = os.path.basename(os.getcwd())
        self.data['name'] = dirName
        m = re.match(r'(.*)-(\d.+)', dirName)
        if m:
            self.data['name'] = m.group(1)
            self.data['version'] = m.group(2)

    def query_user(self):
        self.data['name'] = ask('Project name', self.data['name'],
              _helptext['name'])
        self.data['version'] = ask('Current version number',
              self.data.get('version'), _helptext['version'])
        self.data['description'] = ask('Package description',
              self.data.get('description'), _helptext['description'],
              lengthy=True)
        self.data['author'] = ask('Author name',
              self.data.get('author'), _helptext['author'])
        self.data['author_email'] = ask('Author e-mail address',
              self.data.get('author_email'), _helptext['author_email'])
        self.data['home_page'] = ask('Project Home Page',
              self.data.get('home_page'), _helptext['home_page'],
              required=False)

        while ask_yn('Do you want to add a package ?',
                  helptext=_helptext['package']) == 'y':
            self.set_package()

        if ask_yn('Do you want to set Trove classifiers?',
                  helptext=_helptext['do_classifier']) == 'y':
            self.set_classifier()

    def set_package(self):
        packages = self.data['packages']
        name = ask('Package name', helptext=_helptext['package']).strip()
        if name == '':
            return
        if name not in packages:
            packages.append(name)

    def set_classifier(self):
        self.set_devel_status(self.classifiers)
        self.set_license(self.classifiers)
        self.set_other_classifier(self.classifiers)

    def set_other_classifier(self, classifiers):
        if ask_yn('Do you want to set other trove identifiers', 'n',
                  _helptext['trove_generic']) != 'y':
            return
        self.walk_classifiers(classifiers, [CLASSIFIERS], '')

    def walk_classifiers(self, classifiers, trovepath, desc):
        trove = trovepath[-1]

        if not trove:
            return

        for key in sorted(trove.keys()):
            if len(trove[key]) == 0:
                if ask_yn('Add "%s"' % desc[4:] + ' :: ' + key, 'n') == 'y':
                    classifiers[desc[4:] + ' :: ' + key] = 1
                continue

            if ask_yn('Do you want to set items under\n   "%s" (%d sub-items)'
                      % (key, len(trove[key])), 'n',
                      _helptext['trove_generic']) == 'y':
                self.walk_classifiers(classifiers, trovepath + [trove[key]],
                                      desc + ' :: ' + key)

    def set_license(self, classifiers):
        while True:
            license = ask('What license do you use',
                          helptext=_helptext['trove_license'], required=False)
            if not license:
                return

            licenseWords = license.lower().split(' ')

            foundList = []
            # TODO use enumerate
            for index in range(len(_CLASSIFIERS_LIST)):
                troveItem = _CLASSIFIERS_LIST[index]
                if not troveItem.startswith('License :: '):
                    continue
                troveItem = troveItem[11:].lower()

                allMatch = True
                for word in licenseWords:
                    if not word in troveItem:
                        allMatch = False
                        break
                if allMatch:
                    foundList.append(index)

            question = 'Matching licenses:\n\n'
            # TODO use enumerate?
            for i in xrange(1, len(foundList) + 1):
                question += '   %s) %s\n' % (i, _CLASSIFIERS_LIST[foundList[i - 1]])
            question += ('\nType the number of the license you wish to use or '
                         '? to try again:')
            troveLicense = ask(question, required=False)

            if troveLicense == '?':
                continue
            if troveLicense == '':
                return
            # FIXME the int conversion can fail
            foundIndex = foundList[int(troveLicense) - 1]
            classifiers[_CLASSIFIERS_LIST[foundIndex]] = 1
            try:
                return
            except IndexError:
                print ("ERROR: Invalid selection, type a number from the list "
                       "above.")

    def set_devel_status(self, classifiers):
        while True:
            choice = ask(dedent('''\
                Please select the project status:

                1 - Planning
                2 - Pre-Alpha
                3 - Alpha
                4 - Beta
                5 - Production/Stable
                6 - Mature
                7 - Inactive

                Status'''), required=False)
            if choice:
                try:
                    choice = int(choice) - 1
                    key = ['Development Status :: 1 - Planning',
                           'Development Status :: 2 - Pre-Alpha',
                           'Development Status :: 3 - Alpha',
                           'Development Status :: 4 - Beta',
                           'Development Status :: 5 - Production/Stable',
                           'Development Status :: 6 - Mature',
                           'Development Status :: 7 - Inactive'][choice]
                    classifiers[key] = 1
                    return
                except (IndexError, ValueError):
                    print ("ERROR: Invalid selection, type a single digit "
                           "number.")

    def _dotted_packages(self, data):
        packages = sorted(data.keys())
        modified_pkgs = []
        for pkg in packages:
            pkg = pkg.lstrip('./')
            pkg = pkg.replace('/', '.')
            modified_pkgs.append(pkg)
        return modified_pkgs

    def write_setup_script(self):
        if os.path.exists(_FILENAME):
            if os.path.exists('%s.old' % _FILENAME):
                print("ERROR: %(name)s.old backup exists, please check that "
                    "current %(name)s is correct and remove %(name)s.old" % \
                    {'name': _FILENAME})
                return
            shutil.move(_FILENAME, '%s.old' % _FILENAME)

        fp = open(_FILENAME, 'w')
        try:
            fp.write('[metadata]\n')
            fp.write('name = %s\n' % self.data['name'])
            fp.write('version = %s\n' % self.data['version'])
            fp.write('author = %s\n' % self.data['author'])
            fp.write('author_email = %s\n' % self.data['author_email'])
            fp.write('description = %s\n' % self.data['description'])
            fp.write('home_page = %s\n' % self.data['home_page'])
            fp.write('\n')
            if len(self.data['classifier']) > 0:
                classifiers = '\n'.join(['    %s' % clas for clas in
                                         self.data['classifier']])
                fp.write('classifier = %s\n' % classifiers.strip())
                fp.write('\n')

            fp.write('[files]\n')
            packages = '\n'.join(['    %s' % pkg for pkg in
                                  self.data['packages']])
            fp.write('\n')
            fp.write('packages = %s\n' % packages.strip())
        finally:
            fp.close()

        os.chmod(_FILENAME, 0755)
        print 'Wrote "%s".' % _FILENAME


def main():
    """Main entry point."""
    program = MainProgram()
    # uncomment when implemented
    #program.load_existing_setup_script()
    program.inspect_directory()
    program.query_user()
    program.update_config_file()
    program.write_setup_script()


if __name__ == '__main__':
    main()
