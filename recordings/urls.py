"""A recording of URL routing: a URLconf becoming a tree of resolvers and patterns, a path
resolved through that tree to a view, a name reversed to a path, and what Django keeps for a
thread while it does so.

    python recordings/urls.py > recordings/urls.txt

The chapter of the book (pages/urls.md and the pages under it) is written against this output.
It needs only the pinned Django (the project's virtual environment has it) and the small
project beside it, `museum/`: a root URLconf that includes one application's URLs twice, a
converter of its own, nine more URLconfs, each for a particular part of the recording, and
two views that are coroutines (`views_async.py`). The message catalogue that translates two
routes into Dutch is written into a temporary directory as the script starts. Run it again
after a re-pin: where the output changes, the chapter has to.

A block is one of three kinds. Where the order of calls is the point, the lines are the calls
of Django's own functions that the chapter names, nested as they were made, with the
arguments that tell them apart. What a call returned follows `->`, and `raises` names the
exception that left it: on the call's own line where nothing was written down under the
call, and otherwise on a line of its own under it. Everything between the lines ran and is
left out, and one thing more: a matcher's `match` that returned None is left out unless
something was written down under it, so a `match` in the output is one that matched or one
whose converter refused. And a function behind `functools.cache`, `lru_cache` or
`cached_property` is written down only when its body runs: where such a call is missing from
a block, the answer came out of the cache. A second kind of block puts one question to a
running Django on each line; the text before `->` is the expression that was evaluated, or,
where a few words stand there, they say of what object it was asked. In a question,
`converters_of(...)` is the script's: it writes each converter by its class. The third kind
writes down what an object holds, read by this script after Django made it.

Every request is made by the script, which is the server. Under WSGI it calls the handler
with an environ whose PATH_INFO is the path the block names, writes down start_response, joins
the body and calls close(); in the two blocks of /files/maps/ground%20floor.pdf the title says
whether it first decoded the request line's path, as wsgiref's server does. Under ASGI it runs
a coroutine of its own with asyncio.run() on the script's thread, gives the body, empty, in one
message, and then waits in receive until the handler cancels it. asyncio.run() runs that
coroutine in a copy of the script's thread's context, so nothing set in that copy reaches the
script's thread once asyncio.run() has returned. The ASGI handler runs a view that is a
plain function, and a response's close(), on a thread of asgiref's: in those blocks
the rules are watched on every thread, a call made on such a thread from the event loop ends
`[on a worker thread]` (the calls under it ran on the same thread), and a coroutine that is
waiting stays open, so that what runs meanwhile on the worker thread stands under it. There
`signal request_started` is written for Signal.asend.

The recording has a middleware of its own, which gives a request for the members' host the
members' URLconf: HostURLconf under WSGI, and host_urlconf_on_the_loop, a coroutine, under
ASGI. A block that installs it, or changes a setting, says so in its title. Where it is
installed in front of a URLconf that cannot be imported, the wrapper Django puts around each
layer of the chain is written by its name, `convert_exception_to_response.<locals>.inner`,
and the brackets say what it wraps. In the block of two ASGI requests at once the interleaving is the script's: before it
asks anything, each view awaits an asyncio.Event that the other request's view sets (the
museum's view waits until the members' view has started, and the members' until the museum's
has asked), so the lines are the same on every run whatever order the event loop ran the rest
in; only the views' questions and the server's answers are written down.

Nothing of Django's is patched or replaced. The blocks after those of get_callable() come last
because they change, in place, the converters of matchers that URLconfs of earlier blocks
share, and that is not put back.

    RECORD_EVERYTHING=1 python recordings/urls.py     every call in the chapter's modules
"""
import os
import sys
import weakref

HERE = os.path.dirname(os.path.abspath(__file__))
# `museum` imports from this directory, as it would from a project's. The directory goes last
# on the path and not first, where Python puts a script's own: `http.py` in it has the name of
# a package of the standard library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]

import asyncio  # noqa: E402
import dis  # noqa: E402
import io  # noqa: E402
import pickle  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = bool(os.environ.get("RECORD_EVERYTHING"))


def catalogue(messages: dict) -> bytes:
    """A compiled message catalogue, the file `msgfmt` writes: a header, two tables of
    (length, offset), the original strings in order, then their translations."""
    messages = {"": "Content-Type: text/plain; charset=UTF-8\n", **messages}
    originals = sorted(messages)
    strings = [o.encode() for o in originals] + [messages[o].encode() for o in originals]
    count = len(originals)
    start = 28 + 16 * count
    table, data = b"", b""
    for one in strings:
        table += struct.pack("<II", len(one), start + len(data))
        data += one + b"\0"
    return struct.pack("<IIIIIII", 0x950412DE, 0, count, 28, 28 + 8 * count, 0, 0) + table + data


LOCALE = tempfile.mkdtemp()
os.makedirs(os.path.join(LOCALE, "nl", "LC_MESSAGES"))
with open(os.path.join(LOCALE, "nl", "LC_MESSAGES", "django.mo"), "wb") as f:
    f.write(catalogue({"opening-hours/": "openingstijden/", "visits/<int:year>/": "bezoeken/<int:jaar>/"}))

settings.configure(
    DEBUG=False,
    SECRET_KEY="recording",
    ROOT_URLCONF="museum.urls",
    ALLOWED_HOSTS=["museum.example", "members.museum.example"],
    MIDDLEWARE=[],
    TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates"}],
    USE_I18N=True,
    LANGUAGE_CODE="en",
    LANGUAGES=[("en", "English"), ("nl", "Dutch")],
    LOCALE_PATHS=[LOCALE],
)
django.setup()

from django.conf.urls.i18n import i18n_patterns, is_language_prefix_patterns_used  # noqa: E402
from django.core import checks, signals  # noqa: E402
from django.core.handlers import asgi, wsgi  # noqa: E402
from django.core.handlers.asgi import ASGIHandler  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.template import engines  # noqa: E402
from django.urls import (  # noqa: E402
    NoReverseMatch, Resolver404, URLPattern, URLResolver, clear_url_caches, get_resolver, get_script_prefix,
    get_urlconf, include, is_valid_path, path, re_path, resolve, reverse, reverse_lazy, set_script_prefix,
    set_urlconf, translate_url,
)
from django.urls.resolvers import LocalePrefixPattern, RegexPattern, RoutePattern, _get_cached_resolver, get_ns_resolver  # noqa: E402
from django.urls.utils import extract_views_from_urlpatterns, get_callable, simplify_regex  # noqa: E402
from django.utils import translation  # noqa: E402
from django.utils.regex_helper import normalize  # noqa: E402

LINES = []
STACK = []  # the watched frames open at this moment: the depth of the next line
AT = {}  # where in LINES the line of each open watched call is, by the frame
SEEN = {}  # generator frames already written down: a generator is entered once per value
PENDING = []  # the watched call that has just returned: (frame, depth, its line, what to say of its value, the value)
RAISED = []  # exceptions already written down, at the innermost watched call they left: the objects, so that none is mistaken for a later one
LEFT_OUT = object()  # what a rule answers for a call that is not to be written down after all


def flush() -> None:
    """Say what the call that has just returned gave back, if that is to be said: on the
    call's own line where nothing was written under it, and on a line of its own otherwise."""
    while PENDING:
        frame, depth, at, after, value = PENDING.pop(0)
        said = after(frame, value) if after else None
        alone = at == len(LINES) - 1
        if said is LEFT_OUT:
            if alone:
                LINES.pop()
            else:
                LINES.append("  " * depth + "-> None")
        elif said is not None:
            if alone:
                LINES[at] += f"  ->  {said}"
            else:
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
    AT.clear()
    SEEN.clear()
    RAISED.clear()
    THREAD_OF.clear()


class doing:
    """`with doing("the script reads resolver.url_patterns"):` writes the line down and nests
    under it whatever Django does in the block."""

    def __init__(self, what: str):
        self.line = what

    def __enter__(self):
        note(self.line)
        STACK.append(self)

    def __exit__(self, *exc):
        flush()
        while STACK and STACK[-1] is not self:
            STACK.pop()
        STACK.pop()


# ---------------------------------------------------------------------------------------------
# How things are named in the output. Nothing is written that differs between machines or
# runs: no address in memory, no path on disk.

def named(view) -> str:
    """A view by its module's last name and its own: views.room."""
    view = getattr(view, "view_class", view)
    module = getattr(view, "__module__", "") or ""
    return f"{module.rsplit('.', 1)[-1]}.{getattr(view, '__name__', type(view).__name__)}"


MADE_FOR_A_NAMESPACE = []  # (resolver, what to call it): the two resolvers each call of get_ns_resolver made


def which(resolver) -> str:
    """A resolver, by what tells it apart: its URLconf's name where it has one, and its own
    route otherwise."""
    if isinstance(resolver.urlconf_name, str):
        return "the root resolver" if resolver.urlconf_name == settings.ROOT_URLCONF else f"the root resolver of {resolver.urlconf_name}"
    for made_one, said in MADE_FOR_A_NAMESPACE:
        if made_one is resolver:
            return said
    if isinstance(resolver.pattern, RegexPattern) and str(resolver.pattern) == "^/":
        return "the root resolver of the URLconf given"
    return repr(str(resolver.pattern))


def converters_of(converters: dict) -> str:
    return "{" + ", ".join(f"{name!r}: {type(c).__name__}" for name, c in converters.items()) + "}"


def match_said(match) -> str:
    said = [named(match.func)]
    if match.args:
        said.append(f"args={match.args!r}")
    said.append(f"kwargs={match.kwargs!r}")
    said.append(f"namespaces={match.namespaces!r}")
    said.append(f"route={match.route!r}")
    return f"ResolverMatch({', '.join(said)})"


def tried_said(tried) -> list:
    """The list of what was tried: each entry is the chain of resolvers down to a pattern."""
    return [" > ".join(repr(str(p.pattern)) for p in chain) for chain in tried]


def urlconf_said(urlconf) -> str:
    if isinstance(urlconf, str):
        return repr(urlconf)
    if hasattr(urlconf, "__name__"):
        return f"the module {urlconf.__name__}"
    return f"a {type(urlconf).__name__} of {len(urlconf)} {'entry' if len(urlconf) == 1 else 'entries'}"


# ---------------------------------------------------------------------------------------------
# What to write down, and how to say it. A rule is given the frame at the moment of the call
# and returns the line, or None for a call not to write down.

def cls_of(frame) -> str:
    return type(frame.f_locals["self"]).__name__


def plain(frame) -> str:
    return frame.f_code.co_qualname


def on(frame) -> str:
    """A method by the class that declares it, and the class of the object when that differs."""
    declared = frame.f_code.co_qualname
    actual = cls_of(frame)
    return declared if declared.startswith(actual + ".") else f"{declared}  ({actual})"


def with_arg(name: str):
    def label(frame):
        return f"{frame.f_code.co_qualname}({frame.f_locals[name]!r})"
    return label


def of_resolver(frame) -> str:
    return f"{frame.f_code.co_qualname}  ({which(frame.f_locals['self'])})"


def imported(frame) -> str:
    return f"import {frame.f_globals['__name__']}"


def signal_sent(frame):
    signal = frame.f_locals["self"]
    for name in ("request_started", "request_finished"):
        if getattr(signals, name) is signal:
            return f"signal {name}"
    return None


def path_called(frame) -> str:
    f = frame.f_locals
    view = f["view"]
    if isinstance(view, (list, tuple)):
        given = "what include returned" if len(view) == 3 else f"a {type(view).__name__} of {len(view)}"
    else:
        given = named(view)
    said = [repr(f["route"]), given]
    if f["kwargs"] is not None:
        said.append(repr(f["kwargs"]))
    if f["name"] is not None:
        said.append(f"name={f['name']!r}")
    return f"{'path' if f['Pattern'] is RoutePattern else 're_path'}({', '.join(said)})"


def include_called(frame) -> str:
    f = frame.f_locals
    arg = f["arg"]
    if isinstance(arg, tuple):
        given = f"({urlconf_said(arg[0])}, {arg[1]!r})"
    else:
        given = urlconf_said(arg)
    return f"include({given}" + (f", namespace={f['namespace']!r})" if f["namespace"] else ")")


def included(frame, value) -> str:
    urlconf, app_name, namespace = value
    return f"({urlconf_said(urlconf)}, {app_name!r}, {namespace!r})"


def made(frame, value) -> str:
    if isinstance(value, URLResolver):
        return (f"a URLResolver: app_name {value.app_name!r}, namespace {value.namespace!r}, "
                f"default_kwargs {value.default_kwargs!r}")
    return f"a URLPattern: name {value.name!r}, default_args {value.default_args!r}"


def resolver_made(frame, value) -> str:
    return f"a URLResolver: pattern {str(value.pattern)!r}, urlconf_name {urlconf_said(value.urlconf_name)}"


def route_compiled(frame) -> str:
    return f"_route_to_regex({frame.f_locals['route']!r}, is_endpoint={frame.f_locals['is_endpoint']})"


def get_resolver_called(frame) -> str:
    urlconf = frame.f_locals["urlconf"]
    return "get_resolver()" if urlconf is None else f"get_resolver({urlconf_said(urlconf)})"


def resolve_called(frame) -> str:
    urlconf = frame.f_locals["urlconf"]
    return f"resolve({str(frame.f_locals['path'])!r}" + (")" if urlconf is None else f", urlconf={urlconf_said(urlconf)})")


def resolver_resolve(frame) -> str:
    return f"URLResolver.resolve({str(frame.f_locals['path'])!r})  ({which(frame.f_locals['self'])})"


def root_resolve(frame):
    """The same, written down for a resolver that has a URLconf's name and for no other."""
    resolver = frame.f_locals["self"]
    if not isinstance(resolver.urlconf_name, str):
        return None
    return f"URLResolver.resolve({str(frame.f_locals['path'])!r})  ({which(resolver)})"


def pattern_resolve(frame) -> str:
    return f"URLPattern.resolve({frame.f_locals['path']!r})  ({str(frame.f_locals['self'].pattern)!r})"


def matched(frame, value):
    return LEFT_OUT if value is None else repr(value)


def resolved(frame, value):
    return "None" if value is None else match_said(value)


def view_called(frame) -> str:
    f = frame.f_locals
    given = ", ".join(f"{name}={f[name]!r}" for name in frame.f_code.co_varnames[1:frame.f_code.co_argcount])
    return f"views.{frame.f_code.co_name}(request{', ' + given if given else ''})"


def reverse_called(frame) -> str:
    f = frame.f_locals
    said = [named(f["viewname"]) if callable(f["viewname"]) else repr(f["viewname"])]
    if f["urlconf"] is not None:
        said.append(f"urlconf={urlconf_said(f['urlconf'])}")
    for name in ("args", "kwargs", "current_app", "query", "fragment"):
        if f[name]:
            said.append(f"{name}={f[name]!r}")
    return f"reverse({', '.join(said)})"


def reverse_with_prefix(frame) -> str:
    f = frame.f_locals
    view = named(f["lookup_view"]) if callable(f["lookup_view"]) else repr(f["lookup_view"])
    said = [view, repr(f["_prefix"]), *map(repr, f["args"]), *(f"{k}={v!r}" for k, v in f["kwargs"].items())]
    return f"URLResolver._reverse_with_prefix({', '.join(said)})  ({which(f['self'])})"


def ns_resolver(frame) -> str:
    f = frame.f_locals
    return (f"get_ns_resolver({f['ns_pattern']!r}, the resolver of {str(f['resolver'].pattern)!r}, "
            f"({', '.join(f'({name!r}, {type(c).__name__})' for name, c in f['converters'])}{',' if len(f['converters']) == 1 else ''}))")


def ns_resolver_made(frame, value) -> str:
    inner = value.url_patterns[0]
    MADE_FOR_A_NAMESPACE.append((value, "a resolver made for the namespace"))
    MADE_FOR_A_NAMESPACE.append((inner, f"the resolver made for {str(inner.pattern)!r}"))
    return (f"a URLResolver {str(value.pattern)!r} whose one entry is a URLResolver with the "
            f"{type(inner.pattern).__name__} {str(inner.pattern)!r} and converters {converters_of(inner.pattern.converters)}")


def is_valid(frame) -> str:
    return f"is_valid_path({frame.f_locals['path']!r}, {frame.f_locals['urlconf']!r})"


def valid(frame, value) -> str:
    return "False" if value is False else "the ResolverMatch"


def error_handler(frame) -> str:
    return f"URLResolver.resolve_error_handler({frame.f_locals['view_type']!r})  ({which(frame.f_locals['self'])})"


def hook(frame) -> str:
    label = on(frame)
    if frame.f_code.co_name == "process_response":
        label += f"  (given a {frame.f_locals['response'].status_code})"
    return label


def responded(frame, value):
    if value is None:
        return "None"
    location = value.headers.get("Location")
    return f"a {value.status_code}" + (f", Location {location!r}" if location else "")


CONVERTERS = {
    ("django.urls.converters", "IntConverter.to_python"): with_arg("value"),
    ("django.urls.converters", "StringConverter.to_python"): lambda f: on_converter(f),
    ("django.urls.converters", "UUIDConverter.to_python"): with_arg("value"),
    ("museum.converters", "MonthConverter.to_python"): with_arg("value"),
    ("django.urls.converters", "IntConverter.to_url"): with_arg("value"),
    ("django.urls.converters", "StringConverter.to_url"): lambda f: on_converter(f),
    ("django.urls.converters", "UUIDConverter.to_url"): with_arg("value"),
    ("museum.converters", "MonthConverter.to_url"): with_arg("value"),
}


def on_converter(frame) -> str:
    """StringConverter's two methods serve its subclasses: the method by the class that
    declares it, and in brackets the class of the converter when that is another."""
    declared = f"{frame.f_code.co_qualname}({frame.f_locals['value']!r})"
    actual = cls_of(frame)
    return declared if actual == "StringConverter" else f"{declared}  ({actual})"


VIEWS = {("museum.views", name): view_called for name in (
    "entrance", "tickets", "wing", "room", "track", "shop", "item", "plan", "download", "hours", "members")}

# The URLconf is imported and the tree is made.
BUILD = {
    ("django.urls.resolvers", "get_resolver"): get_resolver_called,
    ("django.urls.resolvers", "_get_cached_resolver"): with_arg("urlconf"),
    ("django.urls.resolvers", "URLResolver.url_patterns"): of_resolver,
    ("django.urls.resolvers", "URLResolver.urlconf_module"): of_resolver,
    ("museum.urls", "<module>"): imported,
    ("museum.gallery.urls", "<module>"): imported,
    ("museum.views", "<module>"): imported,
    ("museum.converters", "<module>"): imported,
    ("django.urls.converters", "register_converter"): lambda f: f"register_converter({f.f_locals['converter'].__name__}, {f.f_locals['type_name']!r})",
    ("django.urls.conf", "_path"): path_called,
    ("django.urls.conf", "include"): include_called,
}

# A route is expanded into a regular expression as path() is called.
EXPAND = {
    ("django.urls.conf", "_path"): path_called,
    ("django.urls.resolvers", "_route_to_regex"): route_compiled,
}

# A path is resolved: every resolver and pattern asked, in order.
RESOLVE = {
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.base", "resolve"): resolve_called,
    ("django.urls.resolvers", "get_resolver"): get_resolver_called,
    ("django.urls.resolvers", "URLResolver.resolve"): resolver_resolve,
    ("django.urls.resolvers", "URLPattern.resolve"): pattern_resolve,
    ("django.urls.resolvers", "RegexPattern.match"): with_arg("path"),
    ("django.urls.resolvers", "RoutePattern.match"): with_arg("path"),
    ("django.urls.resolvers", "LocalePrefixPattern.match"): with_arg("path"),
    ("django.core.handlers.exception", "response_for_exception"): plain,
    ("django.urls.resolvers", "URLResolver.resolve_error_handler"): error_handler,
    **CONVERTERS,
    **VIEWS,
}

# A request from the server's call to its close(): what is set for the thread, and each
# resolution of a whole path, without the calls inside it.
REQUEST = {
    ("django.core.handlers.wsgi", "WSGIHandler.__call__"): lambda f: "WSGIHandler.__call__(environ, start_response)",
    ("django.urls.base", "set_script_prefix"): with_arg("prefix"),
    ("django.urls.base", "set_urlconf"): with_arg("urlconf_name"),
    ("django.dispatch.dispatcher", "Signal.send"): signal_sent,
    ("django.core.handlers.base", "BaseHandler.get_response"): plain,
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.resolvers", "get_resolver"): get_resolver_called,
    ("django.urls.resolvers", "URLResolver.resolve"): root_resolve,
    ("django.urls.base", "is_valid_path"): is_valid,
    ("django.middleware.common", "CommonMiddleware.process_response"): hook,
    ("django.middleware.common", "CommonMiddleware.should_redirect_with_slash"): plain,
    ("django.middleware.locale", "LocaleMiddleware.process_request"): hook,
    ("django.middleware.locale", "LocaleMiddleware.process_response"): hook,
    ("django.conf.urls.i18n", "is_language_prefix_patterns_used"): with_arg("urlconf"),
    ("django.utils.translation.trans_real", "activate"): with_arg("language"),
    ("__main__", "HostURLconf.__call__"): lambda f: "HostURLconf.__call__, the recording's middleware",
    ("django.http.response", "HttpResponseBase.close"): on,
    ("django.core.handlers.base", "reset_urlconf"): plain,
    **VIEWS,
}

# A name is reversed.
REVERSE = {
    ("django.urls.base", "reverse"): reverse_called,
    ("django.urls.resolvers", "get_resolver"): get_resolver_called,
    ("django.urls.resolvers", "get_ns_resolver"): ns_resolver,
    ("django.urls.resolvers", "URLResolver._reverse_with_prefix"): reverse_with_prefix,
    ("django.urls.resolvers", "URLResolver._populate"): of_resolver,
    **CONVERTERS,
}

RULES = {}  # the set in force

# (module, qualname) -> what to say of the value a call returned, or None to say nothing.
AFTER = {
    ("django.urls.resolvers", "_get_cached_resolver"): resolver_made,
    ("django.urls.conf", "_path"): made,
    ("django.urls.conf", "include"): included,
    ("django.urls.resolvers", "_route_to_regex"): lambda f, v: f"({v[0]!r}, {converters_of(v[1])})",
    ("django.urls.resolvers", "URLResolver.resolve"): resolved,
    ("django.urls.resolvers", "URLPattern.resolve"): resolved,
    ("django.urls.base", "resolve"): resolved,
    ("django.urls.resolvers", "RegexPattern.match"): matched,
    ("django.urls.resolvers", "RoutePattern.match"): matched,
    ("django.urls.resolvers", "LocalePrefixPattern.match"): matched,
    ("django.urls.base", "is_valid_path"): valid,
    ("django.middleware.common", "CommonMiddleware.should_redirect_with_slash"): lambda f, v: repr(v),
    ("django.middleware.common", "CommonMiddleware.process_response"): responded,
    ("django.middleware.locale", "LocaleMiddleware.process_response"): responded,
    ("django.conf.urls.i18n", "is_language_prefix_patterns_used"): lambda f, v: repr(v),
    ("django.urls.base", "reverse"): lambda f, v: repr(v),
    ("django.urls.resolvers", "URLResolver._reverse_with_prefix"): lambda f, v: repr(v),
    ("django.urls.resolvers", "URLResolver.resolve_error_handler"): lambda f, v: named(v),
    ("django.urls.resolvers", "get_ns_resolver"): ns_resolver_made,
    ("django.middleware.common", "CommonMiddleware.process_request"): responded,
    ("django.urls.utils", "get_callable"): lambda f, v: named(v),
    **{key: (lambda f, v: repr(v)) for key in CONVERTERS},
}

OURS = ("django.urls", "django.conf.urls", "django.utils.regex_helper", "museum")


def find(module: str, qualname: str):
    label = RULES.get((module, qualname))
    if label is None and EVERYTHING and module.startswith(OURS) and "<" not in qualname:
        return plain
    return label


GENERATOR, COROUTINE = 0x20, 0x80  # the flags of a code object that say what kind of function it is
YIELD_VALUE = dis.opmap["YIELD_VALUE"]
MAIN = threading.get_ident()  # the script's thread, on which asyncio.run() runs the event loop
THREAD_OF = {}  # the thread each watched call open at this moment was made on, by its frame


def profile(frame, event, arg):
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), code.co_qualname)
        if label is None:
            return
        if code.co_flags & (GENERATOR | COROUTINE):  # every resumption is a call event
            known = SEEN.get(id(frame))
            if known is not None and known() is frame.f_generator:
                if code.co_flags & GENERATOR:
                    STACK.append(frame)
                return  # a coroutine was kept open while it waited
            SEEN[id(frame)] = weakref.ref(frame.f_generator)  # by its generator, weakly held: a frame's address is used again once its generator is gone
        flush()  # what the call before this one returned is said first: a label may depend on it
        text = label(frame)
        if text is None:
            return
        here = threading.get_ident()
        above = next((THREAD_OF[id(f)] for f in reversed(STACK) if id(f) in THREAD_OF), MAIN)
        if here != MAIN and here != above:  # said of the call that crossed to the thread, not of the calls under it
            text += "  [on a worker thread]"
        note(text)
        AT[id(frame)] = len(LINES) - 1
        THREAD_OF[id(frame)] = here
        STACK.append(frame)
    elif event == "return":
        if code.co_flags & COROUTINE and code.co_code[frame.f_lasti] == YIELD_VALUE:
            return  # a coroutine waits and stays open: what runs meanwhile on a worker thread stands under it
        if STACK and STACK[-1] is frame:
            flush()
            after = None if code.co_flags & (GENERATOR | COROUTINE) else AFTER.get((frame.f_globals.get("__name__", ""), code.co_qualname))
            PENDING.append((frame, len(STACK), AT.pop(id(frame), -1), after, arg))
            THREAD_OF.pop(id(frame), None)
            STACK.pop()


def unwinding(code, offset, exception):
    """An exception is leaving a function. The profile hook has just been told that the
    function returned None: where it was a watched call, take that back, and say what was
    raised, once, at the innermost watched call the exception leaves."""
    frame = sys._getframe(1)
    if PENDING and PENDING[-1][0] is frame:
        _, depth, at, _, _ = PENDING.pop()
        if not any(e is exception for e in RAISED) and not isinstance(exception, (StopIteration, GeneratorExit)):
            RAISED.append(exception)
            if at == len(LINES) - 1:
                LINES[at] += f"  raises {type(exception).__name__}"
            else:
                LINES.append("  " * depth + f"raises {type(exception).__name__}")


UNWINDING = unwinding.__code__
MONITOR = sys.monitoring.PROFILER_ID
sys.monitoring.use_tool_id(MONITOR, "recordings/urls.py")
sys.monitoring.register_callback(MONITOR, sys.monitoring.events.PY_UNWIND, unwinding)
sys.monitoring.set_events(MONITOR, sys.monitoring.events.PY_UNWIND)


class recorded:
    """`with recorded(RESOLVE):` writes down, of what runs in the block, the calls those
    rules name."""

    def __init__(self, rules: dict):
        self.rules = rules

    def __enter__(self):
        global RULES
        RULES = self.rules
        sys.setprofile(profile)

    def __exit__(self, *exc):
        sys.setprofile(None)
        flush()


class recorded_on_every_thread(recorded):
    """The same, on the script's thread and on every thread started while it is in force: the
    ASGI handler runs a view that is a plain function, and a response's close, on a thread of
    asgiref's."""

    def __enter__(self):
        global RULES
        RULES = self.rules
        threading.setprofile_all_threads(profile)

    def __exit__(self, *exc):
        threading.setprofile_all_threads(None)
        flush()


ASKING = {}  # the names an asked expression may use


def ask(expression: str, brief: bool = False, show_as: str = "") -> None:
    """One question and its answer, on one line. The question is evaluated as it is written
    down, so the line cannot say one thing and the script do another. A brief answer names an
    exception and leaves out its message."""
    watching = sys.getprofile()
    sys.setprofile(None)  # a question is its answer and nothing else: no calls are written down under it
    try:
        value = eval(expression, ASKING)
        said = value if isinstance(value, Said) else repr(value)
    except Exception as raised:
        said = f"raises {type(raised).__name__}" + ("" if brief else f": {raised}")
    note(f"{show_as or expression}  ->  {said}")
    sys.setprofile(watching)


class Said(str):
    """An answer already put into words, to be written as it is and not as a string's repr."""


class under:
    """`with under("with the language nl active"):` writes that line and sets the questions
    asked in the block in under it."""

    def __init__(self, heading: str):
        self.heading = heading

    def __enter__(self):
        note(self.heading)
        STACK.append(self)

    def __exit__(self, *exc):
        flush()
        STACK.pop()


# ---------------------------------------------------------------------------------------------
# The server's part.

def environ(url: str, method: str = "GET", **more) -> dict:
    path_info, _, query = url.partition("?")
    made_ = {
        "REQUEST_METHOD": method, "PATH_INFO": path_info, "QUERY_STRING": query, "SCRIPT_NAME": "",
        "SERVER_NAME": "museum.example", "SERVER_PORT": "80", "SERVER_PROTOCOL": "HTTP/1.1",
        "HTTP_HOST": "museum.example", "wsgi.url_scheme": "http", "wsgi.input": io.BytesIO(b""),
    }
    made_.update(more)
    return made_


def serve(handler, env: dict, rules: dict) -> None:
    """Call the handler as a WSGI server does: start the response, send the body, close it."""
    def start_response(status, headers):
        location = dict(headers).get("Location")
        note(f'start_response("{status}", headers)' + (f", with Location: {location}" if location else ""))

    with recorded(rules):
        result = handler(env, start_response)
        body = b"".join(result)
        note(f"the server sends the body: {body.decode()!r}" if len(body) < 80 else f"the server sends the body, {len(body)} bytes")
        note("the server calls close() on what it was given")
        result.close()


class HostURLconf:
    """The recording's one middleware of its own: a request for the members' host is given
    the members' URLconf."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.get_host().startswith("members."):
            request.urlconf = "museum.urls_members"
            note('request.urlconf = "museum.urls_members"')
            ask("get_urlconf()", show_as="and then, still in the middleware: get_urlconf()")
        return self.get_response(request)


def asgi_scope(url: str, root_path: str = "", host: str = "museum.example") -> dict:
    scope = {"type": "http", "method": "GET", "path": url, "query_string": b"", "scheme": "http",
             "server": (host, 80), "headers": [(b"host", host.encode())]}
    if root_path:
        scope["root_path"] = root_path
    return scope


async def asgi_call(handler, scope: dict, said: bool = True) -> list:
    """Call the handler as an ASGI server does, from a coroutine on the event loop: the body,
    empty, in one message, and then a receive that waits until the handler cancels it. With
    said, the server writes down the body it gives and each message it is sent."""
    waiting = [{"type": "http.request", "body": b"", "more_body": False}]
    never = asyncio.Event()
    sent = []

    async def receive():
        if waiting:
            if said:
                note("the server's receive returns http.request, with no body and more_body False")
            return waiting.pop(0)
        await never.wait()  # the client stays: the handler's listener waits until it is cancelled

    async def send(message):
        sent.append(message)
        if said and message["type"] == "http.response.start":
            note(f"the server is sent http.response.start, status {message['status']}")
        elif said:
            note(f"the server is sent http.response.body: {message.get('body', b'').decode()!r}")

    await handler(scope, receive, send)
    return sent


print("Django", django.get_version(), "and the project museum: ROOT_URLCONF = 'museum.urls', no middleware unless a block says so\n")

plain_handler = WSGIHandler()

# ---------------------------------------------------------------------------------------------
# The URLconf becomes a tree.

note(f"before anything asks: 'museum.urls' in sys.modules is {'museum.urls' in sys.modules}")
with recorded(BUILD):
    with doing("the script calls get_resolver()"):
        root = get_resolver()
    note(f"'museum.urls' in sys.modules is {'museum.urls' in sys.modules}")
    with doing("the script reads the resolver's url_patterns"):
        root.url_patterns
    note(f"'museum.urls' in sys.modules is {'museum.urls' in sys.modules}")
    with doing("the script calls get_resolver() and reads url_patterns again"):
        get_resolver().url_patterns
show("The root URLconf is imported by the first read of the root resolver's url_patterns")


def tree(resolver, depth: int = 0, seen=None) -> None:
    seen = {} if seen is None else seen
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            said = [f"URLResolver {str(entry.pattern)!r}"]
            if entry.app_name or entry.namespace:
                said.append(f"app_name {entry.app_name!r}, namespace {entry.namespace!r}")
            if entry.default_kwargs:
                said.append(f"default_kwargs {entry.default_kwargs!r}")
            said.append(f"urlconf_name {urlconf_said(entry.urlconf_name)}")
            LINES.append("  " * depth + "; ".join(said))
            if id(entry.url_patterns) in seen:
                LINES.append("  " * (depth + 1) + f"its entries are the list under {seen[id(entry.url_patterns)]!r}: the same objects")
            else:
                seen[id(entry.url_patterns)] = str(entry.pattern)
                tree(entry, depth + 1, seen)
        else:
            said = [f"URLPattern {str(entry.pattern)!r}", f"callback {named(entry.callback)}", f"name {entry.name!r}"]
            if entry.default_args:
                said.append(f"default_args {entry.default_args!r}")
            LINES.append("  " * depth + "; ".join(said))


LINES.append(f"URLResolver {str(root.pattern)!r}; urlconf_name {urlconf_said(root.urlconf_name)}")
tree(root, 1)
show("The tree: what the root resolver holds, read from url_patterns downwards")


def compiled(resolver, done: set) -> None:
    for entry in resolver.url_patterns:
        pattern = entry.pattern
        if id(pattern) not in done:
            done.add(id(pattern))
            kind = "RoutePattern" if isinstance(pattern, RoutePattern) else "RegexPattern"
            whose = "an include's" if isinstance(entry, URLResolver) else "a view's"
            said = f"{kind} {str(pattern)!r}, {whose}  ->  regex {pattern._regex!r}"
            if pattern.converters:
                said += f", converters {converters_of(pattern.converters)}"
            LINES.append(said)
        if isinstance(entry, URLResolver):
            compiled(entry, done)


compiled(root, set())
show("The matcher of each entry in the tree, and the regular expression made from its route")

from django.urls.resolvers import _route_to_regex  # noqa: E402

ASKING.update(
    path=path, re_path=re_path, include=include, views=__import__("museum.views").views, resolve=resolve,
    reverse=reverse, reverse_lazy=reverse_lazy, normalize=normalize, get_resolver=get_resolver,
    get_script_prefix=get_script_prefix, get_urlconf=get_urlconf, is_valid_path=is_valid_path,
    translate_url=translate_url, simplify_regex=simplify_regex, get_callable=get_callable, pickle=pickle, sys=sys,
    is_language_prefix_patterns_used=is_language_prefix_patterns_used, i18n_patterns=i18n_patterns,
    _route_to_regex=_route_to_regex,
)
views = ASKING["views"]

ask("_route_to_regex.cache_info()", show_as="after the import of the URLconf: _route_to_regex.cache_info()")
with recorded(EXPAND):
    with doing('the script calls path("lifts/<int:floor>/", views.plan)'):
        path("lifts/<int:floor>/", views.plan)
    with doing("and calls it again"):
        path("lifts/<int:floor>/", views.plan)
    with doing('the script calls path("", views.entrance), a route the URLconf has already used'):
        path("", views.entrance)
    with doing('the script calls path("lifts/", include([]))'):
        path("lifts/", include([]))
show("path() turns its route into a regular expression as it is called, and the result is kept")

ask('path("lifts/<int:floor>/", views.plan).pattern.regex.pattern')
ask('path("lifts/<floor>/", views.plan).pattern.regex.pattern')
ask('type(path("lifts/<floor>/", views.plan).pattern.converters["floor"]).__name__')
ask('path("lifts/<floor:number>/", views.plan)')
ask('path("lifts/<int:floor number>/", views.plan)')
ask('path("lifts/<int:2nd>/", views.plan)')
show("What a route expands to with and without a converter named, and the routes path() refuses")

ask('type(path("tour/", views.Tour.as_view())).__name__')
ask('type(path("tour/", views.Tour)).__name__')
ask('path("tour/", views.Tour())')
ask('path("tour/", "museum.views.shop")')
ask('path("tour/", views.shop, ["guide"])')
ask('path("shop/", [path("", views.shop)])', brief=True)
show("What path() makes of the argument in the view's place")

ask('include("museum.gallery.urls")[1:]')
ask('include("museum.gallery.urls", namespace="east")[1:]')
ask('include(("museum.gallery.urls", "exhibits"))[1:]')
ask('include(([], "audio"))')
ask('include(([], "audio"), namespace="guide")')
ask('include([])')
ask('include([], namespace="guide")', brief=True)
ask('include(([], "audio", "guide"))', brief=True)
ask('include("museum.nowhere")', brief=True)
ask('include("museum.urls_languages")')
show("What include() returns: the URLconf, the application namespace and the instance namespace")

NAMED = (path("guide/", include([path("", views.shop, name="shop")]), name="guide"),)
ASKING["NAMED"] = NAMED
note('NAMED is a URLconf of one entry: path("guide/", include([path("", views.shop, name="shop")]), name="guide")')
STACK.append(None)
ask("type(NAMED[0]).__name__")
ask('hasattr(NAMED[0], "name")')
ask("NAMED[0].pattern.name")
ask('"guide" in vars(NAMED[0]).values()')
ask('"guide" in vars(NAMED[0].pattern).values()')
ask('reverse("guide", urlconf=NAMED)')
ask('reverse("shop", urlconf=NAMED)')
STACK.pop()
show("A name written beside an include(): what path() makes, and reverse() of that name")

SLASHLESS = (path("east", include("museum.gallery.urls"), {"wing": "east"}),)
ASKING["SLASHLESS"] = SLASHLESS


def found(url: str, urlconf=None, name: str = "") -> None:
    """One path resolved, on one line: the view, and what it would be called with."""
    asked = f"resolve({url!r}" + (f", urlconf={name})" if name else ")")
    try:
        match = resolve(url, urlconf=urlconf)
        note(f"{asked}  ->  {named(match.func)}, args {match.args!r}, kwargs {match.kwargs!r}")
    except Resolver404:
        note(f"{asked}  ->  raises Resolver404")


note('SLASHLESS is a URLconf of one entry: path("east", include("museum.gallery.urls"), {"wing": "east"})')
found("/east/rooms/12/", SLASHLESS, "SLASHLESS")
found("/eastrooms/12/", SLASHLESS, "SLASHLESS")
show("An include's route is matched as a prefix, and nothing puts a slash after it")


class settings_as:
    """`with settings_as(MIDDLEWARE=[...]):` sets those settings for the block and puts back
    what they were. It assigns to the settings object and sends no signal."""

    def __init__(self, **changed):
        self.changed = changed

    def __enter__(self):
        self.before = {name: getattr(settings, name) for name in self.changed}
        for name, value in self.changed.items():
            setattr(settings, name, value)

    def __exit__(self, *exc):
        for name, value in self.before.items():
            setattr(settings, name, value)


with settings_as(ROOT_URLCONF="museum.urls_early"):
    ask('resolve("/")')
    with under("afterwards"):
        ask('"museum.urls_early" in sys.modules')
        ask('"urlconf_module" in vars(get_resolver())')
        ask('hasattr(get_resolver().urlconf_module, "urlpatterns")')
        ask('resolve("/")', brief=True)
show("ROOT_URLCONF = 'museum.urls_early', a URLconf that calls reverse() above its own urlpatterns")

BROKEN = {
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.resolvers", "URLResolver.resolve"): root_resolve,
    ("django.urls.resolvers", "URLResolver.urlconf_module"): of_resolver,
    ("django.core.handlers.exception", "response_for_exception"): plain,
    ("django.core.handlers.exception", "handle_uncaught_exception"): plain,
    ("django.urls.resolvers", "URLResolver.resolve_error_handler"): error_handler,
}
with settings_as(ROOT_URLCONF="museum.urls_broken"):
    with recorded(BROKEN):
        try:
            plain_handler(environ("/"), lambda status, headers: note(f'start_response("{status}", headers)'))
        except Exception as left:
            note(f"the handler raises {type(left).__name__} to the server")
    with under("afterwards"):
        ask('"urlconf_module" in vars(get_resolver())')
        ask("get_urlconf()")
set_urlconf(None)  # no response was made, so none was closed, and nothing reset this
show("GET / when ROOT_URLCONF names a module that cannot be imported, with DEBUG = False")

BROKEN_DEBUG = {
    **BROKEN,
    ("django.views.debug", "technical_500_response"): plain,
    ("django.views.debug", "get_caller"): plain,
    ("django.urls.base", "resolve"): resolve_called,
}
with settings_as(ROOT_URLCONF="museum.urls_broken", DEBUG=True):
    with recorded(BROKEN_DEBUG):
        try:
            plain_handler(environ("/"), lambda status, headers: note(f'start_response("{status}", headers)'))
        except Exception as left:
            note(f"the handler raises {type(left).__name__} to the server")
set_urlconf(None)
show("The same request with DEBUG = True")


def wrapper_called(frame) -> str:
    """The function convert_exception_to_response returns, by what it wraps: the middleware,
    or the centre of the chain."""
    around = frame.f_locals["get_response"]
    return f"{frame.f_code.co_qualname}  (around {type(around).__name__ if isinstance(around, HostURLconf) else around.__qualname__})"


BROKEN_CHAIN = {
    **BROKEN,
    ("django.core.handlers.exception", "convert_exception_to_response.<locals>.inner"): wrapper_called,
    ("__main__", "HostURLconf.__call__"): lambda f: "HostURLconf.__call__, the recording's middleware",
}
with settings_as(MIDDLEWARE=[f"{__name__}.HostURLconf"]):
    chain_handler = WSGIHandler()
with settings_as(ROOT_URLCONF="museum.urls_broken"):
    with recorded(BROKEN_CHAIN):
        try:
            chain_handler(environ("/"), lambda status, headers: note(f'start_response("{status}", headers)'))
        except Exception as left:
            note(f"the handler raises {type(left).__name__} to the server")
set_urlconf(None)
show("GET / when ROOT_URLCONF names a module that cannot be imported, with DEBUG = False and one middleware installed, the recording's own")

# ---------------------------------------------------------------------------------------------
# A path is resolved.

serve(plain_handler, environ("/east/rooms/12/"), RESOLVE)
show("GET /east/rooms/12/: the path is resolved, entry by entry, and the view is called")

serve(plain_handler, environ("/tickets/2026/13/"), RESOLVE)
try:
    resolve("/tickets/2026/13/")
except Resolver404 as refused:
    carried = refused.args[0]
    note(f"asked again with resolve(), the root resolver raises a Resolver404 that carries one dictionary: 'path' is {carried['path']!r}, and 'tried' is")
    for chain in tried_said(carried["tried"]):
        note("  " + chain)
show("GET /tickets/2026/13/: a converter refuses, and nothing else matches")

for url in ("/east/rooms/12", "east/rooms/12/"):
    try:
        resolve(url)
    except Resolver404 as refused:
        carried = refused.args[0]
        note(f"resolve({url!r}) raises Resolver404 with {{'tried': ..., 'path': {carried['path']!r}}}, where 'tried' is"
             if "tried" in carried else f"resolve({url!r}) raises Resolver404 with {carried!r}")
        for chain in tried_said(carried.get("tried", ())):
            note("  " + chain)
show("What a Resolver404 carries: the path that was left, and each chain of entries tried")

for url in ("/", "/tickets/2026/", "/tickets/2026/03/", "/tickets/2026/3/", "/tickets/2026/13/", "/tickets/2026/\n", "/plans/2",
            "/plans/2.pdf", "/plans/2.png", "/files/maps/ground floor.pdf", "/shop/poster/", "/shop/tea towel/", "/east/",
            "/east/rooms/12/audio/intro/", "/east/rooms/12", "east/rooms/12/", "/north/rooms/12/"):
    found(url)
show("resolve(path): the view found, and what it will be called with")

from urllib.parse import unquote  # noqa: E402

ASKING["unquote"] = unquote
DECODED = {
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.resolvers", "URLResolver.resolve"): root_resolve,
    **VIEWS,
}


def path_info_asked(request) -> None:
    note(f"request.path_info  ->  {request.path_info!r}")


views.ON_VIEW.append(path_info_asked)
note("the request line's path is /files/maps/ground%20floor.pdf, and the server puts in PATH_INFO what wsgiref's server puts there:")
ask('unquote("/files/maps/ground%20floor.pdf", "iso-8859-1")')
serve(plain_handler, environ(unquote("/files/maps/ground%20floor.pdf", "iso-8859-1")), DECODED)
show("GET /files/maps/ground%20floor.pdf, the server having decoded the path into PATH_INFO as wsgiref's server does: what is resolved, and what the view is given")

LEFT_ENCODED = environ("/files/maps/ground%20floor.pdf")
note(f"the server puts the request line's path in PATH_INFO as it stands: PATH_INFO  ->  {LEFT_ENCODED['PATH_INFO']!r}")
serve(plain_handler, LEFT_ENCODED, DECODED)
views.ON_VIEW.clear()
show("The same request from a server that leaves the escape in PATH_INFO: neither the request nor the resolver decodes it")

match = resolve("/east/rooms/12/audio/intro/")
ASKING["match"] = match
note('match = resolve("/east/rooms/12/audio/intro/")')
STACK.append(None)
for attribute in ("func", "args", "kwargs", "url_name", "route", "app_names", "app_name", "namespaces", "namespace",
                  "view_name", "captured_kwargs", "extra_kwargs", "_func_path"):
    value = getattr(match, attribute)
    note(f"match.{attribute}  ->  {named(value) if attribute == 'func' else repr(value)}")
note("match.tried  ->  a list of the chains tried, the last being the one that matched:")
for chain in tried_said(match.tried):
    note("  " + chain)
view, args, kwargs = match
note(f"view, args, kwargs = match  ->  {named(view)}, {args!r}, {kwargs!r}")
ask("pickle.dumps(match)")
STACK.pop()
show("A ResolverMatch, attribute by attribute")

ENDS = (
    re_path(r"^tower/$", views.shop, name="tower"),
    re_path(r"^press/", views.shop, name="press"),
    re_path(r"cafe/$", views.shop, name="cafe"),
    re_path(r"lift/", views.shop, name="lift"),
)
note("ENDS is a URLconf of four patterns:")
note('  re_path(r"^tower/$", views.shop, name="tower")')
note('  re_path(r"^press/", views.shop, name="press")')
note('  re_path(r"cafe/$", views.shop, name="cafe")')
note('  re_path(r"lift/", views.shop, name="lift")')
for url in ("/tower/", "/tower/\n", "/press/", "/press/2026/release.pdf", "/cafe/", "/ground/cafe/", "/ground/lift/up"):
    found(url, ENDS, "ENDS")
show("Regular expressions written with re_path(): what holds a match to the start and to the end of the text")

GROUPS = (
    re_path(r"^archive/([0-9]{4})/([0-9]{2})/$", views.tickets, name="archive"),
    re_path(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$", views.tickets, name="mixed"),
    re_path(r"^draft/([0-9]+)?$", views.tickets, name="draft"),
)
note("GROUPS is a URLconf of three patterns:")
note('  re_path(r"^archive/([0-9]{4})/([0-9]{2})/$", views.tickets, name="archive")')
note('  re_path(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$", views.tickets, name="mixed")')
note('  re_path(r"^draft/([0-9]+)?$", views.tickets, name="draft")')
for url in ("/archive/2026/03/", "/mixed/2026/03/", "/draft/"):
    found(url, GROUPS, "GROUPS")
show("Regular expressions written with re_path(): which groups become the view's arguments")

OVERRIDES = (
    path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")]), {"wing": "annexe"}),
)
NESTED = (path("<slug:wing>/", include([path("<slug:wing>/", views.wing, name="wing")])),)
POSITIONAL = (
    re_path(r"^a/([0-9]+)/", include([re_path(r"^b/([0-9]+)/$", views.tickets, name="b")])),
    re_path(r"^c/([0-9]+)/", include([re_path(r"^d/([0-9]+)/$", views.tickets, {"month": 12}, name="d")])),
)
note('OVERRIDES is path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")]), {"wing": "annexe"})')
STACK.append(None)
found("/east/rooms/12/", OVERRIDES, "OVERRIDES")
STACK.pop()
note('NESTED is path("<slug:wing>/", include([path("<slug:wing>/", views.wing, name="wing")]))')
STACK.append(None)
found("/east/west/", NESTED, "NESTED")
STACK.pop()
note("POSITIONAL is a URLconf of two entries:")
note('  re_path(r"^a/([0-9]+)/", include([re_path(r"^b/([0-9]+)/$", views.tickets, name="b")]))')
note('  re_path(r"^c/([0-9]+)/", include([re_path(r"^d/([0-9]+)/$", views.tickets, {"month": 12}, name="d")]))')
STACK.append(None)
found("/a/1/b/2/", POSITIONAL, "POSITIONAL")
found("/c/1/d/2/", POSITIONAL, "POSITIONAL")
STACK.pop()
show("Arguments from several levels: which one the view gets")

CAPTURED = (path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, name="room")]), {"room": 1}),)
EACH = (path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")])),)
ASKING.update(CAPTURED=CAPTURED, EACH=EACH)
note('CAPTURED is path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, name="room")]), {"room": 1})')
STACK.append(None)
found("/east/rooms/12/", CAPTURED, "CAPTURED")
ask('resolve("/east/rooms/12/", urlconf=CAPTURED).captured_kwargs')
ask('resolve("/east/rooms/12/", urlconf=CAPTURED).extra_kwargs')
STACK.pop()
note('EACH gives the same extra argument to the line instead: path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")]))')
STACK.append(None)
found("/east/rooms/12/", EACH, "EACH")
STACK.pop()
show("An include's extra argument against a capture of the same name further down, and the same argument given to the line instead")

RETURNS = (
    path("shop/", include([path("", views.shop, name="shop"), path("<slug:item>/", views.item, name="item")])),
    path("shop/<slug:item>/closed/", views.item, name="closed"),
)
note("RETURNS is a URLconf of two entries:")
note('  path("shop/", include([path("", views.shop, name="shop"), path("<slug:item>/", views.item, name="item")]))')
note('  path("shop/<slug:item>/closed/", views.item, name="closed")')
with recorded(RESOLVE):
    with doing('the script calls resolve("/shop/poster/closed/", urlconf=RETURNS)'):
        resolve("/shop/poster/closed/", urlconf=RETURNS)
show("A path that gets into an include, matches nothing there, and is matched by a later entry")

# The resolver is asked by more than the handler. A request with CommonMiddleware in front.
SLASH = {
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.resolvers", "URLResolver.resolve"): root_resolve,
    ("django.urls.base", "is_valid_path"): is_valid,
    ("django.middleware.common", "CommonMiddleware.process_response"): hook,
    ("django.middleware.common", "CommonMiddleware.should_redirect_with_slash"): plain,
    **VIEWS,
}
with settings_as(MIDDLEWARE=["django.middleware.common.CommonMiddleware"]):
    common_handler = WSGIHandler()
serve(common_handler, environ("/east/rooms/12"), SLASH)
show("GET /east/rooms/12, with CommonMiddleware and APPEND_SLASH: the resolver is asked three times")

WWW = {**SLASH, ("django.middleware.common", "CommonMiddleware.process_request"): hook}
with settings_as(PREPEND_WWW=True):
    serve(common_handler, environ("/east/rooms/12"), WWW)
show("GET /east/rooms/12 for the host museum.example, with CommonMiddleware, APPEND_SLASH and PREPEND_WWW = True: "
     "process_request asks the resolver, and the handler does not")

with settings_as(PREPEND_WWW=False):
    serve(common_handler, environ("/east/rooms/12"), WWW)
show("The same request with PREPEND_WWW = False, the default: process_request does not ask the resolver")

def compiled_or_not(resolver, done: set) -> None:
    """Each matcher of the tree, and whether it has compiled its regular expression yet."""
    for entry in resolver.url_patterns:
        matcher = entry.pattern
        if id(matcher) not in done:
            done.add(id(matcher))
            has = "compiled" if "regex" in vars(matcher) else "not compiled"
            LINES.append(f"{type(matcher).__name__} {str(matcher)!r}  ->  {has}")
        if isinstance(entry, URLResolver):
            compiled_or_not(entry, done)


compiled_or_not(root, set())
show("After every path above was resolved, and before any name of museum.urls is reversed: which entries of its tree have a matcher with a compiled expression")

# ---------------------------------------------------------------------------------------------
# A name is reversed.

with recorded(REVERSE):
    with doing('the script calls reverse("tickets", kwargs={"year": 2026, "month": 3})'):
        reverse("tickets", kwargs={"year": 2026, "month": 3})
    with doing("and calls it again"):
        reverse("tickets", kwargs={"year": 2026, "month": 3})
    with doing('the script calls reverse("tickets", kwargs={"year": 2026, "month": 13})'):
        try:
            reverse("tickets", kwargs={"year": 2026, "month": 13})
        except NoReverseMatch:
            pass
show("reverse(): the first call for a URLconf fills its resolvers' tables, and each call reads them")

compiled_or_not(root, set())
show("After that first reverse with museum.urls: which entries of its tree have a matcher with a compiled expression")

UNCLOSED = "museum.urls_unclosed"
ASKING["UNCLOSED"] = UNCLOSED
for check in (checks.urls.check_url_config, checks.urls.check_url_namespaces_unique, checks.urls.check_url_settings,
              checks.urls.check_custom_error_handlers):
    ASKING[check.__name__] = check
note("UNCLOSED is 'museum.urls_unclosed', a URLconf of three entries, the second with a group that is never closed:")
note('  path("", views.entrance, name="entrance")')
note('  re_path(r"^plans/(?P<floor>[0-9]/$", views.plan, name="plan")')
note('  path("shop/", views.shop, name="shop")')
ask('re_path(r"^plans/(?P<floor>[0-9]/$", views.plan, name="plan")')
ask("get_resolver(UNCLOSED).url_patterns[1]")
ask('"regex" in vars(get_resolver(UNCLOSED).url_patterns[1].pattern)')
with settings_as(ROOT_URLCONF=UNCLOSED):
    with under("with ROOT_URLCONF = 'museum.urls_unclosed', the four checks tagged urls, each called by name"):
        for name in ("check_url_config", "check_url_namespaces_unique", "check_url_settings", "check_custom_error_handlers"):
            ask(f"{name}(None)")
ask('resolve("/", urlconf=UNCLOSED).url_name')
ask('resolve("/plans/2/", urlconf=UNCLOSED)')
ask('resolve("/shop/", urlconf=UNCLOSED)', brief=True)
ask('reverse("entrance", urlconf=UNCLOSED)', brief=True)
show("A re_path() whose expression does not compile: the import, the four URL checks with ROOT_URLCONF = 'museum.urls_unclosed', "
     "and the first paths matched against it")


def candidates_said(candidates) -> list:
    return [f"{possibilities!r}; {pattern!r}; {defaults!r}; {converters_of(converters)}"
            for possibilities, pattern, defaults, converters in candidates]


def tables(resolver) -> None:
    lookups = resolver.reverse_dict
    note("reverse_dict: under each key its candidates, in the order they are tried; "
         "a candidate is its forms; its regular expression; its extra arguments; its converters")
    listed = {}
    for key in lookups:
        said = candidates_said(lookups.getlist(key))
        if callable(key):
            listed[tuple(said)] = key
            continue
        note(f"  {key!r}")
        for line in said:
            note(f"    {line}")
        same = listed.pop(tuple(said), None)
        if same is not None:
            note(f"  the function {named(same)}  ->  the same candidates as {key!r}")
    for said, key in listed.items():
        note(f"  the function {named(key)}")
        for line in said:
            note(f"    {line}")
    note("namespace_dict")
    for namespace, (prefix, sub) in resolver.namespace_dict.items():
        note(f"  {namespace!r}  ->  ({prefix!r}, the resolver {str(sub.pattern)!r})")
    if not resolver.namespace_dict:
        note("  empty")
    note(f"app_dict  ->  {resolver.app_dict!r}")


tables(root)
note(f"_callback_strs, sorted  ->  {sorted(root._callback_strs)!r}")
show("What the root resolver keeps for reversing")

tables(root.url_patterns[3])
show("What the resolver of 'east/' keeps for reversing")

ask('reverse("entrance")')
ask('reverse("tickets", kwargs={"year": 2026})')
ask('reverse("tickets", kwargs={"year": 2026, "month": 3})')
ask('reverse("tickets", args=[2026, 3])')
ask('reverse("tickets", args=[2026], kwargs={"month": 3})')
ask('reverse("tickets")')
ask('reverse("tickets", kwargs={"year": 2026, "day": 1})', brief=True)
ask('reverse("tickets", kwargs={"year": 2026, "month": 13})', brief=True)
ask('reverse("ticket")')
ask('reverse(views.tickets, kwargs={"year": 2026})')
ask('reverse("museum.views.tickets", kwargs={"year": 2026})')
ask('reverse(views.room, kwargs={"room": 12})')
ask('reverse("plan", kwargs={"floor": 2})')
ask('reverse("plan", kwargs={"floor": 2, "format": "pdf"})')
ask('reverse("plan", args=[2, "svg"])')
ask('reverse("plan", kwargs={"floor": 2, "format": "png"})', brief=True)
ask('reverse("plan", kwargs={"floor": 12})', brief=True)
ask('reverse("item", kwargs={"item": "poster"})')
ask('reverse("item", kwargs={"item": "tea towel"})', brief=True)
show("reverse(): what comes back, and what is refused")

ANYTHING = (path("<path:name>", views.download, name="anything"),)
ASKING["ANYTHING"] = ANYTHING
ask('reverse("download", kwargs={"name": "maps/ground floor.pdf"})')
ask('reverse("download", kwargs={"name": "notes?draft#2 100%.txt"})')
ask('reverse("download", kwargs={"name": "café.txt"})')
note('ANYTHING is a URLconf of one pattern: path("<path:name>", views.download, name="anything")')
STACK.append(None)
ask('reverse("anything", urlconf=ANYTHING, kwargs={"name": "/evil.example/"})')
STACK.pop()
NOTES = (re_path(r"^notes/(?P<name>[a-z ]+)/$", views.download, name="notes"),)
ASKING["NOTES"] = NOTES
note('NOTES is a URLconf of one pattern: re_path(r"^notes/(?P<name>[a-z ]+)/$", views.download, name="notes")')
STACK.append(None)
ask('reverse("notes", urlconf=NOTES, kwargs={"name": "tea towel"})')
ask('reverse("notes", urlconf=NOTES, kwargs={"name": "tea%20towel"})', brief=True)
STACK.pop()
show("reverse(): the path is escaped once it has been checked")

ask('reverse("entrance", query={"lang": "nl", "tag": ["new", "sale"]}, fragment="hours")')
ask('reverse("entrance", query={})')
ask('reverse("entrance", fragment="")')
show("reverse(): a query string and a fragment")

ask('type(reverse_lazy("entrance")).__mro__[1].__name__')
ask('str(reverse_lazy("entrance"))')
ask('reverse_lazy("no-such-name") is not None')
ask('str(reverse_lazy("no-such-name"))', brief=True)
show("reverse_lazy(): nothing is reversed until the text is asked for")

FEEDS = (
    path("feed/rss/", views.feed, {"kind": "rss"}, name="feed"),
    path("feed/atom/", views.feed, {"kind": "atom"}, name="feed"),
)
ASKING["FEEDS"] = FEEDS
note("FEEDS is a URLconf of two patterns, in this order:")
note('  path("feed/rss/", views.feed, {"kind": "rss"}, name="feed")')
note('  path("feed/atom/", views.feed, {"kind": "atom"}, name="feed")')
found("/feed/rss/", FEEDS, "FEEDS")
ask('reverse("feed", urlconf=FEEDS, kwargs={"kind": "rss"})')
ask('reverse("feed", urlconf=FEEDS, kwargs={"kind": "atom"})')
ask('reverse("feed", urlconf=FEEDS)')
ask('reverse("feed", urlconf=FEEDS, kwargs={"kind": "json"})', brief=True)
show("Two patterns with one name, told apart by their extra arguments")

ASKING["OVERRIDES"] = OVERRIDES
note('OVERRIDES is path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")]), {"wing": "annexe"})')
STACK.append(None)
found("/east/rooms/12/", OVERRIDES, "OVERRIDES")
ask('get_resolver(OVERRIDES).reverse_dict.getlist("room")[0][2]')
ask('reverse("room", urlconf=OVERRIDES, kwargs={"wing": "annexe", "room": 1})')
ask('reverse("room", urlconf=OVERRIDES, kwargs={"wing": "east", "room": 12})')
ask('reverse("room", urlconf=OVERRIDES, kwargs={"room": 1})')
ask('reverse("room", urlconf=OVERRIDES)')
STACK.pop()
show("OVERRIDES reversed: its candidate keeps both extra arguments, and reverse() does not hold a parameter the route captures to its extra argument")

SAME_NAME = (path("plans/", include([path("<int:floor>/", views.plan, {"format": "pdf"}, name="plan")]), {"format": "svg"}),)
ASKING["SAME_NAME"] = SAME_NAME
note('SAME_NAME is path("plans/", include([path("<int:floor>/", views.plan, {"format": "pdf"}, name="plan")]), {"format": "svg"})')
STACK.append(None)
found("/plans/2/", SAME_NAME, "SAME_NAME")
ask('get_resolver(SAME_NAME).reverse_dict.getlist("plan")[0][2]')
ask('reverse("plan", urlconf=SAME_NAME, kwargs={"floor": 2, "format": "pdf"})', brief=True)
ask('reverse("plan", urlconf=SAME_NAME, kwargs={"floor": 2, "format": "svg"})')
ask('reverse("plan", urlconf=SAME_NAME, kwargs={"floor": 2})')
STACK.pop()
show("An extra argument of the same name at an include and at its pattern: the view is given the pattern's, and reverse() holds to the include's")

ALTERNATIVES = (path("about/", views.entrance, name="about"), re_path(r"^(?:east|west)/lift/$", views.entrance, name="lift"))
PERCENT = (path("about/", views.entrance, name="about"), path("sale-50%/", views.shop, name="sale"))
FLAGGED = (path("about/", views.entrance, name="about"), re_path(r"(?i)^cafe/$", views.entrance, name="cafe"))
CAFE = [re_path(r"(?i)^cafe/$", views.entrance, name="cafe")]
INCLUDING = (path("about/", views.entrance, name="about"), path("food/", include((CAFE, "food"))))
ASKING.update(ALTERNATIVES=ALTERNATIVES, PERCENT=PERCENT, FLAGGED=FLAGGED, INCLUDING=INCLUDING)
note('ALTERNATIVES is path("about/", views.entrance, name="about") and re_path(r"^(?:east|west)/lift/$", views.entrance, name="lift")')
STACK.append(None)
ask('resolve("/west/lift/", urlconf=ALTERNATIVES).url_name')
ask('reverse("lift", urlconf=ALTERNATIVES)', brief=True)
ask('reverse("about", urlconf=ALTERNATIVES)')
STACK.pop()
note('PERCENT is path("about/", views.entrance, name="about") and path("sale-50%/", views.shop, name="sale")')
STACK.append(None)
ask('resolve("/sale-50%/", urlconf=PERCENT).url_name')
ask('reverse("sale", urlconf=PERCENT)', brief=True)
ask('reverse("about", urlconf=PERCENT)')
STACK.pop()
note('FLAGGED is path("about/", views.entrance, name="about") and re_path(r"(?i)^cafe/$", views.entrance, name="cafe")')
STACK.append(None)
ask('resolve("/CAFE/", urlconf=FLAGGED).url_name')
ask('reverse("cafe", urlconf=FLAGGED)')
ask('reverse("about", urlconf=FLAGGED)')
STACK.pop()
note('CAFE is [re_path(r"(?i)^cafe/$", views.entrance, name="cafe")], and INCLUDING is path("about/", views.entrance, name="about") and path("food/", include((CAFE, "food")))')
STACK.append(None)
ask('reverse("about", urlconf=INCLUDING)')
STACK.pop()
show("Patterns that resolve and cannot be reversed, and how far the failure reaches")

MIXED = (re_path(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$", views.tickets, name="mixed"),)
ASKING["MIXED"] = MIXED
note('MIXED is a URLconf of one pattern: re_path(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$", views.tickets, name="mixed")')
STACK.append(None)
found("/mixed/2026/03/", MIXED, "MIXED")
ask('normalize(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$")')
ask('reverse("mixed", urlconf=MIXED, kwargs={"month": "03"})', brief=True)
ask('reverse("mixed", urlconf=MIXED, args=[2026, "03"])')
STACK.pop()
show("An expression with an unnamed group and a named one: what resolving passes on, and what reversing asks for")

for pattern in (r"^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\Z", r"^plans/(?P<floor>[0-9])(?:\.(?P<format>pdf|svg))?$",
                r"^archive/([0-9]{4})/([0-9]{2})/$", r"^pair/(?P<a>[0-9]+)/(?P=a)/$", r"^rooms?/$", r"^(?:wing/)?rooms/$",
                r"^room/\d+/\w+/$", r"^files/.+\.[a-z]{3}$", r"^files/[^/]+/$", r"^(?:east|west)/lift/$",
                r"^lift/(?P<side>east|west)/$", r"^sale\-50%/\Z", r"(?i)^cafe/$", r"^a{,3}/$", ""):
    ASKING["pattern"] = pattern
    ask("normalize(pattern)", show_as=f"normalize({pattern!r})", brief=pattern == r"^a{,3}/$")  # that message is Python's
show("normalize(): the forms a regular expression can be filled in as")

# ---------------------------------------------------------------------------------------------
# Namespaces.

with recorded(REVERSE):
    with doing('the script calls reverse("east:audio:track", kwargs={"room": 12, "track": "intro"})'):
        reverse("east:audio:track", kwargs={"room": 12, "track": "intro"})
    with doing("and calls it again"):
        reverse("east:audio:track", kwargs={"room": 12, "track": "intro"})
    with doing('the script calls reverse("east:room", kwargs={"room": 12})'):
        reverse("east:room", kwargs={"room": 12})
show("reverse() of a name inside namespaces: a resolver is made for the routes that lead to the namespace, and kept")

ask('reverse("east:room", kwargs={"room": 12})')
ask('reverse("west:room", kwargs={"room": 12})')
ask('reverse("gallery:room", kwargs={"room": 12})')
ask('reverse("gallery:room", kwargs={"room": 12}, current_app="east")')
ask('reverse("gallery:room", kwargs={"room": 12}, current_app="north")')
ask('reverse("east:room", kwargs={"room": 12}, current_app="west")')
ask('reverse("room", kwargs={"room": 12})', brief=True)
ask('reverse("east:audio:track", kwargs={"room": 12, "track": "intro"})')
ask('reverse("gallery:audio:track", kwargs={"room": 12, "track": "intro"})')
ask('reverse("gallery:audio:track", kwargs={"room": 12, "track": "intro"}, current_app="east:audio")')
ask('reverse("north:room", kwargs={"room": 12})')
ask('reverse("east:shop:item", kwargs={"item": "poster"})')
ask('reverse("east:wing")')
ask('reverse("east:wing", kwargs={"wing": "east"})', brief=True)
show("reverse() and namespaces: which wing a name leads to")

DEFAULT = (
    path("east/", include("museum.gallery.urls", namespace="east")),
    path("main/", include("museum.gallery.urls")),
    path("west/", include("museum.gallery.urls", namespace="west")),
)
ASKING["DEFAULT"] = DEFAULT
note("DEFAULT is a URLconf of three entries, in this order:")
note('  path("east/", include("museum.gallery.urls", namespace="east"))')
note('  path("main/", include("museum.gallery.urls"))')
note('  path("west/", include("museum.gallery.urls", namespace="west"))')
ask('get_resolver(DEFAULT).app_dict')
ask('reverse("gallery:wing", urlconf=DEFAULT)')
ask('reverse("gallery:wing", urlconf=DEFAULT, current_app="east")')
ask('reverse("gallery:wing", urlconf=DEFAULT, current_app="north")')
show("An instance whose namespace is the application's own is the default")


def url_tag(request) -> None:
    template = engines["django"].from_string("{% url 'gallery:room' room=13 %}")
    note(f"request.resolver_match.namespace  ->  {request.resolver_match.namespace!r}")
    with doing("the view renders the template {% url 'gallery:room' room=13 %}"):
        rendered = template.render({}, request)
        note(f"the template renders as {rendered!r}")
    request.current_app = "west"
    with doing('the view sets request.current_app = "west" and renders it again'):
        rendered = template.render({}, request)
        note(f"the template renders as {rendered!r}")


TAG = {("django.urls.base", "reverse"): reverse_called, **VIEWS}
views.ON_VIEW.append(url_tag)
serve(plain_handler, environ("/east/rooms/12/"), TAG)
views.ON_VIEW.clear()
show("GET /east/rooms/12/: the template tag {% url %} reverses for the wing the request is in")

# ---------------------------------------------------------------------------------------------
# What is kept for a thread: the script prefix and the URLconf.


def inside(request) -> None:
    with under("the view asks"):
        note(f"request.path  ->  {request.path!r}")
        note(f"request.path_info  ->  {request.path_info!r}")
        ask("get_script_prefix()")
        ask("get_urlconf()")
        ask('reverse("entrance")')


def elsewhere() -> str:
    """What another thread, started now, answers."""
    said = []
    thread = threading.Thread(target=lambda: said.append(get_script_prefix()))
    thread.start()
    thread.join()
    return said[0]


ASKING["elsewhere"] = elsewhere
with under("before this request"):
    ask("get_script_prefix()")
    ask("get_urlconf()")
views.ON_VIEW.append(inside)
serve(plain_handler, environ("/east/rooms/12/", SCRIPT_NAME="/museum"), REQUEST)
with under("after the request, on the same thread"):
    ask("get_script_prefix()")
    ask("get_urlconf()")
    ask('reverse("entrance")')
with under("and on a thread started now"):
    ask("elsewhere()", show_as="get_script_prefix()")
set_script_prefix("/")
show("GET /museum/east/rooms/12/, where the server's SCRIPT_NAME is /museum: what the handler sets for the thread, and what clears it")

# Of the handler's calls only the one that sets the prefix is written down this time.
FORCED = {key: REQUEST[key] for key in (
    ("django.core.handlers.wsgi", "WSGIHandler.__call__"), ("django.urls.base", "set_script_prefix"), ("museum.views", "room"))}
with settings_as(FORCE_SCRIPT_NAME="/exhibits"):
    with recorded(FORCED):
        plain_handler(environ("/east/rooms/12/", SCRIPT_NAME="/museum"), lambda status, headers: None).close()
set_script_prefix("/")
show("The same request with FORCE_SCRIPT_NAME = '/exhibits': the prefix the handler sets, and what the view is told")

views.ON_VIEW.clear()

# The same under ASGI: the script is the server, and runs it on an event loop of its own thread.
ASGI_REQUEST = {
    ("django.core.handlers.asgi", "ASGIHandler.__call__"): lambda f: "ASGIHandler.__call__(scope, receive, send)",
    ("django.core.handlers.asgi", "ASGIHandler.handle"): plain,
    ("django.core.handlers.asgi", "ASGIHandler.read_body"): plain,
    ("django.core.handlers.asgi", "ASGIHandler.create_request"): plain,
    ("django.urls.base", "set_script_prefix"): with_arg("prefix"),
    ("django.urls.base", "set_urlconf"): with_arg("urlconf_name"),
    ("django.dispatch.dispatcher", "Signal.send"): signal_sent,
    ("django.dispatch.dispatcher", "Signal.asend"): signal_sent,
    ("django.core.handlers.base", "BaseHandler.get_response_async"): plain,
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.resolvers", "get_resolver"): get_resolver_called,
    ("django.urls.resolvers", "URLResolver.resolve"): root_resolve,
    ("django.http.response", "HttpResponseBase.close"): on,
    ("django.core.handlers.base", "reset_urlconf"): plain,
    **VIEWS,
}
asgi_handler = ASGIHandler()


async def served_under_asgi() -> None:
    with under("before this request, in the server's coroutine"):
        ask("get_script_prefix()")
        ask("get_urlconf()")
    with recorded_on_every_thread(ASGI_REQUEST):
        await asgi_call(asgi_handler, asgi_scope("/museum/east/rooms/12/", root_path="/museum"))
    with under("after the request, in the server's coroutine"):
        ask("get_script_prefix()")
        ask("get_urlconf()")


views.ON_VIEW.append(inside)
asyncio.run(served_under_asgi())
views.ON_VIEW.clear()
with under("and on the script's thread, once asyncio.run() has returned (it ran the server's coroutine in a copy of this thread's context)"):
    ask("get_script_prefix()")
    ask("get_urlconf()")
show("GET /museum/east/rooms/12/ under ASGI, where the scope's root_path is /museum: what the handler sets, and what clears it")

ASKING.update(wsgi=wsgi, asgi=asgi)
with settings_as(FORCE_SCRIPT_NAME=""):
    ask('wsgi.get_script_name({"SCRIPT_NAME": "/museum", "PATH_INFO": "/east/rooms/12/"})')
    ask('asgi.get_script_prefix({"root_path": "/museum", "path": "/museum/east/rooms/12/"})')
    views.ON_VIEW.append(lambda request: ask(
        "get_script_prefix()", show_as="through WSGIHandler, SCRIPT_NAME being /museum: the view's get_script_prefix()"))
    plain_handler(environ("/east/rooms/12/", SCRIPT_NAME="/museum"), lambda status, headers: None).close()
    views.ON_VIEW.clear()
    views.ON_VIEW.append(lambda request: ask(
        "get_script_prefix()", show_as="through ASGIHandler, root_path being /museum: the view's get_script_prefix()"))
    asyncio.run(asgi_call(asgi_handler, asgi_scope("/museum/east/rooms/12/", root_path="/museum"), said=False))
    views.ON_VIEW.clear()
set_script_prefix("/")
show("FORCE_SCRIPT_NAME = '', and a server that mounts the project at /museum: the prefix each handler takes")


def inside_members(request) -> None:
    with under("the view asks"):
        ask("get_urlconf()")
        ask('reverse("renew", kwargs={"year": 2026})')
        ask('reverse("tickets", kwargs={"year": 2026})', brief=True)


views.ON_VIEW.append(inside_members)
with settings_as(MIDDLEWARE=[f"{__name__}.HostURLconf"]):
    host_handler = WSGIHandler()
serve(host_handler, environ("/", HTTP_HOST="members.museum.example"), REQUEST)
with under("after the request"):
    ask("get_urlconf()")
show("GET / for the host members.museum.example: a middleware sets request.urlconf")
views.ON_VIEW.clear()

from museum import views_async  # noqa: E402


def host_urlconf_on_the_loop(get_response):
    """The recording's middleware again, as a coroutine for the ASGI handler, so that the whole
    chain runs on the event loop: a request for the members' host is given the members' URLconf
    for that server, museum.urls_members_async."""
    async def middleware(request):
        if request.get_host().startswith("members."):
            request.urlconf = "museum.urls_members_async"
        return await get_response(request)
    return middleware


host_urlconf_on_the_loop.sync_capable = False
host_urlconf_on_the_loop.async_capable = True

STARTED = {}  # for each of the two requests, set when its view has started
ASKED = []  # set when the museum's view has asked its questions
ASKING["threading"] = threading


async def asks_in_turn(request) -> None:
    """In each view: the museum's asks once the members' view has started, and the members'
    once the museum's has asked. Each waits on an event the other sets."""
    mine, other = ("members", "museum") if request.get_host().startswith("members.") else ("museum", "members")
    STARTED[mine].set()
    await STARTED[other].wait()
    if mine == "members":
        await ASKED[0].wait()
    with under("the members' view, once the museum's view has asked" if mine == "members" else
               "the museum's view, once the members' view has started"):
        ask("threading.current_thread() is threading.main_thread()")
        ask("get_urlconf()")
        ask('reverse("tickets", kwargs={"year": 2026})', brief=True)
        ask('reverse("renew", kwargs={"year": 2026})', brief=True)
    if mine == "museum":
        ASKED[0].set()


async def two_at_once():
    STARTED.update(museum=asyncio.Event(), members=asyncio.Event())
    ASKED[:] = [asyncio.Event()]
    return await asyncio.gather(
        asgi_call(together_handler, asgi_scope("/"), said=False),
        asgi_call(together_handler, asgi_scope("/", host="members.museum.example"), said=False),
    )


with settings_as(ROOT_URLCONF="museum.urls_async", MIDDLEWARE=[f"{__name__}.host_urlconf_on_the_loop"]):
    together_handler = ASGIHandler()
    note("the server runs GET / for museum.example and GET / for members.museum.example together, with asyncio.gather, "
         "on an event loop on the script's thread")
    views_async.ON_VIEW.append(asks_in_turn)
    answered = asyncio.run(two_at_once())
    views_async.ON_VIEW.clear()
    for host, sent in zip(("museum.example", "members.museum.example"), answered):
        note(f"the server is sent, for {host}: status {sent[0]['status']}, {sent[1]['body'].decode()!r}")
with under("afterwards, on the script's thread"):
    ask("get_urlconf()")
show("Two requests at once under ASGI, with ROOT_URLCONF = 'museum.urls_async' and a middleware of the recording's own that gives "
     "the members' host its URLconf: each view, a coroutine on the event loop, asks once the other request's view has started, "
     "the two waiting on events each other sets")

from django.test import Client  # noqa: E402

views.ON_VIEW.append(inside)
note('the script calls set_script_prefix("/elsewhere")')
set_script_prefix("/elsewhere")
note('and then Client().get("/east/rooms/12/", SCRIPT_NAME="/museum")')
STACK.append(None)
Client().get("/east/rooms/12/", SCRIPT_NAME="/museum")
STACK.pop()
views.ON_VIEW.clear()
set_script_prefix("/")
show("The test client passes SCRIPT_NAME to the request, and its handler does not set the script prefix")

from django.test.utils import override_settings  # noqa: E402  (django.test, imported above, has connected the receivers of setting_changed)

ASKING.update(before=get_resolver(), _get_cached_resolver=_get_cached_resolver, get_ns_resolver=get_ns_resolver,
              clear_url_caches=clear_url_caches, override_settings=override_settings)
ask("get_resolver() is get_resolver()")
ask('get_resolver() is get_resolver("museum.urls")')
ask('get_resolver("museum.urls_members") is get_resolver()')
ask('get_resolver(sys.modules["museum.urls"]) is get_resolver("museum.urls")')
ask("_get_cached_resolver.cache_info().currsize > 1")
ask("get_ns_resolver.cache_info().currsize > 0")
note("the script calls clear_url_caches()")
clear_url_caches()
ask("_get_cached_resolver.cache_info().currsize")
ask("get_ns_resolver.cache_info().currsize")
ask("get_resolver() is before", show_as="get_resolver() is the root resolver there was before the call")
ASKING["before"] = get_resolver()
note('the script keeps the root resolver there is now, enters override_settings(ROOT_URLCONF="museum.urls_members") and leaves it again')
with override_settings(ROOT_URLCONF="museum.urls_members"):
    ask('reverse("renew", kwargs={"year": 2026})', show_as='inside it: reverse("renew", kwargs={"year": 2026})')
ask("get_resolver() is before", show_as="get_resolver() is the root resolver the script kept")
show("One root resolver for each value get_resolver() is given, kept until the caches are cleared")

# ---------------------------------------------------------------------------------------------
# Language prefixes and translated routes.

LANGUAGES = "museum.urls_languages"
ASKING["LANGUAGES"] = LANGUAGES
for language in ("en", "nl"):
    with translation.override(language):
        with under(f"with the language {language} active"):
            ask('reverse("hours", urlconf=LANGUAGES)')
            ask('reverse("shop", urlconf=LANGUAGES)')
            ask('reverse("entrance", urlconf=LANGUAGES)')
            ask('resolve("/en/opening-hours/", urlconf=LANGUAGES).url_name', brief=True)
            ask('resolve("/nl/openingstijden/", urlconf=LANGUAGES).url_name', brief=True)
            ask('resolve("/nl/opening-hours/", urlconf=LANGUAGES).url_name', brief=True)
show("museum.urls_languages: a prefix for the active language, and a route that is translated")

languages = get_resolver(LANGUAGES)
prefixed = languages.url_patterns[1]
hours, shop = prefixed.url_patterns
ASKING.update(languages=languages, prefixed=prefixed, hours=hours, shop=shop)
note("shop is the URLPattern of the route \"shop/\", a str; hours is the URLPattern of the translated route; "
     "resolver is the root resolver of museum.urls_languages")
ASKING["resolver"] = languages
ask("type(shop.pattern._route).__name__")
ask('"regex" in vars(shop.pattern)')
ask("sorted(shop.pattern._regex_dict)")
ask("type(hours.pattern._route).__mro__[1].__name__")
ask('"regex" in vars(hours.pattern)')
ask("sorted(hours.pattern._regex_dict)")
ask("sorted(resolver._reverse_dict)")
show("What is kept once, and what once for each language")

ask("type(prefixed).__name__, type(prefixed.pattern).__name__",
    show_as="the entry i18n_patterns made: type(entry).__name__, type(entry.pattern).__name__")
ask("is_language_prefix_patterns_used(LANGUAGES)")
ask('is_language_prefix_patterns_used("museum.urls")')
show("is_language_prefix_patterns_used(urlconf): is there a prefix, and has the default language one")

ASKING.update(translation=translation, settings=settings)
with translation.override(None):
    with under("inside translation.override(None), which deactivates translations"):
        ask("translation.get_language()")
        ask("settings.LANGUAGE_CODE")
        ask('reverse("hours", urlconf=LANGUAGES)')
        ask('resolve("/en/opening-hours/", urlconf=LANGUAGES).url_name', brief=True)
show("With no language active, the prefix is that of LANGUAGE_CODE")

set_urlconf(LANGUAGES)
with under("with en active, and museum.urls_languages the current URLconf"):
    ask('translate_url("/en/opening-hours/", "nl")')
    ask('translate_url("https://museum.example/en/opening-hours/?day=sunday#top", "nl")')
    ask('translate_url("/en/shop/", "nl")')
    ask('translate_url("/", "nl")')
    ask('translate_url("/en/nothing/", "nl")')
    ask('translate_url("/nl/openingstijden/", "en")')
with translation.override("nl"):
    with under("with nl active"):
        ask('translate_url("/nl/openingstijden/", "en")')
set_urlconf(None)
show("translate_url(url, lang_code): the same view's address in another language")

UNPREFIXED = tuple(i18n_patterns(path("shop/", views.shop, name="shop"), prefix_default_language=False))
ASKING["UNPREFIXED"] = UNPREFIXED
note('UNPREFIXED is a URLconf of what i18n_patterns(path("shop/", views.shop, name="shop"), prefix_default_language=False) returns')
for language in ("en", "nl"):
    with translation.override(language):
        with under(f"with the language {language} active"):
            ask('reverse("shop", urlconf=UNPREFIXED)')
ask("is_language_prefix_patterns_used(UNPREFIXED)")
with settings_as(USE_I18N=False):
    ask('[type(p).__name__ for p in i18n_patterns(path("shop/", views.shop, name="shop"))]',
        show_as='with USE_I18N = False: [type(p).__name__ for p in i18n_patterns(path("shop/", views.shop, name="shop"))]')
show("The default language without a prefix")

LOCALE_RULES = {
    ("django.middleware.locale", "LocaleMiddleware.process_request"): hook,
    ("django.middleware.locale", "LocaleMiddleware.process_response"): hook,
    ("django.conf.urls.i18n", "is_language_prefix_patterns_used"): with_arg("urlconf"),
    ("django.utils.translation.trans_real", "activate"): with_arg("language"),
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.resolvers", "URLResolver.resolve"): root_resolve,
    ("django.urls.base", "is_valid_path"): is_valid,
    **VIEWS,
}
with settings_as(ROOT_URLCONF=LANGUAGES, MIDDLEWARE=["django.middleware.locale.LocaleMiddleware"]):
    locale_handler = WSGIHandler()
    note("the script empties the cache of is_language_prefix_patterns_used, so that its body runs when it is next called")
    is_language_prefix_patterns_used.cache_clear()
    serve(locale_handler, environ("/nl/openingstijden/"), LOCALE_RULES)
    translation.deactivate()
    ask("is_language_prefix_patterns_used.cache_info()", show_as="afterwards: is_language_prefix_patterns_used.cache_info()")
    show("With LocaleMiddleware and ROOT_URLCONF = 'museum.urls_languages': GET /nl/openingstijden/")
    serve(locale_handler, environ("/shop/", HTTP_ACCEPT_LANGUAGE="nl"), LOCALE_RULES)
    translation.deactivate()
    ask("is_language_prefix_patterns_used.cache_info()", show_as="afterwards: is_language_prefix_patterns_used.cache_info()")
    show("With LocaleMiddleware and ROOT_URLCONF = 'museum.urls_languages': GET /shop/ with Accept-Language: nl")

RENAMED = "museum.urls_renamed"
ASKING.update(RENAMED=RENAMED, converters_of=lambda converters: Said(converters_of(converters)))
note("RENAMED is 'museum.urls_renamed': i18n_patterns(path(_(\"visits/<int:year>/\"), views.tickets, name=\"visits\")), "
     "where the catalogue translates the route as \"bezoeken/<int:jaar>/\"")
with translation.override("en"):
    with under("with en active, the script reads the URLconf's patterns, and so imports it"):
        ask("converters_of(get_resolver(RENAMED).url_patterns[0].url_patterns[0].pattern.converters)")
        found("/en/visits/2026/", RENAMED, "RENAMED")
with translation.override("nl"):
    with under("with nl active"):
        ask("str(get_resolver(RENAMED).url_patterns[0].url_patterns[0].pattern)")
        ask("converters_of(get_resolver(RENAMED).url_patterns[0].url_patterns[0].pattern.converters)")
        with recorded(RESOLVE):
            with doing('the script calls resolve("/nl/bezoeken/2026/", urlconf=RENAMED)'):
                try:
                    resolve("/nl/bezoeken/2026/", urlconf=RENAMED)
                except KeyError:
                    pass
        ask('resolve("/nl/bezoeken/2026/", urlconf=RENAMED)')
show("A translated route whose Dutch translation renames its parameter: the converters are those of the route as it read at the import")

RENAMED_RULES = {
    **LOCALE_RULES,
    ("django.core.handlers.exception", "response_for_exception"): plain,
    ("django.core.handlers.exception", "handle_uncaught_exception"): plain,
    ("django.urls.resolvers", "URLResolver.resolve_error_handler"): error_handler,
}
with settings_as(ROOT_URLCONF=RENAMED):
    serve(locale_handler, environ("/nl/bezoeken/2026/"), RENAMED_RULES)
    translation.deactivate()
show("With LocaleMiddleware and ROOT_URLCONF = 'museum.urls_renamed': GET /nl/bezoeken/2026/")

# ---------------------------------------------------------------------------------------------
# The checks, and the tools that walk the tree.

from django.core.checks import urls as url_checks  # noqa: E402

# The registry keeps its checks in a set, so the order they run in is not the same from one
# process to the next: each is called here by name, in the order of its module.
URL_CHECKS = (url_checks.check_url_config, url_checks.check_url_namespaces_unique, url_checks.check_url_settings,
              url_checks.check_custom_error_handlers)
with settings_as(ROOT_URLCONF="museum.urls_mistakes", STATIC_URL="static"):
    for check in URL_CHECKS:
        with under(check.__name__):
            for message in check(None):
                note(f"{message.id}, {type(message).__name__}: {message.msg}")
                if message.hint:
                    note(f"  hint: {message.hint}")
show("The four checks tagged urls, each called over museum.urls_mistakes, with STATIC_URL = 'static'")

ASKING["checks"] = checks
ask('checks.run_checks(tags=["urls"])')
show("The same checks over museum.urls, run through the registry by their tag")

listing = io.StringIO()
call_command("listurls", stdout=listing, no_color=True)
for line in listing.getvalue().splitlines():
    note(line.rstrip())
show('call_command("listurls"), with ROOT_URLCONF = \'museum.urls\': each line as printed, without the spaces at its end')

for callback, route, namespaces, name in extract_views_from_urlpatterns(get_resolver().url_patterns):
    note(f"({named(callback)}, {route!r}, {namespaces!r}, {name!r})")
show("extract_views_from_urlpatterns(get_resolver().url_patterns): a tuple for each pattern")

for pattern in (r"^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\Z", r"^plans/(?P<floor>[0-9])(?:\.(?P<format>pdf|svg))?$",
                r"^archive/([0-9]{4})/([0-9]{2})/$", "east/rooms/<int:room>/audio/<slug:track>/"):
    ASKING["pattern"] = pattern
    ask("simplify_regex(pattern)", show_as=f"simplify_regex({pattern!r})")
show("simplify_regex(): a regular expression made into an address a person can read")

ASKING["named"] = lambda view: Said(named(view))
ask('get_callable("museum.views.shop") is views.shop')
ask("get_callable(views.shop) is views.shop")
ask('get_callable("museum.views.nowhere")')
ask('get_callable("museum.nowhere.shop")')
ask('get_callable("shop")')
ask("get_callable(404)")
ask("named(get_resolver().resolve_error_handler(404))", show_as="get_resolver().resolve_error_handler(404)")
ask("named(get_resolver().resolve_error_handler(500))", show_as="get_resolver().resolve_error_handler(500)")
ask("get_resolver().resolve_error_handler(418)", brief=True)
show("get_callable(), and the error views used when a URLconf names none")

from django.core.exceptions import ViewDoesNotExist  # noqa: E402

GET_CALLABLE = {("django.urls.utils", "get_callable"): with_arg("lookup_view")}
ask("get_callable.cache_info()")
with recorded(GET_CALLABLE):
    with doing('the script calls get_callable("museum.nowhere.item") twice'):
        for _ in range(2):
            try:
                get_callable("museum.nowhere.item")
            except ViewDoesNotExist:
                pass
ask("get_callable.cache_info()")
with recorded(GET_CALLABLE):
    with doing('the script calls get_callable("museum.views.item") twice'):
        for _ in range(2):
            get_callable("museum.views.item")
ask("get_callable.cache_info()")
show("get_callable(), kept by functools.cache: a name that fails is looked up again at each call, and one that works once")

# ---------------------------------------------------------------------------------------------
# A matcher's converters, shared through the cache of _route_to_regex. These blocks come last:
# what they change in place is not put back.

ask('path("tour/<slug:stop>/", include([])).pattern.converters is path("tour/<slug:stop>/", include([])).pattern.converters')
ask('path("tour/<slug:stop>/", views.entrance).pattern.converters is path("tour/<slug:stop>/", include([])).pattern.converters')
show("path() called twice with one route: whether the two matchers hold one dictionary of converters")

LEVELS = (path("floors/<int:floor>/", include([path("tour/<slug:stop>/", include(([path("", views.entrance, name="stop")], "tour")))])),)
ASKING.update(LEVELS=LEVELS, inner=LEVELS[0].url_patterns[0].pattern)
note('LEVELS is path("floors/<int:floor>/", include([path("tour/<slug:stop>/", include(([path("", views.entrance, name="stop")], "tour")))])), '
     "and inner is the matcher of the include with the namespace tour")
STACK.append(None)
ask("converters_of(inner.converters)")
ask('reverse("tour:stop", urlconf=LEVELS, kwargs={"floor": 2, "stop": "intro"})')
ask("converters_of(inner.converters)")
found("/floors/2/tour/intro/", LEVELS, "LEVELS")
STACK.pop()
show("reverse() over a namespaced include under a plain include with a converter: the plain include's converters are put into the namespaced one's matcher")

SMALL = (
    path("", views.entrance, name="entrance"),
    path("floors/<int:wing>/", include([path("<slug:wing>/", include(([path("", views.wing, name="wing")], "tour")))])),
)
ASKING.update(SMALL=SMALL, inner=SMALL[1].url_patterns[0].pattern)
note("SMALL is a URLconf of two entries:")
note('  path("", views.entrance, name="entrance")')
note('  path("floors/<int:wing>/", include([path("<slug:wing>/", include(([path("", views.wing, name="wing")], "tour")))]))')
note("inner is the matcher of the include with the namespace tour")
ask("converters_of(inner.converters)")
found("/floors/2/east/", SMALL, "SMALL")
ask('reverse("entrance", urlconf=SMALL)')
ask("converters_of(inner.converters)")
found("/floors/2/east/", SMALL, "SMALL")
found("/floors/2/3/", SMALL, "SMALL")
show("The same with one parameter's name at both levels: after a reverse(), the namespaced include's matcher converts with the plain include's converter")

ASKING.update(NESTED=NESTED, CAPTURED=CAPTURED)
note("inner is still the matcher of SMALL's include with the namespace tour, whose route is \"<slug:wing>/\"")
ask("inner.converters is NESTED[0].pattern.converters")
ask("inner.converters is CAPTURED[0].pattern.converters")
ask("inner.converters is OVERRIDES[0].pattern.converters")
found("/east/west/", NESTED, "NESTED")
found("/east/rooms/12/", CAPTURED, "CAPTURED")
found("/east/rooms/12/", OVERRIDES, "OVERRIDES")
found("/7/rooms/12/", CAPTURED, "CAPTURED")
show("NESTED, CAPTURED and OVERRIDES, URLconfs of earlier blocks whose includes have the same route, "
     "hold the same dictionary as SMALL's namespaced include, and after that reverse() refuse the paths they resolved there")

shutil.rmtree(LOCALE, ignore_errors=True)
