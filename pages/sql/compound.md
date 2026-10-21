---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Compound statements: `get_combinator_sql`

`SQLCompiler.get_combinator_sql` writes a combined query as a compound statement: it keeps the parts whole, compiles each with a compiler of its own, and joins the statements with the backend's word for a union, an intersection or a difference, `"UNION"`, `"INTERSECT"` and `"EXCEPT"` in the base class.

Two queries of one model can become one statement in two ways. A **merge** writes one `"SELECT"` whose where clause holds the conditions of both ([Merging two queries: `Query.combine`](../query/combine.md)). A **compound statement** writes a `"SELECT"` for each query and puts a set operator between them. The parts stay apart, and what has to be settled is what applies to the whole: the one list of columns every part must select, the ordering and the limit, which stand after the last part and may name no column the parts did not select, and what the backend allows inside a part, which differs from one database to the next.

The queryset's half is told in [Combining querysets: the operators and `union`](../querysets/combining.md): `QuerySet.__and__`, `QuerySet.__or__` and `QuerySet.__xor__` make the checks a merge needs, clone the left side and call `Query.combine` on its query with the right side's; `QuerySet.union`, `QuerySet.intersection` and `QuerySet.difference` make a **combined queryset**, whose query names its **combinator** and holds the queries to be joined as its **parts**.

The recordings below were made from a running Django, on SQLite, over the fleet and crew of [Models and fields](../models.md): a line at the left is Python as it was run, with its value, where it is shown, or the exception it raised after `->`, and under it, nested as they were made, the calls it set going that the passage is about, with `->` what each returned. A line of three dots stands for lines of the block left out.

## The combinators: `combinator`, `combinator_all` and `combined_queries`

`Query` has three class attributes for a compound: `Query.combinator`, `None` or `"union"`, `"intersection"` or `"difference"`; `Query.combinator_all`, false unless a union was asked to keep duplicates; and `Query.combined_queries`, the tuple of the parts, empty for any other query (`django/db/models/sql/query.py:Query`). `QuerySet._combinator_query` sets the three on a clone of the left side, after clearing the clone's ordering and limits and switching its default ordering on; the first part is the left side's own query and the others are clones of the right sides' ([Combining querysets: the operators and `union`](../querysets/combining.md)). The combined query's own where tree and joins are the left side's, and the compiler writes neither: `SQLCompiler.as_sql` turns off to `get_combinator_sql` before the from clause and the where tree are compiled.

Several methods of `Query` reach into the parts. `Query.clone` clones each part (`django/db/models/sql/query.py:Query.clone`). `Query.clear_ordering` clears each part's ordering without force, passing on its own `clear_default=True` or `clear_default=False`; the comment says that the ordering of the parts is cleared with `clear_default=False` when `union` and its analogues are called, so that a later `clear_default=True` has to percolate (`django/db/models/sql/query.py:Query.clear_ordering`). `Query.set_empty` adds a `NothingNode` to each part's where tree as well as to the query's own (`django/db/models/sql/query.py:Query.set_empty`). `Query.resolve_expression` resolves each part against the outer query and `Query.change_aliases` renames in each part the external aliases its change touches, both for a compound that stands inside another query; and `Query.exists` makes each part of a union an `exists` of its own.

## `get_combinator_sql`: the parts compiled and joined

Where the query has a combinator, `SQLCompiler.as_sql` asks the backend's features whether it supports the operation, `supports_select_union` and its two fellows, which the base class has true, and raises `NotSupportedError` otherwise; then it calls `SQLCompiler.get_combinator_sql` with the combinator and `combinator_all` (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/backends/base/features.py:BaseDatabaseFeatures.supports_select_union`). Before that it has run `pre_sql_setup` with column aliases on, so that the combined query's own select list carries `"col1"`, `"col2"` and so on, by which the ordering can name a column ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)).

`get_combinator_sql` makes a compiler for each part, with the connection and the `elide_empty` of the compiler itself (`django/db/models/sql/compiler.py:SQLCompiler.get_combinator_sql`). Where the backend lacks `supports_slicing_ordering_in_compound` it then looks at every part before writing any: a part whose query is sliced is refused with `DatabaseError`, and so is a part for which the part's own `get_order_by` returns anything. The base class has the feature false; the backends for PostgreSQL, MySQL and Oracle set it true, and SQLite's leaves it (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_slicing_ordering_in_compound`). Since a part's `get_order_by` reads the `ordering` of the model's `Meta` wherever the part has its default ordering on, a union of two querysets of ships, whose `Meta` orders by name, is refused on SQLite unless `order_by()` with no names was called on each queryset before combining, which [Combining querysets: the operators and `union`](../querysets/combining.md) shows.

Each part then goes through `_get_combinator_part_sql`, and a part that raises `EmptyResultSet` is left out of a union, and out of a difference once a part is already there; otherwise the exception goes on up, so that an empty part of an intersection, or an empty first part of a difference, empties the whole. No part left means `EmptyResultSet` too. One part left, in a union, where the whole is sliced, is the case the comment explains: a sliced union of a single component could end with two `"LIMIT"` clauses where the component is sliced too, as a backend with `supports_slicing_ordering_in_compound` allows, so the empty part is put back, compiled with its `elide_empty` turned off so that it writes a predicate that is always false instead of raising. The operator is the backend's: `BaseDatabaseOperations.set_operators` maps the three names to `"UNION"`, `"INTERSECT"` and `"EXCEPT"`, Oracle's operations class writes a difference as `"MINUS"`, and a union with `combinator_all` gets `" ALL"` (`django/db/backends/base/operations.py:BaseDatabaseOperations.set_operators`, `django/db/backends/oracle/operations.py:DatabaseOperations.set_operators`). The parts are joined with the operator between them, and their parameters follow in the same order.

`_get_combinator_part_sql` does two things to a part (`django/db/models/sql/compiler.py:SQLCompiler._get_combinator_part_sql`). Where the whole has `Query.selected`, which `values` or `values_list` on the combined queryset sets, and the part has none, the part's query is cloned and given the whole's selection through `Query.set_values`; the comment's rule is that if the columns list is limited, all combined queries must have the same columns list (`django/db/models/sql/query.py:Query.set_values`). Then the part's compiler writes its statement with `with_col_aliases=True`, so that every column has an alias, the name `values` gave it or `"col1"` and on. On a backend with `supports_slicing_ordering_in_compound` every part stands in parentheses, which `get_combinator_sql` puts round each part where the whole is not a subquery and `_get_combinator_part_sql` round each where it is. Without the feature a plain part is bare, and a part that is itself a compound is put in parentheses, or wrapped as `SELECT * FROM (...)` where the backend cannot take a parenthesised compound either, which SQLite's features class says of itself with `supports_parentheses_in_compound` (`django/db/backends/sqlite3/features.py:DatabaseFeatures.supports_parentheses_in_compound`).

In what follows old is the sailors who signed on before 2020, on_petrel the Petrel's crew and dag the sailors named Dag, and sql_of is the statement and parameters the queryset's compiler returns, unsent.

```text recording=sql
sql_of(old.union(on_petrel))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
sql_of(old.union(on_petrel, all=True))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION ALL SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
...
sql_of(old.difference(on_petrel))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s EXCEPT SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
```

A nested compound, and the same three parts given to one `union`:

```text recording=sql
sql_of(old.union(on_petrel).union(dag))  ->  ('SELECT * FROM (SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s) UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s', ('2020-01-01 00:00:00', 1, 'Dag'))
sql_of(old.union(on_petrel, dag))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s', ('2020-01-01 00:00:00', 1, 'Dag'))
```

In the first the left side was itself a union, and so the first part was a compound: on SQLite it was wrapped as a subquery. In the second all three are parts of one query. An empty part, and the sliced union of one part:

```text recording=sql
sql_of(old.union(Sailor.objects.none()))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
...
sql_of(old.difference(Sailor.objects.none()))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
sql_of(old.union(on_petrel.filter(pk__in=[]))[:1])  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE 0 = 1 LIMIT 1', ('2020-01-01 00:00:00',))
```

An empty queryset as the second part of a union, and as the second part of a difference, was left out, and the statement is the one part, still with its column aliases. In the last line the second part matches nothing, by a comparison with an empty list, and the whole is sliced: the empty part was put back and written with `WHERE 0 = 1`, so that the `"LIMIT"` stands after a union and not after the one part. What SQLite refuses inside a part, and the features that decide it:

```text recording=sql
old.order_by('name').union(on_petrel)  ->  raises DatabaseError: ORDER BY not allowed in subqueries of compound statements.
old[:1].union(on_petrel)  ->  raises DatabaseError: LIMIT/OFFSET not allowed in subqueries of compound statements.
connection.ops.set_operators, connection.features.supports_select_union, connection.features.supports_select_intersection, connection.features.supports_select_difference, connection.features.supports_slicing_ordering_in_compound, connection.features.supports_parentheses_in_compound, connection.features.requires_compound_order_by_subquery  ->  ({'union': 'UNION', 'intersection': 'INTERSECT', 'difference': 'EXCEPT'}, True, True, True, False, False, False)
```

## The ordering of a compound statement

The ordering of a compound statement is the combined query's own, and it stands after the last part; what it may name is a column the parts select. `SQLCompiler.get_order_by` refers to a selected column by its alias, `"col2"`, or by its position where `values` named it, and where no selected column matches it adds one, `"__orderbycol"` and a number, as an annotation to every part and to the whole's selection, unless a part's selection was fixed by `values`, which is the `DatabaseError` recorded here; on a backend with `requires_compound_order_by_subquery`, Oracle's, `as_sql` wraps the compound as `SELECT * FROM (...)` and puts the ordering outside (`django/db/models/sql/compiler.py:SQLCompiler.get_order_by`). [ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md) has `_order_by_pairs` and `get_order_by` in full.

```text recording=sql
sql_of(old.union(on_petrel).order_by('name'))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "col2" ASC', ('2020-01-01 00:00:00', 1))
sql_of(old.union(on_petrel).order_by('-signed_on', 'name'))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "col4" DESC, "col2" ASC', ('2020-01-01 00:00:00', 1))
sql_of(old.values('name').union(on_petrel.values('name')).order_by('name'))  ->  ('SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY 1 ASC', ('2020-01-01 00:00:00', 1))
old.values('name').union(on_petrel.values('name')).order_by('id')  ->  raises DatabaseError: ORDER BY term does not match any column in the result set.
```

The first two orderings found their columns among the aliased selection and refer to them as `"col2"` and `"col4"`; the third names a column that `values` selected and is written by position; and the fourth asks for a column the parts, each fixed by `values`, do not select. Here is the call order where a column has to be added to the parts, with the union given `values("name")` and ordered by the moment of signing on:

```text recording=sql
old.union(on_petrel).values('name').order_by('signed_on').query.get_compiler('default').as_sql()
  Query.set_values(('name',))
  SQLCompiler.as_sql
    SQLCompiler.pre_sql_setup
      SQLCompiler.get_order_by
        Query.add_annotation(annotation=F(signed_on), alias='__orderbycol2')
        Query.add_annotation(annotation=F(signed_on), alias='__orderbycol2')
        Query.add_select_col(col=OrderBy(Col(crew_sailor, crew.Sailor.signed_on), descending=False), name='__orderbycol2')
        -> ['"__orderbycol2" ASC']
      -> (extra_select of 0, order_by of 1, group_by of 0)
    SQLCompiler.get_combinator_sql(combinator='union', all=False)
      SQLCompiler.get_order_by  ->  []
      SQLCompiler.get_order_by  ->  []
      SQLCompiler._get_combinator_part_sql(compiler for a Query of Sailor)
        Query.set_values({'name': 0, '__orderbycol2': 1})
        SQLCompiler.as_sql(with_col_aliases=True)
          -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
        -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
      SQLCompiler._get_combinator_part_sql(compiler for a Query of Sailor)
        Query.set_values({'name': 0, '__orderbycol2': 1})
        SQLCompiler.as_sql(with_col_aliases=True)
          -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', (1,))
        -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', (1,))
      -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
    -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "__orderbycol2" ASC', ('2020-01-01 00:00:00', 1))
```

`Query.set_values` was `values` on the combined queryset, setting the whole's selection to the one name. In `pre_sql_setup`, `get_order_by` found no selected column for the moment, added `"__orderbycol2"` as an annotation to each part and as a selected column of the whole, and wrote the ordering as a reference to it. `get_combinator_sql` then asked each part's compiler for its own ordering, the check for SQLite, and got none; gave each part the whole's selection, by now the name and the added column; and had each written with column aliases. `as_sql` put the ordering after the joined parts.

> **Changed in 6.1.** `QuerySet._combinator_query` switches the default ordering on for the combined query, so that the `ordering` of the model's `Meta` orders the whole statement where nothing else does. The release notes give what follows from it: `union`, `intersection` and `difference` raise `DatabaseError` when a field of the model's ordering is not among the columns that `values` or `values_list` selected, and calling `order_by` with no arguments after combining clears the default ordering (`docs/releases/6.1.txt`).

## A compound query inside another

A combined query stands inside another as any query does, with its parts resolved alongside it: `Query.resolve_expression` makes a clone with its alias prefix bumped and marked as a subquery, and resolves each part the same way, so that each part's aliases are moved to the new prefix too; `Query.as_sql` clears the ordering of the query and of each part where the backend does not ignore an unnecessary `"ORDER BY"` in a subquery, and puts the whole in parentheses (`django/db/models/sql/query.py:Query.resolve_expression`, `django/db/models/sql/query.py:Query.as_sql`). Inside, the parts are written bare on SQLite, which lacks `supports_slicing_ordering_in_compound`. [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](../query/subqueries.md) has the resolving in full. A union as the value of an `"in"`:

```text recording=sql
sql_of(Sailor.objects.filter(pk__in=old.union(on_petrel).values('pk')))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" AS "pk" FROM "crew_sailor" "U0" WHERE "U0"."signed_on" < %s UNION SELECT "U0"."id" AS "pk" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = %s)', ('2020-01-01 00:00:00', 1))
```

Each part's table is `"U0"`, the prefix the resolving gave it; and the `"in"` lookup, built once the value was resolved, cleared the clone's ordering through `Query.clear_ordering`, which reached its parts (`django/db/models/lookups.py:In.get_prep_lookup`).

## `exists` and `count` on a union

`Query.exists` on a union makes each part the part's own `exists(limit=False)`, so that every part selects the constant under the alias `"a"` and none is limited, and limits the whole to one row; `Query.get_aggregation`, for a count, wraps a query that has a combinator in a subquery and counts its rows (`django/db/models/sql/query.py:Query.exists`, `django/db/models/sql/query.py:Query.get_aggregation`). [Aggregating a query: `Query.get_aggregation`](aggregation.md) has both.

```text recording=sql
str(old.union(on_petrel).query.exists())  ->  'SELECT 1 AS "a" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < 2020-01-01 00:00:00 UNION SELECT 1 AS "a" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = 1 LIMIT 1'
```
