---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: anatomy, names, joins, where, subqueries, combine
---

# Building a query

A `Query` is the description of a statement that a queryset's methods write and a compiler later reads: a filter's names are walked through the models to joins in an alias map, the words left over become lookups in a where tree, and the conditions vote together on which joins are inner and which outer.

A queryset's methods do not write SQL. Many leave something on an object the queryset carries, and nothing becomes SQL until a compiler reads it. That object is the **query**, an instance of `Query` (`django/db/models/sql/query.py:Query`). It has to do four things before any SQL exists. It has to read a filter's names, `"ship__home__name"`, against the models, and find from those words the tables to join and the column to compare. It has to keep the conditions in the shape the program gave them, under `"AND"`, `"OR"` and `"XOR"` with their negations, since the shape is the meaning. It has to decide, for each join, whether a row on the near side may stand without one on the far side, which is the difference between an inner and an outer join and is decided by the conditions together, not by any one of them. And it has to be copied whenever a queryset is, since a queryset that a program keeps may be refined into several others, and cheaply.

A table's **alias** is the name it goes by in a statement, such as its own name, `"crew_sailor"`, or `"T4"`. The word is also used for a key of `DATABASES`, which is the connection's ([Connections and transactions](connections.md)).

The examples are harbour's, whose models [Models and fields](models.md) lists, over the rows the recording began with, among them three ports, Bergen, Leith and Lisbon; two ships, the Petrel of Bergen and the Gannet of Leith; and four sailors, Ada and Bram of the Petrel and Cora and Dag of the Gannet, of whom Ada and Cora signed on in 2011 and the others in 2026. The recordings were made from a running Django, on SQLite. A line at the left is a line of Python as it was run; the lines set in under it are the calls it set going, nested as they were made, with only the calls the passage is about written down; `->` is what a call returned; a step of a path, a join and a query are put into words, as `PathInfo(from Sailor to Ship via Sailor.ship, direct, one)`, `Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable)` and a Query of Sailor; and a line of three dots stands for lines of the block left out.

## A filter becomes joins and a comparison

`QuerySet.filter` reduces its arguments to a `Q`, a tree of pairs of a name and a value, and hands it to `Query.add_q` ([`filter`, `exclude` and `Q` objects](querysets/filters.md)). Everything from there on is the query's. `Query.add_q` walks the `Q` with `Query._add_q`, which makes a `WhereNode` for the tree's node and calls `Query.build_filter` for each leaf (`django/db/models/sql/query.py:Query.add_q`, `django/db/models/sql/query.py:Query.build_filter`). Here is one filter with two conditions, one across two relations and one with a transform and a lookup in its name, cut to the calls that each of the three steps below turns on:

```text recording=sql
bergen_veterans = Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020)
...
          Query.build_filter(('ship__home__name', 'Bergen'), can_reuse=set())
            Query.solve_lookup_type(lookup='ship__home__name')
              Query.names_to_path(names=['ship', 'home', 'name'])  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], Port.name, (Port.name,), [])
...
              Query.join(join=Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable))
              ...
              Query.join(join=Join(fleet_port, from fleet_ship via Ship.home, INNER JOIN, not nullable))
...
            Query.build_lookup(lookups=[], lhs=Col(fleet_port, fleet.Port.name), rhs='Bergen')
              ...
              -> Exact(Col(fleet_port, fleet.Port.name), 'Bergen')
...
            Query.build_lookup(lookups=['year', 'lt'], lhs=Col(crew_sailor, crew.Sailor.signed_on), rhs=2020)
              Query.try_transform(lhs=Col(crew_sailor, crew.Sailor.signed_on), name='year', lookups=['year', 'lt'])  ->  ExtractYear(Col(crew_sailor, crew.Sailor.signed_on))
              ...
              -> YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020)
...
          JoinPromoter.update_join_types(a Query of Sailor)
            Query.promote_joins(set())
            Query.demote_joins({'crew_sailor', 'fleet_port', 'fleet_ship'})
            ...
```

For one pair, `build_filter` does three things in turn.

**The name is read against the models.** `Query.solve_lookup_type` splits it at each `"__"` and has `Query.names_to_path` walk the words as fields: `"ship"` is a foreign key of Sailor, `"home"` a foreign key of Ship, `"name"` a field of Port, and the walk stops at the first field that is no relation, or at a word that is no field, leaving `["year", "lt"]` over for `"signed_on"`. What the walk returns is a **path**, one `PathInfo` or more for each relation crossed, each saying which models it joins, through which field, in which direction and whether it can reach more than one row (`django/db/models/sql/query.py:Query.names_to_path`, `django/db/models/query_utils.py:PathInfo`). `Query.setup_joins` turns the path into joins, and `Query.trim_joins` takes back any join at the end whose only use is a key the previous table already holds, which is why `filter(ship=petrel)` joins nothing and compares the column `"ship_id"` ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](query/names.md)).

**The joins go into the alias map.** `Query.join` gives each `Join` it adds an alias and keeps it in `Query.alias_map`, which here is a tree: the base table, `"crew_sailor"`, at its root, and each join hung from a table already there, `"fleet_ship"` from the sailors and `"fleet_port"` from the ships. Each entry has a count of what refers to it, and a join whose count falls to zero is left in the map and is not written (`django/db/models/sql/query.py:Query.join`, `django/db/models/sql/datastructures.py:Join`, `django/db/models/sql/compiler.py:SQLCompiler.get_from_clause`). A join starts as `"INNER JOIN"` unless the relation can have no row on the far side, a nullable foreign key or a reverse relation, or the join it hangs from is outer already, in which case it starts as `"LEFT OUTER JOIN"`; and as the conditions are added a `JoinPromoter` counts, for each join, how many of a node's children need a row on the far side, and from the counts, the node's connector and the negations it stands under decides which joins to demote to inner and which to promote to outer, a promotion that `Query.promote_joins` makes only where the relation can have no row on the far side or the join hangs from an outer one (`django/db/models/sql/query.py:JoinPromoter.update_join_types`, `django/db/models/sql/query.py:Query.promote_joins`). That is the vote the two conditions above took on the joins of the ship and the port, which were inner as they were made and stayed so ([Tables and joins: the alias map and join promotion](query/joins.md)).

**The words left over become a lookup.** `Query.build_lookup` takes every word but the last for a **transform**, an expression made of the column, and the last for a **lookup**, a comparison of the column, or of the transformed column, with the value: `"year"` finds `ExtractYear` in the registry of the datetime field, and `"lt"` finds `YearLt` in the registry of `ExtractYear`; a last word that no lookup answers to is taken for one more transform and compared by `"exact"`, which is also the lookup where no word is left, as for `"ship__home__name"` (`django/db/models/sql/query.py:Query.build_lookup`). The lookup prepares its value through the field as it is made, and writes no SQL until the compiler asks; the classes it finds, and the registry they are found in, are [Expressions, lookups and functions](expressions.md)'s.

The lookup is wrapped in a `WhereNode` of its own and added to the node of its `Q`. The tree the filter leaves is an `"AND"` of the two lookups, the `Exact` and the `YearLt`, and `Query.where` holds it: the **where tree**. A negation is kept on the node, and `build_filter` adds a test for null beside a negated comparison of a column that can be null, in itself or by an outer join, so that the SQL agrees with Python's `not`; an exclude across a relation that can reach several rows is turned into a subquery under `"NOT EXISTS"`, since a negated join would exclude a ship for the one sailor whose name matches and keep it for the others ([The where clause: `add_q` and `build_filter`](query/where.md)).

The figure draws what the one call of `filter` left on the query: the two names walked, the alias map that the first one filled, the where tree whose leaves are bound to its aliases, and the vote.

```text figure=a-filter-built
Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020)

the names, walked through the models by names_to_path
  ship__home__name       Sailor --ship--> Ship --home--> Port . name           nothing left over
  signed_on__year__lt    Sailor . signed_on                                     year, lt left over

the alias map, Query.alias_map: a tree from the base table, a count on each entry
  crew_sailor        the base table
    fleet_ship         INNER JOIN, from crew_sailor via Sailor.ship
      fleet_port         INNER JOIN, from fleet_ship via Ship.home

the where tree, Query.where: its leaves bound to the aliases
  AND
    Exact    Col(fleet_port, name)  =  'Bergen'
    YearLt   ExtractYear(Col(crew_sailor, signed_on))  <  2020

the vote, as the AND node is finished: JoinPromoter
  each child says which joins it needs a row through; fleet_ship and fleet_port, INNER as made, stay INNER
```

*One filter of two conditions, as the query holds it. The first name is walked across two relations and leaves two joins in the alias map; the second names a column of the base table and leaves two words over, a transform and a lookup. Under the `"AND"`, the joins stay inner.*

## What else the query holds

The other methods of the queryset leave other things on the query. An annotation is an expression resolved against the query and kept in `Query.annotations` under its name; an aggregate among them sets `Query.group_by`. The ordering is kept as names and expressions and resolved only when the statement is written; `values` leaves the columns to select and their names; `defer` and `only` leave a set of field names to leave out or to keep; a slice leaves its limits in `Query.low_mark` and `Query.high_mark`. None of these is SQL, and a compiler reads them when the statement is written ([The SQL compiler](sql.md)).

The query is copied each time a queryset is cloned ([Clones: how a queryset is built](querysets/chaining.md)). `Query.clone` copies the containers, the alias map, the where tree, the annotations, and shares what they hold, the joins and the expressions; `Query.chain` is the copy `QuerySet._clone` asks for, a clone made ready for the next method ([The query: what a `Query` holds, and how it is copied](query/anatomy.md)).

## A query inside another, and two made one

A query is itself an expression: `Query` is built on `BaseExpression`, so a queryset given as a value, or a `Subquery` or an `Exists`, carries a query that can stand inside another. It is resolved against the outer one, with the aliases its map holds renamed so that the two do not collide, and the outer query's columns are reachable from inside through `OuterRef` ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](query/subqueries.md)). And two queries of one model can be made one: `Query.combine`, which the operators `&`, `|` and `^` between two querysets call, brings the right side's joins into the left side's alias map, deciding for each whether a join already there may serve, and adds its where tree under the connector ([Merging two queries: `Query.combine`](query/combine.md)).

## The neighbours

The query reads the model through its `_meta`: `names_to_path` asks the options for a field by name, a relation field for its path, and a child model for the path to its parent ([Models and fields](models.md), [Relations](relations.md)). The queryset whose methods write the query, and which asks for it to be run, is [QuerySets](querysets.md)'s. The lookups, transforms and other expressions the query holds, and the where tree's way of writing itself, are [Expressions, lookups and functions](expressions.md)'s; the compiler that reads the query and writes the statement is [The SQL compiler](sql.md)'s.
