---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Finding the command

How `ManagementUtility.execute` gets from an argument list to a command object: the two options it reads early, the dictionary that `get_commands` builds from every management/commands directory, and what `ManagementUtility.fetch_command` does when the name is unknown or the settings are missing.

A command line names its command with one word, and nothing in a project lists the commands there are. No setting names them and no application registers them. The set is worked out from the file system when a command is asked for: a command exists because a file with its name lies in a directory with the right name, in Django or in an installed application. This page follows that lookup, from the word on the command line to an instance of a class.

## Three entry points, one function

A command can be typed three ways, and all three call `execute_from_command_line` (`django/core/management/__init__.py:execute_from_command_line`).

- `manage.py` is a file of the project, written by the startproject command. It sets `"DJANGO_SETTINGS_MODULE"` to the project's settings module unless the environment has a value already, and calls the function with `sys.argv` (`django/conf/project_template/manage.py-tpl`).
- `django-admin` is a script that installing Django creates, declared as an entry point that names the function directly (`pyproject.toml`).
- `python -m django` runs Django's `__main__` module, which calls it too (`django/__main__.py`).

The function makes a `ManagementUtility` from the argument list and calls its `execute`. The utility keeps the list, and the base name of its first item as the program's name for messages; where that is `"__main__.py"` it says `"python -m django"` instead (`django/core/management/__init__.py:ManagementUtility.__init__`).

So the three differ in what surrounds the call. Only `manage.py` says which settings to use. And they differ in where Python will look for the project's code: running `manage.py` puts the project's directory first on the module search path, because Python does that with the directory of any script it is given, and `python -m django` gets the current directory there. `django-admin` gets neither, and has to be told where the project is, by the environment or by `--pythonpath`.

## What `execute` does before it knows the command

`ManagementUtility.execute` takes the second item of the argument list as the name of the **subcommand**, or `"help"` if there is none. It cannot look the name up at once, because which commands exist depends on the settings (`django/core/management/__init__.py:ManagementUtility.execute`).

1. **It reads `--settings` and `--pythonpath`.** A parser that knows only those two options is run over the rest of the line, ignoring everything it does not recognise and any error. `handle_default_options` then acts on what was found: a settings module's name is written to the environment variable, and a directory is put at the front of the module search path (`django/core/management/base.py:handle_default_options`).
2. **It tries the settings.** It reads `settings.INSTALLED_APPS`, which loads the settings module if one is named. If the read raises `ImproperlyConfigured`, whatever the cause, the exception is kept on the utility and `execute` goes on without settings. That is the exception raised when no settings module is named, when the named module itself is not found, and when a setting that must be a list is not one. An exception of any other class, from a missing package above the module or from the module's own code, is not caught, and ends every command there with a traceback.
3. **It starts Django**, if the read worked, by calling `django.setup`. For the runserver command with its reloader the call is made so that a failure does not end the process; [Who calls `django.setup`](../startup/callers.md#the-development-server-may-start-broken) tells that case.
4. **It answers a request for shell completion**, if the environment says that is what this run is ([below](#help-version-and-completion)).
5. **It dispatches on the subcommand.** The words help and version, and `--help`, `-h` or `--version` standing alone, are answered by the utility itself. Anything else is taken for a command's name: `ManagementUtility.fetch_command` returns a command object, and its `BaseCommand.run_from_argv` is called with the whole argument list.

The two options are read here and again later. Every command's own parser declares `--settings` and `--pythonpath` too, so that they are accepted and shown in its help, and `BaseCommand.run_from_argv` passes the parsed options through `handle_default_options` a second time. The early reading is the one that decides which commands there are.

## The dictionary of commands: `get_commands`

`get_commands` returns a dictionary from each command's name to the name of the application that provides it (`django/core/management/__init__.py:get_commands`).

It starts with Django's own commands, the modules of `django/core/management/commands/`, each entered under the name `"django.core"`. If the settings are not configured, that is the whole dictionary. Otherwise it goes through the installed applications in the reverse of their order in `settings.INSTALLED_APPS`, and for each one adds the commands found in the application's own management/commands directory, replacing any entry of the same name.

`find_commands` does the finding, and it imports nothing. It asks `pkgutil.iter_modules` for the modules in the directory and keeps the names that are not packages and do not begin with an underscore. A helper module can therefore sit beside the commands, under a name that starts with one (`django/core/management/__init__.py:find_commands`).

The order of the loop is a rule of precedence. Because later entries replace earlier ones, and the applications are taken last to first, **the application listed first wins**, and any application wins over Django. The recorded project installs `django.contrib.staticfiles` and then two applications of its own, trees and press. Here is what each place offers, and which offers are not taken up.

```text recording=commands
The commands of the project: what find_commands finds in each place, in the order of INSTALLED_APPS
    django.core
      check, compilemessages, createcachetable, dbshell, diffsettings, dumpdata, flush,
      inspectdb, listurls, loaddata, makemessages, makemigrations, migrate, optimizemigration,
      runserver (not used: django.contrib.staticfiles has one), sendtestemail, shell,
      showmigrations, sqlflush, sqlmigrate, sqlsequencereset, squashmigrations, startapp,
      startproject, test, testserver
    django.contrib.staticfiles
      collectstatic, findstatic, runserver
    trees
      count, prune
    press
      count (not used: trees has one), juice
```

Replacement is by name and by nothing else. The runserver of `django.contrib.staticfiles` is a subclass of Django's that adds the serving of static files, but that is its author's choice: the dictionary would point just as well at a class that shared nothing with the one it displaced. A project replaces a command of Django's, or of another application, by putting a file of the same name in an application listed earlier.

The dictionary is built once in a process, because `get_commands` is wrapped in `functools.cache`. The recordings in [`call_command`](call-command.md) show it: the directories are listed under the first call in a process and under none after it. In a process whose installed applications change, the test framework's, a receiver of the `setting_changed` signal empties the cache whenever `"INSTALLED_APPS"` is overridden (`django/test/signals.py:update_installed_apps`).

## From a name to an object

`ManagementUtility.fetch_command` looks the subcommand up in the dictionary and hands the application's name to `load_command_class`. That function imports the command's module by its dotted path, the application's name, then management, commands and the command's own name, and returns an instance of the module's class Command, made with no arguments. That is the whole of the contract a command module has to meet: the right place, and a class of that name. An error raised by the import is not caught (`django/core/management/__init__.py:ManagementUtility.fetch_command`, `django/core/management/__init__.py:load_command_class`).

The lookup stops in one of two ways, both ending the process with status 1.

**The name is not in the dictionary.** `fetch_command` complains on standard error. If `difflib.get_close_matches` finds a known name near the one typed, it is offered. And where the settings were not loaded, the complaint is preceded by the reason the project's commands may be missing: the exception kept from the attempt, if the environment names a settings module, or else a line saying that no settings were specified.

**The command needs settings and there are none.** Once the object exists, `fetch_command` looks at the exception that `execute` kept. If there is one and the command's `BaseCommand.requires_settings` is true, which is the default, the exception's message is printed. Four of Django's commands set the attribute to false and run regardless: startproject, startapp, shell and makemessages.

Without any settings, then, a project's command is unknown, a command of Django's that needs settings is refused with the reason, and one that does not need them runs.

```text recording=commands
No settings: python -m django, with DJANGO_SETTINGS_MODULE not set
    python -m django count 3
      stderr | No Django settings specified.
      stderr | Unknown command: 'count'
      stderr | Type 'python -m django help' for usage.
      exit status 1
    python -m django check
      stderr | Requested setting INSTALLED_APPS, but settings are not configured. You must either define the environment variable DJANGO_SETTINGS_MODULE or call settings.configure() before accessing settings.
      exit status 1
    python -m django shell --no-imports -c print(40+2)
      stdout | 42
      exit status 0
```

A settings module that is named and does not exist has the same two outcomes, with its own message. In the third run below nothing but the option names the settings, and the project is importable because `python -m django` was started in its directory.

```text recording=commands
The --settings option, for a module that does not exist and for one that does
    python manage.py count 3 --settings=orchard.no_such_settings
      stderr | No module named 'orchard.no_such_settings'.
      stderr | Unknown command: 'count'
      stderr | Type 'manage.py help' for usage.
      exit status 1
    python manage.py check --settings=orchard.no_such_settings
      stderr | No module named 'orchard.no_such_settings'.
      exit status 1
    python -m django count 3 --settings=orchard.settings
      stdout | 36 trees in 3 rows
      exit status 0
```

> **Changed in 6.2.** `BaseCommand.requires_settings` is new. Before it, a failure to load the settings was set aside for every command, whatever the command went on to need.

A value in the dictionary may also be a command object in place of an application's name: `fetch_command` and `call_command` both test for one and use it as it is. Django itself stores only names there.

## Help, version and completion

Some things a command line can ask for are answered by `ManagementUtility` without running a command.

**Help.** With no subcommand, with help alone, or with `--help` or `-h` as the only argument, `ManagementUtility.main_help_text` lists every name in the dictionary under the application it comes from. If the settings could not be loaded, the list ends with a note that says so and gives the error, since the list is then Django's commands only. Help followed by a name fetches that command, as above, and prints its parser's help (`django/core/management/__init__.py:ManagementUtility.main_help_text`).

**The version.** The subcommand version, or `--version` as the only argument, prints what `get_version` returns (`django/utils/version.py:get_version`).

**Completion.** `ManagementUtility.autocomplete` is called on every run, after the step that starts Django, and returns at once unless the environment has `"DJANGO_AUTO_COMPLETE"`. The Bash completion script that comes with Django's source sets that variable and runs the program again, with the words typed so far in `"COMP_WORDS"` and the index of the word being completed in `"COMP_CWORD"`. The method prints the candidates for that word and exits: the names of the commands, or the options of the command already named, which it gets by fetching that command and building its parser (`django/core/management/__init__.py:ManagementUtility.autocomplete`, `extras/django_bash_completion`).
