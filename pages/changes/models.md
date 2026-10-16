---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in models and fields

The changes from Django 5.0 to this commit in how a model and its fields work: `db_default=` and `GeneratedField`, the `on_delete` actions left to the database, `CompositePrimaryKey`, `BigAutoField` as the automatic key, choices, `Model.NotUpdated`, the constraints, and smaller changes to saving and to the field classes.

Over these releases a model came to leave more to its database, a default, a computed column, a delete, and a save learnt to read back what it made. And 6.0 removed what 5.0 and 5.1 had deprecated. Old habits fail, or are answered otherwise:

```text
# model_habits.py at this commit: petrel is a saved Ship, leith and bergen are Ports, a Berth's key is port and number
petrel.save(False)
    TypeError: Model.save() takes 1 positional argument but 2 were given
models.CheckConstraint(check=Q(tonnage__gt=0), name="positive")
    TypeError: CheckConstraint.__init__() got an unexpected keyword argument 'check'
Ship(pk=999, name="Ghost", tonnage=1, home=bergen).save(force_update=True)
    Ship.NotUpdated: Forced update did not affect any rows.
Berth(port=leith, metres=60) == Berth(port=leith, metres=60)
    False
```

## Values the database supplies: `db_default` and `GeneratedField`

A field may have a default that the database applies, `db_default=` (5.0), beside the `default=` that Django applies to a new instance (`django/db/models/fields/__init__.py:Field._get_default`). A new instance given no value holds a `DatabaseDefault` in the value's place, unless the field also has `default=`, and the insert leaves the column out where it can, or writes `"DEFAULT"` or the default's expression (`django/db/models/sql/compiler.py:SQLInsertCompiler.as_sql`, `django/db/models/expressions.py:DatabaseDefault`).

`GeneratedField` (5.0) is a column the database computes from others in its row, and no save writes it (`django/db/models/fields/generated.py:GeneratedField`). Since 6.0 a save reads back such a field, and one assigned an expression such as `F("tonnage") + 20`, which the release notes say it did not do before. `Model._save_table` asks for both in the statement's `"RETURNING"` clause on SQLite, PostgreSQL and Oracle, and on MariaDB for an insert. On MySQL, and on MariaDB for an update, `Model._assign_returned_values` removes the attribute, so that the next read fetches it (`django/db/models/base.py:Model._assign_returned_values`).

Since 6.1 Django makes virtual generated columns on PostgreSQL 18 and stored ones on Oracle 23.7, each having had only the other kind: `GeneratedField.db_persist` chooses, and a check refuses the kind a database lacks (`django/db/models/fields/generated.py:GeneratedField._check_persistence`). Since 5.2 a constraint's validation handles a generated field, taking it as its expression over the instance's values (`django/db/models/base.py:Model._get_field_expression_map`). [The field classes](../models/field-types.md) tells the field, and [Validating an instance](../models/validation.md) the validation.

## A delete left to the database: `DB_CASCADE`, `DB_SET_NULL` and `DB_SET_DEFAULT`

Before 6.1 every `on_delete` was a Python function, which the `Collector` calls for each relation it follows, so that a cascade or a null set was Django's own work (`django/db/models/deletion.py:CASCADE`). Since 6.1 `DB_CASCADE`, `DB_SET_NULL` and `DB_SET_DEFAULT` leave the work to the foreign key's own `ON DELETE` clause. Each is a `DatabaseOnDelete`, which stands with `DO_NOTHING` in `SKIP_COLLECTION`, so the collector that a delete makes does not follow the relation, fetches none of the rows the database removes, and sends them no signal (`django/db/models/deletion.py:DatabaseOnDelete`). The release notes give the fetch saved as the reason (docs/releases/6.1.txt). The checks refuse `DB_SET_NULL` on a field that cannot be null, `DB_SET_DEFAULT` on one without `db_default=`, and a chain of references that mixes the database's actions with Python's (`django/db/models/fields/related.py:ForeignKey._check_on_delete`). [Deleting: the `Collector`](../models/deleting.md) tells it.

## A key of several columns: `CompositePrimaryKey`

`CompositePrimaryKey` (5.2) is a field with no column, assigned to `"pk"`, that names the fields making up the key; its value is a tuple of theirs (`django/db/models/fields/composite.py:CompositePrimaryKey`). In 6.0 `QuerySet.raw` came to accept such a model ([What changed in querysets](querysets.md)), and a subquery returning such a key to serve lookups other than `"in"` ([What changed in expressions, lookups and the compiler](sql.md)). Also in 6.0, `Model._check_local_fields` began to refuse, as `"models.E049"`, a `ForeignObject` with several `from_fields=` named in `"indexes"`, `"constraints"` or `"unique_together"` (`django/db/models/base.py:Model._check_local_fields`).

`Model._is_pk_set` says whether a key is set: not when it is `None`, not when a part of a tuple is, and since 6.1 not when it is the `DatabaseDefault` of a key the database will supply (`django/db/models/base.py:Model._is_pk_set`). `Model.__eq__` asks it, so an unsaved instance with such a key is equal only to itself, as the two Berths of the run are; the release notes say those with a composite or a `db_default=` key compared equal to others before 6.2 (docs/releases/6.2.txt). [An instance and its state](../models/instances.md) tells it.

## The automatic key: `BigAutoField`

`DEFAULT_AUTO_FIELD` has been `"django.db.models.BigAutoField"` by default since 6.0, where it was `"django.db.models.AutoField"` (`django/conf/global_settings.py`). `Options._get_default_pk_class` picks the class of the `"id"` a model with no primary key is given: that one, unless the application's `AppConfig.default_auto_field` names another (`django/db/models/options.py:Options._get_default_pk_class`). A project that set neither now gets 64-bit keys, and the autodetector, comparing a key made under the old default with the model, makes an `AlterField` for it (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_fields`). The check models.W042, which had warned of such keys since 3.2, is gone, and the project and application templates no longer write either ([What changed in settings, startup and the commands](startup-and-commands.md)).

## Choices: a mapping, a callable or an enumeration

Since 5.0 `choices=` may be a mapping, a callable or an enumeration class itself, as in the harbour's `choices=Rank`, where it had to be a list of pairs or the enumeration's `ChoicesType.choices`. The setter of `Field.choices` passes the value to `normalize_choices`, which makes the list of pairs and wraps a callable in a `CallableChoiceIterator`, called each time the choices are read (`django/utils/choices.py:normalize_choices`, `django/db/models/fields/__init__.py:Field.choices`). The metaclass once named ChoicesMeta was renamed `ChoicesType` in 5.0, and the old name went in 6.0. In 6.1 the blank choice that `Field.get_choices` puts first took `BLANK_CHOICE_LABEL` as its label in place of dashes, which `USE_BLANK_CHOICE_DASH` brings back until Django 2028 ([What changed in forms and validators](forms.md)). [Choices: `normalize_choices` and the choice iterators](../utils/choices.md) tells it.

## `Model.NotUpdated`

Since 6.0 a save told to update, by `force_update=True` or `update_fields=`, that matches no row raises the model's `Model.NotUpdated` in place of a plain `DatabaseError` (`django/db/models/base.py:Model._save_table`; [Saving an instance](../models/saving.md)). `ModelBase.__new__` makes it a subclass of the same class on each base that is a model and not abstract, or else of `ObjectNotUpdated` and `DatabaseError`. Its comment gives the second base as backward compatibility, an `except` clause not consulting `__subclasshook__`, so code that catches `DatabaseError` still catches it (`django/db/models/base.py:ModelBase.__new__`; [`ModelBase`: a class statement becomes a model](../models/metaclass.md)).

## Constraints

`CheckConstraint` has taken its condition as `condition=` since 5.1, which deprecated `check=`, removed in 6.0 (`django/db/models/constraints.py:CheckConstraint.__init__`). The name went to a method. Since 6.0 `BaseConstraint.check` returns the system check's messages for a model and a connection, and `Model._check_constraints` calls it for each database that may hold the model (`django/db/models/base.py:Model._check_constraints`).

`BaseConstraint.violation_error_code` (5.0) sets the code of the `ValidationError` that a failed validation raises. Giving the name or the message by position, deprecated in 5.0, is refused since 6.0 (`django/db/models/constraints.py:BaseConstraint.__init__`). `UniqueConstraint.nulls_distinct` (5.0) asks the database to treat nulls as distinct or not, where its features allow, as PostgreSQL's do; with `False` the validation counts a null as a value that can be taken.

Until 5.2 a `UniqueConstraint` over fields and without a condition answered with a unique field's message whatever it had been given. Now a message given is used, with the code given (`django/db/models/constraints.py:UniqueConstraint.validate`). The release notes say the code is always used; at this commit a code without a message is not, the test being of the message alone. Given only `violation_error_code="taken"`, a constraint over `"name"` raised for a second Petrel an error coded `"unique"`.

The `Meta` option index_together was removed in 5.1. `Options.contribute_to_class` refuses it with a `TypeError`, and an `Index` in `"indexes"` takes its place (`django/db/models/options.py:Options.contribute_to_class`). `AlterIndexTogether` stays, so that old migrations still apply (`django/db/migrations/operations/models.py:AlterIndexTogether`). [Constraints and indexes](../models/constraints.md) tells the rest.

## Smaller changes

The deprecations among these are in [What still warns: the deprecations and the releases that end them](deprecations.md).

| name | what changed | release | now |
|---|---|---|---|
| `Model.save`, `Model.asave` | positional arguments deprecated, then refused | 5.1, 6.0 | `django/db/models/base.py:Model.save` |
| `force_insert=` | may be a tuple of parent classes whose tables are forced too | 5.0 | `django/db/models/base.py:Model._validate_force_insert` |
| `Model.refresh_from_db` | takes `from_queryset=`, the queryset to reload from | 5.1 | `django/db/models/base.py:Model.refresh_from_db` |
| `Field.pre_save` | may be called more than once in one save | 6.0 | `django/db/models/fields/__init__.py:Field.pre_save`, called by `django/db/models/base.py:Model._save_table` |
| `DecimalField` | both sizes may be left out where the backend allows: SQLite, PostgreSQL, Oracle | 6.1 | `django/db/models/fields/__init__.py:DecimalField._check_decimal_places` |
| `CharField` | may be made without `max_length=` on SQLite, as on PostgreSQL | 5.2 | `django/db/models/fields/__init__.py:CharField._check_max_length_attribute` |
| `GenericIPAddressField` | a bad IPv6 address raises `ValidationError` in a save or a filter too, and white space is stripped | 6.2 | `django/db/models/fields/__init__.py:GenericIPAddressField.to_python` |
| `BinaryField` | a string that is not strict Base64 raises `ValidationError` | 6.1 | `django/db/models/fields/__init__.py:BinaryField.to_python` |
| `FileField` | saving a file with no name raises `FieldError` | 5.1 | `django/db/models/fields/files.py:FileField.pre_save` |
| `ImageField` | measured on `post_init` only for a field with a width or height field (5.0), and after a save from the content, not the stored file (5.1) | 5.0, 5.1 | [File fields](../models/files.md) |
| `m2m_changed` | receivers get `"raw"`, true when serialized data sets the relation | 6.1 | [Many-to-many relations](../models/many-to-many.md) |
| a field's get_placeholder | deprecated for `get_placeholder_sql`, which returns the SQL and its parameters | 6.1 | `django/db/models/fields/__init__.py:Field.__init_subclass__` |
| get_cache_name of `FieldCacheMixin` | replaced by `FieldCacheMixin.cache_name`: deprecated, then removed | 5.1, 6.0 | `django/db/models/fields/mixins.py:FieldCacheMixin` |
| `UUIDField` on MariaDB | a `"uuid"` column, not `"char(32)"` | 5.0 | [What changed in the database backends and migrations](backends-and-migrations.md) |
