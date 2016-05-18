# -*- encoding: utf-8 -*-
"""Tests for distutils.command.upload_docs."""
import os
import sys
import httplib
import shutil
import zipfile
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from distutils2.command import upload_docs as upload_docs_mod
from distutils2.command.upload_docs import (upload_docs, zip_dir,
                                            encode_multipart)
from distutils2.core import Distribution
from distutils2.errors import DistutilsFileError, DistutilsOptionError

from distutils2.tests import unittest, support
from distutils2.tests.pypi_server import PyPIServer, PyPIServerTestCase


EXPECTED_MULTIPART_OUTPUT = "\r\n".join([
'---x',
'Content-Disposition: form-data; name="a"',
'',
'b',
'---x',
'Content-Disposition: form-data; name="c"',
'',
'd',
'---x',
'Content-Disposition: form-data; name="e"; filename="f"',
'',
'g',
'---x',
'Content-Disposition: form-data; name="h"; filename="i"',
'',
'j',
'---x--',
'',
])

PYPIRC = """\
[distutils]
index-servers = server1

[server1]
repository = %s
username = real_slim_shady
password = long_island
"""

class UploadDocsTestCase(support.TempdirManager, support.EnvironGuard,
                         support.LoggingCatcher, PyPIServerTestCase):

    def setUp(self):
        super(UploadDocsTestCase, self).setUp()
        self.tmp_dir = self.mkdtemp()
        self.rc = os.path.join(self.tmp_dir, '.pypirc')
        os.environ['HOME'] = self.tmp_dir
        self.dist = Distribution()
        self.dist.metadata['Name'] = "distr-name"
        self.cmd = upload_docs(self.dist)

    def test_default_uploaddir(self):
        sandbox = self.mkdtemp()
        previous = os.getcwd()
        os.chdir(sandbox)
        try:
            os.mkdir("build")
            self.prepare_sample_dir("build")
            self.cmd.ensure_finalized()
            self.assertEqual(self.cmd.upload_dir, os.path.join("build", "docs"))
        finally:
            os.chdir(previous)

    def test_default_uploaddir_looks_for_doc_also(self):
        sandbox = self.mkdtemp()
        previous = os.getcwd()
        os.chdir(sandbox)
        try:
            os.mkdir("build")
            self.prepare_sample_dir("build")
            os.rename(os.path.join("build", "docs"), os.path.join("build", "doc"))
            self.cmd.ensure_finalized()
            self.assertEqual(self.cmd.upload_dir, os.path.join("build", "doc"))
        finally:
            os.chdir(previous)

    def prepare_sample_dir(self, sample_dir=None):
        if sample_dir is None:
            sample_dir = self.mkdtemp()
        os.mkdir(os.path.join(sample_dir, "docs"))
        self.write_file(os.path.join(sample_dir, "docs", "index.html"), "Ce mortel ennui")
        self.write_file(os.path.join(sample_dir, "index.html"), "Oh la la")
        return sample_dir

    def test_zip_dir(self):
        source_dir = self.prepare_sample_dir()
        compressed = zip_dir(source_dir)

        zip_f = zipfile.ZipFile(compressed)
        self.assertEqual(zip_f.namelist(), ['index.html', 'docs/index.html'])

    def test_encode_multipart(self):
        fields = [("a", "b"), ("c", "d")]
        files = [("e", "f", "g"), ("h", "i", "j")]
        content_type, body = encode_multipart(fields, files, "-x")
        self.assertEqual(content_type, "multipart/form-data; boundary=-x")
        self.assertEqual(body, EXPECTED_MULTIPART_OUTPUT)

    def prepare_command(self):
        self.cmd.upload_dir = self.prepare_sample_dir()
        self.cmd.ensure_finalized()
        self.cmd.repository = self.pypi.full_address
        self.cmd.username = "username"
        self.cmd.password = "password"

    def test_upload(self):
        self.prepare_command()
        self.cmd.run()

        self.assertEqual(len(self.pypi.requests), 1)
        handler, request_data = self.pypi.requests[-1]
        self.assertIn("content", request_data)
        self.assertIn("Basic", handler.headers.dict['authorization'])
        self.assertTrue(handler.headers.dict['content-type']
            .startswith('multipart/form-data;'))

        action, name, version, content =\
            request_data.split("----------------GHSKFJDLGDS7543FJKLFHRE75642756743254")[1:5]

        # check that we picked the right chunks
        self.assertIn('name=":action"', action)
        self.assertIn('name="name"', name)
        self.assertIn('name="version"', version)
        self.assertIn('name="content"', content)

        # check their contents
        self.assertIn("doc_upload", action)
        self.assertIn("distr-name", name)
        self.assertIn("docs/index.html", content)
        self.assertIn("Ce mortel ennui", content)

    def test_https_connection(self):
        https_called = False
        orig_https = upload_docs_mod.httplib.HTTPSConnection
        def https_conn_wrapper(*args):
            https_called = True
            return upload_docs_mod.httplib.HTTPConnection(*args) # the testing server is http
        upload_docs_mod.httplib.HTTPSConnection = https_conn_wrapper
        try:
            self.prepare_command()
            self.cmd.run()
            self.assertFalse(https_called)

            self.cmd.repository = self.cmd.repository.replace("http", "https")
            self.cmd.run()
            self.assertFalse(https_called)
        finally:
            upload_docs_mod.httplib.HTTPSConnection = orig_https

    def test_handling_response(self):
        calls = []
        def aggr(*args):
            calls.append(args)
        self.pypi.default_response_status = '403 Forbidden'
        self.prepare_command()
        self.cmd.announce = aggr
        self.cmd.run()
        message, _ = calls[-1]
        self.assertIn('Upload failed (403): Forbidden', message)

        calls = []
        self.pypi.default_response_status = '301 Moved Permanently'
        self.pypi.default_response_headers.append(("Location", "brand_new_location"))
        self.cmd.run()
        message, _ = calls[-1]
        self.assertIn('brand_new_location', message)

    def test_reads_pypirc_data(self):
        self.write_file(self.rc, PYPIRC % self.pypi.full_address)
        self.cmd.repository = self.pypi.full_address
        self.cmd.upload_dir = self.prepare_sample_dir()
        self.cmd.ensure_finalized()
        self.assertEqual(self.cmd.username, "real_slim_shady")
        self.assertEqual(self.cmd.password, "long_island")

    def test_checks_index_html_presence(self):
        self.cmd.upload_dir = self.prepare_sample_dir()
        os.remove(os.path.join(self.cmd.upload_dir, "index.html"))
        self.assertRaises(DistutilsFileError, self.cmd.ensure_finalized)

    def test_checks_upload_dir(self):
        self.cmd.upload_dir = self.prepare_sample_dir()
        shutil.rmtree(os.path.join(self.cmd.upload_dir))
        self.assertRaises(DistutilsOptionError, self.cmd.ensure_finalized)

    def test_show_response(self):
        self.prepare_command()
        self.cmd.show_response = True
        self.cmd.run()
        record = self.logs[-1][1]

        self.assertTrue(record, "should report the response")
        self.assertIn(self.pypi.default_response_data, record)

def test_suite():
    return unittest.makeSuite(UploadDocsTestCase)

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
