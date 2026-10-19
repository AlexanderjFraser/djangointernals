---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Headers, host and scheme

`HttpRequest.headers`, an `HttpHeaders`, reads a request's headers from `META` by their own names. Which of them to believe is decided for the host by `HttpRequest.get_host`, against `ALLOWED_HOSTS`, and for the scheme by `HttpRequest.scheme`, under `SECURE_PROXY_SSL_HEADER`; `HttpRequest.build_absolute_uri` makes full URLs from the two answers, and the `"Accept"` header is ranked by `HttpRequest.accepted_types` and answered by `HttpRequest.get_preferred_type`.

A request's headers reach Django inside `META`, mixed with everything else the server put there and spelt the way CGI spelt them: `"HTTP_ACCEPT_LANGUAGE"` for `Accept-Language`. Two questions come up for any code that reads them. The first is only a matter of convenience: how to look a header up by its own name. The second matters: which headers can be believed. A header is whatever the client chose to send, and a site that builds a password-reset link from the `"Host"` header, or decides a request was encrypted because a header says so, has let the client decide.

`HttpRequest.get_host` and `HttpRequest.scheme` each try their sources in a fixed order, and the figure draws the two side by side. Read each ladder from the top: the first station whose condition holds gives the value, and the host's value is then checked before it is returned. Look at the stations in the accent: they are headers, and so the client's to write.

```text figure=which-host
the host: HttpRequest.get_host              the scheme: HttpRequest.scheme

X-Forwarded-Host                            the header SECURE_PROXY_SSL_HEADER names
  if USE_X_FORWARDED_HOST is true             if the setting is set and the request has the header:
  and the request has the header              "https" if its first item is the setting's value,
     else                                     and "http" if it is not
Host                                             else
  if the request has the header
     else
SERVER_NAME                                 what the server says
  with the port added when it is not          the environ's "wsgi.url_scheme",
  the scheme's usual one                      or the scope's "scheme"
     then
the name, in lower case, without its port or a trailing dot,
compared with ALLOWED_HOSTS,
or, when that is empty and DEBUG is true,
with ".localhost", "127.0.0.1" and "[::1]"
   then
it matches: the value unchanged             it does not: DisallowedHost
```

*Which header is believed, for the host and for the scheme. On each ladder the value comes from the first station, from the top, whose condition holds, written under its name; the host's ladder goes on to the check and its two outcomes. A station in the accent is a header, which the client, or a proxy in front of the server, wrote; a plain station is what the server reports, though with `USE_X_FORWARDED_PORT` set the port may come from X-Forwarded-Port.*

## `HttpHeaders`

`HttpRequest.headers` is a mapping from a header's name to its value, and the name can be written in any case. It is an `HttpHeaders`, made the first time the attribute is read by going through `META` once and keeping the keys that are headers: those that begin with `"HTTP_"`, with the prefix removed, and the two that WSGI leaves without one, `"CONTENT_TYPE"` and `"CONTENT_LENGTH"`. Each key is turned back into a header's usual spelling, underscores to hyphens and each word capitalised (`django/http/request.py:HttpHeaders`, `django/http/request.py:HttpHeaders.parse_header_name`).

The mapping is read-only. Its base class, `CaseInsensitiveMapping`, keeps each entry under its name in lower case beside the name as it was written, and has no method that changes it (`django/utils/datastructures.py:CaseInsensitiveMapping`). It is also a copy: it is made once and kept, so a middleware that changes `META` after something has read `headers` does not change what the next reader of `headers` sees.

A lookup may also write the name with underscores in place of hyphens, `request.headers["user_agent"]`. That spelling is there for templates, where a hyphen cannot appear in a variable's name (`django/http/request.py:HttpHeaders.__getitem__`).

The class also runs the other way, in `HttpHeaders.to_wsgi_names` and `HttpHeaders.to_asgi_names`, for the test client, which lets a test give headers by their real names ([Building a request: `RequestFactory`](../testing/request-factory.md)) (`django/http/request.py:HttpHeaders.to_wsgi_names`, `django/http/request.py:HttpHeaders.to_asgi_names`).

## The host

`HttpRequest.get_host` answers the question of which host the client asked for, and refuses to answer when the host is not one the site has agreed to serve (`django/http/request.py:HttpRequest.get_host`).

It looks in up to three places, in a fixed order (`django/http/request.py:HttpRequest._get_raw_host`). The `X-Forwarded-Host` header is used only when `settings.USE_X_FORWARDED_HOST` is true: a proxy sets that header, and so can anyone else, so it is believed only by a site that has said it stands behind a proxy. Otherwise the `"Host"` header is used. A request with neither gets the server's own name from `"SERVER_NAME"`, with the port added when it is not the usual one for the scheme: `HttpRequest.get_port`'s answer, which is the `X-Forwarded-Port` header when `settings.USE_X_FORWARDED_PORT` is true and the request has one, and `"SERVER_PORT"` otherwise (`django/http/request.py:HttpRequest.get_port`).

The value is then checked against `settings.ALLOWED_HOSTS`. `split_domain_port` lower-cases it, takes the port and a trailing dot off, and rejects anything that is not shaped like a host name or a bracketed IPv6 address. `validate_host` compares what is left with each pattern in the setting: `"*"` matches anything, a pattern that begins with a dot matches that domain and every subdomain of it, and any other pattern must be the host exactly (`django/http/request.py:split_domain_port`, `django/http/request.py:validate_host`, `django/utils/http.py:is_same_domain`).

An empty `ALLOWED_HOSTS` allows nothing, unless `settings.DEBUG` is true, when `get_host` uses in its place the local machine's names, `".localhost"`, `"127.0.0.1"` and `"[::1]"`, the first of which matches localhost and any subdomain of it (`django/http/request.py:HttpRequest.get_host`).

> **History.** Until 1.10.3, the host was not checked against `ALLOWED_HOSTS` at all while `settings.DEBUG` was true, which left a site under development open to a DNS rebinding attack. That security release, with 1.9.11 and 1.8.16 beside it, checked the host in either case, and for convenience allowed the names of localhost when the setting was empty and debugging on (`docs/releases/1.10.3.txt`). Subdomains of localhost, such as static.localhost, joined that fallback in 3.1 (`docs/releases/3.1.txt`).

The check changes nothing in the answer: the comparison is made on the normalised name, and `get_host` returns the value unchanged, capitals, port and trailing dot included, as the answers for SHOP.example:8000 and for the name with a trailing dot show.

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
  ...
```

A host that fails raises `DisallowedHost`. That is a `SuspiciousOperation`, which the middleware chain turns into a 400 response and reports to the logger `"django.security.DisallowedHost"` ([How an exception becomes a response](../handlers/exceptions.md)).

The check runs when `get_host` is called, not when the request is made, and the handler never calls it. Of the middleware that `django-admin startproject` writes, `CommonMiddleware.process_request` calls it for every request that gets past its check of `settings.DISALLOWED_USER_AGENTS` ([The general-purpose middleware](../handlers/general.md#commonmiddleware-on-the-way-in)), and `SecurityMiddleware.process_request`, listed before it, calls it when it redirects a request made over plain HTTP to HTTPS and `SECURE_SSL_HOST` is not set (`django/middleware/common.py:CommonMiddleware.process_request`, `django/middleware/security.py:SecurityMiddleware.process_request`).

> **Trap.** A request's host is checked against `ALLOWED_HOSTS` in `get_host` and nowhere else, so a request whose host nothing asks for is never checked. A response made for such a request, whether from a middleware listed before `CommonMiddleware` or from a view in a project without that middleware, goes out whatever the `"Host"` header said (`django/http/request.py:HttpRequest.get_host`).

## The scheme

`HttpRequest.scheme` is `"http"` or `"https"`, and `HttpRequest.is_secure` says whether it is the second. What the server knows is the scheme of the connection it accepted: a `WSGIRequest` reads the environ's `"wsgi.url_scheme"`, an `ASGIRequest` the scope's `"scheme"`. Behind a proxy that ends TLS that is the wrong answer, since the connection from the proxy is plain HTTP when the client's was not (`django/http/request.py:HttpRequest.scheme`, `django/core/handlers/wsgi.py:WSGIRequest._get_scheme`).

`settings.SECURE_PROXY_SSL_HEADER` names a header and the value that means secure. When it is set and the request has that header, the header alone decides, in both directions: the scheme is `"https"` if the value matches and `"http"` if it does not, whatever the server said. Where the header holds a list, the first item is the one compared. Only when the header is absent does the server's answer stand. The second direction is the last of the lines below that read the scheme, where the header turns a server's https into http.

```text recording=http
...
request.scheme
  the server says http  ->  'http'
  the server says http, X-Forwarded-Proto: https  ->  'http'
  the same, and SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  ->  'https'
  that setting, X-Forwarded-Proto: https, http  (a list)  ->  'https'
  that setting, the server says https, no such header  ->  'https'
  that setting, the server says https, X-Forwarded-Proto: http  ->  'http'
  ...
```

The scheme is a property that is worked out on every read, and a good deal hangs on it: whether `SecurityMiddleware` redirects to HTTPS ([The security headers: `SecurityMiddleware` and `XFrameOptionsMiddleware`](../security/headers.md)), whether the CSRF middleware checks the `"Referer"` of a request that has no `"Origin"` ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md)), what `build_absolute_uri` writes.

## `build_absolute_uri`

`HttpRequest.build_absolute_uri` turns a location into a full URL. It is what code calls when a path is not enough: the cache middleware, for one, keeps a page under a key that holds a hash of the request's full URL, made by this method (`django/utils/cache.py:_generate_cache_key`). It takes the scheme and host from `HttpRequest.scheme` and `get_host`, so it raises `DisallowedHost` where `get_host` would, unless the location it is given already has a scheme and a host of its own. It keeps the two after their first use as `HttpRequest._current_scheme_host`, so a view that builds many URLs validates the host once (`django/http/request.py:HttpRequest.build_absolute_uri`, `django/http/request.py:HttpRequest._current_scheme_host`).

With no location the result is the request's own URL: the scheme and host, then the path and the query string that `HttpRequest.get_full_path` gives (`django/http/request.py:HttpRequest._get_full_path`). A location with a scheme and a host of its own is kept, and any other is resolved against the request's scheme, host and path, much as a browser resolves a link; every result is escaped for use in a URL, as the call with an é shows.

```text recording=http
...
request.build_absolute_uri, of a request for http://shop.example/orders/2026/?page=2
  build_absolute_uri()  ->  'http://shop.example/orders/2026/?page=2'
  build_absolute_uri("/pay/")  ->  'http://shop.example/pay/'
  build_absolute_uri("pay/?step=1")  ->  'http://shop.example/orders/2026/pay/?step=1'
  build_absolute_uri("../2025/")  ->  'http://shop.example/orders/2025/'
  build_absolute_uri("//cdn.example/logo.png")  ->  'http://cdn.example/logo.png'
  build_absolute_uri("https://bank.example/pay/?to=é")  ->  'https://bank.example/pay/?to=%C3%A9'
  get_full_path()  ->  '/orders/2026/?page=2'
```

## The `"Accept"` header

A client says which kinds of response it can take with the `"Accept"` header: a list of media types, each of which may be a pattern such as `"text/*"` and may carry a weight from 0 to 1, written as a parameter named q. `HttpRequest` reads it into a list of `MediaType` objects and answers questions about it. Each item of the header becomes one `MediaType`, an item with a weight of zero is dropped, and a request with no such header is treated as accepting anything (`django/http/request.py:HttpRequest.accepted_types`, `django/http/request.py:MediaType`).

There are two orders to put such a list in, and the request keeps both.

**Preference** is what the client would most like. `HttpRequest.accepted_types` is the list sorted by it: the higher weight first, and at equal weight the more specific type first.

**Precedence** is which item of the header governs a given type, and there the more specific item wins whatever its weight: if a client sends `"text/*"` at 0.9 and `"text/html"` at 0.8, then HTML has weight 0.8, because the client said so about HTML in particular. `HttpRequest.accepted_types_by_precedence` is the same list sorted the other way, by how specific an item is first and by its weight second, and `HttpRequest.accepted_type` returns the first item of it that matches a given type (`django/http/request.py:HttpRequest.accepted_type`).

`HttpRequest.get_preferred_type` is the method a view that can answer in several formats calls. It is given the types the view can produce, finds the governing item for each by precedence, and returns the type whose governing item the client prefers. `HttpRequest.accepts` says only whether a type is acceptable at all (`django/http/request.py:HttpRequest.get_preferred_type`).

The two sorted lists below differ only in where `"text/html"` and `"text/*"` stand, and the second call of `get_preferred_type` is the case the two orders exist for: offered HTML and plain text, it returns plain text, since HTML is governed by its own item at 0.8 and plain text by the pattern at 0.9.

```text recording=http
Accept: text/html;q=0.8, application/json, text/*;q=0.9, */*;q=0.1
  request.accepted_types  ->  application/json, text/*; q=0.9, text/html; q=0.8, */*; q=0.1
  request.accepted_types_by_precedence  ->  application/json, text/html; q=0.8, text/*; q=0.9, */*; q=0.1
  request.accepted_type("text/html")  ->  text/html; q=0.8
  request.accepted_type("text/plain")  ->  text/*; q=0.9
  request.get_preferred_type(["text/html", "application/json"])  ->  'application/json'
  request.get_preferred_type(["text/html", "text/plain"])  ->  'text/plain'
  request.accepts("image/png")  ->  True
  ...
```

> **Changed in 5.2.** `get_preferred_type` was added in that release, and `accepted_types` has been sorted by the client's preference since then (`docs/releases/5.2.txt`).
