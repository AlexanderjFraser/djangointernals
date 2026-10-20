---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# Building the middleware chain

`BaseHandler.load_middleware` turns the list in `settings.MIDDLEWARE` into one callable, the middleware chain: the order it works in, what it asks of a middleware, and the three lists of hooks it fills on the way. The two best-known hooks, `process_request` and `process_response`, are not among them: they are `MiddlewareMixin`'s.

Each entry of `settings.MIDDLEWARE` is the dotted path of a **factory**: something that is called with the chain inside it and returns the middleware itself, a callable that takes a request and returns a response. A class whose `__init__` accepts that chain and which defines `__call__` is the usual form, and by convention the argument is called `get_response`. A function that returns a function serves as well.

## When the chain is built

`WSGIHandler.__init__` and `ASGIHandler.__init__` each end by calling `load_middleware` on the handler being made, the second with `is_async=True` (`django/core/handlers/wsgi.py:WSGIHandler.__init__`, `django/core/handlers/asgi.py:ASGIHandler.__init__`). A serving process makes its handler once, as it loads the application, so its chain is built once, and that is when each factory runs. A middleware's `__init__` is startup code: what it reads from the settings it reads then, and it is not called again for any request. The test client's handlers, `ClientHandler` and `AsyncClientHandler`, build their chain instead at their first request, when they find the attribute that holds it still `None` ([The test client: `Client` and `ClientHandler`](../testing/client.md#the-servers-part-clienthandler__call)) (`django/test/client.py:ClientHandler.__call__`, `django/test/client.py:AsyncClientHandler.__call__`).

## From the centre outwards

`BaseHandler.load_middleware` starts at the centre, the innermost layer, and works outwards (`django/core/handlers/base.py:BaseHandler.load_middleware`).

It begins with `BaseHandler._get_response`, or with `BaseHandler._get_response_async` when the handler is asynchronous, wrapped in `convert_exception_to_response`. That is the first value of a local variable holding the chain so far. Then, for each path in `settings.MIDDLEWARE`, taken in reverse:

1. It imports the factory with `import_string`.
2. It decides whether this layer will run synchronously or asynchronously and, if the chain so far runs the other way, puts an adapter around the chain so far. [Sync and async in one chain](async.md) explains the decision.
3. It calls the factory with the chain so far. What comes back is the middleware: the new layer.
4. It looks on the new layer for three optional methods, and files each one it finds in a list.
5. It wraps the new layer in `convert_exception_to_response`, and that wrapper becomes the chain so far.

After the loop it adapts the outermost wrapper to the handler's own mode and stores it as `BaseHandler._middleware_chain`. That assignment is the method's last statement on purpose: the attribute is `None` until then, and doubles as the sign that the chain is complete.

A, B and C are three middleware that write down each hook as Django calls it. When a `WSGIHandler` is made with `MIDDLEWARE = [A, B, C]`, each writes a line as its factory is called, saying what it was given. C, the last in the setting, is made first, and each is given the wrapper around the layer inside it, never that layer itself.

```text recording=handlers
Making a WSGIHandler builds the chain, last middleware first
    C(get_response)    get_response is the wrapper around BaseHandler._get_response
    B(get_response)    get_response is the wrapper around C
    A(get_response)    get_response is the wrapper around B
```

The third step can end otherwise. A factory may decline: if it raises `MiddlewareNotUsed`, the loop goes on to the next path and the chain so far stays as it was. The layer is simply absent: with `MIDDLEWARE = [A, Unused, C]`, where *Unused* declines, the next factory, A, is given the wrapper around C.

```text recording=handlers
MIDDLEWARE = [A, Unused, C], where Unused raises MiddlewareNotUsed: it is left out of the chain
    C(get_response)    get_response is the wrapper around BaseHandler._get_response
    A(get_response)    get_response is the wrapper around C
```

Raising `MiddlewareNotUsed` lets a middleware take itself out according to configuration, and none of the middleware Django ships does so (`django/core/exceptions.py:MiddlewareNotUsed`).

A factory must return something. If it returns `None`, `load_middleware` raises `ImproperlyConfigured`, with a message that names the factory.

## The three lists of hooks

Besides being a layer of the chain, a middleware may define any of three methods that the centre of the chain calls. `load_middleware` collects them as it goes, into three lists on the handler.

| a middleware's method | kept in | called |
|---|---|---|
| `process_view` | `BaseHandler._view_middleware` | before the view, with the view and its arguments |
| `process_template_response` | `BaseHandler._template_response_middleware` | after the view, or a `process_view` hook that answers, when the response has a callable `render` |
| `process_exception` | `BaseHandler._exception_middleware` | when the view, or the rendering of a template response, raises an exception |

*The three lists a handler keeps beside the chain. The centre of the chain is what calls them, and [The centre of the chain](view.md) says when.*

The orders fall out of the loop. It runs through the setting backwards, and it puts each `process_view` at the front of its list and each of the other two at the end of theirs (`django/core/handlers/base.py:BaseHandler.load_middleware`). So a handler made with `MIDDLEWARE = [A, B, C]` keeps its `process_view` hooks in the setting's order, and the other two in reverse.

```text recording=handlers
The three lists of hooks, as the handler keeps them
    _view_middleware: A, B, C
    _template_response_middleware: C, B, A
    _exception_middleware: C, B, A
```

The result agrees with the onion: a hook that runs before the view runs outermost first, and a hook that runs after it runs innermost first.

The `process_view` and `process_template_response` hooks are adapted to the handler's own mode as they are filed, so that the centre can call them directly.

> **Trap.** The handler never awaits an `async def process_exception`, in either mode. Every `process_exception` hook is filed synchronous, the handling of exceptions being still synchronous throughout (`django/core/handlers/base.py:BaseHandler.load_middleware`), and filing a coroutine function synchronous, `BaseHandler.adapt_method_mode` wraps it in `async_to_sync` ([Sync and async in one chain](async.md)) (`django/core/handlers/base.py:BaseHandler.adapt_method_mode`). Under ASGI the centre calls the hooks from a thread, through `sync_to_async`, and an async hook is sent back to the event loop to run while that thread waits, a trip a synchronous hook does not make (`django/core/handlers/base.py:BaseHandler._get_response_async`). Under WSGI, unless a layer runs asynchronously, each call of the hook starts an event loop in a new thread (`asgiref:asgiref/sync.py:AsyncToSync.__call__`).

## The hooks of `MiddlewareMixin`

`process_request` and `process_response`, the two best-known middleware methods, appear nowhere in the handler. They belong to `MiddlewareMixin`, and a middleware not built on it has them only if it implements them itself. When the layer runs synchronously, `MiddlewareMixin.__call__` gives the request to `process_request`, if the class has one, and calls the layer inside only if that returned no response, which is how such a response skips the view; then it gives the response it holds, whichever made it, to `process_response`, if the class has one, and returns what that returns (`django/middleware/__init__.py:MiddlewareMixin.__call__`).

> **Changed in 6.2.** `MiddlewareMixin` is defined in `django/middleware/__init__.py`. It used to live in `django/utils/deprecation.py`; importing it from there still works, and warns with `RemovedInDjango2029Warning` (`django/utils/deprecation.py:__getattr__`).

Nothing inside B runs when B's `process_request` answers: not C, and not the centre, so neither a `process_view` hook nor the view. B's own `process_response` still runs, before A's.

```text recording=handlers
WSGI, GET /plain/: B.process_request returns a response
...
    A.process_request
    B.process_request, returning a response
    B.process_response(200)
    A.process_response(200)
    ...
```

> **History.** Before 1.10 the layers were not strict. A response that one middleware's `process_request` returned still passed through the `process_response` of every middleware, those that never saw the request included, so a middleware's `process_response` could not count on its own `process_request` having run. DEP 5 made the layers strict, like an onion: each factory is called with the chain inside it, and a response returned early goes back out through the middleware listed before it, never through those listed after. Django 1.10 shipped the new style, in a new setting, `MIDDLEWARE`, "to solve the lack of strict request/response layering" of the old (`docs/releases/1.10.txt`). To carry the old hooks over, DEP 5 offered a mixin, `MiddlewareMixin`, "to ease providing the existing built-in middleware in both new-style and old-style forms, and to ease similar conversions of third-party middleware" (`deps:final/0005-improved-middleware.rst`).
