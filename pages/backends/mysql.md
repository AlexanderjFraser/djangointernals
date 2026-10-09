---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# MySQL and MariaDB

Django's backend `django.db.backends.mysql` serves two databases, MySQL and MariaDB, through one driver, `MySQLdb`. It asks the server which of the two it is, of what version and with what settings, keeps the answer as `mysql_server_data`, and turns much of what its features, its operations object and its schema editor say on that answer.

Django gives the two databases one package and one vendor: `DatabaseWrapper.vendor` is `"mysql"` for both, and an expression's `as_mysql` method serves both (`django/db/backends/mysql/base.py:DatabaseWrapper`, `django/db/models/sql/compiler.py:SQLCompiler.compile`). What sets the backend apart from the base classes comes from the server, which says which of the two it is and has settings Django reads; from what Django asks of each connection as it opens; and from the database's own SQL and limits.

## One backend for two databases

`DatabaseWrapper.mysql_server_data` is a cached property (`django/db/backends/mysql/base.py:DatabaseWrapper.mysql_server_data`). The first time anything asks it of a connection, it sends one `"SELECT"` through `BaseDatabaseWrapper.temporary_connection`, which opens the connection for the question if it is closed and closes it again after, and it keeps the answer for the rest of the connection object's life, through every close and reopening. The statement asks for the server's version and four of its variables, and whether `"CONVERT_TZ"` from UTC to UTC gives anything but null, which the comment says it does only where the server's time zone tables are loaded. Each connection object asks for itself, so two threads using one alias each ask. And since opening a connection reads the reply too, in `DatabaseWrapper.init_connection_state`, a first question put to a closed connection sends the statement twice, once for the opening and once for the question.

Asked of a connection not yet open, on a stand-in for the driver's connection that answers as MySQL 8.4, with no server running and lines left out; in this recording, the lines set in under a line of Python are the calls it made, nested as they were made, and a line `SQL` is a statement as Django handed it to its cursor:

```text recording=backends
server = mysql_asked.mysql_server_data
  DatabaseWrapper.mysql_server_data  (on "mysql")
    BaseDatabaseWrapper.temporary_connection  (on "mysql")
      BaseDatabaseWrapper.connect  (on "mysql")
...
        DatabaseWrapper.init_connection_state  (on "mysql")
          BaseDatabaseWrapper.init_connection_state  (on "mysql")
            BaseDatabaseWrapper.check_database_version_supported  (on "mysql")
              DatabaseWrapper.mysql_server_data  (on "mysql")
                BaseDatabaseWrapper.temporary_connection  (on "mysql")
                SQL (on "mysql") SELECT VERSION(), @@sql_mode, @@default_storage_engine, @@sql_auto_is_null, @@lower_case_table_names, CONVERT_TZ('2001-01-01 01:00:00', 'UTC', 'UTC') IS NOT NULL
...
        Signal.send  (connection_created, sender=DatabaseWrapper)
    SQL (on "mysql") SELECT VERSION(), @@sql_mode, @@default_storage_engine, @@sql_auto_is_null, @@lower_case_table_names, CONVERT_TZ('2001-01-01 01:00:00', 'UTC', 'UTC') IS NOT NULL
    BaseDatabaseWrapper.temporary_connection resumes
      BaseDatabaseWrapper.close  (on "mysql")
```

The version is read from the reply by cached properties too (`django/db/backends/mysql/base.py:DatabaseWrapper.mysql_version`). `DatabaseWrapper.mysql_version` matches the start of the version string, `DatabaseWrapper.mysql_server_info`, against `server_version_re`, three numbers of one or two digits joined by dots, so that `"8.4.6"` becomes `(8, 4, 6)` and `"10.11.8-MariaDB-log"` becomes `(10, 11, 8)`. `DatabaseWrapper.mysql_is_mariadb` is whether the string, in lower case, contains `"mariadb"`, and nothing else tells the two databases apart.

`DatabaseWrapper.get_database_version` returns `mysql_version`, and `DatabaseFeatures.minimum_database_version` is `(10, 11)` where the server is MariaDB and `(8, 4)` where it is MySQL, so the check of the version, made once for each alias as its first connection opens, asks the server before it can compare (`django/db/backends/mysql/features.py:DatabaseFeatures.minimum_database_version`) ([Opening and closing a connection](lifecycle.md)). `DatabaseWrapper.display_name`, a class attribute on the other backends, is here a cached property that says `"MariaDB"` or `"MySQL"` by the same test, so that the refusal of a server too old, and every warning of the checks, name the database the server is (`django/db/backends/mysql/base.py:DatabaseWrapper.display_name`, `django/db/backends/base/base.py:BaseDatabaseWrapper.check_database_version_supported`).

Which of the two it is decides much else: most of the features that ask the server; the operations object's regular expressions and conflict clause; how the schema editor drops a check and defaults a text column; `DatabaseWrapper.data_types`, a cached property here, which maps `"UUIDField"` to the column `"uuid"` on MariaDB alone (`django/db/backends/mysql/base.py:DatabaseWrapper.data_types`) ([Column types: from a field to a column](column-types.md)); and expressions written for the vendor, such as `Cast.as_mysql` (`django/db/models/functions/comparison.py:Cast.as_mysql`). The version itself, beyond the oldest supported, is read in this backend only by the features of the UUID functions on MariaDB.

> **Changed in 6.1.** The oldest servers supported are MySQL 8.4 and MariaDB 10.11. The release notes give the end of upstream support for MySQL 8.0 and MariaDB 10.6, and call the releases between them short-term ones (`docs/releases/6.1.txt`).

## The driver, `MySQLdb`, and opening a connection

The backend's base module imports `MySQLdb`, from the package mysqlclient, as `DatabaseWrapper.Database`, and raises `ImproperlyConfigured` where the import fails or `MySQLdb.version_info` is older than 2.2.1 (`django/db/backends/mysql/base.py`). The driver takes Django's `"%s"` placeholders as they are, and the backend rewrites none ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)).

`DatabaseWrapper.get_connection_params` builds the keyword arguments for `MySQLdb.connect` (`django/db/backends/mysql/base.py:DatabaseWrapper.get_connection_params`). It passes on whichever of the user, database, password, host and port are set, a `"HOST"` that begins with a slash as a Unix socket, with `django_conversions`, the driver's table of conversions ([Values in and out: adapters, converters and time zones](values.md)), `"utf8mb4"` for the `"charset"`, and the client flag FOUND_ROWS. Then it lays `"OPTIONS"`, less `"isolation_level"`, over the arguments, so that anything `MySQLdb.connect` accepts can be given there and wins over the settings.

The comment on the flag says that Django needs the number of rows an `"UPDATE"` could affect, not the number it changed. That number is what `QuerySet.update` returns, and on this backend, which cannot return rows from an update, it is how `Model._save_table` ordinarily learns whether the row it meant to update exists, and so whether to insert it instead (`django/db/models/sql/compiler.py:SQLUpdateCompiler.execute_returning_sql`, `django/db/models/base.py:Model._save_table`) ([Saving an instance](../models/saving.md)).

The isolation level is `"read committed"` unless `"OPTIONS"` names another. `get_connection_params` puts it in lower case and refuses with `ImproperlyConfigured` a level that is not one of `DatabaseWrapper.isolation_levels`, the four of SQL; `None` leaves the server's own. The level is kept on the connection for `DatabaseWrapper.init_connection_state`, so a bad one is refused when a connection opens, not when the settings are read.

> **Why.** The documentation says that Django works best with read committed rather than MySQL's default, repeatable read, under which data loss is possible: `get_or_create` may raise `IntegrityError` and the row still not appear to a `get` that follows (`docs/ref/databases.txt`).

`DatabaseWrapper.init_connection_state` runs once the driver's connection is open and its autocommit set (`django/db/backends/mysql/base.py:DatabaseWrapper.init_connection_state`). It calls the base class's, which checks the version once for each alias in the process, and then sends, joined in one call through Django's cursor, up to two statements: `"SET SQL_AUTO_IS_NULL = 0"` where the features say the server has that variable on, and `"SET SESSION TRANSACTION ISOLATION LEVEL"` with the level in capitals unless the level is `None`. The comment on the first says that the variable decides whether the `"AUTO_INCREMENT"` column of a row just inserted is found by a test for null, and that turning it off brings MySQL in line with the SQL standard. Whichever is made is sent at every opening, the variable read from the reply kept since the first; the server is not asked about itself again. A connection opened once, closed and opened again, on the same stand-in, which reports the variable on, with no server running and lines left out:

```text recording=backends
mysql_opened.close()
mysql_opened.cursor()
  BaseDatabaseWrapper.connect  (on "mysql")
    DatabaseWrapper.init_connection_state  (on "mysql")
      BaseDatabaseWrapper.init_connection_state  (on "mysql")
      SQL (on "mysql") SET SQL_AUTO_IS_NULL = 0; SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED
```

`DatabaseWrapper.is_usable` pings the server and answers false on any error of the driver ([Opening and closing a connection](lifecycle.md)). `DatabaseWrapper.create_cursor` ignores a name, and on this backend is given none: it keeps `BaseDatabaseWrapper.chunked_cursor`, which asks for an ordinary cursor, so `QuerySet.iterator` reads through one; MySQL does not stream results, the documentation says, so the driver loads the whole result into memory (`django/db/backends/base/base.py:BaseDatabaseWrapper.chunked_cursor`, `docs/ref/models/querysets.txt`).

## The cursor wrapper and `codes_for_integrityerror`

MySQL's `CursorWrapper` stands between Django's cursor and the driver's: `DatabaseWrapper.create_cursor` wraps the driver's cursor in it, and Django's own cursor wraps that (`django/db/backends/mysql/base.py:CursorWrapper`). Its docstring gives the reason for a wrapper and not a subclass: it is not bound to whatever class the driver's connection hands out. `CursorWrapper.execute` and `CursorWrapper.executemany` give the statement and its parameters to the driver unchanged, and `CursorWrapper.__getattr__` passes every other attribute through.

What the class adds is a translation. It catches `MySQLdb.OperationalError` and, where the error's code is in `CursorWrapper.codes_for_integrityerror`, raises Django's `IntegrityError` with the same arguments in its place, the comment saying these errors seem misclassified. By the comments beside them the codes are 1048, a column that cannot be null; 1690, a `"BIGINT UNSIGNED"` value out of range; and 3819 and 4025, a check constraint violated and failed. The exception is Django's already, so the `DatabaseErrorWrapper` around the call, which replaces only the driver's classes, lets it through as it is, without setting the connection's `errors_occurred` as it would for an `OperationalError`; after such an error, then, the end of the request does not ping the server (`django/db/utils.py:DatabaseErrorWrapper.__exit__`).

## `sql_mode`, strict mode and the checks

`DatabaseWrapper.sql_mode` is the server's `"@@sql_mode"` from the reply, split at its commas into a set (`django/db/backends/mysql/base.py:DatabaseWrapper.sql_mode`). Django reads the mode and never sets one: nothing in the backend sends it.

Strict mode is a check's concern. `DatabaseValidation._check_sql_mode`, which `DatabaseValidation.check` adds to the base class's checks, warns `"mysql.W002"` where the set holds neither `"STRICT_TRANS_TABLES"` nor `"STRICT_ALL_TABLES"`, its hint saying that strict mode turns warnings, such as data truncated on insertion, into errors (`django/db/backends/mysql/validation.py:DatabaseValidation._check_sql_mode`). The per-field half, `DatabaseValidation.check_field_type`, warns `"mysql.W003"` of a unique field whose column is a `"varchar"` longer than 255 or of no length, which its docstring says MySQL does not allow with a unique index, and `"fields.W162"` of an indexed field whose column type is one of `DatabaseWrapper._limited_data_types`, the text and blob types and `"json"`, which the comment on that tuple says the two databases cannot index at full width ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)).

The features read the mode too. `DatabaseFeatures.allows_auto_pk_0` is whether it holds `"NO_AUTO_VALUE_ON_ZERO"`; where it does not, `DatabaseOperations.validate_autopk_value` refuses `0` for an auto field with `ValueError`, the comment saying that a zero in an `"AUTO_INCREMENT"` column does not work without it (`django/db/backends/mysql/operations.py:DatabaseOperations.validate_autopk_value`). `DatabaseFeatures.allows_group_by_selected_pks` is true on MySQL, and on MariaDB only where the mode lacks `"ONLY_FULL_GROUP_BY"`; where it is true the compiler may group by a table's primary key and leave out the table's other columns (`django/db/backends/mysql/features.py:DatabaseFeatures.allows_group_by_selected_pks`) ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](../sql/grouping.md)).

## Foreign key checks switched off, and `check_constraints`

MySQL checks a foreign key as each statement runs: `DatabaseFeatures.supports_forward_references` is false, the flag whose comment asks whether foreign keys are checked at the end of a transaction or at each save (`django/db/backends/mysql/features.py:DatabaseFeatures`). Rows that refer to rows not yet written cannot then go in one at a time, so the backend switches the checks off (`django/db/backends/mysql/base.py:DatabaseWrapper.disable_constraint_checking`). `DatabaseWrapper.disable_constraint_checking` sends `"SET foreign_key_checks=0"` through Django's cursor and returns `True`, so that `BaseDatabaseWrapper.constraint_checks_disabled` switches them on again after; `DatabaseWrapper.enable_constraint_checking` sends `"SET foreign_key_checks=1"` with `BaseDatabaseWrapper.needs_rollback` cleared while it runs, which the comment says is for `constraint_checks_disabled` inside an atomic block, where Django's cursor would otherwise refuse the statement.

`DatabaseWrapper.check_constraints` finds what went in broken (`django/db/backends/mysql/base.py:DatabaseWrapper.check_constraints`) ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)). For each foreign key `DatabaseIntrospection.get_relations` reports, it selects with a `"LEFT JOIN"` the rows whose column refers to no row, and raises `IntegrityError` at the first, naming the row, its value and what it should refer to. `DatabaseOperations.sql_flush` puts the same switch around its `"TRUNCATE"` or `"DELETE FROM"` statements ([Introspection: reading the schema back](introspection.md)).

## The features

MySQL's `DatabaseFeatures` holds two kinds of answer (`django/db/backends/mysql/features.py:DatabaseFeatures`). Most of those that do not depend on the server are class attributes, and some of them change SQL that other classes write. `DatabaseFeatures.related_fields_match_type` is true, so a foreign key to a positive integer key takes that key's unsigned type ([Column types: from a field to a column](column-types.md)). `DatabaseFeatures.supports_order_by_nulls_modifier` is false and `DatabaseFeatures.order_by_nulls_first` true, so `OrderBy.as_sql` puts `"IS NULL"` or `"IS NOT NULL"` before a column to move its nulls, unless the database's own order already puts them where asked (`django/db/models/expressions.py:OrderBy.as_sql`).

The answers that depend on the server are cached properties, each worked out from the reply the first time it is read, and two properties that read one of them. The engine they ask about, `DatabaseFeatures._mysql_storage_engine`, is the server's default, not any one table's; the documentation notes that Django creates tables without naming an engine, so they get the default (`docs/ref/databases.txt`).

| feature | turns on | answer |
|---|---|---|
| `minimum_database_version` | which database | `(8, 4)` for MySQL, `(10, 11)` for MariaDB |
| `can_return_columns_from_insert`, `can_return_rows_from_bulk_insert` | which database | true on MariaDB only |
| `update_can_self_select`, `has_native_uuid_field` | which database | true on MariaDB only |
| `has_select_for_update_of`, `supports_any_value`, `supports_default_in_lead_lag` | which database | true on MySQL only |
| `supported_explain_formats` | which database | `"JSON"`, `"TEXT"` and `"TRADITIONAL"`, with `"TREE"` on MySQL |
| `supports_uuid4_function`, `supports_uuid7_function` | which database, and its version | true on MariaDB 11.7 and later only |
| `supports_expression_indexes` | which database, and the engine | true on MySQL unless the engine is MyISAM; false on MariaDB |
| `allows_group_by_selected_pks` | which database, and `sql_mode` | true on MySQL; on MariaDB, unless the mode holds `"ONLY_FULL_GROUP_BY"` |
| `allows_auto_pk_0` | `sql_mode` | true where the mode holds `"NO_AUTO_VALUE_ON_ZERO"` |
| `supports_transactions`, `can_introspect_foreign_keys` | the engine | true unless it is MyISAM |
| `supports_index_column_ordering` | the engine | true where it is InnoDB |
| `ignores_table_name_case`, `is_sql_auto_is_null_enabled` | a variable of the server | `"@@lower_case_table_names"` and `"@@sql_auto_is_null"`, as true or false |
| `has_zoneinfo_database` | the time zone tables | whether `"CONVERT_TZ"` gave a value |

*Chosen features of MySQL's `DatabaseFeatures` that ask the server, and what each turns on. `supports_transactions` replaces the base class's, which creates a table to find out (`django/db/backends/mysql/features.py:DatabaseFeatures.supports_transactions`); who reads each flag is in [What a database can do: `BaseDatabaseFeatures`](features.md).*

## The SQL it writes

MySQL's `DatabaseOperations` writes most of what makes a statement MySQL's (`django/db/backends/mysql/operations.py:DatabaseOperations`). `DatabaseOperations.quote_name` puts a name in backticks unless it stands in them already, and `DatabaseOperations.max_name_length` is 64. A slice with an offset and no end still needs a limit in `BaseDatabaseOperations.limit_offset_sql`, whose `BaseDatabaseOperations._get_limit_offset_params` asks `DatabaseOperations.no_limit_value` for one: 2⁶⁴ − 1, which the comment says the MySQL documentation recommends (`django/db/backends/base/operations.py:BaseDatabaseOperations._get_limit_offset_params`). Asked of the recording's MySQL connection:

```text recording=backends
mysql.ops.quote_name('fleet_ship')  ->  '`fleet_ship`'
mysql.ops.limit_offset_sql(5, 15)  ->  'LIMIT 10 OFFSET 5'
mysql.ops.limit_offset_sql(5, None)  ->  'LIMIT 18446744073709551615 OFFSET 5'
mysql.ops.no_limit_value()  ->  18446744073709551615
```

`DatabaseOperations.force_no_ordering` gives the compiler an ordering of `"NULL"` for a statement that has a `"GROUP BY"` and an empty ordering, so that it ends `"ORDER BY NULL"`; the docstring says this keeps MySQL from ordering by the grouped columns of its own accord (`django/db/backends/mysql/operations.py:DatabaseOperations.force_no_ordering`).

To ignore a conflict on insert, `DatabaseOperations.insert_statement` begins the statement `"INSERT IGNORE INTO"`; to update on one, `DatabaseOperations.on_conflict_suffix_sql` writes `"ON DUPLICATE KEY UPDATE"` and sets each field from the row that was to go in, on MySQL by naming that row `"AS new"`, since, the comment says, MySQL does not support `"VALUES()"` there, and on MariaDB with `"VALUE()"` of the column (`django/db/backends/mysql/operations.py:DatabaseOperations.on_conflict_suffix_sql`). The clause names no columns to match on: the features lack `BaseDatabaseFeatures.supports_update_conflicts_with_target`, and `QuerySet.bulk_create` refuses to be given unique fields with `NotSupportedError` (`django/db/models/query.py:QuerySet._check_bulk_create_options`) ([Inserts: returned keys, conflicts and batch sizes](inserts.md)).

The lookups that match text are in `DatabaseWrapper.operators`: the case-insensitive ones a plain `"LIKE"`, and `"contains"`, `"startswith"` and `"endswith"` a `"LIKE BINARY"` (`django/db/backends/mysql/base.py:DatabaseWrapper`). Whether a plain `"LIKE"`, or `"="`, ignores case is then the column's collation's to say, and the documentation notes that MySQL's default collation for UTF-8 ignores it (`docs/ref/databases.txt`). `DatabaseOperations.regex_lookup` writes `"REGEXP_LIKE"` with the match type `'c'` or `'i'` on MySQL, and on MariaDB, where the comment says that function does not exist, `"REGEXP BINARY"` or `"REGEXP"`. `DatabaseOperations.lookup_cast` wraps the column of a JSON field in `"JSON_UNQUOTE"`, for every lookup on MariaDB, and on MySQL for the case-insensitive match, the pattern lookups and the regular expressions (`django/db/backends/mysql/operations.py:DatabaseOperations.lookup_cast`).

Dates and times are written with MySQL's own functions, a datetime's truncation as `"DATE_FORMAT"` cast back, and a change of zone with `"CONVERT_TZ"` from the connection's time zone to the one asked for where `USE_TZ` is on and the two differ, which gives null on a server without its time zone tables (`django/db/backends/mysql/operations.py:DatabaseOperations._convert_sql_to_tz`) ([Values in and out: adapters, converters and time zones](values.md)). A truncation to the month, asked of the recording's MySQL connection:

```text recording=backends
mysql.ops.datetime_trunc_sql('month', '"crew_sailor"."signed_on"', (), 'Europe/Oslo')  ->  ('CAST(DATE_FORMAT(CONVERT_TZ("crew_sailor"."signed_on", %s, %s), %s) AS DATETIME)', ('UTC', 'Europe/Oslo', '%Y-%m-01 00:00:00'))
```

`DatabaseOperations.compiler_module` names a module of the backend's own, whose `SQLDeleteCompiler` deletes over joined tables as `"DELETE"` of the base table `"FROM"` the joins, and whose `SQLUpdateCompiler` adds the update's ordering where it is of the table's own columns (`django/db/backends/mysql/compiler.py`); both are told, with PostgreSQL's insert compiler, in [Inserts: returned keys, conflicts and batch sizes](inserts.md).

## The schema editor

MySQL's `DatabaseSchemaEditor` starts from templates of its own, among them MySQL's ways of dropping an index or a foreign key and renaming a table (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor`). A column's type and its null are changed with `"MODIFY"`, which restates its whole definition, so `DatabaseSchemaEditor._set_field_new_type` adds the old field's database default and its `"NULL"` or `"NOT NULL"` to the new type, to keep them (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor._set_field_new_type`). A check is dropped with `"DROP CHECK"` on MySQL and `"DROP CONSTRAINT IF EXISTS"` on MariaDB (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor.sql_delete_check`). The base class and its order of work, and MySQL's departures from it in altering a column, are told in [The schema editor: `BaseDatabaseSchemaEditor`](schema.md) and [Altering a column, and SQLite's table remake](alter-field.md).

A text or blob column takes a default its own way. On MySQL `DatabaseSchemaEditor._column_default_sql` writes the default of such a column, or of a JSON one, in parentheses, the comment saying MySQL takes it only as an expression, and `DatabaseSchemaEditor.skip_default_on_alter` is true, since it takes none in an `"ALTER COLUMN"`. So `BaseDatabaseSchemaEditor.add_field`, which drops a default once the column is added, leaves that one in place, and `BaseDatabaseSchemaEditor._iter_column_sql` writes it only where the column is not null (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._iter_column_sql`). On both databases `DatabaseSchemaEditor.skip_default` is true for a text or blob column whose default is empty, which is then made without one; where the field declares that default, `DatabaseSchemaEditor.add_field` follows with an `"UPDATE"` that sets it in every row (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor.add_field`).

On InnoDB the index of a foreign key with its constraint is the database's. `DatabaseSchemaEditor._field_should_be_indexed` asks `DatabaseIntrospection.get_storage_engine` for the table's engine and makes no index for a `ForeignKey` with its constraint on InnoDB, the comment saying the constraint brings one, nor for a column of a limited type (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor._field_should_be_indexed`, `django/db/backends/mysql/introspection.py:DatabaseIntrospection.get_storage_engine`). That index can go missing: the docstring of `DatabaseSchemaEditor._create_missing_fk_index` says MySQL may drop it when another index has the key's column first, and then the other index cannot be removed. So before `DatabaseSchemaEditor.remove_index`, `DatabaseSchemaEditor.remove_constraint` of a unique constraint, or `DatabaseSchemaEditor._delete_composed_index` drops an index that starts with a foreign key's column, the method reads the table's constraints and, where that is the only index to start so, creates the key's own index first (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor._create_missing_fk_index`).

## The client

MySQL's `DatabaseClient` runs `"mysql"` (`django/db/backends/mysql/client.py:DatabaseClient`). `DatabaseClient.settings_to_cmd_args_env` takes the database, user, password, host and port from `"OPTIONS"` before the settings; passes an option file in `"read_default_file"` as `--defaults-file`, a host with a slash as `--socket`, and the files of `"ssl"` and the `"charset"` as flags; and puts the password in the environment as `"MYSQL_PWD"`, which the comment prefers to `--password`, an argument exposed on more systems ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)). A set of settings, and the command line made of it with no client run:

```text recording=backends
shore  ->  {'NAME': 'harbour', 'USER': 'purser', 'PASSWORD': 'tide', 'HOST': 'db.harbour.example', 'PORT': '5432', 'OPTIONS': {}}
...
MySQLClient = load_backend('django.db.backends.mysql').DatabaseWrapper.client_class
full(MySQLClient.settings_to_cmd_args_env(shore, []))  ->  (['mysql', '--user=purser', '--host=db.harbour.example', '--port=5432', 'harbour'], {'MYSQL_PWD': 'tide'})
```
