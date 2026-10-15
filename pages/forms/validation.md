---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Validation: `full_clean`, `cleaned_data` and the errors

`BaseForm.full_clean` validates a bound form: it cleans each field, runs the form's `clean`, and leaves two results, `cleaned_data` for the values that passed and an `ErrorDict` of `ErrorList` objects for the rest, every error filed by `BaseForm.add_error`. `BaseForm.errors` and `BaseForm.is_valid` run it the first time they are asked.

A view asks a form whether its data will do, and then wants the values or the errors, each filed under its input. A program tests an error's code, `"required"` or `"min_value"`, and a page shows its message, so a form keeps each error as a `ValidationError`, which has both, in a list that draws itself as HTML.

## When validation runs: `errors` and `is_valid`

Reading `BaseForm.errors` while the form's `_errors` is `None`, as `BaseForm.__init__` leaves it, calls `full_clean`; after that it returns what was found (`django/forms/forms.py:BaseForm.errors`). `BaseForm.is_valid` is the form being bound and its errors empty (`django/forms/forms.py:BaseForm.is_valid`). So an unbound form is never valid, and its validation finds no errors and makes no `cleaned_data`. A call of `full_clean` validates the form afresh.

## `BaseForm.full_clean`

`BaseForm.full_clean` first sets `_errors` to a new `ErrorDict`, made with the form's renderer, and only then looks at the data; whatever files an error during the validation reads `errors`, and finds that dictionary (`django/forms/forms.py:BaseForm.full_clean`). An unbound form stops there.

A bound form is given an empty `cleaned_data`, and then one short cut: a form made with `empty_permitted=True` whose data has not changed from its initial values stops at once, valid, with nothing in `cleaned_data` and none of its fields cleaned, not even the required ones. A formset makes its extra forms past its minimum so, and a blank one is no error ([Formsets: `BaseFormSet` and the management form](formsets.md)). Otherwise three steps run, each whatever the one before found: `_clean_fields`, `_clean_form` and `_post_clean`.

## Each field in turn: `_clean_fields`

`BaseForm._clean_fields` takes the fields in the order of the form's `fields`. For each it puts in `cleaned_data` the value `Field._clean_bound_field` cleans: what the bound field read from the data, or the initial value for a disabled field ([A form field: the base class](fields.md)) (`django/forms/forms.py:BaseForm._clean_fields`, `django/forms/fields.py:Field._clean_bound_field`).

Then, if the form has a method whose name is `"clean_"` and the field's name, it is called with no arguments. It finds the field's value in `cleaned_data`, where BerthForm's method for the ship reads it, and whatever it returns takes the value's place: a method that ends without a `return` makes the value `None`, and the form is still valid. Since the fields go one at a time, such a method sees the fields before its own that passed, and none after: a method for the arrival date could read the ship's name, and the ship's method cannot read the date. A check of two fields waits for the form's `clean`.

A `ValidationError` from the field or the method goes to `add_error` under the field's name, and the field is left out of `cleaned_data`: a value the field had cleaned before its method failed is taken out again. A field that fails never reaches its method.

## The whole form: `clean`, `_clean_form` and `_post_clean`

`BaseForm._clean_form` calls `BaseForm.clean` once every field has been cleaned, whether or not any failed, so a `clean` finds in `cleaned_data` only the fields that passed. In `BaseForm` it returns `cleaned_data` (`django/forms/forms.py:BaseForm._clean_form`, `django/forms/forms.py:BaseForm.clean`).

A `None` from `clean`, unlike one from a field's method, leaves `cleaned_data` as it is; anything else replaces it whole. A `ValidationError` it raises goes to `add_error` with no field, which files an error made from a message or a list under `"__all__"`, the constant `NON_FIELD_ERRORS`, and one made from a dictionary under its keys. On a model form the inherited `BaseModelForm.clean` switches on the unique checks and the constraints, and an override that does not call it goes without them ([Model forms: `ModelForm` and `fields_for_model`](model-forms.md)).

A form for a stay adds a departure and a check of the two dates:

```python
# harbour/fleet/forms.py
class StayForm(BerthForm):
    departs = forms.DateField()

    def clean(self):
        cleaned_data = super().clean()
        arrives, departs = cleaned_data.get("arrives"), cleaned_data.get("departs")
        if arrives and departs and departs < arrives:
            self.add_error("departs", "A ship cannot leave before it arrives.")
```

```python
>>> form = StayForm({"ship": "heron", "tonnage": "0", "arrives": "2026-10-20", "departs": "2026-10-18"})
>>> form.is_valid()
False
>>> form.errors.as_data()
{'tonnage': [ValidationError(['Ensure this value is greater than or equal to 1.'])], 'departs': [ValidationError(['A ship cannot leave before it arrives.'])]}
>>> form.cleaned_data
{'ship': 'Heron', 'arrives': datetime.date(2026, 10, 20)}
```

The tonnage failed in its field and the departure in the form's check. Both are filed by field, in the order they were found, and neither is left in `cleaned_data`, which `clean`, returning `None`, kept.

Last, whatever was found, runs `BaseForm._post_clean`: a hook that does nothing in `BaseForm` and in which a model form fills its instance and has it validated (`django/forms/forms.py:BaseForm._post_clean`).

## `BaseForm.add_error`

`BaseForm.add_error` files every error a form's validation finds, and a `clean` or a view may call it too (`django/forms/forms.py:BaseForm.add_error`); a model formset writes its unique checks' errors into its forms directly ([Model formsets and inline formsets](model-formsets.md)). It takes a field's name or `None`, and an error: a `ValidationError`, or a message, a list or a dictionary of names, which it makes one ([Validating an instance](../models/validation.md#the-error-that-is-raised)).

An error made from a dictionary carries its own names, and the field must be `None`: given a name too, the method raises `TypeError`. Any other error is filed under the name given, or `"__all__"` for `None` or an empty name. Then, for each name:

1. A name that is neither `"__all__"` nor a field of the form raises `ValueError`.
2. The first error under a name makes its list, of the form's `error_class`: for `"__all__"` with the extra class `"nonfield"`, and for a field with `field_id`, the field's `BoundField.auto_id`.
3. The errors are added to the list, as `ValidationError` objects.
4. The name is taken out of `cleaned_data`, if it is there.

`add_error` reads `errors`, so a call before the validation runs it first, and a call after it, from a view, leaves the form not valid. On an unbound form, which has no `cleaned_data`, the call files the error and then fails with `AttributeError`.

`BaseForm.has_error` says whether a field, or `"__all__"`, has an error, and, given a code, whether one of its errors has that code (`django/forms/forms.py:BaseForm.has_error`). `BaseForm.non_field_errors` returns the list under `"__all__"`, or an empty list of the class `"nonfield"` (`django/forms/forms.py:BaseForm.non_field_errors`). A bound field's `errors` is the list under its name, or an empty one ([`BoundField`: a field in a form](bound-fields.md)).

## `has_changed` and `changed_data`

`BaseForm.changed_data` lists the fields whose data differs from their initial values, and `BaseForm.has_changed` says whether it lists any (`django/forms/forms.py:BaseForm.changed_data`). Each bound field answers by `Field.has_changed`, given its data and its initial value, which a field with `show_hidden_initial` reads from a hidden input in the data (`django/forms/boundfield.py:BoundField._has_changed`, `django/forms/fields.py:Field.has_changed`). `changed_data` is a cached property, worked out once.

Validation reads it for the short cut of `empty_permitted`. A formset counts an extra form that has not changed as empty ([Formsets: `BaseFormSet` and the management form](formsets.md)). A model formset saves the forms that have changed and records each changed object with its `changed_data` ([Model formsets and inline formsets](model-formsets.md)) (`django/forms/formsets.py:BaseFormSet.full_clean`, `django/forms/models.py:BaseModelFormSet.save_existing_objects`).

## `ErrorDict` and `ErrorList`

A form's errors are an `ErrorDict`, a `dict` from names to lists that keeps a renderer, and each list is of the form's `error_class`, an `ErrorList` unless the form was given another (`django/forms/utils.py:ErrorDict`, `django/forms/utils.py:ErrorList`). The list keeps in `data` the `ValidationError` objects that `add_error` gives it, or plain strings, and shows messages: indexing gives an error's message with its parameters put in, and a string as it is; since iteration, `repr`, `in` and `==` all go through indexing, a list of errors prints and compares as a list of strings. `ErrorList.as_data` gives each entry as a `ValidationError`. The class derives from `list` as well as `collections.UserList` only so that `isinstance` takes it for a list, for backward compatibility, a comment says, citing ticket 17413.

Both answer the same methods, `as_json`, `as_text`, `as_ul` and `str` from `RenderableErrorMixin` and its base (`django/forms/utils.py:RenderableErrorMixin`):

| method | an `ErrorList` | an `ErrorDict` |
|---|---|---|
| `as_data` | its entries as `ValidationError` objects | each name's `as_data` |
| `get_json_data` | a message and a code, or `""`, for each error | each name's `get_json_data` |
| `as_json` | `get_json_data` as JSON | the same |
| `as_text` | a line for each message | each name, its messages under it |
| `as_ul`, `str` | a `<ul>` of the messages | a `<ul>` with each name and its list |

*What a form's errors give. The last two rows are drawn by the form's renderer, by default from the templates under `django/forms/templates/django/forms/errors/`.*

A list's `error_class` is the CSS class of its `<ul>`: `"errorlist"`, then any it was made with, `"nonfield"` for a form's own errors. Its `field_id` gives the `<ul>` an id, `"id_departs_error"` for StayForm's departure, which the input's `"aria-describedby"` names ([`BoundField`: a field in a form](bound-fields.md)). `ErrorList.copy` keeps the class and the renderer; `BaseForm.get_context` adds to a copy of the non-field errors each hidden field's errors, the field's name in front ([Rendering a form: renderers and templates](rendering.md)) (`django/forms/forms.py:BaseForm.get_context`).

`ErrorList.__reduce_ex__`, which pickling and deep copying call, drops the iterator a `list` adds to its reduction for filling the copy again, which the same comment says would give duplicate entries, citing ticket 23594 (`django/forms/utils.py:ErrorList.__reduce_ex__`).

> **Trap.** A pickle of the errors takes the form's renderer along, and the default renderer's template engine, made when it first draws, does not pickle: a form's errors pickle until the default renderer has drawn anything in the process, a form or only a list of errors, and not after (`django/forms/renderers.py:EngineMixin.engine`).
