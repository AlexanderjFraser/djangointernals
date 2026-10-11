---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From operations to migrations: dependencies, order and names

When its generators have run, the autodetector holds a flat list of operations for each application, each operation with the `OperationDependency` tuples that say what it waits for. `MigrationAutodetector._sort_migrations` orders each list, `MigrationAutodetector._build_migration_list` cuts the lists into migrations that depend on one another, and `MigrationAutodetector.arrange_for_graph` numbers and names them.

An operation cannot run before what it refers to exists: a foreign key needs its target's table. Within an application that is a matter of order in a list; between applications, of which migration is applied before which, and the applications of harbour, this chapter's example project, cannot be put in a row. Fleet's Ship has a captain, a Sailor of crew; crew's Sailor has a ship, and pilots into fleet's ports through office's Licence, which points at Sailor and at Port. The project's first makemigrations wrote crew two files. In the recordings here `stdout |` begins a line a command printed, the calls a call made are set in under it, and `->` is followed by what a call or an expression gave; only the lines a passage is about are written, and the rest left out.

```text recording=migrations
python manage.py makemigrations fleet crew office yard
  stdout | Migrations for 'crew':
  stdout |   harbour/crew/migrations/0001_initial.py
  stdout |     + Create model Sailor
  stdout |     + Create model Officer
  stdout |   harbour/crew/migrations/0002_initial.py
  stdout |     + Add field pilots_into to sailor
  stdout |     + Add field ship to sailor
  stdout |     + Create proxy model Veteran
```

Sailor is made without its two fields that point out of crew, which wait for fleet's and office's migrations: the generators make a new model's relations, all but a primary key or a link to a parent, each an `AddField` apart from its `CreateModel` ([The autodetector: comparing two project states](autodetector.md)).

## What an operation waits for: `OperationDependency`

A generator hands each operation to `MigrationAutodetector.add_operation`, with a list of dependencies where it has any; the list, or an empty one, is set on the operation as the attribute `_auto_deps` (`django/db/migrations/autodetector.py:MigrationAutodetector.add_operation`). A dependency is an `OperationDependency`: a named tuple of an application's label, a model's name, a field's name or `None`, and a member of `OperationDependency.Type` (`django/db/migrations/autodetector.py:OperationDependency`). It names no operation and no migration, only a thing and what must have become of it: the operation waits for whichever other operation of the run does that, if one does. Two of crew's operations as the generators left them, each with what it waits for in square brackets, where needs (crew, sailor) created is `OperationDependency.Type.CREATE` on crew's Sailor, naming no field.

```text recording=migrations
crew: CreateModel: Create model Officer (fields sailor_ptr, rank; bases 'crew.sailor')  [needs (crew, officer) removed; needs (crew, sailor) created; needs (crew, sailor) created]
...
crew: AddField: Add field pilots_into to sailor (ManyToManyField(related_name='pilots', to='fleet.port', through='office.Licence'))  [needs (crew, sailor) created; needs (fleet, port) created; needs (office, licence) created]
```

`MigrationAutodetector.check_dependency` is the one place that says which operation a dependency waits for (`django/db/migrations/autodetector.py:MigrationAutodetector.check_dependency`). It compares the names of models and fields and no labels: its two callers give it only operations of the dependency's application.

| the dependency | the operation that meets it |
|---|---|
| `CREATE`, no field | `CreateModel` of the model |
| `CREATE`, a field | `CreateModel` of the model with a field of that name, or `AddField` of the field |
| `REMOVE`, no field | `DeleteModel` of the model |
| `REMOVE`, a field | `RemoveField` of the field |
| `ALTER`, a field | `AlterField` of the field |
| `REMOVE_ORDER_WRT`, a field | `AlterOrderWithRespectTo` of the model, unless it names the field |
| `ALTER_FOO_TOGETHER`, a field | any `AlterUniqueTogether` or `AlterIndexTogether` of the model |
| `REMOVE_INDEX_OR_CONSTRAINT`, a field | any `RemoveIndex` or `RemoveConstraint` of the model |

*What `check_dependency` answers true for. One of the last four types with no field raises `ValueError`.*

The generators write some dependencies out themselves: a `CreateModel` waits for a model of its own name to be deleted, as when a proxy becomes a model with a table, for the models among its bases, and for the model its primary key points at where the key is a relation: Officer needs Sailor twice. Helpers work out others. `MigrationAutodetector._get_dependencies_for_foreign_key` gives a relation `CREATE` of the model it points at and, for a many-to-many field that names a model between, of that model (`django/db/migrations/autodetector.py:MigrationAutodetector._get_dependencies_for_foreign_key`). `MigrationAutodetector._get_dependencies_for_model` joins those of all of a model's relations, and is what an `AddIndex`, `AddConstraint` or `AlterConstraint` on a model both states have is given, whatever fields it names. `MigrationAutodetector._get_dependencies_for_generated_field` makes an added `GeneratedField` wait for the fields its expression refers to that are added in the same run; it goes by name alone, over every model both states have, and adds each relation newly added to one. `MigrationAutodetector._get_generated_field_dependencies_for_removed_field` makes the `RemoveField` of a field of such a model wait for the removal of each generated field of the model that refers to it.

### A dependency on a setting

A dependency can name a setting in place of a model. Where the field's `RelatedField.swappable_setting` is not `None`, as for a foreign key to the user model, `_get_dependencies_for_foreign_key` gives `"__setting__"` for the label and the setting's name for the model. Such a dependency is resolved for the autodetector's own checks only: `MigrationAutodetector._resolve_dependency` reads the setting and returns a dependency on the model named there, and whether it had to (`django/db/migrations/autodetector.py:MigrationAutodetector._resolve_dependency`). The sorting and the cutting test the resolved one, which shows whether the model is in the operation's own application; where it is in another, the migration is given the unresolved one. With `django.contrib.auth` installed and a foreign key to the user model added to yard's Repair:

```text recording=migrations
yard: AddField: Add field inspector to repair (ForeignKey(null=True, on_delete=SET_NULL, to=settings.AUTH_USER_MODEL ('auth.user')))  [needs (yard, repair, inspector) removed; needs (__setting__, AUTH_USER_MODEL) created]
```

The writer writes such a dependency as a call of `swappable_dependency` ([Writing a migration file: `MigrationWriter`](writer.md)), so the file follows the setting of the project that loads it ([Serializing values: `serializer_factory` and `deconstruct`](serializer.md)).

## Order inside an application: `_sort_migrations`

`MigrationAutodetector._sort_migrations` sorts each application's list by itself, topologically, with the standard library's `graphlib.TopologicalSorter` (`django/db/migrations/autodetector.py:MigrationAutodetector._sort_migrations`). Each operation is a node, and for each of its dependencies on its own application every operation of the list that `check_dependency` accepts becomes its predecessor; a dependency on another application is passed over. Crew's list began with Officer's `CreateModel`, which needs Sailor's; sorted, Sailor's stands first, as in crew's first file.

## Cutting the lists into migrations: `_build_migration_list`

`MigrationAutodetector._build_migration_list` makes migrations by taking operations off the fronts of the lists (`django/db/migrations/autodetector.py:MigrationAutodetector._build_migration_list`). It reorders nothing and passes over an operation's dependencies on its own application, which the sort has settled.

The method goes round the applications, in the order of their labels, until no operation is left. At each it walks the list from the front and stops at the first operation held back. A dependency on another application holds an operation back in two cases. In the first, `check_dependency` accepts an operation still waiting in that application's list: what it needs has yet to be put in a migration. In the second, no such operation is waiting, but the dependency is not on a setting and that application has had no migration made in this run to depend on. If the walk reached the end of the list, the operations it took become a migration; if not, they are put back, and a migration made for another application may have freed the list by the next round.

When a round takes nothing, the method turns on what its code calls **chop mode**: an application whose walk took anything now gets a migration of just that, though its list is not finished, and chop mode is turned off as the migration is made. In chop mode, moreover, the second case holds no operation back: by then, a comment says, every application has been gone through and checked. So chop mode is more than a breaker of circles: where the other application has nothing new in the run, as for a new foreign key to a model there, an operation the second case holds back is taken only in chop mode, after a round that took nothing.

Harbour's first round takes nothing: crew's `AddField` of pilots_into waits for fleet's Port, fleet's `AddField` of captain for crew's Sailor, office and yard for fleet's Port. In chop mode crew, first by its label, is cut after its first two operations, the `CreateModel` of Sailor and of Officer. With Sailor in a migration, the same round takes the whole of fleet's list, of office's and of yard's, and a third takes the rest of crew's. The migrations in the order they were made (`django/db/migrations/migration.py:Migration`):

```text recording=migrations
MigrationAutodetector._build_migration_list
  Migration.__init__(name='auto_1', app_label='crew')
  Migration.__init__(name='auto_1', app_label='fleet')
  Migration.__init__(name='auto_1', app_label='office')
  Migration.__init__(name='auto_1', app_label='yard')
  Migration.__init__(name='auto_2', app_label='crew')
```

```text figure=the-chop
Each application's list after the sort, and the migrations cut from it

crew    CreateModel Sailor, CreateModel Officer  |  AddField Sailor.pilots_into, AddField Sailor.ship, CreateModel Veteran
        crew.auto_1, cut off in chop mode           crew.auto_2, the rest, a round later
fleet   the whole list: fleet.auto_1
office  the whole list: office.auto_1
yard    the whole list: yard.auto_1

Dependencies, each from a migration to one that must be applied before it

fleet.auto_1   ->  crew.auto_1     Ship.captain needs Sailor
office.auto_1  ->  crew.auto_1     Licence.sailor needs Sailor
office.auto_1  ->  fleet.auto_1    Licence.port needs Port
yard.auto_1    ->  fleet.auto_1
crew.auto_2    ->  fleet.auto_1    Sailor.ship needs Ship, Sailor.pilots_into needs Port
crew.auto_2    ->  office.auto_1   Sailor.pilots_into needs Licence
```

*Harbour's four lists cut into five migrations by the first makemigrations: one cut, after crew's Sailor and Officer, breaks the circle, and every other list is taken whole.*

The names beginning auto are placeholders, in which the dependencies among the new migrations are written for now. `Migration.initial` is set true where the application has no model in the from-state, the state the migration files make (`MigrationAutodetector.existing_apps`), which marks both of crew's. And as each operation is taken, each of its needs in another application becomes a key in `Migration.dependencies`:

- for a dependency on a setting, `"__setting__"` and the setting's name;
- where the other application has had a migration made in this run, its latest so far;
- otherwise, and so only in chop mode, the first of that application's leaf nodes in the graph the autodetector was given, since, a comment says, it is not known which of its migrations has what is needed; or the label with `"__first__"` where it has none there, or no graph was given.

If a round in chop mode takes nothing too, the method raises `ValueError` with the lists that remain; the docstring holds that this should be impossible, the operations having been split so that none both depends and is depended on.

## Dependencies tidied, operations folded: `_optimize_migrations`

`MigrationAutodetector._optimize_migrations` does three things (`django/db/migrations/autodetector.py:MigrationAutodetector._optimize_migrations`). It gives each migration after an application's first a dependency on the one before it. It passes each migration's dependencies through a set, which removes duplicates and leaves the list in no order of its own; the writer sorts them when it writes the file. And it replaces each migration's operations with what `MigrationOptimizer.optimize` makes of them, one migration at a time ([The optimizer: `MigrationOptimizer` and `reduce`](optimizer.md)), which is what can put a split-off `AddField` back into its `CreateModel` where both are in the migration. The operations of yard's migration before:

```text recording=migrations
CreateModel: Create model Dock (fields id, name)
CreateModel: Create model Repair (fields id, started, notes)
AddField: Add field port to dock (ForeignKey(on_delete=CASCADE, to='fleet.port'))
AddField: Add field dock to repair (ForeignKey(on_delete=PROTECT, to='yard.dock'))
AddField: Add field ship to repair (ForeignKey(on_delete=CASCADE, to='fleet.ship'))
```

and after:

```text recording=migrations
CreateModel: Create model Dock (fields id, name, port)
CreateModel: Create model Repair (fields id, started, notes, dock, ship)
```

## Numbers and names: `arrange_for_graph`

`MigrationAutodetector.arrange_for_graph`, which `MigrationAutodetector.changes` calls on what `MigrationAutodetector._detect_changes` returns, fits the new migrations onto the graph of the existing ones (`django/db/migrations/autodetector.py:MigrationAutodetector.arrange_for_graph`). For each application it takes the first leaf node the graph has for it, ordinarily the only one (`MigrationGraph.leaf_nodes`; [The migration graph: `MigrationGraph`](graph.md)). Where there is one, the application's first new migration is given a dependency on it, and numbering goes on from the number `MigrationAutodetector.parse_number` reads in its name, or from zero if it reads none: the digits the name begins with or, in preference, digits that follow `"_squashed_"` in it, where squashmigrations puts the name of the last migration replaced.

Where there is no leaf node, numbering starts at 1, but first the questioner is asked whether the application is to have a first migration at all (`MigrationQuestioner.ask_initial`; [The questioner: `MigrationQuestioner`](questioner.md)). If it says no, the application's new migrations are dropped, and a dependency another migration had on one of them becomes one on the label with `"__first__"`. Yard asked for alone, before any application had a migration: the cutting made migrations for all four applications, the questioner refused all but yard a first migration, and yard's dependency on fleet's became:

```text recording=migrations
changes  ->  {'yard': [yard.0001_initial]}
changes['yard'][0].dependencies  ->  [('fleet', '__first__')]
```

[Finding migrations: `MigrationLoader`](loader.md) has what the loader makes of `"__first__"`, and [The makemigrations command](makemigrations.md) the whole course of an application with no migrations yet.

A name is the number in four digits, an underscore, and then the name the caller passed, which is makemigrations' `--name` and goes to every migration alike; or else `"initial"`, for the first migration of an application with no leaf node; or else what `Migration.suggest_name` returns, cut to a hundred characters (`django/db/migrations/migration.py:Migration.suggest_name`; [A migration: its operations, its dependencies and how it is applied](migration.md)). `suggest_name` itself answers `"initial"` where `Migration.initial` is true, which is how crew's second came to be crew.0002_initial. Last, every dependency written with a placeholder is rewritten with the name that replaced it. Yard's second migration has its dependency on fleet's leaf node from the cutting, in chop mode since fleet had nothing new, for an index on Repair:

```text recording=migrations
yard.0002_rename_started_repair_begun_dock_metres_and_more: initial False, dependencies [('fleet', '0001_initial'), ('yard', '0001_initial')]
```

## Keeping to the applications asked for: `_trim_to_apps`

`MigrationAutodetector.changes` ends with `MigrationAutodetector._trim_to_apps` where it was given labels to trim to, which for makemigrations are those on its command line (`django/db/migrations/autodetector.py:MigrationAutodetector._trim_to_apps`; [The makemigrations command](makemigrations.md)). It notes, for each application with new migrations, the labels their dependencies name; starts from the labels asked for and adds what those depend on until nothing is added; and drops the new migrations of every other application. It goes by label, so a dependency on any migration of an application, new or old, keeps that application's new ones. Asked for yard alone, where fleet's Port has gained a field and yard's Repair an index:

```text recording=migrations
  MigrationAutodetector._trim_to_apps(changes={'fleet': [fleet.0002_port_depth], 'yard': [yard.0002_repair_repair_by_dock]}, app_labels={'yard'})  ->  {'fleet': [fleet.0002_port_depth], 'yard': [yard.0002_repair_repair_by_dock]}
{label: sorted(migration.dependencies) for label, [migration] in changes.items()}  ->  {'fleet': [('fleet', '0001_initial')], 'yard': [('fleet', '0002_port_depth'), ('yard', '0001_initial')]}
```

Yard's dependency is on fleet's new migration, the latest the cutting had made for fleet when it took the index, though Ship was made by fleet's first; where yard's change is a plain field on Dock, the same call returns yard's migration alone.
