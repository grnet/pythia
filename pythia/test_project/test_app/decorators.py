from functools import partial

# These check whether pythia can unwrap a function properly
def check_auth(view_fn, request, cast, *args, **kwargs):
    return view_fn(request)
def check_graph_auth(view_fn):
    return partial(check_auth, view_fn, 'test')
