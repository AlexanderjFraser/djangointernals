---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in models and fields

The changes from Django 5.0 to this commit in how a model and its fields work: `db_default` and `GeneratedField`, what a save reads back, `on_delete` left to the database, `CompositePrimaryKey` and unsaved instances' equality, `Model.NotUpdated`, choices, constraints, and the field classes.

Since 6.0 a save asks, in the same statement where the backend can, what an expression became, and after an update a generated column too. Since 6.1 an instance whose key the database will supply counts as having no key yet. Over these releases a model came to leave more to its database: a default and a computed column (5.0), a key of several columns (5.2), and a delete (6.1). 6.0 removed what 5.0 and 5.1 had deprecated, so code that 5.2 ran with a warning raises.

## Values the database supplies: `db_default` and `GeneratedField`

`Field.db_default` (5.0) is a default the database applies. A new instance given no value holds a `DatabaseDefault` in its place, unless the field has Django's default too. The insert then leaves the column out where no other row of a bulk insert gives it a value and it is not the only column left, and otherwise writes `"DEFAULT"`, or the default's expression where the backend lacks that keyword (`django/db/models/fields/__init__.py:Field._get_default`, `django/db/models/sql/compiler.py:SQLInsertCompiler.as_sql`).

`GeneratedField` (5.0) is a column the database computes from its row, and no save writes it (`django/db/models/fields/generated.py:GeneratedField`). Since 5.2 a constraint over one can be validated (`django/db/models/base.py:Model._get_field_expression_map`). Since 6.1 PostgreSQL from 18 may have a virtual one and Oracle from 23.7 a stored one; each had had only the other kind (`django/db/backends/postgresql/features.py:DatabaseFeatures.supports_virtual_generated_columns`, `django/db/backends/oracle/features.py:DatabaseFeatures.supports_stored_generated_columns`). [The field classes](../models/field-types.md) tells both.

## What a save reads back

Until 6.0 a save read back only after an insert, and only the fields `Options.db_returning_fields` names: the automatic key and, where the backend returns columns from an insert, a database default or a generated column. Since 6.0 `Model._save_table` also asks for a field assigned an expression. After an update it also asks for the generated fields that depend on a field it writes (`django/db/models/base.py:Model._save_table`). The habit increments a counter by an expression, saves, and reads it, on SQLite:

```text recording=changes
tally.count = F("count") + 1; tally.save(); tally.count: a field assigned an expression, after the save
    5.2.17       <CombinedExpression: F(count) + Value(1)>
    6.0.8        1
    6.1.1        1
    this commit  1
```

From 6.0 the instance holds what the database wrote, from the statement's `"RETURNING"` clause. Under 5.2.17 on SQLite a generated column was right after an insert but stale after an update, so on SQLite the 6.0 notes' "now refreshed" is new for it only on an update (`docs/releases/6.0.txt`). Where the backend cannot return columns, as on MySQL, and on MariaDB after an update, the field is instead removed from the instance and so deferred to the next read (`django/db/models/base.py:Model._assign_returned_values`; [Saving an instance](../models/saving.md#what-comes-back)).

Since 6.0 the insert of a save that is not raw calls `django.db.models.Field.pre_save` twice for each field it writes: in `_save_table`, to see if the value is an expression, and in the compiler (`django/db/models/base.py:Model._save_table`, `django/db/models/sql/compiler.py:SQLInsertCompiler.pre_save_val`). A field that counted its calls was called once under 5.2.17 and twice under 6.0.8 ([Saving an instance](../models/saving.md#pre_save-and-why-an-insert-calls-it-twice)).

## A delete left to the database: `DB_CASCADE`, `DB_SET_NULL` and `DB_SET_DEFAULT`

Before 6.1 the `Collector` carried out every `on_delete` but `DO_NOTHING`. Under `CASCADE` the collector deletes the related rows itself, and fetches them first where a receiver of `pre_delete` or `post_delete` must be called, or their own relations followed (`django/db/models/deletion.py:Collector.can_fast_delete`). 6.1 added three `DatabaseOnDelete` values that leave the work to the `ON DELETE` clause the schema editor writes (`django/db/models/deletion.py:DatabaseOnDelete`). They are in `SKIP_COLLECTION` with `DO_NOTHING`, so a delete's collector passes the relation over (`django/db/models/deletion.py:Collector.collect`). The habit deletes a harbour with one mooring while a receiver of `post_delete` listens for moorings, and gives the statements sent:

```text recording=changes
harbour.delete(), a Mooring's key to it on_delete=DB_CASCADE, post_delete heard on Mooring: the statements sent
    5.2.17       ImportError: cannot import name 'DB_CASCADE' from 'django.db.models'
    6.0.8        ImportError: cannot import name 'DB_CASCADE' from 'django.db.models'
    6.1.1        DELETE FROM "journal_harbour" WHERE "journal_harbour"."id" IN (1)
    this commit  DELETE FROM "journal_harbour" WHERE "journal_harbour"."id" IN (1)
```

From 6.1 Django leaves the mooring to the database ([Deleting: the `Collector`](../models/deleting.md) shows the rows gone). The 6.1 notes give the saved fetch as the reason, and the unsent signals as its consequence (`docs/releases/6.1.txt`). The checks refuse a key with one of the database's actions to a model whose own key has one of the collector's, or the reverse (`django/db/models/fields/related.py:ForeignKey._check_on_delete`).

> **Trap.** `Collector.delete` sends `post_delete` only for the rows it collected, and counts only those (`django/db/models/deletion.py:Collector.delete`). The harbour's delete calls no receiver and returns `(1, {'journal.Harbour': 1})`, with the mooring gone too.

## Keys: several columns, a database default, and the automatic key

`CompositePrimaryKey` (5.2) is a field without a column, assigned to `pk`, whose value is a tuple (`django/db/models/fields/composite.py:CompositePrimaryKey`). 6.0 let `QuerySet.raw` load such a model ([What changed in querysets](querysets.md)), and let a subquery returning such a key serve more lookups ([What changed in expressions, lookups and the compiler](sql.md)). It also refused, as `"models.E049"`, a `ForeignObject` given several fields as `from_fields=` and named in an index, a constraint or `Options.unique_together`, which 5.2.17 let pass (`django/db/models/base.py:Model._check_local_fields`).

`Model._is_pk_set` counts a key unset when it is `None` or a tuple with a part unset, and since 6.1 when it holds a `DatabaseDefault` (`django/db/models/base.py:Model._is_pk_set`). `Model.__eq__` has asked it only since 6.2; before, it compared any key but `None`. The habit compares two unsaved instances whose integer key has `db_default=1`:

```text recording=changes
Ticket() == Ticket(): unsaved, the key one the database supplies (db_default=1)
    5.2.17       True
    6.0.8        True
    6.1.1        True
    this commit  False
```

`_is_pk_set` changed in 6.1, and equality followed in 6.2. An unsaved instance whose key is unset is now equal only to itself (`django/db/models/base.py:Model.__eq__`; [An instance and its state](../models/instances.md)). Two unsaved instances with a composite key, a part of it unset, changed in the same way. The 6.2 notes say unsaved instances with a composite key "no longer compare equal to other instances" (`docs/releases/6.2.txt`); two with the same whole key still do.

The automatic key's default became `BigAutoField` in 6.0 (`django/conf/global_settings.py`; [What changed](../changes.md#an-old-habit-release-by-release)). The warning models.W042, which 5.2.17 gave a model with an automatic key in a project and an application that named no class, went with it.

## `Model.NotUpdated`

Before 6.0 a save told to update, by `force_update=True` or update_fields, raised a plain `DatabaseError` when no row matched. Since 6.0 it raises the model's own `Model.NotUpdated` (`django/db/models/base.py:Model._save_table`). `ModelBase.__new__` makes it a subclass of a concrete parent's, or else of `ObjectNotUpdated` and `DatabaseError`, which it keeps for backward compatibility (`django/db/models/base.py:ModelBase.__new__`; [`ModelBase`: a class statement becomes a model](../models/metaclass.md)). Under 5.2.17 `except DatabaseError` around a forced update of a missing row caught a `DatabaseError`, and from 6.0.8 an Entry.NotUpdated with the same message.

## Choices: a mapping, a callable or an enumeration

Since 5.0 a field's choices may be a mapping, a callable or an enumeration class, where they had to be pairs or `ChoicesType.choices`. The setter of `Field.choices` passes them to `normalize_choices`, which makes the pairs (`django/db/models/fields/__init__.py:Field.choices`, `django/utils/choices.py:normalize_choices`; [Choices: `normalize_choices` and the choice iterators](../utils/choices.md)). ChoicesMeta, renamed `ChoicesType` in 5.0, warned under 5.2.17 and is an `ImportError` from 6.0. In 6.1 the blank choice that `Field.get_choices` puts first changed from dashes to `"- Select an option -"`. `USE_BLANK_CHOICE_DASH` brings the dashes back until Django 2028 (`django/db/models/utils.py:get_blank_choice_label`; [What changed in forms and validators](forms.md)).

## Constraints

Since 5.1 a `CheckConstraint` takes its condition by the keyword condition. The keyword check, deprecated in 5.1, raises a `TypeError` from 6.0 (`django/db/models/constraints.py:CheckConstraint.__init__`). The name check went to a method. Since 6.0 `BaseConstraint.check` returns the system check's messages, and `Model._check_constraints` calls it (`django/db/models/base.py:Model._check_constraints`). 5.2 had read check as the condition, with a warning. Giving `BaseConstraint` its name or message by position, deprecated in 5.0, is a `TypeError` from 6.0.

`BaseConstraint.violation_error_code` (5.0) sets the code of a failed validation's error, and `UniqueConstraint.nulls_distinct` (5.0) how PostgreSQL treats nulls. Until 5.2 a `UniqueConstraint` over fields and without a condition raised the error a unique field or `Options.unique_together` raises, whatever it was given. Since 5.2 a message given is used, with the code given (`django/db/models/constraints.py:UniqueConstraint.validate`).

> **Trap.** The 5.2 notes say the code and the message "are now always used when provided" (`docs/releases/5.2.txt`). Over fields and without a condition, a code is used only if a message is given: over one field, given only `violation_error_code="taken"`, the error's code was `"unique"` from 5.2.17 to this commit.

The option index_together, removed in 5.1, is refused as a class is made ([What changed](../changes.md#an-old-habit-release-by-release)). `AlterIndexTogether` stays for old migrations (`django/db/migrations/operations/models.py:AlterIndexTogether`; [Constraints and indexes](../models/constraints.md)).

## Smaller changes

What still warns is in [What still warns: the deprecations and the releases that end them](deprecations.md).

The rest, by name:

| name | what changed | release | now |
|---|---|---|---|
| `Model.save`, `Model.asave` | arguments by position deprecated, then a `TypeError` | 5.1, 6.0 | `django/db/models/base.py:Model.save` |
| `DecimalField` | both sizes may be left out on SQLite, PostgreSQL and Oracle | 6.1 | `django/db/models/fields/__init__.py:DecimalField._check_decimal_places` |
| `CharField` | max_length may be left out on SQLite | 5.2 | `django/db/models/fields/__init__.py:CharField._check_max_length_attribute` |
| `GenericIPAddressField` | a bad IPv6 address raises `ValidationError` on a save or a filter, where it was passed as given; spaces are stripped | 6.2 | `django/db/models/fields/__init__.py:GenericIPAddressField.to_python` |
| `BinaryField` | Base64 that is not strict raises `ValidationError` | 6.1 | `django/db/models/fields/__init__.py:BinaryField.to_python` |
| `FileField` | saving a file with no name raises `FieldError` | 5.1 | `django/db/models/fields/files.py:FileField.pre_save` |
| `ImageField` | measured on `post_init` only with a width or height field (5.0), not again after a save (5.1) | 5.0, 5.1 | `django/db/models/fields/files.py:ImageField.contribute_to_class` |
| `m2m_changed` | receivers are given raw, true when serialized data sets the relation | 6.1 | [Many-to-many relations](../models/many-to-many.md) |
| get_placeholder of a field | deprecated for `get_placeholder_sql`, with a warning as the class is made | 6.1 | `django/db/models/fields/__init__.py:Field.__init_subclass__` |
| get_cache_name of `FieldCacheMixin` | replaced by `FieldCacheMixin.cache_name`, which from 6.0 never calls it | 5.1, 6.0 | `django/db/models/fields/mixins.py:FieldCacheMixin` |
