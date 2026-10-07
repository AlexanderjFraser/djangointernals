---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The lookup registry: `RegisterLookupMixin`

`RegisterLookupMixin` gives a field class, a single field and a transform a dictionary from names to the lookups and transforms they answer to. It is where the last words of a filter's name, `"year"` and `"lt"` in `"signed_on__year__lt"`, are looked up, through `RegisterLookupMixin.get_lookup` and `RegisterLookupMixin.get_transform`, and where a project adds a word of its own with `RegisterLookupMixin.register_lookup`.

A filter's name is read in two parts. The first words name fields, and the query matches them against the model and joins tables as it goes. What is left when the fields run out, `"year"` and `"lt"`, means nothing by itself. What `"year"` does depends on what stands to its left, a date here, and the `"lt"` after it is a comparison made for years, not the one a date has. A project, or one of Django's optional packages, must also be able to add a word. So the meaning of a word is not settled in the query. The thing on the left is asked, and a field and a transform carry a dictionary of the words they know. That dictionary, with the methods that fill it and read it, is the **registry**.

Two sorts of class are kept in it. A subclass of `Lookup` makes a comparison of a left side and a value. Such a class is a **lookup**, and the word registered for it is taken for one only at the end of a name. A subclass of `Transform` makes another expression of the left side, a year of a date, and that expression is asked for the next word; such a class is a **transform** (`django/db/models/lookups.py:Lookup`, `django/db/models/lookups.py:Transform`). What the two classes do, and how the query walks the words of a name, is told in [From QuerySet to SQL](../sql.md).

## Who has a registry

`RegisterLookupMixin` is a base of two classes, `Field` and `Transform`, and through them of every field class and every transform (`django/db/models/query_utils.py:RegisterLookupMixin`, `django/db/models/fields/__init__.py:Field`, `django/db/models/lookups.py:Transform`). Nothing else has a dictionary, and the other things a query may put on the left of a comparison pass the question on. An expression has an **output field**, a field object that stands for the type of its value, and `BaseExpression.get_lookup` and `BaseExpression.get_transform` give that field's answer (`django/db/models/expressions.py:BaseExpression.get_lookup`). The rel of a relation, which stands for the relation as seen from the other model, answers with its field's (`django/db/models/fields/reverse_related.py:ForeignObjectRel.get_lookup`).

A column is an expression whose output field is a field of a model. So where the left side of a comparison in a filter is a column, what is asked in the end is one field object, an instance, and not its class.

`Transform` lists the mixin ahead of `Func` among its bases so that, its docstring says, `RegisterLookupMixin.get_lookup` and `RegisterLookupMixin.get_transform` examine the transform itself first and its output field after.

## What a class registers

A class that has `RegisterLookupMixin` among its bases keeps what is registered on it in a dictionary on the class itself, the attribute `"class_lookups"`, from each name to a class. A class has that attribute among its own only when something has been registered on it, and the mixin defines none.

`RegisterLookupMixin.register_class_lookup` puts an entry in. It takes the name from the attribute `lookup_name` of the class it is registering unless it is given another, makes a new, empty dictionary on a class that has none of its own, so that a subclass does not write into its parent's, stores the entry, and returns the class it was given (`django/db/models/query_utils.py:RegisterLookupMixin.register_class_lookup`). Returning the class lets the method be used as a decorator.

That is how the standard lookups are registered, as their modules are imported. In `django/db/models/lookups.py` the class for each lookup registered on `Field`, from `Exact` to `IRegex`, stands under a decorator that registers it. The modules of narrower kinds do the same for theirs: the parts of a date are registered on `DateField`, `TimeField` and `DateTimeField` after the `Extract` classes in `django/db/models/functions/datetime.py`, the comparisons of a relation on `ForeignObject` after that class, and those of JSON and of a composite primary key in the modules of their fields. `django.contrib.postgres` registers lookups of its own on `CharField` and `TextField` when its application is made ready (`django/contrib/postgres/apps.py:PostgresConfig.ready`).

What follows was recorded from a running Django, on SQLite, over the models and rows that the chapter's opening page, [QuerySets](../querysets.md), lists: each line is Python that was run, with its value or the exception it raised after `->` where it is an expression, and a line that begins `SQL` is a statement as Django handed it to its cursor.

```text recording=querysets
sorted(models.Field.get_lookups())  ->  ['contains', 'endswith', 'exact', 'gt', 'gte', 'icontains', 'iendswith', 'iexact', 'in', 'iregex', 'isnull', 'istartswith', 'lt', 'lte', 'range', 'regex', 'startswith']
sorted(set(models.DateField.get_lookups()) - set(models.Field.get_lookups()))  ->  ['day', 'iso_week_day', 'iso_year', 'month', 'quarter', 'week', 'week_day', 'year']
sorted(set(models.CharField.get_lookups()) - set(models.Field.get_lookups())), 'class_lookups' in vars(models.CharField), 'class_lookups' in vars(models.Field)  ->  ([], False, True)
```

The first line is what is registered on `Field`. The second is what `DateField` has beyond it. The third is `CharField`, which in this project has nothing of its own: no name beyond `Field`'s, and no dictionary among its attributes.

What a class answers to is its own dictionary merged with those of the classes it inherits from. `RegisterLookupMixin.get_class_lookups` collects the `"class_lookups"` of each class in the method resolution order, with an empty dictionary for a class that has none, and gives the list to `RegisterLookupMixin.merge_dicts`, which lays them over one another from the last to the first (`django/db/models/query_utils.py:RegisterLookupMixin.get_class_lookups`, `django/db/models/query_utils.py:RegisterLookupMixin.merge_dicts`). So where two classes register one name, the entry found is that of the class nearer the front of the order. `IntegerField` registers a class of its own under `"exact"`, and an integer field, or a field of a class built on `IntegerField`, finds that class and not `Field`'s.

| class, in the method resolution order of `DateTimeField` | names registered on it |
|---|---|
| `DateTimeField` | `"date"`, `"hour"`, `"minute"`, `"second"`, `"time"` |
| `DateField` | `"day"`, `"iso_week_day"`, `"iso_year"`, `"month"`, `"quarter"`, `"week"`, `"week_day"`, `"year"` |
| `DateTimeCheckMixin` | none |
| `Field` | the names of the first recorded line above |
| `RegisterLookupMixin` | none |

*What the merge for `DateTimeField` is made of, by the modules that `django.db.models` imports. An upper row's entry is the one found where two rows have a name.*

The merge is kept for each class. `get_class_lookups` is a class method over a function wrapped in `functools.cache`, with the class as the key, so every later call returns the same object until the cache is cleared.

## One name for a class and for an instance

`RegisterLookupMixin` has three operations, reading the dictionary, registering and unregistering, that each have two forms under one name: one for a class, which works on the dictionaries kept on classes, and one for a single field or transform, which keeps entries of its own. `RegisterLookupMixin.get_lookups`, `RegisterLookupMixin.register_lookup` and `RegisterLookupMixin._unregister_lookup` are each an instance of `class_or_instance_method`, a descriptor made of two functions (`django/db/models/query_utils.py:class_or_instance_method`). When the attribute is read on a class, `class_or_instance_method.__get__` returns the first function with the class already bound to it, as a `functools.partial`. When it is read on an instance, it returns the second function with the instance bound.

| the name | read on a class, it is | read on an instance, it is |
|---|---|---|
| `get_lookups` | `RegisterLookupMixin.get_class_lookups` | `RegisterLookupMixin.get_instance_lookups` |
| `register_lookup` | `RegisterLookupMixin.register_class_lookup` | `RegisterLookupMixin.register_instance_lookup` |
| `_unregister_lookup` | `RegisterLookupMixin._unregister_class_lookup` | `RegisterLookupMixin._unregister_instance_lookup` |

*The three attributes of `RegisterLookupMixin` that are a `class_or_instance_method`.*

## `get_lookup` and `get_transform`

`RegisterLookupMixin.get_lookup` and `RegisterLookupMixin.get_transform` are what a query asks for the class behind one word (`django/db/models/query_utils.py:RegisterLookupMixin.get_lookup`, `django/db/models/query_utils.py:RegisterLookupMixin.get_transform`).

Lookups and transforms share the one dictionary, which both methods read through `RegisterLookupMixin._get_lookup`, and the two differ in a test. `get_lookup` returns what is under the name if that is a subclass of `Lookup`, and `None` if it is anything else. `get_transform` returns it if it is a subclass of `Transform` (`django/db/models/lookups.py:Transform`). Where nothing is under the name and the object has an `output_field`, each passes the question to that field. Of the classes that have a registry, a transform has an output field, being an expression, and so has a `GeneratedField`.

In these lines name_field is the field `"name"` of Sailor, a `CharField`, and `"signed_on"` is a `DateTimeField` (`django/db/models/fields/__init__.py:CharField`).

```text recording=querysets
name_field.get_lookup('exact').__name__, name_field.get_lookup('year'), name_field.get_transform('year')  ->  ('Exact', None, None)
Sailor._meta.get_field('signed_on').get_lookup('year'), Sailor._meta.get_field('signed_on').get_transform('year').__name__  ->  (None, 'ExtractYear')
...
name_field.get_lookups() is models.CharField.get_lookups(), models.CharField.get_lookups() is models.CharField.get_lookups(), models.CharField.get_lookups() is models.Field.get_lookups()  ->  (True, True, False)
```

A sailor's name answers to `"exact"` and knows no `"year"`. The moment a sailor signed on has `"year"`, as a transform and not as a lookup. The transform, `ExtractYear`, has a registry of its own: comparisons made for years are registered on it under `"exact"`, `"gt"`, `"gte"`, `"lt"` and `"lte"`, and asked for another name an `ExtractYear` passes the question to its output field, an integer field (`django/db/models/functions/datetime.py`). The last line is the cache at work: a field with no entries of its own returns its class's dictionary itself, the class returns the same object at each call, and `CharField`'s dictionary is not `Field`'s.

The words of a filter's name are resolved by two methods of the query ([From QuerySet to SQL](../sql.md)). `Query.build_lookup` takes every word but the last for a transform, and the last for a lookup or, failing that, for a transform followed by `"exact"`. `Query.try_transform` is where a word that is neither ends: it raises `FieldError`, naming the word, with the words after it where it is not the last, and the class of the output field (`django/db/models/sql/query.py:Query.build_lookup`, `django/db/models/sql/query.py:Query.try_transform`).

## Lookups of one field

Called on a field, `RegisterLookupMixin.register_lookup` registers for that field alone. `RegisterLookupMixin.register_instance_lookup` keeps the entry in a dictionary on the instance, `RegisterLookupMixin.instance_lookups`, which it makes at the first registration. `RegisterLookupMixin.get_instance_lookups` returns the class's merged dictionary where the instance has no entries, and otherwise a new dictionary of the class's entries with the instance's laid over them (`django/db/models/query_utils.py:RegisterLookupMixin.get_instance_lookups`).

The recording registers a lookup of its own, first on one field and then on a class. The second field it uses is the title of a Logbook, a model of the shipping line's office:

```python
# harbour/office/models.py
class Logbook(models.Model):
    title = models.CharField(max_length=60)
```

```python
# a lookup defined for the recording
class Shouted(Lookup):
    lookup_name = "shouted"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return f"UPPER({lhs}) = UPPER({rhs})", (*lhs_params, *rhs_params)
```

Here title_field is that field `"title"`.

```text recording=querysets
name_field.register_lookup(Shouted)
name_field.instance_lookups, name_field.get_lookup('shouted').__name__, title_field.get_lookup('shouted'), models.CharField.get_lookups().get('shouted')  ->  ({'shouted': <class '__main__.Shouted'>}, 'Shouted', None, None)
list(Sailor.objects.filter(name__shouted='ada'))  ->  [<Sailor: Ada>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") = UPPER(%s) with params ('ada',)
Logbook.objects.filter(title__shouted='log 1')  ->  raises FieldError: Unsupported lookup 'shouted' for CharField or join on the field not permitted.
```

The entry is on the one field. A filter on a sailor's name finds it, because the left side of that comparison is a column whose output field is that very field object. The same word after the title of a Logbook, another `CharField`, is refused, and the class's dictionary has no such name (`django/db/models/fields/__init__.py:CharField`).

One class of Django's registers on instances as a matter of course: a `GeneratedField`, when it joins its model, registers each class lookup of its `output_field` on itself, so that a generated column of integers answers as an integer field does (`django/db/models/fields/generated.py:GeneratedField.contribute_to_class`).

## Registering on a class, and the cache

The recording goes on with `RegisterLookupMixin.register_lookup` called on a class: the lookup Shouted is taken off the one field and registered on `CharField` (`django/db/models/fields/__init__.py:CharField`).

```text recording=querysets
name_field._unregister_lookup(Shouted)
models.CharField.register_lookup(Shouted)
vars(models.CharField)['class_lookups'], title_field.get_lookup('shouted').__name__, models.TextField.get_lookups().get('shouted'), models.EmailField.get_lookups().get('shouted').__name__  ->  ({'shouted': <class '__main__.Shouted'>}, 'Shouted', None, 'Shouted')
Logbook.objects.filter(title__shouted='log 1').count()  ->  1
  SQL SELECT COUNT(*) AS "__count" FROM "office_logbook" WHERE UPPER("office_logbook"."title") = UPPER(%s) with params ('log 1',)
models.CharField._unregister_lookup(Shouted)
vars(models.CharField)['class_lookups'], title_field.get_lookup('shouted')  ->  ({}, None)
```

After the registration the title of a Logbook finds the lookup, and so does `EmailField`, which is built on `CharField`. `TextField`, which is not, does not (`django/db/models/fields/__init__.py:EmailField`).

After it has stored the entry, `RegisterLookupMixin.register_class_lookup` calls `RegisterLookupMixin._clear_cached_class_lookups`, which goes through the class and every class below it, as the generator `subclasses` yields them, and has a cache cleared for each: that of `RegisterLookupMixin.get_class_lookups`, or, for a class at or under `ForeignObject`, that of `ForeignObject.get_class_lookups`, a cached function of its own (`django/db/models/query_utils.py:RegisterLookupMixin._clear_cached_class_lookups`, `django/db/models/query_utils.py:subclasses`, `django/db/models/fields/related.py:ForeignObject.get_class_lookups`). Clearing empties the whole cache of the function, for every class at once.

`RegisterLookupMixin._unregister_class_lookup` deletes an entry and clears the same caches, and `RegisterLookupMixin._unregister_instance_lookup` deletes one from an instance. The docstring of each says that it is for use in tests only, not being thread-safe. Django's own callers keep to that: a context manager that registers lookups for the length of a test, and the function that undoes the registrations of `django.contrib.postgres` when a test's override of the settings ends and the applications it goes back to have not got that one (`django/test/utils.py:register_lookup`, `django/contrib/postgres/apps.py:uninstall_if_needed`). The last of the lines quoted above shows what unregistering leaves: the dictionary stays on `CharField`, empty.

## A relation field stops the merge

`ForeignObject`, the class that `ForeignKey` and `OneToOneField` are built on, overrides `RegisterLookupMixin.get_class_lookups`. Its own cuts the method resolution order off after `ForeignObject` before it merges, so that what `Field` registers is left out (`django/db/models/fields/related.py:ForeignObject.get_class_lookups`). Of what is registered on classes, a field of such a class answers only to what is registered on `ForeignObject` or below it: the comparisons made for relations, which that module registers after the class.

```text recording=querysets
sorted(models.ForeignKey.get_lookups()), sorted(vars(models.ForeignObject)['class_lookups'])  ->  (['contains', 'endswith', 'exact', 'gt', 'gte', 'icontains', 'iendswith', 'iexact', 'in', 'iregex', 'isnull', 'istartswith', 'lt', 'lte', 'range', 'regex', 'startswith'], ['exact', 'gt', 'gte', 'in', 'isnull', 'lt', 'lte'])
...
sorted(Sailor._meta.get_field('ship').get_lookups()), sorted(models.ForeignKey.get_class_lookups())  ->  (['exact', 'gt', 'gte', 'in', 'isnull', 'lt', 'lte'], ['exact', 'gt', 'gte', 'in', 'isnull', 'lt', 'lte'])
Sailor.objects.filter(ship__contains=1)  ->  raises FieldError: Unsupported lookup 'contains' for ForeignKey or join on the field not permitted.
```

The field `"ship"` of Sailor, a foreign key, answers to the seven names registered on `ForeignObject`, as does `get_class_lookups` on its class, and a filter that puts `"contains"` after its name is refused, in the words of `Query.try_transform`. That is the answer a query meets, since a query asks the field. The long list at the head of the block, with all of `Field`'s names in it, is `RegisterLookupMixin.get_lookups` read on the class `ForeignKey`: the mixin's own function with the class bound to it, which merges the whole order without consulting the override. A field goes the other way: `RegisterLookupMixin.get_instance_lookups` calls `get_class_lookups` on the instance, which finds the override (`django/db/models/query_utils.py:RegisterLookupMixin.get_instance_lookups`, `django/db/models/query_utils.py:class_or_instance_method.__get__`).

A rel passes `get_lookups` to its field as it does `get_lookup` and `get_transform`, so a name that reaches the relation from the other model meets the same list (`django/db/models/fields/reverse_related.py:ForeignObjectRel.get_lookups`).
