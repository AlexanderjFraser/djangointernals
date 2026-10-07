---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `bulk_create` and `bulk_update`

`QuerySet.bulk_create` inserts a list of instances in as few statements as the backend allows, and `QuerySet.bulk_update` writes chosen fields of a list of instances with one call of `QuerySet.update` to a batch. Neither calls `Model.save` for an instance and neither sends the signals of a save.

Saving is done an instance at a time. `Model.save` decides between an update and an insert, sends two signals, writes each table of a model that has parents, and reads back what the database decided ([Saving an instance](../models/saving.md)).

SQL can do better. One `"INSERT"` can carry many rows, and one `"UPDATE"` can give a column a different value in each of many rows, if the value is written as a `"CASE"` expression over the rows' keys. `bulk_create` builds the first and `bulk_update` the second. What they give up is what a save does for one instance: there is no choice between updating and inserting and no signal, and `bulk_create` writes no second table. And what shapes them is the backend, which differs from one database to the next: in how many parameters a statement may hold, in whether an insert can hand back the rows it made, in whether it can pass over or resolve a conflict with a row that is already there. Much of `bulk_create` is the handling of those differences.

The examples are the office's logbooks, in the shipping line that the chapter uses ([QuerySets](../querysets.md)). A logbook has a title, and an entry is one line of one logbook:

```python
# harbour/office/models.py
class Logbook(models.Model):
    title = models.CharField(max_length=60)


class LogEntry(models.Model):
    book = models.ForeignKey(Logbook, on_delete=models.DB_CASCADE)
    line = models.CharField(max_length=200)
```

Neither declares a primary key, so each has the automatic one, `"id"`, which the project's settings make a `BigAutoField`.

## One statement for many instances

`QuerySet.bulk_create`, given three entries for one logbook, which the first line here has as log, sends one statement. What follows was recorded from a running Django, on SQLite. Under a line of Python are the calls it set going, nested as they were made and only those the passage is about; `->` is what a call, or the line itself, returned, or the exception it raised; a line that begins `SQL` is a statement as Django handed it to its cursor; and in the calls of `bulk_create` a list of instances is written by its length and its class.

```text recording=querysets
lines = LogEntry.objects.bulk_create([LogEntry(book=log, line='Cast off'), LogEntry(book=log, line='Cleared the mole'), LogEntry(book=log, line='Full ahead')])
  QuerySet.bulk_create(objs=[3 of LogEntry])
    QuerySet._check_bulk_create_options(ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None)  ->  None
    QuerySet._prepare_for_bulk_create([3 of LogEntry])  ->  (0 with a primary key, 3 without)
    QuerySet._batched_insert(objs=[3 of LogEntry], fields=[LogEntry.book, LogEntry.line], batch_size=None)
      QuerySet._insert(objs=[3 of LogEntry], fields=[LogEntry.book, LogEntry.line], returning_fields=[LogEntry.id])
        SQL INSERT INTO "office_logentry" ("book_id", "line") VALUES (%s, %s), (%s, %s), (%s, %s) RETURNING "office_logentry"."id" with params (1, 'Cast off', 1, 'Cleared the mole', 1, 'Full ahead')
        -> [(1,), (2,), (3,)]
    -> [3 of LogEntry], with the primary keys [1, 2, 3]
[(entry.pk, entry._state.adding, entry._state.db) for entry in lines]  ->  [(1, False, 'default'), (2, False, 'default'), (3, False, 'default')]
```

One statement inserted three rows and returned three keys, and the method put each key on its instance. The calls under `QuerySet.bulk_create` are the outline of the method (`django/db/models/query.py:QuerySet.bulk_create`). The options about conflicts are checked. The instances are sorted by whether they have a primary key. Each group that has instances in it is handed to `QuerySet._batched_insert`, which cuts it into batches and calls `QuerySet._insert` for each. And what the statements return is set on the instances.

`_insert` makes an `InsertQuery` of the fields and the instances it is given, and runs it ([Creating, updating and deleting through a queryset](writing.md)). How the insert compiler writes several rows of values, a `"RETURNING"` clause or a clause about conflicts into one statement belongs to [From QuerySet to SQL](../sql.md).

The last line of the recording asks the three instances what they hold afterwards: each has its key, and a state that says it is no longer being added and names the database it was written to.

## The checks before anything is written

`QuerySet.bulk_create` begins with two refusals and an early return, in this order.

A batch size that is given and is not positive is refused with `ValueError`.

A model that spans tables is refused, with `ValueError` too. The long comment at the head of the method gives the reason: a bulk insert does not get the primary keys back, unless the backend can return rows from one, so the rows of a child's table, which have to refer to them, cannot be inserted. The test goes through `Options.all_parents`, and refuses if any ancestor's `Options.concrete_model` is not the model's own; a proxy of a model that has no parent with a table passes it (`django/db/models/options.py:Options.all_parents`) ([Inheritance: abstract bases, parents with tables and proxies](../models/inheritance.md)).

Then a list with nothing in it is returned as it is.

Officer is a child of Sailor with a table of its own, and Veteran is a proxy of Sailor:

```text recording=querysets
Officer.objects.bulk_create([])  ->  raises ValueError: Can't bulk create a multi-table inherited model
Veteran.objects.bulk_create([])  ->  []
Logbook.objects.bulk_create([Logbook(title='x')], batch_size=0)  ->  raises ValueError: Batch size must be a positive integer.
```

The refusal of the model comes before the test for an empty list, so a call with nothing to insert is refused all the same.

## Conflicts: `OnConflict`, and the features that decide

Two arguments of `QuerySet.bulk_create` ask the database to do something other than fail when a new row collides with one that is there. `ignore_conflicts=True` asks it to keep the old row and drop the new. `update_conflicts=True` asks it to update the old row from the new, in the fields that `"update_fields"` names, where the collision is on the fields that `"unique_fields"` names, the conflict's **target**. Not every database can do either, and the method settles what is possible before it writes anything.

First the two lists of names are turned into fields with `Options.get_field` (`django/db/models/options.py:Options.get_field`). In `"unique_fields"` the name `"pk"` stands for the primary key's field; a comment notes that the key is allowed there. Then `QuerySet._check_bulk_create_options` reads the features of the queryset's database, and either raises or returns what the insert is to do about a conflict: `OnConflict.IGNORE` or `OnConflict.UPDATE`, the two members of an enumeration, or `None` (`django/db/models/query.py:QuerySet._check_bulk_create_options`, `django/db/models/constants.py:OnConflict`).

| what is asked for | what must hold | the feature read | refused with |
|---|---|---|---|
| `ignore_conflicts=True` and `update_conflicts=True` together | nothing allows it | none | `ValueError` |
| `ignore_conflicts=True` | the backend can pass over a conflict | `BaseDatabaseFeatures.supports_ignore_conflicts` | `NotSupportedError` |
| `update_conflicts=True` | the backend can update on a conflict | `BaseDatabaseFeatures.supports_update_conflicts` | `NotSupportedError` |
| `update_conflicts=True` | `"update_fields"` was given | none | `ValueError` |
| `update_conflicts=True` with `"unique_fields"` | the backend takes a target for the conflict | `BaseDatabaseFeatures.supports_update_conflicts_with_target` | `NotSupportedError` |
| `update_conflicts=True` without `"unique_fields"` | the backend takes no target | the same feature, which has to be false | `ValueError` |
| `update_conflicts=True`: the fields of `"update_fields"` | each is concrete, and none is part of the primary key | none | `ValueError` |
| `update_conflicts=True`: the fields of `"unique_fields"`, where given | each is concrete | none | `ValueError` |

*The checks of `QuerySet._check_bulk_create_options`, in the order it makes them; the first that fails ends the call. With `ignore_conflicts=True` only the first two are made, with neither option only the first, and in both the two lists of fields are not looked at.*

`BaseDatabaseFeatures` starts with the first of the three features true and the other two false (`django/db/backends/base/features.py:BaseDatabaseFeatures`); which backend changes which is in [Database backends](../backends.md). SQLite's has all three, as the last line here shows, with the feature that decides whether rows are asked back:

```text recording=querysets
Logbook.objects.bulk_create([Logbook(title='x')], update_conflicts=True, update_fields=['title'])  ->  raises ValueError: Unique fields that can trigger the upsert must be provided.
...
connection.features.supports_ignore_conflicts, connection.features.supports_update_conflicts, connection.features.supports_update_conflicts_with_target, connection.features.can_return_rows_from_bulk_insert  ->  (True, True, True, True)
```

The refusal in the first line is the backend's: SQLite's takes a target, so a call that wants conflicts updated has to say on which fields.

### Which database the features are read from

`QuerySet._check_bulk_create_options` finds the features by reading `QuerySet.db`, and `bulk_create` calls it before it sets `QuerySet._for_write`. So on a queryset that has no alias of its own and has not been marked for writing, the question the router is asked at that moment is the one for a read ([Clones: how a queryset is built](chaining.md)). For this recording a router was installed that writes down each question it is asked and answers `None` to all of them:

```text recording=querysets
len(Logbook.objects.bulk_create([Logbook(title='Spare log')]))  ->  1
  the router is asked db_for_read(Logbook)
  the router is asked db_for_write(Logbook)
  the router is asked db_for_write(Logbook)
  SQL INSERT INTO "office_logbook" ("title") VALUES (%s) RETURNING "office_logbook"."id" with params ('Spare log',)
  the router is asked db_for_write(Logbook)
  the router is asked db_for_write(Logbook)
```

The first question asks for a database to read from. The other four, made after the mark is set, ask for one to write to: `QuerySet.db` asks the router afresh each time it is read (`django/db/models/query.py:QuerySet.db`).

## Two groups: the instances with a key and those without

With the options settled, `QuerySet.bulk_create` sets `QuerySet._for_write` and makes its list of fields: the model's concrete fields, less the generated ones, whose values the database works out (`django/db/models/options.py:Options.concrete_fields`). It makes a list of what it was given, so an iterator is used up at this point. Then `QuerySet._prepare_for_bulk_create` goes through the instances once (`django/db/models/query.py:QuerySet._prepare_for_bulk_create`).

```text figure=instances-to-statements
QuerySet.bulk_create: from a list of instances to statements.

the instances, in the caller's order
  QuerySet._prepare_for_bulk_create asks of each: has it a primary key?

  with a key (the caller's, or one the key's field supplied)
      fields: every concrete field that is not generated
      QuerySet._batched_insert:  batch | batch | ...     each batch is one QuerySet._insert

  without a key (None, or a default the database is to supply)
      fields: the same, less any AutoField
      QuerySet._batched_insert:  batch | batch | ...     each batch is one QuerySet._insert

The instances with a key are inserted first.
The size of a batch is the caller's batch_size, or the backend's limit where that is smaller or none was given (BaseDatabaseOperations.bulk_batch_size).
A block of atomic, without a savepoint, is opened around both groups where both have instances,
and around the batches of one group where it has more than one.
```

*How `QuerySet.bulk_create` divides its instances: first by whether they have a primary key, each group having its own list of fields, and then into batches, each of which is one call of `QuerySet._insert`.*

For each instance it first calls `Model._prepare_related_fields_for_save`, the check that a save makes too: an instance holding a related object that has no key yet is refused ([Saving an instance](../models/saving.md)).

```text recording=querysets
LogEntry.objects.bulk_create([LogEntry(book=Logbook(title='unsaved'), line='x')])  ->  raises ValueError: bulk_create() prohibited to prevent data loss due to unsaved related object 'book'.
```

Then it puts the instance into one of two lists, by its primary key:

- A key that is a `DatabaseDefault`, the placeholder an instance holds for a field whose default the database supplies, puts it among those without a key (`django/db/models/expressions.py:DatabaseDefault`).
- A key that is set, by the test of `Model._is_pk_set`, puts it among those with one.
- Otherwise the key's field is asked for a key, with `Field.get_pk_value_on_save`, and the instance is given the answer. If that set the key it goes among those with one, and if not, among those without (`django/db/models/fields/__init__.py:Field.get_pk_value_on_save`).

The two lists are inserted separately, the instances with a key first. For those without, every field that is an `AutoField` is taken out of the list of fields, so where the key is an automatic one it is not among the fields the insert is given, and the database assigns the key; a `BigAutoField` counts as an `AutoField` for that test, by the metaclass `AutoFieldMeta` (`django/db/models/fields/__init__.py:AutoFieldMeta`). In this recording the check of the options, which returned `None` as before, is left out:

```text recording=querysets
mixed = Logbook.objects.bulk_create([Logbook(pk=40, title='Rough log'), Logbook(title='Fair log')])
  QuerySet.bulk_create(objs=[2 of Logbook])
    QuerySet._prepare_for_bulk_create([2 of Logbook])  ->  (1 with a primary key, 1 without)
    Atomic.__enter__  (an Atomic made with savepoint=False)
      SQL BEGIN
    QuerySet._batched_insert(objs=[1 of Logbook], fields=[Logbook.id, Logbook.title], batch_size=None)
      QuerySet._insert(objs=[1 of Logbook], fields=[Logbook.id, Logbook.title], returning_fields=[Logbook.id])
        SQL INSERT INTO "office_logbook" ("id", "title") VALUES (%s, %s) RETURNING "office_logbook"."id" with params (40, 'Rough log')
        -> [(40,)]
    QuerySet._batched_insert(objs=[1 of Logbook], fields=[Logbook.title], batch_size=None)
      QuerySet._insert(objs=[1 of Logbook], fields=[Logbook.title], returning_fields=[Logbook.id])
        SQL INSERT INTO "office_logbook" ("title") VALUES (%s) RETURNING "office_logbook"."id" with params ('Fair log',)
        -> [(41,)]
    Atomic.__exit__
      BaseDatabaseWrapper.commit
    -> [2 of Logbook], with the primary keys [40, 41]
[(book.pk, book.title) for book in mixed]  ->  [(40, 'Rough log'), (41, 'Fair log')]
```

One logbook was given the key 40 and the other none. The first statement has an `"id"` among its columns and the second has not; both asked for the key back, and the instances came out with 40 and 41. Around the two inserts there is a transaction: `bulk_create` opens a block of `atomic` when both lists have instances in them, and only then. The block is made with `savepoint=False`, so inside a transaction already open it would make no savepoint (`django/db/transaction.py:Atomic.__enter__`) ([Database backends](../backends.md)).

Before either insert, and inside the block where there is one, comes `QuerySet._handle_order_with_respect_to`, which has something to do only for a model that has an `Options.order_with_respect_to`. Where a save asks the database for an instance's next position with a query of its own, this method asks once for all the instances, and numbers those that have no position (`django/db/models/query.py:QuerySet._handle_order_with_respect_to`).

## Batches: `_batched_insert`

`QuerySet._batched_insert` is given one of the two lists, the fields, and the caller's batch size, which may be `None` (`django/db/models/query.py:QuerySet._batched_insert`). It asks the backend how many instances one statement can take, with `BaseDatabaseOperations.bulk_batch_size`, and uses the smaller of that and the caller's number, or the backend's alone where the caller gave none; an answer below one is taken as one. So the caller's batch size is a ceiling that the backend can lower and cannot raise.

In the base class the backend's answer is the number of instances, which is no limit at all, unless the backend's features give a `BaseDatabaseFeatures.max_query_params` and there is a field in the list. Then it is that number divided by the number of columns and rounded down, a composite primary key counting as its parts (`django/db/backends/base/operations.py:BaseDatabaseOperations.bulk_batch_size`). SQLite's backend reads its limit from the connection (`django/db/backends/sqlite3/features.py:DatabaseFeatures.max_query_params`).

The list is sliced into batches of that size and `QuerySet._insert` is called for each. Where there is more than one batch the calls are made inside a block of `atomic` without a savepoint, which makes one transaction of them; a single batch gets no block. Here five entries are given with `batch_size=2`, and the check of the options and the sorting of the instances are left out:

```text recording=querysets
LogEntry.objects.bulk_create([LogEntry(book=log, line=f'Sounding {n}') for n in range(1, 6)], batch_size=2)
  QuerySet.bulk_create(objs=[5 of LogEntry], batch_size=2)
    QuerySet._batched_insert(objs=[5 of LogEntry], fields=[LogEntry.book, LogEntry.line], batch_size=2)
      Atomic.__enter__  (an Atomic made with savepoint=False)
        SQL BEGIN
      QuerySet._insert(objs=[2 of LogEntry], fields=[LogEntry.book, LogEntry.line], returning_fields=[LogEntry.id])
        SQL INSERT INTO "office_logentry" ("book_id", "line") VALUES (%s, %s), (%s, %s) RETURNING "office_logentry"."id" with params (1, 'Sounding 1', 1, 'Sounding 2')
        -> [(4,), (5,)]
      QuerySet._insert(objs=[2 of LogEntry], fields=[LogEntry.book, LogEntry.line], returning_fields=[LogEntry.id])
        SQL INSERT INTO "office_logentry" ("book_id", "line") VALUES (%s, %s), (%s, %s) RETURNING "office_logentry"."id" with params (1, 'Sounding 3', 1, 'Sounding 4')
        -> [(6,), (7,)]
      QuerySet._insert(objs=[1 of LogEntry], fields=[LogEntry.book, LogEntry.line], returning_fields=[LogEntry.id])
        SQL INSERT INTO "office_logentry" ("book_id", "line") VALUES (%s, %s) RETURNING "office_logentry"."id" with params (1, 'Sounding 5')
        -> [(8,)]
      Atomic.__exit__
        BaseDatabaseWrapper.commit
    -> [5 of LogEntry], with the primary keys [4, 5, 6, 7, 8]
```

Five entries in batches of two are three statements in one transaction, and the keys they return are gathered into one list, in the order of the instances. Left to itself the method would have sent one statement. For the next recording SQLite's limit was lowered to 10 parameters for the connection, and twelve entries were given with no batch size. The three statements and what they returned are left out:

```text recording=querysets
connection.features.max_query_params  ->  10
...
    QuerySet._batched_insert(objs=[12 of LogEntry], fields=[LogEntry.book, LogEntry.line], batch_size=None)
      BaseDatabaseOperations.bulk_batch_size(fields=[LogEntry.book, LogEntry.line], objs=[12 of LogEntry])  ->  5
      Atomic.__enter__  (an Atomic made with savepoint=False)
        SQL BEGIN
      QuerySet._insert(objs=[5 of LogEntry], fields=[LogEntry.book, LogEntry.line], returning_fields=[LogEntry.id])
      QuerySet._insert(objs=[5 of LogEntry], fields=[LogEntry.book, LogEntry.line], returning_fields=[LogEntry.id])
      QuerySet._insert(objs=[2 of LogEntry], fields=[LogEntry.book, LogEntry.line], returning_fields=[LogEntry.id])
      Atomic.__exit__
        BaseDatabaseWrapper.commit
```

Two columns to a row and ten parameters to a statement make five rows to a batch.

## What comes back, and what is set on the instances

`QuerySet._batched_insert` also decides whether the statements are asked for rows. It passes `Options.db_returning_fields` to `QuerySet._insert` as the fields to return when two things hold: the backend's `BaseDatabaseFeatures.can_return_rows_from_bulk_insert` is true, and conflicts are not being ignored (`django/db/models/options.py:Options.db_returning_fields`). Otherwise it passes `None`, and the statements return nothing.

`db_returning_fields` is the fields of the model whose values the database has a hand in: an automatic key, a generated field, and a field with a database default. Back in `QuerySet.bulk_create`, the rows that came back are matched to the instances in order, and each value is set on its instance under the field's **attname**, the name of the attribute that holds the field's value on an instance, as `"book_id"` is for an entry's `"book"`. The office's manifests have all three kinds of field but the first:

```python
# harbour/office/models.py
class Manifest(models.Model):
    serial = models.CharField(max_length=8, primary_key=True, default=serials.next_serial)
    voyage = models.ForeignKey("fleet.Voyage", on_delete=models.CASCADE)
    crates = models.PositiveIntegerField()
    kilos_each = models.PositiveIntegerField()
    kilos = models.GeneratedField(expression=F("crates") * F("kilos_each"), output_field=models.PositiveIntegerField(), db_persist=True)
    stamped = models.BooleanField(db_default=False)
    scan = models.FileField(upload_to="manifests/", blank=True)
```

Two manifests are made at once, and the check of the options is left out of the quote:

```text recording=querysets
cargo = Manifest.objects.bulk_create([Manifest(voyage=spring, crates=40, kilos_each=25), Manifest(voyage=spring, crates=12, kilos_each=80, stamped=True)])
  QuerySet.bulk_create(objs=[2 of Manifest])
    QuerySet._prepare_for_bulk_create([2 of Manifest])  ->  (2 with a primary key, 0 without)
    QuerySet._batched_insert(objs=[2 of Manifest], fields=[Manifest.serial, Manifest.voyage, Manifest.crates, Manifest.kilos_each, Manifest.stamped, Manifest.scan], batch_size=None)
      QuerySet._insert(objs=[2 of Manifest], fields=[Manifest.serial, Manifest.voyage, Manifest.crates, Manifest.kilos_each, Manifest.stamped, Manifest.scan], returning_fields=[Manifest.kilos, Manifest.stamped])
        SQL INSERT INTO "office_manifest" ("serial", "voyage_id", "crates", "kilos_each", "stamped", "scan") VALUES (%s, %s, %s, %s, %s, %s), (%s, %s, %s, %s, %s, %s) RETURNING "office_manifest"."kilos", "office_manifest"."stamped" with params ('M-0001', 1, 40, 25, False, '', 'M-0002', 1, 12, 80, True, '')
        -> [[1000, False], [960, True]]
    -> [2 of Manifest], with the primary keys ['M-0001', 'M-0002']
[(m.serial, m.kilos, m.stamped) for m in cargo]  ->  [('M-0001', 1000, False), ('M-0002', 960, True)]
```

Both manifests had a key before the insert, from the function that is the default of `"serial"`, so both were in the first list. The list of fields has no `"kilos"`, which is generated, and the fields to return are that one and `"stamped"`. Each instance was given what came back, and the first of them, which was made with no value for `"stamped"`, now holds `False`. That `False` also stands among the parameters of the statement, which is SQLite's doing: it has no keyword for a default inside a row of values, so the default is written out there ([From QuerySet to SQL](../sql.md)).

Last, the state of each instance is brought up to date: `ModelState.adding` is set to false and `ModelState.db` to the queryset's database (`django/db/models/base.py:ModelState`). For the instances that had a key this is done for every one of them. For those that had none it is done inside the loop that matches returned rows to instances, and so only for an instance that got a row back. The queryset's fetch mode is not among what is set, as it is on the instance that `QuerySet.create` makes ([Deferred fields and fetch modes in a queryset](deferred.md)).

### A conflict ignored, and a conflict resolved

What `QuerySet._check_bulk_create_options` returned travels with the two lists of fields from `bulk_create` through `_batched_insert` and `_insert` to the `InsertQuery`, and the compiler asks the backend how to write it. The first and the last of the three recordings below follow the one above in which the logbooks 40 and 41 were made, and both collide with them. The sorting of the instances, all of which had keys, is left out of those two.

```text recording=querysets
again = Logbook.objects.bulk_create([Logbook(pk=40, title='Rough log, again'), Logbook(pk=41, title='Deck log')], ignore_conflicts=True)
  QuerySet.bulk_create(objs=[2 of Logbook], ignore_conflicts=True)
    QuerySet._check_bulk_create_options(ignore_conflicts=True, update_conflicts=False, update_fields=None, unique_fields=None)  ->  OnConflict.IGNORE
    QuerySet._batched_insert(objs=[2 of Logbook], fields=[Logbook.id, Logbook.title], batch_size=None, on_conflict=OnConflict.IGNORE)
      QuerySet._insert(objs=[2 of Logbook], fields=[Logbook.id, Logbook.title], returning_fields=None, on_conflict=OnConflict.IGNORE)
        SQL INSERT OR IGNORE INTO "office_logbook" ("id", "title") VALUES (%s, %s), (%s, %s) with params (40, 'Rough log, again', 41, 'Deck log')
        -> []
    -> [2 of Logbook], with the primary keys [40, 41]
[(book.pk, book._state.adding) for book in again], list(Logbook.objects.filter(pk__in=[40, 41]).values_list('pk', 'title'))  ->  ([(40, False), (41, False)], [(40, 'Rough log'), (41, 'Fair log')])
  SQL SELECT "office_logbook"."id" AS "pk", "office_logbook"."title" AS "title" FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s) with params (40, 41)
```

`INSERT OR IGNORE` is how SQLite writes it. Nothing was asked back, and the statement returned nothing. The last line of Python shows the trap in that: the table has the two titles it had before, not the two the instances were made with, and both instances are marked as no longer being added.

The next logbook was given no key. The statement is sent, nothing comes back, and the key and the state of the instance are left as they were: for this logbook no key, a state that still says it is being added, and no database.

```text recording=querysets
[(book.pk, book._state.adding, book._state.db) for book in Logbook.objects.bulk_create([Logbook(title='Unkeyed log')], ignore_conflicts=True)]  ->  [(None, True, None)]
  SQL INSERT OR IGNORE INTO "office_logbook" ("title") VALUES (%s) with params ('Unkeyed log',)
```

Where conflicts are to be updated, rows are asked back again. The statement that the last line sent is left out:

```text recording=querysets
Logbook.objects.bulk_create([Logbook(pk=40, title='Rough log, fair copy')], update_conflicts=True, update_fields=['title'], unique_fields=['pk'])
  QuerySet.bulk_create(objs=[1 of Logbook], update_conflicts=True, update_fields=['title'], unique_fields=['pk'])
    QuerySet._check_bulk_create_options(ignore_conflicts=False, update_conflicts=True, update_fields=[Logbook.title], unique_fields=[Logbook.id])  ->  OnConflict.UPDATE
    QuerySet._batched_insert(objs=[1 of Logbook], fields=[Logbook.id, Logbook.title], batch_size=None, on_conflict=OnConflict.UPDATE, update_fields=[Logbook.title], unique_fields=[Logbook.id])
      QuerySet._insert(objs=[1 of Logbook], fields=[Logbook.id, Logbook.title], returning_fields=[Logbook.id], on_conflict=OnConflict.UPDATE, update_fields=[Logbook.title], unique_fields=[Logbook.id])
        SQL INSERT INTO "office_logbook" ("id", "title") VALUES (%s, %s) ON CONFLICT("id") DO UPDATE SET "title" = EXCLUDED."title" RETURNING "office_logbook"."id" with params (40, 'Rough log, fair copy')
        -> [(40,)]
    -> [1 of Logbook], with the primary keys [40]
Logbook.objects.get(pk=40).title  ->  'Rough log, fair copy'
```

`"unique_fields"` was given as `"pk"` and reached the check as the field `"id"`. The statement names the target of the conflict and the column to update from the new row, and it asks for the key back, as an insert with no word about conflicts does.

## What `bulk_create` leaves undone

The docstring of `QuerySet.bulk_create` lists what the method does not do. It does not call `Model.save` on the instances, it sends no `pre_save` or `post_save` signal, and it does not set the primary key where that is an automatic one, unless the backend can return rows from a bulk insert.

The first two can be read off the path. From `bulk_create` to the statement the calls are `QuerySet._batched_insert`, `QuerySet._insert` and the insert compiler, and the two signals are sent by `Model.save_base` and by nothing else (`django/db/models/base.py:Model.save_base`). A `save` that a model overrides, and whatever it does, is passed by. One thing a save does for a field is done all the same, because the insert compiler is what does it: it calls each field's `pre_save` for each instance, so a date with `auto_now_add=True` is filled in (`django/db/models/sql/compiler.py:SQLInsertCompiler.pre_save_val`).

The third reaches further than the key, as the logbook without a key showed: where no rows are asked back, on a backend that cannot return them from a bulk insert or with `ignore_conflicts=True`, the state of such an instance is left as it was too.

## `bulk_update`

`QuerySet.bulk_update` is given instances that have rows, and the names of the fields to write from them. It has no statement of its own to build. It builds expressions, and hands them to `QuerySet.update` (`django/db/models/query.py:QuerySet.bulk_update`). Here ada and bram are two Sailors made earlier with `QuerySet.create`, and a new name has just been set on each:

```text recording=querysets
bulk_update: one UPDATE whose value for each column is a CASE over the primary keys
    ada.name, bram.name = 'Ada L.', 'Bram S.'
    Sailor.objects.bulk_update([ada, bram], ['name'])
      QuerySet.bulk_update(objs=[<Sailor: Ada L.>, <Sailor: Bram S.>], fields=['name'])
        Atomic.__enter__  (an Atomic made with savepoint=False)
          SQL BEGIN
        QuerySet.filter(pk__in=[1, 2])
        QuerySet.update(name=a Case)
          mark_for_rollback_on_error  (a context manager, entered here)
          SQL UPDATE "crew_sailor" SET "name" = CASE WHEN ("crew_sailor"."id" = %s) THEN %s WHEN ("crew_sailor"."id" = %s) THEN %s ELSE NULL END WHERE "crew_sailor"."id" IN (%s, %s) with params (1, 'Ada L.', 2, 'Bram S.', 1, 2)
          -> 2
        Atomic.__exit__
          BaseDatabaseWrapper.commit
        -> 2
```

For each field it was given, the method makes a `Case` with a `When` for each instance: when the primary key is this instance's, the value is this instance's (`django/db/models/expressions.py:Case`, `django/db/models/expressions.py:When`). A plain value is wrapped in a `Value` with the field as its output field (`django/db/models/expressions.py:Value`); a value that is already an expression, which the method knows by its having an attribute `"resolve_expression"`, is left as it is. The expressions go into a dictionary by attname, and the dictionary becomes the keyword arguments of an `update`, on a queryset filtered to the keys of the same instances.

Where the backend's `BaseDatabaseFeatures.requires_casted_case_in_updates` is true, each `Case` is wrapped in a `Cast` to the field's type as well. The comment at the feature says what it stands for: a backend that needs the result of a `"CASE"` expression in an update cast, for the expression to have the right type (`django/db/backends/base/features.py:BaseDatabaseFeatures`). SQLite's is not such a backend, and the recorded `"CASE"` stands bare.

So the statement is `update`'s, with all that follows from that: it runs inside `mark_for_rollback_on_error`, which, where an exception passes through it inside a block of `atomic`, marks the connection as needing a rollback ([Creating, updating and deleting through a queryset](writing.md)). The queryset it is called on is a clone of the one `bulk_update` was called on, pinned with `QuerySet.using` to the database for writing. Conditions that were on the queryset are still on the clone, and an instance whose row they leave out is not updated.

The method returns the sum of what the updates returned, each of which is the count of rows its statement matched. The documentation notes that this may be fewer than the instances given, and names two causes: the same instance twice in a batch, and a row that is no longer there (`docs/ref/models/querysets.txt`).

### The batches, and the arithmetic of their size

`QuerySet.bulk_update` takes the caller's batch size capped by the backend's, or the backend's where the caller gave none, and the list of fields it gives to `BaseDatabaseOperations.bulk_batch_size` is the primary key twice and then each field to be written (`django/db/backends/base/operations.py:BaseDatabaseOperations.bulk_batch_size`). A comment gives the count behind the key: it is used twice in the statement, once in the filter and once in the `"WHEN"` (`django/db/models/query.py:QuerySet.bulk_update`). So for a key of one column the method reckons a batch of n instances and f fields at n(f + 2) parameters.

For a key of one column, n different instances and values that are neither `None` nor expressions, the statement Django writes has more than that where there is more than one field, since each field's `"CASE"` names every key again: a batch of f fields carries n(2f + 1) parameters. The two counts agree for one field, as in the statement recorded above: six parameters, three to a sailor. These two calls were made with SQLite's limit lowered to 10 parameters for the connection:

```text recording=querysets
Sailor.objects.bulk_update([ada, bram], ['name'])  ->  2
  SQL BEGIN
  SQL UPDATE "crew_sailor" SET "name" = CASE WHEN ("crew_sailor"."id" = %s) THEN %s WHEN ("crew_sailor"."id" = %s) THEN %s ELSE NULL END WHERE "crew_sailor"."id" IN (%s, %s) with params (1, 'Ada', 2, 'Bram', 1, 2)
Sailor.objects.bulk_update([ada, bram], ['name', 'ship', 'signed_on'])  ->  raises OperationalError: too many SQL variables
  SQL BEGIN
  SQL UPDATE "crew_sailor" SET "name" = CASE WHEN ("crew_sailor"."id" = %s) THEN %s WHEN ("crew_sailor"."id" = %s) THEN %s ELSE NULL END, "ship_id" = CASE WHEN ("crew_sailor"."id" = %s) THEN %s WHEN ("crew_sailor"."id" = %s) THEN %s ELSE NULL END, "signed_on" = CASE WHEN ("crew_sailor"."id" = %s) THEN %s WHEN ("crew_sailor"."id" = %s) THEN %s ELSE NULL END WHERE "crew_sailor"."id" IN (%s, %s) with params (1, 'Ada', 2, 'Bram', 1, 1, 2, 1, 1, '2026-04-10 09:00:00', 2, '2026-04-10 09:00:00', 1, 2)
```

With one field the size reckoned is three instances to a batch, and the two sailors went in one statement of six parameters. With three fields it is two, and the one statement for the two sailors has fourteen parameters where ten were reckoned: SQLite refused it. Which backends give a limit, and what each counts against it, is in [Database backends](../backends.md).

The expressions for every batch are built before the first statement is sent. Then, inside a block of `atomic` without a savepoint, which is opened even for a single batch, there is one `update` for each:

```text recording=querysets
Sailor.objects.bulk_update([ada, bram], ['name'], batch_size=1)
  QuerySet.bulk_update(objs=[<Sailor: Ada>, <Sailor: Bram>], fields=['name'], batch_size=1)
    Atomic.__enter__  (an Atomic made with savepoint=False)
      SQL BEGIN
    QuerySet.filter(pk__in=[1])
    QuerySet.update(name=a Case)
      mark_for_rollback_on_error  (a context manager, entered here)
      SQL UPDATE "crew_sailor" SET "name" = CASE WHEN ("crew_sailor"."id" = %s) THEN %s ELSE NULL END WHERE "crew_sailor"."id" IN (%s) with params (1, 'Ada', 1)
      -> 1
    QuerySet.filter(pk__in=[2])
    QuerySet.update(name=a Case)
      mark_for_rollback_on_error  (a context manager, entered here)
      SQL UPDATE "crew_sailor" SET "name" = CASE WHEN ("crew_sailor"."id" = %s) THEN %s ELSE NULL END WHERE "crew_sailor"."id" IN (%s) with params (2, 'Bram', 2)
      -> 1
    Atomic.__exit__
      BaseDatabaseWrapper.commit
    -> 2
```

### What `bulk_update` refuses

`QuerySet.bulk_update` makes its checks first, in this order: a batch size that is not positive; no field names; an instance whose primary key is not set; a field that is not concrete; and a field that is part of the primary key, the model's own or a parent's. Each is a `ValueError`, and a name that is no field at all is `Options.get_field`'s `FieldDoesNotExist` (`django/db/models/options.py:Options.get_field`). Only after them is an empty list answered with 0, and only then is `Model._prepare_related_fields_for_save` called for each instance, here for the fields being written and no others.

### A model with a parent

`QuerySet.bulk_update` does not refuse a model that spans tables, as `QuerySet.bulk_create` does. Its check on primary keys takes in the keys of every parent, and after that a parent's field is a name like any other to it. The statement that fetched the Officer is left out here:

```text recording=querysets
Officer.objects.bulk_update([Officer.objects.get(pk=3)], ['name'])  ->  1
  SQL BEGIN
  SQL SELECT "crew_officer"."sailor_ptr_id" FROM "crew_officer" WHERE "crew_officer"."sailor_ptr_id" IN (%s) with params (3,)
  SQL UPDATE "crew_sailor" SET "name" = CASE WHEN "crew_sailor"."id" = %s THEN %s ELSE NULL END WHERE "crew_sailor"."id" IN (%s) with params (3, 'Cora', 3)
```

`"name"` is a field of Sailor, Officer's parent, and what became of it is `QuerySet.update`'s doing ([Creating, updating and deleting through a queryset](writing.md)): the update compiler selects the keys of the rows the queryset matches, which is the first statement inside the transaction, and sends an `"UPDATE"` to the parent's table for those keys; the 1 that came back is that statement's count (`django/db/models/sql/compiler.py:SQLUpdateCompiler.pre_sql_setup`, `django/db/models/sql/compiler.py:SQLUpdateCompiler.execute_sql`). The documentation gives the cost as an extra query for each ancestor (`docs/ref/models/querysets.txt`).

### What `bulk_update` leaves undone

`QuerySet.bulk_update` calls no `Model.save` and sends none of a save's signals, like any `QuerySet.update`. No field's `pre_save` is called either: the values are read off the instances with `getattr`, so a date with `auto_now=True` is written only if it is among the fields named, and then with whatever the instance holds. And nothing comes back from the database to the instances. One that was given an expression as a value still holds the expression afterwards.
