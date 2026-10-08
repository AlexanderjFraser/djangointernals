---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Two queries into one: `combine` and `get_combinator_sql`

`Query.combine` merges a second query into a first: it brings the second query's joins into the first's alias map and adds its where tree under a connector, and it is what `&`, `|` and `^` between two querysets come to. `SQLCompiler.get_combinator_sql` does the other thing SQL can do with two queries: it keeps the parts of a combined query whole, compiles each with a compiler of its own, and joins the statements with `"UNION"`, `"INTERSECT"` or `"EXCEPT"`.

Two queries of one model can become one statement in two ways, and each way has its own difficulties. A **merge** writes one `"SELECT"` whose where clause holds the conditions of both. For that the second query's tables have to be brought into the first's alias map without their aliases colliding; for each of its joins it has to be decided whether a join the first query already has may serve, since under `"AND"` a join shared by two conditions on a many-valued relation asks one related row to meet both; the types of the joins have to be settled again, by the votes of both sides; and the second query's conditions have to be relabelled to whatever aliases its joins were given. A **compound statement** writes a `"SELECT"` for each query and puts a set operator between them. The parts stay apart, and what has to be settled is what applies to the whole: the one list of columns every part must select, the ordering and the limit, which stand after the last part and may name no column the parts did not select, and what the backend allows inside a part, which differs from one database to the next.

The queryset's half is told in [Combining querysets: the operators and `union`](../querysets/combining.md): `QuerySet.__and__`, `QuerySet.__or__` and `QuerySet.__xor__` make the checks a merge needs, clone the left side and call `Query.combine` on its query with the right side's; `QuerySet.union`, `QuerySet.intersection` and `QuerySet.difference` make a **combined queryset**, whose query names its **combinator** and holds the queries to be joined as its **parts**. This page begins where those calls end.

The recordings below were made from a running Django, on SQLite, over the fleet and crew of the chapter's opening page ([From QuerySet to SQL](../sql.md)). A line at the left is Python as it was run, with its value after `->` where it is an expression, or the exception it raised; under it, nested as they were made, are the calls it set going that the passage is about, with `->` what each returned; a line `alias_map[...]` is one entry of the query's alias map, with its reference count; and a line that begins `SQL` is a statement as Django handed it to its cursor.

## Merging: `Query.combine`

`Query.combine` is called on the left side's query, which the queryset has cloned, with the right side's query and a connector, `"AND"`, `"OR"` or `"XOR"`; its docstring promises that the right side is not modified (`django/db/models/sql/query.py:Query.combine`). It begins by refusing four pairs of queries, each with `TypeError`, in this order: queries of two different model classes; a left side that is sliced; one query with `Query.distinct` and the other without; two queries with different `Query.distinct_fields`. Three of the four, recorded:

```text recording=sql
Ship.objects.all().query.combine(Sailor.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine queries on two different base models.
Ship.objects.all()[:1].query.combine(Ship.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine queries once a slice has been taken.
Ship.objects.distinct().query.combine(Ship.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine a unique query with a non-unique query.
```

### The right side's aliases

Both queries name their tables by one scheme, the table's own name the first time it appears and `"T"` with a number after that ([Tables and joins: the alias map and join promotion](joins.md)), so the right side's `"T4"` may be another table than the left side's, and renaming an alias as the joins come in could chain into renaming another, `"T4"` to `"T5"` and `"T5"` to `"T6"`. The comment at this point of `combine` gives that as the reason for what it does first: it clones the right side and has the clone move every alias but the base table's to a prefix the left side does not use, through `Query.bump_prefix`, so that no alias of the two queries can coincide (`django/db/models/sql/query.py:Query.bump_prefix`). The base table is left out because, as the comment says, it has to be present in the query on both sides. The recording shows the clone's where tree relabelled to `"U1"` and `"U2"`.

### Which joins may be reused

Under `"AND"` no alias of the left side may serve a join of the right side, and every join is made again; under `"OR"` and `"XOR"` any may. The comment gives the reason: a filter such as `revrel__col=1 & revrel__col=2` cannot be met by one related row, but two related rows might meet it, one each, so the two conditions need two joins; under `"OR"` a single true suffices, so a single row does. It admits what the rule costs too: for joins that are not many-to-many the `"AND"` case makes duplicate joins, correct but too many, and calls that something that could be fixed later on.

The joins are then brought in one by one, with a `JoinPromoter` watching. The promoter is made for two children under the connector, and the aliases of the left side's inner joins are voted in first (`django/db/models/sql/query.py:JoinPromoter.add_votes`). Then, for each entry of the right side's alias map after the first, which is its base table: the join is relabelled with the renamings made so far, so that a join whose parent was renamed hangs from the new name (`django/db/models/sql/datastructures.py:Join.relabeled_clone`); it is handed to `Query.join` with the set of aliases that may be reused, and `join` returns an alias, an existing one where a join equal to this one is among those, a new one otherwise, and a new join gets its type there, outer where it is nullable or its parent is outer and inner otherwise (`django/db/models/sql/query.py:Query.join`). Only then is the join's type read, and where it is inner the new alias is a vote for the right side. The alias is taken out of the reuse set, since, the comment says, two distinct joins of one relation in the right side must stay two joins in the result; the renaming is recorded where the alias changed; and where the right side held the alias but no longer referred to it, the new alias is unreferenced once, so that it is unused in the merged query as well, the join having been added at all so that join promotion knows its type. The right side's votes go in last, and `JoinPromoter.update_join_types` settles every voted join: under `"AND"` each is demoted to inner; under `"OR"` a join voted for by fewer than both sides is promoted to outer and one voted for by both is demoted (`django/db/models/sql/query.py:JoinPromoter.update_join_types`). [Tables and joins: the alias map and join promotion](joins.md) has the promoter in full.

In the recording to_leith and to_lisbon are the voyages that called at Leith and at Lisbon, each a `filter(calls__name=...)` of the voyages: a query over the voyages, joined to the table between a voyage and its ports of call and to the ports. Under `&`:

```text recording=sql
both = to_leith & to_lisbon
  Query.combine(rhs=a Query of Voyage, connector='AND')  (of a Query of Voyage)
    Query.bump_prefix(a Query of Voyage, exclude={'fleet_voyage'})
      WhereNode.relabel_aliases({'fleet_voyage_calls': 'U1', 'fleet_port': 'U2'})
    JoinPromoter.__init__(connector='AND', num_children=2, negated=False)
    JoinPromoter.add_votes(a generator)
    Query.join(Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, INNER JOIN, nullable), reuse=set())  ->  'T4'
    Query.join(Join(fleet_port, from T4 via Voyage_calls.port, INNER JOIN, not nullable), reuse=set())  ->  'T5'
    JoinPromoter.add_votes(set())
    JoinPromoter.update_join_types(a Query of Voyage)  ->  {'fleet_port', 'fleet_voyage_calls'}
    WhereNode.relabel_aliases({'U1': 'T4', 'U2': 'T5'})
alias_map['fleet_voyage']: BaseTable(fleet_voyage), referenced 2
alias_map['fleet_voyage_calls']: Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, INNER JOIN, nullable), referenced 1
alias_map['fleet_port']: Join(fleet_port, from fleet_voyage_calls via Voyage_calls.port, INNER JOIN, not nullable), referenced 1
alias_map['T4']: Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, LEFT OUTER JOIN, nullable), referenced 1
alias_map['T5']: Join(fleet_port, from T4 via Voyage_calls.port, LEFT OUTER JOIN, not nullable), referenced 1
tail(both), list(both)  ->  (('FROM "fleet_voyage" INNER JOIN "fleet_voyage_calls" ON ("fleet_voyage"."id" = "fleet_voyage_calls"."voyage_id") INNER JOIN "fleet_port" ON ("fleet_voyage_calls"."port_id" = "fleet_port"."id") LEFT OUTER JOIN "fleet_voyage_calls" "T4" ON ("fleet_voyage"."id" = "T4"."voyage_id") LEFT OUTER JOIN "fleet_port" "T5" ON ("T4"."port_id" = "T5"."id") WHERE ("fleet_port"."name" = %s AND "T5"."name" = %s)', ('Leith', 'Lisbon')), [<Voyage: Voyage object (1)>])
```

`bump_prefix` relabelled the clone's where tree, and its base table `"fleet_voyage"` kept its name. The left side's two inner joins were voted in. Each of the right side's two joins came to `Query.join` with an empty reuse set and was given a new alias, `"T4"` and then `"T5"`, the second relabelled first so that it hangs from `"T4"`. The right side's votes were the empty set: the join to the table between is nullable, so `join` made it an outer join, the join to the port hangs from it and so is outer too, and the type is read after `join` has set it, so neither voted. `update_join_types` returned the aliases it demoted, the left side's two, which were inner already. The alias map ends with five entries, and the right side's where tree, relabelled once more from `"U1"` and `"U2"` to the new aliases, stands under the `"AND"`. The statement joins a voyage to its calls twice, and the two outer joins change nothing in what comes back: the condition on `"T5"` is in the where clause under the `"AND"`, so a voyage with no row on the far side of the outer join fails it as it would fail an inner join. That is the duplicate join the comment speaks of. Under `|`:

```text recording=sql
either = to_leith | to_lisbon
  Query.combine(rhs=a Query of Voyage, connector='OR')  (of a Query of Voyage)
    Query.bump_prefix(a Query of Voyage, exclude={'fleet_voyage'})
      WhereNode.relabel_aliases({'fleet_voyage_calls': 'U1', 'fleet_port': 'U2'})
    JoinPromoter.__init__(connector='OR', num_children=2, negated=False)
    JoinPromoter.add_votes(a generator)
    Query.join(Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, INNER JOIN, nullable), reuse={'fleet_port', 'fleet_voyage', 'fleet_voyage_calls'})  ->  'fleet_voyage_calls'
    Query.join(Join(fleet_port, from fleet_voyage_calls via Voyage_calls.port, INNER JOIN, not nullable), reuse={'fleet_port', 'fleet_voyage'})  ->  'fleet_port'
    JoinPromoter.add_votes({'fleet_port', 'fleet_voyage_calls'})
    JoinPromoter.update_join_types(a Query of Voyage)  ->  {'fleet_port', 'fleet_voyage_calls'}
    WhereNode.relabel_aliases({'U1': 'fleet_voyage_calls', 'U2': 'fleet_port'})
alias_map['fleet_voyage']: BaseTable(fleet_voyage), referenced 2
alias_map['fleet_voyage_calls']: Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, INNER JOIN, nullable), referenced 2
alias_map['fleet_port']: Join(fleet_port, from fleet_voyage_calls via Voyage_calls.port, INNER JOIN, not nullable), referenced 2
tail(either), list(either)  ->  (('FROM "fleet_voyage" INNER JOIN "fleet_voyage_calls" ON ("fleet_voyage"."id" = "fleet_voyage_calls"."voyage_id") INNER JOIN "fleet_port" ON ("fleet_voyage_calls"."port_id" = "fleet_port"."id") WHERE ("fleet_port"."name" = %s OR "fleet_port"."name" = %s)', ('Leith', 'Lisbon')), [<Voyage: Voyage object (1)>, <Voyage: Voyage object (1)>])
```

Here the reuse set was the whole alias map. `Query.join` found, for each of the right side's joins, an equal join already in the map, two joins being equal by their table, parent alias, field and filtered relation (`django/db/models/sql/datastructures.py:Join.identity`), and returned its alias without touching the join's type, so both voted. Each join had two votes of two children and was demoted, which is to say left inner. The where tree was relabelled from the `"U"` aliases to the aliases found, and each join's reference count went up to two. The statement has one join of each table and both conditions on `"fleet_port"."name"`; and since the merged query has no distinct, the voyage that called at both ports comes back twice under `|`, once for each row that meets the condition, where under `&` it came back once.

```text figure=joins-under-and-and-or
the left side, to_leith                       the right side, to_lisbon: a clone, its aliases bumped
  fleet_voyage         BaseTable                fleet_voyage         kept: the base table is excluded
  fleet_voyage_calls   INNER JOIN               U1  fleet_voyage_calls
  fleet_port           INNER JOIN               U2  fleet_port
  where  fleet_port.name = 'Leith'              where  U2.name = 'Lisbon'

under AND, reuse = {}: every join made again       under OR, reuse = every alias: each join found again
  fleet_voyage         BaseTable                     fleet_voyage         BaseTable
  fleet_voyage_calls   INNER JOIN                    fleet_voyage_calls   INNER JOIN    U1 -> fleet_voyage_calls
  fleet_port           INNER JOIN                    fleet_port           INNER JOIN    U2 -> fleet_port
  T4  fleet_voyage_calls   LEFT OUTER JOIN  U1 -> T4
  T5  fleet_port           LEFT OUTER JOIN  U2 -> T5
  where  fleet_port.name = 'Leith'                   where  fleet_port.name = 'Leith'
         AND T5.name = 'Lisbon'                             OR fleet_port.name = 'Lisbon'
```

*The right side's two joins arriving in the left side's alias map under `&` and under `|`. Under `"AND"` no alias may be reused: each join is made again under a new alias, outer because the first is nullable and the second hangs from it, and the right side's where tree is relabelled to the new aliases. Under `"OR"` each join is found equal to one already there and takes its alias.*

### What else the right side gives

After the joins, `combine` takes the right side's subquery prefixes into its own `Query.subq_aliases`, so that, the comment says, relabelling handles subqueries in the where and select clauses ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). Then it clones the right side's where tree, relabels the clone with the renamings, and adds it to its own tree under the connector (`django/db/models/sql/where.py:WhereNode.relabel_aliases`, `django/utils/tree.py:Node.add`). What the tree then writes, and the or with a count that stands for `"XOR"` on a backend without it, is [The where clause: `build_filter`, `add_q` and `WhereNode`](where.md).

The selection is the right side's: its selected columns, relabelled, or none where it has none. The extra selects, which the comment there calls the right side's too, are in fact merged into the left side's, with one refusal: under `"OR"`, where both sides have extra selects, `ValueError`, the comment judging that such queries do not make sense or return consistent sets and are not worth the complexity when a real query can be written instead. The masks of the two are unioned, and the right side's extra tables are appended (`django/db/models/sql/query.py:Query.set_select`, `django/db/models/sql/query.py:Query.set_extra_mask`). The ordering is the right side's, `Query.order_by` and `Query.extra_order_by` each, unless it has none, in which case the left side's stands.

```text recording=sql
What combine takes from the right side: its ordering where it has one, its select, its extra, and the join promotion of the two where trees
    tail(Ship.objects.order_by('tonnage') | Ship.objects.order_by('name')), tail(Ship.objects.order_by('tonnage') & Ship.objects.all())  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()), ('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" ASC', ()))
    tail(Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500)) & Ship.objects.filter(captain__signed_on__year=2011))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") LEFT OUTER JOIN "crew_sailor" "T3" ON ("fleet_ship"."captain_id" = "T3"."id") WHERE (("crew_sailor"."name" = %s OR "fleet_ship"."tonnage" < %s) AND "T3"."signed_on" BETWEEN %s AND %s) ORDER BY "fleet_ship"."name" ASC', ('Cora', 500, '2011-01-01 00:00:00', '2011-12-31 23:59:59.999999'))
    tail(Ship.objects.filter(captain__name='Cora') | Ship.objects.filter(tonnage__lt=500))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") WHERE ("crew_sailor"."name" = %s OR "fleet_ship"."tonnage" < %s) ORDER BY "fleet_ship"."name" ASC', ('Cora', 500))
    sql_of(Ship.objects.filter(name='Petrel').extra(select={'a': '1'}) | Ship.objects.filter(name='Gannet'))  ->  ('SELECT (1) AS "a", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE ("fleet_ship"."name" = %s OR "fleet_ship"."name" = %s) ORDER BY "fleet_ship"."name" ASC', ('Petrel', 'Gannet'))
    Ship.objects.extra(select={'a': '1'}) | Ship.objects.extra(select={'b': '2'})  ->  raises ValueError: When merging querysets using 'or', you cannot have extra(select=...) on both sides.
    sql_of(Ship.objects.extra(select={'a': '1'}) & Ship.objects.extra(select={'b': '2'}))  ->  ('SELECT (1) AS "a", (2) AS "b", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
    Ship.objects.all().query.combine(Sailor.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine queries on two different base models.
    Ship.objects.all()[:1].query.combine(Ship.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine queries once a slice has been taken.
    Ship.objects.distinct().query.combine(Ship.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine a unique query with a non-unique query.
```

In the first line the right side's ordering won under `|`, and under `&` the right side, every ship, had no ordering of its own, a model's default ordering not being in `Query.order_by`, so the left side's stood. The second and third lines are the promoter at work on two where trees. In the second the left side's `"OR"` had promoted its join to the sailors to an outer join; the right side's join on the same relation was made again under `&`, nullable since a ship may have no captain, and so outer, and the statement has two outer joins to `"crew_sailor"`. In the third the left side's filter had an inner join and the right side had none, so under `|` the join had one vote of two and was promoted. The last two are the extra selects: refused on both sides under `|`, merged under `&`.

## The combinators: `combinator`, `combinator_all` and `combined_queries`

`Query` has three class attributes for a compound: `Query.combinator`, `None` or `"union"`, `"intersection"` or `"difference"`; `Query.combinator_all`, false unless a union was asked to keep duplicates; and `Query.combined_queries`, the tuple of the parts, empty for any other query (`django/db/models/sql/query.py:Query`). `QuerySet._combinator_query` sets the three on a clone of the left side, after clearing the clone's ordering and limits and switching its default ordering on; the first part is the left side's own query and the others are clones of the right sides' ([Combining querysets: the operators and `union`](../querysets/combining.md)). The combined query's own where tree and joins are the left side's, and the compiler writes neither: `SQLCompiler.as_sql` turns off to `get_combinator_sql` before the from clause and the where tree are compiled.

Several methods of `Query` reach into the parts. `Query.clone` clones each part (`django/db/models/sql/query.py:Query.clone`). `Query.clear_ordering` clears each part's ordering without force, passing on its own `clear_default=True` or `clear_default=False`; the comment says that the ordering of the parts is cleared with `clear_default=False` when `union` and its analogues are called, so that a later `clear_default=True` has to percolate (`django/db/models/sql/query.py:Query.clear_ordering`). `Query.set_empty` adds a `NothingNode` to each part's where tree as well as to the query's own (`django/db/models/sql/query.py:Query.set_empty`). `Query.resolve_expression` resolves each part against the outer query and `Query.change_aliases` renames in each part the external aliases its change touches, both for a compound that stands inside another query, below; and `Query.exists` is further down.

## `get_combinator_sql`: the parts compiled and joined

Where the query has a combinator, `SQLCompiler.as_sql` asks the backend's features whether it supports the operation, `supports_select_union` and its two fellows, which the base class has true, and raises `NotSupportedError` otherwise; then it calls `SQLCompiler.get_combinator_sql` with the combinator and `combinator_all` (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/backends/base/features.py:BaseDatabaseFeatures.supports_select_union`). Before that it has run `pre_sql_setup` with column aliases on, so that the combined query's own select list carries `"col1"`, `"col2"` and so on, by which the ordering can name a column ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)).

`get_combinator_sql` makes a compiler for each part, with the connection and the `elide_empty` of the compiler itself (`django/db/models/sql/compiler.py:SQLCompiler.get_combinator_sql`). Where the backend lacks `supports_slicing_ordering_in_compound` it then looks at every part before writing any: a part whose query is sliced is refused with `DatabaseError`, and so is a part for which the part's own `get_order_by` returns anything. The base class has the feature false; the backends for PostgreSQL, MySQL and Oracle set it true, and SQLite's leaves it (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_slicing_ordering_in_compound`). Since a part's `get_order_by` reads the `ordering` of the model's `Meta` wherever the part has its default ordering on, a model with one is refused as a part on SQLite unless the default was cleared on each part before combining, which [Combining querysets: the operators and `union`](../querysets/combining.md) shows.

Each part then goes through `_get_combinator_part_sql`, and a part that raises `EmptyResultSet` is left out of a union, and out of a difference once a part is already there; otherwise the exception goes on up, so that an empty part of an intersection, or an empty first part of a difference, empties the whole. No part left means `EmptyResultSet` too. One part left, in a union, where the whole is sliced, is the case the comment explains: a sliced union of a single component could end with two `"LIMIT"` clauses where the component is sliced too, so the empty part is put back, compiled with its `elide_empty` turned off so that it writes a predicate that is always false instead of raising. The operator is the backend's: `BaseDatabaseOperations.set_operators` maps the three names to `"UNION"`, `"INTERSECT"` and `"EXCEPT"`, and a union with `combinator_all` gets `" ALL"` (`django/db/backends/base/operations.py:BaseDatabaseOperations.set_operators`). Each part is put in parentheses where the query is not itself a subquery and the backend supports slicing and ordering in a compound, and left bare otherwise; the parts are joined with the operator between them, and their parameters follow in the same order.

`_get_combinator_part_sql` does two things to a part (`django/db/models/sql/compiler.py:SQLCompiler._get_combinator_part_sql`). Where the whole has `Query.selected`, which `values` or `values_list` on the combined queryset sets, and the part has none, the part's query is cloned and given the whole's selection through `Query.set_values`; the comment's rule is that if the columns list is limited, all combined queries must have the same columns list (`django/db/models/sql/query.py:Query.set_values`). Then the part's compiler writes its statement with `with_col_aliases=True`, so that every column has an alias, the name `values` gave it or `"col1"` and on. A part that is itself a compound is wrapped as `SELECT * FROM (...)` where the backend lacks `supports_parentheses_in_compound`, which SQLite's features class sets false, and put in parentheses where the whole is a subquery or the backend lacks slicing and ordering in a compound; a plain part is put in parentheses where the whole is a subquery and the backend has that feature (`django/db/backends/sqlite3/features.py:DatabaseFeatures.supports_parentheses_in_compound`).

In what follows old is the sailors who signed on before 2020, on_petrel the Petrel's crew and dag the sailors named Dag, and sql_of is the statement and parameters the queryset's compiler returns, unsent.

```text recording=sql
sql_of(old.union(on_petrel))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
sql_of(old.union(on_petrel, all=True))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION ALL SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
...
sql_of(old.difference(on_petrel))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s EXCEPT SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
```

Each part selects the four columns of a sailor under the aliases `"col1"` to `"col4"`, the parts are bare, and the operator stands between them with `" ALL"` after a union asked to keep duplicates. A nested compound, and the same three parts given to one `union`:

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

The ordering of a compound statement is the combined query's own, and it stands after the last part; what it may name is a column the parts select. In `SQLCompiler._order_by_pairs`, for a query with a combinator, a name is made an `F` of itself rather than resolved through the first model's field, the comment's reason being that other combined queries might define it differently, and a transform in a name is refused with `NotImplementedError` (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`). In `SQLCompiler.get_order_by` each such expression, once resolved, is looked for among the selected columns: found, it becomes a `Ref` to the column's alias; not found, a column `"__orderbycol"` with the number of the position it will take is added as an annotation to every part and selected on the whole, and the ordering refers to that, unless some part has a selection that `values` fixed, in which case `DatabaseError` says that the term does not match any column in the result set (`django/db/models/sql/compiler.py:SQLCompiler.get_order_by`). A name that is one of the names `values` gave the whole is matched earlier, in `_order_by_pairs`, to its position in the select list, and is written as that position. Then `as_sql` appends the `"ORDER BY"` to the joined parts, or on a backend with `requires_compound_order_by_subquery`, Oracle's, wraps the compound as `SELECT * FROM (...)` and puts the ordering outside. [ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md) has the two methods in full.

```text recording=sql
sql_of(old.union(on_petrel).order_by('name'))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "col2" ASC', ('2020-01-01 00:00:00', 1))
sql_of(old.union(on_petrel).order_by('-signed_on', 'name'))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "col4" DESC, "col2" ASC', ('2020-01-01 00:00:00', 1))
sql_of(old.values('name').union(on_petrel.values('name')).order_by('name'))  ->  ('SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY 1 ASC', ('2020-01-01 00:00:00', 1))
old.values('name').union(on_petrel.values('name')).order_by('id')  ->  raises DatabaseError: ORDER BY term does not match any column in the result set.
```

The first two orderings found their columns among the aliased selection and refer to them as `"col2"` and `"col4"`; the third names a column that `values` selected and is written by position; and the fourth asks for a column the parts, each fixed by `values`, do not select. Here is the call order where a column has to be added to the parts, with the union given `values("name")` and ordered by the moment of signing on:

```text recording=sql
A compound statement compiled: each part compiled by a compiler of its own with the outer query's selection, and an ORDER BY column the parts did not select added to each
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
              SQLCompiler.pre_sql_setup
                SQLCompiler.get_order_by  ->  []
                -> (extra_select of 0, order_by of 0, group_by of 0)
              -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
            -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
          SQLCompiler._get_combinator_part_sql(compiler for a Query of Sailor)
            Query.set_values({'name': 0, '__orderbycol2': 1})
            SQLCompiler.as_sql(with_col_aliases=True)
              SQLCompiler.pre_sql_setup
                SQLCompiler.get_order_by  ->  []
                -> (extra_select of 0, order_by of 0, group_by of 0)
              -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', (1,))
            -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', (1,))
          -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', ('2020-01-01 00:00:00', 1))
        -> ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "__orderbycol2" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "__orderbycol2" ASC', ('2020-01-01 00:00:00', 1))
```

`Query.set_values` was `values` on the combined queryset, setting the whole's selection to the one name. In `pre_sql_setup`, `get_order_by` found no selected column for the moment, added `"__orderbycol2"` as an annotation to each part and as a selected column of the whole, and wrote the ordering as a reference to it. `get_combinator_sql` then asked each part's compiler for its own ordering, the check for SQLite, and got none; gave each part the whole's selection, by now the name and the added column; and had each written with column aliases. `as_sql` put the ordering after the joined parts.

> **Changed in 6.1.** `QuerySet._combinator_query` switches the default ordering on for the combined query, so that the `ordering` of the model's `Meta` orders the whole statement where nothing else does. The release notes give what follows from it: `union`, `intersection` and `difference` raise `DatabaseError` when a field of the model's ordering is not among the columns that `values` or `values_list` selected, and calling `order_by` with no arguments after combining clears the default ordering (`docs/releases/6.1.txt`).

## A compound query inside another

A combined query stands inside another as any query does, with its parts resolved alongside it: `Query.resolve_expression` makes a clone with its alias prefix bumped and marked as a subquery, and resolves each part the same way, so that each part's aliases are moved to the new prefix too; `Query.as_sql` clears the ordering of the query and of each part where the backend does not ignore an unnecessary `"ORDER BY"` in a subquery, and puts the whole in parentheses (`django/db/models/sql/query.py:Query.resolve_expression`, `django/db/models/sql/query.py:Query.as_sql`). Inside, `get_combinator_sql` writes the parts bare on SQLite, as above. [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md) has the resolving in full. A union as the value of an `"in"`:

```text recording=sql
sql_of(Sailor.objects.filter(pk__in=old.union(on_petrel).values('pk')))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" AS "pk" FROM "crew_sailor" "U0" WHERE "U0"."signed_on" < %s UNION SELECT "U0"."id" AS "pk" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = %s)', ('2020-01-01 00:00:00', 1))
```

Each part's table is `"U0"`, the prefix the resolving gave it, and the `"in"` lookup cleared the ordering before that, through `Query.clear_ordering`, which reached the parts (`django/db/models/lookups.py:In.get_prep_lookup`).

## `exists` and `count` on a union

`Query.exists` on a union makes each part the part's own `exists(limit=False)`, so that every part selects the constant under the alias `"a"` and none is limited, and limits the whole to one row; `Query.get_aggregation`, for a count, wraps a query that has a combinator in a subquery and counts its rows (`django/db/models/sql/query.py:Query.exists`, `django/db/models/sql/query.py:Query.get_aggregation`). [Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md) has both.

```text recording=sql
str(old.union(on_petrel).query.exists())  ->  'SELECT 1 AS "a" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < 2020-01-01 00:00:00 UNION SELECT 1 AS "a" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = 1 LIMIT 1'
```
