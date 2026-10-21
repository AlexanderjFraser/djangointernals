---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The autodetector: comparing two project states

The autodetector, a `MigrationAutodetector`, is given two project states and finds operations that turn the first into the second. `MigrationAutodetector._detect_changes` sorts the models of both into kept, added and removed, then calls, in a fixed order, the methods that add operations to `MigrationAutodetector.generated_operations`; fields are compared through `MigrationAutodetector.deep_deconstruct`.

makemigrations has two descriptions of the same models, each a project state ([Migrations](../migrations.md#the-project-state)): the **from-state**, which the migration files make, and the **to-state**, read off the model classes by `ProjectState.from_apps`. What it must write is the difference, as operations, and the autodetector finds it by comparing the two states: it is given no connection and reads no database (`django/db/migrations/autodetector.py:MigrationAutodetector`). Where the states cannot settle a question, such as whether a model was renamed or one deleted and another created, it asks the **questioner** it was given ([The questioner: `MigrationQuestioner`](questioner.md)).

## What the autodetector is given and what it returns

`MigrationAutodetector.__init__` takes the from-state, the to-state and a questioner, and without one makes a `MigrationQuestioner`, which asks no one. `MigrationAutodetector.changes` is given the graph and, optionally, a set of labels to trim the result to, a set of labels to convert, which lets an application with no migrations be given its first, and a name for the new migrations (`django/db/migrations/autodetector.py:MigrationAutodetector.changes`). It calls `MigrationAutodetector._detect_changes`, which returns a dictionary from an application's label to a list of new migrations; then `MigrationAutodetector.arrange_for_graph`, which names them and joins them to the graph's leaf nodes; then, where there are labels to trim to, `MigrationAutodetector._trim_to_apps`, which drops the migrations of the other applications, except any that the kept migrations depend on. It returns the dictionary, which is empty when the two states agree.

Two commands make an autodetector. makemigrations gives it the two states and a questioner, and passes the labels on its command line as both sets ([The makemigrations command](makemigrations.md)). migrate makes one with no questioner, and only where its plan is empty and its verbosity is not 0: if `changes` returns anything, it prints the labels in a notice that the models have changes no migration has yet (`django/core/management/commands/migrate.py:Command.handle`; [The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md)).

## `_detect_changes`: the models sorted, then the generators in order

`MigrationAutodetector._detect_changes` first sorts the models (`django/db/migrations/autodetector.py:MigrationAutodetector._detect_changes`). A project state's `ProjectState.models` is keyed by a pair, the application's label and the model's name in lower case, and the method fills four sets of such keys: `MigrationAutodetector.old_model_keys` and `MigrationAutodetector.old_proxy_keys` from the from-state, `MigrationAutodetector.new_model_keys` and `MigrationAutodetector.new_proxy_keys` from the to-state, a model going among the proxies when its options have a true `"proxy"`. A key in a new set alone is a model added, one in an old set alone a model removed, and one in both a model kept, whose fields and options are to be compared.

The from-state's `ProjectState.real_apps` holds the labels of the unmigrated applications, which the loader passes to it; no migration made their models, and the from-state has none of them (`django/db/migrations/loader.py:MigrationLoader.project_state`). The to-state has them, and there a model of such an application goes into no set unless its label is in the set to convert. So a plain makemigrations makes nothing for an application with no `migrations` package, and one that names the application makes its first migration.

> **Trap.** With no leaf node in the graph, `MigrationGraph.make_state` returns a project state whose `real_apps` is empty (`django/db/migrations/graph.py:MigrationGraph.make_state`). In a project with no migrations at all, the sorting therefore leaves no application out: migrations are made for every application that has a model, and `MigrationAutodetector.arrange_for_graph` discards those of an application for which `MigrationQuestioner.ask_initial` answers no, as makemigrations' questioner does for one that was not named and has no `migrations` package ([The makemigrations command](makemigrations.md)).

> **Changed in 6.2.** A model with `managed = False` is sorted like any other: there is no set of keys for unmanaged models. The release notes say that makemigrations now tracks all changes to unmanaged models, and that it will detect new migrations for those that have changed since they were created (`docs/releases/6.2.txt`).

Then the **generators** run, the methods of the autodetector named for one kind of change each. This is their order, from an autodetector called as the first makemigrations of harbour, the chapter's example project, calls it. In the recordings here, from a running Django, only the lines a passage is about are written and what ran between them is left out: a line is a call, with the number of operations a generator added in parentheses; an operation, after its application's label and with what it waits for in square brackets; or an edit to the models, given to the recording's detect as the operations that would make it, and after `->` the migrations the autodetector returned.

```text recording=migrations
MigrationAutodetector.generate_renamed_models  (no operation added)
MigrationAutodetector._prepare_field_lists
MigrationAutodetector._generate_through_model_map
MigrationAutodetector.generate_deleted_models  (no operation added)
MigrationAutodetector.generate_created_models  (29 operations added)
MigrationAutodetector.generate_deleted_proxies  (no operation added)
MigrationAutodetector.generate_created_proxies  (1 operation added)
MigrationAutodetector.generate_altered_options  (no operation added)
MigrationAutodetector.generate_altered_managers  (no operation added)
MigrationAutodetector.generate_altered_db_table_comment  (no operation added)
...
MigrationAutodetector.generate_altered_db_table  (no operation added)
MigrationAutodetector._sort_migrations
MigrationAutodetector._build_migration_list
MigrationAutodetector._optimize_migrations
```

Renames have to come first: `MigrationAutodetector.generate_renamed_models` moves a renamed model's key in `old_model_keys` to its new name, so that the model counts as kept, and later generators find its old state through `MigrationAutodetector.renamed_models`. The calls left out at the dots are those for fields and for what names fields: constraints, indexes and entries of `"unique_together"` are removed first, then fields are removed, added and altered, then `"unique_together"`, indexes and constraints are added. Those calls and the two after the renames that prepare for them are in [The autodetector: fields, indexes and constraints](autodetector-fields.md).

A generator returns nothing: it gives each operation to `MigrationAutodetector.add_operation`, which adds it to its application's list in `MigrationAutodetector.generated_operations` and sets on it the dependencies the generator named, each a model or a field and what must first have become of it (`django/db/migrations/autodetector.py:MigrationAutodetector.add_operation`). The last three calls reorder each list by those dependencies, cut the lists into migrations and put each migration through the optimizer; all that, and the naming and trimming that follow `_detect_changes`, is in [From operations to migrations: dependencies, order and names](dependencies.md).

## Comparing two fields: `deep_deconstruct`

Two fields cannot be compared with `==`: a field's equality compares creation counters and models, its place and not its definition (`django/db/models/fields/__init__.py:Field.__eq__`). What can be compared is what `Field.deconstruct` returns, the path of the class and the arguments that would make the field again ([A field: the base class](../models/fields.md)), and `MigrationAutodetector.deep_deconstruct` is that, carried all the way down (`django/db/migrations/autodetector.py:MigrationAutodetector.deep_deconstruct`).

One level is not enough where an argument is itself a field: a `GeneratedField` has one in `GeneratedField.output_field`, which `deconstruct` returns as it is and `==` would again compare by place. So the method goes into lists, tuples and dicts, turns a `functools.partial` into its function, arguments and keywords, and for anything with a `deconstruct` method keeps the path and deconstructs each argument, dropping a field's name first. A compiled regular expression becomes a `RegexObject`, equal to another of the same pattern and flags (`django/db/migrations/utils.py:RegexObject`). A class is returned as it is: one that declares `deconstruct` for its instances has the attribute too, and is not itself to be deconstructed. So is anything else.

`MigrationAutodetector.only_relation_agnostic_fields` is a coarser view of a whole model, used to recognise a rename: the deep deconstructions of its fields, in the order of the fields' names and without the names (`django/db/migrations/autodetector.py:MigrationAutodetector.only_relation_agnostic_fields`). A relation's `"to"` is taken out, since a relation to the renamed model itself names it differently in the two states.

## Renamed models: `generate_renamed_models`

A model added and a model removed may be one model under a new name, and the states cannot say. `MigrationAutodetector.generate_renamed_models` looks, for each added model, among the removed models of the same application for one with equal `MigrationAutodetector.only_relation_agnostic_fields`, and on a match asks the questioner's `MigrationQuestioner.ask_rename_model` (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_renamed_models`). On a yes it adds a `RenameModel`, records the old name under the new key in `MigrationAutodetector.renamed_models`, and puts the new key in place of the old in `MigrationAutodetector.old_model_keys`. Without a match there is no question: a model whose fields' definitions changed in the same edit is created and its predecessor deleted.

In the first of two runs Dock, a model of the example that Repair points at, is renamed Basin, and the questioner has a yes ready. In the second a field was altered in the same edit, and the answer was never asked for: the migration returned would drop Dock's table, with its rows, and make another for Basin.

```text recording=migrations
detect(after=[migrations.RenameModel('Dock', 'Basin')], ask_rename_model=True)  ->  yard.0002_rename_dock_basin: [RenameModel: Rename model Dock to Basin]
...
detect(after=[migrations.RenameModel('Dock', 'Basin'), migrations.AlterField('basin', 'name', models.CharField(max_length=80))], ask_rename_model=True)  ->  yard.0002_basin_alter_repair_dock_delete_dock: [CreateModel: Create model Basin (fields id, name, port), AlterField: Alter field dock on repair (ForeignKey(on_delete=PROTECT, to='yard.basin')), DeleteModel: Delete model Dock]
```

## Created models: `generate_created_models`

`MigrationAutodetector.generate_created_models` takes each added model, at harbour's first makemigrations every model but the proxy, and may make several operations of it. It adds a `CreateModel` without the model's relations, a primary key and a parent link excepted, and then, each an operation of its own, an `AddField` for each relation left out, an `AlterOrderWithRespectTo` for `"order_with_respect_to"`, an `AddIndex` for each index, an `AddConstraint` for each constraint and an `AlterUniqueTogether` for `"unique_together"` (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_created_models`). Harbour's Ship and Sailor at its first makemigrations, as the generators left them:

```text recording=migrations
fleet: CreateModel: Create model Ship (fields id, name, tonnage; options ordering=['name'], abstract=False)  [needs (fleet, ship) removed]
...
fleet: AddField: Add field captain to ship (OneToOneField(blank=True, null=True, related_name='command', on_delete=SET_NULL, to='crew.sailor'))  [needs (crew, sailor) created; needs (fleet, ship) created]
...
crew: CreateModel: Create model Sailor (fields id, name, signed_on)  [needs (crew, sailor) removed]
...
crew: AddField: Add field ship to sailor (ForeignKey(related_name='crew', on_delete=CASCADE, to='fleet.ship'))  [needs (crew, sailor) created; needs (fleet, ship) created]
```

The splitting is what makes an order possible. A `CreateModel` with a foreign key inside needs the other model first, and Ship and Sailor point at each other from two applications. Split, neither `CreateModel` waits for the other and each `AddField` waits for both. A `CreateModel` itself waits for the removal of a model with its key, which matters when a proxy becomes a model with a table, for its base models, and for the model that a primary key which is a relation points at ([From operations to migrations: dependencies, order and names](dependencies.md)). The optimizer later folds an `AddField` into a `CreateModel` of the same migration where it can ([The optimizer: `MigrationOptimizer` and `reduce`](optimizer.md)). An `AddIndex`, an `AddConstraint` and an `AlterUniqueTogether` each depend on every split-off field of the model, since they may name one.

The added models are sorted by `MigrationAutodetector.swappable_first_key`, which, by its docstring, places models that may be swapped, the one `AUTH_USER_MODEL` names among them, first in the lists of created models (`django/db/migrations/autodetector.py:MigrationAutodetector.swappable_first_key`). For a new proxy `MigrationAutodetector.generate_created_proxies` adds a `CreateModel` with no fields, and for one removed `MigrationAutodetector.generate_deleted_proxies` adds a `DeleteModel` (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_created_proxies`).

## Deleted models: `generate_deleted_models`

For each removed model `MigrationAutodetector.generate_deleted_models` adds an `AlterUniqueTogether` that empties `"unique_together"` where there is one, a `RemoveIndex` for each index, a `RemoveConstraint` for each constraint, a `RemoveField` for every relation, primary key and parent link included, and last the `DeleteModel` (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_deleted_models`). Dependencies hold this much of that order through the sorting: a `RemoveField` waits for the removal of the model's indexes and constraints, and the `DeleteModel` for the removal of its own relations. The `DeleteModel` waits too for every field that points at the model to be removed or, unless it is many-to-many, altered.

## Options, managers and the table

The generators of options, managers and the table each compare one thing in a model's two model states and, where it differs, add one operation with the new value.

| generator | compares | for | adds |
|---|---|---|---|
| `MigrationAutodetector.generate_altered_options` | the options under the keys of `AlterModelOptions.ALTER_OPTION_KEYS` | kept models and kept proxies | `AlterModelOptions` |
| `MigrationAutodetector.generate_altered_managers` | the lists of managers | kept models | `AlterModelManagers` |
| `MigrationAutodetector.generate_altered_db_table_comment` | `"db_table_comment"` | kept models and kept proxies | `AlterModelTableComment` |
| `MigrationAutodetector.generate_altered_db_table` | `"db_table"` | kept models and kept proxies | `AlterModelTable` |

*What each of these generators compares, and the operation it adds.*

Among the keys of `ALTER_OPTION_KEYS` are `"managed"`, `"ordering"`, `"permissions"` and `"verbose_name"`; the docstring of `generate_altered_options` calls such options non-schema-affecting, kept in the state in case Python code in migrations needs them (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_options`). The lists of managers are compared with `!=`, and a manager is equal to an instance of its class that was made with the same arguments (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_managers`, `django/db/models/manager.py:BaseManager.__eq__`).
