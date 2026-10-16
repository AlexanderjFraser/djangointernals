---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Content types: `ContentType` and its cache

`ContentType` is a row for each installed model, named by its application label and its model name. Its manager, `ContentTypeManager`, finds the row for a model, an instance, a key or a natural key, makes the row for a model that has none, and keeps every row found or made that way in a cache that only `ContentTypeManager.clear_cache` empties.

A content type's key is what a table holds where it has to name a model: a permission ([Permissions: `Permission`, groups and `has_perm`](../auth/permissions.md)), a line of the admin's log ([The log and the history: `LogEntry` and `history_view`](../admin/log.md)), a note's generic foreign key ([Generic foreign keys: `GenericForeignKey`](generic-foreign-key.md)). The generic foreign key needs that key whenever it sets or loads an object, and the admin for every change it logs. So the manager reads each row once and keeps it: lookups "are cached so that subsequent lookups for the same model don't hit the database", says the docstring of `ContentTypeManager.get_for_model` (`django/contrib/contenttypes/models.py:ContentTypeManager`).

## The row

Besides its key, `ContentType` has two fields of 100 characters: `ContentType.app_label`, the label of the model's application, and `ContentType.model`, the class's name in lower case. `unique_together` makes the pair unique, and the table is `"django_content_type"` (`django/contrib/contenttypes/models.py:ContentType`). Nothing else is stored.

`ContentType.model_class` asks the app registry for the model the pair names and answers `None` when there is none: the row is **stale**, left by a model deleted or an application removed. `ContentType.name` is the model's `verbose_name`, or the stored `model` for a stale row; `ContentType.app_labeled_name`, which `ContentType.__str__` returns, joins the application's `verbose_name` to the model's, or gives the bare pair for a stale row. Worked out at each call, both follow the active language:

```text
# a shell of the harbour office's site
ContentType.objects.get_for_model(Ship)           key 12    Fleet | ship
ContentType.objects.get_for_model(ContentType)    key 6     Content Types | content type
    inside translation.override("fr")                       Types de contenus | type de contenu
a row made for office.tidetable, which names no model:
    model_class() None    name 'tidetable'    str 'office | tidetable'
```

`ContentType.natural_key` gives the pair, and `ContentTypeManager.get_by_natural_key` takes it back. A content type's key "isn't easy to predict", the documentation says, since it depends on how and when migrate ran; data serialized with natural keys names a content type by its pair instead (`docs/topics/serialization.txt`).

`ContentType.get_object_for_this_type` gets one object with the arguments given, through the model's base manager, on the database `using=alias` names or else the router's, and `ContentType.get_all_objects_for_this_type` filters the base manager's queryset by them. The base manager is a plain `Manager` unless the model's options name another (`django/db/models/options.py:Options.base_manager`) ([Managers](../models/managers.md#the-default-manager-and-the-base-manager)): Veteran's manager keeps the sailors who signed on before 2020, yet Veteran's own content type found Ada, who signed on in the run, with one query of `"crew_sailor"` and no condition on the date (`django/contrib/contenttypes/models.py:ContentType.get_object_for_this_type`). On a stale row both methods raise `AttributeError`: "'NoneType' object has no attribute '_base_manager'". Reading one note's object, the generic foreign key calls `get_object_for_this_type` (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.fetch_one`), so through a stale content type it raised the same error.

## The cache

`ContentTypeManager.__init__` makes one dictionary. Its keys are database aliases, and under each alias `ContentTypeManager._add_to_cache` puts every row twice, under its pair and under its key. It takes the pair from the row's own fields, not from its model's options, because, its comment says, a row may be stale. The alias is the manager's `BaseManager.db`: the one `BaseManager.db_manager` set, or else the router's `db_for_read` for `ContentType` (`django/db/models/manager.py:BaseManager.db`). `ContentType.objects` is a copy of the manager the class declares, made by its options (`django/db/models/options.py:Options.managers`), and `db_manager` makes another; the copies are shallow, so all of them share the one dictionary.

After `ContentTypeManager.clear_cache`, which empties the dictionary for every alias, the run asked for the ship model's content type five times and sent one query:

```text
# a shell of the harbour office's site
ContentType.objects.get_for_model(Ship)                    1 query, for the pair ('fleet', 'ship')
ContentType.objects.get_for_model(Ship)                    0
ContentType.objects.get_for_model(endeavour)               0
ContentType.objects.get_for_id(12)                         0
ContentType.objects.get_by_natural_key("fleet", "ship")    0
the same object each time; the cache's keys: {'default': [('fleet', 'ship'), 12]}
```

## `get_for_model`

`ContentTypeManager.get_for_model` takes a model or an instance. `ContentTypeManager._get_opts` takes the options of its concrete model, or of the model itself with `for_concrete_model=False`, and the cache is read by the pair (`django/contrib/contenttypes/models.py:ContentTypeManager.get_for_model`). On a miss the method calls `QuerySet.get` with the pair and, if there is no row, `get_or_create`; either way the row goes into the cache. A comment gives the reason for the `get`: it reads from the router's `db_for_read` (ticket 20401), where `QuerySet.get_or_create` reads from the database for writing. Another gives the reason for `get_or_create` rather than `QuerySet.create`: a race with another process making the same row. With the logbook model's row deleted inside a transaction, `get_for_model` sent a SELECT, the SELECT of `get_or_create`, a savepoint, the INSERT and the savepoint's release.

So a proxy is answered with its concrete model's row ([Inheritance: abstract bases, parents with tables and proxies](../models/inheritance.md)) unless it asks for its own, which migrate makes too:

```text
# a shell of the harbour office's site
ContentType.objects.get_for_model(Veteran)                            key 1    Crew | sailor
ContentType.objects.get_for_model(Veteran, for_concrete_model=False)  key 2    Crew | veteran
```

The admin passes `for_concrete_model=False`, so a change made through a proxy's admin is logged under the proxy (`django/contrib/admin/models.py:LogEntryManager.log_actions`), and a proxy's permissions are made with its own content type ([Making the permissions: `create_permissions`](../auth/creating-permissions.md)).

## `get_for_models`, `get_for_id` and `get_by_natural_key`

`ContentTypeManager.get_for_models` returns a dictionary from each model given to its content type. It answers what it can from the cache, reads the rest in one query, an OR of one condition for each application label, and makes each row still missing with `QuerySet.create`, one at a time (`django/contrib/contenttypes/models.py:ContentTypeManager.get_for_models`). With the ship model's row cached, asking for the port, ship, lighthouse and note models sent:

```text
# a shell of the harbour office's site
SELECT "django_content_type"."id", "django_content_type"."app_label", "django_content_type"."model"
FROM "django_content_type"
WHERE (("django_content_type"."app_label" = 'fleet' AND "django_content_type"."model" IN ('port'))
    OR ("django_content_type"."app_label" = 'notes' AND "django_content_type"."model" IN ('note', 'lighthouse')))
```

`ContentTypeManager.get_for_id` and `get_by_natural_key` read the cache by key and by pair, and on a miss call `QuerySet.get`; neither makes a row. `get_for_id(9999)` raised `Model.DoesNotExist` and cached nothing, which its comment calls correct. The generic foreign key finds a note's content type with `get_for_id`; a deserializer finds one by its natural key with `get_by_natural_key`, as `PermissionManager.get_by_natural_key` does for a permission's (`django/contrib/auth/models.py:PermissionManager.get_by_natural_key`).

## Where the cache is wrong

The cache is never checked against the database and never expires, so a row deleted or a key changed behind its back is still answered. Django's `TestCase` rolls each test back, and the cache is not rolled back with it:

```text
# a shell of the harbour office's site: the logbook model's row is 17
inside transaction.atomic(), with that row deleted:
    ContentType.objects.get_for_model(Logbook)    makes row 27, and caches it
after the rollback:
    ContentType.objects.get_for_model(Logbook)    27, with no query; the database has 17, and no 27
    after clear_cache()                           17
```

A note given content type 27 names a row that does not exist; saved in autocommit, it failed on the foreign key's constraint: "FOREIGN KEY constraint failed". Since `ContentTypeManager.use_in_migrations` is true, the historical `ContentType` a migration is given has the manager too, but a new instance of it, with a dictionary of its own (`django/db/migrations/state.py:ModelState.construct_managers`). `create_contenttypes` ([Making content types: `create_contenttypes` and `RenameContentType`](making-content-types.md)) clears that of the `ContentType` in the registry it is given, before it reads the rows: flush gives it the project's own, and a flush emptied the process's cache; migrate gives it the historical registry, and a migrate called in the run left the process's cache as it was (`django/contrib/contenttypes/management/__init__.py:create_contenttypes`). The command remove_stale_contenttypes clears the process's cache before it reads. `RenameContentType` clears the historical manager's after a rename, because `get_by_natural_key` had cached the row under its old name. Django's documentation has a test call `clear_cache` in its set-up and again in a cleanup (`docs/ref/contrib/contenttypes.txt`).
