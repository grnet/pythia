import django
from django.template.base import Template, Origin
from django.conf import settings

import os
import sys
import argparse
from distutils.version import StrictVersion

from traversal import Traverser

def main():
    args = parse_arguments()
    # Setup django settings
    if 'DJANGO_SETTINGS_MODULE' not in os.environ:
        print("[*] Error: 'DJANGO_SETTINGS_MODULE' environment variable should"
                "be set and point to your settings module, e.g. 'myproj.settings'")
        sys.exit(1)
    sys.path.append(os.getcwd()) # This is needed in order to run pythia from anywhere
    django.setup()
    version = StrictVersion(django.get_version())

    # Backwards compatibility requires this
    if version >= StrictVersion('1.9.0'):
        from django.template.exceptions import TemplateSyntaxError
    else:
        from django.template.base import TemplateSyntaxError

    # Find all templates in the project
    # TODO: Optimize this with glob ( if we are going to use python > 3.6 )
    templates = []
    for root, dirnames, filenames in os.walk("."):
        for filename in filenames:
            if filename.endswith("html") and "/templates" in root:
                original_path = os.path.join(root, filename)
                templates.append(original_path)

    tr = Traverser(args.disable_warnings, args.dangerous_filters)

    for template_path in templates:
        with open(template_path) as f:
            stripped_path = template_path.split("/templates/")[1]
            # This allows relative imports in templates while being backwards compatible
            # TODO: Handle exceptions for TemplateSyntaxError
            try:
                if version < StrictVersion("1.10.0"):
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
