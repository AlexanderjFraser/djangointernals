---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in settings, startup and the commands

The email settings that `MAILERS` replaces, warned of and refused beside it; the system checks and the databases; a settings module that fails to load, and `BaseCommand.requires_settings`; what startproject, startapp and the shell give a project.

In 6.1 the settings object began to enforce a deprecation. The email settings that `MAILERS` replaces warn when read as well as when set, and are refused beside it. In 6.1 too the system checks began to be given every database when their caller names none, so a check may connect to one. Since 6.2 Django's own commands that need settings are refused in one line when none are named, or when the module named is the one missing. They used to start, and fail with a traceback if they read a setting. An `ImportError` of any other kind now stops every command.

## The deprecated email settings and `MAILERS`

Since 6.1 a project names its mail backends by alias in `MAILERS` ([What changed in mail and tasks](mail-and-tasks.md)). The email settings it replaces warn ([What still warns: the deprecations and the releases that end them](deprecations.md)), and beside it they are refused. `django.conf` lists them in `DEPRECATED_EMAIL_SETTINGS`: `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `EMAIL_SSL_CERTFILE`, `EMAIL_SSL_KEYFILE` and EMAIL_FILE_PATH. A project that defines them and no `MAILERS` still sends mail through them (`django/core/mail/__init__.py:get_connection`).

An email setting that the settings module defines warns as the module loads (`django/conf/__init__.py:Settings.__init__`). One set by `LazySettings.configure`, `override_settings` or an assignment warns as it is set. The first read warns too. The settings object then keeps the value, and later reads do not warn while it is kept. Setting and reading warn only from code outside Django, so a value that Django's own code read first warns no later reader (`django/conf/__init__.py:_show_settings_deprecation_warning`). The transitional settings `USE_BLANK_CHOICE_DASH` and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` warn in the same places when defined or set.

A settings module that defines an email setting beside `MAILERS` is refused with `ImproperlyConfigured`, and so is one call of `LazySettings.configure` given both (`django/conf/__init__.py:_check_email_settings_conflicts`). Under 5.2.17 and 6.0.8 such a module loads. Where `MAILERS` is defined, an email setting cannot be read, even one left at its default (`django/conf/__init__.py:LazySettings.__getattr__`). Asked for `EMAIL_BACKEND`, settings that define only `MAILERS` used to hand back a default the project never chose:

```text recording=changes
settings.EMAIL_BACKEND, when the settings module defines MAILERS and not EMAIL_BACKEND
    5.2.17       'django.core.mail.backends.smtp.EmailBackend'
    6.0.8        'django.core.mail.backends.smtp.EmailBackend'
    6.1.1        AttributeError: The EMAIL_BACKEND setting is not available when MAILERS is defined.
    this commit  AttributeError: The EMAIL_BACKEND setting is not available when MAILERS is defined.
```

Code that still reads an email setting fails in a project that has moved to `MAILERS`. `override_settings` does not check for a conflict, and may set an email setting beside `MAILERS` that cannot then be read.

## The system checks and the databases

Since 6.1 the system checks are given every database when their caller names none, and a check may connect to one. `CheckRegistry.run_checks` used to pass on `None`, which Django's checks read as no database. It now passes every configured alias. Where no tags are named either, it leaves out the checks tagged database (`django/core/checks/registry.py:CheckRegistry.run_checks`). The notes name the check command, but the change is the registry's. It reaches every command whose checks name no database, runserver among them.

The aliases reach the model checks, which are not tagged database. A field's backend checks ask MySQL's backend for the field's column type (`django/db/models/fields/__init__.py:Field._check_backend_specific_checks`), and the backend connects to learn its features (`django/db/backends/mysql/base.py:DatabaseWrapper.mysql_server_data`). With a MySQL database beside SQLite's and no server to answer, the check command now fails to connect where it found no issues. The refusal comes from a stand-in for the driver's connect:

```text recording=changes
call_command("check"): DATABASES names a MySQL database beside SQLite's, and no MySQL server answers
    5.2.17       System check identified no issues (0 silenced).
    6.0.8        System check identified no issues (0 silenced).
    6.1.1        OperationalError: (2003, "Can't connect to MySQL server (refused by a stand-in for MySQLdb.connect)")
    this commit  OperationalError: (2003, "Can't connect to MySQL server (refused by a stand-in for MySQLdb.connect)")
```

The notes say that callers "should be prepared for databases to be accessed" (`docs/releases/6.1.txt`; [The system checks](../commands/checks.md)).

Since 5.2 `BaseCommand.execute` takes its arguments for `BaseCommand.check` from `BaseCommand.get_check_kwargs`, which a command may override (`django/core/management/base.py:BaseCommand.get_check_kwargs`). The migrate command adds its database; runserver runs the checks itself as it starts serving, with no database named (`django/core/management/commands/runserver.py:Command.inner_run`).

## A settings module that cannot be loaded: `BaseCommand.requires_settings`

Since 6.2 Django's own commands that need settings are refused in one line when none are named, or when the module named is the one missing ([Finding the command](../commands/finding.md)). `Settings.__init__` turns an `ImportError` that names the settings module itself into `ImproperlyConfigured` (`django/conf/__init__.py:Settings.__init__`), which `ManagementUtility.execute` keeps. `ManagementUtility.fetch_command` then refuses a command whose `BaseCommand.requires_settings` is true, with the exception's message (`django/core/management/__init__.py:ManagementUtility.fetch_command`). The attribute is true by default, and startproject, startapp, shell and makemessages set it false.

Until 6.2 `execute` kept an `ImportError` too and ran the command, which failed with a traceback if it read a setting (`django/core/management/__init__.py:ManagementUtility.execute`). When `"DJANGO_SETTINGS_MODULE"` names a missing module, the check command's traceback is the old behaviour and its one line the new; each line is the exit status and standard error:

```text recording=changes
python -m django check, DJANGO_SETTINGS_MODULE naming a module that does not exist
    5.2.17       exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_nowhere'
    6.0.8        exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_nowhere'
    6.1.1        exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_nowhere'
    this commit  exit 1: No module named 'almanac_nowhere'.
```

Any other `ImportError` ends every command before the command is found: one for the module's own package, or for a package the module imports that is not installed. `Settings.__init__` lets it through, and `execute` no longer catches it. Even startproject, which needs no settings, now stops when `"DJANGO_SETTINGS_MODULE"` names a module that imports a package not installed; exit 0 is the old behaviour:

```text recording=changes
python -m django startproject almanac, the settings module importing a package that is not installed
    5.2.17       exit 0
    6.0.8        exit 0
    6.1.1        exit 0
    this commit  exit 1, a traceback ending ModuleNotFoundError: No module named 'almanac_missing_package'
```

The 6.2 notes say `requires_settings` makes configurable "whether to suppress an ImportError escaping from a settings module" (`docs/releases/6.2.txt`). At this commit it decides only where loading the settings raises `ImproperlyConfigured`.

## What startproject, startapp and the shell give a new project

In 6.0 the settings module that startproject writes lost `DEFAULT_AUTO_FIELD` (`django/conf/project_template/project_name/settings.py-tpl`), and the configuration class that startapp writes lost `AppConfig.default_auto_field`. Both had named `BigAutoField`, which 6.0 made the default (`docs/releases/6.0.txt`). In 6.1 the settings module gained `MAILERS`, with the console backend as `"default"`. Since 6.0 both commands make a missing target directory, parents and all, where 5.2.17 refused (`django/core/management/templates.py:TemplateCommand.handle`).

Since 5.2 the shell fills its namespace before it starts, from the dotted paths that `Command.get_auto_imports` returns (`django/core/management/commands/shell.py:Command.get_auto_imports`). In 5.2 they are the models that `Apps.get_models` lists. Since 6.0 the settings object, the default connection, `django.db.models`, `django.db.models.functions`, `reset_queries` and `django.utils.timezone` come before the models ([The commands Django ships](../commands/builtin.md#the-shell)).

## Smaller changes

| what | change | where |
|---|---|---|
| the setting `TIME_ZONE` | Since 6.2, checked with `zoneinfo.ZoneInfo` as a settings module loads, where 5.2.17 to 6.1.1 looked for a file under /usr/share/zoneinfo; still not checked on Windows, and no release note says so | `django/conf/__init__.py:Settings.__init__` |
| a mistyped choice | Since 6.1, on Python 3.14, argparse's error offers the nearest choice | `django/core/management/base.py:CommandParser.__init__` |
| listurls | New in 6.2: the command that lists the root URLconf's URLs ([The URL checks, and listing the patterns](../urls/checks.md)) | `django/core/management/commands/listurls.py:Command.handle` |
| the debug context processor | Since 5.2, left out of the `TEMPLATES` that startproject writes, and still in Django | `django/template/context_processors.py:debug` |
