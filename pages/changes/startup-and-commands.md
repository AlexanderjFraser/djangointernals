---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in settings, startup and the commands

The changes from Django 5.0 to this commit in the settings object, the project template and the management commands: deprecated settings beside `MAILERS`, the shell's automatic imports, `BaseCommand.get_check_kwargs`, `BaseCommand.requires_settings`, the checks' databases, and listurls.

## A deprecated setting in the settings object

Since 6.1 the settings object ([The settings object](../startup/settings.md)) watches a few names: the email settings that `MAILERS` replaces, listed in `DEPRECATED_EMAIL_SETTINGS`, and the transitional settings `USE_BLANK_CHOICE_DASH` and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK`. Setting one warns with `RemovedInDjango2028Warning`. `Settings.__init__` warns for each that the settings module defines, attributed to the first frame outside Django (`django/conf/__init__.py:Settings.__init__`). `LazySettings.configure`, `override_settings` and an assignment to `settings` set values through `UserSettingsHolder.__setattr__` or `LazySettings.__setattr__`, which warn only when the code that set the value is outside Django (`django/conf/__init__.py:_show_settings_deprecation_warning`).

The email settings are watched when read, too. `LazySettings.__getattr__` warns when the code reading one is outside Django, and keeps the value on the proxy: later reads do not reach it, so none warns, even where Django's own code made the first. Where the project defines `MAILERS`, the read raises `AttributeError` instead, and `LazySettings.__dir__` leaves their defaults out of `dir(settings)` (`django/conf/__init__.py:LazySettings.__getattr__`, `django/conf/__init__.py:LazySettings.__dir__`). Defining both is refused with `ImproperlyConfigured` in the settings module or in one call of `configure` (`django/conf/__init__.py:_check_email_settings_conflicts`); `override_settings` does not check, and an email setting it sets beside `MAILERS` is refused when read.

```text
# deprecated_settings.py at this commit, every warning recorded; settings modules
# with EMAIL_HOST, with it and MAILERS, with MAILERS; then an override
EMAIL_HOST: the first read of any setting, SECRET_KEY
    -> 'harbour-office-not-a-secret'
    warns RemovedInDjango2028Warning: The EMAIL_HOST setting is deprecated. Migrate to MAILERS before Django 2028.
  settings.EMAIL_HOST
    -> 'smtp.harbour.example'
    warns RemovedInDjango2028Warning: The EMAIL_HOST setting is deprecated. Migrate to MAILERS before Django 2028.
  settings.EMAIL_HOST, again
    -> 'smtp.harbour.example'
EMAIL_HOST and MAILERS: the first read
    raises ImproperlyConfigured: Deprecated email settings are not allowed when MAILERS is defined: EMAIL_HOST.
MAILERS: settings.EMAIL_BACKEND
    raises AttributeError: The EMAIL_BACKEND setting is not available when MAILERS is defined.
override_settings(MAILERS={...}, EMAIL_PORT=587), entered
    warns RemovedInDjango2028Warning: The EMAIL_PORT setting is deprecated. Migrate to MAILERS before Django 2028.
  settings.EMAIL_PORT
    raises AttributeError: The EMAIL_PORT setting is not available when MAILERS is defined.
```

[What changed in mail and tasks](mail-and-tasks.md) tells what `MAILERS` configures; [What still warns: the deprecations and the releases that end them](deprecations.md) lists every deprecation.

## What startproject and startapp write

Since 5.2 the `TEMPLATES` of the settings module that startproject writes omits the debug context processor, which still exists (`django/conf/project_template/project_name/settings.py-tpl`, `django/template/context_processors.py:debug`). Since 6.0 that module sets no `DEFAULT_AUTO_FIELD`, and the `AppConfig` that startapp writes no `AppConfig.default_auto_field` (`django/conf/app_template/apps.py-tpl`): both named `BigAutoField`, which 6.0 made the setting's default ([What changed in models and fields](models.md)). Since 6.1 the module defines `MAILERS`, with the console backend as the default mailer.

## Before a command's `handle`

`ManagementUtility.execute` reads the settings before it loads the command, and keeps the `ImproperlyConfigured` of a failed read: no settings named, a module not found (an `ImportError` that `Settings.__init__` turns into that exception), a list setting that is not a list, email settings beside `MAILERS`. Since 6.2 `ManagementUtility.fetch_command` then refuses, with that message and status 1, a command whose `BaseCommand.requires_settings` is true, the default (`django/core/management/__init__.py:ManagementUtility.fetch_command`). Before, the notes say, an `ImportError` from the settings module was suppressed for every command (`docs/releases/6.2.txt`). At this commit an `ImportError` raised inside the settings module is not caught, and ends every command with a traceback ([Finding the command](../commands/finding.md)).

Since 5.2 `BaseCommand.execute` asks `BaseCommand.get_check_kwargs` for the arguments of its call of `BaseCommand.check`, a method a command may override (`django/core/management/base.py:BaseCommand.get_check_kwargs`). migrate overrides it to add its database, whose checks then run before it migrates; runserver returns an empty collection of tags, which selects nothing, and runs them itself in the serving process ([The development server](../commands/runserver.md)).

Since 6.1 `CheckRegistry.run_checks` gives the check functions every configured alias when its caller leaves the databases argument at None, where it used to give none (`django/core/checks/registry.py:CheckRegistry.run_checks`). It holds for every command whose checks leave it at None, not only the check command the notes name. The checks tagged database are still left out unless asked for. The change reaches the checks that work per database, among them the model checks of long column names, indexes, constraints and table comments (`django/db/models/base.py:Model.check`) and the fields' checks that ask the backend (`django/db/models/fields/__init__.py:Field._check_backend_specific_checks`): they now run against the connection of each alias the router lets the model migrate to, and where a backend learns its features from the server, as MySQL's does, the first read of one connects (`django/db/backends/mysql/base.py:DatabaseWrapper.mysql_server_data`). Callers, the notes say, "should be prepared for databases to be accessed" (`docs/releases/6.1.txt`; [The system checks](../commands/checks.md)).

## The shell

Since 5.2 the shell fills its namespace before it starts. `Command.get_auto_imports` returns dotted paths to import, among them every model that `Apps.get_models` returns, which leaves out the automatic through models of many-to-many relations and swapped models (`django/core/management/commands/shell.py:Command.get_auto_imports`). Since 6.0 the list begins with common utilities: at this commit the settings object, the default connection, `django.db.models`, `django.db.models.functions`, `reset_queries` and `django.utils.timezone`. Code given with `--command` or on standard input gets the namespace too, and `--no-imports` empties it ([The commands Django ships](../commands/builtin.md#the-shell)).

## Other changes

| what | what changed | release | where now |
|---|---|---|---|
| a query before the app registry is ready | warns with `RuntimeWarning`, unless a test has the installed applications overridden, and still runs ([Cursors: executing a statement, the query log and execute wrappers](../backends/cursors.md)) | 5.0 | `django/db/backends/utils.py:CursorWrapper._execute` |
| runserver's banner | ends with a warning that the server is for development, unless the environment sets `"DJANGO_RUNSERVER_HIDE_WARNING"` to `"true"` | 5.2 | `django/core/management/commands/runserver.py:Command.on_bind` |
| startproject and startapp given a directory | make it, and its missing parents, if it does not exist | 6.0 | `django/core/management/templates.py:TemplateCommand.handle` |
| a mistyped choice or subcommand | on Python 3.14 argparse suggests the nearest, the parser being made with `suggest_on_error=True`; on later versions Django leaves argparse's own default | 6.1 | `django/core/management/base.py:CommandParser.__init__` |
| listurls | new: prints the root URLconf's patterns, views and names | 6.2 | [The URL checks, and listing the patterns](../urls/checks.md) |

*Smaller changes to startup and the management commands.*
