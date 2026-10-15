---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `BoundField`: a field in a form

A `BoundField` is one field of a form joined to one form instance: it knows the field's name in the submitted data, its id and label, the value to show and the errors, and it draws the field's widget and label. `form["tonnage"]`, a loop over a form and the form's templates all deal in bound fields.

A field knows nothing of the form that holds it: not its prefix, data, initial values, errors or renderer. The bound field keeps the form, the field and its name, settles its names and label when it is made, keeps the initial value and the widget's parts once worked out, and works out the data, the value and the errors each time it is asked (`django/forms/boundfield.py:BoundField`).

## Who makes a bound field

`BaseForm.__getitem__` makes a name's bound field the first time it is asked for, by `Field.get_bound_field`, and keeps it: a form has one for each name (`django/forms/forms.py:BaseForm.__getitem__`). The class is the field's `bound_field_class`, else the form's, else `BoundField` (`django/forms/fields.py:Field.get_bound_field`). The form's was settled in `BaseForm.__init__`: its argument, else its class's, else the renderer's `BaseRenderer.bound_field_class` (`django/forms/forms.py:BaseForm.__init__`).

## Names, ids and the label

`BoundField.__init__` settles the field's names in the HTML (`django/forms/boundfield.py:BoundField.__init__`). `html_name` is the field's name with the form's prefix, by `BaseForm.add_prefix`. `html_initial_name` and `html_initial_id` are the name and the id passed through `BaseForm.add_initial_prefix`, which adds the prefix and then `"initial-"`, for a hidden input that carries an initial value. The label is the field's, or else the name made readable by `pretty_name`: underscores become spaces, the first letter a capital and the rest lower case (`django/forms/utils.py:pretty_name`).

`BoundField.auto_id` comes from the form's `auto_id`: a string with `%s` in it is filled with the html name, another true value is the html name itself, and a false one gives `""`, and so no `"aria-describedby"` and, unless the widget has an id of its own, no `"id"` and no label element (`django/forms/boundfield.py:BoundField.auto_id`).

```python
# BerthForm of harbour/fleet/forms.py, in a shell
>>> field = BerthForm(prefix="berth")["tonnage"]
>>> field.html_name, field.auto_id, field.label
('berth-tonnage', 'id_berth-tonnage', 'Tonnage')
```

`BoundField.id_for_label`, the id a label points at, is the widget's own `"id"` or else `auto_id`, as `Widget.id_for_label` gives it back (`django/forms/boundfield.py:BoundField.id_for_label`). A `MultiWidget` and a `RadioSelect` give back `""`, so their label points at no input (`django/forms/widgets.py:MultiWidget.id_for_label`). For radio buttons the docstring says this improves accessibility when using a screen reader, and that clicking such a label would toggle the first input (`django/forms/widgets.py:RadioSelect.id_for_label`).

## The value to show: `data`, `initial` and `value`

`BoundField.data` is what was submitted: the field's widget reads it out of the form's data and files under the html name at each use; the base widget gives `None` when nothing is there (`django/forms/forms.py:BaseForm._widget_data_value`). `BoundField.initial` is the form's initial value for the name over the field's own, a callable called, from `BaseForm.get_initial_for_field`. It is a cached property, so a callable initial is called once in a form's life (`django/forms/boundfield.py:BoundField.initial`).

`BoundField.value` is what the input shows (`django/forms/boundfield.py:BoundField.value`). An unbound form shows the initial value. A bound one shows what `Field.bound_data` makes of the data and the initial: in the base class the data, but the initial for a disabled field (`django/forms/fields.py:Field.bound_data`). A file field always gives the initial ([The built-in form fields](field-types.md)). The result then passes through `Field.prepare_value`. So a bound form shows what was typed (a JSON field's parsed and dumped again), not what it was cleaned to, and any other field missing from the data shows no value, not its initial one, as a comment in `Field.__init__` warns:

```python
# BerthForm of harbour/fleet/forms.py, in a shell
>>> form = BerthForm({"ship": "Heron"}, initial={"tonnage": 120})
>>> form["tonnage"].initial, form["tonnage"].value()
(120, None)
```

## Changed or not: `_has_changed`

`BaseForm.changed_data` asks each bound field `BoundField._has_changed`, which hands `Field.has_changed` an initial value and `data` (`django/forms/boundfield.py:BoundField._has_changed`, `django/forms/fields.py:Field.has_changed`). The initial value is `initial`, unless the field was made with `show_hidden_initial=True`. Such a field is drawn with a hidden input after its widget, by `as_hidden(only_initial=True)`, named `html_initial_name`, with the id `html_initial_id`, and holding `value`, or on a redraw what was submitted under that name (`django/forms/utils.py:RenderableFieldMixin.__str__`, `django/forms/boundfield.py:BoundField.as_widget`). `_has_changed` compares with what comes back in it, through `Field.to_python`; a value that will not convert counts as a change. So the data is compared with what the person was shown, not with an initial a callable has worked out anew; a model field with a callable default asks for this ([Model forms: `ModelForm` and `fields_for_model`](model-forms.md)).

## Drawing the widget: `as_widget`

`str(form["tonnage"])`, what `{{ form.tonnage }}` prints, is the widget alone: `RenderableFieldMixin` replaces the `__str__` and `__html__` of `RenderableMixin` with `as_widget`, and the hidden initial input when the field asks for one (`django/forms/utils.py:RenderableFieldMixin`). The whole group, label, help text, errors and widget, is `RenderableFieldMixin.as_field_group`, rendering `BoundField.template_name`: the field's template, or the renderer's, `"django/forms/field.html"` by default ([Rendering a form: renderers and templates](rendering.md)).

`BoundField.as_widget` draws the field's widget, or one it is handed. It marks the widget localized if the field is, adds attributes by `build_widget_attrs`, gives `auto_id` as the `"id"` unless the widget or the attributes passed have one, and has it render the html name and `value` with the form's renderer (`django/forms/boundfield.py:BoundField.as_widget`). `BoundField.as_text`, `BoundField.as_textarea` and `BoundField.as_hidden` hand it a new `TextInput`, `Textarea` or hidden widget, which has none of the attributes of the field's own: the tonnage drawn by `as_text` has no `"min"`.

## The attributes a bound field adds

`BoundField.build_widget_attrs` copies the attributes it is given and adds these (`django/forms/boundfield.py:BoundField.build_widget_attrs`):

| attribute | added when |
|---|---|
| `"required"` | the field is required, the form's `use_required_attribute` is true, and the widget's `Widget.use_required_attribute` agrees, given the initial value |
| `"disabled"` | the field is disabled |
| `"aria-invalid"` | the widget drawn is not hidden and the field has errors |
| `"aria-describedby"` | none was given, the widget is not in a fieldset, and `aria_describedby` is not empty |

The widget has a say in `"required"` (`django/forms/widgets.py:Widget.use_required_attribute`). A hidden input never takes it, nor a `CheckboxSelectMultiple`, where the browser would demand every box, nor a file input that already has a file; a single `Select` takes it only when its first option is empty. A `MultiValueField` whose `require_all_fields` is false marks each part of its widget by that part's own field instead.

Reading the errors reads `BaseForm.errors`, so drawing a visible field's widget validates a bound form if nothing has yet. `BoundField.errors` is the form's list for the name, or an empty one of the form's `error_class` (`django/forms/boundfield.py:BoundField.errors`).

`BoundField.aria_describedby` joins `auto_id` with `"_helptext"` if there is help text and with `"_error"` if there are errors: the ids that `"django/forms/field.html"` gives the help text and the error list's template makes from `ErrorList.field_id` ([Validation: `full_clean`, `cleaned_data` and the errors](validation.md)). It is empty for a hidden field or one with no id, and `None` when the widget has an `"aria-describedby"` of its own (`django/forms/boundfield.py:BoundField.aria_describedby`). A widget whose `Widget.use_fieldset` is true is drawn by that template in a `<fieldset>`, which takes the attribute instead; `BoundField.use_fieldset` reads the flag.

## Labels and classes

`BoundField.label_tag` draws the label (`django/forms/boundfield.py:BoundField.label_tag`). Its text is the contents passed, else the label, then a suffix: the one passed, else the field's `label_suffix`, else the form's, by default a translated `":"`. The suffix is left off when the text ends in one of `":?.!"`, a string translators may change. The element gets a `"for"` from `id_for_label` when that is not empty, and the form's `"required_css_class"` for a required field; with no id at all there is no element, only the text. `BoundField.legend_tag` does the same with a `<legend>` and no `"for"`, for a field drawn in a fieldset.

`BoundField.css_classes` gives the classes for the element around a field: those passed, with the form's `"error_css_class"` if the field has errors and its `"required_css_class"` if it is required (`django/forms/boundfield.py:BoundField.css_classes`). `BaseForm` declares neither; a form opts in by declaring them. They are gathered in a set, so their order is not fixed.

## A widget's parts: `subwidgets` and `BoundWidget`

`BoundField.subwidgets` asks the field's widget for its parts, with the html name, `value` and the attributes `build_widget_attrs` makes, and wraps each in a `BoundWidget` (`django/forms/boundfield.py:BoundField.subwidgets`). The base widget has one part; a choice widget has one for each option (`django/forms/widgets.py:ChoiceWidget.subwidgets`). Iteration, length and indexing use this list, so a template can lay out a radio group's buttons one by one. It is cached, its docstring says, so that a `ModelChoiceField`'s options cost one query. A `BoundWidget` renders its part with `BoundWidget.tag`, and as a string with `"wrap_label"` set, which puts a radio button inside its label; `BoundWidget.choice_label` and `BoundWidget.id_for_label` read the option's label and id (`django/forms/boundfield.py:BoundWidget`).

`BoundField.__getitem__` takes only an integer or a slice, and raises `TypeError` for anything else before it touches the list, to prevent, its comment says, needless re-evaluation when a template reads its attributes (`django/forms/boundfield.py:BoundField.__getitem__`). The template language tries a key before an attribute, so `{{ field.label }}` calls it with `"label"` first ([Variables and filters: `FilterExpression` and `Variable`](../templates/variables.md)). `BoundField.__bool__` is always true, where `__len__` alone would make a field with no options false.

`BoundField.widget_type` is the widget's class name in lower case, less a final `"widget"` or `"input"`: `"number"` for a `NumberInput` (`django/forms/boundfield.py:BoundField.widget_type`). `BoundField.is_hidden` is the widget's `Widget.is_hidden`.
