import unittest
from pythia import urlresolver
import django
import json

class TestResolver(unittest.TestCase):
    def setUp(self):
        django.setup()

    def test_resolve_urls(self):
        views = urlresolver.resolve_urls()
        flat_modules = [item['module'] for item in views]
        self.assertIsInstance(views, list)
        self.assertTrue("test_app.views.test_decorated_func" in flat_modules)

    def test_resolve_urls_format(self):
        views = urlresolver.resolve_urls(format_json=True)
        try:
            json_obj = json.loads(views)
        except Exception as e:
            self.fail("Output is not JSON")

