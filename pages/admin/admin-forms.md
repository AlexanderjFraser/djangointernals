---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The admin's forms: `get_form` and `formfield_for_dbfield`

`ModelAdmin.get_form` makes a change form's model form class for each request, from the names `BaseModelAdmin.get_fieldsets` gives less those excluded or read-only; `BaseModelAdmin.formfield_for_dbfield` makes each form field from its model field and chooses the admin's widgets. `AdminForm` and its `Fieldset`, `Fieldline`, `AdminField` and `AdminReadonlyField` walk the form in its fieldsets for the template, showing read-only fields from the object.

The admin must make a form for any model without a form class from the project, and one that may change between requests: a user who may only view gets nothing to edit, and a field may be read-only once the object exists. So it keeps three things apart. The **fieldsets** are the layout, groups of field names, named or not, that the template follows. The form class is made from those names by `modelform_factory` for each request, the read-only names left out: a field named read-only is not a form field, and takes no part in validation or saving. And each form field the form does not declare comes from `formfield_for_dbfield`, which `fields_for_model` calls for each model field it takes ([Model forms: `ModelForm` and `fields_for_model`](../forms/model-forms.md)).

## The layout: `get_fieldsets` and `get_fields`

A fieldset is a pair of a name, or `None`, and a dictionary: `"fields"`, a list of names in which a tuple or a list puts several on one line, and optionally `"classes"`, CSS classes for the group, and `"description"`, shown under its heading unescaped. `BaseModelAdmin.get_fieldsets` returns the option `fieldsets` if it is set, else one unnamed fieldset of `BaseModelAdmin.get_fields` (`django/contrib/admin/options.py:BaseModelAdmin.get_fieldsets`). `get_fields` returns `fields` if set; else it builds a form, `get_form` with no fields, and returns the names of its `BaseForm.base_fields` and then the read-only names (`django/contrib/admin/options.py:BaseModelAdmin.get_fields`).

So a model admin that names no fields builds its form twice for each change form: on one `"GET"` of Endeavour's as nora, `BaseModelAdmin.formfield_for_dbfield` ran for id, name, tonnage, home and captain, then for the last four again.

`BaseModelAdmin.get_exclude`, `BaseModelAdmin.get_readonly_fields` and `BaseModelAdmin.get_prepopulated_fields` return the options `exclude`, `readonly_fields` and `prepopulated_fields`. Each takes the request and the object, `None` on the add page, and is a hook for deciding per request. The auth application's `UserAdmin` overrides `get_fieldsets` and `get_form` so that its add page has `UserAdmin.add_fieldsets` and `UserAdmin.add_form` (`django/contrib/auth/admin.py:UserAdmin.get_fieldsets`, `django/contrib/auth/admin.py:UserAdmin.get_form`). An inline's form is made from the same hooks and `formfield_for_dbfield`, by `InlineModelAdmin.get_formset` ([Inlines: `InlineModelAdmin` and its formsets](inlines.md)).

## The form class: `ModelAdmin.get_form`

`ModelAdmin.get_form` takes the request, the object, `change=True` on a change page, and keyword arguments, in this order (`django/contrib/admin/options.py:ModelAdmin.get_form`):

1. The fields are the `fields` argument if there is one (the change form passes its fieldsets' names, `get_fields` passes `None`), else those of `get_fieldsets`, flattened by `flatten_fieldsets`.
2. The exclusions are `get_exclude`'s and every name of `get_readonly_fields`.
3. On a change page whose user may not change the object, every field is excluded too: the view-only form has no form field made from the model ([The change form: `changeform_view`](change-form.md)).
4. The exclusions in the form's own Meta are added only when `get_exclude` gives `None`.
5. The form is subclassed with `type` under its own name, each read-only name it declares as a field set to `None`, which `DeclarativeFieldsMetaclass` takes to drop the field (`django/forms/forms.py:DeclarativeFieldsMetaclass.__new__`).
6. The arguments are that subclass as the form, the fields, the exclusions or `None`, and as `formfield_callback` the model admin's `formfield_for_dbfield` with the request bound to it; `get_form`'s keyword arguments come last and win. Fields still `None`, with a form whose Meta names neither fields nor exclusions, become `ALL_FIELDS` (`django/forms/models.py:modelform_defines_fields`).
7. `modelform_factory` makes the class. A `FieldError` is raised again naming the model admin's class: `fields = ["name", "tonage"]` on ShipAdmin gave “Unknown field(s) (tonage) specified for Ship. Check fields/fieldsets/exclude attributes of class ShipAdmin.”

ShipAdmin names no fields, so its form has all of Ship's but id:

```text
# a run of the example: ShipAdmin's form for Endeavour's change form, as nora and as piet
get_fieldsets   [(None, {'fields': ['name', 'tonnage', 'home', 'captain']})]
get_form        ShipForm < ModelForm < ModelForm < BaseModelForm
  name     CharField         AdminTextInputWidget
  tonnage  IntegerField      AdminIntegerFieldWidget
  home     ModelChoiceField  RelatedFieldWidgetWrapper(Select); links for nora: view; for piet: add, change, delete, view
  captain  ModelChoiceField  RelatedFieldWidgetWrapper(Select); links for nora: none; for piet: none
```

Above ShipForm stand the subclass of the fifth step, named after ShipAdmin's `form`, and that form, `forms.ModelForm`.

## One form field: `formfield_for_dbfield`

`BaseModelAdmin.formfield_for_dbfield` is given a model field, the request, and the keyword arguments from the form's Meta, and decides in this order (`django/contrib/admin/options.py:BaseModelAdmin.formfield_for_dbfield`):

1. A field with choices goes to `BaseModelAdmin.formfield_for_choice_field`, which gives the field's own `models.Field.formfield`, with `AdminRadioSelect` if `radio_fields` names it: a select of some kind needs no admin widget, says the comment.
2. A `ForeignKey` or `ManyToManyField` takes the `formfield_overrides` entry for its exact class and goes to `BaseModelAdmin.formfield_for_foreignkey` or `BaseModelAdmin.formfield_for_manytomany`. Unless `raw_id_fields` names it, the widget that comes back is wrapped in `RelatedFieldWidgetWrapper`, given the related model admin's four permissions for the request, or none if that model is not registered here ([The admin's widgets: related objects, raw ids and autocomplete](widgets.md)).
3. Any other field takes a deep copy of the first entry of `formfield_overrides` along its class's MRO, for its `formfield`.
4. Otherwise the field's `formfield` is called as it is.

The keyword arguments passed in override an entry's, being more specific, says the comment; a field with choices never reaches `formfield_overrides`. `BaseModelAdmin.__init__` makes the entries, merging each of the class's `formfield_overrides` into a copy of `FORMFIELD_FOR_DBFIELD_DEFAULTS`, the admin's widgets by model field class, "rather than simply overwriting" (`django/contrib/admin/options.py:BaseModelAdmin.__init__`). With `formfield_overrides = {models.CharField: {"help_text": "As painted on the stern."}, models.ForeignKey: {"empty_label": "(no port)"}}` on ShipAdmin, name kept `AdminTextInputWidget` beside the help text, and home offered "(no port)", but captain, a `OneToOneField`, did not.

`formfield_for_foreignkey` and `formfield_for_manytomany` choose a widget only when none was passed: by `get_autocomplete_fields`, then `raw_id_fields`, then `radio_fields` for a foreign key, or `filter_vertical` and `filter_horizontal` for a many-to-many (`django/contrib/admin/options.py:BaseModelAdmin.formfield_for_foreignkey`, `django/contrib/admin/options.py:BaseModelAdmin.formfield_for_manytomany`). The queryset, unless passed, is `BaseModelAdmin.get_field_queryset`'s: the related model's default manager, ordered by the related model admin's `BaseModelAdmin.get_ordering` and not filtered by its `BaseModelAdmin.get_queryset`; with no model admin or no ordering, `None`, and the model field makes its own (`django/contrib/admin/options.py:BaseModelAdmin.get_field_queryset`). A many-to-many field through a model of its own gets no form field; and a multiple select other than checkboxes or autocomplete gets "Hold down “Control”, or “Command” on a Mac, to select more than one." in its help text, as Voyage's calls did.

## Walking the form: `AdminForm` and the read-only fields

The change form wraps the form in an `AdminForm`, with the fieldsets, the prepopulated fields and the read-only names, which on a view-only form are every name of the fieldsets (`django/contrib/admin/options.py:ModelAdmin._changeform_view`, `django/contrib/admin/helpers.py:AdminForm`). It gives a `Fieldset` for each fieldset, which gives a `Fieldline` for each entry of `"fields"`, which gives for each name on the line an `AdminReadonlyField` if the name is read-only, else an `AdminField` around the form's `BoundField` ([`BoundField`: a field in a form](../forms/bound-fields.md)). `django/contrib/admin/templates/admin/includes/fieldset.html` walks them. `AdminErrorList` puts the errors of a bound form and of its inline formsets in one list, whose length chooses "error" or "errors" in the note above the fieldsets (`django/contrib/admin/helpers.py:AdminErrorList`).

`AdminReadonlyField` finds a read-only field's label and value itself (`django/contrib/admin/helpers.py:AdminReadonlyField`). The label is the one the form's Meta gives, or `label_for_field`'s: a model field's verbose name, or a callable's `"short_description"`, or else its name made readable. The value is `lookup_field`'s: a model field's value, or what a callable, a method of the model admin, or an attribute or method of the model gives for the object (`django/contrib/admin/utils.py:lookup_field`). A value that is no field's is shown as a boolean icon when the callable carries `"boolean"`, and otherwise as text, escaped unless it is already HTML. A field's value goes by the field: a many-to-many's objects joined by commas; a foreign key's or a one-to-one's object as a link to its change page in this site, with no permission asked, or as its text where no such URL reverses; anything else through `display_for_field`, as the change list shows it ([The change list's columns: `list_display` and `list_editable`](list-display.md)). A lookup that raises `AttributeError`, `ValueError` or `ObjectDoesNotExist` shows the empty value.

`Fieldset.is_collapsible` is true when `"collapse"` occurs in the string of its classes and no name of the fieldset's `"fields"` has an error, so a group that holds an error opens (`django/contrib/admin/helpers.py:Fieldset.is_collapsible`). The template draws a collapsible group as `<details>` with its name as the `<summary>`, and only for a group that has a name: an unnamed fieldset with `"collapse"` is not collapsed.

ShipAdmin with these added gives a collapsed group, and two fields read-only once a ship exists:

```python
# harbour/fleet/admin.py: in ShipAdmin
    fieldsets = [
        (None, {"fields": ["name", "home"]}),
        ("Register", {
            "classes": ["collapse"],
            "description": "As entered in the port's register.",
            "fields": [("tonnage", "captain")],
        }),
    ]

    def get_readonly_fields(self, request, obj=None):
        # once a ship is entered, its home and tonnage are the register's
        return ["home", "tonnage"] if obj else []
```

```text
# a run of the example, as nora: get_form called by hand for adding and for Endeavour, then Endeavour's AdminForm walked
add: base_fields ['name', 'home', 'tonnage', 'captain'], exclude None
change: base_fields ['name', 'captain'], exclude ['home', 'tonnage']
Fieldset None classes='' is_collapsible=False
  Fieldline: AdminField name
  Fieldline: AdminReadonlyField home: <a href="/admin/fleet/port/1/change/">Valletta</a>
Fieldset 'Register' classes='collapse' is_collapsible=True
  Fieldline: AdminReadonlyField tonnage: 366 | AdminField captain
```

> **Trap.** `is_collapsible` looks for a field with an error among the entries of `"fields"` as written, and does not find one inside a tuple. Adding a ship with no tonnage, the Register group opened when its fields were `["tonnage", "captain"]`, and stayed closed over its error when they were `[("tonnage", "captain")]`.
