---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The parts of Django, and what each leans on

Django's source is a set of packages under `django/`, and their imports stand them in layers, the departments of [What Django is](../introduction.md), each leaning on those beneath it. A few imports run against the layers.

An import at the top of a module is a dependency from the moment the module loads; one inside a function is made when the function runs. The layers are read from the first kind; the second is how a part reaches one above it without loading it.

> **Why.** Comments beside some of those imports give the reason. The database session store imports its model inside a method, which "avoids a circular import" (`django/contrib/sessions/backends/db.py:SessionStore.get_model_class`). Making a test database imports the management package inside the method, so as not to import it "if it isn't needed" (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`).

The figure places the packages in their layers. At the bottom is the **floor**, the utilities, the settings and the app registry, and with them `django/core/exceptions.py`; all the others but `django/core/signals.py` import from these. The data side is the **ORM**, the object-relational mapper in `django/db/`; [What Django is](../introduction.md) draws it beside the presentation side, beneath the view, but their imports put the presentation side above it. An accented arrow runs against the layers.

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
    every package but core/signals.py -> the floor;  conf -> utils
    against the layers: utils -> conf, core/cache, core/mail, http
```

*The packages in layers. An arrow runs from a package to one it imports at module level; an accented arrow runs against the layers. The arrows are a selection: the floor's by the other packages, and every layer's by `django/contrib/`, are one arrow each, and the accented ones are the crossings the text tells.*

## The parts, one by one

The table gives each part, from the floor up, with the chapter that tells it.

| part: what it holds | imports at load | chapter |
|---|---|---|
| `django.utils`: lazy objects, importing by dotted path, data structures, text | in modules that belong to other parts, the mail package, the cache, the request and the response | [The utility layer](../utils.md) |
| `django.core.exceptions`: the exceptions the parts share | nothing | [Django's exceptions: `django.core.exceptions`](../utils/exceptions.md) |
| `django.conf`: the settings | nothing | [Settings, apps and startup](../startup.md) |
| `django.apps`: the app registry | nothing | [Settings, apps and startup](../startup.md) |
| `django.dispatch`: `Signal` | nothing | [Caching, files, mail, signals and tasks](../services.md) |
| `django.core.signals`: a request's signals, `setting_changed` | only `Signal` | [Caching, files, mail, signals and tasks](../services.md) |
| `django.core.mail`: mail | nothing | [Caching, files, mail, signals and tasks](../services.md) |
| `django.core.files`: files | only `setting_changed` | [Caching, files, mail, signals and tasks](../services.md) |
| `django.core.cache`: the cache | the ORM, in its database backend | [Caching, files, mail, signals and tasks](../services.md) |
| `django.core.serializers`: serialization | the ORM | [Caching, files, mail, signals and tasks](../services.md) |
| `django.tasks`: tasks | the ORM's `TextChoices` | [Caching, files, mail, signals and tasks](../services.md) |
| `django.core.checks`: the system checks | the database connections, the caches, the mail package | [The system checks](../commands/checks.md) |
| `django.db`: models, querysets, SQL, backends, migrations | the checks, the files package, the validators, the signals, the serializers, `CommandError` and `OutputWrapper`, the forms | [Models and fields](../models.md), [QuerySets](../querysets.md), [From QuerySet to SQL](../sql.md), [Database backends](../backends.md), [Migrations](../migrations.md) |
| `django.template`: the template engine and its backends, and the libraries of `django.templatetags` | the request and the response, the middleware | [Templates](../templates.md) |
| `django.forms`: forms, fields, widgets, renderers | the template system, a helper module of the ORM | [Forms](../forms.md) |
| `django.http`: the request and the response | the upload handlers, `request_finished`, `DjangoJSONEncoder` | [Requests and responses](../http.md) |
| `django.urls`: the resolver, and the URLconf helpers of `django.conf.urls` | the request and the response; the helpers also the views | [URL routing](../urls.md) |
| `django.views`: the views Django ships | the resolver, the request and the response, the template system, the forms, the ORM | [Views](../views.md) |
| `django.middleware`: the middleware | the resolver, the request and the response | [Handlers and middleware](../handlers.md), [Security](../security.md) |
| `django.core.handlers`: the handler | the resolver, the request and the response, the ORM, the debug views | [Handlers and middleware](../handlers.md) |
| `django.core.management`: the commands | more of the ORM than of any other part | [Management commands](../commands.md) |
| `django.test`: the test framework | the handler, the ORM, the mail package, the template system | [The test framework](../testing.md) |
| `django.contrib`: the applications | every layer | [Authentication, sessions and messages](../auth.md), [The admin](../admin.md), [Content types, static files and the other contrib apps](../contrib.md) |

*Imports at load are what a part's modules import from other parts as they load, the floor aside; a cell is a selection unless it says nothing or only.*

Counted inside functions too, the imports say who uses a part. Nothing outside the tasks package imports the tasks. The packages of the request and the response, the resolver and the middleware never import the ORM, the template system and its libraries, or the forms; of the three, the handler imports only the ORM, to wrap a view in a transaction where a database sets `"ATOMIC_REQUESTS"` (`django/core/handlers/base.py:BaseHandler.make_view_atomic`). The mail package, the files package and `Signal`'s package never import the ORM, nor the ORM the template system.

Beyond the tools and `django/contrib/`, the views are imported only by the handler, the resolver and the URLconf helpers, and the handler only by the modules that make the WSGI and ASGI applications and the development server (`django/core/servers/basehttp.py`). The test framework is imported only by the test command and the static files app's test case; `django/contrib/` by nothing as it loads, and inside functions only by the static tag library, the test client and the test framework's receivers of `setting_changed`.

What follows are imports that run against the layers, from the floor up.

## The floor

The utilities import the settings: `django/utils/timezone.py` reads `TIME_ZONE` and `USE_TZ`, and `BaseConnectionHandler` the setting its subclass names (`django/utils/connection.py:BaseConnectionHandler.configure_settings`). That makes no cycle. The utility modules that `django/conf/__init__.py` loads import nothing of `django.conf`, and `settings` reads the settings module only the first time the settings are needed (`django/conf/__init__.py:LazySettings._setup`), so a utility can import it as it loads and read it later.

Some modules of `django/utils/` belong by subject to another part and import upward; among them, `django/utils/log.py` imports the mail package for `AdminEmailHandler`, and `django/utils/cache.py` the cache and `django.http` ([The utility layer](../utils.md#where-the-other-modules-of-djangoutils-are-told)).

## The services

`django/core/signals.py` defines a request's signals, `request_started`, `request_finished` and `got_request_exception`, with `setting_changed`, and imports only `django.dispatch`. Through it a lower part hears of a request without importing the handler: `django/db/__init__.py` connects `close_old_connections` to the first two, and the cache closes its connections on `request_finished` (`django/core/cache/__init__.py:close_caches`).

The cache's database backend imports the ORM, but the cache loads it only when `CACHES` names it (`django/core/cache/__init__.py:CacheHandler.create_connection`). The serializers stand among the services but lean on the ORM: `django/core/serializers/` writes model instances, and imports `django.db.models` and the app registry as it loads.

The system checks are a tool by purpose, but their imports put them among the services: the models, the fields, the URL resolver and the template backend import `django/core/checks/` as they load. The checks import the database connections, the caches and the mail package as they load, and the resolver and the template engines, among others, only inside functions. Of the mail package they take only `DEFAULT_MAILER_ALIAS`, the key they look up in `MAILERS` (`django/core/checks/mail.py`).

## The data side

The ORM imports from two parts above it as it loads. For the migrations it takes `CommandError` and `OutputWrapper` from the management package (`django/db/migrations/loader.py`, `django/db/migrations/questioner.py`). And `django/db/models/fields/__init__.py` imports `django.forms`, for the method with which a model field makes the form field that edits it (`django/db/models/fields/__init__.py:Field.formfield`).

The forms import back, as they load, only a helper module, `django/db/models/utils.py`, and the rest of the ORM inside functions (`django/forms/models.py:construct_instance`). But Python imports a package before any module in it, so importing the helper loads `django.db.models`.

> **Trap.** A package's imports say what it uses, not what loading it costs. `django/http/` imports nothing of the ORM, yet importing it loads `django.db.models`: `django/http/response.py` takes `DjangoJSONEncoder` from the serializers, whose base module imports the ORM (`django/core/serializers/base.py`). The model fields then import `django.forms`, and the forms the template system.

## The presentation side

The modules of the template engine, its compiler and its context import only the utilities, the exceptions and one another, though an engine always includes, imported by its dotted path, the `csrf` **context processor**, a callable that returns variables for the template from the request (`django/template/engine.py:Engine.template_context_processors`). Four other modules import from the request side. `SimpleTemplateResponse` is a subclass of `HttpResponse` (`django/template/response.py:SimpleTemplateResponse`); the `querystring` tag builds a `QueryDict` (`django/template/defaulttags.py:querystring`); the `csrf` context processor takes the token from `get_token` in `django/middleware/csrf.py` (`django/template/context_processors.py:csrf`); and so does the backends' `csrf_input`.
