"""The habits of the section "What changed in the test framework", release by release: the query
string a test factory is given in its constructor, `AsyncClient` following a redirect,
`force_login` with a backend that answers only permissions, a query from a thread a
`SimpleTestCase` starts, `assertContains` twice on one streaming response, the extra tests
`build_suite` is handed, the processes `--parallel auto` gets under the forkserver start method,
`django.test.selenium`, and what `create_test_db` serializes with and without its serialize
argument. A habit that runs a test case runs it in a suite and a runner of its own, whose output
is kept from the recording, and its line is what the test came to. Windows, where the recording
is made, has no forkserver start method: multiprocessing.get_start_method(), which is all that
get_max_test_processes reads of it, is made to answer "forkserver". Run by recordings/changes.py
under each release; _run.py says how a habit is written.
"""
from _run import configure, habit, main, tables

configure()
tables()


def outcome(case):
    """Run the tests of one test case class in a suite of its own, with a runner of its own whose
    report goes nowhere: "the test passes", or the class and the message of what ended it."""
    import io
    import unittest

    class Kept(unittest.TextTestResult):
        ended = None

        def addFailure(self, test, err):
            super().addFailure(test, err)
            self.ended = err[1]

        def addError(self, test, err):
            super().addError(test, err)
            self.ended = err[1]

    runner = unittest.TextTestRunner(stream=io.StringIO(), resultclass=Kept, verbosity=0, warnings="always")
    result = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    if result.ended is None:
        return "the test passes"
    return f"{type(result.ended).__name__}: {result.ended}"


def urls(name, *patterns):
    """A URLconf made in memory, for override_settings(ROOT_URLCONF=name)."""
    import sys
    import types

    module = types.ModuleType(name)
    module.urlpatterns = list(patterns)
    sys.modules[name] = module
    return name


# The clients.


@habit('RequestFactory(query_params={"year": "2026"}).get("/entries/").GET')
def factory_query_params():
    from django.test import RequestFactory
    return repr(RequestFactory(query_params={"year": "2026"}).get("/entries/").GET)


@habit('AsyncRequestFactory(query_params={"year": "2026"}).get("/entries/").GET')
def async_factory_query_params():
    from django.test import AsyncRequestFactory
    return repr(AsyncRequestFactory(query_params={"year": "2026"}).get("/entries/").GET)


def follow(path):
    """GET path with AsyncClient(), following redirects: the status of the last response."""
    import asyncio

    from django.http import HttpResponse, HttpResponseRedirect
    from django.test import AsyncClient
    from django.test.utils import override_settings
    from django.urls import path as route

    def relative(request):
        return HttpResponseRedirect("2026/")

    def preserving(request):
        return HttpResponseRedirect("/entries/2026/", preserve_request=True)

    def year(request):
        return HttpResponse("2026")

    conf = urls(
        "journal_redirects",
        route("entries/", relative),
        route("entries/latest/", preserving),
        route("entries/2026/", year),
    )

    async def get():
        return await AsyncClient().get(path, follow=True)

    with override_settings(ROOT_URLCONF=conf, ALLOWED_HOSTS=["testserver"]):
        response = asyncio.run(get())
    return repr(response.status_code)


@habit('await AsyncClient().get("/entries/", follow=True): a redirect to the relative "2026/"')
def async_client_follows_relative():
    return follow("/entries/")


@habit('await AsyncClient().get("/entries/latest/", follow=True): a 307 redirect to "/entries/2026/"')
def async_client_follows_307():
    return follow("/entries/latest/")


def permissions_first():
    """AUTHENTICATION_BACKENDS with a backend that answers only permissions, before ModelBackend."""
    import sys
    import types

    from django.contrib.auth.backends import BaseBackend

    class PermissionsOnly(BaseBackend):
        def has_perm(self, user_obj, perm, obj=None):
            return perm == "journal.view_entry"

    module = types.ModuleType("journal_permissions")
    module.PermissionsOnly = PermissionsOnly
    sys.modules["journal_permissions"] = module
    return ["journal_permissions.PermissionsOnly", "django.contrib.auth.backends.ModelBackend"]


def ada():
    from django.contrib.auth.models import User
    return User.objects.get_or_create(username="ada")[0]


@habit("client.force_login(ada): the backend the session records, a permission-only backend listed first")
def force_login_backend():
    from django.contrib.auth import BACKEND_SESSION_KEY
    from django.test import Client
    from django.test.utils import override_settings

    with override_settings(AUTHENTICATION_BACKENDS=permissions_first()):
        client = Client()
        client.force_login(ada())
        return client.session[BACKEND_SESSION_KEY]


@habit('client.force_login(ada), then client.get("/whoami/").content: a permission-only backend listed first')
def force_login_next_request():
    from django.http import HttpResponse
    from django.test import Client
    from django.test.utils import override_settings
    from django.urls import path

    def whoami(request):
        return HttpResponse(str(request.user))

    conf = urls("journal_whoami", path("whoami/", whoami))
    middleware = [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
    ]
    with override_settings(
        AUTHENTICATION_BACKENDS=permissions_first(),
        ROOT_URLCONF=conf,
        MIDDLEWARE=middleware,
        ALLOWED_HOSTS=["testserver"],
    ):
        client = Client()
        client.force_login(ada())
        return repr(client.get("/whoami/").content)


# The test cases.


@habit("Entry.objects.count() in a thread that a SimpleTestCase's test starts")
def query_in_a_thread():
    import threading

    from django.test import SimpleTestCase
    from journal.models import Entry

    raised = []

    def count():
        try:
            Entry.objects.count()
        except Exception as error:  # noqa: BLE001 - the test raises it in its own thread
            raised.append(error)

    class InAThread(SimpleTestCase):
        def test_count(self):
            thread = threading.Thread(target=count)
            thread.start()
            thread.join()
            if raised:
                raise raised[0]

    ended = outcome(InAThread)
    return ended.split(". ")[0] + "." if ". " in ended else ended  # the message's first sentence


@habit('assertContains(response, "a year"), called twice on StreamingHttpResponse([b"2026: ", b"a year"])')
def assert_contains_twice_on_streaming():
    from django.http import StreamingHttpResponse
    from django.test import SimpleTestCase

    class Twice(SimpleTestCase):
        def test_twice(self):
            response = StreamingHttpResponse([b"2026: ", b"a year"])
            self.assertContains(response, "a year")
            self.assertContains(response, "a year")

    return outcome(Twice)


# The runner.


@habit('DiscoverRunner(verbosity=0).build_suite(["journal_suite"], extra_tests=[extra]): the tests in the suite')
def build_suite_extra_tests():
    import sys
    import types
    import unittest

    from django.test.runner import DiscoverRunner

    class Listed(unittest.TestCase):
        def test_listed(self):
            pass

    class Extra(unittest.TestCase):
        def test_extra(self):
            pass

    module = types.ModuleType("journal_suite")
    Listed.__module__ = Extra.__module__ = "journal_suite"
    Listed.__qualname__, Extra.__qualname__ = "Listed", "Extra"
    module.Listed = Listed
    sys.modules["journal_suite"] = module
    suite = DiscoverRunner(verbosity=0).build_suite(["journal_suite"], extra_tests=[Extra("test_extra")])
    return ", ".join(test.id() for test in suite)


@habit('get_max_test_processes() with DJANGO_TEST_PROCESSES=4, multiprocessing.get_start_method() answering "forkserver"')
def processes_under_forkserver():
    # Windows has no forkserver start method. get_max_test_processes learns the start method from
    # multiprocessing.get_start_method() and from nothing else, so that call is made to answer it.
    import multiprocessing
    import os
    from unittest import mock

    from django.test.runner import get_max_test_processes

    with mock.patch.object(multiprocessing, "get_start_method", return_value="forkserver"), \
            mock.patch.dict(os.environ, {"DJANGO_TEST_PROCESSES": "4"}):
        return repr(get_max_test_processes())


@habit("from django.test.selenium import SeleniumTestCase")
def selenium_module():
    from django.test.selenium import SeleniumTestCase
    return SeleniumTestCase.__module__


# The test databases. These come last: each makes the test database of the default alias, and
# puts the alias's settings back after it.


def serialized(**arguments):
    """create_test_db with these arguments: whether it kept the rows a serialized_rollback
    restores, on the connection."""
    from django.db import connection

    old_name = connection.settings_dict["NAME"]
    try:
        connection.creation.create_test_db(verbosity=0, **arguments)
        kept = hasattr(connection, "_test_serialized_contents")
    finally:
        if hasattr(connection, "_test_serialized_contents"):
            del connection._test_serialized_contents
        connection.creation.destroy_test_db(old_name, verbosity=0)
    return "the rows serialized" if kept else "nothing serialized"


@habit("connection.creation.create_test_db(verbosity=0): the rows kept for serialized_rollback")
def create_test_db_default():
    return serialized()


@habit("connection.creation.create_test_db(verbosity=0, serialize=True): the rows kept for serialized_rollback")
def create_test_db_serialize():
    return serialized(serialize=True)


main()
