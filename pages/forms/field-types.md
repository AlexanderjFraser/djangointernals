---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The built-in form fields

The form fields Django ships besides the base class and the choice fields, by the kind of value they make: text, numbers, dates and times, files, booleans, and values made of several fields. Each is drawn by a widget and cleans what was submitted to a value of its own kind.

A built-in field is a subclass of `Field` that overrides a few of its parts: its `widget`, messages and validators, `widget_attrs` for the widget's HTML attributes, and `to_python`, which makes the value ([A form field: the base class](fields.md)) (`django/forms/fields.py:Field.__init__`). `ChoiceField` and its subclasses, `FilePathField` among them, are told in [Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](choices.md). The examples use a port's clearance form:

```python
# harbour/fleet/forms.py
class ClearanceForm(forms.Form):
    departs = forms.DateTimeField()
    draught = forms.DecimalField(max_digits=4, decimal_places=2, min_value=0)
    manifest = forms.FileField(required=False)
    hazardous = forms.BooleanField(required=False)
```

## The fields by family

A required field, `NullBooleanField` aside, refuses an empty value with the code `"required"`; the last column is what one that is not required makes of `""` or `None` (`django/forms/fields.py:Field.validate`).

| field | widget | cleans to | empty |
|---|---|---|---|
| `CharField` | `TextInput` | a `str`, stripped unless `strip=False` | `empty_value`, `""` by default |
| `RegexField` | `TextInput` | a `str`, not stripped, in which its pattern is found | `""` |
| `EmailField` | `EmailInput` | a `str`, at most 320 characters by default | `""` |
| `URLField` | `URLInput` | a `str` with a scheme | `""` |
| `SlugField` | `TextInput` | a `str` that is a slug | `""` |
| `UUIDField` | `TextInput` | a `uuid.UUID` | `None` |
| `GenericIPAddressField` | `TextInput` | a `str`, an IPv6 address normalized | `""` |
| `JSONField` | `Textarea` | the decoded value | `None` |
| `IntegerField` | `NumberInput` | an `int` | `None` |
| `FloatField` | `NumberInput` | a finite `float` | `None` |
| `DecimalField` | `NumberInput` | a finite `decimal.Decimal` | `None` |
| `DateField` | `DateInput` | a `datetime.date` | `None` |
| `TimeField` | `TimeInput` | a `datetime.time` | `None` |
| `DateTimeField` | `DateTimeInput` | a `datetime.datetime`, aware under `USE_TZ` | `None` |
| `DurationField` | `TextInput` | a `datetime.timedelta` | `None` |
| `FileField` | `ClearableFileInput` | an uploaded file, the file already there, or `False` | `None` |
| `ImageField` | `ClearableFileInput` | the same; an upload checked by Pillow | `None` |
| `BooleanField` | `CheckboxInput` | a `bool` | `False` |
| `NullBooleanField` | `NullBooleanSelect` | `True`, `False` or `None`, even when required | `None` |
| `ComboField` | `TextInput` | what its fields make of it, in turn | the same |
| `MultiValueField` | `TextInput`, for a subclass to replace | what `compress` returns | what `compress` returns for `[]` |
| `SplitDateTimeField` | `SplitDateTimeWidget` | a `datetime.datetime`, aware under `USE_TZ` | `None` |

*The fields that are not choice fields, the base class aside, by family: text, numbers, dates and times, files, booleans, composites.*

## Numbers

`FloatField` and `DecimalField` are subclasses of `IntegerField` and share its limits: `max_value`, `min_value` and `step_size` become validators, the step counted from the minimum or from 0 ([Validators: `django/core/validators.py`](validators.md)), and `IntegerField.widget_attrs` writes them on a `NumberInput` as `"min"`, `"max"` and `"step"` (`django/forms/fields.py:IntegerField.widget_attrs`). For a `DecimalField` with `decimal_places` and no `step_size`, `DecimalField.widget_attrs` makes the step one unit of the last decimal place, as `str` writes it, in lower case: `"0.01"` for the draught, and `"1e-7"` for seven places, an exponent that, the comment says, keeps a small value from being parsed as 0 (ticket 20765) (`django/forms/fields.py:DecimalField.widget_attrs`).

`IntegerField.to_python` strips a trailing point and zeros before calling `int`, so `"3.0"` is 3 and `"3.5"` is refused as `"invalid"`. `float` and `decimal.Decimal` accept `"inf"` and `"NaN"`, and `FloatField.validate` and `DecimalField.validate` refuse a value that is not finite (`django/forms/fields.py:DecimalField.validate`).

`localize=True` makes the widget a `TextInput`, unless one was given, because, the comment says, a localized number input is not well supported on most browsers; so a localized field given no widget has no `"min"`, `"max"` or `"step"`. Its value is written in the locale's format and read with `sanitize_separators` ([Internationalization and time zones](../i18n.md)) (`django/forms/fields.py:IntegerField.__init__`).

## Dates and times

`DateField`, `TimeField` and `DateTimeField` hand a string to `BaseTemporalField.to_python`, which strips it and tries the field's `input_formats` one by one with `datetime.datetime.strptime`, refusing it as `"invalid"` when none fits (`django/forms/fields.py:BaseTemporalField.to_python`). Formats given as `input_formats` replace the class's, which are the locale's, looked up when the form is cleaned: under `"en-us"` `"10/20/2026"` is a date, under `"en-gb"` it is not ([Internationalization and time zones](../i18n.md)).

`DateTimeField.to_python` first tries `parse_datetime`, which reads ISO 8601 with any offset; a string of that shape that is no real moment, `"2026-02-30 14:30"`, is refused there. Then come the `DATETIME_INPUT_FORMATS` and after them the `DATE_INPUT_FORMATS`, so a date alone is read as its midnight (`django/forms/fields.py:DateTimeField.to_python`). Under `USE_TZ`, `from_current_timezone` makes a naive result aware in the current time zone, and refuses a time that the zone skips or repeats as `"ambiguous_timezone"`; a result with an offset keeps it (`django/forms/utils.py:from_current_timezone`). In Malta the clocks went forward at two in the morning of 29 March 2026:

```python
>>> from django.utils import timezone
>>> timezone.activate("Europe/Malta")
>>> form = ClearanceForm({"departs": "2026-10-20 14:30", "draught": "4.2"})
>>> form.is_valid(), form.cleaned_data["departs"]
(True, datetime.datetime(2026, 10, 20, 14, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Malta')))
>>> form = ClearanceForm({"departs": "2026-03-29 02:30", "draught": "4.2"})
>>> form.errors.as_data()
{'departs': [ValidationError(['2026-03-29 02:30:00 couldn’t be interpreted in time zone Europe/Malta; it may be ambiguous or it may not exist.'])]}
```

`DateTimeField.prepare_value` goes the other way, so that an input shows an aware value in the current zone's time (`django/forms/utils.py:to_current_timezone`).

## Files

A file input is never drawn with a value, so a form editing a record with a file must tell "no new file" from "remove the file". Beside a file already there, for a field that is not required, `ClearableFileInput` draws a box to clear it, and reads the pair as one value: the upload, `False` for the box alone, or the marker `FILE_INPUT_CONTRADICTION` for both ([Widgets: `Widget` and its subclasses](widgets.md)) (`django/forms/widgets.py:ClearableFileInput.value_from_datadict`).

`FileField.clean` is given the initial value too, by `FileField._clean_bound_field` (`django/forms/fields.py:FileField.clean`). It refuses the marker as `"contradiction"`. It returns `False` unchecked when the field is not required, and takes it as `None` when it is. With no upload, an initial value is the cleaned value, unchecked. Anything else goes to `Field.clean`, where `FileField.to_python` wants an object with a `name` and a `size`, and refuses an empty file unless `allow_empty_file=True`. When a model form fills its instance, a model's file field keeps its file for `None` and is emptied by `False` ([File fields](../models/files.md)) (`django/db/models/fields/files.py:FileField.save_form_data`).

`FileField.bound_data` returns the initial value whatever was sent, so a form drawn again after an error shows the old file, not the new one. `FileField.has_changed` counts anything but `None` from the widget as a change, unless the field is disabled (`django/forms/fields.py:FileField.bound_data`).

`ImageField.to_python` adds Pillow, imported when an image is cleaned (`django/forms/fields.py:ImageField.to_python`). It opens the upload from its path on disk or from its bytes and has Pillow verify the image rather than load it: loading, the comment says, could spot a truncated JPEG but reads the whole image into memory, a denial-of-service vector (tickets 3848 and 18520). Anything Pillow raises becomes `"invalid_image"`. Its validator `validate_image_file_extension` refuses an extension Pillow does not know, and a file input with no `"accept"` gets `"image/*"` (`django/forms/fields.py:ImageField.widget_attrs`).

## Booleans: required means ticked

An unticked checkbox is absent from the data, and `CheckboxInput` reads that as `False`. `BooleanField.to_python` reads `"false"`, in any case, and `"0"` as `False`, and anything else by `bool`, so `"no"` is `True`. `BooleanField.validate` refuses a false value for a required field: a required `BooleanField` is a box that must be ticked (`django/forms/fields.py:BooleanField.validate`). A box that may be left empty, like the hazardous box, needs `required=False`, which a model's boolean field without choices gives its form field ([The field classes](../models/field-types.md)).

`NullBooleanField` reads `"True"`, `"true"` and `"1"` as `True`, their opposites as `False` and anything else as `None`, and its `validate` does nothing, so being required refuses nothing (`django/forms/fields.py:NullBooleanField.to_python`).

## Fields made of fields

`MultiValueField` makes one value of several inputs: it is given a list of fields, and a `MultiWidget` reads one string for each (`django/forms/fields.py:MultiValueField.clean`). `MultiValueField.clean` refuses as `"invalid"` a value that is neither empty nor a list or tuple, and, when the field is required, one whose items are all empty. It cleans each item with its field, gathering each distinct error. With `require_all_fields`, the default, any empty item refuses a required field as `"required"`; without it, an empty item for a required subfield gives that subfield's `"incomplete"` message. The cleaned list goes to `compress`, which a subclass writes, and the validators run on what it returns; the widget's `decompress` is its inverse.

`SplitDateTimeField` is a `DateField` and a `TimeField` drawn by a `SplitDateTimeWidget`; its `compress` joins them and passes the result through `from_current_timezone` (`django/forms/fields.py:SplitDateTimeField.compress`). `ComboField` is the reverse, one value that must pass several fields: after its own required check and validators, its `clean` hands the value to each field's `clean` in turn (`django/forms/fields.py:ComboField.clean`).

## URLs and the assumed scheme

`URLField.to_python` strips the value and, if it finds no scheme, puts the field's `assume_scheme` in front, by default `"https"`: `"harbour.example/berths"` becomes `"https://harbour.example/berths"` (`django/forms/fields.py:URLField.to_python`). It takes what precedes the first colon as the scheme when that begins with an ASCII letter and holds no slash; splitting at the colon, the comment says, avoids calling `urllib.parse.urlsplit` on large or slow-to-normalize inputs.

> **Trap.** `"harbour.example:8000/berths"` has a scheme by that test, `"harbour.example"`, so nothing is put in front of it, and the field's `URLValidator` refuses it.

> **Changed in 6.0.** The assumed scheme was `"http"`.

## JSON

`JSONField` is a `CharField` drawn as a `Textarea`, whose `to_python` decodes with `json.loads` (`django/forms/fields.py:JSONField.to_python`). A decoded string comes back as a `JSONString`, and a value that is already a list, a dictionary, a number or a `JSONString` passes through as it is. `JSONField.bound_data` wraps text that does not decode in an `InvalidJSONInput`, which `JSONField.prepare_value` leaves alone where it writes every other value with `json.dumps`: text that failed is shown again as it was typed, and text that passed as `json.dumps` writes it.

> **Trap.** `"null"`, `"[]"` and `"{}"` decode to empty values, so a required `JSONField` refuses them as `"required"`.
