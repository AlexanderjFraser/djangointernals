---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Serializing values: `serializer_factory` and `deconstruct`

A migration file is Python source that Django writes, so every value in an operation has to become an expression that makes the value again when the file is imported. `serializer_factory` picks a serializer for a value, the serializer returns the expression as a string with the import lines it needs, and an object with a `deconstruct` method is written as a call with the arguments the method returns.

A **serializer** is an instance of a subclass of `BaseSerializer`, made with the value. The subclass overrides `BaseSerializer.serialize` to return the text and a set of import lines, each a whole statement such as `"import datetime"`; `MigrationWriter.serialize` only calls `serializer_factory` and then that method (`django/db/migrations/serializer.py:BaseSerializer`, `django/db/migrations/writer.py:MigrationWriter.serialize`).

A value is written whole, as a literal or its `repr`; or by name, as the dotted path it is imported by; or as a call that makes it again. One that holds others is written by writing those: its serializer calls `serializer_factory` on each and adds their imports to its own. Of each recording only the lines a passage is about are quoted: a line is an expression put to a running Django and, after `->`, its value, or the word raises and an exception, and written stands for `MigrationWriter.serialize`, giving the text and then the imports. Here the value is a field whose default is next_serial, a function at the top of harbour's module serials:

```text recording=migrations
written(models.CharField(max_length=8, default=next_serial))  ->  models.CharField(default=harbour.serials.next_serial, max_length=8)   needs ['from django.db import models', 'import harbour.serials']
```

A value Django has no expression for cannot be written into a migration file, and that is the limit on what a field's `deconstruct` may return. The autodetector compares fields by what it returns ([The autodetector: comparing two project states](autodetector.md)).

## `serializer_factory`: the order of the tests

`serializer_factory` is a fixed sequence of tests, and the first a value passes decides (`django/db/migrations/serializer.py:serializer_factory`). It first unwraps: a `Promise`, which a lazily translated string is, becomes its `str` then, and a `LazyObject` the object it wraps.

Then a field gets `ModelFieldSerializer`, a manager `ModelManagerSerializer`, an operation `OperationSerializer`, a class `TypeSerializer`, and anything else with an attribute `deconstruct` gets `DeconstructibleSerializer`. A class whose instances can deconstruct has the attribute too, and is caught by the test before.

What passes none of these reaches the registry, `Serializer._registry`: a dictionary from a type, or a tuple of types, to a serializer class (`django/db/migrations/serializer.py:Serializer`). Its entries are tried in the dictionary's order with `isinstance`, and some depend on that order: `models.Choices` stands before `enum.Enum` and `datetime.datetime` before `datetime.date`, each a subclass of what it precedes; `SettingsReference` before `str`; `pathlib.PurePath` before `os.PathLike`; and `str`, `bytes`, `range` and the containers before `collections.abc.Iterable`, which each of them is.

```text recording=migrations
type(serializer_factory(Rank.MATE)).__name__  ->  'ChoicesSerializer'
type(serializer_factory(uuid.SafeUUID.safe)).__name__  ->  'EnumSerializer'
```

Rank is harbour's class of text choices, `uuid.SafeUUID` an enumeration of Python's. `SET` returns a function, which the entry for functions would take, but sets a `deconstruct` on it, and the attribute is tested first (`django/db/models/deletion.py:SET`).

## `deconstruct`: a value written as a call

The **`deconstruct` protocol** is how an object says how to make it again: the method returns the dotted path of something to call, positional arguments and keyword arguments, and `DeconstructibleSerializer.serialize_deconstructed` writes the call (`django/db/migrations/serializer.py:DeconstructibleSerializer.serialize_deconstructed`). A path whose module is exactly `django.db.models` is written `models.` and the name, with `"from django.db import models"`; any other whole, with an import of its module (`django/db/migrations/serializer.py:DeconstructibleSerializer._serialize_path`). The positional arguments go through `serializer_factory` in turn, then the keyword arguments sorted by name; those whose names are not identifiers go into a dictionary written after `**`. So an object can be written only if everything it deconstructs to can.

A field, a manager and an operation answer in other shapes, so each has its own serializer. `Field.deconstruct` returns the field's name first, which `ModelFieldSerializer` leaves out, and shortens the path of a class under `django.db.models.fields` to `django.db.models` (`django/db/models/fields/__init__.py:Field.deconstruct`; [A field: the base class](../models/fields.md)). `ModelManagerSerializer` writes a manager that `QuerySet.as_manager` made as a call of that method on the queryset class's path, and another as a call of its own class ([Managers](../models/managers.md)). `OperationSerializer` hands an operation to `OperationWriter` ([Writing a migration file: `MigrationWriter`](writer.md)).

`Q.deconstruct`, `Index.deconstruct` and `BaseConstraint.deconstruct` are written by hand, and each shortens its own module to `django.db.models` (`django/db/models/query_utils.py:Q.deconstruct`; [Constraints and indexes](../models/constraints.md)). Other classes get the method from the decorator `deconstructible` (`django/utils/deconstruct.py:deconstructible`). It replaces the class's `__new__` with one that keeps the arguments of the call on the new object, as `_constructor_args`, and adds a `deconstruct` that returns them after a path. The path is the module and name of the object's own class, so a subclass is written under its own name; an object of the decorated class itself gets the path passed as `path=`, where one was. The method first imports the module, and raises `ValueError` if the name is not in it, as an inner class's is not. Tide is a class decorated with `path="__main__.Tide"`:

```text recording=migrations
written(Tide(high=4.2))  ->  __main__.Tide(high=4.2)   needs ['import __main__']
Tide(high=4.2).deconstruct()  ->  ('__main__.Tide', (), {'high': 4.2})
```

`Expression` is decorated, as is every validator class of `django/core/validators.py`; `F`, `Func`, `Value` and some others are decorated with a path in `django.db.models`, which is why a file has `models.F` and not `django.db.models.expressions.F` (`django/db/models/expressions.py:F`).

## Values written by name

What is written by name is not written out: the file imports whatever has that name when the migration is loaded.

`FunctionTypeSerializer` takes what `FUNCTION_TYPES` lists, functions, built-in functions and methods among them (`django/db/migrations/serializer.py:FunctionTypeSerializer`). A method whose `__self__` is a class is written as the class's module, its qualified name and the method's name. Anything else is written as its `__module__` and `__qualname__` (`django/utils/module_loading.py:qualname`): a function at the top of a module, or in the body of a class. A method defined in Python and bound to an instance is written so too, as the function it wraps: the loaded migration has the function and no instance.

`TypeSerializer` writes a class by module and qualified name too, except `models.Model` and `types.NoneType`, written under those names, and a builtin, written bare with no import (`django/db/migrations/serializer.py:TypeSerializer`). `EnumSerializer` writes a member as its class and, in square brackets, its name, and a combined `enum.Flag` as its members joined by `|`. `ChoicesSerializer` writes a member of a `Choices` class not by name but as its value alone, so the file does not import the class.

A **`SettingsReference`** is a `str` that also holds a setting's name, in `SettingsReference.setting_name` (`django/conf/__init__.py:SettingsReference`). A field makes one: where `RelatedField.swappable_setting` names a setting, as it does for a field that points at the user model, which `AUTH_USER_MODEL` can swap, `ForeignObject.deconstruct` and `ManyToManyField.deconstruct` put a `SettingsReference` in place of the `"to"` argument (`django/db/models/fields/related.py:ForeignObject.deconstruct`). It is written as the setting, so the file follows the setting of the project that loads it; the setting's value by itself is written as a string:

```text recording=migrations
written(SettingsReference(settings.AUTH_USER_MODEL, 'AUTH_USER_MODEL'))  ->  settings.AUTH_USER_MODEL   needs ['from django.conf import settings']
written(settings.AUTH_USER_MODEL)  ->  'auth.User'   needs no import
```

The dependency that goes with it is in [From operations to migrations: dependencies, order and names](dependencies.md).

## Values written whole

Where a value's `repr` is an expression that makes it, the `repr` is the text; `BaseSimpleSerializer` returns it with no import. The other serializers of this kind mend what `repr` leaves undone: an import it needs, the module's name in front of it, or a call of `float` on a string for a `float` that is not a number or is infinite. `DatetimeDatetimeSerializer` first converts a datetime in a time zone other than UTC to UTC. `PathSerializer` writes a concrete path as the pure path of its flavour, so that, its comment says, a migration made on one platform can be used on another. `RegexSerializer` writes a pattern's flags after an exclusive-or with those of an empty `str` pattern, and none where that leaves none: `'^m-'` compiled with `re.IGNORECASE` is written `re.compile('^m-', 2)`, without the `re.UNICODE` that Python added (`django/db/migrations/serializer.py:RegexSerializer`).

For a list, a tuple or a set, `BaseSequenceSerializer.serialize` writes each item and joins the strings, and a subclass gives the brackets through `BaseSequenceSerializer._format`: a tuple of one item gets its comma, and an empty set is `set()`, since `{}` is a dictionary (`django/db/migrations/serializer.py:BaseSequenceSerializer`). `BaseUnorderedSequenceSerializer` first sorts a set or a frozenset by the `repr` of its items, and `DictionarySerializer` a dictionary by its items themselves, so the text does not depend on the order of iteration. `IterableSerializer` writes any other iterable, a generator too, as a tuple of what it yields.

## The registry, in its order

The entries of `Serializer._registry` stand in the order `serializer_factory` tries them, so a row takes only what no row above it took (`django/db/migrations/serializer.py:Serializer`).

| serializer | key | writes |
|---|---|---|
| `FrozensetSerializer` | `frozenset` | `frozenset([1, 2])` |
| `SequenceSerializer` | `list` | `['Bergen', 'Leith']` |
| `SetSerializer` | `set` | `{'Bergen', 'Leith', 'Lisbon'}`, `set()` |
| `TupleSerializer` | `tuple` | `('Bergen',)` |
| `DictionarySerializer` | `dict` | `{'name': 'Petrel', 'tonnage': 480}` |
| `ChoicesSerializer` | `models.Choices` | `'mate'` |
| `EnumSerializer` | `enum.Enum` | `uuid.SafeUUID['safe']` |
| `DatetimeDatetimeSerializer` | `datetime.datetime` | `datetime.datetime(2026, 3, 2, 9, 0, tzinfo=datetime.timezone.utc)`, for 10:00 in Oslo too |
| `DateTimeSerializer` | `datetime.date`, `datetime.timedelta`, `datetime.time` | `datetime.timedelta(days=14)` |
| `SettingsReferenceSerializer` | `SettingsReference` | `settings.AUTH_USER_MODEL` |
| `FloatSerializer` | `float` | `float("inf")` |
| `BaseSimpleSerializer` | `bool`, `int`, `types.NoneType`, `bytes`, `str`, `range` | `'North dock'`, `range(1, 4)` |
| `DecimalSerializer` | `decimal.Decimal` | its `repr`, with `"from decimal import Decimal"` |
| `FunctoolsPartialSerializer` | `functools.partial`, `functools.partialmethod` | `functools.partial(builtins.round, ndigits=2)` |
| `FunctionTypeSerializer` | `FUNCTION_TYPES` | `django.db.models.deletion.CASCADE`, `datetime.date.today` |
| `GenericAliasSerializer` | `types.GenericAlias` | `list[int]` |
| `IterableSerializer` | `collections.abc.Iterable` | `('Bergen',)`, for an iterator |
| `RegexSerializer` | `COMPILED_REGEX_TYPE`, `RegexObject` | `re.compile('^m-', 2)` |
| `UUIDSerializer` | `uuid.UUID` | `uuid.UUID('12345678-1234-5678-1234-567812345678')` |
| `PathSerializer` | `pathlib.PurePath` | `pathlib.PureWindowsPath('manifests')`, for a `pathlib.Path` on Windows |
| `PathLikeSerializer` | `os.PathLike` | the `repr` of what `os.fspath` returns, a `str` or `bytes`, and `{}` for its imports |
| `ZoneInfoSerializer` | `zoneinfo.ZoneInfo` | `zoneinfo.ZoneInfo(key='Europe/Oslo')` |
| `DatabaseOnDeleteSerializer` | `DatabaseOnDelete` | `django.db.models.deletion.DB_CASCADE` |

> **Changed in 6.0.** `ZoneInfoSerializer` is new in 6.0, as is the dictionary after `**` in a deconstructed call.

## What cannot be written

A function is written by name, and a lambda has none to import by: `FunctionTypeSerializer` refuses it, a function with no module, and one for which `qualname` raises, as it does for a function defined inside another, whose qualified name has `"<"` in it (`django/db/migrations/serializer.py:FunctionTypeSerializer.serialize`). What passes no test of `serializer_factory` gets the general `ValueError`. `datetime.UTC` by itself does: the registry has no key for a `datetime.timezone`, and inside a datetime it is only part of a `repr`. So does `object()` in these lines, in which nested is a function of the recording's own that returns one defined inside it:

```text recording=migrations
written(lambda: 1)  ->  raises ValueError: Cannot serialize function: lambda
written(nested())  ->  raises ValueError: Could not find function inner in __main__.\n
written(object())  ->  raises ValueError: Cannot serialize: <object object>\nThere are some values Django cannot serialize into migration files.\nFor more, see https://docs.djangoproject.com/en/dev/topics/migrations/#migration-serializing
```

## Registering a serializer

`Serializer.register` takes a type, or a tuple of types, and a serializer class; it raises `ValueError` for a class that is no subclass of `BaseSerializer` and otherwise stores the pair, and `Serializer.unregister` pops a key; `MigrationWriter.register_serializer` and `MigrationWriter.unregister_serializer` only call the two (`django/db/migrations/serializer.py:Serializer.register`). A new key goes to the end of the dictionary, so it is reached only by a value no entry before it matches; a key already there keeps its place and gets the new class. And the registry is reached only past the tests before it: a serializer registered for a field class, or for a class with a `deconstruct`, is never asked. Fathoms is a class with no `deconstruct`, and this is a serializer for it, which writes the class as if it stood in a module depths that harbour does not have:

```python
class FathomsSerializer(BaseSerializer):
    def serialize(self):
        return f"harbour.depths.Fathoms({self.value.number})", {"import harbour.depths"}
```

```text recording=migrations
MigrationWriter.register_serializer(Fathoms, FathomsSerializer)
list(Serializer._registry)[-1] is Fathoms  ->  True
written(Fathoms(12))  ->  harbour.depths.Fathoms(12)   needs ['import harbour.depths']
```
