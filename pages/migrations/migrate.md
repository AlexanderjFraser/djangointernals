---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The migrate command, showmigrations and sqlmigrate

The migrate command is a front for the executor: it turns its arguments into targets, refuses a history it cannot work from, sends the signals `pre_migrate` and `post_migrate` around `MigrationExecutor.migrate`, and prints progress. showmigrations and sqlmigrate each read the same files and rows and record nothing: one lists the migrations and marks those applied, the other prints the statements one migration would send.

## Before the plan: what the command loads and refuses

`Command.handle` first imports the module `"management"` of each installed application that has one, so that a receiver connected in that module is connected before either signal is sent. It calls `BaseDatabaseWrapper.prepare_database`, a hook, empty in the base class, for a backend with a database to check or prepare first, and makes the executor, whose loader builds the graph from the migration files and reads which migrations are applied (`django/core/management/commands/migrate.py:Command.handle`, `django/db/backends/base/base.py:BaseDatabaseWrapper.prepare_database`).

Then come the refusals, both tests of the loader's ([Finding migrations: `MigrationLoader`](loader.md)). `MigrationLoader.check_consistent_history` raises `InconsistentMigrationHistory` for a recorded history that is out of order; that is no `CommandError`, so at a terminal the command ends in a traceback. `MigrationLoader.detect_conflicts` returns the applications with more than one leaf node (a migration on which no other migration of the application depends), and for any the command raises `CommandError` and names the remedy ([The makemigrations command](makemigrations.md)) (`django/core/management/commands/migrate.py:Command.handle`). In a recording a line beginning `python manage.py` is a command run as a process of its own, with what it printed under it, each line after its stream; the other lines are calls, or Python the recording ran, each under the call that made it, with `->` before what it returned and `stdout |` before a line the command printed, and only the calls a passage is about, so that what ran between two lines is left out; a call is written with the class of its object, or a signal's with its name, and a class in parentheses after it is the one that declares the method that ran.

With two migrations of yard that depend on the same one:

```text recording=migrations
python manage.py migrate
  stderr | CommandError: Conflicting migrations detected; multiple leaf nodes in the migration graph: (0006_dock_covered, 0006_long_dock in yard).
  stderr | To fix them run 'python manage.py makemigrations --merge'
  exit status 1
```

## Targets from the arguments

migrate takes an application's label and a migration's name, each optional, and makes of them the **targets** for `MigrationExecutor.migration_plan`: the keys that its **plan**, a list of pairs of a migration and whether it runs backwards, is to reach. With neither, they are every leaf node, `MigrationGraph.leaf_nodes`; with a label, that application's. With a name as well, as when migrate was given yard, 0002 and `--plan` with yard's three migrations applied:

```text recording=migrations
migrate.Command.handle(app_label='yard', migration_name='0002', plan=True)
  MigrationLoader.get_migration_by_prefix(app_label='yard', name_prefix='0002')  ->  yard.0002_rename_started_repair_begun_dock_metres_and_more
  MigrationExecutor.migration_plan(targets=[('yard', '0002_rename_started_repair_begun_dock_metres_and_more')])  ->  [(yard.0003_repair_foreman, True)]
  stdout | Planned operations:
  stdout | yard.0003_repair_foreman
  stdout |     Undo Add field foreman to repair
```

The name need only be the start of a migration's name: `MigrationLoader.get_migration_by_prefix` finds the migration, and for a start that several names share, or none, the command raises `CommandError`. Nothing in the arguments says forwards or backwards: `migration_plan` decides by whether the target is applied, and yard's second was, so the plan unapplies what follows it. The name `"zero"` gives the target `("yard", None)`, which the executor takes to mean that none of yard's migrations is to stay applied ([Applying a plan: `MigrationExecutor`](executor.md)). A migration that replaces others, a squashed one, may stand in the graph in their place; while only some of them are applied it is left out, and a name that finds it gives the last of the migrations it replaces as the target ([Squashed migrations: `replaces` and the squashmigrations command](squashing.md)) (`django/core/management/commands/migrate.py:Command.handle`).

## `--prune`, `--plan` and `--check`

`--prune`, `--plan` and `--check` each end migrate before anything is applied (`django/core/management/commands/migrate.py:Command.handle`). `--prune` needs a label, and deletes the rows of that application whose migration file is gone, each through `MigrationRecorder.record_unapplied`; it deletes none while a replacing migration on disk names one of them as replaced ([Squashed migrations: `replaces` and the squashmigrations command](squashing.md)).

`--plan` prints the plan: each migration, and under it a line for each of its operations from `Command.describe_operation`, which says IRREVERSIBLE where a `RunPython` or a `RunSQL` is to run backwards and was given nothing to run (`django/core/management/commands/migrate.py:Command.describe_operation`). `--check` ends the command with status 1 if the plan holds anything, and with `--plan` prints it first.

## The run: `pre_migrate`, the executor, `post_migrate`

Unless `--prune`, `--plan` or `--check` ended it, migrate makes the state that receivers of `pre_migrate` are shown, with `MigrationExecutor._create_project_state`: the state of the migrations applied on this database, rendered, its model states made into model classes ([Applying a plan: `MigrationExecutor`](executor.md)). `emit_pre_migrate_signal` sends `pre_migrate` once for each application of the main registry that has a models module (`django/core/management/sql.py:emit_pre_migrate_signal`).

`MigrationExecutor.migrate` is then given the targets, the plan, a clone of that state and, where the plan is not empty, what was typed for `--fake` and `--fake-initial`, which the executor carries out. The executor reports each migration to `Command.migration_progress_callback`, which prints its line, at verbosity 2 with the time it took and at verbosity 0 not at all (`django/core/management/commands/migrate.py:Command.migration_progress_callback`).

The state the executor returns is changed before `post_migrate` is sent, since a receiver may ask its registry for any model (`django/core/management/commands/migrate.py:Command.handle`). `ProjectState.clear_delayed_apps_cache` discards a registry that an operation re-rendered only in part, the models near its change and not those further off, so that the next read renders every model state afresh (`django/db/migrations/state.py:ProjectState.clear_delayed_apps_cache`). And the models of unmigrated applications, which a state's registry renders without their relations, are taken out and rendered again with them, or a receiver would get those models with no foreign keys ([Historical models: `StateApps` and rendering](historical-models.md)). `emit_post_migrate_signal` then sends `post_migrate` likewise.

Recorded as migrate applied yard's second migration, which renames Repair's field started to begun, with a receiver of the recording's own, watching, connected to both signals to write down what it is given:

```text recording=migrations
emit_pre_migrate_signal
  pre_migrate.send(sender=the AppConfig yard)  (Signal.send)
    watching(sender=the AppConfig yard, ...)  for pre_migrate, with the keyword arguments app_config, apps, interactive, plan, signal, stdout, using, verbosity
      app_config is sender: True; using: 'default'; verbosity: 1; interactive: True
      plan: [(yard.0002_rename_started_repair_begun_dock_metres_and_more, False)]
      apps: a state's registry; apps is the main registry: False
      the fields of apps.get_model('yard', 'Repair'): ['id', 'started', 'notes', 'dock', 'ship']
...
emit_post_migrate_signal
  post_migrate.send(sender=the AppConfig yard)  (Signal.send)
    watching(sender=the AppConfig yard, ...)  for post_migrate, with the keyword arguments app_config, apps, interactive, plan, signal, stdout, using, verbosity
...
      the fields of apps.get_model('yard', 'Repair'): ['id', 'notes', 'dock', 'ship', 'begun']
```

Of what watching was given, interactive is all that `--noinput` changes: the command itself asks nothing. And apps is a state's registry, not the main one: the historical models as the applied migrations describe them before, and as the plan left them after, so that Repair has started in the first list and begun in the second. Django's reference tells a receiver to take its models from apps (`docs/ref/signals.txt`).

Django connects one receiver to `pre_migrate`, `inject_rename_contenttypes_operations`, whose work is to put an operation of its own after each `RenameModel` in the migrations of the plan it is handed, for the executor to run ([Making content types: `create_contenttypes` and `RenameContentType`](../contrib/making-content-types.md)) (`django/contrib/contenttypes/management/__init__.py:inject_rename_contenttypes_operations`). To `post_migrate`, contenttypes connects `create_contenttypes`, auth `create_permissions` and `rename_permissions_after_model_rename` ([Making the permissions: `create_permissions`](../auth/creating-permissions.md)), and sites `create_default_site` (`django/contrib/contenttypes/apps.py:ContentTypesConfig.ready`, `django/contrib/auth/apps.py:AuthConfig.ready`, `django/contrib/sites/apps.py:SitesConfig.ready`).

With an empty plan both signals are still sent and the executor is still called. Before the executor, unless verbosity is 0, the command then looks for changes in the models that no migration has: an autodetector, of the class in `Command.autodetector`, is given the loader's `MigrationLoader.project_state` as its from-state and `ProjectState.from_apps` of the main registry as its to-state, and a notice names the applications in what its `MigrationAutodetector.changes` returns, if anything ([The autodetector: comparing two project states](autodetector.md)) (`django/core/management/commands/migrate.py:Command.handle`). With yard's models edited and no migration yet written:

```text recording=migrations
stdout |   Your models in app(s): 'yard' have changes that are not yet reflected in a migration, and so won't be applied.
stdout |   Run 'manage.py makemigrations' to make new migrations, and then re-run 'manage.py migrate' to apply them.
```

## `--run-syncdb` and `sync_apps`

Between `pre_migrate` and the executor, migrate given `--run-syncdb` makes tables for the applications the loader sorted as unmigrated ([Finding migrations: `MigrationLoader`](loader.md)): all of them, or the one named, which must be one of them; with none the option does nothing. `Command.sync_apps` reads the names of the tables the database has, asks `ConnectionRouter.get_migratable_models` for each application's models, sets aside those whose table is there, and in one schema editor calls `BaseDatabaseSchemaEditor.create_model` for each of the rest that `Options.can_migrate` allows (`django/core/management/commands/migrate.py:Command.sync_apps`, `django/db/models/options.py:Options.can_migrate`). On an empty database, with `MIGRATION_MODULES` giving `None` for yard, and then the rows of `"django_migrations"`:

```text recording=migrations
    migrate.Command.sync_apps(connection=the connection "default", app_labels={'yard'})
...
      ConnectionRouter.get_migratable_models(app_config=the AppConfig yard, db='default')  ->  [the model yard.Dock, the model yard.Repair]
...
      DatabaseSchemaEditor.create_model(the model yard.Dock)  (BaseDatabaseSchemaEditor.create_model)
...
recorded_rows()  ->  ['crew.0001_initial', 'fleet.0001_initial', 'office.0001_initial', 'crew.0002_initial']
```

These are the main registry's models, as `models.py` has them now, where a migration's operation is given historical models; no migration of yard runs and no row is written for it: the four rows are the other applications' migrations, which the same command went on to apply. So yard's tables, whose foreign keys name fleet's, were made first, which Django's documentation says may work and is not supported (`docs/topics/migrations.txt`). A test database gets its schema from migrate called with `run_syncdb=True` ([Test databases: `BaseDatabaseCreation`](../backends/creation.md)).

## One database at a time

A run of migrate is for one connection, the alias of `--database` or `"default"`: one executor, one loader, one table `"django_migrations"`. `Command.get_check_kwargs` gives the alias to the system checks that run first, so that the checks kept for databases run, for that alias alone ([The system checks](../commands/checks.md)) (`django/core/management/commands/migrate.py:Command.get_check_kwargs`). The router is not asked which migrations an alias is to have. An operation on a model or a field that changes a table asks it, in its database half, whether the model belongs on the connection, and sends nothing where it does not ([Operations: the base class and its two halves](operations.md), [Routing between databases: `ConnectionRouter`](../backends/routers.md)) (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`). The executor records the migration either way. Harbour's router keeps the models Logbook and LogEntry for `"archive"` and says nothing of the rest. After a migrate for each of two empty databases, their rows compared and then their tables:

```text recording=migrations
recorded_rows('default') == recorded_rows('archive')  ->  True
...
[name for name in tables('archive') if name not in tables('default')]  ->  ['office_logbook', 'office_logentry']
```

## showmigrations

showmigrations has two listings (`django/core/management/commands/showmigrations.py:Command.handle`). The default, `--list`, is by application: `Command.show_list` prints the nodes of each application named, or else of every migrated one, in the order of the `MigrationGraph.forwards_plan` of its leaf nodes, and marks each by two readings of what is applied, the loader's and, apart from it, a recorder's `MigrationRecorder.applied_migrations` (`django/core/management/commands/showmigrations.py:Command.show_list`). `"[X]"` marks a migration that the loader counts applied and the recorder has a row for; `"[ ]"` one the loader does not count applied; and `"[-]"` one the loader counts applied that has no row, which is a replacing migration whose replaced migrations are all applied. Yard comes to have eight migrations, and then one squashed migration that replaces all eight; with the eight applied:

```text recording=migrations
python manage.py showmigrations yard
  stdout | yard
  stdout |  [-] 0001_squashed_0007_merge (8 squashed migrations) Run 'manage.py migrate' to finish recording.
```

`--plan` is by order. `Command.show_plan` takes the forwards plan of every leaf node, or of the leaf nodes of the applications named, keeps each node once, and marks it `"[X]"` where its key is in the loader's `MigrationLoader.applied_migrations` (`django/core/management/commands/showmigrations.py:Command.show_plan`). It differs from the plan migrate would make in keeping the applied migrations.

## sqlmigrate

sqlmigrate prints the statements one migration would send (`django/core/management/commands/sqlmigrate.py:Command.handle`). It makes a loader with `replace_migrations=False`, in whose graph replaced and replacing migrations are all nodes; finds the migration by the start of its name, as migrate does; and hands `MigrationLoader.collect_sql` a plan of one pair, the migration and whether `--backwards` was given. `collect_sql` has the migration apply or unapply itself, from the state of the migrations it depends on, whatever the database has had, to a schema editor whose `BaseDatabaseSchemaEditor.execute` keeps each statement it is handed as text in place of sending it ([Finding migrations: `MigrationLoader`](loader.md)) (`django/db/migrations/loader.py:MigrationLoader.collect_sql`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.execute`). For yard's third migration, where that state has seven of the project's thirteen model states:

```text recording=migrations
  MigrationLoader.collect_sql(plan=[(yard.0003_repair_foreman, False)])
    DatabaseWrapper.schema_editor(collect_sql=True, atomic=True)  (BaseDatabaseWrapper.schema_editor)
...
    MigrationLoader.project_state(nodes=('yard', '0003_repair_foreman'), at_end=False)  ->  a ProjectState of 7 model states, its registry not rendered
    Migration.apply(project_state=state, schema_editor=the schema editor, collect_sql=True)  [yard.0003_repair_foreman]
...
stdout | BEGIN;
stdout | --
stdout | -- Add field foreman to repair
...
stdout | COMMIT;
```

`Migration.apply` and `Migration.unapply`, told to collect, write a comment naming each operation, as in the lines printed here, and another in place of calling the database half of a `RunPython`, whose `RunPython.reduces_to_sql` is false (`django/db/migrations/migration.py:Migration.apply`). The database half of a `RunPython` that a `SeparateDatabaseAndState` was given as a database operation is still called, so sqlmigrate can run a developer's function against the database ([`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](special-operations.md)).

`"BEGIN;"` and `"COMMIT;"` are not statements the editor collected: `BaseCommand.execute` writes the string that `handle` returns, and where the command's `BaseCommand.output_transaction` is true puts the connection's `BaseDatabaseOperations.start_transaction_sql` and `BaseDatabaseOperations.end_transaction_sql` around it (`django/core/management/base.py:BaseCommand.execute`). sqlmigrate sets the attribute for each run: true where the migration's `Migration.atomic` is true and the features have `BaseDatabaseFeatures.can_rollback_ddl`, as SQLite's do.
