---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# How an exception becomes a response

`convert_exception_to_response`, wrapped around every layer of the middleware chain, ordinarily turns an exception raised inside a layer into the response `response_for_exception` chooses. A view's exception meets the `process_exception` hooks first; for one no hook answers and Django does not recognise, `got_request_exception` is sent and `handle_uncaught_exception` answers.

An exception raised while Django serves a request rarely reaches the server. Two mechanisms catch it on its way up, and they are easy to confuse: the `process_exception` hooks, which get a first look at what a view raises, and the wrapper around each layer, which turns what is left into a response at the boundary of the layer that raised it, so that only the layers outside see it. In the figure, A, B and C are three middleware that write down each hook as Django calls it: follow each exception to the boundary that catches it, and the 500 out from there:

```text figure=exception-paths
MIDDLEWARE = [A, B, C]; A, B, C and BaseHandler._get_response, each in its wrapper

the view raises ValueError:
    offered to the process_exception hooks of C, B and A; none answers
    caught at the centre's boundary; the 500 goes out through C, B and A

B.process_request raises RuntimeError:
    caught at B's boundary; C and the centre do not run; the 500 goes out through A

C.process_response raises RuntimeError:
    caught at C's boundary; the 500 goes out through B and A

past A's boundary, to the server:
    an exception that is not an Exception
    an unrecognised exception, with DEBUG_PROPAGATE_EXCEPTIONS = True
    a 500 error view that raises an unrecognised exception
```

*A, B and C nested around the centre, each box's edge the boundary where its wrapper catches what is raised inside. An accented arrow runs from a raise to the boundary that catches it, a plain one carries the 500 out; what passes A's edge to the server is beside it.*

## The wrapper around every layer

`convert_exception_to_response` takes a callable and returns a function that calls it inside a `try` and, if it raises an `Exception`, returns what `response_for_exception` makes of the request and the exception (`django/core/handlers/exception.py:convert_exception_to_response`). `BaseHandler.load_middleware` applies it to the centre and to every middleware as it builds the chain (`django/core/handlers/base.py:BaseHandler.load_middleware`). Around a coroutine function the wrapper is a coroutine function too, and runs `response_for_exception` in a thread through `sync_to_async`, since that function is synchronous throughout.

When B's `process_request` raises, look for what is missing after it: C, the centre, and B's own `process_response`. Only A's runs, handed a 500:

```text recording=handlers
WSGI, GET /raise-in-B/: B.process_request raises RuntimeError
...
    A.process_request
    B.process_request
    signal: got_request_exception
    A.process_response(500)
    ...
```

A knows nothing of the exception: the wrapper around B made it a 500 response, which A's `process_response` received as it would any other.

An exception raised on the way out is caught the same way. Watch the status B and A are handed once C's `process_response` raises:

```text recording=handlers
WSGI, GET /plain/: C.process_response raises RuntimeError
...
    the view
    C.process_response(200), raising RuntimeError
    signal: got_request_exception
    B.process_response(500)
    A.process_response(500)
    ...
```

B and A are not skipped: each does its work on the way out, on the 500 the wrapper around C made in place of the view's 200.

> **Why.** A wrapper on every layer spares each middleware from handling what the layers inside it raise: a middleware is meant to get a response from the layer inside it, not an exception, as DEP 5, which brought in `settings.MIDDLEWARE`, laid down (`django/core/handlers/exception.py:convert_exception_to_response`, `deps:final/0005-improved-middleware.rst`). Had the chain been wrapped once, at the outside, the layers outside the one that raised would have lost their work on the way out.

## Two chances for a view's exception

An exception raised by a view meets the `process_exception` hooks first. The centre calls them ([The centre of the chain](view.md)): each is offered the exception, innermost middleware first, and the first to return a response ends the matter (`django/core/handlers/base.py:BaseHandler.process_exception_by_middleware`). If C's hook answers, B's and A's are never called, and no signal is sent:

```text recording=handlers
WSGI, GET /broken/: the view raises ValueError, and C.process_exception returns a response
...
    the view, raising ValueError
    C.process_exception(ValueError), returning a response
    C.process_response(200)
    B.process_response(200)
    A.process_response(200)
    ...
```

Only when no hook answers is the exception raised again, to be caught by the wrapper around the centre. Here all three decline it, and `got_request_exception` is sent before the 500 goes out through every layer:

```text recording=handlers
WSGI, GET /broken/: the view raises ValueError
...
    the view, raising ValueError
    C.process_exception(ValueError)
    B.process_exception(ValueError)
    A.process_exception(ValueError)
    signal: got_request_exception
    C.process_response(500)
    B.process_response(500)
    A.process_response(500)
    ...
```

The hooks see only what a view, or the rendering of a template response, raises; anything else raised in the chain goes directly to a wrapper (`django/core/handlers/base.py:BaseHandler._get_response`).

## Which exception becomes which response

`response_for_exception` is a run of `isinstance` tests, tried in the order of the rows below, and the first that matches decides what answers. An **error view** in the table is one of four views that a project can replace; the next heading describes them (`django/core/handlers/exception.py:response_for_exception`).

| the exception is a | answered by | status |
|---|---|---|
| `Http404` | with `settings.DEBUG`, the debug page of `technical_404_response`; otherwise the 404 error view | 404 |
| `PermissionDenied` | the 403 error view | 403 |
| `MultiPartParserError` | the 400 error view | 400 |
| `BadRequest` | with `settings.DEBUG`, the debug page of `technical_500_response`; otherwise the 400 error view | 400 |
| `SuspiciousOperation` | the same as for `BadRequest` | 400 |
| anything else | `handle_uncaught_exception` | 500 |

*What `response_for_exception` returns, by the class of the exception.*

The status in the last column is the one Django's own error views return, and ordinarily the debug pages ([The debug pages and `ExceptionReporter`](../views/debug.md#the-404-page-technical_404_response)); a replacement may set another ([The error views](../views/errors.md#a-custom-error-view-handler404-and-its-kin)). Three of the suspicious operations, `RequestDataTooBig`, `TooManyFieldsSent` and `TooManyFilesSent`, enforce the limits on the request's data ([The body: `body`, `POST` and `FILES`](../http/body.md#the-limits)). For these `response_for_exception` first calls `HttpRequest._mark_post_parse_error`, which gives the request an empty `POST` and an empty `FILES`, so that the error view or the debug page can read them without parsing the data again and raising the same exception (`django/http/request.py:HttpRequest._mark_post_parse_error`).

Besides choosing, `response_for_exception` announces an exception it does not recognise, logs, and renders a template response. The announcement is `got_request_exception`, sent before `handle_uncaught_exception` is called; a recognised exception sends nothing, unless the error view that answers it raises. `response_for_exception` logs the response through `log_response`, with the exception attached, for every class but `Http404`, and a response is logged once ([Logging](../startup/logging.md#log_response-a-response-is-logged-once)) (`django/utils/log.py:log_response`). A `SuspiciousOperation` goes to a logger of its own, at the error level: one under `"django.security"` named for its class, so that security events can be routed apart from request errors. An error view's template response, if not yet rendered, never passes the centre's rendering step, so `response_for_exception` renders it.

## The error views

An error view is found by `URLResolver.resolve_error_handler`, in the current URLconf or among Django's defaults ([The error views](../views/errors.md#found-through-the-urlconf-called-like-a-view)) (`django/urls/resolvers.py:URLResolver.resolve_error_handler`). `get_exception_response` calls it with the request and the exception. If the error view itself raises, the failure is treated as an unrecognised exception, the signal sent and `handle_uncaught_exception` taking over: a broken 404 page becomes a 500 (`django/core/handlers/exception.py:get_exception_response`).

## `handle_uncaught_exception`, the last resort

`handle_uncaught_exception` makes the response for everything unrecognised. If `settings.DEBUG_PROPAGATE_EXCEPTIONS` is true it raises the exception again; otherwise, if `settings.DEBUG` is true, it returns `technical_500_response`, the debug page with the traceback ([The debug pages and `ExceptionReporter`](../views/debug.md)); otherwise it calls the 500 error view, with the request alone (`django/core/handlers/exception.py:handle_uncaught_exception`).

## What does reach the server

The wrappers catch `Exception` and nothing wider, so an exception that is not an `Exception`, such as `KeyboardInterrupt` or `SystemExit`, goes through every layer untouched.

An unrecognised exception is let through deliberately when `settings.DEBUG_PROPAGATE_EXCEPTIONS` is true: each wrapper sends the signal and raises the exception again, for the next to catch. After the hooks come the signals of the four wrappers, the centre's and the three middleware's, and not one `process_response`:

```text recording=handlers
WSGI, GET /broken/: the view raises ValueError, with DEBUG_PROPAGATE_EXCEPTIONS = True
...
    A.process_exception(ValueError)
    signal: got_request_exception
    signal: got_request_exception
    signal: got_request_exception
    signal: got_request_exception
    the handler raises ValueError to the server
```

An exception raised before the chain is entered can reach the server too, since the wrappers, part of the chain, cannot catch what happens outside it: a malformed `Content-Type` header, for one, raises `BadRequest` while the request object is being made (`django/http/request.py:HttpRequest._set_content_type_params`).

Last, the conversion itself can fail, most plainly when the 500 error view raises an unrecognised exception. Nothing is left to turn that into a response: each wrapper in turn tries the 500 error view again, after the signal, and when the outermost has failed too, the exception leaves the handler:

```text recording=handlers
WSGI, GET /broken/: the view raises ValueError, and the 500 error view raises too
...
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

The error view ran four times: once for the centre, once for each middleware.

The debug page can fail too, on the request's data. Under `settings.DEBUG` it reads `GET` and `POST` for its tables, and in two of the cases where the exception was raised by a read of one of them (a query string over the field limit read through `GET`, an ordinary form in a charset other than UTF-8 read through `POST`), the page's read raises it again, and it leaves the handler (`django/views/debug.py:ExceptionReporter.get_traceback_data`).
