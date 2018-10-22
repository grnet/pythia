import django
from django.template.base import Template, Origin
from django.conf import settings

import os
import sys
import argparse
import ast
import logging

from logger import init_logging
from traversal import TemplateTraverser, NodeVisitor

if django.VERSION >= (1, 9, 0):
    from django.template.exceptions import TemplateSyntaxError
else:
    from django.template.base import TemplateSyntaxError

log = logging.getLogger('pythia')

def main():
    args = parse_arguments()
    init_logging(args.debug, args.enable_warnings)

    check_environment()
    # NOTE: This is needed because if PYTHONENV is not set, this will raise an exception
    from urlresolver import UrlResolver

    # NOTE: Optimize this with glob.iglob ( if we are going to use python > 3.6 )
    templates = []
    for root, dirnames, filenames in os.walk("."):
        for filename in filenames:
            if filename.endswith("html") and "/templates" in root:
                original_path = os.path.join(root, filename)
                templates.append(original_path)

    tt = TemplateTraverser(args.dangerous_filters)

    for template_path in templates:
        with open(template_path) as f:
            stripped_path = template_path.split("/templates/")[1]
            try:
                if django.VERSION < (1, 10, 0):
                    tpl = Template(f.read())
                else:
                    tpl = Template(f.read(), origin=Origin("starting_point", template_name=stripped_path))
            except TemplateSyntaxError as err:
                log.warn('Could not parse template ({}): "{}"'.format(template_path, err))
                continue
            tt.walk(stripped_path, tpl)

    # Resolve all urls -> views
    resolver = UrlResolver()
    views = resolver.resolve()

    visited = set()
    view_templates = {}
    for v in views:
        # Cut off view's name, e.g. ganeti.views.get_users -> ganeti/views/
        module_path = "/".join(v['module'].split(".")[:-1])

        if "django" in module_path or module_path in visited:
            continue

        # NOTE: maybe we can just import module instead of opening the file?
        # If the module 'ganeti/views.py does not exist, we should try ganeti/views/__init__.py
        if not os.path.exists(os.path.join(os.getcwd(), module_path) + ".py"):
            relative_path = os.path.join(module_path, "__init__.py")
        else:
            relative_path = module_path + ".py"

        absolute_path = os.path.join(os.getcwd(), relative_path)
        try:
            with open(absolute_path) as mod_file:
                visited.add(relative_path)
                nv = NodeVisitor(relative_path)
                code = mod_file.read()
                tree = ast.parse(code)
                nv.visit(tree)
                view_templates.update(nv.templates)
        except IOError:
            log.warn("Module '{}' does not exist. "
                     "Likely a module provided by an external package" \
                    .format(v['module']))

    for tpl, (origin, filter, var_name, ctx) in tt.results.items():
        if tpl in view_templates:
            (module_path, view, lineno) = view_templates[tpl]
            log.info("{0}:{1}:{2} -> {3} used '{4}' on '{5}' with context '{6}'" \
                    .format(module_path, view, lineno, origin, filter, var_name, ctx))


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--dangerous-filters', nargs="+", default=["safe", "safeseq"])
    parser.add_argument('-w', '--enable-warnings', action="store_true")
    parser.add_argument('-d', '--debug', action="store_true")
    args = parser.parse_args()
    return args

def check_environment():
    if 'DJANGO_SETTINGS_MODULE' not in os.environ:
        log.critical("'DJANGO_SETTINGS_MODULE' environment variable should"
                "be set and point to your settings module, e.g. 'myproj.settings'")
        sys.exit(1)
    if 'PYTHONPATH' not in os.environ or os.getcwd() not in os.environ['PYTHONPATH']:
        log.critical("Append your current working directory to your 'PYTHONPATH',"
                " run `export PYTHONPATH=$PYTHONPATH:${PWD}`"
                " under the same directory as your manage.py resides")
        sys.exit(1)
    django.setup()

if __name__ == "__main__":
    main()
