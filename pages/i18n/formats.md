---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Locale formats: `get_format` and the format modules

`django.utils.formats.get_format` says how the active language writes a date or a number: it looks a format's name, such as `"DATE_FORMAT"` or `"DECIMAL_SEPARATOR"`, up in the language's format modules, falls back to the setting of that name, and caches the answer. `django.utils.formats.localize` writes a value with what it finds, and `sanitize_separators` reads a typed number back.

A format is data: a locale writes a date by a format string, `"j F Y"` in Dutch, and a number with a decimal separator, a thousands separator and a size of group. Django keeps one set as settings, and a **format module**, a locale's `formats.py`, for most of its locales, and chooses as a value is written, by the language active then. No setting turns this off: a value is localized unless the caller passes `use_l10n=False`, as a template does inside `{% localize off %}`.

## The format settings

`FORMAT_SETTINGS` is the set of names that are formats (`django/utils/formats.py:FORMAT_SETTINGS`). Each is also a setting, with a default (`django/conf/global_settings.py`):

| setting | default | Django's Dutch module |
|---|---|---|
| `DATE_FORMAT` | `"N j, Y"` | `"j F Y"` |
| `DATETIME_FORMAT` | `"N j, Y, P"` | `"j F Y H:i"` |
| `TIME_FORMAT` | `"P"` | `"H:i"` |
| `SHORT_DATE_FORMAT` | `"m/d/Y"` | `"j-n-Y"` |
| `DATE_INPUT_FORMATS` | `"%Y-%m-%d"`, `"%m/%d/%Y"`, … | `"%d-%m-%Y"`, `"%d-%m-%y"`, … |
| `DECIMAL_SEPARATOR` | `"."` | `","` |
| `THOUSAND_SEPARATOR` | `","` | `"."` |
| `NUMBER_GROUPING` | `0` | `3` |
| `FIRST_DAY_OF_WEEK` | `0`, Sunday | `1`, Monday |

*Some of the format settings, beside `django.conf.locale.nl.formats`.*

A display format is written in the letters of `django.utils.dateformat`, an input format for Python's strptime. Beside them stand two settings that are not formats: `USE_THOUSAND_SEPARATOR`, `False`, which lets digits be grouped, and `FORMAT_MODULE_PATH`, `None`, which names a project's own format modules. The JavaScript catalogue sends the browser the same formats ([The language views: `set_language` and `JavaScriptCatalog`](views.md)) (`django/views/i18n.py:get_formats`).

English has a format module too, which repeats the defaults but groups digits by three. So a setting is reached only where the language's modules lack the name, or the caller passes `use_l10n=False`. In a run, a project with `DATE_FORMAT = "Y-m-d"` still wrote 29 March 2026 as `"March 29, 2026"` in English, and `"2026-03-29"` only unlocalized.

## `get_format`

`get_format` takes a format's name, and optionally a language code and `use_l10n=False` (`django/utils/formats.py:get_format`). Without that flag it reads the modules of the language, or of the active one. The cache is asked first, under the name and the language.

Otherwise the first module that defines the name answers. A module answers name by name, so one that sets a single format leaves the rest to the modules after it. When none answers, a name in `FORMAT_SETTINGS` gets its setting, and any other name comes back as it was given, uncached. The `date` filter relies on that: `"SHORT_DATE_FORMAT"` as its argument gives the locale's format, and `"j F Y"`, which names none, is the format itself ([The built-in filters](../templates/filters.md)). Input formats found in a module are copied, and each of `ISO_INPUT_FORMATS` they lack is added at the end, as `"%Y-%m-%d"` is to Dutch dates.

> **Trap.** Anything a format module defines can be reached by name, by the `date` filter's argument too; the documentation warns against putting anything sensitive in one (`docs/topics/i18n/formatting.txt`).

## Finding the modules: `iter_format_modules`

`iter_format_modules` yields a language's modules in the order they are asked (`django/utils/formats.py:iter_format_modules`). It first asks `django.utils.translation.check_for_language`: with `USE_I18N` true, a language for which no locale path holds a `"django"` catalogue, its own or its language's, gets no module, and all its formats are the settings' (`django/utils/translation/trans_real.py:translation_catalog_exists`); with it false, every language passes (`django/utils/translation/trans_null.py:check_for_language`). The locations are each package `FORMAT_MODULE_PATH` names, a string or a list, then `django.conf.locale`. In each it tries the locale `to_locale` makes of the code, `"de_CH"` for `"de-ch"`, then the language alone, `"de"`. Location is the outer loop, so a project's `"de"` comes before Django's `"de_CH"`. An `ImportError` passes a module over in silence, whether it is missing or fails an import of its own.

`get_format_modules` gives the list for a language, the active one by default, and keeps it in `_format_modules_cache` (`django/utils/formats.py:get_format_modules`). The harbour office, with `FORMAT_MODULE_PATH = "harbour.formats"`, gives its Dutch datetimes the weekday and drops the year:

```python
# harbour/formats/nl/formats.py
DATETIME_FORMAT = "l j F, H:i"
```

A run, the test client requesting the page:

```text
# a run of the example, with FORMAT_MODULE_PATH = "harbour.formats"
get_format_modules("nl")          harbour.formats.nl.formats, django.conf.locale.nl.formats
get_format_modules("de-ch")       django.conf.locale.de_CH.formats, django.conf.locale.de.formats
get_format_modules("ht")          none
# in Dutch
get_format("DATETIME_FORMAT")     'l j F, H:i'
get_format("DATE_FORMAT")         'j F Y'
get_format("DATE_INPUT_FORMATS")  ['%d-%m-%Y', '%d-%m-%y', '%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d', '%Y-%m-%d']
get_format("j F Y")               'j F Y'
the arrivals page                 Endeavour: zondag 29 maart, 11:30, 1234,5 t
```

Django has a format module for Haitian Creole, `"ht"`, but at this commit no catalogue, so, with `USE_I18N` true and none from a project or an application, its formats are the settings'.

## The caches and `get_format_lazy`

`_format_cache` and `_format_modules_cache` are module dictionaries, shared by every thread for the process's life. `reset_format_cache` empties both; its docstring says it is primarily for testing, and `localize_settings_changed` calls it when a test overrides a format setting or `USE_THOUSAND_SEPARATOR` ([Overriding settings](../startup/overrides.md)) (`django/test/signals.py:localize_settings_changed`). Not `FORMAT_MODULE_PATH`: in a run, the harbour's `"l j F, H:i"` survived `override_settings(FORMAT_MODULE_PATH=None)` until `reset_format_cache` was called.

`get_format_lazy` is `get_format` made lazy, for a value made at import (`django/utils/formats.py:get_format_lazy`). `DateField.input_formats` and `TimeField.input_formats` are such values (`django/forms/fields.py:DateField`), made once and read in the active language at each parse, so one `DateField` took `"29-03-2026"` in Dutch and refused it in English ([The built-in form fields](../forms/field-types.md)).

## Writing a value

`django.utils.formats.localize` sends a value to the writer for its type (`django/utils/formats.py:localize`). A string comes back first, for speed, as its comment says; a `bool` next, so that it is not treated as the number Python takes it for: with digits grouped in Dutch, `number_format` writes `True` as `"T.rue"`. A number goes to `number_format`; a `datetime.datetime`, tested before the `datetime.date` it is a kind of, to `date_format` with `"DATETIME_FORMAT"`; a date with `"DATE_FORMAT"`; a time to `time_format`. Anything else comes back as it was.

With `use_l10n=False` a number is written by `str` and a date by the setting's format, but the letters still write names in the active language:

```text
# localize in Dutch, with the harbour's format module, then with use_l10n=False
1234.5                         '1234,5'                  '1234.5'
datetime(2026, 3, 29, 11, 30)  'zondag 29 maart, 11:30'  'mrt 29, 2026, 11:30 a.m.'
date(2026, 3, 29)              '29 maart 2026'           'mrt 29, 2026'
```

`number_format` gives the language's `DECIMAL_SEPARATOR`, `NUMBER_GROUPING` and `THOUSAND_SEPARATOR` to `django.utils.numberformat.format`, which groups the digits of a localized value where `USE_THOUSAND_SEPARATOR` is true, and of any value where `force_grouping=True` asks, but never with a grouping of 0 (`django/utils/formats.py:number_format`) (`django/utils/numberformat.py:format`). `date_format` and `time_format` look a format up by name, `"DATE_FORMAT"` or `"TIME_FORMAT"` by default, for `django.utils.dateformat.format` and `django.utils.dateformat.time_format` ([Writing numbers, dates and durations](writing-values.md)). A template prints each value through `localize` ([Rendering: nodes and the render context](../templates/rendering.md)).

## Reading a value back

A localized widget, and every date or time input, writes its value with `localize_input`: a number through `number_format`, a date or time by strftime in a date or time input's own format, else the first of the locale's input formats, `"29-03-2026 11:30:00"` in Dutch ([Widgets: `Widget` and its subclasses](../forms/widgets.md)) (`django/utils/formats.py:localize_input`). For a date or a datetime it first calls `sanitize_strftime_format`, which, where the platform does not pad a year below 1000 to four digits (glibc's does not), rewrites `"%Y"` and its kin with explicit padding (CPython issue 13305) (`django/utils/formats.py:sanitize_strftime_format`).

A localized integer, float or decimal field reads a typed number through `sanitize_separators` (`django/utils/formats.py:sanitize_separators`). It cuts the string at the first decimal separator; only where `USE_THOUSAND_SEPARATOR` is true does it remove the thousands separator, as written and in its NFKD form, so a space stands for a non-breaking one; and it joins the parts with a dot. Where the thousands separator is a dot and the string has one dot not followed by three digits, the dot is kept as the decimal point the visitor likely meant (ticket 22171). In Dutch:

| typed | separators off | separators on |
|---|---|---|
| `"1.234,5"` | `"1.234.5"`, refused | `"1234.5"` |
| `"1.234"` | `"1.234"` | `"1234"` |
| `"1234.5"` | `"1234.5"` | `"1234.5"` |

*`sanitize_separators` in Dutch, `USE_THOUSAND_SEPARATOR` false and true; a localized float or decimal field refused `"1.234.5"`.*

In English with separators on, the comma is the thousands separator: `"1234,5"` became `"12345"`.
