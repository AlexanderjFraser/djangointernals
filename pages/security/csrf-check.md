---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The CSRF check: `CsrfViewMiddleware.process_view`

Before a view runs, the CSRF check puts a request whose method is not safe through a sequence of tests, and the first test that decides ends it. The tests ask where the request came from, the site or one it trusts, by its `"Origin"` header or, on a secure request without one, its `"Referer"`; then whether it carries a token made from the browser's CSRF secret, which no page of another site can read. The check is `CsrfViewMiddleware.process_view`; the origins it trusts are `CSRF_TRUSTED_ORIGINS`, and a request it refuses is answered by the view `CSRF_FAILURE_VIEW` names, `csrf_failure` by default.

Four of the tests let a request through unchecked. Each refusal has a **reason**, a short sentence that is logged and handed to the failure view (`django/middleware/csrf.py:CsrfViewMiddleware._reject`). The secret and its token are in [The CSRF secret and its token](csrf-token.md).

In the figure a request goes down the tests on the left until one decides it, and leaves by that test's arrow; its origin is judged by one header or by none, and a request that passes every test is accepted at the foot.

```text figure=the-check
CsrfViewMiddleware.process_view, its tests from the top          where a request leaves

let through
  already marked "csrf_processing_done"                     ->  on to the view
  the view marked csrf_exempt                               ->  on to the view, not marked
  a safe method: "GET", "HEAD", "OPTIONS", "TRACE"          ->  _accept: marked, on to the view
  the test client's "_dont_enforce_csrf_checks"             ->  _accept: marked, on to the view

the origin, by one header or none
  an Origin header, which _origin_verified does not accept  ->  _reject: REASON_BAD_ORIGIN
  no Origin, a secure request: _check_referer refuses       ->  _reject: one of the four Referer reasons
  no Origin, plain HTTP: no header read, on to the token

the token: _check_token
  the cookie malformed                                      ->  _reject: a malformed cookie
  no secret                                                 ->  _reject: REASON_NO_CSRF_COOKIE
  no token in "csrfmiddlewaretoken", no X-CSRFToken         ->  _reject: REASON_CSRF_TOKEN_MISSING
  the token malformed                                       ->  _reject: a malformed token
  a token that does not match the secret                    ->  _reject: incorrect

every test passed                                           ->  _accept: marked, on to the view

_reject: the failure view's 403 in the view's place, the reason logged
```

*The tests of `CsrfViewMiddleware.process_view`, in the order it makes them. A request leaves at the first test that decides it: on to the view, marked as checked or not, or to `_reject` with a reason, whose text the table under "Refusal and its reasons" gives.*

## Requests let through unchecked

`CsrfViewMiddleware.process_view` first lets through a request that has been accepted already. `CsrfViewMiddleware._accept` marks an accepted request with the attribute `"csrf_processing_done"`, and `process_view` returns at once for a request so marked (`django/middleware/csrf.py:CsrfViewMiddleware._accept`). The mark is what lets the middleware and the `csrf_protect` decorator, a second instance of the class around the view, share one request: the chain's `process_view` runs first, and once it has accepted the request the decorator's returns without testing anything ([A middleware as a decorator](../views/middleware-decorators.md)). How the two then send the cookie only once is in [The CSRF secret and its token](csrf-token.md).

A view marked by `csrf_exempt` is let through next, without the request being marked ([View decorators](../views/decorators.md)). It is tested after `CsrfViewMiddleware.process_request` has read the browser's secret, so `get_token` in an exempt view still uses that secret (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`).

Then the safe methods, `"GET"`, `"HEAD"`, `"OPTIONS"` and `"TRACE"`: whatever RFC 9110 does not define as safe is taken to need protection. Last, the test client's flag: its handler sets `"_dont_enforce_csrf_checks"` on every request, true unless the client was made with `enforce_csrf_checks=True` ([The test client: `Client` and `ClientHandler`](../testing/client.md)) (`django/test/client.py:ClientHandler.__call__`). Both these paths mark the request as checked.

## The origin: `_origin_verified` and `_check_referer`

A request with an `"Origin"` header is refused unless `CsrfViewMiddleware._origin_verified` accepts it, in one of three ways tried in order (`django/middleware/csrf.py:CsrfViewMiddleware._origin_verified`). The header may equal the site's own origin: `"https"` or `"http"` as `HttpRequest.is_secure` says, and the host from `HttpRequest.get_host` ([Headers, host and scheme](../http/headers.md)). Where `get_host` raises `DisallowedHost`, for a host that is not valid or that `ALLOWED_HOSTS` refuses, this way does not match and the next is tried. The header may be one of `CSRF_TRUSTED_ORIGINS` exactly. Or it may have the scheme of a trusted origin written with a `"*"`, and a host that matches that origin's host, star taken off, by `is_same_domain`, where a pattern that begins with a dot matches the domain and every subdomain (`django/utils/http.py:is_same_domain`).

Posted under two trusted origins with the Origins of other sites, the harbour's form shows each origin's scheme and host kept apart. The wildcard admits pilots.harbour.example over HTTPS. The same host over HTTP is compared with no trusted host, since no trusted origin has that scheme: the one `is_same_domain` under it is `get_host`'s, which tests the `"Host"` against `ALLOWED_HOSTS` (`django/http/request.py:validate_host`). And a.pay.example is compared only with the wildcard's host, since an origin given exactly covers none of its subdomains.

```text recording=security
POST https://harbour.example/berths/, other sites' Origins, under CSRF_TRUSTED_ORIGINS = ['https://*.harbour.example', 'https://pay.example'], with a handler built and used under it
...
    CsrfViewMiddleware._origin_verified(request), the Origin 'https://pilots.harbour.example'
      ...
      CsrfViewMiddleware.allowed_origins_exact, the body of the cached_property  ->  {'https://pay.example'}
      CsrfViewMiddleware.allowed_origin_subdomains, the body of the cached_property  ->  defaultdict {'https': ['.harbour.example']}
      is_same_domain('pilots.harbour.example', '.harbour.example')  ->  True
      -> True
    ...
    CsrfViewMiddleware._origin_verified(request), the Origin 'http://pilots.harbour.example'
      HttpRequest.get_host(), the Host 'harbour.example'
        is_same_domain('harbour.example', 'harbour.example')  ->  True
        -> 'harbour.example'
      -> False
    ...
    CsrfViewMiddleware._origin_verified(request), the Origin 'https://a.pay.example'
      ...
      is_same_domain('a.pay.example', '.harbour.example')  ->  False
      -> False
      ...
```

The setting is read by each instance of the middleware, as the first request alone shows: `CSRF_TRUSTED_ORIGINS` goes into three cached properties, each the first time the instance needs it and never again (`django/middleware/csrf.py:CsrfViewMiddleware.allowed_origin_subdomains`). A chain that has refused an origin goes on refusing it after the setting changes to name it, while a chain built after accepts it ([Building the middleware chain](../handlers/chain.md#when-the-chain-is-built)).

> **History.** Before 4.0 the check did not read the `"Origin"` header, and `CSRF_TRUSTED_ORIGINS`, which 1.9 had added to allow cross-origin requests over HTTPS, held hosts alone, a leading dot standing for a domain and its subdomains. 4.0 made the check consult the `"Origin"` whenever a request has one, and to that end the setting's values had to begin with a scheme: `".example.com"` became `"https://*.example.com"`. A system check made for the change, `check_csrf_trusted_origins`, still reports a value without `"://"` as `"4_0.E001"` (`docs/releases/1.9.txt`, `docs/releases/4.0.txt`, `django/core/checks/compatibility/django_4_0.py:check_csrf_trusted_origins`).

Only a request with no `"Origin"` has its `"Referer"` read, and only if it is secure; over plain HTTP such a request goes on to the token with neither header read (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`).

> **Why.** An attacker in the middle of a visit to the site over plain HTTP can send the browser a form that posts to the site's HTTPS address, and can give it a cookie and a token that match. The cookie is what makes this work: browsers accept a cookie set over plain HTTP even for a site they reach over HTTPS, and since a secret kept in the cookie is tied to no session, a secret of the attacker's making serves as well as the site's (`docs/ref/csrf.txt`). Nothing stops that on a plain-HTTP connection, but a site served over HTTPS is expected to do better, so a secure request with no `"Origin"` must bring a `"Referer"` that is itself HTTPS, which treats the site's plain-HTTP pages as untrusted. The check can afford to be that strict because the `"Referer"` is seldom missing over HTTPS: Barth et al. found it absent from same-domain HTTPS requests in about 0.2% of cases or fewer (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`).

`CsrfViewMiddleware._check_referer` refuses a request with no `"Referer"`, one that does not parse into a scheme and a host, and one whose scheme is not `"https"`. It accepts a host that matches a trusted origin's host by `is_same_domain`, whatever that origin's scheme. Otherwise the host must match the cookie's domain: `CSRF_COOKIE_DOMAIN`, or `SESSION_COOKIE_DOMAIN` under `CSRF_USE_SESSIONS`. The request's port is added to that domain unless it is 443 or 80. When the domain is `None`, as by default, the host must match `get_host`, which includes any port, and a `DisallowedHost` from `get_host` is refused with `REASON_BAD_REFERER` (`django/middleware/csrf.py:CsrfViewMiddleware._check_referer`).

Look for the trusted hosts, which a third cached property reads without their schemes and which are tried before the site's own, so the wildcard admits the site's own `"Referer"` at once; for the `"Referer"` on port 8443, which matches neither a trusted host nor the site's own, since its port is part of what is compared and the site's host, as `get_host` gives it, has none; and for the `"Referer"` that begins `"http://"`, refused as insecure before any host is compared.

```text recording=security
POST https://harbour.example/berths/, a Referer and no Origin, under CSRF_TRUSTED_ORIGINS = ['https://*.harbour.example', 'https://pay.example'], with a handler built and used under it
...
    CsrfViewMiddleware._check_referer(request), the Referer 'https://harbour.example/berths/'
      CsrfViewMiddleware.csrf_trusted_origins_hosts, the body of the cached_property  ->  ['.harbour.example', 'pay.example']
      is_same_domain('harbour.example', '.harbour.example')  ->  True
      -> None
    ...
    CsrfViewMiddleware._check_referer(request), the Referer 'https://harbour.example:8443/berths/'
      is_same_domain('harbour.example:8443', '.harbour.example')  ->  False
      is_same_domain('harbour.example:8443', 'pay.example')  ->  False
      HttpRequest.get_host(), the Host 'harbour.example'
        is_same_domain('harbour.example', 'harbour.example')  ->  True
        -> 'harbour.example'
      is_same_domain('harbour.example:8443', 'harbour.example')  ->  False
      raises RejectRequest
    log, WARNING to django.security.csrf: Forbidden (Referer checking failed - https://harbour.example:8443/berths/ does not match any trusted origins.): /berths/
    ...
    CsrfViewMiddleware._check_referer(request), the Referer 'http://harbour.example/berths/'  raises RejectRequest
    log, WARNING to django.security.csrf: Forbidden (Referer checking failed - Referer is insecure while host is secure.): /berths/
    ...
```

## The token: `_check_token`

`CsrfViewMiddleware._check_token` reads the secret again from the cookie or the session, by `CsrfViewMiddleware._get_secret`, rather than taking the copy `CsrfViewMiddleware.process_request` kept in `META`: an authentication middleware may have called `rotate_token` in its `process_request`, replacing that copy, while the browser's token was made from the old secret. A malformed cookie is refused, though `process_request` has already replaced it for the response ([The CSRF secret and its token](csrf-token.md)). A request with no secret is refused too, and **login CSRF** is among the attacks that stops: another site tricking a user's browser into logging into this one with someone else's credentials (`docs/ref/csrf.txt`) (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`).

For a `"POST"` the token is the form field `"csrfmiddlewaretoken"`. An `UnreadablePostError`, an error in reading the body, counts as an empty field, so that the check does not raise it. If the field is missing or empty, or the method is another, the token is the header `CSRF_HEADER_NAME` names, `"HTTP_X_CSRFTOKEN"` by default, which is X-CSRFToken: the fallback that makes things easier for AJAX and possible for `"PUT"` and `"DELETE"`. No other body is read, so a `"PUT"` with a good token only in its form-encoded body is refused with `"CSRF token missing."` (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`).

The token must then be 32 or 64 letters and digits (`django/middleware/csrf.py:_check_token_format`). `_does_token_match` unmasks a token of 64, takes one of 32 as the secret itself, as a script that read the cookie sends it, and compares it with the secret by `constant_time_compare` ([Secret keys and `django.utils.crypto`](keys.md)) (`django/middleware/csrf.py:_does_token_match`). The reason for a malformed or wrong token names where the token was found, the form or the header, as in `"CSRF token from the 'X-Csrftoken' HTTP header has incorrect length."` (`django/middleware/csrf.py:CsrfViewMiddleware._bad_token_message`).

## Refusal and its reasons

`CsrfViewMiddleware.process_view` makes the origin test's reason in place; the `"Referer"` and token tests raise `RejectRequest` with theirs, which `process_view` catches; and each refusal ends in `CsrfViewMiddleware._reject`, given the reason (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`).

| reason | refused when | message |
|---|---|---|
| `REASON_BAD_ORIGIN` | the `"Origin"` is not verified | `"Origin checking failed - %s does not match any trusted origins."` |
| `REASON_NO_REFERER` | secure, and no `"Origin"` or `"Referer"` | `"Referer checking failed - no Referer."` |
| `REASON_MALFORMED_REFERER` | the `"Referer"` does not parse into a scheme and a host | `"Referer checking failed - Referer is malformed."` |
| `REASON_INSECURE_REFERER` | the `"Referer"` is not HTTPS | `"Referer checking failed - Referer is insecure while host is secure."` |
| `REASON_BAD_REFERER` | the host matches neither a trusted host nor the cookie's domain, by default the site's | `"Referer checking failed - %s does not match any trusted origins."` |
| a malformed cookie | its length or characters | `"CSRF cookie has incorrect length."`, `"CSRF cookie has invalid characters."` |
| `REASON_NO_CSRF_COOKIE` | no secret | `"CSRF cookie not set."` |
| `REASON_CSRF_TOKEN_MISSING` | no token in `"csrfmiddlewaretoken"`, no X-CSRFToken header | `"CSRF token missing."` |
| a malformed token | its length or characters | for a token from the form, such as `"CSRF token from POST has incorrect length."` |
| a wrong token | it does not match the secret | for a token from the form, `"CSRF token from POST incorrect."` |

*The reasons the CSRF check gives, in the order it tests. The messages for a malformed cookie or token are made from `REASON_INCORRECT_LENGTH` and `REASON_INVALID_CHARACTERS`.*

## The failure view: `CSRF_FAILURE_VIEW` and `csrf_failure`

`CsrfViewMiddleware._reject` calls the view `CSRF_FAILURE_VIEW` names, imported by `get_callable`, with the request and the reason, and logs the response it gets back by `log_response` on the logger `"django.security.csrf"`, as `"Forbidden (%s): %s"` with the reason and the path; that response goes out through the chain in the view's place (`django/middleware/csrf.py:CsrfViewMiddleware._reject`). The security checks import the view and test that it takes a request and a reason ([The security checks](checks.md)) (`django/core/checks/security/csrf.py:check_csrf_failure_view`). `_reject` is a method so that a subclass can replace it: the class of `requires_csrf_token`, like that of `ensure_csrf_cookie`, replaces it with one that refuses nothing ([A middleware as a decorator](../views/middleware-decorators.md)) (`django/views/decorators/csrf.py`).

`log_response` logs a 4xx as a warning and marks the response as logged, so that the handler, which logs a response of 400 or more to `"django.request"`, does not log it again ([Logging](../startup/logging.md#log_response-a-response-is-logged-once)) (`django/utils/log.py:log_response`). The harbour's form posted without its token shows a refusal whole: the token test's reason, handed to `_reject`; inside the failure view, the request's nonce asked of the `csp` context processor, `"403_csrf.html"` sought and not found, and the built-in page compiled in its place, its stylesheet drawing the nonce; the warning to `"django.security.csrf"`; and, last, the handler's `log_response` finding the response already logged.

```text recording=security
POST https://harbour.example/berths/, no token: refused, and the failure view
...
        CsrfViewMiddleware._check_token(request)
          CsrfViewMiddleware._get_secret(request)  ->  'SWEQqS7DG7hYtBdVhvpQRYXJGaCfdMll'
          RejectRequest('CSRF token missing.')
          raises RejectRequest
        CsrfViewMiddleware._reject(request, 'CSRF token missing.')
          _get_failure_view()
            get_callable('django.views.csrf.csrf_failure')  ->  the function django.views.csrf.csrf_failure
            -> the function django.views.csrf.csrf_failure
          csrf_failure(request, reason='CSRF token missing.')
            csp(request), called by csrf_failure  ->  {'csp_nonce': a LazyNonce, not drawn}
            get_template('403_csrf.html')  raises TemplateDoesNotExist
            Engine.from_string(the text of django/views/templates/csrf_403.html)
            nonce_attr(context), for {% csp_nonce_attr %}
              generate_nonce()  ->  'SFWHX0PmviNLKDg9bdZhrQ'
              -> 'nonce="SFWHX0PmviNLKDg9bdZhrQ"'
            -> an HttpResponseForbidden, status 403
          log_response('Forbidden (%s): %s', ...) to django.security.csrf, the response not yet logged
            log, WARNING to django.security.csrf: Forbidden (CSRF token missing.): /berths/
          -> an HttpResponseForbidden, status 403
        -> an HttpResponseForbidden, status 403
      ContentSecurityPolicyMiddleware.process_response(request, response)
        build_policy(SECURE_CSP, a LazyNonce, drawn: 'SFWHX0PmviNLKDg9bdZhrQ')  ->  "default-src 'self'; script-src 'self' 'nonce-SFWHX0PmviNLKDg9bdZhrQ'"
        -> the response, Content-Security-Policy added
      log_response('%s: %s', ...) to django.request, the response already marked as logged
      ...
```

`csrf_failure` asks the project's template engines for `"403_csrf.html"`, and when none has it renders the built-in `"csrf_403.html"`, with an `Engine` of its own, which does not read `TEMPLATES`; either page goes back in an `HttpResponseForbidden` (`django/views/csrf.py:csrf_failure`).

The built-in page's context holds the reason and two flags, `"no_referer"` and `"no_cookie"`, true under `REASON_NO_REFERER` and `REASON_NO_CSRF_COOKIE` (`django/views/csrf.py:csrf_failure`). The page shows its paragraphs for a missing `"Referer"` or cookie only under those two reasons, and the reason itself, with a list of what to check, only when `settings.DEBUG` is true (`django/views/templates/csrf_403.html`). On the harbour's site the 403's policy names the nonce in `"script-src"` alone, where its setting puts `CSP.NONCE`, so the nonce on the built-in page's stylesheet is not one the policy admits for styles ([Content Security Policy and the nonce](csp.md)).

> **Trap.** A project's own `"403_csrf.html"` gets none of that context. `csrf_failure` renders it with the request alone, so it sees what a `RequestContext` gives it, the context processors' values, and nothing of the view's: a template that writes `{{ reason }}`, `{{ no_cookie }}` and `{{ csp_nonce }}` renders the first two empty and the third, where the engine has the `csp` processor, with the nonce (`django/views/csrf.py:csrf_failure`).
