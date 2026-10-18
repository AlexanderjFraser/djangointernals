---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the test framework

The backend `ClientMixin.force_login` records; `SimpleTestCase.assertContains` on a streaming response; `BaseDatabaseCreation.create_test_db`'s `serialize=`; parallel runs under forkserver; and the test clients' `query_params=` and coroutine methods.

Until 6.2 `force_login` could record a backend that answers only permissions, and the client seemed logged out. Until 6.1 `assertContains` used up a streaming response. 6.0 deprecated `create_test_db`'s `serialize=`: the runner's `setup_databases` already serialized the rows a `TransactionTestCase` restores. 6.0 also let parallel workers start by forkserver. The 5.x releases gave the clients coroutine methods and `query_params=`. Since 5.1 a `SimpleTestCase` refuses a new connection to a database it does not name in every thread, not only its own.

## The test clients

Since 6.2 `ClientMixin.force_login` no longer leaves the client logged out when a permission-only `BaseBackend` subclass is listed first. Given no backend, it records the one `ClientMixin._get_backend` chooses, through which the next request finds the user. Before 6.2 that was the first entry of `AUTHENTICATION_BACKENDS` with a get_user method, which `BaseBackend` gives every subclass, returning `None`. Since 6.2 it is the first whose class overrides `BaseBackend.get_user` or `BaseBackend.aget_user` (`django/test/client.py:ClientMixin._get_backend`, `docs/releases/6.2.txt`).

A `BaseBackend` subclass defining only `has_perm` is listed before `ModelBackend`, and a view at "/whoami/" returns `str(request.user)`. Under the old choice the view sees the anonymous user:

```text recording=changes
client.force_login(ada), then client.get("/whoami/").content: a permission-only backend listed first
    5.2.17       b'AnonymousUser'
    6.0.8        b'AnonymousUser'
    6.1.1        b'AnonymousUser'
    this commit  b'ada'
```

Since 5.1 the request methods of `RequestFactory`, `AsyncRequestFactory`, `Client` and `AsyncClient` take `query_params=`, a mapping made the query string (`django/test/client.py:RequestFactory.generic`). Under all four releases, `query_params=` given to a constructor is lost by the request methods of `RequestFactory`, whose `generic` sets the query string over the default, and of `Client`, built on it. `AsyncRequestFactory`'s keep it, and so do `AsyncClient`'s, built on it ([Building a request: `RequestFactory`](../testing/request-factory.md)).

> **Trap.** Since 5.0 `AsyncClient`'s methods take `follow=True`, but `ClientMixin._follow_redirect`, which it shares with `Client`, reads two keys of a WSGI environ that its requests lack. Under all four releases a relative `"Location"` raises `KeyError: 'PATH_INFO'`, and any other 307 or 308 raises `KeyError: 'REQUEST_METHOD'` (`django/test/client.py:ClientMixin._follow_redirect`).

## The test cases

Since 6.1 `SimpleTestCase.assertContains` and `SimpleTestCase.assertNotContains` can be called more than once on the same streaming response. A streaming response can be read once. The two share `SimpleTestCase._assert_contains`, which now sets `StreamingHttpResponse.streaming_content` again from the bytes it read (`django/test/testcases.py:SimpleTestCase._assert_contains`; [Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`](../testing/response-assertions.md)). Before 6.1 the first call read the stream to its end, and a second call on the same text searched what was left, an empty body:

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

Since 5.1 a database that `SimpleTestCase.databases` does not name is refused a new connection in every thread, not only in the one that sets the class up. A `SimpleTestCase` replaces methods of that thread's connection to such a database. Each thread has connections of its own. Since 5.1 it also replaces `BaseDatabaseWrapper.ensure_connection` while the class runs, "to enforce test isolation", the notes say (`docs/releases/5.1.txt`). Under all four releases a query to such a database in a thread a test started raises `DatabaseOperationForbidden` for "threaded connections" (`django/test/testcases.py:SimpleTestCase.ensure_connection_patch_method`; [Which databases a test uses: `databases`](../testing/test-databases.md)).

Since 5.2 the fixtures and serialized rows of a `TransactionTestCase` that is not a `TestCase` are there in its own `setUpClass`, once it has called the parent's (`django/test/testcases.py:TransactionTestCase.setUpClass`; [Emptying the tables after each test: `TransactionTestCase`](../testing/transaction-test-case.md)).

## The runner

Since 6.0 the parallel runner supports the forkserver start method, the default on Linux since Python 3.14. A worker started by spawn has no copy of its parent's memory: `_init_worker` sets Django and the test environment up again, and takes the parent's database settings. Under forkserver it now does the same (`django/test/runner.py:_init_worker`; [Running in parallel: `ParallelTestSuite`](../testing/parallel.md)). Before 6.0 `get_max_test_processes`, which `--parallel auto` asks, answered 1 under forkserver (`django/test/runner.py:get_max_test_processes`). So on Linux under Python 3.14, `--parallel auto` under 5.2.17 runs one process.

5.0 removed the argument `extra_tests=` of `DiscoverRunner.build_suite` and `DiscoverRunner.run_tests`, and their `**kwargs` take it and ignore it. Under all four releases a test given in it is left out of the suite without a word (`django/test/runner.py:DiscoverRunner.build_suite`).

Since 6.1 a project may name its email backends by alias in the setting `MAILERS`. `setup_test_environment` gives each alias the local-memory backend, and sets `EMAIL_BACKEND` only where `MAILERS` is not defined (`django/test/utils.py:setup_test_environment`; [What changed in mail and tasks](mail-and-tasks.md)).

## The test databases

6.0 deprecated the argument `serialize=` of `BaseDatabaseCreation.create_test_db`, to go in Django 2028. It also changed the argument's default from true to `None`, which serializes nothing. A `TransactionTestCase` with `TransactionTestCase.serialized_rollback` gets back before each test the rows migrations wrote. The runner's `setup_databases` serializes them once every test database is made (`django/test/utils.py:setup_databases`; [Test databases: `BaseDatabaseCreation`](../backends/creation.md)). A call without the argument shows the old default under 5.2.17 and the new under 6.0.8 and later:

```text recording=changes
connection.creation.create_test_db(verbosity=0): the rows kept for serialized_rollback
    5.2.17       the rows serialized
    6.0.8        nothing serialized
    6.1.1        nothing serialized
    this commit  nothing serialized
```

> **Trap.** Nothing warns of the new default. A project's own runner that relied on the old one now serializes nothing, and `TransactionTestCase._fixture_setup` restores no rows (`django/test/testcases.py:TransactionTestCase._fixture_setup`).

Since 6.0 `create_test_db` warns when it is given `serialize=` other than `None`. A true value still serializes. The warning's message points to DatabaseCreation.serialize_test_db, which no class defines. The notes name `BaseDatabaseCreation.serialize_db_to_string` (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`; [What still warns: the deprecations and the releases that end them](deprecations.md)).

## The smaller changes

The rest, by name:

| what | change | where |
|---|---|---|
| the clients' coroutine methods | New in 5.0: `ClientMixin.asession`, `ClientMixin.alogin`, `ClientMixin.aforce_login` and `ClientMixin.alogout` | `django/test/client.py:ClientMixin.alogin` |
| `SimpleTestCase.assertContains`, `SimpleTestCase.assertNotContains` | Since 5.1, a failure on the text ends its message with the body, as bytes | `django/test/testcases.py:SimpleTestCase.assertContains` |
| `SimpleTestCase.assertInHTML` | Since 5.1, a failed search's message ends with the HTML searched, and `": "` follows a `msg_prefix=` | `django/test/testcases.py:SimpleTestCase.assertInHTML` |
| `SimpleTestCase.assertURLEqual` | Since 5.1, `": "` follows a `msg_prefix=` | `django/test/testcases.py:SimpleTestCase.assertURLEqual` |
| `SimpleTestCase.assertNotInHTML` | New in 5.1: `assertInHTML` with `count=0` | `django/test/testcases.py:SimpleTestCase.assertNotInHTML` |
| `SimpleTestCase.assertFormError`, `SimpleTestCase.assertFormSetError` | Gone in 5.0: a response and a form's name, given in place of the form or the formset | `django/test/testcases.py:SimpleTestCase._assert_form_error` |
| `errors=None` in a form assertion | Since 5.0, the one error `None`, no longer no errors; no errors is `errors=[]` | `django/test/testcases.py:to_list` |
| assertFormsetError, assertQuerysetEqual | Gone in 5.1: the old names of `assertFormSetError` and `TransactionTestCase.assertQuerySetEqual` | `django/test/testcases.py` |
| a failure's traceback | Since 5.2, without the frames of `django.test.testcases`, which sets `__unittest = True`: a failing assertion of Django's is reported at the test's line and, the notes say, `--pdb` enters the test | `django/test/testcases.py:__unittest` |
| the option `--durations` | New in 5.0: the slowest tests, reported by `unittest.TextTestRunner` | `django/test/runner.py:DiscoverRunner.get_test_runner_kwargs` |
| django.test.selenium | Gone in 6.2: the undocumented module | `django/test/` |
