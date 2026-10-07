---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Combining querysets: the operators and `union`

Two querysets become one in two ways. The operators `&`, `|` and `^`, which are `QuerySet.__and__`, `QuerySet.__or__` and `QuerySet.__xor__`, make a single query that holds the conditions of both. `QuerySet.union`, `QuerySet.intersection` and `QuerySet.difference` keep the two queries whole, side by side, as the parts of one compound statement.

A program that holds two querysets and wants the rows of both, or of either, could evaluate the two and work on the lists. It would then have a list, already fetched, and no longer something that the database can order, slice or count. `QuerySet` can make one queryset of two without sending anything, and the two ways of doing it are the two ways SQL has of saying it.

```text figure=two-shapes
old: the sailors who signed on before 2020        on_petrel: the sailors of the Petrel

old & on_petrel
    a clone of old, whose Query has
        where:  (signed on before 2020) AND (ship is the Petrel)
    compiled as one SELECT with one WHERE

old.union(on_petrel)
    a clone of old, whose Query has
        combinator:        "union"
        combined_queries:  0  the Query of old itself, not a copy     where: signed on before 2020
                           1  a clone of the Query of on_petrel       where: ship is the Petrel
    compiled as one SELECT for each part, with UNION between them
```

*The two shapes: what `&` and what `union` make of the same two querysets.*

A statement made of whole `"SELECT"`s with `"UNION"`, `"INTERSECT"` or `"EXCEPT"` between them is a **compound statement**. What the three methods return is a **combined queryset**, and the queries its query holds are its **parts**; many of the methods that would change a query refuse it. What an operator returns has an ordinary query, and can be refined further like any queryset. The operators need two querysets of one model. The methods compare nothing between the querysets they are given: what the parts select has only to satisfy the database.

In both, the queryset whose method is called is the **left side** and the method's argument the **right side**: Python turns an operator between two querysets into a call of the left one's method with the right one.

## The operators: one query made of two

`QuerySet.__and__`, `QuerySet.__or__` and `QuerySet.__xor__` have one outline (`django/db/models/query.py:QuerySet.__and__`, `django/db/models/query.py:QuerySet.__or__`). Two checks come first. Then, if either side is an empty queryset, one of the two operands is returned as it stands. Otherwise, in the case recorded here, the left side is cloned, the related objects that the right side already has in hand are merged into the clone's, and the clone's query is told to take the other query in: `Query.combine`, with a connector, `"AND"`, `"OR"` or `"XOR"` (`django/db/models/sql/query.py:Query.combine`).

What follows was recorded from a running Django, on SQLite, over the rows that the chapter's opening page, [QuerySets](../querysets.md), lists: a line at the left is a line of Python as it was run, the lines under it are the calls it set going, nested as they were made and only those this passage is about, `->` is what a call returned, and a line that begins `SQL` is a statement as Django handed it to its cursor. Of the four sailors, Ada and Cora signed on in 2011 and Bram and Dag in 2026, and Ada and Bram serve on the Petrel.

```text recording=querysets
old = Sailor.objects.filter(signed_on__year__lt=2020); on_petrel = Sailor.objects.filter(ship=petrel)
both = old & on_petrel
  QuerySet.__and__(a SailorQuerySet of Sailor, no result cache)
    QuerySet._check_operator_queryset(other=a SailorQuerySet of Sailor, no result cache, operator_='&')
    QuerySet._merge_sanity_check(a SailorQuerySet of Sailor, no result cache)
    QuerySet._chain  ->  a new SailorQuerySet
    QuerySet._merge_known_related_objects(a SailorQuerySet of Sailor, no result cache)
    Query.combine(rhs=a Query of Sailor, connector='AND')
either = old | on_petrel
  QuerySet.__or__(a SailorQuerySet of Sailor, no result cache)
    QuerySet._check_operator_queryset(other=a SailorQuerySet of Sailor, no result cache, operator_='|')
    QuerySet._merge_sanity_check(a SailorQuerySet of Sailor, no result cache)
    Query.can_filter
    QuerySet._chain  ->  a new SailorQuerySet
    QuerySet._merge_known_related_objects(a SailorQuerySet of Sailor, no result cache)
    Query.can_filter
    Query.combine(rhs=a Query of Sailor, connector='OR')
```

Neither operator sent a statement. Under `|` the calls written down are those of `&` with `Query.can_filter` asked twice among them, once of each side: a question about slices, taken up below. The statements came when the results were listed:

```text recording=querysets
list(both)  ->  [<Sailor: Ada>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE ("crew_sailor"."signed_on" < %s AND "crew_sailor"."ship_id" = %s) with params ('2020-01-01 00:00:00', 1)
list(either)  ->  [<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE ("crew_sailor"."signed_on" < %s OR "crew_sailor"."ship_id" = %s) with params ('2020-01-01 00:00:00', 1)
list(old ^ on_petrel)  ->  [<Sailor: Bram>, <Sailor: Cora>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE (("crew_sailor"."signed_on" < %s OR "crew_sailor"."ship_id" = %s) AND %s = (CASE WHEN "crew_sailor"."signed_on" < %s THEN %s ELSE %s END + CASE WHEN "crew_sailor"."ship_id" = %s THEN %s ELSE %s END)) with params ('2020-01-01 00:00:00', 1, 1, '2020-01-01 00:00:00', 1, 0, 1, 1, 0)
```

Each is one `"SELECT"` with one where clause, in which the condition of the one queryset and the condition of the other stand in parentheses with the connector between them. The third is long because of the backend. Where a backend's feature `BaseDatabaseFeatures.supports_logical_xor` is false, as it is for SQLite, the where clause writes an exclusive or as an `"OR"` of the conditions together with a count of how many of them hold (`django/db/models/sql/where.py:WhereNode.as_sql`).

### An empty operand

Before anything is cloned, each of `QuerySet.__and__`, `QuerySet.__or__` and `QuerySet.__xor__` asks whether either side is an empty queryset, one whose query has been marked as returning nothing, as `QuerySet.none` marks it. The test is `isinstance` against `EmptyQuerySet`, which [Annotations, ordering and the other methods that change the query](methods.md) explains. Where one side is empty no query is merged, and an operand is returned. Where one side alone is empty, `&` returns it and the other two return the other side. In each case it is the operand itself, not a clone of it:

```text recording=querysets
(Sailor.objects.none() | old) is old, (old & Sailor.objects.none()).query.is_empty()  ->  (True, True)
```

The first question is put with `is`: what came back is old itself. And the short cut is taken before `Query.combine` is reached, so where one side is empty nothing that `combine` would refuse is refused.

### The clone, and the known related objects

Where neither side is empty, `QuerySet.__and__` returns what `QuerySet._chain` returns for the left side: a clone of it, unless the queryset is being changed in place ([Clones: how a queryset is built](chaining.md)). `QuerySet.__or__` and `QuerySet.__xor__` do the same unless the left side is sliced, which "A sliced operand", below, takes up. A clone of the left side has its class, and whatever a clone takes from its original, among them the alias of a database, the hints, the iterable class, the fetch mode, the prefetch lookups and `QuerySet._fields`. Of the right side, its query's share and its known related objects reach the result, and nothing else that it was given.

`QuerySet._known_related_objects` is the dictionary in which the queryset of a foreign key's reverse manager records, under that field, the object it was made for, so that each instance it makes is given that very object ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)). `QuerySet._merge_known_related_objects` copies the right side's entries into the result's dictionary, field by field (`django/db/models/query.py:QuerySet._merge_known_related_objects`). A clone has no dictionary of its own, though: `QuerySet._clone` hands on the one its original holds. So, where the clone is of the left operand, the entries are written into that operand's dictionary as well, and of every other queryset that shares it, and each of them, evaluated afterwards, has those objects too to give to the instances it makes. Here of_petrel and of_gannet are the crews of the two ships, from their related managers, and the question lists the keys that of_petrel knows:

```text recording=querysets
of_petrel = petrel.crew.all(); of_gannet = gannet.crew.all()
{field.name: sorted(known) for field, known in of_petrel._known_related_objects.items()}  ->  {'ship': [1]}
of_petrel | of_gannet
{field.name: sorted(known) for field, known in of_petrel._known_related_objects.items()}  ->  {'ship': [1, 2]}
```

### What the operators refuse

A pair of querysets can be turned away at three places, in this order.

- `QuerySet._check_operator_queryset` raises `TypeError` where the query of either side has a combinator, that is, where either is a combined queryset. Its message names the operator (`django/db/models/query.py:QuerySet._check_operator_queryset`).
- `QuerySet._merge_sanity_check` is about querysets that return something other than instances. Where the left side has `QuerySet._fields`, which `QuerySet.values` and `QuerySet.values_list` set, the two queries must select the same names: it compares `Query.values_select`, `Query.extra_select` and `Query.annotation_select` of the two, each as a set, and raises `TypeError` at a difference. Where the left side has none it compares nothing, whatever the right side is (`django/db/models/query.py:QuerySet._merge_sanity_check`).
- `Query.combine` begins with four tests, each a `TypeError`: the two queries are for different model classes; the query it is called on, which is the clone of the left side, is sliced; one of the two has `Query.distinct` set and the other has not; the two have different `Query.distinct_fields`. The models are compared as classes, so a model and a proxy of it are two models. Further on, and for the connector `"OR"` alone, it raises `ValueError` where both queries have columns that `QuerySet.extra` selected.

The second of these is one-sided, and the recording shows it from both sides, with a refusal by `combine` after it:

```text recording=querysets
Sailor.objects.values('name') | Sailor.objects.values('id')  ->  raises TypeError: Merging 'SailorQuerySet' classes must involve the same values in each case.
type(Sailor.objects.all() | Sailor.objects.values('id')).__name__, (Sailor.objects.all() | Sailor.objects.values('id'))._fields  ->  ('SailorQuerySet', None)
Sailor.objects.all() | Ship.objects.all()  ->  raises TypeError: Cannot combine queries on two different base models.
```

A queryset of instances on the left and one made by `values` on the right are merged without complaint: the result is a clone of the left side with no `_fields`, and since `combine` gives its query the columns the right side selects, it yields instances that have only that one column loaded.

What `combine` does once its tests are passed, with the joins of the two queries, the aliases of their tables, what they select and how they are ordered, is told in [From QuerySet to SQL](../sql.md). The operators between `Q` objects are another matter, and are in [`filter`, `exclude` and `Q` objects](filters.md).

## A sliced operand: `__or__` and `__xor__` rewrite it

`Query.can_filter` is a query's answer to whether a condition may still be added to it, and it is false exactly where the query is sliced (`django/db/models/sql/query.py:Query.can_filter`); why a sliced query takes no more conditions is told in [Evaluation and the result cache](evaluation.md). `QuerySet.__or__` and `QuerySet.__xor__` put the question to each side, and replace a side that answers no by a queryset that can be merged and selects the same rows: the model's base manager, filtered by `"pk__in"` of the sliced queryset's `values("pk")`. The sliced query becomes a subquery, limits and all, and what is merged is one condition on the primary key.

Here two is the first two sailors by key, a sliced queryset, and dag_only the sailors named Dag:

```text recording=querysets
two = Sailor.objects.order_by('id')[:2]; dag_only = Sailor.objects.filter(name='Dag')
first_two = two | dag_only
  QuerySet.__or__(a SailorQuerySet of Sailor, no result cache)
    QuerySet._check_operator_queryset(other=a SailorQuerySet of Sailor, no result cache, operator_='|')
    QuerySet._merge_sanity_check(a SailorQuerySet of Sailor, no result cache)
    Query.can_filter
    QuerySet._chain  ->  a new SailorQuerySet
    QuerySet._not_support_combined_queries('filter')
    QuerySet._chain  ->  a new QuerySet
    Query.clear_ordering
    QuerySet._chain  ->  a new QuerySet
    QuerySet._merge_known_related_objects(a SailorQuerySet of Sailor, no result cache)
    Query.can_filter
    Query.combine(rhs=a Query of Sailor, connector='OR')
list(first_two)  ->  [<Sailor: Ada>, <Sailor: Bram>, <Sailor: Dag>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE ("crew_sailor"."id" IN (SELECT "U0"."id" AS "pk" FROM "crew_sailor" "U0" ORDER BY "U0"."id" ASC LIMIT 2) OR "crew_sailor"."name" = %s) with params ('Dag',)
two & dag_only  ->  raises TypeError: Cannot combine queries once a slice has been taken.
list(dag_only & two)  ->  [<Sailor: Dag>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s ORDER BY "crew_sailor"."id" ASC with params ('Dag',)
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('ship')[:2] | dag_only), (Sailor.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('ship')[:2] | dag_only)._prefetch_related_lookups  ->  ((FETCH_ONE), ())
```

The first `Query.can_filter` is the question put to the left side. The four lines after it are the making of the replacement: the `QuerySet._chain` of `QuerySet.values`, which clones the sliced queryset, a SailorQuerySet; the test and the `_chain` of `QuerySet.filter`, called through the base manager, which clones the queryset that manager made, a plain `QuerySet`; and a `Query.clear_ordering`, by which the `"in"` lookup asks the inner query to drop its ordering (`django/db/models/lookups.py:In.get_prep_lookup`). That call is not forced, and unforced it leaves a sliced query alone: the subquery of the statement has kept its `ORDER BY` beside its `"LIMIT"`. The third `_chain` is the clone that becomes the result, and the second `can_filter` the question put to the right side, which could be filtered.

So where the left side was sliced, the result is a clone not of it but of a queryset that the base manager made ([Managers](../models/managers.md)): the third `_chain` returned a plain `QuerySet` where the first, the clone of the sliced queryset, returned a SailorQuerySet. Its fetch mode and its prefetch lookups are that queryset's too: in the recording's line about a fetch mode, written there as mode(...), a sliced left side had `FETCH_PEERS` and a prefetch lookup, and the result has `FETCH_ONE` and no lookups. So is its alias for a database. One that `QuerySet.using` set on the sliced queryset stays with the subquery and does not reach the result, and if the result is then compiled for another database the `"in"` lookup raises `ValueError` (`django/db/models/manager.py:BaseManager.get_queryset`, `django/db/models/lookups.py:In.process_rhs`).

`&` makes no such replacement. A sliced left side reaches `Query.combine` and is refused there, as the recording shows.

> **Trap.** A sliced right side under `&` is tested by nothing: `combine` looks at the limits of the query it is called on and not at those of the query it is given, and takes none of them over, though it does take the other query's ordering (`django/db/models/sql/query.py:Query.combine`). So the slice is dropped without a word, and the answer can change. The recording puts the sailors named Dag to `&` with the first two sailors, among whom Dag is not: the statement has the `ORDER BY` of two and no `"LIMIT"`, and Dag comes back.

## `union`, `intersection` and `difference`: the queries side by side

`QuerySet.union`, `QuerySet.intersection` and `QuerySet.difference` each take any number of other querysets and, short cuts aside, hand them to one method, `QuerySet._combinator_query`, with the name of the set operation: `"union"`, `"intersection"` or `"difference"` (`django/db/models/query.py:QuerySet._combinator_query`). That method merges nothing. It works on what `QuerySet._chain` returns for the left side, a clone in the recording, and sets three things on its query. `Query.combinator` is the name of the operation. `Query.combinator_all` says whether duplicate rows are to be kept, which `union` alone can ask for, with `all=True`. And `Query.combined_queries` is a tuple of the queries to be joined, the left side's first.

```text recording=querysets
named_dag = Sailor.objects.filter(name='Dag')
names = old.union(on_petrel, named_dag)
  QuerySet.union(a SailorQuerySet of Sailor, no result cache, a SailorQuerySet of Sailor, no result cache)
    QuerySet._combinator_query(combinator='union', a SailorQuerySet of Sailor, no result cache, a SailorQuerySet of Sailor, no result cache)
      QuerySet._chain  ->  a new SailorQuerySet
      Query.clear_ordering(force=True)
      QuerySet._clear_ordering_in_combined_queries(cloned_query=a Query of Sailor, other_qs=(a SailorQuerySet of Sailor, no result cache, a SailorQuerySet of Sailor, no result cache))
        Query.clear_ordering(clear_default=False)
        Query.clear_ordering(clear_default=False)
      Query.clear_limits
      -> a SailorQuerySet of Sailor, no result cache
    -> a SailorQuerySet of Sailor, no result cache
names.query.combinator, names.query.combinator_all, len(names.query.combined_queries), bool(names.query.where)  ->  ('union', False, 3, True)
names.query.combined_queries[0] is old.query, names.query.combined_queries[1] is on_petrel.query  ->  (True, False)
```

The left side is cloned for the reason a comment gives: so that the result inherits what the left side selects, and everything else. The clone's conditions come with it, as the question about its where clause shows: it is not empty. They are not what is compiled. For a query with a combinator the compiler writes each part and joins them, and takes from the combined query itself what applies to the whole, such as an ordering and a limit (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`).

The parts are not all made alike, as the question with `is` shows. The first part is the left queryset's own query: the same object, not a copy. Each of the others is a clone of its queryset's query, made by `QuerySet._clear_ordering_in_combined_queries` (`django/db/models/query.py:QuerySet._clear_ordering_in_combined_queries`).

### Orderings and limits, cleared in some places and kept in others

`_combinator_query` deals with an ordering or a limit that one of the querysets brought with it as it assembles the parts, and a comment says to what end: so that an ordering and limits can be applied again, to the combined queryset. Three queries are treated in three ways.

| the query | an ordering it was given | the model's default ordering | its limits |
|---|---|---|---|
| the combined queryset's own, the clone's | cleared, by force | switched on | cleared |
| the first part, the left queryset's own query | kept | as it was | kept |
| each other part, a clone | cleared, unless the part is sliced, has distinct fields or locks its rows | as it was | kept |

*What `_combinator_query` does to the orderings and limits of the queries it puts together.*

The clearing is done by `Query.clear_ordering`, which unless it is forced does nothing to a query that is sliced, has distinct fields or has `Query.select_for_update` set, and which leaves `Query.default_ordering` alone where it is called with `clear_default=False`, as it is for the other parts (`django/db/models/sql/query.py:Query.clear_ordering`).

An ordering or a slice given to the combined queryset afterwards is written once, after the last part:

```text recording=querysets
list(names.order_by('-name')[:2])  ->  [<Sailor: Dag>, <Sailor: Cora>]
  SQL SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s ORDER BY "col2" DESC LIMIT 2 with params ('2020-01-01 00:00:00', 1, 'Dag')
```

`intersection` and `difference` differ from `union` in the name they pass, and in having no argument for keeping duplicates:

```text recording=querysets
list(old.intersection(on_petrel))  ->  [<Sailor: Ada>]
  SQL SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s INTERSECT SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s with params ('2020-01-01 00:00:00', 1)
list(on_petrel.difference(old))  ->  [<Sailor: Bram>]
  SQL SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s EXCEPT SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s with params (1, '2020-01-01 00:00:00')
list(old.union(on_petrel, all=True).values_list('name', flat=True).order_by('name'))  ->  ['Ada', 'Ada', 'Bram', 'Cora']
  SQL SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION ALL SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY 1 ASC with params ('2020-01-01 00:00:00', 1)
```

In the statement of the union with `all=True` each part selects the one column, though `QuerySet.values_list` was called on the combined queryset and not on its parts: the compiler hands what the whole selects down to each part that has no selection of its own (`django/db/models/sql/compiler.py:SQLCompiler._get_combinator_part_sql`).

### Empty querysets, and `union` with nothing

Each of `QuerySet.union`, `QuerySet.intersection` and `QuerySet.difference` looks for an empty queryset before it calls `_combinator_query` (`django/db/models/query.py:QuerySet.union`, `django/db/models/query.py:QuerySet.intersection`). An empty queryset adds nothing to a union: where the left side is empty, `union` combines only those of the others that are not, returning the one itself where one is all there is and the left side where there is none, and an empty queryset among the others of a left side that is not empty stays as a part. It empties an intersection: `intersection` returns the first empty queryset it finds, the left side before the others. And it leaves a difference empty where it is on the left: `difference` returns an empty left side, and an empty queryset among the others stays as a part. With no other queryset at all, `union` returns the left side, and the other two make a combined queryset of one part unless the left side is empty. As with the operators, a short cut that returns one of the querysets it was given returns that queryset itself and not a clone.

```text recording=querysets
old.union() is old, old.union(Sailor.objects.none()).query.combinator  ->  (True, 'union')
Sailor.objects.none().union(old) is old, Sailor.objects.none().intersection(old).query.is_empty(), old.intersection(Sailor.objects.none()).query.is_empty()  ->  (True, True, True)
```

An empty queryset that stays as a part is the compiler's to deal with: it leaves the empty parts out of a union that is not sliced, and an empty part out of a difference unless it is the first part (`django/db/models/sql/compiler.py:SQLCompiler.get_combinator_sql`).

## What the compiler asks of the backend

`QuerySet.union` builds a combined queryset on any backend, and nothing about the database is asked until the statement is written. Then the compiler asks, and two of its questions can end in a refusal. One is whether the backend has the operation at all, which every backend Django ships has (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_select_union`). The other has consequences. Whether a part of a compound statement may have an `ORDER BY` or a `"LIMIT"` of its own depends on the database, and a backend says so in `BaseDatabaseFeatures.supports_slicing_ordering_in_compound`. The base class has it false. The backends for PostgreSQL, MySQL and Oracle set it true, and SQLite's leaves it as it is (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_slicing_ordering_in_compound`).

Where the feature is false, `SQLCompiler.get_combinator_sql` looks at every part before it writes any. For a part whose query is sliced it raises `DatabaseError`, and likewise for a part for which that part's compiler finds an ordering (`django/db/models/sql/compiler.py:SQLCompiler.get_combinator_sql`). Finding an ordering means that `SQLCompiler.get_order_by` returns anything, and the ordering it reads falls back on the `ordering` of the model's `Meta` wherever the query has `Query.default_ordering` on and no ordering of its own (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`). On such a backend, then, a part is refused for its model's default ordering as much as for one that `QuerySet.order_by` gave it.

Here is what SQLite did with old and on_petrel, two querysets of a model with no default ordering:

```text recording=querysets
list(old.order_by('name').union(on_petrel))  ->  raises DatabaseError: ORDER BY not allowed in subqueries of compound statements.
list(old.union(on_petrel.order_by('name')))  ->  [<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>]
  SQL SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s with params ('2020-01-01 00:00:00', 1)
list(old[:1].union(on_petrel))  ->  raises DatabaseError: LIMIT/OFFSET not allowed in subqueries of compound statements.
```

An ordering on the left side is still in the first part, and is refused. An ordering on the right side was cleared as its part was made, and the statement is sent. A slice of the left side is still in the first part too.

Ship is another case. It has `ordering = ["name"]` in its `Meta`, by way of an abstract base class, so each of its querysets has a default ordering, and no part loses that in `QuerySet._combinator_query`. Here heavy and light are the ships over and under a thousand tons:

```text recording=querysets
heavy = Ship.objects.filter(tonnage__gt=1000); light = Ship.objects.filter(tonnage__lt=1000)
Ship._meta.ordering, Sailor._meta.ordering  ->  (['name'], [])
list(heavy.union(light))  ->  raises DatabaseError: ORDER BY not allowed in subqueries of compound statements.
list(heavy.union(light).order_by())  ->  raises DatabaseError: ORDER BY not allowed in subqueries of compound statements.
list(heavy.order_by().union(light))  ->  raises DatabaseError: ORDER BY not allowed in subqueries of compound statements.
list(heavy.order_by().union(light.order_by()))  ->  [<Ship: Gannet>, <Ship: Petrel>]
  SQL SELECT "fleet_ship"."id" AS "col1", "fleet_ship"."name" AS "col2", "fleet_ship"."tonnage" AS "col3", "fleet_ship"."home_id" AS "col4", "fleet_ship"."captain_id" AS "col5" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s UNION SELECT "fleet_ship"."id" AS "col1", "fleet_ship"."name" AS "col2", "fleet_ship"."tonnage" AS "col3", "fleet_ship"."home_id" AS "col4", "fleet_ship"."captain_id" AS "col5" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" < %s ORDER BY "col2" ASC with params (1000, 1000)
heavy.union(light).query.default_ordering, heavy.union(light).query.combined_queries[0].default_ordering, heavy.union(light).query.combined_queries[1].default_ordering  ->  (True, True, True)
connection.features.supports_slicing_ordering_in_compound  ->  False
```

The plain union fails on the default ordering of its parts, which the question about `default_ordering` shows switched on in all three queries. Calling `order_by()` on the combined queryset does not help. `QuerySet.order_by` clears with `clear_default=False`, and `Query.clear_ordering`, which goes on to clear each part of a combined query, hands that on to them; what switches the default off is `Query.add_ordering` called with no names, on the combined queryset's query alone (`django/db/models/sql/query.py:Query.add_ordering`). Clearing the left side before combining leaves the right part with its default. Of the four ways the recording tries, only the one that calls `order_by()` on each queryset before combining is compiled. Its statement ends in an `ORDER BY` all the same, on the column of the name: the combined queryset's own default ordering, which `_combinator_query` switched on.

`QuerySet.count` and `QuerySet.exists` of the plain union, which could not be listed, are answered all the same. Each clears the ordering of the parts with the default included, `count` in `Query.get_aggregation` and `exists` in `Query.exists` (`django/db/models/sql/query.py:Query.get_aggregation`, `django/db/models/sql/query.py:Query.exists`):

```text recording=querysets
heavy.union(light).count(), heavy.union(light).exists()  ->  (2, True)
  SQL SELECT COUNT(*) FROM (SELECT "fleet_ship"."id" AS "col1", "fleet_ship"."name" AS "col2", "fleet_ship"."tonnage" AS "col3", "fleet_ship"."home_id" AS "col4", "fleet_ship"."captain_id" AS "col5" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s UNION SELECT "fleet_ship"."id" AS "col1", "fleet_ship"."name" AS "col2", "fleet_ship"."tonnage" AS "col3", "fleet_ship"."home_id" AS "col4", "fleet_ship"."captain_id" AS "col5" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" < %s) subquery with params (1000, 1000)
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s UNION SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" < %s LIMIT 1 with params (1, 1000, 1, 1000)
```

The count wraps the compound statement in a subquery and counts its rows, and `exists` asks for a constant from each part and stops at one row.

> **Changed in 6.1.** The model's default ordering is applied to a combined queryset. The release notes give the consequence they expect a project to meet: `union`, `QuerySet.intersection` and `QuerySet.difference` raise `DatabaseError` when a field of the model's `ordering` is not among those selected by `QuerySet.values` or `QuerySet.values_list`, and calling `order_by` with no arguments after combining clears the default ordering (`docs/releases/6.1.txt`).

The error of that note is not SQLite's refusal of a part. `SQLCompiler.get_order_by` raises it for the ordering of the whole statement, which is the ordering that call clears, where what is ordered by is not among the columns selected and a part has a selection that `values` or `values_list` fixed (`django/db/models/sql/compiler.py:SQLCompiler.get_order_by`).

## What a combined queryset refuses, and what it allows

A condition given to a combined queryset would go into the where clause of its own query, and the compiler does not write that clause for a compound statement: it writes the parts (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). Many of a queryset's methods are closed to a combined queryset. Each of these begins by calling `QuerySet._not_support_combined_queries` with its own name, and that method raises `NotSupportedError` where the query has a combinator (`django/db/models/query.py:QuerySet._not_support_combined_queries`):

- `QuerySet.filter` and `QuerySet.exclude`;
- `QuerySet.annotate` and `QuerySet.alias`;
- `QuerySet.select_related` and `QuerySet.prefetch_related`;
- `QuerySet.distinct` and `QuerySet.extra`;
- `QuerySet.defer` and `QuerySet.only`;
- `QuerySet.contains`, `QuerySet.update` and `QuerySet.delete`.

`QuerySet.get` makes the test itself, and only when it is given a condition (`django/db/models/query.py:QuerySet.get`) ([`get`, `first`, `count` and the other methods that run a query at once](results.md)). The operators refuse through `QuerySet._check_operator_queryset`. And a method that is built on one of the methods listed inherits the refusal: `QuerySet.in_bulk` with a list of values calls `filter`, and `QuerySet.dates` and `QuerySet.datetimes` call `annotate`.

```text recording=querysets
old.union(on_petrel).filter(name='Ada')  ->  raises NotSupportedError: Calling QuerySet.filter() after union() is not supported.
old.union(on_petrel).annotate(n=Count('id'))  ->  raises NotSupportedError: Calling QuerySet.annotate() after union() is not supported.
old.union(on_petrel).get(name='Ada')  ->  raises NotSupportedError: Calling QuerySet.get(...) with filters after union() is not supported.
...
old.union(on_petrel) | old  ->  raises TypeError: Cannot use | operator with combined queryset.
old.union(on_petrel).delete()  ->  raises NotSupportedError: Calling QuerySet.delete() after union() is not supported.
old.union(on_petrel).update(name='x')  ->  raises NotSupportedError: Calling QuerySet.update() after union() is not supported.
```

Other methods make no such test. What each of those the recording tries does, `QuerySet.complex_filter` apart, it does to the compound statement as a whole. `QuerySet.order_by` and a slice were shown above, and `QuerySet.values_list`, which like `QuerySet.values` sets what the combined query selects; either is refused all the same when it is given an expression, since it then calls `annotate`. So were `QuerySet.count` and `QuerySet.exists`. `complex_filter` is the exception:

```text recording=querysets
list(old.union(on_petrel).complex_filter({'name': 'Ada'}))  ->  [<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>]
  SQL SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s with params ('2020-01-01 00:00:00', 1)
```

> **Trap.** The test is made by the methods listed, not by the query. `complex_filter`, the method behind `"limit_choices_to"` ([`filter`, `exclude` and `Q` objects](filters.md)), reaches the query without going through any of them, so a combined queryset does not refuse it: its condition on the name was not written, and all three sailors came back (`django/db/models/query.py:QuerySet.complex_filter`).
