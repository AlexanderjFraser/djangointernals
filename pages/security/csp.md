---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce

`ContentSecurityPolicyMiddleware` adds the Content-Security-Policy and Content-Security-Policy-Report-Only headers, written by `build_policy` from the settings `SECURE_CSP` and `SECURE_CSP_REPORT_ONLY`, and gives each request a nonce, a `LazyNonce` whose value is made only when first read. `csp_override` and `csp_report_only_override` give one view a policy of its own.

A content security policy tells the browser where a page may load scripts, styles, images and frames from, a defence against script injected into the page. A policy that allows scripts only from the site itself also refuses every inline `<script>`, the site's own included, and the **nonce** is how a page names the inline elements it means: the policy lists a random value as `'nonce-…'`, and the browser runs an inline script or style only if its `"nonce"` attribute matches (`docs/ref/csp.txt`). Django writes the header from a dictionary, and makes the value and puts it in both the header and the template's context.

## The settings and the `CSP` constants

`SECURE_CSP` is the enforced policy and `SECURE_CSP_REPORT_ONLY` a policy whose breaches the browser only reports. Each is a dictionary from a directive (`"script-src"`) to the sources it allows, and each defaults to an empty dictionary, which adds no header (`django/conf/global_settings.py`).

A source is a string as the header spells it, and the specification's keywords carry single quotes: `'self'`, `'none'`. `CSP` is a string enumeration of them, `CSP.SELF` being `"'self'"`; its docstring gives the reasons, type checking, autocompletion and protection against a typo, missing quotes or quotes of the wrong kind. Each member equals its value, so a raw string works as well. Two members are the header names, `CSP.HEADER_ENFORCE` and `CSP.HEADER_REPORT_ONLY`. And `CSP.NONCE`, `"<CSP_NONCE_SENTINEL>"`, is Django's own: a placeholder that stands in a directive's list for the nonce until the header is written (`django/utils/csp.py:CSP`).

## Writing the header: `build_policy`

`build_policy` turns one dictionary and a nonce into the text of one header: each directive followed by its sources, the directives in the dictionary's order joined with `"; "` (`django/utils/csp.py:build_policy`). A directive's value is read thus:

- `None` or `False`: the directive is left out.
- `True`: the directive is written alone, for one that takes no sources (`"upgrade-insecure-requests"`).
- a list or a tuple: its items, in order.
- a set: its items sorted, which the comment says keeps the header the same from one request to the next, for caching.
- anything else: a single source.

Then the placeholder. Where a directive's list holds `CSP.NONCE` and the nonce is true, the placeholder becomes `'nonce-…'` with the value in it; where it is false or not given, the placeholder is removed. A directive left with no sources is left out altogether. A run, with a fuller policy than the example's:

```python
>>> from django.utils.csp import CSP, LazyNonce, build_policy
>>> config = {
...     "default-src": [CSP.SELF],
...     "img-src": {CSP.SELF, "https://tiles.harbour.example", "data:"},
...     "script-src": [CSP.SELF, CSP.NONCE],
...     "style-src": [CSP.NONCE],
...     "frame-src": None,
...     "upgrade-insecure-requests": True,
... }
>>> nonce = LazyNonce()
>>> bool(nonce)
False
>>> build_policy(config, nonce)
"default-src 'self'; img-src 'self' data: https://tiles.harbour.example; script-src 'self'; upgrade-insecure-requests"
>>> str(nonce)
'3l1OwaZ5kzB1fOiERN0O4g'
>>> build_policy(config, nonce)
"default-src 'self'; img-src 'self' data: https://tiles.harbour.example; script-src 'self' 'nonce-3l1OwaZ5kzB1fOiERN0O4g'; style-src 'nonce-3l1OwaZ5kzB1fOiERN0O4g'; upgrade-insecure-requests"
```

Before the nonce was read, `"style-src"`, holding only the placeholder, was dropped, and `"script-src"` kept `'self'` alone.

## The nonce: `LazyNonce`

The nonce must be new for every response, and many never use it: a redirect, a page with no inline script. `LazyNonce` is a `SimpleLazyObject` around `generate_nonce`, which returns `secrets.token_urlsafe(16)`, sixteen random bytes as 22 characters of URL-safe base64 (`django/utils/csp.py:generate_nonce`). Nothing is drawn until something reads the value, as a template does when it writes it; the first reading makes it, and every later one in the request gets the same ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)).

What the subclass changes is truth. A `SimpleLazyObject` asked whether it is true makes its object to find out. `LazyNonce.__bool__` answers instead whether the value has been made, and makes nothing (`django/utils/csp.py:LazyNonce`). That is the test `build_policy` applies, so the header names a nonce only if something in the request read it.

> **Trap.** `LazyNonce`'s docstring says `{% csp_nonce_attr %}` renders the attribute only if the nonce has been read elsewhere. The tag's function tests only that the context's value is not `None`, and writes it, so the tag itself makes the nonce: a run rendering the tag over a fresh `LazyNonce` found it false before and true after (`django/utils/csp.py:nonce_attr`).

## `ContentSecurityPolicyMiddleware`

`ContentSecurityPolicyMiddleware.process_request` puts a new `LazyNonce` on the request as `"_csp_nonce"`, which costs nothing while no value is drawn (`django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_request`). `get_nonce` reads it back, or gives `None` for a request the middleware has not seen (`django/middleware/csp.py:get_nonce`).

`ContentSecurityPolicyMiddleware.process_response` writes the two headers. For each it takes the policy a decorator stored on the response, as `"_csp_config"` or `"_csp_ro_config"`, and otherwise the setting; it tests for the attribute against a sentinel of its own, not for a true value, so an empty dictionary stored there is used. An empty policy adds nothing, and nor does one whose header the response already has, whatever the case of its name; the comment gives the reason, that a view may set its own. Otherwise the header is `build_policy` of the policy and the request's nonce, the same nonce for both headers (`django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_response`).

This runs on the way out, after the view has rendered its template, so by then the nonce has been made or not.

## A policy for one view: `csp_override`

`csp_override` and `csp_report_only_override` give one view's response a policy that replaces the setting whole, rather than merging with it. Each calls `_make_csp_decorator` with the attribute it stores the policy in. That function refuses a policy that is not a dictionary at once, before there is a view to wrap, with `TypeError` and the message "CSP config should be a mapping.". It then wraps the view, in a coroutine function if the view is one, and the wrapper sets the attribute on the response the view returns (`django/views/decorators/csp.py:_make_csp_decorator`) ([View decorators](../views/decorators.md)).

```python
# harbour/office/views.py
from django.http import HttpResponse
from django.utils.csp import CSP
from django.views.decorators.csp import csp_override


@csp_override({"default-src": [CSP.SELF], "img-src": [CSP.SELF, "https://tiles.harbour.example"]})
def chart(request):
    return HttpResponse("The harbour chart.")


@csp_override({})
def notice(request):
    return HttpResponse("Notice to mariners.")


def tides(request):
    response = HttpResponse("Tide table.")
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response
```

A run of the example, with the test client making the requests, gave these policies:

```text
GET https://harbour.example/chart/     Content-Security-Policy: default-src 'self'; img-src 'self' https://tiles.harbour.example
GET https://harbour.example/notice/    no Content-Security-Policy
GET https://harbour.example/tides/     Content-Security-Policy: default-src 'none'
```

An empty dictionary exempts a view from that decorator's header. Django's debug pages, whose styles and script are written into them, carry both decorators with `{}` ([The debug pages and `ExceptionReporter`](../views/debug.md)) (`django/views/debug.py:technical_500_response`).

> **Trap.** The wrapper marks only a response the view returns. A view that raises, `Http404` say, is answered by the handler's exception handling, with a response that carries no mark of the view's (`django/core/handlers/exception.py:response_for_exception`): in a run with `settings.DEBUG` off, a view under `csp_override({})` that raised `Http404` was answered with a 404 under the site's policy.

## The nonce in templates

The `csp` context processor adds `"csp_nonce"` to the context, the request's nonce or `None` (`django/template/context_processors.py:csp`) ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)). `{% csp_nonce_attr %}`, new in 6.1, writes `nonce="…"` from it, or nothing; given a form's media, it renders the media, with the nonce on its elements when there is one ([The built-in tags](../templates/tags.md), [Form assets: `Media`](../forms/media.md)). Without the processor a template's context holds the nonce only where a view puts it there, and unless other code reads it the header names none: `"security.W027"` warns of that when the middleware is installed and a policy holds `CSP.NONCE`, and `"security.E026"` refuses a policy setting that is not a dictionary, both on every check ([The security checks](checks.md)) (`django/core/checks/security/base.py:check_csp_nonce_context_processor`, `django/core/checks/security/base.py:check_csp_settings`).

> **Changed in 6.1.** The admin's templates and Django's other built-in templates, the debug pages' aside, carry the nonce on their `<script>`, `<style>` and `<link>` elements when the `csp` processor is configured. `csrf_failure`, which renders its built-in `"csrf_403.html"` with an `Engine` of its own, adds the nonce to that template's context itself ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)).
