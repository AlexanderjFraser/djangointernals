---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Services
contents: csrf-token, csrf-check, headers, csp, keys, signing, checks
---

# Security

Django's protections around a request are a few middleware that guard against what a browser would otherwise allow, and two small libraries, `django.utils.crypto` and `django.core.signing`, that make the keyed hashes and signatures the rest of Django relies on. `CsrfViewMiddleware` checks that a request of a method that may change something, such as a `"POST"`, came from the site's own pages and carries a token from them; `SecurityMiddleware`, `XFrameOptionsMiddleware` and `ContentSecurityPolicyMiddleware` add headers that tell the browser what to refuse.

A browser does several things on its user's behalf. It sends a site's cookies with requests that other sites' pages make to it, unless a cookie's SameSite attribute holds it back, so a form on another site can post to this one as the logged-in user (`docs/ref/settings.txt`). It shows a page inside a frame on any other site that asks. It runs every script a page contains, whoever put it there, and it will load a page over plain HTTP if a link says so. And a value the site hands it, in a cookie or a URL, can come back changed. Django cannot change the browser. What it can do is refuse a request it has no reason to trust, tell the browser in a response's headers what it may not do, and sign what it hands out so that a change is detected when it comes back.

Each of these is a separate piece that a project chooses. The protections against forged requests and the headers are middleware, listed in `MIDDLEWARE` like any other, and work as layers of the chain that [Handlers and middleware](handlers.md) describes. Signing is a library of functions and classes that other code calls. None of them knows who the user is.

## The objects

| object | what it is | when it acts |
|---|---|---|
| `CsrfViewMiddleware` | keeps a random **CSRF secret** for each browser, in a cookie or the session, and checks a request of a method that is not **safe**, as `"GET"`, `"HEAD"`, `"OPTIONS"` and `"TRACE"` are, for its origin and for a **token** made from that secret | on the way in, to read the secret; before the view, to check; on the way out, to send the secret |
| `get_token` | makes the token a page carries, by masking the secret anew at each call | when a template or a view asks for it |
| `csrf_failure` | the view that, by default, answers a refused request, with a 403 | when the check refuses |
| `SecurityMiddleware` | can redirect plain HTTP to HTTPS, and adds up to four headers, Strict-Transport-Security among them | on the way in, the redirect; on the way out, the headers |
| `XFrameOptionsMiddleware` | adds X-Frame-Options, which says whether the page may be shown in a frame | on the way out |
| `ContentSecurityPolicyMiddleware` | gives each request a **nonce**, a random value that the policy names and the page's scripts carry, and adds the policy that says what the page may load and run | on the way in, the nonce; on the way out, the policy |
| `salted_hmac` | an HMAC of a value, with a key made from a **salt**, a string that names the use, and `SECRET_KEY` or a secret it is given | whenever it is called |
| `Signer`, `TimestampSigner` | add an HMAC, and a time, to a string, and check them when it comes back | whenever they are called |
| the security checks | system checks of the settings, most of them run only by the check command with `--deploy` | when the check framework runs |

*The objects of Django's security machinery. The middleware live in `django/middleware/`, the HMAC and signing in `django/utils/crypto.py` and `django/core/signing.py`, the checks in `django/core/checks/security/`.*

## One request through the security middleware

The harbour office's site takes requests for berths at harbour.example. Its settings install the four middleware, require HTTPS, and set a content security policy whose scripts must come from the site itself or carry the request's nonce (`django/utils/csp.py:CSP`):

```python
# harbour/settings.py
from django.utils.csp import CSP

ALLOWED_HOSTS = ["harbour.example"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 3600
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
}
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.csp"]},
    }
]
```

One view shows the form and accepts it:

```python
# harbour/office/views.py
from django.http import HttpResponse
from django.shortcuts import render


def berths(request):
    if request.method == "POST":
        return HttpResponse("Berth requested.")
    return render(request, "office/berths.html")
```

```html
<!-- harbour/office/templates/office/berths.html -->
<form method="post">
  {% csrf_token %}
  <input name="ship">
  <button>Request a berth</button>
</form>
<script {% csp_nonce_attr %}>document.forms[0].ship.focus()</script>
```

The four middleware act at different moments of the request, and in the order of the list on the way in and its reverse on the way out:

```text figure=the-security-middleware
on the way in, in the order of MIDDLEWARE
  SecurityMiddleware                plain HTTP: answers with a redirect to HTTPS, and nothing inside it runs
  CsrfViewMiddleware                reads the CSRF secret from the request's cookie
  ContentSecurityPolicyMiddleware   gives the request a nonce, made when it is first used

before the view
  CsrfViewMiddleware                a method that is not safe: checks the origin, then the token; or refuses with a 403

the view
  renders the template              {% csrf_token %} asks for a token, {% csp_nonce_attr %} for the nonce

on the way out, in the reverse order
  ContentSecurityPolicyMiddleware   Content-Security-Policy, with the nonce if it was used
  XFrameOptionsMiddleware           X-Frame-Options
  CsrfViewMiddleware                the secret in a cookie, if a token was asked for
  SecurityMiddleware                Strict-Transport-Security on HTTPS, X-Content-Type-Options,
                                    Referrer-Policy, Cross-Origin-Opener-Policy
```

*Where each of the four middleware acts on one request. The CSRF check waits for the view to be known; the headers are all added on the way out, by the innermost middleware first.*

A run of the example, with Django's test client making the requests, gave this for the page that shows the form:

```text
GET https://harbour.example/berths/
200 OK
Content-Type: text/html; charset=utf-8
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-D5c3_Jq0piOSyAMgXQiP4Q'
X-Frame-Options: DENY
Vary: Cookie
Strict-Transport-Security: max-age=3600
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Cross-Origin-Opener-Policy: same-origin
Set-Cookie: csrftoken=7YkKvMPTXJDYBQxRXZU3jXyYEN3cg7ZV; expires=Thu, 14 Oct 2027 18:09:33 GMT; Max-Age=31449600; Path=/; SameSite=Lax
```

```html
<form method="post">
  <input type="hidden" name="csrfmiddlewaretoken" value="7QC6uv1bW9BmWyM8sYm5Dg8ucdW1uhW04EMGP7GUJI4ane9PfN6YM3wiGQP3AeLL">
  <input name="ship">
  <button>Request a berth</button>
</form>
<script nonce="D5c3_Jq0piOSyAMgXQiP4Q">document.forms[0].ship.focus()</script>
```

The headers came in the order the middleware added them, which is the onion read from the inside; a response keeps its cookies apart, and the handler writes them after its headers (`django/core/handlers/wsgi.py:WSGIHandler.__call__`). The policy came first, from the innermost middleware, with the nonce that `{% csp_nonce_attr %}` had written into the page. X-Frame-Options came next, `"DENY"` because `X_FRAME_OPTIONS` defaults to it. Then `CsrfViewMiddleware` set its cookie and added `"Cookie"` to `"Vary"`, because the template's `{% csrf_token %}` had asked for a token. Last, `SecurityMiddleware` added Strict-Transport-Security, which it sends only on a secure request, and three headers whose settings are on by default (`django/middleware/security.py:SecurityMiddleware.process_response`).

The cookie and the token are not the same string. The cookie holds the secret, 32 letters and digits. The page holds a token of 64: a random mask, and the secret enciphered with it. A second request from the same client got the same secret back in its cookie and a different token in its page, since every call of `get_token` makes a new mask (`django/middleware/csrf.py:get_token`).

The same client then posted the form, and then four posts, each lacking or changing one part of it. What the CSRF check did with each, as the logger `"django.security.csrf"` recorded the refusals:

```text
POST https://harbour.example/berths/
  the cookie, the token, Origin: https://harbour.example    200  Berth requested.
  the cookie and Origin, no token                           403  Forbidden (CSRF token missing.): /berths/
  the cookie and the token, Origin: https://evil.example    403  Forbidden (Origin checking failed - https://evil.example does not match any trusted origins.): /berths/
  the cookie and the token, no Origin and no Referer        403  Forbidden (Referer checking failed - no Referer.): /berths/
  the token and Origin, no cookie                           403  Forbidden (CSRF cookie not set.): /berths/
```

The accepted post's response had the same headers as the page's, with these differences: no cookie and no `"Vary"`, since nothing asked for a token, and a policy of `script-src 'self'` alone. Nothing in that request read its nonce, and the policy names a nonce only when something did ([Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](security/csp.md)).

Over plain HTTP the request went no further than the first middleware. `SecurityMiddleware.process_request` answered with a redirect to the same address over HTTPS, so the three middleware inside it never ran and the redirect carried none of their headers; it still had `SecurityMiddleware`'s own, added as its response went out (`django/middleware/security.py:SecurityMiddleware.process_request`):

```text
GET http://harbour.example/berths/
301 Moved Permanently
Content-Type: text/html; charset=utf-8
Location: https://harbour.example/berths/
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Cross-Origin-Opener-Policy: same-origin
```

## The CSRF check

A **cross-site request forgery** is a request that another site's page makes the browser send to this one: a form that posts to harbour.example from a page elsewhere, which the browser may send with harbour.example's cookies. To the site it looks like the user's own request. The defence rests on what the other page cannot do: it may make the browser send the cookie, but it cannot read it, nor any page of this site.

So `CsrfViewMiddleware` keeps a secret for each browser and gives the site's own pages a token made from it. When a request arrives, `CsrfViewMiddleware.process_request` reads the secret from the cookie, `"csrftoken"` unless `CSRF_COOKIE_NAME` says otherwise, or from the session when `CSRF_USE_SESSIONS` is true. A template that writes `{% csrf_token %}` calls `get_token` by way of the CSRF context processor, which makes a secret if the request had none and marks it to be sent back; on the way out, `CsrfViewMiddleware.process_response` sets the cookie, or stores the secret in the session ([The CSRF secret and its token](security/csrf-token.md)) (`django/middleware/csrf.py:CsrfViewMiddleware.process_response`).

The check itself is in `CsrfViewMiddleware.process_view`, which the handler calls with the view it has resolved; it reads there the mark `csrf_exempt` leaves on a view ([View decorators](views/decorators.md)). It lets through, unchecked, the methods that RFC 9110 calls safe, `"GET"`, `"HEAD"`, `"OPTIONS"` and `"TRACE"`: a view that changes something on a `"GET"` has no protection from it. Any other method is checked in two steps. First the origin: a request with an `"Origin"` header must come from the site's own scheme and host, or from one of `CSRF_TRUSTED_ORIGINS`; a secure request with no `"Origin"` must have a `"Referer"` that names the site or a trusted origin. Then the token: there must be a secret, and a token, in the form field `"csrfmiddlewaretoken"` or the header X-CSRFToken, that matches it. A request that fails is answered by the view `CSRF_FAILURE_VIEW` names, `csrf_failure` by default, with a 403, and the view it was going to is never called ([The CSRF check: `CsrfViewMiddleware.process_view`](security/csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`).

The token is masked so that it differs on every page while the secret stays the same; Django's documentation gives the reason as protection against the BREACH attack (`docs/ref/csrf.txt`). The secret is kept from request to request; `rotate_token`, which `login` in `django.contrib.auth` calls, replaces it, as does `CsrfViewMiddleware.process_request` itself when a request's cookie is malformed (`django/contrib/auth/__init__.py:login`, `django/middleware/csrf.py:rotate_token`).

## Headers that tell the browser what to refuse

The other three middleware do their work by adding headers to the response on the way out. On the way in, `SecurityMiddleware` does only the redirect of plain HTTP that `SECURE_SSL_REDIRECT` turns on, and `ContentSecurityPolicyMiddleware` only gives the request its nonce ([The security headers: `SecurityMiddleware` and `XFrameOptionsMiddleware`](security/headers.md)).

| header | added by | from the settings |
|---|---|---|
| Strict-Transport-Security | `SecurityMiddleware`, on a secure request only | `SECURE_HSTS_SECONDS`, with `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` |
| X-Content-Type-Options | `SecurityMiddleware` | `SECURE_CONTENT_TYPE_NOSNIFF` |
| Referrer-Policy | `SecurityMiddleware` | `SECURE_REFERRER_POLICY` |
| Cross-Origin-Opener-Policy | `SecurityMiddleware` | `SECURE_CROSS_ORIGIN_OPENER_POLICY` |
| X-Frame-Options | `XFrameOptionsMiddleware` | `X_FRAME_OPTIONS` |
| Content-Security-Policy | `ContentSecurityPolicyMiddleware` | `SECURE_CSP` |
| Content-Security-Policy-Report-Only | `ContentSecurityPolicyMiddleware` | `SECURE_CSP_REPORT_ONLY` |

*The headers the security middleware add, and the settings they come from.*

None of them overwrites a header the response already has, so a view that sets one keeps its own. A view can also change what the middleware do for it alone: `xframe_options_exempt` marks its response to be left without X-Frame-Options, and `csp_override` gives its response a policy of its own, which the middleware then uses in place of `SECURE_CSP` (`django/views/decorators/clickjacking.py:xframe_options_exempt`, `django/views/decorators/csp.py:csp_override`).

The policy's nonce is the one moving part. `ContentSecurityPolicyMiddleware.process_request` gives the request a `LazyNonce`, which makes its random value only when something first reads it, and the `csp` context processor puts it in the context of each template rendered with the request. On the way out, `build_policy` writes the policy from the setting's dictionary, and replaces the placeholder `CSP.NONCE` with the nonce if the nonce was made, or drops it if not ([Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](security/csp.md)) (`django/utils/csp.py:build_policy`).

## Keys and signatures

Every key with which Django tells its own values from forged ones is ordinarily made from `SECRET_KEY`. The base of them is `salted_hmac`, which makes an HMAC of a value with a key made by hashing a salt, which names the use, together with the secret key; so each use has a key of its own, and a value made for one use does not verify for another ([Secret keys and `django.utils.crypto`](security/keys.md)) (`django/utils/crypto.py:salted_hmac`).

`Signer` uses it to sign a string: the value, a separator, and the HMAC of the value. `TimestampSigner` puts the time of signing between the two, so that a reader can refuse a value older than it wants. `dumps` signs any value that JSON can hold, by way of a `TimestampSigner` with the salt `"django.core.signing"` unless it is given another, and `loads` checks it and gives the value back ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](security/signing.md)) (`django/core/signing.py:dumps`):

```python
>>> from django.core import signing
>>> s = signing.dumps({"berth": 4, "ship": "Endeavour"}, salt="harbour.berths")
>>> s
'eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xHPtn:0FeZlbBD_zc3yj0U94CdSZvBzG5MHoHtkxretch2utk'
>>> signing.loads(s, salt="harbour.berths")
{'berth': 4, 'ship': 'Endeavour'}
>>> signing.loads(s, salt="harbour.invoices")
Traceback (most recent call last):
  ...
django.core.signing.BadSignature: Signature "0FeZlbBD_zc3yj0U94CdSZvBzG5MHoHtkxretch2utk" does not match
```

The first part is the JSON in URL-safe base64, which anyone can decode: signing makes a change detectable and hides nothing. The value read under another salt was refused, as it was after `SECRET_KEY` was changed; with the old key listed in `SECRET_KEY_FALLBACKS`, it was accepted again. A `Signer` tries its key and then each of the fallbacks, which is how a site changes its key without at once losing every value signed with the old one (`django/core/signing.py:Signer.unsign`).

The users of these are mostly elsewhere in Django: signed cookies ([Cookies](http/cookies.md)), the session's stored data and the session backend that keeps everything in a cookie, the messages kept in a cookie, and in `django.contrib.auth` the tokens of a password reset and the hash that ties a session to the user's password ([The session store: `SessionBase`](auth/sessions.md), [Password reset: `PasswordResetTokenGenerator` and the reset views](auth/password-reset.md), [The user of a request: `login`, `logout` and `AuthenticationMiddleware`](auth/login.md)).

## Checks before deployment

Most of what this chapter describes is only as good as the settings, so Django checks them. The security checks are system checks with the tag `"security"`, and most are registered as deployment checks, which run only when the check command is given `--deploy`: that `settings.DEBUG` is off, that `SECRET_KEY` is long and not one startproject wrote, that `SecurityMiddleware`, `CsrfViewMiddleware` and `XFrameOptionsMiddleware` are installed and the cookies marked secure ([The security checks](security/checks.md)) ([The system checks](commands/checks.md)) (`django/core/checks/security/base.py:check_secret_key`). Three run on every check: that the two policy settings are dictionaries, that a policy with a nonce has the `csp` context processor to put the nonce in templates, and that the view `CSRF_FAILURE_VIEW` names takes a request and a reason (`django/core/checks/security/csrf.py:check_csrf_failure_view`).

## Where security meets the rest of Django

The middleware are layers of the chain in [Handlers and middleware](handlers.md). Two of the checks they rely on are the request's: `HttpRequest.get_host`, which ordinarily refuses a host not in `ALLOWED_HOSTS`, and `HttpRequest.is_secure`, which a proxy's header can decide ([Headers, host and scheme](http/headers.md)); and checking a URL before redirecting to it is in [The helpers in `django/utils/http.py`](http/helpers.md). Signed cookies and the order of the salt are in [Cookies](http/cookies.md). The CSRF decorators, made from the middleware, are in [A middleware as a decorator](views/middleware-decorators.md), and `csrf_exempt` in [View decorators](views/decorators.md). The two context processors that put the token and the nonce in a template's context are in [The context: `Context`, `RequestContext` and context processors](templates/context.md), the tags that write them in [The built-in tags](templates/tags.md), and the escaping that keeps a value from becoming markup in [Autoescaping and safe strings](templates/autoescape.md). Passwords, their hashers, the login that rotates the CSRF secret and the session are in [Authentication, sessions and messages](auth.md). The test client turns the CSRF check off unless it is made with `enforce_csrf_checks=True` ([The test client: `Client` and `ClientHandler`](testing/client.md)).
