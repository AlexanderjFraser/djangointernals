---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Foundations
contents: startup, arrival, view, query, template, response
---

# A request, end to end

One HTTP request followed from the server's call to the last byte of the response, through every system this book describes: the handler and its middleware, the URL resolver, the view, the ORM from queryset to SQL, the template engine, and the response.

Django's job can be said in one sentence: in a process it has configured once, turn each request a server hands it into a response. This chapter follows one request through the whole of that, so that the reader has the shape of the system before any part of it is taken apart. The request is `GET /entries/2026/` to the smallest project that exercises every system: the settings `django-admin startproject` writes, with their seven middleware and with `settings.DEBUG` off as it is in production, and one package, journal, which is the project and its one application at once: it holds the settings and the URLconf beside a model with a title and a date, one view and one template. The database is SQLite with three rows in it. This is the whole of the project's own code, apart from the settings:

```python
# journal/urls.py
urlpatterns = [path("entries/<int:year>/", views.by_year, name="entries-by-year")]

# journal/models.py
class Entry(models.Model):
    title = models.CharField(max_length=100)
    published = models.DateField()

# journal/views.py
def by_year(request, year):
    entries = Entry.objects.filter(published__year=year).order_by("published")
    return render(request, "journal/entries.html", {"year": year, "entries": entries})
```

```html
<!-- journal/templates/journal/entries.html -->
<title>Entries of {{ year }}</title>
<h1>Entries of {{ year }}</h1>
<ul>
{% for entry in entries %}
  <li>{{ entry.published|date:"j F" }}: {{ entry.title }}</li>
{% endfor %}
</ul>
```

Everything below was recorded from a running Django serving that request, twice: the first time, when the process does for the first time what it will then keep, and a second time, when it does only what every request needs. The chapter's sections follow the request a station at a time and quote the recording as they go.

## The shape of it

A request passes through Django in a fixed order, and each stage is owned by one part of the framework. Read down, this list is the chapter; each item also names the part of the book that explains it.

1. **The process was prepared once.** Before any request, importing the project's `wsgi.py` loaded the settings, imported every installed application and registered its models, and made the handler, which built the middleware chain from `settings.MIDDLEWARE` (`django/core/wsgi.py:get_wsgi_application`, `django/__init__.py:setup`). None of this runs again: [Before the first request](overview/startup.md).
2. **The server calls the handler.** `WSGIHandler.__call__` sends the `request_started` signal, wraps the server's dictionary in a `WSGIRequest` that leaves the query string, the cookies and the body unparsed until they are read, and calls the chain (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).
3. **The request goes in through the middleware.** Seven layers, each wrapped in `convert_exception_to_response`, a function that turns an exception raised inside the layer into a response at its boundary (`django/core/handlers/exception.py:convert_exception_to_response`). On the way in three of them leave something on the request for a later layer or the view, a session that has not been loaded, a user that has not been looked up, a place for messages, and one checks the `"Host"` header: [From the server's call to the view](overview/arrival.md).
4. **The URL is resolved and the view called.** At the centre of the chain `BaseHandler._get_response` asks the resolver, one object per process, to match the path. The pattern that matches, a `URLPattern`, names the view, and its route, a `RoutePattern`, converts `2026` to an `int` (`django/urls/resolvers.py:URLPattern.resolve`); the CSRF middleware's `process_view` accepts a `GET`; and the view is called with the capture as a keyword argument (`django/core/handlers/base.py:BaseHandler._get_response`): [The URL is resolved and the view is called](overview/view.md).
5. **The view builds a queryset and sends no query.** `QuerySet.filter` and `QuerySet.order_by` each return a new `QuerySet` around a `Query` that records the condition, the year of the date field compared with the value, and the ordering; nothing touches the database: [A queryset becomes SQL](overview/query.md).
6. **The view asks for a template.** `render` looks the template up through the engine, which the first request makes from `settings.TEMPLATES`, and the engine's loaders find the file in the application's templates directory and compile it into nodes, once; the second request takes the compiled template from the cached loader: [The template is rendered](overview/template.md).
7. **Rendering runs the context processors and then each node**, and the `for` tag, needing the number of rows for its loop variables, takes the length of the queryset.
8. **That is the moment the query runs.** The `Query` is compiled to one `"SELECT"` by a `SQLCompiler` for the database's backend, a connection is opened, the statement executed, and each row becomes an instance of the model through `Model.from_db` (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`, `django/db/models/base.py:Model.from_db`).
9. **Each value is escaped as it is rendered**, and the joined string becomes an `HttpResponse` with a `Content-Type` of HTML.
10. **The response goes out through the middleware**, in the reverse order, three of the seven adding five headers between them, and `WSGIHandler.__call__` hands the status, the headers and the body to the server: [The response returns to the server](overview/response.md).
11. **The server ends the request.** When it has sent the body it closes the response, which sends `request_finished`, and a receiver of that closes the database connection: with the default settings a connection lives for one request (`django/http/response.py:HttpResponseBase.close`, `django/db/__init__.py:close_old_connections`).

```text figure=the-path
time runs down; each column is a part of Django, and the chapters that explain it

the server  |  Handlers, middleware, requests  |  URL routing, views     |  Models, querysets, SQL, backends  |  Templates
            |                                  |                         |                                    |
   calls -> |  WSGIHandler.__call__            |                         |                                    |
            |  request_started; a WSGIRequest  |                         |                                    |
            |  six process_request, the way in:|                         |                                    |
            |  session, host, user, messages   |                         |                                    |
            |                                  |  URLResolver.resolve    |                                    |
            |                                  |  a route matches;       |                                    |
            |                                  |  ResolverMatch          |                                    |
            |                                  |  the view is called     |                                    |
            |                                  |  with year=2026         |                                    |
            |                                  |                         |  QuerySet.filter, order_by         |
            |                                  |                         |  a Query is built; no SQL yet      |
            |                                  |                         |                                    |  get_template
            |                                  |                         |                                    |  the engine, its loaders,
            |                                  |                         |                                    |  the compile: once a process
            |                                  |                         |                                    |  Template.render
            |                                  |                         |                                    |  context processors, then nodes
            |                                  |                         |  QuerySet.__len__ from {% for %}   |
            |                                  |                         |  SQLCompiler; connect; SELECT;     |
            |                                  |                         |  rows become model instances       |
            |                                  |                         |                                    |  VariableNode.render
            |                                  |                         |                                    |  each value escaped
            |  HttpResponse                    |                         |                                    |
            |  six process_response, the way   |                         |                                    |
            |  out: five headers added         |                         |                                    |
 <- sends   |  start_response; the body        |                         |                                    |
   closes ->|  HttpResponseBase.close          |                         |                                    |
            |  request_finished; the           |                         |                                    |
            |  connection is closed            |                         |                                    |
```

*The request's path through Django, time running down. Each column is one part of the framework and the chapters that explain it; the path crosses from the handler to the resolver and the view, from the view to the ORM and the template system, from the template's loop back to the ORM for the rows, and returns through the middleware to the server.*

## The request, recorded

This is the second request, the one that does only what every request does. The recording writes down the functions the chapter names and nothing between them, nested as they were called; most of its lines are left out here, and the sections quote the recording in full, a station at a time, from whichever of the two requests shows the station best.

```text recording=overview
WSGIHandler.__call__(environ, start_response)  GET /entries/2026/
  signal request_started -> reset_queries, close_old_connections
  WSGIRequest.__init__(environ)
  BaseHandler.get_response
      SecurityMiddleware.process_request
        SessionMiddleware.process_request
          CommonMiddleware.process_request
            CsrfViewMiddleware.process_request
              AuthenticationMiddleware.process_request
                MessageMiddleware.process_request
                  BaseHandler._get_response
                      URLResolver.resolve('/entries/2026/')
                        ResolverMatch(journal.views.by_year, kwargs={'year': 2026})
                    CsrfViewMiddleware.process_view
                    journal.views.by_year(request, year=2026)
                      QuerySet.filter(published__year=2026)
                      QuerySet.order_by('published')
                      render(request, "journal/entries.html", context)
                        get_template('journal/entries.html')
                          DjangoTemplates.get_template('journal/entries.html')
                            Engine.get_template('journal/entries.html')
                              Engine.find_template('journal/entries.html')
                                cached.Loader.get_template('journal/entries.html')
                          Template.render(context)  (the engine's Template)
                            context_processors.csrf
                            context_processors.request
                            auth.context_processors.auth
                            messages.context_processors.messages
                            VariableNode.render  {{ year }}
                            ForNode.render  {% for entry in entries %}
                              QuerySet.__len__
                                    SQLCompiler.execute_sql
                                      SQLCompiler.as_sql
                                      BaseDatabaseWrapper.cursor
                                        BaseDatabaseWrapper.connect
                                        SQL SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" WHERE "journal_entry"."published" BETWEEN %s AND %s ORDER BY "journal_entry"."published" ASC with params ('2026-01-01', '2026-12-31')
                                    Model.from_db  (Entry)
                                    Model.from_db  (Entry)
                              VariableNode.render  {{ entry.published|date:"j F" }}
                              VariableNode.render  {{ entry.title }}
                        HttpResponse.__init__(content)
                  XFrameOptionsMiddleware.process_response  (status 200)
                MessageMiddleware.process_response  (status 200)
            CsrfViewMiddleware.process_response  (status 200)
          CommonMiddleware.process_response  (status 200)
        SessionMiddleware.process_response  (status 200)
      SecurityMiddleware.process_response  (status 200)
  start_response("200 OK", [Content-Type, X-Frame-Options, Content-Length, X-Content-Type-Options, Referrer-Policy, Cross-Origin-Opener-Policy])
the server has sent the body: 148 bytes
HttpResponseBase.close
  signal request_finished -> close_old_connections, close_caches, reset_urlconf
        DatabaseWrapper.close  (sqlite3)
```

The nesting is the call stack, kept as it was recorded even where the lines between are left out. The view runs inside the innermost middleware, the query runs inside the template's loop, and the response is built at the bottom of the stack and carried up through every layer that the request came down.

## What is kept and what is made each time

Much of what looks like a cost of serving a request is paid once, by the process, and much of what looks like state is made for one request and discarded with it. The chapter's sections show each of these at the moment it happens; this is the ledger.

| kept for the life of the process | where it is kept | made for one request |
|---|---|---|
| the settings, loaded on their first use and cached value by value | `django/conf/__init__.py:LazySettings.__getattr__` | the `WSGIRequest`, with its query string, cookies and body parsed only if read |
| the app registry, every model class and its `_meta` | `django/apps/registry.py:Apps.populate` | the session store, the lazy user and the message storage the middleware set on it |
| the handler and the middleware chain, each middleware instantiated once | `django/core/handlers/base.py:BaseHandler.load_middleware` | the `ResolverMatch`, kept on the request |
| the root resolver, and the URLconf it imports on first use | `django/urls/resolvers.py:_get_cached_resolver` | each `QuerySet` and its `Query`, the `SQLCompiler`, and the rows and model instances |
| the template engines, their loaders, their tag libraries and their context processors, each made on first use | `django/template/utils.py:EngineHandler.__getitem__` | the `RequestContext` and the rendered string |
| every compiled template, in the cached loader | `django/template/loaders/cached.py:Loader.get_template` | the `HttpResponse` |
| the database connection, only when `"CONN_MAX_AGE"` is set; with the default it is opened and closed within the request | `django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete` | the URLconf set for the thread and cleared at the end, and the script prefix set for it at each request's start |

*What a process keeps across requests and what it makes for each. The left column is made by the first request that needs it, except the first three rows, which are made before any request; the right column has nothing to do with the left in any one row.*

A third kind of state is kept for a thread. The connection wrappers that `connections` hands out are one per database per thread, and they outlive the connections they open (`django/utils/connection.py:BaseConnectionHandler.__getitem__`); the script prefix and the URLconf are set for the thread by each request, and the URLconf is cleared at its end.

## Where this request did not go

The request touched most of Django and left some of it alone, and what it left alone is the rest of the book.

It was a `GET` with no body, so no form was bound and no body was parsed; a `POST` would have its body read by the request on first use and checked by the CSRF middleware's `process_view` before the view ran, and the view would hand the data to a `Form` ([Forms](forms.md)). It carried no cookie, so the session was never loaded and the user never looked up; a logged-in user's request would load the session at the first touch of `HttpRequest.user`, with a query for the session and one for the user ([Authentication, sessions and messages](auth.md)). It passed through no locale middleware, and the only translations it made were of two month names in the date filter, lazy text that the filter turned into English ([Internationalization and time zones](i18n.md)). It used no cache, though `close_caches` ran at its end, and sent no mail; it did send five kinds of signal, and the dispatcher that carried them is a small machine of its own ([Caching, files, mail, signals and tasks](services.md)). The lazy objects that let the user and the token wait until they are read are the work of one module ([The utility layer](utils.md)).

The process it ran in was started by a server, but the same process serves a management command, which calls `django.setup` before it runs and is how the table the query read was made in the first place, by a migration ([Management commands](commands.md), [Migrations](migrations.md)). The admin's modules were imported at startup, by its application's `ready`, and then not visited ([The admin](admin.md)); the static files application registered its checks and was not asked for a file ([Content types, static files and the other contrib apps](contrib.md)). Under ASGI the same chain would have run, with the synchronous middleware on a thread of the request's own and the centre on the event loop ([Handlers and middleware](handlers.md)). And a test would have driven the same chain without a server, through a handler of the test client's ([The test framework](testing.md)).
