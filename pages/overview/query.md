---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A queryset becomes SQL

How the view's queryset, the entries whose date falls in a year, ordered by date, is built without touching the database, and what happens when the template's loop finally evaluates it: a `Query` is compiled to one `"SELECT"` by a `SQLCompiler`, a connection is opened, the rows are fetched, and each becomes a model instance.

Building a queryset and running it are two different moments. In the figure no call of the first moment reaches the database; every call that does comes in the second, inside the template's loop.

```text figure=two-moments
two panels, the view's above the template's, time running down; on the right, beyond a line, the database
a box is a step; an accented arrow crosses the line, to the database or back

the view builds the queryset:
  QuerySet.filter      a clone; its Query gets the condition
  QuerySet.order_by    a clone; its Query gets the ordering
  no arrow: the QuerySet is handed to the template

the template's loop runs it:
  QuerySet.__len__ -> QuerySet._fetch_all   the loop takes the queryset's length
  compile   SQLCompiler.as_sql            the Query becomes one SELECT and its parameters
  connect   BaseDatabaseWrapper.connect   -> the database
  execute, then fetch   CursorWrapper.execute   -> the database, the SELECT; <- the rows
  rows      Model.from_db                 each row becomes an instance, kept in the cache
  QuerySet.__iter__                       the loop iterates: the cache is already filled; no arrow
```

*The view's moment above, the template's below. An accented arrow crosses to the database or back; the view's moment has none.*

## A manager hands out querysets

The model's `objects` is a manager the metaclass, `ModelBase`, added, because the class declared none (`django/db/models/base.py:ModelBase._prepare`). `BaseManager.get_queryset` makes a new `QuerySet` for the model, and most public methods of `QuerySet`, `QuerySet.filter` among them, are copied onto the manager class as methods that call them on a fresh queryset. So the view's `filter` is `get_queryset` followed by `QuerySet.filter` (`django/db/models/manager.py:BaseManager._get_queryset_methods`; [Managers](../models/managers.md)).

A new `QuerySet` holds a new `Query` for its model and the class that will turn rows into objects, `ModelIterable` (`django/db/models/query.py:QuerySet.__init__`). The `Query` is the ORM's description of a statement to be: the tables it joins, the conditions, the ordering, what to select (`django/db/models/sql/query.py:Query`).

## Each method returns a new queryset

`QuerySet.filter` clones the queryset it is called on, applies the filter to the clone, and returns the clone, so that a queryset can be kept and refined into several others (`django/db/models/query.py:QuerySet._filter_or_exclude`). The clone has its own `Query`, which `Query.clone` makes by copying the mutable parts, the where clause among them (`django/db/models/sql/query.py:Query.clone`).

The keyword arguments become a `Q`, an object holding conditions, which `&` and `|` combine (`django/db/models/query_utils.py:Q`). `Query.add_q` adds it to the where clause. The work is in `Query.build_filter`, which turns one `"published__year"` with its value into a condition (`django/db/models/sql/query.py:Query.build_filter`):

1. `Query.solve_lookup_type` splits the name at the double underscores: `"published"` is a field of the model, a `DateField`, not a relation, so `"year"` is left over (`django/db/models/sql/query.py:Query.solve_lookup_type`, `django/db/models/sql/query.py:Query.names_to_path`).
2. `Query.setup_joins` makes no join for `"published"`, and `build_filter` asks the field for its column, a `Col` (`django/db/models/sql/query.py:Query.setup_joins`, `django/db/models/fields/__init__.py:Field.get_col`).
3. `Query.build_lookup` turns the leftover name into the condition. A **transform** makes an expression out of another, as the year of a date; a **lookup** compares an expression with a value. The date field has no lookup named `"year"`, so `Query.try_transform` wraps the field's transform of that name, `ExtractYear`, around the column. The transform's `"exact"` lookup is `YearExact`, a `YearLookup`, and it is made with the transform on its left and `2026` on its right (`django/db/models/lookups.py:YearExact`). The rule is that the last name is a lookup if what it applies to has one so named, and otherwise a transform, with `"exact"` as the lookup (`django/db/models/sql/query.py:Query.build_lookup`).

`QuerySet.order_by` clones and clears the ordering, and `Query.add_ordering` checks that `"published"` names a field and stores the name itself (`django/db/models/sql/query.py:Query.add_ordering`). It becomes a column only when the statement is compiled (`django/db/models/sql/compiler.py:SQLCompiler.find_ordering_name`).

In both requests the view's calls record the same lines: `QuerySet._clone` and `Query.clone` first under each, and the three steps above in their order; nothing reaches a compiler or a connection:

```text recording=overview
BaseManager.get_queryset  (Entry.objects)
QuerySet.filter(published__year=2026)
  QuerySet._clone
    Query.clone
  Query.add_q
    Query.build_filter
      Query.solve_lookup_type('published__year')
      Query.setup_joins(['published'])
      Query.build_lookup
        Query.try_transform('year')
          ExtractYear.__init__
        YearExact.__init__(lhs=ExtractYear, rhs=2026)
QuerySet.order_by('published')
  QuerySet._clone
    Query.clone
  Query.add_ordering
```

At the end of the view the queryset holds a `Query` with one base table, one condition and one ordering.

## The template runs it

Nothing evaluates a queryset but a request for its contents: iterating it, taking its length, testing it for truth. Each goes through `QuerySet._fetch_all`, which fills the result cache, if there is none yet, with the list its iterable class, `ModelIterable`, yields (`django/db/models/query.py:QuerySet._fetch_all`). The `for` tag takes the length first, which decides whether the `"empty"` part renders and gives `"forloop"` its `"revcounter"` and `"last"` ([The template is rendered](template.md)). `ModelIterable.__iter__` then does the whole of one query: it asks the router which database to read from, asks the `Query` for a compiler for that database's backend, runs it, and turns each row into an instance (`django/db/models/query.py:ModelIterable.__iter__`).

Both requests record these lines alike. The compile, the connect and the execute stand under `SQLCompiler.execute_sql`, and the rows become instances after it. Other lines are left out; the loop's own `QuerySet.__iter__`, last, has nothing under its `QuerySet._fetch_all`:

```text recording=overview
QuerySet.__len__
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQLCompiler.execute_sql
        SQLCompiler.as_sql
          ...
          WhereNode.as_sql
            YearLookup.as_sql  (YearExact)
        BaseDatabaseWrapper.cursor
          BaseDatabaseWrapper.connect
            DatabaseWrapper.get_new_connection  (sqlite3)
        CursorWrapper.execute
          SQL SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" WHERE "journal_entry"."published" BETWEEN %s AND %s ORDER BY "journal_entry"."published" ASC with params ('2026-01-01', '2026-12-31')
      SQLCompiler.results_iter
      DatabaseOperations.convert_datefield_value  (sqlite3)
      Model.from_db  (Entry)
        Model.__init__  (Entry)
      ...
QuerySet.__iter__
  QuerySet._fetch_all
```

## Compiling the statement

`SQLCompiler.execute_sql` first calls `SQLCompiler.as_sql`, which is where the `Query` becomes a string and its parameters. It builds the clauses and joins them as `"SELECT"`, `"FROM"`, `"WHERE"`, `"ORDER BY"`, appending each clause's parameters in the same order, so that the placeholders and the parameters line up (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`; [The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)).

Each node of the query writes its own SQL, and here `SQLCompiler.compile` calls a node's `as_sql` (`django/db/models/sql/compiler.py:SQLCompiler.compile`). The where clause joins its children's SQL with `"AND"`, and its one child is the year lookup (`django/db/models/sql/where.py:WhereNode.as_sql`).

> **Why.** The statement compares the date column itself, with no extraction of the year, so that an index on the column can be used, as a comment in `YearLookup.as_sql` says. When the right side is a plain value, that method compiles the bare column, leaving out the `ExtractYear` around it, and here compares it with `"BETWEEN"` the first and last day of the year. So the recorded statement's two parameters are the two dates (`django/db/models/lookups.py:YearLookup.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.year_lookup_bounds_for_date_field`).

## The connection and the cursor

The statement needs a cursor, and `BaseDatabaseWrapper.cursor` opens the connection if there is none (`django/db/backends/base/base.py:BaseDatabaseWrapper.cursor`). The database wrapper, here SQLite's `DatabaseWrapper`, lives as long as the thread: `connections`, the `ConnectionHandler` from which `Query.get_compiler` took it by its alias, keeps one per alias per thread. What `BaseDatabaseWrapper.connect` opens and `close` discards is the driver's connection inside it (`django/db/backends/sqlite3/base.py:DatabaseWrapper`, `django/utils/connection.py:BaseConnectionHandler.__getitem__`). `connect` notes when that connection is to be closed, from the database's `"CONN_MAX_AGE"`, and then has the backend's `get_new_connection` open it (`django/db/backends/base/base.py:BaseDatabaseWrapper.connect`). With the default of 0 it is closed when the request ends ([The response returns to the server](response.md)), and the second request's first query opens one again.

With `"AUTOCOMMIT"` true, the default, and `"ATOMIC_REQUESTS"` false, no transaction is opened around the query: each statement is a transaction of its own, which the database commits as it ends (`django/db/backends/sqlite3/base.py:DatabaseWrapper._set_autocommit`; [Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md)). The driver's cursor is wrapped in a `CursorWrapper`, whose `execute` passes it the statement (`django/db/backends/utils.py:CursorWrapper.execute`; [Cursors: executing a statement, the query log and execute wrappers](../backends/cursors.md)).

## Rows become objects

`SQLCompiler.results_iter` returns a generator over the rows the cursor fetched, which applies the converters the backend declares for each column's type as `ModelIterable.__iter__` takes each row (`django/db/models/sql/compiler.py:SQLCompiler.results_iter`). So the converters and `Model.from_db` stand beside `results_iter` in the recording, not under it. SQLite has no date type, so for a date field the backend supplies `DatabaseOperations.convert_datefield_value`, which parses a date that arrived as text. Here the column, declared `"date"`, was already parsed by a converter the backend registers with the driver, so the backend's finds a date and leaves it; a column with no declared type, such as a function's, would reach it as text (`django/db/backends/sqlite3/operations.py:DatabaseOperations.convert_datefield_value`, `django/db/backends/sqlite3/base.py`; [Values in and out: adapters, converters and time zones](../backends/values.md)).

For each converted row `Model.from_db` makes the instance: it calls the class with the values in field order, then marks the instance as not being added and records the database it came from (`django/db/models/base.py:Model.from_db`). These instances are what the loop iterates, and what `"entry.title"` resolves against in the template ([An instance and its state](../models/instances.md)).
