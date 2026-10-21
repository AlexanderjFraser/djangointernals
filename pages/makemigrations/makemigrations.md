---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The makemigrations command

The makemigrations command writes new migration files. `Command.handle` makes a `MigrationLoader` with no connection, has a `MigrationAutodetector` compare the project state the loaded migrations describe with the one read off the models, and gives each migration that comes back to a `MigrationWriter`. `--merge`, `--empty` and `--update` each leave that road at one point; `--dry-run`, `--check` and `--scriptable` change what is written, asked and printed along it (`django/core/management/commands/makemigrations.py:Command.handle`).

The comparison is the autodetector's, the questions are the questioner's and a file's text is the writer's. `handle` owns the order, the refusals, what is printed and the files; how any command is found, parsed and run is in [Management commands](../commands.md). It begins with its arguments: a `--name` that is not empty and not a valid Python identifier is a `CommandError`, `--check` turns on `--dry-run`, and a label that is no application's is reported on standard error and ends the command with status 2 before anything is loaded.

## The loader, and each database's history

`Command.handle` makes its loader as `MigrationLoader(None, ignore_no_migrations=True)` (`django/core/management/commands/makemigrations.py:Command.handle`). With no connection the loader asks no database what has been applied and counts nothing as applied (`django/db/migrations/loader.py:MigrationLoader.build_graph`). A comment gives the purpose, that replaced migrations are not to be resolved from a database: with none applied, every replacing migration (a squashed one) that no other replaces stands in the graph in place of those it replaces, whatever a developer's database has had ([Replacing migrations: `replaces`](../migrations/replacing.md)). `ignore_no_migrations=True` quiets two errors of [Finding migrations: `MigrationLoader`](../migrations/loader.md): an application for which `MIGRATION_MODULES` names a module that is not there is counted as unmigrated, and a dependency on `"__first__"` or `"__latest__"` of a migrated application with no migration yet is dropped (`django/db/migrations/loader.py:MigrationLoader.load_disk`, `django/db/migrations/loader.py:MigrationLoader.check_key`).

The history is checked all the same, on real connections. The aliases are all of `DATABASES` where `DATABASE_ROUTERS` is not empty and `"default"` alone where it is, in sorted order. One is passed over if its engine is the dummy backend, which a project with no database configured has, or if the router lets no model of any installed application be migrated there. On the others `MigrationLoader.check_consistent_history` reads the database's table and raises `InconsistentMigrationHistory`, which ends the command, if a migration applied there, and in the loader's graph, has a parent, a migration it depends on, that is not applied there (`django/db/migrations/loader.py:MigrationLoader.check_consistent_history`). An unapplied parent is let pass where it is a replacing migration each of whose replaced migrations is applied or is, in turn, such a replacing migration (`django/db/migrations/loader.py:MigrationLoader.all_replaced_applied`). An `OperationalError`, as from a database that cannot be reached, becomes a `RuntimeWarning`, and the command goes on.

> **Trap.** `handle` gives `ConnectionRouter.allow_migrate` the hint `model_name` as the model's `Options.object_name`, the class's name with its capitals, where `ConnectionRouter.allow_migrate_model` and `MigrationExecutor.detect_soft_applied`, its other callers that give the hint, give the lower-case `Options.model_name` (`django/db/models/options.py:Options.contribute_to_class`). A router that looks for `"logbook"` is asked here about `"Logbook"`. If it answers `None` to a name it does not know, the history is checked even of a database it keeps every model out of: with no answer from a router, `allow_migrate` returns `True` (`django/db/utils.py:ConnectionRouter.allow_migrate`; [Routing between databases: `ConnectionRouter`](../connections/routers.md)).

## Two leaf nodes, and `--merge`

For makemigrations, `MigrationLoader.detect_conflicts` gives, for each application with more than one leaf node, those nodes' names (`django/db/migrations/loader.py:MigrationLoader.detect_conflicts`); where labels were given on its command line, the command drops other applications' conflicts. If any is left and `--merge` was not given, the command stops with a `CommandError` that names them: the docstring of `MigrationGraph.leaf_nodes` calls more than one leaf in an application an error, usually the result of a merge in version control, that needs the user (`django/db/migrations/graph.py:MigrationGraph.leaf_nodes`). With `--merge` and none left, it logs that there is nothing to merge and returns (`django/core/management/commands/makemigrations.py:Command.handle`).

With `--merge`, `Command.handle_merge` takes each application in conflict in turn (`django/core/management/commands/makemigrations.py:Command.handle_merge`). For each leaf it works out an **ancestry** within the application: the nodes of `MigrationGraph.forwards_plan` for the leaf, less those of other applications. It reads the ancestries side by side from the start and counts how far they hold the same node: those are the **common ancestors**, and with none it raises `ValueError`. What follows them in a leaf's ancestry is its **branch**, and the operations of the branch's migrations, in order, are printed under the leaf's name at verbosity 1 or more.

Nothing tests whether the branches can be merged: `InteractiveMigrationQuestioner.ask_merge` puts the question to the user, and its text says what the answer rests on; with `--noinput` the questioner is a plain `MigrationQuestioner` whose default for `"ask_merge"` is yes, and nothing is asked ([The questioner: `MigrationQuestioner`](questioner.md)).

In harbour, yard has two migrations numbered 0006, yard.0006_dock_covered and yard.0006_long_dock, both depending on yard.0005_repair_by_foreman, so each branch is its leaf alone. In the recordings here a line beginning `python manage.py` is a command line; under it `stdout |` or `stderr |` begins a line the command printed on that stream, `stdin  |` a line typed to it and a bar a line of a file it wrote; only the lines a passage is about are quoted.

```text recording=migrations
python manage.py makemigrations --merge --name merge
  stdout | Merging yard
  stdout |   Branch 0006_dock_covered
  stdout |     + Add field covered to dock
  stdout |   Branch 0006_long_dock
  stdout |     s Raw SQL operation
  stdout |
  stdout | Merging will only work if the operations printed above do not conflict
  stdout | with each other (working on different fields or models)
  stdout | Should these migration branches be merged? [y/N]
  stdin  | y
  stdout |
  stdout | Created new merge migration harbour/yard/migrations/0007_merge.py
```

On a yes the command makes the migration itself. Its number is one more than the largest that `MigrationAutodetector.parse_number` reads from the leaves' names, or 2 where it reads none. After the number comes the value of `--name`, or else `"merge"` followed by the leaves' names, sorted and joined with underscores, or by the date and the time where the joined names are longer than 47 characters. Unless this is a dry run, a `MigrationWriter`'s text for it is written to the writer's path. Having no operations, the migration changes no state and no database: it gives the application one leaf node again.

```text figure=the-merge
an arrow runs from a migration to one it depends on

yard.0005_repair_by_foreman  <--+--  yard.0006_dock_covered: + Add field covered to dock  <--+--  yard.0007_merge
  the last common ancestor      |                                                            |      no operations
                                +--  yard.0006_long_dock: s Raw SQL operation             <--+
```

*Yard's two leaf nodes both depend on yard.0005_repair_by_foreman, the last node their ancestries share; yard.0007_merge has no operations and depends on both.*

## The two states and `changes`

Without `--merge`, `Command.handle` next chooses a questioner (`django/core/management/commands/makemigrations.py:Command.handle`): an `InteractiveMigrationQuestioner` unless `--noinput` was given, and then a `NonInteractiveMigrationQuestioner`. Each is given the labels and whether this is a dry run. The autodetector is made of the from-state, `MigrationLoader.project_state` for the whole graph, the to-state, `ProjectState.from_apps` of the main registry, and the questioner.

`MigrationAutodetector.changes` is called with the loader's graph, the value of `--name`, and the labels twice, or `None` twice where there were none (`django/db/migrations/autodetector.py:MigrationAutodetector.changes`). As the applications to trim to, the labels cut the result down to those applications and the ones their new migrations depend on. What returns is a dictionary from a label to that application's new migrations, numbered, named and given their dependencies ([From operations to migrations: dependencies, order and names](dependencies.md)). Where it is empty the command logs, at verbosity 1 or more, that no changes were detected, and returns.

As the applications to convert, the labels matter to an application with no `migrations` package: a plain makemigrations makes nothing for it, and one given its label makes its first migration. The loader counts such an application as **unmigrated**, and the from-state is given the unmigrated applications as its `ProjectState.real_apps` (`django/db/migrations/loader.py:MigrationLoader.project_state`): the autodetector leaves their models out of the comparison unless the label is one of those to convert ([The autodetector: comparing two project states](autodetector.md)). A graph with no leaf node gives a from-state with no `real_apps`, so in a project with no migration at all every application's models are compared (`django/db/migrations/graph.py:MigrationGraph.make_state`). `MigrationAutodetector.arrange_for_graph` then asks `MigrationQuestioner.ask_initial` of each application that has new migrations and no leaf node, and drops them on a no: yes for a label that was given or a package whose only Python file is `"__init__.py"`, no for an application with no package ([The questioner: `MigrationQuestioner`](questioner.md)). So where no application has a migrations package yet, a plain makemigrations finds no changes.

`--empty` leaves the comparison out. It requires a label, and for each it makes a `Migration` with no operations, puts them in a dictionary of the shape `changes` returns, and hands that to `MigrationAutodetector.arrange_for_graph` for a number, a name and a dependency on the application's leaf node, where it has one (`django/db/migrations/autodetector.py:MigrationAutodetector.arrange_for_graph`, `django/db/migrations/migration.py:Migration`). The files are written like any others.

`--check` is `--dry-run` with a verdict on the comparison: where `changes` returns migrations, the command exits with status 1 after its dry run of them; where it returns none the status is 0. `--empty` and `--merge` return before that exit.

## Writing the files: `write_migration_files`

`Command.write_migration_files` takes a dictionary from a label to that application's migrations, an application at a time (`django/core/management/commands/makemigrations.py:Command.write_migration_files`). For each migration it makes a `MigrationWriter`, one that writes no header comment under `--no-header`, and, at verbosity 1 or more, logs the file's path and a line for each operation: `Operation.formatted_description`, the sign of its `Operation.category`, or `"?"` where it has none, and what its `Operation.describe` returns (`django/db/migrations/operations/base.py:Operation.formatted_description`). Unless this is a dry run it then makes the path's directory and an empty `"__init__.py"` there if either is missing, has the writer make the text, and writes it to the path ([Writing a migration file: `MigrationWriter`](writer.md)). At the end, as after a merge, `run_formatters` runs the formatter black over the files written, if a program of that name is on the path (`django/core/management/utils.py:run_formatters`).

In a dry run at verbosity 3 each file's text is logged under a heading that names it. `--scriptable` sends everything the command logs, with the questioner's prompts, to standard error, and each file's path to standard output: `Command.log`, through which the logged lines are written, takes its stream from `Command.log_output` (`django/core/management/commands/makemigrations.py:Command.log_output`).

```text recording=migrations
python manage.py makemigrations yard --scriptable
  stdout | harbour/yard/migrations/0006_dock_covered.py
  stderr | Migrations for 'yard':
  stderr |   harbour/yard/migrations/0006_dock_covered.py
  stderr |     + Add field covered to dock
```

> **Trap.** `write_migration_files` writes the path to standard output inside its test of the verbosity and before its test of a dry run: `--scriptable` at verbosity 0 prints no path, and with `--dry-run` it prints the path of a file that was not written. Reading the path can itself make a package, dry run or not ([Writing a migration file: `MigrationWriter`](writer.md)).
