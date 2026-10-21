---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Which databases a test uses: `databases`

`SimpleTestCase.databases` names the aliases of `DATABASES` a test case class may use. The runner reads it to choose which test databases to make (`DiscoverRunner.get_databases`), `SimpleTestCase.setUpClass` reads it to make every other alias raise `DatabaseOperationForbidden`, and `skipUnlessDBFeature` and its relatives read it before they ask the default database what it can do.

Django's documentation gives the reason a `SimpleTestCase` names no database by default: its tests are not run in a transaction, so a write would affect later tests (`docs/topics/testing/tools.txt`).

## The attribute

`SimpleTestCase.databases` is an empty set and `TransactionTestCase.databases` is `{"default"}`, which `TestCase` inherits; a class may name other aliases, or give `"__all__"` for every alias (`django/test/testcases.py:TransactionTestCase`). The same aliases, mirrors apart, are where a `TransactionTestCase` loads fixtures and flushes, and all of them where a `TestCase` opens its atomic blocks (`django/test/testcases.py:TransactionTestCase._databases_names`; [Emptying the tables after each test: `TransactionTestCase`](transaction-test-case.md), [A transaction around each test: `TestCase`](test-case.md)).

`SimpleTestCase._validate_databases` checks the attribute as the class is set up. `"__all__"` becomes a frozenset of every alias; an alias that `django.db.connections` does not know raises `ImproperlyConfigured`, naming the class and the alias, and the closest alias where `difflib.get_close_matches` finds one. The frozenset it returns replaces the class's attribute (`django/test/testcases.py:SimpleTestCase._validate_databases`, `django/test/testcases.py:SimpleTestCase._add_databases_failures`).

## What the runner makes

`DiscoverRunner._get_databases` reads `databases` from every test of the suite, `"__all__"` standing for every alias; a plain `unittest.TestCase` has none. The result maps each alias to whether any test that uses it sets `TransactionTestCase.serialized_rollback` (`django/test/runner.py:DiscoverRunner._get_databases`). `DiscoverRunner.get_databases` logs the aliases no test uses at the debug level, which a runner made without a logger, as the test command makes it, prints from verbosity 2 (`django/test/runner.py:DiscoverRunner.get_databases`).

`DiscoverRunner.run_tests` passes the aliases, and those to serialize, to `DiscoverRunner.setup_databases`, and the aliases to `DiscoverRunner.run_checks`, so that the database checks run for these alone, and keeps both sets on the suite for a `ParallelTestSuite`'s workers (`django/test/runner.py:DiscoverRunner.run_tests`).

A module where one class names the archive and two use a database they do not name:

```python
# harbour/office/tests/test_archive.py
from django.test import SimpleTestCase, TestCase, skipUnlessDBFeature

from harbour.fleet.models import Ship


class ShipCountTests(SimpleTestCase):
    def test_count(self):
        Ship.objects.count()


class ArchiveCountTests(TestCase):
    def test_archive_count(self):
        Ship.objects.using("archive").count()


class ArchiveTests(TestCase):
    databases = {"default", "archive"}

    @skipUnlessDBFeature("has_select_for_update")
    def test_lock_ships(self):
        list(Ship.objects.select_for_update())
```

Both test databases are made, since a class names `"archive"`; migrate's lines, the tracebacks and the end are left out:

```text
$ python manage.py test harbour.office.tests.test_archive -v 2
Found 3 test(s).
Creating test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
...
Creating test database for alias 'archive' ('file:memorydb_archive?mode=memory&cache=shared')...
...
System check identified no issues (0 silenced).
test_archive_count (harbour.office.tests.test_archive.ArchiveCountTests.test_archive_count) ... FAIL
test_lock_ships (harbour.office.tests.test_archive.ArchiveTests.test_lock_ships) ... skipped "Database doesn't support feature(s): has_select_for_update"
test_count (harbour.office.tests.test_archive.ShipCountTests.test_count) ... FAIL
...
django.test.testcases.DatabaseOperationForbidden: Database queries to 'archive' are not allowed in this test. Add 'archive' to harbour.office.tests.test_archive.ArchiveCountTests.databases to ensure proper test isolation and silence this failure.
...
django.test.testcases.DatabaseOperationForbidden: Database queries to 'default' are not allowed in SimpleTestCase subclasses. Either subclass TestCase or TransactionTestCase to ensure proper test isolation or add 'default' to harbour.office.tests.test_archive.ShipCountTests.databases to silence this failure.
...
```

## Making and destroying them: `setup_databases`

`DiscoverRunner.setup_databases` hands the aliases to `django.test.utils.setup_databases`, with the verbosity, `--noinput`, `--keepdb`, `--debug-sql` and `--parallel`. There `get_unique_databases_and_mirrors` groups the aliases asked for by the database each reaches, `"default"` first in its group, and takes every alias whose `"TEST"` names a `"MIRROR"`, asked for or not ([Test databases: `BaseDatabaseCreation`](../schema/test-databases.md) tells both). It orders the groups: an alias waits for those its `"TEST"` lists under `"DEPENDENCIES"`, and without that key an alias other than `"default"` whose database differs from `"default"`'s waits for `"default"`. `dependency_ordered` takes, round after round, the groups whose dependencies are met, and raises `ImproperlyConfigured` where an alias depends on one of its own group or a round takes none (`django/test/utils.py:get_unique_databases_and_mirrors`, `django/test/utils.py:dependency_ordered`).

> **Trap.** A round takes none whenever a dependency is not to be made, cycle or not. A run whose only class names `{"archive"}` ends before any database is made, with "Circular dependency in TEST[DEPENDENCIES]": `"archive"` waits for `"default"`, which nothing asked for. With `"DEPENDENCIES": []` in the archive's `"TEST"`, the same run passes.

For each group the creation of the first alias makes the test database, and its clones for `--parallel`; the group's other aliases are pointed at it, and each mirror at the database of the alias it names; once all are made, those to serialize are serialized (`django/test/utils.py:setup_databases`). Last, `--debug-sql` sets `force_debug_cursor` on every alias's connection, used or not, so that each statement is logged whatever `settings.DEBUG` is ([Cursors: executing a statement, the query log and execute wrappers](../connections/cursors.md)).

It returns, for each alias asked for that is not a mirror, the connection, the name the settings gave the database, and whether this alias made it. In its `finally`, `run_tests` gives that list to `teardown_databases`, which destroys each made database's clones and then the database, or leaves them with `--keepdb`, and puts back the `"NAME"` of the alias that made it (`django/test/utils.py:teardown_databases`).

Through the test command, a misspelt alias never reaches `_validate_databases`: `get_unique_databases_and_mirrors` passes over it, the check command fails on it once the others are made (`django/core/checks/database.py:check_database_backends`), and the `finally` destroys them. For `{"default", "archiv"}` the run ended with `ConnectionDoesNotExist`: "The connection 'archiv' doesn't exist."

## The guard: `_add_databases_failures`

`SimpleTestCase.setUpClass`, after the class's settings overrides, calls `SimpleTestCase._add_databases_failures`. It validates `databases`, then, on the connection of each alias the class does not name, replaces the methods `BaseDatabaseFeatures.disallowed_simple_test_case_connection_methods` lists: `"connect"` and `"temporary_connection"`, "connections" in the message, and `"cursor"` and `"chunked_cursor"`, "queries". Each becomes a `_DatabaseFailure`, which keeps the method and, called, raises `DatabaseOperationForbidden` with the class's message: `SimpleTestCase._disallowed_database_msg`, or `TransactionTestCase`'s own (`django/test/testcases.py:SimpleTestCase._add_databases_failures`). The exception is an `AssertionError`, so a refused query in a test method is reported as a failure; one in `TestCase.setUpTestData` is an error of `setUpClass`.

A thread has connection objects of its own ([Connections by alias: `DATABASES` and `ConnectionHandler`](../connections/aliases.md)), and those methods are replaced only on the thread that set the class up. For the rest, the class replaces `BaseDatabaseWrapper.ensure_connection` with what `SimpleTestCase.ensure_connection_patch_method` makes, which refuses to open a connection to an alias the class does not name, as "threaded connections": another thread's, and in the test's own thread one opened other than through the replaced methods, as an atomic block opens it through `BaseDatabaseWrapper.get_autocommit`. It lets through a connection already open, the connection without a database (`NO_DB_ALIAS`), and, a comment says, one made by hand under an alias `DATABASES` lacks (`django/test/testcases.py:SimpleTestCase.ensure_connection_patch_method`).

Both are undone as class cleanups after `tearDownClass`: `SimpleTestCase._remove_databases_failures` puts each method back, and `ensure_connection` is restored (`django/test/testcases.py:SimpleTestCase._remove_databases_failures`).

## Skipping by feature: `skipUnlessDBFeature`

`skipIfDBFeature` skips where the database has any of the features named, `skipUnlessDBFeature` where it lacks any, `skipUnlessAnyDBFeature` where it has none. A feature is named as a string and read from the features of `django.db.connection`, an instance of its backend's subclass of `BaseDatabaseFeatures`, so the database asked is always `"default"`'s ([What a database can do: `BaseDatabaseFeatures`](../backends/features.md)). Django's documentation says `skipIfDBFeature` needs all the features (`docs/topics/testing/tools.txt`); the code needs one. All three are made by `_deferredSkip` (`django/test/testcases.py:_deferredSkip`).

**On a method**, the wrapper acts as the test runs: `ValueError` if the test's `databases` lacks `"default"`, then `unittest.SkipTest` if the condition holds. The skip is raised inside the test method, so `SimpleTestCase._pre_setup`, `setUp`, `tearDown` and `SimpleTestCase._post_teardown` all run around it; a method marked by `unittest.skip` runs none of them ([One test, in order: `SimpleTestCase`](simple-test-case.md)).

**On a class**, it sets `"__unittest_skip__"` to a `CheckCondition`. The descriptor asks its conditions only when the attribute is read, as `unittest` comes to set the class up, after the test databases are made: importing the module asks the database nothing. A skipped base skips the class; otherwise the first condition that holds sets the attribute to `True`, with the reason (`django/test/testcases.py:CheckCondition.__get__`). Where the class does not name `"default"`, the condition raises `ValueError` instead, deferred, a comment says, so that the module can be imported; it is raised outside any test, and ends the run.

> **Trap.** On a class the check reads `databases` as written, and the string `"__all__"` does not contain `"default"`. A class with `databases = "__all__"` under `skipUnlessDBFeature` ended its run with that `ValueError`.
