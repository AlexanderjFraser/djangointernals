"""A recording of the handler at work: how the middleware chain is built, and what runs, in
what order and on which thread, for a request through it.

    python recordings/handlers.py > recordings/handlers.txt

Chapter 4 of the book (pages/handlers.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and
configures a project of its own in this one file: three middleware, A, B and C, that
write down every hook Django calls on them, and a handful of views. Run it again after a
re-pin: where the output changes, the chapter has to.

Thread names are made stable: the event loop's thread is `loop`, and a thread a request's
synchronous code runs on is `worker`.
"""
import asyncio
import io
import os
import sys
import threading

# Python puts a script's directory first on the path, and `http.py` in this one has the name of
# a package of the standard library, which Django imports: take the directory off first.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(newline="\n")  # the same bytes on every machine
LINES = []
WORKERS = set()  # the threads, other than the event loop's, that a request's code was seen on


def thread() -> str:
    if threading.current_thread() is threading.main_thread():
        return "loop"
    WORKERS.add(threading.get_ident())
    return "worker"


def note(what: str, where: bool = False) -> None:
    LINES.append(f"{what}  [{thread()}]" if where else what)


settings.configure(
    DEBUG=False,
    SECRET_KEY="recording",
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["*"],
    MIDDLEWARE=[f"{__name__}.A", f"{__name__}.B", f"{__name__}.C"],
    TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates"}],
)
django.setup()

from django.core import signals  # noqa: E402
from django.core.exceptions import MiddlewareNotUsed, PermissionDenied  # noqa: E402
from django.core.handlers.asgi import ASGIHandler  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler  # noqa: E402
from django.http import Http404, HttpResponse  # noqa: E402
from django.middleware import MiddlewareMixin  # noqa: E402
from django.template import engines  # noqa: E402
from django.template.response import TemplateResponse  # noqa: E402
from django.urls import path  # noqa: E402

WHERE = False  # whether a hook says which thread it ran on: the ASGI recordings do


def named(thing) -> str:
    """What a callable is, said shortly: an adapter by what it adapts, the wrapper that
    convert_exception_to_response makes by what it wraps, a middleware's hook on the
    middleware's own class, anything else by its qualified name."""
    from asgiref.sync import AsyncToSync, SyncToAsync

    if isinstance(thing, SyncToAsync):
        return f"sync_to_async({named(thing.func)})"
    if isinstance(thing, AsyncToSync):
        return f"async_to_sync({named(thing.awaitable)})"
    if hasattr(thing, "__wrapped__"):
        return f"the wrapper around {named(thing.__wrapped__)}"
    owner = getattr(thing, "__self__", None)
    if isinstance(owner, MiddlewareMixin):
        return f"{type(owner).__name__}.{thing.__name__}"
    return getattr(thing, "__qualname__", None) or type(thing).__name__


def record_crossings() -> None:
    """From here on, write down every crossing between synchronous and asynchronous code:
    each call of asgiref's sync_to_async (the event loop hands work to a thread) and of
    async_to_sync (a thread hands a coroutine to the event loop and waits for it)."""
    from asgiref.sync import AsyncToSync, SyncToAsync

    to_thread, to_loop = SyncToAsync.__call__, AsyncToSync.__call__

    async def into_thread(self, *args, **kwargs):
        note(f"  loop -> thread: {named(self)}")
        return await to_thread(self, *args, **kwargs)

    def into_loop(self, *args, **kwargs):
        note(f"  thread -> loop: {named(self)}")
        return to_loop(self, *args, **kwargs)

    SyncToAsync.__call__, AsyncToSync.__call__ = into_thread, into_loop


class Recording(MiddlewareMixin):
    """A middleware that writes down each hook the handler, or MiddlewareMixin, calls on it."""

    async_capable = False

    def __init__(self, get_response):
        note(f"{type(self).__name__}(get_response)    get_response is {named(get_response)}")
        super().__init__(get_response)

    def process_request(self, request):
        note(f"{type(self).__name__}.process_request", WHERE)
        if request.path == f"/raise-in-{type(self).__name__}/":
            raise RuntimeError("raised in a middleware")

    def process_view(self, request, view, args, kwargs):
        note(f"{type(self).__name__}.process_view", WHERE)

    def process_exception(self, request, exception):
        note(f"{type(self).__name__}.process_exception({type(exception).__name__})", WHERE)

    def process_template_response(self, request, response):
        note(f"{type(self).__name__}.process_template_response", WHERE)
        return response

    def process_response(self, request, response):
        note(f"{type(self).__name__}.process_response({response.status_code})", WHERE)
        return response


class A(Recording):
    pass


class B(Recording):
    pass


class C(Recording):
    pass


class InAndOut(MiddlewareMixin):
    """A middleware with the two hooks most have, and no others: the ASGI recordings use it."""

    async_capable = False

    def __init__(self, get_response):
        note(f"{type(self).__name__}(get_response)    get_response is {named(get_response)}")
        super().__init__(get_response)

    def process_request(self, request):
        note(f"{type(self).__name__}.process_request", WHERE)

    def process_response(self, request, response):
        note(f"{type(self).__name__}.process_response({response.status_code})", WHERE)
        return response


# Three of them, with the same names as above.
IO_A, IO_B, IO_C = (type(name, (InAndOut,), {}) for name in "ABC")


class Unused:
    def __init__(self, get_response):
        raise MiddlewareNotUsed


def plain(request):
    note("the view", WHERE)
    return HttpResponse("ok")


async def async_view(request):
    if WHERE:
        note("the view (async def)", True)
    else:  # under WSGI: was it called on the thread the server called the handler on?
        same = threading.current_thread() is threading.main_thread()
        note("the view (async def), on " + ("the server's thread" if same else "another thread"))
    return HttpResponse("ok")


def template(request):
    note("the view, returning a TemplateResponse")
    return TemplateResponse(request, engines["django"].from_string("hello"), {})


def missing(request):
    note("the view, raising Http404")
    raise Http404


def denied(request):
    note("the view, raising PermissionDenied")
    raise PermissionDenied


def broken(request):
    note("the view, raising ValueError")
    raise ValueError


def nothing(request):
    note("the view, returning None")


urlpatterns = [
    path("plain/", plain), path("async/", async_view), path("template/", template), path("missing/", missing),
    path("denied/", denied), path("broken/", broken), path("nothing/", nothing), path("raise-in-B/", plain),
]


def on_started(**kwargs):
    note("signal: request_started")


def on_finished(**kwargs):
    note("signal: request_finished")


def on_exception(**kwargs):
    note("signal: got_request_exception")


signals.request_started.connect(on_started)
signals.request_finished.connect(on_finished)
signals.got_request_exception.connect(on_exception)


def show(title: str) -> None:
    print(title)
    for line in LINES:
        print("    " + line)
    print()
    LINES.clear()


def wsgi(handler, url: str, title: str) -> None:
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": url, "SERVER_NAME": "recording", "SERVER_PORT": "80",
               "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.input": io.BytesIO(b""), "wsgi.url_scheme": "http"}

    def start_response(status, headers):
        note(f'start_response("{status}", headers)')

    try:
        response = handler(environ, start_response)
    except Exception as raised:
        note(f"the handler raises {type(raised).__name__} to the server")
    else:
        b"".join(response)
        note("the server closes the response")
        response.close()
    show(f"WSGI, GET {url}: {title}")


def asgi(handler, url: str, title: str) -> None:
    async def run():
        waiting = [{"type": "http.request", "body": b"", "more_body": False}]

        async def receive():
            if waiting:
                return waiting.pop(0)
            await asyncio.sleep(3600)

        async def send(message):
            note(f"send({message['type']})", WHERE)

        await handler({"type": "http", "method": "GET", "path": url, "headers": [], "query_string": b""}, receive, send)

    WORKERS.clear()
    asyncio.run(run())
    note(f"(everything marked worker ran on {len(WORKERS)} thread)" if len(WORKERS) == 1 else f"(worker threads seen: {len(WORKERS)})")
    show(f"ASGI, GET {url}: {title}")


print("Django", django.get_version(), "with MIDDLEWARE = [A, B, C]\n")

handler = WSGIHandler()
show("Making a WSGIHandler builds the chain, last middleware first")
for name in ("_view_middleware", "_template_response_middleware", "_exception_middleware"):
    LINES.append(f"{name}: " + ", ".join(type(method.__self__).__name__ for method in getattr(handler, name)))
show("The three lists of hooks, as the handler keeps them")

wsgi(handler, "/plain/", "a view that returns a response")
wsgi(handler, "/template/", "a view that returns a TemplateResponse")
wsgi(handler, "/nowhere/", "no URL pattern matches")
wsgi(handler, "/missing/", "the view raises Http404")
wsgi(handler, "/denied/", "the view raises PermissionDenied")
wsgi(handler, "/broken/", "the view raises ValueError")
wsgi(handler, "/nothing/", "the view returns None")
wsgi(handler, "/raise-in-B/", "B.process_request raises RuntimeError")
wsgi(handler, "/async/", "an async view")


def failing_error_view(request):
    note("the 500 error view, raising LookupError")
    raise LookupError


globals()["handler500"] = failing_error_view  # this module is the URLconf, so this is its 500 error view
wsgi(handler, "/broken/", "the view raises ValueError, and the 500 error view raises too")
del globals()["handler500"]

settings.DEBUG_PROPAGATE_EXCEPTIONS = True
wsgi(handler, "/broken/", "the view raises ValueError, with DEBUG_PROPAGATE_EXCEPTIONS = True")
settings.DEBUG_PROPAGATE_EXCEPTIONS = False

settings.MIDDLEWARE = [f"{__name__}.A", f"{__name__}.Unused", f"{__name__}.C"]
WSGIHandler()
show("MIDDLEWARE = [A, Unused, C], where Unused raises MiddlewareNotUsed: it is left out of the chain")
settings.MIDDLEWARE = [f"{__name__}.A", f"{__name__}.B", f"{__name__}.C"]

print("From here on A, B and C have process_request and process_response and no other hook, each line says\n"
      "which thread it ran on, and every crossing between the event loop and a thread is written down.\n")
WHERE = True
record_crossings()
signals.request_started.disconnect(on_started)
signals.request_finished.disconnect(on_finished)
signals.got_request_exception.disconnect(on_exception)
settings.MIDDLEWARE = [f"{__name__}.IO_A", f"{__name__}.IO_B", f"{__name__}.IO_C"]

handler = ASGIHandler()
LINES.append(f"the chain: {named(handler._middleware_chain)}")
show("Making an ASGIHandler; A, B and C can only run synchronously (async_capable = False)")
asgi(handler, "/async/", "an async view, synchronous middleware")
asgi(handler, "/plain/", "a synchronous view, synchronous middleware")

InAndOut.async_capable = True
handler = ASGIHandler()
LINES.append(f"the chain: {named(handler._middleware_chain)}")
show("Making an ASGIHandler; A, B and C say they can run either way (async_capable = True)")
asgi(handler, "/async/", "an async view, middleware in async mode")
asgi(handler, "/plain/", "a synchronous view, middleware in async mode")

IO_A.async_capable, IO_B.async_capable, IO_C.async_capable = True, False, True
handler = ASGIHandler()
LINES.append(f"the chain: {named(handler._middleware_chain)}")
show("Making an ASGIHandler; A and C can run either way, B only synchronously")
