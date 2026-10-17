"""The habits of the section "What changed in handlers, requests, URLs and views", release by
release: what Django's own middleware declares, and how many calls a request through startproject's
middleware, and through none, hands from the event loop to a thread; the thread an error view runs on under ASGI,
the cookies of an ASGI request, `JsonResponse` without and with its safe argument, the
multipart parser's Base64 and the class a request parses multipart data with, the redirects'
new arguments and limit, and a converter registered twice. Run by recordings/changes.py under each release; _run.py says how a habit is written.
"""
from _run import configure, habit, main

configure()


@habit("CommonMiddleware.async_capable")
def async_capable():
    from django.middleware.common import CommonMiddleware
    return repr(CommonMiddleware.async_capable)


STARTPROJECT_MIDDLEWARE = [  # MIDDLEWARE as startproject writes it, the same in every release recorded
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


def handoffs(middleware):
    """One GET under ASGI to a synchronous view: how many calls the request hands from the event
    loop to a thread, counted at asgiref's SyncToAsync.__call__, through which every such handoff
    of Django's goes; the class is restored afterwards."""
    import asyncio
    import sys
    import types

    from asgiref import sync
    from django.core.handlers.asgi import ASGIHandler
    from django.http import HttpResponse
    from django.test.utils import override_settings
    from django.urls import path

    def entries(request):
        return HttpResponse("entries")

    urls = types.ModuleType("journal_handoffs")
    urls.urlpatterns = [path("entries/", entries)]
    sys.modules["journal_handoffs"] = urls
    scope = {"type": "http", "method": "GET", "path": "/entries/", "query_string": b"",
             "headers": [(b"host", b"journal.example")]}
    sent, counted = [], []

    async def serve(handler):
        received = []

        async def receive():
            if not received:
                received.append(True)
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()  # the client never disconnects

        async def send(message):
            sent.append(message)

        await handler(scope, receive, send)

    original = sync.SyncToAsync.__call__

    async def counting(self, *args, **kwargs):
        counted.append(1)
        return await original(self, *args, **kwargs)

    with override_settings(ROOT_URLCONF="journal_handoffs", MIDDLEWARE=middleware, ALLOWED_HOSTS=["journal.example"]):
        handler = ASGIHandler()  # the chain is built here, before the counting starts
        sync.SyncToAsync.__call__ = counting
        try:
            asyncio.run(serve(handler))
        finally:
            sync.SyncToAsync.__call__ = original
    assert sent[0]["status"] == 200
    return f"{len(counted)} calls handed to a thread"


@habit("A GET under ASGI through startproject's MIDDLEWARE to a synchronous view: the calls handed to a thread")
def handoffs_through_startproject_middleware():
    return handoffs(STARTPROJECT_MIDDLEWARE)


@habit("The same GET with MIDDLEWARE empty: the calls handed to a thread")
def handoffs_with_no_middleware():
    return handoffs([])


@habit("handler500 under ASGI, when a synchronous view raises: the thread it runs on")
def error_view_thread():
    import asyncio
    import sys
    import threading
    import types

    from django.core.handlers.asgi import ASGIHandler
    from django.http import HttpResponse
    from django.test.utils import override_settings
    from django.urls import path

    threads = {}

    def failing(request):
        threads["view"] = threading.get_ident()
        raise ValueError("no such entry")

    def server_error(request):
        threads["handler500"] = threading.get_ident()
        return HttpResponse("error", status=500)

    urls = types.ModuleType("journal_errors")
    urls.urlpatterns = [path("fail/", failing)]
    urls.handler500 = server_error
    sys.modules["journal_errors"] = urls
    scope = {"type": "http", "method": "GET", "path": "/fail/", "query_string": b"", "headers": []}
    sent = []

    async def serve():
        received = []

        async def receive():
            if not received:
                received.append(True)
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()  # the client never disconnects

        async def send(message):
            sent.append(message)

        await ASGIHandler()(scope, receive, send)

    with override_settings(ROOT_URLCONF="journal_errors"):
        asyncio.run(serve())
    assert sent[0]["status"] == 500
    return "the view's thread" if threads["handler500"] == threads["view"] else "another thread"


@habit('request.COOKIES under ASGI, sent as two "cookie" headers: year=2026 and order=newest')
def asgi_cookies():
    import io

    from django.core.handlers.asgi import ASGIRequest

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/entries/2026/",
        "headers": [(b"cookie", b"year=2026"), (b"cookie", b"order=newest")],
    }
    return repr(ASGIRequest(scope, io.BytesIO()).COOKIES)


@habit("JsonResponse([1, 2]).content")
def json_response_of_a_list():
    from django.http import JsonResponse
    return repr(JsonResponse([1, 2]).content)


@habit("JsonResponse([1, 2], safe=False).content")
def json_response_not_safe():
    from django.http import JsonResponse
    return repr(JsonResponse([1, 2], safe=False).content)


def multipart(disposition, payload):
    """A POST whose one multipart part is sent with Content-Transfer-Encoding: base64."""
    from django.test import RequestFactory

    body = (
        "--journal\r\n"
        f"Content-Disposition: form-data; {disposition}\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        f"{payload}\r\n"
        "--journal--\r\n"
    )
    return RequestFactory().post(
        "/entries/", data=body.encode(), content_type="multipart/form-data; boundary=journal"
    )


@habit('request.POST["title"]: a multipart field sent as base64, "TW9u!ZGF5"')
def base64_field_invalid():
    request = multipart('name="title"', "TW9u!ZGF5")
    return repr(request.POST["title"])


@habit('request.FILES["notes"].read(): a file sent as base64, "TW9u!ZGF5"')
def base64_file_invalid():
    request = multipart('name="notes"; filename="notes.txt"', "TW9u!ZGF5")
    return repr(request.FILES["notes"].read())


@habit('request.POST["body"]: a multipart field sent as base64 over two lines, "TW9u" and "ZGF5"')
def base64_field_in_lines():
    request = multipart('name="body"', "TW9u\r\nZGF5")
    return repr(request.POST["body"])


@habit("HttpRequest().multipart_parser_class")
def multipart_parser_class():
    from django.http import HttpRequest
    return repr(HttpRequest().multipart_parser_class)


@habit('RedirectView.as_view(url="/entries/2026/", preserve_request=True)(request).status_code: a POST')
def redirect_view_preserving():
    from django.test import RequestFactory
    from django.views.generic import RedirectView

    view = RedirectView.as_view(url="/entries/2026/", preserve_request=True)
    return repr(view(RequestFactory().post("/entries/")).status_code)


@habit('HttpResponseRedirect("/entries/" + "x" * 20000, max_length=None).status_code')
def redirect_without_limit():
    from django.http import HttpResponseRedirect
    return repr(HttpResponseRedirect("/entries/" + "x" * 20000, max_length=None).status_code)


@habit('HttpResponseRedirect("/entries/" + "é" * 3000).status_code: within the limit until it is encoded')
def redirect_limit_encoded():
    from django.http import HttpResponseRedirect
    return repr(HttpResponseRedirect("/entries/" + "é" * 3000).status_code)


@habit('register_converter(YearConverter, "int"): a name Django already defines')
def converter_registered_twice():
    from django.urls import converters, register_converter

    class YearConverter:
        regex = "[0-9]{4}"

        def to_python(self, value):
            return int(value)

        def to_url(self, value):
            return "%04d" % value

    try:
        register_converter(YearConverter, "int")
        return type(converters.get_converters()["int"]).__name__
    finally:
        from django.urls.resolvers import _route_to_regex

        converters.REGISTERED_CONVERTERS.pop("int", None)
        converters.get_converters.cache_clear()
        _route_to_regex.cache_clear()


main()
