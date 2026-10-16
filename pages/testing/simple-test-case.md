---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# One test, in order: `SimpleTestCase`

How `SimpleTestCase.__call__` runs one test, Django's hooks `SimpleTestCase._pre_setup` and `SimpleTestCase._post_teardown` around those of `unittest`; what `SimpleTestCase.setUpClass` does for a class; and `SimpleTestCase.assertRaisesMessage` and `SimpleTestCase.assertFieldOutput`.

`unittest` gives a test case two hooks around each test, `unittest.TestCase.setUp` and `unittest.TestCase.tearDown`, and both are the project's to override. So `SimpleTestCase`, the base of every Django test case class, does its own work around each test from `__call__`, the method `unittest` calls to run one: its docstring says this is so that a project's test case need not call `super().setUp()` (`django/test/testcases.py:SimpleTestCase.__call__`).

## The hooks of a class

The three classes run the same hooks in the same order ([Emptying the tables after each test: `TransactionTestCase`](transaction-test-case.md), [A transaction around each test: `TestCase`](test-case.md)). Each class does what its parent does, and what its column adds or replaces:

| hook | `SimpleTestCase` | `TransactionTestCase` | `TestCase` |
|---|---|---|---|
| `setUpClass` | the class's overrides entered; the database guard set | if not a `TestCase`, `_pre_setup` for the first test | an atomic block on each of its databases; the fixtures; `TestCase.setUpTestData`; its objects made `TestData` |
| `_pre_setup` | new clients; the outbox emptied | as the class asks, `TransactionTestCase.available_apps` applied, sequences reset, serialized rows and fixtures loaded; the query log cleared | in place of the reset and the loading, an atomic block inside the class's: a savepoint |
| `setUp`, the method, `tearDown`, the cleanups | the project's; an `async def` method run by `async_to_sync` | nothing | nothing |
| `_post_teardown` | nothing | the flush command on each of its databases; connections closed; `available_apps` undone | in place of the flush, deferred constraints checked, the savepoint rolled back; connections left open |
| `tearDownClass` | nothing | if not a `TestCase`, `available_apps` undone if still applied | the class's atomic blocks rolled back; connections closed |
| the class cleanups | the database guard removed; the overrides left | nothing | nothing |

*A test case class's hooks, in order; the rows from `_pre_setup` to `_post_teardown` repeat for each test. `TestCase`'s column holds where its databases have transactions and savepoints.*

## Running one test: `_setup_and_call`

`unittest`'s suite calls a test with the result that collects outcomes, and `__call__` passes that to `SimpleTestCase._setup_and_call` (`django/test/testcases.py:SimpleTestCase._setup_and_call`):

1. A test whose class or method is marked skipped, as `unittest.skip` marks it, gets neither of Django's hooks.
2. A coroutine test method is replaced on the instance by `async_to_sync` of it, which runs it on an event loop in another thread ([Sync and async in one chain](../handlers/async.md)); `unittest.TestCase.setUp` and `unittest.TestCase.tearDown` are not converted.
3. `_pre_setup` is called, unless the class's `SimpleTestCase._pre_setup_ran_eagerly` says `TransactionTestCase.setUpClass` has done it; then the flag is cleared. If it raises, the exception is added to the result as an error, and nothing more is done.
4. `unittest.TestCase.__call__` runs the test: the result's `unittest.TestResult.startTest`; `setUp`; the method and `tearDown` only if `setUp` succeeded; the cleanups in any case.
5. `_post_teardown` is called, whatever the outcome. An exception there is added as an error too, and a test that passed is then reported both as a success and as an error.

A module that prints each hook as it runs:

```python
# harbour/office/tests/test_hooks.py
import threading

from django.test import SimpleTestCase, TestCase


class Hooks:
    @classmethod
    def setUpClass(cls):
        print(cls.__name__, "setUpClass")
        super().setUpClass()

    @classmethod
    def _pre_setup(cls):
        print("  _pre_setup")
        super()._pre_setup()

    def setUp(self):
        print("    setUp")
        self.addCleanup(print, "    cleanup")

    def tearDown(self):
        print("    tearDown")

    def _post_teardown(self):
        super()._post_teardown()
        print("  _post_teardown")


class ShipPageHookTests(Hooks, TestCase):
    async def test_page(self):
        print("      test_page, on", threading.current_thread().name)


class ShipNumberTests(TestCase):
    reset_sequences = True

    def test_first_ship(self):
        print("      test_first_ship")


class BerthHookTests(Hooks, SimpleTestCase):
    def setUp(self):
        super().setUp()
        raise RuntimeError("no berth free")

    def test_berth(self):
        print("      test_berth")
```

At verbosity 0, the second error's traceback left out:

```text
$ python manage.py test harbour.office.tests.test_hooks -v 0
System check identified no issues (0 silenced).
ShipPageHookTests setUpClass
  _pre_setup
    setUp
      test_page, on ThreadPoolExecutor-1_0
    tearDown
    cleanup
  _post_teardown
BerthHookTests setUpClass
  _pre_setup
    setUp
    cleanup
  _post_teardown
======================================================================
ERROR: test_first_ship (harbour.office.tests.test_hooks.ShipNumberTests.test_first_ship)
----------------------------------------------------------------------
TypeError: reset_sequences cannot be used on TestCase instances

======================================================================
ERROR: test_berth (harbour.office.tests.test_hooks.BerthHookTests.test_berth)
----------------------------------------------------------------------
...
RuntimeError: no berth free

----------------------------------------------------------------------
Ran 2 tests in 0.002s

FAILED (errors=2)
```

Where `setUp` raised, the cleanup and `_post_teardown` still ran. ShipNumberTests' method never ran: on a database with transactions, `TestCase._fixture_setup`, which `_pre_setup` calls, refuses `TransactionTestCase.reset_sequences` (`django/test/testcases.py:TestCase._fixture_setup`). The run counts two tests of three: counting is `startTest`'s, which `_setup_and_call` never reached.

> **Changed in 5.2.** `django/test/testcases.py` sets `__unittest = True`, the mark of a module whose frames `unittest` cuts from a reported traceback: those it starts with, and, in a failure, every frame from the next of them on. So a failure in one of Django's assertions is reported without the assertion's frames: easier to read, the release note says, and `--pdb` enters the failing test directly (`docs/releases/5.2.txt`). Every frame of the `TypeError` above is in that module: it has no traceback.

`SimpleTestCase.debug` runs the same steps but raises what they would add to a result, and runs the test by `unittest.TestCase.debug`, so a failing test never reaches `_post_teardown` (`django/test/testcases.py:SimpleTestCase.debug`). `SimpleTestCase.__getstate__` makes a test case picklable, as a failed subtest sent from a parallel run's worker needs ([Running in parallel: `ParallelTestSuite`](parallel.md)).

## Before each test: `_pre_setup`

`SimpleTestCase._pre_setup` makes a test client and an asynchronous one, of the classes `SimpleTestCase.client_class` and `SimpleTestCase.async_client_class` name, and empties the local-memory email backend's outbox (`django/test/testcases.py:SimpleTestCase._pre_setup`). Each test so begins with no mail and a client with no cookies, and so no session, but a `TransactionTestCase`'s first test finds the outbox and the client as `setUpClass` left them, having run `_pre_setup` for it. It is a class method, and keeps the clients on the class, as `SimpleTestCase.client` and `SimpleTestCase.async_client`.

## A class: `SimpleTestCase.setUpClass`

`SimpleTestCase.setUpClass` calls `unittest`'s, then does two things (`django/test/testcases.py:SimpleTestCase.setUpClass`). If `override_settings` or `modify_settings` decorated the class, it enters a new one made from their options, by `unittest.TestCase.enterClassContext` ([Settings for one test: `override_settings` and `TestContextDecorator`](test-decorators.md)). Then it sets the guard that refuses the class every database it does not name, and registers the guard's removal with `unittest.TestCase.addClassCleanup` ([Which databases a test uses: `databases`](test-databases.md)), where the override's exit was registered too. Class cleanups run after `tearDownClass`, the last registered first, and, unlike `tearDownClass`, also when `setUpClass` raised after registering them. A project's `setUpClass` that does not call the parent's loses all of this, as the documentation warns (`docs/topics/testing/tools.txt`).

Inside a test, `SimpleTestCase.settings` and `SimpleTestCase.modify_settings` return an `override_settings` and a `modify_settings`.

## Assertions on exceptions and form fields

`SimpleTestCase.assertRaisesMessage` and `SimpleTestCase.assertWarnsMessage` are `unittest.TestCase.assertRaises` and `unittest.TestCase.assertWarns` with a check that the expected text is in the string of what was caught, as a substring, not a pattern (`django/test/testcases.py:SimpleTestCase._assert_raises_or_warns_cm`). Given a callable and its arguments, the assertion calls it; given none, it is a context manager (`django/test/testcases.py:SimpleTestCase._assertFooMessage`). This test passes, its parentheses taken as they stand:

```python
# harbour/office/tests/test_urls.py
from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse


class ShipUrlErrorTests(SimpleTestCase):
    def test_detail_needs_a_number(self):
        with self.assertRaisesMessage(NoReverseMatch, "1 pattern(s) tried"):
            reverse("ship-detail", args=["Endeavour"])
```

`SimpleTestCase.assertFieldOutput` makes a form field as given and with `required=False`. Each valid input must clean to its value in both, each invalid one raise a `ValidationError` with the messages given, and each of `empty_values` be refused by the first with its `"required"` message and cleaned by the second to the empty value given, `""` by default; a subclass of `django.forms.fields.CharField` must accept `min_length=2` and `max_length=20` (`django/test/testcases.py:SimpleTestCase.assertFieldOutput`).
