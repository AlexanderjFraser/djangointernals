---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `call_command`: a command called from code

`call_command` runs a management command from Python: it finds the command as the command line would, builds its parser to learn the default of every option, and calls `BaseCommand.execute` directly. Nothing that `BaseCommand.run_from_argv` does takes place, so errors are exceptions and nothing is closed afterwards, and the function itself turns the system checks off.

Commands are run by code as well as by people. Django does it itself: the test runner builds a test database by calling migrate and then runs check, a test case with fixtures calls loaddata, a test case that touches the database outside a transaction empties it with flush, and the testserver command calls loaddata and then runserver (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`, `django/test/runner.py:DiscoverRunner.run_checks`, `django/test/testcases.py:TransactionTestCase._fixture_teardown`, `django/core/management/commands/testserver.py:Command.handle`). All of them go through one function, and the function's task is to make a call from code look, to the command, like a run from a command line.

## Why it builds a parser

A command's `handle` is written against a dictionary of options, and it expects the dictionary to be complete: every option the command declared, and every option all commands share, present with at least its default. The command line provides that for free, because the parser fills in whatever was not typed.

A caller in code names only the options it cares about. So `call_command` builds the command's parser anyway, runs it, and uses the result as the base that the caller's keywords are laid over. A comment in the function says as much: the parsing is simulated to get the defaults (`django/core/management/__init__.py:call_command`).

The recordings on this page call two commands of a small project. One, count, takes a number of rows as a positional argument and has an option, declared as an integer, for the trees in a row; it writes the product.

```text recording=commands
call_command: a command called from code
    call_command("count", 3, per_row=10, stdout=out)
      call_command("count", 3, per_row=10, stdout=a StringIO)
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
        BaseCommand.create_parser("", "count")
          Command.add_arguments  (trees.management.commands.count)
        CommandParser.parse_args(["3"])
        BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, skip_checks=True, rows=3, per_row=10, stdout=a StringIO)
          Command.handle  (trees.management.commands.count)
            OutputWrapper.write("30 trees in 3 rows")  to a StringIO
      -> None
    out.getvalue()  -> '30 trees in 3 rows\n'
```

The caller gave one argument and two options, and `execute` received every option the command has.

## What it does, in order

1. **It finds the command.** A name is looked up in the dictionary of `get_commands` and loaded with `load_command_class`, the same two functions the command line uses ([Finding the command](finding.md#the-dictionary-of-commands-get_commands)); a name that is not there is a `CommandError`. The caller may pass a command object in place of a name, and it is used as it is.
2. **It builds the parser**, with `BaseCommand.create_parser`, which calls the command's `add_arguments`.
3. **It translates the keywords.** A keyword may be an option's **destination**, the name `handle` will find it under, or the option as it is typed, without its leading dashes and with underscores for its hyphens. The second form is mapped to the first. Where an option can be typed several ways, only the spelling that sorts first is known: the flush command accepts `--noinput` and `--no-input` and stores the answer as interactive, and a caller may write interactive or no_input, and not noinput.
4. **It parses the positional arguments.** Each is turned into a string, a list into its items, and they are given to the parser as a command line of their own. An option that the parser requires, if the caller gave it as a keyword under its destination, is added to that line, so that the parser does not stop for the lack of it.
5. **It lays the keywords over the result**, and refuses any keyword that is neither a destination, nor an option's name, nor one of the command's stealth options ([below](#stealth-options)), with a `TypeError` that lists what is valid.
6. **It sets the option skip_checks to true**, unless the caller gave it a value.
7. **It calls `BaseCommand.execute`** with the whole dictionary, and returns what that returns.

Step 5 has a consequence that the recording shows best. What is given positionally, or spelt as on a command line, passes through the parser and is converted by it. What is given as a keyword is not converted: it replaces the parsed value as it stands, whatever its type. Unless the option is one the parser requires, the parser never sees the value at all, and the argument's declared type and choices are not applied to it. The command recorded here declares its option as an integer and multiplies by it.

```text recording=commands
call_command: an option given as an argument is parsed, and one given as a keyword is not
    call_command("count", 3, "--per-row", "10", stdout=out), the option as the command line spells it
      call_command("count", 3, "--per-row", "10", stdout=a StringIO)
        load_command_class("trees", "count")
        BaseCommand.create_parser("", "count")
          Command.add_arguments  (trees.management.commands.count)
        CommandParser.parse_args(["3", "--per-row", "10"])
        BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, skip_checks=True, rows=3, per_row=10, stdout=a StringIO)
          Command.handle  (trees.management.commands.count)
            OutputWrapper.write("30 trees in 3 rows")  to a StringIO
      -> None
    out.getvalue()  -> '30 trees in 3 rows\n'
    call_command("count", 3, per_row="10", stdout=out), the option as a keyword, and its value a string
      call_command("count", 3, per_row="10", stdout=a StringIO)
        load_command_class("trees", "count")
        BaseCommand.create_parser("", "count")
          Command.add_arguments  (trees.management.commands.count)
        CommandParser.parse_args(["3"])
        BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, skip_checks=True, rows=3, per_row="10", stdout=a StringIO)
          Command.handle  (trees.management.commands.count)
            OutputWrapper.write("101010 trees in 3 rows")  to a StringIO
      -> None
    out.getvalue()  -> '101010 trees in 3 rows\n'
```

Step 4 has an edge of its own. A positional argument that the parser requires has to be given positionally. The command's rows argument is one: it is required and has a destination like any option, so step 4 tries to add it to the command line, and fails for want of an option string to add it under.

```text recording=commands
call_command: a positional argument given as a keyword
    call_command("count", rows=3)
      call_command("count", rows=3)
        load_command_class("trees", "count")
        BaseCommand.create_parser("", "count")
          Command.add_arguments  (trees.management.commands.count)
      -> raises ValueError: min() iterable argument is empty
```

## What differs from a command line

`call_command` enters at `execute`, the inner of the two layers described in [Running a command: `BaseCommand`](running.md#two-layers-around-handle).

| | from a command line | through `call_command` |
|---|---|---|
| Django is started | by `ManagementUtility.execute` | by the caller, beforehand |
| `--settings` and `--pythonpath` | acted on | in the options, and not acted on |
| an argument the parser refuses | the usage on standard error, exit status 2 | a `CommandError` |
| a `CommandError` from the command | a line on standard error, an exit status | reaches the caller |
| the system checks | run, unless `--skip-checks` | not run, unless the caller passes skip_checks as false |
| the database connections | closed when the command ends | left as they are |
| what the command returned | written to standard output | written, and returned to the caller |

*A command run from a command line and the same command run through `call_command`.*

The second, fourth and sixth are things `run_from_argv` does and `execute` does not. The third follows from them: `run_from_argv` marks a command as coming from a command line, and a parser whose command is not so marked raises instead of exiting ([The parser](running.md#the-parser)). The fifth is step 6 above: `execute` runs the checks in both columns, and `call_command` hands it the option that says not to. The first row is only where each begins, and the last is `execute` at work in both columns: it writes the value and returns it, and `run_from_argv` has no one to return it to.

```text recording=commands
call_command: errors reach the caller as exceptions
    call_command("juice")
      call_command("juice")
        load_command_class("press", "juice")
        BaseCommand.create_parser("", "juice")
          Command.add_arguments  (press.management.commands.juice)
        CommandParser.parse_args([])
        BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, kilos=0, skip_checks=True)
          Command.handle  (press.management.commands.juice)
      -> raises CommandError: The press is empty.
    call_command("count", "three")
      call_command("count", "three")
        load_command_class("trees", "count")
        BaseCommand.create_parser("", "count")
          Command.add_arguments  (trees.management.commands.count)
        CommandParser.parse_args(["three"])
          CommandParser.error("argument rows: invalid int value: 'three'")
      -> raises CommandError: Error: argument rows: invalid int value: 'three'
    call_command("count", 3, colour=True)
      call_command("count", 3, colour=True)
        load_command_class("trees", "count")
        BaseCommand.create_parser("", "count")
          Command.add_arguments  (trees.management.commands.count)
        CommandParser.parse_args(["3"])
      -> raises TypeError: Unknown option(s) for count command: colour. Valid options are: force_color, help, no_color, per_row, pythonpath, rows, settings, skip_checks, stderr, stdout, traceback, verbosity, version.
    call_command("cont", 3)
      call_command("cont", 3)
      -> raises CommandError: Unknown command: 'cont'
```

## The checks, and their two exceptions

The checks are the row most likely to surprise. The project has one system check of its own, which returns an error when a setting, TREES_PER_ROW, is above 20. With the setting at 30 a command line refuses to run count; through `call_command` it runs, and is refused only when the caller asks for the checks.

```text recording=commands
call_command runs no system checks unless it is asked to
    TREES_PER_ROW is 30, for which the check of the trees application returns an error
    call_command("count", 3, stdout=out)
      ...
          Command.handle  (trees.management.commands.count)
            OutputWrapper.write("90 trees in 3 rows")  to a StringIO
      -> None
    call_command("count", 3, stdout=out, skip_checks=False)
      call_command("count", 3, stdout=a StringIO, skip_checks=False)
        load_command_class("trees", "count")
        BaseCommand.create_parser("", "count")
          Command.add_arguments  (trees.management.commands.count)
        CommandParser.parse_args(["3"])
        BaseCommand.execute(verbosity=1, settings=None, pythonpath=None, traceback=False, no_color=False, force_color=False, skip_checks=False, rows=3, per_row=None, stdout=a StringIO)
          BaseCommand.get_check_kwargs
            -> {}
          BaseCommand.check()
            CheckRegistry.run_checks()
              -> 23 check functions called; trees.E001
      -> raises SystemCheckError: SystemCheckError: System check identified some issues: ...
```

The option governs the checks that `execute` runs, and those of a command that consults the option for itself, as runserver does before the checks it runs on its own. A command that runs checks in its `handle` without looking at the option runs them however it was called: the check command is the plain case, and it is how the test runner, which uses `call_command`, has the project checked. And a command whose class asks for no checks does not have the option at all, so passing it is an error.

```text recording=commands
call_command and the checks: a command whose class asks for none, and the check command
    call_command("juice", kilos=10, stdout=out, skip_checks=False)
      ...
      -> raises TypeError: Unknown option(s) for juice command: skip_checks. Valid options are: force_color, help, kilos, no_color, pythonpath, settings, stderr, stdout, traceback, verbosity, version.
    call_command("check", stdout=out)
      ...
          Command.handle  (django.core.management.commands.check)
            BaseCommand.check(display_num_errors=True)
              CheckRegistry.run_checks()
                -> 23 check functions called; trees.E001
      -> raises SystemCheckError: SystemCheckError: System check identified some issues: ...
```

## Output and the return value

A command writes to its own two wrappers, which are made around the process's standard streams when the command object is made. A caller that wants the output passes a stream of its own as stdout or stderr, and `execute` puts a new wrapper around it before anything is written. That is how the recordings on this page capture a line in a buffer.

What `handle` returns comes back as well. For a command that returns its output, such as the project's juice, the caller gets the text twice: in the stream, and as the value of the call.

```text recording=commands
call_command: what the command returns is returned, and written as well
    call_command("juice", kilos=10, stdout=out), a command that returns its output
      ...
          Command.handle  (press.management.commands.juice)
          OutputWrapper.write("6.0 litres")  to a StringIO
      -> '6.0 litres'
    out.getvalue()  -> '6.0 litres\n'
```

## Stealth options

Some commands read options from their dictionary that no parser argument declares, so they cannot be typed and exist only for callers in code. `call_command` would refuse them as unknown, so a command lists them: `BaseCommand.base_stealth_options` names the two every command has, stdout and stderr, and a class adds its own in `BaseCommand.stealth_options`.

The flush command has three, which let the test framework that calls it decide whether sequences are reset, whether the truncation may cascade, and whether the `post_migrate` signal is sent afterwards (`django/core/management/commands/flush.py:Command`). The runserver command has one, a message to print when the server is stopped, which is passed by testserver (`django/core/management/commands/runserver.py:Command.inner_run`).
