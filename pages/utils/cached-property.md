---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `cached_property`, `classproperty` and `classonlymethod`

`cached_property` makes a method an attribute that is worked out at its first read on an instance and kept on that instance; `classproperty` makes a method of the class an attribute that is worked out at every read; `classonlymethod` is a `classmethod` that an instance cannot reach.

Many of Django's objects answer questions that cost something and that not every use asks: a request's headers, gathered from `META`; whether a database supports transactions, found by trying. Answering in `__init__` makes every object pay for every answer, and a method pays at each call. A **cached property** pays once, at the first read. `HttpRequest.headers` is one ([Headers, host and scheme](../http/headers.md)), as are the flags of `BaseDatabaseFeatures` that ask the database ([What a database can do: `BaseDatabaseFeatures`](../backends/features.md)), `BaseConnectionHandler.settings`, which reads `DATABASES`, `CACHES` or `TASKS` at the handler's first use ([Connections by alias: `DATABASES` and `ConnectionHandler`](../backends/connections.md)), and the lists a model's options derive (`django/http/request.py:HttpRequest.headers`, `django/db/backends/base/features.py:BaseDatabaseFeatures.supports_transactions`, `django/utils/connection.py:BaseConnectionHandler.settings`, `django/db/models/options.py:Options.fields`). [The utility layer](../utils.md) sets it beside the other ways Django's code waits.

## The descriptor and its name

`cached_property.__init__` keeps the function as `cached_property.real_func` and copies its docstring, and nothing more: the descriptor does not yet know the name under which it will store a value. Until it does, `cached_property.name` is the class's `None`, and `cached_property.func`, which `cached_property.__get__` calls, is a placeholder, a static method that raises `TypeError` (`django/utils/functional.py:cached_property`).

The name comes from Python, which calls `__set_name__` on each attribute that defines it as a class statement makes the class. `cached_property.__set_name__` records the name the first time and puts the real function in `func`. Called again with the same name, as when a subclass assigns the inherited descriptor to the same attribute, it does nothing; with another name it raises `TypeError` (`django/utils/functional.py:cached_property.__set_name__`). The name is the key under which every instance's value is stored, and it is the attribute's, not the function's: `fleet = cached_property(get_ships)` stores under `"fleet"`. A class of the harbour office's that gives one descriptor two names fails as its class statement runs:

```python
# harbour/office/board.py
class Office:
    @cached_property
    def ships(self):
        return list(Ship.objects.order_by("name"))

    fleet = ships
```

```text
TypeError: Cannot assign the same cached_property to two different names ('ships' and 'fleet').
```

A `cached_property` assigned to a class after its class statement is never named, and its first read on an instance raises the placeholder's `TypeError`.

## Why the second read never reaches `__get__`

`cached_property.__get__`, read on the class, returns the descriptor itself. Read on an instance, it calls `func` with the instance, writes the result into the instance's `__dict__` under the name, and returns it (`django/utils/functional.py:cached_property.__get__`).

Later reads are kept away by the order of Python's lookup of an instance's attribute. A **data descriptor** on the class, one that defines `__set__` or `__delete__`, answers before the instance's `__dict__` is looked in; any other descriptor answers only if the name is not in that `__dict__`. `cached_property` defines neither method, so the value stored at the first read hides it. An assignment does not reach the descriptor either: with no `__set__` to take it, the value goes straight into the instance's `__dict__`, and a value put there before the first read is returned without a call. A run with the example's Harbour, harbour and other being two instances, and the number of SQL statements each line sent:

```text
Harbour.ships.name           0 queries  'ships'
harbour.ships                1 query    [<Ship: Beagle>, <Ship: Endeavour>]
harbour.ships                0 queries  [<Ship: Beagle>, <Ship: Endeavour>]
del harbour.ships            0 queries
del harbour.ships            0 queries  AttributeError: 'Harbour' object has no attribute 'ships'
other.ships = []             0 queries
other.ships                  0 queries  []
```

## Forgetting a value, and copying one

Deleting the attribute of a `cached_property` from an instance removes the value from the instance's `__dict__`, and the next read calls the function again. With no `__delete__` on the descriptor, `del` reaches only the dictionary, so deleting a value never computed raises `AttributeError`. `Options._expire_cache` deletes a name a model's options cache only where it finds it in the dictionary ([The options: what a model keeps as `_meta`](../models/options.md)) (`django/db/models/options.py:Options._expire_cache`).

The value is an ordinary entry of the dictionary, so a copy made from the dictionary carries it: in a run, `copy.copy` of a Harbour and a pickle round trip both kept the list. `Query.clone` copies the query's `__dict__` and then pops `Query.base_table` with a default, and the clone works it out again ([The query: what a `Query` holds, and how it is copied](../sql/query.md)) (`django/db/models/sql/query.py:Query.clone`).

## No lock, and no `__dict__`

`cached_property.__get__` calls the function and stores its result with no lock (`django/utils/functional.py:cached_property.__get__`). Two threads that read the attribute of one instance before either has stored a value both call the function: in a run whose function waited a fifth of a second, it was called twice, each thread got a list of its own, and the instance kept one of them.

A class whose instances have no `__dict__`, as with `__slots__`, cannot use it. The function is called before the store is tried, so it runs, and then the store fails, at every read. Mooring, a class of the example with `__slots__ = ("name",)` and the same ships:

```text
mooring.ships                1 query    AttributeError: 'Mooring' object has no attribute '__dict__'
```

## `classproperty`

`classproperty.__get__` calls the function with the class it was read through, the class itself or an instance's class, and keeps nothing, so the function runs at every read (`django/utils/functional.py:classproperty`). `classproperty.getter` replaces the function and returns the descriptor. There is no setter and no `__set__`, so an assignment on an instance stores a value in its `__dict__` that hides the descriptor for that instance alone. The example's Harbour, given berths and a second attribute:

```python
# harbour/office/board.py
class Harbour:
    berths = 12

    @classproperty
    def free_berths(cls):
        return cls.berths - Ship.objects.count()


class BigHarbour(Harbour):
    berths = 20
```

```text
Harbour.free_berths          1 query    10
Harbour.free_berths          1 query    10
harbour.free_berths          1 query    10
BigHarbour.free_berths       1 query    18
harbour.free_berths = 0      0 queries
harbour.free_berths          0 queries  0
Harbour.free_berths          1 query    10
```

Where Django wants the answer kept, the function keeps it. `MigrationRecorder.Migration` defines its model class at the first read and keeps it in `MigrationRecorder._migration_class` ([What has been applied: `MigrationRecorder` and the table `"django_migrations"`](../migrations/recorder.md)) (`django/db/migrations/recorder.py:MigrationRecorder.Migration`). `View.view_is_async` is worked out at each read ([Asynchronous views](../views/async.md)) (`django/views/generic/base.py:View.view_is_async`).

## `classonlymethod`

`classonlymethod` is a `classmethod` whose `__get__` raises `AttributeError` when it is read through an instance, "This method is available only on the class, not on instances.", and otherwise binds to the class (`django/utils/decorators.py:classonlymethod`). Django's one use of it is `View.as_view` ([`View.as_view` and dispatch](../views/as-view.md)).
