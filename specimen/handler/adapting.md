---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
status: verified
owns: "`BaseHandler.adapt_method_mode`"
---

# Sync and async at the handler

What does `BaseHandler.adapt_method_mode` return, for each pairing of the mode wanted with the mode it is told a method is in, or finds it in?

`BaseHandler.adapt_method_mode` is told which mode is wanted (`is_async=True` or `is_async=False`) and may be told which mode the method is in; told nothing of that (`method_is_async=None`), it asks `inspect.iscoroutinefunction`. With `is_async=True` and a method that is not in the asynchronous mode, it returns `sync_to_async(method, thread_sensitive=True)`; with `is_async=False` and a method that is, it returns `async_to_sync(method)`; otherwise it returns the method it was given (`django/core/handlers/base.py:BaseHandler.adapt_method_mode`). `sync_to_async` is `asgiref`'s (`asgiref:asgiref/sync.py:sync_to_async`).

## What does `BaseHandler.adapt_method_mode` return?

`BaseHandler.adapt_method_mode` is told which mode is wanted (`is_async=True` or `is_async=False`) and may be told which mode the method is in; told nothing of that (`method_is_async=None`), it asks `inspect.iscoroutinefunction`. With `is_async=True` and a method that is not in the asynchronous mode, it returns `sync_to_async(method, thread_sensitive=True)`; with `is_async=False` and a method that is, it returns `async_to_sync(method)`; otherwise it returns the method it was given (`django/core/handlers/base.py:BaseHandler.adapt_method_mode`).

## What is `sync_to_async`?

`sync_to_async` is `asgiref`'s: a function with two `typing.overload` signatures before its definition (`asgiref:asgiref/sync.py:sync_to_async`). Called with a function, it returns the result of calling `SyncToAsync` on it; called without one, it returns a `lambda` that takes the function and does that (`asgiref:asgiref/sync.py:sync_to_async`).

`SyncToAsync.__init__` raises `TypeError` when its argument is not callable, is a coroutine function, or has a `__call__` that is one (`asgiref:asgiref/sync.py:SyncToAsync.__init__`).

## Where does the handler get `iscoroutinefunction`?

The name `iscoroutinefunction` that the handlers' base module calls is bound there by an import: the module takes the function by name from `inspect` (`django/core/handlers/base.py:iscoroutinefunction`).

## Where is each of these in the source?

| what | whose | where |
|---|---|---|
| `BaseHandler.adapt_method_mode` | Django's | `django/core/handlers/base.py:BaseHandler.adapt_method_mode` |
| `sync_to_async` | `asgiref`'s | `asgiref:asgiref/sync.py:sync_to_async` |
| `SyncToAsync` | `asgiref`'s | `asgiref:asgiref/sync.py:SyncToAsync` |
| `iscoroutinefunction`, as the handlers' base module binds it | the standard library's, imported | `django/core/handlers/base.py:iscoroutinefunction` |
