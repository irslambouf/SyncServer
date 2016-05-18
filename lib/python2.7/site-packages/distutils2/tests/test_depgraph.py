"""Tests for distutils.depgraph """

from distutils2.tests import unittest, support
from distutils2 import depgraph
from distutils2._backport import pkgutil

import os
import sys
import re
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

class DepGraphTestCase(support.LoggingCatcher,
                       unittest.TestCase):

    DISTROS_DIST = ('choxie', 'grammar', 'towel-stuff')
    DISTROS_EGG  = ('bacon', 'banana', 'strawberry', 'cheese')
    BAD_EGGS = ('nut',)

    EDGE = re.compile(
           r'"(?P<from>.*)" -> "(?P<to>.*)" \[label="(?P<label>.*)"\]'
           )

    def tearDown(self):
        super(DepGraphTestCase, self).tearDown()
        pkgutil.enable_cache()
        sys.path = self.sys_path

    def checkLists(self, l1, l2):
        """ Compare two lists without taking the order into consideration """
        self.assertListEqual(sorted(l1), sorted(l2))

    def setUp(self):
        super(DepGraphTestCase, self).setUp()
        path = os.path.join(os.path.dirname(__file__), '..', '_backport',
                            'tests', 'fake_dists')
        path = os.path.abspath(path)
        self.sys_path = sys.path[:]
        sys.path[0:0] = [path]
        pkgutil.disable_cache()

    def test_generate_graph(self):
        dists = []
        for name in self.DISTROS_DIST:
            dist = pkgutil.get_distribution(name)
            self.assertNotEqual(dist, None)
            dists.append(dist)

        choxie, grammar, towel = dists

        graph = depgraph.generate_graph(dists)

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[choxie]]
        self.checkLists([('towel-stuff', 'towel-stuff (0.1)')], deps)
        self.assertTrue(choxie in graph.reverse_list[towel])
        self.checkLists(graph.missing[choxie], ['nut'])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[grammar]]
        self.checkLists([], deps)
        self.checkLists(graph.missing[grammar], ['truffles (>=1.2)'])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[towel]]
        self.checkLists([], deps)
        self.checkLists(graph.missing[towel], ['bacon (<=0.2)'])

    def test_generate_graph_egg(self):
        dists = []
        for name in self.DISTROS_DIST + self.DISTROS_EGG:
            dist = pkgutil.get_distribution(name, use_egg_info=True)
            self.assertNotEqual(dist, None)
            dists.append(dist)

        choxie, grammar, towel, bacon, banana, strawberry, cheese = dists

        graph = depgraph.generate_graph(dists)

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[choxie]]
        self.checkLists([('towel-stuff', 'towel-stuff (0.1)')], deps)
        self.assertTrue(choxie in graph.reverse_list[towel])
        self.checkLists(graph.missing[choxie], ['nut'])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[grammar]]
        self.checkLists([('bacon', 'truffles (>=1.2)')], deps)
        self.checkLists(graph.missing[grammar], [])
        self.assertTrue(grammar in graph.reverse_list[bacon])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[towel]]
        self.checkLists([('bacon', 'bacon (<=0.2)')], deps)
        self.checkLists(graph.missing[towel], [])
        self.assertTrue(towel in graph.reverse_list[bacon])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[bacon]]
        self.checkLists([], deps)
        self.checkLists(graph.missing[bacon], [])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[banana]]
        self.checkLists([('strawberry', 'strawberry (>=0.5)')], deps)
        self.checkLists(graph.missing[banana], [])
        self.assertTrue(banana in graph.reverse_list[strawberry])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[strawberry]]
        self.checkLists([], deps)
        self.checkLists(graph.missing[strawberry], [])

        deps = [(x.name, y) for (x,y) in graph.adjacency_list[cheese]]
        self.checkLists([], deps)
        self.checkLists(graph.missing[cheese], [])

    def test_dependent_dists(self):
        dists = []
        for name in self.DISTROS_DIST:
            dist = pkgutil.get_distribution(name)
            self.assertNotEqual(dist, None)
            dists.append(dist)

        choxie, grammar, towel = dists

        deps = [d.name for d in depgraph.dependent_dists(dists, choxie)]
        self.checkLists([], deps)

        deps = [d.name for d in depgraph.dependent_dists(dists, grammar)]
        self.checkLists([], deps)

        deps = [d.name for d in depgraph.dependent_dists(dists, towel)]
        self.checkLists(['choxie'], deps)


    def test_dependent_dists_egg(self):
        dists = []
        for name in self.DISTROS_DIST + self.DISTROS_EGG:
            dist = pkgutil.get_distribution(name, use_egg_info=True)
            self.assertNotEqual(dist, None)
            dists.append(dist)

        choxie, grammar, towel, bacon, banana, strawberry, cheese = dists

        deps = [d.name for d in depgraph.dependent_dists(dists, choxie)]
        self.checkLists([], deps)

        deps = [d.name for d in depgraph.dependent_dists(dists, grammar)]
        self.checkLists([], deps)

        deps = [d.name for d in depgraph.dependent_dists(dists, towel)]
        self.checkLists(['choxie'], deps)

        deps = [d.name for d in depgraph.dependent_dists(dists, bacon)]
        self.checkLists(['choxie', 'towel-stuff', 'grammar'], deps)

        deps = [d.name for d in depgraph.dependent_dists(dists, strawberry)]
        self.checkLists(['banana'], deps)

        deps = [d.name for d in depgraph.dependent_dists(dists, cheese)]
        self.checkLists([], deps)

    def test_graph_to_dot(self):
        expected = (
            ('towel-stuff', 'bacon', 'bacon (<=0.2)'),
            ('grammar', 'bacon', 'truffles (>=1.2)'),
            ('choxie', 'towel-stuff', 'towel-stuff (0.1)'),
            ('banana', 'strawberry', 'strawberry (>=0.5)')
        )

        dists = []
        for name in self.DISTROS_DIST + self.DISTROS_EGG:
            dist = pkgutil.get_distribution(name, use_egg_info=True)
            self.assertNotEqual(dist, None)
            dists.append(dist)

        graph = depgraph.generate_graph(dists)
        buf = StringIO.StringIO()
        depgraph.graph_to_dot(graph, buf)
        buf.seek(0)
        matches = []
        lines = buf.readlines()
        for line in lines[1:-1]: # skip the first and the last lines
            if line[-1] == '\n':
                line = line[:-1]
            match = self.EDGE.match(line.strip())
            self.assertTrue(match is not None)
            matches.append(match.groups())

        self.checkLists(matches, expected)

    def test_graph_bad_version_to_dot(self):
        expected = (
            ('towel-stuff', 'bacon', 'bacon (<=0.2)'),
            ('grammar', 'bacon', 'truffles (>=1.2)'),
            ('choxie', 'towel-stuff', 'towel-stuff (0.1)'),
            ('banana', 'strawberry', 'strawberry (>=0.5)')
        )

        dists = []
        for name in self.DISTROS_DIST + self.DISTROS_EGG + self.BAD_EGGS:
            dist = pkgutil.get_distribution(name, use_egg_info=True)
            self.assertNotEqual(dist, None)
            dists.append(dist)

        graph = depgraph.generate_graph(dists)
        buf = StringIO.StringIO()
        depgraph.graph_to_dot(graph, buf)
        buf.seek(0)
        matches = []
        lines = buf.readlines()
        for line in lines[1:-1]: # skip the first and the last lines
            if line[-1] == '\n':
                line = line[:-1]
            match = self.EDGE.match(line.strip())
            self.assertTrue(match is not None)
            matches.append(match.groups())

        self.checkLists(matches, expected)

    def test_main(self):
        tempout = StringIO.StringIO()
        old = sys.stdout
        sys.stdout = tempout
        oldargv = sys.argv[:]
        sys.argv[:] = ['script.py']
        try:
            try:
                depgraph.main()
            except SystemExit:
                pass
        finally:
            sys.stdout = old
            sys.argv[:] = oldargv

        # checks what main did XXX could do more here
        tempout.seek(0)
        res = tempout.read()
        self.assertTrue('towel' in res)


def test_suite():
    return unittest.makeSuite(DepGraphTestCase)

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
