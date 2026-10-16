---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Actions: `response_action` and `delete_selected`

An action is a function the admin runs on the objects a user ticked on the change list, or, since 6.1, on the one object of a change form. `ModelAdmin.get_actions` collects a model admin's actions for a request, `ModelAdmin.response_action` turns a posted action form into a call, and `delete_selected`, the site's own action, confirms with a page that posts back to the change list.

The change list has to let a user do one thing to many rows at once, whatever it is. So an action is only a function of the model admin, the request and a queryset of the chosen rows, and the admin does the rest: what is offered, what was chosen, and what the browser gets after.

## Where a model admin's actions come from

An admin site keeps **site-wide actions**, which each of its model admins includes unless its `ModelAdmin.actions` is `None`: `delete_selected`, from `AdminSite.__init__`, and any that `AdminSite.add_action` adds. `AdminSite.disable_action` takes a name from the enabled ones, `AdminSite.actions`, but not from the dictionary `AdminSite.get_action` reads, so a disabled action named in one model admin's `ModelAdmin.actions` comes back for that one (`django/contrib/admin/sites.py:AdminSite.disable_action`).

Each item of `actions` is a callable or a name, which `ModelAdmin.get_action` looks for on the model admin's class, then among the site's actions. A method comes from the class, unbound, so that, as the comment says, methods and functions are called alike, with the model admin first (`django/contrib/admin/options.py:ModelAdmin.get_action`). `ModelAdmin._get_base_actions` puts the site's enabled actions first, less those the model admin's list names, then the model admin's, keeping those located on the page being built (`django/contrib/admin/options.py:ModelAdmin._get_base_actions`).

Each is an `Action`, a dataclass of the function, its name, its description, its plural description and its locations (`django/contrib/admin/options.py:Action`), read from attributes that the decorator `django.contrib.admin.action` sets on the function: `"short_description"`, `"plural_description"` (the description when no plural is given) and `"locations"`, where one `ActionLocation` is made a list; the `"allowed_permissions"` it sets too are not copied into the `Action` (`django/contrib/admin/decorators.py:action`). Without a description, the name, capitalised, underscores as spaces, describes it; without locations, it is the change list's.

## Which actions a user is offered

`ModelAdmin.get_actions` returns a dictionary from each action's name to its `Action`, empty when `actions` is `None` or the page is a popup. Otherwise `ModelAdmin._filter_actions_by_permissions` keeps an action without `"allowed_permissions"`, and one with them when any of the model admin's methods they name is true for the request: `"change"` names `BaseModelAdmin.has_change_permission`, asked without an object even on a change form (`django/contrib/admin/options.py:ModelAdmin._filter_actions_by_permissions`). `ModelAdmin.get_action_choices` makes the action form's choices: a blank one, then each name with a description formatted with the model's verbose names: the plural description on the change list, the description on a change form (`django/contrib/admin/options.py:ModelAdmin.get_action_choices`). `delete_selected` asks for `"delete"`, home_at_valletta for `"change"`:

```text
# a run: the choices of the action form on /admin/fleet/ship/
nora  [('', '- Select an option -'), ('home_at_valletta', 'Home the selected ships at Valletta')]
piet  [('', '- Select an option -'), ('delete_selected', 'Delete selected ships'), ('home_at_valletta', 'Home the selected ships at Valletta')]
```

## The action form and `response_action`

The change list shows an `ActionForm`, a choice field `"action"` and a hidden boolean `"select_across"`, which the page's JavaScript sets when the user selects every row the change list matches (`django/contrib/admin/helpers.py:ActionForm`). The ticked rows are a column put first when there are actions, `ModelAdmin.action_checkbox`: checkboxes named `ACTION_CHECKBOX_NAME`, `"_selected_action"`, holding the rows' keys ([The change list: `changelist_view` and `ChangeList`](change-list.md)). The action form may stand above and below the list (`ModelAdmin.actions_on_top`, `ModelAdmin.actions_on_bottom`), both inside the form that holds the list, and each copy's Run button posts `"index"`, the copy's number (`django/contrib/admin/templatetags/admin_list.py:admin_actions`).

`ModelAdmin.response_action` turns that `"POST"` into a call (`django/contrib/admin/options.py:ModelAdmin.response_action`):

1. It binds the action form to a copy of the `"POST"` whose `"action"` is the one from the copy `"index"` names, without the selected keys and `"index"`.
2. It gives the form the choices of `get_action_choices` and validates it, so the offer is also the check. An invalid form, as an action not offered makes it, adds the warning "No action selected." and returns `None`.
3. It takes the function from `get_actions`. With no key selected and `"select_across"` false it adds a warning and returns `None`; unless `"select_across"` is true, it narrows the queryset to the selected keys.
4. It calls the function. A response the function returns, any `HttpResponseBase`, is returned; for anything else, a redirect to the request's path and query string.

On the change list the queryset is `ChangeList.get_queryset` for the request, so `"select_across"` means every row the query string's filters and search match, on every page.

```text
# a run: nora posts the action form of /admin/fleet/ship/
action=home_at_valletta  index=0  _selected_action=2
    302 Found   Location: /admin/fleet/ship/
    message (info): 1 ships now home at Valletta.
action=delete_selected  index=0  _selected_action=2
    302 Found   Location: /admin/fleet/ship/
    message (warning): No action selected.
```

## The two branches in `changelist_view`

`ModelAdmin.changelist_view` calls `response_action` from two places, each for a `"POST"` to a model admin with actions and without `"_save"`, the save button of `ModelAdmin.list_editable` ([The change list's columns: `list_display` and `list_editable`](list-display.md)) (`django/contrib/admin/options.py:ModelAdmin.changelist_view`). The first, under the comment "Actions with no confirmation", takes a `"POST"` with `"index"`, from the action form; with no key selected it calls nothing and warns "Items must be selected in order to perform actions on them. No items have been changed." The second, "Actions with confirmation", takes selected keys without `"index"`, as the confirmation page of `delete_selected` posts them.

When `response_action` returned `None`, or nothing was selected, the view redirects to the same path and query string, so that, as the comment says, a refresh or "No, take me back" on a confirmation page does not post the form again. `changelist_view` opens no transaction around an action, as `ModelAdmin.changeform_view` and `ModelAdmin.delete_view` do around a `"POST"`.

## `delete_selected`

`delete_selected` is declared with `django.contrib.admin.action` as asking for `"delete"`, and described as "Delete selected %(verbose_name_plural)s" (`django/contrib/admin/actions.py:delete_selected`). It runs for each `"POST"` of a deletion, and begins with `ModelAdmin.get_deleted_objects`: the objects a delete would take, nested, their counts by model, the models whose objects the user may not delete, and the protected objects ([Deleting: `delete_view` and `get_deleted_objects`](deleting.md)).

Without `"post"`, or with something protected, it answers with the confirmation page, `"admin/delete_selected_confirmation.html"` unless the model, the application or `ModelAdmin.delete_selected_confirmation_template` has another ([The admin's templates and media](templates.md)). With a permission lacking or an object protected, the page is titled "Cannot delete" and the model's name, and lists what stands in the way. Otherwise it is titled "Delete multiple objects", lists the objects, and holds a form of hidden inputs: each key as `"_selected_action"`, `"action"` as `"delete_selected"`, and `"post"` as `"yes"` (`django/contrib/admin/templates/admin/delete_selected_confirmation.html`).

With `"post"` and nothing protected, a lacking permission raises `PermissionDenied`. Otherwise, if the queryset has any rows, the function calls `ModelAdmin.log_deletions` ([The log and the history: `LogEntry` and `history_view`](log.md)), then `ModelAdmin.delete_queryset`, and adds "Successfully deleted" and the count as a success message; either way it returns `None`, for `response_action` to redirect. `delete_queryset` calls `QuerySet.delete`, for efficiency, the documentation says, so `Model.delete` is not called ([Creating, updating and deleting through a queryset](../querysets/writing.md)) (`django/contrib/admin/options.py:ModelAdmin.delete_queryset`, `docs/ref/contrib/admin/actions.txt`).

The second `"POST"` of piet's deletion of both ships collected the related objects again and wrote both rows of the log in one INSERT; the delete then selected what it would take and sent BEGIN, a DELETE each for the voyages' port calls and manifests, the voyages and the ships, and COMMIT:

```text figure=delete-selected
1. POST /admin/fleet/ship/  action=delete_selected  select_across=0  index=0  _selected_action=2, 1
   ModelAdmin.changelist_view: "index" posted, the first branch
     ModelAdmin.response_action: the queryset narrowed to the keys 2 and 1
       delete_selected
         ModelAdmin.get_deleted_objects: what the delete would take
         no "post": the confirmation page
   200  "Delete multiple objects", a form of hidden inputs:
        _selected_action=2, 1  action=delete_selected  post=yes

2. POST /admin/fleet/ship/  _selected_action=2, 1  action=delete_selected  post=yes
   ModelAdmin.changelist_view: no "index", keys posted, the second branch
     ModelAdmin.response_action: the same queryset
       delete_selected
         ModelAdmin.get_deleted_objects again: nothing protected, no permission lacking
         "post" posted:
           ModelAdmin.log_deletions    INSERT two rows into "django_admin_log"
           ModelAdmin.delete_queryset  SELECTs; BEGIN; DELETE port calls, manifests, voyages, ships; COMMIT
           ModelAdmin.message_user     "Successfully deleted 2 ships."
         returns None
       None: a redirect to the request's path
   302  to /admin/fleet/ship/
```

*piet's deletion of two ships: two `"POST"`s to the change list, told apart by `"index"` and `"post"`.*

## Actions on the change form

`ModelAdmin._changeform_view` asks `get_actions` for `ActionLocation.CHANGE_FORM` and, on a change page with any, makes the action form with the prefix `"CHANGE_FORM"` (`django/contrib/admin/options.py:ModelAdmin._changeform_view`). It sits in the change form's own form beside a hidden `"_selected_action"`, the object's key, so its select is posted with every save: a `"POST"` is an action's when it has `"CHANGE_FORM-action"` and none of `"_save"`, `"_continue"` and `"_addanother"`. The selected keys must be exactly the object's, or the view raises `BadRequest`, a 400. `response_action` gets `BaseModelAdmin.get_queryset`, with `"select_across"` forced false, and the view answers with the function's response or a redirect to the change page, all before it asks for the change permission ([The change form: `changeform_view`](change-form.md)).

> **Deprecated.** Since 6.1, unpacking or indexing an `Action` like the tuple it replaced warns with `RemovedInDjango2028Warning`, as, through `warn_about_implementation`, does overriding `get_actions` or `get_action_choices` without `action_location=`; such a `get_actions` gives a change form no actions (`django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location`) ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](../utils/deprecation.md)).
