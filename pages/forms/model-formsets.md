---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Model formsets and inline formsets

`BaseModelFormSet` is a formset of model forms: a form for each object of a queryset, extra forms for new objects, and a `save` that updates, inserts and deletes rows to match. `modelformset_factory` makes its class; `inlineformset_factory` makes the class of a `BaseInlineFormSet`, a model formset over the objects whose foreign key points at one parent.

A plain formset knows its forms by position: the third form's inputs are named `"form-2-…"` ([Formsets: `BaseFormSet` and the management form](formsets.md)). Position will not do for the rows of a table: between drawing the page and its submission a row may be added or deleted, and the third object of the queryset may not be the one the third form showed. So each form carries its object's primary key, ordinarily in a hidden input, and the submitted formset finds each object by its key. A model formset also checks its forms against one another for values that must be unique, and its `save` sorts the forms into objects changed, added and deleted.

## The class: `modelformset_factory`

`modelformset_factory` makes a model form class with `modelform_factory`, then a formset class of that form with `formset_factory`, on `BaseModelFormSet`, and sets `BaseModelFormSet.model` and `BaseModelFormSet.edit_only` on it (`django/forms/models.py:modelformset_factory`). First it raises `ImproperlyConfigured` if neither its arguments nor the given form's `Meta` name `fields` or `exclude`. It keeps the defaults of `formset_factory`: one extra form, no deletion.

```python
# harbour/fleet/forms.py
ShipFormSet = forms.modelformset_factory(Ship, fields=["name", "tonnage", "home"])
```

## A form for each object

`BaseModelFormSet.__init__` keeps `initial=` as `BaseModelFormSet.initial_extra`, the initial values of the extra forms, the first for the first: the initial forms take theirs from their objects (`django/forms/models.py:BaseModelFormSet._construct_form`).

`BaseModelFormSet.get_queryset` makes the queryset once: the one given, or the model's default manager's. If it is not `QuerySet.totally_ordered`, it is ordered by its own ordering or the model's and then by `"pk"`, so that, a comment says, every formset made from it has its forms in the same order: Ship's ordering by name becomes `"name"` and `"pk"` (`django/forms/models.py:BaseModelFormSet.get_queryset`) ([Annotations, ordering and the other methods that change the query](../querysets/methods.md)). It is not cut to `BaseFormSet.max_num`; a comment cites ticket 13023, and every existing object is shown (`django/forms/formsets.py:BaseFormSet.total_form_count`).

Unbound, `BaseModelFormSet.initial_form_count` evaluates the queryset to count it, and `_construct_form` gives each form the object at its position (`django/forms/models.py:BaseModelFormSet.initial_form_count`).

### The hidden key

An automatic key has no form field. `BaseModelFormSet.add_fields` gives each form one under the key's name, with the comment that this is how the formset tells which object is which when the data comes back: a `ModelChoiceField` over the default manager of the model, or of the model the key points at, a `HiddenInput` unless `Meta` names a widget for it, not required, and initially the object's key. It does so for a key that is automatic, not editable, or not among the form's fields (`django/forms/models.py:BaseModelFormSet.add_fields`).

```python
>>> formset = ShipFormSet()
>>> [form.instance for form in formset]
[<Ship: Beagle>, <Ship: Endeavour>, <Ship: >]
>>> print(formset[0]["id"])
<input type="hidden" name="form-0-id" value="2" id="id_form-0-id">
```

### Finding each object

Bound, `_construct_form` finds each initial form's object. It reads the key from the data, `"form-0-id"`, converts it with the `to_python` of the key's field, or of the field at the end of its relations, and looks it up in a dictionary of the queryset's objects by key (`django/forms/models.py:BaseModelFormSet._existing_object`). A key that is missing, will not convert, or names no object of the queryset leaves the form with a new instance; of the first two, the comments say the user may have tampered with the data. Then the key's field is made required on each initial form, and a form without its key fails (`django/forms/models.py:BaseModelFormSet._construct_form`).

The hidden field looks the key up again through the default manager, a query for each initial form, and so accepts the key of a row outside the formset's queryset. Such a form still has a new instance, and the row outside is not changed: `save` passes over the instance where it has no key, as a new Ship has none, and inserts it as a new row where the key has a default.

## The forms checked against one another

Each form validates its own instance, and that validation's unique checks and constraints ask the database ([Validating an instance](../models/validation.md)). They cannot see the other forms: two forms that each add a Heron at Valletta each find no such row. `BaseModelFormSet.clean` calls `BaseModelFormSet.validate_unique`, which compares the forms with one another (`django/forms/models.py:BaseModelFormSet.validate_unique`).

It asks the instance of each form that is valid and not marked for deletion for its checks, by `Model._get_unique_checks`, excluding what `BaseModelForm._get_validation_exclusions` excludes and with `include_meta_constraints=True`, which adds the unique constraints without a condition or expressions. For each unique check each form gives a tuple of its cleaned values for the check's fields, an object reduced to its key. A tuple holding `None` is passed over; one already seen is a duplicate. A date check compares the field's value and the date, or its year or month.

The form where a duplicate is found, not the first to hold the values, has its errors under `NON_FIELD_ERRORS` replaced by the message of `BaseModelFormSet.get_form_error`, and the check's fields (of a date check, the field but not the date) taken out of its `cleaned_data`. At the end the method raises a `ValidationError` with a message for each duplicate, which `BaseFormSet.full_clean` keeps as the formset's non-form errors:

```python
>>> data = {"form-TOTAL_FORMS": "2", "form-INITIAL_FORMS": "0",
...         "form-0-name": "Heron", "form-0-tonnage": "100", "form-0-home": "1",
...         "form-1-name": "Heron", "form-1-tonnage": "120", "form-1-home": "1"}
>>> formset = ShipFormSet(data, queryset=Ship.objects.none())
>>> formset.is_valid()
False
>>> formset.non_form_errors()
['Please correct the duplicate data for name and home, which must be unique.']
>>> formset[1].errors.as_data()
{'__all__': [ValidationError(['Please correct the duplicate values below.'])]}
```

## Saving

`BaseModelFormSet.save` saves the initial forms' objects, then the extra forms', and returns those it saved (`django/forms/models.py:BaseModelFormSet.save`). `BaseModelFormSet.save_existing_objects` passes over an initial form whose instance has no key (its comment: an object outside the queryset, or one deleted since). It deletes the object of a form marked for deletion, by `BaseModelFormSet.delete_existing`, and saves a form that has changed, by `BaseModelFormSet.save_existing`; a form that has not changed is not saved (`django/forms/models.py:BaseModelFormSet.save_existing_objects`). `BaseModelFormSet.save_new_objects` saves, by `BaseModelFormSet.save_new`, each extra form that has changed and is not marked for deletion (`django/forms/models.py:BaseModelFormSet.save_new_objects`). On the way they fill `BaseModelFormSet.changed_objects`, each object with the names of its changed fields, `BaseModelFormSet.deleted_objects` and `BaseModelFormSet.new_objects`.

With `commit=False` the instances come back unsaved; an object marked for deletion is listed and not deleted, `delete_existing` deleting only when it commits; and the formset gets a `BaseModelFormSet.save_m2m` that calls each saved form's own. `BaseModelFormSet.edit_only` is read by `save` alone, which then saves no new object; the extra forms are still made, drawn and validated.

## Inline formsets

An inline formset edits the children of one parent. `inlineformset_factory` calls `modelformset_factory` with `BaseInlineFormSet` as the formset, and sets on the class, as `BaseInlineFormSet.fk`, the foreign key from child to parent (`django/forms/models.py:inlineformset_factory`). Its defaults are three extra forms and deletion allowed, and a unique foreign key, as a `OneToOneField` is, makes the maximum one. The key is found by `_get_foreign_key`: the field `fk_name=` names, checked, or else the one `ForeignKey` of the child that points at the parent, at an ancestor of it, or at a proxy of either, with a `ValueError` if there is none or several (`django/forms/models.py:_get_foreign_key`).

```python
# harbour/fleet/forms.py
VoyageFormSet = forms.inlineformset_factory(Ship, Voyage, fields=["sailed"])
```

`BaseInlineFormSet.__init__` takes the parent as `instance=`, or makes a new, empty instance of the model the foreign key points at. Its queryset is the one given, or the child model's default manager, filtered to the parent's children, and empty (`QuerySet.none`) while the parent has no key. It sets `BaseModelFormSet.unique_fields` to the foreign key's name. Where the form's `Meta` lists fields without the foreign key, it adds the key to the list, in the form class's options, with the comment that validation must not be skipped on that field: `_get_validation_exclusions` excludes what the list leaves out (`django/forms/models.py:BaseInlineFormSet.__init__`). The prefix is the name of the parent's accessor for its children (`django/forms/models.py:BaseInlineFormSet.get_default_prefix`):

```python
>>> endeavour = Ship.objects.get(name="Endeavour")
>>> formset = VoyageFormSet(instance=endeavour)
>>> formset.prefix, list(formset[0].fields)
('voyage_set', ['sailed', 'id', 'DELETE', 'ship'])
>>> print(formset[0]["ship"])
<input type="hidden" name="voyage_set-0-ship" value="1" id="id_voyage_set-0-ship">
```

### The parent's key in each form: `InlineForeignKeyField`

A child form offers no choice of parent. `BaseInlineFormSet.add_fields` puts an `InlineForeignKeyField` under the foreign key's name: hidden, not required, and initially the parent's key, or the value of the parent's field the foreign key points at (`django/forms/models.py:BaseInlineFormSet.add_fields`). Its `clean` takes an empty value as the parent (as `None` if the foreign key is the child's primary key), compares any other with that value as strings, refusing a different one ("The inline value did not match the parent instance."), and returns the parent. It never counts as changed, so an extra form holding only that value is still empty (`django/forms/models.py:InlineForeignKeyField`).

`BaseInlineFormSet._construct_form` sets the foreign key on each form's instance, so that, its comment says, the form can do its validation. `BaseModelForm._post_clean` leaves an `InlineForeignKeyField` out of the instance's `full_clean`, since, its comment says, the value may not be supplied and the parent may not yet exist (tickets 12507 and 12749), and keeps it in the unique checks (`django/forms/models.py:BaseModelForm._post_clean`). In the formset's comparison the foreign key is one of `unique_fields`, which `validate_unique` puts into each tuple by name, not value: every form has the same parent. `BaseInlineFormSet.get_unique_error_message` leaves it out of the message.

`BaseInlineFormSet.save_new` sets the parent on each new child again before saving it, since, its comment says, the parent may have been saved after the formset was made (`django/forms/models.py:BaseInlineFormSet.save_new`). So one request can make a parent and its children: the formset is made with the unsaved parent and validated, the parent is saved, then the formset.

With `save_as_new=True`, `_construct_form` blanks each form's key and foreign key in the data, making a `QueryDict` mutable for the moment, and `BaseInlineFormSet.initial_form_count` answers zero, so every form is an extra form and every child saved is a new object of the formset's parent (`django/forms/models.py:BaseInlineFormSet._construct_form`).
