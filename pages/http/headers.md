---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Headers, host and scheme

How a request's headers are read from `META` through `HttpHeaders`, how `HttpRequest.get_host` and `HttpRequest.scheme` decide which of them to believe, how `build_absolute_uri` uses the answers, and how the `"Accept"` header is ranked.

A request's headers reach Django inside `META`, mixed with everything else the server put there and spelt the way CGI spelt them: `"HTTP_ACCEPT_LANGUAGE"` for `Accept-Language`. Two questions come up for any code that reads them. The first is only a matter of convenience: how to look a header up by its own name. The second matters: which headers can be believed. A header is whatever the client chose to send, and a site that builds a password-reset link from the `"Host"` header, or decides a request was encrypted because a header says so, has let the client decide.

## `HttpHeaders`

`HttpRequest.headers` is a mapping from a header's name to its value, and the name can be written in any case. It is an `HttpHeaders`, made the first time the attribute is read by going through `META` once and keeping the keys that are headers: those that begin with `"HTTP_"`, with the prefix removed, and the two that WSGI leaves without one, `"CONTENT_TYPE"` and `"CONTENT_LENGTH"`. Each key is turned back into a header's usual spelling, underscores to hyphens and each word capitalised (`django/http/request.py:HttpHeaders`, `django/http/request.py:HttpHeaders.parse_header_name`).

The mapping is read-only. Its base class, `CaseInsensitiveMapping`, keeps each entry under its name in lower case beside the name as it was written, and has no method that changes it (`django/utils/datastructures.py:CaseInsensitiveMapping`). It is also a copy: it is made once and kept, so a middleware that changes `META` after something has read `headers` does not change what the next reader of `headers` sees.

A lookup may also write the name with underscores in place of hyphens, `request.headers["user_agent"]`. That spelling is there for templates, where a hyphen cannot appear in a variable's name (`django/http/request.py:HttpHeaders.__getitem__`).

The class also runs the other way, for the test client, which lets a test give headers by their real names. `HttpHeaders.to_wsgi_names` takes a dictionary keyed that way and returns it keyed as an environ would have it. `HttpHeaders.to_asgi_names` only puts each name in upper case with underscores, and the asynchronous half of the test client turns the result into the header names of a scope (`django/test/client.py:RequestFactory.generic`, `django/test/client.py:AsyncRequestFactory.generic`).

## The host

`HttpRequest.get_host` answers the question of which host the client asked for, and refuses to answer when the host is not one the site has agreed to serve (`django/http/request.py:HttpRequest.get_host`).

It looks in up to three places, in a fixed order (`django/http/request.py:HttpRequest._get_raw_host`). The `X-Forwarded-Host` header is used only when `settings.USE_X_FORWARDED_HOST` is true: a proxy sets that header, and so can anyone else, so it is believed only by a site that has said it stands behind a proxy. Otherwise the `"Host"` header is used. A request with neither gets the server's own name from `"SERVER_NAME"`, with the port added when it is not the usual one for the scheme.

The value is then checked against `settings.ALLOWED_HOSTS`. `split_domain_port` lower-cases it, takes the port and a trailing dot off, and rejects anything that is not shaped like a host name or a bracketed IPv6 address. `validate_host` compares what is left with each pattern in the setting: `"*"` matches anything, a pattern that begins with a dot matches that domain and every subdomain of it, and any other pattern must be the host exactly (`django/http/request.py:split_domain_port`, `django/http/request.py:validate_host`, `django/utils/http.py:is_same_domain`).

```text recording=http
request.get_host(), with ALLOWED_HOSTS = ['shop.example'] unless the line says otherwise
  Host: shop.example  ->  'shop.example'
  Host: SHOP.example:8000  ->  'SHOP.example:8000'
  Host: shop.example.  (a trailing dot)  ->  'shop.example.'
  Host: www.shop.example  ->  raises DisallowedHost
  Host: www.shop.example, and ALLOWED_HOSTS = ['.shop.example']  ->  'www.shop.example'
  Host: shop.example/x  (not a host name)  ->  raises DisallowedHost
  no Host header; SERVER_NAME shop.example, SERVER_PORT 80  ->  'shop.example'
  no Host header; SERVER_NAME shop.example, SERVER_PORT 8000  ->  'shop.example:8000'
  Host: shop.example, X-Forwarded-Host: evil.example  ->  'shop.example'
  the same, and USE_X_FORWARDED_HOST = True  ->  raises DisallowedHost
  Host: evil.example, and ALLOWED_HOSTS = ['*']  ->  'evil.example'
  Host: evil.example, and ALLOWED_HOSTS = [], DEBUG = False  ->  raises DisallowedHost
  Host: evil.example, and ALLOWED_HOSTS = [], DEBUG = True  ->  raises DisallowedHost
  Host: app.localhost:8000, and ALLOWED_HOSTS = [], DEBUG = True  ->  'app.localhost:8000'
```

The recording shows what the check does and does not change. The comparison is made on the normalised name, but what `get_host` returns is the value as it was sent, capitals, port and trailing dot included. An empty `ALLOWED_HOSTS` allows nothing, with one exception: when `settings.DEBUG` is true as well, the names a developer's own machine goes by are allowed: `"localhost"` with its subdomains, `"127.0.0.1"` and `"[::1]"`.

A host that fails raises `DisallowedHost`. That is a `SuspiciousOperation`, which the middleware chain turns into a 400 response and reports to the logger `"django.security.DisallowedHost"` ([How an exception becomes a response](../handlers/exceptions.md)).

The check runs when `get_host` is called, not when the request is made. Nothing in the handler calls it. In a project with the middleware that `django-admin startproject` writes, every request is checked all the same, because `CommonMiddleware.process_request` calls `get_host` on its way in, once the request has passed that middleware's check of its user agent; a request answered by a middleware listed before that one, or served by a project without it, is checked only if something asks for the host (`django/middleware/common.py:CommonMiddleware.process_request`).

`HttpRequest.get_port` is simpler. It returns `"SERVER_PORT"`, or the `X-Forwarded-Port` header when `settings.USE_X_FORWARDED_PORT` is true and the header is there, and it validates nothing (`django/http/request.py:HttpRequest.get_port`).

## The scheme

`HttpRequest.scheme` is `"http"` or `"https"`, and `HttpRequest.is_secure` says whether it is the second. What the server knows is the scheme of the connection it accepted: a `WSGIRequest` reads the environ's `"wsgi.url_scheme"`, an `ASGIRequest` the scope's `"scheme"`. Behind a proxy that ends TLS that is the wrong answer, since the connection from the proxy is plain HTTP when the client's was not (`django/http/request.py:HttpRequest.scheme`, `django/core/handlers/wsgi.py:WSGIRequest._get_scheme`).

`settings.SECURE_PROXY_SSL_HEADER` names a header and the value that means secure. When it is set and the request has that header, the header alone decides, in both directions: the scheme is `"https"` if the value matches and `"http"` if it does not, whatever the server said. Where the header holds a list, the first item is the one compared. Only when the header is absent does the server's answer stand.

```text recording=http
request.scheme
  the server says http  ->  'http'
  the server says http, X-Forwarded-Proto: https  ->  'http'
  the same, and SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  ->  'https'
  that setting, X-Forwarded-Proto: https, http  (a list)  ->  'https'
  that setting, the server says https, no such header  ->  'https'
  that setting, the server says https, X-Forwarded-Proto: http  ->  'http'
```

The scheme is a property that is worked out on every read, and a good deal hangs on it: whether `SecurityMiddleware` redirects to HTTPS, whether the CSRF middleware applies its stricter checks, what `build_absolute_uri` writes.

## `build_absolute_uri`

`HttpRequest.build_absolute_uri` turns a location into a full URL on the site the request came to. It is what code calls when a path is not enough: within Django, the cache keys a page by the request's full URL. It takes the scheme and host from `HttpRequest.scheme` and `get_host`, so it raises `DisallowedHost` where `get_host` would, unless the location it is given already has a scheme and a host of its own (`django/http/request.py:HttpRequest.build_absolute_uri`, `django/utils/cache.py:_generate_cache_key`).

```text recording=http
request.build_absolute_uri, of a request for http://shop.example/orders/2026/?page=2
  build_absolute_uri()  ->  'http://shop.example/orders/2026/?page=2'
  build_absolute_uri("/pay/")  ->  'http://shop.example/pay/'
  build_absolute_uri("pay/?step=1")  ->  'http://shop.example/orders/2026/pay/?step=1'
  build_absolute_uri("../2025/")  ->  'http://shop.example/orders/2025/'
  build_absolute_uri("//cdn.example/logo.png")  ->  'http://cdn.example/logo.png'
  build_absolute_uri("https://bank.example/pay/?to=é")  ->  'https://bank.example/pay/?to=%C3%A9'
  get_full_path()  ->  '/orders/2026/?page=2'
```

With no argument it is the request's own URL. A location that already has a scheme and a host is left as it is, apart from the escaping every result gets. Anything else is resolved against the request's URL as a browser would resolve a link on the page: a path from the root replaces the path, a relative one is joined to it, and a location that names a host and no scheme takes the request's scheme. The plain case of a path from the root with no dot segments is done by joining strings, without the general algorithm.

The scheme and host together are kept after the first use as `HttpRequest._current_scheme_host`, so a view that builds many URLs validates the host once. `HttpRequest.get_full_path` is the path and the query string with neither scheme nor host, escaped for use in a URL; `HttpRequest.get_full_path_info` is the same for `path_info` (`django/http/request.py:HttpRequest._get_full_path`).

## The `"Accept"` header

A client says which kinds of response it can take with the `"Accept"` header: a list of media types, each of which may be a pattern such as `"text/*"` and may carry a weight from 0 to 1, written as a parameter named q. `HttpRequest` reads it into a list of `MediaType` objects and answers questions about it. Each item of the header becomes one `MediaType`, an item with a weight of zero is dropped, and a request with no such header is treated as accepting anything (`django/http/request.py:HttpRequest.accepted_types`, `django/http/request.py:MediaType`).

There are two orders to put such a list in, and the request keeps both.

**Preference** is what the client would most like. `HttpRequest.accepted_types` is the list sorted by it: the higher weight first, and at equal weight the more specific type first.

**Precedence** is which item of the header governs a given type, and there the more specific item wins whatever its weight: if a client sends `"text/*"` at 0.9 and `"text/html"` at 0.8, then HTML has weight 0.8, because the client said so about HTML in particular. `HttpRequest.accepted_types_by_precedence` is the same list sorted the other way, by how specific an item is first and by its weight second, and `HttpRequest.accepted_type` returns the first item of it that matches a given type (`django/http/request.py:HttpRequest.accepted_type`).

```text recording=http
Accept: text/html;q=0.8, application/json, text/*;q=0.9, */*;q=0.1
  request.accepted_types  ->  application/json, text/*; q=0.9, text/html; q=0.8, */*; q=0.1
  request.accepted_types_by_precedence  ->  application/json, text/html; q=0.8, text/*; q=0.9, */*; q=0.1
  request.accepted_type("text/html")  ->  text/html; q=0.8
  request.accepted_type("text/plain")  ->  text/*; q=0.9
  request.get_preferred_type(["text/html", "application/json"])  ->  'application/json'
  request.get_preferred_type(["text/html", "text/plain"])  ->  'text/plain'
  request.accepts("image/png")  ->  True
```

`HttpRequest.get_preferred_type` is the method a view that can answer in several formats calls. It is given the types the view can produce, finds the governing item for each by precedence, and returns the type whose governing item the client prefers. The second call in the recording is the case the two orders exist for: offered HTML and plain text, it returns plain text, since HTML is governed by its own item at 0.8 and plain text by the pattern at 0.9. `HttpRequest.accepts` says only whether a type is acceptable at all (`django/http/request.py:HttpRequest.get_preferred_type`).

> **Changed in 5.2.** `get_preferred_type` was added in that release, and `accepted_types` has been sorted by the client's preference since then.
