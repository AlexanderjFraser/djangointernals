---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Content Security Policy and the nonce

A content security policy is a header that tells the browser where a page may load scripts, styles and the rest from, as a defence against script injected into the page. Where a project sets a policy, `ContentSecurityPolicyMiddleware` writes Content-Security-Policy, which the browser enforces, from `SECURE_CSP`, and Content-Security-Policy-Report-Only, whose breaches it only reports, from `SECURE_CSP_REPORT_ONLY`. The **nonce**, a random value new for each request and named in the policy, lets the page's own inline scripts and styles run; it is a `LazyNonce`, made only when something reads it, as `{% csp_nonce_attr %}` does.

A policy that allows scripts only from the site itself also refuses every inline `<script>`, the site's own included. The nonce is how a page names the inline elements it means: the policy lists it as `'nonce-…'`, and the browser runs an inline script or style only if its `"nonce"` attribute matches (`docs/ref/csp.txt`). Django writes each header from a dictionary, gives a template the nonce through a context processor, and names it in the header only if something has read it.

> **New in 6.0.** Django had no content security policy before 6.0, which brought the middleware, the two settings, the `csp` context processor and the decorators (`docs/releases/6.0.txt`). `{% csp_nonce_attr %}` and the nonce on the elements of Django's own templates came in 6.1 (`docs/releases/6.1.txt`). [What changed in security: Content Security Policy and signing](../changes/security.md) tells both.

## The settings and the `CSP` constants

`SECURE_CSP` and `SECURE_CSP_REPORT_ONLY` are each a dictionary from a directive (`"script-src"`) to the sources it allows, and each defaults to an empty dictionary, which adds no header (`django/conf/global_settings.py`). A value that is neither `None` nor a dictionary is refused by `"security.E026"`, with or without `--deploy` ([The security checks](checks.md)) (`django/core/checks/security/base.py:check_csp_settings`).

A source is a string as the header spells it, and the specification's keywords carry single quotes: `'self'`, `'none'`. `CSP` is a string enumeration of the common ones, `CSP.SELF` being `"'self'"`, for type checking, autocompletion and protection against a typo, missing quotes or quotes of the wrong kind. Each member equals its value, so a raw string works as well. Two members are the header names, `CSP.HEADER_ENFORCE` and `CSP.HEADER_REPORT_ONLY`. And `CSP.NONCE`, `"<CSP_NONCE_SENTINEL>"`, is Django's own: a placeholder that stands in a directive's list for the nonce until the header is written (`django/utils/csp.py:CSP`).

## Writing the header: `build_policy`

`build_policy` turns one dictionary and a nonce into the text of one header: each directive followed by its sources, the directives in the dictionary's order joined with `"; "` (`django/utils/csp.py:build_policy`). A directive's value is read thus:

- `None` or `False`: the directive is left out.
- `True`: the directive is written alone, for one that takes no sources (`"upgrade-insecure-requests"`).
- a list or a tuple: its items, in order.
- a set: its items sorted, so that the header is the same from one request to the next.
- a string: a single source.

Then the placeholder. Where a directive's list holds `CSP.NONCE` and the nonce is true, the placeholder becomes `'nonce-…'` with the value in it; where it is false or not given, the placeholder is removed. A directive left with no sources is left out altogether. In the first call below, made before the nonce is read, `"style-src"`, which holds only the placeholder, is dropped and `"script-src"` keeps `'self'` alone; in the second both name the nonce; the last, given no nonce, writes what the first did; and the set given for `"img-src"` comes out sorted each time.

```text recording=security
build_policy over a fuller policy than the harbour's, before and after the nonce is read
    config = {"default-src": [CSP.SELF], "img-src": {CSP.SELF, "https://tiles.harbour.example", "data:"}, "script-src": [CSP.SELF, CSP.NONCE], "style-src": [CSP.NONCE], "frame-src": None, "upgrade-insecure-requests": True}
    nonce = LazyNonce()
    bool(nonce)  ->  False
    build_policy(config, nonce)  ->  "default-src 'self'; img-src 'self' data: https://tiles.harbour.example; script-src 'self'; upgrade-insecure-requests"
    str(nonce)  ->  'tTsW5NGJ55id-GPawe_arw'
    bool(nonce)  ->  True
    build_policy(config, nonce)  ->  "default-src 'self'; img-src 'self' data: https://tiles.harbour.example; script-src 'self' 'nonce-tTsW5NGJ55id-GPawe_arw'; style-src 'nonce-tTsW5NGJ55id-GPawe_arw'; upgrade-insecure-requests"
    build_policy(config)  ->  "default-src 'self'; img-src 'self' data: https://tiles.harbour.example; script-src 'self'; upgrade-insecure-requests"
```

## The nonce: `LazyNonce`

The nonce must be new for every response, and many never use it: a redirect, a page that never writes it. `LazyNonce` is a `SimpleLazyObject` around `generate_nonce`, which returns `secrets.token_urlsafe(16)`, sixteen random bytes as 22 characters of URL-safe base64 (`django/utils/csp.py:generate_nonce`). Nothing is drawn until something reads the value, as a template does when it writes it; the first reading makes it, and every later one in the request gets the same ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)).

What the subclass changes is truth. A `SimpleLazyObject` asked whether it is true makes its object to find out. `LazyNonce.__bool__` answers instead whether the value has been made, and makes nothing (`django/utils/csp.py:LazyNonce`). That is the test `build_policy` applies, so the header names a nonce only if something in the request read it.

## The nonce in templates

The `csp` context processor adds `"csp_nonce"` to the context, the request's nonce or `None` (`django/template/context_processors.py:csp`) ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)). `{% csp_nonce_attr %}` writes `nonce="…"` from it, or nothing; given a form's `Media`, the stylesheets and scripts the form requires, it writes their elements, the nonce, when there is one, on all but those given as ready HTML (`django/utils/csp.py:nonce_attr`) ([The built-in tags](../templates/tags.md), [Form assets: `Media`](../forms/media.md)). The tag asks only whether the context holds a nonce, not whether it has been made, so it draws the nonce itself as it writes it.

Django's own templates carry the tag on their `<script>`, `<style>` and `<link>` elements, all but the debug pages (`django/contrib/admin/templates/`, `django/views/templates/csrf_403.html`). The built-in CSRF failure page, which `csrf_failure` renders with an `Engine` of its own, is given the nonce by the view itself ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)) (`django/views/csrf.py:csrf_failure`).

Without the processor a template's context holds the nonce only where other code puts it, and unless other code reads it the header names none; `"security.W027"` warns of that only where no template engine lists it ([The security checks](checks.md)) (`django/core/checks/security/base.py:check_csp_nonce_context_processor`).

## `ContentSecurityPolicyMiddleware`

`ContentSecurityPolicyMiddleware.process_request` puts a new `LazyNonce` on the request as `"_csp_nonce"`, which costs nothing while no value is drawn (`django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_request`). `get_nonce` reads it back, or gives `None` for a request the middleware has not seen (`django/middleware/csp.py:get_nonce`).

`ContentSecurityPolicyMiddleware.process_response` writes the two headers, each from its setting, or from a policy that a decorator such as `csp_override` has put on the response. A response that already has the header, whatever the case of its name, keeps it, so that a view may set its own, and an empty policy adds none. Otherwise the header is `build_policy` of the policy and the request's nonce, the same nonce for both headers (`django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_response`).

`process_response` runs on the way out, after the view, so by then the nonce has been drawn or not, and that decides what `build_policy` makes of the placeholder. The figure follows the nonce through two of the harbour's requests: the `"GET"` of its form's page, whose template writes `{% csp_nonce_attr %}`, and the `"POST"` of the form, which the view *berths* answers with no template. Each nonce goes onto its request undrawn, and the two part at the view.

```text figure=the-nonce
                 GET https://harbour.example/berths/                   POST https://harbour.example/berths/, accepted

the way in                       ContentSecurityPolicyMiddleware.process_request:
                                 request._csp_nonce is a LazyNonce, not drawn

the view         berths renders the form's template                     berths answers the post, with no template
                 {% csp_nonce_attr %} draws the nonce                   nothing reads the nonce
                 generate_nonce()  ->  'WgGtjgT-tnPCZAmsOjekWQ'

the way out                      ContentSecurityPolicyMiddleware.process_response:
                                 build_policy(SECURE_CSP, the LazyNonce)
                 drawn: CSP.NONCE becomes the nonce                     not drawn: CSP.NONCE is removed
                 Content-Security-Policy:                               Content-Security-Policy:
                   default-src 'self';                                    default-src 'self';
                   script-src 'self' 'nonce-WgGtjgT-tnPCZAmsOjekWQ'       script-src 'self'
```

*The nonce of two requests through the harbour's chain, the form's page on the left and the post of the form on the right, read downwards from the way in to the way out. A step set across both columns is one the two requests take alike; under each request is what happened to it alone.*

## A policy for one view: `csp_override`

`csp_override` and `csp_report_only_override` give one view's response a policy that replaces the setting whole, rather than merging with it. The wrapper each makes puts the policy on the response the view returns, as `"_csp_config"` or `"_csp_ro_config"`, where `process_response` takes it in the setting's place. A policy that is not a dictionary is refused with `TypeError` when the decorator is made, before there is a view to wrap (`django/views/decorators/csp.py:_make_csp_decorator`) ([View decorators](../views/decorators.md)).

The harbour's view *chart* carries `csp_override` with a policy of its own, *notice* carries `csp_override({})`, and *tides* sets the header itself. The setting's `"script-src"` is missing from *chart*'s header, since its policy replaces the setting whole; *notice*'s response goes out with no policy; and *tides*' header is the view's own, which `process_response` leaves as it is.

```text recording=security
GET https://harbour.example/chart/, /notice/ and /tides/: csp_override with a policy, csp_override({}), and a header the view sets itself
    GET https://harbour.example/chart/, the browser sending nothing but the request
    the wrapper csp_override made, around chart, the policy {'default-src': ["'self'"], 'img-src': ["'self'", 'https://tiles.harbour.example']}  ->  an HttpResponse, status 200, its _csp_config {'default-src': ["'self'"], 'img-src': ["'self'", 'https://tiles.harbour.example']}
    ContentSecurityPolicyMiddleware.process_response(request, response)
      build_policy(the policy {'default-src': ["'self'"], 'img-src': ["'self'", 'https://tiles.harbour.example']}, a LazyNonce, not drawn)  ->  "default-src 'self'; img-src 'self' https://tiles.harbour.example"
      -> the response, Content-Security-Policy added
    start_response("200 OK", headers)
      Content-Security-Policy: default-src 'self'; img-src 'self' https://tiles.harbour.example
    GET https://harbour.example/notice/, the browser sending nothing but the request
    the wrapper csp_override made, around notice, the policy {}  ->  an HttpResponse, status 200, its _csp_config {}
    ContentSecurityPolicyMiddleware.process_response(request, response)  ->  the response, unchanged
    start_response("200 OK", headers)
      no Content-Security-Policy
    GET https://harbour.example/tides/, the browser sending nothing but the request
    tides(request)  ->  an HttpResponse, status 200, its Content-Security-Policy "default-src 'none'"
    ContentSecurityPolicyMiddleware.process_response(request, response)  ->  the response, unchanged
    start_response("200 OK", headers)
      Content-Security-Policy: default-src 'none'
```

An empty dictionary, then, takes the setting's place like any other policy, and so exempts a view from that decorator's header (`django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_response`). Django's debug pages, whose styles are written into them, carry both decorators with `{}` ([The debug pages and `ExceptionReporter`](../views/debug.md)) (`django/views/debug.py:technical_500_response`, `django/views/debug.py:technical_404_response`, `django/views/debug.py:default_urlconf`).

> **Trap.** The wrapper marks only a response the view returns. A view that raises, `Http404` say, is answered by the handler's exception handling, with a response that carries no mark of the view's: with `settings.DEBUG` off, a view under `csp_override({})` that raises `Http404` is answered with a 404 under the site's policy (`django/core/handlers/exception.py:response_for_exception`).
