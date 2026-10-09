---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The asynchronous methods of a queryset

Each public method of `QuerySet` that sends a statement when it is called has a **twin**, a coroutine function of the same name with an a in front, `QuerySet.aget`, `QuerySet.acount`, `QuerySet.acreate`, and a queryset can be the subject of `async for`, through `QuerySet.__aiter__` or, a chunk at a time, through `QuerySet.aiterator`. None of them reaches the database asynchronously: each hands synchronous code to a thread through `sync_to_async` and waits for it.

A coroutine shares its thread with every other coroutine of its event loop, and while one of them is inside an ordinary blocking call, none of the others runs. A query is such a call: the driver sends the statement and waits for the database. And Django's database layer is synchronous from the queryset down. Nothing under `django/db/models/sql/` or `django/db/backends/` is a coroutine function, and the connection's methods that open it, give a cursor, end a transaction or keep a savepoint refuse to be called on a thread where an event loop is running.

So what Django offers a coroutine is not an asynchronous query. It is a way to wait for a synchronous one without holding the event loop: the work is given to another thread, by asgiref's `sync_to_async`, and the coroutine is suspended until that thread has done it (`asgiref:asgiref/sync.py:SyncToAsync.__call__`). One such handing-over is a **crossing**. Building a queryset asks no connection for a cursor, so `QuerySet.filter`, `QuerySet.order_by` and the other methods that return a queryset need no second form and have none. Each public method that runs a query has its twin, and iteration has two forms.

```text figure=crossings-to-a-thread
Two loops in a coroutine. Time runs left to right. Each "->" is one call handed to a thread through sync_to_async;
the coroutine is suspended from there until the thread returns.

async for sailor in Sailor.objects.filter(ship=petrel).order_by('id')          two sailors
    the event loop's thread:   QuerySet.__aiter__  ->  . . . . . . . . . . . . . . . . . . . . . .  the loop's body, twice
    another thread:                                    QuerySet._fetch_all: the statement, both instances

async for sailor in Sailor.objects.order_by('id').aiterator(chunk_size=3)      four sailors
    the event loop's thread:   QuerySet.aiterator  ->  . . . . . . . . . . . .  the body, three times  ->  . . . . . . .  the body, once
    another thread:                                    the statement, a list of 3                           a list of 1

One crossing for the whole of an evaluation, or, here, one for each chunk of an iteration that keeps nothing.
```

*The two ways to loop over a queryset from a coroutine. `QuerySet.__aiter__` has the queryset evaluated on a thread in one call, and the loop then runs over the list; `QuerySet.aiterator` goes to the thread, here, once for each chunk of items: there are no prefetch lookups, and four is not a multiple of three.*

## The twins

A twin is a coroutine function of one expression. It wraps the synchronous method, bound to the queryset the twin was called on, in `sync_to_async`, calls what that returns with its own arguments, and awaits the result (`django/db/models/query.py:QuerySet.aget`).

| the synchronous methods are in | their twins | marks on the twins |
|---|---|---|
| [`get`, `first`, `count` and the other methods that run a query at once](results.md) | `QuerySet.aget`, `QuerySet.afirst`, `QuerySet.alast`, `QuerySet.aearliest`, `QuerySet.alatest`, `QuerySet.acount`, `QuerySet.aexists`, `QuerySet.acontains`, `QuerySet.aaggregate`, `QuerySet.ain_bulk`, `QuerySet.aexplain` | none |
| [Creating, updating and deleting through a queryset](writing.md) | `QuerySet.acreate`, `QuerySet.aget_or_create`, `QuerySet.aupdate_or_create`, `QuerySet.aupdate`, `QuerySet.adelete` | `"alters_data"` on each, and `"queryset_only"` on `adelete` |
| [`bulk_create` and `bulk_update`](bulk.md) | `QuerySet.abulk_create`, `QuerySet.abulk_update` | `"alters_data"` on each |

*The twins of `QuerySet`. Each awaits the method whose name is its own without the a.*

The private methods that the model layer calls, `QuerySet._insert` among them, have no twin, and neither have Python's own protocols for length, truth and indexing. Each mark is set on a twin as it is on the method the twin runs: `"alters_data"` keeps a template from calling it, and `"queryset_only"` keeps `adelete`, like `QuerySet.delete`, off managers ([Clones: how a queryset is built](chaining.md)).

`sync_to_async` returns a `SyncToAsync`, and calling that object is itself a coroutine, `SyncToAsync.__call__`. It chooses an executor, has the event loop submit the call to it with `asyncio.AbstractEventLoop.run_in_executor`, and awaits the future that the loop gives it. The coroutine that awaited the twin is suspended at that point, and the event loop is free to run others, until the call has returned; what the method returned, or the exception it raised, is then what the `await` gives (`asgiref:asgiref/sync.py:SyncToAsync.__call__`).

What follows was recorded from a running Django, on SQLite, over the shipping line of the chapter's opening page ([QuerySets](../querysets.md)): the ship Petrel has two sailors, Ada and Bram, and there are four sailors and two ships in all. Under a line of Python are the calls the passage is about; `->` is what a call returned; and a line that begins `SQL` is a statement as Django handed it to its cursor. Each line of a call also says which of two threads it ran on, the thread the event loop runs on or another, and the nesting is each thread's own: a line stands one step in from the call of its own thread that it ran under, whatever lines of the other thread come between, and a thread's outermost call one step in from the line of Python. A line `SyncToAsync.__call__` is asgiref's coroutine, written with the function it was made for: it is where a crossing begins.

```text recording=querysets
ada = await Sailor.objects.aget(name='Ada')
  QuerySet.aget(name='Ada')  [the event loop's thread]
    SyncToAsync.__call__  (made by sync_to_async for QuerySet.get)  [the event loop's thread]
  QuerySet.get(name='Ada')  [another thread]
    QuerySet._fetch_all  [another thread]
      ModelIterable.__iter__  [another thread]
        SQLCompiler.execute_sql  [another thread]
          SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s LIMIT 21 with params ('Ada',)
    -> <Sailor: Ada>
```

`QuerySet.aget` and asgiref's coroutine began on the event loop's thread, and then `QuerySet.get` and everything under it, down to the statement, ran on the other.

The twins pass `sync_to_async` no option, so the call is thread-sensitive, which is asgiref's default: all such calls made inside one `ThreadSensitiveContext`, asgiref's context manager for the purpose, are sent to a single thread and run there one after another. The docstring of `SyncToAsync` says what that is needed for: code that is not thread-safe, and its example is code that handles SQLite's database connections (`asgiref:asgiref/sync.py:SyncToAsync`). Django's ASGI handler enters such a context for each request, so under the handler the thread is the request's own (`django/core/handlers/asgi.py:ASGIHandler.__call__`) ([Sync and async in one chain](../handlers/async.md)). Where nothing of Django's or asgiref's stands above the event loop, as in these recordings, it is one thread that the class keeps for the whole process (`asgiref:asgiref/sync.py:SyncToAsync.single_thread_executor`). So two twins awaited together free the event loop for other work, and their queries are not run side by side:

```text recording=querysets
await asyncio.gather(Sailor.objects.acount(), Ship.objects.acount())
  QuerySet.acount  [the event loop's thread]
    SyncToAsync.__call__  (made by sync_to_async for QuerySet.count)  [the event loop's thread]
  QuerySet.acount  [the event loop's thread]
    SyncToAsync.__call__  (made by sync_to_async for QuerySet.count)  [the event loop's thread]
  QuerySet.count  [another thread]
    SQLCompiler.execute_sql(result_type='single')  [another thread]
      SQL SELECT COUNT(*) AS "__count" FROM "crew_sailor"
    -> 4
  QuerySet.count  [another thread]
    SQLCompiler.execute_sql(result_type='single')  [another thread]
      SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
    -> 2
```

One count ran and returned before the other began, and both are lines of the one thread. That both coroutines had begun, and both crossings, before the first count is the order in which the interpreter let the two threads run, and not one that asgiref or Django fixes.

Everything about the query is the synchronous method's, and is told where that method is. The object is the same on both threads, since the twin wraps a method bound to its own queryset: whatever the method leaves on the queryset, the mark for writing for one, is there when the `await` returns. And the thread matters to the database layer here in this way: Django keeps its connections for each thread separately, so the statement goes over the connection of the thread that runs the method, not over one the event loop's thread may have (`django/db/utils.py:ConnectionHandler.thread_critical`) ([Connections by alias: `DATABASES` and `ConnectionHandler`](../backends/connections.md#one-connection-for-each-alias-in-each-thread)). Calls that a context's one thread runs therefore share a connection.

A manager has the twins as it has the other public methods of its queryset class. `BaseManager._get_queryset_methods` copies the public functions of the class that are not marked for querysets only, passing over a name the manager's class already has, and a coroutine function is a function (`django/db/models/manager.py:BaseManager._get_queryset_methods`) ([Managers](../models/managers.md)). The manager's copy is an ordinary function that makes a queryset and calls the method of that name on it, so `aget` called on a manager returns the coroutine that the queryset's `aget` made. The first line of the first recording awaited one. `adelete` is not copied, because of its mark.

## `async for` over a queryset: `QuerySet.__aiter__`

`QuerySet.__aiter__` is what `async for` calls on a queryset. By Python's rules it is an ordinary method, and what it returns has to be asynchronous. It defines an asynchronous generator inside itself and returns one (`django/db/models/query.py:QuerySet.__aiter__`). The generator awaits one thing, `QuerySet._fetch_all` wrapped in `sync_to_async`, and then yields the items of the result cache one after another. Here one queryset, of the Petrel's sailors, is looped over twice:

```text recording=querysets
kept = Sailor.objects.filter(ship=petrel).order_by('id')
async for sailor in kept: seen(sailor)
  QuerySet.__aiter__  [the event loop's thread]
  generator  (the asynchronous generator QuerySet.__aiter__ returned)  [the event loop's thread]
    SyncToAsync.__call__  (made by sync_to_async for QuerySet._fetch_all)  [the event loop's thread]
  QuerySet._fetch_all  [another thread]
    ModelIterable.__iter__  [another thread]
      SQLCompiler.execute_sql  [another thread]
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "crew_sailor"."id" ASC with params (1,)
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
async for sailor in kept: seen(sailor)
  QuerySet.__aiter__  [the event loop's thread]
  generator  (the asynchronous generator QuerySet.__aiter__ returned)  [the event loop's thread]
    SyncToAsync.__call__  (made by sync_to_async for QuerySet._fetch_all)  [the event loop's thread]
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
```

The first loop is an evaluation like any other ([Evaluation and the result cache](evaluation.md)), done whole on the other thread: the statement, every row read, every instance made, and the queryset's prefetch lookups followed, all inside the one call of `_fetch_all`. By the time the loop's body first runs, which it does in the coroutine and so on the event loop's thread, the thread's work is over and the list is in memory. The queryset has its result cache afterwards, and the second loop shows what that saves. The crossing is made again, since the generator awaits `_fetch_all` whether or not there is a cache. But no line `QuerySet._fetch_all` follows it: the method had nothing to do, and no statement was sent.

A manager has no `__aiter__`: the copying of methods passes over a name that begins with an underscore where its function carries no `"queryset_only"`, and `__aiter__` carries none (`django/db/models/manager.py:BaseManager._get_queryset_methods`). So a manager cannot be the subject of `async for`, where a queryset from it can, and the error is Python's:

```text recording=querysets
async for sailor in Sailor.objects: seen(sailor)
raises TypeError: 'async for' requires an object with __aiter__ method, got ManagerFromSailorQuerySet
```

`RawQuerySet.__aiter__` is the same method for a raw queryset, around the `_fetch_all` of that class (`django/db/models/query.py:RawQuerySet.__aiter__`) ([Raw querysets](raw.md)).

## `aiterator`: a crossing for each chunk

`QuerySet.aiterator` reads the rows of a queryset without keeping them, as `QuerySet.iterator` does for a plain loop ([Evaluation and the result cache](evaluation.md)). It is an asynchronous generator function, so nothing in it runs until the first item is asked for. Then it refuses a chunk size that is not positive with `ValueError`, decides on a chunked fetch as `iterator` does, by the setting `"DISABLE_SERVER_SIDE_CURSORS"` of the database, and makes the queryset's iterable class with the queryset, that decision and the chunk size, which is 2,000 where none was given (`django/db/models/query.py:QuerySet.aiterator`) ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)). On a queryset without prefetch lookups the rest of the method is a loop: `async for` over the iterable, yielding each item as it comes.

> **Deprecated.** A queryset with prefetch lookups needs a chunk size. The synchronous `iterator` raises `ValueError` when it is given none. `aiterator` warns with `RemovedInDjango2029Warning` and goes on with 2,000; the release notes of 6.2, which deprecate the call, say that it will raise `ValueError` in its turn (`docs/releases/6.2.txt`).

### `BaseIterable._async_generator`: a generator advanced on a thread

What `async for` calls on an iterable is `BaseIterable.__aiter__`, which the iterable classes all inherit. It returns the asynchronous generator that `BaseIterable._async_generator` makes (`django/db/models/query.py:BaseIterable._async_generator`).

`_async_generator` makes the ordinary iterator first, with a call of the iterable's own `__iter__`, where the coroutine is running, on the event loop's thread. A comment says why that does no harm: a generator does not start running until `next` is first called on it, so the generator object can be made on the asynchronous side and then advanced, time after time, on a synchronous thread. The advancing is a loop of crossings. Each one awaits, through `sync_to_async`, a small function that takes the generator and returns a list of up to one chunk of its items, by `itertools.islice`; the items of the list are yielded; and the loop stops when a list comes back shorter than the chunk size. The generator is the one piece of state that goes over at each crossing: its statement is sent at the first advance, and each later crossing reads on from where the last one stopped.

```text recording=querysets
async for sailor in Sailor.objects.order_by('id').aiterator(chunk_size=3): seen(sailor)
  QuerySet.aiterator(chunk_size=3)  [the event loop's thread]
    BaseIterable.__aiter__  [the event loop's thread]
    BaseIterable._async_generator  [the event loop's thread]
      SyncToAsync.__call__  (made by sync_to_async for next_slice)  [the event loop's thread]
  next_slice  (the function BaseIterable._async_generator hands to sync_to_async)  [another thread]
    ModelIterable.__iter__  [another thread]
      SQLCompiler.execute_sql(chunked_fetch=True, chunk_size=3)  [another thread]
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC
    -> a list of 3
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
  the loop's body runs with <Sailor: Cora>
      SyncToAsync.__call__  (made by sync_to_async for next_slice)  [the event loop's thread]
  next_slice  (the function BaseIterable._async_generator hands to sync_to_async)  [another thread]  ->  a list of 1
  the loop's body runs with <Sailor: Dag>
```

The function is the one the recording writes as next_slice. `ModelIterable.__iter__` stands under the first call of it, on the other thread: the body of the generator began to run there, at the first advance, and so the statement was sent from that thread and not from the one on which the generator was made. Three instances came back in a list, the loop's body ran for each of them, and a second crossing, with no statement under it, brought a list of one. One is fewer than three, and the loop ended.

The loop ends on a short list, and a full list tells it nothing either way. Where the number of items is a multiple of the chunk size there is therefore one crossing more, which comes back empty.

The comment above `BaseIterable.__aiter__` is frank about the design. It calls the method a generic converter of iterables for now, says that it will suffer a performance penalty on large sets of items, from the cost of crossing the sync barrier for each chunk, and says what should replace it and what stands in the way: an `__aiter__` of its own for each iterable class, which needs some work in the compiler first (`django/db/models/query.py:BaseIterable`).

> **Trap.** The premise of the comment in `BaseIterable._async_generator`, that a generator does not run until it is first advanced, holds for an `__iter__` that is a generator function, as `ModelIterable.__iter__` is. Of the iterable classes, `ValuesListIterable` alone has an `__iter__` that is not one: it returns what `SQLCompiler.results_iter` returns, and that method has the statement run before it returns (`django/db/models/query.py:ValuesListIterable.__iter__`, `django/db/models/sql/compiler.py:SQLCompiler.results_iter`). So for a queryset from `QuerySet.values_list` with neither `flat=True` nor `named=True` ([`values` and `values_list`: rows as dictionaries and tuples](values.md)), the first step of `_async_generator` compiles the query on the event loop's thread and, unless it compiles to nothing, as after `QuerySet.none`, asks for a cursor there.

Such a queryset, recorded with no chunk size given:

```text recording=querysets
async for row in Sailor.objects.values_list('name').aiterator(): seen(row)
  QuerySet.aiterator  [the event loop's thread]
    BaseIterable.__aiter__  [the event loop's thread]
    BaseIterable._async_generator  [the event loop's thread]
      ValuesListIterable.__iter__  [the event loop's thread]
        SQLCompiler.execute_sql(chunked_fetch=True, chunk_size=2000)  [the event loop's thread]  raises SynchronousOnlyOperation
raises SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async.
```

`ValuesListIterable.__iter__` and `SQLCompiler.execute_sql` both ran on the event loop's thread, and the exception left the second, which had asked the connection for a cursor. The call of `aiterator` itself raises nothing: the exception comes when the first item is asked for. Nor is anything raised where the environment variable `"DJANGO_ALLOW_ASYNC_UNSAFE"` is set. An `async for` over the queryset itself goes through `QuerySet._fetch_all` on a thread and is not touched by this.

### With prefetch lookups

Prefetch lookups are followed for a list of instances at once ([`prefetch_related`: related objects in a second query](prefetch.md)), so with them `aiterator` does not yield an instance as it arrives. It gathers what the iterable yields into a list until the list is as long as the chunk size, awaits `aprefetch_related_objects` with the list and the lookups, yields the instances, and empties the list; what is left over when the iterable ends is dealt with in the same way (`django/db/models/query.py:QuerySet.aiterator`). `aprefetch_related_objects` is to `prefetch_related_objects` what a twin is to its method, a coroutine function that awaits the synchronous function through `sync_to_async` with the arguments it was given, and `aiterator` is its one caller in Django (`django/db/models/query.py:aprefetch_related_objects`). The chunk size then sets two things at once: how many items a crossing brings back, and how many instances one prefetch serves. Here the ships are read one to a chunk, with their crews, and the prefetch of the second ship's crew is left out of the quote:

```text recording=querysets
async for ship in Ship.objects.prefetch_related('crew').aiterator(chunk_size=1): seen(ship)
  QuerySet.aiterator(chunk_size=1)  [the event loop's thread]
    BaseIterable.__aiter__  [the event loop's thread]
    BaseIterable._async_generator  [the event loop's thread]
      SyncToAsync.__call__  (made by sync_to_async for next_slice)  [the event loop's thread]
  next_slice  (the function BaseIterable._async_generator hands to sync_to_async)  [another thread]
    ModelIterable.__iter__  [another thread]
      SQLCompiler.execute_sql(chunked_fetch=True, chunk_size=1)  [another thread]
        SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
    -> a list of 1
    aprefetch_related_objects(model_instances=[<Ship: Gannet>], 'crew')  [the event loop's thread]
      SyncToAsync.__call__  (made by sync_to_async for prefetch_related_objects)  [the event loop's thread]
  prefetch_related_objects(model_instances=[<Ship: Gannet>], 'crew')  [another thread]
    QuerySet._fetch_all  [another thread]
      ModelIterable.__iter__  [another thread]
        SQLCompiler.execute_sql  [another thread]
          SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (%s) with params (2,)
  the loop's body runs with <Ship: Gannet>
      SyncToAsync.__call__  (made by sync_to_async for next_slice)  [the event loop's thread]
  next_slice  (the function BaseIterable._async_generator hands to sync_to_async)  [another thread]  ->  a list of 1
  the loop's body runs with <Ship: Petrel>
      SyncToAsync.__call__  (made by sync_to_async for next_slice)  [the event loop's thread]
  next_slice  (the function BaseIterable._async_generator hands to sync_to_async)  [another thread]  ->  a list of 0
```

The statement for the ships was sent once, in the first crossing. The second crossing for items, a line with nothing under it, brought back the next ship from the same generator, and the third came back empty: two ships in chunks of one, and the extra crossing of a count that divides evenly. Each ship's crew was fetched in a crossing of its own, which `aprefetch_related_objects` began on the event loop's thread: its line stands under `QuerySet.aiterator`, which awaited it, and not under the other thread's lines above it. So each ship cost two crossings, and the three statements, of which the quote has two, were all sent from the other thread.

## A synchronous method where an event loop is running

A synchronous method of a queryset that runs its query on a thread where an event loop is running is refused, with `SynchronousOnlyOperation`, which is why the twins exist. Here `QuerySet.get` is called in the coroutine itself:

```text recording=querysets
Sailor.objects.get(name='Ada')
  QuerySet.get(name='Ada')  [the event loop's thread]
    QuerySet._fetch_all  [the event loop's thread]
      ModelIterable.__iter__  [the event loop's thread]
        SQLCompiler.execute_sql  [the event loop's thread]  raises SynchronousOnlyOperation
raises SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async.
```

The same `get` that ran on the other thread in the first recording ran here on the event loop's thread, and got as far as the cursor. The queryset's share of the work went through, and the exception left `SQLCompiler.execute_sql`, which is where the connection is asked for a cursor (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`).

`BaseDatabaseWrapper.cursor` is wrapped by the decorator `async_unsafe`, as are the connection's methods that open it, close it, end a transaction or keep a savepoint (`django/db/backends/base/base.py:BaseDatabaseWrapper.cursor`).

The wrapper asks `asyncio.get_running_loop` whether an event loop is running in the thread that made the call. If one is, it raises `SynchronousOnlyOperation` with the message of the recording, unless the environment variable `"DJANGO_ALLOW_ASYNC_UNSAFE"` is set; if none is, it calls the method (`django/utils/asyncio.py:async_unsafe`, `django/core/exceptions.py:SynchronousOnlyOperation`).

The test is of the thread and not of the caller. A queryset can be built in a coroutine, filtered and ordered, since none of that asks for a cursor, and a synchronous method that runs its query there is refused at the cursor. On the thread that `sync_to_async` gives the work to, no event loop is running, and the same method goes through.

A model and a related manager have asynchronous methods of the same kind, `Model.asave` for one ([Saving an instance](../models/saving.md), [Reading and setting related objects](../models/related-objects.md)), and how a view comes to be a coroutine that the handler awaits is in [Asynchronous views](../views/async.md).
