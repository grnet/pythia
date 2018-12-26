import functools
import json
import types
import inspect
import re

from django.contrib.admindocs.views import simplify_regex
from django.conf import settings
from django.core.exceptions import ViewDoesNotExist
import django

# NOTE: https://github.com/django-extensions/django-extensions/blob/1b54bdfdd87d8eb738c66a95bb8f88cbb1aa9b80/django_extensions/management/commands/show_urls.py#L16
if django.VERSION >= (2, 0):
    from django.urls import URLPattern, URLResolver

    class RegexURLPattern:
        pass

    class RegexURLResolver:
        pass

    class LocaleRegexURLResolver:
        pass

    def describe_pattern(p):
        return str(p.pattern)
else:
    try:
        from django.urls import (
                RegexURLPattern, RegexURLResolver, LocaleRegexURLResolver)
    except ImportError:
        from django.core.urlresolvers import (
                RegexURLPattern, RegexURLResolver, LocaleRegexURLResolver)

    class URLPattern:
        pass

    class URLResolver:
        pass

    def describe_pattern(p):
        return p.regex.pattern


def resolve_urls(format_json=False):
    urlconf = "ROOT_URLCONF"
    views = []
    try:
        urlconf = __import__(getattr(settings, urlconf), {}, {}, [''])
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise Exception("Error occurred while trying to load {0}: {1}"
                        .format(urlconf, str(e)))

    find_view_function = get_view_resolver()
    view_functions = extract_views_from_urlpatterns(urlconf.urlpatterns)
    for (func, regex, url_name) in view_functions:
        if ("decorators" in func.__module__):
            func = find_view_function(func)

        if hasattr(func, '__name__'):
            func_name = func.__name__
        elif hasattr(func, '__class__'):
            func_name = func.__class__.__name__
        else:
            func_name = re.sub(r' at 0x[0-9a-f]+', '', repr(func))

        module = '{0}.{1}'.format(func.__module__, func_name)
        url_name = url_name or ''
        url = simplify_regex(regex)
        view_name = module.split(".")[-1]

        views.append({"view_name": view_name, "url": url, "module": module, "name": url_name})

    if format_json:
        return json.dumps(views, indent=4)
    return(views)


def extract_views_from_urlpatterns(urlpatterns, base='', namespace=None):
    """
    Return a list of views from a list of urlpatterns.
    Each object in the returned list is a three-tuple: (view_func, regex, name)
    """
    views = []
    for p in urlpatterns:
        if isinstance(p, (URLPattern, RegexURLPattern)):
            try:
                if not p.name:
                    name = p.name
                elif namespace:
                    name = '{0}:{1}'.format(namespace, p.name)
                else:
                    name = p.name
                pattern = describe_pattern(p)
                views.append((p.callback, base + pattern, name))
            except ViewDoesNotExist:
                continue
        elif isinstance(p, (URLResolver, RegexURLResolver)):
            try:
                patterns = p.url_patterns
            except ImportError:
                continue
            if namespace and p.namespace:
                _namespace = '{0}:{1}'.format(namespace, p.namespace)
            else:
                _namespace = (p.namespace or namespace)
            pattern = describe_pattern(p)
            if isinstance(p, LocaleRegexURLResolver):
                continue
            else:
                views.extend(extract_views_from_urlpatterns(
                    patterns, base + pattern, namespace=_namespace))
        elif hasattr(p, '_get_callback'):
            try:
                views.append((p._get_callback(),
                             base + describe_pattern(p), p.name))
            except ViewDoesNotExist:
                continue
        elif hasattr(p, 'url_patterns') or hasattr(p, '_get_url_patterns'):
            try:
                patterns = p.url_patterns
            except ImportError:
                continue
            views.extend(extract_views_from_urlpatterns(
                patterns, base + describe_pattern(p), namespace=namespace))
        else:
            raise TypeError("%s does not appear to be a urlpattern object" % p)
    return views

def get_view_resolver():
    def find_view_function_p2(func):
        """ Resolves nested decorators and returns the original view function """
        if func.func_closure is None:
            return func
        for closure in func.func_closure:
            cell = closure.cell_contents
            if isinstance(cell, types.FunctionType) and cell.func_name == '<lambda>':
                continue
            elif isinstance(cell, (str, types.NoneType)):
                continue
            elif isinstance(cell, functools.partial):
                return find_view_function_p2(cell.args[0])
            return find_view_function_p2(cell)

    def find_view_function_p3(func):
        partial_func = inspect.unwrap(func)
        return partial_func.args[0] if isinstance(partial_func, functools.partial) else partial_func

    import sys
    return find_view_function_p3 if sys.version_info[0] == 3 else find_view_function_p2
