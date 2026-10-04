---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# Sync and async in one chain

How one chain serves both WSGI and ASGI when each of its layers may be synchronous or asynchronous: the two flags a middleware declares, the rule `BaseHandler.load_middleware` applies to them, and what each arrangement costs in crossings between the event loop and a thread.

A handler runs its chain in one of two modes. A `WSGIHandler` calls it as a function, and an `ASGIHandler` awaits it as a coroutine. The layers, though, are written by different people at different times: a middleware may be an ordinary callable or a coroutine function, and so may a view. Django makes every combination work by placing an adapter wherever two neighbours disagree.

The adapters come from asgiref, a small library that Django depends on. `sync_to_async` makes a function awaitable by running it in a thread, and `async_to_sync` makes a coroutine function callable by running it on an event loop and waiting for it (`asgiref:asgiref/sync.py:sync_to_async`, `asgiref:asgiref/sync.py:async_to_sync`). Each use is a crossing between the event loop and a thread, and this part of Django is designed to make as few of them as it can.

## The adapter

`BaseHandler.adapt_method_mode` is given the mode that is wanted and a method, and returns something that can be called in that mode (`django/core/handlers/base.py:BaseHandler.adapt_method_mode`).

| | the method is synchronous | the method is a coroutine function |
|---|---|---|
| **synchronous wanted** | the method, unchanged | `async_to_sync(method)` |
| **asynchronous wanted** | `sync_to_async(method, thread_sensitive=True)` | the method, unchanged |

It can be told which kind the method is. When it is not told, it asks `inspect.iscoroutinefunction`.

## What a middleware declares

A middleware factory says which modes it can run in through two attributes, which `load_middleware` reads from the class or the function itself.

| attribute | when it is absent | meaning |
|---|---|---|
| `sync_capable` | taken as true | the middleware can be given a synchronous inner layer and be called as a function |
| `async_capable` | taken as false | the middleware can be given a coroutine function and be awaited |

A middleware that says nothing is therefore synchronous only. One that sets both to false is refused with a `RuntimeError` when the chain is built. For a factory that is a function, the three decorators `sync_only_middleware`, `async_only_middleware` and `sync_and_async_middleware` set the pair (`django/utils/decorators.py:sync_and_async_middleware`).

`MiddlewareMixin` sets both to true and handles both modes itself. Its `__init__` looks at the inner layer it was given: if that is a coroutine function, the instance goes into async mode and marks itself as a coroutine function too, so that whatever wraps it next sees one. In async mode `MiddlewareMixin.__call__` hands over to `MiddlewareMixin.__acall__`, which awaits the inner layer and runs `process_request` and `process_response` each through `sync_to_async`, since those two methods are ordinary functions (`django/middleware/__init__.py:MiddlewareMixin.__init__`, `django/middleware/__init__.py:MiddlewareMixin.__acall__`).

Django's own middleware are nearly all built on the mixin, and nearly all of them turn its second flag off again.

> **Changed in 6.2.** Every middleware class Django ships that is built on `MiddlewareMixin` and has a `process_request` or a `process_response` sets `async_capable = False`. Before 6.2 they inherited the mixin's `True`. So under ASGI Django's own middleware now run synchronously, where they used to run in the mixin's async mode (`django/middleware/common.py:CommonMiddleware.async_capable`).

## The rule

As `load_middleware` works outwards from the centre it keeps track of the mode of the chain so far. At the centre that is the handler's own mode. For each middleware it then decides:

- If the chain so far is synchronous and the middleware can run synchronously, the middleware runs synchronously.
- Otherwise the middleware runs asynchronously if it is able to, and synchronously if it is not.

If the mode chosen differs from that of the chain so far, the chain so far is adapted before the middleware is given it. And when the loop ends, the outermost layer is adapted to the handler's mode (`django/core/handlers/base.py:BaseHandler.load_middleware`).

A chain that mixes the kinds shows the rule at work. In this recording of an `ASGIHandler` being made, A and C can run either way and B can only run synchronously:

```text
Making an ASGIHandler; A and C can run either way, B only synchronously
    C(get_response)    get_response is the wrapper around BaseHandler._get_response_async
    B(get_response)    get_response is async_to_sync(the wrapper around C)
    A(get_response)    get_response is the wrapper around B
    the chain: sync_to_async(the wrapper around A)
```

C sits on an asynchronous centre and can run asynchronously, so nothing is adapted. B cannot, so the chain so far is put inside `async_to_sync` before B is given it. A could run either way, but the layer inside it is now synchronous, so A runs synchronously too and nothing is adapted. At the top, one `sync_to_async` joins the synchronous chain to the asynchronous handler.

The rule keeps each layer in the mode of the layer inside it whenever the layer is able, so the mode changes only where it must. Under WSGI with ordinary middleware nothing is adapted at all.

## What the arrangements cost

Under ASGI, then, a chain of Django's own middleware is synchronous from top to bottom, around an asynchronous centre. This is a request for an async view through three such middleware. Every crossing made by one of the adapters is written down, and each hook says which thread it ran on.

```text
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

The first crossing and the last are made for every ASGI request, whatever its middleware: Django's own receivers of `request_started` are synchronous functions, and so is closing the response. Between them, the whole of the middleware is one call into a thread, and from inside it the centre of the chain is one call back to the event loop, where the view runs.

With a synchronous view there is one crossing more. The centre hands the view to a thread, and the thread that takes it is the same one: the worker that is waiting inside the middleware for the centre to return.

A chain of middleware that are built on `MiddlewareMixin` and leave the flag alone, as Django's own did before 6.2, runs in async mode instead. The chain itself then stays on the event loop, and each `process_request` and each `process_response` is a call into a thread and back: one for each of the two hooks a middleware has.

```text figure=crossings
A request for an async view under ASGI, through middleware A, B and C. Time runs left to right.

Synchronous middleware, as Django's own is:
  event loop:  handle                      the centre of the chain, the view                       send
  worker:              A B C process_request                                 C B A process_response
  (the middleware makes two calls between the loop and the worker: in, and back out to the centre)

MiddlewareMixin in async mode, as Django's own was before 6.2:
  event loop:  handle     .     .     .    the centre of the chain, the view    .     .     .      send
  worker:              A     B     C                                         C     B     A
                       (process_request)                                     (process_response)
  (the middleware makes six calls: each hook goes to the worker and returns to the loop)

Not drawn: the two crossings every ASGI request makes whatever its middleware,
for the receivers of request_started and for closing the response.
```

*The same request under the two arrangements. Synchronous middleware run together on the worker thread, and the chain leaves it once, for the centre. Middleware in async mode stay on the event loop and send each hook to the worker separately. The two crossings that every request makes, for the receivers of `request_started` and for closing the response, are not drawn.*

Neither arrangement is free. In the first a thread is busy for the whole request: it is inside the middleware's call, waiting, for as long as the view takes. In the second the request's thread is idle while the view runs, and the price is the repeated switching. The release notes for 6.2 give that switching as the reason for the change, and say that a deployment with high in-process concurrency over I/O that is not the ORM's may prefer the old behaviour, and can restore it by setting `async_capable = True` (`docs/releases/6.2.txt`).

## One thread per request

The crossings on the path through the chain (into a layer, a hook, the view, the rendering of a template, the conversion of an exception) are all made with `thread_sensitive=True`, and `ASGIHandler.__call__` runs each request inside asgiref's `ThreadSensitiveContext`. Together these mean that all of this code runs on one thread for the length of a request, however many separate crossings reach it, and that two requests do not share a thread. The last line of the recording above is the recorder's own count.

The thread is made at a request's first such crossing and lasts until the request ends. Because Django's own receivers of `request_started` are synchronous, the first crossing comes before the request object even exists. Every ASGI request therefore has a thread of its own, whatever its middleware and its view (`asgiref:asgiref/sync.py:SyncToAsync.__call__`).

Two crossings are not thread-sensitive, and use the event loop's ordinary pool of threads: the logging of a response in `BaseHandler.get_response_async`, and writing the request body to its temporary file once that file is on disk.

The single thread matters because of what Django keeps per thread. A database connection belongs to the thread that opened it (`django/db/utils.py:ConnectionHandler.thread_critical`), so a middleware's `process_request` and the view it precedes see the same connection, and the same transaction, only if they run on the same thread.

## Hooks and views

The three lists of hooks are adapted separately from the layers. A `process_view` or a `process_template_response` is adapted to the handler's mode when it is filed, whatever mode its middleware runs in as a layer. Under ASGI, then, a synchronous `process_view` is a crossing of its own for every request. The `process_exception` hooks are kept synchronous in both modes and reached, under ASGI, through one `sync_to_async` around the whole list.

A view is adapted at the moment it is called. Under ASGI a synchronous view runs on the request's thread, through `sync_to_async`. Under WSGI an async view is run by `async_to_sync`, on a thread of its own, while the thread that called the handler waits for it. Such a view can still await several things at once. It gains nothing between requests, and for its length it occupies two threads where a synchronous view would occupy one.
