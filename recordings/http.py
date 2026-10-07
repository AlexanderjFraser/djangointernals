"""A recording of requests and responses: what making a request object does and what each
first read of it does, how a body and an upload are parsed, and how a response leaves, under
WSGI and under ASGI.

    python recordings/http.py > recordings/http.txt

Chapter 5 of the book (pages/http.md and the pages under it) is written against this output.
It needs only the pinned Django (the project's virtual environment has it) and configures a
project of its own in this one file: no middleware, a handful of views, and a script that
plays the server's part. Run it again after a re-pin: where the output changes, the chapter
has to.

A block is one of two kinds. Where the order of calls is the point, the lines are the calls
of Django's own functions that the chapter names, nested as they were made, with the
arguments that tell them apart; a line that begins `->` is what the call above it returned,
and `raises` the exception that left it. Everything between them ran and is left out. The
other blocks put one question to a running Django on each line and write down the answer.

`time.time` is stopped, so that a cookie's expiry date and a signature's timestamp are the same
on every run. The sizes in the titles and labels are computed from the data, not typed.

    RECORD_EVERYTHING=1 python recordings/http.py     every call in the chapter's modules
"""
import os
import sys
import weakref

# This file is named for its chapter, and so has the name of a package of the standard
# library. Python puts a script's directory first on the path: take it off before anything
# imports `http`.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]

import asyncio  # noqa: E402
import io  # noqa: E402
import logging  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = bool(os.environ.get("RECORD_EVERYTHING"))

settings.configure(
    DEBUG=False,
    SECRET_KEY="recording",
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["shop.example"],
    MIDDLEWARE=[],
    TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates"}],
)
django.setup()

from django.core import signals, signing  # noqa: E402
from django.core.handlers.asgi import ASGIHandler, ASGIRequest  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler, WSGIRequest  # noqa: E402
from django.http import (  # noqa: E402
    FileResponse, HttpResponse, HttpResponseNotAllowed, HttpResponseNotModified, HttpResponsePermanentRedirect,
    HttpResponseRedirect, JsonResponse, QueryDict, StreamingHttpResponse, parse_cookie,
)
from django.urls import path  # noqa: E402

NOW = 1790000000.0  # 21 September 2026, 14:13:20 GMT
time.time = lambda: NOW

LINES = []
STACK = []  # the watched frames open at this moment: the depth of the next line
SEEN = {}  # generator frames already written down: a generator is entered once per value
PENDING = []  # the watched call that has just returned: (frame, depth, what to say of its value, the value)
RAISED = []  # exceptions already written down, at the innermost watched call they left: the objects, since an id is used again
UPLOAD = {"open": False, "chunks": 0, "more": 0, "last": None, "reads": 0}  # the file being uploaded
GIVEN = {}  # what a header was set to, by the frame of the call that set it
HANDLERS = []  # the upload handlers of the request being parsed


def flush() -> None:
    """Say what the call that has just returned gave back, if that is to be said."""
    while PENDING:
        frame, depth, after, value = PENDING.pop(0)
        said = after(frame, value) if after else None
        if said is not None:
            LINES.append("  " * depth + f"-> {said}")


def note(text: str) -> None:
    flush()
    LINES.append("  " * len(STACK) + text)


def show(title: str) -> None:
    flush()
    print(title)
    for line in LINES:
        print("    " + line)
    print()
    LINES.clear()
    STACK.clear()
    SEEN.clear()
    RAISED.clear()


class reading:
    """`with reading("request.GET"):` writes down what the view is about to do, and nests
    under that line whatever Django does in the block. It says nothing where calls are not
    being recorded."""

    def __init__(self, what: str, verb: str = "the view reads"):
        self.line = f"{verb} {what}"

    def __enter__(self):
        if sys.getprofile() is not None:
            note(self.line)
        STACK.append(self)

    def __exit__(self, *exc):
        while STACK and STACK[-1] is not self:
            STACK.pop()
        STACK.pop()


# ---------------------------------------------------------------------------------------------
# What to write down, and how to say it. A label function is given the frame at the moment of
# the call and returns the line, or None for a call not to write down.

def cls_of(frame) -> str:
    return type(frame.f_locals["self"]).__name__


def plain(frame) -> str:
    return frame.f_code.co_qualname


def with_arg(name: str):
    def label(frame):
        return f"{frame.f_code.co_qualname}({frame.f_locals[name]!r})"
    return label


def on(frame) -> str:
    """A method by the class that declares it, and the class of the object when that differs."""
    declared = frame.f_code.co_qualname
    actual = cls_of(frame)
    return declared if declared.startswith(actual + ".") else f"{declared}  ({actual})"


def short(value, limit: int = 60) -> str:
    text = repr(value)
    return text if len(text) <= limit else f"{text[:limit - 20]}... ({len(value)} {'bytes' if isinstance(value, bytes) else 'characters'})"


def setter(name: str):
    """A property's setter and its getter share a qualified name: write down only the setter."""
    def label(frame):
        if name not in frame.f_locals:
            return None
        return f"{frame.f_code.co_qualname} = {short(frame.f_locals[name])}"
    return label


def signal_sent(frame):
    signal = frame.f_locals["self"]
    for name in ("request_started", "request_finished", "got_request_exception"):
        if getattr(signals, name) is signal:
            return f"signal {name}"
    return None


def query_dict(frame):
    query_string = frame.f_locals["query_string"]
    if not query_string:
        return None
    return f"QueryDict.__init__({short(query_string)}, encoding={frame.f_locals['encoding']!r})"


def parser_made(frame) -> str:
    HANDLERS[:] = list(frame.f_locals["upload_handlers"])
    UPLOAD.update(open=False, chunks=0, more=0, last=None, reads=0)
    return f"MultiPartParser.__init__(META, input_data, upload_handlers, encoding={frame.f_locals['encoding']!r})"


def between_chunks() -> bool:
    """Whether the parser is in its loop over a file's chunks, past the first."""
    top = STACK[-1] if STACK else None
    return UPLOAD["open"] and UPLOAD["chunks"] >= 1 and getattr(getattr(top, "f_code", None), "co_qualname", "") == "MultiPartParser.parse"


def request_read(frame):
    if between_chunks():
        UPLOAD["reads"] += 1
        return None
    return f"HttpRequest.read({', '.join(map(repr, frame.f_locals['args']))})"


def limited_read(frame):
    return None if between_chunks() else f"LimitedStream.read({frame.f_locals['size']})"


def new_file(frame) -> str:
    args = frame.f_locals["args"]
    UPLOAD.update(open=True, chunks=0, more=0, last=None, reads=0)
    return f'{frame.f_code.co_qualname}("{args[0]}", "{args[1]}", "{args[2]}")'


def chunk(frame):
    """Every chunk of a file goes to each handler in turn. The first chunk's calls are written
    down; the rest are counted, and said in one line when the file's last chunk has gone."""
    first = frame.f_locals["self"] is HANDLERS[0]
    if first:
        UPLOAD["chunks"] += 1
    if UPLOAD["chunks"] > 1:
        if first:
            UPLOAD["more"] += 1
            UPLOAD["last"] = (len(frame.f_locals["raw_data"]), frame.f_locals["start"])
        return None
    return f"{frame.f_code.co_qualname}({len(frame.f_locals['raw_data'])} bytes, start={frame.f_locals['start']})"


def rest_of_file() -> None:
    if UPLOAD["more"]:
        size, start = UPLOAD["last"]
        note(f"... {UPLOAD['reads']} more reads of the stream and {UPLOAD['more']} more chunks, each chunk through the same "
             f"calls; the last is {size} bytes at start={start}")
        UPLOAD["more"] = 0


def part(frame) -> str:
    rest_of_file()
    return "parse_boundary_stream"


def file_complete(frame) -> str:
    rest_of_file()
    UPLOAD["open"] = False
    return f'MultiPartParser.handle_file_complete("{frame.f_locals["old_field_name"]}")'


def header_set(frame) -> str:
    GIVEN[id(frame)] = frame.f_locals["value"]
    return f'response["{frame.f_locals["key"]}"] = {frame.f_locals["value"]!r}'


def header_stored(frame, value):
    given = GIVEN.pop(id(frame), None)
    stored = frame.f_locals["value"]
    return None if type(given) is str and given == stored else f"stored as {stored!r}"


def cookie_set(frame) -> str:
    f = frame.f_locals
    given = ", ".join(f"{k}={f[k]!r}" for k in ("max_age", "expires", "path", "domain", "secure", "httponly", "samesite")
                      if f[k] not in (None, False) and not (k == "path" and f[k] == "/"))
    return f'HttpResponseBase.set_cookie("{f["key"]}", {f["value"]!r}{", " + given if given else ""})'


# (module, qualname) -> the label function. COMMON is written down in every recorded request;
# REQUEST where the block is about the request, RESPONSE where it is about the response.
COMMON = {
    ("django.core.handlers.wsgi", "WSGIHandler.__call__"): lambda f: "WSGIHandler.__call__(environ, start_response)",
    ("django.dispatch.dispatcher", "Signal.send"): signal_sent,
    ("django.core.handlers.wsgi", "WSGIRequest.__init__"): lambda f: "WSGIRequest.__init__(environ)",
    ("django.core.handlers.base", "BaseHandler.get_response"): plain,
    ("django.http.response", "HttpResponseBase.close"): on,
    ("django.http.request", "HttpRequest.close"): plain,
    ("django.core.files.uploadedfile", "TemporaryUploadedFile.close"): plain,
    ("django.core.files.base", "File.close"): on,
}

REQUEST = {
    # the request is made
    ("django.http.request", "HttpRequest._set_content_type_params"): plain,
    ("django.utils.http", "parse_header_parameters"): with_arg("line"),
    ("django.http.request", "HttpRequest.encoding"): setter("val"),
    ("django.core.handlers.wsgi", "LimitedStream.__init__"): lambda f: f"LimitedStream.__init__(stream, limit={f.f_locals['limit']})",
    # what is read on first use
    ("django.core.handlers.wsgi", "WSGIRequest.GET"): plain,
    ("django.http.request", "QueryDict.__init__"): query_dict,
    ("django.core.handlers.wsgi", "WSGIRequest.COOKIES"): plain,
    ("django.http.cookie", "parse_cookie"): with_arg("cookie"),
    ("django.http.request", "HttpRequest.headers"): plain,
    ("django.http.request", "HttpHeaders.__init__"): lambda f: "HttpHeaders.__init__(META)",
    ("django.http.request", "HttpRequest.get_host"): plain,
    ("django.http.request", "HttpRequest._get_raw_host"): plain,
    ("django.http.request", "validate_host"): lambda f: f"validate_host({f.f_locals['host']!r}, {f.f_locals['allowed_hosts']!r})",
    # the body
    ("django.core.handlers.wsgi", "WSGIRequest._get_post"): plain,
    ("django.core.handlers.wsgi", "WSGIRequest.FILES"): plain,
    ("django.http.request", "HttpRequest._load_post_and_files"): plain,
    ("django.http.request", "HttpRequest._mark_post_parse_error"): plain,
    ("django.http.request", "HttpRequest.body"): plain,
    ("django.http.request", "HttpRequest._check_data_too_big"): with_arg("length"),
    ("django.http.request", "HttpRequest.read"): request_read,
    ("django.core.handlers.wsgi", "LimitedStream.read"): limited_read,
    # a multipart body
    ("django.http.request", "HttpRequest.parse_file_upload"): plain,
    ("django.http.request", "HttpRequest._initialize_handlers"): plain,
    ("django.core.files.uploadhandler", "load_handler"): lambda f: f'load_handler("{f.f_locals["path"]}", request)',
    ("django.http.multipartparser", "MultiPartParser.__init__"): parser_made,
    ("django.http.multipartparser", "MultiPartParser.parse"): plain,
    ("django.core.files.uploadhandler", "FileUploadHandler.handle_raw_input"): on,
    ("django.core.files.uploadhandler", "MemoryFileUploadHandler.handle_raw_input"): lambda f: f"MemoryFileUploadHandler.handle_raw_input(content_length={f.f_locals['content_length']})",
    ("django.http.multipartparser", "parse_boundary_stream"): part,
    ("django.http.multipartparser", "MultiPartParser.sanitize_file_name"): with_arg("file_name"),
    ("django.core.files.uploadhandler", "MemoryFileUploadHandler.new_file"): new_file,
    ("django.core.files.uploadhandler", "TemporaryFileUploadHandler.new_file"): new_file,
    ("django.core.files.uploadedfile", "TemporaryUploadedFile.__init__"): lambda f: f'TemporaryUploadedFile.__init__("{f.f_locals["name"]}", ...)',
    ("django.core.files.uploadhandler", "MemoryFileUploadHandler.receive_data_chunk"): chunk,
    ("django.core.files.uploadhandler", "TemporaryFileUploadHandler.receive_data_chunk"): chunk,
    ("django.http.multipartparser", "MultiPartParser.handle_file_complete"): file_complete,
    ("django.core.files.uploadhandler", "MemoryFileUploadHandler.file_complete"): with_arg("file_size"),
    ("django.core.files.uploadhandler", "TemporaryFileUploadHandler.file_complete"): with_arg("file_size"),
    ("django.core.files.uploadhandler", "FileUploadHandler.upload_complete"): on,
    ("django.core.files.uploadhandler", "FileUploadHandler.upload_interrupted"): on,
    ("django.core.files.uploadhandler", "TemporaryFileUploadHandler.upload_interrupted"): on,
}

RESPONSE = {
    # the response is made
    ("django.http.response", "HttpResponse.__init__"): on,
    ("django.http.response", "HttpResponseBase.__init__"): plain,
    ("django.http.response", "ResponseHeaders.__setitem__"): header_set,
    ("django.http.response", "HttpResponse.content"): setter("value"),
    ("django.http.response", "HttpResponse.write"): lambda f: f"HttpResponse.write({short(f.f_locals['content'])})",
    ("django.http.response", "HttpResponseBase.set_cookie"): cookie_set,
    ("django.http.response", "StreamingHttpResponse.__init__"): on,
    ("django.http.response", "StreamingHttpResponse._set_streaming_content"): on,
    ("django.http.response", "FileResponse.__init__"): plain,
    ("django.http.response", "FileResponse._set_streaming_content"): plain,
    ("django.http.response", "FileResponse.set_headers"): plain,
    ("django.utils.http", "content_disposition_header"): lambda f: f"content_disposition_header({f.f_locals['as_attachment']!r}, {f.f_locals['filename']!r})",
    # the response leaves
    ("django.http.response", "HttpResponse.__iter__"): plain,
    ("django.http.response", "StreamingHttpResponse.__iter__"): on,
}

# What a refused request is recorded with: enough to see where the exception left.
LIMITS = {
    ("django.core.handlers.wsgi", "WSGIRequest.__init__"): lambda f: "WSGIRequest.__init__(environ)",
    ("django.http.request", "HttpRequest._set_content_type_params"): plain,
    ("django.http.request", "HttpRequest._load_post_and_files"): plain,
    ("django.http.request", "HttpRequest._mark_post_parse_error"): plain,
    ("django.http.request", "HttpRequest.body"): plain,
    ("django.core.handlers.wsgi", "WSGIRequest.GET"): plain,
    ("django.http.request", "HttpRequest.get_host"): plain,
    ("django.http.multipartparser", "MultiPartParser.__init__"): lambda f: "MultiPartParser.__init__",
    ("django.http.multipartparser", "MultiPartParser.parse"): plain,
}

RULES = {}  # the set in force


def returned_size(frame, value):
    return f"{len(value)} bytes"


def returned_part(frame, value):
    kind, headers, stream = value
    if kind == "raw":
        return "raw: no headers" if not headers else "raw: no Content-Disposition"
    disposition = headers["content-disposition"][1]
    said = ", ".join(f'{k}="{v.decode()}"' for k, v in disposition.items())
    return f"{kind}: {said}"


# (module, qualname) -> what to say of the value a call returned, or None to say nothing.
AFTER = {
    ("django.core.handlers.wsgi", "LimitedStream.read"): returned_size,
    ("django.http.request", "HttpRequest.body"): returned_size,
    ("django.http.request", "HttpRequest.get_host"): lambda f, v: repr(v),
    ("django.http.request", "HttpRequest._get_raw_host"): lambda f, v: repr(v),
    ("django.http.request", "validate_host"): lambda f, v: repr(v),
    ("django.utils.http", "parse_header_parameters"): lambda f, v: repr(v),
    ("django.http.cookie", "parse_cookie"): lambda f, v: repr(v),
    ("django.core.files.uploadhandler", "MemoryFileUploadHandler.handle_raw_input"): lambda f, v: f"{v!r}, and activated = {f.f_locals['self'].activated}",
    ("django.core.files.uploadhandler", "FileUploadHandler.handle_raw_input"): lambda f, v: repr(v),
    ("django.http.multipartparser", "parse_boundary_stream"): returned_part,
    ("django.http.multipartparser", "MultiPartParser.sanitize_file_name"): lambda f, v: repr(v),
    ("django.core.files.uploadhandler", "MemoryFileUploadHandler.receive_data_chunk"): lambda f, v: "None: the chunk is kept, and goes no further" if v is None else "the chunk, for the next handler",
    ("django.core.files.uploadhandler", "TemporaryFileUploadHandler.receive_data_chunk"): lambda f, v: "None: the chunk is written to the file" if v is None else "the chunk",
    ("django.core.files.uploadhandler", "MemoryFileUploadHandler.file_complete"): lambda f, v: repr(v),
    ("django.core.files.uploadhandler", "TemporaryFileUploadHandler.file_complete"): lambda f, v: repr(v),
    ("django.utils.http", "content_disposition_header"): lambda f, v: repr(v),
    ("django.http.response", "ResponseHeaders.__setitem__"): header_stored,
}

OURS = ("django.http", "django.core.files.uploadhandler", "django.core.files.uploadedfile", "django.utils.http",
        "django.core.handlers.wsgi")


def find(module: str, qualname: str):
    label = RULES.get((module, qualname))
    if label is None and EVERYTHING and module.startswith(OURS) and "<" not in qualname:
        return plain
    return label


def profile(frame, event, arg):
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), code.co_qualname)
        if label is None:
            return
        if code.co_flags & 0x20:  # a generator: every resumption is a call event
            known = SEEN.get(id(frame))
            if known is not None and known() is frame.f_generator:
                STACK.append(frame)
                return
            SEEN[id(frame)] = weakref.ref(frame.f_generator)  # by its generator, weakly held: a frame's address is used again once its generator is gone
        text = label(frame)
        if text is None:
            return
        note(text)
        STACK.append(frame)
    elif event == "return":
        if STACK and STACK[-1] is frame:
            flush()
            after = None if code.co_flags & 0x20 else AFTER.get((frame.f_globals.get("__name__", ""), code.co_qualname))
            PENDING.append((frame, len(STACK), after, arg))
            STACK.pop()


def unwinding(code, offset, exception):
    """An exception is leaving a function. The profile hook has just been told that the
    function returned None: where it was a watched call, take that back, and say what was
    raised, once, at the innermost watched call the exception leaves."""
    frame = sys._getframe(1)
    if PENDING and PENDING[-1][0] is frame:
        depth = PENDING.pop()[1]
        if not any(e is exception for e in RAISED) and not isinstance(exception, (StopIteration, GeneratorExit)):
            RAISED.append(exception)
            LINES.append("  " * depth + f"raises {type(exception).__name__}")


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/http.py")
sys.monitoring.register_callback(MONITOR, sys.monitoring.events.PY_UNWIND, unwinding)
sys.monitoring.set_events(MONITOR, sys.monitoring.events.PY_UNWIND)


class Logged(logging.Handler):
    def emit(self, record):
        note(f"logged by {record.name} at {record.levelname}: {record.getMessage()}")


logging.getLogger("django").addHandler(Logged())


def warned(message, category, filename, lineno, file=None, line=None):
    note(f"warning ({category.__name__}): {message}")


warnings.simplefilter("always")
warnings.showwarning = warned

# ---------------------------------------------------------------------------------------------
# The views.

HERE = tempfile.mkdtemp()
REPORT = os.path.join(HERE, "report.txt")
with open(REPORT, "wb") as f:
    f.write(b"0123456789" * 1000)
TEMPORARY = []  # where the last upload's temporary files are


def order(request):
    with reading("request.method, request.path, request.content_type and request.encoding"):
        note(f"-> {request.method!r}, {request.path!r}, {request.content_type!r}, {request.encoding!r}")
    with reading("request.GET"):
        value = request.GET
        note(f"-> {value!r}")
    with reading("request.GET again"):
        request.GET
    with reading("request.COOKIES"):
        request.COOKIES
    with reading("request.headers"):
        value = request.headers
        note(f"-> {dict(value)!r}")
    with reading("request.POST"):
        value = request.POST
        note(f"-> {value!r}")
    with reading("request.FILES"):
        value = request.FILES
        note(f"-> {value!r}")
    with reading("request.body"):
        request.body
    with reading("request.get_host()", "the view calls"):
        request.get_host()
    return HttpResponse("ok")


def upload(request):
    with reading("request.POST"):
        posted = request.POST
        note(f"-> {posted!r}")
    with reading("request.FILES"):
        files = request.FILES
        for name, uploaded in files.lists():
            for one in uploaded:
                where = "a temporary file on disk" if hasattr(one, "temporary_file_path") else "in memory"
                note(f'FILES["{name}"] is a {type(one).__name__}, name {one.name!r}, size {one.size}, {where}')
                if hasattr(one, "temporary_file_path"):
                    TEMPORARY.append(one.temporary_file_path())
    return HttpResponse("ok")


def posted(request):
    request.POST
    return HttpResponse("ok")


def queried(request):
    request.GET
    return HttpResponse("ok")


def hosted(request):
    request.get_host()
    return HttpResponse("ok")


def page(request):
    with reading('HttpResponse("<h1>Thanks</h1>")', "the view makes"):
        response = HttpResponse("<h1>Thanks</h1>")
    with reading('response["X-Order"] = 1042', "the view sets"):
        response["X-Order"] = 1042
    with reading('response.set_cookie("basket", "empty", max_age=3600, httponly=True)', "the view calls"):
        response.set_cookie("basket", "empty", max_age=3600, httponly=True)
    with reading('response.write("<p>Order 1042</p>")', "the view calls"):
        response.write("<p>Order 1042</p>")
    return response


def stream(request):
    def parts():
        try:
            for number in (1, 2, 3):
                note(f"the generator produces part {number}")
                yield f"part {number}\n"
            note("the generator has no more parts")
        except GeneratorExit:
            note("the generator is closed where it stood, after a part and before the next")
            raise

    with reading("StreamingHttpResponse(parts())", "the view makes"):
        response = StreamingHttpResponse(parts())
    return response


def download(request):
    with reading('FileResponse(open(".../report.txt", "rb"), as_attachment=True)', "the view makes"):
        response = FileResponse(open(REPORT, "rb"), as_attachment=True)
    return response


def large(request):
    return HttpResponse(b"x" * 150000)


async def async_stream(request):
    async def parts():
        try:
            for number in (1, 2, 3):
                await asyncio.sleep(0.01)  # a real wait, as for the data of the next part
                note(f"the async generator produces part {number}")
                yield f"part {number}\n"
        except asyncio.CancelledError:
            note("the async generator, waiting for its next part, is stopped by CancelledError")
            raise

    return StreamingHttpResponse(parts())


urlpatterns = [
    path("orders/", order), path("upload/", upload), path("posted/", posted), path("queried/", queried),
    path("hosted/", hosted), path("page/", page), path("stream/", stream), path("download/", download),
    path("large/", large), path("async-stream/", async_stream),
]

# ---------------------------------------------------------------------------------------------
# The server's part.

BOUNDARY = "recording-boundary"
MULTIPART = f"multipart/form-data; boundary={BOUNDARY}"
FORM = "application/x-www-form-urlencoded"


def multipart(*parts) -> bytes:
    """A multipart body. A part is (name, value) for a field, or (name, file name, content
    type, content) for a file."""
    out = []
    for part in parts:
        out.append(f"--{BOUNDARY}".encode())
        if len(part) == 2:
            out += [f'Content-Disposition: form-data; name="{part[0]}"'.encode(), b"", part[1]]
        else:
            out += [f'Content-Disposition: form-data; name="{part[0]}"; filename="{part[1]}"'.encode(),
                    f"Content-Type: {part[2]}".encode(), b"", part[3]]
    out += [f"--{BOUNDARY}--".encode(), b""]
    return b"\r\n".join(out)


def environ(method: str, url: str, body: bytes = b"", content_type: str = "", **more) -> dict:
    path_info, _, query = url.partition("?")
    made = {
        "REQUEST_METHOD": method, "PATH_INFO": path_info, "QUERY_STRING": query, "SCRIPT_NAME": "",
        "SERVER_NAME": "shop.example", "SERVER_PORT": "80", "SERVER_PROTOCOL": "HTTP/1.1",
        "HTTP_HOST": "shop.example", "wsgi.url_scheme": "http", "wsgi.input": io.BytesIO(body),
    }
    if body or method == "POST":
        made["CONTENT_LENGTH"] = str(len(body))
    if content_type:
        made["CONTENT_TYPE"] = content_type
    made.update(more)
    return made


def serve(handler, env: dict, title: str, rules: dict, *, stop_after: int = 0, files: bool = False) -> None:
    """Call the handler as a WSGI server does: start the response, send the body, close it."""
    global RULES
    RULES = {**COMMON, **rules}
    TEMPORARY.clear()

    def start_response(status, headers):
        if rules is not RESPONSE:
            note(f'start_response("{status}", headers)')
            return
        note(f'start_response("{status}", headers), the headers being:')
        for name, value in headers:
            note(f"  {name}: {value}")

    sys.setprofile(profile)
    result = handler(env, start_response)
    if hasattr(result, "status_code"):
        note("the handler has returned the response; the server iterates it")
    else:
        note(f"the handler has returned a {type(result).__name__}, the server's own wrapper around the file; the server iterates it")
    sent = 0
    for piece in result:
        sent += 1
        note(f"the server sends {len(piece)} bytes")
        if sent == stop_after:
            note("the client goes away; the server stops iterating")
            break
    if files and TEMPORARY:
        note(f"the uploaded files' temporary files exist: {[os.path.exists(p) for p in TEMPORARY]}")
    note("the server calls close() on what it was given")
    result.close()
    sys.setprofile(None)
    if files and TEMPORARY:
        note(f"the uploaded files' temporary files exist: {[os.path.exists(p) for p in TEMPORARY]}")
    show(title)


class ServerFileWrapper:
    """What a server puts in the environ as wsgi.file_wrapper: wsgiref's is like it."""

    def __init__(self, filelike, block_size=8192):
        note(f"the server's file wrapper is made around the file, block size {block_size}")
        self.filelike, self.block_size = filelike, block_size

    def __iter__(self):
        return iter(lambda: self.filelike.read(self.block_size), b"")

    def close(self):
        with reading("the file's close, which the handler replaced with the response's", "the wrapper calls"):
            self.filelike.close()


def asgi(handler, url: str, title: str, *, leave_after: int = 0) -> None:
    """Call the handler as an ASGI server does, and write down each message it is sent. With
    leave_after, the client disconnects once that many messages of the body have been sent."""
    async def run():
        waiting = [{"type": "http.request", "body": b"", "more_body": False}]
        gone = asyncio.Event()
        sent = 0

        async def receive():
            if waiting:
                return waiting.pop(0)
            await gone.wait()
            note("receive: http.disconnect")
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                note(f'send: http.response.start, status {message["status"]}, headers:')
                for name, value in message["headers"]:
                    note(f"  {name.decode()}: {value.decode()}")
            else:
                said = [f"{len(message['body'])} bytes" if "body" in message else "no body"]
                if "more_body" in message:
                    said.append(f"more_body {message['more_body']}")
                note("send: http.response.body, " + ", ".join(said))
                nonlocal sent
                sent += 1
                if sent == leave_after:
                    gone.set()

        scope = {"type": "http", "method": "GET", "path": url, "query_string": b"", "scheme": "http",
                 "server": ("shop.example", 80), "headers": [(b"host", b"shop.example")]}
        await handler(scope, receive, send)

    asyncio.run(run())
    show(title)


def attempt(what: str, do, brief: bool = False) -> None:
    """One question and its answer, on one line. A brief answer names an exception and leaves
    out its message."""
    try:
        said = do()
    except Exception as raised:
        said = f"raises {type(raised).__name__}" + ("" if brief else f": {raised}")
    note(f"{what}  ->  {said}")


print("Django", django.get_version(), "with no middleware, and ALLOWED_HOSTS = ['shop.example']\n")

wsgi_handler = WSGIHandler()

# ---------------------------------------------------------------------------------------------
# Making the request, and the first read of each part of it.

serve(wsgi_handler, environ("POST", "/orders/?page=2&tag=new&tag=sale", b"customer=Ada&item=3&item=7", FORM,
                            HTTP_COOKIE="theme=dark; basket=3", HTTP_ACCEPT_LANGUAGE="en"),
      "A form is posted: what making the request does, and what each first read does", REQUEST)

RULES = {**COMMON, **REQUEST}
sys.setprofile(profile)
with reading('made, for a request line of "POST /orders/?q=caf%E9" and a Content-Type of "text/plain; charset=iso-8859-1"',
             "a WSGIRequest is"):
    made = WSGIRequest(environ("POST", "/orders/?q=caf%E9", b"", "text/plain; charset=iso-8859-1"))
sys.setprofile(None)
note(f"request.encoding is {made.encoding!r}, and request.GET is {made.GET!r}")
show("A Content-Type with a charset sets the request's encoding as the request is made")

AS_PASSED = "/caf\xc3\xa9/"  # the UTF-8 bytes of the path, decoded as ISO-8859-1: what a WSGI server passes
request = WSGIRequest(env := environ("GET", AS_PASSED, SCRIPT_NAME="/shop", HTTP_X_TOKEN="abc", CONTENT_TYPE="text/plain"))
note(f"the environ: SCRIPT_NAME {env['SCRIPT_NAME']!r}, and PATH_INFO as a WSGI server passes it, {AS_PASSED!a}")
note(f"request.META is environ: {request.META is env}")
note(f"request.path_info: {request.path_info!r}")
note(f"request.path: {request.path!r}")
note(f'request.META["PATH_INFO"]: {request.META["PATH_INFO"]!r}')
note(f"request.headers: {dict(request.headers)!r}")
note(f'request.headers["x_token"]: {request.headers["x_token"]!r}')
show("WSGI: the environ is META, and the path is decoded again")

SCOPE_HEADERS = [(b"host", b"shop.example"), (b"accept", b"text/html"), (b"accept", b"application/json"),
                 (b"cookie", b"theme=dark"), (b"cookie", b"basket=3"), (b"x_token", b"spoofed"),
                 (b"x-token", b"abc"), (b"content-type", b"text/plain"), (b"content-length", b"0")]
request = ASGIRequest({
    "type": "http", "method": "get", "path": "/shop/café/", "root_path": "/shop", "query_string": b"page=2",
    "scheme": "https", "client": ("203.0.113.9", 51234), "server": ("shop.example", 443), "headers": SCOPE_HEADERS,
}, io.BytesIO())
note("the scope's headers, in the order sent:")
for name, value in SCOPE_HEADERS:
    note(f"  {name.decode()}: {value.decode()}")
note(f"request.method: {request.method!r}")
note(f"request.path: {request.path!r}")
note(f"request.path_info: {request.path_info!r}")
note(f"request.scheme: {request.scheme!r}")
for key, value in request.META.items():
    note(f"META[{key!r}]: {value!r}")
show("ASGI: META is built from the scope")

# ---------------------------------------------------------------------------------------------
# The body can be read once.


def fresh(content_type: str, body: bytes):
    return WSGIRequest(environ("POST", "/orders/", body, content_type))


URLENCODED = b"customer=Ada&item=3"
PARTS = multipart(("customer", b"Ada"))


def then(request, *steps):
    said = None
    for step in steps:
        said = step(request)
    return said


def read_post(request):
    return f"POST is {dict(request.POST.lists())!r}"


def read_body(request):
    return f"body is {len(request.body)} bytes"


def read_stream(request):
    return f"read() returns {len(request.read())} bytes"


def read_twice(request):
    return f"read() returns {len(request.read())} bytes, and then {len(request.read())}"


def set_encoding(request):
    request.encoding = "utf-8"


def read_some(request):
    return f"read(8) returns {request.read(8)!r}"


for label, content_type, body in (("a form (application/x-www-form-urlencoded)", FORM, URLENCODED),
                                  ("a multipart form (multipart/form-data)", MULTIPART, PARTS)):
    note(f"{label}, {len(body)} bytes")
    STACK.append(None)
    attempt("request.body, then request.POST", lambda: then(fresh(content_type, body), read_body, read_post))
    attempt("request.body, then request.read()", lambda: then(fresh(content_type, body), read_body, read_stream))
    attempt("request.body, then request.read() twice", lambda: then(fresh(content_type, body), read_body, read_twice))
    attempt("request.POST, then request.body", lambda: then(fresh(content_type, body), read_post, read_body))
    attempt("request.POST, then request.read()", lambda: then(fresh(content_type, body), read_post, read_stream))
    attempt("request.read(8), then request.body", lambda: then(fresh(content_type, body), read_some, read_body))
    attempt("request.read(8), then request.POST", lambda: then(fresh(content_type, body), read_some, read_post))
    attempt('request.POST, then request.encoding = "utf-8", then request.POST',
            lambda: then(fresh(content_type, body), read_post, set_encoding, read_post))
    STACK.pop()
show("The body's stream is read once: what can follow what")

# ---------------------------------------------------------------------------------------------
# Uploads.

NOTES = ("notes", "notes.txt", "text/plain", b"Leave it with the neighbour.\n")
SMALL = multipart(("customer", b"Ada"), NOTES)
LARGE = multipart(("customer", b"Ada"), NOTES, ("scan", "../scans/receipt.bin", "application/octet-stream", bytes(3_000_000)))
LIMIT = settings.FILE_UPLOAD_MAX_MEMORY_SIZE
serve(wsgi_handler, environ("POST", "/upload/", SMALL, MULTIPART),
      f"A multipart form with a small file: the body, {len(SMALL)} bytes, is under FILE_UPLOAD_MAX_MEMORY_SIZE ({LIMIT})", REQUEST,
      files=True)
serve(wsgi_handler, environ("POST", "/upload/", LARGE, MULTIPART),
      f"The same form with a second file of 3,000,000 bytes: the body, {len(LARGE)} bytes, is over FILE_UPLOAD_MAX_MEMORY_SIZE ({LIMIT})",
      REQUEST, files=True)


def parsed(what: str, body: bytes) -> None:
    def read():
        request = fresh(MULTIPART, body)
        files = {name: [f"{type(f).__name__}, {f.size} bytes" for f in found] for name, found in request.FILES.lists()}
        return f"POST is {dict(request.POST.lists())!r}, FILES is {files!r}"
    attempt(what, read)


CUT = SMALL[:SMALL.index(b"Leave it") + 8]
parsed(f"the small form above, cut off after {len(CUT)} of its {len(SMALL)} bytes, inside the file", CUT)
parsed('a form whose one part is a file input left empty: name="photo"; filename=""',
       multipart(("photo", "", "application/octet-stream", b"")))
show("Two multipart forms that are not what they seem")

# ---------------------------------------------------------------------------------------------
# The limits, and what the client gets.


def refused(what: str, env: dict) -> None:
    status = []
    note(what)
    STACK.append(None)
    RAISED.clear()
    sys.setprofile(profile)
    try:
        result = wsgi_handler(env, lambda s, h: status.append(s))
    except Exception as raised:
        sys.setprofile(None)
        flush()
        STACK.clear()
        note(f"  the handler raises {type(raised).__name__} to the server, and has made no response")
        return
    b"".join(result)
    result.close()
    sys.setprofile(None)
    flush()
    STACK.clear()
    note(f"  the client gets {status[0]}")


RULES = LIMITS
refused("a query string of 1001 parameters; the view reads request.GET",
        environ("GET", "/queried/?" + "&".join(f"f{n}=1" for n in range(1001))))
refused("a form of 1001 fields; the view reads request.POST",
        environ("POST", "/posted/", "&".join(f"f{n}=1" for n in range(1001)).encode(), FORM))
TOO_BIG = b"a=" + b"x" * (settings.DATA_UPLOAD_MAX_MEMORY_SIZE - 1)
refused(f"a form of {len(TOO_BIG)} bytes; the view reads request.POST", environ("POST", "/posted/", TOO_BIG, FORM))
refused("a multipart form with one field of 3,000,000 bytes and no file; the view reads request.POST",
        environ("POST", "/posted/", multipart(("essay", b"x" * 3_000_000)), MULTIPART))
refused("a multipart form with 101 files; the view reads request.POST",
        environ("POST", "/posted/", multipart(*((f"f{n}", f"{n}.txt", "text/plain", b"x") for n in range(101))), MULTIPART))
refused("a multipart form whose Content-Type names no boundary; the view reads request.POST",
        environ("POST", "/posted/", PARTS, "multipart/form-data"))
refused('a form whose Content-Type is "application/x-www-form-urlencoded; charset=iso-8859-1"; the view reads request.POST',
        environ("POST", "/posted/", URLENCODED, FORM + "; charset=iso-8859-1"))
refused('a request whose Host header is "evil.example"; the view calls request.get_host()',
        environ("GET", "/hosted/", HTTP_HOST="evil.example"))
TOO_LONG = "text/plain; a=" + "x" * 10000
refused(f"a request whose Content-Type header is {len(TOO_LONG):,} characters long; no view is reached",
        environ("POST", "/posted/", URLENCODED, TOO_LONG))
show("What is refused, by which exception, and what the client gets")

# ---------------------------------------------------------------------------------------------
# A response leaves, under WSGI.

serve(wsgi_handler, environ("GET", "/page/"), "A response under WSGI, from its constructor to the server's close()", RESPONSE)
serve(wsgi_handler, environ("GET", "/stream/"), "A streaming response under WSGI: the body is produced as the server asks for it",
      RESPONSE)
serve(wsgi_handler, environ("GET", "/stream/"), "A streaming response under WSGI, and the client goes away after the first part",
      RESPONSE, stop_after=1)
serve(wsgi_handler, environ("GET", "/download/"), "A FileResponse under WSGI, to a server that offers no file wrapper", RESPONSE)
env = environ("GET", "/download/")
env["wsgi.file_wrapper"] = ServerFileWrapper
serve(wsgi_handler, env, "A FileResponse under WSGI, to a server that offers wsgi.file_wrapper", RESPONSE)

# ---------------------------------------------------------------------------------------------
# A response leaves, under ASGI: what the server is sent.

asgi_handler = ASGIHandler()
asgi(asgi_handler, "/page/", "ASGI: an HttpResponse is two messages")
asgi(asgi_handler, "/large/", "ASGI: a body of 150,000 bytes goes in pieces of at most 65,536")
asgi(asgi_handler, "/async-stream/", "ASGI: a streaming response over an asynchronous iterator")
asgi(asgi_handler, "/stream/", "ASGI: a streaming response over a synchronous iterator")
finished = lambda **kwargs: note("signal request_finished")  # noqa: E731
signals.request_finished.connect(finished)
asgi(asgi_handler, "/async-stream/", "ASGI: a streaming response, and the client goes away after the first part", leave_after=1)
signals.request_finished.disconnect(finished)
asgi(asgi_handler, "/download/", "ASGI: a FileResponse of 10,000 bytes")


def asgi_form(what: str, body: bytes, *headers) -> None:
    """Make an ASGIRequest as the handler does, around a body already received, and read it."""
    def read():
        request = ASGIRequest({"type": "http", "method": "POST", "path": "/upload/", "query_string": b"",
                               "headers": [(b"content-type", MULTIPART.encode()), *headers]}, io.BytesIO(body))
        files = {name: [f"{type(f).__name__}, {f.size} bytes" for f in found] for name, found in request.FILES.lists()}
        return f"POST is {dict(request.POST.lists())!r}, FILES is {files!r}"
    attempt(what, read)


FORM_WITH_FILE = multipart(("customer", b"Ada"), NOTES)
SIZE = len(FORM_WITH_FILE)
asgi_form(f"with Content-Length: {SIZE}, which is the body's length", FORM_WITH_FILE, (b"content-length", str(SIZE).encode()))
asgi_form("with Content-Length: 5", FORM_WITH_FILE, (b"content-length", b"5"))
asgi_form("with no Content-Length header", FORM_WITH_FILE)
show(f"ASGI: the multipart form of {SIZE} bytes again, and what its Content-Length header says")

# ---------------------------------------------------------------------------------------------
# Small questions, each put to a running Django.

q = QueryDict("tag=new&tag=sale&page=2&empty=")
note('q = QueryDict("tag=new&tag=sale&page=2&empty=")')
attempt('q["tag"]', lambda: repr(q["tag"]))
attempt('q.getlist("tag")', lambda: repr(q.getlist("tag")))
attempt('q["empty"]', lambda: repr(q["empty"]))
attempt('q.get("missing")', lambda: repr(q.get("missing")))
attempt('q["missing"]', lambda: repr(q["missing"]))
attempt("dict(q.items())", lambda: repr(dict(q.items())))
attempt("dict(q.lists())", lambda: repr(dict(q.lists())))
attempt("q.dict()", lambda: repr(q.dict()))
attempt('q["page"] = "3"', lambda: q.__setitem__("page", "3"))
c = q.copy()
c["page"] = "3"
c.appendlist("tag", "last")
note('c = q.copy(); c["page"] = "3"; c.appendlist("tag", "last")')
attempt("c.urlencode()", lambda: repr(c.urlencode()))
attempt("q.urlencode()", lambda: repr(q.urlencode()))


def united():
    frozen = QueryDict("page=2")
    frozen |= {"extra": ["1"]}
    return f"{frozen!r}, and its _mutable is still {frozen._mutable}"


attempt('frozen = QueryDict("page=2"); frozen |= {"extra": ["1"]}', united)
attempt('QueryDict("next=/a%26b/").urlencode()', lambda: repr(QueryDict("next=/a%26b/").urlencode()))
attempt('QueryDict("next=/a%26b/").urlencode(safe="/")', lambda: repr(QueryDict("next=/a%26b/").urlencode(safe="/")))
attempt('QueryDict(b"name=caf\\xe9")  (bytes that are not UTF-8)', lambda: repr(QueryDict(b"name=caf\xe9")))
attempt('QueryDict("name=caf%E9")  (an escape that is not UTF-8)', lambda: repr(QueryDict("name=caf%E9")))
attempt('QueryDict("name=caf%E9", encoding="iso-8859-1")', lambda: repr(QueryDict("name=caf%E9", encoding="iso-8859-1")))
show("QueryDict: one key, several values, and no changing it")


def negotiating(accept: str):
    return WSGIRequest(environ("GET", "/", HTTP_ACCEPT=accept))


request = negotiating("text/html;q=0.8, application/json, text/*;q=0.9, */*;q=0.1")
note("Accept: text/html;q=0.8, application/json, text/*;q=0.9, */*;q=0.1")
STACK.append(None)
attempt("request.accepted_types", lambda: ", ".join(str(t) for t in request.accepted_types))
attempt("request.accepted_types_by_precedence", lambda: ", ".join(str(t) for t in request.accepted_types_by_precedence))
attempt('request.accepted_type("text/html")', lambda: str(request.accepted_type("text/html")))
attempt('request.accepted_type("text/plain")', lambda: str(request.accepted_type("text/plain")))
attempt('request.get_preferred_type(["text/html", "application/json"])', lambda: repr(request.get_preferred_type(["text/html", "application/json"])))
attempt('request.get_preferred_type(["text/html", "text/plain"])', lambda: repr(request.get_preferred_type(["text/html", "text/plain"])))
attempt('request.accepts("image/png")', lambda: repr(request.accepts("image/png")))
STACK.pop()
request = negotiating("text/html, image/png;q=0")
note("Accept: text/html, image/png;q=0")
STACK.append(None)
attempt("request.accepted_types", lambda: ", ".join(str(t) for t in request.accepted_types))
attempt('request.accepts("image/png")', lambda: repr(request.accepts("image/png")))
STACK.pop()
request = WSGIRequest(environ("GET", "/"))
note("no Accept header")
STACK.append(None)
attempt("request.accepted_types", lambda: ", ".join(str(t) for t in request.accepted_types))
STACK.pop()
show("The Accept header: preference and precedence")


def asked(ask, what: str, env: dict, **changed) -> None:
    """One question of a request made from this environ, under these settings."""
    saved = {name: getattr(settings, name) for name in changed}
    for name, value in changed.items():
        setattr(settings, name, value)
    try:
        request = WSGIRequest(env)
        attempt(what, lambda: repr(ask(request)), brief=True)
    finally:
        for name, value in saved.items():
            setattr(settings, name, value)


def host(what: str, env: dict, **changed) -> None:
    asked(lambda request: request.get_host(), what, env, **changed)


def scheme(what: str, env: dict, **changed) -> None:
    asked(lambda request: request.scheme, what, env, **changed)


def without(env: dict, key: str) -> dict:
    return {k: v for k, v in env.items() if k != key}


note("request.get_host(), with ALLOWED_HOSTS = ['shop.example'] unless the line says otherwise")
STACK.append(None)
host("Host: shop.example", environ("GET", "/"))
host("Host: SHOP.example:8000", environ("GET", "/", HTTP_HOST="SHOP.example:8000"))
host("Host: shop.example.  (a trailing dot)", environ("GET", "/", HTTP_HOST="shop.example."))
host("Host: www.shop.example", environ("GET", "/", HTTP_HOST="www.shop.example"))
host("Host: www.shop.example, and ALLOWED_HOSTS = ['.shop.example']", environ("GET", "/", HTTP_HOST="www.shop.example"),
     ALLOWED_HOSTS=[".shop.example"])
host("Host: shop.example/x  (not a host name)", environ("GET", "/", HTTP_HOST="shop.example/x"))
host("no Host header; SERVER_NAME shop.example, SERVER_PORT 80", without(environ("GET", "/"), "HTTP_HOST"))
host("no Host header; SERVER_NAME shop.example, SERVER_PORT 8000", without(environ("GET", "/", SERVER_PORT="8000"), "HTTP_HOST"))
host("Host: shop.example, X-Forwarded-Host: evil.example", environ("GET", "/", HTTP_X_FORWARDED_HOST="evil.example"))
host("the same, and USE_X_FORWARDED_HOST = True", environ("GET", "/", HTTP_X_FORWARDED_HOST="evil.example"),
     USE_X_FORWARDED_HOST=True)
host("Host: evil.example, and ALLOWED_HOSTS = ['*']", environ("GET", "/", HTTP_HOST="evil.example"), ALLOWED_HOSTS=["*"])
host("Host: evil.example, and ALLOWED_HOSTS = [], DEBUG = False", environ("GET", "/", HTTP_HOST="evil.example"), ALLOWED_HOSTS=[])
host("Host: evil.example, and ALLOWED_HOSTS = [], DEBUG = True", environ("GET", "/", HTTP_HOST="evil.example"),
     DEBUG=True, ALLOWED_HOSTS=[])
host("Host: app.localhost:8000, and ALLOWED_HOSTS = [], DEBUG = True", environ("GET", "/", HTTP_HOST="app.localhost:8000"),
     DEBUG=True, ALLOWED_HOSTS=[])
STACK.pop()
PROXY = {"SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https")}
HTTPS = {"wsgi.url_scheme": "https"}
note("request.scheme")
STACK.append(None)
scheme("the server says http", environ("GET", "/"))
scheme("the server says http, X-Forwarded-Proto: https", environ("GET", "/", HTTP_X_FORWARDED_PROTO="https"))
scheme('the same, and SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")',
       environ("GET", "/", HTTP_X_FORWARDED_PROTO="https"), **PROXY)
scheme("that setting, X-Forwarded-Proto: https, http  (a list)", environ("GET", "/", HTTP_X_FORWARDED_PROTO="https, http"), **PROXY)
scheme("that setting, the server says https, no such header", environ("GET", "/", **HTTPS), **PROXY)
scheme("that setting, the server says https, X-Forwarded-Proto: http", environ("GET", "/", HTTP_X_FORWARDED_PROTO="http", **HTTPS),
       **PROXY)
STACK.pop()
request = WSGIRequest(environ("GET", "/orders/2026/?page=2"))
note("request.build_absolute_uri, of a request for http://shop.example/orders/2026/?page=2")
STACK.append(None)
attempt("build_absolute_uri()", lambda: repr(request.build_absolute_uri()))
attempt('build_absolute_uri("/pay/")', lambda: repr(request.build_absolute_uri("/pay/")))
attempt('build_absolute_uri("pay/?step=1")', lambda: repr(request.build_absolute_uri("pay/?step=1")))
attempt('build_absolute_uri("../2025/")', lambda: repr(request.build_absolute_uri("../2025/")))
attempt('build_absolute_uri("//cdn.example/logo.png")', lambda: repr(request.build_absolute_uri("//cdn.example/logo.png")))
attempt('build_absolute_uri("https://bank.example/pay/?to=é")', lambda: repr(request.build_absolute_uri("https://bank.example/pay/?to=é")))
attempt("get_full_path()", lambda: repr(request.get_full_path()))
STACK.pop()
show("The host and the scheme: what is believed")


def made_response(what: str, make) -> None:
    def describe():
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                response = make()
            except Exception as raised:
                said = f"raises {type(raised).__name__}: {raised}"
            else:
                headers = ", ".join(f"{name}: {value}" for name, value in response.items())
                said = f"{response.status_code} {response.reason_phrase}; headers: {headers or 'none'}" + (f"; body {response.content!r}" if response.content else "")
        return said + "".join(f"; warns {type(w.message).__name__}: {w.message}" for w in caught)
    attempt(what, describe)


made_response('HttpResponse("café")', lambda: HttpResponse("café"))
made_response('HttpResponse("café", content_type="text/plain; charset=iso-8859-1")',
              lambda: HttpResponse("café", content_type="text/plain; charset=iso-8859-1"))
made_response('HttpResponse(iter(["a", b"b", 3]))', lambda: HttpResponse(iter(["a", b"b", 3])))
made_response("HttpResponse(status=204)", lambda: HttpResponse(status=204))
made_response("HttpResponse(status=299)", lambda: HttpResponse(status=299))
made_response("HttpResponse(status=600)", lambda: HttpResponse(status=600))
made_response('HttpResponseRedirect("/next/")', lambda: HttpResponseRedirect("/next/"))
made_response('HttpResponseRedirect("/next/", preserve_request=True)', lambda: HttpResponseRedirect("/next/", preserve_request=True))
made_response('HttpResponsePermanentRedirect("/café/?q=é")', lambda: HttpResponsePermanentRedirect("/café/?q=é"))
made_response('HttpResponsePermanentRedirect("/next/", preserve_request=True)',
              lambda: HttpResponsePermanentRedirect("/next/", preserve_request=True))
made_response('HttpResponseRedirect("javascript:alert(1)")', lambda: HttpResponseRedirect("javascript:alert(1)"))
made_response('HttpResponseRedirect("/" + "x" * 16384)', lambda: HttpResponseRedirect("/" + "x" * 16384))
made_response('HttpResponseNotAllowed(["GET", "HEAD"])', lambda: HttpResponseNotAllowed(["GET", "HEAD"]))
made_response("HttpResponseNotModified()", lambda: HttpResponseNotModified())
made_response('HttpResponseNotModified("body")', lambda: HttpResponseNotModified("body"))
made_response("JsonResponse([1, 2])", lambda: JsonResponse([1, 2]))
made_response('JsonResponse({"a": 1}, safe=False)', lambda: JsonResponse({"a": 1}, safe=False))
made_response("JsonResponse([1, 2], safe=True)", lambda: JsonResponse([1, 2], safe=True))
show("The response classes: what a constructor leaves")


def header(what: str, value) -> None:
    def describe():
        response = HttpResponse()
        response["X-Note"] = value
        return f"stored as {response['X-Note']!r}"
    attempt(what, describe)


header('response["X-Note"] = "plain"', "plain")
header('response["X-Note"] = 42', 42)
header('response["X-Note"] = "café"  (Latin-1 can hold it)', "café")
header('response["X-Note"] = "naïve ☕"  (Latin-1 cannot)', "naïve ☕")
header('response["X-Note"] = "one\\r\\nSet-Cookie: stolen=1"', "one\r\nSet-Cookie: stolen=1")
attempt('response["X-Nöte"] = "x"  (a name that is not ASCII)', lambda: HttpResponse().__setitem__("X-Nöte", "x"))
response = HttpResponse()
response["content-type"] = "text/plain"
attempt('response["content-type"] = "text/plain", then response.items()', lambda: repr(list(response.items())))
attempt('"CONTENT-TYPE" in response', lambda: repr("CONTENT-TYPE" in response))
attempt("HttpResponse(reason=\"Fine\\r\\nX: y\")", lambda: HttpResponse(reason="Fine\r\nX: y"))
show("Headers on a response: what is stored, and what is refused")


def cookies(response) -> None:
    for morsel in response.cookies.values():
        note(f"  Set-Cookie: {morsel.OutputString()}")


response = HttpResponse()
response.set_cookie("theme", "dark")
note('response.set_cookie("theme", "dark")')
cookies(response)
response = HttpResponse()
response.set_cookie("basket", "3", max_age=3600, secure=True, httponly=True, samesite="Lax")
note('response.set_cookie("basket", "3", max_age=3600, secure=True, httponly=True, samesite="Lax")')
cookies(response)
response = HttpResponse()
response.set_cookie("note", "a b; c")
note('response.set_cookie("note", "a b; c")')
cookies(response)
response = HttpResponse()
response.delete_cookie("basket")
note('response.delete_cookie("basket")')
cookies(response)
response = HttpResponse()
response.delete_cookie("__Host-basket")
note('response.delete_cookie("__Host-basket")')
cookies(response)
response = HttpResponse()
response.set_signed_cookie("basket", "3", salt="shop")
note('response.set_signed_cookie("basket", "3", salt="shop")')
cookies(response)
signed = response.cookies["basket"].value
note(f"the signer's salt for it: {signing._cookie_signer_salt('basket', 'shop')!r}")


def returning(name: str, value: str, **kwargs):
    return WSGIRequest(environ("GET", "/", HTTP_COOKIE=f"{name}={value}")).get_signed_cookie(name, **kwargs)


note("and when a request brings the cookie back:")
STACK.append(None)
attempt('request.get_signed_cookie("basket", salt="shop")', lambda: repr(returning("basket", signed, salt="shop")))
attempt('request.get_signed_cookie("basket")  (no salt)', lambda: repr(returning("basket", signed)), brief=True)
attempt('the same value sent back under the name "total"', lambda: repr(returning("total", signed, salt="shop")), brief=True)
attempt("the value changed from 3 to 9", lambda: repr(returning("basket", "9" + signed[1:], salt="shop")), brief=True)
attempt("the value changed, and default=None", lambda: repr(returning("basket", "9" + signed[1:], salt="shop", default=None)))
attempt('request.get_signed_cookie("absent"), of a request with no such cookie',
        lambda: repr(WSGIRequest(environ("GET", "/")).get_signed_cookie("absent")))
NOW += 7200
attempt("two hours later, with max_age=3600", lambda: repr(returning("basket", signed, salt="shop", max_age=3600)), brief=True)
attempt("two hours later, with no max_age", lambda: repr(returning("basket", signed, salt="shop")))
NOW -= 7200
STACK.pop()
COOKIE_HEADER = r'theme=dark; basket=3; flag; note="a b\073 c"'
attempt(f"parse_cookie, given the header  {COOKIE_HEADER}", lambda: repr(parse_cookie(COOKIE_HEADER)))
show("Cookies on a response, and cookies coming back")

from django.utils import http as helpers  # noqa: E402
from django.utils.datastructures import MultiValueDict  # noqa: E402

note("dates")
STACK.append(None)
attempt("http_date(1790000000)", lambda: repr(helpers.http_date(1790000000)))
attempt('parse_http_date("Mon, 21 Sep 2026 14:13:20 GMT")', lambda: repr(helpers.parse_http_date("Mon, 21 Sep 2026 14:13:20 GMT")))
attempt('parse_http_date("Monday, 21-Sep-26 14:13:20 GMT")', lambda: repr(helpers.parse_http_date("Monday, 21-Sep-26 14:13:20 GMT")))
attempt('parse_http_date("Mon Sep 21 14:13:20 2026")', lambda: repr(helpers.parse_http_date("Mon Sep 21 14:13:20 2026")))
attempt('parse_http_date("2026-09-21 14:13:20")', lambda: repr(helpers.parse_http_date("2026-09-21 14:13:20")), brief=True)
attempt('parse_http_date_safe("2026-09-21 14:13:20")', lambda: repr(helpers.parse_http_date_safe("2026-09-21 14:13:20")))
STACK.pop()
note("entity tags")
STACK.append(None)
attempt("quote_etag('abc')", lambda: repr(helpers.quote_etag("abc")))
attempt("quote_etag('W/\"abc\"')", lambda: repr(helpers.quote_etag('W/"abc"')))
attempt("parse_etags('\"abc\", W/\"def\", ghi')", lambda: repr(helpers.parse_etags('"abc", W/"def", ghi')))
attempt("parse_etags('*')", lambda: repr(helpers.parse_etags("*")))
STACK.pop()
note("header values")
STACK.append(None)
attempt("parse_header_parameters('Text/HTML; Charset=\"utf-8\"')", lambda: repr(helpers.parse_header_parameters('Text/HTML; Charset="utf-8"')))
attempt("parse_header_parameters(\"attachment; filename*=UTF-8''caf%C3%A9.txt\")",
        lambda: repr(helpers.parse_header_parameters("attachment; filename*=UTF-8''caf%C3%A9.txt")))
attempt("list(split_header_value('Accept-Encoding,  Cookie,'))", lambda: repr(list(helpers.split_header_value("Accept-Encoding,  Cookie,"))))
attempt("list(split_directive_names('max-age=60, Private=\"Set-Cookie\"'))",
        lambda: repr(list(helpers.split_directive_names('max-age=60, Private="Set-Cookie"'))))
attempt("content_disposition_header(True, 'report 2026.txt')", lambda: repr(helpers.content_disposition_header(True, "report 2026.txt")))
attempt("content_disposition_header(False, 'café \"menu\".txt')", lambda: repr(helpers.content_disposition_header(False, 'café "menu".txt')))
attempt("content_disposition_header(False, 'a \"b\".txt')", lambda: repr(helpers.content_disposition_header(False, 'a "b".txt')))
attempt("content_disposition_header(False, '')", lambda: repr(helpers.content_disposition_header(False, "")))
STACK.pop()
note("query strings")
STACK.append(None)
attempt("urlencode({'tag': ['new', 'sale'], 'page': 2}, doseq=True)", lambda: repr(helpers.urlencode({"tag": ["new", "sale"], "page": 2}, doseq=True)))
attempt("urlencode(MultiValueDict({'tag': ['new', 'sale']}), doseq=True)",
        lambda: repr(helpers.urlencode(MultiValueDict({"tag": ["new", "sale"]}), doseq=True)))
attempt("urlencode({'page': None})", lambda: repr(helpers.urlencode({"page": None})))
STACK.pop()
note("URLs that came from a client; allowed_hosts is {'shop.example'}")
STACK.append(None)
for url in ("/orders/", "https://shop.example/orders/", "https://evil.example/", "//evil.example/", "///evil.example/",
            "/\\evil.example/", "http:///evil.example/", "javascript:alert(1)", "ftp://shop.example/", ""):
    attempt(f"url_has_allowed_host_and_scheme({url!r}, allowed_hosts)",
            lambda: repr(helpers.url_has_allowed_host_and_scheme(url, {"shop.example"})))
for url in ("//shop.example/orders/", "https://SHOP.example/orders/", "https://shop.example:443/orders/"):
    attempt(f"url_has_allowed_host_and_scheme({url!r}, allowed_hosts)",
            lambda: repr(helpers.url_has_allowed_host_and_scheme(url, {"shop.example"})))
attempt("url_has_allowed_host_and_scheme('http://shop.example/', allowed_hosts, require_https=True)",
        lambda: repr(helpers.url_has_allowed_host_and_scheme("http://shop.example/", {"shop.example"}, require_https=True)))
attempt("escape_leading_slashes('//evil.example/')", lambda: repr(helpers.escape_leading_slashes("//evil.example/")))
attempt("is_same_domain('www.shop.example', '.shop.example')", lambda: repr(helpers.is_same_domain("www.shop.example", ".shop.example")))
attempt("is_same_domain('shop.example', '.shop.example')", lambda: repr(helpers.is_same_domain("shop.example", ".shop.example")))
attempt("is_same_domain('notshop.example', '.shop.example')", lambda: repr(helpers.is_same_domain("notshop.example", ".shop.example")))
STACK.pop()
note("compact encodings")
STACK.append(None)
attempt("int_to_base36(1790000000)", lambda: repr(helpers.int_to_base36(1790000000)))
attempt("base36_to_int('tlpwu8')", lambda: repr(helpers.base36_to_int("tlpwu8")))
attempt("base36_to_int('z' * 14)", lambda: repr(helpers.base36_to_int("z" * 14)))
attempt("urlsafe_base64_encode(bytes([251, 255, 254]))", lambda: repr(helpers.urlsafe_base64_encode(bytes([251, 255, 254]))))
attempt("urlsafe_base64_encode(b'42')", lambda: repr(helpers.urlsafe_base64_encode(b"42")))
attempt("urlsafe_base64_decode('NDI')", lambda: repr(helpers.urlsafe_base64_decode("NDI")))
STACK.pop()
show("The helpers of django/utils/http.py")

shutil.rmtree(HERE, ignore_errors=True)
