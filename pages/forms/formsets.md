---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Formsets: `BaseFormSet` and the management form

A formset is a set of forms of one class on one page, each under a numbered prefix, `"form-0"`, `"form-1"`, and counted by a hidden `ManagementForm`. `formset_factory` makes the class; `BaseFormSet` reads the count, makes the forms, validates them as a set, and says which were marked for deletion or given an order.

A page that asks for the berths of several ships at once repeats one form's inputs, and the browser submits them as one flat set of strings. The server must tell the rows apart, learn how many were sent, know which stood for values the view already had, and let a blank new row stay blank. The prefixes tell the rows apart; the rest comes from numbers sent in the hidden inputs of the management form.

## The class: `formset_factory`

`formset_factory` makes a formset class with `type`: a subclass of `BaseFormSet`, or of the formset class it is given, whose class attributes are its other arguments (`django/forms/formsets.py:formset_factory`). The form class becomes `BaseFormSet.form`, and `BaseFormSet.extra`, `BaseFormSet.min_num`, `BaseFormSet.max_num` and the rest are what the methods read; the body of `BaseFormSet` sets none of them. The class is named for the form: `"Set"` is added to a name that ends in `"Form"`, `"FormSet"` to any other.

```python
# harbour/fleet/forms.py
from django.forms import formset_factory

BerthFormSet = formset_factory(BerthForm, extra=2, can_delete=True)
```

Unless given, `extra` is 1, `min_num` 0 and `max_num` 1000, `DEFAULT_MAX_NUM`, there, a comment says, to prevent memory exhaustion. `BaseFormSet.absolute_max` defaults to `max_num` plus 1000, and a `max_num` above it is a `ValueError`.

An instance is bound as a form is, when given data or files (`django/forms/formsets.py:BaseFormSet.__init__`). Its prefix is `"form"` unless given another, from `BaseFormSet.get_default_prefix`, which an inline formset overrides; its `initial` is a list of dictionaries, the first forms' initial values in order. `BaseFormSet.form_renderer` is the factory's renderer or `None`, and is given to each form, which with none chooses its own; `BaseFormSet.renderer` is that one or the default, and draws the formset, its management form and its own errors.

## One submission, read

A bound formset is given the whole of `POST`, the management form's keys beside every form's. BerthFormSet read two berths, the second marked for deletion, so:

```text figure=formset-data
the data, flat                  how BerthFormSet reads it
"form-TOTAL_FORMS":   "2"       1. the management form, prefix "form", reads these four keys:
"form-INITIAL_FORMS": "0"          TOTAL_FORMS 2, INITIAL_FORMS 0; the other two unused
"form-MIN_NUM_FORMS": "0"
"form-MAX_NUM_FORMS": "1000"    2. the count: the smaller of 2 and absolute_max, 2000
"form-0-ship":    "heron"       3. form 0, prefix "form-0", reads only its own keys:
"form-0-tonnage": "120"            ship "Heron", tonnage 120, arrives 2026-10-20, DELETE False
"form-0-arrives": "2026-10-20"
"form-1-ship":    "beagle"         form 1, prefix "form-1", reads only its own keys:
"form-1-tonnage": "0"              an error, tonnage below 1; DELETE True, so the error is left out
"form-1-arrives": "2026-10-21"
"form-1-DELETE":  "on"          4. errors [{}], for form 0 only; is_valid() True; deleted_forms [form 1]
```

*How BerthFormSet reads one flat submission: the management form first, for the count; then each form, reading the keys under its own prefix; then the set as a whole.*

## The management form: `ManagementForm`

`ManagementForm` is a form of four hidden `IntegerField`s (`django/forms/formsets.py:ManagementForm`, `django/forms/fields.py:IntegerField`). `"TOTAL_FORMS"` and `"INITIAL_FORMS"` are required; `"MIN_NUM_FORMS"` and `"MAX_NUM_FORMS"` are not, and a comment says they are written out only for code in the browser, their submitted values unchecked: nothing compares them with the formset's limits, but one that is not a whole number makes the management form invalid.

`BaseFormSet.management_form` makes it once, with the formset's prefix (`django/forms/formsets.py:BaseFormSet.management_form`): unbound, with the formset's counts and limits as initial values; bound, from the formset's data, and cleaned at once. A count missing or not a whole number `ManagementForm.clean` sets to 0, because, its comment says, when the management form is invalid the number of forms submitted is not known. Data with no management form makes no forms, and an error that names the inputs at fault:

```python
>>> formset = BerthFormSet({"form-0-ship": "heron"})
>>> formset.non_form_errors().as_data()
[ValidationError(['ManagementForm data is missing or has been tampered with. Missing fields: form-TOTAL_FORMS, form-INITIAL_FORMS. You may need to file a bug report if the issue persists.'])]
```

## Counting the forms

A formset's first forms are its **initial forms**, which stand for values the view already had; the rest are its **extra forms**, new and perhaps blank. Two methods count them (`django/forms/formsets.py:BaseFormSet.total_form_count`, `django/forms/formsets.py:BaseFormSet.initial_form_count`).

| count | unbound | bound |
|---|---|---|
| `BaseFormSet.initial_form_count` | the number of dictionaries in `initial` | the management form's `"INITIAL_FORMS"` |
| `BaseFormSet.total_form_count` | the larger of the initial count and `min_num`, plus `extra`; no more than `max_num`, unless the initial forms alone are more | the management form's `"TOTAL_FORMS"`, no more than the absolute maximum |

Unbound, every existing value is shown but, a comment says, no extra form beyond `max_num`. Bound, the count sent is taken up to the absolute maximum, a guard, a comment says, against clients that would force the server to make any number of forms. `max_num` alone limits no submission: three forms sent with `max_num=2` make a valid formset without `validate_max=True`.

## Making the forms: `forms` and `_construct_form`

`BaseFormSet.forms` makes the forms on first use and keeps them, one for each index below the total count, by `BaseFormSet._construct_form` (`django/forms/formsets.py:BaseFormSet.forms`). Iterating, indexing and the length of a formset are over this list, which `BaseFormSet.initial_forms` and `BaseFormSet.extra_forms` slice.

`_construct_form` gives form i the formset's prefix, a hyphen and i, `"form-0"`; when the formset is bound, its whole data and files, of which the form reads only the keys under its prefix (`django/forms/forms.py:BaseForm.add_prefix`); the i-th dictionary of `initial`, if there is one; and two arguments a form alone seldom has. Keyword arguments from the hook `BaseFormSet.get_form_kwargs`, a copy of `form_kwargs`, override all of these, and `BaseFormSet.add_fields` then adds its fields (`django/forms/formsets.py:BaseFormSet._construct_form`):

- `empty_permitted=True`, for an extra form whose index is not below `min_num`. Such a form skips validation when nothing in it differs from its initial values, and is then valid with an empty `cleaned_data` ([Validation: `full_clean`, `cleaned_data` and the errors](validation.md)). A blank extra row is no error; the initial forms and the first `min_num` are validated even when blank.
- `use_required_attribute=False`, for every form: the comment's reason is that the HTML `"required"` attribute may cause incorrect validation of extra, optional and deleted forms. A form also refuses both arguments true ([Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`](declaring.md)).

## Deleting and ordering: `add_fields`

`BaseFormSet.add_fields` adds fields to each form's own copy of its class's fields, leaving the class untouched (`django/forms/formsets.py:BaseFormSet.add_fields`). With `can_order=True`, it adds `"ORDER"`, an `IntegerField` drawn by `BaseFormSet.ordering_widget`, a `NumberInput`, not required, whose initial value on an initial form is its index plus one. With `can_delete=True`, it adds `"DELETE"`, a `BooleanField` drawn by `BaseFormSet.deletion_widget`, a `CheckboxInput`, not required: on every form, or with `can_delete_extra=False` on the initial forms only (`django/forms/fields.py:BooleanField`). A model formset adds each object's key here too ([Model formsets and inline formsets](model-formsets.md)).

`BaseFormSet.deleted_forms` is the forms whose cleaned `"DELETE"` is true, an extra form that has not changed aside; it is empty when the formset is invalid or cannot delete. `BaseFormSet.ordered_forms` is the forms by their `"ORDER"`, a blank one last, deleted forms and unchanged extra forms left out; it raises `AttributeError` when the formset is invalid or cannot order (`django/forms/formsets.py:BaseFormSet.ordered_forms`).

## The empty form and `"__prefix__"`

`BaseFormSet.empty_form` is a form made afresh at each use, with the prefix `"form-__prefix__"`, `empty_permitted=True` and no `"required"` attributes (`django/forms/formsets.py:BaseFormSet.empty_form`). Never bound and not among the forms, it is a pattern for a script in the browser, which copies it, puts the next index in place of `"__prefix__"`, and, as the docstring of `ManagementForm` asks, adds one to the count. The admin's inline formsets add rows so (`django/contrib/admin/static/admin/js/inlines.js`).

## Validating the set: `full_clean` and `is_valid`

A formset is validated the first time its errors are asked for: `BaseFormSet.errors` and `BaseFormSet.non_form_errors` call `BaseFormSet.full_clean` if it has not run (`django/forms/formsets.py:BaseFormSet.full_clean`). In order:

1. The formset's own errors start as an empty list of its `error_class`, `ErrorList` by default, marked `"nonform"`. An unbound formset stops here.
2. An invalid management form adds the error shown above.
3. Each form is validated, an unchanged extra form counted as empty. A form marked for deletion keeps its errors out of the list.
4. Too many forms: more than `max_num`, deleted forms aside, with `validate_max=True`; or a `"TOTAL_FORMS"` above the absolute maximum, always. The message names `max_num` in both.
5. Too few forms: fewer than `min_num`, deleted and empty forms aside, with `validate_min=True`.
6. `BaseFormSet.clean`, an empty hook for checks across forms.

Steps four and five set deleted forms aside only when the steps before found no error: `BaseFormSet.deleted_forms` is empty for a formset that is not valid. An error raised at the fourth step or later replaces the formset's own errors rather than joining them, and the steps after it do not run.

> **Trap.** So when the management form is missing and the formset's `clean` raises, `non_form_errors()` holds only the error from `clean`.

`BaseFormSet.is_valid` is false for an unbound formset; otherwise it asks every form not marked for deletion, without stopping at the first invalid one, and is true when they are all valid and the formset has no errors of its own (`django/forms/formsets.py:BaseFormSet.is_valid`). `BaseFormSet.total_error_count` adds those errors to the number of fields with errors in each entry of `errors`, a form's `"__all__"` counted as one; `BaseFormSet.has_changed` is true when any form has changed. `all_valid` asks every formset in a list, all of them even after one fails; the admin's add and change view checks its inline formsets with it (`django/forms/formsets.py:all_valid`, `django/contrib/admin/options.py:ModelAdmin._changeform_view`).

## Drawing a formset

`str(formset)` renders the formset's template with the context `{"formset": formset}` ([Rendering a form: renderers and templates](rendering.md)). `BaseFormSet.template_name` is the renderer's `formset_template_name`, `"django/forms/formsets/div.html"` (`django/forms/renderers.py:BaseRenderer`); `as_p` and the other three take `BaseFormSet.template_name_p` and its siblings. Each template writes the management form, then each form by the form's method of the same style, which draws it by the form's `template_name_div` or a sibling, not by the renderer's `form_template_name` (`django/forms/templates/django/forms/formsets/div.html`). None writes the formset's own errors or its empty form.

`BaseFormSet.media` and `BaseFormSet.is_multipart` ask the first form, or the empty form when there are none; a comment says all the forms of a formset are alike ([Form assets: `Media`](media.md)).
