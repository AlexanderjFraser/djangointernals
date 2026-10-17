---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What still warns: the deprecations and the releases that end them

Every deprecation in the code at this commit, by the release that ends it: most of what 6.2 deprecated, warning with `RemovedInDjango2029Warning` until Django 2029, and what 6.0 and 6.1 deprecated, warning with `RemovedInDjango2028Warning` until Django 2028; the code that warns and what it will do then; and which line a warning names, and what a project sees.

The deprecation timeline, `docs/internals/deprecation.txt`, lists what each coming release removes or changes. At this commit each entry but one is code that keeps an old use working, most of it warning; `select_related(True)` fails already, with an `AttributeError` that becomes a `TypeError`. What 5.0, 5.1 and 5.2 deprecated, removed in 6.0 and 6.1, is told by part of the book in [What changed](../changes.md).

A reader who knew 6.1 meets these warnings louder. Under 6.1.1 what 6.0 and 6.1 deprecated warned with RemovedInDjango70Warning, a `PendingDeprecationWarning`, which Python's default filters never show. At this commit, on its way to 6.2, the last feature release before Django 2028, it warns with `RemovedInDjango2028Warning`, a `DeprecationWarning`, which they show when its line is in the script Python runs, as a deprecated setting's can be in manage.py (`django/utils/deprecation.py:RemovedInDjango2028Warning`; [What changed](../changes.md#how-a-change-is-carried) tells the renaming).

The old name RemovedInDjango70Warning gives `RemovedInDjango2028Warning`, with a `UserWarning`, which Python shows wherever it is named; RemovedInDjango71Warning, which no release had, fails to import (`django/utils/deprecation.py:__getattr__`).

Which release ends a deprecation follows from the release that began it (`docs/internals/release-process.txt`); the figure sets each feature release from 5.0 beside the release that removes what it deprecated.

```text figure=deprecation-spans
What each feature release from 5.0 deprecated, from that release to the one that removes it.
LTS: a long-term support release.

   4 December 2023    5.0
   7 August 2024      5.1
   2 April 2025       5.2 LTS
   3 December 2025    6.0
   5 August 2026      6.1
  26 September 2026   this commit: main, a pre-alpha of 6.2, django.VERSION (6, 2, 0, "alpha", 0)
   April 2027         6.2 LTS, expected
                      Django 2028, then Django 2029: calendar versions, under DEP 20

Where what a release deprecated is removed:
  deprecated in 5.0 and 5.1    removed in 6.0
  deprecated in 5.2            removed in 6.1
  deprecated in 6.0 and 6.1    removed in Django 2028    warns RemovedInDjango2028Warning
  deprecated in 6.2            removed in Django 2029    warns RemovedInDjango2029Warning
                               (the readings of django.VERSION that 6.2 deprecated end in Django 2028)
```

*Each bar runs from the release that deprecated a feature to the one that removes it, over an axis of the feature releases from 5.0 to Django 2029; the upright line is this commit. A bar's label is the class its deprecations warn with at this commit, but for the bar of the readings of `django.VERSION`, deprecated in 6.2, which end a release early, in Django 2028.*

## Removed in Django 2029

Most of what 6.2 deprecated warns with `RemovedInDjango2029Warning`. [What changed in handlers, requests, URLs and views](request-cycle.md) tells the first two; [What changed in querysets](querysets.md), [What changed in expressions, lookups and the compiler](sql.md) and [What changed in forms and validators](forms.md) one each.

| deprecated | warns at | in Django 2029 |
|---|---|---|
| `MiddlewareMixin` imported from `django.utils.deprecation` | `django/utils/deprecation.py:__getattr__` | the old path fails; the class is in `django.middleware` |
| `JsonResponse` given `safe=`, true or false | `django/http/response.py:JsonResponse.__init__` | the parameter goes, with the `TypeError` for data not a dict |
| `QuerySet.aiterator` after `QuerySet.prefetch_related` with no chunk size; it takes 2,000 | `django/db/models/query.py:QuerySet.aiterator` | `ValueError`, as `QuerySet.iterator` raises already |
| an `Extract` or `Trunc` with no `tzinfo` deconstructed, as a migration writes it, while `USE_TZ` is true | `django/db/models/functions/datetime.py:TimezoneMixin.deconstruct` | the current time zone captured in migrations |
| `EmailValidator.validate_domain_part` overridden, or called from code Django did not call | `django/core/validators.py:EmailValidator` | removed; `EmailValidator.validate_domain` |

## Removed in Django 2028

What 6.0 and 6.1 deprecated, and the readings of `django.VERSION` deprecated in 6.2, ends in Django 2028; where it warns, it warns with `RemovedInDjango2028Warning`.

### Settings

[What changed in settings, startup and the commands](startup-and-commands.md) tells the first three, and names every email setting of the first. `MAILERS` is the setting that names a project's mail backends by alias.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| the settings in the set `DEPRECATED_EMAIL_SETTINGS`, `EMAIL_BACKEND`, `EMAIL_HOST` and `EMAIL_PORT` among them, set, or read first from outside Django | `django/conf/__init__.py:Settings.__init__`, `django/conf/__init__.py:LazySettings.__getattr__` | removed; `MAILERS` |
| `USE_BLANK_CHOICE_DASH` set | `django/conf/__init__.py:Settings.__init__` | removed; the blank choice's label is `BLANK_CHOICE_LABEL` |
| `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` set | `django/conf/__init__.py:Settings.__init__` | removed; `_unsign_cookie` tries only `_cookie_signer_salt` |
| `URLIZE_ASSUME_HTTPS` set | no warning | removed |

### Mail

A project that configures no mail at all, neither `MAILERS` nor an old email setting, is warned too, when a message goes through the default mailer: Django 2028 has none. [What changed in mail and tasks](mail-and-tasks.md) tells the first ten.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| neither `MAILERS` nor an email setting, as the default mailer is made | `django/core/mail/deprecation.py:warn_about_default_mailers_if_needed` | no default mailer; sending fails without `MAILERS` |
| fail_silently and later arguments of `send_mail`, `send_mass_mail`, `mail_admins`, `mail_managers` and `django.core.mail.get_connection`, and all but the first four of `EmailMessage` and `EmailMultiAlternatives`, by position | `django/utils/deprecation.py:deprecate_posargs` | `TypeError`; keyword arguments |
| `django.core.mail.get_connection` called from outside Django | `django/core/mail/__init__.py:get_connection` | removed; backends come from `mailers` |
| the arguments connection, fail_silently, auth_user and auth_password, where the sending functions, `EmailMessage` and `EmailMessage.send` take them, and `EmailMessage.connection` | `django/core/mail/__init__.py:send_mail`, `django/core/mail/message.py:EmailMessage` | removed; `using=` names a `MAILERS` alias, and username and password are its `"OPTIONS"` |
| the SMTP `EmailBackend` made outside `mailers` | `django/core/mail/backends/smtp.py:EmailBackend.__init__` | unsupported; `mailers` makes it |
| the argument fail_silently, or a keyword it does not take, passed to `BaseEmailBackend.__init__` outside `mailers`; the attribute fail_silently read where a backend sets none | `django/core/mail/backends/base.py:BaseEmailBackend` | `TypeError` for an unknown keyword; fail_silently a backend's own attribute |
| `AdminEmailHandler` given the argument email_backend | `django/utils/log.py:AdminEmailHandler.__init__` | removed; `using=` names the mailer |
| `ADMINS` or `MANAGERS` as (name, address) pairs, when mail goes to them | `django/core/mail/__init__.py:_send_server_message` | `ImproperlyConfigured`; a list of addresses |
| an `email.mime.base.MIMEBase` attached | `django/core/mail/message.py:EmailMessage.attach` | removed; an `email.message.MIMEPart` |
| `BadHeaderError`, `SafeMIMEText` and `SafeMIMEMultipart` from `django.core.mail`; from `django.core.mail.message`, no warning | `django/core/mail/__init__.py:__getattr__` | removed; `BadHeaderError` is `ValueError` already |
| `forbid_multi_line_headers` and `sanitize_address` | `django/core/mail/message.py` | removed; Python's email API |

### Models, querysets and SQL

Told in [What changed in querysets](querysets.md), [What changed in expressions, lookups and the compiler](sql.md), [What changed in models and fields](models.md), [What changed in forms and validators](forms.md), [What changed in the database backends and migrations](backends-and-migrations.md) and [What changed in the test framework](testing.md).

| deprecated | warns at | in Django 2028 |
|---|---|---|
| `QuerySet.select_related` with no arguments, called from outside Django | `django/db/models/query.py:QuerySet.select_related` | `TypeError`; the fields named |
| `select_related(True)`, which fails with `AttributeError` | no warning | `TypeError` |
| `QuerySet.values_list` with `flat=True` and no field | `django/db/models/query.py:QuerySet.values_list` | `TypeError`; a field named, as `"pk"` |
| an override of `Model.from_db` that takes no argument fetch_mode | `django/db/models/query.py:_get_from_db` | always given fetch_mode |
| a percent sign in an alias | `django/db/models/sql/query.py:Query.check_alias` | `ValueError` |
| `None` as an exact lookup's value on a whole `JSONField`, taken as JSON null | `django/db/models/fields/json.py:JSONExact.process_rhs` | SQL's IS NULL; JSON null is `JSONNull` |
| a field class with a method get_placeholder and no get_placeholder_sql | `django/db/models/fields/__init__.py:Field.__init_subclass__` | only get_placeholder_sql called, not get_placeholder |
| `SQLCompiler.quote_name_unless_alias` | `django/db/models/sql/compiler.py:SQLCompiler.quote_name_unless_alias` | removed; `SQLCompiler.quote_name` |
| `BLANK_CHOICE_DASH` | no warning | removed |
| `django.db.transaction.savepoint` | `django/db/transaction.py:savepoint` | removed; `savepoint_create` |
| `BaseDatabaseCreation.create_test_db` given `serialize=` | `django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db` | the parameter goes |

### Templates, signing, pagination and the version

[What changed in templates](templates.md) tells the first two; [What changed in security: Content Security Policy and signing](security.md) the algorithm; [What changed in caching, files, signals, serialization and pagination](caching-files-signals.md) the orphans; [Django's version: `VersionTuple` and `get_version`](../utils/version.md) the readings of `django.VERSION`.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| `urlize` and `urlizetrunc` linking a bare domain, `URLIZE_ASSUME_HTTPS` false | `django/utils/html.py:Urlizer.handle_word` | `"https://"` assumed |
| two dots in a row in a variable, `{{ port..name }}` | `django/template/base.py:Parser.parse` | `TemplateSyntaxError` |
| `salted_hmac` or `base64_hmac` with no algorithm, which takes `"sha1"` | `django/utils/crypto.py:salted_hmac`, `django/core/signing.py:base64_hmac` | `"sha256"` the default |
| a `Paginator` or `AsyncPaginator` whose orphans are not fewer than its page size | `django/core/paginator.py:BasePaginator.__init__` | `ValueError` |
| `django.VERSION` indexed from its third component, iterated, measured, or compared with three or more components | `django/utils/version.py:VersionTuple._warn` | four components, (year, patch, status, iteration); attributes such as `VersionTuple.feature` |

### The admin and the PostgreSQL aggregates

[What changed in the admin](admin.md) tells the first, third, fourth and fifth; [What changed in the other contrib apps](contrib.md) the last three.

| deprecated | warns at | in Django 2028 |
|---|---|---|
| `ModelAdmin.list_select_related` set to `True` in a subclass | `django/contrib/admin/options.py:ModelAdmin.__init_subclass__` | `ValueError`; `False` or the fields to fetch |
| `ModelAdmin.get_list_select_related` returning `True` | `django/contrib/admin/options.py:ModelAdmin.get_changelist_instance` | the same |
| `ModelAdmin.get_actions` overridden without the argument action_location; at this commit the change form gets no actions | `django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location` | called with action_location |
| `ModelAdmin.get_action_choices` overridden likewise | `django/contrib/admin/options.py:ModelAdmin._get_action_choices_with_action_location` | the same |
| an `Action` unpacked or indexed like the tuple it replaced | `django/contrib/admin/options.py:Action` | removed; the attributes of `Action` |
| `StringAgg` of `django.contrib.postgres.aggregates`, and its delimiter given as a string | `django/contrib/postgres/aggregates/general.py:StringAgg.__init__` | removed; `django.db.models.StringAgg` reads a string as a field |
| `BitAnd`, `BitOr` and `BitXor` of the same module | `django/contrib/postgres/aggregates/general.py` | removed; those of `django.db.models` |
| `OrderableAggMixin` subclassed | `django/contrib/postgres/aggregates/mixins.py:OrderableAggMixin.__init_subclass__` | removed; `Aggregate.allow_order_by` |

## Which line a warning names, and what a project sees

Python's filters judge a warning by the module of the line it names, and by default show a `DeprecationWarning` only when its line is in `__main__`, the script Python runs ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](../utils/deprecation.md) tells the helpers and the filters). Most sites name the code that used the deprecated feature, passing over Django's frames, and `warn_about_external_use` warns not at all when that code is Django's (`django/utils/warnings.py:django_file_prefixes`, `django/utils/deprecation.py:warn_about_external_use`).

A project's module, diary.py, makes seven deprecated calls, which a script, main.py, imports and runs under `python -Wd`; each line gives a call, its warning and the line named, "this line" where it is the call's. 6.0.8 and 6.1.1, left out, named the same line for each warning they raised; 5.2.17 raised none:

```text recording=changes
python -Wd main.py, main.py running diary.py's deprecated calls: each call that warns, its warning, and the line the warning names
...
    this commit
        from django.utils.deprecation import MiddlewareMixin      RemovedInDjango2029Warning  diary.py, this line
        from django.core.mail import BadHeaderError               RemovedInDjango2028Warning  django/core/mail/__init__.py, in __getattr__
        class EntryAdmin(ModelAdmin): list_select_related = True  RemovedInDjango2028Warning  diary.py, this line
        Entry.objects.select_related()                            RemovedInDjango2028Warning  diary.py, this line
        Paginator(range(10), 2, orphans=2)                        RemovedInDjango2028Warning  diary.py, this line
        AsyncPaginator(range(10), 2, orphans=2)                   RemovedInDjango2028Warning  django/core/paginator.py, in AsyncPaginator.__init__
        urlize("journal.example.com")                             RemovedInDjango2028Warning  django/utils/html.py, in Urlizer.__call__
```

Of the three that name Django's line, the import from `django.core.mail` does because the module's `__getattr__` warns with no stack level (`django/core/mail/__init__.py:__getattr__`), as `QuerySet.values_list`, `EmailMessage.attach` and others do. The other two warn with a `stacklevel=2` that stops inside Django: in `Urlizer.__call__`, and, for an `AsyncPaginator` but not a `Paginator`, in `AsyncPaginator.__init__` (`django/utils/html.py:Urlizer.handle_word`, `django/core/paginator.py:BasePaginator.__init__`). Without `-Wd` the seven write nothing under any of the four: every line they name is in an imported module.

A deprecated setting's warning can name the script. `Settings.__init__` warns for each of `DEPRECATED_EMAIL_SETTINGS` that the settings module sets, and for `USE_BLANK_CHOICE_DASH` and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK`, at the first frame outside Django (`django/conf/__init__.py:Settings.__init__`), which, when manage.py loads the settings, is manage.py's, run as `__main__`. The settings set `EMAIL_HOST`, and manage.py check runs plainly:

```text recording=changes
python manage.py check, the settings module setting EMAIL_HOST: what Python writes to stderr
    5.2.17       nothing written
    6.0.8        nothing written
    6.1.1        nothing written
    this commit
        manage.py:18: RemovedInDjango2028Warning: The EMAIL_HOST setting is deprecated. Migrate to MAILERS before Django 2028.
          execute_from_command_line(sys.argv)
```

Under 6.1.1 the warning named the same line, as `python -Wd` shows, but as a `PendingDeprecationWarning` it was dropped. `python -m django` shows no warning: its first frame outside Django is the standard library's runpy (`django/__main__.py`).
