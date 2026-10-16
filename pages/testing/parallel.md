---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Running in parallel: `ParallelTestSuite`

`ParallelTestSuite` is the suite the runner builds when `--parallel` asks for more than one process and the suite has more than one class: one subsuite for each test class, a `multiprocessing.Pool` of worker processes that run them, each worker on its own clone of each test database, and the parent process replaying what the workers report into the one result that `unittest` prints.

Tests running at once cannot share a database, so each process needs its own copy of each test database, and must know which is its own; and `unittest.TextTestRunner` must still count and print every result. The work is done in a suite, the docstring of `ParallelTestSuite` says, because test runner classes such as `unittest.TextTestRunner` are in practice more concerned with displaying results, and are customised more often than suites: one test runner still collects every result without knowing the tests ran in parallel (`django/test/runner.py:ParallelTestSuite`).

## How many processes: `--parallel`

`--parallel` takes a number, or `"auto"`, which it also means given alone; `parallel_type` refuses anything else (`"'many' is not an integer or the string 'auto'"`). Without it, 0: one process. The test command turns `"auto"` into `get_max_test_processes`: 1 where `multiprocessing.get_start_method` is not fork, spawn or forkserver, which a comment says the runner requires; otherwise the environment variable `"DJANGO_TEST_PROCESSES"`, or the number of CPUs (`django/test/runner.py:get_max_test_processes`, `django/core/management/commands/test.py:Command.handle`). A number given goes to the runner as it is. `--pdb` is refused with more than one ([The runner: the test command and `DiscoverRunner`](runner.md)).

> **Changed in 6.0.** The parallel runner supports the forkserver start method (`docs/releases/6.0.txt`).

## One subsuite for each class

`DiscoverRunner.build_suite` ends by cutting the ordered suite when more than one process is asked for (`django/test/runner.py:DiscoverRunner.build_suite`). `partition_suite_by_case` makes each run of consecutive tests of one class a subsuite, and the ordering keeps a class's tests together ([Finding and ordering the tests: `DiscoverRunner.build_suite`](discovery.md); `django/test/runner.py:partition_suite_by_case`). The number of processes is cut to the number of subsuites, a comment saying no more are needed, and `DiscoverRunner.parallel` is set to it, another saying the number of test databases is taken from it. Only if more than one process remains is the suite a `ParallelTestSuite`, of the class in `DiscoverRunner.parallel_test_suite`: a label of one class runs in one process, and nothing is cloned.

`setup_databases` clones each test database once per process as soon as it is made, with the suffixes `"1"`, `"2"` and on; `teardown_databases` destroys the clones first (`django/test/utils.py:setup_databases`; [Test databases: `BaseDatabaseCreation`](../backends/creation.md#clones-for-parallel-test-runs)). The office's tests with a third class:

```python
# harbour/office/tests/test_ports.py
from django.test import TestCase

from harbour.fleet.models import Port


class PortTests(TestCase):
    def test_new_port(self):
        Port.objects.create(name="Valletta", country="Malta")
        self.assertEqual(Port.objects.count(), 1)

    def test_no_ports_yet(self):
        self.assertFalse(Port.objects.exists())
```

```text
$ python manage.py test harbour.office --parallel 2
Found 6 test(s).
Creating test database for alias 'default'...
Cloning test database for alias 'default'...
Cloning test database for alias 'default'...
System check identified no issues (0 silenced).
......
----------------------------------------------------------------------
Ran 6 tests in 0.733s

OK
Destroying test database for alias 'default'...
Destroying test database for alias 'default'...
Destroying test database for alias 'default'...
```

With twenty CPUs here, `--parallel auto` made three clones, one for each class; `--parallel` alone, with `"DJANGO_TEST_PROCESSES"` set to 2, made two.

## The parent: `ParallelTestSuite.run`

`ParallelTestSuite.run` does the rest, in the parent (`django/test/runner.py:ParallelTestSuite.run`):

1. Under spawn or forkserver, `ParallelTestSuite.initialize_suite` collects each alias's settings, as the test databases have left them, and the serialized rows, for workers that do not start with a copy of the parent's memory; a forked worker has them in the memory it copied.
2. It makes, in shared memory, a slot for each process, so for each clone, holding the pid of the worker that took it or 0, and a flag a worker sets if its start fails.
3. It makes a task of each subsuite, with its index and the failfast and buffering options; the subsuite goes to a worker pickled, and the index comes back with a list of events.
4. It turns buffering off in its own result, a comment saying this avoids problems in propagating errors.
5. It makes a `multiprocessing.Pool`, each process started by `_safe_init_worker` around `_init_worker`, and hands it the tasks with `multiprocessing.pool.Pool.imap_unordered`, which yields results as workers return them.
6. It waits in a loop. Each turn terminates the pool if the result has been told to stop, by failfast or a Ctrl-C; frees the slots of exited workers (`_release_dead_worker_slots`); and waits a tenth of a second for a result. If none came and a worker failed to start, it raises the timeout with the note `"ERROR: _init_worker failed, see prior traceback"`.

`ParallelTestSuite.handle_event` calls the method of the parent's result that each event names, with the test at the event's index in the parent's own subsuite (`django/test/runner.py:ParallelTestSuite.handle_event`). For each passing test the workers sent `startTest`, `addDuration`, `addSuccess` and `stopTest`, and the runner's result printed and counted them as in one process. A class is reported when its worker ends it: at verbosity 2 the run printed PortTests, ShipUrlTests, ShipPageTests. With `--failfast`, a failure replayed in the parent terminated the pool, and the running classes went unreported.

## A worker: `_init_worker`

`multiprocessing.Pool` runs `_init_worker` once in each worker as it starts (`django/test/runner.py:_init_worker`). It claims a slot with `_claim_database_clone_slot`: the one already holding the worker's pid, else the first holding 0, retrying for five seconds before a `RuntimeError`; the slot's number, from 1, kept as `_worker_id`, is the suffix of its clones. Slots, the docstring says, make a worker the pool starts in place of one that exited wait for the parent to free that slot, rather than take a number with no clone; the pid's own slot comes first, a comment says, so that a replacement given a dead worker's pid never holds two (`django/test/runner.py:_claim_database_clone_slot`).

Under spawn or forkserver it then sets itself up as the parent was: `ParallelTestSuite.process_setup`, empty unless set, then `django.setup`, and `setup_test_environment` with the run's `--debug-mode`. For each alias the tests use it restores the parent's settings and serialized rows, and calls `BaseDatabaseCreation.setup_worker_connection` with its number, pointing the connection at its clone, which SQLite's, under spawn or forkserver, copies into memory ([Test databases: `BaseDatabaseCreation`](../backends/creation.md#sqlite-the-in-memory-test-database-and-the-start-method)). Last it runs the check command, discarding the output. A worker started by fork, which the runs here did not use, only claims a slot and calls `setup_worker_connection`.

Each task runs in `_run_subsuite`, which returns the index and the events (`django/test/runner.py:_run_subsuite`); a worker free again takes the next task, on the same clone. Here, where workers start by spawn, a runner printing what each process did drew this run:

```text figure=the-workers
python manage.py test harbour.office --parallel 2      workers started by spawn

THE PARENT
  build_suite       subsuites 0 PortTests, 1 ShipPageTests, 2 ShipUrlTests; 2 processes
  setup_databases   the test database of "default", then its clones "1" and "2"
  run               slots [0, 0]; a Pool of two workers; tasks 0, 1, 2

WORKER A, slot 2                        WORKER B, slot 1
  django.setup, setup_test_environment,   the same, with clone 1
  the parent's settings, clone 2 copied
  into memory, check
  subsuite 0, PortTests: its events,      subsuite 1, ShipPageTests
  for each test startTest, addDuration,
  addSuccess, stopTest, sent back
  subsuite 2, ShipUrlTests: its events
                                          its events sent back

THE PARENT replays each list as it arrives into its result, which prints
  PortTests' two tests, ShipUrlTests' one, ShipPageTests' three: Ran 6 tests, OK
  teardown_databases: clones "1" and "2", then the test database
```

*Two workers and three classes: each worker claims a slot and works on its clone, takes a subsuite whenever it is free, and sends back each subsuite's events at its end, for the parent to replay. Which worker takes which slot and subsuite varies from run to run.*

## What a worker sends back: `RemoteTestResult`

`RemoteTestRunner.run` makes a `RemoteTestResult` with the failfast and buffering options, runs the subsuite, and prints nothing (`django/test/runner.py:RemoteTestRunner.run`). The result records each call, but a passing subtest's, as an event: the method's name, the index of the current test in the subsuite, and the arguments, such as a failure's exception (`django/test/runner.py:RemoteTestResult`). Its lists of failures and errors are a `DummyList`, which keeps nothing, to save memory, a comment says; `RemoteTestResult.wasSuccessful` reads the events.

An exception reaches the parent pickled, and Python cannot pickle a traceback; tblib, a third-party library, makes it picklable where installed. `RemoteTestResult.check_picklable` pickles and unpickles each exception before recording it, and on failure prints the test, the exception and advice, and lets the error rise, ending the run (`django/test/runner.py:RemoteTestResult.check_picklable`). With test_new_port expecting two ports and no tblib, the worker printed the advice to install tblib, and the parent destroyed the test databases and ended with `"TypeError: cannot pickle 'traceback' object"`, with no summary; with tblib, the run reported the failure, its traceback and `"FAILED (failures=1)"`.

A failed subtest's event carries the subtest, and so the test case, which `SimpleTestCase.__getstate__` pickles, while it runs, without its outcome and whatever cannot be pickled (`django/test/testcases.py:SimpleTestCase.__getstate__`).

> **Trap.** With tblib, an error before a subsuite's first test, from `setUpClass`, is sent with `unittest`'s description of it, and reported as `setUpClass`. A later one carries only the index of the last test run: an exception from `tearDownClass` was reported in a parallel run as an error of the class's last test, test_second, and in one process as `tearDownClass` (`django/test/runner.py:RemoteTestResult.addError`).

## Classes that take turns: `SerializeMixin`

`SerializeMixin` makes classes that share something outside their databases, such as a file, take turns (`django/test/testcases.py:SerializeMixin`). A class built on it names an existing file in `SerializeMixin.lockfile`; its `SerializeMixin.setUpClass` opens the file and takes an exclusive lock with `django.core.files.locks.lock`, waiting while another class holds it, before calling the next `setUpClass`, and the file is closed, freeing the lock, as a class cleanup after `tearDownClass`. The docstring asks for it early among the bases, so that the lock covers the other classes' set-up and tear-down. A subclass defined while `lockfile` is `None` is refused with `ValueError` (`"ChartTests.lockfile isn't set. Set it to a unique value in the base class."`). In a run in three processes, the second of two classes sharing a lock file began when the first ended.
