import django
from django.template.base import Template, Origin
from django.conf import settings

import os
import sys
from distutils.version import StrictVersion

from traversal import Traverser

# Setup django settings
sys.path.append(os.getcwd()) # This is needed in order to run pythia from anywhere
django.setup()
version = StrictVersion(django.get_version())


# Find all templates in the project
# TODO: Optimize this with glob
templates = []
for root, dirnames, filenames in os.walk("."):
    for filename in filenames:
        if filename.endswith("html") and "/templates/" in root:
            original_path = os.path.join(root, filename)
            templates.append(original_path)

# TODO: expose this to the user as an argument
dangerous_filters = ["safe", "safeseq"]
tr = Traverser(dangerous_filters)

for template_path in templates:
    with open(template_path) as f:
        stripped_path = template_path.split("/templates/")[1]
        # This allows relative imports while being backwards compatible
        if version < StrictVersion("1.10.0"):
            tpl = Template(f.read())
        else:
            tpl = Template(f.read(), origin=Origin("starting_point", template_name=stripped_path))
        tr.traverseTemplate(stripped_path, tpl)
