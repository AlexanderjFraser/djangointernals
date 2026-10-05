---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The system checks

The system check framework is a set of functions, registered in a `CheckRegistry`, that examine a loaded project and return `CheckMessage` objects. `CheckRegistry.run_checks` selects them by tag and calls them; `BaseCommand.check` sorts what they return by level, prints it, and raises `SystemCheckError` when a message is serious enough to stop the command.

Much of what can be wrong with a Django project is wrong before any request arrives: a field declared with an argument missing, two models claiming one table, a URL pattern that can never match, a setting of the wrong type. Python accepts all of it, because none of it is an error until the code that depends on it runs. The checks exist to find such faults early and say what they are. They look at the project as it stands once Django has started, its settings, its models, its URL patterns, its template engines, and do not exercise it.

## Registered, run, reported

The framework keeps apart three things that are easy to run together.

**Registering.** A check is a function that takes the applications to look at and returns a list of messages. It becomes a system check by being registered, which puts it in a set, and that happens as Django starts: when a module is imported, or when an application is made ready.

**Running.** `CheckRegistry.run_checks` picks functions out of the set, calls each, and returns all their messages in one list. It decides nothing about what the messages mean.

**Reporting.** `BaseCommand.check` is the only thing in Django that calls `run_checks`. It takes the list, leaves out the messages the project has silenced, prints the rest grouped by how serious they are, and raises an exception if any is serious enough.

```text figure=the-checks
registered                         run                                  reported
as modules are imported,           CheckRegistry.run_checks             BaseCommand.check
and in AppConfig.ready

registered_checks            ->    with tags: the checks that      ->   silenced, its id in SILENCED_SYSTEM_CHECKS:
deployment_checks                  carry one of them                    counted, and not shown
(joined only for --deploy)         with databases and no tags:
                                   all of them                          below the fail level:
                                   with neither: all but those          printed, and the command goes on
                                   tagged database
                                                                        at the fail level or above:
                                   each is called, and returns          SystemCheckError, and the command does not run
                                   CheckMessage objects
```

*The three steps of a system check. A check function is registered once, may be run many times, and never decides for itself what its messages lead to.*

## The registry

`CheckRegistry` holds two sets of functions, `registered_checks` and `deployment_checks`. There is one registry in a process, made as its module is imported, and the names a project uses are that object's methods: `register`, `run_checks` and `tag_exists` in `django.core.checks` are bound to it (`django/core/checks/registry.py:CheckRegistry`, `django/core/checks/registry.py:registry`).

`CheckRegistry.register` takes a function and any number of **tags**, strings that say what kind of check it is. It can be used as a decorator, with tags or bare, or called with the function first. It writes the tags onto the function and adds the function to the first set, or to the second if it was registered with `deploy=True`. It refuses a function that does not accept arbitrary keyword arguments, with a `TypeError`, so that a keyword argument can be added to what every check is called with and no registered check breaks (`django/core/checks/registry.py:CheckRegistry.register`).

Because the checks are kept in sets, they have no order. A check cannot count on another having run before it, and nothing a check does should matter to the next.

When a function is registered depends on where it lives.

- **Django's core checks** are registered by importing `django.core.checks`. The package's own module imports every module that defines them, and says in a comment that it does so to force registration. A process that has imported the model layer has them (`django/core/checks/__init__.py`).
- **A contrib application's checks** are registered in its `AppConfig.ready`, so only for a project that installs it. The admin, auth, contenttypes, sites and staticfiles applications each do this (`django/contrib/auth/apps.py:AuthConfig.ready`).
- **The check of the task backends** is registered when `django.tasks` is imported, so only in a process that imports that package (`django/tasks/checks.py:check_tasks`).
- **A project's checks** follow one of these patterns: usually an application's `ready` imports the module that defines them.

This is the registry of the recorded project once Django has started. The project installs one contrib application, `django.contrib.staticfiles`, and one of its own applications, trees, registers a check under a tag of its own. The check looks at a setting, TREES_PER_ROW, and returns a warning when it is above 16 and an error when it is above 20.

```text recording=commands
The check registry after django.setup(), by the module that defines each check
    registered_checks
      django.contrib.staticfiles.checks  tagged staticfiles
        check_finders, check_storages
      django.core.checks.caches  tagged caches
        check_default_cache_is_configured, check_file_based_cache_is_absolute
      django.core.checks.commands  tagged commands
        migrate_and_makemigrations_autodetector
      django.core.checks.compatibility.django_4_0  tagged compatibility
        check_csrf_trusted_origins
      django.core.checks.database  tagged database
        check_database_backends
      django.core.checks.files  tagged files
        check_setting_file_upload_temp_dir
      django.core.checks.mail  tagged mail
        check_mailers_default_alias
      django.core.checks.model_checks  tagged models
        check_all_models, check_lazy_references
      ...
      django.core.checks.urls  tagged urls
        check_custom_error_handlers, check_url_config, check_url_namespaces_unique,
        check_url_settings
      trees.checks  tagged trees
        check_trees_per_row
    deployment_checks
      django.core.checks.async_checks  tagged async_support
        check_async_unsafe
      django.core.checks.caches  tagged caches
        check_cache_location_not_exposed
      django.core.checks.mail  tagged mail
        check_mailers_production_backend
      django.core.checks.security.base  tagged security
```

`Tags` gives names to the tags of Django's own checks, as attributes whose values are the same words. A tag is only a string, and a project invents its own by using it. A check may also have none, as the auth application's check of the middleware has, and it is then run only when no tags are asked for (`django/core/checks/registry.py:Tags`).

## One function, many objects

Most of the functions in the list look at a setting or two and are complete in themselves. A few are of another kind: they walk a collection of objects and ask each to check itself.

`check_all_models` is the plainest case. It goes through every model class, or those of the applications it was given, and calls the class's `Model.check`. That method examines the model's own options and asks each of its fields and managers, and each of its indexes and constraints, to check itself. What the function adds of its own is mainly what no single model can know: that two models use one table, or that an index or a constraint has a name another already has (`django/core/checks/model_checks.py:check_all_models`, `django/db/models/base.py:Model.check`).

The same shape recurs. `check_url_config` asks the root URL resolver, which asks every pattern under it. `check_templates` asks each configured template engine. `check_database_backends` asks each connection's validation object. The admin's check asks every admin site, which asks each model admin registered with it whose class is not the plain base class (`django/core/checks/urls.py:check_url_config`, `django/core/checks/templates.py:check_templates`, `django/core/checks/database.py:check_database_backends`, `django/contrib/admin/checks.py:check_admin_app`).

So a kind of object that can be misconfigured has a method named check, and some registered function reaches it. The knowledge of what makes a field or a pattern wrong stays with the field or the pattern, and the chapters on those subsystems are where their checks are told.

## What `run_checks` selects

`CheckRegistry.run_checks` takes four arguments: the applications to check, a collection of tags, whether to include the deployment checks, and a list of database aliases. All four may be left out (`django/core/checks/registry.py:CheckRegistry.run_checks`).

1. It starts from `registered_checks`, with `deployment_checks` added if they were asked for.
2. If tags were given, it keeps the functions that carry at least one of them. If none were given and no databases either, it drops the functions tagged database: those checks, a comment says, do more than static analysis of code.
3. If no databases were given, it takes every configured alias.
4. It calls each remaining function with the applications and the databases as keyword arguments, and adds what the function returns to one list. A function that returns something that cannot be iterated over is a `TypeError`.

The applications are passed through and nothing more. Whether a check narrows its work to them is the check's business: the model check does, and a check of a setting has no reason to.

Step 2 means that the database checks have to be asked for, by a tag or by naming a database. A command that works on one database does the second: migrate overrides `BaseCommand.get_check_kwargs` to pass its database, so that backend's checks run before it migrates (`django/core/management/commands/migrate.py:Command.get_check_kwargs`). It also means that a collection of tags that is given but empty selects nothing at all, which is how runserver keeps `BaseCommand.execute` from running the checks it is about to run itself ([The development server](runserver.md#the-command)).

```text recording=commands
The checks of two tags, one of them the tag that is left out unless asked for, from BaseCommand.execute on
    python manage.py check --database default --tag database --tag trees
      ...
        Command.handle  (django.core.management.commands.check)
          BaseCommand.check(tags=["database", "trees"], display_num_errors=True, databases=["default"])
            CheckRegistry.run_checks(tags=["database", "trees"], databases=["default"])
              -> 2 check functions called; no messages
                 check_database_backends, check_trees_per_row
```

> **Changed in 6.1.** A run that names no database gives the check functions every configured alias, where it used to give them none.

## Messages and levels

What a check returns is a list of `CheckMessage` objects, and a message is five values: a level, the text, an optional hint, the object the message is about, and an id (`django/core/checks/messages.py:CheckMessage`).

The **level** is a number, and five are named: `DEBUG` is 10, `INFO` 20, `WARNING` 30, `ERROR` 40 and `CRITICAL` 50, the scale of Python's `logging` module. Five subclasses, `Debug`, `Info`, `Warning`, `Error` and `Critical`, each fix one, so that a check writes the class and not the number.

The **id** is a short string that names the kind of problem, by convention the area, a letter for the level and a number, as in `"models.E028"`. It is what a project quotes to silence a message.

`CheckMessage.is_serious` says whether its level reaches a given one, an error if none is given. `CheckMessage.is_silenced` says whether its id is listed in `settings.SILENCED_SYSTEM_CHECKS`.

## What `BaseCommand.check` does with them

`BaseCommand.check` calls `run_checks` and then decides what the result means for the command (`django/core/management/base.py:BaseCommand.check`).

It sorts the messages that are not silenced into five groups by level, the most serious first, and builds a report: a header, then each group that has anything in it under its own heading. A message is shown as the object it concerns, or a question mark for none, then its id and text, with the hint on a line below. A caller may ask for a last line that counts the issues and the silenced messages; the check command and runserver do.

Then one test settles the outcome. If any message that is not silenced is serious at the **fail level**, which is an error unless the caller says otherwise, the method raises `SystemCheckError` with the report as its message, and the command goes no further: `handle` is never called. Otherwise the method prints the report and returns. A report that has issues in it goes to standard error; one that is only the count, with nothing found, goes to standard output.

A warning, then, is seen and does not stop anything.

```text recording=commands
A check returns a warning and the command runs, from BaseCommand.execute on
    TREES_PER_ROW=18 python manage.py count 3
      BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, skip_checks=False, rows=3, per_row=None)
        BaseCommand.get_check_kwargs
          -> {}
        BaseCommand.check()
          CheckRegistry.run_checks()
            -> 23 check functions called; trees.W001
          OutputWrapper.write("System check identified some issues:\n\nWARNINGS:\n?: (trees.W001) TREE...")  to stderr
        Command.handle  (trees.management.commands.count)
          OutputWrapper.write("54 trees in 3 rows")  to stdout
      BaseConnectionHandler.close_all  (the database connections)
      stdout | 54 trees in 3 rows
      stderr | System check identified some issues:
      stderr |
      stderr | WARNINGS:
      stderr | ?: (trees.W001) TREES_PER_ROW is 18: the trees will be crowded.
      exit status 0
```

An error stops the command before its own code runs. The exception passes out of `execute`, and `BaseCommand.run_from_argv` catches it as it catches any `CommandError`, writes the report as it stands, and exits with status 1.

```text recording=commands
A check returns an error and the command does not run, from BaseCommand.run_from_argv on
    TREES_PER_ROW=30 python manage.py count 3
      ...
          BaseCommand.check()
            CheckRegistry.run_checks()
              -> 23 check functions called; trees.E001
        OutputWrapper.write("SystemCheckError: System check identified some issues:\n\nERRORS:\n?: (...")  to stderr
        BaseConnectionHandler.close_all  (the database connections)
      stderr | SystemCheckError: System check identified some issues:
      stderr |
      stderr | ERRORS:
      stderr | ?: (trees.E001) TREES_PER_ROW is 30, and a row has room for 20.
      stderr |         HINT: Plant another row.
      exit status 1
```

Silencing is absolute. A silenced message is not printed and cannot stop the command, whatever its level; it survives only as a count in the last line of a report that prints one. Below, the same error is skipped by an option, then silenced, and a warning is made fatal by lowering the fail level. The recorded project copies the variable SILENCED into `settings.SILENCED_SYSTEM_CHECKS`.

```text recording=commands
The same error skipped and silenced, and a warning made to fail
    TREES_PER_ROW=30 python manage.py count 3 --skip-checks
      stdout | 90 trees in 3 rows
      exit status 0
    TREES_PER_ROW=30 SILENCED=trees.E001 python manage.py count 3
      stdout | 90 trees in 3 rows
      exit status 0
    TREES_PER_ROW=30 SILENCED=trees.E001 python manage.py check
      stdout | System check identified no issues (1 silenced).
      exit status 0
    TREES_PER_ROW=18 python manage.py check --fail-level WARNING
      stderr | SystemCheckError: System check identified some issues:
      stderr |
      stderr | WARNINGS:
      stderr | ?: (trees.W001) TREES_PER_ROW is 18: the trees will be crowded.
      stderr |
      stderr | System check identified 1 issue (0 silenced).
      exit status 1
```

## When the checks run

The checks run when a command runs them, and at no other time.

| who | when | which |
|---|---|---|
| `BaseCommand.execute` | before `handle`, for a command whose class asks for checks, unless the options say to skip them | every check but the database ones, or those with one of the tags the class lists |
| the check command | in its `handle` | what its options say: applications, tags, `--deploy`, `--database` |
| migrate | before `handle`, through `execute` | every check, the database ones for the database being migrated |
| runserver | in the serving process, each time it starts | every check but the database ones |
| the test runner | after the test databases are made, by calling the check command | every check, the database ones for the databases the tests use |
| a worker of a parallel test run | as it starts, if it was not forked from the test process, by calling the check command with its output thrown away | the same |

*Where Django runs the system checks. The deployment checks are in none of these runs unless the check command is given `--deploy`.*

The check command is the framework's own front. Its class asks `execute` for no checks and calls `BaseCommand.check` itself, so that its options can shape the run: app labels narrow the applications, `--tag` the tags, `--database` the aliases, `--fail-level` the level that fails, and `--deploy` adds the second set (`django/core/management/commands/check.py:Command.handle`). The test runner's two rows are calls of this command through `call_command` (`django/test/runner.py:DiscoverRunner.run_checks`, `django/test/runner.py:_init_worker`).

```text recording=commands
python manage.py check, from BaseCommand.run_from_argv on
    python manage.py check
      ...
          Command.handle  (django.core.management.commands.check)
            BaseCommand.check(display_num_errors=True)
              CheckRegistry.run_checks()
                -> 23 check functions called; no messages
                   check_all_models, check_csp_nonce_context_processor, check_csp_settings,
                   check_csrf_failure_view, check_csrf_trusted_origins, check_custom_error_handlers,
                   check_default_cache_is_configured, check_file_based_cache_is_absolute, check_finders,
                   check_language_settings_consistent, check_lazy_references, check_mailers_default_alias,
                   check_setting_file_upload_temp_dir, check_setting_language_code, check_setting_languages,
                   check_setting_languages_bidi, check_storages, check_templates, check_trees_per_row,
                   check_url_config, check_url_namespaces_unique, check_url_settings,
                   migrate_and_makemigrations_autodetector
                   and from inside them: import django.core.management.commands.makemigrations
                   and from inside them: import django.core.management.commands.migrate
                   and from inside them: import orchard.urls
                   and from inside them: import orchard.views
                   and from inside them: load_command_class("django.core", "makemigrations")
                   and from inside them: load_command_class("django.core", "migrate")
              OutputWrapper.write("System check identified no issues (0 silenced).")  to stdout
```

The last six lines under `run_checks` are imports and loads that happened inside the check functions, and they have consequences outside this chapter. The URL checks import the project's root URLconf, and with it every module of views the URLconf imports. So any command that runs all the checks imports the URLconf and everything the URLconf imports, and an error raised by importing a view surfaces in a command that has nothing to do with views. And one check loads the migrate and makemigrations commands, to compare an attribute the two must share (`django/core/checks/commands.py:migrate_and_makemigrations_autodetector`).

A server is not in the table. `get_wsgi_application` starts Django and makes a handler, and neither step calls the checks: a project deployed without ever running a command has never been checked. And `call_command` turns off the checks that `execute` would run, unless the caller asks for them ([`call_command`](call-command.md#the-checks-and-their-two-exceptions)).

## The deployment checks

The functions in `deployment_checks` look for settings that are reasonable while developing and wrong in production: debugging left on, no allowed hosts, cookies not marked secure, the security middleware absent. Run by default they would complain about every development setup, so nothing runs them but the check command with `--deploy`. Most are the security checks, which belong to [Security](../security.md).

```text recording=commands
python manage.py check --deploy, for this project
    python manage.py check --deploy
      stderr | System check identified some issues:
      stderr |
      stderr | WARNINGS:
      ...
      stderr | ?: (security.W018) You should not have DEBUG set to True in deployment.
      stderr | ?: (security.W020) ALLOWED_HOSTS must not be empty in deployment.
      stderr |
      stderr | System check identified 6 issues (0 silenced).
      exit status 0
```

All six here are warnings, so the command ends with status 0. A deployment script that wants warnings to stop it passes `--fail-level WARNING` as well.
