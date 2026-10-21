---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: compiler, select, ordering, grouping, aggregation, qualify, compound, writing
---

# The SQL compiler

A `SQLCompiler` turns a query into one string of SQL with its parameters, sends it, and hands the rows back with their converters applied. It settles the clauses in the order they depend on one another and writes them in the order SQL wants, and where one `"SELECT"` cannot say what a queryset asks, it writes more than one, side by side or one inside another.

A query describes a statement and does not hold its SQL ([Building a query](query.md)). The **compiler** is what writes it: an instance of `SQLCompiler` or of one of its subclasses, made for one query and one database connection (`django/db/models/sql/compiler.py:SQLCompiler`). The query is the description; the compiler is the writing and the running. Writing is more than putting the query's parts into the order of a `"SELECT"`. The parts depend on one another in another order: the ordering and the grouping refer to the selected columns, the ordering may join a table the filter did not, and the `"FROM"` clause can be written only when every step that may join has run. The query keeps the least that must be grouped by, and the compiler widens it to what the statement's other clauses need and narrows it to what the backend accepts ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](sql/grouping.md)). And some of what a queryset asks cannot be said in one `"SELECT"` at all: an aggregate over a sliced query, a filter on a window. For both the compiler writes one statement inside another.

The project is harbour, whose models [Models and fields](models.md) lists: ports, ships and voyages in the application fleet, sailors in crew, and the office's paperwork in office. A port and a ship are ordered by name unless a queryset says otherwise, and a sailor has no ordering; a Veteran is a sailor who signed on before 2020, by its manager's filter. The recordings were made in one run, which began with these rows:

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

The recordings ran on SQLite. In a recording, a line at the left is a line of Python as it was run, or the title of its block; a line's value, where it is shown, follows `->`, or the word "raises" and the exception. The lines set in under a line of Python are the calls it set going, nested as they were made, with only the calls the passage is about written down, and `->` there is what a call returned, put into words as it was returned. A name in parentheses after a call is the class that declares the method, where the object's own class does not. A line of three dots stands for lines of the block left out. A line that begins `SQL` is a statement as Django handed it to its cursor, with Django's `%s` for a parameter, and what such a line shows of SQL's dialect is this backend's. Some lines of the sections ask through helpers of the recording's own: a line beginning sql_of( answers with a queryset's statement and its parameters, tail( with the statement from its FROM on and the parameters after the select list's, and said( with an object in a few words.

## What the compiler is given

The compiler is given a query that a queryset's methods have written, and here it is the query of the sailors whose ship's home port is Bergen and who signed on before 2020, the filter of [Building a query](query.md), ordered by the date each sailor signed on, latest first, and limited to five rows. The filter's names have been walked through the models into joins, kept in the query's alias map as a tree from the sailors' table through the ships' to the ports', each join an `"INNER JOIN"`, as it was made and as the vote of the two conditions left it; the two conditions have become two lookups, an `Exact` and a `YearLt`, in the query's where tree; and the ordering is still a name, `"-signed_on"`, and the limit two numbers ([Building a query](query.md)). Every node the query holds writes its own SQL, through its `as_sql` or the method for the connection's vendor, so the compiler's work is to decide what goes into each clause and in what order the clauses are made, and to have each node write its piece ([Expressions, lookups and functions](expressions.md)).

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

The clauses are made in an order that is not the statement's. `SQLCompiler.pre_sql_setup` first has `SQLCompiler.get_select` settle the columns, every concrete field of the model where nothing narrows them, then has `SQLCompiler.get_order_by` resolve the ordering, which may join a table of its own and which `get_group_by` has to see, then splits the where tree into the conditions that go into `"WHERE"`, those that compare an aggregate and go into `"HAVING"`, and those that compare a window function, which are left for a statement wrapped round this one ([The QUALIFY rewrite: a filter on a window](sql/qualify.md)), and then has `SQLCompiler.get_group_by` write the grouping (`django/db/models/sql/compiler.py:SQLCompiler.pre_sql_setup`). Only after that does `as_sql` read the alias map for the `"FROM"` clause, since the select and the ordering may have added joins, compile the where tree, and put the pieces together as `"SELECT"`, `"FROM"`, `"WHERE"`, `"GROUP BY"`, `"HAVING"`, `"ORDER BY"` and the limit, gathering the parameters in the same order so that each `%s` meets its value (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). On the way out it puts back the reference counts of the aliases as they were, since resolving the ordering counts the tables it walks and may join one the query did not have before. [The compiler: `as_sql`, `execute_sql` and `results_iter`](sql/compiler.md) tells the assembly; [The SELECT clause: `get_select`, the select mask and `klass_info`](sql/select.md), [ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](sql/ordering.md) and [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](sql/grouping.md) tell the clauses.

Each node writes its own SQL. `SQLCompiler.compile` calls a node's `as_sql`, or its method for the connection's vendor where it has one, and a node compiles its children the same way: the where tree compiles each lookup, a lookup compiles its left side and prepares its right, and a `Col` writes its alias and column, quoted by the backend (`django/db/models/sql/where.py:WhereNode.as_sql`, `django/db/models/lookups.py:BuiltinLookup.as_sql`). Why `YearLt` wrote the column and a date, and not the year, is told with the lookups in [Expressions, lookups and functions](expressions.md).

```text figure=from-filter-to-statement
building, on the Query                                    compiling, in the SQLCompiler

QuerySet.filter(ship__home__name='Bergen')                QuerySet is evaluated
  the name, walked through the models -> Join, Join         Query.get_compiler -> a SQLCompiler
  the name and the value -> a Lookup                        SQLCompiler.as_sql
                                                              pre_sql_setup
the query holds:                                                get_select            SELECT ...
  alias_map  the joins                                          get_order_by          ORDER BY ...
  where      the where tree of lookups                          split_having_qualify  WHERE from HAVING
  and what the queryset's other methods leave:                  get_group_by          GROUP BY ...
  the ordering, still a name; the limit, two numbers          get_from_clause   FROM, the alias map
                                                              compile(where)    WHERE, each Lookup.as_sql
                                                          the statement and its parameters:
                                                            SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY, the limit
                                                          SQLCompiler.execute_sql: runs it on a cursor
                                                          SQLCompiler.results_iter: the rows, converters applied
```

*The two halves of the way from a filter to a statement. On the left, what a queryset's methods leave on the query; on the right, what the compiler does with it when the queryset is evaluated.*

## Running: `execute_sql` and the rows

`SQLCompiler.execute_sql` calls `as_sql`, takes a cursor from the connection, runs the statement, and returns what the caller asked for: the rows a chunk at a time for an iteration, one row for an aggregate, the row count for an update, the cursor itself, or nothing (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`). Where the where tree can match nothing, which a comparison with an empty list makes it, `as_sql` raises `EmptyResultSet`, and `execute_sql` answers with no rows and sends nothing. `SQLCompiler.results_iter` reads the rows and applies to each column its **converters**, the functions the backend and the column's field or expression supply for turning what the driver returned into what the program is to have: a datetime from the text SQLite stores, a `bool` from an integer, a `float` from an expression cast to one (`django/db/models/sql/compiler.py:SQLCompiler.results_iter`, `django/db/models/sql/compiler.py:SQLCompiler.get_converters`). The rows go to the queryset's iterable class; `ModelIterable` makes instances of them, with the compiler's `klass_info` saying which columns are whose ([From rows to instances: `ModelIterable`](querysets/rows.md)).

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

Where one `"SELECT"` cannot say what the queryset asks, the compiler writes more than one. An aggregate asked of a queryset goes through `Query.get_aggregation`, which makes the aggregates the query's only selected annotations, or wraps the query as a subquery where it is sliced, distinct, combined or grouped already, and in a few cases more ([Aggregating a query: `Query.get_aggregation`](sql/aggregation.md)). A filter on a window is tested in a statement wrapped round the one that computes it ([The QUALIFY rewrite: a filter on a window](sql/qualify.md)). And `union` and its relatives keep the queries side by side, which `SQLCompiler.get_combinator_sql` compiles each with a compiler of its own and joins with the operator ([Compound statements: `get_combinator_sql`](sql/compound.md)); the operators `&` and `|` of a queryset make one query of two before any compiler is made ([Merging two queries: `Query.combine`](query/combine.md)).

An insert, an update and a delete have a `Query` subclass each, `InsertQuery`, `UpdateQuery` and `DeleteQuery`, and a compiler each (`django/db/models/sql/compiler.py:SQLInsertCompiler`, `django/db/models/sql/compiler.py:SQLUpdateCompiler`, `django/db/models/sql/compiler.py:SQLDeleteCompiler`). `SQLInsertCompiler.as_sql` takes each field's value from each instance through the field's `pre_save` and prepares it, writes one `"VALUES"` list for all the rows where the backend can take one, and asks for the columns the database fills in, an automatic key among them, back with `"RETURNING"` where it can. `SQLUpdateCompiler.as_sql` writes a `"SET"` of prepared values and compiled expressions, and where the filter joins another table, moves the joins into a subquery on the primary key first, or, where the backend cannot select from the table it is updating or the update reaches a parent's table too, into a select that is run beforehand and whose keys the update then names. `SQLDeleteCompiler.as_sql` moves a delete's joins into a subquery in the same way ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](sql/writing.md)).

## The neighbours

The query the compiler reads is built by a queryset's methods, from the model's `_meta` ([Building a query](query.md), [QuerySets](querysets.md)), and every node in it writes its own SQL ([Expressions, lookups and functions](expressions.md)). The rows the compiler hands back go to the queryset's iterable class, which decides what each row becomes ([QuerySets](querysets.md)); the inserts, updates and deletes that a save and a delete send are written by the insert, update and delete compilers, for [An instance and its row](instance.md).

The compiler leans on the connection at every turn. The operations object supplies the compiler class, the quoting of a name, the SQL of a limit, of `"DISTINCT ON"` and of `"FOR UPDATE"`, and the converters of a column's type; the connection itself holds the table of operators a `BuiltinLookup` writes from; and the features object says what the backend can do, from a `"RETURNING"` clause to a tuple comparison, and a statement is written one way or another by it ([Database backends](backends.md)). The cursor the compiler runs the statement on is the connection's ([Connections and transactions](connections.md)).
