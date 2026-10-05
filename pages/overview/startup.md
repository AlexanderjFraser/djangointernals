---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Before the first request

What a process does between importing Django and serving its first request: `django.setup` loads the settings and populates the app registry, which imports every model, and then the handler is made and builds its middleware chain. All of it happens once.

A Django process is not ready to serve a request the moment Django is imported. Importing `django` defines a version and the function `django.setup`, and nothing else. What makes the process one that can answer requests is a sequence of three things, run once, in this order: the settings are loaded, the applications and their models are imported and registered, and a handler is made. A server starts that sequence by importing the project's `wsgi.py`, which calls `get_wsgi_application` (`django/core/wsgi.py:get_wsgi_application`). This is the recording of a process doing so, with the applications that `django-admin startproject` installs and one application of its own, journal, which has one model.

```text recording=overview
The process starts: a server imports journal/wsgi.py
    get_wsgi_application
      setup
        LazySettings._setup: the settings module "journal.settings" is imported
        configure_logging
        Apps.populate
          AppConfig.create("django.contrib.admin")
          AppConfig.create("django.contrib.auth")
          AppConfig.create("django.contrib.contenttypes")
          AppConfig.create("django.contrib.sessions")
          AppConfig.create("django.contrib.messages")
          AppConfig.create("django.contrib.staticfiles")
          AppConfig.create("journal")
          AppConfig.import_models  (admin)
            Apps.register_model(contenttypes.ContentType)
            Apps.register_model(admin.LogEntry)
          AppConfig.import_models  (auth)
            Apps.register_model(auth.Permission)
            Apps.register_model(auth.Group_permissions)
            Apps.register_model(auth.Group)
            Apps.register_model(auth.User_groups)
            Apps.register_model(auth.User_user_permissions)
            Apps.register_model(auth.User)
          AppConfig.import_models  (contenttypes)
          AppConfig.import_models  (sessions)
            Apps.register_model(sessions.Session)
          AppConfig.import_models  (messages)
          AppConfig.import_models  (staticfiles)
          AppConfig.import_models  (journal)
            Apps.register_model(journal.Entry)
          AdminConfig.ready  (admin)
            SimpleAdminConfig.ready  (admin)
            autodiscover
          AuthConfig.ready  (auth)
          ContentTypesConfig.ready  (contenttypes)
          AppConfig.ready  (sessions)
          MessagesConfig.ready  (messages)
          StaticFilesConfig.ready  (staticfiles)
          AppConfig.ready  (journal)
      WSGIHandler.__init__
        BaseHandler.load_middleware
          MiddlewareMixin.__init__ (XFrameOptionsMiddleware)
          MiddlewareMixin.__init__ (MessageMiddleware)
          MiddlewareMixin.__init__ (AuthenticationMiddleware)
          MiddlewareMixin.__init__ (CsrfViewMiddleware)
          MiddlewareMixin.__init__ (CommonMiddleware)
          MiddlewareMixin.__init__ (SessionMiddleware)
          MiddlewareMixin.__init__ (SecurityMiddleware)
```

`get_wsgi_application` does two things: it calls `django.setup`, and it returns a new `WSGIHandler`. `django.setup` itself is three lines: configure logging, set the script prefix (the part of the path the server mounted Django under) when asked to, and populate the app registry from `settings.INSTALLED_APPS` (`django/__init__.py:setup`). Everything else in the recording is what those lines set off.

## The settings are loaded on first use

The settings module is not imported by `django.setup`. It is imported by the first line of `django.setup` touching a setting, which is the moment the recording marks with `LazySettings._setup`.

`django.conf.settings` is a `LazySettings`, made when `django.conf` is imported and empty until something reads an attribute of it (`django/conf/__init__.py:settings`). The first read calls `LazySettings._setup`, which takes the module's dotted name from the environment variable `"DJANGO_SETTINGS_MODULE"` and makes a `Settings` from it; if the variable is not set and nobody has called `LazySettings.configure`, it raises `ImproperlyConfigured` with the familiar message about settings not being configured (`django/conf/__init__.py:LazySettings._setup`). `Settings.__init__` first copies every upper-case name of `django/conf/global_settings.py` onto itself, then imports the project's module and copies its upper-case names over them, remembering which ones the project set explicitly. It also checks that the five settings which must be lists or tuples are, and, where the platform allows, moves the time zone into the environment (`django/conf/__init__.py:Settings.__init__`). Every value read through the proxy is then kept on the proxy itself, so a setting is looked up once per process (`django/conf/__init__.py:LazySettings.__getattr__`).

This is why the settings module may be imported by the first of many things: a management command, a test runner, or a stray import of a module that reads a setting at import time. Whichever comes first does it, and the rest find it done. [The settings object](../startup/settings.md) has the proxy in full.

## The app registry is populated in three phases

`Apps.populate` is where a project's applications become objects Django can ask about. It holds a lock, returns at once when it has already run, raises if it is entered again while running, and runs three phases over `settings.INSTALLED_APPS` in order (`django/apps/registry.py:Apps.populate`).

1. **Each entry becomes an `AppConfig`.** `AppConfig.create` imports the entry's module and looks for an `apps` submodule with one `AppConfig` subclass in it; a dotted path to a configuration class is accepted too (`django/apps/config.py:AppConfig.create`). Labels must be unique. After this phase `Apps.apps_ready` is true, and the registry can say which applications are installed; the models modules are the next phase's work.
2. **Each application's models are imported.** `AppConfig.import_models` imports the application's `models` module if it has one (`django/apps/config.py:AppConfig.import_models`). Importing it runs each model's class statement, and a model's class statement is where the ORM does its setup: the metaclass `ModelBase.__new__` builds the class's `_meta`, an `Options`, moves each field onto it, gives the class its three exceptions, DoesNotExist, MultipleObjectsReturned and NotUpdated, adds a default manager named `objects` if the class declares none, and finally registers the class with the registry (`django/db/models/base.py:ModelBase.__new__`, `django/db/models/base.py:ModelBase._prepare`). `Apps.register_model` files it under its application label and lower-case name, which is the key `Apps.get_model` later answers to (`django/apps/registry.py:Apps.register_model`). The order in the recording is the order in which class statements finish. The admin's models module imports the content types model, so that one is registered during the admin's turn and nothing is left for its own application's; and the through table of a many-to-many field, auth's Group_permissions among them, is a model that the field makes while its own model's fields are being set up, so it is registered before the model that declares the field. After this phase `Apps.models_ready` is true.
3. **Each application's `ready` runs.** `AppConfig.ready` is the hook for work that needs every model to exist (`django/apps/config.py:AppConfig.ready`). The admin's is the one with a visible effect: `AdminConfig.ready` calls `autodiscover`, which imports the `admin` module of every installed application so that their `ModelAdmin` registrations run (`django/contrib/admin/apps.py:AdminConfig.ready`, `django/utils/module_loading.py:autodiscover_modules`). The auth application's connects receivers to `post_migrate`, so that permissions are created after each migration, and registers system checks (`django/contrib/auth/apps.py:AuthConfig.ready`). After this phase `Apps.ready` is true.

The order of the phases is the reason an application's models module must not touch another application's models at import time through the registry, and the reason `ready` exists: in phase two the registry is not complete, and in phase three it is. [Populating the app registry](../startup/populate.md) records what the registry answers during each.

## The handler is made, and the chain with it

With the registry ready, `get_wsgi_application` returns a `WSGIHandler`. Its constructor ends by calling `BaseHandler.load_middleware`, which imports each class named in `settings.MIDDLEWARE` and instantiates it, last first, each given the layer before it as the one it will call, the last in the setting being given the handler's own `BaseHandler._get_response`, so that the first in the setting is the outermost layer (`django/core/handlers/wsgi.py:WSGIHandler.__init__`, `django/core/handlers/base.py:BaseHandler.load_middleware`). [Handlers and middleware](../handlers.md) explains the chain; what matters here is when the constructors run. A middleware's constructor is startup code. `SecurityMiddleware` reads nine settings into attributes when it is made and never again; `SessionMiddleware` imports the session engine named by `settings.SESSION_ENGINE` and keeps the engine's session store class, which for the default engine is the `SessionStore` of `django/contrib/sessions/backends/db.py` (`django/middleware/security.py:SecurityMiddleware.__init__`, `django/contrib/sessions/middleware.py:SessionMiddleware.__init__`).

## What is still not done

Three things one might expect at startup are deferred to the first request that needs them, and the next sections show each happening.

- **The root URLconf is not imported.** The resolver is made on the first request, and it imports `settings.ROOT_URLCONF` the first time its patterns are asked for (`django/urls/resolvers.py:URLResolver.urlconf_module`).
- **No template engine exists.** The engines named in `settings.TEMPLATES` are made the first time a template is asked for, and each engine's loaders the first time it looks for one (`django/template/utils.py:EngineHandler.__getitem__`).
- **No database connection is open.** A connection is opened by the first query that needs a cursor (`django/db/backends/base/base.py:BaseDatabaseWrapper.ensure_connection`).

Under the development server all three come earlier. The runserver command (`django/core/management/commands/runserver.py`) runs the system checks before it serves: the check of the URL configuration asks the resolver for its patterns, which imports the URLconf, and the check of the templates asks for every engine, which makes them (`django/core/checks/urls.py:check_url_config`, `django/core/checks/templates.py:check_templates`); it then looks for unapplied migrations, which opens a database connection, and closes every connection before it serves (`django/core/management/commands/runserver.py:Command.inner_run`). The server then obtains the handler by importing the object `settings.WSGI_APPLICATION` names, which is the same `wsgi.py` a production server would import, and hands it to a `WSGIServer` to serve for ever (`django/core/servers/basehttp.py:get_internal_wsgi_application`, `django/core/servers/basehttp.py:run`). A management command's process runs `django.setup` too, before the command, so the first two stages above are the same for a command as for a server; the third is a server's, and runserver's, and the test client makes a handler of its own to drive the chain without a server (`django/core/management/__init__.py:ManagementUtility.execute`). [The development server](../commands/runserver.md) follows the command and the server it runs.
