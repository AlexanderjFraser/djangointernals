---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The optimizer: `MigrationOptimizer` and `reduce`

The optimizer, a `MigrationOptimizer`, shortens a list of operations: a model created and then given a field becomes a model created with that field, and a field added and then removed becomes nothing. It knows no operation itself: it asks each one, through its method `reduce`, what to make of a later one, and operations answer with the help of `references_model` and `references_field`. The command optimizemigration runs it over one migration file.

Besides that command, Django runs the optimizer wherever it writes operations it has put together itself. The autodetector runs it on each migration it has cut, which puts back into a `CreateModel`, where it can, the relations, indexes and constraints the autodetector wrote as operations apart from it (`django/db/migrations/autodetector.py:MigrationAutodetector._optimize_migrations`; [From operations to migrations: dependencies, order and names](dependencies.md)). squashmigrations runs it, unless given `--no-optimize`, on the operations of all the migrations it replaces (`django/core/management/commands/squashmigrations.py:Command.handle`; [Rewriting migrations: `--update`, squashmigrations and optimizemigration](rewriting.md)). `makemigrations --update`, which folds new operations into an application's last migration, runs it on the lengthened list (`django/core/management/commands/makemigrations.py:Command.write_to_last_migration_files`; [Rewriting migrations: `--update`, squashmigrations and optimizemigration](rewriting.md)).

## `reduce`: one question, three kinds of answer

The optimizer calls `Operation.reduce` on one operation with another that stands later in the list, and with the label of the list's application, which an operation does not hold (`django/db/migrations/operations/base.py:Operation.reduce`). A list says: put these in place of the two of us. That is a **fold**: the list is empty where the two cancel, holds one operation where they merge, and of Django's own only `AlterField.reduce` returns two. `True` says: no fold, but the two may change places. `False` says: no fold, and the later may not be moved in front of the earlier.

The base class ([Operations: the base class and its two halves](../migrations/operations.md)) answers `False` but for one case, `Operation.elidable`. An elidable operation answers any later one with a list of that one alone, and so drops out; an operation asked about a later one that is elidable answers with a list of itself. `elidable` is `False` on the class, and `RunSQL` and `RunPython` take it as an argument, by which a migration's author marks an operation that is safe to leave out ([`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](../migrations/special-operations.md)).

In the recordings here, of a running Django, only the lines a passage is about are written, the rest left out: a line with `=` is Python as it was run; `->` is followed by what a call returned, and the calls it made are set in under it; `python manage.py` begins a command line and `stdout |` a line it printed, the path less the directory the recording ran in; an operation is written as its class, its description and, in parentheses, what the recording adds to tell it apart.

```text recording=migrations
create = migrations.CreateModel('Crane', [('id', models.BigAutoField(primary_key=True))])
tonnes = migrations.AddField('crane', 'tonnes', models.PositiveSmallIntegerField(default=5))
...
no_crane = migrations.DeleteModel('Crane')
metres = migrations.AddField('dock', 'metres', models.PositiveSmallIntegerField(default=120))
...
sql = migrations.RunSQL('UPDATE yard_dock SET name = name')
passing = migrations.RunSQL('UPDATE yard_dock SET name = name', elidable=True)
create.reduce(tonnes, 'yard')  ->  [CreateModel: Create model Crane (fields id, tonnes)]
create.reduce(no_crane, 'yard')  ->  []
...
tonnes.reduce(metres, 'yard')  ->  True
...
sql.reduce(tonnes, 'yard')  ->  False
tonnes.reduce(sql, 'yard')  ->  False
passing.reduce(tonnes, 'yard')  ->  [AddField: Add field tonnes to crane (PositiveSmallIntegerField(default=5))]
```

Every `reduce` Django ships falls back on the base's where it has no fold of its own, so an elidable operation drops out beside any operation of Django's. `RunSQL`, `RunPython` and `SeparateDatabaseAndState` declare neither `reduce` nor `references_model`, the question a model operation puts to a later one before it lets the two change places: do you refer to my model? `Operation.references_model` says yes, `True`, whatever the model. So unless one of the two is elidable, such an operation answers `False` about every other, and every other answers `False` about it. It is a **boundary**: nothing changes places with it. So is an operation of a project's own that overrides nothing.

## `MigrationOptimizer.optimize`: one fold to a pass

`MigrationOptimizer.optimize` calls `MigrationOptimizer.optimize_inner` on the list, and again on what that returned, until a call returns a list equal to the one it was given (`django/db/migrations/optimizer.py:MigrationOptimizer.optimize`); its docstring draws the consequence, that a fold must never return a list longer than what it replaces. Each call is a **pass**, and a pass makes at most one fold. Here the list is the `CreateModel` of Crane, the `AddField` of its field tonnes and an `AlterField` of that field.

```text recording=migrations
MigrationOptimizer.optimize(<3 operations>, 'yard')
  MigrationOptimizer.optimize_inner(<3 operations>)  ->  [CreateModel: Create model Crane (fields id, tonnes), AlterField: Alter field tonnes on crane (PositiveIntegerField(default=5))]
  MigrationOptimizer.optimize_inner(<2 operations>)  ->  [CreateModel: Create model Crane (fields id, tonnes)]
  MigrationOptimizer.optimize_inner(<1 operations>)  ->  [CreateModel: Create model Crane (fields id, tonnes)]
```

In a pass, `optimize_inner` takes each operation in turn and asks it about every operation after it, nearest first (`django/db/migrations/optimizer.py:MigrationOptimizer.optimize_inner`). `True` lets the scan go on, and so does `False`, which is noted. The first list ends the scan, and the pass must decide where its operations are to stand, since the operations between the two must go to one side of them.

- **To the right.** If no answer before this one was `False`, the earlier operation could be moved across everything between: the operations between keep their places, and the list stands after them.
- **To the left.** Otherwise the pass asks each operation between about the later one. If every one answers `True`, the later operation could be moved across them all: the list stands where the earlier operation stood, and the operations between follow.
- If neither holds, the earlier operation stays and the pass goes on to the operation after it; the scan is not taken up again, and so misses any fold with an operation further on.

In the figure's first list the field added to Crane is a foreign key to Hook, a model created between, and the merged operation goes right, after the model it now points at. In its second, Hook has a foreign key to Crane, and the merged operation goes left, before the model that points at it.

```text figure=right-and-left
to the right:  CreateModel Crane (id)  /  CreateModel Hook (id)  /  AddField hook to crane, a foreign key to Hook
               Crane's CreateModel about Hook's  ->  True
               becomes  CreateModel Hook (id)  /  CreateModel Crane (id, hook)

to the left:   CreateModel Crane (id)  /  CreateModel Hook (id, crane), a foreign key to Crane  /  AddField tonnes to crane
               Crane's CreateModel about Hook's  ->  False;  Hook's about the AddField  ->  True
               becomes  CreateModel Crane (id, tonnes)  /  CreateModel Hook (id, crane)
```

*Two lists, each folded in one pass, one to the right and one to the left.*

## The model operations

`ModelOperation.reduce` answers with `Operation.reduce`'s list where there is one, and otherwise with `ModelOperation.can_reduce_through`: true exactly when the later operation's `references_model`, asked about this operation's model, says no (`django/db/migrations/operations/models.py:ModelOperation.reduce`). `DeleteModel` has no more than this. `CreateModel.reduce` has a fold for each of these operations on its own model (`django/db/migrations/operations/models.py:CreateModel.reduce`).

| the later operation | what the `CreateModel` answers |
|---|---|
| `DeleteModel` | an empty list, unless the model is a proxy |
| `RenameModel` | itself under the new name |
| `AlterModelOptions` | its options with the operation's laid over them, less any key of `AlterModelOptions.ALTER_OPTION_KEYS` the operation leaves out |
| `AlterModelManagers` | the operation's managers in place of its own |
| `AlterModelTable`, `AlterModelTableComment`, `AlterUniqueTogether`, `AlterIndexTogether`, `AlterOrderWithRespectTo` | the one option the operation is about, set to its value |
| `AddField` | the field put last among its fields |
| `AlterField` | the field of that name replaced |
| `RemoveField` | the field taken out, its name taken out of `"unique_together"` and `"index_together"`, and `"order_with_respect_to"` dropped where it named the field |
| `RenameField` | the field renamed, among the fields and in those three options |
| `AddIndex`, `AddConstraint` | the index or constraint put last in `"indexes"` or `"constraints"` |
| `RemoveIndex`, `RemoveConstraint` | the index or constraint of that name taken out |
| `AlterConstraint` | the constraint of that name taken out and the new one put last |

*What `CreateModel.reduce` answers: but for the first row, a list of one `CreateModel`, a changed copy of itself. A `RenameIndex`, a proxy's `DeleteModel` and an operation on another model get the answer of `ModelOperation.reduce`.*

`RenameModel.reduce` answers a later `RenameModel` from its new name with one rename; for anything else it passes over `ModelOperation.reduce`, which would test its old name, and tests the later operation against its new one. `ModelOptionOperation.reduce`, which the operations that alter a model's options or its managers inherit, answers an operation of its own class on its model, or a `DeleteModel` of it, with a list of the later one alone (`django/db/migrations/operations/models.py:ModelOptionOperation.reduce`). `AlterTogetherOptionOperation.can_reduce_through` adds that an `AlterUniqueTogether` and an `AlterIndexTogether`, the two subclasses of that class, let each other through on one model, so that two of one kind fold across one of the other.

## The field operations

`FieldOperation.reduce` answers with `Operation.reduce`'s list where there is one, and otherwise with true exactly when the later operation's `references_field`, asked about this operation's field, says no (`django/db/migrations/operations/fields.py:FieldOperation.reduce`). Its subclasses add folds, comparing names in lower case.

`AddField.reduce` answers a later operation on its field: an `AlterField` with an `AddField` of the altered field, a `RemoveField` with nothing, a `RenameField` with an `AddField` under the new name. `RemoveField.reduce` answers a `DeleteModel` of its model with the `DeleteModel`. `AlterField.reduce` answers a later `AlterField` or `RemoveField` of its field with the later operation, and a `RenameField` of it, where the altered field has no `db_column`, with the rename and then a copy of itself under the new name: a list no shorter than the two, but its `AlterField` can then fold with an `AlterField` or a `RemoveField` after the rename. `RenameField.reduce` answers a `RenameField` of the same model from its new name with one rename; for anything else it passes over `FieldOperation.reduce` and tests the later operation against both its names.

> **Trap.** A `CreateModel` has nowhere to keep `preserve_default=False`, so a default typed only for the rows that existed becomes the model's: squashing the example's yard folded the `AddField` of Repair's foreman into its `CreateModel` with `default='not recorded'`, and the next makemigrations wrote an `AlterField` to take it out. Where an `AddField` folded with an `AlterField` under `makemigrations --update`, the example lost a typed default instead ([Rewriting migrations: `--update`, squashmigrations and optimizemigration](rewriting.md)).

## Indexes and constraints, and a cautious `references_model`

`IndexOperation`, the base of the operations on indexes and constraints, declares none of `reduce`, `references_model` and `references_field` (`django/db/migrations/operations/models.py:IndexOperation`). `AddIndex.reduce` answers a `RemoveIndex` of its index's name with nothing and a `RenameIndex` from that name with an `AddIndex` of a renamed copy, comparing names and not models. `RenameIndex.reduce` answers a `RenameIndex` on its model, from its new name, with one rename. `AddConstraint.reduce` answers a `RemoveConstraint` of its model and name with nothing, and an `AlterConstraint` of them with an `AddConstraint` of the new constraint. `AlterConstraint.reduce` answers a later `AlterConstraint` or `RemoveConstraint` of its model and name with the later operation. To everything else they, like `RemoveIndex` and `RemoveConstraint`, give the base's answers: but for these folds and `CreateModel`'s, each is a boundary.

`Operation.references_model` returns `True` by the rule in its docstring: if in doubt, return true, since a true too many makes the optimizer a little less efficient and a false too many may leave an optimized migration that cannot be used (`django/db/migrations/operations/base.py:Operation.references_model`); `Operation.references_field` falls back on it. The model and field operations declare narrower ones ([The field operations, and those on indexes and constraints](../migrations/field-operations.md)); `DeleteModel` alone declares one that returns `True` for every model, since the model it deletes may point at any other.

The example project's first makemigrations shows what the caution costs: fleet's migration left the optimizer with Ship's index and two constraints as operations of their own. Voyage's `CreateModel` stood between and pointed at Ship, so the fold of Ship's `CreateModel` with the `AddIndex` could not go right, and Voyage's `CreateModel` answered `False` about the `AddIndex`, whose `references_model` is the base's, so the fold could not go left.
