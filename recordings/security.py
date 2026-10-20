"""A recording of the security machinery: the four security middleware on a request, the CSRF
secret, its token and the check, the headers, the content security policy and its nonce,
signing and the key, and the security checks.

    PYTHONIOENCODING=utf-8 python recordings/security.py > recordings/security.txt

The chapter of the book (pages/security.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and
configures a project of its own in this one file. Run it again after a re-pin: where the
output changes, the chapter has to.

The site. The harbour office takes requests for berths at harbour.example. Its settings are
those the chapter's opening page shows: DEBUG = False; SECRET_KEY the harbour's key, 65
characters; ALLOWED_HOSTS = ["harbour.example"]; INSTALLED_APPS = []; MIDDLEWARE
SecurityMiddleware, CsrfViewMiddleware, XFrameOptionsMiddleware and
ContentSecurityPolicyMiddleware, in that order; SECURE_SSL_REDIRECT = True;
SECURE_HSTS_SECONDS = 3600; SECURE_CSP = {"default-src": [CSP.SELF], "script-src":
[CSP.SELF, CSP.NONCE]}; one template engine whose templates are held in memory, with the
context processor csp (a RequestContext runs the context processor csrf besides, always); and
ROOT_URLCONF = "__main__", this script. Every other setting is Django's default. The view
berths shows the form of office/berths.html on a GET (a {% csrf_token %} in the form, a <script
{% csp_nonce_attr %}> after it: the template asks for the token before the nonce, and so the
secret and the token are made and drawn before the nonce, an order Django does not set) and
answers "Berth requested." on a POST. The blocks that say so request the script's other views:
protected, under csrf_protect, which renders the same template; tides, under
xframe_options_exempt, which sets its own Content-Security-Policy, "default-src 'none'"; chart,
under xframe_options_sameorigin and a csp_override of its own; and notice, under
csp_override({}), which raises Http404 when it is given a number. The script has two keys,
named in its lines as HARBOUR_KEY and NEW_KEY and in words as "the harbour's key" and "the new
key"; neither is ever printed.

The server. The harbour's chain is one WSGIHandler, built once as the script starts, as a
server builds it. A block that needs other settings builds a handler of its own under them and
says so in its title; such a handler is not used after its block. The script calls a handler
as a WSGI server does, with an environ of its own making: the method, the path and the query
string; HTTP_HOST, SERVER_NAME and SERVER_PORT from the URL (443 or 80); "wsgi.url_scheme"
"https" for a URL that begins https://, so that the request is secure, and "http" otherwise;
"wsgi.input", the body; CONTENT_LENGTH for a request with a body or a method other than GET
and HEAD, and CONTENT_TYPE for one with a body ("application/x-www-form-urlencoded" for a form);
and the browser's headers. `start_response(...)` is the script's line for the call the handler
makes: "the headers being:" and every header, or else only the headers the block is about,
either way in the order it was given them, one to a line; then `no X` for each of those it was
not given. `the server sends the body` gives the body, or the lines of it that hold what the
block is about, stripped of their indentation, and `the handler raises X to the server` an
exception that left the handler.

The browser. Each block starts with a browser of the script's own that holds nothing. It
keeps each cookie a response sets, by name, and forgets one that a response expires (Max-Age=0);
it sends every cookie it holds, as Cookie, with each request to harbour.example. On a POST it
sends Origin: https://harbour.example, as a browser does for a form posted from the site's own
page, and no Referer. It fills the form from the last page it was given that holds one: the
hidden "csrfmiddlewaretoken" read out of the HTML, and ship=Endeavour. A line `METHOD URL, the
browser sending ...` says, before each request, every header and field it sends; a block whose
browser does otherwise (no cookie, no Origin, a foreign one, a Referer, a token in X-CSRFToken,
a cookie the script set) says so in its title. A line `beforehand, unrecorded, GET ...` is a
request made without writing anything down, and says what the browser was given and keeps.

The lines. Where the order of calls is the point, the lines are the calls a block watches,
nested as they were made; everything between them ran and is left out. A method is written by
the class that declares it, whatever the class of its object: `MiddlewareMixin.__call__(request),
on SecurityMiddleware` is that method called on that middleware, and "which has no
process_request" is the test the method makes, hasattr, answered for that object. The line of
words under BaseHandler._get_response says whose process_view the chain holds: that test was
made by BaseHandler.load_middleware, with hasattr, when it built the chain, and _get_response
calls only the hooks it kept. A method of CsrfViewMiddleware says `(the chain's)` or `(the
decorator's)` in the blocks about csrf_protect, and `(on an instance of _EnsureCsrfToken, the
class of requires_csrf_token)` where Django's error views, which carry that decorator, run it.
The context processor csp is written `csp(request), called by csrf_failure` where that view
calls it itself, outside any RequestContext. What a call returned follows `->`, put into words
at the moment it returned: a process_response hook by what it added to the response, a nonce by
whether it is drawn, get_token by its token and what request.META then holds. `raises X` names
an exception, once, at the innermost written-down call it left. A function behind
functools.cache (get_callable) or a cached_property (the three of CsrfViewMiddleware) is
written down only when its body runs: where a block that watches it does not show it, it was
either not asked for or answered from the cache. A line `log, LEVEL to logger: message` is a
record given to one of Django's loggers, where it was given; `signal got_request_exception` is
written by a receiver the script connects.

Many lines are a line of Python run from the text it prints: a statement on a line of its own,
with the calls it made nested under it (`do`), and under those, as `raises X: message`, the
exception that left the statement, if one did, though a call under it already named it; or a
question, `expression  ->  answer`, evaluated as written, with no calls under it (`ask`).
`Python warns:` under a question is a warning Python gave while it was answered, by its class
and message, and the line it is attributed to, in words. A setting is changed by such a line,
`changed = override_settings(...); changed.enable()`, and put back by `changed.disable()`. A
line of words says what the script does by its own hand: the clock moved, a cookie set, a page
gone back to.
In the blocks of the check command, `$ python manage.py check ...` is the command, run by
call_command with no_color, and `stdout |` and `stderr |` the lines it wrote to each stream;
the command sorts the messages of each level itself. `call_command raises X, its message
being:` is an exception that left call_command (run from manage.py, the command would write a
CommandError's message, such as a SystemCheckError's, to stderr and exit with status 1).

What was replaced, and why. The pages print secrets, tokens, nonces, signatures, signing times
and cookies' expiry dates, and two runs must give the same output byte for byte. So the module
`secrets` that django.utils.crypto and django.utils.csp draw from is replaced, in those two
modules, by an object whose choice and token_urlsafe draw from Python's random.Random, seeded
at the start of each block from the CRC-32 of the block's title, so that what one block draws
does not depend on the blocks before it; its compare_digest is Python's own. And time.time is
replaced by a clock that stands at 12 October 2026, 09:00:00 UTC: TimestampSigner.timestamp,
TimestampSigner.unsign (for a signature's age) and a cookie's expiry date read it. A block about
time moves the clock on by the script's hand and says so; each block starts at 09:00. With the
clock standing still, an age is a whole number of seconds; in a running site it carries the
fraction of a second that TimestampSigner.timestamp dropped when it signed.
datetime.datetime.now is not replaced; what reads it (a reset token's time, a session's expiry
date in the database, a user's last login) is never printed. Putting a call into words never
draws, under RECORD_EVERYTHING too: the script stops if it does.

The parts. The block of login, and each of the four blocks after a key change (a database
session's data, get_user over a session of the database backend and over one of the cache
backend, and a password-reset token), run in an interpreter of their own, one to a block (this
script, given the part's name), as their titles say: with django.contrib.auth, contenttypes and
sessions installed, an SQLite database in memory migrated as the interpreter starts, and one
user, harbourmaster, made then, whose unusable password is drawn from the generator, seeded
with 0, before any block seeds it (get_user's session hashes are made from that password);
sessions in the database, SessionMiddleware and AuthenticationMiddleware in the chain in their
documented places, and a login view of the script's own, log_in at /accounts/login/, which logs
in the user its form names. The four blocks after a key change send no request: the script
makes their sessions, requests and token by its own hand. Every other block runs in the first
interpreter, which installs no application, so that the security checks see the harbour's
settings.

    RECORD_EVERYTHING=1 python recordings/security.py     every call in the chapter's modules
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# This directory holds http.py, which has the name of a package of the standard library that
# Django imports: take the directory off the path before anything imports `http`. Nothing
# here is imported from it.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE]

import base64  # noqa: E402
import datetime  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import secrets  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
import zlib  # noqa: E402
from urllib.parse import urlencode, urlsplit  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = bool(os.environ.get("RECORD_EVERYTHING"))
PART = sys.argv[1] if len(sys.argv) > 1 else None  # an interpreter of its own, for one part

# ---------------------------------------------------------------------------------------------
# The clock and the random source: see the docstring.

NOW = 1791795600.0  # 12 October 2026, 09:00:00 UTC
CLOCK = [NOW]
time.time = lambda: CLOCK[0]


class Draws:
    """What django.utils.crypto and django.utils.csp draw from in place of the module secrets:
    the same three functions, the draws from a generator seeded at the start of each block."""

    compare_digest = staticmethod(secrets.compare_digest)  # compares, draws nothing

    def __init__(self):
        self.generator = random.Random(0)
        self.count = 0  # the draws made: the guard below compares it before and after a label

    def seed(self, words: str) -> None:
        self.generator.seed(zlib.crc32(words.encode()))

    def choice(self, sequence):
        self.count += 1
        return self.generator.choice(sequence)

    def token_urlsafe(self, nbytes: int) -> str:
        self.count += 1
        return base64.urlsafe_b64encode(self.generator.randbytes(nbytes)).rstrip(b"=").decode()


DRAWS = Draws()

# ---------------------------------------------------------------------------------------------
# The harbour office's site.

import django  # noqa: E402
from django.conf import settings  # noqa: E402
from django.utils.csp import CSP  # noqa: E402

HARBOUR_KEY = "harbour-office-k3y-for-the-security-chapter-0123456789-abcdefghij"
NEW_KEY = "harbour-office-new-k3y-for-the-security-chapter-9876543210-klmnop"

BERTHS_HTML = """<form method="post">
  {% csrf_token %}
  <input name="ship">
  <button>Request a berth</button>
</form>
<script {% csp_nonce_attr %}>document.forms[0].ship.focus()</script>
"""

HARBOUR_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]
HARBOUR_TEMPLATES = {"office/berths.html": BERTHS_HTML}


def templates(more: dict | None = None) -> list:
    return [{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            "loaders": [("django.template.loaders.locmem.Loader", {**HARBOUR_TEMPLATES, **(more or {})})],
            "context_processors": ["django.template.context_processors.csp"],
        },
    }]


HARBOUR = dict(
    DEBUG=False,
    SECRET_KEY=HARBOUR_KEY,
    ALLOWED_HOSTS=["harbour.example"],
    ROOT_URLCONF="__main__",
    INSTALLED_APPS=[],
    MIDDLEWARE=HARBOUR_MIDDLEWARE,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=3600,
    SECURE_CSP={
        "default-src": [CSP.SELF],
        "script-src": [CSP.SELF, CSP.NONCE],
    },
    TEMPLATES=templates(),
)

# The parts run in an interpreter of their own add the applications and the database that
# login, get_user and the sessions in the database need, and sessions and authentication to
# the chain in their documented places.
AUTH_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]
LOGIN_HTML = """<form method="post">
  {% csrf_token %}
  <input name="username">
  <button>Log in</button>
</form>
"""
if PART is None:
    settings.configure(**HARBOUR)
else:
    settings.configure(**{
        **HARBOUR,
        "INSTALLED_APPS": ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions"],
        "MIDDLEWARE": AUTH_MIDDLEWARE,
        "DATABASES": {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        "DEFAULT_AUTO_FIELD": "django.db.models.BigAutoField",
        "TEMPLATES": templates({"office/login.html": LOGIN_HTML}),
    })
django.setup()

import django.utils.crypto  # noqa: E402
import django.utils.csp  # noqa: E402

django.utils.crypto.secrets = DRAWS
django.utils.csp.secrets = DRAWS

from django.core import signing  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler, WSGIRequest  # noqa: E402
from django.http import Http404, HttpResponse, HttpResponseBase  # noqa: E402
from django.middleware.csrf import (  # noqa: E402
    CSRF_ALLOWED_CHARS, CsrfViewMiddleware, _get_new_csrf_string, _mask_cipher_secret, _unmask_cipher_token, get_token, rotate_token,
)
from django.contrib.messages import constants as message_constants  # noqa: E402
from django.contrib.messages.storage.cookie import CookieStorage  # noqa: E402
from django.middleware import MiddlewareMixin  # noqa: E402
from django.middleware.csp import ContentSecurityPolicyMiddleware  # noqa: E402
from django.middleware.security import SecurityMiddleware  # noqa: E402
from django.template import engines  # noqa: E402
from django.utils.crypto import salted_hmac  # noqa: E402
from django.shortcuts import render  # noqa: E402
from django.test.utils import override_settings  # noqa: E402  (django.test connects the receivers of setting_changed)
from django.urls import path  # noqa: E402
from django.utils.csp import LazyNonce, build_policy  # noqa: E402
from django.utils.functional import empty  # noqa: E402
from django.views.decorators.clickjacking import xframe_options_exempt, xframe_options_sameorigin  # noqa: E402
from django.views.decorators.csp import csp_override  # noqa: E402
from django.views.decorators.csrf import csrf_protect  # noqa: E402


def berths(request):
    if request.method == "POST":
        return HttpResponse("Berth requested.")
    return render(request, "office/berths.html")


@csrf_protect
def protected(request):
    return render(request, "office/berths.html")


@xframe_options_exempt
def tides(request):
    response = HttpResponse("Tide table.")
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


@xframe_options_sameorigin
@csp_override({"default-src": [CSP.SELF], "img-src": [CSP.SELF, "https://tiles.harbour.example"]})
def chart(request):
    return HttpResponse("The harbour chart.")


@csp_override({})
def notice(request, number=None):
    if number is not None:
        raise Http404("No such notice.")
    return HttpResponse("Notice to mariners.")


class RotatesOnTheWayOut(MiddlewareMixin):
    """A middleware of the script's own, installed only for the handler of the block that says
    so: it calls rotate_token in its process_response."""

    def process_response(self, request, response):
        rotate_token(request)
        return response


urlpatterns = [
    path("berths/", berths),
    path("protected/", protected),
    path("tides/", tides),
    path("chart/", chart),
    path("notice/", notice),
    path("notices/<int:number>/", notice),
]

if PART is not None:
    from django.contrib.auth import get_user_model, login  # noqa: E402
    from django.core.management import call_command  # noqa: E402

    def log_in(request):
        """The parts' login view: it logs in the user the form names, asking no password."""
        if request.method == "POST":
            login(request, get_user_model().objects.get(username=request.POST["username"]))
            return HttpResponse("Logged in.")
        return render(request, "office/login.html")

    urlpatterns.append(path("accounts/login/", log_in))
    call_command("migrate", verbosity=0)
    get_user_model().objects.create_user("harbourmaster")

# ---------------------------------------------------------------------------------------------
# The recorder.

LINES = []
STACK = []  # the watched frames open at this moment: the depth of the next line
AT = {}  # where in LINES the line of each open watched call is, by the frame
SEEN = {}  # generator frames already written down: such a frame is entered more than once
PENDING = []  # the watched call that has just returned: (frame, depth, its line, what is to be said of its value)
RAISED = []  # exceptions already written down, at the innermost watched call they left
RESUMABLE = 0x20 | 0x80 | 0x200  # a generator, a coroutine, an asynchronous generator


def flush() -> None:
    """Say what the call that has just returned gave back, if that is to be said: on the
    call's own line where nothing was written under it, and on a line of its own otherwise."""
    while PENDING:
        frame, depth, at, said = PENDING.pop(0)
        if said is not None:
            if at == len(LINES) - 1:
                LINES[at] += f"  ->  {said}"
            else:
                LINES.append("  " * depth + f"-> {said}")


def note(text: str) -> None:
    """A line, at the depth of the calls open now; a text of several lines is several lines,
    each at that depth, so that nothing but a title stands at the margin."""
    flush()
    for line in text.split("\n"):
        LINES.append("  " * len(STACK) + line)


def show(title: str) -> None:
    flush()
    print(title)
    for line in LINES:
        print("    " + line)
    print()
    LINES.clear()
    STACK.clear()
    AT.clear()
    SEEN.clear()
    RAISED.clear()


MADE_BY = {"_EnsureCsrfToken": "the class of requires_csrf_token", "_EnsureCsrfCookie": "the class of ensure_csrf_cookie"}
RULES = {}  # the set in force: (module, qualname) -> what to write of the call
INSTANCES = None  # the chain's middleware, where a block tells its instances of CsrfViewMiddleware from a decorator's
AFTER = {}  # (module, qualname) -> what to say of the value it returned
WATCHED = ("django.middleware", "django.utils.csp", "django.views.csrf", "django.views.decorators", "django.core.signing",
           "django.utils.crypto", "django.template.context_processors", "django.contrib.auth", "django.contrib.sessions",
           "django.contrib.messages", "django.core.handlers", "django.shortcuts", "django.utils.log")


def plain(frame) -> str:
    return frame.f_code.co_qualname


def find(module: str, qualname: str):
    label = RULES.get((module, qualname))
    if label is not None:
        return label
    if EVERYTHING and (module.startswith(WATCHED) or (module == "__main__" and qualname in VIEWS)):
        return plain
    return None


VIEWS = {"berths"}  # the script's own views, which RECORD_EVERYTHING writes down as Django's


def profile(frame, event, arg):
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), code.co_qualname)
        if label is None:
            return
        if code.co_flags & RESUMABLE:  # every resumption is a call event
            known = SEEN.get(id(frame))
            if known is not None and known is frame.f_generator:
                STACK.append(frame)
                return
            # By its generator, held until the block ends: a frame's address is used again once
            # its generator is gone. (A weak reference crashed this Python as the block ended.)
            SEEN[id(frame)] = frame.f_generator
        flush()  # what the call before this one returned is said first: a label may depend on it
        drawn = DRAWS.count
        try:
            text = label(frame)
        except Exception:  # a fault of this script's: Python would drop the hook and carry on, and the recording would be short
            import traceback
            traceback.print_exc()
            os._exit(1)
        under = []
        if isinstance(text, tuple):  # the call's line, and lines of words under it
            text, under = text
        instance = frame.f_locals.get("self")
        # issubclass(type()), never isinstance(): see said(). The object may be a lazy one.
        if text is not None and issubclass(type(instance), CsrfViewMiddleware):
            if INSTANCES is not None:
                text += f"  ({instance_of(frame)})"
            elif type(instance) is not CsrfViewMiddleware:
                text += f"  (on an instance of {type(instance).__name__}, {MADE_BY.get(type(instance).__name__, 'a subclass')})"
        guard(drawn, code)  # nothing from the label to here may have drawn
        if text is None:
            return
        note(text)
        AT[id(frame)] = len(LINES) - 1
        STACK.append(frame)
        for line in under:
            note(line)
    elif event == "return":
        if STACK and STACK[-1] is frame:
            flush()
            after = None if code.co_flags & RESUMABLE else AFTER.get((frame.f_globals.get("__name__", ""), code.co_qualname))
            # The value is put into words now, as it is returned.
            drawn = DRAWS.count
            try:
                words = after(frame, arg) if after else None
            except Exception:
                if arg is not None:  # a fault of this script's
                    import traceback
                    traceback.print_exc()
                    os._exit(1)
                words = None  # an exception is leaving the frame, and unwinding() is about to say so
            guard(drawn, code)
            PENDING.append((frame, len(STACK), AT.pop(id(frame), -1), words))
            STACK.pop()


def guard(drawn: int, code) -> None:
    """Putting a call into words must never draw from the random source: a nonce made by its
    description would be a nonce the recording says Django made."""
    if DRAWS.count != drawn:
        print(f"recordings/security.py: putting {code.co_qualname} into words drew from the random source", file=sys.stderr)
        os._exit(1)


def unwinding(code, offset, exception):
    """An exception is leaving a function. The profile hook has just been told that the
    function returned None: where it was a watched call, take that back, and say what was
    raised, once, at the innermost watched call the exception leaves."""
    frame = sys._getframe(1)
    if PENDING and PENDING[-1][0] is frame:
        _, depth, at, _ = PENDING.pop()
        if not any(e is exception for e in RAISED) and not isinstance(exception, (StopIteration, GeneratorExit)):
            RAISED.append(exception)
            if at == len(LINES) - 1:
                LINES[at] += f"  raises {type(exception).__name__}"
            else:
                LINES.append("  " * depth + f"raises {type(exception).__name__}")


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/security.py")
sys.monitoring.register_callback(MONITOR, sys.monitoring.events.PY_UNWIND, unwinding)
sys.monitoring.set_events(MONITOR, sys.monitoring.events.PY_UNWIND)


class recorded:
    """`with recorded(rules):` writes down, of what runs in the block, the calls those rules
    name, and says what the calls AFTER names returned."""

    def __init__(self, rules: dict):
        self.rules = rules

    def __enter__(self):
        global RULES
        self.before = RULES
        RULES = self.rules
        sys.setprofile(profile)

    def __exit__(self, *exc):
        global RULES
        sys.setprofile(None)
        flush()
        RULES = self.before


def _raises():
    raise KeyError("probe")


def self_test() -> None:
    """The line `raises X` depends on the profile hook being told of a return before
    sys.monitoring reports the unwinding. Prove it on this Python before anything is recorded."""
    with recorded({("__main__", "_raises"): lambda f: "_raises"}):
        try:
            _raises()
        except KeyError:
            pass
    if LINES != ["_raises  raises KeyError"]:
        raise SystemExit(f"recordings/security.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
    LINES.clear()
    RAISED.clear()


self_test()

# ---------------------------------------------------------------------------------------------
# How things are said. Nothing is written that differs between machines or runs.

KEYS = {HARBOUR_KEY: "the harbour's key", NEW_KEY: "the new key"}


def key_said(key) -> str:
    if isinstance(key, bytes) and key.startswith(b"django.http.cookies"):
        return KEYS.get(key[len(b"django.http.cookies"):].decode(), "a key of the script's") + ', with "django.http.cookies" in front'
    return KEYS.get(key, "a key of the script's")


def a(name: str) -> str:
    return ("an " if name[0] in "AEIOU" or name.startswith("Http") else "a ") + name


def said(value) -> str:
    """A value in words: a response by its class and status, a nonce by whether it is drawn.
    The class is read with type(), never isinstance(): isinstance() asks a lazy object for its
    __class__, which makes its value, and a nonce would be drawn by its description."""
    kind = type(value)
    if issubclass(kind, HttpResponseBase):
        return f"{a(kind.__name__)}, status {value.status_code}" + (
            f", Location {value['Location']!r}" if "Location" in value else "")
    if issubclass(kind, LazyNonce):
        return f"a LazyNonce, drawn: {str(value)!r}" if value else "a LazyNonce, not drawn"
    if kind.__name__ == "AnonymousUser":
        return "an AnonymousUser"
    if hasattr(value, "_meta") and hasattr(value, "get_username"):
        return f"the {kind.__name__} {value.get_username()!r}"
    text = repr(value)
    if " at 0x" in text:  # a repr that names a place in memory
        return a(kind.__name__)
    return text


def as_is(frame, value) -> str:
    return said(value)


def cls_of(frame) -> str:
    return type(frame.f_locals["self"]).__name__


def method_of(frame) -> str:
    """A call of a method by the class that declares it, with the arguments after self."""
    code = frame.f_code
    names = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]
    return f"{code.co_qualname}({', '.join(n for n in names if n not in ('self', 'cls'))})"


def meta_said(request) -> str:
    """What request.META holds of the CSRF secret at this moment."""
    if "CSRF_COOKIE" not in request.META:
        return "no CSRF_COOKIE"
    flag = request.META.get("CSRF_COOKIE_NEEDS_UPDATE")
    return f"CSRF_COOKIE {request.META['CSRF_COOKIE']!r}" + (
        f", CSRF_COOKIE_NEEDS_UPDATE {flag!r}" if "CSRF_COOKIE_NEEDS_UPDATE" in request.META else ", no CSRF_COOKIE_NEEDS_UPDATE")


HEADERS_AT = {}  # what a response held when a process_response hook was given it, by the frame


def hook_given(frame) -> str:
    response = frame.f_locals["response"]
    HEADERS_AT[id(frame)] = (dict(response.items()), {k: v.value for k, v in response.cookies.items()})
    return f"{frame.f_code.co_qualname}(request, response)"


def hook_returned(frame, value) -> str:
    """What a process_response hook did to the response: the headers it added or changed, and
    the cookies it set."""
    if id(frame) not in HEADERS_AT or not isinstance(value, HttpResponseBase):  # (RECORD_EVERYTHING labels a hook plainly)
        HEADERS_AT.pop(id(frame), None)
        return said(value)
    headers, cookies = HEADERS_AT.pop(id(frame))
    done = []
    for name, header in value.items():
        if name not in headers:
            done.append(f"{name} added")
        elif headers[name] != header:
            done.append(f"{name} changed to {header!r}")
    for name, cookie in value.cookies.items():
        if cookies.get(name) != cookie.value:
            done.append(f"the cookie {name} set" if cookie.value else f"the cookie {name} emptied")
    return "the response, " + (", ".join(done) if done else "unchanged")


def middleware_called(frame):
    middleware = frame.f_locals["self"]
    text = f"MiddlewareMixin.__call__(request), on {type(middleware).__name__}"
    if not hasattr(middleware, "process_request"):
        text += ", which has no process_request"
    return text


def chain_of(handler) -> list:
    """The middleware instances of a handler's chain, outermost first."""
    found, layer = [], handler._middleware_chain
    while True:
        cells = dict(zip(layer.__code__.co_freevars, layer.__closure__ or ()))
        inner = cells["get_response"].cell_contents
        if not hasattr(inner, "get_response"):
            return found
        found.append(inner)
        layer = inner.get_response


def views_middleware(frame):
    handler = frame.f_locals["self"]
    hooks = [m.__self__.__class__.__name__ for m in handler._view_middleware]
    lacking = [type(m).__name__ for m in chain_of(handler) if not hasattr(m, "process_view")]
    under = []
    if lacking:  # the test load_middleware made when it built the chain, not one _get_response makes now
        def listed(names):
            return " and ".join(names) if len(names) < 3 else ", ".join(names[:-1]) + " and " + names[-1]
        under.append("BaseHandler.load_middleware, building the chain, kept "
                     + (f"the process_view of {listed(hooks)} only" if hooks else "no process_view")
                     + f": {listed(lacking)} {'has' if len(lacking) == 1 else 'have'} none")
    return "BaseHandler._get_response(request)", under


def view_given(frame) -> str:
    f = frame.f_locals
    return (f"CsrfViewMiddleware.process_view(request, {f['callback'].__name__}, {f['callback_args']!r}, "
            f"{f['callback_kwargs']!r}), for a {f['request'].method!r}")


def instance_of(frame) -> str:
    return "the chain's" if any(m is frame.f_locals["self"] for m in INSTANCES) else "the decorator's"


def policy_said(config) -> str:
    """A policy's dictionary as it would be written, CSP's members by their values."""
    def plain(v):
        if isinstance(v, CSP):
            return str(v)
        if isinstance(v, (list, tuple)):
            return type(v)(plain(x) for x in v)
        if isinstance(v, set):
            return sorted(plain(x) for x in v)
        return v
    return repr({k: plain(v) for k, v in config.items()})


def policy_given(frame) -> str:
    f = frame.f_locals
    config = f["config"]
    which = ("SECURE_CSP" if config is settings.SECURE_CSP else "SECURE_CSP_REPORT_ONLY" if config is settings.SECURE_CSP_REPORT_ONLY
             else f"the policy {policy_said(config)}")
    return f"build_policy({which}, {said(f['nonce'])})"


def token_returned(frame, value) -> str:
    return f"the token {value!r}; request.META now holds {meta_said(frame.f_locals['request'])}"


# What to write of a call, by its function's module and qualified name.
LABELS = {
    ("django.core.handlers.wsgi", "WSGIHandler.__call__"): lambda f: "WSGIHandler.__call__(environ, start_response)",
    ("django.core.handlers.base", "BaseHandler._get_response"): views_middleware,
    ("django.middleware", "MiddlewareMixin.__call__"): middleware_called,
    ("django.middleware.security", "SecurityMiddleware.process_request"): method_of,
    ("django.middleware.security", "SecurityMiddleware.process_response"): hook_given,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_request"): method_of,
    ("django.middleware.csrf", "CsrfViewMiddleware._get_secret"): method_of,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_view"): view_given,
    ("django.middleware.csrf", "CsrfViewMiddleware._accept"): method_of,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_response"): lambda f: (
        hook_given(f) + f", request.META holding {meta_said(f.f_locals['request'])}"),
    ("django.middleware.csrf", "CsrfViewMiddleware._set_csrf_cookie"): method_of,
    ("django.middleware.csrf", "get_token"): lambda f: "get_token(request)",
    ("django.middleware.clickjacking", "XFrameOptionsMiddleware.process_response"): hook_given,
    ("django.middleware.clickjacking", "XFrameOptionsMiddleware.get_xframe_options_value"): method_of,
    ("django.middleware.csp", "ContentSecurityPolicyMiddleware.process_request"): method_of,
    ("django.middleware.csp", "ContentSecurityPolicyMiddleware.process_response"): hook_given,
    ("django.utils.csp", "build_policy"): policy_given,
    ("django.utils.csp", "nonce_attr"): lambda f: "nonce_attr(context), for {% csp_nonce_attr %}",
    ("django.utils.csp", "generate_nonce"): lambda f: "generate_nonce()",
    ("django.template.context_processors", "csrf"): lambda f: "the context processor csrf(request)",
    ("django.template.context_processors", "csp"): lambda f: (  # csrf_failure calls it itself, outside any RequestContext
        "csp(request), called by csrf_failure" if f.f_back.f_code.co_name == "csrf_failure" else "the context processor csp(request)"),
    ("django.template.defaulttags", "CsrfTokenNode.render"): lambda f: "CsrfTokenNode.render(context), for {% csrf_token %}",
    ("django.shortcuts", "render"): lambda f: f"render(request, {f.f_locals['template_name']!r})",
    ("__main__", "berths"): lambda f: "berths(request)",
    ("django.middleware.csrf", "CsrfViewMiddleware._origin_verified"): lambda f: (
        f"CsrfViewMiddleware._origin_verified(request), the Origin {f.f_locals['request'].META['HTTP_ORIGIN']!r}"),
    ("django.middleware.csrf", "CsrfViewMiddleware._check_referer"): lambda f: (
        f"CsrfViewMiddleware._check_referer(request), the Referer {f.f_locals['request'].META.get('HTTP_REFERER')!r}"),
    ("django.middleware.csrf", "CsrfViewMiddleware._check_token"): method_of,
    ("django.middleware.csrf", "_check_token_format"): lambda f: f"_check_token_format({f.f_locals['token']!r}), {len(f.f_locals['token'])} characters",
    ("django.middleware.csrf", "_does_token_match"): lambda f: (
        f"_does_token_match({f.f_locals['request_csrf_token']!r}, {f.f_locals['csrf_secret']!r})"),
    ("django.middleware.csrf", "_unmask_cipher_token"): lambda f: f"_unmask_cipher_token({f.f_locals['token']!r})",
    ("django.middleware.csrf", "_mask_cipher_secret"): lambda f: f"_mask_cipher_secret({f.f_locals['secret']!r})",
    ("django.middleware.csrf", "_add_new_csrf_cookie"): lambda f: "_add_new_csrf_cookie(request)",
    ("django.middleware.csrf", "_get_new_csrf_string"): lambda f: "_get_new_csrf_string()",
    ("django.middleware.csrf", "rotate_token"): lambda f: "rotate_token(request)",
    ("django.utils.crypto", "constant_time_compare"): lambda f: f"constant_time_compare({f.f_locals['val1']!r}, {f.f_locals['val2']!r})",
    ("django.middleware.csrf", "RejectRequest.__init__"): lambda f: f"RejectRequest({f.f_locals['reason']!r})",
    ("django.middleware.csrf", "CsrfViewMiddleware._reject"): lambda f: (
        f"CsrfViewMiddleware._reject(request, {f.f_locals['reason']!r})"),
    ("django.middleware.csrf", "_get_failure_view"): lambda f: "_get_failure_view()",
    ("django.urls.utils", "get_callable"): lambda f: f"get_callable({f.f_locals['lookup_view']!r})",
    ("django.views.csrf", "csrf_failure"): lambda f: f"csrf_failure(request, reason={f.f_locals['reason']!r})",
    ("django.template.loader", "get_template"): lambda f: f"get_template({f.f_locals['template_name']!r})",
    ("django.template.engine", "Engine.from_string"): lambda f: (
        "Engine.from_string(the text of django/views/templates/csrf_403.html)" if f.f_locals["template_code"] == CSRF_403
        else "Engine.from_string(some other text)"),
    ("django.utils.log", "log_response"): lambda f: (
        f"log_response({f.f_locals['message']!r}, ...) to {f.f_locals['logger'].name}, "
        + ("the response already marked as logged" if getattr(f.f_locals["response"], "_has_been_logged", False)
           else "the response not yet logged")),
    ("django.core.handlers.base", "BaseHandler.get_response"): method_of,
    ("django.http.request", "HttpRequest.is_secure"): method_of,
    ("django.http.request", "HttpRequest.get_host"): lambda f: f"HttpRequest.get_host(), the Host {f.f_locals['self'].META['HTTP_HOST']!r}",
    ("django.http.request", "HttpRequest.get_full_path"): lambda f: "HttpRequest.get_full_path()",
    ("django.core.handlers.exception", "response_for_exception"): lambda f: (
        f"response_for_exception(request, {type(f.f_locals['exc']).__name__})"),
    ("django.core.handlers.exception", "handle_uncaught_exception"): lambda f: "handle_uncaught_exception(request, resolver, exc_info)",
    ("django.core.handlers.exception", "get_exception_response"): lambda f: (
        f"get_exception_response(request, resolver, {f.f_locals['status_code']}, {type(f.f_locals['exception']).__name__})"),
}
def args_of(frame, *names) -> str:
    """The arguments of a call, as they would be written, keys put into words."""
    out = []
    for name in names:
        value = frame.f_locals[name]
        if name in ("key", "secret") and value is not None:
            out.append(key_said(value))
        else:
            out.append(repr(value))
    return ", ".join(out)


def short(value) -> str:
    """A value by its repr, or, where that is long, by its kind and the length of its JSON."""
    text = repr(value)
    if len(text) <= 60:
        return text
    return f"a {type(value).__name__} of {len(signing.JSONSerializer().dumps(value))} bytes as JSON"


def signer_made(frame) -> str:
    f = frame.f_locals
    given = []
    for n in ("key", "sep", "salt", "algorithm", "fallback_keys"):
        value = f[n]
        if value is None or (n == "sep" and value == ":"):
            continue
        if n == "key":
            given.append(f"key={key_said(value)}")
        elif n == "fallback_keys":
            given.append("fallback_keys=" + (f"[{', '.join(key_said(k) for k in value)}]" if isinstance(value, list)
                                             else f"a {type(value).__name__} object"))
        else:
            given.append(f"{n}={value!r}")
    given = ", ".join(given)
    kind = type(f["self"]).__name__
    return f"Signer.__init__({given})" + (f"  (a {kind})" if kind != "Signer" else "")


def signer_returned(frame, value) -> str:
    signer = frame.f_locals["self"]
    fallbacks = [key_said(k) for k in signer.fallback_keys]
    return (f"its key {key_said(signer.key)}, its fallback keys "
            + (", ".join(fallbacks) if fallbacks else "none") + f", its salt {signer.salt!r}")


def signature_of(frame) -> str:
    f = frame.f_locals
    signer, key = f["self"], f["key"]
    if key is None:
        which = f"no key given, so the key, {key_said(signer.key)}"
    elif key is signer.key or key == signer.key:
        which = f"the key, {key_said(key)}"
    else:
        which = f"the fallback key, {key_said(key)}"
    return f"Signer.signature({f['value']!r}), {which}"


LABELS.update({
    ("django.core.signing", "Signer.__init__"): signer_made,
    ("django.core.signing", "Signer.signature"): signature_of,
    ("django.core.signing", "Signer.sign"): lambda f: f"Signer.sign({f.f_locals['value']!r})",
    ("django.core.signing", "Signer.unsign"): lambda f: f"Signer.unsign({f.f_locals['signed_value']!r})",
    ("django.core.signing", "TimestampSigner.sign"): lambda f: f"TimestampSigner.sign({f.f_locals['value']!r})",
    ("django.core.signing", "TimestampSigner.unsign"): lambda f: (
        f"TimestampSigner.unsign({f.f_locals['value']!r}, max_age={f.f_locals['max_age']!r})"),
    ("django.core.signing", "TimestampSigner.timestamp"): lambda f: "TimestampSigner.timestamp()",
    ("django.core.signing", "Signer.sign_object"): lambda f: (
        f"Signer.sign_object({short(f.f_locals['obj'])}, compress={f.f_locals['compress']!r})"),
    ("django.core.signing", "Signer.unsign_object"): lambda f: f"Signer.unsign_object({f.f_locals['signed_obj']!r})",
    ("django.core.signing", "dumps"): lambda f: f"dumps({f.f_locals['obj']!r}, salt={f.f_locals['salt']!r})",
    ("django.core.signing", "loads"): lambda f: (
        f"loads({f.f_locals['s']!r}, salt={f.f_locals['salt']!r}" + (f", max_age={f.f_locals['max_age']!r})" if f.f_locals["max_age"] is not None else ")")),
    ("django.core.signing", "base64_hmac"): lambda f: f"base64_hmac({args_of(f, 'salt', 'value', 'key', 'algorithm')})",
    ("django.utils.crypto", "salted_hmac"): lambda f: f"salted_hmac({args_of(f, 'key_salt', 'value', 'secret')}, algorithm={f.f_locals['algorithm']!r})",
    ("django.core.signing", "get_cookie_signer"): lambda f: f"get_cookie_signer(salt={f.f_locals['salt']!r})",
    ("django.core.signing", "_unsign_cookie"): lambda f: (
        f"_unsign_cookie({f.f_locals['signed_value']!r}, cookie_name={f.f_locals['cookie_name']!r}, salt={f.f_locals['salt']!r})"),
})
AFTER.update({
    ("django.core.signing", "Signer.__init__"): signer_returned,
    ("django.core.signing", "Signer.signature"): as_is,
    ("django.core.signing", "Signer.sign"): as_is,
    ("django.core.signing", "Signer.unsign"): as_is,
    ("django.core.signing", "TimestampSigner.sign"): as_is,
    ("django.core.signing", "TimestampSigner.unsign"): as_is,
    ("django.core.signing", "TimestampSigner.timestamp"): as_is,
    ("django.core.signing", "Signer.sign_object"): as_is,
    ("django.core.signing", "Signer.unsign_object"): as_is,
    ("django.core.signing", "dumps"): as_is,
    ("django.core.signing", "loads"): as_is,
    ("django.core.signing", "base64_hmac"): as_is,
})

LABELS.update({
    ("django.contrib.auth", "login"): lambda f: f"login(request, {said(f.f_locals['user'])})",
    ("django.contrib.sessions.backends.base", "SessionBase.cycle_key"): method_of,
    ("django.contrib.sessions.backends.base", "SessionBase.flush"): method_of,
    ("__main__", "log_in"): lambda f: "log_in(request)",
    ("django.contrib.auth", "get_user"): lambda f: "get_user(request)",
    ("django.core.checks.registry", "CheckRegistry.run_checks"): lambda f: "CheckRegistry.run_checks(...)",
    ("django.core.checks.security.csrf", "check_csrf_failure_view"): lambda f: "check_csrf_failure_view(app_configs)",
    ("django.contrib.sessions.backends.base", "SessionBase.decode"): lambda f: "SessionBase.decode(the stored string)",
    ("django.contrib.sessions.backends.db", "SessionStore.load"): method_of,
    ("django.contrib.auth.base_user", "AbstractBaseUser._get_session_auth_hash"): lambda f: (
        "AbstractBaseUser._get_session_auth_hash(" + ("secret=" + key_said(f.f_locals["secret"]) if f.f_locals["secret"] else "") + ")"),
    ("django.contrib.auth.tokens", "PasswordResetTokenGenerator.check_token"): lambda f: "PasswordResetTokenGenerator.check_token(user, token)",
    ("django.contrib.auth.tokens", "PasswordResetTokenGenerator._make_token_with_timestamp"): lambda f: (
        f"PasswordResetTokenGenerator._make_token_with_timestamp(user, timestamp, {key_said(f.f_locals['secret'])})"),
    ("django.middleware.csrf", "CsrfViewMiddleware._bad_token_message"): lambda f: (
        f"CsrfViewMiddleware._bad_token_message({f.f_locals['reason']!r}, {f.f_locals['token_source']!r})"),
})
AFTER.update({
    ("django.contrib.auth", "get_user"): as_is,
    ("django.contrib.sessions.backends.base", "SessionBase.decode"): as_is,
    ("django.contrib.sessions.backends.db", "SessionStore.load"): as_is,
    ("django.contrib.auth.base_user", "AbstractBaseUser._get_session_auth_hash"): as_is,
    ("django.contrib.auth.tokens", "PasswordResetTokenGenerator.check_token"): as_is,
    ("__main__", "log_in"): as_is,
    ("django.middleware.csrf", "CsrfViewMiddleware._bad_token_message"): as_is,
    ("django.middleware.csrf", "rotate_token"): lambda f, v: f"{said(v)}; request.META now holds {meta_said(f.f_locals['request'])}",
})

def cached_body(frame) -> str:
    return f"{frame.f_code.co_qualname}, the body of the cached_property"


def collection_said(frame, value) -> str:
    if isinstance(value, dict):
        return f"{type(value).__name__} {dict(value)!r}"
    return repr(value)


def security_made(frame, value) -> str:
    m = frame.f_locals["self"]
    return (f"sts_seconds {m.sts_seconds!r}, sts_preload {m.sts_preload!r}, referrer_policy {m.referrer_policy!r}, "
            f"redirect_exempt {[p.pattern for p in m.redirect_exempt]!r}")


def wrapper_of(frame) -> str:
    """A decorator's wrapper, by the decorator that made it."""
    decorator = frame.f_code.co_qualname.split(".<locals>")[0]
    return f"the wrapper {decorator} made, around {frame.f_locals['view_func'].__name__}"


LABELS.update({
    ("django.middleware.csrf", "CsrfViewMiddleware.csrf_trusted_origins_hosts"): cached_body,
    ("django.middleware.csrf", "CsrfViewMiddleware.allowed_origins_exact"): cached_body,
    ("django.middleware.csrf", "CsrfViewMiddleware.allowed_origin_subdomains"): cached_body,
    ("django.utils.http", "is_same_domain"): lambda f: f"is_same_domain({f.f_locals['host']!r}, {f.f_locals['pattern']!r})",
    ("django.middleware.security", "SecurityMiddleware.__init__"): lambda f: "SecurityMiddleware.__init__(get_response)",
    ("django.views.decorators.clickjacking", "xframe_options_exempt.<locals>._view_wrapper"): wrapper_of,
    ("django.views.decorators.clickjacking", "xframe_options_sameorigin.<locals>._view_wrapper"): wrapper_of,
    ("django.views.decorators.csp", "_make_csp_decorator.<locals>.decorator.<locals>._wrapped_sync_view"): lambda f: (
        f"the wrapper csp_override made, around {f.f_locals['view_func'].__name__}, the policy {policy_said(f.f_locals['config_attr_value'])}"),
    ("__main__", "tides"): lambda f: "tides(request)",
    ("__main__", "chart"): lambda f: "chart(request)",
    ("__main__", "notice"): lambda f: f"notice(request{', number=' + repr(f.f_locals['number']) if f.f_locals['number'] is not None else ''})",
    ("__main__", "protected"): lambda f: "protected(request)",
    ("__main__", "RotatesOnTheWayOut.process_response"): hook_given,
})
AFTER.update({
    ("django.middleware.csrf", "CsrfViewMiddleware.csrf_trusted_origins_hosts"): collection_said,
    ("django.middleware.csrf", "CsrfViewMiddleware.allowed_origins_exact"): collection_said,
    ("django.middleware.csrf", "CsrfViewMiddleware.allowed_origin_subdomains"): collection_said,
    ("django.utils.http", "is_same_domain"): as_is,
    ("django.middleware.security", "SecurityMiddleware.__init__"): security_made,
    ("django.views.decorators.clickjacking", "xframe_options_exempt.<locals>._view_wrapper"): lambda f, v: (
        f"{said(v)}, its xframe_options_exempt {getattr(v, 'xframe_options_exempt', None)!r}"),
    ("django.views.decorators.clickjacking", "xframe_options_sameorigin.<locals>._view_wrapper"): lambda f, v: (
        f"{said(v)}, its X-Frame-Options {v.get('X-Frame-Options')!r}"),
    ("django.views.decorators.csp", "_make_csp_decorator.<locals>.decorator.<locals>._wrapped_sync_view"): lambda f, v: (
        f"{said(v)}, its _csp_config {policy_said(v._csp_config)}"),
    ("__main__", "tides"): lambda f, v: f"{said(v)}, its Content-Security-Policy {v.get('Content-Security-Policy')!r}",
    ("__main__", "chart"): as_is,
    ("__main__", "notice"): as_is,
    ("__main__", "protected"): as_is,
    ("__main__", "RotatesOnTheWayOut.process_response"): hook_returned,
    ("django.middleware.csrf", "CsrfViewMiddleware._set_csrf_cookie"): lambda f, v: (
        f"the session holds {f.f_locals['request'].session.get('_csrftoken')!r} under '_csrftoken', "
        f"the session modified {f.f_locals['request'].session.modified!r}" if settings.CSRF_USE_SESSIONS else None),
    ("django.contrib.sessions.middleware", "SessionMiddleware.process_response"): hook_returned,
})
LABELS.update({
    ("django.contrib.sessions.middleware", "SessionMiddleware.process_response"): lambda f: (
        hook_given(f) + f", the session accessed {f.f_locals['request'].session.accessed!r}, modified {f.f_locals['request'].session.modified!r}"),
})

LABELS[("django.middleware.security", "SecurityMiddleware.process_request")] = lambda f: (
    f"SecurityMiddleware.process_request(request), the path it searches {f.f_locals['request'].path.lstrip('/')!r}"
    if f.f_locals["self"].redirect_exempt else "SecurityMiddleware.process_request(request)")

with open(os.path.join(os.path.dirname(django.__file__), "views", "templates", "csrf_403.html"), encoding="utf-8") as fh:
    CSRF_403 = fh.read()

AFTER.update({
    ("django.middleware.security", "SecurityMiddleware.process_request"): as_is,
    ("django.middleware.security", "SecurityMiddleware.process_response"): hook_returned,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_request"): lambda f, v: f"{said(v)}; request.META holds {meta_said(f.f_locals['request'])}",
    ("django.middleware.csrf", "CsrfViewMiddleware._get_secret"): as_is,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_view"): as_is,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_response"): hook_returned,
    ("django.middleware.csrf", "get_token"): token_returned,
    ("django.middleware.clickjacking", "XFrameOptionsMiddleware.process_response"): hook_returned,
    ("django.middleware.clickjacking", "XFrameOptionsMiddleware.get_xframe_options_value"): as_is,
    ("django.middleware.csp", "ContentSecurityPolicyMiddleware.process_request"): lambda f, v: (
        f"{said(v)}; request._csp_nonce is {said(f.f_locals['request']._csp_nonce)}"),
    ("django.middleware.csp", "ContentSecurityPolicyMiddleware.process_response"): hook_returned,
    ("django.utils.csp", "build_policy"): as_is,
    ("django.utils.csp", "nonce_attr"): lambda f, v: repr(str(v)),
    ("django.utils.csp", "generate_nonce"): as_is,
    ("django.template.context_processors", "csrf"): lambda f, v: (  # reading _wrapped evaluates nothing
        "{'csrf_token': " + a(type(v["csrf_token"]).__name__)
        + (", not yet evaluated}" if v["csrf_token"]._wrapped is empty else ", evaluated}")),
    ("django.template.context_processors", "csp"): lambda f, v: "{'csp_nonce': " + said(v["csp_nonce"]) + "}",
    ("__main__", "berths"): as_is,
    ("django.middleware.csrf", "CsrfViewMiddleware._origin_verified"): as_is,
    ("django.middleware.csrf", "CsrfViewMiddleware._check_referer"): as_is,
    ("django.middleware.csrf", "CsrfViewMiddleware._check_token"): as_is,
    ("django.middleware.csrf", "_does_token_match"): as_is,
    ("django.middleware.csrf", "_unmask_cipher_token"): as_is,
    ("django.middleware.csrf", "_mask_cipher_secret"): as_is,
    ("django.middleware.csrf", "_add_new_csrf_cookie"): as_is,
    ("django.middleware.csrf", "_get_new_csrf_string"): as_is,
    ("django.utils.crypto", "constant_time_compare"): as_is,
    ("django.middleware.csrf", "CsrfViewMiddleware._reject"): as_is,
    ("django.middleware.csrf", "_get_failure_view"): lambda f, v: f"the function {v.__module__}.{v.__qualname__}",
    ("django.urls.utils", "get_callable"): lambda f, v: f"the function {v.__module__}.{v.__qualname__}",
    ("django.views.csrf", "csrf_failure"): as_is,
    ("django.http.request", "HttpRequest.is_secure"): as_is,
    ("django.http.request", "HttpRequest.get_host"): as_is,
    ("django.http.request", "HttpRequest.get_full_path"): as_is,
    ("django.core.handlers.exception", "response_for_exception"): as_is,
    ("django.core.handlers.exception", "get_exception_response"): as_is,
})


def rules(*names: str) -> dict:
    """The labels of the functions named, by qualified name."""
    chosen = {key: label for key, label in LABELS.items() if key[1] in names}
    missing = set(names) - {key[1] for key in chosen}
    if missing:
        raise SystemExit(f"recordings/security.py: no label for {missing}")
    return chosen


ASKING = {}  # the names a line run from its own text may use


def ask(expression: str, brief: bool = False, warned: bool = False) -> None:
    """One question and its answer, on one line. The question is evaluated as it is written
    down, so the line cannot say one thing and the script do another. A log record made while
    it was answered stands under it; and, where `warned`, each warning Python gave, by its
    class and message, and the line it is attributed to, in words."""
    watching = sys.getprofile()
    sys.setprofile(None)  # a question is its answer and nothing else: no calls are written down under it
    flush()
    before = len(LINES)
    with warnings.catch_warnings(record=True) as given:
        warnings.simplefilter("always" if warned else "default")
        try:
            value = eval(expression, ASKING)
            answer = said(value)
        except Exception as raised:
            answer = f"raises {type(raised).__name__}" + ("" if brief else f": {raised}")
    for one in given if warned else ():
        where = ("this line of the script's" if one.filename == "<string>" else
                 "a line of Django's" if one.filename.startswith(os.path.dirname(django.__file__)) else "a line elsewhere")
        note(f"Python warns: {one.category.__name__}: {one.message} It is attributed to {where}.")
    LINES[before:] = ["  " * len(STACK) + f"{expression}  ->  {answer}", *("  " + line for line in LINES[before:])]
    sys.setprofile(watching)


def do(statement: str) -> None:
    """A statement, written down and then run as it is written, with the calls the rules in
    force record nested under it, and under them the exception that left it, if one did."""
    note(statement)
    STACK.append(None)
    try:
        exec(statement, ASKING)
    except Exception as raised:
        note(f"raises {type(raised).__name__}: {raised}")
    finally:
        flush()
        STACK.pop()


def step(words: str) -> None:
    """A line of words: what the script is about to do, by its own hand."""
    note(words)


class Noted(logging.Handler):
    def emit(self, record):
        note(f"log, {record.levelname} to {record.name}: {record.getMessage()}")


logging.getLogger("django").addHandler(Noted())


def uncaught(sender, **kwargs):
    exception = sys.exc_info()[1]
    note(f"signal got_request_exception, for {type(exception).__name__}")


from django.core.signals import got_request_exception  # noqa: E402

got_request_exception.connect(uncaught)


class block:
    """`with block("title"):` seeds the random source from the title, and prints the block
    under the title when it ends."""

    def __init__(self, title: str):
        self.title = title

    def __enter__(self):
        DRAWS.seed(self.title)
        ASKING.clear()
        ASKING.update(NAMES)
        return self

    def __exit__(self, *exc):
        CLOCK[0] = NOW  # a block that moved the clock leaves it as the next expects it
        if exc[0] is None:
            show(self.title)


# ---------------------------------------------------------------------------------------------
# The server and the browser.

SITE = "https://harbour.example"


def environ(method: str, url: str, body: bytes = b"", content_type: str = "", headers: dict | None = None) -> dict:
    parts = urlsplit(url)
    secure = parts.scheme == "https"
    made = {
        "REQUEST_METHOD": method, "PATH_INFO": parts.path, "QUERY_STRING": parts.query, "SCRIPT_NAME": "",
        "SERVER_NAME": parts.hostname, "SERVER_PORT": str(parts.port or (443 if secure else 80)),
        "SERVER_PROTOCOL": "HTTP/1.1", "HTTP_HOST": parts.netloc, "wsgi.url_scheme": parts.scheme,
        "wsgi.input": io.BytesIO(body),
    }
    if body or method not in ("GET", "HEAD"):
        made["CONTENT_LENGTH"] = str(len(body))
    if content_type:
        made["CONTENT_TYPE"] = content_type
    for name, value in (headers or {}).items():
        made["HTTP_" + name.upper().replace("-", "_")] = value
    return made


TOKEN_IN_PAGE = re.compile(r'name="csrfmiddlewaretoken" value="([A-Za-z0-9]+)"')


class Browser:
    """The script's browser: see the docstring."""

    def __init__(self):
        self.cookies = {}  # name -> value, of harbour.example
        self.page = ""  # the last page it was given that holds a form

    def token(self) -> str:
        found = TOKEN_IN_PAGE.search(self.page)
        return found[1] if found else ""

    def keep(self, headers: list, content: bytes) -> None:
        for name, value in headers:
            if name == "Set-Cookie":
                pair = value.split(";")[0]
                cookie, _, kept = pair.partition("=")
                if "Max-Age=0" in value:
                    self.cookies.pop(cookie, None)
                else:
                    self.cookies[cookie] = kept
        text = content.decode()
        if "<form" in text:
            self.page = text

    def send(self, handler, method: str, url: str, *, rules: dict | None = None, form: dict | None = None,
             headers: dict | None = None, cookies: bool = True, origin: str | None = SITE, show_headers=(), body=(),
             says: bool = True, raw_body: bytes | None = None, content_type: str = ""):
        """Send a request to the handler as the browser does, as a WSGI server would pass it,
        and keep what the response sets."""
        sent = dict(headers or {})
        if cookies and self.cookies:
            sent["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if method == "POST" and origin is not None and "Origin" not in sent:
            sent["Origin"] = origin
        content = raw_body if raw_body is not None else b""
        if form is not None:
            content = urlencode(form).encode()
            content_type = "application/x-www-form-urlencoded"
        if says:
            words = [f"{name}: {value}" for name, value in sent.items()]
            if form is not None:
                words.append("the form " + ", ".join(f"{k}={v}" for k, v in form.items()))
            elif raw_body is not None:
                words.append(f"the body {raw_body.decode()!r}, {content_type}")
            step(f"{method} {url}, the browser sending " + ("; ".join(words) if words else "nothing but the request"))
        env = environ(method, url, content, content_type, sent)
        return serve(handler, env, rules or {}, show_headers, body, self)

    def given_page(self, handler, url: str = SITE + "/berths/") -> None:
        """A GET of the page, made without writing anything down but one line of what the
        browser was given and keeps."""
        before = len(LINES)
        serve(handler, environ("GET", url, headers={"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items())}
                               if self.cookies else None), {}, quiet=True, browser=self)
        del LINES[before:]
        step(f"beforehand, unrecorded, GET {url} gave the browser the cookie csrftoken={self.cookies.get('csrftoken')} "
             f"and a page whose form holds the token {self.token()}")


def serve(handler, env: dict, rules: dict, show_headers=(), body=(), browser: Browser | None = None, quiet: bool = False):
    """Call the handler as a WSGI server does: start the response, send the body, close it.
    `show_headers` is "all", for every header, or the names of those to write down; either
    way they are written in the order start_response was given them. `body` names what the
    lines of the body to write down contain, or is "all"."""
    got = {}

    def start_response(status, response_headers):
        got["status"], got["headers"] = status, response_headers
        if quiet:
            return
        if show_headers == "all":
            note(f'start_response("{status}", headers), the headers being:')
            for name, value in response_headers:
                note(f"  {name}: {value}")
        else:  # the headers named, in the order start_response was given them, then those it was not given
            note(f'start_response("{status}", headers)')
            for header, value in response_headers:
                if header in show_headers:
                    note(f"  {header}: {value}")
            present = {header for header, _ in response_headers}
            for name in show_headers:
                if name not in present:
                    note(f"  no {name}")

    with recorded(rules):
        try:
            result = handler(env, start_response)
        except Exception as raised:
            flush()
            note(f"the handler raises {type(raised).__name__} to the server: {raised}")
            return got
        content = b"".join(result)
        result.close()
    text = content.decode()
    if body == "all":
        note(f"the server sends the body: {text!r}")
    elif body:
        lines = [line.strip() for line in text.splitlines() if any(marker in line for marker in body)]
        note(f"the server sends the body, {len(content)} bytes; its lines with {' or '.join(repr(m) for m in body)}:")
        for line in lines:
            note(f"  {line}")
    if browser is not None:
        browser.keep(got["headers"], content)
    return got


HANDLER = WSGIHandler()  # the harbour's chain, built once, as a server builds it

# The names a line run from its text may use, given afresh to each block.
NAMES = {
    "WSGIHandler": WSGIHandler, "settings": settings, "signing": signing, "CSP": CSP, "LazyNonce": LazyNonce,
    "build_policy": build_policy, "CSRF_ALLOWED_CHARS": CSRF_ALLOWED_CHARS, "_mask_cipher_secret": _mask_cipher_secret,
    "_unmask_cipher_token": _unmask_cipher_token, "get_token": get_token, "rotate_token": rotate_token,
    "datetime": datetime, "timedelta": datetime.timedelta, "HARBOUR_KEY": HARBOUR_KEY, "NEW_KEY": NEW_KEY,
    "Signer": signing.Signer, "TimestampSigner": signing.TimestampSigner, "override_settings": override_settings,
    "_get_new_csrf_string": _get_new_csrf_string, "environ": environ, "WSGIRequest": WSGIRequest, "HttpResponse": HttpResponse,
    "ContentSecurityPolicyMiddleware": ContentSecurityPolicyMiddleware, "engines": engines, "salted_hmac": salted_hmac,
    "CookieStorage": CookieStorage, "constants": message_constants,
}


# ---------------------------------------------------------------------------------------------
# The blocks.

def block_page() -> None:
    with block("GET https://harbour.example/berths/, no cookie: the four middleware, in and out"):
        browser = Browser()
        browser.send(HANDLER, "GET", SITE + "/berths/", show_headers="all", body=("csrfmiddlewaretoken", "nonce"), rules=rules(
            "WSGIHandler.__call__", "MiddlewareMixin.__call__", "BaseHandler._get_response",
            "SecurityMiddleware.process_request", "CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret",
            "ContentSecurityPolicyMiddleware.process_request", "CsrfViewMiddleware.process_view", "CsrfViewMiddleware._accept",
            "berths", "csrf", "csp", "CsrfTokenNode.render", "get_token", "nonce_attr", "generate_nonce",
            "ContentSecurityPolicyMiddleware.process_response", "build_policy", "XFrameOptionsMiddleware.process_response",
            "XFrameOptionsMiddleware.get_xframe_options_value", "CsrfViewMiddleware.process_response",
            "CsrfViewMiddleware._set_csrf_cookie", "SecurityMiddleware.process_response"))


CHECKED = (
    "CsrfViewMiddleware.process_request", "CsrfViewMiddleware.process_view", "CsrfViewMiddleware._origin_verified", "CsrfViewMiddleware._check_referer",
    "CsrfViewMiddleware._check_token", "CsrfViewMiddleware._get_secret", "RejectRequest.__init__", "CsrfViewMiddleware._reject",
    "CsrfViewMiddleware._accept", "log_response",
)


def block_accepted() -> None:
    with block("POST https://harbour.example/berths/, form and cookie as the page left them: accepted"):
        browser = Browser()
        browser.given_page(HANDLER)
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                     show_headers=("Content-Security-Policy", "Vary", "Set-Cookie"), body="all", rules=rules(
                         "CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret", "CsrfViewMiddleware.process_view",
                         "CsrfViewMiddleware._origin_verified", "CsrfViewMiddleware._check_token", "_check_token_format",
                         "_does_token_match", "_unmask_cipher_token", "constant_time_compare", "CsrfViewMiddleware._accept",
                         "berths", "CsrfViewMiddleware.process_response", "ContentSecurityPolicyMiddleware.process_response",
                         "build_policy"))


def block_refusals() -> None:
    with block("POST https://harbour.example/berths/, no token: refused, and the failure view"):
        browser = Browser()
        browser.given_page(HANDLER)
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"ship": "Endeavour"},
                     show_headers=("Content-Security-Policy", "Set-Cookie"), body=("nonce", "<h1>", "<p>"), rules=rules(
                         *CHECKED, "_get_failure_view", "get_callable", "csrf_failure", "csp", "get_template", "Engine.from_string",
                         "nonce_attr", "generate_nonce", "ContentSecurityPolicyMiddleware.process_response", "build_policy",
                         "BaseHandler.get_response"))
    with block("POST https://harbour.example/berths/, Origin https://evil.example: refused"):
        browser = Browser()
        browser.given_page(HANDLER)
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                     origin="https://evil.example", show_headers=("Content-Security-Policy",), body=("nonce", "<p>"),
                     rules=rules(*CHECKED, "BaseHandler.get_response"))
    with block("POST https://harbour.example/berths/, neither Origin nor Referer: refused"):
        browser = Browser()
        browser.given_page(HANDLER)
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                     origin=None, show_headers=("Content-Security-Policy",), body=("nonce", "<p>"),
                     rules=rules(*CHECKED, "BaseHandler.get_response"))
    with block("POST https://harbour.example/berths/, no cookie, the browser having forgotten it: refused"):
        browser = Browser()
        browser.given_page(HANDLER)
        token = browser.token()
        browser.cookies.clear()
        step("the browser forgets its cookie, and keeps the page")
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": token, "ship": "Endeavour"},
                     show_headers=("Content-Security-Policy", "Set-Cookie"), body=("nonce", "<p>"),
                     rules=rules(*CHECKED, "BaseHandler.get_response"))


INSIDE = (  # the hooks of the three middleware inside SecurityMiddleware, watched to show whether they run
    "CsrfViewMiddleware.process_request", "ContentSecurityPolicyMiddleware.process_request", "CsrfViewMiddleware.process_view",
    "ContentSecurityPolicyMiddleware.process_response", "XFrameOptionsMiddleware.process_response",
    "CsrfViewMiddleware.process_response",
)


def block_redirect() -> None:
    with block("GET http://harbour.example/berths/?ship=Endeavour, over plain HTTP: the redirect, and nothing inside SecurityMiddleware runs"):
        Browser().send(HANDLER, "GET", "http://harbour.example/berths/?ship=Endeavour", show_headers="all", rules=rules(
            "WSGIHandler.__call__", "MiddlewareMixin.__call__", "SecurityMiddleware.process_request", "HttpRequest.is_secure",
            "HttpRequest.get_host", "HttpRequest.get_full_path", "SecurityMiddleware.process_response", *INSIDE))
    with block("GET http://evil.example/berths/, the browser's Host evil.example: a 400, and no redirect"):
        Browser().send(HANDLER, "GET", "http://evil.example/berths/", show_headers="all", body="all", rules=rules(
            "BaseHandler.get_response", "MiddlewareMixin.__call__", "SecurityMiddleware.process_request", "HttpRequest.is_secure",
            "HttpRequest.get_host", "response_for_exception", "get_exception_response", "log_response",
            "SecurityMiddleware.process_response"))
    for pattern in (r"^health/$", r"^/health/$"):
        with block(f"SECURE_REDIRECT_EXEMPT = [r{pattern!r}], in a handler built under it: which paths, asked for over plain HTTP, are exempt"):
            with override_settings(SECURE_REDIRECT_EXEMPT=[pattern]):
                handler = WSGIHandler()
            for url in (["/health/", "/x/health/", "/healthy/"] if pattern == r"^health/$" else ["/health/"]):
                Browser().send(handler, "GET", "http://harbour.example" + url, show_headers=("Location",), rules=rules(
                    "SecurityMiddleware.process_request", "log_response"))


def block_get_token() -> None:
    with block("get_token: one secret, two masks, over two GETs of https://harbour.example/berths/ a day apart"):
        browser = Browser()
        made = rules("get_token", "_add_new_csrf_cookie", "_get_new_csrf_string", "_mask_cipher_secret")
        browser.send(HANDLER, "GET", SITE + "/berths/", show_headers=("Set-Cookie",), body=("csrfmiddlewaretoken",), rules=made)
        ASKING["first"] = browser.token()
        CLOCK[0] = NOW + 86400
        step("the clock moves on a day, by the script's hand")
        browser.send(HANDLER, "GET", SITE + "/berths/", show_headers=("Set-Cookie",), body=("csrfmiddlewaretoken",), rules=made)
        ASKING.update(second=browser.token(), secret=browser.cookies["csrftoken"], CSRF_ALLOWED_CHARS=CSRF_ALLOWED_CHARS,
                      _unmask_cipher_token=_unmask_cipher_token)
        step("first and second are the tokens of the two pages, secret the cookie's value")
        for expression in ("secret", "first[:32]", "first[32:]", "second[:32]", "second[32:]",
                           "[CSRF_ALLOWED_CHARS.index(c) for c in secret[:3]]",
                           "[CSRF_ALLOWED_CHARS.index(c) for c in first[:3]]",
                           "[CSRF_ALLOWED_CHARS.index(c) for c in first[32:35]]",
                           "_unmask_cipher_token(first)", "_unmask_cipher_token(second)",
                           "_unmask_cipher_token(first) == _unmask_cipher_token(second) == secret"):
            ask(expression)
        ASKING.clear()


SIGNING = ("Signer.__init__", "Signer.sign", "Signer.unsign", "Signer.signature", "constant_time_compare")


def block_signer() -> None:
    with block("Signer.sign and Signer.unsign: the key signs, and unsign checks with the key"):
        with recorded(rules(*SIGNING, "base64_hmac", "salted_hmac")):
            do('signer = Signer(salt="harbour.berths")')
            do('signed = signer.sign("Endeavour")')
        with recorded(rules(*SIGNING)):
            do("signer.unsign(signed)")
    with block("Signer.unsign after SECRET_KEY is changed: a signer made before keeps its keys, one made after has the new"):
        with recorded(rules(*SIGNING)):
            do('signer = Signer(salt="harbour.berths"); signed = signer.sign("Endeavour")')
            do("changed = override_settings(SECRET_KEY=NEW_KEY); changed.enable()")
            do("signer.unsign(signed)")
            do('Signer(salt="harbour.berths").unsign(signed)')
            do("changed.disable()")
    with block("Signer.unsign with the old key in SECRET_KEY_FALLBACKS: the key, then the fallback key"):
        with recorded(rules(*SIGNING)):
            do('signed = Signer(salt="harbour.berths").sign("Endeavour")')
            do("changed = override_settings(SECRET_KEY=NEW_KEY, SECRET_KEY_FALLBACKS=[HARBOUR_KEY]); changed.enable()")
            do('rotated = Signer(salt="harbour.berths")')
            do("rotated.unsign(signed)")
            do('resigned = rotated.sign("Endeavour")')
            ask("resigned == signed")
            do("changed.disable()")


DUMPED = ("dumps", "loads", "TimestampSigner.unsign", "Signer.unsign", "Signer.signature")


def block_dumps() -> None:
    with block('dumps and loads: the berth signed under the salt "harbour.berths", read under it and under another'):
        with recorded(rules("dumps", "Signer.__init__", "Signer.sign_object", "TimestampSigner.sign", "TimestampSigner.timestamp",
                            "Signer.sign", "Signer.signature", "base64_hmac")):
            do('s = signing.dumps({"berth": 4, "ship": "Endeavour"}, salt="harbour.berths")')
        ask("s")
        ask('signing.b64_decode(s.split(":")[0].encode())')
        ask('signing.b62_decode(s.split(":")[1])')
        ask('datetime.datetime.fromtimestamp(signing.b62_decode(s.split(":")[1]), datetime.UTC).isoformat()')
        ask('signing.loads(s, salt="harbour.berths")')
        ask('signing.loads(s, salt="harbour.invoices")')
        ask("signing.loads(s)")
    with block("loads two hours after dumps, the clock moved on by the script's hand: the maximum age"):
        do('s = signing.dumps({"berth": 4, "ship": "Endeavour"}, salt="harbour.berths")')
        CLOCK[0] = NOW + 7200
        step("the clock moves on two hours, by the script's hand")
        with recorded(rules("TimestampSigner.unsign")):
            for age in ("3600", "timedelta(hours=1)", "timedelta(hours=3)"):
                do(f'signing.loads(s, salt="harbour.berths", max_age={age})')
            do('signing.loads(s, salt="harbour.berths")')
    with block("loads of the berth with its JSON changed to berth 5, two hours on: refused as forged, not as old"):
        do('s = signing.dumps({"berth": 4, "ship": "Endeavour"}, salt="harbour.berths")')
        CLOCK[0] = NOW + 7200
        step("the clock moves on two hours, by the script's hand")
        do('forged = signing.b64_encode(b\'{"berth":5,"ship":"Endeavour"}\').decode() + s[s.index(":"):]')
        ask("forged")
        with recorded(rules("TimestampSigner.unsign", "Signer.unsign", "Signer.signature", "constant_time_compare")):
            do('signing.loads(forged, salt="harbour.berths", max_age=3600)')
    with block("Signer.sign_object with compress=True: the berth kept as it is, eight berths compressed"):
        do('signer = Signer(salt="harbour.berths")')
        do('eight = {"berths": [{"berth": n, "ship": "Endeavour"} for n in range(8)]}')
        with recorded(rules("Signer.sign_object")):
            do('small = signer.sign_object({"berth": 4, "ship": "Endeavour"}, compress=True)')
            do("large = signer.sign_object(eight, compress=True)")
        ask("len(signer.sign_object(eight))")
        ask("len(large)")
        ask("large[:4]")
        ask("signer.unsign_object(large) == eight")
    with block('Signer(sep=...): of nine separators, which Signer.__init__ refuses'):
        for sep in ("^", "[", "]", "\\", "`", "_", "/", ".", ""):
            ask(f"Signer(sep={sep!r}).sep")


TRUSTED = ["https://*.harbour.example", "https://pay.example"]
ORIGINS = ("CsrfViewMiddleware._origin_verified", "CsrfViewMiddleware.csrf_trusted_origins_hosts",
           "CsrfViewMiddleware.allowed_origins_exact", "CsrfViewMiddleware.allowed_origin_subdomains", "is_same_domain",
           "CsrfViewMiddleware._check_referer", "HttpRequest.get_host")


def block_trusted() -> None:
    with block(f"POST https://harbour.example/berths/, other sites' Origins, under CSRF_TRUSTED_ORIGINS = {TRUSTED!r}, "
               "with a handler built and used under it"):
        with override_settings(CSRF_TRUSTED_ORIGINS=TRUSTED):
            handler = WSGIHandler()
            browser = Browser()
            browser.given_page(handler)
            for origin in ("https://pilots.harbour.example", "http://pilots.harbour.example", "https://a.pay.example",
                           "https://pay.example"):
                browser.send(handler, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                             origin=origin, rules=rules(*ORIGINS[:5], "HttpRequest.get_host"))
    with block(f"POST https://harbour.example/berths/, a Referer and no Origin, under CSRF_TRUSTED_ORIGINS = {TRUSTED!r}, "
               "with a handler built and used under it"):
        with override_settings(CSRF_TRUSTED_ORIGINS=TRUSTED):
            handler = WSGIHandler()
            browser = Browser()
            browser.given_page(handler)
            for referer in ("https://harbour.example/berths/", "https://harbour.example:8443/berths/",
                            "http://harbour.example/berths/", "https://pilots.harbour.example/berths/"):
                browser.send(handler, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                             origin=None, headers={"Referer": referer}, rules=rules(*ORIGINS[1:]))
    with block("CSRF_TRUSTED_ORIGINS changed after a chain was built, the browser posting with Origin https://pay.example: "
               "that chain keeps its first reading, a chain built after reads the new"):
        do("before = WSGIHandler()")
        browser = Browser()
        browser.given_page(ASKING["before"])
        form = {"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"}
        step("the browser posts, from now on, with Origin: https://pay.example")
        browser.send(ASKING["before"], "POST", SITE + "/berths/", form=form, origin="https://pay.example", rules=rules(*ORIGINS[:4]))
        do('changed = override_settings(CSRF_TRUSTED_ORIGINS=["https://pay.example"]); changed.enable()')
        browser.send(ASKING["before"], "POST", SITE + "/berths/", form=form, origin="https://pay.example", rules=rules(*ORIGINS[:4]))
        do("after = WSGIHandler()")
        browser.send(ASKING["after"], "POST", SITE + "/berths/", form=form, origin="https://pay.example", rules=rules(*ORIGINS[:4]))
        do("changed.disable()")


def block_tokens() -> None:
    with block('POST https://harbour.example/berths/, the cookie "short", set by the script: refused; the 403 sets a new cookie, '
               "and the next page's token is accepted"):
        browser = Browser()
        browser.given_page(HANDLER)
        browser.cookies["csrftoken"] = "short"
        step('the script sets the browser\'s cookie csrftoken to "short"; the browser keeps the page')
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                     show_headers=("Set-Cookie",), rules=rules(
                         "CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret", "_check_token_format",
                         "_add_new_csrf_cookie", "CsrfViewMiddleware._check_token", "RejectRequest.__init__",
                         "CsrfViewMiddleware._reject", "CsrfViewMiddleware.process_response"))
        browser.send(HANDLER, "GET", SITE + "/berths/", show_headers=("Set-Cookie",))
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                     body="all")
    with block("POST https://harbour.example/berths/, a cookie of 64 characters, a secret masked as an older Django set it, "
               "cookie and token made by the script: accepted and no cookie set; the next page sets the 32"):
        browser = ASKING["browser"] = Browser()
        do("secret = _get_new_csrf_string()")
        do('browser.cookies["csrftoken"] = _mask_cipher_secret(secret)')
        do("token = _mask_cipher_secret(secret)")
        step("the browser's form holds that token, as the older Django's page gave it")
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": ASKING["token"], "ship": "Endeavour"},
                     show_headers=("Set-Cookie",), body="all", rules=rules(
                         "CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret", "_unmask_cipher_token",
                         "CsrfViewMiddleware._check_token", "_does_token_match", "CsrfViewMiddleware.process_response"))
        browser.send(HANDLER, "GET", SITE + "/berths/", show_headers=("Set-Cookie",), rules=rules(
            "CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret", "_unmask_cipher_token", "get_token",
            "CsrfViewMiddleware.process_response"))
    with block("POST https://harbour.example/berths/, the token in X-CSRFToken and not in the form"):
        browser = Browser()
        browser.given_page(HANDLER)
        for which, token in (("the cookie's value", browser.cookies["csrftoken"]), ("the page's token", browser.token()),
                             ("a malformed token", "short")):
            step(f"X-CSRFToken carries {which}")
            browser.send(HANDLER, "POST", SITE + "/berths/", form={"ship": "Endeavour"}, headers={"X-CSRFToken": token},
                         rules=rules("CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret", "CsrfViewMiddleware._check_token",
                                     "_check_token_format", "_does_token_match", "CsrfViewMiddleware._bad_token_message",
                                     "CsrfViewMiddleware._reject"))
    with block("PUT https://harbour.example/berths/ with the page's token in a form-encoded body, the browser sending Origin as for a POST: refused"):
        browser = Browser()
        browser.given_page(HANDLER)
        browser.send(HANDLER, "PUT", SITE + "/berths/", headers={"Origin": SITE},
                     raw_body=urlencode({"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"}).encode(),
                     content_type="application/x-www-form-urlencoded",
                     rules=rules("CsrfViewMiddleware.process_request", "CsrfViewMiddleware._check_token", "CsrfViewMiddleware._get_secret", "RejectRequest.__init__",
                                 "CsrfViewMiddleware._reject"))


def block_protect() -> None:
    global INSTANCES
    hooks = rules("CsrfViewMiddleware.process_request", "CsrfViewMiddleware.process_view", "CsrfViewMiddleware._accept",
                  "protected", "get_token", "CsrfViewMiddleware.process_response", "CsrfViewMiddleware._set_csrf_cookie",
                  "RotatesOnTheWayOut.process_response", "rotate_token")
    with block("GET https://harbour.example/protected/, a view under csrf_protect, through the harbour's chain: "
               "two instances of CsrfViewMiddleware, and the cookie set once"):
        INSTANCES = chain_of(HANDLER)
        Browser().send(HANDLER, "GET", SITE + "/protected/", show_headers=("Set-Cookie",), rules=hooks)
        INSTANCES = None
    with block("GET https://harbour.example/protected/, with a handler built with RotatesOnTheWayOut, the script's, after CsrfViewMiddleware "
               "in MIDDLEWARE: rotate_token after the decorator's process_response, and the chain's sends the new secret"):
        middleware = [*HARBOUR_MIDDLEWARE[:2], "__main__.RotatesOnTheWayOut", *HARBOUR_MIDDLEWARE[2:]]
        with override_settings(MIDDLEWARE=middleware):
            handler = WSGIHandler()
        INSTANCES = chain_of(handler)
        Browser().send(handler, "GET", SITE + "/protected/", show_headers=("Set-Cookie",), rules=hooks)
        INSTANCES = None


SESSIONS_MIDDLEWARE = [HARBOUR_MIDDLEWARE[0], "django.contrib.sessions.middleware.SessionMiddleware", *HARBOUR_MIDDLEWARE[1:]]


def block_sessions() -> None:
    title = ("with a handler built under CSRF_USE_SESSIONS = True, SessionMiddleware before CsrfViewMiddleware, "
             'and SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"')
    in_session = rules("CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret", "get_token", "CsrfViewMiddleware.process_response",
                       "CsrfViewMiddleware._set_csrf_cookie", "SessionMiddleware.process_response")
    with override_settings(CSRF_USE_SESSIONS=True, MIDDLEWARE=SESSIONS_MIDDLEWARE,
                           SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies"):
        with block(f"CSRF_USE_SESSIONS = True, sessions in signed cookies: two GETs of https://harbour.example/berths/ and a POST, {title}"):
            handler = WSGIHandler()
            browser = Browser()
            browser.send(handler, "GET", SITE + "/berths/", show_headers=("Vary", "Set-Cookie"), rules=in_session)
            browser.send(handler, "GET", SITE + "/berths/", show_headers=("Vary", "Set-Cookie"), rules=in_session)
            browser.send(handler, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                         show_headers=("Vary", "Set-Cookie"), body="all", rules=in_session)
    with override_settings(CSRF_USE_SESSIONS=True):
        with block("CSRF_USE_SESSIONS = True without SessionMiddleware: GET https://harbour.example/berths/, with a handler built "
                   "under that setting and the harbour's MIDDLEWARE"):
            handler = WSGIHandler()
            Browser().send(handler, "GET", SITE + "/berths/", show_headers=("Content-Type",), rules=rules(
                "CsrfViewMiddleware.process_request", "CsrfViewMiddleware._get_secret", "response_for_exception",
                "handle_uncaught_exception", "log_response"))


def block_settings_read() -> None:
    changes = dict(SECURE_HSTS_PRELOAD=True, SECURE_REFERRER_POLICY="no-referrer, strict-origin-when-cross-origin",
                   X_FRAME_OPTIONS="sameorigin")
    shown = ("Strict-Transport-Security", "Referrer-Policy", "X-Frame-Options")
    with block("Settings changed after a chain was built: SecurityMiddleware keeps what it read when the chain was built, "
               "XFrameOptionsMiddleware reads X_FRAME_OPTIONS at each response"):
        made, through = rules("SecurityMiddleware.__init__"), rules("XFrameOptionsMiddleware.get_xframe_options_value")
        with recorded(made):
            do("before = WSGIHandler()")
        step("GET https://harbour.example/berths/ through the handler before, the browser sending nothing but the request")
        Browser().send(ASKING["before"], "GET", SITE + "/berths/", show_headers=shown, says=False, rules=through)
        with recorded(made):
            do("changed = override_settings(" + ", ".join(f"{k}={v!r}" for k, v in changes.items()) + "); changed.enable()")
            do("after = WSGIHandler()")
        for name in ("before", "after"):
            step(f"GET https://harbour.example/berths/ through the handler {name}, the browser sending nothing but the request")
            Browser().send(ASKING[name], "GET", SITE + "/berths/", show_headers=shown, says=False, rules=through)
        do("changed.disable()")
    with block("GET https://harbour.example/tides/ and /chart/: views under xframe_options_exempt and xframe_options_sameorigin"):
        for url in ("/tides/", "/chart/"):
            Browser().send(HANDLER, "GET", SITE + url, show_headers=("X-Frame-Options",), rules=rules(
                "xframe_options_exempt.<locals>._view_wrapper", "xframe_options_sameorigin.<locals>._view_wrapper",
                "XFrameOptionsMiddleware.process_response", "XFrameOptionsMiddleware.get_xframe_options_value"))


FULLER = ('{"default-src": [CSP.SELF], "img-src": {CSP.SELF, "https://tiles.harbour.example", "data:"}, '
          '"script-src": [CSP.SELF, CSP.NONCE], "style-src": [CSP.NONCE], "frame-src": None, "upgrade-insecure-requests": True}')

PROJECT_403 = "reason=[{{ reason }}] no_cookie=[{{ no_cookie }}] csp_nonce=[{{ csp_nonce }}]\n"


def block_csp() -> None:
    policy = ("Content-Security-Policy",)
    with block("GET https://harbour.example/chart/, /notice/ and /tides/: csp_override with a policy, csp_override({}), "
               "and a header the view sets itself"):
        for url in ("/chart/", "/notice/", "/tides/"):
            Browser().send(HANDLER, "GET", SITE + url, show_headers=policy, rules=rules(
                "_make_csp_decorator.<locals>.decorator.<locals>._wrapped_sync_view", "tides",
                "ContentSecurityPolicyMiddleware.process_response", "build_policy"))
    with block("GET https://harbour.example/notices/7/, a view under csp_override({}) that raises Http404: "
               "answered under the site's policy"):
        Browser().send(HANDLER, "GET", SITE + "/notices/7/", show_headers=policy, rules=rules(
            "_make_csp_decorator.<locals>.decorator.<locals>._wrapped_sync_view", "notice", "response_for_exception",
            "get_exception_response", "log_response", "ContentSecurityPolicyMiddleware.process_response", "build_policy"))
    with block("{% csp_nonce_attr %} over a fresh request's LazyNonce: the tag draws the nonce"):
        do('request = WSGIRequest(environ("GET", "https://harbour.example/berths/"))')
        do("ContentSecurityPolicyMiddleware(lambda request: None).process_request(request)")
        do("nonce = request._csp_nonce")
        ask("bool(nonce)")
        with recorded(rules("csp", "nonce_attr", "generate_nonce")):
            do('html = engines["django"].from_string("<script {% csp_nonce_attr %}></script>").render(request=request)')
        ask("html")
        ask("bool(nonce)")
        ask('engines["django"].from_string("<script {% csp_nonce_attr %}></script>").render()')
    with block("build_policy over a fuller policy than the harbour's, before and after the nonce is read"):
        do(f"config = {FULLER}")
        do("nonce = LazyNonce()")
        ask("bool(nonce)")
        ask("build_policy(config, nonce)")
        ask("str(nonce)")
        ask("bool(nonce)")
        ask("build_policy(config, nonce)")
        ask("build_policy(config)")
    with block("POST https://harbour.example/berths/ refused, with TEMPLATES given a 403_csrf.html of the project's, "
               "the form with no token: what csrf_failure renders it with"):
        with override_settings(TEMPLATES=templates({"403_csrf.html": PROJECT_403})):
            step(f"the project's 403_csrf.html: {PROJECT_403!r}")
            browser = Browser()
            browser.given_page(HANDLER)
            browser.send(HANDLER, "POST", SITE + "/berths/", form={"ship": "Endeavour"}, show_headers=policy, body="all",
                         rules=rules("csrf_failure", "get_template", "csp", "nonce_attr", "generate_nonce"))


def block_key_changed() -> None:
    no_fallback = 'changed = override_settings(SECRET_KEY=NEW_KEY); changed.enable()'
    with_fallback = 'changed = override_settings(SECRET_KEY=NEW_KEY, SECRET_KEY_FALLBACKS=[HARBOUR_KEY]); changed.enable()'
    with block("loads after a key change: with no fallback, and with the old key as the fallback"):
        do('s = signing.dumps({"berth": 4}, salt="harbour.berths")')
        for change in (no_fallback, with_fallback):
            do(change)
            ask('signing.loads(s, salt="harbour.berths")')
            do("changed.disable()")
    with block("get_signed_cookie after a key change: with no fallback, and with the old key as the fallback"):
        do('response = HttpResponse(); response.set_signed_cookie("berth", "4", salt="harbour")')
        ask('response.cookies["berth"].value')
        do('request = WSGIRequest(environ("GET", "https://harbour.example/berths/", headers={"Cookie": "berth=" + response.cookies["berth"].value}))')
        ask('request.get_signed_cookie("berth", salt="harbour")')
        do(no_fallback)
        with recorded(rules("_unsign_cookie", "get_cookie_signer", "Signer.unsign")):
            do('request.get_signed_cookie("berth", salt="harbour")')
        ask('request.get_signed_cookie("berth", default=None, salt="harbour")')
        do("changed.disable()")
        do(with_fallback)
        ask('request.get_signed_cookie("berth", salt="harbour")')
        do("changed.disable()")
    with block("CookieStorage's messages cookie after a key change: with no fallback, and with the old key as the fallback"):
        do('storage = CookieStorage(WSGIRequest(environ("GET", "https://harbour.example/berths/")))')
        do('storage.add(constants.INFO, "Berth 4 is yours."); response = HttpResponse(); storage.update(response)')
        do('cookie = "messages=" + response.cookies["messages"].value')
        ask("cookie")
        for change in (no_fallback, with_fallback):
            do(change)
            do('storage = CookieStorage(WSGIRequest(environ("GET", "https://harbour.example/berths/", headers={"Cookie": cookie})))')
            if change is no_fallback:
                ask("len(storage)")  # decodes the cookie without iterating: iterating would mark the storage used itself
                ask("storage.used")
                do("response = HttpResponse(); storage.update(response)")
                ask('response.cookies["messages"].OutputString()')
            else:
                ask("list(storage)")
            do("changed.disable()")
    with block("salted_hmac: one value under two salts, an algorithm hashlib lacks, and none"):
        ask('salted_hmac("harbour.invoices", "invoice 112", algorithm="sha256").hexdigest()')
        ask('salted_hmac("harbour.berths", "invoice 112", algorithm="sha256").hexdigest()')
        ask('salted_hmac("harbour.berths", "invoice 112", algorithm="sha257")')
        ask('salted_hmac("harbour.berths", "invoice 112").hexdigest()', warned=True)
        ask('signing.base64_hmac("harbour.berths", "invoice 112", HARBOUR_KEY)', warned=True)


class OfficeSecurityMiddleware(SecurityMiddleware):
    """A subclass of SecurityMiddleware of the script's own, for one block of the checks."""


def check_command(title: str, args: tuple = ("--deploy", "--tag", "security"), **changes) -> None:
    """Run the check command by call_command, without colour, and write down what it writes, a
    line to a line, on the stream it writes it to, or the exception that left call_command."""
    from django.core.management import call_command
    with block(title):
        with override_settings(**changes):
            out, err = io.StringIO(), io.StringIO()
            note(f"$ python manage.py check {' '.join(args)}")
            with recorded(rules("CheckRegistry.run_checks", "check_csrf_failure_view", "get_callable")
                          if "CSRF_FAILURE_VIEW" in changes else {}):
                try:
                    call_command("check", *args, no_color=True, stdout=out, stderr=err)
                except Exception as raised:
                    flush()
                    note(f"call_command raises {type(raised).__name__}, its message being:")
                    for line in str(raised).splitlines():
                        note(f"  | {line}".rstrip())
            for stream, text in (("stdout", out.getvalue()), ("stderr", err.getvalue())):
                for line in text.splitlines():
                    note(f"{stream} | {line}".rstrip())


def block_checks() -> None:
    check_command("check --deploy --tag security, under the harbour's settings")
    check_command("SECURE_HSTS_SECONDS = 0: check --deploy --tag security", SECURE_HSTS_SECONDS=0)
    check_command("CSRF_COOKIE_SECURE = 1: check --deploy --tag security", CSRF_COOKIE_SECURE=1)
    check_command('MIDDLEWARE with "__main__.OfficeSecurityMiddleware", a subclass of SecurityMiddleware, in its place: '
                  "check --deploy --tag security", MIDDLEWARE=["__main__.OfficeSecurityMiddleware", *HARBOUR_MIDDLEWARE[1:]])
    check_command('CSRF_FAILURE_VIEW = "django.views.csrf.no_such_view", a module that imports and lacks the name: '
                  "check --deploy --tag security", CSRF_FAILURE_VIEW="django.views.csrf.no_such_view")
    check_command("SECURE_CSP = \"default-src 'self'\", a string: check --tag security, without --deploy",
                  ("--tag", "security"), SECURE_CSP="default-src 'self'")


def run_part(name: str) -> None:
    """A part in an interpreter of its own: this script, run with the part's name."""
    sys.stdout.flush()
    done = subprocess.run([sys.executable, __file__, name], capture_output=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if done.returncode:
        sys.exit(done.stderr)
    sys.stdout.write(done.stdout)


PART_TITLE = ("in an interpreter of its own, with django.contrib.auth, contenttypes and sessions installed, sessions in the database, "
              "and SessionMiddleware and AuthenticationMiddleware in the chain")


def part_login() -> None:
    with block(f"login rotates the CSRF secret, {PART_TITLE}: a form rendered before the login is refused after it"):
        browser = Browser()
        browser.given_page(HANDLER)
        before = browser.page
        browser.given_page(HANDLER, SITE + "/accounts/login/")
        browser.send(HANDLER, "POST", SITE + "/accounts/login/",
                     form={"csrfmiddlewaretoken": browser.token(), "username": "harbourmaster"},
                     show_headers=("Set-Cookie",), body="all", rules=rules(
                         "log_in", "login", "SessionBase.cycle_key", "rotate_token", "_add_new_csrf_cookie", "_get_new_csrf_string",
                         "CsrfViewMiddleware.process_response"))
        browser.page = before
        step("the browser goes back to the berths page it was given before the login, as after the back button, and posts its form")
        browser.send(HANDLER, "POST", SITE + "/berths/", form={"csrfmiddlewaretoken": browser.token(), "ship": "Endeavour"},
                     rules=rules("CsrfViewMiddleware.process_request", "CsrfViewMiddleware._check_token",
                                 "CsrfViewMiddleware._get_secret", "_does_token_match",
                                 "_unmask_cipher_token", "constant_time_compare", "CsrfViewMiddleware._reject",
                                 "CsrfViewMiddleware._bad_token_message", "log_response"))


NO_FALLBACK = "changed = override_settings(SECRET_KEY=NEW_KEY); changed.enable()"
WITH_FALLBACK = "changed = override_settings(SECRET_KEY=NEW_KEY, SECRET_KEY_FALLBACKS=[HARBOUR_KEY]); changed.enable()"
USERS = ("get_user", "SessionBase.decode", "SessionBase.cycle_key", "SessionBase.flush", "AbstractBaseUser._get_session_auth_hash")
# constant_time_compare written down only where get_user calls it: the comparisons of the session's hash.
BY_GET_USER = {("django.utils.crypto", "constant_time_compare"): lambda f: (
    LABELS[("django.utils.crypto", "constant_time_compare")](f) if f.f_back.f_code.co_qualname.startswith("get_user") else None)}


def key_names() -> dict:
    """The names the blocks after a key change use, besides NAMES."""
    from django.contrib.auth import get_user
    from django.contrib.auth.models import User
    from django.contrib.auth.tokens import default_token_generator
    from django.contrib.sessions.backends.cache import SessionStore as CacheStore
    from django.contrib.sessions.backends.db import SessionStore

    return dict(SessionStore=SessionStore, CacheStore=CacheStore, get_user=get_user, User=User, login=login,
                default_token_generator=default_token_generator)


# Each of the four blocks after a key change is a part of its own, so that none finds the database, the cache or the
# user as another block left them.
def part_session_data() -> None:
    with block(f"A database session's data after a key change: with no fallback, and with the old key as the fallback; {PART_TITLE}"):
        ASKING.update(key_names())
        do('store = SessionStore(); store["berth"] = 4; store.save(); key = store.session_key')
        for change in (NO_FALLBACK, WITH_FALLBACK):
            do(change)
            with recorded(rules("SessionStore.load", "SessionBase.decode", "loads")):
                do("SessionStore(key).load()")
            do("changed.disable()")


def part_get_user(kind: str, store: str) -> None:
    where = ("the database backend's" if store == "SessionStore" else
             "the cache backend's, made by the script's hand whatever SESSION_ENGINE says, over the default local-memory cache")
    with block(f"get_user over a {kind} session after a key change: with no fallback, and with the old key as the fallback; "
               f"{PART_TITLE}, the session {where}"):
        ASKING.update(key_names())
        for change in (NO_FALLBACK, WITH_FALLBACK):
            do(f'request = WSGIRequest(environ("GET", "https://harbour.example/berths/")); request.session = {store}()')
            do('login(request, User.objects.get(username="harbourmaster")); request.session.save(); key = request.session.session_key')
            do(change)
            do(f'request = WSGIRequest(environ("GET", "https://harbour.example/berths/")); request.session = {store}(key)')
            with recorded({**rules(*USERS), **BY_GET_USER}):
                do("user = get_user(request)")
            ask("user")
            ask("request.session.session_key == key")
            ask('"_auth_user_id" in request.session')
            do("changed.disable()")


def part_reset_token() -> None:
    with block(f"PasswordResetTokenGenerator.check_token after a key change: with no fallback, and with the old key as the fallback; {PART_TITLE}"):
        ASKING.update(key_names())
        do('user = User.objects.get(username="harbourmaster"); token = default_token_generator.make_token(user)')
        ask("default_token_generator.check_token(user, token)")
        for change in (NO_FALLBACK, WITH_FALLBACK):
            do(change)
            with recorded(rules("PasswordResetTokenGenerator.check_token", "PasswordResetTokenGenerator._make_token_with_timestamp")):
                do("checked = default_token_generator.check_token(user, token)")
            ask("checked")
            do("changed.disable()")


PARTS = {
    "login": part_login, "session-data": part_session_data,
    "get-user-database": lambda: part_get_user("database", "SessionStore"), "get-user-cached": lambda: part_get_user("cached", "CacheStore"),
    "reset-token": part_reset_token,
}

if __name__ == "__main__" and PART is not None:
    PARTS[PART]()

if __name__ == "__main__":
    if PART is None:
        # The commit comes from the book's pin and not from django.get_version(), which for a development version asks
        # git for a timestamp and so depends on the machine.
        with open(os.path.join(os.path.dirname(HERE), "pin.json"), encoding="utf-8") as fh:
            PIN = json.load(fh)["trees"]["django"]["commit"]
        print(f"Django {django.VERSION[0]}.{django.VERSION[1]} in development, at the commit {PIN}, and the harbour office's site\n"
              "at harbour.example, as the docstring gives it; the clock at 2026-10-12 09:00:00 UTC\n")
        block_page()
        block_accepted()
        block_refusals()
        block_redirect()
        block_get_token()
        block_signer()
        run_part("login")
        block_dumps()
        block_trusted()
        block_tokens()
        block_protect()
        block_sessions()
        block_settings_read()
        block_csp()
        block_key_changed()
        for name in ("session-data", "get-user-database", "get-user-cached", "reset-token"):
            run_part(name)
        block_checks()
