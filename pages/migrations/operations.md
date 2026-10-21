---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Operations: the base class and its two halves

An operation is one change that a migration makes, an instance of a subclass of `django.db.migrations.operations.base.Operation`. It can make the change in two places: its state half, `Operation.state_forwards`, in a project state, and its database half, `Operation.database_forwards` and `Operation.database_backwards`, in a database. The base class also keeps the arguments an operation was made with, for `Operation.deconstruct`, and gives every operation its flags, its description and `Operation.allow_migrate_model`.

Django needs to know what the models were at any point of the history without going near a database: the project state that makemigrations compares the models with is made by running state halves alone (`django/db/migrations/migration.py:Migration.mutate_state`). Changing a schema is another matter, and an operation's own arguments are not enough for it: an `AlterField` holds the field as it is to be, and the schema editor's `alter_field` wants the field as it was too. The database half is handed two project states, the one before the operation and the one after, and finds both fields in them; the state half makes the second out of the first.

```text figure=two-halves
AddField(model_name='dock', name='metres', field=...), in a migration of yard

state half: state_forwards('yard', state)
    ProjectState.add_field: the model state yard.Dock gains the field metres

database half: database_forwards('yard', schema editor, from-state, to-state)
    from-state: the project state before the state half ran, Dock without metres
    to-state: the project state after it, Dock with metres
    the historical model yard.Dock from each state's registry  ->  the schema editor's add_field
```

*The two halves of one operation, an `AddField` on yard's Dock: what each is given, and what it changes.*

The operations themselves are in [The model operations: `CreateModel`, `DeleteModel`, `RenameModel` and the option operations](model-operations.md), [The field operations, and those on indexes and constraints](field-operations.md) and [`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](special-operations.md).

## `state_forwards`, `database_forwards` and `database_backwards`

`Operation` declares the methods of the two halves only to raise `NotImplementedError`. A subclass provides all three; every other member has a default in the base (`django/db/migrations/operations/base.py:Operation`).

The **state half** is given a project state, which it changes in place, and the label of the application whose migration holds the operation, which the operation itself does not know. In the operations that `django.db.migrations.operations` exports, set out in the table below, it calls methods of `ProjectState`, passes the call to operations it holds or, in `RunPython`, does nothing ([Project state: `ProjectState` and its model states](state.md)).

The **database half** is two methods with the same parameters: the label, a schema editor and two project states. Forwards, the **from-state** is the state before the operation and the **to-state** the state after (`django/db/migrations/migration.py:Migration.apply`). Backwards they change places: either way the from-state describes the database as the method finds it and the to-state as it is to leave it. No state half runs backwards: `Migration.unapply` first runs the state halves forwards and keeps the states between ([A migration: its operations, its dependencies and how it is applied](migration.md)).

## The shape of a database half

Apart from `RunSQL`, `RunPython` and `SeparateDatabaseAndState`, and from the operations whose database halves do nothing, each of those operations has a database half of one shape (`django/db/migrations/operations/fields.py:AddField.database_forwards`). Forwards, it takes the historical model from the to-state's registry, `ProjectState.apps`, or in `DeleteModel`, `RemoveField` and `RemoveIndex` from the from-state's, which still has what they remove. It asks `Operation.allow_migrate_model` whether the schema editor's connection is to have that model, and returns without a word if not (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`). Then it looks up whatever else the change needs, for an `AddField` the from-state's model, and calls the schema editor where there is something to change ([Historical models: `StateApps` and rendering](historical-models.md), [The schema editor: `BaseDatabaseSchemaEditor`](../schema/editor.md)).

`allow_migrate_model` asks the model's options before any router: `Options.can_migrate` is false for a proxy, a swapped-out or an unmanaged model, and for one whose `Options.required_db_vendor` is another vendor than the connection's or, with no vendor named, whose `Options.required_db_features` include a feature the connection lacks (`django/db/models/options.py:Options.can_migrate`). Only for a model that passes is the router asked, by `ConnectionRouter.allow_migrate_model`, which hands the routers the historical model among their hints ([Routing between databases: `ConnectionRouter`](../connections/routers.md)).

A recording is of a running Django, here on SQLite: a line is a call, set in under the call that made it, or Python as it was run; `->` is followed by what came back, parentheses name the class that declares a method where the object's class is another, square brackets hold an operation's description, and only the lines a passage is about are written, the rest left out. This one is the database half of an `AddField` of a field metres to yard's Dock, called by hand with two project states: the recording's from_state, which lacks the field, and its to_state, a clone of that on which the state half had been run.

```text recording=migrations
AddField.database_forwards(from_state=from_state, to_state=to_state)  [Add field metres to dock]
  AddField.allow_migrate_model(connection_alias='default', model=the historical model yard.Dock)  (Operation.allow_migrate_model)
    Options.can_migrate('default')  ->  True
    ConnectionRouter.allow_migrate_model(db='default', model=the historical model yard.Dock)
      -> True
    -> True
  DatabaseSchemaEditor.add_field(model=the historical model yard.Dock, field=the field yard.Dock.metres)
```

A refusal by `Operation.allow_migrate_model` is silent. The state half has run, the migration goes on to its next operation, and the executor writes the migration's row as for any other: a database that a router keeps a model out of has the row and no table for the model (`django/db/migrations/executor.py:MigrationExecutor.apply_migration`).

The database halves that do nothing are those of `AlterModelOptions`, `AlterModelManagers` and `AlterConstraint`: their change lives in the state alone. `RunSQL` and `RunPython` concern no model and never call `allow_migrate_model`: each asks `ConnectionRouter.allow_migrate` itself, with the application's label and the hints it was made with (`django/db/migrations/operations/special.py:RunPython.database_forwards`). `SeparateDatabaseAndState` asks nothing and hands on to the operations it holds.

## An operation as a value

The writer turns an operation into the text of a call that makes it again, and asks the operation for the arguments it was made with. `Operation.__new__` runs before any subclass's `__init__` and keeps the positional and the keyword arguments of the call on the instance, as the pair `_constructor_args` (`django/db/migrations/operations/base.py:Operation.__new__`). `Operation.deconstruct`, which `OperationWriter.serialize` calls, returns the class's name and the two members of that pair ([Writing a migration file: `MigrationWriter`](../makemigrations/writer.md)). None of those operations is left with the base's `deconstruct`: each builds its arguments from the instance's attributes. The base's serves an operation that defines none, such as `CreateExtension` of `django.contrib.postgres.operations` ([The PostgreSQL application: `PostgresConfig`, operations and aggregates](../contrib/postgres.md)).

`Operation.__replace__` makes another operation of the same class from the kept arguments with some of them changed: a change is given by keyword, and a positional argument is matched to it by its name in the class's signature, as the last line below shows (`django/db/migrations/operations/base.py:Operation.__replace__`). `copy.replace` calls it, as does Django's own copy of that function for Python 3.12 (`django/utils/copy.py`). That is how `CreateModel.reduce`, asked by the optimizer about a later `RenameModel` of its model, answers with the `CreateModel` made again under the new name (`django/db/migrations/operations/models.py:CreateModel.reduce`; [The optimizer: `MigrationOptimizer` and `reduce`](../makemigrations/optimizer.md)). In the recording an `AddField` is made with positional arguments and asked what it kept and what its own `deconstruct` returns, and a copy is asked what it kept:

```text recording=migrations
positional = migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120), False)
positional._constructor_args  ->  (('dock', 'metres', an unbound PositiveSmallIntegerField, False), {})
positional.deconstruct()  ->  ('AddField', [], {'model_name': 'dock', 'name': 'metres', 'field': an unbound PositiveSmallIntegerField, 'preserve_default': False})
...
copy.replace(positional, name='length')._constructor_args  ->  (('dock', 'length', an unbound PositiveSmallIntegerField, False), {})
```

The class's docstring says an operation is to be considered immutable. The kept arguments do not follow an attribute assigned later: assign an `AddField` another name and its `deconstruct`, which reads the attribute, reports the new one, while a copy made by `__replace__` has the old.

## The flags

Class attributes of `Operation` say how an operation may be run (`django/db/migrations/operations/base.py:Operation`, `django/db/migrations/migration.py:Migration.unapply`; [A migration: its operations, its dependencies and how it is applied](migration.md)).

- `Operation.reversible`, true in the base: whether the operation can be run backwards, read by `Migration.unapply`. `RunSQL` and `RunPython` make it a property, true where they were given something to run backwards.
- `Operation.reduces_to_sql`, true in the base: whether the operation can be written as SQL, read by `Migration.apply` and `Migration.unapply` where statements are collected and not sent, as for sqlmigrate. `RunPython` alone sets it false.
- `Operation.atomic`, false in the base: whether the operation is to be run in an atomic block even on a backend that cannot roll back DDL, which its comment says is for an operation that has no DDL, like `RunPython`. `Migration.apply` and `Migration.unapply` read it with the migration's own `atomic`, and `RunPython` takes it as an argument.
- `Operation.elidable`, false in the base: whether `Operation.reduce` may leave the operation out of a list being optimized. `RunSQL` and `RunPython` take it as an argument.

## `category`, `describe` and the name fragment

`Operation.describe` returns a phrase for the operation; none of those operations is left with the base's, which falls back on the class's name and the kept arguments (`django/db/migrations/operations/base.py:Operation.describe`). `Operation.category` is a member of `OperationCategory`, an `enum.StrEnum` whose values are signs: `ADDITION` is `"+"`, `REMOVAL` `"-"`, `ALTERATION` `"~"`, `PYTHON` `"p"`, `SQL` `"s"` and `MIXED` `"?"`. `Operation.formatted_description` puts the sign and a space before the description, with `"?"` for a category of `None`, the base's.

Unless its verbosity is 0, makemigrations prints the formatted description of each operation of a migration it writes or, under `--dry-run`, would write, and of the branches it is asked to merge (`django/core/management/commands/makemigrations.py:Command.write_migration_files`, `django/core/management/commands/makemigrations.py:Command.handle_merge`); sqlmigrate and `migrate --plan` use `describe` and so show no sign. `Operation.migration_name_fragment` is a property: the operation's part of a name for the migration that holds it, read by `Migration.suggest_name` ([A migration: its operations, its dependencies and how it is applied](migration.md)), and `None` in the base and in `RunSQL`, `RunPython` and `SeparateDatabaseAndState`.

## What the optimizer asks

The optimizer, which shortens a list of operations, asks an operation through `Operation.reduce` about one that comes later in the list: the answer is a list of operations to stand in place of both, or true or false for whether the two may change places (`django/db/migrations/operations/base.py:Operation.reduce`; [The optimizer: `MigrationOptimizer` and `reduce`](../makemigrations/optimizer.md)). The `reduce` methods in turn ask `Operation.references_model` and `Operation.references_field` whether an operation has anything to do with a model or a field. The docstring's rule is: when in doubt, true, since a wrong true only costs the optimizer some efficiency and a wrong false may leave a migration that cannot be used. The base's answer to both is true.

## The operations of `django.db.migrations.operations`

The exported operations are the classes of this table, and `django.db.migrations` exports them again, which is where a migration file finds them (`django/db/migrations/operations/__init__.py`, `django/db/migrations/__init__.py`).

| class | category | state half | database half, forwards |
|---|---|---|---|
| `CreateModel` | `ADDITION` | `add_model` | `create_model`; `alter_index_together` where the model state has `"index_together"` |
| `DeleteModel` | `REMOVAL` | `remove_model` | `delete_model` |
| `RenameModel` | `ALTERATION` | `rename_model` | `alter_db_table`; `alter_field` for fields pointing at the model; `_alter_many_to_many` for many-to-many tables of its own |
| `AlterModelTable` | `ALTERATION` | `alter_model_options` | `alter_db_table`, for the model's table and each many-to-many table made for it |
| `AlterModelTableComment` | `ALTERATION` | `alter_model_options` | `alter_db_table_comment` |
| `AlterUniqueTogether` | `ALTERATION` | `alter_model_options` | `alter_unique_together` |
| `AlterIndexTogether` | `ALTERATION` | `alter_model_options` | `alter_index_together` |
| `AlterOrderWithRespectTo` | `ALTERATION` | `alter_model_options` | `add_field` or `remove_field` of the column `"_order"`, where the option is gained or lost |
| `AlterModelOptions` | `ALTERATION` | `alter_model_options` | nothing |
| `AlterModelManagers` | `ALTERATION` | `alter_model_managers` | nothing |
| `AddField` | `ADDITION` | `add_field` | `add_field` |
| `RemoveField` | `REMOVAL` | `remove_field` | `remove_field` |
| `AlterField` | `ALTERATION` | `alter_field` | `alter_field` |
| `RenameField` | `ALTERATION` | `rename_field` | `alter_field` |
| `AddIndex` | `ADDITION` | `add_index` | `add_index` |
| `RemoveIndex` | `REMOVAL` | `remove_index` | `remove_index` |
| `RenameIndex` | `ALTERATION` | `rename_index`; given `old_fields`, the fields of an index that has no name in the state, `add_index` and `remove_model_options` | `rename_index`, unless the name is unchanged; given `old_fields`, `_constraint_names` first, to find the index's name |
| `AddConstraint` | `ADDITION` | `add_constraint` | `add_constraint` |
| `RemoveConstraint` | `REMOVAL` | `remove_constraint` | `remove_constraint` |
| `AlterConstraint` | `ALTERATION` | `alter_constraint` | nothing |
| `RunSQL` | `SQL` | the state halves of its `state_operations` | `execute`, for each statement |
| `RunPython` | `PYTHON` | nothing | its function, given the from-state's registry and the schema editor |
| `SeparateDatabaseAndState` | `MIXED` | the state halves of its `state_operations` | the database halves of its `database_operations` |

*The rows from `AlterModelTable` to `AlterModelManagers` inherit their category from `ModelOptionOperation`. The state half's methods are `ProjectState`'s and the database half's the schema editor's (`django/db/migrations/operations/`).*
