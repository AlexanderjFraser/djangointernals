---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Permissions in the admin: `has_change_permission` and the others

The admin asks a model admin what a request's user may do with its model, through methods of `BaseModelAdmin`: `has_add_permission`, `has_change_permission`, `has_delete_permission`, `has_view_permission` and `has_module_permission`. The index, a model admin's pages, actions and inlines, and a related field's links ask them, and by default each asks the user's `has_perm`, or for the module its `has_module_perms`.

Being staff only gets a user past `AdminSite.admin_view` ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](site-urls.md)). After that the admin must decide what this user may do with this model's rows, and a project must be able to decide otherwise: for one object, or never. So the questions are methods, given the request and, for change, delete and view, the object. A model admin's refused view raises `PermissionDenied`, a 403 ([How an exception becomes a response](../handlers/exceptions.md)); a template leaves out what is denied.

## The default answers

The defaults for add, change, delete and view join the model's application label to a codename that `get_permission_codename` makes of an action and the model's name, `"fleet.change_ship"`, and ask the user's `has_perm` with it, which for auth's users is `PermissionsMixin.has_perm` ([Permissions: `Permission`, groups and `has_perm`](../auth/permissions.md)) (`django/contrib/admin/options.py:BaseModelAdmin.has_change_permission`, `django/contrib/auth/__init__.py:get_permission_codename`). `has_view_permission` asks for view, then for change: a user who may change may see. `BaseModelAdmin.has_view_or_change_permission` asks the two methods in turn, so it follows an override of either. `has_module_permission` asks the user's `has_module_perms` with the label; by its docstring it governs the two index pages and restricts no add, change or delete view.

The defaults ignore the object; their docstrings say what an override owes: given an object, whether the request may act on it; given `None`, whether it may act on any object of the type. The defaults do not hand the object to `has_perm`, and `ModelBackend` answers no to any question asked with one: nora's `has_perm` for `"fleet.change_ship"` is true, and with Endeavour as the object false (`django/contrib/auth/backends.py:ModelBackend.get_all_permissions`).

`ModelAdmin.get_model_perms` puts the four, asked with no object, in a dictionary under `"add"`, `"change"`, `"delete"` and `"view"`. The index leaves out a model whose model admin's `has_module_permission` refuses or whose four answers are all false ([The site's own pages: the index, the login and `AdminSite.each_context`](site-views.md)) (`django/contrib/admin/sites.py:AdminSite._build_app_dict`).

## Which page asks which

| page | asks | when refused |
|---|---|---|
| the index, an application's index | `has_module_permission`, then `get_model_perms` | the model left out; an empty application's index, 404 |
| the change list | `has_view_or_change_permission`; `has_change_permission` for its title, `has_add_permission` for its add button | 403 |
| the add page | `has_add_permission` | 403 |
| a change page | `has_view_or_change_permission` with the object, before its absence is answered | 403, for a missing object too |
| a change page, `"POST"` of its form | `has_change_permission` with the object, before the form is bound; for `"_saveasnew"`, `has_add_permission` | 403 |
| the delete page | `has_delete_permission` with the object, before its absence is answered; then, for each registered object the delete would take, its model admin's | 403; a lack is listed, and the delete refused |
| the history page | as a change page | 403 |
| an action | for each of its `"allowed_permissions"`, the method named for it, with no object; one true is enough | not offered, and not run if posted |
| `list_editable` | `has_change_permission`, with no object, then for each row | no formset, and the `"POST"` 403; the row's fields removed, the row not saved |
| a related field's widget, unless in `raw_id_fields` | the related model admin's four, with no object | the link left out |

*Where each page asks: `django/contrib/admin/options.py:ModelAdmin.changelist_view`, `django/contrib/admin/options.py:ModelAdmin._changeform_view`, `django/contrib/admin/options.py:ModelAdmin._delete_view`, `django/contrib/admin/utils.py:get_deleted_objects`, `django/contrib/admin/options.py:ModelAdmin.history_view`, `django/contrib/admin/options.py:ModelAdmin._filter_actions_by_permissions`, `django/contrib/admin/options.py:ModelAdmin._get_formset_with_permissions`, `django/contrib/admin/options.py:BaseModelAdmin.formfield_for_dbfield`.*

A user who may view and not change gets a change page to read: `ModelAdmin.get_form` excludes every field from the form class, `ModelAdmin._changeform_view` makes every field read-only and titles the page "View", and Close replaces the save buttons (`django/contrib/admin/options.py:ModelAdmin.get_form`, `django/contrib/admin/templatetags/admin_modify.py:submit_row`). As nora:

| page | Ship | Port | Voyage |
|---|---|---|---|
| change list | 200, "Select ship to change" | 200, "Select port to view" | 403 |
| add page | 403 | 403 | 403 |
| change page of pk 1 | 200, "Change ship" | 200, "View port" | 403 |
| the same, `"POST"` | 302 to the change list | 403 | 403 |
| delete page | 403 | 403 | 403 |
| history page | 200 | 200 | 403 |
| change page of pk 99 | 302 to /admin/ | 302 to /admin/ | 403 |

*Nora's answers. Piet had a 200 or a redirect from each; tomas, not staff, a redirect to the login.*

A missing object sends a user who passes the check to the index with a warning; one who fails it gets 403, and cannot tell which keys exist.

> **Changed in 6.2.** The history page asks the permission before it answers an object's absence (`docs/releases/6.2.txt`).

## Superusers, and staff without permissions

`PermissionsMixin.has_perm` and `PermissionsMixin.has_module_perms` answer yes for an active superuser whatever is asked, so every default is true for piet, whom only an override can refuse. Staff with no permission pass `admin_view` and are refused every model's pages: tomas, made staff, got an index saying "You don’t have permission to view or edit anything.", 404 for /admin/fleet/ and 403 for the ship change list.

## Inlines

`InlineModelAdmin` declares the four again; its `InlineModelAdmin.has_add_permission` takes the parent object. `ModelAdmin.get_inline_instances` leaves out an inline the user may neither view, change, add to nor delete from, and sets `max_num` to nought on one the user may not add to (`django/contrib/admin/options.py:ModelAdmin.get_inline_instances`). `ModelAdmin.get_inline_formsets` lets an inline be edited only with the parent's permission, change on a change page and add on an add page; without it the inline's add, change and delete are false, and its formset's extra forms and maximum are set to nought ([Inlines: `InlineModelAdmin` and its formsets](inlines.md)) (`django/contrib/admin/options.py:ModelAdmin.get_inline_formsets`). So nora, who may change ships, saw Valletta's ships read-only: she may not change the port.

The table a many-to-many field makes has no permissions of its own, as a comment in `has_add_permission` says, so for an inline of one, add, change and delete ask for change on the model at the other end from the parent, and view for view or change (`django/contrib/admin/options.py:InlineModelAdmin._has_any_perms_for_target_model`). On PortAdmin, an inline of the table behind Voyage's calls asks `"fleet.change_voyage"`, and nora did not get it.

## Overriding a permission

Two overrides, one per object, one read-only for everyone:

```python
# harbour/fleet/admin.py
@admin.register(Ship)
class ShipAdmin(admin.ModelAdmin):
    ...

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.tonnage > 300:
            return request.user.is_superuser
        return super().has_change_permission(request, obj)


@admin.register(Voyage)
class VoyageAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
```

Nora then got Endeavour's change page as "View ship" and a 403 for its `"POST"`, while Beagle's was "Change ship" and saved; the change list, asked with no object, still read "Select ship to change". Piet got voyages view-only, on the index and the change page, and a 403 from the add page, the delete page and a `"POST"`: `has_view_permission`, not overridden, still asks `has_perm`.

> **Trap.** An action's permissions are asked with no object, so a refusal for one object does not reach it. With Endeavour moved to Piraeus, nora ran home_at_valletta on it, and it went home to Valletta, though she could only view its change page. The rows of `list_editable`, and the objects a delete would take, are asked about one by one.
