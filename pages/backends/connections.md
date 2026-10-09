---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# Connections by alias: `DATABASES` and `ConnectionHandler`

`django.db.connections`, the one `ConnectionHandler` of a process, turns an alias of the setting `DATABASES` into a connection that the calling thread may use. It fills in the setting's defaults once, makes a connection the first time a thread asks for an alias, importing its backend where that has not been done, and keeps it in storage of that thread's own; `django.db.connection` is a proxy for the connection `"default"`.

Code that sends a statement starts from an **alias**, a key of `DATABASES`, and needs the **connection** for it: an instance of the backend's `DatabaseWrapper`, such as SQLite's (`django/db/backends/sqlite3/base.py:DatabaseWrapper`), that it can use at once. Three things stand in between. The settings a project wrote may leave out most of their keys, or be empty; the backend is a dotted path still to be imported; and a connection carries the driver's connection and the state of a transaction, which Django does not let a second thread take a cursor on, commit or roll back unless told that it may.

`ConnectionHandler` deals with all three behind one subscript, `connections["default"]` (`django/db/utils.py:ConnectionHandler`, `django/utils/connection.py:BaseConnectionHandler`). Making a connection opens nothing: the driver's connection is opened the first time something needs it (`django/db/backends/base/base.py:BaseDatabaseWrapper.ensure_connection`) ([Opening and closing a connection](lifecycle.md)).

```text figure=alias-and-thread
connections: the one ConnectionHandler of the process

  settings   DATABASES, its defaults filled in once, the first time it is read:
             one dictionary for each alias, held by every thread's connection for that alias
               "default"   {"ENGINE": "django.db.backends.sqlite3", "NAME": "harbour.sqlite3", "CONN_MAX_AGE": 0, ...}
               "archive"   {"ENGINE": "django.db.backends.sqlite3", "NAME": "archive.sqlite3", ...}

  storage    Local(thread_critical=True): what one thread puts there, no other thread sees
               the main thread     "default" -> a DatabaseWrapper     "archive" -> a DatabaseWrapper
               a second thread     "default" -> another DatabaseWrapper
               a thread running an event loop: a store of its own for each asyncio context

connections["archive"], asked on a thread
  in this thread's storage                     ->  that connection
  not there, and not an alias of the settings  ->  raises ConnectionDoesNotExist
  not there                                    ->  create_connection("archive"): load_backend(ENGINE).DatabaseWrapper(...),
                                                   kept in this thread's storage and returned; nothing is opened
```

*`django.db.connections` keeps one set of settings for the process and, in each thread, a connection for each alias that thread has asked for, made the first time it asked. In a thread that runs an event loop the storage is divided again, by asyncio context.*

## The handler, and its first use

`django.db` makes the handler as the package is imported, with no settings, and the handler reads nothing until `BaseConnectionHandler.settings`, a cached property, is first read (`django/db/__init__.py`, `django/utils/connection.py:BaseConnectionHandler.settings`). That first read calls `ConnectionHandler.configure_settings`, which reads `DATABASES` where the handler was given no settings and adds the defaults; the result is kept for the life of the handler.

The first use in a process was recorded from a running Django, in an interpreter of its own, with the example project's two SQLite databases, `"default"` and `"archive"`. A line at the left margin is a question with its answer after `->`, or a line of Python with the calls it set going nested under it, only the calls the passage is about written down and `->` for what a call returned; a call is written by the class that declares its method, or by the object's class with the declaring class after it in parentheses:

```text recording=backends
'settings' in vars(connections)  ->  False
'django.db.backends.sqlite3.base' in sys.modules  ->  False
django.setup()
  import_module('harbour.fleet.models')
    Options.contribute_to_class(cls=Named, name='_meta')
      BaseConnectionHandler.__getitem__('default')
        BaseConnectionHandler.settings
          ConnectionHandler.configure_settings
            BaseConnectionHandler.configure_settings
            -> a dict of 2: 'default', 'archive', each with its defaults filled in
        ConnectionHandler.create_connection('default')
          load_backend('django.db.backends.sqlite3')
            import_module('django.db.backends.sqlite3.base')
            -> the module django.db.backends.sqlite3.base
          DatabaseWrapper.__init__(settings_dict=connections.settings['default'], alias='default')  (BaseDatabaseWrapper.__init__)
...
          -> the connection "default"
```

What first asked was not a query. `Options.contribute_to_class`, setting up the first model class, the fleet's abstract Named, asks the default connection's operations object for the longest name the database allows, to cut the default table name to it (`django/db/models/options.py:Options.contribute_to_class`) ([The options: what a model keeps as `_meta`](../models/options.md)). That one subscript configured the settings of every alias, imported SQLite's backend through `load_backend` (`django/db/utils.py:load_backend`), and made the connection, whose `BaseDatabaseWrapper.__init__` made the helper objects ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)). Afterwards the connection is in this thread's storage, and the dictionary it holds as `BaseDatabaseWrapper.settings_dict` is the handler's own for the alias, not a copy:

```text recording=backends
'settings' in vars(connections)  ->  True
connections.all(initialized_only=True)  ->  [the connection "default"]
'django.db.backends.sqlite3.base' in sys.modules  ->  True
conn = connections['default']
connections['default'] is conn  ->  True
conn.settings_dict is connections.settings['default']  ->  True
conn.connection  ->  None
```

## The defaults, and the alias `"default"`

`ConnectionHandler.configure_settings` settles two things: that there is an alias `"default"`, and that every alias has a value for each of the keys below (`django/db/utils.py:ConnectionHandler.configure_settings`). For an alias given an engine and a name and nothing else, a key to a line:

```text recording=backends
given = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'harbour.sqlite3'}}
handler = ConnectionHandler(given)
handler.settings is given  ->  True
settings['default']['ENGINE']: 'django.db.backends.sqlite3'
settings['default']['NAME']: 'harbour.sqlite3'
settings['default']['ATOMIC_REQUESTS']: False
settings['default']['AUTOCOMMIT']: True
settings['default']['CONN_MAX_AGE']: 0
settings['default']['CONN_HEALTH_CHECKS']: False
settings['default']['OPTIONS']: {}
settings['default']['TIME_ZONE']: None
settings['default']['USER']: ''
settings['default']['PASSWORD']: ''
settings['default']['HOST']: ''
settings['default']['PORT']: ''
settings['default']['TEST']: {'CHARSET': None, 'COLLATION': None, 'MIGRATE': True, 'MIRROR': None, 'NAME': None}
```

Each default is written with `dict.setdefault`, so a key the project gave keeps its value, except an `"ENGINE"` that names no backend (below). The defaults go into the setting's own dictionaries: the recorded handler kept the very dictionary it was given, and the handler of `django.db` fills in the object that `settings.DATABASES` holds. Each key is read where its subject is told: `"ENGINE"` by the handler, to load the backend; `"NAME"`, `"USER"`, `"PASSWORD"`, `"HOST"`, `"PORT"` and `"OPTIONS"` by each backend that uses them ([SQLite](sqlite.md), [PostgreSQL](postgresql.md), [MySQL and MariaDB](mysql.md), [Oracle](oracle.md)); `"AUTOCOMMIT"`, `"CONN_MAX_AGE"` and `"CONN_HEALTH_CHECKS"` as a connection is opened and closed ([Opening and closing a connection](lifecycle.md)); `"ATOMIC_REQUESTS"` around each view ([Transactions: autocommit, `atomic` and savepoints](transactions.md)); `"TIME_ZONE"` where values cross ([Values in and out: adapters, converters and time zones](values.md)); and `"TEST"` when the test databases are made ([Test databases: `BaseDatabaseCreation`](creation.md)).

The alias `"default"` is settled first. An empty setting, which is also what `DATABASES` is in Django's global settings, is given a `"default"` whose engine is `"django.db.backends.dummy"` (`django/conf/global_settings.py`). A setting with aliases, none of them `"default"`, is refused. A `"default"` given as an empty dictionary is given the dummy engine, and so, in the loop that follows, is any alias whose `"ENGINE"` is missing, empty, `None` or the bare `"django.db.backends."`:

```text recording=backends
empty = ConnectionHandler({})
empty.settings['default']['ENGINE']  ->  'django.db.backends.dummy'
...
ConnectionHandler({'other': {'ENGINE': 'django.db.backends.sqlite3'}}).settings  ->  raises ImproperlyConfigured: You must define a 'default' database.
ConnectionHandler({'default': {}}).settings['default']['ENGINE']  ->  'django.db.backends.dummy'
```

So the alias may be a placeholder, but it must be there. `"default"`, which Django names `DEFAULT_DB_ALIAS` (`django/db/utils.py:DEFAULT_DB_ALIAS`), is the alias it falls back on wherever no other has been chosen: the router's answer when no router answers and no instance among its hints has a database ([Routing between databases: `ConnectionRouter`](routers.md)), the alias of `django.db.connection`, and the one the functions of `django.db.transaction` use when they are given none (`django/db/transaction.py:get_connection`). Django's guide to several databases puts it from the user's side: an entry for `"default"` is required, and its dictionary may be left empty where routers send every query elsewhere (`docs/topics/db/multi-db.txt`).

## `create_connection`, and importing the backend

`ConnectionHandler.create_connection` hands the alias's `"ENGINE"` to `load_backend` and calls the `DatabaseWrapper` of the module that comes back with the alias's settings and the alias (`django/db/utils.py:ConnectionHandler.create_connection`, `django/db/backends/sqlite3/base.py:DatabaseWrapper`). The class is looked up by its name, so a backend is any package whose `base` module defines one ([The connection object: `BaseDatabaseWrapper` and what a backend provides](wrapper.md)).

`load_backend` imports the backend's module `base`, which Python then keeps in `sys.modules`, so the import is done once in a process (`django/db/utils.py:load_backend`). Where the import raises `ImportError`, the name decides what follows. A name that is not a built-in backend's, a package under `django/db/backends/` other than `"base"` and `"dummy"`, is refused with `ImproperlyConfigured`, which lists the built-ins and is raised from the `ImportError`, so that the cause stands above it in the traceback; a built-in backend's `ImportError` is raised again, the comment taking it for an error in Django:

```text recording=backends
load_backend('harbour.nosuch')  ->  raises ImproperlyConfigured: 'harbour.nosuch' isn't an available database backend or couldn't be imported. Check the above exception. To use one of the built-in backends, use 'django.db.backends.XXX', where XXX is one of:\n    'mysql', 'oracle', 'postgresql', 'sqlite3'
```

PostgreSQL's, MySQL's and Oracle's backends never reach that branch when their driver is not installed: each base module catches its driver's `ImportError` and raises an `ImproperlyConfigured` of its own (`django/db/backends/postgresql/base.py`, `django/db/backends/mysql/base.py`, `django/db/backends/oracle/base.py`).

## One connection for each alias in each thread

`BaseConnectionHandler.__getitem__` returns what it finds in the storage under the alias. Finding nothing, it refuses an alias the settings lack with the class's `BaseConnectionHandler.exception_class`, `ConnectionDoesNotExist`, and otherwise calls `ConnectionHandler.create_connection` and stores what it returns (`django/utils/connection.py:BaseConnectionHandler.__getitem__`).

```text recording=backends
connections['nosuch']  ->  raises ConnectionDoesNotExist: The connection 'nosuch' doesn't exist.
```

The storage is asgiref's `Local`, made with `BaseConnectionHandler.thread_critical`, which `ConnectionHandler` sets to `True` (`django/db/utils.py:ConnectionHandler.thread_critical`). With that flag, in a thread that runs no event loop, `Local` behaves exactly as a `threading.local`: what one thread sets, only that thread sees (`asgiref:asgiref/local.py:Local`). Here the main thread holds `"default"` and a second thread asks for the same alias:

```text recording=backends
main_connection = connections['default']
main_connection.connection is None  ->  True
# on a second thread, which the main thread waits for:
  connections.all(initialized_only=True)  ->  []
  connections['default'] is main_connection  ->  False
  connections.all(initialized_only=True)  ->  [the connection "default"]
```

Each thread is given its own connection; `BaseConnectionHandler.all` with `initialized_only=True` lists what the asking thread has made. A connection refuses another thread a cursor, a commit or a rollback unless it has been allowed to be shared (`django/db/backends/base/base.py:BaseDatabaseWrapper.validate_thread_sharing`) ([Opening and closing a connection](lifecycle.md)). Only the connection objects are kept apart. Every thread's connection for an alias holds the one dictionary of settings, so a change made to it through one is seen by all.

`BaseConnectionHandler.__setitem__` puts a connection into this thread's storage without a check (`django/utils/connection.py:BaseConnectionHandler.__setitem__`).

In a thread where an event loop is running, `Local` keeps within the thread's store a second one that behaves as a context variable (`asgiref:asgiref/local.py:Local._lock_storage`). A connection a coroutine makes is seen by what it awaits and by tasks it starts afterwards, not by its thread outside the loop: a coroutine asking for `"default"` is given a connection other than the one its thread holds in synchronous code, and two tasks that each ask first are given two, which the coroutine that started them does not see. Each task here returns the connection it is given:

```text recording=backends
asyncio.run(in_a_new_loop())  # the script's coroutine, whose lines stand under this one; nothing in it has asked for a connection before
  first, second = await asyncio.gather(asks_first(), asks_first())
  first is second  ->  False
  first is main_connection  ->  False
  connections['default'] is main_connection  ->  False
  connections['default'] is first  ->  False
  third, fourth = await asyncio.gather(asks_first(), asks_first())
  third is fourth is connections['default']  ->  True
  threading.current_thread() is threading.main_thread()  ->  True
```

In a thread whose event loop is running, any connection refuses to open or to give a cursor, unless the environment variable `"DJANGO_ALLOW_ASYNC_UNSAFE"` is set (`django/utils/asyncio.py:async_unsafe`) ([The asynchronous methods of a queryset](../querysets/async.md)). The comment on `ConnectionHandler` gives the reasoning: backends are to guard their code against asynchronous contexts with `async_unsafe`, the storage gives such contexts separate connections in case one is needed all the same, and since nothing cleans up after them, using such a connection is not allowed where it can be helped. The work goes to another thread through `sync_to_async`, which here runs every call on one thread kept for the purpose (`asgiref:asgiref/sync.py:SyncToAsync.__call__`); that thread, running no loop, keeps connections of its own from one call to the next:

```text recording=backends
asyncio.run(in_the_loop())  # the script's coroutine, whose lines stand under this one
  threading.current_thread() is threading.main_thread()  ->  True
  connections['default'].cursor()  ->  raises SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async.
  Ship.objects.count()  ->  raises SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async.
  await sync_to_async(threading.current_thread)() is threading.main_thread()  ->  False
  await sync_to_async(connections.__getitem__)('default') is main_connection  ->  False
  await sync_to_async(threading.get_ident)() == await sync_to_async(threading.get_ident)()  ->  True
  await sync_to_async(Ship.objects.count)()  ->  2
    SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
```

## `django.db.connection`: a proxy for `"default"`

`django.db.connection` is a `ConnectionProxy` of the handler and `DEFAULT_DB_ALIAS`, made as `django.db` is imported, with a comment that it is kept for backwards compatibility and that `connections['default']` is to be preferred (`django/db/__init__.py`). The proxy holds the handler and the alias and nothing else. Each attribute read that the proxy itself lacks, each one set or deleted on it, and its `in` and its `==`, go to `connections["default"]`, looked up again at that moment (`django/utils/connection.py:ConnectionProxy`), so the one name stands in each thread for that thread's connection.

```text recording=backends
type(connection)  ->  django.utils.connection.ConnectionProxy
connection == connections['default']  ->  True
connection is connections['default']  ->  False
connection.alias  ->  'default'
```

## The dummy backend

`django.db.backends.dummy` is the backend of an alias that names no engine (`django/db/backends/dummy/base.py`). Two functions of the module are put in place of the base classes' methods, as class attributes: `complain`, which raises `ImproperlyConfigured`, and `ignore`, which does nothing. The comment on the dummy's `DatabaseWrapper` gives the line between them: whatever tries actually to do something complains, and whatever tries to roll back or undo something is ignored (`django/db/backends/dummy/base.py:DatabaseWrapper`). `empty` is the handler given an empty setting:

```text recording=backends
type(empty['default'])  ->  django.db.backends.dummy.base.DatabaseWrapper
empty['default'].cursor()  ->  raises ImproperlyConfigured: settings.DATABASES is improperly configured. Please supply the ENGINE value. Check settings documentation for more details.
empty['default'].close()  ->  None
```

So the connection is made like any other; whatever would open it through `BaseDatabaseWrapper.ensure_connection`, or take a cursor, stops with a message that names the missing value, and `BaseDatabaseWrapper.close` returns at once, there being no driver's connection. `BaseDatabaseWrapper.rollback` returns quietly where `BaseDatabaseWrapper.commit` complains, and `BaseDatabaseWrapper.savepoint` returns before making a savepoint, `DummyDatabaseFeatures.uses_savepoints` being false (`django/db/backends/base/base.py:BaseDatabaseWrapper._savepoint_allowed`):

```text recording=backends
empty['default'].rollback()  ->  None
empty['default'].features.uses_savepoints  ->  False
empty['default'].savepoint()  ->  None
empty['default'].commit()  ->  raises ImproperlyConfigured: settings.DATABASES is improperly configured. Please supply the ENGINE value. Check settings documentation for more details.
```

A model class can still be set up, the base class's `BaseDatabaseOperations.max_name_length` answering `None`, no limit (`django/db/backends/base/operations.py:BaseDatabaseOperations.max_name_length`).

## `all`, `close_all` and the receivers of `django.db`

`BaseConnectionHandler.all` returns `self[alias]` for each alias of the settings, which makes every connection this thread has not made, unless `initialized_only=True` is given: then only what this thread's storage holds is returned (`django/utils/connection.py:BaseConnectionHandler.all`). `BaseConnectionHandler.close_all` closes each connection this thread has made. `BaseCommand.run_from_argv` calls it after a command run from the command line (`django/core/management/base.py:BaseCommand.run_from_argv`); the server a live server's thread runs, which serves each client's connection on a thread of its own, calls it when it has finished with that connection (`django/core/servers/basehttp.py:ThreadedWSGIServer.close_request`), and the live server's thread calls it as it ends (`django/test/testcases.py:LiveServerThread.run`).

`django/db/__init__.py` ends by connecting two functions to the signals a handler sends at a request's start and end ([The two entry points](../handlers/entry.md)). `reset_queries`, on `request_started`, empties the query log, `BaseDatabaseWrapper.queries_log`, of each connection this thread has made ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)). `close_old_connections`, on `request_started` and `request_finished` both, calls `BaseDatabaseWrapper.close_if_unusable_or_obsolete` on each ([Opening and closing a connection](lifecycle.md)) (`django/db/__init__.py:close_old_connections`). Both pass `initialized_only=True`, so neither makes a connection. Here the two signals are sent by hand, as a handler sends them:

```text recording=backends
signals.request_started.send(sender=WSGIHandler, environ={})
  Signal.send  (request_started, sender=WSGIHandler)
    reset_queries
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
...
signals.request_finished.send(sender=WSGIHandler)
  Signal.send  (request_finished, sender=WSGIHandler)
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
```

Under ASGI both signals reach the receivers through `sync_to_async`, on the request's own thread, where its connections were made (`django/core/handlers/asgi.py:ASGIHandler.handle`) ([Sync and async in one chain](../handlers/async.md)).
