---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons

A `Lookup` is the comparison at the end of a filter's name: a left side, a right side prepared for the left side's type, and an `as_sql` that writes the two with an operator between. `BuiltinLookup` takes the operator from the backend's table, and the classes of `django/db/models/lookups.py` registered on `Field`, from `Exact` and `In` to `IsNull` and `IRegex`, are what every field answers to, with the integer, year and UUID lookups registered beside them.

A lookup has four things to do. It has to hold a left side, a column or an expression, and a right side, a value or another expression. It has to prepare the right side for the left side's type before any SQL exists: `"480"` given for a column of integers becomes `480`, and `"x"` is refused, when the filter is built and not when the rows are wanted. It has to write the comparison for one backend, since `=` is the same everywhere and a case-insensitive match is not. And it sometimes has to decide the answer without the database: a comparison with an empty list matches nothing, an integer past the column's range matches nothing or everything, and `"IS NULL"` of a constant is known before it is written.

What follows is recorded from a running Django, on SQLite, over the shipping line of the chapter's opening page ([From QuerySet to SQL](../sql.md)): a line at the left margin is Python as it was run, with its value after `->` where it is an expression, or the word "raises" and the exception; under a line of Python stand the statements it sent, each on a line that begins `SQL`, as Django handed it to its cursor. Which class a word of a filter's name finds is settled before any of this, by `Query.build_lookup` and the registry; [From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md) and [The lookup registry: `RegisterLookupMixin`](../querysets/lookups.md) have that.

## `Lookup`: a comparison as an expression

`Lookup` is built on `Expression`, and a lookup is an expression whose value is true or false of a row: it can be resolved, compiled, compared with another and selected as a column ([Expressions: `resolve_expression` and `as_sql`](expressions.md)). `Lookup.__init__` takes the two sides and prepares them in a fixed order (`django/db/models/lookups.py:Lookup.__init__`). First the right side, through `Lookup.get_prep_lookup`, while the left side is still as it was given; then the left side, through `Lookup.get_prep_lhs`, which keeps anything that can resolve itself and wraps anything else in a `Value`. Then it asks the left side for its **bilateral transforms**, the transforms in the chain above the column that are marked to apply to the right side too, and keeps the list; a transform that is bilateral refuses, with `NotImplementedError`, a `Query` as the right side, the comment saying that it cannot work and the user is better warned at once.

`get_prep_lookup` is where the value meets the field (`django/db/models/lookups.py:Lookup.get_prep_lookup`). A right side that can resolve itself, an `F`, a `Value` or a `Query`, is kept as it is. Otherwise, where the left side has an output field with a `get_prep_value`, the value goes through it, and that method is the field's: `IntegerField.get_prep_value` makes an `int` of the value or raises `ValueError` naming the field, `Field.get_prep_value` itself only unwraps a lazy string ([A field, the base class](../models/fields.md), `django/db/models/fields/__init__.py:IntegerField.get_prep_value`). A left side with no output field, a plain value, gets a plain right side wrapped in a `Value`. One class attribute turns the step off: `Lookup.prepare_rhs`, false on the lookups that want the value as the program gave it. A second, `Lookup.can_use_none_as_rhs`, is read only by `build_lookup`, before it turns a `None` into `"isnull"`; of Django's own lookups, `JSONExact` on `JSONField`, `KeyTransformExact` through it, and `KeyTransformIExact` on a key transform set it ([Content types, static files and the other contrib apps](../contrib.md), `django/db/models/fields/json.py:JSONField`).

The following lines put a lookup together by hand. Here tonnage is the column `"tonnage"` of the ships' table, a `Col`, and compiler is a compiler for a query of all ships.

```text recording=sql
Exact(tonnage, '480').rhs, Exact(tonnage, '480').lhs, Exact(tonnage, 480).rhs_is_direct_value(), Exact(tonnage, F('id')).rhs_is_direct_value()  ->  (480, Col(fleet_ship, fleet.Ship.tonnage), True, True)
Exact(tonnage, 'x')  ->  raises ValueError: Field 'tonnage' expected a number but got 'x'.
Exact(480, 480), Exact(480, 480).lhs  ->  (Exact(Value(480), Value(480)), Value(480))
type(Exact(tonnage, 480).output_field).__name__, Exact(tonnage, 480).conditional, Exact(tonnage, 480).lookup_name, Exact.prepare_rhs, IsNull.prepare_rhs, Exact.can_use_none_as_rhs  ->  ('BooleanField', True, 'exact', True, False, False)
Exact(tonnage, 480).get_source_expressions(), Exact(tonnage, F('id')).resolve_expression(Ship.objects.all().query).get_source_expressions()  ->  ([Col(fleet_ship, fleet.Ship.tonnage)], [Col(fleet_ship, fleet.Ship.tonnage), Col(fleet_ship, fleet.Ship.id)])
```

The string became an integer and the bad string was refused as the lookup was made. Two plain values became two `Value` objects. The rest of what a lookup is as an expression is on the fourth line: `Lookup.output_field` is a `django.db.models.fields.BooleanField`, so `conditional` is true and a lookup may stand as a filter by itself and be chosen between in a `Case` ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)); `Lookup.lookup_name` is the word the class is registered under when `register_lookup` is given no other. `Lookup.rhs_is_direct_value` is whether the right side lacks an `as_sql`, which a plain value lacks and an `F` not yet resolved lacks too, as the first line shows; `Lookup.get_source_expressions` is the left side alone for a direct value and both sides otherwise, which is what the last line shows before and after resolving (`django/db/models/lookups.py:Lookup.rhs_is_direct_value`).

`Lookup.resolve_expression` copies the lookup, resolves its left side against the query, and its right side where that can be resolved, and marks the copy with `is_summary` where it was asked to summarise (`django/db/models/lookups.py:Lookup.resolve_expression`); it is what binds a lookup made without a query to the tables of the query it is used on. `Lookup.identity` is the class and the two sides; `Lookup.__eq__` compares it, and `Lookup.__hash__` hashes it through `make_hashable`, for a right side that is a list (`django/db/models/lookups.py:Lookup.identity`), so that two lookups made alike are equal and hash alike, as expressions are. Selected as a column rather than filtered on, a lookup is wrapped by `Lookup.select_format` in `CASE WHEN ... THEN 1 ELSE 0 END` where the backend cannot select a condition, and gives the grouping the columns of its sources through `Lookup.get_group_by_cols`; `Lookup.allowed_default` is whether both sides may stand in a database default.

## The two halves: `process_lhs` and `process_rhs`

A lookup writes its SQL in two halves and puts them together. `Lookup.process_lhs` resolves the left side against the compiler's query where it can resolve itself, compiles it, and puts it in parentheses where it is itself a lookup, so that a comparison of a comparison keeps its precedence (`django/db/models/lookups.py:Lookup.process_lhs`). `Lookup.process_rhs` has more cases (`django/db/models/lookups.py:Lookup.process_rhs`). Where there are bilateral transforms, a direct value is wrapped in a `Value` with the left side's output field, the transforms are applied to it, and the result is resolved, so that what follows sees an expression. An expression is compiled, and its SQL put in parentheses unless it is a `Value` or begins with one already, the comment saying that a doubled pair is misread by some backends, SQLite's subqueries among them; a `ColPairs`, the columns of a composite key, is refused with `ValueError` as a value. A direct value goes to `Lookup.get_db_prep_lookup`, which on `Lookup` itself returns a `%s` and the value as it is.

```text recording=sql
Exact(tonnage, 480).process_lhs(compiler, connection), Exact(tonnage, 480).process_rhs(compiler, connection), Exact(tonnage, 480).get_rhs_op(connection, '%s')  ->  (('"fleet_ship"."tonnage"', ()), ('%s', [480]), '= %s')
Exact(tonnage, 480).as_sql(compiler, connection), Exact(tonnage, F('id')).resolve_expression(Ship.objects.all().query).as_sql(compiler, connection)  ->  (('"fleet_ship"."tonnage" = %s', (480,)), ('"fleet_ship"."tonnage" = ("fleet_ship"."id")', ()))
Exact(tonnage, Ship.objects.filter(pk=1).values('tonnage')[:1].query).resolve_expression(Ship.objects.all().query).as_sql(compiler, connection)  ->  ('"fleet_ship"."tonnage" = (SELECT "U0"."tonnage" AS "tonnage" FROM "fleet_ship" "U0" WHERE "U0"."id" = %s ORDER BY "U0"."name" ASC LIMIT 1)', (1,))
```

The first line is the two halves and the operator, the second the whole: a plain value becomes a placeholder and a parameter, a column on the right is written in parentheses, and a query on the right is written as a subquery in its own parentheses, which is why none are added ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). `Lookup.as_oracle` is the one vendor method on the base class: where both sides are conditional, each side that Oracle would accept alone in a `"WHERE"` is wrapped in a `Case` that yields `True` or `False`, since that backend will not compare an `"EXISTS"` or a filter with another expression as it stands (`django/db/models/lookups.py:Lookup.as_oracle`).

> **Changed in 6.0.** `as_sql`, `process_lhs` and `process_rhs` of a lookup or an expression are to return their parameters as a tuple; a list was accepted before, and the release notes say the mixture caused interoperability problems. `BuiltinLookup.as_sql` unpacks both halves' parameters into one tuple, and 6.0.3 fixed a crash in a subclass of a builtin lookup that had not been updated to accept either (`docs/releases/6.0.txt`, `docs/releases/6.0.3.txt`).

### The bilateral transforms

A transform marked `bilateral` is applied to the right side as well as the left, so that `name__shout='ada'` compares `"UPPER(name)"` with `"UPPER('ada')"` ([Transforms and database functions: `Transform` and `Func`](functions.md)). `Transform.get_bilateral_transforms` collects, from the column outwards, the classes of the transforms in the chain that are marked so (`django/db/models/lookups.py:Transform.get_bilateral_transforms`); `Lookup.apply_bilateral_transforms` applies each class to a value in that order, and `Lookup.batch_process_rhs` does the same for each of several values, wrapping each in a `Value` of the left side's type, resolving and compiling it, and otherwise hands the values to `get_db_prep_lookup` and returns a placeholder for each (`django/db/models/lookups.py:Lookup.batch_process_rhs`). The recording registers a transform of its own, Shout, on `CharField` for one block, an `"UPPER"` with `bilateral = True`, and `Upper` beside it is the same function without the mark (`django/db/models/fields/__init__.py:CharField`):

```text recording=sql
tail(Sailor.objects.filter(name__upper='ADA'))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") = %s', ('ADA',))
tail(Sailor.objects.filter(name__shout='ada'))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") = (UPPER(%s))', ('ada',))
tail(Sailor.objects.filter(name__shout__in=['ada', 'bram']))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") IN (UPPER(%s), UPPER(%s))', ('ada', 'bram'))
tail(Sailor.objects.filter(name__shout__startswith='a'))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") LIKE REPLACE(REPLACE(REPLACE((UPPER(%s)), \'\\\', \'\\\\\'), \'%%\', \'\\%%\'), \'_\', \'\\_\') || \'%%\' ESCAPE \'\\\'', ('a',))
tail(Sailor.objects.filter(name__lower__shout__exact='ada'))  ->  ('FROM "crew_sailor" WHERE UPPER(LOWER("crew_sailor"."name")) = (UPPER(%s))', ('ada',))
Sailor.objects.filter(name__shout__in=Sailor.objects.values('name'))  ->  raises NotImplementedError: Bilateral transformations on nested querysets are not implemented.
entry(Sailor.objects.filter(name__shout='ada')).bilateral_transforms, entry(Sailor.objects.filter(name__shout='ada')).lhs.get_bilateral_transforms(), entry(Sailor.objects.filter(name__upper='ADA')).bilateral_transforms  ->  ([<class '__main__.Shout'>], [<class '__main__.Shout'>], [])
```

With `Upper` the value is a parameter; with Shout it is `"UPPER(%s)"`, in parentheses because it is now an expression, and each value of an `in` is transformed in turn. The `"startswith"` takes the road for an expression, which the section on `IExact` and the pattern lookups tells, because a bilateral transform makes the value one. The queryset is refused by `__init__`. The last line is the list each lookup kept: the Shout class for the one, nothing for the other.

## `BuiltinLookup`: the operator from the backend's table

`BuiltinLookup` is the base of every lookup registered on `Field`, and its `as_sql` is the plain case: the left half, the right half, and between them the operator, the parameters of the two halves joined in that order (`django/db/models/lookups.py:BuiltinLookup.as_sql`). `BuiltinLookup.get_rhs_op` takes the operator from `operators`, a dictionary on the connection's `DatabaseWrapper` from a lookup's name to a string with a `%s` for the right half, so that `"= %s"` becomes `= %s` and SQLite's `"LIKE %s ESCAPE '\'"` becomes the same with the placeholder inside (`django/db/models/lookups.py:BuiltinLookup.get_rhs_op`, `django/db/backends/sqlite3/base.py:DatabaseWrapper.operators`). Each backend has its own table, and the differences are the dialects': PostgreSQL writes `"iexact"` as `"= UPPER(%s)"` and `"regex"` as `"~ %s"`, MySQL has no entry for `"regex"` at all. `BuiltinLookup.process_lhs` wraps the left half in what `BaseDatabaseOperations.lookup_cast` returns for the lookup's name and the field's internal type, `"%s"` on the base class and on SQLite, a cast to text on PostgreSQL for `"iexact"`, the pattern and the regex lookups, with an `"UPPER"` round it for `"iexact"`, `"icontains"`, `"istartswith"` and `"iendswith"`, an `"UPPER"` or a `"DBMS_LOB.SUBSTR"` on Oracle (`django/db/models/lookups.py:BuiltinLookup.process_lhs`, `django/db/backends/base/operations.py:BaseDatabaseOperations.lookup_cast`, `django/db/backends/postgresql/operations.py:DatabaseOperations.lookup_cast`). So a case-insensitive comparison is written by the two halves together: the cast on the left, the operator on the right, and on SQLite neither, whose `"LIKE"` is the same string for `"contains"` and `"icontains"`.

```text recording=sql
connection.operators['exact'], connection.operators['icontains'], connection.ops.lookup_cast('icontains', 'CharField'), connection.ops.lookup_cast('exact', 'CharField')  ->  ('= %s', "LIKE %s ESCAPE '\\'", '%s', '%s')
```

### Preparing through the field: the two mixins

`get_db_prep_lookup` on `Lookup` passes a value through untouched. `FieldGetDbPrepValueMixin` replaces it with a call of the field's `get_db_prep_value`, the second step of a field's preparation, which adapts a value to the backend, with `prepared=True` since `get_prep_value` has run already (`django/db/models/lookups.py:FieldGetDbPrepValueMixin.get_db_prep_lookup`, `django/db/models/fields/__init__.py:Field.get_db_prep_value`). The field asked is the output field's `target_field` where it has one, which the comment says is for a relation field; a value that is an expression is left for the compiler. `Exact` and the ordered comparisons carry the mixin; `IExact`, the pattern lookups, `IsNull` and `Regex` do not.

`FieldGetDbPrepValueIterableMixin` is the same for a lookup whose right side is several values, `In` and `Range`, and it draws one line: a list of plain values is prepared in Python, each through the field's `get_prep_value` and then its `get_db_prep_value`, and becomes placeholders, while a list with an expression in it is handed to the database as expressions, each plain value wrapped in a `Value` of the left side's type and compiled beside them, so that `tonnage__in=[F('id'), 480]` writes a column and a placeholder (`django/db/models/lookups.py:FieldGetDbPrepValueIterableMixin.get_prep_lookup`, `django/db/models/lookups.py:FieldGetDbPrepValueIterableMixin.batch_process_rhs`). Such a list is kept as an `ExpressionList` from `get_prep_lookup` to `process_rhs`, which unwraps it and sends the expressions through `batch_process_rhs`, where `resolve_expression_parameter` compiles each; an iterator is read into a list first, with the comment that the test for an expression must not consume it. The `F` in that list was resolved to a column before the lookup was built, by `Query.resolve_lookup_value` ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)).

> **Changed in 6.1.1.** The release notes record a regression of 6.1 in which an `in` lookup on an annotation returned nothing and a `range` lookup crashed when given an iterator (`docs/releases/6.1.1.txt`).

## The standard lookups, registered on every field

Every field answers to the names in the table below, which `django/db/models/lookups.py` registers on `Field` as it is imported, unless its class registers another class under the same name, as `IntegerField` does, or cuts the inheritance off, as a relation field does (`django/db/models/fields/__init__.py:Field`, `django/db/models/fields/__init__.py:IntegerField`) ([The lookup registry: `RegisterLookupMixin`](../querysets/lookups.md), [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](related-lookups.md)). Each is a `BuiltinLookup`, and what each adds to the plain case follows.

| name | class | SQLite writes | refuses, or decides without the database |
|---|---|---|---|
| `"exact"` | `Exact` | `"= %s"` | refuses a queryset not sliced to one row, or selecting other than the left side's number of columns |
| `"iexact"` | `IExact` | `"LIKE %s ESCAPE '\'"` | |
| `"gt"` | `GreaterThan` | `"> %s"` | |
| `"gte"` | `GreaterThanOrEqual` | `">= %s"` | |
| `"lt"` | `LessThan` | `"< %s"` | |
| `"lte"` | `LessThanOrEqual` | `"<= %s"` | |
| `"in"` | `In` | `"IN (%s, %s)"` | refuses a queryset selecting other than the left side's number of columns, or of another database; drops `None` and duplicates, and decides that nothing is matched where nothing is left |
| `"contains"` | `Contains` | `"LIKE %s ESCAPE '\'"` with `%` either side of the value | |
| `"icontains"` | `IContains` | the same | |
| `"startswith"` | `StartsWith` | the same, with `%` after the value | |
| `"istartswith"` | `IStartsWith` | the same | |
| `"endswith"` | `EndsWith` | the same, with `%` before the value | |
| `"iendswith"` | `IEndsWith` | the same | |
| `"range"` | `Range` | `"BETWEEN %s AND %s"` | |
| `"isnull"` | `IsNull` | `"IS NULL"` or `"IS NOT NULL"` | refuses a value that is not `True` or `False`; decides a `Value` on the left without SQL |
| `"regex"` | `Regex` | `"REGEXP %s"` | |
| `"iregex"` | `IRegex` | `"REGEXP '(?i)' || %s"` | |

*The lookups registered on `Field`, the operator each takes from SQLite's table, and what each refuses or settles itself. A refusal is a `ValueError`; a decision is `EmptyResultSet` or `FullResultSet`, which the where tree counts.*

```text recording=sql
list(Sailor.objects.filter(name__exact='Ada'))
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s with params ('Ada',)
list(Sailor.objects.filter(name__iexact='ada'))
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE %s ESCAPE '\' with params ('ada',)
...
list(Sailor.objects.filter(name__contains='100%_a'))
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE %s ESCAPE '\' with params ('%100\\%\\_a%',)
...
list(Ship.objects.filter(tonnage__range=(400, 600)))
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" BETWEEN %s AND %s ORDER BY "fleet_ship"."name" ASC with params (400, 600)
list(Ship.objects.filter(tonnage__in=[480, 1200]))
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."tonnage" IN (%s, %s) ORDER BY "fleet_ship"."name" ASC with params (480, 1200)
...
list(Ship.objects.filter(captain__isnull=True))
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."captain_id" IS NULL ORDER BY "fleet_ship"."name" ASC
list(Ship.objects.filter(captain__isnull=False))
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."captain_id" IS NOT NULL ORDER BY "fleet_ship"."name" ASC
list(Sailor.objects.filter(name__regex='^A'))
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" REGEXP %s with params ('^A',)
list(Sailor.objects.filter(name__iregex='^a'))
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" REGEXP '(?i)' || %s with params ('^a',)
```

### `Exact`

`Exact` has two cases of its own (`django/db/models/lookups.py:Exact.get_prep_lookup`). A `Query` on the right, which is what a queryset given as a value has become by the time the lookup is built, must be limited to one row by `Query.has_limit_one`, and must select as many columns as the left side has, one for a `Col` and the number of its columns for a `ColPairs`, counted by `Query._subquery_fields_len`; where it selects nothing in particular its select list is cleared and the primary key added ([The query: what a `Query` holds, and how it is copied](query.md), [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). The ordering is left as it is, where `In` clears it.

```text recording=sql
Exact with a queryset: limited to one row and one column, or refused
    Ship.objects.filter(pk=Ship.objects.filter(name='Petrel'))  ->  raises ValueError: The QuerySet value for an exact lookup must be limited to one result using slicing.
    Ship.objects.filter(pk=Ship.objects.values('id', 'name')[:1])  ->  raises ValueError: The QuerySet value for the exact lookup must have 1 selected fields (received 2)
    tail(Ship.objects.filter(pk=Ship.objects.filter(name='Petrel')[:1]))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."id" = (SELECT "U0"."id" FROM "fleet_ship" "U0" WHERE "U0"."name" = %s ORDER BY "U0"."name" ASC LIMIT 1) ORDER BY "fleet_ship"."name" ASC', ('Petrel',))
    tail(Ship.objects.filter(name=Ship.objects.filter(name='Petrel').values('name')[:1]))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."name" = (SELECT "U0"."name" AS "name" FROM "fleet_ship" "U0" WHERE "U0"."name" = %s ORDER BY 1 ASC LIMIT 1) ORDER BY "fleet_ship"."name" ASC', ('Petrel',))
    tail(Ship.objects.filter(tonnage__gt=Ship.objects.filter(name='Petrel').values('tonnage')[:1]))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > (SELECT "U0"."tonnage" AS "tonnage" FROM "fleet_ship" "U0" WHERE "U0"."name" = %s ORDER BY "U0"."name" ASC LIMIT 1) ORDER BY "fleet_ship"."name" ASC', ('Petrel',))
    tail(Ship.objects.filter(tonnage__gt=Ship.objects.filter(name='Petrel').values('tonnage')))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > (SELECT "U0"."tonnage" AS "tonnage" FROM "fleet_ship" "U0" WHERE "U0"."name" = %s ORDER BY "U0"."name" ASC) ORDER BY "fleet_ship"."name" ASC', ('Petrel',))
```

The last line is `GreaterThan`, which makes neither check: the subquery is written as it is, unsliced, and whether the database accepts a comparison with several rows is the database's affair.

The other case is a boolean on the right of a conditional left side, a column of a `BooleanField` or an annotation that is a condition (`django/db/models/lookups.py:Exact.as_sql`). Where the backend accepts the left side standing alone in a `"WHERE"`, `Exact.as_sql` writes it alone for `True` and under `"NOT"` for `False`, with the left side's parameters and none for the boolean. The backend answers through `BaseDatabaseOperations.conditional_expression_supported_in_where_clause`: yes to anything where it has a native boolean type, which PostgreSQL has, and otherwise yes to an `Exists`, a lookup, a where tree, a conditional `RawSQL` or a conditional `ExpressionWrapper` of one of these, and no to a plain column (`django/db/backends/base/operations.py:BaseDatabaseOperations.conditional_expression_supported_in_where_clause`).

```text recording=sql
Exact with a boolean: a conditional column stands alone in the WHERE, or under NOT
    tail(Manifest.objects.filter(stamped=True)), tail(Manifest.objects.filter(stamped=False))  ->  (('FROM "office_manifest" WHERE "office_manifest"."stamped" = %s', (True,)), ('FROM "office_manifest" WHERE "office_manifest"."stamped" = %s', (False,)))
    tail(Manifest.objects.filter(stamped=1))  ->  ('FROM "office_manifest" WHERE "office_manifest"."stamped" = %s', (True,))
    sql_of(Ship.objects.annotate(big=Q(tonnage__gt=1000)).filter(big=True))  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "fleet_ship"."tonnage" > %s AS "big" FROM "fleet_ship" WHERE ("fleet_ship"."tonnage" > %s) ORDER BY "fleet_ship"."name" ASC', (1000, 1000))
    sql_of(Ship.objects.annotate(big=Q(tonnage__gt=1000)).filter(big=False))  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "fleet_ship"."tonnage" > %s AS "big" FROM "fleet_ship" WHERE NOT ("fleet_ship"."tonnage" > %s) ORDER BY "fleet_ship"."name" ASC', (1000, 1000))
    connection.ops.conditional_expression_supported_in_where_clause(Manifest._meta.get_field('stamped').get_col('office_manifest'))  ->  False
```

On SQLite the stamped column is compared with a parameter, which the field prepared from `1` into `True`, while the annotation, a where tree, stands alone under its parentheses, and is selected as a column as well, which is the first parameter of each of those two statements.

### `IExact` and the pattern lookups

`IExact` sets `prepare_rhs` off and passes its one parameter through `BaseDatabaseOperations.prep_for_iexact_query`, which on the base class is `prep_for_like_query`, escaping `\`, `%` and `_` for a `"LIKE"`; PostgreSQL and Oracle, whose operator for it is `"= UPPER(%s)"`, return the value untouched (`django/db/models/lookups.py:IExact.process_rhs`, `django/db/backends/base/operations.py:BaseDatabaseOperations.prep_for_iexact_query`).

`PatternLookup` is the base of the pattern lookups, with `prepare_rhs` off and a `param_pattern` that says where the `%` go: either side of the value on `Contains`, after it on `StartsWith`, before it on `EndsWith`; `IContains`, `IStartsWith` and `IEndsWith` are subclasses with another name and nothing else, their difference being the backend's operator and cast (`django/db/models/lookups.py:PatternLookup`). The right side takes one of two roads, chosen by `PatternLookup.is_simple_lookup`: a direct value with no bilateral transform is simple. A simple value is escaped in Python by `prep_for_like_query` and, where `BaseDatabaseFeatures.pattern_lookup_needs_param_pattern` says the backend matches with `"LIKE"`, wrapped in the `%` of the pattern, and the operator comes from `operators` as usual (`django/db/models/lookups.py:PatternLookup.process_rhs`, `django/db/backends/base/features.py:BaseDatabaseFeatures.pattern_lookup_needs_param_pattern`). Anything else, a column, a transform or a transformed value, is escaped and wrapped by the database: `PatternLookup.get_rhs_op` takes the pattern from `pattern_ops`, a second table on the `DatabaseWrapper` whose entries hold the operator and the `%` as SQL, and fills its hole with `pattern_esc`, the SQL that escapes the three characters with `"REPLACE"` (`django/db/models/lookups.py:PatternLookup.get_rhs_op`, `django/db/backends/sqlite3/base.py:DatabaseWrapper.pattern_ops`).

```text recording=sql
PatternLookup: a plain value is escaped and wrapped in Python, an expression is wrapped by SQL from pattern_ops
    tail(Sailor.objects.filter(name__startswith='A%')), tail(Sailor.objects.filter(name__startswith='A_'))  ->  (('FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE %s ESCAPE \'\\\'', ('A\\%%',)), ('FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE %s ESCAPE \'\\\'', ('A\\_%',)))
    tail(Sailor.objects.filter(name__startswith=F('name')))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE REPLACE(REPLACE(REPLACE(("crew_sailor"."name"), \'\\\', \'\\\\\'), \'%%\', \'\\%%\'), \'_\', \'\\_\') || \'%%\' ESCAPE \'\\\'', ())
    tail(Sailor.objects.filter(name__icontains=Lower('name')))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE \'%%\' || UPPER(REPLACE(REPLACE(REPLACE((LOWER("crew_sailor"."name")), \'\\\', \'\\\\\'), \'%%\', \'\\%%\'), \'_\', \'\\_\')) || \'%%\' ESCAPE \'\\\'', ())
    tail(Sailor.objects.filter(name__iexact=F('name')))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."name" LIKE ("crew_sailor"."name") ESCAPE \'\\\'', ())
    connection.ops.prep_for_like_query('100%_a'), connection.pattern_esc, connection.pattern_ops['startswith'], connection.features.pattern_lookup_needs_param_pattern  ->  ('100\\%\\_a', "REPLACE(REPLACE(REPLACE({}, '\\', '\\\\'), '%%', '\\%%'), '_', '\\_')", "LIKE {} || '%%' ESCAPE '\\'", True)
```

The first line is the escaping of a value: a `%` and an `_` in it are to be matched as themselves. The next two are the road for an expression, with `"UPPER"` written round the escaped column for `"icontains"`, as SQLite's `pattern_ops` has it. The last line is the pieces: the escaped value, the two tables' entries and the feature.

### `In`

`In` carries the iterable mixin and does three things of its own. A `Query` on the right is checked for the number of columns, as `Exact` checks it, then has its ordering cleared, default ordering included, and its primary key selected where nothing is (`django/db/models/lookups.py:In.get_prep_lookup`). The ordering is what distinguishes the two subqueries recorded under `Exact`: `Exact` kept the `"ORDER BY"` and `In` will not. `In.process_rhs` refuses with `ValueError` a query whose `_db` is another database than the connection's, the attribute `QuerySet.resolve_expression` sets on the query it hands over, with the message that the inner query is to be evaluated with `list` first (`django/db/models/lookups.py:In.process_rhs`, `django/db/models/query.py:QuerySet.resolve_expression`). For direct values it drops `None`, since the comment says `"NULL"` is never equal to anything, and duplicates, through an `OrderedSet` that keeps the order of first appearance, falling back to a list where a value cannot be hashed; and where nothing is left it raises `EmptyResultSet` (`django/utils/datastructures.py:OrderedSet`). What is left goes through `batch_process_rhs`, and the placeholders are joined inside parentheses. `In.as_sql` has one more case: where `BaseDatabaseOperations.max_in_list_size` gives a limit, Oracle's being 1000, and the values exceed it, `In.split_parameter_list_as_sql` writes `(col IN (...) OR col IN (...))` in groups of that size (`django/db/models/lookups.py:In.split_parameter_list_as_sql`, `django/db/backends/oracle/operations.py:DatabaseOperations.max_in_list_size`).

```text recording=sql
In: duplicates and None are dropped, an empty list matches nothing, and a queryset becomes a subquery with its ordering cleared
    tail(Ship.objects.filter(tonnage__in=[480, 480, 1200]))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" IN (%s, %s) ORDER BY "fleet_ship"."name" ASC', (480, 1200))
    tail(Ship.objects.filter(tonnage__in=[480, None]))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" IN (%s) ORDER BY "fleet_ship"."name" ASC', (480,))
    sql_of(Ship.objects.filter(tonnage__in=[None]))  ->  raises EmptyResultSet: 
    tail(Ship.objects.filter(tonnage__in=iter([480])))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" IN (%s) ORDER BY "fleet_ship"."name" ASC', (480,))
    tail(Ship.objects.filter(tonnage__in=[F('id'), 480]))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" IN ("fleet_ship"."id", %s) ORDER BY "fleet_ship"."name" ASC', (480,))
    tail(Ship.objects.filter(tonnage__in=Ship.objects.values('tonnage').order_by('name')))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" IN (SELECT "U0"."tonnage" AS "tonnage" FROM "fleet_ship" "U0") ORDER BY "fleet_ship"."name" ASC', ())
    Ship.objects.filter(tonnage__in=Ship.objects.values('tonnage', 'name'))  ->  raises ValueError: The QuerySet value for the 'in' lookup must have 1 selected fields (received 2)
    connection.ops.max_in_list_size()  ->  None
```

### `Range`, `IsNull`, `Regex` and `IRegex`

`Range` is the iterable mixin and one operator: its `get_rhs_op` writes `BETWEEN %s AND %s` from the first two placeholders (`django/db/models/lookups.py:Range.get_rhs_op`).

`IsNull` writes no placeholder at all: `IS NULL` for `True` and `IS NOT NULL` for `False`, and anything else on the right is refused with `ValueError` when the SQL is written, not when the filter is built (`django/db/models/lookups.py:IsNull.as_sql`). A `Value` on the left is decided before any SQL: a `None`, or an empty string where `BaseDatabaseFeatures.interprets_empty_strings_as_nulls` says the backend stores one as null, which Oracle's does, is null, and the lookup raises `FullResultSet` or `EmptyResultSet` according to the side asked for (`django/db/backends/base/features.py:BaseDatabaseFeatures.interprets_empty_strings_as_nulls`).

```text recording=sql
IsNull: on a Value the answer is known before any SQL is written
    tail(Ship.objects.annotate(v=Value(None, output_field=models.CharField())).filter(v__isnull=True))  ->  ('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
    sql_of(Ship.objects.annotate(v=Value(None, output_field=models.CharField())).filter(v__isnull=False))  ->  raises EmptyResultSet: 
    sql_of(Ship.objects.annotate(v=Value('x')).filter(v__isnull=True))  ->  raises EmptyResultSet: 
    tail(Ship.objects.filter(tonnage__isnull='yes'))  ->  raises ValueError: The QuerySet value for an isnull lookup must be True or False.
    tail(Ship.objects.filter(tonnage__isnull=1))  ->  raises ValueError: The QuerySet value for an isnull lookup must be True or False.
```

The annotation of a null constant filtered with `isnull=True` has no `"WHERE"`, and filtered with `isnull=False` sends nothing; the last two lines' error is raised by `IsNull.as_sql` as the helper tail asks the compiler for the statement, the filter itself having been built without complaint.

`Regex` goes by the table where the backend has an entry for its name, as SQLite and PostgreSQL have, and otherwise by `BaseDatabaseOperations.regex_lookup`, a template with a hole for each side, which MySQL and Oracle fill with `"REGEXP_LIKE"` and a flag for the case, and MariaDB with `"REGEXP"` (`django/db/models/lookups.py:Regex.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.regex_lookup`). `IRegex` is the same class under another name. SQLite's `"REGEXP"` is a function Django registers on each connection, backed by Python's `re` (`django/db/backends/sqlite3/_functions.py:_sqlite_regexp`), and its table writes `"iregex"` by prepending `(?i)` to the pattern:

```text recording=sql
Sailor.objects.filter(name__regex='^A').query.where.children[0].as_sql(compiler, connection), 'regex' in connection.operators, connection.operators['regex']  ->  (('"crew_sailor"."name" REGEXP %s', ('^A',)), True, 'REGEXP %s')
```

## The integer lookups: `IntegerFieldOverflow` and `IntegerFieldFloatRounding`

`IntegerField` registers, over the standard ones, `IntegerFieldExact`, `IntegerGreaterThan`, `IntegerGreaterThanOrEqual`, `IntegerLessThan` and `IntegerLessThanOrEqual`, under `"exact"`, `"gt"`, `"gte"`, `"lt"` and `"lte"`, and an integer column, or a column of a class built on `IntegerField`, finds these first (`django/db/models/fields/__init__.py:IntegerField`, `django/db/models/lookups.py:IntegerFieldExact`). Each is the base lookup with one or two mixins in front of it. `IntegerFieldOverflow.process_rhs` asks `BaseDatabaseOperations.integer_field_range` for the range of the column's type and, where the value is an `int` outside it, raises an exception instead of sending anything (`django/db/models/lookups.py:IntegerFieldOverflow.process_rhs`, `django/db/backends/base/operations.py:BaseDatabaseOperations.integer_field_range`). Which exception is the class's: `EmptyResultSet` on both sides for `IntegerFieldExact`, and for the comparisons the side that would match every row raises `FullResultSet`, a `"gt"` or `"gte"` below the range and a `"lt"` or `"lte"` above it, while the other side raises `EmptyResultSet`. `IntegerFieldFloatRounding.get_prep_lookup` rounds a `float` up with `math.ceil` before the field makes an integer of it, and only `IntegerGreaterThanOrEqual` and `IntegerLessThan` carry it, the docstring saying that without it the decimal part would always be discarded: an `int` of 1.5 is 1, so `gt=1.5` and `lte=1.5` are right with the integer part alone, while `gte=1.5` and `lt=1.5` need 2 (`django/db/models/lookups.py:IntegerFieldFloatRounding.get_prep_lookup`).

```text recording=sql
The lookups IntegerField registers over Field's: a value past the column's range is decided without the database, and a float is rounded
    sql_of(Ship.objects.filter(tonnage__gt=2 ** 70))  ->  raises EmptyResultSet: 
    tail(Ship.objects.filter(tonnage__lt=2 ** 70))  ->  ('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
    sql_of(Ship.objects.filter(tonnage=2 ** 70))  ->  raises EmptyResultSet: 
    tail(Ship.objects.filter(tonnage__gte=-2 ** 70))  ->  ('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
    sql_of(Ship.objects.filter(tonnage__lte=-2 ** 70))  ->  raises EmptyResultSet: 
    connection.ops.integer_field_range('PositiveIntegerField'), connection.ops.integer_field_range('BigIntegerField')  ->  ((0, 9223372036854775807), (-9223372036854775808, 9223372036854775807))
    tail(Ship.objects.filter(tonnage__lt=1.5)), tail(Ship.objects.filter(tonnage__gte=1.5)), tail(Ship.objects.filter(tonnage__gt=1.5))  ->  (('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" < %s ORDER BY "fleet_ship"."name" ASC', (2,)), ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" >= %s ORDER BY "fleet_ship"."name" ASC', (2,)), ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" > %s ORDER BY "fleet_ship"."name" ASC', (1,)))
    Ship.objects.filter(tonnage='x')  ->  raises ValueError: Field 'tonnage' expected a number but got 'x'.
    tail(Ship.objects.filter(tonnage='480'))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."tonnage" = %s ORDER BY "fleet_ship"."name" ASC', (480,))
```

The range is the backend's: SQLite's `integer_field_range` gives every integer type 64 bits, and the positive types a floor of zero, while the base table gives each type the range of its own column type (`django/db/backends/sqlite3/operations.py:DatabaseOperations.integer_field_range`). The last two lines are `get_prep_value` at work before anything else: a string that is no number is refused as the lookup is made, and one that is becomes the integer.

## `YearLookup` and the year lookups

A date's `"year"` is a transform, `ExtractYear`, and what follows it would ordinarily be the integer lookups of its output field. Instead `ExtractYear` and `ExtractIsoYear` each register, under the same names, classes of their own: `YearExact`, `YearGt`, `YearGte`, `YearLt` and `YearLte` (`django/db/models/functions/datetime.py`). Each is `YearLookup` in front of the plain lookup of that name, and `YearLookup.as_sql` does one thing: where the right side is a direct value, it compares the column under the extract, the transform's own left side, and not the extract, the comment saying this is to let an index on the column be used (`django/db/models/lookups.py:YearLookup.as_sql`). The year becomes its first and last moments through `YearLookup.year_lookup_bounds`, which asks `BaseDatabaseOperations.year_lookup_bounds_for_datetime_field` where the column is a `DateTimeField` and `year_lookup_bounds_for_date_field` otherwise, with an ISO week-numbering year where the transform was `ExtractIsoYear`; the datetime bounds are made aware in the current time zone where `USE_TZ` is on (`django/db/models/lookups.py:YearLookup.year_lookup_bounds`, `django/db/backends/base/operations.py:BaseDatabaseOperations.year_lookup_bounds_for_datetime_field`). Then `get_direct_rhs_sql` gives the operator, `"BETWEEN %s AND %s"` on `YearExact` and the table's on the others, and `get_bound_params` chooses the bounds the operator needs: both for `YearExact`, the first for `YearGte` and `YearLt`, the last for `YearGt` and `YearLte`. The placeholder from `process_rhs` is used and its parameter thrown away, the bounds standing in its place.

```text recording=sql
YearLookup: a plain year is compared as bounds on the column itself, so that an index on the column can serve
    tail(Voyage.objects.filter(sailed__year=2026)), tail(Voyage.objects.filter(sailed__year__lt=2026)), tail(Voyage.objects.filter(sailed__year__gt=2026))  ->  (('FROM "fleet_voyage" WHERE "fleet_voyage"."sailed" BETWEEN %s AND %s', ('2026-01-01', '2026-12-31')), ('FROM "fleet_voyage" WHERE "fleet_voyage"."sailed" < %s', ('2026-01-01',)), ('FROM "fleet_voyage" WHERE "fleet_voyage"."sailed" > %s', ('2026-12-31',)))
    tail(Voyage.objects.filter(sailed__year__gte=2026)), tail(Voyage.objects.filter(sailed__year__lte=2026))  ->  (('FROM "fleet_voyage" WHERE "fleet_voyage"."sailed" >= %s', ('2026-01-01',)), ('FROM "fleet_voyage" WHERE "fleet_voyage"."sailed" <= %s', ('2026-12-31',)))
    tail(Sailor.objects.filter(signed_on__year=2011))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."signed_on" BETWEEN %s AND %s', ('2011-01-01 00:00:00', '2011-12-31 23:59:59.999999'))
    tail(Voyage.objects.filter(sailed__iso_year=2026))  ->  ('FROM "fleet_voyage" WHERE "fleet_voyage"."sailed" BETWEEN %s AND %s', ('2025-12-29', '2027-01-03'))
    tail(Voyage.objects.filter(sailed__year=F('id')))  ->  ('FROM "fleet_voyage" WHERE django_date_extract(%s, "fleet_voyage"."sailed") = ("fleet_voyage"."id")', ('year',))
    tail(Voyage.objects.filter(sailed__year__in=[2025, 2026]))  ->  ('FROM "fleet_voyage" WHERE django_date_extract(%s, "fleet_voyage"."sailed") IN (%s, %s)', ('year', 2025, 2026))
    connection.ops.year_lookup_bounds_for_date_field(2026), connection.ops.year_lookup_bounds_for_datetime_field(2026)  ->  (['2026-01-01', '2026-12-31'], ['2026-01-01 00:00:00', '2026-12-31 23:59:59.999999'])
```

A year of a `DateField` is bounded by two dates, of a `DateTimeField` by two moments to the microsecond, and an ISO year by the Monday its first week begins on and the Sunday its last ends on. Where the right side is an expression, `YearLookup.as_sql` steps aside and the plain lookup writes the extract on the left; and `"sailed__year__in"` is not one of them, so it is the `In` of the extract's integer output field, with the extract written too.

## `UUIDTextMixin`: the text lookups of a UUID field

A `UUIDField` on a backend with no UUID type of its own stores the hex digits with the hyphens removed, which is what `UUIDField.get_db_prep_value` returns where `BaseDatabaseFeatures.has_native_uuid_field` is false: PostgreSQL's sets it outright, and MySQL's is a property that is true on MariaDB (`django/db/models/fields/__init__.py:UUIDField.get_db_prep_value`, `django/db/backends/base/features.py:BaseDatabaseFeatures.has_native_uuid_field`). The comparisons that prepare their value through the field, `Exact` among them, meet the column as it is stored. Those that do not, `IExact` and the pattern lookups, would compare a hyphenated string with unhyphenated text, so `UUIDField` registers a subclass of each with `UUIDTextMixin` in front: its `process_rhs`, where the backend has no native type, wraps a direct value in a `Value` and the right side in a `Replace` that removes the hyphens in SQL, with a `CharField` as its output field, and then goes on as the lookup would (`django/db/models/lookups.py:UUIDTextMixin.process_rhs`, `django/db/models/functions/text.py:Replace`). The classes are `UUIDIExact`, `UUIDContains`, `UUIDIContains`, `UUIDStartsWith`, `UUIDIStartsWith`, `UUIDEndsWith` and `UUIDIEndsWith`.

## `PostgresOperatorLookup`

`PostgresOperatorLookup` is a base for a lookup that PostgreSQL writes with an operator of its own: a subclass names the operator in `postgres_operator`, and `PostgresOperatorLookup.as_postgresql` writes the two halves with it between, leaving `as_sql` to the subclass for every other backend (`django/db/models/lookups.py:PostgresOperatorLookup.as_postgresql`). The containment and key lookups of `JSONField`, and the containment, overlap, key and trigram lookups of `django.contrib.postgres` and those of its range fields, are built on it (`django/db/models/fields/json.py:JSONField`, [Content types, static files and the other contrib apps](../contrib.md)).
