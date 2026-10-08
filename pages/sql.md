---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: query, expressions, names, joins, where, lookups, related-lookups, functions, aggregates, subqueries, windows, compiler, select, ordering, grouping, combining, writing
---

# From QuerySet to SQL

A `Query` describes a statement as a tree of expressions: the tables it joins, the conditions of its where tree, and what it selects, groups and orders by. A `SQLCompiler` turns that description into one string of SQL with its parameters, sends it, and hands the rows back with their converters applied. This chapter is how a filter's name becomes joins and a comparison, what an expression, a lookup, a function and an aggregate write, and how the compiler assembles and runs the statement.

A queryset's methods do not write SQL. Each leaves something on an object the queryset carries, and nothing is SQL until the queryset is evaluated and asks for the rows. That object is the **query**, an instance of `Query`, and it is the first of the two things this chapter is about (`django/db/models/sql/query.py:Query`). The second is the **compiler**, an instance of `SQLCompiler` or of one of its subclasses, made for one query and one database connection when the rows are wanted, and thrown away with them (`django/db/models/sql/compiler.py:SQLCompiler`). The query is the description; the compiler is the writing and the running. [QuerySets](querysets.md) tells what the queryset's methods ask of the query and when the queryset asks for a compiler; this chapter begins where that one stops.

What the query holds is not SQL either. It is a set of Python objects that each know how to write their own piece: a `Col` for a column, a `Value` for a parameter, a `Func` for a function call, a `Lookup` for a comparison, a `WhereNode` for the conditions joined by `"AND"`, `"OR"` or `"XOR"`, a `Join` for a table joined to another. Each has the same two methods, and the whole chapter turns on them. `BaseExpression.resolve_expression` binds an object to a query: a name becomes a column of a table the query has joined, and whatever the object holds is bound in turn, so that a resolved object is a copy and the original is left as it was (`django/db/models/expressions.py:BaseExpression.resolve_expression`). `BaseExpression.as_sql` writes the SQL and parameters of a bound object, by compiling its parts and putting them into a template of its own; a backend may supply an `as_sqlite`, an `as_postgresql` or the like, and `SQLCompiler.compile` prefers the one for its connection's vendor (`django/db/models/expressions.py:BaseExpression.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.compile`). An **expression** in this chapter is any object with those two methods. A query is one itself: inside another query it is a subquery, and `Query` is built on `BaseExpression` for that reason.

The project is the shipping line of [Models and fields](models.md), which [QuerySets](querysets.md) records over too: ports, ships and voyages in the application fleet, sailors in crew, and the office's paperwork in office. The two applications most of this chapter's queries run over:

```python
# harbour/fleet/models.py
class Named(models.Model):
    name = models.CharField(max_length=60)

    class Meta:
        abstract = True
        ordering = ["name"]


class Port(Named):
    country = models.CharField(max_length=40)


class Ship(Named):
    tonnage = models.PositiveIntegerField()
    home = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ships")
    captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")


class Voyage(models.Model):
    ship = models.ForeignKey(Ship, on_delete=models.CASCADE)
    sailed = models.DateField()
    calls = models.ManyToManyField(Port)


# harbour/crew/models.py
class Sailor(models.Model):
    name = models.CharField(max_length=60)
    ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE, related_name="crew")
    signed_on = models.DateTimeField(auto_now_add=True)
    pilots_into = models.ManyToManyField("fleet.Port", through="office.Licence", related_name="pilots")


class Officer(Sailor):
    rank = models.CharField(max_length=10, choices=Rank)
```

Left out are the docstrings, the constraints and the index of a ship, the manager of a sailor and the choices of a rank. A port and a ship are ordered by name unless a queryset says otherwise, and a sailor has no ordering. The models of the office are shown where a section turns on one: a Berth, whose primary key is two columns, and a Manifest, with a column the database computes and another it defaults. The recordings were made in one run, which began with these rows:

```text recording=sql
The rows the recording begins with
    Port: 1 Bergen (Norway), 2 Leith (Scotland), 3 Lisbon (Portugal)
    Ship: 1 Petrel (480 tons, home Bergen, captain none), 2 Gannet (1200 tons, home Leith, captain Cora)
    Sailor: 1 Ada (ship Petrel, signed on 2011), 2 Bram (ship Petrel, signed on 2026), 3 Cora (ship Gannet, signed on 2011), 4 Dag (ship Gannet, signed on 2026)
    Officer: 3 Cora (master)
    Voyage: 1 (ship Petrel, sailed 2026-03-02, calls at Leith and Lisbon), 2 (ship Gannet, sailed 2025-10-06, calls at Bergen)
    Licence: 1 (Ada into Bergen)
    Berth: Bergen 1 (90 m), Bergen 2 (140 m)
    Logbook: 25, from 1 Log 1 to 25 Log 25
    Manifest: M-0001 (voyage 1, 40 crates of 25 kg, 1000 kg, stamped False)
```

The recordings ran on SQLite. In a recording, a line at the left is a line of Python as it was run; where it is an expression, its value follows `->`, or the word "raises" and the exception. The lines set in under it are the calls it set going, nested as they were made, with only the calls the passage is about written down, and `->` there is what a call returned, put into words as it was returned. A line that begins `SQL` is a statement as Django handed it to its cursor, with Django's `%s` for a parameter. An expression is written as its repr, which for most is the call that would make it; a where tree as `(AND: ...)`; a step of a path through the models as `PathInfo(from Sailor to Ship via Sailor.ship, direct, one)`; and an entry of the query's alias map as `Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable)`. What such a line shows of SQL's dialect is this backend's.

## Building: a filter becomes joins and a comparison

`QuerySet.filter` reduces its arguments to a `Q`, a tree of pairs of a name and a value, and hands it to `Query.add_q` ([`filter`, `exclude` and `Q` objects](querysets/filters.md)). Everything from there on is the query's. Here is one filter with two conditions, one across two relations and one with a transform and a lookup in its name:

```text recording=sql
bergen_veterans = Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020)
  QuerySet.filter(ship__home__name='Bergen', signed_on__year__lt=2020)
    QuerySet._filter_or_exclude_inplace(negate=False, args=(), kwargs={'ship__home__name': 'Bergen', 'signed_on__year__lt': 2020})
      Query.add_q(q_object=<Q: (AND: ('ship__home__name', 'Bergen'), ('signed_on__year__lt', 2020))>)
        Query._add_q(<Q: (AND: ('ship__home__name', 'Bergen'), ('signed_on__year__lt', 2020))>, used_aliases=set())
          JoinPromoter.__init__(connector='AND', num_children=2, negated=False)
          Query.build_filter(('ship__home__name', 'Bergen'), can_reuse=set())
            Query.solve_lookup_type(lookup='ship__home__name')
              Query.names_to_path(names=['ship', 'home', 'name'])  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], Port.name, (Port.name,), [])
              -> ([], ['ship', 'home', 'name'], False)
            Query.join(join=BaseTable(crew_sailor))
              Query.table_alias(table_name='crew_sailor', create=True)  ->  ('crew_sailor', True)
              -> 'crew_sailor'
            Query.setup_joins(names=['ship', 'home', 'name'], alias='crew_sailor', can_reuse=set())
              Query.names_to_path(names=['ship', 'home', 'name'], fail_on_missing=True)  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], Port.name, (Port.name,), [])
              Query.join(join=Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable))
                Query.table_alias(table_name='fleet_ship', create=True)  ->  ('fleet_ship', True)
                -> 'fleet_ship'
              Query.join(join=Join(fleet_port, from fleet_ship via Ship.home, INNER JOIN, not nullable))
                Query.table_alias(table_name='fleet_port', create=True)  ->  ('fleet_port', True)
                -> 'fleet_port'
              -> JoinInfo(final_field=Port.name, targets=(Port.name,), opts=the options of Port, joins=['crew_sailor', 'fleet_ship', 'fleet_port'], path=[PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)])
            Query.check_related_objects(field=Port.name, value='Bergen', opts=the options of Port)
            Query.trim_joins(targets=(Port.name,), joins=['crew_sailor', 'fleet_ship', 'fleet_port'], path=[PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)])  ->  ((Port.name,), 'fleet_port', ['crew_sailor', 'fleet_ship', 'fleet_port'])
            Query.build_lookup(lookups=[], lhs=Col(fleet_port, fleet.Port.name), rhs='Bergen')
              Exact.__init__(lhs=Col(fleet_port, fleet.Port.name), rhs='Bergen')  (Lookup.__init__)
                Exact.get_prep_lookup  (Lookup.get_prep_lookup)  ->  'Bergen'
              -> Exact(Col(fleet_port, fleet.Port.name), 'Bergen')
            -> ((AND: Exact(Col(fleet_port, fleet.Port.name), 'Bergen')), {'crew_sailor', 'fleet_port', 'fleet_ship'})
...
          Query.build_filter(('signed_on__year__lt', 2020), can_reuse={'crew_sailor', 'fleet_port', 'fleet_ship'})
            Query.solve_lookup_type(lookup='signed_on__year__lt')
              Query.names_to_path(names=['signed_on', 'year', 'lt'])  ->  ([], Sailor.signed_on, (Sailor.signed_on,), ['year', 'lt'])
              -> (['year', 'lt'], ['signed_on'], False)
            Query.resolve_lookup_value(value=2020, can_reuse={'crew_sailor', 'fleet_port', 'fleet_ship'}, allow_joins=True)  ->  2020
            Query.setup_joins(names=['signed_on'], alias='crew_sailor', can_reuse={'crew_sailor', 'fleet_port', 'fleet_ship'})
              Query.names_to_path(names=['signed_on'], fail_on_missing=True)  ->  ([], Sailor.signed_on, (Sailor.signed_on,), [])
              -> JoinInfo(final_field=Sailor.signed_on, targets=(Sailor.signed_on,), opts=the options of Sailor, joins=['crew_sailor'], path=[])
            Query.check_related_objects(field=Sailor.signed_on, value=2020, opts=the options of Sailor)
            Query.trim_joins(targets=(Sailor.signed_on,), joins=['crew_sailor'], path=[])  ->  ((Sailor.signed_on,), 'crew_sailor', ['crew_sailor'])
            Query.build_lookup(lookups=['year', 'lt'], lhs=Col(crew_sailor, crew.Sailor.signed_on), rhs=2020)
              Query.try_transform(lhs=Col(crew_sailor, crew.Sailor.signed_on), name='year', lookups=['year', 'lt'])  ->  ExtractYear(Col(crew_sailor, crew.Sailor.signed_on))
              YearLt.__init__(lhs=ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), rhs=2020)  (Lookup.__init__)
                YearLt.get_prep_lookup  (Lookup.get_prep_lookup)  ->  2020
              -> YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020)
            -> ((AND: YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020)), {'crew_sailor'})
...
          JoinPromoter.update_join_types(a Query of Sailor)
            Query.promote_joins(set())
            Query.demote_joins({'crew_sailor', 'fleet_port', 'fleet_ship'})
```

`Query.add_q` walks the `Q` with `Query._add_q`, which makes a `WhereNode` for the tree's node and calls `Query.build_filter` for each leaf (`django/db/models/sql/query.py:Query.add_q`, `django/db/models/sql/query.py:Query.build_filter`). For one pair, `build_filter` does three things in turn, and the three are the subjects of the next sections.

**The name is read against the models.** `Query.solve_lookup_type` splits it at each `"__"` and has `Query.names_to_path` walk the words as fields: `"ship"` is a foreign key of Sailor, `"home"` a foreign key of Ship, `"name"` a field of Port, and the walk stops at a word that is no field, leaving `["year", "lt"]` over for `"signed_on"`. What the walk returns is a **path**, one `PathInfo` for each relation crossed, each saying which models it joins, through which field, in which direction and whether it can reach more than one row (`django/db/models/sql/query.py:Query.names_to_path`, `django/db/models/query_utils.py:PathInfo`). `Query.setup_joins` turns the path into joins, and `Query.trim_joins` takes back any join at the end whose only use is a key the previous table already holds, which is why `filter(ship=petrel)` joins nothing and compares the column `"ship_id"` ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](sql/names.md)).

**The joins go into the alias map.** `Query.join` gives each `Join` an alias, the table's own name the first time a table appears and `T` with a number after that, and keeps it in `Query.alias_map` with a count of how many conditions and columns refer to it; a join made for a condition that is later dropped is left in the map with a count of zero and is not written (`django/db/models/sql/query.py:Query.join`, `django/db/models/sql/datastructures.py:Join`). A join starts as `"INNER JOIN"` unless the relation can have no row on the far side, a nullable foreign key or a reverse relation, in which case it starts as `"LEFT OUTER JOIN"`; and as the conditions are added a `JoinPromoter` counts, for each join, how many of a node's children need a row on the far side, and demotes the join to inner under an `"AND"` or promotes it to outer under an `"OR"` that not every child shares (`django/db/models/sql/query.py:JoinPromoter.update_join_types`). That is what the two conditions above did to the joins of the ship and the port, and [Tables and joins: the alias map and join promotion](sql/joins.md) has the rules.

**The words left over become a lookup.** `Query.build_lookup` takes every word but the last for a **transform**, an expression made of the column, and the last for a **lookup**, a comparison of the column, or of the transformed column, with the value: `"year"` finds `ExtractYear` in the registry of the datetime field, and `"lt"` finds `YearLt` in the registry of `ExtractYear` (`django/db/models/sql/query.py:Query.build_lookup`). The registry is told in [The lookup registry: `RegisterLookupMixin`](querysets/lookups.md); the classes it finds are this chapter's. A `Lookup` holds a left side and a right side, prepares the right side through the left side's field, and writes `"column = %s"` from the backend's table of operators ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](sql/lookups.md)); the comparisons registered on a relation and on a composite primary key are a few more ([Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](sql/related-lookups.md)). A transform is a `Func` with one argument that also has a registry of its own, and the database functions of `django.db.models.functions` are the same class with a template each ([Transforms and database functions: `Transform` and `Func`](sql/functions.md)).

The lookup is wrapped in a `WhereNode` of its own and added to the node of its `Q`. The tree the filter leaves is what the last line above shows, and `Query.where` holds it. A negation is kept on the node, and `build_filter` adds an `"IS NOT NULL"` beside a negated comparison of a nullable column so that the SQL agrees with Python's `not`; an exclude across a relation that can reach several rows is turned into a subquery under `"NOT EXISTS"`, since a negated join would exclude a ship for the one sailor whose name matches and keep it for the others ([The where clause: `build_filter`, `add_q` and `WhereNode`](sql/where.md)).

## What else the query is given

The other methods of the queryset leave other things on the query, and most of them are expressions too. An annotation is an expression resolved against the query and kept in `Query.annotations` under its alias; an aggregate among them sets `Query.group_by` ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](sql/aggregates.md), [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](sql/grouping.md)). A queryset given as a value, or a `Subquery` or an `Exists`, carries a query of its own, which is resolved against the outer one, with its aliases renamed so that the two do not collide and the outer query's columns reachable through `OuterRef` ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](sql/subqueries.md)). A `Window` is an expression whose function runs over a partition of the rows, and a filter on one cannot stand in a `"WHERE"`, so the compiler wraps the statement in another ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](sql/windows.md)). The ordering is kept as names and expressions and resolved only when the statement is written; `values` leaves the columns to select and their names; `defer` and `only` leave a set of field names to leave out or to keep. What a `Query` holds, how `Query.clone` copies it for the next method and what `Query.chain` resets, is [The query: what a `Query` holds, and how it is copied](sql/query.md).

An expression can be built without a query and used on several. `F("tonnage") + 1` is a `CombinedExpression` of an `F` and a `Value`; resolving it against a query of ships turns the `F` into a `Col` of the ships' table through `Query.resolve_ref`, and asks the pair of field types what type the sum is (`django/db/models/sql/query.py:Query.resolve_ref`). Two expressions built the same way are equal and hash alike, which is what lets the compiler notice that an ordering refers to a selected column. [Expressions: `resolve_expression` and `as_sql`](sql/expressions.md) is the protocol in full, with `F`, `Value`, `Col`, `Case` and the rest of `django/db/models/expressions.py`.

## Compiling: the compiler assembles the statement

When the queryset is evaluated, `Query.get_compiler` asks the connection's operations object for the class named by `Query.compiler`, `"SQLCompiler"` for a select, and makes one for the query and the connection (`django/db/models/sql/query.py:Query.get_compiler`, `django/db/backends/base/operations.py:BaseDatabaseOperations.compiler`). The compiler's `SQLCompiler.as_sql` is where the query becomes a string. The same query as above, ordered and limited, compiled:

```text recording=sql
compiler.as_sql()
  SQLCompiler.as_sql
    SQLCompiler.pre_sql_setup
      SQLCompiler.setup_query
        SQLCompiler.get_select
          SQLCompiler.get_default_columns  ->  [Col(crew_sailor, crew.Sailor.id), Col(crew_sailor, crew.Sailor.name), Col(crew_sailor, crew.Sailor.ship), Col(crew_sailor, crew.Sailor.signed_on)]
          -> (4 columns, klass_info for Sailor, {})
      SQLCompiler.get_order_by
        SQLCompiler._order_by_pairs
          SQLCompiler.find_ordering_name(name='-signed_on')
            Query.setup_joins(names=['signed_on'], alias='crew_sailor')  ->  JoinInfo(final_field=Sailor.signed_on, targets=(Sailor.signed_on,), opts=the options of Sailor, joins=['crew_sailor'], path=[])
            Query.trim_joins(targets=(Sailor.signed_on,), joins=['crew_sailor'], path=[])  ->  ((Sailor.signed_on,), 'crew_sailor', ['crew_sailor'])
            -> [OrderBy(Col(crew_sailor, crew.Sailor.signed_on), descending=True)]
        SQLCompiler.compile(OrderBy(Col(crew_sailor, crew.Sailor.signed_on), descending=True))
          OrderBy.as_sql
            -> ('"crew_sailor"."signed_on" DESC', ())
          -> ('"crew_sailor"."signed_on" DESC', ())
        -> ['"crew_sailor"."signed_on" DESC']
      WhereNode.split_having_qualify  ->  ((AND: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020)), None, None)
      SQLCompiler.get_extra_select  ->  []
      SQLCompiler.get_group_by  ->  []
      -> (extra_select of 0, order_by of 1, group_by of 0)
    SQLCompiler.get_distinct  ->  ([], [])
    SQLCompiler.get_from_clause
      SQLCompiler.compile(BaseTable(crew_sailor))
        BaseTable.as_sql  ->  ('"crew_sailor"', [])
        -> ('"crew_sailor"', [])
      SQLCompiler.compile(Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable))
        Join.as_sql
          -> ('INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id")', [])
        -> ('INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id")', [])
      SQLCompiler.compile(Join(fleet_port, from fleet_ship via Ship.home, INNER JOIN, not nullable))
        Join.as_sql
          -> ('INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id")', [])
        -> ('INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id")', [])
      -> (['"crew_sailor"', 'INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id")', 'INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id")'], [])
    SQLCompiler.compile((AND: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020)))
      WhereNode.as_sql
        SQLCompiler.compile(Exact(Col(fleet_port, fleet.Port.name), 'Bergen'))
          Exact.as_sql  (BuiltinLookup.as_sql)
            Exact.process_lhs  (BuiltinLookup.process_lhs)
              Exact.process_lhs  (Lookup.process_lhs)
                -> ('"fleet_port"."name"', ())
              -> ('"fleet_port"."name"', ())
            Exact.process_rhs  (Lookup.process_rhs)  ->  ('%s', ['Bergen'])
            -> ('"fleet_port"."name" = %s', ('Bergen',))
          -> ('"fleet_port"."name" = %s', ('Bergen',))
        SQLCompiler.compile(YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020))
          YearLt.as_sql  (YearLookup.as_sql)
            YearLt.process_lhs(lhs=Col(crew_sailor, crew.Sailor.signed_on))  (BuiltinLookup.process_lhs)
              YearLt.process_lhs(lhs=Col(crew_sailor, crew.Sailor.signed_on))  (Lookup.process_lhs)
                -> ('"crew_sailor"."signed_on"', ())
              -> ('"crew_sailor"."signed_on"', ())
            YearLt.process_rhs  (Lookup.process_rhs)  ->  ('%s', [2020])
            -> ('"crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
          -> ('"crew_sailor"."signed_on" < %s', ('2020-01-01 00:00:00',))
        -> ('("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s)', ['Bergen', '2020-01-01 00:00:00'])
      -> ('("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s)', ['Bergen', '2020-01-01 00:00:00'])
    BaseDatabaseOperations.limit_offset_sql(low_mark=0, high_mark=5)  ->  'LIMIT 5'
    Query.reset_refcounts({'crew_sailor': 2, 'fleet_ship': 1, 'fleet_port': 1})
    -> ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE ("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s) ORDER BY "crew_sailor"."signed_on" DESC LIMIT 5', ('Bergen', '2020-01-01 00:00:00'))
```

The clauses are made in an order that is not the statement's. `SQLCompiler.pre_sql_setup` first has `SQLCompiler.get_select` settle the columns, every concrete field of the model where nothing narrows them, then has `SQLCompiler.get_order_by` resolve the ordering, which may join a table of its own and which `get_group_by` has to see, then splits the where tree into the conditions that go into `"WHERE"` and those that compare an aggregate and go into `"HAVING"`, and then has `SQLCompiler.get_group_by` write the grouping (`django/db/models/sql/compiler.py:SQLCompiler.pre_sql_setup`). Only after that does `as_sql` read the alias map for the `"FROM"` clause, since the select and the ordering may have added joins, compile the where tree, and put the pieces together as `"SELECT"`, `"FROM"`, `"WHERE"`, `"GROUP BY"`, `"HAVING"`, `"ORDER BY"` and the limit, gathering the parameters in the same order so that each `%s` meets its value (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). On the way out it puts back the reference counts of the aliases as they were, since writing the statement joined tables for the ordering that the query did not have before. [The compiler: `as_sql`, `execute_sql` and `results_iter`](sql/compiler.md) tells the assembly; [The SELECT clause: `get_select`, the select mask and `klass_info`](sql/select.md), [ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](sql/ordering.md) and [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](sql/grouping.md) tell the clauses.

Each node writes its own SQL. `SQLCompiler.compile` calls a node's `as_sql`, or its method for the connection's vendor where it has one, and a node compiles its children the same way: the where tree compiles each lookup, a lookup compiles its left side and prepares its right, and a `Col` writes its alias and column, quoted by the backend (`django/db/models/sql/where.py:WhereNode.as_sql`, `django/db/models/lookups.py:BuiltinLookup.as_sql`). The year comparison is the one surprise in the statement above: `YearLt` compares the column itself with the first day of the year, not the year extracted from it, so that an index on the column can serve (`django/db/models/lookups.py:YearLookup.as_sql`).

```text figure=from-filter-to-statement
building, on the Query                                    compiling, in the SQLCompiler

QuerySet.filter(ship__home__name='Bergen')                QuerySet is evaluated
  Query.add_q                                               Query.get_compiler -> a SQLCompiler
    Query.build_filter, for each name and value             SQLCompiler.as_sql
      names_to_path:  ship, home, name -> a path              pre_sql_setup
      setup_joins:    the path -> Join, Join                    get_select            SELECT ...
      trim_joins:     a join not needed is unreferenced         get_order_by          ORDER BY ...
      build_lookup:   the words left -> transforms, a Lookup    split_having_qualify  WHERE from HAVING
    JoinPromoter:     each join INNER or LEFT OUTER             get_group_by          GROUP BY ...
                                                              get_from_clause   FROM, the alias map
the query holds:                                              compile(where)    WHERE, each Lookup.as_sql
  alias_map  the joins                                    the statement and its parameters:
  where      the where tree of lookups                      SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY, the limit
  and what the queryset's other methods leave:            SQLCompiler.execute_sql: runs it on a cursor
  annotations, select, order_by, group_by,                SQLCompiler.results_iter: the rows, converters applied
  low_mark, high_mark
```

*The two halves of the way from a filter to a statement. On the left, what one call of `filter` leaves on the query; on the right, what the compiler does with it when the queryset is evaluated. The query is kept from one method to the next; the compiler is made when the rows are wanted and reads the query once.*

## Running: `execute_sql` and the rows

`SQLCompiler.execute_sql` calls `as_sql`, takes a cursor from the connection, runs the statement, and returns what the caller asked for: the rows a chunk at a time for an iteration, one row for an aggregate, the row count for an update, the cursor itself, or nothing (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`). Where the where tree can match nothing, which a comparison with an empty list makes it, `as_sql` raises `EmptyResultSet`, and `execute_sql` answers with no rows and sends nothing. `SQLCompiler.results_iter` reads the rows and applies to each column its **converters**, the functions the backend and the column's field or expression supply for turning what the driver returned into what the program is to have: a datetime from the text SQLite stores, a `bool` from an integer, a `float` from an expression cast to one (`django/db/models/sql/compiler.py:SQLCompiler.results_iter`, `django/db/models/sql/compiler.py:SQLCompiler.get_converters`). The rows go to the queryset's iterable class, which makes instances of them with the compiler's `klass_info` saying which columns are whose ([From rows to instances: `ModelIterable` and `select_related`](querysets/iterables.md)).

```text recording=sql
rows = list(compiler.results_iter())
  SQLCompiler.results_iter
    SQLCompiler.execute_sql
      SQLCompiler.as_sql  (as above)  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE ("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s) ORDER BY "crew_sailor"."signed_on" DESC LIMIT 5', ('Bergen', '2020-01-01 00:00:00'))
      CursorWrapper.execute
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE ("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s) ORDER BY "crew_sailor"."signed_on" DESC LIMIT 5 with params ('Bergen', '2020-01-01 00:00:00')
    SQLCompiler.get_converters  ->  {3: [DatabaseOperations.convert_datetimefield_value]}
  SQLCompiler.apply_converters
rows  ->  [[1, 'Ada', 1, datetime.datetime(2011, 6, 1, 8, 0, tzinfo=datetime.timezone.utc)]]
```

## The other statements

Two queries can be made one. The operators `&` and `|` of a queryset call `Query.combine`, which brings the right side's joins into the left side's alias map, making them afresh under an `"AND"` and reusing them under an `"OR"`, and adds its where tree under the connector; `union` and its relatives keep the queries side by side, and `SQLCompiler.get_combinator_sql` compiles each with a compiler of its own and joins the statements with the operator ([Two queries into one: `combine` and `get_combinator_sql`](sql/combining.md)). An aggregate asked of a queryset goes through `Query.get_aggregation`, which makes the aggregates the query's only selected annotations, or wraps the query as a subquery where it is sliced, distinct or grouped already ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](sql/aggregates.md)).

An insert, an update and a delete have a `Query` subclass each, `InsertQuery`, `UpdateQuery` and `DeleteQuery`, and a compiler each (`django/db/models/sql/compiler.py:SQLInsertCompiler`, `django/db/models/sql/compiler.py:SQLUpdateCompiler`, `django/db/models/sql/compiler.py:SQLDeleteCompiler`). `SQLInsertCompiler.as_sql` takes each field's value from each instance through the field's `pre_save` and prepares it, writes one `"VALUES"` list for all the rows where the backend can take one, and asks for the key back with `"RETURNING"` where it can. `SQLUpdateCompiler.as_sql` writes a `"SET"` of prepared values and compiled expressions, and where the filter joins another table, moves the joins into a subquery on the primary key first. `SQLDeleteCompiler.as_sql` does the same for a delete ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](sql/writing.md)).

## The neighbours

The query is built from the model's `_meta`: `names_to_path` asks the options for a field by name, a relation field for its path, and a child model for the path to its parent ([The options](models/options.md), [Relations](models/relations.md), [Inheritance: abstract bases, parents with tables and proxies](models/inheritance.md)). A lookup prepares its value through the field's `get_prep_value` and `get_db_prep_value`, and the field's converters are its own ([A field, the base class](models/fields.md)). The registry a word is looked up in is `RegisterLookupMixin`, which [QuerySets](querysets.md) tells.

The compiler leans on the connection at every turn, and that is [Database backends](backends.md): the operations object supplies the compiler class, the quoting of a name, the table of operators a `BuiltinLookup` writes from, the SQL of a limit, of `"DISTINCT ON"` and of `"FOR UPDATE"`, and the converters of a column's type; the features object says what the backend can do, from a `"RETURNING"` clause to a tuple comparison, and a statement is written one way or another by it; and the cursor the compiler runs the statement on is the connection's. The lookups and transforms of `django.contrib.postgres`, of a `JSONField` and of a geometry are built on the classes here (`django/db/models/fields/json.py:JSONField`), and [Content types, static files and the other contrib apps](contrib.md) has them.
