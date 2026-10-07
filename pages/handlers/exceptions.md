---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# How an exception becomes a response

What stands between an exception raised during a request and the response the client is sent: `convert_exception_to_response`, which is wrapped around every layer of the chain, and `response_for_exception`, which chooses what answers.

An exception raised while Django serves a request rarely reaches the server. Somewhere on its way up it is caught, and a response is returned where it would have passed. Two mechanisms do this, and they are easy to confuse: the `process_exception` hooks, which get a first look at what a view raises, and the wrapper around each layer, which catches what is left.

## The wrapper around every layer

`convert_exception_to_response` takes a callable and returns a function that calls it inside a `try`. If the call raises an `Exception`, the function returns what `response_for_exception` makes of the request and the exception (`django/core/handlers/exception.py:convert_exception_to_response`).

`BaseHandler.load_middleware` applies it to the centre of the chain and to every middleware as it builds the chain, so each layer has a wrapper of its own. The point of wrapping each one is that no middleware leaks an exception to the next: the layer outside can rely on being handed a response. The effect shows when a middleware in the middle of the chain raises:

```text recording=handlers
WSGI, GET /raise-in-B/: B.process_request raises RuntimeError
    signal: request_started
    A.process_request
    B.process_request
    signal: got_request_exception
    A.process_response(500)
    start_response("500 Internal Server Error", headers)
    the server closes the response
    signal: request_finished
```

C and the view never ran. A knows nothing of the exception: the wrapper around B turned it into a 500 response, and A's `process_response` received that response as it would any other. Had the chain been wrapped once, at the outside, A's work on the way out would have been skipped.

When the callable it wraps is a coroutine function, the wrapper is a coroutine too. It awaits the call, and it runs `response_for_exception` in a thread through `sync_to_async`, because everything that function does is synchronous.

## Two chances for a view's exception

An exception raised by a view meets the `process_exception` hooks first. They belong to the centre of the chain and are described with it in [The centre of the chain](view.md): each is offered the exception, innermost middleware first, and the first to return a response ends the matter. Only when none answers is the exception raised again and caught by the wrapper around the centre.

```text recording=handlers
WSGI, GET /broken/: the view raises ValueError
    signal: request_started
    A.process_request
    B.process_request
    C.process_request
    A.process_view
    B.process_view
    C.process_view
    the view, raising ValueError
    C.process_exception(ValueError)
    B.process_exception(ValueError)
    A.process_exception(ValueError)
    signal: got_request_exception
    C.process_response(500)
    B.process_response(500)
    A.process_response(500)
    start_response("500 Internal Server Error", headers)
    the server closes the response
    signal: request_finished
```

The hooks see only what a view raises, or what rendering a template response raises. An exception from a middleware, a URL that matches nothing, a view that returns `None`: none of these is offered to them, and each goes directly to a wrapper.

## Which exception becomes which response

`response_for_exception` is a run of `isinstance` tests, tried in the order of the rows below, and the first that matches decides what answers. An **error view** in the table is one of four views that a project can replace; the next heading describes them (`django/core/handlers/exception.py:response_for_exception`).

| the exception is a | answered by | status |
|---|---|---|
| `Http404` | the debug page of `technical_404_response` when `settings.DEBUG` is true; otherwise the 404 error view | 404 |
| `PermissionDenied` | the 403 error view | 403 |
| `MultiPartParserError` | the 400 error view | 400 |
| `BadRequest` | the debug page of `technical_500_response` when `settings.DEBUG` is true; otherwise the 400 error view | 400 |
| `SuspiciousOperation` | the same as for `BadRequest` | 400 |
| anything else | `handle_uncaught_exception` | 500 |

*What `response_for_exception` returns, by the class of the exception.*

The status in the last column is the one Django's own error views and debug pages return. `response_for_exception` chooses which error view is asked, and the status is that view's to set: a project's 403 view that returns an ordinary response sends a 200. The debug 404 page has a case of the same kind. For a project whose URLconf has no patterns yet, it is Django's welcome page, and its status is 200.

An unrecognised exception is announced. Before the last row is handled the `got_request_exception` signal is sent, as in the recording above. The recognised exceptions send nothing, unless the error view that answers one itself raises.

A `SuspiciousOperation` is logged apart from the rest: at the error level, to a logger named for the exception's class under `"django.security"`, so that security events can be routed separately from ordinary request errors.

Three suspicious operations, `RequestDataTooBig`, `TooManyFieldsSent` and `TooManyFilesSent`, are raised while the request's own data is being parsed: its body, and for the second its query string as well. For these the function first calls `HttpRequest._mark_post_parse_error`, so that the error view can touch the request's form data without setting off the same exception again.

An error view may return a template response that has not been rendered. It will never pass the step of the centre that renders such responses, so `response_for_exception` renders it before returning it.

## The error views

An error view is found by `URLResolver.resolve_error_handler`. It looks in the current URLconf module for a variable named `handler404` (or `handler403`, `handler400`, `handler500`), and when the module has none it takes the default of the same name from `django/conf/urls/__init__.py`, which are the views in `django/views/defaults.py` ([The error views](../views/errors.md)) (`django/urls/resolvers.py:URLResolver.resolve_error_handler`).

`get_exception_response` calls the error view with the request and the exception. If the error view itself raises, the failure is treated as an unrecognised exception: the signal is sent and `handle_uncaught_exception` takes over. A broken 404 page thus becomes a 500 (`django/core/handlers/exception.py:get_exception_response`).

## The last resort

`handle_uncaught_exception` makes the response for everything unrecognised (`django/core/handlers/exception.py:handle_uncaught_exception`).

1. If `settings.DEBUG_PROPAGATE_EXCEPTIONS` is true, it raises the exception again.
2. Otherwise, if `settings.DEBUG` is true, it returns `technical_500_response`: the debug page with the traceback ([The debug pages and `ExceptionReporter`](../views/debug.md)).
3. Otherwise it calls the 500 error view, with the request alone.

## What does reach the server

Not everything is caught. These pass out of the handler to the server.

Anything that is not an `Exception`. The wrappers catch `Exception` and nothing wider, so `KeyboardInterrupt` and `SystemExit` go through every layer untouched.

An unrecognised exception, when `settings.DEBUG_PROPAGATE_EXCEPTIONS` is true. The wrapper that catches it raises it again; the wrapper around the next layer catches it, and does the same; and so on outwards. Each sends the signal as it does so, and no middleware's `process_response` runs. This one is deliberate.

Anything raised before the chain is entered. The wrappers are part of the chain and cannot catch what happens outside it: a malformed `Content-Type` header, for one, raises `BadRequest` while the request object is being made (`django/http/request.py:HttpRequest._set_content_type_params`).

A failure of the conversion itself. The plainest case is a 500 error view that raises. Nothing is left to turn that into a response: each wrapper in turn tries the 500 error view again, and when the outermost has failed as well, the exception leaves the handler:

```text recording=handlers
WSGI, GET /broken/: the view raises ValueError, and the 500 error view raises too
    signal: request_started
    A.process_request
    B.process_request
    C.process_request
    A.process_view
    B.process_view
    C.process_view
    the view, raising ValueError
    C.process_exception(ValueError)
    B.process_exception(ValueError)
    A.process_exception(ValueError)
    signal: got_request_exception
    the 500 error view, raising LookupError
    signal: got_request_exception
    the 500 error view, raising LookupError
    signal: got_request_exception
    the 500 error view, raising LookupError
    signal: got_request_exception
    the 500 error view, raising LookupError
    the handler raises LookupError to the server
```

The error view ran four times: once for the centre and once for each of the three middleware.

## A response is logged once

Responses with a status of 400 or more are logged by `log_response`, and several places call it: most branches of `response_for_exception`, with the exception attached, and `BaseHandler.get_response` for every such response that comes out of the chain. To keep one failure from being logged twice, `log_response` marks each response it logs and returns at once when it meets a marked one. The 500 logged with its traceback at the wrapper is not logged again on the way out (`django/utils/log.py:log_response`).

> **A method nothing calls.** `ASGIHandler.handle_uncaught_exception` is described by its docstring as a last-chance handler, and it calls a method of the same name on its base class. `BaseHandler` declares no such method, and no code in `django/` calls this one: the function that does the work is the module-level `handle_uncaught_exception` above. Changing the method changes nothing (`django/core/handlers/asgi.py:ASGIHandler.handle_uncaught_exception`).
