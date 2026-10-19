---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Building a request: `RequestFactory`

`RequestFactory` makes a `WSGIRequest` from a method, a path, data and headers, as a WSGI server would describe the request, for a test to pass straight to a view. A method named after an HTTP method decides what its data becomes, `RequestFactory.generic` builds the request, and `AsyncRequestFactory` does the same for an `ASGIRequest`.

A view is a function of a request, and the plainest test of one calls it. The factory's docstring says its request can be passed to any view function as though the view had been reached through a URLconf (`django/test/client.py:RequestFactory`). `Client`, its subclass, sends the request through a handler instead ([The test client: `Client` and `ClientHandler`](client.md)).

## What the request has not been through

The request has met no handler, so nothing the handler or the middleware add is on it.

- **No session and no user.** The session middleware and `AuthenticationMiddleware` set them, so a view under `login_required` raises `AttributeError` until the test sets a user by hand ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md)).
- **No CSRF check**, which is `CsrfViewMiddleware`'s: a `"POST"` without a token reaches the view, unless the view is decorated with `csrf_protect`, which makes the check itself; the factory does not mark its request to be let through, as the client's handler does, and `LoginView` answered such a `"POST"` with 403 ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md)).
- **No resolving.** `HttpRequest.resolver_match` stays `None`, and the test passes the view its URL's arguments (`django/core/handlers/base.py:BaseHandler.resolve_request`).
- **No exception made a response.** ship_detail, called for a missing ship, raised `Http404` into the test ([How an exception becomes a response](../handlers/exceptions.md)).
- **The host is `"testserver"`**, which `HttpRequest.get_host` accepts once the test environment has added it to `ALLOWED_HOSTS` ([The test environment: `setup_test_environment`](environment.md)).

```python
# harbour/office/tests/test_direct.py
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from harbour.fleet.models import Port
from harbour.office.views import new_ship


class NewShipTests(TestCase):
    def test_new_ship(self):
        valletta = Port.objects.create(name="Valletta", country="Malta")
        data = {"name": "Beagle", "tonnage": 242, "home": valletta.pk}
        request = RequestFactory().post("/ships/new/", data)
        with self.assertRaisesMessage(AttributeError, "has no attribute 'user'"):
            new_ship(request)
        request.user = User.objects.create_user("nora")
        self.assertEqual(new_ship(request).status_code, 302)
```

The test passes, with no CSRF token sent.

## The environ: `RequestFactory.__init__` and `_base_environ`

`RequestFactory.__init__` keeps what every request shares: the **defaults**, environ keys given as keyword arguments, joined by headers given by their real names, through `HttpHeaders.to_wsgi_names` ([Headers, host and scheme](../http/headers.md)), and by query parameters as a url-encoded `"QUERY_STRING"`. `RequestFactory.json_encoder` is `DjangoJSONEncoder` by default; `RequestFactory.cookies` starts as an empty `SimpleCookie`; `RequestFactory.errors` is each request's `"wsgi.errors"` (`django/test/client.py:RequestFactory.__init__`).

> **Trap.** A default query string reaches no request that `generic` builds: it always sets `"QUERY_STRING"`, empty if the call and the path give none, over the default. A factory made with `query_params={"port": "Valletta"}` made a `"GET"` with no query string. `Client` inherits this.

`RequestFactory._base_environ` is the minimal environ of PEP 3333 and, its comment says, two keys more: `"HTTP_COOKIE"`, the factory's cookies sorted and joined with `"; "`, and `"REMOTE_ADDR"`, `"127.0.0.1"`, "often useful", citing ticket #8551. The server is `"testserver"` on port `"80"`, and with no `"Host"` header `get_host` falls back to that name. The defaults are laid over these keys, and the request's own over the defaults (`django/test/client.py:RequestFactory._base_environ`).

## `RequestFactory.generic`

Every method ends in `RequestFactory.generic`, whose keys `RequestFactory.request` makes into a `WSGIRequest` (`django/test/client.py:RequestFactory.generic`). It hands the path over as a WSGI server would, `RequestFactory._get_path` turning its escapes into bytes and decoding them as ISO-8859-1, which `WSGIRequest` reverses before decoding them as UTF-8 ([Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md)): "/ships/Cáceres/" and "/ships/C%C3%A1ceres/" gave the same path.

The data is made bytes in `DEFAULT_CHARSET`. Only bytes that are not empty give the request `"CONTENT_LENGTH"`, `"CONTENT_TYPE"` and a `FakePayload` holding them as `"wsgi.input"`: `generic` gives a `"GET"` no content type. `secure=True` makes the port `"443"` and the scheme `"https"`. The call's headers and other keyword arguments, as environ keys, are laid over the rest, even `"CONTENT_LENGTH"`. The query string is the call's query parameters url-encoded, a list giving a repeated key (`"port=Valletta&flag=red&flag=blue"`); else a `"QUERY_STRING"` keyword; else the path's own.

## The methods

| methods | what data becomes | default content type | JSON |
|---|---|---|---|
| `RequestFactory.get`, `RequestFactory.head` | the query string; a `ValueError` beside query parameters | none | no |
| `RequestFactory.post` | the body: multipart, or text in the content type's charset | `MULTIPART_CONTENT` | encoded |
| `RequestFactory.put`, `RequestFactory.patch`, `RequestFactory.delete` | the body, in `DEFAULT_CHARSET` | `"application/octet-stream"` | encoded |
| `RequestFactory.options` | the body, in `DEFAULT_CHARSET` | `"application/octet-stream"` | not encoded |
| `RequestFactory.trace` | no data argument | none | no |

*The factory's methods and their data.*

`RequestFactory._encode_json` serializes a dictionary, list or tuple with the factory's encoder when `JSON_CONTENT_TYPE_RE` matches the start of the content type: `"application/json"`, or an application type with a +json suffix, whatever follows; `DjangoJSONEncoder` writes a `decimal.Decimal` and a date as strings (`b'{"tonnage": "242.5", "launched": "1820-05-11"}'`). `post` alone then calls `RequestFactory._encode_data`: multipart for `MULTIPART_CONTENT`, else text in the content type's charset, or `DEFAULT_CHARSET`. The others leave that to `generic`, so "Cáceres" as "text/plain; charset=utf-16" arrived as UTF-16 from `post` and UTF-8 from `put`. A dictionary under any other content type, or given to `options`, is sent as its `str` (`django/test/client.py:RequestFactory._encode_json`, `django/test/client.py:RequestFactory._encode_data`).

> **Trap.** `_encode_data` tests the content type against `MULTIPART_CONTENT` by identity, so the same text typed out does not count: a dictionary posted under "multipart/form-data; boundary=BoUnDaRyStRiNg" was sent as `b"{'name': 'Beagle'}"`.

`encode_multipart` writes a part for each key, lines ended by CRLF, the whole closed by the boundary and two dashes:

```text
# a run of the example: the first lines of the body of a post of {"name": "Beagle", "tonnage": 242, "home": 1}
--BoUnDaRyStRiNg
Content-Disposition: form-data; name="name"

Beagle
--BoUnDaRyStRiNg
Content-Disposition: form-data; name="tonnage"
```

An iterable that is not a `str`, bytes among them, gives a part for each item. A file-like value, one with a callable read method, is written by `encode_file` with its base name, or the key, and a content type: the one the object carries, else a guess from the name, else `"application/octet-stream"`. A key's value of `None` is refused with a `TypeError` asking whether an empty string or no value was meant (`django/test/client.py:encode_multipart`, `django/test/client.py:encode_file`); the parser's side is [Multipart parsing: `MultiPartParser`](../http/multipart.md).

## `FakePayload`

A body is a `FakePayload`: bytes that can be written until the first read, and that refuse, with an `AssertionError`, a read of more than is left. Its docstring's reason: network data cannot be sought or read past its length, and a view should do nothing under the test client that would fail in real life (`django/test/client.py:FakePayload`). Behind a `WSGIRequest`'s `LimitedStream`, which stops at `"CONTENT_LENGTH"`, the guard is met when a test sets a length longer than the body.

## `AsyncRequestFactory`

`AsyncRequestFactory` makes an `ASGIRequest` with the same synchronous methods; `AsyncClient` is built on it. `AsyncRequestFactory._base_scope` is a minimal scope with, its comment says, a `"cookie"` header and the `"client"` address, citing ticket #8551, and the defaults as keys. `AsyncRequestFactory.generic` fills in the rest, and here the factory's default query string counts. `AsyncRequestFactory.request` wraps the payload in a `LimitedStream` of its length, so a long read returns what there is (`django/test/client.py:AsyncRequestFactory.request`).

```text
# a run of the example: three keys of a JSON post's scope, with query_params={"port": "Valletta"} given to the factory and headers={"X-Harbour": "Valletta"} to the post
query_string: 'port=Valletta'
server: ('127.0.0.1', '80')
headers: [(b'host', b'testserver'), (b'content-length', b'18'), (b'content-type', b'application/json'), (b'x-harbour', b'Valletta'), (b'cookie', b'')]
```

Headers given to a call pass through `HttpHeaders.to_asgi_names`, upper case with underscores; the defaults and other keywords count as header names. Each is put in lower case with `"_"` as `"-"`: `ASGIRequest` drops a header with an underscore (CVE-2026-3902), and the comment's reason is not to break tests that give names in that form ([Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md#from-an-asgi-scope), `django/test/client.py:AsyncRequestFactory.generic`).

> **Trap.** The constructor is the parent's, which makes headers environ keys: `headers={"X-Harbour": "Valletta"}` given to it sent a header named "http-x-harbour", filed as `"HTTP_HTTP_X_HARBOUR"`. A keyword argument named after the header arrives as meant.
