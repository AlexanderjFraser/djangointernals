"""A recording of views: what the handler calls, how a class becomes something it can call,
what the decorators and the generic views do around a view's own code, and what the error
views, the debug pages and the static file view answer.

    python recordings/views.py > recordings/views.txt

Chapter 7 of the book (pages/views.md and the pages under it) is written against this output.
It needs only the pinned Django (the project's virtual environment has it) and the small
project beside it, `gazette/`: a town's newspaper, with one model, views of every kind the
chapter describes, and a template for each view that renders one. The database is a SQLite
file made for the run. Run it again after a re-pin: where the output changes, the chapter
has to.

A block is one of three kinds. Where the order of calls is the point, the lines are calls,
nested as they were made. In the blocks about View and the generic views those are every
method of Django's generic views that ran, the project's own views, and the other functions
of Django's that the chapter names; the blocks about decorators, errors and the debug pages
write down the calls they are about and no others, and a block of several requests with a
line of words before each writes down only what each request came to. What a call returned
follows `->`, put into words at the moment it was returned; `raises` names an exception,
once, at the innermost written-down call it left: on the call's own line where nothing was
written down under the call, and otherwise on a line of its own under it. A call with
neither after it returned something the recording does not describe, or was left by an
exception already named further in. A method is written by the class that declares it,
whatever class the view is. Everything between the lines ran and is left out, and a function
behind `functools.lru_cache` or `cached_property` is written down only when its body runs:
where such a call is missing, the answer came out of the cache. The keys of a dictionary are
listed in alphabetical order. A line that begins `SQL` is a query as Django handed it to
the database's cursor, and one that begins `log` is a record given to one of Django's
loggers. The lines that begin `start_response` and `the server` are the script's own, playing
the server's part: of a response's headers it writes Location, Allow, and those a block is
about. A line that begins `signal` is written by a receiver of got_request_exception that
the script connects, and the lines of Stamp, Shut and announced by those parts of the
project themselves. A
second kind of block puts one question to a running Django on each line: the text before
`->` is the expression that was evaluated, or, where a few words stand there, they say of
what it was asked. The third kind writes down what an object holds.

The clock is the recording's own: `django.utils.timezone.now` is replaced by a function that
returns 10 April 2026, 09:00 UTC, so that what the date views decide by that function is the
same on every run. One article is dated after that moment. Two of the date views also read
`datetime.date.today()`, which is the machine's: TodayArchiveView is therefore not asked, and
DateDetailView only about days long past.

    RECORD_EVERYTHING=1 python recordings/views.py     every call in the chapter's modules
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# `gazette` imports from this directory, as it would from a project's. The directory goes last
# on the path and not first, where Python puts a script's own: `http.py` in it has the name of
# a package of the standard library, which Django imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE] + [HERE]

import atexit  # noqa: E402
import datetime  # noqa: E402
import io  # noqa: E402
import logging  # noqa: E402
import mimetypes  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from urllib.parse import urlencode  # noqa: E402

import django  # noqa: E402
from django.conf import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # the same bytes on every machine
EVERYTHING = bool(os.environ.get("RECORD_EVERYTHING"))

SCRATCH = tempfile.mkdtemp()
DATABASE = os.path.join(SCRATCH, "gazette.sqlite3")
FILES = os.path.join(HERE, "gazette", "files")
ERROR_PAGES = os.path.join(HERE, "gazette", "error_pages")
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True}]
TEMPLATES_WITH_404 = [{**TEMPLATES[0], "DIRS": [ERROR_PAGES]}]

settings.configure(
    DEBUG=False,
    SECRET_KEY="recording",
    ROOT_URLCONF="gazette.urls",
    ALLOWED_HOSTS=["gazette.example"],
    INSTALLED_APPS=["gazette"],
    MIDDLEWARE=[],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATABASE}},
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    TEMPLATES=TEMPLATES,
    USE_TZ=True,
    TIME_ZONE="UTC",
)
django.setup()

from inspect import iscoroutinefunction  # noqa: E402

from django.conf.urls.static import static  # noqa: E402
from django.core import signals  # noqa: E402
from django.core.handlers.wsgi import WSGIHandler, WSGIRequest  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.models import QuerySet  # noqa: E402
from django.db.transaction import non_atomic_requests  # noqa: E402
from django.http import HttpResponseBase  # noqa: E402
from django.shortcuts import get_list_or_404, get_object_or_404, redirect, render, resolve_url  # noqa: E402
from django.template.response import TemplateResponse  # noqa: E402
from django.test.utils import override_settings  # noqa: E402  (django.test connects the receivers of setting_changed)
from django.urls import get_resolver, path, resolve, reverse_lazy  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.decorators import method_decorator  # noqa: E402
from django.views import View, debug, defaults  # noqa: E402
from django.views import static as static_views  # noqa: E402
from django.views.decorators.cache import cache_control, never_cache  # noqa: E402
from django.views.decorators.clickjacking import xframe_options_exempt  # noqa: E402
from django.views.decorators.common import no_append_slash  # noqa: E402
from django.views.decorators.cache import cache_page  # noqa: E402
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie, requires_csrf_token  # noqa: E402
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables  # noqa: E402
from django.views.decorators.http import require_POST  # noqa: E402
from django.views import generic  # noqa: E402

NOW = datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.UTC)
timezone.now = lambda: NOW  # the recording's clock: see the docstring

LINES = []
STACK = []  # the watched frames open at this moment: the depth of the next line
AT = {}  # where in LINES the line of each open watched call is, by the frame
SEEN = set()  # generator and coroutine frames already written down: such a frame is entered more than once
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


# ---------------------------------------------------------------------------------------------
# How things are said. Nothing is written that differs between machines or runs: no address in
# memory, no path on disk, no time read from the machine's clock.

def a(name: str) -> str:
    """A thing by its class's name, with the article the name is read with."""
    return ("an " if name[0] in "AEIOU" or name.startswith("Http") else "a ") + name


def brief(value) -> str:
    """A value in few words: a date as its ISO text, a queryset without running it."""
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, QuerySet):
        return queryset_said(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k!r}: {brief(v)}" for k, v in value.items()) + "}"
    if isinstance(value, HttpResponseBase):
        return responded(None, value)
    return repr(value)


def queryset_said(queryset) -> str:
    """A queryset, without sending its query: asking for its repr would."""
    if queryset.query.is_empty():
        return f"an empty QuerySet of {queryset.model.__name__}: its query is marked empty"
    said = f"a QuerySet of {queryset.model.__name__}"
    if queryset.query.order_by:
        said += f", ordered by {', '.join(queryset.query.order_by)}"
    said += ", already fetched" if queryset._result_cache is not None else ", not yet fetched"
    return said


def responded(frame, value):
    if value is None:
        return "None"
    if asyncio_coroutine(value):
        return "a coroutine"
    said = f"{a(type(value).__name__)}, status {value.status_code}"
    if isinstance(value, TemplateResponse):
        said += ", rendered" if value.is_rendered else ", not rendered"
    for header in ("Location", "Allow"):
        if value.headers.get(header) is not None:
            said += f", {header} {value.headers[header]!r}"
    return said


def asyncio_coroutine(value) -> bool:
    import asyncio
    return asyncio.iscoroutine(value)


def keys(frame, value) -> str:
    return "a dict with the keys " + ", ".join(sorted(value))


def cls_of(frame) -> str:
    return type(frame.f_locals["self"]).__name__


def plain(frame) -> str:
    return frame.f_code.co_qualname


def given(frame, *skip) -> str:
    """The arguments of a call after the request, as they would be written."""
    code = frame.f_code
    names = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]
    said = [f"{name}={brief(frame.f_locals[name])}" for name in names if name not in ("self", "cls", "request", *skip)]
    if code.co_flags & 0x04:  # *args
        said += [brief(v) for v in frame.f_locals[code.co_varnames[len(names)]]]
    if code.co_flags & 0x08:  # **kwargs
        extra = frame.f_locals[code.co_varnames[len(names) + bool(code.co_flags & 0x04)]]
        said += [f"{k}={brief(v)}" for k, v in extra.items()]
    return ", ".join(said)


def view_made(frame) -> str:
    """View.__init__ runs for an instance being made: each such line is a new instance."""
    view = frame.f_locals["self"]
    kwargs = ", ".join(f"{k}={brief(v)}" for k, v in frame.f_locals["kwargs"].items())
    return f"View.__init__({kwargs})  (a new {type(view).__name__})"


def entered(frame) -> str:
    """The function that as_view returned."""
    said = given(frame)
    return f"view(request{', ' + said if said else ''})  (the function as_view returned for {frame.f_locals['cls'].__name__})"


# What to say of a call of a generic view's method: its arguments, where they tell.
ARGUMENTS = {
    "View.setup": lambda f: "request" + (", " + given(f) if given(f) else ""),
    "View.dispatch": lambda f: "request" + (", " + given(f) if given(f) else ""),
    "View.http_method_not_allowed": lambda f: "request",
    "View.options": lambda f: "request",
    "ContextMixin.get_context_data": lambda f: ", ".join(f"{k}=..." for k in f.f_locals["kwargs"]),
    "SingleObjectMixin.get_context_data": lambda f: ", ".join(f"{k}=..." for k in f.f_locals["kwargs"]),
    "MultipleObjectMixin.get_context_data": lambda f: ", ".join(
        [*(["object_list=..."] if f.f_locals["object_list"] is not None else []), *(f"{k}=..." for k in f.f_locals["kwargs"])]),
    "FormMixin.get_context_data": lambda f: ", ".join(f"{k}=..." for k in f.f_locals["kwargs"]),
    "SingleObjectMixin.get_object": lambda f: "" if f.f_locals["queryset"] is None else "queryset=...",
    "BaseDateDetailView.get_object": lambda f: "" if f.f_locals["queryset"] is None else "queryset=...",
    "FormMixin.get_form": lambda f: "",
    "FormMixin.form_valid": lambda f: "form",
    "ModelFormMixin.form_valid": lambda f: "form",
    "BaseDeleteView.form_valid": lambda f: "form",
    "FormMixin.form_invalid": lambda f: "form",
    "TemplateResponseMixin.render_to_response": lambda f: "context",
    "MultipleObjectMixin.paginate_queryset": lambda f: f"queryset, {f.f_locals['page_size']}",
    "MultipleObjectMixin.get_paginate_by": lambda f: "queryset",
    "MultipleObjectMixin.get_paginator": lambda f: f"queryset, {f.f_locals['per_page']}, orphans={f.f_locals['orphans']}, "
                                                   f"allow_empty_first_page={f.f_locals['allow_empty_first_page']}",
    "MultipleObjectMixin.get_context_object_name": lambda f: "object_list",
    "SingleObjectMixin.get_context_object_name": lambda f: "obj",
    "BaseDateListView.get_dated_queryset": lambda f: ", ".join(f"{k}={brief(v)}" for k, v in f.f_locals["lookup"].items()),
    "BaseDateListView.get_date_list": lambda f: "queryset" + (f", ordering={f.f_locals['ordering']!r}" if f.f_locals["ordering"] != "ASC" else ""),
    "DateMixin._make_date_lookup_arg": lambda f: brief(f.f_locals["value"]),
    "DateMixin._make_single_date_lookup": lambda f: brief(f.f_locals["date"]),
    "_date_from_string": lambda f: ", ".join(repr(f.f_locals[n]) for n in ("year", "year_format", "month", "month_format", "day", "day_format")
                                                if f.f_locals[n] != ""),
    "_get_next_prev": lambda f: f"view, {brief(f.f_locals['date'])}, is_previous={f.f_locals['is_previous']}, period={f.f_locals['period']!r}",
    "RedirectView.get_redirect_url": lambda f: given(f),
}
for _name in ("_get_next_year", "_get_current_year", "_get_next_month", "_get_current_month", "_get_next_day", "_get_current_day",
              "_get_next_week", "_get_current_week", "get_next_year", "get_previous_year", "get_next_month", "get_previous_month",
              "get_next_day", "get_previous_day", "get_next_week", "get_previous_week"):
    for _cls in ("YearMixin", "MonthMixin", "DayMixin", "WeekMixin"):
        ARGUMENTS[f"{_cls}.{_name}"] = lambda f: brief(f.f_locals["date"])


def generic_called(frame) -> str:
    qualname = frame.f_code.co_qualname
    if qualname == "View.as_view.<locals>.view":
        return entered(frame)
    if qualname == "View.__init__":
        return view_made(frame)
    said = ARGUMENTS.get(qualname)
    if said is None:
        if frame.f_code.co_name in VERBS:
            return f"{qualname}(request{', ' + given(frame) if given(frame) else ''})"
        return qualname
    return f"{qualname}({said(frame)})"


VERBS = ("get", "post", "put", "patch", "delete", "head", "trace")


def template_response(frame, value) -> str:
    return responded(frame, value)


def form_said(frame, value) -> str:
    return f"{a(type(value).__name__)}, {'bound' if value.is_bound else 'not bound'}"


def page_said(frame, value) -> str:
    paginator, page, object_list, more = value
    return f"(a {type(paginator).__name__}, {page!r}, the page's objects: {brief(object_list)}, {more})"


def dated_items(frame, value) -> str:
    date_list, object_list, extra = value
    if date_list is None:
        dates = "None"
    elif date_list._result_cache is None:
        dates = "a QuerySet, not yet fetched"
    else:
        dates = f"a QuerySet of {len(date_list)} {kind_of(date_list)}"
    return f"({dates}, {brief(object_list)}, {brief(extra)})"


def kind_of(fetched) -> str:
    """What a fetched list of dates holds: datetimes, or dates."""
    kinds = {type(one).__name__ for one in fetched}
    return "/".join(sorted(kinds)) + "s" if kinds else "items"


def date_list_said(frame, value) -> str:
    if value._result_cache is None:
        return "a QuerySet, not yet fetched"
    return f"a QuerySet of {kind_of(value)}, already fetched: " + ", ".join(brief(d) for d in value)


def as_is(frame, value) -> str:
    return brief(value)


# What to say of what a generic view's method returned, by the method's name.
RETURNED = {
    "get_object": as_is, "get_queryset": as_is, "get_dated_queryset": as_is,
    "get_context_data": keys, "get_form_kwargs": keys,
    "get_template_names": as_is, "get_success_url": as_is, "get_redirect_url": as_is,
    "render_to_response": template_response, "view": responded, "dispatch": responded,
    "http_method_not_allowed": responded, "options": responded,
    "form_valid": responded, "form_invalid": responded,
    **{verb: responded for verb in VERBS},
    "get_form": form_said, "get_form_class": lambda f, v: v.__name__,
    "paginate_queryset": page_said, "get_dated_items": dated_items, "get_date_list": date_list_said,
    "get_paginate_by": as_is, "get_allow_empty": as_is, "get_allow_future": as_is, "get_ordering": as_is,
    "get_context_object_name": as_is, "get_slug_field": as_is, "get_initial": as_is, "get_prefix": as_is,
    "get_date_field": as_is, "get_year": as_is, "get_month": as_is, "get_day": as_is,
    "get_year_format": as_is, "get_month_format": as_is, "get_day_format": as_is,
    "uses_datetime_field": as_is, "view_is_async": as_is, "_allowed_methods": as_is,
    "_date_from_string": as_is, "_get_next_prev": as_is, "_make_date_lookup_arg": as_is, "_make_single_date_lookup": as_is,
    "get_next_month": as_is, "get_previous_month": as_is, "_get_next_month": as_is, "_get_current_month": as_is,
    "get_date_list_period": as_is, "get_paginate_orphans": as_is, "get_make_object_list": as_is,
    "get_next_year": as_is, "get_previous_year": as_is, "_get_next_year": as_is, "_get_current_year": as_is,
    "get_paginator": lambda f, v: a(type(v).__name__),
}


def ours_called(frame) -> str:
    """A function or a method of the project's own views module."""
    qualname = frame.f_code.co_qualname
    said = given(frame)
    if frame.f_code.co_name == "form_valid":
        return f"{qualname}(form)"
    if "." in qualname:
        return f"{qualname}(request{', ' + said if said else ''})" if frame.f_code.co_name in VERBS else f"{qualname}({said})"
    return f"views.{qualname}(request{', ' + said if said else ''})"


def ours_returned(frame, value):
    if frame.f_code.co_name == "<module>":
        return None
    if frame.f_code.co_name == "edition_tag":
        return repr(value)
    if frame.f_code.co_name == "form_valid" or isinstance(value, HttpResponseBase) or value is None:
        return responded(frame, value)
    return None


def imported(frame) -> str:
    return f"import {frame.f_globals['__name__']}"


def as_view_called(frame) -> str:
    kwargs = ", ".join(f"{k}={brief(v)}" for k, v in frame.f_locals["initkwargs"].items())
    return f"{frame.f_locals['cls'].__name__}.as_view({kwargs})"


def as_view_returned(frame, value) -> str:
    return f"a function named {value.__name__!r}, with view_class {value.view_class.__name__} and view_initkwargs {brief(value.view_initkwargs)}"


def decorated_by_middleware(frame) -> str:
    view = frame.f_locals["view_func"]
    return f"the decorator made from {frame.f_locals['middleware_class'].__name__} is given {gazette.stamp.called(view)}"


def middleware_of(frame):
    """The middleware instance a wrapper made by make_middleware_decorator works with: the
    wrapper does not name it, the function it calls first does."""
    first = frame.f_locals["_pre_process_request"]
    return dict(zip(first.__code__.co_freevars, first.__closure__))["middleware"].cell_contents


def method_decorated(frame) -> str:
    f = frame.f_locals
    decorator = f["decorator"]
    name = "stamped" if decorator is gazette.stamp.stamped else getattr(decorator, "__name__", decorator)
    if isinstance(decorator, (list, tuple)):
        name = "[" + ", ".join(getattr(one, "__name__", str(one)) for one in decorator) + "]"
    return f"method_decorator({name}" + (f", name={f['name']!r})" if f["name"] else ")")


def conditional(frame) -> str:
    f = frame.f_locals
    return f"get_conditional_response(request, etag={f['etag']!r}, last_modified={f['last_modified']!r})"


def error_view(frame) -> str:
    exception = frame.f_locals.get("exception")
    return f"{frame.f_code.co_name}(request" + (f", {type(exception).__name__})" if exception is not None else ")")


BUILT_IN = {"get_traceback_html": "technical_500.html", "get_traceback_text": "technical_500.txt",
            "technical_404_response": "technical_404.html", "default_urlconf": "default_urlconf.html",
            "directory_index": "directory_index.html"}


def from_string(frame):
    """A template made from text and not found by a loader: say which text, by who asked."""
    asked = frame.f_back.f_code.co_name
    if asked in BUILT_IN:
        with open(os.path.join(os.path.dirname(debug.__file__), "templates", BUILT_IN[asked]), encoding="utf-8") as fh:
            same = fh.read() == frame.f_locals["template_code"]
        return f"Engine.from_string(the text of django/views/templates/{BUILT_IN[asked]})" if same else "Engine.from_string(some other text)"
    if asked == "page_not_found":
        return "Engine.from_string(ERROR_PAGE_TEMPLATE, filled in)"
    return None


def csrf_hook(frame) -> str:
    return f"{frame.f_code.co_qualname}  ({cls_of(frame)})"


def template_asked(frame) -> str:
    return f"get_template({frame.f_locals['template_name']!r})"


def frame_variables(frame) -> str:
    return f"SafeExceptionReporterFilter.get_traceback_frame_variables  (the frame of {frame.f_locals['tb_frame'].f_code.co_name})"


def variables_said(frame, value) -> str:
    return "{" + ", ".join(f"{name!r}: {v if isinstance(v, str) and set(v) == {'*'} else '...'}" for name, v in value) + "}"


def reporter_made(frame) -> str:
    f = frame.f_locals
    return f"ExceptionReporter.__init__(request, {f['exc_type'].__name__}, ..., is_email={f['is_email']})"


IMPORT = {
    ("gazette.urls", "<module>"): imported,
    ("gazette.views", "<module>"): imported,
    ("django.views.generic.base", "View.as_view"): as_view_called,
    ("django.utils.decorators", "make_middleware_decorator.<locals>._make_decorator.<locals>._decorator"): decorated_by_middleware,
    ("django.utils.decorators", "method_decorator"): method_decorated,
    ("django.utils.decorators", "_multi_decorate"): lambda f: f"_multi_decorate(decorators, {f.f_locals['method'].__qualname__})",
    ("django.utils.decorators", "_update_method_wrapper"): plain,
}

# A request for a view: the handler's call of it, and what the view's own machinery calls.
REQUEST = {
    "generic": True,
    "ours": True,
    ("django.core.handlers.base", "BaseHandler._get_response"): plain,
    ("django.template.response", "SimpleTemplateResponse.render"): plain,
    ("django.forms.forms", "BaseForm.is_valid"): plain,
    ("django.forms.models", "BaseModelForm.save"): plain,
    ("django.forms.models", "modelform_factory"): lambda f: f"modelform_factory({f.f_locals['model'].__name__}, fields={f.f_locals['fields']!r})",
    ("django.db.models.base", "Model.delete"): plain,
    ("django.core.paginator", "Paginator.page"): lambda f: f"Paginator.page({f.f_locals['number']!r})",
    ("gazette.models", "Article.get_absolute_url"): plain,
    ("django.core.handlers.exception", "response_for_exception"): lambda f: f"response_for_exception(request, {type(f.f_locals['exc']).__name__})",
}

# A request for a decorated view: each wrapper as it is entered.
WRAPPED = {
    "ours": True,
    ("django.core.handlers.base", "BaseHandler._get_response"): plain,
    ("django.views.generic.base", "View.as_view.<locals>.view"): entered,
    ("django.views.generic.base", "View.__init__"): view_made,
    ("django.views.generic.base", "View.setup"): lambda f: "View.setup(request)",
    ("django.views.generic.base", "View.dispatch"): lambda f: "View.dispatch(request)",
    ("django.views.decorators.http", "require_http_methods.<locals>.decorator.<locals>.inner"):
        lambda f: f"the wrapper require_http_methods made, for {f.f_locals['request_method_list']!r}",
    ("django.views.decorators.cache", "never_cache.<locals>._view_wrapper"): lambda f: "the wrapper never_cache made",
    ("django.views.decorators.vary", "vary_on_headers.<locals>.decorator.<locals>._view_wrapper"):
        lambda f: f"the wrapper vary_on_headers made, for {f.f_locals['headers']!r}",
    ("django.utils.cache", "add_never_cache_headers"): lambda f: "add_never_cache_headers(response)",
    ("django.utils.cache", "patch_vary_headers"): lambda f: f"patch_vary_headers(response, {f.f_locals['newheaders']!r})",
    ("django.views.decorators.http", "condition.<locals>.decorator.<locals>.inner"): lambda f: "the wrapper condition made",
    ("django.utils.cache", "get_conditional_response"): conditional,
    ("django.utils.decorators", "make_middleware_decorator.<locals>._make_decorator.<locals>._decorator.<locals>._view_wrapper"):
        lambda f: f"the wrapper made from {type(middleware_of(f)).__name__}",
    ("django.utils.decorators", "make_middleware_decorator.<locals>._make_decorator.<locals>._decorator"): decorated_by_middleware,
    ("django.utils.decorators", "_multi_decorate.<locals>._wrapper"): lambda f: "the wrapper method_decorator made",
    ("django.template.response", "SimpleTemplateResponse.add_post_render_callback"): plain,
    ("django.template.response", "SimpleTemplateResponse.render"): plain,
    ("django.core.handlers.exception", "response_for_exception"): lambda f: f"response_for_exception(request, {type(f.f_locals['exc']).__name__})",
}

# An exception becomes a page: the error views and the debug pages.
ERRORS = {
    "ours": True,
    ("django.core.handlers.base", "BaseHandler._get_response"): plain,
    ("django.core.handlers.exception", "response_for_exception"): lambda f: f"response_for_exception(request, {type(f.f_locals['exc']).__name__})",
    ("django.core.handlers.exception", "get_exception_response"): lambda f: f"get_exception_response(request, resolver, {f.f_locals['status_code']}, exception)",
    ("django.core.handlers.exception", "handle_uncaught_exception"): lambda f: "handle_uncaught_exception(request, resolver, exc_info)",
    ("django.urls.resolvers", "URLResolver.resolve_error_handler"): lambda f: f"URLResolver.resolve_error_handler({f.f_locals['view_type']!r})",
    ("django.utils.decorators", "make_middleware_decorator.<locals>._make_decorator.<locals>._decorator.<locals>._view_wrapper"):
        lambda f: f"the wrapper made from {type(middleware_of(f)).__name__}",
    ("django.middleware.csrf", "CsrfViewMiddleware.process_request"): csrf_hook,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_view"): csrf_hook,
    ("django.middleware.csrf", "CsrfViewMiddleware.process_response"): csrf_hook,
    ("django.views.defaults", "page_not_found"): error_view,
    ("django.views.defaults", "server_error"): error_view,
    ("django.views.defaults", "bad_request"): error_view,
    ("django.views.defaults", "permission_denied"): error_view,
    ("django.template.loader", "get_template"): template_asked,
    ("django.template.engine", "Engine.from_string"): from_string,
    ("django.views.debug", "technical_500_response"): lambda f: f"technical_500_response(request, {f.f_locals['exc_type'].__name__}, ..., status_code={f.f_locals['status_code']})",
    ("django.views.debug", "technical_404_response"): lambda f: "technical_404_response(request, exception)",
    ("django.views.debug", "default_urlconf"): lambda f: "default_urlconf(request)",
    ("django.views.debug", "get_exception_reporter_class"): plain,
    ("django.views.debug", "get_exception_reporter_filter"): plain,
    ("django.views.debug", "get_default_exception_reporter_filter"): plain,
    ("django.views.debug", "get_caller"): plain,
    ("django.views.debug", "ExceptionReporter.__init__"): reporter_made,
    ("django.views.debug", "ExceptionReporter.get_traceback_html"): plain,
    ("django.views.debug", "ExceptionReporter.get_traceback_text"): plain,
    ("django.views.debug", "ExceptionReporter.get_traceback_data"): plain,
    ("django.views.debug", "ExceptionReporter.get_traceback_frames"): plain,
    ("django.views.debug", "SafeExceptionReporterFilter.get_traceback_frame_variables"): frame_variables,
    ("django.views.debug", "SafeExceptionReporterFilter.get_safe_request_meta"): plain,
    ("django.views.debug", "SafeExceptionReporterFilter.get_safe_cookies"): plain,
    ("django.views.debug", "SafeExceptionReporterFilter.get_post_parameters"): plain,
    ("django.views.debug", "SafeExceptionReporterFilter.get_safe_settings"): plain,
    ("django.views.debug", "SafeExceptionReporterFilter.is_active"): plain,
    ("django.http.request", "HttpRequest.get_preferred_type"): lambda f: f"HttpRequest.get_preferred_type({f.f_locals['media_types']!r})",
}

RULES = {}  # the set in force

# (module, qualname) -> what to say of the value a call returned.
AFTER = {
    ("django.views.generic.base", "View.as_view"): as_view_returned,
    ("django.views.generic.base", "View.as_view.<locals>.view"): responded,
    ("django.views.generic.base", "View.dispatch"): responded,
    ("django.core.handlers.exception", "response_for_exception"): responded,
    ("django.core.handlers.exception", "get_exception_response"): responded,
    ("django.core.handlers.exception", "handle_uncaught_exception"): responded,
    ("django.utils.cache", "get_conditional_response"): responded,
    ("django.views.decorators.http", "require_http_methods.<locals>.decorator.<locals>.inner"): responded,
    ("django.views.decorators.http", "condition.<locals>.decorator.<locals>.inner"): responded,
    ("django.views.decorators.cache", "never_cache.<locals>._view_wrapper"): responded,
    ("django.views.decorators.vary", "vary_on_headers.<locals>.decorator.<locals>._view_wrapper"): responded,
    ("django.utils.decorators", "make_middleware_decorator.<locals>._make_decorator.<locals>._decorator.<locals>._view_wrapper"): responded,
    ("django.utils.decorators", "_multi_decorate.<locals>._wrapper"): responded,
    ("django.forms.forms", "BaseForm.is_valid"): as_is,
    ("django.forms.models", "BaseModelForm.save"): as_is,
    ("django.forms.models", "modelform_factory"): lambda f, v: f"the class {v.__name__}",
    ("django.core.paginator", "Paginator.page"): as_is,
    ("gazette.models", "Article.get_absolute_url"): as_is,
    ("django.urls.resolvers", "URLResolver.resolve_error_handler"): lambda f, v: f"{v.__module__}.{v.__name__}",
    ("django.views.defaults", "page_not_found"): responded,
    ("django.views.defaults", "server_error"): responded,
    ("django.views.defaults", "bad_request"): responded,
    ("django.views.defaults", "permission_denied"): responded,
    ("django.views.debug", "technical_500_response"): lambda f, v: f"{responded(f, v)}, Content-Type {v.headers['Content-Type']!r}",
    ("django.views.debug", "technical_404_response"): responded,
    ("django.views.debug", "default_urlconf"): responded,
    ("django.views.debug", "get_exception_reporter_class"): lambda f, v: f"the class {v.__name__}",
    ("django.views.debug", "get_exception_reporter_filter"): lambda f, v: a(type(v).__name__),
    ("django.views.debug", "get_default_exception_reporter_filter"): lambda f, v: a(type(v).__name__),
    ("django.views.debug", "get_caller"): as_is,
    ("django.views.debug", "SafeExceptionReporterFilter.get_traceback_frame_variables"): variables_said,
    ("django.views.debug", "SafeExceptionReporterFilter.is_active"): as_is,
    ("django.http.request", "HttpRequest.get_preferred_type"): as_is,
}

OURS = ("django.views", "django.shortcuts", "gazette")
GENERIC = "django.views.generic."


def find(module: str, qualname: str):
    label = RULES.get((module, qualname))
    if label is not None:
        return label
    if "<" in qualname and qualname != "View.as_view.<locals>.view":
        return None
    if RULES.get("generic") and module.startswith(GENERIC) and qualname != "View.as_view":
        return generic_called
    if RULES.get("ours") and module == "gazette.views":
        return ours_called
    if EVERYTHING and module.startswith(OURS):
        return plain
    return None


def after_of(module: str, code):
    found = AFTER.get((module, code.co_qualname))
    if found is None and module.startswith(GENERIC):
        found = RETURNED.get(code.co_name)
    if found is None and module == "gazette.views":
        found = ours_returned
    return found


def profile(frame, event, arg):
    code = frame.f_code
    if code is UNWINDING:
        return
    if event == "call":
        label = find(frame.f_globals.get("__name__", ""), code.co_qualname)
        if label is None:
            return
        if code.co_flags & RESUMABLE:  # every resumption is a call event
            if id(frame) in SEEN:
                STACK.append(frame)
                return
            SEEN.add(id(frame))
        flush()  # what the call before this one returned is said first: a label may depend on it
        try:
            text = label(frame)
        except Exception:  # a fault of this script's: Python would drop the hook and carry on, and the recording would be short
            import traceback
            traceback.print_exc()
            os._exit(1)
        if text is None:
            return
        note(text)
        AT[id(frame)] = len(LINES) - 1
        STACK.append(frame)
    elif event == "return":
        if STACK and STACK[-1] is frame:
            flush()
            after = None if code.co_flags & RESUMABLE else after_of(frame.f_globals.get("__name__", ""), code)
            # The value is put into words now, as it is returned: a dictionary its caller goes on to
            # add to would otherwise be described as the caller left it.
            try:
                said = after(frame, arg) if after else None
            except Exception:
                if arg is not None:  # a fault of this script's
                    import traceback
                    traceback.print_exc()
                    os._exit(1)
                said = None  # an exception is leaving the frame, and unwinding() is about to say so
            PENDING.append((frame, len(STACK), AT.pop(id(frame), -1), said))
            STACK.pop()


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
sys.monitoring.use_tool_id(MONITOR, "recordings/views.py")
sys.monitoring.register_callback(MONITOR, sys.monitoring.events.PY_UNWIND, unwinding)
sys.monitoring.set_events(MONITOR, sys.monitoring.events.PY_UNWIND)


class recorded:
    """`with recorded(REQUEST):` writes down, of what runs in the block, the calls those
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


def _raises():
    raise KeyError("probe")


def self_test() -> None:
    """The line `raises X` depends on the profile hook being told of a return before
    sys.monitoring reports the unwinding. Prove it on this Python before anything is recorded."""
    global RULES
    with recorded({("__main__", "_raises"): plain}):
        try:
            _raises()
        except KeyError:
            pass
    if LINES != ["_raises  raises KeyError"]:
        raise SystemExit(f"recordings/views.py: this Python reports an exception leaving a function otherwise than expected: {LINES!r}")
    LINES.clear()
    RAISED.clear()
    RULES = {}


self_test()

ASKING = {}  # the names an asked expression may use


class Said(str):
    """An answer already put into words, to be written as it is and not as a string's repr."""


def ask(expression: str, brief_: bool = False, show_as: str = "") -> None:
    """One question and its answer, on one line. The question is evaluated as it is written
    down, so the line cannot say one thing and the script do another. A brief answer names an
    exception and leaves out its message."""
    watching = sys.getprofile()
    sys.setprofile(None)  # a question is its answer and nothing else: no calls are written down under it
    flush()
    before = len(LINES)
    try:
        value = eval(expression, ASKING)
        said = value if isinstance(value, Said) else answered(value)
    except Exception as raised:
        said = f"raises {type(raised).__name__}" + ("" if brief_ else f": {raised}")
    # A log record made while the question was answered stands under the question, not above it.
    LINES[before:] = ["  " * len(STACK) + f"{show_as or expression}  ->  {said}", *("  " + line for line in LINES[before:])]
    sys.setprofile(watching)


def answered(value) -> str:
    """An answer: a response by its class, its status and what it carries; anything else by
    its repr."""
    if not isinstance(value, HttpResponseBase):
        return repr(value)
    said = [a(type(value).__name__), f"status {value.status_code}"]
    for header in ("Location", "Allow", "Content-Type", "Last-Modified", "Content-Encoding"):
        if value.headers.get(header) is not None and (header != "Content-Type" or WITH_TYPE):
            said.append(f"{header} {value.headers[header]!r}")
    if isinstance(value, TemplateResponse) and not value.is_rendered:
        said.append("not rendered")
    elif not value.streaming:
        text = value.content.decode()
        if "<body>" in text:  # a whole page: what stands between its body tags, its white space run together
            said.append(f"between its body tags, white space run together: {' '.join(text.split('<body>')[1].split('</body>')[0].split())}")
        else:
            said.append(f"content {text!r}")
    if value.streaming:
        value.close()
    return ", ".join(said)


WITH_TYPE = False  # whether an answer that is a response says its Content-Type


# ---------------------------------------------------------------------------------------------
# What is written down besides calls: queries, log records, the recording's middleware.

def query(execute, sql, params, many, context):
    note(f"SQL {sql} with params {params!r}")
    return execute(sql, params, many, context)


class Noted(logging.Handler):
    def emit(self, record):
        note(f"log, {record.levelname} to {record.name}: {record.getMessage()}")


logging.getLogger("django").addHandler(Noted())


def uncaught(sender, **kwargs):
    exception = sys.exc_info()[1]
    note(f"signal got_request_exception, for {type(exception).__name__}: {exception}")


signals.got_request_exception.connect(uncaught)

import gazette.stamp  # noqa: E402

gazette.stamp.SAY.append(note)

# ---------------------------------------------------------------------------------------------
# The server's part.

def environ(url: str, method: str = "GET", data: dict | None = None, **more) -> dict:
    path_info, _, query_string = url.partition("?")
    body = urlencode(data).encode() if data is not None else b""
    made = {
        "REQUEST_METHOD": method, "PATH_INFO": path_info, "QUERY_STRING": query_string, "SCRIPT_NAME": "",
        "SERVER_NAME": "gazette.example", "SERVER_PORT": "80", "SERVER_PROTOCOL": "HTTP/1.1",
        "HTTP_HOST": "gazette.example", "wsgi.url_scheme": "http", "wsgi.input": io.BytesIO(body),
    }
    if data is not None:
        made["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
        made["CONTENT_LENGTH"] = str(len(body))
    made.update(more)
    return made


def serve(handler, env: dict, rules: dict, headers: tuple = (), body: bool = True) -> None:
    """Call the handler as a WSGI server does: start the response, send the body, close it.
    `headers` names the response's headers to write down beside its status."""
    def start_response(status, response_headers):
        sent = dict(response_headers)
        said = [f"{name}: {sent[name]}" for name in ("Location", "Allow", *headers) if name in sent]
        note(f'start_response("{status}", headers)' + (", with " + ", ".join(said) if said else ""))

    with recorded(rules):
        try:
            result = handler(env, start_response)
        except Exception as raised:
            note(f"the handler raises {type(raised).__name__} to the server: {raised}")
            return
        content = b"".join(result)
        if env["REQUEST_METHOD"] == "HEAD":
            note(f"what the handler returned has a body of {len(content)} bytes")
        elif body:
            text = content.decode()
            note(f"the server sends the body: {text!r}" if len(text) < 100 else f"the server sends the body, {len(content)} bytes")
        result.close()


def request(url: str = "/", method: str = "GET", data: dict | None = None, **more):
    """A request object of the kind the handler makes, for a question that needs one."""
    return WSGIRequest(environ(url, method, data, **more))


print(f"Django {django.get_version()} and the project gazette: ROOT_URLCONF = 'gazette.urls', no middleware unless a block says so,\n"
      "DEBUG = False unless a block says so, and the clock at 2026-04-10 09:00 UTC\n")

handler = WSGIHandler()


def tidy() -> None:
    connection.close()
    shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(tidy)

# The table and its rows.
from gazette.models import Article  # noqa: E402

with connection.schema_editor() as editor:
    editor.create_model(Article)


def at(month: int, day: int, hour: int) -> datetime.datetime:
    return datetime.datetime(2026, month, day, hour, 0, tzinfo=datetime.UTC)


Article.objects.bulk_create([
    Article(slug="lost-cat", headline="Lost: a grey cat, Quay Street", published=at(1, 9, 8)),
    Article(slug="found-cat", headline="Found: a grey cat", published=at(1, 12, 8)),
    Article(slug="harbour-wall", headline="Harbour wall to be rebuilt", published=at(2, 27, 9)),
    Article(slug="ferry-timetable", headline="New ferry timetable", published=at(3, 3, 8)),
    Article(slug="lighthouse-open-day", headline="Lighthouse open day", published=at(3, 14, 10)),
    Article(slug="council-budget", headline="Council passes budget", published=at(3, 28, 18)),
    Article(slug="spring-fair", headline="Spring fair dates set", published=at(4, 2, 12)),
    Article(slug="may-day", headline="May Day programme", published=at(5, 1, 7)),
])
ferry = Article.objects.get(slug="ferry-timetable")


def rows(title: str) -> None:
    """A block that lists the table's rows: later blocks add, change and delete some."""
    for article in Article.objects.order_by("published"):
        note(f"{article.published:%Y-%m-%d %H:%M} UTC  {article.slug}: {article.headline}")
    show(title)


rows("The Gazette's articles as the recording begins, by the moment each was published")
connection.execute_wrappers.append(query)

# ---------------------------------------------------------------------------------------------
# The URLconf is imported: every as_view() and every decorator runs once.

with recorded(IMPORT):
    root = get_resolver()
    root.url_patterns
show("The URLconf is imported: each as_view() is called once; the decorators made from a middleware, and method_decorator, as they run")

from gazette import views  # noqa: E402

ASKING.update(
    views=views, View=View, generic=generic, path=path, resolve=resolve, reverse_lazy=reverse_lazy, request=request,
    iscoroutinefunction=iscoroutinefunction, method_decorator=method_decorator, Article=Article,
    csrf_exempt=csrf_exempt, csrf_protect=csrf_protect, no_append_slash=no_append_slash, non_atomic_requests=non_atomic_requests,
    never_cache=never_cache, cache_control=cache_control, require_POST=require_POST, xframe_options_exempt=xframe_options_exempt,
    sensitive_variables=sensitive_variables, sensitive_post_parameters=sensitive_post_parameters,
    resolve_url=resolve_url, redirect=redirect, render=render, get_object_or_404=get_object_or_404, get_list_or_404=get_list_or_404,
    TemplateResponse=TemplateResponse, defaults=defaults, debug=debug, static=static, settings=settings, Said=Said,
)

# ---------------------------------------------------------------------------------------------
# What the URLconf holds, and how a view is named.

ask('resolve("/").func is views.front')
ask('resolve("/").func.__name__')
ask('resolve("/")._func_path')
ask('resolve("/colophon/").func.__name__')
ask('resolve("/colophon/").func.__qualname__')
ask('resolve("/colophon/").func.view_class')
ask('resolve("/colophon/")._func_path')
ask('resolve("/colophon/").view_name')
ask('resolve("/colophon/").func is resolve("/colophon/large/").func')
ask('resolve("/colophon/large/").func.view_initkwargs')
ask('type(resolve("/almanac/").func).__name__')
ask('resolve("/almanac/")._func_path')
ask('type(resolve("/tide/").func).__name__')
ask('resolve("/tide/")._func_path')
ask('resolve("/tide/").view_name')
ASKING["get_resolver"] = get_resolver
ask('next(p for p in get_resolver().url_patterns if p.name == "colophon").lookup_str', show_as="the lookup_str of the pattern named colophon")
show("What the resolver hands the handler, for each kind of view in the Gazette's URLconf")

ask('views.Colophon.as_view().__doc__')
ask('views.Colophon.as_view().__module__')
ask('views.Colophon.as_view(type_size=14).view_initkwargs')
ask('views.Colophon.as_view(colour="red")')
ask('views.Colophon.as_view(get=None)')
ask('views.Colophon().as_view')
ask('path("colophon/", views.Colophon())')
ask('[error.id for error in path("colophon/", views.Colophon).check()]')
ask('views.Colophon.as_view()(request("/colophon/"))')
ask('views.Colophon(type_size=30).type_size')
show("as_view(): what it accepts, what it refuses, and what it leaves on the function")

# ---------------------------------------------------------------------------------------------
# A class-based view is called.

note("GET /nothing/, a function that returns None")
serve(handler, environ("/nothing/"), {}, body=False)
note("GET /blank/, a class whose get returns None")
serve(handler, environ("/blank/"), {}, body=False)
note("GET /almanac/blank/, an object whose __call__ returns None")
serve(handler, environ("/almanac/blank/"), {}, body=False)
show("A view that returns None: how the handler names the view in its complaint")

note("GET /headline/, a function that returns a string, with no middleware")
serve(handler, environ("/headline/"), {}, body=False)
settings.MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
with_common = WSGIHandler()
note("the same request with CommonMiddleware installed")
serve(with_common, environ("/headline/"), {}, body=False)
settings.MIDDLEWARE = []
show("A view that returns something that is not a response")

serve(handler, environ("/colophon/"), REQUEST)
note("and the same request again")
serve(handler, environ("/colophon/"), REQUEST)
show("GET /colophon/, twice: a class-based view is a function that makes an instance for each request")

serve(handler, environ("/colophon/large/"), REQUEST)
show("GET /colophon/large/: the arguments given to as_view() are given to each instance")

serve(handler, environ("/colophon/", "HEAD"), REQUEST)
show("HEAD /colophon/: a class with get and no head")

serve(handler, environ("/colophon/", "OPTIONS"), REQUEST)
show("OPTIONS /colophon/: answered by View.options")

serve(handler, environ("/colophon/", "PUT"), REQUEST)
show("PUT /colophon/: the class has no method of that name")

serve(handler, environ("/colophon/", "PROPFIND"), REQUEST)
show("PROPFIND /colophon/: a method that is not in http_method_names")

# ---------------------------------------------------------------------------------------------
# Decorators.

serve(handler, environ("/masthead/"), WRAPPED, headers=("Vary", "Cache-Control"))
show("GET /masthead/: three decorators around one function")

serve(handler, environ("/masthead/", "POST", {}), WRAPPED, headers=("Vary", "Cache-Control"))
show("POST /masthead/: the outermost wrapper answers, and nothing inside it runs")

note("views.front is a function with no decorators; request(...) makes a request as the handler would, for a path, a method and posted data")
ask("csrf_exempt(views.front).csrf_exempt")
ask("csrf_exempt(views.front) is views.front")
ask('hasattr(views.front, "csrf_exempt")')
ask("csrf_exempt(views.front).__wrapped__ is views.front")
ask("csrf_exempt(views.front).__name__")
ask("no_append_slash(views.front).should_append_slash")
ask("non_atomic_requests(views.front)._non_atomic_requests")
ask('non_atomic_requests(using="archive")(non_atomic_requests(views.front))._non_atomic_requests == {"default", "archive"}')
ask("never_cache(csrf_exempt(views.front)).csrf_exempt")
ask('hasattr(views.bare(csrf_exempt(views.front)), "csrf_exempt")')
ask("xframe_options_exempt(views.front)(request()).xframe_options_exempt")
ask('sensitive_post_parameters("password")(views.front)(posted := request("/", "POST", {})) and posted.sensitive_post_parameters',
    show_as='after sensitive_post_parameters("password")(views.front) is called with a request: request.sensitive_post_parameters')
ask("never_cache(views.front)('not a request')")
ask("sensitive_variables(views.front)")
show("What a decorator leaves behind: on the view, on the response, on the request")

ask("views.Tips.as_view().csrf_exempt")
ask("views.Tips.dispatch.csrf_exempt")
ask('hasattr(views.TipsMarkedOnPost.as_view(), "csrf_exempt")')
ask("views.TipsMarkedOnPost.post.csrf_exempt")
ask("views.Tips.dispatch is View.dispatch")
ask("views.Tips.dispatch.__name__")
ask("method_decorator(never_cache).__name__")
ask('method_decorator(never_cache, name="render")(views.Tips)', brief_=True)
ask("method_decorator([never_cache, csrf_exempt])(View.dispatch).csrf_exempt")
show("as_view() copies what decorators left on dispatch; a mark on post stays on post")

serve(handler, environ("/births/"), WRAPPED)
note("and the same request again")
serve(handler, environ("/births/"), WRAPPED)
show("GET /births/, twice: a decorator on dispatch is applied again at every call")

settings.MIDDLEWARE = ["django.middleware.csrf.CsrfViewMiddleware"]
guarded = WSGIHandler()
note("POST /tips/, whose class has csrf_exempt on dispatch")
serve(guarded, environ("/tips/", "POST", {"tip": "the ferry is late"}), {}, body=False)
note("POST /tips/marked/, whose class has csrf_exempt on post")
serve(guarded, environ("/tips/marked/", "POST", {"tip": "the ferry is late"}), {}, body=False)
settings.MIDDLEWARE = []
show("POST /tips/ and POST /tips/marked/ with CsrfViewMiddleware installed and no token sent")

# ---------------------------------------------------------------------------------------------
# A middleware made into a decorator.

serve(handler, environ("/notices/"), WRAPPED)
show("GET /notices/: a view decorated with a middleware")

serve(handler, environ("/notices/page/"), WRAPPED)
show("GET /notices/page/: the decorated view returns a TemplateResponse")

serve(handler, environ("/notices/lost/"), WRAPPED)
show("GET /notices/lost/: the decorated view raises")

serve(handler, environ("/notices/shut/"), WRAPPED)
show("GET /notices/shut/: the middleware's process_request answers")

serve(handler, environ("/crossword/"), WRAPPED)
note("and the same request again")
serve(handler, environ("/crossword/"), WRAPPED)
show("GET /crossword/, twice: method_decorator applies its decorator again at every call")

ASKING.update(ensure_csrf_cookie=ensure_csrf_cookie, requires_csrf_token=requires_csrf_token, cache_page=cache_page)
ask('csrf_protect(views.front)(request("/", "POST", {})).status_code')
ask('requires_csrf_token(views.front)(request("/", "POST", {})).status_code')
ask('"csrftoken" in views.front(request()).cookies')
ask('"csrftoken" in csrf_protect(views.front)(request()).cookies')
ask('"csrftoken" in ensure_csrf_cookie(views.front)(request()).cookies')
ask('cache_page(60)(views.front)(request()).headers["Cache-Control"]')
ask("csrf_protect.__name__")
show("The decorators Django makes from its own middleware")

serve(handler, environ("/edition/"), WRAPPED, headers=("ETag",))
show("GET /edition/: a view under condition()")

serve(handler, environ("/edition/", HTTP_IF_NONE_MATCH='"edition-7"'), WRAPPED, headers=("ETag",))
show('GET /edition/ with If-None-Match: "edition-7"')

serve(handler, environ("/edition/", "PUT", HTTP_IF_MATCH='"edition-6"'), WRAPPED, headers=("ETag",))
show('PUT /edition/ with If-Match: "edition-6"')

# ---------------------------------------------------------------------------------------------
# Views that are coroutines.

ask("iscoroutinefunction(views.front)")
ask("iscoroutinefunction(views.wire)")
ask("views.Colophon.view_is_async")
ask("views.Wire.view_is_async")
ask("iscoroutinefunction(views.Wire.as_view())")
ask("iscoroutinefunction(views.Colophon.as_view())")
ask("View.view_is_async")
ask("views.Muddle.view_is_async")
ask("views.Muddle.as_view()")
ask("iscoroutinefunction(never_cache(views.wire))")
ask("iscoroutinefunction(csrf_exempt(views.wire))")
ask('iscoroutinefunction(require_POST(views.wire))')
ask("iscoroutinefunction(non_atomic_requests(views.wire))")
ask('iscoroutinefunction(method_decorator(never_cache)(views.Wire.get))')
ask("iscoroutinefunction(views.counted(views.wire))")
ask("iscoroutinefunction(views.wire_counted)")
ask("iscoroutinefunction(views.bare(views.wire))")
ask("iscoroutinefunction(views.counted(views.Wire.as_view()))")
ask("iscoroutinefunction(views.bare(views.Wire.as_view()))")
show("Which views are coroutine functions, and which decorators keep them so")

note("GET /wire/, an async def function")
serve(handler, environ("/wire/"), {})
note("GET /wire/class/, a class whose get is async def")
serve(handler, environ("/wire/class/"), {})
note("OPTIONS /wire/class/")
serve(handler, environ("/wire/class/", "OPTIONS"), {}, body=False)
note("PUT /wire/class/")
serve(handler, environ("/wire/class/", "PUT"), {}, body=False)
note("GET /wire/class/counted/, the function as_view returned for that class, inside a wrapper that is an ordinary function")
serve(handler, environ("/wire/class/counted/"), {})
note("GET /wire/counted/, an async def function inside the same kind of wrapper")
serve(handler, environ("/wire/counted/"), {}, body=False)
show("Views that are coroutine functions, requested through a WSGIHandler")

# ---------------------------------------------------------------------------------------------
# The shortcuts.

ASKING["ferry"] = ferry

ask('resolve_url("/articles/")')
ask('resolve_url("articles")')
ask('resolve_url("article", slug="ferry-timetable")')
ask('resolve_url("article", "ferry-timetable")')
ask("resolve_url(views.front)")
ask("resolve_url(ferry)", show_as="resolve_url(ferry), where ferry is the Article with the slug 'ferry-timetable'")
ask('resolve_url(ferry, slug="ignored")', show_as='resolve_url(ferry, slug="ignored")')
ask('resolve_url("./next/")')
ask('resolve_url("../")')
ask('resolve_url("https://example.org/")')
ask('resolve_url("gazette.example")')
ask('resolve_url("no-such-name")', brief_=True)
ask('resolve_url("no such/name")')
ask('resolve_url(reverse_lazy("articles"))')
ask("resolve_url(views.nothing, 7)", brief_=True)
show("resolve_url(): an object, a name, or a URL")

ask('redirect("articles")')
ask('redirect("article", slug="ferry-timetable")')
ask("redirect(ferry)")
ask('redirect("articles", permanent=True)')
ask('redirect("articles", preserve_request=True)')
ask('redirect("articles", permanent=True, preserve_request=True)')
ask('redirect("https://example.org/")')
ask('redirect("javascript:alert(1)")')
show("redirect(): the response it makes")

ask('render(request(), "gazette/front.html", {"edition": 7})')
ask('render(request(), "gazette/front.html", {"edition": 7}, status=203)')
ask('TemplateResponse(request(), "gazette/front.html", {"edition": 7})')
ask('render(request(), "gazette/no-such.html")', brief_=True)
ask('TemplateResponse(request(), "gazette/no-such.html")')
show("render() returns a response already rendered; a TemplateResponse is made unrendered")

connection.execute_wrappers.remove(query)
note("(the queries these questions send are not written down)")
ask('get_object_or_404(Article, slug="ferry-timetable")')
ask('get_object_or_404(Article.objects, slug="ferry-timetable")')
ask('get_object_or_404(Article.objects.filter(published__month=3), slug="ferry-timetable")')
ask('get_object_or_404(Article.objects.filter(published__month=4), slug="ferry-timetable")')
ask('get_object_or_404(Article, slug="no-such-article")')
ask('get_object_or_404(Article, headline__contains="cat")', brief_=True)
ask('get_object_or_404("Article", slug="ferry-timetable")')
ask('get_list_or_404(Article.objects.order_by("published"), headline__contains="cat")')
ask('get_list_or_404(Article, headline__contains="dog")')
ask('type(get_list_or_404(Article.objects.order_by("slug"), published__month=3)).__name__')
show("get_object_or_404() and get_list_or_404()")
connection.execute_wrappers.append(query)

# ---------------------------------------------------------------------------------------------
# The generic views.


def mro(view) -> Said:
    return Said(" > ".join(c.__name__ for c in view.__mro__ if c is not object))


ASKING["mro"] = mro
for name in ("TemplateView", "RedirectView", "DetailView", "ListView", "FormView", "CreateView", "UpdateView", "DeleteView",
             "ArchiveIndexView", "YearArchiveView", "MonthArchiveView", "WeekArchiveView", "DayArchiveView", "TodayArchiveView",
             "DateDetailView"):
    ask(f"mro(generic.{name})", show_as=name)
show("The method resolution order of each generic view, without object, the last of each")


def supplies(view, names) -> None:
    """For each name, the first class in the view's method resolution order that declares it."""
    for name in names:
        owner = next((c.__name__ for c in view.__mro__ if name in vars(c)), "no class")
        note(f"{name}  ->  {owner}")


supplies(generic.DetailView, ("as_view", "setup", "dispatch", "get", "get_object", "get_queryset", "get_slug_field", "get_context_data",
                              "get_context_object_name", "render_to_response", "get_template_names"))
show("DetailView: which class supplies each method")

supplies(generic.UpdateView, ("get", "post", "put", "get_object", "get_form", "get_form_class", "get_form_kwargs", "get_initial",
                              "form_valid", "form_invalid", "get_success_url", "get_context_data", "render_to_response",
                              "get_template_names"))
show("UpdateView: which class supplies each method")

supplies(generic.DeleteView, ("get", "post", "delete", "get_object", "get_form", "get_form_class", "form_valid", "form_invalid",
                              "get_success_url", "get_context_data", "get_template_names"))
show("DeleteView: which class supplies each method")

supplies(generic.MonthArchiveView, ("get", "get_dated_items", "get_year", "get_month", "get_dated_queryset", "get_date_list",
                                    "get_queryset", "get_ordering", "get_next_month", "get_previous_month", "get_context_data",
                                    "render_to_response", "get_template_names"))
show("MonthArchiveView: which class supplies each method")

serve(handler, environ("/about/"), REQUEST)
show("GET /about/: a TemplateView made in the URLconf")

serve(handler, environ("/news/"), REQUEST)
show("GET /news/: a RedirectView with a pattern_name")

serve(handler, environ("/news/ferry-timetable/?ref=front"), REQUEST)
show("GET /news/ferry-timetable/?ref=front: a RedirectView that is permanent and keeps the query string")

serve(handler, environ("/weather/"), REQUEST)
show("GET /weather/: a RedirectView with nowhere to send the request")

serve(handler, environ("/articles/ferry-timetable/"), REQUEST)
show("GET /articles/ferry-timetable/: a DetailView")

serve(handler, environ("/articles/no-such-article/"), REQUEST, body=False)
show("GET /articles/no-such-article/: the DetailView finds no object")

serve(handler, environ("/articles/?page=2"), REQUEST)
show("GET /articles/?page=2: a ListView that paginates")

serve(handler, environ("/articles/?page=9"), REQUEST, body=False)
show("GET /articles/?page=9: a page the list does not have")

serve(handler, environ("/letters/"), REQUEST)
show("GET /letters/: a FormView shows its form")

serve(handler, environ("/letters/", "POST", {"name": "A. Reader", "letter": "Too short."}), REQUEST)
show("POST /letters/ with a letter that is too short: the form is not valid")

serve(handler, environ("/letters/", "POST", {"name": "A. Reader", "letter": "The ferry has been late every day this week."}), REQUEST)
note(f"the view's own form_valid put the name in views.RECEIVED: {views.RECEIVED!r}")
show("POST /letters/ with a letter the form accepts")

serve(handler, environ("/articles/new/", "POST", {"slug": "regatta", "headline": "Regatta results", "published": "2026-04-05 17:00"}), REQUEST)
show("POST /articles/new/: a CreateView saves a new object")

serve(handler, environ("/articles/regatta/edit/"), REQUEST)
show("GET /articles/regatta/edit/: an UpdateView shows the form for an object")

serve(handler, environ("/articles/regatta/edit/", "POST", {"headline": "Regatta results, corrected"}), REQUEST)
show("POST /articles/regatta/edit/: an UpdateView saves the object")

serve(handler, environ("/articles/lost-cat/delete/"), REQUEST)
show("GET /articles/lost-cat/delete/: a DeleteView asks first")

serve(handler, environ("/articles/lost-cat/delete/", "POST", {}), REQUEST)
show("POST /articles/lost-cat/delete/: a DeleteView deletes through its form")

serve(handler, environ("/articles/found-cat/delete/", "DELETE"), REQUEST)
show("DELETE /articles/found-cat/delete/: the same view, by the method DELETE")

connection.execute_wrappers.remove(query)
rows("The Gazette's articles by now: one was added and changed, and two were deleted")
connection.execute_wrappers.append(query)

serve(handler, environ("/archive/2026/3/"), REQUEST)
show("GET /archive/2026/3/: a MonthArchiveView")

serve(handler, environ("/archive/2026/4/"), REQUEST)
show("GET /archive/2026/4/: the month the clock is in; the one article dated after the clock is in May")

serve(handler, environ("/archive/2026/"), REQUEST)
show("GET /archive/2026/: a YearArchiveView, which lists months and, unless told to, no articles")

serve(handler, environ("/archive/2025/12/"), REQUEST, body=False)
show("GET /archive/2025/12/: a month with no articles")

serve(handler, environ("/archive/2026/13/"), REQUEST, body=False)
show("GET /archive/2026/13/: a month that is not one")
connection.execute_wrappers.remove(query)

STANDARD = ("view", "paginator", "page_obj", "is_paginated", "article", "article_list")


def context(view_class, init=None, **kwargs) -> Said:
    """What one of the date views puts in the context: the view is made for the model Article
    and its field published, and called; the keys every list or detail view has are left out,
    and each queryset is listed, an article by its slug."""
    response = view_class.as_view(model=Article, date_field="published", **(init or {}))(request(), **kwargs)
    said = []
    for key, value in sorted(response.context_data.items()):
        if key in STANDARD:
            continue
        if isinstance(value, QuerySet):
            value = [one.slug if isinstance(one, Article) else brief(one) for one in value]
            said.append(f"{key} = [{', '.join(value)}]")
        else:
            said.append(f"{key} = {value.slug if isinstance(value, Article) else brief(value)}")
    return Said("; ".join(said))


ASKING["context"] = context
note("context(V, attributes, **from_the_path) makes the view V.as_view(model=Article, date_field=\"published\", **attributes), calls it with")
note("a GET request and the arguments given, and lists what the response's context holds: an article by its slug, the context's")
note(f"keys in alphabetical order, and without the keys {', '.join(STANDARD)}.")
note("The queries are not written down. TodayArchiveView is not asked, and DateDetailView only about days long past: both read")
note("the machine's date, datetime.date.today(), which the recording's clock does not replace.")
STACK.append(None)
ask("context(generic.ArchiveIndexView)")
ask("context(generic.YearArchiveView, year=2026)")
ask('context(generic.YearArchiveView, {"make_object_list": True}, year=2026)')
ask('context(generic.MonthArchiveView, year=2026, month="mar")')
ask("context(generic.WeekArchiveView, year=2026, week=10)")
ask('context(generic.DayArchiveView, year=2026, month="mar", day=14)')
ask('context(generic.DayArchiveView, year=2026, month="mar", day=15)')
ask('context(generic.DayArchiveView, {"allow_empty": True}, year=2026, month="mar", day=15)')
ask('context(generic.DateDetailView, year=2026, month="mar", day=14, slug="lighthouse-open-day")')
ask('context(generic.DateDetailView, year=2026, month="mar", day=15, slug="lighthouse-open-day")')
ask('context(generic.MonthArchiveView, {"allow_future": True}, year=2026, month="may")')
ask('context(generic.MonthArchiveView, year=2026, month="may")')
ask('context(generic.MonthArchiveView, year=2026, month="3")')
ask('context(generic.WeekArchiveView, {"week_format": "%V"}, year=2026, week=10)')
STACK.pop()
show("The date views: what each puts in the context, for the model Article and its field published")
connection.execute_wrappers.append(query)

# ---------------------------------------------------------------------------------------------
# The error views.

serve(handler, environ("/no-such-page/"), ERRORS)
show("GET /no-such-page/ with DEBUG = False and no template named 404.html")

with override_settings(TEMPLATES=TEMPLATES_WITH_404):
    serve(handler, environ("/no-such-page/"), ERRORS)
    show("GET /no-such-page/ with DEBUG = False and a template named 404.html")

    serve(handler, environ("/articles/no-such-article/"), ERRORS)
    show("GET /articles/no-such-article/ with a template named 404.html: the message of the Http404 a view raised")

serve(handler, environ("/editions/1790/"), ERRORS)
show("GET /editions/1790/ with DEBUG = False: the view raises LookupError")

from django.core.exceptions import BadRequest, PermissionDenied  # noqa: E402
from django.http import Http404  # noqa: E402

ASKING.update(Http404=Http404, PermissionDenied=PermissionDenied, BadRequest=BadRequest)
ask('defaults.page_not_found(request("/x y/"), Http404("no such edition"))')
ask('defaults.page_not_found(request("/x y/"), Http404())')
ask('defaults.page_not_found(request("/x y/"), Http404({"path": "x y/", "tried": []}))')
ask('defaults.page_not_found(request(), Http404(), template_name="gazette/gone.html")', brief_=True)
ask('defaults.permission_denied(request(), PermissionDenied("subscribers only"))')
ask('defaults.bad_request(request(), BadRequest("no"))')
ask("defaults.server_error(request())")
with override_settings(TEMPLATES=TEMPLATES_WITH_404):
    ask('defaults.page_not_found(request("/x y/"), Http404("no such edition"))',
        show_as='with a template named 404.html: defaults.page_not_found(request("/x y/"), Http404("no such edition"))')
show("The four error views, called directly")

# ---------------------------------------------------------------------------------------------
# The debug pages.

settings.DEBUG = True
serve(handler, environ("/editions/1790/", HTTP_ACCEPT="text/html"), ERRORS, headers=("Content-Type",), body=False)
show("GET /editions/1790/ with DEBUG = True and Accept: text/html")

serve(handler, environ("/editions/1790/", HTTP_ACCEPT="application/json"), ERRORS, headers=("Content-Type",), body=False)
show("GET /editions/1790/ with DEBUG = True and Accept: application/json")

serve(handler, environ("/no-such-page/"), ERRORS, headers=("Content-Type",), body=False)
show("GET /no-such-page/ with DEBUG = True")

with override_settings(ROOT_URLCONF=()):
    serve(handler, environ("/"), ERRORS, headers=("Content-Type",), body=False)
    show("GET / with DEBUG = True and a URLconf that has no patterns")
settings.DEBUG = False


def page_type(**headers) -> str:
    """The Content-Type of the page technical_500_response makes for a request with these headers."""
    return debug.technical_500_response(request(**headers), LookupError, LookupError("no edition"), None)["Content-Type"]


ASKING["page_type"] = page_type
note("page_type(...) is the Content-Type of what technical_500_response returns for a request with the headers given")
STACK.append(None)
ask("page_type()")
ask('page_type(HTTP_ACCEPT="*/*")')
ask('page_type(HTTP_ACCEPT="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")')
ask('page_type(HTTP_ACCEPT="text/plain")')
ask('page_type(HTTP_ACCEPT="application/json")')
ask('page_type(HTTP_ACCEPT="text/plain, text/html")')
STACK.pop()
show("technical_500_response: HTML or plain text, by the request's Accept header")


def reporter_for(view, asked, is_email):
    """The reporter for what the view raises. This function's frame is the first of the
    traceback, so it holds nothing but the view, the request and a flag."""
    try:
        view(asked, year=1790)
    except Exception:
        return debug.ExceptionReporter(asked, *sys.exc_info(), is_email=is_email)


def html(view, debug_on: bool, post: dict | None = None) -> str:
    """The HTML report an ExceptionReporter writes for what a view raised, with DEBUG as given:
    made as the debug page makes it when DEBUG is on, and as the handler that emails the site's
    administrators makes it (is_email=True) when DEBUG is off."""
    with override_settings(DEBUG=debug_on):
        asked = request("/editions/1790/", "POST" if post is not None else "GET", post)
        return reporter_for(view, asked, not debug_on).get_traceback_html()


def text(view, debug_on: bool, post: dict | None = None) -> str:
    """The same report as plain text."""
    with override_settings(DEBUG=debug_on):
        asked = request("/editions/1790/", "POST" if post is not None else "GET", post)
        return reporter_for(view, asked, not debug_on).get_traceback_text()


def lookup():
    return {}["edition"]


def chained():
    try:
        lookup()
    except KeyError as missing_key:
        raise LookupError("no edition") from missing_key


def frames() -> list:
    try:
        chained()
    except LookupError:
        return debug.ExceptionReporter(None, *sys.exc_info()).get_traceback_frames()


guarded_view = sensitive_variables("password")(views.missing)
all_guarded_view = sensitive_variables()(views.missing)
post_guarded_view = sensitive_post_parameters("pin")(views.till)
ASKING.update(html=html, text=text, guarded=guarded_view, all_guarded=all_guarded_view, post_guarded=post_guarded_view, frames=frames)
note("views.missing has two local variables whose values are 'open sesame' (password) and 'the attic' (shelf), neither written out")
note("whole in its source, and raises LookupError;")
note('guarded is sensitive_variables("password")(views.missing), and all_guarded is sensitive_variables()(views.missing);')
note("views.till has one local variable, posted = request.POST, and raises LookupError;")
note('post_guarded is sensitive_post_parameters("pin")(views.till);')
note("html(view, DEBUG) and text(view, DEBUG) are the two reports an ExceptionReporter writes for what the view raised, with the")
note("setting DEBUG as given: with DEBUG True the reporter is made as for the debug page, and with DEBUG False as for the email")
note("to the site's administrators (is_email=True), which by default carries the text report alone. The text report shows no")
note("frame's variables at all, whatever the setting. The third argument of html and text is what was posted.")
STACK.append(None)
ask('"open sesame" in html(views.missing, True)')
ask('"open sesame" in text(views.missing, True)')
ask('"open sesame" in html(views.missing, False)')
ask('"open sesame" in text(views.missing, False)')
ask('"the attic" in text(views.missing, False)')
ask('"open sesame" in html(guarded, False)')
ask('"the attic" in html(guarded, False)')
ask('"open sesame" in html(guarded, True)')
ask('"the attic" in html(all_guarded, False)')
ask('"fourteen-ninety-two" in text(views.till, False, {"pin": "fourteen-ninety-two", "note": "urgent"})')
ask('"fourteen-ninety-two" in html(views.till, False, {"pin": "fourteen-ninety-two", "note": "urgent"})')
ask('"fourteen-ninety-two" in text(post_guarded, False, {"pin": "fourteen-ninety-two", "note": "urgent"})')
ask('"fourteen-ninety-two" in html(post_guarded, False, {"pin": "fourteen-ninety-two", "note": "urgent"})')
ask('"urgent" in text(post_guarded, False, {"pin": "fourteen-ninety-two", "note": "urgent"})')
ask('"fourteen-ninety-two" in text(post_guarded, True, {"pin": "fourteen-ninety-two", "note": "urgent"})')
ask('"SECRET_KEY = \'********************\'" in text(views.missing, True)')
STACK.pop()
show("What a report shows of a frame's variables and of the posted data")

note("lookup() raises KeyError; chained() calls it, catches the KeyError and raises LookupError from it;")
note("frames() calls chained(), catches the LookupError, and returns what ExceptionReporter.get_traceback_frames makes of it:")
note("the third frame is that of frames() itself, where the LookupError was caught")
STACK.append(None)
ask('[(frame["function"], type(frame["exc_cause"]).__name__, bool(frame["exc_cause_explicit"])) for frame in frames()]')
ask('[frame["type"] for frame in frames()]')
ask('sorted(frames()[0])')
STACK.pop()
show("The frames of a report, when one exception was raised from another")

filter_ = debug.SafeExceptionReporterFilter()
ASKING["filter"] = filter_
note("filter is a SafeExceptionReporterFilter(), and request(...) a request with the headers given")
ask("filter.cleansed_substitute")
ask('filter.cleanse_setting("SECRET_KEY", "recording")')
ask('filter.cleanse_setting("TIME_ZONE", "UTC")')
ask('filter.cleanse_setting("PASSENGERS", 12)')
ask('filter.cleanse_setting("API_URL", "https://api.example/")')
ask('filter.cleanse_setting("DATABASES", {"default": {"NAME": "gazette", "PASSWORD": "s3cret"}})')
ask('filter.cleanse_setting("ADMINS", [{"email": "editor@gazette.example", "token": "t0ken"}])')
ask('filter.cleanse_setting("LOGIN_URL", len)')
ask('type(filter.cleanse_setting("LOGIN_URL", len)).__name__')
ask('settings.SESSION_COOKIE_NAME')
ask('filter.cleanse_setting("sessionid", "abc123")')
ask('filter.get_safe_request_meta(request(HTTP_COOKIE="sessionid=abc123", HTTP_X_API_KEY="k3y"))["HTTP_COOKIE"]')
ask('filter.get_safe_request_meta(request(HTTP_COOKIE="sessionid=abc123", HTTP_X_API_KEY="k3y"))["HTTP_X_API_KEY"]')
ask('filter.get_safe_request_meta(request(HTTP_COOKIE="sessionid=abc123", HTTP_X_API_KEY="k3y"))["HTTP_HOST"]')
ask('filter.get_safe_cookies(request(HTTP_COOKIE="sessionid=abc123; theme=dark"))')
ask("filter.is_active(request())")
with override_settings(DEBUG=True):
    ask("filter.is_active(request())", show_as="with DEBUG = True: filter.is_active(request())")
show("SafeExceptionReporterFilter: what is replaced by stars")

# ---------------------------------------------------------------------------------------------
# The static file view.

mimetypes.add_type("text/plain", ".txt")  # what most machines say already; on Windows the registry decides, so the script does
MODIFIED = 1767268800  # 1 January 2026, 12:00 UTC: the files are given this time, so that it is the same on every machine
for folder, _, names in os.walk(FILES):
    for one in names:
        os.utime(os.path.join(folder, one), (MODIFIED, MODIFIED))

serve_ = static_views.serve
ASKING.update(serve=serve_, FILES=FILES, static_views=static_views, re=__import__("re"))
WITH_TYPE = True
note("FILES is a directory that holds masthead.txt, a file named .proofs, and a directory, issues, with one file in it;")
note("the script has set each file's modification time to 1 January 2026, 12:00:00 UTC, and told Python's mimetypes, which")
note("the view asks, that .txt is text/plain")
STACK.append(None)
ask('serve(request(), "masthead.txt", document_root=FILES)')
ask('b"".join(serve(request(), "masthead.txt", document_root=FILES))')
ask('serve(request(HTTP_IF_MODIFIED_SINCE="Thu, 01 Jan 2026 12:00:00 GMT"), "masthead.txt", document_root=FILES)')
ask('serve(request(HTTP_IF_MODIFIED_SINCE="Thu, 01 Jan 2026 11:59:59 GMT"), "masthead.txt", document_root=FILES)')
ask('serve(request(HTTP_IF_MODIFIED_SINCE="yesterday"), "masthead.txt", document_root=FILES)')
ask('serve(request(), "issues/1871-01-07.txt", document_root=FILES)')
ask('serve(request(), "issues/../masthead.txt", document_root=FILES)')
ask('serve(request(), "/masthead.txt", document_root=FILES)')
ask('serve(request(), "../views.py", document_root=FILES)', brief_=True)
ask('serve(request(), "no-such-file.txt", document_root=FILES)', brief_=True)
ask('serve(request(), "issues", document_root=FILES)')
ask('serve(request(), "issues", document_root=FILES, show_indexes=True).status_code')
ask('sorted(re.findall(\'href="([^"]*)"\', serve(request(), "issues", document_root=FILES, show_indexes=True).content.decode()))')
ask('sorted(re.findall(\'href="([^"]*)"\', serve(request(), "", document_root=FILES, show_indexes=True).content.decode()))')
ask('serve(request(), "masthead.txt")', brief_=True)
ask('static_views.was_modified_since("Thu, 01 Jan 2026 12:00:00 GMT", 1767268800.9)')
ask('static_views.was_modified_since("Thu, 01 Jan 2026 12:00:00 GMT", 1767268801)')
ask("static_views.was_modified_since(None, 1767268800)")
STACK.pop()
show("django.views.static.serve: what it answers")
WITH_TYPE = False

ask('static("/media/", document_root=FILES)')
ask('static("", document_root=FILES)', brief_=True)
with override_settings(DEBUG=True):
    note("with DEBUG = True")
    STACK.append(None)
    ask('static("/media/", document_root=FILES)')
    ask('static("/media/", document_root=FILES)[0].callback is serve')
    ask('static("/media/", document_root=FILES)[0].default_args == {"document_root": FILES}')
    ask('static("https://cdn.example/media/", document_root=FILES)')
    STACK.pop()
show("static(): the pattern that routes a prefix to the view, made only when DEBUG is true")
