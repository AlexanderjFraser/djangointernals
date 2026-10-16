---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A transaction around each test: `TestCase`

`TestCase` undoes what each test writes by rolling it back, where its databases have transactions and savepoints: `TestCase.setUpClass` opens an atomic block on each database the class uses and calls `TestCase.setUpTestData` inside it, `TestCase._fixture_setup` opens a savepoint for each test, and `TestCase._fixture_teardown` rolls back to it. `TestData` gives each test copies of what `setUpTestData` kept on the class.

`TransactionTestCase` undoes what a test wrote by emptying the tables after each test ([Emptying the tables after each test: `TransactionTestCase`](transaction-test-case.md)). `TestCase` lets the database forget instead: the class's rows are written inside a transaction that is never committed, and each test runs inside a savepoint of it, rolled back as the test ends.

`TestCase` replaces `setUpClass` and `tearDownClass`, and `_fixture_setup` and `_fixture_teardown`, which `TransactionTestCase._pre_setup` and `TransactionTestCase._post_teardown` call around each test ([One test, in order: `SimpleTestCase`](simple-test-case.md)). Each turns on whether every alias in the class's `databases` has `BaseDatabaseFeatures.supports_transactions`, and all but `_fixture_teardown` on whether each has `BaseDatabaseFeatures.uses_savepoints` too, as `TestCase._databases_support_transactions` and `TestCase._databases_support_savepoints` ask (`django/test/testcases.py:connections_support_transactions`, `django/test/testcases.py:connections_support_savepoints`). SQLite, PostgreSQL and Oracle have both; MySQL too, unless its engine is MyISAM (`django/db/backends/mysql/features.py:DatabaseFeatures.supports_transactions`).

## What ShipPageTests sends

ShipPageTests from [The test framework](../testing.md), run with `--debug-sql` and a handler printing each statement logged to `"django.db.backends"`, sends:

```text figure=the-atomics
setUpClass
  _enter_atomics              BEGIN
  setUpTestData               INSERT INTO "fleet_port" ... ('Valletta', 'Malta') ...
                              INSERT INTO "fleet_ship" ... ('Endeavour', 366, 1, NULL) ...
test_list_shows_ships
  _fixture_setup              SAVEPOINT "s30220_x4"
  the test                    SELECT ... FROM "fleet_ship" INNER JOIN "fleet_port" ...
  _fixture_teardown           PRAGMA foreign_key_check
                              ROLLBACK TO SAVEPOINT "s30220_x4"
                              RELEASE SAVEPOINT "s30220_x4"
test_missing_ship_is_404
  _fixture_setup              SAVEPOINT "s30220_x5"
  the test                    SELECT ... WHERE "fleet_ship"."id" = 999 LIMIT 21
  _fixture_teardown           PRAGMA foreign_key_check
                              ROLLBACK TO SAVEPOINT "s30220_x5"
                              RELEASE SAVEPOINT "s30220_x5"
test_rename
  _fixture_setup              SAVEPOINT "s30220_x6"
  the test                    UPDATE "fleet_ship" SET "name" = 'Resolution', ...
                              SELECT ... FROM "fleet_ship" LIMIT 21
  _fixture_teardown           PRAGMA foreign_key_check
                              ROLLBACK TO SAVEPOINT "s30220_x6"
                              RELEASE SAVEPOINT "s30220_x6"
tearDownClass
  _rollback_atomics           ROLLBACK
```

*ShipPageTests run whole: the statements Django sent to `"default"`, each beside the hook or the test that sent it. The class's transaction is begun and rolled back once; inside it each test's savepoint is made, rolled back to and released.*

The class's block sent `"BEGIN"` on entering, before any write: SQLite's backend begins a transaction with that statement, followed by the `"transaction_mode"` of its `"OPTIONS"` where one is set (`django/db/backends/sqlite3/base.py:DatabaseWrapper._start_transaction_under_autocommit`). A savepoint is named from the thread's number and the connection's count of savepoints ([Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#savepoints)).

## The class's block: `TestCase.setUpClass`

`TestCase.setUpClass` first calls the parent's: `SimpleTestCase.setUpClass` enters the class's overridden settings and guards the aliases it does not name, and `TransactionTestCase.setUpClass` runs no `_pre_setup` for a `TestCase` (`django/test/testcases.py:TransactionTestCase.setUpClass`). Without both features it stops there. Otherwise, in order (`django/test/testcases.py:TestCase.setUpClass`):

1. `TestCase._enter_atomics` makes an `atomic` block for each alias of the class, mirrors included, sets `Atomic._from_testcase` on it, which lets a durable block directly inside it through ([Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#durable-blocks)), and enters it, beginning a transaction.
2. The class's `fixtures` are loaded by loaddata into each database that is not a mirror ([Fixtures: dumpdata and loaddata](../services/fixtures.md)).
3. The class's own attributes are noted as they stand, and `setUpTestData` is called.
4. Each attribute whose value is not the object it was before, a new one or one rebound, is replaced on the class by a `TestData` holding the value.

If the fixtures or `setUpTestData` raise, `TestCase._rollback_atomics` rolls the blocks back first. `unittest` calls no `tearDownClass` after a `setUpClass` that raised.

> **Trap.** A project's `setUpClass` that raises after calling the parent's leaves the transaction open; Django's documentation warns of a segmentation fault on some platforms (`docs/topics/testing/tools.txt`).

## A copy for each test: `TestData`

`TestData` is a descriptor with a `__get__` and no `__set__` (`django/test/testcases.py:TestData`). Read from the class, it returns the value itself; read from a test, it copies the object with `copy.deepcopy` and sets the copy on the test under the same name, where later reads find it first. `unittest` makes an instance of the class for each test method, so each test copies afresh. A test's copies share one memo, kept on the test as `"_testdata_memo"` (`TestData.memo_attr`), so that, the docstring says, they keep their relations.

```python
# harbour/office/tests/test_copies.py
from django.test import TestCase

from harbour.fleet.models import Port, Ship


class ShipCopyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valletta = Port.objects.create(name="Valletta", country="Malta")
        cls.endeavour = Ship.objects.create(name="Endeavour", tonnage=366, home=cls.valletta)

    def test_a_rename(self):
        self.endeavour.name = "Resolution"
        print(self.endeavour.name, self.endeavour.home is self.valletta)

    def test_b_read(self):
        print(self.endeavour.name, ShipCopyTests.endeavour.name)
        print(ShipCopyTests.__dict__["endeavour"])
```

```text
$ python manage.py test harbour.office.tests.test_copies
...
Resolution True
.Endeavour Endeavour
<TestData: name='endeavour', data=<Ship: Endeavour>>
.
...
OK
```

A test's copies keep their relations, and a rename in one test is not seen by the next.

> **Trap.** An attribute the class had before, a list say, that `setUpTestData` changes in place keeps its identity, so it is not wrapped, and every test shares it.

## Each test's block: `TestCase._fixture_setup`

`TestCase._fixture_setup`, where the databases have transactions, refuses `reset_sequences` with a `TypeError` and calls `_enter_atomics` again. Inside the class's blocks, `Atomic.__enter__` makes each new block a savepoint (`django/test/testcases.py:TestCase._fixture_setup`; [Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#entering-a-block-atomic__enter)).

Where `setUpClass` stopped early, each test gets what it skipped. With transactions but no savepoints, each test's block begins a transaction, and the fixtures and `setUpTestData` are loaded inside it. Without transactions, `setUpTestData` is called and then `TransactionTestCase._fixture_setup`, and the test ends with the parent's flush. Nothing is wrapped in `TestData`; Django's documentation notes the speed lost without transactions (`docs/topics/testing/tools.txt`).

## The end of a test: `TestCase._fixture_teardown`

`TestCase._fixture_teardown`, where the databases have transactions, goes through the class's aliases in reverse order (`django/test/testcases.py:TestCase._fixture_teardown`). It calls `BaseDatabaseWrapper.check_constraints` on each connection that `TestCase._should_check_constraints` passes: one whose features have `BaseDatabaseFeatures.can_defer_constraint_checks`, that `BaseDatabaseWrapper.is_usable` says works, and that is not marked by `BaseDatabaseWrapper.needs_rollback`. Then, in a `finally`, `_rollback_atomics` calls `django.db.transaction.set_rollback` with `True` and leaves each block, which rolls back to its savepoint and releases it, or, where the block began the transaction, rolls that back ([Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#leaving-a-block-atomic__exit)).

SQLite, PostgreSQL and Oracle make foreign keys deferred, checked at the commit ([The connection object: `BaseDatabaseWrapper` and what a backend provides](../backends/wrapper.md#foreign-key-checks-switched-off-constraint_checks_disabled)), and a `TestCase`'s transaction never commits. The release notes of Django 1.10, which added the check, give its purpose as catching bugs (`docs/releases/1.10.txt`).

```python
# harbour/office/tests/test_constraints.py
from django.test import TestCase

from harbour.fleet.models import Ship


class OrphanShipTests(TestCase):
    def test_ship_of_no_port(self):
        Ship.objects.create(name="Beagle", tonnage=235, home_id=999)
```

```text
$ python manage.py test harbour.office.tests.test_constraints
...
.E
...
django.db.utils.IntegrityError: The row in table 'fleet_ship' with primary key '1' has an invalid foreign key: fleet_ship.home_id contains a value '999' that does not have a corresponding value in fleet_port.id.
...
Ran 1 test in 0.001s
```

The deferred key let Beagle in with a home port that does not exist, and `unittest` recorded a success, the dot. Then `"PRAGMA foreign_key_check"` found the row, SQLite's `check_constraints` raised (`django/db/backends/sqlite3/base.py:DatabaseWrapper.check_constraints`), and `SimpleTestCase._setup_and_call` added an error to the same test, the E.

## The end of the class: `TestCase.tearDownClass`

`TestCase.tearDownClass`, where the databases have both features, rolls the class's blocks back, ending each transaction, and closes every connection that was opened; in every case it then calls the parent's (`django/test/testcases.py:TestCase.tearDownClass`). Between tests `TransactionTestCase._post_teardown` closes none, as `TestCase._should_reload_connections` answers false wherever there are transactions.

## What a test inside the blocks does not see

Inside a `TestCase`'s blocks nothing is committed. A callback registered with `on_commit` does not run; `TestCase.captureOnCommitCallbacks` collects such callbacks and can call them ([Work held until the commit: `on_commit`](../backends/on-commit.md)). Another connection does not see the rows, which the docstring of `LiveServerTestCase` gives as the reason it is a `TransactionTestCase` ([A server in a thread: `LiveServerTestCase`](live-server.md)).
