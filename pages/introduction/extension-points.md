---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# How Django is extended

Django is extended at its **extension points**: places where it calls code that need not be its own, named in a setting, handed to a registry or found by a convention. Most are a dotted path in a setting, which `import_string` turns into a class; Django makes an object of it and keeps it for a process, a request, a thread or an asynchronous context, or makes one at each use. Three matter most: the applications a project is made of, the middleware every request passes through, and the backends behind its database, cache, files and mail.

A setting holds a name, not the object, which puts the import off until the object is first wanted. The settings module is imported when a setting is first read, and a module it imported may read the settings in turn: the translation functions read them, so Django's defaults, `django.conf.global_settings`, define a do-nothing one (`django/utils/translation/__init__.py:Trans.__getattr__`, `django/conf/global_settings.py:gettext_noop`). [What Django is](../introduction.md#a-project-names-its-parts) shows a new project's names.

## The pattern

A **dotted path** is a module's path with one more name after the last dot. `import_string` imports the module and returns that attribute of it (`django/utils/module_loading.py:import_string`; [Importing by name: `import_string` and `autodiscover_modules`](../utils/importing.md)).

The default `CACHES` is one extension point whole: its **alias** `"default"`, by which code asks for the backend, names `LocMemCache`, which is called with the alias's `"LOCATION"` and the rest of its dictionary, both empty here. In the figure, look for when the path becomes a class, the base class nothing tests, and what keeps the instance (`django/core/cache/__init__.py:CacheHandler.create_connection`, `asgiref:asgiref/local.py:Local`).

```text figure=the-pattern
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    |  when code in a thread or asynchronous context first asks for caches["default"]
    v
CacheHandler.create_connection("default")
    |  the string under "BACKEND"
    v
import_string(the string)
    |
    v
the class LocMemCache  - - subclasses, unchecked - ->  BaseCache
    |  called with "LOCATION" and the rest of the alias's dictionary
    v
the instance, kept by caches in a Local under "default":
    one for each alias in each thread or asynchronous context, made on first use and kept
```

*The default cache, from its setting to the object that serves it. The solid arrows are the code's steps, in order; the dashed arrow is subclassing, which nothing tests.*

Three of the things the figure shows differ from one point to the next. What is done with the import: most points call a class, the middleware calls a factory, a few name a function and `WSGI_APPLICATION` the application itself, and some import a module with `importlib.import_module` instead, as the database and session engines do.

What the object must be: most points have a base class that Django's own implementations subclass, but a setting's loading code tests it only for the installed applications, the static file finders and the default primary key; elsewhere an object need only have what Django uses of it.

And how long it lives, which is whatever holds it: an object made at import, the request, a `cached_property` or a `functools` cache on what builds it, a `Local` with a value for each thread or asynchronous context, or nothing, so that each use makes a new one.

> **Trap.** An object built from a setting does not see the setting change. `override_settings`, which changes settings for a test, reaches `CACHES` because a receiver of `setting_changed` discards the caches (`django/test/signals.py:clear_cache_handlers`), but not `DEFAULT_EXCEPTION_REPORTER_FILTER` once its filter is made (`django/views/debug.py:get_default_exception_reporter_filter`).

## The installed applications

Each entry of `INSTALLED_APPS` is the path of a package or of an `AppConfig` subclass. `AppConfig.create` imports a package with `importlib.import_module`, taking the configuration class from its submodule called apps where it finds one, and anything else with `import_string`; the class must subclass `AppConfig` (`django/apps/config.py:AppConfig.create`). `Apps.populate` makes the configurations once a process, keeps them in the app registry, imports each application's models module, and last calls each `AppConfig.ready` once, the place for an application's startup code (`django/apps/registry.py:Apps.populate`).

Django also looks inside each installed application by name: for its template tags, commands, migrations and translations with no setting, and for its templates and static files where the settings ask (`django/db/migrations/loader.py:MigrationLoader.migrations_module`; [Settings, apps and startup](../startup.md)).

## The middleware

Each entry of `MIDDLEWARE` is the dotted path of a **factory**, most often the middleware's class: `BaseHandler.load_middleware` imports it and calls it once with the layer inside it, and what it returns is the middleware, called for each request (`django/core/handlers/base.py:BaseHandler.load_middleware`). No base class is asked for, `MiddlewareMixin` being a convenience: the factory must return something other than `None` and may raise `MiddlewareNotUsed` to be left out. A server's handler runs the factories when it is made, once a process ([Building the middleware chain](../handlers/chain.md)).

> **Why.** DEP 5, a Django Enhancement Proposal, rejected a middleware that is a function of the request and the next layer: it left no place for setup done once or for disabling, and Django would have built a chain of closures for each request, where a factory's is built once (`deps:final/0005-improved-middleware.rst`).

## The backends

A **backend** is a pluggable implementation that a setting names, and six kinds share a shape, each with a base class: `BaseDatabaseWrapper`, `BaseCache`, `Storage`, `BaseTaskBackend`, `BaseEmailBackend` and `BaseEngine`. The setting maps each alias to a dictionary whose `"ENGINE"` (in `DATABASES`) or `"BACKEND"` (in `CACHES`, `STORAGES`, `TASKS` and `MAILERS`) names the backend; `TEMPLATES` lists such dictionaries, and an engine's alias is its `"NAME"` or else the next-to-last name of its path, `"django"` for `DjangoTemplates` (`django/template/utils.py:EngineHandler.templates`). An object made at import, such as `caches`, makes the backend for an alias when code asks for it.

They differ in how long a backend lives:

- `caches`, `task_backends` and `connections`, each a `BaseConnectionHandler`, keep one for each alias in each thread or asynchronous context, in a `Local` (`django/utils/connection.py:BaseConnectionHandler.__getitem__`).
- `storages` and `engines` keep one for each alias for the process, made when first asked for, in a dictionary all threads share; the system checks and `get_template`, by default, ask for every engine (`django/core/files/storage/handler.py:StorageHandler`, `django/template/utils.py:EngineHandler`, `django/template/loader.py:get_template`).
- `mailers` makes a new backend at each access, because Django's sending functions had made each backend for one sending, DEP 18 says (`django/core/mail/handler.py:MailersHandler.create_connection`, `deps:accepted/0018-mailers.md`).

A database's `"ENGINE"` names a package, not a class: Django imports its base module and takes the class called DatabaseWrapper from it (`django/db/utils.py:load_backend`, `django/db/utils.py:ConnectionHandler.create_connection`).

## The other settings

Other settings name code, each loaded by `import_string` unless the loader says otherwise: "by module" is `importlib.import_module`. Below, "made" says how long the object lives.

| setting: what it names | made | loaded by |
|---|---|---|
| `AUTH_PASSWORD_VALIDATORS`: dictionaries, a class in each `"NAME"` ([Authentication, sessions and messages](../auth.md)) | once a process | `django/contrib/auth/password_validation.py:get_password_validators` |
| `AUTHENTICATION_BACKENDS`: each a `BaseBackend` ([Authentication, sessions and messages](../auth.md)) | at each use | `django/contrib/auth/__init__.py:load_backend` |
| `CSRF_FAILURE_VIEW`: a view ([Security](../security.md)) | once a process | by `get_callable`: `django/middleware/csrf.py:_get_failure_view` |
| `DATABASE_ROUTERS`: paths of router classes, or routers; no base class ([Database backends](../backends.md)) | once a process | `django/db/utils.py:ConnectionRouter.routers` |
| `DEFAULT_AUTO_FIELD`: a subclass of `AutoField`, tested ([Models and fields](../models.md)) | once a model without its own primary key | `django/db/models/options.py:Options._get_default_pk_class` |
| `DEFAULT_EXCEPTION_REPORTER`: an `ExceptionReporter` ([Views](../views.md)) | at each use | `django/views/debug.py:get_exception_reporter_class` |
| `DEFAULT_EXCEPTION_REPORTER_FILTER`: a `SafeExceptionReporterFilter` ([Views](../views.md)) | once a process | `django/views/debug.py:get_default_exception_reporter_filter` |
| `FILE_UPLOAD_HANDLERS`: each a `FileUploadHandler` ([Requests and responses](../http.md)) | once a request | `django/http/request.py:HttpRequest._initialize_handlers` |
| `FORM_RENDERER`: a `BaseRenderer` ([Forms](../forms.md)) | once a process | `django/forms/renderers.py:get_default_renderer` |
| `FORMAT_MODULE_PATH`: packages of format modules by locale ([Internationalization and time zones](../i18n.md)) | once a language | by module: `django/utils/formats.py:iter_format_modules` |
| `LOGGING_CONFIG`: a function, given `LOGGING` ([Settings, apps and startup](../startup.md)) | once, by `django.setup`; called only if `LOGGING` is not empty | `django/utils/log.py:configure_logging` |
| `MESSAGE_STORAGE`: a `BaseStorage` ([Authentication, sessions and messages](../auth.md)) | once a request | `django/contrib/messages/storage/__init__.py:default_storage` |
| `MIGRATION_MODULES`: an application's migrations package ([Migrations](../migrations.md)) | once a loader | by module: `django/db/migrations/loader.py:MigrationLoader.load_disk` |
| `PASSWORD_HASHERS`: each a `BasePasswordHasher` ([Authentication, sessions and messages](../auth.md)) | once a process | `django/contrib/auth/hashers.py:get_hashers` |
| `ROOT_URLCONF`, no default: the root URLconf ([URL routing](../urls.md)) | once a process | by module: `django/urls/resolvers.py:URLResolver.urlconf_module` |
| `SERIALIZATION_MODULES`, no default: a module for each format ([Caching, files, mail, signals and tasks](../services.md)) | once a process | by module: `django/core/serializers/__init__.py:_load_serializers` |
| `SESSION_ENGINE`: a module with a `SessionBase` store ([Authentication, sessions and messages](../auth.md)) | the module once a process; a store once a request | by module: `django/contrib/sessions/middleware.py:SessionMiddleware.__init__` |
| `SESSION_SERIALIZER`: a class like `django.core.signing.JSONSerializer` ([Authentication, sessions and messages](../auth.md)) | once a session store | `django/contrib/sessions/backends/base.py:SessionBase.__init__` |
| `SIGNING_BACKEND`: a `Signer` ([Security](../security.md)) | at each use | `django/core/signing.py:get_cookie_signer` |
| `STATICFILES_FINDERS`: each a `BaseFinder`, tested ([Content types, static files and the other contrib apps](../contrib.md)) | once a process | `django/contrib/staticfiles/finders.py:get_finder` |
| `TEMPLATES`' `"OPTIONS"`: loaders, each a `django.template.loaders.base.Loader`; context processors; tag modules ([Templates](../templates.md)) | once an engine | tag modules by module: `django/template/engine.py:Engine` |
| `TEST_RUNNER`: a `DiscoverRunner` ([The test framework](../testing.md)) | once a test run | by `__import__`: `django/test/utils.py:get_runner` |
| `WSGI_APPLICATION`: the application itself ([Management commands](../commands.md)) | once, by runserver | `django/core/servers/basehttp.py:get_internal_wsgi_application` |

*"Tested": the class is checked against its base. "No default": not in `django/conf/global_settings.py`.*

## Registries

Some extension points are not settings: an object handed to a registry, or a module Django finds by name (`django/template/backends/django.py:get_template_tag_modules`, `django/core/management/__init__.py:get_commands`).

| registry: what it holds | registered by, or found in | lifetime | chapter |
|---|---|---|---|
| template tag libraries: modules with a `Library` | each application's templatetags package | once an engine | [Templates](../templates.md) |
| lookups and transforms, what follows the fields in a filter: `Lookup` and `Transform` classes, tested on use | `django/db/models/query_utils.py:RegisterLookupMixin.register_lookup` | held by the class, or the field, it is registered on; an instance for each filter | [QuerySets](../querysets.md) |
| system checks: functions that return messages | `django/core/checks/registry.py:CheckRegistry.register` | held for the process; called at each run of the checks | [The system checks](../commands/checks.md) |
| the admin: a `ModelAdmin` for each model, on the site whose class `SimpleAdminConfig.default_site` names | each application's admin module, which calls `django/contrib/admin/sites.py:AdminSite.register` | once a process | [The admin](../admin.md) |
| management commands: each a `BaseCommand` | each application's management/commands directory | the list once a process; a command at each use | [Management commands](../commands.md) |

## Signals: Django calling out

A setting or a registry hands Django code to call when needed. A **signal** is Django announcing an event, as a request starts and finishes or a model is saved, by calling the **receivers**, the functions connected to the `Signal` Django made for it (`django/dispatch/dispatcher.py:Signal.send`). [The signals Django sends](../services/builtin-signals.md) lists them.
