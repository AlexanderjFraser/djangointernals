---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in security: Content Security Policy and signing

Since 6.0 Django can write a Content Security Policy header, and since 6.1 the admin's pages can carry its nonce. Signing grew stricter: a signed cookie's new salt, and SHA-1 deprecated as the default of `salted_hmac`.

The Content Security Policy is a defence Django did not offer before 6.0. The changes to signing come in steps that leave the old form usable for a time. 5.2.15 and 6.0.6 gave a signed cookie a new salt. They still read a cookie signed with the old one, and 6.1 turned that off by default. A call to `salted_hmac` that names no algorithm gets SHA-1, and warns since 6.1. Both allowances end in Django 2028 ([What still warns: the deprecations and the releases that end them](deprecations.md)).

## Content Security Policy (6.0)

Since 6.0 Django can send a Content Security Policy, which tells the browser which scripts, styles and images a page may load. The 6.0 notes give it as a defence against content injection, such as cross-site scripting (`docs/releases/6.0.txt`). The policy is two settings: `SECURE_CSP`, which the browser enforces, and `SECURE_CSP_REPORT_ONLY`, whose breaches it only reports. Each maps a directive to its sources. The **nonce** is a value new for every request, which a policy that names it requires of an inline script or style (`docs/ref/csp.txt`). The enumeration `CSP` holds the two headers' names, quoted keywords such as `CSP.SELF`, and one placeholder of Django's own, `CSP.NONCE`, which stands in a policy for the request's nonce (`django/utils/csp.py:CSP`).

`ContentSecurityPolicyMiddleware` gives each request a nonce on the way in, made only when first read. On the way out it writes each header whose policy is not empty and which the response lacks (`django/middleware/csp.py:ContentSecurityPolicyMiddleware`; [Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](../security/csp.md)). The context processor `django.template.context_processors.csp` gives a template the nonce as `"csp_nonce"` (`django/template/context_processors.py:csp`). The decorators `csp_override` and `csp_report_only_override` give one view a policy of its own (`django/views/decorators/csp.py:_make_csp_decorator`). A project has none of this until it asks. Both settings are empty by default (`django/conf/global_settings.py`), and the settings startproject writes name neither the middleware nor the processor (`django/conf/project_template/project_name/settings.py-tpl`).

## What 6.1 added: the tag, Django's own templates and W027

6.1 brought the tag `{% csp_nonce_attr %}`, put it in many of Django's own templates, and added a check for a nonce no template is given. Without an argument, the tag writes `nonce="…"` from the context's `"csp_nonce"`, or nothing when the context has none. Given a form's media, it writes the media's tags, with the nonce if there is one (`django/utils/csp.py:nonce_attr`; [The built-in tags](../templates/tags.md)).

The admin's templates, admindocs' and the CSRF failure page carry the tag on their `<script>`, `<style>` and `<link>` elements (`docs/releases/6.1.txt`). The notes make this depend on the `csp` processor, but Django's own failure page does not. When the project has no `"403_csrf.html"`, the view `csrf_failure` renders the built-in `"csrf_403.html"` with an `Engine` of its own, and adds the nonce itself (`django/views/csrf.py:csrf_failure`).

Django's own failure page shows the change in its `<style>`, under a policy that names the nonce for styles and with no template engine configured. Under 6.0.8 the element has no nonce, so a browser would refuse it (`docs/ref/csp.txt`). Since 6.1 it carries the nonce, written as an ellipsis:

```text recording=changes
csrf_failure(request) through ContentSecurityPolicyMiddleware, SECURE_CSP with CSP.NONCE: the page's <style>
    5.2.17       ModuleNotFoundError: No module named 'django.middleware.csp'
    6.0.8        <style>
    6.1.1        <style nonce="…">
    this commit  <style nonce="…">
```

A project's own `"403_csrf.html"` is rendered with the request alone, so its context holds the nonce only through its engine's context processors.

The check `"security.W027"` warns when `ContentSecurityPolicyMiddleware` is in `MIDDLEWARE` and a policy holds `CSP.NONCE`, but no engine in `TEMPLATES` lists the `csp` processor. It is registered without `deploy=True`, so check reports it without --deploy (`django/core/checks/security/base.py:check_csp_nonce_context_processor`; [The security checks](../security/checks.md)). On such settings, check --tag security says nothing under 6.0.8 and names W027 since 6.1:

```text recording=changes
MIDDLEWARE = [ContentSecurityPolicyMiddleware], SECURE_CSP with CSP.NONCE, no "csp" processor in TEMPLATES: the messages of check --tag security, without --deploy
    5.2.17       ModuleNotFoundError: No module named 'django.utils.csp'
    6.0.8        no message
    6.1.1        security.W027
    this commit  security.W027
```

## The salt of a signed cookie (5.2.15, 6.0.6, 6.1)

Since 5.2.15 and 6.0.6 a signed cookie is signed with a new salt. Since 6.1 a cookie signed with the old one is refused by default. A signed cookie's salt names the cookie, so that a value signed for one cookie is refused under another ([Cookies](../http/cookies.md#signed-cookies)). Until 5.2.15 and 6.0.6 that salt was the cookie's name followed by the caller's salt. So the cookie "draft" with the salt "s" and the cookie "drafts" with none made the same salt, and a value signed for either was accepted for the other (CVE-2026-6873, `docs/releases/5.2.15.txt`; [Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md)). `HttpResponseBase.set_signed_cookie` now signs with a salt of a fixed prefix, the length of the caller's salt, that salt and the name, so that no two pairs of name and salt make one string (`django/core/signing.py:_cookie_signer_salt`).

The transitional setting `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` lets a project go on reading the cookies signed before the fix. When it is true and the new salt fails for any reason but age, the function `_unsign_cookie` tries the old one (`django/core/signing.py:_unsign_cookie`). The setting was true by default in 5.2.15 and 6.0.6, and is false since 6.1. The 6.1 notes list among its features that signed cookies use the new salt by default (`docs/releases/6.1.txt`), but 5.2.17 and 6.0.8 already sign with it: what 6.1 changed is what is read.

The collision shows in a value that `set_signed_cookie("drafts", "4")` wrote before the fix, read at the defaults as the cookie "draft" with the salt "s". `'4'` is that old cookie still read, the collision left open, and `None` its refusal:

```text recording=changes
request.get_signed_cookie("draft", default=None, salt="s"): the value set_signed_cookie("drafts", "4") wrote before 5.2.15 and 6.0.6
    5.2.17       '4'
    6.0.8        '4'
    6.1.1        None
    this commit  None
```

The default of 6.1 refuses more than the collision. A project's own cookies signed before the fix are refused too, under every name and salt. What `set_signed_cookie("draft", "4", salt="s")` wrote then was signed with the same old salt, "drafts" (`django/core/signing.py:_cookie_signer_legacy_salt`). With the fallback set true, the old value is read as "4" under all four. Under all four a cookie signed now is safe from the collision, with the fallback set or not. Since 6.1 a project that sets the fallback gets a warning, whatever the value (`django/conf/__init__.py:Settings.__init__`).

> **Trap.** Nothing warns when an old cookie is refused. Since 6.1, at the default, `HttpRequest.get_signed_cookie` treats it as a forged one: it raises `BadSignature`, or returns the default it was given (`django/http/request.py:HttpRequest.get_signed_cookie`).

## The algorithm of `salted_hmac` and `base64_hmac` (6.1)

A call that names no algorithm warns since 6.1, whether to `salted_hmac`, the keyed hash under Django's signing, or to `base64_hmac`, with which `Signer` signs (`django/utils/crypto.py:salted_hmac`, `django/core/signing.py:base64_hmac`). It still gets SHA-1, which 6.1 deprecated as their default ([What changed](../changes.md#an-old-habit-release-by-release)). Django's own callers name the algorithm, so signing never meets the warning: `Signer` names the one it was made with, SHA-256 by default (`django/core/signing.py:Signer.signature`; [Secret keys and `django.utils.crypto`](../security/keys.md), [Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](../security/signing.md)).

## What was removed

`Signer` takes keyword arguments only since 5.1, which removed the positional ones deprecated in 4.2 (`docs/releases/5.1.txt`). `TimestampSigner` inherits `Signer.__init__` (`django/core/signing.py:Signer.__init__`). Under all four `Signer("journal-key")` raises `TypeError`, "Signer.__init__() takes 1 positional argument but 2 were given".

5.0 removed the transitional setting CSRF_COOKIE_MASKED, and nothing at this commit reads it. It came in 4.1, when `CsrfViewMiddleware` stopped masking the secret in its cookie, to keep the cookie masked while a project's instances were upgraded (`docs/releases/4.1.txt`). Under all four a project that still sets it true gets, without a warning, a cookie of 32 characters, the secret itself (`django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`). A cookie of 64 characters, a masked secret, is still accepted, and unmasked as it is read (`django/middleware/csrf.py:CsrfViewMiddleware._get_secret`; [The CSRF secret and its token](../security/csrf-token.md)).
