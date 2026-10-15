---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Writing numbers, dates and durations

`django.utils.numberformat.format` writes a number with the separators and grouping it is given; `django.utils.dateformat`, through `DateFormat` and `TimeFormat`, writes a date or a time by a format string of letters, with the names of months and days from `django/utils/dates.py`; and `django.utils.timesince.timesince` and `timeuntil` put the time between two datetimes into words.

These functions choose no format: the separators, the grouping and the format string are their arguments, chosen for the active language by `get_format` and its wrappers ([Locale formats: `get_format` and the format modules](formats.md)). What the language decides inside them is words: the names of months and days, "a.m." and "noon", "hours" and "minutes", each a translation looked up as the value is written.

## Numbers

`django.utils.numberformat.format` takes the number, the decimal separator and, optionally, the places after the point, the grouping and the thousands separator (`django/utils/numberformat.py:format`). It groups the digits only when told to, by `force_grouping=True` or by `USE_THOUSAND_SEPARATOR` unless `use_l10n=False`, and never where the grouping is `0`. `USE_THOUSAND_SEPARATOR` is false by default, so the example's tonnage was "1234,5" in Dutch, with no thousands point.

An `int` neither grouped nor given places comes back at once as a string of itself. Other values become a string of digits: a finite `decimal.Decimal` written out in full, as is a `float` whose `str` has an exponent, and the rest by `str`. A leading minus is set aside, the digits after the point are cut or padded with zeros to the places asked for, and those before it are grouped from the right.

A grouping may be a sequence, the size of each group in turn leftwards from the point: `(3, 2, 0)` is Indian English's, as `NUMBER_GROUPING`'s documentation says (`docs/ref/settings.txt`). Past the sequence's end, or at a `0`, the last size repeats; `-1` stops the grouping.

Two rules guard a `decimal.Decimal`. One less than a unit of the last place asked for (a tenth, where zero places are asked for) is taken as zero, too small, the comment says, to affect any place written; a `float` written without an exponent is not, and keeps its minus. One whose digits and exponent run past 200 is written in scientific notation, its coefficient formatted alone: the comment calls 200 arbitrary, and gives the reason, the memory `"{:f}"` would take to write the number out. A run:

```text
django.utils.numberformat.format: the arguments, and what it returned
1234.5, ",", grouping=3, thousand_sep="."                                   1234,5
1234.5, ",", grouping=3, thousand_sep=".", force_grouping=True              1.234,5
1234567890, ".", grouping=(3, 2, 0), thousand_sep=",", force_grouping=True  1,23,45,67,890
1234.567, ".", decimal_pos=2                                                1234.56
Decimal("-0.0001"), ".", decimal_pos=2                                      0.00
-0.0001, ".", decimal_pos=2                                                 -0.00
Decimal("1234.5e300"), ","                                                  1,2345e+303
```

> **Trap.** Places are cut, not rounded. A caller that wants rounding rounds first, as the `floatformat` filter does, half up ([The built-in filters](../templates/filters.md)) (`django/template/defaultfilters.py:floatformat`).

## Dates and times: `DateFormat` and `TimeFormat`

In a format string of `django.utils.dateformat`, each letter names a method of the formatter. `Formatter.format` splits it with `re_formatchars`, the letters that have a meaning and no backslash before them; it calls the method for each letter and makes its result a string, and copies the text between, dropping each escaping backslash (`django/utils/dateformat.py:Formatter.format`). Any other letter is copied. A word's letters must be escaped, or they are read: `"j de F"` writes the example's first arrival, made local, as "29 29CEST March", and Catalan's `DATE_FORMAT` is `r"j E \d\e Y"`.

`TimeFormat` has the letters of a time of day and four of the zone's, `"e"`, `"O"`, `"T"` and `"Z"`; `DateFormat` subclasses it and adds the rest (`django/utils/dateformat.py:DateFormat`). `django.utils.dateformat.format` writes with a `DateFormat`, and `django.utils.dateformat.time_format`, which `django.utils.formats.time_format` calls, with a `TimeFormat`, so a time's format can hold none of the rest: one raises `AttributeError`. A `datetime.date` is refused the other way: for a letter `TimeFormat` has, `Formatter.format` raises `TypeError`, "The format for date objects may not contain time-related format specifiers (found 'H')."

The zone's letters need a zone, and `TimeFormat.__init__` gives the formatter a zone only for a datetime: an aware value's own, or for a naive one the default time zone, `TIME_ZONE` (`django/utils/dateformat.py:TimeFormat.__init__`). A date gets none, a zone being "not appropriate" to it, and a time none, "against established django policy", as the comment there says. Nor does a datetime the zone's clocks skip or repeat: `_datetime_ambiguous_or_imaginary` compares the zone's offsets at the value's two folds, and where they differ the formatter keeps no zone, even for an aware value whose `fold=1` settles its offset ([Time zones](time-zones.md)). Without a zone those letters write `""`; and `"e"` asks the value itself, so writes `""` for any naive one. A run in the example's settings:

```text
"e|O|T|Z|I", run with TIME_ZONE = "Europe/Amsterdam"
the first arrival, made local: 2026-03-29 11:30+02:00    CEST|+0200|CEST|7200|1
naive 2026-03-29 11:30                                   |+0200|CEST|7200|1
naive 2026-03-29 02:30, which the clocks skip            ||||
aware 2026-10-25 02:30, fold=1, which the clocks repeat  ||||
```

| letter | writes |
|---|---|
| `"f"` | the hour on a 12-hour clock, and the minutes unless they are zero |
| `"P"` | `"f"` and "a.m." or "p.m.", but "midnight" at 00:00 and "noon" at 12:00 |
| `"N"` | the month abbreviated as the Associated Press does |
| `"E"` | the month's alternative name, as some languages write it in a date |
| `"e"` | the name of an aware value's own zone |
| `"O"` | the offset from UTC in hours and minutes |
| `"T"` | the name of the formatter's zone at that moment |
| `"Z"` | the offset from UTC in seconds |
| `"I"` | "1" where the zone is on daylight saving time, else "0" |

*The letters their docstrings call a proprietary extension, and those that need a time zone.*

## The names of months and days

`django/utils/dates.py` holds the words the letters write, as dictionaries of lazy translations made at import: the days of the week, and the months in four sets, `django.utils.dates.MONTHS` for `"F"`, `MONTHS_3` for `"b"` and, title-cased, `"M"`, `MONTHS_AP` for `"N"` and `MONTHS_ALT` for `"E"`. A name is looked up when `Formatter.format` makes it a string, in the language active then ([Lazy translations](lazy.md)). The last two sets have contexts, `"abbrev. month"` and `"alt. month"`, which make `MONTHS_ALT`'s English words, the same as `MONTHS`', messages of their own, for languages that write a month otherwise in a date: Polish translates `"F"`'s March as "Marzec" and `"E"`'s as "marca", and its `DATE_FORMAT` is `"j E Y"`. The comment on `MONTHS_ALT` says only that some locales require it for a long date (`django/utils/dates.py:MONTHS_ALT`).

"a.m.", "p.m.", "midnight" and "noon" are messages `TimeFormat` translates as it writes them: in German, `"P"` writes the first arrival, made local, as "11:30 vorm." (`django/utils/dateformat.py:TimeFormat.P`, `django/utils/dateformat.py:TimeFormat.a`). The suffix `"S"` writes is English in every language: "29th".

## Durations: `timesince` and `timeuntil`

`django.utils.timesince.timesince` gives the time from one datetime to a later one in years, months, weeks, days, hours and minutes, ignoring seconds (`django/utils/timesince.py:timesince`). Without a second datetime it measures to `datetime.datetime.now`, in the first one's zone where it has one; with two aware ones, the second is put in the first's zone. A date is taken as its midnight. `timeuntil` is the same with the two exchanged (`django/utils/timesince.py:timeuntil`).

Months and years are counted on the calendar. `timesince` counts the months between the two, one fewer if the first's day of the month, or its time on the same day, comes later than the second's; moves the first on by those months, to the same day or, in a shorter month, the month's last, taking February as 28 days; and divides the rest into weeks, days, hours and minutes. In the docstring's examples, 10 February 2013 to 10 March 2014 is 393 days and 10 August 2007 to 10 September 2008 is 397, and each is "1 year, 1 month".

From the first unit not zero, it writes at most depth units, two by default, and only adjacent ones: it stops at a zero, so a year and five days is "1 year". A depth below one raises `ValueError`. A first datetime not at least a minute before the second gives "0 minutes".

The words are `TIME_STRINGS`, a `django.utils.translation.ngettext_lazy` for each unit with the key `"num"`, so that `%` with a dictionary chooses the plural by the number in it ([Lazy translations](lazy.md)). `avoid_wrapping` makes each part's spaces non-breaking (`django/utils/html.py:avoid_wrapping`), and the parts are joined by `", "`, itself a message: Arabic's catalogue has "، ". A run with the example's arrivals at 09:30 and 14:05 UTC, non-breaking spaces shown as spaces:

```text
timesince and timeuntil, run with the example's two arrivals
timesince(first, second)            4 hours, 35 minutes
timesince(first, second, depth=1)   4 hours
timesince(second, first)            0 minutes
timeuntil(second, first)            4 hours, 35 minutes
timesince(first, second), in Dutch  4 uur, 35 minuten
```

The filters `|timesince` and `|timeuntil` call these two ([The built-in filters](../templates/filters.md)).
