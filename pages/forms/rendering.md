---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Rendering a form: renderers and templates

A form, a bound field, a list of errors and a widget each draw themselves by handing a template's name and a context to a renderer, an object of `django/forms/renderers.py` that finds the template and renders it. `get_default_renderer` makes the one the setting `FORM_RENDERER` names, and the built-in templates under `django/forms/templates/` nest, the form's calling each field's.

A form's HTML must be changeable without its Python, for a project or a form class. So each object that draws has a template's name and a `get_context` that makes the template's dictionary, and the renderer, which alone knows where templates are found and in which engine, turns the two into a string.

## Drawing oneself: `RenderableMixin`

`RenderableMixin.render`, called with no arguments, renders the object's `template_name` with the dictionary of its `get_context` through the object's own renderer, and marks the result safe; any of the three can be given instead (`django/forms/utils.py:RenderableMixin.render`). It is also the class's `__str__` and `__html__`, so `{{ form }}` in a template draws the form, and the safe string is not escaped again: a submitted value or a message is escaped once, by the innermost template that prints it ([Autoescaping and safe strings](../templates/autoescape.md)).

`BaseForm` and `BaseFormSet` take it through `RenderableFormMixin`; `BoundField` through `RenderableFieldMixin`, whose `__str__` draws the widget, with no label or errors, and whose `RenderableFieldMixin.as_field_group` is the whole field ([`BoundField`: a field in a form](bound-fields.md)); `ErrorDict` and `ErrorList` through `RenderableErrorMixin`. A widget has a method of its own, `Widget.render`, which hands its context to the renderer it is given, or to the default one ([Widgets: `Widget` and its subclasses](widgets.md)) (`django/forms/widgets.py:Widget._render`).

`RenderableFormMixin` adds `as_div`, `as_p`, `as_table` and `as_ul`, each rendering a name the class holds, such as `BaseForm.template_name_div` (`django/forms/utils.py:RenderableFormMixin`). `str(form)` renders `BaseForm.template_name`, a property that reads the renderer's form template (`django/forms/forms.py:BaseForm.template_name`). In a run, a renderer whose form template was `"django/forms/p.html"` made `str(form)` draw paragraphs while `as_div()` still drew divisions.

## The renderer a form uses

`BaseForm.__init__` settles a form's renderer once: the argument; else the class's `BaseForm.default_renderer`, made an instance if it is a class; else what `get_default_renderer` returns (`django/forms/forms.py:BaseForm.__init__`). Its bound fields, error lists and labels use it, and the bound field hands it to the widget (`django/forms/boundfield.py:BoundField.as_widget`). A widget or an `ErrorList` given no renderer uses the default.

`get_default_renderer` imports the class `FORM_RENDERER` names, by default `"django.forms.renderers.DjangoTemplates"`, and makes an instance. The function is cached, so everything that falls back on it shares one renderer and one engine; under `DjangoTemplates` that engine's loader is the cached one, which keeps each template it has compiled (`django/forms/renderers.py:get_default_renderer`, `django/template/engine.py:Engine.__init__`).

> **Trap.** A class as `BaseForm.default_renderer` makes a new renderer, with a new engine, for each form. In a run, berth forms whose class set it to `DjangoTemplates` each compiled every template they drew; set to an instance, only the first form did.

## `BaseRenderer`: a name and a context in, a string out

`django/forms/renderers.py:BaseRenderer` holds the names of the default templates, `BaseRenderer.form_template_name`, `BaseRenderer.formset_template_name` and `BaseRenderer.field_template_name`, and `BaseRenderer.bound_field_class`, the form's last resort for its class of bound field. A subclass supplies `BaseRenderer.get_template`. `BaseRenderer.render` renders the template with the context and an optional request and strips white space from both ends (`django/forms/renderers.py:BaseRenderer.render`); the blank lines inside a piece stay.

No caller in the forms library passes a request, so the backend renders with a plain context and no context processor runs for a form's templates under Django's renderers ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)) (`django/template/context.py:make_context`, `django/template/backends/jinja2.py:Template.render`).

## `EngineMixin`: an engine of the renderer's own

The renderers `DjangoTemplates` and `Jinja2` share `EngineMixin`, whose `EngineMixin.engine` is made on first use and kept on the renderer: an instance of the renderer's template backend, named `"djangoforms"`, with empty `"OPTIONS"`, `"APP_DIRS"` true, and in `"DIRS"` the directory beside `renderers.py` named after the backend's `app_dirname`: `django/forms/templates/`, or `django/forms/jinja2/`, templates of the same names in Jinja2's syntax (`django/forms/renderers.py:EngineMixin.engine`). It stands apart from `TEMPLATES`, with the backend's defaults: for Django's, the cached loader, `"debug"` from `settings.DEBUG`, and no context processors ([Template engines: `TEMPLATES` and the backends](../templates/engines.md)).

Both backends search `"DIRS"` before the applications' directories (`django/template/engine.py:Engine.__init__`, `django/template/backends/base.py:BaseEngine.template_dirs`). So a built-in template is found in Django's directory first, and an application cannot replace it ([Finding a template: `Engine` and the loaders](../templates/loaders.md)). In a run, an application's own `"django/forms/div.html"` was passed over; a template of a new name in it was found.

## `TemplatesSetting`: the project's engines

`django/forms/renderers.py:TemplatesSetting` keeps no engine: it finds a template with `django.template.loader.get_template`, which asks each backend of `TEMPLATES` in turn (`django/forms/renderers.py:TemplatesSetting.get_template`, `django/template/loader.py:get_template`). The project's directories, applications and options now decide, and its own `"django/forms/div.html"` can replace Django's. The built-in templates are found only where the project's engines look, as with `"django.forms"` in `INSTALLED_APPS` and an engine whose `"APP_DIRS"` is true, or with their directory in `"DIRS"`. In a run with neither, `as_p()` raised `TemplateDoesNotExist` for `"django/forms/p.html"`.

## The form's context: `BaseForm.get_context`

`BaseForm.get_context` gives the form's template four keys (`django/forms/forms.py:BaseForm.get_context`): `"form"`; `"fields"`, a pair for each visible field of its bound field and its errors; `"hidden_fields"`, the bound fields with hidden widgets; and `"errors"`, a copy of `BaseForm.non_field_errors` with each hidden field's errors added, in a run as `"(Hidden field token) This field is required."`. The templates draw a hidden field with no label or errors of its own. A bound field's context is the bound field, under `"field"`.

## The built-in templates

An object's template goes through the renderer; an `{% include %}` inside it is found by the same engine alone.

```text figure=the-templates
str(form) for a BerthForm
->       the object hands the template to the form's renderer
include  an {% include %}, found by the renderer's engine alone

BerthForm                  ->  "django/forms/div.html"
    ErrorList, the form's  ->  "django/forms/errors/list/default.html"
        include                "django/forms/errors/list/ul.html"
    for each field, ship, tonnage and arrives:
    BoundField             ->  "django/forms/field.html"
        BerthForm, for BoundField.label_tag  ->  "django/forms/label.html"
            include                              "django/forms/attrs.html"
        ErrorList, the field's  ->  "django/forms/errors/list/default.html"    even when empty
            include                 "django/forms/errors/list/ul.html"
        the widget              ->  "django/forms/widgets/text.html"      ship, a TextInput
                                    "django/forms/widgets/number.html"    tonnage, a NumberInput
                                    "django/forms/widgets/date.html"      arrives, a DateInput
            include                 "django/forms/widgets/input.html"
                include             "django/forms/widgets/attrs.html"
```

*The templates `str(form)` rendered for the berth form in a run, as they nest.*

`"django/forms/div.html"` prints the form's errors, then a `<div>` for each visible field holding the field's group, and the hidden fields inside the last, if there is one (`django/forms/templates/django/forms/div.html`). `"django/forms/p.html"`, `"django/forms/table.html"` and `"django/forms/ul.html"` follow the same plan, with no `<table>` or `<ul>` around their rows, and draw each field's parts themselves.

The field's template is its own, if it was given one, or the renderer's (`django/forms/boundfield.py:BoundField.template_name`). It draws the label, or a `<fieldset>` and `<legend>` for a widget whose `use_fieldset` is set; the help text; the field's `ErrorList`, whose template is rendered even when it is empty and includes `"django/forms/errors/list/ul.html"`, which writes nothing then ([Validation: `full_clean`, `cleaned_data` and the errors](validation.md)); and the widget. The label is `BaseForm.template_name_label`, rendered by `BoundField.label_tag` through the form (`django/forms/boundfield.py:BoundField.label_tag`). A widget renders its class's `template_name`; most inputs' include `"django/forms/widgets/input.html"`. A formset's default template prints its management form, then each form's `as_div()` ([Formsets: `BaseFormSet` and the management form](formsets.md)).

Attributes are written by included templates: `"django/forms/widgets/attrs.html"` for a widget, `"django/forms/attrs.html"` for a label, in the dictionary's order, leaving out `False` and writing `True` as a bare name. `django/forms/utils.py:flatatt` does the same in Python, for a media asset's attributes among others, but sorts the names, puts the bare ones last and leaves out `None`, which a widget given `{"placeholder": None}` drew, in a run, as `placeholder="None"`.
