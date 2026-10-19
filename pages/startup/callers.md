---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Who calls `django.setup`

`django.setup` is called by whatever starts the process: `get_wsgi_application` or `get_asgi_application` under a server, `ManagementUtility.execute` for a management command (through `check_errors` when the command is runserver with its reloader), the startproject and startapp commands where nothing is configured, a test worker that starts from an empty interpreter, and a script by hand. Each also has to say which settings to use, through the environment variable `"DJANGO_SETTINGS_MODULE"` or by calling `settings.configure`.

Django cannot start itself. Importing it starts nothing, and the import of some model or view cannot be the trigger either, because populating the app registry imports the project's code and has to happen from outside it, at a moment when it is safe. So startup is the caller's job. There are few kinds of caller, and the table sets them side by side (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`, `django/core/management/__init__.py:ManagementUtility.execute`, `django/core/management/templates.py:TemplateCommand.handle`, `django/test/runner.py:_init_worker`).

| caller | how the settings are named | the script prefix | what follows `django.setup` |
|---|---|---|---|
| a server, through `get_wsgi_application` or `get_asgi_application` | `"DJANGO_SETTINGS_MODULE"`, set by `wsgi.py` or `asgi.py` unless already set | left to the handler, which sets it for each request | the handler is made, and builds the middleware chain |
| `ManagementUtility.execute`, for a command | the same variable, set by `manage.py` unless already set, or overwritten by `--settings` | `"/"`, or `settings.FORCE_SCRIPT_NAME` | the command is found and run |
| `ManagementUtility.execute`, for runserver with its reloader | as for any command | as for any command | the command runs even if `django.setup` failed, with the registry emptied and marked ready |
| startproject and startapp, with no settings configured | none: `settings.configure()` gives the defaults alone | `"/"` | the files are rendered from templates |
| a test worker started from an empty interpreter | the variable, in the environment it starts with | `"/"`, or `settings.FORCE_SCRIPT_NAME` | the test environment set up again, the worker's own test databases, and the system checks |
| a script | the variable, or `settings.configure` | `"/"`, or `settings.FORCE_SCRIPT_NAME` | its own code, which may now import models |

*The callers of `django.setup`, and what each does around the call.*

## `"DJANGO_SETTINGS_MODULE"` and `--settings`

Before `django.setup` can do anything, the process must be able to load its settings, and for a project with a settings module that means the environment variable `"DJANGO_SETTINGS_MODULE"` must name it by the time a setting is first read.

The three entry files that `django-admin startproject` writes each begin by setting it, and each uses `os.environ.setdefault`, so a value already in the environment wins over the one written in the file (`django/conf/project_template/manage.py-tpl`, `django/conf/project_template/project_name/wsgi.py-tpl`, `django/conf/project_template/project_name/asgi.py-tpl`). That is how one project is run with different settings on different machines without editing any of them.

A management command's `--settings` option writes the same variable later, and unconditionally, so it wins over both: `ManagementUtility.execute` reads that option, and `handle_default_options` assigns its value (`django/core/management/base.py:handle_default_options`). This works only because the settings are lazy. By that point `django.conf` has long been imported, and the object `settings` exists; nothing has yet read from it.

## A server

A WSGI or ASGI server is pointed at a module of the project and imports it. The module calls `get_wsgi_application` or `get_asgi_application`, and each of those is two lines: call `django.setup` with `set_prefix=False`, and return a new handler (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`).

The argument tells `django.setup` to leave the script prefix alone, because under a server the handler sets it for each request, from `settings.FORCE_SCRIPT_NAME` or else from what the server passes with the request (`django/core/handlers/wsgi.py:WSGIHandler.__call__`). Look for what is missing after `configure_logging`: a command's call reads `settings.FORCE_SCRIPT_NAME` there and calls `set_script_prefix`, and here the read of `settings.INSTALLED_APPS` follows at once.

```text recording=startup
get_wsgi_application() in a new process: django.setup(set_prefix=False), then the handler
    get_wsgi_application()
      setup(set_prefix=False)
        ...
        configure_logging("logging.config.dictConfig", {})
        LazySettings.__getattr__("INSTALLED_APPS")
        Apps.populate
      WSGIHandler.__init__
        BaseHandler.load_middleware(is_async=False)
          LazySettings.__getattr__("MIDDLEWARE")
      -> a WSGIHandler
```

The order matters for the handler. Its constructor builds the middleware chain, which imports every middleware class and instantiates it, and middleware modules import models, so the registry has to be ready first. `get_asgi_application` makes the same call of `django.setup`, and an `ASGIHandler`. [Before the first request](../overview/startup.md) records the whole sequence under a server.

## A management command

`manage.py` and `django-admin` both end in `ManagementUtility.execute`, which calls `django.setup` before it has found the command's class (`django/core/management/__init__.py:ManagementUtility.execute`). It first reads `settings.INSTALLED_APPS`, and an `ImproperlyConfigured` from that read is kept for later rather than raised, because some commands need no settings and must work in a directory with no project, startproject among them. It calls `django.setup` only if `settings.configured` is then true, which it is when a read has loaded a settings module or the process had called `settings.configure` before. The command that then runs finds the registry ready. [Finding the command](../commands/finding.md#what-execute-does-before-it-knows-the-command) follows `execute`'s steps in order.

### The development server may start broken

One command is treated differently. For runserver with its reloader, run without `--noreload`, `execute` calls `django.setup` through a wrapper, `check_errors`, and catches whatever comes out. A project with a syntax error in a models module would otherwise end the server at startup, and the point of the reloader is that runserver keeps running while the code is being fixed. The reloader's first process starts a second, its child, running the same command, and starts it again each time the child exits on a change to a file (`django/utils/autoreload.py:restart_with_reloader`).

> **Why.** The runserver command is picked out by its name on the command line, not by an attribute of its class, because the class has not been found yet: "The hardcoded condition is a code smell but we can't rely on a flag on the command class because we haven't located it yet." The failure is set aside because the child will report it: "The exception will be raised later in the child process started by the autoreloader. Pretend it didn't happen by loading an empty list of applications." (`django/core/management/__init__.py:ManagementUtility.execute`)

`check_errors` notes the exception and the file it came from, and raises it again (`django/utils/autoreload.py:check_errors`). `execute` catches it and pretends. It replaces the registry's two maps, `Apps.app_configs` and `Apps.all_models`, with empty ones, and sets the three flags to true by hand, though the registry is not in fact populated. With no application installed, the runserver to be found is the built-in one (`django/core/management/__init__.py:get_commands`), so `execute` takes off the command line any option that the built-in runserver does not know, those of the staticfiles application's runserver among them, and lets the command run.

Under `manage.py runserver --nostatic`, with `INSTALLED_APPS` naming catalogue and misprint, whose models module misspells a field class, `execute` goes on past the line that raises: it calls `ManagementUtility.fetch_command` twice, once for the parser that finds the options to take off and once for the command, which is given the line without `--nostatic`.

```text recording=startup
ManagementUtility(['manage.py', 'runserver', '--nostatic']).execute()
  check_errors.<locals>.wrapper
    setup
      Apps.populate
        ...
              Apps.register_model(catalogue.Book)
        AppConfig.import_models  (misprint)
          import library.misprint.models
            raises AttributeError: module 'django.db.models' has no attribute 'TextFeld'
  ManagementUtility.fetch_command("runserver")
  ManagementUtility.fetch_command("runserver")
  runserver's Command.run_from_argv(['manage.py', 'runserver']), replaced: it writes this line and returns
  ...
```

Two lines of the registry `execute` leaves behind matter: `Apps.all_models`, empty though catalogue's Book was registered above, and `Apps.loading`, still true beside the three flags set by hand.

```text recording=startup
The registry as ManagementUtility.execute() leaves it when django.setup() has failed under runserver
    apps.app_configs  -> {}
    dict(apps.all_models)  -> {}
    apps_ready True, models_ready True, ready True
    apps.loading  -> True
    ...
```

Replacing `Apps.all_models` with an empty dictionary goes against the comment in `Apps.__init__`, which says the map is "never overridden or reset" (`django/apps/registry.py:Apps.__init__`); [The registry and its models](registry.md) gives the comment's reason. `Apps.loading` left true does no harm, since `Apps.populate` returns before it looks at it once `Apps.ready` is true (`django/apps/registry.py:Apps.populate`).

The child goes through `execute` and pretends in the same way, and then its server's thread begins by raising the exception that `check_errors` noted, so that its traceback is printed, while the process waits for a file to change ([The autoreloader](../commands/autoreload.md#a-process-that-starts-broken)).

### Commands that configure for themselves

The startproject and startapp commands render files from templates with Django's template engine, in a directory where there may be no project and so no settings. When nothing is configured, `TemplateCommand.handle` gives the rendering settings of its own: it calls `settings.configure()` with no arguments, which yields the defaults alone, and then `django.setup`, which populates the registry with no applications (`django/core/management/templates.py:TemplateCommand.handle`).

## A test run

Tests are run by a management command, so the process that runs them was started by `execute` like any other. The exception is a parallel run, whose workers each have to be a configured Django too. A worker forked from the test process is a copy of it, with the loaded settings and the populated registry. A worker made any other way, spawned or forked from a separate fork server, has neither, and the function that initializes each worker calls `django.setup` for it (`django/test/runner.py:_init_worker`).

## A script

Code that uses Django outside a server or a command does what they do, in the same order: name the settings, or call `settings.configure`; call `django.setup`; and only then import anything that defines a model. The last condition is the one that is easy to break, because imports are usually written at the top of a file. A model's class statement needs the registry's first phase to be over ([The registry and its models](registry.md#a-model-class-registers-itself)). A script that imports a models module first meets the registry's refusal, in a message that names neither the model nor the missing call of `django.setup`.

```text recording=startup
A models module is imported before django.setup()
    import library.catalogue.models  -> raises AppRegistryNotReady: Apps aren't loaded yet.
```

With `settings.configure`, a script decides for itself what is installed. Called with no `INSTALLED_APPS`, it leaves the default, an empty list, and `django.setup` populates the registry with nothing, which is enough for the parts of Django that need settings and no models (`django/conf/__init__.py:LazySettings.configure`).

## Calling `django.setup` again

A second call in one process is common. The development server makes one: the command has already started Django when it obtains the handler, and obtaining it runs `get_wsgi_application`, which calls `django.setup` again (`django/core/servers/basehttp.py:get_internal_wsgi_application`). The second call finds the registry ready, and `Apps.populate` returns at once (`django/apps/registry.py:Apps.populate`), but it configures logging again, and under a project's `LOGGING` that leaves out `"disable_existing_loggers"` a logger obtained between the two calls can be disabled ([Logging](logging.md)).

Two other calls are refused with `RuntimeError` by `Apps.populate`: a call from inside the first, made by a `ready` method or by code the phases import, and any call after a phase has failed, while `Apps.ready` is false; a call from another thread while the first is running waits for it to finish ([Populating the app registry](populate.md#appspopulate-runs-once-by-one-thread)).
