---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: verified
contents: chain, adapting, exceptions
---

# The handler

An instance of `WSGIHandler` itself runs `BaseHandler.load_middleware` as it is made, and `BaseHandler.adapt_method_mode` wraps a method in `sync_to_async` or in `async_to_sync` when the mode it is told the method is in, or finds it in, is not the mode asked for.

`WSGIHandler.__init__` ends by calling the method named `"load_middleware"` on the handler being made, which on an instance of `WSGIHandler` itself is `BaseHandler.load_middleware` (`django/core/handlers/wsgi.py:WSGIHandler.__init__`). `BaseHandler.adapt_method_mode` is told which mode is wanted (`is_async=True` or `is_async=False`) and may be told which mode the method is in; told nothing of that (`method_is_async=None`), it asks `inspect.iscoroutinefunction`. With `is_async=True` and a method that is not in the asynchronous mode, it returns `sync_to_async(method, thread_sensitive=True)`; with `is_async=False` and a method that is, it returns `async_to_sync(method)`; otherwise it returns the method it was given (`django/core/handlers/base.py:BaseHandler.adapt_method_mode`).

## How are this part's figures read?

A box is a call, named by what is called. What is drawn inside a box is what that call does, from top to bottom, and a dashed box is a loop. An arrow is a call, from the box above to the box below. [The chain being built](handler/chain.md#figure-building-the-chain) is drawn this way. The figure planned for [how an exception becomes a response](handler/exceptions.md) is to be drawn from a recording.
