---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The two entry points

`WSGIHandler` and `ASGIHandler`, made by `get_wsgi_application` and `get_asgi_application`, each turn a server's call into a request, run the middleware chain and hand the response back. `ASGIHandler.handle` works in phases, one listening for the client to leave.

A server imports the project's `wsgi.py` or `asgi.py`, which makes the handler by calling one of the two functions; each runs `django.setup` first (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`). A serving process therefore makes its handler once, as the server starts, and making it builds the chain ([Building the middleware chain](chain.md)).

Other handlers are built on `BaseHandler`: the test client's `ClientHandler` and `AsyncClientHandler`, which run the whole chain and none of `WSGIHandler.__call__` ([The test client: `Client` and `ClientHandler`](../testing/client.md#the-servers-part-clienthandler__call)), and `StaticFilesHandler` and `FSFilesHandler`, which serve static files, the second media files too, for the development server and live-server tests ([Serving static files: `StaticFilesHandler` and the development server](../contrib/serving-static.md), [A server in a thread: `LiveServerTestCase`](../testing/live-server.md#static-and-media-files-fsfileshandler)).

## A WSGI request

A WSGI server calls its application with the environ, a dictionary describing the request, and a function to call with the status and headers. `WSGIHandler.__call__` sets the script prefix, the part of the path at which the server mounts the project ([The script prefix, the current URLconf and the caches](../urls/state.md#the-script-prefix)), sends `request_started`, makes a `WSGIRequest` without reading the body ([Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md#from-a-wsgi-environ)), and calls `BaseHandler.get_response`, which runs the chain. It then calls the server's function with the status line and the headers, and returns the response (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).

For a response that streams a file, when the environ holds the server's file wrapper, `"wsgi.file_wrapper"`, the handler returns the file in it instead, and gives the file the response's `close`, since the server will close the wrapper and not the response ([Streaming and file responses](../http/streaming.md#fileresponse)).

## What `BaseHandler.get_response` adds

`BaseHandler.get_response` is a thin shell around the chain's call (`django/core/handlers/base.py:BaseHandler.get_response`). Before it, it sets the current URLconf to `settings.ROOT_URLCONF` ([The script prefix, the current URLconf and the caches](../urls/state.md#the-current-urlconf)). After it, it adds the request's `close`, which closes its uploaded files, to the response's closers, the functions the response's `close` calls, and passes a response of 400 or above to `log_response` (`django/utils/log.py:log_response`). `BaseHandler.get_response_async` is the same shell for the asynchronous path.

> **Why.** By the docstring of `BaseHandler.get_response_async`, one asynchronous `get_response` for everything, WSGI included, is too slow, and a separate path avoids the context switch (`django/core/handlers/base.py:BaseHandler.get_response_async`): under WSGI no event loop is running, and `async_to_sync` then runs a coroutine on a new loop in a new thread while the calling thread waits (`asgiref:asgiref/sync.py:AsyncToSync.__call__`).

## Who ends the request

The WSGI handler returns before the request is over: the server still has to iterate the response for the body, and then calls its `close`. `HttpResponseBase.close` runs every closer registered on the response, the request's among them, and then sends `request_finished` (`django/http/response.py:HttpResponseBase.close`). So the signal that ends a request fires after the last of the body is handed to the server, for a streaming response perhaps long after the view returned.

Django hangs its per-request housekeeping on signals, not on the handler.

| signal | sent | Django's own receivers |
|---|---|---|
| `request_started` | by the handler, before the request object is made | `reset_queries` empties each database connection's query log; `close_old_connections` closes connections that are unusable or past their age |
| `request_finished` | by `HttpResponseBase.close`; under ASGI by the handler itself, when the client left before the handler had a response | `close_old_connections` again; `close_caches`; `reset_urlconf`, which clears a URLconf override; and the development server's reloader, when it watches files with Watchman |
| `got_request_exception` | by `response_for_exception` and `get_exception_response`, when an exception is to become a 500 or, under `settings.DEBUG_PROPAGATE_EXCEPTIONS`, to be raised on | none in a serving process; the test client listens, to hand the exception to the test |

*The three signals of the request cycle, defined in `django/core/signals.py`.*

## An ASGI request

An ASGI server calls its application once for each request, with the scope, a dictionary, and two awaitable callables that receive and send messages. `ASGIHandler.__call__` accepts only a scope of the type `"http"` and runs `ASGIHandler.handle` inside asgiref's `ThreadSensitiveContext`, which gives the request's synchronous code a thread of its own ([Sync and async in one chain](async.md#one-thread-per-request)) (`django/core/handlers/asgi.py:ASGIHandler.__call__`).

`ASGIHandler.handle` works in phases (`django/core/handlers/asgi.py:ASGIHandler.handle`). `ASGIHandler.read_body` receives the whole body into a temporary file, and only then does `handle` send `request_started` and make the `ASGIRequest`. It then starts the listener `ASGIHandler.listen_for_disconnect` as the one task of an `asyncio.TaskGroup`, to wait for the client to go, and in its own task runs the chain and `ASGIHandler.send_response` ([Streaming and file responses](../http/streaming.md#under-asgi) has the sending).

Whichever ends first cancels the other. With the response sent, `handle` raises an exception of its own, and the group cancels the listener. At a disconnect the listener raises `RequestAborted` (`django/core/handlers/asgi.py:ASGIHandler.listen_for_disconnect`), and the group cancels `handle`'s own task where it waits; leaving its block, it withdraws that cancellation and raises the `RequestAborted` in an exception group (`asyncio.TaskGroup`). `handle` catches either and goes on, to close the response, which sends `request_finished`, or, with none, to send the signal itself.

In the figure the phases run left to right: two exits drop below the phases they leave, before the task group, and inside the group the two run one above the other.

```text figure=asgi-phases
ASGIHandler.handle, its phases left to right; an exit drops below the phase it leaves

read_body: the whole body
    exit: a disconnect -> return, no signal at all
signal: request_started
create_request: the ASGIRequest
    exit: UnicodeDecodeError -> a 400, sent and closed, no middleware
the task group: whichever ends first cancels the other
    the chain, then send_response  |  listen_for_disconnect
the end
    a response: closed, which sends request_finished
    no response: handle sends request_finished
```

*The phases of `ASGIHandler.handle`, left to right; in the task group the two run at once, and an arrow down from a phase is an exit.*

Each line's tag names its thread, `[loop]` the event loop's and `[worker]` the request's own, the crossings left out ([Sync and async in one chain](async.md#what-the-arrangements-cost)). The listener's line marked meanwhile is written while the thread runs the chain, and its place among the chain's lines is no order; the listener is cancelled once the response has gone.

```text recording=handlers
ASGI, GET /plain/: a synchronous view, synchronous middleware, as the server sees it
    receive() from ASGIHandler.read_body -> http.request, more_body False  [loop]
    ...
    signal: request_started  [worker]
    ASGIRequest(scope, body_file)  [loop]
    ...
    receive() from ASGIHandler.listen_for_disconnect: waiting  [loop, meanwhile]
...
    send(http.response.start), status 200  [loop]
    send(http.response.body)  [loop]
    receive() from ASGIHandler.listen_for_disconnect: cancelled  [loop]
    ...
    signal: request_finished  [worker]
    ...
```

`ASGIHandler.create_request` answers two failures. For a `UnicodeDecodeError` it returns a 400 in the request's place, which `handle` sends and closes before the task group: no middleware runs, and both signals are sent, `request_finished` by the close. It would return a 413 for `RequestDataTooBig`, but making an `ASGIRequest` reads no body and so never raises it; any other exception it does not catch (`django/core/handlers/asgi.py:ASGIHandler.create_request`).

### A client that disconnects

A disconnect while the body arrives ends the request earliest: `ASGIHandler.read_body` raises `RequestAborted`, and `handle` returns before either signal (`django/core/handlers/asgi.py:ASGIHandler.read_body`).

A disconnect while the chain runs cancels `handle`'s task where it waits, which behind synchronous middleware is the crossing at the top of the chain. If a task the thread started on the loop with `async_to_sync` is still running, that crossing cancels it and waits for the thread (`asgiref:asgiref/sync.py:SyncToAsync.__call__`). Once the innermost synchronous layer has handed the centre to the loop, that task is the centre's. Its cancellation becomes an `asyncio.CancelledError` raised in that layer's call (`asgiref:asgiref/sync.py:AsyncToSync.main_wrap`): at once for an async view, which is cancelled where it awaits; for a synchronous view, which the thread runs inside that call, when the view returns.

That error is no `Exception`: `MiddlewareMixin.__call__` never reaches its `process_response`, and each layer's wrapper, catching only `Exception`, lets it through (`django/middleware/__init__.py:MiddlewareMixin.__call__`, `django/core/handlers/exception.py:convert_exception_to_response`). Middleware in async mode let it through alike (`django/middleware/__init__.py:MiddlewareMixin.__acall__`).

For an async view, the crossing that sends `request_finished` follows its cancellation with no `process_response` between:

```text recording=handlers
ASGI, GET /hang/: the client disconnects during an async view, synchronous middleware
...
    the view (async def), letting the client disconnect  [loop]
    receive() from ASGIHandler.listen_for_disconnect -> http.disconnect  [loop]
    the view (async def) is cancelled  [loop]
      loop -> thread: sync_to_async(Signal.asend.<locals>.sync_send)
    signal: request_finished  [worker]
    ...
```

A synchronous view still running when the loop has handled the disconnect runs to its end, and the same two lines follow:

```text recording=handlers
ASGI, GET /hang-sync/: the client disconnects during a synchronous view that is still running when the loop has handled it, synchronous middleware
...
    receive() from ASGIHandler.listen_for_disconnect -> http.disconnect  [loop]
    the view returns, after the centre's task on the loop has ended  [worker]
      loop -> thread: sync_to_async(Signal.asend.<locals>.sync_send)
    signal: request_finished  [worker]
    ...
```

A synchronous middleware's code still running when the loop has handled the disconnect, before the centre is handed over, has no task to cancel: the crossing stops waiting, and the thread runs the rest of the chain, the view included, for a response never sent. `handle` goes on at once to send `request_finished`, whose synchronous receivers wait for the thread and so run after the chain.

> **Trap.** Under ASGI no `process_response` runs once the loop has handled a disconnect while the view runs, whatever the view's kind: what a middleware does there is not done for that request, though `request_finished` is still sent.
