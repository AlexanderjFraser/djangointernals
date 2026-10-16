---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Deleting: `delete_view` and `get_deleted_objects`

`ModelAdmin.delete_view` serves an object's delete page. Asked with `"GET"`, it shows every row that deleting the object would take with it, found by `ModelAdmin.get_deleted_objects` with `NestedObjects`, a collector that deletes nothing; posted to, it logs the deletion, deletes, and answers.

A delete takes with it the rows that point at its row, or is refused by them, as their relations' `on_delete` says ([Deleting: the `Collector`](../models/deleting.md)). The admin shows the user that reach first, and stops at a row that `PROTECT` or `RESTRICT` guards, or at a row of a registered model the user may not delete. Both are found by running a delete's collection, made to fetch every row, without the delete.

## The view

`ModelAdmin.delete_view` is under `csrf_protect`, and runs a request whose method is not safe inside `atomic` on the database the router gives for writing the model, so a confirmed delete's collection, log and delete run in one transaction (`django/contrib/admin/options.py:ModelAdmin.delete_view`). `ModelAdmin._delete_view` does the work, in this order (`django/contrib/admin/options.py:ModelAdmin._delete_view`):

1. A `"_to_field"` is put to `BaseModelAdmin.to_field_allowed`, and a refusal raises `DisallowedModelAdminToField`, a 400 ([The change list: `changelist_view` and `ChangeList`](change-list.md)).
2. `ModelAdmin.get_object` loads the object, or gives `None`.
3. `BaseModelAdmin.has_delete_permission` is asked, with the object, and a refusal raises `PermissionDenied`. A user without the permission gets the same 403 for a key that exists and for one that does not.
4. With no object, the user is sent to the index with a warning.
5. `get_deleted_objects` collects what the delete would reach.
6. A `"POST"` carrying any form data, when nothing is protected, is the confirmation: a lacking permission raises `PermissionDenied`, and otherwise the object is logged, deleted, and answered by `ModelAdmin.response_delete`.
7. Anything else gets the confirmation page.

The view never reads `"post"`, the field its form sends: with the CSRF check enforced, a `"POST"` of the token alone deleted, and one with no form data, its token in a header, got the page again.

| request | response |
|---|---|
| nora, `"GET"` /admin/fleet/ship/2/delete/ | 403 |
| nora, `"GET"` /admin/fleet/ship/99/delete/ | 403 |
| piet, `"GET"` /admin/fleet/ship/99/delete/ | 302 to /admin/, warning "ship with ID “99” doesn’t exist. Perhaps it was deleted?" |
| piet, `"GET"` /admin/fleet/port/1/delete/ | 200, "Cannot delete port" |
| piet, `"POST"` /admin/fleet/port/1/delete/ | 200, the same page, nothing deleted |

*Delete pages as nora, who may not delete ships, and piet, a superuser ([The admin](../admin.md)).*

## `get_deleted_objects`

`ModelAdmin.get_deleted_objects` is a hook that the delete view and the `delete_selected` action both call ([Actions: `response_action` and `delete_selected`](actions.md)). Its default calls the function of that name in `django.contrib.admin.utils`, which collects the objects with a `NestedObjects` on the database the router gives for writing them, and returns four values: the tree of what would be deleted, as nested lists of strings; the number of each model's objects, under its plural verbose name; the verbose names of the models the user may not delete; and the protected objects, as strings (`django/contrib/admin/utils.py:get_deleted_objects`).

A function defined inside it makes each string, the model's verbose name and the object's text. For an object of a model registered with the site, it asks that model's model admin `has_delete_permission` with the object, records the model's verbose name when refused, and links the object's text to its change page if that reverses in the site's namespace. Any other object's string has no link. So only rows of registered models need a permission: Endeavour's ports of call, rows of the model Django made for `"calls"`, go with the ship whoever deletes it.

## `NestedObjects`

`NestedObjects` is a `Collector` made with `force_collection=True` (`django/contrib/admin/utils.py:NestedObjects`). A forced collector marks nothing for a fast delete, so it fetches every row the delete would take, and it follows a relation with `DB_CASCADE`, whose rows the real delete leaves to the database, so the page names those too ([Deleting: the `Collector`](../models/deleting.md)).

`NestedObjects.collect` records an edge to each row it is handed from the object the row was reached from, read off the row through the field that reached it. The rows given at the start are roots, and so are rows reached without such a field: a generic relation's, or a parent's reached by a link with no related name or one ending in `"+"`. Then it calls `Collector.collect`, and catches `ProtectedError` and `RestrictedError` into its set of protected objects (`django/contrib/admin/utils.py:NestedObjects.collect`). A cascade's nested call is this method too, so a `ProtectedError`, raised by the call whose rows a protected relation points at, ends only that call, and the collection goes on; a `RestrictedError` comes only from the outermost call, once everything is collected (`django/db/models/deletion.py:CASCADE`, `django/db/models/deletion.py:Collector.collect`).

`NestedObjects.related_objects` adds `QuerySet.select_related` of the field, so each row arrives, whole, with the object the edge is read from (`django/contrib/admin/utils.py:NestedObjects.related_objects`). `NestedObjects.nested` walks the edges from the roots, depth first, and gives each object once, followed by a list of its children if it has any (`django/contrib/admin/utils.py:NestedObjects.nested`). A row that `SET_NULL` would update is not collected, and is not in the tree.

For Endeavour the collection sent four statements, for voyages, ports of call, manifests and sailors, each joining in the row it came from. piet's page summed it up as "Ships: 1", "Voyages: 2" and "Voyage-port relationships: 2", above this tree:

```text
<ul id="deleted-objects">	<li>Ship: <a href="/admin/fleet/ship/1/change/">Endeavour</a>
	<ul>
		<li>Voyage: <a href="/admin/fleet/voyage/1/change/">Voyage object (1)</a>
		<ul>
			<li>Voyage-port relationship: Voyage_calls object (1)</li>
		</ul>
		</li>
		<li>Voyage: <a href="/admin/fleet/voyage/2/change/">Voyage object (2)</a>
		<ul>
			<li>Voyage-port relationship: Voyage_calls object (2)</li>
		</ul>
		</li>
	</ul>
	</li></ul>
```

## The confirmation page

`ModelAdmin.render_delete_form` renders `"admin/delete_confirmation.html"`, unless the model or its application has its own, or `ModelAdmin.delete_confirmation_template` names one ([The admin's templates and media](templates.md)) (`django/contrib/admin/options.py:ModelAdmin.render_delete_form`). Its title is "Delete", or "Cannot delete ship" when a permission is lacking or a row is protected. The template shows the models the user may not delete; failing those, the protected objects; failing those, the summary, the tree and a form that posts `"post"` (`django/contrib/admin/templates/admin/delete_confirmation.html`). Valletta's page listed only Endeavour and Beagle, which `"home"` protects. Given `"fleet.delete_ship"`, nora got "Cannot delete ship" for Endeavour, listing "voyage", and a `"POST"` got 403.

The lists are drawn by `truncated_unordered_list`, given `BaseModelAdmin.delete_confirmation_max_display` (`django/contrib/admin/templatetags/admin_filters.py:truncated_unordered_list`). It counts the items in the order it draws them, each before its children, leaves out those past the limit, and ends with their count: with 2 on ShipAdmin, Endeavour's tree showed the ship and its first voyage, then "…and 3 more objects.". `None`, the default, draws every item; 0 draws none. The documentation calls it purely a display setting, which does not change what is fetched (`docs/ref/contrib/admin/index.txt`).

> **Changed in 6.1.** `delete_confirmation_max_display` is new; it limits the page of `delete_selected` too, and an inline's refusal to delete a protected row, where 0, like `None`, sets no limit ([Inlines: `InlineModelAdmin` and its formsets](inlines.md)).

## The delete and the answer

On the confirmation, `_delete_view` takes the object's text and its key, or the value of the `"_to_field"` field, before the delete, which leaves the instance's key `None`. Then `ModelAdmin.log_deletions` writes the log's row, first, as its docstring requires ([The log and the history: `LogEntry` and `history_view`](log.md)), and `ModelAdmin.delete_model` calls `Model.delete`, which collects again with an ordinary collector; `ModelAdmin.delete_queryset` is its counterpart for `delete_selected` (`django/contrib/admin/options.py:ModelAdmin.delete_model`). The documentation warns that an override of `delete_model` must still delete: it is not for a veto (`docs/ref/contrib/admin/index.txt`).

piet's `"POST"` for Endeavour sent, after `"BEGIN"`, the ship, the admin's four statements, the content type and the log's `"INSERT"`, then:

```text
SELECT "fleet_voyage"."id" FROM "fleet_voyage" WHERE "fleet_voyage"."ship_id" IN (1)
SELECT "crew_sailor"."id" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (1)
DELETE FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" IN (1, 2)
DELETE FROM "office_manifest" WHERE "office_manifest"."voyage_id" IN (1, 2)
DELETE FROM "fleet_voyage" WHERE "fleet_voyage"."id" IN (2, 1)
DELETE FROM "fleet_ship" WHERE "fleet_ship"."id" IN (1)
COMMIT
```

The reach was found twice: as whole rows by the admin's collector, and as keys by the model's, which deleted the ports of call and manifests unfetched.

`ModelAdmin.response_delete` answers a delete made in a popup with `"admin/popup_response.html"`, carrying `{"action": "delete", "value": "2"}` for Piraeus, to the page that opened it ([The admin's widgets: related objects, raw ids and autocomplete](widgets.md)). Otherwise it adds "The ship “Endeavour” was deleted successfully." at `SUCCESS`, and redirects to the change list, keeping the preserved filters, if the user may change the model's objects, and to the index if not (`django/contrib/admin/options.py:ModelAdmin.response_delete`). nora, allowed to view and delete voyages but not to change them, was sent to /admin/.
