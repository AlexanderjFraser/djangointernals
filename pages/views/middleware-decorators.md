---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A middleware as a decorator

Several of Django's view decorators are a middleware class applied to one view: an instance of the class is made for the decorated view, and a wrapper calls the instance's hooks around the view. `csrf_protect`, `requires_csrf_token`, `ensure_csrf_cookie`, `gzip_page` and `conditional_page` are made by `decorator_from_middleware`, and `cache_page` by its variant that takes arguments.

A middleware acts on every request a site serves. Sometimes the same behaviour is wanted for one view only: the page cache for the one expensive page, the CSRF check for the one form on a site that does not install the middleware. For these, Django does not write the behaviour twice. `decorator_from_middleware` takes the middleware class and returns a decorator, and the decorator runs the middleware's own methods around a single view. Both it and the variant are one line each, a call of `make_middleware_decorator`, where the work is done (`django/utils/decorators.py:decorator_from_middleware`, `django/utils/decorators.py:make_middleware_decorator`).

The result behaves like the middleware in most respects and unlike it in a few, and the few come from where the decorator's wrapper stands. A middleware in the chain is outside the URL resolver, the other middleware's `process_view` hooks, and the handler's rendering of template responses. The decorator's wrapper is inside all of them, with nothing between it and the view.

## The decorators made this way

Five of them are made in one line of their module: `decorator_from_middleware` applied to a class, and the result bound to a name. The lines after it give four of them a docstring, and the three for CSRF a name of their own as well. `cache_page` is a function, described below.

| decorator | made from | what it adds to the one view |
|---|---|---|
| `csrf_protect` | `CsrfViewMiddleware` | the CSRF check, as the middleware makes it |
| `requires_csrf_token` | `_EnsureCsrfToken` | the same processing with rejection turned off: a token is there for the template, and no request is refused |
| `ensure_csrf_cookie` | `_EnsureCsrfCookie` | the same as the last, and the CSRF secret is sent with the response, as the cookie unless `settings.CSRF_USE_SESSIONS` keeps it in the session, whether or not the template used the token |
| `cache_page` | `CacheMiddleware` | the page cache, with a timeout, a cache alias and a key prefix of its own |
| `gzip_page` | `GZipMiddleware` | compression of the response |
| `conditional_page` | `ConditionalGetMiddleware` | for a `"GET"`, an `"ETag"` worked out from the finished response, and a 304 when the client already has it |

*The decorators in `django/views/decorators/` that are a middleware class applied to one view.*

The two classes with an underscore are subclasses of `CsrfViewMiddleware` kept beside the decorators that use them. Both replace `CsrfViewMiddleware._reject` with a method that returns `None`, so that a failed check is not an answer, and `_EnsureCsrfCookie` adds a call of `get_token`, which is what makes the middleware's `process_response` set the cookie (`django/views/decorators/csrf.py:_EnsureCsrfToken`, `django/views/decorators/csrf.py:_EnsureCsrfCookie`).

```text recording=views
The decorators Django makes from its own middleware
    csrf_protect(views.front)(request("/", "POST", {})).status_code  ->  403
      log, WARNING to django.security.csrf: Forbidden (CSRF cookie not set.): /
    requires_csrf_token(views.front)(request("/", "POST", {})).status_code  ->  200
    "csrftoken" in views.front(request()).cookies  ->  False
    "csrftoken" in csrf_protect(views.front)(request()).cookies  ->  False
    "csrftoken" in ensure_csrf_cookie(views.front)(request()).cookies  ->  True
    cache_page(60)(views.front)(request()).headers["Cache-Control"]  ->  'max-age=60'
    csrf_protect.__name__  ->  'csrf_protect'
```

`cache_page` takes arguments, and is made by the variant that passes them on. `decorator_from_middleware_with_args` returns a function whose arguments are given to the middleware's constructor after the view, and `cache_page` is a small function that calls it with the timeout, the alias and the prefix under the names `CacheMiddleware.__init__` expects (`django/views/decorators/cache.py:cache_page`). What the cache then does with a request and a response is the subject of [Caching, files, mail, signals and tasks](../services.md), and the CSRF check that of [Security](../security.md).

## One instance for each view

The Gazette has a middleware that has all five hooks and does nothing in any of them but say that it was called, and a decorator made from it.

```python
# gazette/stamp.py
class Stamp(MiddlewareMixin):
    def __init__(self, get_response): ...
    def process_request(self, request): ...
    def process_view(self, request, view, args, kwargs): ...
    def process_exception(self, request, exception): ...
    def process_template_response(self, request, response): ...
    def process_response(self, request, response): ...


stamped = decorator_from_middleware(Stamp)

# gazette/views.py
@stamped
def notices(request):
    return HttpResponse("public notices")
```

When the decorator is applied to a view it calls the middleware class with the view as its first argument. A middleware's first argument is the callable it is to wrap, `get_response`, so the instance believes the view is the rest of the chain. This happens as the views module is imported:

```text recording=views
import gazette.views
  the decorator made from Stamp is given notices
    Stamp.__init__(get_response=notices)
  the decorator made from Stamp is given notices_page
    Stamp.__init__(get_response=notices_page)
  the decorator made from Stamp is given notices_lost
    Stamp.__init__(get_response=notices_lost)
```

Three of the Gazette's functions are decorated with it, so three instances are made, each holding its own view. An instance lasts as long as the wrapper that uses it. A middleware that keeps state on itself keeps it per decorated view.

The wrapper never calls the instance, though. In the chain the handler calls the middleware object, and `MiddlewareMixin.__call__` runs `process_request`, the rest of the chain and `process_response` in turn. The wrapper leaves that method alone, looks for each hook by name, and calls the ones it finds itself. The view is called by the wrapper directly and not through the instance's `get_response`.

## The hooks, in the wrapper's order

```text recording=views
GET /notices/: a view decorated with a middleware
    BaseHandler._get_response
      the wrapper made from Stamp
        Stamp.process_request
        Stamp.process_view(view=notices)
        views.notices(request)  ->  an HttpResponse, status 200
        Stamp.process_response(a 200, content='public notices')
        -> an HttpResponse, status 200
    start_response("200 OK", headers)
    the server sends the body: 'public notices'
```

Before the view, the wrapper calls `process_request` with the request, and then `process_view` with the request, the undecorated view and the arguments the view is about to get. After it, `process_response`.

`process_request` runs after the URL has been resolved. In the chain it runs before, and is not told which view the request is for. Here it runs because the view was chosen, an instant before `process_view`, and the distinction between the two hooks has gone.

A response from either of the first two hooks is returned as it is. The wrapper does not pass it to `process_response`, where `MiddlewareMixin.__call__` would. The Gazette has a second middleware, a Stamp whose `process_request` answers the request itself, and a view decorated with it:

```text recording=views
GET /notices/shut/: the middleware's process_request answers
    BaseHandler._get_response
      the wrapper made from Shut
        Shut.process_request, which returns a response
        -> an HttpResponse, status 200
    start_response("200 OK", headers)
    the server sends the body: 'the office is shut'
```

And an exception is handled on the spot. If the view raises, the wrapper calls `process_exception`. A response from that hook is returned, again without `process_response`. If the hook returns nothing the exception is raised again and carries on up to the handler, which makes the 500:

```text recording=views
BaseHandler._get_response
  the wrapper made from Stamp
    Stamp.process_request
    Stamp.process_view(view=notices_lost)
    views.notices_lost(request)  raises LookupError
    Stamp.process_exception(LookupError)
response_for_exception(request, LookupError)
  signal got_request_exception, for LookupError: the notices are lost
  the wrapper made from _EnsureCsrfToken  ->  an HttpResponseServerError, status 500
  log, ERROR to django.request: Internal Server Error: /notices/lost/
  -> an HttpResponseServerError, status 500
start_response("500 Internal Server Error", headers)
```

`process_response` did not run. A middleware in the chain would have seen the 500, because `convert_exception_to_response`, around the layer inside it, had already turned the exception into a response. The decorator's wrapper is inside that conversion and sees the exception itself.

## A template response is finished later

A view may return a `TemplateResponse`, which has not been rendered when the wrapper gets it back. The handler will render it, but only after the wrapper has returned. A `process_response` that ran in the wrapper would be given a response whose content cannot yet be read. So for a response with a callable `render` the wrapper does two different things: it calls `process_template_response` straight away, and it registers `process_response` on the response as a callback to be run after rendering (`django/template/response.py:SimpleTemplateResponse.add_post_render_callback`).

```text recording=views
GET /notices/page/: the decorated view returns a TemplateResponse
    BaseHandler._get_response
      the wrapper made from Stamp
        Stamp.process_request
        Stamp.process_view(view=notices_page)
        views.notices_page(request)  ->  a TemplateResponse, status 200, not rendered
        Stamp.process_template_response(is_rendered=False)
        SimpleTemplateResponse.add_post_render_callback
        -> a TemplateResponse, status 200, not rendered
      SimpleTemplateResponse.render
        Stamp.process_response(a 200, content='3 public notices\n')
    start_response("200 OK", headers)
    the server sends the body: '3 public notices\n'
```

The wrapper returned an unrendered response. The handler's own `process_template_response` hooks run at that point, on a site that has any, and then the handler called `render`, which ran the callback. If the callback returns a response, `render` returns that one in place of the one it rendered, so for a response that was not yet rendered the hook can still replace it, as it could in the chain (`django/template/response.py:SimpleTemplateResponse.render`).

The comment in the source gives the purpose in a line: to defer `process_response` until after the template has been rendered.

## A coroutine view

For a view that is a coroutine function the wrapper is a coroutine function too, and awaits the view. The hooks are a different matter. They are ordinary methods, and the wrapper calls them directly, as the synchronous wrapper does, with no `sync_to_async` between. They run wherever the wrapper is running (`django/utils/decorators.py:make_middleware_decorator`).

## On a method: a middleware for every request

One instance for each decorated view is the arrangement when the decorator is applied to a function. `method_decorator` changes it. That function applies its decorator again at every call ([View decorators](decorators.md#decorating-a-class)), and to apply a decorator of this kind is to construct a middleware. The Gazette's crossword view is a class with stamped on its `dispatch`:

```python
# gazette/views.py
@method_decorator(stamped, name="dispatch")
class Crossword(View):
    def get(self, request):
        return HttpResponse("today's crossword")
```

```text recording=views
BaseHandler._get_response
  view(request)  (the function as_view returned for Crossword)
    View.__init__()  (a new Crossword)
    View.setup(request)
    the wrapper method_decorator made
      the decorator made from Stamp is given a partial around the bound method View.dispatch
        Stamp.__init__(get_response=a partial around the bound method View.dispatch)
      the wrapper made from Stamp
        Stamp.process_request
        Stamp.process_view(view=a partial around the bound method View.dispatch)
        View.dispatch(request)
          Crossword.get(request)  ->  an HttpResponse, status 200
          -> an HttpResponse, status 200
        Stamp.process_response(a 200, content="today's crossword")
        -> an HttpResponse, status 200
      -> an HttpResponse, status 200
    -> an HttpResponse, status 200
start_response("200 OK", headers)
the server sends the body: "today's crossword"
```

The construction of a Stamp is in the recording, under the wrapper that `method_decorator` made. It runs for each request to that view, and the instance it makes serves that request and no other. One more instance is made when the class is defined, around a function that does nothing, so that `method_decorator` can copy any attributes the decorator sets:

```text recording=views
method_decorator(stamped, name='dispatch')
_multi_decorate(decorators, View.dispatch)
  _update_method_wrapper
    the decorator made from Stamp is given _update_method_wrapper.<locals>.dummy
      Stamp.__init__(get_response=_update_method_wrapper.<locals>.dummy)
```

Django's own class-based views are decorated in this way. `LoginView` has `csrf_protect` among the decorators on its `dispatch`, so each request to a login page constructs a `CsrfViewMiddleware` (`django/contrib/auth/views.py:LoginView`).

## Used together with the middleware

`csrf_protect` can be used on a site that also installs `CsrfViewMiddleware`; its docstring calls using both harmless and efficient, and the middleware is written to make it so. `CsrfViewMiddleware._accept`, which `process_view` calls for a request it accepts, sets an attribute on the request, and `process_view` returns at once when it is given a request already marked. And once `process_response` has set the cookie, it clears the flag that asked for the cookie, so a second instance does not set it again (`django/middleware/csrf.py:CsrfViewMiddleware._accept`, `django/middleware/csrf.py:CsrfViewMiddleware.process_view`, `django/middleware/csrf.py:CsrfViewMiddleware.process_response`).

The four default error views are themselves decorated with `requires_csrf_token`. The comment above them says why: they can be called when `CsrfViewMiddleware.process_view` has not run, and the template may need the CSRF token. A path that matched nothing is such a case ([The error views](errors.md)).
