---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A middleware as a decorator

Several of Django's view decorators are a middleware class applied to one view: an instance of the class is made for the decorated view, and a wrapper calls the instance's hooks around the view. `csrf_protect`, `requires_csrf_token`, `ensure_csrf_cookie`, `gzip_page` and `conditional_page` are made by `decorator_from_middleware`, and `cache_page` by `decorator_from_middleware_with_args`, its variant that takes arguments.

A middleware acts on every request a site serves. Sometimes the same behaviour is wanted for one view only: the page cache for the one expensive page, the CSRF check for the one form on a site that does not install the middleware. For these, Django does not write the behaviour twice. `decorator_from_middleware` takes the middleware class and returns a decorator, and the decorator runs the middleware's own methods around a single view. It and its variant both hand the class to `make_middleware_decorator`, which does the work (`django/utils/decorators.py:decorator_from_middleware`, `django/utils/decorators.py:make_middleware_decorator`).

The result behaves like the middleware in most respects and unlike it in a few. A middleware in the chain is outside the URL resolver, the other middleware's `process_view` hooks, and the handler's rendering of template responses. The decorator's wrapper is inside all of them, called once `BaseHandler._get_response` has resolved the path (`django/core/handlers/base.py:BaseHandler._get_response`).

The figure follows one request for such a view, on a site whose chain holds a middleware as well, from the outside in. The wrapper is a box inside `BaseHandler._get_response`, below the chain's `process_view` hooks, and only for a template response does a hook of its middleware run outside it.

```text figure=the-wrapper
One request for a view under a decorator made from a middleware, on a site whose chain holds
a middleware as well; outermost first.
A dashed arrow, - - ->, takes process_response out of the wrapper, for a template response.

a middleware of the chain            process_request
  BaseHandler._get_response          resolves the path
    the chain's process_view hooks
    the wrapper the decorator made   calls the hooks of the instance made for this view
      process_request                either one answers: its response is returned at once,
      process_view                     and process_response is not called
      the view                       it raises: process_exception; if that gives no response,
                                       the exception goes on, out of the wrapper
      process_response  - - ->       for a template response: process_template_response, then
                                       process_response registered on it as a callback
    SimpleTemplateResponse.render    the handler renders the template response,
      - - ->  process_response         and the callback runs
a middleware of the chain            process_response
```

*One request, outermost first: a middleware of the chain outside, `BaseHandler._get_response` inside it, and, accented, the wrapper the decorator made, which holds its own instance's hooks and the view. Beside them are the wrapper's other ways out; the dashed arrow takes `process_response`, for a template response, out of the wrapper to the handler's render.*

## The decorators made this way

`csrf_protect`, `requires_csrf_token`, `ensure_csrf_cookie`, `gzip_page` and `conditional_page` are each made by a single statement of their module: `decorator_from_middleware` applied to a class, and the result bound to a name. The statements after it give each but `conditional_page` a docstring, and the three for CSRF a name of their own as well (`django/views/decorators/csrf.py`, `django/views/decorators/gzip.py`, `django/views/decorators/http.py`). `cache_page` is a function, described below.

| decorator | made from | what it adds to the one view |
|---|---|---|
| `csrf_protect` | `CsrfViewMiddleware` | the CSRF check, as the middleware makes it |
| `requires_csrf_token` | `_EnsureCsrfToken` | the same processing with rejection turned off: a token is there for the template, and no request is refused |
| `ensure_csrf_cookie` | `_EnsureCsrfCookie` | the same as the last, and the CSRF secret is sent with the response, as the cookie unless `settings.CSRF_USE_SESSIONS` keeps it in the session, whether or not the template used the token |
| `cache_page` | `CacheMiddleware` | the page cache, with a timeout, a cache alias and a key prefix of its own |
| `gzip_page` | `GZipMiddleware` | compression of the response |
| `conditional_page` | `ConditionalGetMiddleware` | for a `"GET"`, an `"ETag"` worked out from the finished response, and a 304 when the client already has it |

*The decorators in `django/views/decorators/` that are a middleware class applied to one view.*

The two classes with an underscore are subclasses of `CsrfViewMiddleware` kept beside the decorators that use them. Both replace `CsrfViewMiddleware._reject` with a method that returns `None`, so that a failed check is not an answer, and `_EnsureCsrfCookie` adds a call of `get_token`, which is what makes the middleware's `process_response` set the cookie (`django/views/decorators/csrf.py:_EnsureCsrfToken`, `django/views/decorators/csrf.py:_EnsureCsrfCookie`). Django's four default error views carry `requires_csrf_token` ([The error views](errors.md)) (`django/views/defaults.py`).

Applied to the Gazette's front page, a plain function, the three for CSRF differ where the table says: in whether a `"POST"` without a token is refused, and in whether a page that never used the token gets the cookie.

```text recording=views
The decorators Django makes from its own middleware
    csrf_protect(views.front)(request("/", "POST", {})).status_code  ->  403
      log, WARNING to django.security.csrf: Forbidden (CSRF cookie not set.): /
    requires_csrf_token(views.front)(request("/", "POST", {})).status_code  ->  200
    "csrftoken" in views.front(request()).cookies  ->  False
    "csrftoken" in csrf_protect(views.front)(request()).cookies  ->  False
    "csrftoken" in ensure_csrf_cookie(views.front)(request()).cookies  ->  True
    ...
```

`cache_page` takes arguments, and is made by the variant that passes them on. `decorator_from_middleware_with_args` returns a function whose arguments are given to the middleware's constructor after the view, and `cache_page` is a small function that calls it with the timeout, the alias and the prefix under the names `CacheMiddleware.__init__` expects (`django/views/decorators/cache.py:cache_page`). What the cache then does with a request and a response is the subject of [The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md), and the CSRF check that of [The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md).

## One instance for each view

A decorator made from a middleware class, applied to a view, calls the class with the view as its first argument. A middleware's first argument is the callable it is to wrap, `get_response`, so the instance believes the view is the rest of the chain (`django/utils/decorators.py:make_middleware_decorator`).

The Gazette has a middleware, Stamp, that has all five hooks and does nothing in any of them but say that it was called, and a decorator made from it:

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

Each function decorated with it gets an instance of its own, made as the views module is imported, holding that function as its `get_response`:

```text recording=views
The URLconf is imported: each as_view() is called once; the decorators made from a middleware, and method_decorator, as they run
      ...
      import gazette.views
        the decorator made from Stamp is given notices
          Stamp.__init__(get_response=notices)
        the decorator made from Stamp is given notices_page
          Stamp.__init__(get_response=notices_page)
        the decorator made from Stamp is given notices_lost
          Stamp.__init__(get_response=notices_lost)
          ...
```

An instance lasts as long as the wrapper that uses it. A middleware that keeps state on itself keeps it per decorated view.

## The hooks, in the wrapper's order

The wrapper that `make_middleware_decorator` makes never calls the instance. In the chain the handler calls the middleware object, and `MiddlewareMixin.__call__` runs `process_request`, the rest of the chain and `process_response` in turn. The wrapper leaves that method alone, looks for each hook by name, and calls the ones it finds itself. The view is called by the wrapper directly and not through the instance's `get_response` (`django/utils/decorators.py:make_middleware_decorator`, `django/middleware/__init__.py:MiddlewareMixin.__call__`).

Before the view the wrapper calls `process_request` with the request, then `process_view` with the request, the callable it wraps and the arguments the view is about to get; after it, `process_response`. In a request for the Gazette's notices the three stand directly under the wrapper, around the view, and `process_view` is given the undecorated function:

```text recording=views
GET /notices/: a view decorated with a middleware
    BaseHandler._get_response
      the wrapper made from Stamp
        Stamp.process_request
        Stamp.process_view(view=notices)
        views.notices(request)  ->  an HttpResponse, status 200
        Stamp.process_response(a 200, content='public notices')
        ...
```

Either of the first two hooks may answer, and the wrapper then returns that response at once. Shut, a Stamp whose `process_request` answers the request itself, ends a request for the view it decorates before `process_view` and the view are reached, and nothing of Shut's runs after it:

```text recording=views
GET /notices/shut/: the middleware's process_request answers
    BaseHandler._get_response
      the wrapper made from Shut
        Shut.process_request, which returns a response
        -> an HttpResponse, status 200
        ...
```

An exception from the view goes to `process_exception`, and the wrapper returns the hook's response if it gives one. If it gives none, the wrapper raises the exception again, and the exception carries on out to the handler, which makes a response of it ([How an exception becomes a response](../handlers/exceptions.md)) (`django/core/handlers/exception.py:convert_exception_to_response`). When the Gazette's lost notices raise, `process_exception` is the last of Stamp's hooks to run:

```text recording=views
GET /notices/lost/: the decorated view raises
    BaseHandler._get_response
      the wrapper made from Stamp
        ...
        views.notices_lost(request)  raises LookupError
        Stamp.process_exception(LookupError)
    response_for_exception(request, LookupError)
      ...
      -> an HttpResponseServerError, status 500
      ...
```

> **Trap.** A middleware made into a decorator does not run as it does in the chain. Its `process_request` runs once the URL has been resolved, an instant before its `process_view`, where in the chain it runs before the resolver: the two hooks no longer differ in time, though only `process_view` is given the view and its arguments. A response from `process_request`, `process_view` or `process_exception` never reaches `process_response`, as in the chain it would. And when the view raises and `process_exception` gives no response, `process_response` is not called at all. In the chain the same middleware's `process_response` would have been given the error response, which `convert_exception_to_response` makes at the centre's boundary, inside every middleware; the wrapper stands inside that boundary, and sees only the exception (`django/utils/decorators.py:make_middleware_decorator`, `django/core/handlers/exception.py:convert_exception_to_response`).

## A template response is finished later

A view may return a `TemplateResponse`, which has not been rendered when the wrapper gets it back. The handler will render it, but only after the wrapper has returned. So for a response with a callable `render` the wrapper does two different things: it calls `process_template_response` straight away, and it registers `process_response` on the response as a callback to be run after rendering (`django/utils/decorators.py:make_middleware_decorator`, `django/template/response.py:SimpleTemplateResponse.add_post_render_callback`).

For the Gazette's page of notices, `process_response` runs outside the wrapper, under the handler's `SimpleTemplateResponse.render`, and is given the rendered content:

```text recording=views
GET /notices/page/: the decorated view returns a TemplateResponse
    BaseHandler._get_response
      the wrapper made from Stamp
        ...
        views.notices_page(request)  ->  a TemplateResponse, status 200, not rendered
        Stamp.process_template_response(is_rendered=False)
        SimpleTemplateResponse.add_post_render_callback
        -> a TemplateResponse, status 200, not rendered
      SimpleTemplateResponse.render
        Stamp.process_response(a 200, content='3 public notices\n')
        ...
```

Between the wrapper's return and the render, the handler runs the chain's own `process_template_response` hooks, on a site that has any ([The centre of the chain](../handlers/view.md#template-responses)) (`django/core/handlers/base.py:BaseHandler._get_response`). If the callback returns a response, `render` returns that one in place of the one it rendered, so `process_response` can still replace a response that was not yet rendered, as it could in the chain (`django/template/response.py:SimpleTemplateResponse.render`).

> **Why.** `process_response` is put off until the template has been rendered, as the comment above the callback says (`django/utils/decorators.py:make_middleware_decorator`). Called in the wrapper, it would be given a response whose content cannot yet be read, for a `SimpleTemplateResponse` refuses its `content` until it has been rendered ([`SimpleTemplateResponse` and `TemplateResponse`](../templates/responses.md#content-refused-before-a-render-contentnotrenderederror)) (`django/template/response.py:SimpleTemplateResponse.content`).

## A coroutine view

For a view that is a coroutine function the wrapper is a coroutine function too, and awaits the view. The hooks are a different matter. They are ordinary methods, and the wrapper calls them directly, as the synchronous wrapper does, with no `sync_to_async` between. Those the wrapper calls run wherever it is running (`django/utils/decorators.py:make_middleware_decorator`).

Requested through an `ASGIHandler`, the wrapper around the Gazette's notices from the wire, an `async def` function, is awaited on the event loop, and Stamp's hooks run there with it. Each line's tag names its thread, `[loop]` the event loop's and `[worker]` any other:

```text recording=views
GET /notices/wire/ through an ASGIHandler, with ROOT_URLCONF = 'gazette.desk' for this block: the decorator made from Stamp around an async def view
    BaseHandler._get_response_async  [loop]
      the wrapper made from Stamp  [loop]
        Stamp.process_request  [loop]
        Stamp.process_view(view=wire_notices)  [loop]
        desk.wire_notices(request)  [loop]  ->  an HttpResponse, status 200
        Stamp.process_response(a 200, content='notices from the wire')  [loop]
        ...
```

Through the same handler, a view that is not a coroutine function gets an ordinary wrapper, which the handler runs on a worker thread, and the hooks and the view run there with it (`django/core/handlers/base.py:BaseHandler._get_response_async`).

> **Trap.** Around a coroutine view, the hooks the wrapper calls are synchronous code running on an event loop: the server's, under an `ASGIHandler`, and under a `WSGIHandler` the one in which `async_to_sync` runs the wrapper (`django/core/handlers/base.py:BaseHandler._get_response`). A hook that waits on the network holds up the loop while it waits, as `cache_page`'s hooks do on a cache kept on another server (`django/middleware/cache.py:FetchFromCacheMiddleware.process_request`). A hook that reaches the database fails outright, since Django refuses a query from a thread whose event loop is running: `cache_page` with the database cache, or `csrf_protect` reading the request's session from the database under `settings.CSRF_USE_SESSIONS`, raises `SynchronousOnlyOperation`, and the client gets a 500 (`django/utils/asyncio.py:async_unsafe`). Around a view that is not a coroutine function the hooks run on a thread with no event loop, under either handler, and the same two decorators answer with a 200.

## On a method: a middleware for every request

One instance for each decorated view is the arrangement when the decorator is applied to a function. `method_decorator` changes it. It applies its decorator again at every call, to a partial of the method bound to the instance that serves the request ([Decorating a class: `method_decorator`](method-decorator.md)), and to apply a decorator of this kind is to construct a middleware. The Gazette's crossword view is a class given stamped on its `dispatch` by `method_decorator`, and every request for it constructs a Stamp of its own, inside the wrapper that `method_decorator` made, around a partial of the bound `dispatch`:

```text recording=views
GET /crossword/, twice: method_decorator applies its decorator again at every call
        ...
        the wrapper method_decorator made
          the decorator made from Stamp is given a partial around the bound method View.dispatch
            Stamp.__init__(get_response=a partial around the bound method View.dispatch)
            ...
```

The instance serves that request and no other. One more is made when the class is defined, around the stand-in that `method_decorator` decorates so that it can copy the decorator's marks (`django/utils/decorators.py:_update_method_wrapper`). Some of Django's class-based views are decorated in this way: `LoginView` has `csrf_protect` among the decorators that `method_decorator` puts on its `dispatch`, so each request to a login page constructs a `CsrfViewMiddleware` (`django/contrib/auth/views.py:LoginView`).

## `csrf_protect` and `CsrfViewMiddleware` together

`csrf_protect` can be used on a site that also installs `CsrfViewMiddleware`, and using both is harmless and efficient (`django/views/decorators/csrf.py`). For a `"POST"` with a valid token, the chain's instance checks the token in its `process_view` and marks the request accepted; the decorator's `process_view` then returns at once, and the decorator's `process_response`, the first of the two to run, sets the cookie the view asked for, so that the chain's sets nothing. A `"POST"` without a token is refused by the chain's instance with a 403, and the decorator's wrapper is never called. How the request is marked, and how the cookie is kept from being set twice, are the middleware's ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md), [The CSRF secret and its token](../security/csrf-token.md)) (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`, `django/middleware/csrf.py:CsrfViewMiddleware.process_response`).
