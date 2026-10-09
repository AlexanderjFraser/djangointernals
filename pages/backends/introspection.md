---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Introspection: reading the schema back

`BaseDatabaseIntrospection` is the class of a connection's **introspection**, the object that asks a database what its schema holds and answers in Django's terms: the tables and views, a table's columns, its foreign keys, primary key, constraints and indexes, and the sequences that number its new rows. Beside it stand the operations object's methods that empty tables and reset their sequences, `BaseDatabaseOperations.sql_flush`, `BaseDatabaseOperations.execute_sql_flush`, `BaseDatabaseOperations.sequence_reset_by_name_sql` and `BaseDatabaseOperations.sequence_reset_sql`.

Most of what Django does to a schema it does from the models alone. A few jobs need what the database actually holds, among them these. The schema editor, to drop a constraint or an index that a field or the model's `unique_together` implies, needs the name the database knows it by, and finds it among the table's constraints by their columns and kinds (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._constraint_names`). inspectdb writes models for tables Django did not make ([The commands Django ships](../commands/builtin.md)). migrate, given `--run-syncdb`, asks which tables exist, to make the tables of an application without migrations where they are missing (`django/core/management/commands/migrate.py:Command.sync_apps`), and, with `--fake-initial`, to see whether an initial migration's tables and columns are there already, so that it can be recorded as applied (`django/db/migrations/executor.py:MigrationExecutor.detect_soft_applied`) ([Migrations](../migrations.md)). And SQLite's and MySQL's versions of `BaseDatabaseWrapper.check_constraints`, looking for foreign keys that point nowhere, ask it for a table's primary key, MySQL's for the foreign keys too (`django/db/backends/sqlite3/base.py:DatabaseWrapper.check_constraints`, `django/db/backends/mysql/base.py:DatabaseWrapper.check_constraints`) ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)).

Each database keeps a catalog of its own schema and is asked in its own way: SQLite through its table `"sqlite_master"`, which holds the text of each `"CREATE TABLE"`, and through `"PRAGMA"` statements; PostgreSQL through `"pg_catalog"`; MySQL through `"information_schema"` and `"SHOW INDEX"`; Oracle through its dictionary views, `"user_tables"`, `"user_constraints"` and the rest. The base class fixes the shape of each answer, and each backend's `DatabaseIntrospection` asks the questions, SQLite's among them (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection`).

## The class and its questions

`BaseDatabaseIntrospection.__init__` keeps the connection, and `BaseDatabaseWrapper.__init__` makes one for each connection from the backend's `BaseDatabaseWrapper.introspection_class` (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.__init__`, `django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`). The methods that read the catalog raise `NotImplementedError` in the base class and are each backend's to write: `BaseDatabaseIntrospection.get_table_list`, `BaseDatabaseIntrospection.get_table_description`, `BaseDatabaseIntrospection.get_relations`, `BaseDatabaseIntrospection.get_constraints` and `BaseDatabaseIntrospection.get_sequences`. Most of the rest are the base class's, built on those and on the installed models; SQLite's and Oracle's override one of them, `BaseDatabaseIntrospection.get_primary_key_columns`, where their catalog answers more directly. A method that reads the catalog takes a cursor its caller opened, and inspectdb puts all its questions over one (`django/core/management/commands/inspectdb.py:Command.handle_inspection`); `BaseDatabaseIntrospection.table_names` opens its own when it is given none.

## Tables: `get_table_list` and `table_names`

`BaseDatabaseIntrospection.get_table_list` returns, in no particular order, a `TableInfo` for each table and view: a named tuple of the name and a type, `"t"` for a table and `"v"` for a view (`django/db/backends/base/introspection.py:TableInfo`). SQLite's reads `"sqlite_master"`, sorted by name, leaving out `"sqlite_sequence"`, a table SQLite keeps for itself; PostgreSQL's reads `"pg_class"` for what is visible on the search path, and calls a table that is a partition of another `"p"` and a materialized view `"v"` (`django/db/backends/postgresql/introspection.py:DatabaseIntrospection.get_table_list`).

`BaseDatabaseIntrospection.table_names` keeps the names of type `"t"`, or every name with `include_views=True`, so a partition is left out with the views; and it sorts them itself, in Python, whatever order they came in, since the database's `"ORDER BY"` sorts subtly differently from one database to another (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.table_names`).

In the quotes, from SQLite, a line at the margin is a line of Python with `->` and its value, and a line `SQL` under it is a statement it sent:

```text recording=backends
cursor = connection.cursor()
full(connection.introspection.table_names(cursor))  ->  ['crew_officer', 'crew_sailor', 'fleet_port', 'fleet_ship', 'fleet_voyage', 'fleet_voyage_calls', 'moorings_buoy', 'office_berth', 'office_licence', 'office_manifest']
  SQL SELECT name, type FROM sqlite_master WHERE type in ('table', 'view') AND NOT name='sqlite_sequence' ORDER BY name
```

`"moorings_buoy"` is the table of a model made in an application registry of its own, which no installed application holds.

## Columns: `get_table_description`

`BaseDatabaseIntrospection.get_table_description` returns a `FieldInfo` for each column of a table, in the table's order (`django/db/backends/base/introspection.py:FieldInfo`). The base `FieldInfo` holds what PEP 249's cursor description gives of a column, from its name and its type code to whether it may be null, with its default and its collation added. Each backend's module defines a `FieldInfo` with more, mostly for the backend's version of `BaseDatabaseIntrospection.get_field_type` to read: SQLite's adds whether the column is in the primary key and whether it has a JSON check (`django/db/backends/sqlite3/introspection.py:FieldInfo`); the others add such things as whether the column is an identity or auto-increment column, and the column's comment, which inspectdb reads.

PostgreSQL, MySQL and Oracle run a `"SELECT *"` of the table limited to a row and read the driver's cursor description, so their type code is the driver's: a type's identifier on PostgreSQL, a `MySQLdb` field type, an `oracledb` database type. Each completes the description from its catalog, and PostgreSQL's and MySQL's comments say why: the cursor's description does not reliably give nullability on PostgreSQL, and on MySQL gives a varchar's internal length and not its visible one, and no auto-increment (`django/db/backends/postgresql/introspection.py:DatabaseIntrospection.get_table_description`, `django/db/backends/mysql/introspection.py:DatabaseIntrospection.get_table_description`).

SQLite's backend asks `"PRAGMA table_xinfo"`, whose type is the text the column was declared with, though SQLite gives the names of its own types back in capitals, `"integer"` as `"INTEGER"` and `"text"` as `"TEXT"`. It reads the stored `"CREATE TABLE"` for the rest: each column's collation, and, where the features object has `BaseDatabaseFeatures.can_introspect_json_field`, whether a column has a check that calls `"json_valid"`, which SQLite's backend writes on a JSON field's text column (`django/db/backends/sqlite3/base.py:DatabaseWrapper.data_type_check_constraints`). It marks no column as in the key where the key has several (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection.get_table_description`). For the ships' table, its description a column to a line:

```text recording=backends
description = connection.introspection.get_table_description(cursor, 'fleet_ship')
  SQL PRAGMA table_xinfo("fleet_ship")
  SQL SELECT sql FROM sqlite_master WHERE type = 'table' AND name = %s with params ['fleet_ship']
  SQL SELECT sql FROM sqlite_master WHERE type = 'table' AND name = %s AND sql LIKE %s with params ['fleet_ship', '%json_valid("id")%']
...
  SQL SELECT sql FROM sqlite_master WHERE type = 'table' AND name = %s AND sql LIKE %s with params ['fleet_ship', '%json_valid("captain_id")%']
  FieldInfo(name='id', type_code='INTEGER', display_size=None, internal_size=None, precision=None, scale=None, null_ok=False, default=None, collation=None, pk=True, has_json_constraint=False)
  FieldInfo(name='name', type_code='varchar(60)', display_size=60, internal_size=None, precision=None, scale=None, null_ok=False, default=None, collation=None, pk=False, has_json_constraint=False)
  FieldInfo(name='tonnage', type_code='integer unsigned', display_size=None, internal_size=None, precision=None, scale=None, null_ok=False, default=None, collation=None, pk=False, has_json_constraint=False)
  FieldInfo(name='home_id', type_code='bigint', display_size=None, internal_size=None, precision=None, scale=None, null_ok=False, default=None, collation=None, pk=False, has_json_constraint=False)
  FieldInfo(name='captain_id', type_code='bigint', display_size=None, internal_size=None, precision=None, scale=None, null_ok=True, default=None, collation=None, pk=False, has_json_constraint=False)
```

## From a column to a field: `get_field_type` and `data_types_reverse`

`BaseDatabaseIntrospection.get_field_type` is given a column's type code and its whole description, and returns the name of a field class as a string. The base class looks the type code up in `BaseDatabaseIntrospection.data_types_reverse`, and its docstring says a backend may use the rest of the description, for Oracle's type alone cannot tell a float field from an integer field (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.get_field_type`). Each backend's mapping is keyed by its type code, and SQLite's is a `FlexibleFieldLookupDict`, which lowers the declared type's case and drops a size in parentheses before looking, its comment saying SQLite accepts any type name and does not normalize it (`django/db/backends/sqlite3/introspection.py:FlexibleFieldLookupDict`).

The backends' own `get_field_type` correct the plain answer. SQLite's makes an integer primary key `"AutoField"`, and never a big or small auto field, since SQLite treats every integer primary key as a signed 64-bit integer, and a column with a JSON check `"JSONField"` (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection.get_field_type`). PostgreSQL's and MySQL's make an identity or auto-increment column the auto field of its size, and MySQL's an unsigned integer the positive field of its size. Oracle's decides a `"NUMBER"` by its precision and scale: a scale of 0 is `"BooleanField"` at a precision of 1, and otherwise `"BigIntegerField"` above a precision of 11 and `"IntegerField"` up to it, or an auto field for an identity column; a scale of -127 is `"FloatField"` (`django/db/backends/oracle/introspection.py:DatabaseIntrospection.get_field_type`).

```text recording=backends
[connection.introspection.get_field_type(info.type_code, info) for info in description]  ->  ['AutoField', 'CharField', 'PositiveIntegerField', 'BigIntegerField', 'BigIntegerField']
```

The ships' key, a `BigAutoField` in the model, comes back `"AutoField"`, and the foreign keys come back `"BigIntegerField"`: a column's description says nothing of a relation, which inspectdb learns from `BaseDatabaseIntrospection.get_relations`. The mapping is a guess at a model and not the inverse of a field's column type ([Column types: from a field to a column](column-types.md)). A type it lacks raises `KeyError`, and inspectdb then writes `"TextField"` with a note that the type is a guess (`django/core/management/commands/inspectdb.py:Command.get_field_type`).

## Keys and relations: `get_relations` and `get_primary_key_columns`

`BaseDatabaseIntrospection.get_relations` returns, for each column of a table that is a foreign key, the column and the table it refers to and what the database itself does when the row it refers to is deleted (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.get_relations`). The last comes from `BaseDatabaseIntrospection.on_delete_types`, which maps the database's rule to `DB_CASCADE`, `DB_SET_NULL`, `DB_SET_DEFAULT`, or, for `"NO ACTION"`, `DO_NOTHING`; `"RESTRICT"` is not supported and maps to `None`. PostgreSQL's backend keys its own map by the letters of its catalog.

```text recording=backends
connection.introspection.get_relations(cursor, 'crew_sailor')  ->  {'ship_id': ('id', 'fleet_ship', the function DO_NOTHING)}
  SQL PRAGMA foreign_key_list("crew_sailor")
connection.introspection.get_primary_key_column(cursor, 'fleet_ship')  ->  'id'
  SQL PRAGMA table_info("fleet_ship")
connection.introspection.get_primary_key_columns(cursor, 'office_berth')  ->  ['port_id', 'number']
  SQL PRAGMA table_info("office_berth")
```

A sailor's ship has `on_delete=models.CASCADE`, which Django carries out itself by collecting the rows; the column was made with no rule of the database's, which SQLite reports as `"NO ACTION"`, read back as `DO_NOTHING`. The project's router keeps the office's logbooks and their entries on `"archive"`; an entry's book has `on_delete=models.DB_CASCADE`, which the database carries out, and reads back as such:

```text recording=backends
relations = connections['archive'].introspection.get_relations(archive_cursor, 'office_logentry')
  SQL (on "archive") PRAGMA foreign_key_list("office_logentry")
relations  ->  {'book_id': ('id', 'office_logbook', a DatabaseOnDelete)}
relations['book_id'][2] is models.DB_CASCADE  ->  True
```

> **Changed in 6.1.** Each value of `get_relations` holds the database's delete rule as its third member, and the release notes ask a third-party backend to return it (`docs/releases/6.1.txt`).

`BaseDatabaseIntrospection.get_primary_key_columns` returns the key's columns, or `None`, and the base class takes them from the constraint whose `"primary_key"` is true; `BaseDatabaseIntrospection.get_primary_key_column` is the first of them (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.get_primary_key_columns`). SQLite's and Oracle's backends read the key directly and return an empty list for a table without one, SQLite's from `"PRAGMA table_info"` in the order of the table's columns (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection.get_primary_key_columns`); a Berth's key is the pair of its port and its number.

## Constraints and indexes: `get_constraints`

`BaseDatabaseIntrospection.get_constraints` returns a dictionary from the name of each constraint and index of a table to a dictionary that describes it, whose keys its docstring fixes (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.get_constraints`):

| key | what it holds |
|---|---|
| `"columns"` | the columns, in order (SQLite's key: in the table's order) |
| `"primary_key"` | whether it is the primary key |
| `"unique"` | whether it is unique |
| `"foreign_key"` | the table and column it refers to, as a pair, or `None` |
| `"check"` | whether it is a check constraint |
| `"index"` | whether it is an index |
| `"orders"` | for an index, `"ASC"` or `"DESC"` for each column, where the backend reads an order (PostgreSQL's for a B-tree index only) |
| `"type"` | for an index, `"idx"` for a B-tree index such as `Index` makes, otherwise the database's name for its kind, which PostgreSQL's also gives a B-tree index with storage options or whose name ends `"_btree"`, as a `BTreeIndex`'s generated name does |

*What `get_constraints` says of each constraint and index. PostgreSQL's adds `"definition"`, the definition of an index on expressions, and `"options"`, the storage options.*

`"idx"` is the suffix of Django's `Index` (`django/db/models/indexes.py:Index.suffix`). The name is the database's where it has one, and the docstring warns that a backend may return names that exist nowhere. SQLite's backend calls the primary key `"__primary__"`, its comment saying no harm follows because it never drops a primary key by name and remakes the table instead; it numbers the foreign keys `"fk_0"` and on; and it numbers a unique or check constraint that has no name `"__unnamed_constraint_1__"` and on. MySQL's backend reports a check constraint named after its only column as unnamed in the same way, which its comment says is how MySQL names an unnamed one (`django/db/backends/mysql/introspection.py:DatabaseIntrospection.get_constraints`).

SQLite's backend reads three places (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection.get_constraints`). It parses the stored `"CREATE TABLE"` with sqlparse for the unique and check constraints written inside it, once `get_table_description` has given it the columns' names. It asks `"PRAGMA index_list"` for the indexes and passes over each one that has no `"CREATE INDEX"` text of its own: those SQLite made for a constraint in the table, which the comment says is found in the table's text already, under a name and with facts that may differ from the index's. And it asks the `"PRAGMA"` statements for the key and the foreign keys. For the ships' table, a constraint to a line:

```text recording=backends
constraints = connection.introspection.get_constraints(cursor, 'fleet_ship')
  SQL SELECT sql FROM sqlite_master WHERE type='table' and name=%s with params ['fleet_ship']
...
  SQL PRAGMA index_list("fleet_ship")
  SQL SELECT sql FROM sqlite_master WHERE type='index' AND name=%s with params ['fleet_ship_home_id_f9b8f2_idx']
  SQL PRAGMA index_info("fleet_ship_home_id_f9b8f2_idx")
  SQL SELECT sql FROM sqlite_master WHERE type='index' AND name=%s with params ['fleet_ship_home_id_12c4d51a']
  SQL PRAGMA index_info("fleet_ship_home_id_12c4d51a")
  SQL SELECT sql FROM sqlite_master WHERE type='index' AND name=%s with params ['sqlite_autoindex_fleet_ship_2']
  SQL SELECT sql FROM sqlite_master WHERE type='index' AND name=%s with params ['sqlite_autoindex_fleet_ship_1']
  SQL PRAGMA table_info("fleet_ship")
  SQL PRAGMA foreign_key_list("fleet_ship")
  __primary__: {'columns': ['id'], 'primary_key': True, 'unique': False, 'foreign_key': None, 'check': False, 'index': False}
  __unnamed_constraint_1__: {'check': True, 'columns': ['tonnage'], 'primary_key': False, 'unique': False, 'foreign_key': None, 'index': False}
  __unnamed_constraint_2__: {'unique': True, 'columns': ['captain_id'], 'primary_key': False, 'foreign_key': None, 'check': False, 'index': False}
  fk_0: {'columns': ['captain_id'], 'primary_key': False, 'unique': False, 'foreign_key': ('crew_sailor', 'id'), 'check': False, 'index': False}
  fk_1: {'columns': ['home_id'], 'primary_key': False, 'unique': False, 'foreign_key': ('fleet_port', 'id'), 'check': False, 'index': False}
  fleet_ship_home_id_12c4d51a: {'columns': ['home_id'], 'primary_key': False, 'unique': False, 'foreign_key': None, 'check': False, 'index': True, 'type': 'idx', 'orders': ['ASC']}
  fleet_ship_home_id_f9b8f2_idx: {'columns': ['home_id', 'tonnage'], 'primary_key': False, 'unique': False, 'foreign_key': None, 'check': False, 'index': True, 'type': 'idx', 'orders': ['ASC', 'ASC']}
  one_name_to_a_port: {'unique': True, 'columns': ['name', 'home_id'], 'primary_key': False, 'foreign_key': None, 'check': False, 'index': False}
  ship_has_tonnage: {'check': True, 'columns': ['tonnage'], 'primary_key': False, 'unique': False, 'foreign_key': None, 'index': False}
```

`"one_name_to_a_port"` and `"ship_has_tonnage"` are the model's `UniqueConstraint` and `CheckConstraint`, written into the table under their own names ([Constraints and indexes](../models/constraints.md)). The first unnamed constraint is the check that a `PositiveIntegerField`'s column carries, the second the `"UNIQUE"` that a one-to-one field writes into its column's definition. The two indexes are the foreign key's and the one of the model's `Meta`; SQLite's own indexes, `"sqlite_autoindex_fleet_ship_1"` and `"sqlite_autoindex_fleet_ship_2"`, have no text and were passed over.

The flags differ between backends for the same object. SQLite's `"__primary__"` is not unique, its comment saying the key is not actually a unique constraint, where PostgreSQL's, MySQL's and Oracle's count the primary key as unique; Oracle's marks the key and every unique constraint as an index too, all uniques coming with an index, as its comment has it (`django/db/backends/oracle/introspection.py:DatabaseIntrospection.get_constraints`), and MySQL's marks as an index whatever `"SHOW INDEX"` lists, the key and the unique constraints among them. The schema editor's `BaseDatabaseSchemaEditor._constraint_names` filters this dictionary by its columns and flags ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)).

## The models' tables: `django_table_names` and `sequence_list`

`BaseDatabaseIntrospection.get_migratable_models` yields each installed model that the router lets migrate on this connection's alias and that `Options.can_migrate` allows, which it does not for a proxy, a swapped or an unmanaged model, or one whose required vendor or features the connection lacks (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.get_migratable_models`, `django/db/models/options.py:Options.can_migrate`) ([Routing between databases: `ConnectionRouter`](routers.md)). `BaseDatabaseIntrospection.django_table_names` collects their tables, with those of their many-to-many relations where the model between is managed, and with `only_existing=True` keeps the ones the database has (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.django_table_names`).

```text recording=backends
full(sorted(connection.introspection.django_table_names(only_existing=True)))  ->  ['crew_officer', 'crew_sailor', 'fleet_port', 'fleet_ship', 'fleet_voyage', 'fleet_voyage_calls', 'office_berth', 'office_licence', 'office_manifest']
  SQL SELECT name, type FROM sqlite_master WHERE type in ('table', 'view') AND NOT name='sqlite_sequence' ORDER BY name
sorted(set(connection.introspection.table_names()) - set(connection.introspection.django_table_names()))  ->  ['moorings_buoy']
  SQL SELECT name, type FROM sqlite_master WHERE type in ('table', 'view') AND NOT name='sqlite_sequence' ORDER BY name
```

The logbooks are not in the answer: the project's router lets them migrate only on `"archive"`, so `get_migratable_models` does not yield them for `"default"`.

`BaseDatabaseIntrospection.sequence_list` asks `BaseDatabaseIntrospection.get_sequences` of each of those models' tables, and of the table of each many-to-many relation whose model between Django made, recording that table with no column where nothing was found (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.sequence_list`). A **sequence** is what numbers a table's new rows, and each backend finds a different thing: PostgreSQL's the sequences the table's columns own, MySQL's the table's auto-increment column, Oracle's the sequence of an identity column in the primary key, or an `AutoField`'s column with no sequence named (`django/db/backends/oracle/introspection.py:DatabaseIntrospection.get_sequences`). SQLite keeps a counter in `"sqlite_sequence"` for each table whose key is declared `"AUTOINCREMENT"`, as its backend declares an auto field's (`django/db/backends/sqlite3/base.py:DatabaseWrapper.data_types_suffix`). Its backend names the key's column whether the table has a counter or not, and, of a key of several columns, the one that stands first in the table: `"serial"` for the manifests and `"port_id"` for the berths (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection.get_sequences`):

```text recording=backends
full(connection.introspection.sequence_list())  ->  [{'table': 'fleet_port', 'column': 'id'}, {'table': 'fleet_ship', 'column': 'id'}, {'table': 'fleet_voyage', 'column': 'id'}, {'table': 'fleet_voyage_calls', 'column': 'id'}, {'table': 'crew_sailor', 'column': 'id'}, {'table': 'crew_officer', 'column': 'sailor_ptr_id'}, {'table': 'office_licence', 'column': 'id'}, {'table': 'office_manifest', 'column': 'serial'}, {'table': 'office_berth', 'column': 'port_id'}]
  SQL PRAGMA table_info("fleet_port")
...
  SQL PRAGMA table_info("office_berth")
```

## Names compared: `identifier_converter`

`BaseDatabaseIntrospection.identifier_converter` puts a name into the form in which names are compared; the base class returns it unchanged, for case-sensitive comparison (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection.identifier_converter`). Oracle's puts it into lower case, its docstring saying that identifier comparison is case-insensitive under Oracle (`django/db/backends/oracle/introspection.py:DatabaseIntrospection.identifier_converter`). Oracle's operations object quotes every name in capitals (`django/db/backends/oracle/operations.py:DatabaseOperations.quote_name`), so its catalog gives back `"FLEET_SHIP"` for the table Django calls `"fleet_ship"`. Oracle's introspection passes the names it reads through the converter, and the schema editor's `BaseDatabaseSchemaEditor._constraint_names`, among the code that compares a model's names with the database's, passes the model's through it too. `MigrationExecutor.detect_soft_applied` compares otherwise, folding both sides' case where the features object has `BaseDatabaseFeatures.ignores_table_name_case`, as SQLite's and Oracle's do, and MySQL's where the server's variable lower_case_table_names is set (`django/db/migrations/executor.py:MigrationExecutor.detect_soft_applied`, `django/db/backends/mysql/features.py:DatabaseFeatures.ignores_table_name_case`).

## Flushing: `sql_flush` and `execute_sql_flush`

To **flush** a database is to empty the models' tables, as introspection names them, without dropping them. `BaseDatabaseOperations.sql_flush` is given the tables and writes the statements, with `reset_sequences=True` adding the statements that reset their sequences and `allow_cascade=True` letting the emptying reach the tables whose foreign keys refer to them, which its docstring says PostgreSQL requires even where those tables are empty (`django/db/backends/base/operations.py:BaseDatabaseOperations.sql_flush`). The tables come from the function of the same name, which asks introspection for `django_table_names(only_existing=True, include_views=False)` (`django/core/management/sql.py:sql_flush`). The flush and sqlflush commands call that function ([The commands Django ships](../commands/builtin.md)), and `TransactionTestCase._fixture_teardown` runs flush after each test ([The test framework](../testing.md)).

| | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| each table | `"DELETE"` `"FROM"` | one `"TRUNCATE"` of them all | `"DELETE"` `"FROM"`, between `"SET FOREIGN_KEY_CHECKS = 0"` and `= 1` | `"TRUNCATE"` `"TABLE"`, the table's own foreign keys disabled before and enabled after |
| `reset_sequences=True` | `"UPDATE"` of `"sqlite_sequence"` | `"RESTART IDENTITY"` | `"TRUNCATE"` in place of `"DELETE"` `"FROM"` | a block for each sequence |
| `allow_cascade=True` | the tables that refer to them, found recursively, emptied too | `"CASCADE"` | ignored | the tables that refer to them, found recursively, truncated too, their referring foreign keys disabled in place of the tables' own |

*The statements of each backend's `sql_flush`.*

The comments give reasons. PostgreSQL's truncates every table in one statement, which lets it truncate a table that a foreign key in another refers to (`django/db/backends/postgresql/operations.py:DatabaseOperations.sql_flush`). MySQL's truncates only where the sequences are to be reset, `"TRUNCATE"` being faster than altering a table's counter, and otherwise deletes, which is faster still and keeps the counters (`django/db/backends/mysql/operations.py:DatabaseOperations.sql_flush`). Oracle's says its `"TRUNCATE CASCADE"` works only with foreign keys declared `"ON DELETE CASCADE"`, and the backend emulates PostgreSQL's by finding the foreign keys itself (`django/db/backends/oracle/operations.py:DatabaseOperations.sql_flush`). SQLite's finds the tables that refer to the flushed ones, where it may cascade, by a recursive query of `"sqlite_master"` (`django/db/backends/sqlite3/operations.py:DatabaseOperations.sql_flush`).

`BaseDatabaseOperations.execute_sql_flush` runs the statements on one cursor inside `atomic`, which, where the flush stands inside another atomic block, makes a savepoint only if the features object has `BaseDatabaseFeatures.can_rollback_ddl` (`django/db/backends/base/operations.py:BaseDatabaseOperations.execute_sql_flush`) ([Transactions: autocommit, `atomic` and savepoints](transactions.md)). Two of the project's tables flushed on SQLite, the calls nested as they were made:

```text recording=backends
connection.ops.execute_sql_flush(connection.ops.sql_flush(no_style(), ['office_licence', 'office_berth'], reset_sequences=True))
  BaseDatabaseOperations.execute_sql_flush
    Atomic.__enter__
      SQL BEGIN
    SQL DELETE FROM "office_licence";
    SQL DELETE FROM "office_berth";
    SQL UPDATE "sqlite_sequence" SET "seq" = 0 WHERE "name" IN ('office_licence', 'office_berth');
    Atomic.__exit__
      BaseDatabaseWrapper.commit
```

The `"BEGIN"` is SQLite's backend starting the transaction through Django's cursor, and the commit is a call of the driver's, not a statement (`django/db/backends/sqlite3/base.py:DatabaseWrapper._start_transaction_under_autocommit`).

## Sequences: `sequence_reset_by_name_sql` and `sequence_reset_sql`

`BaseDatabaseOperations.sequence_reset_by_name_sql` is given sequences as introspection describes them and writes the statements that reset each, on SQLite, PostgreSQL and MySQL back to its start; the base class writes none (`django/db/backends/base/operations.py:BaseDatabaseOperations.sequence_reset_by_name_sql`). SQLite's sets the counters in `"sqlite_sequence"` to 0, PostgreSQL's calls `"setval"`, and MySQL's sets `"AUTO_INCREMENT"` to 1. Oracle's writes a PL/SQL block that draws numbers from the table's sequence while the table's largest key is above it, which moves a sequence forward to its table and never back (`django/db/backends/oracle/operations.py:DatabaseOperations.sequence_reset_by_name_sql`). SQLite's and Oracle's versions of `BaseDatabaseOperations.sql_flush` add these statements where sequences are to be reset, and `TransactionTestCase._reset_sequences` runs them before each test of a class that sets `TransactionTestCase.reset_sequences`, where the features object has `BaseDatabaseFeatures.supports_sequence_reset`, which Oracle's does not (`django/test/testcases.py:TransactionTestCase._reset_sequences`).

`BaseDatabaseOperations.sequence_reset_sql` is given models and writes the statements that move each one's sequence to the largest key in its table, for after rows were written with their keys given (`django/db/backends/base/operations.py:BaseDatabaseOperations.sequence_reset_sql`). loaddata runs them after loading a fixture (`django/core/management/commands/loaddata.py:Command.reset_sequences`), sqlsequencereset prints them, and the sites application runs them after saving its default site with a key of its own choosing (`django/contrib/sites/management.py:create_default_site`). PostgreSQL's and Oracle's write them; SQLite's and MySQL's, which keep the base class's, write none.
