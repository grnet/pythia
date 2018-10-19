import django
from django.template.base import VariableNode
from django.template.loader import get_template
from django.template.loader_tags import (
    TextNode, BlockNode, 
    IncludeNode, ExtendsNode, Variable
)
from django.template.defaulttags import (
    CommentNode, CsrfTokenNode,
    AutoEscapeControlNode, IfNode, WithNode, ForNode
)

from collections import OrderedDict
import copy
import os
import ast

class TemplateTraverser:
    """ Provides the core functionality for traversing a django template's AST """
    def __init__(self, disable_warnings, filters):
        # TODO: Based on disable_warnings, set a logger's level instead
        self.dangerous_filters = filters
        self.ctx = Context()
        self.disable_warnings = disable_warnings
        self.results = []

    def traverse_template(self, tpl_path, tpl):
        origin = Origin(tpl_path)
        for node in tpl:
            self._traverse_node(origin, node, self.ctx)

    def _traverse_node(self, origin, node, ctx):
        # NOTE: Deep copy is need because dictionaries are
        # passed by reference.
        ctx = copy.deepcopy(ctx)

        cls = node.__class__

        ignored_node_types = [CommentNode, CsrfTokenNode, TextNode]
        # TODO: Maybe csrftokenNode holds all children nodes and so
        # it shouldn't be ignored
        if cls in ignored_node_types:
            return

        elif cls == VariableNode:
            tokens = node.filter_expression.token.split("|")
            var_name, filters = tokens[0], tokens[1:]

            # This is needed for cases like {{ vuln|  safe }}
            filters = [f.strip(" ") for f in filters]

            for f in filters:
                if f in self.dangerous_filters:
                    # print("[{}]: The '{}' filter was used for '{}' " \
                    #         "with context: '{}'\n" \
                    #         .format(origin, f, var_name, ctx))
                    origin = copy.deepcopy(origin)
                    self.results.append((origin, f, var_name, ctx))
                    return

        elif cls == AutoEscapeControlNode:
            # If {% autoescape off %} occurs
            if not node.setting:
                return
            # print("Autoescape is turned OFF within: {}\n".format(origin))

        elif cls == BlockNode or cls == IfNode:
            # Check from context if block node were overriden.
            for snode in node.nodelist:
                self._traverse_node(origin, snode, ctx)

        elif cls == IncludeNode:
            # TODO: Handle relative paths aswell
            if node.template.var.__class__ == Variable:
                if not self.disable_warnings:
                    return
                    # print("[{}]: Custom filter was used to find the included " \
                    #     "template's name, investigate: {}\n" \
                    #     .format(origin, node.template.token))
            inclusion_path = node.template.var

            if inclusion_path.startswith((".", "..")) and django.VERSION < (1, 10, 0):
                print("[*] relative paths are not supported for django < 1.10.0")
                return

            # Handle exceptions
            tpl = get_template(inclusion_path).template
            origin = copy.deepcopy(origin)
            origin.append(inclusion_path)
            for snode in tpl:
                self._traverse_node(origin, snode, ctx)

        elif cls == ExtendsNode:
            extension_path = node.parent_name.var

            # {% extends var_path %} is not supported
            if extension_path.__class__ == Variable:
                print("[*] variable paths are not supported, ignoring extension")
                sys.exit()
                return

            if extension_path.startswith(("..", ".")) and django.VERSION < (1, 10, 0):
                print("[*] relative paths are not supported for django < 1.10.0")
                return

            # Handle exceptions
            tpl = get_template(extension_path).template

            extension_origin = copy.deepcopy(origin)
            extension_origin.append(extension_path)

            # Follow the extending base template
            # TODO: Check if another template has already traversed the
            # template we are about to extend
            for parent_node in tpl:
                self._traverse_node(extension_origin, parent_node, ctx)

            # Then traverse the origin template
            for sub_node in node.nodelist:
                self._traverse_node(origin, sub_node, ctx)

        elif cls == WithNode:
            # TODO: This is odd, research
            key, val = node.extra_context.popitem()
            if val.__class__ == Variable:
                val = val.var.var
            else:
                val = val.var
            ctx[key] = val
            for snode in node.nodelist:
                self._traverse_node(origin, snode, ctx)

        elif cls == ForNode:
            # In the case of {% key, val in dict %}
            # loopvars would be ['key', 'val']
            for var in node.loopvars:
                ctx[var] = node.sequence.token
            for sub_node in node.nodelist_loop:
                self._traverse_node(origin, sub_node, ctx)


class NodeVisitor(ast.NodeVisitor):
    """
    Collects all templates used in a module's views

    After running NodeVisitor.visit() on an ast, `templates` will hold 
    a list of tuple with the following:

    [(view, template, lineno), ...], where lineno is where the template's context is defined

    `assignments` holds all assignments for the current function's scope
    `current_func` is the current function we are traversing
    """
    def __init__(self):
        self.templates = []
        self.current_func = None
        self.assignments = {}
        super(NodeVisitor, self).__init__()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            function_called = node.func.attr
        else:
            function_called = node.func.id

        if function_called == 'render':
            # In case the caller didn't provide any context
            if len(node.args) == 0 or isinstance(node.args[0], ast.Call):
                """
                This is the following
                t = get_template("test.html")
                t.render(RequestContext(request))
                TODO: Check if it is an attribute call 
                """
                self.templates.append((self.current_func.name, "unknown", node.lineno))
            else:
                if len(node.args) == 2:
                    lineno = node.lineno
                elif isinstance(node.args[2], ast.Dict):
                    lineno = node.args[2].lineno
                else:
                    lineno = self.assignments[node.args[2].id].lineno
                self.templates.append((self.current_func.name, node.args[1].s, lineno))
        self.generic_visit(node)

    def visit_Assign(self,node):
        """ 
        Holds a per-function cache for all assignments 

        This helps in the case of:
        return_dict = {"users": User.objects.all()}
        ...
        return render(request, "users.html", return_dict)
        """
        for target in node.targets:
            # TODO: Handle subscript also
            if isinstance(target, ast.Attribute):
                var_name = target.attr
            elif isinstance(target, ast.Name):
                var_name = target.id
            else:
                continue
            self.assignments[var_name] = node.value
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """
        Cleans up after previous function's assignments.
        Also hooks the current node as the current_func.
        """
        self.current_func = node
        self.assignments = {}
        self.generic_visit(node)

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
