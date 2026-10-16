---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the database backends and migrations

The changes from Django 5.0 to this commit in the database backends and migrations: connection pools, SQLite's `"init_command"` and `"transaction_mode"`, MySQL's `"utf8mb4"`, oracledb, the deprecated `savepoint`, the backend API, the migration serializer, operation categories, `AlterConstraint`, squashing and unmanaged models.

## Connection pools: PostgreSQL and Oracle

PostgreSQL's backend can take its connections from a pool since 5.1, and Oracle's since 5.2; without one, each thread's connection is the driver's own, kept or closed by `"CONN_MAX_AGE"`. With `"pool"` in an alias's `"OPTIONS"`, `True` or the pool's arguments, the backend's `pool` property makes one pool for the process, and each connection is taken from it as it opens (`django/db/backends/postgresql/base.py:DatabaseWrapper.pool`, `django/db/backends/oracle/base.py:DatabaseWrapper.pool`). PostgreSQL's pool is psycopg_pool's, refused under psycopg2, Oracle's is oracledb's, and both refuse a `"CONN_MAX_AGE"` other than 0. The release notes' reason: opening a connection can take relatively long, and keeping connections open can reduce latency (`docs/releases/5.1.txt`; [Opening and closing a connection](../backends/lifecycle.md#connection-pools-postgresql-and-oracle)).

## SQLite's and MySQL's connection options

Since 5.1 SQLite's backend takes two keys out of `"OPTIONS"` before the rest reach `sqlite3.connect` (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_connection_params`). `"init_command"` is split at each semicolon, each command run on every new connection after Django's two pragmas (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_new_connection`). `"transaction_mode"`, `"DEFERRED"`, `"EXCLUSIVE"` or `"IMMEDIATE"`, capitals or not, is written after the `"BEGIN"` that opens an outermost atomic block, and any other string raises `ImproperlyConfigured` (`django/db/backends/sqlite3/base.py:DatabaseWrapper._start_transaction_under_autocommit`; [SQLite](../backends/sqlite.md#opening-a-connection-get_connection_params-and-get_new_connection)).

Since 5.2 MySQL's backend asks for the character set `"utf8mb4"`, where it asked for `"utf8"`, which the release notes call an alias of the deprecated `"utf8mb3"`; a `"charset"` in `"OPTIONS"` still wins (`django/db/backends/mysql/base.py:DatabaseWrapper.get_connection_params`; [MySQL and MariaDB](../backends/mysql.md#the-driver-mysqldb-and-opening-a-connection)).

## Columns and values: UUIDs on MariaDB, integers on SQLite

Since 5.0 a `UUIDField` on MariaDB is a column of the database's type `"uuid"`, where it was `"char(32)"`, as it still is on MySQL (`django/db/backends/mysql/base.py:DatabaseWrapper.data_types`). The release notes say MariaDB 10.7 and later; at this commit the flag is whether the server is MariaDB at all (`django/db/backends/mysql/features.py:DatabaseFeatures.has_native_uuid_field`). The field writes a `uuid.UUID` for a native column and its hex otherwise (`django/db/models/fields/__init__.py:UUIDField.get_db_prep_value`), so a `"char(32)"` column an earlier release made on MariaDB no longer matches ([Column types: from a field to a column](../backends/column-types.md#mysqls-two-properties)).

Since 5.0 SQLite's operations object gives every integer field a 64-bit range, from 0 for the positive ones, its comment saying that sqlite3 supports integers up to 64 bits (`django/db/backends/sqlite3/operations.py:DatabaseOperations.integer_field_range`). `IntegerField.validators` and `IntegerFieldOverflow` read that range, so on SQLite a `SmallIntegerField` is validated up to 9223372036854775807 ([The field classes](../models/field-types.md#integers)).

## The Oracle driver: oracledb only

5.0 added oracledb and deprecated cx_Oracle, and 6.0 removed cx_Oracle. At this commit `django/db/backends/oracle/base.py` imports `oracledb` alone, and raises `ImproperlyConfigured` where it cannot ([Oracle](../backends/oracle.md#the-driver-and-the-processs-environment)).

## `savepoint`, deprecated for `savepoint_create`

Since 6.1 `django.db.transaction.savepoint` warns with `RemovedInDjango2028Warning` and calls `savepoint_create` (`django/db/transaction.py:savepoint`; [Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#savepoints); [What still warns: the deprecations and the releases that end them](deprecations.md)).

## The backend API

The classes a third-party backend supplies, and what they may call, changed in 5.0, 5.2, 6.0 and 6.1, in part to carry a feature of the ORM: database defaults (5.0), an update's `"RETURNING"` (6.0), the database's own on_delete and the bit aggregates (6.1).

| name | what changed | where now |
|---|---|---|
| `BaseDatabaseFeatures.supports_expression_defaults`, `BaseDatabaseFeatures.supports_default_keyword_in_insert`, `BaseDatabaseFeatures.supports_default_keyword_in_bulk_insert` | new, true by default; where false, the check `"fields.E011"` refuses an expression as a `db_default`, and an insert writes the default's expression where it would write `"DEFAULT"` (SQLite lacks the second, Oracle the third) (5.0) | `django/db/models/fields/__init__.py:Field._check_db_default`, `django/db/models/expressions.py:DatabaseDefault.as_sql`, `django/db/models/sql/compiler.py:SQLInsertCompiler.as_sql` |
| `BaseDatabaseOperations.lookup_cast` | replaces field_cast_sql, deprecated in 5.0 and removed in 6.0, in `BuiltinLookup.process_lhs` (5.0, 6.0) | `django/db/models/lookups.py:BuiltinLookup.process_lhs` |
| `BaseDatabaseOperations.adapt_decimalfield_value` | a no-op: returns the value as given (5.2) | `django/db/backends/base/operations.py:BaseDatabaseOperations.adapt_decimalfield_value` |
| `Model._is_pk_set` | new: whether an instance's key, each column of a composite one, is set (5.2) | [What changed in models and fields](models.md) |
| `BaseDatabaseOperations.returning_columns`, `BaseDatabaseOperations.fetch_returned_rows`, `BaseDatabaseFeatures.can_return_rows_from_update` | the methods renamed from return_insert_columns and fetch_returned_insert_rows, serving an update's `"RETURNING"` too, the second given the returning parameters; fetch_returned_insert_columns gone; the flag new, false by default (6.0) | [Inserts: returned keys, conflicts and batch sizes](../backends/inserts.md#what-comes-back-returning_columns-fetch_returned_rows-and-last_insert_id) |
| `BaseDatabaseSchemaEditor.sql_delete_column` | no `"CASCADE"`, and PostgreSQL's editor adds none (6.0) | [The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md#adding-and-removing-a-field-and-deleting-a-table) |
| `BaseDatabaseOperations.adapt_durationfield_value` | new: a duration for the driver, an integer of microseconds, or the value itself on PostgreSQL and Oracle (6.1) | `django/db/backends/base/operations.py:BaseDatabaseOperations.adapt_durationfield_value` |
| `BaseDatabaseIntrospection.get_relations` | a third member, the delete rule, which inspectdb writes as `DB_CASCADE` and its like (6.1) | [Introspection: reading the schema back](../backends/introspection.md#keys-and-relations-get_relations-and-get_primary_key_columns) |
| `BaseDatabaseFeatures.supports_inspectdb` | new, true by default; where false, inspectdb raises `CommandError` (6.1) | `django/core/management/commands/inspectdb.py:Command.handle` |
| `BaseDatabaseOperations.binary_placeholder_sql`, `BaseSpatialOperations.get_geom_placeholder_sql` | return the SQL and a tuple of parameters; the first is given the compiler, the second renamed from get_geom_placeholder (6.1) | `django/db/backends/base/operations.py:BaseDatabaseOperations.binary_placeholder_sql`, `django/contrib/gis/db/backends/base/operations.py:BaseSpatialOperations.get_geom_placeholder_sql` |
| `BaseDatabaseFeatures.supports_bit_aggregations` | new, true by default; where false, `BitAggregate.as_sql` raises `NotSupportedError`; on Oracle, true from 21 (6.1) | `django/db/models/aggregates.py:BitAggregate.as_sql` |

The flag prohibits_dollar_signs_in_column_aliases of the features is gone, removed in 6.1, the release that began quoting aliases ([What changed in expressions, lookups and the compiler](sql.md)).

## What the migration serializer writes

The migration serializer writes values it could not write before ([Serializing values: `serializer_factory` and `deconstruct`](../migrations/serializer.md)). Since 5.0 a function under `functools.cache` or `functools.lru_cache` is written by name: on CPython it is an instance of `functools._lru_cache_wrapper`, which the serializer adds to `FUNCTION_TYPES` (`django/db/migrations/serializer.py:FUNCTION_TYPES`). Since 6.0 `ZoneInfoSerializer` writes a `zoneinfo.ZoneInfo`, and keyword arguments of a deconstructed call whose names are not identifiers go into a dictionary after `**` (`django/db/migrations/serializer.py:DeconstructibleSerializer.serialize_deconstructed`).

```text
# migration_values.py at this commit: a value, and serializer_factory(value).serialize()
# (tides is the project's: high_water under functools.cache, Chart deconstructible)
tides.high_water                           ('tides.high_water', {'import tides'})
zoneinfo.ZoneInfo("Europe/London")         ("zoneinfo.ZoneInfo(key='Europe/London')", {'import zoneinfo'})
tides.Chart(**{"x-scale": 2, "depth": 5})  ("tides.Chart(depth=5, **{'x-scale': 2})", {'import tides'})
```

## Operation categories

Since 5.1 an operation has a **category**, `Operation.category`, a member of `OperationCategory`, whose values are signs: `"+"` an addition, `"-"` a removal, `"~"` an alteration, `"p"` Python, `"s"` SQL, `"?"` a mix. makemigrations prints `Operation.formatted_description`, sign and description, for each operation it writes or merges; a category of `None`, the base class's, shows `"?"` (`django/db/migrations/operations/base.py:Operation.formatted_description`; [Operations: the base class and its two halves](../migrations/operations.md#category-describe-and-the-name-fragment)).

## The autodetector: `AlterConstraint`, unmanaged models and its class

Since 5.2 a constraint changed only in the attributes `BaseConstraint.non_db_attrs` lists, `violation_error_message` and `violation_error_code`, becomes an `AlterConstraint`, which changes the project state and sends nothing; a constraint changed otherwise is still removed and added, in the database too, except where a field it names was renamed and kept its db_column (`django/db/migrations/autodetector.py:MigrationAutodetector._constraint_should_be_dropped_and_recreated`; [The autodetector: fields, indexes and constraints](../migrations/autodetector-fields.md#constraints-create_altered_constraints)).

Since 6.2 makemigrations tracks every change to a model with `managed = False`, and, the release notes warn, unmanaged models changed since they were made get new migrations. `MigrationAutodetector._detect_changes` sorts an unmanaged model with the others (`django/db/migrations/autodetector.py:MigrationAutodetector._detect_changes`); its operations change the state and no table, since `Operation.allow_migrate_model` refuses a model whose options say it cannot be migrated (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`), and the questioner is asked no default for a field it gains that cannot be null ([The autodetector: comparing two project states](../migrations/autodetector.md#detect_changes-the-models-sorted-then-the-generators-in-order)).

Since 5.2 makemigrations and migrate make their autodetector from a class attribute, by default `MigrationAutodetector` (`django/core/management/commands/makemigrations.py:Command.autodetector`, `django/core/management/commands/migrate.py:Command.autodetector`).

## Squashing a squashed migration

Since 6.0 squashmigrations squashes a range that holds a squashed migration, and the new migration's `replaces` names it. The loader follows the chain down to migrations that replace nothing, whose rows decide whether it counts as applied, and refuses a cycle with `CommandError` (`django/db/migrations/loader.py:MigrationLoader._resolve_replaced_migration_keys`, `django/db/migrations/loader.py:MigrationLoader.replace_migration`; [Squashed migrations: `replaces` and the squashmigrations command](../migrations/squashing.md#a-replacing-migration-that-is-replaced)).
