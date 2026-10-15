---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets

A choice field accepts only a value it offers. `ChoiceField`, `TypedChoiceField` and their multiple variants keep a list of values and labels; `ModelChoiceField` and `ModelMultipleChoiceField` read theirs from a queryset and clean submitted keys into objects; the choice widgets, `Select`, `RadioSelect`, `CheckboxSelectMultiple` and their kin, draw the list and read back what was chosen.

A browser sends back only the chosen option's value, as a string, and a client can send any string, so a choice field checks it against what it offered before converting it. The field reads the list to check a value, the widget to draw the options, and the field hands its widget the list when its own is set. A model choice field keeps a queryset instead, and each reading of its choices goes back to the database.

## The choices on a field and on its widget

`ChoiceField.choices` is a property whose setter passes the value through `normalize_choices`, which makes a mapping, an enumeration or nested groups into lists of pairs and wraps a callable to be called at each reading ([Choices: `normalize_choices` and the choice iterators](../utils/choices.md)), and hands the result to the widget's `ChoiceWidget.choices`, which normalizes it again (`django/forms/fields.py:ChoiceField.choices`). A list so becomes two equal lists.

Each form instance deep-copies its fields ([Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`](declaring.md)). `ChoiceField.__deepcopy__` adds a deep copy of the choices, and the widget copies its own shallowly (`django/forms/widgets.py:ChoiceWidget.__deepcopy__`). A form's `__init__` can so give one field new choices without touching the class's, provided it assigns them: a list changed in place changes what the field accepts and not what its widget draws.

`FilePathField` makes its own choices: the files or directories under its directory that match its pattern, the blank choice first when the field is not required (`django/forms/fields.py:FilePathField.set_choices`). It reads the directory when the field is made and again at each call of `set_choices`, as from a form's `__init__`, and hands the widget the new list.

> **Changed in 6.1.** `FilePathField.set_choices` was added.

## Checking a choice: `ChoiceField` and `TypedChoiceField`

`ChoiceField.to_python` makes a value a string, an empty one `""`. `ChoiceField.validate` makes the required check of `django/forms/fields.py:Field`, then asks `ChoiceField.valid_value`, which looks through the choices, and inside each group (a pair whose second element is a list or a tuple), for a value equal to the one given or with the same string, which lets a browser's string match a number among the choices. Anything else is an `"invalid_choice"` error naming the value (`django/forms/fields.py:ChoiceField.validate`, `django/forms/fields.py:ChoiceField.valid_value`).

`TypedChoiceField` then converts. After the whole of `Field.clean`, `TypedChoiceField._coerce` passes the checked string to the field's `coerce`, and gives `empty_value`, `""` unless another is given, for an empty one; a failed conversion is an `"invalid_choice"` error too (`django/forms/fields.py:TypedChoiceField._coerce`). A berth chosen by quay:

```python
# harbour/fleet/forms.py
QUAYS = {
    "North quay": {1: "Berth 1", 2: "Berth 2"},
    "South quay": {3: "Berth 3"},
}


class BerthingForm(forms.Form):
    berth = forms.TypedChoiceField(choices=QUAYS, coerce=int)
```

```python
>>> form = BerthingForm({"berth": "2"})
>>> form.is_valid(), form.cleaned_data
(True, {'berth': 2})
```

A model field with choices makes a `TypedChoiceField` with its own `to_python` as `coerce` ([Model forms: `ModelForm` and `fields_for_model`](model-forms.md)).

`MultipleChoiceField` takes a list: `MultipleChoiceField.to_python` makes an empty value `[]` and each item of a list or a tuple a string, and refuses anything else as `"invalid_list"`; its `validate` checks each distinct item with `valid_value`, and `MultipleChoiceField.has_changed` compares lengths, then sets of strings (`django/forms/fields.py:MultipleChoiceField`). `TypedMultipleChoiceField` coerces each item, and its empty value is `[]` unless another is given.

## The choice widgets

A choice widget draws one template for the whole and one for each option. `ChoiceWidget.get_context` adds the list `ChoiceWidget.optgroups` makes, a triple for each top-level choice: its group's name (`None` outside a group), its options, and its index (`django/forms/widgets.py:ChoiceWidget.optgroups`). Each option is a dictionary from `ChoiceWidget.create_option`, with the keys `"name"`, `"value"`, `"label"`, `"selected"`, `"index"`, `"attrs"`, `"type"`, `"template_name"` and `"wrap_label"`. Its index is its place, or its group's and its own joined, `"0_1"` for Berth 2, and `ChoiceWidget.id_for_label` numbers an `"id"` among its attributes with that index (`django/forms/widgets.py:ChoiceWidget.create_option`).

Selection is by string: `ChoiceWidget.format_value` makes the value a list of strings, and an option is selected when its value's string is in it. A widget of one value marks only the first match; one whose `ChoiceWidget.allow_multiple_selected` is true marks every match, and reads the data with `MultiValueDict.getlist` where it can, so that a `QueryDict` gives every value submitted under the name (`django/forms/widgets.py:ChoiceWidget.value_from_datadict`). `ChoiceWidget.subwidgets` yields the options singly through `ChoiceWidget.options`, for a bound field to loop over ([`BoundField`: a field in a form](bound-fields.md)).

`Select` draws a `<select>`, a group as an `<optgroup>`, and `SelectMultiple` marks it `"multiple"`; `NullBooleanSelect` offers Unknown, Yes and No, read as `None`, `True` and `False`; `RadioSelect` and `CheckboxSelectMultiple` draw radio inputs and checkboxes in a `<div>`; `RadioSelect.use_fieldset` has a field's template add a `<fieldset>`. On a required field, `Select.use_required_attribute` withholds `"required"` from a select of one value whose first choice has a value, which its docstring calls invalid HTML (`django/forms/widgets.py:Select.use_required_attribute`). A `ChoiceField` adds no blank choice, so BerthingForm's select has no `"required"`. A `RadioSelect` puts it on each input, and gives its field's label no `"for"`, for screen readers, its docstring says, and because clicking such a label would toggle the first input (`django/forms/widgets.py:RadioSelect.id_for_label`). `CheckboxSelectMultiple` omits it: with it, a comment says, a browser would require every box ticked. It and `SelectMultiple` report their value never omitted from the data, since nothing is submitted when nothing is chosen ([Widgets: `Widget` and its subclasses](widgets.md)).

## `ModelChoiceField`: choices from a queryset

`ModelChoiceField` keeps a queryset in place of a list (`django/forms/models.py:ModelChoiceField`). Assigning `ModelChoiceField.queryset` stores the queryset's `QuerySet.all`, a copy with nothing cached, and hands the widget the field's choices (`django/forms/models.py:ModelChoiceField._set_queryset`). Reading `ModelChoiceField.choices`, unless choices were assigned by hand, makes a new `ModelChoiceIterator`, so that, a comment says, it has not been consumed (`django/forms/models.py:ModelChoiceField._get_choices`). The widget keeps the iterator it was handed and goes through it at each drawing.

`ModelChoiceIterator` yields the blank choice, `""` with `ModelChoiceField.empty_label`, unless that is `None`; then, for each object, a pair: a `ModelChoiceIteratorValue`, which holds the object's key and the object and is equal to the key, and the label `ModelChoiceField.label_from_instance` gives, the object's `str` by default (`django/forms/models.py:ModelChoiceIterator`). It reads through `QuerySet.iterator`, keeping no rows, unless the queryset uses `QuerySet.prefetch_related`, which a comment says rules that out. Its length costs a `QuerySet.count`, and its truth, with no blank choice, a `QuerySet.exists` ([Evaluation and the result cache](../querysets/evaluation.md)).

ShipForm's home port:

```python
>>> form = ShipForm()
>>> print(form["home"])
<select name="home" required id="id_home">
  <option value="" selected>- Select an option -</option>

  <option value="2">Piraeus</option>

  <option value="1">Valletta</option>

</select>
```

Drawing it sent one query for the ports, ordered by name; each drawing sends another. A select of one value with no blank choice sends two, the first from `Select.use_required_attribute` reading the first choice (`django/forms/widgets.py:Select.use_required_attribute`).

`ModelChoiceField.empty_label` is `None`, with no blank choice, when the field is required and has an initial value of its own (not the form's: ShipForm made with a ship still offers one), or when its widget is a `RadioSelect` and it was not made with `blank=True`, which a foreign key passes from its own `blank`. Otherwise it is the label given, `None` again meaning none, and the default, `""`, is replaced by what `get_blank_choice_label` gives (`django/forms/models.py:ModelChoiceField.__init__`).

`ModelChoiceField.__deepcopy__` skips `ChoiceField`'s copy of the choices and assigns the copy its queryset anew, which hands the copy's widget an iterator over the copy; its comment cites ticket 11183. Without it, each form's widget would read the class's field (`django/forms/models.py:ModelChoiceField.__deepcopy__`).

## Cleaning a key into an object

`ModelChoiceField.to_python` makes an empty value `None`, refuses a null character, and otherwise fetches the object with `QuerySet.get` on the field's queryset, one query, by `ModelChoiceField.to_field_name` or the primary key; an object of the model is taken by its key (`django/forms/models.py:ModelChoiceField.to_python`). A key of the wrong type and one not in the queryset are both `"invalid_choice"`, whose message names no value. The query is the check against the choices, and `ModelChoiceField.validate` skips `ChoiceField.validate`, keeping only the required check (`django/forms/models.py:ModelChoiceField.validate`). A foreign key's form field gets the field it points to as `to_field_name`, `"id"` for the home port.

`ModelMultipleChoiceField` has no blank choice and draws a `SelectMultiple`. `ModelMultipleChoiceField.clean` returns `QuerySet.none` for an empty value when not required, and `ModelMultipleChoiceField._check_values` drops repeated keys, builds an unrun filter for each, so that a key of the wrong type is `"invalid_pk_value"`, fetches them all in one query with `"__in"`, and refuses a key it did not find as `"invalid_choice"` (`django/forms/models.py:ModelMultipleChoiceField._check_values`). The field cleans to that queryset, already evaluated.

## `limit_choices_to`

A `ModelChoiceField` keeps the `limit_choices_to` it is given, a foreign key passing its own, and does not apply it; `ModelChoiceField.get_limit_choices_to` calls it if it is callable. `apply_limit_choices_to_to_formfield` makes a dictionary a `Q`, adds the condition that the key equal the outer row's, and filters the field's queryset on `Exists` over the model's base manager, which a comment says avoids duplicates (`django/forms/models.py:apply_limit_choices_to_to_formfield`). `ModelFormMetaclass` has `fields_for_model` skip this, and `BaseModelForm.__init__` does it for every field of each instance, so a callable is called for each form (`django/forms/models.py:BaseModelForm.__init__`).

> **Trap.** A plain `Form` never applies it: a `ModelChoiceField` there offers and accepts every object of its queryset.

## The blank choice's label

`get_blank_choice_label` gives a blank choice's label: `BLANK_CHOICE_LABEL`, a translated `"- Select an option -"`, or, while `USE_BLANK_CHOICE_DASH` is true, the dashes of `BLANK_CHOICE_DASH` (`django/db/models/utils.py:get_blank_choice_label`). It reads the constant at each call, so an application's `AppConfig.ready` can replace it, as a comment beside it invites. Its callers include `ModelChoiceField.__init__` and a model field's `get_choices` (`django/db/models/fields/__init__.py:Field.get_choices`).

> **Changed in 6.1.** The label was the dashes, which `USE_BLANK_CHOICE_DASH` brings back; the setting and `BLANK_CHOICE_DASH` are deprecated, and setting it warns with `RemovedInDjango2028Warning`.
