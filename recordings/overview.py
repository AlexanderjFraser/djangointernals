"""A recording of one request, end to end: a process starting, and then two requests for the
same page, written down as Django serves them.

    python recordings/overview.py > recordings/overview.txt

Chapter 1 of the book (pages/overview.md and the pages under it) is written against this
output. It needs only the pinned Django (the project's virtual environment has it) and the
small project beside it, `journal/`: what `django-admin startproject` writes, with one app
that has one model, one URL pattern, one view and one template. The database is a SQLite file
made for the run, with three rows in it. Run it again after a re-pin: where the output
changes, the chapter has to.

What is written down is a selection: the calls on the request's path that the chapter names,
nested as they were made, with the arguments that tell them apart. Everything between them
ran and is left out. A line is a function of Django's by its qualified name, or an event: a
signal sent, a query executed, a header set, a module imported, the server's own calls.
"""
import datetime
import io
import os
import sys
import weakref
import tempfile

sys.stdout.reconfigure(newline="\n")  # the same bytes on every machine
HERE = os.path.dirname(os.path.abspath(__file__))
# `journal` imports from this directory, as it would from a project's. The directory goes last
# on the path and not first, where Python puts a script's own: `http.py` in it has the name of
# a package of the standard library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]

DATABASE = os.path.join(tempfile.mkdtemp(), "journal.sqlite3")
os.environ["JOURNAL_DATABASE"] = DATABASE
os.environ["DJANGO_SETTINGS_MODULE"] = "journal.settings"

LINES = []
STACK = []  # the watched frames open at this moment: the depth of the next line
SEEN = {}  # generator frames already written down: a generator is entered once per value
SIGNALS = {"request_started", "request_finished", "got_request_exception", "connection_created", "pre_init", "post_init"}


def note(text: str) -> None:
    LINES.append("  " * len(STACK) + text)


def show(title: str) -> None:
    print(title)
    for line in LINES:
        print("    " + line)
    print()
    LINES.clear()
    STACK.clear()
    SEEN.clear()


# ---------------------------------------------------------------------------------------------
# What to write down, and how to say it. A label function is given the frame at the moment of
# the call and returns the line, or None for a call not to write down.

def signal_name(signal) -> str:
    for module in ("django.core.signals", "django.db.models.signals", "django.db.backends.signals"):
        mod = sys.modules.get(module)
        for name in dir(mod) if mod else ():
            if getattr(mod, name) is signal:
                return name
    return ""


def send(frame):
    signal, sender = frame.f_locals["self"], frame.f_locals.get("sender")
    name = signal_name(signal)
    if name not in SIGNALS:
        return None
    receivers = signal._live_receivers(sender)
    if isinstance(receivers, tuple):  # (synchronous receivers, asynchronous receivers)
        receivers = [*receivers[0], *receivers[1]]
    names = ", ".join(getattr(r, "__qualname__", type(r).__name__) for r in receivers) or "no receivers"
    return f"signal {name} -> {names}"


def template_dir(origin) -> str:
    """An origin's directory by the app it belongs to, not by this machine's path."""
    parts = origin.name.replace("\\", "/").split("/")
    if "templates" in parts:
        at = parts.index("templates")
        return "/".join(parts[max(at - 1, 0):at + 1])
    return "a directory in DIRS"


def cls_of(frame) -> type:
    return type(frame.f_locals["self"])


def hook(frame) -> str:
    label = frame.f_code.co_qualname
    if frame.f_code.co_name == "process_response":
        label += f"  (status {frame.f_locals['response'].status_code})"
    return label


def middleware_made(frame):
    """A middleware's constructor, when the chain is built: the same constructors also run for
    every view decorated with csrf_protect, as modules that do so are imported."""
    caller = frame.f_back
    while caller is not None and caller.f_code.co_name == "__init__":  # a subclass's own __init__ calling up
        caller = caller.f_back
    made_by_chain = caller is not None and caller.f_code.co_qualname == "BaseHandler.load_middleware"
    return f"MiddlewareMixin.__init__ ({cls_of(frame).__name__})" if made_by_chain else None


def loader_made(frame) -> str:
    declared = frame.f_globals["__name__"].rsplit(".", 1)[1]
    actual = cls_of(frame).__module__.rsplit(".", 1)[1]
    return f"{declared}.Loader.__init__" + (f"  ({actual}.Loader)" if actual != declared else "")


def loader_method(frame) -> str:
    declared = frame.f_globals["__name__"].rsplit(".", 1)[1]
    actual = cls_of(frame).__module__.rsplit(".", 1)[1]
    label = f"{declared}.Loader.{frame.f_code.co_name}"
    if "origin" in frame.f_locals:
        label += f"  ({actual}.Loader, in {template_dir(frame.f_locals['origin'])})"
    elif "template_name" in frame.f_locals:
        label += f"({frame.f_locals['template_name']!r})" + (f"  ({actual}.Loader)" if actual != declared else "")
    return label


def with_arg(name: str):
    def label(frame):
        return f"{frame.f_code.co_qualname}({frame.f_locals[name]!r})"
    return label


def plain(frame) -> str:
    return frame.f_code.co_qualname


def imported(frame) -> str:
    return f"import {frame.f_globals['__name__']}"


# (module, qualname) -> the label function. A module ending in "." matches that package and
# everything under it; a qualname of "*.name" matches any method of that name.
STARTUP = {
    ("django.core.wsgi", "get_wsgi_application"): plain,
    ("django", "setup"): plain,
    ("django.conf", "LazySettings._setup"): lambda f: 'LazySettings._setup: the settings module "journal.settings" is imported',
    ("django.utils.log", "configure_logging"): plain,
    ("django.apps.registry", "Apps.populate"): plain,
    ("django.apps.config", "AppConfig.create"): lambda f: f'AppConfig.create("{f.f_locals["entry"]}")',
    ("django.apps.config", "AppConfig.import_models"): lambda f: f"AppConfig.import_models  ({f.f_locals['self'].label})",
    ("django.apps.registry", "Apps.register_model"): lambda f: f"Apps.register_model({f.f_locals['model']._meta.label})",
    ("django.apps.config", "AppConfig.ready"): lambda f: f"AppConfig.ready  ({f.f_locals['self'].label})",
    ("django.contrib.", "*.ready"): lambda f: f"{f.f_code.co_qualname}  ({f.f_locals['self'].label})",
    ("django.contrib.admin", "autodiscover"): plain,
    ("django.core.handlers.wsgi", "WSGIHandler.__init__"): plain,
    ("django.core.handlers.base", "BaseHandler.load_middleware"): plain,
    ("django.middleware", "MiddlewareMixin.__init__"): middleware_made,
}

REQUEST = {
    # the handler, and the middleware
    ("django.core.handlers.wsgi", "WSGIHandler.__call__"): lambda f: f'WSGIHandler.__call__(environ, start_response)  {f.f_locals["environ"]["REQUEST_METHOD"]} {f.f_locals["environ"]["PATH_INFO"]}',
    ("django.urls.base", "set_script_prefix"): with_arg("prefix"),
    ("django.dispatch.dispatcher", "Signal.send"): send,
    ("django.db", "reset_queries"): plain,
    ("django.db", "close_old_connections"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.close_if_unusable_or_obsolete"): plain,
    ("django.core.cache", "close_caches"): plain,
    ("django.core.handlers.base", "reset_urlconf"): plain,
    ("django.core.handlers.wsgi", "WSGIRequest.__init__"): lambda f: "WSGIRequest.__init__(environ)",
    ("django.core.handlers.base", "BaseHandler.get_response"): plain,
    ("django.urls.base", "set_urlconf"): with_arg("urlconf_name"),
    ("django.middleware", "MiddlewareMixin.__call__"): lambda f: f"MiddlewareMixin.__call__ ({cls_of(f).__name__})",
    ("django.middleware.", "*.process_request"): hook,
    ("django.middleware.", "*.process_view"): hook,
    ("django.middleware.", "*.process_response"): hook,
    ("django.contrib.", "*.process_request"): hook,
    ("django.contrib.", "*.process_view"): hook,
    ("django.contrib.", "*.process_response"): hook,
    ("django.contrib.sessions.backends.db", "SessionStore.__init__"): lambda f: f"SessionStore.__init__(session_key={f.f_locals['session_key']!r})  (sessions.backends.db)",
    ("django.http.request", "HttpRequest.get_host"): plain,
    ("django.middleware.csrf", "CsrfViewMiddleware._get_secret"): plain,
    ("django.contrib.messages.storage.fallback", "FallbackStorage.__init__"): plain,
    ("django.contrib.sessions.backends.base", "SessionBase.is_empty"): plain,
    ("django.contrib.messages.storage.base", "BaseStorage.update"): plain,
    ("django.http.response", "ResponseHeaders.__setitem__"): lambda f: f'response["{f.f_locals["key"]}"] = "{f.f_locals["value"]}"',
    # the centre: the URL, the view
    ("django.core.handlers.base", "BaseHandler._get_response"): plain,
    ("django.core.handlers.base", "BaseHandler.resolve_request"): plain,
    ("django.urls.resolvers", "URLResolver.resolve"): with_arg("path"),
    ("django.urls.resolvers", "URLResolver.urlconf_module"): lambda f: "URLResolver.urlconf_module: the root URLconf is imported",
    ("journal.urls", "<module>"): imported,
    ("journal.views", "<module>"): imported,
    ("django.urls.conf", "_path"): lambda f: f'path("{f.f_locals["route"]}", {f.f_locals["view"].__qualname__}, name="{f.f_locals["name"]}")',
    ("django.urls.resolvers", "URLPattern.resolve"): with_arg("path"),
    ("django.urls.resolvers", "RoutePattern.match"): with_arg("path"),
    ("django.urls.converters", "IntConverter.to_python"): with_arg("value"),
    ("django.urls.resolvers", "ResolverMatch.__init__"): lambda f: f"ResolverMatch({f.f_locals['func'].__module__}.{f.f_locals['func'].__qualname__}, kwargs={f.f_locals['kwargs']})",
    ("django.core.handlers.base", "BaseHandler.make_view_atomic"): plain,
    ("journal.views", "by_year"): lambda f: f"journal.views.by_year(request, year={f.f_locals['year']})",
    ("django.core.handlers.base", "BaseHandler.check_response"): plain,
    # the queryset is built
    ("django.db.models.manager", "BaseManager.get_queryset"): lambda f: f"BaseManager.get_queryset  ({f.f_locals['self'].model.__name__}.objects)",
    ("django.db.models.query", "QuerySet.filter"): lambda f: f"QuerySet.filter({', '.join(f'{k}={v!r}' for k, v in f.f_locals['kwargs'].items())})",
    ("django.db.models.query", "QuerySet._clone"): plain,
    ("django.db.models.sql.query", "Query.clone"): plain,
    ("django.db.models.sql.query", "Query.add_q"): plain,
    ("django.db.models.sql.query", "Query.build_filter"): plain,
    ("django.db.models.sql.query", "Query.solve_lookup_type"): with_arg("lookup"),
    ("django.db.models.sql.query", "Query.setup_joins"): with_arg("names"),
    ("django.db.models.sql.query", "Query.build_lookup"): plain,
    ("django.db.models.sql.query", "Query.try_transform"): with_arg("name"),
    ("django.db.models.functions.datetime", "Extract.__init__"): lambda f: f"{cls_of(f).__name__}.__init__",
    ("django.db.models.lookups", "Lookup.__init__"): lambda f: f"{cls_of(f).__name__}.__init__(lhs={type(f.f_locals['lhs']).__name__}, rhs={f.f_locals['rhs']!r})",
    ("django.db.models.query", "QuerySet.order_by"): lambda f: f"QuerySet.order_by({', '.join(repr(a) for a in f.f_locals['field_names'])})",
    ("django.db.models.sql.query", "Query.add_ordering"): plain,
    # the template is found, compiled and rendered
    ("django.shortcuts", "render"): lambda f: f'render(request, "{f.f_locals["template_name"]}", context)',
    ("django.template.loader", "get_template"): with_arg("template_name"),
    ("django.template.utils", "EngineHandler.__getitem__"): lambda f: f'EngineHandler.__getitem__("{f.f_locals["alias"]}")',
    ("django.template.backends.django", "DjangoTemplates.__init__"): plain,
    ("django.template.backends.django", "get_installed_libraries"): plain,
    ("django.template.engine", "Engine.__init__"): plain,
    ("django.template.backends.django", "DjangoTemplates.get_template"): with_arg("template_name"),
    ("django.template.engine", "Engine.get_template"): with_arg("template_name"),
    ("django.template.engine", "Engine.find_template"): with_arg("name"),
    ("django.template.engine", "Engine.get_template_loaders"): plain,
    ("django.template.loaders.cached", "Loader.__init__"): loader_made,
    ("django.template.loaders.filesystem", "Loader.__init__"): loader_made,
    ("django.template.loaders.cached", "Loader.get_template"): loader_method,
    ("django.template.loaders.base", "Loader.get_template"): loader_method,
    ("django.template.loaders.filesystem", "Loader.get_contents"): loader_method,
    ("django.template.exceptions", "TemplateDoesNotExist.__init__"): lambda f: "raises TemplateDoesNotExist",
    ("django.template.base", "Template.__init__"): lambda f: "Template.__init__: the source is compiled",
    ("django.template.base", "Lexer.tokenize"): plain,
    ("django.template.base", "Parser.parse"): plain,
    ("django.template.defaulttags", "do_for"): lambda f: "do_for: {% for %} becomes a ForNode",
    ("django.template.backends.django", "Template.render"): lambda f: "Template.render(context, request)  (the backend's Template)",
    ("django.template.context", "make_context"): plain,
    ("django.template.context", "RequestContext.__init__"): plain,
    ("django.template.base", "Template.render"): lambda f: "Template.render(context)  (the engine's Template)",
    ("django.template.engine", "Engine.template_context_processors"): lambda f: "Engine.template_context_processors: the context processors are imported",
    ("django.template.context_processors", "csrf"): lambda f: "context_processors.csrf",
    ("django.template.context_processors", "request"): lambda f: "context_processors.request",
    ("django.contrib.auth.context_processors", "auth"): lambda f: "auth.context_processors.auth",
    ("django.contrib.messages.context_processors", "messages"): lambda f: "messages.context_processors.messages",
    ("django.template.base", "VariableNode.render"): lambda f: f"VariableNode.render  {{{{ {f.f_locals['self'].filter_expression.token} }}}}",
    ("django.template.defaulttags", "ForNode.render"): lambda f: f"ForNode.render  {{% for {', '.join(f.f_locals['self'].loopvars)} in {f.f_locals['self'].sequence.token} %}}",
    ("django.template.defaultfilters", "date"): lambda f: f'defaultfilters.date(value, "{f.f_locals["arg"]}")',
    ("django.utils.html", "conditional_escape"): plain,
    # the query runs
    ("django.db.models.query", "QuerySet.__len__"): plain,
    ("django.db.models.query", "QuerySet.__iter__"): plain,
    ("django.db.models.query", "QuerySet._fetch_all"): plain,
    ("django.db.models.query", "ModelIterable.__iter__"): plain,
    ("django.db.models.sql.query", "Query.get_compiler"): with_arg("using"),
    ("django.db.models.sql.compiler", "SQLCompiler.execute_sql"): plain,
    ("django.db.models.sql.compiler", "SQLCompiler.as_sql"): plain,
    ("django.db.models.sql.compiler", "SQLCompiler.get_select"): plain,
    ("django.db.models.sql.compiler", "SQLCompiler.get_order_by"): plain,
    ("django.db.models.sql.compiler", "SQLCompiler.get_from_clause"): plain,
    ("django.db.models.sql.where", "WhereNode.as_sql"): plain,
    ("django.db.models.lookups", "YearLookup.as_sql"): lambda f: f"YearLookup.as_sql  ({cls_of(f).__name__})",
    ("django.db.backends.base.base", "BaseDatabaseWrapper.cursor"): plain,
    ("django.db.backends.base.base", "BaseDatabaseWrapper.connect"): plain,
    ("django.db.backends.sqlite3.base", "DatabaseWrapper.get_new_connection"): lambda f: "DatabaseWrapper.get_new_connection  (sqlite3)",
    ("django.db.backends.utils", "CursorWrapper.execute"): plain,
    ("django.db.backends.sqlite3.base", "SQLiteCursorWrapper.execute"): plain,
    ("django.db.models.sql.compiler", "SQLCompiler.results_iter"): plain,
    ("django.db.backends.sqlite3.operations", "DatabaseOperations.convert_datefield_value"): lambda f: "DatabaseOperations.convert_datefield_value  (sqlite3)",
    ("django.db.models.base", "Model.from_db"): lambda f: f"Model.from_db  ({f.f_locals['cls'].__name__})",
    ("django.db.models.base", "Model.__init__"): lambda f: f"Model.__init__  ({cls_of(f).__name__})",
    # the response
    ("django.http.response", "HttpResponse.__init__"): lambda f: "HttpResponse.__init__(content)",
    ("django.http.response", "HttpResponseBase.close"): plain,
    ("django.http.request", "HttpRequest.close"): plain,
    ("django.db.backends.sqlite3.base", "DatabaseWrapper.close"): lambda f: "DatabaseWrapper.close  (sqlite3)",
}

RULES = {}  # the set in force: STARTUP, then REQUEST


def find(module: str, qualname: str):
    """The label function for a call of this function, or None."""
    name = qualname.rsplit(".", 1)[-1]
    for (want_module, want), label in RULES.items():
        if module == want_module or (want_module.endswith(".") and module.startswith(want_module)):
            if want == qualname or (want.startswith("*.") and want[2:] == name and "." in qualname):
                return label
    return None


def profile(frame, event, arg):
    if event == "call":
        code = frame.f_code
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
            STACK.pop()


# ---------------------------------------------------------------------------------------------

RULES = STARTUP
sys.setprofile(profile)
import journal.wsgi  # noqa: E402  what a server does: import the module that makes the handler
sys.setprofile(None)

import django  # noqa: E402

print("Django", django.get_version(), "with the settings django-admin startproject writes, and one app, journal\n")
show("The process starts: a server imports journal/wsgi.py")

application = journal.wsgi.application

from django.db import connection  # noqa: E402
from journal.models import Entry  # noqa: E402

with connection.schema_editor() as editor:
    editor.create_model(Entry)
Entry.objects.create(title="A first entry", published=datetime.date(2026, 3, 14))
Entry.objects.create(title="Spring", published=datetime.date(2026, 4, 2))
Entry.objects.create(title="Last year", published=datetime.date(2025, 12, 31))
connection.close()


def sql_wrapper(execute, sql, params, many, context):
    note(f"SQL {sql} with params {params}")
    return execute(sql, params, many, context)


def request(title: str) -> None:
    environ = {
        "REQUEST_METHOD": "GET", "PATH_INFO": "/entries/2026/", "SERVER_NAME": "journal.example",
        "SERVER_PORT": "80", "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.input": io.BytesIO(b""),
        "wsgi.url_scheme": "http", "HTTP_HOST": "journal.example",
    }

    def start_response(status, headers):
        note(f'start_response("{status}", [{", ".join(name for name, value in headers)}])')

    with connection.execute_wrapper(sql_wrapper):
        sys.setprofile(profile)
        response = application(environ, start_response)
        body = b"".join(response)
        note(f"the server has sent the body: {len(body)} bytes")
        response.close()
        sys.setprofile(None)
    show(title)


RULES = REQUEST
request("The first request: GET /entries/2026/")
request("The second request: GET /entries/2026/ again")
