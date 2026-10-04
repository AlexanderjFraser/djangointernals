---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The centre of the chain

What `BaseHandler._get_response` does once a request has passed every middleware: it resolves the URL to a view, offers the view to the view middleware, calls it, and renders the response if it is a template still waiting to be rendered.

The innermost layer of the chain is not a middleware. It is a method of the handler, `BaseHandler._get_response`: in its docstring's words, everything that happens inside the request and response middleware (`django/core/handlers/base.py:BaseHandler._get_response`). This section follows it from top to bottom. A request can leave it early at almost every step.

## Resolving the URL

`BaseHandler.resolve_request` picks a resolver, asks it to match the request's `path_info`, which is the path without the script prefix, and stores the answer on the request (`django/core/handlers/base.py:BaseHandler.resolve_request`).

The resolver is normally the one for `settings.ROOT_URLCONF`, which `get_resolver` makes on first use and keeps. A middleware can route a single request by a different URLconf by setting an attribute named `"urlconf"` on the request: `resolve_request` looks for that attribute, and when it is there it makes the named URLconf the current one (for the thread, or under ASGI for the task) and resolves with it.

The match is a `ResolverMatch`. It is kept as `HttpRequest.resolver_match`, where the view and anything after it can read it, and it unpacks into the three things the handler needs: the view, its positional arguments and its keyword arguments.

When nothing matches, the resolver raises `Resolver404`, which is a subclass of `Http404` (`django/urls/exceptions.py:Resolver404`). No view has been chosen, so nothing described below runs. The exception leaves `_get_response` and is turned into a 404 response by the wrapper around the centre. The middleware never see the exception, only the response on its way out:

```text
WSGI, GET /nowhere/: no URL pattern matches
    signal: request_started
    A.process_request
    B.process_request
    C.process_request
    C.process_response(404)
    B.process_response(404)
    A.process_response(404)
    start_response("404 Not Found", headers)
    the server closes the response
    signal: request_finished
```

## The view middleware

With a view in hand, the handler calls each method in `BaseHandler._view_middleware`: the `process_view` hooks, in the order of the setting. Each is given the request, the view, and the arguments the view is about to be called with. If one returns a response, the loop stops and the view is not called; the response goes on through the rest of this method as if the view had returned it.

This hook exists because of what it is told. A middleware's `process_request` runs before the handler has resolved the URL, and is not told which view the request is for. `process_view` runs after, and is handed the view itself. `CsrfViewMiddleware` does its checking here for that reason: whether a view is exempt is an attribute of the view (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`).

## Calling the view

The view may be wrapped before it is called.

`BaseHandler.make_view_atomic` goes through the configured databases, and for each one whose settings have `"ATOMIC_REQUESTS"` true it wraps the view in `django.db.transaction.atomic` for that database, unless the view was marked to be left out. The transaction is around the view and nothing else. The middleware run outside it, and so does the rendering of a template response, which comes later in this method. An async view cannot be wrapped this way: the method raises `RuntimeError` if it finds one while a database asks for atomic requests (`django/core/handlers/base.py:BaseHandler.make_view_atomic`).

If the view is a coroutine function and the handler is running synchronously, the view is then wrapped in `async_to_sync`, so that it can be called like a function.

Then the view is called, inside a `try`. If it raises an `Exception`, the handler passes the exception to `BaseHandler.process_exception_by_middleware`, which calls the `process_exception` hooks, innermost middleware first, until one returns a response (`django/core/handlers/base.py:BaseHandler.process_exception_by_middleware`). If one does, that response replaces the view's and the request carries on. If none does, the exception is raised again and leaves the centre, to be turned into a response by the wrapper around it, as [the next section](exceptions.md) describes.

## The view must have returned a response

`BaseHandler.check_response` then refuses two things a view can return by mistake: `None`, and a coroutine that was never awaited. Each raises a `ValueError` whose message names the view (`django/core/handlers/base.py:BaseHandler.check_response`). The first is a message most Django developers have met:

```text
The view app.views.detail didn't return an HttpResponse object. It returned None instead.
```

The check stands after the `try` that surrounds the view, not inside it. So this error is not offered to the `process_exception` hooks: it goes straight out of the centre and becomes a 500.

## Template responses

A view may return a response that has not been rendered yet: a `TemplateResponse` holds a template and a context, and makes its content only when its `render` method is called. The handler tests for exactly that, a response with a callable `render`, and has more to do with such a response before it leaves the centre.

It is first passed through each method in `BaseHandler._template_response_middleware`, the `process_template_response` hooks, innermost first. A hook may change the template or the context, or return a different response, which must itself have a `render` method. Whatever it returns is checked as the view's result was. Then the handler calls `render`. An exception raised while rendering gets the same treatment as one raised by the view: the exception hooks first, and out of the centre if none of them answers.

```text
WSGI, GET /template/: a view that returns a TemplateResponse
    signal: request_started
    A.process_request
    B.process_request
    C.process_request
    A.process_view
    B.process_view
    C.process_view
    the view, returning a TemplateResponse
    C.process_template_response
    B.process_template_response
    A.process_template_response
    C.process_response(200)
    B.process_response(200)
    A.process_response(200)
    start_response("200 OK", headers)
    the server closes the response
    signal: request_finished
```

This is the reason to return a `TemplateResponse` and not a rendered `HttpResponse`: the rendering is deferred until the middleware have had the chance to alter what is rendered.

## The asynchronous twin

`BaseHandler._get_response_async` is the same method written as a coroutine, and an `ASGIHandler` puts it at the centre of its chain. The steps are the same, and each adaptation runs the other way (`django/core/handlers/base.py:BaseHandler._get_response_async`):

- A view that is *not* a coroutine function is wrapped in `sync_to_async`, so that it runs in a thread and the event loop is not blocked.
- The view middleware and the template response middleware are awaited. `load_middleware` adapted them to the handler's mode when it filed them.
- The exception hooks are synchronous whatever the mode, so `process_exception_by_middleware` is itself called through `sync_to_async`.
- `render` is awaited if it is a coroutine function and called through `sync_to_async` if it is not.
- As a last guard, a response that is still a coroutine when the method is about to return raises `RuntimeError`.

URL resolving is not adapted at all. `resolve_request` is called directly in both methods, so under ASGI the URL is matched on the event loop's thread.
