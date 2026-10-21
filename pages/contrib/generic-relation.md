---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Generic relations: `GenericRelation` and generic inlines

`GenericRelation` is the reverse of a generic foreign key, declared on the model the key points at: a field without a column that gives each instance a manager of the rows attached to it, lets a query join in both directions, and makes a delete take those rows with it. `generic_inlineformset_factory` and `GenericInlineModelAdmin` edit the same rows in a formset and in the admin.

A generic foreign key lies wholly on one side: nothing in a lighthouse's table records that the harbour office's notes point at it. A `GenericRelation` on the lighthouse model tells the ORM what the other side is to know: a join from the lighthouse's key to the note's object id, with the note's content type held to the lighthouse model's.

## The field: a `ForeignObject` turned round

`GenericRelation` is a `ForeignObject`, the relation by pairs of fields of which a foreign key is the simplest case ([Relations: a field, its rel and the class at the other end](../relations/fields.md)). `GenericRelation.__init__` passes the object id field as `from_fields` and no `to_fields`, and `GenericRelation.resolve_related_fields` adds the model's primary key when the relation's fields are first asked for. A comment calls the construct somewhat of an abuse of `ForeignObject`: the relation runs from the key to the object id, but its join is made the other way, as along a foreign key from the note, so the object id is the from-field (`django/contrib/contenttypes/fields.py:GenericRelation.__init__`).

The same method forces five options: `null=True` and `blank=True`, since, as its comment says, Django cannot enforce that a key on the other model points here; `editable=False`; `serialize=False`; and `on_delete=CASCADE`. That last is never read. `ForeignObject.__init__` uses its `on_delete` only to make a rel when it is given none, and `GenericRelation` gives it a `GenericRel`, made with `DO_NOTHING`, as the run found (`django/contrib/contenttypes/fields.py:GenericRel`). A delete reaches the notes another way, through `bulk_related_objects`.

The rest of the declaration is about the other side. `object_id_field="object_id"` and `content_type_field="content_type"`, the defaults, name the generic key's two fields on the note model; `for_concrete_model` says whether an instance of a proxy model is matched by its concrete model's content type, the default, or by its own ([Content types: `ContentType` and its cache](content-types.md)); `related_query_name` and `limit_choices_to` go to the rel. `GenericRelation.get_internal_type` gives `"ManyToManyField"`, a type none of Django's backends has a column type for.

`GenericRelation.contribute_to_class` joins the class with `private_only=True`, so the field is kept in `Options.private_fields`, as a `GenericForeignKey` is, and not among the local fields; and it puts a `ReverseGenericManyToOneDescriptor` under its name (`django/contrib/contenttypes/fields.py:GenericRelation.contribute_to_class`). A copy that a child inherits from a parent with a table gets no reverse relation ([Inheritance: abstract bases, parents with tables and proxies](../models/inheritance.md)). If the note model is ordered with respect to the matching generic key, the lighthouse model gets the two order methods a foreign key would give it (`django/db/models/base.py:make_foreign_order_accessors`). The field's check, `GenericRelation._check_generic_foreign_key_existence`, gives `"contenttypes.E004"` when the other model has no `GenericForeignKey` among its private fields with the same two field names.

## Joining in both directions

`GenericRelation.get_path_info` gives the one hop a query takes from the lighthouse to the note, made as the reverse of a foreign key is, with the rel as its join field; `GenericRelation.get_reverse_path_info` gives the hop back, with the field itself (`django/contrib/contenttypes/fields.py:GenericRelation.get_path_info`). When the object id belongs to a parent of the note model with a table, `GenericRelation._get_path_info_with_parent` joins that parent first, then the parent links down to the note model.

Either join pairs the note's object id with the lighthouse's key. The content type comes from `GenericRelation.get_extra_restriction`: an exact lookup of the note's content type column against the key of the lighthouse model's content type, which `Join.as_sql` adds to the ON clause in parentheses (`django/db/models/sql/datastructures.py:Join.as_sql`). A rel hands the question to its field with the two aliases swapped, so the condition falls on the note's table whichever way the join runs (`django/db/models/fields/reverse_related.py:ForeignObjectRel.get_extra_restriction`). From notes to lighthouses, the run compiled for SQLite:

```text
Note.objects.filter(lighthouse__name="St Elmo")

SELECT "notes_note"."id", "notes_note"."text", "notes_note"."added", "notes_note"."content_type_id", "notes_note"."object_id"
FROM "notes_note"
INNER JOIN "notes_lighthouse" ON ("notes_note"."object_id" = "notes_lighthouse"."id"
                                  AND ("notes_note"."content_type_id" = %s))
WHERE "notes_lighthouse"."name" = %s
params: (21, 'St Elmo')
```

The name lighthouse is the `related_query_name`. `GenericRel` takes it for its related name too, so the note model also gets an attribute of that name, a manager of the lighthouses, set as for the other end of any `ForeignObject` (`django/db/models/fields/related.py:ForeignObject.contribute_to_related_class`). Without it, the rel's related name is `"+"`, which hides the relation, and the note model gets no attribute.

## The manager of a lighthouse's notes

`ReverseGenericManyToOneDescriptor` is the reverse descriptor of a foreign key with another manager class: `create_generic_related_manager` subclasses the note model's default manager's class (`django/contrib/contenttypes/fields.py:ReverseGenericManyToOneDescriptor.related_manager_cls`). The manager made for one lighthouse looks up its content type, on the lighthouse's database and by `for_concrete_model`, and keeps a filter of the two fields. Its queryset is what `prefetch_related` left on the lighthouse, if anything, and otherwise the default manager's, filtered so, in the lighthouse's fetch mode ([Deferred fields and the fetch modes](../instance/fetching.md)) (`django/contrib/contenttypes/fields.py:create_generic_related_manager`).

Its methods that change the set:

- `add` takes saved notes only by default: it refuses an object of another model with `TypeError` and an unsaved one, or one of another database, with `ValueError`, and sends one UPDATE of both fields. With `bulk=False` it sets them on each note and saves it, in one transaction.
- `remove` and `clear` delete the notes: by `QuerySet.delete`, or with `bulk=False` one by one in a transaction. `remove` filters the set by the keys it is given, so a note attached elsewhere is left alone.
- `set`, in one transaction, removes what is not wanted and adds what is missing, or with `clear=True` clears and adds everything.
- `create`, `get_or_create` and `update_or_create` put the content type and the object id into the arguments and call the method of that name on the manager's queryset, on the database for writes.

The reverse manager of a foreign key does otherwise: its `remove` and `clear` set the key to null, and exist only where the key may be null ([Reading and setting related objects](../relations/related-objects.md)). The run sent, for St Elmo, with hull the note on Endeavour:

```text
st_elmo.notes.create(text="Fog signal tested", added=...)
    INSERT INTO "notes_note" ("text", "added", "content_type_id", "object_id") VALUES ('Fog signal tested', '2026-10-15 07:00:00', 21, 1) RETURNING "notes_note"."id"
st_elmo.notes.add(hull)
    UPDATE "notes_note" SET "content_type_id" = 21, "object_id" = 1 WHERE "notes_note"."id" IN (1)
st_elmo.notes.remove(hull)
    BEGIN
    DELETE FROM "notes_note" WHERE ("notes_note"."content_type_id" = 21 AND "notes_note"."object_id" = 1 AND "notes_note"."id" IN (1))
    COMMIT
```

The hull note was deleted. A `remove` of the note on Valletta sent the same DELETE with that note's key, and the note stayed. For `prefetch_related("notes")` the manager filters by the content type and keys of each group of lighthouses that share a content type, and matches notes to lighthouses by the pair of object id and content type ([`prefetch_related`: related objects in a second query](../relations/prefetch.md)).

## Deleting

Deleting a lighthouse deletes its notes. `Collector.collect` asks each private field of the model that has a `bulk_related_objects` for more rows, and collects them in turn (`django/db/models/deletion.py:Collector.collect`); the same attribute stops `Collector.can_fast_delete` letting the lighthouses be deleted unseen ([Deleting: the `Collector`](../instance/deleting.md)). `GenericRelation.bulk_related_objects` answers with the note model's base manager on the collector's database, filtered by the content type's key and the keys being deleted (`django/contrib/contenttypes/fields.py:GenericRelation.bulk_related_objects`). St Elmo's delete:

```text
st_elmo.delete()  ->  (3, {'notes.Note': 2, 'notes.Lighthouse': 1})
    BEGIN
    DELETE FROM "notes_note" WHERE ("notes_note"."content_type_id" = 21 AND "notes_note"."object_id" IN (1))
    DELETE FROM "notes_lighthouse" WHERE "notes_lighthouse"."id" IN (1)
    COMMIT
```

## Generic inlines

`BaseGenericInlineFormSet` is a model formset of the rows attached to one object, as an inline formset is of the rows whose foreign key names one parent ([Model formsets and inline formsets](../forms/model-formsets.md)). `generic_inlineformset_factory` takes the note model and the names of its two fields; it refuses a content type field that is not a foreign key to `ContentType` with a bare `Exception`, excludes both fields from the forms, makes the class with `modelformset_factory`, and sets the two fields and `for_concrete_model` on it (`django/contrib/contenttypes/forms.py:generic_inlineformset_factory`). Made with an instance, the formset's queryset is the notes of the default manager, or of the queryset it is given, for the instance's content type and key, or none for an instance without a key, and `BaseGenericInlineFormSet.save_new` sets the two fields on each new note (`django/contrib/contenttypes/forms.py:BaseGenericInlineFormSet`). For St Elmo, before its delete, the formset's prefix, then each form's prefix, fields and note's key:

```text
NoteFormSet = generic_inlineformset_factory(Note, fields=["text", "added"], extra=1)
NoteFormSet(instance=st_elmo)

prefix: notes-note-content_type-object_id
   notes-note-content_type-object_id-0 ['text', 'added', 'id', 'DELETE'] 3
   notes-note-content_type-object_id-1 ['text', 'added', 'id', 'DELETE'] 4
   notes-note-content_type-object_id-2 ['text', 'added', 'id', 'DELETE'] None
```

> **Trap.** The queryset uses the content type that `for_concrete_model` gives; `save_new` calls `ContentTypeManager.get_for_model` without it. With `for_concrete_model=False` and an instance of a proxy model, a run's new note was saved under the concrete model's content type, and the formset then did not list it.

`GenericInlineModelAdmin` is the admin's inline for such rows, and `GenericStackedInline` and `GenericTabularInline` differ from it only in their template. `GenericInlineModelAdmin.get_formset` reads the same hooks as `InlineModelAdmin.get_formset` and calls `generic_inlineformset_factory` with `ct_field` and `ct_fk_field` where the other names a foreign key; its form ignores changes the user may not make, but lacks the other's refusal to delete a row that protected objects point at (`django/contrib/contenttypes/admin.py:GenericInlineModelAdmin.get_formset`) ([Inlines: `InlineModelAdmin` and its formsets](../admin/inlines.md)). `GenericInlineModelAdminChecks` replaces the check of the foreign key with one that the model has a `GenericForeignKey` on the two named fields, `"admin.E301"` to `"admin.E304"` (`django/contrib/contenttypes/admin.py:GenericInlineModelAdminChecks._check_relation`).
