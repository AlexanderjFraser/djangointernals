---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Opening and closing a connection

A connection opens its driver's connection in `BaseDatabaseWrapper.connect`, when it is first needed, and closes it in `BaseDatabaseWrapper.close`. At the start and the end of each request `BaseDatabaseWrapper.close_if_unusable_or_obsolete` decides, from `"CONN_MAX_AGE"`, `"AUTOCOMMIT"` and what has happened to the connection, whether it is kept for the next; a connection may be used only by the thread that made it unless it is shared, and PostgreSQL and Oracle can take their connections from a pool.

A connection to a database is costly to open and can die while it is held; Django's documentation gives the first as the reason to keep connections between requests, and a server that drops idle clients or restarts as the second (`docs/ref/databases.txt`). The connection object outlives any number of driver's connections: its attribute `connection` is the driver's connection while it is open and, outside an atomic block, `None` once it is closed, as it is when the object is made (`django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`). It opens when something first needs the driver's connection, a cursor or the autocommit mode, which entering an atomic block reads, and not before; it closes at a few fixed points: when code asks, when a request starts or ends and the connection is too old or in doubt, and when a health check finds it dead.

```text figure=a-connection-across-requests
connections["default"], first asked for in a thread      the connection made; .connection is None

a request starts         close_old_connections          nothing open: nothing asked
  the first cursor       ensure_connection -> connect   the driver's connection opened;
                                                         close_at = now + CONN_MAX_AGE, none for None
  more cursors           the same driver's connection
a request ends           close_old_connections -> close_if_unusable_or_obsolete,
                         which asks of an open connection, in this order:
                           autocommit not as "AUTOCOMMIT" says?          close
                           errors_occurred, and is_usable() says no?    close
                           close_at passed?                              close
                           none of these                                 keep

                         CONN_MAX_AGE 0      close_at passed as it opened: closed
                         CONN_MAX_AGE 60     kept until 60 seconds after it opened
                         CONN_MAX_AGE None   never closed for its age

the next request starts  close_old_connections -> the same questions
  the first cursor       kept: a health check, where CONN_HEALTH_CHECKS is on;
                           is_usable() says no?  close, and connect again
                         closed: connect
a request ends           the same questions
```

*One thread's connection across requests: opened at the first cursor, with `close_at` fixed by `"CONN_MAX_AGE"`, asked whether to close as a request starts and ends, and, where health checks are on, checked when the next request first uses it.*

## Opened by the first cursor: `ensure_connection`

`BaseDatabaseWrapper.ensure_connection` calls `BaseDatabaseWrapper.connect` if the driver's connection is `None`, unless `BaseDatabaseWrapper.in_atomic_block` and `BaseDatabaseWrapper.closed_in_transaction` are both set, when it refuses ([Closed inside an atomic block](#closed-inside-an-atomic-block)), and otherwise does nothing (`django/db/backends/base/base.py:BaseDatabaseWrapper.ensure_connection`). `BaseDatabaseWrapper._cursor` calls it before making each cursor, and `BaseDatabaseWrapper.get_autocommit` and `BaseDatabaseWrapper.set_autocommit` before they read or change the mode. Making the connection object and building a queryset send nothing; compiling a query can, for instance the first time a connection object needs the server's version or, on Oracle, its operators. It runs `connect` inside `BaseDatabaseWrapper.wrap_database_errors`, so a driver's failure to connect reaches the caller as the `django.db` exception of the same name ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)). Both methods refuse to run on a thread where an event loop is running, unless the environment sets `"DJANGO_ALLOW_ASYNC_UNSAFE"` ([The asynchronous methods of a queryset](../querysets/async.md)).

A second cursor finds the driver's connection open, and its `ensure_connection` returns at once; each cursor is a driver's cursor of its own, made on the one driver's connection (`django/db/backends/base/base.py:BaseDatabaseWrapper._cursor`). Recorded from a running Django after a first cursor, called first in the recording, had opened the connection `"default"`; a line at the left margin is a line of Python as it ran, with its value after `->`, and the lines under it are the calls it set going, nested as they were made, only those this passage is about written down:

```text recording=backends
second = connection.cursor()
  BaseDatabaseWrapper.cursor
    BaseDatabaseWrapper._cursor
      BaseDatabaseWrapper.close_if_health_check_failed
      BaseDatabaseWrapper.ensure_connection
      DatabaseWrapper.create_cursor
...
first.cursor is second.cursor  ->  False
first.cursor.connection is second.cursor.connection is connection.connection  ->  True
```

## `connect`, in its order

`BaseDatabaseWrapper.connect` assumes that the connection is closed, and takes its steps in an order in which the later ones rely on the earlier (`django/db/backends/base/base.py:BaseDatabaseWrapper.connect`):

1. `BaseDatabaseWrapper.check_settings` refuses, with `ImproperlyConfigured`, an alias that sets `"TIME_ZONE"` while `USE_TZ` is off, before anything is opened ([Values in and out: adapters, converters and time zones](values.md)).
2. The transaction's state is reset, in case the previous connection was closed inside an atomic block: `BaseDatabaseWrapper.in_atomic_block`, `BaseDatabaseWrapper.savepoint_ids`, `BaseDatabaseWrapper.atomic_blocks`, `BaseDatabaseWrapper.needs_rollback`.
3. What governs closing is reset: `BaseDatabaseWrapper.health_check_enabled` from `"CONN_HEALTH_CHECKS"`, `BaseDatabaseWrapper.close_at` from `"CONN_MAX_AGE"`, `BaseDatabaseWrapper.closed_in_transaction` and `BaseDatabaseWrapper.errors_occurred` cleared, and `BaseDatabaseWrapper.health_check_done` set, since, the comment says, new connections are healthy.
4. `BaseDatabaseWrapper.get_connection_params` turns the settings into the driver's arguments, and `BaseDatabaseWrapper.get_new_connection` opens the driver's connection with them; on SQLite it also registers Django's functions with the driver's connection (`django/db/backends/sqlite3/_functions.py:register`) ([SQLite](sqlite.md)). The driver's connection is stored as `connection` at once, so every later step finds it open, and one that raises leaves it so.
5. `BaseDatabaseWrapper.set_autocommit` puts the connection in the mode `"AUTOCOMMIT"` asks for, autocommit unless it is `False`, whatever mode the driver opened it in, PEP 249's default being off ([Transactions: autocommit, `atomic` and savepoints](transactions.md)).
6. `BaseDatabaseWrapper.init_connection_state` checks the database's version, once for each alias; the overrides of PostgreSQL, MySQL and Oracle call it first and then set the session up, in the mode just set. PostgreSQL's and Oracle's commit their setup where autocommit is off; Oracle's comment says this is so that the changes are kept (`django/db/backends/oracle/base.py:DatabaseWrapper.init_connection_state`).
7. `connection_created` is sent, with the connection's class as the sender and the connection as `connection`; `django.contrib.postgres` connects a receiver that registers hstore and citext for each new PostgreSQL connection but the one with no database (`django/contrib/postgres/apps.py:PostgresConfig.ready`).
8. The callbacks held for a commit are dropped ([Work held until the commit: `on_commit`](on-commit.md)).

### What each backend does to open

`connect` leaves three steps to the backend, and the base class implements only the third, as the version check (`django/db/backends/base/base.py:BaseDatabaseWrapper.get_new_connection`, `django/db/backends/base/base.py:BaseDatabaseWrapper.init_connection_state`):

| backend | `get_connection_params` | `get_new_connection` | `init_connection_state` |
|---|---|---|---|
| SQLite (`django/db/backends/sqlite3/base.py:DatabaseWrapper`) | the file's name and `"OPTIONS"`, Django's own two options taken out, with the driver's guard against sharing between threads turned off; an empty `"NAME"` refused | the driver's connect; Django's functions registered; foreign keys turned on; the init commands run | the base class's version check alone |
| PostgreSQL (`django/db/backends/postgresql/base.py:DatabaseWrapper`) | the settings and `"OPTIONS"`, Django's own options taken out; under psycopg 3 the adapters, and no prepared statements unless asked | a connection from the pool where there is one, the driver's connect otherwise | the version check; the session's time zone and role, unless a pool set them |
| MySQL (`django/db/backends/mysql/base.py:DatabaseWrapper`) | Django's converters, `"utf8mb4"`, the settings, a flag to count the rows an update matched, the isolation level checked; then `"OPTIONS"` | the driver's connect | the version check; one statement for `"SET SQL_AUTO_IS_NULL = 0"`, where the server has it on, and the isolation level |
| Oracle (`django/db/backends/oracle/base.py:DatabaseWrapper`) | `"OPTIONS"`, without `"use_returning_into"` | a connection from the pool where there is one, the driver's connect otherwise | the version check; the session's territory, date formats and, under `USE_TZ`, time zone; a test of how `"LIKE"` can be written, once for each connection object; the statement cache |

*The three steps of `connect` that a backend supplies or extends. The backends' sections have the detail: [SQLite](sqlite.md), [PostgreSQL](postgresql.md), [MySQL and MariaDB](mysql.md), [Oracle](oracle.md).*

### The version, checked once for each alias

The base class's `init_connection_state` checks the version only for an alias not yet in `RAN_DB_VERSION_CHECK`, a set at the module's level, and adds the alias once the check has passed (`django/db/backends/base/base.py:BaseDatabaseWrapper.init_connection_state`). The set is the process's: a second thread's connection for the alias, or the same connection opened again, does not ask again. Here the connection `"default"` is opened after both aliases have passed the check, and its `init_connection_state` asks nothing; base_module is the module `django/db/backends/base/base.py`:

```text recording=backends
connection.connection is None  ->  True
sorted(base_module.RAN_DB_VERSION_CHECK)  ->  ['archive', 'default']
first = connection.cursor()
  BaseDatabaseWrapper.cursor
    BaseDatabaseWrapper._cursor
      BaseDatabaseWrapper.close_if_health_check_failed
      BaseDatabaseWrapper.ensure_connection
        BaseDatabaseWrapper.connect
          BaseDatabaseWrapper.init_connection_state
          Signal.send  (connection_created, sender=DatabaseWrapper)
```

`BaseDatabaseWrapper.check_database_version_supported` compares `BaseDatabaseWrapper.get_database_version` with `BaseDatabaseFeatures.minimum_database_version`, and refuses an older server with `NotSupportedError` (`django/db/backends/base/base.py:BaseDatabaseWrapper.check_database_version_supported`) ([What a database can do: `BaseDatabaseFeatures`](features.md)). SQLite's version is the library's, which the driver reports with no connection. The other three need an open connection, and ask through a cached property of the connection object that takes one with `BaseDatabaseWrapper.temporary_connection`, MySQL's alone by a statement (`django/db/backends/postgresql/base.py:DatabaseWrapper.pg_version`, `django/db/backends/mysql/base.py:DatabaseWrapper.mysql_server_data`, `django/db/backends/oracle/base.py:DatabaseWrapper.oracle_version`).

> **Trap.** `connect` stores the driver's connection before the check, and nothing closes it when the check refuses. The next cursor finds the connection open and uses it, unchecked, without the rest of `init_connection_state`, without `connection_created`, and without the step that drops the held callbacks.

Recorded on a connection of a separate alias, `"aged"`, whose features were set to ask for a newer SQLite:

```text recording=backends
aged.cursor()
...
raises NotSupportedError: SQLite 3.99 or later is required (found 3.50.4).
aged.connection is None  ->  False
'aged' in base_module.RAN_DB_VERSION_CHECK  ->  False
aged.cursor()
  BaseDatabaseWrapper.cursor  (on "aged")
    BaseDatabaseWrapper._cursor  (on "aged")
      BaseDatabaseWrapper.close_if_health_check_failed  (on "aged")
      BaseDatabaseWrapper.ensure_connection  (on "aged")
      DatabaseWrapper.create_cursor  (on "aged")
```

## Closing: `close` and `_close`

`BaseDatabaseWrapper.close` checks that this thread may use the connection, drops the callbacks held for a commit, and returns at once if the connection is not open, or was closed already inside a block (`django/db/backends/base/base.py:BaseDatabaseWrapper.close`). Otherwise it calls `BaseDatabaseWrapper._close`, which calls the driver's connection's close inside `BaseDatabaseWrapper.wrap_database_errors`, and then `close`, in a `finally`, sets `connection` to `None`, so that the driver's connection is forgotten even when its close raised; inside an atomic block it keeps it instead ([Closed inside an atomic block](#closed-inside-an-atomic-block)). Unlike `BaseDatabaseWrapper.commit`, `BaseDatabaseWrapper.rollback` and `BaseDatabaseWrapper.set_autocommit`, `close` does not refuse inside an atomic block, and its comment says why: a connection in an invalid state should not be hard to get rid of, and the next `BaseDatabaseWrapper.connect` resets the transaction's state anyway.

A backend changes what closing does to the driver's connection in `_close`, as PostgreSQL's does to give a pooled connection back. SQLite's `DatabaseWrapper.close` replaces `close` itself, and ignores a close of a database in memory, which, its comment says, closing would destroy (`django/db/backends/sqlite3/base.py:DatabaseWrapper.close`).

## Kept or closed at a request's end: `close_if_unusable_or_obsolete`

`close_old_connections`, a receiver of `request_started` and `request_finished` ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)), calls `BaseDatabaseWrapper.close_if_unusable_or_obsolete` on each connection this thread has made (`django/db/__init__.py:close_old_connections`). `close_if_unusable_or_obsolete` leaves a closed connection alone, and asks of an open one, in this order (`django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete`):

1. It marks the health check as not done, so that the next cursor, or the next change of autocommit, runs one where health checks are on.
2. If autocommit is not as `"AUTOCOMMIT"` says, it closes the connection: code changed the mode and did not restore it.
3. If `BaseDatabaseWrapper.errors_occurred` is set, it asks `BaseDatabaseWrapper.is_usable`. A connection that answers is not closed for this: the flag is cleared, the health check is counted as done, and the last question is asked; one that does not answer is closed.
4. If `BaseDatabaseWrapper.close_at` is set and has passed, it closes the connection.

Recorded with `"CONN_MAX_AGE"` set to `None`, then 60, then 0, the connection closed by hand before each new setting, and the calls on the project's second database left out:

```text recording=backends
connection.settings_dict['CONN_MAX_AGE'] = None
Ship.objects.count()
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
connection.close_at  ->  None
signals.request_finished.send(sender=WSGIHandler)
  Signal.send  (request_finished, sender=WSGIHandler)
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
        BaseDatabaseWrapper.get_autocommit  ->  True
connection.connection is None  ->  False
...
connection.settings_dict['CONN_MAX_AGE'] = 60
Ship.objects.count()
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
59 < connection.close_at - time.monotonic() <= 60  ->  True
...
connection.settings_dict['CONN_MAX_AGE'] = 0
Ship.objects.count()
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
connection.close_at <= time.monotonic()  ->  True
signals.request_finished.send(sender=WSGIHandler)
  Signal.send  (request_finished, sender=WSGIHandler)
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
        BaseDatabaseWrapper.get_autocommit  ->  True
        DatabaseWrapper.close
          BaseDatabaseWrapper.close
connection.connection is None  ->  True
```

`BaseDatabaseWrapper.connect` reads `"CONN_MAX_AGE"` each time it opens the connection, and sets `close_at` to `time.monotonic` of that moment plus the age, or to `None` for `None`. The default, 0, which `ConnectionHandler.configure_settings` fills in, makes `close_at` the moment of opening: the age question at the first request boundary after finds it passed, and the connection lives for one request. A number keeps the connection until that many seconds after it was opened, counted from the opening and not from its last use; `None` never closes it for its age. Between boundaries nothing looks at the age, so a connection past its `close_at` is used until a request starts or ends in its thread. The test client takes `close_old_connections` off both signals while it sends them, so a request made in a test leaves the test's connections as they were ([The test framework](../testing.md)).

> **Changed in 6.2.** Under ASGI, the response for an exception, a 404's or a 500's page, is made on the request's own thread and not on one of a shared pool, so that, the release notes say, a connection used while the response is made is managed by `close_old_connections` (`django/core/handlers/exception.py:convert_exception_to_response`, `docs/releases/6.2.txt`).

The other two questions, recorded with `"CONN_MAX_AGE"` at `None` so that age closes nothing, the second database's calls again left out:

```text recording=backends
transaction.set_autocommit(False)
signals.request_finished.send(sender=WSGIHandler)
  Signal.send  (request_finished, sender=WSGIHandler)
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
        BaseDatabaseWrapper.get_autocommit  ->  False
        DatabaseWrapper.close
          BaseDatabaseWrapper.close
connection.connection is None  ->  True
...
with connection.cursor() as cursor: cursor.execute('SELEC 1')
  SQL SELEC 1
raises OperationalError: near "SELEC": syntax error
connection.errors_occurred  ->  True
signals.request_finished.send(sender=WSGIHandler)
  Signal.send  (request_finished, sender=WSGIHandler)
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
        BaseDatabaseWrapper.get_autocommit  ->  True
        DatabaseWrapper.is_usable  ->  True
connection.connection is None  ->  False
connection.errors_occurred  ->  False
```

`DatabaseErrorWrapper.__exit__` sets `errors_occurred` for each driver's error it translates but a `DataError` or an `IntegrityError`, here the misspelt statement's `OperationalError` (`django/db/utils.py:DatabaseErrorWrapper.__exit__`) ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)). `connect` clears it, and so do `BaseDatabaseWrapper.commit` and `BaseDatabaseWrapper.rollback`, a commit or rollback that succeeded meaning that the connection works.

## Health checks: `"CONN_HEALTH_CHECKS"`

A health check asks a connection kept between requests whether it still works before the next request uses it, since the server may have dropped it meanwhile; `"CONN_HEALTH_CHECKS"`, off unless it is set, turns the checks on. `BaseDatabaseWrapper.connect` copies it into `BaseDatabaseWrapper.health_check_enabled` and sets `BaseDatabaseWrapper.health_check_done`; `BaseDatabaseWrapper.close_if_unusable_or_obsolete` clears `health_check_done` at each request boundary; and `BaseDatabaseWrapper.close_if_health_check_failed`, which `BaseDatabaseWrapper._cursor` and `BaseDatabaseWrapper.set_autocommit` call before `BaseDatabaseWrapper.ensure_connection`, checks a connection that is open, has checks enabled and has not been checked since. If `BaseDatabaseWrapper.is_usable` says no it closes the connection, and outside an atomic block the `ensure_connection` after it opens another (`django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_health_check_failed`). Either way it marks the check done, so a request pays for one check at most, and none if it does not use the database. Recorded with `"CONN_HEALTH_CHECKS"` on and `"CONN_MAX_AGE"` at `None`, on an open connection once a request has started:

```text recording=backends
connection.health_check_done  ->  False
Ship.objects.count()
  BaseDatabaseWrapper.close_if_health_check_failed
    DatabaseWrapper.is_usable  ->  True
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
connection.health_check_done  ->  True
Port.objects.count()
  BaseDatabaseWrapper.close_if_health_check_failed
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_port"
```

A check that fails, recorded with a stand-in for `is_usable` that answers no:

```text recording=backends
connection.health_check_done  ->  False
Ship.objects.count()
  BaseDatabaseWrapper.close_if_health_check_failed
    unusable  (the stand-in set as the connection's is_usable)  ->  False
    DatabaseWrapper.close
      BaseDatabaseWrapper.close
  BaseDatabaseWrapper.connect
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      BaseDatabaseWrapper.close_if_health_check_failed
    Signal.send  (connection_created, sender=DatabaseWrapper)
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
```

What a check costs is the backend's `is_usable`, whose docstring in the base class asks it not to raise, since an exception there may prevent Django from recycling an unusable connection (`django/db/backends/base/base.py:BaseDatabaseWrapper.is_usable`). SQLite's always answers true. PostgreSQL's runs `"SELECT 1"` on a driver's cursor, not Django's (`django/db/backends/postgresql/base.py:DatabaseWrapper.is_usable`). MySQL's and Oracle's ask the driver to ping the server.

## Closed inside an atomic block

A connection can be closed while an atomic block is open, by code that calls `BaseDatabaseWrapper.close` or by a check that finds it unusable. Recorded on SQLite, where the outermost block begins its transaction by sending `"BEGIN"` through Django's cursor ([Transactions: autocommit, `atomic` and savepoints](transactions.md)):

```text recording=backends
block = transaction.atomic()
block.__enter__()
  SQL BEGIN
  sqlite BEGIN
connection.close()
  DatabaseWrapper.close
    BaseDatabaseWrapper.close
      sqlite3.Connection.close
connection.closed_in_transaction  ->  True
connection.needs_rollback  ->  True
connection.connection is None  ->  False
Ship.objects.count()
  BaseDatabaseWrapper.ensure_connection
  DatabaseWrapper.create_cursor
    sqlite3.Connection.cursor
    raises sqlite3.ProgrammingError
raises ProgrammingError: Cannot operate on a closed database.
block.__exit__(None, None, None)
  Atomic.__exit__
connection.connection is None  ->  True
connection.in_atomic_block  ->  False
```

Inside a block `close` closes the driver's connection but does not forget it: it sets `BaseDatabaseWrapper.closed_in_transaction` and `BaseDatabaseWrapper.needs_rollback`, and leaves the closed driver's connection in `connection`. `BaseDatabaseWrapper.ensure_connection` therefore finds a connection and opens no other, and the next query fails on the closed connection. Opening another would reset the state of the block still open. The block waits instead: its exits neither commit nor roll back, since, a comment in `Atomic.__exit__` says, the database rolls back by itself. At the outermost block's exit, if the block was entered under autocommit, `connection` is set to `None` and `BaseDatabaseWrapper.in_atomic_block` cleared, and the next query opens a new connection (`django/db/transaction.py:Atomic.__exit__`).

Where it finds no connection while `in_atomic_block` and `closed_in_transaction` are both set, `ensure_connection` refuses outright, with a `ProgrammingError` that says a new connection cannot be opened in an atomic block (`django/db/backends/base/base.py:BaseDatabaseWrapper.ensure_connection`). The base class's `close` keeps the driver's connection, so that refusal is reached where the backend's own close sets `connection` to `None`, as PostgreSQL's `DatabaseWrapper._close` does for a pooled connection (`django/db/backends/postgresql/base.py:DatabaseWrapper._close`), and after a block entered with autocommit already off. Such a block sets `in_atomic_block` itself as it is entered, and its exit, finding the connection closed, sets `connection` to `None` and leaves the flag set (`django/db/transaction.py:Atomic.__enter__`).

## `temporary_connection` and `_nodb_cursor`

`BaseDatabaseWrapper.temporary_connection` gives a cursor, and afterwards closes the connection only if it opened it, to avoid leaving a connection dangling, its docstring says, outside the request cycle (`django/db/backends/base/base.py:BaseDatabaseWrapper.temporary_connection`). Asked once of a closed connection and once of an open one, with the sending of `connection_created` left out:

```text recording=backends
connection.close()
with connection.temporary_connection() as cursor: cursor.execute('SELECT COUNT(*) FROM fleet_port')
  BaseDatabaseWrapper.temporary_connection
    BaseDatabaseWrapper.connect
  SQL SELECT COUNT(*) FROM fleet_port
  BaseDatabaseWrapper.temporary_connection resumes
    BaseDatabaseWrapper.close
connection.connection is None  ->  True
Ship.objects.count()
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
with connection.temporary_connection() as cursor: cursor.execute('SELECT COUNT(*) FROM fleet_port')
  BaseDatabaseWrapper.temporary_connection
  SQL SELECT COUNT(*) FROM fleet_port
  BaseDatabaseWrapper.temporary_connection resumes
connection.connection is None  ->  False
```

`BaseDatabaseWrapper._nodb_cursor` gives a cursor on another connection altogether: a new wrapper of the same class, with the same settings but `"NAME"` set to `None`, under the alias `NO_DB_ALIAS`, closed when the cursor is done (`django/db/backends/base/base.py:BaseDatabaseWrapper._nodb_cursor`). Its docstring gives it to the making and destroying of test databases, where the main database is not needed. PostgreSQL's backend connects to the database `"postgres"` for a name of `None`, and if that fails warns and falls back to the first PostgreSQL database configured (`django/db/backends/postgresql/base.py:DatabaseWrapper._nodb_cursor`) ([PostgreSQL](postgresql.md)); MySQL's connects to no database; SQLite's and Oracle's creation do not use it ([Test databases: `BaseDatabaseCreation`](creation.md)).

## One thread at a time: `validate_thread_sharing`

`BaseDatabaseWrapper.validate_thread_sharing` refuses, with `DatabaseError`, a cursor, a commit, a rollback, a savepoint or a close asked of a connection object on a thread other than the one that made it, unless it is being shared. `connections` gives each thread its own connection for an alias ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)), but a connection object can still be handed to another thread: the connection keeps the identity of the thread that made it, and the check compares the calling thread's with it (`django/db/backends/base/base.py:BaseDatabaseWrapper.validate_thread_sharing`). For a cursor it runs as the cursor is prepared, after `BaseDatabaseWrapper.ensure_connection`, so a thread it refuses may already have opened the connection, as the second thread below opens the main thread's before it is refused. Sharing is counted, under a lock: `BaseDatabaseWrapper.inc_thread_sharing` adds a permission, `BaseDatabaseWrapper.dec_thread_sharing` takes one away, `BaseDatabaseWrapper.allow_thread_sharing` is true while any are given, and taking away one more than was given raises `RuntimeError`. Here main_connection is the connection `"default"` that the main thread made:

```text recording=backends
main_connection.connection is None  ->  True
# on a second thread, which the main thread waits for:
...
  main_connection.allow_thread_sharing  ->  False
  main_connection.cursor()  ->  raises DatabaseError: DatabaseWrapper objects created in a thread can only be used in that same thread. The object with alias 'default' was created in thread id (the main thread) and this is thread id (the second thread).
main_connection.connection is None  ->  False
main_connection.inc_thread_sharing()
# on a second thread, which the main thread waits for:
  main_connection.allow_thread_sharing  ->  True
  main_connection.cursor().execute('SELECT COUNT(*) FROM fleet_ship').fetchone()  ->  (2,)
    SQL SELECT COUNT(*) FROM fleet_ship
main_connection.dec_thread_sharing()
main_connection.allow_thread_sharing  ->  False
main_connection.dec_thread_sharing()  ->  raises RuntimeError: Cannot decrement the thread sharing count below zero.
```

Django's own sharing is for SQLite's database in memory, which closing would destroy. `LiveServerTestCase` hands each connection to such a database to its server's thread with a permission to share it, and takes the permission back when the thread is stopped; the server's threads put the connection in place of their own (`django/test/testcases.py:LiveServerTestCase._start_server_thread`, `django/core/servers/basehttp.py:ThreadedWSGIServer.process_request_thread`). SQLite's `DatabaseWrapper.get_connection_params` turns the driver's own guard off for every connection because, its comment says, the driver's setting cannot be changed once a connection is open; the guarding is left to `allow_thread_sharing` (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_connection_params`).

## Connection pools: PostgreSQL and Oracle

PostgreSQL's backend under psycopg 3, and Oracle's, take their driver's connections from a pool kept for the process when the alias's `"OPTIONS"` has `"pool"` (on PostgreSQL, for any alias but `NO_DB_ALIAS`). Each backend's `pool` property makes the pool the first time it is asked for, and keeps it in a dictionary on the class, so every thread's connection for the alias uses the one pool: PostgreSQL's keyed by the alias, Oracle's by the alias and the user (`django/db/backends/postgresql/base.py:DatabaseWrapper.pool`, `django/db/backends/oracle/base.py:DatabaseWrapper.pool`).

With a pool, opening and closing become taking and giving back. The backend's `DatabaseWrapper.get_new_connection` takes a connection from the pool, PostgreSQL's opening the pool first if nothing has, and `BaseDatabaseWrapper.connect` takes all its other steps, `connection_created` among them, each time a connection is taken, whether the pool opened it then or long before. PostgreSQL's `DatabaseWrapper._close` gives the connection back to the pool and sets `connection` to `None` itself (`django/db/backends/postgresql/base.py:DatabaseWrapper._close`). Oracle's has no `_close` of its own, and `BaseDatabaseWrapper._close` closes the connection the pool handed out. PostgreSQL's `DatabaseWrapper.init_connection_state` sets no time zone or role under a pool, because, a comment says, the pool itself calls `DatabaseWrapper._configure_connection` after it opens a connection (`django/db/backends/postgresql/base.py:DatabaseWrapper.init_connection_state`, `django/db/backends/postgresql/base.py:DatabaseWrapper._configure_connection`).

The rest of a pooled connection's health is the pool's. Both backends' `DatabaseWrapper.close_if_health_check_failed` return at once under a pool, their comment saying that the pool only returns healthy connections (`django/db/backends/oracle/base.py:DatabaseWrapper.close_if_health_check_failed`); PostgreSQL's gives the pool its own check where `"CONN_HEALTH_CHECKS"` is on and the options name none. Both `pool` properties refuse, with `ImproperlyConfigured`, a `"CONN_MAX_AGE"` other than 0, `None` included; at 0, `close_old_connections` gives a pooled connection back as each request ends. PostgreSQL's backend also refuses a pool under psycopg2, in its `DatabaseWrapper.get_connection_params` (`django/db/backends/postgresql/base.py:DatabaseWrapper.get_connection_params`), and without the package psycopg_pool, when the pool is made.

`close_pool`, which those two backends alone define, closes the pool and forgets it, so that the next `pool` makes another (`django/db/backends/postgresql/base.py:DatabaseWrapper.close_pool`). Nothing in a request calls it. The test databases' creation does, before it copies or destroys a database ([Test databases: `BaseDatabaseCreation`](creation.md)), and so does PostgreSQL's `ensure_timezone`, which the test framework calls when a time zone setting changes, so that, its comment says, new connections pick up the right zone. Otherwise a pool lasts as long as the process.
