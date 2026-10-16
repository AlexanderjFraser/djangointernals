---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What still warns: the deprecations and the releases that end them

Every deprecation in the code at this commit: what warns with `RemovedInDjango2029Warning` or `RemovedInDjango2028Warning`, the line that raises the warning, and what the code will do in Django 2029 or Django 2028, the releases that end them.

The deprecation timeline, `docs/internals/deprecation.txt`, lists under each coming release what it will remove or change. At this commit each entry but the one for `select_related(True)`, which fails already, is code that keeps the old use working beside the new, and comments naming the warning class mark lines that must change when a deprecation ends, often with the code that will replace them.

## Removed in Django 2029

What 6.2 deprecated, but for the readings of `django.VERSION`, warns with `RemovedInDjango2029Warning`, a `PendingDeprecationWarning`. [What changed in handlers, requests, URLs and views](request-cycle.md) tells the first two; [What changed in querysets](querysets.md), [What changed in expressions, lookups and the compiler](sql.md) and [What changed in forms and validators](forms.md) one each.

| deprecated | warns at | in Django 2029 |
|---|---|---|
| `MiddlewareMixin` imported from `django.utils.deprecation` | `django/utils/deprecation.py:__getattr__` | the old path fails; the class is in `django.middleware` |
| `JsonResponse` given safe at all, true or false | `django/http/response.py:JsonResponse.__init__` | the parameter goes, with the `TypeError` for data not a dict |
| `QuerySet.aiterator` after `QuerySet.prefetch_related` with no chunk size; it takes 2,000 | `django/db/models/query.py:QuerySet.aiterator` | `ValueError`, as `QuerySet.iterator` raises already |
| an `Extract` or `Trunc` with no `tzinfo` deconstructed, as a migration writes it, while `USE_TZ` is true | `django/db/models/functions/datetime.py:TimezoneMixin.deconstruct` | the current time zone is written into the arguments |
| `EmailValidator.validate_domain_part`, overridden, or called from code that Django did not call | `django/core/validators.py:EmailValidator.__init_subclass__`, `django/core/validators.py:EmailValidator.validate_domain_part` | removed; `EmailValidator.validate_domain` alone checks the domain |

## Removed in Django 2028

What 6.0 and 6.1 deprecated, and the readings of `django.VERSION` deprecated in 6.2, ends in Django 2028, and what of it warns does so with `RemovedInDjango2028Warning`, a `DeprecationWarning`.

### Settings

[What changed in settings, startup and the commands](startup-and-commands.md) tells how the settings object warns for a deprecated setting and refuses the email settings beside `MAILERS`, and [What changed](../changes.md#how-a-change-is-carried) the transitional settings.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| the email settings of `DEPRECATED_EMAIL_SETTINGS`, `EMAIL_BACKEND` among them, set, or read first from outside Django | `django/conf/__init__.py:Settings.__init__`, `django/conf/__init__.py:LazySettings.__getattr__` | removed; `MailersHandler.settings` reads `MAILERS` alone |
| no `MAILERS` and no email setting set, when the default mailer is built | `django/core/mail/deprecation.py:warn_about_default_mailers_if_needed` | no default mailer: the global settings define `MAILERS` as empty (`django/conf/global_settings.py`) |
| `USE_BLANK_CHOICE_DASH` set | `django/conf/__init__.py:Settings.__init__` | removed, with `get_blank_choice_label`; a blank choice's label is `BLANK_CHOICE_LABEL` |
| `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` set | `django/conf/__init__.py:Settings.__init__` | removed; `_unsign_cookie` tries only the salt of `_cookie_signer_salt` |
| `URLIZE_ASSUME_HTTPS` set | no warning; read where `urlize` warns (`django/utils/html.py:Urlizer.handle_word`) | removed; `"https"` the default |

### Mail

[What changed in mail and tasks](mail-and-tasks.md) tells the changes these serve: Python's modern email API, keyword arguments and `MAILERS`.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| fail_silently or a later argument of `send_mail`, `send_mass_mail`, `mail_admins`, `mail_managers` or `django.core.mail.get_connection`, or any after the first four of `EmailMessage` and `EmailMultiAlternatives`, given by position | `django/utils/deprecation.py:deprecate_posargs` | `TypeError`: the decorator goes, the parameters stay keyword-only |
| `django.core.mail.get_connection`, called from outside Django | `django/core/mail/__init__.py:get_connection` | removed; a backend comes from `mailers` |
| the connection, fail_silently, auth_user and auth_password arguments of the sending functions, `EmailMessage`'s connection and `EmailMessage.connection`, fail_silently of `EmailMessage.send` | `django/core/mail/__init__.py:send_mail`, `django/core/mail/message.py:EmailMessage.__init__`, `django/core/mail/message.py:EmailMessage.connection`, `django/core/mail/message.py:EmailMessage.send` | removed; a message goes through the mailer that using names, or the default |
| the SMTP `EmailBackend` made outside `mailers` | `django/core/mail/backends/smtp.py:EmailBackend.__init__` | unsupported, the timeline says |
| `BaseEmailBackend.__init__`, outside `mailers`, given a keyword it does not take, or fail_silently; fail_silently read on a backend that sets none | `django/core/mail/backends/base.py:BaseEmailBackend.__init__`, `django/core/mail/backends/base.py:BaseEmailBackend.__getattr__` | `TypeError` for an unknown keyword, the warning says; no fail_silently |
| `AdminEmailHandler` given email_backend | `django/utils/log.py:AdminEmailHandler.__init__` | removed; the handler's using names the mailer |
| `ADMINS` or `MANAGERS` as (name, address) pairs, when mail is sent to them | `django/core/mail/__init__.py:_send_server_message` | the branch goes, and the check after it raises `ImproperlyConfigured` |
| an `email.mime.base.MIMEBase` attached, by `EmailMessage.attach` or the attachments argument | `django/core/mail/message.py:EmailMessage.attach` | removed; an attachment is an `email.message.MIMEPart` or a tuple |
| `BadHeaderError`, `SafeMIMEText` and `SafeMIMEMultipart` taken from `django.core.mail` | `django/core/mail/__init__.py:__getattr__` | removed; `BadHeaderError` is already `ValueError` |
| `forbid_multi_line_headers` or `sanitize_address` called | `django/core/mail/message.py:forbid_multi_line_headers`, `django/core/mail/message.py:sanitize_address` | removed |

### Models, querysets and SQL

Told in [What changed in querysets](querysets.md) (`select_related`, `values_list`, `from_db`), [What changed in expressions, lookups and the compiler](sql.md) (the alias, the JSON lookup, the compiler), [What changed in models and fields](models.md) (the placeholder), [What changed in forms and validators](forms.md) (the blank choice), [What changed in the database backends and migrations](backends-and-migrations.md) (the savepoint) and [What changed in the test framework](testing.md) (the test database).

| deprecated | warns at | in Django 2028 |
|---|---|---|
| `QuerySet.select_related` with no arguments, called from outside Django | `django/db/models/query.py:QuerySet.select_related` | `TypeError` |
| `select_related(True)`, which fails with `AttributeError` | no warning; `django/db/models/sql/query.py:Query.add_select_related` | `TypeError` |
| `QuerySet.values_list` with `flat=True` and no field, which takes the first concrete field | `django/db/models/query.py:QuerySet.values_list` | `TypeError` |
| a model's own `Model.from_db` that takes no fetch_mode, called without the queryset's mode | `django/db/models/query.py:_get_from_db` | `from_db` always given fetch_mode |
| a percent sign in an alias | `django/db/models/sql/query.py:Query.check_alias` | `ValueError`: `FORBIDDEN_ALIAS_PATTERN` takes in the sign |
| `None` as an exact lookup's value on a whole `JSONField`, taken as JSON null | `django/db/models/fields/json.py:JSONExact.process_rhs` | `"IS NULL"`; JSON null is `JSONNull` |
| a field class that defines a method get_placeholder and no get_placeholder_sql, given one that calls it | `django/db/models/fields/__init__.py:Field.__init_subclass__` | the shim goes |
| `SQLCompiler.quote_name_unless_alias` | `django/db/models/sql/compiler.py:SQLCompiler.quote_name_unless_alias` | removed; `SQLCompiler.quote_name` |
| `BLANK_CHOICE_DASH` | no warning; read when `USE_BLANK_CHOICE_DASH` is true (`django/db/models/utils.py:get_blank_choice_label`) | removed |
| `django.db.transaction.savepoint` | `django/db/transaction.py:savepoint` | removed; `savepoint_create` |
| `BaseDatabaseCreation.create_test_db` given serialize; the message names a serialize_test_db that the tree does not define | `django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db` | the parameter goes |

### Templates, signing, pagination and the version

[What changed in templates](templates.md) tells the first two; [What changed in security: Content Security Policy and signing](security.md) the algorithm; [What changed in caching, files, signals, serialization and pagination](caching-files-signals.md) the orphans; [Django's version: `VersionTuple` and `get_version`](../utils/version.md) the readings of `django.VERSION`.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| `urlize` and `urlizetrunc` linking a web address that has no scheme, while `URLIZE_ASSUME_HTTPS` is false | `django/utils/html.py:Urlizer.handle_word` | `"https://"` assumed |
| two dots in a row in a variable tag, `{{ port..name }}` | `django/template/base.py:Parser.parse` | `TemplateSyntaxError`, by the comment at the warning |
| `salted_hmac` or `base64_hmac` with no algorithm, which takes `"sha1"` | `django/utils/crypto.py:salted_hmac`, `django/core/signing.py:base64_hmac` | `"sha256"` the default |
| a `Paginator` or `AsyncPaginator` whose orphans are not fewer than its page size | `django/core/paginator.py:BasePaginator.__init__` | `ValueError` |
| `django.VERSION` indexed from its third component, iterated, measured, or compared with three or more components | `django/utils/version.py:VersionTuple._warn` | four components, (year, patch, status, iteration) |

### The admin

[What changed in the admin](admin.md) tells these changes.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| `ModelAdmin.list_select_related` set to `True` in a subclass | `django/contrib/admin/options.py:ModelAdmin.__init_subclass__` | `ValueError` |
| `ModelAdmin.get_list_select_related` returning `True` | `django/contrib/admin/options.py:ModelAdmin.get_changelist_instance` | `ValueError` |
| `ModelAdmin.get_actions` overridden without action_location, which gives the change form no actions | `django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location` | called with action_location, say the comments at its callers |
| `ModelAdmin.get_action_choices` overridden without action_location | `django/contrib/admin/options.py:ModelAdmin._get_action_choices_with_action_location` | the same |
| an `Action` unpacked or indexed like the tuple it replaced | `django/contrib/admin/options.py:Action.__iter__`, `django/contrib/admin/options.py:Action.__getitem__` | removed |

### The PostgreSQL aggregates

[What changed in the other contrib apps](contrib.md) tells them.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| `StringAgg` of `django.contrib.postgres.aggregates`, and its delimiter given as a string | `django/contrib/postgres/aggregates/general.py:StringAgg.__init__` | removed; in `django.db.models.StringAgg` a string delimiter is a field reference |
| `BitAnd`, `BitOr` and `BitXor` of the same module | `django/contrib/postgres/aggregates/general.py:BitAnd.__init__`, `django/contrib/postgres/aggregates/general.py:BitOr.__init__`, `django/contrib/postgres/aggregates/general.py:BitXor.__init__` | removed; those of `django.db.models` |
| `OrderableAggMixin` subclassed | `django/contrib/postgres/aggregates/mixins.py:OrderableAggMixin.__init_subclass__` | removed; `Aggregate.allow_order_by` |

## Which line a warning names, and what `-Wd` shows

A warning names one line of the stack, and Python's filters judge it by that line's module. Each site chooses the line: `skip_file_prefixes=django_file_prefixes()` names the first frame outside Django's directory (`django/utils/warnings.py:django_file_prefixes`); `warn_about_external_use` names the code that used the feature, and is silent when that code is in the `django` package (`django/utils/deprecation.py:warn_about_external_use`); `warn_about_implementation` names the line where an override is defined; a stack level names the frame that many levels up, and none the warning's own line. [Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](../utils/deprecation.md) tells the helpers and the filters.

Python's default filters show a `DeprecationWarning` only when it names a line of `__main__`, and never a `PendingDeprecationWarning`, so a project's modules show neither; `-Wd` shows each warning once for each line it names. A module of the harbour project runs old habits:

```text
# habits.py, called from main.py run plainly and with -Wd: each habit, its warning, the line named
python main.py
    nothing printed
python -Wd main.py
    from django.utils.deprecation import MiddlewareMixin  RemovedInDjango2029Warning  the habit's line
    from django.core.mail import BadHeaderError           RemovedInDjango2028Warning  django/core/mail/__init__.py, in __getattr__
    Ship.objects.select_related()                         RemovedInDjango2028Warning  the habit's line
    Ship.objects.values_list(flat=True)                   RemovedInDjango2028Warning  django/db/models/query.py, in QuerySet.values_list
    Paginator(range(10), 2, orphans=2)                    RemovedInDjango2028Warning  the habit's line
    urlize("harbour.example.com")                         RemovedInDjango2028Warning  django/utils/html.py, in Urlizer.__call__
```

Three name Django's line: the `__getattr__` of `django.core.mail` and `values_list` give no stack level, and the urlizer's `stacklevel=2` reaches only `Urlizer.__call__`. The development server keeps the option: its autoreloader passes its `-W` options to the serving process (`django/utils/autoreload.py:get_child_arguments`).
