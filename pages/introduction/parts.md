---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The parts of Django, and what each leans on

Django's source is a set of packages under `django/`, and their imports stand them in layers, the departments of [What Django is](../introduction.md), each leaning on those beneath it. A few imports run against the layers.

An import at the top of a module is a dependency from the moment the module loads; one inside a function is made when the function runs. The layers are read from the first kind; the second is how a part reaches one above it without loading it.

> **Why.** Comments beside some of those imports give the reason. The database session store imports its model inside a method, which "avoids a circular import" (`django/contrib/sessions/backends/db.py:SessionStore.get_model_class`). Making a test database imports the management package inside the method, so as not to import it "if it isn't needed" (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`). And `django/utils/deprecation.py` still hands out `MiddlewareMixin`, now in `django/middleware/`, but imports it only inside the module's `__getattr__`, which Python calls for a name the module does not define: reading `django.__version__` loads the module, a build backend reads the version before Django's own dependencies are installed, and `django/middleware/` imports one of them, asgiref (`django/utils/deprecation.py:__getattr__`).

The figure places the packages in their layers. At the bottom is the **floor**, the utilities, the settings and the app registry, and with them `django/core/exceptions.py`; every other package imports from it. An accented arrow runs against the layers.

```text figure=layers
django/, in layers from the top

on top: contrib/  -> every layer
the tools: test/  core/management/
    test -> core/handlers;  management -> db
the request side: core/handlers/  views/  http/  urls/ (with conf/urls/)  middleware/
    handlers -> views, db;  views -> http, forms, template;  urls -> http;  middleware -> urls
the presentation side: forms/  template/  templatetags/
    forms -> template, db
    against the layers: template -> http, middleware
the data side: db/
    db -> core/checks, core/signals.py, core/files
    against the layers: db -> forms, core/management
the services: core/checks/  core/signals.py  core/files/  core/cache/  core/serializers/  tasks/
    beneath them: dispatch/  core/mail/
    core/signals.py -> dispatch
    against the layers: core/checks -> db;  core/cache -> db;  core/serializers -> db;  tasks -> db
the floor: conf/  apps/  core/exceptions.py
    beneath them: utils/
    every package -> the floor;  conf -> utils
    against the layers: utils -> conf, core/cache, core/mail;  utils -> http, drawn short, to its name
```

*The packages in layers. An arrow runs from a package to one it imports at module level; an accented arrow runs against the layers. The arrows are a selection, not all there are: the floor's by every package, and every layer's by `django/contrib/`, are one arrow each, and the accented ones are the crossings the text tells.*

## The parts, one by one

The table gives each part, from the floor up: what it holds, what it imports as it loads, what imports it, and the chapter that tells it.

| part: what it holds | imports at load | imported by | chapter |
|---|---|---|---|
| `django/utils/`: lazy objects, importing by dotted path, data structures, text | in modules that belong to other parts, the mail package, the cache, `django.http` | every other package | [The utility layer](../utils.md) |
| `django/core/exceptions.py`: the exceptions the parts share | nothing | | [Django's exceptions: `django.core.exceptions`](../utils/exceptions.md) |
| `django/conf/__init__.py`: the settings | nothing | | [Settings, apps and startup](../startup.md) |
| `django/apps/`: the app registry | nothing | | [Settings, apps and startup](../startup.md) |
| `django/dispatch/`: `Signal` | nothing | | [Caching, files, mail, signals and tasks](../services.md) |
| `django/core/signals.py`: a request's signals, `setting_changed` | only `django.dispatch` | | [Caching, files, mail, signals and tasks](../services.md) |
| `django/core/mail/`: mail | nothing | | [Caching, files, mail, signals and tasks](../services.md) |
| `django/core/files/`: files | only `setting_changed` | | [Caching, files, mail, signals and tasks](../services.md) |
| `django/core/cache/`: the cache | the ORM, in its database backend | | [Caching, files, mail, signals and tasks](../services.md) |
| `django/core/serializers/`: serialization | the ORM | | [Caching, files, mail, signals and tasks](../services.md) |
| `django/tasks/`: tasks | the ORM's `TextChoices` | nothing outside it | [Caching, files, mail, signals and tasks](../services.md) |
| `django/core/checks/`: the system checks | the database connections, the caches, the mail package | | [The system checks](../commands/checks.md) |
| `django/db/`: models, querysets, SQL, backends, migrations | the checks, `django/core/files/`, the validators, the signals, the serializers, `CommandError` and `OutputWrapper`, `django.forms` | never `django/http/`, `django/urls/`, `django/middleware/`, `django/core/mail/`, `django/core/files/`, `django/dispatch/` | [Models and fields](../models.md), [QuerySets](../querysets.md), [From QuerySet to SQL](../sql.md), [Database backends](../backends.md), [Migrations](../migrations.md) |
| `django/template/`, `django/templatetags/`: the template engine and its backends, the libraries a template loads | `django/http/`, `django/middleware/` | never `django/db/`, `django/http/`, `django/urls/`, `django/middleware/`, `django/core/handlers/` | [Templates](../templates.md) |
| `django/forms/`: forms, fields, widgets, renderers | the template system, `django/db/models/utils.py` | never `django/http/`, `django/urls/`, `django/middleware/`, `django/core/handlers/` | [Forms](../forms.md) |
| `django/http/`: the request and the response | the upload handlers of `django/core/files/`, `request_finished`, `DjangoJSONEncoder` | | [Requests and responses](../http.md) |
| `django/urls/`: the resolver, and beside it `django/conf/urls/` | `django/http/`; `django/conf/urls/` also `django/views/` | | [URL routing](../urls.md) |
| `django/views/`: the views Django ships | `django/urls/`, `django/http/`, the template system, the forms, the ORM | beyond the tools and `django/contrib/`, only the handler, `django/conf/urls/`, `django/urls/` | [Views](../views.md) |
| `django/middleware/`: the middleware | `django/urls/`, `django/http/` | | [Handlers and middleware](../handlers.md), [Security](../security.md) |
| `django/core/handlers/`: the handler | `django/urls/`, `django/http/`, the ORM, `django/views/debug.py` | beyond the tools and `django/contrib/`, only `django/core/wsgi.py`, `django/core/asgi.py`, `django/core/servers/basehttp.py` | [Handlers and middleware](../handlers.md) |
| `django/core/management/`: the commands | more of the ORM than of any other part | | [Management commands](../commands.md) |
| `django/test/`: the test framework | the handler, the ORM, the mail package, the template system | only the test command, `django/contrib/staticfiles/testing.py` | [The test framework](../testing.md) |
| `django/contrib/`: the applications | every layer | nothing at load; inside functions, only `django/templatetags/static.py`, `django/test/client.py`, `django/test/signals.py` | [Authentication, sessions and messages](../auth.md), [The admin](../admin.md), [Content types, static files and the other contrib apps](../contrib.md) |

*Imports at load are those beyond the floor: a selection, as the figure's arrows are, unless the cell says nothing or only. Imported by counts import statements, inside a function as well as at load; an empty cell there makes no claim.*

## The floor

The utilities import the settings: `django/utils/timezone.py` reads `TIME_ZONE` and `USE_TZ`, and `BaseConnectionHandler` the setting its subclass names (`django/utils/connection.py:BaseConnectionHandler.configure_settings`). That makes no cycle. The utility modules that `django/conf/__init__.py` imports import nothing of `django.conf`, and `settings` reads the settings module only the first time the settings are needed (`django/conf/__init__.py:LazySettings._setup`), so a utility can import it as it loads and read it later.

Some modules of `django/utils/` belong by subject to another part and import upward: `django/utils/log.py` imports the mail package for `AdminEmailHandler`, and `django/utils/cache.py` the cache and `django.http` ([The utility layer](../utils.md#where-the-other-modules-of-djangoutils-are-told)).

## The services

`django/core/signals.py` defines a request's signals, `request_started`, `request_finished` and `got_request_exception`, with `setting_changed`, and imports only `django.dispatch`. Through it a lower part hears of a request without importing the handler: `django/db/__init__.py` connects `close_old_connections` to the first two (`django/db/__init__.py:close_old_connections`), and the cache closes its connections on `request_finished` (`django/core/cache/__init__.py:close_caches`).

The cache's database backend imports the ORM, but the cache loads it only when `CACHES` names it (`django/core/cache/__init__.py:CacheHandler.create_connection`). The serializers stand among the services but lean on the data side: `django/core/serializers/` writes model instances, and imports `django.db.models` and the app registry as it loads.

The system checks are a tool by purpose, but their imports put them among the services: the models, the fields, the URL resolver and the template backend import `django/core/checks/` as they load, and it imports the database connections, the caches and the mail package as it loads, and the URLconf and the template engines, among others, only inside functions.

## The data side

`django/db/` imports from two parts above it as it loads. For the migrations it takes `CommandError` and `OutputWrapper` from the management package (`django/db/migrations/loader.py`, `django/db/migrations/questioner.py`). And `django/db/models/fields/__init__.py` imports `django.forms`, for the method with which a model field makes the form field that edits it (`django/db/models/fields/__init__.py:Field.formfield`).

The forms import back, as they load, only a helper module, `django/db/models/utils.py`, and the rest of the ORM inside functions (`django/forms/models.py:construct_instance`). But Python imports a package before any module in it, so importing the helper loads `django.db.models`.

> **Trap.** A package's imports say what it uses, not what loading it costs. `django/http/` imports nothing of the ORM, yet importing it loads `django.db.models`: `django/http/response.py` takes `DjangoJSONEncoder` from the serializers, whose base module imports the ORM (`django/core/serializers/base.py`). The model fields then import `django.forms`, and the forms the template system.

## The presentation side

The modules of the template engine, its compiler and its context import only the utilities, the exceptions and one another, though an engine always includes the `csrf` context processor, imported by its dotted path (`django/template/engine.py:Engine.template_context_processors`). Four other modules import from the request side. `SimpleTemplateResponse` is a subclass of `HttpResponse` (`django/template/response.py:SimpleTemplateResponse`); the `querystring` tag builds a `QueryDict` (`django/template/defaulttags.py:querystring`); the `csrf` context processor takes the token from `get_token` in `django/middleware/csrf.py` (`django/template/context_processors.py:csrf`); and so does the backends' `csrf_input`.
