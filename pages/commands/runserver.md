---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The development server

What `python manage.py runserver` runs: a command whose `handle` does not return while the server is up, which runs the system checks, obtains the project's WSGI application, and gives it to `run` in `django/core/servers/basehttp.py`, an HTTP server made of small subclasses of the classes in Python's `wsgiref` and `socketserver`.

Django contains one web server, and it is short because most of it is borrowed. Python's standard library has a reference implementation of the server's half of WSGI, `wsgiref.simple_server`, built in turn on `socketserver`. Django subclasses its parts and changes what a developer would notice: a thread for each connection, connections that stay open, a log line with colour, a file watcher beside it.

What the server serves is not a development version of anything. It is the project's own WSGI application, the object a production server would be pointed at, with the same handler and the same middleware chain inside. A request under runserver takes the path through Django that it takes under any other WSGI server; this page is about what stands outside that path.

## The command

The command's class divides its work at one line: what every process of the server does, including the first, which never serves a request, and what only a process that serves does (`django/core/management/commands/runserver.py:Command`).

The first part is short. `Command.handle` refuses to start, with a `CommandError`, if `settings.DEBUG` is false and `settings.ALLOWED_HOSTS` is empty, a combination under which no request's host is accepted. It reads the one positional argument, a port or an address and a port, falling back on the loopback address and port 8000. Then `Command.run` chooses how to go on. With the reloader, which is the default, it passes the second part to `run_with_reloader`, and from here on there are two processes ([The autoreloader](autoreload.md)). With `--noreload` it calls the second part itself.

Before that, the inherited machinery is kept out of the way. `Command.get_check_kwargs` returns an empty collection of tags, so that when `BaseCommand.execute` runs the system checks ahead of `handle`, none is selected: the checks belong to the part that serves. And `Command.execute` wraps the inherited method to carry one option further than it would reach. The server's log lines are coloured by a logging formatter, not by the command, so for `--no-color` the method sets `"DJANGO_COLORS"` in the environment, which a comment calls the only way to reach the code that logs requests.

The second part is `Command.inner_run`, the server proper. Under the reloader it runs only in a second process, on a thread that the reloader names django-main-thread, though the process's main thread is another, and it runs from the top in every process that replaces that one. This is that thread, recorded in the orchard project used throughout the chapter.

```text recording=commands
The development server: the second process (started by the first with RUN_MAIN="true"), the thread django-main-thread
    the wrapper that check_errors made around Command.inner_run
      Command.inner_run  (django.core.management.commands.runserver)
        raise_last_exception
        OutputWrapper.write("Performing system checks...\n\n")  to stdout
        BaseCommand.get_check_kwargs
          -> {}
        BaseCommand.check(display_num_errors=True)
          CheckRegistry.run_checks()
            -> 23 check functions called; no messages
          OutputWrapper.write("System check identified no issues (0 silenced).")  to stdout
        BaseCommand.check_migrations
        Command.get_handler  (django.contrib.staticfiles.management.commands.runserver)
          Command.get_handler  (django.core.management.commands.runserver)
            get_internal_wsgi_application
              import orchard.wsgi
                get_wsgi_application
                  django.setup
                  WSGIHandler.__init__
          StaticFilesHandler.__init__
            WSGIHandler.__init__
        run("127.0.0.1", 8642, a StaticFilesHandler, threading=True, server_cls=WSGIServer)
          WSGIServer.__init__  (the class is WSGIServer, made from socketserver.ThreadingMixIn, WSGIServer)
          Command.on_bind  (django.core.management.commands.runserver)
          BaseServer.serve_forever
            ThreadingMixIn.process_request  (a connection is accepted: a thread is started for it)
```

The first call belongs to the reloader's story: it raises again an exception that startup set aside, if there was one. Then come the system checks that the empty tags postponed. The method asks the inherited `get_check_kwargs`, going past its own override, which is the empty dictionary in the recording, and so runs what any command runs: every check but the database ones. `--skip-checks` leaves this out. `BaseCommand.check_migrations` follows, which prints a notice if the default database has unapplied migrations, and the method closes the database connections that the look opened.

Then the server itself. `Command.get_handler` returns the application, and `run` is called with the address, the application and `Command.on_bind`, a method to be called once the socket is bound. `run` returns only when the server stops.

`inner_run` also answers the failures a developer is most likely to cause. An `OSError` from binding the socket, a port already in use or one the user may not open, is printed as one line and the process is ended with `os._exit`, because, in the words of a comment, `sys.exit` does not work in a thread. A `KeyboardInterrupt` ends the command quietly with status 0.

`Command.on_bind` prints the banner. This is the terminal of the recorded run as far as the first request. The recording's server was restarted once, which made three processes in all, but every line shown here was written by the second: the first process prints nothing. The first line is the reloader's, the next three are the checks', then the banner, and last the log of the request.

```text recording=commands
The development server: what the three processes wrote to the terminal, standard output and standard error together
    | Watching for file changes with StatReloader
    | Performing system checks...
    |
    | System check identified no issues (0 silenced).
    | (the date and the time)
    | Django version 6.2.dev20260926051415, using settings 'orchard.settings'
    | Starting WSGI development server at http://127.0.0.1:8642/
    | Quit the server with CTRL-BREAK.
    |
    | WARNING: This is a development server. Do not use it in a production setting. Use a production WSGI or ASGI server instead.
    | For more information on production servers see: https://docs.djangoproject.com/en/dev/howto/deployment/
    | [(the date and the time)] "GET / HTTP/1.1" 200 13
```

## Which application it serves

The command's `get_handler` returns what `get_internal_wsgi_application` returns, and that function reads one setting (`django/core/management/commands/runserver.py:Command.get_handler`). `settings.WSGI_APPLICATION` is the dotted path of the project's application object, in a project made by startproject the object named application in its `wsgi.py`. The function imports it. If the setting is `None` it calls `get_wsgi_application` itself (`django/core/servers/basehttp.py:get_internal_wsgi_application`).

Importing the project's `wsgi.py` is why the recording shows `get_wsgi_application` under the import, and under that a second `django.setup` and a `WSGIHandler` being made. The second setup finds the applications loaded, and configures logging over again; making the handler builds the middleware chain. It also follows that whatever a project wraps around its application in that file, a piece of WSGI middleware for instance, is in place under runserver as it is in production. The setting exists for this server alone; a production server is told where the object is by its own configuration.

In most projects one more layer is added, and by a different class. A project that installs `django.contrib.staticfiles` runs that application's runserver, a subclass that replaces Django's by name ([Finding the command](finding.md#the-dictionary-of-commands-get_commands)). Its `get_handler` wraps the application in a `StaticFilesHandler` when `settings.DEBUG` is true, or when `--insecure` was given, and `--nostatic` was not (`django/contrib/staticfiles/management/commands/runserver.py:Command.get_handler`).

`StaticFilesHandler` is a WSGI application around another. For a path under `settings.STATIC_URL`, provided that setting does not name a host, it answers itself, with the file that the static files finders locate. Every other path it passes to the application inside (`django/contrib/staticfiles/handlers.py:StaticFilesHandler`). This is why static files are served in development without having been collected, and not in production: the wrapping is done by this command, and the only other thing in Django that does it is a live server for tests.

## The classes of `basehttp.py`

`run` is short. It chooses a server class, makes an instance bound to the address, calls `on_bind`, gives the instance the application and calls its `socketserver.BaseServer.serve_forever` (`django/core/servers/basehttp.py:run`).

The server class is made on the spot. When threading is on, which it is under runserver unless `--nothreading` was given, `run` creates a new class from `socketserver.ThreadingMixIn` and the server class it was passed, and marks the instance's request threads as daemons. A comment explains the mark: the server will not wait for request threads to finish when it stops, which makes a reload faster and spares the user a process that will not die because a thread is stuck.

Each class in the file extends one from the standard library and changes a few things.

| class | extends | what Django's adds |
|---|---|---|
| `WSGIServer` | `wsgiref.simple_server.WSGIServer` | a listen queue of 10; the IPv6 address family when asked; a broken connection reported as one log line, not a traceback |
| `WSGIRequestHandler` | `wsgiref.simple_server.WSGIRequestHandler` | HTTP/1.1 and connections kept open between requests; header names with underscores dropped; log lines sent to the logger `"django.server"` |
| `ServerHandler` | `wsgiref.simple_server.ServerHandler` | a request body that is drained if the application did not read it; more reasons to close a connection |
| `ThreadedWSGIServer` | `socketserver.ThreadingMixIn` and `WSGIServer` | database connections that can be handed to it and shared by its request threads; all of a thread's connections closed when its client's connection ends |

*The four classes of `django/core/servers/basehttp.py`.*

The last is not the threaded class runserver uses, which is the one `run` makes. `ThreadedWSGIServer` is the server class of the test framework's live server, where a test and the server may have to share one connection to an in-memory database (`django/test/testcases.py:LiveServerThread`).

## One request through it

The recorded server was asked for one page. The last line of the recording above, on the server's thread, is the connection being accepted. This is the thread that was started for it.

```text recording=commands
The development server: the second process (started by the first with RUN_MAIN="true"), the thread started for the connection that sent GET /
    ThreadingMixIn.process_request_thread
      WSGIRequestHandler.handle
        WSGIRequestHandler.handle_one_request
          BaseHandler.run(a StaticFilesHandler)
            StaticFilesHandler.__call__  GET /
              WSGIHandler.__call__  GET /
            ServerHandler.finish_response
              ServerHandler.close
                WSGIRequestHandler.log_message("\"GET / HTTP/1.1\" 200 13")
```

```text figure=one-request
the thread django-main-thread               a thread for each connection

BaseServer.serve_forever                    WSGIRequestHandler.handle                one object for the connection
  accepts a connection,              ->       WSGIRequestHandler.handle_one_request  reads one request line and its headers
  starts a thread for it,                       BaseHandler.run                      on a ServerHandler, one object for the request
  and waits for the next                          StaticFilesHandler.__call__        answers a path under STATIC_URL itself
                                                    WSGIHandler.__call__             the project's application: Django's request cycle
                                                  ServerHandler.finish_response      sends the response, logs the request, closes it
                                              and again, while the connection stays open
```

*One request under the development server. The server's own thread only accepts connections; each connection has a thread, each request on it a `ServerHandler`, and inside that the project's application is called as any WSGI server would call it.*

A `WSGIRequestHandler` is made for the connection, and its `handle` serves requests on it one after another until the connection is to be closed (`django/core/servers/basehttp.py:WSGIRequestHandler.handle`).

`WSGIRequestHandler.handle_one_request` reads one request. It reads the request line, answering one that is too long with status 414, and has the standard library parse the headers. Then it builds the WSGI environment, and `WSGIRequestHandler.get_environ` first deletes every header whose name contains an underscore. WSGI turns a header's name into a key by, among other things, replacing hyphens with underscores, so two different headers could arrive under one key, and a client could use that to counterfeit a header that a proxy in front was trusted to set. A comment notes that Nginx and Apache drop such headers too.

A `ServerHandler` is made for the request. Its `run`, inherited from `wsgiref.handlers.BaseHandler`, calls the application with the environment and a function to start the response. Here the application is the `StaticFilesHandler`, which passes a path that is not a static file's to the project's application. That call is the whole of Django's request cycle, and [Handlers and middleware](../handlers.md) begins there.

`ServerHandler.finish_response` sends what came back, and `ServerHandler.close` finishes: it reads whatever of the request's body the application left unread, so that nothing of it is left on the connection, logs the request, and closes the response (`django/core/servers/basehttp.py:ServerHandler`).

Whether the connection then stays open is decided in two places. The standard library decides first, as it parses the request: an HTTP/1.1 client that does not ask for the connection to be closed gets to keep it. `ServerHandler.cleanup_headers` can then only add reasons to close. It does so when the response has no `Content-Length`, unless the request was a HEAD, since the client could not tell where such a response ends; and when the server is not threaded, which a comment puts as a rule: persistent connections require a threading server. An application can also ask for the connection to be closed, by sending the header itself.

## The log line

`WSGIRequestHandler.log_message` is what the standard library calls to log anything about a request, most often the request line with its status and size. Django's version sends the message to the logger `"django.server"`, choosing the level from the status: an error for 500 and above, a warning for 400 and above, and information otherwise (`django/core/servers/basehttp.py:WSGIRequestHandler.log_message`, `django/utils/log.py:log_message`).

That logger has a handler and a formatter of its own in Django's default logging configuration, which is why the line appears whatever `settings.DEBUG` is, and with the time in brackets before it. The formatter, `ServerFormatter`, colours the message by the class of its status. It makes a style object of its own for that, from the same palettes as a command's ([Running a command: `BaseCommand`](running.md#output-and-colour)), which is why `--no-color` has to travel through the environment to reach it (`django/utils/log.py:ServerFormatter`).

One line is rewritten on the way. A request line that begins with the bytes of a TLS handshake, answered with a status in the 400s, means a browser tried HTTPS on a server that speaks only HTTP, and Django logs a sentence that says so, as an error, where the request line of unreadable bytes would have been.

## A WSGI server, for development

The file's first lines say the server has not been reviewed for security and is not to be used in production, and the banner repeats the warning on every start unless the environment sets `"DJANGO_RUNSERVER_HIDE_WARNING"` to true.

It is also a WSGI server only. The banner says so, and an ASGI application is not something `run` can be given. Asynchronous views still work under it, by the same adaptation the handler makes under any WSGI server ([Sync and async in one chain](../handlers/async.md)).

## testserver

The testserver command is the development server over a throwaway database. Its `handle` creates a test database as the test runner would, loads the fixtures named on the command line into it with `call_command`, and then calls runserver the same way, with the reloader off and a message to print on shutdown that says the test database has been left in place. A comment gives the reason for the reloader: with it, this `handle`, and so the creation of the database, would run more than once (`django/core/management/commands/testserver.py:Command.handle`).

How it makes that call has consequences. The server runs no system checks at all, because `call_command` turns them off and testserver's own class asks for none. And whether the server is threaded is decided by the database backend, by whether its test database can take more than one connection; with SQLite it cannot.
