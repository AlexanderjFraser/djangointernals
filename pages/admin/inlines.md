---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Inlines: `InlineModelAdmin` and its formsets

An `InlineModelAdmin` edits the rows of a related model on the parent's change form, as an inline formset. `ModelAdmin.get_inline_instances` makes the inlines for each request, `InlineModelAdmin.get_formset` makes each one's formset class, `ModelAdmin._create_formsets` binds them, and `InlineAdminFormSet` walks them for the templates of `TabularInline` and `StackedInline`.

A port's ships each hold a foreign key to it, and are best edited on its page. The forms package has the tool, an inline formset ([Model formsets and inline formsets](../forms/model-formsets.md)). The admin adds what a page for many users needs: rows a user may not add or change left unsaved whatever the browser sends; a child held by a protected relation refused for deletion; prefixes that keep several formsets apart; and the script that adds rows in the browser.

## An inline for each request

An inline is a `BaseModelAdmin`, with a model admin's options for its form (`fields`, `fieldsets`, `readonly_fields`, `form`) and its own `formfield_for_dbfield`, which makes its widgets ([The admin's forms: `get_form` and `formfield_for_dbfield`](admin-forms.md)). Its own options are these (`django/contrib/admin/options.py:InlineModelAdmin`):

| option | default | what it decides |
|---|---|---|
| `InlineModelAdmin.model` | `None` | the child model |
| `InlineModelAdmin.fk_name` | `None` | the foreign key to the parent, needed when the child has several |
| `InlineModelAdmin.formset` | `BaseInlineFormSet` | the formset's base class |
| `InlineModelAdmin.extra`, `min_num`, `max_num` | 3, `None`, `None` | the formset's counts, read through `InlineModelAdmin.get_extra`, `get_min_num` and `get_max_num` |
| `InlineModelAdmin.can_delete` | `True` | whether a child can be ticked for deletion |
| `InlineModelAdmin.show_change_link` | `False` | a link to each child's change page, if its model is registered |
| `InlineModelAdmin.template` | `None`, set by `StackedInline` and `TabularInline` | the template that draws the formset |
| `InlineModelAdmin.classes` | `None` | CSS classes for the group; `"collapse"` folds it, unless one of its forms has errors |
| `InlineModelAdmin.verbose_name`, `verbose_name_plural` | `None` | the names the group shows: unset, the model's, but the plural is `verbose_name` and an "s" when only that is set |

*The options of an inline. `InlineModelAdmin.__init__` works out the names; the checks are in [The admin's checks: `check_dependencies` and `ModelAdminChecks`](checks.md) (`django/contrib/admin/options.py:InlineModelAdmin.__init__`, `django/contrib/admin/checks.py:InlineModelAdminChecks`).*

An inline is not made at registration. `ModelAdmin.inlines` lists classes, `BaseModelAdmin.get_inlines` is its hook, and `ModelAdmin.get_inline_instances` makes an instance of each, with the parent's model and the site, each time a change form is drawn or posted. It leaves out an inline whose model the user may not view, change, add or delete, and sets `max_num` to 0 on one whose objects the user may not add (`django/contrib/admin/options.py:ModelAdmin.get_inline_instances`). With a `StackedInline` of voyages on ShipAdmin, piet's change form for Endeavour had a formset, `"voyage_set"`, with a form for each voyage, the three extra forms of the default `extra`, and the empty form; nora, with no permission on voyages, had none.

## The formset class: `InlineModelAdmin.get_formset`

`InlineModelAdmin.get_formset` gathers the arguments of `inlineformset_factory` from the inline's hooks and calls it with the parent's model and the child's (`django/contrib/admin/options.py:InlineModelAdmin.get_formset`). The fields are those of `get_fieldsets`; the excluded fields are `get_exclude`'s and the read-only ones, with the form's own exclusions when `get_exclude` returns `None`; `formfield_for_dbfield` is the callback, with the request bound in; the counts come from the three hooks; and `can_delete` holds only when the user has the delete permission. Keyword arguments to `get_formset` override them.

The form it passes is a subclass of the inline's `form`, made inside the method at each call and closing over the user's permissions. Its `has_changed` answers false for an existing child when the user may not change, and for a new one when the user may not add. A model formset saves only the forms that have changed, so such a row is never saved, whatever the browser sent for it.

Its `is_valid` validates as usual and then refuses to delete a child that something protects. When the form's `"DELETE"` is ticked and its object exists, it collects the object with `NestedObjects`, which keeps protected objects instead of raising ([Deleting: `delete_view` and `get_deleted_objects`](deleting.md)), and raises a `ValidationError` naming any it found: since 6.1, at most the inline's `BaseModelAdmin.delete_confirmation_max_display` of them and a count of the rest, though `None`, the default, and 0 both name them all. A formset leaves forms ticked for deletion out of `BaseFormSet.is_valid`, but `BaseModelFormSet.clean` calls `BaseModelFormSet.validate_unique`, which asks every form whether it is valid; the exception escapes, and `BaseFormSet.full_clean` keeps it as an error of the whole formset (`django/forms/models.py:BaseModelFormSet.validate_unique`, `django/forms/formsets.py:BaseFormSet.full_clean`). The change form is shown again; nothing is deleted.

## Binding the formsets: `ModelAdmin._create_formsets`

The change form calls `ModelAdmin._create_formsets` for a `"GET"` and a `"POST"` alike, with the parent: the object being changed, or on an add page the parent form's unsaved instance. It takes each formset class and its inline from `ModelAdmin.get_formsets_with_inlines` and binds it with what `ModelAdmin.get_formset_kwargs` returns: the parent as `instance=`, the prefix, the inline's `InlineModelAdmin.get_queryset`, empty for a user who may neither view nor change, and for a `"POST"` a copy of the data, the files, and `save_as_new=True` when `"_saveasnew"` was pressed (`django/contrib/admin/options.py:ModelAdmin._create_formsets`, `django/contrib/admin/options.py:ModelAdmin.get_formset_kwargs`).

The prefix is the formset class's default, the parent's accessor for its children: for ships, their `related_name`, `"ships"`. A prefix already taken is numbered, so a second inline of ships on the port is `"ships-2"`, and an empty prefix is numbered even the first time.

Two permissions change the binding. "Save as new" makes every child of the copy a new object; for an inline whose objects the user may not add, the copied data's two counts are set to 0, and the copy is saved without children. And for an inline the user may not change, each existing form is given no errors and its initial values as its cleaned data, unless the user ticked it for deletion and may delete; the comment's reason is that a view-only form's data is not in the `"POST"`.

Piet's change form for Valletta, read back:

```text
GET /admin/fleet/port/1/change/ as piet
ships-group, data-inline-type tabular
  data-inline-formset  {"name": "#ships", "options": {"prefix": "ships", "addText": "Add another Ship", "deleteText": "Remove"}}
  management form      TOTAL_FORMS 3, INITIAL_FORMS 2, MIN_NUM_FORMS 0, MAX_NUM_FORMS 1000
  row ships-0         id 2, home 1, name Beagle, tonnage 235, DELETE
  row ships-1         id 1, home 1, name Endeavour, tonnage 366, DELETE
  row ships-2         id, home 1, name, tonnage
  row ships-empty     id, home 1, name, tonnage
```

Each input is named by its row's prefix and its field, `"ships-0-name"`. The initial forms carry their ship's key and, in an `InlineForeignKeyField`, the port's; the third row is the extra form of `extra = 1`; the last is the formset's `BaseFormSet.empty_form`, named with `"__prefix__"`. With `max_num` unset, the maximum is `DEFAULT_MAX_NUM`. Posted back with Resolution, 462 tons, in the extra row, the page redirected to the ports' list: the port was updated, Resolution inserted, and Beagle and Endeavour, validated and unchanged, not written.

## Drawing the inlines: `InlineAdminFormSet`

`ModelAdmin.get_inline_formsets` wraps each formset in an `InlineAdminFormSet`, with the inline's fieldsets, read-only fields and permissions. The inline's add, change and delete permissions count only when the user may change the parent, or add it on an add page; otherwise all three are false and the formset's `extra` and `max_num` are set to 0 ([Permissions in the admin: `has_change_permission` and the others](admin-permissions.md)) (`django/contrib/admin/options.py:ModelAdmin.get_inline_formsets`). Nora may change ships but not ports, and her Valletta had `"ships-MAX_NUM_FORMS"` 0, the ships' names and tonnages as text beside their hidden keys, and no extra or empty row.

Iterated, an `InlineAdminFormSet` yields an `InlineAdminForm` for each initial form, with its object, all read-only when the user may not change; one for each extra form; and one for the empty form, only when the user may add. Each walks its fieldsets as `InlineFieldset`s, which leave out the foreign key to the parent; the templates put it, and the child's key where needed, in hidden inputs (`django/contrib/admin/helpers.py:InlineAdminFormSet.__iter__`, `django/contrib/admin/helpers.py:InlineFieldset.__iter__`). The change form includes each inline's `template`: `"admin/edit_inline/tabular.html"`, a table with a row for each form and headings from `InlineAdminFormSet.fields`, or `"admin/edit_inline/stacked.html"`, each form a block of its own (`django/contrib/admin/templates/admin/edit_inline/`).

Rows are added in the browser. The template writes `InlineAdminFormSet.inline_formset_data`, JSON, in the group's `"data-inline-formset"`; `"inlines.js"`, in the inline's `InlineModelAdmin.media`, reads it and shows an "Add another Ship" link while the maximum exceeds the total. A click copies the row `"ships-empty"`, puts the next index in place of `"__prefix__"`, and adds one to `"TOTAL_FORMS"`; removing a new row numbers the rest again (`django/contrib/admin/static/admin/js/inlines.js`). The server sees a total and the inputs under each index.

## Saving and the log

Once the parent's form and every formset are valid and the parent is saved, `ModelAdmin.save_related` saves each formset through `ModelAdmin.save_formset`, which calls the formset's `save` ([The change form: `changeform_view`](change-form.md)) (`django/contrib/admin/options.py:ModelAdmin.save_related`). The parent's change message gains an entry for each object a formset added, changed or deleted, in the parent's row of the log ([The log and the history: `LogEntry` and `history_view`](log.md)) (`django/contrib/admin/utils.py:construct_change_message`). Piet's `"POST"` logged, on Valletta:

```text
change_message   [{"added": {"name": "ship", "object": "Resolution"}}]
str(entry)       Changed “Valletta” — Added ship “Resolution”.
```
