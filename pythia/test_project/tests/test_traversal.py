import unittest
import django
import json
import ast

from pythia import traversal

class TestTraversal(unittest.TestCase):
    def setUp(self):
        django.setup()

    def test_assignments(self):
        view_module = "test_app/views.py"
        with open(view_module) as mod_file:
            nv = traversal.NodeVisitor("views.test")
            code = mod_file.read()
            tree = ast.parse(code)
            nv.visit(tree)
            print(nv.templates)
