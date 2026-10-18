---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in time zones, translation and the utilities

`USE_TZ` true by default and `zoneinfo` in place of pytz; localization without USE_L10N; itercompat and the other modules gone from `django/utils/`; `import_string` given a module's path; new languages, `parse_duration` and `django.VERSION`.

What the 6.x releases changed here is local. Since 6.2 `import_string` returns a module where it used to raise. Earlier imports no longer decide whether it returns a submodule or its package's attribute of that name. 6.2 also deprecated reading `django.VERSION` past its second number, since the calendar versions from Django 2028 have no minor number ([Django's version: `VersionTuple` and `get_version`](../utils/version.md)). Since 6.1 `parse_duration` reads weeks. 6.0 removed the module itercompat and listed Haitian Creole.

The larger changes came in 5.0, which ended what 4.0 had begun: datetimes are aware unless a project says otherwise, every zone made from a name is the standard library's, and no setting turns localized formats off. The 4.0 notes say the new defaults of `USE_TZ` and of localization follow "good practice" (`docs/releases/4.0.txt`).

A module, a name or an argument that 5.0 removed fails where it is used, except `is_dst=` given to a truncation. A removed setting is passed over in silence: the settings object takes any upper-case name, and nothing at this commit reads the removed settings (`django/conf/__init__.py:Settings.__init__`).

## Time zones: `USE_TZ` and `zoneinfo`

`USE_TZ` has been true by default since 5.0 (`django/conf/global_settings.py`). The project template has written `USE_TZ = True` since 1.4, so the change reached settings that never set it, such as `settings.configure` in a script (`docs/releases/4.0.txt`). With `USE_TZ` on, `django.utils.timezone.now` is aware, in UTC (`django/utils/timezone.py:now`). A datetime field given a naive value then warns, and takes the value to be in the default zone (`django/db/models/fields/__init__.py:DateTimeField.get_prep_value`).

pytz's zones went in 5.0 with USE_DEPRECATED_PYTZ, the transitional setting that had kept them through 4.x (`docs/releases/4.0.txt`, `docs/releases/5.0.txt`). No module of Django imports pytz at this commit. `TIME_ZONE`, and a name given to `django.utils.timezone.activate`, become a `zoneinfo.ZoneInfo` (`django/utils/timezone.py:get_default_timezone`, `django/utils/timezone.py:activate`). A zone given as an object, a pytz zone among them, is used as any `datetime.tzinfo` is, never through pytz's localize. The alias utc of `datetime.timezone.utc` went from `django.utils.timezone` in 5.0 too ([Time zones](../i18n/time-zones.md)).

The argument `is_dst=` went with pytz. It chose how a pytz zone read a local time that happens twice or never. `make_aware` and `QuerySet.datetimes` refuse it. `Trunc` and the truncations by unit take it, and ignore it. `make_aware` now only attaches the zone (`django/utils/timezone.py:make_aware`). A `zoneinfo.ZoneInfo` reads such a time by the value's attribute `datetime.datetime.fold`.

> **Trap.** A truncation still takes `is_dst=`. `TruncBase.__init__` passes on the keywords it does not name, `Func.__init__` keeps them as extra values for its SQL template, and a truncation's SQL reads none of them (`django/db/models/functions/datetime.py:TruncBase.__init__`, `django/db/models/expressions.py:Func.__init__`). Under all four releases `TruncDay("arrived", is_dst=True)` is accepted without an error or a warning, where `make_aware` raises `TypeError`.

## Localization: no USE_L10N

USE_L10N, the setting that switched localized formats on, was removed in 5.0. 4.0 had deprecated it, and made its default true. A project that still sets USE_L10N = False is neither refused nor warned, and is localized all the same. Under all four releases `django.utils.formats.localize(1234.5)` in Dutch gives `"1234,5"` with the setting overridden to False.

At this commit `get_format` takes `use_l10n=None` to mean true, as `localize` and the functions under it do (`django/utils/formats.py:get_format`). A caller turns localization off, as a template does inside `{% localize off %}` (`django/templatetags/l10n.py:LocalizeNode`; [Locale formats: `get_format` and the format modules](../i18n/formats.md)).

## The removed modules: baseconv, datetime_safe and itercompat

The undocumented modules baseconv and datetime_safe went in 5.0, after their deprecation in 4.0 (`docs/releases/5.0.txt`). The module itercompat, with its one function is_iterable, was deprecated in 5.1 and removed in 6.0 (`docs/releases/6.0.txt`). Under 5.2.17 the module warns only when is_iterable is called. So a project that imported the function and never called it was told nothing until 6.0 refused the import.

## `import_string` and a module's path

Since 6.2 `import_string` returns a module where it used to raise. A path without a dot is imported as a module. Any other path is first imported whole, and only then is the attribute read; an `ImportError` from that first import is passed over (`django/utils/module_loading.py:import_string`).

Before 6.2 `import_string` split the path at its last dot, imported the part before it and returned the attribute the part after it named. So a path without a dot failed, as `import_string("json")` does under 6.1.1. A submodule was found only if something had imported it already, since that import is what sets a submodule on its package. For a submodule of Django's that nothing has imported, the `ImportError` is the old answer:

```text recording=changes
import_string("django.utils.archive"): a submodule nothing has imported
    5.2.17       ImportError: Module "django.utils" does not define a "archive" attribute/class
    6.0.8        ImportError: Module "django.utils" does not define a "archive" attribute/class
    6.1.1        ImportError: Module "django.utils" does not define a "archive" attribute/class
    this commit  the module django.utils.archive
```

Importing the whole path also changes the answer where a package's `__init__.py` binds the name of a submodule that nothing has imported yet. A package almanac binds `tides = "high water"` and has a submodule tides.py; the string is the old answer, and the module the new:

```text recording=changes
import_string("almanac.tides"): a submodule, where almanac's __init__.py binds tides = "high water"
    5.2.17       'high water'
    6.0.8        'high water'
    6.1.1        'high water'
    this commit  the module almanac.tides
```

Importing the submodule puts it on the package in the string's place, so the attribute read next is the module. Before 6.2 the answer depended on whether something had imported the submodule yet (`docs/releases/6.2.txt`).

Where a package imports its submodule itself and then rebinds the name, the rebinding stands, as before. A submodule is set on its package only when it is first imported, and here that import came before the rebinding. The package unittest imports main in its `__init__.py` and then binds the name to the class TestProgram. `import_string("unittest.main")` returns that class under all four releases ([Importing by name: `import_string` and `autodiscover_modules`](../utils/importing.md)).

## The smaller changes

The 5.2 changes to `SafeString.__add__` and `format_html_join` are told in [What changed in templates](templates.md). The rest, by name:

| what | change | where |
|---|---|---|
| `cached_property` | Gone in 5.0: its argument `name=`; the name comes only from `cached_property.__set_name__` | [`cached_property`, `classproperty` and `classonlymethod`](../utils/cached-property.md) |
| Uyghur, `"ug"` | New in 5.0: in `LANGUAGES`, and in `LANGUAGES_BIDI` | `django/conf/global_settings.py` |
| Haitian Creole, `"ht"` | New in 6.0: in `LANGUAGES`, with a format module but no catalogue, so a request's path, cookie or header never selects it unless a project or an application provides one; the 6.0 notes speak of "support and translations" | `django/utils/translation/trans_real.py:get_supported_language_variant` |
| `Truncator` | Since 5.1, parses with subclasses of `html.parser.HTMLParser` under `html=True`, which the filters `truncatechars_html` and `truncatewords_html` pass: "more robust and faster", the notes say, though the output may differ slightly | `django/utils/text.py:TruncateHTMLParser` |
| `parse_duration` | Since 6.1, reads ISO 8601's weeks, alone or before days and a time: `"P1W2DT3H"` is nine days and three hours, where 6.0.8 gives `None` | `django/utils/dateparse.py:iso8601_duration_re` |
| `django.VERSION` | Deprecated in 6.2: reading it by its length or past its second number, as `django.VERSION[:3]` does; it is a `VersionTuple`, which warns with `RemovedInDjango2028Warning` | `django/utils/version.py:VersionTuple` |
