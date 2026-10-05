---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Building the middleware chain

How `BaseHandler.load_middleware` turns the list in `settings.MIDDLEWARE` into one callable: the order it works in, what it asks of a middleware, and the three lists of hooks it fills on the way.

Each entry of `settings.MIDDLEWARE` is the dotted path of a **factory**: something that is given the next layer inwards and returns the middleware itself, a callable that takes a request and returns a response. A class whose `__init__` accepts the inner layer and which defines `__call__` is the usual form, and by convention the argument is called `get_response`. A function that returns a function serves as well.

## When the chain is built

`WSGIHandler.__init__` and `ASGIHandler.__init__` each end by calling `load_middleware` on the handler being made, the second with `is_async=True` (`django/core/handlers/wsgi.py:WSGIHandler.__init__`, `django/core/handlers/asgi.py:ASGIHandler.__init__`). A process makes its handler once, so the chain is built once, as the server starts, and that is when each factory runs. A middleware's `__init__` is startup code: what it reads from the settings it reads then, and it is not called again for any request.

## The loop

`BaseHandler.load_middleware` starts at the centre and works outwards (`django/core/handlers/base.py:BaseHandler.load_middleware`).

It begins with `BaseHandler._get_response`, or with `BaseHandler._get_response_async` when the handler is asynchronous, wrapped in `convert_exception_to_response`. That is the first value of a local variable holding the chain so far. Then, for each path in `settings.MIDDLEWARE`, taken in reverse:

1. It imports the factory with `import_string`.
2. It decides whether this layer will run synchronously or asynchronously and, if the chain so far runs the other way, puts an adapter around the chain so far. [Sync and async in one chain](async.md) explains the decision.
3. It calls the factory with the chain so far. What comes back is the middleware: the new layer.
4. It looks on the new layer for three optional methods, and files each one it finds in a list.
5. It wraps the new layer in `convert_exception_to_response`, and that wrapper becomes the chain so far.

After the loop it adapts the outermost wrapper to the handler's own mode and stores it as `BaseHandler._middleware_chain`. That assignment is the method's last statement on purpose. The attribute is `None` until then, and doubles as the sign that the handler is ready: the test client's handlers test it on each request to decide whether the chain has still to be built.

In this recording of a `WSGIHandler` being made with `MIDDLEWARE = [A, B, C]`, each middleware writes a line when its factory is called, saying what it was given.

```text recording=handlers
Making a WSGIHandler builds the chain, last middleware first
    C(get_response)    get_response is the wrapper around BaseHandler._get_response
    B(get_response)    get_response is the wrapper around C
    A(get_response)    get_response is the wrapper around B
```

The third step can end otherwise.

A factory may decline. If it raises `MiddlewareNotUsed`, the loop goes on to the next path and the chain so far stays as it was, so the layer is simply absent. When `settings.DEBUG` is true the fact is logged at the debug level. This is the way for a middleware to take itself out according to configuration. None of the middleware Django ships does so: the exception exists for the middleware a project writes (`django/core/exceptions.py:MiddlewareNotUsed`).

A factory must return something. If it returns `None`, `load_middleware` raises `ImproperlyConfigured`, with a message that names the factory.

## The three lists of hooks

Besides being a layer of the chain, a middleware may define any of three methods that the centre of the chain calls directly. `load_middleware` collects them as it goes, into three lists on the handler.

| a middleware's method | kept in | order | called |
|---|---|---|---|
| `process_view` | `BaseHandler._view_middleware` | as in the setting | before the view, with the view and its arguments |
| `process_template_response` | `BaseHandler._template_response_middleware` | the setting reversed | after the view, when the response can still be rendered |
| `process_exception` | `BaseHandler._exception_middleware` | the setting reversed | when the view, or the rendering of a template response, raises an exception |

*The three lists a handler keeps beside the chain. The centre of the chain is what calls them, and [The centre of the chain](view.md) says when.*

The orders fall out of the loop. It runs through the setting backwards, and it puts each `process_view` at the front of its list and each of the other two at the end of theirs. The result agrees with the onion: a hook that runs before the view runs outermost first, and a hook that runs after it runs innermost first.

Each method is adapted to the handler's own mode as it is filed, so that the centre can call it directly. The `process_exception` hooks are different: they are filed as synchronous whatever the mode, and a comment at that line says the exception-handling stack is, for now, always synchronous.

## What the handler does not know about

`process_request` and `process_response`, the two best-known middleware methods, appear nowhere in the handler. They belong to `MiddlewareMixin`, and what they mean is a few lines of `MiddlewareMixin.__call__` (`django/middleware/__init__.py:MiddlewareMixin.__call__`):

1. If the class has a `process_request`, call it with the request.
2. If that returned a response, keep it. Otherwise call the layer inside.
3. If the class has a `process_response`, pass the response through it.
4. Return the response.

So the rule that a `process_request` returning a response skips the view is no rule of the handler's. It is the second step above, and a middleware that is not built on `MiddlewareMixin` has these two hooks only if it implements them itself.

> **Changed in 6.2.** `MiddlewareMixin` is defined in `django/middleware/__init__.py`. It used to live in `django/utils/deprecation.py`; importing it from there still works, and warns with `RemovedInDjango2029Warning` (`django/utils/deprecation.py:__getattr__`).
