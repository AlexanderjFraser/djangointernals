---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: settings, logging, populate, registry, callers, overrides
---

# Settings, apps and startup

Startup makes a Python process a configured Django. `django.conf.settings` loads the module that `"DJANGO_SETTINGS_MODULE"` names at the first read or write of a setting, and `django.setup` populates the app registry, `django.apps.apps`: an `AppConfig` for each entry of `settings.INSTALLED_APPS`, and every application's models imported. Until that call the registry refuses most questions, with `AppRegistryNotReady` where settings can be read.

Importing `django` does almost nothing: the package's own module defines a version and one function (`django/__init__.py`). Yet most other parts of the framework take two things for granted about the process they run in: that there are settings to read, and that the process knows which applications are installed and which models they define. Neither is true of a process that has only imported Django. Making them true is what startup means.

## `settings` and `apps`, made empty

The answers to both questions live in two objects, each made by the last statement of its module.

`django.conf.settings` is a `LazySettings`: a stand-in for the project's settings (`django/conf/__init__.py:settings`). `django.apps.apps` is an `Apps`, the **app registry**: the record of the installed applications and of the model classes (`django/apps/registry.py:apps`). Each is made when its module is first imported, with nothing in it, and every module that imports one of them gets that same object.

Starting empty is what lets any module import the two objects at its top without caring whether startup has happened yet. What a module cannot do is use them too early, and here the two behave differently.

**The settings load themselves.** The first read or write of any setting imports the module named by the environment variable `"DJANGO_SETTINGS_MODULE"` and builds a `Settings` from it, unless `settings.configure` has already filled the settings by hand. Startup never says "load the settings": whichever line of code first reads or writes a setting does it (`django/conf/__init__.py:LazySettings._setup`, `django/utils/functional.py:LazyObject.__setattr__`).

**The registry has to be told.** It stays empty until `Apps.populate` is called with the list of applications, and until then, where settings can be read, it refuses most questions with `AppRegistryNotReady` (`django/apps/registry.py:Apps.populate`, `django/apps/registry.py:Apps.check_apps_ready`).

## `django.setup` is three statements

`django.setup` is the function that takes a process from the one state to the other, from having imported Django to being able to use it (`django/__init__.py:setup`).

1. It configures logging, from `settings.LOGGING_CONFIG` and `settings.LOGGING`, unless `LOGGING_CONFIG` is empty. Where the settings are still empty, reading the first of these is the moment the settings module is imported.
2. It sets the script prefix to `"/"` or to `settings.FORCE_SCRIPT_NAME`, unless its caller asks it not to, as a server's does. The script prefix is the part of a URL's path that belongs to the server's mount point, which the URLs Django generates have to begin with (`django/urls/base.py:set_script_prefix`, `django/urls/base.py:reverse`). Under a server it is set for each request served, to `FORCE_SCRIPT_NAME` or else to what the server says the site is mounted under (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.handle`).
3. It calls `Apps.populate` with `settings.INSTALLED_APPS`.

The figure sets the three statements between the two objects: the first reaches across to the settings, and the third runs the registry's phases, each over every application and each ending in a flag.

```text figure=two-objects
settings                               django.setup()                         apps
a LazySettings, made empty                                                    an Apps, made empty
when django.conf is imported                                                  when django.apps is imported

a Settings: the settings module,  <-   1  configure_logging
imported on the first read or write    reads settings.LOGGING_CONFIG

                                       2  set_script_prefix
                                       unless the caller asks it not to

                                       3  Apps.populate                  ->   AppConfig.create, for each entry of INSTALLED_APPS
                                       with settings.INSTALLED_APPS           then apps_ready is true
                                                                              AppConfig.import_models, for each application
                                                                              then models_ready is true
                                                                              AppConfig.ready, for each application
                                                                              then ready is true
```

*The three statements of `django.setup`: the first imports the settings module where the settings are still empty, and the third populates the app registry.*

Each statement is preceded by the reads of the settings it passes, and `import library.settings` stands nested under the first read. The project, *library*, installs three applications with one model each.

```text recording=startup
django.setup() in a new process
    setup
      LazySettings.__getattr__("LOGGING_CONFIG")
        LazySettings._setup("LOGGING_CONFIG")
          Settings.__init__("library.settings")
            import library.settings
      LazySettings.__getattr__("LOGGING")
      configure_logging("logging.config.dictConfig", {})
        ...
      LazySettings.__getattr__("FORCE_SCRIPT_NAME")
      set_script_prefix("/")
      LazySettings.__getattr__("INSTALLED_APPS")
      Apps.populate
        ...
```

## The registry fills in three phases

`Apps.populate` does not finish one application before starting the next. It runs three passes over the whole list, and what the registry can answer grows with each.

1. **Each entry of `INSTALLED_APPS` becomes an `AppConfig`**, the object that stands for one installed application. Making it imports the application's package. When every entry has one, `Apps.apps_ready` becomes true, and the registry can say which applications are installed.
2. **Each application's `models` module is imported.** Nobody hands the models to the registry: each registers itself, as the last act of its own class statement, so importing the module is enough. When every application has had its turn, `Apps.models_ready` becomes true, and `Apps.get_model` and `Apps.get_models` answer.
3. **Each application's `AppConfig.ready` is called.** This is the place for startup work, such as connecting signal receivers, once every models module is imported. When all have returned, `Apps.ready` becomes true.

The phases are the reason for two rules a project otherwise meets as errors. Nothing imported during the first phase can define a model, not even a model of an application whose configuration is already made, because a model's class statement asks the registry which application it belongs to, and the registry will not say until every entry has its configuration (`django/apps/registry.py:Apps.get_containing_app_config`). A models module cannot fetch another application's model with `Apps.get_model` while the second phase runs, unless it passes `require_ready=False`, and then `get_model` imports that application's models module itself if its turn has not yet come (`django/apps/registry.py:Apps.get_model`). [Populating the app registry](startup/populate.md) follows each phase and what the registry answers during it.

> **History.** Before Django 1.7 a singleton called the app cache dealt with both installed applications and models, and many APIs took an application's models module to stand for the application. 1.7 refactored it into the app registry, in which an application has a configuration object of its own, with a `ready` method, and Django began to import every application's configuration and models as soon as it started, "through a deterministic and straightforward process" that the release notes expected to make import loops easier to diagnose. From then on a script that relied on `"DJANGO_SETTINGS_MODULE"` had to call `django.setup` itself, or meet `AppRegistryNotReady` (`docs/releases/1.7.txt`).

## Who calls `django.setup`

Whatever starts the process calls `django.setup`. Under a server it is `get_wsgi_application` or `get_asgi_application`, which the project's `wsgi.py` or `asgi.py` calls as the server imports it; each calls `django.setup` and then makes the handler, the object the server will call with every request (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`). For a management command it is ordinarily `ManagementUtility.execute`, before it looks for the command (`django/core/management/__init__.py:ManagementUtility.execute`). A script that uses Django on its own calls it by hand. [Who calls `django.setup`](startup/callers.md) has each case.

A call after one that succeeded finds the registry ready, and `Apps.populate` returns at once; but logging is ordinarily configured again, which under a project's `LOGGING` can disable loggers made between the two calls (`django/utils/log.py:configure_logging`; [Logging](startup/logging.md)).

## Settings and the registry are constants of the process

Once `django.setup` has returned, the settings and the registry are treated as constants of the process. Django does not copy them defensively or watch them for changes; it does the opposite, and builds on them things it keeps. `SecurityMiddleware` reads its settings into attributes once, in its constructor, when the middleware chain is made (`django/middleware/security.py:SecurityMiddleware.__init__`). The template engines are made at their first use, from `settings.TEMPLATES` as it then stood, and kept (`django/template/utils.py:EngineHandler.templates`, `django/template/utils.py:EngineHandler.__getitem__`). A model's `_meta` caches lists of fields that depend on which other models exist (`django/db/models/options.py:Options.related_objects`).

So a setting assigned in a running process changes what the next read of it returns, and nothing that was built from the old value (`django/conf/__init__.py:LazySettings.__setattr__`). A test that needs other settings has the test framework's `override_settings`, which wraps a second object around the settings and sends a signal, `setting_changed`, whose receivers discard or redo some of what was built ([Overriding settings](startup/overrides.md)).

## The neighbours

Startup ends where the rest of the book begins. A server's next step is to make a handler, whose constructor builds the middleware chain ([Handlers and middleware](handlers.md)); a command's is to find the command and run it, and a command that asks for them runs the system checks first, those the applications registered in their `ready` methods among them ([Management commands](commands.md)). The class statement that registers a model belongs to [Models and fields](models.md), and the registries of historical models that migrations build for themselves, separate from `django.apps.apps`, to [Historical models: `StateApps` and rendering](migrations/historical-models.md). What startup leaves for the first request, the root URLconf, the template engines and the database connection among it, is listed in [Before the first request](overview/startup.md#what-the-process-keeps).
