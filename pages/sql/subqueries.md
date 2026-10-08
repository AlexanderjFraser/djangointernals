---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another

A `Query` is an expression, and `Query.resolve_expression` is how one comes to stand inside another: a clone whose aliases `bump_prefix` has renamed, which notes the outer query's tables as `external_aliases`, and in whose conditions the `ResolvedOuterRef` an `OuterRef` left has become a column of the outer table. `Subquery` and `Exists` wrap such a query to stand as a selected column or a condition; a queryset given as the value of a filter goes the same way with no wrapper at all.

A query inside another has four things to do. It has to keep its tables apart from the outer query's, since both may read the same table and SQL tells them apart by alias alone. It has to be able to refer to the outer query's columns, which is what makes a subquery correlated: the first sailor of each ship, not of all ships. It has to be written wherever an expression is wanted, in parentheses, as a column of the select list, as the right side of a comparison, or as a condition under `"EXISTS"`. And it has to know when it can match nothing, so that a condition on it can be decided without the database. The opening page, [From QuerySet to SQL](../sql.md), says that `Query` is built on `BaseExpression` for this reason; this page is what that buys.

## A query as an expression: `Query.resolve_expression`

`Query.resolve_expression` binds a query to another: the outer query is what the inner one is bound to, and the resolved object is a copy, which the method makes with `Query.clone` and then does four things to (`django/db/models/sql/query.py:Query.resolve_expression`).

It renames the clone's aliases. `Query.bump_prefix` is given the outer query and, where the two have the same `alias_prefix`, gives the clone the next prefix that is not in `subq_aliases`, `"U"` after the `"T"` every query starts with, and adds it to the `subq_aliases` of both queries, so that a third query resolved against either avoids it; a query whose prefix differs from the outer's already, as one resolved a second time at a deeper level, is left as it is. The clone's `change_aliases` then renames every alias in its map to the prefix and a number, relabelling each reference in the where tree, the select, the group by and the annotations, which replaces each leaf of the where tree by a relabelled copy (`django/db/models/sql/query.py:Query.bump_prefix`, `django/db/models/sql/query.py:Query.change_aliases`). The docstring gives the reason, that the two queries' aliases must not conflict, and [Tables and joins: the alias map and join promotion](joins.md) tells the method in full.

It marks the clone with `subquery` true. The flag is what the rest of the chapter reads: `Query.as_sql` puts the statement in parentheses, and clears the ordering on a backend that does not ignore an unnecessary one; the compiler wraps a subquery whose select list has extra columns in another select, and sets the parentheses of a compound statement by it; a tuple comparison against a subquery is refused on some backends by it; and `BaseExpression.contains_subquery` is true of an expression one of whose sources carries it (`django/db/models/sql/query.py:Query.as_sql`, `django/db/models/expressions.py:BaseExpression.contains_subquery`).

It resolves the clone's where tree against the outer query, leaf by leaf: `WhereNode.resolve_expression` has each leaf's left side and right side resolved where they can be, and that is where a `ResolvedOuterRef` in a condition becomes a column (`django/db/models/sql/where.py:WhereNode._resolve_node`). The method returns a clone of the tree, which `Query.resolve_expression` throws away; the resolution reaches the clone's tree all the same, because `WhereNode.clone` keeps the leaf objects, a lookup having no `clone` of its own, and `_resolve_node` sets the sides on those very objects (`django/db/models/sql/where.py:WhereNode.clone`). What keeps the queryset's own leaves out of it is `change_aliases`, which had replaced each leaf by a relabelled copy first. The parts of a combined query are resolved the same way, each against the outer query, and so is each annotation; an annotation that is itself a subquery has the clone's external aliases added to its own.

It notes the outer query's tables. `external_aliases` maps each alias of the outer query's alias map to whether that table stands under an alias other than its own name, and a comment in the constructor says it exists because a query may refer to aliases of an outer query, as one made by `split_exclude` does (`django/db/models/sql/query.py:Query.__init__`). `change_aliases` keeps the map up to date when the clone is renamed again, and `Query.get_external_cols` reads its keys.

What follows was recorded from a running Django, on SQLite, over the shipping line of the opening page. A line at the left is Python as it was run, with its value after `->` where it is a question, and nothing after it where it only bound a name; the lines set in under it are the calls it set going, nested as they were made, with only the calls the passage is about written down, and `->` what a call returned; a method is sometimes written as the object's class and, in parentheses, the class whose method ran; a line that begins `SQL` is a statement as Django handed it to its cursor.

```text recording=sql
first_hand = Sailor.objects.filter(ship=OuterRef('pk')).order_by('name').values('name')[:1]
...
sub = Subquery(first_hand)
sub.query is first_hand.query, sub.query.subquery, first_hand.query.subquery, said(sub.get_source_expressions())  ->  (False, True, False, [a Query of Sailor])
outer = Ship.objects.all().query
resolved = sub.resolve_expression(outer)
type(resolved).__name__, resolved.subquery, resolved.alias_prefix, list(resolved.alias_map), resolved.external_aliases, sorted(outer.subq_aliases)  ->  ('Query', True, 'U', ['U0', 'U1'], {'fleet_ship': False}, ['T', 'U'])
said(resolved.where)  ->  (AND: RelatedExact(Col(U0, crew.Sailor.ship), Col(fleet_ship, fleet.Ship.id)))
```

`Subquery` had already cloned the queryset's query and marked the clone, and the queryset's own query is untouched. The resolved object is a `Query`, not a `Subquery`: why `Subquery.resolve_expression` removes the wrapper is told under `Subquery`. Its prefix is `"U"` and its alias map has two entries, `"U0"` for the sailors' table and `"U1"` for the ships' table that the filter on `"ship"` joined and `trim_joins` took back, left in the map with a count of zero as the opening page describes. The outer query's one table is external and not aliased, and the outer query now knows `"U"` as a prefix in use. The where tree compares the sailors' `"ship_id"` under the new alias with a column of the outer table, `Col(fleet_ship, fleet.Ship.id)`, which is what the `OuterRef` became.

```text recording=sql
A subquery resolved and compiled: OuterRef becomes a ResolvedOuterRef as the inner filter is built, and a Col of the outer table when the inner query is resolved against the outer
    first_hand = Sailor.objects.filter(ship=OuterRef('pk')).order_by('name').values('name')[:1]
      OuterRef.resolve_expression  (OuterRef(pk))  ->  ResolvedOuterRef(pk)
    with_first = Ship.objects.annotate(first=Subquery(first_hand))
      Subquery.resolve_expression  (Subquery.resolve_expression)
        Query.resolve_expression(query=a Query of Ship)  (of a Query of Sailor)
          Query.bump_prefix(a Query of Ship)
            Query.change_aliases({'crew_sailor': 'U0', 'fleet_ship': 'U1'})
          WhereNode.resolve_expression
            ResolvedOuterRef.resolve_expression  (ResolvedOuterRef(pk))
              F.resolve_expression  (ResolvedOuterRef(pk))
                Query.resolve_ref(name='pk')  ->  Col(fleet_ship, fleet.Ship.id)
                -> Col(fleet_ship, fleet.Ship.id)
              -> Col(fleet_ship, fleet.Ship.id)
          -> a Query of Sailor
        -> a Query of Sailor
    with_first.query.get_compiler('default').as_sql()
      Query.as_sql  (of a Query of Sailor)  ->  ('(SELECT "U0"."name" AS "name" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = ("fleet_ship"."id") ORDER BY 1 ASC LIMIT 1)', ())
```

The `OuterRef` became a `ResolvedOuterRef` as first_hand's filter was built, with no outer query in sight. `Subquery.resolve_expression` then resolved its one source, the query, which bumped its prefix and renamed its two aliases before the where tree was resolved; inside the where tree the `ResolvedOuterRef` resolved as an `F` does, by asking the outer query's `resolve_ref` for the column named `"pk"` ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). When the outer statement was written, `Query.as_sql` wrote the inner one in parentheses, with the outer column inside it. The parentheses round `"fleet_ship"."id"` are `Lookup.process_rhs` wrapping a compiled expression ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)), and `ORDER BY 1` orders by position because the ordered column is the selected one ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)).

> **Trap.** `bump_prefix` renames the entries the alias map has, and a query that has asked for no table yet has none: the ships ordered by name and cut to one, `order_by('name')[:1]`, have filtered nothing and selected nothing in particular, so the query's map is empty until the compiler asks for its initial alias at the start of `SQLCompiler.setup_query` (`django/db/models/sql/compiler.py:SQLCompiler.setup_query`), while `values('tonnage')` on the ships, which has to find its column, fills it. Such a query stands inside another with its table under the table's own name, as the recording under The ordering of a subquery shows.

```text recording=sql
list(Ship.objects.order_by('name')[:1].query.alias_map), list(Ship.objects.values('tonnage').query.alias_map)  ->  ([], ['fleet_ship'])
```

A resolved query is read from outside through `get_external_cols`, `get_group_by_cols` and `output_field`. `Query.get_external_cols` walks the annotations and the where tree's leaves, yielding each `Col` and, for a nested subquery, its own external columns, and keeps those whose alias is in `external_aliases` (`django/db/models/sql/query.py:Query.get_external_cols`). `Query.get_group_by_cols` returns those columns, so that a grouped outer query groups by the outer columns a subquery refers to rather than by the subquery; but where any of them is marked `possibly_multivalued`, which `ResolvedOuterRef` sets on a column whose name holds a `"__"`, it returns the wrapper it was given, or the query itself, so that the whole subquery is grouped by (`django/db/models/sql/query.py:Query.get_group_by_cols`) ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md)). `Query.output_field` is the type a query has as an expression: the target of its one selected column, or the output field of its one selected annotation, and `None` where neither is exactly one (`django/db/models/sql/query.py:Query.output_field`).

```text recording=sql
resolved.get_external_cols(), resolved.get_group_by_cols(), resolved.contains_subquery, Ship.objects.annotate(first=Subquery(first_hand)).query.annotations['first'].contains_subquery  ->  ([Col(fleet_ship, fleet.Ship.id)], [Col(fleet_ship, fleet.Ship.id)], True, True)
said(Subquery(Sailor.objects.filter(name=OuterRef('crew__name')).values('id')[:1]).resolve_expression(Ship.objects.all().query).get_group_by_cols())  ->  [a Query of Sailor]
```

The one external column is the ship's key; the group-by columns are the same, since `"pk"` holds no `"__"`; `contains_subquery` is true both of the resolved query and of the annotation the outer query kept, which is such a resolved query with no wrapper round it; and a subquery whose outer reference is `"crew__name"` is grouped by as a whole.

## `OuterRef` and `ResolvedOuterRef`

`OuterRef` is an `F` that defers its resolution by one query (`django/db/models/expressions.py:OuterRef`). An `F` resolves against the query it is given; an `OuterRef` resolves against the query outside that one. Its `resolve_expression` does not look at the query it is handed at all: it returns a `ResolvedOuterRef` of its name, or, where its name is itself an `OuterRef`, that inner `OuterRef` with one level taken off (`django/db/models/expressions.py:OuterRef.resolve_expression`). So an `OuterRef` in the filter of a queryset becomes a `ResolvedOuterRef` as soon as the filter is built, when `Query.resolve_lookup_value` resolves the value against the inner query ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)).

`ResolvedOuterRef` is an `F` too, and resolving it is an ordinary `F`'s resolution: the query it is given, which is the outer query when the inner one is resolved, finds the name with `resolve_ref`, a column or an annotation of the outer query. It refuses one thing, an outer expression with a window in it, with `NotSupportedError` ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)), and marks the column `possibly_multivalued` where the name holds a `"__"`, a comment noting that the mark should one day be reserved for the relations that are many (`django/db/models/expressions.py:ResolvedOuterRef.resolve_expression`). Its `relabeled_clone` returns itself, since it refers to no alias of the query being renamed, and its `get_group_by_cols` is empty. Its `as_sql` raises `ValueError`, saying that the queryset contains a reference to an outer query and may be used in a subquery alone: a queryset filtered with an `OuterRef` cannot be run on its own, and the refusal comes when its statement is written (`django/db/models/expressions.py:ResolvedOuterRef.as_sql`).

```text figure=inner-and-outer
the outer query, a Query of Ship                      the inner query, a Query of Sailor, resolved against it

  alias_map:     fleet_ship                             alias_map:        U0 (crew_sailor), U1 (fleet_ship, count 0)
  subq_aliases:  T, U                                   alias_prefix:     U        subquery: True
  alias_prefix:  T                                      external_aliases: fleet_ship, not aliased
  annotations:   first, the inner query

  SELECT "fleet_ship"."id", "fleet_ship"."name", ...,   (SELECT "U0"."name" AS "name"
         ( the inner statement ) AS "first"              FROM "crew_sailor" "U0"
  FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC     WHERE "U0"."ship_id" = ("fleet_ship"."id")
            ^                                            ORDER BY 1 ASC LIMIT 1)
            |
            |                                           the OuterRef became the column in two steps
            |                                           OuterRef('pk')
            |                                               |  as the inner filter is built
            |                                               v
            |                                           ResolvedOuterRef('pk')
            |                                               |  as the inner query is resolved
            |                                               v
            +------------------------------------------ Col(fleet_ship, fleet.Ship.id)
                 a column of the outer table, written inside the inner statement
```

*The query of the ships annotated with `first=Subquery(first_hand)` beside the query of first_hand once it has been resolved against it. The inner query has aliases of its own under the prefix `"U"`, notes the outer query's table as external, and holds in its where tree a column of the outer table, which the `OuterRef` became in two steps: a `ResolvedOuterRef` when the inner queryset was filtered, and a `Col` when the inner query was resolved against the outer one.*

Each level of nesting takes one `OuterRef` off. A subquery inside a subquery that needs the outermost query's column writes `OuterRef(OuterRef('pk'))`: the first resolution, against the innermost query, leaves `OuterRef('pk')`; the second, against the middle query, leaves `ResolvedOuterRef('pk')`; the third, against the outermost, finds the column.

```text recording=sql
OuterRef inside OuterRef: each level of nesting takes one off
    sql_of(Port.objects.annotate(x=Subquery(Ship.objects.filter(home=OuterRef('pk')).annotate(y=Subquery(Sailor.objects.filter(ship=OuterRef(OuterRef('pk'))).values('name')[:1])).values('y')[:1])).values('name', 'x'))  ->  ('SELECT "fleet_port"."name" AS "name", (SELECT (SELECT "U0"."name" AS "name" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = ("fleet_port"."id") LIMIT 1) AS "y" FROM "fleet_ship" "V0" WHERE "V0"."home_id" = ("fleet_port"."id") ORDER BY "V0"."name" ASC LIMIT 1) AS "x" FROM "fleet_port" ORDER BY 1 ASC', ())
    OuterRef('pk').resolve_expression(), OuterRef(OuterRef('pk')).resolve_expression(), OuterRef(OuterRef('pk')).resolve_expression().resolve_expression()  ->  (ResolvedOuterRef(pk), OuterRef(pk), ResolvedOuterRef(pk))
    Sailor.objects.filter(ship=OuterRef('pk'))  ->  raises ValueError: This queryset contains a reference to an outer query and may only be used in a subquery.
    list(Sailor.objects.filter(ship=OuterRef('pk')))  ->  raises ValueError: This queryset contains a reference to an outer query and may only be used in a subquery.
```

In the statement the innermost query, under `"U0"`, compares its `"ship_id"` with `"fleet_port"."id"`, the outermost table's column, across the middle query under `"V0"`; the middle query got `"V"` because `"U"` was already in its `subq_aliases` from the resolution of the query inside it. The last two lines are `ResolvedOuterRef.as_sql` refusing: the first when the queryset's repr evaluated it, the second when a list was made of it.

## `Subquery`

`Subquery` wraps a query so that it can be written as an expression with a template, `"(%(subquery)s)"` by default (`django/db/models/expressions.py:Subquery`). It is built on `BaseExpression` and `Combinable`, so arithmetic on one makes a `CombinedExpression` ([Expressions: `resolve_expression` and `as_sql`](expressions.md)). Its constructor takes a queryset or a query, clones the query, marks the clone `subquery`, takes a `template` out of the keyword arguments where one is given, and keeps the rest as `extra` for the template to fill; an `output_field` is passed to `BaseExpression` as for any expression. The query is its one source expression, `Subquery.copy` clones it afresh, and `Subquery.external_aliases` and `Subquery.get_external_cols` are the query's. `Subquery.as_sql` has the query write itself through `Query.as_sql`, strips the parentheses that method added, and puts the result into the template under the name `"subquery"`, with `extra` and whatever the caller passed as the rest of the template's values (`django/db/models/expressions.py:Subquery.as_sql`). `Subquery.get_group_by_cols` asks the query with itself as the wrapper. `contains_aggregate` is false on the class, so an aggregate inside the subquery does not count as one of the outer query's, and `empty_result_set_value` is `None`: a selected subquery whose query can match nothing is written as `"NULL"` by the compiler ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)).

Its output field is the query's own, through `_resolve_output_field`, unless one was given. And its `resolve_expression` removes the wrapper: after the ordinary resolution of its sources, which is `Query.resolve_expression` on the query, a plain `Subquery` with the default template marks the resolved query `contains_subquery` and returns that query in its own place, a comment calling the wrapper an unnecessary shim that complicates the inspection of a lookup's right side. Where an output field was given whose type is not that of the query's own, the query is returned inside an `ExpressionWrapper` of that field instead. A subclass, or a `Subquery` given another template, stays as it is (`django/db/models/expressions.py:Subquery.resolve_expression`).

```text recording=sql
type(Subquery(first_hand, output_field=models.CharField()).resolve_expression(outer)).__name__, type(Subquery(first_hand, output_field=models.IntegerField()).resolve_expression(outer)).__name__  ->  ('Query', 'ExpressionWrapper')
type(Subquery(first_hand).resolve_expression(outer).output_field).__name__  ->  'CharField'
Subquery(Sailor.objects.filter(ship=OuterRef('pk')).values('name', 'id')[:1]).resolve_expression(outer).output_field  ->  raises OutputFieldIsNoneError: Cannot resolve expression type, unknown output_field
```

With a `CharField` given, the type the query has already, the resolved object is the query; with an `IntegerField` it is the wrapper (`django/db/models/fields/__init__.py:CharField`, `django/db/models/fields/__init__.py:IntegerField`). Without one, the query's output field is the type of its one selected column, `"name"`. The last line selects two columns: the query's `output_field` is then `None`, and reading the wrapper's output field raises `OutputFieldIsNoneError`, which is where the resolution stops, since it reads the output field to decide what to return.

The annotation recorded under A query as an expression is the common case: the resolved query stands in `Query.annotations` under `"first"`, and the compiler selects it in parentheses under that alias ([Annotations, ordering and the other methods that change the query](../querysets/methods.md)).

## `Exists`

`Exists` is a `Subquery` with the template `"EXISTS(%(subquery)s)"`, a `BooleanField` as its output field, so that it is conditional and can stand in a filter and in a `When`, and `False` as its `empty_result_set_value` (`django/db/models/expressions.py:Exists`, `django/db/models/fields/__init__.py:BooleanField`). Its constructor replaces the query it was given with that query's `Query.exists`: a clone whose select list is cleared unless the query is both distinct and sliced, with a grouped query's grouping made explicit first, whose ordering is cleared, which asks for one row, and which selects the constant 1 under the alias `"a"`; a union's parts are each given the same treatment without the limit (`django/db/models/sql/query.py:Query.exists`) ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)). So, unless the queryset is both distinct and sliced, what it selected is thrown away and `values` on it changes nothing.

`Exists.as_sql` catches the `EmptyResultSet` an inner query raises when it can match nothing and compiles `Value(False)` in its place, or writes `"1=0"` on a backend without boolean expressions in a select list (`django/db/models/expressions.py:Exists.as_sql`). `Exists.select_format` is for such a backend too: where `supports_boolean_expr_in_select_clause` is off, a selected `Exists` is wrapped as `"CASE WHEN"` the subquery `"THEN 1 ELSE 0 END"` (`django/db/models/expressions.py:Exists.select_format`).

```text recording=sql
tail(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk'), name='Ada'))))  ->  ('FROM "fleet_ship" WHERE EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U0" WHERE ("U0"."name" = %s AND "U0"."ship_id" = ("fleet_ship"."id")) LIMIT 1) ORDER BY "fleet_ship"."name" ASC', (1, 'Ada'))
```

As a filter an `Exists` is a conditional expression, and `Query.build_filter` resolves it and wraps it as `Exact(Exists(...), True)`, which `Exact.as_sql` writes as the expression alone, `WHERE EXISTS(...)`, and with `"NOT"` in front where the right side is `False`; `~Exists(...)` is a `NegatedExpression`, which writes its own `"NOT"` ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md), [Expressions: `resolve_expression` and `as_sql`](expressions.md)):

```text recording=sql
where_said(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk')))))  ->  (AND: Exact(Exists(a Query of Sailor), True))
```

```text recording=sql
tail(Ship.objects.filter(Exists(Sailor.objects.none())))  ->  ('FROM "fleet_ship" WHERE %s ORDER BY "fleet_ship"."name" ASC', (False,))
sql_of(Ship.objects.annotate(x=Exists(Sailor.objects.none())).values('x'))  ->  ('SELECT %s AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', (False,))
Exists(Sailor.objects.all()).query.select, Exists(Sailor.objects.all()).query.high_mark, Exists(Sailor.objects.all()).output_field, Exists(Sailor.objects.all()).empty_result_set_value, Subquery(Sailor.objects.all()).empty_result_set_value  ->  ((), 1, <django.db.models.fields.BooleanField>, False, None)
...
tail(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk')).values('name'))))  ->  ('FROM "fleet_ship" WHERE EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = ("fleet_ship"."id") LIMIT 1) ORDER BY "fleet_ship"."name" ASC', (1,))
```

The inner query made by `QuerySet.none` raised `EmptyResultSet` when compiled, and the condition became the parameter `False`; selected as an annotation, the same `False` stands under the alias. The attributes are the constructor's doing: no select, a limit of one, the boolean output field, and the two classes' values for an empty result. The last line selected `"name"` on the inner queryset and got the same `SELECT %s AS "a"` as the first.

## A queryset as the value of a filter

A queryset on the right of `"in"`, `"exact"` or a comparison is a subquery without a wrapper. `Query.resolve_lookup_value` resolves any value that has `resolve_expression`, and a queryset has one: `QuerySet.resolve_expression` returns its query resolved against the outer one, with the queryset's database alias, `QuerySet._db`, copied onto it (`django/db/models/query.py:QuerySet.resolve_expression`). What the lookup then holds on its right is a `Query` marked `subquery`. Before the lookup is built, `Query.check_related_objects` refuses a queryset of another model for a relation unless it has chosen its columns ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)). `In.get_prep_lookup` and `Exact.get_prep_lookup` then make the subquery fit the left side: each compares the subquery's width with the left side's and refuses a mismatch with `ValueError`, and where the queryset has `has_select_fields` false, has chosen no columns, each clears its select clause and adds `"pk"`; `Exact` first refuses a query that `has_limit_one` denies, and `In` clears the ordering ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md), `django/db/models/lookups.py:In.get_prep_lookup`, `django/db/models/lookups.py:Exact.get_prep_lookup`). The width is `Query._subquery_fields_len`: the model's key columns where the queryset has chosen no columns or its select list is empty, and otherwise the select list's, a composite key counted by its columns (`django/db/models/sql/query.py:Query._subquery_fields_len`). `In.process_rhs` adds one refusal at compile time, a subquery whose queryset was bound to another database than the connection's, with a message that says to evaluate it as a list instead (`django/db/models/lookups.py:In.process_rhs`). A relation on the left adds the preparation of [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](related-lookups.md).

```text recording=sql
tail(Ship.objects.filter(tonnage__gt=Subquery(Ship.objects.filter(name='Petrel').values('tonnage')[:1])))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > (SELECT "U0"."tonnage" AS "tonnage" FROM "fleet_ship" "U0" WHERE "U0"."name" = %s ORDER BY "U0"."name" ASC LIMIT 1) ORDER BY "fleet_ship"."name" ASC', ('Petrel',))
...
tail(Ship.objects.filter(tonnage=Subquery(Ship.objects.order_by('-tonnage').values('tonnage')[:1]) - 720))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" = ((SELECT "U0"."tonnage" AS "tonnage" FROM "fleet_ship" "U0" ORDER BY 1 DESC LIMIT 1) - %s) ORDER BY "fleet_ship"."name" ASC', (720,))
tail(Ship.objects.filter(pk__in=Sailor.objects.filter(name='Ada').values('ship')))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."id" IN (SELECT "U0"."ship_id" AS "ship" FROM "crew_sailor" "U0" WHERE "U0"."name" = %s) ORDER BY "fleet_ship"."name" ASC', ('Ada',))
tail(Ship.objects.filter(pk__in=Sailor.objects.filter(name='Ada').values_list('ship', flat=True)))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."id" IN (SELECT "U0"."ship_id" AS "ship" FROM "crew_sailor" "U0" WHERE "U0"."name" = %s) ORDER BY "fleet_ship"."name" ASC', ('Ada',))
tail(Ship.objects.filter(pk__in=Subquery(Sailor.objects.filter(name='Ada').values('ship'))))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."id" IN (SELECT "U0"."ship_id" AS "ship" FROM "crew_sailor" "U0" WHERE "U0"."name" = %s) ORDER BY "fleet_ship"."name" ASC', ('Ada',))
```

The first line is an explicit `Subquery` on the right of `"gt"`, which the resolution reduced to its query, and the second is one in arithmetic, a `CombinedExpression` whose left side is the subquery. The last three lines are one statement written three ways: a `values` queryset, a flat `values_list` queryset and a `Subquery` of the first all reach `In.get_prep_lookup` as the same resolved query, and the column `"ship"` each had chosen is kept under its alias.

## The ordering of a subquery

A subquery's ordering is the inner query's own, and what becomes of it depends on who holds the subquery. `In.get_prep_lookup` clears it with `clear_default=True`, so that the model's default ordering does not come back either (`django/db/models/sql/query.py:Query.clear_ordering`). `Exact.get_prep_lookup` leaves it, and a query limited to one row is written with it. A `Subquery` leaves it too. Then `Query.as_sql` asks the backend: where `ignores_unnecessary_order_by_in_subqueries` is off, as it is for Oracle, it clears the ordering without force, which `clear_ordering` declines to do for a query that is sliced, has distinct fields or asks for a lock, so a sliced subquery keeps its ordering there too (`django/db/backends/base/features.py:BaseDatabaseFeatures.ignores_unnecessary_order_by_in_subqueries`).

A subquery that is `distinct()` without fields and ordered by a column it does not select has that column added to its select list, and a subquery must yield as many columns as its left side expects. So where the query is a subquery and `get_extra_select` added columns, `SQLCompiler.as_sql` wraps the statement in another select that reads the wanted columns alone from it, under the alias `"subquery"` ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md), `django/db/models/sql/compiler.py:SQLCompiler.as_sql`).

```text recording=sql
The ordering of a query inside another: cleared by In, kept under a slice, and the extra columns of distinct with order_by wrapped away
    tail(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000).order_by('name')))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (SELECT "U0"."id" FROM "fleet_ship" "U0" WHERE "U0"."tonnage" > %s)', (1000,))
    tail(Sailor.objects.filter(ship=Ship.objects.order_by('name')[:1]))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = (SELECT "fleet_ship"."id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC LIMIT 1)', ())
    sql_of(Ship.objects.annotate(x=Subquery(Sailor.objects.filter(ship=OuterRef('pk')).order_by('-name').values('name')[:1])).values('x'))  ->  ('SELECT (SELECT "U0"."name" AS "name" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = ("fleet_ship"."id") ORDER BY 1 DESC LIMIT 1) AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
    connection.features.ignores_unnecessary_order_by_in_subqueries  ->  True
    sql_of(Ship.objects.annotate(x=Subquery(Sailor.objects.filter(ship=OuterRef('pk')).distinct().order_by('signed_on').values('name')[:1])).values('x'))  ->  ('SELECT (SELECT "subquery"."name" FROM (SELECT DISTINCT "U0"."name" AS "name", "U0"."signed_on" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = ("fleet_ship"."id") ORDER BY "U0"."signed_on" ASC LIMIT 1) subquery) AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
```

The ordered queryset under `"in"` lost its ordering; the sliced one under `"exact"` kept it, and stands under its table's own name, having had no alias to rename; the `Subquery` kept its descending order, written by position. The last line is the wrap: the inner statement selects `"name"` and `"signed_on"`, and the statement round it selects `"subquery"."name"` alone.

## Django's own subqueries

Django makes subqueries of its own by the same means. `Query.split_exclude` builds one for an `exclude` across a relation that can reach several rows, filtering the inner query with a `ResolvedOuterRef` or by an external alias, and makes an `Exists` of it for the outer where tree, where the negation of the `exclude` puts `"NOT"` in front ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)). `Query.get_aggregation` marks a clone of the query `subquery` and makes it the inner query of an `AggregateQuery` where the query is sliced, distinct, grouped or combined, among other conditions, and where an aggregate refers to an annotation whose `contains_subquery` is true ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)). The compiler's `get_qualify_sql` does the same to write a filter on a window ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)); a compound statement stands inside another with parentheses chosen by the flag ([Two queries into one: `combine` and `get_combinator_sql`](combining.md)); and an update or a delete whose filter joins another table moves the joins into a subquery on the primary key ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md)).
