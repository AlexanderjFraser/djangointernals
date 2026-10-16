---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in handlers, requests, URLs and views

The changes from Django 5.0 to this commit in the request cycle: Django's middleware made synchronous under ASGI, `MiddlewareMixin` moved and error responses made on the request's thread (6.2); the ASGI request's disconnect and cookies; decorators that keep a coroutine view a coroutine function; `JsonResponse` without safe; the multipart parser's strict Base64; and smaller changes to requests, responses, redirects, `reverse` and converters.

Most of these changes are additions. The largest to a running site is 6.2's, to the mode Django's own middleware runs in under ASGI.

## Django's middleware under ASGI

Before 6.2 Django's middleware classes inherited `async_capable = True` from `MiddlewareMixin`, so under ASGI a chain of them ran in the mixin's async mode: the chain stayed on the event loop, and each `process_request` and `process_response` went to a thread and back. Since 6.2 each that has either hook sets it to false, and `BaseHandler.load_middleware` runs them synchronously: together they make one call into the request's thread, and the centre of the chain one call back to the loop (`django/middleware/common.py:CommonMiddleware.async_capable`, `django/core/handlers/base.py:BaseHandler.load_middleware`). The release notes give the repeated switching as the reason, and allow that a deployment with much concurrent I/O outside the ORM may prefer it to a thread held for each request (`docs/releases/6.2.txt`). [Sync and async in one chain](../handlers/async.md) tells the rule and draws both arrangements.

The mixin's own flag is still true (`django/middleware/__init__.py:MiddlewareMixin`), so a project's middleware built on it can still run asynchronously, and a subclass of Django's that sets the flag back can run in async mode again. But the chain runs a layer synchronously whenever the layer inside it is synchronous and it can be, so one of Django's middleware listed after a project's puts the project's in sync mode too. `RemoteUserMiddleware`, not built on the mixin, declares both flags; `LoginRequiredMiddleware` and `XViewMiddleware` have neither hook and keep the mixin's (`django/contrib/auth/middleware.py:RemoteUserMiddleware`).

`MiddlewareMixin` itself moved in 6.2, from `django.utils.deprecation` to `django.middleware`. The old module answers the old import through its module-level `__getattr__`, which warns with `RemovedInDjango2029Warning` and returns the same class (`django/utils/deprecation.py:__getattr__`; [What still warns: the deprecations and the releases that end them](deprecations.md)).

## Error responses on the request's thread

Under ASGI the wrapper `convert_exception_to_response` puts around an asynchronous layer, the centre of the chain or a middleware in async mode, is a coroutine, which runs `response_for_exception`, error view and all, through `sync_to_async` when the layer raises. Since 6.2 it passes `thread_sensitive=True`, so the error view runs on the request's own thread, where before it ran on a shared pool (`django/core/handlers/exception.py:convert_exception_to_response`). The release notes' reason is the database: a connection belongs to the thread that opened it, and the change lets `close_old_connections`, which runs on the request's thread as the request starts and ends, manage the connections a `handler404` or a `handler500` uses (`django/db/utils.py:ConnectionHandler.thread_critical`, `django/db/__init__.py:close_old_connections`). [How an exception becomes a response](../handlers/exceptions.md) tells the conversion, and [Sync and async in one chain](../handlers/async.md#one-thread-per-request) the request's thread.

## The ASGI request: a disconnect and several cookies

Since 5.0 an `"http.disconnect"` that comes before the response is made is handled, so that a view can clean up (`docs/releases/5.0.txt`). At this commit `ASGIHandler.handle` hears it while it reads the body, and then runs a listener beside the chain and the sending of the response in one `asyncio.TaskGroup`. A disconnect cancels the work: a coroutine view is cancelled where it awaits, and can clean up, while synchronous code already running in the request's thread runs to its end (`django/core/handlers/asgi.py:ASGIHandler.handle`; [The two entry points](../handlers/entry.md#an-asgi-request)).

Since 6.0 the several `"cookie"` headers that HTTP/2 allows are joined with a semicolon and a space into one `"HTTP_COOKIE"`, where any other repeated header is joined with commas (`django/core/handlers/asgi.py:ASGIRequest.__init__`; [Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md)).

## Decorators around a coroutine view

The handler decides how to call a view by asking whether it is a coroutine function, and it asks the outermost decorator's wrapper: a wrapper written with `def` makes an `async def` view look synchronous. The view decorators did not support coroutine views before 5.0 (`docs/releases/5.0.txt`). Since then each decorator of `django/views/decorators/` but `sensitive_variables`, and each made from a middleware, picks when it is applied a `def` wrapper or an `async def` one that awaits the view (`django/views/decorators/http.py:require_http_methods`, `django/utils/decorators.py:make_middleware_decorator`); since 5.2 `method_decorator` marks its replacement as a coroutine function when the method is one (`django/utils/decorators.py:_multi_decorate`). `sensitive_variables` takes a coroutine by not wrapping it: it records the names under the function's file and first line, where the error reporter looks (`django/views/decorators/debug.py:sensitive_variables`). [Asynchronous views](../views/async.md#what-a-decorator-has-to-keep) tells what the handler's test needs.

> **Trap.** Around a coroutine view, a decorator made from a middleware calls the middleware's hooks directly, so they run on the event loop ([A middleware as a decorator](../views/middleware-decorators.md#a-coroutine-view)).

## `JsonResponse` and its safe argument

`JsonResponse` used to refuse anything but a dictionary unless it was given `safe=False`, a guard against an attack on a JSON array through JavaScript's array prototype that, the release notes say, ECMAScript 5 closed. Since 6.2 the argument's default is `None`, read as false, so a list is serialised without it. Passing it any value but `None` warns with `RemovedInDjango2029Warning`, and `safe=True` still raises `TypeError` for a value that is not a dictionary (`django/http/response.py:JsonResponse.__init__`; [The response object](../http/response.md#jsonresponse)).

## The multipart parser's Base64

Since 6.1 `MultiPartParser.parse` decodes a part sent with a `"base64"` transfer encoding through `base64.b64decode` with `validate=True`, so a character outside the Base64 alphabet makes the data invalid (in a file, white space is removed first); before, the notes say, invalid data could be silently ignored or give empty values (`django/http/multipartparser.py:MultiPartParser.parse`; [Multipart parsing and upload handlers](../http/uploads.md)). They say it now raises `MultiPartParserError`. At this commit that holds for a file, which the handler answers with a 400; a field that does not decode is kept as sent.

```text
# base64_parts.py at this commit: one part of a multipart body, with Content-Transfer-Encoding: base64
a field, 'aGFyYm91cg=='    POST {'berth': ['harbour']}
a field, 'aGFy!Ym91cg=='   POST {'berth': ['aGFy!Ym91cg==']}
a file,  'aGFyYm91cg=='    FILES {'log': b'harbour'}
a file,  'aGFy!Ym91cg=='   raises MultiPartParserError: Could not decode base64 data.
```

## The smaller changes

| what | at this commit | release | where |
|---|---|---|---|
| a form not in UTF-8 | loading `POST` or `FILES` for an `"application/x-www-form-urlencoded"` request with an encoding other than `"utf-8"` raises `BadRequest`, a 400 | 5.0 | `django/http/request.py:HttpRequest._load_post_and_files` |
| `HttpRequest.accepted_types` | sorted by the client's preference: weight first, then how specific the type is | 5.2 | [Headers, host and scheme](../http/headers.md) |
| `HttpRequest.get_preferred_type` | new: of the types given, the one the client prefers, or `None` | 5.2 | [Headers, host and scheme](../http/headers.md) |
| `HttpRequest.multipart_parser_class` | new: the parser's class, settable until `POST` or `FILES` is loaded, then `RuntimeError` | 6.1 | [Multipart parsing and upload handlers](../http/uploads.md) |
| `HttpResponse.text` | new: the content decoded with the charset; a streaming response raises `AttributeError` | 5.2 | [The response object](../http/response.md) |
| a redirect with `preserve_request=True` | 307 in place of 302, 308 in place of 301; `redirect` passes the argument on | 5.2 | `django/http/response.py:HttpResponseRedirectBase.__init__` |
| `RedirectView.preserve_request` | new, passed to the response | 6.1 | `django/views/generic/base.py:RedirectView.get` |
| a redirect's maximum length | keyword-only, `MAX_URL_REDIRECT_LENGTH` by default, no check for `max_length=None`; `redirect` passes it on; the limit came with a security fix, [Security fixes: limits against denial of service](security-fixes-limits.md) | 6.1 | [The response object](../http/response.md) |
| `reverse` | keyword-only arguments for a query string and a fragment, added after the path; `reverse_lazy` takes them too | 5.2 | [Reversing a name](../urls/reversing.md) |
| `register_converter` | a name already registered, or a default one, raises `ValueError`; overriding warned from 5.1 | 6.0 | [Routes, regular expressions and converters](../urls/patterns.md) |
| get_converter | removed; the converters are read through `get_converters` | 5.1 | `django/urls/converters.py:get_converters` |
| `aget_object_or_404`, `aget_list_or_404` | new: the shortcuts' twins for a coroutine | 5.0 | [The shortcuts](../views/shortcuts.md) |
| `SafeExceptionReporterFilter.hidden_settings` | matches `"AUTH"` too, so `AUTH_USER_MODEL` and `AUTHENTICATION_BACKENDS` are starred in an error report | 5.2 | [The debug pages and `ExceptionReporter`](../views/debug.md) |
