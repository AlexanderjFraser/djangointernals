---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Deferred fields and fetch modes in a queryset

`QuerySet.defer` and `QuerySet.only` leave columns out of a queryset's statement by recording names on its query, and an instance made without a value fetches it through a `DeferredAttribute` when the value is read. How it is fetched, for that instance, for all its peers or not at all, is decided by a fetch mode, `FETCH_ONE`, `FETCH_PEERS` or `FETCH_RAISE`, which `QuerySet.fetch_mode` sets on a queryset and the queryset hands to the instances it makes.

A table's row can be wide and a use of it narrow: a page that lists a thousand sailors by name has no use for the other columns of each. So a queryset can be told which columns to leave out of its statement. That saves the columns, and it raises two questions the statement cannot answer. An instance made from a short row is an instance like any other, and code that knows nothing of how it was fetched may read any attribute of it, so something has to happen at a read of a value that is not there. And whatever happens is a statement the program did not write: in a loop over the thousand it is a thousand statements, which cost more than the columns did.

The first question has a small answer. On an instance a deferred field is a key missing from its `__dict__` and nothing more, and the descriptor the field left on the class is what Python turns to when the key is missing ([An instance and its state](../models/instances.md)). The queryset's part is to select fewer columns and to tell `Model.from_db` which ones it selected. The second question is answered by an object the queryset carries, its **fetch mode**, which is handed the read of a missing value. The queryset gives its mode to the instances it makes, and under one of the modes it also tells each instance which others were made with it, its **peers**, so that a value missing from one can be fetched for all of them together. The same mode decides how a related object that is not at hand is fetched, and [Reading and setting related objects](../models/related-objects.md) sets the modes side by side and says what a relation's descriptor does under each.

## `FetchMode` and its subclasses

A mode is an instance of a subclass of `FetchMode`, a class with no state of its own, an attribute `track_peers` and one method, `FetchMode.fetch`, which takes a fetcher, the descriptor that was read and had no value to give, and an instance, and in the base class raises `NotImplementedError`. `FetchOne.fetch` calls the fetcher's `fetch_one` with the instance. `FetchPeers.fetch` calls the fetcher's `fetch_many` with the instance's peers where more than one of them is still alive, and its `fetch_one` otherwise. `FetchRaise.fetch` raises `FieldFetchBlocked`, which is a `FieldError`, with the names of the instance's class and of the fetcher's field. The module makes one instance of each subclass as it is imported, `FETCH_ONE`, `FETCH_PEERS` and `FETCH_RAISE`, and `django.db.models` exports them (`django/db/models/fetch_modes.py`, `django/core/exceptions.py:FieldFetchBlocked`).

> **Changed in 6.1.** Fetch modes are new in 6.1, and with them `QuerySet.fetch_mode`, the peers, and the argument `fetch_mode=` of `Model.from_db`. The release notes describe `FETCH_ONE`, the default, as the behaviour Django had before: a missing value is fetched for the one instance it was read from (`docs/releases/6.1.txt`).

## `defer` and `only`: names recorded on the query

A call of `QuerySet.defer` or of `QuerySet.only` sends nothing. Each returns what `QuerySet._chain` gives it, a clone unless cloning has been turned off for the queryset ([Clones: how a queryset is built](chaining.md)), whose query holds another `Query.deferred_loading`: a pair of a set of names and a flag (`django/db/models/sql/query.py:Query`). With the flag true, the names are the fields to leave out. With it false, they are the only fields to load. A new query has an empty set and a true flag, which leaves nothing out; and a pair whose set is empty restricts nothing, whichever way its flag stands.

`QuerySet.defer` hands its names to `Query.add_deferred_loading`, and `QuerySet.only` hands its own to `Query.add_immediate_loading`. What each makes of them depends on the flag it finds (`django/db/models/sql/query.py:Query.add_deferred_loading`, `django/db/models/sql/query.py:Query.add_immediate_loading`).

| the call | where the set is of names to leave out | where the set is of the only names to load |
|---|---|---|
| `defer` | adds its names to the set | takes its names out of the set |
| `only` | makes the set its own names, less those that were to be left out, and turns the flag to false | replaces the set with its own names |

*What `defer` and `only` do to `Query.deferred_loading`, by the flag they find.*

So a second `defer` adds to the first, a second `only` replaces the first, and an `only` leaves the pair a list of what to load: the docstring of `add_immediate_loading` puts it as overriding any existing immediate values and respecting existing deferrals. One case falls outside the table: a `defer` that leaves nothing of such a list. The pair then starts again from empty, as after `only('name').defer('name')` in the recording below, and those of the `defer`'s names that were not in the list become the names to leave out.

In the recordings, made on SQLite over the rows [QuerySets](../querysets.md) lists, a line at the margin is Python that was run, with the value of an expression after `->`; the lines under it are the calls it set going, nested as they were made and only those the passage is about, with what a call returned after `->`; and a line that begins `SQL` is a statement as Django handed it to its cursor. What a question calls deferred of a queryset is the `deferred_loading` of its query, with the names in order.

```text recording=querysets
deferred(Sailor.objects.all())  ->  ([], True)
deferred(Sailor.objects.defer('name')), deferred(Sailor.objects.defer('name').defer('signed_on'))  ->  ((['name'], True), (['name', 'signed_on'], True))
deferred(Sailor.objects.only('name')), deferred(Sailor.objects.only('name').only('signed_on'))  ->  ((['name'], False), (['signed_on'], False))
deferred(Sailor.objects.only('name', 'signed_on').defer('name')), deferred(Sailor.objects.defer('name').only('name', 'signed_on'))  ->  ((['signed_on'], False), (['signed_on'], False))
deferred(Sailor.objects.defer('name').defer(None))  ->  ([], True)
Sailor.objects.only(None)  ->  raises TypeError: Cannot pass None as an argument to only().
sorted(Sailor.objects.only('name').get(pk=1).get_deferred_fields()), sorted(Sailor.objects.defer('id').get(pk=1).get_deferred_fields())  ->  (['ship_id', 'signed_on'], [])
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
deferred(Sailor.objects.only('name').defer('name')), deferred(Sailor.objects.only('pk'))  ->  (([], True), (['id'], False))
list(Sailor.objects.only('cargo'))  ->  raises FieldDoesNotExist: Sailor has no field named 'cargo'
```

`defer(None)` empties the pair, through `Query.clear_deferred_loading`. `only(None)` is refused with `TypeError`: a comment in the method says that `None` can be passed to `defer` alone, and that people will try all the same. Both methods refuse a queryset made by `union`, `intersection` or `difference` ([Combining querysets: the operators and `union`](combining.md)), and one on which `values` or `values_list` has been called, which makes no instances ([`values` and `values_list`: rows as dictionaries and tuples](values.md)). `only` refuses one thing more, a name whose first part is the alias of a `FilteredRelation` on the query, a relation joined under a condition of its own ([`filter`, `exclude` and `Q` objects](filters.md)) (`django/db/models/query.py:QuerySet.defer`, `django/db/models/query.py:QuerySet.only`).

Neither method looks a name up in the model, except that `add_immediate_loading` exchanges `"pk"` for the name of the model's primary key, which `add_deferred_loading` does not: `only('pk')` is stored as `"id"`. Any other name is stored as it was written: a field's name, or several names joined by `"__"` to reach a field of a model that `select_related` joins ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)).

Turning the pair into columns is the query's work and the compiler's. The compiler asks `Query.get_select_mask` for the fields that are to be loaded, model by model, and where the pair restricts anything that method puts the model's primary key among them, whatever the names say ([From QuerySet to SQL](../sql.md)). The question about `Model.get_deferred_fields` shows both halves: after `only` with one name the instance lacks two fields and not three, and after a `defer` of the primary key it lacks none. The name `"cargo"`, which is no field of Sailor, is refused with `FieldDoesNotExist` when the queryset is evaluated, and no statement is sent (`django/db/models/sql/query.py:Query.get_select_mask`).

## A shorter statement, and a shorter list for `from_db`

A queryset that leaves columns out sends a shorter statement, and with each row it hands `Model.from_db` the list of the names it did select. Here two sailors are fetched with `only`.

```text recording=querysets
slim = list(Sailor.objects.only('name').order_by('id')[:2])
  QuerySet.only('name')
    Query.add_immediate_loading(('name',))
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQLCompiler.execute_sql
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC LIMIT 2
      SQLCompiler.results_iter
      Model.from_db('default', ['id', 'name'], (1, 'Ada'), fetch_mode=FETCH_ONE)  (Sailor)
      Model.from_db('default', ['id', 'name'], (2, 'Bram'), fetch_mode=FETCH_ONE)  (Sailor)
```

The statement selects two columns, the one that was named and the primary key. A row of two values does not say which fields they belong to, so the iterable says it. Before it reads the first row, `ModelIterable.__iter__` makes a list of the attnames of the columns the compiler selected for the queryset's model, an attname being the name of the attribute that holds a field's value on an instance, `"ship_id"` for the foreign key ship, and it passes that list to `Model.from_db` with every row, as the second argument: here `['id', 'name']` (`django/db/models/query.py:ModelIterable.__iter__`). `from_db` compares the number of values with the number of the model's concrete fields, and where the two differ it puts a marker, `DEFERRED`, in the place of each field whose attname is not in the list; `Model.__init__` sets nothing for a marker ([An instance and its state](../models/instances.md)). No list of deferred fields passes from the queryset to the instance. The queryset says what was fetched, and the instance is short by the rest.

The other makers of instances do the same for their own columns: a `RelatedPopulator`, for a model that `select_related` joins, and `RawModelIterable`, from the columns a raw statement returned ([From rows to instances: `ModelIterable` and `select_related`](iterables.md), [Raw querysets](raw.md)).

## Reading a deferred field: `DeferredAttribute.__get__`

A field that has a column leaves a `DeferredAttribute` on its model class, under its attname. The class has no `__set__`, so Python goes to it only when the instance's `__dict__` has no entry of that name, which is when the field is deferred ([An instance and its state](../models/instances.md)). Read on the class, the attribute is the descriptor itself. Read on an instance, `DeferredAttribute.__get__` looks in the `__dict__` itself before anything else: a subclass that does define `__set__`, such as the `ForeignKeyDeferredAttribute` under a foreign key's attname, is consulted at every read, and finds the value there unless the field is deferred. Where there is no value it tries three things in turn (`django/db/models/query_utils.py:DeferredAttribute.__get__`).

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

`DeferredAttribute.fetch_one` is a single call: `Model.refresh_from_db`, with the field's attname as the one field to reload ([An instance and its state](../models/instances.md)) (`django/db/models/query_utils.py:DeferredAttribute.fetch_one`). In this recording slim is the list of the two sailors fetched above, and `"signed_on"` is read from the first of them.

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

`fetch_many` does not go through `refresh_from_db`, and it makes no instances. It takes the base manager of the model that declares the field, for the database the first of the instances came from, asks it for a flat `values_list` of the one attname, and calls `QuerySet.in_bulk` on that with the set of the instances' primary keys, which gives a dictionary from key to value. Then it sets the value on each instance with `setattr` (`django/db/models/query_utils.py:DeferredAttribute.fetch_many`). The lines under `in_bulk` are that method's own way of working: it turns the flat list back into pairs of key and value, and filters them to the keys it was given ([`get`, `first`, `count` and the other methods that run a query at once](results.md)). Here one statement brought four values, and the last line finds one on each of the four sailors.

> **Trap.** Every instance in the list is assigned the value the database returned, so a peer whose attribute the program has assigned since it was fetched has it overwritten. And an instance whose row is gone has no entry in the dictionary, so the loop raises `KeyError` when it reaches it, having assigned to the instances before it in the list.

In the first lines below the second sailor's `"signed_on"` is set to `None` before the first's is read. In the last, a sailor named Eve is fetched as a fifth peer and her row is then deleted; her key is 6, a sailor with key 5 having been made and deleted in the same run.

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

The `fetch_many` of a relation's descriptor begins otherwise, by setting aside the instances that already have their object cached ([Reading and setting related objects](../models/related-objects.md)).

## The fetch mode a queryset carries

A queryset holds its mode as `QuerySet._fetch_mode`, which `QuerySet.__init__` sets to `DEFAULT_FETCH_MODE`, a name of the module that is bound to `FETCH_ONE` (`django/db/models/query.py:DEFAULT_FETCH_MODE`). `QuerySet.fetch_mode` sets the mode it was given on what `QuerySet._chain` returns, a clone unless cloning is turned off for the queryset, and that is the whole of the method. It tests neither the query, so it is accepted after `values`, after a slice and after `union`, nor its argument (`django/db/models/query.py:QuerySet.fetch_mode`).

From there the mode travels both ways: from a queryset to the instances it makes, and from an instance to the querysets that are made on its behalf, so that what is reached from an instance has the instance's mode. `Model.from_db` stores the mode in the new instance's state, and an instance that was given none has `FETCH_ONE` from the first time its mode is read ([Reading and setting related objects](../models/related-objects.md)); a model whose own `from_db` does not take the argument is called without it ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)). In the questions below, what is written as mode of several things is the fetch mode of each, a queryset's or an instance's, by its name.

```text recording=querysets
mode(Sailor.objects.all(), Sailor.objects.fetch_mode(models.FETCH_RAISE), Sailor.objects.fetch_mode(models.FETCH_RAISE).filter(pk=1).order_by('name'))  ->  (FETCH_ONE, FETCH_RAISE, FETCH_RAISE)
mode(ada, Sailor.objects.fetch_mode(models.FETCH_PEERS).get(pk=1), Sailor.objects.fetch_mode(models.FETCH_PEERS).get(pk=1).ship)  ->  (FETCH_ONE, FETCH_PEERS, FETCH_PEERS)
...
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor'), Sailor.objects.fetch_mode(models.FETCH_PEERS).create(name='Eve', ship=petrel))  ->  (FETCH_PEERS, FETCH_PEERS)
...
mode(petrel.crew.all(), Ship.objects.fetch_mode(models.FETCH_RAISE).get(pk=1).crew.all())  ->  (FETCH_ONE, FETCH_RAISE)
```

A refined queryset keeps the mode. An instance has the mode of the queryset that made it, and so has the ship that was read from it, which the forward descriptor's queryset fetched. The `RawQuerySet` has it, and so has the sailor `create` saved. And the queryset of a ship's related manager has the ship's mode, which the manager's `_apply_rel_filters` sets on it: the default for petrel, a Ship made in the ordinary way, and `FETCH_RAISE` for the same ship fetched under that mode.

Some places do not hand the mode on. `RawQuerySet._clone` makes its copy without it, so the `RawQuerySet` that `RawQuerySet.prefetch_related` returns has the default mode (`django/db/models/query.py:RawQuerySet._clone`). `QuerySet.bulk_create` sets no mode on the instances it is given, where `create` sets the queryset's on the one it makes (`django/db/models/query.py:QuerySet.bulk_create`, `django/db/models/query.py:QuerySet.create`). And where `QuerySet.prefetch_related` has a related manager fetch the related objects of all a queryset's instances with one statement, the manager's queryset for that statement does not pass through `_apply_rel_filters`: it starts from what the class of the related model's default manager gives, and no mode is set on it. So the objects prefetched for the far end of a foreign key, or across a many-to-many relation, have the mode of that manager's querysets, which for a plain manager is the default, whatever the mode of the instances they were fetched for. A foreign key's own descriptor or a one-to-one field's builds the queryset for a prefetch with its `get_queryset`, and it has the mode of the first of the instances. Either way a queryset that the caller supplied for the prefetch, in a `Prefetch`, is used in its place and keeps the mode it came with ([`prefetch_related`: related objects in a second query](prefetch.md), `django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`, `django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.get_prefetch_querysets`).

```text recording=querysets
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor').prefetch_related('ship'))  ->  (FETCH_ONE)
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('ship')[0].ship)  ->  (FETCH_PEERS)
...
mode(Ship.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('crew')[0].crew.all()[0])  ->  (FETCH_ONE)
```

The raw queryset lost `FETCH_PEERS` at `prefetch_related`. A ship prefetched for sailors of that mode has it, and a sailor prefetched for a ship of that mode has `FETCH_ONE`: what is missing from such a sailor is fetched for that sailor alone. The documentation says that Django copies the fetch mode of an instance to any related objects it fetches, so that the mode applies to a whole tree of relationships (`docs/topics/db/fetch-modes.txt`). The prefetched sailor is a related object that does not have the ship's mode: there the recording and the documentation differ.

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

Four rows made four sailors and four ships, since `select_related` made a new instance of the joined model for each of these rows, though the table has two ships ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)). The list each ship holds has four references. The second question was answered with a dictionary, which has no state to keep a mode or a list in.

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

The objects a fetch for several peers brings back are peers in their turn, where they came from one run of a queryset that carries the mode ([Reading and setting related objects](../models/related-objects.md)).

An instance that has been pickled comes back with its mode and without its peers: `ModelState.__getstate__` leaves the list out. Each of the subclasses of `FetchMode` defines `__reduce__` to return the name its one instance is bound to, as a string. To `pickle` a string from `__reduce__` is the name of a global: it stores the name, and on loading looks it up in the module. So a mode that was pickled, in the state of an instance or as an attribute of a queryset, comes back as the same object and not as a copy of it.

```text recording=querysets
pickle.loads(pickle.dumps(models.FETCH_PEERS)) is models.FETCH_PEERS, models.FETCH_ONE.__reduce__()  ->  (True, 'FETCH_ONE')
```
