---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Running a command: `BaseCommand`

How `BaseCommand` runs a command once it has been found: `BaseCommand.run_from_argv` builds the parser and parses, `BaseCommand.execute` runs the system checks and calls `handle`, output goes through `OutputWrapper`, and a `CommandError` becomes a message and an exit status.

Most of what happens when a command runs was not written by the command's author. The author declares the command's arguments in `BaseCommand.add_arguments` and does the work in `BaseCommand.handle`, and may set a few class attributes. Everything around those two methods is inherited: reading the command line, the options every command accepts, the checks, where output goes and in what colours, and what an exception turns into (`django/core/management/base.py:BaseCommand`).

## Two layers around `handle`

The inherited part is two methods, one inside the other, and the split between them is deliberate.

**`BaseCommand.run_from_argv` is the layer for a command line.** It owns what only makes sense when a person typed the command: parsing an argument list, turning a `CommandError` into a line on standard error and an exit status, and closing the database connections before the process ends (`django/core/management/base.py:BaseCommand.run_from_argv`).

**`BaseCommand.execute` is the layer for any caller.** It is given the options already parsed, as keyword arguments, and owns what belongs to running the command however it was started: the colour options, the checks, the call of `handle`, and writing out what `handle` returned. Code that runs a command without a command line enters here ([`call_command`](call-command.md)) (`django/core/management/base.py:BaseCommand.execute`).

The recordings on this page are of the small project used throughout the chapter. One of its commands, juice, takes a weight of apples in one option, asks for no system checks, and returns its output instead of writing it. This is a run of it from the moment its object exists.

```text recording=commands
A command that returns its output and asks for no system checks, from BaseCommand.run_from_argv on
    python manage.py juice --kilos 10
      BaseCommand.run_from_argv(["manage.py", "juice", "--kilos", "10"])
        BaseCommand.create_parser("manage.py", "juice")
          Command.add_arguments  (press.management.commands.juice)
        CommandParser.parse_args(["--kilos", "10"])
        handle_default_options(settings=None, pythonpath=None)
        BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, kilos=10)
          Command.handle  (press.management.commands.juice)
          OutputWrapper.write("6.0 litres")  to stdout
        BaseConnectionHandler.close_all  (the database connections)
      stdout | 6.0 litres
      exit status 0
```

## The parser

`BaseCommand.create_parser` returns a `CommandParser`, Django's subclass of `argparse.ArgumentParser`, named after the program and the subcommand and described by the class's `help` attribute (`django/core/management/base.py:BaseCommand.create_parser`).

Before the command is asked for its arguments, the parser is given the ones all commands share: `--version`, `--verbosity`, `--settings`, `--pythonpath`, `--traceback`, `--no-color` and `--force-color`. One more, `--skip-checks`, depends on the class. `BaseCommand.requires_system_checks` says which system checks the command wants run before it: the string `"__all__"`, which is the default, or a list of tags, and an empty list for none. A class with an empty list is not given the option, since it has no checks to skip: the command recorded above is one, and the line for `execute` shows no value for it. Then `add_arguments` is called with the parser, and the command adds its own.

The shared options are part of every command's interface, and a class can keep them out of the way. It can list some of them in `BaseCommand.suppressed_base_arguments`, and they are then accepted as before and left out of the help; runserver lists two (`django/core/management/base.py:BaseCommand.add_base_argument`). And the help is laid out by `DjangoHelpFormatter`, which moves the shared options after the command's own.

```text recording=commands
The help of one command: its own arguments, then those every command has
    python manage.py count --help
      stdout | usage: manage.py count [-h] [--per-row PER_ROW] [--version] [-v {0,1,2,3}]
      stdout |                        [--settings SETTINGS] [--pythonpath PYTHONPATH]
      stdout |                        [--traceback] [--no-color] [--force-color]
      stdout |                        [--skip-checks]
      stdout |                        rows
```

`CommandParser` differs from the parser it extends mainly in what an error does (`django/core/management/base.py:CommandParser`).

`argparse` answers a bad argument by printing the usage and ending the process with status 2. That is right for a command line and wrong for a program that called the command. So `run_from_argv` sets `BaseCommand._called_from_command_line` on the command before it builds the parser, and `CommandParser.error` ends the process only when it finds that set. Otherwise it raises the error as a `CommandError`. If a command gives its parser sub-parsers, they are made the same way.

A class may also define a `missing_args_message`, and the parser then gives that message, in place of the standard complaint, when a command that needs arguments is given none at all. On Python 3.14 the parser is also told to suggest the nearest valid choice for a mistyped one, and from that version on, to leave colour out of its own help when the command line or the environment asks for none.

The parsed result is turned into the call of `execute` by one convention. The namespace becomes a dictionary of keyword arguments, with one exception: a positional argument declared under the name args is taken out and passed as positional arguments. That is why `handle` is written to accept both, and why the dictionary it receives holds the shared options as well as the command's own: all of them but `--version`, which prints and exits without storing anything.

> **Changed in 6.1.** The suggestions for a mistyped choice date from this release.

## The order of `execute`

`BaseCommand.execute` works in this order.

1. **The colour options.** `--force-color` and `--no-color` together are a `CommandError`. Either one alone replaces the command's style ([below](#output-and-colour)).
2. **The streams.** If the options hold a value for stdout or stderr, the command's stream is replaced by a wrapper around it. No command-line option sets these: they are how a caller in code captures a command's output.
3. **The system checks**, unless the class's `requires_system_checks` is empty or the options say to skip them. `BaseCommand.get_check_kwargs` turns the attribute into the arguments of the call: none for the default, or the class's list of tags. With none, every check runs but those tagged for databases, which have to be asked for, and the deployment checks, which only the check command runs. The checks raise if they find an error, and then nothing below happens ([The system checks](checks.md)).
4. **The migrations check**, if the class sets `BaseCommand.requires_migrations_checks`. `BaseCommand.check_migrations` asks the migration executor for its plan on the default database and, if any migration is unapplied, prints a notice naming the applications concerned. It stops nothing.
5. **`handle`**, with the positional and keyword arguments.
6. **What `handle` returned.** If it is not empty it is written to the command's standard output, and it is also what `execute` returns. If the class sets `BaseCommand.output_transaction`, the text is first wrapped in the statements that open and close a transaction on the database the options name. The commands that print SQL for a person to run use this.

So `handle` can produce output as it goes, which suits progress and anything long, or return one string at the end.

Another of the project's commands, prune, shows step 3 with a list. Its class names two tags, and it is built on `LabelCommand`, which the next section describes.

```text recording=commands
A LabelCommand that asks for the checks of two tags, from BaseCommand.run_from_argv on
    python manage.py prune 4 7
      BaseCommand.run_from_argv(["manage.py", "prune", "4", "7"])
        BaseCommand.create_parser("manage.py", "prune")
          LabelCommand.add_arguments
        CommandParser.parse_args(["4", "7"])
        handle_default_options(settings=None, pythonpath=None)
        BaseCommand.execute("4", "7", verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, skip_checks=False)
          BaseCommand.get_check_kwargs
            -> {"tags": ["models", "trees"]}
          BaseCommand.check(tags=["models", "trees"])
            CheckRegistry.run_checks(tags=["models", "trees"])
              -> 3 check functions called; no messages
          LabelCommand.handle("4", "7")
            Command.handle_label("4")  (trees.management.commands.prune)
            Command.handle_label("7")  (trees.management.commands.prune)
          OutputWrapper.write("row 4 pruned\nrow 7 pruned")  to stdout
        BaseConnectionHandler.close_all  (the database connections)
      stdout | row 4 pruned
      stdout | row 7 pruned
      exit status 0
```

## `AppCommand` and `LabelCommand`

`BaseCommand` has two small subclasses for commands that do the same thing to each of their arguments. Each declares the positional arguments, under the name args, and implements `handle` as a loop; the author writes the body of the loop (`django/core/management/base.py:AppCommand`, `django/core/management/base.py:LabelCommand`).

`LabelCommand.handle` calls `LabelCommand.handle_label` once for each argument, with the argument as a string. `AppCommand.handle` first turns each argument into an installed application's `AppConfig`, refusing with a `CommandError` a label that names none, and calls `AppCommand.handle_app_config` with each. Both collect what the calls return and return it joined into lines, which `execute` then writes: the last call of `OutputWrapper.write` in the recording above. Of Django's commands, sqlsequencereset is an `AppCommand` and the findstatic of `django.contrib.staticfiles` a `LabelCommand`.

## Output and colour

A command writes to `BaseCommand.stdout` and `BaseCommand.stderr`, which are not the process's streams but an `OutputWrapper` around each (`django/core/management/base.py:OutputWrapper`).

The wrapper's `write` adds a line ending to a message that lacks one, and passes the message through a **style function**, a function from a string to the same string with terminal colour codes around it. Everything else asked of the wrapper is passed on to the stream inside. Because a command writes through the wrapper and not with `print`, the stream behind it can be exchanged, and a test or another command that asks for the output gets exactly what a terminal would have shown.

The style functions come from the command's `style` attribute, an object with one function for each of a fixed set of roles: an error, a warning, a success, a notice, the parts of an SQL statement, the classes of HTTP status, and a few more (`django/core/management/color.py:make_style`). `BaseCommand.__init__` chooses the object.

- If colour is not supported, each function returns its argument unchanged. `supports_color` decides, and its first condition is that the process's standard output is a terminal; on Windows it also wants one of several signs that the console understands the codes (`django/core/management/color.py:supports_color`).
- Otherwise the colours come from a **palette**. Django has a dark one, which is the default, a light one, and one with no colours. The environment variable `"DJANGO_COLORS"` can name another and override single roles (`django/core/management/color.py:color_style`, `django/utils/termcolors.py:parse_color_setting`).

`--no-color` and `--force-color` replace the object at the start of `execute`, the first with the colourless one and the second with a palette whether or not the output is a terminal.

The wrapper for standard error is also given the error role as its default style, so whatever a command writes there is coloured as an error without asking. A wrapper accepts a default only when its own stream is a terminal.

## What becomes of an exception

`CommandError` is the exception a command raises to say it cannot do what was asked, and `run_from_argv` treats it differently from every other (`django/core/management/base.py:CommandError`). The juice command raises one when it is given no apples.

```text recording=commands
A command raises CommandError, from BaseCommand.run_from_argv on
    python manage.py juice
      BaseCommand.run_from_argv(["manage.py", "juice"])
        BaseCommand.create_parser("manage.py", "juice")
          Command.add_arguments  (press.management.commands.juice)
        CommandParser.parse_args([])
        handle_default_options(settings=None, pythonpath=None)
        BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, kilos=0)
          Command.handle  (press.management.commands.juice)
        OutputWrapper.write("CommandError: The press is empty.")  to stderr
        BaseConnectionHandler.close_all  (the database connections)
      stderr | CommandError: The press is empty.
      exit status 5
```

`run_from_argv` catches it, writes the name of its class and its message to the command's standard error, and exits with the exception's `returncode`. The status is 1 unless the code that raised the exception gave another, as this command did. Django's dbshell uses that to end with the status of the database client it ran (`django/core/management/commands/dbshell.py:Command.handle`).

A failed system check arrives the same way. `SystemCheckError` is a subclass of `CommandError` whose message is the whole report, already formatted by `BaseCommand.check` and beginning with the exception's own name. So `run_from_argv` writes it as it stands, adding neither the name nor the error colour a second time.

With `--traceback`, `run_from_argv` raises the `CommandError` again instead of reporting it, and Python prints a traceback and ends the process with status 1: the exception's own status is lost. An ordinary exception of any other class is not caught by `run_from_argv` at all, and ends the same way. The command below raises a `ValueError` for a negative weight. A command can also end the process itself: some of Django's call `sys.exit` with a status of their choosing, and that passes through `run_from_argv` like any exit.

```text recording=commands
CommandError with --traceback, and an exception that is not a CommandError
    python manage.py juice --traceback
      stderr | Traceback (most recent call last):
      stderr |   (the frames)
      stderr | django.core.management.base.CommandError: The press is empty.
      exit status 1
    python manage.py juice --kilos -1
      stderr | Traceback (most recent call last):
      stderr |   (the frames)
      stderr | ValueError: a weight cannot be negative
      exit status 1
```

On every one of these paths `run_from_argv` ends by closing the database connections, in a `finally` clause. One kind of failure does not reach it. An argument the parser refuses ends the process inside the parser, with the usage and status 2, before the `try` begins.

```text recording=commands
An argument the parser refuses, from BaseCommand.run_from_argv on
    python manage.py juice --kilos ten
      BaseCommand.run_from_argv(["manage.py", "juice", "--kilos", "ten"])
        BaseCommand.create_parser("manage.py", "juice")
          Command.add_arguments  (press.management.commands.juice)
        CommandParser.parse_args(["--kilos", "ten"])
          CommandParser.error("argument --kilos: invalid int value: 'ten'")
      stderr | usage: manage.py juice [-h] [--kilos KILOS] [--version] [-v {0,1,2,3}]
      stderr |                        [--settings SETTINGS] [--pythonpath PYTHONPATH]
      stderr |                        [--traceback] [--no-color] [--force-color]
      stderr | manage.py juice: error: argument --kilos: invalid int value: 'ten'
      exit status 2
```

## `no_translations`

A command runs with whatever language is active in the process; `execute` does nothing about it. A command that must not produce translated text, because what it writes is stored and not shown, wraps its `handle` in the decorator `no_translations`, which deactivates translation for the call and restores the language afterwards. Of Django's commands, migrate and makemigrations do (`django/core/management/base.py:no_translations`).
