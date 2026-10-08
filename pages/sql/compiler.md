---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The compiler: `as_sql`, `execute_sql` and `results_iter`

A `SQLCompiler` is made for one query and one connection when the rows are wanted. `SQLCompiler.as_sql` assembles the statement from the query's clauses, in an order that is not the statement's; `SQLCompiler.execute_sql` sends it on a cursor and returns rows, one row, a row count or the cursor itself; and `SQLCompiler.results_iter` hands each row on with its converters applied.

A `Query` knows no backend, and the compiler is where the backend enters. The connection's operations object supplies the compiler's class; every name the compiler writes goes through the backend's quoting; the SQL of a limit, a lock, a `"DISTINCT"` and an `"EXPLAIN"` is the operations object's, and what the backend can do is asked of its features object at each turn, so that one query is written one way for SQLite and another for PostgreSQL ([Database backends](../backends.md)). The compiler runs the statement once, on a cursor the connection gives it, and gives back what its caller asked for: the rows in chunks for an iteration, one row for an aggregate, the count of rows an update touched. And it leaves the query as it found it. Writing a statement joins tables the query did not have, for an ordering or a `select_related`, and counts references to the aliases it uses; before it returns, the compiler puts every count back, since the queryset may be evaluated again.

The compiler is empty until it has written its statement. Four of its attributes, the select list, `klass_info`, the map of annotations to columns and the count of columns, are filled by `as_sql` and read afterwards by whoever runs the statement: that is how the queryset's iterable knows which columns are whose ([From rows to instances: `ModelIterable` and `select_related`](../querysets/iterables.md)). The recordings below ran on SQLite. Where lines are nested they are calls as they were made, with only the calls the passage is about written down and `->` what each returned; where a line is a question, its answer follows `->`; and a line beginning `SQL` is a statement as Django handed it to its cursor.

## `get_compiler`: the backend supplies the class

`Query.get_compiler` takes the alias of a database or a connection, and refuses with `ValueError` when it is given neither; given the alias, it takes the connection for it from the connection handler. It then asks the connection's operations object for a class by the name the query carries in `Query.compiler`, which is `"SQLCompiler"` on `Query` itself and the name of another compiler on each subclass that writes another statement, and it makes one with the query, the connection, the alias and `elide_empty` (`django/db/models/sql/query.py:Query.get_compiler`, `django/db/models/sql/query.py:Query.compiler`). `BaseDatabaseOperations.compiler` imports the module named by `BaseDatabaseOperations.compiler_module` the first time it is asked, keeps it, and returns the attribute of that name; the base class names `django.db.models.sql.compiler`, and a backend that wants compilers of its own names another module, as MySQL's and PostgreSQL's operations do, which is why the query carries a name and not a class (`django/db/backends/base/operations.py:BaseDatabaseOperations.compiler`).

```text recording=sql
type(Ship.objects.all().query.get_compiler('default')).__name__, connection.ops.compiler_module, Query.compiler, UpdateQuery.compiler, InsertQuery.compiler, DeleteQuery.compiler, AggregateQuery.compiler  ->  ('SQLCompiler', 'django.db.models.sql.compiler', 'SQLCompiler', 'SQLUpdateCompiler', 'SQLInsertCompiler', 'SQLDeleteCompiler', 'SQLAggregateCompiler')
type(Ship.objects.all().query.get_compiler(connection=connection)).__name__, Ship.objects.all().query.get_compiler('default').using, Ship.objects.all().query.get_compiler(connection=connection).using  ->  ('SQLCompiler', 'default', None)
Ship.objects.all().query.get_compiler()  ->  raises ValueError: Need either using or connection
connection.ops.compiler('SQLCompiler').__module__, connection.ops.compiler('SQLInsertCompiler').__name__  ->  ('django.db.models.sql.compiler', 'SQLInsertCompiler')
```

A compiler made with a connection and no alias has `None` for `SQLCompiler.using`, as the second line shows. That is how a query standing inside another gets its compiler: `Query.as_sql` is handed the outer compiler's connection and asks for one from that alone ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)); the compiler of each part of a compound statement is made with the outer compiler's alias and connection both ([Two queries into one: `combine` and `get_combinator_sql`](combining.md)).

`SQLCompiler.__init__` keeps the four things it was given and sets `SQLCompiler.quote_cache` to a dictionary holding `"*"` only; then it sets `SQLCompiler.select`, `SQLCompiler.annotation_col_map`, `SQLCompiler.klass_info` and `SQLCompiler._meta_ordering` to `None` (`django/db/models/sql/compiler.py:SQLCompiler.__init__`). The comment at those lines says why the three are attributes at all: the select, the `klass_info` and the annotations are needed by the queryset's iteration, and are set as a side effect of executing the query. `SQLCompiler.elide_empty` is the one option: the comment says that some queries, a coalesced aggregation for one, have to be executed even where they would return no rows. `Query.get_aggregation` passes it as `False` where an aggregate has no answer of its own for no rows ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)), and `get_combinator_sql` turns it off on the compiler of an empty part that a sliced union has to keep ([Two queries into one: `combine` and `get_combinator_sql`](combining.md)). Here compiler is a compiler for the ships over a hundred tons, asked first what it holds before its statement is written:

```text recording=sql
compiler = Ship.objects.filter(tonnage__gt=100).query.get_compiler('default')
compiler.elide_empty, compiler.select, compiler.klass_info, compiler.annotation_col_map, compiler.quote_cache  ->  (True, None, None, None, {'*': '*'})
compiler.quote_name('name'), compiler.quote_name('*'), compiler.quote_name('name') is compiler.quote_name('name'), compiler.quote_cache  ->  ('"name"', '*', True, {'*': '*', 'name': '"name"'})
compiler.quote_name_unless_alias('name')  ->  '"name"'
  warns RemovedInDjango2028Warning: SQLCompiler.quote_name_unless_alias() is deprecated. Use .quote_name() instead.
repr(compiler)[:40]  ->  '<SQLCompiler model=Ship connection=<Data'
```

`SQLCompiler.quote_name` is a memo around the operations object's `quote_name`: a name already in `quote_cache` comes back from there, and any other is quoted once and kept (`django/db/models/sql/compiler.py:SQLCompiler.quote_name`). That is why asking twice returns the same string, as the question about `quote_name` shows. The quoting itself is the backend's: on SQLite, `DatabaseOperations.quote_name` wraps a name in double quotes unless it is already so wrapped (`django/db/backends/sqlite3/operations.py:DatabaseOperations.quote_name`), and the base class's raises `NotImplementedError`. A `Col` writes its alias and its column through the compiler's method ([Expressions: `resolve_expression` and `as_sql`](expressions.md)).

> **Deprecated.** `SQLCompiler.quote_name_unless_alias` warns with `RemovedInDjango2028Warning` and calls `quote_name` (`django/db/models/sql/compiler.py:SQLCompiler.quote_name_unless_alias`). The release notes of 6.1 deprecate it in favour of the newly introduced `quote_name`, naming the compiler as the object an expression's `as_sql` is handed (`docs/releases/6.1.txt`).

`SQLCompiler.compile` is how every node of the query is written. It looks on the node for a method whose name is `"as_"` followed by the connection's vendor, `as_sqlite` for SQLite, and calls that with the compiler and the connection; where there is none it calls the node's `as_sql` (`django/db/models/sql/compiler.py:SQLCompiler.compile`). The where tree, each lookup, each join and each selected expression is compiled through it, and a node compiles its children the same way, so a vendor's method is found at every depth; the pattern is told with the functions that use it most ([Transforms and database functions: `Transform` and `Func`](functions.md)). `SQLCompiler.__repr__` names the class, the model, the connection and the alias; the last line above is the first forty characters of one.

## `pre_sql_setup`: the clauses are settled before the statement is written

`SQLCompiler.setup_query` is the first thing `as_sql` does, through `pre_sql_setup`. Where every alias in the query's alias map has a count of zero, which is so of a query with no alias at all and of one whose counts have all been given back, it has `Query.get_initial_alias` join the base table, or count a reference to it again. Then it calls `get_select` and keeps what it returns as `select`, `klass_info` and `annotation_col_map`, and sets `SQLCompiler.col_count` to the length of the select list (`django/db/models/sql/compiler.py:SQLCompiler.setup_query`). What `get_select` decides, and what `klass_info` is, is [The SELECT clause: `get_select`, the select mask and `klass_info`](select.md).

`SQLCompiler.pre_sql_setup` then settles the rest, in an order its docstring does not give but the clauses demand (`django/db/models/sql/compiler.py:SQLCompiler.pre_sql_setup`). It has `get_order_by` resolve the ordering, which may join a table and may refer to a selected column by its position, so the select list has to exist first ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)). It has `WhereNode.split_having_qualify` divide the where tree into the conditions for `"WHERE"`, those that compare an aggregate and go to `"HAVING"`, and those on a window function, keeping the three as `SQLCompiler.where`, `SQLCompiler.having` and `SQLCompiler.qualify` ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md), [Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)). It has `get_extra_select` find the ordering columns a `"DISTINCT"` statement must select though nothing asked for them, and records whether there were any as `SQLCompiler.has_extra_select`. And last it has `get_group_by` write the grouping, which starts from the query's own grouping where it names one, adds the select list with those extra columns, then what the ordering refers to and what the having compares, and so needs all three settled. It returns the extra selects, the ordering and the grouping. Recorded for a query of the sailors whose ship's home port is Bergen and who signed on before 2020, ordered by the latest signing and limited to five, with the compiling of each column left out:

```text recording=sql
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
    -> ['"crew_sailor"."signed_on" DESC']
  WhereNode.split_having_qualify  ->  ((AND: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020)), None, None)
  SQLCompiler.get_extra_select  ->  []
  SQLCompiler.get_group_by  ->  []
  -> (extra_select of 0, order_by of 1, group_by of 0)
```

The ordering joined nothing new here, since the column is the base table's, but `find_ordering_name` took the query's initial alias, which counts one more reference to the base table, and set up the join path from it all the same; the last part of `as_sql` puts the counts back.

## `as_sql`: the statement assembled

`SQLCompiler.as_sql` takes two options, `with_limits=True` and `with_col_aliases=False`, and returns the statement and a tuple of its parameters (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). Its first act is to copy `Query.alias_refcount`, and everything after runs inside a `try` whose `finally` is `Query.reset_refcounts` to that copy: whatever the compiler joined or counted for the statement is uncounted again, and a join whose count falls to zero is not written the next time ([Tables and joins: the alias map and join promotion](joins.md)). After `pre_sql_setup` there are three roads. A query with a combinator, a union or its relatives, is refused with `NotSupportedError` unless the features object has `supports_select_union` or the flag for its operator, and is then written by `get_combinator_sql` ([Two queries into one: `combine` and `get_combinator_sql`](combining.md)). A query with a qualify part is written by `get_qualify_sql`, which wraps the statement in another and ends it with the ordering itself, so `as_sql` writes none at this level; the comment says the SQL standard is unclear on whether a derived table's ordering propagates, so it is repeated on the outermost statement ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)). The rest is the plain case, which does two things the other roads do not: it reads the alias map, once every step that may join a table has run, and it compiles the where tree and the having.

In the plain case `as_sql` first calls `get_distinct`, which resolves the fields of a `"DISTINCT ON"` and may join tables for them, and only then `get_from_clause`, whose docstring says it must be called after anything that might change the tables, the select columns, the ordering and the distinct among them: it reads the alias map and writes every entry that is still referenced, and the query's extra tables after them (`django/db/models/sql/compiler.py:SQLCompiler.get_from_clause`). Then it compiles the where tree. `EmptyResultSet` out of it, which a comparison with an empty list raises, is let through when `elide_empty` holds, so that nothing is sent, and otherwise becomes the predicate `"0 = 1"`; `FullResultSet`, which a condition that every row meets raises, leaves the clause out ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)). The having is compiled the same way, with only `FullResultSet` caught.

The parts are then put in a list, and the parameters in another in the same order, so that each `%s` meets its value. `"SELECT"` comes first, with what the operations object's `distinct_sql` returns after it where the query is distinct, which for the base class is `"DISTINCT"` alone and a `NotSupportedError` for fields (`django/db/backends/base/operations.py:BaseDatabaseOperations.distinct_sql`). Then the select list with the extra selects after it, each column as its SQL and, where it has an alias, `"AS"` and the alias quoted by the operations object. Then `"FROM"` and the from clause, or, where the query has no table, the features' `bare_select_suffix`, for a backend that cannot write a `"SELECT"` with no `"FROM"`. Then `"WHERE"` where there is one; `"GROUP BY"` where there is one, which is refused with `NotImplementedError` beside distinct fields, and which replaces an empty ordering with the operations object's `force_no_ordering` and drops the ordering where it was only the model's own default ordering ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md)); and `"HAVING"` where there is one, with the operations object's `force_group_by` before it where nothing grouped.

The lock is the clause the backend decides most: whether it is written at all, whether each of its four variants is allowed, and where it stands are each a feature flag, and its text is the operations object's. `Query.select_for_update` is written only where the features object has `BaseDatabaseFeatures.has_select_for_update`; where it has not, which is so of SQLite, the statement is written without a lock. Where it has, `as_sql` raises `TransactionManagementError` when the connection is in autocommit and supports transactions, with the message that the lock cannot be used outside a transaction; `NotSupportedError` when the query is sliced and the backend lacks `supports_select_for_update_with_limit`; and `NotSupportedError` for each of `Query.select_for_update_nowait`, `Query.select_for_update_skip_locked`, `Query.select_for_update_of` and `Query.select_for_no_key_update` whose feature the backend lacks, which the comment says is to prevent a possible deadlock. What survives goes to the operations object's `for_update_sql`, with the tables of an `"OF"` from `get_select_for_update_of_arguments` ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)), and the clause is placed after `"FROM"` where `for_update_after_from` says so, which its comment says is for MSSQL, and at the end of the statement otherwise (`django/db/backends/base/operations.py:BaseDatabaseOperations.for_update_sql`).

What follows is common to the three roads. Where the query has `Query.explain_info`, the operations object's `explain_query_prefix` is put at the front. `"ORDER BY"` follows, and where the query is compound and the features object has `requires_compound_order_by_subquery`, the whole is wrapped as `SELECT * FROM (...)` with the ordering outside. The limit is the operations object's `limit_offset_sql` of the query's two marks, written only where the query is sliced and the caller did not pass `with_limits=False` ([The query: what a `Query` holds, and how it is copied](query.md)). One more wrap stands at the end: where the query is a subquery and there were extra selects, the statement is wrapped as `SELECT ... FROM (...) subquery` with only the selected columns named, each relabelled to the alias `"subquery"`, because, the comment says, a subquery that combines `order_by` with `distinct` would otherwise have more columns than the expression on its left expects ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)).

Of the two options, `with_limits=False` has one caller in the tree, the qualify rewrite, which writes the inner statement without its limit and applies the limit outside. `with_col_aliases=True` gives every column that has no alias one of the form `"col1"`, `"col2"`, numbered in order among the columns that get one, so that a statement standing inside another can be referred to by column; `pre_sql_setup` is given it, or `True` for any compound query, and its callers are each part of a compound statement, the inner query of an `AggregateQuery` and the inner statement of the qualify rewrite. Asked of the compiler for the ships over a hundred tons:

```text recording=sql
compiler.as_sql()  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s ORDER BY "fleet_ship"."name" ASC', (100,))
compiler.as_sql(with_col_aliases=True)  ->  ('SELECT "fleet_ship"."id" AS "col1", "fleet_ship"."name" AS "col2", "fleet_ship"."tonnage" AS "col3", "fleet_ship"."home_id" AS "col4", "fleet_ship"."captain_id" AS "col5" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s ORDER BY "fleet_ship"."name" ASC', (100,))
compiler.as_sql(with_limits=False), Ship.objects.all()[:1].query.get_compiler('default').as_sql(with_limits=False)  ->  (('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s ORDER BY "fleet_ship"."name" ASC', (100,)), ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()))
compiler.select[0], compiler.col_count, compiler.klass_info, compiler.annotation_col_map, compiler.has_extra_select  ->  ((Col(fleet_ship, fleet.Ship.id), ('"fleet_ship"."id"', ()), None), 5, {'model': <class 'harbour.fleet.models.Ship'>, 'select_fields': [0, 1, 2, 3, 4]}, {}, False)
compiler.query.alias_refcount  ->  {'fleet_ship': 1}
```

The select list that `as_sql` left on the compiler holds, for each column, the expression, its SQL with its parameters and its alias; the count of references to the base table is as it was before the statement was written, which is what `reset_refcounts` in the `finally` is for. The order in which the pieces were made, beside the order they stand in:

```text figure=as-sql-assembly
the order as_sql makes the clauses                   the order the statement has them

 1  setup_query                                      [EXPLAIN]                       9
      get_select            the select list          SELECT                          1
 2  get_order_by            ORDER BY                 DISTINCT [ON]                   6
 3  split_having_qualify    WHERE from HAVING        the select list                 1
 4  get_extra_select        columns DISTINCT needs   the extra selects               4
 5  get_group_by            GROUP BY                 FROM     the alias map          7
 6  get_distinct            DISTINCT ON              [FOR UPDATE]  on some backends  8
 7  get_from_clause         FROM, after the joins    WHERE                           3, 8
 8  compile(where)          WHERE                    GROUP BY                        5
    compile(having)         HAVING                   HAVING                          3, 8
    for_update_sql          FOR UPDATE               ORDER BY                        2
 9  explain_query_prefix    EXPLAIN                  LIMIT, OFFSET                   9
    limit_offset_sql        LIMIT, OFFSET            [FOR UPDATE]                    8
10  reset_refcounts         the counts put back
```

*The clauses of a plain statement in the order `as_sql` makes them, on the left, and the order it writes them, on the right, each with the step that made it. The select list is settled first and the from clause read after every step that may join a table.*

## `execute_sql`: five kinds of result

`SQLCompiler.execute_sql` takes a result type, which is `MULTI` unless another is given and `NO_RESULTS` where `None` is given, and two options for reading in chunks (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`). It calls `as_sql`. An `EmptyResultSet` out of it, or an empty statement, is answered without the database: an empty iterator for `MULTI`, `None` for every other type, and nothing is sent. Otherwise it takes a cursor from the connection, `BaseDatabaseWrapper.chunked_cursor` when `chunked_fetch` was asked for and `BaseDatabaseWrapper.cursor` otherwise; the base class's `chunked_cursor` is `cursor`, and PostgreSQL's wrapper, which has server-side cursors, is the one that overrides it (`django/db/backends/base/base.py:BaseDatabaseWrapper.chunked_cursor`) ([Database backends](../backends.md)). It executes the statement with its parameters, and where that raises, closes the cursor before raising again; the comment says the close itself may fail for a server-side cursor, as when the connection is closed, and where it raises a `DatabaseError` the first exception is raised in its place. What happens next is the result type's.

| result type | what `execute_sql` returns | who asks for it |
|---|---|---|
| `MULTI` | the rows a chunk at a time: a list of lists, or the generator `cursor_iter` where the read is chunked and the features object has `can_use_chunked_reads` | `results_iter`, and through it the values iterables; `ModelIterable.__iter__`; `explain_query`; `SQLUpdateCompiler.pre_sql_setup` for the keys of an update |
| `SINGLE` | one row, the first the cursor gives, cut to `col_count`, or `None`; the cursor closed | `has_results`, `Query.get_aggregation`, `Q.check` |
| `ROW_COUNT` | the cursor's count of rows; the cursor closed | `QuerySet.update`, `QuerySet._update`, `QuerySet._raw_delete`, `DeleteQuery.do_query`, `SQLUpdateCompiler.execute_returning_sql` |
| `CURSOR` | the cursor, which the caller is to close | nothing in Django's tree |
| `NO_RESULTS` | `None`; the cursor closed | `UpdateQuery.update_batch` |

*The result types of `django/db/models/sql/constants.py`, what each returns, and the callers that pass each at the pin. The writing compilers' callers are told in [INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md).*

Asked of the compiler for the ships over a hundred tons, each line below sent the one statement, which is left out:

```text recording=sql
compiler.execute_sql()  ->  [[(2, 'Gannet', 1200, 2, 3), (1, 'Petrel', 480, 1, None)]]
compiler.execute_sql(SINGLE)  ->  (2, 'Gannet', 1200, 2, 3)
compiler.execute_sql(NO_RESULTS)  ->  None
compiler.execute_sql(ROW_COUNT)  ->  -1
type(compiler.execute_sql(CURSOR)).__name__  ->  'CursorWrapper'
type(compiler.execute_sql(MULTI, chunked_fetch=True)).__name__, connection.features.can_use_chunked_reads  ->  ('generator', True)
```

The row count is `-1` here: the cursor's count is what SQLite's driver reports, and for a select it reports that. The generator of the last line is `cursor_iter`, a function of the module: it asks the cursor for `chunk_size` rows at a time, until what comes back is the features' `empty_fetchmany_value`, and closes the cursor in a `finally` when the iteration ends or is abandoned (`django/db/models/sql/compiler.py:cursor_iter`). Where the compiler has extra selects, each row is cut to `col_count` on the way, so that the columns a `"DISTINCT"` needed for its ordering never reach the caller. Where the read is not chunked, or the features object lacks `can_use_chunked_reads`, `execute_sql` returns `list` of the generator, which the comment says is the same structure read whole into memory first.

```text recording=sql
Rows a chunk at a time: cursor_iter asks the cursor for chunk_size rows until none come back
    [len(chunk) for chunk in Logbook.objects.all().query.get_compiler('default').execute_sql(chunked_fetch=True)]  ->  [25]
      SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook"
    [len(chunk) for chunk in Logbook.objects.all().query.get_compiler('default').execute_sql(chunked_fetch=True, chunk_size=10)]  ->  [10, 10, 5]
      SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook"
    [len(chunk) for chunk in Logbook.objects.all().query.get_compiler('default').execute_sql()]  ->  [25]
      SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook"
    len(list(Logbook.objects.all().query.get_compiler('default').results_iter(chunked_fetch=True, chunk_size=10)))  ->  25
      SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook"
    connection.features.empty_fetchmany_value, connection.ops.compiler_module  ->  ([], 'django.db.models.sql.compiler')
```

The chunk size is `GET_ITERATOR_CHUNK_SIZE`, a hundred, unless the caller gives another; `QuerySet.iterator` gives two thousand where it was given none, and whether it asks for a chunked read depends on the database's settings ([Evaluation and the result cache](../querysets/evaluation.md)). The block below is the two kinds of empty: a query that can match nothing sends no statement and returns an empty list or `None`, and the same query compiled with `elide_empty=False` sends one with `"0 = 1"` for its where clause:

```text recording=sql
list(Ship.objects.filter(pk__in=[]).query.get_compiler('default').execute_sql()), Ship.objects.filter(pk__in=[]).query.get_compiler('default').execute_sql(SINGLE)  ->  ([], None)
Ship.objects.filter(pk__in=[]).query.get_compiler('default', elide_empty=False).execute_sql(SINGLE)  ->  None
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE 0 = 1 ORDER BY "fleet_ship"."name" ASC
compiler.has_results(), Ship.objects.filter(pk__in=[]).query.get_compiler('default').has_results()  ->  (True, False)
```

`SQLCompiler.has_results` is `bool` of `execute_sql(SINGLE)`; its docstring says a backend may override it with a faster way of asking whether a query has any rows, and no backend in the tree does (`django/db/models/sql/compiler.py:SQLCompiler.has_results`). `Query.has_results` makes the query that answers, through `Query.exists`, before asking its compiler ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)).

## `results_iter`: the rows with their converters applied

`SQLCompiler.results_iter` returns an iterator over the rows: a row is a list where a converter or a composite key was applied, a tuple where `tuple_expected=True` was asked, and otherwise what the cursor gave (`django/db/models/sql/compiler.py:SQLCompiler.results_iter`). It is given the result of `execute_sql` where the caller ran that itself, which `ModelIterable.__iter__` does so that it can read the compiler's select list and `klass_info` between the two, and otherwise calls `execute_sql(MULTI)` with the two chunking options. It takes the first `col_count` expressions of the select list as the columns, asks `get_converters` for their converters, flattens the chunks into rows, applies the converters where there are any, turns the columns of a composite primary key into one tuple where the list holds a `ColPairs`, and makes each row a tuple where `tuple_expected=True` was asked, which `ValuesListIterable` asks ([`values` and `values_list`: rows as dictionaries and tuples](../querysets/values.md)).

A **converter** is a function of a value, the expression and the connection that turns what the driver returned into what the program is to have. `SQLCompiler.get_converters` walks the expressions by position and collects, for each, the backend's converters followed by the expression's, keeping an entry only where there is at least one; a `ColPairs` counts for as many positions as it has columns, and each column's converters go under its own position (`django/db/models/sql/compiler.py:SQLCompiler.get_converters`). The backend's are the operations object's `get_db_converters` of the expression: the base class returns none, and SQLite's `DatabaseOperations.get_db_converters` adds one by the internal type of the expression's output field, for a datetime, a date, a time, a decimal, a UUID and a boolean (`django/db/backends/sqlite3/operations.py:DatabaseOperations.get_db_converters`). The expression's are `BaseExpression.get_db_converters`: its own `convert_value`, a function chosen by the output field's type that makes a `float`, an `int` or a `decimal.Decimal` of what came back, unless that is the no-op, and then the output field's own converters (`django/db/models/expressions.py:BaseExpression.get_db_converters`); a `Col` does not use `convert_value`: `Col.get_db_converters` returns its output field's converters, and its target field's after them where the output field is another field ([Expressions: `resolve_expression` and `as_sql`](expressions.md), [A field: the base class](../models/fields.md)). `SQLCompiler.apply_converters` makes a list of each row and, for each position that has converters, runs them in that order, the backend's first (`django/db/models/sql/compiler.py:SQLCompiler.apply_converters`).

Here typed is a compiler for the manifests of the office, annotated with the weight of a crate cast to a float, half the number of crates, and a datetime given as a `Value`. The statement selects the manifest's seven columns and then the three annotations, so the positions below count from the serial at nought to the datetime at nine; the last three lines each sent the one statement, which is left out:

```text recording=sql
converters_said(typed)  ->  {5: [DatabaseOperations.convert_booleanfield_value], 7: [BaseExpression.convert_value's lambda], 8: [BaseExpression.convert_value's lambda], 9: [DatabaseOperations.convert_datetimefield_value]}
[row for row in typed.results_iter()]  ->  [['M-0001', 1, 40, 25, 1000, False, '', 25.0, 20.0, datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.timezone.utc)]]
[type(v).__name__ for v in next(iter(typed.results_iter()))]  ->  ['str', 'int', 'int', 'int', 'int', 'bool', 'str', 'float', 'float', 'datetime']
[type(v).__name__ for v in next(iter(typed.execute_sql()))[0]]  ->  ['str', 'int', 'int', 'int', 'int', 'bool', 'str', 'float', 'float', 'str']
```

Four columns have converters. The boolean at position five has the backend's. The two floats have the function `convert_value` returns for a float output field: the cast was given that field, and the division infers it from an integer and a float ([Expressions: `resolve_expression` and `as_sql`](expressions.md)). The datetime at nine has the backend's, the `Value` having been given a datetime field for its output. The two lists of types are the row before and after: `execute_sql` hands the datetime on as the text SQLite stores, and `results_iter` as an aware `datetime`.

`SQLCompiler.composite_fields_to_tuples` is the last step, taken only where `has_composite_fields` finds a `ColPairs` among the columns: for each, the slice of the row that holds its columns is replaced by one value, the tuple of them, so that a Berth's key comes back as the pair of its port and its number in one cell (`django/db/models/sql/compiler.py:SQLCompiler.composite_fields_to_tuples`). What a `ColPairs` is, and how the key is compared, is [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](related-lookups.md).

## `explain_query` and `Query.explain`

`QuerySet.explain` passes its format and options to `Query.explain` with the queryset's database (`django/db/models/query.py:QuerySet.explain`). `Query.explain` clones the query, refuses with `ValueError` an option whose name does not match `EXPLAIN_OPTIONS_PATTERN`, a word of letters, digits, underscores and hyphens, or holds `"--"`, sets `Query.explain_info` on the clone to an `ExplainInfo` of the format and the options, and joins with newlines what the clone's compiler's `explain_query` yields (`django/db/models/sql/query.py:Query.explain`, `django/db/models/sql/query.py:EXPLAIN_OPTIONS_PATTERN`). Since the clone carries the mark, the query itself never does, and a clone made afterwards does not either, as the last line below shows.

`SQLCompiler.explain_query` runs `execute_sql` and reads every row; the comment says some backends return one-element tuples of strings and others tuples of integers and strings, so a row that is not a string is joined into one by spaces, each value through `json.dumps` where the format is JSON and `str` otherwise (`django/db/models/sql/compiler.py:SQLCompiler.explain_query`). The prefix is written by `as_sql`, which puts the operations object's `explain_query_prefix` at the front of the statement when the query carries an `explain_info`. The base class's refuses with `NotSupportedError` where the features object lacks `supports_explaining_query_execution`, which is whether the operations object has an `explain_prefix` at all; refuses a format with `ValueError` unless it is among the features' `supported_explain_formats`, with a message that lists them or says the backend has none; refuses any option the same way; and returns `BaseDatabaseOperations.explain_prefix`, which SQLite's operations set to `"EXPLAIN QUERY PLAN"` (`django/db/backends/base/operations.py:BaseDatabaseOperations.explain_query_prefix`). PostgreSQL's and MySQL's operations override the method ([Database backends](../backends.md)).

```text recording=sql
Ship.objects.filter(name='Petrel').explain()  ->  '4 0 63 SEARCH fleet_ship USING INDEX sqlite_autoindex_fleet_ship_2 (name=?)'
  SQL EXPLAIN QUERY PLAN SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s ORDER BY "fleet_ship"."name" ASC with params ('Petrel',)
...
Ship.objects.filter(name='Petrel').explain(format='json')  ->  raises ValueError: JSON is not a recognized format. SQLite does not support any formats.
Ship.objects.filter(name='Petrel').explain(**{'bad option': True})  ->  raises ValueError: Invalid option name: 'bad option'.
Ship.objects.filter(name='Petrel').query.explain_info, Ship.objects.filter(name='Petrel').query.clone().explain_info  ->  (None, None)
```

The text of the plan is SQLite's planner's, for one build of SQLite, and the rows came back as tuples of integers and a string, joined as the comment says.

## The other compilers

`SQLInsertCompiler`, `SQLUpdateCompiler` and `SQLDeleteCompiler` are subclasses that override `as_sql` for their statement and, the first two, `execute_sql` as well; each is made by the same `get_compiler` from the name its `Query` subclass carries, and [INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md) tells them. `SQLAggregateCompiler.as_sql` writes the selected annotations over an inner query compiled with column aliases, as `SELECT ... FROM (...) subquery`, and sets `col_count` to their number; it is the compiler of the `AggregateQuery` that `get_aggregation` makes where the aggregates cannot be put on the query itself (`django/db/models/sql/compiler.py:SQLAggregateCompiler.as_sql`) ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)). `PositionRef` is a `Ref` that writes a number, the position of a selected column; `SQLCompiler._order_by_pairs` orders by one where an ordering term names a selected expression or its alias ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)).
