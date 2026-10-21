---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Generic foreign keys: `GenericForeignKey`

`GenericForeignKey` reads two ordinary fields of a model, a foreign key to `ContentType` and an object id, as one relation to a row of any model. It has no column; its descriptor, `GenericForeignKeyDescriptor`, reads and assigns the object, and fetches the objects of many rows with a query for each content type, which `GenericPrefetch` can replace.

A foreign key gets from the schema the table it points at, a constraint that keeps its column right, and a join that a filter or `select_related` can write. A generic foreign key has none of these, because its table differs from row to row: in a note of the harbour office the content type says which model, and the object id which row ([Content types, static files and the other contrib apps](../contrib.md) draws three). What a foreign key does with a model it knows, a generic key does by asking the content type for the model each time it loads an object; what a foreign key leaves to SQL, a generic key does in Python or not at all.

## A field without a column

`GenericForeignKey` is a `django.db.models.Field` with `FieldCacheMixin`, made with the names of the two fields it reads: `GenericForeignKey.ct_field`, `"content_type"` unless given, and `GenericForeignKey.fk_field`, `"object_id"`. It passes `editable=False`, so a model form leaves it out, and carries the flags of a relation to one object, `is_relation` and `many_to_one` (`django/contrib/contenttypes/fields.py:GenericForeignKey.__init__`).

`GenericForeignKey.contribute_to_class` registers it as a private field, in `Options.private_fields`, and puts a `GenericForeignKeyDescriptor` on the class under its name. `GenericForeignKey.get_attname_column` answers with no column, so the field is not concrete: it is in no table and no statement. Nor has it a `remote_field` or a `related_model`, and a relation to one object with no model at the other end is what `Options.fields` leaves out of its list (`django/db/models/options.py:Options.fields`). The object, once read, is kept in the instance's cache of related objects under `GenericForeignKey.cache_name`, the field's name ([Reading and setting related objects](../relations/related-objects.md#where-a-related-object-is-kept)).

Every content type the descriptor needs comes from `GenericForeignKey.get_content_type`: for an object, its model's content type on the object's database; for a key, `ContentTypeManager.get_for_id`; for a model class, `ContentTypeManager.get_for_model`; given none, a bare `Exception`. The two that start from a model pass `GenericForeignKey.for_concrete_model`: unless it is false, an object of a proxy model is stored under its concrete model's content type. All go through the manager's cache ([Content types: `ContentType` and its cache](content-types.md)).

## The checks

`Model._check_fields` checks a model's local and many-to-many fields, not its private ones (`django/db/models/base.py:Model._check_fields`). `ContentTypesConfig.ready` registers `check_generic_foreign_keys` instead, which finds each `GenericForeignKeyDescriptor` among a model class's own attributes and runs its field's `check` (`django/contrib/contenttypes/checks.py:check_generic_foreign_keys`). The field's name is checked as any field's, then the two fields it names (`django/contrib/contenttypes/fields.py:GenericForeignKey.check`):

| id | refused when |
|---|---|
| `"contenttypes.E001"` | the object id names no field of the model |
| `"contenttypes.E002"` | the content type names no field of the model |
| `"contenttypes.E003"` | the content type's field is not a `ForeignKey` |
| `"contenttypes.E004"` | it is a `ForeignKey` to another model than `ContentType` |
| `"contenttypes.E006"` | its `on_delete` is a database-level variant, such as `DB_CASCADE` |

*The errors of a generic key's check of its two fields. The object id's field is checked only for being there, not for its type.*

## Reading: `GenericForeignKeyDescriptor.__get__`

`GenericForeignKeyDescriptor.__get__` begins by reading the content type's key from the row, the foreign key's attribute content_type_id on a note, and not the content type itself (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.__get__`).

> **Why.** Reading the content type through its foreign key "might reload the same ContentType over and over", the comment says, citing ticket 5570; the key becomes a content type later through `get_for_id`, which, it says, has a global cache.

Then it looks in the instance's cache. A cached `None` is returned as it is. A cached object is returned if it still matches the row: its model's content type must have the row's content type key, and the row's object id, converted by the object's key field, must equal its key. Assigning to either field leaves the generic key's cache entry alone, so this comparison is what notices a change. In the run, in the default fetch mode, a second read of Endeavour's note sent nothing; with its object id set to 2, the next read sent a query and gave Beagle.

Otherwise the read goes to the instance's fetch mode, as a foreign key's does ([Deferred fields and the fetch modes](../instance/fetching.md#the-fetch-modes)). `GenericForeignKeyDescriptor.fetch_one` asks `ContentType.get_object_for_this_type` for the row, on the instance's database and through the model's base manager; a row that is gone gives `None`, cached like an object (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.fetch_one`). `GenericForeignKeyDescriptor.fetch_many`, which `FETCH_PEERS` calls for several peers, passes the peers with nothing cached to `prefetch_related_objects`. A note whose cached object no longer matches is not among them, and keeps its entry: in the run, among four notes read under `FETCH_PEERS`, Endeavour's note, its object id set to 2, still gave Endeavour with no query (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.fetch_many`). Under `FETCH_RAISE` the read raises `FieldFetchBlocked`: "Fetching of Note.content_object blocked."

> **Changed in 6.1.** The descriptor is a class of its own; until then the field was its own descriptor, as the field's docstring still says.

`GenericForeignKeyDescriptor.__set__` sets both fields from the object it is given, the content type by `get_content_type` and the object id from the object's key, and caches the object; `None` sets both to `None` and caches `None` (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.__set__`).

## Prefetching: a query for each content type

`GenericForeignKeyDescriptor.get_prefetch_querysets` makes the descriptor the generic key's prefetcher ([`prefetch_related`: related objects in a second query](../relations/prefetch.md)). It groups the instances' object ids by content type key, skipping a row where either is `None`. For each group it makes one queryset, `ContentType.get_all_objects_for_this_type` filtered by the group's keys, through the model's base manager, gives it the first instance's fetch mode, and evaluates it. It matches objects to instances by a pair, a key as text and a model class: for an object, its key field's `value_to_string` and its class; for an instance, its object id as a string and the model its content type names. Both must match, the comment says; as text, an object id kept in a text field meets an integer key (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.get_prefetch_querysets`).

With a fourth note, on the ship Beagle, reading the four notes' objects one by one sent five queries; with the prefetch, four, as under `FETCH_PEERS`:

```text
# notes: the four notes and their objects, with prefetch_related
notes = list(Note.objects.order_by("pk").prefetch_related("content_object"))

SELECT "notes_note"."id", "notes_note"."text", "notes_note"."added", "notes_note"."content_type_id", "notes_note"."object_id" FROM "notes_note" ORDER BY "notes_note"."id" ASC
SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."id" IN (1, 2) ORDER BY "fleet_ship"."name" ASC
SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."id" IN (1) ORDER BY "fleet_port"."name" ASC
SELECT "notes_lighthouse"."id", "notes_lighthouse"."name", "notes_lighthouse"."port_id" FROM "notes_lighthouse" WHERE "notes_lighthouse"."id" IN (1)
```

### `GenericPrefetch`

A `Prefetch` holds one queryset; a generic key needs one for each model. `GenericPrefetch` holds a list, refuses a queryset made by `raw`, `values` or `values_list` as `Prefetch` does, and hands the list to `get_prefetch_querysets` at the last level of its lookup (`django/contrib/contenttypes/prefetch.py:GenericPrefetch`). There each queryset is filed under its model's content type, a second for one content type raising `ValueError`, "Only one queryset is allowed for each content type.", and used, filtered by the group's keys, in place of the default. Given a `GenericPrefetch` with one queryset, of the ships of 300 tons or more, the ships' statement became `WHERE ("fleet_ship"."tonnage" >= 300 AND "fleet_ship"."id" IN (1, 2))`, and Beagle's note, its ship filtered out, had `None` cached.

## What a generic key cannot do

A filter, an exclude or an ordering through a generic key fails as the name is resolved: `Query.names_to_path` refuses a relation field without a related model, which its comment says "cannot generate reverse relations", so the message speaks of reverse querying even for a field of the note's own (`django/db/models/sql/query.py:Query.names_to_path`):

```text
# notes: Note.objects.filter(content_object=endeavour)
FieldError: Field 'content_object' does not generate an automatic reverse relation and therefore cannot be used for reverse querying. If it is a GenericForeignKey, consider adding a GenericRelation.
```

`select_related` walks the model's list of fields that leaves generic keys out, and refuses the name: "Invalid field name(s) given in select_related: 'content_object'. Choices are: content_type" (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`). A query for one object's notes filters on the two fields themselves.

Nor is the object id kept right: it has no constraint, and when the run deleted a ship, no statement touched the notes; the ship's note stayed, its object `None`. A `GenericRelation` on the model pointed at makes a delete reach the notes ([Generic relations: `GenericRelation` and generic inlines](generic-relation.md)).

## Filters for one object

`GenericForeignKey.get_filter_kwargs_for_object`, given a note, gives the filter for the rows on the same object, by the note's two values; `GenericForeignKey.get_forward_related_filter`, given the object, gives it by the object's key and content type. They serve `order_with_respect_to`, which may name a generic key: a new row takes the next number among the rows the first filter finds (`django/db/models/base.py:Model._save_table`), and the second serves the order accessors a `GenericRelation` adds to the other model (`django/db/models/base.py:method_get_order`, `django/db/models/base.py:method_set_order`).
