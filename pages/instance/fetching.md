---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Deferred fields and the fetch modes

A field is deferred on an instance when its attname is not in the instance's `__dict__`, and reading it ordinarily fetches the value through `DeferredAttribute.__get__`. How it is fetched, for that instance alone, for every peer made by the same query, or not at all, is decided by the instance's fetch mode, `FETCH_ONE`, `FETCH_PEERS` or `FETCH_RAISE`, which also decides how a related object that is not at hand is fetched.

## A deferred field is a missing key

A deferred field is, on the instance, nothing more than a key that is missing. One cause is a query that fetches fewer columns than the model has. `Model.from_db` is then handed fewer values than there are concrete fields, and makes up the difference itself: for each field whose attname is not among those fetched it puts a marker, `DEFERRED`, in that position, and `Model.__init__` sets nothing for a value that is the marker. Another is a generated field: `Model.__init__` passes it over, so on an instance made from keyword arguments its key is missing too.

```text recording=models
Ship.objects.only('name').get(name='Petrel'): a row with two of the model's five columns
    SQL SELECT "fleet_ship"."id", "fleet_ship"."name" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Petrel',)
    Model.from_db('default', ['id', 'name'], (1, 'Petrel'), fetch_mode=FETCH_ONE)  (Ship)
      Model.__init__(1, 'Petrel', <Deferred field>, <Deferred field>, <Deferred field>)  (a new Ship)
```

```text recording=models
What the Ship made from two columns holds in its __dict__
    _state: a ModelState
    id: 1
    name: 'Petrel'
    and its _state: adding=False, db='default', fields_cache={}
```

That is the whole representation. No list of deferred fields is kept: `Model.get_deferred_fields` works one out each time, as the attnames of the concrete fields that have no entry in the `__dict__` (`django/db/models/base.py:Model.get_deferred_fields`).

Reading such an attribute works by ordinary Python rules. The instance has no entry of that name, so the lookup goes to the class, and finds the `DeferredAttribute` that the field set there when the class was made. A descriptor without a `__set__` is consulted only in that case, which is why it costs nothing for a field that is loaded. A foreign key's attname is an exception, and so is a file field's: each has a descriptor with a `__set__`, so Python goes to it at every read. The foreign key's hands back the entry when there is one.

```text recording=models
slim.tonnage is read
  DeferredAttribute.__get__(a Ship)  (Ship.tonnage)
    DeferredAttribute._check_parent_chain  ->  None
    FetchOne.fetch(a DeferredAttribute for Ship.tonnage, <Ship: Petrel>)
      DeferredAttribute.fetch_one(a Ship)
        Model.refresh_from_db(fields=['tonnage'])  (a Ship)
          SQL SELECT "fleet_ship"."id", "fleet_ship"."tonnage" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 21 with params (1,)
          Model.from_db('default', ['id', 'tonnage'], (1, 480), fetch_mode=FETCH_ONE)  (Ship)
            Model.__init__(1, <Deferred field>, 480, <Deferred field>, <Deferred field>)  (a new Ship)
    -> 480
slim.tonnage is read again
```

`DeferredAttribute.__get__` first looks for the value somewhere it may already be: a child model that deferred its parent's primary key has the same value in its link to the parent. Failing that, it refuses an instance with no primary key, which has no row to fetch from, and hands the fetch to the instance's fetch mode. The default mode fetches for this instance alone, by calling `Model.refresh_from_db` for the one field; the value arrives in the `__dict__`, and the second read in the recording finds it there and calls nothing (`django/db/models/query_utils.py:DeferredAttribute.__get__`). Under `FETCH_PEERS` the same read, when other instances of the same query are still alive, fetches the field for all of them through `QuerySet.in_bulk`, and under `FETCH_RAISE` it raises ([The fetch modes](#the-fetch-modes) has the fetch modes).

Assigning to a deferred attribute puts a value under the key like any assignment. The field is then no longer deferred, and nothing was fetched.

## `FetchMode` and its subclasses

A mode is an instance of a subclass of `FetchMode`, a class with no state of its own, an attribute `track_peers` and one method, `FetchMode.fetch`, which takes a fetcher, the descriptor that was read and had no value to give, and an instance, and in the base class raises `NotImplementedError`. `FetchOne.fetch` calls the fetcher's `fetch_one` with the instance. `FetchPeers.fetch` calls the fetcher's `fetch_many` with the instance's peers where more than one of them is still alive, and its `fetch_one` otherwise. `FetchRaise.fetch` raises `FieldFetchBlocked`, which is a `FieldError`, with the names of the instance's class and of the fetcher's field. The module makes one instance of each subclass as it is imported, `FETCH_ONE`, `FETCH_PEERS` and `FETCH_RAISE`, and `django.db.models` exports them (`django/db/models/fetch_modes.py`, `django/core/exceptions.py:FieldFetchBlocked`).

> **Changed in 6.1.** Fetch modes are new in 6.1, and with them `QuerySet.fetch_mode`, the peers, and the argument `fetch_mode=` of `Model.from_db`. The release notes describe `FETCH_ONE`, the default, as the behaviour Django had before: a missing value is fetched for the one instance it was read from (`docs/releases/6.1.txt`).

## Reading a deferred field: `DeferredAttribute.__get__`

A field that has a column leaves a `DeferredAttribute` on its model class, under its attname. The class has no `__set__`, so Python goes to it only when the instance's `__dict__` has no entry of that name, which is when the field is deferred ([A deferred field is a missing key](#a-deferred-field-is-a-missing-key)). Read on the class, the attribute is the descriptor itself. Read on an instance, `DeferredAttribute.__get__` looks in the `__dict__` itself before anything else: a subclass that does define `__set__`, such as the `ForeignKeyDeferredAttribute` under a foreign key's attname, is consulted at every read, and finds the value there unless the field is deferred. Where there is no value it tries three things in turn (`django/db/models/query_utils.py:DeferredAttribute.__get__`).

**A value the instance holds under another name.** `DeferredAttribute._check_parent_chain` covers one case: the deferred field is a primary key, and the instance is of a child model that inherited it. A child with a table of its own holds a link to its parent, and the link's column has the same value as the parent's key ([Inheritance: abstract bases, parents with tables and proxies](../models/inheritance.md)). The method asks `Options.get_ancestor_link` for the instance's link towards the model that declares the field, and where the field is a primary key and is not that link, it returns what the instance holds under the link's attname (`django/db/models/options.py:Options.get_ancestor_link`, `django/db/models/query_utils.py:DeferredAttribute._check_parent_chain`). `__get__` stores that under the field's own attname and returns it. An Officer is a Sailor with a second table, whose own primary key is the link `"sailor_ptr"`. Fetched with `only`, and under `FETCH_RAISE` so that a read which reached the mode would raise, it comes with that key and without `"id"`, which is Sailor's:

```text recording=querysets
Officer.objects.fetch_mode(models.FETCH_RAISE).only('rank').get(pk=3).id  ->  3
  SQL SELECT "crew_officer"."sailor_ptr_id", "crew_officer"."rank" FROM "crew_officer" WHERE "crew_officer"."sailor_ptr_id" = %s LIMIT 21 with params (3,)
```

The read of `"id"` was answered from `"sailor_ptr_id"`: the one statement is the `get` that fetched the Officer, and nothing was raised.

**An instance with no primary key.** Failing that, the instance is asked `Model._is_pk_set`, and one without a key raises `AttributeError`, whose message calls it an unsaved model. Here a sailor's key is set to `None` after it was fetched.

```text recording=querysets
unkeyed = Sailor.objects.only('name').get(pk=1); unkeyed.pk = None
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
unkeyed.signed_on  ->  raises AttributeError: Cannot retrieve deferred field 'signed_on' from an unsaved model.
```

**The fetch mode.** Otherwise the descriptor calls `FetchMode.fetch` on the instance's mode, `ModelState.fetch_mode`, with itself and the instance (`django/db/models/base.py:ModelState`). The mode calls back one of two methods of the descriptor, `DeferredAttribute.fetch_one` or `DeferredAttribute.fetch_many`, or raises. `__get__` then returns what is in the `__dict__`, so each of the two methods has to have put the value there.

For a deferred field under `FETCH_RAISE`, the read raises once the two earlier steps of `__get__` have found nothing. The statement under the question is the one that fetched the sailor:

```text recording=querysets
Sailor.objects.fetch_mode(models.FETCH_RAISE).only('name').get(pk=1).signed_on  ->  raises FieldFetchBlocked: Fetching of Sailor.signed_on blocked.
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
```

### `fetch_one`: one field, for one instance

`DeferredAttribute.fetch_one` is a single call: `Model.refresh_from_db`, with the field's attname as the one field to reload ([An instance and its state](state.md)) (`django/db/models/query_utils.py:DeferredAttribute.fetch_one`). In this recording slim is the list of the two sailors fetched above, and `"signed_on"` is read from the first of them.

```text recording=querysets
slim[0].signed_on
  FetchOne.fetch(a DeferredAttribute for Sailor.signed_on, <Sailor: Ada>)
    DeferredAttribute.fetch_one(<Sailor: Ada>)  (Sailor.signed_on)
      Model.refresh_from_db(fields=['signed_on'])  (<Sailor: Ada>)
        QuerySet.only('signed_on')
          Query.add_immediate_loading(('signed_on',))
        QuerySet._fetch_all
          ModelIterable.__iter__
            SQLCompiler.execute_sql
              SQL SELECT "crew_sailor"."id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
            SQLCompiler.results_iter
            Model.from_db('default', ['id', 'signed_on'], [1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
```

`refresh_from_db` builds a queryset of its own, narrows it with `only` to the one field, and gets one row from it: a deferred field is fetched by a queryset that defers everything else. The row becomes a second instance, and the value is copied from that onto the first (`django/db/models/base.py:Model.refresh_from_db`). A read that goes this way is one statement for one field of one instance, so two deferred fields of an instance are two statements.

### `fetch_many`: one field, for every peer

Under `FETCH_PEERS`, where the instance has other peers still alive, the mode calls `DeferredAttribute.fetch_many` with all of them. Here four sailors are fetched under that mode with only their names, and `"signed_on"` is read from the first.

```text recording=querysets
peers = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id'))
...
peers[0].signed_on
  FetchPeers.fetch(a DeferredAttribute for Sailor.signed_on, <Sailor: Ada>)
    DeferredAttribute.fetch_many([<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>])  (Sailor.signed_on)
      QuerySet.values_list('signed_on', flat=True)
        Query.clear_deferred_loading
      QuerySet.in_bulk(id_list={1, 2, 3, 4})
        QuerySet.values_list('pk', 'signed_on')
          Query.clear_deferred_loading
        QuerySet._fetch_all
          ValuesListIterable.__iter__
            SQLCompiler.results_iter
              SQLCompiler.execute_sql
                SQL SELECT "crew_sailor"."id" AS "pk", "crew_sailor"."signed_on" AS "signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (%s, %s, %s, %s) with params (1, 2, 3, 4)
        -> {1: datetime(2011, 6, 1, 8, 0, tzinfo=UTC), 2: datetime(2026, 4, 10, 9, 0, tzinfo=UTC), 3: datetime(2011, 6, 1, 8, 0, tzinfo=UTC), 4: datetime(2026, 4, 10, 9, 0, tzinfo=UTC)}
['signed_on' in vars(sailor) for sailor in peers], len(peers[0]._state.peers)  ->  ([True, True, True, True], 4)
```

`fetch_many` does not go through `refresh_from_db`, and it makes no instances. It takes the base manager of the model that declares the field, for the database the first of the instances came from, asks it for a flat `values_list` of the one attname, and calls `QuerySet.in_bulk` on that with the set of the instances' primary keys, which gives a dictionary from key to value. Then it sets the value on each instance with `setattr` (`django/db/models/query_utils.py:DeferredAttribute.fetch_many`). The lines under `in_bulk` are that method's own way of working: it turns the flat list back into pairs of key and value, and filters them to the keys it was given ([`get`, `first`, `count` and the other methods that run a query at once](../querysets/results.md)). Here one statement brought four values, and the last line finds one on each of the four sailors.

> **Trap.** Every instance in the list is assigned the value the database returned, so a peer whose attribute the program has assigned since it was fetched has it overwritten. And an instance whose row is gone has no entry in the dictionary, so the loop raises `KeyError` when it reaches it, having assigned to the instances before it in the list.

In the first lines below the second sailor's `"signed_on"` is set to `None` before the first's is read. In the last, a sailor named Eve is fetched as a fifth peer and Eve's row is then deleted; its key is 6, a sailor with key 5 having been made and deleted in the same run.

```text recording=querysets
peers = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id')); peers[1].signed_on = None
...
peers[0].signed_on.year, peers[1].signed_on.year  ->  (2011, 2026)
  SQL SELECT "crew_sailor"."id" AS "pk", "crew_sailor"."signed_on" AS "signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (%s, %s, %s, %s) with params (1, 2, 3, 4)
eve = Sailor.objects.create(name='Eve', ship=petrel); peers = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id')); Sailor.objects.filter(name='Eve').delete()
...
peers[0].signed_on  ->  raises KeyError: 6
  SQL SELECT "crew_sailor"."id" AS "pk", "crew_sailor"."signed_on" AS "signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (%s, %s, %s, %s, %s) with params (1, 2, 3, 4, 6)
```

The `fetch_many` of a relation's descriptor begins otherwise, by setting aside the instances that already have their object cached ([The fetch modes](#the-fetch-modes)).

## The fetch modes

A relation's descriptor does not decide how an object that is missing is fetched. It calls `fetch` on the instance's fetch mode, `ModelState.fetch_mode`, with itself and the instance (`django/db/models/base.py:ModelState`, `django/db/models/fetch_modes.py`).

A fetch mode is an object with that one method. What it is handed is a **fetcher**: anything that can fetch its value for one instance, with a method `fetch_one`, and for a list of instances at once, with a method `fetch_many`. The forward descriptor is a fetcher. So is `ReverseOneToOneDescriptor`, and so is the `DeferredAttribute` of a deferred field, whose missing value goes through the same modes ([Reading a deferred field: `DeferredAttribute.__get__`](#reading-a-deferred-field-deferredattribute__get)).

| the mode | its class | what its `fetch` does |
|---|---|---|
| `FETCH_ONE` | `FetchOne` | calls the fetcher's `fetch_one` with the instance |
| `FETCH_PEERS` | `FetchPeers` | gathers the instance's **peers**, the instances that share its list, made with it by one run of a query; with more than one it calls the fetcher's `fetch_many` with all of them, and otherwise `fetch_one` |
| `FETCH_RAISE` | `FetchRaise` | raises `FieldFetchBlocked`, with the names of the instance's class and of the field |

*The three fetch modes. Each is the one object of its class, and `django.db.models` exports the three.*

> **Changed in 6.1.** Fetch modes are new. Before them a read of a related object that was not at hand always ran one query for that one instance, which is what `FETCH_ONE` still does.

### How an instance gets its mode, and its peers

An instance has `FETCH_ONE` until something gives it another: `ModelState.fetch_mode` is a descriptor that supplies `FETCH_ONE` the first time it is read (`django/db/models/base.py:ModelStateFetchModeDescriptor`). Another mode comes from a queryset. `QuerySet.fetch_mode` returns a copy of the queryset that carries the mode, and when the queryset runs, its `ModelIterable` passes the mode to `Model.from_db` with every row, which stores it in the new instance's state (`django/db/models/query.py:QuerySet.fetch_mode`, `django/db/models/query.py:ModelIterable`).

Peers are instances made together by one run of a query. Where the mode's `track_peers` is true, which among the three it is for `FetchPeers` only, `ModelIterable` keeps one list for the instances it makes of the queryset's own model, adds a weak reference to each as it makes it, and binds that list as `ModelState.peers` of each. Every one of those holds the same list, itself in it. The references are weak, the documentation says, so that instances the program has discarded are not kept by the list (`docs/topics/db/fetch-modes.txt`), and `FetchPeers.fetch` takes from it the instances that are still alive (`django/db/models/fetch_modes.py:FetchPeers.fetch`).

Here four sailors are fetched under `FETCH_PEERS`, and the ship of the first is read, then the ship of the last:

```text recording=models
crew = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).order_by('id')[:4])
...
crew[0].ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Ada>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Ada>)  (Sailor.ship)  raises KeyError
    FetchPeers.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Sailor: Ada>)
      ForwardManyToOneDescriptor.fetch_many([<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>])  (Sailor.ship)
        prefetch_related_objects([<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], 'ship')
          SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE ("fleet_ship"."id") IN ((%s), (%s)) with params (1, 2)
...
crew[3].ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Dag>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Dag>)  (Sailor.ship)  ->  <Ship: Gannet>
```

With four peers the mode calls `ForwardManyToOneDescriptor.fetch_many`. That method sets aside the instances that already have the object cached and gives the others to `prefetch_related_objects`, the function behind `prefetch_related`, with the field's name. One statement fetches the two ships that the four keys name, and fills the cache entry of each sailor (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.fetch_many`).

```text recording=models
Asked of the four
    [type(s._state.fetch_mode).__name__ for s in crew], len(crew[0]._state.peers), bram._state.peers  ->  (['FetchPeers', 'FetchPeers', 'FetchPeers', 'FetchPeers'], 4, ())
    crew[0].ship is crew[1].ship, crew[0].ship == crew[1].ship, crew[2].ship is crew[3].ship  ->  (True, True, True)
```

Sailors of one ship are given one Ship object between them, which a fetch for each sailor would not do. The third value of the first line is the peers of an instance fetched in the ordinary way: an empty tuple.

The fourth step of the read returns what is in the cache without the test for `None`. So where a key has no row, and the prefetch that `fetch_many` runs caches `None` for it, the read that set the fetch off returns `None` even from a field that may not be null, and a later read from such a field raises (`django/db/models/query.py:prefetch_one_level`). A peer with such a key raises at its first read, since the one prefetch cached `None` for each of them.

An instance that was fetched alone is its own only peer, and for it the mode calls `fetch_one`. Of this recording the statement that fetched the sailor is left out, and the lines under `fetch_one`, which are those of any such fetch:

```text recording=models
alone = Sailor.objects.fetch_mode(models.FETCH_PEERS).get(name='Bram')
...
alone.ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Bram>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  raises KeyError
    FetchPeers.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Sailor: Bram>)
      ForwardManyToOneDescriptor.fetch_one(<Sailor: Bram>)  (Sailor.ship)
```

The queryset that fetches a related object is given the instance's mode, so the object fetched has that mode, and so has what is fetched from it in turn. Under `FETCH_PEERS` the objects that one such fetch brings back are peers of each other.

### `FETCH_RAISE`

Under `FETCH_RAISE` the read that would have fetched raises instead:

```text recording=models
strict = Sailor.objects.fetch_mode(models.FETCH_RAISE).get(name='Bram')
...
strict.ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Bram>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  raises KeyError
    FetchRaise.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Sailor: Bram>)  raises FieldFetchBlocked
  the caller catches FieldFetchBlocked: Fetching of Sailor.ship blocked.
```

`FieldFetchBlocked` is a `FieldError` (`django/core/exceptions.py:FieldFetchBlocked`). The mode is reached only when the cache has no entry and the key is set. An object that is already cached, because it was assigned or was fetched with the instance, is returned under any mode.

## Peers: a list for each run of a query

Under a mode that tracks them, the instances of the queryset's model made by one **run** of a query, which is one call of the iterable's `__iter__`, are each other's peers. `ModelIterable.__iter__` asks the mode one thing, `FetchMode.track_peers`, which is false there and true on `FetchPeers` alone. Where it is true, the iterable keeps one list for the run, and for each instance it makes of the queryset's model it adds a weak reference to the list and binds the list as the instance's `ModelState.peers`. Each of those instances holds the same list, with itself in it, and the list goes on growing as later rows are read. Under the other modes nothing is bound, and `peers` is the empty tuple of the class (`django/db/models/query.py:ModelIterable.__iter__`, `django/db/models/base.py:ModelState`).

One evaluation of a queryset is a run, and so is one use of `QuerySet.iterator`. Instances from two evaluations are not peers, however alike the two querysets, and an instance that `get` fetched alone is its own only peer.

The list is built in two more places, in the same way. `RawModelIterable.__iter__` keeps one for the instances of a raw statement. And each `RelatedPopulator` has a list of its own, made with the populator, so the instances reached through one joined relation are peers of each other, and not of the instances they hang from (`django/db/models/query.py:RelatedPopulator`). The iterable classes behind `values` and `values_list` make no instances and read no mode.

```text recording=querysets
[len(s.ship._state.peers) for s in Sailor.objects.fetch_mode(models.FETCH_PEERS).select_related('ship')]  ->  [4, 4, 4, 4]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id")
[type(row).__name__ for row in Sailor.objects.fetch_mode(models.FETCH_PEERS).values('name')[:1]]  ->  ['dict']
  SQL SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" LIMIT 1
```

Four rows made four sailors and four ships, since `select_related` made a new instance of the joined model for each of these rows, though the table has two ships ([`select_related`: related objects from the same row](../relations/select-related.md)). The list each ship holds has four references. The second question was answered with a dictionary, which has no state to keep a mode or a list in.

> **Changed in 6.1.2.** The notes for 6.1.2, a release that at this commit is expected and not yet made, list as fixed a bug in 6.1 where `FETCH_PEERS` did not batch instances loaded by `select_related`, causing unnecessary queries (`docs/releases/6.1.2.txt`).

The references are weak so that the list does not keep alive instances the program has let go; the documentation gives the reason, as avoiding a leak of memory (`docs/topics/db/fetch-modes.txt`). `FetchPeers.fetch` takes from the list the instances whose references are still alive (`django/db/models/fetch_modes.py:FetchPeers.fetch`). In the loop recorded below, over `QuerySet.iterator` of a queryset with no prefetch lookups, the body keeps none of the instances: the one before is gone by the time a value is read from the next, and the value is fetched for one instance at a time, as it would be under `FETCH_ONE`.

```text recording=querysets
for sailor in Sailor.objects.fetch_mode(models.FETCH_PEERS).only('name').order_by('id').iterator(): seen(sailor.signed_on.year)
...
      Model.from_db('default', ['id', 'name'], (1, 'Ada'), fetch_mode=FETCH_PEERS)  (Sailor)
  FetchPeers.fetch(a DeferredAttribute for Sailor.signed_on, <Sailor: Ada>)
    DeferredAttribute.fetch_one(<Sailor: Ada>)  (Sailor.signed_on)
  the loop's body runs with 2011
      Model.from_db('default', ['id', 'name'], (2, 'Bram'), fetch_mode=FETCH_PEERS)  (Sailor)
  FetchPeers.fetch(a DeferredAttribute for Sailor.signed_on, <Sailor: Bram>)
    DeferredAttribute.fetch_one(<Sailor: Bram>)  (Sailor.signed_on)
  the loop's body runs with 2026
...
```

The objects a fetch for several peers brings back are peers in their turn, where they came from one run of a queryset that carries the mode ([How an instance gets its mode, and its peers](#how-an-instance-gets-its-mode-and-its-peers)).

An instance that has been pickled comes back with its mode and without its peers: `ModelState.__getstate__` leaves the list out. Each of the subclasses of `FetchMode` defines `__reduce__` to return the name its one instance is bound to, as a string. To `pickle` a string from `__reduce__` is the name of a global: it stores the name, and on loading looks it up in the module. So a mode that was pickled, in the state of an instance or as an attribute of a queryset, comes back as the same object and not as a copy of it.

```text recording=querysets
pickle.loads(pickle.dumps(models.FETCH_PEERS)) is models.FETCH_PEERS, models.FETCH_ONE.__reduce__()  ->  (True, 'FETCH_ONE')
```
