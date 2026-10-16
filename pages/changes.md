---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Django in time
contents: startup-and-commands, request-cycle, models, querysets, sql, backends-and-migrations, templates, forms, security, i18n-and-utils, mail-and-tasks, caching-files-signals, auth, admin, contrib, testing, security-fixes-sql, security-fixes-exposure, security-fixes-limits, requirements, deprecations
---

# What changed

What a reader who learnt Django from an earlier release may believe that is no longer true: the changes from Django 5.0 to this commit that alter how the code works, where each now lives in the source, and what the code still carries for the releases that will remove it.

Every other chapter describes the code at one commit, on Django's main branch on its way to 6.2, and mentions what the code used to do only in a note, where an older belief would mislead. This chapter gathers the older beliefs. Its sections follow the parts of the book. Each gives a change, the release that made it, the place in the source where the code now does what it does, and a link to the page that tells the mechanism as it now stands.

## An old habit at this commit

A change can meet old code in three ways. A default that changed is not announced: the code that relied on the old value runs on and does something else. A deprecated feature ordinarily goes on working and raises a warning whose class names the release that will remove it, though a few raise nothing. A removed feature is ordinarily an error, though not always: an override of a method that Django no longer calls is simply not called, and a removed setting, like a few removed arguments, is still taken and ignored. This script runs a few habits of older Django against this commit; Ship is a model of the harbour project that the ORM chapters use ([Models and fields](models.md)).

```text
# old_habits.py at this commit, every warning shown; its settings set neither USE_TZ nor
# DEFAULT_AUTO_FIELD (an error's message is shown without its file's path)
settings.USE_TZ                                       True
Ship._meta.pk                                         <django.db.models.fields.BigAutoField: id>
JsonResponse([1, 2]).content                          b'[1, 2]'
django.VERSION[:3]                                    (6, 2, 0), warns RemovedInDjango2028Warning
from django.utils.deprecation import MiddlewareMixin  warns RemovedInDjango2029Warning
Ship.objects.select_related()                         warns RemovedInDjango2028Warning
salted_hmac("harbour", "Endeavour")                   warns RemovedInDjango2028Warning
Meta.index_together = [("quay", "number")]            TypeError: 'class Meta' got invalid attribute(s): index_together
from django.utils.timezone import utc                 ImportError: cannot import name 'utc' from 'django.utils.timezone'
```

The first three lines changed without a word. `USE_TZ` has been true by default since 5.0, so a project that never set it now works with aware datetimes; `DEFAULT_AUTO_FIELD` has named `BigAutoField` since 6.0, so a model with no primary key of its own, in an application that names no other, gets a 64-bit one (`django/conf/global_settings.py`); and since 6.2 `JsonResponse` serialises a list without being told that it is safe (`django/http/response.py:JsonResponse.__init__`). The next four still work and warn: a slice of `django.VERSION` that reaches its third part, `MiddlewareMixin` from its old module, `select_related` with no arguments, and `salted_hmac` with no algorithm. The last two are gone: the `Meta` option index_together was removed in 5.1, and the alias utc in 5.0.

## The releases

Django makes a feature release about every eight months, and the third of each series is a long-term support release, which receives security fixes for a guaranteed period, typically three years (`docs/internals/release-process.txt`). 5.0 came on 4 December 2023, 5.1 on 7 August 2024, 5.2 on 2 April 2025, 6.0 on 3 December 2025 and 6.1 on 5 August 2026 (`docs/releases/`). This commit is main on 26 September 2026, a pre-alpha of 6.2, and `django.VERSION` is `(6, 2, 0, "alpha", 0)`; 6.2 is expected in April 2027 and will be the next long-term release. Following DEP 20, the releases after it, once planned as 7.0 and 7.1, are Django 2028 and Django 2029, calendar versions with no minor number (`docs/releases/6.2.txt`; [Django's version: `VersionTuple` and `get_version`](utils/version.md)).

```text figure=the-releases
Feature releases from 5.0 to this commit, and those that follow. LTS: a long-term support release.

   4 December 2023    5.0
   7 August 2024      5.1
   2 April 2025       5.2 LTS     security fixes until April 2028
   3 December 2025    6.0
   5 August 2026      6.1         mainstream support expected until April 2027, extended until December 2027
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

*The feature releases from 5.0 to the one this commit is on its way to, and the two after it. What a release deprecates is removed in the first release of the next series, or in its second when the release was the last of its series, so that a deprecation ordinarily spans at least two feature releases; the readings of `django.VERSION`, whose shape changes in Django 2028, are the exception.*

Between feature releases come patch releases, numbered with a third part. A fix for a critical bug in the newest feature release, a crash, a regression, a major fault in a new feature, goes to that release's branch as well as to main; a fix for a security issue or for the loss of data goes to main, to the last two feature releases and to any long-term release still supported (`docs/internals/release-process.txt`). Most of the patch releases since 5.0 carry security fixes. Many of those tighten the code in ways a project can notice, a value refused, a header added, a character no longer allowed in an alias, and the chapter gathers them by kind: [Security fixes: SQL injection](changes/security-fixes-sql.md), [Security fixes: disclosure, spoofing and privilege](changes/security-fixes-exposure.md) and [Security fixes: limits against denial of service](changes/security-fixes-limits.md).

## How a change is carried

A feature release may change behaviour outright, and its notes list each such change as backwards incompatible; the release process allows these where a path through deprecation is not possible or not worth its cost (`docs/internals/release-process.txt`). The ordinary path is **deprecation**: the old behaviour stays and raises a warning, for at least two feature releases, and is then removed. The warning classes are named for the release that removes what they mark: `RemovedInDjango2028Warning`, a `DeprecationWarning`, for what 6.0 and 6.1 deprecated, and `RemovedInDjango2029Warning`, a `PendingDeprecationWarning`, for what 6.2 deprecated, except the readings of `django.VERSION`, which warn with the first. Python's default filters show the first only when it is attributed to the module `__main__`, and never show the second ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](utils/deprecation.md)).

To keep an old use working, the code has to recognise it, and it does so in a few recurring ways. A name that moved is answered by a module's `__getattr__`, as `MiddlewareMixin` is in its old module (`django/utils/deprecation.py:__getattr__`). A parameter made keyword-only takes its old position for the period through `deprecate_posargs` (`django/utils/deprecation.py:deprecate_posargs`). An override written for the old signature is found by inspecting it: a model's own `from_db` that accepts neither `fetch_mode` nor arbitrary keywords is called without the mode, with a warning (`django/db/models/query.py:_get_from_db`). A class that defines an old hook is caught as it is made, in `__init_subclass__`, as a field class that defines the old placeholder method is (`django/db/models/fields/__init__.py:Field.__init_subclass__`). And a value of the old kind is caught where it is used, as `select_related` is when a caller outside Django gives it nothing. [What still warns: the deprecations and the releases that end them](changes/deprecations.md) lists the deprecations at this commit, each with the place in the code that warns, or, for the few that raise nothing, the place that will change.

Some deprecations need a **transitional setting**, which lets a project take the new behaviour early or keep the old one for a time, and which goes with the deprecation it serves. These are the ones at this commit (`django/conf/global_settings.py`). `URLIZE_ASSUME_HTTPS`, from 6.0, makes `urlize` assume `"https"` for the bare domains it links, a name beginning with www. or ending in .com, .org or one of five others, before Django 2028 makes that the default (`django/utils/html.py:Urlizer.handle_word`). `USE_BLANK_CHOICE_DASH`, from 6.1, brings back the dashes that the blank choice of a model field's choices and of a `ModelChoiceField` used to show (`django/db/models/utils.py:get_blank_choice_label`). `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` came with a fix to the salts of signed cookies in 5.2.15 and 6.0.6, and when true lets a signed cookie made under the old salt be read; its default became false in 6.1 (`django/core/signing.py:_unsign_cookie`). Setting either of the last two warns: in a settings module always, and through `configure` or an override when the code that sets it is outside Django (`django/conf/__init__.py:Settings.__init__`, `django/conf/__init__.py:_show_settings_deprecation_warning`; [What changed in settings, startup and the commands](changes/startup-and-commands.md)).

## What changed, in outline

The changes from 5.0 to this commit are not spread evenly. Some parts of Django changed their model; most gained a feature or two and lost what an earlier release had deprecated. The larger movements:

**The database does more of the work.** A field may have a default that the database supplies, `Field.db_default` (5.0), or be a column the database generates, `GeneratedField` (5.0), which since 6.0 a save reads back with the statement's `"RETURNING"` clause where the backend has one (`django/db/models/fields/generated.py:GeneratedField`, `django/db/models/base.py:Model._save_table`). A primary key may span several columns, `CompositePrimaryKey` (5.2). An `on_delete` may leave the work to the database's own `ON DELETE` clause, with `DB_CASCADE`, `DB_SET_NULL` or `DB_SET_DEFAULT` (6.1), and the collector of a delete then passes over the relation (`django/db/models/deletion.py:DatabaseOnDelete`). PostgreSQL connections can come from a pool since 5.1, and Oracle's since 5.2. [What changed in models and fields](changes/models.md) and [What changed in the database backends and migrations](changes/backends-and-migrations.md) have the rest.

**Fetching on demand is a choice.** Reading a field or a related object that a queryset did not load used to run one query for that one instance. Since 6.1 that is one of three **fetch modes**, `FETCH_ONE`, beside `FETCH_PEERS`, which fetches it at once for the other instances that the same run of the queryset made, and `FETCH_RAISE`, which refuses (`django/db/models/fetch_modes.py`; [Deferred fields and fetch modes in a queryset](querysets/deferred.md)). With them `select_related` with no arguments, which follows the relations that cannot be null, is deprecated. [What changed in querysets](changes/querysets.md) tells it.

**Services are configured by alias.** `TASKS` (6.0) and `MAILERS` (6.1) are dictionaries of named backends, as `CACHES`, `DATABASES` and `STORAGES` were already, and the settings that configured a single backend before them are deprecated or gone: the single storage's settings went in 5.1, and `EMAIL_BACKEND` and the email settings beside it go in Django 2028. Until then `mailers["default"]` is built from `EMAIL_BACKEND` when a project does not define `MAILERS` (`django/core/mail/handler.py:MailersHandler.create_connection`). [What changed in mail and tasks](changes/mail-and-tasks.md) tells it.

**New machinery.** Background tasks, `django.tasks` (6.0): a task is defined, and enqueuing it on a backend returns a `TaskResult`; of the two backends Django ships, `ImmediateBackend` runs the task at once and `DummyBackend` only stores the result, both meant chiefly for development and tests, and running tasks in production is left to a backend and a worker outside Django ([Background tasks: `Task`, `TaskResult` and the task backends](services/tasks.md)). Content Security Policy, with `ContentSecurityPolicyMiddleware` and a nonce for each request (6.0; [Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](security/csp.md)). Template partials, named fragments of a template (6.0; [Template partials: `{% partialdef %}` and `{% partial %}`](templates/partials.md)). The `{% querystring %}` tag (5.1). `LoginRequiredMiddleware`, which requires a login for every view not marked as exempt (5.1; [Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](auth/requiring-login.md)). A form field drawn with its label, help and errors by one template, `RenderableFieldMixin.as_field_group` (5.0). And email built on Python's modern email API, where `EmailMessage.message` returns an `email.message.EmailMessage` (6.0).

**Asynchronous code, and a step back.** Release after release added coroutine twins, named with a leading a: the authentication functions such as `aauthenticate` (5.0), the session store's methods (5.1), the authentication backends' (5.2), `Signal.asend` (5.0), the test client's `ClientMixin.alogin` and the others (5.0); and 6.0 added `AsyncPaginator`, a paginator whose methods are coroutines. Then 6.2 made most of Django's own middleware set `async_capable = False`, so that under ASGI a chain of Django's own middleware runs together on one thread, around a centre that stays on the event loop, instead of crossing into a thread and back for each hook ([Sync and async in one chain](handlers/async.md)).

**Safer defaults.** Aware datetimes (5.0), 64-bit automatic keys (6.0), `"https"` as the scheme a form's URL field assumes (6.0; `django/forms/fields.py:URLField`) and the urlize filter will assume (Django 2028), SHA-256 as `salted_hmac`'s default algorithm (Django 2028), and an iteration count for the PBKDF2 password hasher raised in every feature release, from 720,000 in 5.0 to 1,800,000 at this commit (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher`).

## Where the changes are told

The sections take the parts of the book in its order, from settings and the commands to the test framework, and each links into the chapters of its part. The security fixes cut across the parts and are grouped by kind. [The versions Django needs: Python, databases and libraries](changes/requirements.md) gives the oldest Python, database and library that each release supports. The last section, [What still warns: the deprecations and the releases that end them](changes/deprecations.md), looks forward: what the code at this commit still carries, by the release that will take it out.
