---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the test framework

The changes from Django 5.0 to this commit in `django.test` and the test databases: `ClientMixin.force_login` (6.2), `SimpleTestCase.assertContains` on a streaming response (6.1), `BaseDatabaseCreation.create_test_db`'s `serialize=` and parallel runs under forkserver (6.0); the clients' `query_params=` and coroutine methods, threads refused a connection, and the assertions (5.0 to 5.2).

Two of the newest changes mend a helper that did less than it seemed to. Until 6.2 `force_login` could record a backend that answers only permissions, and the client seemed logged out; until 6.1 `assertContains` used up a streaming response. 6.0 deprecated `create_test_db`'s `serialize=`: the runner's `setup_databases` already serialized the rows a `TransactionTestCase` restores. 6.0 also let parallel workers start by forkserver. The 5.x releases gave the clients coroutine methods and `query_params=`, and since 5.1 a `SimpleTestCase` refuses a database it does not name in every thread, not only its own.

## The test clients

Since 5.1 the request methods of `RequestFactory`, `AsyncRequestFactory`, `Client` and `AsyncClient` take `query_params=`, a mapping made the query string (`django/test/client.py:RequestFactory.generic`). Given to a constructor, it is lost by `RequestFactory`, whose `generic` sets the query string over the default: under all four releases `RequestFactory(query_params={"year": "2026"}).get("/entries/").GET` is empty, where `AsyncRequestFactory`'s keeps the year. `Client`, built on `RequestFactory`, loses it too, and `AsyncClient`, built on `AsyncRequestFactory`, keeps it ([Building a request: `RequestFactory`](../testing/request-factory.md)).

`ClientMixin.asession`, `ClientMixin.alogin`, `ClientMixin.aforce_login` and `ClientMixin.alogout` (5.0) are coroutine twins of the session and the login and logout methods (`django/test/client.py:ClientMixin.alogin`; [Sessions and logins in the test client: `ClientMixin.login` and `force_login`](../testing/client-login.md#the-asynchronous-methods)).

> **Trap.** `AsyncClient`'s methods have taken `follow=True` since 5.0, but `ClientMixin._follow_redirect`, which it shares with `Client`, reads two keys of a WSGI environ its requests lack: under all four releases a relative `"Location"` raises `KeyError: 'PATH_INFO'`, and otherwise a 307 or 308 `KeyError: 'REQUEST_METHOD'` (`django/test/client.py:ClientMixin._follow_redirect`).

`ClientMixin.force_login`, given no backend, records the one `ClientMixin._get_backend` chooses, through which the next request finds the user. Before 6.2 that was the first entry of `AUTHENTICATION_BACKENDS` with a get_user method, which `BaseBackend` gives every subclass, returning `None`; since 6.2 it is the first whose class overrides `BaseBackend.get_user` or `BaseBackend.aget_user`, so that "permission-only backends", the notes say, are passed over (`django/test/client.py:ClientMixin._get_backend`, `docs/releases/6.2.txt`). With a backend that defines only `has_perm` before `ModelBackend`, and a view at "/whoami/" returning `str(request.user)`, the old choice leaves the client logged out:

```text recording=changes
client.force_login(ada), then client.get("/whoami/").content: a permission-only backend listed first
    5.2.17       b'AnonymousUser'
    6.0.8        b'AnonymousUser'
    6.1.1        b'AnonymousUser'
    this commit  b'ada'
```

## The test cases

A streaming response can be read once. Since 6.1 `SimpleTestCase._assert_contains`, which `SimpleTestCase.assertContains` and `SimpleTestCase.assertNotContains` share, sets `StreamingHttpResponse.streaming_content` again from the bytes it read (`django/test/testcases.py:SimpleTestCase._assert_contains`). A test that asserts one text twice fails before 6.1, on the second call:

```text recording=changes
assertContains(response, "a year"), called twice on StreamingHttpResponse([b"2026: ", b"a year"])
    5.2.17
        AssertionError: False is not true : Couldn't find 'a year' in the following response
        b''
    6.0.8
        AssertionError: False is not true : Couldn't find 'a year' in the following response
        b''
    6.1.1        the test passes
    this commit  the test passes
```

The first call read the stream to its end, and the second searched what was left ([Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`](../testing/response-assertions.md)).

A `SimpleTestCase` refuses a database that `SimpleTestCase.databases` does not name by replacing methods of the connections of the thread that sets the class up, and each thread has its own. Since 5.1, "to enforce test isolation" (`docs/releases/5.1.txt`), it also replaces `BaseDatabaseWrapper.ensure_connection` while the class runs: under all four releases a query in a thread a test started raises `DatabaseOperationForbidden` for "threaded connections" (`django/test/testcases.py:SimpleTestCase.ensure_connection_patch_method`; [Which databases a test uses: `databases`](../testing/test-databases.md)).

Two changes of 5.2 alter what a test sees. `django/test/testcases.py` sets `__unittest = True`, by which `unittest` cuts the module's frames from a failure's traceback, so a failing assertion of Django's is reported at the test's line and, the notes add, `--pdb` enters the test (`django/test/testcases.py:__unittest`). And the fixtures and serialized rows of a `TransactionTestCase` that is not a `TestCase` are there in its own `setUpClass`, once it has called the parent's. `TransactionTestCase.setUpClass` runs `TransactionTestCase._pre_setup` for the first test, and marks `SimpleTestCase._pre_setup_ran_eagerly` so that the test does not run it again (`django/test/testcases.py:TransactionTestCase.setUpClass`; [Emptying the tables after each test: `TransactionTestCase`](../testing/transaction-test-case.md)).

## The runner

A worker started by spawn has no copy of its parent's memory: `_init_worker` sets Django and the test environment up again and takes the parent's database settings. Since 6.0 it does the same under forkserver, and `get_max_test_processes`, which `--parallel auto` asks, no longer answers 1 for it (`django/test/runner.py:_init_worker`, `django/test/runner.py:get_max_test_processes`; [Running in parallel: `ParallelTestSuite`](../testing/parallel.md)). Python 3.14 made forkserver the default start method on Linux, so there `--parallel auto` under 5.2.17 runs one process.

The argument `extra_tests=` of `DiscoverRunner.build_suite` and `DiscoverRunner.run_tests`, removed in 5.0, is taken by their `**kwargs` and ignored: under all four releases a test given in it is left out of the suite without a word (`django/test/runner.py:DiscoverRunner.build_suite`).

Since 6.1 a project may name its email backends by alias in the setting `MAILERS`; `setup_test_environment` gives each alias the local-memory backend, and sets `EMAIL_BACKEND` only without `MAILERS` (`django/test/utils.py:setup_test_environment`; [What changed in mail and tasks](mail-and-tasks.md)).
## The test databases

A `TransactionTestCase` with `TransactionTestCase.serialized_rollback` gets back before each test the rows migrations wrote, which the runner's `setup_databases` serializes once every test database is made (`django/test/utils.py:setup_databases`; [Test databases: `BaseDatabaseCreation`](../backends/creation.md)). 6.0 deprecated the argument `serialize=` of `BaseDatabaseCreation.create_test_db`, to go in Django 2028, and changed its default from true to `None`, which serializes nothing. A call without the argument shows the two defaults:

```text recording=changes
connection.creation.create_test_db(verbosity=0): the rows kept for serialized_rollback
    5.2.17       the rows serialized
    6.0.8        nothing serialized
    6.1.1        nothing serialized
    this commit  nothing serialized
```

> **Trap.** Nothing warns of the new default: a project's runner that relies on it serializes nothing, and `TransactionTestCase._fixture_setup` restores no rows (`django/test/testcases.py:TransactionTestCase._fixture_setup`).

Given `serialize=` other than `None`, `create_test_db` warns since 6.0, and a true value still serializes. The warning's message points to DatabaseCreation.serialize_test_db, which no class defines; the notes name `BaseDatabaseCreation.serialize_db_to_string` (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`; [What still warns: the deprecations and the releases that end them](deprecations.md)).

## The smaller changes

The rest, by name:

| what | at this commit | release | where |
|---|---|---|---|
| `SimpleTestCase.assertContains`, `SimpleTestCase.assertNotContains` | the message ends with the body, as bytes | 5.1 | `django/test/testcases.py:SimpleTestCase.assertContains` |
| `SimpleTestCase.assertInHTML`, `SimpleTestCase.assertURLEqual` | `": "` follows a `msg_prefix=`; the first's message ends with the haystack | 5.1 | `django/test/testcases.py:SimpleTestCase.assertInHTML` |
| `SimpleTestCase.assertNotInHTML` | new: `assertInHTML` with `count=0` | 5.1 | `django/test/testcases.py:SimpleTestCase.assertNotInHTML` |
| `SimpleTestCase.assertFormError`, `SimpleTestCase.assertFormSetError` | a form or a formset, not a response and a name; `errors=None`, which before 5.0 meant no errors, is the one error `None`; no errors is `errors=[]` | 5.0 | `django/test/testcases.py:SimpleTestCase._assert_form_error` |
| assertFormsetError, assertQuerysetEqual | removed for `assertFormSetError` and `TransactionTestCase.assertQuerySetEqual` | 5.1 | `django/test/testcases.py:TransactionTestCase.assertQuerySetEqual` |
| the option `--durations` | new: the slowest tests, reported by `unittest.TextTestRunner` | 5.0 | `django/test/runner.py:DiscoverRunner.get_test_runner_kwargs` |
| django.test.selenium | the undocumented module, still in 6.1.1, removed | 6.2 | `django/test/` |
