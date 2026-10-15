---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Time zones

How `django.utils.timezone` keeps datetimes as instants and turns them into a local clock's reading: `USE_TZ`, aware and naive datetimes, the default and the current time zone, `django.utils.timezone.activate` and `override`, `localtime`, `make_aware`, and a local time that the clocks skip or repeat.

An instant is the same everywhere; a clock's reading of it is not, and where a zone keeps summer time it is not even one to one: an hour of readings never happens on the day the clocks go forward, and one happens twice on the day they go back. So Django keeps instants. With `USE_TZ` on, a datetime that Django makes, or reads from the database, carries its offset, and becomes a local reading at the edges, where a template writes it out and a form reads one in. The documentation's reason: a program working in local time meets errors twice a year, when the clocks change (`docs/topics/i18n/timezones.txt`).

## Aware and naive

A datetime is **aware** when its `datetime.datetime.utcoffset` gives an offset, and **naive** when it gives `None`. `django.utils.timezone.is_aware` and `is_naive` test exactly that, and a comment says that they, `make_aware` and `make_naive` check nothing about their argument, by design: given `None`, they fail with an `AttributeError` (`django/utils/timezone.py:is_aware`).

`django.utils.timezone.now` is the present: aware in UTC where `USE_TZ` is true, and where it is false a naive reading of the process's clock, which is in `TIME_ZONE` where the settings object could set it ([The settings object](../startup/settings.md)) (`django/utils/timezone.py:now`).

> **Changed in 5.0.** `USE_TZ` is true by default, and pytz has gone, with `make_aware`'s is_dst argument (`docs/releases/5.0.txt`): the documentation points instead to the value's `datetime.datetime.fold` for a local time that happens twice or never (`docs/topics/i18n/timezones.txt`).

## The default and the current time zone

The **default time zone** is `TIME_ZONE`'s, `"America/Chicago"` unless a project sets it (`django/conf/global_settings.py`). `get_default_timezone` makes a `zoneinfo.ZoneInfo` of it on its first call and keeps it, under `functools.lru_cache`; its comment says it is a function so that the setting is not read at import (`django/utils/timezone.py:get_default_timezone`). A test that overrides `TIME_ZONE` empties the cache ([Overriding settings](../startup/overrides.md)).

The **current time zone** is the one a request is shown in. `django.utils.timezone._active` holds it, an `asgiref.local.Local` as the active language's holder is: a value for each thread, or in asynchronous code for each context ([The active language](active-language.md)). `get_current_timezone` gives that value, or the default zone where there is none (`django/utils/timezone.py:get_current_timezone`).

`activate` sets it: a `tzinfo` as it is, a string as a `zoneinfo.ZoneInfo`, so that an unknown name fails with `zoneinfo.ZoneInfoNotFoundError`, and anything else is refused with `ValueError`, `"Invalid timezone: 5"` for a 5 (`django/utils/timezone.py:activate`). `deactivate` removes it, and the default applies. `override`, a context manager and a decorator, remembers on entry the value present and activates its zone, or deactivates for `None`; on exit it puts the remembered value back, or deactivates where there was none (`django/utils/timezone.py:override`). `{% timezone %}` renders its body inside it. None of them touches the process: a comment says they neither change the environment variable `"TZ"` nor call the `time` module's `"tzset"`, because that is not thread-safe.

`get_current_timezone_name` and `get_default_timezone_name` name a zone through `_get_timezone_name`: by the name it gives without a date, as a fixed offset does, and otherwise as a string, which for a `zoneinfo.ZoneInfo` is its key, `"Europe/Amsterdam"` (`django/utils/timezone.py:_get_timezone_name`). `get_fixed_timezone` makes a fixed offset named so, `"+0200"`, from minutes or a `datetime.timedelta`. The name is what a `Trunc` or an `Extract` gives the backend for its SQL ([Transforms and database functions: `Transform` and `Func`](../sql/functions.md)) (`django/db/models/functions/datetime.py:TimezoneMixin.get_tzname`).

## Choosing the zone for a request

Django has no middleware that activates a time zone. The documentation's reason: a request carries nothing to choose one by, as Accept-Language does a language (`docs/topics/i18n/timezones.txt`). Nor does anything deactivate the zone after a response, so a middleware that changes it has to put it back. The harbour office's takes a zone from a cookie:

```python
# harbour/office/middleware.py
import zoneinfo

from django.utils import timezone


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            zone = zoneinfo.ZoneInfo(request.COOKIES["harbour_timezone"])
        except (KeyError, ValueError):
            zone = None
        with timezone.override(zone):
            return self.get_response(request)
```

A missing cookie and an unknown name are each a `KeyError`, a malformed name a `ValueError`, and each gives the default zone. After `LocaleMiddleware`, in a run of the example with the test client making four requests for the arrivals page on one thread, it writes the first ship:

```text
no cookie                         Endeavour: March 29, 2026, 11:30 a.m., 1234.5 t
harbour_timezone=Europe/London    Endeavour: March 29, 2026, 10:30 a.m., 1234.5 t
no cookie                         Endeavour: March 29, 2026, 11:30 a.m., 1234.5 t
harbour_timezone=Mars/Olympus     Endeavour: March 29, 2026, 11:30 a.m., 1234.5 t
```

> **Trap.** A middleware that calls `django.utils.timezone.activate` where there is a cookie, and does nothing where there is none, leaves the zone on the thread: run so, the third request was shown London's 10:30.

## From an instant to a local time

`django.utils.timezone.localtime` converts an aware datetime into the current zone, or one it is given, and with no value converts the present (`django/utils/timezone.py:localtime`). It refuses a naive value with `ValueError`, which `datetime.datetime.astimezone` would take to be in the process's local time; the comment says this keeps that method's behaviour before Python 3.6. `localdate` is the result's date, which depends on the zone: 23:30 UTC on 28 March 2026 is the 29th in Amsterdam. `make_naive` converts the same way and drops the zone (`django/utils/timezone.py:make_naive`).

A template converts each aware datetime it writes, through `template_localtime`, unless `USE_TZ` or the template's own flag says not to or a filter has converted it already (`django/utils/timezone.py:template_localtime`); the tags are in [The libraries to load: static, i18n, l10n, tz and cache](../templates/loadable-libraries.md).

## From a local time to an instant

`django.utils.timezone.make_aware` takes a naive datetime as a reading of the current zone's clock, or another zone's, and attaches the zone with `datetime.datetime.replace`, refusing an aware value with `ValueError`; a comment warns that this "may be wrong around DST changes" (`django/utils/timezone.py:make_aware`).

Twice a year in Amsterdam a reading does not name one instant. On 29 March 2026, at 01:00 UTC, the clock goes from 02:00 to 03:00 and the day has 23 hours: 02:30 never happens, and is **imaginary**. On 25 October, at 01:00 UTC, it goes from 03:00 back to 02:00 and the day has 25: 02:30 happens twice, and is **ambiguous**. The replacement refuses neither. The naive value's `datetime.datetime.fold` decides, as PEP 495 defines it and `zoneinfo` follows: 0, the default, takes the offset in force before the change, and 1 the offset after.

```text figure=a-day-of-23-hours
Europe/Amsterdam, two days of 2026: instants in UTC above, the local clock below

29 March: forward at 01:00 UTC, a day of 23 hours
  UTC     00:00   00:30   01:00   01:30   02:00
  local   01:00   01:30 | 03:00   03:30   04:00
          +01:00        | +02:00
  02:00 to 02:59 never happens: 02:30 is imaginary
  fold=0  make_aware(datetime(2026, 3, 29, 2, 30))          ->  02:30+01:00 = 01:30 UTC, which the clock reads 03:30
  fold=1  make_aware(datetime(2026, 3, 29, 2, 30, fold=1))  ->  02:30+02:00 = 00:30 UTC, which the clock reads 01:30

25 October: back at 01:00 UTC, a day of 25 hours
  UTC     00:00   00:30   01:00   01:30   02:00
  local   02:00   02:30 | 02:00   02:30   03:00
          +02:00        | +01:00
  02:00 to 02:59 happens twice: 02:30 is ambiguous
  fold=0  make_aware(datetime(2026, 10, 25, 2, 30))          ->  02:30+02:00 = 00:30 UTC, the first
  fold=1  make_aware(datetime(2026, 10, 25, 2, 30, fold=1))  ->  02:30+01:00 = 01:30 UTC, the second

a form's DateTimeField in Europe/Amsterdam, given "2026-03-29 02:30" or "2026-10-25 02:30":
  ValidationError, code "ambiguous_timezone"
```

*Two days of 2026 in Amsterdam, from a run: a local 02:30 never happens on the first and happens twice on the second; `make_aware` gives each an instant by its fold, and a form's datetime field refuses both.*

The imaginary reading is the trap: `make_aware` returned a real instant, 01:30 UTC, that still reads 02:30, and `localtime` gives it back unchanged: `make_aware` attached the current zone's own object, and `datetime.datetime.astimezone` leaves a value alone when given the very object it carries. The same instant given in UTC is shown as 03:30.

`_datetime_ambiguous_or_imaginary` finds such readings: the zone gives the value one offset as it is and another with its fold flipped (`django/utils/timezone.py:_datetime_ambiguous_or_imaginary`). Django asks it in two places. `from_current_timezone`, through which a form's datetime field passes what it read, refuses such a reading with a `ValidationError` of code `"ambiguous_timezone"` ([The built-in form fields](../forms/field-types.md#dates-and-times)) (`django/forms/utils.py:from_current_timezone`). `TimeFormat` gives such a value no zone, so the format letters `"e"`, `"O"`, `"T"`, `"Z"` and `"I"` write nothing ([Writing numbers, dates and durations](writing-values.md)) (`django/utils/dateformat.py:TimeFormat.__init__`).

Nothing else asks. A model's datetime field given a naive value warns and makes it aware in the default zone, not the current one; its comment expects an exception at a change of the clocks, and under `zoneinfo` none comes, so a naive 02:30 on 29 March becomes 01:30 UTC ([The field classes](../models/field-types.md)) (`django/db/models/fields/__init__.py:DateTimeField.get_prep_value`).

## Where else the current zone is read

The current zone plays no part in storing a value: a backend whose database keeps no time zone stores an aware datetime in UTC, or in the zone its connection names ([Values in and out: adapters, converters and time zones](../backends/values.md)). It matters where a query cuts a datetime into a calendar's parts: a `Trunc` or an `Extract` given no `tzinfo` uses the current zone, and one written into a migration so is deprecated ([Transforms and database functions: `Transform` and `Func`](../sql/functions.md)). The date views make each boundary of a period midnight in the current zone, for a datetime field ([The date views](../views/dates.md)) (`django/views/generic/dates.py:DateMixin._make_date_lookup_arg`).
