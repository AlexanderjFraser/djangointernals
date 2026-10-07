---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Evaluation and the result cache

A queryset is evaluated the first time it is iterated or asked its length or its truth: `QuerySet._fetch_all` sends its statement and keeps the list of what came back as `QuerySet._result_cache`. Later uses read the list; a narrower question put to a queryset that has no list, an index, `QuerySet.count`, `QuerySet.exists`, is answered without evaluating it; and `QuerySet.iterator` reads rows without keeping them.

Two costs pull against each other here. A queryset that is used twice, tested for emptiness and then looped over, should not send its statement twice, so the rows have to be kept. But keeping them means that every row of the result is in memory as an instance for as long as the queryset is, and a question such as how many rows there are should not need that. Django's answer has three parts. An evaluation is whole: the first use that needs the rows fetches all of them and makes the list. A narrower question put to a queryset that has not been evaluated is answered by a narrower statement, and leaves the queryset as it was. And for a result too large to keep there is a method that reads it once and keeps nothing.

## `_fetch_all`

`QuerySet._fetch_all` does two things. Where there is no result cache it makes an instance of the queryset's iterable class, handing it the queryset, and stores the list of everything that instance yields. Then, where the queryset has prefetch lookups and its `QuerySet._prefetch_done` is not yet true, it follows them, which sets it (`django/db/models/query.py:QuerySet._fetch_all`). The Python protocols of the class call it: `QuerySet.__iter__` calls it and returns an iterator over the list, and `QuerySet.__len__` and `QuerySet.__bool__` call it and return the list's length and its truth.

The recordings on this page were made from a running Django, on SQLite, over the rows that the chapter's opening page, [QuerySets](../querysets.md), lists: the lines set in are calls, nested as they were made, `->` is what a call or an expression returned, and a line that begins `SQL` is a statement as Django handed it to its cursor. The queryset called named is the crew of the Petrel in order of name.

```text recording=querysets
for sailor in named: seen(sailor)
  QuerySet.__iter__
    QuerySet._fetch_all  (there is no result cache)
      ModelIterable.__iter__
        Query.get_compiler(using='default')
        SQLCompiler.execute_sql
          SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "crew_sailor"."name" ASC with params (1,)
          the cursor's fetchmany(100)  ->  2 rows
          the cursor's fetchmany(100)  ->  0 rows
        SQLCompiler.results_iter
        Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [1, 'Ada', 1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
        Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [2, 'Bram', 1, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
```

The iterable is where the query is run, and how it turns a row into an instance is told in [From rows to instances: `ModelIterable` and `select_related`](iterables.md). What matters here is the order. `SQLCompiler.execute_sql` sent the statement and then read every row from the cursor, a hundred at a call until a call returned none, before it returned; both instances were made; and only then did the loop's body run for the first time (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`). The hundred is `GET_ITERATOR_CHUNK_SIZE`, the number of rows asked of the cursor at once, and has no bearing on how many are fetched in all.

## What the cache answers, and what a queryset answers without one

With a result cache, these uses of a queryset read the list:

```text recording=querysets
len(named)
  QuerySet.__len__
    QuerySet._fetch_all  (the result cache is filled)
    -> 2
bool(named)
  QuerySet.__bool__
    QuerySet._fetch_all  (the result cache is filled)
    -> True
named[0]
  QuerySet.__getitem__(0)  ->  <Sailor: Ada>
named.count()
  QuerySet.count  ->  2
named.exists()
  QuerySet.exists  ->  True
named.contains(dag)
  QuerySet.contains(<Sailor: Dag>)  ->  False
for hand in named: seen(hand)
  QuerySet.__iter__
    QuerySet._fetch_all  (the result cache is filled)
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
```

An index is an index into the list, and `QuerySet.count`, `QuerySet.exists` and `QuerySet.contains` are its length, its truth and a membership test. No statement was sent for any of them.

Without a result cache the same uses divide. Iteration, `len` and `bool` evaluate the queryset, as above. The others are each answered without evaluating the queryset, on a clone or on a copy of the query. Here fresh is another queryset of the same crew:

```text recording=querysets
fresh.count()
  QuerySet.count
    Query.get_count('default')
      Query.get_compiler(using='default')
      SQLCompiler.execute_sql(result_type='single')
        SQL SELECT COUNT(*) AS "__count" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s with params (1,)
        the cursor's fetchone()  ->  a row
      -> 2
    -> 2
fresh.exists()
  QuerySet.exists
    Query.has_results('default')
      Query.set_limits(high=1)
      Query.get_compiler(using='default')
      SQLCompiler.execute_sql(result_type='single')
        SQL SELECT %s AS "a" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s LIMIT 1 with params (1, 1)
        the cursor's fetchone()  ->  a row
      -> True
    -> True
fresh.contains(dag)
  QuerySet.contains(<Sailor: Dag>)
    QuerySet.exists
      Query.has_results('default')
        Query.set_limits(high=1)
        Query.get_compiler(using='default')
        SQLCompiler.execute_sql(result_type='single')
          SQL SELECT %s AS "a" FROM "crew_sailor" WHERE ("crew_sailor"."ship_id" = %s AND "crew_sailor"."id" = %s) LIMIT 1 with params (1, 1, 4)
          the cursor's fetchone()  ->  no row
        -> False
      -> False
    -> False
fresh[0]
  QuerySet.__getitem__(0)
    Query.set_limits(low=0, high=1)
    QuerySet._fetch_all  (there is no result cache)
      ModelIterable.__iter__
        Query.get_compiler(using='default')
        SQLCompiler.execute_sql
          SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "crew_sailor"."name" ASC LIMIT 1 with params (1,)
          the cursor's fetchmany(100)  ->  1 row
          the cursor's fetchmany(100)  ->  0 rows
        SQLCompiler.results_iter
        Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [1, 'Ada', 1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
    -> <Sailor: Ada>
fresh[1:3]
  QuerySet.__getitem__(slice(1, 3, None))
    Query.set_limits(low=1, high=3)
    -> a SailorQuerySet of Sailor, no result cache
fresh[0:4:2]
  QuerySet.__getitem__(slice(0, 4, 2))
    Query.set_limits(low=0, high=4)
    QuerySet.__iter__
      QuerySet._fetch_all  (there is no result cache)
        ModelIterable.__iter__
          Query.get_compiler(using='default')
          SQLCompiler.execute_sql
            SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "crew_sailor"."name" ASC LIMIT 4 with params (1,)
            the cursor's fetchmany(100)  ->  2 rows
            the cursor's fetchmany(100)  ->  0 rows
          SQLCompiler.results_iter
          Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [1, 'Ada', 1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
          Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [2, 'Bram', 1, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
    QuerySet.__len__
      QuerySet._fetch_all  (the result cache is filled)
      -> 2
    -> [<Sailor: Ada>]
fresh._result_cache  ->  None
```

`count` hands the query to `Query.get_count`, which asks the database to count. `exists` hands it to `Query.has_results`, which has `Query.exists` make a copy of the query that selects a constant and stops at one row (`django/db/models/sql/query.py:Query.exists`); `contains` is `exists` on a clone filtered by the object's primary key (`django/db/models/query.py:QuerySet.contains`). An index makes a clone limited to the one row and evaluates the clone. The plain slice sent nothing. Under the slice with a step, the `QuerySet.__len__` that follows `QuerySet.__iter__` is Python's doing: `QuerySet.__getitem__` makes a list of the clone, and `list` asks its argument for a length once it has taken an iterator from it. The last line shows that after all six, fresh still has no list: a program that asks an unevaluated queryset for its `count` and then loops over it has sent two statements.

| use | with a result cache | without one |
|---|---|---|
| iteration, `len`, `bool` | reads the list | evaluates the queryset: `_fetch_all` fills the cache |
| pickling | pickles the list with the rest | evaluates the queryset first |
| an index, `[k]` | the item of the list | a clone limited to that row is evaluated; the queryset is not |
| a slice, `[a:b]` | a slice of the list, which is a list | a clone with the limits on its query, not evaluated |
| a slice with a step, `[a:b:c]` | a slice of the list | a clone with the limits is evaluated, and the step is taken from its list |
| `repr` | the first twenty of the list, and a note where there are more | a clone limited to twenty-one rows is evaluated |
| `count` | the list's length | `Query.get_count`: a statement that counts |
| `exists` | the list's truth | `Query.has_results`: a statement that stops at one row |
| `contains` | whether the object is in the list | `exists` on a clone filtered by the object's primary key |
| a shallow copy, `copy.copy` | the copy shares the list | evaluates the queryset first, as pickling does |
| `iterator` | does not look at it | runs the statement, and keeps nothing |

*How each use of a queryset is answered. The methods that return one object or one value, `QuerySet.get` and `QuerySet.first` among them, are in [`get`, `first`, `count` and the other methods that run a query at once](results.md).*

## An index and a slice

`QuerySet.__getitem__` takes an integer or a slice and refuses anything else with `TypeError`, and refuses a negative index or bound with `ValueError`. With a result cache it indexes the list. Without one it makes a clone and narrows the clone's query with `Query.set_limits` (`django/db/models/query.py:QuerySet.__getitem__`). An index past the last row raises `IndexError` either way. Without a result cache that is because the clone is evaluated, its list is empty, and the first item is asked of it.

A query keeps its limits as two marks, `Query.low_mark` and `Query.high_mark`, the offsets of the first row wanted and of the first row not wanted, and `set_limits` applies new bounds within the old ones. So a slice of a slice counts from the first slice's start and cannot reach past its end (`django/db/models/sql/query.py:Query.set_limits`). Below, everyone is the queryset of all four sailors by key.

```text recording=querysets
everyone[1:3].query.low_mark, everyone[1:3].query.high_mark  ->  (1, 3)
everyone[5:].query.low_mark, everyone[5:].query.high_mark, everyone[5:][2:4].query.low_mark, everyone[5:][2:4].query.high_mark  ->  (5, None, 7, 9)
everyone[:3][:10].query.high_mark, everyone[2:6][1:].query.low_mark  ->  (3, 3)
type(everyone[1:3]).__name__, type(everyone[0:4:2]).__name__  ->  ('SailorQuerySet', 'list')
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC LIMIT 4
everyone[-1]  ->  raises ValueError: Negative indexing is not supported.
everyone[:-1]  ->  raises ValueError: Negative indexing is not supported.
everyone['id']  ->  raises TypeError: QuerySet indices must be integers or slices, not str.
everyone[9]  ->  raises IndexError: list index out of range
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC LIMIT 1 OFFSET 9
isinstance(everyone[2:2], EmptyQuerySet), list(everyone[2:2])  ->  (True, [])
```

A plain slice returns the clone, still unevaluated, so it can be passed on like any queryset. A slice with a step is the one slice that evaluates: the clone is limited to the bounds, turned into a list, and the step applied to the list. And where the two marks meet, `set_limits` marks the query as empty, which makes the slice an empty queryset: `isinstance` with `EmptyQuerySet` is true of any queryset whose query is so marked, and evaluating it sends no statement ([Annotations, ordering and the other methods that change the query](methods.md) has the empty queryset).

Once a query has limits, some of the queryset's methods refuse it. For a filter and an ordering Django's documentation gives the reason: that does not translate well into SQL and would not have a clear meaning (`docs/ref/models/querysets.txt`). `Query.is_sliced` is true when either mark has moved, and each of these tests it:

```text recording=querysets
everyone[1:3].filter(name='Bram')  ->  raises TypeError: Cannot filter a query once a slice has been taken.
everyone[1:3].order_by('name')  ->  raises TypeError: Cannot reorder a query once a slice has been taken.
everyone[1:3].reverse()  ->  raises TypeError: Cannot reverse a query once a slice has been taken.
everyone[1:3].distinct()  ->  raises TypeError: Cannot create distinct fields once a slice has been taken.
everyone[1:3].update(name='x')  ->  raises TypeError: Cannot update a query once a slice has been taken.
everyone[1:3].delete()  ->  raises TypeError: Cannot use 'limit' or 'offset' with delete().
everyone[1:3].in_bulk()  ->  raises TypeError: Cannot use 'limit' or 'offset' with in_bulk().
everyone[1:3].latest('signed_on')  ->  raises TypeError: Cannot change a query once a slice has been taken.
list(everyone[1:3].values_list('name', flat=True)), everyone[1:3].count(), everyone[1:3].exists()  ->  (['Bram', 'Cora'], 2, True)
  SQL SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC LIMIT 2 OFFSET 1
  SQL SELECT COUNT(*) FROM (SELECT "crew_sailor"."id" AS "col1" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC LIMIT 2 OFFSET 1) subquery
  SQL SELECT %s AS "a" FROM "crew_sailor" LIMIT 1 OFFSET 1 with params (1,)
```

`QuerySet.filter` and `QuerySet.exclude` refuse only when they are given an argument (`django/db/models/query.py:QuerySet._filter_or_exclude`). `QuerySet.values_list`, `QuerySet.count` and `QuerySet.exists` in the last question are among the methods that do not refuse a sliced query: the count is taken over the slice as a subquery, and `exists` asks whether the slice has a row. What the operators that combine two querysets do with a sliced one is in [Combining querysets: the operators and `union`](combining.md).

## `iterator`: reading without keeping

`QuerySet.iterator` returns a generator over the same iterable class that `QuerySet._fetch_all` uses, and stores nothing: the queryset has no result cache afterwards, and one it already had is neither read nor changed (`django/db/models/query.py:QuerySet._iterator`). It also asks the compiler for a **chunked fetch**, unless the database's entry in `DATABASES` has `"DISABLE_SERVER_SIDE_CURSORS"` set. With a chunked fetch `SQLCompiler.execute_sql` takes its cursor from `BaseDatabaseWrapper.chunked_cursor` and, where the backend's feature `BaseDatabaseFeatures.can_use_chunked_reads` is true, returns without having read the rows: they are read from the cursor as the consumer asks for them, a chunk at a call (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`, `django/db/models/sql/compiler.py:cursor_iter`).

```text recording=querysets
iterator: rows are read from the cursor a chunk at a time, and each becomes an instance as the loop asks for it
    everyone = Sailor.objects.order_by('id')
    for sailor in everyone.iterator(chunk_size=3): seen(sailor)
      QuerySet.iterator(chunk_size=3)  ->  a generator
      QuerySet._iterator(use_chunked_fetch=True, chunk_size=3)
        ModelIterable.__iter__
          SQLCompiler.execute_sql(chunked_fetch=True, chunk_size=3)
            BaseDatabaseWrapper.chunked_cursor
              BaseDatabaseWrapper.cursor
            SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC
          SQLCompiler.results_iter
          the cursor's fetchmany(3)  ->  3 rows
          Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [1, 'Ada', 1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      the loop's body runs with <Sailor: Ada>
          Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [2, 'Bram', 1, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      the loop's body runs with <Sailor: Bram>
          Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      the loop's body runs with <Sailor: Cora>
          the cursor's fetchmany(3)  ->  1 row
          Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [4, 'Dag', 2, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      the loop's body runs with <Sailor: Dag>
          the cursor's fetchmany(3)  ->  0 rows
    everyone._result_cache  ->  None
```

Three rows were read, and the loop's body ran after each instance was made, before the next was. The fourth row was not read from the cursor until the loop asked for a fourth instance. Compare the same loop over the queryset itself, where everything is read and made first:

```text recording=querysets
The same loop over the queryset itself: every row is read and every instance made before the loop sees the first
    for sailor in everyone: seen(sailor)
      QuerySet.__iter__
        QuerySet._fetch_all
          ModelIterable.__iter__
            SQLCompiler.execute_sql
              BaseDatabaseWrapper.cursor
              SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC
              the cursor's fetchmany(100)  ->  4 rows
              the cursor's fetchmany(100)  ->  0 rows
            SQLCompiler.results_iter
            Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [1, 'Ada', 1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
            Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [2, 'Bram', 1, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
            Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
            Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [4, 'Dag', 2, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      the loop's body runs with <Sailor: Ada>
      the loop's body runs with <Sailor: Bram>
      the loop's body runs with <Sailor: Cora>
      the loop's body runs with <Sailor: Dag>
    len(everyone._result_cache)  ->  4
```

The argument `chunk_size=` of `iterator` is the number of rows asked of the cursor at a call, and it is 2,000 when none is given. A number that is not positive is refused with `ValueError` (`django/db/models/query.py:QuerySet.iterator`). Where the queryset has prefetch lookups the argument is required, and is then also the number of instances for which the lookups are followed at a time ([`prefetch_related`: related objects in a second query](prefetch.md)).

In the base class `chunked_cursor` returns an ordinary cursor, and its docstring says what a backend's own may return instead, where the database supports it: a cursor that tries to avoid caching, the server-side cursor that `"DISABLE_SERVER_SIDE_CURSORS"` is named for (`django/db/backends/base/base.py:BaseDatabaseWrapper.chunked_cursor`). The setting is for a connection that cannot use such a cursor, and Django's documentation gives the case of a connection pooler in transaction pooling mode (`docs/ref/databases.txt`). What each backend does is in [Database backends](../backends.md). On a connection with the setting on, `iterator` still makes one instance at a time and keeps none, but `execute_sql` has read every row first, as it does for `_fetch_all`.

## `repr`, pickling and copying

Printing a queryset, pickling it and copying it are uses of it too:

```text recording=querysets
Asked of repr, pickle and copy
    repr(Port.objects.all())  ->  '<QuerySet [<Port: Bergen>, <Port: Leith>, <Port: Lisbon>]>'
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" ORDER BY "fleet_port"."name" ASC LIMIT 21
    repr(Logbook.objects.order_by('id')).count('<Logbook'), repr(Logbook.objects.order_by('id'))[-45:]  ->  (20, "0)>, '...(remaining elements truncated)...']>")
      SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook" ORDER BY "office_logbook"."id" ASC LIMIT 21
      SQL SELECT "office_logbook"."id", "office_logbook"."title" FROM "office_logbook" ORDER BY "office_logbook"."id" ASC LIMIT 21
    len(pickle.loads(pickle.dumps(Port.objects.all()))._result_cache)  ->  3
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" ORDER BY "fleet_port"."name" ASC
...
    ports = Port.objects.all(); list(ports)
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" ORDER BY "fleet_port"."name" ASC
    len(ports._result_cache), copy.deepcopy(ports)._result_cache, copy.copy(ports)._result_cache is ports._result_cache  ->  (3, None, True)
    unread = Port.objects.all()
    len(copy.copy(unread)._result_cache), len(unread._result_cache)  ->  (3, 3)
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" ORDER BY "fleet_port"."name" ASC
    Port.objects.all() == Port.objects.all(), ports == ports  ->  (False, True)
```

`QuerySet.__repr__` takes a slice of twenty-one, one more than `REPR_OUTPUT_SIZE`, and so sends a statement with that limit when the queryset has not been evaluated; a twenty-first row, which the office's twenty-five logbooks have, is replaced in what it prints by a note that the rest were left out (`django/db/models/query.py:QuerySet.__repr__`). Printing a queryset in a shell or a debugger is a query.

`QuerySet.__getstate__` evaluates the queryset and returns its attributes, the list among them, with the version of Django under the key `"_django_version"`. `QuerySet.__setstate__` warns, with `RuntimeWarning`, when the version it finds is not the one running, or when there is none, and restores the attributes either way (`django/db/models/query.py:QuerySet.__setstate__`). A pickled queryset is therefore a pickled result, and unpickling it sends nothing.

`QuerySet.__deepcopy__` copies every attribute deeply but the result cache, which it leaves as `None` on the copy, so a deep copy of an evaluated queryset is an unevaluated one (`django/db/models/query.py:QuerySet.__deepcopy__`). The copy has the original's `_prefetch_done` with the rest, so where the original has followed its prefetch lookups, evaluating the copy does not follow them. The class defines no `__copy__`, so a shallow copy is made by Python from what `__getstate__` returns: it evaluates a queryset that has not been evaluated, as pickling does, and the copy shares the list. The question put to the queryset called unread shows the statement. The class defines no `__eq__`, so two querysets are equal only when they are the same object.

## A queryset given as a value

A queryset can be the value of another's condition, and that is not a use of its contents:

```text recording=querysets
A queryset given as a value to another's filter is not evaluated: its query goes into the other's statement
    heavy = Ship.objects.filter(tonnage__gt=1000)
    on_heavy = Sailor.objects.filter(ship__in=heavy)
      QuerySet.resolve_expression
    heavy._result_cache, on_heavy._result_cache  ->  (None, None)
    for sailor in on_heavy: seen(sailor)
      QuerySet.__iter__
        QuerySet._fetch_all  (there is no result cache)
          ModelIterable.__iter__
            Query.get_compiler(using='default')
            SQLCompiler.execute_sql
              SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (SELECT "U0"."id" FROM "fleet_ship" "U0" WHERE "U0"."tonnage" > %s) with params (1000,)
              the cursor's fetchmany(100)  ->  2 rows
              the cursor's fetchmany(100)  ->  0 rows
            SQLCompiler.results_iter
            Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
            Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [4, 'Dag', 2, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      the loop's body runs with <Sailor: Cora>
      the loop's body runs with <Sailor: Dag>
    heavy._result_cache  ->  None
```

When the outer queryset's filter is built, the inner one is asked to resolve itself as an expression, and `QuerySet.resolve_expression` hands back a copy of its query, resolved, with the queryset's own alias for a database set on the copy (`django/db/models/query.py:QuerySet.resolve_expression`). The copy is compiled into the outer statement as a subquery, and the inner queryset still has no result cache when the outer one has been evaluated. How a query becomes a subquery is in [From QuerySet to SQL](../sql.md).

## What empties the cache

A result cache is a list made at one moment, and nothing ties it to the rows it was made from. A queryset evaluated before a row was changed elsewhere goes on returning what it read. `QuerySet.update`, `QuerySet._update` and `QuerySet.delete`, each of which changes rows through the queryset, also set the cache of the queryset they are called on back to `None` (`django/db/models/query.py:QuerySet.update`, `django/db/models/query.py:QuerySet.delete`) ([Creating, updating and deleting through a queryset](writing.md)). A clone has no cache to begin with, so `QuerySet.all` of an evaluated queryset is one that will send the statement again.
