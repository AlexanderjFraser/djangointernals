"""The habits of the section "What changed in authentication, sessions and messages", release
by release: the iterations a password is stored with again at a check, and what that does to
the user's other sessions; a removed hasher still named in PASSWORD_HASHERS; what the
asynchronous functions ask of a backend; a subclass of RemoteUserMiddleware under ASGI,
overriding process_request or reading a header of its own; login given no user, and the
request's auser after a login; an empty session's truth, the cached database store when its
cache fails, the permissions of a renamed model and Permission.user_perm_str;
LoginRequiredMiddleware and a view's LoginRequiredMixin; and the old uses removed since 5.0.
Run by recordings/changes.py under each release; _run.py says how a habit is written.

Every habit runs at the release's default settings but for what its title names, over one
database in memory, each making users of its own names. PASSWORD_HASHERS is the release's
default, so a password is hashed at the release's iterations; only the aauthenticate habit
for olga hashes with MD5PasswordHasher, where the hash is not its question.

The habits under ASGI serve one GET through ASGIHandler with startproject's MIDDLEWARE and the
subclass placed in it. A middleware that can run either way, as RemoteUserMiddleware can, takes
the mode of the layer inside it (BaseHandler.load_middleware), and at this commit every one of
startproject's middleware is synchronous only: where the subclass stands decides whether it
runs as a coroutine, and each title says where it stands.
"""
import sys
import types

from _run import configure, habit, main, tables

configure()
tables()

# The project's own code a habit names by a dotted path (a backend, a middleware, a cache, a
# URLconf) is put in this module, made in memory, as each habit defines it.
PROJECT = types.ModuleType("journal_auth")
sys.modules["journal_auth"] = PROJECT

FAST = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # where the hash is not the question
PASSWORD = "Beagle-1831"


def stored_by_5_0(password):
    """A password encoded as 5.0 stored it: PBKDF2 with SHA-256 and 720,000 iterations."""
    from django.contrib.auth.hashers import PBKDF2PasswordHasher

    hasher = PBKDF2PasswordHasher()
    return hasher.encode(password, hasher.salt(), iterations=720_000)


def request_with_session(path="/entries/2026/"):
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory

    request = RequestFactory().get(path)
    request.session = SessionStore()
    return request


# The hashers


@habit('user.check_password("Beagle-1831"), the password stored at 5.0\'s 720,000 iterations: '
       'what is stored after')
def pbkdf2_stored_again():
    from django.contrib.auth.models import User

    user = User.objects.create(username="tomas", password=stored_by_5_0(PASSWORD))
    assert user.check_password(PASSWORD)
    algorithm, iterations, _ = User.objects.get(pk=user.pk).password.split("$", 2)
    return f"{algorithm}, {int(iterations):,} iterations"


@habit("get_user(request) for a session logged in before user.check_password stored the password again")
def session_after_stored_again():
    from django.contrib.auth import get_user, login
    from django.contrib.auth.models import User
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory

    user = User.objects.create(username="ines", password=stored_by_5_0(PASSWORD))
    elsewhere = request_with_session()
    login(elsewhere, user)
    elsewhere.session.save()
    assert user.check_password(PASSWORD)
    later = RequestFactory().get("/entries/2026/")
    later.session = SessionStore(elsewhere.session.session_key)
    return str(get_user(later))


@habit('check_password("Beagle-1831", stored), stored by SHA1PasswordHasher, PASSWORD_HASHERS naming it')
def removed_sha1_hasher():
    import hashlib

    from django.conf import global_settings
    from django.contrib.auth.hashers import check_password
    from django.test.utils import override_settings

    # PASSWORD_HASHERS as a project that stored such strings had it (its default has not named
    # the hasher since 1.10): the default, and the hasher of the old strings after it.
    hashers = [*global_settings.PASSWORD_HASHERS, "django.contrib.auth.hashers.SHA1PasswordHasher"]
    salt = "journal"
    stored = "sha1$%s$%s" % (salt, hashlib.sha1((salt + PASSWORD).encode()).hexdigest())
    with override_settings(PASSWORD_HASHERS=hashers):
        return repr(check_password(PASSWORD, stored))


# The asynchronous functions and the backends


@habit('aauthenticate(username="olga", password="Beagle-1831"), the backend a ModelBackend whose '
       'authenticate alone refuses olga')
def aauthenticate_passes_over_an_override():
    from asgiref.sync import async_to_sync
    from django.contrib.auth import aauthenticate
    from django.contrib.auth.backends import ModelBackend
    from django.contrib.auth.hashers import make_password
    from django.contrib.auth.models import User
    from django.test.utils import override_settings

    class RefusingBackend(ModelBackend):
        def authenticate(self, request, username=None, password=None, **kwargs):
            if username == "olga":
                return None
            return super().authenticate(request, username, password, **kwargs)

    PROJECT.RefusingBackend = RefusingBackend
    with override_settings(PASSWORD_HASHERS=FAST, AUTHENTICATION_BACKENDS=["journal_auth.RefusingBackend"]):
        User.objects.create(username="olga", password=make_password(PASSWORD))
        return repr(async_to_sync(aauthenticate)(username="olga", password=PASSWORD))


class PlainBackend:
    """A backend on no base class of Django's, written before the asynchronous functions:
    it knows nora, and its has_perm says yes to every permission."""

    def authenticate(self, request, username=None, password=None):
        from django.contrib.auth.models import User

        return User.objects.filter(username=username).first() if username == "nora" else None

    def get_user(self, user_id):
        from django.contrib.auth.models import User

        return User.objects.filter(pk=user_id).first()

    def has_perm(self, user_obj, perm, obj=None):
        return True


PROJECT.PlainBackend = PlainBackend


@habit('aauthenticate(username="nora", password="x"), the one backend a class on no base of Django\'s')
def aauthenticate_with_a_plain_backend():
    from asgiref.sync import async_to_sync
    from django.contrib.auth import aauthenticate
    from django.test.utils import override_settings

    with override_settings(AUTHENTICATION_BACKENDS=["journal_auth.PlainBackend"]):
        return repr(async_to_sync(aauthenticate)(username="nora", password="x"))


@habit('await nora.ahas_perm("journal.change_entry"), the one backend that class, whose has_perm says yes')
def ahas_perm_with_a_plain_backend():
    from asgiref.sync import async_to_sync
    from django.contrib.auth.models import User
    from django.test.utils import override_settings

    with override_settings(AUTHENTICATION_BACKENDS=["journal_auth.PlainBackend"]):
        nora = User(username="nora")
        assert nora.has_perm("journal.change_entry")
        return repr(async_to_sync(nora.ahas_perm)("journal.change_entry"))


# RemoteUserMiddleware under ASGI

STARTPROJECT_MIDDLEWARE = [  # MIDDLEWARE as startproject writes it, the same in every release recorded
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
CALLED = []


def remote_user_middleware():
    """Two subclasses of RemoteUserMiddleware a project of 5.x might have written: one that
    overrides process_request alone, noting each call, and one that reads a header of its own."""
    from django.contrib.auth.middleware import RemoteUserMiddleware

    class NotingRemoteUserMiddleware(RemoteUserMiddleware):
        def process_request(self, request):
            CALLED.append(request.path)
            super().process_request(request)

    class AuthUserMiddleware(RemoteUserMiddleware):
        header = "HTTP_AUTHUSER"

    PROJECT.NotingRemoteUserMiddleware = NotingRemoteUserMiddleware
    PROJECT.AuthUserMiddleware = AuthUserMiddleware


def served_under_asgi(middleware, headers):
    """One GET under ASGI through the given MIDDLEWARE, with RemoteUserBackend the one backend,
    to a synchronous view that answers with str(request.user)."""
    from asgiref.sync import async_to_sync
    from django.core.handlers.asgi import ASGIHandler
    from django.http import HttpResponse
    from django.test.utils import override_settings
    from django.urls import path

    def whoami(request):
        return HttpResponse(str(request.user))

    urls = types.ModuleType("journal_auth_urls")
    urls.urlpatterns = [path("whoami/", whoami)]
    sys.modules["journal_auth_urls"] = urls
    scope = {"type": "http", "method": "GET", "path": "/whoami/", "query_string": b"",
             "headers": [(b"host", b"journal.example"), *headers]}
    sent = []

    async def serve(handler):
        import asyncio

        received = []

        async def receive():
            if not received:
                received.append(True)
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()  # the client never disconnects

        async def send(message):
            sent.append(message)

        await handler(scope, receive, send)

    with override_settings(
        ROOT_URLCONF="journal_auth_urls",
        MIDDLEWARE=middleware,
        ALLOWED_HOSTS=["journal.example"],
        AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.RemoteUserBackend"],
    ):
        async_to_sync(serve)(ASGIHandler())
    assert sent[0]["status"] == 200, sent[0]
    return b"".join(message.get("body", b"") for message in sent[1:]).decode()


def after_authentication(name):
    """startproject's MIDDLEWARE with a middleware of journal_auth directly after
    AuthenticationMiddleware, where the documentation puts RemoteUserMiddleware."""
    middleware = list(STARTPROJECT_MIDDLEWARE)
    at = middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1
    middleware.insert(at, f"journal_auth.{name}")
    return middleware


@habit("A subclass of RemoteUserMiddleware that overrides process_request alone, after "
       "AuthenticationMiddleware in startproject's MIDDLEWARE, under ASGI: is the override called")
def remote_user_override_after_authentication():
    remote_user_middleware()
    CALLED.clear()
    served_under_asgi(after_authentication("NotingRemoteUserMiddleware"), [(b"remote-user", b"ingrid")])
    return "the override is called" if CALLED else "the override is not called"


@habit("The same subclass last in MIDDLEWARE, under ASGI: is the override called")
def remote_user_override_last():
    remote_user_middleware()
    CALLED.clear()
    middleware = STARTPROJECT_MIDDLEWARE + ["journal_auth.NotingRemoteUserMiddleware"]
    served_under_asgi(middleware, [(b"remote-user", b"ingrid")])
    return "the override is called" if CALLED else "the override is not called"


@habit('header = "HTTP_AUTHUSER" on a subclass of RemoteUserMiddleware last in MIDDLEWARE, under ASGI, '
       'sent "authuser: rafa": the request\'s user')
def remote_user_custom_header():
    # Last, so that the layer inside it is the handler's coroutine under every release and the
    # subclass runs aprocess_request: after AuthenticationMiddleware, at this commit, it would
    # run process_request, which has read the header as written in every release.
    remote_user_middleware()
    middleware = STARTPROJECT_MIDDLEWARE + ["journal_auth.AuthUserMiddleware"]
    return served_under_asgi(middleware, [(b"authuser", b"rafa")])


# login, and the request's user


@habit("login(request, None), request.user being piet: the user the session is given")
def login_given_none():
    from django.contrib.auth import SESSION_KEY, login
    from django.contrib.auth.models import User

    request = request_with_session()
    request.user = User.objects.create(username="piet")
    login(request, None)
    return User.objects.get(pk=request.session[SESSION_KEY]).get_username()


@habit("await request.auser() after login(request, ada), when it was awaited before the login")
def auser_after_login():
    from asgiref.sync import async_to_sync
    from django.contrib.auth import login
    from django.contrib.auth.middleware import AuthenticationMiddleware
    from django.contrib.auth.models import User

    request = request_with_session()
    AuthenticationMiddleware(lambda request: None).process_request(request)
    assert not async_to_sync(request.auser)().is_authenticated
    login(request, User.objects.create(username="ada"))
    return str(async_to_sync(request.auser)())


# Sessions


@habit("bool(SessionStore()): a new session, with no key and no data")
def empty_session_truth():
    from django.contrib.sessions.backends.db import SessionStore
    return repr(bool(SessionStore()))


@habit("SessionStore.delete() of the cached database store, when the cache raises on a delete")
def cached_db_delete_when_the_cache_fails():
    import logging

    from django.contrib.sessions.backends.cached_db import SessionStore
    from django.core.cache.backends.locmem import LocMemCache
    from django.test.utils import override_settings

    class FailingDeleteCache(LocMemCache):
        def delete(self, key, version=None):
            raise ConnectionError("the cache is unreachable")

    PROJECT.FailingDeleteCache = FailingDeleteCache
    records = []

    class Keep(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("django.contrib.sessions")
    keep = Keep()
    with override_settings(CACHES={"default": {"BACKEND": "journal_auth.FailingDeleteCache"}}):
        store = SessionStore()
        store["year"] = 2026
        store.save()
        logger.addHandler(keep)
        try:
            store.delete()
        finally:
            logger.removeHandler(keep)
    return " and ".join(f'the error logged to "{record.name}", at {record.levelname}' for record in records) or "nothing logged"


# Permissions


@habit('migrate: RenameModel("Notebook", "Ledger") in journal, then the codenames of the change '
       'permissions of Ledger')
def permissions_after_a_rename():
    import os
    import shutil
    import tempfile

    from django.contrib.auth.models import Permission
    from django.core.management import call_command
    from django.test.utils import override_settings

    migrations = {
        "__init__.py": "",
        "0001_initial.py": (
            "from django.db import migrations, models\n\n\n"
            "class Migration(migrations.Migration):\n"
            "    initial = True\n"
            "    dependencies = []\n"
            "    operations = [\n"
            "        migrations.CreateModel(\n"
            "            name=\"Notebook\",\n"
            "            fields=[(\"id\", models.AutoField(primary_key=True))],\n"
            "        ),\n"
            "    ]\n"
        ),
        "0002_rename.py": (
            "from django.db import migrations\n\n\n"
            "class Migration(migrations.Migration):\n"
            "    dependencies = [(\"journal\", \"0001_initial\")]\n"
            "    operations = [migrations.RenameModel(\"Notebook\", \"Ledger\")]\n"
        ),
    }
    directory = tempfile.mkdtemp()
    package = os.path.join(directory, "journal_auth_migrations")
    os.mkdir(package)
    for name, text in migrations.items():
        with open(os.path.join(package, name), "w", encoding="utf-8") as file:
            file.write(text)
    sys.path.insert(0, directory)
    try:
        with override_settings(MIGRATION_MODULES={"journal": "journal_auth_migrations"}):
            call_command("migrate", "journal", "0001", verbosity=0, skip_checks=True)
            call_command("migrate", "journal", "0002", verbosity=0, skip_checks=True)
    finally:
        sys.path.remove(directory)
        shutil.rmtree(directory)
    codenames = Permission.objects.filter(
        content_type__app_label="journal", content_type__model="ledger", codename__startswith="change_"
    ).values_list("codename", flat=True)
    return repr(sorted(codenames))


@habit('Permission.objects.get(codename="change_entry").user_perm_str')
def user_perm_str():
    from django.contrib.auth.models import Permission
    return repr(Permission.objects.get(codename="change_entry").user_perm_str)


# Requiring a login


@habit('LoginRequiredMiddleware, a LoginRequiredMixin view whose login_url is "/journal/login/", '
       'an anonymous GET: where it is sent')
def login_required_middleware_and_the_mixin():
    from django.contrib.auth.middleware import LoginRequiredMiddleware
    from django.contrib.auth.mixins import LoginRequiredMixin
    from django.contrib.auth.models import AnonymousUser
    from django.http import HttpResponse
    from django.test import RequestFactory
    from django.test.utils import override_settings
    from django.views.generic import View

    class EntriesView(LoginRequiredMixin, View):
        login_url = "/journal/login/"

        def get(self, request):
            return HttpResponse("entries")

    request = RequestFactory().get("/entries/2026/")
    request.user = AnonymousUser()
    with override_settings(ALLOWED_HOSTS=["testserver"]):  # RequestFactory's host
        response = LoginRequiredMiddleware(lambda request: None).process_view(request, EntriesView.as_view(), (), {})
    return response["Location"]


# The old uses removed


@habit('LogoutView.as_view()(request).status_code: a GET')
def logout_by_get():
    from django.contrib.auth.views import LogoutView
    from django.test import RequestFactory
    return repr(LogoutView.as_view()(RequestFactory().get("/accounts/logout/")).status_code)


@habit('authenticate(remote_user="ingrid"), the backend a RemoteUserBackend whose configure_user '
       'takes (request, user)')
def configure_user_without_created():
    from django.contrib.auth import authenticate
    from django.test.utils import override_settings

    # Defined in the project's module, as a project defines it, so that Python's message names
    # the method as OldRemoteUserBackend.configure_user.
    exec(
        "from django.contrib.auth.backends import RemoteUserBackend\n\n\n"
        "class OldRemoteUserBackend(RemoteUserBackend):\n"
        "    def configure_user(self, request, user):\n"
        "        return user\n",
        PROJECT.__dict__,
    )
    with override_settings(AUTHENTICATION_BACKENDS=["journal_auth.OldRemoteUserBackend"]):
        return repr(authenticate(remote_user="ingrid"))


@habit('SessionStore(), SESSION_SERIALIZER naming "django.contrib.sessions.serializers.PickleSerializer"')
def pickle_serializer():
    from django.contrib.sessions.backends.db import SessionStore
    from django.test.utils import override_settings

    with override_settings(SESSION_SERIALIZER="django.contrib.sessions.serializers.PickleSerializer"):
        SessionStore()
    return "the store is made"


@habit("User.objects.make_random_password()")
def make_random_password():
    from django.contrib.auth.models import User
    return repr(User.objects.make_random_password())


main()
