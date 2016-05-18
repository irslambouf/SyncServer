"""Tests for the distutils2.index.xmlrpc module."""

from distutils2.tests.pypi_server import use_xmlrpc_server
from distutils2.tests import unittest, run_unittest
from distutils2.index.xmlrpc import Client
from distutils2.install import (get_infos, InstallationException)
from distutils2.metadata import DistributionMetadata


class FakeDist(object):
    """A fake distribution object, for tests"""
    def __init__(self, name, version, deps):
        self.name = name
        self.version = version
        self.metadata = DistributionMetadata()
        self.metadata['Requires-Dist'] = deps
        self.metadata['Provides-Dist'] = ['%s (%s)' % (name, version)]

    def __repr__(self):
        return '<FakeDist %s>' % self.name


def get_fake_dists(dists):
    objects = []
    for (name, version, deps) in dists:
        objects.append(FakeDist(name, version, deps))
    return objects


class TestInstallWithDeps(unittest.TestCase):
    def _get_client(self, server, *args, **kwargs):
        return Client(server.full_address, *args, **kwargs)

    def _get_results(self, output):
        """return a list of results"""
        installed = [(o.name, '%s' % o.version) for o in output['install']]
        remove = [(o.name, '%s' % o.version) for o in output['remove']]
        conflict = [(o.name, '%s' % o.version) for o in output['conflict']]
        return (installed, remove, conflict)

    @use_xmlrpc_server()
    def test_existing_deps(self, server):
        # Test that the installer get the dependencies from the metadatas
        # and ask the index for this dependencies.
        # In this test case, we have choxie that is dependent from towel-stuff
        # 0.1, which is in-turn dependent on bacon <= 0.2:
        # choxie -> towel-stuff -> bacon.
        # Each release metadata is not provided in metadata 1.2.
        client = self._get_client(server)
        archive_path = '%s/distribution.tar.gz' % server.full_address
        server.xmlrpc.set_distributions([
            {'name':'choxie',
             'version': '2.0.0.9',
             'requires_dist': ['towel-stuff (0.1)',],
             'url': archive_path},
            {'name':'towel-stuff',
             'version': '0.1',
             'requires_dist': ['bacon (<= 0.2)',],
             'url': archive_path},
            {'name':'bacon',
             'version': '0.1',
             'requires_dist': [],
             'url': archive_path},
            ])
        installed = get_fake_dists([('bacon', '0.1', []),])
        output = get_infos("choxie", index=client,
                           installed=installed)

        # we dont have installed bacon as it's already installed on the system.
        self.assertEqual(0, len(output['remove']))
        self.assertEqual(2, len(output['install']))
        readable_output = [(o.name, '%s' % o.version)
                           for o in output['install']]
        self.assertIn(('towel-stuff', '0.1'), readable_output)
        self.assertIn(('choxie', '2.0.0.9'), readable_output)

    @use_xmlrpc_server()
    def test_upgrade_existing_deps(self, server):
        # Tests that the existing distributions can be upgraded if needed.
        client = self._get_client(server)
        archive_path = '%s/distribution.tar.gz' % server.full_address
        server.xmlrpc.set_distributions([
            {'name':'choxie',
             'version': '2.0.0.9',
             'requires_dist': ['towel-stuff (0.1)',],
             'url': archive_path},
            {'name':'towel-stuff',
             'version': '0.1',
             'requires_dist': ['bacon (>= 0.2)',],
             'url': archive_path},
            {'name':'bacon',
             'version': '0.2',
             'requires_dist': [],
             'url': archive_path},
            ])

        output = get_infos("choxie", index=client, installed=
                           get_fake_dists([('bacon', '0.1', []),]))
        installed = [(o.name, '%s' % o.version) for o in output['install']]

        # we need bacon 0.2, but 0.1 is installed.
        # So we expect to remove 0.1 and to install 0.2 instead.
        remove = [(o.name, '%s' % o.version) for o in output['remove']]
        self.assertIn(('choxie', '2.0.0.9'), installed)
        self.assertIn(('towel-stuff', '0.1'), installed)
        self.assertIn(('bacon', '0.2'), installed)
        self.assertIn(('bacon', '0.1'), remove)
        self.assertEqual(0, len(output['conflict']))

    @use_xmlrpc_server()
    def test_conflicts(self, server):
        # Tests that conflicts are detected
        client = self._get_client(server)
        archive_path = '%s/distribution.tar.gz' % server.full_address
        server.xmlrpc.set_distributions([
            {'name':'choxie',
             'version': '2.0.0.9',
             'requires_dist': ['towel-stuff (0.1)',],
             'url': archive_path},
            {'name':'towel-stuff',
             'version': '0.1',
             'requires_dist': ['bacon (>= 0.2)',],
             'url': archive_path},
            {'name':'bacon',
             'version': '0.2',
             'requires_dist': [],
             'url': archive_path},
            ])
        already_installed = [('bacon', '0.1', []),
                             ('chicken', '1.1', ['bacon (0.1)'])]
        output = get_infos("choxie", index=client, installed=
                           get_fake_dists(already_installed))

        # we need bacon 0.2, but 0.1 is installed.
        # So we expect to remove 0.1 and to install 0.2 instead.
        installed, remove, conflict = self._get_results(output)
        self.assertIn(('choxie', '2.0.0.9'), installed)
        self.assertIn(('towel-stuff', '0.1'), installed)
        self.assertIn(('bacon', '0.2'), installed)
        self.assertIn(('bacon', '0.1'), remove)
        self.assertIn(('chicken', '1.1'), conflict)

    @use_xmlrpc_server()
    def test_installation_unexisting_project(self, server):
        # Test that the isntalled raises an exception if the project does not
        # exists.
        client = self._get_client(server)
        self.assertRaises(InstallationException, get_infos,
                          'unexistant project', index=client)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestInstallWithDeps))
    return suite

if __name__ == '__main__':
    run_unittest(test_suite())
