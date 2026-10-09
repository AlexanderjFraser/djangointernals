---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Cursors: executing a statement, the query log and execute wrappers

Django's cursor, `django.db.backends.utils.CursorWrapper`, stands around the driver's cursor: it refuses a statement while the transaction is broken, passes it through the connection's execute wrappers, and turns the driver's exceptions into the classes of `django.db` with `DatabaseErrorWrapper`. Its subclass `django.db.backends.utils.CursorDebugWrapper` times each statement and writes it to the query log, `BaseDatabaseWrapper.queries_log`, and to the logger `"django.db.backends"`.

A cursor is PEP 249's object for sending a statement and reading what comes back; drivers differ in their style of placeholder, and each has its own classes of exception. Django needs more where a statement leaves it: to refuse a statement, without asking the database, once an atomic block's transaction has been marked to be rolled back; to let a project see each statement, change it or stop it; to keep a record of statements when asked; and to raise an exception the code above can catch whatever the driver, `django.db.IntegrityError` and not the driver's class of that name. `BaseDatabaseWrapper.cursor` returns Django's own object, and each of those duties is a layer of it. Under it is what this chapter calls the **driver's cursor**, the object the backend's `BaseDatabaseWrapper.create_cursor` returns, which on SQLite and Oracle rewrites Django's placeholders as the driver's.

## Making a cursor: `cursor`, `create_cursor` and `_prepare_cursor`

`BaseDatabaseWrapper.cursor` calls `BaseDatabaseWrapper._cursor` without a name. `_cursor` gives the health check its turn, opens the driver's connection if none is open ([Opening and closing a connection](lifecycle.md)), and then, inside the connection's translation of errors, asks the backend's `BaseDatabaseWrapper.create_cursor` for the driver's cursor and hands that to `BaseDatabaseWrapper._prepare_cursor` (`django/db/backends/base/base.py:BaseDatabaseWrapper._cursor`). `cursor` is marked `async_unsafe`, and so raises `SynchronousOnlyOperation` in a thread where an event loop is running, unless the environment sets `"DJANGO_ALLOW_ASYNC_UNSAFE"` ([The asynchronous methods of a queryset](../querysets/async.md)).

The base class's `create_cursor` raises `NotImplementedError`, and each backend's returns the driver's cursor, which on SQLite, MySQL and Oracle is of a class the backend defines. SQLite's is a `SQLiteCursorWrapper`, a subclass of sqlite3's cursor class (`django/db/backends/sqlite3/base.py:DatabaseWrapper.create_cursor`); MySQL's is a second `CursorWrapper`, the backend's own, which holds a cursor of MySQLdb's and reclassifies some of its errors (`django/db/backends/mysql/base.py:DatabaseWrapper.create_cursor`); Oracle's is a `FormatStylePlaceholderCursor`, which holds a cursor of the driver's (`django/db/backends/oracle/base.py:DatabaseWrapper.create_cursor`). PostgreSQL's is a cursor declared on the server when it is given a name, and otherwise one of the class chosen as the connection opened, under psycopg 3 the backend's `Cursor`, or its `ServerBindingCursor` where `"server_side_binding"` is `True` (`django/db/backends/postgresql/base.py:DatabaseWrapper.create_cursor`).

Django's cursor keeps the driver's cursor as `CursorWrapper.cursor`, beside the connection as `CursorWrapper.db` (`django/db/backends/utils.py:CursorWrapper.__init__`).

`_prepare_cursor` checks that this thread may use the connection, and then wraps (`django/db/backends/base/base.py:BaseDatabaseWrapper._prepare_cursor`). Where `BaseDatabaseWrapper.queries_logged` holds, which it does where `settings.DEBUG` is true or the connection's `BaseDatabaseWrapper.force_debug_cursor` has been set, `BaseDatabaseWrapper.make_debug_cursor` makes a `CursorDebugWrapper`; otherwise `BaseDatabaseWrapper.make_cursor` makes a plain `CursorWrapper`. The choice is made once, as the cursor is made: a cursor taken before `force_debug_cursor` was set stays plain, and one taken while it was set goes on logging after it is cleared.

## A statement on its way down

Django's cursor is given a statement with one parameter in the recording below, on SQLite, whose cursor rewrites its placeholder for the driver. Under the line of Python stand some of the calls it made, nested; a line `SQL` is the statement as Django handed it to its cursor, written by a wrapper of the recording's own, and a line sqlite the statement as SQLite ran it.

```text recording=backends
with connection.cursor() as cursor: cursor.execute('SELECT name, tonnage FROM fleet_ship WHERE tonnage > %s', [500]); rows = cursor.fetchall()
  BaseDatabaseWrapper.cursor  ->  a CursorWrapper
  CursorWrapper.__enter__
  CursorWrapper.execute
    CursorWrapper._execute_with_wrappers
      SQL SELECT name, tonnage FROM fleet_ship WHERE tonnage > %s with params [500]
      CursorWrapper._execute
        BaseDatabaseWrapper.validate_no_broken_transaction
        SQLiteCursorWrapper.execute
          SQLiteCursorWrapper.convert_query  ->  'SELECT name, tonnage FROM fleet_ship WHERE tonnage > ?'
          sqlite3.Cursor.execute
            sqlite SELECT name, tonnage FROM fleet_ship WHERE tonnage > 500
  CursorWrapper.__getattr__('fetchall')
  sqlite3.Cursor.fetchall
  CursorWrapper.__exit__
    CursorWrapper.__getattr__('close')
    sqlite3.Cursor.close
rows  ->  [('Gannet', 1200)]
```

`CursorWrapper.execute` and `CursorWrapper.executemany` only hand `CursorWrapper._execute_with_wrappers` the statement, its parameters, `many=False` or `many=True`, and the method that does the work, `CursorWrapper._execute` or `CursorWrapper._executemany`. `_execute_with_wrappers` makes a dictionary of context, the connection under `"connection"` and Django's cursor under `"cursor"`, puts the connection's execute wrappers, callables installed to stand around its statements, around the method that does the work, and calls the result (`django/db/backends/utils.py:CursorWrapper._execute_with_wrappers`). The `SQL` line stands between it and `_execute` because the recording's wrapper is one of those wrappers.

`_execute` is the innermost layer (`django/db/backends/utils.py:CursorWrapper._execute`). Until the app registry is first ready, it warns with `RuntimeWarning` and the message of `CursorWrapper.APPS_NOT_READY_WARNING_MSG`. It calls `BaseDatabaseWrapper.validate_no_broken_transaction`, which raises `TransactionManagementError` while the connection's `BaseDatabaseWrapper.needs_rollback` is set, as it is once an error inside an atomic block has left the transaction to be rolled back, or once `BaseDatabaseWrapper.set_rollback` has asked for that ([Transactions: autocommit, `atomic` and savepoints](transactions.md)). Then, inside the connection's translation of errors, it calls the driver's cursor's `execute`, with the parameters, or with the statement alone where they are `None`, leaving their default to the driver. `_executemany` makes the same checks and, inside the same translation, always passes the driver's `executemany` its list.

Before `django.setup()` has run, a statement draws the warning and still reaches SQLite:

```text recording=backends
with connection.cursor() as cursor: cursor.execute('SELECT COUNT(*) FROM fleet_ship')
  CursorWrapper.execute
    CursorWrapper._execute_with_wrappers
      CursorWrapper._execute
        sqlite SELECT COUNT(*) FROM fleet_ship
  warns RuntimeWarning: Accessing the database during app initialization is discouraged. To fix this warning, avoid executing queries in AppConfig.ready() or when your app modules are imported.
```

Django's documentation gives the reason: such a query runs as every management command starts, slowing it, and may cache stale data or fail where migrations are pending (`docs/ref/applications.txt`). Both checks stand inside the wrappers, so a wrapper sees a statement that is about to be refused.

```text figure=a-statement-on-its-way-down
cursor.execute(sql, params)          sql with "%s", or "%(name)s", for each parameter
|
+- CursorDebugWrapper.execute        only where queries_logged held when the cursor was made
|    debug_sql: the clock starts
|  +- CursorWrapper.execute -> _execute_with_wrappers
|  |    context = {"connection": the connection, "cursor": Django's cursor}
|  |  +- the execute wrapper installed first
|  |  |  +- the execute wrapper installed next ... the last is handed _execute itself
|  |  |  |  +- CursorWrapper._execute
|  |  |  |  |    RuntimeWarning, if the apps are not ready
|  |  |  |  |    validate_no_broken_transaction: TransactionManagementError, if needs_rollback
|  |  |  |  |  +- wrap_database_errors (DatabaseErrorWrapper)
|  |  |  |  |  |  +- the driver's cursor: the backend's class
|  |  |  |  |  |  |    SQLite: "%s" -> "?"            Oracle: "%s" -> ":arg0", ":arg1" ...
|  |  |  |  |  |  |    PostgreSQL and MySQL: the driver takes "%s" as it is
|  |  |  |  |  |  |  +- the driver -> the database
|
on the way back up
  a result      returned through Django's layers unchanged
  an exception  of the driver's: wrap_database_errors raises django.db's namesake of its
                PEP 249 class from it; the wrappers see Django's class
                of anything else: passes Django's layers as it is
  debug_sql     in a finally: the time, and the statement, appended to queries_log and
                logged to "django.db.backends", whether the statement returned or raised
```

*The layers a statement passes through on its way to the database, outermost first, and what each does with what comes back; an execute wrapper is there only where one has been installed on the connection.*

A result comes back up through Django's own layers unchanged: Django's cursor does not read it, and PEP 249 does not say what it is. On SQLite it is the driver's cursor, the one Django's cursor holds as `CursorWrapper.cursor`:

```text recording=backends
cursor.execute('SELECT COUNT(*) FROM fleet_ship') is cursor.cursor  ->  True
  SQL SELECT COUNT(*) FROM fleet_ship
```

> **Trap.** On SQLite, then, a fetch chained onto `CursorWrapper.execute` is the driver's own method, outside Django's translation of errors, as in SQLite's `DatabaseWrapper.disable_constraint_checking` (`django/db/backends/sqlite3/base.py:DatabaseWrapper.disable_constraint_checking`). MySQL's driver returns a count of rows instead.

## Execute wrappers: `execute_wrapper` and `execute_wrappers`

An **execute wrapper** is a callable put around the statements of one connection. It is called with five arguments, the next layer inward, the statement, its parameters, whether it is an `executemany`, and the dictionary of context, and is expected to call the next layer with the other four and return what that returns; so it may look, change the statement or its parameters, or not call the next layer at all (`django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`). `BaseDatabaseWrapper.execute_wrappers` is the list of them, empty when the connection is made. `BaseDatabaseWrapper.execute_wrapper` is a context manager that appends a wrapper to the list and, as it is left, pops the last one: the list is a stack, kept in order by the nesting of `with` statements (`django/db/backends/base/base.py:BaseDatabaseWrapper.execute_wrapper`).

`CursorWrapper._execute_with_wrappers` reads the list at every statement, so a wrapper installed after a cursor was made applies to that cursor's next statement. It takes the list in reverse and binds each wrapper to the layer inside it, so the wrapper installed first is outermost and the one installed last is handed `CursorWrapper._execute` or `CursorWrapper._executemany` itself (`django/db/backends/utils.py:CursorWrapper._execute_with_wrappers`). The recording's own wrappers, three that write a line where they run and one that refuses:

```text recording=backends
# the execute wrappers of the script's own:
  def counted(execute, sql, params, many, context):
      note(f"counted is given execute={brief(execute)}, sql={sql!r}, params={params!r}, many={many!r}, context={brief(context)}")
      return execute(sql, params, many, context)
  def outer(execute, sql, params, many, context):
      note("outer begins")
      try:
          return execute(sql, params, many, context)
      finally:
          note("outer ends")
  def inner(execute, sql, params, many, context):
      note(f"inner begins, and is given execute={brief(execute)}")
      try:
          return execute(sql, params, many, context)
      finally:
          note("inner ends")
  def refuse(execute, sql, params, many, context):
      raise PermissionError(f"not here: {sql}")
```

And their use, with the wrapper that writes the `SQL` lines taken off, so that the sqlite lines say what reached the database:

```text recording=backends
connection.execute_wrappers  ->  []
with connection.execute_wrapper(counted): Ship.objects.filter(tonnage__gt=500).count()
  counted is given execute=the method CursorWrapper._execute of a CursorWrapper, sql='SELECT COUNT(*) AS "__count" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s', params=(500,), many=False, context={'connection': the connection "default", 'cursor': a CursorWrapper}
  sqlite SELECT COUNT(*) AS "__count" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > 500
with connection.execute_wrapper(outer), connection.execute_wrapper(inner): Port.objects.count()
  outer begins
  inner begins, and is given execute=the method CursorWrapper._execute of a CursorWrapper
  sqlite SELECT COUNT(*) AS "__count" FROM "fleet_port"
  inner ends
  outer ends
with connection.execute_wrapper(refuse): Port.objects.count()
raises PermissionError: not here: SELECT COUNT(*) AS "__count" FROM "fleet_port"
connection.execute_wrappers  ->  []
```

The innermost wrapper is handed `_execute` itself, whether alone, as counted was, or last of two, as inner was, and it is given the statement as the compiler wrote it, with its `"%s"`. The `PermissionError` of refuse came out as it went in, and nothing reached SQLite. The wrappers stand outside the translation of errors: a driver's exception reaches them already turned into Django's class, and an exception of their own is not translated at all.

The list belongs to the connection, one alias in one thread, so a wrapper installed on `"default"` does not see `"archive"`, or another thread's `"default"`. Every `execute` and `executemany` of Django's cursor passes through it, savepoints included, and on SQLite the `"BEGIN"` of an atomic block ([Transactions: autocommit, `atomic` and savepoints](transactions.md)). It does not see `CursorWrapper.callproc`, which calls no wrapper; a commit or a rollback, which are calls on the driver's connection; or what a backend sends to the driver directly as a connection opens, such as SQLite's first `"PRAGMA"` statements and PostgreSQL's setting of the time zone (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_new_connection`) ([Opening and closing a connection](lifecycle.md)).

## Errors translated: `DatabaseErrorWrapper`

`django/db/utils.py` declares Django's copy of PEP 249's exceptions, all but its warning class: `Error`; under it `InterfaceError` and `DatabaseError`; and under `DatabaseError` those that name a kind of failure, `DataError`, `OperationalError`, `IntegrityError`, `InternalError`, `ProgrammingError` and `NotSupportedError`. `django.db` exports them all (`django/db/__init__.py`). PEP 249 has a driver's module define classes of the same names, and the translation depends on it: the backend's `DatabaseWrapper` names its driver's module as its class attribute `Database`, which `DatabaseErrorWrapper.__init__` requires to define PEP 249's exceptions (`django/db/backends/sqlite3/base.py:DatabaseWrapper`, `django/db/utils.py:DatabaseErrorWrapper.__init__`).

`BaseDatabaseWrapper.wrap_database_errors` is the translator: a `DatabaseErrorWrapper` made once for each connection, used as a context manager around a call into the driver and as a decorator of a method of the driver's (`django/db/backends/base/base.py:BaseDatabaseWrapper.wrap_database_errors`). `DatabaseErrorWrapper.__exit__` does nothing when no exception is leaving. Otherwise it goes through Django's classes in a fixed order, `DataError`, `OperationalError`, `IntegrityError`, `InternalError`, `ProgrammingError`, `NotSupportedError`, `DatabaseError`, `InterfaceError`, `Error`, and for each looks up the driver's class of the same name. At the first that the exception is an instance of, it makes Django's class with the same arguments and raises it with the driver's traceback, from the driver's exception, which becomes its `__cause__` (`django/db/utils.py:DatabaseErrorWrapper.__exit__`).

The order is the tree read from its leaves up. In PEP 249's tree a driver's `IntegrityError` is a subclass of its `DatabaseError` and of its `Error`, and the test is a subclass test: a parent tried before its child would claim the child's exceptions, and a duplicate key would arrive as Django's `DatabaseError`. An exception of none of the driver's classes, one of Python's or of Django's, leaves the translation as it came.

Every class but `DataError` and `IntegrityError` also sets the connection's `BaseDatabaseWrapper.errors_occurred`, which the comment says is set only for errors that may make the connection unusable. Where it is set, the connection is asked whether it still works at the next start or end of a request, and closed if it does not (`django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete`) ([Opening and closing a connection](lifecycle.md)); a commit or a rollback that succeeds clears it. Both kinds on SQLite:

```text recording=backends
with connection.cursor() as cursor: cursor.execute('INSERT INTO fleet_port (id, name, country) VALUES (%s, %s, %s)', [1, 'Bergen', 'Norway'])
  SQL INSERT INTO fleet_port (id, name, country) VALUES (%s, %s, %s) with params [1, 'Bergen', 'Norway']
  CursorWrapper._execute
    sqlite3.Cursor.execute
    DatabaseErrorWrapper.__exit__(exc_type=sqlite3.IntegrityError)  raises IntegrityError
raises IntegrityError: UNIQUE constraint failed: fleet_port.id
type(caught)  ->  django.db.utils.IntegrityError
type(caught.__cause__)  ->  sqlite3.IntegrityError
caught.args  ->  ('UNIQUE constraint failed: fleet_port.id',)
isinstance(caught, DatabaseError)  ->  True
connection.errors_occurred  ->  False
with connection.cursor() as cursor: cursor.execute('SELEC 1')
  SQL SELEC 1
  CursorWrapper._execute
    sqlite3.Cursor.execute
    DatabaseErrorWrapper.__exit__(exc_type=sqlite3.OperationalError)  raises OperationalError
raises OperationalError: near "SELEC": syntax error
type(caught)  ->  django.db.utils.OperationalError
type(caught.__cause__)  ->  sqlite3.OperationalError
connection.errors_occurred  ->  True
connection.close()
```

The same translator stands around the calls that open the driver's connection, make a cursor, roll back, close and change autocommit, and around a commit on every backend but Oracle (`django/db/backends/base/base.py:BaseDatabaseWrapper._commit`). Two backends reclassify an error before the translator sees it. MySQL's `CursorWrapper` raises Django's `IntegrityError` where MySQLdb raises `OperationalError` with a code in `CursorWrapper.codes_for_integrityerror`, those of a column that cannot be null, an unsigned value out of range and a check constraint, which the comment says seem misclassified (`django/db/backends/mysql/base.py:CursorWrapper.execute`). At the cursor, being Django's own class, that exception passes the translation untouched. Oracle's `wrap_oracle_errors` does the same for a transaction rolled back by a broken foreign key or a duplicate key, around its cursor's statements and, in the translator's place, around its commit, so that any other exception of a commit on Oracle leaves untranslated (`django/db/backends/oracle/base.py:wrap_oracle_errors`, `django/db/backends/oracle/base.py:DatabaseWrapper._commit`) ([MySQL and MariaDB](mysql.md), [Oracle](oracle.md)).

## The rest of the cursor: fetching, closing and `callproc`

`CursorWrapper.callproc`, `CursorWrapper.execute` and `CursorWrapper.executemany` are methods of Django's cursor (`django/db/backends/utils.py:CursorWrapper`). `CursorWrapper.__getattr__` hands on everything else from the driver's cursor: those that `CursorWrapper.WRAP_ERROR_ATTRS` names, `"fetchone"`, `"fetchmany"`, `"fetchall"` and `"nextset"`, wrapped in the connection's translation of errors, and the rest, the count of rows, the description of the columns, the method that closes it, as the driver has it (`django/db/backends/utils.py:CursorWrapper.__getattr__`). In the first recording on this page, the fetch and the close are each looked up through `__getattr__`. `CursorWrapper.__iter__` iterates over the driver's cursor inside the translation.

Django's cursor is its own context manager. `CursorWrapper.__enter__` returns it, and `CursorWrapper.__exit__` closes the driver's cursor and ignores any exception of the driver's that the close raises; the comment gives both reasons, that closing rather than passing the `with` through to the driver's cursor avoids behaviour peculiar to a backend, and that errors in cleanup code are not useful (`django/db/backends/utils.py:CursorWrapper.__exit__`).

`callproc` calls a stored procedure. It refuses keyword parameters with `NotSupportedError` unless the features say `BaseDatabaseFeatures.supports_callproc_kwargs`, which only Oracle's do; the comment says PEP 249 has no keyword parameters for it but a driver may, oracledb for one. Then it warns before the apps are ready, refuses in a broken transaction, and calls the driver's method inside the translation (`django/db/backends/utils.py:CursorWrapper.callproc`). It calls no execute wrapper, and `CursorDebugWrapper` neither times nor logs it. Under psycopg 3 the PostgreSQL backend's cursor classes supply `callproc` themselves, as a `"SELECT"` from the function (`django/db/backends/postgresql/base.py:CursorMixin.callproc`) ([PostgreSQL](postgresql.md)).

## Placeholders: `"%s"` and `"%(name)s"`

Django writes a statement in one style whatever the database: `"%s"` for each parameter where the parameters are a sequence, as the compiler's always are, and `"%(name)s"` where they are a dictionary, which raw SQL may give. Where there are parameters, a percent sign meant literally is written twice, `"%%"`, as in the patterns a backend keeps for `"LIKE"`, PostgreSQL's `"LIKE '%%' || {}"` among them (`django/db/backends/postgresql/base.py:DatabaseWrapper.pattern_ops`). Each backend's cursor turns that into its driver's style:

- SQLite's `SQLiteCursorWrapper.convert_query` writes each `"%s"` not preceded by a percent sign as `"?"` and each `"%%"` as `"%"`, and with a dictionary writes each `"%(name)s"` as `":name"` (`django/db/backends/sqlite3/base.py:SQLiteCursorWrapper.convert_query`); [SQLite](sqlite.md).
- PostgreSQL's backend rewrites nothing, since psycopg 3 and psycopg2 both take `"%s"` and `"%(name)s"`; `Cursor` has the driver write the values into the statement before sending it, and `ServerBindingCursor` has it send them beside the statement for the server to bind (`django/db/backends/postgresql/base.py:DatabaseWrapper.get_connection_params`); [PostgreSQL](postgresql.md).
- MySQL's backend rewrites nothing, since MySQLdb takes the same two styles and writes the values, quoted, into the statement before sending it (`django/db/backends/mysql/base.py:CursorWrapper.execute`); [MySQL and MariaDB](mysql.md).
- Oracle's `FormatStylePlaceholderCursor._fix_for_params` writes the placeholders of a sequence as `":arg0"`, `":arg1"` and on, giving equal values of one type a single placeholder in an `execute`, and each `"%(name)s"` as `":name"` (`django/db/backends/oracle/base.py:FormatStylePlaceholderCursor._fix_for_params`); [Oracle](oracle.md).

With a dictionary of parameters, SQLite's rewriting is the one below:

```text recording=backends
SQL SELECT name FROM fleet_ship WHERE tonnage > %(tonnage)s with params {'tonnage': 500}
CursorWrapper._execute
  BaseDatabaseWrapper.validate_no_broken_transaction
  SQLiteCursorWrapper.execute
    SQLiteCursorWrapper.convert_query(param_names=['tonnage'])  ->  'SELECT name FROM fleet_ship WHERE tonnage > :tonnage'
    sqlite3.Cursor.execute
      sqlite SELECT name FROM fleet_ship WHERE tonnage > 500
```

> **Trap.** A percent sign is doubled only where there are parameters. Given `None`, `CursorWrapper._execute` sends the statement alone, and SQLite's and Oracle's cursors pass it on without reading its percent signs, as do the drivers of PostgreSQL and MySQL, so `"%%"` reaches the database as two characters (`django/db/backends/utils.py:CursorWrapper._execute`). An empty list is parameters, and `"%%"` becomes one.

## The debug cursor and the query log

`CursorDebugWrapper` is a `CursorWrapper` whose `execute` and `executemany` run the parent's inside `CursorDebugWrapper.debug_sql`, a context manager that reads a monotonic clock before and after and writes its record in a `finally`, so a statement that raised is recorded with the rest (`django/db/backends/utils.py:CursorDebugWrapper.debug_sql`). The time covers the wrappers and the driver's `execute`, not the reading of rows. The record goes to the connection's `BaseDatabaseWrapper.queries_log` and, at the debug level, to the logger `"django.db.backends"`, whose record also carries the parameters and the alias, in its message and as attributes. For `execute` the statement is what the operations object's `BaseDatabaseOperations.last_executed_query` makes of it, with its values in place where the backend can put them; for `executemany` it is the statement as given, and its entry in `queries_log` begins with the number of sets of parameters, or a question mark where they were an iterator with no length.

```text recording=backends
connection.force_debug_cursor = True
connection.queries_logged  ->  True
# the logger django.db.backends is set to DEBUG for this block, and given the script's handler, which writes each record as a line `log`
with connection.cursor() as cursor: cursor.execute('SELECT name FROM fleet_ship WHERE tonnage > %s', [500])
  BaseDatabaseWrapper.cursor
    sqlite3.Connection.cursor
    BaseDatabaseWrapper.make_debug_cursor  ->  a CursorDebugWrapper
    -> a CursorDebugWrapper
  CursorDebugWrapper.execute
    CursorDebugWrapper.debug_sql
    CursorWrapper.execute
      SQL SELECT name FROM fleet_ship WHERE tonnage > %s with params [500]
      sqlite3.Cursor.execute
        sqlite SELECT name FROM fleet_ship WHERE tonnage > 500
    CursorDebugWrapper.debug_sql resumes
      DatabaseOperations.last_executed_query
...
        -> 'SELECT name FROM fleet_ship WHERE tonnage > 500'
      log django.db.backends DEBUG: (0.000) SELECT name FROM fleet_ship WHERE tonnage > 500; args=[500]; alias=default  (extra: alias, duration, params, sql)
full(connection.queries)  ->  [{'sql': 'SELECT name FROM fleet_ship WHERE tonnage > 500', 'time': '0.000'}]
```

`settings.DEBUG` was off, and the debug cursor was made because `force_debug_cursor` was set. The base class's `last_executed_query` returns the statement and its parameters as text, in the form `"QUERY = %r - PARAMS = %r"` (`django/db/backends/base/operations.py:BaseDatabaseOperations.last_executed_query`). MySQL's returns the statement MySQLdb sent, values and all, and PostgreSQL's the one psycopg sent where the values are bound on the client, or one psycopg composes where they are bound on the server (`django/db/backends/mysql/operations.py:DatabaseOperations.last_executed_query`, `django/db/backends/postgresql/operations.py:DatabaseOperations.last_executed_query`). SQLite's puts the quoted values into the statement, and returns the statement as it is where the parameters are `None` or empty; Oracle's takes the driver's statement, which keeps `":arg0"` and the rest, and replaces each with its value's text (`django/db/backends/sqlite3/operations.py:DatabaseOperations.last_executed_query`, `django/db/backends/oracle/operations.py:DatabaseOperations.last_executed_query`).

`queries_log` is a deque made with each connection, whose length is bounded by the class attribute `BaseDatabaseWrapper.queries_limit`, 9,000, past which the oldest record drops off as each new one is added. `BaseDatabaseWrapper.queries` returns a copy as a list, and warns where the log is full (`django/db/backends/base/base.py:BaseDatabaseWrapper.queries`). `reset_queries` empties the log of every connection this thread has made, and `django/db/__init__.py` connects it to `request_started`, so that with `settings.DEBUG` on a connection's log holds the statements since the current request began (`django/db/__init__.py:reset_queries`). Next, an `executemany`, logged with its placeholders and its count, and the log emptied:

```text recording=backends
with connection.cursor() as cursor: cursor.executemany('UPDATE crew_sailor SET name = %s WHERE id = %s', [('Ada', 1), ('Bram', 2), ('Dag', 4)])
...
  CursorDebugWrapper.executemany
    CursorDebugWrapper.debug_sql
    CursorWrapper.executemany
      SQL UPDATE crew_sailor SET name = %s WHERE id = %s with each of [('Ada', 1), ('Bram', 2), ('Dag', 4)] (executemany)
      sqlite3.Cursor.executemany
        sqlite UPDATE crew_sailor SET name = 'Ada' WHERE id = 1
        sqlite UPDATE crew_sailor SET name = 'Bram' WHERE id = 2
        sqlite UPDATE crew_sailor SET name = 'Dag' WHERE id = 4
    CursorDebugWrapper.debug_sql resumes
      log django.db.backends DEBUG: (0.000) UPDATE crew_sailor SET name = %s WHERE id = %s; args=[('Ada', 1), ('Bram', 2), ('Dag', 4)]; alias=default  (extra: alias, duration, params, sql)
full(connection.queries)  ->  [{'sql': 'SELECT name FROM fleet_ship WHERE tonnage > 500', 'time': '0.000'}, {'sql': '3 times: UPDATE crew_sailor SET name = %s WHERE id = %s', 'time': '0.000'}]
reset_queries()
connection.queries  ->  []
connection.force_debug_cursor = False
```

A commit, a rollback and turning autocommit off are not statements through a cursor but calls on the driver's connection, which `debug_transaction` records in `queries_log` and to the logger as `"COMMIT"`, `"ROLLBACK"` and `"BEGIN"`, where `queries_logged` holds as they end; `BaseDatabaseWrapper._commit`, `BaseDatabaseWrapper._rollback` and `BaseDatabaseWrapper.set_autocommit` use it (`django/db/backends/utils.py:debug_transaction`). A savepoint is a statement through a cursor, as on SQLite is the `"BEGIN"` of an atomic block, and the debug cursor records them (`django/db/backends/base/base.py:BaseDatabaseWrapper._savepoint`). Both, with `force_debug_cursor` set:

```text recording=backends
with transaction.atomic(): Ship.objects.count()
  Atomic.__enter__
    DatabaseWrapper._start_transaction_under_autocommit
      CursorDebugWrapper.execute
        SQL BEGIN
        sqlite BEGIN
        log django.db.backends DEBUG: (0.000) BEGIN; args=None; alias=default  (extra: alias, duration, params, sql)
...
  Atomic.__exit__
    BaseDatabaseWrapper.commit
      BaseDatabaseWrapper._commit
        debug_transaction(connection, 'COMMIT')
        sqlite3.Connection.commit
          sqlite COMMIT
        debug_transaction resumes
          log django.db.backends DEBUG: (0.000) COMMIT; args=None; alias=default  (extra: alias, duration, sql)
```

Oracle, which does not release savepoints, appends a line marked as faked to `queries_log` where the release would be, when `queries_logged` holds (`django/db/backends/oracle/base.py:DatabaseWrapper._savepoint_commit`) ([Transactions: autocommit, `atomic` and savepoints](transactions.md)).

Django's documentation says SQL logging is enabled only when `settings.DEBUG` is true (`docs/ref/logging.txt`); the code's condition is `queries_logged`, which `force_debug_cursor` makes true as well. The test framework sets it: `CaptureQueriesContext`, which `assertNumQueries` uses, sets it for the length of its block and meanwhile disconnects `reset_queries`, and the test runner's option `"--debug-sql"` sets it on every connection (`django/test/utils.py:CaptureQueriesContext`, `django/test/utils.py:setup_databases`) ([The test framework](../testing.md)).

## The chunked cursor: `chunked_cursor`

`BaseDatabaseWrapper.chunked_cursor` is the cursor the compiler takes when the rows are to be read a chunk at a time, which `QuerySet.iterator` asks for unless the alias sets `"DISABLE_SERVER_SIDE_CURSORS"` ([Evaluation and the result cache](../querysets/evaluation.md), [The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)). It is meant to return a cursor that tries to avoid caching in the database where the database supports one, and a regular cursor otherwise; the base class's returns `cursor()` (`django/db/backends/base/base.py:BaseDatabaseWrapper.chunked_cursor`). On SQLite:

```text recording=backends
ships = list(Ship.objects.iterator(chunk_size=1))
  QuerySet.iterator(chunk_size=1)
  QuerySet._iterator(use_chunked_fetch=True, chunk_size=1)
    SQLCompiler.execute_sql(chunked_fetch=True, chunk_size=1)
      BaseDatabaseWrapper.chunked_cursor
        BaseDatabaseWrapper.cursor  ->  a CursorWrapper
      SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
    cursor_iter(itersize=1)
      sqlite3.Cursor.fetchmany
  QuerySet._iterator resumes
    cursor_iter resumes
      sqlite3.Cursor.fetchmany
  QuerySet._iterator resumes
    cursor_iter resumes
      sqlite3.Cursor.fetchmany
ships  ->  [<Ship: Gannet>, <Ship: Petrel>]
connection.features.can_use_chunked_reads  ->  True
```

Of the four backends, PostgreSQL's alone overrides it. Its `DatabaseWrapper.chunked_cursor` hands `BaseDatabaseWrapper._cursor` a name made of the thread's identifier, the current asyncio task's identity or `"sync"`, and a count kept on the connection, and its `DatabaseWrapper.create_cursor`, given a name, opens a cursor declared on the server, holdable past the end of a transaction where the connection is in autocommit (`django/db/backends/postgresql/base.py:DatabaseWrapper.chunked_cursor`) ([PostgreSQL](postgresql.md)). SQLite's, MySQL's and Oracle's are the base's, and `BaseDatabaseFeatures.can_use_chunked_reads` is true on all four, so on each the compiler hands back `cursor_iter`'s generator unread rather than reading it into a list, and `cursor_iter` stops at the features' `BaseDatabaseFeatures.empty_fetchmany_value`, which MySQL's give as `()` (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`, `django/db/backends/mysql/features.py:DatabaseFeatures`). What a chunk costs is the driver's affair: Django's documentation says MySQL's driver loads the whole result into memory, Oracle's always reads through a cursor on the server, and SQLite's can fetch results in batches (`docs/ref/models/querysets.txt`).
