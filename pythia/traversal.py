import django
from django.template.base import VariableNode
from django.template.loader import get_template
from django.template.loader_tags import (
    TextNode, BlockNode, 
    IncludeNode, ExtendsNode, Template, Variable
)
from django.template.defaulttags import (
    CommentNode, CsrfTokenNode,
    AutoEscapeControlNode, IfNode, WithNode, ForNode
)

from distutils.version import StrictVersion
from collections import OrderedDict
import copy
import os

class Origin:
    """ Holds a list of extensions/inclusions of a certain template """

    def __init__(self, template_path):
        self.path = [template_path]

    def append(self, template_path):
        self.path.append(template_path)

    def __str__(self):
        """ Prints the origin path for both inclusions and extensions.

        For example,
        'admin/login.html -> admin/base.html'
        """
        return " -> ".join(self.path)

class Context(OrderedDict):
    """ A wrapper class for collections.OrderedDict """

    def __str__(self):
        """ Prints all the context values in a readable format

        For example,
        'var1->alias1 / var2->alias2'
        """
        formatted_values = [
            '{0}->{1}' \
            .format(key, value) for (key, value) in reversed(self.items())
        ]
        return " / ".join(formatted_values)

class Traverser:
    """ Provides the core functionality for traversing the template's AST """
    def __init__(self, disable_warnings, filters):
        # TODO: Based on warnings, construct a logger instead.
        self.dangerous_filters = filters
        self.ctx = Context()
        self.disable_warnings = disable_warnings
        self.results = []
        self.django_version = StrictVersion(django.get_version())

    def traverseNode(self, origin, node, ctx):
        # NOTE: Deep copy is need because dictionaries are
        # passed by reference.
        ctx = copy.deepcopy(ctx)

        cls = node.__class__

        ignored_node_types = [CommentNode, CsrfTokenNode, TextNode]
        if cls in ignored_node_types:
            return

        elif cls == VariableNode:
            tokens = node.filter_expression.token.split("|")
            var_name, filters = tokens[0], tokens[1:]

            # This is needed for cases like {{ vuln|  safe }}
            filters = [f.strip(" ") for f in filters]

            for f in filters:
                if f in self.dangerous_filters:
                    print("[{}]: The '{}' filter was used for '{}' " \
                            "with context: '{}'\n" \
                            .format(origin, f, var_name, ctx))
                    origin = copy.deepcopy(origin)
                    self.results.append((origin, f, var_name, ctx))
                    return

        elif cls == AutoEscapeControlNode:
            # If {% autoescape off %} occurs
            if not node.setting:
                print("Autoescape is turned OFF within: {}\n".format(origin))

        elif cls == BlockNode or cls == IfNode:
            # Check from context if block node were overriden.
            for snode in node.nodelist:
                self.traverseNode(origin, snode, ctx)

        elif cls == IncludeNode:
            # TODO: Handle relative paths aswell
            if node.template.var.__class__ == Variable:
                if not self.disable_warnings:
                    print("[{}]: Custom filter was used to find the included " \
                        "template's name, investigate: {}\n" \
                        .format(origin, node.template.token))
                return
            inclusion_path = node.template.var
            # Handle exceptions
            tpl = get_template(inclusion_path).template
            origin = copy.deepcopy(origin)
            origin.append(inclusion_path)
            for snode in tpl:
                self.traverseNode(origin, snode, ctx)

        elif cls == ExtendsNode:
            extension_path = node.parent_name.var

            # {% extends var_path %} is not supported
            if extension_path.__class__ == Variable:
                print("[*] variable paths are not supported, ignoring extension")
                sys.exit()
                return
            # Extensions were introduced in Django 1.10.0
            if ".." in extension_path and self.django_version < StrictVersion("1.10.0"):
                print("[*] relative paths are not supported for django < 1.10.0")
                return

            # Handle exceptions
            tpl = get_template(extension_path).template


            # NOTE: Deep copying is needed, because dictionaries are passed
            # by reference.
            extension_origin = copy.deepcopy(origin)
            extension_origin.append(extension_path)

            # Follow the extending base template
            for parent_node in tpl:
                self.traverseNode(extension_origin, parent_node, ctx)

            # Then traverse the origin template
            for sub_node in node.nodelist:
                self.traverseNode(origin, sub_node, ctx)

        elif cls == WithNode:
            # TODO: This is odd, research
            key, val = node.extra_context.popitem()
            if val.__class__ == Variable:
                val = val.var.var
            else:
                val = val.var
            ctx[key] = val
            for snode in node.nodelist:
                self.traverseNode(origin, snode, ctx)

        elif cls == ForNode:
            # In the case of {% key, val in dict %}
            # loopvars would be ['key', 'val']
            for var in node.loopvars:
                ctx[var] = node.sequence.token
            for sub_node in node.nodelist_loop:
                self.traverseNode(origin, sub_node, ctx)

    def traverseTemplate(self, tpl_path, tpl):
        origin = Origin(tpl_path)
        for node in tpl:
            self.traverseNode(origin, node, self.ctx)

    def draw_graph(self):
        """ Experimental dependency graph drawing

        Requires pygraphviz etc.
        """
        import networkx as nx
        from networkx.drawing.nx_agraph import write_dot, graphviz_layout
        import matplotlib.pyplot as plt
        G = nx.Graph()
        for (origin, filter, var_name, context) in self.results:
            root_node = origin.path.pop(0)
            G.add_node(root_node)
            for template in origin.path:
                if not G.has_node(template):
                    G.add_node(template)
                G.add_edge(root_node, template)

        plt.figure(3, figsize=(15,15))
        options = {
                "arrows": True,
                "with_labels": True,
                "node_size": 100,
                "font_size": 6,
                }
        nx.draw_circular(G, **options)
        plt.savefig('nx_test.png')
