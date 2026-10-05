---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Who calls `django.setup`

`django.setup` is called by whatever starts the process: `get_wsgi_application` or `get_asgi_application` under a server, `ManagementUtility.execute` for a management command, a test worker that starts from an empty interpreter, and a script by hand. Each also has to say which settings to use, usually through the environment variable `"DJANGO_SETTINGS_MODULE"`.

Django cannot start itself. Importing it does nothing, and the import of some model or view cannot be the trigger either, because populating the app registry imports the project's code and has to happen from outside it, at a moment when it is safe. So startup is the caller's job. There are few kinds of caller, and each is a short piece of code.

## Saying which settings

Before `django.setup` can do anything, the process must be able to load its settings, and for a project with a settings module that means the environment variable must name it by the time a setting is first read.

The three entry files that `django-admin startproject` writes each begin by setting it, and each uses `os.environ.setdefault`, so a value already in the environment wins over the one written in the file (`django/conf/project_template/manage.py-tpl`, `django/conf/project_template/project_name/wsgi.py-tpl`, `django/conf/project_template/project_name/asgi.py-tpl`). That is how one project is run with different settings on different machines without editing any of them.

A management command's `--settings` option writes the same variable later, and unconditionally, so it wins over both. `ManagementUtility.execute` parses that one option, and `--pythonpath`, ahead of everything else, and `handle_default_options` assigns the value (`django/core/management/base.py:handle_default_options`). This works only because the settings are lazy. By that point `django.conf` has long been imported, and the object `settings` exists; nothing has yet read from it.

## A server

A WSGI or ASGI server is pointed at a module of the project and imports it. The module calls `get_wsgi_application` or `get_asgi_application`, and each of those is two lines: call `django.setup` with `set_prefix=False`, and return a new handler (`django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`).

The argument tells `django.setup` to leave the script prefix alone. Under a server the handler sets the prefix at the start of each request, from `settings.FORCE_SCRIPT_NAME` or else from what the server passes with the request; a command has no request and gets `"/"`, or `settings.FORCE_SCRIPT_NAME`, for the whole run.

The order matters for the handler. Its constructor builds the middleware chain, which imports every middleware class and instantiates it, and middleware modules import models. All of that runs after the registry is ready. [Before the first request](../overview/startup.md) has a recording of the whole sequence under a server.

## A management command

`manage.py` and `django-admin` both end in `ManagementUtility.execute`, and it decides whether to start Django before it has found the command's class (`django/core/management/__init__.py:ManagementUtility.execute`).

It reads `settings.INSTALLED_APPS` inside a `try`. If that raises `ImproperlyConfigured`, there are no usable settings; the exception is kept for later and the method carries on. Some commands need no settings, startproject among them, and the command line must work for those in an empty directory. A command class says which kind it is with its attribute `BaseCommand.requires_settings`: when the kept exception exists and the command wants settings, `ManagementUtility.fetch_command` prints the exception and exits.

If the read succeeds, the settings are configured, and `execute` calls `django.setup`. The command that then runs finds the registry ready. The list of available commands depends on the same test: without settings it holds only Django's own, and with them it also holds those of every installed application, found by looking in each one's directory (`django/core/management/__init__.py:get_commands`).

### The development server may start broken

One command is treated differently. For runserver with its reloader, `execute` calls `django.setup` through a wrapper and catches whatever comes out. A project with a syntax error in a models module would otherwise kill the server at startup, and the point of the reloader is that the server stays up while the code is being fixed.

The wrapper, `check_errors`, notes the exception and the file it came from before letting it out, and `execute` then swallows it (`django/utils/autoreload.py:check_errors`). `execute` gives the registry an empty set of applications, sets its three flags to true by hand, and lets the command proceed. The registry is not in fact populated.

The reloader runs the server as two processes. The parent does nothing but start the child, and start another whenever one exits asking for it. The child runs the server in a thread of its own, while its main thread watches the project's files. Both processes go through `execute`, so with broken code both fail and both pretend. In the child, the first thing the server's thread does is raise the noted exception again, so the traceback appears and that thread ends (`django/core/management/commands/runserver.py:Command.inner_run`). The main thread goes on watching, the file that failed included, and when one is saved it exits the process with the status that asks the parent for a new child (`django/utils/autoreload.py:restart_with_reloader`). [The autoreloader](../commands/autoreload.md) follows both processes, with a recording of each.

`Apps.ready_event` has its one reader here. Before the watching thread imports the root URLconf and starts to watch, it waits for the event, or for the server's thread to end without it (`django/utils/autoreload.py:BaseReloader.wait_for_apps_ready`). Under runserver the event is already set by then if startup worked, because `django.setup` ran earlier on that same thread. If startup failed it is never set, since setting the flags by hand does not set it, and the wait ends when the server's thread dies.

### Commands that configure for themselves

The startproject and startapp commands render files from templates with Django's template engine, in a directory where there may be no project and so no settings. `TemplateCommand.handle` prepares what its comment calls a stub settings environment for the rendering: when nothing is configured it calls `settings.configure()` with no arguments, which yields the defaults alone, and then `django.setup`, which populates the registry with no applications (`django/core/management/templates.py:TemplateCommand.handle`).

## A test run

Tests are run by a management command, so the process that runs them was started by `execute` like any other. The exception is a parallel run. Each worker process has to be a configured Django too, and whether it is depends on how it was made. A worker forked from the test process is a copy of it, and inherits the loaded settings and the populated registry. A worker made any other way, spawned or forked from a separate fork server, has neither, and the function that initializes each worker calls `django.setup` for it and sets up the test environment again (`django/test/runner.py:_init_worker`).

## A script

Code that uses Django outside a server or a command does what they do, in the same order: name the settings, or call `settings.configure`; call `django.setup`; and only then import anything that defines a model. The last condition is the one that is easy to break, because imports are usually written at the top of a file. A model's class statement needs the registry's first phase to be over, and this is the error when it is not.

```text recording=startup
A models module is imported before django.setup()
    import library.catalogue.models  -> raises AppRegistryNotReady: Apps aren't loaded yet.
```

With `settings.configure`, a script decides for itself what is installed. Called with no `INSTALLED_APPS`, it leaves the default, an empty list, and `django.setup` populates the registry with nothing, which is enough for the parts of Django that need settings and no models.

```text recording=startup
No settings module: settings.configure
    ...
    django.setup()
      Apps.populate([])
```

## Calling it again

A second call in one process is common, and harmless. The development server makes one: the command has already started Django when it obtains the handler, and obtaining it runs `get_wsgi_application`, which calls `django.setup` again (`django/core/servers/basehttp.py:get_internal_wsgi_application`). The second call finds the registry ready and returns from `Apps.populate` at once. Two cases are not harmless, a call made while the first is still running and a call made after the first has failed, and [Populating the app registry](populate.md#once-by-one-thread) has both.
