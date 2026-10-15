---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Sending email: `mailers` and the email backends

`mailers`, the handler of the `MAILERS` setting, makes a new email backend each time it is asked for an alias. The backends build on `BaseEmailBackend`, whose `send_messages` sends a list of messages; `send_mail`, `send_mass_mail`, `mail_admins` and `mail_managers` build messages and hand them to one.

In production a message leaves through an SMTP server, over a connection costly to open (`docs/topics/email.txt`); in development and tests it goes to the console, a file, a list in memory or nowhere. A backend offers one method, `BaseEmailBackend.send_messages`, which sends a list of messages, and two more, `BaseEmailBackend.open` and `BaseEmailBackend.close`, for a connection that is to serve several sends. The message itself is the subject of [Email messages: `EmailMessage` and `EmailMultiAlternatives`](email-messages.md).

## `MAILERS` and `MailersHandler`

`django.core.mail.mailers` is a `MailersHandler`. Unlike the handlers of the cache and the tasks it is not built on `BaseConnectionHandler`, and keeps nothing: `MailersHandler.__getitem__` calls `MailersHandler.create_connection` every time, and `MailersHandler.settings` reads `MAILERS` at each access, so a change to the setting is seen by the next lookup (`django/core/mail/handler.py:MailersHandler`). `MailersHandler.default` looks up `"default"`; a test with `in`, and iteration, go over the setting's keys; `MailersHandler.get` returns its default only for an alias that is not configured.

`create_connection` raises `MailerDoesNotExist` for an alias the setting lacks. It takes the entry's `"OPTIONS"`, refuses options that name `"alias"`, imports the class that `"BACKEND"` names, the SMTP backend when none is given (`DEFAULT_MAILER_BACKEND`), and makes the backend with the options as keyword arguments and the alias beside them, `alias="relay"` for the entry below. A path that will not import becomes an `InvalidMailer` that names it (`django/core/mail/handler.py:MailersHandler.create_connection`). `InvalidMailer` is an `ImproperlyConfigured` whose message begins by naming the entry when it is given the alias, and `MailerDoesNotExist` is an `InvalidMailer` that is also a `KeyError`, whose message, without that beginning, is the one shown below (`django/core/mail/exceptions.py`).

The office gives its bulletin a mailer of its own and names an SMTP relay:

```python
# harbour/settings.py, the mailers
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
    "bulletin": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
    "relay": {"OPTIONS": {"host": "mail.harbour.example", "use_tls": True}},
}
```

Asked with these settings, the handler answered:

```text
list(mailers)                               ['default', 'bulletin', 'relay']
mailers["default"] is mailers["default"]    False
mailers["relay"]                            django.core.mail.backends.smtp.EmailBackend, port 587
mailers["nowhere"]                          MailerDoesNotExist: "The mailer 'nowhere' is not configured."
mailers.get("nowhere")                      None
```

A backend holds the state of its connection, the SMTP backend a socket and the file backend an open file, and each lookup gives the caller one that no other caller holds. To send several times over one connection, code keeps the instance, in the documentation's way in a `with` block (`docs/topics/email.txt`).

## Without `MAILERS`: the deprecated settings

`MAILERS` has no default: `django/conf/global_settings.py` holds it only as a comment, so `MailersHandler._is_configured`, a test of whether the settings have it, is true only in a project that defines it. Where it is false, `create_connection` answers `"default"` with `django.core.mail.get_connection`, and any other alias is `MailerDoesNotExist`; `"default" in mailers` is false there, though the lookup succeeds. `get_connection` warns that Django 2028 will have no default mailer, unless an old email setting is defined (`warn_about_default_mailers_if_needed`), and makes the backend `EMAIL_BACKEND` names without an alias, which sends the SMTP backend to `EMAIL_HOST`, `EMAIL_PORT` and the other old settings (`django/core/mail/__init__.py:get_connection`).

`get_connection` is deprecated in 6.1, with the `connection=`, `fail_silently=` and credential arguments of the sending functions, to go in Django 2028 (`docs/releases/6.1.txt`, `docs/internals/deprecation.txt`). It warns through `warn_about_external_use`, which warns only when the caller is outside Django, so that one deprecated feature built on another does not warn twice ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](../utils/deprecation.md)) (`django/utils/deprecation.py:warn_about_external_use`). With `MAILERS` defined, it returns the default mailer, with any keyword arguments added to the entry's options, and refuses a backend's path with `RuntimeError`.

Defining any setting of `DEPRECATED_EMAIL_SETTINGS` beside `MAILERS` is an `ImproperlyConfigured` as the settings load (`django/conf/__init__.py:_check_email_settings_conflicts`), and reading one while `MAILERS` is defined raises `AttributeError` (`django/conf/__init__.py:LazySettings.__getattr__`).

## `BaseEmailBackend`

`BaseEmailBackend.__init__` keeps `alias`, `None` for a backend made directly. It receives the keyword arguments the subclass did not consume: made for an alias, it raises `InvalidMailer` naming them as unknown options; made directly, it ignores them, warning when the maker is outside Django (`django/core/mail/backends/base.py:BaseEmailBackend.__init__`). So a subclass takes its own options out before it passes the rest up, and `"fail_silently"` is an option only of the backends that consume it, the SMTP, console and file backends; the local-memory and dummy backends refuse it.

`open` and `close` do nothing in the base. `BaseEmailBackend.__enter__` calls `open`, and `close` if that fails; `BaseEmailBackend.__exit__` calls `close` (`django/core/mail/backends/base.py:BaseEmailBackend.__enter__`). `send_messages` raises `NotImplementedError`: it is the one method a backend must write. Its contract, in the documentation: return the number sent; open a connection if none is open and close it after, but leave open one that was open (`docs/topics/email.txt`).

## The SMTP backend

`django.core.mail.backends.smtp.EmailBackend` is what an entry gets when it names no backend. Made for an alias, it requires `"host"`; without `"port"` it takes 465 with `"use_ssl"`, 587 with `"use_tls"`, else 25; it refuses the two together. Made without an alias, it reads each option it is not given from the old setting, the port from `EMAIL_PORT` whatever the security (`django/core/mail/backends/smtp.py:EmailBackend.__init__`).

`EmailBackend.open` returns `False` when a connection is open. Otherwise it closes what is left of an earlier attempt and connects, over SSL with `"use_ssl"`. The new connection is held aside while STARTTLS (with `"use_tls"`) and the login (when a username and a password are set) run, and becomes `EmailBackend.connection` only when both have succeeded, so a connection that failed half-way is never taken for an open one; the next `open` or `close` quits it. With `"fail_silently"`, an `OSError`, which every exception of the standard library's SMTP module is, makes `open` return `None` (`django/core/mail/backends/smtp.py:EmailBackend.open`).

`EmailBackend.send_messages` returns 0 for an empty list. Otherwise, under the instance's re-entrant lock, it calls `open`, returns 0 if that failed in silence, sends each message with `EmailBackend._send`, and in a `finally` clause closes the connection if this call opened it (`django/core/mail/backends/smtp.py:EmailBackend.send_messages`). So one call sends all its messages over one connection, and one the caller opened stays open. `_send` skips a message with no recipients, reduces the sender and recipients to the bare addresses of the SMTP envelope, and sends the message's bytes, built under the standard library's SMTP policy, whose lines end in CR LF.

`EmailBackend.prep_address` raises `ValueError` for any defect the standard library's parser finds in an address, a line break among them, but allows a local part with no domain, so that a sender such as `"webmaster"` works (ticket 15042). It requires one mailbox, encodes a domain that is not ASCII with IDNA, and returns the bare address: `"office@harbour.example"` for `"Harbour Office <office@harbour.example>"` (`django/core/mail/backends/smtp.py:EmailBackend.prep_address`).

## The console, file, local-memory and dummy backends

The console backend writes each message's text to its `"stream"`, standard output by default, with a line of 79 hyphens after it (`django/core/mail/backends/console.py:EmailBackend.send_messages`). The file backend is a console backend whose stream is a file: it requires `"file_path"`, a directory it creates, and its `open` opens for appending a file there named for the time and the instance's `id` (`django/core/mail/backends/filebased.py:EmailBackend.open`).

The local-memory backend, as it is made, sets `outbox` on `django.core.mail` to an empty list if the module has none. Its `send_messages` builds each message, which validates its headers, and appends a deep copy to the outbox with `EmailMessage.sent_using` set to its alias, leaving the caller's message unchanged (`django/core/mail/backends/locmem.py:EmailBackend.send_messages`). The dummy backend counts the messages and drops them. These four are for development: the deployment check mail.E001 fails when one of them is the `"default"` mailer (`django/core/checks/mail.py:check_mailers_production_backend`). For a test run Django gives every alias the local-memory backend ([The test framework](../testing.md)) (`django/test/utils.py:setup_test_environment`).

## `send_mail`, `send_mass_mail`, `mail_admins` and `mail_managers`

`send_mail`, `send_mass_mail`, `mail_admins` and `mail_managers` all end in `EmailMessage.send` or in one backend's `send_messages`. `EmailMessage.send` returns 0 for a message with no recipients, before any backend is made. With `using=` it sends through that alias's mailer; without, through a backend given by the deprecated argument, or else through `django.core.mail.get_connection`, which with `MAILERS` defined is the default mailer; `using=` beside a deprecated argument is a `TypeError` (`django/core/mail/message.py:EmailMessage.send`).

`send_mail` builds an `EmailMultiAlternatives`, an HTML body as its alternative where one is given, and returns what `send` returns (`django/core/mail/__init__.py:send_mail`). `send_mass_mail` makes one backend and sends all its messages in one call of `send_messages`, so through the SMTP backend they share a connection, where `send_mail` opens one each time (`django/core/mail/__init__.py:send_mass_mail`).

`mail_admins` and `mail_managers` share `_send_server_message`, which reads `ADMINS` or `MANAGERS` and, when the list is empty, returns without making a message or a backend. A list of `(name, address)` pairs is warned of and reduced to its addresses; anything but a list or tuple of strings is `ImproperlyConfigured`. The subject is prefixed with `EMAIL_SUBJECT_PREFIX`, `"[Django] "` by default, and the sender is `SERVER_EMAIL`, not `DEFAULT_FROM_EMAIL` (`django/core/mail/__init__.py:_send_server_message`). With the settings above, a run gave:

```text
send_mail(..., using="bulletin")            1
send_mail(...)                              1
mail_admins(...), ADMINS = []               None
mail_admins(...), ADMINS = ["master@..."]   None
mail.outbox
  'Berths free on 20 October'   from office@harbour.example  sent_using 'bulletin'
  'Endeavour sailed'            from office@harbour.example  sent_using 'default'
  '[Django] Disk full'          from root@localhost          sent_using 'default'
```

`AdminEmailHandler` mails errors through `mail_admins` ([Logging](../startup/logging.md)). The sendtestemail command calls `send_mail` and, with its options, `mail_managers` and `mail_admins`, each with the alias its option --using gives (`django/core/management/commands/sendtestemail.py:Command.handle`).
