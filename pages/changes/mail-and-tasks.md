---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in mail and tasks

The changes in `django.core.mail` and `django.tasks` from Django 5.0 to this commit: messages on Python's modern email API; the `MAILERS` setting and its handler `mailers`, `EMAIL_BACKEND` and `get_connection`; and background tasks.

In 6.0 Django moved the building of a message from Python's legacy email classes to its modern API. In 6.1 it began to name backends by alias, in `MAILERS`, as `CACHES`, `DATABASES`, `STORAGES` and `TASKS` do, and deprecated `EMAIL_BACKEND`, to go in Django 2028. Background tasks are new in 6.0.

## The message: Python's modern email API

Under 5.2 `EmailMessage.message` built Django's `SafeMIMEText`, or a `SafeMIMEMultipart` for a message with attachments or alternatives, and checked each header itself. Since 6.0 it builds an `email.message.EmailMessage` under a policy, `email.policy.default` unless its new policy argument names another, and the policy does the checking (`django/core/mail/message.py:EmailMessage.message`). Here a message is built; the line is its class:

```text recording=changes
EmailMessage("Monday", "Published.", to=["ada@example.com"]).message(): its class
    5.2.17       django.core.mail.message.SafeMIMEText
    6.0.8        email.message.EmailMessage
    6.1.1        email.message.EmailMessage
    this commit  email.message.EmailMessage
```

The new value has the old classes' API but is no instance of them, the 6.0 notes say (`docs/releases/6.0.txt`). A newline in the subject raised Django's `BadHeaderError` under 5.2.17, and raises the policy's `ValueError` since 6.0; `BadHeaderError`, deprecated, is now `ValueError` itself, so that code catching it catches the policy's error (`django/core/mail/message.py:BadHeaderError`). Importing `BadHeaderError`, `SafeMIMEText` or `SafeMIMEMultipart` from `django.core.mail` warns (`django/core/mail/__init__.py:__getattr__`).

`EmailMessage.attach` takes an `email.message.MIMEPart` since 6.0, which 5.2.17 refused, and attaches a legacy `email.mime.base.MIMEBase` with a warning (`django/core/mail/message.py:EmailMessage.attach`). Since 6.1 a `"Bcc"` among the extra headers raises `ValueError` as the message is built, where 5.2.17 and 6.0.8 wrote it into the message every recipient receives ([Email messages: `EmailMessage` and `EmailMultiAlternatives`](../services/email-messages.md)).

## Keyword arguments, and `ADMINS` as addresses

Since 6.0 the functions of `django.core.mail` take fail_silently and every parameter after it by keyword, and `EmailMessage` and `EmailMultiAlternatives` all but the subject, body, sender and To list. A positional use still works, and warns (`django/utils/deprecation.py:deprecate_posargs`).

Under 5.2.17 `ADMINS` and `MANAGERS` had to be lists of (name, address) pairs, and `mail_admins` refused a list of strings with `ValueError`. Django never used the names, the 6.0 notes say, and since 6.0 both are lists of address strings: as `mail_admins` or `mail_managers` sends, a list of pairs is reduced to its addresses with a warning, and a value that is neither empty nor a list or tuple of strings is `ImproperlyConfigured` (`django/core/mail/__init__.py:_send_server_message`).

## `MAILERS` and `mailers`

Until 6.1 a project's settings configured one email backend, named by `EMAIL_BACKEND` and made by `get_connection`. Since 6.1 `MAILERS` names backends by alias, for "configuring multiple email backends with different options" (`docs/releases/6.1.txt`), and its handler, `django.core.mail.mailers`, makes at each lookup a new backend from an entry's `"BACKEND"` and `"OPTIONS"` (`django/core/mail/handler.py:MailersHandler.create_connection`). The sending functions and `EmailMessage.send` take using=, an alias, and sendtestemail --using ([Sending email: `mailers` and the email backends](../services/mailers.md)). The figure gives each way in:

```text figure=finding-a-mailer
send_mail(...)                  an EmailMultiAlternatives holding connection= if given (deprecated),
                                or, with no using= either, get_connection(); then its send(using=...)

EmailMessage.send(using=None)
  using=alias                   mailers[alias]
  a connection held             that backend; holding one is deprecated
  neither                       get_connection()

mailers[alias]                  a new instance at each lookup
  MAILERS defined               the class MAILERS[alias]["BACKEND"] names,
                                made with its "OPTIONS" and alias=alias; an alias it lacks: MailerDoesNotExist
  MAILERS not defined           "default": get_connection(); any other alias: MailerDoesNotExist

get_connection(backend=None)    deprecated: warns when called from outside Django
  MAILERS defined               a new instance of the "default" entry, keyword arguments added to
                                its "OPTIONS"; a backend's path: RuntimeError
  MAILERS not defined           warns "Django 2028 will not have a default mailer. ..." unless an old
                                email setting is defined; makes the class EMAIL_BACKEND names (or the
                                path given) with no alias: the SMTP backend reads EMAIL_HOST and the rest
```

*How the code at this commit finds the backend that sends a message: the mailer `using=` names, or a backend passed as `connection=` (the two together are a `TypeError`), or else what the deprecated `get_connection` makes, the default mailer or the backend `EMAIL_BACKEND` names.*

`send_mail` builds an `EmailMultiAlternatives`, and given neither `using=` nor `connection=` hands it the backend `get_connection` makes (`django/core/mail/__init__.py:send_mail`). An alias `MAILERS` lacks, or any but `"default"` without it, raises the exception `MailerDoesNotExist`; beside `MAILERS`, `get_connection` makes the `"default"` mailer, its keyword arguments added to the entry's `"OPTIONS"`, unknown ones ignored, and refuses a backend's path with `RuntimeError` (`django/core/mail/__init__.py:get_connection`). Without `MAILERS`, `get_connection` makes the backend whose path it is given, or else the class `EMAIL_BACKEND` names, and `mailers` answers `"default"` with it; it warns "Django 2028 will not have a default mailer. …" unless an old email setting is defined, since such a setting warns of its own (`django/core/mail/deprecation.py:warn_about_default_mailers_if_needed`, `django/conf/__init__.py:Settings.__init__`). Here a project with no email setting asks for its default mailer; since 6.1 even such a project is warned:

```text recording=changes
mailers["default"]: in a project that defines no MAILERS, every setting at its default
    5.2.17       ImportError: cannot import name 'mailers' from 'django.core.mail'
    6.0.8        ImportError: cannot import name 'mailers' from 'django.core.mail'
    6.1.1        django.core.mail.backends.smtp.EmailBackend, alias None, host 'localhost', port 25, warns RemovedInDjango70Warning
    this commit  django.core.mail.backends.smtp.EmailBackend, alias None, host 'localhost', port 25, warns RemovedInDjango2028Warning
```

The old settings are refused beside `MAILERS` ([What changed in settings, startup and the commands](startup-and-commands.md)).

## The old ways in, and what they now refuse

`get_connection` is deprecated (6.1); 5.2.17 and 6.0.8, which knew no `MAILERS`, made the backend of `EMAIL_BACKEND` whatever `MAILERS` held (`django/core/mail/__init__.py:get_connection`). Deprecated with it, and warning only when called from outside Django: connection= and `EmailMessage.connection`, fail_silently=, auth_user= and auth_password= (`django/utils/deprecation.py:warn_about_external_use`).

Here `send_mail` is given a backend as connection= and fail_silently=True; older versions ignored fail_silently= beside a connection, the documentation says (`docs/topics/email.txt`):

```text recording=changes
send_mail("Monday", "Published.", None, ["ada@example.com"], fail_silently=True, connection=backend)
    5.2.17       1
    6.0.8        1
    6.1.1        TypeError: fail_silently cannot be used with a connection. Pass fail_silently to get_connection() instead., warns RemovedInDjango70Warning
    this commit  TypeError: fail_silently cannot be used with a connection. Pass fail_silently to get_connection() instead., warns RemovedInDjango2028Warning
```

Since 6.1 the call is refused before a message is made, after two warnings, of fail_silently= and connection=, whose one class the line names once (`django/core/mail/__init__.py:send_mail`); credentials beside a connection are refused alike.

Since 6.1 `EmailMessage.send` no longer leaves the backend it used in `EmailMessage.connection` of a message that held none, as 5.2.17 and 6.0.8 did. A subclass that defines a method get_connection, which `send` called before 6.1, now makes `send` raise `AttributeError` (`django/core/mail/message.py:EmailMessage.send`).

A backend's unknown keyword argument, ignored before 6.1, raises the exception `InvalidMailer` among an entry's `"OPTIONS"`. A backend made directly, by calling its class, has the alias `None` and still ignores the argument, with a warning (`django/core/mail/backends/base.py:BaseEmailBackend.__init__`). An SMTP backend made directly, deprecated too, reads the old settings for what it is not given (`django/core/mail/backends/smtp.py:EmailBackend.__init__`). Where `MAILERS` is defined none can be read, even one left at its default, so given only a host the backend raises `AttributeError` as it reads `EMAIL_PORT`, where 5.2.17 and 6.0.8 read port 25 (`django/conf/__init__.py:LazySettings.__getattr__`).

## Error reports by email

`AdminEmailHandler` takes using= since 6.1, and its email_backend argument is deprecated. Its undocumented connection method is no longer called, the 6.1 notes say, and since 6.1 a subclass that defines one raises `AttributeError` as it is made (`django/utils/log.py:AdminEmailHandler.__init__`; [Logging](../startup/logging.md)). `BrokenLinkEmailsMiddleware` takes its alias from `BrokenLinkEmailsMiddleware.using` (`django/middleware/common.py:BrokenLinkEmailsMiddleware.send_mail`).

> **Trap.** Defining `MAILERS` can make a failed error report loud. Without it, the handler and the middleware send with fail_silently=True, so the SMTP backend passes over a server it cannot reach; with it, they catch only `MailerDoesNotExist`, and unless the mailer's `"OPTIONS"` set `"fail_silently"`, an error in sending is raised from `AdminEmailHandler.emit` to the code that logged the record, since logging does not catch what a handler raises (`django/utils/log.py:AdminEmailHandler.send_mail`).

## Background tasks: `django.tasks`

Since 6.0 the `task` decorator turns a module-level function into a `Task`, and `Task.enqueue` hands it and its arguments to its backend of `TASKS`, which returns a `TaskResult` (`django/tasks/base.py:Task.enqueue`). `TASKS` defaults to `ImmediateBackend`, which runs the task inside `enqueue`; `DummyBackend` runs nothing. Django "does not provide a worker mechanism to run tasks", the 6.0 notes say (`docs/releases/6.0.txt`; [Background tasks: `Task`, `TaskResult` and the task backends](../services/tasks.md)).

Since 6.1 the decorator passes a keyword argument it does not name, run_after apart, to the backend's `BaseTaskBackend.task_class`, where 6.0.8's decorator refused it; the default class, `Task`, takes only its own fields (`django/tasks/base.py:task`). And since 6.1 a task can be pickled; here one is pickled and loaded:

```text recording=changes
pickle.loads(pickle.dumps(publish_entry)).name: a task
    5.2.17       ModuleNotFoundError: No module named 'django.tasks'
    6.0.8        PicklingError: Can't pickle <function publish_entry>: it's not the same object as __main__.publish_entry
    6.1.1        'publish_entry'
    this commit  'publish_entry'
```

Pickle finds a function by its name, which the decorator bound to the `Task`. Since 6.1 `Task.__reduce__` pickles the function's dotted path, and `Task._reconstruct` takes the function from the task bound there (`django/tasks/base.py:Task.__reduce__`).

## The smaller changes

The rest, by name:

| what | at this commit | release | where |
|---|---|---|---|
| mixed_subtype, alternative_subtype | undocumented; set, they make building a message with attachments, or alternatives, raise `AttributeError`; 5.2.17 used them as subtypes, and nothing warned; 5.2.17's _create_ methods, _create_message among them, are gone, and an override of one is not called | 6.0 | `django/core/mail/message.py:EmailMessage._add_attachments` |
| `EmailMessage.encoding` | undocumented; an `email.charset.Charset` there raises `TypeError` as the message is built | 6.0 | `django/core/mail/message.py:EmailMessage._add_bodies` |
| `EmailMultiAlternatives.alternatives` | `EmailAlternative` named tuples, as attachments are `EmailAttachment`; a plain tuple appended raises `AttributeError` as the message is built (`docs/releases/5.2.txt`) | 5.2 | `django/core/mail/message.py:EmailMultiAlternatives._add_bodies` |
| `"mail.W001"`, `"mail.E001"` | checks: `MAILERS` without `"default"`; in deployment, a development backend there | 6.1 | `django/core/checks/mail.py` |
