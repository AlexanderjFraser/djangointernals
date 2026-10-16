---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in forms and validators

The changes from Django 5.0 to this commit in `django.forms` and `django/core/validators.py`: the div layout as the default, `RenderableFieldMixin.as_field_group`, `bound_field_class`, the ARIA attributes, the URL field's `"https"`, the blank choice's label, and `EmailValidator`'s new methods.

Most of the change is in the HTML a form draws; the fields and validators changed a default or a hook at a time.

## The layout: divisions, and a template for each field

Since 5.0 a form draws itself as divisions: `BaseRenderer.form_template_name` is `"django/forms/div.html"` and `BaseRenderer.formset_template_name` `"django/forms/formsets/div.html"`, and `str(form)` renders the renderer's (`django/forms/renderers.py:BaseRenderer`, `django/forms/forms.py:BaseForm.template_name`). The default had been the table layout, through the templates django/forms/default.html and django/forms/formsets/default.html, which 5.0 removed. The transitional renderers DjangoDivFormRenderer and Jinja2DivFormRenderer, which drew divisions early, were deprecated in 5.0 and removed in 6.0. The other layouts remain, as the `as_table`, `as_p` and `as_ul` of `RenderableFormMixin`; the method _html_output of `BaseForm`, which drew them in Python before 4.0, went in 5.0 ([Rendering a form: renderers and templates](../forms/rendering.md)).

The division template hands each field to a template of its own (5.0). It prints `{{ field.as_field_group }}`, and `RenderableFieldMixin.as_field_group` renders the bound field's template, which draws label, help text, errors and widget (`django/forms/utils.py:RenderableFieldMixin.as_field_group`). That template is one given to the form field as `template_name=`, or else the renderer's `BaseRenderer.field_template_name`, `"django/forms/field.html"` (`django/forms/boundfield.py:BoundField.template_name`). The paragraph, table and list templates still draw each field's parts themselves.

Rendering an error list or dictionary to a plain string, not a safe one, was deprecated in 4.0 and stopped working in 5.0. `BaseForm.get_context` hands the template each field's `ErrorList` as it is, and the template escapes a plain string (`django/forms/forms.py:BaseForm.get_context`): in a run, an error class whose `__str__` returned `"<b>…</b>"` unmarked drew `&lt;b&gt;`. Django's own error lists are marked safe by `RenderableMixin.render` (`django/forms/utils.py:RenderableMixin.render`).

## `bound_field_class`

Before 5.2 a field had bound fields of another class only by an override of `Field.get_bound_field` (`django/forms/fields.py:Field.get_bound_field`). Since 5.2 that method takes the class from the field's `Field.bound_field_class`, else from the form's, else `BoundField`. The form's is settled by `BaseForm.__init__`: its argument, else its class's `BaseForm.bound_field_class`, else the renderer's `BaseRenderer.bound_field_class`, `None` on Django's renderers (`django/forms/forms.py:BaseForm.__init__`). So the project's renderer can give every form one class of bound field ([`BoundField`: a field in a form](../forms/bound-fields.md)).

## The attributes for screen readers

From 5.0 to 5.2 a field was tied to its help text and errors, for screen readers. 5.0 gave the input `"aria-describedby"`, naming the help text, and `"aria-invalid"` set to `"true"` when the field has errors; 5.1 put `"aria-describedby"` on the `<fieldset>` the field's template draws for a widget whose `Widget.use_fieldset` is true, such as a `RadioSelect`; 5.2 added the errors to it. At this commit `BoundField.aria_describedby` (5.2) joins `BoundField.auto_id` with `"_helptext"` and `"_error"`, as the field has help text and errors (`django/forms/boundfield.py:BoundField.aria_describedby`). `BoundField.build_widget_attrs` puts it on the widget unless the widget has its own or asks for a fieldset; then `"django/forms/field.html"` puts it on the fieldset (`django/forms/boundfield.py:BoundField.build_widget_attrs`). The errors' id is written by `"django/forms/errors/list/ul.html"` from `ErrorList.field_id` (5.2), which `BaseForm.add_error` sets to the field's `auto_id` (`django/forms/forms.py:BaseForm.add_error`).

```python
# BerthForm of harbour/fleet/forms.py, tonnage with help_text="Gross tons.", in a shell
>>> form = BerthForm({"ship": "Heron", "tonnage": "0", "arrives": "2026-10-20"})
>>> print(form["tonnage"].as_field_group())
<label for="id_tonnage">Tonnage:</label>

<div class="helptext" id="id_tonnage_helptext">Gross tons.</div>
<ul class="errorlist" id="id_tonnage_error"><li>Ensure this value is greater than or equal to 1.</li></ul>
<input type="number" name="tonnage" value="0" min="1" required aria-invalid="true" aria-describedby="id_tonnage_helptext id_tonnage_error" id="id_tonnage">
```

> **Trap.** The paragraph, table and list templates draw no fieldset, yet a widget that asks for one still gets no `"aria-describedby"`. In a run, `as_p()` gave a `RadioSelect` field's help text and errors their ids, and nothing named them.

## The URL field's scheme

In 5.0 the scheme `URLField.to_python` puts in front of a value that has none became `URLField.assume_scheme`, an argument whose default, `"http"`, was deprecated at once; in 6.0 the default became `"https"`, and FORMS_URLFIELD_ASSUME_HTTPS, the transitional setting that took it early, was removed (`django/forms/fields.py:URLField.__init__`). Nothing in Django passes the argument, so the form field a model's URL field makes assumes `"https"` too ([The built-in form fields](../forms/field-types.md#urls-and-the-assumed-scheme)).

## The blank choice's label

A blank choice, the empty option that a model field's choices and a `ModelChoiceField`'s begin with, was labelled with dashes. Since 6.1 its label comes from `get_blank_choice_label`: `BLANK_CHOICE_LABEL`, a translated `"- Select an option -"`, or the dashes of `BLANK_CHOICE_DASH` while `USE_BLANK_CHOICE_DASH` is true (`django/db/models/utils.py:get_blank_choice_label`). It reads the constant at each call, so an application may replace it; the model side is in [What changed in models and fields](models.md). The setting and the constant are deprecated, to go in Django 2028 ([What still warns: the deprecations and the releases that end them](deprecations.md)). Defining the setting warns with `RemovedInDjango2028Warning` (`django/conf/__init__.py:Settings.__init__`); in a run, reading the constant did not ([Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](../forms/choices.md#the-blank-choices-label)).

## `EmailValidator`

Before 6.2 a subclass could replace the domain's check in `EmailValidator.__call__` through `EmailValidator.validate_domain_part`, which answers true or false. Now the call is `EmailValidator.parse_address`, then `EmailValidator.validate`, which hands the user part to `EmailValidator.validate_username` and the domain to `EmailValidator.validate_domain`; each raises `ValidationError` itself, with the part as the parameter `"username"` or `"domain"` beside `"value"` (`django/core/validators.py:EmailValidator.validate`). The old method is deprecated, to go in Django 2029: a subclass that defines it warns with `RemovedInDjango2029Warning` as the class is made, and `validate` then calls it in place of `validate_domain` (`django/core/validators.py:EmailValidator.__init_subclass__`; [Validators: `django/core/validators.py`](../forms/validators.md#domain-names-urls-and-email-addresses)).

## The smaller changes

| name | what changed | release | where now |
|---|---|---|---|
| `ColorInput`, `SearchInput`, `TelInput` | new inputs of the types `"color"`, `"search"` and `"tel"`; no Django field uses them | 5.2 | `django/forms/widgets.py:ColorInput` |
| `Script` | a script of a `Media` declaration, with HTML attributes | 5.2 | `django/forms/widgets.py:Script` |
| `Stylesheet` | the same for a stylesheet; at this commit a path given as a string becomes one, or a `Script` | 6.1 | `django/forms/widgets.py:Media._normalize_css`, `django/forms/widgets.py:Media._normalize_js`, [Form assets: `Media`](../forms/media.md) |
| `FilePathField.set_choices` | reads the directory again; the field calls it when made, and a form's `__init__` may call it | 6.1 | `django/forms/fields.py:FilePathField.set_choices` |
| `BaseModelFormSet.save_existing` | its second argument, once named instance, is named obj; Django passes it by position | 5.0 | `django/forms/models.py:BaseModelFormSet.save_existing_objects` |
| `StepValueValidator` | takes an offset to count the steps from; at this commit the form `IntegerField` and its subclasses give `min_value=` as the offset | 5.0 | `django/core/validators.py:StepValueValidator.__call__`, `django/forms/fields.py:IntegerField.__init__` |
| `DomainNameValidator` | new; at this commit `URLValidator` and `EmailValidator` take its host-name patterns; a newline refused since a security fix ([Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md)) | 5.1 | `django/core/validators.py:DomainNameValidator` |
