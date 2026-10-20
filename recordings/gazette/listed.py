"""A class given two decorators of the project's own as one list, by `method_decorator`.

`first` and `second` are ordinary decorators, as `announced` in `stamp.py` is: each says when it
is applied to a view and when the wrapper it made is called, through the recording script's
`SAY`. `Corrections` has the two on its `dispatch`, given as `[first, second]`.
"""
from functools import partial, wraps

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View

from .stamp import say


def given(view):
    """What a decorator was given: the wrapper of the other decorator, a partial around a bound
    method (what method_decorator hands a decorator at a call), or a function by its name."""
    made_by = getattr(view, "made_by", None)
    if made_by is not None:
        return f"the wrapper {made_by} made"
    if isinstance(view, partial):
        return f"a partial around the bound method {view.__qualname__}"
    return view.__qualname__


def first(view):
    say(f"first is applied to {given(view)}")

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        say("the wrapper first made is called")
        return view(request, *args, **kwargs)

    wrapper.made_by = "first"
    return wrapper


def second(view):
    say(f"second is applied to {given(view)}")

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        say("the wrapper second made is called")
        return view(request, *args, **kwargs)

    wrapper.made_by = "second"
    return wrapper


@method_decorator([first, second], name="dispatch")
class Corrections(View):
    def get(self, request):
        return HttpResponse("corrections and clarifications")
