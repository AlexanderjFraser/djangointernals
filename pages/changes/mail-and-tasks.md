---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in mail and tasks

Messages built on Python's modern email API; keyword arguments, and `ADMINS` as addresses; mailers named by alias in `MAILERS`, in place of `EMAIL_BACKEND`; and background tasks, `django.tasks`.

In 6.0 Django moved the building of a message from Python's legacy email classes to its modern API. In 6.1 it began to name backends by alias, in `MAILERS`. `EMAIL_BACKEND` is deprecated with it. Background tasks are new in 6.0.

## The message: Python's modern email API

Since 6.0 `EmailMessage.message` builds Python's `email.message.EmailMessage`, where 5.2 built Django's `SafeMIMEText` or `SafeMIMEMultipart`. The new message has the old classes' API but is no instance of them (`docs/releases/6.0.txt`). It is built under a policy, `email.policy.default` unless `policy=` names another, and the policy checks the headers (`django/core/mail/message.py:EmailMessage.message`).

A newline in the subject raised Django's `BadHeaderError` under 5.2.17, and raises the policy's `ValueError` since 6.0. `BadHeaderError`, deprecated, is now `ValueError` itself, so code that catches it catches the policy's error (`django/core/mail/message.py:BadHeaderError`).

Since 6.1 a `"Bcc"` among the extra headers raises `ValueError` as the message is built. 5.2.17 and 6.0.8 wrote it into the message every recipient receives ([Email messages: `EmailMessage` and `EmailMultiAlternatives`](../services/email-messages.md)).

## Keyword arguments, and `ADMINS` as addresses

Since 6.0 the functions of `django.core.mail` take `fail_silently=` and every parameter after it by keyword. `EmailMessage` and `EmailMultiAlternatives` take all but the subject, body, sender and To list by keyword. A positional use still works, and warns (`django/utils/deprecation.py:deprecate_posargs`).

Since 6.0 `ADMINS` and `MANAGERS` are lists of address strings. Under 5.2.17 they had to be lists of (name, address) pairs, and `mail_admins` refused a list of strings with `ValueError`. Django never used the names, the 6.0 notes say. A list of pairs is now reduced to its addresses as mail is sent, with a warning. A value that is neither empty nor a list or tuple of strings is `ImproperlyConfigured` (`django/core/mail/__init__.py:_send_server_message`).

## `MAILERS` and `mailers`

Since 6.1 a project names its email backends by alias in `MAILERS`, where it named one in `EMAIL_BACKEND`. The handler `django.core.mail.mailers` makes a new backend at each lookup, of the class an entry's `"BACKEND"` names, with its `"OPTIONS"` (`django/core/mail/handler.py:MailersHandler.create_connection`). The sending functions and `EmailMessage.send` take `using=`, an alias, and sendtestemail takes --using ([Sending email: `mailers` and the email backends](../services/mailers.md)).

`EmailMessage.send`, which `send_mail` calls, takes the mailer `using=` names. Without `using=`, it takes a backend the message holds, given as `connection=`, or else what the deprecated `get_connection` makes (`django/core/mail/message.py:EmailMessage.send`). An alias `MAILERS` lacks raises `MailerDoesNotExist`. Without `MAILERS`, so does every alias but `"default"`, and that one is what `get_connection` makes. Given no backend's path, `get_connection` makes the `"default"` mailer where `MAILERS` is defined, and otherwise the class `EMAIL_BACKEND` names, with no alias (`django/core/mail/__init__.py:get_connection`). The figure follows `send` to a message's backend:

```text figure=finding-a-mailer
EmailMessage.send(), which send_mail calls

1  using= given?
     yes                       mailers[alias]: step 2
     no, connection= given     that backend
     no, neither               get_connection(): step 3
2  mailers[alias]: MAILERS defined?
     yes, with the alias       a new backend of the entry's "BACKEND"
     yes, without it           MailerDoesNotExist
     no, the alias "default"   get_connection(): step 3
     no, another alias         MailerDoesNotExist
3  get_connection(): MAILERS defined?
     yes, with "default"       a new backend of the "default" entry
     no                        a new backend of the class
                               EMAIL_BACKEND names
```

*How `EmailMessage.send`, not given both `using=` and `connection=`, finds the backend: an answer turns right off its question's line, to a backend, an error or step 2, or runs down into step 3.*

Without `MAILERS`, `get_connection` also warns "Django 2028 will not have a default mailer. …", unless an old email setting is defined, since such a setting warns of its own (`django/core/mail/deprecation.py:warn_about_default_mailers_if_needed`). So since 6.1 a project that sets no email setting is warned as it asks for its default mailer; 5.2.17 and 6.0.8 have no `mailers` to ask:

```text recording=changes
mailers["default"]: in a project that defines no MAILERS, every setting at its default
    5.2.17       ImportError: cannot import name 'mailers' from 'django.core.mail'
    6.0.8        ImportError: cannot import name 'mailers' from 'django.core.mail'
    6.1.1        django.core.mail.backends.smtp.EmailBackend, alias None, host 'localhost', port 25, warns RemovedInDjango70Warning
    this commit  django.core.mail.backends.smtp.EmailBackend, alias None, host 'localhost', port 25, warns RemovedInDjango2028Warning
```

The old settings are refused beside `MAILERS` ([What changed in settings, startup and the commands](startup-and-commands.md)).

## The old ways in, and what they now refuse

Since 6.1 `django.core.mail.get_connection` is deprecated, and with it `connection=` and `EmailMessage.connection`, `fail_silently=`, `auth_user=` and `auth_password=`. Each warns only when used from outside Django (`django/utils/deprecation.py:warn_about_external_use`).

Since 6.1 `send_mail` refuses `fail_silently=True`, `auth_user=` or `auth_password=` beside a backend given as `connection=` (`django/core/mail/__init__.py:send_mail`). Older versions ignored them there, the documentation says (`docs/topics/email.txt`). Under 5.2.17 and 6.0.8 the message is sent; the refusal comes after the warnings of `fail_silently=` and `connection=`:

```text recording=changes
send_mail("Monday", "Published.", None, ["ada@example.com"], fail_silently=True, connection=backend)
    5.2.17       1
    6.0.8        1
    6.1.1        TypeError: fail_silently cannot be used with a connection. Pass fail_silently to get_connection() instead., warns RemovedInDjango70Warning
    this commit  TypeError: fail_silently cannot be used with a connection. Pass fail_silently to get_connection() instead., warns RemovedInDjango2028Warning
```

Since 6.1 `EmailMessage.send` no longer leaves the backend it used in `EmailMessage.connection`, as 5.2.17 and 6.0.8 did for a message that held none. A subclass that defines a method get_connection, which `send` called before 6.1, now makes `send` raise `AttributeError` (`django/core/mail/message.py:EmailMessage.send`).

Since 6.1 a keyword argument a backend does not take raises the exception `InvalidMailer` among an entry's `"OPTIONS"`. A backend made directly, by calling its class, ignores it, as all did before 6.1, and warns (`django/core/mail/backends/base.py:BaseEmailBackend.__init__`). An SMTP backend made directly, deprecated too, reads the old settings for what it is not given (`django/core/mail/backends/smtp.py:EmailBackend.__init__`). Where `MAILERS` is defined none of the old settings can be read. So given only a host, it raises `AttributeError` at `EMAIL_PORT`, where 5.2.17 and 6.0.8 read port 25 (`django/conf/__init__.py:LazySettings.__getattr__`).

## Error reports by email

Since 6.1 `AdminEmailHandler` takes `using=`, and `email_backend=` is deprecated. A subclass that defines a connection method, undocumented and no longer called, raises `AttributeError` as it is made (`django/utils/log.py:AdminEmailHandler.__init__`; [Logging](../startup/logging.md)). `BrokenLinkEmailsMiddleware` takes its alias from `BrokenLinkEmailsMiddleware.using`, also since 6.1 (`django/middleware/common.py:BrokenLinkEmailsMiddleware.send_mail`).

> **Trap.** Defining `MAILERS` can make a failed error report loud. Without it, the handler and the middleware send with `fail_silently=True`, so the SMTP backend passes over a server it cannot reach. With it, they catch only `MailerDoesNotExist`. Unless the mailer's `"OPTIONS"` set `"fail_silently"`, an error in sending is raised from `AdminEmailHandler.emit` to the code that logged the record, since logging does not catch what a handler raises (`django/utils/log.py:AdminEmailHandler.send_mail`).

## Background tasks: `django.tasks`

Background tasks are new in 6.0. The `task` decorator turns a module-level function into a `Task`, and `Task.enqueue` hands it to its backend of `TASKS` (`django/tasks/base.py:Task.enqueue`). The default, `ImmediateBackend`, runs the task inside `enqueue`. Django "does not provide a worker mechanism to run tasks", the 6.0 notes say (`docs/releases/6.0.txt`; [Background tasks: `Task`, `TaskResult` and the task backends](../services/tasks.md)).

Since 6.1 the decorator passes the keyword arguments it does not name, all but `run_after=`, to the backend's `BaseTaskBackend.task_class`; 6.0.8's decorator refused them. The default class, `Task`, takes only its own fields (`django/tasks/base.py:task`).

Since 6.1 a task can be pickled. Under 6.0.8 pickle refuses one with `pickle.PicklingError`: it finds a function by its name, and the decorator bound that name to the `Task`. `Task.__reduce__` now pickles the function's dotted path instead (`django/tasks/base.py:Task.__reduce__`).

## The smaller changes

The rest, by name:

| what | change | where |
|---|---|---|
| `EmailMessage.attach` | Since 6.0, takes an `email.message.MIMEPart`, which 5.2.17 refused; a legacy `email.mime.base.MIMEBase` is attached with a warning | `django/core/mail/message.py:EmailMessage.attach` |
| `EmailMultiAlternatives.alternatives` | Since 5.2, holds `EmailAlternative` named tuples; a plain tuple appended raises `AttributeError` as the message is built | `django/core/mail/message.py:EmailMultiAlternatives._add_bodies` |
| `EmailMessage.encoding` | Since 6.0, an `email.charset.Charset` there raises `TypeError` as the message is built | `django/core/mail/message.py:EmailMessage._add_bodies` |
| mixed_subtype, alternative_subtype | Gone in 6.0, unwarned: the undocumented subtypes of a message with attachments, or alternatives; set, they make building it raise `AttributeError` | `django/core/mail/message.py` |
| 5.2's _create_ methods | Gone in 6.0: undocumented, _create_message among them; an override of one is not called | `django/core/mail/message.py:EmailMessage.message` |
| the checks of `MAILERS` | New in 6.1: `"mail.W001"` warns of no `"default"`; `"mail.E001"`, in deployment, fails on a development backend there | `django/core/checks/mail.py` |
