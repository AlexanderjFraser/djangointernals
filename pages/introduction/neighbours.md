---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1; sqlparse 0.6.0
---

# Django's neighbours

Django's neighbours are the software it works with and does not contain: what calls it, what it needs, and what is built on it.

The figure draws the line between Django and its neighbours, and the calls that cross it: the server's call into the handler, which the middleware chain carries to the view, and the database backend's call out to its driver, made for the models and querysets the view uses.

```text figure=the-boundary
above the line, outside Django: the server
    a WSGI server (Gunicorn, uWSGI, mod_wsgi, Waitress)
        calls a WSGIHandler with the environ and start_response
    an ASGI server (Daphne, Uvicorn, Hypercorn)
        awaits an ASGIHandler with the scope, receive and send
------------------------------------------------------------ Django
the handler -> the middleware chain -> the view -> models and querysets -> the backend
required: asgiref (sync_to_async, async_to_sync, Local) and sqlparse;
    on Windows tzdata, which the standard library's zoneinfo reads
------------------------------------------------------------ Django
below the line, outside Django: the driver the backend imports -> the database
```

*Where Django stops. Between the two rules, Django's code and the libraries it requires; above, the server, which calls the handler; below, the driver and the database, which the backend calls. An arrow is a call.*

## The server

A web server owns the socket: it accepts connections, reads HTTP, and calls one Python object it was given when it started. Under WSGI it calls that object with the request's environ and a function that starts the response; under ASGI it awaits it with a scope and two awaitable callables for messages. The object is Django's handler (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.__call__`), and what it does with the call is [The two entry points](../handlers/entry.md).

A server is pointed at the object a project's `wsgi.py` or `asgi.py` makes with `get_wsgi_application` or `get_asgi_application`, each of which runs `django.setup` and makes a handler (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`). The WSGI servers [Gunicorn](https://gunicorn.org/), [uWSGI](https://uwsgi-docs.readthedocs.io/), [mod_wsgi](https://modwsgi.readthedocs.io/) and [Waitress](https://github.com/Pylons/waitress) are pointed at the first; the ASGI servers [Daphne](https://github.com/django/daphne), [Uvicorn](https://www.uvicorn.dev/) and [Hypercorn](https://hypercorn.readthedocs.io/) at the second. The ASGI handler serves HTTP only: any other scope, a WebSocket's included, it refuses with `ValueError`.

Django's own tree holds one server, the one runserver starts: WSGI only, built on the standard library's `wsgiref.simple_server`, and by its docstring not for production (`django/core/servers/basehttp.py`). It serves the object `WSGI_APPLICATION` names, which in a new project is the one a production WSGI server is given. If the setting is `None`, it serves what `get_wsgi_application` returns (`django/core/servers/basehttp.py:get_internal_wsgi_application`). [The development server](../commands/runserver.md) takes it apart.

## What Django requires

Django's `pyproject.toml` names three dependencies beside Python 3.12 or newer: asgiref 3.12.1 or newer, sqlparse 0.5.0 or newer, and tzdata on Windows only (`django:pyproject.toml`). The first two are imported at the top of the modules that use them: asgiref before `django.setup` runs, since the module a server or manage.py starts from imports the signals, whose dispatcher imports asgiref (`django/dispatch/dispatcher.py`), and sqlparse with a database backend's operations, when the backend is loaded.

**asgiref** is the bridge between synchronous and asynchronous code, and Django's uses of it fall into three groups.

- **Calling code of either kind.** Where Django calls code of the other kind, or code that may be either, it fits it to the caller. `BaseHandler.adapt_method_mode` fits each layer of the middleware chain to its caller: a synchronous layer called by an asynchronous one is wrapped in `sync_to_async`, which runs it on a thread, and the reverse in `async_to_sync`; the centre of the chain fits the view so, and `Signal.send` its asynchronous receivers (`django/core/handlers/base.py:BaseHandler.adapt_method_mode`, `django/dispatch/dispatcher.py:Signal.send`). [Sync and async in one chain](../handlers/async.md) explains the handler's part.
- **The asynchronous methods.** `QuerySet.aget` is `QuerySet.get` run by `sync_to_async`, and `Model.asave` and `BaseCache.aget` are made the same way (`django/db/models/query.py:QuerySet.aget`).
- **State that belongs to a request.** asgiref's `Local` follows a request whether it runs on a thread or as a coroutine. It holds the active language, the active time zone, the current URLconf and each connection handler's connections, though the databases' stay in their thread (`asgiref:asgiref/local.py:Local`, `django/utils/connection.py:BaseConnectionHandler.__init__`).

> **Why.** DEP 9, Andrew Godwin's proposal for an async-capable Django, made asgiref an install-time dependency: `sync_to_async`, `async_to_sync` and `Local` were already written there, in an official Django project (`deps:accepted/0009-async.rst`). It also parted two kinds of per-thread state: a "context local", such as the active language, must follow a request from a coroutine into a thread, and a "true threadlocal", such as a database connection, must not. So the databases' connections are kept in a thread-critical `Local` (`django/db/utils.py:ConnectionHandler.thread_critical`).

**sqlparse** serves the database backends, in three ways. `BaseDatabaseOperations.prepare_sql_script` splits a script into statements for a `RunSQL` operation, a migration's step of raw SQL, given one string; on PostgreSQL it is executed whole (`django/db/migrations/operations/special.py:RunSQL._run_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.prepare_sql_script`, `django/db/backends/postgresql/operations.py:DatabaseOperations.prepare_sql_script`, `sqlparse:sqlparse/__init__.py:split`). `BaseDatabaseOperations.format_debug_sql` lays out a query for the test runner's --debug-sql. And the introspection of SQLite and of MySQL parses SQL the database gives back, such as a table's `"CREATE TABLE"` statement or a check constraint's clause, to find constraints, their columns and, on SQLite, each column's collation (`django/db/backends/sqlite3/introspection.py:DatabaseIntrospection._parse_table_constraints`, `django/db/backends/mysql/introspection.py:DatabaseIntrospection._parse_constraint_columns`).

**tzdata** Django never imports. Its time zones are the standard library's `zoneinfo` (`django/utils/timezone.py:get_default_timezone`), which reads the system's database of time zones and, where there is none, as on Windows, the tzdata package's.

## The database drivers

A database backend's base module imports its driver, the library that talks to the database, at its top, under the name `Database`. The module is imported when the connection of its alias is first asked for (`django/db/utils.py:ConnectionHandler.create_connection`), so a missing driver raises `ImproperlyConfigured` then, naming the driver, in the backends for PostgreSQL, MySQL and Oracle.

- PostgreSQL: `psycopg`, or `psycopg2` where it is absent (`django/db/backends/postgresql/base.py:Database`).
- MySQL and MariaDB: `MySQLdb`, from the mysqlclient package (`django/db/backends/mysql/base.py:Database`).
- Oracle: `oracledb` (`django/db/backends/oracle/base.py:Database`).
- SQLite: the standard library's `sqlite3` (`django/db/backends/sqlite3/base.py:Database`), so a new project, whose settings name SQLite, needs no driver installed.

Each driver raises its own exceptions, under the names PEP 249 gives them. `DatabaseErrorWrapper` raises each error again as Django's class of the same name, so that code above the backend catches one `IntegrityError` whatever the driver (`django/db/utils.py:DatabaseErrorWrapper.__exit__`). The rest is [Database backends](../backends.md).

## The libraries a feature imports

Beyond its requirements, Django imports a library only where a feature needs it, and where the import stands decides when its absence shows. Inside a function, it shows when the function runs, as with the cache clients and the hashers' libraries (`django/contrib/auth/hashers.py:BasePasswordHasher._load_library`). At the top of a module Django imports on demand, it shows then, as Jinja2's does when an engine of `TEMPLATES` uses its backend; PyYAML's is caught when the serializers are first registered, and becomes a stand-in that raises when called (`django/core/serializers/__init__.py:register_serializer`). In a `try` at a module's top, it can set a flag: without docutils, the admin's documentation pages say so (`django/contrib/admindocs/views.py:BaseAdminDocsView.dispatch`).

| library | used by | absence shows | import |
|---|---|---|---|
| Pillow, as `PIL` | `ImageField`, model and form; image sizes; image extensions | at the call | `django/db/models/fields/files.py:ImageField._check_image_library_installed`, `django/forms/fields.py:ImageField.to_python`, `django/core/files/images.py:get_image_dimensions`, `django/core/validators.py:get_available_image_extensions` |
| argon2-cffi | `Argon2PasswordHasher` | at the call | `django/contrib/auth/hashers.py:Argon2PasswordHasher.library` |
| bcrypt | `BCryptSHA256PasswordHasher`, `BCryptPasswordHasher` | at the call | `django/contrib/auth/hashers.py:BCryptSHA256PasswordHasher.library` |
| redis | `RedisCache` | at the call | `django/core/cache/backends/redis.py:RedisCacheClient.__init__` |
| pymemcache | `PyMemcacheCache` | at the call | `django/core/cache/backends/memcached.py:PyMemcacheCache.__init__` |
| pylibmc | `PyLibMCCache` | at the call | `django/core/cache/backends/memcached.py:PyLibMCCache.__init__` |
| Jinja2, as `jinja2` | the Jinja2 template backend; `require_jinja2` | as the module loads; for `require_jinja2`, as a flag | `django/template/backends/jinja2.py:jinja2`, `django/test/utils.py:jinja2` |
| PyYAML, as `yaml` | the YAML serializer | at the call, by a stand-in | `django/core/serializers/pyyaml.py:yaml` |
| docutils | `django.contrib.admindocs` | as a flag | `django/contrib/admindocs/utils.py:docutils_is_available` |
| geoip2 | `GeoIP2` | at the call | `django/contrib/gis/geoip2.py:geoip2` |
| GDAL, a C library, through `ctypes.CDLL` | GeoDjango's spatial references, rasters and vector data | as the module loads | `django/contrib/gis/gdal/libgdal.py:lgdal` |
| GEOS, a C library, through `ctypes.CDLL` | GeoDjango's geometries | as the module loads | `django/contrib/gis/geos/libgeos.py:load_geos` |

*Some of the optional libraries: what uses each, when its absence shows, and where it is imported.*

## The packages built on the extension points

A package built on Django attaches where Django leaves a point open: where it imports what a project names ([How Django is extended](extension-points.md)), or outside it, around the handler or in a process of its own.

| package | attaches to | home |
|---|---|---|
| Channels | around the handler, as an ASGI application that wraps it ([The two entry points](../handlers/entry.md)) | [site](https://channels.readthedocs.io/) |
| WhiteNoise | around the WSGI application, or in `MIDDLEWARE` instead | [site](https://whitenoise.readthedocs.io/) |
| Django Debug Toolbar | `MIDDLEWARE` ([Building the middleware chain](../handlers/chain.md)), and URL patterns | [site](https://django-debug-toolbar.readthedocs.io/) |
| django-allauth | `MIDDLEWARE`, `INSTALLED_APPS` and `AUTHENTICATION_BACKENDS` | [site](https://docs.allauth.org/) |
| django-cors-headers | `MIDDLEWARE` | [repository](https://github.com/adamchainz/django-cors-headers) |
| django-htmx | `MIDDLEWARE` | [site](https://django-htmx.readthedocs.io/) |
| Django REST framework | views and URL patterns ([Views](../views.md)) | [site](https://www.django-rest-framework.org/) |
| Wagtail | `INSTALLED_APPS`, with models ([Settings, apps and startup](../startup.md)) | [site](https://wagtail.org/) |
| django CMS | `INSTALLED_APPS`, with models | [site](https://www.django-cms.org/) |
| django-extensions | `INSTALLED_APPS`, for its commands ([Finding the command](../commands/finding.md)) | [site](https://django-extensions.readthedocs.io/) |
| django-storages | `STORAGES` | [site](https://django-storages.readthedocs.io/) |
| django-redis | `CACHES` | [repository](https://github.com/jazzband/django-redis) |
| django-filter | forms, which it builds ([Forms](../forms.md)) | [site](https://django-filter.readthedocs.io/) |
| crispy-forms | forms, which it renders through a template tag library of its own | [site](https://django-crispy-forms.readthedocs.io/) |
| pytest-django | the test runner's place: pytest runs the tests ([The test framework](../testing.md)) | [site](https://pytest-django.readthedocs.io/) |
| django-environ | the settings module, which calls it ([The settings object](../startup/settings.md)) | [site](https://django-environ.readthedocs.io/) |
| Celery | a process of its own, a worker that reads the settings and uses the ORM | [site](https://docs.celeryq.dev/) |

*Some packages built on Django: the point each attaches to, and its home.*
