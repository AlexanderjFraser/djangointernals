---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Test databases: `BaseDatabaseCreation`

`BaseDatabaseCreation` is the class of a connection's **creation**, the object that makes the database a test run works in and destroys it afterwards: `BaseDatabaseCreation.create_test_db` and `BaseDatabaseCreation.destroy_test_db`, the copies that parallel test processes work in, the rows kept for a `TransactionTestCase`, and `BaseDatabaseCreation.test_db_signature`, which says whether two aliases are one database.

Tests write to the database, and must not write to the one the settings name. So for each database a project uses, a test run needs another: made empty, given the schema the models need, put where the settings point so that every connection to the alias reaches it, and taken away at the end. Several aliases may be one database; a run in several processes needs a copy for each; and a test that empties the tables after itself takes with it the rows that migrations wrote, which some tests need back. The runner decides which aliases need a database and in what order, and calls each one's creation: `setup_databases` and `teardown_databases` are [The test framework](../testing.md)'s (`django/test/utils.py:setup_databases`). The wrapper makes a creation for each connection from the backend's `BaseDatabaseWrapper.creation_class`, and the creation keeps the connection (`django/db/backends/base/creation.py:BaseDatabaseCreation`).

In the quotes below, recorded from a running Django on SQLite, a line at the margin is a line of Python, with `->` and its value; the lines set in under it are the calls it set going that the passage is about, with `->` what a call returned; and a line beginning `#` counts the statements a line sent.

## Making a test database: `create_test_db`

`BaseDatabaseCreation.create_test_db` takes a verbosity, `autoclobber=False` and `keepdb=False`, and returns the name of the test database (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`). Here it makes one for `"default"`, whose `"TEST"` settings were given a name, a file beside the project's own:

```text recording=backends
connection.settings_dict['TEST']['NAME'] = os.path.join(run_directory, 'test_harbour.sqlite3')
old_name = connection.settings_dict['NAME']
old_name  ->  'harbour.sqlite3'
settings.DATABASES['default'] is connection.settings_dict  ->  True
test_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)
  BaseDatabaseCreation.create_test_db(verbosity=0, autoclobber=True)
    DatabaseCreation._get_test_db_name  ->  'test_harbour.sqlite3'
    DatabaseCreation._create_test_db(verbosity=0, autoclobber=True)
      DatabaseCreation._get_test_db_name  ->  'test_harbour.sqlite3'
      -> 'test_harbour.sqlite3'
    DatabaseWrapper.close
      BaseDatabaseWrapper.close
    call_command('migrate', verbosity=0, interactive=False, database='default', run_syncdb=True)
      BaseDatabaseWrapper.connect
    call_command('createcachetable', database='default')
    -> 'test_harbour.sqlite3'
  # 29 statements were sent while this line ran: none is written
test_name  ->  'test_harbour.sqlite3'
settings.DATABASES['default']['NAME']  ->  'test_harbour.sqlite3'
connection.settings_dict['NAME']  ->  'test_harbour.sqlite3'
os.path.exists(test_name)  ->  True
```

```text figure=create-test-db
create_test_db                       NAME, in DATABASES and on the connection   the connection

1  _get_test_db_name                 the real database's: "harbour.sqlite3"     as it was
   NAME in TEST, or "test_" + NAME
2  _create_test_db
   CREATE DATABASE, on a second connection that has no NAME;
   one already there is kept with keepdb, or dropped and made again with autoclobber or on "yes"
3  close                                                                        closed
4  NAME set to the test name         the test database's, in both places:
                                     "test_harbour.sqlite3"
5  migrate, run_syncdb=True                                                     open, on the test database
   the tables: by the migrations, or from the models
   (MIGRATE False in TEST: every application taken as one without migrations)
6  createcachetable
   the tables of the database caches
7  ensure_connection
   opens it, if nothing has
8  mark_expected_failures_and_skips
   only in Django's own test suite
-> the test name
```

*The steps of `create_test_db` as the base class takes them, with what NAME holds, in `settings.DATABASES` and in the connection's `settings_dict`, and the state of the connection after each.*

**The name.** `BaseDatabaseCreation._get_test_db_name` is the `"TEST"` dictionary's `"NAME"`, or `"test_"` before the alias's `"NAME"` (`django/db/backends/base/creation.py:BaseDatabaseCreation._get_test_db_name`, `django/db/backends/base/creation.py:TEST_DATABASE_PREFIX`). Its docstring warns that it is only useful from `create_test_db` and `BaseDatabaseCreation._create_test_db` and when nothing else changes `"NAME"`; once the test database is made, `"NAME"` is the test database's own. Oracle's backend returns `"NAME"` itself, its docstring saying a database's name as Django handles it has no counterpart in Oracle.

**The database.** `BaseDatabaseCreation._create_test_db` makes the database over a second connection, and keeps one that is already there, replaces it, or ends the run. It asks `BaseDatabaseCreation.sql_table_creation_suffix` for the options of the new database, and has `BaseDatabaseCreation._execute_create_test_db` send `"CREATE DATABASE"` on a cursor of a connection made with no `"NAME"`, which `BaseDatabaseWrapper._nodb_cursor` opens and closes again ([Opening and closing a connection](lifecycle.md)). Where the statement fails and `keepdb=True` was asked, the database is taken to be there and kept. Otherwise, unless `autoclobber=True`, the person running the tests is asked whether to delete the old test database; it is then dropped and made again, and a refusal, or an error in either statement, ends the process (`django/db/backends/base/creation.py:BaseDatabaseCreation._create_test_db`). The runner passes `autoclobber=not interactive`. PostgreSQL's and MySQL's `_execute_create_test_db` let only the error that the database exists through to that question, and end the process at once on any other (`django/db/backends/postgresql/creation.py:DatabaseCreation._execute_create_test_db`). SQLite's makes nothing: it removes an old file, asking as the base class does, and the new file appears when migrate first connects (`django/db/backends/sqlite3/creation.py:DatabaseCreation._create_test_db`).

**The settings.** `"NAME"` is set in two places, in `settings.DATABASES` for the alias and in the connection's `settings_dict`: the connection reads its own dictionary when it opens; other code reads the setting, as Oracle's creation does when it makes its administrative connection (`django/db/backends/oracle/creation.py:DatabaseCreation._maindb_connection`). In this project the two are one dictionary, as the recording shows where it asks whether they are the same object. Both are changed in place and never replaced: a connection that another thread makes later is made from the connection handler's settings ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)), the same dictionaries, and so opens the test database as well (`django/db/utils.py:ConnectionHandler.create_connection`).

**The schema.** `create_test_db` calls the migrate command for the alias with `run_syncdb=True`, which makes the tables of applications without migrations from their models (`django/core/management/commands/migrate.py:Command.sync_apps`). The project's applications have no migrations, and their tables were made so; migrate opened the connection, on the test database. Where the `"TEST"` dictionary's `"MIGRATE"` is `False`, `create_test_db` sets `MIGRATION_MODULES` to `None` for every application while migrate runs, so that every application is made from its models, and puts the setting back after, as this run with `"MIGRATE"` set to `False` shows:

```text recording=backends
settings.MIGRATION_MODULES  ->  {}
test_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)
  BaseDatabaseCreation.create_test_db(verbosity=0, autoclobber=True)
    call_command('migrate', verbosity=0, interactive=False, database='default', run_syncdb=True)  (settings.MIGRATION_MODULES is then {'fleet': None, 'crew': None, 'office': None})
...
settings.MIGRATION_MODULES  ->  {}
```

**The rest.** Then the createcachetable command makes the tables of the database caches that the router lets on this alias ([Caching, files, mail, signals and tasks](../services.md)); `BaseDatabaseWrapper.ensure_connection` opens the connection if nothing has; and where the environment variable `"RUNNING_DJANGOS_TEST_SUITE"` is `"true"`, `BaseDatabaseCreation.mark_expected_failures_and_skips` marks the tests of Django's own suite that this backend's features list ([What a database can do: `BaseDatabaseFeatures`](features.md)).

## Destroying it: `destroy_test_db`

`BaseDatabaseCreation.destroy_test_db` closes the connection, takes the test database's name from `"NAME"`, or from a clone's settings where it is given a suffix, and has `BaseDatabaseCreation._destroy_test_db` remove it unless `keepdb=True`; then, where it is given the old name, it puts that back in both places (`django/db/backends/base/creation.py:BaseDatabaseCreation.destroy_test_db`). The runner destroys each clone by its suffix and then the test database, with the name it kept (`django/test/utils.py:teardown_databases`).

```text recording=backends
connection.creation.destroy_test_db(old_name, verbosity=0)
  BaseDatabaseCreation.destroy_test_db(old_database_name='harbour.sqlite3', verbosity=0)
    DatabaseWrapper.close
      BaseDatabaseWrapper.close
    DatabaseCreation._destroy_test_db(test_database_name='test_harbour.sqlite3', verbosity=0)
  # 0 statements were sent while this line ran: none is written
os.path.exists(test_name)  ->  False
settings.DATABASES['default']['NAME']  ->  'harbour.sqlite3'
connection.settings_dict['NAME']  ->  'harbour.sqlite3'
```

The base `_destroy_test_db` sends `"DROP DATABASE"` on a cursor of a second connection, its comment saying a database cannot be dropped while connected to it (`django/db/backends/base/creation.py:BaseDatabaseCreation._destroy_test_db`). SQLite's removes the file, and does nothing for a database in memory; PostgreSQL's closes the connection's pool first.

## The `"TEST"` settings

`ConnectionHandler.configure_settings` gives each alias a `"TEST"` dictionary and fills in its defaults ([Connections by alias: `DATABASES` and `ConnectionHandler`](connections.md)). The recording's, before its name was set:

```text recording=backends
connection.settings_dict['TEST']  ->  {'CHARSET': None, 'COLLATION': None, 'MIGRATE': True, 'MIRROR': None, 'NAME': None}
```

| key | filled in | what reads it, and what it does |
|---|---|---|
| `"NAME"` | `None` | `BaseDatabaseCreation._get_test_db_name`: the test database's name, in place of `"test_"` and `"NAME"` |
| `"MIGRATE"` | `True` | `BaseDatabaseCreation.create_test_db`: with `False`, the tables are made from the models and no migration runs |
| `"MIRROR"` | `None` | `get_unique_databases_and_mirrors`: another alias whose test database this one uses |
| `"CHARSET"` | `None` | PostgreSQL's and MySQL's `sql_table_creation_suffix`: PostgreSQL's `"ENCODING"`, MySQL's `"CHARACTER SET"` |
| `"COLLATION"` | `None` | the same: MySQL's `"COLLATE"`; PostgreSQL's raises `ImproperlyConfigured`, its message saying PostgreSQL does not support setting a collation when a database is created |
| `"DEPENDENCIES"` | no | `get_unique_databases_and_mirrors`: the aliases whose test databases are made before this one's |
| `"TEMPLATE"` | no | PostgreSQL's suffix: the template the database is made from |

*The keys of a `"TEST"` dictionary read outside Oracle's backend, which reads more, for its test user and tablespaces.*

The base class's suffix is empty, and PostgreSQL's and MySQL's write their options from these keys (`django/db/backends/postgresql/creation.py:DatabaseCreation.sql_table_creation_suffix`, `django/db/backends/mysql/creation.py:DatabaseCreation.sql_table_creation_suffix`). Without `"DEPENDENCIES"`, an alias other than `"default"` whose database differs from `"default"`'s waits for `"default"`; and `"default"` is put first among the aliases of one database, a comment saying data migrations use the default alias (`django/test/utils.py:get_unique_databases_and_mirrors`).

## Which databases to make: `test_db_signature` and mirrors

The runner groups the aliases by `BaseDatabaseCreation.test_db_signature`, a tuple of the settings that say which database an alias reaches: the base class's is the host, the port, the engine and the test database's name (`django/db/backends/base/creation.py:BaseDatabaseCreation.test_db_signature`). For each group the runner calls `BaseDatabaseCreation.create_test_db` on the first alias and `BaseDatabaseCreation.set_as_test_mirror` on the rest, which copies the first one's `"NAME"`; then it does the same for each alias whose `"TEST"` names a `"MIRROR"`, so that a replica in the settings reads the test database of the alias it replicates (`django/test/utils.py:setup_databases`). Oracle's `set_as_test_mirror` copies the user and the password instead (`django/db/backends/oracle/creation.py:DatabaseCreation.set_as_test_mirror`), and Oracle's signature adds the test user. SQLite's signature is the real database's name and the test database's, or the alias in place of the latter where the test database is in memory, its docstring saying that in-memory databases are distinct even with one `"TEST"` name (`django/db/backends/sqlite3/creation.py:DatabaseCreation.test_db_signature`):

```text recording=backends
connection.creation.test_db_signature()  ->  ('harbour.sqlite3', 'default')
connection.settings_dict['TEST']['NAME'] = os.path.join(run_directory, 'test_harbour.sqlite3')
connection.creation.test_db_signature()  ->  ('harbour.sqlite3', 'test_harbour.sqlite3')
```

## Rows kept for a `TransactionTestCase`: `serialize_db_to_string`

A `TestCase` undoes each test by rolling back a transaction where its databases have them; a `TransactionTestCase` does not, and empties the tables after each test with flush instead ([Introspection: reading the schema back](introspection.md)). Flushing takes with it the rows that migrations wrote, and a class that sets `TransactionTestCase.serialized_rollback` has them put back before each of its tests (`django/test/testcases.py:TransactionTestCase._fixture_setup`). A comment in `setup_databases` gives this as the way that tests on databases without transactions, or in a `TransactionTestCase`, still get a clean database for every test. Once all the test databases are made, its comment saying this is to account for mirrors and routing, `setup_databases` serializes each one whose alias is in its argument serialized_aliases, or every one where it is given none, and keeps the text on the connection; the runner names only the aliases that tests setting `serialized_rollback` use (`django/test/runner.py:DiscoverRunner._get_databases`).

`BaseDatabaseCreation.serialize_db_to_string` writes as JSON every row of every model that can migrate on the connection and that the router allows there, in order of its primary key, for each application that has migrations and is not in `TEST_NON_SERIALIZED_APPS`; its docstring says it is meant for the test runner and will not handle large amounts of data (`django/db/backends/base/creation.py:BaseDatabaseCreation.serialize_db_to_string`).

`BaseDatabaseCreation.deserialize_db_from_string` loads the rows back inside an atomic block, which a comment says handles forward references and cycles, and inside `BaseDatabaseWrapper.constraint_checks_disabled`, which another comment says is because MySQL does not support deferred checks, and then hands the tables it wrote to the connection's `BaseDatabaseWrapper.check_constraints` (`django/db/backends/base/creation.py:BaseDatabaseCreation.deserialize_db_from_string`).

## Clones for parallel test runs

When the runner runs the tests in several processes, `setup_databases` calls `BaseDatabaseCreation.clone_test_db` once for each process, with the suffixes `"1"`, `"2"` and on, right after it has made the test database. A clone's settings are `BaseDatabaseCreation.get_test_db_clone_settings`: a copy of the connection's, with the suffix after `"NAME"`, which by then, its comment says, is the test database's own (`django/db/backends/base/creation.py:BaseDatabaseCreation.get_test_db_clone_settings`). `clone_test_db` calls `BaseDatabaseCreation._clone_test_db`, which in the base class raises `NotImplementedError`; Oracle's backend has no other.

The other three copy the database each its own way. SQLite's copies the file, to the name with the suffix before its extension, or writes a database in memory to a file where the way the workers are started needs one (`django/db/backends/sqlite3/creation.py:DatabaseCreation._clone_test_db`). PostgreSQL's makes the clone with `"CREATE DATABASE"` from the test database as its template, closing the connection and its pool first, since, its comment says, the statement requires the connections to the template to be closed (`django/db/backends/postgresql/creation.py:DatabaseCreation._clone_test_db`). MySQL's makes an empty database and pipes mysqldump of the test database into the mysql client, both command lines built by its `DatabaseClient.settings_to_cmd_args_env` (`django/db/backends/mysql/creation.py:DatabaseCreation._clone_test_db`, `django/db/backends/mysql/creation.py:DatabaseCreation._clone_db`). Asked once the test database is made, as a test run asks, SQLite's clone settings give the test database's file name with the suffix:

```text recording=backends
connection.settings_dict['NAME']  ->  'test_harbour.sqlite3'
connection.creation.get_test_db_clone_settings('2')['NAME']  ->  'test_harbour_2.sqlite3'
```

Each worker process, as it starts, calls `BaseDatabaseCreation.setup_worker_connection` with its number for each alias the tests use, or for every alias where the suite names none (`django/test/runner.py:_init_worker`). The base class's updates the connection's `settings_dict` with the clone's settings and closes the connection; its comment says the update must be in place, because with a new dictionary assigned, new threads would connect to the default database instead of the clone (`django/db/backends/base/creation.py:BaseDatabaseCreation.setup_worker_connection`). A worker started by spawn or forkserver is a new interpreter, and `_init_worker` first gives it the settings and the serialized rows of the process that made the databases.

## SQLite: the in-memory test database and the start method

SQLite's backend takes a missing `"TEST"` name as `":memory:"`, and makes it the name `"file:memorydb_default?mode=memory&cache=shared"` for `"default"`, with the alias in it (`django/db/backends/sqlite3/creation.py:DatabaseCreation._get_test_db_name`). It is a URI, which the backend always asks the driver to open as one (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_connection_params`); its `"mode=memory"` is what `DatabaseCreation.is_in_memory_db` looks for; the alias in it gives each alias a database of its own, as the signature does; and the testing documentation says the shared cache lets tests share the database between threads (`docs/topics/testing/overview.txt`).

```text recording=backends
test_name = connection.creation.create_test_db(verbosity=0, autoclobber=True)
  BaseDatabaseCreation.create_test_db(verbosity=0, autoclobber=True)
    DatabaseCreation._get_test_db_name  ->  'file:memorydb_default?mode=memory&cache=shared'
...
    DatabaseWrapper.close
      BaseDatabaseWrapper.close
    call_command('migrate', verbosity=0, interactive=False, database='default', run_syncdb=True)
      BaseDatabaseWrapper.connect
...
connection.settings_dict['NAME']  ->  'file:memorydb_default?mode=memory&cache=shared'
connection.is_in_memory_db()  ->  True
```

SQLite's `DatabaseWrapper.close` does nothing for a database in memory, its comment saying that closing the connection destroys the database (`django/db/backends/sqlite3/base.py:DatabaseWrapper.close`; [SQLite](sqlite.md)). `BaseDatabaseCreation.create_test_db` closed the connection while `"NAME"` was still the real database's, and the close went through. `BaseDatabaseCreation.destroy_test_db` calls `close` while `"NAME"` is the in-memory database's, so that close does nothing; it removes no file and puts `"NAME"` back, and the connection keeps its driver's connection, so the test database in memory is not destroyed, though the settings now name the file.

```text recording=backends
connection.creation.destroy_test_db(old_name, verbosity=0)
  BaseDatabaseCreation.destroy_test_db(old_database_name='harbour.sqlite3', verbosity=0)
    DatabaseWrapper.close
    DatabaseCreation._destroy_test_db(test_database_name='file:memorydb_default?mode=memory&cache=shared', verbosity=0)
  # 0 statements were sent while this line ran: none is written
connection.settings_dict['NAME']  ->  'harbour.sqlite3'
connection.connection is None  ->  False
```

Clones of a database in memory depend on how the worker processes are started, which `multiprocessing.get_start_method` says. A fork copies an in-memory database with the process, a comment says, so the clone's settings are the test database's own and nothing is copied. Under spawn or forkserver, `DatabaseCreation._clone_test_db` writes the database with the driver's `sqlite3.Connection.backup` to a file named for the alias and the suffix (`django/db/backends/sqlite3/creation.py:DatabaseCreation._clone_test_db`, `django/db/backends/sqlite3/creation.py:DatabaseCreation.get_test_db_clone_settings`); any other start method raises `NotSupportedError`. Here the recording set `"NAME"` by hand to `":memory:"`, which `DatabaseCreation.is_in_memory_db` takes to be in memory, like the test database's URI:

```text recording=backends
multiprocessing.get_start_method()  ->  'spawn'
connection.settings_dict['NAME'] = ':memory:'
connection.creation.get_test_db_clone_settings('2')['NAME']  ->  'default_2.sqlite3'
```

In the worker, SQLite's `DatabaseCreation.setup_worker_connection`, under spawn or forkserver, opens the clone's file read-only, copies it with the same `sqlite3.Connection.backup` into a new database in memory, sets that as `"NAME"`, and connects before it closes the copy (`django/db/backends/sqlite3/creation.py:DatabaseCreation.setup_worker_connection`). It does so whatever the test database was: under spawn, a worker on SQLite works in memory even where the test database is a file, as it is here:

```text recording=backends
connection.creation.setup_worker_connection('2')  # as the second worker process calls it, here in this one
  DatabaseCreation.setup_worker_connection('2')
    DatabaseCreation.get_test_db_clone_settings('2')  ->  the connection's settings with 'NAME': 'test_harbour_2.sqlite3'
    BaseDatabaseWrapper.connect
  # 0 statements were sent while this line ran: none is written
connection.settings_dict['NAME']  ->  'file:memorydb_default_2?mode=memory&cache=shared'
full(sorted(connection.introspection.table_names()))  ->  ['crew_officer', 'crew_sailor', 'fleet_port', 'fleet_ship', 'fleet_voyage', 'fleet_voyage_calls', 'office_berth', 'office_licence', 'office_manifest']
```

## Oracle: a test user and tablespaces

Oracle has no separate databases under one user, the docstring of `DatabaseCreation._switch_to_test_user` says, so Oracle's backend makes a test database a user of its own; [Oracle](oracle.md) tells how the user and its tablespaces are made (`django/db/backends/oracle/creation.py:DatabaseCreation._switch_to_test_user`).
