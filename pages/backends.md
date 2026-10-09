---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: connections, wrapper, lifecycle, cursors, transactions, on-commit, routers, features, operations, values, inserts, column-types, introspection, schema, alter-field, creation, sqlite, postgresql, mysql, oracle
---

# Database backends

A **backend** is the package that stands between the ORM and one kind of database. Its class of connection, built on `BaseDatabaseWrapper`, is what Django holds to a database, and the objects that connection carries say what the database can do, what SQL it writes, how a value crosses into it and back, and how its schema is read and changed. This chapter is how a connection is made, opened, used and closed, how `atomic` becomes transactions and savepoints, and what SQLite, PostgreSQL, MySQL and Oracle each do their own way.

Everything above this chapter speaks one language. The compiler writes a statement with `"%s"` wherever a parameter goes and hands it over with a list of Python values; a field hands over a Python value and expects one back; a queryset asks for rows. Below it are databases that differ in much of what that language takes for granted: how a name is quoted, how the number of rows is limited, whether a column can be altered in place, whether a table can be created inside a transaction and dropped again by its rollback, whether an insert can hand back the key it made, how a date is stored. Each is reached through a **driver**, a Python module that follows the database API of PEP 249: `sqlite3` from the standard library, `psycopg` (or `psycopg2`, where psycopg 3 is not installed) for PostgreSQL, `MySQLdb` for MySQL and MariaDB, `oracledb` for Oracle. Django leans on that API for the shape of a connection and a cursor and for the names of the error classes a driver defines (`django/db/utils.py:DatabaseErrorWrapper`); the drivers still differ in the placeholders they take and the types they convert.

Django's answer is one package for each kind of database, each providing the same set of classes. The setting `DATABASES` gives each database an **alias**, `"default"` and any others, and names its package in `"ENGINE"`; `load_backend` imports that package's `base` module, and the class it defines as `DatabaseWrapper` is the way in for everything else (`django/db/utils.py:load_backend`, `django/db/backends/sqlite3/base.py:DatabaseWrapper`). The four that Django ships are under `django/db/backends/`, beside `django.db.backends.dummy`, which stands in when no database is configured. A backend from elsewhere is any package whose `base` module defines a `DatabaseWrapper`: that is the one name Django takes from it, and it reaches everything else through that class's attributes (`django/db/utils.py:ConnectionHandler.create_connection`).

## The objects that carry it

The ORM reaches a database through `django.db.connections`, an instance of `ConnectionHandler`: a mapping from an alias to a **connection**, an instance of the backend's `DatabaseWrapper`, such as SQLite's (`django/db/utils.py:ConnectionHandler`, `django/db/backends/sqlite3/base.py:DatabaseWrapper`). It fills in the defaults of every alias's settings when it first reads `DATABASES`, makes a connection the first time an alias is asked for, and keeps what it made in storage local to the thread, so that two threads asking for `"default"` are given two connections; a comment on the class calls connections "truly thread-critical" (`django/utils/connection.py:BaseConnectionHandler.__getitem__`, `django/db/utils.py:ConnectionHandler.thread_critical`). Making a connection opens nothing. `django.db.connection`, the name much code reaches for, is a proxy that looks up `connections["default"]` each time it is used (`django/utils/connection.py:ConnectionProxy`). [Connections by alias: `DATABASES` and `ConnectionHandler`](backends/connections.md) has the mapping, and [Routing between databases: `ConnectionRouter`](backends/routers.md) has how a query chooses an alias when there are several.

A connection is a `BaseDatabaseWrapper` underneath, and most of what it does is inherited from that class: it opens the driver's connection when a cursor or the state of autocommit is first wanted, makes cursors, keeps the state of the transaction, commits, rolls back and closes (`django/db/backends/base/base.py:BaseDatabaseWrapper`). What the backend's `DatabaseWrapper` adds is what only that database knows: how the settings become the driver's arguments, how the driver's connection is opened and a cursor made on it, how autocommit is turned on and off, the column type of each kind of field. The **driver's connection**, the object the driver's `connect` returned, is held as the connection's attribute `connection`, and is `None` until the connection is opened.

The rest of what differs between databases is in helper objects. The backend's `DatabaseWrapper` names their classes as class attributes, and `BaseDatabaseWrapper.__init__` makes one of each for every connection it makes; the schema editor alone is made when it is asked for (`django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`).

| attribute | base class | what it holds |
|---|---|---|
| `ops` | `BaseDatabaseOperations` | the SQL the database writes for what the compiler asks of it, and the adapters and converters of values: [The SQL a backend writes: `BaseDatabaseOperations`](backends/operations.md) |
| `features` | `BaseDatabaseFeatures` | flags that say what the database can do, read by whatever has a choice to make: [What a database can do: `BaseDatabaseFeatures`](backends/features.md) |
| `introspection` | `BaseDatabaseIntrospection` | the tables, columns and constraints read back from the database: [Introspection: reading the schema back](backends/introspection.md) |
| `creation` | `BaseDatabaseCreation` | making and destroying the databases tests run on: [Test databases: `BaseDatabaseCreation`](backends/creation.md) |
| `client` | `BaseDatabaseClient` | the command line that the command dbshell runs |
| `validation` | `BaseDatabaseValidation` | checks of a field's definition against the database |
| `schema_editor()` | `BaseDatabaseSchemaEditor` | creating and changing tables, columns, indexes and constraints: [The schema editor: `BaseDatabaseSchemaEditor`](backends/schema.md) |

*The helper objects of a connection. A backend subclasses the base classes where its database needs it; the client and validation are in [The connection object: `BaseDatabaseWrapper` and what a backend provides](backends/wrapper.md).*

A **cursor**, in this chapter, is what `BaseDatabaseWrapper.cursor` returns: Django's `CursorWrapper` around the **driver's cursor** (`django/db/backends/utils.py:CursorWrapper`). The statements of the compiler and of the schema editor go through one; a backend sends a few of its own straight to the driver while it sets a connection up, and a commit or a rollback is a call on the driver's connection, not a statement. Django's cursor refuses a statement while the transaction is broken, passes it through any execute wrappers that have been installed, and turns an exception of one of the driver's error classes, or of a subclass of one, into Django's class of that class's name, so that code above the backend catches `IntegrityError` from `django.db` and not the driver's own (`django/db/utils.py:DatabaseErrorWrapper`).

```text figure=a-connection
the ORM: a statement with "%s" for each parameter, and Python values
        |
        v
django.db.connections   a ConnectionHandler: one connection per alias, per thread, made on first use
        |
        |  ["default"]
        v
the connection: the backend's DatabaseWrapper (BaseDatabaseWrapper underneath)
        .ops .features .introspection .creation .client .validation   made with the connection
        .schema_editor()                                              made when asked for
        .connection   the driver's connection: None until a cursor, or the state of autocommit, is first wanted
        |
        |  cursor()
        v
Django's cursor: CursorWrapper   refuses a statement in a broken transaction; execute wrappers; errors translated
        |
        v
the backend's own cursor class, where it has one   on SQLite and Oracle, Django's "%s" rewritten as the driver's placeholders
        |
        v
the driver's cursor   (sqlite3, psycopg, MySQLdb, oracledb): its own placeholders, and its own conversions of types
        |
        v
the database
```

*A connection from the outside in. Below Django's cursor, each backend has a cursor class of its own, PostgreSQL's only under psycopg 3, and SQLite's and Oracle's rewrite the placeholders there; below that are the driver and the database.*

## One query, in order

What follows was recorded from a running Django, on SQLite, over the shipping line that [Models and fields](models.md) introduces: ports and ships in the application fleet, sailors in crew, and the office's paperwork in office. The models the queries of this chapter run over:

```python
# harbour/fleet/models.py
class Named(models.Model):
    name = models.CharField(max_length=60)

    class Meta:
        abstract = True
        ordering = ["name"]


class Port(Named):
    country = models.CharField(max_length=40)


class Ship(Named):
    tonnage = models.PositiveIntegerField()
    home = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ships")
    captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")


class Voyage(models.Model):
    ship = models.ForeignKey(Ship, on_delete=models.CASCADE)
    sailed = models.DateField()
    calls = models.ManyToManyField(Port)


# harbour/crew/models.py
class Sailor(models.Model):
    name = models.CharField(max_length=60)
    ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE, related_name="crew")
    signed_on = models.DateTimeField(auto_now_add=True)
```

Left out are the officers and the rest of the crew and the office, which are shown where a section turns on them. The project's settings name two databases, `"default"` and `"archive"`, both SQLite files, with `USE_TZ` on and `TIME_ZONE` set to Oslo's.

In a recording, a line at the left margin is a line of Python as it was run, or, where a quote begins with it, the title of the block; where its value matters it follows `->`, or the word raises and the exception. The lines set in under it are the calls it set going, nested as they were made, with only the calls the passage is about written down, so that everything between two lines ran and is left out. A method is written by the class that declares it, and a backend's class written without its module, DatabaseWrapper or DatabaseOperations, is SQLite's; `->` under a call is what the call returned, and the word resumes marks a generator running again. A call written `sqlite3.Cursor.execute` is the driver's own, written in C. A line `SQL` is a statement as Django handed it to its cursor, with Django's `"%s"` for each parameter and the parameters after it; a line that begins sqlite is the statement as SQLite ran it, with the parameters bound in, and shows too what reached SQLite without passing through Django's cursor. `(on "archive")` marks a call or a statement on a connection other than `"default"`. A thread's number, which differs from run to run, is written as the thread's part, `(the main thread)`, and a savepoint's name, which holds it, as `s(the thread)_x1`. A line of three dots stands for lines of the block left out. A few questions ask through helpers of the recording's own, which Django does not have: full( writes a value whole, sql_for( gives the statement a queryset's compiler writes for a connection, insert_sql( the statements an insert would send, and flags( a feature on each backend in turn. A block that writes SQL for PostgreSQL, MySQL or Oracle ran with their drivers installed and no server, and says in its title which versions of the servers it assumed.

The block starts with a connection not yet opened and a query for the sailors of one ship. Its first part is the cursor the compiler asks for:

```text recording=backends
sailors = list(Sailor.objects.filter(ship__name='Petrel'))
  SQLCompiler.execute_sql
    BaseDatabaseWrapper.cursor
      BaseDatabaseWrapper._cursor
        BaseDatabaseWrapper.close_if_health_check_failed
        BaseDatabaseWrapper.ensure_connection
          BaseDatabaseWrapper.connect
            DatabaseWrapper.get_connection_params  ->  {'database': 'harbour.sqlite3', 'detect_types': 3, 'check_same_thread': False, 'uri': True}
            DatabaseWrapper.get_new_connection
              sqlite3.connect(database='harbour.sqlite3', detect_types=3, check_same_thread=False, uri=True)
              register
                sqlite3.Connection.execute
                  sqlite select sqlite_compileoption_used('ENABLE_MATH_FUNCTIONS')
              sqlite3.Connection.execute
                sqlite PRAGMA foreign_keys = ON
              sqlite3.Connection.execute
                sqlite PRAGMA legacy_alter_table = OFF
              -> the driver's connection
            BaseDatabaseWrapper.set_autocommit(autocommit=True)
              BaseDatabaseWrapper.close_if_health_check_failed
              BaseDatabaseWrapper.ensure_connection
              DatabaseWrapper._set_autocommit(True)
            BaseDatabaseWrapper.init_connection_state
              BaseDatabaseWrapper.check_database_version_supported
                DatabaseWrapper.get_database_version  ->  (3, 50, 4)
            Signal.send  (connection_created, sender=DatabaseWrapper)
        DatabaseWrapper.create_cursor
          sqlite3.Connection.cursor
          -> the driver's cursor, a SQLiteCursorWrapper
        BaseDatabaseWrapper._prepare_cursor
          BaseDatabaseWrapper.validate_thread_sharing
          BaseDatabaseWrapper.make_cursor  ->  a CursorWrapper
      -> a CursorWrapper
```

The compiler asks the connection for a cursor, and here that is the moment the connection is opened: nothing before it, not making the connection, not building the queryset and not compiling it, touched the database; on some backends compiling a query can open the connection first, to learn the server's version (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`). `BaseDatabaseWrapper._cursor` gives a health check its chance first, which does nothing unless the alias has `"CONN_HEALTH_CHECKS"` on, and then calls `ensure_connection`, which finds the driver's connection to be `None` and calls `connect` (`django/db/backends/base/base.py:BaseDatabaseWrapper._cursor`).

`BaseDatabaseWrapper.connect` checks the alias's settings, resets the connection's transaction state, works out from `"CONN_MAX_AGE"` when the connection is to be closed, and then asks the backend for three things in turn: the arguments for the driver's `connect` (`get_connection_params`, here the file's name and the options SQLite's backend always sets), the driver's connection opened with them (`get_new_connection`, which on SQLite registers Django's own functions on the driver's connection and turns SQLite's foreign key checks on), and that connection brought into the state Django expects: autocommit as the alias's `"AUTOCOMMIT"` says, on unless it says otherwise, and the database's version checked against the oldest the backend supports, for each alias until the check has passed once in the process. Then it sends `connection_created` with the connection, for any receiver that wants to prepare each new connection, and empties the connection's list of callbacks held for a commit (`django/db/backends/base/base.py:BaseDatabaseWrapper.connect`). [Opening and closing a connection](backends/lifecycle.md) has each step and the backends' versions of them.

The cursor comes next. `create_cursor` asks the driver's connection for one, and SQLite's backend asks for its own subclass of the driver's cursor, `SQLiteCursorWrapper`; `_prepare_cursor` checks that this thread may use the connection and wraps the driver's cursor in Django's, a `CursorWrapper`, or a `CursorDebugWrapper` that times and logs each statement when the setting DEBUG is on or the connection's `force_debug_cursor` has been set (`django/db/backends/base/base.py:BaseDatabaseWrapper._prepare_cursor`, `django/db/backends/utils.py:CursorDebugWrapper`).

The compiler hands Django's cursor the statement and its parameters, and reads the rows:

```text recording=backends
  CursorWrapper.execute
    CursorWrapper._execute_with_wrappers
      SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE "fleet_ship"."name" = %s with params ('Petrel',)
      CursorWrapper._execute
        SQLiteCursorWrapper.execute
          SQLiteCursorWrapper.convert_query
          sqlite3.Cursor.execute
            sqlite SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE "fleet_ship"."name" = 'Petrel'
  cursor_iter(itersize=100)
    sqlite3.Cursor.fetchmany
      decoder(parse_datetime)'s lambda(b'2011-06-01 08:00:00')
        parse_datetime('2011-06-01 08:00:00')  ->  datetime(2011, 6, 1, 8, 0)
      decoder(parse_datetime)'s lambda(b'2026-04-10 09:00:00')
        parse_datetime('2026-04-10 09:00:00')  ->  datetime(2026, 4, 10, 9, 0)
  cursor_iter resumes
    sqlite3.Cursor.fetchmany
    sqlite3.Cursor.close
SQLCompiler.results_iter
  SQLCompiler.get_converters
    DatabaseOperations.get_db_converters(Col(crew_sailor, crew.Sailor.id))  ->  []
    DatabaseOperations.get_db_converters(Col(crew_sailor, crew.Sailor.name))  ->  []
    DatabaseOperations.get_db_converters(Col(crew_sailor, crew.Sailor.ship))  ->  []
    DatabaseOperations.get_db_converters(Col(crew_sailor, crew.Sailor.signed_on))  ->  [DatabaseOperations.convert_datetimefield_value]
    -> {3: [DatabaseOperations.convert_datetimefield_value]}
SQLCompiler.apply_converters
  DatabaseOperations.convert_datetimefield_value(datetime(2011, 6, 1, 8, 0))  ->  datetime(2011, 6, 1, 8, 0, tzinfo=UTC)
SQLCompiler.apply_converters resumes
```

The `SQL` line stands where it does because the recording's own execute wrapper, outermost of the wrappers that `_execute_with_wrappers` calls, writes it; then `_execute` hands the statement to the driver's cursor, where SQLite's backend rewrites each `"%s"` as SQLite's `"?"`, and the driver binds `'Petrel'` in its place (`django/db/backends/sqlite3/base.py:SQLiteCursorWrapper.convert_query`). [Cursors: executing a statement, the query log and execute wrappers](backends/cursors.md) has the cursor, and [SQLite](backends/sqlite.md) the rewriting.

The rows come back through two kinds of converter: one that SQLite's backend registered with the driver turns the stored text of each sailor's signed_on into a `datetime` with no time zone, and one the operations object names for the column, `DatabaseOperations.convert_datetimefield_value`, makes it aware in the connection's time zone (`django/db/backends/sqlite3/operations.py:DatabaseOperations.convert_datetimefield_value`). [Values in and out: adapters, converters and time zones](backends/values.md) follows a value both ways.

Last, the signal a handler sends when it has finished with a request:

```text recording=backends
signals.request_finished.send(sender=WSGIHandler)
  Signal.send  (request_finished, sender=WSGIHandler)
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
        BaseDatabaseWrapper.get_autocommit
          BaseDatabaseWrapper.ensure_connection
        DatabaseWrapper.close
          BaseDatabaseWrapper.validate_thread_sharing
          BaseDatabaseWrapper.close
            BaseDatabaseWrapper.validate_thread_sharing
            BaseDatabaseWrapper._close
              sqlite3.Connection.close
```

When the handler has finished with the request it sends `request_finished`, and `close_old_connections`, a receiver connected in `django/db/__init__.py`, asks each connection this thread has made whether it should be closed (`django/db/__init__.py:close_old_connections`). `"CONN_MAX_AGE"` is 0 unless the alias says otherwise, so the time to close came as the connection opened, and `BaseDatabaseWrapper.close_if_unusable_or_obsolete` closes it; the next request will open another (`django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete`).

## Transactions

A connection is in **autocommit** unless code asks for more. A comment in the base class gives PEP 249's default as autocommit off, and `connect` sets it as the alias's `"AUTOCOMMIT"` says, which is on unless the alias says otherwise, so that each statement is a transaction of its own, committed by the database as the statement ends (`django/db/backends/base/base.py:BaseDatabaseWrapper.set_autocommit`). `atomic` is how code asks for more. In the plain case, where autocommit is on, the **outermost block**, the atomic block that no other contains, starts a transaction as it is entered, by turning autocommit off (on SQLite the backend sends `"BEGIN"` instead), and as it is left commits the transaction, or rolls it back if an exception is leaving the block or the transaction has been marked for rollback. An atomic block inside another makes a **savepoint** instead, and as it is left releases the savepoint or rolls back to it, so that an inner block that fails undoes its own work and leaves the work of the blocks around it (`django/db/transaction.py:Atomic`). Two blocks, one inside the other, each creating a port, with what the outer and the inner block's entry and exit sent:

```text recording=backends
outer = transaction.atomic()
inner = transaction.atomic()
outer.__enter__()
  Atomic.__enter__
    BaseDatabaseWrapper.set_autocommit(autocommit=False, force_begin_transaction_with_broken_autocommit=True)
      DatabaseWrapper._start_transaction_under_autocommit
        SQL BEGIN
        sqlite BEGIN
Port.objects.create(name='Oban', country='Scotland')
  SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Oban', 'Scotland')
  sqlite INSERT INTO "fleet_port" ("name", "country") VALUES ('Oban', 'Scotland') RETURNING "fleet_port"."id"
inner.__enter__()
  Atomic.__enter__
    BaseDatabaseWrapper.savepoint
      SQL SAVEPOINT "s(the thread)_x1"
      sqlite SAVEPOINT "s(the thread)_x1"
      -> 's(the thread)_x1'
Port.objects.create(name='Ayr', country='Scotland')
  SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Ayr', 'Scotland')
  sqlite INSERT INTO "fleet_port" ("name", "country") VALUES ('Ayr', 'Scotland') RETURNING "fleet_port"."id"
inner.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.savepoint_commit('s(the thread)_x1')
      SQL RELEASE SAVEPOINT "s(the thread)_x1"
      sqlite RELEASE SAVEPOINT "s(the thread)_x1"
outer.__exit__(None, None, None)
  Atomic.__exit__
    BaseDatabaseWrapper.commit
      BaseDatabaseWrapper._commit
        sqlite3.Connection.commit
          sqlite COMMIT
    BaseDatabaseWrapper.set_autocommit(autocommit=True)
      DatabaseWrapper._set_autocommit(True)
connection.get_autocommit()  ->  True
```

The state lives on the connection, not on the block: whether an atomic block is open, the stack of savepoint names, the stack of open blocks, and `needs_rollback`, which marks a transaction that must be rolled back before the connection runs another statement (`django/db/backends/base/base.py:BaseDatabaseWrapper.validate_no_broken_transaction`). [Transactions: autocommit, `atomic` and savepoints](backends/transactions.md) has every branch of the entry and the exit, every way the mark is set, and the cases other than the plain one. A callback registered with `on_commit` is kept on the same connection until the outermost block commits, and dropped if its savepoint or the transaction is rolled back: [Work held until the commit: `on_commit`](backends/on-commit.md).

## What differs between databases, and where it is decided

The base classes hold the plain case, and a backend departs from it in four places. Its connection class has tables of its own: the column type of each kind of field (`data_types`) and the SQL of each comparison (`operators`) (`django/db/backends/sqlite3/base.py:DatabaseWrapper`). The **features** are flags on the connection's `BaseDatabaseWrapper.features` that code above the backend reads before it chooses what to ask for: whether an insert can hand back the key it made, whether a table can be created inside a transaction and dropped again by its rollback, whether `SELECT ... FOR UPDATE` takes `"NOWAIT"` (`django/db/backends/base/features.py:BaseDatabaseFeatures`). The **operations object** writes most of the fragments of SQL that differ and that something above it asks for by name: a quoted name, a limit, the year of a date, the words that ignore a conflict; it also adapts values on their way in and names the converters for their way out (`django/db/backends/base/operations.py:BaseDatabaseOperations`). And where a fragment is not enough, the backend's own classes override methods of the base classes: SQLite's schema editor builds a table again to make most changes to one of its columns, MySQL has compilers of its own for `"UPDATE"` and `"DELETE"`, Oracle's cursor rewrites Django's placeholders as its own.

Here is one queryset compiled for the four backends by their own compilers. The drivers of PostgreSQL, MySQL and Oracle were installed and their servers never ran, so nothing was sent:

```text recording=backends
voyages = Voyage.objects.filter(sailed__month=3, ship__name__icontains='pet').order_by('-sailed')[:5]
sql_for(voyages, sqlite)  ->  ('SELECT "fleet_voyage"."id", "fleet_voyage"."ship_id", "fleet_voyage"."sailed" FROM "fleet_voyage" INNER JOIN "fleet_ship" ON ("fleet_voyage"."ship_id" = "fleet_ship"."id") WHERE (django_date_extract(%s, "fleet_voyage"."sailed") = %s AND "fleet_ship"."name" LIKE %s ESCAPE \'\\\') ORDER BY "fleet_voyage"."sailed" DESC LIMIT 5', ('month', 3, '%pet%'))
sql_for(voyages, postgresql)  ->  ('SELECT "fleet_voyage"."id", "fleet_voyage"."ship_id", "fleet_voyage"."sailed" FROM "fleet_voyage" INNER JOIN "fleet_ship" ON ("fleet_voyage"."ship_id" = "fleet_ship"."id") WHERE (EXTRACT(MONTH FROM "fleet_voyage"."sailed") = %s AND UPPER("fleet_ship"."name"::text) LIKE UPPER(%s)) ORDER BY "fleet_voyage"."sailed" DESC LIMIT 5', (Int4(3), '%pet%'))
sql_for(voyages, mysql)  ->  ('SELECT `fleet_voyage`.`id`, `fleet_voyage`.`ship_id`, `fleet_voyage`.`sailed` FROM `fleet_voyage` INNER JOIN `fleet_ship` ON (`fleet_voyage`.`ship_id` = `fleet_ship`.`id`) WHERE (EXTRACT(MONTH FROM `fleet_voyage`.`sailed`) = %s AND `fleet_ship`.`name` LIKE %s) ORDER BY `fleet_voyage`.`sailed` DESC LIMIT 5', (3, '%pet%'))
sql_for(voyages, oracle)  ->  ('SELECT "FLEET_VOYAGE"."ID", "FLEET_VOYAGE"."SHIP_ID", "FLEET_VOYAGE"."SAILED" FROM "FLEET_VOYAGE" INNER JOIN "FLEET_SHIP" ON ("FLEET_VOYAGE"."SHIP_ID" = "FLEET_SHIP"."ID") WHERE (EXTRACT(MONTH FROM "FLEET_VOYAGE"."SAILED") = %s AND UPPER("FLEET_SHIP"."NAME") LIKE UPPER(TRANSLATE(%s USING NCHAR_CS)) ESCAPE TRANSLATE(\'\\\' USING NCHAR_CS)) ORDER BY "FLEET_VOYAGE"."SAILED" DESC FETCH FIRST 5 ROWS ONLY', (3, '%pet%'))
```

Each difference is decided in one of those places. The quoting of names is the operations object's `quote_name`: double quotes, MySQL's backticks, and on Oracle double quotes around a name put into capitals, because Oracle keeps a name given without quotes in capitals and the backend's comment chooses to make every name so (`django/db/backends/oracle/operations.py:DatabaseOperations.quote_name`). The month of a date is its `date_extract_sql`: three backends write `"EXTRACT"`, and SQLite calls `"django_date_extract"`, a function that Django's backend registered in SQLite when it opened the connection and that SQLite calls back into Python to compute. The case-insensitive match is the wrapper's `operators` and the operations object's `lookup_cast`, which the lookup asks for: a `"LIKE"` with an escape character on SQLite, both sides in capitals on PostgreSQL and Oracle, and on MySQL a plain `"LIKE"`, MySQL's case-sensitive match being the one that is written differently (`django/db/backends/mysql/base.py:DatabaseWrapper`). The limit is `limit_offset_sql`, `"LIMIT"` on three and `"FETCH FIRST"` on Oracle. [The SQL a backend writes: `BaseDatabaseOperations`](backends/operations.md) has the rest, and an insert, which differs more still, is in [Inserts: returned keys, conflicts and batch sizes](backends/inserts.md).

Each of the four backends has a section of its own for what only it does. [SQLite](backends/sqlite.md) is a library in the same process, with functions Django adds to it from Python and a table built again where another database would alter a column. [PostgreSQL](backends/postgresql.md) is reached through psycopg 3 or psycopg2, and under psycopg 3 can keep a pool of connections and bind parameters on the server; a queryset's `iterator` reads through a cursor named on the server, unless the alias sets `"DISABLE_SERVER_SIDE_CURSORS"`. [MySQL and MariaDB](backends/mysql.md) are one backend for two databases, which asks the server which of the two it is and of what version. [Oracle](backends/oracle.md) stores an empty string as null, shortens a name it quotes to thirty characters, and rewrites Django's placeholders as its own before the driver sees a statement.

## Where it meets its neighbours

The compiler is this chapter's main client: it asks the connection for the operations object, the features and a cursor, and hands its statement down ([From QuerySet to SQL](sql.md), and its section [The compiler: `as_sql`, `execute_sql` and `results_iter`](sql/compiler.md)). Fields meet the backend at their edges: a field's column type comes from the wrapper's `data_types` ([Column types: from a field to a column](backends/column-types.md)), and its values are adapted and converted by the operations object ([Models and fields](models.md) has the field's side). A queryset chooses its alias by asking the router, and its asynchronous methods reach a connection from a thread of their own ([QuerySets](querysets.md), and [The asynchronous methods of a queryset](querysets/async.md)). The handler sends the signals that open and close each request's use of a connection, and wraps a view in `atomic` where an alias sets `"ATOMIC_REQUESTS"` ([Handlers and middleware](handlers.md)). Migrations change the schema through the schema editor and read it back through introspection ([Migrations](migrations.md)); the test runner makes its databases through creation ([The test framework](testing.md)); and dbshell, inspectdb and flush are commands over the client, introspection and the operations object ([Management commands](commands.md)).
