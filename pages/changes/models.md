---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in models and fields

A model leaves more to its database: `db_default`, `GeneratedField`, `CompositePrimaryKey` and `DB_CASCADE`. Also changed: what a save reads back, unsaved instances' equality, `Model.NotUpdated`, choices, constraints and the field classes.

Since 6.0 a save reads back what an expression became, and after an update a generated column, where the backend can.

## Values the database supplies: `db_default` and `GeneratedField`

`Field.db_default` (5.0) is a default the database applies. A new instance given no value holds a `DatabaseDefault` in its place, unless the field has Django's default too (`django/db/models/fields/__init__.py:Field._get_default`; [The field classes](../models/field-types.md)).

`GeneratedField` (5.0) is a column the database computes from its row, and no save writes it (`django/db/models/fields/generated.py:GeneratedField`). Since 5.2 a constraint over one can be validated (`django/db/models/base.py:Model._get_field_expression_map`). Since 6.1 PostgreSQL from 18 may have a virtual one and Oracle from 23.7 a stored one; each had had only the other kind (`django/db/backends/postgresql/features.py:DatabaseFeatures.supports_virtual_generated_columns`, `django/db/backends/oracle/features.py:DatabaseFeatures.supports_stored_generated_columns`).

## What a save reads back

Since 6.0 `Model._save_table` reads back a field assigned an expression, and after an update the generated fields that depend on a field it writes (`django/db/models/base.py:Model._save_table`). Before, a save read back only after an insert, and only `Options.db_returning_fields`: the automatic key, and a database default or a generated column where the backend can return them.

On SQLite, 5.2.17 leaves the expression on the instance; the later releases hold the value the statement's `"RETURNING"` clause gave back:

```text recording=changes
tally.count = F("count") + 1; tally.save(); tally.count: a field assigned an expression, after the save
    5.2.17       <CombinedExpression: F(count) + Value(1)>
    6.0.8        1
    6.1.1        1
    this commit  1
```

On MySQL, and on MariaDB after an update, the backend cannot return the columns, so the field is removed from the instance and deferred to the next read (`django/db/models/base.py:Model._assign_returned_values`; [Saving an instance](../models/saving.md#what-comes-back)).

Since 6.0 the insert of a save that is not raw calls `django.db.models.Field.pre_save` twice for each field it writes, where 5.2.17 called it once (`django/db/models/sql/compiler.py:SQLInsertCompiler.pre_save_val`; [Saving an instance](../models/saving.md#pre_save-and-why-an-insert-calls-it-twice)).

## A delete left to the database: `DB_CASCADE`, `DB_SET_NULL` and `DB_SET_DEFAULT`

Since 6.1 the three `DatabaseOnDelete` values of `on_delete` leave the related rows to the `ON DELETE` clause the schema editor writes (`django/db/models/deletion.py:DatabaseOnDelete`). They are in `SKIP_COLLECTION` with `DO_NOTHING`, so a delete's `Collector` passes the relation over (`django/db/models/deletion.py:Collector.collect`).

Under `CASCADE` the `Collector` deletes and counts the related rows itself, before the row they point to where their key cannot be null. It fetches them first where a receiver of `pre_delete` or `post_delete` must be called for them, or their own relations followed (`django/db/models/deletion.py:Collector.can_fast_delete`, `django/db/models/deletion.py:Collector.sort`).

The figure deletes a harbour with one mooring under `CASCADE` and `DB_CASCADE`, a receiver of `post_delete` listening for moorings: look at who deletes the mooring, and what the receiver and the count hear.

```text figure=who-deletes
CASCADE: Django deletes the mooring
  Django        SELECT the moorings, as a receiver must be called
  Django        DELETE the mooring
  Django        DELETE the harbour
  post_delete   called for the mooring
  counted       the harbour and the mooring

DB_CASCADE, since 6.1: the database deletes the mooring
  Django        DELETE the harbour, the one statement sent
  database      deletes the mooring, by its key's ON DELETE clause
  post_delete   not called for the mooring
  counted       the harbour alone
```

*Read each half down: the steps of one delete in order, beside who carries each out, then what the receiver and the count learn of the mooring.*

The 6.1 notes give the saved fetch as the reason, and the unsent signals as its consequence (`docs/releases/6.1.txt`; [Deleting: the `Collector`](../models/deleting.md)). The checks refuse a chain of keys that mixes the database's actions with the collector's (`django/db/models/fields/related.py:ForeignKey._check_on_delete`).

> **Trap.** `Collector.delete` sends `post_delete` only for the rows it collected, and counts only those (`django/db/models/deletion.py:Collector.delete`). Under `DB_CASCADE` the harbour's delete sends its own `"DELETE"` alone, calls no receiver and returns `(1, {'journal.Harbour': 1})`, with the mooring gone too.

## Keys: several columns, a database default, and the automatic key

`CompositePrimaryKey` (5.2) is a field without a column, assigned to `pk`, whose value is a tuple (`django/db/models/fields/composite.py:CompositePrimaryKey`). 6.0 let `QuerySet.raw` load such a model ([What changed in querysets](querysets.md)) and a subquery returning one serve more lookups ([What changed in expressions, lookups and the compiler](sql.md)). Since 6.0 the check `"models.E049"` refuses a `ForeignObject` of several `from_fields=` named in an index, a constraint or `Options.unique_together`; 5.2.17 let one pass (`django/db/models/base.py:Model._check_local_fields`).

`Model._is_pk_set` counts a key unset when it is `None` or a tuple with a part unset, and since 6.1 when it holds a `DatabaseDefault` (`django/db/models/base.py:Model._is_pk_set`). Since 6.2 `Model.__eq__` asks it, and an unsaved instance whose key is unset is equal only to itself; before, it compared any key but `None` (`django/db/models/base.py:Model.__eq__`; [An instance and its state](../models/instances.md)).

So two unsaved instances whose integer key has `db_default=1` are still equal under 6.1.1, and not at this commit; nor are two with a composite key, a part of it unset. Two with the same whole key still are, though the 6.2 notes say unsaved instances with a composite key "no longer compare equal to other instances" (`docs/releases/6.2.txt`).

The automatic key's default became `BigAutoField` in 6.0, and the warning models.W042 went with it (`django/conf/global_settings.py`; [What changed](../changes.md#an-old-habit-release-by-release)).

## Choices: a mapping, a callable or an enumeration

Since 5.0 a field's choices may be a mapping, a callable or an enumeration class, where they had to be pairs or `ChoicesType.choices`. The setter of `Field.choices` passes them to `normalize_choices`, which makes the pairs (`django/db/models/fields/__init__.py:Field.choices`, `django/utils/choices.py:normalize_choices`; [Choices: `normalize_choices` and the choice iterators](../utils/choices.md)). ChoicesMeta, renamed `ChoicesType` in 5.0, warned under 5.2.17 and is an `ImportError` since 6.0.

Since 6.1 the blank choice that `Field.get_choices` puts first is `"- Select an option -"`, where it was dashes. `USE_BLANK_CHOICE_DASH` brings the dashes back until Django 2028 (`django/db/models/utils.py:get_blank_choice_label`; [What changed in forms and validators](forms.md)).

## Constraints

Since 6.0 a `CheckConstraint` given `check=` raises a `TypeError`: 5.1 had deprecated it for `condition=` (`django/db/models/constraints.py:CheckConstraint.__init__`). A name or message given to `BaseConstraint` by position, deprecated in 5.0, raises one too. Since 6.0 `BaseConstraint.check` is the method that gives `Model._check_constraints` the system check's messages; under 5.2.17 `check` was the condition, with a warning (`django/db/models/base.py:Model._check_constraints`).

`BaseConstraint.violation_error_code` (5.0) sets the code of a failed validation's error, and `UniqueConstraint.nulls_distinct` (5.0) how PostgreSQL treats nulls. Until 5.2 a `UniqueConstraint` over fields and without a condition raised the error of a unique field or `Options.unique_together`, whatever it was given. Since 5.2 it uses a message given, with the code given (`django/db/models/constraints.py:UniqueConstraint.validate`).

> **Trap.** The 5.2 notes say the code and the message "are now always used when provided" (`docs/releases/5.2.txt`). Over fields and without a condition, a code given without a message is not: given only `violation_error_code="taken"`, a constraint over one field raises the code `"unique"` under all four releases.

## The smaller changes

The rest:

| what | change | where |
|---|---|---|
| `Model.NotUpdated` | New in 6.0: what a forced update raises when no row matches, a subclass of `DatabaseError` | `django/db/models/base.py:ModelBase.__new__` |
| `Model.save`, `Model.asave` | Gone in 6.0, deprecated in 5.1: arguments by position raise `TypeError` | `django/db/models/base.py:Model.save` |
| The option index_together | Gone in 5.1: refused as a class is made; `AlterIndexTogether` stays for old migrations | `django/db/migrations/operations/models.py:AlterIndexTogether` |
| `DecimalField` | Since 6.1, both `max_digits` and `decimal_places` may be left out on SQLite, PostgreSQL and Oracle | `django/db/models/fields/__init__.py:DecimalField._check_decimal_places` |
| `CharField` | Since 5.2, `max_length=` may be left out on SQLite | `django/db/models/fields/__init__.py:CharField._check_max_length_attribute` |
| `GenericIPAddressField` | Since 6.2, a save or a filter refuses a bad IPv6 address with `ValidationError`, and strips spaces round it | `django/db/models/fields/__init__.py:GenericIPAddressField.to_python` |
| `BinaryField` | Since 6.1, Base64 that is not strict raises `ValidationError` | `django/db/models/fields/__init__.py:BinaryField.to_python` |
| `FileField` | Since 5.1, saving a file with no name raises `FieldError` | `django/db/models/fields/files.py:FileField.pre_save` |
| `ImageField` | Since 5.0, measured on `post_init` only with a width or height field; since 5.1, not again after a save | `django/db/models/fields/files.py:ImageField.contribute_to_class` |
| `m2m_changed` | New in 6.1: the argument `raw=`, true when serialized data sets the relation | [Many-to-many relations](../models/many-to-many.md) |
| get_placeholder of a field | Deprecated in 6.1 for `get_placeholder_sql`; a field class that defines it without `get_placeholder_sql` warns when made | `django/db/models/fields/__init__.py:Field.__init_subclass__` |
| get_cache_name of `FieldCacheMixin` | Gone in 6.0, deprecated in 5.1 for `FieldCacheMixin.cache_name`, which no longer calls it | `django/db/models/fields/mixins.py:FieldCacheMixin` |
