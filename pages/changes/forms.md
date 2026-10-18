---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in forms and validators

Forms drawn in divisions, with a template for each field and attributes for screen readers; the URL field's `"https"`; the blank choice's label; and `EmailValidator` split into methods a subclass can replace.

In 6.0 two deprecations ended: the transitional renderers went, and the URL field's assumed scheme became `"https"`. 6.1 replaced the blank choice's dashes with a label "more accessible and translatable" (`docs/releases/6.1.txt`). 6.2 split `EmailValidator` into methods a subclass can replace. 5.0 made the division layout the default, which the 4.1 notes had recommended as "easier for screen reader users to navigate" (`docs/releases/4.1.txt`). 5.0 also gave each field a template. And 5.0 tied an input to its help text for screen readers, a tie that 5.1 carried to the fieldset and 5.2 to the errors.

## How a form is drawn: divisions, and a template for each field

Since 5.0 a form rendered as a string uses `BaseRenderer.form_template_name`, `"django/forms/div.html"` (`django/forms/forms.py:BaseForm.template_name`). 5.0 removed the former default, django/forms/default.html, a proxy for the table layout, and its formset twin. It also removed BaseForm's _html_output, which drew the layouts in Python before 4.0 (`docs/releases/4.0.txt`, `docs/releases/5.0.txt`).

The division template prints each visible field's `RenderableFieldMixin.as_field_group` (5.0), which draws label, help text, errors and widget from the field's template, by default `"django/forms/field.html"` (`django/forms/boundfield.py:BoundField.template_name`; [Rendering a form: renderers and templates](../forms/rendering.md#the-built-in-templates)).

From 4.1 a transitional renderer named in `FORM_RENDERER` gave the division layout early. 5.0 deprecated DjangoDivFormRenderer and Jinja2DivFormRenderer, and 6.0 removed them. A project whose setting still names one gets it, with a warning, under 5.2.17; since 6.0 the import fails (`django/forms/renderers.py:get_default_renderer`):

```text recording=changes
FORM_RENDERER = "django.forms.renderers.DjangoDivFormRenderer": the class of a form's renderer
    5.2.17       DjangoDivFormRenderer, warns RemovedInDjango60Warning
    6.0.8        ImportError: Module "django.forms.renderers" does not define a "DjangoDivFormRenderer" attribute/class
    6.1.1        ImportError: Module "django.forms.renderers" does not define a "DjangoDivFormRenderer" attribute/class
    this commit  ImportError: Module "django.forms.renderers" does not define a "DjangoDivFormRenderer" attribute/class
```

## The attributes for screen readers

Since 5.2 the attribute `"aria-describedby"` names a field's help text and errors, on its input or on the fieldset its widget asks for. 5.0 put it on the input, naming the help text, and marked an input with errors `"aria-invalid"`. 5.1 put it on the `<fieldset>` drawn around a widget whose `Widget.use_fieldset` is true (`docs/releases/5.0.txt`, `docs/releases/5.1.txt`, `docs/releases/5.2.txt`).

At this commit `BoundField.aria_describedby` (5.2) gives the ids of the help text and errors the field has (`django/forms/boundfield.py:BoundField.aria_describedby`). `BoundField.build_widget_attrs` puts them on the input unless the attribute is given or the widget asks for a fieldset (`django/forms/boundfield.py:BoundField.build_widget_attrs`). The error list takes its id from `ErrorList.field_id` (5.2), which `BaseForm.add_error` sets (`django/forms/forms.py:BaseForm.add_error`; [`BoundField`: a field in a form](../forms/bound-fields.md#the-attributes-a-bound-field-adds)).

A required field with help text, submitted empty, drew the same under all four; in this commit's lines the input names both ids and is marked invalid:

```text recording=changes
form["title"].as_field_group(): a required field with help text, sent empty
...
    this commit
        <label for="id_title">Title:</label>
        <div class="helptext" id="id_title_helptext">At most twenty characters.</div>
        <ul class="errorlist" id="id_title_error"><li>This field is required.</li></ul>
        <input type="text" name="title" maxlength="20" required aria-invalid="true" aria-describedby="id_title_helptext id_title_error" id="id_title">
```

> **Trap.** Of the form templates, only `"django/forms/field.html"` draws a fieldset. So when `RenderableFormMixin.as_p`, `RenderableFormMixin.as_table` or `RenderableFormMixin.as_ul` draws a `RadioSelect` field, its help text and errors get their ids and nothing names them. The inputs take no `"aria-describedby"`, because the widget asks for a fieldset. Under all four, `as_p` wrote the attribute nowhere.

## The URL field's scheme

Since 6.0 a form's URL field by default puts `"https"` in front of a value with no scheme, where it put `"http"` (`django/forms/fields.py:URLField.to_python`). 5.0 made the scheme the argument `assume_scheme=` and deprecated its default (`django/forms/fields.py:URLField.__init__`). A transitional setting, FORMS_URLFIELD_ASSUME_HTTPS, took `"https"` early, until 6.0 removed it. For a field made without `assume_scheme=`, 5.2.17's line is the old scheme, with its warning:

```text recording=changes
forms.URLField().clean("journal.example.com")
    5.2.17       'http://journal.example.com', warns RemovedInDjango60Warning
    6.0.8        'https://journal.example.com'
    6.1.1        'https://journal.example.com'
    this commit  'https://journal.example.com'
```

Nothing in Django passes the argument, so the form field of a model's URL field does the same ([The built-in form fields](../forms/field-types.md#urls-and-the-assumed-scheme)).

## The blank choice's label

Since 6.1 a blank choice, the empty option at the head of choices such as a `ModelChoiceField`'s or a model field's, is labelled `"- Select an option -"` where it had dashes ([What changed in models and fields](models.md)). `get_blank_choice_label` gives it: `BLANK_CHOICE_LABEL`, translated, or the dashes of `BLANK_CHOICE_DASH` while `USE_BLANK_CHOICE_DASH` is true (`django/db/models/utils.py:get_blank_choice_label`). Nothing warns of the change: for a field made without `empty_label=`, the dashes of 5.2.17 and 6.0.8 are the old label:

```text recording=changes
forms.ModelChoiceField(Entry.objects.all()).empty_label
    5.2.17       '---------'
    6.0.8        '---------'
    6.1.1        '- Select an option -'
    this commit  '- Select an option -'
```

The setting and the constant are deprecated, to go in Django 2028 ([What still warns: the deprecations and the releases that end them](deprecations.md)). Since 6.1, setting `USE_BLANK_CHOICE_DASH` warns (`django/conf/__init__.py`). Reading `BLANK_CHOICE_DASH`, a plain constant, warned under no release (`django/db/models/fields/__init__.py:BLANK_CHOICE_DASH`; [Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](../forms/choices.md#the-blank-choices-label)).

> **Trap.** Since 6.1, `ModelChoiceField.__init__` defaults `empty_label=` to `""` and replaces `""` with the blank choice's label (`django/forms/models.py:ModelChoiceField.__init__`). An `empty_label=""` stayed empty under 5.2.17 and 6.0.8, and is `"- Select an option -"` under 6.1.1 and this commit. The notes speak only of the default. Only the constructor does this: an `empty_label` set to `""` after the field is made is drawn as it is (`django/forms/models.py:ModelChoiceIterator.__iter__`).

## `EmailValidator`, in parts

In 6.2 `EmailValidator` checks an address in methods a subclass can replace (`docs/releases/6.2.txt`). Before, `EmailValidator.__call__` checked the whole address and called one replaceable method, `EmailValidator.validate_domain_part`, which answers true or false. Now `EmailValidator.parse_address` splits the address at its last `"@"`. `EmailValidator.validate` hands the user part to `EmailValidator.validate_username` and the domain to `EmailValidator.validate_domain` (`django/core/validators.py:EmailValidator.validate`). These two raise `ValidationError` with their part as the parameter `"username"` or `"domain"` (`django/core/validators.py:EmailValidator.validate_username`, `django/core/validators.py:EmailValidator.validate_domain`). Under 5.2.17, 6.0.8 and 6.1.1 the error for a bad domain carried `"value"` alone.

The old method is deprecated, to go in Django 2029. A subclass that defines it warns as the class is made (`django/core/validators.py:EmailValidator.__init_subclass__`). `validate` then calls it in place of `validate_domain` ([Validators: `django/core/validators.py`](../forms/validators.md#domain-names-urls-and-email-addresses)). A subclass whose `validate_domain_part` accepts the domain `"journal"` is still asked about it under all four, and only this commit's line warns:

```text recording=changes
class LocalEmailValidator(EmailValidator) defining validate_domain_part, given "entry@journal": the domains it is asked about
    5.2.17       ['journal']
    6.0.8        ['journal']
    6.1.1        ['journal']
    this commit  ['journal'], warns RemovedInDjango2029Warning
```

## The smaller changes

| what | change | where |
|---|---|---|
| `bound_field_class` | New in 5.2: on a form field, a form or a renderer, the class of bound field; before, only an override of `Field.get_bound_field` chose one | `django/forms/fields.py:Field.get_bound_field` |
| `ErrorList`, `ErrorDict` | Since 5.0, a plain string from their rendering is escaped; 4.0 had deprecated it | `django/template/base.py:render_value_in_context` |
| `Script` | New in 5.2: a `Media` asset for a script, with HTML attributes; since 6.1, a script's path given as a string becomes one | `django/forms/widgets.py:Media._normalize_js` |
| `Stylesheet` | New in 6.1: a `Media` asset for a stylesheet, with HTML attributes; a stylesheet's path given as a string becomes one | `django/forms/widgets.py:Media._normalize_css` |
| `FilePathField.set_choices` | New in 6.1: scans the directory; the field's `__init__` calls it, and a form's `__init__` may call it again | `django/forms/fields.py:FilePathField.set_choices` |
| `BaseModelFormSet.save_existing` | Since 5.0, its second argument is `obj=`, once `instance=`; Django passes it by position | `django/forms/models.py:BaseModelFormSet.save_existing_objects` |
| `StepValueValidator` | New in 5.0: `offset=`, a value to count the steps from; the form `IntegerField` and its subclasses give their `min_value` | `django/forms/fields.py:IntegerField.__init__` |
| `DomainNameValidator` | New in 5.1: validates a domain name, as does `validate_domain_name`; `URLValidator` and `EmailValidator` take its host-name patterns | `django/core/validators.py:DomainNameValidator` |
| a newline in a domain name | Since 5.2.16 and 6.0.7, a security fix, refused by `DomainNameValidator` | [Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md) |
