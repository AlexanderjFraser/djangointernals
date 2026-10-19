"""A recording of the handler at work: how the middleware chain is built, and what runs, in
what order and on which thread, for a request through it.

    python recordings/handlers.py > recordings/handlers.txt

The chapter of the book (pages/handlers.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and
configures a project of its own in this one file: three middleware, A, B and C, that
write down every hook Django calls on them, and a handful of views. Run it again after a
re-pin: where the output changes, the chapter has to.

Thread names are made stable: the event loop's thread is `loop`, and a thread a request's
synchronous code runs on is `worker` (`worker 1` and `worker 2` in the block of two requests
at once, each named for the request that first wrote a line on it).

The output has four parts, each opened by lines at the margin.

WSGI, with A, B and C writing down every hook. In the blocks of the ways out of the onion, B or
C is a variant with one job (it answers from a hook, raises in process_response, or returns a
response with no render method from process_template_response) and keeps its name; the handler
for such a block is made without writing down the build, and settings.MIDDLEWARE is put back.

ASGI ("From here on A, B and C have process_request and process_response..."): the signal
receivers are disconnected and the server's receive writes nothing.

ASGI, as the server sees it ("From here on the three signal receivers are connected again..."):
- `receive() from X -> message`: the server's receive, called by the handler's method X, returns
  a message at once; `receive() from X: waiting`: it has none to give and waits; then
  `... -> http.disconnect` when it returns after waiting, or `...: cancelled` when what awaits it
  is cancelled. The listener's `waiting` line, marked `[loop, meanwhile]`, is written on the loop
  while the request's thread runs the chain, and which writes first is a race: that line is put
  directly after the last line written on the loop (the call into the thread before it), which is
  where the loop makes the call; its place says nothing about the worker's lines around it.
- The handler is a subclass of ASGIHandler that writes `ASGIRequest(scope, body_file)` as it makes
  the request (and `ASGIRequest.__init__ raises ...`), and `BaseHandler.resolve_request` as it
  resolves the URL. `send(...)` gives the status of http.response.start.
- A disconnect is timed by the code, not a clock: the server's waiting receive returns
  http.disconnect once an event is set, and a view or a B.process_request sets it when it starts.
  An async view then sleeps until it is cancelled. The synchronous view of /hang-sync/ waits until
  the task that async_to_sync started on the loop for the centre of the chain has ended (the script
  wraps asgiref's AsyncToSync.main_wrap to know it), so that the cancellation has reached and ended
  the centre's task before the view returns. The B.process_request that lets the client go waits
  until the loop next hands a call to a thread. Each wait gives up after 30 seconds and its line then
  says so. These two blocks therefore record synchronous code that is still running when the loop
  has handled the disconnect, and their titles say so; code that returns just as the client goes
  can meet other outcomes, which the order of the threads decides.
- Two requests at once: each request's lines are kept apart by a context variable set in its task,
  which follows the request into its threads; only the lines marked worker are shown (the crossings
  are left out), each request's together, and each view waits at a barrier until the other's is running too, so
  that the two requests' threads are alive at the same time.

WSGI again, with Django's own middleware ("From here on, under WSGI again..."): A, B and C have the
two hooks only. Django's middleware are subclasses of the same name that write down each hook as
it is called, with the status of the response given to process_response, and `... raises X`.
`X sees H: value` and `X sees no H header` are headers of the response X's process_response was
given; `(varies)` stands for the Content-Length of a body GZipMiddleware compressed, which it pads
with a random number of bytes. Mail goes through settings.MAILERS, no deprecated email setting
being used (BrokenLinkEmailsMiddleware.send_mail then takes its current branch): MAILERS =
{"default": {"BACKEND": "<this module>.Outbox"}}, where Outbox is Django's in-memory backend
(django.core.mail.backends.locmem.EmailBackend) writing `a mail to ...: "subject"` for each message,
and MANAGERS = ["manager@example.com"]; a warning of any kind during the mail blocks makes the
script exit with an error after them. In the block of Referer headers each line is one request, and says only what came of it.
Every setting a block changes (DEBUG, DISALLOWED_USER_AGENTS, PREPEND_WWW, MAILERS, MANAGERS) is put
back after it, a setting that was not there removed.
"""
import asyncio
import contextlib
import contextvars
import io
import os
import re
import sys
import threading
import warnings

# Python puts a script's directory first on the path, and `http.py` in this one has the name of
# a package of the standard library, which Django imports: take the directory off first.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(newline="\n")  # the same bytes on every machine
LINES = []
WORKERS = set()  # the threads, other than the event loop's, that a request's code was seen on

# For the block of two requests at once: which request a line is for (set in each request's
# task, so that it follows the request into its threads), each request's lines, the threads
# each request's lines were written on, and the name given to each of those threads.
REQUEST = contextvars.ContextVar("request", default=None)
GROUPS = {}
SEEN = {}
NAMES = {}

NOTING = threading.Lock()
LOOP_MARK = 0  # the place just after the last line written on the event loop's thread


def thread() -> str:
    if threading.current_thread() is threading.main_thread():
        return "loop"
    WORKERS.add(threading.get_ident())
    number = REQUEST.get()
    if number is None:
        return "worker"
    ident, seen = threading.get_ident(), SEEN.setdefault(number, [])
    if ident not in seen:
        seen.append(ident)
    if ident not in NAMES:  # a thread is named for the request that first wrote a line on it
        NAMES[ident] = f"worker {number}" + ("" if len(seen) == 1 else f".{len(seen)}")
    return NAMES[ident]


def note(what: str, where: bool = False, after_loop: bool = False) -> None:
    """Write down a line. `after_loop` puts it directly after the last line written on the event
    loop's thread, for a line the loop writes while a thread may be writing too."""
    global LOOP_MARK
    with NOTING:
        line = f"{what}  [{thread()}]" if where else what
        number = REQUEST.get()
        lines = LINES if number is None else GROUPS.setdefault(number, [])
        if after_loop:
            lines.insert(LOOP_MARK, line)
        else:
            lines.append(line)
        if threading.current_thread() is threading.main_thread():
            LOOP_MARK = (LOOP_MARK + 1) if after_loop else len(lines)


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
from django.core.handlers.asgi import ASGIHandler, ASGIRequest  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler  # noqa: E402
from django.core.mail.backends.locmem import EmailBackend  # noqa: E402
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse  # noqa: E402
from django.middleware import MiddlewareMixin  # noqa: E402
from django.middleware.common import BrokenLinkEmailsMiddleware, CommonMiddleware  # noqa: E402
from django.middleware.gzip import GZipMiddleware  # noqa: E402
from django.middleware.http import ConditionalGetMiddleware  # noqa: E402
from django.utils.module_loading import import_string  # noqa: E402
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
        CROSSED.set()
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


# Variants of B and C, each with one job of its own and the name of the middleware it varies.
def answer_request(self, request):
    note(f"{type(self).__name__}.process_request, returning a response")
    return HttpResponse("answered")


def answer_view(self, request, view, args, kwargs):
    note(f"{type(self).__name__}.process_view, returning a response")
    return HttpResponse("answered")


def answer_exception(self, request, exception):
    note(f"{type(self).__name__}.process_exception({type(exception).__name__}), returning a response")
    return HttpResponse("answered")


def raise_in_response(self, request, response):
    note(f"{type(self).__name__}.process_response({response.status_code}), raising RuntimeError")
    raise RuntimeError("raised in a middleware")


def plain_template_response(self, request, response):
    note(f"{type(self).__name__}.process_template_response, returning an HttpResponse")
    return HttpResponse("not a template")


def let_go_in_request(self, request):
    name = type(self).__name__
    note(f"{name}.process_request, letting the client disconnect", WHERE)
    CROSSED.clear()
    LOOP.call_soon_threadsafe(LET_GO.set)
    if CROSSED.wait(30):
        note(f"{name}.process_request returns, after the loop's next call into a thread", WHERE)
    else:
        note(f"{name}.process_request returns, the loop having made no call into a thread in 30 seconds", WHERE)


B_answering_request = type("B", (B,), {"process_request": answer_request})
B_answering_view = type("B", (B,), {"process_view": answer_view})
C_answering_exception = type("C", (C,), {"process_exception": answer_exception})
C_raising_in_response = type("C", (C,), {"process_response": raise_in_response})
B_replacing_template_response = type("B", (B,), {"process_template_response": plain_template_response})


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

IO_B_letting_go = type("B", (IO_B,), {"process_request": let_go_in_request})

LOOK = {}  # block by block: the headers a layer writes down when it sees the response, by its name


class Looking:
    """A layer that, after its process_response, writes down the headers the block asks it about."""

    def process_response(self, request, response):
        response = super().process_response(request, response)
        name = type(self).__name__
        for header in LOOK.get(name, ()):
            if not response.has_header(header):
                note(f"{name} sees no {header} header")
            elif header == "Content-Length" and response.get("Content-Encoding") == "gzip" and not response.streaming:
                note(f"{name} sees {header}: (varies)")  # GZipMiddleware pads the body with random bytes
            else:
                note(f"{name} sees {header}: {response[header]}")
        return response


# A, B and C with the two hooks only, and looking: the blocks of the general-purpose middleware use them.
LOOK_A, LOOK_B, LOOK_C = (type(layer.__name__, (Looking, layer), {}) for layer in (IO_A, IO_B, IO_C))


def watched(real):
    """The middleware `real` itself, as a subclass of the same name that writes down each of its
    hooks as it is called (with the status of the response it is given) and what one raises."""

    def hook(name):
        def run(self, request, *args):
            note(f"{real.__name__}.{name}" + (f"({args[0].status_code})" if args else ""), WHERE)
            try:
                return getattr(real, name)(self, request, *args)
            except Exception as raised:
                note(f"{real.__name__}.{name} raises {type(raised).__name__}", WHERE)
                raise

        return run

    hooks = {name: hook(name) for name in ("process_request", "process_response") if hasattr(real, name)}
    return type(real.__name__, (real,), hooks)


Common, GZip, BrokenLinks, Conditional = map(
    watched, (CommonMiddleware, GZipMiddleware, BrokenLinkEmailsMiddleware, ConditionalGetMiddleware)
)


class Outbox(EmailBackend):
    """Django's in-memory mail backend, writing down each message it is given."""

    def send_messages(self, messages):
        for message in messages:
            note(f'a mail to {", ".join(message.to)}: "{message.subject}"', WHERE)
        return super().send_messages(messages)


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


def boom():
    note("the template calls boom, which raises ValueError")
    raise ValueError


def template_raises(request):
    note("the view, returning a TemplateResponse of {{ boom }}")
    return TemplateResponse(request, engines["django"].from_string("{{ boom }}"), {"boom": boom})


LOOP = None  # the running event loop, in the ASGI blocks
LET_GO = None  # an asyncio.Event of that loop: once it is set, the server's waiting receive returns http.disconnect
CENTRE_ENDED = threading.Event()  # set each time a task that async_to_sync started on the loop ends
CROSSED = threading.Event()  # set each time the event loop hands a call to a thread (sync_to_async)


async def hang(request):
    note("the view (async def), letting the client disconnect", WHERE)
    LET_GO.set()
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        note("the view (async def) is cancelled", WHERE)
        raise
    note("the view (async def) was not cancelled in 30 seconds", WHERE)
    return HttpResponse("ok")


def hang_sync(request):
    note("the view, letting the client disconnect", WHERE)
    CENTRE_ENDED.clear()
    LOOP.call_soon_threadsafe(LET_GO.set)
    if CENTRE_ENDED.wait(30):
        note("the view returns, after the centre's task on the loop has ended", WHERE)
    else:
        note("the view returns, the centre's task on the loop not having ended in 30 seconds", WHERE)
    return HttpResponse("ok")


TOGETHER = threading.Barrier(2)


def together(request):
    note("the view, waiting until the other request's view is running too", WHERE)
    TOGETHER.wait(30)
    return HttpResponse("ok")


def small(request):
    note("the view, returning 199 bytes")
    return HttpResponse(b"x" * 199)


def large(request):
    note("the view, returning 400 bytes")
    return HttpResponse(b"x" * 400)


def tagged(request):
    note('the view, returning 400 bytes with ETag: "v1"')
    response = HttpResponse(b"x" * 400)
    response["ETag"] = '"v1"'
    return response


def stream(request):
    note("the view, returning a StreamingHttpResponse")
    return StreamingHttpResponse(iter([b"ok"]))


def a_file(request):
    note("the view, returning a FileResponse of 400 bytes")
    return FileResponse(io.BytesIO(b"x" * 400))


urlpatterns += [
    path("template-raises/", template_raises), path("hang/", hang), path("hang-sync/", hang_sync),
    path("together/", together), path("small/", small), path("large/", large), path("tagged/", tagged),
    path("stream/", stream), path("file/", a_file),
]


def on_started(**kwargs):
    note("signal: request_started", WHERE)


def on_finished(**kwargs):
    note("signal: request_finished", WHERE)


def on_exception(**kwargs):
    note("signal: got_request_exception", WHERE)


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


def built(handler_class, *names: str, say: bool = True):
    """A handler for MIDDLEWARE = names, made without writing down the build; settings.MIDDLEWARE
    is put back as it was. With `say`, its requests' blocks begin with the chain."""
    before = settings.MIDDLEWARE
    settings.MIDDLEWARE = [f"{__name__}.{name}" for name in names]
    made = handler_class()
    LINES.clear()
    settings.MIDDLEWARE = before
    layers = ", ".join(import_string(f"{__name__}.{name}").__name__ for name in names)
    made.chain_line = f"MIDDLEWARE = [{layers}]" if say else None
    return made


@contextlib.contextmanager
def changed(**values):
    """Settings for one block, put back as they were after it (one that was not there is removed)."""
    before = {name: getattr(settings, name) for name in values if hasattr(settings, name)}
    for name, value in values.items():
        setattr(settings, name, value)
    try:
        yield
    finally:
        for name in values:
            if name in before:
                setattr(settings, name, before[name])
            else:
                delattr(settings, name)


def wsgi_call(handler, method: str, url: str, **environ) -> None:
    """As wsgi() does, for any method, with more of the environ (a header as HTTP_...)."""
    environ = {"REQUEST_METHOD": method, "PATH_INFO": url, "SERVER_NAME": "recording", "SERVER_PORT": "80",
               "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.input": io.BytesIO(b""), "wsgi.url_scheme": "http", **environ}

    def start_response(status, headers):
        note(f'start_response("{status}", headers)')

    if getattr(handler, "chain_line", None):
        note(handler.chain_line)
    try:
        response = handler(environ, start_response)
    except Exception as raised:
        note(f"the handler raises {type(raised).__name__} to the server")
    else:
        b"".join(response)
        note("the server closes the response")
        response.close()


def wsgi_request(handler, method: str, url: str, title: str, **environ) -> None:
    wsgi_call(handler, method, url, **environ)
    show(f"WSGI, {method} {url}: {title}")


class RecordedRequest(ASGIRequest):
    """An ASGIRequest that writes down its making."""

    def __init__(self, scope, body_file):
        note("ASGIRequest(scope, body_file)", WHERE)
        try:
            super().__init__(scope, body_file)
        except Exception as raised:
            note(f"ASGIRequest.__init__ raises {type(raised).__name__}", WHERE)
            raise


class Handler(ASGIHandler):
    """An ASGIHandler that writes down the request it makes and the URL it resolves."""

    request_class = RecordedRequest

    def resolve_request(self, request):
        note("BaseHandler.resolve_request", WHERE)
        return super().resolve_request(request)


def watch_awaited_tasks() -> None:
    """From here on, set CENTRE_ENDED as each task that asgiref's async_to_sync starts on the
    event loop ends (AsyncToSync.main_wrap is what runs in that task)."""
    from asgiref.sync import AsyncToSync

    main_wrap = AsyncToSync.main_wrap

    async def watched_main_wrap(self, *args, **kwargs):
        try:
            return await main_wrap(self, *args, **kwargs)
        finally:
            CENTRE_ENDED.set()

    AsyncToSync.main_wrap = watched_main_wrap


def described(message) -> str:
    if message["type"] == "http.request":
        return f"http.request, more_body {message.get('more_body', False)}"
    return message["type"]


async def serve(handler, method: str, url: str, *, query=b"", messages=None, number=None, write_receive=True):
    """Play an ASGI server's part for one request. receive returns the messages given, one a call
    (by default the whole of an empty body); when they are spent it waits, until a view lets the
    client go (it then returns http.disconnect) or until it is cancelled."""
    if number is not None:
        REQUEST.set(number)
    waiting = list(messages or [{"type": "http.request", "body": b"", "more_body": False}])

    async def receive():
        caller = sys._getframe(1).f_code.co_qualname
        if waiting:
            message = waiting.pop(0)
            if write_receive:
                note(f"receive() from {caller} -> {described(message)}", WHERE, after_loop=True)
            return message
        if write_receive:
            note(f"receive() from {caller}: waiting  [{thread()}, meanwhile]", after_loop=True)
        try:
            await LET_GO.wait()
        except asyncio.CancelledError:
            if write_receive:
                note(f"receive() from {caller}: cancelled", WHERE)
            raise
        if write_receive:
            note(f"receive() from {caller} -> http.disconnect", WHERE)
        return {"type": "http.disconnect"}

    async def send(message):
        status = f", status {message['status']}" if "status" in message else ""
        note(f"send({message['type']}){status}", WHERE)

    scope = {"type": "http", "method": method, "path": url, "headers": [], "query_string": query}
    await handler(scope, receive, send)


def run_asgi(title: str, *requests) -> None:
    """Run the requests (coroutines of serve) together under one event loop, and show the block."""
    global LOOP_MARK

    async def main():
        global LOOP, LET_GO
        LOOP, LET_GO = asyncio.get_running_loop(), asyncio.Event()
        await asyncio.gather(*requests)

    WORKERS.clear()
    GROUPS.clear(), SEEN.clear(), NAMES.clear()
    LOOP_MARK = 0
    asyncio.run(main())
    if GROUPS:  # two requests at once: each request's lines written on a worker thread, together
        for number in sorted(GROUPS):
            LINES.append(f"request {number}:")
            LINES.extend("    " + line for line in GROUPS[number] if "  [worker" in line)
        for number in sorted(GROUPS):
            count = len(SEEN.get(number, []))
            LINES.append(f"(request {number}'s lines marked worker ran on {count} thread{'' if count == 1 else 's'})")
        shared = set(SEEN.get(1, [])) & set(SEEN.get(2, []))
        LINES.append("(a thread ran lines of both requests)" if shared else "(no thread ran lines of both requests)")
    elif not WORKERS:
        LINES.append("(nothing ran on a worker thread)")
    else:
        LINES.append(f"(everything marked worker ran on {len(WORKERS)} thread)" if len(WORKERS) == 1
                     else f"(worker threads seen: {len(WORKERS)})")
    show(title)


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

# The ways out of the onion: each block's B or C is a variant with one job (the handler for it is
# made without writing down the build), A and the others are as above.
wsgi(built(WSGIHandler, "A", "B_answering_request", "C", say=False), "/plain/",
     "B.process_request returns a response")
wsgi(built(WSGIHandler, "A", "B_answering_view", "C", say=False), "/plain/",
     "B.process_view returns a response")
wsgi(built(WSGIHandler, "A", "B", "C_answering_exception", say=False), "/broken/",
     "the view raises ValueError, and C.process_exception returns a response")
wsgi(built(WSGIHandler, "A", "B", "C_raising_in_response", say=False), "/plain/",
     "C.process_response raises RuntimeError")
wsgi(handler, "/template-raises/", "a TemplateResponse whose template raises ValueError when it is rendered")
wsgi(built(WSGIHandler, "A", "B_replacing_template_response", "C", say=False), "/template/",
     "B.process_template_response returns an HttpResponse, which has no render method")

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

print("From here on the three signal receivers are connected again, the server's receive writes a line\n"
      "each time it is called, and the handler writes down the request it makes and the URL it resolves.\n")
signals.request_started.connect(on_started)
signals.request_finished.connect(on_finished)
signals.got_request_exception.connect(on_exception)
watch_awaited_tasks()

run_asgi("ASGI, GET /async/: an async view, A and C either way and B only synchronously",
         serve(built(Handler, "IO_A", "IO_B", "IO_C", say=False), "GET", "/async/"))

IO_A.async_capable, IO_B.async_capable, IO_C.async_capable = False, False, False
synchronous = built(Handler, "IO_A", "IO_B", "IO_C", say=False)
run_asgi("ASGI, GET /plain/: a synchronous view, synchronous middleware, as the server sees it",
         serve(synchronous, "GET", "/plain/"))
run_asgi('ASGI, GET /plain/ with the query string b"q=\\xff", which is not UTF-8: a 400 from ASGIHandler.create_request',
         serve(synchronous, "GET", "/plain/", query=b"q=\xff"))
run_asgi("ASGI, POST /plain/: the client disconnects while the body is arriving",
         serve(synchronous, "POST", "/plain/", messages=[{"type": "http.request", "body": b"part", "more_body": True},
                                                        {"type": "http.disconnect"}]))

IO_A.async_capable, IO_B.async_capable, IO_C.async_capable = True, True, True
run_asgi("ASGI, GET /hang/: the client disconnects during an async view, middleware in async mode",
         serve(built(Handler, "IO_A", "IO_B", "IO_C", say=False), "GET", "/hang/"))
IO_A.async_capable, IO_B.async_capable, IO_C.async_capable = False, False, False
run_asgi("ASGI, GET /hang/: the client disconnects during an async view, synchronous middleware",
         serve(synchronous, "GET", "/hang/"))
run_asgi("ASGI, GET /hang-sync/: the client disconnects during a synchronous view that is still running when the loop "
         "has handled it, synchronous middleware",
         serve(synchronous, "GET", "/hang-sync/"))
run_asgi("ASGI, GET /plain/: the client disconnects during B.process_request, which is still running when the loop "
         "has handled it, synchronous middleware",
         serve(built(Handler, "IO_A", "IO_B_letting_go", "IO_C", say=False), "GET", "/plain/"))

run_asgi("ASGI, GET /together/ twice at once under one event loop, synchronous middleware: the threads",
         serve(synchronous, "GET", "/together/", number=1, write_receive=False),
         serve(synchronous, "GET", "/together/", number=2, write_receive=False))

WHERE = False
print("From here on, under WSGI again, A, B and C have process_request and process_response only and stand\n"
      "around Django's own middleware, which write down their hooks as they are called. A line \"A sees\" is a\n"
      "header of the response A's process_response was given, and so for B and C. A block's first line is the chain.\n")

common = built(WSGIHandler, "LOOK_A", "Common", "LOOK_C")
LOOK = {"A": ("Location",)}
wsgi_request(common, "GET", "/plain", "CommonMiddleware turns the 404 that C saw into a redirect")
LOOK = {}
with changed(DEBUG=True):
    wsgi_request(common, "POST", "/plain", "with DEBUG = True, CommonMiddleware.process_response raises RuntimeError")
with changed(DISALLOWED_USER_AGENTS=[re.compile("badbot")]):
    wsgi_request(common, "GET", "/plain/", "the User-Agent is one that DISALLOWED_USER_AGENTS refuses",
                 HTTP_USER_AGENT="badbot/1.0")
LOOK = {"A": ("Location",)}
with changed(PREPEND_WWW=True):
    wsgi_request(common, "GET", "/plain", "with PREPEND_WWW = True, one redirect for the www. and the slash")
LOOK = {"A": ("Content-Length",), "C": ("Content-Length",)}
wsgi_request(common, "GET", "/plain/", "CommonMiddleware gives a response the Content-Length it lacked")
wsgi_request(common, "GET", "/stream/", "CommonMiddleware gives a streaming response no Content-Length")

compressing = built(WSGIHandler, "LOOK_A", "GZip", "LOOK_C")
LOOK = {"A": ("Content-Encoding", "Vary")}
wsgi_request(compressing, "GET", "/small/", "GZipMiddleware and a body under 200 bytes, with Accept-Encoding: gzip",
             HTTP_ACCEPT_ENCODING="gzip")
wsgi_request(compressing, "GET", "/large/", "GZipMiddleware and 400 bytes, with no Accept-Encoding")
LOOK = {"C": ("ETag", "Content-Length"), "A": ("Content-Encoding", "Vary", "ETag", "Content-Length")}
wsgi_request(compressing, "GET", "/tagged/", "GZipMiddleware and 400 bytes with a strong ETag, with Accept-Encoding: gzip",
             HTTP_ACCEPT_ENCODING="gzip")
LOOK = {"C": ("Content-Length",), "A": ("Content-Encoding", "Content-Length")}
wsgi_request(compressing, "GET", "/file/", "GZipMiddleware and a FileResponse, with Accept-Encoding: gzip",
             HTTP_ACCEPT_ENCODING="gzip")
LOOK = {"B": ("ETag", "Content-Encoding"), "A": ("ETag", "Content-Encoding")}
wsgi_request(built(WSGIHandler, "LOOK_A", "GZip", "LOOK_B", "Conditional"), "GET", "/large/",
             "ConditionalGetMiddleware inside GZipMiddleware, with Accept-Encoding: gzip", HTTP_ACCEPT_ENCODING="gzip")

# BrokenLinkEmailsMiddleware mails through settings.MAILERS (no deprecated email setting is used):
# its default mailer is Outbox, Django's in-memory backend writing down what it is given.
LOOK = {}
with warnings.catch_warnings(record=True) as caught, changed(
    MAILERS={"default": {"BACKEND": f"{__name__}.Outbox"}}, MANAGERS=["manager@example.com"]
):
    warnings.simplefilter("always")
    broken_links = built(WSGIHandler, "LOOK_A", "BrokenLinks", "LOOK_C")
    wsgi_request(broken_links, "GET", "/missing/", "BrokenLinkEmailsMiddleware and a 404 with a Referer on the same host",
                 HTTP_REFERER="http://recording/elsewhere/")

    def mailed(debug: bool = False, **environ) -> str:
        """What came of one request: the mail lines it wrote, or that it wrote none."""
        with changed(DEBUG=debug):
            wsgi_call(broken_links, "GET", "/missing/", **environ)
        mails = [line for line in LINES if line.startswith("a mail")]
        LINES.clear()
        return "; ".join(mails) or "no mail"

    table = [broken_links.chain_line, f"no Referer -> {mailed()}"]
    for referer in ("http://recording/elsewhere/", "https://example.com/page/"):
        table.append(f"Referer: {referer} -> {mailed(HTTP_REFERER=referer)}")
    table.append(f"Referer: http://recording/elsewhere/, with DEBUG = True -> "
                 f"{mailed(debug=True, HTTP_REFERER='http://recording/elsewhere/')}")
    for referer in ("http://recording/missing", "/missing"):
        table.append(f"Referer: {referer} -> {mailed(HTTP_REFERER=referer)}")
    LINES.extend(table)
    show("WSGI, GET /missing/, the view raising Http404, through BrokenLinkEmailsMiddleware: which Referer mails")

    wsgi_request(built(WSGIHandler, "LOOK_A", "BrokenLinks", "Common", "LOOK_C"), "GET", "/plain",
                 "BrokenLinkEmailsMiddleware outside CommonMiddleware, with a Referer on the same host",
                 HTTP_REFERER="http://recording/elsewhere/")
    wsgi_request(built(WSGIHandler, "LOOK_A", "Common", "BrokenLinks", "LOOK_C"), "GET", "/plain",
                 "BrokenLinkEmailsMiddleware inside CommonMiddleware, with a Referer on the same host",
                 HTTP_REFERER="http://recording/elsewhere/")
if caught:
    raise SystemExit("the mail blocks warned: " + "; ".join(str(warning.message) for warning in caught))
