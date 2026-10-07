"""The recording's two middleware, the decorators made from them, and one plain decorator.

`Stamp` has all five hooks and does nothing in any of them but tell the recording script it
was called: the script puts a callable in `SAY`. `stamped` is the class turned into a view
decorator by `decorator_from_middleware`, as Django turns `CsrfViewMiddleware` into
`csrf_protect`. `Shut` is a `Stamp` whose `process_request` answers the request itself, and
`shut` the decorator made from it. `announced` is an ordinary decorator that says when it is
applied to a view and when the wrapper it made is called.
"""
from functools import partial, wraps

from django.http import HttpResponse
from django.middleware import MiddlewareMixin
from django.utils.decorators import decorator_from_middleware

SAY = []


def say(text):
    for one in SAY:
        one(text)


def called(view):
    """A view by its name. What method_decorator hands a decorator is a functools.partial
    around a bound method, carrying the method's name: say that it is one."""
    name = getattr(view, "__qualname__", type(view).__name__)
    return f"a partial around the bound method {name}" if isinstance(view, partial) else name


class Stamp(MiddlewareMixin):
    def __init__(self, get_response):
        super().__init__(get_response)
        say(f"Stamp.__init__(get_response={called(get_response)})")

    def process_request(self, request):
        say("Stamp.process_request")

    def process_view(self, request, view, args, kwargs):
        say(f"Stamp.process_view(view={called(view)})")

    def process_exception(self, request, exception):
        say(f"Stamp.process_exception({type(exception).__name__})")

    def process_template_response(self, request, response):
        say(f"Stamp.process_template_response(is_rendered={response.is_rendered})")
        return response

    def process_response(self, request, response):
        say(f"Stamp.process_response(a {response.status_code}, content={response.content.decode()!r})")
        return response


class Shut(Stamp):
    def process_request(self, request):
        say("Shut.process_request, which returns a response")
        return HttpResponse("the office is shut")


def announced(view):
    say(f"announced is applied to {called(view)}")

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        say("the wrapper that announced made is called")
        return view(request, *args, **kwargs)

    return wrapper


stamped = decorator_from_middleware(Stamp)
shut = decorator_from_middleware(Shut)
