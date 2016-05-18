"""Tests for the distutils2.index.dist module."""

import os

from distutils2.tests.pypi_server import use_pypi_server
from distutils2.tests import run_unittest
from distutils2.tests import unittest
from distutils2.tests.support import TempdirManager
from distutils2.version import VersionPredicate
from distutils2.index.errors import HashDoesNotMatch, UnsupportedHashName
from distutils2.index.dist import (ReleaseInfo, ReleasesList, DistInfo,
                                   split_archive_name, get_infos_from_url)


def Dist(*args, **kwargs):
    # DistInfo takes a release as a first parameter, avoid this in tests.
    return DistInfo(None, *args, **kwargs)


class TestReleaseInfo(unittest.TestCase):

    def test_instantiation(self):
        # Test the DistInfo class provides us the good attributes when
        # given on construction
        release = ReleaseInfo("FooBar", "1.1")
        self.assertEqual("FooBar", release.name)
        self.assertEqual("1.1", "%s" % release.version)

    def test_add_dist(self):
        # empty distribution type should assume "sdist"
        release = ReleaseInfo("FooBar", "1.1")
        release.add_distribution(url="http://example.org/")
        # should not fail
        release['sdist']

    def test_get_unknown_distribution(self):
        # should raise a KeyError
        pass

    def test_get_infos_from_url(self):
        # Test that the the URLs are parsed the right way
        url_list = {
            'FooBar-1.1.0.tar.gz': {
                'name': 'foobar',  # lowercase the name
                'version': '1.1.0',
            },
            'Foo-Bar-1.1.0.zip': {
                'name': 'foo-bar',  # keep the dash
                'version': '1.1.0',
            },
            'foobar-1.1b2.tar.gz#md5=123123123123123': {
                'name': 'foobar',
                'version': '1.1b2',
                'url': 'http://example.org/foobar-1.1b2.tar.gz',  # no hash
                'hashval': '123123123123123',
                'hashname': 'md5',
            },
            'foobar-1.1-rc2.tar.gz': {  # use suggested name
                'name': 'foobar',
                'version': '1.1c2',
                'url': 'http://example.org/foobar-1.1-rc2.tar.gz',
            }
        }

        for url, attributes in url_list.items():
            # for each url
            infos = get_infos_from_url("http://example.org/" + url)
            for attribute, expected in attributes.items():
                got = infos.get(attribute)
                if attribute == "version":
                    self.assertEqual("%s" % got, expected)
                else:
                    self.assertEqual(got, expected)

    def test_split_archive_name(self):
        # Test we can split the archive names
        names = {
            'foo-bar-baz-1.0-rc2': ('foo-bar-baz', '1.0c2'),
            'foo-bar-baz-1.0': ('foo-bar-baz', '1.0'),
            'foobarbaz-1.0': ('foobarbaz', '1.0'),
        }
        for name, results in names.items():
            self.assertEqual(results, split_archive_name(name))


class TestDistInfo(TempdirManager, unittest.TestCase):

    def test_get_url(self):
        # Test that the url property works well

        d = Dist(url="test_url")
        self.assertDictEqual(d.url, {
            "url": "test_url",
            "is_external": True,
            "hashname": None,
            "hashval": None,
        })

        # add a new url
        d.add_url(url="internal_url", is_external=False)
        self.assertEqual(d._url, None)
        self.assertDictEqual(d.url, {
            "url": "internal_url",
            "is_external": False,
            "hashname": None,
            "hashval": None,
        })
        self.assertEqual(2, len(d.urls))

    def test_comparison(self):
        # Test that we can compare DistInfoributionInfoList
        foo1 = ReleaseInfo("foo", "1.0")
        foo2 = ReleaseInfo("foo", "2.0")
        bar = ReleaseInfo("bar", "2.0")
        # assert we use the version to compare
        self.assertTrue(foo1 < foo2)
        self.assertFalse(foo1 > foo2)
        self.assertFalse(foo1 == foo2)

        # assert we can't compare dists with different names
        self.assertRaises(TypeError, foo1.__eq__, bar)

    @use_pypi_server("downloads_with_md5")
    def test_download(self, server):
        # Download is possible, and the md5 is checked if given

        url = "%s/simple/foobar/foobar-0.1.tar.gz" % server.full_address
        # check md5 if given
        dist = Dist(url=url, hashname="md5",
                    hashval="d41d8cd98f00b204e9800998ecf8427e")
        dist.download(self.mkdtemp())

        # a wrong md5 fails
        dist2 = Dist(url=url, hashname="md5", hashval="wrongmd5")

        self.assertRaises(HashDoesNotMatch, dist2.download, self.mkdtemp())

        # we can omit the md5 hash
        dist3 = Dist(url=url)
        dist3.download(self.mkdtemp())

        # and specify a temporary location
        # for an already downloaded dist
        path1 = self.mkdtemp()
        dist3.download(path=path1)
        # and for a new one
        path2_base = self.mkdtemp()
        dist4 = Dist(url=url)
        path2 = dist4.download(path=path2_base)
        self.assertTrue(path2_base in path2)

    def test_hashname(self):
        # Invalid hashnames raises an exception on assignation
        Dist(hashname="md5", hashval="value")

        self.assertRaises(UnsupportedHashName, Dist,
                          hashname="invalid_hashname",
                          hashval="value")


class TestReleasesList(unittest.TestCase):

    def test_filter(self):
        # Test we filter the distributions the right way, using version
        # predicate match method
        releases = ReleasesList('FooBar', (
            ReleaseInfo("FooBar", "1.1"),
            ReleaseInfo("FooBar", "1.1.1"),
            ReleaseInfo("FooBar", "1.2"),
            ReleaseInfo("FooBar", "1.2.1"),
        ))
        filtered = releases.filter(VersionPredicate("FooBar (<1.2)"))
        self.assertNotIn(releases[2], filtered)
        self.assertNotIn(releases[3], filtered)
        self.assertIn(releases[0], filtered)
        self.assertIn(releases[1], filtered)

    def test_append(self):
        # When adding a new item to the list, the behavior is to test if
        # a release with the same name and version number already exists,
        # and if so, to add a new distribution for it. If the distribution type
        # is already defined too, add url informations to the existing DistInfo
        # object.

        releases = ReleasesList("FooBar", [
            ReleaseInfo("FooBar", "1.1", url="external_url",
                        dist_type="sdist"),
        ])
        self.assertEqual(1, len(releases))
        releases.add_release(release=ReleaseInfo("FooBar", "1.1",
                                                 url="internal_url",
                                                 is_external=False,
                                                 dist_type="sdist"))
        self.assertEqual(1, len(releases))
        self.assertEqual(2, len(releases[0]['sdist'].urls))

        releases.add_release(release=ReleaseInfo("FooBar", "1.1.1",
                                                 dist_type="sdist"))
        self.assertEqual(2, len(releases))

        # when adding a distribution whith a different type, a new distribution
        # has to be added.
        releases.add_release(release=ReleaseInfo("FooBar", "1.1.1",
                                                 dist_type="bdist"))
        self.assertEqual(2, len(releases))
        self.assertEqual(2, len(releases[1].dists))

    def test_prefer_final(self):
        # Can order the distributions using prefer_final

        fb10 = ReleaseInfo("FooBar", "1.0")  # final distribution
        fb11a = ReleaseInfo("FooBar", "1.1a1")  # alpha
        fb12a = ReleaseInfo("FooBar", "1.2a1")  # alpha
        fb12b = ReleaseInfo("FooBar", "1.2b1")  # beta
        dists = ReleasesList("FooBar", [fb10, fb11a, fb12a, fb12b])

        dists.sort_releases(prefer_final=True)
        self.assertEqual(fb10, dists[0])

        dists.sort_releases(prefer_final=False)
        self.assertEqual(fb12b, dists[0])

#    def test_prefer_source(self):
#        # Ordering support prefer_source
#        fb_source = Dist("FooBar", "1.0", type="source")
#        fb_binary = Dist("FooBar", "1.0", type="binary")
#        fb2_binary = Dist("FooBar", "2.0", type="binary")
#        dists = ReleasesList([fb_binary, fb_source])
#
#        dists.sort_distributions(prefer_source=True)
#        self.assertEqual(fb_source, dists[0])
#
#        dists.sort_distributions(prefer_source=False)
#        self.assertEqual(fb_binary, dists[0])
#
#        dists.append(fb2_binary)
#        dists.sort_distributions(prefer_source=True)
#        self.assertEqual(fb2_binary, dists[0])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestDistInfo))
    suite.addTest(unittest.makeSuite(TestReleaseInfo))
    suite.addTest(unittest.makeSuite(TestReleasesList))
    return suite

if __name__ == '__main__':
    run_unittest(test_suite())
