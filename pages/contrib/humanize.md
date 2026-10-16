---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Humanize: `naturaltime`, `intcomma` and the other filters

`django.contrib.humanize` is one template library, `"humanize"`, of filters that write a value as a person would say it: `ordinal`, `intcomma`, `intword` and `apnumber` for numbers, and `naturalday` and `naturaltime`, with its `NaturalTimeFormatter`, for dates. Every word they write is looked up in the active language.

The application has no models and no middleware, and `HumanizeConfig` names it and overrides nothing, `AppConfig.ready` included (`django/contrib/humanize/apps.py:HumanizeConfig`). Being installed does two things. The `DjangoTemplates` backend finds the library in the application's templatetags package, so `{% load humanize %}` knows its name ([Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md)); and the application's locale directory joins the catalogues `DjangoTranslation` merges, with the translations of the filters' words (`django/utils/translation/trans_real.py:DjangoTranslation._add_installed_apps_translations`) ([Message catalogues: `DjangoTranslation`](../i18n/catalogues.md)).

Each filter reads its value as the kind it works on; a value it cannot read, a string of letters or `None`, it gives back unchanged, and `intcomma` as text; an infinite float raises `OverflowError` out of the three that read an integer.

| filter | reads the value as | registered with |
|---|---|---|
| `ordinal` | an integer | `is_safe=True` |
| `intcomma` | a decimal, unless it is a float | `is_safe=True` |
| `intword` | an integer | `is_safe=False` |
| `apnumber` | an integer | `is_safe=True` |
| `naturalday` | a date | `expects_localtime=True` |
| `naturaltime` | a datetime | no flag |

`is_safe=True` carries a safe input's safety to the result and creates none (`django/template/base.py:FilterExpression.resolve`) ([Autoescaping and safe strings](../templates/autoescape.md)). A value given back unchanged keeps its own safety, flag or none; the flag matters where a filter makes a new string of a safe input: in a run, `intcomma` of the safe string `"1234<b>"` wrote `"1,234<b>"`, and with the flag taken off `"1,234&lt;b&gt;"`.

## The numbers

`ordinal` chooses a format, "{}st", "{}nd", "{}rd" or "{}th", by `django.utils.translation.pgettext` with a context: "ordinal is 1" for 1, "ordinal 11, 12, 13" when the last two digits are 11 to 13, and otherwise "ordinal 0" to "ordinal 9" by the last digit. Where English needs four messages, a translator has one for each case, and French writes 1 otherwise than 21. A negative number comes back as text. The ordinal is marked safe so that, the comment there says, citing ticket 19988, a translation holding `"<sup>"` or `"<sub>"` is not broken (`django/contrib/humanize/templatetags/humanize.py:ordinal`).

`intcomma`, with its argument use_l10n true, the default, hands the value to `number_format` with `use_l10n=True` and `force_grouping=True`: the active language's separators, grouped whatever `USE_THOUSAND_SEPARATOR` says, unless the language's grouping is 0, as the default settings make it for one with no format module: Afrikaans got "45000" (`django/utils/formats.py:number_format`) ([Writing numbers, dates and durations](../i18n/writing-values.md)). A value that cannot be made a decimal, and any value with the argument false, is written as its text, its leading digits grouped in threes by commas: the code's commas, in every language (`django/contrib/humanize/templatetags/humanize.py:intcomma`).

`intword` gives back a number under a million in absolute value. Otherwise it takes from `intword_converters` the first of a million, a billion and so on to a decillion, then a googol, whose thousandfold exceeds the absolute value, divides by it, and writes the quotient to one place with `floatformat` into a message chosen by `django.utils.translation.ngettext`. The count `ngettext` is given is `round_away_from_one` of the quotient, which rounds any number but 1.0 away from one, 1.2 to 2 and 0.5 to 0, so only a quotient of exactly 1.0 has the count 1; the documentation says this may be wrong for some languages (`django/utils/translation/__init__.py:round_away_from_one`, `docs/ref/contrib/humanize.txt`). The quotient is rounded only as it is written, so 999,999,999 is "1000.0 million"; from a thousand decillions a number is counted in googols, and from a thousand googols it is given back (`django/contrib/humanize/templatetags/humanize.py:intword`).

`apnumber` writes 1 to 9 as words and gives back any other number (`django/contrib/humanize/templatetags/humanize.py:apnumber`).

```text
# a run of the example: {{ v|filter }} in English, then in French; \xa0 is a non-breaking space
ordinal   1          '1st'             '1<sup>er</sup>'
ordinal   21         '21st'            '21<sup>e</sup>'
intcomma  4500.2     '4,500.2'         '4\xa0500,2'
intcomma  "1234abc"  '1,234abc'        '1,234abc'
intword   1000000    '1.0 million'     '1,0\xa0million'
intword   1200000    '1.2 million'     '1,2\xa0millions'
intword   999999999  '1000.0 million'  '1000,0\xa0millions'
intword   10**50     '0.0 googol'      '0,0 gogol'
apnumber  7          'seven'           'sept'
```

## The dates

`naturalday` has `expects_localtime=True`, so in a template an aware datetime is first put in the current time zone, unless time zones are off there or the `|timezone` filter has converted it already ([Time zones](../i18n/time-zones.md)). It keeps the year, month and day, compares them with today, taken in the value's zone or, for a value without one, in local time, and gives "today", "tomorrow" or "yesterday"; any other day goes to the `|date` filter with the argument, or the active language's `DATE_FORMAT` (`django/contrib/humanize/templatetags/humanize.py:naturalday`). In a run at 16:42 in Malta on 16 October, 22:30 UTC on the 15th, half past midnight in Malta, was "today" in a template and "yesterday" inside `{% localtime off %}`.

> **Trap.** The `|date` filter is given the date, not the datetime, so an argument with a time letter fails on any other day: `naturalday:"H:i"` of a datetime five days on raised `TypeError`, "The format for date objects may not contain time-related format specifiers (found 'H')."

`naturaltime` is registered without `expects_localtime=True`: the comment above it says it deals properly with naive and aware datetimes, so the cost of converting is avoided. It hands the value to `NaturalTimeFormatter.string_for`, which compares it with now, taken in UTC for an aware value and naive for a naive one. A difference of a day or more goes to `django.utils.timesince.timesince`, or `timeuntil` for the future, which write up to two adjacent units, set in "%(delta)s ago" or "%(delta)s from now"; a smaller one is written in whole hours, minutes or seconds, the largest unit that fits, and less than a second is "now" (`django/contrib/humanize/templatetags/humanize.py:NaturalTimeFormatter.string_for`).

`NaturalTimeFormatter.time_strings` holds the phrases; `NaturalTimeFormatter.past_substrings` and `NaturalTimeFormatter.future_substrings` hold the units given to timesince in place of its `TIME_STRINGS`, made by `django.utils.translation.npgettext_lazy` with a context, "naturaltime-past" or "naturaltime-future", that sets them apart from each other and from timesince's own ([Translating a message](../i18n/translating.md)). A count and its unit are joined by a non-breaking space, in the English phrases and, by `avoid_wrapping`, in timesince's units; translators' comments ask every language to keep it (`django/utils/html.py:avoid_wrapping`).

```text
# a run of the example
now 2026-10-16T16:42+02:00
naturaltime  now             'now'                      'maintenant'
naturaltime  now - 3 h       '3\xa0hours ago'           'il y a 3\xa0heures'
naturaltime  now - 26 h      '1\xa0day, 2\xa0hours ago' 'il y a 1\xa0jour, 2\xa0heures'
naturaltime  now + 9 days    '1\xa0week, 2\xa0days from now' 'dans 1\xa0semaine, 2\xa0jours'
```

> **Trap.** A `datetime.date` passes the filter's first test, the comment there noting that a datetime is a subclass of date, but `is_aware` then asks it for its offset from UTC, which a date lacks: `naturaltime` of today's date raised `AttributeError` out of the render (`django/utils/timezone.py:is_aware`).
