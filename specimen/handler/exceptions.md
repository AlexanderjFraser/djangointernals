---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: outline
owns: "`convert_exception_to_response`, `response_for_exception`"
---

# How an exception becomes a response

What stands between an exception raised under a handler and the response a client is sent?

`convert_exception_to_response` returns a function that calls what it wraps inside a `try`; when that raises an `Exception`, the function calls `response_for_exception` with the request and the exception and returns what it returns, going through `sync_to_async` when what it wraps is a coroutine function (`django/core/handlers/exception.py:convert_exception_to_response`). `BaseHandler.load_middleware` calls it in two places: before its loop, on the handler's own `BaseHandler._get_response` or `BaseHandler._get_response_async`, and inside the loop, on the middleware instance just made (`django/core/handlers/base.py:BaseHandler.load_middleware`).

## What does `convert_exception_to_response` wrap, and how often?

- To assert: the two call sites in `BaseHandler.load_middleware`, and what each wraps.
- Figure: the chain as it stands after the loop, each layer inside its own wrapper. Drawn from a recording of the specimen project's chain, not from reading.

## Which exception becomes which response?

- To assert: the branches of `response_for_exception`, in the order the function tries them, as a table: the exception, the status, and what makes the response.
- To assert: the cases in which the wrapper returns no response. One of them: `handle_uncaught_exception` raises again when `settings.DEBUG_PROPAGATE_EXCEPTIONS` is true (`django/core/handlers/exception.py:handle_uncaught_exception`), and its default is `False` (`django/conf/global_settings.py`). To find: what the wrapper's `except` clause does not catch, and what is raised while a response is being made.

## Why is each middleware wrapped, and not the chain once?

- Why: the docstring of `convert_exception_to_response` gives a reason for applying it to all middleware. Find the ticket it came with.
- To check: the same docstring says all exceptions are converted. Set that beside the cases above.
