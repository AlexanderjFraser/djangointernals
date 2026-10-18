---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Applications and tools
contents: "The history: first-decade, second-decade; By part of the book: startup-and-commands, request-cycle, models, querysets, sql, backends-and-migrations, templates, forms, security, i18n-and-utils, mail-and-tasks, caching-files-signals, auth, admin, contrib, geodjango, testing; For looking up: security-fixes-sql, security-fixes-exposure, security-fixes-limits, requirements, deprecations"
---

# What changed

How Django became what it is, from the framework released out of a newsroom in 2005 to this commit, and what a reader who learnt an earlier release must update: the changes from Django 5.0 on, where each now lives in the source, and the old uses the code keeps working until a coming release removes them.

## The releases

Since 1.0 a release numbered A.B has been a **feature release**, and one numbered A.B.C a **patch release** of its series. A fix for a security issue or for the loss of data goes to main, to the last two feature releases and to any **long-term support release** still supported, a feature release given such fixes for at least three years, of which 1.4 was the first (`docs/internals/release-process.txt`, `docs/releases/1.8.txt`).

How often Django releases has twice been set by a **Django Enhancement Proposal**, a DEP, the document in which the project decides a major change ([Where Django came from, and who makes it](introduction/origins.md#django-enhancement-proposals)). DEP 4, written in 2015, set a feature release every eight months, the rhythm since 1.8, and, from 2.0, series of three, X.0, X.1 and X.2, the last its long-term release (`deps:final/0004-release-schedule.rst`). DEP 20, accepted in 2026, ends that rhythm after 6.2: from 2028, one feature release each January, numbered by its year and supported for three years, as only a long-term release was. The releases that were to be 7.0 and 7.1 are Django 2028 and Django 2029 (`deps:accepted/0020-annual-release-cycle.rst`, `docs/releases/6.2.txt`).

This commit is main on 26 September 2026, a pre-alpha of 6.2 (`django/utils/version.py:get_version`); 6.1.1 is the newest release, and 6.2 is expected in April 2027. The figure sets the releases in their years, from the release notes (`docs/releases/`) and, for [0.90](https://www.djangoproject.com/weblog/2005/nov/16/firstrelease/), [0.96](https://www.djangoproject.com/weblog/2007/mar/23/096/) and [1.0](https://www.djangoproject.com/weblog/2008/sep/03/1/), the project's announcements: look for the long-term releases, the two changes of rhythm, and where this commit stands.

```text figure=the-releases
Django's releases, from the first public release to the first calendar versions.
LTS: a long-term support release, given security fixes for at least three years.
From 2.0, every long-term support release is an X.2.

2005   the first public release, in July; 0.90 in November
2006   0.91 in January, 0.95 in July
2007   0.96 in March
2008   1.0 in September
2009   1.1 in July
2010   1.2 in May
2011   1.3 in March
2012   1.4 LTS in March, the first long-term support release
2013   1.5 in February, 1.6 in November
2014   1.7 in September
       from 1.8, a feature release every eight months, the schedule of DEP 4
2015   1.8 LTS in April, 1.9 in December
2016   1.10 in August
2017   1.11 LTS in April, 2.0 in December
2018   2.1 in August
2019   2.2 LTS in April, 3.0 in December
2020   3.1 in August
2021   3.2 LTS in April, 4.0 in December
2022   4.1 in August
2023   4.2 LTS in April, 5.0 in December
2024   5.1 in August
2025   5.2 LTS in April, 6.0 in December
2026   6.1 in August; this commit, on 26 September
2027   6.2 LTS, expected in April
       from 2028, one feature release a year, each supported for three years (DEP 20)
2028   Django 2028, in January
2029   Django 2029, in January

Beside the years, a bracket for each span this chapter tells:
  The first decade: from the first release to 1.8
  The second decade: from 1.9 to 5.0
  The sections by part of the book: from 5.0 to this commit
```

*Every final release but the patch releases, a row a year with its months from January to December. The long-term support releases are boxed, this commit is the accented mark, what is still to come is dashed, and the brackets on the right show what each part of this chapter tells.*

## What changed, in outline

The larger movements since 5.0:

- **The database does more of the work**: a default it supplies, `Field.db_default`, and a column it generates, `GeneratedField` (5.0; `django/db/models/fields/__init__.py:Field`, `django/db/models/fields/generated.py:GeneratedField`); and an `on_delete` that leaves the related rows to the database's own `ON DELETE` clause (6.1; `django/db/models/deletion.py:DatabaseOnDelete`; [What changed in models and fields](changes/models.md)).
- **Fetching on demand is a choice.** Since 6.1, reading a field or a related object a queryset did not load follows a **fetch mode**: a fetch for that instance, as before (`FETCH_ONE`); one for it and its peers, other instances of its model the same run of the queryset made (`FETCH_PEERS`); or a refusal (`FETCH_RAISE`) (`django/db/models/fetch_modes.py`; [What changed in querysets](changes/querysets.md)).
- **Services are configured by alias**: `TASKS` (6.0) and `MAILERS` (6.1) name their backends as `CACHES`, `DATABASES` and `STORAGES` already did, and the email settings `MAILERS` replaces are deprecated (`django/tasks/__init__.py:TaskBackendHandler`, `django/core/mail/handler.py:MailersHandler`; [What changed in mail and tasks](changes/mail-and-tasks.md)).
- **Asynchronous code, and a step back.** Release after release added coroutine twins, such as `aauthenticate` and `Signal.asend` (5.0); then 6.2 made most of Django's own middleware synchronous only (`async_capable = False`), so that under ASGI a chain of it runs in a thread as one call around its centre, which stays on the event loop, instead of crossing into a thread and back for each hook (`django/core/handlers/base.py:BaseHandler.load_middleware`; [Sync and async in one chain](handlers/async.md)).
- **Safer defaults**: time zone support (5.0), 64-bit automatic keys (6.0), `"https"` as the scheme a form's URL field assumes (6.0), and more iterations of the PBKDF2 password hasher in every feature release (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher`).

## How a change is carried

A release can change what old code does in three ways: outright; by a deprecation; and, at a deprecation's end, by a removal.

### An outright change

The release process allows a change outright where a path through deprecation is not possible or not worth its cost (`docs/internals/release-process.txt`). The notes list such changes as backwards incompatible, though not every one: the sections by part meet some that no note lists. A quiet kind is a changed default, where code that relied on the old value runs on and does something else.

### A deprecation

A deprecation is the ordinary path. The old behaviour ordinarily stays for at least two feature releases and warns, some of its warnings only when the use comes from outside Django's own code (`django/utils/deprecation.py:warn_about_external_use`). The warning's class names the release that will end the old behaviour. `RemovedInDjango2028Warning` is a `DeprecationWarning`, which Python shows by default only when the line it names is in the script Python runs; `RemovedInDjango2029Warning` is a `PendingDeprecationWarning`, which Python never shows by default (`django/utils/deprecation.py`). What they were called before 6.2 is told in [What still warns: the deprecations and the releases that end them](changes/deprecations.md).

Under DEP 4, what X.0 or X.1 deprecated goes in the next series' Y.0, and what the long-term X.2 deprecated in Y.1; under DEP 20, what one year's release deprecates goes two releases later. So what 6.0 and 6.1 deprecated ends in the next series' first release, 7.0, which is Django 2028; most of what 6.2 deprecated ends in its second, Django 2029.

Some deprecations come with a **transitional setting**, which lets a project take the new behaviour early or keep the old one for a time: at this commit `URLIZE_ASSUME_HTTPS`, `USE_BLANK_CHOICE_DASH` and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` (`django/conf/global_settings.py`; [What still warns: the deprecations and the releases that end them](changes/deprecations.md#settings)).

### A removal

A removal ends a deprecation, and is ordinarily an error, though not always: a deprecated default simply changes, and an override Django no longer calls, a removed setting or keyword argument may be ignored.

## An old habit, release by release

A **habit** here is a few lines written as an older release taught. The habits below show the three ways, each run under 5.2.17, 6.0.8 and 6.1.1, the newest of each series still supported on this commit's date, and under this commit, with the application journal of [A request, end to end](overview.md) and every setting but the applications, the database, the secret key and the URLconf at the release's default. A line gives what the habit returned or the exception it raised, and then the class of each warning it raised, named once however many times it was raised.

A model that declares no primary key and has no parent, such as journal's Entry, is given one, of the class that `DEFAULT_AUTO_FIELD` names unless its application names another (`django/db/models/options.py:Options._get_default_pk_class`). 6.0 changed the setting's default from `AutoField` to `BigAutoField`, and since then nothing warns (`django/conf/global_settings.py`):

```text recording=changes
Entry._meta.pk: the key of a model that declares none, in an application that names no default
    5.2.17       <django.db.models.fields.AutoField: id>
    6.0.8        <django.db.models.fields.BigAutoField: id>
    6.1.1        <django.db.models.fields.BigAutoField: id>
    this commit  <django.db.models.fields.BigAutoField: id>
```

A project upgraded to 6.0 that never named the class finds each such model's key a `BigAutoField`, and makemigrations writes an `AlterField` for each (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_fields`).

`salted_hmac`, the keyed hash under Django's signing, uses SHA-1 when given no algorithm; 6.1 deprecated that default, which becomes SHA-256 in Django 2028. Django's own calls name their algorithm, so only calls from outside Django warn (`django/utils/crypto.py:salted_hmac`, `django/core/signing.py:Signer.signature`). The warning's class names the release that will remove the old default, 7.0 when 6.1 was made, and Django 2028 since 6.2 renamed it:

```text recording=changes
salted_hmac("journal", "entry").name: the algorithm when none is named
    5.2.17       'hmac-sha1'
    6.0.8        'hmac-sha1'
    6.1.1        'hmac-sha1', warns RemovedInDjango70Warning
    this commit  'hmac-sha1', warns RemovedInDjango2028Warning
```

A public name that moves is answered at its old address for the length of a deprecation. At this commit `MiddlewareMixin`, the base class of nearly all Django's own middleware, lives in `django.middleware`, and its old module's `__getattr__` hands the class to an old import with a warning (`django/utils/deprecation.py:__getattr__`). The line gives the module the class is defined in:

```text recording=changes
from django.utils.deprecation import MiddlewareMixin
    5.2.17       django.utils.deprecation
    6.0.8        django.utils.deprecation
    6.1.1        django.utils.deprecation
    this commit  django.middleware, warns RemovedInDjango2029Warning
```

A removal is final. 5.2 deprecated `login` given no user, which then logged in the request's user, and 6.1 removed the fallback (`docs/releases/5.2.txt`, `django/contrib/auth/__init__.py:login`). The habit's request already has a user, piet; from 6.1 the call fails, in an error that says nothing of the old way:

```text recording=changes
login(request, None), request.user being piet: the user the session is given
    5.2.17       piet, warns RemovedInDjango61Warning
    6.0.8        piet, warns RemovedInDjango61Warning
    6.1.1        AttributeError: 'NoneType' object has no attribute 'get_session_auth_hash'
    this commit  AttributeError: 'NoneType' object has no attribute 'get_session_auth_hash'
```
