---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# PostgreSQL fields: `ArrayField`, the range fields and hstore

The model fields for PostgreSQL's own types, `ArrayField`, `django.contrib.postgres.fields.HStoreField` and the range fields: the column each names, how it prepares and validates a value, the lookups and transforms it registers, and the form fields and validators made for them.

PostgreSQL has arrays, ranges of numbers, dates and moments, and, from the hstore extension, maps of text keys to text values or nulls. psycopg converts each to and from Python, an hstore once its type is registered with psycopg ([The PostgreSQL application: `PostgresConfig`, operations and aggregates](postgres.md)). So these fields convert little: they name the column's type, hand an array's items to the field it is made of, validate, and give the ORM words for PostgreSQL's operators. Each is a `django.db.models.Field` and a `CheckPostgresInstalledMixin`, whose check fails while `django.contrib.postgres` is not installed (`django/contrib/postgres/utils.py:CheckPostgresInstalledMixin`). The lookups of these fields that write PostgreSQL's own operators are `PostgresOperatorLookup`s and write SQL in `as_postgresql` only: compiled for SQLite, `"crew__overlap"` raised `NotImplementedError` (`django/db/models/lookups.py:PostgresOperatorLookup.as_postgresql`). The SQL below was compiled for PostgreSQL with no server behind it.

## `ArrayField`: a field made of a field

`ArrayField` is given an instance of another field, `ArrayField.base_field`, and its column is that field's type with brackets after it: `"varchar(60)[]"` for the crew, `"varchar(60)[4]"` with `size=4` (`django/contrib/postgres/fields/array.py:ArrayField.db_type`). PostgreSQL does not enforce the size, the documentation says (`docs/ref/contrib/postgres/fields.txt`): only Django checks it, by the `ArrayMaxLengthValidator` that `ArrayField.__init__` adds.

On the way in, `ArrayField.get_db_prep_value` and `ArrayField.get_db_prep_save` hand each item of a list to the base field's method of the same name, and the list goes to the driver as one parameter, which `ArrayField.get_placeholder_sql` casts to the column's type (`django/contrib/postgres/fields/array.py:ArrayField.get_placeholder_sql`). A sailing from eight to noon on 20 October 2026, Malta time:

```text
Sailing(vessel="Calypso", window=(eight, noon), crew=["Nora", "Edda"], cargo={"salt": 40, "wine": None})

INSERT INTO "charts_sailing" ("vessel", "window", "crew", "cargo") VALUES (%s, %s::tstzrange, %s::varchar(60)[], %s)
params: ('Calypso', [2026-10-20 08:00:00+02:00, 2026-10-20 12:00:00+02:00), ['Nora', 'Edda'], {'salt': '40', 'wine': None})
```

On the way out `ArrayField.__init__` gives the field a `from_db_value`, `ArrayField._from_db_value`, which hands each item to the base field's, only when the base field has one, for performance, the comment says; otherwise the value stays as the driver gave it ([A field: the base class](../models/fields.md#out-of-a-row)). `ArrayField.to_python` and `ArrayField.value_to_string` read and write JSON for the serializers, each item through the base field, though `value_to_string` writes a `None` itself.

> **Changed in 6.1.** An item `None` in an array of `django.db.models.JSONField` is saved as SQL NULL, not JSON null: `ArrayField.get_db_prep_save` hands it to `JSONField.get_db_prep_save`, which returns `None` as it is (`django/db/models/fields/json.py:JSONField.get_db_prep_save`).

`ArrayField.check` refuses a related field as the base, `"postgres.E002"`, and gathers the base field's errors but `"postgres.E005"` into one `"postgres.E001"` and its warnings into one `"postgres.W004"` (`django/contrib/postgres/fields/array.py:ArrayField.check`). `ArrayField.validate` and `ArrayField.run_validators` run the base field's on each item and raise at the first that fails, its error rewritten by `prefix_validation_error` with the code `"item_invalid"` and the item's number: "Item 2 in the array did not validate: Ensure this value has at most 60 characters (it has 70)." (`django/contrib/postgres/utils.py:prefix_validation_error`). `ArrayField.validate` also refuses an array whose arrays differ in length.

## Lookups and transforms on an array

`"contains"` (`"@>"`), `"contained_by"` (`"<@"`), `"overlap"` (`"&&"`) and `"exact"` on an array are built on `ArrayRHSMixin`, which turns a list on the right, unless it holds only `None`, into an `"ARRAY[...]"` of `Value`s prepared by the base field, and casts the right side to the column's type either way (`django/contrib/postgres/fields/array.py:ArrayRHSMixin`). `"len"`, `ArrayLenTransform`, writes `"array_length"` inside a `"CASE"` that tells a NULL array from an empty one.

Any other name that is no lookup of the field goes to `ArrayField.get_transform` (`django/contrib/postgres/fields/array.py:ArrayField.get_transform`). A number is an index, made by `IndexTransformFactory` with one added, because PostgreSQL counts from one and the ORM, like Python, from zero. Two numbers joined by an underscore are a slice, made by `SliceTransformFactory` with one added to the start and not to the end; a slice too counts from zero, as Python does, the documentation says, so `"crew__0_2"` means the Python slice 0:2. An index's output field is the base field, whose lookups then apply; a slice's is the array. Any other name is refused, with `FieldError`.

```text
Sailing.objects.filter(crew__contains=["Nora"])
    WHERE "charts_sailing"."crew" @> (ARRAY[%s])::varchar(60)[]
    params: ('Nora',)
Sailing.objects.filter(crew__0__startswith="No")
    WHERE ("charts_sailing"."crew")[%s]::text LIKE %s
    params: (1, 'No%')
Sailing.objects.filter(crew__0_2=["Nora", "Edda"])
    WHERE ("charts_sailing"."crew")[%s:%s] = (ARRAY[%s, %s])::varchar(60)[]
    params: (1, 2, 'Nora', 'Edda')
```

## The hstore field: text keys, text values

`django.contrib.postgres.fields.HStoreField` is a column of the type `"hstore"`, which a database has once the extension is created in it, by the migration operation `HStoreExtension` or by hand. `HStoreField.get_prep_value` makes each key a string and each value a string or `None`, so `{"salt": 40}` is saved as `{'salt': '40'}`; `HStoreField.validate`, which converts nothing, refuses it: "The value of “salt” is not a string or null." (`django/contrib/postgres/fields/hstore.py:HStoreField.validate`).

It registers the lookups `"contains"`, `"contained_by"`, `"has_key"` (`"?"`), `"has_keys"` (`"?&"`) and `"has_any_keys"` (`"?|"`), and the transforms `"keys"` and `"values"`, written `"akeys"` and `"avals"`, whose arrays take an array's lookups. A name that is no lookup or transform of the field is a key: `HStoreField.get_transform` answers it with a `KeyTransformFactory`, whose transform writes `"->"` (`django/contrib/postgres/fields/hstore.py:HStoreField.get_transform`). So a mistyped lookup is no error but a key:

```text
Sailing.objects.filter(cargo__has_kye="salt")
    WHERE ("charts_sailing"."cargo" -> %s) = %s
    params: ('has_kye', 'salt')
```

## The range fields

`RangeField` is the base of `IntegerRangeField` (`"int4range"`), `BigIntegerRangeField` (`"int8range"`), `DecimalRangeField` (`"numrange"`), `DateTimeRangeField` (`"tstzrange"`) and `DateRangeField` (`"daterange"`), each naming the model field of its bounds, `base_field`, a `range_type` and a form field (`django/contrib/postgres/fields/ranges.py`). The range types are psycopg's, named in `django/db/backends/postgresql/psycopg_any.py`. `RangeField.get_prep_value` makes a range of a list or tuple of two bounds (`django/contrib/postgres/fields/ranges.py:RangeField.get_prep_value`), with `ContinuousRangeField.default_bounds` on `DecimalRangeField` and `DateTimeRangeField`: `"[)"` unless the field was made with one of the other three (`django/contrib/postgres/fields/ranges.py:ContinuousRangeField.get_prep_value`). The discrete fields refuse that argument with `TypeError`; PostgreSQL, the documentation says, returns a discrete range as `"[)"` whatever bounds it was saved with.

The lookups write the operators `RangeOperators` names: `"contains"`, `"contained_by"`, `"overlap"`, `"fully_lt"` (`"<<"`), `"fully_gt"` (`">>"`), `"not_lt"` (`"&>"`), `"not_gt"` (`"&<"`) and `"adjacent_to"` (`"-|-"`). `"contains"` also takes one value, which `RangeContains` casts to the bounds' field; on the date and datetime ranges `"contains"` is `DateTimeRangeContains` instead, which casts it to the bounds' column type (`django/contrib/postgres/fields/ranges.py:DateTimeRangeContains.as_postgresql`). The transforms `"startswith"` and `"endswith"` write `"lower"` and `"upper"`; `"isempty"`, `"lower_inc"`, `"lower_inf"`, `"upper_inc"` and `"upper_inf"` give a boolean.

`RangeContainedBy` asks the other question, a plain value in a range: importing the range fields' module registers it as `"contained_by"` on `models.DateField`, `models.DateTimeField`, `models.IntegerField`, `models.FloatField` and `models.DecimalField`, and it casts the range to the type `RangeContainedBy.type_mapping` gives the column (`django/contrib/postgres/fields/ranges.py:RangeContainedBy`). Here eight and noon are those hours of 20 October 2026, Malta time:

```text
Sailing.objects.filter(window__overlap=(eight, noon))
    WHERE "charts_sailing"."window" && %s
    params: ([2026-10-20 08:00:00+02:00, 2026-10-20 12:00:00+02:00),)
Sailing.objects.filter(window__contains=eight)
    WHERE "charts_sailing"."window" @> %s::timestamp with time zone
    params: (2026-10-20 08:00:00+02:00,)
Bulletin.objects.filter(published__contained_by=DateTimeTZRange(eight, noon))
    WHERE "notes_bulletin"."published" <@ %s::tstzrange
    params: ([2026-10-20 08:00:00+02:00, 2026-10-20 12:00:00+02:00),)
```

> **Trap.** `RangeContainedBy.get_prep_lookup` prepares the value with a bare `RangeField`, which has no range type: given a tuple, it raised `AttributeError`.

`RangeBoundary`, an expression that writes bounds such as `"'[)'"`, is for range functions, and `RangeOperators` for the operators of `ExclusionConstraint` as well as the lookups ([PostgreSQL indexes and `ExclusionConstraint`](postgres-indexes.md)).

## Form fields and validators

`ArrayField.formfield` gives a `SimpleArrayField` of the base field's form field, the size its maximum (`django/contrib/postgres/forms/array.py:SimpleArrayField`). It splits its text at a comma, or another delimiter, and its `to_python`, `validate` and `run_validators` each report every item that fails, where the model field stopped at the first. `SplitArrayField` draws as many inputs as its size, more for a longer value, by a `SplitArrayWidget`, and with `remove_trailing_nulls=True` drops empty ones at the end.

A range's form field is a `BaseRangeField`, a `MultiValueField` of two of the bounds' form fields drawn by a `RangeWidget` ([The built-in form fields](../forms/field-types.md)). `BaseRangeField.compress` refuses a start after the end and makes the range with the bounds `ContinuousRangeField.formfield` passed it, if any (`django/contrib/postgres/forms/ranges.py:BaseRangeField.compress`). The hstore form field reads a JSON dictionary from a `Textarea`.

```text
crew.formfield().clean("Nora," + "x" * 70 + "," + "y" * 61)  ->  ValidationError ['Item 2 in the array did not validate: Ensure this value has at most 60 characters (it has 70).', 'Item 3 in the array did not validate: Ensure this value has at most 60 characters (it has 61).']
window.formfield().clean(["2026-10-20 08:00", "2026-10-20 12:00"])  ->  [2026-10-20 08:00:00+02:00, 2026-10-20 12:00:00+02:00)
```

`django/contrib/postgres/validators.py` has validators of a list's length (`ArrayMaxLengthValidator`, `ArrayMinLengthValidator`), an hstore's keys (`KeysValidator`) and a range's bounds (`RangeMaxValueValidator`, `RangeMinValueValidator`, for which a missing bound is beyond any limit).

## The case-insensitive fields

`CICharField`, `CIEmailField` and `CITextField` remain only so that old migrations import (`django/contrib/postgres/fields/citext.py`). Each sets `django.db.models.Field.system_check_removed_details`, so a model that uses one fails its checks (`"fields.E905"` to `"fields.E907"`), as one with `django.contrib.postgres.fields.JSONField` does (`"fields.E904"`) ([The field classes](../models/field-types.md#classes-kept-so-that-old-migrations-load)).
