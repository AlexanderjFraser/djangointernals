---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Django's version: `VersionTuple` and `get_version`

`django.VERSION` is a `VersionTuple`, a tuple that names its parts and warns about the readings that will change meaning when Django's versions become calendar versions, and `django.__version__` is the string that `get_version` makes from it. Beside them, `django/utils/version.py` has `get_docs_version`, `get_version_tuple` and the constants `PY310` to `PY315`.

`django/__init__.py` makes `VERSION`, `(6, 2, 0, "alpha", 0)` at the pin, and computes `__version__` from it on import (`django/__init__.py:VERSION`). The command `django-admin version`, the development server's banner, a migration's header and a new project's settings print the string.

## Two forms of a version

Following DEP 20, the releases from Django 2028, the one that was to be 7.0, are calendar versions, numbered by a year and a patch number (2028.1) with no minor number (`docs/releases/6.2.txt`). `VERSION` holds the numbers as printed, then the status (`"alpha"`, `"beta"`, `"rc"` or `"final"`) and its iteration: five parts for 6.2.1, four for 2028.1. A comment on `_validate_version` says that keeping the numbers as printed is what makes `django.VERSION >= (2028, 3)` mean what it looks like; the function checks the length and the status with `assert` (`django/utils/version.py:_validate_version`).

The two forms agree from the right. `VersionTuple.patch`, `VersionTuple.status` and `VersionTuple.iteration` are the third, second and last parts from the end, and `VersionTuple.feature`, the numbers that name a feature release, is everything before them (`django/utils/version.py:VersionTuple`).

```text figure=two-schemes
                      feature             patch    status     iteration
6.2.1    VERSION = (  6,       2,         1,       "final",   0  )
                      [0]      [1]        [2]      [3]        [4]
2028.1   VERSION = (  2028,               1,       "final",   0  )
                      [0]                 [1]      [2]        [3]

VERSION[2]   1 under the first form, "final" under the second
```

*The two forms of django.VERSION aligned from the right: the attributes read the same parts in both, while the third part from the left is the patch number of 6.2.1 and the status of 2028.1.*

`VersionTuple` is a `tuple` with empty `__slots__`, made from its parts one by one. A subclass of `tuple` is copied and pickled by handing the whole tuple to its constructor as one argument, which the validation refuses, so `VersionTuple.__getnewargs__` hands over the parts, and `copy.copy` and `pickle` give back a `VersionTuple` (`django/utils/version.py:VersionTuple.__getnewargs__`). A class that defines `__eq__` without `__hash__` is unhashable; `VersionTuple` assigns the tuple's `__hash__`.

## The deprecations of 6.2

Without the minor number every later part moves down an index, so 6.2 deprecates each reading that depends on position or length: indexing the third part or later, a negative index included (even `VERSION[-1]`, the iteration in both forms, warns), a slice that reaches the third part, iterating or unpacking, `len`, and comparing with a tuple of three parts or more (`django/utils/version.py:VersionTuple.__getitem__`, `django/utils/version.py:VersionTuple._warn_comparison`). A comparison with one or two parts does not warn, nor do `in` and `repr`, which the class leaves to the tuple.

Each goes through `VersionTuple._warn`, which returns at once for a version of four parts and otherwise calls `warn_about_external_use` with `RemovedInDjango2028Warning` (`django/utils/version.py:VersionTuple._warn`). Its `skip_name_prefixes="django.utils.version.VersionTuple"` passes over the class's own methods, so the warning is attributed to the code that read the tuple, and is not raised when that code is Django's: `get_version` unpacks the tuple in silence ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](deprecation.md)).

```text
# a run in a script, django.VERSION being (6, 2, 0, "alpha", 0)
django.VERSION >= (6, 2)              True
"alpha" in django.VERSION             True
django.VERSION[2]                     0        RemovedInDjango2028Warning
django.VERSION[-1]                    0        RemovedInDjango2028Warning
len(django.VERSION)                   5        RemovedInDjango2028Warning
django.VERSION >= (6, 2, 0)           True     RemovedInDjango2028Warning
major, minor, *rest = django.VERSION           RemovedInDjango2028Warning
VersionTuple(2028, 1, "final", 0)[2]  'final'

the first message:
  Indexing django.VERSION from its third component on is deprecated.
  django.VERSION has four components from Django 2028, (year, patch, status,
  iteration), as calendar versions have no minor component. Use `.feature`,
  `.patch`, `.status`, and `.iteration` attributes instead.
```

## `get_version` and the strings made from a version

`get_version` makes a PEP 440 string (`django/utils/version.py:get_version`). `get_main_version` joins the numbers before the status, the last left out if it is zero: `"6.2"` for `(6, 2, 0, "alpha", 0)`, `"2028"` for `(2028, 0, "final", 0)` (`django/utils/version.py:get_main_version`). A suffix follows. An alpha of iteration 0, a pre-alpha in the code's comment, as at the pin, takes `".dev"` and what `get_git_changeset` returns; another alpha, a beta or a release candidate takes `"a"`, `"b"` or `"rc"` and the iteration; a final release takes nothing.

`get_git_changeset` runs `git log` in the directory of the `django` package, so git reads whatever repository holds that directory, and formats the time of its checked-out commit in UTC, year to second. Where the output is not a number, as without git or outside a repository, it returns `None` and the suffix is left off; `functools.lru_cache` keeps it to one run a process (`django/utils/version.py:get_git_changeset`). A pre-alpha's version thus changes with each commit, and a pickled model instance, which carries `django.__version__`, warns when unpickled under another (`django/db/models/base.py:Model.__setstate__`).

`get_docs_version` gives `"dev"` for a version that is not final and otherwise the feature numbers, since, a comment says, documentation is published per feature release (`django/utils/version.py:get_docs_version`). It goes into the links to docs.djangoproject.com in Django's messages, such as the development server's warning and the page shown when no URLs are configured (`django/views/debug.py:default_urlconf`).

```text
# a run: versions made by hand      get_version              get_docs_version
VersionTuple(6, 2, 0, "alpha", 0)   '6.2.dev20260926051415'  'dev'
VersionTuple(6, 2, 0, "beta", 1)    '6.2b1'                  'dev'
VersionTuple(6, 2, 1, "final", 0)   '6.2.1'                  '6.2'
VersionTuple(2028, 0, "final", 0)   '2028'                   '2028'
VersionTuple(2028, 1, "final", 0)   '2028.1'                 '2028'
```

## `get_version_tuple` and the Python constants

`get_version_tuple` reads another program's version string as numbers, stopping at the first part that is not one: `get_version_tuple("3.2.0b1")` is `(3, 2, 0)` (`django/utils/version.py:get_version_tuple`). Django reads with it the versions of the psycopg and oracledb drivers, GEOS, SpatiaLite, PostGIS and Watchman (`django/db/backends/postgresql/base.py:psycopg_version`).

`PYPY` and `PY310` to `PY315` are booleans set at import, `PY314` meaning Python 3.14 or later. Comments call them a private, stable API, and keep each version's constant as long as the oldest supported Django supports that Python (`django/utils/version.py`). Django chooses code by them where Python changed: `django/utils/copy.py` is `copy.replace` from 3.13 and its own backport on 3.12, for the migration operations copied with changes ([Operations: the base class and its two halves](../migrations/operations.md)), and `PY314` and `PY315` choose how `django/utils/inspect.py` asks for a signature ([Asking a callable what it accepts: `django/utils/inspect.py`](inspect.md)).
