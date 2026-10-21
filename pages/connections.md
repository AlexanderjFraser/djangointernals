---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The database
contents: aliases, opening, cursors, atomic, on-commit, routers
---

# Connections and transactions

Django holds a database as a connection object for each alias of `DATABASES` in each thread, opened when it is first needed and kept or closed at each request's end; the statements of the compiler and of the schema editor pass through Django's cursor, and under autocommit every write is its own transaction unless an atomic block makes it part of one.

Everything above this chapter asks for rows and hands down statements; something has to hold the database open for it. A connection to a database is costly to open and can die while it is held. It carries the state of a transaction, which a second thread must not commit or roll back by accident. A statement on its way to the driver has to pass checks and translations that the driver knows nothing of. And code that writes several rows wants them written together or not at all, at any depth of calls, without each caller knowing whether a caller above it has already begun a transaction. Django's answer is one object, and most of what this chapter tells is state on that object and the moments it changes: whether the driver's connection behind the object is open, what a statement passes through on its way down, which transaction the object is in, and what waits for that transaction to commit.

The examples are harbour's, whose models [Models and fields](models.md) lists. The settings name two databases, `"default"` and `"archive"`, both SQLite files, with a router of the project's that sends the office's logbooks to `"archive"`; `USE_TZ` is on and `TIME_ZONE` is Oslo's. The recording was made from a running Django. A line at the left is a line of Python as it was run; the lines set in under it are the calls it set going, nested as they were made, with only the calls the passage is about written down; `->` is what a call returned. A method is written by the class that declares it, and a backend's class written without its module, DatabaseWrapper, is SQLite's; a call written `sqlite3.connect` or `sqlite3.Cursor.execute` is the driver's own. A line `SQL` is a statement as Django handed it to its cursor, with Django's `"%s"` for each parameter, and a line that begins sqlite is the statement as SQLite ran it, with the parameters bound in. A line of three dots stands for lines of the block left out.

## A connection for each alias, in each thread

The setting `DATABASES` gives each database an **alias**, `"default"` and any others; the word has a second sense, a table's name in a statement, which is the query's ([Building a query](query.md)). The ORM reaches a database through `django.db.connections`, an instance of `ConnectionHandler`: a mapping from an alias to a **connection**, an instance of the backend's `DatabaseWrapper`, such as SQLite's (`django/db/utils.py:ConnectionHandler`, `django/db/backends/sqlite3/base.py:DatabaseWrapper`). It fills in the defaults of every alias's settings when it first reads `DATABASES`, makes a connection the first time an alias is asked for, and keeps what it made in storage local to the thread, so that two threads asking for `"default"` are given two connections (`django/utils/connection.py:BaseConnectionHandler.__getitem__`). Making a connection opens nothing. `django.db.connection`, the name much code reaches for, is a proxy that looks up `connections["default"]` each time it is used (`django/utils/connection.py:ConnectionProxy`) ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections/aliases.md)). Which alias a query goes to is chosen before the connection is reached, by the code that makes the query or by the router ([Routing between databases: `ConnectionRouter`](connections/routers.md)).

A connection is a `BaseDatabaseWrapper` underneath, and most of what it does is inherited from that class: it opens the driver's connection when something first needs it, makes cursors, keeps the state of the transaction, commits, rolls back and closes (`django/db/backends/base/base.py:BaseDatabaseWrapper`). The **driver's connection**, the driver's object that the backend's `get_new_connection` returned, is held as the connection's attribute `connection`, and is `None` until the connection is opened. `BaseDatabaseWrapper.__init__` sets the rest of the connection's state on the instance in groups, and the table names the page that tells each:

| what it serves | attributes | told in |
|---|---|---|
| the driver's connection | `connection`, `None` until it is first needed (`django/db/backends/base/base.py:BaseDatabaseWrapper.ensure_connection`); `settings_dict`; `alias` | [Opening and closing a connection](connections/opening.md) |
| the query log | `queries_log`, which keeps at most `queries_limit` entries; `force_debug_cursor` | [Cursors: executing a statement, the query log and execute wrappers](connections/cursors.md) |
| the transaction | `autocommit`, `False` as PEP 249 has a new connection; `in_atomic_block`, `savepoint_state`, `savepoint_ids`, `atomic_blocks`, `commit_on_exit`, `needs_rollback`, `rollback_exc` | [Transactions: autocommit, `atomic` and savepoints](connections/atomic.md) |
| when to close | `close_at`, `closed_in_transaction`, `errors_occurred`, `health_check_enabled`, `health_check_done` | [Opening and closing a connection](connections/opening.md) |
| threads | the identity of the thread that made the connection, and a count, kept under a lock, of the permissions to share it | [Connections by alias: `DATABASES` and `ConnectionHandler`](connections/aliases.md) |
| work held until the commit | `run_on_commit`, `run_commit_hooks_on_set_autocommit_on` | [Work held until the commit: `on_commit`](connections/on-commit.md) |
| execute wrappers | `execute_wrappers` | [Cursors: executing a statement, the query log and execute wrappers](connections/cursors.md) |
| the helper objects | `client`, `creation`, `features`, `introspection`, `ops`, `validation` | the table in [Database backends](backends.md#what-a-backend-provides) |

*The attributes `BaseDatabaseWrapper.__init__` sets, grouped by what they serve (`django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`). The connection's time zone is worked out from the settings when it is first asked for ([Values in and out: adapters, converters and time zones](backends/values.md)).*

## A statement on its way down

A **cursor**, in this chapter, is what `BaseDatabaseWrapper.cursor` returns: Django's `CursorWrapper` around the **driver's cursor** (`django/db/backends/utils.py:CursorWrapper`). The statements of the compiler and of the schema editor go through one; a backend sends a few of its own straight to the driver while it sets a connection up, and a commit or a rollback is a call on the driver's connection, not a statement. Django's cursor refuses a statement while the transaction is broken, passes it through any execute wrappers that have been installed, and turns an exception of one of the driver's error classes, or of a subclass of one, into Django's class of that class's name, so that code above the backend catches `IntegrityError` from `django.db` and not the driver's own (`django/db/utils.py:DatabaseErrorWrapper`). The figure draws the layers a statement passes through.

```text figure=a-connection
the ORM: a statement with "%s" for each parameter, and Python values
        |
        v
django.db.connections   a ConnectionHandler: a connection per alias, per thread, made on first use
        |
        |  ["default"]
        v
the connection: the backend's DatabaseWrapper (BaseDatabaseWrapper underneath)
        .ops .features .introspection .creation .client .validation   made with the connection
        .connection   the driver's connection: None until something first needs it
        |
        |  cursor()
        v
Django's cursor: CursorWrapper   refuses a statement in a broken transaction; execute wrappers; errors translated
        |
        v
the backend's own cursor class, where it has one   on SQLite and Oracle, Django's "%s" rewritten as the driver's placeholders
        |
        v
the driver's cursor   its own placeholders
        |
        v
the database
```

*A connection from the outside in. Below Django's cursor, each backend has a cursor class of its own, PostgreSQL's only under psycopg 3, and SQLite's and Oracle's rewrite the placeholders there; below that are the driver and the database.*

## One query, in order

The recording begins with a connection not yet opened and a query for the sailors of one ship. The compiler asks the connection for a cursor, and here that is the moment the connection is opened: nothing before it, not making the connection, not building the queryset and not compiling it, touched the database. Look for the driver's connection made inside `connect`, and the cursor wrapped round the driver's once it is open.

```text recording=backends
sailors = list(Sailor.objects.filter(ship__name='Petrel'))
  SQLCompiler.execute_sql
    BaseDatabaseWrapper.cursor
      BaseDatabaseWrapper._cursor
        BaseDatabaseWrapper.close_if_health_check_failed
        BaseDatabaseWrapper.ensure_connection
          BaseDatabaseWrapper.connect
...
            DatabaseWrapper.get_new_connection
              sqlite3.connect(database='harbour.sqlite3', detect_types=3, check_same_thread=False, uri=True)
              ...
              -> the driver's connection
...
            Signal.send  (connection_created, sender=DatabaseWrapper)
        DatabaseWrapper.create_cursor
          sqlite3.Connection.cursor
          -> the driver's cursor, a SQLiteCursorWrapper
        BaseDatabaseWrapper._prepare_cursor
          BaseDatabaseWrapper.validate_thread_sharing
          BaseDatabaseWrapper.make_cursor  ->  a CursorWrapper
          ...
```

`BaseDatabaseWrapper.connect` asks the backend for three things in turn: arguments for the driver's `connect`, the driver's connection, and that connection brought into the state Django expects, autocommit as the alias's `"AUTOCOMMIT"` says and the database's version checked against the oldest the backend supports, once for each alias. Then it sends `connection_created` with the connection, for any receiver that wants to prepare each new connection (`django/db/backends/base/base.py:BaseDatabaseWrapper.connect`). It also works out from `"CONN_MAX_AGE"` when the connection is to be closed. [Opening and closing a connection](connections/opening.md) has each step and the backends' versions of them.

The compiler hands Django's cursor the statement and its parameters; then the recording sends `request_finished`, as the end of a request ordinarily does:

```text recording=backends
    ...
    CursorWrapper.execute
      CursorWrapper._execute_with_wrappers
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE "fleet_ship"."name" = %s with params ('Petrel',)
        CursorWrapper._execute
          SQLiteCursorWrapper.execute
            SQLiteCursorWrapper.convert_query
            sqlite3.Cursor.execute
              sqlite SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE "fleet_ship"."name" = 'Petrel'
...
signals.request_finished.send(sender=WSGIHandler)
  Signal.send  (request_finished, sender=WSGIHandler)
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
        ...
        DatabaseWrapper.close
          ...
          BaseDatabaseWrapper.close
            ...
            BaseDatabaseWrapper._close
              sqlite3.Connection.close
```

The `SQL` line is the statement as it reached Django's cursor; below it, SQLite's backend rewrote each `"%s"` as SQLite's `"?"`, and the driver bound `'Petrel'` in its place ([Cursors: executing a statement, the query log and execute wrappers](connections/cursors.md)). On that signal `close_old_connections`, a receiver connected in `django/db/__init__.py`, asked each connection this thread had made whether it should be closed. `"CONN_MAX_AGE"` is 0 unless the alias says otherwise, so the time to close came as the connection opened, and `BaseDatabaseWrapper.close_if_unusable_or_obsolete` closed it; it is opened again when it is next needed (`django/db/__init__.py:close_old_connections`, `django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete`).

## Transactions

A connection is in **autocommit** unless code asks for more: `connect` sets it as the alias's `"AUTOCOMMIT"` says, which is on unless the alias says otherwise, so that each statement is a transaction of its own, committed by the database as the statement ends (`django/db/backends/base/base.py:BaseDatabaseWrapper.set_autocommit`). `atomic` is how code asks for more. In the plain case, where autocommit is on, the **outermost block**, the atomic block that no other contains, starts a transaction as it is entered, by turning autocommit off (on SQLite the backend sends `"BEGIN"` instead), and as it is left commits the transaction, or rolls it back if an exception is leaving the block or the transaction has been marked for rollback. An atomic block inside another can make a **savepoint** instead, and as it is left release the savepoint or roll back to it, so that an inner block that fails can undo its own work and leave the work of the blocks around it (`django/db/transaction.py:Atomic`).

The state lives on the connection, not on the block: whether an atomic block is open, the stack of savepoint names, the stack of open blocks, and `needs_rollback`, which marks a transaction that must be rolled back before the connection runs another statement (`django/db/backends/base/base.py:BaseDatabaseWrapper.validate_no_broken_transaction`). So a block knows whether it is the outermost by asking the connection, and a function that opens one need not know whether its caller already has ([Transactions: autocommit, `atomic` and savepoints](connections/atomic.md)). A callback registered with `on_commit` in an atomic block is kept on the same connection until the transaction commits, and dropped if its savepoint or the transaction is rolled back ([Work held until the commit: `on_commit`](connections/on-commit.md)).

## The neighbours

The compiler asks a connection for its cursor, and a queryset given no alias asks the router for one ([The SQL compiler](sql.md), [QuerySets](querysets.md)). What differs between one database and another, the connection's helper objects and the four backends Django ships, is [Database backends](backends.md); the schema editor that writes a table, and the test databases made through creation, are [Schemas and test databases](schema.md)'s. The signals of a request's start and end, on which a connection is kept or closed, are sent in the request cycle, and the handler wraps a view in `atomic` where an alias sets `"ATOMIC_REQUESTS"` ([Handlers and middleware](handlers.md)); a connection may not be used from an event loop's thread, which the asynchronous methods of a queryset meet ([The asynchronous methods of a queryset](querysets/async.md)).
