"""Fixer for setup() options.

All distutils or setuptools options are translated
into PEP 345-style options.
"""
from lib2to3.pytree import Leaf, Node
from lib2to3.pgen2 import token
from lib2to3.fixer_base import BaseFix

# XXX where is that defined ?
_ARG = 260

# name mapping : we want to convert
# all old-style options to distutils2 style
_OLD_NAMES = {'url': 'home_page',
              'long_description': 'description',
              'description': 'summary',
              'install_requires': 'requires_dist'}

_SEQUENCE_NAMES = ['requires_dist']


class FixSetupOptions(BaseFix):

    # XXX need to find something better here :
    # identify a setup call, whatever alias is used
    PATTERN = """
            power< name='setup' trailer< '(' [any] ')' > any* >
              """

    def _get_list(self, *nodes):
        """A List node, filled"""
        lbrace = Leaf(token.LBRACE, u"[")
        lbrace.prefix = u" "
        if len(nodes) > 0:
            nodes[0].prefix = u""
        return Node(self.syms.trailer,
                    [lbrace] +
                    [node.clone() for node in nodes] +
                    [Leaf(token.RBRACE, u"]")])

    def _fix_name(self, argument, remove_list):
        name = argument.children[0]

        if not hasattr(name, "next_sibling"):
            name.next_sibling = name.get_next_sibling()

        sibling = name.next_sibling
        if sibling is None or sibling.type != token.EQUAL:
            return False

        if name.value in _OLD_NAMES:
            name.value = _OLD_NAMES[name.value]
            if name.value in _SEQUENCE_NAMES:
                if not hasattr(sibling, "next_sibling"):
                    sibling.next_sibling = sibling.get_next_sibling()
                right_operand = sibling.next_sibling
                # replacing string -> list[string]
                if right_operand.type == token.STRING:
                    # we want this to be a list now
                    new_node = self._get_list(right_operand)
                    right_operand.replace(new_node)


            return True

        return False

    def transform(self, node, results):
        arglist = node.children[1].children[1]
        remove_list = []
        changed = False

        for subnode in arglist.children:
            if subnode.type != _ARG:
                continue
            if self._fix_name(subnode, remove_list) and not changed:
                changed = True

        for subnode in remove_list:
            subnode.remove()

        if changed:
            node.changed()
        return node
