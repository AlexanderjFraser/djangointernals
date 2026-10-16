---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the admin

The changes to the admin from Django 5.0 to this commit: actions on a change form and the `Action` objects of `ModelAdmin.get_actions` (6.1); the change list's facets, its columns across relations and its joins under `ModelAdmin.list_select_related`; `ModelAdmin.log_deletions` in place of the single log methods; and the site's new hooks and stricter answers.

A project extends the admin by overriding the methods of `ModelAdmin` and `AdminSite`, and several of the changes are to what those methods take and return. An override written for an older release now warns (the action hooks, `list_select_related`), raises `TypeError` (`BaseModelAdmin.lookup_allowed` without the request), or is never called (the method log_deletion).

## Actions: `Action` and `ActionLocation`

Until 6.1 an action ran only from a change list, and `ModelAdmin.get_actions` mapped each name to a tuple of the function, the name and the description. Since 6.1 an action has **locations**, members of `ActionLocation`: `ActionLocation.CHANGE_LIST`, the default, and `ActionLocation.CHANGE_FORM`, where it runs on a change page's object ([Actions: `response_action` and `delete_selected`](../admin/actions.md)). The decorator `django.contrib.admin.action` stores its `location=`, one or a list, as the function's `"locations"`; `description_plural=` is the change list's text, `description=` the change form's, and both when no plural is given (`django/contrib/admin/decorators.py:action`). `get_actions`, `ModelAdmin.get_action`, `ModelAdmin.get_action_choices` and `ModelAdmin.response_action` take `action_location=`, and each value of `get_actions` is an `Action`, a dataclass of the function, the name, both descriptions and the locations (`django/contrib/admin/options.py:Action`).

The old shapes still work until Django 2028, and warn with `RemovedInDjango2028Warning` ([What still warns: the deprecations and the releases that end them](deprecations.md)). An `Action` unpacked or indexed gives the tuple's members (`Action.__iter__`, `Action.__getitem__`). An override of `get_actions` or `get_action_choices` without `action_location=` is found by inspecting its signature at each call, warned of through `warn_about_implementation` with the file and line that define it, and called without the argument; such a `get_actions` gives a change form no actions (`django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location`). Tuples that an override returns are read by index, and nothing warns of them.

```text
# a run at this commit, as piet, blank choices left out; home_at_valletta has both locations, a description
# and a plural one, and old_admin's get_actions(self, request) takes no action_location
ship_admin.get_action_choices(request)
    ('delete_selected', 'Delete selected ships')
    ('home_at_valletta', 'Home the selected ships at Valletta')
ship_admin.get_action_choices(request, action_location=ActionLocation.CHANGE_FORM)
    ('home_at_valletta', 'Home ship at Valletta')
old_admin.get_action_choices(request, action_location=ActionLocation.CHANGE_FORM)
    RemovedInDjango2028Warning: Overriding get_actions() without the 'action_location' parameter is deprecated. Update the signature to get_actions(self, request, action_location=ActionLocation.CHANGE_LIST).
```

## The change list

`ModelAdmin.show_facets` (5.0) gives each filter's choices the count of rows each would leave: under `ShowFacets.ALLOW`, the default, when the query string has `"_facets"`; always under `ShowFacets.ALWAYS`; never under `ShowFacets.NEVER` (`django/contrib/admin/views/main.py:ChangeList.__init__`; [Filters and search: `list_filter`, `search_fields` and `date_hierarchy`](../admin/filters.md)). Since 5.0 `AllValuesFieldListFilter`, `ChoicesFieldListFilter`, `RelatedFieldListFilter` and `RelatedOnlyFieldListFilter` take several values of their parameter and mark each as selected (`django/contrib/admin/filters.py:RelatedFieldListFilter.choices`); the change list keeps every value of a key and joins them with OR (`django/contrib/admin/utils.py:build_q_object_from_lookup_parameters`).

`BaseModelAdmin.lookup_allowed` has taken the request as its third argument since 5.0, and `ChangeList.get_filters` passes it by position (`django/contrib/admin/views/main.py:ChangeList.get_filters`). 5.0 deprecated overrides without it and 6.0 dropped them, so one that takes only the lookup and the value fails on the first lookup in a query string: in a run, `"?tonnage=366"` raised `TypeError`, "OldLookupAdmin.lookup_allowed() takes 3 positional arguments but 4 were given".

### Columns across relations

Since 5.1 a name of `ModelAdmin.list_display` may be a path across relations, "home__name", which `lookup_field` walks (`django/contrib/admin/utils.py:lookup_field`). Since 6.1 a path ending at a boolean field draws the boolean icon; since 5.0 a property draws it when its getter has `"boolean"` (`django/contrib/admin/templatetags/admin_list.py:items_for_result`). Since 5.2 a model's URL field is a link in read-only fields and in the list, unless its column is the row's link to the change form (`django/contrib/admin/utils.py:display_for_field`); a later security release keeps a value `URLValidator` refuses as text ([Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md); [The change list's columns: `list_display` and `list_editable`](../admin/list-display.md)).

### The joins: `list_select_related`

With `ModelAdmin.list_select_related` false, the default, a change list showing a foreign key used to fetch, in the release notes' words, all foreign key fields (`docs/releases/6.1.txt`). Since 6.1 `ChangeList.apply_select_related` joins only what `ChangeList.get_select_related_fields`, which replaced has_related_field_in_list_display, finds: each column that names a foreign key or one-to-one field by its own name (`django/contrib/admin/views/main.py:ChangeList.get_select_related_fields`). In a run, "home" and "captain" were joined and "home_id" joined nothing; with "home__name" the change list joined nothing and fetched each row's port with a query of its own.

`True` is deprecated in 6.1, to raise `ValueError` in Django 2028: `ModelAdmin.__init_subclass__` warns as a class that sets it is defined, and `ModelAdmin.get_changelist_instance` when `ModelAdmin.get_list_select_related` returns it though the attribute is not `True` (`django/contrib/admin/options.py:ModelAdmin.get_changelist_instance`).

## Deleting and the log

Until 5.1 a deletion was logged an object at a time, with the methods log_deletion of `ModelAdmin` and log_action of `LogEntryManager`; 5.1 deprecated both for the plural `ModelAdmin.log_deletions` and `LogEntryManager.log_actions`, and 6.0 removed them. At this commit `ModelAdmin.log_addition`, `ModelAdmin.log_change` and `log_deletions` all write through `log_actions`, which saves one entry with `Model.save` and several with one `QuerySet.bulk_create` (`django/contrib/admin/models.py:LogEntryManager.log_actions`). So `delete_selected` logs several objects through `bulk_create`, which sends no `pre_save` or `post_save`: in a run of `log_deletions`, a receiver of `post_save` for `LogEntry` heard Endeavour's row alone, and neither row of two ships ([The log and the history: `LogEntry` and `history_view`](../admin/log.md)).

> **Trap.** An override of log_deletion, or a manager's log_action, is not called at this commit, and nothing warns: the admin calls only the plural names (`django/contrib/admin/actions.py:delete_selected`, `django/contrib/admin/options.py:ModelAdmin._delete_view`).

`BaseModelAdmin.delete_confirmation_max_display` (6.1) limits the lists of objects on the delete page, on `delete_selected`'s and in an inline's refusal to delete protected rows, giving the rest as a count; `None`, the default, sets no limit (`django/contrib/admin/templatetags/admin_filters.py:truncated_unordered_list`, `django/contrib/admin/options.py:InlineModelAdmin.get_formset`; [Deleting: `delete_view` and `get_deleted_objects`](../admin/deleting.md)).

## The site's hooks and answers

`AdminSite.get_model_admin` (5.0) returns a model's model admin or raises `NotRegistered`, which, with `AlreadyRegistered`, is defined in `django/contrib/admin/exceptions.py` since 5.0; `django.contrib.admin.sites` imports both, so the old import gives the same classes (`django/contrib/admin/sites.py:AdminSite.get_model_admin`). `AdminSite.get_log_entries` (5.0) makes the log's queryset that every page's context carries. `AdminSite.password_change_form` (6.0) names the password change's form, the admin's own when it is `None` (`django/contrib/admin/sites.py:AdminSite.password_change`).

Since 6.1 `AdminSite.login` sends a user already let in to the request's `"next"`, when it is safe, and no longer always to the index (`django/contrib/admin/sites.py:AdminSite.login`). In 6.2 two views began to ask the permission before they answer an object's absence, so a user without it gets 403 whether the object exists or not: `ModelAdmin.history_view`, which, the release notes say, checked the existence first, and `AdminSite.shortcut_view`, behind "View on site", which asks the registered model's `BaseModelAdmin.has_view_permission` (`django/contrib/admin/options.py:ModelAdmin.history_view`, `django/contrib/admin/sites.py:AdminSite.shortcut_view`; [Permissions in the admin: `has_change_permission` and the others](../admin/admin-permissions.md)).

## Templates, the change form's layout and the internals

Since 6.1 the change form puts each field below its label, the help text and then the errors between the two; a checkbox keeps the old layout (`django/contrib/admin/templates/admin/includes/fieldset.html`). The class wide, which the new layout made obsolete, is gone, and the change form's `{% block object-tools %}` stands outside its `{% block content %}` (`django/contrib/admin/templates/admin/change_form.html`). Since 5.1 a named fieldset with the class `"collapse"` is drawn in an HTML details element, unless one of its fields has an error, and collapse.js is gone (`django/contrib/admin/helpers.py:Fieldset.is_collapsible`); since 5.2 `"admin/base.html"` has `{% block extrabody %}` before the end of the body; since 6.1 the two-box select, `FilteredSelectMultiple`, keeps named groups of choices ([The admin's widgets: related objects, raw ids and autocomplete](../admin/widgets.md)).

Of the undocumented pieces, django.contrib.admin.helpers.checkbox was removed in 5.0, and the module django.contrib.admin.tests in 6.2; `InclusionAdminNode.__init__` takes the tag's name first since 6.1 (`django/contrib/admin/templatetags/base.py:InclusionAdminNode.__init__`).

## The documentation generator

Since 5.2 admindocs shows a model only to a user who may view or change it, asking the user and no model admin (`django/contrib/admindocs/views.py:user_has_model_view_permission`). A link in a docstring may also carry its own text, the target after it in angle brackets (`django/contrib/admindocs/utils.py:split_explicit_title`; [The documentation generator: `django.contrib.admindocs`](../admin/admindocs.md)).
