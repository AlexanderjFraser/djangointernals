---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Model forms: `ModelForm` and `fields_for_model`

A `ModelForm` makes its fields from a model's when its class is made, by `ModelFormMetaclass` and `fields_for_model`, and works on one instance: `model_to_dict` makes the instance initial values, `construct_instance` copies the cleaned values back onto it, `BaseModelForm._post_clean` has it validate itself, and `BaseModelForm.save` writes it.

A form for a model would otherwise repeat the model: each value's type, whether it may be blank, what it is called. A model form asks the model, once, when its class is made. At each request it holds one instance, shows its values, puts what it cleaned back on it, and lets the model judge it before the row is written. For ShipForm of [Forms](../forms.md):

```text figure=round-trip
class ShipForm(ModelForm): once, by ModelFormMetaclass
    fields_for_model(Ship, ["name", "tonnage", "home"])
        each model field's formfield()  ->  CharField, IntegerField, ModelChoiceField

ShipForm(data, instance=endeavour): BaseModelForm.__init__
    model_to_dict(endeavour)  ->  initial {"name": "Endeavour", "tonnage": 366, "home": 1}

form.is_valid()  ->  BaseForm.full_clean
    the fields cleaned; clean(), where BaseModelForm.clean sets two flags
    BaseModelForm._post_clean
        _get_validation_exclusions  ->  {"id", "captain"}: not on the form
        construct_instance: the cleaned values set on endeavour, file fields last
        endeavour.full_clean(exclude, validate_unique=False, validate_constraints=False)
        validate_unique  ->  Model.validate_unique(exclusions anew), if its flag is set
        validate_constraints  ->  Model.validate_constraints(exclusions anew), if its flag is set
        each ValidationError  ->  _update_errors  ->  the form's errors

form.save(): BaseModelForm.save
    endeavour.save()
    BaseModelForm._save_m2m: then the many-to-many values (ShipForm has none)
```

*A Ship through ShipForm, in the order the calls are made: the cleaned values reach the instance before it is validated, and the row is saved before the many-to-many values.*

## The class: `ModelFormMetaclass`

`ModelForm` is `BaseModelForm` with `ModelFormMetaclass`, which first lets `DeclarativeFieldsMetaclass` collect the declared fields ([Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`](declaring.md)). It then reads the inner `Meta`, a parent's if the class has none, into a `ModelFormOptions`, kept as `BaseModelForm._meta` (`django/forms/models.py:ModelFormOptions`).

It refuses at class time (`django/forms/models.py:ModelFormMetaclass.__new__`). A string as `fields`, `exclude` or `localized_fields`, other than `"__all__"`, raises `TypeError`: a likely `('foo')` for `('foo',)`, says the comment. A `Meta` that names a model but neither `fields` nor `exclude` raises `ImproperlyConfigured`. Then `fields_for_model` is called with `Meta` and the declared fields, `"__all__"` (`ALL_FIELDS`) given as `None`, which it reads as every field. A name in `fields` that is neither a model field nor declared raises `FieldError`.

Last, the declared fields are laid over the result: one named after a model field the form takes stands in its place, any other is added after the rest unless `fields` places it, and each stays even when `exclude` names it. That is `BaseForm.base_fields`.

## Which fields, in what order: `fields_for_model`

`fields_for_model` takes the model's concrete fields, the private ones that are model fields, and the many-to-many ones, sorted together by the counter each takes when made: first those Django makes itself, such as the implicit key, then the others in the order they were made, ordinarily that of declaration (`django/forms/models.py:fields_for_model`, `django/db/models/fields/__init__.py:Field.__lt__`). It passes over a field that is not editable, and raises `FieldError` if `fields` names it and `exclude` does not. It passes over a field outside `fields` or inside `exclude`, and takes the form's own field where it declares one.

Every other model field is asked for its form field, with its entries in the dictionaries of `Meta` as keyword arguments: the widget, the label, the help text, the messages, the class, and `localize=True` where `localized_fields` names it or is `"__all__"`. A `formfield_callback` in `Meta` is called in place of the field's `formfield`. An answer of `None` drops the field silently: `AutoFieldMixin.formfield` answers so, and a ShipForm whose `fields` holds `"id"` has no such field. When `fields` was given, the dictionary is remade in its order, a name not filled mapping to `None`, which the metaclass reads as unknown.

## What the model field gives: `formfield`

A model field makes its own form field (`django/db/models/fields/__init__.py:Field.formfield`) ([A field: the base class](../models/fields.md)). In the base class `required` is the negation of `blank`, and the label is `verbose_name` with a capital. A default becomes the initial value; a callable one is passed uncalled, with `show_hidden_initial=True`: the form calls it for the initial, and a hidden input holds the value shown, which `BoundField._has_changed` reads back ([`BoundField`: a field in a form](bound-fields.md)). A field with choices becomes a `TypedChoiceField` that coerces with the model field's `to_python`, has `None` as its empty value when the field is nullable, and offers a blank choice unless the field may not be blank and has a default or is given an initial value. The caller's arguments override these, and the class is `CharField` unless one is given (`django/forms/fields.py:CharField`); but a field with choices gets its choice class whatever it was given, so `field_classes` does not reach it.

The field classes override `formfield` ([The field classes](../models/field-types.md)). ShipForm's tonnage, a `PositiveIntegerField`, becomes an `IntegerField` with a `min_value` of 0 (`django/db/models/fields/__init__.py:PositiveIntegerField.formfield`), and its home a `ModelChoiceField` over the ports' default manager (`django/db/models/fields/related.py:ForeignKey.formfield`).

## An instance in the form: `BaseModelForm.__init__`

`BaseModelForm.__init__` takes a form's arguments and an instance (`django/forms/models.py:BaseModelForm.__init__`). Without one it makes a new instance of the model. With one, `model_to_dict` reads the editable fields that `Meta` allows, each by the field's `value_from_object`: the attribute under its attname, a foreign key's key, or a many-to-many field's list of objects (`django/forms/models.py:model_to_dict`). For Endeavour that is `{'name': 'Endeavour', 'tonnage': 366, 'home': 1}`. The `initial` argument is laid over what was read.

The method sets `BaseModelForm._validate_unique` and `BaseModelForm._validate_constraints` false. Only `BaseModelForm.clean` sets them true, so that, says the comment, a form that overrides `clean` without calling it gets neither check. Last, it applies each field's `limit_choices_to` to the queryset of the form's own copy (`django/forms/models.py:apply_limit_choices_to_to_formfield`), which the metaclass told `fields_for_model` not to do: a callable, says the comment in `RelatedField.formfield`, is called when the form is made (`django/db/models/fields/related.py:RelatedField.formfield`) ([Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](choices.md)).

## The cleaned values onto the instance: `construct_instance`

`BaseModelForm._post_clean`, after the form's fields and its `clean`, copies the cleaned values onto the instance with `construct_instance` before validating it (`django/forms/models.py:construct_instance`). `construct_instance` takes the model's fields but the many-to-many ones, and passes over one that is not editable, is an auto-incremented key, is outside `fields` or inside `exclude`, or is missing from `cleaned_data`, as a field that failed is. Each value is set by the model field's `save_form_data`: an assignment, except that a file field takes `None` to mean the file stands ([File fields](../models/files.md)).

Two rules, each with a comment, shape it. A field with a default is left as the instance has it when its widget says the value was omitted from the data and the cleaned value is empty. Checkboxes are the exception, being left out of the data when not ticked, so `CheckboxInput.value_omitted_from_data` and the select-multiple widgets always answer `False` ([Widgets: `Widget` and its subclasses](widgets.md)). And file fields are set last, so that a callable `upload_to` can use the other values.

## The instance validated: `BaseModelForm._post_clean`

`BaseModelForm._post_clean` then has the instance validate itself in three calls that [Validating an instance](../models/validation.md) takes apart, each leaving out the names `BaseModelForm._get_validation_exclusions` gives, among them the fields not on the form, for ShipForm the key and the captain, and those that already have an error: `Model.full_clean` without unique checks and constraints, then `BaseModelForm.validate_unique` and `BaseModelForm.validate_constraints`, each if its flag is set (`django/forms/models.py:BaseModelForm._post_clean`). The last two ask anew, so a field the model refused is left out of them too.

The form passes a tonnage of 0, its field's minimum, which the model's check constraint refuses, and a name that Valletta, port 1, already has, which the unique constraint refuses:

```python
# a shell, with ShipForm from harbour/fleet/forms.py
>>> endeavour = Ship.objects.get(name="Endeavour")
>>> form = ShipForm({"name": "Beagle", "tonnage": "0", "home": "1"}, instance=endeavour)
>>> form.errors.as_data()
{'__all__': [ValidationError(['Constraint “ship_has_tonnage” is violated.']), ValidationError(['Ship with this Name and Home already exists.'])]}
>>> endeavour.name, endeavour.tonnage
('Beagle', 0)
```

> **Trap.** Nothing undoes `construct_instance`: an instance given to a form that fails keeps the submitted values, as Endeavour does, though its row is unchanged.

Each `ValidationError` from the instance passes through `BaseModelForm._update_errors`, where the form's messages override the model's: an error takes the form field's message for its code, or, under `"__all__"`, the one under `NON_FIELD_ERRORS` in the `error_messages` of `Meta`. Then it goes to `BaseForm.add_error` (`django/forms/models.py:BaseModelForm._update_errors`) ([Validation: `full_clean`, `cleaned_data` and the errors](validation.md)).

## Saving: `BaseModelForm.save`

`BaseModelForm.save` asks for the errors and raises `ValueError` if there are any: `"The Ship could not be created because the data didn't validate."`, or "changed" for an instance not being added (`django/forms/models.py:BaseModelForm.save`). Otherwise it saves the instance, and then `BaseModelForm._save_m2m` gives each many-to-many field in `cleaned_data` to its `save_form_data`, which calls the related manager's `set` (`django/db/models/fields/related.py:ManyToManyField.save_form_data`) ([Many-to-many relations](../models/many-to-many.md)); that manager raises `ValueError` for an instance with no primary key (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`). Private fields with a `save_form_data` go too: a `GenericRelation`, says a comment, was once a fake many-to-many field. With `commit=False` nothing is written: the instance comes back unsaved, and the form gets `BaseModelForm.save_m2m`, the bound `_save_m2m`, to call once the caller has saved it.

## A model form made by a call: `modelform_factory`

`modelform_factory` builds a `Meta` with `type` from its arguments, on the base of the form's own `Meta` if it has one, refuses with `ImproperlyConfigured` a `Meta` with neither `fields` nor `exclude`, and calls the form's metaclass for a class named after the model: `modelform_factory(Ship, fields=["name"])` is named ShipForm (`django/forms/models.py:modelform_factory`). Its callers are `ModelFormMixin.get_form_class` ([The form views](../views/editing.md)), `modelformset_factory` ([Model formsets and inline formsets](model-formsets.md)) and the admin, which passes `"__all__"` when it has no fields and `modelform_defines_fields` finds no `_meta` on the form, or neither `fields` nor `exclude` in it (`django/forms/models.py:modelform_defines_fields`) ([The admin's forms: `get_form` and `formfield_for_dbfield`](../admin/admin-forms.md)).
