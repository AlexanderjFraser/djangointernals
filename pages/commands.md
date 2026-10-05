---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Foundations
contents: finding, running, call-command, checks, runserver, autoreload, builtin
---

# Management commands

What happens between a command line such as `python manage.py migrate` and the code that does the work: `ManagementUtility` finds the command's class, and `BaseCommand` parses the arguments, runs the system checks and calls the command's `handle`. The development server is one such command, and its reloader runs it as two processes.

A server calls Django once for each request. Everything else that is done to a project is done from a terminal: its database is migrated, its static files are collected, its tests are run, a development server is started. Each of these is a **management command**, and Django does not treat its own differently from a project's. A command is a class named Command, in a module whose file name is the command's name, in the directory management/commands of Django or of an installed application. The machinery that takes a command line to that class and runs it is small, and every command passes through it in the same way.

## `ManagementUtility` and `BaseCommand`

Two objects carry a command line, one after the other.

**`ManagementUtility` stands for one command line.** It is made with the argument list, and its one job is to turn the second word of that list into a command object. To do so it has to decide whether the project's settings can be loaded, start Django if they can, and find out which application provides a command of that name (`django/core/management/__init__.py:ManagementUtility`).

**`BaseCommand` is the base class of every command.** An instance has what any command needs: an argument parser that already knows the options all commands share, an output stream and an error stream, a hook that runs the system checks, and a way of turning an error into a message and an exit status. A command's author writes two methods: `add_arguments`, which declares the command's own arguments, and `handle`, which does the work (`django/core/management/base.py:BaseCommand`).

A project's `manage.py`, the `django-admin` script and `python -m django` all reach the first object through one function, `execute_from_command_line` ([Finding the command](commands/finding.md#three-entry-points-one-function)).

## One command line, in order

This is a command recorded as it ran. The project is a small one, an orchard, made for this chapter's recordings. Its settings install `django.contrib.staticfiles` and two applications of its own, trees and then press. The command count belongs to trees: it multiplies the number of rows it is given by a number of trees to the row. The lines are a selection of the calls made, nested as they were made, and then what the process wrote and the status it ended with.

```text recording=commands
A command of the project, from the command line
    python manage.py count 3 --per-row 10
      execute_from_command_line(["manage.py", "count", "3", "--per-row", "10"])
        ManagementUtility.execute
          handle_default_options(settings=None, pythonpath=None)
          Settings.__init__("orchard.settings")
            import orchard.settings
          django.setup
            import trees.apps
            import trees.models
            import trees.checks
          ManagementUtility.autocomplete
          ManagementUtility.fetch_command("count")
            get_commands
              find_commands("django/core/management")
                -> 26 names, "check" to "testserver"
              find_commands("press/management")
                -> ["count", "juice"]
              find_commands("trees/management")
                -> ["count", "prune"]
              find_commands("django/contrib/staticfiles/management")
                -> ["collectstatic", "findstatic", "runserver"]
            load_command_class("trees", "count")
              import trees.management
              import trees.management.commands
              import trees.management.commands.count
          BaseCommand.run_from_argv(["manage.py", "count", "3", "--per-row", "10"])
            BaseCommand.create_parser("manage.py", "count")
              Command.add_arguments  (trees.management.commands.count)
            CommandParser.parse_args(["3", "--per-row", "10"])
            handle_default_options(settings=None, pythonpath=None)
            BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, skip_checks=False, rows=3, per_row=10)
              BaseCommand.get_check_kwargs
                -> {}
              BaseCommand.check()
                CheckRegistry.run_checks()
                  -> 23 check functions called; no messages
              Command.handle  (trees.management.commands.count)
                OutputWrapper.write("30 trees in 3 rows")  to stdout
            BaseConnectionHandler.close_all  (the database connections)
      stdout | 30 trees in 3 rows
      exit status 0
```

Read against the code, the run has three stages.

**`ManagementUtility.execute` starts Django.** It looks through the arguments for two options, `--settings` and `--pythonpath`, because they decide which settings there are and so which commands. Then it reads a setting, which is what loads the settings module, and calls `django.setup`, which imports every installed application. [Who calls `django.setup`](startup/callers.md#a-management-command) follows this step and its exceptions (`django/core/management/__init__.py:ManagementUtility.execute`).

**`ManagementUtility.fetch_command` finds the command.** `get_commands` builds a dictionary from each command's name to the application that provides it, by listing the files of every management/commands directory, without importing any of them. It reads Django's own directory first and then the applications' from the last listed to the first, each replacing what was there. That is why press is read before trees above, and why, of the two files called count, the one in trees is kept: the application listed first in `settings.INSTALLED_APPS` has the last word. Only then is the chosen command's module imported, with the two packages above it, and its class instantiated (`django/core/management/__init__.py:get_commands`, `django/core/management/__init__.py:load_command_class`).

**`BaseCommand.run_from_argv` runs it.** It builds the parser, lets the command add its arguments, and parses the rest of the command line into a dictionary of options. `BaseCommand.execute` then runs the system checks, and only if they find no error calls `handle` with the options. The line this command prints goes through an `OutputWrapper`, the command's own wrapper around standard output. On the way out, `run_from_argv` closes the database connections the command opened (`django/core/management/base.py:BaseCommand.run_from_argv`, `django/core/management/base.py:BaseCommand.execute`).

```text figure=one-command-line
python manage.py count 3 --per-row 10

ManagementUtility.execute                          one for each command line
  1  reads --settings and --pythonpath before anything else
  2  loads the settings and calls django.setup()
  3  finds the command by name, and makes an instance of its class

  BaseCommand.run_from_argv                        the same for every command
    4  builds the parser, adds the command's arguments, parses the rest of argv

    BaseCommand.execute
      5  runs the system checks, unless the command or the command line declines
      6  Command.handle(*args, **options)          the command's own code
      7  writes what handle returned, if it returned anything

    8  on CommandError: the message to standard error, its status to the shell
    9  closes the database connections
```

*One command line as calls nested one inside another. Of everything that runs, only `handle` and the declaration of its arguments belong to the command.*

[Finding the command](commands/finding.md) is the first two stages: the entry points, what happens when there are no settings, and how one application's command replaces another's. [Running a command: `BaseCommand`](commands/running.md) is the third: the parser, the order of `execute`, output and colour, and what becomes of an exception.

## The checks stand in front of a command

In the recording, `handle` is not the first code to look at the project: the line under `CheckRegistry.run_checks` counts the functions that ran before it. They are the **system checks**: functions that inspect the project, its settings, its models, its URL patterns, and return messages about what is wrong with it. Django's own subsystems register some as they are imported, and installed applications register more as they are made ready. `BaseCommand.execute` runs them before `handle` unless the command's class or the command line says otherwise, and a message at the level of an error stops the command before it has done anything.

So a model with a field that cannot work is reported by migrate, by makemigrations and by a project's own commands alike, before any of them acts, and none of them contains code to look for it. The development server runs the same checks, at a moment of its own choosing, each time it starts. A production server does not run them at all: nothing on the path from `get_wsgi_application` to the first request calls them. [The system checks](commands/checks.md) has the registry, the selection by tag, and how messages are sorted into what is printed and what is fatal (`django/core/checks/registry.py:CheckRegistry.run_checks`, `django/core/management/base.py:BaseCommand.check`).

## A command called from code

Commands are also run by other code: a test loads a fixture, the test runner migrates a new database, one command runs another. `call_command` does this. It enters at the second object, not the first: it finds the command and instantiates it as above, builds the same parser to get the default of every option, and calls `BaseCommand.execute` directly. Nothing that `run_from_argv` adds takes place, so an error reaches the caller as an exception and not as text and an exit status. And `call_command` itself turns the system checks off, unless the caller asks for them. [`call_command`](commands/call-command.md) follows it (`django/core/management/__init__.py:call_command`).

## The development server is a command

To the machinery above, runserver is a command like any other, with one exception made for it by name: when Django fails to start and the command is runserver with its reloader, `ManagementUtility.execute` lets the command go on, so that the server can come up around broken code and wait for it to be mended. Otherwise it is a command whose `handle` does not return while the server runs.

What is unusual is inside it. It serves requests with a small HTTP server built on Python's `wsgiref`, handing each one to the project's own WSGI application, the object a production server would call ([The development server](commands/runserver.md)). And by default it runs as two processes: the one that was typed, which only starts a copy of itself and waits, and the copy, in which one thread runs the server while the main thread watches the file of every imported module and ends the process when one changes, so that the first can start another ([The autoreloader](commands/autoreload.md)).

## The neighbours

Most commands are a thin front for a subsystem that has a chapter of its own, and [The commands Django ships](commands/builtin.md) says which. The migrate command and its relatives drive [Migrations](migrations.md); test hands over to [The test framework](testing.md); dumpdata and loaddata call the serializers of [Caching, files, mail, signals and tasks](services.md). The step that starts Django belongs to [Settings, apps and startup](startup.md), and the handler that the development server calls to [Handlers and middleware](handlers.md). The checks themselves live with what they check: a model's with [Models and fields](models.md), the security checks with [Security](security.md).
