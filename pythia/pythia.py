import django
from django.template.base import Template, Origin
from django.conf import settings

import os
import sys
import argparse
import ast

from traversal import TemplateTraverser, NodeVisitor

# Backwards compatibility requires this
if django.VERSION >= (1, 9, 0):
    from django.template.exceptions import TemplateSyntaxError
else:
    from django.template.base import TemplateSyntaxError

def main():
    args = parse_arguments()

    check_environment()
    from urlresolver import UrlResolver

    # NOTE: Optimize this with glob.iglob ( if we are going to use python > 3.6 )
    templates = []
    for root, dirnames, filenames in os.walk("."):
        for filename in filenames:
            if filename.endswith("html") and "/templates" in root:
                original_path = os.path.join(root, filename)
                templates.append(original_path)

    tt = TemplateTraverser(args.disable_warnings, args.dangerous_filters)

    for template_path in templates:
        with open(template_path) as f:
            stripped_path = template_path.split("/templates/")[1]
            try:
                if django.VERSION < (1, 10, 0):
                    tpl = Template(f.read())
                else:
                    tpl = Template(f.read(), origin=Origin("starting_point", template_name=stripped_path))
            except TemplateSyntaxError as err:
                print('[*] Error: could not parse template "{}":\n{}\n'.format(template_path, err))
                continue
            tt.traverse_template(stripped_path, tpl)

    resolver = UrlResolver()
    views = resolver.resolve()

    visited = set()
    for v in views:
        # Cut off view's name, e.g. ganeti.views.get_users -> ganeti/views/
        module_path = "/".join(v['module'].split(".")[:-1])
        if "django" in module_path or module_path in visited:
            continue

        # NOTE: maybe we can just import module instead of opening the file?
        # If the module 'ganeti/views.py does not exist, we should try ganeti/views/__init__.py
        absolute_path = os.path.join(os.getcwd(), module_path) + ".py"
        if not os.path.exists(absolute_path):
            final_path = os.path.join(os.getcwd(), module_path, "__init__.py")
        else:
            final_path = absolute_path

        try:
            with open(final_path) as mod_file:
                visited.add(module_path)
                nv = NodeVisitor()
                print(final_path)
                code = mod_file.read()
                tree = ast.parse(code)
                nv.visit(tree)
                print(nv.templates)
        except IOError:
            print("Warning: module '{}' does not exist. "
                  "Likely a module provided by an external package" \
                    .format(v['module']))

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--dangerous-filters', nargs="+", default=["safe", "safeseq"])
    parser.add_argument('-w', '--disable-warnings', action="store_true")
    args = parser.parse_args()
    return args

def check_environment():
    if 'DJANGO_SETTINGS_MODULE' not in os.environ:
        print("[*] Error: 'DJANGO_SETTINGS_MODULE' environment variable should"
                "be set and point to your settings module, e.g. 'myproj.settings'")
        sys.exit(1)
    if 'PYTHONPATH' not in os.environ or os.getcwd() not in os.environ['PYTHONPATH']:
        print("[*] Error: append your current working directory to your 'PYTHONPATH',"
                " run `export PYTHONPATH=$PYTHONPATH:${PWD}`"
                " under the same directory as your manage.py resides")
        sys.exit(1)
    django.setup()

if __name__ == "__main__":
    main()
