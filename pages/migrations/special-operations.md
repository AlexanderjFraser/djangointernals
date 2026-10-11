---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `RunPython`, `RunSQL` and `SeparateDatabaseAndState`

`RunPython` calls a function with the historical models and the schema editor, `RunSQL` sends SQL of the author's own, and `SeparateDatabaseAndState` gives the project state one list of operations and the database another. They are the classes of `django/db/migrations/operations/special.py`.

Each of the other operations in `django.db.migrations` stands for one change to the models. Its state half makes the change in the project state, its database half makes it in a database if a database holds it at all, and the two stay in step ([Operations: the base class and its two halves](operations.md)). These three are for what cannot be read off two project states: rows to change, a statement the schema editor would not write, a change meant for the state alone or for the database alone. The autodetector makes none of them (`django/db/migrations/autodetector.py`).

The example is the fourth migration of yard, the repair yard of the example project, filled in by hand. The third gave the model Repair a column `"foreman"` holding `"not recorded"` in the rows there were; the fourth puts a name in those rows and a sentence in the empty notes. Below are one of its two functions and its operations. In a recording a line that begins with a bar is a line of a file, `python manage.py` begins a command line and `stdout |` a line it printed, and the other lines are calls, nested as they were made and only those a passage is about, with what ran between them left out: square brackets hold an operation's description, or the migration; a class in parentheses is the one that declares the method; an arrow is followed by what a call returned; and `SQL` begins a statement as Django handed it to its cursor.

```text recording=migrations
| def name_foremen(apps, schema_editor):
|     """Every repair whose foreman was not recorded is put down to the yard's master."""
|     Repair = apps.get_model("yard", "Repair")
|     Repair.objects.using(schema_editor.connection.alias).filter(foreman="not recorded").update(foreman="Yard master")
...
|     operations = [
|         migrations.RunPython(name_foremen, reverse_code=forget_foremen),
|         migrations.RunSQL(
|             sql="UPDATE yard_repair SET notes = 'No notes were kept.' WHERE notes = ''",
|             reverse_sql="UPDATE yard_repair SET notes = '' WHERE notes = 'No notes were kept.'",
|         ),
|     ]
```

## `RunPython`: a function and the historical models

`RunPython.database_forwards` calls the function the operation was made with, with two arguments. The first is the registry of the from-state, which is the project state as everything before this operation left it; the second is the schema editor (`django/db/migrations/operations/special.py:RunPython.database_forwards`). So `Apps.get_model`, called on the first, returns a historical model: the fields the model had at this point of the history, and none of the methods written in the model's class ([Historical models: `StateApps` and rendering](historical-models.md)). A query through a historical model goes to `"default"` unless a router or the function says otherwise, not to the database being migrated, so name_foremen takes the alias from the schema editor (`docs/ref/migration-operations.txt`).

Here migrate applies the migration on SQLite.

```text recording=migrations
Migration.apply  [yard.0004_name_the_foremen]
  RunPython.state_forwards  [Raw Python operation]
  RunPython.database_forwards  [Raw Python operation]
    ProjectState.clear_delayed_apps_cache
    ConnectionRouter.allow_migrate(db='default', app_label='yard')  ->  True
    name_foremen(apps=a state's registry, schema_editor=the schema editor)
      StateApps.get_model(app_label='yard', model_name='Repair')  (Apps.get_model)  ->  the historical model yard.Repair
      SQL UPDATE "yard_repair" SET "foreman" = %s WHERE "yard_repair"."foreman" = %s with params ('Yard master', 'not recorded')
```

`RunPython.state_forwards` does nothing; a state change is added by combining the operation with `SeparateDatabaseAndState`. Forwards, the database half begins with `ProjectState.clear_delayed_apps_cache`: a schema operation before it may have rendered again only the models nearest its change and marked the state delayed, and the function may ask for any model (`django/db/migrations/state.py:ProjectState.clear_delayed_apps_cache`; [Historical models: `StateApps` and rendering](historical-models.md)).

Then the router is asked. Where an operation on a model asks it, it asks about that model, and a router is handed the model and its name (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`, `django/db/utils.py:ConnectionRouter.allow_migrate_model`). `RunPython` has no model: it calls `ConnectionRouter.allow_migrate` with the alias, the migration's application label and its own `hints` as keyword arguments, so a router's `allow_migrate` gets no model's name unless `hints` holds one ([Routing between databases: `ConnectionRouter`](../backends/routers.md)). A false answer skips the function and raises nothing.

### Backwards: `reverse_code` and `noop`

`RunPython.reversible` is true when a function was given as `reverse_code`, and `RunPython.database_backwards` calls that function with the registry of its own from-state, which is the state as the operation left it, and the schema editor. Where an operation in a migration's list has `reversible` false, `Migration.unapply` raises `IrreversibleError` (`django/db/migrations/migration.py:Migration.unapply`; [A migration: its operations, its dependencies and how it is applied](migration.md)). `RunPython.noop` does nothing: as `reverse_code` it makes an operation reversible, and as the code one that acts only backwards.

### `atomic`: an atomic block of its own

`RunPython` sets `Operation.atomic`, `False` on the class, on its instance: to its argument of that name, or to `None` without one. Where the schema editor has not made the migration one transaction, because the backend cannot roll back DDL (`BaseDatabaseFeatures.can_rollback_ddl`) or the migration has `atomic = False`, `Migration.apply` and `Migration.unapply` give the database half an atomic block of its own with `atomic=True`, none with `atomic=False`, and with `None` one where the migration is atomic (`django/db/migrations/migration.py:Migration.apply`; [A migration: its operations, its dependencies and how it is applied](migration.md)). `atomic=False` is for a function that uses the schema editor on a backend that cannot roll back DDL, where `BaseDatabaseSchemaEditor.execute` raises `TransactionManagementError` inside an atomic block. `RunSQL` takes no such argument and gets no block of its own.

### `reduces_to_sql`

`RunPython.reduces_to_sql` is `False`, and no other class in Django sets it so. A migration asked to collect its statements forwards, as sqlmigrate asks, writes a comment in place of such an operation and runs neither of its halves (`django/db/migrations/migration.py:Migration.apply`); backwards, `Migration.unapply` passes over its database half the same way.

```text recording=migrations
python manage.py sqlmigrate yard 0004
  stdout | BEGIN;
  stdout | --
  stdout | -- Raw Python operation
  stdout | --
  stdout | -- THIS OPERATION CANNOT BE WRITTEN AS SQL
  stdout | --
  stdout | -- Raw SQL operation
  stdout | --
  stdout | UPDATE yard_repair SET notes = 'No notes were kept.' WHERE notes = '';
  stdout | COMMIT;
```

### `elidable`

`elidable=True`, which `RunSQL` takes too, sets `Operation.elidable`. Of two operations one of which is elidable, `Operation.reduce` answers with the other alone, and that is how squashing drops one (`django/db/migrations/operations/base.py:Operation.reduce`; [Squashed migrations: `replaces` and the squashmigrations command](squashing.md)).

## `RunSQL`: statements of the author's own

`RunSQL` asks the router as `RunPython` does, by alias, application label and `hints`, and hands `sql`, or backwards `reverse_sql`, to `RunSQL._run_sql` (`django/db/migrations/operations/special.py:RunSQL._run_sql`). A string goes to the backend's `BaseDatabaseOperations.prepare_sql_script`: the base has sqlparse split the string and strip its comments, and PostgreSQL's returns it whole (`django/db/backends/base/operations.py:BaseDatabaseOperations.prepare_sql_script`, `django/db/backends/postgresql/operations.py:DatabaseOperations.prepare_sql_script`). A list or a tuple is taken an item at a time, unsplit: a statement, or a pair of a statement and its parameters. `RunSQL.noop`, the empty string, sends nothing; as `reverse_sql`, which is `None` unless given, it makes `RunSQL.reversible` true.

Each statement goes to `BaseDatabaseSchemaEditor.execute` and none straight to a cursor, so an editor that is collecting statements writes it down with its parameters quoted into it, and sqlmigrate prints it (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.execute`).

`RunSQL.state_forwards` runs the state halves of the operations given as `state_operations`, whose database halves never run: they tell the state what the SQL did. If a column is added by an `"ALTER TABLE"` of the author's own and no `AddField` says so, the state the migration files make lacks the field, and the next makemigrations writes an `AddField` for a column that exists (`docs/ref/migration-operations.txt`).

## `SeparateDatabaseAndState`: two lists of operations

`SeparateDatabaseAndState` takes `database_operations` and `state_operations`, so that operations that do not support a state change can have one applied, and operations can affect the state and not the database (`django/db/migrations/operations/special.py:SeparateDatabaseAndState`). The model Repair has gained an index; yard's fifth migration, written by hand, makes the index with a statement of its own and tells the state with an `AddIndex`, and makemigrations then finds nothing to do.

```text recording=migrations
|     operations = [
|         migrations.SeparateDatabaseAndState(
|             database_operations=[
|                 migrations.RunSQL(
|                     sql='CREATE INDEX "repair_by_foreman" ON "yard_repair" ("foreman")',
|                     reverse_sql='DROP INDEX "repair_by_foreman"',
|                 ),
|             ],
|             state_operations=[
|                 migrations.AddIndex("repair", models.Index(fields=["foreman"], name="repair_by_foreman")),
|             ],
|         ),
|     ]
python manage.py makemigrations yard --check
  stdout | No changes detected in app 'yard'
```

`SeparateDatabaseAndState.state_forwards` runs the state halves of the state operations. The database half runs the database operations, each between a from-state and a to-state. The to-state the migration hands over was made by the other list, so `SeparateDatabaseAndState.database_forwards` never reads it and makes its own: from the from-state it was given, it clones the state, runs the database operation's own state half on the clone, and calls its database half between the two; the clone is the next operation's from-state. Where migrate applies yard's fifth migration, state is the project state the executor carries, and the clones are numbered as they were made.

```text recording=migrations
Migration.apply(state, the schema editor)  [yard.0005_repair_by_foreman]
  ProjectState.clone  ->  clone 1, a ProjectState of 13 model states, its registry rendered
  SeparateDatabaseAndState.state_forwards(state=state)  [Custom state/database change combination]
    AddIndex.state_forwards(state=state)  [Create index repair_by_foreman on field(s) foreman of model repair]
...
  SeparateDatabaseAndState.database_forwards(from_state=clone 1, to_state=state)  [Custom state/database change combination]
    ProjectState.clone  ->  clone 2, a ProjectState of 13 model states, its registry rendered
    RunSQL.state_forwards(state=clone 2)  [Raw SQL operation]
    RunSQL.database_forwards(from_state=clone 1, to_state=clone 2)  [Raw SQL operation]
      ConnectionRouter.allow_migrate(db='default', app_label='yard')  ->  True
      SQL CREATE INDEX "repair_by_foreman" ON "yard_repair" ("foreman")
```

`SeparateDatabaseAndState.database_backwards` builds the same chain, forwards, from its to-state, the state before the operation, and then calls `database_backwards` on the database operations in reverse order, each between the state after it and the state before it.

> **Trap.** A migration reads `reversible`, `reduces_to_sql` and `atomic` on the operations of its own list, and `SeparateDatabaseAndState` leaves all three as the base class has them. So sqlmigrate, a command meant to print, calls the function of a `RunPython` among its database operations, and what the function writes through a model is committed: only what goes through the schema editor's `execute` is collected and not sent (`django/db/migrations/loader.py:MigrationLoader.collect_sql`). Such a `RunPython` also gets no atomic block of its own, and without a reverse raises `NotImplementedError` in the middle of an unapply.
