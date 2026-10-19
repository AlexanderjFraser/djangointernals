---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in handlers, requests, URLs and views

Under ASGI, most of Django's own middleware now runs on the request's thread in one call, and error views run there too. `MiddlewareMixin`, cookies, decorators on coroutine views, `JsonResponse`, multipart Base64, redirects and `reverse` changed too.

Both ASGI changes came in 6.2 and concern the one thread each request has, on which Django runs the synchronous code it calls with `thread_sensitive=True` (`django/core/handlers/asgi.py:ASGIHandler.__call__`). The notes give two reasons: the cost of switching to that thread and back for each hook, and the database connections an error view uses (`docs/releases/6.2.txt`).

## Django's middleware under ASGI

Since 6.2 a chain of Django's own middleware under ASGI is one call into the request's thread (`django/core/handlers/base.py:BaseHandler.load_middleware`). Each class Django builds on `MiddlewareMixin` with a `process_request` or a `process_response` now sets `async_capable = False`, the flag that says whether a middleware can run on the event loop, where it took the mixin's `True` (`django/middleware/common.py:CommonMiddleware.async_capable`). Such a chain used to run in the mixin's async mode, on the event loop, sending each hook to the thread and back. Its centre, where the handler resolves the view and calls it, is now one call back to the loop.

The recording counts the calls a GET for a synchronous view hands to a thread through startproject's `MIDDLEWARE`:

```text recording=changes
A GET under ASGI through startproject's MIDDLEWARE to a synchronous view: the calls handed to a thread
    5.2.17       16 calls handed to a thread
    6.0.8        16 calls handed to a thread
    6.1.1        16 calls handed to a thread
    this commit  5 calls handed to a thread
```

With `MIDDLEWARE` empty the same GET hands three under all four: for the receivers of `request_started`, the view and closing the response. The other thirteen of 6.1.1's are the middleware's: six `process_request`, one `process_view` and six `process_response`. At this commit the middleware's are two: the chain, and `CsrfViewMiddleware.process_view`, still handed over on its own, as the view is (`django/core/handlers/base.py:BaseHandler._get_response_async`). In the figure, look for where the chain runs and what its centre hands over:

```text figure=thread-crossings
6.1.1, the chain on the event loop: 16 calls
  -> request_started's receivers
  -> each process_request
  -> CsrfViewMiddleware.process_view
  -> the view
  -> each process_response
  -> closing the response

This commit: 5 calls
  -> request_started's receivers
  -> the chain, on the thread: each process_request,
       then its centre, on the event loop:
         -> CsrfViewMiddleware.process_view
         -> the view
     then each process_response
  -> closing the response
```

*Time runs down; each arrow is a call handed from the event loop to the request's thread. At this commit the accented box is the chain's one call, its hooks running inside it, and its centre on the event loop hands over two calls.*

A project's own class built directly on the mixin keeps the flag true unless it sets it. It therefore takes the mode of the layer inside it. Listed last, it runs in async mode as before; directly before one of Django's synchronous ones, it now runs synchronously, in their one call (`django/middleware/__init__.py:MiddlewareMixin.async_capable`, `django/core/handlers/base.py:BaseHandler.load_middleware`; [Sync and async in one chain](../handlers/async.md)).

`MiddlewareMixin` moved in 6.2, from `django.utils.deprecation` to `django.middleware`. The old import still works, and warns with `RemovedInDjango2029Warning` (`django/utils/deprecation.py:__getattr__`; [What changed](../changes.md#an-old-habit-release-by-release)).

## Error responses on the request's thread

Since 6.2 an error view under ASGI runs on the request's thread, where it ran on a shared pool, the notes say. The wrapper that `convert_exception_to_response` puts around an asynchronous layer runs `response_for_exception`, error view and all, through `sync_to_async` when the layer raises. That call now passes `thread_sensitive=True` (`django/core/handlers/exception.py:convert_exception_to_response`; [How an exception becomes a response](../handlers/exceptions.md)).

When a synchronous view raises under an `ASGIHandler`, "another thread", where the project's `handler500` ran, is one of the pool's:

```text recording=changes
handler500 under ASGI, when a synchronous view raises: the thread it runs on
    5.2.17       another thread
    6.0.8        another thread
    6.1.1        another thread
    this commit  the view's thread
```

> **Why.** The notes' reason is the database. A connection belongs to the thread that opened it (`django/db/utils.py:ConnectionHandler.thread_critical`). `close_old_connections`, which closes one broken or past its age, runs on the request's thread as the request starts and ends (`django/db/__init__.py:close_old_connections`). Before 6.2 it could not reach one that an error view opened on a pool thread.

## `JsonResponse` and its safe argument

Since 6.2 `JsonResponse` serialises a list. It used to refuse anything but a dictionary unless given `safe=False`. It guarded against an attack on a JSON array through JavaScript's array prototype, which ECMAScript 5 closed, the 6.2 notes say (`docs/releases/6.2.txt`). The default of `safe=` is now `None`, read as false (`django/http/response.py:JsonResponse.__init__`).

Given a list and no `safe=`, 6.1.1's `TypeError` is the old refusal; 5.2.17 and 6.0.8 raised it too and are left out:

```text recording=changes
JsonResponse([1, 2]).content
...
    6.1.1        TypeError: In order to allow non-dict objects to be serialized set the safe parameter to False.
    this commit  b'[1, 2]'
```

Passing `safe=` any value but `None` now warns, since the argument goes in Django 2029 ([What still warns: the deprecations and the releases that end them](deprecations.md)). So `safe=False`, a 5.x project's habit, gives the same bytes as before and warns. `safe=True` warns and still refuses a list.

## The multipart parser's Base64

Since 6.1 the multipart parser is strict about a part whose Content-Transfer-Encoding is `"base64"`. Before 6.1 it decoded such a part leniently: invalid data "could be silently ignored or result in empty values", the 6.1 notes say (`docs/releases/6.1.txt`). `MultiPartParser.parse` now decodes with `validate=True`, which refuses any character outside the Base64 alphabet (`django/http/multipartparser.py:MultiPartParser.parse`; [Multipart parsing: `MultiPartParser`](../http/multipart.md)).

A file's data has an exclamation mark inside it, and the `b'Monday'` of 5.2.17 and 6.0.8 is the mark dropped without a word:

```text recording=changes
request.FILES["notes"].read(): a file sent as base64, "TW9u!ZGF5"
    5.2.17       b'Monday'
    6.0.8        b'Monday'
    6.1.1        MultiPartParserError: Could not decode base64 data.
    this commit  MultiPartParserError: Could not decode base64 data.
```

The handler answers `MultiPartParserError` with a 400 (`django/core/handlers/exception.py:response_for_exception`). The notes say invalid data now raises that error, but that holds for a file alone. A field that fails is kept as sent: "TW9u!ZGF5", where 5.2.17 and 6.0.8 gave "Monday".

The file's branch and the field's also differ over white space: the file's removes it before decoding, the field's does not. In a field whose Base64 is broken into lines, 6.1.1 and this commit give the data undecoded:

```text recording=changes
request.POST["body"]: a multipart field sent as base64 over two lines, "TW9u" and "ZGF5"
    5.2.17       'Monday'
    6.0.8        'Monday'
    6.1.1        'TW9u\r\nZGF5'
    this commit  'TW9u\r\nZGF5'
```

> **Trap.** Nothing warns or fails. Since 6.1 a field whose Base64 is written in lines, as MIME writes it, arrives undecoded, while the same data in a file still decodes (`django/http/multipartparser.py:MultiPartParser.parse`).

## The smaller changes

The rest, by name:

| what | change | where |
|---|---|---|
| a disconnect under ASGI | Since 5.0, one before the response cancels a coroutine view where it awaits; synchronous code under way runs to its end | [The two entry points](../handlers/entry.md#an-asgi-request) |
| cookies under ASGI | Since 6.0, separate `"cookie"` headers are joined with `"; "`, so each cookie is read; 5.2.17 joined them with commas, the second inside the first's value | [Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md#from-an-asgi-scope) |
| a form not in UTF-8 | Since 5.0, a urlencoded body declared in another charset raises `BadRequest`, a 400 | `django/http/request.py:HttpRequest._load_post_and_files` |
| `HttpRequest.accepted_types` | Since 5.2, sorted by the client's preference | [Headers, host and scheme](../http/headers.md) |
| `HttpRequest.get_preferred_type` | New in 5.2: of the types given, the one the client prefers | `django/http/request.py:HttpRequest.get_preferred_type` |
| `HttpRequest.multipart_parser_class` | New in 6.1: the parser's class, replaceable until the body is parsed | [Multipart parsing: `MultiPartParser`](../http/multipart.md#replacing-the-parser-multipart_parser_class) |
| `django.views.decorators` | Since 5.0, each wraps a coroutine view in an `async def` that awaits it; `sensitive_variables` leaves it unwrapped | [Asynchronous views](../views/async.md#what-a-decorator-has-to-keep) |
| `method_decorator` | Since 5.2, marks its replacement a coroutine function when the method is one | `django/utils/decorators.py:_multi_decorate` |
| `preserve_request=` of a redirect | New in 5.2: 307 for 302 and 308 for 301, in `HttpResponseRedirect`, `HttpResponsePermanentRedirect` and `redirect` | [The response object](../http/response.md#redirects) |
| `RedirectView.preserve_request` | New in 6.1: given to the response the view makes | `django/views/generic/base.py:RedirectView.get` |
| `max_length=` of a redirect | New in 6.1, keyword-only: `MAX_URL_REDIRECT_LENGTH` unless given, `None` for no limit; `redirect` takes it too | `django/http/response.py:HttpResponseRedirectBase.__init__` |
| a redirect's limit | Since 6.1, measured on the escaped `"Location"`; a security fix brought the limit | [Security fixes: limits against denial of service](security-fixes-limits.md) |
| `reverse` | New in 5.2: keyword-only `query=` and `fragment=`, taken by `reverse_lazy` too | [Reversing a name](../urls/reversing.md#the-query-string-and-the-fragment) |
| `register_converter` | Since 6.0, `ValueError` for a name already registered, a default's included; deprecated in 5.1, it warns and replaces under 5.2.17 | [Routes, regular expressions and converters](../urls/patterns.md#converters) |
| get_converter | Gone in 5.1; the registry is read through `get_converters` | `django/urls/converters.py:get_converters` |
