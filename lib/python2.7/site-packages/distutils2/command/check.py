"""distutils.command.check

Implements the Distutils 'check' command.
"""

from distutils2.core import Command
from distutils2.errors import DistutilsSetupError
from distutils2.util import resolve_name

class check(Command):
    """This command checks the metadata of the package.
    """
    description = ("perform some checks on the package")
    user_options = [('metadata', 'm', 'Verify metadata'),
                    ('all', 'a',
                     ('runs extended set of checks')),
                    ('strict', 's',
                     'Will exit with an error if a check fails')]

    boolean_options = ['metadata', 'all', 'strict']

    def initialize_options(self):
        """Sets default values for options."""
        self.all = 0
        self.metadata = 1
        self.strict = 0
        self._warnings = []

    def finalize_options(self):
        pass

    def warn(self, msg):
        """Counts the number of warnings that occurs."""
        self._warnings.append(msg)
        return Command.warn(self, msg)

    def run(self):
        """Runs the command."""
        # perform the various tests
        if self.metadata:
            self.check_metadata()
        if self.all:
            self.check_restructuredtext()
            self.check_hooks_resolvable()

        # let's raise an error in strict mode, if we have at least
        # one warning
        if self.strict and len(self._warnings) > 0:
            msg = '\n'.join(self._warnings)
            raise DistutilsSetupError(msg)

    def check_metadata(self):
        """Ensures that all required elements of metadata are supplied.

        name, version, URL, (author and author_email) or
        (maintainer and maintainer_email)).

        Warns if any are missing.
        """
        missing, __ = self.distribution.metadata.check()
        if missing != []:
            self.warn("missing required metadata: %s"  % ', '.join(missing))

    def check_restructuredtext(self):
        """Checks if the long string fields are reST-compliant."""
        missing, warnings = self.distribution.metadata.check()
        if self.distribution.metadata.docutils_support:
            for warning in warnings:
                line = warning[-1].get('line')
                if line is None:
                    warning = warning[1]
                else:
                    warning = '%s (line %s)' % (warning[1], line)
                self.warn(warning)
        elif self.strict:
            raise DistutilsSetupError('The docutils package is needed.')

    def check_hooks_resolvable(self):
        for options in self.distribution.command_options.values():
            for hook_kind in ("pre_hook", "post_hook"):
                if hook_kind not in options:
                    break
                for hook_name in options[hook_kind][1].values():
                    try:
                        resolve_name(hook_name)
                    except ImportError:
                        self.warn("Name '%s' cannot be resolved." % hook_name)
