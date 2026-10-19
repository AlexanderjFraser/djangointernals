---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The centre of the chain

`BaseHandler._get_response` is the centre of the chain: `BaseHandler.resolve_request` finds the view, which is offered to the `process_view` hooks and called; `BaseHandler.check_response` refuses `None` or an unawaited coroutine in place of a response; and a template response is rendered after the `process_template_response` hooks. `BaseHandler._get_response_async` is its twin under ASGI.

The innermost layer of the chain is not a middleware but a method of the handler: in its docstring's words, everything that happens inside the request and response middleware (`django/core/handlers/base.py:BaseHandler._get_response`). A request can leave it early at almost every step: in the figure, look to the right of a station for its way out. A, B and C, there and in the blocks below, are three middleware that write down each hook as Django calls it.

```text figure=the-stations
MIDDLEWARE = [A, B, C]
on the right, one rail: out of the centre, to the wrapper around it
a dashed arrow, - - ->, is a hook's response going on down the column

resolve_request  ->  Resolver404  ->  the rail
the process_view hooks: A, B, C
    one answers: the view is skipped  - - ->  its response rejoins below the call
make_view_atomic, then async_to_sync for an async view
the call of the view  ->  it raises: the process_exception hooks: C, B, A
    one answers  - - ->  its response rejoins below the call
    none answers: raised again  ->  the rail
check_response  ->  None or an unawaited coroutine: ValueError, past the process_exception hooks  ->  the rail
only a response with a callable render:
the process_template_response hooks: C, B, A, then render  ->  render raises: the process_exception hooks: C, B, A
    one answers  - - ->  its response is returned
    none answers: raised again  ->  the rail
the response, returned to the wrapper around the centre
```

*The stations of `BaseHandler._get_response`, top to bottom. An arrow to the rail is an exception leaving the centre, for the wrapper around it to turn into a response; the boxes beside the call and `render` are the `process_exception` hooks; the three dashed arrows, from a `process_view` hook and from the exception hooks, are a hook's response going on down the column, not to the rail.*

## Resolving the URL

`BaseHandler.resolve_request` picks a resolver, asks it to match the request's `path_info`, which is the path without the script prefix, and stores the answer, a `ResolverMatch`, on the request as `HttpRequest.resolver_match`; it unpacks into the view and its positional and keyword arguments (`django/core/handlers/base.py:BaseHandler.resolve_request`) ([Resolving a path](../urls/resolving.md#a-resolvermatch-attribute-by-attribute)). The resolver is the one for `settings.ROOT_URLCONF` unless the request has an attribute named `"urlconf"` other than `None`, which a middleware may set: that URLconf is then made the current one ([The script prefix, the current URLconf and the caches](../urls/state.md#the-current-urlconf)).

When nothing matches, the resolver raises `Resolver404`, a subclass of `Http404` (`django/urls/exceptions.py:Resolver404`). No view has been chosen, so nothing below runs: the exception leaves `_get_response`, and the wrapper around the centre turns it into a 404. Between C's `process_request` and C's `process_response` no other hook stands; the middleware never see the exception, only the response on its way out:

```text recording=handlers
WSGI, GET /nowhere/: no URL pattern matches
...
    A.process_request
    B.process_request
    C.process_request
    C.process_response(404)
    B.process_response(404)
    A.process_response(404)
    ...
```

## The `process_view` hooks

With a view in hand, the handler calls each method in `BaseHandler._view_middleware`: the `process_view` hooks, in the order of the setting. Each is given the request, the view, and the arguments the view is about to be called with. If one returns a response, the loop stops and the view is not called; the response goes on through the rest of this method as if the view had returned it (`django/core/handlers/base.py:BaseHandler._get_response`).

When B's hook answers, C's hook and the view never run, yet C's `process_response` is the first to receive the response, made inside the centre, which C surrounds:

```text recording=handlers
WSGI, GET /plain/: B.process_view returns a response
...
    A.process_view
    B.process_view, returning a response
    C.process_response(200)
    B.process_response(200)
    A.process_response(200)
    ...
```

> **Why.** The hook exists because of what it is told. A middleware's `process_request` runs before the handler has resolved the URL, and is not told which view the request is for; `process_view` runs after, just before the view is called, and is handed the view itself (`docs/topics/http/middleware.txt`). `CsrfViewMiddleware` does its checking here for that reason: whether a view is exempt is an attribute of the view ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`).

## Calling the view

Before the call, `BaseHandler.make_view_atomic` wraps the view in `django.db.transaction.atomic` for each database whose settings have `"ATOMIC_REQUESTS"` true, unless the view was marked to be left out, as [Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#atomic_requests-and-non_atomic_requests) shows; an async view it refuses with `RuntimeError` instead of wrapping it (`django/core/handlers/base.py:BaseHandler.make_view_atomic`). Then a view that is a coroutine function is wrapped in `async_to_sync`, so that the synchronous handler can call it.

> **Trap.** The transaction is around the view and nothing else: the middleware run outside it, and so does the rendering of a template response, later in this method (`django/core/handlers/base.py:BaseHandler._get_response`). The documentation says so (`docs/topics/db/transactions.txt`).

Then the view is called, inside a `try`. An `Exception` it raises is offered to the `process_exception` hooks, innermost first, by `BaseHandler.process_exception_by_middleware`, until one answers: its response replaces the view's; if none answers, the exception is raised again and leaves the centre for the wrapper around it ([How an exception becomes a response](exceptions.md)) (`django/core/handlers/base.py:BaseHandler.process_exception_by_middleware`).

## `check_response`: the view must return a response

`BaseHandler.check_response` then refuses two things a view can return by mistake: `None`, and a coroutine that was never awaited. Each raises a `ValueError` whose message names the view (`django/core/handlers/base.py:BaseHandler.check_response`) ([What the handler asks of a view](../views/callable.md#what-a-view-may-return)).

No `process_exception` hook follows a view that returns `None`: the signal comes at once, and the 500 goes out through every layer:

```text recording=handlers
WSGI, GET /nothing/: the view returns None
...
    the view, returning None
    signal: got_request_exception
    C.process_response(500)
    B.process_response(500)
    A.process_response(500)
    ...
```

> **Trap.** `check_response` stands after the `try` that surrounds the view, not inside it, so its `ValueError` is never offered to the `process_exception` hooks: it leaves the centre at once, and the wrapper around the centre sends `got_request_exception` and ordinarily makes a 500 (`django/core/handlers/base.py:BaseHandler._get_response`, `django/core/handlers/exception.py:response_for_exception`).

## Template responses

A view may return a response that has not been rendered yet: a `TemplateResponse` holds a template and a context, and makes its content only when its `render` method is called. The handler tests for a response with a callable `render`, and has more to do with one.

It is first passed through each method in `BaseHandler._template_response_middleware`, the `process_template_response` hooks, innermost first. A hook may change the template or the context, or return a different response; whatever it returns is checked as the view's result was, and given to the next hook. Then the handler calls `render` (`django/core/handlers/base.py:BaseHandler._get_response`). The three hooks stand between the view's line and the first `process_response`, inside the centre:

```text recording=handlers
WSGI, GET /template/: a view that returns a TemplateResponse
...
    A.process_view
    B.process_view
    C.process_view
    the view, returning a TemplateResponse
    C.process_template_response
    B.process_template_response
    A.process_template_response
    C.process_response(200)
    ...
```

Rendering last is a reason to return a `TemplateResponse` and not a rendered `HttpResponse`: the middleware can still alter what is rendered ([`SimpleTemplateResponse` and `TemplateResponse`](../templates/responses.md)).

An exception raised while rendering is offered to the `process_exception` hooks too: `render` is called inside a `try` of its own, a response from one of them is returned as it is, and if none answers the exception is raised again out of the centre (`django/core/handlers/base.py:BaseHandler._get_response`). The documentation asks a hook to return a response with a `render` method (`docs/topics/http/middleware.txt`), but nothing checks: `render` is called on whatever the last hook returned. A plain `HttpResponse` from B's hook is still given to A's, and its missing `render` raises `AttributeError`, which takes that path:

```text recording=handlers
WSGI, GET /template/: B.process_template_response returns an HttpResponse, which has no render method
...
    B.process_template_response, returning an HttpResponse
    A.process_template_response
    C.process_exception(AttributeError)
    B.process_exception(AttributeError)
    A.process_exception(AttributeError)
    signal: got_request_exception
    ...
```

## `_get_response_async`, the asynchronous twin

`BaseHandler._get_response_async` is the twin of `_get_response`, written as a coroutine, at the centre of an `ASGIHandler`'s chain. Its adaptations run the other way from `_get_response`'s, from the event loop into a thread (`django/core/handlers/base.py:BaseHandler._get_response_async`):

- A view that is *not* a coroutine function is wrapped in `sync_to_async`, so that it runs in a thread, off the event loop.
- The `process_view` and `process_template_response` hooks are awaited, as they were adapted when filed, and the exception hooks, filed synchronous, are reached by calling `process_exception_by_middleware` through `sync_to_async` ([Building the middleware chain](chain.md#the-three-lists-of-hooks)).
- `render` is awaited if it is a coroutine function, and called through `sync_to_async` if not.

URL resolving is not adapted at all: `resolve_request` is called directly in both methods, so under ASGI the URL is resolved on the event loop's thread ([Sync and async in one chain](async.md#what-the-arrangements-cost)).
