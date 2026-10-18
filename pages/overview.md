---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: startup, arrival, view, query, template, response
---

# A request, end to end

One HTTP request followed from the server's call to the last byte of the response, through the handler and its middleware, the URL resolver, the view, the ORM from queryset to SQL, the template engine, and the response.

[What Django is](introduction.md) lays out Django's parts and how they lean on one another; this chapter sets them moving. Django's job is to turn each request a server hands it into a response, in a process it has configured once, and the chapter follows one request through the whole of that. The request is `GET /entries/2026/` to a small project: the settings `django-admin startproject` writes, with their seven middleware and `settings.DEBUG` off, as in production, and every host allowed; and one package, journal, which is the project and its one application at once: it holds the settings and the URLconf beside a model, a view and a template. The database is SQLite, with three rows. Apart from the settings, the project's own code is little more than this:

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

A running Django served that request twice, and the chapter quotes the recording: the first request does once what the process then keeps, and the second only what every request needs.

## The shape of it

A request passes through Django in a fixed order, each stage in one part of the framework. The figure follows this one across the parts.

```text figure=the-path
across the top, once, before the first request: the settings, the app registry, the handler and its middleware chain
below, time running down: the server on the left, outside Django; a column for each part of Django it crosses; a box a station

the server calls the handler ->
  the handler and the middleware   WSGIHandler.__call__: request_started; a WSGIRequest
  the handler and the middleware   process_request, the way in: session, host, user, messages
  the resolver and the view        URLResolver.resolve: a route matches
  the resolver and the view        by_year(year=2026): the view is called
  the ORM                          QuerySet.filter, order_by: a Query is built; no SQL yet
  the template engine              get_template: the engine, its loaders, the compile, once a process
  the template engine              Template.render: the context processors, then the nodes
  the ORM, accented                QuerySet.__len__ from {% for %}: SQLCompiler; connect; SELECT; rows become instances
  the template engine              VariableNode.render: the loop's values escaped
  the resolver and the view        the view returns an HttpResponse
  the handler and the middleware   process_response, the way out: five headers added
  the handler and the middleware   start_response: the status and the headers; the response is returned
<- the server sends the body, then closes the response ->
  the handler and the middleware   HttpResponseBase.close: request_finished; the connection is closed
```

*The band at the top is the work of startup, done once; below it, time running down, each column is one part of the framework, each box a station of the request, and an arrow the request passing from one station to the next. The accented box is the moment the query runs: in the template's loop, not where the view built it.*

**The process is prepared once.** A server imports the project's `wsgi.py`, which calls `get_wsgi_application`: the settings are loaded, every installed application is imported and its models are registered in the app registry, and the handler is made, which builds the middleware chain from `settings.MIDDLEWARE` (`django/core/wsgi.py:get_wsgi_application`). None of it runs again: [Before the first request](overview/startup.md).

**The request goes in through the middleware.** The server calls `WSGIHandler.__call__`, which sends the `request_started` signal, wraps the server's dictionary in a `WSGIRequest` that parses the query string, the cookies and the body only when they are read, and calls the chain (`django/core/handlers/wsgi.py:WSGIHandler.__call__`). Of the seven middleware, `SessionMiddleware` leaves on the request a session that has not been loaded, `AuthenticationMiddleware` a user that has not been looked up and `MessageMiddleware` a place for messages, and `CommonMiddleware` checks the `"Host"` header: [From the server's call to the view](overview/arrival.md).

**The path is resolved and the view called.** At the centre of the chain `BaseHandler._get_response` asks the resolver, one object kept for the life of the process, to match the path. The route converts `2026` to an `int`; the CSRF middleware, offered the view before it is called, lets a `"GET"` through; and the view is called with `year=2026` (`django/core/handlers/base.py:BaseHandler._get_response`): [The URL is resolved and the view is called](overview/view.md).

**The view builds a queryset, and the template runs it.** `QuerySet.filter` and `QuerySet.order_by` each return a new `QuerySet` around a `Query` that records the condition and the ordering, and nothing touches the database. The query runs when the template's loop asks how many rows there are: the `Query` is compiled to one `"SELECT"` by a `SQLCompiler`, a connection is opened, and each row becomes an instance of the model (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`, `django/db/models/base.py:Model.from_db`): [A queryset becomes SQL](overview/query.md).

**The template is found, compiled once and rendered.** `render` looks the template up through the template engine, which the first request makes from `settings.TEMPLATES`; the engine's loaders find the file and compile it into nodes, and the second request takes the compiled template from the cached loader. Rendering runs the context processors and then each node, escaping each value as its `VariableNode` renders it, and `render` makes an `HttpResponse` of the string (`django/shortcuts.py:render`): [The template is rendered](overview/template.md).

**The response goes back out.** It passes through the middleware in the reverse order, three of the seven adding five headers between them, and `WSGIHandler.__call__` hands the status, the headers and the body to the server. When the server has sent the body it closes the response, which sends `request_finished`, and a receiver of that closes the database connection: with the default settings a connection lives for one request (`django/http/response.py:HttpResponseBase.close`, `django/db/__init__.py:close_old_connections`): [The response returns to the server](overview/response.md).

## The request, recorded

This is the second request, cut to the lines that name a station; the dots stand for the middleware in the middle of the chain. The nesting is the call stack, each layer's `MiddlewareMixin.__call__` left out, and it is the thing to look at: the view runs inside the innermost middleware, the query inside the template's loop, and the response is made at the bottom of the stack and carried up through every layer the request came down.

```text recording=overview
WSGIHandler.__call__(environ, start_response)  GET /entries/2026/
  signal request_started -> reset_queries, close_old_connections
  WSGIRequest.__init__(environ)
  BaseHandler.get_response
      SecurityMiddleware.process_request
        SessionMiddleware.process_request
          ...
                MessageMiddleware.process_request
                  BaseHandler._get_response
                    BaseHandler.resolve_request
                      URLResolver.resolve('/entries/2026/')
                    CsrfViewMiddleware.process_view
                    journal.views.by_year(request, year=2026)
                      QuerySet.filter(published__year=2026)
                      QuerySet.order_by('published')
                      render(request, "journal/entries.html", context)
                        get_template('journal/entries.html')
                        Template.render(context, request)  (the backend's Template)
                          Template.render(context)  (the engine's Template)
                            ForNode.render  {% for entry in entries %}
                              QuerySet.__len__
                                        SQL SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" WHERE "journal_entry"."published" BETWEEN %s AND %s ORDER BY "journal_entry"."published" ASC with params ('2026-01-01', '2026-12-31')
                                    Model.from_db  (Entry)
                                    Model.from_db  (Entry)
                        HttpResponse.__init__(content)
                  XFrameOptionsMiddleware.process_response  (status 200)
          ...
      SecurityMiddleware.process_response  (status 200)
  start_response("200 OK", [Content-Type, X-Frame-Options, Content-Length, X-Content-Type-Options, Referrer-Policy, Cross-Origin-Opener-Policy])
the server has sent the body: 148 bytes
HttpResponseBase.close
  signal request_finished -> close_old_connections, close_caches, reset_urlconf
```

## Where this request did not go

The request touched most of Django and left some of it alone. It was a `"GET"` with no body and no cookie, so no form was bound and no user looked up; a `"POST"` would have had its token checked by the CSRF middleware before the view ran, and its data ready for a form ([Forms](forms.md), [The user of a request: `login`, `logout` and `AuthenticationMiddleware`](auth/login.md)). It used no cache and sent no mail. Other handlers build a chain of the same middleware: an `ASGIHandler` awaits its chain as a coroutine, with an adapter wherever a layer and its neighbour disagree ([Sync and async in one chain](handlers/async.md)), and the test client has a handler of its own and needs no server ([The test framework](testing.md)).

Every part of Django, what it leans on and the chapter that explains it is in [The parts of Django, and what each leans on](introduction/parts.md); the places where a project puts its own code into this path, its applications, its middleware and its backends, are [How Django is extended](introduction/extension-points.md).
