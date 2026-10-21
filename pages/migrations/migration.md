---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A migration: its operations, its dependencies and how it is applied

A **migration**, as the loader makes it, is an instance of the class `Migration` that a migration file defines, a subclass of the `Migration` of `django.db.migrations` (`django/db/migrations/migration.py:Migration`). It holds a list of operations and the keys of the migrations it depends on, and runs its operations in three ways: `Migration.mutate_state` runs their state halves alone, `Migration.apply` both halves forwards, and `Migration.unapply` the database halves backwards.

`MigrationLoader.load_disk` calls each module's class with the module's name and the application's label ([Finding migrations: `MigrationLoader`](loader.md)), and the label with the name, `("fleet", "0001_initial")`, is the migration's **key**. `django.db.migrations` imports the base class, `swappable_dependency` and the operation classes that `django.db.migrations.operations` exports, so a file reaches them all as attributes of one package (`django/db/migrations/__init__.py`). An operation has a **state half**, which changes a project state, and a **database half**, which changes a database ([Operations: the base class and its two halves](operations.md)).

## The attributes a file sets

`Migration` gives each of its attributes a value, so the subclass that a migration file defines need state only those that differ (`django/db/migrations/migration.py:Migration`). `Migration.operations` lists the operations in the order they run.

`Migration.dependencies` and `Migration.run_before` are lists of keys that the loader turns into edges of the graph, in opposite directions, though from a key whose name is `"__first__"` or `"__latest__"` it may make none ([Finding migrations: `MigrationLoader`](loader.md)). A key in `dependencies` names a migration that must be applied before this one: its node becomes a parent of this one's. A key in `run_before` names one that must be applied after: this migration's node becomes a parent of that one's, as if the other file had named this migration in its own `dependencies` (`django/db/migrations/loader.py:MigrationLoader.add_internal_dependencies`, `django/db/migrations/loader.py:MigrationLoader.add_external_dependencies`; [The migration graph: `MigrationGraph`](graph.md)). The comment on `run_before` gives a use: to make third-party applications' migrations run after a project's replacement for the user model.

`Migration.initial` is `None`, `True` or `False`. Under `migrate --fake-initial`, `MigrationExecutor.detect_soft_applied` looks in the database for the tables and columns a migration would make, and where it finds them the executor records the migration as applied without running it. The method looks where `initial` is `True`, does not where it is `False`, and where it is `None` looks only if the migration depends on no migration of its own application ([Applying a plan: `MigrationExecutor`](executor.md)). The autodetector sets `initial` on each migration it makes, to true where the application has no model in the state the migration files make (`django/db/migrations/autodetector.py:MigrationAutodetector._build_migration_list`), and the writer writes `initial = True` for a true value and nothing for any other ([Writing a migration file: `MigrationWriter`](../makemigrations/writer.md)).

`Migration.atomic`, true unless a file says otherwise, asks for the migration to run in one transaction. `Migration.replaces` lists the keys of the migrations this one stands in place of, which makes it a **replacing migration** ([Replacing migrations: `replaces`](replacing.md)).

## The instance: lists of its own, identity by key

`Migration.__init__` keeps the name and the label, and gives the instance its own copy of each list of the class: the operations, the dependencies, `Migration.run_before` and `Migration.replaces` (`django/db/migrations/migration.py:Migration.__init__`). Its comment gives the reason, that the lists may be changed at runtime, and they are: `makemigrations --update` extends the operations and the dependencies of a migration the loader made (`django/core/management/commands/makemigrations.py:Command.write_to_last_migration_files`; [Rewriting migrations: `--update`, squashmigrations and optimizemigration](../makemigrations/rewriting.md)).

Two migrations are equal when their names and their labels are equal, whatever else they hold, and a migration's hash is that of the string `str` makes of it, the label and the name with a dot between: migrations can be kept in a set and be the keys of a dict, as the executor keeps them (`django/db/migrations/migration.py:Migration.__eq__`, `django/db/migrations/migration.py:Migration.__hash__`).

## `mutate_state`: the state halves alone

`Migration.mutate_state` runs the state half of each operation in order, on one project state, and returns that state (`django/db/migrations/migration.py:Migration.mutate_state`). It touches no database, and is how the loader and the executor make a project state from migration files: `MigrationGraph.make_state` runs it for each migration of a forwards plan, and `MigrationExecutor._create_project_state`, called with `with_applied_migrations=True`, for each applied migration ([Project state: `ProjectState` and its model states](state.md)). Left to itself it clones the state and changes the clone; with `preserve=False`, which both of those pass, it changes the state it was given.

## `apply`: both halves, forwards

`Migration.apply` is given the project state as the migrations before this one left it, and a schema editor. For each operation in turn it clones the state, runs the state half on the state it was given, and calls the database half forwards with the clone as the from-state and the state as the to-state (`django/db/migrations/migration.py:Migration.apply`). A database half may need both ([Operations: the base class and its two halves](operations.md)). What `apply` returns is the object it was given, moved on by every operation, for the next migration to start from: `MigrationExecutor.apply_migration`, which calls `apply` inside a schema editor it has opened, returns it, and `MigrationExecutor._migrate_all_forwards` gives it to the `apply_migration` of the next migration.

Here yard's first migration is applied by hand, as `apply_migration` applies it, to a state rendered as the executor renders it. In a recording a call is set under the call that made it, with the migration or operation it was called on in square brackets and what it returned after `->`, and a line after a bar is a line of a file; only the lines a passage is about are written, and what ran between them is left out.

```text recording=migrations
Migration.apply(project_state=state, schema_editor=the schema editor)  [yard.0001_initial]
  ProjectState.clone  ->  clone 1, a ProjectState of 11 model states, its registry rendered
  CreateModel.state_forwards(state=state)  [Create model Dock]
  CreateModel.database_forwards(from_state=clone 1, to_state=state)  [Create model Dock]
  ProjectState.clone  ->  clone 2, a ProjectState of 12 model states, its registry rendered
  CreateModel.state_forwards(state=state)  [Create model Repair]
  CreateModel.database_forwards(from_state=clone 2, to_state=state)  [Create model Repair]
  -> state
```

## An atomic block for the migration, or for one operation

The schema editor that the executor makes with `atomic=migration.atomic` holds one atomic block open from its entry to its exit where that argument is true and the database can roll back DDL, the statements that change a schema, as SQLite and PostgreSQL can and MySQL and Oracle cannot; `BaseDatabaseSchemaEditor.atomic_migration` says whether it does ([The schema editor: `BaseDatabaseSchemaEditor`](../schema/editor.md)). `Migration.apply` and `Migration.unapply` add a block only where the editor has none: an operation's database half then runs in an atomic block of its own when `Operation.atomic` is true, or when it is anything but `False` and `Migration.atomic` is true (`django/db/migrations/migration.py:Migration.apply`, `django/db/migrations/operations/base.py:Operation`).

`Operation.atomic` is `False` on the base class, whose comment says a true value is for forcing an operation that has no DDL, like `RunPython`, to be atomic even where DDL cannot be rolled back. `RunPython` is the one operation in Django that sets it otherwise, on each instance, to the argument it was made with: `atomic=None` unless one is given ([`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](special-operations.md)).

| the operation | atomic migration | `atomic = False` |
|---|---|---|
| a `RunPython` made with `atomic=True` | a block of its own | a block of its own |
| a `RunPython` left at `atomic=None` | a block of its own | none |
| a `RunPython` made with `atomic=False`, or any other operation of Django's | none | none |

*Whether the database half of an operation in a migration's own list gets an atomic block of its own, where the schema editor holds none: in an atomic migration on a database that cannot roll back DDL, and in a migration with `atomic = False` on any database.*

> **Trap.** The comment on `Migration.atomic` says it only has an effect on backends that support transactional DDL. On the others it still decides whether a `RunPython` left at `atomic=None` runs in a transaction.

## `unapply`: backwards, in two passes

`Migration.unapply` is given what `Migration.apply` is given, the state before the migration, and has to call each operation's database half backwards, last operation first, each with the state after its operation as the from-state and the state before it as the to-state (`django/db/migrations/migration.py:Migration.unapply`). Those states cannot be had by going backwards, since an operation has a state half forwards and none backwards: the state after the last operation exists only when every state half has run, in order, from the state before the first.

So `unapply` makes two passes. The first goes forwards and sends the database nothing. A state half works on the state it is given and makes no new one, so for each operation the pass clones the state so far and clones that clone, then runs the state half on the first of the two: the first is now the state after the operation, and the second is left as the state before it. It puts the operation and its two states at the front of a list, and the first clone is the state so far for the next operation. The second pass goes down the list, which has the last operation first, and calls each database half backwards with the states exchanged: the one reached after the operation is where the database stands, and the one before it is where it is to go. Atomic blocks are decided as in `apply`; the state given is not changed, and is returned.

```text figure=unapply-two-passes
Migration.unapply(state)  [yard.0001_initial: Create model Dock, then Create model Repair]

first pass, forwards: two clones for each operation, and its state half run on one

    Create model Dock      clone 3 of state      clone 4 of clone 3    state half on clone 3: clone 3 with Dock, clone 4 without
    Create model Repair    clone 5 of clone 3    clone 6 of clone 5    state half on clone 5: clone 5 with Repair, clone 6 without

second pass, in reverse: each database half backwards

    Create model Repair    database_backwards(from_state=clone 5, to_state=clone 6)
    Create model Dock      database_backwards(from_state=clone 3, to_state=clone 4)
```

*`Migration.unapply` on yard's first migration, recorded as called by hand with the state `MigrationExecutor.unapply_migration` would give it; its clones are numbered on from the two that `apply` made.*

The first pass begins each turn by reading `Operation.reversible`, and raises `IrreversibleError`, a `RuntimeError`, at the first operation for which it is false (`django/db/migrations/exceptions.py:IrreversibleError`, `django/db/migrations/operations/base.py:Operation`). Since the whole pass comes before any database half, such a migration is refused with none of its operations undone. `reversible` is true on `Operation`, and in Django only `RunPython` and `RunSQL` can have it false: theirs is a property, true only where the operation was given something to run backwards.

## `collect_sql=True`: comments among the statements

Given `collect_sql=True`, `Migration.apply` and `Migration.unapply` write comments among the statements a collecting schema editor keeps as text. `MigrationLoader.collect_sql` calls them so, and sqlmigrate prints the result (`django/db/migrations/migration.py:Migration.apply`, `django/db/migrations/loader.py:MigrationLoader.collect_sql`; [The migrate command, showmigrations and sqlmigrate](migrate.md)). Before an operation's database half the migration appends three comment lines to `BaseDatabaseSchemaEditor.collected_sql`, the middle one holding what `Operation.describe` returns. Where `Operation.reduces_to_sql` is false, which in Django is `RunPython` alone, it appends a fourth and goes on to the next operation: `apply` has then run neither half of that one, and `unapply`, whose first pass ran its state half, not its database half. After any other operation it appends `"-- (no-op)"` if the database half added nothing to the list (`django/db/migrations/operations/base.py:Operation`). What sqlmigrate prints for a migration with a `RunPython` is in [`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](special-operations.md).

## `suggest_name`

`Migration.suggest_name` proposes the part of a migration's name that follows its number. Where no `--name` was given, `MigrationAutodetector.arrange_for_graph` asks it for each new migration that is not its application's first, and `makemigrations --update` for the one it rewrites (`django/db/migrations/migration.py:Migration.suggest_name`; [From operations to migrations: dependencies, order and names](../makemigrations/dependencies.md)). Where `Migration.initial` is true the answer is `"initial"`. Otherwise it takes each operation's `Operation.migration_name_fragment`, with every run of characters other than letters, digits and underscores made an underscore (`django/db/migrations/operations/base.py:Operation`). If there is no operation, or one of them has no fragment, as `RunPython`, `RunSQL` and `SeparateDatabaseAndState` have none, the answer is `"auto_"` and the date and the time to the minute, a fallback the docstring calls an effort to avoid conflicts in version control. Otherwise the name is the first fragment, whatever its length, with each later one joined on by an underscore until one would make the name longer than 52 characters; there `"_and_more"` is added instead, and the rest are left out. For yard's second migration, of four operations, the answer was `"rename_started_repair_begun_dock_metres_and_more"`: its third fragment, `"alter_dock_name"`, would have made a name of 55 characters.

## `swappable_dependency` and `SwappableTuple`

A migration may depend on whatever model a setting names, as one with a foreign key to the user model depends on `AUTH_USER_MODEL`. Its file then holds a call where the key would be, as in the migration that gives yard's Repair such a foreign key, made with `django.contrib.auth` installed:

```text recording=migrations
|     dependencies = [
|         ('yard', '0008_alter_repair_foreman'),
|         migrations.swappable_dependency(settings.AUTH_USER_MODEL),
```

`swappable_dependency` is given the setting's value as the file is imported, and returns the label that value begins with, paired with `"__first__"`, as a `SwappableTuple`: a tuple that also carries the value it was made from (`django/db/migrations/migration.py:swappable_dependency`). To the loader it is a key like any other, whose `"__first__"` `MigrationLoader.check_key` resolves, here to `("auth", "0001_initial")`, the first migration of auth ([Finding migrations: `MigrationLoader`](loader.md)). Squashmigrations reads the value the tuple carries: where that is the current value of `AUTH_USER_MODEL`, the file it writes has the call again (`django/core/management/commands/squashmigrations.py:Command.handle`; [Rewriting migrations: `--update`, squashmigrations and optimizemigration](../makemigrations/rewriting.md)).
