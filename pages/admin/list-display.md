---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The change list's columns: `list_display` and `list_editable`

`ModelAdmin.list_display` names the columns of a model's change list. For each name `label_for_field` makes the header, and `lookup_field` finds each row's value, which, but for a foreign key's, `display_for_field` or `display_for_value` writes into the cell; `ModelAdmin.list_editable` turns cells into the fields of a model formset that saves the page's rows at once.

A column is one name, and from it the admin makes a header, a cell for each row and, where it can, a sort. The name may be a field, a path across relations, a method or a function, so functions resolve it in a fixed order and the drawing decides by what they found. This happens as the template renders, in the tag result_list, an `InclusionAdminNode` whose function `result_list` calls `result_headers` and, for each row of the page, `items_for_result` ([The admin's templates and media](templates.md)) (`django/contrib/admin/templatetags/admin_list.py:result_list`). A page holds `ModelAdmin.list_per_page` rows, or, when the query string has `"all"`, every row if they are no more than `ModelAdmin.list_max_show_all`, and the `pagination` tag links the others ([The change list: `changelist_view` and `ChangeList`](change-list.md)).

## What a name may be: `lookup_field`

`ModelAdmin.list_display` is `("__str__",)` unless a project sets it; `ModelAdmin.get_list_display` is its hook. When the user has an action for the change list, `ModelAdmin.get_changelist_instance` puts `"action_checkbox"` first, the name of the method `ModelAdmin.action_checkbox`, which draws a row's checkbox ([Actions: `response_action` and `delete_selected`](actions.md)) (`django/contrib/admin/options.py:ModelAdmin.get_changelist_instance`).

`lookup_field` resolves a name against a row in this order (`django/contrib/admin/utils.py:lookup_field`):

1. A field of the model; not a reverse foreign key, a generic foreign key, or a foreign key's column name such as `"home_id"` (`django/contrib/admin/utils.py:_get_non_gfk_field`).
2. A callable, called with the row.
3. An attribute of the model admin, called with the row; never `"__str__"`.
4. An attribute of the model, called if callable.
5. A path across relations, `"home__name"`, walked an attribute at a time; an empty link gives no value.

It returns the field if the name is one, else the attribute it found, and the value. For Endeavour, "home" gave the foreign key, no attribute and Valletta; "is_large", no field, ShipAdmin's bound method and `True`. The checks refuse a reverse foreign key, and a many-to-many field, which, the documentation says, would need a query for each row ([The admin's checks: `check_dependencies` and `ModelAdminChecks`](checks.md)) (`docs/ref/contrib/admin/index.txt`).

## The header: `label_for_field`

`label_for_field` gives a field's `verbose_name`, and for `"__str__"` the model's; otherwise the attribute's `"short_description"`, else a name made readable by `pretty_name`, "--" for a lambda. A path is made readable itself: the header of `"home__name"` is "Home  name", each underscore a space (`django/contrib/admin/utils.py:label_for_field`, `django/forms/utils.py:pretty_name`).

`result_headers` makes a header a sorting link when the name is among what `BaseModelAdmin.get_sortable_by` returns: `sortable_by`, or, when that is `None` as by default, what `get_list_display` returns (`django/contrib/admin/options.py:BaseModelAdmin.get_sortable_by`). A name that is not a field needs an `"admin_order_field"` on its attribute, or must be a path ending at a field; the documentation says the database does the sorting (`django/contrib/admin/templatetags/admin_list.py:result_headers`, `docs/ref/contrib/admin/index.txt`).

The sort is kept in `"o"`: the positions of the sorted columns, `"action_checkbox"` counted, by priority, "-" marking descent. `ChangeList.get_ordering_field_columns` says which columns are sorted; without `"o"` it guesses from the default ordering, since, its comment says, several columns may sort by one field (`django/contrib/admin/views/main.py:ChangeList.get_ordering_field_columns`). `ChangeList.get_ordering_field` says what a column sorts by (`django/contrib/admin/views/main.py:ChangeList.get_ordering_field`). Ship is ordered by name, so nora's list came with Name marked as sorted, and Large's header linked to ?o=4.1, column 4, which sorts by tonnage, then column 1. That page's query ended `ORDER BY "fleet_ship"."tonnage" ASC, "fleet_ship"."name" ASC, "fleet_ship"."id" DESC`.

## The cell: `items_for_result`

`items_for_result` starts each cell from the **empty value**, what a cell shows when there is nothing to show: the model admin's `empty_value_display` if it has one, else the site's, `AdminSite.empty_value_display`, `"-"` by default (`django/contrib/admin/options.py:BaseModelAdmin.get_empty_value_display`); an attribute's `"empty_value_display"` replaces it for its column. Then what `lookup_field` found decides the text (`django/contrib/admin/templatetags/admin_list.py:items_for_result`):

- **A foreign key or one-to-one field**: the related object's `str`, or the empty value.
- **Another field**, or a path's last field: `display_for_field`, by the field's type. Choices give their label; a boolean field an icon for yes, no or unknown; dates, times and numbers the active language's format ([Writing numbers, dates and durations](../i18n/writing-values.md)); a file or URL a link outside the linked column, a URL only if `URLValidator` accepts it, so that, the comment says, a dangerous scheme stays text (`django/contrib/admin/utils.py:display_for_field`).
- **Anything else**, automatic fields included: `display_for_value`, by the value's Python type, or an icon when the attribute has `"boolean"` (`django/contrib/admin/utils.py:display_for_value`).

An `ObjectDoesNotExist` in the lookup, as from an empty reverse one-to-one, gives the empty value; the column's own is not read. The cell is written by `format_html`, which escapes all but a safe string ([Autoescaping and safe strings](../templates/autoescape.md)).

```text
# GET /admin/fleet/ship/ as nora: Endeavour's cells, one to a line
<td class="action-checkbox"><input type="checkbox" name="_selected_action" value="1" class="action-select" aria-label="Select this object for an action - Endeavour"></td>
<th class="field-name"><a href="/admin/fleet/ship/1/change/">Endeavour</a></th>
<td class="field-tonnage">366</td>
<td class="field-home nowrap">Valletta</td>
<td class="field-is_large"><img src="/static/admin/img/icon-yes.svg" alt="True"></td>
```

> **Changed in 6.1.** A path ending at a related model's boolean field is drawn as an icon: the path's last field, from `get_fields_from_path`, writes the cell (`docs/releases/6.1.txt`).

The columns of `ModelAdmin.list_display_links` link to the change form. `ModelAdmin.get_list_display_links` gives the first of `list_display` when the option is empty; `None` means no links (`django/contrib/admin/options.py:ModelAdmin.get_list_display_links`). Asked before `"action_checkbox"` is added, it gave Name the link, reversed by `ChangeList.url_for_result`.

## The decorator `django.contrib.admin.display`

`django.contrib.admin.display` sets on a function the attributes the code reads (`django/contrib/admin/decorators.py:display`).

| argument | sets | read for |
|---|---|---|
| `boolean=True` | `"boolean"` | the cell, as an icon |
| `ordering="tonnage"` | `"admin_order_field"` | the sort |
| `description="Large"` | `"short_description"` | the header |
| `empty_value="none"` | `"empty_value_display"` | the column's empty value |

Given `boolean=` with `empty_value=`, it raises `ValueError`.

## Editing in the list: `list_editable`

`ModelAdmin.list_editable` names fields the change list shows as inputs. It has no hook, and the `ChangeList` drops it in a popup (`django/contrib/admin/views/main.py:ChangeList.__init__`). The checks require each to be an editable field, a column, and not a linked one (`django/contrib/admin/checks.py:ModelAdminChecks._check_list_editable_item`).

The inputs are a model formset over the page's rows ([Model formsets and inline formsets](../forms/model-formsets.md)), made by `ModelAdmin.get_changelist_formset` with no extra form and the form of `ModelAdmin.get_changelist_form`, whose fields `BaseModelAdmin.formfield_for_dbfield` makes ([The admin's forms: `get_form` and `formfield_for_dbfield`](admin-forms.md)) (`django/contrib/admin/options.py:ModelAdmin.get_changelist_formset`). On a `"GET"`, `ModelAdmin.changelist_view` makes it if the user may change the model, and `ModelAdmin._get_formset_with_permissions` takes the fields out of each form whose object `BaseModelAdmin.has_change_permission` refuses (`django/contrib/admin/options.py:ModelAdmin._get_formset_with_permissions`). `items_for_result` draws a cell outside the linked column as its form's field whenever the name is among the form's fields, which, a comment says, lets a project vary them per request (`django/contrib/admin/templatetags/admin_list.py:items_for_result`). The keys go in hidden inputs, with a button named `"_save"`. With `list_editable = ["tonnage"]` on a subclass of ShipAdmin, Endeavour's tonnage became a number input named form-1-tonnage.

A `"POST"` with `"_save"` goes in this order (`django/contrib/admin/options.py:ModelAdmin.changelist_view`):

1. Without the change permission, `PermissionDenied`.
2. `ModelAdmin._get_list_editable_queryset` narrows the queryset to the posted keys, or keeps it whole if a key will not convert: tampered data, its comment says.
3. The formset is bound to the data and that queryset; rows the user may not change lose their fields.
4. If it is valid, `ModelAdmin._save_formset` opens a transaction and, for each changed form the user may change, calls `ModelAdmin.save_form`, `ModelAdmin.save_model`, `ModelAdmin.save_related`, `ModelAdmin.construct_change_message` and `ModelAdmin.log_change`, as the change form does ([The change form: `changeform_view`](change-form.md)). A form whose object is new raises `BadRequest`, a 400 ([How an exception becomes a response](../handlers/exceptions.md)). A message counts the rows; the answer redirects to the same URL.
5. If not, the page comes again, the errors in the cells.

```text
# POST /admin/fleet/ship/ as nora: Beagle at 240 tons, Endeavour at 368, and _save
302 Found
Location: /admin/fleet/ship/
message (success): 2 ships were changed successfully.
log: Beagle [{"changed": {"fields": ["Tonnage"]}}]
log: Endeavour [{"changed": {"fields": ["Tonnage"]}}]
```

Only the saving is in a transaction: `changelist_view` opens none of its own, unlike `ModelAdmin.changeform_view`. Before BEGIN, after the change list's queries, it selected the two ships by key, then each form's ship again through its hidden key, and checked the ship's check constraint; inside, an UPDATE of each ship and an INSERT into `"django_admin_log"` ([The log and the history: `LogEntry` and `history_view`](log.md)). A request like it with a third, new form answered 400, and the transaction took back the update and log row already written.
