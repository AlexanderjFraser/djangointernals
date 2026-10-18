---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the admin

An admin override written for an older release may now work and warn, raise, or not be called. Actions on the change form; a change list's joins; `BaseModelAdmin.lookup_allowed`; the deletion log; the permission checks of the history page and "View on site".

A project extends the admin by overriding the methods of `ModelAdmin` and `AdminSite`. Much of what changed is what those methods take, return and are called with.

## Actions on the change form: `Action` and `ActionLocation`

Since 6.1 an action can run from a change form as well as from the change list. `ModelAdmin.get_actions` maps each name to an `Action`, no longer a tuple of the function, the name and the description. An `Action` adds a plural description and the **locations**, members of `ActionLocation`: `ActionLocation.CHANGE_LIST`, the default, and `ActionLocation.CHANGE_FORM` (`django/contrib/admin/options.py:Action`). The decorator `django.contrib.admin.action` sets them with `location=` and `description_plural=` (`django/contrib/admin/decorators.py:action`; [Actions: `response_action` and `delete_selected`](../admin/actions.md)).

The old shapes warn since 6.1, and work until Django 2028. An `Action` unpacked or indexed gives the tuple's members. 6.1 gave `get_actions` and `ModelAdmin.get_action_choices` the argument `action_location=`, the location whose actions are wanted. An override of `get_actions` without it is found by its signature, and called without it on the change list (`django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location`). On a change form it is not called, and no action is offered.

In the lines of 6.1.1 and this commit, the two with `ActionLocation`, an archive action is declared for both locations, by a list given to `location=`. Look for what the change form offers, and the warning:

```text recording=changes
old_admin.get_action_choices(request, default_choices=[], action_location=ActionLocation.CHANGE_FORM), get_actions(self, request) overridden: an archive action declared for both locations
    6.1.1        [], warns RemovedInDjango70Warning
    this commit  [], warns RemovedInDjango2028Warning
```

The list is empty: the archive action is not offered. `default_choices=[]` only leaves out the blank choice that would open the list.

## What a change list joins: `list_select_related`

Since 6.1, with `ModelAdmin.list_select_related` false, the default, a change list joins only the foreign keys that are columns, which `ChangeList.get_select_related_fields` collects (`django/contrib/admin/views/main.py:ChangeList.get_select_related_fields`; [The change list: `changelist_view` and `ChangeList`](../admin/change-list.md)). A change list showing a foreign key used to call `select_related()` with no fields, which follows every foreign key that cannot be null (`django/db/models/query_utils.py:select_related_descend`).

A model Note has the keys author and notebook, which cannot be null, and editor, a second key to Author, which may be; its change list shows editor. The old lines join the two keys no column names, and leave out editor:

```text recording=changes
list_display = ("title", "editor"), editor the foreign key that may be null: the change list's joins
    5.2.17       INNER JOIN "journal_author" ON author_id, INNER JOIN "journal_notebook" ON notebook_id
    6.0.8        INNER JOIN "journal_author" ON author_id, INNER JOIN "journal_notebook" ON notebook_id
    6.1.1        LEFT OUTER JOIN "journal_author" ON editor_id
    this commit  LEFT OUTER JOIN "journal_author" ON editor_id
```

`list_select_related = True` still calls `select_related()` with no fields, a call 6.1 deprecated on any queryset, and the value `True` is deprecated with it. A class that sets `True` warns as it is defined, asking for `False` or the fields to fetch; in Django 2028 it is to raise `ValueError` instead (`django/contrib/admin/options.py:ModelAdmin.__init_subclass__`).

## `lookup_allowed` and the request

Since 6.0 an override of `BaseModelAdmin.lookup_allowed` that takes no request raises `TypeError`. The method decides whether a key of the query string may filter the change list. 5.0 gave it the request as a third argument, which `ChangeList.get_filters` passes by position, and deprecated overrides without it (`django/contrib/admin/views/main.py:ChangeList.get_filters`). 6.0 dropped the fallback that called them with two arguments. For a filter on title, 5.2.17's line is that fallback still at work:

```text recording=changes
The change list for "?title=Monday", in a ModelAdmin whose lookup_allowed(self, lookup, value) takes no request: the entries listed
    5.2.17       ['Monday'], warns RemovedInDjango60Warning
    6.0.8        TypeError: EntryAdmin.lookup_allowed() takes 3 positional arguments but 4 were given
    6.1.1        TypeError: EntryAdmin.lookup_allowed() takes 3 positional arguments but 4 were given
    this commit  TypeError: EntryAdmin.lookup_allowed() takes 3 positional arguments but 4 were given
```

> **Trap.** Without a filter in the query string an old `lookup_allowed` is not called, so its `TypeError` waits for the first filtered request.

## Deleting and the log: `log_deletions`

Since 5.1 the admin logs deletions through `ModelAdmin.log_deletions` and `LogEntryManager.log_actions`. Until then each deletion was logged by itself, through log_deletion of `ModelAdmin` and log_action of `LogEntryManager`, which 5.1 deprecated and 6.0 removed. `log_actions` saves several entries with one `QuerySet.bulk_create`, so the entries that `delete_selected` logs for several objects send no `post_save`, as the 5.1 notes say. The delete page's single entry is saved with `Model.save`, and sends one (`django/contrib/admin/models.py:LogEntryManager.log_actions`; [The log and the history: `LogEntry` and `history_view`](../admin/log.md)).

> **Trap.** Since 6.0 an override of log_deletion, or of a manager's log_action, is not called, and nothing warns; `log_actions` writes the entries without it (`django/contrib/admin/options.py:ModelAdmin.log_deletions`). Under 5.2.17 such an override is still called, with a warning.

## The history page and "View on site"

Before 6.2 the history page told a user without the view or change permission whether an object existed. For an object that exists, 5.2.17 to this commit all raise `PermissionDenied`, a 403. For one that does not, 5.2.17, 6.0.8 and 6.1.1 sent such a user to the index, the answer for a missing object. Since 6.2 `ModelAdmin.history_view` raises `PermissionDenied` for such a user before it answers that the object is missing (`django/contrib/admin/options.py:ModelAdmin.history_view`).

Since 6.2 "View on site" is the site's own view, `AdminSite.shortcut_view`. It raises `PermissionDenied` when the model is registered and its model admin's `BaseModelAdmin.has_view_permission` is false (`django/contrib/admin/sites.py:AdminSite.shortcut_view`; [The site's own pages: the index, the login and `AdminSite.each_context`](../admin/site-views.md)). Under 5.2.17, 6.0.8 and 6.1.1 the link was the contenttypes app's view `shortcut`, which sent a staff user with no permissions on to the object's own URL.

## The smaller changes

The rest, by name:

| what | change | where |
|---|---|---|
| `AdminSite.get_model_admin` | New in 5.0: a model's model admin, or `NotRegistered` | `django/contrib/admin/sites.py:AdminSite.get_model_admin` |
| `AdminSite.get_log_entries` | New in 5.0: the queryset of the log entries the site lists | `django/contrib/admin/sites.py:AdminSite.get_log_entries` |
| `NotRegistered`, `AlreadyRegistered` | Since 5.0, moved to `django.contrib.admin.exceptions`; the old import still works, unwarned | `django/contrib/admin/exceptions.py` |
| `AdminSite.password_change_form` | New in 6.0: the password change's form | `django/contrib/admin/sites.py:AdminSite.password_change` |
| `AdminSite.login` | Since 6.1, a user already let in goes to `"next"` if it is safe; under 6.0.8, to the index | `django/contrib/admin/sites.py:AdminSite.login` |
| `ModelAdmin.show_facets` | New in 5.0: beside each filter's choices, how many rows each would leave; by default only with `"_facets"` in the query string | `django/contrib/admin/views/main.py:ChangeList.__init__` |
| a list filter of values, choices or relations | Since 5.0, takes several values, joined with OR: `AllValuesFieldListFilter`, `ChoicesFieldListFilter`, `RelatedFieldListFilter` and `RelatedOnlyFieldListFilter` | `django/contrib/admin/utils.py:build_q_object_from_lookup_parameters` |
| `ModelAdmin.list_display` | Since 5.1, a name may be a path across relations | [The change list's columns: `list_display` and `list_editable`](../admin/list-display.md) |
| a boolean field at a path's end | Since 6.1, drawn as the boolean icon, not the text True, as for "author__active" | `django/contrib/admin/templatetags/admin_list.py:items_for_result` |
| a property in a column | Since 5.0, drawn as the boolean icon when its getter is marked boolean, as by `display(boolean=True)` | `django/contrib/admin/templatetags/admin_list.py:items_for_result` |
| a model's URL field | Since 5.2, a link in a read-only field, and in the change list unless its column is the link to the change form; text when `URLValidator` refuses the value, since 5.2.17 and 6.0.8 fixed CVE-2026-15920 | `django/contrib/admin/utils.py:display_for_field` |
| `BaseModelAdmin.delete_confirmation_max_display` | New in 6.1: caps the lists of objects on the delete pages | [Deleting: `delete_view` and `get_deleted_objects`](../admin/deleting.md) |
| a change form's field | Since 6.1, its label, help text, errors and input stand one below the other, in that order; a checkbox stays beside its label; the class `"wide"` is gone | `django/contrib/admin/templates/admin/includes/fieldset.html` |
| `{% block object-tools %}` | Since 6.1, outside `{% block content %}`, in the change form and the change list | `django/contrib/admin/templates/admin/base.html` |
| a fieldset of the class `"collapse"` | Since 5.1, one with a name, shown as its heading, is a details element, closed until opened, unless one of its fields has an error; collapse.js is gone | `django/contrib/admin/helpers.py:Fieldset.is_collapsible` |
| `{% block extrabody %}` | New in 5.2: before the end of the body | `django/contrib/admin/templates/admin/base.html` |
| admindocs | Since 5.2, a model's page only for a user who may view or change the model; a docstring's link may carry its own text | `django/contrib/admindocs/` |
| `InclusionAdminNode.__init__` | Since 6.1, takes the tag's name first | `django/contrib/admin/templatetags/base.py:InclusionAdminNode.__init__` |
| AdminSeleniumTestCase | Gone in 6.2 outright, with django.contrib.admin.tests, which held it; under 6.1.1 nothing warns | `docs/releases/6.2.txt` |
