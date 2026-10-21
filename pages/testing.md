---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Applications and tools
contents: runner, discovery, environment, test-databases, simple-test-case, transaction-test-case, test-case, test-decorators, request-factory, client, client-login, response-assertions, html-assertions, query-assertions, live-server, parallel
---

# The test framework

`django.test` runs a project's tests, written as `unittest` test cases, against the project itself. The test command hands them to a runner, by default `DiscoverRunner`, which finds them, makes a test database for each database they use and runs them; the test case classes `SimpleTestCase`, `TransactionTestCase` and `TestCase` keep each test from seeing what another wrote to the database; and the `Client` sends requests through the project's middleware and views with no server.

A test of a Django project exercises the project as it runs: its models write to a database, its views answer requests, its settings decide what happens. The framework's work is to let that happen without harm and without one test disturbing the next. The tests must not write to the database the settings name, so each database they use gets a twin made for the run, given the schema the models need, and destroyed at the end. Each test must begin from the same state, so what a test writes has to be undone before the next begins. A view must be called as a server would call it, so a test can send a request through the handler and read the response. A test may need a setting changed, and the process must be put back afterwards. And what would otherwise leave the process, a message sent by mail, a template rendered and gone, must be kept where a test can look at it.

All of it is built on `unittest` from Python's standard library. A test class is a subclass of `unittest.TestCase`; the runner, by default, finds tests with `unittest`'s loader and, in one process, runs them with `unittest.TextTestRunner`, which counts the failures. What Django adds sits mostly around those: steps before and after the suite, and hooks before and after each class and each test; inside a test, it adds assertions and helpers of its own.

## The objects

| object | what it is | when it acts |
|---|---|---|
| `DiscoverRunner` | the **runner**: finds the tests, sets the process up for them, makes the test databases, runs the suite and undoes what it set up | once a run, called by the test command |
| `setup_test_environment` | the **test environment**: `"testserver"` added to `ALLOWED_HOSTS`, debugging as the runner asks (off unless told otherwise), mail kept in memory, every render of a Django template reported | once, before the suite, and undone after it; again, and never undone, in each worker a parallel run starts by spawn or forkserver |
| `BaseDatabaseCreation` | a connection's **creation**: makes, migrates and destroys a **test database** | for each database the tests use, before and after the suite |
| `SimpleTestCase` | the base of Django's test cases: a fresh client before each test, settings overridden for a class, queries refused to a database the class does not name | around each test, and each class |
| `TransactionTestCase` | a test case that may use the database, and empties its tables after each test | around each test; its first test's `_pre_setup` runs in `setUpClass` |
| `TestCase` | a test case whose tests run, where the database allows, inside a transaction opened for the class, each in a savepoint, all rolled back | around each class, and each test |
| `LiveServerTestCase` | a `TransactionTestCase` with a real HTTP server in a thread, for a browser to talk to | around each class, and each test |
| `Client` | the **test client**: a request sent through a handler of its own, over the project's middleware and views, the response returned with what rendered it and its cookies kept, or an exception answered with a 500 raised in the test | at each request a test makes |
| `RequestFactory` | builds a request and nothing more, for a view called directly | at each request a test builds |
| `override_settings` | settings changed for a block, a test or a `SimpleTestCase` class, and put back | around a block or a test; for a class, from its `SimpleTestCase.setUpClass` to after its `tearDownClass` |
| `ParallelTestSuite` | the suite cut into its classes and run by worker processes, each on a copy of each test database the suite uses | in place of the suite, when `--parallel` asks for more than one process and the suite has more than one class |

*The objects of the test framework. All are in `django/test/` but the creation, which each database backend provides (`django/db/backends/base/creation.py`).*

## The harbour office's tests

The harbour office's site lists its ships at ships/ and shows each at ships/ followed by its key, with a page to register a new ship behind a login. Its tests are a package of the office application, which the runner finds by its default pattern, `"test*.py"`:

```python
# harbour/office/tests/test_ships.py
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from harbour.fleet.models import Port, Ship


class ShipPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valletta = Port.objects.create(name="Valletta", country="Malta")
        cls.endeavour = Ship.objects.create(name="Endeavour", tonnage=366, home=cls.valletta)

    def test_list_shows_ships(self):
        response = self.client.get("/ships/")
        self.assertContains(response, "Endeavour")
        self.assertTemplateUsed(response, "office/ship_list.html")

    def test_missing_ship_is_404(self):
        response = self.client.get("/ships/999/")
        self.assertEqual(response.status_code, 404)

    def test_rename(self):
        self.endeavour.name = "Resolution"
        self.endeavour.save()
        self.assertEqual(Ship.objects.get().name, "Resolution")


class ShipUrlTests(SimpleTestCase):
    def test_detail_url(self):
        self.assertEqual(reverse("ship-detail", args=[1]), "/ships/1/")
```

The settings name two SQLite databases, `"default"` and `"archive"`, as files beside manage.py. A run of these tests, as a terminal shows it:

```text
$ python manage.py test harbour.office
Found 4 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
....
----------------------------------------------------------------------
Ran 4 tests in 0.015s

OK
Destroying test database for alias 'default'...
```

The first line is the runner's count of what it found, and the line of the system checks is the check command's, which the runner calls once the test databases exist. Before it the creation of `"default"` made its test database, and after the dots, one to a test that passed, destroyed it. No test database was made for `"archive"`, because no test asked for it (at a higher verbosity the runner says so), and neither database file was made: with no `"NAME"` in its `"TEST"` settings, SQLite's test database is kept in memory. The test test_rename saved a new name, and no other test sees it; the rest of the page says why.

## A run, in order

The test command takes the runner's class from `--testrunner` or from the setting `TEST_RUNNER`, whose default is `DiscoverRunner`, makes it with the command's options, and calls its `run_tests` with the labels typed after `test`. The runner returns the number of failures, errors and unexpected successes the result recorded, and the command ends the process with status 1 if there are any ([The runner: the test command and `DiscoverRunner`](testing/runner.md); `django/core/management/commands/test.py:Command.handle`). `DiscoverRunner.run_tests` calls the runner's own methods in a fixed order, each of which a subclass may replace (`django/test/runner.py:DiscoverRunner.run_tests`):

```text figure=the-run
python manage.py test harbour.office
  test command: the runner class from TEST_RUNNER, DiscoverRunner, made with the options
  DiscoverRunner.run_tests(("harbour.office",))
    setup_test_environment      "testserver" allowed, DEBUG off, mail kept in memory, renders reported
    build_suite                 the tests found from the labels; TestCase classes before other Django tests, plain unittest tests last
    get_databases               the aliases the tests' databases attributes name: "default"
    setup_databases             a test database for each, made and migrated
    run_checks                  the system checks, now that the test databases exist
    run_suite                   unittest runs the suite, a class at a time
      ShipPageTests, a TestCase
        setUpClass              a transaction opened on "default"; setUpTestData writes its rows inside it
          each test             a new Client; a savepoint; setUp, the test, tearDown; back to the savepoint
        tearDownClass           the transaction rolled back
      ShipUrlTests, a SimpleTestCase
          each test             a new Client; a query to any database refused
    teardown_databases          each test database destroyed
    teardown_test_environment   the settings and the template renderer put back
  any failure, error or unexpected success: the process ends with status 1
```

*One run of `manage.py test harbour.office`: the runner's steps in order, and within the suite the life of each class. On a database with transactions and savepoints, nothing a `TestCase` writes is committed: its tests run inside a transaction opened for the class, each in a savepoint that is rolled back.*

**The environment** comes first. `setup_test_environment` adds `"testserver"`, the host the test client's requests name, to `ALLOWED_HOSTS`; sets `settings.DEBUG` to what the runner passes, false unless the run was asked for `--debug-mode`; points the mailers (every alias of `MAILERS`, or `EMAIL_BACKEND` where a project has none) at the backend that keeps messages in a list in memory, the outbox; and replaces the method that renders a template of Django's own language, `_render`, on both the template's class and the partial's, with one that first sends the signal `template_rendered`, which the client listens to, and `assertTemplateUsed` as a context manager ([The test environment: `setup_test_environment`](testing/environment.md); `django/test/utils.py:setup_test_environment`).

**The suite** is built next, from the labels: a dotted name is loaded as it is, a package in which that finds no test, or a directory, is searched for modules that match the pattern, and a path to a file is refused. The runner then reorders what it found, by default: any module or name that failed to load first, then the `TestCase` classes, then the other classes built on `SimpleTestCase`, then plain `unittest` tests; Django's documentation gives the reason as guaranteeing that every `TestCase` starts with a clean database (`docs/topics/testing/overview.txt`). The tests of one class are kept together ([Finding and ordering the tests: `DiscoverRunner.build_suite`](testing/discovery.md); `django/test/runner.py:reorder_tests`).

**The test databases** are made only for the aliases some test may use, and an alias whose `"TEST"` settings name it a mirror of another is pointed at that one's; by default every other alias with a database of its own waits for `"default"`'s, which must then be among them. Each test class names them in its `databases` attribute, empty on `SimpleTestCase` and `"default"` alone on `TransactionTestCase` and so on `TestCase`, and the runner collects them from every test of the suite ([Which databases a test uses: `databases`](testing/test-databases.md); `django/test/runner.py:DiscoverRunner._get_databases`, `django/test/utils.py:get_unique_databases_and_mirrors`). For each database among them, `setup_databases` calls the creation of its first alias, which makes the database, points the alias's settings at it so that every connection to the alias reaches it, and runs migrate there ([Test databases: `BaseDatabaseCreation`](schema/test-databases.md)). The system checks run after this, a comment in the runner saying that some of them need the database (`django/test/runner.py:DiscoverRunner.run_checks`).

**The suite runs** under `unittest`, which ordinarily sets each class up with `setUpClass`, runs its tests, and tears it down with `tearDownClass` and the class's cleanups, and after a `setUpClass` that raised runs only the cleanups; in a parallel run that happens in the workers. Django's own work around a single test is called from `SimpleTestCase.__call__`, which `unittest` calls to run one: a hook before the test, `_pre_setup`, and one after it, `_post_teardown`, around the `setUp`, the test method, the `tearDown` and the cleanups that `unittest` runs between them. The hooks are Django's rather than the project's, so a test class that overrides `setUp` without calling the parent's loses none of them (`django/test/testcases.py:SimpleTestCase._setup_and_call`; [One test, in order: `SimpleTestCase`](testing/simple-test-case.md), which has the exceptions: a test marked skipped gets neither hook, one whose `_pre_setup` raises gets nothing more, and a `TransactionTestCase` that is not a `TestCase` runs its first test's `_pre_setup` in `setUpClass`). Then the test databases are destroyed, unless `--keepdb` asked for them to be kept, and the environment undone, in a `finally` around the checks and the suite that runs whether they passed or not.

A run in several processes, with `--parallel`, cuts the suite into its classes and hands them out to worker processes, each of which works on a copy of each test database the suite uses; a worker started by spawn or forkserver, as on Windows, first sets Django and the environment up again for itself and runs the checks ([Running in parallel: `ParallelTestSuite`](testing/parallel.md)).

## Keeping tests apart

The three test case classes differ in what they do about the database, and so in what one test can leave behind for another.

A `SimpleTestCase` may not use a database unless it names one. Its `databases` is empty by default, and as each class is set up, every connection of the setting-up thread whose alias it does not name has its methods that connect or open a cursor replaced with ones that raise `DatabaseOperationForbidden`, an `AssertionError` whose message says to subclass `TestCase` or `TransactionTestCase`, or to add the alias to `databases`; for the length of the class, opening a connection to such an alias in another thread is refused too (`django/test/testcases.py:SimpleTestCase._add_databases_failures`). A class that names an alias in `databases` is let through to that one: the guard is on every Django test case, each refusing the aliases it does not name.

A `TransactionTestCase` uses the database and cleans up after itself the long way. After each test it runs the flush command on each of its databases that is not a mirror, which empties the models' tables (under `available_apps`, those applications'), and before each test it loads the class's fixtures again ([Emptying the tables after each test: `TransactionTestCase`](testing/transaction-test-case.md); `django/test/testcases.py:TransactionTestCase._fixture_teardown`). What a test of this class commits is committed, for the length of the test: other connections see it, and code that commits or rolls back does so for real. The cost is the flush, and what it takes with it: the rows that migrations wrote come back only where the class asks for them with `serialized_rollback` and the runner kept them, the content types and permissions apart, which receivers of `post_migrate` ordinarily make again after the flush, under new keys (not under `available_apps`, nor where the rows are to be loaded back).

A `TestCase` relies on the database's transactions instead. Where its databases have transactions and savepoints, as the class is set up it opens an atomic block on each of them, loads the class's fixtures and calls `TestCase.setUpTestData`, all inside it; before each test it opens another atomic block inside the first, which is a savepoint; and after each test it rolls that back, and after the last the outer block too (`django/test/testcases.py:TestCase.setUpClass`, `django/test/testcases.py:TestCase._fixture_setup`). So the harbour office's test_rename saved its new name inside its savepoint, and the rollback to the savepoint undid it. The rows made in `setUpTestData` are made once for the class; each test gets its own deep copy of each object the method bound to an attribute of the class, so that a test that renames Endeavour renames a copy ([A transaction around each test: `TestCase`](testing/test-case.md)). On a database without transactions, a `TestCase` calls `setUpTestData` before each test and flushes after it, as a `TransactionTestCase` does; with transactions but no savepoints, each test runs in a transaction of its own.

The price of the transaction is what a test inside it cannot see. Inside the blocks nothing a `TestCase` writes is committed, so a callback registered with `on_commit` does not run unless the test asks for it ([Work held until the commit: `on_commit`](connections/on-commit.md)), and another connection does not see the rows. The docstring of `LiveServerTestCase`, whose server answers in another thread, gives that as the reason it is a `TransactionTestCase`: threads do not share transactions, so each must commit for the other to see its rows; with SQLite's database in memory the test hands the server's thread its own connection, and the two share one ([A server in a thread: `LiveServerTestCase`](testing/live-server.md); `django/test/testcases.py:LiveServerTestCase`).

## Requests without a server

A test asks for a page with the client its class makes before each test, `SimpleTestCase.client`. `Client` is a `RequestFactory` that sends what it builds: the factory turns the method, the path, the data and the headers into the dictionary a WSGI server would pass, with `"testserver"` as the server's name ([Building a request: `RequestFactory`](testing/request-factory.md)), and the client hands that dictionary to the `ClientHandler` it made for itself, a subclass of the same `BaseHandler` the WSGI and ASGI handlers are built on ([Handlers and middleware](handlers.md)). The handler builds its middleware chain at the client's first request, from the settings as they are then, and keeps it for the client's life; it sends each request through the chain to the view much as a server's handler would, though not quite: it sets no script prefix, leaves the test's database connections open, and returns the response object itself, its body emptied where a server would send none (`django/test/client.py:ClientHandler.__call__`).

What the client adds is on the way back. While the request runs, `Client.request` listens to `template_rendered` and keeps each template rendered and a copy of its context, and listens to `got_request_exception`, which the handler sends for an exception it has no answer for but a 500, and keeps that exception. It raises that exception again in the test, unless the client was made with `raise_request_exception=False`; otherwise it gives the response the templates and the contexts, the arguments the request was built from, a `json` function and a `resolver_match` worked out from the path when first read, and keeps the cookies the response set, so that the next request sends them, a session's among them, unless it gives a `"Cookie"` header of its own (`django/test/client.py:Client.request`). Some assertions read what the client added: `assertTemplateUsed`, given a response, its templates; `assertRedirects` the chain where the client followed redirects, and the client itself where it fetches the target ([The test client: `Client` and `ClientHandler`](testing/client.md), [Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`](testing/response-assertions.md)).

The test client is not a browser. It runs no JavaScript and does not check the CSRF token unless it is made with `enforce_csrf_checks=True`: its handler marks every request as one `CsrfViewMiddleware` should let through ([The CSRF check: `CsrfViewMiddleware.process_view`](security/csrf-check.md)). A test that needs a browser runs a real server with `LiveServerTestCase` and drives a browser at it with a library of its own.

## Settings and the state of the process

A test that needs a setting changed decorates itself, or its class if that is a `SimpleTestCase`, with `override_settings`, or uses it around a block. The override stacks a holder of the new values on top of the settings and sends `setting_changed` for each name, and receivers, most of them in `django/test/signals.py`, repair what Django built from the old value, most by throwing it away: the URL resolvers' caches for `ROOT_URLCONF`, the template engines for `TEMPLATES`, the translations for `LANGUAGES` ([Overriding settings](startup/overrides.md)). On a class, the override is entered in `setUpClass` and left after `tearDownClass`, so it covers every test of the class, and the class's own set-up once that has called its parent's ([Settings for one test: `override_settings` and `TestContextDecorator`](testing/test-decorators.md)).

Most of what the run changed in the process, it puts back. `teardown_test_environment` restores `ALLOWED_HOSTS`, `settings.DEBUG`, the mail setting it replaced and the template renderer, and deletes the outbox (`django/test/utils.py:teardown_test_environment`). It does so by assignment, which sends no `setting_changed`, so what was built from the test's values stays as it was built: a template engine that took its debugging from `settings.DEBUG` during the run keeps it. The active translation it turned off is not turned on again. The test databases are destroyed, unless `--keepdb` asked for them to be kept, and each alias whose creation made one gets its `"NAME"` back.

## Where it meets the rest of Django

The test command is a management command like any other, found and run as [Management commands](commands.md) describes, and other commands are called on its way: migrate to build each test database, check for the system checks, flush to empty the tables after each test of a `TransactionTestCase`, loaddata for a class's fixtures ([The commands Django ships](commands/builtin.md), [Fixtures: dumpdata and loaddata](services/fixtures.md)). The test databases themselves are the database backends' work ([Test databases: `BaseDatabaseCreation`](schema/test-databases.md)), and a `TestCase`'s blocks are ordinary atomic blocks, marked so that a durable block the code under test opens directly inside one is let through ([Transactions: autocommit, `atomic` and savepoints](connections/atomic.md)). The client sends its requests through a handler ([Handlers and middleware](handlers.md)), its requests and responses are those [Requests and responses](http.md) describes, and its logins call the auth application's `login` on a request of the client's own, after `authenticate` unless forced ([Authentication, sessions and messages](auth.md), [Sessions and logins in the test client: `ClientMixin.login` and `force_login`](testing/client-login.md)). Mail sent during a test is kept by the local-memory backend ([Sending email: `mailers` and the email backends](services/mailers.md)). The development server with fixtures, testserver, is in [The development server](commands/runserver.md), and the live server whose static files come from the static files application's finders, `StaticLiveServerTestCase`, is that application's ([Serving static files: `StaticFilesHandler` and the development server](contrib/serving-static.md)).
