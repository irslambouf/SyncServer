"""distutils.command.upload

Implements the Distutils 'upload' subcommand (upload package to PyPI)."""
import os
import socket
import platform
from urllib2 import urlopen, Request, HTTPError
from base64 import standard_b64encode
import urlparse
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
try:
    from hashlib import md5
except ImportError:
    from distutils2._backport.hashlib import md5

from distutils2.errors import DistutilsOptionError
from distutils2.util import spawn
from distutils2 import log
from distutils2.command.cmd import Command
from distutils2 import log
from distutils2.util import (metadata_to_dict, read_pypirc,
                             DEFAULT_REPOSITORY, DEFAULT_REALM)


class upload(Command):

    description = "upload distribution to PyPI"

    user_options = [
        ('repository=', 'r',
         "repository URL [default: %s]" % DEFAULT_REPOSITORY),
        ('show-response', None,
         "display full response text from server"),
        ('sign', 's',
         "sign files to upload using gpg"),
        ('identity=', 'i',
         "GPG identity used to sign files"),
        ('upload-docs', None,
         "upload documentation too"),
        ]

    boolean_options = ['show-response', 'sign']

    def initialize_options(self):
        self.repository = None
        self.realm = None
        self.show_response = 0
        self.username = ''
        self.password = ''
        self.show_response = 0
        self.sign = False
        self.identity = None
        self.upload_docs = False

    def finalize_options(self):
        if self.repository is None:
            self.repository = DEFAULT_REPOSITORY
        if self.realm is None:
            self.realm = DEFAULT_REALM
        if self.identity and not self.sign:
            raise DistutilsOptionError(
                "Must use --sign for --identity to have meaning"
            )
        config = read_pypirc(self.repository, self.realm)
        if config != {}:
            self.username = config['username']
            self.password = config['password']
            self.repository = config['repository']
            self.realm = config['realm']

        # getting the password from the distribution
        # if previously set by the register command
        if not self.password and self.distribution.password:
            self.password = self.distribution.password

    def run(self):
        if not self.distribution.dist_files:
            raise DistutilsOptionError("No dist file created in earlier command")
        for command, pyversion, filename in self.distribution.dist_files:
            self.upload_file(command, pyversion, filename)
        if self.upload_docs:
            upload_docs = self.get_finalized_command("upload_docs")
            upload_docs.repository = self.repository
            upload_docs.username = self.username
            upload_docs.password = self.password
            upload_docs.run()

    # XXX to be refactored with register.post_to_server
    def upload_file(self, command, pyversion, filename):
        # Makes sure the repository URL is compliant
        schema, netloc, url, params, query, fragments = \
            urlparse.urlparse(self.repository)
        if params or query or fragments:
            raise AssertionError("Incompatible url %s" % self.repository)

        if schema not in ('http', 'https'):
            raise AssertionError("unsupported schema " + schema)

        # Sign if requested
        if self.sign:
            gpg_args = ["gpg", "--detach-sign", "-a", filename]
            if self.identity:
                gpg_args[2:2] = ["--local-user", self.identity]
            spawn(gpg_args,
                  dry_run=self.dry_run)

        # Fill in the data - send all the metadata in case we need to
        # register a new release
        content = open(filename,'rb').read()

        data = metadata_to_dict(self.distribution.metadata)

        # extra upload infos
        data[':action'] = 'file_upload'
        data['protcol_version'] = '1'
        data['content'] = [os.path.basename(filename), content]
        data['filetype'] = command
        data['pyversion'] = pyversion
        data['md5_digest'] = md5(content).hexdigest()

        comment = ''
        if command == 'bdist_dumb':
            comment = 'built for %s' % platform.platform(terse=1)
        data['comment'] = comment

        if self.sign:
            data['gpg_signature'] = [(os.path.basename(filename) + ".asc",
                                      open(filename+".asc").read())]

        # set up the authentication
        auth = "Basic " + standard_b64encode(self.username + ":" +
                                             self.password)

        # Build up the MIME payload for the POST data
        boundary = '--------------GHSKFJDLGDS7543FJKLFHRE75642756743254'
        sep_boundary = '\n--' + boundary
        end_boundary = sep_boundary + '--'
        body = StringIO()
        file_fields = ('content', 'gpg_signature')

        for key, values in data.items():
            # handle multiple entries for the same name
            if not isinstance(values, (tuple, list)):
                values = [values]

            content_dispo = 'Content-Disposition: form-data; name="%s"' % key

            if key in file_fields:
                filename_, content = values
                filename_ = ';filename="%s"' % filename_
                body.write(sep_boundary)
                body.write("\n")
                body.write(content_dispo)
                body.write(filename_)
                body.write("\n\n")
                body.write(content)
            else:
                for value in values:
                    body.write(sep_boundary)
                    body.write("\n")
                    body.write(content_dispo)
                    body.write("\n\n")
                    body.write(value)
                    if value and value[-1] == '\r':
                        # write an extra newline (lurve Macs)
                        body.write('\n')

        body.write(end_boundary)
        body.write("\n")
        body = body.getvalue()

        self.announce("Submitting %s to %s" % (filename, self.repository),
                      log.INFO)

        # build the Request
        headers = {'Content-type':
                        'multipart/form-data; boundary=%s' % boundary,
                   'Content-length': str(len(body)),
                   'Authorization': auth}

        request = Request(self.repository, data=body,
                          headers=headers)
        # send the data
        try:
            result = urlopen(request)
            status = result.code
            reason = result.msg
        except socket.error, e:
            self.announce(str(e), log.ERROR)
            return
        except HTTPError, e:
            status = e.code
            reason = e.msg

        if status == 200:
            self.announce('Server response (%s): %s' % (status, reason),
                          log.INFO)
        else:
            self.announce('Upload failed (%s): %s' % (status, reason),
                          log.ERROR)

        if self.show_response:
            msg = '\n'.join(('-' * 75, result.read(), '-' * 75))
            self.announce(msg, log.INFO)
