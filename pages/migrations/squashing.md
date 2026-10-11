---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Squashed migrations: `replaces` and the squashmigrations command

A squashed migration is one migration that stands in for a run of others, which it names in `Migration.replaces` (`django/db/migrations/migration.py:Migration`). squashmigrations writes one; `MigrationLoader.replace_migration` decides for each database whether the graph holds it or the migrations it replaces; and `MigrationExecutor.record_migration` and `MigrationExecutor.check_replacements` keep the rows of `"django_migrations"` in step with both.

A history only grows: building the graph imports every file of it, and an empty database runs every operation. A **replacing migration**, which the command calls squashed, is one whose `replaces` is not empty: the list holds the keys of the **replaced** migrations, whose work its operations do in one step.

One set of files serves every database, and the databases are at different points of the history. Where none of the replaced migrations is applied, the replacing one should be applied in their place. Where all are, it must count as applied and never run. Where some are, it cannot be used, and the database goes on with the old ones. So the replaced files stay beside the new one, and each loader chooses between them as it builds the graph, by the rows of its own database.

In the example yard's eight migrations, 0001_initial to 0007_merge (two are numbered 0006, and 0007_merge joins them), are squashed into yard.0001_squashed_0007_merge, and three databases meet it: `"default"`, where all eight are applied; `"fresh"`, which is empty; and `"halfway"`, where the first three are (a settings module, settings_three, adds the last two of these databases).

## The squashmigrations command

squashmigrations takes an application's label and the name of the last migration to squash, and optionally, before that, the name of the first (`django/core/management/commands/squashmigrations.py:Command.handle`). Its loader has no connection, so for it no migration is applied. `MigrationLoader.get_migration_by_prefix` finds a named migration by the beginning of its name, among those on disk, and the run is the application's part of `MigrationGraph.forwards_plan` of the last one, cut to begin at the first if one was named.

In the recordings here, from a running Django, `python manage.py` begins a command line, `stdout |` a line it printed, and a bar alone a line of a file; the other lines are Python as it ran and the calls it made, nested as they were made, with what came back after `->`, (on "fresh") after a call on that connection, words in angle brackets in place of a value, and full, the recording's own, writing a value out whole; only the lines a passage is about are written, and whatever else ran, or was printed or written, is left out.

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

## The loader chooses: `replace_migration`

`MigrationLoader.build_graph` first makes every migration on disk a node, replaced and replacing alike, with the edges its file names, and keeps each replacing one in `MigrationLoader.replacements` by its key. Then, unless its `MigrationLoader.replace_migrations` is false, it calls `MigrationLoader.replace_migration` for each (`django/db/migrations/loader.py:MigrationLoader.build_graph`; [Finding migrations: `MigrationLoader`](loader.md)).

`replace_migration` looks each replaced key up in `MigrationLoader.applied_migrations`, the rows the recorder read, or nothing for a loader with no connection (`django/db/migrations/loader.py:MigrationLoader.replace_migration`). If every one is there it puts the replacing migration in too; if not it takes it out, whatever row that migration has of its own: to a loader that replaces, a replacing migration is applied exactly when all it replaces is.

Then the graph: where all are applied or none, `MigrationGraph.remove_replaced_nodes` takes the replaced nodes out and moves every edge between one of them and a node outside the set onto the replacing node (`django/db/migrations/graph.py:MigrationGraph.remove_replaced_nodes`). Where some are applied, `MigrationGraph.remove_replacement_node` takes out the replacing node instead and gives its children, such as a migration made since the squash, to the last of the replaced nodes still in the graph, those that are a parent of no other replaced node (`django/db/migrations/graph.py:MigrationGraph.remove_replacement_node`).

```text recording=migrations
loader = MigrationLoader(connections['default'])
  MigrationLoader.replace_migration(('yard', '0001_squashed_0007_merge'))
    MigrationGraph.remove_replaced_nodes(replacement=('yard', '0001_squashed_0007_merge'), replaced=<8 keys>)
full(sorted(name for label, name in loader.graph.nodes if label == 'yard'))  ->  ['0001_squashed_0007_merge']
loader = MigrationLoader(connections['fresh'])
  MigrationLoader.replace_migration(('yard', '0001_squashed_0007_merge'))  (on "fresh")
    MigrationGraph.remove_replaced_nodes(replacement=('yard', '0001_squashed_0007_merge'), replaced=<8 keys>)
full(sorted(name for label, name in loader.graph.nodes if label == 'yard'))  ->  ['0001_squashed_0007_merge']
loader = MigrationLoader(connections['halfway'])
  MigrationLoader.replace_migration(('yard', '0001_squashed_0007_merge'))  (on "halfway")
    MigrationGraph.remove_replacement_node(replacement=('yard', '0001_squashed_0007_merge'), replaced=<8 keys>)
full(sorted(name for label, name in loader.graph.nodes if label == 'yard'))  ->  ['0001_initial', '0002_rename_started_repair_begun_dock_metres_and_more', '0003_repair_foreman', '0004_name_the_foremen', '0005_repair_by_foreman', '0006_dock_covered', '0006_long_dock', '0007_merge']
```

```text figure=three-graphs
S is yard.0001_squashed_0007_merge, the eight it replaces are written by their numbers, and an arrow points from a migration to one it depends on.

as build_graph first makes it, on every database:
    0007  ->  0006_long_dock and 0006_dock_covered  ->  0005  ->  0004  ->  0003  ->  0002  ->  0001
    S

"fresh", none of the eight applied: remove_replaced_nodes
    S                                  S is not applied, and a plan applies it

"default", all eight applied: remove_replaced_nodes
    S                                  S counts as applied, and a plan is empty

"halfway", 0001 to 0003 applied: remove_replacement_node
    0007  ->  ...  ->  0001            S is not in the graph, and a plan applies 0004 to 0007
```

*Yard's part of the graph on three databases: the replacing node in place of the eight where none or all of them are applied, and the eight without it where some are.*

`MigrationExecutor.migration_plan` reads the loader's `applied_migrations`, not the table, so on `"default"` it plans nothing for the replacing migration, which has no row there ([Applying a plan: `MigrationExecutor`](executor.md)).

### A replacing migration that is replaced

A replaced key may itself be a replacing migration's. `replace_migration` first calls itself for each such key; `MigrationLoader._resolve_replaced_migration_keys` then follows them through `MigrationLoader.disk_migrations` down to keys that name no replacing migration, and the rows of those decide (`django/db/migrations/loader.py:MigrationLoader._resolve_replaced_migration_keys`). squashmigrations makes such a migration unasked: for its loader no migration is applied, so an earlier replacing migration stands in the graph in place of its run and is squashed like any other.

> **Changed in 6.0.** The release notes say that squashed migrations can themselves be squashed before they are turned into normal migrations (`docs/releases/6.0.txt`).

`MigrationLoader.replacements_progress` holds `False` for a key while its replacement is under way and `True` once it is done: a call that finds `True` returns at once, and one that finds `False` has come round to a migration it has not finished, and raises `CommandError` for a cycle. The recording put beside the squashed migration one of its own, yard.0001_resquashed, that replaces it alone, and loaded both on `"fresh"`:

```text recording=migrations
loader = MigrationLoader(connections['fresh'])
  MigrationLoader.replace_migration(('yard', '0001_resquashed'))  (on "fresh")
    MigrationLoader.replace_migration(('yard', '0001_squashed_0007_merge'))  (on "fresh")
  MigrationLoader.replace_migration(('yard', '0001_squashed_0007_merge'))  (on "fresh")
full(sorted(name for label, name in loader.graph.nodes if label == 'yard'))  ->  ['0001_resquashed']
```

### A dependency on a replaced migration with no file

A dependency on a key that is no node gets a `DummyNode` in its place ([The migration graph: `MigrationGraph`](graph.md)). If a replacing migration replaces that key, `remove_replaced_nodes` takes the `DummyNode` out with the rest and moves the dependency to the replacing node: to a loader that replaces, a migration can go on naming a replaced migration whose file is gone. Where the replacing node was taken out instead, the `DummyNode` stays and `MigrationGraph.validate_consistency` raises `NodeNotFoundError`. `build_graph` raises it again, if the missing key is one that replacing migrations replace and none of them is in the graph, saying that Django tried to replace the migration and could not because some of the replaced migrations are already applied (`django/db/migrations/loader.py:MigrationLoader.build_graph`).

## The rows: `record_migration` and `check_replacements`

A loader that replaces judges a replacing migration by the rows of what it replaces and any other by its own row, and the executor writes both. When a replacing migration is applied, `MigrationExecutor.record_migration` calls itself for each key the migration replaces and then writes the migration's own row; unapplying deletes the same rows (`django/db/migrations/executor.py:MigrationExecutor.record_migration`). On `"fresh"`, where migrate applied the replacing migration:

```text recording=migrations
MigrationExecutor.record_migration(app_label='yard', name='0001_squashed_0007_merge')  (on "fresh")
  MigrationExecutor.record_migration(app_label='yard', name='0001_initial')  (on "fresh")
    MigrationRecorder.record_applied(app='yard', name='0001_initial')  (on "fresh")
...
  MigrationExecutor.record_migration(app_label='yard', name='0007_merge')  (on "fresh")
    MigrationRecorder.record_applied(app='yard', name='0007_merge')  (on "fresh")
  MigrationRecorder.record_applied(app='yard', name='0001_squashed_0007_merge')  (on "fresh")
```

On `"default"` nothing was to be applied, yet the replacing migration needs a row of its own before `replaces` can ever be taken out of it. `MigrationExecutor.check_replacements` writes it: it reads the table again, and for each key of `MigrationLoader.replacements` that has no row it asks `MigrationLoader.all_replaced_applied` whether every migration the key replaces has one, following a replaced replacing migration down, and if so records the key (`django/db/migrations/executor.py:MigrationExecutor.check_replacements`). `MigrationExecutor.migrate` calls it last whatever the plan held, returning before it only where the plan is empty and the database has no table `"django_migrations"`. Until the row is there showmigrations marks the migration `"[-]"` ([The migrate command, showmigrations and sqlmigrate](migrate.md)).

```text recording=migrations
MigrationExecutor.check_replacements
  MigrationLoader.all_replaced_applied(('yard', '0001_squashed_0007_merge'), <12 applied>)  ->  True
  MigrationRecorder.record_applied(app='yard', name='0001_squashed_0007_merge')
```

On `"halfway"` the plan held the five replaced migrations that were not applied, and once they had run, `check_replacements` found all eight applied:

```text recording=migrations
python manage.py migrate yard --database halfway --settings=settings_three
...
  stdout |   Applying yard.0004_name_the_foremen... OK
  stdout |   Applying yard.0005_repair_by_foreman... OK
  stdout |   Applying yard.0006_long_dock... OK
  stdout |   Applying yard.0006_dock_covered... OK
  stdout |   Applying yard.0007_merge... OK
python manage.py showmigrations yard --database halfway --settings=settings_three
  stdout | yard
  stdout |  [X] 0001_squashed_0007_merge (8 squashed migrations)
```

`MigrationLoader.check_consistent_history` is the other caller of `all_replaced_applied`. It raises where an applied migration has a parent that is not, reading the rows itself, and passes over a parent that is a replacing migration with no row where all it replaces is applied (`django/db/migrations/loader.py:MigrationLoader.check_consistent_history`). migrate runs that check before it plans, so before `check_replacements` has run.

## A replaced migration as a target

Where the replacing node is in the graph the replaced ones are not, yet one can be named as a target. `MigrationExecutor.migration_plan`, meeting a target that is no node while its loader replaces, sets `MigrationLoader.replace_migrations` to `False`, has the loader build the graph again and starts over (`django/db/migrations/executor.py:MigrationExecutor.migration_plan`). That graph has every node, replaced and replacing side by side. On `"fresh"` a plan back to yard's second migration holds the six after it and not the replacing one, whose row stays and, to a loader that replaces, no longer counts.

The migrate command sees to the opposite case: a name that finds a replacing migration which is on disk and not in the graph, as a partly applied one is, is turned into the last of the keys it replaces (`django/core/management/commands/migrate.py:Command.handle`).

## Finishing a squash

No command ends a squash. Django's documentation gives the steps: delete the replaced files, point any dependency on one of them at the squashed migration, and take `replaces` out of it (`docs/topics/migrations.txt`). They are for when migrate has been run on every database, with the squashed migration beside the ones it replaces, so that each has that migration's own row: every database has its own table, and a run of migrate writes to one. With the steps done, the squashed migration is an ordinary one, applied where it has its own row. On a database with rows for replaced migrations and none for it, its work is partly or wholly done, yet migrate would plan it and begin applying it, or, where an applied migration depends on it, stop at `MigrationLoader.check_consistent_history` with `InconsistentMigrationHistory`.

The rows of the deleted migrations stay. `migrate --prune` deletes the rows of the named application's migrations that have no file; where a replacing migration still lists one of them it deletes none, and says that such a migration may not be recorded as applied: run migrate again, and remove `replaces` (`django/core/management/commands/migrate.py:Command.handle`). With those rows gone and `replaces` still there, the loader would count the migration as not applied, whatever row of its own it had.
