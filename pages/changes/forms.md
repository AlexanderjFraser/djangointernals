---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in forms and validators

The changes from Django 5.0 to this commit in `django.forms` and `django/core/validators.py`: the division layout and `RenderableFieldMixin.as_field_group`, the attributes for screen readers, `bound_field_class`, the URL field's `"https"`, the blank choice's label, and `EmailValidator`'s new methods.

In 6.0 two deprecations ended: the transitional renderers went, and the URL field's assumed scheme became `"https"`. 6.1 replaced the blank choice's dashes with a label "more accessible and translatable" (`docs/releases/6.1.txt`). 6.2 split `EmailValidator` into methods a subclass can replace. From 5.0 to 5.2 the templates that draw a form were reshaped for screen readers. 5.0 made the division layout the default, which the 4.1 notes had recommended as "easier for screen reader users to navigate" (`docs/releases/4.1.txt`). It also gave each field a template of its own, and began tying an input to its help text, which 5.1 carried to the fieldset and 5.2 to the errors.

## How a form is drawn: divisions, and a template for each field

Since 5.0 a form rendered as a string uses `BaseRenderer.form_template_name`, `"django/forms/div.html"` (`django/forms/forms.py:BaseForm.template_name`). 5.0 removed the former default, the table layout's django/forms/default.html and its formset twin, and BaseForm's _html_output, which drew the layouts in Python before 4.0 (`docs/releases/4.0.txt`, `docs/releases/5.0.txt`). The division template prints each field's `RenderableFieldMixin.as_field_group` (5.0), which renders the bound field's template (the form field's own, if it was given one, or the renderer's, `"django/forms/field.html"`) to draw label, help text, errors and widget (`django/forms/boundfield.py:BoundField.template_name`; [Rendering a form: renderers and templates](../forms/rendering.md#the-built-in-templates)).

From 4.1 a transitional renderer named in `FORM_RENDERER` gave the division layout early. 5.0 deprecated DjangoDivFormRenderer and Jinja2DivFormRenderer, and 6.0 removed them. A form given no renderer, whose class names none, reads the setting (`django/forms/renderers.py:get_default_renderer`). Here the setting names DjangoDivFormRenderer:

```text recording=changes
FORM_RENDERER = "django.forms.renderers.DjangoDivFormRenderer": the class of a form's renderer
    5.2.17       DjangoDivFormRenderer, warns RemovedInDjango60Warning
    6.0.8        ImportError: Module "django.forms.renderers" does not define a "DjangoDivFormRenderer" attribute/class
    6.1.1        ImportError: Module "django.forms.renderers" does not define a "DjangoDivFormRenderer" attribute/class
    this commit  ImportError: Module "django.forms.renderers" does not define a "DjangoDivFormRenderer" attribute/class
```

## The attributes for screen readers

5.0 gave an input `"aria-describedby"`, naming its help text, and `"aria-invalid"` when the field has errors. 5.1 put `"aria-describedby"` on the `<fieldset>` drawn around a widget whose `Widget.use_fieldset` is true. 5.2 added the errors to it (`docs/releases/5.0.txt`, `docs/releases/5.1.txt`, `docs/releases/5.2.txt`). At this commit `BoundField.aria_describedby` (5.2) gives the ids of the help text and errors the field has (`django/forms/boundfield.py:BoundField.aria_describedby`). `BoundField.build_widget_attrs` puts them on the input unless the widget has its own or asks for a fieldset. The error list takes its id from `ErrorList.field_id` (5.2), which `BaseForm.add_error` sets (`django/forms/forms.py:BaseForm.add_error`). A required field with help text, submitted empty, drew the same under all four; this commit's lines:

```text recording=changes
form["title"].as_field_group(): a required field with help text, sent empty
...
    this commit
        <label for="id_title">Title:</label>
        <div class="helptext" id="id_title_helptext">At most twenty characters.</div>
        <ul class="errorlist" id="id_title_error"><li>This field is required.</li></ul>
        <input type="text" name="title" maxlength="20" required aria-invalid="true" aria-describedby="id_title_helptext id_title_error" id="id_title">
```

The input names both ids, and is marked invalid ([`BoundField`: a field in a form](../forms/bound-fields.md#the-attributes-a-bound-field-adds)).

> **Trap.** Of the form templates, only `"django/forms/field.html"` draws a fieldset. When `RenderableFormMixin.as_p`, `RenderableFormMixin.as_table` or `RenderableFormMixin.as_ul` draws a `RadioSelect` field, its help text and errors get their ids and nothing names them: the inputs take no `"aria-describedby"`, because the widget asks for a fieldset. From 5.2.17 to this commit, `as_p` wrote the attribute nowhere.

## The URL field's scheme

`URLField.to_python` puts a scheme in front of a value that has none (`django/forms/fields.py:URLField.to_python`). 5.0 made that scheme, until then `"http"`, the argument assume_scheme and deprecated the default, with a transitional setting, FORMS_URLFIELD_ASSUME_HTTPS, to take `"https"` early. 6.0 made the default `"https"` and removed the setting (`django/forms/fields.py:URLField.__init__`). A field made without the argument:

```text recording=changes
forms.URLField().clean("journal.example.com")
    5.2.17       'http://journal.example.com', warns RemovedInDjango60Warning
    6.0.8        'https://journal.example.com'
    6.1.1        'https://journal.example.com'
    this commit  'https://journal.example.com'
```

Nothing in Django passes the argument, so the form field of a model's URL field does the same ([The built-in form fields](../forms/field-types.md#urls-and-the-assumed-scheme)).

## The blank choice's label

A blank choice, the empty option at the head of a `ModelChoiceField`'s choices or a model field's, was labelled with dashes. Since 6.1 `get_blank_choice_label` gives the label: `BLANK_CHOICE_LABEL`, a translated `"- Select an option -"`, or the dashes of `BLANK_CHOICE_DASH` while `USE_BLANK_CHOICE_DASH` is true (`django/db/models/utils.py:get_blank_choice_label`). The model's side is in [What changed in models and fields](models.md). The label of a field made with no `empty_label`:

```text recording=changes
forms.ModelChoiceField(Entry.objects.all()).empty_label
    5.2.17       '---------'
    6.0.8        '---------'
    6.1.1        '- Select an option -'
    this commit  '- Select an option -'
```

The label changed in 6.1, and nothing warned. The setting and the constant are deprecated, to go in Django 2028 ([What still warns: the deprecations and the releases that end them](deprecations.md)). Setting `USE_BLANK_CHOICE_DASH` warns in 6.1.1 and at this commit (`django/conf/__init__.py:Settings.__init__`); reading `BLANK_CHOICE_DASH`, a plain constant, warned under no release (`django/db/models/fields/__init__.py:BLANK_CHOICE_DASH`; [Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](../forms/choices.md#the-blank-choices-label)).

> **Trap.** Since 6.1, `ModelChoiceField.__init__` defaults `empty_label` to `""` and replaces `""` with the blank choice's label (`django/forms/models.py:ModelChoiceField.__init__`). An `empty_label=""` stayed empty under 5.2.17 and 6.0.8, and became `"- Select an option -"` from 6.1.1; the notes speak only of the default. Only the constructor does this: an `empty_label` set to `""` after the field is made is drawn as it is (`django/forms/models.py:ModelChoiceIterator.__iter__`).

## `EmailValidator`, in parts

Before 6.2 `EmailValidator.__call__` checked the whole address, calling one method a subclass could replace, `EmailValidator.validate_domain_part`, which answers true or false. Now `EmailValidator.parse_address` splits the address at its last `"@"`, and `EmailValidator.validate` hands the user part to `EmailValidator.validate_username` and the domain to `EmailValidator.validate_domain` (`django/core/validators.py:EmailValidator.validate`). These two raise `ValidationError` with their part as the parameter `"username"` or `"domain"` (`django/core/validators.py:EmailValidator.validate_username`, `django/core/validators.py:EmailValidator.validate_domain`); under 5.2.17, 6.0.8 and 6.1.1 the error for a bad domain carried `"value"` alone. The methods, the notes say, "can be overridden to customize how the address is parsed and validated" (`docs/releases/6.2.txt`).

The old method is deprecated, to go in Django 2029. A subclass that defines it warns as the class is made, and `validate` calls it in place of `validate_domain` (`django/core/validators.py:EmailValidator.__init_subclass__`; [Validators: `django/core/validators.py`](../forms/validators.md#domain-names-urls-and-email-addresses)). A subclass whose method accepts the domain `"journal"`, given an address there:

```text recording=changes
class LocalEmailValidator(EmailValidator) defining validate_domain_part, given "entry@journal": the domains it is asked about
    5.2.17       ['journal']
    6.0.8        ['journal']
    6.1.1        ['journal']
    this commit  ['journal'], warns RemovedInDjango2029Warning
```

## The smaller changes

Each smaller change by name: what changed, in which release, and where the code at this commit does it.

| the name | what changed | release | where now |
|---|---|---|---|
| `bound_field_class` | on a form field, a form or a renderer, the class of bound field; before, only an override of `Field.get_bound_field` chose one | 5.2 | `django/forms/fields.py:Field.get_bound_field`, [`BoundField`: a field in a form](../forms/bound-fields.md#who-makes-a-bound-field) |
| `ErrorList`, `ErrorDict` | a plain string from their rendering, deprecated in 4.0, is now escaped | 5.0 | `django/template/base.py:render_value_in_context` |
| `Script`, `Stylesheet` | a `Media` asset with HTML attributes; since 6.1 a path given as a string becomes one | 5.2, 6.1 | `django/forms/widgets.py:Media._normalize_js`, `django/forms/widgets.py:Media._normalize_css`, [Form assets: `Media`](../forms/media.md) |
| `FilePathField.set_choices` | scans the directory; the field's `__init__` calls it, and a form's `__init__` may call it again | 6.1 | `django/forms/fields.py:FilePathField.set_choices` |
| `BaseModelFormSet.save_existing` | its second argument, instance, renamed obj; Django passes it positionally | 5.0 | `django/forms/models.py:BaseModelFormSet.save_existing_objects` |
| `StepValueValidator` | an offset to count the steps from; the form `IntegerField` and its subclasses give their `min_value` | 5.0 | `django/forms/fields.py:IntegerField.__init__` |
| `DomainNameValidator` | new, with `validate_domain_name`; `URLValidator` and `EmailValidator` take its host-name patterns; a newline refused since a security fix ([Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md)) | 5.1 | `django/core/validators.py:DomainNameValidator` |
