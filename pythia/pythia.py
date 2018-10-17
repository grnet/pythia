import django
from django.template.base import Template, Origin
from django.conf import settings

import os
import sys
import argparse

from traversal import TemplateTraverser, ViewTraverser

# Backwards compatibility requires this
if django.VERSION >= (1, 9, 0):
    from django.template.exceptions import TemplateSyntaxError
else:
    from django.template.base import TemplateSyntaxError

def main():
    args = parse_arguments()
    # Setup django settings
    if 'DJANGO_SETTINGS_MODULE' not in os.environ:
        print("[*] Error: 'DJANGO_SETTINGS_MODULE' environment variable should"
                "be set and point to your settings module, e.g. 'myproj.settings'")
        sys.exit(1)
    if 'PYTHONPATH' not in os.environ or os.getcwd() not in os.environ['PYTHONPATH']:
        print("[*] Error: append your current working directory to your 'PYTHONPATH',"
                " run `export PYTHONPATH=$PYTHONPATH:${PWD}` under the same directory as your manage.py resides")
        sys.exit(1)

    django.setup()

    # Find all templates in the project
    # TODO: Optimize this with glob ( if we are going to use python > 3.6 )
    templates = []
    for root, dirnames, filenames in os.walk("."):
        for filename in filenames:
            if filename.endswith("html") and "/templates" in root:
                original_path = os.path.join(root, filename)
                templates.append(original_path)

    tr = TemplateTraverser(args.disable_warnings, args.dangerous_filters)

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
            tr.traverseTemplate(stripped_path, tpl)

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--dangerous-filters', nargs="+", default=["safe", "safeseq"])
    parser.add_argument('-w', '--disable-warnings', action="store_true")
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    main()
