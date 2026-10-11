---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The field operations, and those on indexes and constraints

`AddField`, `RemoveField`, `AlterField` and `RenameField` are the migration operations on one field of a model, and `AddIndex`, `RemoveIndex`, `RenameIndex`, `AddConstraint`, `RemoveConstraint` and `AlterConstraint` those of `django.db.migrations` on one index or constraint of its `Meta`. They differ in which project state each takes its model from, in what running backwards means, and in what `preserve_default=False` does with a default.

Their shape, but for `AlterConstraint` and for a `RenameIndex` made with an index's fields in place of its old name, when that one runs backwards, is the one [Operations: the base class and its two halves](operations.md) describes: a **state half** that has the project state change a model state, and a **database half** that is given the **from-state** and the **to-state**, the project state before its change and the one after, takes a **historical model**, a class rendered from a model state, from one or both, and calls the schema editor ([The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md)). The examples are from yard, whose models are Dock, with a name and a port, and Repair, with a ship, a dock, a date started, later renamed begun, and notes.

## The field operations

`FieldOperation`, their base, keeps the model's name, the field's name and the field: unbound, as a model state holds its fields, and `None` in a `RemoveField` and a `RenameField`, which are made without one (`django/db/migrations/operations/fields.py:FieldOperation`).

### `AddField`, and a default for one call

`AddField.state_forwards` has `ProjectState.add_field` put the field into the model state. `AddField.database_forwards` takes the field from the to-state's historical model and hands it to `BaseDatabaseSchemaEditor.add_field` with the from-state's model, the table as it stands; backwards, model and field come from the from-state, by then the state that has the field, and go to `BaseDatabaseSchemaEditor.remove_field` (`django/db/migrations/operations/fields.py:AddField.database_forwards`).

A new column that may not be null needs a value for the rows already in the table. Repair's new foreman, `models.CharField(max_length=60)`, offers none, and for it the autodetector asks the questioner for one, sets it as the default of a clone of the field, and makes the operation with `preserve_default=False` (`django/db/migrations/autodetector.py:MigrationAutodetector._generate_added_field`; [The questioner: `MigrationQuestioner`](questioner.md)). With `'not recorded'` typed at the prompt, makemigrations wrote the operation below. In the recordings on this page a line that begins with a bar is a line of a file; any other line at the margin is Python as it ran, a question being followed by `->` and its answer, and set in under it are the calls it set going, with `changed:` before what then differs in the model state, `SQL` before a statement handed to Django's cursor, and in square brackets the operation or the recording's note on the call; only the lines a passage is about are written, and what ran between them is left out.

```text recording=migrations
|         migrations.AddField(
|             model_name='repair',
|             name='foreman',
|             field=models.CharField(default='not recorded', max_length=60),
|             preserve_default=False,
```

The default is for one call of the schema editor, and both halves keep it out of the model. Told `preserve_default=False`, `ProjectState.add_field` puts into the model state a clone of the field with its default set to `NOT_PROVIDED`, so the state this operation leaves, and a historical model rendered from it, has the field without that default (`django/db/migrations/state.py:ProjectState.add_field`). The database half therefore finds no default on the to-state's field: it sets the operation's there, calls the editor, and sets `NOT_PROVIDED` again.

The recording ran that operation by hand, on states made as the executor makes them. Here state is the to-state and previous the from-state:

```text recording=migrations
operation.state_forwards('yard', state)
  ProjectState.add_field(app_label='yard', model_name='repair', name='foreman', field=an unbound CharField, preserve_default=False)
  changed: state.models['yard', 'repair'].fields has gained 'foreman': CharField(max_length=60)
...
operation.database_forwards('yard', schema_editor, previous, state)
  AddField.database_forwards(from_state=previous, to_state=state)  [Add field foreman to repair]
    DatabaseSchemaEditor.add_field(model=the historical model yard.Repair, field=the field yard.Repair.foreman)  [field.default is 'not recorded' at this moment]
      DatabaseSchemaEditor._remake_table(model=the historical model yard.Repair, create_field=the field yard.Repair.foreman)
        SQL INSERT INTO "new__yard_repair" ("id", "notes", "dock_id", "ship_id", "begun", "foreman") SELECT "id", "notes", "dock_id", "ship_id", "begun", 'not recorded' FROM "yard_repair"
```

SQLite's editor builds the table again to add this column, and the default is the value it selects into every row (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.add_field`); what an editor that adds the column in place does with the default is in [The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md#defaults-written-once-then-dropped). `AlterField` takes `preserve_default=False` the same way, in both halves.

### `RemoveField`

`RemoveField` hands the editor's `remove_field` the from-state's model and its field, and backwards hands the editor's `add_field` the field as the to-state, the state before the removal, has it, with no default lent (`django/db/migrations/operations/fields.py:RemoveField.database_backwards`). Django's documentation counts the operation reversible, but for the data lost, where the field may be null or has a default (`docs/ref/migration-operations.txt`); a default `AddField` lent with `preserve_default=False` is not in the state its state half made, so a `RemoveField` run backwards to that state hands the editor the field without it.

### `AlterField` and `RenameField`

`AlterField` holds the field as it is to be. Its database half takes the field of that name from each state's historical model and hands both to `BaseDatabaseSchemaEditor.alter_field`, which compares them and decides what, if anything, is sent ([Altering a column, and SQLite's table remake](../backends/alter-field.md)).

`AlterField.database_backwards` calls `database_forwards` with the arguments it was given (`django/db/migrations/operations/fields.py:AlterField.database_backwards`). The direction is in the states: `Migration.unapply` gives a database half that runs backwards the state after the operation as its from-state and the state before as its to-state, so the same call alters the column from the newer field to the older (`django/db/migrations/migration.py:Migration.unapply`).

`RenameField` holds the old name and the new, and its database half is `alter_field` too: the from-state's field under the old name and the to-state's under the new, or backwards the from-state's under the new and the to-state's under the old (`django/db/migrations/operations/fields.py:RenameField.database_backwards`). For a field that has a column, the editor finds two columns that differ in name and renames the column, unless the field was given a column name of its own, when the two are one and nothing is sent. What `ProjectState.rename_field` must then correct elsewhere in the state is in [Project state: `ProjectState` and its model states](state.md).

## The operations on indexes and constraints

`IndexOperation` is the base of the index operations and of the constraint operations alike (`django/db/migrations/operations/models.py:IndexOperation`). It declares `IndexOperation.option_name`, the key of a model state's options its kind is kept under: `"indexes"`, which the constraint classes set to `"constraints"` and the autodetector reads.

### `AddIndex` and `RemoveIndex`: an index is its name

`AddIndex` holds an `Index` and hands it to `BaseDatabaseSchemaEditor.add_index`, or backwards to `BaseDatabaseSchemaEditor.remove_index`. `RemoveIndex` holds only a name, and finds the index with `ModelState.get_index_by_name`, forwards in the from-state's model state and backwards in the to-state's (`django/db/migrations/operations/models.py:RemoveIndex.database_forwards`). In each of these database halves the model, too, comes from the state that has the index.

A model state's index is found by its name ([Project state: `ProjectState` and its model states](state.md)), and `AddIndex.__init__` raises `ValueError` for an index that has none (`django/db/migrations/operations/models.py:AddIndex.__init__`).

### `RenameIndex`: by its old name, or by its fields

`RenameIndex` is made with a new name and exactly one of an old name and the names of the index's fields, `RenameIndex.old_fields`; its `__init__` raises `ValueError` for neither and for both (`django/db/migrations/operations/models.py:RenameIndex.__init__`).

Given the old name, the database half takes the old index from the from-state's model state and the new from the to-state's and hands both to `BaseDatabaseSchemaEditor.rename_index`. Backwards the operation exchanges its own old name and new, calls `RenameIndex.database_forwards`, and exchanges them back (`django/db/migrations/operations/models.py:RenameIndex.database_backwards`).

The field names are for an index that has no name in any state. A model state made by old migrations may hold tuples of field names under `"index_together"`, an option `Meta` no longer accepts, and the schema editor named each tuple's index as it created it. Where the models now declare an `Index` of just those fields, the autodetector makes a `RenameIndex` that gives the fields ([The autodetector: fields, indexes and constraints](autodetector-fields.md)). Its state half adds such an `Index` under the new name and takes the tuple out of `"index_together"`. Its database half has to ask the database what the index is called: it turns the field names into columns and asks `BaseDatabaseSchemaEditor._constraint_names` for the indexes on exactly those columns that are not unique, raises `ValueError` unless there is exactly one, and makes an `Index` under that name to stand for the old index (`django/db/migrations/operations/models.py:RenameIndex.database_forwards`).

Run backwards in this form, `RenameIndex.database_backwards` returns at once: the index keeps its new name while the state goes back to the tuple. Applied forwards again, the search finds the index already under the new name, and `database_forwards` returns before it calls `rename_index`.

### `AddConstraint`, `RemoveConstraint` and `AlterConstraint`

`AddConstraint` holds a constraint, whose name `BaseConstraint.__init__` requires, and `RemoveConstraint` a name, which it resolves with `ModelState.get_constraint_by_name` as `RemoveIndex` does. Unlike `AddIndex` and `RemoveIndex`, these two take the model from the to-state in each of their database halves, the model as it is to be when the call is done (`django/db/migrations/operations/models.py:RemoveConstraint.database_forwards`). SQLite's editor depends on it: for every constraint but a unique constraint with a condition, an expression, included fields or a deferral, it ignores the constraint it is handed and builds the table again from the model, with the model's constraints (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.remove_constraint`).

`AlterConstraint` changes the state and sends nothing: `ProjectState.alter_constraint` puts the constraint it holds in the place of the one of that name, and both database halves are empty (`django/db/migrations/operations/models.py:AlterConstraint`). A constraint is also checked in Python, when a model instance is validated, and the code and the message of the error raised there are arguments of the constraint, those `BaseConstraint.non_db_attrs` lists. Where two constraints of one name differ only in those, the autodetector makes an `AlterConstraint` in place of a removal and an addition ([The autodetector: fields, indexes and constraints](autodetector-fields.md)).

## What an operation says it touches: `references_model` and `references_field`

`Operation.references_model` and `Operation.references_field` are how the `reduce` of an earlier operation asks a later one whether it touches the earlier one's model or field (`django/db/migrations/operations/base.py:Operation.references_model`); what the optimizer does with the answer is in [The optimizer: `MigrationOptimizer` and `reduce`](optimizer.md).

`FieldOperation.references_model` says yes for the operation's own model and, where it holds a field, for a model the field points at or goes through. `FieldOperation.references_field` says yes, on its own model, for its own field's name, for a name among its field's `ForeignObject.from_fields`, and for a name its generated field's expression uses. Otherwise, where it holds a field, it gives the answer of `field_references`, which says whether a field refers to a given model or to a named field of it (`django/db/migrations/operations/fields.py:FieldOperation.references_field`). `RenameField.references_field` answers for both of its names. The index and constraint operations declare neither method, and so give the base's answer, yes to every model and every field ([Operations: the base class and its two halves](operations.md)).

## The helpers: `field_references`, `get_references` and `field_is_referenced`

`field_references`, `get_references` and `field_is_referenced` answer from a model state's relations, which are strings, with nothing rendered. `resolve_relation` turns a relation's target, however written, into the key of a model state, a pair of an application's label and a model's name in lower case, and takes what a bare name or `"self"` leaves out from the label and the name it is given (`django/db/migrations/utils.py:resolve_relation`).

`field_references` is given a model's key, one of its fields and the key of the model asked about, and returns `False` or a `FieldReference`, a named tuple of two members, to and through (`django/db/migrations/utils.py:field_references`). The first is set where the field's target is that model, and the second where the model between of a many-to-many field is; each is the pair of the field's relation object, a `ManyToOneRel` for a foreign key, and the fields it names there, `ForeignObject.to_fields` or `ManyToManyRel.through_fields`. Given a field's name as well, it counts a relation that names that field and one that names no field at all. A foreign key naming none is a case apart, for it points at the primary key: handed the field with the name, the function counts it only if the field is the primary key, and handed the name alone, it cannot tell and counts it. The docstring admits these false positives, and says they should not be an issue where the question is whether an optimization can take place, as when `FieldOperation.references_field` asks. In the recording dock is Repair's foreign key to Dock:

```text recording=migrations
dock.to_fields  ->  [None]
field_references(('yard', 'repair'), dock, ('yard', 'dock'), 'id', state.models['yard', 'dock'].fields['id'])  ->  FieldReference(to=(a ManyToOneRel, [None]), through=None)
field_references(('yard', 'repair'), dock, ('yard', 'dock'), 'name', state.models['yard', 'dock'].fields['name'])  ->  False
field_references(('yard', 'repair'), dock, ('yard', 'dock'), 'name')  ->  FieldReference(to=(a ManyToOneRel, [None]), through=None)
```

`get_references` runs `field_references` over every field of every model state of a project state and yields each field that refers, with its model state, its name and the reference; `field_is_referenced` says whether there is any. `ProjectState.rename_model` and `ProjectState.rename_field` repoint relations with the first, and `ProjectState.alter_field` decides with the second how much must be rendered again ([Historical models: `StateApps` and rendering](historical-models.md)).
