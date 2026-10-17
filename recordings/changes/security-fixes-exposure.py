"""The habits of the section "Security fixes: disclosure, spoofing and privilege", release by
release. Each habit sends what an attacker would send and asks whether it is refused: what the
page cache stores, a header spoofed under ASGI, a domain name with a newline, the log of a path
holding a control character (in a 404, and in runserver's own line), the hasher's runs for an
account whose password is unusable and for a name with no account, a password reset whose mail
fails, a file name or an archive member that leaves its directory, the umask, the admin's forged
rows and its links, and STARTTLS failing silently. Every fix came in a patch release no later
than 5.2.17, so these habits give one line under all four releases, and under the patch release
before its fix each gives another. The exception is runserver's own line, which no 5.2 release
escapes: 5.2.17 logs the escape character itself, and 6.0 escapes it. GeoDjango's two fixes are
told from the code and not run. Run by recordings/changes.py under each release; _run.py says
how a habit is written.
"""
from _run import BASE, configure, create, habit, main, tables

configure(INSTALLED_APPS=BASE["INSTALLED_APPS"] + ["django.contrib.admin"])
tables()


# What the page cache stores.

def through_the_page_cache(prepare, headers=None, cookies=None):
    """A GET for /entries/2026/ through UpdateCacheMiddleware and FetchFromCacheMiddleware, the
    two halves of the page cache, to a view whose 200 response `prepare` adjusts; then the same
    GET again, asked of FetchFromCacheMiddleware alone. Returns the first response, and whether
    the second was found in the cache."""
    from django.core.cache import cache
    from django.http import HttpResponse
    from django.middleware.cache import FetchFromCacheMiddleware, UpdateCacheMiddleware
    from django.test import RequestFactory
    from django.test.utils import override_settings

    def view(request):
        response = HttpResponse("entries")
        prepare(response)
        return response

    def get():
        factory = RequestFactory(headers=headers or {})
        for name, value in (cookies or {}).items():
            factory.cookies[name] = value
        return factory.get("/entries/2026/")

    with override_settings(ALLOWED_HOSTS=["testserver"]):
        cache.clear()
        response = UpdateCacheMiddleware(FetchFromCacheMiddleware(view))(get())
        found = FetchFromCacheMiddleware(view).process_request(get()) is not None
        cache.clear()
    return response, found


def stored(prepare, headers=None, cookies=None):
    return "stored" if through_the_page_cache(prepare, headers, cookies)[1] else "not stored"


@habit("SESSION_SAVE_EVERY_REQUEST = True behind the page cache: what answers a visitor "
       "without a session, after one with a session the view never touched")
def session_saved_every_request():
    from importlib import import_module

    from django.conf import settings
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.core.cache import cache
    from django.http import HttpResponse
    from django.middleware.cache import FetchFromCacheMiddleware, UpdateCacheMiddleware
    from django.test import RequestFactory
    from django.test.utils import override_settings

    calls = []

    def view(request):
        calls.append(request)
        return HttpResponse("entries")

    with override_settings(
        ALLOWED_HOSTS=["testserver"],
        SESSION_SAVE_EVERY_REQUEST=True,
        SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
    ):
        cache.clear()
        # MIDDLEWARE = [UpdateCacheMiddleware, SessionMiddleware, FetchFromCacheMiddleware]
        chain = UpdateCacheMiddleware(SessionMiddleware(FetchFromCacheMiddleware(view)))
        session = import_module(settings.SESSION_ENGINE).SessionStore()
        session["reader"] = "ada"
        session.save()
        reader = RequestFactory()
        reader.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
        chain(reader.get("/entries/2026/"))
        second = chain(RequestFactory().get("/entries/2026/"))
        cookie = settings.SESSION_COOKIE_NAME in second.cookies
        cache.clear()
    if len(calls) == 2:
        return "the view, setting a session cookie" if cookie else "the view, setting no cookie"
    return "the cache, setting the first visitor's session cookie" if cookie else "the cache"


@habit('response["Cache-Control"] = "Private": whether UpdateCacheMiddleware stores it')
def cache_control_in_capitals():
    def prepare(response):
        response["Cache-Control"] = "Private"
    return stored(prepare)


@habit('response["Vary"] = "*": whether UpdateCacheMiddleware stores it')
def vary_star():
    def prepare(response):
        response["Vary"] = "*"
    return stored(prepare)


@habit('response["Vary"] = " * ", the star between spaces: whether UpdateCacheMiddleware stores it')
def vary_star_between_spaces():
    def prepare(response):
        response["Vary"] = " * "
    return stored(prepare)


@habit('response.set_cookie("sessionid", "ada") with "Vary: Cookie", the request carrying only '
       'theme=dark: whether UpdateCacheMiddleware stores it')
def cookie_set_with_another_in_the_request():
    def prepare(response):
        response.set_cookie("sessionid", "ada")
        response["Vary"] = "Cookie"
    return stored(prepare, cookies={"theme": "dark"})


@habit('A GET bearing "Authorization: Bearer ada": the Vary UpdateCacheMiddleware leaves on the response')
def authorization_varied_on():
    response, found = through_the_page_cache(lambda response: None, headers={"Authorization": "Bearer ada"})
    return repr(response.get("Vary"))


# Header names, domain names and log lines.

@habit('ASGIRequest(scope).META.get("HTTP_X_FORWARDED_FOR"): the header sent as "x_forwarded_for"')
def asgi_underscored_header():
    import io

    from django.core.handlers.asgi import ASGIRequest

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/entries/2026/",
        "headers": [(b"x_forwarded_for", b"10.0.0.1")],
    }
    return repr(ASGIRequest(scope, io.BytesIO()).META.get("HTTP_X_FORWARDED_FOR"))


@habit('DomainNameValidator()("journal.example\\n")')
def domain_name_with_a_newline():
    from django.core.validators import DomainNameValidator
    DomainNameValidator()("journal.example\n")
    return "accepted"


def logged(logger_name, call):
    """The messages logged to one logger while `call` runs, its own handlers set aside."""
    import logging

    messages = []

    class Keep(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    logger = logging.getLogger(logger_name)
    handlers, logger.handlers = logger.handlers, [Keep()]
    propagate, logger.propagate = logger.propagate, False
    try:
        call()
    finally:
        logger.handlers, logger.propagate = handlers, propagate
    return messages


@habit('Client().get("/entries/%1B[2J"): the message "django.request" logs for the 404')
def log_of_a_404_path():
    from django.test import Client

    messages = logged("django.request", lambda: Client().get("/entries/%1B[2J"))
    return repr(messages[0])


@habit('runserver\'s log of the request line "GET /entries/\\x1b[2J HTTP/1.1", answered 404')
def runserver_log_line():
    import socket

    from django.core.handlers.wsgi import WSGIHandler
    from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer

    # runserver's server, not bound, and its handler serving one connection, as runserver serves
    # each: the request comes over a socket pair, its request line holding the escape character
    # itself, as a client may send it, and Django answers it.
    server = WSGIServer(("127.0.0.1", 0), WSGIRequestHandler, bind_and_activate=False)
    server.server_name, server.server_port = "testserver", 80
    server.setup_environ()
    server.set_app(WSGIHandler())
    client, served = socket.socketpair()
    try:
        client.sendall(b"GET /entries/\x1b[2J HTTP/1.1\r\nHost: testserver\r\n\r\n")
        client.shutdown(socket.SHUT_WR)
        messages = logged("django.server", lambda: WSGIRequestHandler(served, ("127.0.0.1", 50000), server))
    finally:
        served.close()
        client.close()
        server.server_close()
    return repr(messages[0])


# What timing and outcomes tell.

def hasher_runs(call):
    """How often the default hasher hashes while `call` runs; its iterations are cut to one for
    the run, which changes how long a run takes and not how often it hashes."""
    from django.contrib.auth.hashers import PBKDF2PasswordHasher

    runs = []
    encode, iterations = PBKDF2PasswordHasher.encode, PBKDF2PasswordHasher.iterations

    def counting(self, password, salt, iterations=None):
        runs.append(1)
        return encode(self, password, salt, iterations)

    PBKDF2PasswordHasher.encode, PBKDF2PasswordHasher.iterations = counting, 1
    try:
        call()
    finally:
        PBKDF2PasswordHasher.encode, PBKDF2PasswordHasher.iterations = encode, iterations
    return f"{len(runs)} run of the default hasher" if len(runs) == 1 else f"{len(runs)} runs of the default hasher"


@habit('authenticate(username="ada", password="guess"), ada\'s password unusable: the hasher\'s runs')
def authenticate_unusable_password():
    from django.contrib.auth import authenticate
    from django.contrib.auth.models import User

    ada = User(pk=1, username="ada")
    ada.set_unusable_password()
    ada.save()
    try:
        return hasher_runs(lambda: authenticate(username="ada", password="guess"))
    finally:
        ada.delete()


@habit('modwsgi.check_password({}, "nobody", "guess"): the hasher\'s runs for a name with no account')
def modwsgi_check_password():
    from django.contrib.auth.handlers import modwsgi
    return hasher_runs(lambda: modwsgi.check_password({}, "nobody", "guess"))


@habit('PasswordResetForm({"email": "ada@journal.example"}).save(), the mail failing to send')
def password_reset_mail_fails():
    import smtplib

    from django.contrib.auth.forms import PasswordResetForm
    from django.contrib.auth.models import User
    from django.core.mail import EmailMessage
    from django.test.utils import override_settings

    templates = {"journal/subject.txt": "Your journal", "journal/email.txt": "Reset it."}
    # A usable password, so that the form finds ada; it is never checked.
    ada = User.objects.create(pk=1, username="ada", email="ada@journal.example", password="pbkdf2_sha256$1$salt$hash")

    def refused(self, fail_silently=False):
        raise smtplib.SMTPRecipientsRefused({"ada@journal.example": (550, b"no such mailbox")})

    send, EmailMessage.send = EmailMessage.send, refused
    form = PasswordResetForm({"email": "ada@journal.example"})
    form.is_valid()
    try:
        with override_settings(TEMPLATES=[{
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "OPTIONS": {"loaders": [("django.template.loaders.locmem.Loader", templates)]},
        }]):
            messages = logged("django.contrib.auth", lambda: form.save(
                domain_override="journal.example",
                subject_template_name="journal/subject.txt",
                email_template_name="journal/email.txt",
            ))
    finally:
        EmailMessage.send = send
        ada.delete()
    return f"returns; \"django.contrib.auth\" logs {messages[0]!r}" if messages else "returns; nothing logged"


# File names, archives and modes.

@habit('Storage.save("/journal.txt", ContentFile(b"entry")), the storage\'s _save writing any name '
       'it is given: what it writes')
def storage_save_absolute_name():
    from django.core.files.base import ContentFile
    from django.core.files.storage import Storage

    written = {}

    class Remote(Storage):
        """A storage of its own, as one over a remote service is: it writes the name it is given."""

        def exists(self, name):
            return name in written

        def _save(self, name, content):
            written[name] = content.read()
            return name

    try:
        Remote().save("/journal.txt", ContentFile(b"entry"))
    except Exception as error:  # noqa: BLE001 - what is written is the question, the error its reason
        refusal = f": {type(error).__name__}: {error}"
    else:
        refusal = ""
    return (", ".join(sorted(written)) or "nothing") + refusal


@habit('extract("template.zip", "journal"): an archive with a member "../journal-evil/settings.py"')
def archive_partial_traversal():
    import os
    import tempfile
    import zipfile

    from django.utils.archive import extract

    with tempfile.TemporaryDirectory() as directory:
        archive = os.path.join(directory, "template.zip")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("manage.py", "")
            zipped.writestr("../journal-evil/settings.py", "")
        target = os.path.join(directory, "journal")
        os.mkdir(target)
        extract(archive, target)
        return "extracted"


@habit('FileSystemStorage(location, directory_permissions_mode=0o750).save("2026/notes.txt", ...): '
       'the calls of os.umask')
def storage_directories_without_umask():
    import os
    import tempfile

    from django.core.files.base import ContentFile
    from django.core.files.storage import FileSystemStorage

    calls = []
    umask = os.umask

    def counting(mask):
        calls.append(mask)
        return umask(mask)

    with tempfile.TemporaryDirectory() as directory:
        storage = FileSystemStorage(location=directory, directory_permissions_mode=0o750)
        os.umask = counting
        try:
            storage.save("2026/notes.txt", ContentFile(b"entry"))
        finally:
            os.umask = umask
    return f"{len(calls)} calls"


# The admin's formsets and links.

class Clerk:
    """A staff user of the admin who may view and change everything and add nothing."""
    is_active = is_staff = True
    is_superuser = False
    is_authenticated = True
    pk = id = 1

    def has_perm(self, perm, obj=None):
        return not perm.split(".")[-1].startswith("add_")

    def has_module_perms(self, app_label):
        return True


@habit("A generic inline's formset, a forged new row from a user who may change but not add: the rows it saves")
def generic_inline_forged_row():
    from django.contrib import admin
    from django.contrib.contenttypes.admin import GenericTabularInline
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType
    from django.db import models
    from django.test import RequestFactory
    from journal.models import Entry

    class Remark(models.Model):
        content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
        object_id = models.PositiveIntegerField()
        content_object = GenericForeignKey("content_type", "object_id")
        text = models.CharField(max_length=100)

        class Meta:
            app_label = "journal"

    create(Remark)

    class RemarkInline(GenericTabularInline):
        model = Remark

    entry = Entry.objects.create(title="Monday", published="2026-09-21")
    request = RequestFactory().post("/admin/journal/entry/1/change/")
    request.user = Clerk()
    FormSet = RemarkInline(Entry, admin.AdminSite()).get_formset(request, entry)
    prefix = FormSet.get_default_prefix()
    data = {f"{prefix}-TOTAL_FORMS": "1", f"{prefix}-INITIAL_FORMS": "0", f"{prefix}-0-text": "forged"}
    formset = FormSet(data, instance=entry, prefix=prefix)
    try:
        if not formset.is_valid():
            return f"invalid: {formset.errors!r}"
        return f"{len(formset.save(commit=False))} rows saved"
    finally:
        entry.delete()


@habit("ModelAdmin.changelist_view with list_editable: a POST that forges a new row, from a user "
       "who may change entries but not add them")
def list_editable_forged_row():
    from django.contrib import admin
    from django.contrib.auth.models import Permission, User
    from django.contrib.messages.storage.cookie import CookieStorage
    from django.test import RequestFactory
    from journal.models import Entry

    class EntryAdmin(admin.ModelAdmin):
        list_display = ["id", "title", "published"]
        list_editable = ["title", "published"]

    clerk = User.objects.create(pk=1, username="clerk", is_staff=True, password="!")
    clerk.user_permissions.add(*Permission.objects.filter(codename__in=["view_entry", "change_entry"]))
    request = RequestFactory().post("/admin/journal/entry/", {
        "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0",
        "form-0-id": "", "form-0-title": "Forged", "form-0-published": "2026-09-28", "_save": "Save",
    })
    request.user = clerk
    request._dont_enforce_csrf_checks = True
    request._messages = CookieStorage(request)
    try:
        response = EntryAdmin(Entry, admin.AdminSite()).changelist_view(request)
        return f"answered {response.status_code}; entries in the table: {Entry.objects.count()}"
    finally:
        Entry.objects.all().delete()
        clerk.delete()


@habit('display_for_field("javascript:alert(1)", models.URLField(), "-")')
def admin_url_field_link():
    from django.contrib.admin.utils import display_for_field
    from django.db import models
    return repr(display_for_field("javascript:alert(1)", models.URLField(), "-"))


# STARTTLS in the SMTP backend.

@habit("EmailBackend(use_tls=True, fail_silently=True).send_messages, twice, STARTTLS failing: "
       "the messages handed to the server")
def starttls_failing_silently():
    import smtplib
    import warnings

    from django.core.mail import EmailMessage
    from django.core.mail.backends.smtp import EmailBackend

    handed = []

    class Server:
        """Stands for smtplib.SMTP: STARTTLS fails, and every message it is handed is kept."""

        def __init__(self, host, port, **kwargs):
            pass

        def starttls(self, context=None):
            raise smtplib.SMTPException("STARTTLS extension not supported by server.")

        def login(self, user, password):
            pass

        def sendmail(self, from_address, to_addresses, message, *args, **kwargs):
            handed.append(message)
            return {}

        def quit(self):
            pass

        def close(self):
            pass

    class Backend(EmailBackend):
        connection_class = Server

    with warnings.catch_warnings():  # how the backend is made is not what is asked
        warnings.simplefilter("ignore")
        backend = Backend(host="smtp.journal.example", port=587, use_tls=True, fail_silently=True)
    message = EmailMessage("Monday", "The entry.", "journal@journal.example", ["ada@journal.example"])
    backend.send_messages([message])
    backend.send_messages([message])
    return f"{len(handed)} messages handed to the server"


main()
