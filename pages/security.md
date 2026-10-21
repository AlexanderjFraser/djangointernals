---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: csrf-token, csrf-check, headers, csp, keys, signing, checks
---

# Security

Django's security machinery includes four middleware and two small libraries. `CsrfViewMiddleware` ordinarily refuses a request that may change something, such as a `"POST"`, unless it comes from the site's own pages and carries a **CSRF token** from them; `SecurityMiddleware`, `XFrameOptionsMiddleware` and `ContentSecurityPolicyMiddleware` add headers that tell the browser what to refuse; and `django.utils.crypto` and `django.core.signing` make, from `SECRET_KEY`, the keyed hashes with which Django signs what it hands out. System checks tagged `"security"` look over many settings.

The protections answer what a browser does on its user's behalf. It sends a site's cookies with the requests that other sites' pages make it send, as far as each cookie's SameSite attribute allows, so a page elsewhere may post a form to this site with the user's credentials: the attack the documentation calls a **cross-site request forgery** (`docs/ref/csrf.txt`). It shows a page inside a frame on any site that asks. It runs every script a page contains, whoever put it there. It follows a link to the site over plain HTTP, where anyone on the way can read the request and change the answer. And a value the site hands it, in a cookie or a link, can come back changed. Django cannot change the browser. What it can do is refuse a request it has no reason to trust, tell the browser in a response's headers what it may not do, and sign what it hands out so that a change is detected when it comes back.

The refusing and the telling are middleware, listed in `MIDDLEWARE` like any other and run as layers of the chain that [Handlers and middleware](handlers.md) describes, save what a view's decorators do for that view alone; the signing is a library of functions and classes that other code calls. None of them asks who the user is.

## Four middleware, three moments

Each middleware acts at the moments its work needs, and the moments are those of any layer of the chain: on the way in, the `process_request` hooks, outermost first; before the view, the `process_view` hooks, which the handler calls from the centre of the chain once it knows the view; on the way out, the `process_response` hooks, innermost first ([Handlers and middleware](handlers.md)). A middleware with no hook for a moment does nothing at it. The harbour office's site, which takes requests for berths at harbour.example, installs the four in the order `SecurityMiddleware`, `CsrfViewMiddleware`, `XFrameOptionsMiddleware`, `ContentSecurityPolicyMiddleware`; it requires HTTPS (`SECURE_SSL_REDIRECT`, with `SECURE_HSTS_SECONDS` of an hour) and sets a content security policy whose scripts must come from the site itself or carry the request's **nonce**, a random value that the policy names and an inline script repeats (`SECURE_CSP`, with `CSP.SELF` and `CSP.NONCE`) (`django/utils/csp.py:CSP`). Its view *berths* renders a form on `"GET"` and accepts it on `"POST"`, and its template asks for the token and the nonce:

```html
<form method="post">
  {% csrf_token %}
  <input name="ship">
  <button>Request a berth</button>
</form>
<script {% csp_nonce_attr %}>document.forms[0].ship.focus()</script>
```

The figure follows a request for that page from a browser that has never visited the site, and so holds no **CSRF secret**, the random string a page's token is made from. Only `CsrfViewMiddleware` has a `process_view`, and `XFrameOptionsMiddleware` has nothing to do on the way in.

```text figure=the-security-middleware
GET https://harbour.example/berths/, from a browser with no cookie

the way in, outermost first
  SecurityMiddleware                the request is secure: no redirect
  CsrfViewMiddleware                looks for the browser's CSRF secret in its cookie: there is none
  XFrameOptionsMiddleware           no process_request
  ContentSecurityPolicyMiddleware   gives the request a nonce, made when first read

at the centre of the chain
  CsrfViewMiddleware.process_view   "GET" is a safe method: accepted unchecked
  the view berths                   renders the template:
                                      {% csrf_token %} makes the secret and the page's token
                                      {% csp_nonce_attr %} makes the nonce

the way out, innermost first
  ContentSecurityPolicyMiddleware   Content-Security-Policy, naming the nonce
  XFrameOptionsMiddleware           X-Frame-Options: DENY
  CsrfViewMiddleware                the secret in the cookie csrftoken, and Vary: Cookie
  SecurityMiddleware                Strict-Transport-Security, X-Content-Type-Options,
                                    Referrer-Policy, Cross-Origin-Opener-Policy
```

*One request through the four middleware. The CSRF check waits at the centre of the chain, where the view is known; the secret and the nonce are made when the template asks for them, not on the way in; and the middleware add their headers on the way out, the innermost first.*

By the way out the template has made the secret and the nonce that the way in left unmade, and each middleware has something to write (`django/middleware/csrf.py:CsrfViewMiddleware.process_request`, `django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_request`). Look for each writing it in turn, from the innermost, and for the headers in the order the server was given them:

```text recording=security
GET https://harbour.example/berths/, no cookie: the four middleware, in and out
...
              ContentSecurityPolicyMiddleware.process_response(request, response)
                build_policy(SECURE_CSP, a LazyNonce, drawn: 'WgGtjgT-tnPCZAmsOjekWQ')  ->  "default-src 'self'; script-src 'self' 'nonce-WgGtjgT-tnPCZAmsOjekWQ'"
                -> the response, Content-Security-Policy added
            XFrameOptionsMiddleware.process_response(request, response)
              XFrameOptionsMiddleware.get_xframe_options_value(request, response)  ->  'DENY'
              -> the response, X-Frame-Options added
          CsrfViewMiddleware.process_response(request, response), request.META holding CSRF_COOKIE 'nUDKPUQ25LFtLiGKFwniLxI4ueoOhK66', CSRF_COOKIE_NEEDS_UPDATE True
            CsrfViewMiddleware._set_csrf_cookie(request, response)
            -> the response, Vary added, the cookie csrftoken set
        SecurityMiddleware.process_response(request, response)  ->  the response, Strict-Transport-Security added, X-Content-Type-Options added, Referrer-Policy added, Cross-Origin-Opener-Policy added
      start_response("200 OK", headers), the headers being:
        Content-Type: text/html; charset=utf-8
        Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-WgGtjgT-tnPCZAmsOjekWQ'
        X-Frame-Options: DENY
        Vary: Cookie
        Strict-Transport-Security: max-age=3600
        X-Content-Type-Options: nosniff
        Referrer-Policy: same-origin
        Cross-Origin-Opener-Policy: same-origin
        Set-Cookie: csrftoken=nUDKPUQ25LFtLiGKFwniLxI4ueoOhK66; expires=Mon, 11 Oct 2027 09:00:00 GMT; Max-Age=31449600; Path=/; SameSite=Lax
...
```

After Content-Type, which the response was made with, the headers stand in the order the middleware added them, and the cookie comes last, since a response keeps its cookies apart from its headers and the handler writes them after (`django/core/handlers/wsgi.py:WSGIHandler.__call__`). Over plain HTTP the same request goes no further than the first layer, which answers it with a redirect to HTTPS ([The security headers: `SecurityMiddleware` and `XFrameOptionsMiddleware`](security/headers.md)) (`django/middleware/security.py:SecurityMiddleware.process_request`).

## The CSRF check

A cross-site request forgery works because the browser attaches the site's cookie to a request that another site's page made. The defence rests on what that page cannot do: it can make the browser send the cookie, but it cannot read it, nor any page of this site. So `CsrfViewMiddleware` keeps a CSRF secret for a browser, in its cookie or, with `CSRF_USE_SESSIONS`, in the session, and the site's own pages carry a token made from it, a different one on every page ([The CSRF secret and its token](security/csrf-token.md)) (`django/middleware/csrf.py:get_token`). Before the view, a request of a method that is not **safe**, as `"GET"`, `"HEAD"`, `"OPTIONS"` and `"TRACE"` are, must ordinarily come from the site's own origin or a trusted one and carry a token that matches the browser's secret; one that fails is answered by the failure view, with a 403 by default, in place of its view ([The CSRF check: `CsrfViewMiddleware.process_view`](security/csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`). The check runs in `CsrfViewMiddleware.process_view`, a hook that is handed the view, because a view may carry the mark of `csrf_exempt`, which the middleware reads off the view ([The centre of the chain](handlers/view.md#the-process_view-hooks)) (`django/views/decorators/csrf.py:csrf_exempt`).

## Headers the browser obeys

The other three middleware work through the browser: each header is an instruction it carries out. `SecurityMiddleware` adds up to four. Strict-Transport-Security, which it sends on a secure request when `SECURE_HSTS_SECONDS` is not zero, tells the browser to reach the site only over HTTPS, for as long as the header says; X-Content-Type-Options, not to guess a response's type from its content; Referrer-Policy, how much of the page's address to send in a `"Referer"`; Cross-Origin-Opener-Policy, at its default, to keep this window apart from other origins' windows. `XFrameOptionsMiddleware` adds X-Frame-Options to any response that passes through it but an exempt view's, by default `"DENY"`: show this page in no frame. `ContentSecurityPolicyMiddleware` adds the policy written from `SECURE_CSP` or from a view's `csp_override`: where the page may load scripts, styles and the rest from, and which inline scripts it may run. None of them replaces a header the response already has ([The security headers: `SecurityMiddleware` and `XFrameOptionsMiddleware`](security/headers.md)) (`django/middleware/security.py:SecurityMiddleware.process_response`, `django/middleware/clickjacking.py:XFrameOptionsMiddleware.process_response`, `django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_response`).

Under the harbour's policy, the browser runs an inline script only if its nonce is the one the policy names. The nonce `ContentSecurityPolicyMiddleware.process_request` gives each request is a `LazyNonce`, made only when something first reads it, so on the way out `build_policy` writes it into the policy if it was made and leaves it out if not ([Content Security Policy and the nonce](security/csp.md)) (`django/utils/csp.py:build_policy`).

## Keys and signatures

Every value Django signs is keyed from `SECRET_KEY`, unless the code that signs it is given another secret. The base of them is `salted_hmac`: an HMAC of the value, whose key is made by hashing together a **salt**, a string that names the use, and the secret, the salt first. So each use has a key of its own, and a value made for one use does not verify for another. Django makes its values with `SECRET_KEY` alone. Its signers, the password-reset tokens, and `get_user` when it reads back the hash a session keeps, check what comes back against `SECRET_KEY` and then against each of `SECRET_KEY_FALLBACKS`, which is how a site changes its key without at once refusing everything made with the old one ([Secret keys and `django.utils.crypto`](security/keys.md)) (`django/utils/crypto.py:salted_hmac`, `django/core/signing.py:Signer.unsign`, `django/contrib/auth/tokens.py:PasswordResetTokenGenerator.check_token`, `django/contrib/auth/__init__.py:get_user`).

`Signer` writes a string, a separator and the string's HMAC; `TimestampSigner` puts the time of signing between the two, so that a reader can refuse a value older than it wants. `dumps` signs any value JSON can hold, by way of a `TimestampSigner` whose salt is `"django.core.signing"` unless it is given another, and `loads` checks the signature and gives the value back. The value `dumps` signs is only encoded, in base64 and sometimes compressed, which anyone can undo: a signature makes a change detectable and hides nothing ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](security/signing.md)) (`django/core/signing.py:dumps`). The users of both libraries are mostly in other chapters: signed cookies ([Cookies](http/cookies.md)), the session's stored data ([The session store: `SessionBase`](auth/sessions.md)), and the password-reset tokens and the hash that ties a session to a password, which `salted_hmac` makes directly ([Password reset: `PasswordResetTokenGenerator` and the reset views](auth/password-reset.md), [The user of a request: `login`, `logout` and `AuthenticationMiddleware`](auth/login.md)).

## The neighbours

Everything here is only as good as the settings it reads, and the security checks look over many of them, most of the checks only when the check command is given `--deploy` ([The security checks](security/checks.md)). The host and the scheme they rely on, `HttpRequest.get_host` with `ALLOWED_HOSTS` and `HttpRequest.is_secure`, are the request's ([Headers, host and scheme](http/headers.md)). The CSRF decorators made from the middleware are in [A middleware as a decorator](views/middleware-decorators.md), and `csrf_exempt`'s mark in [View decorators](views/decorators.md). The context processors that put the token and the nonce in a template's context are in [The context: `Context`, `RequestContext` and context processors](templates/context.md), and the escaping that keeps a value from becoming markup in [Autoescaping and safe strings](templates/autoescape.md). The login that rotates the CSRF secret is in [Authentication, sessions and messages](auth.md), and the test client, which skips the CSRF check unless it is made with `enforce_csrf_checks=True`, in [The test client: `Client` and `ClientHandler`](testing/client.md).
