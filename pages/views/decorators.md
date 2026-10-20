---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# View decorators

The decorators of `django/views/decorators/`, such as `require_http_methods`, `never_cache` and `csrf_exempt`: the wrappers they put around a view, acting before the call or after it, the marks some leave for other code to read, and how `condition` answers a request without calling the view.

A view decorator takes a view and returns what goes into the URLconf in its place. That is all the word means, and the handler knows nothing about it: by the time a request arrives, a decorator written above a function ran long ago, when the module that defines the view was imported, and what is left is a function. Django's decorators differ in what that function does. Some call the view and act before the call or after it. Some change nothing about the call and exist to be noticed by other code. And one group is made mechanically from middleware classes, which [A middleware as a decorator](middleware-decorators.md) takes up; how any of them is put on a method of a class is [Decorating a class: `method_decorator`](method-decorator.md).

## One wrapper, written twice

Each decorator whose wrapper is written in `django/views/decorators/`, all but `sensitive_variables`, defines that wrapper twice, once with `def` and once with `async def`, picks one by asking whether the view is a coroutine function, and passes it through `functools.wraps` (`django/views/decorators/cache.py:never_cache`). The choice is made when the decorator is applied, not at each call of the wrapper, and it keeps a coroutine function a coroutine function, which the handler depends on ([Asynchronous views](async.md#what-a-decorator-has-to-keep)). The decorators made from a middleware class are defined in the directory too, but get their two wrappers from `make_middleware_decorator`, which is written to the same pattern (`django/utils/decorators.py:make_middleware_decorator`).

`functools.wraps` copies the view's name, module and docstring onto the wrapper, copies the view's attributes over the wrapper's own, and leaves the view itself reachable as `__wrapped__`. The copied attributes matter most: they carry every mark an inner decorator set out to the function that the URLconf will hold ([What the handler asks of a view](callable.md#what-other-code-reads-from-a-view)).

A decorator that takes settings is one level deeper: `require_http_methods`, `vary_on_headers`, `cache_control` and `condition` are functions that return a decorator, and are written with parentheses and arguments. The ones Django supplies ready-made, such as `require_GET` and `vary_on_cookie`, are the result of such a call kept under a name (`django/views/decorators/http.py:require_GET`).

## Before the view, and after

The Gazette's masthead has three decorators, and between them they show both places a wrapper can act.

```python
# gazette/views.py
@require_GET
@never_cache
@vary_on_cookie
def masthead(request):
    return HttpResponse("The Gazette")
```

`require_GET`, written first, makes the outermost wrapper, which acts before it calls inwards; the wrappers of `never_cache` and `vary_on_cookie` act after, on the response as it comes back out, the innermost first:

```text recording=views
GET /masthead/: three decorators around one function
    BaseHandler._get_response
      the wrapper require_http_methods made, for ['GET']
        the wrapper never_cache made
          the wrapper vary_on_headers made, for ('Cookie',)
            views.masthead(request)  ->  an HttpResponse, status 200
            patch_vary_headers(response, ('Cookie',))
            -> an HttpResponse, status 200
          add_never_cache_headers(response)
          -> an HttpResponse, status 200
        -> an HttpResponse, status 200
    start_response("200 OK", headers), with Vary: Cookie, Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private
    the server sends the body: 'The Gazette'
```

The wrapper that `require_http_methods` makes compares the request's method with its list, and if the method is not there it returns an `HttpResponseNotAllowed` naming the list, logs a warning, and never calls what it wraps (`django/views/decorators/http.py:require_http_methods`). A `"POST"` to the masthead gets no further than the outermost wrapper:

```text recording=views
POST /masthead/: the outermost wrapper answers, and nothing inside it runs
    BaseHandler._get_response
      the wrapper require_http_methods made, for ['GET']
        log, WARNING to django.request: Method Not Allowed (POST): /masthead/
        -> an HttpResponseNotAllowed, status 405, Allow 'GET'
    start_response("405 Method Not Allowed", headers), with Allow: GET
    the server sends the body: ''
```

> **Trap.** `require_http_methods` compares the request's method with its list as written, and the handlers' requests hold the method in upper case, so a list in lower case refuses every request: under `require_http_methods(["get"])` a `"GET"` gets a 405. The docstring asks for the methods in upper case, and nothing converts the list (`django/views/decorators/http.py:require_http_methods`, `django/core/handlers/wsgi.py:WSGIRequest.__init__`, `django/core/handlers/asgi.py:ASGIRequest.__init__`).

The masthead's other two wrappers each call inwards, take the response that comes back, and edit its headers before returning it. `vary_on_headers` hands the response to `patch_vary_headers` with the names it was given, and `never_cache` to `add_never_cache_headers`; `cache_control` hands its keyword arguments to `patch_cache_control`. What each of those functions writes, and how it merges with a header already there, is told in [Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md) (`django/views/decorators/vary.py:vary_on_headers`, `django/views/decorators/cache.py:never_cache`, `django/views/decorators/cache.py:cache_control`).

Since each decorator wraps what the one under it returned, the order of writing is the order of the wrappers: the first above a view is outermost, so it is the first to act before the view and the last to act after it, on a response the inner ones have already edited. A wrapper that answers by itself leaves everything under it unrun, so a decorator under one that may answer in the view's place, as `condition` may with a 304, sets nothing on that answer. Written under `condition`, `vary_on_cookie` runs only when the view does; written over it, it patches the 304 as well ([Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md#under-the-condition-decorator)) (`django/views/decorators/http.py:condition`).

The view decorators of the directory not made from a middleware class each change the request or the response before the view, after it, at both times, or never:

| decorator | when it changes anything | what it does |
|---|---|---|
| `require_http_methods`, and `require_GET`, `require_POST`, `require_safe` made from it | before | answers 405 itself unless the request's method is in its list; `require_safe` allows `"GET"` and `"HEAD"` |
| `condition`, and `etag`, `last_modified` made from it | before and after | may answer 304 or 412 itself; may add `"ETag"` and Last-Modified to the response |
| `never_cache` | after | `add_never_cache_headers` |
| `cache_control` | after | `patch_cache_control` with its keyword arguments |
| `vary_on_headers`, and `vary_on_cookie` made from it | after | `patch_vary_headers` with its names |
| `xframe_options_deny`, `xframe_options_sameorigin` | after | set X-Frame-Options unless the response has one |
| `xframe_options_exempt` | after | marks the response |
| `csp_override`, `csp_report_only_override` | after | mark the response |
| `sensitive_post_parameters` | before | marks the request |
| `csrf_exempt`, `no_append_slash` | never | mark the view |

*The view decorators of `django/views/decorators/` that are not made from a middleware, by when each changes the request or the response. The wrappers of `csrf_exempt` and `no_append_slash` run at every request and do nothing but call the view.*

`sensitive_variables`, in the same directory, is not for views in particular. It can decorate any function, and what it records is read by the exception reporter ([The debug pages and `ExceptionReporter`](debug.md#sensitive_variables-and-sensitive_post_parameters)).

## `condition`: answering before the view runs

Of the decorators in the table, `condition` is the one that can answer a request the view would have served, without calling the view. It is given one or two functions that work out, from the request and the view's own arguments, the `"ETag"` of what the view would return or the time it last changed. Its wrapper calls those first and passes the results to `get_conditional_response`, with the headers the client sent. If the client already holds the current version and the request is a `"GET"` or a `"HEAD"`, the answer is a 304 and the view is never called (`django/views/decorators/http.py:condition`).

For its view of today's edition, the Gazette has a function that returns the edition's tag.

```python
# gazette/views.py
def edition_tag(request):
    return "edition-7"


@condition(etag_func=edition_tag)
def edition(request):
    return HttpResponse("today's edition")
```

A request that sends that tag back in If-None-Match, as a client holding today's edition does, is answered by the wrapper: the tag function runs, and between `get_conditional_response` and the wrapper's return there is no call of the view.

```text recording=views
GET /edition/ with If-None-Match: "edition-7"
    BaseHandler._get_response
      the wrapper condition made
        views.edition_tag(request)  ->  'edition-7'
        get_conditional_response(request, etag='"edition-7"', last_modified=None)  ->  an HttpResponseNotModified, status 304
        -> an HttpResponseNotModified, status 304
    start_response("304 Not Modified", headers), with ETag: "edition-7"
    the server sends the body: ''
```

After the view, or in its place, the wrapper sets `"ETag"` and Last-Modified on the response, each only if the response lacks it and only for a `"GET"` or a `"HEAD"`. How `get_conditional_response` compares the versions, the 412 it gives a request that would replace a version other than the current one, and how the wrapper quotes a tag and reads a time without a time zone, are told in [Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md), with `ConditionalGetMiddleware`, which makes the same decision for a `"GET"` from the finished response, and so only after the view has done its work.

## Marks

A mark is an attribute set for some other code to find. The decorators leave them on the view, on the response, or on the request.

**On the view.** `csrf_exempt` and `no_append_slash` return a wrapper that does nothing but call the view, and set an attribute on the wrapper, `"csrf_exempt"` or `"should_append_slash"` (`django/views/decorators/csrf.py:csrf_exempt`, `django/views/decorators/common.py:no_append_slash`). `non_atomic_requests`, in `django/db/transaction.py`, marks its wrapper in the same way, with `"_non_atomic_requests"`, a set of database aliases, which a second use of the decorator copies with its own added (`django/db/transaction.py:_non_atomic_requests`). The view that was decorated is untouched: `csrf_exempt` around the Gazette's front-page view, a function with no decorators, gives a new function that carries the mark, and leaves the view without one.

```text recording=views
...
csrf_exempt(views.front).csrf_exempt  ->  True
csrf_exempt(views.front) is views.front  ->  False
hasattr(views.front, "csrf_exempt")  ->  False
...
```

> **Why.** Setting the attribute on the view itself would work as well, and the comment at the head of `csrf_exempt` and of `no_append_slash` says so; each returns a new function because, in that comment's words, "decorators are nicer if they don't have side effects" (`django/views/decorators/csrf.py:csrf_exempt`, `django/views/decorators/common.py:no_append_slash`). `login_not_required`, in `django/contrib/auth/decorators.py`, takes the other course: it sets its attribute on the view it is given and returns that same view (`django/contrib/auth/decorators.py:login_not_required`).

The marks are not all read at the same moment. `CsrfViewMiddleware.process_view` reads `"csrf_exempt"` and `BaseHandler.make_view_atomic` reads `"_non_atomic_requests"`, both from the view the handler is about to call. `"should_append_slash"` is read by `CommonMiddleware.should_redirect_with_slash`, which resolves the path with a slash added to find the view it would lead to, and is called from that middleware's `process_request` and `process_response` ([What the handler asks of a view](callable.md#what-other-code-reads-from-a-view)) (`django/middleware/common.py:CommonMiddleware.should_redirect_with_slash`).

**On the response.** `xframe_options_exempt` calls the view and sets `"xframe_options_exempt"`, true, on the response, which `XFrameOptionsMiddleware.process_response` tests before it adds its header. `csp_override` and `csp_report_only_override` each store a policy on the response, which `ContentSecurityPolicyMiddleware.process_response` uses in place of the one in the settings (`django/views/decorators/clickjacking.py:xframe_options_exempt`, `django/views/decorators/csp.py:_make_csp_decorator`).

**On the request.** `sensitive_post_parameters` sets an attribute of its own name on the request each time the view is called, holding the names of the posted fields that an error report must not show, `("password",)` for `sensitive_post_parameters("password")`, or `"__ALL__"` for `sensitive_post_parameters()` (`django/views/decorators/debug.py:sensitive_post_parameters`). How a report reads it is told in [The debug pages and `ExceptionReporter`](debug.md#sensitive_variables-and-sensitive_post_parameters).

`never_cache` and `cache_control` guard against being used on a method, where the first argument would be the view's instance and not a request: they test that their first argument has a `META` attribute, and `sensitive_post_parameters` tests that it is an `HttpRequest`. Each raises a `TypeError` that recommends `method_decorator`. `sensitive_variables` and `sensitive_post_parameters` refuse another slip, with a message of their own: they must be called, even with no arguments, and refuse to be handed a function directly.

```text recording=views
...
never_cache(views.front)('not a request')  ->  raises TypeError: never_cache didn't receive an HttpRequest. If you are decorating a classmethod, be sure to use @method_decorator.
sensitive_variables(views.front)  ->  raises TypeError: sensitive_variables() must be called to use it as a decorator, e.g., use @sensitive_variables(), not @sensitive_variables.
```
