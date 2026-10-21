---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The change form: `changeform_view`

`ModelAdmin.changeform_view` is the admin's add page and its change page in one view. It loads the object, asks the permission, builds the model form and the inline formsets, and for a `"POST"` validates them and saves through a fixed order of hooks, `ModelAdmin.save_form`, `ModelAdmin.save_model`, `ModelAdmin.save_related`, the log, then `ModelAdmin.response_add` or `ModelAdmin.response_change`, which answer a popup or redirect by the button pressed.

An add page and a change page differ in a few places, among them whether there is an object to load, which permission is asked, what the log says, and where the user goes afterwards; `ModelAdmin.add_view` and `ModelAdmin.change_view` each call `changeform_view`, the first with no object's key (`django/contrib/admin/options.py:ModelAdmin.add_view`).

## The transaction

`ModelAdmin.changeform_view` carries the CSRF check itself, as `csrf_protect` made a method decorator, besides the one `AdminSite.admin_view` adds ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](site-urls.md)). For any method but `"GET"`, `"HEAD"`, `"OPTIONS"` and `"TRACE"` it runs `ModelAdmin._changeform_view` inside `atomic`, on the database the router gives for writing the model; the check stands outside the block (`django/contrib/admin/options.py:ModelAdmin.changeform_view`) ([Transactions: autocommit, `atomic` and savepoints](../connections/atomic.md)).

So a save is one transaction, from the view's first query to the row of the log, and an exception in a later hook, saving the related objects or writing the log, takes the object's save back with it. A form that does not validate leaves the block normally, having written nothing. The page that shows its errors is a `TemplateResponse`, rendered after the view returns ([`SimpleTemplateResponse` and `TemplateResponse`](../templates/responses.md)), so its select widgets query after the commit.

## Before the form

`ModelAdmin._changeform_view` first reads `"_to_field"`, the field a related object's popup names the object by, and refuses one `BaseModelAdmin.to_field_allowed` does not admit, with a 400 ([The change list: `changelist_view` and `ChangeList`](change-list.md)). A `"POST"` carrying `"_saveasnew"` has its object's key dropped: from there on it is an add, of the data posted (`django/contrib/admin/options.py:ModelAdmin._changeform_view`).

An add asks `BaseModelAdmin.has_add_permission` and raises `PermissionDenied` without it. A change loads the object with `ModelAdmin.get_object`, through `BaseModelAdmin.get_queryset`, and asks `BaseModelAdmin.has_view_or_change_permission`; only then, when there is no object, does it redirect to the index with a warning (`django/contrib/admin/options.py:ModelAdmin._get_obj_does_not_exist_redirect`). So a user without the permission gets a 403 for any key: nora got one for voyage 99, and for ship 99 a redirect to /admin/ with "ship with ID “99” doesn’t exist. Perhaps it was deleted?". Ship "abc" got the same, since `get_object` returns `None` for a key its field cannot convert (`django/contrib/admin/options.py:ModelAdmin.get_object`).

A change form then makes the action form for the actions whose location includes it, new in 6.1 ([Actions: `response_action` and `delete_selected`](actions.md)). Last, `BaseModelAdmin.get_fieldsets` gives the groups of fields and `ModelAdmin.get_form` a model form class with the fields they name ([The admin's forms: `get_form` and `formfield_for_dbfield`](admin-forms.md)).

## A `"POST"`: validated, then saved

A `"POST"` that carries the action form's choice and none of `"_save"`, `"_continue"` and `"_addanother"` goes to `ModelAdmin.response_action`; its one selected key must be the object's, or the view raises `BadRequest`. Any other `"POST"` to a change page asks `BaseModelAdmin.has_change_permission`, so a user who may only view gets a 403. The view binds the form to the data, with the object as its instance, and `ModelAdmin._create_formsets` makes the inlines' formsets ([Inlines: `InlineModelAdmin` and its formsets](inlines.md)) (`django/contrib/admin/options.py:ModelAdmin._changeform_view`). If all are valid, it saves through hooks a project overrides to step in:

1. `ModelAdmin.save_form` calls `BaseModelForm.save` with `commit=False`: the instance with the cleaned values on it, unsaved (`django/contrib/admin/options.py:ModelAdmin.save_form`) ([Model forms: `ModelForm` and `fields_for_model`](../forms/model-forms.md)). It runs once the form is valid, before the formsets are asked.
2. `ModelAdmin.save_model` calls the instance's `save`.
3. `ModelAdmin.save_related` calls the form's `save_m2m`, then `ModelAdmin.save_formset`, the formset's `save`, for each formset (`django/contrib/admin/options.py:ModelAdmin.save_related`).
4. `ModelAdmin.construct_change_message` describes the change as a list that the log keeps as JSON, and `ModelAdmin.log_addition` or `ModelAdmin.log_change` writes it to the log ([The log and the history: `LogEntry` and `history_view`](log.md)).
5. `ModelAdmin.response_add` or `ModelAdmin.response_change` answers.

> **Trap.** An override of `save_model` must still save: the hook is for work around the save, says the documentation, not for a veto (`docs/ref/contrib/admin/index.txt`).

```text figure=the-save
nora's "POST" to /admin/fleet/ship/1/change/: tonnage 368, "_save"

the code                                 the SQL it sent
AdminSite.admin_view: has_permission     the session's row; the user
ModelAdmin.changeform_view               BEGIN
  _changeform_view
    get_object                           the ship, pk 1
    has_view_or_change_permission        the user's permissions; the groups' permissions
    get_fieldsets, get_form
    has_change_permission
    the form bound; no formsets
    is_valid                             the port, pk 1, for the form field
                                         that the port exists, for the foreign key
                                         SAVEPOINT; the check constraint; RELEASE SAVEPOINT
                                         another Endeavour at Valletta, for the unique constraint
    save_form
    save_model                           UPDATE "fleet_ship"
    save_related
    construct_change_message
    log_change                           INSERT INTO "django_admin_log"
    response_change: the message
      response_post_save_change: 302 to /admin/fleet/ship/
  the block ends                         COMMIT
```

*Nora's change of Endeavour's tonnage as a run recorded it: each step of the code, and the SQL it sent, if any. Everything from the ship's SELECT to the log's INSERT is one transaction.*

The session and the user were read before the transaction, when `AdminSite.has_permission` touched the request's user; the permissions once, then cached on the user. Validation checked the check constraint in a savepoint, since a transaction was open (`django/db/models/query_utils.py:Q.check`) ([Validating an instance](../instance/validation.md)). The log's content type was cached by the change page's `"GET"`; else `log_change` selects it first (`django/contrib/contenttypes/models.py:ContentTypeManager.get_for_model`).

When the form or a formset is not valid, nothing is saved and the form is shown again with its errors ([Validation: `full_clean`, `cleaned_data` and the errors](../forms/validation.md)). Nora's tonnage of 0 got a 200 with "Please correct the error below." and, above the fields, "Constraint “ship_has_tonnage” is violated."; the ship kept its tonnage, and the log got no row.

## A `"GET"`, and the page

A `"GET"` of an add page takes the form's initial values from `ModelAdmin.get_changeform_initial_data`: every parameter of the query string, a many-to-many field's value split at its commas (`django/contrib/admin/options.py:ModelAdmin.get_changeform_initial_data`). For piet, /admin/fleet/ship/add/?name=Argo&home=2&tonnage=12 opened a form with Argo, 12 and Piraeus filled in.

The page is built alike for a `"GET"` and a `"POST"` that failed. On a change page the user may not change, every field is read-only; otherwise `BaseModelAdmin.get_readonly_fields` says which are. The form is wrapped in an `AdminForm` for the templates. The title is "Add", "Change" or "View" and the model's verbose name, "Change ship", by whether there is an object and whether the user may change it; the context starts from `AdminSite.each_context`, with a caller's extra context laid over it. `ModelAdmin.render_change_form` adds the user's permissions and the options the buttons depend on, and returns a `TemplateResponse` of the template the model admin names, if any, or else of the first found of the model's, the application's and the admin's change form template ([The admin's templates and media](templates.md)) (`django/contrib/admin/options.py:ModelAdmin.render_change_form`).

## The answer: `response_add` and `response_change`

The answer goes by the name of the button the `"POST"` carries. A popup, marked with `"_popup"`, is answered first, with a page that hands the object's key and text to the opener ([The admin's widgets: related objects, raw ids and autocomplete](widgets.md)). Otherwise the response adds a success message linking the object's name to its change page, and redirects (`django/contrib/admin/options.py:ModelAdmin.response_add`, `django/contrib/admin/options.py:ModelAdmin.response_change`):

| the button | after an add | after a change |
|---|---|---|
| `"_continue"` | the new object's change page | the same page |
| `"_addanother"` | the add page again | the add page |
| `"_saveasnew"` | the new object's change page if `ModelAdmin.save_as_continue` and the user may change it, else as `"_save"` | never met: the request is an add |
| `"_save"`, or none | `ModelAdmin.response_post_save_add` | `ModelAdmin.response_post_save_change` |

*Where a save sends the user. After an add, the message links the object only for a user who may change it.*

Both of these go to the change list, with its preserved filters, for a user who may view or change the model, and to the index otherwise (`django/contrib/admin/options.py:ModelAdmin._response_post_save`).

```text
# a run: nora posts Endeavour's form, tonnage 369, with "_addanother", then follows the redirect
302 Found
Location: /admin/fleet/ship/add/
message (success): The ship “<a href="/admin/fleet/ship/1/change/">Endeavour</a>” was changed successfully. You may add another ship below.
GET /admin/fleet/ship/add/: 403 Forbidden
```

The buttons a page shows are decided by `submit_row`, which offered nora only "Save" and "Save and continue editing", as nora may not add ships (`django/contrib/admin/templatetags/admin_modify.py:submit_row`). The view does not ask again: a `"POST"` with `"_addanother"` is saved and sent to an add page its user cannot open.

## "Save as new": `save_as`

`ModelAdmin.save_as` puts a "Save as new" button on a change page, for a user who may add, in place of "Save and add another", and `ModelAdmin.save_on_top` repeats the buttons above the form (`django/contrib/admin/templatetags/admin_modify.py:submit_row`). The view only hands them to the template, and acts on `"_saveasnew"` in any `"POST"`, so what guards a copy is the add permission. With ShipAdmin's `save_as` false, piet's `"POST"` of Endeavour's form with `"_saveasnew"` and the name Resolution made ship 3, logged an addition and redirected to /admin/fleet/ship/3/change/; nora's got a 403.

A copy that fails validation is shown with the change page's template and without "Save" and "Save and continue editing", lest the interface get confusing, says the comment (`django/contrib/admin/options.py:ModelAdmin._changeform_view`); with `save_as` true that leaves "Save as new". Its title still says "Add ship".

## `message_user`

The change form sends its messages through `ModelAdmin.message_user`, which calls `add_message` ([Messages: `add_message`, `Message` and `MessageMiddleware`](../auth/messages.md)). The level may be a number or a level's name, `"warning"`; another name raises `ValueError` (`django/contrib/admin/options.py:ModelAdmin.message_user`). The default is `INFO`, which since 6.0 the admin styles apart from `SUCCESS`, the level the change form's success messages pass (`django/contrib/messages/constants.py`, `docs/releases/6.0.txt`).
