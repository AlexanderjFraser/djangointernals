---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Column types: from a field to a column

The type of a field's column is named by the backend, in a dictionary on its connection, `BaseDatabaseWrapper.data_types`, from a field's internal type to a string with `%(name)s` holes or to a function, and `Field.db_type` fills it in from the field (`django/db/models/fields/__init__.py:Field.db_type`).

A model is written once, and its tables may be made on any of four databases that name their types differently: a boolean column is `"bool"` on SQLite and MySQL, `"boolean"` on PostgreSQL and `"NUMBER(1)"` on Oracle. The field knows what it holds and the backend knows the names, and Django keeps the names on the backend as data, in dictionaries keyed by a string the field gives. That string is the field's **internal type**, what `Field.get_internal_type` returns: the name of the field's class in the base class, and the name of a built-in class in a class that wants that class's column ([A field: the base class](../models/fields.md)). So a field class needs no backend's names, and a backend's dictionaries know nothing of a field class but its internal type. The schema editor is the main reader of what the field answers ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)).

## `data_types`: the dictionary on the connection class

`BaseDatabaseWrapper.data_types` is an empty dictionary, and SQLite's, PostgreSQL's and Oracle's `DatabaseWrapper` each give one of their own as a class attribute (`django/db/backends/sqlite3/base.py:DatabaseWrapper.data_types`); MySQL's is a property. A value is one of two things. Most are strings, with holes in the `%(name)s` form for the attributes the type needs: `"varchar(%(max_length)s)"`, or MySQL's `"numeric(%(max_digits)s, %(decimal_places)s)"`. A few are functions of one argument, the same attributes, which return the string. The functions are where a type changes its shape when an attribute is missing. `_get_varchar_column` writes `"varchar"` alone for a field with no length, and SQLite and PostgreSQL each define one (`django/db/backends/sqlite3/base.py:_get_varchar_column`, `django/db/backends/postgresql/base.py:_get_varchar_column`); `_get_decimal_column` writes PostgreSQL's `"numeric"` or Oracle's `"NUMBER"` alone for a field with neither digits nor places (`django/db/backends/postgresql/base.py:_get_decimal_column`, `django/db/backends/oracle/base.py:_get_decimal_column`). SQLite and PostgreSQL are the backends whose features have `BaseDatabaseFeatures.supports_unlimited_charfield`, and PostgreSQL, Oracle and SQLite those with `BaseDatabaseFeatures.supports_no_precision_decimalfield`; SQLite's decimal column, `"decimal"`, has no holes at all. Where a backend has only a string, a missing attribute is written in as `None`.

This line is a question and its answer after `->`, recorded from a running Django with the drivers of PostgreSQL, MySQL and Oracle installed and no server running, PostgreSQL 17, MySQL 8.4 and Oracle 23 assumed; columns, the recording's own helper, gives the field's `db_type` on each of the four connections in turn:

```text recording=backends
columns(models.CharField())  ->  sqlite 'varchar', postgresql 'varchar', mysql 'varchar(None)', oracle 'NVARCHAR2(None)'
```

A check refuses a `CharField` without a length where the default connection's features do not allow one, unless the model's options name the feature as required (`django/db/models/fields/__init__.py:CharField._check_max_length_attribute`); [The model checks](../models/checks.md) has the checks.

SQLite's dictionary names types that SQLite does not have. The comment above it says that SQLite does not actually support most of them but does the right thing given more verbose definitions, and that they are left as they are so that schema inspection is more useful. The names matter to SQLite's driver too: it converts a value by the type its column was declared with, and among the converters SQLite's backend registers are ones under `"bool"`, `"date"`, `"time"` and `"datetime"`, its own names for those columns ([Values in and out: adapters, converters and time zones](values.md)). On SQLite:

```text recording=backends
models.BooleanField().db_type(connection)  ->  'bool'
models.CharField(max_length=60).db_type(connection)  ->  'varchar(60)'
models.CharField().db_type(connection)  ->  'varchar'
models.DateField().db_type(connection)  ->  'date'
models.DateTimeField().db_type(connection)  ->  'datetime'
models.DecimalField(max_digits=8, decimal_places=2).db_type(connection)  ->  'decimal'
...
models.PositiveIntegerField().db_type(connection)  ->  'integer unsigned'
```

Because the key is the internal type and not the class, a class that answers with another's name gets that class's column (`django/db/models/fields/__init__.py:CharField.get_internal_type`, `django/db/models/fields/files.py:FileField.get_internal_type`). `EmailField` and `URLField` declare no internal type of their own and answer `"CharField"`, and `ImageField` answers `"FileField"`. `GeneratedField` answers with its output field's internal type and attributes, and so gets the output field's column (`django/db/models/fields/generated.py:GeneratedField.db_parameters`).

The dictionary has other readers. PostgreSQL's insert compiler sends rows as arrays only when the dictionary holds every field's internal type, or, for a relation, that of the field it points at ([Inserts: returned keys, conflicts and batch sizes](inserts.md)), and PostgreSQL's schema editor reads it when it alters a column. Introspection reads columns back the other way, through `BaseDatabaseIntrospection.data_types_reverse` ([Introspection: reading the schema back](introspection.md)).

## `db_type`, and what fills the holes

`Field.db_type` asks the field for its internal type and looks it up in the connection's `BaseDatabaseWrapper.data_types` (`django/db/models/fields/__init__.py:Field.db_type`). An internal type with no entry gives `None`. An entry that is callable is called with the field's parameters, and any other has them put in with `%`. The parameters are `Field.db_type_parameters`: a `DictWrapper` around the field's `__dict__`, which looks a key up as it is, except that a key beginning `"qn_"` has the prefix taken off and the value passed through the operations object's `BaseDatabaseOperations.quote_name` (`django/db/models/fields/__init__.py:Field.db_type_parameters`, `django/utils/datastructures.py:DictWrapper`). So `"%(max_length)s"` takes the field's `Field.max_length`, `"%(column)s"` its column's name as it is, and `"%(qn_column)s"` the name quoted for the backend, which Oracle's checks use.

The comment in `db_type` gives a field class two ways to its column: return from `Field.get_internal_type` the name of the built-in class it most resembles, and get that class's column on every backend; or, where no built-in class has the column it wants, override `db_type` and write the type out, as the fields of `django.contrib.postgres` do ([Content types, static files and the other contrib apps](../contrib.md)). A field whose type is `None` has no column: `BaseDatabaseSchemaEditor.column_sql` returns no definition for it. A `ManyToManyField`, whose `db_type` returns `None`, is not among a model's local fields, and `BaseDatabaseSchemaEditor.create_model` makes its table (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.column_sql`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.create_model`, `django/db/models/fields/related.py:ManyToManyField.db_type`).

## Beside the type: suffixes, checks and `db_parameters`

`BaseDatabaseWrapper.data_types_suffix` and `BaseDatabaseWrapper.data_type_check_constraints` are looked up by the internal type too. `Field.db_type_suffix` returns the entry of `data_types_suffix`, or `None`: words written after the rest of the column's definition (`django/db/models/fields/__init__.py:Field.db_type_suffix`). `Field.db_check` returns the entry of `data_type_check_constraints` filled from the same parameters, or `None`: the condition of a check on the column (`django/db/models/fields/__init__.py:Field.db_check`). Neither lookup calls a function, as `db_type`'s does.

| entry | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| suffix of the automatic keys | `"AUTOINCREMENT"` | `"GENERATED BY DEFAULT AS IDENTITY"` | none: it is in the type | none: it is in the type |
| check of the positive integers | `'"%(column)s" >= 0'` | `'"%(column)s" >= 0'` | ``'`%(column)s` >= 0'`` | `"%(qn_column)s >= 0"` |
| check of `"JSONField"` | `'(JSON_VALID("%(column)s") OR "%(column)s" IS NULL)'` | none | none | `"%(qn_column)s IS JSON"` |
| check of `"BooleanField"` | none | none | none | `"%(qn_column)s IN (0,1)"` |

*The suffixes and checks of the four backends, as their connection classes write them. The automatic keys are the entries `"AutoField"`, `"BigAutoField"` and `"SmallAutoField"`; the positive integers are `"PositiveIntegerField"`, `"PositiveBigIntegerField"` and `"PositiveSmallIntegerField"`. MySQL's automatic keys have `"AUTO_INCREMENT"` in the type, and Oracle's `"GENERATED BY DEFAULT ON NULL AS IDENTITY"`.*

`Field.db_parameters` gathers what the schema editor needs into one dictionary, the type under `"type"` and the check under `"check"` (`django/db/models/fields/__init__.py:Field.db_parameters`). A field class adds to it or replaces it. `CharField.db_parameters` and `TextField.db_parameters` add `"collation"`, the field's `db_collation` (`django/db/models/fields/__init__.py:CharField.db_parameters`); a `ForeignKey` gives its own type, no check, and the collation of the field it points at, and a `ManyToManyField` gives `None` for both (`django/db/models/fields/related.py:ForeignKey.db_parameters`, `django/db/models/fields/related.py:ManyToManyField.db_parameters`). Here the field is given a name, `"crates"`, so that a check has a column to name:

```text recording=backends
named(models.PositiveIntegerField(), 'crates').db_parameters(connection)  ->  {'type': 'integer unsigned', 'check': '"crates" >= 0'}
named(models.JSONField(), 'crates').db_parameters(connection)  ->  {'type': 'text', 'check': '(JSON_VALID("crates") OR "crates" IS NULL)'}
named(models.AutoField(primary_key=True), 'crates').db_parameters(connection)  ->  {'type': 'integer', 'check': None}
named(models.CharField(max_length=60, db_collation='nocase'), 'crates').db_parameters(connection)  ->  {'type': 'varchar(60)', 'check': None, 'collation': 'nocase'}
```

`BaseDatabaseSchemaEditor.column_sql` writes the type from `"type"` and puts the collation, a default, `"NOT NULL"` and the rest after it; the check and the suffix are added by the callers, `BaseDatabaseSchemaEditor.table_sql` for a new table and `BaseDatabaseSchemaEditor.add_field` for a new column (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.table_sql`). The recording's schema editor collects, without running it, the SQL for a model of the recording's own, Buoy, whose key is the default `BigAutoField`:

```text recording=backends
  class Buoy(models.Model):
      name = models.CharField(max_length=40)
      port = models.ForeignKey(Port, on_delete=models.CASCADE)
...
editor.create_model(Buoy)
  BaseDatabaseSchemaEditor.create_model(Buoy)
    BaseDatabaseSchemaEditor.table_sql(Buoy)
      BaseDatabaseSchemaEditor.column_sql(Buoy, Buoy.id)  ->  ('integer NOT NULL PRIMARY KEY', [])
      BaseDatabaseSchemaEditor.column_sql(Buoy, Buoy.name)  ->  ('varchar(40) NOT NULL', [])
      BaseDatabaseSchemaEditor.column_sql(Buoy, Buoy.port)  ->  ('bigint NOT NULL', [])
      -> ('CREATE TABLE "moorings_buoy" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(40) NOT NULL, "port_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED)', [])
```

The key's column, as `column_sql` returned it, ends at `"PRIMARY KEY"`, and `"AUTOINCREMENT"` is the suffix that `table_sql` put after it. The column of the foreign key, `"port_id"`, is `"bigint"`, the `rel_db_type` of the key of Port. How the schema editor builds the rest of the statement is [The schema editor: `BaseDatabaseSchemaEditor`](schema.md)'s.

## MySQL's two properties

MySQL's `DatabaseWrapper.data_types` and `DatabaseWrapper.data_type_check_constraints` are cached properties and not class attributes (`django/db/backends/mysql/base.py:DatabaseWrapper.data_types`). `data_types` copies the class's `DatabaseWrapper._data_types` and replaces the column of a `"UUIDField"`, `"char(32)"`, with `"uuid"` where the features' `BaseDatabaseFeatures.has_native_uuid_field` is true, which MySQL's features answer by whether the server is MariaDB. Only that column depends on the server, yet every column type a MySQL connection gives waits on `DatabaseWrapper.mysql_server_data`, what the connection has asked of its server, once for each connection ([MySQL and MariaDB](mysql.md)). `data_type_check_constraints` gives its checks only where the features have `BaseDatabaseFeatures.supports_column_check_constraints`, which MySQL's always do (`django/db/backends/mysql/base.py:DatabaseWrapper.data_type_check_constraints`).

## The column of a foreign key: `rel_db_type`

A column that points at another field takes its type from that field. `ForeignKey.db_type`, which `OneToOneField` inherits, returns the `rel_db_type` of the field it points at, and `Field.rel_db_type` returns the field's own `db_type` (`django/db/models/fields/related.py:ForeignKey.db_type`, `django/db/models/fields/__init__.py:Field.rel_db_type`). Two kinds of field answer otherwise.

The automatic keys answer with the type of the plain integer class of their size: `AutoField.rel_db_type` with `IntegerField`'s, and so on (`django/db/models/fields/__init__.py:AutoField.rel_db_type`). On MySQL an `AutoField`'s own type is `"integer AUTO_INCREMENT"` and a column pointing at it is `"integer"`. On SQLite a `BigAutoField`'s own type is `"integer"`, which loses nothing, since SQLite keeps every integer primary key as a signed 64-bit integer (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection.get_field_type`); a column pointing at it is `"bigint"`, as the Buoy's `"port_id"` is.

The positive integers answer through `PositiveIntegerRelDbTypeMixin.rel_db_type` with the type of the plain integer class they are built on, unless the features' `BaseDatabaseFeatures.related_fields_match_type` is true, and then with their own (`django/db/models/fields/__init__.py:PositiveIntegerRelDbTypeMixin.rel_db_type`). Its docstring gives the reason: a foreign key to a positive integer key has an integer column in most cases, but some databases, MySQL for one, have an unsigned integer type, and there the key should give its own type. MySQL's features set the flag, and no other backend's do (`django/db/backends/mysql/features.py:DatabaseFeatures`). For a `PositiveIntegerField` used as a key, on the four backends with no server running for the last three:

```text recording=backends
models.PositiveIntegerField(primary_key=True).rel_db_type(sqlite)  ->  'integer'
models.PositiveIntegerField(primary_key=True).rel_db_type(postgresql)  ->  'integer'
models.PositiveIntegerField(primary_key=True).rel_db_type(mysql)  ->  'integer UNSIGNED'
models.PositiveIntegerField(primary_key=True).rel_db_type(oracle)  ->  'NUMBER(11)'
```

## The type in a `Cast`: `cast_db_type`

`Field.cast_db_type` returns the type that `Cast` casts to: the operations object's `BaseDatabaseOperations.cast_data_types` entry for the internal type, filled from the field's parameters, where there is one, and `db_type` where there is not (`django/db/models/fields/__init__.py:Field.cast_db_type`, `django/db/models/functions/comparison.py:Cast.as_sql`). `CharField.cast_db_type` gives the operations object's `BaseDatabaseOperations.cast_char_field_without_max_length` for a field with no length, and `ForeignKey.cast_db_type` the cast type of the field it points at (`django/db/models/fields/__init__.py:CharField.cast_db_type`, `django/db/models/fields/related.py:ForeignKey.cast_db_type`). On SQLite, MySQL and Oracle an entry names another type than the column's: MySQL's casts an integer to `"signed integer"` or `"unsigned integer"`, and Oracle's a `"TextField"` to `"NVARCHAR2(2000)"`, its comment saying that Oracle does not support a string without a precision, so the largest size is used (`django/db/backends/oracle/operations.py:DatabaseOperations.cast_data_types`). SQLite's names `"TEXT"` for a date and a datetime, but its `Cast` does not ask for that entry where the field's column type is `"date"` or `"datetime"`: it writes the value with SQLite's date functions and no `"CAST"` (`django/db/models/functions/comparison.py:Cast.as_sqlite`). The operations object's attributes are [The SQL a backend writes: `BaseDatabaseOperations`](operations.md)'s. On SQLite:

```text recording=backends
models.CharField(max_length=60).cast_db_type(connection)  ->  'varchar(60)'
models.DateTimeField().cast_db_type(connection)  ->  'TEXT'
models.IntegerField().cast_db_type(connection)  ->  'integer'
```

## The column of each field class, on each backend

The four dictionaries side by side, each cell as the backend's `DatabaseWrapper` writes it (`django/db/backends/sqlite3/base.py:DatabaseWrapper.data_types`, `django/db/backends/postgresql/base.py:DatabaseWrapper.data_types`, `django/db/backends/mysql/base.py:DatabaseWrapper._data_types`, `django/db/backends/oracle/base.py:DatabaseWrapper.data_types`):

| internal type | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| `"AutoField"` | `"integer"` | `"integer"` | `"integer AUTO_INCREMENT"` | `"NUMBER(11) GENERATED BY DEFAULT ON NULL AS IDENTITY"` |
| `"BigAutoField"` | `"integer"` | `"bigint"` | `"bigint AUTO_INCREMENT"` | `"NUMBER(19) GENERATED BY DEFAULT ON NULL AS IDENTITY"` |
| `"SmallAutoField"` | `"integer"` | `"smallint"` | `"smallint AUTO_INCREMENT"` | `"NUMBER(5) GENERATED BY DEFAULT ON NULL AS IDENTITY"` |
| `"IntegerField"` | `"integer"` | `"integer"` | `"integer"` | `"NUMBER(11)"` |
| `"BigIntegerField"` | `"bigint"` | `"bigint"` | `"bigint"` | `"NUMBER(19)"` |
| `"SmallIntegerField"` | `"smallint"` | `"smallint"` | `"smallint"` | `"NUMBER(11)"` |
| `"PositiveIntegerField"` | `"integer unsigned"` | `"integer"` | `"integer UNSIGNED"` | `"NUMBER(11)"` |
| `"PositiveBigIntegerField"` | `"bigint unsigned"` | `"bigint"` | `"bigint UNSIGNED"` | `"NUMBER(19)"` |
| `"PositiveSmallIntegerField"` | `"smallint unsigned"` | `"smallint"` | `"smallint UNSIGNED"` | `"NUMBER(11)"` |
| `"FloatField"` | `"real"` | `"double precision"` | `"double precision"` | `"DOUBLE PRECISION"` |
| `"DecimalField"` | `"decimal"` | `"numeric"` | `"numeric"` | `"NUMBER"` |
| `"BooleanField"` | `"bool"` | `"boolean"` | `"bool"` | `"NUMBER(1)"` |
| `"CharField"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"NVARCHAR2(%(max_length)s)"` |
| `"SlugField"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"NVARCHAR2(%(max_length)s)"` |
| `"TextField"` | `"text"` | `"text"` | `"longtext"` | `"NCLOB"` |
| `"FileField"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"NVARCHAR2(%(max_length)s)"` |
| `"FilePathField"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"varchar(%(max_length)s)"` | `"NVARCHAR2(%(max_length)s)"` |
| `"DateField"` | `"date"` | `"date"` | `"date"` | `"DATE"` |
| `"DateTimeField"` | `"datetime"` | `"timestamp with time zone"` | `"datetime"` | `"TIMESTAMP"` |
| `"TimeField"` | `"time"` | `"time"` | `"time"` | `"TIMESTAMP"` |
| `"DurationField"` | `"bigint"` | `"interval"` | `"bigint"` | `"INTERVAL DAY(9) TO SECOND(6)"` |
| `"BinaryField"` | `"BLOB"` | `"bytea"` | `"longblob"` | `"BLOB"` |
| `"UUIDField"` | `"char(32)"` | `"uuid"` | `"char(32)"`, or `"uuid"` on MariaDB | `"VARCHAR2(32)"` |
| `"JSONField"` | `"text"` | `"jsonb"` | `"json"` | `"NCLOB"` |
| `"GenericIPAddressField"` | `"char(39)"` | `"inet"` | `"char(39)"` | `"VARCHAR2(39)"` |
| `"IPAddressField"` | `"char(15)"` | `"inet"` | `"char(15)"` | `"VARCHAR2(15)"` |

*The column type for each entry that the four backends' `data_types` share, the entry being the internal type, which for each of these field classes is its own name. SQLite's and PostgreSQL's `"CharField"`, and PostgreSQL's and Oracle's `"DecimalField"`, are functions: for a field without its length, or its digits and places, they write `"varchar"`, `"numeric"` and `"NUMBER"`, and for one with them `"CharField"` is as given here and `"DecimalField"` adds `"(%(max_digits)s, %(decimal_places)s)"` to the type shown, as MySQL's always does. MySQL's `"DateTimeField"` and `"TimeField"` add `"(6)"` to the type shown. An email or a URL field takes the row of `"CharField"`, an image field that of `"FileField"`, a foreign key the `rel_db_type` of the field it points at, and a many-to-many field has no column.*
