---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Counting queries: `assertNumQueries` and `CaptureQueriesContext`

`CaptureQueriesContext` records the statements one database connection sends during a block, by turning the connection's query log on and reading what the block added. `TransactionTestCase.assertNumQueries` is that context manager with a number to check; `TransactionTestCase.assertQuerySetEqual` compares a queryset with a list of values.

A page can render the right text and send a query for each row. Counting queries takes a log, which a connection keeps only while `BaseDatabaseWrapper.queries_logged` holds, that is while `settings.DEBUG` is on or `BaseDatabaseWrapper.force_debug_cursor` is set; the test environment turns `settings.DEBUG` off unless the run asks for `--debug-mode` ([Cursors: executing a statement, the query log and execute wrappers](../connections/cursors.md)).

## `CaptureQueriesContext`: a slice of the query log

Entering, `CaptureQueriesContext` keeps the connection's `force_debug_cursor` and sets it; calls `BaseDatabaseWrapper.ensure_connection`, so that, the comment says, queries opening the connection are not counted; notes the length of `BaseDatabaseWrapper.queries_log` as the start; and disconnects `reset_queries` from `request_started` (`django/test/utils.py:CaptureQueriesContext.__enter__`). Leaving, it puts `force_debug_cursor` back, reconnects `reset_queries` if it was the one to disconnect it, and notes the length as the end, unless an exception is leaving: then the end stays unset, and the slice runs on to the log's end (`django/test/utils.py:CaptureQueriesContext.__exit__`). `CaptureQueriesContext.captured_queries` is `BaseDatabaseWrapper.queries` sliced from start to end: dictionaries of `"sql"` and `"time"`, which the object also counts, indexes and iterates (`django/test/utils.py:CaptureQueriesContext.captured_queries`).

The test client's handler sends `request_started` at each request, and `reset_queries` empties the log of every connection the thread has made (`django/db/__init__.py:reset_queries`): in a run, a request outside a capture emptied the log, and one inside left it whole.

The slice holds every entry the block added. On SQLite, outside a `TestCase`, an atomic block with another inside was captured as `"BEGIN"`, its first count, a SAVEPOINT with the savepoint's name, the inner block's count, a RELEASE SAVEPOINT of it, and `"COMMIT"`.

## `assertNumQueries`

`TransactionTestCase.assertNumQueries` makes an `_AssertNumQueriesContext`, a `CaptureQueriesContext` on the connection `using=` names, by default `"default"`. Without a function it returns the context manager; with one, it calls it with the other arguments inside (`django/test/testcases.py:TransactionTestCase.assertNumQueries`). As a block is left, it compares the number captured with the number expected, its message listing the statements, numbered; an exception leaving the block goes on its way, and nothing is compared (`django/test/testcases.py:_AssertNumQueriesContext.__exit__`).

The list page uses `QuerySet.select_related`; these tests count its queries and a loop's:

```python
# harbour/office/tests/test_queries.py
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from harbour.fleet.models import Port, Ship


class ShipQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        valletta = Port.objects.create(name="Valletta", country="Malta")
        Ship.objects.create(name="Endeavour", tonnage=366, home=valletta)
        Ship.objects.create(name="Beagle", tonnage=235, home=valletta)

    def test_list_page(self):
        with CaptureQueriesContext(connection) as captured:
            self.client.get("/ships/")
        self.assertEqual(len(captured), 1)
        self.assertIn("INNER JOIN", captured[0]["sql"])

    def test_homes(self):
        with self.assertNumQueries(1):
            [ship.home.name for ship in Ship.objects.all()]

    def test_names(self):
        ships = Ship.objects.all()
        self.assertQuerySetEqual(ships, ["Beagle", "Endeavour"], transform=str)
        self.assertQuerySetEqual(ships, ["Endeavour", "Beagle"], transform=str, ordered=False)
```

test_names passes, and so does test_list_page: the page took one statement. test_homes reads each ship's home without `select_related`, and under the default fetch mode, `FETCH_ONE`, each read is a query ([Deferred fields and the fetch modes](../instance/fetching.md)); under `FETCH_PEERS` the loop sent two. test_homes fails at the `with` line, with this message:

```text
AssertionError: 3 != 1 : 3 queries executed, 1 expected
Captured queries were:
1. SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
2. SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."id" = 1 LIMIT 21
3. SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."id" = 1 LIMIT 21
```

The method is declared on `TransactionTestCase`, and `SimpleTestCase` has none. A capture on an alias the class does not name is refused at the `with` where the connection is not yet open, and otherwise at the block's first statement ([Which databases a test uses: `databases`](test-databases.md)).

## The log's limit

`queries_log` holds at most `BaseDatabaseWrapper.queries_limit` entries, 9,000; past that each new one pushes out the oldest, and the length stays. A capture measures lengths: with the log filled to its limit by hand, `assertNumQueries(2)` around two statements failed with "0 queries executed, 2 expected", and `queries` warned that the limit was exceeded (`django/db/backends/base/base.py:BaseDatabaseWrapper.queries`).

So `TransactionTestCase._pre_setup` clears the log of each of the class's databases but mirrors before each test of a `TransactionTestCase` or a `TestCase`, the comment saying that one test probably won't run 9,000 queries and that an overflow breaks `assertNumQueries` (`django/test/testcases.py:TransactionTestCase._pre_setup`). Outside a capture the log grows under `--debug-mode` or `--debug-sql`.

## `assertQuerySetEqual`

`TransactionTestCase.assertQuerySetEqual` takes a queryset, or any iterable, and the values expected; given `transform=`, it passes each item through that first; without, the items themselves are compared (`django/test/testcases.py:TransactionTestCase.assertQuerySetEqual`). With `ordered=False` both sides are counted with `collections.Counter`, so order is ignored and repeats are not. Otherwise the two are compared as lists, unless there is more than one value and the queryset's `QuerySet.ordered` is false, when it raises `ValueError`. Ships are ordered by name; a queryset of sailors, whose model has no ordering, was refused against two names.

> **Changed in 5.1.** The old name, assertQuerysetEqual, is removed (`docs/releases/5.1.txt`).
