---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The security headers: `SecurityMiddleware` and `XFrameOptionsMiddleware`

A browser that asks for a page over plain HTTP can be redirected to HTTPS, and the response carries headers that tell the browser what to refuse: Django asks, and the browser does the refusing. `SecurityMiddleware` makes the redirect only when `SECURE_SSL_REDIRECT` is true, and it and `XFrameOptionsMiddleware` add headers, among them Strict-Transport-Security, or HSTS, which `SECURE_HSTS_SECONDS` turns on, and X-Frame-Options, from `X_FRAME_OPTIONS`.

Their five headers are each an instruction: reach this site only over HTTPS, do not guess a content type, say in a `"Referer"` only what the policy allows, by default keep this window apart from other sites' windows, show this page in no frame, or only in the site's own pages. `SecurityMiddleware` acts on the way in, in `process_request`, and on the way out, in `process_response`; `XFrameOptionsMiddleware` acts on the way out alone. Neither replaces a header the response already has, so a view that sets one keeps its own (`django/middleware/security.py:SecurityMiddleware.process_response`, `django/middleware/clickjacking.py:XFrameOptionsMiddleware.process_response`).

## The redirect to HTTPS

A request made over plain HTTP travels on an unsecured connection, so a site served over HTTPS can send the browser to HTTPS rather than serve the page there (`docs/ref/middleware.txt`). `SecurityMiddleware.process_request` answers such a request itself when three things hold: `SECURE_SSL_REDIRECT` is true, the request is not secure, and no pattern of `SECURE_REDIRECT_EXEMPT` is found in its path. Whether the request is secure is `HttpRequest.is_secure`'s answer, which a proxy's header can decide through `SECURE_PROXY_SSL_HEADER` ([Headers, host and scheme](../http/headers.md)). The method is not looked at, and no URL has been resolved yet, so a path with no view is redirected too.

The answer is a 301, an `HttpResponsePermanentRedirect`, to `"https://"`, the host, and `HttpRequest.get_full_path`, which keeps the query string. The host is `SECURE_SSL_HOST` if it names one, and otherwise `HttpRequest.get_host`, which raises `DisallowedHost` for a host outside `ALLOWED_HOSTS` (`django/middleware/security.py:SecurityMiddleware.process_request`).

The redirect never reaches the layers inside. `MiddlewareMixin.__call__` calls the layer inside only when `process_request` has returned nothing, and gives the response it holds, whichever made it, to the same middleware's `process_response` (`django/middleware/__init__.py:MiddlewareMixin.__call__`). In the harbour's chain, a request for the form over plain HTTP is answered at the first layer: the Location keeps the request's query string, `process_response` follows `process_request` with no layer between them, and its own call of `is_secure` leaves Strict-Transport-Security out, since that header goes only on a secure request.

```text recording=security
GET http://harbour.example/berths/?ship=Endeavour, over plain HTTP: the redirect, and nothing inside SecurityMiddleware runs
...
      MiddlewareMixin.__call__(request), on SecurityMiddleware
        SecurityMiddleware.process_request(request)
          HttpRequest.is_secure()  ->  False
          HttpRequest.get_host(), the Host 'harbour.example'  ->  'harbour.example'
          HttpRequest.get_full_path()  ->  '/berths/?ship=Endeavour'
          -> an HttpResponsePermanentRedirect, status 301, Location 'https://harbour.example/berths/?ship=Endeavour'
        SecurityMiddleware.process_response(request, response)
          HttpRequest.is_secure()  ->  False
          -> the response, X-Content-Type-Options added, Referrer-Policy added, Cross-Origin-Opener-Policy added
          ...
```

A request that meets the three conditions but is for a host outside `ALLOWED_HOSTS`, with no `SECURE_SSL_HOST` to send it to, gets no redirect and none of `SecurityMiddleware`'s headers. `get_host` raises `DisallowedHost` inside `process_request`, the exception leaves `MiddlewareMixin.__call__` before it can call `process_response`, and `convert_exception_to_response`, around the layer, turns it into a 400 by way of `response_for_exception` (`django/core/handlers/exception.py:response_for_exception`). In the harbour's chain, where `SecurityMiddleware` stands first, the 400 goes out with no header but Content-Type.

> **Trap.** A pattern of `SECURE_REDIRECT_EXEMPT` is searched for anywhere in the path, not matched from its start, and the path it is searched in has lost its leading slashes: /health/ is searched as `"health/"`. So `r"^health/$"` exempts /health/ and neither /x/health/ nor /healthy/, `r"health"` exempts every path that holds the word, and `r"^/health/$"`, written as the path is, matches nothing, and /health/ is redirected (`django/middleware/security.py:SecurityMiddleware.process_request`).

## The headers on the way out

`SecurityMiddleware.process_response` adds up to four headers, in this order (`django/middleware/security.py:SecurityMiddleware.process_response`).

**Strict-Transport-Security** goes only on a response to a secure request, only when `SECURE_HSTS_SECONDS` is not its default, zero, and only when the response has no such header. Its value is `"max-age="` and the seconds, and for that many seconds the browser refuses to reach the site's host over plain HTTP, at any address on it, not only the one the header came with (`docs/ref/middleware.txt`). `"; includeSubDomains"` follows if `SECURE_HSTS_INCLUDE_SUBDOMAINS` is true, and extends the refusal to the host's subdomains; `"; preload"` follows if `SECURE_HSTS_PRELOAD` is, and without it the site cannot be submitted to the browser preload list (`docs/ref/middleware.txt`).

**X-Content-Type-Options** is `"nosniff"` when `SECURE_CONTENT_TYPE_NOSNIFF` is true. It keeps the browser from guessing a response's type over its Content-Type, a guess that could take an uploaded file for HTML or JavaScript (`docs/ref/middleware.txt`).

**Referrer-Policy** comes from `SECURE_REFERRER_POLICY`, which may be a string of comma-separated values, split and stripped, or an iterable; either way the values are joined with a bare comma. A policy of `"no-referrer"` leaves a secure request with no `"Origin"` without the `"Referer"` that the CSRF check then requires ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)).

> **Why.** `SECURE_REFERRER_POLICY` takes several values to give the browser a fallback: a browser that does not know a value of the policy uses the last one that it does understand (`docs/ref/middleware.txt`, `django/middleware/security.py:SecurityMiddleware.process_response`).

**Cross-Origin-Opener-Policy** comes from `SECURE_CROSS_ORIGIN_OPENER_POLICY`. At `"same-origin"`, it asks the browser to keep the site's top-level windows apart from other sites' windows, so that a popup of another site opened from one of them gets no reference back to it: a defence in depth against cross-origin attacks such as Spectre (`docs/ref/middleware.txt`).

> **History.** Until 4.0, `SecurityMiddleware` could add X-XSS-Protection, when a setting of its own asked for it. Django 4.0 dropped X-XSS-Protection and its setting together, since most modern browsers do not honour the header, and pointed instead to a content security policy that does not allow every inline script. In the same release `SecurityMiddleware` began to add Cross-Origin-Opener-Policy, `"same-origin"` unless `SECURE_CROSS_ORIGIN_OPENER_POLICY` says otherwise, so that a popup of another origin is kept apart from the site's window (`docs/releases/4.0.txt`).

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

X-Frame-Options says whether a browser may show the response inside a frame: `"DENY"` in none, `"SAMEORIGIN"` only in a page of the same site (`django/middleware/clickjacking.py:XFrameOptionsMiddleware`). Refusing the frame defends against clickjacking, in which another site loads a page of this one in an invisible frame laid over a button of its own, so that the user's click on that button lands on the framed page instead (`docs/ref/clickjacking.txt`).

`XFrameOptionsMiddleware.process_response` leaves the response alone if it has the header already, or if it carries an attribute `"xframe_options_exempt"` that is true (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.process_response`). Otherwise it asks `XFrameOptionsMiddleware.get_xframe_options_value`, which returns `X_FRAME_OPTIONS` in capitals, so `"sameorigin"` goes out as `"SAMEORIGIN"`. The method is there to be overridden: a subclass can make the value depend on the request or the response (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.get_xframe_options_value`).

## The X-Frame-Options decorators

`xframe_options_deny` and `xframe_options_sameorigin` set the header to `"DENY"` or `"SAMEORIGIN"` on the response of the view they wrap, unless it already has one; `xframe_options_exempt` sets the attribute `"xframe_options_exempt"` to `True` (`django/views/decorators/clickjacking.py`). Each wraps a view, and keeps an async view async, in the way [View decorators](../views/decorators.md) tells of three others.

A decorator acts on the response as the view returns it, inside the whole chain and before any middleware's `process_response`. So the header a decorator sets is already there when `XFrameOptionsMiddleware` looks, and the middleware leaves it. The harbour lets other sites frame its tide table, the view *tides*, and lets only its own pages frame its chart, the view *chart*: under `xframe_options_exempt` the first goes out with no X-Frame-Options, and under `xframe_options_sameorigin` the second with `"SAMEORIGIN"` in place of the site's `"DENY"`, `XFrameOptionsMiddleware.process_response` returning each response unchanged (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.process_response`).

## When the settings are read

`SecurityMiddleware.__init__` copies its settings into attributes, and compiles each pattern of `SECURE_REDIRECT_EXEMPT` as a regular expression (`django/middleware/security.py:SecurityMiddleware.__init__`). It runs once, when the handler builds the chain ([Building the middleware chain](../handlers/chain.md)), so a later change to one of them is not seen by that chain. `XFrameOptionsMiddleware` keeps no setting: `XFrameOptionsMiddleware.get_xframe_options_value` reads `X_FRAME_OPTIONS` at each call (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.get_xframe_options_value`).

Two handlers, *before* and *after*, are built on either side of a change to three settings, and the harbour's page is asked of each. X-Frame-Options turns to `"SAMEORIGIN"` through both, since each response reads the setting anew, while Strict-Transport-Security gains its `"; preload"` and Referrer-Policy its new list only through *after*, whose `__init__` read them.

```text recording=security
Settings changed after a chain was built: SecurityMiddleware keeps what it read when the chain was built, XFrameOptionsMiddleware reads X_FRAME_OPTIONS at each response
    before = WSGIHandler()
      SecurityMiddleware.__init__(get_response)  ->  sts_seconds 3600, sts_preload False, referrer_policy 'same-origin', redirect_exempt []
...
    changed = override_settings(SECURE_HSTS_PRELOAD=True, SECURE_REFERRER_POLICY='no-referrer, strict-origin-when-cross-origin', X_FRAME_OPTIONS='sameorigin'); changed.enable()
    after = WSGIHandler()
      SecurityMiddleware.__init__(get_response)  ->  sts_seconds 3600, sts_preload True, referrer_policy 'no-referrer, strict-origin-when-cross-origin', redirect_exempt []
    GET https://harbour.example/berths/ through the handler before, the browser sending nothing but the request
    XFrameOptionsMiddleware.get_xframe_options_value(request, response)  ->  'SAMEORIGIN'
    start_response("200 OK", headers)
      X-Frame-Options: SAMEORIGIN
      Strict-Transport-Security: max-age=3600
      Referrer-Policy: same-origin
    GET https://harbour.example/berths/ through the handler after, the browser sending nothing but the request
    XFrameOptionsMiddleware.get_xframe_options_value(request, response)  ->  'SAMEORIGIN'
    start_response("200 OK", headers)
      X-Frame-Options: SAMEORIGIN
      Strict-Transport-Security: max-age=3600; preload
      Referrer-Policy: no-referrer,strict-origin-when-cross-origin
      ...
```
