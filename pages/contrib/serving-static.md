---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Serving static files: `StaticFilesHandler` and the development server

How the static files application serves files in development without collecting them: `StaticFilesHandler`, which its runserver puts in front of the project's handler, the finders' view `django.contrib.staticfiles.views.serve` under it and `staticfiles_urlpatterns`, `ASGIStaticFilesHandler`, and `StaticLiveServerTestCase`.

In production a web server serves the collected files from `STATIC_ROOT`. In development nothing need be collected. The static files application serves each file from where it is kept: it asks the finders for the path and hands what they find to `django.views.static.serve` ([The static file view](../views/static-files.md)). Two things lead there: a handler in front of the project's own, which the development server uses, and a URL pattern in the project's URLconf.

## The finders' view

`django.contrib.staticfiles.views.serve` takes a request and a path relative to `STATIC_URL` (`django/contrib/staticfiles/views.py:serve`). Unless `settings.DEBUG` is true or it is called with `insecure=True`, it raises a bare `Http404`. Otherwise it normalizes the path as the static file view does, with `posixpath.normpath` and the leading slashes stripped, and asks `django.contrib.staticfiles.finders.find` for the first match ([Finding static files: the finders](static-finders.md)). If no finder has one, the path is refused with `Http404`: "Directory indexes are not allowed here." when it is empty or ends in a slash, and "'notes/missing.css' could not be found", with the path, otherwise.

A match is split into its directory and its name, and `django.views.static.serve` is called with the directory as the document root and with any further keyword arguments the view was given, `show_indexes=True` for one.

```text
# a run: django.contrib.staticfiles.views.serve called with a GET request for the path
settings.DEBUG false
  serve(request, "notes/harbour.css")                 Http404, no message
  serve(request, "notes/harbour.css", insecure=True)  200, a FileResponse, text/css
settings.DEBUG true
  serve(request, "notes/missing.css")                 Http404: 'notes/missing.css' could not be found
  serve(request, "nowhere/")                          Http404: Directory indexes are not allowed here.
```

`staticfiles_urlpatterns` makes the URL pattern. It passes its prefix, `STATIC_URL` unless another is given, and this view to `django.conf.urls.static.static`, so it refuses an empty prefix and returns an empty list unless `settings.DEBUG` is true and the prefix names no host (`django/contrib/staticfiles/urls.py:staticfiles_urlpatterns`, `django/conf/urls/static.py:static`). Its module is a URLconf as well: when it is first imported with `settings.DEBUG` true, its own list of patterns receives the same pattern (`django/contrib/staticfiles/urls.py`).

## `StaticFilesHandler`

`StaticFilesHandler` is a `WSGIHandler` made around another WSGI application. `StaticFilesHandler.__call__` reads the path from the environ, and unless `StaticFilesHandlerMixin._should_handle` finds it under the path of `STATIC_URL`, with no host in `STATIC_URL`, it calls the application inside, untouched (`django/contrib/staticfiles/handlers.py:StaticFilesHandler.__call__`). A path it keeps goes through the inherited `WSGIHandler.__call__`, which makes the request and hands the response to the server as usual ([The two entry points](../handlers/entry.md)).

The difference is in the middle. `StaticFilesHandlerMixin` holds what the WSGI and the ASGI handler share, and replaces methods of `BaseHandler`. `StaticFilesHandlerMixin.load_middleware`, which `WSGIHandler.__init__` calls, does nothing; the comment says the middleware are already loaded for the application inside (`django/contrib/staticfiles/handlers.py:StaticFilesHandlerMixin.load_middleware`). `StaticFilesHandlerMixin.get_response` calls no chain. It calls `StaticFilesHandlerMixin.serve`, which gives the finders' view, with `insecure=True`, what `StaticFilesHandlerMixin.file_path` makes of the request's path: the path of `STATIC_URL` cut off, the rest made a file system path by `urllib.request.url2pathname`. So the handler serves whatever `settings.DEBUG` is. An `Http404` becomes a response through `response_for_exception`: the project's 404 view, or the technical 404 page while `settings.DEBUG` is true (`django/contrib/staticfiles/handlers.py:StaticFilesHandlerMixin.get_response`).

A file served so passes through no middleware and no URL resolver. In the example, with `settings.DEBUG` false and nothing collected:

```text
# a run: StaticFilesHandler(WSGIHandler()) called as a WSGI server calls it; Host harbour.example unless shown
GET /static/notes/harbour.css                          200, text/css, a FileResponse
GET /static/notes/missing.css                          404, the project's 404 page
GET /lighthouses/1/                                    200, text/plain, from the WSGIHandler inside
GET /static/notes/harbour.css, Host elsewhere.example  200, text/css
GET /lighthouses/1/, Host elsewhere.example            400: the host is not in ALLOWED_HOSTS
GET /static/../contrib_setup.py                        SuspiciousFileOperation, raised out of the handler
```

Nothing asked the host of the static request, so a host the project refuses was served. And only `Http404` is caught: the `SuspiciousFileOperation` a finder raises for a path that climbs out of its directory, which the project's chain would have made a 400, leaves the handler for the server (`django/core/handlers/exception.py:response_for_exception`).

Closing the response sends `request_finished` with the handler's class as its sender: `StaticFilesHandler` for the static files of the run, `WSGIHandler` for the lighthouse (`django/http/response.py:HttpResponseBase.close`). `StaticFilesHandlerMixin.handles_files` is true and read nowhere in Django; its comment says it may tell the handlers apart, in such a receiver for one.

The handler reads `STATIC_URL` once, when it is made, through `StaticFilesHandlerMixin.get_base_url`, which first runs `check_settings`. That raises `ImproperlyConfigured` for a `STATIC_URL` not set (an empty one becomes the script prefix, ordinarily `"/"`, under which every path falls), a `MEDIA_URL` equal to it, a `MEDIA_ROOT` and a `STATIC_ROOT` both set and equal, and, while `settings.DEBUG` is true, a `MEDIA_URL` inside `STATIC_URL`, whose paths the handler would take for its own (`django/contrib/staticfiles/utils.py:check_settings`, `django/conf/__init__.py:LazySettings._add_script_prefix`).

## `ASGIStaticFilesHandler`

`ASGIStaticFilesHandler` does the same under ASGI. `ASGIStaticFilesHandler.__call__` keeps a scope of the type `"http"` whose path is under `STATIC_URL`, for `ASGIHandler.__call__`, and passes every other, a lifespan or a WebSocket among them, to the application inside (`django/contrib/staticfiles/handlers.py:ASGIStaticFilesHandler.__call__`). `StaticFilesHandlerMixin.get_response_async` runs the view with `sync_to_async` on the event loop's ordinary pool of threads, and makes a 404 on the request's own thread ([Sync and async in one chain](../handlers/async.md#one-thread-per-request)). `ASGIStaticFilesHandler.get_response_async` then replaces the synchronous iterator of a streaming response, such as the view's `FileResponse`, with an asynchronous generator that first reads all of it in a thread; its comment says `FileResponse` is not async compatible (`django/contrib/staticfiles/handlers.py:ASGIStaticFilesHandler.get_response_async`). Nothing in Django makes this handler: the development server is WSGI only ([The development server](../commands/runserver.md#a-wsgi-server-for-development)).

## The development server and live-server tests

Installing `django.contrib.staticfiles` replaces Django's runserver with the application's own, a subclass, unless an application listed before it has one too: an installed application's command replaces Django's of the same name, and the first listed wins ([Finding the command](../commands/finding.md#the-dictionary-of-commands-get_commands)). It adds `--nostatic` and `--insecure`, and its `Command.get_handler` wraps what Django's returns, the project's WSGI application, in a `StaticFilesHandler`, unless `--nostatic` was given, if `settings.DEBUG` is true or `--insecure` was given (`django/contrib/staticfiles/management/commands/runserver.py:Command.get_handler`). The server asks for its handler once, before it starts ([The development server](../commands/runserver.md#which-application-it-serves)).

`--insecure` serves files by the names they are kept under, and the documentation says it does not work with `ManifestStaticFilesStorage` (`docs/ref/contrib/staticfiles.txt`). In the example, after collectstatic and with `settings.DEBUG` false, `{% static "notes/harbour.css" %}` wrote /static/notes/harbour.f60ecf1ef40a.css, which the handler answered with a 404: no finder has that name.

`StaticLiveServerTestCase` overrides `LiveServerTestCase.static_handler`, a private handler that serves `STATIC_ROOT`, with `StaticFilesHandler`, so a live server's static files come from the finders, with nothing collected (`django/contrib/staticfiles/testing.py:StaticLiveServerTestCase`, `django/test/testcases.py:_StaticFilesHandler`) ([The test framework](../testing.md)).
