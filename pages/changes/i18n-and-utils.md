---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in time zones, translation and the utilities

The changes from Django 5.0 to this commit in time zones, localization, translation and the smaller modules of `django/utils/`: the functions `import_string` and `parse_duration`, `django.VERSION`, the module itercompat, Haitian Creole, the setting `USE_TZ`, pytz and is_dst, the alias utc and the setting USE_L10N.

What the 6.x releases changed here is local. `import_string` returns a module where it raised, and no longer lets earlier imports decide between a submodule and its package's attribute (6.2); `parse_duration` reads weeks (6.1); 6.0 removed the module itercompat and listed Haitian Creole; and 6.2 deprecated reading `django.VERSION` past its second number, since the calendar versions from Django 2028 have no minor number ([Django's version: `VersionTuple` and `get_version`](../utils/version.md)).

The larger changes came in 5.0, which ended what 4.0 had begun: datetimes are aware unless a project says otherwise, every zone made from a name is the standard library's, and no setting turns localized formats off. The 4.0 notes give the reason for the new defaults of `USE_TZ` and of localization: they follow "good practice" (`docs/releases/4.0.txt`). What 5.0 removed fails where it was a module, a name or an argument, but for the is_dst that a truncation still takes. Where it was a setting, it is passed over in silence: the settings object takes any upper-case name (`django/conf/__init__.py:Settings.__init__`), and nothing at this commit reads the removed settings.

## Time zones: `USE_TZ` and `zoneinfo`

`USE_TZ` has been true by default since 5.0 (`django/conf/global_settings.py`). The project template has written `USE_TZ = True` since 1.4, so the change reached settings that never set it, such as `settings.configure` in a script (`docs/releases/4.0.txt`). With it on, `django.utils.timezone.now` is aware, in UTC (`django/utils/timezone.py:now`), and a datetime field given a naive value warns and takes it to be in the default zone (`django/db/models/fields/__init__.py:DateTimeField.get_prep_value`).

pytz's zones went in 5.0 with USE_DEPRECATED_PYTZ, the transitional setting that had kept them through 4.x (`docs/releases/4.0.txt`, `docs/releases/5.0.txt`), and no module of Django imports pytz at this commit. `TIME_ZONE`, and a name given to `django.utils.timezone.activate`, become a `zoneinfo.ZoneInfo` (`django/utils/timezone.py:get_default_timezone`, `django/utils/timezone.py:activate`), and a zone given as an object, a pytz zone among them, is used as any `datetime.tzinfo` is, never through pytz's localize. The is_dst argument, which chose how a pytz zone read a local time that happens twice or never, went with pytz: `make_aware` and `QuerySet.datetimes` refuse it, and `Trunc` and the truncations by unit take it and ignore it. `make_aware` now only attaches the zone, and a `zoneinfo.ZoneInfo` reads such a time by the value's attribute `datetime.datetime.fold` (`django/utils/timezone.py:make_aware`). The alias utc of `datetime.timezone.utc` went from `django.utils.timezone` in the same release ([Time zones](../i18n/time-zones.md)).

> **Trap.** A truncation still takes is_dst. `TruncBase.__init__` passes on the keywords it does not name, `Func.__init__` keeps them as extra values for its SQL template, and a truncation's SQL reads none of them (`django/db/models/functions/datetime.py:TruncBase.__init__`, `django/db/models/expressions.py:Func.__init__`). Under 5.2.17 and every release since, `TruncDay("arrived", is_dst=True)` is accepted without an error or a warning, where `make_aware` raises `TypeError`.

## Localization: no USE_L10N

USE_L10N, the setting that switched localized formats on, was deprecated in 4.0, which made its default true, and removed in 5.0. At this commit `get_format` takes use_l10n=None to mean true, as `localize` and the functions under it do (`django/utils/formats.py:get_format`). Localization is turned off by a caller, as a template is inside `{% localize off %}` (`django/templatetags/l10n.py:LocalizeNode`). A project that still sets USE_L10N = False is neither refused nor warned, and is localized all the same: under 5.2.17 and every release since, `formats.localize(1234.5)` in Dutch, with the setting overridden to False, gives `"1234,5"` ([Locale formats: `get_format` and the format modules](../i18n/formats.md)).

## The removed modules: baseconv, datetime_safe and itercompat

The undocumented modules baseconv and datetime_safe went in 5.0, after their deprecation in 4.0 (`docs/releases/5.0.txt`). itercompat, with its one function is_iterable, was deprecated in 5.1 and removed in 6.0 (`docs/releases/6.0.txt`). In 5.2.17 the module, django/utils/itercompat.py, raises its deprecation warning inside is_iterable, so a project that imported the function and never called it was told nothing until 6.0 refused the import.

## `import_string` and a module's path

Before 6.2 `import_string` split the path at its last dot, imported the part before it and returned the attribute the part after it named. So a path without a dot failed, as `import_string("json")` does under 6.1.1, and a submodule was found only if something had imported it already, since that import is what sets a submodule on its package. Since 6.2 a path without a dot is imported as a module, and any other path is first imported whole, an `ImportError` passed over, before the attribute is read (`django/utils/module_loading.py:import_string`). Here `import_string` is given a submodule of Django's that nothing has imported; the `ImportError` is the old answer:

```text recording=changes
import_string("django.utils.archive"): a submodule nothing has imported
    5.2.17       ImportError: Module "django.utils" does not define a "archive" attribute/class
    6.0.8        ImportError: Module "django.utils" does not define a "archive" attribute/class
    6.1.1        ImportError: Module "django.utils" does not define a "archive" attribute/class
    this commit  the module django.utils.archive
```

That import of the whole path also changes the answer where a package binds, in its `__init__.py`, the name of a submodule that nothing has imported yet. Here a package almanac binds `tides = "high water"`, and has a submodule tides.py that nothing has imported; the string is the old answer:

```text recording=changes
import_string("almanac.tides"): a submodule, where almanac's __init__.py binds tides = "high water"
    5.2.17       'high water'
    6.0.8        'high water'
    6.1.1        'high water'
    this commit  the module almanac.tides
```

Importing the submodule puts it on the package in the string's place, so the attribute read next is the module; before 6.2 the string came back until something imported the submodule (`docs/releases/6.2.txt`). Where a package imports its submodule itself and then rebinds the name, the rebinding stands, as before, since a submodule is set on its package only when first imported, which here came before the rebinding: unittest's `__init__.py` imports main and binds the name to the class TestProgram, and `import_string("unittest.main")` returns that class under every release from 5.2.17 to this commit ([Importing by name: `import_string` and `autodiscover_modules`](../utils/importing.md)).

## The smaller changes

The rest, by name; `SafeString.__add__` and `format_html_join` (5.2) are told in [What changed in templates](templates.md).

| what | at this commit | release | where |
|---|---|---|---|
| `cached_property` | the name argument is gone; the name comes only from `cached_property.__set_name__` | 5.0 | [`cached_property`, `classproperty` and `classonlymethod`](../utils/cached-property.md) |
| `LANGUAGES` | holds Uyghur, `"ug"`, which `LANGUAGES_BIDI` lists too, and Haitian Creole, `"ht"`, which has a format module and, though the 6.0 notes speak of "support and translations", no catalogue, so a request's path, cookie or header never selects it unless a project or an application provides one (`django/utils/translation/trans_real.py:get_supported_language_variant`) | 5.0, 6.0 | [Choosing a language: `LocaleMiddleware`](../i18n/choosing.md) |
| `Truncator` | with html=True, for the `truncatechars_html` and `truncatewords_html` filters, parses with subclasses of `html.parser.HTMLParser`, "more robust and faster" in the notes, which say the output may differ slightly (`django/utils/text.py:TruncateHTMLParser`) | 5.1 | [Text helpers: `Truncator` and `django/utils/text.py`](../utils/text.md) |
| `parse_duration` | reads ISO 8601's weeks, alone or before days and a time (`django/utils/dateparse.py:iso8601_duration_re`): `"P1W2DT3H"` gives `None` under 6.0.8, and nine days and three hours from 6.1.1 | 6.1 | [Dates, durations and addresses: `parse_datetime`, `parse_duration` and `clean_ipv6_address`](../utils/parsing.md) |
| `django.VERSION` | a `VersionTuple`, whose readings past its second number or by its length warn with `RemovedInDjango2028Warning`: `django.VERSION[:3]` warns at this commit, and did not under 6.1.1 | 6.2 | [Django's version: `VersionTuple` and `get_version`](../utils/version.md) |
