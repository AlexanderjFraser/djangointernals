---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The runner: the test command and `DiscoverRunner`

The test command takes the runner's class from `--testrunner` or `TEST_RUNNER`, adds that class's options to its command line, and ends with status 1 when anything failed. `DiscoverRunner.run_tests` is the run: a fixed order of steps, the suite run by `unittest.TextTestRunner`, with `DebugSQLTextTestResult` for `--debug-sql`.

The command owns what belongs to a command line: which runner, which options, the exit status. Of the runner it asks only that its class can be made with the options as keyword arguments, and that its `run_tests` takes the labels and returns a false value, such as zero, when all went well.

## The test command

Some of the test command's options are not its own: the runner's class adds them, and the class may be named on the same command line (`django/core/management/commands/test.py:Command`). `BaseCommand.run_from_argv` builds the parser before it parses ([Running a command: `BaseCommand`](../commands/running.md)), so `Command.run_from_argv` first reads `--testrunner` alone, with `get_command_line_option`; its docstring gives the reason, that this lets a runner define further options (`django/core/management/commands/test.py:Command.run_from_argv`). `Command.add_arguments` adds the labels, `--noinput` and `--testrunner`, and takes the class with `get_runner`, which imports the module of the dotted path read, or of `TEST_RUNNER`, and returns the attribute the last part names (`django/test/utils.py:get_runner`); if the class has an `add_arguments`, it adds its options. Through `call_command`, which skips `run_from_argv`, the parser is built for the class `TEST_RUNNER` names.

`BaseCommand.requires_system_checks` is an empty list here, its comment saying that `DiscoverRunner` runs the checks after the databases are set up: `BaseCommand.execute` runs none, and there is no `--skip-checks`.

`Command.handle` takes the class again, from the parsed option or the setting; replaces a `--parallel` of `"auto"` by what `get_max_test_processes` returns ([Running in parallel: `ParallelTestSuite`](parallel.md)); makes the runner with every option as a keyword argument, those every command shares included; calls `run_tests` with the labels, timed as `"Total run"`; and calls `sys.exit` with 1 if it returned a true value, such as a count above zero (`django/core/management/commands/test.py:Command.handle`).

## The options of `DiscoverRunner`

`DiscoverRunner.add_arguments`, a class method, runs before any runner exists; `DiscoverRunner.__init__` keeps most options under their destinations (`django/test/runner.py:DiscoverRunner.__init__`).

| option | kept as | read by |
|---|---|---|
| `--failfast` | `failfast` | `unittest.TextTestRunner`: stop at the first failure, error or unexpected success; `build_suite`, for parallel workers |
| `-t`, `--top-level-directory` | `top_level` | `DiscoverRunner.build_suite` |
| `-p`, `--pattern` | `pattern`, `"test*.py"` by default | `build_suite` |
| `-k` | `test_name_patterns` | `build_suite` |
| `--tag`, `--exclude-tag` | `tags`, `exclude_tags`, as sets | `build_suite` |
| `--shuffle [SEED]` | `shuffle` | `build_suite`; `DiscoverRunner.run_suite` logs the seed again |
| `-r`, `--reverse` | `DiscoverRunner.reverse` | `build_suite` |
| `--debug-mode` | `debug_mode` | `DiscoverRunner.setup_test_environment`; `build_suite`, for parallel workers |
| `--keepdb` | `keepdb` | `DiscoverRunner.setup_databases`, `DiscoverRunner.teardown_databases` |
| `-d`, `--debug-sql` | `debug_sql` | `setup_databases`; `DiscoverRunner.get_resultclass` |
| `--parallel [N]` | `parallel` | `__init__`, `build_suite`, `setup_databases`, `teardown_databases` |
| `--pdb` | `DiscoverRunner.pdb` | `get_resultclass` |
| `-b`, `--buffer` | `buffer` | `unittest.TextTestRunner`: a test's output shown only if it fails or has an error; `build_suite`, for parallel workers |
| `--durations N` | `durations` | `unittest.TextTestRunner` |
| `--timing` | a `TimeKeeper` | `run_tests` |
| `--no-faulthandler` | nothing | `__init__` |
| `--noinput`, the command's | `interactive` | `setup_databases`: if false, the creation deletes an old test database without asking, unless `--keepdb` keeps it |
| `-v`, every command's | `verbosity` | `DiscoverRunner.log`, `unittest.TextTestRunner`, the creation, the checks |

Two act in `__init__`. `--pdb` with a `parallel` above 1 is refused with `ValueError`; Django's documentation says a debugger there ends in `bdb.BdbQuit` (`docs/ref/django-admin.txt`). And `faulthandler.enable` is called on standard error, unless `--no-faulthandler` was given or it is on already.

## `run_tests`, in order

`DiscoverRunner.run_tests` calls the runner's own methods in a fixed order (`django/test/runner.py:DiscoverRunner.run_tests`):

1. `DiscoverRunner.setup_test_environment`, which also calls `unittest.installHandler` ([The test environment: `setup_test_environment`](environment.md)).
2. `build_suite` ([Finding and ordering the tests: `DiscoverRunner.build_suite`](discovery.md)).
3. `DiscoverRunner.get_databases`, the aliases the tests use ([Which databases a test uses: `databases`](test-databases.md)).
4. `DiscoverRunner.setup_databases`, timed as `"Total database setup"`.
5. `DiscoverRunner.run_checks`, then `run_suite`.
6. In a `finally`, `DiscoverRunner.teardown_databases`, timed as `"Total database teardown"`, and `DiscoverRunner.teardown_test_environment`.
7. The time keeper's records printed, and `DiscoverRunner.suite_result` returned.

The `try` opens once the databases exist, so a `SystemCheckError` or an exception out of the suite still has them destroyed and the environment undone; an exception in that teardown is dropped if the run raised an `Exception`, not to shadow it, the comment says. A failure before the `try`, in building the suite or making a database, is undone by nothing.

`suite_result` adds the lengths of the result's lists of failures, errors and unexpected successes: entries, not tests. A test whose loop of `unittest.TestCase.subTest` failed for two values reported "Ran 1 test" and "FAILED (failures=2)".

Django's documentation lets a project's runner subclass `DiscoverRunner` or stand alone, and asks it to accept `**kwargs`, so that Django can add options (`docs/topics/testing/advanced.txt`). Options it adds are known when `TEST_RUNNER` or `--testrunner` names it, and refused otherwise.

## The checks after the databases

`DiscoverRunner.run_checks` calls the check command with the runner's verbosity and the aliases the tests use, after the databases since, its comment says, some checks need them (`django/test/runner.py:DiscoverRunner.run_checks`). The checks tagged for databases run on those aliases; with none, as when no test names a database, they are left out (`django/core/checks/registry.py:CheckRegistry.run_checks`; [The system checks](../commands/checks.md)).

## Running the suite

`DiscoverRunner.run_suite` makes `DiscoverRunner.test_runner`, `unittest.TextTestRunner`, with `DiscoverRunner.get_test_runner_kwargs`: `failfast`, `verbosity`, `buffer`, `durations`, and the result class from `DiscoverRunner.get_resultclass`. It runs the suite and, in a `finally`, logs the shuffle seed that `DiscoverRunner.setup_shuffler` logged before (`django/test/runner.py:DiscoverRunner.run_suite`). What `unittest` prints goes to standard error. The runner's own lines go through `DiscoverRunner.log`: to a logger the runner was given, or else printed to standard output, INFO and above at verbosity 1, everything at 2 (`django/test/runner.py:DiscoverRunner.log`).

`get_resultclass` returns `DebugSQLTextTestResult` with `--debug-sql`, else `PDBDebugResult` with `--pdb`, else `None`, which leaves `unittest.TextTestResult`; given both options, no debugger opens (`django/test/runner.py:DiscoverRunner.get_resultclass`). `PDBDebugResult` opens a post-mortem debugger at each error, failure and failing subtest: ipdb where it can be imported, pdb otherwise (`django/test/runner.py:PDBDebugResult`).

## `--debug-sql`: `DebugSQLTextTestResult`

`DebugSQLTextTestResult` sets the logger `"django.db.backends"` to DEBUG and, from `DebugSQLTextTestResult.startTest` to `DebugSQLTextTestResult.stopTest`, gives it a handler that writes into a string through `QueryFormatter` (`django/test/runner.py:DebugSQLTextTestResult`). `QueryFormatter` passes each statement through its alias's `BaseDatabaseOperations.format_debug_sql`, which reindents it with sqlparse (`django/test/runner.py:QueryFormatter`). An error, a failure or a failing subtest gets the text after its traceback; at verbosity 2 each test's statements are also printed as it ends. They are logged at all because, for `--debug-sql`, `setup_databases` set `BaseDatabaseWrapper.force_debug_cursor` on every connection ([Which databases a test uses: `databases`](test-databases.md)).

`unittest` calls `startTest` and `stopTest` around `setUp`, the test and `tearDown`, inside Django's hooks ([One test, in order: `SimpleTestCase`](simple-test-case.md)). So a class's `setUpTestData` and a `TestCase`'s savepoint are left out, as in this test of the harbour office:

```python
# harbour/office/tests/test_tonnage.py
from django.test import TestCase

from harbour.fleet.models import Port, Ship


class TonnageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        valletta = Port.objects.create(name="Valletta", country="Malta")
        Ship.objects.create(name="Endeavour", tonnage=366, home=valletta)

    def test_heavy_ships(self):
        self.assertEqual(Ship.objects.filter(tonnage__gt=400).count(), 1)
```

```text
$ python manage.py test harbour.office.tests.test_tonnage --debug-sql
...
F
======================================================================
FAIL: test_heavy_ships (harbour.office.tests.test_tonnage.TonnageTests.test_heavy_ships)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
AssertionError: 0 != 1

----------------------------------------------------------------------
(0.000) SELECT COUNT(*) AS "__count"
FROM "fleet_ship"
WHERE "fleet_ship"."tonnage" > 400; args=(400,); alias=default

----------------------------------------------------------------------
Ran 1 test in 0.007s

FAILED (failures=1)
Destroying test database for alias 'default'...
```

The first lines and the traceback's frame are left out. The process ended with status 1.

## `--timing`: `TimeKeeper`

`--timing` gives the command and the runner each a `TimeKeeper`, and otherwise a `NullTimeKeeper`, which records nothing. `TimeKeeper.timed` records its block's time under a name entered as the block begins, so a block is printed before those inside it, such as each creation `setup_databases` times (`django/test/utils.py:TimeKeeper`). The runner prints its records to standard error as `run_tests` ends, and the command its total after:

```text
$ python manage.py test harbour.office.tests.test_ships --timing
...
Destroying test database for alias 'default'...
Total database setup took 0.132s
  Creating 'default' took 0.132s
Total database teardown took 0.000s
Total run took 0.180s
```
