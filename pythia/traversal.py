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

if django.VERSION >= (1, 9, 0):
    from django.template.exceptions import TemplateDoesNotExist
else:
    from django.template.base import TemplateDoesNotExist

from collections import OrderedDict
import copy
import os
import ast
import logging

log = logging.getLogger('pythia')

class TemplateTraverser:
    """ 
    Provides the core functionality for traversing a django template's AST 

    This class follows python's ast package's pattern:

    For all nodes, `visit` is going to be called.
    `visit` acts as the router function for all template tags.

    For example, for a `CommentNode`, `visit_CommentNode` will be called.
    If that function does not exist, then `generic_visit` will be called.

    `generic_visit` acts as the default handler for all unhandled template tags
    """
    def __init__(self, filters):
        self.dangerous_filters = filters
        self.results = {}

    def walk(self, tpl_path, tpl):
        origin = Origin(tpl_path)
        for node in tpl:
            self.visit(origin, node, Context())

    def visit(self, origin, node, ctx):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        # NOTE: Deep copy is need because dictionaries are passed by reference.
        ctx = copy.deepcopy(ctx)
        return visitor(origin, node, ctx)

    def generic_visit(self, origin, node, ctx):
        """ Ignore all other tags for now """
        return

    def visit_IncludeNode(self, origin, node, ctx):
        inclusion_path = node.template.var

        if inclusion_path.__class__ == Variable:
            log.warn("Variable paths are not supported, ignoring inclusion")
            return

        if inclusion_path.startswith((".", "..")) and django.VERSION < (1, 10, 0):
            log.warn("Relative paths are not supported for django < 1.10.0")
            return

        try:
            tpl = get_template(inclusion_path).template
        except TemplateDoesNotExist:
            log.warn("Attempted to include '%s' and it does not exist" % extension_path)
            return

        origin = copy.deepcopy(origin)
        origin.append(inclusion_path)
        for sub_node in tpl:
            self.visit(origin, sub_node, ctx)

    def visit_ExtendsNode(self, origin, node, ctx):
        extension_path = node.parent_name.var

        if extension_path.__class__ == Variable:
            log.warn("variable paths are not supported, ignoring extension")
            return

        if extension_path.startswith((".", "..")) and django.VERSION < (1, 10, 0):
            log.warn("relative paths are not supported for django < 1.10.0")
            return

        try:
            tpl = get_template(extension_path).template
        except TemplateDoesNotExist:
            log.warn("Attempted to extend '%s' and it does not exist" % extension_path)
            return

        extension_origin = copy.deepcopy(origin)
        extension_origin.append(extension_path)

        # TODO: Check if another template has already traversed the
        # template we are about to extend
        for extending_tpl_node in tpl:
            self.visit(extension_origin, extending_tpl_node, ctx)

        for sub_node in node.nodelist:
            self.visit(origin, sub_node, ctx)

    def visit_ForNode(self, origin, node, ctx):
        # In the case of {% key, val in dict %}
        # loopvars would be ['key', 'val']
        for var in node.loopvars:
            ctx[var] = node.sequence.token
        for sub_node in node.nodelist_loop:
            self.visit(origin, sub_node, ctx)

    def visit_VariableNode(self, origin, node, ctx):
        tokens = node.filter_expression.token.split("|")
        var_name, filters = tokens[0], tokens[1:]

        # This is needed for cases like {{ vuln|  safe }}
        filters = [f.strip(" ") for f in filters]

        if ctx.autoescape:
            self.results[origin.path[0]] = (origin, 'autoescape', var_name, ctx)
            return

        for f in filters:
            if f in self.dangerous_filters:
                log.debug("[{}]: The '{}' filter was used for '{}' " \
                        "with context: '{}'" \
                        .format(origin, f, var_name, ctx))
                origin = copy.deepcopy(origin)
                self.results[origin.path[0]] = (origin, f, var_name, ctx)

    def visit_WithNode(self, origin, node, ctx):
        key, val = node.extra_context.popitem()
        if val.__class__ == Variable:
            val = val.var.var
        else:
            val = val.var
        ctx[key] = val
        for sub_node in node.nodelist:
            self.visit(origin, sub_node, ctx)

    def visit_IfNode(self, origin, node, ctx):
        for sub_node in node.nodelist:
            self.visit(origin, sub_node, ctx)

    def visit_BlockNode(self, origin, node, ctx):
        for sub_node in node.nodelist:
            self.visit(origin, sub_node, ctx)

    def visit_TextNode(self, origin, node, ctx):
        return

    def visit_CsrfTokenNode(self, origin, node, ctx):
        return


    def visit_AutoEscapeControlNode(self, origin, node, ctx):
        # When {% autoescape off %} occurs
        # All output will be considered potentially vulnerable.
        if not node.setting:
            log.debug("Autoescape is turned OFF within: {}".format(origin))
            ctx.autoescape = True
        for sub_node in node.nodelist:
            self.visit(origin, sub_node, ctx)


class NodeVisitor(ast.NodeVisitor):
    """
    Collects all templates used in a module's views

    After running NodeVisitor.visit() on an ast, `templates` will hold 
    a dict with the following:

    {"template_name": (module_path, view, lineno), ...}, where lineno is where the template's context is defined

    `assignments` holds all assignments inside the current function's scope

    `current_func` is the current function we are currently traversing
    """
    def __init__(self, module_path):
        self.templates = {}
        self.current_func = None
        self.assignments = {}
        self.module_path = module_path
        super(NodeVisitor, self).__init__()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            function_called = node.func.attr
        else:
            function_called = node.func.id

        if function_called == 'render':
            # In case the caller didn't provide any context
            if len(node.args) == 0 or isinstance(node.args[0], ast.Call):
                # Example: t = get_template("test.html")
                # t.render(RequestContext(request))
                # TODO: Check if it is an attribute call
                return
            else:
                if len(node.args) == 2:
                    lineno = node.lineno
                elif isinstance(node.args[2], ast.Dict):
                    lineno = node.args[2].lineno
                else:
                    lineno = self.assignments[node.args[2].id].lineno
                self.templates[node.args[1].s] = (self.module_path, self.current_func.name, lineno)
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

    def __init__(self, *args, **kwargs):
        super(Context, self).__init__(*args, **kwargs)
        self.autoescape = False

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
