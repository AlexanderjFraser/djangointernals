---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in security: Content Security Policy and signing

The changes from Django 5.0 to this commit in Content Security Policy and signing: the settings `SECURE_CSP` and `SECURE_CSP_REPORT_ONLY`, `ContentSecurityPolicyMiddleware`, the tag `{% csp_nonce_attr %}` and the check `"security.W027"`; a signed cookie's salt and the setting `SIGNED_COOKIE_LEGACY_SALT_FALLBACK`; the default algorithm of `salted_hmac` and `base64_hmac`; `Signer`'s positional arguments and the setting CSRF_COOKIE_MASKED.

Two things moved. Django took on a defence it had not offered: since 6.0 a project names a Content Security Policy in its settings and a middleware writes the header, and 6.1 made the admin's pages carry its nonce. And signing became stricter in steps that leave the old form usable for a time. The new cookie salt of 5.2.15 and 6.0.6 still read cookies signed with the old one, until 6.1 turned that off by default; a call to `salted_hmac` that names no algorithm, and so gets SHA-1, warns since 6.1. Both allowances end in Django 2028 ([What still warns: the deprecations and the releases that end them](deprecations.md)).

## Content Security Policy (6.0)

A Content Security Policy tells the browser which scripts, styles and images a page may load; the 6.0 notes give it as a defence against content injection such as cross-site scripting (`docs/releases/6.0.txt`). The policy is two settings, `SECURE_CSP`, which the browser enforces, and `SECURE_CSP_REPORT_ONLY`, whose breaches it only reports. Each maps a directive to its sources and is empty by default, which writes no header (`django/conf/global_settings.py`). The enumeration `CSP` names the two headers, the specification's quoted keywords such as `CSP.SELF`, and one placeholder of Django's own, `CSP.NONCE`, which stands in a policy for the request's nonce (`django/utils/csp.py:CSP`).

`ContentSecurityPolicyMiddleware` gives each request a `LazyNonce`, made only when first read, on the way in, and on the way out writes each header whose policy is not empty and which the response lacks (`django/middleware/csp.py:ContentSecurityPolicyMiddleware`). The context processor `django.template.context_processors.csp` gives a template the nonce as `"csp_nonce"` (`django/template/context_processors.py:csp`). The function `build_policy` puts the nonce in place of the placeholder if something read it, and otherwise drops the placeholder (`django/utils/csp.py:build_policy`). The decorators `csp_override` and `csp_report_only_override` give one view a policy that replaces the setting's entirely; an empty one leaves that header off (`django/views/decorators/csp.py:_make_csp_decorator`). A new project has no policy: the settings startproject writes name neither the middleware nor the processor (`django/conf/project_template/project_name/settings.py-tpl`). [Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](../security/csp.md) tells the mechanism.

## What 6.1 added: the tag, Django's own templates and W027

Without an argument, `{% csp_nonce_attr %}` writes `nonce="…"` from the context's `"csp_nonce"`, or nothing when the context has none; given a form's media, it writes the media's tags, with the nonce if any (`django/utils/csp.py:nonce_attr`; [The built-in tags](../templates/tags.md)). Since 6.1 the admin's templates, admindocs' and the CSRF failure page carry it on their `<script>`, `<style>` and `<link>` elements (`docs/releases/6.1.txt`). The notes make this depend on the `csp` processor. Django's own failure page does not: when the project has no `"403_csrf.html"`, the view `csrf_failure` renders the built-in `"csrf_403.html"` with an `Engine` of its own, and adds the nonce itself (`django/views/csrf.py:csrf_failure`). Here Django's own failure page, with no template engine configured, is answered under a policy that names the nonce for styles; look at its `<style>`, whose nonce is new for every request and written as an ellipsis:

```text recording=changes
csrf_failure(request) through ContentSecurityPolicyMiddleware, SECURE_CSP with CSP.NONCE: the page's <style>
    5.2.17       ModuleNotFoundError: No module named 'django.middleware.csp'
    6.0.8        <style>
    6.1.1        <style nonce="…">
    this commit  <style nonce="…">
```

Under 6.0.8 the page's inline style had no nonce, so a browser would refuse it (`docs/ref/csp.txt`). A project's own `"403_csrf.html"` is rendered with the request alone, so its context holds the nonce only through its engine's context processors.

`"security.W027"` warns when `ContentSecurityPolicyMiddleware` is in `MIDDLEWARE`, a policy holds `CSP.NONCE`, and no engine in `TEMPLATES` lists the `csp` processor, which gives a template the nonce. It is registered without `deploy=True`, so check reports it without --deploy (`django/core/checks/security/base.py:check_csp_nonce_context_processor`; [The security checks](../security/checks.md)). Here such settings are checked; 6.0.8 passes them:

```text recording=changes
MIDDLEWARE = [ContentSecurityPolicyMiddleware], SECURE_CSP with CSP.NONCE, no "csp" processor in TEMPLATES: the messages of check --tag security, without --deploy
    5.2.17       ModuleNotFoundError: No module named 'django.utils.csp'
    6.0.8        no message
    6.1.1        security.W027
    this commit  security.W027
```

## The salt of a signed cookie (5.2.15, 6.0.6, 6.1)

A signed cookie is signed with a salt that names the cookie, so that a value signed for one cookie is refused under another ([Cookies](../http/cookies.md#signed-cookies)). Until 5.2.15 and 6.0.6 that salt was the cookie's name followed by the caller's salt, so the cookie "draft" with the salt "s" and the cookie "drafts" with none made the same one, and a value signed for either was accepted for the other (CVE-2026-6873, `docs/releases/5.2.15.txt`; [Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md)). `HttpResponseBase.set_signed_cookie` has since signed with a salt of a fixed prefix, the length of the caller's salt, that salt and the name, so that no two pairs make one string (`django/core/signing.py:_cookie_signer_salt`).

For the cookies signed before, the function `_unsign_cookie` tries the old salt when the new one fails for any reason but age, if `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` is true (`django/core/signing.py:_unsign_cookie`). The setting was true by default in 5.2.15 and 6.0.6, and is false since 6.1. The 6.1 notes list "Signed cookies now use an unambiguous salt derivation by default" among its features (`docs/releases/6.1.txt`), but 5.2.17 and 6.0.8 already sign with the new salt: what 6.1 changed is what is read. Here a value that `set_signed_cookie("drafts", "4")` wrote before the fix is read, at the defaults, as the cookie "draft" with the salt "s"; `'4'` is that old cookie still read, the collision left open, and `None` its refusal:

```text recording=changes
request.get_signed_cookie("draft", default=None, salt="s"): the value set_signed_cookie("drafts", "4") wrote before 5.2.15 and 6.0.6
    5.2.17       '4'
    6.0.8        '4'
    6.1.1        None
    this commit  None
```

Since 6.1, at the default, a project's own cookies signed before the fix are refused too, under every name and salt: what `set_signed_cookie("draft", "4", salt="s")` wrote then was signed with the same old salt, "drafts" (`django/core/signing.py:_cookie_signer_legacy_salt`). With the fallback set true, all four releases read the old value as "4". A cookie signed now is safe from the collision, fallback or not: no release accepts as "draft" with "s" a value that `set_signed_cookie("drafts", "4")` writes now. 6.1.1 and this commit warn when a project sets the fallback, to either value (`django/conf/__init__.py:Settings.__init__`).

> **Trap.** Nothing warns when an old cookie is refused: from 6.1, at the default, `HttpRequest.get_signed_cookie` raises `BadSignature` for it, or returns the default it was given, as for a forged one (`django/http/request.py:HttpRequest.get_signed_cookie`).

## The algorithm of `salted_hmac` and `base64_hmac` (6.1)

6.1 deprecated SHA-1 as the default algorithm of `salted_hmac`, the keyed hash under Django's signing ([What changed](../changes.md#an-old-habit-release-by-release)), and of `base64_hmac`, with which `Signer` signs: under 5.2.17 and 6.0.8 `base64_hmac("journal", "entry", "journal-key")` returns its digest without a word, and 6.1.1 and this commit return the same digest and warn (`django/core/signing.py:base64_hmac`). Django's own callers name the algorithm, `Signer` the one it was made with, SHA-256 by default, so signing never meets the warning (`django/core/signing.py:Signer.signature`; [Secret keys and `django.utils.crypto`](../security/keys.md), [Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](../security/signing.md)).

## What was removed

`Signer` takes keyword arguments only: positional ones, deprecated in 4.2, were removed in 5.1 (`docs/releases/5.1.txt`), and `TimestampSigner` inherits the same `__init__` (`django/core/signing.py:Signer.__init__`). Under 5.2.17 and every later release `Signer("journal-key")` raises `TypeError`, "Signer.__init__() takes 1 positional argument but 2 were given".

The transitional setting CSRF_COOKIE_MASKED went in 5.0. It came in 4.1, when `CsrfViewMiddleware` stopped masking the secret in its cookie, to keep it masked while a project's instances were upgraded (`docs/releases/4.1.txt`). Nothing at this commit reads it: under 5.2.17 and every later release a project that sets it true gets, without a warning, a cookie of 32 characters, the secret itself (`django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`). A cookie of 64, a masked secret, is still accepted, and unmasked as it is read (`django/middleware/csrf.py:CsrfViewMiddleware._get_secret`; [The CSRF secret and its token](../security/csrf-token.md)).
