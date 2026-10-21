---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Aggregates: `Aggregate` and `Count`

`Aggregate` is the `Func` that folds the rows of a group into one value, `"COUNT"`, `"SUM"`, `"STRING_AGG"`, and is marked as one, so that the query groups for it and a filter on it goes to `"HAVING"`.

An aggregate has three jobs that a plain function has not. It has to say that it is one, since the shape of the statement turns on it: the compiler groups by the selected columns that are not aggregated, and a condition that compares an aggregate cannot stand in `"WHERE"`, where the database tests one row at a time, and is moved to `"HAVING"` ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](../sql/grouping.md)). Each of those decisions is read off one mark, `contains_aggregate`, which an aggregate sets on its class and most other expressions compute from their parts; a `Window` sets it `False` on its class, a comment saying that the grouping an aggregate would bring in is not wanted for one. It has to refuse to stand inside another aggregate. And it has to answer for no rows: the database answers a sum of nothing with a null, and where the compiler can tell that the query matches nothing, and every aggregate has an answer for no rows, it sends no statement at all. Beside these it carries what SQL lets an aggregate carry: `"DISTINCT"` on its argument, a `"FILTER"` clause, an `"ORDER BY"` inside the parentheses for a function whose result depends on the order of the rows, and a default for the null.

## `Aggregate`: a `Func` with a mark and four options

`Aggregate` is a subclass of `Func`, and what a function class declares, `function`, `template`, `arity`, it declares too ([Transforms and database functions: `Transform` and `Func`](functions.md)). Its template has three slots that `Func`'s has not, `"%(function)s(%(distinct)s%(expressions)s%(order_by)s)%(filter)s"`, one for each option that is written as SQL. On the class, `Aggregate.contains_aggregate` is `True`, where `BaseExpression` computes it from the sources; `window_compatible` is `True`, so that an aggregate may be the function a `Window` runs over its partition ([Window expressions: `Window` and `WindowFrame`](windows.md)); `empty_result_set_value`, the answer for no rows, is `None`; `allow_distinct` and `allow_order_by` are `False`, and each subclass turns on what its function accepts; and `name` is what the class is called in a message and in a default alias (`django/db/models/aggregates.py:Aggregate`).

`Aggregate.__init__` takes the function's arguments by position and the four options by keyword, and refuses three of them with `TypeError` according to the class: `distinct` unless `allow_distinct` is set, `order_by` unless `allow_order_by` is, and `default` where the class has an `empty_result_set_value` that is not `None`, which `Count` has. It keeps `distinct` as given, wraps the filter in an `AggregateFilter`, keeps the default as given until the aggregate is resolved, and turns the ordering into an `AggregateOrderBy` through `OrderByList.from_param`, which takes a string, an expression, or a list or tuple of either and raises `ValueError` for anything else; the arguments go to `Func.__init__` (`django/db/models/aggregates.py:Aggregate.__init__`, `django/db/models/expressions.py:OrderByList.from_param`).

What follows was recorded from a running Django, on SQLite, over the models of [Models and fields](../models.md): a line is a question and its answer after `->`, with a statement it sent under it as `SQL`, or a call with the calls it set going nested under it and `->` what each returned.

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

`Count` takes one expression, or the string `"*"`, which `Count.__init__` turns into a `Star`, the expression that writes `*`. Its output field is declared on the class, an `IntegerField`, its `empty_result_set_value` is 0, and it allows `distinct` (`django/db/models/aggregates.py:Count`, `django/db/models/expressions.py:Star`, `django/db/models/fields/__init__.py:IntegerField`). It is the one class of the module with `allows_composite_expressions` set, so that `BaseExpression.resolve_expression` lets a `ColPairs`, the column pair a composite primary key resolves to ([Expressions: `resolve_expression` and `as_sql`](protocol.md)), through; `Count.resolve_expression` then puts the first column of the pair in its place, a comment saying that a composite key is counted by its first column, and refuses `distinct` on one with `ValueError` (`django/db/models/aggregates.py:Count.resolve_expression`).

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
