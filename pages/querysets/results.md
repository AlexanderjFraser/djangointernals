---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `get`, `first`, `count` and the other methods that run a query at once

`QuerySet.get`, `QuerySet.first`, `QuerySet.last`, `QuerySet.earliest`, `QuerySet.latest`, `QuerySet.count`, `QuerySet.exists`, `QuerySet.contains`, `QuerySet.aggregate`, `QuerySet.in_bulk` and `QuerySet.explain` do not return a queryset. Each answers when it is called, and returns one thing the queryset yields, a number, a truth value, a dictionary or a piece of text.

Most methods of a queryset describe a statement and wait. These are the ones a program calls when it wants an answer: the one row with this name, whether there is any row at all, how many there are, the sum of a column. A queryset could answer most of them by evaluating itself and looking through its list, and that would fetch every row to return one of them, or a number. So a method of this kind shapes the statement to its answer before anything is sent: a condition added, a limit of one row or of twenty-one, an ordering added or taken away, the columns replaced by a constant or by an aggregate. `explain` shapes nothing, and neither does `in_bulk` where it is given no list and has no column to add. And each does the shaping on a clone of the queryset or on a copy of its query, so that the queryset it was called on is left as it was.

| the method | the statement it sends | what it returns | where the queryset has a result cache |
|---|---|---|---|
| `get` | the queryset's, with the conditions given, without an ordering unless it is sliced or has distinct fields, and limited to 21 rows at most in every case but one | what the queryset yields for the one row, or an exception for none and for several | not read |
| `first`, `last` | the queryset's, ordered by the primary key where it has to be given an ordering, the ordering reversed for `last`, limited to one row | what the queryset yields for the one row, or `None` | `first` slices the list where the queryset needs no new ordering; `last` does not read it |
| `earliest`, `latest` | the queryset's, ordered by the fields named, the other way round for `latest`, limited to one row | what the queryset yields for the one row, or an exception for none | not read |
| `count` | a count of the queryset's rows | an integer | the list's length |
| `exists` | a constant, limited to one row | `True` or `False` | the list's truth |
| `contains` | as `exists`, with a condition on the object's key | `True` or `False` | whether the object is in the list |
| `aggregate` | the aggregates, in place of the queryset's columns | a dictionary of the values, by alias | not read |
| `in_bulk` | the queryset's, with the values given as a condition | a dictionary of what the queryset yields, by key | not read |
| `explain` | the queryset's, after the backend's prefix for an explanation | a string | not read |

*What each of these methods sends and returns. `count`, `exists` and `contains` are recorded with and without a result cache in [Evaluation and the result cache](evaluation.md).*

Each has an asynchronous twin, `aget`, `acount` and the rest ([The asynchronous methods of a queryset](async.md)).

## `get`: one row, or an exception

`QuerySet.get` is a call of `QuerySet.filter` and an evaluation, with two things done between them that suit a query expected to find one row (`django/db/models/query.py:QuerySet.get`).

It begins with a clone. The arguments go to `filter`, so `get` takes what `filter` takes, keyword conditions and `Q` objects, and they join the conditions the queryset has already ([`filter`, `exclude` and `Q` objects](filters.md)). A combined queryset, the result of `QuerySet.union` and its relatives, refuses `filter`: for one of those `get` raises `NotSupportedError` if it was given arguments, and otherwise takes a plain clone from `QuerySet._chain` ([Combining querysets: the operators and `union`](combining.md)).

Then the clone loses its ordering, which the docstring of Django's own test of the step calls an optimization (`tests/queries/tests.py:Queries1Tests.test_get_clears_ordering`). Where no slice has been taken from the queryset's query, which is what `Query.can_filter` asks, and it has no **distinct fields**, the names given to `QuerySet.distinct` and kept as `Query.distinct_fields`, `get` calls `QuerySet.order_by` on the clone with no names, which clears any ordering it was given and switches the model's default ordering off.

Then the clone is limited, by `Query.set_limits`, to `MAX_GET_RESULTS` rows, which is 21; the one case in which it is not is told below. And then it is evaluated: `get` takes `len` of the clone, which fills the clone's result cache as any evaluation does ([Evaluation and the result cache](evaluation.md)), and the length decides what happens next.

What follows was recorded from a running Django, on SQLite, over the rows that the chapter's opening page, [QuerySets](../querysets.md), lists: a line at the left is a line of Python as it was run, the lines under it are the calls it set going, nested as they were made and only those this passage is about, `->` is what a line or a call returned or raised, and a line that begins `SQL` is a statement as Django handed it to its cursor.

```text recording=querysets
Ship.objects.get(name='Petrel')
  QuerySet.get(name='Petrel')
    QuerySet.filter(name='Petrel')
    QuerySet.order_by
      Query.clear_ordering(force=True, clear_default=False)
      Query.add_ordering
    Query.set_limits(high=21)
    QuerySet.__len__
      QuerySet._fetch_all
        ModelIterable.__iter__
          SQLCompiler.execute_sql
            SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Petrel',)
...
      -> 1
    -> <Ship: Petrel>
```

Ship is ordered by name by default, and the statement has no `ORDER BY`. It has a `LIMIT 21`, the length of the clone was 1, and the one instance made is what `get` returned: the first item of the clone's result cache.

### The three outcomes

`QuerySet.get` returns the one item of the clone's result cache where the clone's length is one. A length of zero raises the model's `Model.DoesNotExist`. Anything else raises its `Model.MultipleObjectsReturned`, with a message that says how many rows there were, as far as `get` knows. How much it knows depends on the limit: fewer than 21 rows is an exact number, and 21 rows means only that there were at least that many, which the message puts as more than 20. The office of the example has twenty-five logbooks, titled Log 1 to Log 25:

```python
# harbour/office/models.py
class Logbook(models.Model):
    title = models.CharField(max_length=60)
```

```text recording=querysets
Ship.objects.get(name='Skua')  ->  raises DoesNotExist: Ship matching query does not exist.
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Skua',)
Sailor.objects.get(ship=petrel)  ->  raises MultipleObjectsReturned: get() returned more than one Sailor -- it returned 2!
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s LIMIT 21 with params (1,)
Logbook.objects.get(title__startswith='Log')  ->  raises MultipleObjectsReturned: get() returned more than one Logbook -- it returned more than 20!
  SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook" WHERE "office_logbook"."title" LIKE %s ESCAPE '\' LIMIT 21 with params ('Log%',)
Logbook.objects.get()  ->  raises MultipleObjectsReturned: get() returned more than one Logbook -- it returned more than 20!
  SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook" LIMIT 21
```

The `LIKE ... ESCAPE` in the statement for the titles is the way SQLite's backend writes the lookup `"startswith"`.

The two exceptions are classes of the model itself, made with it ([`ModelBase`: a class statement becomes a model](../models/metaclass.md)). What `get` raises is the class of the queryset's model, with the model's name in the message.

The rows are fetched by the clone: a result cache that the queryset itself has is not consulted, and it is not given one.

### Where the ordering is kept, and where the limit is not set

`QuerySet.get` keeps the ordering in two cases: a query a slice has been taken from, and a query with distinct fields. A comment in `Query.get_aggregation`, the method behind `QuerySet.count` and `QuerySet.aggregate`, names the same two as the queries that need their ordering (`django/db/models/sql/query.py:Query.get_aggregation`). Of the backends Django ships only PostgreSQL's writes distinct fields, as `DISTINCT ON`, which the reference documentation says gives the first row for each value and, with no order specified, some arbitrary row (`docs/ref/models/querysets.txt`).

```text recording=querysets
Sailor.objects.order_by('name')[:1].get().name  ->  'Ada'
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."name" ASC LIMIT 1
Sailor.objects.order_by('name')[:2].get()  ->  raises MultipleObjectsReturned: get() returned more than one Sailor -- it returned 2!
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."name" ASC LIMIT 2
Sailor.objects.distinct().get(name='Ada').name  ->  'Ada'
  SQL SELECT DISTINCT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s LIMIT 21 with params ('Ada',)
```

A sliced queryset can be given no conditions, since `filter` refuses it any, for the reason [Evaluation and the result cache](evaluation.md) gives, but `get()` with none works on it: the ordering stays, and the limit of 21 is applied within the limit the query has already, so the first statement ends `LIMIT 1` and the second `LIMIT 2` (`django/db/models/sql/query.py:Query.set_limits`). `distinct` with no field names is not the case of distinct fields: its statement is an ordinary `get`, with the limit of 21.

The limit is left off in one case: a clone that locks its rows, with `Query.select_for_update` set, on a backend whose feature `BaseDatabaseFeatures.supports_select_for_update_with_limit` is false. The compiler refuses a limit on such a statement there, with `NotSupportedError` (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). The base class has the feature true, and among the backends Django ships Oracle's sets it false (`django/db/backends/oracle/features.py:DatabaseFeatures.supports_select_for_update_with_limit`). For such a clone every matching row is fetched, and the message for several gives their true number.

`QuerySet.get_or_create` and `QuerySet.update_or_create` are built on `get` ([Creating, updating and deleting through a queryset](writing.md)).

## `first` and `last`

`QuerySet.first` and `QuerySet.last` return what the queryset yields for one row, an instance unless `QuerySet.values` or `QuerySet.values_list` came first, or `None` where the queryset has no row. Which row is first depends on an ordering, and each method begins by deciding whether the queryset has to be given one (`django/db/models/query.py:QuerySet.first`).

The queryset is used as it stands in two cases. One is that it is ordered: `QuerySet.ordered` is true, as it is for a query with an ordering of its own, for one that has the model's default ordering and is not grouped, and for an empty queryset ([Annotations, ordering and the other methods that change the query](methods.md)). The other is that its query has `Query.default_ordering` off, which is the mark `order_by()` with no names leaves: a program that cleared the ordering on purpose is not given another. In the case that remains, a queryset with no ordering that nobody asked to have none, the method orders it by the primary key: `first` takes `order_by("pk")` of it, and `last` takes `order_by("-pk")`.

`first` then takes the slice `[:1]` of the queryset it settled on and returns the first thing a loop over the slice yields. A loop that yields nothing falls through, and the method returns `None`. `last`, where the queryset is used as it stands, takes the same slice of `QuerySet.reverse` of it: `last` is `first` of the queryset reversed.

```text recording=querysets
Sailor.objects.first()
  QuerySet.first
    QuerySet.order_by('pk')
      Query.clear_ordering(force=True, clear_default=False)
      Query.add_ordering('pk')
    QuerySet.__getitem__(slice(None, 1, None))
      Query.set_limits(high=1)
      -> a SailorQuerySet of Sailor, no result cache
    QuerySet.__iter__
      QuerySet._fetch_all
        ModelIterable.__iter__
          SQLCompiler.execute_sql
            SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC LIMIT 1
...
Ship.objects.first()
  QuerySet.first
    QuerySet.__getitem__(slice(None, 1, None))
      Query.set_limits(high=1)
      -> a QuerySet of Ship, no result cache
    QuerySet.__iter__
      QuerySet._fetch_all
        ModelIterable.__iter__
          SQLCompiler.execute_sql
            SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC LIMIT 1
...
Ship.objects.last()
  QuerySet.last
    QuerySet.reverse
    QuerySet.__getitem__(slice(None, 1, None))
      Query.set_limits(high=1)
      -> a QuerySet of Ship, no result cache
    QuerySet.__iter__
      QuerySet._fetch_all
        ModelIterable.__iter__
          SQLCompiler.execute_sql
            SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" DESC LIMIT 1
```

Sailor has no default ordering, so its queryset was ordered by `"pk"`, sliced and iterated. Ship has one, and both methods use its queryset as it stands.

```text recording=querysets
Sailor.objects.filter(name='Nobody').first(), Sailor.objects.none().last()  ->  (None, None)
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s ORDER BY "crew_sailor"."id" ASC LIMIT 1 with params ('Nobody',)
Sailor.objects.order_by('-name').first().name, Sailor.objects.order_by('-name').last().name  ->  ('Dag', 'Ada')
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."name" DESC LIMIT 1
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."name" ASC LIMIT 1
...
Sailor.objects.values('ship').annotate(n=Count('id')).first()  ->  raises TypeError: Cannot use QuerySet.first() on an unordered queryset performing aggregation. Add an ordering with order_by().
Sailor.objects.values('ship').annotate(n=Count('id')).order_by('ship').first()  ->  {'ship': 1, 'n': 2}
  SQL SELECT "crew_sailor"."ship_id" AS "ship", COUNT("crew_sailor"."id") AS "n" FROM "crew_sailor" GROUP BY 1 ORDER BY 1 ASC LIMIT 1
```

The first line has one statement under it for two answers of `None`: the empty queryset that `QuerySet.none` returns sends nothing. In the second, a queryset with an ordering of its own is used as it stands by both methods, and the two statements differ in the direction alone.

### An unordered queryset that aggregates

Before `first` or `last` orders by the primary key it calls `QuerySet._check_ordering_first_last_queryset_aggregation` with its own name. That raises `TypeError` where the query groups by an explicit list of columns, with a tuple as its `Query.group_by`, and the primary key is not among them (`django/db/models/query.py:QuerySet._check_ordering_first_last_queryset_aggregation`); the documentation says of `first` that ordering by the key can affect the results of an aggregation, a field named in `order_by` being one the rows are grouped by too (`docs/ref/models/querysets.txt`, `docs/topics/db/aggregation.txt`). A queryset made by `values` and then annotated with an aggregate is grouped in that way: the last lines of the recording group sailors by ship and count them. With an ordering, which the message asks for, the method takes its other branch, where the check is not made.

### With a result cache, and after a slice

`first` on a queryset that is used as it stands does not always send a statement. Where the queryset has a result cache, its slice `[:1]` is a slice of the list ([Evaluation and the result cache](evaluation.md)), and `first` returns the list's first item. `last` gets no such help: `reverse` returns a clone, and so does `order_by`, and a clone has no result cache. Here by_name, the sailors in order of name, is evaluated first:

```text recording=querysets
by_name = Sailor.objects.order_by('name'); list(by_name)
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."name" ASC
by_name.first()  ->  <Sailor: Ada>
by_name.last()  ->  <Sailor: Dag>
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."name" DESC LIMIT 1
```

`first` sent nothing, and `last` a statement of its own.

A sliced queryset refuses both `order_by` and `reverse`. So `last` raises `TypeError` on any sliced queryset, and `first` does on one that it would have to order; on a sliced queryset used as it stands, `first` takes a slice of the slice.

### An ordering cleared on purpose

> **Changed in 6.1.** `first` and `last` no longer order by the primary key a queryset whose ordering has been forcibly cleared by calling `order_by` with no arguments (`docs/releases/6.1.txt`).

For a queryset so cleared, `last` has nothing to reverse, and the two methods send the same statement:

```text recording=querysets
Ship.objects.order_by().first().name, Ship.objects.order_by().last().name  ->  ('Petrel', 'Petrel')
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" LIMIT 1
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" LIMIT 1
```

## `earliest` and `latest`

`QuerySet.earliest` and `QuerySet.latest` take the ordering from their caller and end in `QuerySet.get`. Each refuses a sliced queryset with `TypeError`. Then `earliest` calls `QuerySet._earliest` on the queryset, and `latest` calls it on `QuerySet.reverse` of the queryset (`django/db/models/query.py:QuerySet.latest`).

`_earliest` orders by the field names it is given. Given none, it reads the model's `Options.get_latest_by`, the `get_latest_by` of the model's `Meta`, which may be one name or a list of them (`django/db/models/options.py:Options.get_latest_by`); and where that is `None` too it raises `ValueError`. It then makes a clone, limits the clone to one row, clears whatever ordering the clone had, by force, adds the names as its ordering, and returns `get()` of it (`django/db/models/query.py:QuerySet._earliest`).

```text recording=querysets
Sailor.objects.latest('signed_on', 'name')
  QuerySet.latest('signed_on', 'name')
    QuerySet.reverse
    QuerySet._earliest('signed_on', 'name')
      Query.set_limits(high=1)
      Query.clear_ordering(force=True)
      Query.add_ordering('signed_on', 'name')
      QuerySet.get
        QuerySet.filter
        Query.set_limits(high=21)
        QuerySet.__len__
          QuerySet._fetch_all
            ModelIterable.__iter__
              SQLCompiler.execute_sql
                SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."signed_on" DESC, "crew_sailor"."name" DESC LIMIT 1
```

Inside `get` nothing more is narrowed. The clone is already sliced, so `get` leaves its ordering alone, as the absence of `QuerySet.order_by` under `QuerySet.get` shows; and the limit of 21, applied within a limit of one, leaves one. The names were not rewritten for `latest`. The clone that `reverse` made has `Query.standard_ordering` off, and the compiler wrote each of the two columns the other way round (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`).

Ending in `get` gives the two methods their outcomes. With one row at most there is never more than one, so the answer is the one item or `Model.DoesNotExist`: `earliest` and `latest` raise where `QuerySet.first` and `QuerySet.last` return `None`.

```text recording=querysets
Sailor.objects.earliest()  ->  raises ValueError: earliest() and latest() require either fields as positional arguments or 'get_latest_by' in the model's Meta.
...
Sailor.objects.filter(name='Nobody').earliest('signed_on')  ->  raises DoesNotExist: Sailor matching query does not exist.
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s ORDER BY "crew_sailor"."signed_on" ASC LIMIT 1 with params ('Nobody',)
```

In the first line Sailor has no `Meta`, so no `get_latest_by`, and no field name was given. In the second no sailor has the name.

## `count`, `exists` and `contains`

`QuerySet.count`, `QuerySet.exists` and `QuerySet.contains` are answered from the result cache where the queryset has one, and by a statement of their own where it has not. [Evaluation and the result cache](evaluation.md) has each of them recorded both ways, call by call.

```text recording=querysets
Ship.objects.count()  ->  2
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
Ship.objects.filter(tonnage__gt=1000).exists()  ->  True
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s LIMIT 1 with params (1, 1000)
```

`QuerySet.count` without a result cache hands the query to `Query.get_count`. That method copies the query and has `Query.get_aggregation` compute `Count("*")` over it under the alias `"__count"`, which is the alias in the statement (`django/db/models/sql/query.py:Query.get_count`). So what is said of `get_aggregation` below holds for a count, the subquery included.

`QuerySet.exists` without a result cache asks `Query.has_results`, which has a narrowed copy of the query made by `Query.exists` and asks the copy's compiler whether a row comes back (`django/db/models/sql/query.py:Query.exists`). The narrowing shows in the recorded statement: no columns, no ordering although Ship has a default one, a limit of one row, and the constant 1 selected under the alias `"a"`.

`QuerySet.contains` asks whether one object is among the queryset's rows, and compares models before it looks for the object (`django/db/models/query.py:QuerySet.contains`). It first refuses a combined queryset, with `NotSupportedError`, and a queryset made by `QuerySet.values` or `QuerySet.values_list`, with `TypeError`. Then it compares the concrete model of the object with that of the queryset's model, and where they differ answers `False` at once; an argument that is not a model instance, which it knows by its having no `Model._meta`, raises `TypeError` there. Only after that is an object whose primary key is not set refused, with `ValueError`. With a result cache the answer is then whether the object is in the list, which Python settles with `Model.__eq__`: the same concrete model and the same key (`django/db/models/base.py:Model.__eq__`). Without one it is `exists` of the queryset filtered by `"pk"` equal to the object's key.

A model's concrete model is the model itself, unless it is a proxy, whose concrete model is that of the model it stands for ([Inheritance: abstract bases, parents with tables and proxies](../models/inheritance.md)). So an instance of a child model cannot be contained in a queryset of its parent, although its row is in the parent's table, and an instance of a proxy can be contained in a queryset of the model it stands for. Because the models are compared before the key is looked at, an unsaved object of another model is answered with `False` and not with the error. In the recording cora is an Officer, and Officer a child of Sailor with a table of its own; Veteran is a proxy of Sailor whose manager adds a condition of its own:

```text recording=querysets
Ship.objects.contains(petrel)  ->  True
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 1 with params (1, 1)
Ship.objects.contains(ada)  ->  False
type(cora).__name__, Sailor.objects.contains(cora), Officer.objects.contains(cora)  ->  ('Officer', False, True)
  SQL SELECT %s AS "a" FROM "crew_officer" WHERE "crew_officer"."sailor_ptr_id" = %s LIMIT 1 with params (1, 3)
Ship.objects.contains('Petrel')  ->  raises TypeError: 'obj' must be a model instance.
Ship.objects.contains(Ship(name='Skua'))  ->  raises ValueError: QuerySet.contains() cannot be used on unsaved objects.
...
Veteran.objects.contains(ada), Sailor.objects.contains(Veteran.objects.get(pk=1))  ->  (True, True)
  SQL SELECT %s AS "a" FROM "crew_sailor" WHERE ("crew_sailor"."signed_on" < %s AND "crew_sailor"."id" = %s) LIMIT 1 with params (1, '2020-01-01 00:00:00', 1)
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE ("crew_sailor"."signed_on" < %s AND "crew_sailor"."id" = %s) LIMIT 21 with params ('2020-01-01 00:00:00', 1)
  SQL SELECT %s AS "a" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 1 with params (1, 1)
```

Cora is not contained in the sailors and is contained in the officers, and the one statement under that line is the officers'. A sailor is not contained in the ships, and that line has no statement under it. Ada is contained in the veterans, and a Veteran is contained in the sailors; the statement with `LIMIT 21` under that line is the `get` that fetched the Veteran.

## `aggregate`

`QuerySet.aggregate` computes values over all the queryset's rows at once and returns them in a dictionary (`django/db/models/query.py:QuerySet.aggregate`).

It makes three checks of its own. A queryset with distinct fields is refused with `NotImplementedError`. Each argument, positional or keyword, has to be an expression, something that has a `resolve_expression`: `QuerySet._validate_values_are_expressions` raises `TypeError` for anything else, a string for one. And each positional argument is returned under its default alias, `"tonnage__sum"` for a sum of the tonnage, and is refused with a `TypeError` that asks for an alias where it has none ([Annotations, ordering and the other methods that change the query](methods.md)). The positional arguments then join the keyword ones under those names, one of them replacing a keyword argument that has the same name.

```text recording=querysets
Ship.objects.aggregate(Sum('tonnage'))  ->  {'tonnage__sum': 1680}
  SQL SELECT SUM("fleet_ship"."tonnage") AS "tonnage__sum" FROM "fleet_ship"
Ship.objects.aggregate(total=Sum('tonnage'), ships=Count('id'))  ->  {'total': 1680, 'ships': 2}
  SQL SELECT SUM("fleet_ship"."tonnage") AS "total", COUNT("fleet_ship"."id") AS "ships" FROM "fleet_ship"
Ship.objects.aggregate(Sum('tonnage') + 1)  ->  raises TypeError: Complex aggregates require an alias
Ship.objects.aggregate('tonnage')  ->  raises TypeError: QuerySet.aggregate() received non-expression(s): tonnage.
```

The work is the query's. `aggregate` takes a copy of the query from `Query.chain` and calls `Query.get_aggregation` on the copy with the queryset's database and the dictionary of expressions (`django/db/models/sql/query.py:Query.get_aggregation`). That method resolves each expression against the query, raising `TypeError` for one that contains no aggregate, and then decides between two shapes of statement. Ordinarily it empties the copy's select clause and puts the aggregates there, which gives the statements above: one `"SELECT"` over the queryset's rows, with no `ORDER BY` although Ship has a default ordering. In other cases a clone of the copy becomes a subquery: the aggregates are selected from a statement made of it, set in parentheses (`django/db/models/sql/compiler.py:SQLAggregateCompiler.as_sql`), as the count of a union is in [Combining querysets: the operators and `union`](combining.md). Those cases include a query that is sliced, distinct or combined, one that groups by an explicit list of columns, and one that already has an aggregate among its annotations. A comment gives the reason for the first three: the aggregate has to be taken over the rows that the limit, the distinct or the set operation leaves, not applied before them.

Either way the outer query's ordering and limits are cleared, one row is fetched, and the dictionary is made of the aliases and the values of that row. Where the compiler can tell that the query matches nothing and sends no statement, each expression answers with the value it declares for an empty result: `None` as `Aggregate.empty_result_set_value` has it, 0 for `Count`, and for an aggregate that was given a plain value as `default=...`, that value. How the two shapes are written is told in [From QuerySet to SQL](../sql.md).

## `in_bulk`: a dictionary by key

`QuerySet.in_bulk` returns a dictionary that holds, under each key, what the queryset yields for the row with that key. Given a list of values it fetches the rows whose field has one of them. Given nothing it fetches every row of the queryset. The field is the primary key unless another is named, as `field_name="..."` (`django/db/models/query.py:QuerySet.in_bulk`).

A sliced queryset is refused with `TypeError`, and an empty list is answered with an empty dictionary before the field's name is looked at. Then the name is checked, since a dictionary can hold one row under a key. It is accepted on any of four grounds:

- it is `"pk"`, the default;
- the field is unique, which a primary key is too (`django/db/models/fields/__init__.py:Field.unique`);
- the field is the one field of a `UniqueConstraint` that has no condition and no expressions, which is what `Options.total_unique_constraints` lists (`django/db/models/options.py:Options.total_unique_constraints`);
- the queryset is distinct on that field and no other: `Query.distinct_fields` holds just its name.

The name of a field of the model's own that passes none of them raises `ValueError`; a name the model has no field for raises `FieldDoesNotExist`, in `Options.get_field`.

```text recording=querysets
Sailor.objects.in_bulk([1, 2])  ->  {1: <Sailor: Ada>, 2: <Sailor: Bram>}
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (%s, %s) with params (1, 2)
Sailor.objects.in_bulk([])  ->  {}
Port.objects.in_bulk()  ->  {1: <Port: Bergen>, 2: <Port: Leith>, 3: <Port: Lisbon>}
  SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" ORDER BY "fleet_port"."name" ASC
Sailor.objects.in_bulk(['Ada'], field_name='name')  ->  raises ValueError: in_bulk()'s field_name must be a unique field but 'name' isn't.
...
Sailor.objects.distinct('name').in_bulk(['Ada'], field_name='name')  ->  raises NotSupportedError: DISTINCT ON fields is not supported by this database backend
```

The call with an empty list sent nothing. The call with no list fetched every port, in the ports' default ordering: with no list, `in_bulk` iterates a plain clone. A sailor's name is not unique and is refused. The last line passed the check, being distinct on the field it named, and was refused afterwards, when the statement was compiled: SQLite's backend does not write distinct fields ([Annotations, ordering and the other methods that change the query](methods.md)).

### After `values` and `values_list`

Django itself calls `in_bulk` on a queryset that does not yield instances: `DeferredAttribute.fetch_many` fetches a deferred field for several instances at once by `in_bulk` of their keys on a flat list of the field's values (`django/db/models/query_utils.py:DeferredAttribute.fetch_many`) ([Deferred fields and fetch modes in a queryset](deferred.md)). `in_bulk` looks at the queryset's iterable class, `QuerySet._iterable_class`, to know where the key is in what that class makes of a row: an attribute of an instance, an item of a dictionary or of a tuple, or the one value of a flat list ([`values` and `values_list`: rows as dictionaries and tuples](values.md)). After `QuerySet.values` or `QuerySet.values_list`, where the name of the key's field is not among those the queryset selects, `in_bulk` selects it too, by calling the method once more with the field's name put first, and takes it out again from what it returns, but from a named tuple, which keeps it. A queryset whose iterable class is of none of these kinds is refused with `TypeError`.

```text recording=querysets
Sailor.objects.values_list('name', flat=True).in_bulk([1, 2])  ->  {1: 'Ada', 2: 'Bram'}
  SQL SELECT "crew_sailor"."id" AS "pk", "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (%s, %s) with params (1, 2)
...
Sailor.objects.values_list('name', named=True).in_bulk([1])  ->  {1: Row(pk=1, name='Ada')}
  SQL SELECT "crew_sailor"."id" AS "pk", "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (%s) with params (1,)
```

The flat list is the shape `fetch_many` asks for: the statement selects the key beside the name, and the dictionary has the name alone under each key. The named tuple has kept its key.

> **Changed in 6.1.** `in_bulk` can be called after `values` and `values_list` (`docs/releases/6.1.txt`).

### A list longer than a statement can take

With a list of values, `in_bulk` filters the queryset by the lookup `"in"` on the field and iterates the result. Where the list is longer than the backend's `BaseDatabaseOperations.bulk_batch_size` allows in one statement ([`bulk_create` and `bulk_update`](bulk.md)), it is cut into batches of that size, a filtered queryset is evaluated for each batch, and the dictionary is made from the rows of all of them. For this recording SQLite's limit on the parameters of a statement had been lowered to 10 on the connection, and the office's twenty-five logbooks were asked for by key:

```text recording=querysets
len(Logbook.objects.in_bulk(range(1, 26)))  ->  25
  SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) with params (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
  SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) with params (11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
  SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s, %s, %s, %s) with params (21, 22, 23, 24, 25)
```

## `explain`

`QuerySet.explain` returns the database's account of how it would run the queryset's statement, as a string. The work is the query's and the compiler's: `Query.explain` puts the format and the options on a copy of the query as `Query.explain_info`, and the compiler writes the backend's prefix in front of the statement and runs it (`django/db/models/sql/query.py:Query.explain`).

`Query.explain` makes one check: an option's name has to consist of letters, digits, underscores and hyphens, with no two hyphens together, or `ValueError` is raised. Whether a format or an option means anything is the backend's to say: `BaseDatabaseOperations.explain_query_prefix` in the base class refuses a format that the backend's features do not list, and any option at all, and a backend that has options takes them out before it calls the base method (`django/db/backends/base/operations.py:BaseDatabaseOperations.explain_query_prefix`).

```text recording=querysets
isinstance(Ship.objects.filter(name='Petrel').explain(), str)  ->  True
  SQL EXPLAIN QUERY PLAN SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s ORDER BY "fleet_ship"."name" ASC with params ('Petrel',)
```

The prefix `EXPLAIN QUERY PLAN` is SQLite's. What follows it is the queryset's own statement with nothing narrowed, the ordering included.
