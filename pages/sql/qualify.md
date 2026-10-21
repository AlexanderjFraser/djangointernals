---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The QUALIFY rewrite: a filter on a window

A condition on a window cannot stand in a statement's `"WHERE"`, so where a filter names one, `WhereNode.split_having_qualify` sets the condition aside and `SQLCompiler.get_qualify_sql` writes the statement inside another and tests the condition there.

The recordings below were made from a running Django, on SQLite, over harbour's models, which [Models and fields](../models.md) lists. A line at the left is Python as it was run, with its value after `->` where it is shown, or the word raises and the exception; calls it set going are set in under it, nested as they were made, `->` there being what a call returned, and a line that begins `SQL` is a statement as Django handed it to its cursor. A line beginning sql_of( asks for a queryset's statement and its parameters as its compiler returns them, unsent, and a line of three dots stands for lines of the block left out.

## A filter on a window

A window reaches the where tree as any annotation does: `filter(n=1)` on a queryset whose `"n"` is a window resolves the name to the window itself, and the lookup made of it, `IntegerFieldExact` with the window on its left, is the tree's child ([The where clause: `add_q` and `build_filter`](../query/where.md)). The lookup's `contains_over_clause` is true through its left side, and so is the tree's. The compiler does not write that lookup into the `"WHERE"`. What Django does instead is write the statement without the condition, inside another statement that reads its rows as a table and tests the condition on them. The name it gives the device, in the code and in the alias of the inner statement, is `"qualify"`.

```text recording=sql
numbered = Sailor.objects.annotate(n=Window(RowNumber(), partition_by='ship', order_by='name'))
numbered.filter(n=1).query.get_compiler('default').as_sql()
  SQLCompiler.as_sql
    SQLCompiler.pre_sql_setup
      SQLCompiler.get_select  ->  (5 columns, klass_info for Sailor, {'n': 4})
      SQLCompiler.get_order_by  ->  []
      WhereNode.split_having_qualify  ->  (None, None, (AND: IntegerFieldExact(<Window: RowNumber() OVER (PARTITION BY Col(crew_sailor, crew.Sailor.ship)Col(crew_sailor, crew.Sailor.name))>, 1)))
      -> (extra_select of 0, order_by of 0, group_by of 0)
    SQLCompiler.get_qualify_sql
      SQLCompiler.get_select  ->  (5 columns, klass_info for Sailor, {'n': 4})
      SQLCompiler.get_order_by  ->  []
      SQLCompiler.as_sql(with_col_aliases=True)
        SQLCompiler.pre_sql_setup
          SQLCompiler.get_select  ->  (5 columns, klass_info for Sailor, {'n': 4})
          SQLCompiler.get_order_by  ->  []
          WhereNode.split_having_qualify  ->  ((AND: ), None, None)
          -> (extra_select of 0, order_by of 0, group_by of 0)
        -> ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor"', ())
      -> ('SELECT * FROM ( SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" ) "qualify" WHERE "n" = %s', (1,))
```

The block's first line makes numbered: every sailor, numbered within its ship's crew by name, under the annotation `"n"`. The filter asks for the first of each crew.

### The split

`SQLCompiler.pre_sql_setup` has `WhereNode.split_having_qualify` divide the query's where tree into its where part, its having part and its qualify part, the last being what refers to a window, and keeps the three on the compiler (`django/db/models/sql/compiler.py:SQLCompiler.pre_sql_setup`, `django/db/models/sql/where.py:WhereNode.split_having_qualify`); how the tree is walked, and which nodes must stay whole, is told in [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md). The recording's line for `split_having_qualify` shows the result for `filter(n=1)`: nothing for the `"WHERE"`, nothing for the `"HAVING"`, and the lookup on the window as the qualify part.

Where a node's children must stay together, as those of an `"OR"` that is not negated must, and a window is among them, the whole node goes to the qualify part, unless the node has plain children beside the window and the query groups, which the caller passes in as `must_group_by=True`: then the method raises `NotImplementedError`, with the message the documentation quotes (`docs/ref/models/expressions.txt`). The comment beside the test says that such a disjunction can be pushed down to the qualify part as long as no conditional aggregation is involved, and admits the test is wider than it has to be: in theory only a plain condition on a multi-valued relation could change what the groups contain, but that is hard to tell.

```text recording=sql
sql_of(numbered.filter(Q(n=1) | Q(name='Dag')))[0][120:]  ->  '"crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" ) "qualify" WHERE ("n" = %s OR "col2" = %s)'
sql_of(numbered.filter(n=1, name__startswith='A'))[0][120:]  ->  '"crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE %s ESCAPE \'\\\' ) "qualify" WHERE "n" = %s'
```

The statement with the `"OR"` is of a window and a plain condition on a query that does not group: the node went whole to the qualify part, and the condition on the name is tested outside, against the column's alias in the inner statement. The one with `"name__startswith"` is an `"AND"`: divided, the condition on the name stands in the inner statement's `"WHERE"`, and only the window's in the outer one. The `"LIKE ... ESCAPE"` is SQLite's way of writing `"startswith"` ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../expressions/lookups.md)).

```text recording=sql
numbered.annotate(hands=Count('id')).filter(Q(n=1) | Q(hands__gt=1))  ->  <SailorQuerySet [<Sailor: Ada>, <Sailor: Cora>]>
  SQL SELECT * FROM ( SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n", COUNT("crew_sailor"."id") AS "hands" FROM "crew_sailor" GROUP BY 1, 2, 3, 4 ) "qualify" WHERE ("n" = %s OR "hands" > %s) LIMIT 21 with params (1, 1)
...
sql_of(numbered.annotate(hands=Count('id')).filter(Q(n=1) | Q(name='Dag')))  ->  raises NotImplementedError: Heterogeneous disjunctive predicates against window functions are not implemented when performing conditional aggregation.
```

An `"OR"` of a window and an aggregate on a query that groups is allowed, since no plain condition is among the children: the node went to the qualify part whole, aggregate and all, and the inner statement groups while the outer one tests both. A plain condition under an `"OR"` with the window, on the same grouped query, is the `NotImplementedError`.

### `get_qualify_sql`

With a qualify part set, `SQLCompiler.as_sql` takes the statement from `SQLCompiler.get_qualify_sql` and sets its own ordering aside, since the method has written one (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.get_qualify_sql`).

The whole method turns on one constraint: the outer statement can name only what the inner one selects, and only by alias. So the inner query is given an alias for every column, each expression the condition refers to is replaced by the alias of the column that holds it, and an expression the inner query does not select is added to it under an alias of its own for the test and masked out again afterwards.

`get_qualify_sql` begins with the inner query: a clone of the query, marked as a subquery, whose where tree is a new node holding the where part and the having part, so that the condition on the window is the one thing left out. It calls `SQLCompiler.get_select` with `with_col_aliases=True`, which gives every selected column an alias, `"col1"`, `"col2"` and on, where the column has none of its own, and an annotation its own name ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)), and makes a dictionary from each selected expression to its alias.

The function it defines next, over a list of expressions, works out the replacements. An expression that is selected is replaced by its alias. Otherwise a lookup is opened, its sources going on the list; a `Ref` to a selected alias is left as it is, and a `Ref` to anything else is opened like a lookup. Anything else is added to the inner query as an annotation under `"qual0"`, `"qual1"` and on, with `Query.add_annotation`, and replaced by that alias (`django/db/models/sql/query.py:Query.add_annotation`); the comment at the top of the method says when this happens, a window that `values` or `alias` has masked out of the selection being filtered on. The function is run over the leaves of the qualify tree, which `WhereNode.leaves` yields, and the tree is rewritten with `WhereNode.replace_expressions`, each expression that has a replacement becoming a `Ref` to its alias (`django/db/models/sql/where.py:WhereNode.leaves`, `django/db/models/sql/where.py:WhereNode.replace_expressions`). A `Ref` writes its alias, quoted, and nothing more, which is why the outer `"WHERE"` reads `"n" = %s` and `"col2" = %s` ([Expressions: `resolve_expression` and `as_sql`](../expressions/protocol.md)).

The ordering is treated the same way. For each expression `SQLCompiler.get_order_by` returns, the function runs over its sources, and a copy of the expression with the replacements is kept to be written outside. The inner query then gets a compiler of its own, made with the same connection and the outer compiler's `elide_empty`, and its `as_sql` is called with `with_limits=False` and `with_col_aliases=True`; the comments give both reasons: the limits must be applied to the outer query, or rows would be pruned before the condition is tested, and every column needs an alias of its own so that the outer statement can refer to it. The result is a list of pieces, `"SELECT * FROM ("`, the inner statement, `")"`, the quoted name `"qualify"`, `"WHERE"` and the compiled qualify part. Where any `"qual"` alias was added, the whole is wrapped once more, in a `"SELECT"` of the aliases the outer compiler's own selection had, from the pieces as a subquery named `"qualify_mask"`: the comment says that aliases unmasked for filtering must be masked back.

```text recording=sql
list(numbered.filter(n=1).values_list('name', flat=True))  ->  ['Ada', 'Cora']
  SQL SELECT "name" FROM ( SELECT * FROM ( SELECT "crew_sailor"."name" AS "name", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "qual0" FROM "crew_sailor" ) "qualify" WHERE "qual0" = %s ) "qualify_mask" with params (1,)
```

Here `values_list("name")` had masked the window out of the selection, `"qual0"` was added to the inner statement, and the outermost `"SELECT"` names `"name"` alone. Last, where there was an ordering, `"ORDER BY"` and the rewritten expressions are appended; the comment says why it is repeated outside when the inner statement already has it: the SQL specification does not say whether a derived table's ordering carries through, so it is repeated on the outermost query to make sure.

```text recording=sql
sql_of(numbered.filter(n=1).order_by('-name'))[0][120:]  ->  '"crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" ORDER BY "crew_sailor"."name" DESC ) "qualify" WHERE "n" = %s ORDER BY "col2" DESC'
```

Back in `as_sql`, the limit and the offset are appended as for any other statement, which [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md) tells; the `LIMIT 21` of the statement above that filters on `Q(n=1) | Q(hands__gt=1)` is what a queryset's repr asks for, and stands after the outer `"WHERE"` (`django/db/models/query.py:QuerySet.__repr__`).

```text figure=the-qualify-rewrite
a condition on a window, which SQL will not take in a WHERE:

    SELECT ..., ROW_NUMBER() OVER (PARTITION BY ship_id ORDER BY name) AS n
    FROM crew_sailor
    WHERE n = 1

what get_qualify_sql writes, two statements where one was wanted:

    SELECT * FROM (                                                 <- the outer statement
        SELECT id AS col1, name AS col2, ship_id AS col3, ...,      <- the inner query: a clone, with the WHERE and HAVING parts
               ROW_NUMBER() OVER (...) AS n                            and no limit, written by its compiler's
        FROM crew_sailor                                               as_sql(with_col_aliases=True)
        ORDER BY name DESC
    ) "qualify"
    WHERE "n" = 1                                                   <- the qualify part, each expression a Ref to an alias
    ORDER BY "col2" DESC  LIMIT 21                                  <- the ordering repeated outside; the limit, from as_sql

and a third, where values() had masked the window out of the selection:

    SELECT "name" FROM (                                            <- a third statement round the two
        SELECT * FROM (
            SELECT ..., ROW_NUMBER() OVER (...) AS "qual0" FROM crew_sailor
        ) "qualify"                                                 <- the window the selection had masked,
        WHERE "qual0" = 1                                              selected under "qual0" for the test
    ) "qualify_mask"                                                <- the selection masked again
```

*The rewrite of a filter on a window. The statement the filter asks for, which no `"WHERE"` can hold, becomes an inner statement without the condition and an outer one that reads its rows by their aliases and tests the condition there; a window the selection had masked is selected under a `"qual"` alias for the test and masked again by a third statement round the two.*

A compound query never reaches this branch: `as_sql` looks for a combinator first, and a combined queryset refuses a filter ([Compound statements: `get_combinator_sql`](compound.md)).

## A window in an aggregation, and from an outer query

`Query.get_aggregation` does not take the plain way, making the aggregates the query's only annotations, where a window is involved. It looks for an aggregate that refers to an annotation with `contains_over_clause` set, and for a qualify part in the where tree, and for either sends the query inside an `AggregateQuery`, the window selected in the inner statement and the aggregate reading its alias outside (`django/db/models/sql/query.py:Query.get_aggregation`). [Aggregating a query: `Query.get_aggregation`](aggregation.md) has the method; the statement it makes here is this:

```text recording=sql
numbered.aggregate(m=Max('n'))  ->  {'m': 2}
  SQL SELECT MAX("n") FROM (SELECT ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor") subquery
```

A subquery may not reach an outer query's window either. `OuterRef` resolves to a `ResolvedOuterRef`, and when that in turn is resolved against the outer query, `ResolvedOuterRef.resolve_expression` raises `NotSupportedError` where what it found has `contains_over_clause` set, naming the reference (`django/db/models/expressions.py:ResolvedOuterRef.resolve_expression`). The two classes, and how a query stands inside another, are [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](../query/subqueries.md).
