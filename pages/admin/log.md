---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The log and the history: `LogEntry` and `history_view`

The admin's log is the table `"django_admin_log"`: a `LogEntry` for each addition, change and deletion that the admin's views record, written by `ModelAdmin.log_addition`, `ModelAdmin.log_change` and `ModelAdmin.log_deletions` through `LogEntryManager.log_actions`. `ModelAdmin.history_view` reads one object's rows back, and the index shows a user's latest.

The log has to name objects of every model in one table, go on naming an object after it is deleted, and describe a change in the reader's language rather than the writer's. Each of those shapes a column. Within Django, only the admin's views write it, through the three log methods; nora's run of home_at_valletta, a `QuerySet.update`, added no row.

## The row: `LogEntry`

| field | what it holds |
|---|---|
| `action_time` | when: `django.utils.timezone.now` by default, not editable |
| `user` | who: a foreign key to `AUTH_USER_MODEL` with `CASCADE`, so a deleted user's rows go too |
| `content_type` | the model, as a `ContentType`: nullable, with `SET_NULL` |
| `object_id` | the object's primary key, as text |
| `object_repr` | the object's text at the time, cut to 200 characters |
| `action_flag` | `ADDITION`, `CHANGE` or `DELETION`: 1, 2 or 3 |
| `change_message` | what changed: JSON written by the admin, or any string |

*The fields of `LogEntry`, ordered newest first (`django/contrib/admin/models.py:LogEntry`).*

One table holds the rows of every model, whose keys may be integers, strings or UUIDs; `object_id` is a `TextField`, "the textual representation" of the key in the documentation (`docs/ref/contrib/admin/index.txt`). `SET_NULL` keeps a row whose content type is deleted, and `object_repr` is all that names a deleted object. The migration `0002` replaced `action_time`'s `auto_now=True` with that default; `0003` gave `action_flag` its choices (`django/contrib/admin/migrations/`).

## Writing a row: `log_actions`

`LogEntryManager.log_actions` makes a `LogEntry` for each object it is given: the content type from `ContentTypeManager.get_for_model` with `for_concrete_model=False`, which files an object edited through a proxy model's admin under the proxy; the key; the text; and the message, dumped to JSON when it is a list. One entry is saved with `Model.save`, several together by `QuerySet.bulk_create` ([`bulk_create` and `bulk_update`](../querysets/bulk.md)) (`django/contrib/admin/models.py:LogEntryManager.log_actions`).

The three methods of `ModelAdmin` are the hooks: each calls `log_actions` with the request's user and its flag, and a project overrides them to log elsewhere or not at all (`django/contrib/admin/options.py:ModelAdmin.log_addition`). The change form calls `log_addition` or `log_change` after `ModelAdmin.save_related` ([The change form: `changeform_view`](change-form.md)); the change list calls `log_change` for each row `list_editable` saved ([The change list's columns: `list_display` and `list_editable`](list-display.md)); the delete view and `delete_selected` call `log_deletions` ([Deleting: `delete_view` and `get_deleted_objects`](deleting.md), [Actions: `response_action` and `delete_selected`](actions.md)).

`log_deletions` "must be called before the deletion", its docstring says. Called after it, `log_actions`, which iterates what it is given, would find a queryset empty once `ModelAdmin.delete_queryset` had run, and instances whose keys the collector had set to `None` (`django/db/models/deletion.py:Collector.delete`).

## The change message: `construct_change_message`

`ModelAdmin.construct_change_message` hands the form, the formsets and whether the object is new to `django.contrib.admin.utils.construct_change_message`, which returns a list: `{"added": {}}` for an addition, or else `{"changed": {"fields": [...]}}` with the labels of the fields that changed, if any; then an `"added"`, `"changed"` or `"deleted"` entry for each object a formset added, changed or deleted, with the model's verbose name and the object's text (`django/contrib/admin/utils.py:construct_change_message`).

Those strings are taken with translation off, inside `django.utils.translation.override` with `None` ([The active language](../i18n/active-language.md)): the docstring says they are stored untranslated and translated when the row is read, and the documentation that this lets `LogEntry.get_change_message` speak the reader's language. For a change, `BaseForm.changed_data` is read first, while the user's language is active; the comment's reason is that a field affected by localization, a date written MM/DD/YYYY in one language and DD/MM/YYYY in another, could otherwise be counted as changed.

Four requests: nora changed Endeavour's tonnage; piet added the port Genoa with a ship, Resolution, in its inline; piet deleted Beagle; and piet, with French active, changed nora's first name and email address. Each row, its message, and its `LogEntry.__str__`:

```text
# the rows of "django_admin_log"
1  nora, ship "1", "Endeavour", action_flag 2
   [{"changed": {"fields": ["Tonnage"]}}]
   Changed “Endeavour” — Changed Tonnage.
2  piet, port "3", "Genoa", action_flag 1
   [{"added": {}}, {"added": {"name": "ship", "object": "Resolution"}}]
   Added “Genoa”.
3  piet, ship "2", "Beagle", action_flag 3
   (an empty string)
   Deleted “Beagle.”
4  piet, user "2", "nora", action_flag 2
   [{"changed": {"fields": ["First name", "Email address"]}}]
   Changed “nora” — Changed First name and Email address.
```

## Reading it back: `get_change_message`

`LogEntry.get_change_message` turns a message that begins with `"["` and parses as JSON into sentences in the language active as it reads: each sentence's pattern, model name and label goes through `django.utils.translation.gettext`, and an empty list reads "No fields changed.". Anything else, a deletion's empty string or a sentence a project wrote, is returned as it is (`django/contrib/admin/models.py:LogEntry.get_change_message`). `__str__` names the object, with the message for a change, by the flag that `LogEntry.is_addition`, `is_change` and `is_deletion` test. Rows 1 and 4 with French active:

```text
# rows 1 and 4, read inside translation.override("fr")
Modification de « Endeavour » — Modification de Tonnage.
Modification de « nora » — Modification de First name et Adresse électronique.
```

> **Trap.** A label is looked up as stored, capital and all. The French catalogues have "Email address", and "first name" but not "First name"; harbour has no catalogue, so "Tonnage" stays.

`LogEntry.get_edited_object` fetches the object through its content type. `LogEntry.get_admin_url` reverses `"admin:fleet_ship_change"`, or its like, with the key quoted, and gives `None` without a content type, a key or such a URL; it does not ask whether the object exists, and gave /admin/fleet/ship/2/change/ for Beagle's deletion (`django/contrib/admin/models.py:LogEntry.get_admin_url`).

## The history page: `history_view`

`ModelAdmin.history_view` loads the object with `ModelAdmin.get_object`, asks `BaseModelAdmin.has_view_or_change_permission`, and raises `PermissionDenied` before it looks whether there was an object; only then is a missing object sent to the index with a warning (`django/contrib/admin/options.py:ModelAdmin.history_view`). nora got 403 for voyage 99's history, and a redirect for ship 99's.

> **Changed in 6.2.** The history view answers 403 to staff without the view or change permission whether the object exists or not (`docs/releases/6.2.txt`).

The rows are the model's content type's, from `get_content_type_for_model`, with the key from the URL unquoted, `"user"` and `"content_type"` joined in, oldest first, 100 to a page from `ModelAdmin.get_paginator`. The template, `"admin/object_history.html"` by default, shows each row's time, user and change message, or with no rows that the object "probably wasn’t added via this admin site".

```text
# GET /admin/fleet/ship/1/history/ as nora: "Change history: Endeavour"
Oct. 16, 2026, 12:46 p.m.   nora (Nora)   Changed Tonnage.
1 entry
```

## Recent actions on the index

`AdminSite.each_context` gives every page `"log_entries"`, the queryset of `AdminSite.get_log_entries`: every row, its content type and user joined, not yet evaluated (`django/contrib/admin/sites.py:AdminSite.get_log_entries`). Of the admin's templates only the index evaluates it, with `{% get_admin_log 10 as admin_log for_user user %}`, whose node keeps one user's rows and takes the newest ten (`django/contrib/admin/templatetags/log.py:AdminLogNode.render`); nora's change list sent no query of the log. Each entry links to `LogEntry.get_admin_url` unless it is a deletion or has none, under its content type's name or "Unknown content" (`django/contrib/admin/templates/admin/index.html`). piet's listed the change of nora, Beagle's deletion without a link, and Genoa's addition.
