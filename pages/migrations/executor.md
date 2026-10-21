---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Applying a plan: `MigrationExecutor`

`MigrationExecutor` brings one database to a set of targets: `MigrationExecutor.migration_plan` works out which migrations must run and in which direction, and `MigrationExecutor.migrate` runs them, giving each migration its project state, opening a schema editor for it and recording it in `"django_migrations"`. With `fake=True` the rows change and the operations do nothing to the database; with `fake_initial=True` alone, `MigrationExecutor.detect_soft_applied` looks in the database for what a migration would create.

The **executor** is made for a connection and keeps three things beside it (`django/db/migrations/executor.py:MigrationExecutor.__init__`): a loader made with that connection, which reads the migration files into the graph and asks the database which migrations are **applied**, those with a row in the table `"django_migrations"` ([Finding migrations: `MigrationLoader`](loader.md)); a recorder, which writes and deletes those rows ([What has been applied: `MigrationRecorder` and the table `"django_migrations"`](recorder.md)); and a progress callback, or `None`. A migration that replaces others (a squashed one) may stand in the graph in their place, and is then counted applied by their rows; [Replacing migrations: `replaces`](replacing.md) has that. The loader reads the table as the executor is made, and migrating does not update `MigrationLoader.applied_migrations`: before the same executor plans again, `MigrationLoader.build_graph` has to be called.

## From targets to a plan: `migration_plan`

A **target** is the key of a migration the database is to be brought to, or a label with `None`, as in `("yard", None)`, for an application that is to have nothing applied. A **plan** is a list of pairs: a migration, and whether it runs backwards. `MigrationExecutor.migration_plan` takes the targets in turn (`django/db/migrations/executor.py:MigrationExecutor.migration_plan`). It works on a copy of `MigrationLoader.applied_migrations`, putting in each migration it plans forwards and taking out each it plans backwards, and in the three cases applied means in that copy:

- **A target that is not applied** is reached forwards: each migration of its forwards plan that is not applied goes into the plan (`MigrationGraph.forwards_plan`; [The migration graph: `MigrationGraph`](graph.md)).
- **A target that is applied** is reached backwards, and stays applied itself. For each of its children in its own application, the migrations there that depend on it directly, every applied migration of the child's backwards plan is planned: whatever depends on the child, in any application, and then the child (`MigrationGraph.backwards_plan`).
- **A label with `None`** plans backwards every applied migration of the backwards plan of each root node of that application, a migration that depends on none of the application's own.

So in a plan that runs all one way, a migration that two targets call for stands once.

The recordings ran on SQLite over a project, harbour, in which the application yard has three migrations, each depending on the one before (the third adds a field), and fleet has one, on which migrations of the three other applications depend. Each quote has only the lines its passage is about, and what ran between them is left out: a line is Python as it was run, or a call, nested under what made it; an arrow leads to a value or to what a call returned; of two classes on a call, the first is the object's and the one in parentheses declares the method that ran; other words in parentheses are the recording's remark, square brackets hold the migration a method was called on, and a line beginning sqlite is a statement as SQLite ran it; progress, whole, first and the names of states are the recording's own. In the first quote, every migration is applied.

```text recording=migrations
executor.migration_plan([('fleet', '0001_initial')])  ->  []
whole(executor.migration_plan([('fleet', None)]))  ->  [(yard.0003_repair_foreman, True), (yard.0002_rename_started_repair_begun_dock_metres_and_more, True), (yard.0001_initial, True), (crew.0002_initial, True), (office.0001_initial, True), (fleet.0001_initial, True)]
```

With fleet.0001_initial for a target nothing is unapplied, whatever depends on it: it has no child in fleet. The code's comment gives the reason: going back all the way to the target could roll back migrations of other applications that need not be.

With `clean_start=True` the method starts from nothing applied, so that a key's whole forwards plan is planned. Made so for every leaf node, a migration on which none of its own application depends, the plan is the **full plan**, the one for an empty database. A target that is no node of the graph may be a replaced migration: the method has the loader build its graph again with nothing replaced, and starts over ([Replacing migrations: `replaces`](replacing.md)).

## Running a plan: `migrate`

`MigrationExecutor.migrate` takes the targets and, optionally, a plan, a state and the two flags for faking; given no plan it makes one from the targets (`django/db/migrations/executor.py:MigrationExecutor.migrate`). First it has the recorder make the table `"django_migrations"` if it is not there (`MigrationRecorder.ensure_schema`), unless the plan it was given is an empty list, as the command migrate's is when there is nothing to run: then it makes no table, and where there is none it returns at once, with a project state on which no migration has run.

Then it makes the full plan, which is never run: it is the order in which the forwards run applies and the backwards run builds its states. An empty plan runs nothing. A plan all one way goes to `MigrationExecutor._migrate_all_forwards` or `MigrationExecutor._migrate_all_backwards`. A plan with some pairs forwards and some backwards, which targets that pull opposite ways give, goes to neither: it is refused with `InvalidMigrationPlan`. Last, `MigrationExecutor.check_replacements` records a replacing migration whose replaced migrations are all applied ([Replacing migrations: `replaces`](replacing.md)), and the project state as the run left it is returned.

## Forwards: `_migrate_all_forwards`

`MigrationExecutor._migrate_all_forwards` is given a state to start from, the project as the applied migrations describe it. `MigrationExecutor._create_project_state` makes a `ProjectState` with no model state, whose `ProjectState.real_apps` are the **unmigrated** applications, those the loader found no migrations package for: a rendering takes their models from the main registry. With `with_applied_migrations=True` it then goes through the full plan and has each applied migration run its operations' state halves on the state, the halves that change a project state and no database (`django/db/migrations/executor.py:MigrationExecutor._create_project_state`, `django/db/migrations/migration.py:Migration.mutate_state`). For a plan that runs forwards, `MigrationExecutor.migrate` has the state made this way where it was given none.

`_migrate_all_forwards` then goes through the full plan and calls `MigrationExecutor.apply_migration` at each migration that is in the plan, the plan's own order deciding nothing (`django/db/migrations/executor.py:MigrationExecutor._migrate_all_forwards`). Before the first, if the state has no registry, it reads `ProjectState.apps`, which renders every model state into a historical model. The registry is then kept: a state half re-renders, of the whole project, only the model it changed and those related to it ([Historical models: `StateApps` and rendering](historical-models.md)).

With yard's second and third migrations not applied, `migrate` is called with the third for its target:

```text recording=migrations
MigrationExecutor._migrate_all_forwards(state=state, plan=[(yard.0002_rename_started_repair_begun_dock_metres_and_more, False), (yard.0003_repair_foreman, False)], full_plan=a plan of 7, fake=False, fake_initial=False)
  progress('render_start')
  StateApps.__init__(real_apps=set(), models=<13 model states>)
  progress('render_success')
  MigrationExecutor.apply_migration(state=state, migration=yard.0002_rename_started_repair_begun_dock_metres_and_more)  (what it called is not written, nor the 18 statements it sent)
    -> state
  MigrationExecutor.apply_migration(state=state, migration=yard.0003_repair_foreman)  (what it called is not written, nor the 13 statements it sent)
    -> state
  -> state
```

The state is one object throughout: `Migration.apply` changes the state it is given and returns it.

## One migration: `apply_migration`

`MigrationExecutor.apply_migration` opens one schema editor for the whole migration, asking `BaseDatabaseWrapper.schema_editor` for it with the migration's `Migration.atomic`, and inside the editor's `with` block calls `Migration.apply`, which runs each operation's state half and then its database half (`django/db/migrations/executor.py:MigrationExecutor.apply_migration`, `django/db/migrations/migration.py:Migration.apply`; [A migration: its operations, its dependencies and how it is applied](migration.md)). Where the features have `BaseDatabaseFeatures.can_rollback_ddl` and the migration is atomic, entering the editor enters an atomic block, and leaving it leaves the block, which, on a connection in autocommit, commits when no other is open around it; the statements the editor has deferred are sent as it is left, before that commit ([The schema editor: `BaseDatabaseSchemaEditor`](../schema/editor.md)).

`MigrationExecutor.record_migration` has the recorder write the migration's row or, with `forward=False`, delete it; for a replacing migration it first does the same for each migration it replaces (`django/db/migrations/executor.py:MigrationExecutor.record_migration`; [Replacing migrations: `replaces`](replacing.md)). Where `apply_migration` calls it depends on `BaseDatabaseSchemaEditor.deferred_sql` once `Migration.apply` has returned: inside the block if the list is empty; after the block if the editor holds deferred statements, still to be sent, so one that fails leaves no row. Yard's third migration leaves nothing deferred:

```text recording=migrations
MigrationExecutor.apply_migration(yard.0003_repair_foreman)
  DatabaseWrapper.schema_editor(atomic=True)  (BaseDatabaseWrapper.schema_editor)
  DatabaseSchemaEditor.__enter__
    DatabaseSchemaEditor.__enter__  (BaseDatabaseSchemaEditor.__enter__)
      Atomic.__enter__
        sqlite BEGIN
  Migration.apply  [yard.0003_repair_foreman]  (what it called is not written, nor the 7 statements it sent)
  MigrationExecutor.record_migration(app_label='yard', name='0003_repair_foreman')
    MigrationRecorder.record_applied(app='yard', name='0003_repair_foreman')
      sqlite INSERT INTO "django_migrations" ("app", "name", "applied") VALUES ('yard', '0003_repair_foreman', '(the date and the time)') RETURNING "django_migrations"."id"
  DatabaseSchemaEditor.__exit__
    DatabaseSchemaEditor.__exit__  (BaseDatabaseSchemaEditor.__exit__)
      Atomic.__exit__
        DatabaseWrapper.commit  (BaseDatabaseWrapper.commit)
          sqlite COMMIT
```

The schema change and the row are one transaction: both are in the database afterwards, or neither. Yard's first migration leaves the editor three indexes deferred, so its row is written after the commit, by itself, and a stop between the two leaves the schema changed and no row ([Migrations](../migrations.md#applying-migrations) shows it applied, by the statements Django handed its cursor, of which a commit is not one). PostgreSQL's features have `can_rollback_ddl` as SQLite's do; MySQL's and Oracle's do not, and there, or for a migration with `atomic = False`, the editor enters no atomic block for the row to be inside. The order is the same there.

```text figure=one-migration-applied
MigrationExecutor.apply_migration on SQLite, where the schema editor's block is a transaction

nothing deferred: yard.0003_repair_foreman      statements deferred: yard.0001_initial

enter the schema editor: BEGIN                  enter the schema editor: BEGIN
    the operations' statements                      the operations' statements
    the migration's row is inserted
leave the schema editor                         leave the schema editor
                                                    three deferred CREATE INDEX
    COMMIT                                          COMMIT
                                                the migration's row is inserted
```

*One migration applied on SQLite, two ways. With nothing deferred, the row is written inside the schema editor's block and commits with the schema change; with statements deferred, they are sent as the block is left, the transaction commits, and the row is written afterwards.*

## Backwards: `_migrate_all_backwards`

`Migration.unapply` must be given the project state as it was before its migration (`django/db/migrations/migration.py:Migration.unapply`), and an operation has a state half that runs forwards and none that runs backwards (`django/db/migrations/operations/base.py:Operation`): that state is not had by undoing a later one, and is built from the start of the history. So `MigrationExecutor._migrate_all_backwards` makes two passes: the first computes the state before each migration of the plan, and the second unapplies them (`django/db/migrations/executor.py:MigrationExecutor._migrate_all_backwards`).

The first pass sends the database nothing. It starts from a state with no model state (`MigrationExecutor._create_project_state`) and goes through the full plan until it has met every migration of the plan. A migration it meets that is applied and not in the plan runs its state halves on the state in place (`preserve=False`). A migration of the plan has the state as it stands kept for it, and the pass goes on with a clone on which that migration's state halves have run (`preserve=True`); the registry is made before the first such, so each kept state is rendered. A migration that is neither is passed over. So a kept state is made by the migrations before its own in the full plan that are applied or in the plan, and by no others. The second pass takes the plan in its own order, in which `MigrationExecutor.migration_plan` put each migration after whatever depends on it, and calls `MigrationExecutor.unapply_migration` for each with its kept state.

With every migration applied and yard's first for the target:

```text recording=migrations
state = executor.migrate([first])
  MigrationExecutor.migrate([('yard', '0001_initial')])
    MigrationExecutor._migrate_all_backwards(plan=[(yard.0003_repair_foreman, True), (yard.0002_rename_started_repair_begun_dock_metres_and_more, True)], full_plan=a plan of 7, fake=False)
      MigrationExecutor._create_project_state  ->  state 0, a ProjectState of 0 model states, its registry not rendered
      progress('render_start')
      Migration.mutate_state(state 0, preserve=False)  [crew.0001_initial]
      Migration.mutate_state(state 0, preserve=False)  [fleet.0001_initial]
      Migration.mutate_state(state 0, preserve=False)  [office.0001_initial]
      Migration.mutate_state(state 0, preserve=False)  [crew.0002_initial]
      Migration.mutate_state(state 0, preserve=False)  [yard.0001_initial]
      StateApps.__init__(real_apps=set(), models=<13 model states>)
      Migration.mutate_state(state 0, preserve=True)  [yard.0002_rename_started_repair_begun_dock_metres_and_more]  ->  state 1, a ProjectState of 13 model states, its registry rendered
      Migration.mutate_state(state 1, preserve=True)  [yard.0003_repair_foreman]  ->  state 2, a ProjectState of 13 model states, its registry rendered
      progress('render_success')
      MigrationExecutor.unapply_migration(state 1, yard.0003_repair_foreman)
      MigrationExecutor.unapply_migration(state 0, yard.0002_rename_started_repair_begun_dock_metres_and_more)
      -> state 0
'apps' in state.__dict__  ->  False
```

The method then makes the state it returns: it takes the state kept for the plan's last migration, deletes its registry, since changing a rendered state is expensive, and runs on it the state halves of the migrations after that one in the full plan that are still applied. Here none is, and the state returned is the one the database is left in.

`unapply_migration` opens a schema editor as `MigrationExecutor.apply_migration` does, calls `Migration.unapply` inside the block, and has the row deleted after the block, whatever the editor deferred (`django/db/migrations/executor.py:MigrationExecutor.unapply_migration`).

## The progress callback

The executor calls its progress callback, `MigrationExecutor.progress_callback`, where it has one, with the name of an action first: `"apply_start"` and `"apply_success"` first and last in `MigrationExecutor.apply_migration`, `"unapply_start"` and `"unapply_success"` in `MigrationExecutor.unapply_migration`, each with the migration and whether it is faked, which `"apply_start"` says before `MigrationExecutor.detect_soft_applied` has been asked; and, with nothing more, `"render_start"` and `"render_success"`, forwards around the making of the registry, where the state has none, and backwards around the whole first pass. At a verbosity of 1 or more the command migrate prints a line for each pair ([The migrate command, showmigrations and sqlmigrate](migrate.md)); it hands `MigrationExecutor.migrate` a state already rendered (`django/core/management/commands/migrate.py:Command.handle`), so its line about rendering appears only for a plan that runs backwards.

## Faking, and `detect_soft_applied`

With `fake=True` a migration's operations do nothing to the database and its row still changes: `MigrationExecutor.apply_migration` opens no schema editor and has the row written, and `MigrationExecutor.unapply_migration` likewise has the row deleted (`django/db/migrations/executor.py:MigrationExecutor.apply_migration`, `django/db/migrations/executor.py:MigrationExecutor.unapply_migration`). Forwards, no state half runs either: `apply_migration` returns the state it was given, so the state `MigrationExecutor.migrate` returns lacks the faked migrations' changes.

The command's `--fake-initial` is for a database that had its tables before migrations were used on it (`docs/ref/django-admin.txt`). With `fake_initial=True` and without `fake=True`, `apply_migration` first asks `MigrationExecutor.detect_soft_applied` whether the database already has what the migration would create, and fakes that migration if the answer is yes (`django/db/migrations/executor.py:MigrationExecutor.detect_soft_applied`). `Migration.initial` settles which migrations are looked at (`django/db/migrations/migration.py:Migration.initial`): with `initial = True` the method looks; with `initial = False` it answers no; with `None`, the default, it looks unless the migration depends on a migration of its own application.

Where it looks, the method runs the migration's state halves on a clone of the state `apply_migration` gave it, takes historical models from the clone's registry, and has introspection list the database's tables (`BaseDatabaseIntrospection.table_names`; [Introspection: reading the schema back](../schema/introspection.md)). For a `CreateModel`, the model's table must be in the list. For an `AddField` of a many-to-many field, the table of the model between must be; for another field, the model's table must have a column with the name of the field's column (`BaseDatabaseIntrospection.get_table_description`). No other operation is looked at, and of a table or a column only the name: a table with other columns passes, as does a column of another type. A model is skipped if it is a proxy, is not managed, or `ConnectionRouter.allow_migrate` keeps it off this database ([Routing between databases: `ConnectionRouter`](../connections/routers.md)). One thing missing makes the answer no; the answer is yes if nothing was missing and at least one table or column was found. Having looked and missed nothing, the method returns with either answer the state after the migration, and otherwise the state it was given; `apply_migration` goes on with what it returns.
