---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the test framework

What changed in `django.test` from 5.0 to this commit: the test clients' query_params, coroutine methods and redirects, the backend `ClientMixin.force_login` chooses, a `TransactionTestCase`'s first set-up, the guard on connections in threads, the assertions, and the runner's `--durations`, forkserver and serialized databases.

The framework kept the shape that [The test framework](../testing.md) describes; what changed is in its parts.

## The test clients

Since 5.1 the methods of `RequestFactory`, `AsyncRequestFactory`, `Client` and `AsyncClient` take query_params, a mapping that becomes the query string of any method's request: `RequestFactory.generic` url-encodes it as the environ's `"QUERY_STRING"`, `AsyncRequestFactory.generic` as the scope's `"query_string"` (`django/test/client.py:RequestFactory.generic`, `django/test/client.py:AsyncRequestFactory.generic`). On `RequestFactory.get` and `RequestFactory.head`, whose data is the query too, giving both is a `ValueError` (`django/test/client.py:RequestFactory.get`). Given to the constructor of `RequestFactory` or `Client`, the mapping reaches no request that `generic` builds, since it sets `"QUERY_STRING"` over the default ([Building a request: `RequestFactory`](../testing/request-factory.md)).

`ClientMixin` declares `ClientMixin.asession`, `ClientMixin.alogin`, `ClientMixin.aforce_login` and `ClientMixin.alogout` (5.0), coroutine twins of the session property and of the login and logout methods, on both clients (`django/test/client.py:ClientMixin.alogin`; [Sessions and logins in the test client: `ClientMixin.login` and `force_login`](../testing/client-login.md#the-asynchronous-methods)). `AsyncClient`'s methods have taken `follow=True` since 5.0, but `ClientMixin._follow_redirect`, which it shares with `Client`, reads the request's WSGI keys for a relative Location and for a 307 or 308, and a scope has none: in a run, `AsyncClient` raised `KeyError` for both, which `Client` followed (`django/test/client.py:ClientMixin._follow_redirect`; [The test client: `Client` and `ClientHandler`](../testing/client.md#asyncclient-and-asyncclienthandler)).

`ClientMixin.force_login`, given no backend, takes the first entry of `AUTHENTICATION_BACKENDS` whose class overrides `BaseBackend.get_user` or `BaseBackend.aget_user`, by which later requests find the user; before 6.2 a backend that answers only permissions could be chosen (`django/test/client.py:ClientMixin._get_backend`).

## The test cases

Since 5.2 `TransactionTestCase.setUpClass`, for a class that is not a `TestCase`, runs the first test's `_pre_setup`, a class method, and sets `SimpleTestCase._pre_setup_ran_eagerly` so that `SimpleTestCase._setup_and_call` does not run it again (`django/test/testcases.py:TransactionTestCase.setUpClass`). A class's `TransactionTestCase.fixtures` and the rows of `TransactionTestCase.serialized_rollback` are thus in the database during its own `setUpClass`, once that has called the parent's ([Emptying the tables after each test: `TransactionTestCase`](../testing/transaction-test-case.md#the-first-tests-set-up-runs-in-setupclass)).

Since 5.2 `django/test/testcases.py` sets `__unittest = True`, the mark by which `unittest` leaves a module's frames out of a reported traceback, so a failing assertion of Django's is reported at the test's own line and, the release notes add, `--pdb` enters the test method (`django/test/testcases.py:__unittest`; [One test, in order: `SimpleTestCase`](../testing/simple-test-case.md)).

The guard that refuses a `SimpleTestCase` the databases it does not name replaces connection methods in the thread that sets the class up. Since 5.1, "to enforce test isolation" in the release notes' words, it also replaces `BaseDatabaseWrapper.ensure_connection` for the class, refusing a new connection to such an alias in any thread: in a run, a query in a thread the test started raised `DatabaseOperationForbidden` for "threaded connections" (`django/test/testcases.py:SimpleTestCase.ensure_connection_patch_method`; [Which databases a test uses: `databases`](../testing/test-databases.md)).

The undocumented module django.test.selenium went in 6.2; importing it is a `ModuleNotFoundError`.

## The assertions

| assertion | what changed | release | where now |
|---|---|---|---|
| `SimpleTestCase.assertContains`, `SimpleTestCase.assertNotContains` | the message ends with the body, as bytes | 5.1 | `django/test/testcases.py:SimpleTestCase.assertContains` |
| the same, on a streaming response | can be called again: the body read is put back as `StreamingHttpResponse.streaming_content` | 6.1 | `django/test/testcases.py:SimpleTestCase._assert_contains` |
| `SimpleTestCase.assertInHTML` | the message ends with the haystack; `": "` follows a msg_prefix | 5.1 | `django/test/testcases.py:SimpleTestCase.assertInHTML` |
| `SimpleTestCase.assertNotInHTML` | new: `assertInHTML` with `count=0` | 5.1 | `django/test/testcases.py:SimpleTestCase.assertNotInHTML` |
| `SimpleTestCase.assertURLEqual` | `": "` follows a msg_prefix | 5.1 | `django/test/testcases.py:SimpleTestCase.assertURLEqual` |
| `SimpleTestCase.assertFormError`, `SimpleTestCase.assertFormSetError` | take a form or a formset, not a response and a name; `errors=None`, once no errors, is now `[None]` | 5.0 | `django/test/testcases.py:SimpleTestCase.assertFormError` |
| assertFormsetError | removed for `assertFormSetError` | 5.1 | `django/test/testcases.py:SimpleTestCase.assertFormSetError` |
| assertQuerysetEqual | removed for `TransactionTestCase.assertQuerySetEqual` | 5.1 | `django/test/testcases.py:TransactionTestCase.assertQuerySetEqual` |

*The changes to the assertions of Django's test case classes.*

## The runner and the test databases

`--durations` (5.0) is added by `DiscoverRunner.add_arguments` and passed to `unittest.TextTestRunner`, which reports the slowest tests (`django/test/runner.py:DiscoverRunner.get_test_runner_kwargs`; [The runner: the test command and `DiscoverRunner`](../testing/runner.md)). The release notes gave it for Python 3.12 and later, now the oldest Python Django supports (`pyproject.toml`).

Since 6.0 a parallel run works under the forkserver start method, which `_init_worker` treats as spawn: each worker starts without the parent's state, sets Django and the test environment up again and takes the parent's database settings (`django/test/runner.py:_init_worker`; [Running in parallel: `ParallelTestSuite`](../testing/parallel.md)). Since 6.1 `setup_test_environment` gives each alias of a project's `MAILERS` the local-memory backend, and sets `EMAIL_BACKEND` only without it (`django/test/utils.py:setup_test_environment`; [What changed in mail and tasks](mail-and-tasks.md)).

The extra_tests argument of `DiscoverRunner.build_suite` and `DiscoverRunner.run_tests` went in 5.0, but both still take `**kwargs` and use none, so the argument is accepted and ignored (`django/test/runner.py:DiscoverRunner.build_suite`).

`setup_databases` serializes the rows a class with `serialized_rollback` gets back after every test database is made, which its comment says is for mirrors and routing, and, called by the runner, only for the aliases such classes use (`django/test/utils.py:setup_databases`; [Test databases: `BaseDatabaseCreation`](../backends/creation.md)). The serialize argument of `BaseDatabaseCreation.create_test_db`, which when true serializes one database as it is made, warns with `RemovedInDjango2028Warning` whenever it is not None (6.0); the release notes name `BaseDatabaseCreation.serialize_db_to_string` in its place, the warning's message a DatabaseCreation.serialize_test_db that no class defines (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`; [What still warns: the deprecations and the releases that end them](deprecations.md)). The SERIALIZE test setting went in 5.0, deprecated in 4.0 as inferable from the tests' `serialized_rollback` (`docs/releases/4.0.txt`); nothing reads the key now (`django/db/utils.py:ConnectionHandler.configure_settings`).
