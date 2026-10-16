---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Emptying the tables after each test: `TransactionTestCase`

`TransactionTestCase` is the test case class whose tests write to the test database as any code does, committing for real, and which puts the database back the long way: after each test `TransactionTestCase._post_teardown` runs the flush command, and before the next `TransactionTestCase._pre_setup` loads the class's `fixtures` and, where the class sets `serialized_rollback`, the rows that migrations wrote.

A rollback cannot undo what a test committed, and some tests must commit: code that commits or rolls back, to see the effect, or a check that code runs inside a transaction, as `select_for_update` requires, which Django's documentation says cannot be made in a `TestCase` (`docs/topics/testing/tools.txt`). Such a test runs in autocommit, and the way back is to delete what it wrote: a flush after every test, where a `TestCase` on a database with transactions rolls back ([A transaction around each test: `TestCase`](test-case.md)).

The class's work is in Django's two hooks around a test. Each has a database half, `TransactionTestCase._fixture_setup` and `TransactionTestCase._fixture_teardown`, which `TestCase` replaces; the rest it inherits. Both work on the class's databases: the aliases of `databases` in the order of `DATABASES`, less any whose `"TEST"` settings name a `"MIRROR"` ([Test databases: `BaseDatabaseCreation`](../backends/creation.md); `django/test/testcases.py:TransactionTestCase._databases_names`). The class also declares `TransactionTestCase.assertNumQueries` and `TransactionTestCase.assertQuerySetEqual` ([Counting queries: `assertNumQueries` and `CaptureQueriesContext`](query-assertions.md)).

## Before each test: `_pre_setup`

`TransactionTestCase._pre_setup` is a class method, and works in this order (`django/test/testcases.py:TransactionTestCase._pre_setup`):

1. The parent's, `SimpleTestCase._pre_setup`: a new client, the outbox emptied ([One test, in order: `SimpleTestCase`](simple-test-case.md)).
2. Where the class sets `TransactionTestCase.available_apps`, `Apps.set_available_apps` narrows the app registry to them; `setting_changed` is sent for `INSTALLED_APPS`, and its receivers drop what they built from the registry ([Overriding settings](../startup/overrides.md)); and `emit_post_migrate_signal` sends `post_migrate` on each of the class's databases, to those applications alone.
3. `_fixture_setup`. If it raises, the narrowing is undone and `setting_changed` sent again before the exception goes on.
4. Its databases' query logs are emptied, so that, the comment says, they are less likely to overflow and break `assertNumQueries`.

## The first test's set-up runs in `setUpClass`

`TransactionTestCase.setUpClass` calls the parent's and then, for a class that is not a `TestCase`, calls `_pre_setup` and sets `SimpleTestCase._pre_setup_ran_eagerly` on the class; `SimpleTestCase._setup_and_call` finds the flag at the first test that is not skipped, clears it, and does not call `_pre_setup` again (`django/test/testcases.py:TransactionTestCase.setUpClass`). Rows that a class's own `setUpClass` writes are committed: in a run, the first test found such a row and the second, after the flush, did not.

> **Changed in 5.2.** Rows from `fixtures` and from `serialized_rollback` are there during `setUpClass` (`docs/releases/5.2.txt`).

> **Trap.** `unittest` runs neither the tests nor `tearDownClass` of a class whose `setUpClass` raised, so an exception raised after the parent's leaves the first test's set-up in place: in a run, a class that loaded a fixture and then raised `unittest.SkipTest` left its port for the next class's first test.

`TransactionTestCase.tearDownClass` undoes a narrowing that no test undid, as when every test was skipped, counted in `TransactionTestCase._available_apps_calls_balanced`.

## The rows a test begins with: `_fixture_setup`

`TransactionTestCase._fixture_setup` works on each of the class's databases in turn, and what it writes is committed (`django/test/testcases.py:TransactionTestCase._fixture_setup`):

- With `TransactionTestCase.reset_sequences`, `TransactionTestCase._reset_sequences` sets each table's sequence back to its start, on a backend whose `BaseDatabaseFeatures.supports_sequence_reset` is true ([Introspection: reading the schema back](../backends/introspection.md)).
- With `TransactionTestCase.serialized_rollback`, and where the runner kept the database's rows as text after making it, `BaseDatabaseCreation.deserialize_db_from_string` writes them back, the narrowing to `available_apps` lifted while it does.
- With `TransactionTestCase.fixtures`, loaddata loads them ([Fixtures: dumpdata and loaddata](../services/fixtures.md)).

## After each test: `_post_teardown` and the flush

`TransactionTestCase._post_teardown` calls `_fixture_teardown`, then closes each connection made in this thread, whatever its alias, and in a `finally` undoes the narrowing to `available_apps` (`django/test/testcases.py:TransactionTestCase._post_teardown`). The comment's reason for the closing: some cursors send statements as they are made, a time zone setting among them, and a test that rolls back loses their effect. A `TestCase` does not close them where its databases have transactions (`TestCase._should_reload_connections`), and SQLite's backend ignores the close of a database in memory (`django/db/backends/sqlite3/base.py:DatabaseWrapper.close`).

`_fixture_teardown` calls flush on each of the class's databases, with `reset_sequences=False`, with `allow_cascade=True` only under `available_apps`, and with `inhibit_post_migrate=True` under `available_apps`, or under `serialized_rollback` where the runner kept the rows, the comment saying the latter is so as not to recreate the serialized rows (`django/test/testcases.py:TransactionTestCase._fixture_teardown`). Flush empties the models' tables in one transaction ([Introspection: reading the schema back](../backends/introspection.md)), and then, unless inhibited, sends `post_migrate` on the database for each application with a models module, its comment saying this lets each respond as if the database had been migrated from scratch: contenttypes and auth make their rows again ([The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md); `django/core/management/commands/flush.py:Command.handle`).

A class of the example's, whose fixture, the office application's fixtures/valletta.json, holds the port Valletta with the key 1; its first test commits a ship and its second finds none:

```python
# harbour/office/tests/test_commits.py
from django.db import transaction
from django.test import TransactionTestCase

from harbour.fleet.models import Port, Ship


class ShipCommitTests(TransactionTestCase):
    fixtures = ["valletta"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.valletta = Port.objects.get(name="Valletta")

    def test_commit(self):
        with transaction.atomic():
            Ship.objects.create(name="Endeavour", tonnage=366, home=self.valletta)
        self.assertEqual(Ship.objects.count(), 1)

    def test_empty_again(self):
        self.assertEqual(Ship.objects.count(), 0)
        self.assertEqual(Port.objects.get().name, "Valletta")
```

Both pass. With each hook printed as entered and each statement under it, lines left out at each `...`:

```text
test_commit
  SQL BEGIN
  SQL INSERT INTO "fleet_ship" ("name", "tonnage", "home_id", "captain_id") VALUES ('Endeavour', 366, 1, NULL) RETURNING "fleet_ship"."id"
  SQL COMMIT
  ...
TransactionTestCase._post_teardown
  TransactionTestCase._fixture_teardown
    ...
    SQL DELETE FROM "django_content_type";
    ...
    SQL COMMIT
    ...
TransactionTestCase._pre_setup
  TransactionTestCase._fixture_setup
    ...
    SQL INSERT INTO "fleet_port" ("id", "name", "country") VALUES (1, 'Valletta', 'Malta') RETURNING "fleet_port"."id"
    ...
test_empty_again
  ...
```

The statements of `post_migrate`'s receivers follow the `"COMMIT"`. The deletes come in the order of a set of table names, which changed from one run to the next.

## Fewer applications: `available_apps`

`available_apps` is private, Django's documentation says, and spares Django's own test suite the `post_migrate` after each flush, whose cost grows with the number of models (`docs/topics/testing/advanced.txt`). Under it, whatever asks the registry sees only the applications named: the flush empties their tables and, where the backend cascades, those that refer to them, and sends no `post_migrate`; and loaddata looks for fixtures in their directories and no other application's (`django/core/management/commands/loaddata.py:Command.fixture_dirs`).

In a run with `available_apps = ["harbour.fleet"]`, the port a test made was gone at the next, and the user it made, nora, was not. The `post_migrate` before each test wrote nothing: the receivers of contenttypes and auth return when the registry has no `ContentType` or no `Permission` (`django/contrib/contenttypes/management/__init__.py:create_contenttypes`, `django/contrib/auth/management/__init__.py:create_permissions`).

## Rows that migrations wrote: `serialized_rollback`

The flush takes every row, and `post_migrate` puts back only what its receivers write, under new keys, the sequences not being reset: in a run, Ship's content type had the key 9 in a class's first test and 23 in its second. A class with `serialized_rollback = True` has the rows the runner serialized after migrating written back before each test, keys and all, and its flush sends no `post_migrate`: run alone, such a class saw 9 in both tests ([Test databases: `BaseDatabaseCreation`](../backends/creation.md)).

Classes with and without it do not mix. Run after a class without it, a class with `serialized_rollback` failed in `setUpClass` with `"UNIQUE constraint failed: django_content_type.app_label, django_content_type.model"`: the first content type written back, key 1, met the one `post_migrate` had made for the same model under another key. With `--reverse`, the first test of the class without it found no content type, the other's last flush having sent no `post_migrate`. The documentation says the like of `available_apps`: no harm, provided every `TransactionTestCase` of a suite sets it, or none does.
