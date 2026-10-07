---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Saving an instance

`Model.save` writes an instance to the database one table at a time. For each table it sends an `"UPDATE"`, an `"INSERT"`, or the first and then the second, decided by what the instance holds, the arguments, and whether the update touched a row, ordinarily without a query to ask whether the row exists. The choice is made in `Model._save_table`; `Model.save_base` sends the signals and wraps the work, and what the statement returns is put back on the instance.

An instance does not know for certain whether it has a row. It was made by a query, or by a call of its class, or copied, or unpickled, and it may have been given a primary key by hand; what its state records is whether this object was loaded or saved, not whether a row with its key exists. So a save cannot simply insert what is new and update what is old. Django's answer is to try: where the instance has a key, send an update for that key and look at whether a row was touched; where that fails, or there is no key, insert. The rest of the method is the exceptions to that rule and the bookkeeping around it.

The work is divided among a chain of methods, of which one runs once for the save and another once for each table:

```text recording=models
heron.save(): a new Ship, whose primary key is not set
    Model.save()  (a Ship)
      Model._prepare_related_fields_for_save
      Model.save_base()
        signal pre_save, sender Ship, raw=False, update_fields=None
        mark_for_rollback_on_error
        Model._save_table(cls=Ship)
          Field.get_pk_value_on_save()  (Ship.id)  ->  None
          Model._do_insert(fields=[name, tonnage, home, captain], returning_fields=[id])
            SQL INSERT INTO "fleet_ship" ("name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s) RETURNING "fleet_ship"."id" with params ('Heron', 300, 1, None)
            -> [(3,)]
          Model._assign_returned_values((3,), [id])
          -> updated: False
        signal post_save, sender Ship, created=True, update_fields=None
```

`Model.save` runs once and settles the arguments. `Model.save_base` runs once and does what belongs to the save as a whole: the two signals, the transaction, the instance's state. In a save that is not raw, `Model._save_table` runs once for each table: once for a model with no parents, and once more for each parent of a model that has them. And `Model._do_update` and `Model._do_insert` ordinarily send one statement each, through a queryset method made for saving (`django/db/models/base.py:Model.save`, `django/db/models/base.py:Model.save_base`).

In the recordings of this page, `_save_table` returns whether it updated a row, so `updated: False` under an insert means only that there was no row to update, and `_do_update` returns a list with an entry for the row it updated, or an empty one. Each save quoted here sent `pre_save` as it entered `save_base`, and `post_save` if it reached the end. Most quotes after this one leave those lines out, and the calls of each field's `pre_save` are listed in one recording only, in the section about them.

## What `save` settles first

Before it writes, `save` looks at the related objects the instance holds. A relation field whose object was assigned, and whose object still has no primary key, is refused. The source's comment gives the reason: where the field may be null, the save would go through and the reference would be silently lost (`django/db/models/base.py:Model._prepare_related_fields_for_save`):

```text recording=models
Sailor(name='Gus', ship=Ship(name='Tern', tonnage=50, home=leith)).save(): the ship has not been saved
    Model.save()  (a Sailor)
      Model._prepare_related_fields_for_save  raises ValueError
    the caller catches ValueError: save() prohibited to prevent data loss due to unsaved related object 'ship'.
```

The same method deals with a related object that was assigned first and saved afterwards. The instance's key attribute was set when the object had no key, so it is empty; finding that the object now has one, the method assigns the object again, which copies the key across.

Then the arguments. With no alias given, one comes from the router's `ConnectionRouter.db_for_write`. Forcing an insert together with forcing an update, or with `"update_fields"`, is refused. And `"update_fields"`, when given, is checked: an empty one ends the save at that point, with no signal sent and nothing written, and every name in it must be the name or the attname of a concrete field that is not part of a primary key, the model's own or a parent's (`django/db/models/options.py:Options._non_pk_concrete_field_names`).

One case sets `"update_fields"` without being asked. An instance with deferred fields has nothing to write for them, and writing the others must not disturb them:

```text recording=models
A Ship fetched with only('name') is renamed and saved
    SQL SELECT "fleet_ship"."id", "fleet_ship"."name" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Skua',)
    Model.save()  (a Ship)
      Model._prepare_related_fields_for_save
      Model.save_base(update_fields={'name'})
        mark_for_rollback_on_error
        Model._save_table(cls=Ship, update_fields={'name'})
          Model._do_update(pk_val=40, values for [name], forced_update)
            SQL UPDATE "fleet_ship" SET "name" = %s WHERE "fleet_ship"."id" = %s with params ('Skua II', 40)
            -> [()]
          -> updated: True
```

The save was called with no arguments, and it handed `save_base` an `"update_fields"` of one name. When `"update_fields"` was not given and the instance has a key, is being saved to the database its state names, is not forced to insert, and lacks the value of some concrete field that is not generated, `save` sets `"update_fields"` itself: to the concrete fields outside the key whose values the instance holds, and with them the model's generated fields, held or not. Where that leaves no name it sets nothing. The statement here sets one column. Such a save is an update and nothing else: where no row has the key it raises `Model.NotUpdated`, as it would had the caller given the names.

## Once for the whole save: `save_base`

`Model.save_base` begins by working out which class it is saving. For a proxy that is the concrete model behind it, whose options and tables are used from here on; the proxy stays the sender of the signals.

It sends `pre_save` before anything is written and `post_save` after everything is, the second with `created=True` when the model's own table took an insert. A model that Django made itself, the table between the two sides of a many-to-many relation, sends neither.

Between the two it opens a block. Which kind depends on whether the model has parents, and the source's comment gives the thought behind it: a transaction is not needed if one query is issued. A model with parents will write several tables, and gets a block of `atomic`, without a savepoint (`django/db/transaction.py:atomic`). A model without parents gets `mark_for_rollback_on_error`, which starts nothing (`django/db/transaction.py:mark_for_rollback_on_error`). The comment counts the ordinary case: where such a save sends an update that touches nothing and then an insert, as one recorded below does, the two statements have no transaction of the save's own around them.

What that second block does matters to a caller who catches a failed save. If an exception leaves it while the save is inside an `atomic` block of the caller's, that outer transaction is marked as needing a rollback, and the next query in it is refused. This is so for any exception that leaves the block, the model's own `Model.NotUpdated` included, not only for an error from the database. An exception raised before the block is entered, as the `ValueError` for an unsaved related object is, marks nothing.

Inside the block the parents are saved and then the model's own table, each by `_save_table`. Afterwards `save_base` sets the instance's state (`django/db/models/base.py:ModelState`): the alias it was saved to, and `ModelState.adding` false.

`save_base` can also be called with `raw=True`, and deserialization does so when it loads a fixture (`django/core/serializers/base.py:DeserializedObject.save`): the object is to be written exactly as it stands. A raw save does not save parents, does not call a field's `pre_save`, and passes the flag on to both signals (`django/db/models/base.py:Model.save_base`).

## Once for each table: update, or else insert

`Model._save_table` is where the statements are chosen (`django/db/models/base.py:Model._save_table`). It first makes the list of fields an update may set: the concrete fields of this table that are neither part of the primary key nor generated, narrowed to `"update_fields"` when that was given. Then it goes through a short series of questions.

```text figure=update-or-insert
Model._save_table, for one table of a model.

Is the primary key set?
    no:   ask the key's field for a value (get_pk_value_on_save), unless it holds a placeholder, and go on
    A key still unset when an update was forced, or update_fields given, raises ValueError.

Is the instance being added, and has every field of the key a default?
    (and the save is not raw, and neither force_insert nor force_update was given)
    yes:  INSERT
    no:   go on

Is the key set, and the save not an insert?
    no:   INSERT
    yes:  UPDATE ... where the key matches
              a row was updated:     this table is done
              no row was updated:    Was an update forced, or update_fields given?
                                         yes:  raise NotUpdated
                                         no:   INSERT
```

*The decision in `Model._save_table`. An update is tried only for a key that is set, and an insert follows an update that touched nothing unless an update was forced or `"update_fields"` is set, by the caller or by `save` itself for an instance with deferred fields.*

**A key that is not set** is given a chance to be made, unless what it holds is the placeholder for a default the database will supply. `Field.get_pk_value_on_save` returns what `Field.get_default` gives, unless the field's `default` is a false value such as `0`, when it returns `None` (`django/db/models/fields/__init__.py:Field.get_pk_value_on_save`). `Model.__init__` has already applied a default once, so this matters for an instance whose key is `None` all the same: given as `None`, or set back to it afterwards. For an automatic key the answer is `None`: it stays unset, and is left for the database to assign. A key that is still unset when an update was forced, or `"update_fields"` given, raises `ValueError` here.

**An insert at once.** When the state says the instance is being added, and every field of the key has a default or a default the database supplies, the save becomes an insert before any update is considered, unless it is raw or was forced either way with `force_insert=True` or `force_update=True`. Giving `"update_fields"` does not stop it: a new Manifest saved with `"update_fields"` is inserted whole. The condition is on the fields having defaults, not on where this instance's key came from. The office's manifests are numbered by a function:

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

```text recording=models
a Manifest is made: its serial is 'M-0001', its stamped is a DatabaseDefault, and it has no value under kilos
Model.save()  (a Manifest)
  Model._prepare_related_fields_for_save
  Model.save_base()
    mark_for_rollback_on_error
    Model._save_table(cls=Manifest)
...
      Model._do_insert(fields=[serial, voyage, crates, kilos_each, stamped, scan], returning_fields=[kilos, stamped])
...
        SQL INSERT INTO "office_manifest" ("serial", "voyage_id", "crates", "kilos_each", "scan") VALUES (%s, %s, %s, %s, %s) RETURNING "office_manifest"."kilos", "office_manifest"."stamped" with params ('M-0001', 1, 12, 40, '')
        -> [[480, False]]
      Model._assign_returned_values([480, False], [kilos, stamped])
      -> updated: False
```

The key was set, to a serial the default supplied, and no update was tried. So a new row whose key came from a default costs one statement and not two; and a new instance given by hand the key of an existing row is inserted, and refused by the database, where a model without the default would have updated that row.

**An update first.** Otherwise, a key that is set means an update is tried, and its result decides. This is a Ship given a key by hand, for which there is no row:

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

The update came back empty and the insert followed, with the key among its columns. Had the row existed, the first statement would have been the whole save. That is what the second save of the Heron, the Ship of the first recording, was:

```text recording=models
heron.save() again, with its tonnage changed
    Model.save()  (a Ship)
      Model._prepare_related_fields_for_save
      Model.save_base()
        signal pre_save, sender Ship, raw=False, update_fields=None
        mark_for_rollback_on_error
        Model._save_table(cls=Ship)
          Model._do_update(pk_val=3, values for [name, tonnage, home, captain])
            SQL UPDATE "fleet_ship" SET "name" = %s, "tonnage" = %s, "home_id" = %s, "captain_id" = %s WHERE "fleet_ship"."id" = %s with params ('Heron', 320, 1, None, 3)
            -> [()]
          -> updated: True
        signal post_save, sender Ship, created=False, update_fields=None
```

**A forced update** takes away the fallback. With `"update_fields"`, or with `force_update=True` for the model's own table, an update that touches no row raises the model's `Model.NotUpdated`:

```text recording=models
Ship(id=99, name='Auk', tonnage=70, home=leith).save(update_fields=['tonnage']): no such row
    Model.save(update_fields=['tonnage'])  (a Ship)
      Model._prepare_related_fields_for_save
      Model.save_base(update_fields={'tonnage'})
        mark_for_rollback_on_error
        Model._save_table(cls=Ship, update_fields={'tonnage'})
          Model._do_update(pk_val=99, values for [tonnage], forced_update)
            SQL UPDATE "fleet_ship" SET "tonnage" = %s WHERE "fleet_ship"."id" = %s with params (70, 99)
            -> []
          raises NotUpdated
    the caller catches Ship.NotUpdated: Save with update_fields did not affect any rows.
```

> **Changed in 6.0.** The exception used to be a plain `DatabaseError`. `Model.NotUpdated` is a subclass of it, made for each model class that is not abstract ([`ModelBase`: a class statement becomes a model](metaclass.md)).

**A forced insert** skips the update, and leaves it to the database to refuse a key that is taken. The recording shows the argument as a tuple of classes, which is what `save_base` makes of `True`:

```text recording=models
Model.save(force_insert=True)  (a Ship)
  Model._prepare_related_fields_for_save
  Model.save_base(force_insert=True)
    mark_for_rollback_on_error
    Model._save_table(cls=Ship, force_insert=(Ship,))
...
        SQL INSERT INTO "fleet_ship" ("id", "name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s, %s) RETURNING "fleet_ship"."id" with params (40, 'Skua', 90, 2, None)
        raises IntegrityError
the caller catches IntegrityError: UNIQUE constraint failed: fleet_ship.id
```

The recorded cases, side by side:

| the instance | what `_save_table` sends |
|---|---|
| new, with no key | an insert |
| saved or loaded before | an update |
| a key set by hand, and no such row | an update that touches nothing, then an insert |
| new, with a key whose field has a default | an insert |
| `"update_fields"` given, and no such row | an update that touches nothing, then `Model.NotUpdated` |
| `force_insert=True`, and the row exists | an insert, which the database refuses |

*What one call of `Model._save_table` sent for each of the cases recorded in this part of the page.*

## The update

`Model._do_update` is handed a queryset from the model's base manager, the key, and a value for each field to write, and filters the queryset to the key (`django/db/models/base.py:Model._do_update`). It is the base manager's queryset and not the default manager's: a default manager whose queryset leaves some rows out has no say in which row a save can update ([Managers](managers.md)).

With values to write it calls `QuerySet._update`, a version of `QuerySet.update` that takes field objects, and returns what that returns: a list with an entry for the row it updated, or an empty one. With no values to write there is nothing to send, and the method has to decide what to report. If `"update_fields"` was given it reports success, since a save of fields that all belong to another table of the model has nothing to do here. Otherwise this table has nothing to write but its key, as the table of a child with no field of its own has, and the one thing to find out is whether the row exists, which costs a query, by `QuerySet.exists`.

A model whose `Meta` sets `select_on_save` spends queries to be sure, where the update was not forced. Before the update it asks whether the row exists and reports failure if not. After an update that reports no row it asks again, and reports success if the row is there. The source's comment names the case this is for: a database that returns zero for an update that did match a row.

## The insert

`Model._save_table` hands the insert the concrete fields of the table that are not generated, less the automatic key when it has no value, so that the database assigns one. The statement may hold fewer columns still: the Manifest's insert above has no `"stamped"`, whose value was the placeholder for the database's default, and the compiler leaves out a column for which every row has that placeholder, unless it is the only column left. For a model ordered with respect to another, a query first finds the next position among its siblings and sets it.

The statement is sent by `Model._do_insert`, through `QuerySet._insert` on the base manager, with the list of fields to write and a second list: the fields whose values the database should hand back (`django/db/models/base.py:Model._do_insert`, `django/db/models/query.py:QuerySet._insert`).

## What comes back

Some values are only known once a save's statement has run: an automatic key, a default the database supplied, a generated column, the result of an expression. `Model._save_table` therefore asks for them in the same statement, where the backend can return columns, and `Model._assign_returned_values` sets each on the instance under its field's attname (`django/db/models/base.py:Model._assign_returned_values`).

For an insert the list starts as `Options.db_returning_fields`, which for Ship is its key and for Manifest, in the recording above, the generated column and the column with a database default: the instance had a placeholder under `"stamped"` and nothing at all under `"kilos"` before the save, and has `False` and `480` after it. To that list is added any field whose value is an expression. For an update the list is the fields whose value is an expression (where `"update_fields"` is set, those it holds by name), and the generated fields that depend on a field being written.

An expression is the case where the instance would otherwise be left holding something that is not a value. By now the Heron's row holds a tonnage of 330, from a save with `"update_fields"` that is not quoted here, and the instance a new name which that save did not write:

```text recording=models
heron.tonnage = F('tonnage') + 20, and heron.save(): the value is an expression
    Model.save()  (a Ship)
      Model._prepare_related_fields_for_save
      Model.save_base()
        mark_for_rollback_on_error
        Model._save_table(cls=Ship)
          Field.pre_save(add=False)  (Ship.name)  ->  'Heron II'
          Field.pre_save(add=False)  (Ship.tonnage)  ->  <CombinedExpression: F(tonnage) + Value(20)>
          Field.pre_save(add=False)  (Ship.home)  ->  1
          Field.pre_save(add=False)  (Ship.captain)  ->  None
          Model._do_update(pk_val=3, values for [name, tonnage, home, captain], returning_fields=[tonnage])
            SQL UPDATE "fleet_ship" SET "name" = %s, "tonnage" = ("fleet_ship"."tonnage" + %s), "home_id" = %s, "captain_id" = %s WHERE "fleet_ship"."id" = %s RETURNING "fleet_ship"."tonnage" with params ('Heron II', 20, 1, None, 3)
            -> [(350,)]
          Model._assign_returned_values((350,), [tonnage])
          -> updated: True
```

```text recording=models
Asked of the Ship after the expression was saved
    heron.tonnage  ->  350
```

After an update, or an insert that handed something back, a field that was to come back and did not is not left stale. Its entry is removed from the instance's `__dict__`, which makes it deferred, and the next read of the attribute fetches it ([An instance and its state](instances.md)).

> **Changed in 6.0.** Generated fields and fields assigned an expression are refreshed after a save since 6.0: from the statement's `"RETURNING"` clause where the backend has one, and otherwise by being made deferred in the cases just given.

## `pre_save`, and why an insert calls it twice

Every value written by a save that is not raw starts from what the field's `pre_save` returns, not from what is read off the instance. For a field that does not override it that is the same thing: `Field.pre_save` returns the attribute (`django/db/models/fields/__init__.py:Field.pre_save`). A field that sets itself on saving overrides it, as a date with `auto_now_add` does, and a file field uses it to write its file ([A field: the base class](fields.md), [File fields](files.md)).

An update calls it once for each field. An insert calls it twice:

```text recording=models
Port(name='Oban', country='Scotland').save(): the same kind of save, with each call of a field's pre_save
    Model.save()  (a Port)
      Model._prepare_related_fields_for_save
      Model.save_base()
        mark_for_rollback_on_error
        Model._save_table(cls=Port)
          Field.get_pk_value_on_save()  (Port.id)  ->  None
          Field.pre_save(add=True)  (Port.name)  ->  'Oban'
          Field.pre_save(add=True)  (Port.country)  ->  'Scotland'
          Model._do_insert(fields=[name, country], returning_fields=[id])
            SQLInsertCompiler.pre_save_val(Port.name)
              Field.pre_save(add=True)  (Port.name)  ->  'Oban'
              -> 'Oban'
            SQLInsertCompiler.pre_save_val(Port.country)
              Field.pre_save(add=True)  (Port.country)  ->  'Scotland'
              -> 'Scotland'
            SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Oban', 'Scotland')
            -> [(4,)]
          Model._assign_returned_values((4,), [id])
          -> updated: False
```

`_save_table` calls it first for each field to be inserted, and uses the result only to see whether it is an expression, which decides the list of fields to return. The values that go into the statement are fetched again by the insert's compiler, which calls `pre_save` itself for each field of each object it is given (`django/db/models/sql/compiler.py:SQLInsertCompiler.pre_save_val`). A `pre_save` with an effect beyond returning a value therefore has to tolerate being called twice in one save, and three times in a save that tries an update and falls back to an insert, the first of them with `add=False`.

## A model with a parent

A model that inherits from one with a table of its own is a row in each table, and `Model._save_parents` writes the parent's first (`django/db/models/base.py:Model._save_parents`). For each parent it calls itself, so that a grandparent is written before a parent, then `_save_table` for the parent's class, and then copies the parent's key into the child's link field, which is how a key the database has just assigned reaches the child's row.

```text recording=models
Officer(name='Finn', ship=gannet, rank=Rank.MATE).save(): a model with a parent, two tables
    Model.save()  (an Officer)
      Model._prepare_related_fields_for_save
      Model.save_base()
        signal pre_save, sender Officer, raw=False, update_fields=None
        Atomic.__enter__  (savepoint=False)
          SQL BEGIN
        Model._save_parents(cls=Officer)
          Model._save_table(cls=Sailor)
            Field.get_pk_value_on_save()  (Sailor.id)  ->  None
            Model._do_insert(fields=[name, ship, signed_on], returning_fields=[id])
              SQL INSERT INTO "crew_sailor" ("name", "ship_id", "signed_on") VALUES (%s, %s, %s) RETURNING "crew_sailor"."id" with params ('Finn', 2, '2026-04-10 09:00:00')
              -> [(6,)]
            Model._assign_returned_values((6,), [id])
            -> updated: False
          -> inserted: True
        Model._save_table(cls=Officer, force_insert=True)
          Model._do_insert(fields=[sailor_ptr, rank], returning_fields=[])
            SQL INSERT INTO "crew_officer" ("sailor_ptr_id", "rank") VALUES (%s, %s) with params (6, Rank.MATE)
            -> []
          -> updated: False
        Atomic.__exit__
          BaseDatabaseWrapper.commit
        signal post_save, sender Officer, created=True, update_fields=None
```

The second `_save_table` was told to insert: `save_base` passes that on whenever a parent's row was inserted, so no update is tried for the child's. The two inserts are inside one transaction, begun before the first and committed after the second. A later save of the same Officer sends an update to each table:

```text recording=models
Model._save_parents(cls=Officer)
  Model._save_table(cls=Sailor)
    Model._do_update(pk_val=6, values for [name, ship, signed_on])
      SQL UPDATE "crew_sailor" SET "name" = %s, "ship_id" = %s, "signed_on" = %s WHERE "crew_sailor"."id" = %s with params ('Finn', 2, '2026-04-10 09:00:00', 6)
      -> [()]
    -> updated: True
...
Model._save_table(cls=Officer)
  Model._do_update(pk_val=6, values for [rank])
    SQL UPDATE "crew_officer" SET "rank" = %s WHERE "crew_officer"."sailor_ptr_id" = %s with params (Rank.ENGINEER, 6)
    -> [()]
  -> updated: True
```

Where a model reaches the same ancestor by two routes, the ancestor is saved once: the method keeps a dictionary of the parents it has dealt with in this save. And `"force_insert"` need not be a boolean for a model with parents. `True` forces the model's own table only, and each parent's table is decided as usual. A tuple of classes, each a base of the model, also forces the table of every parent that is one of them or inherits from one (`django/db/models/base.py:Model._validate_force_insert`, `django/db/models/base.py:Model._save_parents`). `force_update=True` is not handed to `_save_parents` at all: a parent's table is decided as usual, and where its row is inserted the child's is too.

## A key of several columns

Nothing in the choice `Model._save_table` makes between an update and an insert depends on the key being one column. For a model with a composite primary key, the key's value is a tuple, it is set when every part of it is, and on SQLite the update's condition compares the columns together:

```text recording=models
Model.save()  (a Berth)
  Model._prepare_related_fields_for_save
  Model.save_base()
    mark_for_rollback_on_error
    Model._save_table(cls=Berth)
      Model._do_update(pk_val=(1, 2), values for [metres])
        SQL UPDATE "office_berth" SET "metres" = %s WHERE ("office_berth"."port_id", "office_berth"."number") = (%s, %s) with params (150, 1, 2)
        -> [()]
      -> updated: True
```

## What a save leaves alone

A save does not validate. It sends what the instance holds, and a value the table will not take comes back as the database's own error ([Validating an instance](validation.md)). It does not write many-to-many relations, which have no column in the model's table and are changed through their managers ([Many-to-many relations](many-to-many.md)). And it writes every column of the fields listed above, changed or not, unless `"update_fields"` narrows it: an instance keeps no record of what has changed.

`QuerySet.create` is a call of the model and a `save` with `force_insert=True` (`django/db/models/query.py:QuerySet.create`). `Model.asave` awaits `save`, wrapped in `sync_to_async`, with the same arguments.
