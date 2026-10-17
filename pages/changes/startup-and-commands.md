---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in settings, startup and the commands

The changes from Django 5.0 to this commit in the settings object, the project templates and the management commands: the email settings deprecated beside `MAILERS`, every database given to the system checks, `BaseCommand.requires_settings`, `BaseCommand.get_check_kwargs`, the shell's automatic imports and listurls.

In 6.1 the settings object began to enforce a deprecation: the email settings that `MAILERS` replaces warn when read as well as when set, and cannot stand beside it. In 6.1 too the system checks began to be given every database when their caller names none, so a check may connect to one. And in 6.2 a command that needs settings is refused in one line when none are named or the module named is the one missing, where it used to start and fail with a traceback; an `ImportError` of any other kind, such as a missing package's, now stops every command.

## The deprecated email settings and `MAILERS`

At this commit the settings object knows the email settings that `MAILERS` replaces, as `DEPRECATED_EMAIL_SETTINGS`: `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `EMAIL_SSL_CERTFILE`, `EMAIL_SSL_KEYFILE` and EMAIL_FILE_PATH. A project that defines them and no `MAILERS` still sends mail through them (`django/core/mail/__init__.py:get_connection`; [What changed in mail and tasks](mail-and-tasks.md)). One that the settings module defines warns as the module loads (`django/conf/__init__.py:Settings.__init__`); one set by `LazySettings.configure`, `override_settings` or an assignment warns as it is set; the first read warns, and the settings object then keeps the value, so that later reads do not warn while it is kept. Setting and reading warn only from code outside Django. A value that Django's own code read first therefore warns no later reader (`django/conf/__init__.py:_show_settings_deprecation_warning`). Nothing warns under 5.2.17 and 6.0.8; 6.1.1 and this commit warn. The transitional settings `USE_BLANK_CHOICE_DASH` and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` warn in the same places when defined or set.

Beside `MAILERS` they are refused. A settings module, or one call of `LazySettings.configure`, that defines both is refused with `ImproperlyConfigured` (`django/conf/__init__.py:_check_email_settings_conflicts`), where 5.2.17 and 6.0.8 load it. Where `MAILERS` is defined, an email setting cannot be read, even one left at its default (`django/conf/__init__.py:LazySettings.__getattr__`). Here settings that define only `MAILERS` are asked for `EMAIL_BACKEND`:

```text recording=changes
settings.EMAIL_BACKEND, when the settings module defines MAILERS and not EMAIL_BACKEND
    5.2.17       'django.core.mail.backends.smtp.EmailBackend'
    6.0.8        'django.core.mail.backends.smtp.EmailBackend'
    6.1.1        AttributeError: The EMAIL_BACKEND setting is not available when MAILERS is defined.
    this commit  AttributeError: The EMAIL_BACKEND setting is not available when MAILERS is defined.
```

Code that still reads an email setting fails in a project that has moved to `MAILERS`. `override_settings` does not check for a conflict, so an override may set one beside `MAILERS` that cannot then be read. [What still warns: the deprecations and the releases that end them](deprecations.md) lists the warnings.

## The system checks and the databases

Since 5.2 `BaseCommand.execute` takes its arguments for `BaseCommand.check` from `BaseCommand.get_check_kwargs`, which a command may override (`django/core/management/base.py:BaseCommand.get_check_kwargs`): migrate adds its database, and runserver names an empty set of tags, which selects no check, and runs the checks itself, naming no tags, as it starts serving (`django/core/management/commands/runserver.py:Command.inner_run`).

6.1 changed what a check is given when no database is named. `CheckRegistry.run_checks` used to pass on `None`, which Django's checks read as no database; at this commit it passes every configured alias, and, where no tags are named either, leaves out the checks tagged database (`django/core/checks/registry.py:CheckRegistry.run_checks`). The notes name the check command; the change is the registry's, and reaches every command whose checks name no database, runserver among them. The aliases reach the model checks, which are not tagged database: a field's backend checks ask MySQL's backend for the field's column type (`django/db/models/fields/__init__.py:Field._check_backend_specific_checks`), and the backend connects to learn its features (`django/db/backends/mysql/base.py:DatabaseWrapper.mysql_server_data`). The habit runs the check command with a MySQL database beside SQLite's and no server, the driver's connect replaced by a stand-in that refuses; the error's text is the stand-in's:

```text recording=changes
call_command("check"): DATABASES names a MySQL database beside SQLite's, and no MySQL server answers
    5.2.17       System check identified no issues (0 silenced).
    6.0.8        System check identified no issues (0 silenced).
    6.1.1        OperationalError: (2003, "Can't connect to MySQL server (refused by a stand-in for MySQLdb.connect)")
    this commit  OperationalError: (2003, "Can't connect to MySQL server (refused by a stand-in for MySQLdb.connect)")
```

The notes say that callers "should be prepared for databases to be accessed" (`docs/releases/6.1.txt`; [The system checks](../commands/checks.md)).

## A settings module that cannot be loaded: `BaseCommand.requires_settings`

`ManagementUtility.execute` reads `settings.INSTALLED_APPS` before it looks a command up, and catches and keeps the `ImproperlyConfigured` that loading the settings may raise (`django/core/management/__init__.py:ManagementUtility.execute`). Until 6.2 it kept an `ImportError` too and ran the command, which failed with a traceback if it read a setting. At this commit `Settings.__init__` turns into `ImproperlyConfigured` an `ImportError` that names the settings module itself (`django/conf/__init__.py:Settings.__init__`). `ManagementUtility.fetch_command` then refuses, with the exception's message and status 1, a command whose `BaseCommand.requires_settings` is true, the default; startproject, startapp, shell and makemessages set it false (`django/core/management/__init__.py:ManagementUtility.fetch_command`). Here `"DJANGO_SETTINGS_MODULE"` names no module; a line gives the exit status and the command's standard error:

```text recording=changes
python -m django check, DJANGO_SETTINGS_MODULE naming a module that does not exist
    5.2.17       exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_nowhere'
    6.0.8        exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_nowhere'
    6.1.1        exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_nowhere'
    this commit  exit 1: No module named 'almanac_nowhere'.
```

The traceback has become one line, as it has where no settings are named at all ([Finding the command](../commands/finding.md)).

Any other `ImportError`, for the module's own package or for a package the module imports that is not installed, is another matter: `Settings.__init__` lets it through, and `ManagementUtility.execute` no longer catches it, so it ends every command before the command is found. Here startproject, which needs no settings, is run with `"DJANGO_SETTINGS_MODULE"` set in its environment to a module that imports a package not installed:

```text recording=changes
python -m django startproject almanac, the settings module importing a package that is not installed
    5.2.17       exit 0
    6.0.8        exit 0
    6.1.1        exit 0
    this commit  exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_missing_package'
```

The 6.2 notes say `BaseCommand.requires_settings` makes configurable "whether to suppress an ImportError escaping from a settings module" (`docs/releases/6.2.txt`); at this commit it decides only where loading the settings raises `ImproperlyConfigured`.

## What startproject, startapp and the shell give a new project

In 6.0 the settings module that startproject writes (`django/conf/project_template/project_name/settings.py-tpl`) lost `DEFAULT_AUTO_FIELD`, and startapp's class lost `AppConfig.default_auto_field`, both `BigAutoField` under 5.2.17, whose default was `AutoField`; 6.0 made `BigAutoField` the default and removed the lines (`docs/releases/6.0.txt`). In 6.1 the settings module gained `MAILERS`, the console backend as `"default"`. Since 6.0 both commands make a missing target directory, parents and all, where 5.2.17 refused (`django/core/management/templates.py:TemplateCommand.handle`).

Since 5.2 the shell fills its namespace before it starts, from the dotted paths `Command.get_auto_imports` returns (`django/core/management/commands/shell.py:Command.get_auto_imports`): in 5.2 the models that `Apps.get_models` lists, and from 6.0, before them, the settings object, the default connection, `django.db.models`, `django.db.models.functions`, `reset_queries` and `django.utils.timezone` ([The commands Django ships](../commands/builtin.md#the-shell)).

## Smaller changes

The rest, by name:

| what | what changed | release | where now |
|---|---|---|---|
| the setting `TIME_ZONE` | checked with `zoneinfo.ZoneInfo` as a settings module loads, where 5.2.17 to 6.1.1 looked for a file under /usr/share/zoneinfo; still not checked on Windows; no release note says so | 6.2 | `django/conf/__init__.py:Settings.__init__` |
| a mistyped choice | on Python 3.14, argparse's error offers the nearest choice | 6.1 | `django/core/management/base.py:CommandParser.__init__` |
| listurls | new ([The URL checks, and listing the patterns](../urls/checks.md)) | 6.2 | `django/core/management/commands/listurls.py:Command.handle` |
| the debug context processor | left out of the `TEMPLATES` that startproject writes, and still in Django | 5.2 | `django/template/context_processors.py:debug` |
