---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Dates, durations and addresses: `parse_datetime`, `parse_duration` and `clean_ipv6_address`

`django/utils/dateparse.py` reads a date, a time, a datetime or a duration from text, with `parse_date`, `parse_time`, `parse_datetime` and `parse_duration`; `django/utils/duration.py` writes a duration back as text; and `django/utils/ipv6.py` checks an IPv6 address and gives it one spelling, with `clean_ipv6_address`.

Values reach Django as text: SQLite keeps dates and times as text, and fixtures and posted forms are text. A parser of dates and times answers in one of three ways: the value; `None`, when the text is in no form it reads; or `ValueError`, when the form is right but the value cannot exist, the thirtieth of February. A model's date, time or datetime field turns `None` into its `"invalid"` error and `ValueError` into `"invalid_date"`, `"invalid_time"` or `"invalid_datetime"`, so that its message says whether the format or the value was wrong (`django/db/models/fields/__init__.py:DateField.to_python`). `normalize_json` makes a task's arguments and return value the types of JSON ([Background tasks: `Task`, `TaskResult` and the task backends](../services/tasks.md)) (`django/utils/json.py:normalize_json`).

## Dates and times

`parse_date`, `parse_time` and `parse_datetime` each try their type's own fromisoformat first, `datetime.datetime.fromisoformat` for a datetime, and the module's pattern only when that raises `ValueError`, passing the pattern's groups as integers to the type's constructor (`django/utils/dateparse.py:parse_datetime`). The pattern adds forms ISO 8601 does not allow, such as a one-digit month, day or hour. Text that neither reads gives `None`. Text the pattern matches but the constructor refuses raises the constructor's `ValueError`; the comment at the top of the module counts the constructors' friendlier messages among its reasons for regular expressions rather than `time.strptime`, beside validating as they parse and flexibility. The fraction of a second that the pattern reads is padded on the right, so that `".5"` is half a second, not five microseconds.

`parse_datetime` returns an aware datetime when the text has an offset and a naive one when it has none. On the pattern's path `"Z"` becomes `datetime.UTC`, and another offset is counted in minutes and given to `get_fixed_timezone`, which returns a `datetime.timezone` named after it (`django/utils/timezone.py:get_fixed_timezone`). An ISO 8601 date alone is read as its midnight.

`parse_time` never returns an aware time. Where the standard library reads an offset, `parse_time` removes it, its comment's reason being that an aware `datetime.time` makes sense in no circumstance: the offset is dropped, not applied. The pattern has no place for an offset, so text the standard library refuses gives `None` if it carries one, the case the docstring describes (`django/utils/dateparse.py:parse_time`). A voyage's sailing, read from text, and last through the Voyage model's field sailed:

```text
parse_date("2026-3-14")  ->  datetime.date(2026, 3, 14)
parse_date("2026-02-30")  ->  raises ValueError: day 30 must be in range 1..28 for month 2 in year 2026
parse_datetime("2026-03-14 7:30+0100")  ->  datetime.datetime(2026, 3, 14, 7, 30, tzinfo=datetime.timezone(datetime.timedelta(seconds=3600), '+0100'))
parse_time("17:30+01:00")  ->  datetime.time(17, 30)
parse_time("7:30+01:00")  ->  None
sailed = Voyage._meta.get_field("sailed")
sailed.to_python("14 March 2026")  ->  raises ValidationError, code 'invalid'
sailed.to_python("2026-02-30")  ->  raises ValidationError, code 'invalid_date'
```

The parsers' main callers are SQLite's converters, which the driver runs on each date, time and datetime column it fetches ([Values in and out: adapters, converters and time zones](../backends/values.md)) (`django/db/backends/sqlite3/base.py:decoder`); a model field's `to_python`, given a string ([The field classes](../models/field-types.md)); and the form field `DateTimeField`, before its input formats ([The built-in form fields](../forms/field-types.md)) (`django/forms/fields.py:DateTimeField.to_python`).

## Durations: `parse_duration`

`parse_duration` tries three patterns in turn and uses the first that matches (`django/utils/dateparse.py:parse_duration`). Django's own is the docstring's `"%d %H:%M:%S.%f"`, its days, hours and minutes optional; Python's `str` of a `datetime.timedelta`, `"2 days, 6:30:00"`, matches it too. ISO 8601's is read without years and months, which a `datetime.timedelta` cannot hold, as the comment above its pattern says. The third is PostgreSQL's day-time interval, `"2 days 06:30:00"`, its year-month and mixed intervals refused for the same reason.

In Django's form and PostgreSQL's the days carry their own sign, and a sign before the time applies to the time alone: `"-2 06:30:00"` is two days back and six and a half hours forward. In ISO 8601 a sign before the `P` applies to the whole: the code multiplies the days by the sign only for that pattern. Django's pattern and ISO 8601's take a comma for the decimal point; PostgreSQL's takes only a point. Text in no form gives `None`; a duration too long for a `datetime.timedelta` raises `OverflowError`, which the form field `DurationField` reports as `"overflow"` (`django/forms/fields.py:DurationField.to_python`) and the model field lets through.

> **Changed in 6.1.** `parse_duration` reads weeks in ISO 8601's form, `"P1W"` (`docs/releases/6.1.txt`).

`django/utils/duration.py` writes two of the forms. `duration_string` writes Django's own, with days and microseconds only where there are some, and a negative duration as Python holds it, negative days and a positive time (`django/utils/duration.py:duration_string`); a model's `DurationField.value_to_string` gives it to a serializer (`django/db/models/fields/__init__.py:DurationField.value_to_string`). `duration_iso_string` writes ISO 8601, for `DjangoJSONEncoder.default` (`django/core/serializers/json.py:DjangoJSONEncoder.default`) and for Oracle's schema editor, which quotes a duration with it (`django/db/backends/oracle/schema.py:DatabaseSchemaEditor.quote_value`). `duration_microseconds` makes the integer that `BaseDatabaseOperations.adapt_durationfield_value` hands the driver, which PostgreSQL's and Oracle's override to pass the `datetime.timedelta` on (`django/db/backends/base/operations.py:BaseDatabaseOperations.adapt_durationfield_value`). The voyage to Piraeus took two days and six and a half hours:

```text
length = datetime.timedelta(days=2, hours=6, minutes=30)
parse_duration("2 06:30:00")  ->  datetime.timedelta(days=2, seconds=23400)
parse_duration("PT54,5H")  ->  datetime.timedelta(days=2, seconds=23400)
parse_duration("-2 06:30:00")  ->  datetime.timedelta(days=-2, seconds=23400)
parse_duration("-P2DT6H30M")  ->  datetime.timedelta(days=-3, seconds=63000)
parse_duration("P1Y")  ->  None
duration_string(-length)  ->  '-3 17:30:00'
duration_iso_string(-length)  ->  '-P2DT06H30M00S'
```

## IPv6 addresses: `clean_ipv6_address`

An IPv6 address can be spelt many ways, and `clean_ipv6_address` gives it the one `ipaddress.IPv6Address` writes, compressed and in lower case (`django/utils/ipv6.py:clean_ipv6_address`). It refuses text longer than its max_length argument, by default `MAX_IPV6_ADDRESS_LENGTH`, 39, eight full groups, a bound added against a denial of service, CVE-2024-56374 (`docs/releases/5.1.5.txt`); parses the text; and makes the address an integer and an address again, which drops a scope such as `"%eth0"` (`django/utils/ipv6.py:_ipv6_address_from_str`). An IPv4-mapped address is written with its last part dotted, or with `unpack_ipv4=True` as the IPv4 address alone. A failure raises `ValidationError` with the message given, code `"invalid"` and the parameter `"protocol"`, `"IPv6"`, which the model field's message puts in.

> **Trap.** The limit counts characters. A valid address written in full with a dotted IPv4 part can run to 45 and is refused, where the same address in short groups passes.

`is_valid_ipv6_address` asks the same without raising: an `ipaddress.IPv6Address` is valid at once, and anything else is parsed under the default limit, `TypeError` and `ValueError` both meaning `False`; `validate_ipv6_address` is built on it (`django/core/validators.py:validate_ipv6_address`). The model's and the form's `GenericIPAddressField.to_python` strip a value and call `clean_ipv6_address` if it has a colon, the form's with its own `max_length` ([The field classes](../models/field-types.md), [The built-in form fields](../forms/field-types.md)) (`django/forms/fields.py:GenericIPAddressField.to_python`).

```text
clean_ipv6_address("2001:0DB8:0000:0000:0000:0000:0000:0001")  ->  '2001:db8::1'
clean_ipv6_address("::ffff:0a0a:0a0a", unpack_ipv4=True)  ->  '10.10.10.10'
clean_ipv6_address("fe80::1%eth0")  ->  'fe80::1'
clean_ipv6_address("0:0:0:0:0:ffff:192.168.100.228")  ->  '::ffff:192.168.100.228'
clean_ipv6_address("0000:0000:0000:0000:0000:ffff:192.168.100.228")  ->  raises ValidationError, code 'invalid'
```
