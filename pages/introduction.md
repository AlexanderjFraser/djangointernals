---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
contents: parts, extension-points, neighbours, philosophies, origins
---

# What Django is

Django is a web framework written in Python: the code between a web server and a web application, which turns each HTTP request the server hands it into a response, keeps the application's data as models over a relational database, and draws its pages from templates. This chapter is the map of it: the objects that carry it, how its parts lean on one another, how it is extended, and where it stops.

All of it happens in a process that Django configures once, before the first request, and then keeps. A request is a call into that process, and a view, chosen by the request's path, decides what its response is, reading and writing rows through models and rendering text through templates. Beside that machinery Django ships tools for the developer who builds on it: the management commands, with the system checks they run, and the test framework.

It began at World Online, the web department of a newspaper in Lawrence, Kansas, whose developers drew it out of the sites they built in Python from 2003; it was made open source in 2005, and is now run by an international team of volunteers ([Where Django came from, and who makes it](introduction/origins.md)).

## A project names its parts

What a developer writes with Django is a **project**: a settings module; a root URLconf, the module whose list of patterns maps a path to a view; and **applications**, each a Python package that keeps its models, views and templates together. Much of Django's own work arrives the same way. The admin, authentication and sessions are applications in `django.contrib`, listed in the settings beside the project's own.

The settings are where a project says what it is made of, and they say much of it with dotted paths, each naming a module, a class or another object that Django will import. This is part of the settings module that `django-admin startproject` writes for a new project:

```python
# settings.py as django-admin startproject writes it; some lines are left out
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # ...
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # ...
    }
}
```

The applications, the middleware and the backends of the templates and of the database are each named, not built in, and each could be another: the pattern by which Django loads what a setting names, and the places it is used, is [How Django is extended](introduction/extension-points.md).

## The objects that carry it

The process is prepared once, before it serves anything. A server is pointed at the project's `wsgi.py` or `asgi.py`, which startproject also writes: a WSGI server calls the object the module makes, and an ASGI server awaits it. Importing the module calls `get_wsgi_application` or `get_asgi_application`, which calls `django.setup` and then makes the handler (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`). Another way into a process is a management command: `manage.py` calls `execute_from_command_line`, which calls `django.setup` and then runs the command (`django/core/management/__init__.py:ManagementUtility.execute`).

**The settings** are an object, `settings`, a `LazySettings` made when `django.conf` is imported. It is lazy: it reads the settings module only when first needed, and keeps the values. `setup` asks for a setting at once, so by then the module has been read (`django/conf/__init__.py:LazySettings._setup`). Next `setup` fills **the app registry**, an `Apps` named `apps`, which imports every installed application and then its models, and holds an `AppConfig` for each application and every model class but the abstract ones (`django/__init__.py:setup`, `django/apps/registry.py:Apps.populate`).

**The handler**, a `WSGIHandler` or an `ASGIHandler`, is the object the server calls, once for each request. When it is made it turns the `MIDDLEWARE` setting into the **middleware chain** and keeps it: the middleware nested one inside the next, each a layer a request passes through on its way in and its response on its way out (`django/core/handlers/base.py:BaseHandler.load_middleware`). For each request it builds an `HttpRequest` from what the server passed, calls the chain with it, and hands the response that comes back to the server in the server's terms. The innermost layer of the chain is the handler's own method, which asks **the resolver**, a `URLResolver` made from the root URLconf on first use and kept, to match the request's path against the URL patterns; the resolver returns the view and the arguments the path supplied (`django/urls/resolvers.py:URLResolver.resolve`). **The view** is any callable that takes a request and returns a response; Django asks of it only that it return one (`django/core/handlers/base.py:BaseHandler.check_response`).

Two sides of Django serve the view. On **the data side**, **the model**, a subclass of `Model`, is the class through which a table's rows are read and written, a field in most cases standing for a column; its options, kept as `Model._meta` (an `Options`), hold what Django knows about it: its fields, its table, its relations, its ordering (`django/db/models/base.py:ModelBase.__new__`). The admin, the model forms and the migrations derive what they need from `_meta` (`django/forms/models.py:fields_for_model`, `django/db/migrations/state.py:ModelState.from_model`). **The queryset**, a `QuerySet`, is a lazy description of a query, built up by chained calls, which a `SQLCompiler` of the database's backend turns into SQL when its results are first needed (`django/db/models/query.py:QuerySet._fetch_all`).

On **the presentation side**, **the template engine**, an `Engine`, finds a template by name through its loaders and compiles it into a tree of nodes, which is rendered with a context (`django/template/engine.py:Engine.get_template`). The `TEMPLATES` setting names not the engine but a **template backend**, `DjangoTemplates`, which wraps it in the interface every backend shares, so that Jinja2 can stand in its place (`django/template/backends/django.py:DjangoTemplates`, `deps:final/0182-multiple-template-engines.rst`).

## The parts, in one picture

The objects that carry Django belong to a few departments of its source, and the figure places them, each department leaning on those beneath it: the request side, with the view at its centre; beneath the view, the presentation side and the data side, which the view uses; beneath those, the services, which any part may call on, the system checks among them by what imports them, not their purpose; and on the floor, the settings, the registry, the utilities and the core exceptions, which every part imports. The applications of `django.contrib` and the developer's tools are built on top of all of it.

```text figure=the-whole
the server, outside Django: a WSGI or an ASGI server
    calls the handler, once for each request
------------------------------------------------------------------------------------------------ Django
on top, built on the rest:
    the applications of django.contrib: auth, sessions, messages, admin, contenttypes,
        staticfiles and the others, each an application like the project's own
    the developer's tools: the management commands, the test framework

the request side, left to right:
    handler -> middleware, the way in -> resolver -> view -> middleware, the way out -> response

beneath the view, which uses them:
    the presentation side: templates, forms
    the data side: models, querysets, SQL, backends, migrations

beneath those, the services any part may call on:
    signals, files, cache, mail, tasks, serialization, the system checks

the floor, which every part imports: the settings, the app registry, the utilities, the core exceptions
------------------------------------------------------------------------------------------------ Django
the database, outside Django, reached through its driver
```

*Django's parts as departments, each leaning on those beneath it. The large box is Django; the two dashed boxes, the server above and the database below, are outside it. The accented arrows are a request's way from the server's call along the request side, the view at its centre accented too; the plain arrow is the data side's way out to the database.*

The picture is a map, not a set of walls: the parts do import one another, and which part imports which, and which never does, is the subject of [The parts of Django, and what each leans on](introduction/parts.md). The principles they are built by are written down in the project's design philosophies, and where the code keeps them and where it bends them is [The design philosophies, in the code](introduction/philosophies.md).

## One request, in brief

The server calls the handler. The request goes in through the middleware, the first in the setting first; each may answer at once and send the request no further. At the centre the resolver matches the path and the view is called. A view that shows data builds a queryset, which sends no query yet, and renders a template, and it may be the template's loop that first reads the rows and so sends the `"SELECT"`. The view returns a response, which goes back out through the middleware in the reverse order and on to the server, and when the response has been sent it is closed, which sends `request_finished`, one of the **signals** by which a part of Django tells any receiver that something has happened (`django/http/response.py:HttpResponseBase.close`). [A request, end to end](overview.md) follows one request through all of this, recorded from a running Django; in that request it is the loop that sends the query.

## Where Django stops

Django's handler listens on no socket: a WSGI or an ASGI server does that and calls it, and the development server that runserver starts is the one server Django ships. The models' rows live in a database, outside Django, reached through a driver that a backend imports. Django requires two libraries beside Python, asgiref for the bridge between synchronous and asynchronous code and sqlparse for splitting and parsing SQL, and on Windows a third, tzdata (`django:pyproject.toml`); it imports others where a feature needs them, from Pillow for images to Jinja2 for a second template engine. Packages built on Django attach where it leaves a point open: [Django's neighbours](introduction/neighbours.md).
