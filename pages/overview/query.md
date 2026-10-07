---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A queryset becomes SQL

How the view's queryset, the entries whose date falls in a year, ordered by date, is built without touching the database, and what happens when the template's loop finally evaluates it: a `Query` is compiled to one `"SELECT"` by a `SQLCompiler`, a connection is opened, the rows are fetched, and each becomes a model instance.

The ORM's first rule is that building a queryset and running it are two different moments. The view builds one and hands it to the template; the template runs it. The recording shows the two moments apart. The first is in the view:

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

## A manager hands out querysets

The model's `objects` is the manager the metaclass gave it when its class statement ran, because the class declared none (`django/db/models/base.py:ModelBase._prepare`). On the class it is a `ManagerDescriptor`, which refuses to be read on an instance and returns the manager (`django/db/models/manager.py:ManagerDescriptor.__get__`). A manager has few methods of its own: `BaseManager.get_queryset` makes a new `QuerySet` for the model, and the public methods of `QuerySet`, `filter` among them, are copied onto the manager class as methods that call them on a fresh queryset, all but the few the queryset keeps to itself and those the manager defines (`django/db/models/manager.py:BaseManager.get_queryset`, `django/db/models/manager.py:BaseManager._get_queryset_methods`). So a call of `filter` on the manager is `get_queryset` followed by `QuerySet.filter`, which is the recording's first two lines ([Managers](../models/managers.md)).

A new `QuerySet` holds a new `Query` for its model, no results, and the class that will turn rows into objects, `ModelIterable` (`django/db/models/query.py:QuerySet.__init__`). The `Query` is the ORM's description of a statement to be: the tables it joins, the conditions, the ordering, what to select (`django/db/models/sql/query.py:Query`).

## Each method returns a new queryset

`QuerySet.filter` does not change the queryset it is called on. It clones it, applies the filter to the clone, and returns the clone, so that a queryset can be kept and refined into several others (`django/db/models/query.py:QuerySet._filter_or_exclude`, `django/db/models/query.py:QuerySet._clone`). The clone has its own `Query`, which `Query.clone` makes by copying the mutable parts, the where clause among them (`django/db/models/sql/query.py:Query.clone`). The recording's `QuerySet._clone` and `Query.clone` under each method are this.

The keyword arguments become a `Q`, and `Query.add_q` adds it to the where clause (`django/db/models/sql/query.py:Query.add_q`). The work is in `Query.build_filter`, which turns one `"published__year"` with its value into a condition (`django/db/models/sql/query.py:Query.build_filter`):

1. `Query.solve_lookup_type` splits the name at the double underscores and walks the model's fields with the pieces: `"published"` is a field, a `DateField`; `"year"` is not, so it is left over as a lookup name (`django/db/models/sql/query.py:Query.solve_lookup_type`).
2. `Query.setup_joins` follows the field path, which for a field on the model itself is no join at all, and names the field and the table it is reached through; `build_filter` then asks the field for its column, a `Col` naming the table and the field (`django/db/models/sql/query.py:Query.setup_joins`, `django/db/models/fields/__init__.py:Field.get_col`, `django/db/models/expressions.py:Col`).
3. `Query.build_lookup` applies the rule for the leftover names. A **transform** makes an expression out of another, as the year of a date; a **lookup** compares an expression with a value. Each name but the last is a transform, the last is a lookup if the column has one so named, and otherwise it is a transform too and the lookup is `"exact"` (`django/db/models/sql/query.py:Query.build_lookup`). The date field has no lookup named `"year"`, but it has a transform, `ExtractYear`, which `Query.try_transform` wraps around the column; the transform's `"exact"` lookup is `YearExact`, and it is made with the transform on its left and `2026` on its right (`django/db/models/sql/query.py:Query.try_transform`, `django/db/models/functions/datetime.py:ExtractYear`, `django/db/models/lookups.py:YearExact`).

The value is prepared as it is stored: `Lookup.__init__` asks the output field of its left side to prepare the right, and the transform's output is an integer, so the value goes through `IntegerField.get_prep_value`, which makes an `int` of what it is given; the URL converter had already made the year one (`django/db/models/lookups.py:Lookup.__init__`, `django/db/models/fields/__init__.py:IntegerField.get_prep_value`).

`QuerySet.order_by` is simpler. It clones, clears the ordering, and `Query.add_ordering` checks that each name is a field and stores the names themselves; they are resolved to columns only when the statement is compiled (`django/db/models/sql/query.py:Query.add_ordering`). At the end of the view the queryset is a `Query` with one base table, one condition and one ordering, and the database has not been consulted.

## The template runs it

Nothing evaluates a queryset but a request for its contents: iterating it, taking its length, testing it for truth. The `for` tag takes its length first ([The template is rendered](template.md)), and that is the second moment:

```text recording=overview
QuerySet.__len__
  QuerySet._fetch_all
    ModelIterable.__iter__
      Query.get_compiler('default')
      SQLCompiler.execute_sql
        SQLCompiler.as_sql
          SQLCompiler.get_select
          SQLCompiler.get_order_by
            Query.setup_joins(['published'])
          SQLCompiler.get_from_clause
          WhereNode.as_sql
            YearLookup.as_sql  (YearExact)
        BaseDatabaseWrapper.cursor
          BaseDatabaseWrapper.connect
            DatabaseWrapper.get_new_connection  (sqlite3)
            signal connection_created -> no receivers
        CursorWrapper.execute
          SQL SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" WHERE "journal_entry"."published" BETWEEN %s AND %s ORDER BY "journal_entry"."published" ASC with params ('2026-01-01', '2026-12-31')
          SQLiteCursorWrapper.execute
      SQLCompiler.results_iter
      DatabaseOperations.convert_datefield_value  (sqlite3)
      Model.from_db  (Entry)
        Model.__init__  (Entry)
          signal pre_init -> no receivers
          signal post_init -> no receivers
      DatabaseOperations.convert_datefield_value  (sqlite3)
      Model.from_db  (Entry)
        Model.__init__  (Entry)
          signal pre_init -> no receivers
          signal post_init -> no receivers
QuerySet.__iter__
  QuerySet._fetch_all
```

`QuerySet._fetch_all` fills the result cache if there is none yet, with the list of what the iterable class yields; iterating a queryset, indexing it, taking its length and testing it for truth all go through it, and `QuerySet.iterator` is the method for reading rows without keeping them (`django/db/models/query.py:QuerySet._fetch_all`, `django/db/models/query.py:QuerySet.iterator`). The loop's `QuerySet.__iter__` a moment later finds the cache filled and runs no query: a queryset is evaluated once and holds its rows.

`ModelIterable.__iter__` does the whole of one query (`django/db/models/query.py:ModelIterable.__iter__`). It asks the router which database to read from, which with no routers configured is `"default"`; asks the `Query` for a compiler for that database's backend, which the backend's operations object supplies by name; runs it; and turns each row into an instance.

## Compiling the statement

`SQLCompiler.execute_sql` first calls `SQLCompiler.as_sql`, which is where the `Query` becomes a string and its parameters (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`, `django/db/models/sql/compiler.py:SQLCompiler.as_sql`). The compiler builds the clauses in an order that is not the statement's: the select columns, which with nothing deferred are every concrete field of the model, each a `Col` (`django/db/models/sql/compiler.py:SQLCompiler.get_select`); the ordering, which is when the name stored by `order_by` is resolved to a column, by `SQLCompiler.find_ordering_name`, the recording's second `Query.setup_joins` (`django/db/models/sql/compiler.py:SQLCompiler.find_ordering_name`); the from clause from the tables the query references (`django/db/models/sql/compiler.py:SQLCompiler.get_from_clause`); and the where clause. It then joins them as `"SELECT"`, `"FROM"`, `"WHERE"`, `"ORDER BY"`, appending each clause's parameters in the same order, so that the placeholders and the parameters line up.

Each node of the query writes its own SQL. `SQLCompiler.compile` calls a node's `as_sql`, or a vendor-specific method such as `as_sqlite` when the node defines one for this backend (`django/db/models/sql/compiler.py:SQLCompiler.compile`). The where clause compiles its children and joins them with `"AND"` (`django/db/models/sql/where.py:WhereNode.as_sql`). Its one child is the year lookup, and its `as_sql` is the reason the recorded statement compares the column itself and extracts no year from it: when the right side is a plain value, `YearLookup.as_sql` compiles the column under the transform instead of the transform, and compares it with `"BETWEEN"` the first and last day of the year, which lets the database use an index on the column (`django/db/models/lookups.py:YearLookup.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.year_lookup_bounds_for_date_field`). The two dates are the statement's two parameters.

## The connection and the cursor

The statement needs a cursor, and `BaseDatabaseWrapper.cursor` opens the connection if there is none (`django/db/backends/base/base.py:BaseDatabaseWrapper.cursor`). The wrapper object itself lives as long as the thread: `connections` keeps one `DatabaseWrapper` per database alias per thread, and what `BaseDatabaseWrapper.connect` opens and `close` discards is the driver's connection inside it (`django/db/__init__.py:connections`, `django/utils/connection.py:BaseConnectionHandler.__getitem__`). `connect` resets the transaction state, notes when the connection should be closed, from the database's `"CONN_MAX_AGE"`, calls the backend's `get_new_connection`, sets autocommit, and sends `connection_created` (`django/db/backends/base/base.py:BaseDatabaseWrapper.connect`). The SQLite backend's `get_new_connection` connects with the standard library's module, registers the SQL functions Django implements in Python, and turns foreign key enforcement on with a pragma (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_new_connection`).

With `"AUTOCOMMIT"` true, the default, and `"ATOMIC_REQUESTS"` false, there is no transaction: on SQLite autocommit means the driver issues no `"BEGIN"` of its own (`django/db/backends/sqlite3/base.py:DatabaseWrapper._set_autocommit`). The cursor is wrapped in a `CursorWrapper`, or in `CursorDebugWrapper` when `BaseDatabaseWrapper.queries_logged` is true, which it is when `settings.DEBUG` is or when a test is capturing queries; that is the wrapper that logs every query, and the recording ran with the setting off (`django/db/backends/base/base.py:BaseDatabaseWrapper._prepare_cursor`, `django/db/backends/utils.py:CursorDebugWrapper`). `CursorWrapper.execute` runs any execute wrappers the project installed around the real call, refuses to run inside a transaction that needs a rollback, and translates the driver's exceptions into Django's (`django/db/backends/utils.py:CursorWrapper.execute`). The SQLite cursor's last act is to rewrite the `%s` placeholders Django writes into the `?` the driver wants (`django/db/backends/sqlite3/base.py:SQLiteCursorWrapper.execute`).

All of this is one statement through Django's cursor; the two pragmas ran on the driver's connection as it was opened, below the cursor. The recording writes down what passes through the cursor, one `"SELECT"` per request and no `"BEGIN"`, which would have passed through it too; with autocommit on, no commit is issued either.

## Rows become objects

`SQLCompiler.results_iter` reads the rows the cursor fetched and applies the converters the backend declares for each column's type (`django/db/models/sql/compiler.py:SQLCompiler.results_iter`). SQLite has no date type, so for a `DateField` (`django/db/models/fields/__init__.py:DateField`) the backend supplies `DatabaseOperations.convert_datefield_value`, which parses a date that arrived as text; here the column's text was already parsed on the way out of the driver, by a converter the backend registers with the driver when it is imported, so the backend's own converter finds a `date` and leaves it (`django/db/backends/sqlite3/base.py`) (`django/db/backends/sqlite3/operations.py:DatabaseOperations.convert_datefield_value`).

For each converted row `Model.from_db` makes the instance: it calls the class with the values in field order, then marks the instance as not being added and records the database it came from (`django/db/models/base.py:Model.from_db`). `Model.__init__` sends `pre_init`, sets each field from the positional values, and sends `post_init`; the two signals are sent for every row, receivers or none (`django/db/models/base.py:Model.__init__`). These instances are what the loop iterates, and what `"entry.title"` resolves against in the template ([An instance and its state](../models/instances.md)).

When the request ends the connection is closed, as [The response returns to the server](response.md) says. The wrapper, SQLite's `DatabaseWrapper` (`django/db/backends/sqlite3/base.py:DatabaseWrapper`), stays on the thread, and the next request's first query opens a connection again, which is why the second request in the recording also shows `BaseDatabaseWrapper.connect`.
