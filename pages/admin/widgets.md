---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The admin's widgets: related objects, raw ids and autocomplete

The admin's forms use the widgets of `django/contrib/admin/widgets.py`: its own inputs for dates, times, text, numbers, URLs, files and UUIDs; `RelatedFieldWidgetWrapper`, with links to add, change, delete and view a related object; the raw-id widgets `ForeignKeyRawIdWidget` and `ManyToManyRawIdWidget`; and `AutocompleteSelect`, whose script asks `AutocompleteJsonView` for matching rows as the user types.

A model form gives a foreign key a select of every related row, and no way to add a missing one. A clerk should be able to add a port from a ship's form, and a hundred thousand ports cannot be sent down as a select; so the admin puts links to the related model's pages beside a related field, opened in a popup that reports back, and offers widgets that never load the related table.

## The widget for each kind of field

`BaseModelAdmin.__init__` merges `formfield_overrides` into a copy of `FORMFIELD_FOR_DBFIELD_DEFAULTS`, and `formfield_for_dbfield` searches the result along a model field's MRO, so a ship's tonnage, a `PositiveIntegerField`, takes the entry for `IntegerField` ([The admin's forms: `get_form` and `formfield_for_dbfield`](admin-forms.md)) (`django/contrib/admin/options.py:FORMFIELD_FOR_DBFIELD_DEFAULTS`, `django/db/models/fields/__init__.py`, `django/db/models/fields/files.py`).

| model field | widget | its class, or what it adds |
|---|---|---|
| `DateTimeField` | `AdminSplitDateTime`, with `SplitDateTimeField` | the admin's date and time inputs |
| `DateField`, `TimeField` | `AdminDateWidget`, `AdminTimeWidget` | `"vDateField"`, `"vTimeField"`: a calendar, a clock (`django/contrib/admin/static/admin/js/admin/DateTimeShortcuts.js`) |
| `CharField`, `EmailField`, `TextField` | `AdminTextInputWidget`, `AdminEmailInputWidget`, `AdminTextareaWidget` | `"vTextField"`, `"vLargeTextField"` |
| `IntegerField`, `BigIntegerField` | `AdminIntegerFieldWidget`, `AdminBigIntegerFieldWidget` | `"vIntegerField"`, `"vBigIntegerField"` |
| `URLField` | `AdminURLFieldWidget` | a link to the current value, if it is a valid URL |
| `FileField`, `ImageField` | `AdminFileWidget` | the admin's template for the clearable file input |
| `UUIDField` | `AdminUUIDInputWidget` | `"vUUIDField"` |

## How a related field's widget is chosen

A foreign key gets its widget from `BaseModelAdmin.formfield_for_foreignkey`, a many-to-many field from `formfield_for_manytomany`. Each takes the first that applies: a widget passed in, as `formfield_overrides` passes one for a field's exact class; an autocomplete widget for a field `BaseModelAdmin.get_autocomplete_fields` names; a raw-id widget for one in `BaseModelAdmin.raw_id_fields`; then `AdminRadioSelect` for a foreign key in `BaseModelAdmin.radio_fields`, or `FilteredSelectMultiple` for a many-to-many field in `BaseModelAdmin.filter_horizontal` or `filter_vertical`; otherwise the model field's own select (`django/contrib/admin/options.py:BaseModelAdmin.formfield_for_foreignkey`, `django/contrib/admin/options.py:BaseModelAdmin.formfield_for_manytomany`). `formfield_for_dbfield` then wraps the widget of every field not in `raw_id_fields` in `RelatedFieldWidgetWrapper`. ShipAdmin names none, so home and captain are selects inside the wrapper.

## Related objects: `RelatedFieldWidgetWrapper`

`RelatedFieldWidgetWrapper` draws the widget it wraps and after it up to four links into the related model's admin: change the selected object, add another, delete it, view it. `formfield_for_dbfield` gives it the related model admin's answers for the request to `has_add_permission`, `has_change_permission`, `has_delete_permission` and `has_view_permission`, and no link for a model not registered on the site (`django/contrib/admin/options.py:BaseModelAdmin.formfield_for_dbfield`). The wrapper drops change, delete and view beside anything but a select of one value, and delete for a relation whose `on_delete` is `CASCADE`, where a comment calls the deletion confusing (`django/contrib/admin/widgets.py:RelatedFieldWidgetWrapper.__init__`). After home's select on Endeavour's change form:

```text
as nora
  view-related    /admin/fleet/port/__fk__/change/?_to_field=id
as piet
  change-related  /admin/fleet/port/__fk__/change/?_to_field=id&_popup=1&_source_model=fleet.ship
  add-related     /admin/fleet/port/add/?_to_field=id&_popup=1&_source_model=fleet.ship
  delete-related  /admin/fleet/port/__fk__/delete/?_to_field=id&_popup=1&_source_model=fleet.ship
  view-related    /admin/fleet/port/__fk__/change/?_to_field=id
```

nora may only view ports; home is `PROTECT`, so piet's delete link stays; captain had none, sailors not being registered. `"__fk__"` marks where the key goes, which `"RelatedObjectLookups.js"`, a script of `ModelAdmin.media`, fills in when the page loads and whenever the select changes (`django/contrib/admin/widgets.py:RelatedFieldWidgetWrapper.get_context`, `django/contrib/admin/static/admin/js/admin/RelatedObjectLookups.js`). The query string tells the page which field the relation points at (`"_to_field"`), that it is a popup (`"_popup"`), and which model's form opened it (`"_source_model"`).

## The popup and its answer

`"RelatedObjectLookups.js"` opens every link but the view link in a new window. The add or change form there carries the three keys on as hidden inputs, and an addition ends in the popup branch of `ModelAdmin.response_add`: no success message and no redirect, but the new object's value for `"_to_field"` and its text, as JSON, in the template `"admin/popup_response.html"` (`django/contrib/admin/options.py:ModelAdmin.response_add`). piet added a port from home's add link:

```text
POST /admin/fleet/port/add/?_to_field=id&_popup=1&_source_model=fleet.ship
200, data-popup-response {"value": "3", "obj": "Naples"}
```

The answer's script calls a function of the opening window, which adds Naples to home's select and selects it, or writes the key into a raw-id input, and closes the popup (`django/contrib/admin/static/admin/js/admin/RelatedObjectLookups.js`).

## Raw ids: `ForeignKeyRawIdWidget` and `ManyToManyRawIdWidget`

A field in `raw_id_fields` is a text input holding the related object's key, without a wrapper. `ForeignKeyRawIdWidget` adds a link to the related model's change list, if that model is registered, and the current object's text, found by one query and, for a registered model, linked to its change page (`django/contrib/admin/widgets.py:ForeignKeyRawIdWidget.get_context`). home, in a model admin made by hand with `raw_id_fields = ["home"]`:

```text
<div><input type="text" name="home" value="1" required id="id_home" class="vForeignKeyRawIdAdminField">
<a href="/admin/fleet/port/?_to_field=id" class="related-lookup" id="lookup_id_home" title="Lookup"></a>
<strong><a href="/admin/fleet/port/1/change/">Valletta</a></strong></div>
```

The lookup link opens the change list in a popup, where a click on a row writes its value for `"_to_field"` into the input (`django/contrib/admin/templatetags/admin_list.py:items_for_result`). `ManyToManyRawIdWidget` holds keys separated by commas, with no text and no `"_to_field"`, and a key chosen is appended (`django/contrib/admin/widgets.py:ManyToManyRawIdWidget`, `django/contrib/admin/static/admin/js/admin/RelatedObjectLookups.js`).

A relation's `limit_choices_to`, if a dictionary, goes into the link's query string too (`django/contrib/admin/widgets.py:url_params_from_lookup_dict`). `BaseModelAdmin.lookup_allowed` refuses a lookup across a relation that neither a filter nor the date hierarchy offers, but first admits any lookup and value a foreign key to the model has in its `limit_choices_to`, so that, its comment says, these popups work (`django/contrib/admin/options.py:BaseModelAdmin.lookup_allowed`).

## Radio buttons and the filter box

`AdminRadioSelect` serves a foreign key or a field with choices named in `radio_fields`, with the class `"radiolist"` for `VERTICAL` or `"radiolist inline"` for `HORIZONTAL`; beside a foreign key's buttons the wrapper shows at most the add link (`django/contrib/admin/options.py:get_ul_class`, `django/contrib/admin/options.py:BaseModelAdmin.formfield_for_choice_field`).

`FilteredSelectMultiple` is a multiple select that `"SelectFilter2.js"` turns into two filtered boxes, available and chosen, side by side for `filter_horizontal` and stacked for `filter_vertical`, keeping, since 6.1, named groups of choices as optgroups; the script, the widget's docstring warns, needs the JavaScript catalogue (`django/contrib/admin/widgets.py:FilteredSelectMultiple`, `django/contrib/admin/static/admin/js/SelectBox.js`, `docs/releases/6.1.txt`).

## Autocomplete: `AutocompleteSelect` and `AutocompleteJsonView`

`AutocompleteSelect` and `AutocompleteSelectMultiple` add `AutocompleteMixin` to the form library's selects and hand the work to Select2, which the admin ships. The widget draws only the selected options, found by one query if any, and a blank one for an optional single select (`django/contrib/admin/widgets.py:AutocompleteMixin.optgroups`), and writes in attributes what Select2 needs to fetch the rest: the URL of the site's autocomplete view; the application, model and name of the field being edited; and a `"lang"`, the active language as Select2 names it, whose translation the widget's media add to jQuery and Select2 (`django/contrib/admin/widgets.py:AutocompleteMixin.build_attrs`, `django/contrib/admin/widgets.py:get_select2_language`).

`AdminSite.autocomplete_view` is wrapped like the site's other pages: tomas, not staff, was sent to the login. It runs `AutocompleteJsonView`, a `BaseListView` ([`DetailView` and `ListView`](../views/display.md#listview-many-objects-and-pages-of-them)). `process_request` reads `"term"`, `"app_label"`, `"model_name"` and `"field_name"`, and answers 403 unless the last three lead to a relation whose model is registered on the site, since, its docstring says, the permission check needs that model's admin; 404 if that model admin's `get_search_fields` gives no fields; and 403 if the relation's target field fails `to_field_allowed` (`django/contrib/admin/views/autocomplete.py:AutocompleteJsonView.process_request`). Then it asks that model admin's `has_view_permission`, takes its queryset, narrows it by `limit_choices_to`, searches it with `get_search_results` ([Filters and search: `list_filter`, `search_fields` and `date_hierarchy`](filters.md)), and pages it twenty rows at a time (`django/contrib/admin/views/autocomplete.py:AutocompleteJsonView.get`, `django/contrib/admin/views/autocomplete.py:AutocompleteJsonView.get_queryset`). As nora:

```text
GET /admin/autocomplete/?term=pir&app_label=fleet&model_name=ship&field_name=home
  200 {"results": [{"id": "2", "text": "Piraeus"}], "pagination": {"more": false}}
```

The view consults neither the form's own model admin, not even on whether its `autocomplete_fields` holds the field (ShipAdmin's did not), nor the user's permissions on that model: nora, with none on voyages, got the same answer for a voyage's calls. It guards the related model, which a user must be allowed to view so that, the documentation says, its rows are not disclosed (`docs/ref/contrib/admin/index.txt`). The system checks require each field of `autocomplete_fields` to lead to a model admin with `search_fields` ([The admin's checks: `check_dependencies` and `ModelAdminChecks`](checks.md)).
