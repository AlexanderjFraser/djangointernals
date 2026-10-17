---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the admin

The changes to the admin from Django 5.0 to this commit: actions on the change form and `ModelAdmin.list_select_related` (6.1); `BaseModelAdmin.lookup_allowed`; `ModelAdmin.log_deletions`; the history page and "View on site" (6.2); facets, filters and smaller changes.

A project extends the admin by overriding the methods of `ModelAdmin` and `AdminSite`, and much of what changed is what those methods take, return and are called with. Two changes of 6.1 alter how the admin works: an action is an `Action` whose locations can offer it on a change form as well as on the change list; and a change list joins the foreign keys its columns name, not every non-null one, a gain, the notes say, for models with many foreign keys (`docs/releases/6.1.txt`). An override written for an older release now works and warns (`get_actions` on the change list, since 6.1), raises (`lookup_allowed` without the request, since 6.0), or is not called.

## Actions on the change form: `Action` and `ActionLocation`

Before 6.1 an action ran only from the change list, and `ModelAdmin.get_actions` mapped each name to a tuple of the function, the name and the description. Since 6.1 each value is an `Action`, which adds a plural description and the **locations**, members of `ActionLocation`: `ActionLocation.CHANGE_LIST`, the default, and `ActionLocation.CHANGE_FORM`, a change page's one object (`django/contrib/admin/options.py:Action`). The decorator `django.contrib.admin.action` takes `location=`, one location or a list, and `description_plural=`, the change list's text in place of `description=` (`django/contrib/admin/decorators.py:action`; [Actions: `response_action` and `delete_selected`](../admin/actions.md)).

The old shapes warn since 6.1, and work until Django 2028: an `Action` unpacked or indexed gives the tuple's members (`Action.__iter__`), and an override of `get_actions` or `ModelAdmin.get_action_choices` without `action_location=` is found by its signature and called without it on the change list (`django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location`). On a change form such a `get_actions` is not called, and no action is offered, not even one declared for both locations (`default_choices=[]` leaves out the blank choice):

```text recording=changes
old_admin.get_action_choices(request, default_choices=[], action_location=ActionLocation.CHANGE_FORM), get_actions(self, request) overridden: an archive action declared for both locations
    5.2.17       ImportError: cannot import name 'ActionLocation' from 'django.contrib.admin'
    6.0.8        ImportError: cannot import name 'ActionLocation' from 'django.contrib.admin'
    6.1.1        [], warns RemovedInDjango70Warning
    this commit  [], warns RemovedInDjango2028Warning
```

## What a change list joins: `list_select_related`

With `ModelAdmin.list_select_related` false, the default, a change list showing a foreign key used to call `select_related()` with no fields, which follows every foreign key that cannot be null (`django/db/models/query_utils.py:select_related_descend`): "all foreign key fields", the 6.1 notes say (`docs/releases/6.1.txt`). Since 6.1 only the keys that columns name are joined, as `ChangeList.get_select_related_fields`, which replaced has_related_field_in_list_display, collects them (`django/contrib/admin/views/main.py:ChangeList.get_select_related_fields`; [The change list: `changelist_view` and `ChangeList`](../admin/change-list.md)). In a model Note, the keys author and notebook cannot be null, and editor may be; the change list shows editor:

```text recording=changes
list_display = ("title", "editor"), editor the foreign key that may be null: the change list's joins
    5.2.17       INNER JOIN "journal_author" ON author_id, INNER JOIN "journal_notebook" ON notebook_id
    6.0.8        INNER JOIN "journal_author" ON author_id, INNER JOIN "journal_notebook" ON notebook_id
    6.1.1        LEFT OUTER JOIN "journal_author" ON editor_id
    this commit  LEFT OUTER JOIN "journal_author" ON editor_id
```

Before 6.1 the key the column named was the one left out. None of the four releases joins a key for a column passing through it, as "author__name" passes through author: unless something else joins it, each row's author is fetched by a query of its own, under the default fetch mode since 6.1, the choice of what such a read does (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__get__`; [Deferred fields and fetch modes in a queryset](../querysets/deferred.md)).

`list_select_related = True` still calls `select_related()` with no fields, a call 6.1 deprecates on any queryset, and is deprecated with it, to raise `ValueError` in Django 2028. A class that sets it warns as it is defined, asking for `False` or the fields to fetch (`django/contrib/admin/options.py:ModelAdmin.__init_subclass__`).

## `lookup_allowed` and the request

`BaseModelAdmin.lookup_allowed` decides whether a key of the query string may filter the change list. 5.0 gave it the request as a third argument, which `ChangeList.get_filters` passes by position (`django/contrib/admin/views/main.py:ChangeList.get_filters`); 5.0 deprecated overrides without it, and 6.0 dropped the fallback that called them with two. Only 5.2.17 still calls such an override so, here for a filter on title:

```text recording=changes
The change list for "?title=Monday", in a ModelAdmin whose lookup_allowed(self, lookup, value) takes no request: the entries listed
    5.2.17       ['Monday'], warns RemovedInDjango60Warning
    6.0.8        TypeError: EntryAdmin.lookup_allowed() takes 3 positional arguments but 4 were given
    6.1.1        TypeError: EntryAdmin.lookup_allowed() takes 3 positional arguments but 4 were given
    this commit  TypeError: EntryAdmin.lookup_allowed() takes 3 positional arguments but 4 were given
```

Without a filter in the query string the method is not called, so the error waits for the first filtered request.

## How a value is drawn: booleans and URLs

Since 6.1 a column of `ModelAdmin.list_display` that crosses a relation and ends at a boolean field, such as "author__active", is drawn as the boolean icon (`django/contrib/admin/templatetags/admin_list.py:items_for_result`). 5.2.17 and 6.0.8 drew the text True. A property has been drawn so since 5.0, when its getter has `"boolean"`. Since 5.2 a model's URL field is a link in a read-only field and in the change list outside a linked column, kept as text by a later security fix when `URLValidator` refuses it ([Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md)).

## Deleting and the log: `log_deletions`

Until 5.1 each deletion was logged by itself, through log_deletion of `ModelAdmin` and log_action of `LogEntryManager`, which 5.1 deprecated for `ModelAdmin.log_deletions` and `LogEntryManager.log_actions` and 6.0 removed. At this commit every log method of `ModelAdmin` writes through `log_actions`, which saves a single entry with `Model.save` and several with one `QuerySet.bulk_create` (`django/contrib/admin/models.py:LogEntryManager.log_actions`; [The log and the history: `LogEntry` and `history_view`](../admin/log.md)). So the entries `delete_selected` logs for several objects send no `post_save`, as the 5.1 notes say, while the delete page's single entry sends one, under all four releases. A model admin written for 5.0 overrides log_deletion alone, and its `log_deletions` is given two of the journal's Entry rows:

```text recording=changes
log_deletions(request, Entry.objects.all()), in a ModelAdmin that overrides log_deletion: the entries the override is called for
    5.2.17       ['Monday', 'Tuesday'], warns RemovedInDjango60Warning
    6.0.8        []
    6.1.1        []
    this commit  []
```

> **Trap.** Since 6.0 an override of log_deletion, or of a manager's log_action, is not called, and nothing warns; `log_actions` writes the entries without it (`django/contrib/admin/options.py:ModelAdmin.log_deletions`).

## The history page and "View on site"

`ModelAdmin.history_view` loads the object first, and since 6.2 refuses a user without the view or change permission, with `PermissionDenied`, a 403, before it answers that the object is missing (`django/contrib/admin/options.py:ModelAdmin.history_view`). For an entry that does not exist, the redirect to the index is the answer for a missing object:

```text recording=changes
GET /admin/journal/entry/999/history/ by a staff user without permissions: entry 999 does not exist
    5.2.17       302 to /admin/
    6.0.8        302 to /admin/
    6.1.1        302 to /admin/
    this commit  PermissionDenied
```

For entry 1, which exists, all four releases raise `PermissionDenied`: before 6.2 the answer told such a user whether the object existed.

"View on site" has been the site's own view since 6.2, `AdminSite.shortcut_view`, which raises `PermissionDenied` when the model is registered and its model admin's `BaseModelAdmin.has_view_permission` is false (`django/contrib/admin/sites.py:AdminSite.shortcut_view`; [The site's own pages: the index, the login and `AdminSite.each_context`](../admin/site-views.md)). Under 5.2.17, 6.0.8 and 6.1.1 the link sent a staff user with no permissions on to the object's own URL.

## The smaller changes

The rest, by name:

| what | at this commit | release | where |
|---|---|---|---|
| `AdminSite.get_model_admin`, `AdminSite.get_log_entries` | new: a model's model admin, or `NotRegistered`; the log's queryset | 5.0 | `django/contrib/admin/sites.py:AdminSite.get_model_admin` |
| `NotRegistered`, `AlreadyRegistered` | moved to `django.contrib.admin.exceptions`; the old import gives the same classes, silently | 5.0 | `django/contrib/admin/exceptions.py` |
| `AdminSite.password_change_form` | new: the password change's form | 6.0 | `django/contrib/admin/sites.py:AdminSite.password_change` |
| `AdminSite.login` | a user already let in goes to `"next"` if safe; under 6.0.8, to the index | 6.1 | `django/contrib/admin/sites.py:AdminSite.login` |
| `ModelAdmin.show_facets` | new: beside each filter's choices, how many rows each would leave, by default when the query string has `"_facets"` | 5.0 | `django/contrib/admin/views/main.py:ChangeList.__init__` |
| `AllValuesFieldListFilter`, `ChoicesFieldListFilter`, `RelatedFieldListFilter`, `RelatedOnlyFieldListFilter` | take several values, joined with OR | 5.0 | [The change list: `changelist_view` and `ChangeList`](../admin/change-list.md#building-the-queryset-changelistget_queryset) |
| `ModelAdmin.list_display` | a name may be a path across relations | 5.1 | [The change list's columns: `list_display` and `list_editable`](../admin/list-display.md) |
| `BaseModelAdmin.delete_confirmation_max_display` | new: caps the lists of objects on the delete pages | 6.1 | [Deleting: `delete_view` and `get_deleted_objects`](../admin/deleting.md) |
| the change form | a field's input below its label, its help text and then its errors between; a checkbox still beside its label; the class `"wide"` gone; `{% block object-tools %}` outside `{% block content %}` | 6.1 | `django/contrib/admin/templates/admin/includes/fieldset.html` |
| a fieldset of the class `"collapse"` | if named, a details element, closed until opened; an open fieldset while one of its fields has an error; collapse.js gone | 5.1 | `django/contrib/admin/helpers.py:Fieldset.is_collapsible` |
| `{% block extrabody %}` | new, before the end of the body | 5.2 | `django/contrib/admin/templates/admin/base.html` |
| `FilteredSelectMultiple` | its script keeps named groups of choices | 6.1 | `django/contrib/admin/static/admin/js/SelectBox.js` |
| admindocs | a model's page only for a user who may view or change it; a docstring's link may carry its own text | 5.2 | `django/contrib/admindocs/views.py:user_has_model_view_permission` |
| the undocumented | helpers.checkbox gone (5.0); `InclusionAdminNode.__init__` takes the tag's name first (6.1); django.contrib.admin.tests, which held AdminSeleniumTestCase, gone with django.test.selenium, its base (6.2; [What changed in the test framework](testing.md)) | 5.0 to 6.2 | `django/contrib/admin/templatetags/base.py:InclusionAdminNode.__init__` |
