---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Serialization: `serialize`, `deserialize` and `DeserializedObject`

`serialize` writes model instances out in a named format, as text in `"json"`, `"jsonl"`, `"xml"` or `"yaml"`, or as lists and dictionaries in the internal `"python"`, and `deserialize` reads the text back as instances not yet saved, each held in a `DeserializedObject` whose save writes the row raw (`django/core/serializers/__init__.py`).

A serializer has to write a row so that it can be read back into the same row, perhaps in another database; a deserializer builds the instance from what was written, to be saved without calling the model's own `save`. The dumpdata and loaddata commands are built on the two ([Fixtures: dumpdata and loaddata](fixtures.md)).

## The registry of formats

Each format is a module with a `Serializer` and a `Deserializer` class (`django/core/serializers/base.py:Serializer`, `django/core/serializers/base.py:Deserializer`); a built-in one is named by its dotted path in `BUILTIN_SERIALIZERS`. The registry, `_serializers`, stays empty until it is first needed; then `_load_serializers` registers the built-in formats and after them those of `SERIALIZATION_MODULES`, a setting with no default, which may add a format or replace one. The docstring's reason for waiting: a project can set up its settings without minding the order of imports (`django/core/serializers/__init__.py:_load_serializers`).

`register_serializer` imports a format's module; if the import raises `ImportError`, it registers a stand-in whose serializer and deserializer are one `BadSerializer` holding the exception, which raises it when called, so that, the docstring says, the error reaches whoever uses the format (`django/core/serializers/__init__.py:register_serializer`). So without PyYAML, `"yaml"` is still listed, and fails when used. `get_serializer` raises `SerializerDoesNotExist` for an unknown format, and `get_public_serializer_formats` leaves out a format whose serializer has `Serializer.internal_use_only` true, of the built-in ones only the Python one; dumpdata refuses those. `serialize` runs a serializer and returns its `Serializer.getvalue`; `deserialize` returns the deserializer itself, an iterator (`django/core/serializers/__init__.py:serialize`, `django/core/serializers/__init__.py:deserialize`).

## One walk over the fields

`Serializer.serialize` is the same for every format Django ships; a format supplies the hooks it calls as it starts, at the start and the end of each instance, for each field, and as it ends (`django/core/serializers/base.py:Serializer.serialize`). It takes any iterable of instances.

The fields are the local fields of the instance's concrete model, so a proxy, which has none of its own, is written with those of the model it stands for; the comment cites ticket 17717. A field made with `serialize=False` is skipped, and the model's options turn that flag off on the primary key, which is written apart (`django/db/models/options.py:Options.setup_pk`). Under `use_natural_primary_keys=True` a multi-table child's link to its parent is kept all the same, since, the comment says, the record could not be read back without it. A child's parent fields are not local to it: they are the parent's own record (`docs/topics/serialization.txt`).

A field that is not a relation goes to `Serializer.handle_field`, a foreign key or a one-to-one to `Serializer.handle_fk_field`, and then each many-to-many field to `Serializer.handle_m2m_field`. Given `fields=`, it keeps only the fields named.

## The Python serializer: a dictionary for each object

The Python serializer builds a list of dictionaries, and the JSON, JSON Lines and YAML serializers are built on it. `Serializer.get_dump_object` makes each from `"model"`, the model's label in lower case, `"pk"`, and `"fields"`, the values by field name (`django/core/serializers/python.py:Serializer.get_dump_object`). A value of a type that `is_protected_type` names, none, an integer, a float, a decimal, a date, a time or a datetime, is kept as it is. Any other, a string or a UUID among them, is written as what the field's `value_to_string` makes of it, which the field's `to_python` reads back ([A field: the base class](../models/fields.md)) (`django/db/models/fields/__init__.py:Field.value_to_string`). A composite primary key is written as a list.

A foreign key is written as its column's value. A many-to-many field, written only when its through model was made automatically, is the list of the related keys, in the related model's ordering with the key added where that order is not total (`django/core/serializers/python.py:Serializer.handle_m2m_field`). Endeavour's voyage, in JSON:

```text
serialize("json", Voyage.objects.all())
[{"model": "fleet.voyage", "pk": 1, "fields": {"ship": 1, "sailed": "2026-10-12", "calls": [2]}}]
```

The date went into the dictionary as a date, and the JSON encoder wrote it.

## Natural keys

A **natural key** is a tuple of values that identifies a row without its primary key: a model gives it by a `natural_key` method, and its default manager finds the row again by `get_by_natural_key`. The documentation's reason is the rows Django makes itself, such as content types, whose keys depend on when they were made (`docs/topics/serialization.txt`). With `use_natural_foreign_keys=True` a relation to a model with `natural_key` is written as the related object's natural key, and with `use_natural_primary_keys=True` an object with a natural key is written without `"pk"` (`django/core/serializers/python.py:Serializer.handle_fk_field`). For this run, Port was given a `natural_key` method returning its name, and its default manager a `get_by_natural_key` that finds a port by name:

```text
serialize("json", Ship.objects.filter(name="Beagle"), use_natural_foreign_keys=True)
[{"model": "fleet.ship", "pk": 2, "fields": {"name": "Beagle", "tonnage": 235, "home": ["Valletta"], "captain": null}}]

serialize("json", Port.objects.filter(name="Valletta"), use_natural_primary_keys=True)
[{"model": "fleet.port", "fields": {"name": "Valletta", "country": "Malta"}}]
```

> **Changed in 6.1.** A `natural_key` that returns `()` opts out, and the key is written in its place: with Port's returning `()`, Beagle's home is 1 again (`docs/releases/6.1.txt`).

## The formats

The JSON serializer writes each object's dictionary as the object ends, passing its remaining options, such as `indent=2`, to the json module's dump (`django/core/serializers/json.py:Serializer.end_object`), with `DjangoJSONEncoder` and `ensure_ascii=False` unless they say otherwise (`django/core/serializers/json.py:Serializer._init_options`). The encoder writes a datetime in ISO 8601 to the millisecond, or to the second where the milliseconds are zero, with `"Z"` for an offset of zero; a date; a time, refusing one with a zone; a duration in ISO 8601; and a decimal, a UUID or a lazy string as its string (`django/core/serializers/json.py:DjangoJSONEncoder.default`).

> **Changed in 6.2.** Where the milliseconds of a datetime or a time are zero, `DjangoJSONEncoder` wrote `".000"` before (`docs/releases/6.2.txt`).

The JSON Lines serializer writes one object to a line. The YAML serializer needs PyYAML, and dumps the whole list at the end with `DjangoSafeDumper`, which writes decimals and times as strings; the comment says a time tagged as Python's could be read in no other language (`django/core/serializers/pyyaml.py:DjangoSafeDumper`).

The XML serializer is built on the base class, and writes an `<object>` element for each instance and in it a `<field>` for each field (`django/core/serializers/xml_serializer.py:Serializer`). Its deserializer parses with `DefusedExpatParser`, which refuses a document type declaration, an entity declaration and an external reference (`django/core/serializers/xml_serializer.py:DefusedExpatParser`).

> **Changed in 6.1.** The XML deserializer raises `SuspiciousOperation` when a field's text holds an element with content of its own (`django/core/serializers/xml_serializer.py:check_element_type`).

## Reading back: the Python deserializer

The JSON and YAML deserializers parse the whole text, and the JSON Lines one a line at a time; each hands the Python objects to the Python deserializer, an iterator that makes a record into an object only when the iteration reaches it (`django/core/serializers/python.py:Deserializer._handle_object`):

1. The model, from `"model"`, by `Apps.get_model`. An unknown one raises `DeserializationError`, or with `ignorenonexistent=True` the record is skipped.
2. The key, where there is a `"pk"`, through the key field's `to_python`.
3. Each field by name, a name the model lacks skipped under `ignorenonexistent=True`. A many-to-many value goes to `deserialize_m2m_values`, a foreign key's to `deserialize_fk_value`, any other through `to_python`. A value that fails raises `DeserializationError.WithData`, naming the model, the key and the value.
4. The instance, from `build_instance`, held in a `DeserializedObject` with the many-to-many values and the deferred fields.

The XML deserializer has code of its own for these steps.

`deserialize_fk_value` reads a list, or any iterable but a string, as a natural key, where the related model's default manager has `get_by_natural_key`, and looks the object up on the deserializer's database, given by `using=`. Any other value goes through the target field's `to_python` and is not looked up (`django/core/serializers/base.py:deserialize_fk_value`). `deserialize_m2m_values` does the same for each value of a list. So only a natural key can be a **forward reference**, to an object not yet saved. With `handle_forward_references=True` such a field is set aside as deferred, marked by `DEFER_FIELD`; without it, the missing object is an error.

`build_instance` makes the instance with the model's constructor. Where the data has no primary key, the model has `natural_key` and its default manager `get_by_natural_key`, it first asks a provisional instance for its natural key and looks the row up; if the row is there, its key goes into the data, and a save then updates that row (`django/core/serializers/base.py:build_instance`). Read back, Valletta's record written without `"pk"` gets Valletta's key, 1.

## A raw save: `DeserializedObject.save`

`DeserializedObject.save` calls the base class's `Model.save_base` on `DeserializedObject.object` with `raw=True`, which, the comment says, bypasses any save the model defines (`django/core/serializers/base.py:DeserializedObject.save`). A raw save writes the values the instance holds without asking its fields for their own, saves no parent, and passes `raw=True` to `pre_save` and `post_save` ([Saving an instance](../models/saving.md)), which tells a receiver, the documentation says, to leave other rows alone, as the database may not be consistent yet (`docs/ref/signals.txt`, [The signals Django sends](builtin-signals.md)). Then each many-to-many relation is set by `set_base` with `raw=True`, which `m2m_changed` passes on ([Many-to-many relations](../models/many-to-many.md)), and the many-to-many values are emptied so that, the comment says, a second call does not save them twice. Endeavour's record read back, its tonnage set to 370 and saved, with a receiver of both signals and the SQL printed:

```text
<DeserializedObject: fleet.Ship(pk=1)>, still being added: True
  pre_save for Ship, raw=True
  UPDATE "fleet_ship" SET "name" = %s, "tonnage" = %s, "home_id" = %s, "captain_id" = %s WHERE "fleet_ship"."id" = %s
  post_save for Ship, raw=True, created=False
```

The record had a key, so the save tried an update, found the row and inserted nothing. It writes to the database given by `using=`, or the router's choice.

`DeserializedObject.save_deferred_fields` is the second pass: it looks each deferred value up again, raising now if the object is still missing, sets it, and saves again (`django/core/serializers/base.py:DeserializedObject.save_deferred_fields`). loaddata saves every object first and makes this pass at the end ([Fixtures: dumpdata and loaddata](fixtures.md)); a foreign key deferred so must accept null for the first save (`docs/topics/serialization.txt`).
