---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The security headers: `SecurityMiddleware` and `XFrameOptionsMiddleware`

`SecurityMiddleware` can redirect a request made over plain HTTP to HTTPS, and adds Strict-Transport-Security, X-Content-Type-Options, Referrer-Policy and Cross-Origin-Opener-Policy to responses. `XFrameOptionsMiddleware` adds X-Frame-Options, and the decorators `xframe_options_deny`, `xframe_options_sameorigin` and `xframe_options_exempt` change it for one view.

Each of these headers is an instruction to the browser: reach this site only over HTTPS, do not guess a content type, say little in a `"Referer"`, keep this window apart from other sites' windows, do not show this page in another site's frame. Django adds the header and the browser does the refusing. `SecurityMiddleware` acts in `process_request` and `process_response`, `XFrameOptionsMiddleware` in `process_response` alone, and neither replaces a header the response already has, so a view that sets one keeps its own. Both declare `async_capable = False`, so under ASGI they run synchronously ([Sync and async in one chain](../handlers/async.md)) (`django/middleware/security.py:SecurityMiddleware.async_capable`).

## When the settings are read

`SecurityMiddleware.__init__` copies its settings into attributes, and compiles each pattern of `SECURE_REDIRECT_EXEMPT` as a regular expression (`django/middleware/security.py:SecurityMiddleware.__init__`). It runs once, when the handler builds the chain ([Building the middleware chain](../handlers/chain.md)), so a setting changed later in the process is not seen by that chain. `XFrameOptionsMiddleware` keeps no setting: it reads `X_FRAME_OPTIONS` at each response. A run of the example shows the difference, with the test client making the requests and three settings changed by `override_settings` after one client's first request:

```text
settings changed in the running process
    SECURE_HSTS_PRELOAD = True
    SECURE_REFERRER_POLICY = "no-referrer, strict-origin-when-cross-origin"
    X_FRAME_OPTIONS = "sameorigin"
GET https://harbour.example/berths/
  from a client whose chain was built before the change
    Strict-Transport-Security: max-age=3600
    Referrer-Policy: same-origin
    X-Frame-Options: SAMEORIGIN
  from a client made after it
    Strict-Transport-Security: max-age=3600; preload
    Referrer-Policy: no-referrer,strict-origin-when-cross-origin
    X-Frame-Options: SAMEORIGIN
```

## The redirect to HTTPS

`SecurityMiddleware.process_request` answers a request itself when three things hold: `SECURE_SSL_REDIRECT` is true, the request is not secure, and no pattern of `SECURE_REDIRECT_EXEMPT` is found in its path. The answer is a 301, an `HttpResponsePermanentRedirect`, to `"https://"`, the host, and `HttpRequest.get_full_path`, which keeps the query string. The host is `SECURE_SSL_HOST` if it names one, and otherwise `HttpRequest.get_host`, which raises `DisallowedHost` for a host outside `ALLOWED_HOSTS`: in a run of the example, a plain request for evil.example got a 400 and no redirect (`django/middleware/security.py:SecurityMiddleware.process_request`).

The method is not looked at, and no URL has been resolved yet, so a path with no view is redirected too. Whether the request is secure is `HttpRequest.is_secure`'s answer, which a proxy's header can decide through `SECURE_PROXY_SSL_HEADER` ([Headers, host and scheme](../http/headers.md)).

The exemptions are matched with a search, not from the start, against the path with its leading slashes taken off. So `r"^health/$"` exempts /health/ but not /x/health/ or /healthy/, `r"^/health/$"` can never match, and `r"health"` exempts every path that contains the word.

`MiddlewareMixin.__call__` passes the redirect to the same middleware's `process_response`, so it leaves with this middleware's headers, though without Strict-Transport-Security, since the request was not secure; the middleware inside it never run (`django/middleware/__init__.py:MiddlewareMixin.__call__`).

## The headers on the way out

`SecurityMiddleware.process_response` adds up to four headers, in this order (`django/middleware/security.py:SecurityMiddleware.process_response`).

**Strict-Transport-Security** goes only on a response to a secure request, only when `SECURE_HSTS_SECONDS` is not zero, and only when the response has no such header. Its value is `"max-age="` and the seconds, then `"; includeSubDomains"` if `SECURE_HSTS_INCLUDE_SUBDOMAINS` is true and `"; preload"` if `SECURE_HSTS_PRELOAD` is.

> **Trap.** The browser applies the header to the whole domain and remembers it for the seconds given; Django's documentation advises starting with a small value, an hour, as the harbour office does, and raising it once everything is served over HTTPS (`docs/ref/middleware.txt`).

**X-Content-Type-Options** is `"nosniff"` when `SECURE_CONTENT_TYPE_NOSNIFF` is true. The documentation's reason: a browser that guesses a file's type over its Content-Type may take an uploaded file for HTML or JavaScript (`docs/ref/middleware.txt`).

**Referrer-Policy** comes from `SECURE_REFERRER_POLICY`, which may be a string of comma-separated values, split and stripped, or an iterable; either way the values are joined with a bare comma. The comment gives the reason as fallback: the documentation says the browser takes the last value it understands (`docs/ref/middleware.txt`). A policy of `"no-referrer"` leaves a secure request with no `"Origin"` without the `"Referer"` that the CSRF check then requires ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)).

**Cross-Origin-Opener-Policy** comes from `SECURE_CROSS_ORIGIN_OPENER_POLICY`; the documentation describes it as isolating the site's windows from other sites' documents, against attacks like Spectre (`docs/ref/middleware.txt`).

Strict-Transport-Security is tested for and then assigned. The other three are added with `setdefault`, the last through `HttpResponseBase.setdefault`, which hands it to `ResponseHeaders.setdefault`: a header is set only when the response lacks it (`django/http/response.py:ResponseHeaders.setdefault`). The effect is the same in all four.

| setting | default | at the default |
|---|---|---|
| `SECURE_SSL_REDIRECT` | `False` | no redirect |
| `SECURE_SSL_HOST` | `None` | the request's own host |
| `SECURE_REDIRECT_EXEMPT` | `[]` | no path exempt |
| `SECURE_HSTS_SECONDS` | `0` | no Strict-Transport-Security |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | no `"includeSubDomains"` |
| `SECURE_HSTS_PRELOAD` | `False` | no `"preload"` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | `"nosniff"` |
| `SECURE_REFERRER_POLICY` | `"same-origin"` | `"same-origin"` |
| `SECURE_CROSS_ORIGIN_OPENER_POLICY` | `"same-origin"` | `"same-origin"` |
| `X_FRAME_OPTIONS` | `"DENY"` | `"DENY"` |

*The two middleware's settings and their defaults (`django/conf/global_settings.py`). With none set, only the headers of the last four rows are added.*

## `XFrameOptionsMiddleware`

X-Frame-Options says whether a browser may show the response inside a frame: `"DENY"` nowhere, `"SAMEORIGIN"` only in a page of the same site, as the class's docstring says (`django/middleware/clickjacking.py:XFrameOptionsMiddleware`). `XFrameOptionsMiddleware.process_response` leaves the response alone if it has the header already, or if it carries an attribute `"xframe_options_exempt"` that is true (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.process_response`). Otherwise it asks `XFrameOptionsMiddleware.get_xframe_options_value`, given the request and the response, which returns `X_FRAME_OPTIONS` in capitals, so `"sameorigin"` goes out as `"SAMEORIGIN"`. Its docstring invites a subclass to override it, so that the value can depend on the request or the response (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.get_xframe_options_value`).

## The decorators

`xframe_options_deny` and `xframe_options_sameorigin` set the header to `"DENY"` or `"SAMEORIGIN"` on the response of the view they wrap, unless it already has one; `xframe_options_exempt` sets the attribute `"xframe_options_exempt"` to `True`. Each makes a coroutine function as its wrapper when the view is one and an ordinary function otherwise, so an async view stays async (`django/views/decorators/clickjacking.py`). What they share with Django's other view decorators is in [View decorators](../views/decorators.md).

A decorator acts on the response as the view returns it, inside the whole chain and before any middleware's `process_response`. So the header a decorator sets is already there when `XFrameOptionsMiddleware` looks, and the middleware leaves it; a header the view set itself is left by the decorator in turn. The harbour office's tide table is framed by another site, and its chart only by its own pages. In a run of the example, with the first view marked `xframe_options_exempt` and the second `xframe_options_sameorigin`:

```text
GET https://harbour.example/tides/
    no X-Frame-Options
GET https://harbour.example/chart/
    X-Frame-Options: SAMEORIGIN
```
