---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Making the permissions: `create_permissions`

`create_permissions` is the receiver of `post_migrate` that writes the rows of `"auth_permission"`: for each model, one for each action its `Meta` lists in `"default_permissions"`, add, change, delete and view unless it says otherwise, and one for each pair in `"permissions"`. Beside it, `rename_permissions_after_model_rename` renames the rows when a migration renames their model, and `check_models_permissions` reports permissions too long or clashing.

A permission is a row naming a model by its content type and an action by its codename ([Permissions: `Permission`, groups and `has_perm`](permissions.md)), and defining a model makes none. `AuthConfig.ready` connects both receivers to `post_migrate` with no sender, so each runs for every application with a models module, and registers the check among the model checks (`django/contrib/auth/apps.py:AuthConfig.ready`).

## The permissions a model asks for

A model's options carry two lists. `Options.default_permissions` is a tuple of actions, add, change, delete and view unless the `Meta` sets another (`django/db/models/options.py:Options.__init__`); `Options.permissions` is a list of pairs of codename and name, empty unless the `Meta` sets one ([The options: what a model keeps as `_meta`](../models/options.md)).

`_get_builtin_permissions` turns each action into a pair. The codename is the action and the model's name joined by an underscore, `"change_ship"`, made by `get_permission_codename`, which the admin also uses ([The admin](../admin.md)) (`django/contrib/auth/__init__.py:get_permission_codename`). The name is "Can", the action and `Options.verbose_name_raw`, the verbose name untranslated whatever language is active (`django/contrib/auth/management/__init__.py:_get_builtin_permissions`). `_get_all_permissions` puts the `Meta`'s own pairs after these (`django/contrib/auth/management/__init__.py:_get_all_permissions`).

## `create_permissions` in its order

`create_permissions` returns without a write when the application has no models module; when the registry it is given has no `Permission` (auth not installed, or its migrations not applied in the state); when the router does not let `Permission` be migrated on the database it is given; or when the registry has no `ContentType` or no such application (`django/contrib/auth/management/__init__.py:create_permissions`). The registry is the `"apps"` that migrate sends: a state's registry of historical models, not the main one ([The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md)).

Otherwise it first calls `create_contenttypes` for the application, which clears `ContentTypeManager`'s cache and makes the missing content types (`django/contrib/contenttypes/management/__init__.py:create_contenttypes`). It takes the application's models from the registry, less the models made for many-to-many fields and those swapped out (`django/apps/config.py:AppConfig.get_models`), and their content types from `ContentTypeManager.get_for_models` with `for_concrete_models=False`, which gives a proxy its own content type, and so its own permissions, and makes any it does not find. A comment says the first call is needed when auth stands before contenttypes in `INSTALLED_APPS`, which puts auth's receivers first. Run so without it, a migrate made the same rows; a flush, in a process whose cache held the deleted content types, failed on the foreign key.

Then one query reads the pairs of content type and codename that exist for those content types. Each pair a model asks for that is not among them becomes a `Permission`, and all are inserted by one `QuerySet.bulk_create`. The name plays no part in the match: a name changed in a `Meta` leaves its row's name as it was, and a pair taken out of a `Meta` leaves its row.

The registry being a state's, a permission added to a `Meta` in an application with migrations is made by the migrate that applies the `AlterModelOptions` recording it (`django/db/migrations/operations/models.py:AlterModelOptions`); the models of an application without migrations are rendered from their classes.

## The harbour office's permissions

After migrate, each of fleet's models has its four rows, from `"add_port"` to `"view_voyage"`; the model made for Voyage's many-to-many field has none. Three models of the office's own put the options to work:

```python
# harbour/office/models.py
from django.db import models

from harbour.fleet.models import Ship


class TideTable(models.Model):
    port = models.CharField(max_length=60)

    class Meta:
        default_permissions = ()


class BerthRequest(models.Model):
    ship = models.CharField(max_length=60)

    class Meta:
        permissions = [("approve_berthrequest", "Can approve berth request")]


class Tug(Ship):
    class Meta:
        proxy = True
```

The next migrate wrote these rows of office. At verbosity 2 it printed each, on the process's standard output rather than the command's, in a line like "Adding permission 'Permission object (65)'", the `Permission` of a state's registry lacking the class's `Permission.__str__`.

```text
berthrequest  add_berthrequest      Can add berth request
berthrequest  approve_berthrequest  Can approve berth request
berthrequest  change_berthrequest   Can change berth request
berthrequest  delete_berthrequest   Can delete berth request
berthrequest  view_berthrequest     Can view berth request
tidetable     (none)
tug           add_tug               Can add tug
tug           change_tug            Can change tug
tug           delete_tug            Can delete tug
tug           view_tug              Can view tug
```

TideTable has a content type and no permission. Tug's rows are under office, so nora's `"fleet.change_ship"` gives nothing over tugs: a proxy does not inherit its concrete model's permissions, as Django's documentation puts it (`docs/topics/auth/default.txt`).

## Renaming with the model: `rename_permissions_after_model_rename`

When a migration renames a model, an operation that contenttypes' `pre_migrate` receiver puts after the `RenameModel` renames its content type in place ([Content types, static files and the other contrib apps](../contrib.md)), so the rows keep their content type but their codenames and names carry the old name. `rename_permissions_after_model_rename` learns of the rename from the `"plan"` migrate sends: it collects each `RenameModel` in the application's migrations of the plan, old name to new, or new to old for a migration unapplied. Without a plan, as from flush, it does nothing (`django/contrib/auth/management/__init__.py:rename_permissions_after_model_rename`).

For each rename it reads the model's actions and verbose name from the registry, or, for a model the state no longer has, `Permission`'s default actions and the model's name (`django/contrib/auth/management/__init__.py:_get_permission_metadata`). It finds the application's rows whose codename is an action and the old name, and plans a new codename and name for each. Only these move. In a run where a dock application's Tug became Tender, `"change_tug"` became `"change_tender"` while the `Meta`'s `"launch_tug"` stayed and `create_permissions` made `"launch_tender"` beside it.

Before changing a row it looks for the new codenames among the application's rows. If one is there, it warns of each row in conflict, unless verbosity is 0, and raises `RuntimeError`: migrate stops with the migration applied and recorded, no row renamed, and no later receiver run, for that application (`create_permissions` among them) or any after it. Otherwise it saves every row inside one `atomic`. It runs before `create_permissions`; with the two connected the other way round, the same rename failed: `create_permissions` made `"add_tender"` and the other three first, and the renaming refused all four.

> **Changed in 6.1.** A permission's name and codename are renamed when a migration renames its model (`docs/releases/6.1.txt`).

## Proxy models: the migration `0011_update_proxy_permissions`

Auth's migration `0011_update_proxy_permissions` moves, for each proxy model in the state, the rows of its default permissions and of its `Meta`'s pairs from the concrete model's content type to the proxy's own, and back when unapplied. Where the proxy already has such a row the update raises `IntegrityError`, and the migration prints a warning naming both content types and goes on (`django/contrib/auth/migrations/0011_update_proxy_permissions.py:update_proxy_model_permissions`).

> **Why.** A proxy's permissions were once made with its concrete model's content type. The release notes of 2.2, which changed that, give this migration as the way existing rows follow (`docs/releases/2.2.txt`).

## `check_models_permissions`

`check_models_permissions` measures the models of the main registry against `Permission`'s columns, 255 characters for a name and 100 for a codename. It reports a built-in name or codename too long, with the longest verbose name or model name that would fit (`"auth.E007"`, `"auth.E011"`); a `Meta` pair whose name or codename is too long (`"auth.E008"`, `"auth.E012"`); a `Meta` codename that is also a built-in one (`"auth.E005"`); and any other `Meta` codename given twice (`"auth.E006"`) (`django/contrib/auth/checks.py:check_models_permissions`).
