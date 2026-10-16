---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The admin's checks: `check_dependencies` and `ModelAdminChecks`

The admin's system checks are two functions registered under the tag `"admin"`: `check_dependencies`, which looks for the applications, template settings and middleware the admin needs, and `check_admin_app`, which has every admin site check its model admins, each through a checks class, `ModelAdminChecks` for a model admin and `InlineModelAdminChecks` for an inline.

Most of a model admin's options are read only when a page uses them, so a misspelt name would otherwise surface only on that page, often as an exception. The checks read them, and the settings, when a command runs the system checks ([The system checks](../commands/checks.md)).

## When they run

`SimpleAdminConfig.ready` registers both functions, and `AdminConfig.ready` calls it before `autodiscover` (`django/contrib/admin/apps.py:SimpleAdminConfig.ready`). They run after every application is ready: under `AdminConfig`, after every admin module has registered its model admins.

## The admin's dependencies: `check_dependencies`

`check_dependencies` looks at the settings (`django/contrib/admin/checks.py:check_dependencies`). It returns nothing when the admin is not installed, and takes no notice of the applications it is given.

| what is required | id | asked |
|---|---|---|
| the contenttypes, auth and messages applications in `INSTALLED_APPS` | `"admin.E401"`, `"admin.E405"`, `"admin.E406"` | always |
| a `DjangoTemplates` engine in `TEMPLATES` | `"admin.E403"` | always |
| `"django.contrib.auth.context_processors.auth"` | `"admin.E402"` | when there is such an engine and `AUTHENTICATION_BACKENDS` holds `ModelBackend` or a subclass |
| `"django.contrib.messages.context_processors.messages"` | `"admin.E404"` | when there is such an engine |
| `"django.template.context_processors.request"` | `"admin.W411"`, a warning | when there is such an engine and a site shows the navigation sidebar |
| `AuthenticationMiddleware`, `MessageMiddleware`, `SessionMiddleware` in `MIDDLEWARE` | `"admin.E408"`, `"admin.E409"`, `"admin.E410"` | always |

*What `check_dependencies` asks, and the id of each error or warning.*

The context processors are looked for in the first `DjangoTemplates` engine only, by the dotted paths the setting spells. The admin's base template reads `"user"` and `"messages"`, which the auth and messages processors set, and the sidebar includes `"admin/app_list.html"`, which reads the request's path. The warning needs a site in `all_sites` with `AdminSite.enable_nav_sidebar` true, its default.

The middleware are looked for by class: `_contains_subclass` imports each path in `MIDDLEWARE` and is satisfied by the class required or a subclass of it (`django/contrib/admin/checks.py:_contains_subclass`). It asks whether each is there, not in what order: the hint of `"admin.E410"` says to put `SessionMiddleware` before `AuthenticationMiddleware`, yet harbour's settings with `AuthenticationMiddleware` moved first passed every check. With `MessageMiddleware` taken out:

```text
# the check command, harbour's MIDDLEWARE without MessageMiddleware
SystemCheckError: System check identified some issues:

ERRORS:
?: (admin.E409) 'django.contrib.messages.middleware.MessageMiddleware' must be in MIDDLEWARE in order to use the admin application.

System check identified 1 issue (0 silenced).
```

## Every site and its model admins: `check_admin_app`

`check_admin_app` calls `AdminSite.check` on each site in `all_sites`, a weak set that `AdminSite.__init__` adds every site to, so a site is checked whether or not its URLs are in the URLconf, as long as something holds it (`django/contrib/admin/checks.py:check_admin_app`). `AdminSite.check` passes over a model admin whose class is `ModelAdmin` itself, one its docstring calls not customized at all, and checks each other one whose model belongs to an application the run was given, or to any when it was given none (`django/contrib/admin/sites.py:AdminSite.check`). In the harbour office that is `GroupAdmin`, `UserAdmin`, PortAdmin and ShipAdmin, and not Voyage's plain `ModelAdmin`.

`BaseModelAdmin.check` makes an instance of the class in `BaseModelAdmin.checks_class` and hands it the model admin (`django/contrib/admin/options.py:BaseModelAdmin.check`). `ModelAdmin` names `ModelAdminChecks` there and `InlineModelAdmin` names `InlineModelAdminChecks`, both subclasses of `BaseModelAdminChecks`, which checks the options the two share; a project adds checks of its own by naming a subclass in `checks_class`. An inline is checked through its parent: for each class in `inlines` that inherits from `InlineModelAdmin` and names a model, `ModelAdminChecks` makes an instance with the parent's model and site and calls its `check` (`django/contrib/admin/checks.py:ModelAdminChecks._check_inlines_item`).

## What the options are checked against

The checks read the options as attributes and call none of the hooks, which take a request; the check of `list_display_links` against `list_display` is skipped when the class overrides `ModelAdmin.get_list_display` (`django/contrib/admin/checks.py:ModelAdminChecks._check_list_display_links`).

- **The type.** Many options must be a list or a tuple, others a dictionary, a boolean or an integer; `form` must inherit from `BaseModelForm`, an inline's `formset` from `BaseModelFormSet`.
- **Fields of the model.** Each name in `raw_id_fields`, `autocomplete_fields`, `filter_horizontal`, `filter_vertical`, `radio_fields`, `prepopulated_fields`, `list_editable` and `ordering` must be a field, though `ordering` lets `"?"` alone, `"pk"`, a path with `"__"` and an expression other than an `F` through. `list_display` and `readonly_fields` take more: a callable, or an attribute of the model admin or of the model, and `list_display` a path across relations, though no item of it may be a many-to-many field or a reverse foreign key. `date_hierarchy` must lead to a date or date-and-time field, and `list_filter` must take one of its three forms ([Filters and search: `list_filter`, `search_fields` and `date_hierarchy`](filters.md)).
- **Relations.** `raw_id_fields` and `autocomplete_fields` must name foreign keys or many-to-many fields, and the model an autocomplete field points to must be registered on the same site, with `search_fields` on its model admin. `filter_horizontal` and `filter_vertical` must name many-to-many fields with no through model of their own.
- **`list_editable`.** Each field must be in `list_display`, editable, not the primary key, and not in `list_display_links`; nor the first column while `list_display_links` is empty, as it is by default, which links the first column. `None` there, or another column, frees it.
- **Actions.** Only the actions whose locations include `ActionLocation.CHANGE_LIST` are looked at: each permission in an action's `"allowed_permissions"` needs a method named after it, as `BaseModelAdmin.has_change_permission` is after `"change"`, and no two of them may share a name (`django/contrib/admin/checks.py:ModelAdminChecks._check_actions`, `django/contrib/admin/options.py:ModelAdmin._get_base_actions`).
- **An inline's parent.** `InlineModelAdminChecks` asks `_get_foreign_key` for the inline's foreign key to the parent, by `fk_name` if set, reports its error as `"admin.E202"`, and refuses an `exclude` naming that key (`django/contrib/admin/checks.py:InlineModelAdminChecks._check_relation`, `django/contrib/admin/checks.py:InlineModelAdminChecks._check_exclude_of_parent_model`).

A name in `fields` or `fieldsets` that is not a field passes, since, a comment says, it could be an extra field of the form (`django/contrib/admin/checks.py:BaseModelAdminChecks._check_field_spec_item`), and `search_fields` is checked only for its type. A ShipAdmin with "draught" in `fields` and "beam" in `search_fields` passed the checks, and then its change form and its search each raised `FieldError`.

## The messages

Most messages take one of three shapes, made by `must_be`, `must_inherit_from` and `refer_to_missing_field`: the option, or the item at fault with its index, and what it must be, must inherit from, or names that the model lacks (`django/contrib/admin/checks.py:must_be`). Each gives the class checked as its object. Here ShipAdmin has three mistakes, and harbour/crew/admin.py registers Sailor under the plain `ModelAdmin`:

```python
# harbour/fleet/admin.py
class ShipAdmin(admin.ModelAdmin):
    list_display = ["name", "tonnage", "home", "is_large", "draught"]
    list_editable = ["name"]
    autocomplete_fields = ["captain"]
    # the rest as before
```

```text
# the check command, with ShipAdmin as above
SystemCheckError: System check identified some issues:

ERRORS:
<class 'harbour.fleet.admin.ShipAdmin'>: (admin.E040) ModelAdmin must define "search_fields", because it's referenced by ShipAdmin.autocomplete_fields.
<class 'harbour.fleet.admin.ShipAdmin'>: (admin.E108) The value of 'list_display[4]' refers to 'draught', which is not a callable or attribute of 'ShipAdmin', or an attribute, method, or field on 'fleet.Ship'.
<class 'harbour.fleet.admin.ShipAdmin'>: (admin.E124) The value of 'list_editable[0]' refers to the first field in 'list_display' ('name'), which cannot be used unless 'list_display_links' is set.

System check identified 3 issues (0 silenced).
```
