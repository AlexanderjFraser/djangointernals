---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The autodetector: fields, indexes and constraints

For a model that both project states have, `MigrationAutodetector` compares what the model is made of: its fields, its indexes, its constraints, and the options `unique_together` and `order_with_respect_to`. The differences become `RenameField`, `AddField`, `RemoveField` and `AlterField`, the operations on indexes and constraints, `AlterUniqueTogether` and `AlterOrderWithRespectTo`.

The methods here tell that a field has changed by what `MigrationAutodetector.deep_deconstruct` makes of it: the path of its class and the arguments that would make it again, without its name ([The autodetector: comparing two project states](autodetector.md)).

The example, recorded from a running Django, is yard, a repair yard whose two models have just been edited. In the quotes of the recording a line that names a method is a call, set in under the call that made it, with `->` before what it returned and, in words in parentheses, the recording's count of the operations it appended; `stdout |` begins a line a command printed; and only the lines a passage is about are quoted, what ran between them left out.

```text recording=migrations
The models of yard, second version: harbour/yard/models.py, each line put in marked + and each line taken out marked -; four changes at once: Dock.name made longer, Dock.metres added, Repair.started renamed begun, and an index on Repair
    |   from django.db import models
    |
    |
    |   class Dock(models.Model):
    |       """A dry dock of the repair yard, in one of the fleet's ports."""
    |
    | -     name = models.CharField(max_length=40)
    | +     name = models.CharField(max_length=80)
    |       port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    | +     metres = models.PositiveSmallIntegerField(default=120)
    |
    |
    |   class Repair(models.Model):
    |       """A ship in a dock, under repair."""
    |
    |       ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE)
    |       dock = models.ForeignKey(Dock, on_delete=models.PROTECT)
    | -     started = models.DateField()
    | +     begun = models.DateField()
    |       notes = models.TextField(blank=True)
    | +
    | +     class Meta:
    | +         indexes = [models.Index(fields=["dock", "begun"], name="repair_by_dock")]
```

## The field keys

`MigrationAutodetector._prepare_field_lists` turns the comparison of fields into arithmetic on sets (`django/db/migrations/autodetector.py:MigrationAutodetector._prepare_field_lists`). A **field key** is a tuple of an application's label, a model's name and a field's name, and the method makes two sets of them over the **kept models**, those in both states that `MigrationAutodetector.kept_model_keys` holds: `MigrationAutodetector.old_field_keys` from the model states of the from-state, which the migration files make, and `MigrationAutodetector.new_field_keys` from those of the to-state, read off the models. A model found to have been renamed counts as in both, its old fields keyed under its new name. A key in the new set alone is then a field added, one in the old set alone a field removed, and one in both a field to compare. Yard's new set alone has `("yard", "dock", "metres")` and `("yard", "repair", "begun")`, its old set alone `("yard", "repair", "started")`.

`MigrationAutodetector._generate_through_model_map`, called next, is for models that are deleted: it notes which field of the from-state uses each model named by a `through=`, and such a model's deletion is made to wait for that field's removal (`django/db/migrations/autodetector.py:MigrationAutodetector._generate_through_model_map`).

The methods that make the comparison were recorded in the order `MigrationAutodetector._detect_changes` calls them, for yard and a questioner that answers yes to a rename, with two of the calls of `MigrationAutodetector.deep_deconstruct`, those for Dock's name.

```text recording=migrations
MigrationAutodetector.create_renamed_fields
  MigrationQuestioner.ask_rename(model_name='repair', old_name='started', new_name='begun', field_instance=an unbound DateField)  ->  True
  (no operation added)
MigrationAutodetector.create_altered_indexes  (no operation added)
MigrationAutodetector.create_altered_constraints  (no operation added)
MigrationAutodetector.generate_removed_constraints  (no operation added)
MigrationAutodetector.generate_removed_indexes  (no operation added)
MigrationAutodetector.generate_renamed_fields  (1 operation added)
MigrationAutodetector.generate_renamed_indexes  (no operation added)
MigrationAutodetector.generate_removed_altered_unique_together  (no operation added)
MigrationAutodetector.generate_removed_fields  (no operation added)
MigrationAutodetector.generate_added_fields  (1 operation added)
MigrationAutodetector.generate_altered_fields
  MigrationAutodetector.deep_deconstruct(CharField(max_length=40))  ->  ('django.db.models.CharField', [], {'max_length': 40})
  MigrationAutodetector.deep_deconstruct(CharField(max_length=80))  ->  ('django.db.models.CharField', [], {'max_length': 80})
  (1 operation added)
MigrationAutodetector.generate_altered_order_with_respect_to  (no operation added)
MigrationAutodetector.generate_altered_unique_together  (no operation added)
MigrationAutodetector.generate_added_indexes  (1 operation added)
MigrationAutodetector.generate_added_constraints  (no operation added)
MigrationAutodetector.generate_altered_constraints  (no operation added)
```

The methods whose names begin with create append nothing: each works something out and keeps it for the generators after it. Those that remove constraints and indexes run before the generators of fields, and those that add them after ([The autodetector: comparing two project states](autodetector.md)). That is the order of each application's list of operations before it is sorted by the dependencies each operation was given.

## A rename, or a removal and an addition

Two states cannot tell a field renamed from one removed and another added: either way Repair has lost a date field called started and gained one called begun. `MigrationAutodetector.create_renamed_fields` finds each pair that could be a rename and has the questioner decide (`django/db/migrations/autodetector.py:MigrationAutodetector.create_renamed_fields`).

For each added field, in the order of the sorted keys, it goes through the removed fields of the same model for one that deconstructs as the added field does, a model renamed in this run being read by its new name. A field renamed and otherwise changed in one edit is no match, and nothing is asked about it, unless the change is a `db_column` that keeps the old column.

Each match is put to `MigrationQuestioner.ask_rename`, which is handed the new field: a field of a model state, bound to no model. After a no the search goes on to the next removed field. After a yes it ends: the pair is kept in `MigrationAutodetector.renamed_operations`, and `MigrationAutodetector.renamed_fields` gets the old name under the new field's key.

The operation is written later, by `MigrationAutodetector.generate_renamed_fields`: a `RenameField` with the model's name and the two field names (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_renamed_fields`). Where a `db_column` was added to keep the old column, an `AlterField` of the old name to the new field goes in front of it. The method then puts the new key in place of the old in `MigrationAutodetector.old_field_keys`, and every generator after it finds one field that both states have.

Answered n, in a dry run of makemigrations, the pair stayed a removal and an addition; a dry run does not go on to ask for the default the added field needs ([The questioner: `MigrationQuestioner`](questioner.md)):

```text recording=migrations
stdout |     - Remove field started from repair
stdout |     + Add field metres to dock
stdout |     + Add field begun to repair
```

## Fields removed and added

`MigrationAutodetector.generate_removed_fields` writes a `RemoveField` for each key in the old set alone, and `MigrationAutodetector.generate_added_fields` an `AddField` for each in the new set alone (`django/db/migrations/autodetector.py:MigrationAutodetector._generate_removed_field`, `django/db/migrations/autodetector.py:MigrationAutodetector._generate_added_field`). Each gives its operation dependencies, here in the recording's words for yard's four operations, the rename accepted, as the generators left them:

```text recording=migrations
yard: RenameField: Rename field started on repair to begun  [needs nothing]
yard: AddField: Add field metres to dock (PositiveSmallIntegerField(default=120))  [needs (yard, dock, metres) removed]
yard: AlterField: Alter field name on dock (CharField(max_length=80))  [needs nothing]
yard: AddIndex: Create index repair_by_dock on field(s) dock, begun of model repair  [needs (fleet, ship) created; needs (yard, dock) created]
```

An `AddField` waits for a `RemoveField` of the same name, as when an altered field is removed and added again. A `RemoveField` waits, among the operations on its model, for an `AlterOrderWithRespectTo` that orders by anything but the field and for every `AlterUniqueTogether`, `RemoveIndex` and `RemoveConstraint`, each of which may take away a use of the field (`django/db/migrations/autodetector.py:MigrationAutodetector.check_dependency`). An `AddIndex` waits for the creation of each model that a relation of its own model points at, whatever fields it names, hence for fleet's Ship; that, and what a relation and a generated field add, are in [From operations to migrations: dependencies, order and names](dependencies.md).

The harder half of an addition is the rows the table already has, which need a value in a column that is not null. `_generate_added_field` asks for none where the field is null, has a default or a `db_default`, is many-to-many, or is blank and of a class that allows empty strings (`django/db/models/fields/__init__.py:Field.empty_strings_allowed`); nor for a `DateField`, `DateTimeField` or `TimeField` with `auto_now`, an `AutoField`, `SmallAutoField` or `BigAutoField`, or a field of a model that is not managed. For any other it clones the field, makes the questioner's answer the clone's default, and makes the operation with `preserve_default=False` ([The field operations, and those on indexes and constraints](../migrations/field-operations.md)). The question is `MigrationQuestioner.ask_auto_now_add_addition` for a date or time field with `auto_now_add` and `MigrationQuestioner.ask_not_null_addition` for any other; a third, `MigrationQuestioner.ask_unique_callable_default_addition`, put for a unique field of a managed model whose default is callable, has its answer dropped ([The questioner: `MigrationQuestioner`](questioner.md)).

## Fields altered: `generate_altered_fields`

For each key in both sets, `MigrationAutodetector.generate_altered_fields` fetches the two fields, the old one under the names the from-state has for the model and the field, and compares what they deconstruct to (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_fields`).

A field that was itself renamed in this run makes no operation here, and names in a relation that only follow a rename are first put back to the old ones. Whatever else differs makes an operation, whether or not a column has to change: a new `verbose_name` is an `AlterField` too, and it is the schema editor that then finds nothing to send ([Altering a column, and SQLite's table remake](../schema/alter-field.md)). The operation is an `AlterField` to the new field where neither field is many-to-many, or both are and point at the same model. Otherwise the field is removed and added, by `MigrationAutodetector._generate_removed_field` and `MigrationAutodetector._generate_added_field`: a comment in the source says there can be no altering between a many-to-many field and a concrete one.

A field that was null and is no longer, has no default and no `db_default`, is not many-to-many and is on a managed model leaves the rows that hold null without a value, and `MigrationQuestioner.ask_not_null_alteration` is asked for one: unless the answer is `NOT_PROVIDED`, which leaves the rows to the developer, it becomes the default of a clone, with `preserve_default=False` (`django/db/models/fields/__init__.py:NOT_PROVIDED`).

## Indexes: `create_altered_indexes`

`MigrationAutodetector.create_altered_indexes` works out three lists for each kept model, from the `"indexes"` of its two model states, and keeps them in `MigrationAutodetector.altered_indexes` (`django/db/migrations/autodetector.py:MigrationAutodetector.create_altered_indexes`). An index of the to-state that equals none of the from-state's is added, and one of the from-state's that equals none of the to-state's is removed; two indexes are equal when they are of one class and deconstruct alike, name included (`django/db/models/indexes.py:Index.__eq__`). Out of those two lists come the renames: an added index and a removed one that deconstruct alike but for the name.

`MigrationAutodetector.generate_removed_indexes` then writes a `RemoveIndex` by name, `MigrationAutodetector.generate_renamed_indexes` a `RenameIndex` by the old name, and `MigrationAutodetector.generate_added_indexes` an `AddIndex` holding the index. An index does not follow a renamed field: the two deconstruct differently, and the old one is removed before the `RenameField` and the new one added after it.

An added index may instead be matched to an entry of `"index_together"`, an option that a from-state made from old migrations may still have and no model can declare now ([Constraints and indexes](../models/constraints.md)). For each entry the to-state lacks, if exactly one added index is over those fields in that order and has no argument but its name and its fields, the index is taken off the added list and written as a `RenameIndex` by the entry's fields; if none or several are, no operation is written for the entry.

## Constraints: `create_altered_constraints`

`MigrationAutodetector.create_altered_constraints` works out three lists for each kept model, from the `"constraints"` of its two model states: constraints added, removed and altered (`django/db/migrations/autodetector.py:MigrationAutodetector.create_altered_constraints`). No rename is looked for. Two constraints of the same name, one from each state, whose deconstructions differ are an alteration unless `MigrationAutodetector._constraint_should_be_dropped_and_recreated` finds that the difference reaches the database. That method deconstructs both, takes out of each the arguments its class lists in `BaseConstraint.non_db_attrs`, which are `violation_error_code` and `violation_error_message`, and answers whether what is left differs (`django/db/migrations/autodetector.py:MigrationAutodetector._constraint_should_be_dropped_and_recreated`).

So for a constraint whose message or code changed and nothing else, `MigrationAutodetector.generate_altered_constraints` writes an `AlterConstraint`, which changes the state and no table. One that differs otherwise, or has another name, is on the other two lists: `MigrationAutodetector.generate_removed_constraints` writes a `RemoveConstraint` by name and `MigrationAutodetector.generate_added_constraints` an `AddConstraint`.

> **Trap.** For a field renamed in this run that keeps a `db_column` it already had, `_constraint_should_be_dropped_and_recreated` first puts the old name back in the new constraint's `"fields"`, so that a constraint which only follows the rename is an alteration too. Given such a rename, on any model, a constraint the method is handed that deconstructs without `"fields"` raises `KeyError`.

## `unique_together` and `order_with_respect_to`

`unique_together` has no object to add or drop: its one operation, `AlterUniqueTogether`, carries the option's whole new value. `MigrationAutodetector._get_altered_foo_together_operations` yields, for each kept model whose value differs, the old value and the new as sets of tuples (`django/db/migrations/autodetector.py:MigrationAutodetector._get_altered_foo_together_operations`). Two generators read it. Before fields are removed, `MigrationAutodetector.generate_removed_altered_unique_together` writes an `AlterUniqueTogether` to the entries both values have, where the old value had any (`django/db/migrations/autodetector.py:MigrationAutodetector._generate_removed_altered_foo_together`). After fields are added and altered, `MigrationAutodetector.generate_altered_unique_together` writes one to the whole new value, where that has an entry the first did not keep (`django/db/migrations/autodetector.py:MigrationAutodetector._generate_altered_foo_together`). The first step is there so that an entry which is to go has gone before fields are removed and altered (`tests/migrations/test_autodetector.py:AutodetectorTests.test_alter_field_and_unique_together`).

`MigrationAutodetector.generate_altered_order_with_respect_to` compares the option `order_with_respect_to` in the two model states, and where it differs writes an `AlterOrderWithRespectTo` to the new value (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_order_with_respect_to`). One that sets the option waits for the creation of the field it names, so that a field added in the same run comes first. One that unsets it is given no dependency; a `RemoveField` of the field it named waits for it instead.
