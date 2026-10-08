---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Aggregates: `Aggregate`, `Count` and `get_aggregation`

`Aggregate` is the `Func` that folds the rows of a group into one value, `"COUNT"`, `"SUM"`, `"STRING_AGG"`, and is marked as one, so that the query groups for it and a filter on it goes to `"HAVING"`. `Query.get_aggregation` runs a set of aggregates over a query for `QuerySet.aggregate` and `QuerySet.count`, in the query's own statement where that gives the right answer and otherwise in a statement wrapped around it; `Query.exists` makes the narrowed query that `QuerySet.exists` sends.

An aggregate has three jobs that a plain function has not. It has to say that it is one, since the shape of the statement turns on it: the compiler groups by the selected columns that are not aggregated, and a condition that compares an aggregate cannot stand in `"WHERE"`, where the database tests one row at a time, and is moved to `"HAVING"` ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md)). Each of those decisions is read off one mark, `contains_aggregate`, which an aggregate sets on its class and most other expressions compute from their parts; a `Window` sets it `False` on its class, a comment saying that the grouping an aggregate would bring in is not wanted for one. It has to refuse to stand inside another aggregate. And it has to answer for no rows: the database answers a sum of nothing with a null, and where the compiler can tell that the query matches nothing, and every aggregate has an answer for no rows, it sends no statement at all. Beside these it carries what SQL lets an aggregate carry: `"DISTINCT"` on its argument, a `"FILTER"` clause, an `"ORDER BY"` inside the parentheses for a function whose result depends on the order of the rows, and a default for the null.

## `Aggregate`: a `Func` with a mark and four options

`Aggregate` is a subclass of `Func`, and what a function class declares, `function`, `template`, `arity`, it declares too ([Transforms and database functions: `Transform` and `Func`](functions.md)). Its template has three slots that `Func`'s has not, `"%(function)s(%(distinct)s%(expressions)s%(order_by)s)%(filter)s"`, one for each option that is written as SQL. On the class, `Aggregate.contains_aggregate` is `True`, where `BaseExpression` computes it from the sources; `window_compatible` is `True`, so that an aggregate may be the function a `Window` runs over its partition ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)); `empty_result_set_value`, the answer for no rows, is `None`; `allow_distinct` and `allow_order_by` are `False`, and each subclass turns on what its function accepts; and `name` is what the class is called in a message and in a default alias (`django/db/models/aggregates.py:Aggregate`).

`Aggregate.__init__` takes the function's arguments by position and the four options by keyword, and refuses three of them with `TypeError` according to the class: `distinct` unless `allow_distinct` is set, `order_by` unless `allow_order_by` is, and `default` where the class has an `empty_result_set_value` that is not `None`, which `Count` has. It keeps `distinct` as given, wraps the filter in an `AggregateFilter`, keeps the default as given until the aggregate is resolved, and turns the ordering into an `AggregateOrderBy` through `OrderByList.from_param`, which takes a string, an expression, or a list or tuple of either and raises `ValueError` for anything else; the arguments go to `Func.__init__` (`django/db/models/aggregates.py:Aggregate.__init__`, `django/db/models/expressions.py:OrderByList.from_param`).

What follows was recorded from a running Django, on SQLite, over the models of [From QuerySet to SQL](../sql.md): a line is a question and its answer after `->`, with a statement it sent under it as `SQL`, or a call with the calls it set going nested under it and `->` what each returned.

```text recording=sql
Aggregate.template, Count.function, Count.allow_distinct, Max.allow_distinct, StringAgg.allow_order_by, Count.empty_result_set_value, Sum.empty_result_set_value, Aggregate.contains_aggregate, Aggregate.window_compatible  ->  ('%(function)s(%(distinct)s%(expressions)s%(order_by)s)%(filter)s', 'COUNT', True, False, True, 0, None, True, True)
Max('tonnage', distinct=True)  ->  raises TypeError: Max does not allow distinct.
Count('crew', order_by='name')  ->  raises TypeError: Count does not allow order_by.
Count('crew', default=0)  ->  raises TypeError: Count does not allow default.
```

The filter and the ordering are sources of the expression. `Aggregate.get_source_expressions` returns the arguments with the filter and the ordering appended, `None` where there is none, and `Aggregate.set_source_expressions` takes the last two off again. `Aggregate.get_source_fields`, from which the output field is inferred, leaves them out, since a comment says they have nothing to do with it (`django/db/models/aggregates.py:Aggregate.get_source_expressions`, `django/db/models/aggregates.py:Aggregate.get_source_fields`).

`Aggregate.default_alias` is the name an aggregate goes under when `QuerySet.annotate` or `QuerySet.aggregate` is given it by position. Where exactly one source is not `None` and has a `name`, which an `F` has, the alias is that name, `"__"` and the class's `name` in lower case; otherwise the property raises `TypeError`. So a count of `"crew"` is `"crew__count"`, and a count with a filter, which has two sources that are not `None`, needs an alias as the sum of an arithmetic expression does (`django/db/models/aggregates.py:Aggregate.default_alias`). What the queryset makes of the error, and the names it refuses, is [Annotations, ordering and the other methods that change the query](../querysets/methods.md).

```text recording=sql
Count('crew').default_alias, Sum('tonnage').default_alias  ->  ('crew__count', 'tonnage__sum')
Sum(F('tonnage') * 2).default_alias  ->  raises TypeError: Complex expressions require an alias
Count('crew').get_source_expressions(), Count('crew', filter=Q(crew__name='Ada'), distinct=True).get_source_expressions()  ->  ([F(crew), None, None], [F(crew), AggregateFilter((AND: ('crew__name', 'Ada'))), None])
```

## The options as SQL

`Aggregate.as_sql` fills the three slots, and the backend's features decide two of them (`django/db/models/aggregates.py:Aggregate.as_sql`). It first refuses, with `NotSupportedError`, `distinct` on an aggregate of more than one argument where `supports_aggregate_distinct_multiple_argument` is off, which on SQLite it is (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_aggregate_distinct_multiple_argument`). Then it compiles the ordering: `AggregateOrderBy.as_sql` raises `NotSupportedError` where `supports_aggregate_order_by_clause` is off, and otherwise writes `" ORDER BY "` and its expressions, which go inside the function's parentheses; nothing catches that refusal. SQLite has the clause from version 3.44 (`django/db/models/aggregates.py:AggregateOrderBy`, `django/db/backends/sqlite3/features.py:DatabaseFeatures.supports_aggregate_order_by_clause`).

Then it compiles the filter. `AggregateFilter.as_sql` raises `NotSupportedError` where `supports_aggregate_filter_clause` is off, and this refusal `Aggregate.as_sql` does catch: it makes a copy of the aggregate without the filter, puts in place of the first argument a `Case` of one `When` whose condition is the filter's and whose value is the argument, so that a row the condition rejects contributes `"NULL"` to the function, and compiles the copy; a comment calls it the fallback for backends that lack the clause. Where the clause is supported it is written after the closing parenthesis, `" FILTER (WHERE "`, the condition and `")"` (`django/db/models/aggregates.py:AggregateFilter`, `django/db/backends/base/features.py:BaseDatabaseFeatures.supports_aggregate_filter_clause`). The condition is a `Q`, and becomes a where tree when the aggregate is resolved, as a `Q` does wherever an expression stands ([`filter`, `exclude` and `Q` objects](../querysets/filters.md)). The parameters are gathered in the template's order: the arguments', then the ordering's, then the filter's. The recording asks for the filter twice, the second time with `supports_aggregate_filter_clause` switched off for that one question.

```text recording=sql
Ship.objects.aggregate(n=Count('crew', distinct=True))  ->  {'n': 4}
  SQL SELECT COUNT(DISTINCT "crew_sailor"."id") AS "n" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id")
Ship.objects.aggregate(n=Count('crew', filter=Q(crew__signed_on__year__lt=2020)))  ->  {'n': 2}
  SQL SELECT COUNT("crew_sailor"."id") FILTER (WHERE "crew_sailor"."signed_on" < %s) AS "n" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") with params ('2020-01-01 00:00:00',)
Ship.objects.aggregate(n=Count('crew', filter=Q(crew__signed_on__year__lt=2020)))  ->  {'n': 2}
  SQL SELECT COUNT(CASE WHEN "crew_sailor"."signed_on" < %s THEN "crew_sailor"."id" ELSE NULL END) AS "n" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") with params ('2020-01-01 00:00:00',)
...
Sailor.objects.aggregate(names=StringAgg('name', Value(', '), order_by='-name'))  ->  {'names': 'Dag, Cora, Bram, Ada'}
  SQL SELECT STRING_AGG("crew_sailor"."name", %s ORDER BY "crew_sailor"."name" DESC) AS "names" FROM "crew_sailor" with params (', ',)
Sailor.objects.aggregate(names=StringAgg('name', Value(','), distinct=True))  ->  {'names': 'Ada,Bram,Cora,Dag'}
  SQL SELECT GROUP_CONCAT(DISTINCT "crew_sailor"."name") AS "names" FROM "crew_sailor"
...
Ship.objects.aggregate(Sum('tonnage', default=0), Min('tonnage'))  ->  {'tonnage__sum': 1680, 'tonnage__min': 480}
  SQL SELECT COALESCE(SUM("fleet_ship"."tonnage"), %s) AS "tonnage__sum", MIN("fleet_ship"."tonnage") AS "tonnage__min" FROM "fleet_ship" with params (0,)
```

The `"FILTER"` and the `"ORDER BY"` inside the parentheses are this backend's; with the feature off, the `"CASE"` stands in for the clause, and a row the condition rejects gives `"NULL"` to the count. The default is not in the template at all. In the last statement it has become a `"COALESCE"` around the sum, and that is the work of resolving.

## `resolve_expression`: the refusals and the default

`Aggregate.resolve_expression` is `BaseExpression.resolve_expression`, a copy whose sources are resolved, with three things added, and one argument dropped: it does not pass `for_save` on, since a comment says aggregates are not allowed in an update (`django/db/models/aggregates.py:Aggregate.resolve_expression`, `django/db/models/expressions.py:BaseExpression.resolve_expression`).

The first is the mark `is_summary`, which `BaseExpression.resolve_expression` sets on every copy from the argument written `summarize=True`: true when `get_aggregation` resolves an aggregate and false when `Query.add_annotation` does. A **summary** is an aggregate that is the statement's one answer, taken over all the rows, rather than a column of each row of a group. An `F` inside an aggregate resolves differently under the mark: `Query.resolve_ref` with `summarize=True` answers a name that is a selected annotation with a `Ref` to it, and refuses with `FieldError` a name that is an annotation `QuerySet.alias` left unselected, telling the caller to promote it with `annotate`; without the mark it answers with the annotation itself (`django/db/models/sql/query.py:Query.resolve_ref`).

The second is the refusal of an aggregate inside an aggregate, made two ways. Resolved for an annotation, the copy looks at each of its arguments, the filter and the ordering left out, and raises `FieldError` for one whose `contains_aggregate` is set, naming the argument as it was before resolving: an `F` by its name, so that a sum of an annotation that counts is refused as `Sum('n')`, and an aggregate by its class's `name`. Resolved as a summary, it looks instead at the names it refers to, which `BaseExpression.get_refs` collects from the `Ref` objects in it, and raises for one whose annotation is itself a summary: another aggregate of the same `aggregate` call, which `get_aggregation` puts among the query's annotations as it resolves them. A summary over an annotation that aggregates is allowed, and `get_aggregation` wraps the query in a subquery for it.

```text recording=sql
Ship.objects.annotate(n=Count('crew')).annotate(m=Sum('n'))  ->  raises FieldError: Cannot compute Sum('n'): 'n' is an aggregate
Ship.objects.annotate(m=Sum(Count('crew')))  ->  raises FieldError: Cannot compute Sum('Count'): 'Count' is an aggregate
Ship.objects.annotate(n=Count('crew')).aggregate(m=Sum('n'))  ->  {'m': 4}
  SQL SELECT SUM("n") FROM (SELECT COUNT("crew_sailor"."id") AS "n" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id") subquery
Ship.objects.annotate(n=Count('crew')).aggregate(m=Sum('n'), o=Max('m'))  ->  raises FieldError: Cannot compute Max('m'): 'm' is an aggregate
Ship.objects.aggregate(m=Sum('n'))  ->  raises FieldError: Cannot resolve keyword 'n' into field. Choices are: captain, captain_id, crew, home, home_id, id, name, tonnage, voyage
Ship.objects.alias(n=Count('crew')).aggregate(m=Sum('n'))  ->  raises FieldError: Cannot aggregate over the 'n' alias. Use annotate() to promote it.
```

The third is the default. Where `default` was given, the copy's own `default` is set to `None` and what is returned is not the aggregate but a `Coalesce` of the aggregate and the default, with the aggregate's output field and its `is_summary`. A default that is an expression is resolved first and given the aggregate's output field where it has none of its own; a plain value is wrapped in a `Value` with that field (`django/db/models/functions/comparison.py:Coalesce`). So what an annotation stores under its alias, and what the compiler writes, is a `"COALESCE"`, and its `contains_aggregate`, computed from the sources, is true as the aggregate's was.

`Aggregate.get_group_by_cols` returns an empty list: an aggregate puts no column into the grouping, where an expression without one puts itself (`django/db/models/aggregates.py:Aggregate.get_group_by_cols`).

## The classes

`Count` takes one expression, or the string `"*"`, which `Count.__init__` turns into a `Star`, the expression that writes `*`. Its output field is declared on the class, an `IntegerField`, its `empty_result_set_value` is 0, and it allows `distinct` (`django/db/models/aggregates.py:Count`, `django/db/models/expressions.py:Star`, `django/db/models/fields/__init__.py:IntegerField`). It is the one class of the module with `allows_composite_expressions` set, so that `BaseExpression.resolve_expression` lets a `ColPairs`, the column pair a composite primary key resolves to ([Expressions: `resolve_expression` and `as_sql`](expressions.md)), through; `Count.resolve_expression` then puts the first column of the pair in its place, a comment saying that a composite key is counted by its first column, and refuses `distinct` on one with `ValueError` (`django/db/models/aggregates.py:Count.resolve_expression`).

```text recording=sql
Ship.objects.aggregate(t=Sum('tonnage'), a=Avg('tonnage'), m=Max('tonnage'), s=StdDev('tonnage'), v=Variance('tonnage', sample=True))  ->  {'t': 1680, 'a': 840.0, 'm': 1200, 's': 360.0, 'v': 259200.0}
  SQL SELECT SUM("fleet_ship"."tonnage") AS "t", AVG("fleet_ship"."tonnage") AS "a", MAX("fleet_ship"."tonnage") AS "m", STDDEV_POP("fleet_ship"."tonnage") AS "s", VAR_SAMP("fleet_ship"."tonnage") AS "v" FROM "fleet_ship"
...
Ship.objects.aggregate(n=AnyValue('name'))  ->  {'n': 'Gannet'}
  SQL SELECT ANY_VALUE("fleet_ship"."name") AS "n" FROM "fleet_ship"
...
Berth.objects.aggregate(n=Count('pk'))  ->  {'n': 2}
  SQL SELECT COUNT("office_berth"."port_id") AS "n" FROM "office_berth"
Berth.objects.aggregate(n=Count('pk', distinct=True))  ->  raises ValueError: COUNT(DISTINCT) doesn't support composite primary keys
```

| class | SQL | takes | output field |
|---|---|---|---|
| `Count` | `"COUNT"` | one expression or `"*"`; `distinct`; `filter`, not with `"*"`; no `default` | an integer field |
| `Sum` | `"SUM"` | one; `distinct` | the source's |
| `Avg` | `"AVG"` | one; `distinct` | a decimal field where the source is one, a float field where it is an integer, else the source's |
| `Max` | `"MAX"` | one | the source's |
| `Min` | `"MIN"` | one | the source's |
| `StdDev` | `"STDDEV_POP"`; `"STDDEV_SAMP"` with `sample=True` | one | as `Avg` |
| `Variance` | `"VAR_POP"`; `"VAR_SAMP"` with `sample=True` | one | as `Avg` |
| `StringAgg` | `"STRING_AGG"`; `"GROUP_CONCAT"` on MySQL, on SQLite before 3.44, and on SQLite with `distinct` and the delimiter `Value(",")`; `"LISTAGG"` on Oracle | one and a delimiter; `distinct`; `order_by` | a text field |
| `AnyValue` | `"ANY_VALUE"` | one | the source's |
| `BitAnd`, `BitOr`, `BitXor` | `"BIT_AND"`, `"BIT_OR"`, `"BIT_XOR"`; with `"_AGG"` after on Oracle | one | the source's |

*The aggregate classes of `django/db/models/aggregates.py`: the function each writes, what its constructor accepts, and where its output field comes from. Every class takes `filter`, and every class but `Count` takes `default`.*

`Sum` and `Avg` carry `FixDurationInputMixin`, whose `as_mysql` and `as_oracle` see to an aggregate of durations on those two backends; `Avg`, `StdDev` and `Variance` carry `NumericOutputFieldMixin`, whose `_resolve_output_field` is the rule the table gives (`django/db/models/functions/mixins.py:FixDurationInputMixin`, `django/db/models/functions/mixins.py:NumericOutputFieldMixin`).

`StringAgg` takes an expression and a delimiter, wraps the delimiter in a `StringAggDelimiter`, a `Func` of one expression whose template is the expression alone, and passes both to `Aggregate.__init__`, so that it is an aggregate of two sources (`django/db/models/aggregates.py:StringAgg`, `django/db/models/aggregates.py:StringAggDelimiter`). Its three vendor methods rearrange the two. `StringAgg.as_oracle` writes `"LISTAGG"`, with the ordering outside the parentheses as `"WITHIN GROUP (ORDER BY ...)"`. `StringAgg.as_mysql` writes `"GROUP_CONCAT"`, takes the delimiter out of the sources and writes it last, where the delimiter's own `as_mysql` puts `"SEPARATOR"` before it, since a comment says MySQL takes the delimiter as a declaration at the end and not as an argument. `StringAgg.as_sqlite` has three ways: with `distinct` and the delimiter `Value(",")` it drops the delimiter from the sources and writes `"GROUP_CONCAT"`, which is what let the recorded statement of `StringAgg` with `distinct=True` above pass the check on `distinct` with several arguments; on SQLite before 3.44 it writes `"GROUP_CONCAT"` with the delimiter; otherwise `"STRING_AGG"` (`django/db/models/aggregates.py:StringAgg.as_sqlite`).

`AnyValue` writes `"ANY_VALUE"` of one expression, refuses to be compiled where `supports_any_value` is off, and is the one aggregate with `window_compatible` set to `False` (`django/db/models/aggregates.py:AnyValue`). The documentation of aggregation gives its use: a selected column that is neither grouped by nor aggregated, on a backend that rejects one (`docs/topics/db/aggregation.txt`). `BitAnd`, `BitOr` and `BitXor` are a `BitAggregate` each, with the function on the subclass; `BitAggregate.__init__` writes down whether a default was given, since `Aggregate.resolve_expression` will set `default` to `None`, and `BitAggregate.as_sql` refuses the aggregate where `supports_bit_aggregations` is off and the default where `supports_default_in_bit_aggregations` is (`django/db/models/aggregates.py:BitAggregate`).

> **Changed in 6.0.** `StringAgg` and `AnyValue` are in `django.db.models`; `StringAgg` was PostgreSQL's before, and the `order_by` argument of `Aggregate`, with `allow_order_by`, came in with it (`docs/releases/6.0.txt`).

> **Changed in 6.1.** `BitAnd`, `BitOr` and `BitXor` are in `django.db.models`, from `django.contrib.postgres`; and `StringAgg` accepts `distinct=True` on SQLite, with the delimiter `Value(",")` only (`docs/releases/6.1.txt`).

## `Query.get_aggregation`

`Query.get_aggregation` takes the database alias and a dictionary from aliases to aggregates, and returns a dictionary from the same aliases to values, having sent one statement or none (`django/db/models/sql/query.py:Query.get_aggregation`). It is the whole of `QuerySet.aggregate` after the arguments are checked, called on a copy of the query from `Query.chain`, and of `QuerySet.count` where the queryset has no result cache to measure ([`get`, `first`, `count` and the other methods that run a query at once](../querysets/results.md)).

**The aggregates are resolved against each other.** Each is resolved against the query with `summarize=True`, and a later expression of the call may use an earlier one's alias in arithmetic, though not aggregate over it, as told above. For that, after each aggregate is resolved it is put among the query's annotations under its alias and added to the selected set, which a comment says is so that the remaining ones may resolve against it, and the `Ref` such a name resolves to is replaced by the earlier aggregate itself. Each alias is checked by `Query.check_alias` first, and a resolved copy whose `contains_aggregate` is not set is refused with `TypeError`: a plain expression is not an aggregate. Once all are resolved they are taken out of the annotations and the mask of selected annotations is put back as it was, and the method has noted whether any aggregate refers to an annotation that holds a subquery or a window.

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

`Query.get_count` clones the query and returns `get_aggregation` of `Count("*")` under the alias `"__count"`, which is the alias in the statement; everything above holds for it, the wrapped case included (`django/db/models/sql/query.py:Query.get_count`).

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

`exists` serves one caller besides `QuerySet.exists`: `Exists`, the expression, wraps the query that `exists` makes, so that it stands inside another statement ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). On a union, each part is narrowed the same way ([Two queries into one: `combine` and `get_combinator_sql`](combining.md)). `get_aggregation` over a window, where the aggregate refers to an annotation that holds one or the where tree filters on one, is always the wrapped case, and [Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md) has the inner statement.
