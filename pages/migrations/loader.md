---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Finding migrations: `MigrationLoader`

`MigrationLoader` is where migrations stop being files. `MigrationLoader.load_disk` imports each application's migration modules and makes a migration of each; `MigrationLoader.build_graph` adds which of them one database has applied and joins them into the graph by their dependencies, `"__first__"` and `"__latest__"` among them.

A migration file is a module, and no plan can be made from modules. The **loader**, an instance of `MigrationLoader`, reads two sources, the migration modules on disk and the rows of applied migrations in one database, and keeps what the rest of the system works from: `MigrationLoader.disk_migrations`, every migration found, by its key (label and name); `MigrationLoader.applied_migrations`, the rows read, by the same key, replacement aside; `MigrationLoader.migrated_apps` and `MigrationLoader.unmigrated_apps`, two sets of labels; and `MigrationLoader.graph`. Making a loader builds all of it, since `MigrationLoader.__init__` calls `build_graph` unless given `load=False` (`django/db/migrations/loader.py:MigrationLoader`). Each command of this chapter makes at least one: migrate through its executor, which hands the loader its own connection (`django/db/migrations/executor.py:MigrationExecutor.__init__`), the others directly.

The class's docstring gives the reason a loader reads a database at all, which is replacement: whether a migration that replaces others (a squashed one) stands in the graph in their place depends on which of the replaced ones are applied, and where it does it counts as applied or not by their rows, not its own ([Replacing migrations: `replaces`](replacing.md)). A loader given `None` for its connection reads none: `build_graph` gives it an empty `applied_migrations` and sends no statement, and what it describes is the files alone. makemigrations makes the loader of `Command.handle` so (`django/core/management/commands/makemigrations.py:Command.handle`; [The makemigrations command](../makemigrations/makemigrations.md)), and so do squashmigrations and optimizemigration, the other two commands that write migration files.

## Where an application's migrations are looked for

`MigrationLoader.migrations_module` answers for a label with a pair: the dotted name of a module, and whether the setting `MIGRATION_MODULES` gave it (`django/db/migrations/loader.py:MigrationLoader.migrations_module`). The setting is a dict by label, empty by default (`django/conf/global_settings.py`). For a label it lacks, the name is the application's `AppConfig.name`, a dot, and `MIGRATIONS_MODULE_NAME`, which is `"migrations"`. For a label it has, the name is the value there: another module's name, or `None`, which says the application has no migrations whatever its package holds. A test database made with `"MIGRATE"` set to `False` relies on that: `BaseDatabaseCreation.create_test_db` sets every application's entry to `None` while it calls migrate ([Test databases: `BaseDatabaseCreation`](../schema/test-databases.md)).

## `load_disk`: migrated and unmigrated applications

`MigrationLoader.load_disk` goes through the installed applications, imports the module that `migrations_module` names for each, and puts the label in one of two sets (`django/db/migrations/loader.py:MigrationLoader.load_disk`). A **migrated application** is one whose module imports and is an ordinary package; it need not hold a migration. An **unmigrated application** is any of these: the setting gave `None`; the import raised `ModuleNotFoundError` in a way taken to mean that there is no migrations module; the module has no `__path__`, as a file `"migrations.py"` has none; or it is a namespace package, which is what Python makes of a directory with no `"__init__.py"`.

For a module the setting did not name, a `ModuleNotFoundError` counts only when `"migrations"` is one of the dotted parts of the name Python could not find, so a migrations package that is there, and itself imports a missing module of some other name, stops the loader. For a module the setting named, it counts only in a loader made with `ignore_no_migrations=True`, as makemigrations and showmigrations each make one. Every other exception from the import is raised.

Within a migrated application's package, `load_disk` lists the modules with `pkgutil.iter_modules` and passes over every package among them and every module whose name begins with `"_"` or `"~"`. It imports each of the rest and requires one thing of it, an attribute `Migration`, which in a migration file is a subclass of Django's class of that name; a module without one raises `BadMigrationError` (`django/db/migrations/migration.py:Migration`). It calls the attribute with the module's name, without its package, and the application's label, and files the migration it gets in `disk_migrations` under that pair. A migration's name is therefore its file's name, and nothing inside the file states it.

## `build_graph`, in its order

`MigrationLoader.build_graph` calls `load_disk`, has the recorder read the applied migrations unless the loader has no connection ([What has been applied: `MigrationRecorder` and the table `"django_migrations"`](recorder.md)), and fills a new `MigrationGraph` in three passes over `disk_migrations`: the nodes, then the dependencies inside each application, then the rest (`django/db/migrations/loader.py:MigrationLoader.build_graph`). The recording is of a loader made for harbour's first five migrations with the connection `"default"`, on SQLite. In this page's recordings a line is a call, nested as the calls were made, or a line of Python as it was run, with what came back or the exception raised after `->`; a line beginning with a bar is a line of a file; and only the lines a passage is about are written, the rest left out.

```text recording=migrations
MigrationLoader.build_graph
  MigrationLoader.load_disk
...
  MigrationRecorder.applied_migrations
...
  MigrationGraph.add_node(key=('fleet', '0001_initial'), migration=fleet.0001_initial)
  MigrationGraph.add_node(key=('crew', '0001_initial'), migration=crew.0001_initial)
...
  MigrationLoader.add_internal_dependencies(key=('crew', '0002_initial'), migration=crew.0002_initial)
    MigrationGraph.add_dependency(child=('crew', '0002_initial'), parent=('crew', '0001_initial'), skip_validation=True)
...
  MigrationLoader.add_external_dependencies(key=('crew', '0002_initial'), migration=crew.0002_initial)
    MigrationLoader.check_key(key=('fleet', '0001_initial'), current_app='crew')  ->  ('fleet', '0001_initial')
    MigrationGraph.add_dependency(child=('crew', '0002_initial'), parent=('fleet', '0001_initial'), skip_validation=True)
...
  MigrationGraph.validate_consistency
  MigrationGraph.ensure_not_cyclic
```

Every migration has its node before any dependency is added. An end of an edge that is no node even then gets a placeholder, a `DummyNode`, and one still there when `MigrationGraph.validate_consistency` runs raises `NodeNotFoundError` ([The migration graph: `MigrationGraph`](graph.md)).

The dependencies inside an application go in before those between applications so that a dependency on `"__first__"` finds the right root node (`django/db/migrations/loader.py:MigrationLoader.add_internal_dependencies`). A root node is one with no parent in its own application, and until an application's own edges are in, every node it has is one. `MigrationLoader.add_internal_dependencies` adds an edge for each dependency that carries the migration's own label, but for one named `"__first__"`; `MigrationLoader.add_external_dependencies` takes the dependencies on other applications, each through `MigrationLoader.check_key`, and then `Migration.run_before` (`django/db/migrations/migration.py:Migration`).

After the three passes comes replacement, unless `MigrationLoader.replace_migrations` is `False`, as sqlmigrate makes its loader ([Replacing migrations: `replaces`](replacing.md)); then `validate_consistency`, and last `MigrationGraph.ensure_not_cyclic`, which raises `CircularDependencyError` for a cycle.

## `check_key`: `"__first__"` and `"__latest__"`

`MigrationLoader.check_key` resolves the two names that may stand in a dependency in place of a migration's name, `"__first__"` and `"__latest__"`. It is given the dependency and the label of the application that asks, and returns a key, or `None` for a dependency to be dropped (`django/db/migrations/loader.py:MigrationLoader.check_key`). In the recording yard asks a loader made for harbour's first five migrations.

```text recording=migrations
loader.check_key(('crew', '0001_initial'), 'yard')  ->  ('crew', '0001_initial')
loader.check_key(('crew', '__first__'), 'yard')  ->  ('crew', '0001_initial')
loader.check_key(('crew', '__latest__'), 'yard')  ->  ('crew', '0002_initial')
loader.check_key(('fleet', '__first__'), 'yard')  ->  ('fleet', '0001_initial')
loader.check_key(('yard', '__first__'), 'yard')  ->  None
loader.check_key(('yard', '__latest__'), 'yard')  ->  None
loader.check_key(('nosuch', '__first__'), 'yard')  ->  raises ValueError: Dependency on unknown app: nosuch
```

For a migrated application, the first is taken from `MigrationGraph.root_nodes` for that label and the latest from `MigrationGraph.leaf_nodes`, the nodes with no child in their own application: of either sorted list the first item, however many it has. Where the list is empty, as for an application that has a package and no migration, `check_key` raises `ValueError`, or returns `None` in a loader made with `ignore_no_migrations=True`. For an unmigrated application it returns `None`, under a comment that its models are added to the state all the same. A label in neither of the loader's sets is no installed application's, and is a `ValueError`.

A key with any other name, or one that is a node already, `check_key` returns as it came, whatever the application. So only the two names are forgiven an unmigrated application: a dependency that names one of its migrations outright becomes a `DummyNode`, and `build_graph` ends with `NodeNotFoundError`.

The autodetector writes `"__first__"` into a new migration's dependencies for an application that has no migration and is given none in the same run ([From operations to migrations: dependencies, order and names](../makemigrations/dependencies.md)), and `swappable_dependency` returns one for the application that a swappable model's setting names ([A migration: its operations, its dependencies and how it is applied](migration.md)). Where that application is the migration's own, the reference is ignored (ticket 22325): `add_internal_dependencies` passes over it, and `check_key`, which meets the asking application's own label only in a key of `run_before`, returns `None` for either name. Nothing in Django writes `"__latest__"`.

## `run_before`: an edge added from the other end

`Migration.run_before` is a dependency declared from the other end: the keys of migrations that must run after this one. The class's comment offers, as a use, a third-party application's migrations made to run after a project's replacement for the user model (`django/db/migrations/migration.py:Migration`). `MigrationLoader.add_external_dependencies` passes each key through `check_key` and adds the edge with the migration named as the child and this one as its parent (`django/db/migrations/loader.py:MigrationLoader.add_external_dependencies`). A migration written into yard for the recording and removed after it, yard.0002_before_office, and what a loader then made of it:

```text recording=migrations
| from django.db import migrations
|
|
| class Migration(migrations.Migration):
|
|     dependencies = [("yard", "0001_initial")]
|     run_before = [("office", "0001_initial")]
|     operations = []
loader = MigrationLoader(None)
...
  MigrationLoader.add_external_dependencies(key=('yard', '0002_before_office'), migration=yard.0002_before_office)
    MigrationLoader.check_key(key=('office', '0001_initial'), current_app='yard')  ->  ('office', '0001_initial')
    MigrationGraph.add_dependency(child=('office', '0001_initial'), parent=('yard', '0002_before_office'), skip_validation=True)
```

## Two checks: `check_consistent_history` and `detect_conflicts`

`MigrationLoader.check_consistent_history` compares the graph with the rows of a database. The connection is its argument, and it reads the rows with a recorder of its own, so a loader made with no connection can be asked (`django/db/migrations/loader.py:MigrationLoader.check_consistent_history`). For each applied key that is a node, it goes through the node's parents, and at the first that is not applied it raises `InconsistentMigrationHistory`. Django's documentation says that editing dependencies by hand can make such a history, and calls it a strong indication that they are incorrect (`docs/topics/migrations.txt`). Two things are let pass: a row whose key is no node, and a parent that is a replacing migration which `MigrationLoader.all_replaced_applied` lets through ([Replacing migrations: `replaces`](replacing.md)). A migration written into yard, whose `run_before` makes it a parent of office's first migration, made a history that is refused, office's being applied already:

```text recording=migrations
loader.check_consistent_history(connection)  ->  raises InconsistentMigrationHistory: Migration office.0001_initial is applied before its dependency yard.0002_before_office on database 'default'.
```

`MigrationLoader.detect_conflicts` looks for an application with more than one leaf node. It returns a dict from each such label to the sorted names of its leaf nodes (`django/db/migrations/loader.py:MigrationLoader.detect_conflicts`). It refuses nothing itself: migrate raises `CommandError` if the dict is not empty, and what makemigrations does with it, `--merge` included, is in [The makemigrations command](../makemigrations/makemigrations.md).

## One migration by its name

`MigrationLoader.get_migration` takes a label and a whole name and returns the migration at that key in the graph's `MigrationGraph.nodes` (`django/db/migrations/loader.py:MigrationLoader.get_migration`). `MigrationLoader.get_migration_by_prefix` takes the beginning of a name, as typed on a command line, and searches `disk_migrations`: one match is returned, several raise `AmbiguityError`, none raises `KeyError` (`django/db/migrations/loader.py:MigrationLoader.get_migration_by_prefix`). The two read different collections, so a migration that replacement took out of the graph is still found by its prefix and not by `get_migration`.

## States and statements from the graph

`MigrationLoader.project_state` calls `MigrationGraph.make_state` and adds one thing to its arguments: the loader's `unmigrated_apps`, for the state's `ProjectState.real_apps`, an empty graph aside (`django/db/migrations/loader.py:MigrationLoader.project_state`; [The migration graph: `MigrationGraph`](graph.md)). A migrated model may relate to a model of an unmigrated application: a state's registry renders the models of the applications in its `real_apps` from the main registry's, without their relation fields ([Historical models: `StateApps` and rendering](historical-models.md)).

`MigrationLoader.collect_sql` is how sqlmigrate has a migration's statements without sending them: for each pair of a plan it opens a schema editor on the loader's connection with `collect_sql=True`, under which `BaseDatabaseSchemaEditor.execute` keeps each statement it is given and sends none, has the migration apply or unapply itself, and gathers what the editor kept, so a loader made with no connection cannot be asked (`django/db/migrations/loader.py:MigrationLoader.collect_sql`; [The migrate command, showmigrations and sqlmigrate](migrate.md)).
