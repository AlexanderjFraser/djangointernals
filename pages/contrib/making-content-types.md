---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Making content types: `create_contenttypes` and `RenameContentType`

`create_contenttypes` makes the rows of `"django_content_type"`: a receiver of `post_migrate` that inserts a row for each model of an application that has none, under migrate taking the models from the state the migrations leave. `inject_rename_contenttypes_operations`, a receiver of `pre_migrate`, puts a `RenameContentType` after each `RenameModel` of the plan so that a renamed model keeps its row, and the command remove_stale_contenttypes deletes the rows of models that are gone.

Permissions, the admin's log and generic keys hold a content type's key, so a model's row has to exist before they need it, keep its key through a rename, and outlive its model until someone decides what goes with it ([Content types: `ContentType` and its cache](content-types.md)).

The runs here add an application, pilots, to the harbour office: its migrations create Pilot, PilotBoat and Tender, rename PilotBoat to Launch, and delete Tender; its models.py also has Roster, which no migration creates.

## What `ContentTypesConfig.ready` connects

`ContentTypesConfig.ready` connects `create_contenttypes` to `post_migrate` with no sender, so that it runs for every application the signal is sent for, and `inject_rename_contenttypes_operations` to `pre_migrate` with the application's own config as sender, so that it runs once a migrate, when the signal is sent for contenttypes. It registers `check_generic_foreign_keys` and `check_model_name_lengths` (`django/contrib/contenttypes/apps.py:ContentTypesConfig.ready`).

## `create_contenttypes`

Migrate sends `post_migrate` for each installed application with a models module once the executor has finished, giving as apps the registry of the state the plan left; flush sends it with no apps, and `create_contenttypes` then uses the main registry (`django/core/management/sql.py:emit_post_migrate_signal`) ([The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md)). `create_contenttypes` then works in this order (`django/contrib/contenttypes/management/__init__.py:create_contenttypes`):

1. It returns for an application without a models module, for one the apps lack (as one whose migrations are all unapplied), for apps that lack `ContentType`, and where the router does not allow `ContentType` on the database.
2. It takes the names of the application's models from those apps: none made for a many-to-many field, none swapped out, proxies included; with none, it returns. A model no migration has created is not among them: after migrating pilots, Roster had no row; `ContentTypeManager.get_for_model` makes one when first asked.
3. It clears the cache of the manager of the `ContentType` it was given.
4. It reads the model names the table holds for the application's label, in one query, and inserts a row for each missing name, sorted, in one `QuerySet.bulk_create`. It changes and deletes nothing.
5. At verbosity 2 or more it prints a line for each row with `print`, to standard output whatever stream the command writes to.

Auth's `create_permissions` calls `create_contenttypes` itself, and auth comes first in `INSTALLED_APPS`, so these lines come from its call; the content types' own receiver, after it, found nothing missing ([Making the permissions: `create_permissions`](../auth/creating-permissions.md)).

```text
# call_command("migrate", "pilots", "0001_initial", verbosity=2)
...
  Applying pilots.0001_initial... OK (0.002s)
...
Running post-migrate handlers for application pilots
Adding content type 'pilots | pilot'
Adding content type 'pilots | pilotboat'
Adding content type 'pilots | tender'
Adding permission 'Permission object (101)'
...
```

The rows got the keys 26, 27 and 28, in the order of the sorted names.

> **Trap.** Under migrate that `ContentType` is a historical model, whose manager has a cache of its own; the process's `ContentType.objects` keeps what it had read. After PilotBoat was renamed, its `ContentTypeManager.get_for_id` still answered pilotboat for key 27, while the table said launch.

## Following a rename: `inject_rename_contenttypes_operations`

A `RenameModel` changes the name a model's row is found by. Left alone, the next `create_contenttypes` would insert a row for the new name, and the old row, with every permission and generic key holding its key, would name a model that is gone. `inject_rename_contenttypes_operations` prevents this by editing the plan before the executor runs it (`django/contrib/contenttypes/management/__init__.py:inject_rename_contenttypes_operations`).

It looks for `ContentType` in the state the receivers of `pre_migrate` are shown; if the model is there and the router does not allow it on this database, it does nothing. If the model is not there, it walks the plan without inserting until the plan applies contenttypes' 0001_initial; a plan that unapplies that migration stops the walk: from there on, a comment says, the model is gone. Wherever the model is available, it inserts after each `RenameModel` a `RenameContentType` made from the migration's label and the two names in lower case (`RenameModel.old_name_lower`, `RenameModel.new_name_lower`), in migrations to be unapplied too.

The insertion is made in this run's migration objects, in no file: `migrate --plan`, which ends before `pre_migrate` is sent, listed only "Rename model PilotBoat to Launch", while a receiver of the run's own, connected after this one, found `RenameModel` and then `RenameContentType`. After it, row 27 named launch instead of pilotboat.

## `RenameContentType`

`RenameContentType` is a `RunPython` whose functions are its own methods, `RenameContentType.rename_forward` and `RenameContentType.rename_backward`, so it runs with the historical registry, where the router allows the migration's application ([`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](../migrations/special-operations.md)). Both call `RenameContentType._rename` with the names in their order (`django/contrib/contenttypes/management/__init__.py:RenameContentType.__init__`).

`_rename` asks the router again, for `ContentType`, finds the row, if there is one, with `ContentTypeManager.get_by_natural_key`, and saves the new name inside `atomic`. If the save succeeds, it clears the manager's cache, since, a comment says, `get_by_natural_key` cached the renamed instance under its old name. If it raises `IntegrityError`, a row with the new name exists already, a stale one by the comment's account: it warns with `RuntimeWarning`, puts the old name back on the instance, and migrate goes on (`django/contrib/contenttypes/management/__init__.py:RenameContentType._rename`). With pilots migrated back to 0001 and a row for launch made by hand, migrating forward warned:

```text
RuntimeWarning: Could not rename content type 'pilots.pilotboat' to 'launch' due to an existing conflicting content type. Run 'remove_stale_contenttypes' to clean up stale entries.
```

> **Trap.** After that warning the old row is the stale one: Launch's content type is the row that was in the way, key 30, while key 27 names pilotboat and keeps what pointed at it, in the run four permissions, which remove_stale_contenttypes then listed for deletion.

## Stale content types: remove_stale_contenttypes

A **stale content type** is a row whose `ContentType.model_class` is `None`, as when a migration has deleted its model, which `create_contenttypes` never notices, or its application has left `INSTALLED_APPS`. The command remove_stale_contenttypes deletes such rows (`django/contrib/contenttypes/management/commands/remove_stale_contenttypes.py:Command.handle`).

Where the router allows `ContentType` on the database of `--database`, it clears the manager's cache and reads every row, grouped by application label. A label the app registry lacks is skipped unless `--include-stale-apps` is given; elsewhere, the stale rows are those whose `model_class` is `None`.

Unless `--noinput` is given, it first collects each stale row with a `Collector` made with `force_collection=True`, which fast-deletes nothing and collects what a database-level cascade would remove too, and lists each model found with its number of objects. Only "yes" deletes. Each row is then deleted by `Model.delete`, which cascades as any delete does ([Deleting: the `Collector`](../models/deleting.md)). A note had been attached to tender 1 before Tender was deleted:

```text
# call_command("remove_stale_contenttypes", verbosity=2), answered no
...
The content types and dependent objects that would be deleted are:

    - Content type for pilots.tender
    - 4 auth.Permission object(s)
    - 1 notes.Note object(s)
...
Type 'yes' to continue, or 'no' to cancel: no
Stale content types remain.
```

With `--noinput` the row went, and the note with it. With pilots removed from `INSTALLED_APPS` the command deleted nothing, and with `--include-stale-apps` as well, every row of the application.

## The application's own migrations

0002_remove_content_type_name drops the name column that 0001_initial made, and when unapplied fills it again with `add_legacy_name`, from each model's class name in the migration's state, or the row's model field where the state lacks the model (`django/contrib/contenttypes/migrations/0002_remove_content_type_name.py:add_legacy_name`).

## The two checks

A model's own checks cover its local fields and its many-to-many fields (`django/db/models/base.py:Model._check_fields`), not a `GenericForeignKey`, which is a private field. `check_generic_foreign_keys` finds each `GenericForeignKeyDescriptor` in a model class's own dictionary and runs `GenericForeignKey.check` on its field ([Generic foreign keys: `GenericForeignKey`](generic-foreign-key.md)) (`django/contrib/contenttypes/checks.py:check_generic_foreign_keys`). `check_model_name_lengths` reports `"contenttypes.E005"` for a model whose name in lower case is longer than 100 characters, the `max_length` of `ContentType.model` (`django/contrib/contenttypes/checks.py:check_model_name_lengths`). Both are registered under the tag `"models"` ([The system checks](../commands/checks.md)).
