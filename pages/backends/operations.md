---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The SQL a backend writes: `BaseDatabaseOperations`

The **operations object**, a connection's `BaseDatabaseWrapper.ops`, writes most of the fragments of SQL that differ between databases and that code above the backend asks for by name. Its class is each backend's subclass of `BaseDatabaseOperations`, and beside it, on the connection, stands `operators`, the table from which a lookup takes its comparison.

The compiler asks for a quoted name, a limit, `"DISTINCT"`, a lock and, for a statement that `QuerySet.explain` runs, a prefix; a lookup for a cast of its column and for its operator; a function of a date for the SQL that takes a part out of it or cuts it down; arithmetic on dates and durations for the way its two sides combine; a window for the words of its frame; and many expressions ask whether the backend supports them. Every question but the one for the operator is a method of the operations object (`django/db/backends/base/operations.py:BaseDatabaseOperations`).

What the base class writes is **the plain case**, which a backend keeps unless it overrides the method: `"FOR UPDATE"`, `"UNION"`, two sides with `"+"` between. Where the base has nothing to write, it raises `NotImplementedError`. Another place a difference is kept is the expression, in a method named for a vendor such as `Lookup.as_oracle`, which the compiler prefers where a node has one ([Transforms and database functions: `Transform` and `Func`](../sql/functions.md)). The object's other methods are told with their subjects: the insert's in [Inserts: returned keys, conflicts and batch sizes](inserts.md), the adapters and converters in [Values in and out: adapters, converters and time zones](values.md), the flushing of tables in [Introspection: reading the schema back](introspection.md), the savepoints in [Transactions: autocommit, `atomic` and savepoints](transactions.md), and `BaseDatabaseOperations.last_executed_query` in [Cursors: executing a statement, the query log and execute wrappers](cursors.md).

## One statement, and what its compiler asked

`BaseDatabaseWrapper.__init__` makes the operations object with every connection, from the backend's `BaseDatabaseWrapper.ops_class`, and the object keeps that connection, which it asks for what it needs beyond its arguments, most often the connection's features, which [What a database can do: `BaseDatabaseFeatures`](features.md) tells (`django/db/backends/base/base.py:BaseDatabaseWrapper.__init__`).

Recorded from a running Django on SQLite, the calls this passage is about stand under the line of Python that set them going, nested as they were made, with what a call returned after `->`. The queryset is the second and third of the ships with an e in their name:

```text recording=backends
shown = Ship.objects.filter(name__icontains='e').order_by('name')[1:3]
sql, params = shown.query.get_compiler('default').as_sql()
  BaseDatabaseOperations.compiler('SQLCompiler')  ->  SQLCompiler
  SQLCompiler.as_sql
    reads connection.features.supports_order_by_nulls_modifier  ->  True
    DatabaseOperations.check_expression_support(OrderBy(Col(fleet_ship, fleet.Ship.name), descending=False))
    BaseDatabaseOperations.lookup_cast(lookup_type='icontains', internal_type='CharField')  ->  '%s'
    BaseDatabaseOperations.prep_for_like_query('e')  ->  'e'
    reads connection.features.pattern_lookup_needs_param_pattern  ->  True
    reads connection.operators['icontains']  ->  "LIKE %s ESCAPE '\\'"
    BaseDatabaseOperations.limit_offset_sql(low_mark=1, high_mark=3)
      BaseDatabaseOperations._get_limit_offset_params(low_mark=1, high_mark=3)
      -> 'LIMIT 2 OFFSET 1'
# DatabaseOperations.quote_name was called 6 times, for captain_id, fleet_ship, home_id, id, name, tonnage
sql  ->  'SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" LIKE %s ESCAPE \'\\\' ORDER BY "fleet_ship"."name" ASC LIMIT 2 OFFSET 1'
params  ->  ('%e%',)
```

`Query.get_compiler` asks for the compiler's class before anything is written (`django/db/models/sql/query.py:Query.get_compiler`). The other questions come in the order in which the compiler meets their clauses: the ordering is resolved before the where clause is compiled, so `OrderBy.as_sql` comes first. It reads whether the backend can write `"NULLS LAST"` before it looks whether this ordering places its nulls at all, and asks whether the `OrderBy` is supported (`django/db/models/expressions.py:OrderBy.as_sql`). Then the lookup asks for its cast and its escaping, puts the wildcards round the escaped value where `BaseDatabaseFeatures.pattern_lookup_needs_param_pattern` is set, which made `"e"` the parameter `"%e%"`, and takes its operator from the connection (`django/db/models/lookups.py:PatternLookup.process_rhs`); the limit comes last. SQLite's class inherits most of these methods and declares two of those asked, `DatabaseOperations.check_expression_support` and `DatabaseOperations.quote_name` (`django/db/backends/sqlite3/operations.py:DatabaseOperations`). Each name was quoted once, though the statement names the table at every column, because the compiler keeps each answer (`django/db/models/sql/compiler.py:SQLCompiler.quote_name`) ([The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)).

## Four backends, the same requests

The same requests, put to the four backends, show the shape of the differences: mostly a word or a clause, now and then another construction. The operator of a comparison is the connection's, from `DatabaseWrapper.operators` (`django/db/backends/sqlite3/base.py:DatabaseWrapper.operators`); every other answer is the operations object's.

| request | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| the table's name | in double quotes | in double quotes | in backticks | in double quotes and in capitals |
| the sixth to the fifteenth row | `"LIMIT 10 OFFSET 5"` | `"LIMIT 10 OFFSET 5"` | `"LIMIT 10 OFFSET 5"` | `"OFFSET 5 ROWS FETCH FIRST 10 ROWS ONLY"` |
| every row from the sixth | `"LIMIT -1 OFFSET 5"` | `"OFFSET 5"` | `"LIMIT"` of `2**64 - 1`, then `"OFFSET 5"` | `"OFFSET 5 ROWS"` |
| a pattern | `"%s"`, then `"LIKE %s ESCAPE '\'"` | `"UPPER(%s::text)"`, then `"LIKE UPPER(%s)"` | `"%s"`, then `"LIKE %s"` | `"UPPER(%s)"`, then `"LIKE UPPER(TRANSLATE(%s USING NCHAR_CS)) ESCAPE TRANSLATE('\' USING NCHAR_CS)"` |
| the year of a date | a call of `"django_date_extract"`, with `"year"` as a parameter | `"EXTRACT"` | `"EXTRACT"` | `"EXTRACT"` |
| a lock | the base class's, which the compiler never asks for: the features lack `BaseDatabaseFeatures.has_select_for_update` | the base class's | the base class's | the base class's |

*What the four backends write for the same requests to the operations object. The table `"fleet_ship"`, quoted by `BaseDatabaseOperations.quote_name`, comes back as `'"fleet_ship"'`, on MySQL as ``'`fleet_ship`'`` and on Oracle as `'"FLEET_SHIP"'`. The rows are asked of `BaseDatabaseOperations.limit_offset_sql(5, 15)` and `BaseDatabaseOperations.limit_offset_sql(5, None)`, and MySQL's second is, in full, `"LIMIT 18446744073709551615 OFFSET 5"`. The pattern is `"icontains"` on a column of internal type `"CharField"`: the column's cast, by `BaseDatabaseOperations.lookup_cast`, then the operator, from `DatabaseWrapper.operators`. Oracle has two tables of comparisons, and its connection takes the one shown here where the database accepts a statement written with it. The year is `ExtractYear`'s, by `BaseDatabaseOperations.date_extract_sql`, and PostgreSQL, MySQL and Oracle write it as `"EXTRACT(YEAR FROM ...)"`. The lock, by `BaseDatabaseOperations.for_update_sql`, is the base class's text, `"FOR UPDATE"`, on all four, and they differ in which of its variants their features allow.*

## The compiler's fragments

`BaseDatabaseOperations.compiler` imports the module that `BaseDatabaseOperations.compiler_module` names, once, and returns the compiler class of the name a query carries (`django/db/backends/base/operations.py:BaseDatabaseOperations.compiler`). PostgreSQL's and MySQL's operations name modules of their own, which define the compilers they change and import the rest from the base module ([Inserts: returned keys, conflicts and batch sizes](inserts.md), [MySQL and MariaDB](mysql.md)).

`BaseDatabaseOperations.quote_name` raises `NotImplementedError`. SQLite's and PostgreSQL's operations put a name in double quotes, and MySQL's in backticks, unless it already begins and ends with one (`django/db/backends/sqlite3/operations.py:DatabaseOperations.quote_name`). Oracle's put a name in double quotes and in capitals, and cut an unquoted one longer than 30 characters to 30 with `truncate_name` (`django/db/backends/oracle/operations.py:DatabaseOperations.quote_name`).

`BaseDatabaseOperations.limit_offset_sql` writes `"LIMIT"` and `"OFFSET"` from the marks of a sliced query, each where it is not zero or `None`, and a slice with an offset and no end takes its count from `BaseDatabaseOperations.no_limit_value`, or has no limit where that is `None`, as it is on PostgreSQL and Oracle; the base has no such value and raises `NotImplementedError` (`django/db/backends/base/operations.py:BaseDatabaseOperations.limit_offset_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations._get_limit_offset_params`). Oracle's operations write their own clause, with `"FETCH FIRST"` (`django/db/backends/oracle/operations.py:DatabaseOperations.limit_offset_sql`).

`BaseDatabaseOperations.distinct_sql` returns `"DISTINCT"` and refuses fields with `NotSupportedError`; PostgreSQL's alone write `"DISTINCT ON"` with the fields ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](../sql/ordering.md), `django/db/backends/postgresql/operations.py:DatabaseOperations.distinct_sql`).

`BaseDatabaseOperations.for_update_sql` writes `"FOR UPDATE"` and the variants the compiler asks for; whether it asks at all, and for which variants, the features decide ([What a database can do: `BaseDatabaseFeatures`](features.md), `django/db/backends/base/operations.py:BaseDatabaseOperations.for_update_sql`).

The operations object also writes the words that join two queries, `BaseDatabaseOperations.set_operators`; the ordering of a grouped statement that has none, `BaseDatabaseOperations.force_no_ordering`, and the grouping of a `"HAVING"` that has none, `BaseDatabaseOperations.force_group_by`; and the two sides of each pair of a join, `BaseDatabaseOperations.prepare_join_on_clause` (`django/db/backends/base/operations.py:BaseDatabaseOperations`). Each is told with its clause: [Two queries into one: `combine` and `get_combinator_sql`](../sql/combining.md), [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](../sql/grouping.md) and [Tables and joins: the alias map and join promotion](../sql/joins.md).

## Comparisons: `operators`, `pattern_ops` and `lookup_cast`

A lookup's comparison is two halves, and the backend supplies a piece of each: a cast of the column, from the operations object, and the operator, from a table on the connection; how a lookup reads them is in [Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../sql/lookups.md). The table is `DatabaseWrapper.operators`, from a lookup's name to a string with `"%s"` for the right side. Each backend's connection class declares its own but Oracle's, whose connection objects choose one, and `BaseDatabaseWrapper` declares none (`django/db/backends/sqlite3/base.py:DatabaseWrapper.operators`). The four write `"exact"`, `"gt"`, `"gte"`, `"lt"` and `"lte"` alike, and part on the rest.

- SQLite writes `"LIKE %s ESCAPE '\'"` for `"iexact"` and every pattern lookup, whether it ignores case or not, and `"REGEXP"`, a function Django registers on each connection, for the regular expressions ([SQLite](sqlite.md)).
- PostgreSQL writes `"= UPPER(%s)"` for `"iexact"`, and `"~ %s"` and `"~* %s"` for the regular expressions (`django/db/backends/postgresql/base.py:DatabaseWrapper.operators`).
- MySQL writes `"LIKE BINARY %s"` where case counts, and has no entry for a regular expression (`django/db/backends/mysql/base.py:DatabaseWrapper.operators`).
- Oracle has two tables, `DatabaseWrapper._standard_operators` and `DatabaseWrapper._likec_operators`, the second writing `"LIKEC"`. A connection object tries the first with a test statement as it first connects, falls back on the second where that fails, and takes the matching `pattern_ops` (`django/db/backends/oracle/base.py:DatabaseWrapper.init_connection_state`) ([Oracle](oracle.md)).

Where the right side of a pattern lookup is an expression and not a value, as in a filter of the ships whose name contains their home port's, the escaping and the wildcards have to be written in SQL. `DatabaseWrapper.pattern_ops` holds the comparison that takes the operator's place, on SQLite `"LIKE '%%' || {} || '%%' ESCAPE '\'"` for `"contains"`, and in its `"{}"` stands `DatabaseWrapper.pattern_esc`, which on SQLite escapes the expression's backslashes, `"%"` and `"_"` with nested `"REPLACE"` calls; the wildcards are joined by `"||"` on SQLite, PostgreSQL and Oracle and by `"CONCAT"` on MySQL (`django/db/models/lookups.py:PatternLookup.get_rhs_op`, `django/db/backends/mysql/base.py:DatabaseWrapper.pattern_ops`).

`BaseDatabaseOperations.lookup_cast` returns `"%s"`, the column as it is, and SQLite keeps it. PostgreSQL's cast the column to text for the lookups that match text, an IP address's through `"HOST"`, and put `"UPPER"` round it for `"iexact"`, `"icontains"`, `"istartswith"` and `"iendswith"`. Oracle's write `"UPPER"` for the same four, and for the rest but `"isnull"` pass a binary or text column through `"DBMS_LOB.SUBSTR"`. MySQL's unquote a JSON column for the lookups that match text, and on MariaDB for every lookup (`django/db/backends/postgresql/operations.py:DatabaseOperations.lookup_cast`).

`BaseDatabaseOperations.prep_for_like_query` escapes a backslash, `"%"` and `"_"` in a value for a `"LIKE"`. `BaseDatabaseOperations.prep_for_iexact_query` is the same function, kept apart because `"iexact"` need not be a `"LIKE"`: PostgreSQL's and Oracle's return the value untouched, their `"iexact"` being `"= UPPER(%s)"` (`django/db/backends/base/operations.py:BaseDatabaseOperations.prep_for_iexact_query`).

`BaseDatabaseOperations.regex_lookup` is asked only where `operators` has no entry for a regular expression, as on MySQL and Oracle, whose operations write `"REGEXP_LIKE"` with `'c'` or `'i'` for the case, except that on MariaDB, which has no such function, MySQL's write `"REGEXP BINARY"` or `"REGEXP"` (`django/db/backends/mysql/operations.py:DatabaseOperations.regex_lookup`).

## Dates and times: extraction, truncation and casts

`Extract.as_sql` chooses by its argument's field among `BaseDatabaseOperations.datetime_extract_sql`, `BaseDatabaseOperations.date_extract_sql` and `BaseDatabaseOperations.time_extract_sql` (`django/db/models/functions/datetime.py:Extract.as_sql`), and `TruncBase.as_sql` by its output field among `BaseDatabaseOperations.datetime_trunc_sql`, `BaseDatabaseOperations.date_trunc_sql` and `BaseDatabaseOperations.time_trunc_sql`; `TruncDate` and `TruncTime` ask for a cast, `BaseDatabaseOperations.datetime_cast_date_sql` and `BaseDatabaseOperations.datetime_cast_time_sql` ([Transforms and database functions: `Transform` and `Func`](../sql/functions.md)). Each is given the column's SQL and parameters and, but for the two casts, the part by name, such as `"week_day"`, and returns SQL and parameters.

The month of a sailor's signing-on, in Oslo's time, asked of SQLite and, with nothing sent, of PostgreSQL 17, MySQL 8.4 and Oracle 23:

```text recording=backends
sqlite.ops.datetime_trunc_sql('month', '"crew_sailor"."signed_on"', (), 'Europe/Oslo')  ->  ('django_datetime_trunc(%s, "crew_sailor"."signed_on", %s, %s)', ('month', 'Europe/Oslo', 'UTC'))
postgresql.ops.datetime_trunc_sql('month', '"crew_sailor"."signed_on"', (), 'Europe/Oslo')  ->  ('DATE_TRUNC(%s, "crew_sailor"."signed_on" AT TIME ZONE %s)', ('month', 'Europe/Oslo'))
mysql.ops.datetime_trunc_sql('month', '"crew_sailor"."signed_on"', (), 'Europe/Oslo')  ->  ('CAST(DATE_FORMAT(CONVERT_TZ("crew_sailor"."signed_on", %s, %s), %s) AS DATETIME)', ('UTC', 'Europe/Oslo', '%Y-%m-01 00:00:00'))
oracle.ops.datetime_trunc_sql('month', '"crew_sailor"."signed_on"', (), 'Europe/Oslo')  ->  ('TRUNC(CAST((FROM_TZ("crew_sailor"."signed_on", \'UTC\') AT TIME ZONE \'Europe/Oslo\') AS TIMESTAMP), %s)', ('MONTH',))
```

All four apply the zone before the function, since, a comment says, the result must come from the datetime as it was given, not as it is stored (`django/db/models/functions/datetime.py:TimezoneMixin.get_tzname`); how each gives the database its zones is in [Values in and out: adapters, converters and time zones](values.md). PostgreSQL's, MySQL's and Oracle's write the part of an `"EXTRACT"` into the statement, which, their comments say, cannot take it as a parameter, once a check has found it to be capitals and underscores (`django/db/backends/postgresql/operations.py:DatabaseOperations.date_extract_sql`).

Where their databases count differently, the four make a part mean the same, each making Sunday day 1 of a `"week_day"`: PostgreSQL's add one to `"DOW"`, the comment saying this is for consistency across backends; MySQL's `"DAYOFWEEK"` counts so already; Oracle's `"TO_CHAR"` with `'D'` does under the territory `'AMERICA'`, which the connection sets as it opens so that it does (`django/db/backends/oracle/base.py:DatabaseWrapper.init_connection_state`); and SQLite's function counts so in Python (`django/db/backends/sqlite3/_functions.py:_sqlite_datetime_extract`). A year compared with a plain number, as in a filter for the voyages of 2026, needs no extraction: the column is compared with the first and last day of the year, which `BaseDatabaseOperations.year_lookup_bounds_for_date_field` gives, or for a datetime with the first and last moment, which `BaseDatabaseOperations.year_lookup_bounds_for_datetime_field` gives (`django/db/backends/base/operations.py:BaseDatabaseOperations.year_lookup_bounds_for_date_field`) ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../sql/lookups.md)).

## Arithmetic: `combine_expression`, durations and `subtract_temporals`

`CombinedExpression.as_sql` hands its two compiled sides and its connector, one of the strings of `Combinable`, from `"+"` to `"^"` for a power, `"%%"` for a remainder, doubled because the string may also be given parameters, and `"#"` for an exclusive or, to `BaseDatabaseOperations.combine_expression`, which in the base writes the connector between the sides (`django/db/models/expressions.py:CombinedExpression.as_sql`). PostgreSQL's keep the base's. The power, asked of SQLite and, with no server, of PostgreSQL 17, MySQL 8.4 and Oracle 23:

```text recording=backends
sqlite.ops.combine_expression('^', ['"fleet_ship"."tonnage"', '%s'])  ->  'POWER("fleet_ship"."tonnage",%s)'
postgresql.ops.combine_expression('^', ['"fleet_ship"."tonnage"', '%s'])  ->  '"fleet_ship"."tonnage" ^ %s'
mysql.ops.combine_expression('^', ['"fleet_ship"."tonnage"', '%s'])  ->  'POW("fleet_ship"."tonnage",%s)'
oracle.ops.combine_expression('^', ['"fleet_ship"."tonnage"', '%s'])  ->  'POWER("fleet_ship"."tonnage",%s)'
```

SQLite's `"POWER"` is a function Django registers on the connection where the SQLite library lacks one of its own (`django/db/backends/sqlite3/_functions.py:register`). MySQL's wrap `"&"`, `"|"`, `"<<"` and `"#"` in a conversion to a signed integer, the comment saying MySQL's return an unsigned one (`django/db/backends/mysql/operations.py:DatabaseOperations.combine_expression`).

A duration combined with something of another type becomes a `DurationExpression`, and one date or time less another a `TemporalSubtraction` ([Expressions: `resolve_expression` and `as_sql`](../sql/expressions.md)). `DurationExpression.as_sql` is the plain combination where `BaseDatabaseFeatures.has_native_duration_field` is set, on PostgreSQL and Oracle, whose duration columns are intervals. On SQLite and MySQL a duration is a `"bigint"` of microseconds, and each side that is one passes through `BaseDatabaseOperations.format_for_duration_arithmetic` before `BaseDatabaseOperations.combine_duration_expression` joins them (`django/db/models/expressions.py:DurationExpression.as_sql`), SQLite's with a call of `"django_format_dtdelta"`, another function Django registers (`django/db/backends/sqlite3/operations.py:DatabaseOperations.combine_duration_expression`). `BaseDatabaseOperations.subtract_temporals` writes the two sides with a minus between where `BaseDatabaseFeatures.supports_temporal_subtraction` is set, as all four backends' features set it (`django/db/backends/base/operations.py:BaseDatabaseOperations.subtract_temporals`), but each of the four writes its own subtraction of two dates: SQLite's and MySQL's call a function, and PostgreSQL's and Oracle's turn the difference, a number of days, into an interval (`django/db/backends/postgresql/operations.py:DatabaseOperations.subtract_temporals`). A voyage's sailing date plus three days, and less the first of January 2026, written for SQLite and, with nothing sent, PostgreSQL 17, MySQL 8.4 and Oracle 23:

```text recording=backends
arithmetic = Voyage.objects.annotate(due=models.F('sailed') + datetime.timedelta(days=3), gap=models.F('sailed') - models.Value(datetime.date(2026, 1, 1))).values('due', 'gap')
sql_for(arithmetic, sqlite)  ->  ('SELECT (django_format_dtdelta(\'+\', "fleet_voyage"."sailed", %s)) AS "due", django_timestamp_diff("fleet_voyage"."sailed", %s) AS "gap" FROM "fleet_voyage"', (259200000000, '2026-01-01'))
sql_for(arithmetic, postgresql)  ->  ('SELECT ("fleet_voyage"."sailed" + %s) AS "due", (interval \'1 day\' * ("fleet_voyage"."sailed" - %s)) AS "gap" FROM "fleet_voyage"', (datetime.timedelta(days=3), datetime.date(2026, 1, 1)))
sql_for(arithmetic, mysql)  ->  ('SELECT (`fleet_voyage`.`sailed` + INTERVAL %s MICROSECOND) AS `due`, TIMESTAMPDIFF(MICROSECOND, %s, `fleet_voyage`.`sailed`) AS `gap` FROM `fleet_voyage`', (259200000000, '2026-01-01'))
sql_for(arithmetic, oracle)  ->  ('SELECT ("FLEET_VOYAGE"."SAILED" + %s) AS "DUE", NUMTODSINTERVAL(TO_NUMBER("FLEET_VOYAGE"."SAILED" - %s), \'DAY\') AS "GAP" FROM "FLEET_VOYAGE"', (datetime.timedelta(days=3), datetime.date(2026, 1, 1)))
```

## Window frames

`WindowFrame.as_sql` hands its start and end to `BaseDatabaseOperations.window_frame_rows_start_end` for a `RowRange` and `BaseDatabaseOperations.window_frame_range_start_end` for a `ValueRange`, which turn them into words with `BaseDatabaseOperations.window_frame_value` and the class's constants ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](../sql/windows.md)). No backend of the four overrides them. PostgreSQL's features set `BaseDatabaseFeatures.only_supports_unbounded_with_preceding_and_following`, so that there a range frame from three values back to the current row is refused with `NotSupportedError` (`django/db/backends/base/operations.py:BaseDatabaseOperations.window_frame_range_start_end`). Written for SQLite and, with nothing sent, for PostgreSQL 17:

```text recording=backends
framed = Ship.objects.annotate(nearby=models.Window(models.Sum('tonnage'), order_by=models.F('tonnage').asc(), frame=models.ValueRange(start=-3, end=0))).values('name', 'nearby')
sql_for(framed, sqlite)  ->  ('SELECT "fleet_ship"."name" AS "name", SUM("fleet_ship"."tonnage") OVER (ORDER BY "fleet_ship"."tonnage" ASC RANGE BETWEEN 3 PRECEDING AND CURRENT ROW) AS "nearby" FROM "fleet_ship" ORDER BY 1 ASC', ())
sql_for(framed, postgresql)  ->  raises NotSupportedError: PostgreSQL only supports UNBOUNDED together with PRECEDING and FOLLOWING.
```

## Explaining a query: `explain_prefix` and `explain_query_prefix`

`BaseDatabaseOperations.explain_query_prefix` is what the compiler puts at the head of a statement that `QuerySet.explain` runs ([The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)). The base's returns `BaseDatabaseOperations.explain_prefix`, refusing with `NotSupportedError` where the features lack `BaseDatabaseFeatures.supports_explaining_query_execution`, and with `ValueError` a format not among `BaseDatabaseFeatures.supported_explain_formats`, or any option (`django/db/backends/base/operations.py:BaseDatabaseOperations.explain_query_prefix`). MySQL's ask for the format `"TREE"` where no format is given and the server is MySQL and not MariaDB (`django/db/backends/mysql/operations.py:DatabaseOperations.explain_query_prefix`). Asked of SQLite and, with no server, of PostgreSQL 17, MySQL 8.4 and Oracle 23:

```text recording=backends
sqlite.ops.explain_query_prefix()  ->  'EXPLAIN QUERY PLAN'
postgresql.ops.explain_query_prefix()  ->  'EXPLAIN'
mysql.ops.explain_query_prefix()  ->  'EXPLAIN FORMAT=TREE'
oracle.ops.explain_query_prefix()  ->  raises NotSupportedError: This backend does not support explaining query execution.
```

## Supported or not: `check_expression_support`, and conditions standing alone

`BaseDatabaseOperations.check_expression_support` is where a backend refuses, with `NotSupportedError`, an expression whose implementation on its database is problematic or nonexistent, and the base's does nothing. It is called by `Func.as_sql`, and so for every function and aggregate that compiles through it, and by the `as_sql` of several other expressions, `OrderBy` among them (`django/db/models/expressions.py:Func.as_sql`). Of the four, SQLite's alone overrides it, refusing `Sum`, `Avg`, `Variance` and `StdDev` over a date, a time or a datetime, which, its message says, SQLite stores as text, and `distinct` on an aggregate of several arguments (`django/db/backends/sqlite3/operations.py:DatabaseOperations.check_expression_support`).

`BaseDatabaseOperations.conditional_expression_supported_in_where_clause` says whether a true-or-false expression may stand alone where a condition goes: yes to anything where `BaseDatabaseFeatures.has_native_boolean_field` is set, which among the four only PostgreSQL's features set; elsewhere yes to an `Exists`, a lookup, a where node, or a conditional `RawSQL` or `ExpressionWrapper` of these, and no to the rest, a column of booleans among them (`django/db/backends/base/operations.py:BaseDatabaseOperations.conditional_expression_supported_in_where_clause`). `NegatedExpression.as_sql` asks it, and writes `"NOT"` or, where the answer is no, a `"CASE WHEN"` (`django/db/models/expressions.py:NegatedExpression.as_sql`).

## Limits: `max_name_length` and `max_in_list_size`

`BaseDatabaseOperations.max_in_list_size` is the most values an `"IN"` may hold, and `BaseDatabaseOperations.max_name_length` the longest name of a table, a column or an index, each `None` for no limit in the base; asked of SQLite and, with no server, of PostgreSQL 17, MySQL 8.4 and Oracle 23:

```text recording=backends
sqlite.ops.max_name_length()  ->  None
postgresql.ops.max_name_length()  ->  63
mysql.ops.max_name_length()  ->  64
oracle.ops.max_name_length()  ->  30
sqlite.ops.max_in_list_size()  ->  None
postgresql.ops.max_in_list_size()  ->  None
mysql.ops.max_in_list_size()  ->  None
oracle.ops.max_in_list_size()  ->  1000
```

`In.split_parameter_list_as_sql` splits a list longer than `BaseDatabaseOperations.max_in_list_size` into groups joined by `"OR"`. The longest name is asked, among other places, for a model's default table and a many-to-many field's table, cut with `truncate_name` to the default database's limit (`django/db/backends/utils.py:truncate_name`) ([The options: what a model keeps as `_meta`](../models/options.md)); by the model checks ([The model checks](../models/checks.md)); by the schema editor for the names of indexes and constraints ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)); and by Oracle's quoting.

## JSON paths: `compile_json_path`

`BaseDatabaseOperations.compile_json_path` writes the path to a key inside a JSON value: `"$"`, then a dot and the key in JSON's quotes, or a number through `BaseDatabaseOperations.format_json_path_numeric_index`, in brackets. A negative number is refused with `NotSupportedError` where `BaseDatabaseFeatures.supports_json_negative_indexing` is unset, as on MySQL and on Oracle before 21 (`django/db/backends/base/operations.py:BaseDatabaseOperations.compile_json_path`). The last item under a key, asked of SQLite and, with no server, of PostgreSQL 17, MySQL 8.4, Oracle 23 and Oracle 19:

```text recording=backends
sqlite.ops.compile_json_path(['tags', -1])  ->  '$."tags"[#-1]'
postgresql.ops.compile_json_path(['tags', -1])  ->  '$."tags"[-1]'
mysql.ops.compile_json_path(['tags', -1])  ->  raises NotSupportedError: Using negative JSON array indices is not supported on this database backend.
oracle.ops.compile_json_path(['tags', -1])  ->  '$."tags"[last-0]'
oracle19.ops.compile_json_path(['tags', -1])  ->  raises NotSupportedError: Using negative JSON array indices is not supported on this database backend.
```

The key transforms and the has-key lookups of a `JSONField` ask for a path on SQLite, MySQL and Oracle; on PostgreSQL they use its JSON operators (`django/db/models/fields/json.py:KeyTransform`).

## What the rest of Django asks for

The type a `Cast` casts to is the backend's entry in `BaseDatabaseOperations.cast_data_types`, where it has one, and otherwise the field's column type (`django/db/models/fields/__init__.py:Field.cast_db_type`) ([Column types: from a field to a column](column-types.md)). `BaseDatabaseOperations.unification_cast_sql` is wrapped round a `Case` that has an output field (`django/db/models/expressions.py:Case.as_sql`): no cast in the base, and on PostgreSQL a cast to the field's type for an IP address, a time or a UUID, since PostgreSQL, settling one type for the branches, would otherwise take text, which it could not by default cast back (`django/db/backends/postgresql/operations.py:DatabaseOperations.unification_cast_sql`). `BaseDatabaseOperations.integer_field_range` gives the range of each integer column, and `IntegerFieldOverflow` and `IntegerField.validators` ask it (`django/db/models/fields/__init__.py:IntegerField.validators`).

The schema editor asks for a table's tablespace, `BaseDatabaseOperations.tablespace_sql`, and for the end of a foreign key's clause, `BaseDatabaseOperations.deferrable_sql` and `BaseDatabaseOperations.fk_on_delete_sql` (`django/db/backends/base/operations.py:BaseDatabaseOperations.fk_on_delete_sql`) ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)). The commands that print SQL put it between `BaseDatabaseOperations.start_transaction_sql` and `BaseDatabaseOperations.end_transaction_sql` (`django/core/management/base.py:BaseCommand.execute`) ([Management commands](../commands.md)); `RunSQL` splits a script into statements with `BaseDatabaseOperations.prepare_sql_script` ([Migrations](../migrations.md)); the database cache culls with `BaseDatabaseOperations.cache_key_culling_sql` and reads values through `BaseDatabaseOperations.process_clob` (`django/core/cache/backends/db.py:DatabaseCache._cull`) ([Caching, files, mail, signals and tasks](../services.md)); and the test runner lays out the SQL of failing tests with `BaseDatabaseOperations.format_debug_sql` ([The test framework](../testing.md)).
