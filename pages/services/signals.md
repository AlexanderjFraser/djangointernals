---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# Signals: `Signal`, receivers and sending

How a `Signal` keeps its receivers and calls them: `Signal.connect`, `Signal.disconnect` and the `receiver` decorator, the weak references, the four ways of sending (`Signal.send`, `Signal.send_robust`, `Signal.asend`, `Signal.asend_robust`), and the cache of each sender's receivers that the model signals keep.

The dispatcher has no registry. A signal is an object, each of Django's made once at module level, that holds its own list, `Signal.receivers` (`django/dispatch/dispatcher.py:Signal.__init__`). An entry is a tuple of four: a lookup key, which pairs an identity for the receiver with one for the sender it was connected for; the receiver, or a weak reference to it; a weak reference to the sender, or `None`; and whether the receiver is a coroutine function. Connecting appends an entry. Sending picks out the entries for one sender, turns their references back into callables, and calls them. A `threading.Lock`, `Signal.lock`, guards every change to the list.

## Connecting a receiver: `Signal.connect`

`Signal.connect` takes the receiver, a sender (`None`, the default, means every sender), whether to hold the receiver weakly, and a dispatch uid (`django/dispatch/dispatcher.py:Signal.connect`). When the settings are configured and `settings.DEBUG` is true, it first refuses a receiver that is not callable, with `TypeError`, and one that does not accept `**kwargs`, with `ValueError`: every receiver is called with two keyword arguments, signal and sender, besides those of the send. Otherwise a receiver without `**kwargs` is connected, and fails with `TypeError` at the first send that passes it an argument it does not name.

The lookup key pairs the receiver's identity with the sender's, each from `_make_id`: the object's `id`, or for a bound method, which Python makes anew at each attribute access, the `id` of its instance and of its function (`django/dispatch/dispatcher.py:_make_id`). A dispatch uid, when given, takes the receiver's place. An entry whose key is in the list already is not added, so a function connected twice for one sender is one entry, a method of two instances is two, and of two receivers given one uid for one sender the first is kept.

By default the entry holds a `weakref.ref` to the receiver, or for a bound method a `weakref.WeakMethod`, which dies with the instance; with `weak=False` it holds the receiver itself. `inspect.iscoroutinefunction` tells, before the wrapping, whether it is a coroutine function. The sender is held weakly too where it can be, and the comment gives the reason: its receivers are then cleared when it is garbage collected, so that two senders whose lifetimes do not overlap, and which can have one `id`, are not taken for one. A sender that cannot be weakly referenced, such as a string, is kept only as its `id`. Then, under the lock, `connect` sweeps out dead entries, appends the new one unless its key is there, and empties the signal's cache.

The `receiver` decorator calls `connect` with its keyword arguments, for one signal or for each of a list of them, and returns the function unchanged; one decorated at module level is then held alive by its module's name for it (`django/dispatch/dispatcher.py:receiver`). The documentation has receivers connected in an application's `AppConfig.ready`, as the example's notices does (`docs/topics/signals.txt`).

## Disconnecting: `Signal.disconnect`

`Signal.disconnect` makes the same key, removes the entry with that key, and returns `True`, or `False` when there was none (`django/dispatch/dispatcher.py:Signal.disconnect`). The sender is part of the key, so a receiver connected for every sender is not removed by a disconnect that names one. Like `connect`, it sweeps out dead entries and empties the cache.

## Sending: `Signal.send`

`Signal.send` returns an empty list at once, without taking the lock, when the signal has no entries or its cache records that this sender has none (`django/dispatch/dispatcher.py:Signal.send`). Otherwise `Signal._live_receivers` keeps the entries connected for this sender or for every sender, in the order they were connected, resolves each weak reference, skips an entry whose receiver or sender has died, and returns two lists: the synchronous receivers and the coroutine functions (`django/dispatch/dispatcher.py:Signal._live_receivers`).

`send` calls the synchronous receivers one after another in the calling thread. If there are coroutine functions, it then makes one `async_to_sync` call of a coroutine that runs them through `_run_parallel`, each as a task of one `asyncio.TaskGroup`, so that they run concurrently, all in one copy of the caller's context, their results kept in the receivers' order (`django/dispatch/dispatcher.py:_run_parallel`). asgiref runs that coroutine on the event loop of the asynchronous code that called into this thread, if there is one, and otherwise on a new loop in a thread of its own while the calling thread waits (`asgiref:asgiref/sync.py:AsyncToSync.__call__`). The list returned pairs each receiver with what it returned, the synchronous ones first.

```text figure=one-send
Receivers connected in the order a (sync), b (async), c (sync), d (async).

Signal.send(sender, **named), from synchronous code
  in the calling thread, in order:  a(signal=..., sender=..., **named), then c(...)
  then one async_to_sync call, on an event loop:
    b(...) and d(...) started together in one TaskGroup, run concurrently
  returned: [(a, its result), (c, ...), (b, ...), (d, ...)]

await Signal.asend(sender, **named), from asynchronous code
  one sync_to_async call, on one thread, in order:  a(...), then c(...)
  then on the caller's event loop:
    b(...) and d(...) started together in one TaskGroup, run concurrently
  returned: [(a, its result), (c, ...), (b, ...), (d, ...)]

Under both: an exception in a receiver ends the send and reaches the caller;
send_robust and asend_robust catch an Exception and return it in the receiver's place.
```

*One send and one asend with the same four receivers. Each calls the synchronous receivers first, in order, then runs the coroutine functions together, and returns the pairs in the order a, c, b, d.*

A receiver that raises ends the send, and `send` lets the exception through. A synchronous receiver's comes out at once, and no receiver after it runs. Among the coroutine functions, the task group cancels those still running when one fails, and `_run_parallel` raises a lone exception as itself, two or more as the group, an `ExceptionGroup` when each is an `Exception`. When the group is over, `_restore_context` sets each context variable the receivers changed in the context that awaited `_run_parallel`, which under `send` asgiref copies back to the calling thread, so a value a coroutine receiver sets reaches the code that sent the signal (`django/dispatch/dispatcher.py:_restore_context`, `asgiref:asgiref/sync.py:AsyncToSync.__call__`).

> **Trap.** `send` called in a thread that is running an event loop, in an `async def` view say, raises asgiref's `RuntimeError` when any receiver is a coroutine function, and only after the synchronous receivers have run. Asynchronous code sends with `asend`.

> **Changed in 6.1.** The coroutine receivers used to be run with asyncio's gather (`docs/topics/signals.txt`).

## Robust sending: `Signal.send_robust`

`Signal.send_robust` calls the receivers in the same order, but catches any `Exception` a receiver raises, logs it with its traceback on the logger `"django.dispatch"`, and puts the exception in that receiver's place in the list (`django/dispatch/dispatcher.py:Signal.send_robust`). Each coroutine receiver is wrapped in a coroutine that catches its exception, so the task group sees no failure and cancels nothing. An exception that is not an `Exception`, such as `KeyboardInterrupt`, still ends the send.

## Sending from asynchronous code: `Signal.asend`

`Signal.asend` keeps the grouping the other way round: the synchronous receivers are gathered into one function, called through a single `sync_to_async`, so on one thread and in order, and then the coroutine functions run together through `_run_parallel` on the caller's loop (`django/dispatch/dispatcher.py:Signal.asend`). The pairs come back in the same order as from `send`, and `Signal.asend_robust` is to `asend` what `send_robust` is to `send`. The ASGI handler sends `request_started` with `asend`, and [Sync and async in one chain](../handlers/async.md) records the crossing its synchronous receivers cost each request.

## Dead receivers

When a receiver or a sender held weakly is garbage collected, the reference's callback, `Signal._flag_dead_receivers`, only sets a flag. The comment gives the reason: the callback is a side effect of garbage collection, and can come while the thread already holds the signal's lock, which as a `threading.Lock` it cannot take again. `Signal._clear_dead_receivers` sweeps the list, under the lock, when the flag is set, from `connect`, `disconnect` and `_live_receivers` (`django/dispatch/dispatcher.py:Signal._flag_dead_receivers`, `django/dispatch/dispatcher.py:Signal._clear_dead_receivers`). Until then a dead entry stays in the list, and `_live_receivers` skips it.

## The receivers cache and `ModelSignal`

A signal made with `use_caching=True` remembers, for each sender, the entries `_live_receivers` picked out, references unresolved, or the marker `NO_RECEIVERS` when there were none. `Signal.sender_receivers_cache` is a `weakref.WeakKeyDictionary` keyed by the sender: `connect` and `disconnect` empty it, and `_live_receivers` fills it, and reads it unless the dead flag is set (`django/dispatch/dispatcher.py:Signal._live_receivers`). The keys are weak, so with a receiver of `post_save` connected, sending it with `sender=None` raises `TypeError`.

The signals with caching are the seven `ModelSignal`s: `pre_init`, `post_init`, `pre_save`, `post_save`, `pre_delete`, `post_delete` and `m2m_changed` (`django/db/models/signals.py`). They are sent as instances are made, saved and deleted and as many-to-many relations change, and for a model with no receivers, once the cache records it, each send ends at its first test. In the example, once the rows were made, `post_save`'s cache held `NO_RECEIVERS` for Port and for Ship, and voyage_saved's entry for Voyage. `Signal.has_listeners` asks `_live_receivers` whether a sender has a receiver (`django/dispatch/dispatcher.py:Signal.has_listeners`); the `Collector` asks it of the deletion signals to decide whether rows may go unfetched ([Deleting: the `Collector`](../instance/deleting.md#collectorcan_fast_delete-whether-rows-can-go-unseen)).

`ModelSignal` adds one thing: its `connect` and `disconnect` take the sender as a string, `"app_label.ModelName"` (`django/db/models/signals.py:ModelSignal._lazy_method`). For a string, the call to the base method is handed to `Apps.lazy_model_operation`, which makes it when that model is registered, at once if it already is ([The registry and its models](../startup/registry.md#references-that-wait-appslazy_model_operation)). So `disconnect` with a string returns `None`, whatever it removed.
