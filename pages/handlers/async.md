---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# Sync and async in one chain

Synchronous and asynchronous code meet in one middleware chain: a handler calls its chain under WSGI and awaits it under ASGI, each middleware and the view may be either kind, and wherever two neighbours differ an adapter must join them, at the price of a switch between the event loop and a thread. A middleware declares its modes with `sync_capable` and `async_capable`, `BaseHandler.load_middleware` gives each layer one, and asgiref's `sync_to_async` and `async_to_sync` are the adapters.

`sync_to_async` makes a function awaitable by running it in a thread, and `async_to_sync` makes a coroutine function callable by running it on an event loop and waiting for it (`asgiref:asgiref/sync.py:sync_to_async`, `asgiref:asgiref/sync.py:async_to_sync`). Each use is a **crossing** between the event loop and a thread, and Django is built to make as few as it can.

## The adapter: `adapt_method_mode`

`BaseHandler.adapt_method_mode` fits a method to the mode wanted: a coroutine function wanted synchronous is wrapped in `async_to_sync`, a function wanted asynchronous in `sync_to_async` with `thread_sensitive=True`, which keeps it on the request's one thread ([One thread per request](#one-thread-per-request)), and a method already in that mode is returned unchanged (`django/core/handlers/base.py:BaseHandler.adapt_method_mode`).

## What a middleware declares

A middleware factory, a class or a function, says which modes it can run in with two attributes: `sync_capable`, true when absent, that it can be given a synchronous inner layer and be called, and `async_capable`, false when absent, that it can be given a coroutine function and be awaited. A middleware that says nothing is therefore synchronous only; one that sets both to false is refused with a `RuntimeError` when the chain is built. For a function, the decorators `sync_only_middleware`, `async_only_middleware` and `sync_and_async_middleware` set the pair (`django/utils/decorators.py:sync_and_async_middleware`).

`MiddlewareMixin` sets both to true and handles both modes itself. Its `__init__` looks at the inner layer it was given: if that is a coroutine function, the instance goes into async mode and marks itself as a coroutine function too, so that whatever wraps it next sees one. In async mode `MiddlewareMixin.__call__` hands over to `MiddlewareMixin.__acall__`, which awaits the inner layer and runs `process_request` and `process_response` each through `sync_to_async` (`django/middleware/__init__.py:MiddlewareMixin.__init__`, `django/middleware/__init__.py:MiddlewareMixin.__acall__`).

Django's own middleware are nearly all built on the mixin, and nearly all turn its second flag off again.

> **Changed in 6.2.** Every middleware class Django ships that is built on `MiddlewareMixin` and has a `process_request` or a `process_response` sets `async_capable = False`. Before 6.2 they inherited the mixin's `True`. So under ASGI they now run synchronously, where they used to run in the mixin's async mode (`django/middleware/common.py:CommonMiddleware.async_capable`).

## How a layer's mode is chosen

As `BaseHandler.load_middleware` works outwards from the centre it tracks the mode of the chain so far, at the centre the handler's own. Each middleware takes the mode of the chain inside it if it can run in that mode, and the other mode if it cannot. If the two modes differ, the chain so far is adapted before the middleware is given it, and when the loop ends the outermost layer is adapted to the handler's mode (`django/core/handlers/base.py:BaseHandler.load_middleware`).

A, B and C are three middleware that write down each hook as Django calls it. When an `ASGIHandler` is made with A and C able to run either way and B only synchronously, the mode changes at B and at the top:

```text recording=handlers
Making an ASGIHandler; A and C can run either way, B only synchronously
    C(get_response)    get_response is the wrapper around BaseHandler._get_response_async
    B(get_response)    get_response is async_to_sync(the wrapper around C)
    A(get_response)    get_response is the wrapper around B
    the chain: sync_to_async(the wrapper around A)
```

B cannot run asynchronously, so it takes the other mode and is given the chain so far inside `async_to_sync`. A can run either way and takes B's, and one `sync_to_async` joins the top to the asynchronous handler.

## What the arrangements cost

Under ASGI, then, a chain of Django's own middleware that turn `async_capable` off is synchronous throughout, around an asynchronous centre. For an async view ([Asynchronous views](../views/async.md)) the layers cost two crossings in all, into a thread at the top and back to the event loop for the centre; the request's first crossing comes before the chain, and its last after the response is sent:

```text recording=handlers
ASGI, GET /async/: an async view, synchronous middleware
      loop -> thread: sync_to_async(Signal.asend.<locals>.sync_send)
      loop -> thread: sync_to_async(the wrapper around A)
    A.process_request  [worker]
    B.process_request  [worker]
    C.process_request  [worker]
      thread -> loop: async_to_sync(the wrapper around BaseHandler._get_response_async)
    the view (async def)  [loop]
    C.process_response(200)  [worker]
    B.process_response(200)  [worker]
    A.process_response(200)  [worker]
    send(http.response.start)  [loop]
    send(http.response.body)  [loop]
      loop -> thread: sync_to_async(HttpResponseBase.close)
    (everything marked worker ran on 1 thread)
```

Every ASGI request that is answered makes the first and last, whatever its middleware: Django's own receivers of `request_started` are synchronous, and so is closing the response (`django/dispatch/dispatcher.py:Signal.asend`, `django/core/handlers/asgi.py:ASGIHandler.handle`).

With a synchronous view there is one crossing more ([The centre of the chain](view.md)): the centre resolves the URL on the event loop's thread and hands the view, a function named plain, back to the thread that ran the middleware:

```text recording=handlers
ASGI, GET /plain/: a synchronous view, synchronous middleware, as the server sees it
...
      thread -> loop: async_to_sync(the wrapper around BaseHandler._get_response_async)
    BaseHandler.resolve_request  [loop]
      loop -> thread: sync_to_async(plain)
    the view  [worker]
...
    (everything marked worker ran on 1 thread)
```

The thread can run the view while it waits inside the middleware: until the centre returns, `async_to_sync` keeps it in a `CurrentThreadExecutor`, which runs on it any thread-sensitive code the centre calls through `sync_to_async` (`asgiref:asgiref/sync.py:AsyncToSync.__call__`, `asgiref:asgiref/current_thread_executor.py:CurrentThreadExecutor.run_until_future`).

A chain of middleware built on `MiddlewareMixin` that leave the flag alone, as Django's own did before 6.2, runs in async mode instead: the chain stays on the event loop, and each `process_request` and each `process_response` is a call into a thread and back. The figure draws the two arrangements, time running left to right.

```text figure=crossings
A request for an async view under ASGI, through middleware A, B and C. Time runs left to right.

Synchronous middleware, as most of Django's own is:
  event loop:  handle                      the centre of the chain, the view                       send
  worker:              A B C process_request                                 C B A process_response
  (the middleware makes two calls between the loop and the worker: in, and back out to the centre)

MiddlewareMixin in async mode, as Django's own was before 6.2:
  event loop:  handle     .     .     .    the centre of the chain, the view    .     .     .      send
  worker:              A     B     C                                         C     B     A
                       (process_request)                                     (process_response)
  (the middleware makes six calls: each hook goes to the worker and returns to the loop)

Not drawn: the two crossings every answered ASGI request makes whatever its middleware,
for the receivers of request_started and for closing the response.
```

*The same request under the two arrangements. Synchronous middleware run together on the worker thread, and the chain leaves it once, for the centre; middleware in async mode stay on the event loop and send each hook to the worker. The two crossings every answered request makes, for the receivers of `request_started` and for closing the response, are not drawn.*

Neither arrangement spares the request its thread ([One thread per request](#one-thread-per-request)); they differ in where it is while an async view runs. Under synchronous middleware it is inside their call, waiting in `async_to_sync` for the centre; in async mode it is idle in its executor from the last `process_request` to the first `process_response`, and the second pays in switching (`asgiref:asgiref/sync.py:SyncToAsync.__call__`).

> **Why.** 6.2 turned `async_capable` off to avoid the repeated switching in `MiddlewareMixin.__acall__`. Its release notes allow that for high in-process concurrency over I/O that is not the ORM's, "where no thread is otherwise held", the switching may be preferable to "pinning a thread per request" (`docs/releases/6.2.txt`). The documentation says that with synchronous middleware around an async view Django will "hold the sync thread open for middleware exception propagation" (`docs/topics/async.txt`).

A `process_view` or a `process_template_response` is adapted to the handler's mode as it is filed ([Building the middleware chain](chain.md#the-three-lists-of-hooks)), so under ASGI a synchronous `process_view` is a crossing of its own on each call, whatever mode its middleware runs in (`django/core/handlers/base.py:BaseHandler.load_middleware`).

> **Trap.** Under WSGI an async view gains nothing between requests. The centre runs it through `async_to_sync`, on an event loop in a thread of its own, while the handler's thread waits (`django/core/handlers/base.py:BaseHandler._get_response`, `asgiref:asgiref/sync.py:AsyncToSync.__call__`). It can still await several things at once, but it occupies two threads where a synchronous view would occupy one; as the documentation says, "you will not get the benefits of an async stack" (`docs/topics/async.txt`).

## One thread per request

The crossings into a thread on the path through the chain are all made with `thread_sensitive=True`, and `ASGIHandler.__call__` runs each request inside asgiref's `ThreadSensitiveContext`. Together these mean that everything those crossings run for one request runs on one thread for the length of the request, and that two requests do not share a thread (`django/core/handlers/asgi.py:ASGIHandler.__call__`).

Two requests sent at once under one event loop, each view waiting until the other's is running, keep to a thread each. Only lines run on a worker are kept, and the quote shows each view's:

```text recording=handlers
ASGI, GET /together/ twice at once under one event loop, synchronous middleware: the threads
    request 1:
...
        the view, waiting until the other request's view is running too  [worker 1]
...
    request 2:
...
        the view, waiting until the other request's view is running too  [worker 2]
...
    (no thread ran lines of both requests)
```

The thread is made at a request's first thread-sensitive crossing, the one for `request_started`, and lasts until the request ends: every request that gets that far has a thread of its own, whatever its middleware and its view (`asgiref:asgiref/sync.py:SyncToAsync.__call__`).

The single thread matters because a database connection belongs to the thread that opened it (`django/db/utils.py:ConnectionHandler.thread_critical`): a middleware's `process_request` and the view it precedes see the same connection, and the same transaction, only on the same thread.
