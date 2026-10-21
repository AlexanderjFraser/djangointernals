---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Aggregating a query: `Query.get_aggregation`

`Query.get_aggregation` runs a set of aggregates over a query for `QuerySet.aggregate` and `QuerySet.count`, in the query's own statement where that gives the right answer and otherwise in a statement wrapped around it; `Query.exists` makes the narrowed query that `QuerySet.exists` sends.

The recordings below were made from a running Django, on SQLite, over harbour's models, which [Models and fields](../models.md) lists. A line at the left is Python as it was run, with its value after `->` where it is shown, or the title of the block under it; calls a line of Python set going are set in under it, nested as they were made, `->` there being what a call returned, and a parenthesis after a call names the class that declares the method and, after the word of, the object it was called on. A line that begins `SQL` is a statement as Django handed it to its cursor, and a line of three dots stands for lines of the block left out.

## `Query.get_aggregation`

`Query.get_aggregation` takes the database alias and a dictionary from aliases to aggregates, and returns a dictionary from the same aliases to values, having sent one statement or none (`django/db/models/sql/query.py:Query.get_aggregation`). It is the whole of `QuerySet.aggregate` after the arguments are checked, called on a copy of the query from `Query.chain`, and of `QuerySet.count` where the queryset has no result cache to measure ([`get`, `first`, `count` and the other methods that run a query at once](../querysets/results.md)).

**The aggregates are resolved against each other.** Each is resolved against the query with `summarize=True`, and a later expression of the call may use an earlier one's alias in arithmetic, though not aggregate over it ([Aggregates: `Aggregate` and `Count`](../expressions/aggregates.md)). For that, after each aggregate is resolved it is put among the query's annotations under its alias and added to the selected set, which a comment says is so that the remaining ones may resolve against it, and the `Ref` such a name resolves to is replaced by the earlier aggregate itself. Each alias is checked by `Query.check_alias` first, and a resolved copy whose `contains_aggregate` is not set is refused with `TypeError`: a plain expression is not an aggregate. Once all are resolved they are taken out of the annotations and the mask of selected annotations is put back as it was, and the method has noted whether any aggregate refers to an annotation that holds a subquery or a window.

**Then it chooses between two shapes.** It asks the where tree for its having part and its qualify part, the parts [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md) defines, and takes the query to have an existing aggregation where any annotation contains an aggregate or the having part is not empty. The **plain case** is the query itself with its select list replaced: the aggregates become its only selected annotations, and one statement over the query's rows answers. The **wrapped case** makes a clone of the query the inner query of an `AggregateQuery`, whose compiler selects the aggregates from the clone's statement in parentheses (`django/db/models/sql/subqueries.py:AggregateQuery`). The wrapped case is taken when any of these holds:

- the query's `group_by` is a tuple;
- it is sliced;
- it has an existing aggregation;
- an aggregate refers to an annotation with a subquery, or with a window;
- the where tree has a qualify part;
- the query is distinct, or combined;
- a selected annotation is marked `set_returning`, as an expression that may return more than one row is.

A comment gives the reasons for four of them: an existing aggregation would make the statement group, and `get_aggregation` must produce one result; a limit, a distinct or a set operation has to be done first, so that the aggregate is taken over the rows it leaves and not applied before it.

In the plain case the query's select, `selected`, `default_cols` and `extra` are cleared, the aggregates become its annotations, with a `Ref` to any annotation the query had already replaced by that annotation's expression, and the mask is set to their aliases.

```text recording=sql
Ship.objects.aggregate(total=Sum('tonnage'), ships=Count('id'))
  QuerySet.aggregate(total=Sum(F(tonnage)), ships=Count(F(id)))
    Query.get_aggregation(using='default', aggregate_exprs={'total': Sum(F(tonnage)), 'ships': Count(F(id))})
      Sum.resolve_expression(summarize=True)  (Aggregate.resolve_expression, of Sum(F(tonnage)))  ->  Sum(Col(fleet_ship, fleet.Ship.tonnage))
      Count.resolve_expression(summarize=True)  (Aggregate.resolve_expression, of Count(F(id)))  ->  Count(Col(fleet_ship, fleet.Ship.id))
      Query.clear_ordering(force=True)
      Query.clear_limits
      SQLCompiler.execute_sql(result_type='single')
        SQLCompiler.as_sql  ->  ('SELECT SUM("fleet_ship"."tonnage") AS "total", COUNT("fleet_ship"."id") AS "ships" FROM "fleet_ship"', ())
        SQL SELECT SUM("fleet_ship"."tonnage") AS "total", COUNT("fleet_ship"."id") AS "ships" FROM "fleet_ship"
        -> (1680, 2)
      SQLCompiler.get_converters  ->  {0: [BaseExpression.convert_value's lambda], 1: [BaseExpression.convert_value's lambda]}
      SQLCompiler.apply_converters
      -> {'total': 1680, 'ships': 2}
```

In the wrapped case the inner query is made to select, under aliases, what the outer aggregates refer to and nothing else, and each step serves that. It is marked a subquery, with `select_for_update` and `select_related` off. Its ordering is cleared where `Query.orderby_issubset_groupby` allows, without force, so that a sliced query keeps the ordering its slice depends on ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)). Unless it is distinct, its default columns are turned off, and where it had them and an existing aggregation its `group_by` is set to the model's primary key, since a comment says an inner query with the default columns and an aggregate annotation must be grouped by the main model's primary key; and, where it is not distinct either, an annotation that neither the grouping nor the aggregates refer to, and that puts no column into the grouping, is left unselected, unless a window is filtered on or the query is combined, which a comment says would need complex realiasing. Every column the aggregates refer to directly, which `Query._gen_cols` yields with the `Ref` objects left aside, is added to the inner query as an annotation named `"__col1"`, `"__col2"` and so on, and the aggregate in the outer query is made to refer to that name; an aggregate that refers to an annotation by a `Ref` keeps the `Ref`, the annotation being selected under its own alias. Where that leaves the inner query selecting nothing, the primary key is selected, for the sake of a count over a slice (`django/db/models/sql/query.py:Query._gen_cols`).

```text recording=sql
Ship.objects.order_by('name')[:1].aggregate(total=Sum('tonnage'))
  Query.clear_ordering(force=True, clear_default=False)
  QuerySet.aggregate(total=Sum(F(tonnage)))
    Query.get_aggregation(using='default', aggregate_exprs={'total': Sum(F(tonnage))})
      Sum.resolve_expression(summarize=True)  (Aggregate.resolve_expression, of Sum(F(tonnage)))  ->  Sum(Col(fleet_ship, fleet.Ship.tonnage))
      AggregateQuery.__init__(model=Ship, inner_query=a Query of Ship)
      Query.clear_ordering
      Query.add_annotation(annotation=Col(fleet_ship, fleet.Ship.tonnage), alias='__col1')
      Query.clear_ordering(force=True)
      Query.clear_limits
      SQLCompiler.execute_sql(result_type='single')
        SQLAggregateCompiler.as_sql
          SQLCompiler.as_sql(with_col_aliases=True)  ->  ('SELECT "fleet_ship"."tonnage" AS "__col1" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC LIMIT 1', ())
          -> ('SELECT SUM("__col1") FROM (SELECT "fleet_ship"."tonnage" AS "__col1" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC LIMIT 1) subquery', ())
        SQL SELECT SUM("__col1") FROM (SELECT "fleet_ship"."tonnage" AS "__col1" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC LIMIT 1) subquery
        -> (1200,)
```

The first `clear_ordering` under `get_aggregation`, without force, is the inner query's, and leaves the ordering since the query is sliced; the second, with force, is the outer's. The inner statement keeps its `"ORDER BY"` and `"LIMIT"`, and selects the one column the sum needs under the name the outer statement sums. `SQLAggregateCompiler.as_sql` is the whole of the outer compiler: it compiles each selected annotation of the `AggregateQuery`, has the inner query's compiler write its statement with `with_col_aliases=True`, so that every column has a name the outer statement can use, and writes `"SELECT"`, the aggregates, `"FROM ("`, the inner statement and `") subquery"`; the aggregates are given no aliases, the result being read by position (`django/db/models/sql/compiler.py:SQLAggregateCompiler.as_sql`).

```text recording=sql
Ship.objects.annotate(hands=Count('crew')).aggregate(most=Max('hands'))
  Query.add_annotation(annotation=Count(F(crew)), alias='hands')
    Count.resolve_expression(summarize=False)  (Aggregate.resolve_expression, of Count(F(crew)))  ->  Count(Col(crew_sailor, crew.Sailor.id))
  QuerySet.aggregate(most=Max(F(hands)))
    Query.get_aggregation(using='default', aggregate_exprs={'most': Max(F(hands))})
      Max.resolve_expression(summarize=True)  (Aggregate.resolve_expression, of Max(F(hands)))  ->  Max(Ref(hands, Count(Col(crew_sailor, crew.Sailor.id))))
      AggregateQuery.__init__(model=Ship, inner_query=a Query of Ship)
      Query.clear_ordering
      Query.clear_ordering(force=True)
      Query.clear_limits
      SQLCompiler.execute_sql(result_type='single')
        SQLAggregateCompiler.as_sql
          SQLCompiler.as_sql(with_col_aliases=True)  ->  ('SELECT COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id"', ())
          -> ('SELECT MAX("hands") FROM (SELECT COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id") subquery', ())
        SQL SELECT MAX("hands") FROM (SELECT COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id") subquery
        -> (2,)
```

Here the inner query had default columns and an aggregate among its annotations, so it is grouped by the ship's primary key and selects the count alone, and the outer `Max` refers to it as `"hands"`, the `Ref` the summary resolved to.

```text figure=two-shapes
the plain case                                          the wrapped case

Ship.objects.aggregate(total=Sum('tonnage'),            Ship.objects.annotate(hands=Count('crew'))
                       ships=Count('id'))                          .aggregate(most=Max('hands'))

the query itself, its select list replaced:             an AggregateQuery around a clone of the query:

SELECT SUM("fleet_ship"."tonnage") AS "total",          SELECT MAX("hands")
       COUNT("fleet_ship"."id") AS "ships"              FROM (
FROM "fleet_ship"                                           SELECT COUNT("crew_sailor"."id") AS "hands"
                                                            FROM "fleet_ship"
written by SQLCompiler                                      LEFT OUTER JOIN "crew_sailor" ON (...)
                                                            GROUP BY "fleet_ship"."id"
                                                        ) subquery

                                                        the inner statement by SQLCompiler, with_col_aliases=True;
                                                        the outer by SQLAggregateCompiler
```

*The two shapes of `get_aggregation`, as the two recorded calls above wrote them. On the left the aggregates stand in the query's own select list; on the right the query keeps its grouping inside the parentheses and the aggregates are taken from what it selects.*

**Either way, one row is fetched, or none.** Where every selected aggregate has an answer for no rows, its `empty_result_set_value`, a query the compiler can tell matches nothing is not sent at all, and those answers are the result. The outer query's ordering is cleared with force, its limits are cleared, and `select_for_update` and `select_related` are turned off. The method gathers each selected aggregate's `empty_result_set_value` and sets the compiler's `elide_empty` to whether none of them is `NotImplemented`, the option [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md) tells: with it set, a where tree that can match nothing makes `SQLCompiler.as_sql` raise `EmptyResultSet` and `SQLCompiler.execute_sql` answer with nothing, and the gathered values are the answer; without it, `as_sql` writes `"0 = 1"` for the where clause and the statement is sent, so that an expression with no answer of its own, a sum with one added to it, gets the database's (`django/db/models/sql/compiler.py:SQLCompiler.__init__`, `django/db/models/sql/compiler.py:SQLCompiler.execute_sql`). `Count` answers 0, `Aggregate` answers `None`, a `Coalesce` answers with the first of its sources whose answer is not `None`, and has no answer where that source has none, and a `Value` answers with its value, which is how a default reaches the dictionary without a statement (`django/db/models/functions/comparison.py:Coalesce.empty_result_set_value`).

```text recording=sql
Aggregating over a query that matches nothing: each aggregate's empty_result_set_value is the answer, unless one has none, and then the statement is sent with a false predicate
    Ship.objects.filter(pk__in=[]).aggregate(n=Count('id'), s=Sum('tonnage'), m=Max('tonnage'), c=Coalesce(Sum('tonnage'), 0), d=Sum('tonnage', default=5))  ->  {'n': 0, 's': None, 'm': None, 'c': 0, 'd': 5}
    Ship.objects.filter(pk__in=[]).aggregate(s=Sum('tonnage') + 1)  ->  {'s': None}
      SQL SELECT (SUM("fleet_ship"."tonnage") + %s) AS "s" FROM "fleet_ship" WHERE 0 = 1 with params (1,)
    Ship.objects.filter(pk__in=[]).count()  ->  0
    Count.empty_result_set_value, Sum.empty_result_set_value, Coalesce(Sum('tonnage'), 0).empty_result_set_value, (Sum('tonnage') + 1).empty_result_set_value  ->  (0, None, 0, NotImplemented)
```

The row that comes back from `execute_sql` with `SINGLE` is cut to the compiler's column count and passed through the converters of each aggregate's output field, as a row of the queryset would be ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)), and the dictionary is made of the aliases in the order of `annotation_select` and the row's values.

## `get_count`, `exists` and `has_results`

`Query.get_count` clones the query and returns `get_aggregation` of `Count("*")` under the alias `"__count"`; everything above holds for it, the wrapped case included (`django/db/models/sql/query.py:Query.get_count`).

```text recording=sql
Ship.objects.annotate(hands=Count('crew')).count()
  Query.add_annotation(annotation=Count(F(crew)), alias='hands')
    Count.resolve_expression(summarize=False)  (Aggregate.resolve_expression, of Count(F(crew)))  ->  Count(Col(crew_sailor, crew.Sailor.id))
  QuerySet.count
    Query.get_count('default')
      Query.get_aggregation(using='default', aggregate_exprs={'__count': Count('*')})
        Count.resolve_expression(summarize=True)  (Aggregate.resolve_expression, of Count('*'))  ->  Count('*')
        AggregateQuery.__init__(model=Ship, inner_query=a Query of Ship)
        Query.clear_ordering
        Query.clear_ordering(force=True)
        Query.clear_limits
        SQLCompiler.execute_sql(result_type='single')
          SQLAggregateCompiler.as_sql
            SQLCompiler.as_sql(with_col_aliases=True)  ->  ('SELECT "fleet_ship"."id" AS "col1" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1', ())
            -> ('SELECT COUNT(*) FROM (SELECT "fleet_ship"."id" AS "col1" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1) subquery', ())
          SQL SELECT COUNT(*) FROM (SELECT "fleet_ship"."id" AS "col1" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1) subquery
          -> (2,)
```

The grouped query went inside, and since no column of it is wanted by the count, the inner statement selects the primary key alone, under the alias `"col1"` that `with_col_aliases=True` gives it, and groups by that position.

`Query.exists` makes the narrowed query that answers whether any row matches (`django/db/models/sql/query.py:Query.exists`). On a clone it clears the select clause with `Query.clear_select_clause`, which empties `select`, turns `default_cols` and `select_related` off, and masks every extra and every annotation; but where `group_by` is `True` it first adds every concrete field of the model to the select and calls `Query.set_group_by` with `allow_aliases=False`, so that the grouping is fixed as a tuple of columns before the select list it stood for is cleared, which a comment says is to avoid orphaning a reference to that list; a query that is both distinct and sliced keeps its select list. Where the query is a union, each part is replaced by that part's own `exists`, without the limit. Then the ordering is cleared with force, a limit of one row is set unless the caller asked for none, and the constant 1 is added as an annotation under the alias `"a"`, the one thing selected. `Query.has_results` makes that query and asks its compiler's `SQLCompiler.has_results`, which is whether `execute_sql` with `SINGLE` returned a row (`django/db/models/sql/query.py:Query.has_results`, `django/db/models/sql/compiler.py:SQLCompiler.has_results`).

```text recording=sql
    Query.has_results('default')
      Query.exists
        Query.clear_ordering(force=True)
        Query.add_annotation(annotation=Value(1), alias='a')
        -> a Query of Ship
      SQLCompiler.has_results
        SQLCompiler.execute_sql(result_type='single')
          SQLCompiler.as_sql  ->  ('SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s LIMIT 1', (1, 1000))
          SQL SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s LIMIT 1 with params (1, 1000)
          -> (1,)
        -> True
...
e = Ship.objects.filter(tonnage__gt=1000).query.exists()
e.select, e.default_cols, e.annotation_select, e.high_mark, e.order_by, e.default_ordering, str(e)  ->  ((), False, {'a': Value(1)}, 1, (), False, 'SELECT 1 AS "a" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > 1000 LIMIT 1')
```

The last two lines are the narrowed query itself, and what it holds and its statement: no columns of the model, the annotation alone, a high mark of one, no ordering, and `default_ordering` off so that the model's default ordering does not come back. A query that groups and filters on its count keeps both clauses in the narrowed statement, which [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md) shows.

`exists` serves one caller besides `QuerySet.exists`: `Exists`, the expression, wraps the query that `exists` makes, so that it stands inside another statement ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](../query/subqueries.md)). On a union, each part is narrowed the same way ([Compound statements: `get_combinator_sql`](compound.md)). `get_aggregation` over a window, where the aggregate refers to an annotation that holds one or the where tree filters on one, is always the wrapped case, and [The QUALIFY rewrite: a filter on a window](qualify.md#a-window-in-an-aggregation-and-from-an-outer-query) has the inner statement.
