---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A server in a thread: `LiveServerTestCase`

`LiveServerTestCase` runs the project behind a real HTTP server on a thread of the test process, one server for each test class, at `LiveServerTestCase.live_server_url`. The server is a `ThreadedWSGIServer` run by a `LiveServerThread`, behind handlers that serve static and media files, and a SQLite test database in memory is shared with it through the test's own connection.

The test client has no socket a browser could reach ([The test client: `Client` and `ClientHandler`](client.md)). The class's docstring gives its purpose: a live server in a separate thread, so that tests may use another framework, Selenium for one, in place of the test client. It also says why the class is a `TransactionTestCase`: threads do not share transactions, unless they use SQLite's database in memory, and each must commit for the other to see its changes ([Emptying the tables after each test: `TransactionTestCase`](transaction-test-case.md); `django/test/testcases.py:LiveServerTestCase`).

## Starting the server: `setUpClass`

`LiveServerTestCase.host` is `"localhost"` and `LiveServerTestCase.port` is 0; `LiveServerTestCase.server_thread_class` and `LiveServerTestCase.static_handler` name the thread's class and the outermost handler. `LiveServerTestCase.live_server_url` and `LiveServerTestCase.allowed_host` are class properties (`classproperty`); the URL is made from `host` and the running thread's port.

`LiveServerTestCase.setUpClass` runs its parents' `setUpClass`, which enters the class's settings overrides ([Settings for one test: `override_settings` and `TestContextDecorator`](test-decorators.md)), so the server's handlers read the overridden settings. It appends `allowed_host` to `ALLOWED_HOSTS` with `modify_settings`, entered as a context of the class, and starts the server with `LiveServerTestCase._start_server_thread` (`django/test/testcases.py:LiveServerTestCase.setUpClass`, `django/test/testcases.py:LiveServerTestCase._start_server_thread`):

1. `LiveServerTestCase._make_connections_override` chooses the connections to share, and `BaseDatabaseWrapper.inc_thread_sharing` lets another thread use each ([Opening and closing a connection](../backends/lifecycle.md)).
2. `LiveServerTestCase._create_server_thread` makes the thread from `server_thread_class`, with the host, the port, `static_handler` and those connections; it is made a daemon and started.
3. `LiveServerTestCase._terminate_thread` is registered as a class cleanup.
4. The test's thread waits on `LiveServerThread.is_ready`, a `threading.Event`, and raises the error the thread kept, if any.

`unittest` runs a class's cleanups even when `setUpClass` raises, so a thread whose server failed to start is still joined and its connections' sharing undone. `_terminate_thread` calls `LiveServerThread.terminate`, then `BaseDatabaseWrapper.dec_thread_sharing` on each shared connection (`django/test/testcases.py:LiveServerTestCase._terminate_thread`).

## The thread: `LiveServerThread`

`LiveServerThread.run` puts the shared connections in `connections` under their aliases, in place of this thread's own, and builds the application: a `WSGIHandler` inside a `_MediaFilesHandler` inside the class's `static_handler`. It makes a `ThreadedWSGIServer` on the host and port, with `allow_reuse_address=False` and `QuietWSGIRequestHandler`, which logs no request so as not, its docstring says, to clutter the test output. For port 0 the system gives a free port, which it reads back from the bound socket. Only then does it set `is_ready` and serve. An exception on the way is kept as the thread's error and `is_ready` set, to end the wait; in a `finally` the thread closes its connections (`django/test/testcases.py:LiveServerThread.run`, `django/test/testcases.py:LiveServerThread._create_server`).

The server is built on the development server's `WSGIServer` and `WSGIRequestHandler`; `ThreadedWSGIServer` adds a thread for each client's connection, and is not the threaded class runserver makes ([The development server](../commands/runserver.md)). `ThreadedWSGIServer.process_request_thread` puts the shared connections in place on each such thread, and `ThreadedWSGIServer.close_request` closes the thread's connections when the client's connection ends (`django/core/servers/basehttp.py:ThreadedWSGIServer`). `LiveServerThread.terminate`, if `is_ready` is set, shuts down and closes the server, if one was made, and joins the thread; otherwise it does nothing.

## One connection for two threads

A SQLite test database is in memory unless its `"TEST"` `"NAME"` names a file ([Test databases: `BaseDatabaseCreation`](../backends/creation.md)). `_make_connections_override` takes those of the test thread's connections that are SQLite's to a database in memory (`django/test/testcases.py:LiveServerTestCase._make_connections_override`). The server's threads use those very objects, so they see what the test wrote, committed or not, and their closing does not destroy the database: SQLite's `DatabaseWrapper.close` ignores a close of a database in memory (`django/db/backends/sqlite3/base.py:DatabaseWrapper.close`). The documentation warns against the two threads querying through it at once: a test should wait for a page to load before going on (`docs/topics/testing/tools.txt`).

Any other database is not shared: each thread of the server opens its own connection to the test database, and sees what the test has committed.

## Static and media files: `FSFilesHandler`

`FSFilesHandler` is a `WSGIHandler` around another WSGI application that answers the paths under a URL from a directory. `FSFilesHandler.__call__` hands the application inside every request whose path is not under the URL's path, and all of them when the URL names a host (`django/test/testcases.py:FSFilesHandler._should_handle`). A path it keeps goes through `WSGIHandler.__call__` to `FSFilesHandler.get_response`, and `FSFilesHandler.serve` gives what follows the URL's path, normalised, to `django.views.static.serve`, with the handler's directory as the document root, whatever `settings.DEBUG` is ([The static file view](../views/static-files.md)). A missing file, or a directory, raises `Http404`, and the request goes on to `BaseHandler.get_response`: the file handler's own chain, not the application inside, for as a `WSGIHandler` it built the middleware chain when it was made (`django/test/testcases.py:FSFilesHandler.get_response`).

`_StaticFilesHandler` serves `STATIC_ROOT` under `STATIC_URL`, and `_MediaFilesHandler` serves `MEDIA_ROOT` under `MEDIA_URL`, so static files are served only once collected. The documentation gives that as the reason for `StaticLiveServerTestCase`, whose `static_handler` is the static files application's `StaticFilesHandler`, serving from the finders ([Serving static files: `StaticFilesHandler` and the development server](../contrib/serving-static.md); `docs/howto/static-files/index.txt`).

> **Trap.** Where `STATIC_URL` is not set, `_StaticFilesHandler` raises `TypeError` at every request and the server answers each with a 500. An empty `MEDIA_URL`, the default, is read as the script prefix, ordinarily `"/"` (`django/conf/__init__.py:LazySettings._add_script_prefix`), so the media handler takes every path, and with `MEDIA_ROOT` empty too it serves the current directory: /manage.py gets the project's manage.py.

## The harbour office over HTTP

A `LiveServerTestCase` in the harbour office's tests, with the settings the handlers need, and a notice beside it, notices/tides.txt:

```python
# harbour/office/tests/test_live.py
from pathlib import Path
from urllib.request import urlopen

from django.test import LiveServerTestCase, override_settings

from harbour.fleet.models import Port, Ship

NOTICES = Path(__file__).resolve().parent / "notices"


@override_settings(STATIC_URL="/static/", MEDIA_URL="/media/", MEDIA_ROOT=NOTICES)
class ShipLiveTests(LiveServerTestCase):
    def test_list_over_http(self):
        valletta = Port.objects.create(name="Valletta", country="Malta")
        Ship.objects.create(name="Beagle", tonnage=235, home=valletta)
        print(self.live_server_url)
        with urlopen(self.live_server_url + "/ships/") as response:
            self.assertIn("Beagle", response.read().decode())

    def test_notice(self):
        with urlopen(self.live_server_url + "/media/tides.txt") as response:
            print(response.status, response.headers["Content-Type"], response.read())
```

```text
$ python manage.py test harbour.office.tests.test_live
Found 2 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
http://localhost:46104
.200 text/plain b'High water 06:12\n'
.
----------------------------------------------------------------------
Ran 2 tests in 4.650s

OK
Destroying test database for alias 'default'...
```

The port is this run's. The test made Beagle on its own thread, and ship_list, on a thread of the server, read it through the same connection; the notice came from `MEDIA_ROOT`.

The testserver command is another way to serve a test database: the development server over one loaded with fixtures ([The development server](../commands/runserver.md)).
