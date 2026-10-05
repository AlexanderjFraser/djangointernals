---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Foundations
contents: settings, overrides, populate, registry, logging, callers
---

# Settings, apps and startup

How a Python process becomes a configured Django: the settings object `django.conf.settings`, the app registry `django.apps.apps`, and `django.setup`, the function every kind of process calls to have both ready.

Importing `django` does almost nothing: the package's own module defines a version and one function (`django/__init__.py`). Yet nearly every other part of the framework takes two things for granted about the process it runs in: that there are settings to read, and that the process knows which applications are installed and which models they define. Neither is true of a process that has only imported Django. Making them true is what startup means, and it happens once in a process's life, before the first request is served or the first command runs.

## Two objects, made empty

The answers to both questions live in two objects, each made by the last statement of its module.

`django.conf.settings` is a `LazySettings`: a stand-in for the project's settings that holds nothing until something reads a setting from it (`django/conf/__init__.py:settings`). `django.apps.apps` is an `Apps`, the **app registry**: the record of the installed applications and of every model class (`django/apps/registry.py:apps`). Each is made when its module is first imported, with nothing in it. Every module that imports one of them gets the same object, so there is one of each in a process.

Starting empty is what lets any module, Django's or a project's, import the two objects at its top without caring whether startup has happened yet. What a module cannot do is use them too early, and here the two behave differently.

**The settings load themselves.** The first read of any setting imports the module named by the environment variable `"DJANGO_SETTINGS_MODULE"` and builds a `Settings` from it. Neither a server nor a command ever says "load the settings": whichever line of code reads a setting first does it, and every later read finds it done (`django/conf/__init__.py:LazySettings._setup`).

**The registry has to be told.** It stays empty until `Apps.populate` is called with the list of applications, and until then it refuses most questions with the exception `AppRegistryNotReady` (`django/apps/registry.py:Apps.populate`, `django/apps/registry.py:Apps.check_apps_ready`).

## `django.setup` is three statements

`django.setup` is the function that takes a process from the one state to the other, from having imported Django to being able to use it (`django/__init__.py:setup`).

1. It configures logging, from `settings.LOGGING_CONFIG` and `settings.LOGGING`. Reading the first of these is a read of a setting, and in a process where nothing has read one before, this is the moment the settings module is imported.
2. It sets the script prefix, the part of a URL's path that belongs to the server's mount point and that the URLs Django generates have to begin with, to `"/"` or to `settings.FORCE_SCRIPT_NAME`. A caller can ask it not to. A server does, because the handler sets the prefix again for each request, from that setting or else from what the server passes; a command has no request to take it from.
3. It calls `Apps.populate` with `settings.INSTALLED_APPS`.

```text figure=two-objects
settings                               django.setup()                         apps
a LazySettings, made empty                                                    an Apps, made empty
when django.conf is imported                                                  when django.apps is imported

a Settings: the settings module,  <-   1  configure_logging
imported on the first read             reads settings.LOGGING_CONFIG

                                       2  set_script_prefix
                                       unless the caller asks it not to

                                       3  Apps.populate                  ->   AppConfig.create, for each entry of INSTALLED_APPS
                                       with settings.INSTALLED_APPS           then apps_ready is true
                                                                              AppConfig.import_models, for each application
                                                                              then models_ready is true
                                                                              AppConfig.ready, for each application
                                                                              then ready is true
```

*The three statements of `django.setup`, and what the first and the third set off: the settings module is imported, and the app registry is populated.*

This is `django.setup` recorded in a new process, for a project of three applications, each with one model. The lines are a selection of the calls made, nested as they were made. `LazySettings.__getattr__` is called when a setting is read for the first time, so each of those lines is a setting that startup was the first to read. Lines have been left out under each `AppConfig.create` and under each model's class statement, the first reads of four more settings among them.

```text recording=startup
django.setup() in a new process
    setup
      LazySettings.__getattr__("LOGGING_CONFIG")
        LazySettings._setup("LOGGING_CONFIG")
          Settings.__init__("library.settings")
            import library.settings
      LazySettings.__getattr__("LOGGING")
      configure_logging("logging.config.dictConfig", {})
        AdminEmailHandler.__init__
          LazySettings.__getattr__("DEFAULT_EXCEPTION_REPORTER")
      LazySettings.__getattr__("FORCE_SCRIPT_NAME")
      set_script_prefix("/")
      LazySettings.__getattr__("INSTALLED_APPS")
      Apps.populate
        AppConfig.create("library.loans")
        AppConfig.create("library.catalogue.apps.CatalogueConfig")
        AppConfig.create("library.members")
        AppConfig.import_models  (loans)
          import library.loans.models
            ModelBase.__new__  (class Loan)
              Apps.register_model(loans.Loan)
        AppConfig.import_models  (catalogue)
          import library.catalogue.models
            ModelBase.__new__  (class Book)
              Apps.register_model(catalogue.Book)
        AppConfig.import_models  (members)
          import library.members.models
            ModelBase.__new__  (class Member)
              Apps.register_model(members.Member)
        Apps.clear_cache
        LoansConfig.ready  (loans)
        AppConfig.ready  (catalogue)
        AppConfig.ready  (members)
```

## The registry fills in three phases

`Apps.populate` does not finish one application before starting the next. It runs three passes over the whole list, and what the registry can answer grows with each.

1. **Each entry of `INSTALLED_APPS` becomes an `AppConfig`**, the object that stands for one installed application. Making it imports the application's package. When every entry has one, `Apps.apps_ready` becomes true, and the registry can say which applications are installed.
2. **Each application's `models` module is imported.** Nobody hands the models to the registry: a model class registers itself, as the last act of its own class statement, so importing the module is enough. When every application has had its turn, `Apps.models_ready` becomes true, and the registry can be asked for a model.
3. **Each application's `AppConfig.ready` is called.** This is the place for work that needs every model to exist, such as connecting signal receivers. When all have returned, `Apps.ready` becomes true.

The phases explain three rules that a project otherwise meets as errors. An application's package, its `__init__`, cannot import the application's models. The package is imported during the first phase, and a model's class statement asks the registry which application it belongs to, which the registry will not say until that phase is complete. A models module cannot simply fetch another application's model from the registry. It is imported during the second phase, and `Apps.get_model` refuses, unless told not to wait, until every models module has been imported. And `ready` exists because it is the first moment at which everything is in place. [Populating the app registry](startup/populate.md) follows each phase, and shows what the registry answers during each.

## Who starts it, and how often

Whatever starts the process calls `django.setup`. Under a server it is `get_wsgi_application` or `get_asgi_application`, which the project's `wsgi.py` or `asgi.py` calls as the server imports it; each calls `django.setup` and then makes the handler, the object the server will call with every request (`django/core/wsgi.py:get_wsgi_application`). For a management command it is `ManagementUtility.execute`, before it looks for the command (`django/core/management/__init__.py:ManagementUtility.execute`). A script that uses Django on its own calls it by hand. [Who calls `django.setup`](startup/callers.md) has each case.

Calling it again is harmless and nearly free. `Apps.populate` returns at once when the registry is ready, and the settings are already loaded. Logging is configured again and the script prefix set again.

```text recording=startup
django.setup() a second time in the same process
    setup
      configure_logging("logging.config.dictConfig", {})
        AdminEmailHandler.__init__
      set_script_prefix("/")
      Apps.populate
```

## After startup, both are meant to stay as they are

Once `django.setup` has returned, the settings and the registry are treated as constants of the process. Django does not copy them defensively or watch them for changes; it does the opposite, and builds on them things it never rebuilds. `SecurityMiddleware` reads its settings into attributes once, in its constructor, when the middleware chain is made (`django/middleware/security.py:SecurityMiddleware.__init__`). The template engines are made once, from `settings.TEMPLATES` as it then stood, and kept. A model's `_meta` caches lists of fields that depend on which other models exist.

So a setting assigned in a running process changes what the next read of it returns, and nothing that was built from the old value. Changing one properly takes more, and the machinery for it belongs to the test framework: [Overriding settings](startup/overrides.md) follows `override_settings`, which wraps a second object around the first and sends a signal, `setting_changed`, whose receivers throw away what was built.

## The neighbours

Startup ends where the rest of the book begins. A server's next step is to make a handler, whose constructor builds the middleware chain ([Handlers and middleware](handlers.md)); a command's is to find and run the command, which is also where the system checks run, those the applications registered in their `ready` methods among them ([Management commands](commands.md)). The class statement that registers a model belongs to [Models and fields](models.md), and the registries of historical models that migrations build for themselves, separate from `django.apps.apps`, to [Migrations](migrations.md). What startup leaves for the first request, the root URLconf, the template engines and the database connection among it, is listed in [Before the first request](overview/startup.md#what-is-still-not-done).
