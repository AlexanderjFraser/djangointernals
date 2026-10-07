---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Deleting: the `Collector`

`Model.delete` sends no `"DELETE"` of its own. It hands the instance to a `Collector`, which first gathers everything the delete reaches, by following each foreign key and one-to-one field that points at the instance's model and doing what that relation's `on_delete` says, and then deletes what it gathered: first the rows it never fetched, then the instances it holds, one model at a time.

A row is seldom alone. Other rows hold its key in a foreign key's column, and each of those relations was declared with an `on_delete`: what is to become of a row when the row it points at is deleted. It is deleted too, or the delete is refused, or its column is set to null. Django does most of these itself, in Python, and to do them it has to find the rows.

So a delete is two jobs, and one object does both (`django/db/models/deletion.py:Collector`). `Collector.collect` deletes nothing. It goes from the instance to the rows that point at it, and from those to the rows that point at them, and notes for each set of rows what is to be done with it. `Collector.delete` then does what was noted, and begins a transaction for it where none is open, except on the short way it has for a single instance. A delete that `PROTECT` or `RESTRICT` refuses is refused by the first of the two, before any statement of the second is sent (`django/db/models/deletion.py:Collector.collect`, `django/db/models/deletion.py:Collector.delete`).

The examples are the models of the harbour ([Models and fields](../models.md)). All but three of their foreign keys are declared with `CASCADE`, and so are the ones Django made itself: the two keys of Voyage_calls, the table of the many-to-many field `"calls"`, and `"sailor_ptr"`, the `OneToOneField` that the metaclass made as the link from Officer to Sailor. The three are `"home"` of Ship, which is `PROTECT`, its nullable one-to-one field `"captain"`, which is `SET_NULL`, and `"book"`, the foreign key from a LogEntry of the office to its Logbook, which is `DB_CASCADE`.

This is a voyage being deleted. Rows of two tables point at a voyage: its ports of call in Voyage_calls, and the office's manifests, a Manifest being what a voyage carried, with a foreign key to it. Nothing is fetched, and each table loses its rows in one statement:

```text recording=models
Collector.collect([<Voyage: Voyage object (2)>])
  Collector.can_fast_delete([<Voyage: Voyage object (2)>])  ->  False
  Collector.add([<Voyage: Voyage object (2)>])  ->  not already collected: [<Voyage: Voyage object (2)>]
  Collector.can_fast_delete(the class Voyage_calls, from_field=Voyage_calls.voyage)  ->  True
  Collector.can_fast_delete(the class Manifest, from_field=Manifest.voyage)  ->  True
Collector.delete
  Collector.sort
  Collector.can_fast_delete(<Voyage: Voyage object (2)>)  ->  False
  Atomic.__enter__  (savepoint=False)
    SQL BEGIN
  QuerySet._raw_delete  (a QuerySet of Voyage_calls, not yet fetched)
    SQL DELETE FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" IN (%s) with params (2,)
  QuerySet._raw_delete  (a QuerySet of Manifest, not yet fetched)
    SQL DELETE FROM "office_manifest" WHERE "office_manifest"."voyage_id" IN (%s) with params (2,)
  DeleteQuery.delete_batch([2])  (Voyage)
    SQL DELETE FROM "fleet_voyage" WHERE "fleet_voyage"."id" IN (%s) with params (2,)
  Atomic.__exit__
    BaseDatabaseWrapper.commit
  -> (2, {'fleet.Voyage_calls': 1, 'fleet.Voyage': 1})
```

Under `Collector.collect` the collector entered the voyage in what it holds, and kept a queryset, not fetched, for each of the two models that point at it; the two lines that made the querysets are left out. Under `Collector.delete` is the transaction: a `"DELETE"` for each queryset, on the foreign key since no row's own key was ever read, and one for the voyage by its key. This voyage had no manifest, and the counts do not mention the statement that removed nothing.

## What `Model.delete` does

`Model.delete` refuses an instance whose primary key is not set, with a `ValueError` whose message names the model and the attribute that holds no key. Otherwise it settles the database, which is the alias it was given or else what the router's `ConnectionRouter.db_for_write` returns for the instance, makes a `Collector` for that alias, calls `Collector.collect` with the instance in a list, and returns what `Collector.delete` returns (`django/db/models/base.py:Model.delete`, `django/db/models/deletion.py:Collector`).

The collector is also given its **origin**, the object the delete began from: an instance here, a queryset when a queryset is deleted. It does nothing with it but pass it to the receivers of `pre_delete` and `post_delete`, so a receiver called for a manifest is told that it was a voyage that was deleted.

What comes back is a pair: the number of rows deleted, and a dictionary of that number by model, under each model's label. `Model.adelete` awaits `delete`, wrapped in `sync_to_async`, with the same arguments.

## What a collector holds

A `Collector` is made for one delete on one database (`django/db/models/deletion.py:Collector`). Between `Collector.collect` and `Collector.delete` everything it knows is in these attributes:

| attribute | what it holds | filled by | what `Collector.delete` does with it |
|---|---|---|---|
| `Collector.data` | the instances to delete, by model class | `Collector.add` | deletes them by key, one model at a time, and sends the signals for them |
| `Collector.fast_deletes` | querysets whose rows are to be deleted without having been fetched | `Collector.collect` | sends one `"DELETE"` for each, with the queryset's own condition |
| `Collector.field_updates` | by field and value, the rows whose foreign key is to be given that value | `Collector.add_field_update` | updates those rows, one field and value at a time |
| `Collector.restricted_objects` | by model and field, the rows that `RESTRICT` found | `Collector.add_restricted_objects` | nothing: `collect` settles them before it returns |
| `Collector.dependencies` | for a model, the models whose rows have to be deleted before its own | `Collector.add_dependency` | puts the models of `data` in order by it |

*What a collector accumulates while it collects, and what becomes of each when it deletes.*

An instance in `data` is one Django holds: it can send a signal about it, and can use its key to look for the rows that point at it. A queryset in `fast_deletes` stands for rows nobody has seen.

## `Collector.collect`

`Collector.collect` is given a collection of instances of one model: the list that `Model.delete` made, a queryset, or the rows a relation's function hands back to it. With each it does the same things in the same order (`django/db/models/deletion.py:Collector.collect`).

First, if `Collector.can_fast_delete` accepts what was given, it goes into `Collector.fast_deletes` as it stands and the method returns. A list is never accepted, so the call that `Model.delete` makes always goes on; a queryset may be.

Then `Collector.add` enters the instances in `Collector.data` under the class of the first of them, and returns those that were not there before (`django/db/models/deletion.py:Collector.add`). When none is new, `collect` returns, which is also what ends the recursion where relations lead back to rows already collected.

For a child with a table of its own, the parent's row of each new instance is collected too, by a call of `collect` that is told not to follow relations, unless this call was told to keep parents. The docstring of `collect` calls this the one case in which a cascade follows a foreign key forwards.

The relations come next. `get_candidate_relations_to_delete` picks, from what `Options.get_fields` lists for the model, the entries that were made automatically, have no column, and are one-to-one or one-to-many (`django/db/models/deletion.py:get_candidate_relations_to_delete`, `django/db/models/options.py:Options.get_fields`). Among Django's own classes only a rel answers to that: the far end of a foreign key or a one-to-one field that points at this model, whichever model declares it. A child with a table of its own has the relations that point at its parents too: an Officer's list has those that point at Sailor, `"captain"` of Ship among them, and not its own `"sailor_ptr"` (`django/db/models/options.py:Options._get_fields`). A model's own relation fields are not in the list: they point away from it, and deleting a ship does nothing to its port.

A many-to-many rel is left out, and the rows of such a relation are reached all the same, because its through model has two foreign keys of its own ([Many-to-many relations](many-to-many.md)). Where Django made that model, both keys have a `related_name` ending in `"+"`, which makes a relation **hidden**, and `get_candidate_relations_to_delete` asks for the hidden ones too (`django/db/models/fields/related.py:create_many_to_many_intermediary_model`) ([The options: what a model keeps as `_meta`](options.md)).

For each relation `collect` reads the `on_delete` its field was declared with, kept on the rel as `ForeignObjectRel.on_delete` ([Relations: a field, its rel and the class at the other end](relations.md)), and does one of three things.

It passes the relation over when the value is in `SKIP_COLLECTION`: `DO_NOTHING`, and `DB_CASCADE`, `DB_SET_NULL` and `DB_SET_DEFAULT`, which leave the rows to the database. Only a collector made with `force_collection=True` does otherwise.

It marks the relation for a **fast delete** when `can_fast_delete` accepts the related model. Once every relation has been gone through, each model so marked gives a queryset of its rows that point at the new instances, which goes into `fast_deletes` unfetched.

Otherwise it gets the rows and calls the relation's `on_delete` with them. `Collector.related_objects` makes the queryset: the related model's base manager, not its default one, filtered to the rows whose field is one of the instances (`django/db/models/deletion.py:Collector.related_objects`) ([Managers](managers.md)). The function is called with the collector, the field, the queryset and the alias, and for most functions only if the queryset has rows, which is found out by fetching it. The fetch is as spare as will do: where no receiver of `pre_delete` or `post_delete` is connected for the related model, the queryset is as a rule narrowed with `QuerySet.only` to the key and the fields that relations to that model refer to.

After the relations, a private field with an attribute named `"bulk_related_objects"`, which in Django's own source is a `GenericRelation`, is asked for the rows that point at the new instances through it, and those are collected by another call of `collect` (`django/contrib/contenttypes/fields.py:GenericRelation.bulk_related_objects`) ([Content types, static files and the other contrib apps](../contrib.md)). Last, in the outermost call only, the rows that `RESTRICT` found are settled.

### The `on_delete` functions

Apart from the three that leave the rows to the database, the values `on_delete` takes are ordinary functions of `django/db/models/deletion.py`, each called with the collector, the field, the rows and the alias. What a relation does on a delete is whatever its function does to the collector with them, and `ForeignKey.__init__` asks of the value only that it can be called (`django/db/models/fields/related.py:ForeignKey.__init__`).

| function | what it does with the rows it is handed |
|---|---|
| `CASCADE` | calls `collect` on them, naming the model the field points at as the source |
| `PROTECT` | raises `ProtectedError`, which carries them |
| `RESTRICT` | files them with `Collector.add_restricted_objects`, and adds a dependency between the two models |
| `SET_NULL` | calls `Collector.add_field_update` with `None` |
| `SET_DEFAULT` | calls `add_field_update` with the field's default |
| `SET` | is not such a function but returns one, which calls `add_field_update` with the value `SET` was given or, where that value is callable, with what calling it returns |
| `DO_NOTHING` | nothing, and `collect` does not call it: it is in `SKIP_COLLECTION` |

*The functions a relation can name as its `on_delete`.*

`CASCADE` is `collect` calling itself by way of the relation. The nested call is told the model the relation points at, and `add` makes a dependency of it: these rows are to be deleted before that model's. Where the field may be null `add` makes none. The source's comment there gives the reason: such relations are nulled out before deleting, and so do not affect the order. `CASCADE` itself schedules that update only on a backend whose `BaseDatabaseFeatures.can_defer_constraint_checks` is false (`django/db/models/deletion.py:CASCADE`, `django/db/models/deletion.py:Collector.add`).

`SET_NULL`, and the function `SET` returns for a value that is not callable, carry a true attribute `"lazy_sub_objs"`: `collect` calls them without fetching the rows to see whether there are any, and the queryset they are handed, still unfetched when `Collector.delete` comes to it, becomes the condition of one `"UPDATE"`.

### `ProtectedError` and `RestrictedError`

`ProtectedError` and `RestrictedError` are subclasses of `IntegrityError`, each made with a message and the rows that stood in the way, kept as `ProtectedError.protected_objects` and `RestrictedError.restricted_objects` (`django/db/models/deletion.py:ProtectedError`, `django/db/utils.py:IntegrityError`).

A port has ships that call it home, through `"home"`. Three more models point at a port, with `CASCADE`: Voyage_calls; Licence, the model between Sailor and Port, with a foreign key to each; and Berth, a model of the office whose key is a port and a number. In `collect` for such a port the error is raised at the first relation and leaves only after the last:

```text recording=models
    Collector.can_fast_delete(the class Ship, from_field=Ship.home)  ->  False
    Collector.related_objects(Ship, [Ship.home], [<Port: Bergen>])  ->  a QuerySet of Ship, not yet fetched
    SQL SELECT "fleet_ship"."id" FROM "fleet_ship" WHERE "fleet_ship"."home_id" IN (%s) ORDER BY "fleet_ship"."name" ASC with params (1,)
    PROTECT(collector, Ship.home, a QuerySet of Ship, fetched, 2 rows, 'default')  raises ProtectedError
    Collector.can_fast_delete(the class Voyage_calls, from_field=Voyage_calls.port)  ->  True
    Collector.can_fast_delete(the class Licence, from_field=Licence.port)  ->  True
    Collector.can_fast_delete(the class Berth, from_field=Berth.port)  ->  True
    raises ProtectedError
the caller catches ProtectedError: Cannot delete some instances of model 'Port' because they are referenced through protected foreign keys: 'Ship.home'.
its protected_objects are Ships with the keys [1, 3]
```

`collect` caught the exception that `PROTECT` raised, kept its rows under the name of the relation it was working through, and went on; after the last relation it raised, once, an error that names each relation under which a `ProtectedError` had arrived, here the one protecting field, and carries the rows of them all. One statement was sent, a `"SELECT"` of the ships' keys.

`RESTRICT` raises nothing when it is called. It files the rows in `Collector.restricted_objects` and adds a dependency (`django/db/models/deletion.py:RESTRICT`). Whether they stand in the way is not yet known: a restricted row may itself be on its way out, reached by a cascade through another of its relations. So the question is put at the end of the outermost call, the one `Model.delete` or `QuerySet.delete` makes. The calls nested in it, which `CASCADE` makes and which `collect` makes for a parent or a generic relation, pass `fail_on_restricted=False` and skip it.

There, each restricted row that is also in `data` is struck out. Each queryset in `fast_deletes` whose model has restricted rows is asked, by a query, which of them it would delete, and those are struck out too (`django/db/models/deletion.py:Collector.clear_restricted_objects_from_queryset`). If any row is left, `RestrictedError` is raised. A row behind `PROTECT` stops a delete whatever else is being deleted; a row behind `RESTRICT` stops it only if that row would be left behind.

## A ship is deleted

Deleting one ship of the harbour takes `Collector.collect` two levels down, to rows that are collected, rows that are marked for a fast delete and rows that are only to be updated (`django/db/models/deletion.py:Collector.collect`). The Petrel has a voyage and five sailors, and this is what `collect` did with it:

```text recording=models
Collector.collect([<Ship: Petrel>])
  Collector.can_fast_delete([<Ship: Petrel>])  ->  False
  Collector.add([<Ship: Petrel>])  ->  not already collected: [<Ship: Petrel>]
  Collector.can_fast_delete(the class Voyage, from_field=Voyage.ship)  ->  False
  Collector.related_objects(Voyage, [Voyage.ship], [<Ship: Petrel>])  ->  a QuerySet of Voyage, not yet fetched
  SQL SELECT "fleet_voyage"."id" FROM "fleet_voyage" WHERE "fleet_voyage"."ship_id" IN (%s) with params (1,)
  CASCADE(collector, Voyage.ship, a QuerySet of Voyage, fetched, 1 rows, 'default')
    Collector.collect(a QuerySet of Voyage, fetched, 1 rows, source=Ship, fail_on_restricted=False)
      Collector.can_fast_delete(a QuerySet of Voyage, fetched, 1 rows)  ->  False
      Collector.add(a QuerySet of Voyage, fetched, 1 rows)  ->  not already collected: [<Voyage: Voyage object (1)>]
      Collector.can_fast_delete(the class Voyage_calls, from_field=Voyage_calls.voyage)  ->  True
      Collector.can_fast_delete(the class Manifest, from_field=Manifest.voyage)  ->  True
      Collector.related_objects(Voyage_calls, [Voyage_calls.voyage], [<Voyage: Voyage object (1)>])  ->  a QuerySet of Voyage_calls, not yet fetched
      Collector.related_objects(Manifest, [Manifest.voyage], [<Voyage: Voyage object (1)>])  ->  a QuerySet of Manifest, not yet fetched
  Collector.can_fast_delete(the class Sailor, from_field=Sailor.ship)  ->  False
  Collector.related_objects(Sailor, [Sailor.ship], [<Ship: Petrel>])  ->  a QuerySet of Sailor, not yet fetched
  SQL SELECT "crew_sailor"."id" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (%s) with params (1,)
  CASCADE(collector, Sailor.ship, a QuerySet of Sailor, fetched, 5 rows, 'default')
    Collector.collect(a QuerySet of Sailor, fetched, 5 rows, source=Ship, fail_on_restricted=False)
      Collector.can_fast_delete(a QuerySet of Sailor, fetched, 5 rows)  ->  False
      Collector.add(a QuerySet of Sailor, fetched, 5 rows)  ->  not already collected: [<Sailor: pk=1>, <Sailor: pk=2>, <Sailor: pk=4>, <Sailor: pk=5>, <Sailor: pk=7>]
      Collector.can_fast_delete(the class Ship, from_field=Ship.captain)  ->  False
      Collector.related_objects(Ship, [Ship.captain], [<Sailor: pk=1>, <Sailor: pk=2>, <Sailor: pk=4>, <Sailor: pk=5>, <Sailor: pk=7>])  ->  a QuerySet of Ship, not yet fetched
      SET_NULL(collector, Ship.captain, a QuerySet of Ship, not yet fetched, 'default')
        Collector.add_field_update(Ship.captain, None, a QuerySet of Ship, not yet fetched)
      Collector.can_fast_delete(the class Officer, from_field=Officer.sailor_ptr)  ->  False
      Collector.related_objects(Officer, [Officer.sailor_ptr], [<Sailor: pk=1>, <Sailor: pk=2>, <Sailor: pk=4>, <Sailor: pk=5>, <Sailor: pk=7>])  ->  a QuerySet of Officer, not yet fetched
      SQL SELECT "crew_sailor"."id", "crew_officer"."sailor_ptr_id" FROM "crew_officer" INNER JOIN "crew_sailor" ON ("crew_officer"."sailor_ptr_id" = "crew_sailor"."id") WHERE "crew_officer"."sailor_ptr_id" IN (%s, %s, %s, %s, %s) with params (1, 2, 4, 5, 7)
      Collector.can_fast_delete(the class Licence, from_field=Licence.sailor)  ->  True
      Collector.related_objects(Licence, [Licence.sailor], [<Sailor: pk=1>, <Sailor: pk=2>, <Sailor: pk=4>, <Sailor: pk=5>, <Sailor: pk=7>])  ->  a QuerySet of Licence, not yet fetched
```

Two relations point at Ship, and neither could be marked for a fast delete, because rows of further models point at a voyage and at a sailor, which is one of [the things that rule a fast delete out](#collectorcan_fast_delete-whether-rows-can-go-unseen). So the ship's voyages were fetched, as keys and nothing more, and `CASCADE` handed them back to `collect`, which found the two models that point at Voyage and marked both.

The five sailors went the same way, with three relations behind them. The one-to-one field `"captain"` is `SET_NULL`: its function was called with a queryset that was never fetched, and left a field update. `"sailor_ptr"` of Officer could not be marked, since an Officer inherits the relations that point at Sailor and they are not ones to pass over; its rows were fetched and there were none, so `CASCADE` was not called. And Licence was marked.

```text figure=what-a-ship-reaches
petrel.delete(): what Collector.collect reached, one relation at a time, and how each set of rows was dealt with.
An indented line is a model with a relation that points at the model above it, with the field and its on_delete.

Ship: Petrel, the instance given            entered in data
    Voyage, by ship, CASCADE                not a fast delete: fetched, keys only; 1 row, entered in data
        Voyage_calls, by voyage, CASCADE    a fast delete: a queryset, nothing fetched
        Manifest, by voyage, CASCADE        a fast delete: a queryset, nothing fetched
    Sailor, by ship, CASCADE                not a fast delete: fetched, keys only; 5 rows, entered in data
        Ship, by captain, SET_NULL          a field update: a queryset, nothing fetched
        Officer, by sailor_ptr, CASCADE     not a fast delete: fetched, no rows, nothing done
        Licence, by sailor, CASCADE         a fast delete: a queryset, nothing fetched

Not reached: Port. Ship's field home points from the ship at its port. A child's link to its parent aside, a delete follows only what points at what it deletes.
```

*What the delete of one ship reached. Rows were fetched where their keys were needed to go further, and the rows at the ends of the tree were left to be deleted, or updated, unseen, but for Officer, where a fetch found none.*

`collect` left the collector holding a ship, a voyage and five sailors in `Collector.data`, three querysets in `Collector.fast_deletes`, one field update, and the dependencies that Voyage and Sailor go before Ship. What `Collector.delete` then sent is under [The general case](#the-general-case).

## `Collector.can_fast_delete`: whether rows can go unseen

`Collector.can_fast_delete` is the test of whether rows can be deleted by one statement without being fetched (`django/db/models/deletion.py:Collector.can_fast_delete`). A no does not by itself mean a fetch. For a relation, a no hands the rows over to the relation's function, and `SET_NULL` takes them unfetched. For rows that `CASCADE` is to delete a no does mean a fetch, and outside a forced collector it is given for one of two reasons: somebody is to be told of each row, or the rows' keys are needed to find what else must go with them. The method says no when any of these holds:

- the collector was made with `force_collection=True`;
- the question comes on behalf of a relation, and the relation's `on_delete` is not `CASCADE` itself;
- what it is asked about is neither a model class, nor an instance, nor a queryset: a list, for one;
- a receiver is connected to `pre_delete` or to `post_delete` for the model, a receiver connected for every sender included (`django/dispatch/dispatcher.py:Signal.has_listeners`);
- the model has a parent with a table, unless the question comes by the model's link to that parent and it has no other;
- some relation that points at the model has an `on_delete` outside `SKIP_COLLECTION`, so that its rows would have to be dealt with in turn;
- the model has a private field with an attribute `"bulk_related_objects"`, a generic relation.

The exception for a link to a parent is for a delete that arrives at a child from its parent's row: the source's comment says it avoids cascading back to the parent. `Collector.collect` asks the question of the collection it was given and of each related model, with the relation's field; `Collector.delete` asks it of the instance, when one instance is all there is.

The condition about receivers makes the queries of a delete depend on who is listening. With a receiver of `pre_delete` and one of `post_delete` connected for Manifest, the answer for Manifest is no, and a voyage's manifests are fetched whole and get both signals:

```text recording=models
Collector.can_fast_delete(the class Manifest, from_field=Manifest.voyage)  ->  False
SQL SELECT "office_manifest"."serial", "office_manifest"."voyage_id", "office_manifest"."crates", "office_manifest"."kilos_each", "office_manifest"."kilos", "office_manifest"."stamped", "office_manifest"."scan" FROM "office_manifest" WHERE "office_manifest"."voyage_id" IN (%s) with params (3,)
CASCADE(collector, Manifest.voyage, a QuerySet of Manifest, fetched, 2 rows, 'default')
  Collector.collect(a QuerySet of Manifest, fetched, 2 rows, source=Voyage, fail_on_restricted=False)
    Collector.can_fast_delete(a QuerySet of Manifest, fetched, 2 rows)  ->  False
    Collector.add(a QuerySet of Manifest, fetched, 2 rows)  ->  not already collected: [<Manifest: Manifest object (M-0003)>, <Manifest: Manifest object (M-0004)>]
...
signal pre_delete, sender Manifest, instance=<Manifest: Manifest object (M-0003)>
signal pre_delete, sender Manifest, instance=<Manifest: Manifest object (M-0004)>
DeleteQuery.delete_batch(['M-0004', 'M-0003'])  (Manifest)
  SQL DELETE FROM "office_manifest" WHERE "office_manifest"."serial" IN (%s, %s) with params ('M-0004', 'M-0003')
signal post_delete, sender Manifest, instance=<Manifest: Manifest object (M-0004)>
signal post_delete, sender Manifest, instance=<Manifest: Manifest object (M-0003)>
```

Left out are the line that made the queryset and the fast delete of the ports of call, for whose model nothing was connected. How a signal finds its receivers is in [Caching, files, mail, signals and tasks](../services.md).

`Collector.delete` sends neither signal for a model whose options have `Options.auto_created` set, as the through model that Django makes for a many-to-many field has (`django/db/models/deletion.py:Collector.delete`, `django/db/models/options.py:Options`). `can_fast_delete` makes no such exception (`django/db/models/deletion.py:Collector._has_signal_listeners`). A receiver connected for such a model costs the fetch and is not called for its rows.

## An `on_delete` left to the database

A database can cascade a delete without help: a foreign key's constraint may carry a clause such as `ON DELETE CASCADE`. `DB_CASCADE`, `DB_SET_NULL` and `DB_SET_DEFAULT` are the values of `on_delete` that ask for one, and the office's logbook uses the first:

```python
# harbour/office/models.py
class Logbook(models.Model):
    title = models.CharField(max_length=60)


class LogEntry(models.Model):
    book = models.ForeignKey(Logbook, on_delete=models.DB_CASCADE)
    line = models.CharField(max_length=200)
```

Each of the three is an instance of `DatabaseOnDelete`, made with the words of its clause, and the schema editor has the clause from its `DatabaseOnDelete.on_delete_sql` (`django/db/models/deletion.py:DatabaseOnDelete`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._create_on_delete_sql`). In two of the harbour's tables as SQLite's schema editor made them, a sailor's foreign key to its ship was declared with `CASCADE` and an entry's to its logbook with `DB_CASCADE`, and only the second constraint says anything about a delete:

```text recording=models
editor.create_model(Sailor)
  SQL CREATE TABLE "crew_sailor" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(60) NOT NULL, "ship_id" bigint NOT NULL REFERENCES "fleet_ship" ("id") DEFERRABLE INITIALLY DEFERRED, "signed_on" datetime NOT NULL)
...
editor.create_model(LogEntry)
  SQL CREATE TABLE "office_logentry" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "book_id" bigint NOT NULL REFERENCES "office_logbook" ("id") ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED, "line" varchar(200) NOT NULL)
```

The collector leaves a relation declared with one of the three alone, as it leaves one declared with `DO_NOTHING`: they are in `SKIP_COLLECTION` with it. A logbook with two entries is deleted with one statement, and the entries are gone:

```text recording=models
LogEntry.objects.count()  ->  2
...
      Collector.can_fast_delete(<Logbook: Logbook object (1)>)  ->  True
      mark_for_rollback_on_error
      DeleteQuery.delete_batch([1])  (Logbook)
        SQL DELETE FROM "office_logbook" WHERE "office_logbook"."id" IN (%s) with params (1,)
      -> (1, {'office.Logbook': 1})
...
LogEntry.objects.count()  ->  0
```

`Collector.collect`, whose lines are left out, added the logbook and followed no relation. Django knew nothing of the two entries: no row was fetched, no receiver of the delete signals for LogEntry would have been called, and the count returned is one.

> **Changed in 6.1.** `DB_CASCADE`, `DB_SET_NULL` and `DB_SET_DEFAULT` are new in 6.1.

A row that the database deletes is never collected, and nothing Django does for a collected row is done for it: no signal is sent, and no relation that points at it is followed. The model checks refuse a project in which the two kinds meet ([The model checks](checks.md)).

A collector made with `force_collection=True` marks nothing for a fast delete, and follows a relation declared with `DB_CASCADE` by calling `CASCADE`, which that value carries as its `DatabaseOnDelete.forced_collector`. Django's own source makes such collectors to find out what a delete would reach: the admin's `NestedObjects`, from which it draws its page of confirmation ([The admin](../admin.md)), and the command that removes stale content types (`django/contrib/admin/utils.py:NestedObjects`, `django/contrib/contenttypes/management/commands/remove_stale_contenttypes.py`).

## `Collector.delete`

`Collector.delete` begins by putting things in order (`django/db/models/deletion.py:Collector.delete`). The instances of each model are sorted by key. Then `Collector.sort` tries to arrange the models so that each comes after every model it depends on: it goes round them, taking each whose dependencies have all been taken, and if a round places none it gives up and leaves the order as it was (`django/db/models/deletion.py:Collector.sort`).

The dependencies are those the collector was told of while it collected: by `Collector.add`, for rows a cascade reached through a field that cannot be null; the other way round for a parent's row; and by `RESTRICT`. The source's comment says whom the order is for: databases that have no transactions, or cannot defer the checking of constraints to the end of one.

### One instance and nothing else

`Collector.delete` takes a short way where `Collector.data` holds one instance of one model and `Collector.can_fast_delete` accepts that instance: one `"DELETE"` by key and no signal, the test having just established that there is no receiver for one. The statement is sent inside `mark_for_rollback_on_error`, which opens no transaction; its docstring says it is there to avoid starting one where a single query is executed in autocommit mode (`django/db/transaction.py:mark_for_rollback_on_error`). A licence is such a row, since nothing points at a licence:

```text recording=models
  Collector.can_fast_delete([<Licence: Licence object (2)>])  ->  False
  Collector.add([<Licence: Licence object (2)>])  ->  not already collected: [<Licence: Licence object (2)>]
Collector.delete
  Collector.sort
  Collector.can_fast_delete(<Licence: Licence object (2)>)  ->  True
  mark_for_rollback_on_error
  DeleteQuery.delete_batch([2])  (Licence)
    SQL DELETE FROM "office_licence" WHERE "office_licence"."id" IN (%s) with params (2,)
  -> (1, {'office.Licence': 1})
```

Afterwards:

```text recording=models
licence.pk, licence._state.adding, Licence.objects.filter(port=leith).exists()  ->  (None, False, False)
```

The attribute under the attname of the key has been set to `None`, and nothing else on the instance is touched: its state still says that it is not being added ([An instance and its state](instances.md)).

### The general case

In every other case `Collector.delete` works inside a block of `atomic` made with `savepoint=False`, which begins a transaction when none is open and otherwise joins the one that is (`django/db/transaction.py:Atomic.__enter__`). Inside it, in this order:

1. `pre_delete` is sent for every instance in `data`, with the instance's class as the sender, unless the model is auto-created.
2. Each queryset in `Collector.fast_deletes` is given to `QuerySet._raw_delete`, which sends one `"DELETE"` with the queryset's condition and returns the number of rows (`django/db/models/query.py:QuerySet._raw_delete`).
3. The field updates are made. For each field and value, the querysets that were never fetched are joined into one and updated with `QuerySet.update`, and the rows that were fetched are updated by key with `UpdateQuery.update_batch`.
4. The models are taken in their sorted order. For each, the instances are deleted by key with `DeleteQuery.delete_batch`, highest key first, and then `post_delete` is sent for each of them, again unless the model is auto-created (`django/db/models/sql/subqueries.py:DeleteQuery.delete_batch`).

So every `pre_delete` is sent before any row is changed, and a `post_delete` is sent inside the transaction, while the rows of models later in the order are still there. This is that block for the Petrel, the ship [whose collecting is followed above](#a-ship-is-deleted): three fast deletes, one update, then the three models by key, Ship last.

```text recording=models
Collector.delete
  Collector.sort
  Atomic.__enter__  (savepoint=False)
    SQL BEGIN
  QuerySet._raw_delete  (a QuerySet of Voyage_calls, not yet fetched)
    SQL DELETE FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" IN (%s) with params (1,)
  QuerySet._raw_delete  (a QuerySet of Manifest, not yet fetched)
    SQL DELETE FROM "office_manifest" WHERE "office_manifest"."voyage_id" IN (%s) with params (1,)
  QuerySet._raw_delete  (a QuerySet of Licence, not yet fetched)
    SQL DELETE FROM "office_licence" WHERE "office_licence"."sailor_id" IN (%s, %s, %s, %s, %s) with params (1, 2, 4, 5, 7)
  mark_for_rollback_on_error
  SQL UPDATE "fleet_ship" SET "captain_id" = %s WHERE "fleet_ship"."captain_id" IN (%s, %s, %s, %s, %s) with params (None, 1, 2, 4, 5, 7)
  DeleteQuery.delete_batch([1])  (Voyage)
    SQL DELETE FROM "fleet_voyage" WHERE "fleet_voyage"."id" IN (%s) with params (1,)
  DeleteQuery.delete_batch([7, 5, 4, 2, 1])  (Sailor)
    SQL DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (%s, %s, %s, %s, %s) with params (7, 5, 4, 2, 1)
  DeleteQuery.delete_batch([1])  (Ship)
    SQL DELETE FROM "fleet_ship" WHERE "fleet_ship"."id" IN (%s) with params (1,)
  Atomic.__exit__
    BaseDatabaseWrapper.commit
  -> (13, {'fleet.Voyage_calls': 3, 'office.Manifest': 2, 'office.Licence': 1, 'fleet.Voyage': 1, 'crew.Sailor': 5, 'fleet.Ship': 1})
```

`Collector.sort` put Voyage and Sailor ahead of Ship. The update is a statement of `QuerySet.update`, which brings that method's own `mark_for_rollback_on_error` with it. No receiver was connected, so there is no line for a signal. The total of 13 is the rows the `"DELETE"` statements removed; what an `"UPDATE"` changes is not counted.

After the block, the attribute under the key's attname is set to `None` on every instance in `data`, and the method returns the pair that `Model.delete` returns. The counts are what the `"DELETE"` statements reported, added up by model, and on this path a model whose statements removed no row has no entry.

## A model with a parent, and `keep_parents=True`

An Officer is a row in each of two tables with one key ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)), and deleting one deletes both rows unless the delete is told otherwise. In `Collector.collect`, once the instances have been added, the parent's instance of each is read off the child through its link ([Reading and setting related objects](related-objects.md)), and the parents are handed to `collect` with three instructions (`django/db/models/deletion.py:Collector.collect`). It is not to follow relations: those that point at the parent are already in the child's own list, as the source's comment says. It is to record the dependency the other way round, since here the row being collected is the one pointed at and the child's row has to go first. And it is not to settle restricted rows.

With `keep_parents=True` the parents are not collected, and a relation that points at one of the model's parents is passed over, so the rows that point at the parent's row are left pointing at it. An Officer deleted so loses one row, the child's, with nothing followed:

```text recording=models
      Collector.add([<Officer: Finn>])  ->  not already collected: [<Officer: Finn>]
    Collector.delete
      Collector.sort
      Collector.can_fast_delete(<Officer: Finn>)  ->  False
      Atomic.__enter__  (savepoint=False)
        SQL BEGIN
      DeleteQuery.delete_batch([6])  (Officer)
        SQL DELETE FROM "crew_officer" WHERE "crew_officer"."sailor_ptr_id" IN (%s) with params (6,)
...
Officer.objects.filter(pk=6).exists(), Sailor.objects.filter(pk=6).exists()  ->  (False, True)
```

One instance was all the collector held, yet the short way was not taken: `Collector.can_fast_delete` says no to a model with a parent, and the single statement got a transaction.

## `QuerySet.delete`

`QuerySet.delete` uses the same collector, given a queryset where `Model.delete` gives a list of one instance (`django/db/models/query.py:QuerySet.delete`). The difference shows at the first step of `Collector.collect`, where a queryset, unlike a list, can be accepted for a fast delete. The berths of a port are accepted, and a queryset of sailors is not:

```text recording=models
  Collector.can_fast_delete(a QuerySet of Berth, not yet fetched)  ->  True
Collector.delete
  Collector.sort
  Atomic.__enter__  (savepoint=False)
    SQL BEGIN
  QuerySet._raw_delete  (a QuerySet of Berth, not yet fetched)
    SQL DELETE FROM "office_berth" WHERE "office_berth"."port_id" = %s with params (1,)
...
  Collector.can_fast_delete(a SailorQuerySet of Sailor, not yet fetched)  ->  False
  Collector.add(a SailorQuerySet of Sailor, not yet fetched)
    SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s with params ('Finn',)
    -> not already collected: [<Sailor: Finn>]
```

The berths went in one statement whose condition is the queryset's own, though still in a transaction. Rows of other models point at a sailor, so `Collector.add` fetched that queryset, whole rows as the caller's queryset asks for them, and the delete went on as it does for an instance. What `QuerySet.delete` does around the collector belongs to [QuerySets](../querysets.md).

## What a delete leaves alone

`Model.delete` runs for the instance it is called on. The rows a collector reaches are deleted by the collector's own statements, and no `delete` is called on them, a model's override included; what reaches them is the two signals, and those only the rows it holds as instances (`django/db/models/deletion.py:Collector.delete`).

A file is not deleted with its row: nothing in a delete touches a file field's storage ([File fields](files.md)).
