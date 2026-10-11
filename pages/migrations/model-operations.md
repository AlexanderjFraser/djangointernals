---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The model operations: `CreateModel`, `DeleteModel`, `RenameModel` and the option operations

The model operations are the migration operations that act on a model as a whole: `CreateModel` and `DeleteModel` make and drop its table, `RenameModel` renames it and what is named after it, and the option operations (`AlterModelTable`, `AlterModelTableComment`, `AlterUniqueTogether`, `AlterIndexTogether`, `AlterOrderWithRespectTo`, `AlterModelOptions`, `AlterModelManagers`) each change options of its `Meta` or, the last, its managers. All are subclasses of `ModelOperation` (`django/db/migrations/operations/models.py`).

An operation's **state half** changes the project state, and its **database half** is given the schema editor and two project states: going forwards, the **from-state** before the operation and the **to-state** after it ([Operations: the base class and its two halves](operations.md)). A change to a whole model brings more with it than its table: the tables that point at it, the tables of its many-to-many fields, a column no field of the model state stands for, options that mean nothing to a database. `ModelOperation` holds the model's name as given and, in `ModelOperation.name_lower`, in lower case, as a project state keys its model states; what `ModelOperation.reduce` and its overrides answer the optimizer is in [The optimizer: `MigrationOptimizer` and `reduce`](optimizer.md).

## `CreateModel` and `DeleteModel`

`CreateModel` is given what a model state holds but for the application's label, which its state half is handed: the model's name, its fields as pairs of a name and an unbound field, a dictionary of options, the bases (classes, or strings such as `"crew.sailor"` for a model of the history) and the managers as pairs of a name and a manager. Where the options, the bases or the managers are not given, `CreateModel.__init__` puts in their place an empty dictionary, the one base `Model` and an empty list, and it has `_check_for_duplicates` raise `ValueError` for a field name, a base or a manager name given twice (`django/db/migrations/operations/models.py:CreateModel.__init__`).

Its state half makes a `ModelState` of all this and the label and hands it to `ProjectState.add_model`; the lists of fields and of managers and the dictionary of options are copies, and the fields and managers in them are the operation's own objects (`django/db/migrations/operations/models.py:CreateModel.state_forwards`). Its database half takes the **historical model**, the class rendered from the model state ([Historical models: `StateApps` and rendering](historical-models.md)), from the to-state's registry and, unless `Operation.allow_migrate_model` says no, hands it to `BaseDatabaseSchemaEditor.create_model`, which sends the table's statement, holds its indexes back and makes the tables Django makes for the model's many-to-many fields ([The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md)). The answer is no for a proxy, before any router is asked, so the `CreateModel` of a proxy changes the state and sends nothing (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`).

`ModelState.render` leaves `"index_together"` out of the options it makes a class from, so where an old migration's `CreateModel` gave that option, the historical model cannot tell `create_model` of it. `CreateModel.database_forwards` reads the option from the to-state's model state and, where it is there, calls `BaseDatabaseSchemaEditor.alter_index_together` with an empty set for the old value (`django/db/migrations/operations/models.py:CreateModel.database_forwards`). Its comment says the call can move into the schema editor once that works from model states (ticket 29898).

> **Changed in 5.1.** `Meta` stopped taking `"index_together"` (`docs/releases/5.1.txt`).

`CreateModel.database_backwards` takes the model from the from-state, which going backwards is the state that has it, and calls `BaseDatabaseSchemaEditor.delete_model`. `DeleteModel` is the mirror, without the call for `"index_together"`: its state half is `ProjectState.remove_model`, `DeleteModel.database_forwards` takes the model from the from-state and calls `delete_model`, and `DeleteModel.database_backwards` takes it from the to-state and calls `create_model` (`django/db/migrations/operations/models.py:DeleteModel`). So `DeleteModel` is reversible, and what reversing it gives back is a table: the rows are gone, and so is any index made for `"index_together"`.

## `RenameModel`

`RenameModel` has more to rename than a table: foreign keys in other tables name that table, and the table Django makes for a many-to-many field is named after the model's table and the field, unless the field names one (`django/db/models/fields/related.py:ManyToManyField._get_m2m_db_table`), and has a column named after the model (`django/db/models/fields/related.py:create_many_to_many_intermediary_model`). `RenameModel.database_forwards` takes the table, the fields that point at the model and its many-to-many fields, in that order (`django/db/migrations/operations/models.py:RenameModel.database_forwards`).

The state half, `ProjectState.rename_model`, puts a clone of the model state under the new name, replaces with a clone each field of any model that names the old one, as its target or its through model, and removes the old model state ([Project state: `ProjectState` and its model states](state.md)). So the database half finds the model under its old name in the from-state's registry and under its new one in the to-state's, and first hands `BaseDatabaseSchemaEditor.alter_db_table` the two tables' names; that method returns at once where they are equal, as for a model whose `Meta` gives `db_table`.

Then, for each relation in `Options.related_objects` of the from-state's model, `BaseDatabaseSchemaEditor.alter_field` is called with the model that holds the field, from the to-state, and the field as each state has it (`django/db/models/options.py:Options.related_objects`). The field's column is as it was; the model it names is not. For a foreign key, `BaseDatabaseSchemaEditor._field_should_be_altered` counts that a change only where the target's table has a new name, and `BaseDatabaseSchemaEditor._alter_field` then drops the field's constraint, where it has one, and makes it again under a name made from the new table's. SQLite's editor, for which a foreign key is part of a column's definition, builds the pointing table again ([Altering a column, and SQLite's table remake](../backends/alter-field.md)). For a many-to-many field whose table Django made, `alter_field` calls `BaseDatabaseSchemaEditor._alter_many_to_many`.

> **Trap.** `related_objects` holds a hidden relation only where it is a many-to-many field's, so a foreign key whose related name ends in `"+"` is not altered, and its constraint is not made again under a new name ([The options: what a model keeps as `_meta`](../models/options.md#what-hidden-means)).

Last, the model's own many-to-many fields, paired between the two states, for the tables Django made for them. One with a through model of the project's own has no such table and is passed over, and so is one from the model to itself, which the loop before has handed to `alter_field`. For the others `_alter_many_to_many` renames the field's table where its name has changed and hands the table's two foreign keys to `alter_field`, which returns at once for a key that has not changed. The key pointing back at the model has a column named after the model, and that column changes even where `db_table` has kept the model's table. SQLite's editor, in a `_alter_many_to_many` of its own, builds the field's table again or, where its name changes, makes the new table, copies the rows and drops the old (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor._alter_many_to_many`).

The recordings on this page were made on SQLite with operations run by hand: a line at the margin is Python as it ran, and under it are the calls it set going, nested as they were made, each method by the class that declares it (in parentheses where the object is of another class) and an operation's with its description in square brackets; `SQL` begins a statement as Django handed it to its cursor, a line marked changed says what a state half altered, and only the lines the passage is about are written, what ran between them being left out. Here Dock is renamed Basin, before and after are the project states on either side of the state half, and Dock was given a many-to-many field to Ship, visitors, for the block:

```text recording=migrations
rename.database_forwards('yard', schema_editor, before, after)
  RenameModel.database_forwards(from_state=before, to_state=after)  [Rename model Dock to Basin]
    DatabaseSchemaEditor.alter_db_table(model=the historical model yard.Basin, old_db_table='yard_dock', new_db_table='yard_basin')  (BaseDatabaseSchemaEditor.alter_db_table)
      SQL ALTER TABLE "yard_dock" RENAME TO "yard_basin"
    DatabaseSchemaEditor.alter_field(model=the historical model yard.Repair, old_field=the field yard.Repair.dock, new_field=the field yard.Repair.dock)  (BaseDatabaseSchemaEditor.alter_field)
      DatabaseSchemaEditor._remake_table(model=the historical model yard.Repair, alter_fields=[(the field yard.Repair.dock, the field yard.Repair.dock)])  (what it called is not written, and of the 6 statements it sent the first and the last)
        SQL CREATE TABLE "new__yard_repair" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "started" date NOT NULL, "notes" text NOT NULL, "dock_id" bigint NOT NULL REFERENCES "yard_basin" ("id") DEFERRABLE INITIALLY DEFERRED, "ship_id" bigint NOT NULL REFERENCES "fleet_ship" ("id") DEFERRABLE INITIALLY DEFERRED)
        ... (4 statements between, not written)
        SQL CREATE INDEX "yard_repair_ship_id_3fb74465" ON "yard_repair" ("ship_id")
    DatabaseSchemaEditor._alter_many_to_many(model=the historical model yard.Basin, old_field=the field yard.Dock.visitors, new_field=the field yard.Basin.visitors, strict=False)
...
      SQL INSERT INTO "yard_basin_visitors" (id, basin_id, ship_id) SELECT id, dock_id, ship_id FROM "yard_dock_visitors"
```

`RenameModel.database_backwards` exchanges the operation's two names, calls `database_forwards` with the states it was given, of which the from-state is now the one that has the new name, and exchanges them back: the same code renames Basin to Dock.

## The option operations: `ModelOptionOperation`

The option operations are subclasses of `ModelOptionOperation`, which adds to `ModelOperation` only the category `OperationCategory.ALTERATION` and `ModelOptionOperation.reduce` (`django/db/migrations/operations/models.py:ModelOptionOperation`). All but `AlterModelManagers` have one state half, `ProjectState.alter_model_options` with a dictionary that it lays over the model state's options (`django/db/migrations/state.py:ProjectState.alter_model_options`). None has a backwards half of its own: `AlterModelTable.database_backwards` calls `AlterModelTable.database_forwards`, and so do the others' that are not empty. The forwards half reads the old value from the from-state and the new from the to-state, and going backwards the two arrive exchanged ([A migration: its operations, its dependencies and how it is applied](migration.md)).

### `AlterModelTable` and `AlterModelTableComment`

`AlterModelTable` sets `"db_table"`, to a name or to `None` for the name Django would make. With the model's table it renames the tables Django made for the model's many-to-many fields, whose names follow the model's unless the field gives one (`django/db/migrations/operations/models.py:AlterModelTable.database_forwards`).

`AlterModelTableComment` sets `"db_table_comment"`, and `BaseDatabaseSchemaEditor.alter_db_table_comment` sends a statement only where the editor has a template for one and the features have `BaseDatabaseFeatures.supports_comments`, which SQLite's lack (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.alter_db_table_comment`).

### `AlterUniqueTogether` and `AlterIndexTogether`

`AlterUniqueTogether` and `AlterIndexTogether` are `AlterTogetherOptionOperation` with one `AlterTogetherOptionOperation.option_name` each: `"unique_together"` and `"index_together"`. The database half reads the option from the two states' model states, not from the historical models, and hands the old value and the new to the schema editor's method named after the option, which drops what is only in the old and makes what is only in the new (`django/db/migrations/operations/models.py:AlterTogetherOptionOperation.database_forwards`). Django's documentation supports `AlterIndexTogether` only for migration files from before 4.2 (`docs/ref/migration-operations.txt`).

### `AlterOrderWithRespectTo`

`AlterOrderWithRespectTo` sets `"order_with_respect_to"`, an option that gives a model a column none of its declared fields stands for: `Options._prepare` adds to the class an `OrderWrt` named `"_order"`, an integer that may not be null, and `ModelState.from_model` leaves that field out (`django/db/models/options.py:Options._prepare`). The database half compares the two historical models (`django/db/migrations/operations/models.py:AlterOrderWithRespectTo.database_forwards`). Where only the from-state's has the option, it hands that model's `"_order"` to `BaseDatabaseSchemaEditor.remove_field`. Where only the to-state's has it, it gives that model's `"_order"` a default of 0 if it has none and hands it to `BaseDatabaseSchemaEditor.add_field`: the rows already there need a value in the column, and the editor writes the field's default into them ([The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md#defaults-written-once-then-dropped)). Where both have it, on different fields, nothing is sent, the comment saying the column is left untouched as the change is likely a rename.

### `AlterModelOptions` and `AlterModelManagers`

`AlterModelOptions` and `AlterModelManagers` change the state and no database: in both, `database_forwards` and `database_backwards` are empty. `AlterModelOptions` is for options that change no table, and its docstring gives one reason such a change is a migration at all: Python code in migrations may still need them (`django/db/migrations/operations/models.py:AlterModelOptions`). Another is the autodetector, which compares the options that `AlterModelOptions.ALTER_OPTION_KEYS` lists between the state the migration files make and the one read off the models: a change to one of them that no operation had put into the first would be found again at every makemigrations ([The autodetector: comparing two project states](autodetector.md)). The list is `"base_manager_name"`, `"default_manager_name"`, `"default_related_name"`, `"get_latest_by"`, `"managed"`, `"ordering"`, `"permissions"`, `"default_permissions"`, `"select_on_save"`, `"verbose_name"` and `"verbose_name_plural"`. The operation's dictionary is all of them as they are to be: given the list, `alter_model_options` removes from the model state each listed option that the dictionary lacks. Crane, a model the recording made with `"ordering"`, is here given `"verbose_name"` and nothing else:

```text recording=migrations
migrations.AlterModelOptions('crane', {'verbose_name': 'crane'}).state_forwards('yard', state)
  ProjectState.alter_model_options(app_label='yard', model_name='crane', options={'verbose_name': 'crane'}, option_keys=['base_manager_name', 'default_manager_name', and 9 more])
  changed: state.models['yard', 'crane'].options has no 'ordering' any more (it was ['id'])
  changed: state.models['yard', 'crane'].options has gained 'verbose_name': 'crane'
```

> **Trap.** `"managed"` is on the list: an `AlterModelOptions` that makes a model managed makes no table.

`AlterModelManagers` has `ProjectState.alter_model_managers` put its list in place of the model state's managers. They are the managers a historical model is rendered with ([Historical models: `StateApps` and rendering](historical-models.md)); which of a model's managers reach a migration is in [Managers](../models/managers.md).
