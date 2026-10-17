---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Django in time
contents: first-decade, second-decade, startup-and-commands, request-cycle, models, querysets, sql, backends-and-migrations, templates, forms, security, i18n-and-utils, mail-and-tasks, caching-files-signals, auth, admin, contrib, testing, security-fixes-sql, security-fixes-exposure, security-fixes-limits, requirements, deprecations
---

# What changed

How Django became what it is, from the framework released out of a newsroom in 2005 to this commit, and what a reader who learnt an earlier release must update: the changes from Django 5.0 on, where each now lives in the source, and what the code still carries for the releases that will remove it.

Every other chapter describes the code at one commit and mentions what the code used to do only in passing; this chapter gathers the rest. Why the code is shaped as it is, the technical decisions in the order they were made, is told in [The first decade: from a newsroom to 1.8](changes/first-decade.md) and [The second decade: from 1.9 to 5.0](changes/second-decade.md). What a reader who learnt an earlier release must update is outlined below, and told in the sections after the histories, by part of the book, each change with its release, the place where the code now does it and the page that tells it. The security fixes are grouped by kind, and the last two sections, [The versions Django needs: Python, databases and libraries](changes/requirements.md) and [What still warns: the deprecations and the releases that end them](changes/deprecations.md), are for looking up.

## The releases

Django was first released in July 2005, from a repository that had until then belonged to World Online, the web department of a newspaper in Lawrence, Kansas, where it was built (`docs/releases/1.0.txt`, `docs/faq/general.txt`; [Where Django came from, and who makes it](introduction/origins.md)). Releases numbered 0.9x followed, from [0.90 in November 2005](https://www.djangoproject.com/weblog/2005/nov/16/firstrelease/) to [0.96 in March 2007](https://www.djangoproject.com/weblog/2007/mar/23/096/), and 1.0, [announced on 3 September 2008](https://www.djangoproject.com/weblog/2008/sep/03/1/), came with a promise of API stability. Since then a release numbered A.B has been a **feature release**, and one numbered A.B.C a **patch release** of its series, issued to fix bugs and security issues (`docs/internals/release-process.txt`).

Since 1.8, in 2015, a feature release has come every eight months, each in April, August or December in turn. DEP 4, written that year, set out that schedule; a **Django Enhancement Proposal**, a DEP, is the design document in which the project proposes a major change and records the decision (`deps:final/0004-release-schedule.rst`; [Where Django came from, and who makes it](introduction/origins.md#django-enhancement-proposals)). Some feature releases are **long-term support releases**, given security and data-loss fixes for at least three years: 1.4 was the first, then 1.8 and 1.11 (`docs/releases/1.8.txt`, `docs/releases/1.11.txt`), and from 2.0, as DEP 4 laid down, a series runs X.0, X.1 and X.2, the last its long-term release. DEP 20, accepted in 2026, ends that rhythm after 6.2. From January 2028 Django makes one feature release a year, numbered by its year, each supported for three years: in its first year with the fixes the newest release receives now, in its next two with security and data-loss fixes alone, so that every release has what only the long-term ones had (`deps:accepted/0020-annual-release-cycle.rst`). The releases that were to be 7.0 and 7.1 are Django 2028 and Django 2029 (`docs/releases/6.2.txt`; [Django's version: `VersionTuple` and `get_version`](utils/version.md)).

This commit is main on 26 September 2026, a pre-alpha of 6.2, which `django.VERSION` writes as an alpha of iteration 0, `(6, 2, 0, "alpha", 0)` (`django/utils/version.py:get_version`); 6.1.1 is the newest release, and 6.2 is expected in April 2027. The figure sets the releases in their years, from their notes and, for 0.90, 0.96 and 1.0, the project's announcements (`docs/releases/`): look for the long-term releases, the change of rhythm at 1.8 and again in 2028, and where this commit stands.

```text figure=the-releases
Django's releases, from the first public release to the first calendar versions.
LTS: a long-term support release, given security fixes for at least three years.
From 2.0, every long-term support release is an X.2.

2005   the first public release, in July; 0.90 in November
2006   0.91 in January, 0.95 in July
2007   0.96 in March
2008   1.0 in September, with the promise of a stable API
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

*Every release but the patch releases, from the first to the second calendar version: a row for each year, its months running from January to December, and each release at the month it came. The long-term support releases are boxed, this commit is the accented mark, and what is still to come is dashed. The brackets on the right show what each part of this chapter tells.*

Between feature releases come the patch releases. A fix for a critical bug in the newest feature release goes to that release's branch as well as to main; a fix for a security issue or for the loss of data goes to main, to the last two feature releases and to any long-term release still supported (`docs/internals/release-process.txt`). The security fixes since 5.0 are gathered by kind: [Security fixes: SQL injection](changes/security-fixes-sql.md), [Security fixes: disclosure, spoofing and privilege](changes/security-fixes-exposure.md) and [Security fixes: limits against denial of service](changes/security-fixes-limits.md).

## What changed, in outline

The changes from 5.0 to this commit are not spread evenly. The larger movements:

- **The database does more of the work.** A field may have a default the database supplies, `Field.db_default`, or be a column the database generates, `GeneratedField` (both 5.0; `django/db/models/fields/__init__.py:Field`, `django/db/models/fields/generated.py:GeneratedField`); a primary key may span several columns, `CompositePrimaryKey` (5.2); an `on_delete` may leave the work to the database's own `ON DELETE` clause, and Django's own cascade, which gathers the rows a delete must take with it, then passes over the relation (6.1; `django/db/models/deletion.py:DatabaseOnDelete`, `django/db/models/deletion.py:Collector.collect`). [What changed in models and fields](changes/models.md) and [What changed in the database backends and migrations](changes/backends-and-migrations.md) have the rest.
- **Fetching on demand is a choice.** Reading a field or a related object that a queryset did not load used to run one query for that one instance. Since 6.1 that is one of three **fetch modes**, `FETCH_ONE`, beside `FETCH_PEERS`, which fetches it at once for other instances the same run of the queryset made, and `FETCH_RAISE`, which refuses (`django/db/models/fetch_modes.py`; [What changed in querysets](changes/querysets.md)).
- **Services are configured by alias.** `TASKS` (6.0) and `MAILERS` (6.1) name their backends as `CACHES`, `DATABASES` and `STORAGES` already did, and the email settings that configured a single backend before `MAILERS` are deprecated ([What changed in mail and tasks](changes/mail-and-tasks.md)).
- **New machinery**: background tasks, of which Django ships the interface and two backends meant chiefly for development and tests (6.0; [Background tasks: `Task`, `TaskResult` and the task backends](services/tasks.md)); Content Security Policy, a response header that limits what a page may load, set by `ContentSecurityPolicyMiddleware` (6.0); template partials, named fragments of a template that a view can render alone (6.0; [Template partials: `{% partialdef %}` and `{% partial %}`](templates/partials.md)); and `LoginRequiredMiddleware`, which requires a login for every view not marked exempt (5.1).
- **Asynchronous code, and a step back.** Release after release added coroutine twins named with a leading a, such as `aauthenticate` and `Signal.asend` (5.0). Then 6.2 stepped back from running Django's own middleware asynchronously: most of it now sets `async_capable = False`, so that under ASGI a chain of it runs together on one thread, around a centre that stays on the event loop, instead of crossing into a thread and back for each hook ([Sync and async in one chain](handlers/async.md)).
- **Safer defaults**: aware datetimes (5.0), 64-bit automatic keys (6.0), `"https"` as the scheme a form's URL field assumes (6.0; `django/forms/fields.py:URLField`), and an iteration count for the PBKDF2 password hasher raised in every feature release, from 720,000 in 5.0 to 1,800,000 at this commit (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher`).

## How a change is carried

A release can change what old code does in three ways. It can change a behaviour outright: its notes list each such change as backwards incompatible, and the release process allows one where a path through deprecation is not possible or not worth its cost (`docs/internals/release-process.txt`). The quietest is a changed default, where the code that relied on the old value runs on and does something else. It can **deprecate** a behaviour, which is the ordinary path: the old behaviour stays, and ordinarily warns, for at least two feature releases. And at the end of a deprecation it removes the behaviour, which is ordinarily an error, though not always: an override of a method that Django no longer calls may simply not be called, and a removed setting is still taken and ignored.

When a deprecation ends follows from when it began. Under DEP 4, what X.0 or X.1 deprecated goes in the next series' Y.0, and what the long-term X.2 deprecated in Y.1; under DEP 20, what one year's release deprecates goes two releases later. So at this commit what 6.0 and 6.1 deprecated ends in Django 2028, and what 6.2 deprecated in Django 2029, except some readings of `django.VERSION`, which end a release early, in Django 2028, the first release whose tuple has no minor number ([What still warns: the deprecations and the releases that end them](changes/deprecations.md) draws the spans). The warning classes are named for the release that ends what they mark: `RemovedInDjango2028Warning` is a `DeprecationWarning` and `RemovedInDjango2029Warning` a `PendingDeprecationWarning`, and they were RemovedInDjango70Warning and RemovedInDjango71Warning until 6.2 renamed them for the calendar versions (`docs/releases/6.2.txt`). Python's default filters show the first only when it is attributed to the module `__main__`, and never show the second, so a warning that a project's own modules cause is hidden until warnings are turned on, as `python -Wd` turns them on ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](utils/deprecation.md)).

To keep an old use working, the code has to recognise it: an old import of `MiddlewareMixin`, by its old module's `__getattr__` (`django/utils/deprecation.py:__getattr__`); an argument in its old position, through `deprecate_posargs` (`django/utils/deprecation.py:deprecate_posargs`); a model's own `from_db` written before 6.1 gave it a fetch mode, by inspecting its signature (`django/db/models/query.py:_get_from_db`); a field class that defines the old hook get_placeholder, as the class is made (`django/db/models/fields/__init__.py:Field.__init_subclass__`).

Some deprecations need a **transitional setting**, which lets a project take the new behaviour early or keep the old one for a time, and goes with the deprecation it serves: at this commit `URLIZE_ASSUME_HTTPS` (6.0), `USE_BLANK_CHOICE_DASH` (6.1) and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK`, which came with a security fix in 5.2.15 and 6.0.6, each told in the section of its part (`django/conf/global_settings.py`). `USE_BLANK_CHOICE_DASH` and `SIGNED_COOKIE_LEGACY_SALT_FALLBACK`, which keep an old behaviour, warn when they are set, and `URLIZE_ASSUME_HTTPS`, which takes the new behaviour early, does not (`django/conf/__init__.py:Settings.__init__`; [What changed in settings, startup and the commands](changes/startup-and-commands.md)).

## An old habit, release by release

The same code, run under the newest release of each series still supported on this commit's date, 5.2.17, 6.0.8 and 6.1.1, and under this commit, shows the three ways: a default changed outright, two deprecations, of a default and of a name, and a removal. Each habit runs with the application journal of [A request, end to end](overview.md), whose one model, Entry, declares no primary key, with every setting but the applications, the database, the secret key and the URLconf at the release's default. A line gives what the habit returned or the exception it raised, and then the class of every warning it raised.

A model that declares no primary key is given one, of the class that `DEFAULT_AUTO_FIELD` names unless its application names another (`django/db/models/options.py:Options._get_default_pk_class`). 6.0 changed the setting's default from `AutoField` to `BigAutoField`, and nothing warns (`django/conf/global_settings.py`):

```text recording=changes
Entry._meta.pk: the key of a model that declares none, in an application that names no default
    5.2.17       <django.db.models.fields.AutoField: id>
    6.0.8        <django.db.models.fields.BigAutoField: id>
    6.1.1        <django.db.models.fields.BigAutoField: id>
    this commit  <django.db.models.fields.BigAutoField: id>
```

A project upgraded to 6.0 that never named the class finds the keys of its existing models changed under them, and makemigrations writes an `AlterField` to `BigAutoField` for each (`django/db/migrations/autodetector.py:MigrationAutodetector.generate_altered_fields`). The 6.0 notes expected few projects to meet it: from 3.2 new projects had named `BigAutoField` themselves ([The second decade: from 1.9 to 5.0](changes/second-decade.md)), and a system check had warned those that named nothing (`docs/releases/6.0.txt`).

A deprecation keeps the old behaviour and adds a warning. `salted_hmac`, the keyed hash under Django's signing, uses SHA-1 when it is given no algorithm; 6.1 deprecated that default, which becomes SHA-256 in Django 2028, and Django's own calls name their algorithm, so only calls from outside Django warn (`django/utils/crypto.py:salted_hmac`, `django/core/signing.py:Signer.signature`):

```text recording=changes
salted_hmac("journal", "entry").name: the algorithm when none is named
    5.2.17       'hmac-sha1'
    6.0.8        'hmac-sha1'
    6.1.1        'hmac-sha1', warns RemovedInDjango70Warning
    this commit  'hmac-sha1', warns RemovedInDjango2028Warning
```

The value is the same under every release. What changes is the warning, from 6.1, and its class, which names the release that will remove the old default: 7.0 when 6.1 was made, Django 2028 since 6.2 renamed it.

A name that moves is answered at its old address for the length of a deprecation. At this commit `MiddlewareMixin`, the base class of nearly all Django's own middleware, lives in `django.middleware`, and its old module hands the class to an old import with a warning (`django/utils/deprecation.py:__getattr__`). The line shows the module the imported class is defined in:

```text recording=changes
from django.utils.deprecation import MiddlewareMixin
    5.2.17       django.utils.deprecation
    6.0.8        django.utils.deprecation
    6.1.1        django.utils.deprecation
    this commit  django.middleware, warns RemovedInDjango2029Warning
```

A removal is final. The model option index_together, which 4.2 deprecated in favour of `indexes`, was removed in 5.1 (`docs/releases/5.1.txt`), and a model that still names it is refused as its class is made, by the check that refuses any option of a model's Meta that Django does not know (`django/db/models/options.py:Options.contribute_to_class`):

```text recording=changes
class Meta: index_together = [("title", "published")]
    5.2.17       TypeError: 'class Meta' got invalid attribute(s): index_together
    6.0.8        TypeError: 'class Meta' got invalid attribute(s): index_together
    6.1.1        TypeError: 'class Meta' got invalid attribute(s): index_together
    this commit  TypeError: 'class Meta' got invalid attribute(s): index_together
```

Each release fails in the same words, and nothing in them says that the option once existed.
