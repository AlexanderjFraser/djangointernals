---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Rewriting migrations: `--update`, squashmigrations and optimizemigration

Three commands work on migrations already written: makemigrations `--update` folds the new changes into each application's leaf migration, squashmigrations writes one migration that replaces a run of others, and optimizemigration folds the operations of one migration again.

In the recordings here, from a running Django, `python manage.py` begins a command line, `stdout |` a line it printed, a bar a line of a file it wrote, and `exit status` the status the command ended with; a line of three dots stands for lines left out.

## `--update`: the leaf migration written again

With `--update` the changes are folded into each application's leaf migration by `Command.write_to_last_migration_files` (`django/core/management/commands/makemigrations.py:Command.write_to_last_migration_files`). Here yard.0003_repair_foreman, which adds Repair.foreman with a default typed in answer to the questioner, was written and not yet applied, and the field was then made longer in the models:

```text recording=migrations
python manage.py makemigrations yard --update
  stdout | Migrations for 'yard':
  stdout |   harbour/yard/migrations/0003_repair_foreman_updated.py
  stdout |     + Add field foreman to repair
  stdout | Deleted harbour/yard/migrations/0003_repair_foreman.py
...
|     operations = [
|         migrations.AddField(
|             model_name='repair',
|             name='foreman',
|             field=models.CharField(max_length=80),
|             preserve_default=False,
|         ),
|     ]
```

The method makes a loader of its own, with the connection `"default"`: the first loader counts nothing as applied, and one of the refusals turns on what is. For each application with changes it takes the leaf node of that loader's graph and raises `CommandError` if there is none, if the leaf is a replacing migration, if it is applied on `"default"` (no other database is asked), or if a migration on disk names it among its dependencies.

It then appends to the leaf's operations those of each new migration, and to its dependencies those of theirs whose label is not the application's own: another application's migration, or `("__setting__", "AUTH_USER_MODEL")` for a relation to the user model. The whole list of operations is put through `MigrationOptimizer.optimize` ([The optimizer: `MigrationOptimizer` and `reduce`](optimizer.md)). In the recording the optimizer made one `AddField` of the old `AddField` and the new `AlterField`, and the default that was typed is not in it: applied, the migration has no value for the rows the table has, and on SQLite it fails if there is one.

The new name is the first four characters of the old, an underscore, and the value of `--name` or else `Migration.suggest_name` of the rewritten migration (`django/db/migrations/migration.py:Migration.suggest_name`); where that is the old name again, `"_updated"` is added to it, so the name always changes, and the new file is never the one about to be removed. `Command.write_migration_files` is then given the rewritten migrations and each old file's path. When a new file has been written the old one is removed, unless the writer set `MigrationWriter.needs_manual_porting`, having met a function that must be copied by hand out of a migration module: then the old file is kept, and a warning says so.

## The squashmigrations command

squashmigrations takes an application's label and the name of the last migration to squash, and optionally, before that, the name of the first (`django/core/management/commands/squashmigrations.py:Command.handle`). Its loader has no connection, so for it no migration is applied. `MigrationLoader.get_migration_by_prefix` finds a named migration by the beginning of its name, among those on disk, and the run is the application's part of `MigrationGraph.forwards_plan` of the last one, cut to begin at the first if one was named.

```text recording=migrations
python manage.py squashmigrations yard 0007
  stdout | Will squash the following migrations:
  stdout |  - 0001_initial
...
  stdout |  - 0007_merge
...
  stdout | Optimizing...
  stdout |   Optimized from 12 operations to 7 operations.
  stdout | Created new squashed migration harbour/yard/migrations/0001_squashed_0007_merge.py
...
  stdout | Manual porting required
```

The operations of the run are put end to end in one list, and the command examines none of them: it asks nothing of a `RunPython` or a `RunSQL`, such as whether it can be reversed. Of the dependencies it keeps those on other applications and, from the first migration of the run, those on its own; one made by `swappable_dependency`, a dependency on the application of the model a setting names, is kept whichever application that is, and the new file has the call again where it was made from the present value of `AUTH_USER_MODEL`. Unless `--no-optimize` was given the list then goes through the optimizer ([The optimizer: `MigrationOptimizer` and `reduce`](optimizer.md)).

The new migration is an instance of a subclass of `Migration` (`django/db/migrations/migration.py:Migration`) made on the spot, with those dependencies and operations and with `Migration.replaces` set to the keys of the run, in its order (`django/core/management/commands/squashmigrations.py:Command.handle`). Squashed from the start it is named `"0001_squashed_"` and the last migration's name, and its `Migration.initial` is set to `True`; squashed from a named first migration it has the first's name, `"_squashed_"` and the last's, and `initial` is left alone. With `--squashed-name` the name is the number, an underscore and the option's value. `MigrationWriter` gives the text and the path, and the command writes the file, which it will not put in the place of an existing one ([Writing a migration file: `MigrationWriter`](writer.md)).

```text recording=migrations
| # Functions from the following migrations need manual copying.
| # Move them and any dependencies into this file, then update the
| # RunPython operations to refer to the local versions:
| # harbour.yard.migrations.0004_name_the_foremen
|
| class Migration(migrations.Migration):
|
|     replaces = [('yard', '0001_initial'), ('yard', '0002_rename_started_repair_begun_dock_metres_and_more'), ('yard', '0003_repair_foreman'), ('yard', '0004_name_the_foremen'), ('yard', '0005_repair_by_foreman'), ('yard', '0006_long_dock'), ('yard', '0006_dock_covered'), ('yard', '0007_merge')]
|
|     initial = True
...
|         migrations.RunPython(
|             code=harbour.yard.migrations.0004_name_the_foremen.name_foremen,
|             reverse_code=harbour.yard.migrations.0004_name_the_foremen.forget_foremen,
|         ),
```

A function is written by its dotted path, with an import of its module ([Serializing values: `serializer_factory` and `deconstruct`](serializer.md)). `MigrationWriter.as_string` swaps each import of a module that has a part beginning with a digit, as the migration modules Django names have, for a line of a comment above the class, and sets `MigrationWriter.needs_manual_porting`, on which the command, above verbosity 0, says that functions must be copied by hand (`django/db/migrations/writer.py:MigrationWriter.as_string`). The path stays in the operation, and the file is not Python until the functions are copied in and named directly, as the recording then did.

## The optimizemigration command

optimizemigration takes an application's label and a migration's name, or the beginning of one (`django/core/management/commands/optimizemigration.py:Command.handle`, `django/db/migrations/loader.py:MigrationLoader.get_migration_by_prefix`). It raises `CommandError` for a label no installed application has, for an unmigrated application, and for a name that no migration of the application, or more than one, begins with. Its loader has no connection, so no database is asked whether the migration is applied ([Finding migrations: `MigrationLoader`](../migrations/loader.md)).

It runs the optimizer on the migration's operations and compares the two lists by length. Equal lengths end the command, even where the order changed, as with an `AlterField` and a `RenameField`. Otherwise it prints both lengths, unless `--verbosity` is 0, and with `--check` exits there with status 1, having written nothing; without, it writes over the migration's file what a `MigrationWriter` makes of it with its new operations. Here the file is yard.0002_crane, written for the purpose with three operations that fold into one.

```text recording=migrations
python manage.py optimizemigration yard 0002_crane --check
  stdout | Optimizing from 3 operations to 1 operations.
  exit status 1
python manage.py optimizemigration yard 0002_crane
  stdout | Optimizing from 3 operations to 1 operations.
  stdout | Optimized migration harbour/yard/migrations/0002_crane.py
```

Where the writer has set `MigrationWriter.needs_manual_porting`, for a function that must be copied by hand out of a migration file ([Writing a migration file: `MigrationWriter`](writer.md)), the command leaves the file as it is: for a migration that itself has `replaces` it raises `CommandError`; for any other it makes a migration class with the original's `dependencies`, the new operations and a `replaces` naming the original, calls it by the original's name with `"_optimized"` after it, and writes that beside the original.
