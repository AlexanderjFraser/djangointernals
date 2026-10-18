---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the database backends and migrations

Connections gained pools and new options, `savepoint` was deprecated for `savepoint_create`, and the hooks a third-party backend supplies were renamed, removed and added. Migrations serialize more values, squash squashed migrations and track unmanaged models fully.

For a project, a connection opens much as it did, though Oracle's needs oracledb and MySQL's asks for another character set. The larger change is for whoever writes a backend: a hook renamed or removed is no longer called, without a word. Migrations went the other way, towards doing what they once refused or passed over.

## Connection pools: PostgreSQL and Oracle

Since 5.1 PostgreSQL's backend, and since 5.2 Oracle's, can take connections from a pool, made by the `pool` property when an alias's `"OPTIONS"` hold `"pool"` (`django/db/backends/postgresql/base.py:DatabaseWrapper.pool`, `django/db/backends/oracle/base.py:DatabaseWrapper.pool`). PostgreSQL's pool needs psycopg 3, and both refuse a `"CONN_MAX_AGE"` other than 0 ([Opening and closing a connection](../backends/lifecycle.md#connection-pools-postgresql-and-oracle)).

## Opening a connection: SQLite's options, MySQL's character set, Oracle's driver

Since 5.1 SQLite's backend takes two keys out of `"OPTIONS"`: `"init_command"`, commands run on every new connection, and `"transaction_mode"`, the mode written after the `"BEGIN"` of an outermost atomic block (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_connection_params`; [SQLite](../backends/sqlite.md#opening-a-connection-get_connection_params-and-get_new_connection)).

Since 5.2 MySQL's backend asks for the character set `"utf8mb4"`, where it asked for `"utf8"`, which the notes call an alias of the deprecated `"utf8mb3"`. A `"charset"` in `"OPTIONS"` still replaces it (`django/db/backends/mysql/base.py:DatabaseWrapper.get_connection_params`; [MySQL and MariaDB](../backends/mysql.md#the-driver-mysqldb-and-opening-a-connection)).

5.0 added oracledb to Oracle's backend and deprecated cx_Oracle, which 6.0 removed (`django/db/backends/oracle/base.py`; [Oracle](../backends/oracle.md#the-driver-and-the-processs-environment)).

## Columns and values: UUIDs on MariaDB, integers on SQLite

Since 5.0 a `django.db.models.UUIDField` on MariaDB is a `"uuid"` column, where it was `"char(32)"` (`django/db/backends/mysql/base.py:DatabaseWrapper.data_types`). The 5.0 notes ask that a field made before then be replaced by a subclass backed by `"char(32)"`. They say MariaDB 10.7 and later; at this commit MySQL's `DatabaseFeatures.has_native_uuid_field` asks only whether the server is MariaDB (`django/db/backends/mysql/features.py:DatabaseFeatures.has_native_uuid_field`; [Column types: from a field to a column](../backends/column-types.md#mysqls-two-properties)).

Since 5.0 integer fields on SQLite are validated as 64-bit integers, "to match the behavior of sqlite3", the notes say (`django/db/backends/sqlite3/operations.py:DatabaseOperations.integer_field_range`; [The field classes](../models/field-types.md#integers)).

## `savepoint`, deprecated for `savepoint_create`

6.1 added `django.db.transaction.savepoint_create` and deprecated `savepoint` for it. The old function now warns and calls the new one (`django/db/transaction.py:savepoint`; [Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#savepoints)).

## The backend API: hooks renamed, removed and added

Three changes to the classes a third-party backend supplies now meet old code in silence.

5.0 deprecated the operations' method field_cast_sql for `BaseDatabaseOperations.lookup_cast`, and 6.0 removed it. `BuiltinLookup.process_lhs` now asks `lookup_cast` alone (`django/db/models/lookups.py:BuiltinLookup.process_lhs`; [Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../sql/lookups.md#builtinlookup-the-operator-from-the-backends-table)). Where a backend's operations override field_cast_sql to cast to text, 5.2.17 applies the override with a warning, and the later releases pass it over in silence:

```text recording=changes
a backend's operations that override field_cast_sql: the WHERE clause of Entry.objects.filter(title="Hull")
    5.2.17       CAST("journal_entry"."title" AS TEXT) = %s, warns RemovedInDjango60Warning
    6.0.8        "journal_entry"."title" = %s
    6.1.1        "journal_entry"."title" = %s
    this commit  "journal_entry"."title" = %s
```

Since 6.1 `DurationField.get_db_prep_value` hands a duration to `BaseDatabaseOperations.adapt_durationfield_value`, whose base gives an integer of microseconds (`django/db/models/fields/__init__.py:DurationField.get_db_prep_value`; [Values in and out: adapters, converters and time zones](../backends/values.md#the-operations-objects-adapters)). The 6.1 notes ask a backend with native durations to override it to return the value as given. Until then `get_db_prep_value` read `BaseDatabaseFeatures.has_native_duration_field`. A backend that only set that flag had its `datetime.timedelta` passed through under 5.2.17 and 6.0.8, and since 6.1 is sent microseconds.

6.0 renamed return_insert_columns and fetch_returned_insert_rows to `BaseDatabaseOperations.returning_columns` and `BaseDatabaseOperations.fetch_returned_rows`, which an `UPDATE … RETURNING` uses too, and removed fetch_returned_insert_columns. A method under an old name is no longer called (`django/db/backends/base/operations.py:BaseDatabaseOperations.returning_columns`; [Inserts: returned keys, conflicts and batch sizes](../backends/inserts.md#what-comes-back-returning_columns-fetch_returned_rows-and-last_insert_id)).

The other changes, some of them as silent:

| what | change | where |
|---|---|---|
| `BaseDatabaseFeatures.supports_expression_defaults` | New in 5.0: true by default; where false, `"fields.E011"` refuses any expression but a `Value` as a `db_default` | `django/db/models/fields/__init__.py:Field._check_db_default` |
| `BaseDatabaseFeatures.supports_default_keyword_in_insert` | New in 5.0, as is `BaseDatabaseFeatures.supports_default_keyword_in_bulk_insert`: true by default; where false, an insert writes a `db_default`'s expression for `"DEFAULT"` | `django/db/models/expressions.py:DatabaseDefault.as_sql` |
| `BaseDatabaseSchemaEditor.sql_delete_column` | Since 6.0, no `"CASCADE"`, which PostgreSQL's editor inherited until then | `django/db/backends/base/schema.py` |
| `BaseDatabaseFeatures.can_return_rows_from_update` | New in 6.0: false by default; where false, an update asked for columns back goes without `"RETURNING"` | `django/db/models/sql/compiler.py:SQLUpdateCompiler.execute_returning_sql` |
| `BaseDatabaseIntrospection.get_relations` | Since 6.1, a third member in each value, the key's delete rule, which inspectdb reads for its `on_delete` | `django/db/backends/base/introspection.py` |
| `BaseDatabaseFeatures.supports_inspectdb` | New in 6.1: true by default; where false, inspectdb raises `CommandError` | `django/core/management/commands/inspectdb.py:Command.handle` |
| `BaseDatabaseOperations.binary_placeholder_sql` | Since 6.1, given the compiler, and returns SQL and parameters | `django/db/backends/base/operations.py` |
| `BaseSpatialOperations.get_geom_placeholder_sql` | Since 6.1, the name of get_geom_placeholder, and returns SQL and parameters | `django/contrib/gis/db/backends/base/operations.py` |
| `BaseDatabaseFeatures.supports_bit_aggregations` | New in 6.1: true by default; where false, a bit aggregate raises `NotSupportedError` | `django/db/models/aggregates.py:BitAggregate.as_sql` |

## What the migration serializer writes

Since 6.0 `ZoneInfoSerializer` writes a `zoneinfo.ZoneInfo`, which 5.2.17 refuses. Since 6.0 too, a keyword argument of a deconstructed call whose name is not an identifier goes into a dictionary after `**` (`django/db/migrations/serializer.py:DeconstructibleSerializer.serialize_deconstructed`). 5.2.17 wrote it as it stood, `"x-scale=2"`, which is not Python. Since 5.0 a function under `functools.cache` or `functools.lru_cache` is written by its name (`django/db/migrations/serializer.py:FUNCTION_TYPES`; [Serializing values: `serializer_factory` and `deconstruct`](../migrations/serializer.md#the-registry-in-its-order)).

Other changes stand in no release note. Since 6.0 `DeconstructibleSerializer` is the name of what was DeconstructableSerializer, with no alias left. Since 6.1 `GenericAliasSerializer` writes a generic alias such as `list[int]` (`django/db/migrations/serializer.py:GenericAliasSerializer`).

## makemigrations: operation categories

Since 5.1 an operation may have a category, `Operation.category`, a member of `OperationCategory`. makemigrations prints a sign before each operation's description, such as `"+"` for an addition (`django/db/migrations/operations/base.py:Operation.formatted_description`; [Operations: the base class and its two halves](../migrations/operations.md#category-describe-and-the-name-fragment)).

## The autodetector: `AlterConstraint` and unmanaged models

Since 5.2 a constraint changed only in what `BaseConstraint.non_db_attrs` names, `"violation_error_code"` and `"violation_error_message"`, becomes an `AlterConstraint`, which changes the state and nothing in the database (`django/db/migrations/autodetector.py:MigrationAutodetector._constraint_should_be_dropped_and_recreated`; [The autodetector: fields, indexes and constraints](../migrations/autodetector-fields.md#constraints-create_altered_constraints)).

Since 6.2 makemigrations tracks every change to an unmanaged model, so one changed since it was made gets a migration after the upgrade. The autodetector no longer keeps such models apart: a field added to one got no operation under 5.2.17, 6.0.8 and 6.1.1, and now gets an `AddField` (`django/db/migrations/autodetector.py:MigrationAutodetector._detect_changes`). Such an operation changes the state and no table, since `Operation.allow_migrate_model` refuses an unmanaged model (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`; [The autodetector: comparing two project states](../migrations/autodetector.md#detect_changes-the-models-sorted-then-the-generators-in-order)).

## Squashing a squashed migration

Since 6.0 squashmigrations squashes a range that holds a squashed migration, which 5.2.17 refuses with `CommandError`. The new migration's `replaces` names the squashed migration itself, not the migrations it replaced. The loader follows such a chain down to the migrations that replace nothing (`django/db/migrations/loader.py:MigrationLoader._resolve_replaced_migration_keys`; [Squashed migrations: `replaces` and the squashmigrations command](../migrations/squashing.md#a-replacing-migration-that-is-replaced)).
