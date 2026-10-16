---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in time zones, translation and the utilities

The changes from Django 5.0 to this commit in time zones, localization, translation and the smaller modules of `django/utils/`: `USE_TZ` true by default, pytz, the is_dst argument and the alias utc gone, USE_L10N gone, Uyghur and Haitian Creole added, and what changed in `cached_property`, `Truncator`, `parse_duration`, `import_string` and `django.VERSION`.

Most of what 5.0 changed here ended deprecations that 4.0 began, when Django moved from pytz to the standard library's `zoneinfo` and made localized output the default (`docs/releases/4.0.txt`). What 5.0 removed is an error where it was a module, a name or an argument, with one exception, and is passed over in silence where it was a setting: the settings object takes any upper-case name (`django/conf/__init__.py:Settings.__init__`), and nothing at this commit reads these.

## Time zones: `USE_TZ` and `zoneinfo`

`USE_TZ` has been true by default since 5.0 (`django/conf/global_settings.py`). The project template has written `USE_TZ = True` into a new project's settings since 1.4 (`docs/releases/4.0.txt`), so the change reached the settings that never set it: a settings module written by hand, or `settings.configure` in a script. With it on, `django.utils.timezone.now` is aware, in UTC (`django/utils/timezone.py:now`), and a model's datetime field given a naive value warns and takes it to be in the default zone (`django/db/models/fields/__init__.py:DateTimeField.get_prep_value`). [Time zones](../i18n/time-zones.md) tells the mechanism.

Support for pytz's zones went in 5.0, with USE_DEPRECATED_PYTZ, the transitional setting that had kept it through the 4.x releases. No module of Django imports pytz at this commit. `TIME_ZONE`, and a name given to `django.utils.timezone.activate`, become a `zoneinfo.ZoneInfo`, and a zone given as an object is treated as any `tzinfo`: `make_aware` attaches it with `datetime.datetime.replace` (`django/utils/timezone.py:make_aware`). The is_dst argument, which decided the treatment of local times that never happen or happen twice (`docs/releases/3.0.txt`), went from `make_aware`, `QuerySet.datetimes`, `Trunc` and the truncations by unit; for `make_aware`, which only attaches the zone, a `zoneinfo.ZoneInfo` takes such a time's offset from the value's `datetime.datetime.fold`. The alias utc of `datetime.timezone.utc` went from `django.utils.timezone` too.

A run, with settings that set USE_L10N = False and USE_DEPRECATED_PYTZ = True and leave `USE_TZ` unset; Sailor and Voyage are models of the harbour project the ORM chapters use, with a datetime field and a date field:

```text
# a run at this commit, every warning shown
settings.USE_TZ                          True
timezone.now().tzinfo                    datetime.timezone.utc
Sailor.objects.filter(signed_on__lt=datetime(2026, 3, 29, 11, 30)).count()
    0
    warns RuntimeWarning: DateTimeField Sailor.signed_on received a naive datetime (2026-03-29 11:30:00) while time zone support is active.
timezone.make_aware(datetime(2026, 10, 25, 2, 30), is_dst=True)
    TypeError: make_aware() got an unexpected keyword argument 'is_dst'
Sailor.objects.datetimes("signed_on", "day", is_dst=True)
    TypeError: QuerySet.datetimes() got an unexpected keyword argument 'is_dst'
TruncDay("sailed", is_dst=True): the same SQL as without
    True
```

> **Trap.** A truncation still takes is_dst without complaint. `TruncBase.__init__` passes on the keywords it does not name, and `Func` keeps them as extra values for its SQL template, which a truncation's SQL does not use (`django/db/models/functions/datetime.py:TruncBase.__init__`, `django/db/models/expressions.py:Func.__init__`).

## Localization: no USE_L10N

USE_L10N, the setting that switched localized formats on, was deprecated in 4.0, which made its default true, and removed in 5.0; the 4.0 notes give the consequence, that by default any date or number Django displays is localized (`docs/releases/4.0.txt`). At this commit `get_format` takes use_l10n=None to mean true, and so do `localize` and the functions under it (`django/utils/formats.py:get_format`). Localization is turned off by a caller, as a template is inside `{% localize off %}`, which sets the context's flag (`django/templatetags/l10n.py:LocalizeNode`). A project that still sets USE_L10N = False is neither refused nor warned. The same run, in Dutch:

```text
# the same run, inside translation.override("nl")
settings.USE_L10N                        False
formats.localize(1234.5)                 '1234,5'
formats.localize(date(2026, 3, 29))      '29 maart 2026'
formats.localize(1234.5, use_l10n=False) '1234.5'
```

[Locale formats: `get_format` and the format modules](../i18n/formats.md) tells how a format is found.

## Languages added

Uyghur, `"ug"`, joined `LANGUAGES` in 5.0, written right to left and so in `LANGUAGES_BIDI`, and Haitian Creole, `"ht"`, in 6.0 (`django/conf/global_settings.py`). The 6.0 notes speak of translations for Haitian Creole, but at this commit Django's tree has a format module for it and no catalogue. With `USE_I18N` on, `check_for_language` asks for a catalogue (`django/utils/translation/trans_real.py:translation_catalog_exists`), so for `"ht"` it is false and `get_supported_language_variant` raises `LookupError`: unless a project or an application provides a catalogue, the language is never chosen from a request's path, cookie or Accept-Language (`django/utils/translation/trans_real.py:get_language_from_request`), and in a run, activated by hand, it left Django's messages in English. The security releases' limits on a language code's length are in [Security fixes: limits against denial of service](security-fixes-limits.md).

## The utilities

The undocumented modules baseconv and datetime_safe went in 5.0, after their deprecation in 4.0, and itercompat, with its is_iterable, deprecated in 5.1, went in 6.0. Importing any of them raises `ModuleNotFoundError`. At this commit signing writes its base 62 with its own `b62_encode` and `b62_decode` (`django/core/signing.py:b62_encode`); the 5.1 notes named `collections.abc.Iterable` in is_iterable's place, which is how the check registry tests a check's result (`django/core/checks/registry.py:CheckRegistry.run_checks`).

| name | what changed | release | told in |
|---|---|---|---|
| `cached_property` | the name argument is gone; the name comes only from `cached_property.__set_name__`, called as the class statement runs | 5.0 | [`cached_property`, `classproperty` and `classonlymethod`](../utils/cached-property.md) |
| `Truncator` | with html=True, for the `truncatechars_html` and `truncatewords_html` filters, parses with subclasses of `html.parser.HTMLParser`, more robust and faster in the notes' words, with small differences in output (`django/utils/text.py:TruncateHTMLParser`) | 5.1 | [Text helpers: `Truncator` and `django/utils/text.py`](../utils/text.md) |
| `SafeString.__add__` and `format_html_join` | told with the templates' safe strings | 5.2 | [What changed in templates](templates.md) |
| `parse_duration` | reads ISO 8601's weeks, alone or before days and a time: in a run `"P1W2DT3H"` was nine days and three hours (`django/utils/dateparse.py:iso8601_duration_re`) | 6.1 | [Dates, durations and addresses: `parse_datetime`, `parse_duration` and `clean_ipv6_address`](../utils/parsing.md) |
| `import_string` | imports the whole path as a module first, so it returns a top-level module, and for a longer path a submodule rather than its package's attribute of the same name, unless the package itself rebinds the name after importing the submodule (`django/utils/module_loading.py:import_string`) | 6.2 | [Importing by name: `import_string` and `autodiscover_modules`](../utils/importing.md) |
| `django.VERSION` | a `VersionTuple`: an index or slice past its second part, its length, unpacking, or a comparison with three parts or more warns with `RemovedInDjango2028Warning`, the class once named for 7.0 (`django/utils/version.py:VersionTuple`) | 6.2 | [Django's version: `VersionTuple` and `get_version`](../utils/version.md) |
