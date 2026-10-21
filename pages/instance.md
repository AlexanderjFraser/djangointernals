---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: state, fetching, saving, validation, deleting, files, child
---

# An instance and its row

An instance of a model stands for one row: it holds the row's values in its `__dict__` under the fields' attnames, with a state that says where it came from; it can fetch what it lacks when it is read, writes itself back table by table when it is saved, and is collected, ordinarily with what depends on it, before it is deleted.

A model class describes a table, and an instance has to stand for one of its rows across a program's life. It is made, ordinarily, in one of two ways, by a program that calls the class or by a query that fetched the row. It may hold only some of the row's values, as when the query was told to leave columns out, and has to fetch the rest when they are read. It is written back by `Model.save`, which has to decide whether the row exists without, ordinarily, asking; it is checked by a call of its own, which a model form makes and a save does not; and it is deleted together with whatever its `on_delete` rules say must go with it. Most of these are done partly by Django, in Python, and partly by the database, in SQL, at different moments: a rule the model states, a unique field or a foreign key, may be kept by Django before a statement is sent and by the database when it runs, and most of what surprises a reader of this chapter happens where the two meet.

The examples are harbour's, whose models [Models and fields](models.md) lists: a Ship with a home Port and perhaps a captain, a Voyage with its ports of call, and the office's Manifest of what a voyage carried. The recordings were made from a running Django, on SQLite. A line at the left says what was done; the lines set in under it are the calls it set going, nested as they were made, with only those the passage is about written down; `->` gives what a call returned; a name in parentheses after a call describes the object it was called on; a line beginning `signal` is a signal sent, with its sender, and one beginning `SQL` a statement as Django handed it to its cursor.

## A `__dict__` and a state

Calling a model class runs `Model.__init__`, which sets attributes under the attnames of the fields that have a column, from the arguments or, where a field is not generated, from its default, and binds a new `ModelState` as `Model._state` (`django/db/models/base.py:Model.__init__`, `django/db/models/base.py:ModelState`). That is all a new instance is:

```text recording=models
What the new Ship holds in its __dict__
    _state: a ModelState
    id: None
    name: 'Heron'
    tonnage: 300
    home_id: 1
    captain_id: None
    and its _state: adding=True, db='default', fields_cache={'home': <Port: Bergen>}
```

The values are under attnames, so a foreign key is there as the value of its column. The port itself, having been passed in, is kept in the state's cache of related objects. The state also records whether the instance is being added, which is true until it has been saved or was made from a row, and which database it belongs to. Everything else a new instance seems to have is its class's: the descriptors its fields left there, which act when a value is missing or, for some fields, a relation's or a file's among them, whenever one is read or assigned, and `_meta`. A row fetched by a query becomes an instance through the same `__init__`, called by `Model.from_db` with the row's values in the order of the model's concrete fields, which then marks the instance as not being added and records the database the row came from (`django/db/models/base.py:Model.from_db`) ([An instance and its state](instance/state.md)).

The figure sets the three parties side by side, the class that every instance of Ship shares, one instance, and its row, with the ways the chapter's mechanisms cross between the instance and the row beneath them.

```text figure=an-instance-and-its-row
the class Ship, shared by every instance     one instance: the new Ship, its __dict__  its row in "fleet_ship"
  _meta: the description                       under the attnames:                     none yet: the instance
  the descriptors its fields left there          id: None    name: 'Heron'              is being added
                                                 tonnage: 300    home_id: 1
                                                 captain_id: None
                                               _state, a ModelState:
                                                 adding: True    db: 'default'
                                                 fields_cache: {'home': <Port: Bergen>}

between the instance and its row:
  Model.from_db       a fetched row becomes an instance, through __init__              row -> instance
  a read of a value   not in __dict__: the class's descriptor may fetch it, or raise   SELECT
  Model.save          an UPDATE, or else an INSERT; what the insert hands back is set  UPDATE, INSERT
  Model.full_clean    a call of its own: may read, never writes                        SELECT
  Model.delete        a Collector finds what it is to delete, then deletes it all      SELECT, then DELETE
```

*A new instance holds only its values and its state; the descriptors and the description are its class's. Each line under the three is one way an instance and its row meet, with statements it may send.*

## A value the instance lacks

A query that fetched only some columns leaves the others out of the `__dict__` altogether, and that absence is the whole of what it means for a field to be **deferred**: reading the attribute reaches the descriptor on the class, which, ordinarily, finds nothing on the instance and has the value fetched (`django/db/models/query_utils.py:DeferredAttribute.__get__`). It does not decide how. It asks the instance's **fetch mode**, which the queryset that made the instance handed it: `FETCH_ONE` fetches the value for this instance alone, `FETCH_PEERS` for the instances the same run of the query made, and `FETCH_RAISE` raises instead of fetching (`django/db/models/fetch_modes.py`). The descriptor of a relation to one object asks the same mode for an object it has not got ([Deferred fields and the fetch modes](instance/fetching.md)).

## Saving is an update, or else an insert

`Model.save` does not ordinarily ask first whether the row exists; a model whose `Meta` sets `select_on_save`, and a table with nothing to write but its key, are the exceptions. For each table of the model, it decides from what it has in hand. If the primary key is set it tries an `"UPDATE"`, and takes a result that touched a row as success. If that touched nothing, or the key was not set, it inserts. A Ship made with a key that no row has shows both statements:

```text recording=models
Ship(id=40, name='Skua', tonnage=90, home=leith).save(): a primary key set by hand, and no such row
    Model.save()  (a Ship)
      Model._prepare_related_fields_for_save
      Model.save_base()
        signal pre_save, sender Ship, raw=False, update_fields=None
        mark_for_rollback_on_error
        Model._save_table(cls=Ship)
          Model._do_update(pk_val=40, values for [name, tonnage, home, captain])
            SQL UPDATE "fleet_ship" SET "name" = %s, "tonnage" = %s, "home_id" = %s, "captain_id" = %s WHERE "fleet_ship"."id" = %s with params ('Skua', 90, 2, None, 40)
            -> []
          Model._do_insert(fields=[id, name, tonnage, home, captain], returning_fields=[id])
            SQL INSERT INTO "fleet_ship" ("id", "name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s, %s) RETURNING "fleet_ship"."id" with params (40, 'Skua', 90, 2, None)
            -> [(40,)]
          Model._assign_returned_values((40,), [id])
          -> updated: False
        signal post_save, sender Ship, created=True, update_fields=None
```

The update matched no row, and the insert followed. `Model._do_insert` hands the instance to the base manager's `QuerySet._insert`, which builds an `InsertQuery` and has its compiler, a `SQLInsertCompiler`, write and run the statement (`django/db/models/base.py:Model._do_insert`, `django/db/models/query.py:QuerySet._insert`, `django/db/models/sql/compiler.py:SQLInsertCompiler`). The insert here asks for the key back, and `Model._assign_returned_values` sets what comes back on the instance under each field's attname (`django/db/models/base.py:Model._assign_returned_values`). A save sends its statements for a model with no parent inside `mark_for_rollback_on_error`, which does nothing outside an atomic block and inside one marks it for rollback if an exception passes through; for a model whose save can write several tables, it sends them inside one atomic block (`django/db/models/base.py:Model.save_base`, `django/db/transaction.py:mark_for_rollback_on_error`) ([Transactions: autocommit, `atomic` and savepoints](connections/atomic.md)).

The update is skipped when the key is not set, when the instance is being added and its key has a default (unless the save is forced either way, or is the raw save that loads a fixture), and for a child's table when its parent's row has just been inserted. The arguments `force_insert=True`, `force_update=True` and `"update_fields"` each cut the decision short. With `"update_fields"`, or with `force_update=True` for the model's own table, an update that matches no row raises instead of falling back to an insert. In a save that is not raw, each value written goes through its field's `Field.pre_save` on the way, which is where a date that sets itself on saving gets its value (`django/db/models/base.py:Model._save_table`, `django/db/models/fields/__init__.py:Field.pre_save`, `django/db/models/fields/__init__.py:DateField.pre_save`) ([Saving an instance](instance/saving.md)).

## Validation is a call of its own

A save does not validate. It refuses an instance that was given a related object with no primary key; anything else the instance holds is prepared by its field and sent: a value the field cannot prepare raises there, and one the table will not take is refused by the database. Validation is a separate call, `Model.full_clean`, which a `ModelForm` makes and `save` does not (`django/db/models/base.py:Model.full_clean`). It cleans the value of each field that has one to clean, which for a foreign key means asking the database whether the row it points at exists, calls `Model.clean`, asks the database whether a value that must be unique is already taken, and then tests the model's constraints against the instance, which for the two of Ship, when their fields passed their own cleaning, is a query each. Every question it asks the database is a read, made before the statement that might fail; the table's own constraints still decide when the row is written ([Validating an instance](instance/validation.md), [Constraints and indexes](models/constraints.md)).

## Deleting is collected first

`Model.delete` deletes nothing until it knows everything it has to delete; the only statements it sends before that are the selects that find the rows. It gives the instance to a `Collector`, which follows each foreign key and one-to-one field that points at the instance's model and does what that relation's `on_delete` says: it may collect the related rows too, refuse, or note a value the column is to be set to (`django/db/models/base.py:Model.delete`, `django/db/models/deletion.py:Collector.collect`). Only then does it delete. Where it can, it first puts the models in an order in which a row reached through a field that cannot be null is deleted before the row it points at (`django/db/models/deletion.py:Collector.delete`, `django/db/models/deletion.py:Collector.sort`). Two tables point at a voyage: the one Django made for its ports of call, and that of Manifest, a model of the office with a foreign key to Voyage.

```text recording=models
A Voyage is deleted, with the rows that point at it
    autumn.delete()
      Model.delete()  (a Voyage)
        Collector.collect([<Voyage: Voyage object (2)>])
          Collector.can_fast_delete([<Voyage: Voyage object (2)>])  ->  False
          Collector.add([<Voyage: Voyage object (2)>])  ->  not already collected: [<Voyage: Voyage object (2)>]
          Collector.can_fast_delete(the class Voyage_calls, from_field=Voyage_calls.voyage)  ->  True
          Collector.can_fast_delete(the class Manifest, from_field=Manifest.voyage)  ->  True
          Collector.related_objects(Voyage_calls, [Voyage_calls.voyage], [<Voyage: Voyage object (2)>])  ->  a QuerySet of Voyage_calls, not yet fetched
          Collector.related_objects(Manifest, [Manifest.voyage], [<Voyage: Voyage object (2)>])  ->  a QuerySet of Manifest, not yet fetched
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
        -> (2, {'fleet.Voyage_calls': 1, 'fleet.Voyage': 1})
```

The two tables that point at a voyage are emptied of its rows with one `"DELETE"` each and nothing fetched. The collector allows itself that when it has no reason to look at the rows: no receiver is connected for the model's delete signals, and deleting them calls for nothing further to be collected. Otherwise it fetches the rows, sends `pre_delete` and `post_delete` for each unless the model is one Django made itself, and deletes them by key (`django/db/models/deletion.py:Collector.collect`, `django/db/models/deletion.py:Collector.can_fast_delete`). The voyage's own row goes by its key, through a `DeleteQuery` and its compiler, and all of it inside one atomic block, which here began a transaction. Where the collector holds one instance and nothing beside it, and may delete that instance unseen, the one statement is sent inside `mark_for_rollback_on_error` instead (`django/db/models/deletion.py:Collector.delete`, `django/db/models/sql/subqueries.py:DeleteQuery.delete_batch`) ([Deleting: the `Collector`](instance/deleting.md)).

> **Changed in 6.1.** `on_delete` may also name an action for the database to take, `DB_CASCADE`, `DB_SET_NULL` or `DB_SET_DEFAULT`. The collector that `Model.delete` makes passes over such a relation, and the rows are dealt with by the foreign key's `ON DELETE` clause.

## A file, and a child in two rows

Two kinds of model keep an instance in more than one place. A `FileField` keeps its file in a storage (`django/db/models/fields/files.py:FileField`) and only the file's name in the row, so a save can write the file and the row through two parties with no transaction joining them ([File fields](instance/files.md)). And an instance of a model whose parent has a table, as an Officer is a Sailor, is one object kept in a row of each table: a query for its inherited fields joins the tables, and a save writes the parent's row first ([A child in two rows](instance/child.md)).

## The neighbours

The class an instance belongs to, its fields and their descriptors are [Models and fields](models.md)'s. The queryset that made an instance from a row, and the mode it handed it, are [QuerySets](querysets.md)'s; how a relation's descriptor finds the related object, from its cache, from the same row or from a second statement, is [Relations](relations.md)'s. The insert, the update and the delete are written by the compilers of [The SQL compiler](sql.md), and run on a connection inside its transactions ([Connections and transactions](connections.md)). A `ModelForm` validates the instance it saves ([Model forms: `ModelForm` and `fields_for_model`](forms/model-forms.md)), and the signals a save and a delete send are in [Signals: `Signal`, receivers and sending](services/signals.md).
