---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: registry, protocol, lookups, functions, related-lookups, aggregates, windows, where-node
---

# Expressions, lookups and functions

The objects of a query that write their own SQL: an expression is bound to a query by `resolve_expression` and written by `as_sql`; a lookup is a comparison, found by its name in a registry, prepared when the filter is built and written when the query is compiled; a function fills a template; and the where tree joins them, counting the children that match nothing or everything.

What a query holds is not SQL. It is a set of Python objects that each know how to write their own piece: a `Col` for a column, a `Value` for a parameter, a `Func` for a function call, a `Lookup` for a comparison, a `WhereNode` for the conditions joined by `"AND"`, `"OR"` or `"XOR"`. They have to be written in the dialect of whichever database the query is sent to, which the query itself does not hold, and some of them name columns of tables the query has not yet joined. So each object is dealt with twice. When it is added to a query it is bound to that query, its names made columns of tables the query has joined; when the statement is written it writes its SQL for the connection at hand. And some of them can tell, without asking the database, that they will match no row or every row, and say so in place of their SQL.

The examples are harbour's, whose models [Models and fields](models.md) lists, and the filter of [Building a query](query.md), for the sailors whose ship's home port is Bergen and who signed on before 2020, whose where tree is an `"AND"` of two lookups, an `Exact` on the name of the sailor's ship's home port and a `YearLt` on the year the sailor signed on. The recording was made from a running Django, on SQLite. A line at the left is a call; the lines set in under it are the calls it made, nested as they were made, with only those the passage is about written down; `->` is what a call returned, a piece of SQL and its parameters; a name in parentheses after a call is the class whose method the line records, where that is not the object's own class; and a line of three dots stands for lines left out.

## Two methods, two moments

An **expression**, in this chapter, is any object with two methods. `BaseExpression.resolve_expression` binds it to a query: a name becomes a column of a table the query has joined, and whatever the object holds is bound in turn, so that a resolved object is a copy and the original is left as it was (`django/db/models/expressions.py:BaseExpression.resolve_expression`). `as_sql` writes the SQL and the parameters of a bound object, compiling its parts first, and is left to the subclasses: `BaseExpression.as_sql` only raises `NotImplementedError`. A class may also supply an `as_sqlite`, an `as_postgresql` or the like, and `SQLCompiler.compile` prefers the one for its connection's vendor (`django/db/models/expressions.py:BaseExpression.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.compile`). A query is one itself: `Query` is built on `BaseExpression`, and inside another query it is a subquery.

So an expression can be built without a query and used on several. `F("tonnage") + 1` is a `CombinedExpression` of an `F` and a `Value`; resolving it against a query of ships turns the `F` into a `Col` of the ships' table through `Query.resolve_ref`, and the type of the sum, when it is wanted, is asked of the pair of field types (`django/db/models/sql/query.py:Query.resolve_ref`). Two `Expression` objects built the same way are equal and hash alike, which is what lets the compiler notice that an ordering refers to a selected column ([Expressions: `resolve_expression` and `as_sql`](expressions/protocol.md)).

## A lookup: prepared when built, written when compiled

A **lookup** is the comparison at the end of a filter's name: `Exact`, `In`, `IContains`, `YearLt`. It is found by its name in a **registry**: a field class, and a transform class, carries a dictionary from words to lookup and transform classes, merged down its classes' bases, to which a project may add its own (`django/db/models/query_utils.py:RegisterLookupMixin.get_lookup`) ([The lookup registry: `RegisterLookupMixin`](expressions/registry.md)). A lookup holds a left side, here the column or the transformed column, and a right side, here the value, and it does its work in two moments. When the filter is built `Exact` prepares the value through the field of its left side, so that `'Bergen'` has passed through the port's name field before any SQL exists (`django/db/models/lookups.py:Lookup.get_prep_lookup`). When the statement is written it writes its two halves, the left by compiling it and the right as a placeholder with its parameter, and joins them with the operator the connection's table gives for its name (`django/db/models/lookups.py:BuiltinLookup.as_sql`). The where tree of the filter, compiled:

```text recording=sql
...
SQLCompiler.compile((AND: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020)))
  WhereNode.as_sql
    SQLCompiler.compile(Exact(Col(fleet_port, fleet.Port.name), 'Bergen'))
      Exact.as_sql  (BuiltinLookup.as_sql)
        Exact.process_lhs  (BuiltinLookup.process_lhs)
          ...
          -> ('"fleet_port"."name"', ())
        ...
        -> ('"fleet_port"."name" = %s', ('Bergen',))
...
    SQLCompiler.compile(YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020))
      YearLt.as_sql  (YearLookup.as_sql)
        YearLt.process_lhs(lhs=Col(crew_sailor, crew.Sailor.signed_on))  (BuiltinLookup.process_lhs)
          ...
          -> ('"crew_sailor"."signed_on"', ())
        ...
        -> ('"crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
...
    -> ('("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s)', ['Bergen', '2020-01-01 00:00:00'])
    ...
```

Each node wrote its own piece: the where tree compiled each lookup and joined what came back with its connector, and each lookup compiled its left side. The year comparison is the one surprise. `YearLt` held `ExtractYear` of the column as its left side, and wrote the column itself, compared with the first day of the year, not the year extracted from it, so that an index on the column can serve (`django/db/models/lookups.py:YearLookup.as_sql`). [Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](expressions/lookups.md) has the two halves and the standard lookups registered on every field, and [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](expressions/related-lookups.md) the comparisons of a relation, where an instance becomes its key and a key may be several columns.

## A function fills a template

A **transform**, `ExtractYear` here, is a function of one argument that has a registry of its own, so that a word after it can name a lookup or another transform. It is a `Func`, as are the database functions of `django.db.models.functions`: a `Func` writes its SQL by compiling its arguments and putting them into a template, `"%(function)s(%(expressions)s)"` unless the class says otherwise, with the function's name; a vendor's method most often calls the same `as_sql` with another template or another name (`django/db/models/expressions.py:Func.as_sql`) ([Transforms and database functions: `Transform` and `Func`](expressions/functions.md)). Two kinds of function change the shape of the statement around them. An `Aggregate` folds the rows of a group into one value, and is marked as one, so that the query groups for it and a filter on it goes to `"HAVING"` ([Aggregates: `Aggregate` and `Count`](expressions/aggregates.md)). A `Window` reports a function of a partition of the rows on every row, written as `function OVER (...)`, and is marked so that a filter on it is kept out of the `"WHERE"` ([Window expressions: `Window` and `WindowFrame`](expressions/windows.md)).

## Deciding instead of writing

A leaf of the where tree may know, without asking the database, that it will match no row or every row. It may then raise instead of writing: `EmptyResultSet` where it can match nothing, as `In` does for an empty list, and `FullResultSet` where it matches everything (`django/db/models/lookups.py:In.process_rhs`). `WhereNode.as_sql` counts these as it compiles its children. Under `"AND"`, one empty child makes the node empty, and every child must be full for the node to be full; under `"OR"`, one full child makes the node full, and every child must be empty for it to be empty. When either count is reached the node raises the same exception for itself, the other way round if it is negated, so the news travels up the tree node by node (`django/db/models/sql/where.py:WhereNode.as_sql`). At the top the compiler acts on it: a full tree writes no `"WHERE"`, and a query run on its own whose tree is empty is ordinarily answered with no rows and without a statement being sent (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.execute_sql`) ([What the where tree writes: `WhereNode`](expressions/where-node.md)).

The figure draws both walks over the filter's tree, and below it a tree with an empty leaf, whose signal goes up in place of SQL.

```text figure=down-and-up
the where tree of filter(ship__home__name='Bergen', signed_on__year__lt=2020)

                    bound as the filter is built: down                  written as the statement is compiled: up
AND, a WhereNode                                                        ("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s)
  Exact             the name becomes Col(fleet_port, name);             "fleet_port"."name" = %s             'Bergen'
                    'Bergen' is prepared through Port.name
  YearLt            the name becomes Col(crew_sailor, signed_on),       "crew_sailor"."signed_on" < %s       '2020-01-01 00:00:00'
                    wrapped in the transform ExtractYear                the column itself, against the year's first day

a tree with a leaf that decides
the compiler        given an empty tree, ordinarily sends no statement: the queryset has no rows
AND, a WhereNode    one empty child makes the node empty: it raises EmptyResultSet in turn
  In, given []      can match nothing: raises EmptyResultSet in place of its SQL
  any other child   its SQL is not used
```

*Each lookup of the filter's tree is dealt with twice: bound to the query on the way down, as the filter is built, and written for the connection on the way up, as the statement is compiled. A leaf that can match nothing may raise instead of writing, and the nodes above it count the signal up to the compiler.*

## The neighbours

The query that resolves these objects, and the walk through the models that gives a lookup its left side, are [Building a query](query.md)'s; the compiler that writes them, clause by clause, is [The SQL compiler](sql.md)'s. Most of the standard lookups take their operator from the connection's backend ([Database backends](backends.md)). A field's own preparation of a value is [Models and fields](models.md)'s. The lookups and transforms of a JSON field are built on the classes here (`django/db/models/fields/json.py:KeyTransform`), as are those of `django.contrib.postgres` and of a geometry ([Content types, static files and the other contrib apps](contrib.md)).
