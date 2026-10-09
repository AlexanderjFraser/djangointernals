---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The field classes

The classes built on `django.db.models.fields.Field`, from `IntegerField` and `CharField` to `GeneratedField` and `CompositePrimaryKey`, each change a small part of what the base class does: the internal type that picks the column, what `to_python` makes of a value, how a value is prepared for a backend. They are taken here by the kind of change each makes, after a table of them all.

A field class is a short list of overrides. The base class does the general work ([A field: the base class](fields.md)), and a subclass says what is particular to one kind of value, which for the common kinds comes to the same few methods: `get_internal_type` for the column, `to_python` for a value from outside, `get_prep_value` and `get_db_prep_value` for a value on its way into a statement, and `formfield`. A class with arguments of its own adds them to `deconstruct`, and one with mistakes of its own to catch adds to `check` ([The model checks](checks.md)).

A few of the classes differ in kind and not in detail. `GeneratedField` has a column that Django never writes, and `CompositePrimaryKey` has no column at all. The fields for files and for relations have pages of their own ([File fields](files.md), [Relations: a field, its rel and the class at the other end](relations.md)).

## The classes, to look up

The table has the field classes of `django.db.models` that a model is written with, most of them from one module and the rest from its neighbours (`django/db/models/fields/__init__.py`, `django/db/models/fields/files.py`, `django/db/models/fields/json.py`, `django/db/models/fields/related.py`, `django/db/models/fields/generated.py`, `django/db/models/fields/composite.py`). Each of them answers `get_internal_type` with its own name, except `EmailField` and `URLField`, which answer `"CharField"`, `ImageField`, which answers `"FileField"`, and `GeneratedField`, which gives its output field's. The column type is the one SQLite's backend gave when the class was asked in a recording, and it is that backend's alone: where SQLite has `"bool"`, `"char(32)"` and `"bigint"` for a boolean, a UUID and a duration, PostgreSQL has `"boolean"`, `"uuid"` and `"interval"` ([Column types: from a field to a column](../backends/column-types.md#the-column-of-each-field-class-on-each-backend)).

| class | column on SQLite | what `to_python` returns |
|---|---|---|
| `AutoField` | `"integer"` | an `int` |
| `BigAutoField` | `"integer"` | an `int` |
| `SmallAutoField` | `"integer"` | an `int` |
| `SmallIntegerField` | `"smallint"` | an `int` |
| `IntegerField` | `"integer"` | an `int` |
| `BigIntegerField` | `"bigint"` | an `int` |
| `PositiveSmallIntegerField` | `"smallint unsigned"`, with a check that it is 0 or more | an `int` |
| `PositiveIntegerField` | `"integer unsigned"`, with the same check | an `int` |
| `PositiveBigIntegerField` | `"bigint unsigned"`, with the same check | an `int` |
| `FloatField` | `"real"` | a `float` |
| `DecimalField` | `"decimal"` | a `decimal.Decimal` |
| `BooleanField` | `"bool"` | `True` or `False` |
| `CharField` | `"varchar(60)"` for a `max_length` of 60, `"varchar"` for none | a `str` |
| `SlugField` | `"varchar(50)"` | a `str` |
| `EmailField` | `"varchar(254)"` | a `str` |
| `URLField` | `"varchar(200)"` | a `str` |
| `TextField` | `"text"` | a `str` |
| `FilePathField` | `"varchar(100)"` | the value, unchanged |
| `GenericIPAddressField` | `"char(39)"` | a `str` with white space stripped, and an IPv6 address in one spelling |
| `DateField` | `"date"` | a `datetime.date` |
| `TimeField` | `"time"` | a `datetime.time` |
| `DateTimeField` | `"datetime"` | a `datetime.datetime` |
| `DurationField` | `"bigint"` | a `datetime.timedelta` |
| `UUIDField` | `"char(32)"` | a `uuid.UUID` |
| `BinaryField` | `"BLOB"` | the value, unchanged, except that a `str` is read as base64 into a `memoryview` |
| `JSONField` | `"text"`, with a check that it is valid JSON or null | the value, unchanged |
| `FileField` | `"varchar(100)"` | the value, unchanged |
| `ImageField` | `"varchar(100)"` | the value, unchanged |
| `ForeignKey`, `OneToOneField` | what the field pointed at answers as `rel_db_type`: `"bigint"` for a `BigAutoField` | what the field pointed at returns |
| `GeneratedField` | its output field's type; no check was recorded | the value, unchanged |
| `ManyToManyField`, `CompositePrimaryKey` | none | the value, unchanged, except that `CompositePrimaryKey` reads a `str` as a JSON list and gives each part to its own field's `to_python` |

*The field classes a model is written with, by what distinguishes each. The column types are SQLite's, as recorded; another backend has its own.*

Every one of them returns `None` for `None`, except a `BooleanField` that is not nullable, which refuses it. Asked of a running Django:

```text recording=models
models.IntegerField().to_python('7'), models.IntegerField().to_python(None)  ->  (7, None)
models.IntegerField().to_python('seven')  ->  raises ValidationError: ['“seven” value must be an integer.']
models.BooleanField().to_python('t'), models.BooleanField().to_python('0')  ->  (True, False)
```

The value a field prepares for a statement is converted in much the same way, since for most of these classes `get_prep_value` calls `to_python` or the same constructor, and `get_db_prep_value` then adds what the backend wants. On SQLite a JSON value is sent as a string, and a UUID as 32 hexadecimal digits:

```text recording=models
models.JSONField().get_db_prep_value({'crates': 12}, connection)  ->  '{"crates": 12}'
models.UUIDField().get_db_prep_value(models.UUIDField().to_python('c0ffee00-0000-4000-8000-000000000001'), connection)  ->  'c0ffee00000040008000000000000001'
```

## Integers

`IntegerField` converts with `int`, in two places and with two kinds of error (`django/db/models/fields/__init__.py:IntegerField`). `IntegerField.to_python` raises `ValidationError` for a value `int` will not take. `IntegerField.get_prep_value`, on the way into a statement, raises again the `TypeError` or `ValueError` that `int` raised, with a message that names the field. The other integer classes change the internal type, and with it the column and, for the three positive ones on SQLite, the check that the backend's dictionary of checks has for them (`django/db/backends/sqlite3/base.py:DatabaseWrapper`).

None of that keeps a value within the column's range before the database sees it. Two validators do, and they are not made when the field is. `IntegerField.validators` is put together the first time it is read, and its comment gives the reason: the validators are based on values retrieved from the connection. It asks `BaseDatabaseOperations.integer_field_range` for the least and the greatest value of the field's internal type and adds a `MinValueValidator` and a `MaxValueValidator` for them, leaving either out where the field was given a validator of that kind that is at least as strict (`django/db/models/fields/__init__.py:IntegerField.validators`, `django/db/backends/base/operations.py:BaseDatabaseOperations.integer_field_range`). The connection it asks is the default one, whichever database the model's table is in.

The base class of the backends answers from a table of the usual sizes, 32,767 at most for a `SmallIntegerField` and 2,147,483,647 for an `IntegerField`. SQLite's backend overrides the method to answer with 64 bits for every type, its comment being that SQLite does not enforce integer constraints (`django/db/backends/sqlite3/operations.py:DatabaseOperations.integer_field_range`). So the `PositiveIntegerField` of Ship, in the recording, takes anything from 0 to the greatest 64-bit integer:

```text recording=models
[(type(v).__name__, v.limit_value) for v in Ship._meta.get_field('tonnage').validators]  ->  [('MinValueValidator', 0), ('MaxValueValidator', 9223372036854775807)]
```

The three positive classes share `PositiveIntegerRelDbTypeMixin`, which answers `rel_db_type`, the type of a column that points at the field. A foreign key to a positive integer gets the plain integer type of the same size, unless the backend's `BaseDatabaseFeatures.related_fields_match_type` says that a foreign key must have exactly the type of its target.

## The automatic keys: `AutoField` and `AutoFieldMeta`

An automatic key is an integer field with `AutoFieldMixin` in front of it: `AutoField` is the mixin and `IntegerField`, `BigAutoField` the mixin and `BigIntegerField`, `SmallAutoField` the mixin and `SmallIntegerField` (`django/db/models/fields/__init__.py:AutoFieldMixin`). The database produces the number. What the mixin does is let a field have no value until the row is inserted, and get the number back afterwards.

So `AutoFieldMixin.__init__` makes the field blank, and `Model.clean_fields` passes over a blank field whose value is empty, which is how an instance with no key yet passes validation. `AutoFieldMixin.validate` does nothing. `AutoFieldMixin.formfield` returns `None` in place of a form field. `AutoFieldMixin.contribute_to_class` records the field as `Options.auto_field`, refusing a second on one model, and a save reads that to leave the column out of an insert when the key is not set (`django/db/models/fields/__init__.py:AutoFieldMixin.contribute_to_class`, `django/db/models/base.py:Model._save_table`). `AutoFieldMixin.db_returning` is true, so the number the database chose is asked back from the insert ([Saving an instance](saving.md)). And where a value is written, `AutoFieldMixin.get_db_prep_save` passes it through the backend's `validate_autopk_value`, whose docstring says that certain backends do not accept some values for such a field, and gives zero in MySQL as the example.

A model that declares no primary key, and has no parent with a table to take one from, is given an automatic one by `Options._prepare`, of the class that `Options._get_default_pk_class` returns ([The options: what a model keeps as `_meta`](options.md)).

`BigAutoField` does not inherit from `AutoField`, and `isinstance` says that it does:

```text recording=models
isinstance(models.BigAutoField(primary_key=True), models.AutoField)  ->  True
issubclass(models.SmallAutoField, models.AutoField), issubclass(models.IntegerField, models.AutoField)  ->  (True, False)
[c.__name__ for c in models.BigAutoField.__mro__]  ->  ['BigAutoField', 'AutoFieldMixin', 'BigIntegerField', 'IntegerField', 'Field', 'RegisterLookupMixin', 'object']
...
type(models.AutoField).__name__, type(models.BigAutoField).__name__  ->  ('AutoFieldMeta', 'type')
```

`AutoField` alone is declared with a metaclass, `AutoFieldMeta`, whose `__instancecheck__` and `__subclasscheck__` answer yes for `BigAutoField` and `SmallAutoField`, and for classes built on those, as well as for what really inherits from `AutoField` (`django/db/models/fields/__init__.py:AutoFieldMeta`). One caller that leans on it is `Options._get_default_pk_class`. Having imported the class that the setting or the app config names, it raises `ValueError` unless `issubclass` says the class is an `AutoField`, and for `BigAutoField`, the default, that is true by the metaclass and by nothing else (`django/db/models/options.py:Options._get_default_pk_class`). The docstring of `AutoFieldMeta` calls it a way to maintain backward inheritance compatibility. Many areas of Django, it says, use `isinstance` against `AutoField` to tell an automatically generated field, and a new flag on `Field` needs to be implemented to be used instead.

> **Changed in 6.0.** `settings.DEFAULT_AUTO_FIELD` is `"django.db.models.BigAutoField"` unless a project sets it. It was `"django.db.models.AutoField"` before.

## Booleans

`BooleanField` reads more than booleans as booleans, and by one rule wherever a value arrives (`django/db/models/fields/__init__.py:BooleanField.to_python`). `BooleanField.to_python` takes `True`, `False`, 1 and 0, the strings `"t"`, `"True"`, `"1"`, `"f"`, `"False"` and `"0"`, and, for a nullable field, an empty value, which it returns as `None`. It raises `ValidationError` for anything else. `BooleanField.get_prep_value` passes every value but `None` through it, so a value given to a filter is read by the same rule and refused with the same exception. In a form a field with no choices is a checkbox when it is not nullable and a three-way select when it is, and for both `BooleanField.formfield` makes the form field not required, its comment being that for a checkbox, required means that it must be checked.

## Text

`CharField` is a field with a length (`django/db/models/fields/__init__.py:CharField`). Its `__init__` appends a `MaxLengthValidator` when a `max_length` was given, and takes one argument of its own, `db_collation`, which its `db_parameters` hands on to the schema editor. `CharField.get_prep_value` goes through `CharField.to_python`, so a number given where a string is wanted is stored as its digits.

The length may be left out, on some databases. Nothing in `__init__` requires it. A check does, `CharField._check_max_length_attribute`, and it lets a field without one pass where the default connection's `BaseDatabaseFeatures.supports_unlimited_charfield` is true, or where the model's `Meta` lists that feature as required ([The model checks](checks.md)). SQLite's is true, and its dictionary of types answers for a `CharField` with a function, which returns `"varchar"` alone for a field with no length (`django/db/backends/sqlite3/base.py:_get_varchar_column`).

`TextField` converts values in the same way and has no validator of length: a `max_length` given to it reaches the form field and not the column. Its form field is drawn as a `Textarea`, unless the field has choices.

Three classes are a `CharField` with a validator and a length of their own: `SlugField` has `validate_slug`, or `validate_unicode_slug` when made with `allow_unicode=True`, and an index unless told otherwise, `EmailField` has `validate_email`, and `URLField` has a `URLValidator`. `SlugField` declares an internal type of its own. The other two declare none, inherit `CharField`'s answer, and are to the database a `CharField` and nothing more. The validator is all that makes the value of an `EmailField` an address, and a validator runs when an instance is cleaned, not when it is saved ([Validating an instance](validation.md)).

## Dates and times

`DateField`, `DateTimeField` and `TimeField` have two arguments and a mixin in common (`django/db/models/fields/__init__.py:DateField`). `DateTimeField` inherits from `DateField`. `TimeField` stands apart, on `Field`, and repeats the same `__init__`. The mixin, `DateTimeCheckMixin`, adds two checks ([The model checks](checks.md)).

**A date that sets itself.** The two arguments are `auto_now` and `auto_now_add`. A field made with either is made not editable and blank by its `__init__`, so a `ModelForm` leaves it out and validation passes over it when it is empty, and its value comes from `pre_save` (`django/forms/models.py:fields_for_model`). With `auto_now`, or with `auto_now_add` when the row is being inserted, `pre_save` takes the present moment, sets it on the instance and returns it, and whatever the instance held is ignored. `DateField.pre_save` takes it from `datetime.date.today`, `DateTimeField.pre_save` from `django.utils.timezone.now`, and `TimeField.pre_save` from `datetime.datetime.now`. The crew's Sailor has such a field, `"signed_on"`, made with `auto_now_add=True`. These are the two calls of its `pre_save` in a new sailor's save:

```text recording=models
Model.save()  (a Sailor)
  DateTimeField.pre_save(add=True)  (Sailor.signed_on)  ->  datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
...
  SQLInsertCompiler.pre_save_val(Sailor.signed_on)
    DateTimeField.pre_save(add=True)  (Sailor.signed_on)  ->  datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
    -> datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
```

This insert called `pre_save` twice for the field ([Saving an instance](saving.md)). Each call takes the time afresh and sets the instance's attribute, and the second supplies the value that is written, so the instance and the row agree. When the same sailor is saved again the row is updated, the argument is false, and the field does nothing of its own: the call falls through to the base class's, which returns what the instance holds.

```text recording=models
DateTimeField.pre_save(add=False)  (Sailor.signed_on)
  DateField.pre_save(add=False)  (Sailor.signed_on)
    Field.pre_save(add=False)  (Sailor.signed_on)  ->  datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
    -> datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
```

A field made with `auto_now` would have taken the time again there. `QuerySet.update` calls no field's `pre_save`, and neither kind of field is touched by it.

**Naive and aware.** `DateTimeField.to_python` returns a datetime as it is, naive or aware. A date becomes midnight of that day, and with `settings.USE_TZ` on it is made aware in the default time zone, with a `RuntimeWarning`. A string is parsed as a datetime and, failing that, as a date. `DateTimeField.get_prep_value` is stricter about what goes to the database: after `to_python`, a value that is still naive while `settings.USE_TZ` is on is made aware in the default time zone, with a `RuntimeWarning` that the field received a naive datetime while time zone support is active. The source's comment calls this backwards compatibility, naive datetimes being interpreted in local time. The backend then has its say in `get_db_prep_value`. SQLite, which keeps no time zone, is sent the value moved into the connection's time zone and written as a string without one, and its backend makes the value aware again on the way out ([Values in and out: adapters, converters and time zones](../backends/values.md)).

`DateField.to_python` has the opposite case to settle, a datetime given where a date is wanted. It takes the datetime's date, and with `settings.USE_TZ` on it first moves an aware one into the default time zone.

**Two methods for the model.** `DateField.contribute_to_class`, which `DateTimeField` inherits, adds two methods to the model class for a field that is not nullable (`django/db/models/fields/__init__.py:DateField.contribute_to_class`). For the sailor's field it left these in the class's own `__dict__`:

```text recording=models
get_next_by_signed_on: a partialmethod
get_previous_by_signed_on: a partialmethod
```

The names are `"get_next_by_%s"` and `"get_previous_by_%s"` with the field's name filled in, and each is a `functools.partialmethod` of `Model._get_next_or_previous_by_FIELD` that carries the field. Called on an instance, that method asks the model's default manager for the nearest row after the instance by that field, or before it, with the primary key to settle a tie, and raises the model's `Model.DoesNotExist` when there is none (`django/db/models/base.py:Model._get_next_or_previous_by_FIELD`). `TimeField` is not a `DateField`, and a model gets no such methods for one.

## Decimals and floats

`DecimalField` keeps two numbers, `max_digits` and `decimal_places`, and uses them in three places on a value's way (`django/db/models/fields/__init__.py:DecimalField`). Its `validators` add a `DecimalValidator` made of the two. `DecimalField.get_db_prep_value` passes them to the backend's `adapt_decimalfield_value` with the value. And `DecimalField.to_python` uses the first for the one conversion that needs care. A `float` is turned into a `decimal.Decimal` through a context whose precision is `max_digits`, which rounds it to that many significant digits, where any other value goes straight to the constructor and keeps the digits it was written with. A value that is not finite is refused.

```text recording=models
models.DecimalField(max_digits=4, decimal_places=2).to_python(1.1), models.DecimalField(max_digits=4, decimal_places=2).to_python('1.1')  ->  (Decimal('1.100'), Decimal('1.1'))
```

> **Changed in 6.1.** `max_digits` and `decimal_places` may both be left out on a backend whose `BaseDatabaseFeatures.supports_no_precision_decimalfield` is true, which the release notes give as Oracle, PostgreSQL and SQLite. Before, a check required both everywhere.

`FloatField` is the plainest of the numeric classes: `float` in `FloatField.to_python` and in `FloatField.get_prep_value`, with the same two kinds of error as an `IntegerField`.

## Durations, bytes, UUIDs, addresses and paths

For `DurationField` and `UUIDField` the stored form depends on the backend, and the field asks. A duration is an interval on PostgreSQL and on Oracle, the class's docstring says, and elsewhere an integer of microseconds: `DurationField.get_db_prep_value` leaves the form to the backend's `adapt_durationfield_value`, and for the way back `DurationField.get_db_converters` adds the backend's `convert_durationfield_value` where the backend's features say it has no native duration type (`django/db/models/fields/__init__.py:DurationField.get_db_converters`). `UUIDField.get_db_prep_value` sends the `uuid.UUID` itself where the features say the backend has a native type for one, and its 32 hexadecimal digits where they do not.

`BinaryField` is not editable unless made so, and `BinaryField.value_to_string` writes base64 for a serializer (`django/db/models/fields/__init__.py:BinaryField`).

`GenericIPAddressField` converts on the way into a statement as well as in validation, because its `get_prep_value` goes through `GenericIPAddressField.to_python`, which hands a value with a colon in it to `clean_ipv6_address` and so raises `ValidationError` for an IPv6 address that is not valid. Its validators are chosen when the field is made, from its `protocol` and `unpack_ipv4` (`django/core/validators.py:ip_address_validators`). And the backend's `adapt_ipaddressfield_value`, which the field's `get_db_prep_value` calls, turns an empty string into `None`, which is the reason one of the class's checks gives: a field that may be blank must be nullable, as blank values are stored as nulls.

> **Changed in 6.2.** `GenericIPAddressField` validates IPv6 input strictly when saving and querying. An address that is not valid raises `ValidationError` where it used to be accepted, and surrounding white space is stripped.

`FilePathField` is a column of text that holds a path, and it knows nothing about files. What it is made with, a `path` to look in, a `match`, and whether to go into subdirectories and to offer files or folders, is passed whole to the form field, which is what lists the directory, and a `path` that is callable is called at that moment (`django/db/models/fields/__init__.py:FilePathField.formfield`). Of the value itself the model field does one thing: `FilePathField.get_prep_value` passes anything but `None` to `str`. It is not one of the file fields, which keep a file in a storage ([File fields](files.md)).

## JSON

`JSONField` keeps any value that can be written as JSON (`django/db/models/fields/json.py:JSONField`). It takes an `encoder` and a `decoder`, classes of the kind the standard library's `json` module accepts, and uses each in one direction.

On the way in, `JSONField.get_db_prep_value` hands the value and the encoder to the backend's `adapt_json_value`, which by default is `json.dumps`. The field's `validate` tries the same call and reports a value that cannot be encoded as invalid. `JSONField.get_db_prep_save` settles what `None` means. `None` itself is stored as an SQL null. Storing the JSON value null takes an expression, `JSONNull`, which is a `Value` of `None` whose output field is a `JSONField` (`django/db/models/expressions.py:JSONNull`).

On the way out the class does what no other class in `django/db/models/fields/` does: it declares `JSONField.from_db_value`, which the base class's `get_db_converters` finds and returns. It passes the column's value to `json.loads` with the decoder, and returns as it stands a value that is not valid JSON. It also returns as it stands the result of a key transform that is not a string, its comment being that some backends, SQLite at least, extract such values as their own SQL types.

The class has a query side too. `JSONField.get_transform` answers for any name it does not know with a transform that looks the name up as a key, which is what lets a filter reach inside the stored value, and the module holds the lookups and transforms for that ([From QuerySet to SQL](../sql.md)). It also inherits `CheckFieldDefaultMixin`, whose check warns of a default that is one object shared by every instance and not a callable (`django/db/models/fields/mixins.py:CheckFieldDefaultMixin`).

## Values the database supplies: `GeneratedField` and `db_default`

Two kinds of column can get their value from the database and not from the instance: a generated column always, and a column with a database default when the instance was given nothing for it. Both then leave a new instance without the value until a statement hands it back. A `GeneratedField` is a column that the database computes from other columns of the same row (`django/db/models/fields/generated.py:GeneratedField`). A database default is not a class of field at all: `db_default=` is an argument of the base class, which does what follows from it, and `GeneratedField` and `CompositePrimaryKey` refuse it ([A field: the base class](fields.md)). The office's Manifest has one of each, `"kilos"` and `"stamped"`:

```python
# harbour/office/models.py
class Manifest(models.Model):
    serial = models.CharField(max_length=8, primary_key=True, default=serials.next_serial)
    voyage = models.ForeignKey("fleet.Voyage", on_delete=models.CASCADE)
    crates = models.PositiveIntegerField()
    kilos_each = models.PositiveIntegerField()
    kilos = models.GeneratedField(expression=F("crates") * F("kilos_each"), output_field=models.PositiveIntegerField(), db_persist=True)
    stamped = models.BooleanField(db_default=False)
    scan = models.FileField(upload_to="manifests/", blank=True)
```

The schema editor writes both into the table, the one as a `"GENERATED"` clause and the other as a `"DEFAULT"`:

```text recording=models
editor.create_model(Manifest)
  SQL CREATE TABLE "office_manifest" ("serial" varchar(8) NOT NULL PRIMARY KEY, "voyage_id" bigint NOT NULL REFERENCES "fleet_voyage" ("id") DEFERRABLE INITIALLY DEFERRED, "crates" integer unsigned NOT NULL CHECK ("crates" >= 0), "kilos_each" integer unsigned NOT NULL CHECK ("kilos_each" >= 0), "kilos" integer unsigned GENERATED ALWAYS AS (("crates" * "kilos_each")) STORED, "stamped" bool DEFAULT 0 NOT NULL, "scan" varchar(100) NOT NULL)
```

And this is a Manifest being made and saved, with only the lines that concern the two columns:

```text recording=models
a Manifest is made: its serial is 'M-0001', its stamped is a DatabaseDefault, and it has no value under kilos
...
      Field.pre_save(add=True)  (Manifest.stamped)  ->  a DatabaseDefault
...
      Model._do_insert(fields=[serial, voyage, crates, kilos_each, stamped, scan], returning_fields=[kilos, stamped])
        SQL INSERT INTO "office_manifest" ("serial", "voyage_id", "crates", "kilos_each", "scan") VALUES (%s, %s, %s, %s, %s) RETURNING "office_manifest"."kilos", "office_manifest"."stamped" with params ('M-0001', 1, 12, 40, '')
        -> [[480, False]]
      Model._assign_returned_values([480, False], [kilos, stamped])
```

The insert names neither column and asks for both back, and the instance ends with the two values the database produced.

### The generated column

A `GeneratedField` takes three arguments, all required and all by keyword: the expression, an `output_field` to say what type the result has, and `db_persist`, whether the database stores the result or works it out at each read (`django/db/models/fields/generated.py:GeneratedField.__init__`).

The class has no column type of its own. `GeneratedField.get_internal_type` and `GeneratedField.db_parameters` pass the question to the output field, so the column of `"kilos"` has a `PositiveIntegerField`'s type. What makes it a generated column is written by the schema editor, which asks `GeneratedField.generated_sql` for the expression as SQL and puts it after the type (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._column_generated_sql`).

The field joins the class as any field with a column does, and `GeneratedField.contribute_to_class` then does two things more. It makes the query that the expression is resolved against, one over the field's own model, and joins are refused when the expression is resolved, so the expression can name only columns of that table. And it registers on this one field object the lookups of the output field's class, so that a filter on `"kilos"` has the lookups of an integer (`django/db/models/fields/generated.py:GeneratedField.contribute_to_class`).

Whatever writes values passes the field over. The class sets `GeneratedField.generated`, which `Field` declares as false, and the flag is read by `Model.__init__`, which sets no attribute for the field when it fills an instance from keyword arguments and defaults; by `Model._save_table`, which leaves it out of an insert and of an update alike; and by `Model.clean_fields`, which does not clean it (`django/db/models/base.py:Model._save_table`). The field's own `__init__` refuses the arguments that would contradict this: a default, a database default, `editable=True` and `blank=False`. So a new Manifest has nothing at all under `"kilos"`, which is the state of a deferred field ([An instance and its state](instances.md)).

The value arrives with the save. The class sets `GeneratedField.db_returning`, which puts the field among `Options.db_returning_fields`, the columns an insert is asked to hand back. An update asks for a generated field too, when its expression refers to a field that is being written, which `_save_table` works out from `GeneratedField.referenced_fields`. Here the Manifest's `"crates"` is set to 20 and it is saved again:

```text recording=models
Model._do_update(pk_val='M-0001', values for [voyage, crates, kilos_each, stamped, scan], returning_fields=[kilos])
  SQL UPDATE "office_manifest" SET "voyage_id" = %s, "crates" = %s, "kilos_each" = %s, "stamped" = %s, "scan" = %s WHERE "office_manifest"."serial" = %s RETURNING "office_manifest"."kilos" with params (1, 20, 40, False, '', 'M-0001')
  -> [(800,)]
Model._assign_returned_values((800,), [kilos])
```

On a backend that cannot return columns from a statement the attribute stays absent, or is taken away, and the next read of it fetches the value ([Saving an instance](saving.md)).

> **Changed in 6.0.** Generated fields, and fields that were assigned an expression, are refreshed from the database after a save: from the statement's `"RETURNING"` clause where the backend has one, and by being left deferred where it has not.

### The database default

The Manifest's `"stamped"` is a `BooleanField` made with `db_default=False`. The `"DEFAULT"` clause of its column is what the schema editor writes for any field that has a database default (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._iter_column_sql`). On a new instance the attribute holds a `DatabaseDefault`, an expression that stands for that clause, and in a save `pre_save` returns it like any value (`django/db/models/fields/__init__.py:Field._get_default`).

The insert's compiler does not prepare that object as a value (`django/db/models/sql/compiler.py:SQLInsertCompiler.as_sql`). In the Manifest's insert it left the column out: the insert names five columns, and `"stamped"` is not one. It does that when every object being inserted holds a `DatabaseDefault` for the field and the statement has another column to name. Where it cannot leave the column out, the object is written as the keyword `"DEFAULT"` where the backend's features say it can be, and as the default's own expression where they say it cannot (`django/db/models/expressions.py:DatabaseDefault.as_sql`). And as `Field.db_returning` is true of a field with a database default, the column is asked back, which is how `False` came to take the object's place on the instance.

## A key of several columns: `CompositePrimaryKey`

`CompositePrimaryKey` is a field that stands for a primary key made of several columns, and has no column itself (`django/db/models/fields/composite.py:CompositePrimaryKey`). It is given the names of the fields that make up the key, at least two, and it has to be assigned to the name `"pk"`: a check refuses any other. The office's Berth is known by its port and its number there:

```python
# harbour/office/models.py
class Berth(models.Model):
    pk = models.CompositePrimaryKey("port_id", "number")
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    metres = models.PositiveSmallIntegerField()
```

What kind of field it is shows in how it joins the class:

```text recording=models
ModelBase.add_to_class(Berth, 'pk', a CompositePrimaryKey)
  CompositePrimaryKey.contribute_to_class(Berth, 'pk')
    Field.contribute_to_class(Berth, 'pk')  (a CompositePrimaryKey)
      Options.add_field(Berth.pk)
        Options.setup_pk(Berth.pk)  ->  Options.pk is Berth.pk
```

`CompositePrimaryKey.get_attname_column` gives `None` for the column, so the field is not concrete. `Field.contribute_to_class` enters it in the options, where it becomes `Options.pk` because it says it is the primary key, and sets no descriptor, having no column to set one for (`django/db/models/options.py:Options.setup_pk`). `CompositePrimaryKey.contribute_to_class` then sets one itself, a `CompositeAttribute` under `"pk"` (`django/db/models/fields/composite.py:CompositePrimaryKey.contribute_to_class`). And `Options._prepare` has nothing to add: the model has a key, so it is given no `"id"`.

On most models `"pk"` is the property `Model.pk`. On Berth the `CompositeAttribute` stands in front of it and does the same work for several attributes at once. Reading it gives a tuple of the parts' values. Assigning a tuple or a list to it sets each part, `None` clears them all, and a sequence of the wrong length is refused. It keeps nothing of its own (`django/db/models/fields/composite.py:CompositeAttribute`).

The parts are ordinary fields with columns, and are not themselves marked as primary keys. The composite field finds them by name the first time it is asked, as `CompositePrimaryKey.fields`, and the options give them as `Options.pk_fields`, which for a model with an ordinary key is a list of that one field (`django/db/models/options.py:Options.pk_fields`). `Model._save_table`, for one, leaves the fields of that list out of the columns an update sets.

```text recording=models
Berth._meta.pk, names(Berth._meta.pk_fields), Berth._meta.is_composite_pk  ->  (<django.db.models.fields.composite.CompositePrimaryKey: pk>, [port, number], True)
```

In the table there is no column for the field. The key is a constraint, written after the columns from `CompositePrimaryKey.columns`:

```text recording=models
editor.create_model(Berth)
  SQL CREATE TABLE "office_berth" ("port_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED, "number" smallint unsigned NOT NULL CHECK ("number" >= 0), "metres" smallint unsigned NOT NULL CHECK ("metres" >= 0), PRIMARY KEY ("port_id", "number"))
```

A filter on `"pk"` compares the columns together with a tuple, through lookups registered on the class ([From QuerySet to SQL](../sql.md)). This is a Berth fetched with `pk=(1, 2)`:

```text recording=models
SQL SELECT "office_berth"."port_id", "office_berth"."number", "office_berth"."metres" FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") = (%s, %s) LIMIT 21 with params (1, 2)
```

A save's update has the same condition ([Saving an instance](saving.md)). A key in several parts is set when every part is: `Model._is_pk_set` looks inside the tuple, and one part that is `None` makes the whole key unset.

```text recording=models
berth.pk, Berth._meta.pk.attname, berth._is_pk_set()  ->  ((1, 2), 'pk', True)
Berth(port=leith, number=None, metres=60).pk, Berth(port=leith, number=None, metres=60)._is_pk_set()  ->  ((2, None), False)
```

> **Changed in 5.2.** `CompositePrimaryKey` is new in 5.2.

## `OrderWrt`

`OrderWrt` is a field that Django adds to a model itself: an `IntegerField` that names itself `"_order"` and is not editable (`django/db/models/fields/proxy.py:OrderWrt`, `django/db/models/fields/__init__.py:IntegerField`). `Options._prepare` adds one to a model whose `Meta` sets `order_with_respect_to` (`django/db/models/options.py:Options._prepare`) ([The options: what a model keeps as `_meta`](options.md)), and a save fills it on an insert ([Saving an instance](saving.md)).

## Classes kept so that old migrations load

`CommaSeparatedIntegerField`, `IPAddressField` and `NullBooleanField` are removed, in that a model which uses one fails the system checks, and their classes are still there (`django/db/models/fields/__init__.py:Field._check_deprecation_details`). A migration is Python that names field classes by their dotted paths, and one written while such a class was in use has to go on importing. So the class stays, with an attribute, `system_check_removed_details`, that holds a message, a hint and the id of a check. `Field._check_deprecation_details`, one of the checks that every field runs, returns an error made of those for a field whose class has the attribute set, and the messages say that the class is removed except for support in historical migrations. A class on its way out has `system_check_deprecated_details` in the same form, and the same check returns a warning for it ([The model checks](checks.md)).
