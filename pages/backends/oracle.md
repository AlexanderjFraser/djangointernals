---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Oracle

`django.db.backends.oracle` is Django's backend for Oracle Database, reached through the driver `oracledb`; its cursor, `FormatStylePlaceholderCursor`, turns each statement's `"%s"` into Oracle's named placeholders, and the backend reads a null as the empty string, which Oracle stores as null (`interprets_empty_strings_as_nulls`).

Oracle departs from the plain case of the base classes in three kinds of way. The driver takes placeholders that are names after a colon, must be told when a string is a large object, and is told by the cursor what Python type each number comes back as. The SQL has `"FETCH FIRST"` for a limit, no savepoint released, before Oracle 23 `"FROM DUAL"` after a `"SELECT"` of no table, and identity columns for keys. And the data: Oracle does not tell the empty string from null, keeps a name given without quotes in capitals, and has no separate databases under one user. What every backend shares is in [Database backends](../backends.md).

## The driver and the process's environment

`django/db/backends/oracle/base.py` imports `oracledb` as `Database`, and raises `ImproperlyConfigured` where it is missing. Loading it has `_setup_environment` set two variables of the process's environment, once, for every connection after: `"NLS_LANG"` to `".AL32UTF8"`, since, the comment says, Oracle takes the client's character set from the environment, and `"ORA_NCHAR_LITERAL_REPLACE"` to `"TRUE"`, which, the next comment says, keeps Unicode from being mangled by a database character set that may not be Unicode (`django/db/backends/oracle/base.py:_setup_environment`).

> **Changed in 6.2.** The oldest `oracledb` supported rises from 2.3.0 to 4.0.2 (`docs/releases/6.2.txt`).

## Opening a connection

`BaseDatabaseWrapper.connect` takes the steps and Oracle's `DatabaseWrapper` supplies them ([Opening and closing a connection](lifecycle.md)). `DatabaseWrapper.get_connection_params` is every key of `"OPTIONS"` but `"use_returning_into"`, which Django reads itself, and `DatabaseWrapper.get_new_connection` passes them to `oracledb.connect` with the alias's `"USER"` and `"PASSWORD"` and the address `dsn` makes (`django/db/backends/oracle/base.py:DatabaseWrapper.get_new_connection`). Given a `"PORT"`, `dsn` has `oracledb.makedsn` write a descriptor of the host, `"localhost"` where `"HOST"` is empty, the port, and `"NAME"` as the database's SID; given none, it returns `"NAME"` as it stands (`django/db/backends/oracle/utils.py:dsn`). With `"pool"` set in `"OPTIONS"`, the connection comes from a pool that `oracledb.create_pool` makes, kept on the class, one for each alias and user (`django/db/backends/oracle/base.py:DatabaseWrapper.pool`).

`DatabaseWrapper.init_connection_state` runs the base class's check of the server's version against 19, then prepares the session, on cursors that Django's cursor does not wrap, so no execute wrapper and no query log sees these statements. The territory, `'AMERICA'`, is set alone and first, since, the comment says, the territory resets the formats of dates and timestamps to its own defaults; a second comment says `'AMERICA'` makes Sunday `'1'` in `"TO_CHAR"`, the numbering `DatabaseOperations.date_extract_sql` gives the day of the week. Then come the formats, `'YYYY-MM-DD HH24:MI:SS'` for a date and the same with fractions of a second for a timestamp, and under `USE_TZ` the session's time zone, `'UTC'`. Last, where the alias has autocommit off, it commits, so that, the comment says, the changes are kept (`django/db/backends/oracle/base.py:DatabaseWrapper.init_connection_state`).

### `_UninitializedOperatorsDescriptor`: the operators wait for the server

The first time an instance connects, `init_connection_state` also chooses `DatabaseWrapper.operators`, the SQL of each lookup's right-hand side: it tries the `"contains"` of `DatabaseWrapper._standard_operators`, a `"LIKE"` of the pattern translated into the national character set, on `"DUAL"`, and where the driver raises `oracledb.DatabaseError` takes `DatabaseWrapper._likec_operators`, which write `"LIKEC"` without the translation, and otherwise the standard ones. The comment, citing ticket 14149, says the test is made once for each instance in each thread, since later connections use the same settings. The choice is set on the instance, and until it is, `_UninitializedOperatorsDescriptor` stands in its place, held by the class under the name `operators`: read before the instance has connected, it opens a cursor and closes it, which connects, runs the test and leaves the connection open, and returns what the test set, sparing the code that reads it, the comment says, an `AttributeError`. It defines `__get__` alone, so the instance's own attribute hides it from then on (`django/db/backends/oracle/base.py:_UninitializedOperatorsDescriptor`).

## `FormatStylePlaceholderCursor`: Django's placeholders made Oracle's

`FormatStylePlaceholderCursor` is there because Django writes a parameter as `"%s"`, or `"%(name)s"` with a dictionary of parameters, and `oracledb` takes neither. It stands between Django's cursor and the driver's: `DatabaseWrapper.create_cursor` returns one, which holds the driver's cursor and the connection, rewrites each statement in `FormatStylePlaceholderCursor.execute` and `FormatStylePlaceholderCursor.executemany` before calling the driver inside `wrap_oracle_errors`, and passes any attribute it does not define to the driver's cursor (`django/db/backends/oracle/base.py:FormatStylePlaceholderCursor`) ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)).

`FormatStylePlaceholderCursor._fix_for_params` does the rewriting, and `execute` asks it to unify the parameters by value: each distinct pair of a value's type and the value gets one placeholder, `":arg0"` and on, in order of first appearance, which Python's `%` operator puts in place of each `"%s"`; and the parameters become a dictionary from placeholder to value. With no server, Oracle 23 assumed, `'England'`, given twice in an insert of two ports, would reach the driver once, as `":arg1"`:

```text figure=placeholders
what Oracle's compiler wrote for two ports:

    INSERT INTO "FLEET_PORT" ("NAME", "COUNTRY")
    SELECT * FROM (SELECT %s col_0, %s col_1 UNION ALL SELECT %s, %s)
    ('Hull', 'England', 'Whitby', 'England')

        |  FormatStylePlaceholderCursor._fix_for_params, unify_by_values=True, as execute calls it
        v

    INSERT INTO "FLEET_PORT" ("NAME", "COUNTRY")
    SELECT * FROM (SELECT :arg0 col_0, :arg1 col_1 UNION ALL SELECT :arg2, :arg1)
    {':arg0': an OracleParam, ':arg1': an OracleParam, ':arg2': an OracleParam}

        |  FormatStylePlaceholderCursor._param_generator
        v

what the driver's cursor would be handed with that statement:

    {':arg0': 'Hull', ':arg1': 'England', ':arg2': 'Whitby'}
```

*An insert of two ports on its way through `FormatStylePlaceholderCursor.execute`: each `"%s"` becomes a named placeholder, and the value given twice is bound once.*

The type is in the pair so that, the comment says, `0` and `1` are not unified with `False` and `True`. `executemany` numbers its placeholders by position instead, its one statement serving every row, and a dictionary keeps its keys, each `"%(name)s"` becoming `":name"`, as the block shows, each line of it a line of Python as it ran with its value after `->`, and a line of three dots standing for lines left out:

```text recording=backends
fixed, oracle_params = placeholders._fix_for_params(statement, values)  # as executemany calls it, for its first row of parameters
fixed  ->  'INSERT INTO "FLEET_PORT" ("NAME", "COUNTRY") SELECT * FROM (SELECT :arg0 col_0, :arg1 col_1 UNION ALL SELECT :arg2, :arg3)'
...
fixed, oracle_params = placeholders._fix_for_params('SELECT "ID" FROM "FLEET_PORT" WHERE "NAME" = %(name)s', {'name': 'Hull'})
fixed  ->  'SELECT "ID" FROM "FLEET_PORT" WHERE "NAME" = :name'
```

Parameters of `None` leave the statement unformatted; any others, an empty list too, format it, turning `"%%"` into `%`, which is why `DatabaseOperations.quote_name` doubles each `%` in a name. A last `";"` or `"/"` is cut off first: the comment says the driver wants no `";"` after SQL and no `"/"` after PL/SQL, and that a statement keeps them in case it is handed to SQL*Plus (`django/db/backends/oracle/base.py:FormatStylePlaceholderCursor._fix_for_params`).

### `OracleParam`: what each value is bound as

`_fix_for_params` ends by having `FormatStylePlaceholderCursor._format_params` wrap each parameter in an `OracleParam`, which settles the value to bind, held, despite its name, as `OracleParam.force_bytes`, which `FormatStylePlaceholderCursor._param_generator` hands the driver, and the driver's type to declare for it, if any, `OracleParam.input_size`, which `FormatStylePlaceholderCursor._guess_input_sizes` declares to the driver's cursor (`django/db/backends/oracle/base.py:OracleParam`). Under `USE_TZ` a `datetime` becomes an `Oracle_datetime`, since, the comment says, raw SQL can bring one that no field has prepared; `Oracle_datetime.from_datetime` copies its fields to the microsecond, dropping any time zone unconverted. Where `DatabaseFeatures.supports_boolean_expr_in_select_clause` is false, as before Oracle 23, a boolean is bound as `1` or `0`. A value with a `bind_parameter` method is bound as the driver's variable the method returns: a `BoundVar`, or a `VariableWrapper`, which `FormatStylePlaceholderCursor.var` puts around a variable of the driver's so that, its docstring says, it is not made a string. Text of more than 4000 bytes is declared `oracledb.DB_TYPE_CLOB`. Asked with no server, Oracle 23 assumed and Oracle 19 for the boolean:

```text recording=backends
len(long_text), len(long_text.encode())  ->  (2001, 4002)
full(OracleParam(long_text, placeholders, True).input_size)  ->  <DbType DB_TYPE_CLOB>
aware = datetime.datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))
OracleParam(aware, placeholders, True).force_bytes  ->  Oracle_datetime(2026, 3, 14, 18, 30)
...
OracleParam(True, placeholders19, True).force_bytes  ->  1
```

### `_output_type_handler`: numbers on their way out

The driver asks `FormatStylePlaceholderCursor._output_type_handler` about each column before fetching it, and for a `"NUMBER"` the handler has the value fetched as a string and converted by the column's precision and scale: an integer or a decimal never passes through a `float` (`django/db/backends/oracle/base.py:FormatStylePlaceholderCursor._output_type_handler`). A `"NUMBER(p, s)"`, an integer or a decimal field's, gives `int` for a scale of 0 and otherwise a `decimal.Decimal` quantized to the scale; a scale of -127 with a precision is a float field's `"FLOAT"`, and gives `float`; and a `"NUMBER"` declared without a precision, usually, the comment says, an integer from a sequence, and a number with no type at all, which it says normally comes from arithmetic in the select list, give a `decimal.Decimal` where the string has a point and an `int` where it has none. An `"NCLOB"` is fetched as one, since, the comment says, `oracledb` from 2.0 returns one with an `"IS JSON"` constraint as a dictionary. The operations object's converters finish the work ([Values in and out: adapters, converters and time zones](values.md)).

## Errors and the commit: `wrap_oracle_errors`

`wrap_oracle_errors` is for the constraints the server checks at the commit: Oracle's operations object makes each foreign key `" DEFERRABLE INITIALLY DEFERRED"` (`django/db/backends/oracle/operations.py:DatabaseOperations.deferrable_sql`). A violation found then is reported, the comment in `wrap_oracle_errors` records, as error 2091, the transaction rolled back, with the constraint's own error in its message, `"ORA-02291"` or `"ORA-00001"`. `wrap_oracle_errors`, around the driver's calls in `FormatStylePlaceholderCursor.execute` and `FormatStylePlaceholderCursor.executemany` and in `DatabaseWrapper._commit`, turns that case into Django's `IntegrityError` and raises any other unchanged (`django/db/backends/oracle/base.py:wrap_oracle_errors`). Django's cursor then translates the others with `BaseDatabaseWrapper.wrap_database_errors`; `_commit` has `wrap_oracle_errors` in its place, so any other error at the commit is the driver's own class. Oracle releases no savepoint, the comment says, so `DatabaseWrapper._savepoint_commit` sends nothing, and adds a faked `"RELEASE SAVEPOINT"` to a query log that is being kept, for the count to match other backends' ([Transactions: autocommit, `atomic` and savepoints](transactions.md)).

## The empty string stored as null

Oracle stores the empty string as null, and `DatabaseFeatures.interprets_empty_strings_as_nulls` says so; Oracle's is the one backend in the tree that sets it (`django/db/backends/oracle/features.py:DatabaseFeatures`). Django's convention runs the other way, a text field with no value holding `""`, so the backend makes null mean the empty string for every field that allows one: its column, unless it is the primary key, is nullable whatever the field's `null` says, and a null read back becomes `""`, `b""` for a `BinaryField`, so that a text field with `null=True` gives back `""` whether `None` or `""` was saved (`django/db/backends/oracle/operations.py:DatabaseOperations.get_db_converters`). Code above the backend asks the flag in these places, among others:

| where | what follows | whose flag |
|---|---|---|
| a column (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._iter_column_sql`) | made `"NULL"`; `BaseDatabaseSchemaEditor._alter_column_null_sql` leaves it so | the schema editor's |
| a foreign key (`django/db/models/fields/related.py:ForeignKey.get_db_prep_save`, `django/db/models/fields/related.py:ForeignKey.get_db_converters`) | `""` is saved as null, and read back as `None` | the query's |
| a filter, `"exact"` or `"iexact"` with `""` (`django/db/models/sql/query.py:Query.build_lookup`) | becomes `"isnull"` with `True` | `"default"`'s |
| a join (`django/db/models/sql/query.py:Query.is_nullable`) | the field counts as nullable | `"default"`'s |
| a reverse foreign key's manager (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`) | an instance whose key is `""` has no related objects | the manager's database |
| unique checks (`django/db/models/base.py:Model._perform_unique_checks`, `django/db/models/constraints.py:UniqueConstraint.validate`) | `""` is skipped as `None` is | `"default"`'s; the database `validate` is given |
| a field's default (`django/db/models/fields/__init__.py:Field._get_default`) | `""`, not `None`, for a nullable field that accepts `""` and has no default of its own | `"default"`'s |

*What follows from `interprets_empty_strings_as_nulls`, and whose features each place reads; `"default"`'s are read whatever database the query or the model is for.*

The filter and the join read `"default"` because, their comments say, the decision has to be made while the query is built, since join promotion cannot be done in the compiler, and the queryset does not know which connection it will use ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](../sql/names.md)). Where `"default"` is such a backend, the check that a primary key is not nullable is not made at all, since, its comment says, it cannot be made reliably where null and `""` are one (`django/db/models/fields/__init__.py:Field._check_null_allowed_for_primary_keys`).

## Names in capitals, within thirty characters

`DatabaseOperations.quote_name` puts a name in double quotes and in capitals. One not quoted already is first cut to `DatabaseOperations.max_name_length`, 30, by `truncate_name`; one given in quotes is not cut, and is put in capitals all the same. The comment's reason: a quoted name is case-sensitive, as SQL92 requires, Oracle keeps an unquoted one in capitals, and making every name capitals is simpler (`django/db/backends/oracle/operations.py:DatabaseOperations.quote_name`). A quoted name, with no server:

```text recording=backends
oracle.ops.quote_name('"name_left_in_lowercase"')  ->  '"NAME_LEFT_IN_LOWERCASE"'
```

`truncate_name` keeps the start of a name and ends it with four characters of a digest of the whole ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)), so `DatabaseFeatures.truncates_names` is true, and the model check of long column names passes over the backend (`django/db/backends/oracle/features.py:DatabaseFeatures.truncates_names`, `django/db/models/base.py:Model._check_long_column_names`). A model's default table name is cut by the `"default"` connection's limit as the class is made (`django/db/models/options.py:Options.contribute_to_class`), and names read back are put in lower case (`django/db/backends/oracle/introspection.py:DatabaseIntrospection.identifier_converter`).

## Inserts: `BulkInsertMapper`, `BoundVar` and the returned key

`DatabaseOperations.bulk_insert_sql` writes each row as a `"SELECT"`, joins them with `"UNION ALL"`, and wraps the whole in `"SELECT * FROM (...)"`. The comments give the reasons: the subquery because an identity column makes Oracle add its sequence's next value, which cannot stand in a `"UNION"`, and the aliases `"col_0"`, `"col_1"` on the first select to avoid `"ORA-00918"`, a column ambiguously defined, where two columns hold the same value (`django/db/backends/oracle/operations.py:DatabaseOperations.bulk_insert_sql`). Each placeholder is wrapped in the conversion `BulkInsertMapper.types` gives the internal type of the field, or of the field a foreign key points at; a type it does not list, a `"CharField"`'s, keeps `"%s"` (`django/db/backends/oracle/utils.py:BulkInsertMapper`).

`DatabaseFeatures.can_return_columns_from_insert` is true and `BaseDatabaseFeatures.can_return_rows_from_bulk_insert` is left false, so only the insert of one row asks for its key back, with `"RETURNING ... INTO %s"` and a `BoundVar` for each column as the parameter (`django/db/backends/oracle/operations.py:DatabaseOperations.returning_columns`). When `OracleParam` meets one, `BoundVar.bind_parameter` makes a variable on the driver's cursor, of the type `BoundVar.types` gives the field, `str` where it gives none; the server writes the new row's values into it, and `DatabaseOperations.fetch_returned_rows` reads them back with `BoundVar.get_value` (`django/db/backends/oracle/utils.py:BoundVar`). An update that returns columns does the same. A model with nothing to insert but its key gets `"NULL"` for it from `DatabaseOperations.pk_default_value`, where the base class writes `"DEFAULT"`; an `AutoField`'s column is `"NUMBER(11) GENERATED BY DEFAULT ON NULL AS IDENTITY"` (`django/db/backends/oracle/base.py:DatabaseWrapper.data_types`). Two voyages, and one row of a model with no field but its key, asking it back; no server ran:

```text recording=backends
full(inserts_for(oracle, due, ['ship', 'sailed']))  ->  [('INSERT INTO "FLEET_VOYAGE" ("SHIP_ID", "SAILED") SELECT * FROM (SELECT TO_NUMBER(%s) col_0, TO_DATE(%s) col_1 UNION ALL SELECT TO_NUMBER(%s), TO_DATE(%s))', (1, datetime.date(2026, 5, 1), 2, datetime.date(2026, 5, 9)))]
...
full(inserts_for(oracle, [Beacon()], [], returning=True))  ->  [('INSERT INTO "MOORINGS_BEACON" ("ID") VALUES (NULL) RETURNING "MOORINGS_BEACON"."ID" INTO %s', (<django.db.backends.oracle.utils.BoundVar object>,))]
```

`"use_returning_into"` set false in `"OPTIONS"` turns off `DatabaseFeatures.can_return_columns_from_insert` and `DatabaseFeatures.can_return_rows_from_update` (`django/db/backends/oracle/base.py:DatabaseWrapper.__init__`); `DatabaseOperations.last_insert_id` then reads the key as the current value of the sequence behind the column (`django/db/backends/oracle/operations.py:DatabaseOperations.last_insert_id`) ([Inserts: returned keys, conflicts and batch sizes](inserts.md)).

## The SQL it writes

In Oracle's operations object a time zone is written into the statement, never passed as a parameter, because, the comment says, Oracle crashes with `"ORA-03113"` when it is; the name is checked against a pattern first (`django/db/backends/oracle/operations.py:DatabaseOperations._tzname_re`, `django/db/backends/oracle/operations.py:DatabaseOperations._convert_sql_to_tz`). Asked with no server:

```text recording=backends
oracle.ops.datetime_trunc_sql('month', '"crew_sailor"."signed_on"', (), 'Europe/Oslo')  ->  ('TRUNC(CAST((FROM_TZ("crew_sailor"."signed_on", \'UTC\') AT TIME ZONE \'Europe/Oslo\') AS TIMESTAMP), %s)', ('MONTH',))
```

Before Oracle 23, `Avg` and `Sum` of a duration are taken over seconds, with `IntervalToSeconds` and `SecondsToInterval` of `django/db/backends/oracle/functions.py` (`django/db/models/functions/mixins.py:FixDurationInputMixin.as_oracle`). [The SQL a backend writes: `BaseDatabaseOperations`](operations.md) has the methods Oracle's operations object overrides, beside the other backends'.

## The features that depend on the version

Several flags of Oracle's `DatabaseFeatures` depend on the server's version, read through `DatabaseWrapper.oracle_version`, which opens a connection to ask where none is open, and closes it again (`django/db/backends/oracle/base.py:DatabaseWrapper.oracle_version`). From Oracle 21, `supports_json_negative_indexing`, `supports_primitives_in_json_field`, `supports_frame_exclusion` and `supports_bit_aggregations` are true; from 23, `supports_boolean_expr_in_select_clause`, `supports_comparing_boolean_expr` and `supports_aggregation_over_interval_types` too, and `bare_select_suffix` is empty, `" FROM DUAL"` before; then `supports_tuple_lookups` from 23.4, `supports_stored_generated_columns` from 23.7, `supports_uuid4_function` from 23.9 and `supports_uuid4_function_in_default` from 23.26.2 (`django/db/backends/oracle/features.py:DatabaseFeatures`). [What a database can do: `BaseDatabaseFeatures`](features.md) has every backend's flags side by side.

## The schema editor

Oracle's `DatabaseSchemaEditor` changes a column with `"MODIFY"` where the base class writes `"ALTER COLUMN"`, drops a table with `"CASCADE CONSTRAINTS"`, and calls a stored generated column `"MATERIALIZED"` (`django/db/backends/oracle/schema.py:DatabaseSchemaEditor`). Its features set `requires_literal_defaults`, so each default is written into the statement by `DatabaseSchemaEditor.quote_value`. A column of a large object, which the comment says Oracle cannot index, gets no index from `DatabaseSchemaEditor._field_should_be_indexed`, and `DatabaseValidation.check_field_type` warns of a field that asks for one (`django/db/backends/oracle/validation.py:DatabaseValidation.check_field_type`).

An identity column's identity is dropped before the column is removed, by `DatabaseSchemaEditor.remove_field`, and before an `AutoField` becomes another kind of field, by `DatabaseSchemaEditor._alter_column_type_sql`. `DatabaseSchemaEditor.alter_field` tries the base class's change and, where Oracle refuses it, reads the error and tries another way (`django/db/backends/oracle/schema.py:DatabaseSchemaEditor.alter_field`): for a type Oracle will not change to in place, `"ORA-22858"` or `"ORA-22859"`, `DatabaseSchemaEditor._alter_field_type_workaround` copies the values into a new column of the new type, which takes the old one's place, and a change refused for an identity column or a primary key, `"ORA-30675"`, `"ORA-30673"` or `"ORA-43923"`, has the identity or the key dropped first ([Altering a column, and SQLite's table remake](alter-field.md)).

## Test databases: a user and two tablespaces

Oracle has no separate databases under one user, the docstring of `DatabaseCreation._switch_to_test_user` says, so a test database is a user with a tablespace and a temporary tablespace of its own, and the alias's `"NAME"` stays as it was, which `DatabaseCreation._get_test_db_name` returns (`django/db/backends/oracle/creation.py:DatabaseCreation`). `DatabaseCreation._create_test_db` makes the tablespaces, then the user and its grants. It works through `DatabaseCreation._maindb_connection`, a second connection of the alias as the main user, the only one, its docstring says, that can manage the test databases ([Test databases: `BaseDatabaseCreation`](creation.md) has the order around it). The names and sizes come from keys of `"TEST"` that only Oracle reads (`django/db/backends/oracle/creation.py:DatabaseCreation._get_test_db_params`):

| `"TEST"` key | where it is missing |
|---|---|
| `"USER"` | `"test_"` and the alias's `"USER"` |
| `"PASSWORD"` | thirty random characters where the user is to be created, the limit, the comment says, of an Oracle password, which cannot hold symbols |
| `"TBLSPACE"`, `"TBLSPACE_TMP"` | `"test_"` and the alias's `"USER"`, the second with `"_temp"` |
| `"DATAFILE"`, `"DATAFILE_TMP"` | the tablespace's name and `".dbf"`, unless `"ORACLE_MANAGED_FILES"` leaves the files to Oracle |
| `"DATAFILE_SIZE"`, `"DATAFILE_EXTSIZE"`, `"DATAFILE_MAXSIZE"` | `"50M"`, `"25M"`, `"500M"`, and the same for `"DATAFILE_TMP_SIZE"`, `"DATAFILE_TMP_EXTSIZE"` and `"DATAFILE_TMP_MAXSIZE"` |
| `"CREATE_DB"`, `"CREATE_USER"` | true; false uses tablespaces or a user that exist, and keeps them |

*The keys of `"TEST"` that Oracle's creation reads, and what stands in for each one missing.*

With `"NAME"` `"harbour"`, `"USER"` `"purser"` and none of these keys, the parameters come out so, with no server; nothing reads `"dbname"`:

```text recording=backends
full({key: value for key, value in test_params.items() if key != 'password'})  ->  {'dbname': 'test_harbour', 'user': 'test_purser', 'tblspace': 'test_purser', 'tblspace_temp': 'test_purser_temp', 'datafile': 'test_purser.dbf', 'datafile_tmp': 'test_purser_temp.dbf', 'maxsize': '500M', 'maxsize_tmp': '500M', 'size': '50M', 'size_tmp': '50M', 'extsize': '25M', 'extsize_tmp': '25M'}
len(test_params['password'])  ->  30
```

A tablespace or a user that exists already, `"ORA-01543"` or `"ORA-01920"`, is used as it is under `keepdb=True`, and the user is given the new password where that was made at random; otherwise it is dropped and made again once `"yes"` is typed at the terminal, or at once under `autoclobber=True`, and any other error ends the process. Then `DatabaseCreation._switch_to_test_user` keeps the main user's credentials in the settings as `"SAVED_USER"` and `"SAVED_PASSWORD"` and puts the test user's in their place, so that every connection of the alias after it logs in as the test user; `DatabaseCreation._destroy_test_db` puts them back, unless the alias is pooled, and as the main user drops the test user and the tablespaces with their contents. `DatabaseCreation.set_as_test_mirror` copies a primary's `"USER"` and `"PASSWORD"`, where the base class copies `"NAME"`. The runner's half is in [The test framework](../testing.md).

## The client: SQL*Plus

`DatabaseClient.settings_to_cmd_args_env` builds dbshell's command line: `"sqlplus"`, `"-L"`, a connect string of the user, the password in double quotes and the `dsn` the connection uses, then the arguments given after it; where `"rlwrap"` is on the path it goes in front, and where the block below was recorded it was not (`django/db/backends/oracle/client.py:DatabaseClient`). Asked of one set of settings:

```text recording=backends
shore  ->  {'NAME': 'harbour', 'USER': 'purser', 'PASSWORD': 'tide', 'HOST': 'db.harbour.example', 'PORT': '5432', 'OPTIONS': {}}
...
OracleClient = load_backend('django.db.backends.oracle').DatabaseWrapper.client_class
full(OracleClient.settings_to_cmd_args_env(shore, []))  ->  (['sqlplus', '-L', 'purser/"tide"@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=db.harbour.example)(PORT=5432))(CONNECT_DATA=(SID=harbour)))'], None)
```

Its environment is `None`, so the password stands on the command line, where PostgreSQL's client passes it in `"PGPASSWORD"` and MySQL's in `"MYSQL_PWD"`. [The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md) has dbshell.
