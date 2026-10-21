---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Merging two queries: `Query.combine`

`Query.combine` merges a second query into a first: it brings the second query's joins into the first's alias map and adds its where tree under a connector, and it is what `&`, `|` and `^` between two querysets come to where neither is marked empty.

Two queries of one model can become one statement in two ways, and each way has its own difficulties. A **merge** writes one `"SELECT"` whose where clause holds the conditions of both; the other way, a compound statement, is the compiler's ([Compound statements: `get_combinator_sql`](../sql/compound.md)). For a merge the second query's tables have to be brought into the first's alias map without their aliases colliding; for each of its joins it has to be decided whether a join the first query already has may serve, since under `"AND"` a join shared by two conditions on a many-valued relation asks one related row to meet both; the types of the joins have to be settled again, by the votes of both sides ([Tables and joins: the alias map and join promotion](joins.md)); and the second query's conditions have to be relabelled to whatever aliases its joins were given.

The queryset's half is told in [Combining querysets: the operators and `union`](../querysets/combining.md): `QuerySet.__and__`, `QuerySet.__or__` and `QuerySet.__xor__` make the checks a merge needs and then, where neither is marked empty, call `Query.combine`.

The recordings below were made from a running Django, on SQLite, over the fleet and crew of [Models and fields](../models.md): a line at the left is Python as it was run, with its value or the exception it raised after `->`, and under it, nested as they were made, the calls it set going that the passage is about, with `->` what each returned, an object put into words, a query as a Query of its model and the object a method was called on in parentheses after the call. A line `alias_map[...]` is one entry of the query's alias map with its reference count, a line that begins sql_of( answers with a queryset's statement and its parameters, and a line of three dots stands for lines of the block left out.

## Merging: `Query.combine`

`Query.combine` is called on the left side's query, which the queryset has cloned, with the right side's query and a connector, `"AND"`, `"OR"` or `"XOR"`; its docstring promises that the right side is not modified (`django/db/models/sql/query.py:Query.combine`). It begins by refusing four pairs of queries, each with `TypeError`, in this order: queries of two different model classes; a left side that is sliced; one query with `Query.distinct` and the other without; two queries with different `Query.distinct_fields`. Three of the four, recorded:

```text recording=sql
Ship.objects.all().query.combine(Sailor.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine queries on two different base models.
Ship.objects.all()[:1].query.combine(Ship.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine queries once a slice has been taken.
Ship.objects.distinct().query.combine(Ship.objects.all().query, 'AND')  ->  raises TypeError: Cannot combine a unique query with a non-unique query.
```

### The right side's aliases

Both queries name their tables by one scheme, the table's own name the first time it appears and `"T"` with a number after that ([Tables and joins: the alias map and join promotion](joins.md)), so the right side's `"T4"` may be another table than the left side's, and renaming an alias as the joins come in could chain into renaming another, `"T4"` to `"T5"` and `"T5"` to `"T6"`. The comment at this point of `combine` gives that as the reason for what it does first: it clones the right side and has the clone move every alias but the base table's to a prefix the left side does not use, through `Query.bump_prefix`, so that no alias of the two queries can coincide (`django/db/models/sql/query.py:Query.bump_prefix`). The base table is left out because, as the comment says, it has to be present in the query on both sides. The recording under [Which joins may be reused](#which-joins-may-be-reused) shows the clone's where tree relabelled to `"U1"` and `"U2"`.

### Which joins may be reused

Under `"AND"` `combine` lets no alias of the left side serve a join of the right side, and makes every join again; under `"OR"` and `"XOR"` it lets any serve. The comment gives the reason: a filter such as `revrel__col=1 & revrel__col=2` cannot be met by one related row, but two related rows might meet it, one each, so the two conditions need two joins; under `"OR"` a single true suffices, so a single row does. It admits what the rule costs too: for joins that are not many-to-many the `"AND"` case makes duplicate joins, correct but too many, and calls that something that could be fixed later on.

The joins are then brought in one by one, with a `JoinPromoter` watching, and the rule the loop comes to is this. A join found again keeps its type, and votes where the right side had it inner. A join made again is typed by `Query.join`, outer where it is nullable or hangs from an outer join, and it votes only where `join` made it inner. The promoter is made for two children under the connector, and the aliases of the left side's inner joins are voted in first (`django/db/models/sql/query.py:JoinPromoter.add_votes`). Then each entry of the right side's alias map after the first, its base table, is relabelled with the renamings made so far, so that a join whose parent was renamed hangs from the new name, and handed to `Query.join` with the set of aliases that may be reused; `join` returns an existing alias where a join equal to this one is among those and a new one otherwise, and gives a new join its type (`django/db/models/sql/datastructures.py:Join.relabeled_clone`, `django/db/models/sql/query.py:Query.join`). Only then is the join's type read, and where it is inner the alias is a vote for the right side. The alias is taken out of the reuse set, since, the comment says, two distinct joins of one relation in the right side must stay two joins in the result; the renaming is recorded where the alias changed; and where the right side held the alias but no longer referred to it, the new alias is unreferenced once, so that it is unused in the merged query as well, the join having been added at all so that join promotion knows its type. The right side's votes go in last, and `JoinPromoter.update_join_types` settles the voted joins under `"AND"` and `"OR"`: under `"AND"` each is demoted to inner; under `"OR"` a join voted for by fewer than both sides is promoted to outer and one voted for by both is demoted; under `"XOR"` it promotes and demotes nothing, so each join keeps its type (`django/db/models/sql/query.py:JoinPromoter.update_join_types`). [Tables and joins: the alias map and join promotion](joins.md) has the promoter in full.

In the recording to_leith and to_lisbon are the voyages that called at Leith and at Lisbon, each a `filter(calls__name=...)` of the voyages: a query over the voyages, joined to the table between a voyage and its ports of call and to the ports. Under `&`, with tail asking for the statement from its `"FROM"` clause on and list for the rows:

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

`bump_prefix` relabelled the clone's where tree, and its base table `"fleet_voyage"` kept its name. The left side's two inner joins were voted in. Each of the right side's two joins came to `Query.join` with an empty reuse set and was given a new alias, `"T4"` and then `"T5"`, the second relabelled first so that it hangs from `"T4"`. The right side's votes were the empty set: the join to the table between is nullable, so `join` made it an outer join, the join to the port hangs from it and so is outer too, and the type is read after `join` has set it, so neither voted. `update_join_types` returned the aliases it demoted, the left side's two, which were inner already. The alias map ends with five entries, and the right side's where tree, relabelled once more from `"U1"` and `"U2"` to the new aliases, stands under the `"AND"`. The statement joins a voyage to its calls twice, and the two outer joins change nothing in what comes back: the condition on `"T5"` is in the where clause under the `"AND"`, so a voyage with no row on the far side of the outer join fails it as it would fail an inner join. That is the join the comment says must be made again: a many-to-many, where no one related row can meet both conditions. The duplicate it calls a cost is a join that is not many-to-many, as the join to a ship's captain is in the recording under *What else the right side gives*. Under `|`:

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

Here the reuse set was the whole alias map. `Query.join` found, for each of the right side's joins, an equal join already in the map, two joins being equal by their class, table, parent alias, field and filtered relation (`django/db/models/sql/datastructures.py:Join.identity`), and returned its alias without touching the join's type, so both voted. Each join had two votes of two children and was demoted, which is to say left inner. The where tree was relabelled from the `"U"` aliases to the aliases found, and each join's reference count went up to two. The statement has one join of each table and both conditions on `"fleet_port"."name"`; and since the merged query has no distinct, the voyage that called at both ports comes back twice under `|`, once for each row that meets the condition, where under `&` it came back once.

```text figure=joins-under-and-and-or
the left side, to_leith
  fleet_voyage             BaseTable
  fleet_voyage_calls       INNER JOIN        from fleet_voyage
  fleet_port               INNER JOIN        from fleet_voyage_calls
  where  fleet_port.name = 'Leith'

the right side, to_lisbon: a clone, its aliases bumped
  fleet_voyage             BaseTable         kept: the base table is excluded
  U1  fleet_voyage_calls   INNER JOIN        from fleet_voyage
  U2  fleet_port           INNER JOIN        from U1
  where  U2.name = 'Lisbon'

combined under AND, reuse = set(): every join made again
  fleet_voyage             BaseTable
  fleet_voyage_calls       INNER JOIN        from fleet_voyage
  fleet_port               INNER JOIN        from fleet_voyage_calls
  T4  fleet_voyage_calls   LEFT OUTER JOIN   from fleet_voyage         U1 -> T4
  T5  fleet_port           LEFT OUTER JOIN   from T4                   U2 -> T5
  where  fleet_port.name = 'Leith' AND T5.name = 'Lisbon'

combined under OR, reuse = every alias: each join found again
  fleet_voyage             BaseTable
  fleet_voyage_calls       INNER JOIN        from fleet_voyage         U1 -> fleet_voyage_calls
  fleet_port               INNER JOIN        from fleet_voyage_calls   U2 -> fleet_port
  where  fleet_port.name = 'Leith' OR fleet_port.name = 'Lisbon'
```

*The right side's two joins arriving in the left side's alias map under `&` and under `|`. Under `"AND"` no alias may be reused: each join is made again under a new alias, outer because the first is nullable and the second hangs from it, and the right side's where tree is relabelled to the new aliases. Under `"OR"` each join is found equal to one already there and takes its alias.*

### What else the right side gives

After the joins, `combine` takes the right side's subquery prefixes into its own `Query.subq_aliases` ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). Then it clones the right side's where tree, relabels the clone with the renamings, and adds it to its own tree under the connector (`django/db/models/sql/where.py:WhereNode.relabel_aliases`, `django/utils/tree.py:Node.add`). What the tree then writes, and the or with a count that stands for `"XOR"` on a backend without it, is [What the where tree writes: `WhereNode`](../expressions/where-node.md).

The selection is the right side's: its selected columns, relabelled, or none where it has none. The extra selects, which the comment there calls the right side's too, are in fact merged into the left side's, with one refusal: under `"OR"`, where both sides have extra selects, `ValueError`, the comment judging that such queries do not make sense or return consistent sets and are not worth the complexity when a real query can be written instead. The masks of the two are unioned, and the right side's extra tables are appended (`django/db/models/sql/query.py:Query.set_select`, `django/db/models/sql/query.py:Query.set_extra_mask`). The ordering is the right side's, `Query.order_by` and `Query.extra_order_by` each, unless it has none, in which case the left side's stands. What a reader should expect of a merged queryset, then, is that it selects what the right side selected, and is ordered as the right side was wherever the right side was ordered at all.

```text recording=sql
tail(Ship.objects.order_by('tonnage') | Ship.objects.order_by('name')), tail(Ship.objects.order_by('tonnage') & Ship.objects.all())  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()), ('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" ASC', ()))
tail(Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500)) & Ship.objects.filter(captain__signed_on__year=2011))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") LEFT OUTER JOIN "crew_sailor" "T3" ON ("fleet_ship"."captain_id" = "T3"."id") WHERE (("crew_sailor"."name" = %s OR "fleet_ship"."tonnage" < %s) AND "T3"."signed_on" BETWEEN %s AND %s) ORDER BY "fleet_ship"."name" ASC', ('Cora', 500, '2011-01-01 00:00:00', '2011-12-31 23:59:59.999999'))
tail(Ship.objects.filter(captain__name='Cora') | Ship.objects.filter(tonnage__lt=500))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") WHERE ("crew_sailor"."name" = %s OR "fleet_ship"."tonnage" < %s) ORDER BY "fleet_ship"."name" ASC', ('Cora', 500))
...
sql_of(Ship.objects.filter(name='Petrel').extra(select={'a': '1'}) | Ship.objects.filter(name='Gannet'))  ->  ('SELECT (1) AS "a", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE ("fleet_ship"."name" = %s OR "fleet_ship"."name" = %s) ORDER BY "fleet_ship"."name" ASC', ('Petrel', 'Gannet'))
Ship.objects.extra(select={'a': '1'}) | Ship.objects.extra(select={'b': '2'})  ->  raises ValueError: When merging querysets using 'or', you cannot have extra(select=...) on both sides.
sql_of(Ship.objects.extra(select={'a': '1'}) & Ship.objects.extra(select={'b': '2'}))  ->  ('SELECT (1) AS "a", (2) AS "b", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
```

In the first line the right side's ordering won under `|`, and under `&` the right side, every ship, had no ordering of its own, a model's default ordering not being in `Query.order_by`, so the left side's stood. The second and third lines are the promoter at work on two where trees. In the second the left side's `"OR"` had promoted its join to the sailors to an outer join; the right side's join on the same relation was made again under `&`, nullable since a ship may have no captain, and so outer, and the statement has two outer joins to `"crew_sailor"`. That is the duplicate join the comment calls a cost, made for a relation that is not many-to-many. In the third the left side's filter had an inner join and the right side had none, so under `|` the join had one vote of two and was promoted. The last three are the extra selects: one side's under `|` go through, both sides' under `|` are refused, and both sides' under `&` are merged, each column in the select list.
