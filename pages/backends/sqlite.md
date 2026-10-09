---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# SQLite

SQLite's backend, `django.db.backends.sqlite3`, reaches a database that is a library inside the Python process, through the standard library's `sqlite3`: there is no server, the database keeps types its own way, and its SQL has few functions. Django fills the gaps from Python: it registers functions written in Python in every connection, rewrites its placeholders for the driver in `SQLiteCursorWrapper`, switches and checks foreign keys with PRAGMA statements, and reads the schema back with more of them and from the `"CREATE TABLE"` statements SQLite keeps.

Each of the other three backends talks to a server. SQLite's has none: `sqlite3.connect` opens a file, or a database in memory, and statements run in SQLite's C library inside the driver's calls. The database's version is that of the library the driver has loaded, which `DatabaseWrapper.get_database_version` reads without a statement, and `DatabaseWrapper.is_usable` answers `True` without one, so a health check never finds a SQLite connection unusable (`django/db/backends/sqlite3/base.py:DatabaseWrapper`).

SQLite's types are its own: dates and times are stored as text, as `DatabaseOperations.check_expression_support` says when it refuses `Sum` or `Avg` over them (`django/db/backends/sqlite3/operations.py:DatabaseOperations.check_expression_support`). Five of its departures are told with the mechanisms they bend: its columns in [Column types: from a field to a column](column-types.md), the adapters and converters in [Values in and out: adapters, converters and time zones](values.md), the `"BEGIN"` that opens an atomic block in [Transactions: autocommit, `atomic` and savepoints](transactions.md), how its schema is read back in [Introspection: reading the schema back](introspection.md), and the table built again to change a column in [Altering a column, and SQLite's table remake](alter-field.md).

## Opening a connection: `get_connection_params` and `get_new_connection`

`DatabaseWrapper.get_connection_params` makes the keyword arguments of `sqlite3.connect` from the alias's settings (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_connection_params`). It refuses an alias with no `"NAME"`, starts from the name and detect_types, set to `sqlite3.PARSE_DECLTYPES` and `sqlite3.PARSE_COLNAMES`, the first of which has the driver convert a value by its column's declared type ([Values in and out: adapters, converters and time zones](values.md)), and spreads `"OPTIONS"` over these, so that the driver's own options, such as `"timeout"`, reach it as written. Then it forces check_same_thread to `False`, warning where an option set it `True`, and uri to `True`. The comment gives the reason for the first: the driver forbids sharing a connection between threads unless told otherwise as it opens, and Django keeps that guard itself, in `BaseDatabaseWrapper.allow_thread_sharing` ([Opening and closing a connection](lifecycle.md)). The second lets `"NAME"` be a URI beginning `"file:"`, as an in-memory test database's is ([Test databases: `BaseDatabaseCreation`](creation.md)).

Two keys of `"OPTIONS"` are Django's and never reach the driver. `"transaction_mode"` must be `"DEFERRED"`, `"EXCLUSIVE"` or `"IMMEDIATE"`, in any case, or `None`, or `ImproperlyConfigured` is raised; it is kept in capitals as `DatabaseWrapper.transaction_mode`. `"init_command"` is split at each semicolon into `DatabaseWrapper.init_commands`, so no command can hold a semicolon of its own.

`DatabaseWrapper.get_new_connection` opens the driver's connection, has `register` put Django's functions into it, and sends on it directly, past Django's cursor, `"PRAGMA foreign_keys = ON"`, `"PRAGMA legacy_alter_table = OFF"` and each init command, its surrounding spaces stripped, that is not empty (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_new_connection`, `django/db/backends/sqlite3/_functions.py:register`). The comment over the second says the SQLite bundled with macOS turns legacy_alter_table on, which prevents atomic renames of tables. Below, a connection opens for an alias of its own whose options set both keys. A line at the left margin is Python as it was run, with `->` and its value; the lines under it are the calls it set going, and a line beginning sqlite is a statement as SQLite ran it:

```text recording=backends
Ship.objects.using('immediate').count()
  DatabaseWrapper.get_connection_params  (on "immediate")  ->  {'database': 'harbour.sqlite3', 'detect_types': 3, 'check_same_thread': False, 'uri': True}
  DatabaseWrapper.get_new_connection  (on "immediate")
    sqlite3.connect(database='harbour.sqlite3', detect_types=3, check_same_thread=False, uri=True)
    sqlite3.Connection.execute
      sqlite select sqlite_compileoption_used('ENABLE_MATH_FUNCTIONS')
    sqlite3.Connection.execute
      sqlite PRAGMA foreign_keys = ON
    sqlite3.Connection.execute
      sqlite PRAGMA legacy_alter_table = OFF
    sqlite3.Connection.execute
      sqlite PRAGMA synchronous = NORMAL
    sqlite3.Connection.execute
      sqlite PRAGMA cache_size = 2000
    -> the driver's connection
...
connections['immediate'].transaction_mode  ->  'IMMEDIATE'
connections['immediate'].init_commands  ->  ['PRAGMA synchronous = NORMAL', ' PRAGMA cache_size = 2000']
```

The first statement is `register`'s, asking whether the library was compiled with its mathematical functions; where it was not, `register` supplies `"ACOS"` to `"TAN"` in Python. The transaction mode is spent where an atomic block begins: SQLite's outermost block begins with a `"BEGIN"` sent through Django's cursor, for the reason [Transactions: autocommit, `atomic` and savepoints](transactions.md) gives, and `DatabaseWrapper._start_transaction_under_autocommit` puts the mode after it (`django/db/backends/sqlite3/base.py:DatabaseWrapper._start_transaction_under_autocommit`):

```text recording=backends
with transaction.atomic(using='immediate'): Ship.objects.using('immediate').count()
  Atomic.__enter__  (an Atomic made with using='immediate')
    DatabaseWrapper._start_transaction_under_autocommit  (on "immediate")
      SQL (on "immediate") BEGIN IMMEDIATE
      sqlite BEGIN IMMEDIATE
  SQL (on "immediate") SELECT COUNT(*) AS "__count" FROM "fleet_ship"
  sqlite SELECT COUNT(*) AS "__count" FROM "fleet_ship"
  Atomic.__exit__
    sqlite3.Connection.commit
      sqlite COMMIT
```

Without a mode the statement is a bare `"BEGIN"`, and Django's documentation names `"DEFERRED"` the default; it recommends `"IMMEDIATE"` so that a transaction waits for the driver's timeout before failing with "database is locked" (`docs/ref/databases.txt`).

## The functions Django registers in each connection

`register` gives SQLite functions written in Python under SQL names, through the driver's `sqlite3.Connection.create_function` and `sqlite3.Connection.create_aggregate` (`django/db/backends/sqlite3/_functions.py:register`). The functions Django names itself carry dates, times and durations, which SQLite stores as text and as whole microseconds. The operations object writes each such operation as a call to one of them, with the column or expression among its arguments: `DatabaseOperations.datetime_extract_sql`, for one, writes `"django_datetime_extract"`, which `_sqlite_datetime_extract` answers (`django/db/backends/sqlite3/operations.py:DatabaseOperations`).

For a datetime the operations object passes the part's name where there is one, the value, and two time zones: the one the expression asks for, the current time zone unless it was given its own, and the connection's `BaseDatabaseWrapper.timezone_name`, the zone the value was stored in, `"UTC"` unless the alias sets `"TIME_ZONE"`. Both are `None` where `USE_TZ` is off or no zone is asked for (`django/db/backends/sqlite3/operations.py:DatabaseOperations._convert_tznames_to_sql`). `_sqlite_datetime_parse` reads the stored text, gives it the connection's zone and converts it into the other (`django/db/backends/sqlite3/_functions.py:_sqlite_datetime_parse`). `"django_date_extract"` is the same Python as `"django_datetime_extract"`, registered to take two arguments, so that a date's zones stay `None`.

Others fill gaps under the names Django's expressions write. `"regexp"` is `_sqlite_regexp`, Python's `re.search`: SQLite's operator `"REGEXP"` calls a function of that name, which `DatabaseWrapper.operators` writes for the `"regex"` lookup and, with Python's flag `"(?i)"` before the pattern, for `"iregex"`, so a regular expression on SQLite is Python's (`django/db/backends/sqlite3/base.py:DatabaseWrapper.operators`, `docs/ref/models/querysets.txt`). `"RAND"` replaces `"RANDOM"`, which, the comment in `register` says, returns a 64-bit integer and not a number from nought up to one (`django/db/models/functions/math.py:Random.as_sqlite`).

The aggregates that `StdDev`, `Variance`, `AnyValue`, `BitAnd`, `BitOr` and `BitXor` write, `"STDDEV_POP"`, `"VAR_SAMP"` and their fellows, `"ANY_VALUE"`, `"BIT_AND"`, `"BIT_OR"` and `"BIT_XOR"`, are subclasses of `ListAggregate`, a `list` whose `ListAggregate.step` is `list.append`, called from C for each row of a group. Their `finalize`, called once at the group's end, computes the answer from the whole list: with `statistics.pstdev` and its fellows, by taking the first value, or by folding a bitwise operator over the values that are not null (`django/db/models/aggregates.py`, `django/db/backends/sqlite3/_functions.py:ListAggregate`):

```text recording=backends
spread = Ship.objects.aggregate(spread=models.StdDev('tonnage'))
  SQL SELECT STDDEV_POP("fleet_ship"."tonnage") AS "spread" FROM "fleet_ship"
  sqlite3.Cursor.execute
    StdDevPop.finalize([480, 650, 1200])  (statistics.pstdev, called by SQLite)  ->  307.281991373107
```

## A statement that calls back into Python

A registered function runs where SQLite needs its value: in the `"WHERE"` below, its only condition, once for every row the statement read. The sailors who signed on in March, on `"default"`, where the project's time zone is Oslo's and the connection's UTC:

```text recording=backends
march = list(Sailor.objects.filter(signed_on__month=3))
  sqlite3.Cursor.execute
    sqlite SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE django_datetime_extract('month', "crew_sailor"."signed_on", 'Europe/Oslo', 'UTC') = 3
    _sqlite_datetime_extract(lookup_type='month', dt='2011-06-01 08:00:00', tzname='Europe/Oslo', conn_tzname='UTC')
      -> 6
    _sqlite_datetime_extract(lookup_type='month', dt='2026-03-14 17:30:00', tzname='Europe/Oslo', conn_tzname='UTC')
      -> 3
  sqlite3.Cursor.fetchmany
    _sqlite_datetime_extract(lookup_type='month', dt='2011-06-01 08:00:00', tzname='Europe/Oslo', conn_tzname='UTC')
      -> 6
    _sqlite_datetime_extract(lookup_type='month', dt='2026-04-10 09:00:00', tzname='Europe/Oslo', conn_tzname='UTC')
      -> 4
    _sqlite_datetime_extract(lookup_type='month', dt='2026-04-10 09:00:00', tzname='Europe/Oslo', conn_tzname='UTC')
      -> 4
  sqlite3.Cursor.fetchmany
march  ->  [<Sailor: Bram>]
```

The driver's execute did more than prepare the statement: it ran it as far as its first row, and SQLite called `_sqlite_datetime_extract` through the driver for each row it read on the way: two rows, the second a match. The fetch read the other three, with a call for each. Each call parsed its text again, a value two rows hold included, so every row of the table passed through Python to find one. The month is taken after the conversion to Oslo's time, for the reason the comment of `TimezoneMixin.get_tzname` gives: a conversion must happen before a function is applied (`django/db/models/functions/datetime.py:TimezoneMixin.get_tzname`).

```text figure=a-function-for-each-row
Django, in Python             the driver, sqlite3 (C)          SQLite, the library (C)

the statement  ------------>  sqlite3.Cursor.execute  ------>  runs WHERE django_datetime_extract(...) = 3
                                                               reads a row: '2011-06-01 08:00:00'
_sqlite_datetime_extract  <--  calls back  <------------------
   -> 6  ---------------------------------------------------->  6 = 3? no
                                                               reads a row: '2026-03-14 17:30:00'
_sqlite_datetime_extract  <--  calls back  <------------------
   -> 3  ---------------------------------------------------->  3 = 3? yes: the first row
                         <---  execute returns

fetch the rows  ----------->  sqlite3.Cursor.fetchmany  ---->  reads the three rows left
_sqlite_datetime_extract  <--  calls back, once for each  <---
   -> 6, 4, 4  ---------------------------------------------->  none is 3
                         <---  the one row that matched: Bram
```

*The sailors who signed on in March, on SQLite: the library calls back into Python for each row it reads, twice inside the driver's execute and three times inside the fetch.*

## `SQLiteCursorWrapper`: Django's placeholders made SQLite's

Django's statements mark a parameter with `"%s"`, or with `"%(name)s"` where the parameters are a dictionary, and `sqlite3` takes neither style (`django/db/backends/sqlite3/base.py:SQLiteCursorWrapper`). `DatabaseWrapper.create_cursor` asks the driver's connection for a cursor of the class `SQLiteCursorWrapper`, a subclass of `sqlite3.Cursor`, so the conversion runs beneath Django's `CursorWrapper`, after the execute wrappers have seen the statement in Django's form (`django/db/backends/utils.py:CursorWrapper`) ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)). `SQLiteCursorWrapper.execute` leaves a statement given no parameters as it is. Given any, an empty list among them, `SQLiteCursorWrapper.convert_query` turns every `"%s"` not preceded by `"%"` into `"?"` and then every `"%%"` into `"%"`; for a mapping it formats the statement with Python's `%`, so that each `"%(name)s"` becomes `":name"`. `SQLiteCursorWrapper.executemany` decides which by the first set of parameters, read through `itertools.tee` since the sets may come from a generator.

A literal `"%s"`, written `"%%s"`, sent with a parameter and with none:

```text recording=backends
with connection.cursor() as cursor: cursor.execute("SELECT '%%s', %s", ['x']); rows = cursor.fetchall()
  SQLiteCursorWrapper.execute
    SQLiteCursorWrapper.convert_query  ->  "SELECT '%s', ?"
    sqlite3.Cursor.execute
      sqlite SELECT '%s', 'x'
rows  ->  [('%s', 'x')]
with connection.cursor() as cursor: cursor.execute("SELECT '%%s'"); rows = cursor.fetchall()
  SQLiteCursorWrapper.execute
    sqlite3.Cursor.execute
      sqlite SELECT '%%s'
rows  ->  [('%%s',)]
```

> **Trap.** Given no parameters, nothing is converted, and `"%%"` reaches SQLite as two signs.

## `last_executed_query`: the values quoted by SQLite

`DatabaseOperations.last_executed_query` gives the query log each statement with its values in it ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)). The driver binds the values in C, out of Python's reach, as its comment says (`django/db/backends/sqlite3/operations.py:DatabaseOperations.last_executed_query`), so the backend has SQLite write them: `DatabaseOperations._quote_params_for_last_executed_query` runs `"SELECT QUOTE(?), ..."`, in batches within SQLite's limits of parameters and of columns, on a cursor of the driver's connection and not Django's, which, the comment says, would log the statement in turn and recurse without end (`django/db/backends/sqlite3/operations.py:DatabaseOperations._quote_params_for_last_executed_query`).

```text recording=backends
DatabaseOperations.last_executed_query
  DatabaseOperations._quote_params_for_last_executed_query([500])
    DatabaseFeatures.max_query_params
    sqlite3.Connection.cursor
    sqlite3.Cursor.execute
      sqlite SELECT QUOTE(500)
    sqlite3.Cursor.fetchone
    -> ('500',)
  -> 'SELECT name FROM fleet_ship WHERE tonnage > 500'
```

## `close` and the in-memory database

Django takes a `"NAME"` of `":memory:"`, or any name with `"mode=memory"` in it, for a database that SQLite keeps in memory: `DatabaseWrapper.is_in_memory_db` asks `DatabaseCreation.is_in_memory_db`, which never says so of a `pathlib.Path` (`django/db/backends/sqlite3/creation.py:DatabaseCreation.is_in_memory_db`). Closing the connection would destroy such a database, says the comment of `DatabaseWrapper.close`, which ignores the request to prevent the accidental loss of data: after checking the thread, it does nothing (`django/db/backends/sqlite3/base.py:DatabaseWrapper.close`). On an alias of its own, named `"memory"`, whose `"NAME"` is `":memory:"`:

```text recording=backends
memory = connections['memory']
memory.cursor().execute('CREATE TABLE tide (height real)')
memory.close()
  DatabaseWrapper.close  (on "memory")
    DatabaseWrapper.is_in_memory_db  (on "memory")
memory.connection is None  ->  False
memory.introspection.table_names()  ->  ['tide']
BaseDatabaseWrapper.close(memory)  # the base class's close, which SQLite's skips for an in-memory database
memory.connection is None  ->  True
```

Django closes a driver's connection only through `close`, so nothing closes this one, not even `close_old_connections` at a request's end, whatever `"CONN_MAX_AGE"` says; the base class's method, called directly as the last lines do, closes it and the database with it. SQLite's test database is in memory where `"TEST"` names none ([Test databases: `BaseDatabaseCreation`](creation.md)).

## Foreign keys, switched and checked by PRAGMA

SQLite's schema editor writes every foreign key inside its column's definition, with `"DEFERRABLE INITIALLY DEFERRED"` at its end ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)), so a key is checked when its transaction commits, and the features declare `DatabaseFeatures.can_defer_constraint_checks` (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.sql_create_inline_fk`, `django/db/backends/sqlite3/features.py:DatabaseFeatures`).

The wrapper's three methods for the checks, which do nothing in the base class ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)), are PRAGMA statements here. `DatabaseWrapper.disable_constraint_checking` sends `"PRAGMA foreign_keys = OFF"` and returns whether the checks are off, its comment saying they cannot be turned off inside a transaction of several statements. `DatabaseWrapper.enable_constraint_checking` turns them on. `DatabaseWrapper.check_constraints` runs `"PRAGMA foreign_key_check"` and raises `IntegrityError` at the first violation (`django/db/backends/sqlite3/base.py:DatabaseWrapper.check_constraints`). Inside a transaction SQLite takes a row whose key has nothing behind it, and the check finds it:

```text recording=backends
with transaction.atomic(): Sailor.objects.create(name='Gale', ship_id=99); connection.check_constraints()
  DatabaseWrapper.check_constraints
    SQL PRAGMA foreign_key_check
...
raises IntegrityError: The row in table 'crew_sailor' with primary key '6' has an invalid foreign key: crew_sailor.ship_id contains a value '99' that does not have a corresponding value in fleet_ship.id.
```

`DatabaseSchemaEditor.__enter__` turns the checks off before the base class opens its atomic block, the comment saying some of SQLite's alterations need them off, and raises `NotSupportedError` where they stay on, so inside a transaction the editor can be entered only if the checks were turned off before the transaction began; `DatabaseSchemaEditor.__exit__` checks every table, lets the base class finish, and turns them on (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__enter__`, `django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__exit__`).

The command loaddata and `BaseDatabaseCreation.deserialize_db_from_string` load rows inside `atomic` and then inside `BaseDatabaseWrapper.constraint_checks_disabled`, and call `check_constraints` afterwards (`django/core/management/commands/loaddata.py:Command.handle`, `django/core/management/commands/loaddata.py:Command.loaddata`, `django/db/backends/base/creation.py:BaseDatabaseCreation.deserialize_db_from_string`) ([Test databases: `BaseDatabaseCreation`](creation.md)). On SQLite, inside the transaction, `constraint_checks_disabled` disables nothing, and so turns nothing back on:

```text recording=backends
with transaction.atomic(), connection.constraint_checks_disabled(): Ship.objects.count()
  BaseDatabaseWrapper.constraint_checks_disabled
    DatabaseWrapper.disable_constraint_checking
      SQL PRAGMA foreign_keys = OFF
      SQL PRAGMA foreign_keys
      -> False
...
  BaseDatabaseWrapper.constraint_checks_disabled resumes
connection.cursor().execute('PRAGMA foreign_keys').fetchone()  ->  (1,)
```

On SQLite a `TestCase`, whose transactions never commit, calls `check_constraints` as each test ends, unless the connection is marked for rollback (`django/test/testcases.py:TestCase._fixture_teardown`).

## The library's version and limits: the features

The version is the library's and is known when the module is imported, so a flag that depends on it is a class attribute: `DatabaseFeatures.supports_aggregate_order_by_clause` is true from SQLite 3.44.0 (`django/db/backends/sqlite3/features.py:DatabaseFeatures`). Below 3.39 the operations object writes `"GROUP BY TRUE"` before a `"HAVING"` that has no grouping (`django/db/backends/sqlite3/operations.py:DatabaseOperations.force_group_by`), and `DatabaseFeatures.minimum_database_version`, 3.37, is the oldest the version check lets open.

> **Changed in 6.1.** The oldest SQLite Django supports is 3.37.0. It was 3.31.0 (`docs/releases/6.1.txt`).

`DatabaseFeatures.max_query_params` is a property, asked again at each read, that opens the connection if it must and asks the driver's connection how many parameters one statement may have, a limit set when the library is compiled, 32766 by default, which a connection may lower for itself (`django/db/backends/sqlite3/features.py:DatabaseFeatures.max_query_params`). `BaseDatabaseOperations.bulk_batch_size` divides it by the fields of a row, so that, where it is 32766, a `bulk_create` of ports, two fields each, sends at most 16383 at once (`django/db/backends/base/operations.py:BaseDatabaseOperations.bulk_batch_size`) ([Inserts: returned keys, conflicts and batch sizes](inserts.md)). `DatabaseFeatures.supports_json_field` is a `cached_property` that sends a `"SELECT"` of SQLite's `"JSON"` inside an atomic block the first time it is read, and is false where SQLite raises `OperationalError`. [What a database can do: `BaseDatabaseFeatures`](features.md) has the flags beside the other backends'.

## The schema editor: literals, and where the table is remade

SQLite's schema editor remakes the table where SQLite's `"ALTER TABLE"` falls short, as [Altering a column, and SQLite's table remake](alter-field.md) tells (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor`). `DatabaseSchemaEditor.add_constraint` and `DatabaseSchemaEditor.remove_constraint` remake the table for every constraint but a unique one with a condition, expressions, included columns or a deferral.

Defaults go into SQLite's statements as literals ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)), written by `DatabaseSchemaEditor.quote_value`, which passes the value through `sqlite3.adapt`, then writes it by its type, a string in single quotes with each quote doubled and bytes in hexadecimal, and refuses with `ValueError` a type it does not know (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.quote_value`).

## The command line: SQLite's client

`DatabaseClient.settings_to_cmd_args_env` gives dbshell the command `"sqlite3"`, SQLite's own shell, with the alias's `"NAME"` and dbshell's parameters after it, and no environment (`django/db/backends/sqlite3/client.py:DatabaseClient.settings_to_cmd_args_env`); [The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md) has how dbshell runs it. The shell opens a connection of its own, in another process, and Django's functions are registered only in Django's connections.
