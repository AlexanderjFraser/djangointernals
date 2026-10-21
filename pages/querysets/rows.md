---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From rows to instances: `ModelIterable`

`ModelIterable` is the iterable class of an ordinary queryset: `ModelIterable.__iter__` runs the query, makes a model instance of each row with `Model.from_db`, and sets each annotation the query selects on it as an attribute.

What a statement returns is rows, and a **row** is a sequence of values with no names in it: the fourth value means whatever the fourth item of the statement's select list said. An instance wants the opposite. It wants each value under the **attname** of a field, the name of the attribute that holds the field's value (`"ship_id"` for a sailor's foreign key to a ship); a state that says which database it came from; and, for a relation the program is about to follow, the related object already in place. The step from one to the other has to know what the compiler selected and in what order, so it is taken by an object that works with the compiler directly: an instance of the queryset's **iterable class**, which is `ModelIterable` on a new queryset; `QuerySet.values` and `QuerySet.values_list` set another, which makes no instances ([`values` and `values_list`: rows as dictionaries and tuples](values.md)). When the iterable is made, and what becomes of the instances it yields, is told in [Evaluation and the result cache](evaluation.md).

## An iterable: `BaseIterable`

The iterable classes share a small base, `BaseIterable`, and `BaseIterable.__init__` keeps three things: the queryset, whether the compiler is to be asked for a chunked fetch, and how many rows to ask the cursor for at a call, which is `GET_ITERATOR_CHUNK_SIZE`, 100, unless another number is given (`django/db/models/query.py:BaseIterable`). `QuerySet._fetch_all` makes one from the queryset alone and takes a list of all it yields; `QuerySet.iterator` has one made with the other two given as well.

The base class has no `__iter__`. Each subclass has its own, and that method is where the statement that fetches the queryset's rows is sent and each row is made into something. `BaseIterable.__aiter__` is the way in for the `async for` that `QuerySet.aiterator` runs over the iterable, and belongs to [The asynchronous methods of a queryset](async.md).

## What the compiler has ready

`ModelIterable.__iter__` starts by reading three things off its queryset: the alias of the database, from `QuerySet.db`; a compiler for that database, from the query's `Query.get_compiler`; and the queryset's **fetch mode**, the object that decides how an instance later fetches what is missing from it ([Deferred fields and the fetch modes](../instance/fetching.md)) (`django/db/models/query.py:ModelIterable.__iter__`, `django/db/models/sql/query.py:Query.get_compiler`). The alias is read once, and goes to `Model.from_db` with every row of the run.

Then the iterable calls `SQLCompiler.execute_sql`, which composes the statement and sends it, unless composing it raises `EmptyResultSet`, as it does for a queryset made by `QuerySet.none`: then nothing is sent, and the iterable is given no rows (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`).

To compose the statement the compiler had to settle what is selected, and it keeps what it settled. `SQLCompiler.setup_query` stores the three results of `SQLCompiler.get_select` on the compiler, where until then there was `None`, and the iterable reads them as soon as `execute_sql` has returned (`django/db/models/sql/compiler.py:SQLCompiler.setup_query`, `django/db/models/sql/compiler.py:SQLCompiler.get_select`).

| attribute | what it holds |
|---|---|
| `SQLCompiler.select` | what the query selects, in order, without anything the compiler adds to the statement's select list only for an ordering: for each a tuple of the expression selected, its SQL with its parameters, and its alias or `None` |
| `SQLCompiler.klass_info` | which columns are which model's: a dictionary for the queryset's model with the positions of its columns, and inside it one for each related model the query was asked to select with it |
| `SQLCompiler.annotation_col_map` | for each selected column that has an alias, the alias and the column's position |

*The three results of `SQLCompiler.get_select` that `SQLCompiler.setup_query` keeps on a compiler for the iterable to read.*

What follows was recorded from a running Django, on SQLite, over the models of [Models and fields](../models.md) and the rows that the chapter's opening page, [QuerySets](../querysets.md), lists. A Sailor has a foreign key to a Ship, `"ship"`. A Ship has a foreign key to a Port, `"home"`, and a one-to-one field to a Sailor that may be null, `"captain"`, whose other end is a sailor's `"command"`. And an Officer is a child of Sailor with a table of its own. In a recording a line is a call, nested under the call that made it, or an expression that was evaluated, with what it returned after `->`, and a line that begins `SQL` is a statement as Django handed it to its cursor. Here a compiler was asked for by hand, told to compose the statement, and its `select` and `klass_info` written down, for a queryset of sailors that follows two relations: from a sailor to its ship, and from the ship to its home port.

```text recording=querysets
What the compiler hands the iterable for Sailor.objects.select_related('ship__home'): the columns, and which of them are whose
    joined = Sailor.objects.select_related('ship__home').order_by('id')[:2]
    compiler = joined.query.get_compiler('default'); compiler.as_sql()
    select[0]: crew_sailor.id
    select[1]: crew_sailor.name
    select[2]: crew_sailor.ship_id
    select[3]: crew_sailor.signed_on
    select[4]: fleet_ship.id
    select[5]: fleet_ship.name
    select[6]: fleet_ship.tonnage
    select[7]: fleet_ship.home_id
    select[8]: fleet_ship.captain_id
    select[9]: fleet_port.id
    select[10]: fleet_port.name
    select[11]: fleet_port.country
    klass_info: model Sailor, select_fields [0, 1, 2, 3]
      klass_info: model Ship, reached by Sailor.ship, reverse=False, from_parent=False, select_fields [4, 5, 6, 7, 8]
        klass_info: model Port, reached by Ship.home, reverse=False, from_parent=False, select_fields [9, 10, 11]
```

`klass_info` is a tree. Its root is the dictionary for the queryset's own model, with the model under `"model"` and the positions of its columns under `"select_fields"`. Where the query has `Query.select_related` set, the root also has `"related_klass_infos"`, a list of dictionaries of the same kind, one for each relation followed from that model. Each of those adds the field the relation belongs to, whether it was followed in reverse, whether the related model is a child of the one it was reached from, two functions that will tie the two instances together, and a list of its own for the relations followed from there. How the compiler builds the tree and the joins that go with it is told in [`select_related`: related objects from the same row](../relations/select-related.md); the iterable only reads it.

## One instance from one row

Before its loop over the rows, `ModelIterable.__iter__` works out once what it will do to every row. From the root of `SQLCompiler.klass_info` it takes the model class and the positions of the model's columns, which it treats as one run from the first position to the last, and from `SQLCompiler.select` the attnames that go with that run. Then, for each row that `SQLCompiler.results_iter` yields, it cuts the run out of the row and calls `Model.from_db` with the alias, the names and the values (`django/db/models/query.py:ModelIterable.__iter__`, `django/db/models/sql/compiler.py:SQLCompiler.results_iter`). What `from_db` makes of them is told in [An instance and its state](../instance/state.md), and what follows from a list of names that `QuerySet.defer` or `QuerySet.only` has shortened in [Deferred fields in a queryset: `defer` and `only`](deferred.md).

The new instance is not yielded at once. In this order, the loop adds a weak reference to it to the list of **peers**, the instances made of the rows of this one statement, if the fetch mode is one that keeps track of them ([Deferred fields and the fetch modes](../instance/fetching.md#peers-a-list-for-each-run-of-a-query)); gives the row and the instance to each related populator; sets each annotation on it as an attribute; and looks among the queryset's known related objects for one the instance points at.

> **Deprecated.** `from_db` is called with the queryset's fetch mode as the keyword argument `"fetch_mode"`, which `Model.from_db` has accepted since 6.1. A model whose own `from_db` accepts neither that keyword nor arbitrary keywords is still served: `_get_from_db` finds this out before the loop, warns with `RemovedInDjango2028Warning`, and has the override called without the mode, so the instances are not given the queryset's (`django/db/models/query.py:_get_from_db`).

## Annotations become attributes

`SQLCompiler.annotation_col_map` gives the position in the row of every selected column that has an alias. For a queryset of instances those are the annotations the query selects and the columns added with `extra(select=...)`. For each, the loop of `ModelIterable.__iter__` sets the row's value on the instance under the alias with `setattr` (`django/db/models/query.py:ModelIterable.__iter__`). For an annotation, what results is an ordinary attribute: no field stands behind it and `Model.from_db` was not given it.

An annotation made with `QuerySet.alias` is on the query for conditions and orderings to refer to and is not selected, so it has no position in the row and nothing is set ([Annotations, ordering and the other methods that change the query](methods.md)).

```text recording=querysets
[(ship.name, ship.hands) for ship in Ship.objects.annotate(hands=Count('crew')).order_by('name')]  ->  [('Gannet', 2), ('Petrel', 2)]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" ORDER BY "fleet_ship"."name" ASC
...
[(ship.name, hasattr(ship, 'hands')) for ship in Ship.objects.alias(hands=Count('crew')).filter(hands__gt=1)]  ->  [('Petrel', False), ('Gannet', False)]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" HAVING COUNT("crew_sailor"."id") > %s with params (1,)
```

In the first statement the count is the last column of the select list, and each Ship has it as `"hands"`. In the second the count appears only in the `"HAVING"` clause, and `hasattr` finds nothing on either ship.
