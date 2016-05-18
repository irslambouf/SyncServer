"""Tests for distutils.command.bdist."""
import urllib
import urllib2
import os.path

from distutils2.tests.pypi_server import PyPIServer, PYPI_DEFAULT_STATIC_PATH
from distutils2.tests import unittest


class PyPIServerTest(unittest.TestCase):

    def test_records_requests(self):
        # We expect that PyPIServer can log our requests
        server = PyPIServer()
        server.start()
        self.assertEqual(len(server.requests), 0)

        data = "Rock Around The Bunker"
        headers = {"X-test-header": "Mister Iceberg"}

        request = urllib2.Request(server.full_address, data, headers)
        urllib2.urlopen(request)
        self.assertEqual(len(server.requests), 1)
        handler, request_data = server.requests[-1]
        self.assertIn("Rock Around The Bunker", request_data)
        self.assertIn("x-test-header", handler.headers.dict)
        self.assertEqual(handler.headers.dict["x-test-header"],
                         "Mister Iceberg")
        server.stop()

    def test_serve_static_content(self):
        # PYPI Mocked server can serve static content from disk.

        def uses_local_files_for(server, url_path):
            """Test that files are served statically (eg. the output from the
            server is the same than the one made by a simple file read.
            """
            url = server.full_address + url_path
            request = urllib2.Request(url)
            response = urllib2.urlopen(request)
            file = open(PYPI_DEFAULT_STATIC_PATH + "/test_pypi_server" +
               url_path)
            return response.read() == file.read()

        server = PyPIServer(static_uri_paths=["simple", "external"],
            static_filesystem_paths=["test_pypi_server"])
        server.start()

        # the file does not exists on the disc, so it might not be served
        url = server.full_address + "/simple/unexisting_page"
        request = urllib2.Request(url)
        try:
            urllib2.urlopen(request)
        except urllib2.HTTPError,e:
            self.assertEqual(e.code, 404)

        # now try serving a content that do exists
        self.assertTrue(uses_local_files_for(server, "/simple/index.html"))

        # and another one in another root path
        self.assertTrue(uses_local_files_for(server, "/external/index.html"))
        server.stop()


def test_suite():
    return unittest.makeSuite(PyPIServerTest)

if __name__ == '__main__':
    unittest.main(defaultTest="test_suite")
