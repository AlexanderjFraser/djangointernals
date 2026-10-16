---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in security: Content Security Policy and signing

Since 6.0 Django writes a Content Security Policy itself, from the settings `SECURE_CSP` and `SECURE_CSP_REPORT_ONLY`, with `ContentSecurityPolicyMiddleware` and a nonce for each request, and 6.1 added `{% csp_nonce_attr %}` and the check `"security.W027"`. In signing, a signed cookie's salt is made a new way since 5.2.15 and 6.0.6, `salted_hmac` and `base64_hmac` warn when given no algorithm (6.1), and `Signer` takes keyword arguments only (5.1); the CSRF cookie's setting CSRF_COOKIE_MASKED is gone (5.0).

## Content Security Policy (6.0)

Until 6.0 Django wrote no Content-Security-Policy header of its own. The release notes give the reason for adding one: a policy tells the browser which scripts, styles and images a page may load, a defence against content injection such as cross-site scripting (`docs/releases/6.0.txt`).

The policy is two settings: `SECURE_CSP`, which the browser enforces, and `SECURE_CSP_REPORT_ONLY`, whose breaches it only reports. Each is a dictionary from a directive to its sources, and each is empty by default, which writes no header (`django/conf/global_settings.py`). `CSP`, in `django.utils.csp`, is a string enumeration of the two headers' names, of some of the specification's quoted keywords, such as `CSP.SELF`, and of one placeholder of Django's own, `CSP.NONCE`, which stands in a directive for the request's nonce (`django/utils/csp.py:CSP`).

`ContentSecurityPolicyMiddleware` gives each request a `LazyNonce` on the way in, and on the way out writes, with `build_policy`, each header whose policy is not empty and which the response lacks. `build_policy` puts the nonce in place of the placeholder only if something in the request read it, and otherwise drops it (`django/middleware/csp.py:ContentSecurityPolicyMiddleware`, `django/utils/csp.py:build_policy`). The context processor `django.template.context_processors.csp` puts the nonce in a template's context as `"csp_nonce"` (`django/template/context_processors.py:csp`). `csp_override` and `csp_report_only_override` give one view's response a policy that replaces the setting's whole, and an empty dictionary leaves that header off (`django/views/decorators/csp.py:_make_csp_decorator`). A project has no policy until it asks for one: the settings module startproject writes lists neither the middleware nor the processor (`django/conf/project_template/project_name/settings.py-tpl`). [Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](../security/csp.md) tells the mechanism.

## What 6.1 added to it

`{% csp_nonce_attr %}` writes `nonce="…"` from the context's `"csp_nonce"`, and given a `Media` renders it with that attribute on each `MediaAsset` in it; with no nonce in the context it writes none (`django/utils/csp.py:nonce_attr`) ([The built-in tags](../templates/tags.md)). The tag reads the nonce and so makes it, though `LazyNonce`'s docstring says otherwise.

Django's own templates write it too since 6.1: the `<script>`, `<style>` and `<link>` elements of the admin's templates, the documentation generator's and the CSRF failure page carry the tag, and `csrf_failure`, which renders that page with an engine of its own, adds the processor's dictionary to its context (`django/views/csrf.py:csrf_failure`).

`"security.W027"` warns when `ContentSecurityPolicyMiddleware` is in `MIDDLEWARE`, either policy holds `CSP.NONCE`, and no engine in `TEMPLATES` lists the `csp` processor. It is not a deployment check, so it runs on every check (`django/core/checks/security/base.py:check_csp_nonce_context_processor`) ([The security checks](../security/checks.md)).

## The salt of a signed cookie (5.2.15, 6.0.6, 6.1)

A signed cookie is signed with a salt that names the cookie, so that a value signed for one cookie is refused under another. `HttpResponseBase.set_signed_cookie` signs with the signer of `get_cookie_signer`, given a salt that `_cookie_signer_salt` makes from the cookie's name and the caller's salt (`django/http/response.py:HttpResponseBase.set_signed_cookie`). Until 5.2.15 and 6.0.6 that salt was the name followed by the caller's salt, so that two pairs could make one string and a cookie be accepted where it had not been signed (`docs/releases/6.0.6.txt`). At this commit the salt is `"django.http.cookies.v2:"`, the length of the caller's salt, a colon, that salt and the name; the comment says the length is there so that the pairs cannot collide (`django/core/signing.py:_cookie_signer_salt`). The fix was CVE-2026-6873 ([Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md)).

`HttpRequest.get_signed_cookie` reads through `_unsign_cookie`, which checks the signature under the new salt (`django/core/signing.py:_unsign_cookie`). Only if that fails for a reason other than age, and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` is true, does it check again under the old salt, which `_cookie_signer_legacy_salt` still makes. The fallback only reads: every cookie `set_signed_cookie` signs is signed under the new salt. In 5.2.15 and 6.0.6 it was on by default, so that cookies signed before the fix stayed good (`docs/ref/settings.txt`); since 6.1 its default is false, and the setting is deprecated, to go with the old salt in Django 2028, and warns when a project sets it ([What changed in settings, startup and the commands](startup-and-commands.md)).

```text
# salts.py at this commit: the cookie "berth" with the salt "s", and the cookie "berths" with none;
# each value below was signed for ("berth", "s")
salt of ("berth", "s")    'django.http.cookies.v2:1:sberth'
salt of ("berths", "")    'django.http.cookies.v2:0:berths'
old salt of either        'berths'

get_signed_cookie of a value signed            fallback false   fallback true
under the old salt, read as ("berth", "s")     BadSignature     '4'
under the old salt, read as ("berths", "")     BadSignature     '4'
at this commit, read as ("berth", "s")         '4'              '4'
at this commit, read as ("berths", "")         BadSignature     BadSignature
```

With the fallback on, a value signed under the old salt is good under every pair that makes that salt: the fallback reopens the collision for old cookies, which is why the patch releases' notes told affected projects to turn it off ([Cookies](../http/cookies.md)). The messages' `CookieStorage` passes a salt of its own to `get_cookie_signer` directly, and the fallback has no part in it (`django/contrib/messages/storage/cookie.py:CookieStorage.__init__`).

## The algorithm of `salted_hmac` and `base64_hmac` (6.1)

`salted_hmac` and `base64_hmac` given no algorithm use SHA-1, as before, and since 6.1 warn with `RemovedInDjango2028Warning`; in Django 2028 the default becomes SHA-256 (`django/utils/crypto.py:salted_hmac`, `django/core/signing.py:base64_hmac`). Django's own callers pass an algorithm, so a `Signer`, the password-reset tokens and the session's hash of the password never meet the warning ([Secret keys and `django.utils.crypto`](../security/keys.md), [Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](../security/signing.md)).

## What was removed

`Signer.__init__` takes keyword arguments only: positional ones, deprecated in 4.2, were removed in 5.1, and `TimestampSigner` has the same `__init__` (`django/core/signing.py:Signer.__init__`). In a run, `Signer("harbour-key")` raised `TypeError`, "Signer.__init__() takes 1 positional argument but 2 were given".

The transitional setting CSRF_COOKIE_MASKED went in 5.0. It came in 4.1, when `CsrfViewMiddleware` stopped masking the secret in its cookie, to keep the cookie masked while a project's instances were upgraded (`docs/releases/4.1.txt`). Nothing at this commit reads it. The cookie holds the secret itself, 32 characters (`django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`), and a cookie of 64, a masked secret, is still accepted and unmasked as it is read (`django/middleware/csrf.py:CsrfViewMiddleware._get_secret`) ([The CSRF secret and its token](../security/csrf-token.md)).
