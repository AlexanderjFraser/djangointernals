---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A form field: the base class

The base class of every form field, `Field` (`django/forms/fields.py:Field`), turns one submitted value into a Python value in `Field.clean`, through `Field.to_python`, `Field.validate` and `Field.run_validators`. It also holds an input's widget, label, initial value, messages and validators, and tells a form what to draw and whether a value changed.

A field that belongs to a form class is made once, with the class, and each form of that class works on a deep copy of it ([Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`](declaring.md)). A field holds nothing of any one submission: no data, no errors, not even its name, which is the form's key for it. It holds what was decided where it was declared: which widget draws it, how a string becomes a value, what the value must satisfy, and what to say when it does not. The rest is on the bound field ([`BoundField`: a field in a form](bound-fields.md)).

## What a field class declares

`Field` keeps its defaults in class attributes, for subclasses to override (`django/forms/fields.py:Field`). `Field.widget` is the widget class a field is drawn with by default, `TextInput`, and `Field.hidden_widget` the one for a hidden input, `HiddenInput`. `Field.default_validators` is empty, and `Field.default_error_messages` has a message for the one code the base class raises, `"required"`. `Field.empty_values` are the values that count as empty, a list made from `EMPTY_VALUES`: `None`, the empty string, and the empty list, tuple and dictionary, but not `0` or `False` (`django/core/validators.py:EMPTY_VALUES`). `Field.bound_field_class` is `None`: `Field.get_bound_field` makes the bound field of the class the field names, by argument or attribute, else of the form's, else a `BoundField`.

## Making a field

`Field.__init__` takes only keyword arguments, and stores most of them for others to use: the label, help text, label suffix and template for the bound field, the initial value for the form, which prefers one it was given itself (`django/forms/fields.py:Field.__init__`). A comment adds that `initial` is no fallback: a bound form whose data lacks the field cleans what the widget reads from that data, `None` for most widgets (`django/forms/widgets.py:Widget.value_from_datadict`).

The widget is settled next. The `widget` argument, or the class's, is made an instance if it is a class and deep-copied if it is one already, so a widget given to two fields becomes two. `localize=True` sets `Widget.is_localized`, which `Widget.format_value` reads to write the value in the locale's format. `Widget.is_required` is set from `required`; the HTML attribute `"required"` is the bound field's work, and the flag is for widgets that draw an optional field differently, as `ClearableFileInput` offers its box for clearing the file only then. Last, `Field.widget_attrs` is given the widget, and what it returns is merged into `Widget.attrs`: the hook by which a field turns its arguments into HTML attributes.

Then the messages: one dictionary is updated with the `default_error_messages` of the field's class and its bases, the most general first, and then with the `error_messages` argument. A subclass declares only the codes it adds or rewords, and the caller's message for a code beats every class's. The validators become a new list, the class's `default_validators` and then the `validators` argument, so a field can append to its own without touching the list its class shares.

## Cleaning a value

`Field.clean` makes three calls: `Field.to_python` with the value, then `Field.validate` and `Field.run_validators` with what that returned, which `clean` returns (`django/forms/fields.py:Field.clean`). Each step is a method of its own, so a field class overrides the one it needs.

`to_python` converts what the widget read, usually a string, into the field's type, and raises an error, usually with the code `"invalid"`, for what will not convert; in `Field` it returns the value as it came. `validate` holds the checks built into the field, and in `Field` there is one: a value among `empty_values` is refused with the code `"required"` if the field is required. It is given the converted value, so to a field that strips spaces a string of spaces is empty.

`run_validators` returns at once for an empty value, so no validator of the field sees `None` or an empty string, and an empty value is judged by `required` alone. Otherwise it calls every validator and does not stop at the first failure: it gathers all their errors and raises them as one `ValidationError` made from the list. Where a validator raises a single error, not a list, and the field's `error_messages` has a message for its code, that message replaces the validator's, and the validator's parameters stay with it (`django/forms/fields.py:Field.run_validators`).

```python
>>> tonnage = forms.IntegerField(
...     min_value=1, error_messages={"min_value": "Ships of %(limit_value)s ton and more."}
... )
>>> list(tonnage.error_messages)
['required', 'invalid', 'min_value']
>>> tonnage.clean("0")
Traceback (most recent call last):
  ...
django.core.exceptions.ValidationError: ['Ships of 1 ton and more.']
```

The codes came from `Field`, from `IntegerField` (`django/forms/fields.py:IntegerField`) and from the argument, in that order. The `MinValueValidator` that `min_value=1` gave the field raised its own message with the code `"min_value"`; the field's replaced it, and the validator's limit filled it in ([Validators: `django/core/validators.py`](validators.md)). A `ValidationError` holds one message with a code and parameters, a list of errors, or a dictionary of lists by name; [Validating an instance](../models/validation.md) describes all three, and a model field's `clean`, which takes the same steps (`django/core/exceptions.py:ValidationError`).

## The form's call, and a disabled field

A form does not call the field's `clean` itself. `BaseForm._clean_fields` calls `Field._clean_bound_field` with the bound field, and the method cleans the bound field's data, what the widget read from the submission, or, if the field is disabled, its initial value (`django/forms/fields.py:Field._clean_bound_field`). The rest is [Validation: `full_clean`, `cleaned_data` and the errors](validation.md). `FileField` overrides the method to pass the initial value as well, so a form sent with no new file keeps the old one (`django/forms/fields.py:FileField._clean_bound_field`) ([The built-in form fields](field-types.md)).

`disabled=True` acts in four places that agree. `_clean_bound_field` cleans the initial value, `Field.bound_data` gives it to the widget, `Field.has_changed` answers that nothing changed, and the bound field writes `"disabled"` on the input (`django/forms/boundfield.py:BoundField.build_widget_attrs`). Together they set aside what a client sends for the field in cleaning, drawing and the test for change, but for the hidden initial input of `show_hidden_initial=True`, which the bound field still reads back (`django/forms/boundfield.py:BoundField._has_changed`).

```python
>>> class BerthChangeForm(BerthForm):
...     ship = forms.CharField(max_length=60, disabled=True)
...
>>> form = BerthChangeForm(
...     {"ship": "beagle", "tonnage": "366", "arrives": "2026-10-20"},
...     initial={"ship": "endeavour", "tonnage": 366},
... )
>>> form.is_valid(), form.cleaned_data["ship"], form.changed_data
(True, 'Endeavour', ['arrives'])
```

The submitted name was passed over, and the initial one cleaned and given its capital by the form's method; the tonnage converts to the 366 it started with, so it has not changed.

## What a bound field shows, and what changed

`BoundField.value`, the value an input is drawn with, is the initial value in an unbound form and, in a bound one, what `Field.bound_data` makes of the data and the initial value; either way `Field.prepare_value` has it last (`django/forms/boundfield.py:BoundField.value`). In `Field`, `bound_data` returns the data, or for a disabled field the initial value, and `prepare_value` returns what it is given (`django/forms/fields.py:Field.bound_data`). `FileField.bound_data` always returns the initial value, the file already stored (`django/forms/fields.py:FileField.bound_data`).

`Field.has_changed` tells whether one field's data differs from its initial value, and `BaseForm.changed_data` asks it of every field (`django/forms/fields.py:Field.has_changed`). A disabled field has not changed. The data is converted with `to_python`, and data that will not convert has changed. A field with a method `_coerce`, as `TypedChoiceField` has, compares the two coerced; any other takes `None` as the empty string on either side, so an empty input matches an initial `None`. The initial value is not converted: to an integer field whose initial value is the string `"366"`, a submitted `"366"` is a change. With `show_hidden_initial=True` the bound field also draws the initial value in a hidden input, and compares the data with what that input sends back (`django/forms/utils.py:RenderableFieldMixin.__str__`, `django/forms/boundfield.py:BoundField._has_changed`). Formsets, model formsets and `empty_permitted=True` act on the answers ([Validation: `full_clean`, `cleaned_data` and the errors](validation.md)).

## Writing a field class

`CharField` shows how a field class is written (`django/forms/fields.py:CharField`). Its `__init__` stores its own arguments, `max_length`, `min_length`, `strip` and `empty_value`, before it calls the base's `__init__` with the rest: the base calls `widget_attrs`, and `CharField.widget_attrs` reads the lengths to add `"maxlength"` and `"minlength"` unless the widget is hidden. After the base's `__init__` it appends to the field's validators a `MinLengthValidator` and a `MaxLengthValidator` for the lengths given, and always a `ProhibitNullCharactersValidator`, after the class's and the caller's.

`CharField.to_python` makes any value that is not empty a string and strips white space from its ends, unless the field was made with `strip=False`. A value that is empty, or has become so, is returned as `empty_value`, the empty string unless the field is given another. A model's `CharField` with `null=True` gives it `None`, except on a backend that stores the empty string as NULL (`django/db/models/fields/__init__.py:CharField.formfield`).
