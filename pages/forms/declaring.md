---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`

How a form class collects the fields its class statement declares, and what `BaseForm.__init__` makes of them for each instance: `DeclarativeFieldsMetaclass`, `BaseForm.base_fields`, the copy in `BaseForm.fields`, and the bound fields a form hands out by name.

A form class is ordinarily made once and serves every request; an instance serves one. So the metaclass settles which fields a form class has, and in what order, as the class is made, and `BaseForm.__init__` gives each instance its data, its initial values and fields of its own to change (`django/forms/forms.py:DeclarativeFieldsMetaclass.__new__`).

## `Form` and `BaseForm`

Everything a form does is `BaseForm`'s, but `BaseForm` cannot declare fields: it reads them from the class attribute `BaseForm.base_fields`. `Form` adds only a metaclass; its comment says it is separate to abstract how the fields are specified, the metaclass being purely a convenience for declaring them as attributes (`django/forms/forms.py:Form`). A model form gets its fields from `ModelFormMetaclass`, a subclass of `DeclarativeFieldsMetaclass` ([Model forms: `ModelForm` and `fields_for_model`](model-forms.md)), and a class made with `type` from `BaseForm`, given its `BaseForm.base_fields` directly, needs no metaclass.

## `DeclarativeFieldsMetaclass`: fields out of the class body

`DeclarativeFieldsMetaclass.__new__` is handed the class body's names in a dictionary. It takes out every value that is a form field, an instance of `Field` (`django/forms/fields.py:Field`), and puts them back under one key, `"declared_fields"`, in the order the body assigned them; only then is the class made. So BerthForm has no attribute named ship, and nor has an instance: a field is reached through the instance's `BaseForm.fields`, or by subscription, which gives its bound field (`django/forms/forms.py:DeclarativeFieldsMetaclass.__new__`).

The metaclass then walks the class's method resolution order backwards, from `object` to the class. At each class that has a `BaseForm.declared_fields` it adds the fields found there to a dictionary, and at every class it drops each field whose name the class sets to `None`. So the farthest base's fields come first and the class's own last; a field declared again nearer the class replaces the farther one and keeps its place; and a `None` removes a field only when its class comes before the declaring class in the resolution order:

```python
# harbour/fleet/forms.py
class TugBerthForm(BerthForm):
    tonnage = None
    pilot = forms.CharField()
```

```python
>>> list(TugBerthForm.base_fields)
['ship', 'arrives', 'pilot']
```

> **Trap.** Only a class that has a `BaseForm.declared_fields` contributes fields. A plain mixin's fields stay on it as ordinary attributes, though a `None` on a mixin placed before the form does remove a field.

The dictionary is set on the class as both `BaseForm.base_fields` and `BaseForm.declared_fields`, one object; a model form's metaclass then sets the first again, when its `Meta` names a model, from the model's fields and the declared ones (`django/forms/models.py:ModelFormMetaclass.__new__`). Each class gets a dictionary of its own, but not fields of its own: `TugBerthForm.base_fields["ship"]` is the very field in BerthForm's.

The metaclass is a subclass of `MediaDefiningClass`, which gives each class whose body defines no `media` a property made by `media_property`; on a form, that property gives the widgets' assets, to which an inner `Media` class ordinarily adds its own ([Form assets: `Media`](media.md)) (`django/forms/widgets.py:MediaDefiningClass`).

## `BaseForm.__init__`

`BaseForm.is_bound` is true when data or files are given, even empty. The data, the files and the initial values are kept as given, not copied, or are made empty: a `MultiValueDict` for the first two, a dictionary for the third (`django/forms/forms.py:BaseForm.__init__`).

A prefix passed in replaces the class attribute `BaseForm.prefix`, `None`. `BaseForm.add_prefix` joins it to a field's name with a hyphen, `"berth-ship"` for `prefix="berth"`, and every input's name is made by it; `BaseForm.add_initial_prefix` puts `"initial-"` in front, for the hidden input of a field with `Field.show_hidden_initial` (`django/forms/forms.py:BaseForm.add_prefix`). `BaseForm.auto_id`, unless given, is `"id_%s"`, a pattern the bound field fills with that name to make the input's `"id"` ([`BoundField`: a field in a form](bound-fields.md)) (`django/forms/boundfield.py:BoundField.auto_id`).

`BaseForm.error_class`, `ErrorList` unless given, is the class each list of errors is made of ([Validation: `full_clean`, `cleaned_data` and the errors](validation.md)). `BaseForm.label_suffix`, unless given, is `":"` translated as the form is made, in the language active then.

`empty_permitted=True` lets a form whose data is unchanged from its initial values be valid without being cleaned. `BaseForm.use_required_attribute`, true on the class, lets a bound field put `"required"` on the input of a required field (`django/forms/boundfield.py:BoundField.build_widget_attrs`). `BaseForm.__init__` refuses the two together with a `ValueError`; a formset's forms get `use_required_attribute=False` unless its form arguments say otherwise (`django/forms/formsets.py:BaseFormSet._construct_form`).

The renderer is the one passed in, else the class's `BaseForm.default_renderer` (a class there is instantiated for each form), else the one made once in a process from `FORM_RENDERER` ([Rendering a form: renderers and templates](rendering.md)). `BaseForm.bound_field_class` is the one passed in, else the class's, else the renderer's; a field's own comes before all three (`django/forms/fields.py:Field.get_bound_field`).

## The copy of the fields

An instance's `BaseForm.fields` is a `copy.deepcopy` of its class's `BaseForm.base_fields`, and the comment at the copy says why: those are the definition for the whole class, an instance may want to change its fields, and so it is given its own (`django/forms/forms.py:BaseForm.__init__`). Each field is copied by `Field.__deepcopy__`, which copies less than its name says: the copy is shallow but for its widget, its dictionary of messages and its list of validators (`django/forms/fields.py:Field.__deepcopy__`). `Widget.__deepcopy__` is shallow too, but for a copy of `Widget.attrs` (`django/forms/widgets.py:Widget.__deepcopy__`). Some subclasses copy more: the choice fields and widgets their choices, `ModelChoiceField` a new queryset ([Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](choices.md)), and `MultiValueField` and `MultiWidget` their parts. The rest is shared with the class: the label, the initial value, each validator in the list.

`BaseForm.order_fields` then orders the copies by the order passed in, or else the class's `BaseForm.field_order`. The names listed come first, in that order; a name the form lacks is skipped, which the docstring says lets a subclass remove a field without restating the order; the rest follow in the order they had (`django/forms/forms.py:BaseForm.order_fields`).

## Changing a form's fields in `__init__`

Because the copies are the instance's, a form may change its fields for one use in its own `__init__`, after the base's has run. A berth for ships up to some tonnage:

```python
# harbour/fleet/forms.py
from django.core.validators import MaxValueValidator


class LimitedBerthForm(BerthForm):
    def __init__(self, *args, largest=None, **kwargs):
        super().__init__(*args, **kwargs)
        if largest is not None:
            tonnage = self.fields["tonnage"]
            tonnage.validators.append(MaxValueValidator(largest))
            tonnage.widget.attrs["max"] = largest
```

```python
>>> data = {"ship": "Endeavour", "tonnage": "366", "arrives": "2026-10-20"}
>>> LimitedBerthForm(data, largest=300).errors.as_data()
{'tonnage': [ValidationError(['Ensure this value is less than or equal to 300.'])]}
>>> LimitedBerthForm(data).is_valid()
True
>>> print(LimitedBerthForm(largest=300)["tonnage"])
<input type="number" name="tonnage" min="1" max="300" required id="id_tonnage">
```

The validators' list and the widget's attributes were copied, so other forms are untouched. What was not copied is shared: setting `BaseValidator.limit_value` on the `MinValueValidator` in one form's list changes the least tonnage for every form of the class.

> **Trap.** A bound field keeps the field it was made with. A field replaced in `BaseForm.fields` after the form has handed out its bound field is not seen by that bound field, so changes belong in `__init__`, before anything asks for one.

## Fields by name

`BaseForm.__getitem__` looks a name up in the instance's fields, raising a `KeyError` that lists the names there are, and answers with the field's bound field, made by `Field.get_bound_field` the first time and then kept (`django/forms/forms.py:BaseForm.__getitem__`, `django/forms/fields.py:Field.get_bound_field`). The bound field keeps its initial value in turn, so a callable initial value is called once for each form, however often the form is drawn.

`BaseForm.__iter__` gives the bound fields in the order of `BaseForm.fields`, and `BaseForm._bound_items` the names with them, which `BaseForm._clean_fields`, `BaseForm.changed_data` and `BaseForm.get_context` walk. `BaseForm.hidden_fields` and `BaseForm.visible_fields` split the bound fields by whether the widget is hidden; `BaseForm.is_multipart` is true when a widget has `Widget.needs_multipart_form`, as a file input does. `BaseForm.__repr__` does not run validation, and gives the form's validity as Unknown until something has.

## Initial values: `get_initial_for_field`

`BaseForm.get_initial_for_field` is what a bound field asks for its initial value (`django/forms/forms.py:BaseForm.get_initial_for_field`). The form's `BaseForm.initial` comes first, by the field's name, even where its value is `None`, and the field's own `Field.initial` only where the form's has no such key. A callable is called. A `datetime.datetime` or a `datetime.time` then loses its microseconds when the widget has `Widget.supports_microseconds` false, as the date and time inputs and `SplitDateTimeWidget` do. The comment cites ticket 22502 for a default made at the moment; a fixed value is treated alike.
