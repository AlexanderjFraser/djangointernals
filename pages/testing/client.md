---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The test client: `Client` and `ClientHandler`

The test client, `Client`, sends a request through the project's middleware and views by a handler of its own, `ClientHandler`, with no server, and returns the response with what the request left behind: the templates rendered and their contexts, the exception reported where it is not raised in the test, the match of the URL, the redirects followed. `AsyncClient` and `AsyncClientHandler` do the same under ASGI.

`Client` is a `RequestFactory` whose `Client.request` hands the environ to the handler where the factory's would make a `WSGIRequest` ([Building a request: `RequestFactory`](request-factory.md)), and a `ClientMixin`, which holds what it shares with `AsyncClient`, the logins among it ([Sessions and logins in the test client: `ClientMixin.login` and `force_login`](client-login.md)). `Client.__init__` takes `enforce_csrf_checks=False` and `raise_request_exception=True` by default, and makes the handler (`django/test/client.py:Client.__init__`).

## One request, in order

`Client.get`, like the client's other methods by HTTP method, keeps its extra environ keys and headers on the client, where `assertRedirects` reads them ([Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`](response-assertions.md)), builds the request with the factory's method of the same name, and with `follow=True` follows redirects (`django/test/client.py:Client.get`). In the order a run printed it:

```text figure=the-client
client.get("/ships/")
  Client.get               extra keys and headers kept on the client
    RequestFactory.get, RequestFactory.generic
      Client.request
        _base_environ      the environ
        connect            store_rendered_templates to template_rendered,
                           store_exc_info to got_request_exception
        ClientHandler.__call__
          load_middleware  at the client's first request only
          request_started  sent with close_old_connections off
          WSGIRequest      marked to pass the CSRF check
          get_response     the middleware, then ship_list
            render "office/ship_list.html"   template_rendered
            render "office/base.html"        template_rendered
          conditional_content_removal
          wsgi_request     set on the response
          close            request_finished, close_old_connections off
        disconnect         both receivers, in a finally
        check_exception    exc_info set: None, no exception reported
        response           client, request, templates, context, json, resolver_match set
        cookies            none set by the response, none kept
```

*One `Client.get` of `"/ships/"` as it ran: the factory's methods build the environ, `Client.request` listens while `ClientHandler` plays the server, and the response is annotated on the way back.*

## The harbour office's tests of the client

A test module of the office, with a view that raises in a URLconf of its own:

```python
# harbour/office/tests/test_client.py
from django.test import Client, TestCase, override_settings
from django.urls import include, path

from harbour.fleet.models import Port, Ship


def broken(request):
    raise LookupError("no berth for Endeavour")


urlpatterns = [path("broken/", broken), path("", include("harbour.urls"))]


@override_settings(ROOT_URLCONF=__name__)
class ClientTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        valletta = Port.objects.create(name="Valletta", country="Malta")
        cls.endeavour = Ship.objects.create(name="Endeavour", tonnage=366, home=valletta)

    def test_list(self):
        response = self.client.get("/ships/")
        self.assertEqual([t.name for t in response.templates], ["office/ship_list.html", "office/base.html"])
        self.assertQuerySetEqual(response.context["ships"], [self.endeavour])

    def test_exception(self):
        with self.assertRaisesMessage(LookupError, "no berth for Endeavour"):
            self.client.get("/broken/")
        response = Client(raise_request_exception=False).get("/broken/")
        self.assertEqual(response.status_code, 500)
        self.assertIs(response.exc_info[0], LookupError)

    def test_follow(self):
        response = self.client.get("/ships/new/", follow=True)
        self.assertEqual(response.redirect_chain, [("/accounts/login/?next=/ships/new/", 302)])

    def test_chain_is_kept(self):
        self.client.get("/ships/")
        with self.settings(MIDDLEWARE=[]):
            kept = self.client.get("/ships/")
            fresh = Client().get("/ships/")
        self.assertTrue(hasattr(kept.wsgi_request, "session"))
        self.assertFalse(hasattr(fresh.wsgi_request, "session"))
```

```text
$ python manage.py test harbour.office.tests.test_client
Found 4 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
....
----------------------------------------------------------------------
Ran 4 tests in 0.027s

OK
Destroying test database for alias 'default'...
```

## Listening while the handler runs: `Client.request`

`Client.request` builds the environ with `RequestFactory._base_environ` and connects two receivers before it calls the handler, disconnecting both in a `finally`. To `template_rendered`, which the test environment's render of a template sends as the template begins ([The test environment: `setup_test_environment`](environment.md)), it connects `store_rendered_templates` bound to a new dictionary, which keeps each template and a copy of its context, made, the docstring says, to be accurate at the time of rendering. To `got_request_exception` it connects `ClientMixin.store_exc_info`, which keeps `sys.exc_info()` on the client (`django/test/client.py:Client.request`).

## The server's part: `ClientHandler.__call__`

`ClientHandler` is a `BaseHandler` whose `__call__` takes the environ and returns the response object itself (`django/test/client.py:ClientHandler.__call__`):

1. If `BaseHandler._middleware_chain` is still `None`, it calls `BaseHandler.load_middleware`, which, a comment says, could not be done earlier, the settings not being available. So the chain is built from `MIDDLEWARE` as it is at the client's first request, and kept, as test_chain_is_kept shows ([Building the middleware chain](../handlers/chain.md)).
2. It sends `request_started` with `close_old_connections` disconnected, so that receiver closes none of the test's connections ([Opening and closing a connection](../backends/lifecycle.md)).
3. It makes a `WSGIRequest` and sets `"_dont_enforce_csrf_checks"` on it, true unless the client enforces the check: a "sneaky little hack", the comment says, probably required for backwards compatibility with external tests of the admin's views ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md)).
4. `BaseHandler.get_response` runs the chain.
5. `conditional_content_removal` empties the body of a response to a `"HEAD"` and of a 1xx, 204 or 304, as, its docstring says, most web servers do; the headers stay.
6. It sets `HttpResponseBase.wsgi_request`.
7. It closes the response, which sends `request_finished`, `close_old_connections` again off. A streaming response is closed instead by a wrapper of its content, an async one's by an async wrapper, once that has been read through (`django/test/client.py:closing_iterator_wrapper`, `django/test/client.py:aclosing_iterator_wrapper`).

Unlike `WSGIHandler.__call__` ([The two entry points](../handlers/entry.md)), it sets no script prefix: under a `Client` given `SCRIPT_NAME="/app"`, the request's path begins "/app/", and `reverse` in the view still returns "/ships/".

## What the response carries

Then `Client.request` gives the response `HttpResponseBase.client`; `HttpResponseBase.request`, the keys `RequestFactory.generic` passed, not the whole environ; `HttpResponseBase.templates`, in the order they began to render, a page before the template it extends; `HttpResponseBase.context`; `HttpResponseBase.json`; and `HttpResponseBase.resolver_match`, attributes no response class declares. The response's cookies are merged into the client's, for its next request.

`context` is a `ContextList` of the copies, a list that looks a string key up in each context in turn (`django/test/utils.py:ContextList`). Where one render was reported, its context replaces the list, a step the comment keeps only for backwards compatibility; where none was, `context` is `None`.

`json` is `ClientMixin._parse_json` bound to the response. It raises `ValueError` unless the Content-Type begins `"application/json"`, or `"application/"` and a subtype with the suffix `"+json"`, and keeps what it parsed: a second call returns that, whatever its arguments (`django/test/client.py:ClientMixin._parse_json`).

`resolver_match` is a `SimpleLazyObject` that, when first read, calls `resolve` on the request's `"PATH_INFO"`, with the URLconf set on the request if any (`django/test/client.py:Client.request`; [Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)). It does not reuse the handler's match: a path that matches nothing raises `Resolver404` when the object is first used ([Resolving a path](../urls/resolving.md)).

## Exceptions: `got_request_exception` and `raise_request_exception`

The handler turns an exception raised in the chain into a response ([How an exception becomes a response](../handlers/exceptions.md)), so the client learns of one only by `got_request_exception`, sent where an exception is about to become a 500. An `Http404`, a `PermissionDenied`, a `BadRequest`, a `SuspiciousOperation` or a `MultiPartParserError` reaches the test only as the 4xx response made for it, and an exception a middleware's `process_exception` answered only as that answer (`django/core/handlers/exception.py:response_for_exception`).

`ClientMixin.check_exception` sets `HttpResponseBase.exc_info`, the kept triple or `None`, clears the client's, and raises the exception if `raise_request_exception=True` (`django/test/client.py:ClientMixin.check_exception`). By then the request has run to its end, the 500 response and the middleware's way out included, and the test gets the exception itself, with its traceback, in place of the response; with `raise_request_exception=False`, it gets the 500.

## Following redirects

With `follow=True`, `Client._handle_redirects` gives the first response an empty `HttpResponseBase.redirect_chain` and, while the status is 301, 302, 303, 307 or 308, follows the redirect, carries the chain over and checks it (`django/test/client.py:Client._handle_redirects`). `ClientMixin._follow_redirect` appends the response's `url` and status and sends the next request from the same client, cookies and all; an absolute URL's scheme, host and port go into the environ, and a relative path is joined to the last. A 307 or 308 repeats the method and the data, with the URL's query only for a method other than `"GET"` and `"HEAD"`; any other redirect is a `"GET"` of the URL's query (`django/test/client.py:ClientMixin._follow_redirect`).

`ClientMixin._ensure_redirects_not_cyclic` raises `RedirectCycleError` when the last step, URL and status, was taken before, or the chain is longer than 20: so long a chain, the comment says, is likely a loop whose path, view or query changes, and 20 is Firefox's limit (`django/test/client.py:ClientMixin._ensure_redirects_not_cyclic`).

## `AsyncClient` and `AsyncClientHandler`

`AsyncClient` is a `ClientMixin` and an `AsyncRequestFactory`, which builds an ASGI scope in place of an environ; `AsyncClient.request` is `Client.request` as a coroutine. `AsyncClientHandler.__call__` builds the chain with `load_middleware(is_async=True)`, sends `request_started` with `asend`, makes an `ASGIRequest`, awaits `BaseHandler.get_response_async`, sets `HttpResponseBase.asgi_request`, and closes a response that does not stream through `sync_to_async` (`django/test/client.py:AsyncClientHandler.__call__`). No part of `ASGIHandler` runs ([Sync and async in one chain](../handlers/async.md)). Its methods take `follow=True`, through `AsyncClient._ahandle_redirects`, against the class's docstring, but `ClientMixin._follow_redirect` reads `"PATH_INFO"` and `"REQUEST_METHOD"` from the request, which a scope lacks: a relative redirect, a 307 or a 308 raises `KeyError`.
