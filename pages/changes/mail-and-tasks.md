---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in mail and tasks

What changed in `django.core.mail` and `django.tasks` from Django 5.0 to this commit: messages built with Python's modern email API (6.0), the `MAILERS` setting and its handler `mailers`, which replace `EMAIL_BACKEND` and `get_connection` (6.1), and background tasks (6.0).

What 6.0 and 6.1 deprecated in `django.core.mail` goes in Django 2028; until then it ordinarily works and warns, and some of it is refused where `MAILERS` is defined ([What still warns: the deprecations and the releases that end them](deprecations.md)).

## The message: Python's modern email API

Until 6.0 `EmailMessage.message` built Django's `SafeMIMEText` and `SafeMIMEMultipart`, on the legacy classes of `email.mime`, and checked headers itself. Since 6.0 it builds an `email.message.EmailMessage` under a policy, `email.policy.default` unless its new policy argument names another, and the policy does the checking (`django/core/mail/message.py:EmailMessage.message`). The value has the old classes' API but is no instance of them; the modern API is "a cleaner and Unicode-friendly interface", the release notes say (`docs/releases/6.0.txt`). [Email messages: `EmailMessage` and `EmailMultiAlternatives`](../services/email-messages.md) tells how a message is built now.

What the legacy API needed is deprecated. `SafeMIMEText` and `SafeMIMEMultipart` are still handed out by the package's `__getattr__`, with a warning (`django/core/mail/__init__.py:__getattr__`); `forbid_multi_line_headers` and `sanitize_address` warn when called; and `EmailMessage.attach` warns when given a legacy `email.mime.base.MIMEBase`, and since 6.0 takes an `email.message.MIMEPart`. `BadHeaderError`, deprecated too, is now `ValueError` itself, so that code catching it catches what the policy raises (`django/core/mail/message.py:BadHeaderError`). Undocumented, and changed in 6.0: the attributes mixed_subtype and alternative_subtype, which make building a message with attachments, or alternatives, respectively raise `AttributeError`; `EmailMessage.encoding`, which no longer takes an `email.charset.Charset`; and the underscore methods, rewritten.

Since 5.2 `attach` keeps a filename, content and type as an `EmailAttachment`, a named tuple, and an entry of `EmailMultiAlternatives.alternatives` is an `EmailAlternative`. Alternatives are read by field name as the message is built, so one appended as a plain tuple fails then, with `AttributeError`; the release notes support adding one only by `EmailMultiAlternatives.attach_alternative` (`django/core/mail/message.py:EmailMultiAlternatives._add_bodies`). `EmailMultiAlternatives.body_contains` came then. Since 6.1 a `"Bcc"` among the extra headers raises `ValueError` when the message is built: blind copies go in the bcc argument (`django/core/mail/message.py:EmailMessage.message`).

## Keyword arguments, and `ADMINS` as addresses

Since 6.0 the functions of `django.core.mail` take their less common parameters by keyword: fail_silently and every parameter after it, for `get_connection`, `send_mail`, `send_mass_mail`, `mail_admins` and `mail_managers`, and all but the subject, body, sender and To list, for `EmailMessage` and `EmailMultiAlternatives`. A positional use still works and warns (`django/utils/deprecation.py:deprecate_posargs`).

`ADMINS` and `MANAGERS` are lists of address strings since 6.0. As `mail_admins` or `mail_managers` sends, a list of (name, address) pairs warns and is reduced to its addresses, and a value that is not a list or tuple of strings is `ImproperlyConfigured` (`django/core/mail/__init__.py:_send_server_message`).

## `MAILERS` and `mailers`

Until 6.1 a project had one email backend, named by `EMAIL_BACKEND` and configured by `EMAIL_HOST` and the settings beside it, and `get_connection` made an instance of it or of a path it was given. Since 6.1 `MAILERS` names backends by alias, as `CACHES`, `DATABASES`, `STORAGES` and `TASKS` do, for "configuring multiple email backends with different options" (`docs/releases/6.1.txt`). Its handler, `django.core.mail.mailers`, makes at each lookup a new instance of the class an entry's `"BACKEND"` names, the SMTP backend when it names none, with the entry's `"OPTIONS"` as keyword arguments and the alias beside them (`django/core/mail/handler.py:MailersHandler.create_connection`). The four sending functions, `send_mail`, `send_mass_mail`, `mail_admins` and `mail_managers`, and `EmailMessage.send` take `using=`, an alias, and the sendtestemail command takes --using. [Sending email: `mailers` and the email backends](../services/mailers.md) tells the handler and the backends.

```text figure=finding-a-mailer
send_mail(...)                  an EmailMultiAlternatives holding connection= if given (deprecated),
                                or, with no using= either, get_connection(); then its send(using=...)

EmailMessage.send(using=None)
  using=alias                   mailers[alias]
  a connection held             that backend; holding one is deprecated
  neither                       get_connection()

mailers[alias]                  a new instance at each lookup
  MAILERS defined               the class MAILERS[alias]["BACKEND"] names (the SMTP backend if none),
                                made with its "OPTIONS" and alias=alias; an alias it lacks: MailerDoesNotExist
  MAILERS not defined           "default": get_connection(); any other alias: MailerDoesNotExist

get_connection(backend=None)    deprecated: warns when called from outside Django
  MAILERS defined               a new instance of the "default" entry, keyword arguments added to
                                its "OPTIONS"; a backend's path: RuntimeError
  MAILERS not defined           warns "Django 2028 will not have a default mailer. ..." unless an old
                                email setting is defined; makes the class EMAIL_BACKEND names (or the
                                path given) with no alias: the SMTP backend reads EMAIL_HOST and the rest
```

*How the code at this commit finds the backend that sends a message: the mailer `using=` names, else a backend passed as `connection=`, else what the deprecated `get_connection` makes, the default mailer or the backend `EMAIL_BACKEND` names.*

`MAILERS` has no default; the global settings hold it only as a comment. In a project that does not define it, `mailers` answers `"default"` with `get_connection`, which makes the backend `EMAIL_BACKEND` names, with no alias, so that the SMTP backend reads the old settings; any other alias is `MailerDoesNotExist` (`django/core/mail/handler.py:MailersHandler`). Unless an old email setting is defined, which warned as the settings loaded, the lookup warns that a mailer will be required (`django/core/mail/deprecation.py:warn_about_default_mailers_if_needed`):

```text
# run_block.py at this commit: a project that defines no MAILERS, every setting at its default
mailers["default"]    django.core.mail.backends.smtp.EmailBackend, alias None, host 'localhost', port 25
  warns RemovedInDjango2028Warning: Django 2028 will not have a default mailer. Configure settings.MAILERS to avoid errors when sending email.
mailers["bulletin"]   MailerDoesNotExist: "The mailer 'bulletin' is not configured."
```

The old email settings are deprecated (6.1); what the settings object does with them is in [What changed in settings, startup and the commands](startup-and-commands.md).

## The old ways in, and what they now refuse

`get_connection` is deprecated (6.1). Where `MAILERS` is defined it returns a new instance of the default mailer, its keyword arguments added to the entry's options, and refuses a backend's path with `RuntimeError` (`django/core/mail/__init__.py:get_connection`). Deprecated with it: connection= on the four functions and on `EmailMessage`, and the property `EmailMessage.connection`; fail_silently= on the four and on `EmailMessage.send`; auth_user= and auth_password= on `send_mail` and `send_mass_mail`. Each warns only when called from outside Django, so `send_mail` calling `get_connection` does not warn of it ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](../utils/deprecation.md)).

Some old combinations now raise (6.1). fail_silently=True, auth_user= or auth_password= beside connection= is a `TypeError`, where older versions ignored them, the documentation says (`docs/topics/email.txt`); so is any of them, or connection=, beside `using=` (`django/core/mail/deprecation.py:report_using_incompatibility`). `EmailMessage.send` no longer stores on the message the backend it used, though it uses one set there, and raises `AttributeError` for a subclass that defines a method get_connection, which it used to call (`django/core/mail/message.py:EmailMessage.send`).

`BaseEmailBackend.__init__` keeps the alias, `None` for a backend made directly. An entry's unknown options are `InvalidMailer`; a backend made with no alias ignores unknown keyword arguments, as before, and warns, where the code that makes it is outside Django, that Django 2028 will refuse them. The base's support for fail_silently is deprecated: a backend that offers it keeps its own attribute, as the SMTP, console and file backends do (`django/core/mail/backends/base.py:BaseEmailBackend.__init__`). Making the SMTP backend directly is deprecated too; such an instance reads the old settings for what it is not given, and where `MAILERS` is defined, one made in a run with only a host raised `AttributeError` as it read EMAIL_PORT (`django/core/mail/backends/smtp.py:EmailBackend.__init__`).

Two checks came with it (6.1): `"mail.W001"` warns when `MAILERS` lacks a `"default"` entry, and the deployment check `"mail.E001"` is an error when that entry names the console, file, local-memory or dummy backend (`django/core/checks/mail.py`).

## Error reports by email

`AdminEmailHandler` takes `using=` since 6.1. Its email_backend argument is deprecated, and refused with `ImproperlyConfigured` beside `using=` or where `MAILERS` is defined; its undocumented connection method is gone, and a subclass that defines one raises `AttributeError` as it is made (`django/utils/log.py:AdminEmailHandler.__init__`). `BrokenLinkEmailsMiddleware` takes its alias from its class attribute `BrokenLinkEmailsMiddleware.using` (`django/middleware/common.py:BrokenLinkEmailsMiddleware.send_mail`). Without `MAILERS`, both send with fail_silently=True, as before, and leave the alias aside; with it, they send to the alias, pass no fail_silently and catch only `MailerDoesNotExist`, so an error in sending is not swallowed: in a run whose default mailer's SMTP host could not be reached, `AdminEmailHandler.emit` raised `TimeoutError` (`django/utils/log.py:AdminEmailHandler.send_mail`). [Logging](../startup/logging.md) tells the handler.

## Background tasks: `django.tasks`

Since 6.0 Django describes work to run outside the request. The `task` decorator turns a module-level function into a `Task`, checked against its backend as it is made; `Task.enqueue` hands it and its arguments to the task's backend of `TASKS`, which returns a `TaskResult`, the record of what became of it (`django/tasks/base.py:Task.enqueue`). `TASKS` defaults to `ImmediateBackend`, which runs the task inside `enqueue` (`django/conf/global_settings.py`); `DummyBackend` keeps results and runs nothing. Both are "primarily intended for development and testing", and Django "does not provide a worker mechanism to run tasks", the release notes say (`docs/releases/6.0.txt`). [Background tasks: `Task`, `TaskResult` and the task backends](../services/tasks.md) tells the mechanism.

Since 6.1 the decorator passes a keyword argument it does not take, all but run_after, which it refuses, to the backend's `BaseTaskBackend.task_class`: a task class that declares such a field takes it, and the built-in `Task` refuses it with a `TypeError` (`django/tasks/base.py:task`). And since 6.1 a `Task` and a `TaskResult` can be pickled: a task pickles as its fields, its function replaced by the function's dotted path, and is made again with those fields and the function of the task the decorator bound at that path (`django/tasks/base.py:Task.__reduce__`).
