---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `values` and `values_list`: rows as dictionaries and tuples

`QuerySet.values` and `QuerySet.values_list` return a clone that makes no instances. Its query selects the columns that were named, or every concrete field of the model where none was, and its iterable class, `ValuesIterable`, `ValuesListIterable`, `FlatValuesListIterable` or `NamedValuesListIterable`, makes of each row a dictionary, a tuple, a single value or a named tuple. `QuerySet.dates` and `QuerySet.datetimes` are built on `values_list`.

A program often wants a few columns and not objects: names for a menu, keys to hand to another query, pairs for a chart. A queryset of instances selects the model's columns and runs `Model.__init__` for every row. Two things have to change to avoid that, and they are kept in different places. What is selected is the query's business, so the two methods give the query the names. What a row becomes is settled by the queryset's **iterable class**, the class whose instance runs the query and makes something of each row, so the methods put another class in `QuerySet._iterable_class` in place of `ModelIterable` ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)). And one thing is noted for the queryset's other methods: `QuerySet._fields`, which is `None` on an ordinary queryset and a tuple of names after either method.

| the call | iterable class | one row becomes |
|---|---|---|
| `values("name", "tonnage")` | `ValuesIterable` | a dictionary with those two keys |
| `values()` | `ValuesIterable` | a dictionary with a key for every concrete field: its **attname**, the name of the attribute that holds its value, as `"home_id"` is for a ship's foreign key to its home |
| `values_list("name", "tonnage")` | `ValuesListIterable` | a tuple of the two values |
| `values_list("name", flat=True)` | `FlatValuesListIterable` | the value alone |
| `values_list("name", "tonnage", named=True)` | `NamedValuesListIterable` | a named tuple, of a class named Row |
| `dates("sailed", "year")` | `FlatValuesListIterable` | a date |
| `datetimes("signed_on", "year")` | `FlatValuesListIterable` | a datetime |

*What each call leaves as `QuerySet._iterable_class`, and what that class makes of a row.*

## What the two methods share: `QuerySet._values`

`QuerySet._values` is given names of fields and, by keyword, expressions that each have a name already. It does three things to a clone (`django/db/models/query.py:QuerySet._values`). Where there are expressions, it annotates the clone with them, by calling `QuerySet.annotate` with the keywords: an expression given to `QuerySet.values` is an annotation like any other, resolved against the query and kept under its name ([Annotations, ordering and the other methods that change the query](methods.md)). It stores the names, the expressions' among them, as `QuerySet._fields`. And it hands the names to the query's `Query.set_values` (`django/db/models/sql/query.py:Query.set_values`).

`set_values` is where the select list changes, and two rules come out of it. A call replaces the fields that an earlier `values` or `QuerySet.values_list` selected, and does not add to them. And where names are given, an annotation or an extra column stays selected only if it is among them. The method begins by undoing what does not apply to a row that will not become an instance: it turns `Query.select_related` off and clears the names that `QuerySet.defer` or `QuerySet.only` recorded. A name that is no annotation or extra column is taken for a field of the model, which may be reached through relations, as `"home__country"` is from a ship, and the query adds the joins it needs; a name it cannot resolve raises `FieldError` there, as the method is called. With no names at all, the fields are every concrete field of the model, by attname, and the annotations and extra columns stay selected as they were.

The query is left with two records of what was asked. `Query.values_select` is the names of the fields alone. `Query.selected` is every name in the order given, each with where its column comes from, and is `None` when no names were given. How the compiler writes the select list from them is in [From QuerySet to SQL](../sql.md).

What follows was recorded from a running Django, on SQLite, over the models and rows that the chapter's opening page, [QuerySets](../querysets.md), lists: a Ship there has a name, a tonnage, a foreign key to its home Port, and a one-to-one field to the Sailor who is its captain. A line is a call, nested under the call that made it, or an expression that was evaluated, with what it returned after `->`, and a line that begins `SQL` is a statement as Django handed it to its cursor.

```text recording=querysets
values and values_list: the same rows, and another iterable class to make something of them
    rows = list(Ship.objects.values('name', 'tonnage'))
      QuerySet.values('name', 'tonnage')
        QuerySet._values('name', 'tonnage')
          Query.set_values(('name', 'tonnage'))
      QuerySet._fetch_all
        ValuesIterable.__iter__
          SQLCompiler.results_iter
            SQLCompiler.execute_sql
              SQL SELECT "fleet_ship"."name" AS "name", "fleet_ship"."tonnage" AS "tonnage" FROM "fleet_ship" ORDER BY 1 ASC
    rows  ->  [{'name': 'Gannet', 'tonnage': 1200}, {'name': 'Petrel', 'tonnage': 480}]
    pairs = list(Ship.objects.values_list('name', 'tonnage'))
      QuerySet.values_list('name', 'tonnage')
        QuerySet._values('name', 'tonnage')
          Query.set_values(('name', 'tonnage'))
      QuerySet._fetch_all
        ValuesListIterable.__iter__
          SQLCompiler.results_iter(tuple_expected=True)
            SQLCompiler.execute_sql
              SQL SELECT "fleet_ship"."name" AS "name", "fleet_ship"."tonnage" AS "tonnage" FROM "fleet_ship" ORDER BY 1 ASC
    pairs  ->  [('Gannet', 1200), ('Petrel', 480)]
```

The two methods went through `_values` and `set_values` with the same names, and the two statements are the same. What differs is the class that `QuerySet._fetch_all` made an instance of. In both runs `SQLCompiler.execute_sql` is written under `SQLCompiler.results_iter`: these iterables ask the compiler for rows in one call, where `ModelIterable` calls `execute_sql` itself and reads the compiler's account of the columns before it asks for a row. The model's ordering by name is written in both as a position in the select list, which is the compiler's doing.

## `values`

`QuerySet.values` takes names of fields as positional arguments and expressions as keyword arguments. It adds the keywords' names after the positional ones, calls `QuerySet._values` with both, and sets `ValuesIterable` on the clone (`django/db/models/query.py:QuerySet.values`).

```text recording=querysets
Ship.objects.all()._fields, Ship.objects.values()._fields, Ship.objects.values('name', 'home__country')._fields  ->  (None, (), ('name', 'home__country'))
list(Ship.objects.values())  ->  [{'id': 2, 'name': 'Gannet', 'tonnage': 1200, 'home_id': 2, 'captain_id': 3}, {'id': 1, 'name': 'Petrel', 'tonnage': 480, 'home_id': 1, 'captain_id': None}]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
...
list(Ship.objects.values('name', country=F('home__country')))  ->  [{'name': 'Gannet', 'country': 'Scotland'}, {'name': 'Petrel', 'country': 'Norway'}]
  SQL SELECT "fleet_ship"."name" AS "name", "fleet_port"."country" AS "country" FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") ORDER BY 1 ASC
```

The first line shows `QuerySet._fields` in its three conditions: `None` on a queryset of instances, an empty tuple after `values` with no names, which is not `None` and counts as set, and otherwise the names as they were given. The statement for `values()` selects the model's five columns with no aliases, and its dictionaries have the attnames `"home_id"` and `"captain_id"` as keys. In the last statement the expression is an annotation: the query joined the ports' table to resolve it, and selects the column under the name the keyword gave.

## `values_list`: names for expressions, `flat=True` and `named=True`

`QuerySet.values_list` takes fields and expressions alike as positional arguments, and two flags (`django/db/models/query.py:QuerySet.values_list`). It begins with the flags. `flat=True` and `named=True` together raise `TypeError`, and so does `flat=True` with more than one field.

> **Deprecated.** `flat=True` with no field at all is still accepted: the method warns with `RemovedInDjango2028Warning` and takes the attname of the model's first concrete field. The deprecation timeline has the call raising `TypeError` when the deprecation ends (`docs/internals/deprecation.txt`).

An expression given by position has no name, and it needs one: to be annotated under, to be selected as, and to be a field of a named tuple. So the method invents names:

```text recording=querysets
Ship.objects.values_list(Lower('name'), 'name', 'name')._fields  ->  ('lower1', 'name', 'name1')
list(Ship.objects.values_list(Lower('name'), 'name', 'name'))  ->  [('gannet', 'Gannet', 'Gannet'), ('petrel', 'Petrel', 'Petrel')]
  SQL SELECT LOWER("fleet_ship"."name") AS "lower1", "fleet_ship"."name" AS "name", "fleet_ship"."name" AS "name1" FROM "fleet_ship" ORDER BY 2 ASC
```

A field's name is kept as it is the first time it is met. An expression is named by a base and a number, and so is a field named a second time, which is selected again under the new name as an `F` of the field. The base is the field's own name, or the expression's default alias where it has that attribute, and otherwise the name of its class in lower case. For an aggregate the attribute is the property `Aggregate.default_alias`, and where that raises `TypeError` so does `values_list` (`django/db/models/aggregates.py:Aggregate.default_alias`) ([Annotations, ordering and the other methods that change the query](methods.md)). The number comes from one counter for the whole call, which starts at 1 and is moved on only while the name it would make is taken: it did not move between `"lower1"` and `"name1"`.

> **Why.** An expression is numbered whether or not its base would have collided with anything. A comment in the method gives the reason as backward compatibility: changing the rule could break some uses of `named=True`.

With its names settled the method calls `QuerySet._values`, the invented names among the fields and the expressions and repeated fields by keyword.

## The four iterable classes

`ValuesIterable`, `ValuesListIterable`, `FlatValuesListIterable` and `NamedValuesListIterable` each ask the queryset's query for a compiler and take their rows from `SQLCompiler.results_iter`, which sends the statement (`django/db/models/sql/compiler.py:SQLCompiler.results_iter`). None of them reads what the compiler knows about which column is which model's, and what each does to a row is small.

`ValuesIterable` pairs each value of a row with a name and yields the dictionary. The names are the keys of `Query.selected` where the query has one, which is the order the names were given in. Where it has none, as after `QuerySet.values` with no names, they are the names of the selected extra columns, `Query.extra_select`, then `Query.values_select`, then the names of the selected annotations, `Query.annotation_select`, which is the order of a row: a comment notes that the columns of `extra(select=...)` are always at its start (`django/db/models/query.py:ValuesIterable`).

`ValuesListIterable` yields nothing of its own. `ValuesListIterable.__iter__` returns the compiler's iterator, asked for with `tuple_expected=True` (`django/db/models/query.py:ValuesListIterable`). A row in which the compiler has converted a value, from what the driver returned to what the program is to have, is a list, and with that argument `results_iter` makes a tuple of every row before it hands it over.

`FlatValuesListIterable` yields the first value of each row, and does not ask for tuples (`django/db/models/query.py:FlatValuesListIterable`).

`NamedValuesListIterable` is a subclass of `ValuesListIterable`, and makes of each of its tuples an instance of a class made for the names. The names are the queryset's `QuerySet._fields` where there are any, and otherwise the query's, in the same three groups as above (`django/db/models/query.py:NamedValuesListIterable`).

The class comes from `create_namedtuple_class`, which makes a subclass, named Row, of a named tuple with those fields. The function is cached by the names it is called with, since, as its comment says, making a class is too slow to do at every evaluation (`django/db/models/utils.py:create_namedtuple_class`). The class has a `__reduce__` of its own, which pickles a row as its names and its values, and unpickling makes the class again from the names (`django/db/models/utils.py:unpickle_named_row`).

```text recording=querysets
list(Ship.objects.values_list('name', flat=True))  ->  ['Gannet', 'Petrel']
  SQL SELECT "fleet_ship"."name" AS "name" FROM "fleet_ship" ORDER BY 1 ASC
list(Ship.objects.values_list('name', 'tonnage', named=True))  ->  [Row(name='Gannet', tonnage=1200), Row(name='Petrel', tonnage=480)]
  SQL SELECT "fleet_ship"."name" AS "name", "fleet_ship"."tonnage" AS "tonnage" FROM "fleet_ship" ORDER BY 1 ASC
```

> **Trap.** `NamedValuesListIterable` reads the names from `_fields`, and `QuerySet.annotate` does not add to `_fields`. An annotation added after `QuerySet.values_list` with names and `named=True` is selected and is in every row, by position, and the row's class has no field for it. `ValuesIterable` is not caught the same way: it reads `Query.selected`, to which `Query.add_annotation` adds the annotation's name.

Here a count is added after `values_list('name', named=True)`, and each row is asked for its length and for the fields of its class:

```text recording=querysets
[(len(row), row._fields) for row in Ship.objects.values_list('name', named=True).annotate(hands=Count('crew')).order_by('name')]  ->  [(2, ('name',)), (2, ('name',))]
  SQL SELECT "fleet_ship"."name" AS "name", COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1 ORDER BY 1 ASC
```

Each of the two rows has two values, and a class of one field.

## A query assigned to a queryset

`QuerySet.query` is a property with a setter, and the setter knows about `QuerySet.values`. When the query assigned to it has anything in `Query.values_select`, it sets `ValuesIterable` as the queryset's iterable class, and then stores the query (`django/db/models/query.py:QuerySet.query`, `django/db/models/sql/query.py:Query.values_select`).

Nothing under `django/` assigns to the property: `QuerySet.__init__` stores the query it is given without going through the setter, and a clone is made by calling the class. The setter is for a program that keeps a query and puts it back. The documentation describes pickling a queryset's `query` alone and assigning the unpickled object to a new queryset of the model (`docs/ref/models/querysets.txt`). The class is all the setter restores: `QuerySet._fields` is kept on the queryset and not on the query, so the query that is assigned brings none with it. Here the query of a `QuerySet.values_list` queryset is assigned to a new queryset of ships, and the queryset is then asked for its class, its `_fields` and its rows:

```text recording=querysets
blank = Ship.objects.all(); blank.query = Ship.objects.values_list('name').query
blank._iterable_class.__name__, blank._fields, list(blank)  ->  ('ValuesIterable', None, [{'name': 'Gannet'}, {'name': 'Petrel'}])
  SQL SELECT "fleet_ship"."name" AS "name" FROM "fleet_ship" ORDER BY 1 ASC
```

The rows come back as dictionaries where the queryset the query was taken from would have yielded tuples, which the documentation warns of, and `_fields` is still `None`. And since the test is on `values_select`, which holds the names of fields, a query whose `values` named nothing but expressions does not change the class.

## `dates` and `datetimes`

`QuerySet.dates` and `QuerySet.datetimes` return the distinct values of one date or datetime field, each cut down to its year, month, week or day, and for `datetimes` also to its hour, minute or second. Neither has machinery of its own. Each is a chain of these methods of `QuerySet`, called in this order (`django/db/models/query.py:QuerySet.dates`, `django/db/models/query.py:QuerySet.datetimes`):

1. `QuerySet.annotate`, with two annotations: a `Trunc` of the field to the kind asked for, under the name `"datefield"` or `"datetimefield"`, and the field itself as an `F`, under `"plain_field"`.
2. `QuerySet.values_list` of the first annotation, with `flat=True`.
3. `QuerySet.distinct`.
4. `QuerySet.filter` on `"plain_field"`, to leave out the rows where the field is null.
5. `QuerySet.order_by` on the first annotation, descending where the caller asked for `"DESC"`.

Before the chain each method checks its arguments, and raises `ValueError` for a kind or an order it does not know. `datetimes` also settles the time zone the values are cut down in: where `USE_TZ` is on, the one it was given, or else the current time zone; where it is off, none.

```text recording=querysets
list(Voyage.objects.dates('sailed', 'year'))  ->  [datetime.date(2025, 1, 1), datetime.date(2026, 1, 1)]
  SQL SELECT DISTINCT django_date_trunc(%s, "fleet_voyage"."sailed", %s, %s) AS "datefield" FROM "fleet_voyage" WHERE "fleet_voyage"."sailed" IS NOT NULL ORDER BY 1 ASC with params ('year', None, None)
```

The second annotation is on the query for the condition to refer to, and is not selected, since `values_list` named the first alone: the statement has it only in its where clause, as the test for null. `"django_date_trunc"` is a function that Django registers with SQLite, and another backend cuts a date down in SQL of its own (`django/db/backends/sqlite3/_functions.py:register`). What comes back is a queryset like any other after `values_list`, which can be refined further, and which refuses what such a queryset refuses.

## After `values`

`QuerySet._fields` is how the rest of the class knows that `QuerySet.values` or `QuerySet.values_list` has been called. `QuerySet._clone` copies it, so the mark stays through whatever is chained afterwards (`django/db/models/query.py:QuerySet._clone`). These methods of `QuerySet` test it, and raise `TypeError` when it is not `None`: `QuerySet.select_related`, `QuerySet.defer`, `QuerySet.only`, `QuerySet.delete` and `QuerySet.contains`.

The refusal runs one way. `values` called after `select_related` or after `only` raises nothing, and `Query.set_values` turns the one off and clears the other (`django/db/models/sql/query.py:Query.set_values`).

`QuerySet.annotate` reads the mark and does something different for it: it checks a new annotation's name against `_fields` where it would have checked the model's fields, and for an aggregate added after `values` it has the grouping worked out from what `values` selected and not from the model's fields ([Annotations, ordering and the other methods that change the query](methods.md)).
