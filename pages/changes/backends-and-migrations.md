---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the database backends and migrations

From Django 5.0 to this commit the backends gained connection pools, SQLite's `"init_command"` and `"transaction_mode"`, MySQL's `"utf8mb4"` and oracledb as Oracle's only driver; `savepoint` was deprecated for `savepoint_create`; and the hooks a third-party backend supplies changed in 5.0, 5.2, 6.0 and 6.1. Migrations write more values, squash a squashed migration, and since 6.2 follow every change to an unmanaged model.

For a project, a connection opens much as it did: MySQL's asks for another character set, Oracle's needs oracledb, and PostgreSQL's and Oracle's may come from a pool. The larger change is for whoever writes a backend: its classes changed release after release, several to carry new features of the ORM, and a hook renamed or removed is no longer called, without a word. Migrations went the other way, towards doing what they once refused or passed over.

## Connection pools: PostgreSQL and Oracle

Since 5.1 PostgreSQL's backend, and since 5.2 Oracle's, can take connections from a pool. With `"pool"` in an alias's `"OPTIONS"`, the `pool` property makes one pool for the alias (Oracle's, for the alias and its `"USER"`), and `get_new_connection` takes each connection from it (`django/db/backends/postgresql/base.py:DatabaseWrapper.pool`, `django/db/backends/oracle/base.py:DatabaseWrapper.pool`). PostgreSQL's is psycopg_pool's, refused under psycopg2; Oracle's is oracledb's; both refuse a `"CONN_MAX_AGE"` other than 0. The 5.1 notes' reason: opening a connection can take relatively long, and keeping connections open can reduce latency (`docs/releases/5.1.txt`; [Opening and closing a connection](../backends/lifecycle.md#connection-pools-postgresql-and-oracle)).

## Opening a connection: SQLite's options, MySQL's character set, Oracle's driver

Since 5.1 SQLite's backend takes two keys out of `"OPTIONS"` (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_connection_params`). `"init_command"` is split at each semicolon, each command run on every new connection. `"transaction_mode"`, `"DEFERRED"`, `"EXCLUSIVE"` or `"IMMEDIATE"` in any case, is written after the `"BEGIN"` of an outermost atomic block, and any other string raises `ImproperlyConfigured` ([SQLite](../backends/sqlite.md#opening-a-connection-get_connection_params-and-get_new_connection)).

Since 5.2 MySQL's backend asks for the character set `"utf8mb4"`, where it asked for `"utf8"`, which the notes call an alias of the deprecated `"utf8mb3"`; a `"charset"` in `"OPTIONS"` still replaces it (`django/db/backends/mysql/base.py:DatabaseWrapper.get_connection_params`; [MySQL and MariaDB](../backends/mysql.md#the-driver-mysqldb-and-opening-a-connection)).

5.0 added oracledb to Oracle's backend and deprecated cx_Oracle, which 6.0 removed: at this commit the backend imports oracledb alone (`django/db/backends/oracle/base.py`; [Oracle](../backends/oracle.md#the-driver-and-the-processs-environment)).

## Columns and values: UUIDs on MariaDB, integers on SQLite

Since 5.0 a `django.db.models.UUIDField` on MariaDB is a column of the type `"uuid"`, where it was `"char(32)"`, as MySQL's still is; the 5.0 notes ask that a field made before then be replaced by a subclass backed by `"char(32)"` (`django/db/backends/mysql/base.py:DatabaseWrapper.data_types`). The 5.0 notes say MariaDB 10.7 and later; at this commit the flag asks only whether the server is MariaDB (`django/db/backends/mysql/features.py:DatabaseFeatures.has_native_uuid_field`; [Column types: from a field to a column](../backends/column-types.md#mysqls-two-properties)).

Since 5.0 SQLite's operations give every integer field a 64-bit range, "to match the behavior of sqlite3", the notes say, and the validators of an integer field read it, so on SQLite a `SmallIntegerField` is validated up to 9223372036854775807 (`django/db/backends/sqlite3/operations.py:DatabaseOperations.integer_field_range`; [The field classes](../models/field-types.md#integers)).

## `savepoint`, deprecated for `savepoint_create`

6.1 added `django.db.transaction.savepoint_create` and deprecated `savepoint`, which now warns and calls it (`django/db/transaction.py:savepoint`; [Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#savepoints); [What still warns: the deprecations and the releases that end them](deprecations.md)).

## The backend API: hooks renamed, removed and added

Three changes to the classes a third-party backend supplies reach old code without a warning.

5.0 deprecated the operations' method field_cast_sql for `BaseDatabaseOperations.lookup_cast`, and 6.0 removed it: at this commit `BuiltinLookup.process_lhs` asks `lookup_cast` alone (`django/db/models/lookups.py:BuiltinLookup.process_lhs`). A backend that still overrides field_cast_sql is imitated with SQLite's connection, given, for the call, operations whose field_cast_sql casts to text:

```text recording=changes
a backend's operations that override field_cast_sql: the WHERE clause of Entry.objects.filter(title="Hull")
    5.2.17       CAST("journal_entry"."title" AS TEXT) = %s, warns RemovedInDjango60Warning
    6.0.8        "journal_entry"."title" = %s
    6.1.1        "journal_entry"."title" = %s
    this commit  "journal_entry"."title" = %s
```

5.2.17 applied the override and warned; from 6.0.8 it is passed over in silence ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../sql/lookups.md#builtinlookup-the-operator-from-the-backends-table)).

Since 6.1 `DurationField.get_db_prep_value` hands a duration to `BaseDatabaseOperations.adapt_durationfield_value`, whose base gives an integer of microseconds and which PostgreSQL's and Oracle's operations override to pass it through (`django/db/models/fields/__init__.py:DurationField.get_db_prep_value`). The 6.1 notes ask a backend with native durations to override it too. One that only set `BaseDatabaseFeatures.has_native_duration_field`, which `get_db_prep_value` read until then, is imitated with SQLite's connection, that flag set:

```text recording=changes
DurationField().get_db_prep_value(timedelta(seconds=1), connection): a backend whose features set has_native_duration_field and whose operations add no adapt_durationfield_value
    5.2.17       datetime.timedelta(seconds=1)
    6.0.8        datetime.timedelta(seconds=1)
    6.1.1        1000000
    this commit  1000000
```

Nothing warns of the change ([Values in and out: adapters, converters and time zones](../backends/values.md#the-operations-objects-adapters)).

6.0 renamed return_insert_columns and fetch_returned_insert_rows to `BaseDatabaseOperations.returning_columns` and `BaseDatabaseOperations.fetch_returned_rows`, which an `UPDATE … RETURNING` uses too, and removed fetch_returned_insert_columns; a method under an old name is no longer called ([Inserts: returned keys, conflicts and batch sizes](../backends/inserts.md#what-comes-back-returning_columns-fetch_returned_rows-and-last_insert_id)).

The other changes, some of them as silent:

| name | what changed | release |
|---|---|---|
| `BaseDatabaseFeatures.supports_expression_defaults`, `supports_default_keyword_in_insert`, `supports_default_keyword_in_bulk_insert` | new, true by default; where false, `"fields.E011"` refuses an expression as a `db_default`, and an insert writes the expression for `"DEFAULT"` | 5.0 |
| `BaseDatabaseOperations.adapt_decimalfield_value` | returns the value as given | 5.2 |
| `BaseDatabaseSchemaEditor.sql_delete_column` | no `"CASCADE"`, which PostgreSQL's editor inherited until then | 6.0 |
| `BaseDatabaseFeatures.can_return_rows_from_update` | new, false by default; where false, an update asked for columns back goes without `"RETURNING"` | 6.0 |
| `BaseDatabaseIntrospection.get_relations` | a third member in each value, the key's delete rule, which inspectdb writes as its `on_delete` | 6.1 |
| `BaseDatabaseFeatures.supports_inspectdb` | new, true by default; where false, inspectdb raises `CommandError` | 6.1 |
| `BaseDatabaseOperations.binary_placeholder_sql`, `BaseSpatialOperations.get_geom_placeholder_sql` | return SQL and parameters; the first is given the compiler, the second was get_geom_placeholder | 6.1 |
| `BaseDatabaseFeatures.supports_bit_aggregations` | new, true by default; where false, a bit aggregate raises `NotSupportedError`; Oracle's is true from 21 | 6.1 |

## What the migration serializer writes

Since 5.0 the serializer writes a function under `functools.cache` or `functools.lru_cache` by its name, its CPython class being among `FUNCTION_TYPES` (`django/db/migrations/serializer.py:FUNCTION_TYPES`; [Serializing values: `serializer_factory` and `deconstruct`](../migrations/serializer.md#the-registry-in-its-order)). Since 6.0 `ZoneInfoSerializer` writes a `zoneinfo.ZoneInfo`, which 5.2.17 refuses, and a keyword argument of a deconstructed call whose name is not an identifier goes into a dictionary after `**` (`django/db/migrations/serializer.py:DeconstructibleSerializer.serialize_deconstructed`). For a deconstructible class given such a keyword, 5.2.17 writes `"tides.Chart(depth=5, x-scale=2)"`, which is not Python, and 6.0.8 `"tides.Chart(depth=5, **{'x-scale': 2})"`.

Three changes stand in no release note. Since 6.0 a `functools.partial` is written as a deconstructed call, `functools.partial(int, base=2)` where 5.2.17 wrote `functools.partial(int, *(), **{'base': 2})` (`django/db/migrations/serializer.py:FunctoolsPartialSerializer`), and `DeconstructibleSerializer` is the name of what was DeconstructableSerializer, with no alias left. Since 6.1 `GenericAliasSerializer` writes a generic alias such as `list[int]` (`django/db/migrations/serializer.py:GenericAliasSerializer`).

## makemigrations: operation categories and the autodetector's class

Since 5.1 an operation has a category, `Operation.category`, a member of `OperationCategory` whose values are signs: `"+"` an addition, `"-"` a removal, `"~"` an alteration, `"p"` Python, `"s"` SQL, `"?"` a mix. makemigrations prints each operation's sign before its description, `"?"` for the base class's `None` (`django/db/migrations/operations/base.py:Operation.formatted_description`; [Operations: the base class and its two halves](../migrations/operations.md#category-describe-and-the-name-fragment)). Since 5.2 makemigrations and migrate make their autodetector from a class attribute, which a subclass of the command may replace (`django/core/management/commands/makemigrations.py:Command.autodetector`).

## The autodetector: `AlterConstraint` and unmanaged models

Since 5.2 a constraint changed only in what `BaseConstraint.non_db_attrs` names, `"violation_error_code"` and `"violation_error_message"`, becomes an `AlterConstraint`, which changes the state and nothing in the database (`django/db/migrations/autodetector.py:MigrationAutodetector._constraint_should_be_dropped_and_recreated`; [The autodetector: fields, indexes and constraints](../migrations/autodetector-fields.md#constraints-create_altered_constraints)).

The 6.2 notes say makemigrations now tracks every change to an unmanaged model, and that one changed since it was made gets a migration. Until 6.2 the autodetector kept such a model apart, and wrote for it only its creation, its deletion, and changes to its table's name or comment and to some options; at this commit it compares the model as it does any other (`django/db/migrations/autodetector.py:MigrationAutodetector._detect_changes`). The habit adds a field to one and compares the two states as makemigrations for journal would:

```text recording=changes
MigrationAutodetector, as makemigrations journal runs it, when an unmanaged model (Meta.managed = False) gains a field: the operations
    5.2.17       []
    6.0.8        []
    6.1.1        []
    this commit  ['AddField']
```

Such an operation changes the state and no table, since `Operation.allow_migrate_model` refuses a model that cannot be migrated: a schema editor collecting its SQL collects none, under every release (`django/db/migrations/operations/base.py:Operation.allow_migrate_model`; [The autodetector: comparing two project states](../migrations/autodetector.md#detect_changes-the-models-sorted-then-the-generators-in-order)).

## Squashing a squashed migration

Since 6.0 squashmigrations squashes a range that holds a squashed migration: 5.2.17 refuses with `CommandError`, "You cannot squash squashed migrations!", and from 6.0.8 the new migration's `replaces` names the squashed migration itself, not the migrations it replaced. The loader follows such a chain down to the migrations that replace nothing, whose rows decide whether it counts as applied, and refuses a cycle (`django/db/migrations/loader.py:MigrationLoader.replace_migration`; [Squashed migrations: `replaces` and the squashmigrations command](../migrations/squashing.md#a-replacing-migration-that-is-replaced)).
