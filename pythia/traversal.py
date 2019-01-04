import copy
import ast
from collections import OrderedDict
from .logger import Logger

from django.template.loader import get_template
from django.template.loader_tags import Variable
from django.template.base import Template, Origin

import django
if django.VERSION >= (1, 9, 0):
    from django.template.exceptions import TemplateDoesNotExist
    from django.template.exceptions import TemplateSyntaxError
else:
    from django.template.base import TemplateSyntaxError
    from django.template.base import TemplateDoesNotExist

log = Logger.get_logger('pythia')

class ProjectTraverser:
    """
    A utility class that takes a list of template paths,
    traverses them by using TemplateTraverser, and returns
    all potentially vulnerable variable outputs.
    """

    def __init__(self, templates, dangerous_filters):
        self.templates = templates
        self.dangerous_filters = dangerous_filters

    def walk(self):
        """
        Iterates all templates and returns all potentially vulnerable
        variable outputs
        """
        for template_path in self.templates:
            tt = TemplateTraverser(self.dangerous_filters)
            with open(template_path) as f:
                stripped_path = template_path.split("/templates/")[1]
                try:
                    if django.VERSION < (1, 10, 0):
                        tpl = Template(f.read())
                    else:
                        tpl = Template(f.read(), origin=Origin(
                            "starting_point", template_name=stripped_path))
                except TemplateSyntaxError as err:
                    log.warn('Could not parse template ({}): "{}"'
                             .format(template_path, err))
                    continue
                tt.walk(stripped_path, tpl)
        return tt.final_results


class TemplateTraverser:
    """
    Provides the core functionality for traversing a django template's AST

    This class follows python's ast package's pattern:

    For all nodes, `visit` is going to be called.
    `visit` acts as the router function for all template tags.

    For example, for a `CommentNode`, `visit_CommentNode` will be called.
    If that function does not exist, then `generic_visit` will be called.

    `generic_visit` acts as the default handler for all unhandled template tags

    `final_results` holds a global dictionary of the following:
    {'base.html': [(origin, filter, variable_name, context), ...], ...}
    Essentially, for each template we store all the potentially
    vulnerable variable output

    """
    final_results = {}

    def __init__(self, filters):
        self.dangerous_filters = filters
        self.temp_results = []

    def walk(self, tpl_path, tpl):
        origin = [tpl_path]
        for node in tpl:
            self.visit(origin, node, Context())
        if len(self.temp_results) > 0:
            self.final_results[tpl_path] = self.temp_results

    def visit(self, origin, node, ctx):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(origin, node, ctx)

    def generic_visit(self, origin, node, ctx):
        """ Ignore all other tags for now """
        return

    def visit_IncludeNode(self, origin, node, ctx):
        """
        Uses the global cache `final_results`
        to avoid double traversing of a template
        """
        inclusion_path = node.template.var

        if isinstance(inclusion_path, Variable):
            log.warn("Variable paths are not supported, ignoring inclusion")
            return

        if inclusion_path.startswith((".", "..")) and django.VERSION < (1, 10, 0):
            log.warn("Relative paths are not supported for django < 1.10.0")
            return

        try:
            tpl = get_template(inclusion_path).template
        except TemplateDoesNotExist:
            log.warn("Attempted to include '%s' and it does not exist" % inclusion_path)
            return

        if inclusion_path in self.final_results:
            included_tpl_results = self.final_results[inclusion_path]
        else:
            tt = TemplateTraverser(self.dangerous_filters)
            tt.walk(inclusion_path, tpl)
            included_tpl_results = tt.temp_results

        # Prepend the current origin to all results from the included template
        # E.g. ['404.html, intermidiate.html'] + ['base.html', 'footer.html']
        for res in included_tpl_results:
            vuln = (origin + res[0], res[1], res[2], res[3])
            self.temp_results.append(vuln)

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

        if extension_path in self.final_results:
            extending_tpl_results = self.final_results[extension_path]
        else:
            tt = TemplateTraverser(self.dangerous_filters)
            tt.walk(extension_path, tpl)
            extending_tpl_results = tt.temp_results

        # Same as for inclusions
        for res in extending_tpl_results:
            vuln = (origin + res[0], res[1], res[2], res[3])
            self.temp_results.append(vuln)

        for sub_node in node.nodelist:
            self.visit(origin, sub_node, ctx)

    def visit_ForNode(self, origin, node, ctx):
        # In the case of {% key, val in dict %}
        # loopvars would be ['key', 'val']
        ctx = copy.deepcopy(ctx)
        for var in node.loopvars:
            ctx[var] = node.sequence.token
        for sub_node in node.nodelist_loop:
            self.visit(origin, sub_node, ctx)

    def visit_VariableNode(self, origin, node, ctx):
        """
        Checks whether a `dangerous filter` is used on a variable or
        if the autoescape is turned off during output rendering
        """
        tokens = node.filter_expression.token.split("|")
        var_name, filters = tokens[0], tokens[1:]

        # This is needed for cases like {{ vuln|  safe }}
        filters = [f.strip(" ") for f in filters]

        if ctx.autoescape:
            self.temp_results.append((origin, 'autoescape', var_name, ctx))
            return

        for f in filters:
            if f in self.dangerous_filters:
                log.debug("[{}]: The '{}' filter was used for '{}' "
                          "with context: '{}'"
                          .format(origin, f, var_name, ctx))
                self.temp_results.append((origin, f, var_name, ctx))

    def visit_WithNode(self, origin, node, ctx):
        """ Provides `context` for all subsequent nodes """

        # static data e.g. {% with var="sample" %}
        if node.extra_context:
            ctx = copy.deepcopy(ctx)
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
        """ If autoescape is turned off then pass that to the context """

        ctx = copy.deepcopy(ctx)
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

    {"template_name": (module_path, view, lineno), ...}, where lineno
    is where the template's context is defined

    `assignments` holds all assignments inside the current function's scope

    `current_func` is the current function we are currently traversing
    """
    def __init__(self, module_path, dangerous_decorators):
        self.templates = {}
        self.current_func = None
        self.dangerous_views = {}
        self.dangerous_decorators = dangerous_decorators
        self.dangerous_contexts = {}
        self.assignments = {}
        self.subscript_assignments = {}
        self.module_path = module_path
        super(NodeVisitor, self).__init__()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            function_called = node.func.attr
        elif isinstance(node.func, ast.Name):
            function_called = node.func.id
        else: # could be ast.Call e.g. get_function()()
            return

        if function_called == 'render':
            # In case the caller didn't provide any context
            if len(node.args) == 0 or isinstance(node.args[0], ast.Call):
                # Example: t = get_template("test.html")
                # t.render(RequestContext(request))
                # TODO: Check if it is an attribute call
                return
            else:
                # TODO: Check {}.format() case for str substitution
                if len(node.args) == 2:
                    lineno = node.lineno
                elif len(node.args) < 2:
                    for keyword in node.keywords:
                        if keyword.arg == 'template':
                            node.args.append(keyword.value)
                    lineno = node.lineno
                elif isinstance(node.args[2], ast.Dict): # render(request, {...})
                    lineno = node.args[2].lineno
                else:                                    # render(request, var), lookup var assignment
                    context_name = node.args[2].id
                    lineno = self.assignments[context_name].lineno
                    if context_name in self.subscript_assignments:
                        self.dangerous_contexts[self.current_func] = self.subscript_assignments[context_name]

                key = None
                if isinstance(node.args[1], ast.Name):
                    assignment = self.assignments[node.args[1].id]
                    if isinstance(assignment, ast.BinOp): # template_name = "admin/%s" % tpl_name
                        if not assignment.right.id in self.assignments:
                            return
                        key = assignment.left.s % self.assignments[assignment.right.id].s
                    elif isinstance(assignment, ast.Call) and assignment.func.attr == 'format': # template_name = "admin/{}".format(tpl_name)
                        args = []
                        for arg in assignment.args:
                            if isinstance(arg, ast.Name):
                                args.append(self.assignments[arg.id].s)
                            elif isinstance(arg, ast.Str):
                                args.append(arg.s)
                            else:
                                return
                        key = assignment.func.value.s.format(*args)
                elif isinstance(node.args[1], (ast.Attribute, ast.Dict)): # render(req, self.template_name) in a Class-based view
                    return
                else:
                    key = node.args[1].s

                self.templates.setdefault(key, []) \
                .append((self.module_path, self.current_func.name, lineno))
        self.generic_visit(node)

    def visit_Assign(self, node):
        """
        Holds a per-function cache for all assignments

        This helps in the case of:
        return_dict = {"users": User.objects.all()}
        ...
        return render(request, "users.html", return_dict)
        """
        # TODO: Handle global vars also
        for target in node.targets:
            # TODO: Handle subscript also
            # TODO: Abstract attribute calls.
            if isinstance(target, ast.Attribute):
                var_name = target.attr
                self.assignments[var_name] = node.value
            elif isinstance(target, ast.Name):
                var_name = target.id
                self.assignments[var_name] = node.value
            elif isinstance(target, ast.Tuple): # multiple returns e.g. a, b = get_params()
                for return_arg in target.elts:
                    if isinstance(return_arg, ast.Attribute):
                        var_name = return_arg.attr
                    else:
                        var_name = return_arg.id
                    self.assignments[var_name] = node.value
            elif isinstance(target, ast.Subscript):
                #TODO: refactor this, handle all cases.
                # Case: d[var] = a[var2] instead of function call
                if isinstance(node.value, (ast.Subscript, ast.Str, ast.Name, ast.Compare)):
                    break
                # TODO: Fix case: d[var] = mark_safe(..)
                if isinstance(target.slice.value, ast.Name):
                    key = target.slice.value.id
                elif isinstance(target.slice.value, ast.Str):
                    key = target.slice.value.s
                else:
                    break
                if not hasattr(node.value, "func") or isinstance(node.value.func, ast.Attribute):
                    break
                func_called = node.value.func.id
                # TODO: Expand this for a user-supplied function
                if func_called == 'mark_safe':
                    assignment = (key, func_called, node.lineno)
                    self.subscript_assignments.setdefault(target.value.id, []).append(assignment)

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """
        Cleans up after previous function's assignments.
        Also hooks the current node as the current_func.
        """
        # Flattens all of the function's decorators
        current_func_decorators = [d.id for d in node.decorator_list if isinstance(d, ast.Name)]
        for d in self.dangerous_decorators:
            if d in current_func_decorators:
                self.dangerous_views.setdefault(node.name, []).append(d)
        self.current_func = node
        self.assignments = {}
        self.generic_visit(node)


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
            '{0}->{1}'.format(key, value)
            for (key, value) in reversed(list(self.items()))
        ]
        return " / ".join(formatted_values)
