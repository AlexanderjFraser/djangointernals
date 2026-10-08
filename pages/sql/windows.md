---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite

`Window` is an expression whose function is applied over a partition of the rows and written as `function OVER (...)`; `WindowFrame`, with its two classes `RowRange` and `ValueRange`, says which rows of the partition the function sees. A condition on a window cannot stand in a statement's `"WHERE"`, so where a filter names one, `WhereNode.split_having_qualify` sets the condition aside and `SQLCompiler.get_qualify_sql` writes the statement inside another and tests the condition there.

An aggregate folds a group of rows into one value, and the statement has one row for each group. A **window** applies a function to a set of rows too, but reports the answer on every row: the number of each sailor within the crew of its ship, the sum of the rows before this one, the value in the row above. So a window has to carry three things beside its function: the partition, which rows are reckoned together; an ordering, in which they are reckoned; and a frame, which rows of the partition, counted from the current one, the function sees. It has to say two things about itself: that it is not an aggregate, so that no `"GROUP BY"` is made for it although its function may be `Sum` or `Count`; and that it is a window, so that a condition on it is kept out of the `"WHERE"`, where SQL has no window yet, and written in a clause of its own. And it has to be of its function's type. The source is `django/db/models/expressions.py:Window`, and the functions made for windows are the classes of `django/db/models/functions/window.py`.

The recording this section quotes was made from a running Django, on SQLite, over the models of the chapter's opening page: a line at the left is Python that was run, with its value after `->`, or the exception it raised; the lines set in under a line are the calls it set going, nested as they were made, with only the calls this section is about written down, and `->` what a call returned; a line that begins `SQL` is a statement as Django handed it to its cursor.

## What a `Window` holds

`Window.__init__` takes the expression, and the three clauses, `partition_by`, `order_by` and `frame`, each `None` unless given, and an `output_field` (`django/db/models/expressions.py:Window.__init__`). It refuses, with `ValueError`, an expression whose `window_compatible` is not true. The attribute is `False` on `BaseExpression`, so a column, a plain function or an arithmetic expression is refused; `Aggregate` sets it `True`, every class of `django/db/models/functions/window.py` has it `True`, and of Django's own classes no other sets it, so the expression of a window is an aggregate or a window function. One aggregate takes itself out again: `AnyValue.window_compatible` is `False` (`django/db/models/expressions.py:BaseExpression`, `django/db/models/aggregates.py:Aggregate`, `django/db/models/aggregates.py:AnyValue`).

```text recording=sql
Window(F('name'))  ->  raises ValueError: Expression 'F' isn't compatible with OVER clauses.
Window(RowNumber(), order_by=5)  ->  raises ValueError: Window.order_by must be either a string reference to a field, an expression, or a list or tuple of them not 5.
...
Window(RowNumber()).get_source_expressions(), Window(RowNumber(), partition_by='ship', order_by='name').get_source_expressions()  ->  ([RowNumber(), None, None, None], [RowNumber(), ExpressionList(F(ship)), OrderByList(F(name)), None])
Window(RowNumber(), partition_by='ship', order_by='name').resolve_expression(Sailor.objects.all().query).get_group_by_cols(), Window(Sum('id')).contains_aggregate, Window(Sum('id')).contains_over_clause  ->  ([Col(crew_sailor, crew.Sailor.ship), Col(crew_sailor, crew.Sailor.name)], False, True)
connection.features.supports_over_clause, connection.features.supports_frame_exclusion  ->  (True, True)
```

The two clauses are turned into expressions as the window is made, which is why the question about `get_source_expressions` shows them as objects. A partition given as one thing is made a tuple of one, and the tuple becomes an `ExpressionList`, a `Func` whose template is its arguments joined by commas; a string among them becomes an `F` as any argument of a `Func` does, so `partition_by="ship"` is `ExpressionList(F("ship"))`. The ordering goes through `OrderByList.from_param`, which accepts `None`, a string, an expression, or a list or tuple of them, an empty one counting as none, and refuses anything else with the `ValueError` the question with `order_by=5` shows. `OrderByList` is an `ExpressionList` whose template begins `"ORDER BY"`, and its constructor turns a string that begins with `"-"` into an `OrderBy` of the rest, descending; a string without the sign stays an `F` and is written with no direction after it (`django/db/models/expressions.py:ExpressionList`, `django/db/models/expressions.py:OrderByList`). The two list classes are told with the rest of the small expressions in [Expressions: `resolve_expression` and `as_sql`](expressions.md), and `OrderBy` in [ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md). The frame is kept as it was given, and the expression itself goes through `_parse_expressions` last, which leaves it as it is: anything without `window_compatible`, a string or a plain value among them, was refused before it got there.

`Window.get_source_expressions` returns the four in that order, the expression first, with `None` standing for a clause that was not given; `set_source_expressions` takes four back. That is the shape by which resolving, relabelling and `replace_expressions` reach into a window: each resolves whichever of the four is not `None`, and `None` is left as it is (`django/db/models/expressions.py:Window.get_source_expressions`). `Window._resolve_output_field` answers with the expression's output field, so a window over `Sum("tonnage")` is of the sum's type and one over `RowNumber` is an integer, unless an `output_field` was given.

Two marks are set on the class. `Window.contains_aggregate` is `False`, and the comment beside it gives the reason: the expression may be an aggregate, or contain one, and the `"GROUP BY"` that an aggregate brings into a query is not wanted. `Window.contains_over_clause` is `True`, and it is the only class of `django/db/models/expressions.py` that sets it so; `BaseExpression.contains_over_clause` is a cached property that is true where any source expression's is, and `WhereNode.contains_over_clause` walks a tree's children in the same way, so the mark climbs from a window through a lookup to the where node that holds it (`django/db/models/expressions.py:BaseExpression.contains_over_clause`, `django/db/models/sql/where.py:WhereNode.contains_over_clause`). The two marks together are how a window stands beside an aggregate in a query that groups: the grouping is the aggregate's doing, and the window's function adds nothing to it.

```text recording=sql
tail(Ship.objects.annotate(hands=Count('crew'), fleet=Window(Count('id'))))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id"', ())
```

`Window.get_group_by_cols` is what a window contributes when the compiler gathers the grouping: the columns of its partition and of its ordering, and not those of its expression (`django/db/models/expressions.py:Window.get_group_by_cols`). Where the query groups, each selected expression is asked for its columns, and a window partitioned by the ship puts the ship's column among them ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md)).

## `Window.as_sql`: the partition, the ordering and the frame after `"OVER"`

```text recording=sql
sql_of(Sailor.objects.annotate(n=Window(RowNumber(), partition_by=F('ship'), order_by='name')))[0][:200]  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM '
list(Sailor.objects.annotate(n=Window(RowNumber(), partition_by=F('ship'), order_by='name')).values_list('name', 'n'))  ->  [('Ada', 1), ('Bram', 2), ('Cora', 1), ('Dag', 2)]
  SQL SELECT "crew_sailor"."name" AS "name", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor"
...
sql_of(Sailor.objects.annotate(n=Window(Rank(), order_by=F('signed_on').desc())))[0][:160]  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", RANK() OVER (ORDER BY "crew_sailor"."signed_on" DESC) AS "n'
```

`Window.as_sql` first asks the connection's operations to check the expression, and then refuses, with `NotSupportedError`, a backend whose features say it has no `"OVER"` clause (`django/db/models/expressions.py:Window.as_sql`, `django/db/backends/base/features.py:BaseDatabaseFeatures.supports_over_clause`). The base features say `False`; SQLite's, as the recording asked, say `True`. Then it compiles its parts and puts them into `Window.template`, which is `"%(expression)s OVER (%(window)s)"`. The expression is compiled through the compiler. The partition is written by calling `ExpressionList.as_sql` directly with the template `"PARTITION BY %(expressions)s"`; the ordering and the frame are compiled through the compiler, so a vendor method of either is honoured, and the `"ORDER BY"` is the `OrderByList`'s own template. The three pieces are joined with one space and stripped, so a window with none of them is written `"OVER ()"`. The parameters are the expression's followed by the window's, in the order the pieces were written. In the first statement above, the ordering `"name"` was given as a string and stands with no direction; in the last, `F("signed_on").desc()` made an `OrderBy`, and the direction is written.

SQLite gets a method of its own for one case. `Window.as_sqlite` looks at the window's output field, and where it is a `DecimalField` makes a copy whose expression is given a `FloatField` as its output field, and compiles the copy through `SQLiteNumericMixin.as_sqlite`, which puts `"CAST(... AS NUMERIC)"` round the whole (`django/db/models/expressions.py:Window.as_sqlite`, `django/db/models/expressions.py:SQLiteNumericMixin`, `django/db/models/fields/__init__.py:DecimalField`). The comment says why the cast must go round the whole: it has to stand outside the window expression. An aggregate is a `Func` built on the same mixin, and compiled on its own it would cast itself; given a float field in the copy, it does not, and the one cast is the outer one. For any other output field the method is `as_sql` under another name.

```text recording=sql
sql_of(Sailor.objects.annotate(w=Window(Sum('id'), output_field=models.DecimalField())).values('w'))  ->  ('SELECT (CAST(SUM("crew_sailor"."id") OVER () AS NUMERIC)) AS "w" FROM "crew_sailor"', ())
```

## The frame: `WindowFrame`, `RowRange` and `ValueRange`

A **frame** names the rows of the partition the function sees from the current row: from a start to an end, each a number of rows or of values away, or unbounded. `WindowFrame` is the base, and the two classes differ in one attribute and one method: `RowRange.frame_type` is `"ROWS"`, a frame counted in rows, and `ValueRange.frame_type` is `"RANGE"`, a frame counted in values of the ordering, so that under `"RANGE"` the rows whose value equals the current row's are its peers and stand in the frame with it (`django/db/models/expressions.py:WindowFrame`, `django/db/models/expressions.py:RowRange`, `django/db/models/expressions.py:ValueRange`). What the two kinds mean to the database is the documentation's subject and not the source's (`docs/ref/models/expressions.txt`).

```text recording=sql
sql_of(Sailor.objects.annotate(n=Window(Sum('id'), order_by='id', frame=RowRange(start=-1, end=0))))[0][:200]  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", SUM("crew_sailor"."id") OVER (ORDER BY "crew_sailor"."id" ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)'
sql_of(Sailor.objects.annotate(n=Window(Sum('id'), order_by='id', frame=ValueRange(start=None, end=0, exclusion=WindowFrameExclusion.CURRENT_ROW))))[0][:230]  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", SUM("crew_sailor"."id") OVER (ORDER BY "crew_sailor"."id" RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW EXCLUDE CURRENT ROW) '
...
RowRange(start=1, exclusion='ties')  ->  raises TypeError: RowRange.exclusion must be a WindowFrameExclusion instance.
str(RowRange(start=-1, end=0)), str(ValueRange()), ValueRange().as_sql(compiler, connection)  ->  ('ROWS BETWEEN 1 PRECEDING AND CURRENT ROW', 'RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING', ('RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING', ()))
```

`WindowFrame.__init__` takes a start, an end and an exclusion, each `None` by default, keeps the start and the end as a `Value` each, and refuses with `TypeError` an exclusion that is neither `None` nor a member of `WindowFrameExclusion`, the enumeration of `"CURRENT ROW"`, `"GROUP"`, `"TIES"` and `"NO OTHERS"` (`django/db/models/expressions.py:WindowFrame.__init__`, `django/db/models/expressions.py:WindowFrameExclusion`). A number is read as a distance from the current row: zero is the current row, a negative number is that many rows or values before it, a positive number that many after, and `None` is unbounded, backwards for the start and forwards for the end. The words are the backend's: `WindowFrame.as_sql` hands the two numbers to `WindowFrame.window_frame_start_end`, which the two classes define as a call of `BaseDatabaseOperations.window_frame_rows_start_end` or of `BaseDatabaseOperations.window_frame_range_start_end`, and the operations object turns each number into text with `BaseDatabaseOperations.window_frame_value` from its own constants, `PRECEDING`, `FOLLOWING`, `CURRENT_ROW`, `UNBOUNDED_PRECEDING` and `UNBOUNDED_FOLLOWING` (`django/db/models/expressions.py:WindowFrame.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.window_frame_rows_start_end`). The template is `"%(frame_type)s BETWEEN %(start)s AND %(end)s%(exclude)s"`, and the end is always written, `"UNBOUNDED FOLLOWING"` where none was given, as the answer to `str(ValueRange())` shows. The frame has no parameters: the numbers are written into the text.

The two operations methods check the numbers, and not alike. For `"ROWS"`, each must be an integer or `None`, and the start may not be greater than the end, each refusal a `ValueError`. For `"RANGE"`, the start must be zero, negative or `None` and the end zero, positive or `None`: a range that begins after the current row or ends before it is refused, where a row frame may do either (`django/db/backends/base/operations.py:BaseDatabaseOperations.window_frame_range_start_end`). After that `window_frame_range_start_end` reads one feature, `only_supports_unbounded_with_preceding_and_following`, and where it is set and a distance was given refuses with `NotSupportedError`, naming the backend: of Django's own backends PostgreSQL alone sets it (`django/db/backends/postgresql/features.py`). The exclusion is appended by `WindowFrame.get_exclusion` as `" EXCLUDE "` and the member's value, and `as_sql` refuses one with `NotSupportedError` where `supports_frame_exclusion` is off; the base features say `False`, and SQLite's say `True` (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_frame_exclusion`). `WindowFrame.__str__` works the same words out for itself from the default connection's constants, which is why `str(RowRange(start=-1, end=0))` could be answered without a compiler, and `WindowFrame.get_group_by_cols` returns nothing, so a frame never reaches a `"GROUP BY"`.

## The window functions

The classes of `django/db/models/functions/window.py` are each a `Func` with `window_compatible` set, a `function` name on all but the base `LagLeadFunction`, and for some an `output_field` of their own; none has a template of its own, so each is written as its function name and its arguments in parentheses, and `RowNumber()` is `"ROW_NUMBER()"`. The ones that take an expression answer with that expression's type: `LagLeadFunction` and `NthValue` define `_resolve_output_field` to return the first source's output field, and `FirstValue` and `LastValue` leave the inference to `Func`, which for one argument comes to the same (`django/db/models/functions/window.py:LagLeadFunction`, `django/db/models/functions/window.py:NthValue`). The output fields named below are of `django/db/models/fields/__init__.py:IntegerField` and `django/db/models/fields/__init__.py:FloatField`.

| class | writes | takes | output field |
|---|---|---|---|
| `RowNumber` | `"ROW_NUMBER()"` | nothing | an integer |
| `Rank` | `"RANK()"` | nothing | an integer |
| `DenseRank` | `"DENSE_RANK()"` | nothing | an integer |
| `PercentRank` | `"PERCENT_RANK()"` | nothing | a float |
| `CumeDist` | `"CUME_DIST()"` | nothing | a float |
| `Ntile` | `"NTILE(%s)"` | the number of buckets, 1 unless given; zero or less is refused | an integer |
| `FirstValue` | `"FIRST_VALUE(...)"` | one expression, `arity` 1 | the expression's |
| `LastValue` | `"LAST_VALUE(...)"` | one expression, `arity` 1 | the expression's |
| `NthValue` | `"NTH_VALUE(..., %s)"` | an expression and the position, 1 unless given; `None` for the expression or a position of zero or less is refused | the expression's |
| `Lag` | `"LAG(..., %s[, %s])"` | an expression, an offset of 1 unless given, and a default written only when one is given; `None` for the expression or an offset of zero or less is refused | the expression's |
| `Lead` | `"LEAD(..., %s[, %s])"` | the same as `Lag` | the expression's |

*The window functions, with what each writes on SQLite and what its constructor refuses with `ValueError`. A number given to a constructor becomes a `Value` and is sent as a parameter, which is the `%s` in the second column.*

```text recording=sql
sql_of(Sailor.objects.annotate(n=Window(Lag('name', offset=1, default=Value('-')), order_by='id')))[0][:160]  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", LAG("crew_sailor"."name", %s, %s) OVER (ORDER BY "crew_sail'
sql_of(Sailor.objects.annotate(n=Window(Ntile(2), order_by='id')))[0][:120]  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", NTILE(%s) OVER (ORD'
sql_of(Sailor.objects.annotate(n=Window(DenseRank(), partition_by=['ship', 'signed_on__year'], order_by=['-name', 'id'])))[0][:260]  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", DENSE_RANK() OVER (PARTITION BY "crew_sailor"."ship_id", django_datetime_extract(%s, "crew_sailor"."signed_on", %s, %s) ORDER BY "crew_sailor"."name" DESC, "cr'
```

The default of the `Lag` is given as `Value("-")` and not as the string: a string argument of a `Func` is read as a field's name, and a default of `"-"` would have been an `F`. The question with `DenseRank` shows a partition of two names, the second with a transform in it: `"signed_on__year"` became an `F`, and resolving the `F` against the query found the field and applied the transform, as it would in a filter ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). The function it was written as, `"django_datetime_extract"`, is one Django registers with SQLite, and another backend writes its own ([Transforms and database functions: `Transform` and `Func`](functions.md)). The aggregates that may stand in a window, and what each writes, are in [Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md).

## A filter on a window

A window reaches the where tree as any annotation does: `filter(n=1)` on a queryset whose `"n"` is a window resolves the name to the window itself, and the lookup made of it, `IntegerFieldExact` with the window on its left, is the tree's child ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)). The lookup's `contains_over_clause` is true through its left side, and so is the tree's. The compiler cannot write that lookup into the `"WHERE"`: a window is worked out over the rows the `"WHERE"` has let through, so a condition on one there would be a condition on something not yet known. What Django does instead is write the statement without the condition, inside another statement that reads its rows as a table and tests the condition on them. The name it gives the device, in the code and in the alias of the inner statement, is `"qualify"`.

```text recording=sql
Filtering on a window: split_having_qualify puts the condition aside, and get_qualify_sql wraps the statement in a subquery
    numbered = Sailor.objects.annotate(n=Window(RowNumber(), partition_by='ship', order_by='name'))
    numbered.filter(n=1).query.get_compiler('default').as_sql()
      SQLCompiler.as_sql
        SQLCompiler.pre_sql_setup
          SQLCompiler.get_select  ->  (5 columns, klass_info for Sailor, {'n': 4})
          SQLCompiler.get_order_by  ->  []
          WhereNode.split_having_qualify  ->  (None, None, (AND: IntegerFieldExact(<Window: RowNumber() OVER (PARTITION BY Col(crew_sailor, crew.Sailor.ship)Col(crew_sailor, crew.Sailor.name))>, 1)))
          -> (extra_select of 0, order_by of 0, group_by of 0)
        SQLCompiler.get_qualify_sql
          SQLCompiler.get_select  ->  (5 columns, klass_info for Sailor, {'n': 4})
          SQLCompiler.get_order_by  ->  []
          SQLCompiler.as_sql(with_col_aliases=True)
            SQLCompiler.pre_sql_setup
              SQLCompiler.get_select  ->  (5 columns, klass_info for Sailor, {'n': 4})
              SQLCompiler.get_order_by  ->  []
              WhereNode.split_having_qualify  ->  ((AND: ), None, None)
              -> (extra_select of 0, order_by of 0, group_by of 0)
            -> ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor"', ())
          -> ('SELECT * FROM ( SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" ) "qualify" WHERE "n" = %s', (1,))
        -> ('SELECT * FROM ( SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" ) "qualify" WHERE "n" = %s', (1,))
    list(numbered.filter(n=1).values_list('name', flat=True))  ->  ['Ada', 'Cora']
      SQL SELECT "name" FROM ( SELECT * FROM ( SELECT "crew_sailor"."name" AS "name", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "qual0" FROM "crew_sailor" ) "qualify" WHERE "qual0" = %s ) "qualify_mask" with params (1,)
```

The block's first line makes numbered: every sailor, numbered within its ship's crew by name, under the annotation `"n"`. The filter asks for the first of each crew.

### The split

`SQLCompiler.pre_sql_setup` has the query's where tree divide itself into three with `WhereNode.split_having_qualify`: the part for the `"WHERE"`, the part that compares an aggregate and goes to the `"HAVING"`, and the part that refers to a window, each a node or `None`, and keeps the three on the compiler (`django/db/models/sql/compiler.py:SQLCompiler.pre_sql_setup`, `django/db/models/sql/where.py:WhereNode.split_having_qualify`). The first two parts are the subject of [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md); the third is this section's. A tree in which nothing is an aggregate or a window is returned whole as the first part at once. A node cannot always be divided: under an `"OR"` that is not negated, under an `"AND"` that is, or under `"XOR"`, the children belong together, since `a OR b` is not `a` in one clause and `b` in another, and the method computes that first, as a flag. A node that must stay together and holds an aggregate and no window goes whole to the `"HAVING"` without any walk. Otherwise the method walks the node's children, sending each child that is itself a node through the same split, each other child with `contains_over_clause` to the qualify part, each with `contains_aggregate` to the having part, and the rest to the where part, and makes a node of each part that has anything in it, with the connector and the negation of the node it came from. The recording's line for `split_having_qualify` shows the result for `filter(n=1)`: nothing for the `"WHERE"`, nothing for the `"HAVING"`, and the lookup on the window as the qualify part.

Where the flag is set and a window is among the children, the whole node goes to the qualify part, unless the node has plain children beside the window and the query groups, which the caller passes in as `must_group_by=True`: then the method raises `NotImplementedError`, with the message the documentation quotes (`docs/ref/models/expressions.txt`). The comment beside the test says that such a disjunction can be pushed down to the qualify part as long as no conditional aggregation is involved, and admits the test is wider than it has to be: in theory only a plain condition on a multi-valued relation could change what the groups contain, but that is hard to tell.

```text recording=sql
sql_of(numbered.filter(Q(n=1) | Q(name='Dag')))[0][120:]  ->  '"crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" ) "qualify" WHERE ("n" = %s OR "col2" = %s)'
sql_of(numbered.filter(n=1, name__startswith='A'))[0][120:]  ->  '"crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE %s ESCAPE \'\\\' ) "qualify" WHERE "n" = %s'
```

The statement with the `"OR"` is of a window and a plain condition on a query that does not group: the node went whole to the qualify part, and the condition on the name is tested outside, against the column's alias in the inner statement. The one with `"name__startswith"` is an `"AND"`: divided, the condition on the name stands in the inner statement's `"WHERE"`, and only the window's in the outer one. The `"LIKE ... ESCAPE"` is SQLite's way of writing `"startswith"` ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)).

```text recording=sql
numbered.annotate(hands=Count('id')).filter(Q(n=1) | Q(hands__gt=1))  ->  <SailorQuerySet [<Sailor: Ada>, <Sailor: Cora>]>
  SQL SELECT * FROM ( SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n", COUNT("crew_sailor"."id") AS "hands" FROM "crew_sailor" GROUP BY 1, 2, 3, 4 ) "qualify" WHERE ("n" = %s OR "hands" > %s) LIMIT 21 with params (1, 1)
...
sql_of(numbered.annotate(hands=Count('id')).filter(Q(n=1) | Q(name='Dag')))  ->  raises NotImplementedError: Heterogeneous disjunctive predicates against window functions are not implemented when performing conditional aggregation.
```

An `"OR"` of a window and an aggregate on a query that groups is allowed, since no plain condition is among the children: the node went to the qualify part whole, aggregate and all, and the inner statement groups while the outer one tests both. A plain condition under an `"OR"` with the window, on the same grouped query, is the `NotImplementedError`.

### `get_qualify_sql`

With a qualify part set, `SQLCompiler.as_sql` does not assemble the clauses itself. After the branch for a compound statement, and before the plain one, it calls `SQLCompiler.get_qualify_sql` and takes what that returns as the statement, then sets its own ordering aside, since the method has written one (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.get_qualify_sql`).

The whole method turns on one constraint: the outer statement can name only what the inner one selects, and only by alias. So the inner query is given an alias for every column, each expression the condition refers to is replaced by the alias of the column that holds it, and an expression the inner query does not select is added to it under an alias of its own for the test and masked out again afterwards.

`get_qualify_sql` begins with the inner query: a clone of the query, marked as a subquery, whose where tree is a new node holding the where part and the having part, so that the condition on the window is the one thing left out. It calls `SQLCompiler.get_select` with `with_col_aliases=True`, which gives every selected column an alias, `"col1"`, `"col2"` and on, where the column has none of its own, and an annotation its own name ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)), and makes a dictionary from each selected expression to its alias.

The function it defines next, over a list of expressions, works out the replacements. An expression that is selected is replaced by its alias. Otherwise a lookup is opened, its sources going on the list; a `Ref` to a selected alias is left as it is, and a `Ref` to anything else is opened like a lookup. Anything else is added to the inner query as an annotation under `"qual0"`, `"qual1"` and on, with `Query.add_annotation`, and replaced by that alias (`django/db/models/sql/query.py:Query.add_annotation`); the comment at the top of the method says when this happens, a window that `values` or `alias` has masked out of the selection being filtered on. The function is run over the leaves of the qualify tree, which `WhereNode.leaves` yields, and the tree is rewritten with `WhereNode.replace_expressions`, each expression that has a replacement becoming a `Ref` to its alias (`django/db/models/sql/where.py:WhereNode.leaves`, `django/db/models/sql/where.py:WhereNode.replace_expressions`). A `Ref` writes its alias, quoted, and nothing more, which is why the outer `"WHERE"` reads `"n" = %s` and `"col2" = %s` ([Expressions: `resolve_expression` and `as_sql`](expressions.md)).

The ordering is treated the same way. For each expression `SQLCompiler.get_order_by` returns, the function runs over its sources, and a copy of the expression with the replacements is kept to be written outside. The inner query then gets a compiler of its own, made with the same connection and the outer compiler's `elide_empty`, and its `as_sql` is called with `with_limits=False` and `with_col_aliases=True`; the comments give both reasons: the limits must be applied to the outer query, or rows would be pruned before the condition is tested, and every column needs an alias of its own so that the outer statement can refer to it. The result is a list of pieces, `"SELECT * FROM ("`, the inner statement, `")"`, the quoted name `"qualify"`, `"WHERE"` and the compiled qualify part. Where any `"qual"` alias was added, the whole is wrapped once more, in a `"SELECT"` of the aliases the outer compiler's own selection had, from the pieces as a subquery named `"qualify_mask"`: the comment says that aliases unmasked for filtering must be masked back. That is the shape of the last statement in the recording above, where `values_list("name")` had masked the window out of the selection, `"qual0"` was added to the inner statement, and the outermost `"SELECT"` names `"name"` alone. Last, where there was an ordering, `"ORDER BY"` and the rewritten expressions are appended; the comment says why it is repeated outside when the inner statement already has it: the SQL specification does not say whether a derived table's ordering carries through, so it is repeated on the outermost query to make sure.

```text recording=sql
sql_of(numbered.filter(n=1).order_by('-name'))[0][120:]  ->  '"crew_sailor"."signed_on" AS "col4", ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor" ORDER BY "crew_sailor"."name" DESC ) "qualify" WHERE "n" = %s ORDER BY "col2" DESC'
```

Back in `as_sql`, the statement goes on as any other does from that point: a prefix for `"EXPLAIN"` where one was asked for, no `"ORDER BY"` since the ordering was set aside, and then the limit and the offset, which is why the `LIMIT 21` of the `"OR"` statement above stands after the outer `"WHERE"` ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)).

```text figure=the-qualify-rewrite
a condition on a window, which SQL will not take in a WHERE:

    SELECT ..., ROW_NUMBER() OVER (PARTITION BY ship_id ORDER BY name) AS n
    FROM crew_sailor
    WHERE n = 1

what get_qualify_sql writes, two statements where one was wanted:

    SELECT * FROM (                                                 <- the outer statement
        SELECT id AS col1, name AS col2, ship_id AS col3, ...,      <- the inner query: a clone, with the WHERE and HAVING parts
               ROW_NUMBER() OVER (...) AS n                            and no limit, written by its compiler's
        FROM crew_sailor                                               as_sql(with_col_aliases=True)
        ORDER BY name DESC
    ) "qualify"
    WHERE "n" = 1                                                   <- the qualify part, each expression a Ref to an alias
    ORDER BY "col2" DESC  LIMIT 21                                  <- the ordering repeated outside; the limit, from as_sql

and a third, where values() had masked the window out of the selection:

    SELECT "name" FROM (                                            <- a third statement round the two
        SELECT * FROM (
            SELECT ..., ROW_NUMBER() OVER (...) AS "qual0" FROM crew_sailor
        ) "qualify"                                                 <- the window the selection had masked,
        WHERE "qual0" = 1                                              selected under "qual0" for the test
    ) "qualify_mask"                                                <- the selection masked again
```

*The rewrite of a filter on a window. The statement the filter asks for, which no `"WHERE"` can hold, becomes an inner statement without the condition and an outer one that reads its rows by their aliases and tests the condition there; a window the selection had masked is selected under a `"qual"` alias for the test and masked again by a third statement round the two.*

A compound query never reaches this branch: `as_sql` looks for a combinator first, and a combined queryset refuses a filter ([Two queries into one: `combine` and `get_combinator_sql`](combining.md)).

## A window in an aggregation, and from an outer query

`Query.get_aggregation` does not take the plain way, making the aggregates the query's only annotations, where a window is involved. It looks for an aggregate that refers to an annotation with `contains_over_clause` set, and for a qualify part in the where tree, and for either sends the query inside an `AggregateQuery`, the window selected in the inner statement and the aggregate reading its alias outside (`django/db/models/sql/query.py:Query.get_aggregation`). [Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md) has the method; the statement it makes here is this:

```text recording=sql
numbered.aggregate(m=Max('n'))  ->  {'m': 2}
  SQL SELECT MAX("n") FROM (SELECT ROW_NUMBER() OVER (PARTITION BY "crew_sailor"."ship_id" ORDER BY "crew_sailor"."name") AS "n" FROM "crew_sailor") subquery
```

A subquery may not reach an outer query's window either. `OuterRef` resolves to a `ResolvedOuterRef`, and when that in turn is resolved against the outer query, `ResolvedOuterRef.resolve_expression` raises `NotSupportedError` where what it found has `contains_over_clause` set, naming the reference (`django/db/models/expressions.py:ResolvedOuterRef.resolve_expression`). The two classes, and how a query stands inside another, are [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md).
