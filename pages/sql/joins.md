---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Tables and joins: the alias map and join promotion

`Query.alias_map` is the query's record of every table its statement joins, each under an alias and each but the first a `Join` from a table already there; `Query.join` adds a join to it or reuses one, `Query.table_alias` names it, and `Query.alias_refcount` counts what refers to it. Whether a join is written `"INNER JOIN"` or `"LEFT OUTER JOIN"` is decided by the conditions together, through `JoinPromoter`, `Query.promote_joins` and `Query.demote_joins`; `Query.bump_prefix` and `Query.change_aliases` rename the aliases of a query that is to stand inside another.

A statement reads one table and joins others to it, and the query has to keep that list as conditions, selected columns and an ordering add to it. A table may be joined more than once, so a table is known by an **alias**, and the first alias of a table is its own name, unless the join carries a filtered relation. Each join hangs from a table already in the list, along a field, so that the compiler can write what the join's `"ON"` compares. A join made for a condition that is later dropped, or made by the compiler for an ordering, must not be written and must not be taken out either, since the query is read again at the next evaluation, so each alias carries a count of what refers to it. Whether a join is inner or outer cannot be settled when the join is made: the ships with no captain must survive `Q(captain__name="Cora") | Q(tonnage__lt=500)` and need not survive `captain__name="Cora"` alone, and the same join serves both. And a query put inside another must share no alias with it. The alias map, the counts and the promoter are the query's answers; the compiler reads the map once, when it writes the `"FROM"` clause.

Where a join comes from, the walk of a name into a path and a `Join` for each step of it, is [From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md); what a condition does with a join's alias, and the subquery an `exclude` across a multi-valued relation becomes, is [The where clause: `build_filter`, `add_q` and `WhereNode`](where.md).

## The alias map

`Query.alias_map` is a dictionary from each alias to its entry, in the order the entries were made, except that a join whose filtered relation joined tables of its own is moved after them, and that renaming through `change_aliases` moves the renamed entries after any that were excluded; the first entry is the table the statement selects from (`django/db/models/sql/query.py:Query.__init__`). That entry is a `BaseTable`; every later one is a `Join`, which hangs from an earlier alias. `Query.base_table` is the first key, kept as a cached property that `clone` drops so that a clone works it out again, and `Query.get_initial_alias` is how a method that is about to join gets it: the first key, with its count raised by one, or, on a query that has no entry yet, a `BaseTable` of the model's table put in through `join` (`django/db/models/sql/query.py:Query.get_initial_alias`). Beside the map the query keeps `Query.table_map`, from each table's name to the list of its aliases, which is how `table_alias` knows whether a table is already in the map; `Query.alias_refcount`, from each alias to the count of what refers to it; and `Query.used_aliases`, the aliases that the current call of `filter` has made, which `Query.chain` empties between one call and the next unless the filter is sticky ([The query: what a `Query` holds, and how it is copied](query.md), [Clones: how a queryset is built](../querysets/chaining.md)).

Recorded from a running Django on SQLite: in the lines below, once is a queryset of voyages with two conditions on their ports of call in one call of `filter`, `calls__name="Leith"` and `calls__country="Scotland"`; an `alias_map` line writes out one entry of the map, in the recording's words for a join, with the count of references to its alias and with the join type as the filter's conditions have left it, the work of `JoinPromoter`; and a line that asks a question gives its answer after `->`, tail being the statement from its `"FROM"` on.

```text recording=sql
alias_map['fleet_voyage']: BaseTable(fleet_voyage), referenced 2
alias_map['fleet_voyage_calls']: Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, INNER JOIN, nullable), referenced 2
alias_map['fleet_port']: Join(fleet_port, from fleet_voyage_calls via Voyage_calls.port, INNER JOIN, not nullable), referenced 2
tail(once)  ->  ('FROM "fleet_voyage" INNER JOIN "fleet_voyage_calls" ON ("fleet_voyage"."id" = "fleet_voyage_calls"."voyage_id") INNER JOIN "fleet_port" ON ("fleet_voyage_calls"."port_id" = "fleet_port"."id") WHERE ("fleet_port"."country" = %s AND "fleet_port"."name" = %s)', ('Scotland', 'Leith'))
```

The many-to-many field made two joins of one word, the table between and the ports' table, and the second condition reused both, so that each of the two conditions is on the same joined port: a voyage that called at Leith and at some Scottish port other than Leith does not match. The joins hang one from the other, and the chain is what the `"FROM"` clause writes.

## `Join` and `BaseTable`

A `Join` holds what the compiler needs to write one `"JOIN"` clause: the name of the table joined, the alias it is joined under, the alias of the table it hangs from, the join type, the field or rel the join is made along, whether the join is nullable, and the filtered relation it carries, where it carries one (`django/db/models/sql/datastructures.py:Join`). From the field it takes, as it is made, the pairs of fields the `"ON"` clause compares, through the field's `get_joining_fields`, a pair for each column of the key, and keeps their column names as `Join.join_cols`; a rel answers with its field's pairs the other way round (`django/db/models/fields/related.py:ForeignObject.get_joining_fields`, `django/db/models/fields/reverse_related.py:ForeignObjectRel.get_joining_fields`). The field's side of the pairs is [Relations](../models/relations.md).

> **Changed in 6.0.** `Join` no longer falls back to a field's `"get_joining_columns"`, and that method of `ForeignObject` and `ForeignObjectRel` is gone, as is `"get_reverse_joining_columns"` of `ForeignObject` (`docs/releases/6.0.txt`).

`Join.as_sql` writes the clause. For each pair it asks the backend's `prepare_join_on_clause` for the two sides as expressions, a `Col` of each alias and field in the base implementation, compiles them and writes them with `=` between (`django/db/models/sql/datastructures.py:Join.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.prepare_join_on_clause`). After the pairs it adds, in parentheses, whatever the field's `get_extra_restriction` returns, a hook that returns `None` on `ForeignObject` and that a relation of `django.contrib.contenttypes` uses to restrict a join to one content type, and then the filtered relation's condition, compiled, unless the condition matches every row (`django/db/models/fields/related.py:ForeignObject.get_extra_restriction`). An `"ON"` clause with nothing in it is refused with `ValueError`. The clause is the join type, the table's name quoted, the alias quoted where it differs from the table's name, and the conditions joined by `"AND"` in parentheses.

> **Changed in 6.1.** Table and `"JOIN"` aliases are now quoted systematically, as are the aliases of annotations, so that a special character in one cannot collide with the SQL around it: the recording writes `"crew_sailor" "T3"` (`docs/releases/6.1.txt`).

Two joins are the same join when their `Join.identity` agrees: the class, the table's name, the alias they hang from, the field they are made along, and the filtered relation, compared through `FilteredRelation.__eq__`. The alias of the join itself is not in it, nor the join type, nor whether it is nullable, so a `Join` made afresh for a second condition equals the one already in the map, which is what lets `join` reuse it. `Join.relabeled_clone` returns a copy with the aliases renamed through a mapping, and `Join.promote` and `Join.demote` return a copy made outer and a copy made inner: a join's type and aliases are never changed in place once it is in the map, and the entry is replaced by a copy instead, which is why a clone of a query can share the `Join` objects of its original ([The query: what a `Query` holds, and how it is copied](query.md)); the one thing written on an entry after it is in the map is the filtered relation `join` resolves at once.

```text recording=sql
A Join and a BaseTable: what each holds, and what makes two joins equal
    j = twice.query.alias_map['T4']
    j.table_name, j.parent_alias, j.table_alias, j.join_type, j.join_cols, j.nullable, j.filtered_relation, brief(j.join_field)  ->  ('fleet_voyage_calls', 'fleet_voyage', 'T4', 'INNER JOIN', (('id', 'voyage_id'),), True, None, 'the rel of Voyage_calls.voyage')
    j.identity == twice.query.alias_map['fleet_voyage_calls'].identity, j == twice.query.alias_map['fleet_voyage_calls'], j.relabeled_clone({'T4': 'T9'}).table_alias, j.promote().join_type, j.demote().join_type  ->  (True, True, 'T9', 'LEFT OUTER JOIN', 'INNER JOIN')
    twice.query.alias_map['fleet_voyage'].identity, twice.query.alias_map['fleet_voyage'].join_type, twice.query.alias_map['fleet_voyage'].parent_alias  ->  ((<class 'django.db.models.sql.datastructures.BaseTable'>, 'fleet_voyage', 'fleet_voyage'), None, None)
    twice.query.alias_refcount['fleet_voyage'], twice.query.base_table, twice.query.get_initial_alias(), twice.query.alias_refcount['fleet_voyage']  ->  (2, 'fleet_voyage', 'fleet_voyage', 3)
    twice.query.count_active_tables()  ->  5
```

Here j is the entry under `"T4"` of twice, a queryset of voyages filtered across their ports of call in two calls of `filter`, which joined the same two tables twice. The first questions ask what it holds, and whether it equals the first join of its table: it does, the alias apart; the relabelled clone carries the new alias, the promoted copy is outer and the demoted copy inner, as j was already, and each is a new object. A `BaseTable` holds only a table's name and its alias, and its identity is those two with the class; it writes the name, and the alias after it where the two differ (`django/db/models/sql/datastructures.py:BaseTable`). The question that reads the base table's count twice reads it before and after its own `get_initial_alias`, which raised it by one. `Query.count_active_tables` is the number of aliases whose count is not zero, which the update compiler asks before it decides whether an update can be written against one table ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md)).

## `table_alias` and `join`: an alias, and when a join is reused

`Query.table_alias` gives a table an alias (`django/db/models/sql/query.py:Query.table_alias`). Asked to create one, it gives a table that is not yet in `table_map` the table's own name, or the alias of the filtered relation where the join carries one; a table that is already there gets the query's prefix, `"T"` unless `bump_prefix` has changed it, followed by a number one more than the entries the map has, which is why the recording's second join of the table between is `"T4"` in a map of three entries. Either way the new alias starts with a count of one. Asked without creating, it returns the table's first alias and raises its count where the table has one, and makes one otherwise; that is what `get_from_clause` does for an extra table.

`Query.join` is given a `Join` or a `BaseTable` and returns its alias, after either reusing an entry of the map or adding one (`django/db/models/sql/query.py:Query.join`). It looks for entries that equal the join, among all of them where it is given no set of reusable aliases and among the set's where it is given one; where there are any, it takes the one under the join's own alias where the join came with one, as a join made for a filtered relation does, and the most recent otherwise, since, the comment says, a many-to-many relation may be joined several times, raises that alias's count, and returns it. Otherwise it has `table_alias` make an alias, settles the join's first type, puts the join in the map under the alias and, where the join carries a filtered relation, has the relation resolve its condition against the query, with the new alias among what the resolving may reuse; where resolving added joins of its own, the entry is moved to the end of the map, so that it is written after the joins it depends on. What the first type is, and what changes it, is the subject of the section on promotion.

Which joins may be reused is decided by the caller, and `setup_joins` is the caller that matters: for a step of a path that can reach several rows for one row of the model it leaves, a reverse foreign key or a many-to-many relation, it passes the set it was given, and for any other step it passes `None`, so that an equal join is always reused (`django/db/models/sql/query.py:Query.setup_joins`). The set, for a filter, is `used_aliases`, and `build_filter` adds to it the joins each condition settled, so that the second condition of one `filter` call reuses the first's join across a many-valued relation, as above, and a condition in a later call does not: `chain` emptied the set between the calls. Here twice is the same two conditions as once, in two calls of `filter`:

```text recording=sql
alias_map['fleet_voyage_calls']: Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, INNER JOIN, nullable), referenced 1
alias_map['fleet_port']: Join(fleet_port, from fleet_voyage_calls via Voyage_calls.port, INNER JOIN, not nullable), referenced 1
alias_map['T4']: Join(fleet_voyage_calls, from fleet_voyage via the rel of Voyage_calls.voyage, INNER JOIN, nullable), referenced 1
alias_map['T5']: Join(fleet_port, from T4 via Voyage_calls.port, INNER JOIN, not nullable), referenced 1
twice.query.table_map, sorted(twice.query.used_aliases)  ->  ({'fleet_voyage': ['fleet_voyage'], 'fleet_voyage_calls': ['fleet_voyage_calls', 'T4'], 'fleet_port': ['fleet_port', 'T5']}, ['T4', 'T5', 'fleet_voyage'])
tail(twice)  ->  ('FROM "fleet_voyage" INNER JOIN "fleet_voyage_calls" ON ("fleet_voyage"."id" = "fleet_voyage_calls"."voyage_id") INNER JOIN "fleet_port" ON ("fleet_voyage_calls"."port_id" = "fleet_port"."id") INNER JOIN "fleet_voyage_calls" "T4" ON ("fleet_voyage"."id" = "T4"."voyage_id") INNER JOIN "fleet_port" "T5" ON ("T4"."port_id" = "T5"."id") WHERE ("fleet_port"."name" = %s AND "T5"."country" = %s)', ('Leith', 'Scotland'))
```

The second call joined the table between and the ports' table again, under `"T4"` and `"T5"`, and its condition stands on `"T5"`: a voyage that called at Leith and at any Scottish port matches. `table_map` lists both aliases of each table, and `used_aliases` holds what the second call made, the base table and its two joins. Where a many-to-many manager's queryset is filtered, the set is carried over one call so that the filter shares the manager's own join, and that is the sticky filter of [Clones: how a queryset is built](../querysets/chaining.md). A join along a foreign key, which reaches one row, is reused across calls as within one: a condition on a sailor's ship's name and, in a second call of `filter`, one on the ship's tonnage share one join of the ships' table.

```text recording=sql
alias_map['crew_sailor']: BaseTable(crew_sailor), referenced 2
alias_map['fleet_ship']: Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable), referenced 2
```

## Reference counts

Each alias has a count in `Query.alias_refcount`, raised by `Query.ref_alias` and lowered by `Query.unref_alias`, and the count says how many things stand on the alias: `join` raises the count of an alias it reuses, `table_alias` starts a new one at one, and `get_initial_alias` raises the base table's each time a caller starts a walk from it: once for each condition of a filter, once for each `F` that names a path, once for all the names of a `values` (`django/db/models/sql/query.py:Query.ref_alias`, `django/db/models/sql/query.py:Query.unref_alias`). A count, not a flag: an alias is referred to by several things, and let go of at several times. `trim_joins` lowers the count of a join it takes back, and the join stays in the map, with a count of zero where nothing else referred to it ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). `build_filter` makes its joins before it knows whether the condition will be kept, and its docstring says that a caller which does not add the clause it returns is responsible for unreferencing the joins it used. And the compiler joins tables of its own for an ordering or a selected relation when the statement is written, and puts every count back to what it was, through `Query.reset_refcounts`, before `as_sql` returns, so that the query is as it was for the next evaluation (`django/db/models/sql/query.py:Query.reset_refcounts`, [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)). `reset_refcounts` is given the counts to go back to and lowers each alias's count by the difference. A join whose count is zero is left out of the statement by `SQLCompiler.get_from_clause`.

## Join promotion

A join starts with a type and the conditions change it. The rule the compiler needs is this: a row of the base table that has no row on the far side of a join is lost under an inner join and kept, with nulls, under an outer one; a condition on the far side's columns cannot be true of nulls, so a join such a condition stands on may be inner where the condition must hold, and must be outer where the row may match some other way. Three methods carry it.

**The first type, at `join`.** A new join is outer where the join it hangs from is outer or the join is nullable, and inner otherwise; the docstring of `join` says that a join is always made outer when its left side is outer, to make sure chains like an outer join followed by an inner one are not made (`django/db/models/sql/query.py:Query.join`). Nullable is what `setup_joins` decided from the path, a reverse step or a step along a key that `Query.is_nullable` says may be null ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). So the join a ship makes to its captain, a one-to-one that may be null, and the join a ship makes to its crew, a reverse relation, both start outer, and the join a sailor makes to its ship, a key that may not be null, starts inner. A join that no condition stands on keeps the type it started with: an annotation of `F("captain__name")` leaves the join outer, and the ships with no captain are in the result with a null for the name.

**`promote_joins` and `demote_joins`.** `Query.promote_joins` is given aliases and makes each outer, where the join is nullable or the join it hangs from is outer and it is not outer already, skipping the base table; when it has promoted one it adds to its list every join that hangs from it, so that no inner join is left under an outer one, since, the docstring says, promoting the first without the second would change nothing in the result (`django/db/models/sql/query.py:Query.promote_joins`). `Query.demote_joins` makes each outer join among its aliases inner. Its docstring says the join a demoted join hangs from must be demoted too, so that no outer join is left above an inner one; what the method does is look at that join and add it to its list only where it is inner already, so an outer join above is not demoted here. A demotion by votes reaches it all the same, since a condition's vote names every join on its path (`django/db/models/sql/query.py:Query.demote_joins`).

**`JoinPromoter`: the votes.** `Query._add_q` makes a `JoinPromoter` for each node of the `Q` it walks, with the node's connector, the number of its children, and whether the node stands under an odd number of negations, its own counted, and after it has built the children's clauses it has the promoter settle the joins, unless the caller asked it not to, as a filtered relation's condition does (`django/db/models/sql/query.py:Query._add_q`, `django/db/models/sql/query.py:JoinPromoter`). Each child's clause comes back from `build_filter` with a **vote**: the aliases the condition needs a row at, which are every alias on its name's path, the base table and the joins that were trimmed included, and those a value such as an `F` joined; or no aliases at all where the condition must be allowed a missing row: an `"isnull"` of `True` that is not negated, or, under a negation, any comparison but an `"isnull"` of `True`, to which `build_filter`, unless the comparison is itself an `"isnull"`, adds an `"IS NOT NULL"` where the column may be null or the join it stands on is outer ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)). A child that is a `Q` of its own votes with what its own promoter settled as inner. `JoinPromoter.add_votes` counts each vote in a `collections.Counter` by alias.

`JoinPromoter.update_join_types` then reads the counts against the node's **effective connector**: the node's own, or, where the node is negated, `"OR"` for an `"AND"` and `"AND"` for anything else, so that `NOT (a AND b)` is treated as `a OR b` and `NOT (a OR b)` as `a AND b` (`django/db/models/sql/query.py:JoinPromoter.update_join_types`). Under `"OR"`, an alias that fewer than all the children voted for is promoted, and the comment gives the reason: if one relation produces no row and another child matches, an inner join to the first would remove a valid match. Under `"AND"`, every alias voted for is demoted, and so, under `"OR"`, is one that every child voted for: if the relation produces no row, no child can match, and the comment says an inner join is then safe. Under `"XOR"` neither test is met and the joins keep their types. The method calls `promote_joins` and then `demote_joins`, and returns what it demoted, which is the node's vote to the node above it. Last, `Query.add_q`, which called `_add_q` on the whole tree, demotes every join that was inner before the tree was added: a comment there says the new tree is joined to the existing conditions by `"AND"`, so an existing inner join must stay inner, and an existing outer one may be demoted (`django/db/models/sql/query.py:Query.add_q`).

Three promoters asked for their effective connector, a negated `"OR"`, a negated `"AND"` and an `"OR"` that is not negated:

```text recording=sql
JoinPromoter('OR', 2, True).effective_connector, JoinPromoter('AND', 2, True).effective_connector, JoinPromoter('OR', 2, False).effective_connector  ->  ('AND', 'OR', 'OR')
```

The recording has the three cases the comments give. First an `"OR"` whose two children do not share a join; the lines are calls nested as they were made, with only the calls this passage is about written down, and `->` is what a call returned:

```text recording=sql
either = Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500))
  Query.add_q(q_object=<Q: (AND: (OR: ('captain__name', 'Cora'), ('tonnage__lt', 500)))>)
    Query._add_q(<Q: (AND: (OR: ('captain__name', 'Cora'), ('tonnage__lt', 500)))>)
      JoinPromoter.__init__(connector='AND', num_children=1, negated=False)
      Query._add_q(<Q: (OR: ('captain__name', 'Cora'), ('tonnage__lt', 500))>)
        JoinPromoter.__init__(connector='OR', num_children=2, negated=False)
        Query.join(BaseTable(fleet_ship))  ->  'fleet_ship'
        Query.join(Join(crew_sailor, from fleet_ship via Ship.captain, INNER JOIN, nullable))  ->  'crew_sailor'
        JoinPromoter.add_votes({'crew_sailor', 'fleet_ship'})
        JoinPromoter.add_votes({'fleet_ship'})
        JoinPromoter.update_join_types(a Query of Ship)
          Query.promote_joins({'crew_sailor'})
          Query.demote_joins({'fleet_ship'})
          -> {'fleet_ship'}
      JoinPromoter.add_votes({'fleet_ship'})
      JoinPromoter.update_join_types(a Query of Ship)
        Query.promote_joins(set())
        Query.demote_joins({'fleet_ship'})
        -> {'fleet_ship'}
    Query.demote_joins(set())
alias_map['fleet_ship']: BaseTable(fleet_ship), referenced 2
alias_map['crew_sailor']: Join(crew_sailor, from fleet_ship via Ship.captain, LEFT OUTER JOIN, nullable), referenced 1
```

The captain's join was made outer, nullable as it is. The condition on the captain voted for the base table and the join, the condition on the tonnage for the base table alone, so the `"OR"` promoted the join, which was outer already, and demoted the base table, which `promote_joins` and `demote_joins` leave as it is; it returned the base table as its vote to the `"AND"` above it, which demoted that alone. Then a second `filter`, an `"AND"` of one child that stands on the same join:

```text recording=sql
narrowed = either.filter(captain__signed_on__year=2011)
  Query.add_q(q_object=<Q: (AND: ('captain__signed_on__year', 2011))>)
    Query._add_q(<Q: (AND: ('captain__signed_on__year', 2011))>)
      JoinPromoter.__init__(connector='AND', num_children=1, negated=False)
      Query.join(Join(crew_sailor, from fleet_ship via Ship.captain, INNER JOIN, nullable))  ->  'crew_sailor'
      JoinPromoter.add_votes({'crew_sailor', 'fleet_ship'})
      JoinPromoter.update_join_types(a Query of Ship)
        Query.promote_joins(set())
        Query.demote_joins({'crew_sailor', 'fleet_ship'})
        -> {'crew_sailor', 'fleet_ship'}
    Query.demote_joins(set())
alias_map['fleet_ship']: BaseTable(fleet_ship), referenced 3
alias_map['crew_sailor']: Join(crew_sailor, from fleet_ship via Ship.captain, INNER JOIN, nullable), referenced 2
```

`join` reused the entry, and the one condition voted for it; under `"AND"` a vote is enough, and the join was demoted to inner. The comment in `update_join_types` gives this case, an `"OR"` followed by an `"AND"` on one of its relations, and says the demotion is right: if the relation produces no row, the second condition cannot be true, and the whole must be false. Last, the same `"OR"` negated:

```text recording=sql
neither = Ship.objects.filter(~(Q(captain__name='Cora') | Q(captain__name='Dag')))
  Query.add_q(q_object=<Q: (AND: (NOT (OR: ('captain__name', 'Cora'), ('captain__name', 'Dag'))))>)
    Query._add_q(<Q: (AND: (NOT (OR: ('captain__name', 'Cora'), ('captain__name', 'Dag'))))>)
      JoinPromoter.__init__(connector='AND', num_children=1, negated=False)
      Query._add_q(<Q: (NOT (OR: ('captain__name', 'Cora'), ('captain__name', 'Dag')))>)
        JoinPromoter.__init__(connector='OR', num_children=2, negated=True)
        Query.join(BaseTable(fleet_ship))  ->  'fleet_ship'
        Query.join(Join(crew_sailor, from fleet_ship via Ship.captain, INNER JOIN, nullable))  ->  'crew_sailor'
        JoinPromoter.add_votes(())
        Query.join(Join(crew_sailor, from fleet_ship via Ship.captain, INNER JOIN, nullable))  ->  'crew_sailor'
        JoinPromoter.add_votes(())
        JoinPromoter.update_join_types(a Query of Ship)
          Query.promote_joins(set())
          Query.demote_joins(set())
          -> set()
        -> ((NOT (OR: (AND: Exact(Col(crew_sailor, crew.Sailor.name), 'Cora'), IsNull(Col(crew_sailor, crew.Sailor.name), False)), (AND: Exact(Col(crew_sailor, crew.Sailor.name), 'Dag'), IsNull(Col(crew_sailor, crew.Sailor.name), False)))), set())
      JoinPromoter.add_votes(set())
      JoinPromoter.update_join_types(a Query of Ship)
        Query.promote_joins(set())
        Query.demote_joins(set())
        -> set()
    Query.demote_joins(set())
alias_map['fleet_ship']: BaseTable(fleet_ship), referenced 2
alias_map['crew_sailor']: Join(crew_sailor, from fleet_ship via Ship.captain, LEFT OUTER JOIN, nullable), referenced 2
```

The promoter of the negated `"OR"` has `"AND"` as its effective connector, and each child, being under a negation, voted for nothing and had an `"IS NOT NULL"` added to its clause; with no votes nothing was promoted or demoted, and the join stays outer, which is what the condition needs: a ship with no captain is neither Cora's nor Dag's, and must be kept.

```text figure=the-votes
Ship.objects.filter(Q(captain__name='Cora') | Q(tonnage__lt=500))           and then  .filter(captain__signed_on__year=2011)

join: crew_sailor hangs from fleet_ship along Ship.captain, nullable         ->  LEFT OUTER JOIN to start with

the OR node, 2 children                                                       the AND node of the second filter, 1 child
    captain__name='Cora'   votes  fleet_ship, crew_sailor                         captain__signed_on__year=2011   votes  fleet_ship, crew_sailor
    tonnage__lt=500        votes  fleet_ship
    crew_sailor  1 of 2    promote   (outer already)                              crew_sailor  1 of 1    demote   ->  INNER JOIN
    fleet_ship   2 of 2    demote    (the base table: left as it is)              fleet_ship   1 of 1    demote   (the base table)
    returns {fleet_ship} as its vote to the AND node around it
the AND node around it, 1 child: demotes fleet_ship                           add_q: demotes what was inner before: nothing
add_q: demotes what was inner before: nothing

alias_map after the first filter:  crew_sailor  LEFT OUTER JOIN, referenced 1
alias_map after the second:        crew_sailor  INNER JOIN, referenced 2
```

*The votes of two filters on one join. The `"OR"` promotes a join that not every child needs; the `"AND"` that follows demotes it, since its one condition cannot be true of a ship with no captain.*

**The rule to take away.** A join along a key that may not be null is never promoted on its own account: `promote_joins` makes a join outer only where it is nullable or the join it hangs from is outer. So an `"OR"` whose children do not share a join leaves such a join inner, and a sailor always has a ship; it does promote one that hangs from an outer join, since a row with no captain has no captain's ship either; and a join over a reverse relation, nullable, is left outer under such an `"OR"`. Asked of the statements:

```text recording=sql
tail(Sailor.objects.filter(Q(ship__home__name='Bergen') | Q(name='Dag')))  ->  ('FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE ("fleet_port"."name" = %s OR "crew_sailor"."name" = %s)', ('Bergen', 'Dag'))
tail(Ship.objects.filter(Q(captain__ship__name='Petrel') | Q(name='Gannet')))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") LEFT OUTER JOIN "fleet_ship" "T3" ON ("crew_sailor"."ship_id" = "T3"."id") WHERE ("T3"."name" = %s OR "fleet_ship"."name" = %s) ORDER BY "fleet_ship"."name" ASC', ('Petrel', 'Gannet'))
...
tail(Ship.objects.filter(Q(crew__name='Ada') | Q(tonnage__lt=500)))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") WHERE ("crew_sailor"."name" = %s OR "fleet_ship"."tonnage" < %s) ORDER BY "fleet_ship"."name" ASC', ('Ada', 500))
```

## Renaming aliases: `change_aliases` and `bump_prefix`

A query that is to stand inside another, as a subquery or as the right side of `combine`, must share no alias with it, and the two name their tables the same way. `Query.alias_prefix` is the letter new aliases take, `"T"` on the class, and `Query.subq_aliases` the set of letters in use between a query and those inside it, `{"T"}` to begin with. `Query.bump_prefix` is given the outer query and changes the inner query's prefix to a letter not in its own `subq_aliases`, and tells the outer query of it, so that each query in a nest has a prefix none of the others has (`django/db/models/sql/query.py:Query.bump_prefix`). Where the two prefixes already differ it does nothing. Otherwise it takes the first prefix after its own letter that is not in that set, from a generator defined inside the method that yields the letters after its own, then pairs of letters, and so on; past a sixteenth of Python's recursion limit it raises `RecursionError`, the comment saying the divider is how much depth a nested subquery adds to the stack. The letter is added to both queries' `subq_aliases`, and every alias of the map, except those the caller excludes, is renamed to the letter and the alias's position in the map. Here left and right are queries of voyages with one condition on their ports of call each, and bumped is a clone of right bumped against left with the base table excluded; each line is a question and its answer:

```text recording=sql
bump_prefix and change_aliases: the aliases of a query that is to stand inside another are renamed to a prefix the outer query does not use
    list(left.alias_map), list(right.alias_map), right.alias_prefix, sorted(right.subq_aliases)  ->  (['fleet_voyage', 'fleet_voyage_calls', 'fleet_port'], ['fleet_voyage', 'fleet_voyage_calls', 'fleet_port'], 'T', ['T'])
    list(bumped.alias_map), bumped.alias_prefix, sorted(bumped.subq_aliases), sorted(left.subq_aliases)  ->  (['fleet_voyage', 'U1', 'U2'], 'U', ['T', 'U'], ['T', 'U'])
    bumped.table_map, bumped.alias_refcount, said(bumped.where)  ->  ({'fleet_voyage': ['fleet_voyage'], 'fleet_voyage_calls': ['U1'], 'fleet_port': ['U2']}, {'fleet_voyage': 1, 'U1': 1, 'U2': 1}, (AND: Exact(Col(U2, fleet.Port.name), 'Lisbon')))
    list(right.relabeled_clone({'fleet_voyage_calls': 'C1', 'fleet_port': 'C2'}).alias_map), str(right.relabeled_clone({'fleet_voyage_calls': 'C1', 'fleet_port': 'C2'}).where)  ->  (['fleet_voyage', 'C1', 'C2'], "(AND: Exact(Col(C2, fleet.Port.name), 'Lisbon'))")
```

What is excluded is the caller's choice: `combine` excludes the base table, and the comment there says it must be present in the query on both sides; a query resolved as a subquery excludes nothing ([Two queries into one: `combine` and `get_combinator_sql`](combining.md), [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)).

`Query.change_aliases` does the renaming, given a mapping from old alias to new (`django/db/models/sql/query.py:Query.change_aliases`). It asserts that no alias is both a key and a value of the mapping, since an alias might otherwise be renamed twice, as the comment says. Then it relabels every place an alias is written: the where tree, through `WhereNode.relabel_aliases`, which has each lookup make a relabelled clone of itself; the grouping, where it is a tuple; the select; and the annotations (`django/db/models/sql/where.py:WhereNode.relabel_aliases`). The lookups go through copies, and the clones of the query, which share its lookups, are left as they were ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)). Then the map itself: each entry under an old alias is replaced by its `relabeled_clone` under the new, with its count moved and `table_map` corrected. Last it renames `Query.external_aliases`, the aliases of an outer query that a subquery refers to, marking each renamed one as aliased, and passes the part of the mapping that each combined query refers to down to it ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). `Query.relabeled_clone` is a clone with the renaming applied, as the last line of the recording above shows, and is what an expression's `relabeled_clone` does to a query it holds ([The query: what a `Query` holds, and how it is copied](query.md)).

## `get_from_clause`: the map written out

`SQLCompiler.get_from_clause` reads the map when the statement is written and returns the pieces of the `"FROM"` clause with their parameters: for each entry whose count is not zero, in the map's order, what `BaseTable.as_sql` or `Join.as_sql` writes (`django/db/models/sql/compiler.py:SQLCompiler.get_from_clause`). Its docstring says it must be called after everything that may add a table, the select, the ordering and the distinct, and `SQLCompiler.as_sql` calls it after those ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)). After the entries come the tables of `Query.extra_tables`, those a queryset's `extra` named: each is given an alias by `table_alias` without creating one, and appended after a comma, quoted, unless the table is already joined and written, which the method tells by a count above one; a join of the table that is in the map with a count of zero is written as a bare table this way (`django/db/models/sql/query.py:Query.add_extra`).

```text recording=sql
sql_of(Sailor.objects.extra(tables=['fleet_ship'], where=['fleet_ship.id = crew_sailor.ship_id']))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" , "fleet_ship" WHERE (fleet_ship.id = crew_sailor.ship_id)', ())
```

The extra table is written after a comma, with no `"ON"`, and the condition the program wrote against it is taken as it is ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)).
