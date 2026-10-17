"""What changed in mail and tasks: the habits of the section of that name. They ask what a
message is built as and what it refuses (6.0, 6.1), how the mail functions and classes take
their arguments and ADMINS (6.0), which backend sends where a project defines MAILERS or does
not (6.1), what the old ways of handing a backend in now do (6.1), and what a task is and does
(6.0, 6.1). Run by recordings/changes.py under each release; _run.py says how a habit is
written.

A habit that sends sends through the local-memory backend, handed in or set as EMAIL_BACKEND
for the habit, so that none reaches a mail server; a habit that makes the SMTP backend only
makes it. The lines of a habit that sets EMAIL_BACKEND are those of a project that names its
backend there. From 6.1 setting EMAIL_BACKEND warns, as such a project's settings load and as
override_settings sets it: that warning is the setup's, and is kept off the line
(quietly_overridden). Such a project is not warned at the use, from 6.1, that Django 2028 has
no default mailer; a project that sets no email setting is (mailers["default"]). MAILERS,
whose setting no release warns for, is set with override_settings as it is. The module runs
as a script, so its task's function is __main__.publish_entry.
"""
from contextlib import contextmanager

from _run import configure, habit, main

configure()

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
LOCMEM_MAILERS = {"default": {"BACKEND": LOCMEM}}


def qualname(cls):
    return f"{cls.__module__}.{cls.__qualname__}"


@contextmanager
def quietly_overridden(**values):
    """override_settings, entered and left with warnings silenced: from 6.1 setting a deprecated
    email setting such as EMAIL_BACKEND warns, and that warning is the habit's setup, not the
    use it records."""
    import warnings

    from django.test.utils import override_settings

    override = override_settings(**values)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        override.enable()
    try:
        yield
    finally:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            override.disable()


def monday(**kwargs):
    from django.core.mail import EmailMessage

    return EmailMessage("Monday", "Published.", to=["ada@example.com"], **kwargs)


# The message.


@habit('EmailMessage("Monday", "Published.", to=["ada@example.com"]).message(): its class')
def message_class():
    return qualname(type(monday().message()))


@habit("from django.core.mail import BadHeaderError")
def bad_header_error():
    from django.core.mail import BadHeaderError
    return f"{BadHeaderError.__module__}.{BadHeaderError.__name__}"


@habit('EmailMessage("Monday\\nBcc: eve@example.com", "Published.", to=["ada@example.com"]).message()')
def newline_in_subject():
    from django.core.mail import EmailMessage

    EmailMessage("Monday\nBcc: eve@example.com", "Published.", to=["ada@example.com"]).message()
    return "the message is built"


@habit('message.mixed_subtype = "related", with a file attached: the type of message.message()')
def mixed_subtype():
    message = monday()
    message.mixed_subtype = "related"
    message.attach("entry.txt", "Monday", "text/plain")
    return message.message().get_content_type()


@habit('message.encoding = email.charset.Charset("utf-8"): the charset of message.message()')
def encoding_as_a_charset():
    import email.charset

    message = monday()
    message.encoding = email.charset.Charset("utf-8")
    return repr(message.message().get_content_charset())


@habit("message.attach(part), part an email.message.MIMEPart: the files of message.message()")
def attach_mime_part():
    from email.message import MIMEPart

    part = MIMEPart()
    part.set_content("Monday")
    part.add_header("Content-Disposition", "attachment", filename="entry.txt")
    message = monday()
    message.attach(part)
    return repr([attached.get_filename() for attached in message.message().iter_attachments()])


@habit('message.attach(MIMEText("Monday")), a legacy email.mime.base.MIMEBase: the types in message.attachments')
def attach_mime_base():
    from email.mime.text import MIMEText

    message = monday()
    message.attach(MIMEText("Monday"))
    return repr([type(attached).__name__ for attached in message.attachments])


@habit('message.alternatives.append(("<p>Published.</p>", "text/html")), then message.message()')
def alternative_as_a_tuple():
    from django.core.mail import EmailMultiAlternatives

    message = EmailMultiAlternatives("Monday", "Published.", to=["ada@example.com"])
    message.alternatives.append(("<p>Published.</p>", "text/html"))
    message.message()
    return "the message is built"


@habit('headers={"Bcc": "eve@example.com"}: the "Bcc" header of message.message()')
def bcc_among_the_headers():
    return repr(monday(headers={"Bcc": "eve@example.com"}).message()["Bcc"])


# The sending functions' arguments, and ADMINS.


@habit('EmailMessage("Monday", "Published.", None, ["ada@example.com"], ["eve@example.com"]).bcc')
def bcc_by_position():
    from django.core.mail import EmailMessage

    return repr(EmailMessage("Monday", "Published.", None, ["ada@example.com"], ["eve@example.com"]).bcc)


def admins_sent_to(admins):
    """The To list of what mail_admins sends, through the local-memory backend."""
    from django.core import mail

    with quietly_overridden(EMAIL_BACKEND=LOCMEM, ADMINS=admins):
        mail.outbox = []
        mail.mail_admins("Monday", "Published.")
        return repr(mail.outbox[-1].to)


@habit('ADMINS = ["ada@example.com"], then mail_admins("Monday", "Published."): the message\'s To')
def admins_as_strings():
    return admins_sent_to(["ada@example.com"])


@habit('ADMINS = [("Ada", "ada@example.com")], then mail_admins("Monday", "Published."): the message\'s To')
def admins_as_pairs():
    return admins_sent_to([("Ada", "ada@example.com")])


# Which backend sends.


@habit('mailers["default"]: in a project that defines no MAILERS, every setting at its default')
def default_mailer_without_mailers():
    from django.core.mail import mailers

    backend = mailers["default"]
    return f"{qualname(type(backend))}, alias {backend.alias!r}, host {backend.host!r}, port {backend.port!r}"


@habit('get_connection(): MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}')
def get_connection_with_mailers():
    from django.core.mail import get_connection
    from django.test.utils import override_settings

    with override_settings(MAILERS=LOCMEM_MAILERS):
        return qualname(type(get_connection()))


@habit('smtp.EmailBackend(host="mail.example.com").port: in a project that defines MAILERS')
def smtp_backend_made_directly():
    from django.core.mail.backends.smtp import EmailBackend
    from django.test.utils import override_settings

    with override_settings(MAILERS=LOCMEM_MAILERS):
        return repr(EmailBackend(host="mail.example.com").port)


@habit('locmem.EmailBackend(region="africa-1"): a keyword argument the backend does not take')
def backend_given_an_unknown_option():
    from django.core.mail.backends.locmem import EmailBackend

    return qualname(type(EmailBackend(region="africa-1")))


# The old ways in.


@habit('send_mail("Monday", "Published.", None, ["ada@example.com"], fail_silently=True, connection=backend)')
def fail_silently_beside_a_connection():
    from django.core.mail import send_mail
    from django.core.mail.backends.locmem import EmailBackend

    backend = EmailBackend()
    return repr(send_mail("Monday", "Published.", None, ["ada@example.com"], fail_silently=True,
                          connection=backend))


@habit('class Notice(EmailMessage) that defines get_connection(): Notice("Monday", "Published.", to=["ada@example.com"]).send()')
def subclass_defines_get_connection():
    from django.core.mail import EmailMessage
    from django.core.mail.backends.locmem import EmailBackend

    class Notice(EmailMessage):
        def get_connection(self, fail_silently=False):
            return EmailBackend()

    return repr(Notice("Monday", "Published.", to=["ada@example.com"]).send())


@habit("message.send(), then message.connection: the backend the message holds")
def connection_after_send():
    message = monday()
    with quietly_overridden(EMAIL_BACKEND=LOCMEM):
        message.send()
    connection = message.connection
    return "None" if connection is None else qualname(type(connection))


@habit("class Reporting(AdminEmailHandler) that defines connection(): Reporting()")
def admin_email_handler_with_connection():
    from django.core.mail import get_connection
    from django.utils.log import AdminEmailHandler

    class Reporting(AdminEmailHandler):
        def connection(self):
            return get_connection(fail_silently=True)

    Reporting()
    return "the handler is made"


# Tasks.


def publish_entry():
    """A task's function, at the module's level as a task's must be."""
    return "published"


PUBLISH_ENTRY = publish_entry


def decorated():
    """The task of publish_entry, its name bound to the task as @task above it would bind it."""
    global publish_entry
    from django.tasks import task

    if publish_entry is PUBLISH_ENTRY:
        publish_entry = task(PUBLISH_ENTRY)
    return publish_entry


@habit("publish_entry.enqueue().return_value: @task def publish_entry(), with TASKS at its default")
def enqueue_with_the_default_backend():
    return repr(decorated().enqueue().return_value)


@habit("@task(retries=3) def publish_entry(): a keyword argument the decorator does not name")
def task_given_an_unknown_argument():
    from django.tasks import task

    task(retries=3)(PUBLISH_ENTRY)
    return "the task is made"


@habit("pickle.loads(pickle.dumps(publish_entry)).name: a task")
def task_pickled():
    import pickle
    import re

    task = decorated()
    try:
        return repr(pickle.loads(pickle.dumps(task)).name)
    except pickle.PicklingError as error:
        message = re.sub(r" at 0x[0-9A-Fa-f]+", "", str(error).splitlines()[0])  # an address is this run's
        return f"{type(error).__name__}: {message}"


main()
