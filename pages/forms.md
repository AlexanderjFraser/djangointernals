---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Templates, forms and services
contents: declaring, fields, validation, validators, field-types, widgets, choices, bound-fields, rendering, media, formsets, model-forms, model-formsets
---

# Forms

Django's forms turn the strings a browser submits into checked Python values, and values back into HTML inputs. A form class declares its fields; each instance copies them and, bound to submitted data, cleans each value through the field's widget, the field and its validators before the form's own checks run. Formsets repeat one form over many rows, and a model form makes its fields from a model's and writes what it cleaned back onto an instance.

When a browser submits a form, the request's body is a flat set of strings keyed by the names of the inputs: `"ship=++heron+&tonnage=0&arrives=2026-10-20"`. The view that receives it wants a ship's name as a string with its stray spaces gone, a tonnage as a whole number above nothing, and an arrival as a `date`; or else, for each value that will not do, a message to show beside its input, with what was typed still in it. The first time the page is shown, the same inputs are wanted empty, or filled with values the view already has. The forms library is the one declaration that serves all of this: what each input is, how its string becomes a value, what the value must satisfy, and how the input is drawn again.

A form never reads a request. A view hands it `POST` and `FILES` from the request ([The body: `body`, `POST` and `FILES`](http/body.md)) and gets back values, errors and HTML. A form has the template engines draw its HTML, and a model form has the model validate and save its instance.

## The objects

A form is made of fields, and each field of a widget; around them stand the objects that join a field to one form, check its value and draw it (`django/forms/fields.py:Field`, `django/forms/widgets.py:Widget`).

| object | what it is | made |
|---|---|---|
| `Form` | a class of fields, declared as class attributes; an instance holds its own copy of them, the submitted data, the initial values and the errors | the class once; an instance for each request |
| `Field` | one value: how its string becomes a Python value, and what that value must satisfy; it holds a widget, a label, an initial value, messages and validators | with its form class, and copied for each instance |
| `Widget` | the HTML of a field's input, or inputs, and how its value is read back out of the submitted data | with its field, and copied with it |
| `BoundField` | a field joined to one form: its name in the data, the value to show, its errors and its label | when the form is first asked for it by name |
| a validator | a callable that raises `ValidationError` when a value will not do | with its module or its field class, and shared; or with the field, from the field's arguments |
| `ErrorDict`, `ErrorList` | a form's errors, by field name, which draw themselves as HTML | when the form is validated |
| a renderer | draws forms, fields, widgets and errors from templates | at its first use, and kept; or given to a form |
| `BaseFormSet` | many forms of one class, counted by a management form | a class from `formset_factory`; an instance for each request |
| `ModelForm` | a form whose fields are made from a model's, and which fills, validates and saves an instance | the class once, from its `Meta` |

*The objects of `django.forms`. `Field` here is `django/forms/fields.py:Field`; a model's field is a different class, which makes one of these.*

## A class of fields, and an instance bound to data

A form is declared as a class whose attributes are fields. The berth office of a port might take requests on this one:

```python
# harbour/fleet/forms.py
from django import forms


class BerthForm(forms.Form):
    ship = forms.CharField(max_length=60)
    tonnage = forms.IntegerField(min_value=1)
    arrives = forms.DateField()

    def clean_ship(self):
        return self.cleaned_data["ship"].title()
```

The class's metaclass, `DeclarativeFieldsMetaclass`, takes every attribute that is a field out of the class body before the class is made, so that BerthForm has no attribute named ship, and collects them, after those of its bases, in a dictionary, `BaseForm.base_fields` ([Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`](forms/declaring.md)) (`django/forms/forms.py:DeclarativeFieldsMetaclass`). Each instance then deep-copies that dictionary into a `fields` of its own, each field with its widget, so that one form can change its fields without changing them for every other; a comment at the copy says so (`django/forms/forms.py:BaseForm.__init__`).

A form is **bound** when it is made with data or files, even an empty dictionary, and **unbound** otherwise (`django/forms/forms.py:BaseForm.__init__`). An unbound form is only drawn, with its initial values; it is never valid, and validating it finds no errors.

A form is asked for one of its fields by name, `form["tonnage"]`, and answers with a **bound field**, a `BoundField` that joins the field to this form; it is made the first time it is asked for and kept (`django/forms/forms.py:BaseForm.__getitem__`). A field holds nothing about any form. The bound field knows the input's name in the data (`"tonnage"`, or `"berth-tonnage"` for a form made with `prefix="berth"`), the value to show in it, its errors and its label ([`BoundField`: a field in a form](forms/bound-fields.md)).

## Validation: from strings to values

Validation runs the first time something needs its result. `BaseForm.errors` calls `BaseForm.full_clean` if the errors are not yet known, and `BaseForm.is_valid` asks a bound form for them; once made, they are kept (`django/forms/forms.py:BaseForm.errors`, `django/forms/forms.py:BaseForm.is_valid`).

```text figure=full-clean
form.is_valid()  ->  form.errors  ->  BaseForm.full_clean    (the first time only)

  not bound:  stop, with no errors; is_valid() answers False without asking

  _clean_fields: each field in order, here the tonnage
      BoundField.data       the widget reads the data:  value_from_datadict(data, files, "tonnage")  ->  "0"
      Field.clean
          to_python         "0"  ->  0                  or an error "invalid"
          validate          empty, and required?        an error "required"
          run_validators    MinValueValidator(1)        an error "min_value"
      clean_tonnage         the form's method for the field, if it has one
      a value           ->  cleaned_data["tonnage"]
      a ValidationError ->  errors["tonnage"], and the field left out of cleaned_data

  _clean_form:  the form's clean()       an error of no one field goes under "__all__"
  _post_clean:  nothing on a plain form; a model form fills and validates its instance

  ->  errors (an ErrorDict) and cleaned_data
```

*What asking whether a form is valid sets off. Each field's string is read from the data by its widget, made a Python value by its field and checked, and put in `cleaned_data` for the form's own method for that field; an error at any step is kept under the field's name and the field is left out of `cleaned_data`. Then come the checks of the whole form.*

`BaseForm.full_clean` takes the fields in their order. For each that is not disabled, the bound field asks the field's widget for the value. Most widgets look their name up in the data; a checkbox that was not ticked is not in the data at all and reads as `False`, and a widget made of several inputs reads several names ([Widgets: `Widget` and its subclasses](forms/widgets.md)) (`django/forms/widgets.py:Widget.value_from_datadict`). Then `Field.clean` runs three steps. `Field.to_python`, as a field class overrides it, turns the string into a value of the field's type, or raises an error, usually with the code `"invalid"`. `Field.validate` makes the checks built into the field, which in the base class is only that a required field is not empty. `Field.run_validators` calls every validator of the field on a value that is not empty, and gathers all their errors (`django/forms/fields.py:Field.clean`). If the form has a method whose name is `"clean_"` and the field's name, it runs next, and what it returns replaces the cleaned value. A value that passes goes into `cleaned_data`; a `ValidationError` from any step goes into the form's errors under the field's name, by way of `BaseForm.add_error`, and the field is left out of `cleaned_data` (`django/forms/forms.py:BaseForm._clean_fields`).

Then the form's own `BaseForm.clean` runs, for checks that need more than one field. An error it raises is kept under `"__all__"`, the constant `NON_FIELD_ERRORS`, as belonging to no one field, unless it was made from a dictionary of field names; a dictionary it returns replaces `cleaned_data`. Last comes `BaseForm._post_clean`, which does nothing on a plain form and is where a model form fills its instance and has it validated (`django/forms/forms.py:BaseForm._clean_form`) ([Validation: `full_clean`, `cleaned_data` and the errors](forms/validation.md)).

Given the submission above, the form answers so:

```python
>>> form = BerthForm({"ship": "  heron ", "tonnage": "0", "arrives": "2026-10-20"})
>>> form.is_valid()
False
>>> form.errors.as_data()
{'tonnage': [ValidationError(['Ensure this value is greater than or equal to 1.'])]}
>>> form.cleaned_data
{'ship': 'Heron', 'arrives': datetime.date(2026, 10, 20)}
```

The ship's name was stripped of its spaces by `CharField.to_python` and given its capital by the form's method for that field. The tonnage was turned into the number 0 by `IntegerField.to_python` and refused by the `MinValueValidator` that `min_value=1` gave the field. The date was parsed by `DateField`. The message is the validator's own, because the field's `error_messages` has none for its code, `"min_value"`; a field's message for a code replaces a validator's ([Validators: `django/core/validators.py`](forms/validators.md)) (`django/forms/fields.py:Field.run_validators`).

## Drawing: from values to HTML

A form, a bound field, a widget and a list of errors each draw themselves from a template. `str(form)` calls `RenderableMixin.render`, which has the form's **renderer** render a template with a context that the form makes, and marks the result safe (`django/forms/utils.py:RenderableMixin.render`). Unless a form is given a renderer, or its class names one in `BaseForm.default_renderer`, it uses the one that the setting `FORM_RENDERER` names, made at its first use and kept. By default that is `django.forms.renderers.DjangoTemplates`, which keeps a template engine of its own, apart from those of `TEMPLATES`, that finds templates in `django/forms/templates/` and in the installed applications (`django/forms/renderers.py:get_default_renderer`, `django/forms/renderers.py:EngineMixin.engine`).

The templates nest ([Rendering a form: renderers and templates](forms/rendering.md)). The form's template, `"django/forms/div.html"` by default, writes the errors that belong to no field, with those of the hidden fields among them, and then a `<div>` for each visible field, with the hidden fields inside the last. Each field is drawn, by default, by `"django/forms/field.html"`, which writes its label, its help text, its errors and its widget. The widget is drawn by a template of its own, `"django/forms/widgets/number.html"` for a number input, which includes `"django/forms/widgets/input.html"`, the template that writes an `<input>` element.

What a widget shows is where the two halves of the system meet. An unbound form shows each field's initial value; a bound one ordinarily shows the data that was submitted, as it was typed, and not the cleaned value, though a disabled field and a file field show their initial value still (`django/forms/boundfield.py:BoundField.value`, `django/forms/fields.py:Field.bound_data`). After the submission above, the ship's input still holds `"  heron "`, spaces and all, and the tonnage's is drawn as:

```html
<input type="number" name="tonnage" value="0" min="1" required aria-invalid="true" aria-describedby="id_tonnage_error" id="id_tonnage">
```

The `"min"` came from the field, which put it on its widget when the field was made (`django/forms/fields.py:IntegerField.widget_attrs`). The bound field added the rest as it drew: `"required"` because the field is required, and `"aria-invalid"` and `"aria-describedby"` because it has errors (`django/forms/boundfield.py:BoundField.build_widget_attrs`); then the `"id"`, from the form's `auto_id`, `"id_%s"` unless the form is given another (`django/forms/boundfield.py:BoundField.as_widget`).

## Formsets and model forms

A **formset** is a set of forms of one class on one page, as when the berths of several ships are asked for at once ([Formsets: `BaseFormSet` and the management form](forms/formsets.md)). `formset_factory(BerthForm, extra=2)` makes a class, named BerthFormSet, whose instances make their forms with the prefixes `"form-0"`, `"form-1"` and so on, so that every input on the page has a name of its own: `"form-0-ship"`. How many forms were submitted is submitted too, in the hidden inputs of a **management form**, `"form-TOTAL_FORMS"` and `"form-INITIAL_FORMS"` among them. A bound formset makes as many forms as that count says, but never more than a limit, `BaseFormSet.absolute_max`, which a comment calls protection against a client that would have the server make any number of forms (`django/forms/formsets.py:BaseFormSet.total_form_count`). A formset is valid when each of its forms is valid, those marked for deletion aside, and it has no errors of its own: a management form missing or invalid, too many or too few forms, or what its `clean` raised (`django/forms/formsets.py:BaseFormSet.is_valid`).

A **model form** is a form whose fields are made from a model's ([Model forms: `ModelForm` and `fields_for_model`](forms/model-forms.md)):

```python
# harbour/fleet/forms.py
from harbour.fleet.models import Ship


class ShipForm(forms.ModelForm):
    class Meta:
        model = Ship
        fields = ["name", "tonnage", "home"]
```

Its metaclass, `ModelFormMetaclass`, reads `Meta`, refuses one that names a model but neither `fields` nor `exclude` (`django/forms/models.py:ModelFormMetaclass.__new__`), and asks each model field it is to use for a form field, ordinarily by calling the model field's `formfield`, which makes the field's `blank` into `required`, its `verbose_name` into the label and its default into the initial value (`django/forms/models.py:fields_for_model`, `django/db/models/fields/__init__.py:Field.formfield`). For ShipForm the name becomes a `CharField`, the tonnage an `IntegerField`, and the home port, a foreign key, a `ModelChoiceField` drawn as a `Select` whose options are the ports in the database ([Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](forms/choices.md)).

A model form made with an instance takes its initial values from the instance's fields (`django/forms/models.py:model_to_dict`). Its `BaseModelForm._post_clean` copies the cleaned values onto the instance and has the instance validate itself, leaving out what the form has already found wrong, as [Validating an instance](models/validation.md) tells. `BaseModelForm.save` saves the instance and then its many-to-many values; with `commit=False` it returns the instance unsaved and gives the form a method, `BaseModelForm.save_m2m`, to call when the instance has been saved (`django/forms/models.py:BaseModelForm.save`). Model formsets and inline formsets put the two ideas together: a model form for each object of a queryset, or for each object whose foreign key points at one parent ([Model formsets and inline formsets](forms/model-formsets.md)).

## Where forms meet the rest of Django

A form gets the request's `POST` and `FILES`, parsed on first use ([Multipart parsing and upload handlers](http/uploads.md)). The generic views `FormView`, `CreateView` and `UpdateView` run the cycle of showing a form, checking it and redirecting, and `ModelFormMixin` makes its form class with `modelform_factory` when it is given none ([The form views](views/editing.md)). A form's HTML is drawn by the template engines ([Template engines: `TEMPLATES` and the backends](templates/engines.md)) and comes out as a safe string, which a template prints without escaping again ([Autoescaping and safe strings](templates/autoescape.md)). A model field makes its own form field ([A field: the base class](models/fields.md)), and a file field takes what a form's file field cleaned ([File fields](models/files.md)). A `ModelChoiceField` draws its options from a queryset, evaluated anew each time they are drawn ([QuerySets](querysets.md)). The messages of fields and validators are translated, and numbers and dates can be read and written in the reader's locale ([Internationalization and time zones](i18n.md)). The admin edits an object with a model form and inline formsets ([The admin](admin.md)), the authentication forms are forms like any other ([The authentication forms: `AuthenticationForm` and the password forms](auth/user-forms.md)), `django.contrib.postgres` adds fields and widgets of its own ([PostgreSQL fields: `ArrayField`, the range fields and hstore](contrib/postgres-fields.md)), and the test framework checks a form's errors with `SimpleTestCase.assertFormError` ([Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`](testing/response-assertions.md)). The token against cross-site request forgery is not a form field: a template tag writes it and a middleware checks it ([Security](security.md)).
