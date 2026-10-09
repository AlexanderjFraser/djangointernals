---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The connection object: `BaseDatabaseWrapper` and what a backend provides

A backend is a package whose `base` module defines a class named `DatabaseWrapper`, a subclass of `BaseDatabaseWrapper` that names the driver, where it has one, and the classes of the connection's helper objects (`django/db/backends/sqlite3/base.py:DatabaseWrapper`). `BaseDatabaseWrapper.__init__` gives each connection its state and its own helpers, among them the client that the command dbshell runs and the validation of fields against a database, and the class declares the methods that switch foreign key checks off and on.

Django asks a backend for one thing, its `DatabaseWrapper`, by name, and reaches everything else from that class (`django/db/utils.py:ConnectionHandler.create_connection`, `django/db/utils.py:load_backend`) ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)). Each of the four backends Django ships keeps its helpers in modules of their own, `operations`, `features` and so on, but `"ENGINE"` leads Django to the `base` module alone, and the helpers' modules are found because `base` imports their classes and names them in class attributes. So one backend can be built on another by subclassing its wrapper, as the backends of `django.contrib.gis` do: PostGIS's `DatabaseWrapper` is PostgreSQL's with its own schema editor, features, operations and introspection named in those attributes (`django/contrib/gis/db/backends/postgis/base.py:DatabaseWrapper`). The smallest backend is the dummy, which stands in when no database is configured (`django/db/backends/dummy/base.py:DatabaseWrapper`) ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)).

## What a backend's class declares

A backend's `DatabaseWrapper` is mostly class attributes. In a recording from a running Django, each line under the title but the first, which closes the connection and so leaves the driver's connection `None`, is a question put to the connection `"default"`, SQLite's, and its answer after `->`, and full( is the recording's own helper for writing a value whole (`django/db/backends/sqlite3/base.py:DatabaseWrapper`):

```text recording=backends
What a connection carries: its class, the backend's names for itself, the driver, and the helper objects it made
    connection.close()
    type(connections['default'])  ->  django.db.backends.sqlite3.base.DatabaseWrapper
    connection.vendor  ->  'sqlite'
    connection.display_name  ->  'SQLite'
    connection.Database  ->  the module sqlite3.dbapi2
    connection.SchemaEditorClass  ->  django.db.backends.sqlite3.schema.DatabaseSchemaEditor
    type(connection.ops)  ->  django.db.backends.sqlite3.operations.DatabaseOperations
    type(connection.features)  ->  django.db.backends.sqlite3.features.DatabaseFeatures
    type(connection.introspection)  ->  django.db.backends.sqlite3.introspection.DatabaseIntrospection
    type(connection.creation)  ->  django.db.backends.sqlite3.creation.DatabaseCreation
    type(connection.client)  ->  django.db.backends.sqlite3.client.DatabaseClient
    type(connection.validation)  ->  django.db.backends.base.validation.BaseDatabaseValidation
    connection.ops.connection is connections['default']  ->  True
    connection.connection  ->  None
    full(list(connection.settings_dict))  ->  ['ENGINE', 'NAME', 'ATOMIC_REQUESTS', 'AUTOCOMMIT', 'CONN_MAX_AGE', 'CONN_HEALTH_CHECKS', 'OPTIONS', 'TIME_ZONE', 'USER', 'PASSWORD', 'HOST', 'PORT', 'TEST']
    connection.settings_dict['NAME']  ->  'harbour.sqlite3'
```

| attribute | what it holds | what reads it |
|---|---|---|
| `BaseDatabaseWrapper.vendor` | a short name: `"sqlite"`, `"postgresql"`, `"mysql"` or `"oracle"`, and `"unknown"` on the base class | `SQLCompiler.compile`, which looks on each node for a method named `"as_"` and the vendor; `django/db/models/options.py:Options.can_migrate`, for a model whose `required_db_vendor` names one; code that branches on the database by name, as the JSON field and its lookups do (`django/db/models/fields/json.py`) |
| `BaseDatabaseWrapper.display_name` | the database's name in messages; MySQL's is a cached property that asks the server, and is `"MariaDB"` or `"MySQL"` | the refusal of a server too old; the system checks of fields, constraints and comments; the operations object's refusals |
| `Database` (`django/db/backends/sqlite3/base.py:DatabaseWrapper.Database`) | the driver's module | `DatabaseErrorWrapper`, which looks up on it the driver's exception of the same name as each of Django's ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)); `django/db/backends/utils.py:CursorWrapper.__exit__`, for the driver's base class of errors; `BinaryField.get_db_prep_value`, for the driver's constructor of binary values |
| `BaseDatabaseWrapper.SchemaEditorClass` | the schema editor's class | `BaseDatabaseWrapper.schema_editor`, which refuses with `NotImplementedError` while it is `None` |
| `BaseDatabaseWrapper.client_class` and its siblings, one for each helper | the classes of the helper objects; `BaseDatabaseWrapper.validation_class` is `BaseDatabaseValidation` unless a backend names another | `BaseDatabaseWrapper.__init__` |
| `BaseDatabaseWrapper.data_types`, `BaseDatabaseWrapper.data_types_suffix`, `BaseDatabaseWrapper.data_type_check_constraints` | each field class's column type, the SQL after it, and its check | the fields and the schema editor: [Column types: from a field to a column](column-types.md) |
| `operators`, `pattern_esc`, `pattern_ops` (`django/db/backends/sqlite3/base.py:DatabaseWrapper.operators`) | the SQL of each comparison | the lookups: [The SQL a backend writes: `BaseDatabaseOperations`](operations.md) |
| `BaseDatabaseWrapper.queries_limit` | how many statements the query log keeps | [Cursors: executing a statement, the query log and execute wrappers](cursors.md) |

*What a backend's connection class declares, and what reads each. The base class declares all of them but the driver's module and the comparisons, which are the backends' own.*

The base class leaves to the backend what only the backend can know, and raises `NotImplementedError` from each such method: `BaseDatabaseWrapper.get_connection_params`, `BaseDatabaseWrapper.get_new_connection`, `BaseDatabaseWrapper.is_usable` and `BaseDatabaseWrapper.get_database_version`, which [Opening and closing a connection](lifecycle.md) tells with each backend's; `BaseDatabaseWrapper.create_cursor`, in [Cursors: executing a statement, the query log and execute wrappers](cursors.md); and `BaseDatabaseWrapper._set_autocommit`, in [Transactions: autocommit, `atomic` and savepoints](transactions.md). Other methods are hooks that do nothing until a backend fills them. `BaseDatabaseWrapper.prepare_database` is one: migrate calls it on its connection before it works out what to migrate, and PostGIS's creates the extension `"postgis"` there where it is missing (`django/core/management/commands/migrate.py:Command.handle`, `django/contrib/gis/db/backends/postgis/base.py:DatabaseWrapper.prepare_database`). The methods that turn foreign key checks off and on are others.

## The helper objects

`BaseDatabaseWrapper.__init__` ends by making the helpers, each by calling its class with the connection (`django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`). Every connection object has its own: two threads' connections for one alias share no helper, and a feature that is a cached property, worked out by asking the server, is worked out once for each connection object ([What a database can do: `BaseDatabaseFeatures`](features.md)). The schema editor is not among them; `BaseDatabaseWrapper.schema_editor` makes a new one each time it is called ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)).

Each helper keeps the connection it was given as its attribute `connection`, as the recording's line `connection.ops.connection is connections['default']` shows, and reads there what it needs of it: the operations object the time zone and the features, the validation the display name.

A backend that has to adjust a helper does so after the base class's `__init__` has made it. Oracle's `DatabaseWrapper.__init__` sets two features, whether an insert can hand back columns and an update rows, from the option `"use_returning_into"` (`django/db/backends/oracle/base.py:DatabaseWrapper.__init__`).

## The state of one connection

`BaseDatabaseWrapper.__init__` takes the alias's settings and the alias, opens nothing, and sets the rest of the connection's state on the instance in groups, most of them under a comment of their own:

| what it serves | attributes | told in |
|---|---|---|
| the driver's connection | `connection`, `None` until it is first needed (`django/db/backends/base/base.py:BaseDatabaseWrapper.ensure_connection`); `settings_dict`; `alias` | [Opening and closing a connection](lifecycle.md) |
| the query log | `queries_log`, which keeps at most `queries_limit` entries; `force_debug_cursor` | [Cursors: executing a statement, the query log and execute wrappers](cursors.md) |
| the transaction | `autocommit`, `False` as PEP 249 has a new connection; `in_atomic_block`, `savepoint_state`, `savepoint_ids`, `atomic_blocks`, `commit_on_exit`, `needs_rollback`, `rollback_exc` | [Transactions: autocommit, `atomic` and savepoints](transactions.md) |
| when to close | `close_at`, `closed_in_transaction`, `errors_occurred`, `health_check_enabled`, `health_check_done` | [Opening and closing a connection](lifecycle.md) |
| threads | the identity of the thread that made the connection, and a count, kept under a lock, of the permissions to share it | [Opening and closing a connection](lifecycle.md) |
| work held until the commit | `run_on_commit`, `run_commit_hooks_on_set_autocommit_on` | [Work held until the commit: `on_commit`](on-commit.md) |
| execute wrappers | `execute_wrappers` | [Cursors: executing a statement, the query log and execute wrappers](cursors.md) |
| the helper objects | `client`, `creation`, `features`, `introspection`, `ops`, `validation` | the table in [Database backends](../backends.md#the-objects-that-carry-it) |

*The attributes `BaseDatabaseWrapper.__init__` sets, grouped by what they serve. The connection's time zone is worked out from the settings when it is first asked for ([Values in and out: adapters, converters and time zones](values.md)).*

The settings dictionary is the connection handler's own for the alias, and not a copy, so every thread's connection for an alias holds the same one (`django/db/utils.py:ConnectionHandler.create_connection`) ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)). `BaseDatabaseWrapper.copy` makes a second connection to the same database: a wrapper of the same class with a deep copy of the settings, under the same alias unless it is given another, registered nowhere: `connections` never hands it out (`django/db/backends/base/base.py:BaseDatabaseWrapper.copy`). It is for tests that need two connections to one database, and nothing in Django calls it but Django's own test suite.

## The client: dbshell

The command dbshell runs the database's own command-line program, connected as the alias's settings say. It calls `BaseDatabaseClient.runshell` on the client of the connection its `"--database"` option names, with the arguments given after it on the command line (`django/core/management/commands/dbshell.py:Command.handle`). `runshell` asks the class method `BaseDatabaseClient.settings_to_cmd_args_env` for the program's arguments and an environment, sets that environment over the process's own where there is one, and runs the program with `subprocess.run`, raising if it exits with a failure (`django/db/backends/base/client.py:BaseDatabaseClient.runshell`). The base class's class method raises `NotImplementedError` with a message that gives a backend its choice: provide the class method, or override `runshell`. The command turns two failures into a `CommandError`: `FileNotFoundError`, which it takes to mean that the program named by `BaseDatabaseClient.executable_name` is not installed, and the program's exit with a failure, which it reports with the command line and passes on as its own status.

| backend | the program and its arguments | the password |
|---|---|---|
| SQLite (`django/db/backends/sqlite3/client.py:DatabaseClient`) | `"sqlite3"` with the file's name, then the arguments given | none: a file has none |
| PostgreSQL (`django/db/backends/postgresql/client.py:DatabaseClient`) | `"psql"` with the user, host and port as flags, the arguments given, and last the database, `"postgres"` where neither `"NAME"` nor the option `"service"` names one | in the environment, as `"PGPASSWORD"`, with the options for a service, a password file and SSL |
| MySQL and MariaDB (`django/db/backends/mysql/client.py:DatabaseClient`) | `"mysql"` with a defaults file, the user, the host or a socket, the port, the SSL files and the character set as flags, then the database, then the arguments given; the user, password, host, port and database taken from `"OPTIONS"` before the settings | in the environment, as `"MYSQL_PWD"` |
| Oracle (`django/db/backends/oracle/client.py:DatabaseClient`) | `"sqlplus"` and `"-L"` with one connect string of the user, the password in double quotes and the address from `dsn`, then the arguments given; `"rlwrap"` in front where it is on the path | among the arguments |

*What each backend's client runs. PostgreSQL's and MySQL's `runshell` also make Django's process ignore an interrupt while the program runs, which, their comment says, lets the interrupt pass to the program to stop a query.*

MySQL's client gives its reason for the environment in a comment: MySQL's documentation discourages the variable, since on old Unix systems the command ps can show it, but a password among the arguments is exposed on more systems, and the environment keeps it out of the `subprocess.CalledProcessError` raised when the program fails, whose text holds every argument (`django/db/backends/mysql/client.py:DatabaseClient.settings_to_cmd_args_env`). Oracle's client puts the password among the arguments, and dbshell's message for a program that failed is built from them.

## Validation: `check_field` and the database checks

A connection's validation object is how a backend adds its own warnings to the system checks, through two methods of `BaseDatabaseValidation`. `BaseDatabaseValidation.check` returns no messages in the base class, and is called for each alias by `check_database_backends`, a check registered under the tag for databases (`django/core/checks/database.py:check_database_backends`). A run of the checks that names neither aliases nor tags leaves such checks out, because, a comment says, they do more than read the code (`django/core/checks/registry.py:CheckRegistry.run_checks`); they run under check given its `"--database"` option or that tag, under migrate for its alias, and under the test runner ([The system checks](../commands/checks.md)).

`BaseDatabaseValidation.check_field` is called by the checks of fields, which are not under the tag for databases, so a run that names neither aliases nor tags calls it too, for each field and every alias, where the router allows the field's model to be migrated there (`django/db/models/fields/__init__.py:Field._check_backend_specific_checks`) ([The model checks](../models/checks.md)). It does nothing unless the backend's validation defines `check_field_type`, which it hands the field and its column type on this connection, passing over related fields and a few others (`django/db/backends/base/validation.py:BaseDatabaseValidation.check_field`). SQLite's and PostgreSQL's wrappers name no validation class, so theirs is the base class, as the recording shows for SQLite.

MySQL's validation has both methods (`django/db/backends/mysql/validation.py:DatabaseValidation`). Its `check` warns, as `"mysql.W002"`, when neither of MySQL's strict modes is among the server's SQL modes, which it learns by asking the server; its `check_field_type` warns, as `"mysql.W003"`, of a unique field whose column is a `"varchar"` longer than 255 characters or of no stated length, and, as `"fields.W162"`, of an indexed field whose column is of a type MySQL cannot index in full, a text, a blob or JSON. Oracle's has the last alone, for its large objects (`django/db/backends/oracle/validation.py:DatabaseValidation.check_field_type`). Both take the types from the wrapper's `_limited_data_types` (`django/db/backends/mysql/base.py:DatabaseWrapper._limited_data_types`, `django/db/backends/oracle/base.py:DatabaseWrapper._limited_data_types`); the warning's hint says the index will not be created, and each backend's schema editor reads the same attribute to leave it out.

## Foreign key checks switched off: `constraint_checks_disabled`

Some writes put rows in an order the database's foreign keys would refuse: a fixture whose rows refer forward to rows later in the file, or a cycle of references. `BaseDatabaseWrapper.constraint_checks_disabled` is a context manager for them. It calls `BaseDatabaseWrapper.disable_constraint_checking`, and on leaving calls `BaseDatabaseWrapper.enable_constraint_checking` only if the first returned true, which the base class's docstring asks a backend to return only when the checks were turned off and need turning on again (`django/db/backends/base/base.py:BaseDatabaseWrapper.constraint_checks_disabled`). Its callers then check what was written meanwhile with `BaseDatabaseWrapper.check_constraints`, which is to raise `IntegrityError` for a row that refers to nothing.

| backend | turning off | turning on | checking |
|---|---|---|---|
| the base class | does nothing; false | does nothing | does nothing |
| SQLite (`django/db/backends/sqlite3/base.py:DatabaseWrapper`) | `"PRAGMA foreign_keys = OFF"`, then reads the pragma back: true only if the checks are off; inside a transaction the pragma cannot turn them off | `"PRAGMA foreign_keys = ON"` | `"PRAGMA foreign_key_check"`, of the tables named or of all; the first row found raises, naming its table, key and value |
| PostgreSQL (`django/db/backends/postgresql/base.py:DatabaseWrapper`) | the base class's | the base class's | `"SET CONSTRAINTS ALL IMMEDIATE"`, then `"SET CONSTRAINTS ALL DEFERRED"` |
| MySQL (`django/db/backends/mysql/base.py:DatabaseWrapper`) | `"SET foreign_key_checks=0"`; always true | `"SET foreign_key_checks=1"`, with `needs_rollback` cleared while it runs | for each foreign key of each table named, or of every table, a join that finds the rows whose reference has no row; the first raises |
| Oracle (`django/db/backends/oracle/base.py:DatabaseWrapper`) | the base class's | the base class's | as PostgreSQL's |

*How each backend turns foreign key checks off, in `disable_constraint_checking`, and on, in `enable_constraint_checking`, and checks what was written meanwhile, in `check_constraints`.*

The backends differ because their foreign keys do. PostgreSQL's and Oracle's operations objects make each foreign key `"DEFERRABLE INITIALLY DEFERRED"`, and SQLite's schema editor writes its foreign keys so too, so that within a transaction a row may refer to one not yet written and the database checks when the transaction commits (`django/db/backends/postgresql/operations.py:DatabaseOperations.deferrable_sql`, `django/db/backends/oracle/operations.py:DatabaseOperations.deferrable_sql`, `django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.sql_create_inline_fk`); setting the constraints to immediate, as PostgreSQL's and Oracle's `check_constraints` does before setting them back, makes the database check them at once. SQLite's schema editor, some of whose alterations need the checks off, turns them off as it is entered, refusing where they are on inside a transaction, since the pragma cannot turn them off there, and as it is left checks every table and turns them on again (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__enter__`) ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)). MySQL checks its foreign keys as each statement runs, which a comment gives as the reason for turning the checks off where the test databases are filled again (`django/db/backends/base/creation.py:BaseDatabaseCreation.deserialize_db_from_string`). MySQL's `enable_constraint_checking` clears `needs_rollback` while its statement runs, for `constraint_checks_disabled` nested inside `atomic`, its comment says; a cursor refuses every statement while `needs_rollback` is set ([Transactions: autocommit, `atomic` and savepoints](transactions.md)).

The callers pair the three, and both enter `constraint_checks_disabled` inside an atomic block: loaddata loads its fixtures within its own and then checks the tables it wrote to (`django/core/management/commands/loaddata.py:Command.handle`, `django/core/management/commands/loaddata.py:Command.loaddata`), and the test databases are filled again from their serialized rows the same way ([Test databases: `BaseDatabaseCreation`](creation.md)). Inside a transaction only MySQL's checks go off; SQLite's `disable_constraint_checking` asks for the pragma off and reads it back still on, as this recording shows:

```text recording=backends
with transaction.atomic(), connection.constraint_checks_disabled(): Ship.objects.count()
  Atomic.__enter__
    SQL BEGIN
  BaseDatabaseWrapper.constraint_checks_disabled
    DatabaseWrapper.disable_constraint_checking
      SQL PRAGMA foreign_keys = OFF
      SQL PRAGMA foreign_keys
      -> False
```

On the other three the deferred foreign keys let the rows in, and `check_constraints` checks them. `TestCase` calls `check_constraints` as each test ends, before it rolls the test's transaction back, on each database whose features say it can defer checks and whose connection is usable and not marked for rollback (`django/test/testcases.py:TestCase._fixture_teardown`, `django/test/testcases.py:TestCase._should_check_constraints`) ([The test framework](../testing.md)).
