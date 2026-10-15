---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Widgets: `Widget` and its subclasses

A widget is the part of a form field that knows HTML: `Widget` draws the field's input from a template and reads the field's value back out of the submitted data. Its subclasses are the `<input>` widgets, among them the file inputs and `CheckboxInput`, `Textarea`, the choice widgets, and the widgets of several inputs, `MultiWidget`, `SplitDateTimeWidget` and `SelectDateWidget` (`django/forms/widgets.py`).

Neither half knows about a form. To draw, the bound field hands the widget the input's name, the value, the attributes it adds and the form's renderer ([`BoundField`: a field in a form](bound-fields.md)); to read, the form hands it its data, its files and the name; and each form has its own copy of the widget ([Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`](declaring.md)). The choice widgets are told in [Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](choices.md), and a widget's CSS and JavaScript in [Form assets: `Media`](media.md).

## What a widget holds

`Widget.__init__` keeps a copy of the HTML attributes it is given as `Widget.attrs`; the rest is flags, class attributes that other objects read (`django/forms/widgets.py:Widget`). A field sets `Widget.is_required` on its widget, and `Widget.is_localized` if it is localized, and merges its `Field.widget_attrs` into the attributes, as a `CharField` adds `"maxlength"` ([A form field: the base class](fields.md)) (`django/forms/fields.py:Field.__init__`).

| flag, on `Widget` | changed by | read by |
|---|---|---|
| `is_required`, `False` | the field | the context's `"required"`; the clear checkbox and the blank date choices, offered only when it is false |
| `is_localized`, `False` | the field; `BoundField.as_widget`; a `MultiWidget`, on its widgets | `Widget.format_value` |
| `Widget.needs_multipart_form`, `False` | `FileInput`; `MultiWidget`, from its widgets | `BaseForm.is_multipart` |
| `Widget.supports_microseconds`, `True` | the date and time inputs, `SplitDateTimeWidget` | `BaseForm.get_initial_for_field`, which then drops an initial value's microseconds |
| `Widget.use_fieldset`, `False` | `MultiWidget`, `SelectDateWidget`, `RadioSelect` | `BoundField.use_fieldset`: the field is drawn in a `<fieldset>` |

`Widget.is_hidden` is a property, true when the widget's `Input.input_type` is `"hidden"`, and for a `MultiWidget` when all its widgets are hidden. A hidden field is drawn among the form's hidden fields, and its input gets neither `"required"` nor `"aria-invalid"` (`django/forms/widgets.py:Widget.is_hidden`, `django/forms/boundfield.py:BoundField.build_widget_attrs`).

## Drawing: `Widget.render`, `get_context` and `format_value`

`Widget.render` asks `Widget.get_context` for a dictionary and hands it to `Widget._render`, which has the renderer it was given, or the default one, render the widget's template with it, and marks the result safe (`django/forms/widgets.py:Widget.render`, `django/forms/widgets.py:Widget._render`). In a form the caller is `BoundField.as_widget`, with the form's renderer and attributes such as `"id"` and `"required"` (`django/forms/boundfield.py:BoundField.as_widget`).

The context's one key, `"widget"`, holds the name, `"is_hidden"`, `"required"`, the value as `Widget.format_value` writes it, `"template_name"`, and the attributes: the widget's own and then the call's, which win, merged by `Widget.build_attrs` (`django/forms/widgets.py:Widget.get_context`). The berth form's ship widget, with the `"maxlength"` its field gave it:

```python
>>> from pprint import pp
>>> widget = BerthForm.base_fields["ship"].widget
>>> pp(widget.get_context("ship", "  heron ", {"id": "id_ship"}))
{'widget': {'name': 'ship',
            'is_hidden': False,
            'required': True,
            'value': '  heron ',
            'attrs': {'maxlength': '60', 'id': 'id_ship'},
            'template_name': 'django/forms/widgets/text.html',
            'type': 'text'}}
>>> print(widget.render("ship", "  heron ", {"id": "id_ship"}))
<input type="text" name="ship" value="  heron " maxlength="60" id="id_ship">
```

`Widget.format_value` turns an empty string, `None`, and the `DatabaseDefault` an unsaved instance holds for a database default into `None`, for which the template writes no `"value"`; a localized widget formats the value with `django.utils.formats.localize_input`, which leaves a string as it is; any other value becomes `str(value)` (`django/forms/widgets.py:Widget.format_value`).

Each concrete widget names its template in `template_name`. The attributes are written by `"django/forms/widgets/attrs.html"`, which leaves out one that is `False` and writes one that is `True` bare (`django/forms/templates/django/forms/widgets/attrs.html`); where the templates are found is in [Rendering a form: renderers and templates](rendering.md).

## Reading: `value_from_datadict` and `value_omitted_from_data`

`Widget.value_from_datadict` is given the form's data, its files and the input's name, and returns the raw value that `Field.clean` starts from when the field is not disabled: in the base class, what the data holds under that name, or `None` (`django/forms/widgets.py:Widget.value_from_datadict`). The form asks the widget and not the field because, as the comment in `BaseForm._widget_data_value` says, some widgets split their data over several HTML inputs (`django/forms/forms.py:BaseForm._widget_data_value`).

`Widget.value_omitted_from_data` says whether the input was left out of the submission: in the base class, whether its name is not in the data. Besides the widgets made of others, its reader is `construct_instance`, which leaves a model field that has a default as the instance holds it when the widget says its input was omitted and the cleaned value is empty ([Model forms: `ModelForm` and `fields_for_model`](model-forms.md)) (`django/forms/models.py:construct_instance`).

## The label and the `"required"` attribute

`Widget.id_for_label` gives the id a `<label>` names in its `"for"`: in the base class the input's own; for a widget of several inputs, one of theirs, or an empty string, which leaves the label without a `"for"` (`django/forms/widgets.py:Widget.id_for_label`). `Widget.use_required_attribute`, given the bound field's initial value, says whether the input may carry the HTML attribute `"required"`: in the base class, unless it is hidden. The bound field writes `"required"` only when the widget agrees, the field is required and `BaseForm.use_required_attribute` is true (`django/forms/boundfield.py:BoundField.build_widget_attrs`). `Widget.is_required` becomes no attribute, as the ship's input shows.

## The input widgets

`Input` is the base of the `<input>` widgets. Its `Input.input_type`, which its subclasses set, goes into the context as `"type"`, and a `"type"` among the attributes an instance is made with replaces it (`django/forms/widgets.py:Input`). `TextInput`, `NumberInput`, `EmailInput`, `URLInput`, `ColorInput`, `SearchInput`, `TelInput`, `PasswordInput`, `HiddenInput`, `FileInput` and `CheckboxInput` set the type their names say; the date and time inputs are text inputs.

`PasswordInput` draws no value unless made with `render_value=True`, so a form sent back with errors does not repeat the password (`django/forms/widgets.py:PasswordInput.get_context`). `MultipleHiddenInput` draws a hidden input for each value of a list and reads the list back with `getlist` (`django/forms/widgets.py:MultipleHiddenInput`). `Textarea`, which is no `Input`, writes the value between its tags, with `"cols"` of `"40"` and `"rows"` of `"10"` unless given others (`django/forms/widgets.py:Textarea.__init__`).

The date and time inputs share `DateTimeBaseInput`, which writes a value in its `DateTimeBaseInput.format`, if it was made with one, or else in the first of the locale's formats named by `DateTimeBaseInput.format_key`, as `DATE_INPUT_FORMATS`; a string it leaves alone ([Internationalization and time zones](../i18n.md)) (`django/forms/widgets.py:DateTimeBaseInput.format_value`).

## File inputs: `FileInput` and `ClearableFileInput`

`FileInput` reads from the files and not the data, counts as omitted when its name is not among them, never draws a value, and refuses `"required"` when the field has an initial value (`django/forms/widgets.py:FileInput`). Made with a `"multiple"` attribute it raises `ValueError`, unless its class sets `FileInput.allow_multiple_selected`; then it is drawn with `"multiple"` and reads a list.

`ClearableFileInput` adds a way to remove a stored file, which to `ClearableFileInput.is_initial` is a value with a URL, as a model's `FieldFile` has. Given one, the template writes a link to it and, for a field that is not required, a checkbox named after the input with `"-clear"` added, as `"scan-clear"`, before the file input (`django/forms/templates/django/forms/widgets/clearable_file_input.html`).

`ClearableFileInput.value_from_datadict` reads the upload and then, for a field that is not required, the checkbox. Ticked with no upload, it returns `False`, which `FileField.clean` takes as an order to clear the stored file; ticked with an upload too, the marker `FILE_INPUT_CONTRADICTION`, which the field makes an error ([The built-in form fields](field-types.md)) (`django/forms/widgets.py:ClearableFileInput.value_from_datadict`, `django/forms/fields.py:FileField.clean`). It keeps in `ClearableFileInput.checked` whether the box was sent, and draws the box ticked if so; it counts as omitted only when neither file nor box was sent.

## `CheckboxInput`

`CheckboxInput` draws the box ticked when its `CheckboxInput.check_test` is true of the value. By default that is `boolean_check`, true of anything but `False`, `None` and the empty string, a function at module level so that the widget can be pickled, as the comment above it says, citing ticket 17976 (`django/forms/widgets.py:boolean_check`).

`CheckboxInput.value_from_datadict` returns `False` when the name is not in the data, since a browser sends nothing for an unticked box. Otherwise it reads `"true"` and `"false"`, in any case, as `True` and `False`, and anything else by its truth, so that `"0"` is `True`, and so is `"on"`: by HTML's rule a browser sends that for a ticked box with no `"value"`, and `CheckboxInput.format_value` writes none for `True` (`django/forms/widgets.py:CheckboxInput.value_from_datadict`). An absent box cannot be told from an unticked one, so `CheckboxInput.value_omitted_from_data` always answers `False`, as its comment says. What `BooleanField` makes of the value is in [The built-in form fields](field-types.md) (`django/forms/fields.py:BooleanField`).

## `MultiWidget` and `SplitDateTimeWidget`

`MultiWidget` draws one field as several inputs and reads it back as a list (`django/forms/widgets.py:MultiWidget`). It is made with its widgets, in a sequence or a dictionary, and names each input after the field with a suffix from `MultiWidget.widgets_names`: `"_0"`, `"_1"` and on, or an underscore and the key (none for an empty key). To draw, it hands a value that is not a list or a tuple to `MultiWidget.decompress`, which subclasses write, and has each widget make its context with its own name, value and id (`django/forms/widgets.py:MultiWidget.get_context`). To read, it returns what each widget reads under its own name, for a `MultiValueField` to clean and compress ([The built-in form fields](field-types.md)).

A `MultiWidget` counts as omitted when all its widgets do, and has their media together; its `MultiWidget.id_for_label` is empty.

`SplitDateTimeWidget` is a `MultiWidget` of a `DateInput` and a `TimeInput`; its `SplitDateTimeWidget.decompress` splits a datetime, an aware one first made naive in the current time zone (`django/forms/widgets.py:SplitDateTimeWidget.decompress`).

## `SelectDateWidget`

`SelectDateWidget` draws a date as three `<select>` boxes, named after the field with `"_year"`, `"_month"` and `"_day"` added, in the order of the locale's `DATE_FORMAT`; it is no `MultiWidget`, and makes a `Select` for each box itself (`django/forms/widgets.py:SelectDateWidget`). Read back, boxes that make no date give a string such as `"2026-2-31"`, which the date field refuses and `SelectDateWidget.format_value` reads back, so that, as its docstring says, an invalid date such as February 31 is shown again.
