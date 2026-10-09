---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What a database can do: `BaseDatabaseFeatures`

`BaseDatabaseFeatures` is the class of a connection's features object, `BaseDatabaseWrapper.features`: **flags**, attributes that say what one database can do, which the compiler, the queryset, the schema editor, migrations and the test framework read before they choose what to write or whether to refuse. A flag is a class attribute, a property, a `cached_property` worked out once for each connection, or a value the connection sets on the object.

Code above the backend is written once for every database, and where the databases differ in what they can do it mostly does not ask which database it faces: it asks the question it needs answered. The compiler writes a `"FOR UPDATE"` only where `BaseDatabaseFeatures.has_select_for_update` is true, `bulk_create` asks for the new rows' keys only where `BaseDatabaseFeatures.can_return_rows_from_bulk_insert` is, and the schema editor runs a migration inside a transaction only where `BaseDatabaseFeatures.can_rollback_ddl` is (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.__init__`). Each such question is a flag of the connection's features object, an instance of the backend's own subclass of `BaseDatabaseFeatures` (`django/db/backends/base/features.py:BaseDatabaseFeatures`). The base class declares the flags that code common to every backend reads, with a default for each, and a backend's class overrides what differs for its database. GeoDjango's spatial backends add the flags of `BaseSpatialFeatures` (`django/contrib/gis/db/backends/base/features.py:BaseSpatialFeatures`), and a backend may declare flags of its own besides, which only its own code and its vendor methods read, as the database function `UUID4` reads PostgreSQL's `is_postgresql_18` in `UUID4.as_postgresql` (`django/db/models/functions/uuid.py:UUID4.as_postgresql`). A backend from outside Django sets them for its own database.

## A flag, and where its value comes from

`BaseDatabaseWrapper.__init__` makes the features object as it makes the connection, from `BaseDatabaseWrapper.features_class`, and the object keeps the connection it was made for (`django/db/backends/base/features.py:BaseDatabaseFeatures.__init__`). There is one for each connection, then, and a connection is one alias in one thread ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)). Code asks a question by reading an attribute, and the attribute can get its value in four ways.

The plain flag is a **class attribute**: the base class gives the default, and the backend's class body sets another value where its database differs. Most are true or false, and most of their comments in the base class put the flag as a question: whether the backend supports JSONField, whether DDL can be rolled back in a transaction. The rest are values that code uses as they stand, such as `BaseDatabaseFeatures.max_query_params`, a number or `None`, and `BaseDatabaseFeatures.bare_select_suffix`, text to put after a `"SELECT"` that has no table.

SQLite is a library in Django's own process, and its version is known without a connection. SQLite's `DatabaseFeatures.supports_aggregate_order_by_clause` is set in the class body by comparing the library's version with 3.44.0, when the module is imported (`django/db/backends/sqlite3/features.py:DatabaseFeatures.supports_aggregate_order_by_clause`). What follows was recorded from a running Django on SQLite, each line a question and its answer after `->`; the connection's `Database` is the driver's module:

```text recording=backends
connection.Database.sqlite_version_info  ->  (3, 50, 4)
connection.features.minimum_database_version  ->  (3, 37)
...
connection.features.supports_aggregate_order_by_clause  ->  True
```

A **property** works its value out at each read. Some are another flag read under a second name: SQLite's `DatabaseFeatures.can_introspect_json_field` and `DatabaseFeatures.has_json_object_function` are its `supports_json_field` (`django/db/backends/sqlite3/features.py:DatabaseFeatures.can_introspect_json_field`). SQLite's `DatabaseFeatures.max_query_params` is a property that makes sure the connection is open and asks the driver's connection for the number of parameters a statement may hold: 32766 unless the library was compiled with another limit, or less where the connection has lowered its own (`django/db/backends/sqlite3/features.py:DatabaseFeatures.max_query_params`).

A **`cached_property`** works its value out at the first read and puts it in the object's own dictionary, where every later read finds it without calling the method again (`django/utils/functional.py:cached_property.__get__`). On the four backends a flag whose answer takes a connection or a statement, because it depends on the server's version or settings or asks the database by trying, is a `cached_property` or a property that reads one, so that the cost is paid once, SQLite's `max_query_params` aside, as a connection can lower its limit. The cache belongs to the features object, and so to one connection: a second thread's connection to the same alias works each such flag out again for itself, and a connection that is closed and opened again keeps the answers.

A flag can also be **set on the object** by the connection. Oracle's `DatabaseWrapper.__init__` sets `BaseDatabaseFeatures.can_return_columns_from_insert` and `BaseDatabaseFeatures.can_return_rows_from_update` on its features object to the alias's `"OPTIONS"` entry `"use_returning_into"`, true unless the setting gives it, and its `DatabaseWrapper.get_connection_params` leaves the entry out of the driver's arguments; an attribute set on the object hides the class's for that one connection (`django/db/backends/oracle/base.py:DatabaseWrapper.__init__`).

One flag of the base class is a **method**, given a model. Where the backend has `BaseDatabaseFeatures.allows_group_by_selected_pks`, the compiler drops from a grouping the other columns of a table whose primary key is grouped, and `BaseDatabaseFeatures.allows_group_by_selected_pks_on_model` allows that only for a managed model, since an unmanaged one could stand for a view, on which the database might not allow that (`django/db/backends/base/features.py:BaseDatabaseFeatures.allows_group_by_selected_pks_on_model`, `django/db/models/sql/compiler.py:SQLCompiler.collapse_group_by`) ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](../sql/grouping.md)).

## How a flag reaches the server's version

A flag that depends on the server's version reads it from the connection. PostgreSQL's, MySQL's and Oracle's backends keep the version on the connection as a `cached_property` of their own, which gets it through `BaseDatabaseWrapper.temporary_connection`: that uses the open connection where there is one, and otherwise opens one and closes it afterwards ([Opening and closing a connection](lifecycle.md)).

PostgreSQL's `DatabaseWrapper.pg_version` is the server's version as one number, 170000 for 17.0, read from the driver's connection (`django/db/backends/postgresql/base.py:DatabaseWrapper.pg_version`); its features compare it in `DatabaseFeatures.is_postgresql_18`, which other flags read in turn (`django/db/backends/postgresql/features.py:DatabaseFeatures.is_postgresql_18`). Some of PostgreSQL's flags read the alias's options instead: `DatabaseFeatures.uses_server_side_binding`, whether psycopg 3 is the driver and `"server_side_binding"` is `True`, decides `DatabaseFeatures.max_query_params` (`django/db/backends/postgresql/features.py:DatabaseFeatures.max_query_params`) ([PostgreSQL](postgresql.md)).

MySQL's `DatabaseWrapper.mysql_server_data` runs one statement for everything the backend wants to know of the server: the version string, the SQL mode, the default storage engine, whether `"SQL_AUTO_IS_NULL"` is on, whether table names are kept in lower case, and whether the server's time zone tables are loaded; `DatabaseWrapper.mysql_version` and `DatabaseWrapper.mysql_is_mariadb` are worked out from it and cached in turn (`django/db/backends/mysql/base.py:DatabaseWrapper.mysql_server_data`). That is how one features class answers for two databases: MySQL's `DatabaseFeatures.can_return_columns_from_insert` is whether the server is MariaDB and `DatabaseFeatures.has_select_for_update_of` whether it is not (`django/db/backends/mysql/features.py:DatabaseFeatures`). [MySQL and MariaDB](mysql.md) has the rest.

Oracle's `DatabaseWrapper.oracle_version` is the driver's connection's version string as a tuple of numbers, and its features compare it for frame exclusion in a window, a `"SELECT"` without `"FROM DUAL"`, tuple lookups and stored generated columns among others (`django/db/backends/oracle/base.py:DatabaseWrapper.oracle_version`). SQLite's `DatabaseWrapper.get_database_version` is the library's version as the driver reports it (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_database_version`).

## `minimum_database_version` and the version check

`BaseDatabaseFeatures.minimum_database_version` is the oldest version of the database the backend supports, as a tuple, and `None` in the base class. `BaseDatabaseWrapper.check_database_version_supported` compares the backend's `BaseDatabaseWrapper.get_database_version` with it and raises `NotSupportedError` where the version is older; a backend that leaves the flag at `None` is never checked (`django/db/backends/base/base.py:BaseDatabaseWrapper.check_database_version_supported`). `BaseDatabaseWrapper.init_connection_state` calls it for each alias until it passes once in a process, keeping the aliases that have passed in `RAN_DB_VERSION_CHECK` (`django/db/backends/base/base.py:BaseDatabaseWrapper.init_connection_state`). The values are SQLite 3.37, PostgreSQL 16 and Oracle 19 as class attributes, and on MySQL a `cached_property` that answers 10.11 for MariaDB and 8.4 for MySQL (`django/db/backends/mysql/features.py:DatabaseFeatures.minimum_database_version`). The recorded library, 3.50.4, is newer than SQLite's 3.37, and the first connection opened without complaint.

> **Changed in 6.2.** PostgreSQL's minimum is 16: the release notes of 6.2 drop PostgreSQL 15, whose upstream support ends in November 2027 (`docs/releases/6.2.txt`). Those of 6.1 raised SQLite to 3.37.0, MySQL to 8.4 and MariaDB to 10.11 (`docs/releases/6.1.txt`).

## A flag that asks the database: `supports_transactions`

`BaseDatabaseFeatures.supports_transactions` is the base class's example of a flag that finds its answer by trying. It is a `cached_property` that, on a cursor of the connection, creates a table, turns autocommit off, inserts a row, rolls back, turns autocommit on, counts the rows and drops the table; the database supports transactions if the count is nought (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_transactions`).

None of the backends Django ships runs that probe: SQLite's, PostgreSQL's and Oracle's set the flag true, the dummy backend's sets it false, and MySQL's reads the server's data (`django/db/backends/mysql/features.py:DatabaseFeatures.supports_transactions`). The probe is for a backend that does not say.

The probe that runs on SQLite is its `DatabaseFeatures.supports_json_field`, which executes a `"SELECT"` of SQLite's JSON function inside an atomic block and answers false if the database raises `OperationalError` (`django/db/backends/sqlite3/features.py:DatabaseFeatures.supports_json_field`). Here it is read for the first time on the connection, with the object's own dictionary asked before and after; under the question stand the statements it sent, a line beginning `SQL` as Django handed it to its cursor and one beginning sqlite as SQLite ran it:

```text recording=backends
'supports_json_field' in vars(connection.features)  ->  False
connection.features.supports_json_field  ->  True
  SQL BEGIN
  sqlite BEGIN
  SQL SELECT JSON('{"a": "b"}')
  sqlite SELECT JSON('{"a": "b"}')
  sqlite COMMIT
'supports_json_field' in vars(connection.features)  ->  True
```

The `"BEGIN"` is SQLite's backend starting the atomic block, and the commit, made by the driver's own method, has no `SQL` line ([Transactions: autocommit, `atomic` and savepoints](transactions.md)). Oracle's `DatabaseFeatures.supports_collation_on_charfield` is another such probe (`django/db/backends/oracle/features.py:DatabaseFeatures.supports_collation_on_charfield`).

## Who reads the features

Of the features' readers, the compiler reads the most: the lock and each of its options, the compound statements, chunked reads, the grouping, and whether an insert asks for rows back ([The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md), [INSERT, UPDATE and DELETE: the insert, update and delete compilers](../sql/writing.md)). Expressions read them as they compile, to refuse or to write something else: `Window.as_sql` raises `NotSupportedError` on a backend without `BaseDatabaseFeatures.supports_over_clause`, and where `BaseDatabaseFeatures.supports_aggregate_filter_clause` is false an aggregate's filter raises it too, which `Aggregate.as_sql` catches to write the filter as a `"CASE"` (`django/db/models/expressions.py:Window.as_sql`, `django/db/models/aggregates.py:Aggregate.as_sql`).

The queryset reads them where it chooses before it compiles: for conflicts and returned rows in `bulk_create` ([`bulk_create` and `bulk_update`](../querysets/bulk.md)), and in `QuerySet.get`, which limits the rows it fetches unless the query locks them on a backend that cannot lock a sliced query (`django/db/models/query.py:QuerySet.get`). `Model._save_table` reads `BaseDatabaseFeatures.can_return_columns_from_insert` to choose what a save asks back ([Saving an instance](../models/saving.md)), and the manager of a many-to-many relation adds rows to an automatic table with conflicts ignored where `BaseDatabaseFeatures.supports_ignore_conflicts` holds (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`). The operations object, which writes the database's SQL, reads its own connection's flags, `BaseDatabaseOperations.bulk_batch_size` dividing `BaseDatabaseFeatures.max_query_params`, and the connection reads `BaseDatabaseFeatures.uses_savepoints` before each savepoint on every backend but SQLite, whose connection asks only whether it is inside an atomic block (`django/db/backends/sqlite3/base.py:DatabaseWrapper._savepoint_allowed`) ([Transactions: autocommit, `atomic` and savepoints](transactions.md)).

The schema editor reads them as it writes DDL: whether a migration runs in a transaction, whether foreign keys, check constraints, comments and partial, covering and expression indexes are written at all, whether a default has to be written as a literal ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)). And the test framework reads `BaseDatabaseFeatures.supports_transactions` and `uses_savepoints` for `TestCase`, and any flag by name through `skipUnlessDBFeature` and its relatives, which a test gives as strings (`django/test/testcases.py:skipUnlessDBFeature`) ([The test framework](../testing.md)). `BaseDatabaseFeatures.django_test_skips` and `BaseDatabaseFeatures.django_test_expected_failures` name tests of Django's own suite to skip or to expect to fail on the database, and are read only when that suite runs (`django/db/backends/base/creation.py:BaseDatabaseCreation.mark_expected_failures_and_skips`) ([Test databases: `BaseDatabaseCreation`](creation.md)).

## Chosen flags on the four backends

The flags of `BaseDatabaseFeatures` in the table differ by backend.

| flag | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| `supports_transactions` | true | true | true unless the default storage engine is MyISAM | true |
| `can_release_savepoints` | true | true | false | false |
| `can_rollback_ddl` | true | true | false | false |
| `can_return_columns_from_insert` | true | true | true on MariaDB, false on MySQL | true unless `"use_returning_into"` is false |
| `can_return_rows_from_bulk_insert` | true | true | true on MariaDB, false on MySQL | false |
| `can_return_rows_from_update` | true | true | false | true unless `"use_returning_into"` is false |
| `supports_ignore_conflicts` | true | true | true | false |
| `supports_update_conflicts` | true | true | true | false |
| `supports_update_conflicts_with_target` | true | true | false | false |
| `has_select_for_update` | false | true | true | true |
| `has_select_for_update_nowait` | false | true | true | true |
| `has_select_for_update_skip_locked` | false | true | true | true |
| `has_select_for_update_of` | false | true | true on MySQL, false on MariaDB | true |
| `has_select_for_no_key_update` | false | true | false | false |
| `supports_select_for_update_with_limit` | true | true | true | false |
| `supports_frame_exclusion` | true | true | false | by version: 21 and later |
| `supports_json_field` | asks the database, once for each connection | true | true | true |
| `has_native_json_field` | false | true | false | false |
| `supports_json_field_contains` | false | true | true | false |
| `interprets_empty_strings_as_nulls` | false | false | false | true |
| `supports_timezones` | false | true | false | false |
| `has_zoneinfo_database` | true | true | whether the server's time zone tables are loaded | true |
| `supports_comments` | false | true | true | true |
| `supports_aggregate_order_by_clause` | by the library's version: 3.44.0 and later | true | true | true |
| `supports_stored_generated_columns` | true | true | true | by version: 23.7 and later |
| `supports_virtual_generated_columns` | true | by version: 18 and later | true | true |
| `max_query_params` | the connection's limit, asked at each read: 32766 unless the library was compiled otherwise or the connection lowered it | none; 65535 where parameters are bound on the server under psycopg 3 | none | 65535 |

*Chosen flags of `BaseDatabaseFeatures` on the four database backends Django ships (`django/db/backends/sqlite3/features.py`, `django/db/backends/postgresql/features.py`, `django/db/backends/mysql/features.py`, `django/db/backends/oracle/features.py`). "By version" is the server's, or on SQLite the library's; "none" is `None`, no limit. The insert and conflict flags are told in [Inserts: returned keys, conflicts and batch sizes](inserts.md), and `can_rollback_ddl` in [The schema editor: `BaseDatabaseSchemaEditor`](schema.md).*
