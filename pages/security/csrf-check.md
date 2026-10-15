---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The CSRF check: `CsrfViewMiddleware.process_view`

`CsrfViewMiddleware.process_view` is the CSRF check: before a view runs, it decides whether a request of a method that is not safe came from the site's own pages, first by its `"Origin"` or `"Referer"` header and then by a token that must match the browser's CSRF secret. A request it refuses is answered by the view that `CSRF_FAILURE_VIEW` names, `csrf_failure` by default, which returns a 403.

The check is a sequence of tests, and the first that decides ends it. Four let a request through without looking at it; the rest ask where it came from and what it carries. Each refusal has a **reason**, a short sentence that is logged and handed to the failure view. An accepted request goes on to its view; a refused one gets the failure view's response in its place (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`). The secret and its token are in [The CSRF secret and its token](csrf-token.md).

```text figure=the-check
let through, unchecked
  already marked as checked
  the view is marked csrf_exempt
  a safe method: GET, HEAD, OPTIONS, TRACE
  the test client's flag

the origin
  an Origin header:       the site's own origin or a trusted one        else refused: Origin checking failed - ...
  no Origin, HTTPS:       a Referer naming the site or a trusted host   else refused: Referer checking failed - ...
  no Origin, plain HTTP:  nothing checked

the token
  a malformed cookie                           refused: CSRF cookie has ...
  no secret                                    refused: CSRF cookie not set.
  no token in the form field or the header     refused: CSRF token missing.
  a token of the wrong length or characters    refused: CSRF token from ... has ...
  a token not matching the secret              refused: CSRF token from ... incorrect.
  otherwise                                    accepted, on to the view

refused: the failure view's 403 in the view's place, the reason logged
```

*The decisions of `CsrfViewMiddleware.process_view`, from the top. The first test that decides ends the check.*

## Requests let through unchecked

A request already checked is not checked again. `CsrfViewMiddleware._accept` marks an accepted request with the attribute `"csrf_processing_done"`, and `process_view` returns at once for a request so marked, which is what lets the middleware and the `csrf_protect` decorator share one request ([A middleware as a decorator](../views/middleware-decorators.md)) (`django/middleware/csrf.py:CsrfViewMiddleware._accept`).

A view marked by `csrf_exempt` is let through next, without the request being marked ([View decorators](../views/decorators.md)). It is tested after `CsrfViewMiddleware.process_request` has read the browser's secret, so that, a comment says, `get_token` still works in an exempt view.

Then the safe methods, `"GET"`, `"HEAD"`, `"OPTIONS"` and `"TRACE"`, on the comment's assumption that whatever RFC 9110 does not define as safe needs protection. Last, the test client's flag: its handler sets `"_dont_enforce_csrf_checks"` on every request, true unless the client was made with `enforce_csrf_checks=True` ([The test framework](../testing.md)) (`django/test/client.py:ClientHandler.__call__`). Both these paths mark the request as checked.

## The origin

A request with an `"Origin"` header is refused unless `CsrfViewMiddleware._origin_verified` accepts it, in one of three ways tried in order (`django/middleware/csrf.py:CsrfViewMiddleware._origin_verified`). The header may equal the site's own origin: `"https"` or `"http"` as `HttpRequest.is_secure` says, and the host from `HttpRequest.get_host` ([Headers, host and scheme](../http/headers.md)), a host refused by `ALLOWED_HOSTS` raising `DisallowedHost`, which is passed over. It may be one of `CSRF_TRUSTED_ORIGINS` exactly. Or it may have the scheme of a trusted origin written with a `"*"`, and a host that matches that origin's host, star taken off, by `is_same_domain`, where a pattern that begins with a dot matches the domain and every subdomain (`django/utils/http.py:is_same_domain`).

The setting is read into three cached properties, once for each instance of the middleware (`django/middleware/csrf.py:CsrfViewMiddleware.allowed_origin_subdomains`). In a run, a client whose chain had refused an origin went on refusing it after `CSRF_TRUSTED_ORIGINS` was changed to name it; a new client accepted it.

Only a request with no `"Origin"` has its `"Referer"` read, and only if it is secure. The comment's reason: a man in the middle of a plain-HTTP visit can supply a cookie and a token of his own, the secret being tied to no session, and post them to the HTTPS site, which must treat its plain-HTTP self as untrusted; and as Barth et al. found the `"Referer"` missing from same-domain HTTPS requests in about 0.2% of cases or fewer, a strict check is possible.

`CsrfViewMiddleware._check_referer` refuses a request with no `"Referer"`, one that does not parse into a scheme and a host, and one whose scheme is not `"https"`. It accepts a host that matches a trusted origin's host by `is_same_domain`, whatever that origin's scheme. Otherwise the host must match the cookie's domain, `CSRF_COOKIE_DOMAIN` or, with `CSRF_USE_SESSIONS`, `SESSION_COOKIE_DOMAIN`, with the request's port added unless it is 443 or 80; or, when that domain is `None`, as by default, `get_host`, port and all, a `DisallowedHost` being refused (`django/middleware/csrf.py:CsrfViewMiddleware._check_referer`).

With `CSRF_TRUSTED_ORIGINS = ["https://*.harbour.example", "https://pay.example"]` added to the harbour's, a run of the example, with the test client making the requests, each with the cookie and the token, gave:

```text
POST https://harbour.example/berths/
  Origin: https://pilots.harbour.example   200  Berth requested.
  Origin: http://pilots.harbour.example    403  Forbidden (Origin checking failed - http://pilots.harbour.example does not match any trusted origins.): /berths/
  Origin: https://a.pay.example            403  Forbidden (Origin checking failed - https://a.pay.example does not match any trusted origins.): /berths/
  Referer: https://harbour.example:8443/berths/
                                           403  Forbidden (Referer checking failed - https://harbour.example:8443/berths/ does not match any trusted origins.): /berths/
```

## The token

`CsrfViewMiddleware._check_token` reads the secret again from the cookie or the session, by `CsrfViewMiddleware._get_secret`, rather than taking the copy `process_request` kept in `META`. The comment's reason: an authentication middleware may have called `rotate_token` in its `process_request`, replacing that copy, while the browser's token was made from the old secret. A malformed cookie is refused, though `process_request` has already replaced it for the response. No secret is refused too: insisting on a cookie for a `"POST"`, the comment says, avoids all CSRF attacks, login CSRF among them (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`).

For a `"POST"` the token is the form field `"csrfmiddlewaretoken"`. An `UnreadablePostError` while the body is read is swallowed, as `process_view` should not raise, the comment says, and the field counts as empty. If the field is missing or empty, or the method is another, the token is the header `CSRF_HEADER_NAME` names, `"HTTP_X_CSRFTOKEN"` by default, which is X-CSRFToken: a fallback, the comment says, to make things easier for AJAX and possible for `"PUT"` and `"DELETE"`. No other body is read: in a run, a `"PUT"` whose form-encoded body held a good token was refused with `"CSRF token missing."`.

The token must then be 32 or 64 letters and digits. `_does_token_match` unmasks a token of 64, takes one of 32 as the secret itself, as a script that read the cookie sends it, and compares it with the secret by `constant_time_compare` ([Secret keys and `django.utils.crypto`](keys.md)) (`django/middleware/csrf.py:_does_token_match`). `CsrfViewMiddleware._bad_token_message` names a failing token's source: `"POST"`, or `"the 'X-Csrftoken' HTTP header"`, as `HttpHeaders.parse_header_name` spells it.

## Refusal and its reasons

The referer and token tests raise `RejectRequest` with their reason, and every refusal ends in `CsrfViewMiddleware._reject`. It imports the view `CSRF_FAILURE_VIEW` names by `get_callable`, calls it with the request and the reason, and logs the response by `log_response` to `"django.security.csrf"`, as `"Forbidden (%s): %s"` with the reason and the path (`django/middleware/csrf.py:CsrfViewMiddleware._reject`). `log_response` logs a 4xx as a warning and marks the response as logged, so the handler, which logs every response of 400 or more to `"django.request"`, does not log it again (`django/utils/log.py:log_response`).

A comment says `_accept` and `_reject` exist as methods for `requires_csrf_token`, whose class replaces `_reject` with one that refuses nothing ([A middleware as a decorator](../views/middleware-decorators.md)). The security checks confirm that the failure view can be imported and takes a request and a reason ([The security checks](checks.md)).

| reason | refused when | message |
|---|---|---|
| `REASON_BAD_ORIGIN` | the `"Origin"` is not verified | `"Origin checking failed - %s does not match any trusted origins."` |
| `REASON_NO_REFERER` | secure, and no `"Origin"` or `"Referer"` | `"Referer checking failed - no Referer."` |
| `REASON_MALFORMED_REFERER` | the `"Referer"` does not parse into a scheme and a host | `"Referer checking failed - Referer is malformed."` |
| `REASON_INSECURE_REFERER` | the `"Referer"` is not HTTPS | `"Referer checking failed - Referer is insecure while host is secure."` |
| `REASON_BAD_REFERER` | the host is neither the site's nor trusted | `"Referer checking failed - %s does not match any trusted origins."` |
| a malformed cookie | its length or characters | `"CSRF cookie has incorrect length."`, `"CSRF cookie has invalid characters."` |
| `REASON_NO_CSRF_COOKIE` | no secret | `"CSRF cookie not set."` |
| `REASON_CSRF_TOKEN_MISSING` | no token | `"CSRF token missing."` |
| a malformed token | its length or characters | `"CSRF token from POST has incorrect length."` |
| a wrong token | it does not match the secret | `"CSRF token from POST incorrect."` |

*The reasons the CSRF check gives, in the order it tests. The messages for a malformed cookie or token are made from `REASON_INCORRECT_LENGTH` and `REASON_INVALID_CHARACTERS`.*

## The failure view: `csrf_failure`

`csrf_failure` builds its page's context: a translated title and sentence; the reason; `"no_referer"` and `"no_cookie"`, true when the reason is `REASON_NO_REFERER` or `REASON_NO_CSRF_COOKIE`, each with paragraphs for the user; `settings.DEBUG`, with the documentation's version for its links and a line for when it is off; and the nonce, merged in from the `csp` context processor (`django/views/csrf.py:csrf_failure`).

It asks the project's template engines for `"403_csrf.html"`. A project's template of that name is rendered with the request alone and none of that context: in a run, one that wrote `{{ reason }}`, `{{ no_cookie }}` and `{{ csp_nonce }}` rendered the first two empty and the third, from the context processor, with the nonce. When no engine has it, `csrf_failure` renders the built-in `"csrf_403.html"` with an `Engine` of its own and the context, so the page does not depend on `TEMPLATES` (`django/views/csrf.py:csrf_failure`). A template name of a caller's own that does not exist raises `TemplateDoesNotExist`.

The built-in page shows the paragraphs for a missing `"Referer"` or cookie when the reason is one of those, and, with `settings.DEBUG` true, the reason and a list of what to check (`django/views/templates/csrf_403.html`). Its stylesheet carries `{% csp_nonce_attr %}`, so the harbour's 403 made the nonce, and its policy named it, though only in `"script-src"`, where the harbour's setting puts it. The response is an `HttpResponseForbidden`.

`CsrfViewMiddleware` sets `async_capable = False`, so under ASGI it runs as a synchronous layer. The check is synchronous for another reason: `process_view` is a synchronous method, which the handler adapts to its own mode separately from the layer ([Sync and async in one chain](../handlers/async.md)) (`django/core/handlers/base.py:BaseHandler.load_middleware`).
