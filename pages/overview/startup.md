---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Before the first request

What a process does between importing Django and serving its first request: `django.setup` loads the settings and populates the app registry, which imports every model, and then the handler is made and builds its middleware chain. All of it happens once.

A Django process is not ready to serve a request the moment Django is imported. Importing `django` defines a version and the function `django.setup`, and nothing else. A production WSGI server sets the process up by importing the project's `wsgi.py`, which calls `get_wsgi_application`. That function calls `django.setup` and then returns a new `WSGIHandler` (`django/core/wsgi.py:get_wsgi_application`).

In a process started so, with the applications that `django-admin startproject` installs and one of its own, journal, the nesting shows which call made which: the settings module is imported first inside `django.setup`, the registry's three phases run one after another inside `Apps.populate`, and the middleware are made inside `WSGIHandler.__init__`, the last in the setting first. Each middleware's line names `MiddlewareMixin.__init__` because all seven are built on `MiddlewareMixin`, whose constructor runs when any of them is made (`django/middleware/__init__.py:MiddlewareMixin.__init__`). Phase 2 below says why auth's Group_permissions is registered before auth's Group. Lines are left out, and three dots stand where they were.

```text recording=overview
get_wsgi_application
  setup
    LazySettings._setup: the settings module "journal.settings" is imported
    configure_logging
    Apps.populate
      AppConfig.create("django.contrib.admin")
      ...
      AppConfig.import_models  (auth)
        Apps.register_model(auth.Permission)
        Apps.register_model(auth.Group_permissions)
        Apps.register_model(auth.Group)
      ...
      AdminConfig.ready  (admin)
        ...
        autodiscover
      ...
  WSGIHandler.__init__
    BaseHandler.load_middleware
      MiddlewareMixin.__init__ (XFrameOptionsMiddleware)
      ...
      MiddlewareMixin.__init__ (SecurityMiddleware)
```

## The settings are loaded on first use

`django.setup` does not import the settings module itself. Here the module is imported when `django.setup` reads its first setting, an argument for `configure_logging`, and the recording marks that moment with `LazySettings._setup` (`django/__init__.py:setup`).

`django.conf.settings` is a `LazySettings`, made when `django.conf` is imported and empty until its first use (`django/conf/__init__.py:settings`). Unless the settings were configured by hand, the first read calls `LazySettings._setup`, which takes the module's dotted name from the environment variable `"DJANGO_SETTINGS_MODULE"` and makes a `Settings` from it. Without the variable, it raises `ImproperlyConfigured` (`django/conf/__init__.py:LazySettings._setup`). `Settings.__init__` copies every upper-case name of `django/conf/global_settings.py` onto itself, then imports the project's module and copies its upper-case names over them (`django/conf/__init__.py:Settings.__init__`). Every value read through the proxy is then kept on the proxy itself (`django/conf/__init__.py:LazySettings.__getattr__`).

So the settings module is imported by whichever of many things comes first: a management command, a test runner, or a stray import of a module that reads a setting at import time. The rest find it done. Being lazy, the proxy also lets a process configure the settings by hand, with no module, provided it does so before they are loaded (`django/conf/__init__.py:LazySettings.configure`); [The settings object](../startup/settings.md) has the proxy in full.

## The app registry is populated in three phases

`Apps.populate` is where a project's applications become objects Django can ask about. It holds a lock, returns at once when it has already run, raises if it is entered again while running, and runs three phases over `settings.INSTALLED_APPS` in order (`django/apps/registry.py:Apps.populate`). The figure follows the phases down, each with the flag it sets on the registry and what the registry answers from then on, and ends with the handler, made once `Apps.populate` has returned.

```text figure=three-phases
time runs down; under each phase, after an arrow: the flag it sets, and what the registry answers from then on

get_wsgi_application
  django.setup
    Apps.populate(settings.INSTALLED_APPS)
      phase 1  AppConfig.create for each entry: its module imported, its AppConfig found
               -> apps_ready: which applications are installed; Apps.get_app_config answers
      phase 2  AppConfig.import_models for each: non-abstract models end in Apps.register_model
               -> models_ready: Apps.get_model answers; before, by default: AppRegistryNotReady
      phase 3  AppConfig.ready for each: the admin's ready imports every app's admin module
               -> ready: Apps.populate, called again, returns at once
  WSGIHandler()
    BaseHandler.load_middleware: each class in settings.MIDDLEWARE made, from the last to the first
    the chain: SecurityMiddleware, outermost -> ... -> XFrameOptionsMiddleware -> BaseHandler._get_response
```

*The registry's three phases, then the handler, time running down. An arrow leads from a phase to the flag it sets and what the registry answers from then on, and the frame that opens at a flag holds all that runs after it is set; the accented frame, from `Apps.models_ready` on, is where every model can be asked for. The chain runs from the first middleware in the setting, outermost, to the handler's own method at the centre.*

1. **Each entry becomes an `AppConfig`.** `AppConfig.create` imports the entry's module and looks in its `apps` submodule, if it has one, for the `AppConfig` subclass to use; a dotted path to a configuration class is accepted too (`django/apps/config.py:AppConfig.create`). After this phase `Apps.apps_ready` is true: the registry can say which applications are installed, and `Apps.get_app_config` answers.
2. **Each application's models are imported.** `AppConfig.import_models` imports the application's `models` module if it has one (`django/apps/config.py:AppConfig.import_models`). Importing it runs each model's class statement, where the metaclass, `ModelBase`, builds the class and its `_meta` and registers it if it is not abstract (`django/db/models/base.py:ModelBase.__new__`); [`ModelBase`: a class statement becomes a model](../models/metaclass.md) tells each step. `Apps.register_model` files the class under its application label and lower-case name, the key `Apps.get_model` answers to (`django/apps/registry.py:Apps.register_model`). So models are registered in the order their class statements finish. The through table a many-to-many field makes for itself, such as auth's Group_permissions, is a model made while the fields of the model that declares it are set up, so it is registered before that model (`django/db/models/fields/related.py:ManyToManyField.contribute_to_class`). After this phase `Apps.models_ready` is true, and `Apps.get_model` answers; asked before, it raises `AppRegistryNotReady` by default, even for a model already registered ([Populating the app registry](../startup/populate.md#what-the-registry-answers-phase-by-phase)) (`django/apps/registry.py:Apps.get_model`).
3. **Each application's `ready` runs.** `AppConfig.ready` is the hook for work that needs every model to exist (`django/apps/config.py:AppConfig.ready`). In the admin, `AdminConfig.ready` calls `autodiscover`, which imports the `admin` module of every installed application so that their `ModelAdmin` registrations run (`django/contrib/admin/apps.py:AdminConfig.ready`, `django/utils/module_loading.py:autodiscover_modules`). After this phase `Apps.ready` is true, and a second call of `Apps.populate` returns at once.

## The handler is made, and the chain with it

With the registry ready, `get_wsgi_application` returns a `WSGIHandler`, whose constructor ends by calling `BaseHandler.load_middleware` (`django/core/handlers/wsgi.py:WSGIHandler.__init__`). That method imports each class named in `settings.MIDDLEWARE` and makes it, from the last in the setting to the first. Each is given the layer inside it, wrapped in `convert_exception_to_response`, as the one it will call, and the middleware listed last is given the handler's own `BaseHandler._get_response`. So `SecurityMiddleware`, first in the setting and made last, is the outermost layer, and `XFrameOptionsMiddleware`, made first, the innermost (`django/core/handlers/base.py:BaseHandler.load_middleware`). [Handlers and middleware](../handlers.md) explains the chain.

A middleware's constructor is therefore startup code. `SecurityMiddleware` reads settings into attributes when it is made and never reads them again, and `SessionMiddleware` imports the session engine that `settings.SESSION_ENGINE` names and keeps its session store class (`django/middleware/security.py:SecurityMiddleware.__init__`, `django/contrib/sessions/middleware.py:SessionMiddleware.__init__`).

## What the process keeps

Everything startup makes is kept, and so is some of what the first request makes. The table sets out what the process keeps, when each is made, and where in the source.

| what the process keeps | made | where in the source |
|---|---|---|
| the settings, loaded on their first use and kept value by value | before the first request | `django/conf/__init__.py:LazySettings.__getattr__` |
| the app registry, every model class and its `_meta` | before the first request | `django/apps/registry.py:Apps.populate` |
| the handler and the middleware chain, each middleware made once | before the first request | `django/core/handlers/base.py:BaseHandler.load_middleware` |
| the root resolver, and the URLconf it imports | by the first request that needs it | `django/urls/resolvers.py:_get_cached_resolver` |
| the template engines, their loaders, their tag libraries and their context processors | by the first request that needs them | `django/template/utils.py:EngineHandler.__getitem__` |
| each template the cached loader finds, compiled | by the first request that needs it | `django/template/loaders/cached.py:Loader.get_template` |
| the database connection, which by default is not kept: it is closed when the request ends unless `"CONN_MAX_AGE"` gives it a longer life | by a request that needs it | `django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete` |

The development server makes some of these earlier. Before it serves, the runserver command runs the system checks, unless told to skip them: the check of the URL configuration imports the URLconf, and the check of the templates makes every engine (`django/core/management/commands/runserver.py:Command.inner_run`, `django/core/checks/urls.py:check_url_config`, `django/core/checks/templates.py:check_templates`). [The development server](../commands/runserver.md) follows the command.
