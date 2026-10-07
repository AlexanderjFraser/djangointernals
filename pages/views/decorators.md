---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# View decorators

The decorators of `django/views/decorators/`: the wrappers they put around a view, the marks some of them leave on a view, a response or a request, how `condition` answers a request without calling the view, and how `method_decorator` applies any of them to a method of a class.

A view decorator takes a view and returns what goes into the URLconf in its place. That is all the word means, and the handler knows nothing about it: by the time a request arrives, a decorator written above a function ran long ago, when the module that defines the view was imported, and what is left is a function. This section sorts Django's decorators by what that function does. Some call the view and act before the call or after it. Some change nothing about the call and exist to be noticed by other code. And one group is made mechanically from middleware classes, which the [next section](middleware-decorators.md) takes up.

## The shape they share

The decorators in the directory that make a wrapper are, all but `sensitive_variables`, written to one pattern. Each defines the wrapper twice, once with `def` and once with `async def`, picks one of the two by asking whether the view is a coroutine function, and returns it after passing it through `functools.wraps` (`django/views/decorators/cache.py:never_cache`).

The choice between the two wrappers is made when the decorator runs, once, and not for each request. It keeps a coroutine function a coroutine function, which the handler depends on ([Asynchronous views](async.md#what-a-decorator-has-to-keep)).

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

The wrapper that `require_http_methods` makes acts before. It compares the request's method with its list, and if the method is not there it returns an `HttpResponseNotAllowed` naming the list, logs a warning, and never calls what it wraps. The names in the list are compared as they stand, so they have to be in upper case (`django/views/decorators/http.py:require_http_methods`).

```text recording=views
POST /masthead/: the outermost wrapper answers, and nothing inside it runs
    BaseHandler._get_response
      the wrapper require_http_methods made, for ['GET']
        log, WARNING to django.request: Method Not Allowed (POST): /masthead/
        -> an HttpResponseNotAllowed, status 405, Allow 'GET'
    start_response("405 Method Not Allowed", headers), with Allow: GET
    the server sends the body: ''
```

The other two act after. Each calls inwards, takes the response that comes back, and edits its headers before returning it. `vary_on_headers` passes the response to `patch_vary_headers`, which adds the names it was given to the `"Vary"` header (`django/views/decorators/vary.py:vary_on_headers`). `never_cache` passes it to `add_never_cache_headers`, which sets `"Expires"` to the present moment, unless the response has that header already, and adds five directives to `Cache-Control`, which on a response with no such header gives the value in the recording (`django/views/decorators/cache.py:never_cache`, `django/utils/cache.py:add_never_cache_headers`). `cache_control` is the general form: its keyword arguments go to `patch_cache_control`, which edits that header with them (`django/views/decorators/cache.py:cache_control`).

Since the wrappers are nested, their order is the order they were written in. The first decorator above a view is outermost. When it acts before the view it acts first, and when it acts after it acts last, on a response that the inner ones have already edited.

The table lists the view decorators of the directory by where they act. The ones made from middleware are left for the next section.

| decorator | acts | what it does |
|---|---|---|
| `require_http_methods`, and `require_GET`, `require_POST`, `require_safe` made from it | before | answers 405 itself unless the request's method is in its list; `require_safe` allows `"GET"` and `"HEAD"` |
| `condition`, and `etag`, `last_modified` made from it | before and after | may answer 304 or 412 itself; adds `"ETag"` and `Last-Modified` to the response |
| `never_cache` | after | `add_never_cache_headers` |
| `cache_control` | after | `patch_cache_control` with its keyword arguments |
| `vary_on_headers`, and `vary_on_cookie` made from it | after | `patch_vary_headers` with its names |
| `xframe_options_deny`, `xframe_options_sameorigin` | after | set `X-Frame-Options` unless the response has one |
| `xframe_options_exempt` | after | marks the response |
| `csp_override`, `csp_report_only_override` | after | mark the response |
| `sensitive_post_parameters` | before | marks the request |
| `csrf_exempt`, `no_append_slash` | at no time | mark the view |

*The view decorators of `django/views/decorators/` that are not made from a middleware.*

`sensitive_variables`, in the same directory, is not for views in particular. It can decorate any function, and what it records is read by the exception reporter ([The debug pages and `ExceptionReporter`](debug.md#sensitive_variables-and-sensitive_post_parameters)).

## Marks

A mark is an attribute set for some other code to find. The decorators leave them on the view, on the response, or on the request.

**On the view.** `csrf_exempt` and `no_append_slash` return a wrapper that does nothing but call the view, and set an attribute on the wrapper: `"csrf_exempt"` for `CsrfViewMiddleware`, `"should_append_slash"` for `CommonMiddleware` (`django/views/decorators/csrf.py:csrf_exempt`, `django/views/decorators/common.py:no_append_slash`). The view that was decorated is untouched: here front is the Gazette's plainest view, a function with no decorators.

```text recording=views
csrf_exempt(views.front).csrf_exempt  ->  True
csrf_exempt(views.front) is views.front  ->  False
hasattr(views.front, "csrf_exempt")  ->  False
csrf_exempt(views.front).__wrapped__ is views.front  ->  True
csrf_exempt(views.front).__name__  ->  'front'
no_append_slash(views.front).should_append_slash  ->  False
non_atomic_requests(views.front)._non_atomic_requests  ->  {'default'}
non_atomic_requests(using="archive")(non_atomic_requests(views.front))._non_atomic_requests == {"default", "archive"}  ->  True
```

> **Why a wrapper, for a mark.** Setting the attribute on the view itself would work just as well, and a comment in each of the two functions says so. They return a new function because, in the comment's words, decorators are nicer if they don't have side effects. `login_not_required`, in `django/contrib/auth/decorators.py`, takes the other course. It sets its attribute on the view it is given and returns that same view.

`non_atomic_requests`, which lives with the transaction code in `django/db/transaction.py`, is of the same family: its wrapper carries a set of database aliases, and a second use of the decorator adds to the set the first one left.

The marks are not all read at the same moment. `CsrfViewMiddleware.process_view` reads `"csrf_exempt"` and `BaseHandler.make_view_atomic` reads `"_non_atomic_requests"`, both from the view the handler is about to call. `"should_append_slash"` is read by `CommonMiddleware.should_redirect_with_slash`, which resolves the path with a slash added to find the view it would lead to, and is called from that middleware's `process_request` and `process_response` ([What the handler asks of a view](callable.md#what-other-code-reads-from-a-view)).

**On the response.** `xframe_options_exempt` calls the view and sets an attribute on the response, which `XFrameOptionsMiddleware.process_response` tests before it adds its header. `csp_override` and `csp_report_only_override` each store a policy on the response, which `ContentSecurityPolicyMiddleware.process_response` uses in place of the one in the settings (`django/views/decorators/clickjacking.py:xframe_options_exempt`, `django/views/decorators/csp.py:_make_csp_decorator`).

**On the request.** `sensitive_post_parameters` sets an attribute on the request each time the view is called, naming the posted fields that an error report must not show (`django/views/decorators/debug.py:sensitive_post_parameters`).

```text recording=views
xframe_options_exempt(views.front)(request()).xframe_options_exempt  ->  True
after sensitive_post_parameters("password")(views.front) is called with a request: request.sensitive_post_parameters  ->  ('password',)
```

`never_cache` and `cache_control` guard against being used on a method, where the first argument would be the view's instance and not a request: they test that their first argument has a `META` attribute. `sensitive_post_parameters` tests that it is an `HttpRequest`. Each raises a `TypeError` that recommends `method_decorator`.

```text recording=views
never_cache(views.front)('not a request')  ->  raises TypeError: never_cache didn't receive an HttpRequest. If you are decorating a classmethod, be sure to use @method_decorator.
sensitive_variables(views.front)  ->  raises TypeError: sensitive_variables() must be called to use it as a decorator, e.g., use @sensitive_variables(), not @sensitive_variables.
```

The second line is a different slip with a message of its own: `sensitive_variables` and `sensitive_post_parameters` must be called, even with no arguments, and refuse to be handed a function directly.

## `condition`: answering before the view runs

Of the decorators in the table, `condition` is the one that can answer a request the view would have served, without calling the view. It is given one or two functions that work out, from the request and the view's own arguments, the `"ETag"` of what the view would return or the time it last changed. Its wrapper calls those first and passes the results to `get_conditional_response`, with the headers the client sent. If the client already holds the current version and the request is a `"GET"` or a `"HEAD"`, the answer is a 304 and the view is never called (`django/views/decorators/http.py:condition`).

The Gazette's view of today's edition has a function that returns the edition's tag.

```python
# gazette/views.py
def edition_tag(request):
    return "edition-7"


@condition(etag_func=edition_tag)
def edition(request):
    return HttpResponse("today's edition")
```

A first request runs the view and is told the tag:

```text recording=views
GET /edition/: a view under condition()
    BaseHandler._get_response
      the wrapper condition made
        views.edition_tag(request)  ->  'edition-7'
        get_conditional_response(request, etag='"edition-7"', last_modified=None)  ->  None
        views.edition(request)  ->  an HttpResponse, status 200
        -> an HttpResponse, status 200
    start_response("200 OK", headers), with ETag: "edition-7"
    the server sends the body: "today's edition"
```

A second request sends the tag back in `If-None-Match`:

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

The tag function ran and the view did not. For a method that changes things the same function protects against overwriting: a `"PUT"` that says, in `If-Match`, which version it means to replace is answered with a 412 when that is not the version there is.

```text recording=views
PUT /edition/ with If-Match: "edition-6"
    BaseHandler._get_response
      the wrapper condition made
        views.edition_tag(request)  ->  'edition-7'
        get_conditional_response(request, etag='"edition-7"', last_modified=None)
          log, WARNING to django.request: Precondition Failed: /edition/
          -> an HttpResponse, status 412
        -> an HttpResponse, status 412
    start_response("412 Precondition Failed", headers)
    the server sends the body: ''
```

After the view, or in its place, the wrapper sets `"ETag"` and `Last-Modified` on the response, each only if the response lacks it and only for a `"GET"` or a `"HEAD"`. A tag function may return its tag with or without the quotation marks, and a time without a time zone is taken to be in UTC. `etag` and `last_modified` are `condition` called with one of its two arguments.

The comparisons themselves, and `ConditionalGetMiddleware`, which makes the same decision for a `"GET"` from the finished response and so only after the view has done its work, belong to [Caching, files, mail, signals and tasks](../services.md).

## Decorating a class

A wrapper such as the one `require_http_methods` makes takes the request as its first argument, and uses it. A method's first argument is the instance. So a decorator whose wrapper uses the request cannot be written above a handler method as it stands, and `method_decorator` exists to adapt it (`django/utils/decorators.py:method_decorator`).

It can be used in either of two ways. Applied to a method in a class body, it returns a replacement for that method. Applied to a class, with the name of a method, it sets the replacement on the class under that name and returns the class; a name that is no attribute of the class is a `ValueError`. For an inherited method such as `dispatch` the second form gives the subclass an attribute of its own and leaves the base class as it was.

The replacement is made by `_multi_decorate`, and it does not apply the decorator to the method when the class is defined. It applies it at each call. A comment there says what the decorator is given: something with the signature it expects, with no `self`, that closes over the instance. There is no instance before the call. So the method that `_multi_decorate` returns takes `self`, binds the original method to that instance, wraps the bound method in the decorator, and calls the result. A decorator does its setting up again for every request (`django/utils/decorators.py:_multi_decorate`).

The Gazette has a decorator that says when it is applied and when its wrapper is called, and a class with that decorator on `dispatch`:

```python
# gazette/stamp.py, and the class in gazette/views.py
def announced(view):
    # called(view) is the view's name, and says so when the view is a partial around a bound method
    say(f"announced is applied to {called(view)}")

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        say("the wrapper that announced made is called")
        return view(request, *args, **kwargs)

    return wrapper


@method_decorator(announced, name="dispatch")
class Births(View):
    def get(self, request):
        return HttpResponse("births, marriages and deaths")
```

```text recording=views
BaseHandler._get_response
  view(request)  (the function as_view returned for Births)
    View.__init__()  (a new Births)
    View.setup(request)
    the wrapper method_decorator made
      announced is applied to a partial around the bound method View.dispatch
      the wrapper that announced made is called
      View.dispatch(request)
        Births.get(request)  ->  an HttpResponse, status 200
        -> an HttpResponse, status 200
      -> an HttpResponse, status 200
    -> an HttpResponse, status 200
start_response("200 OK", headers)
```

Inside the function that `as_view` made, the wrapper from `method_decorator` runs in the place of `dispatch`, applies the decorator to this instance's `dispatch`, and only then calls into it. A second request does all of it again. For a decorator that merely wraps, the cost is a few small objects made and thrown away, the decorator's wrapper among them. For one that builds something when it is applied, it is that thing built for each request ([A middleware as a decorator](middleware-decorators.md#on-a-method-a-middleware-for-every-request)).

Marks need separate care, since a mark must be on the method before any call is made. So `_multi_decorate` also applies each decorator once, when the class is defined, to a function that does nothing, and copies whatever attributes that function comes back with onto the replacement method (`django/utils/decorators.py:_update_method_wrapper`). The announcing decorator shows it happening, as the module that defines the class is imported:

```text recording=views
method_decorator(announced, name='dispatch')
_multi_decorate(decorators, View.dispatch)
  _update_method_wrapper
    announced is applied to _update_method_wrapper.<locals>.dummy
```

`as_view` then finishes the job for one method. It copies the attributes of `dispatch` onto the function it returns, so a mark on `dispatch` reaches the URLconf and a mark on `post` stays on `post`, where no middleware looks. Two of the Gazette's classes differ in nothing else:

```python
# gazette/views.py
@method_decorator(csrf_exempt, name="dispatch")
class Tips(View):
    def post(self, request):
        return HttpResponse("thank you")


class TipsMarkedOnPost(View):
    @method_decorator(csrf_exempt)
    def post(self, request):
        return HttpResponse("thank you")
```

```text recording=views
views.Tips.as_view().csrf_exempt  ->  True
views.Tips.dispatch.csrf_exempt  ->  True
hasattr(views.TipsMarkedOnPost.as_view(), "csrf_exempt")  ->  False
views.TipsMarkedOnPost.post.csrf_exempt  ->  True
views.Tips.dispatch is View.dispatch  ->  False
```

With `CsrfViewMiddleware` installed, a form posted to each of the two without a token gets two different answers:

```text recording=views
POST /tips/ and POST /tips/marked/ with CsrfViewMiddleware installed and no token sent
    POST /tips/, whose class has csrf_exempt on dispatch
    start_response("200 OK", headers)
    POST /tips/marked/, whose class has csrf_exempt on post
    log, WARNING to django.security.csrf: Forbidden (CSRF cookie not set.): /tips/marked/
    start_response("403 Forbidden", headers)
```

Given a list of decorators, `method_decorator` applies them so that the first in the list is outermost, as if they had been written one above another in that order.
