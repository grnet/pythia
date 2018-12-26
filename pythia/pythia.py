import os
import sys
import argparse
import ast
import logging
import django


from .logger import init_logging
from .traversal import NodeVisitor, ProjectTraverser

log = logging.getLogger('pythia')


def main():
    args = parse_arguments()
    init_logging(args.debug, args.enable_warnings)

    setup_environment()
    from .urlresolver import resolve_urls

    templates = find_all_templates()
    if not templates:
        log.error("No templates were found. Be sure to run pythia under project root")
        sys.exit(1)

    pt = ProjectTraverser(templates, args.dangerous_filters)
    vuln_templates = pt.walk()

    # Resolve all urls -> views
    views = resolve_urls()

    dangerous_views, view_templates = parse_view_modules(views, args.dangerous_decorators)
    pprint_dangerous_views(dangerous_views, views)
    find_tainted_paths(view_templates, vuln_templates, args.ignore_variables)
    pprint_unresolved(vuln_templates, args.ignore_variables)

def pprint_dangerous_views(dangerous_views, views):
    for dangerous_view, decorators in dangerous_views.items():
        for view in views: #TODO: change this to a dict with the view name as the key
            if view['view_name'] == dangerous_view:
                log.info("Under '{0}' view '{1}' runs the following unsafe decorators: '{2}'"
                        .format(view['url'], view['module'], decorators))

def pprint_unresolved(vuln_templates, ignore_variables):
    for tpl in vuln_templates.keys():
        for (origin, filter, var_name, ctx) in vuln_templates[tpl]:
            if var_name not in ignore_variables:
                log.info("Could not resolve {0}: {1} ran '{2}' on '{3}' with context '{4}'"
                        .format(tpl, origin, filter, var_name, ctx))

def find_all_templates():
    templates = []
    for root, dirnames, filenames in os.walk("."):
        for filename in filenames:
            if filename.endswith("html") and "/templates" in root:
                original_path = os.path.join(root, filename)
                templates.append(original_path)
    return templates


def find_tainted_paths(view_templates, vuln_templates, ignore_variables):
    for tpl in list(vuln_templates.keys()):
        if tpl in view_templates:
            for (origin, filter, var_name, ctx) in vuln_templates[tpl]:
                if var_name not in ignore_variables:
                    for (module_path, view, lineno) in view_templates[tpl]:
                        log.info("{0}:{1}:{2} -> {3} used '{4}' on '{5}' with context '{6}'"
                                .format(module_path, view, lineno, origin, filter, var_name, ctx))
            del vuln_templates[tpl]


def parse_view_modules(views, dangerous_decorators):
    """
    Returns all the templates found through parsing all view modules
    found through `resolve()`.
    """
    visited = set()
    view_templates = {}
    dangerous_views = {}
    for v in views:
        # Cut off view's name, e.g. ganeti.views.get_users -> ganeti/views/
        module_path = "/".join(v['module'].split(".")[:-1])

        if "django" in module_path or module_path in visited:
            continue

        # NOTE: maybe we can just import module instead of opening the file?
        # If the module 'ganeti/views.py does not exist
        # we should try ganeti/views/__init__.py
        if not os.path.exists(os.path.join(os.getcwd(), module_path) + ".py"):
            relative_path = os.path.join(module_path, "__init__.py")
        else:
            relative_path = module_path + ".py"

        absolute_path = os.path.join(os.getcwd(), relative_path)
        try:
            with open(absolute_path) as mod_file:
                visited.add(relative_path)
                nv = NodeVisitor(relative_path, dangerous_decorators)
                code = mod_file.read()
                tree = ast.parse(code)
                nv.visit(tree)
                dangerous_views.update(nv.dangerous_views)
                view_templates.update(nv.templates)
        except IOError:
            log.warn("Module '{}' does not exist. "
                     "Likely a module provided by an external package"
                     .format(v['module']))

    return (dangerous_views, view_templates)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--ignore-variables',
                        nargs="+", default=[])
    parser.add_argument('-f', '--dangerous-filters',
                        nargs="+", default=["safe", "safeseq"])
    parser.add_argument('-dd', '--dangerous-decorators',
                        nargs="+", default=["csrf_exempt"])
    parser.add_argument('-w', '--enable-warnings', action="store_true")
    parser.add_argument('-d', '--debug', action="store_true")
    args = parser.parse_args()
    return args


def setup_environment():
    if 'DJANGO_SETTINGS_MODULE' not in os.environ:
        log.critical("'DJANGO_SETTINGS_MODULE' environment variable should"
                     "be set and point to your settings module, e.g. 'myproj.settings'")
        sys.exit(1)
    if 'PYTHONPATH' not in os.environ or os.getcwd() not in os.environ['PYTHONPATH']:
        log.critical("Append your current working directory to your 'PYTHONPATH', "
                     "run `export PYTHONPATH=$PYTHONPATH:${PWD}` "
                     "under the same directory as your manage.py resides")
        sys.exit(1)
    django.setup()

    # Django adds its own loggers and they catch all logging levels
    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)


if __name__ == "__main__":
    main()
