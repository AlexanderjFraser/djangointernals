---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The two entry points

What `WSGIHandler` and `ASGIHandler` each do around the middleware chain: how a server's call becomes a request object, how the response gets back to the server, and who ends the request.

A server is pointed at a module of the project, `wsgi.py` or `asgi.py` in a project made by `django-admin startproject`, and importing that module makes the handler. It calls one of two functions. `get_wsgi_application` runs `django.setup` and returns a new `WSGIHandler`; `get_asgi_application` does the same and returns an `ASGIHandler`. The functions exist so that the two classes can stay private: a project names the function and never the class (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`). A process therefore has one handler, made as the server starts, and making it builds the middleware chain, which is the subject of [the next section](chain.md).

## A WSGI request

A WSGI server calls its application with two arguments: a dictionary describing the request, the environ, and a function to call with the status and the headers. `WSGIHandler.__call__` works through them in this order (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).

1. It records the **script prefix** for the current thread: the leading part of the path that belongs to the server's mount point and not to Django, which reversed URLs must carry. The value comes from the environ, unless `settings.FORCE_SCRIPT_NAME` overrides it (`django/core/handlers/wsgi.py:get_script_name`).
2. It sends the `request_started` signal.
3. It makes the request, a `WSGIRequest`, from the environ. This is cheap. The body is not read: it is wrapped in a `LimitedStream` that will not read past the declared content length. The query string, the cookies and the form data are each parsed when first asked for (`django/core/handlers/wsgi.py:WSGIRequest.__init__`).
4. It calls `BaseHandler.get_response`, and the chain runs.
5. It calls the server's function with the status line and the headers, each cookie having become a `Set-Cookie` header.
6. It returns the response object itself. An `HttpResponse` can be iterated to yield its content, and that is all WSGI asks of a body.

The last step differs for a file. When the response has a file to stream and the server offers a file wrapper in the environ, the handler returns the server's wrapper around the file, so that the server can send it by its own fastest means. A server that is given its own wrapper will call `close` on the wrapper when it is done, and never on the response; closing the wrapper closes only the file. So the handler first replaces the file's `close` with the response's, which closes the file and everything else.

## What `BaseHandler.get_response` adds

`BaseHandler.get_response` is a thin shell around the call of the chain (`django/core/handlers/base.py:BaseHandler.get_response`).

Before the call it sets the current URLconf to `settings.ROOT_URLCONF`. The value is kept for the thread, or under ASGI for the task. It is what `reverse` and `resolve` consult when they are given no URLconf, and where `response_for_exception` looks for the error views (`django/urls/base.py:get_urlconf`).

After the call it registers the request's own `close` among the response's closers, so that closing the response also closes the request's uploaded files. And if the status is 400 or above it passes the response to `log_response`, which logs a 4xx as a warning and a 5xx as an error, unless the response was already logged where its exception was caught (`django/utils/log.py:log_response`).

`BaseHandler.get_response_async` is the same shell for the asynchronous path. There are two because sending everything, WSGI included, through one asynchronous path proved too slow: each mode has its own, and neither pays for a context switch it does not need (`django/core/handlers/base.py:BaseHandler.get_response_async`).

## Who ends the request

The WSGI handler returns before the request is over. The server still has to iterate the response to send the body, and when it has, it calls the response's `close`. `HttpResponseBase.close` runs every closer registered on the response, the request's among them, and then sends `request_finished` (`django/http/response.py:HttpResponseBase.close`).

So the signal that ends a request fires after the last of the body has been handed to the server. For a streaming response that can be long after the view returned.

Django hangs its own per-request housekeeping on these signals instead of calling it from the handler.

| signal | sent | Django's own receivers |
|---|---|---|
| `request_started` | by the handler, before the request object is made | `reset_queries` empties each database connection's query log; `close_old_connections` closes connections that are unusable or past their age |
| `request_finished` | by `HttpResponseBase.close`; under ASGI by the handler itself, when the client left before there was a response | `close_old_connections` again; `close_caches`; `reset_urlconf`, which clears a URLconf override; and the development server's reloader, when it watches files with Watchman |
| `got_request_exception` | by `response_for_exception` and `get_exception_response`, when an exception is about to become a 500 | none in a serving process; the test client listens during each of its requests, to hand the exception to the test |

*The three signals of the request cycle. They are defined in `django/core/signals.py`. The receivers are connected where they are defined: `django/db/__init__.py`, `django/core/cache/__init__.py`, `django/core/handlers/base.py`, `django/utils/autoreload.py` and `django/test/client.py`.*

The handler itself therefore never closes a database connection. Connections that are unusable, or older than their configured age, are closed by `close_old_connections`, at the start of a request and again at its end.

## An ASGI request

An ASGI server calls its application once for each request, with a dictionary called the scope and two coroutines, one to receive messages and one to send them. `ASGIHandler.__call__` accepts only a scope of the type `"http"` and raises `ValueError` for any other, a WebSocket included. It then runs `ASGIHandler.handle` inside a `ThreadSensitiveContext`. That class comes from asgiref, the library of adapters between synchronous and asynchronous code that Django depends on, and its effect is that the synchronous code of this request's middleware and view runs on a thread of the request's own (`django/core/handlers/asgi.py:ASGIHandler.__call__`, `asgiref:asgiref/sync.py:ThreadSensitiveContext`).

`ASGIHandler.handle` then does what the WSGI handler does, with these differences (`django/core/handlers/asgi.py:ASGIHandler.handle`).

The body is read first, and whole. `ASGIHandler.read_body` receives messages until the last one and writes them to a temporary file, which stays in memory until it grows past `settings.FILE_UPLOAD_MAX_MEMORY_SIZE` and then moves to disk. Only after that is `request_started` sent and the `ASGIRequest` made. If the client disconnects while the body is arriving, the handler returns without a response (`django/core/handlers/asgi.py:ASGIHandler.read_body`).

Two failures to make the request are answered before the chain. `ASGIHandler.create_request` catches `UnicodeDecodeError` and returns a 400 response in the request's place, and the handler sends it at once; such a response passes through no middleware. It catches `RequestDataTooBig` the same way, with a 413, though at this commit that exception is raised only when a request's body is read, which making the request does not do. Any other exception raised while the request is made is not caught here (`django/core/handlers/asgi.py:ASGIHandler.create_request`).

The handler listens for a disconnect while it works. It runs two things together in a task group: the chain followed by the sending of the response, and a listener waiting for the client to go away. Whichever finishes first cancels the other. A client that disconnects thus cancels whatever part of the request is waiting on the event loop at that moment, an async view included. Synchronous code already running in the request's thread is not interrupted. If that code is the synchronous middleware chain itself, the rest of the chain still runs to its end, the view included, and the response is simply never sent.

The handler sends the response and closes it. `ASGIHandler.send_response` sends the status and the headers as one message and the body in pieces of at most `ASGIHandler.chunk_size` bytes. A streaming response whose content is an asynchronous iterator is sent a part at a time, as the parts are produced; one whose content is a synchronous iterator is first read to its end in a thread, with a warning, and then sent (`django/core/handlers/asgi.py:ASGIHandler.send_response`, `django/http/response.py:StreamingHttpResponse.__aiter__`). There is no server to close the response afterwards, so `handle` does it, and `request_finished` is sent as under WSGI. If the client left before there was a response to close, `handle` sends the signal itself.

## Other handlers

Other handlers in Django's tree build on `BaseHandler`.

The test client's `ClientHandler` and `AsyncClientHandler` derive from `BaseHandler` directly. They build the chain on the first request and not when they are made, because the settings may not be available earlier. They are given what a server would pass, an environ or a scope, make the request themselves, run the same chain, and return the `HttpResponse` object itself with the request attached to it. They close the response as a server would. A test therefore exercises the whole of the middleware and the view, and none of `WSGIHandler.__call__` (`django/test/client.py:ClientHandler.__call__`).

The static files handlers, `StaticFilesHandler` and `ASGIStaticFilesHandler`, wrap another application, which is how the development server serves static files. A request whose path is under the static URL they answer themselves; any other they pass to the application they wrap. Their `load_middleware` does nothing, and their `get_response` and `get_response_async` serve the file directly, so a static file served this way passes through no middleware at all (`django/contrib/staticfiles/handlers.py:StaticFilesHandlerMixin.load_middleware`, `django/contrib/staticfiles/handlers.py:StaticFilesHandlerMixin.get_response`).

A last kind is for Django's live-server test case: `FSFilesHandler` and its subclasses serve static and media files in front of a real `WSGIHandler` (`django/test/testcases.py:FSFilesHandler`).
