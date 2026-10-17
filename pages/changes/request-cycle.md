---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in handlers, requests, URLs and views

The changes from Django 5.0 to this commit in the request cycle: Django's middleware under ASGI, error responses on the request's thread and `MiddlewareMixin` moved (6.2); the ASGI request's disconnect and cookies; decorators around coroutine views; `JsonResponse` without safe; strict Base64 in multipart bodies; and smaller changes to requests, redirects, `reverse` and converters.

Two changes of 6.2 alter how a request is served under ASGI, and both concern the one thread each ASGI request has, on which Django runs the synchronous code it calls with `thread_sensitive=True` (`django/core/handlers/asgi.py:ASGIHandler.__call__`). Most of Django's own middleware now runs on that thread in a single call, where it used to send each hook there from the event loop and back, and an error view runs there too, where it ran on a shared pool. The notes' reasons are the cost of the switching and the database connections an error view uses (`docs/releases/6.2.txt`).

Two guards changed too: `JsonResponse` stopped refusing a list (6.2), and the multipart parser became strict about Base64 (6.1).

## Django's middleware under ASGI

Before 6.2 the middleware classes Django builds on `MiddlewareMixin` took its `async_capable = True`, so under ASGI a chain of them ran in the mixin's async mode, on the event loop, sending each `process_request` and `process_response` to the request's thread and back. Since 6.2 every one built on the mixin with either hook has the flag false, and `BaseHandler.load_middleware` therefore runs them synchronously: together they make one call into the request's thread, and the centre of the chain, where the handler resolves the view and calls it, one call back to the loop (`django/middleware/common.py:CommonMiddleware.async_capable`, `django/core/handlers/base.py:BaseHandler.load_middleware`). Here a GET for a synchronous view passes through startproject's `MIDDLEWARE`, and the run counts the calls handed to a thread:

```text recording=changes
A GET under ASGI through startproject's MIDDLEWARE to a synchronous view: the calls handed to a thread
    5.2.17       16 calls handed to a thread
    6.0.8        16 calls handed to a thread
    6.1.1        16 calls handed to a thread
    this commit  5 calls handed to a thread
```

With `MIDDLEWARE` empty the same GET hands three under all four, for the receivers of `request_started`, the view and the closing of the response; the rest are the middleware's. Since 6.2 the chain is one call, and only `CsrfViewMiddleware.process_view` is still handed over on its own, as the view is (`django/core/handlers/base.py:BaseHandler._get_response_async`). Each call is one switch from the event loop to the thread and back, so a request gains the switches saved. [Sync and async in one chain](../handlers/async.md) tells the rule, and when the 6.2 notes say the old arrangement may still be preferred.

`LoginRequiredMiddleware` and `XViewMiddleware`, which have only a `process_view`, keep the mixin's flag, still true (`django/middleware/__init__.py:MiddlewareMixin.async_capable`), and `RemoteUserMiddleware`, not built on the mixin, declares it true (`django/contrib/auth/middleware.py:RemoteUserMiddleware`). A project's own class built directly on the mixin keeps the flag true unless it sets it, and so takes the mode of the layer inside it, the next in `MIDDLEWARE`: after all of Django's synchronous ones it runs in async mode as before, and directly before one it now runs synchronously, in their one call (`django/core/handlers/base.py:BaseHandler.load_middleware`).

`MiddlewareMixin` itself moved in 6.2, from `django.utils.deprecation` to `django.middleware`; the old import still works, and warns with `RemovedInDjango2029Warning` (`django/utils/deprecation.py:__getattr__`; [What changed](../changes.md#an-old-habit-release-by-release)).

## Error responses on the request's thread

Under ASGI the wrapper that `convert_exception_to_response` puts around an asynchronous layer is a coroutine function, and when the layer raises it runs `response_for_exception`, error view and all, through `sync_to_async`. Before 6.2 that ran on a shared pool of threads, the notes say; since 6.2 the call passes `thread_sensitive=True`, which sends it to the request's own thread (`django/core/handlers/exception.py:convert_exception_to_response`). Here a synchronous view raises under an `ASGIHandler`, and the run compares the thread the project's `handler500` runs on with the view's:

```text recording=changes
handler500 under ASGI, when a synchronous view raises: the thread it runs on
    5.2.17       another thread
    6.0.8        another thread
    6.1.1        another thread
    this commit  the view's thread
```

The notes' reason is the database. A connection belongs to the thread that opened it (`django/db/utils.py:ConnectionHandler.thread_critical`), and `close_old_connections`, which closes one that is broken or past its age, runs on the request's thread as the request starts and ends (`django/db/__init__.py:close_old_connections`); before 6.2 it could not reach a connection that a `handler404` or a `handler500` opened on a pool thread. [How an exception becomes a response](../handlers/exceptions.md) tells the conversion.

## The ASGI request: a disconnect, and cookies sent separately

Since 5.0 an `"http.disconnect"` that arrives before the response is made cancels the work, so that a view can clean up (`docs/releases/5.0.txt`). A coroutine view is cancelled where it awaits, while synchronous code already running on the request's thread runs to its end (`django/core/handlers/asgi.py:ASGIHandler.handle`; [The two entry points](../handlers/entry.md#an-asgi-request)).

HTTP/2 lets a client send each cookie as a `"cookie"` header of its own. Here an `ASGIRequest` is made with two:

```text recording=changes
request.COOKIES under ASGI, sent as two "cookie" headers: year=2026 and order=newest
    5.2.17       {'year': '2026,order=newest'}
    6.0.8        {'year': '2026', 'order': 'newest'}
    6.1.1        {'year': '2026', 'order': 'newest'}
    this commit  {'year': '2026', 'order': 'newest'}
```

Under 5.2.17 the second cookie disappeared into the first. Since 6.0 the `"cookie"` headers are joined with a semicolon and a space into `"HTTP_COOKIE"`, where any other repeated header is joined with commas (`django/core/handlers/asgi.py:ASGIRequest.__init__`), and the cookie parser, which splits on semicolons alone, finds both (`django/http/cookie.py:parse_cookie`; [Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md#from-an-asgi-scope)).

## Decorators around a coroutine view

The handler asks the outermost wrapper whether a view is a coroutine function, so a wrapper written with `def` makes an `async def` view look synchronous. Django's view decorators did not support coroutine views before 5.0, the notes say (`docs/releases/5.0.txt`). Since then each decorator in `django/views/decorators/` but `sensitive_variables`, and each made from a middleware, chooses between a `def` wrapper and an `async def` one that awaits the view (`django/views/decorators/http.py:require_http_methods`, `django/utils/decorators.py:make_middleware_decorator`); `sensitive_variables` records which of a coroutine function's variables are sensitive without wrapping it (`django/views/decorators/debug.py:sensitive_variables`). Since 5.2 `method_decorator` marks its replacement as a coroutine function when the method is one (`django/utils/decorators.py:_multi_decorate`; [Asynchronous views](../views/async.md#what-a-decorator-has-to-keep)).

## `JsonResponse` and its safe argument

`JsonResponse` refused anything but a dictionary unless given `safe=False`. The guard was against an attack on a JSON array through JavaScript's array prototype, which, the 6.2 notes say, ECMAScript 5 closed (`docs/releases/6.2.txt`). Since 6.2 the default is `None`, read as false, so a list is serialised (`django/http/response.py:JsonResponse.__init__`). Here a list is given without safe; 5.2.17 and 6.0.8 raised as 6.1.1 did, and are left out:

```text recording=changes
JsonResponse([1, 2]).content
...
    6.1.1        TypeError: In order to allow non-dict objects to be serialized set the safe parameter to False.
    this commit  b'[1, 2]'
```

Passing safe at all now warns, the argument to go in Django 2029 ([What still warns: the deprecations and the releases that end them](deprecations.md)): `safe=False`, the habit of a 5.x project, gives the same bytes as before and warns, and `safe=True` warns and still refuses a list.

## The multipart parser's Base64

A part of a multipart body may declare its Content-Transfer-Encoding as `"base64"`. Before 6.1 the parser decoded it leniently: invalid data "could be silently ignored or result in empty values", the 6.1 notes say (`docs/releases/6.1.txt`). Since 6.1 `MultiPartParser.parse` decodes with `validate=True`, which refuses any character outside the Base64 alphabet (`django/http/multipartparser.py:MultiPartParser.parse`; [Multipart parsing and upload handlers](../http/uploads.md)). Here a file's data has an exclamation mark inside it:

```text recording=changes
request.FILES["notes"].read(): a file sent as base64, "TW9u!ZGF5"
    5.2.17       b'Monday'
    6.0.8        b'Monday'
    6.1.1        MultiPartParserError: Could not decode base64 data.
    this commit  MultiPartParserError: Could not decode base64 data.
```

Under 5.2.17 and 6.0.8 the mark was dropped and the rest decoded; the handler answers `MultiPartParserError` with a 400. The notes say invalid data now raises that error, but that holds for a file alone: a field that fails is kept as sent, "TW9u!ZGF5" where 5.2.17 and 6.0.8 gave "Monday".

The parser's branches for a file and for a field also differ over white space: the file's removes it before decoding, and the field's does not. Here a field's Base64 is broken into lines:

```text recording=changes
request.POST["body"]: a multipart field sent as base64 over two lines, "TW9u" and "ZGF5"
    5.2.17       'Monday'
    6.0.8        'Monday'
    6.1.1        'TW9u\r\nZGF5'
    this commit  'TW9u\r\nZGF5'
```

> **Trap.** Nothing warns or fails: from 6.1 a field whose Base64 is written in lines, as MIME writes it, arrives undecoded, while the same data in a file still decodes (`django/http/multipartparser.py:MultiPartParser.parse`).

## The smaller changes

The rest, by name:

| what | at this commit | release | where |
|---|---|---|---|
| a form not in UTF-8 | an `"application/x-www-form-urlencoded"` body declared in another charset raises `BadRequest`, a 400 | 5.0 | `django/http/request.py:HttpRequest._load_post_and_files` |
| `HttpRequest.accepted_types`, `HttpRequest.get_preferred_type` | the first sorted by the client's preference; the second new, the given type the client prefers | 5.2 | [Headers, host and scheme](../http/headers.md) |
| `HttpRequest.multipart_parser_class` | new: the parser's class, replaceable until the body is parsed | 6.1 | [Multipart parsing and upload handlers](../http/uploads.md#changing-the-handlers) |
| preserve_request on a redirect | 307 for 302 and 308 for 301, in `HttpResponseRedirect`, `HttpResponsePermanentRedirect` and `redirect` | 5.2 | [The response object](../http/response.md#redirects) |
| `RedirectView.preserve_request` | new, given to the response the view makes | 6.1 | `django/views/generic/base.py:RedirectView.get` |
| a redirect's maximum length | a keyword-only max_length, also taken by `redirect`: `MAX_URL_REDIRECT_LENGTH` unless given, `None` for no check; the limit now measures the escaped `"Location"` | 6.1 | `django/http/response.py:HttpResponseRedirectBase.__init__` |
| `reverse` | keyword-only query and fragment; `reverse_lazy` takes them too | 5.2 | [Reversing a name](../urls/reversing.md#the-query-string-and-the-fragment) |
| `register_converter` | a name already registered, a default's included, raises `ValueError`; deprecated in 5.1, so 5.2.17 warns RemovedInDjango60Warning and replaces it | 6.0 | [Routes, regular expressions and converters](../urls/patterns.md#converters) |
| get_converter | removed; the registry is read through `get_converters` | 5.1 | `django/urls/converters.py:get_converters` |

*The redirect's limit came with a security fix ([Security fixes: limits against denial of service](security-fixes-limits.md)).*
