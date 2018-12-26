from django.shortcuts import render
from .decorators import check_graph_auth
from django.contrib.auth.decorators import login_required

@login_required
@check_graph_auth
def test_decorated_func(request):
    return render(request, 'base.html', {"test": "script"})

def test_assignments_func(request):
    tpl_name = "base.html"
    base_name = "%s" % tpl_name
    return render(request, base_name, {"test": "script"})

def test_assignments_func2(request):
    tpl_name = "base.html"
    temp_name = "{}".format(tpl_name)
    return render(request, temp_name, {"test": "script"})
