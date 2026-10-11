---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What has been applied: `MigrationRecorder` and the table `"django_migrations"`

`MigrationRecorder` keeps, in the table `"django_migrations"` of one database, a row for each migration applied there. It makes the table itself, through a model the main registry never holds; `MigrationRecorder.applied_migrations`, `MigrationRecorder.record_applied` and `MigrationRecorder.record_unapplied` read and change what is applied.

A database's schema does not say which migrations made it: an operation that changes only rows leaves no mark on it. Django writes down what it has run, in the database it ran it on. A migration is **applied** on a database when the table there has its row. The docstring of `MigrationRecorder` names the difficulty: the table is itself used in creating models' tables, so it is the one thing that cannot be done through migrations (`django/db/migrations/recorder.py:MigrationRecorder`). The **recorder**, an instance made for one connection, makes the table by hand and queries it through a model of its own.

## The model behind the table

`MigrationRecorder.Migration` is a `classproperty`: its first read defines a model class and keeps it in `MigrationRecorder._migration_class`, and every later read returns the class kept (`django/db/migrations/recorder.py:MigrationRecorder.Migration`). Its docstring says why it waits: to avoid `AppRegistryNotReady` when an installed application imports `MigrationRecorder`. A model's class statement asks the main registry which application its module is in, and the registry refuses until the applications are loaded (`django/apps/registry.py:Apps.get_containing_app_config`).

The model's `Meta` names the table, the label `"migrations"` and a registry of its own, `apps = Apps()`. A model registers in the registry its options name ([The registry and its models](../startup/registry.md#registries-other-than-the-main-one)), so the main registry never has this one, and makemigrations, which reads the models off the main registry, makes no migration for it (`django/db/migrations/state.py:ProjectState.from_apps`). Beside its automatic primary key the model has three fields: `"app"` and `"name"`, character fields of 255 characters for a migration's key, which is its application's label and its name, and `"applied"`, a date and time that defaults to the moment the row is made, taken in Python.

## Finding the table, and making it

A recorder holds its connection and a flag, `MigrationRecorder._has_table`, false at first. `MigrationRecorder.has_table` says yes at once when the flag is set; otherwise it asks the connection's introspection for the database's table names and sets the flag to whether `"django_migrations"` is among them ([Introspection: reading the schema back](../backends/introspection.md)). A yes is thus remembered for the recorder's life, and a no is asked again each time (`django/db/migrations/recorder.py:MigrationRecorder.has_table`).

`MigrationRecorder.ensure_schema` returns if `has_table` says yes, whatever the table's columns: its comment gives the reason, that the table's schema has never been changed in Django's code. Otherwise it opens a schema editor and hands the model to `BaseDatabaseSchemaEditor.create_model`, with no operation, no project state and no question to the router ([The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md)). A `DatabaseError` from that is raised again as `MigrationSchemaMissing`, itself a `DatabaseError`, with the database's message in its own (`django/db/migrations/recorder.py:MigrationRecorder.ensure_schema`).

`ensure_schema` is the first thing `MigrationRecorder.record_applied` and `MigrationRecorder.record_unapplied` do, and `MigrationExecutor.migrate` calls it before carrying out a plan, unless the plan it is given is empty: its comment says the table must be there to record what is applied, but is not to be made when there is nothing to apply (`django/db/migrations/executor.py:MigrationExecutor.migrate`).

Recorded from a running Django, on a recorder made by hand for an empty SQLite database, `"archive"`, which each line names: the lines are calls, nested as they were made, and only those the passage is about, with what ran between them left out; where a class follows a call in parentheses, the first name is the class of the object and the one in parentheses declares the method that ran; a line beginning `SQL` is a statement as Django handed it to its cursor.

```text recording=migrations
MigrationRecorder.ensure_schema  (on "archive")
  DatabaseSchemaEditor.create_model(the recorder's model)  (BaseDatabaseSchemaEditor.create_model)  (on "archive")
    SQL (on "archive") CREATE TABLE "django_migrations" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "app" varchar(255) NOT NULL, "name" varchar(255) NOT NULL, "applied" datetime NOT NULL)
```

## The rows

Rows are read and written through `MigrationRecorder.migration_qs`, a queryset of the model bound to the connection's alias with `QuerySet.using`, so no router is asked where to read or write. `MigrationRecorder.applied_migrations` returns a dictionary from each row's key to the row, an instance of the model; where there is no table it returns an empty one and makes none (`django/db/migrations/recorder.py:MigrationRecorder.applied_migrations`). `MigrationRecorder.record_applied` creates a row from a label and a name, `MigrationRecorder.record_unapplied` deletes every row that has them, and `MigrationRecorder.flush`, which only Django's tests call, deletes all rows.

A row written and then deleted, on the recorder for `"archive"`:

```text recording=migrations
MigrationRecorder.record_applied(app='yard', name='0001_initial')  (on "archive")
  SQL (on "archive") INSERT INTO "django_migrations" ("app", "name", "applied") VALUES (%s, %s, %s) RETURNING "django_migrations"."id" with params ('yard', '0001_initial', '(the date and the time)')
...
MigrationRecorder.record_unapplied(app='yard', name='0001_initial')  (on "archive")
  SQL (on "archive") DELETE FROM "django_migrations" WHERE ("django_migrations"."app" = %s AND "django_migrations"."name" = %s) with params ('yard', '0001_initial')
```

## Who writes a row, and who reads the table

`MigrationExecutor.record_migration` writes the row of a key with `MigrationRecorder.record_applied`, or deletes it with `MigrationRecorder.record_unapplied` (`django/db/migrations/executor.py:MigrationExecutor.record_migration`). `MigrationExecutor.apply_migration` and `MigrationExecutor.unapply_migration` call it for the migration they are given, and with `fake=True` call it without running an operation: a faked migration changes `"django_migrations"` and nothing else ([Applying a plan: `MigrationExecutor`](executor.md)). The other caller of `record_unapplied` is migrate with `--prune`, for rows of the application it is given whose migrations are not on disk ([The migrate command, showmigrations and sqlmigrate](migrate.md)) (`django/core/management/commands/migrate.py:Command.handle`).

`MigrationLoader.build_graph` makes a `MigrationRecorder` for the loader's connection and keeps the dictionary its `MigrationRecorder.applied_migrations` returns as `MigrationLoader.applied_migrations`; a loader with no connection keeps an empty one. `MigrationLoader.check_consistent_history` reads the table for itself, on the connection it is given, to hold the rows against the graph ([Finding migrations: `MigrationLoader`](loader.md)). showmigrations reads it too, for its list (`django/core/management/commands/showmigrations.py:Command.show_list`).

A migration that replaces others (a squashed one) is the exception on both sides: `record_migration` first writes or deletes the rows of those it replaces, and `MigrationExecutor.check_replacements` writes that migration's own row, where it has none, once all it replaces is applied (`django/db/migrations/executor.py:MigrationExecutor.check_replacements`). And the loader may count it applied by their rows, whatever row it has itself, so the loader's dictionary is what counts as applied, not always what has a row; [Squashed migrations: `replaces` and the squashmigrations command](squashing.md) has that.

## What a row does not say

Django's readers use the keys of the dictionary `MigrationRecorder.applied_migrations` returns, and a row's time in one place: showmigrations, in its list, prints it from `--verbosity 2` up, but not for a migration that replaces others (`django/core/management/commands/showmigrations.py:Command.show_list`). The table has nothing of the operations a migration had when it ran, no checksum of its file, no project state: nothing compares a migration file with its row, and a migration whose file is edited after it was applied goes on being applied, under the same key. Nor does anything in the table keep a label and a name to one row: they are a key only in that dictionary.

Each database that migrations are applied to has a table of its own; what that comes to where a router keeps models from a database is in [The migrate command, showmigrations and sqlmigrate](migrate.md).
