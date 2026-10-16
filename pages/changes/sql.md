---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in expressions, lookups and the compiler

What changed from Django 5.0 to this commit in the layer that writes a queryset's SQL: parameters as a tuple, aliases quoted, the aggregates that came into `django.db.models`, `None` and `JSONNull` on a JSON field, and smaller changes to expressions, lookups and the compiler, with the code that now does each.

Each part of a statement, an expression, a lookup, a join, compiles to a pair, SQL with placeholders and the parameters that fill them, and the compiler joins the pairs ([From QuerySet to SQL](../sql.md)). The deprecations below are listed with the others in [What still warns: the deprecations and the releases that end them](deprecations.md).

## Parameters as a tuple

Until 6.0 `BaseExpression.as_sql`, and `Lookup.process_lhs` and `Lookup.process_rhs`, could return their parameters as a list or a tuple. Since 6.0 the second element is to be a tuple. The release notes give as the reason the interoperability problems of the mixture (`docs/releases/6.0.txt`). At this commit `Func.as_sql` gathers its arguments' parameters in a list and returns a tuple of them, and `BuiltinLookup.as_sql` unpacks both halves into one tuple, so that a half of either kind still joins (`django/db/models/expressions.py:Func.as_sql`, `django/db/models/lookups.py:BuiltinLookup.as_sql`). Nothing checks the type of what an `as_sql` returns.

## Aliases quoted, and the percent sign

The release notes of 6.1 say that the aliases of annotations in the select list, and those of tables and joins, are now quoted systematically, so that a special character in one cannot collide with the SQL around it; and that since a quoted alias is case-sensitive, raw SQL, a `RawSQL`'s, that names an alias of mixed case may have to quote it too (`docs/releases/6.1.txt`). At this commit `SQLCompiler.as_sql` writes each alias of the select list through `BaseDatabaseOperations.quote_name`, and `BaseTable.as_sql` and `Join.as_sql` write a table's alias through `SQLCompiler.quote_name` (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/models/sql/datastructures.py:Join.as_sql`). `SQLCompiler.quote_name_unless_alias` is deprecated since 6.1 in favour of it: it warns with `RemovedInDjango2028Warning` and calls `quote_name` ([The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)). Here the annotation's alias and the joined table's are quoted:

```text
# sql_page.py at this commit, on SQLite
str(Ship.objects.filter(home__ships__name='Gannet').annotate(Tons=F('tonnage')).values('Tons').query)  ->  'SELECT "fleet_ship"."tonnage" AS "Tons" FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") INNER JOIN "fleet_ship" "T3" ON ("fleet_port"."id" = "T3"."home_id") WHERE "T3"."name" = Gannet ORDER BY "fleet_ship"."name" ASC'
```

The aliases a queryset is given are checked by `Query.check_alias` against a pattern of what is forbidden ([The SELECT clause: `get_select`, the select mask and `klass_info`](../sql/select.md)). Since 6.0 a percent sign in an alias warns with `RemovedInDjango2028Warning` and is otherwise accepted (`django/db/models/sql/query.py:Query.check_alias`); a comment above `FORBIDDEN_ALIAS_PATTERN` gives the pattern that will refuse it. The aliases security releases since 5.0 closed to injection are in [Security fixes: SQL injection](security-fixes-sql.md).

## Aggregates: ordering, the new classes and arity

Since 6.0 an `Aggregate` takes an ordering, `Aggregate.order_by`, and refuses it with `TypeError` unless the class sets `Aggregate.allow_order_by` (`django/db/models/aggregates.py:Aggregate.__init__`; [Aggregates: `Aggregate`, `Count` and `get_aggregation`](../sql/aggregates.md)). With it two classes came to `django.db.models`: `StringAgg`, which joins values with a delimiter and was the PostgreSQL application's alone, and `AnyValue`, which takes any one value of the group and is refused with `NotSupportedError` where `BaseDatabaseFeatures.supports_any_value` is off, as on MariaDB (`django/db/models/aggregates.py:StringAgg`, `django/db/models/aggregates.py:AnyValue.as_sql`). In 6.1 `BitAnd`, `BitOr` and `BitXor` followed, refused where `BaseDatabaseFeatures.supports_bit_aggregations` is off, as on Oracle before 21 (`django/db/models/aggregates.py:BitAggregate`); and `StringAgg` took `distinct=True` on SQLite with the delimiter `Value(",")` (`django/db/models/aggregates.py:StringAgg.as_sqlite`). The PostgreSQL application's classes of those names are now subclasses that warn with `RemovedInDjango2028Warning` (`django/contrib/postgres/aggregates/general.py`; [What changed in the other contrib apps](contrib.md)).

Since 5.2 `Avg`, `Max`, `Min` and `Sum` declare `Func.arity` as 1, and `Func.__init__` refuses any other number of expressions with `TypeError` (`django/db/models/expressions.py:Func.__init__`); `Count`, `StdDev` and `Variance` declare it too, but their own `__init__` passes on one expression and takes a second argument as filter or sample (`django/db/models/aggregates.py:StdDev.__init__`):

```text
# sql_page.py at this commit
Sum('tonnage', 'name')  ->  raises TypeError: 'Sum' takes exactly 1 argument (2 given)
```

## The JSON field: strings, `None` and `JSONNull`

A string given to a `JSONField`, or compared with it by `"exact"` or `"in"`, is a JSON string at this commit, encoded like any value by `BaseDatabaseOperations.adapt_json_value`, `json.dumps` unless the backend has its own (`django/db/models/fields/json.py:JSONField.get_db_prep_value`). Until 5.1 a string that decoded as JSON was taken as already encoded, with a warning since 4.2 (`docs/releases/4.2.txt`).

A `None` means two things on a `JSONField`: saved, SQL's `"NULL"`; compared with the whole value in an exact lookup, JSON's null. 6.1 added `JSONNull`, a `Value` of `None` whose output is a `JSONField`, which means JSON's null in both places (`django/db/models/expressions.py:JSONNull`, `django/db/models/fields/json.py:JSONField.get_db_prep_save`). The comparison with a top-level `None` is deprecated: `JSONExact.process_rhs` warns with `RemovedInDjango2028Warning` and compiles it as before, to the parameter `JSONNull` gives (`django/db/models/fields/json.py:JSONExact.process_rhs`). A comment marks the line that sets `JSONExact.can_use_none_as_rhs` for removal when the deprecation ends; without it `Query.build_lookup` turns the comparison into `"isnull"`, `"IS NULL"` ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](../sql/names.md)), while a commented line in `KeyTransformExact` is to set it there, so that a key compared with `None` still means JSON's null. Since 6.1 `iexact=None` on a key is compiled as `exact=None` on it, where before it became `"isnull"` (`django/db/models/fields/json.py:KeyTransformIExact.as_sql`).

```text
# sql_page.py at this commit, on SQLite; plans is Ship.objects.alias(plan=Value({"crates": 12}, JSONField())).values("name")
JSONField().get_db_prep_value('[]', connection)  ->  '"[]"'
plans.filter(plan=None).query.sql_with_params()[1]  ->  ('{"crates": 12}', 'null')
  warns RemovedInDjango2028Warning: Using None as the right-hand side of an exact lookup on JSONField to mean JSON scalar 'null' is deprecated. Use JSONNull() instead (or use the __isnull lookup if you meant SQL NULL).
plans.filter(plan=JSONNull()).query.sql_with_params()[1]  ->  ('{"crates": 12}', 'null')
plans.filter(plan__crates__iexact=None).query.sql_with_params() == plans.filter(plan__crates=None).query.sql_with_params()  ->  True
```

A negative index in a key's path counts from the end of an array, on SQLite since 6.0 and on Oracle 21 and later since 6.1; `BaseDatabaseOperations.compile_json_path` refuses one where `BaseDatabaseFeatures.supports_json_negative_indexing` is off, as on MySQL (`django/db/backends/base/operations.py:BaseDatabaseOperations.compile_json_path`; [The SQL a backend writes: `BaseDatabaseOperations`](../backends/operations.md)).

## The smaller changes

| what | the change | where now |
|---|---|---|
| `Now` on Oracle | `"LOCALTIMESTAMP"`, where it was `"CURRENT_TIMESTAMP"` (5.0) | `django/db/models/functions/datetime.py:Now.as_oracle` |
| `"XOR"` of several operands | on the backends without `"XOR"`, all but MySQL's, true when an odd number of operands are; before, exactly one (5.0) | `django/db/models/sql/where.py:WhereNode.as_sql` |
| An integer outside the column's range | decided without the database: `"exact"`, and a comparison no value in range passes, match nothing; one every value passes is dropped (5.0) | `django/db/models/lookups.py:IntegerFieldOverflow.process_rhs` |
| `Query.annotation_select_mask` | the 5.0 notes made it an ordered list; at this commit it is a set, and the select's order is `Query.selected`'s or `Query.annotations`' (5.0) | `django/db/models/sql/query.py:Query.set_annotation_mask` |
| `nulls_first=False`, `nulls_last=False` | refused with `ValueError` (5.0) | `django/db/models/expressions.py:OrderBy` |
| get_joining_columns, get_reverse_joining_columns | gone; `Join` asks only for `ForeignObject.get_joining_fields` or `ForeignObjectRel.get_joining_fields` (6.0) | `django/db/models/sql/datastructures.py:Join` |
| `RowRange`, `ValueRange` | a row frame may start after the current row, or end before it; both take an exclusion, a `WindowFrameExclusion` (5.1) | `django/db/backends/base/operations.py:BaseDatabaseOperations.window_frame_rows_start_end`, `django/db/models/expressions.py:WindowFrame` |
| Ordering by a transform of an annotation | `QuerySet.order_by` takes an annotation's alias followed by transforms, a key of a `JSONObject` for one (5.1) | `django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs` |
| Slicing an `F` | makes a `Sliced`, written by the output field's `Field.slice_expression`: a substring for a text field, refused where not overridden (5.1) | `django/db/models/expressions.py:Sliced` |
| `BaseExpression.constraint_validation_compatible` | where false, a unique or exclusion constraint's validation uses the expression's one source instead (5.1) | `django/db/models/expressions.py:BaseExpression.get_expression_for_validation` |
| `BaseExpression.set_returning` | a selected annotation that sets it makes an aggregation run over a subquery (5.2) | `django/db/models/sql/query.py:Query.get_aggregation` |
| `BaseExpression.allows_composite_expressions` | unless set, `resolve_expression` refuses a composite key's `ColPairs` among the sources with `ValueError` (5.2) | `django/db/models/expressions.py:BaseExpression.resolve_expression` |
| `JSONArray` | new: a JSON array of its arguments (5.2) | `django/db/models/functions/json.py:JSONArray` |
| A subquery of a composite key | may stand on the right of lookups other than `"in"`, `"exact"` among them (6.0) | [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](../sql/related-lookups.md) |
| `UUID4`, `UUID7` | new functions with a `UUIDField` output; `UUID7` takes an optional shift (6.1) | `django/db/models/functions/uuid.py` |
| `Extract` and `Trunc` without a time zone | deconstructed while `USE_TZ` is on, as in a migration's `Field.db_default`, warn with `RemovedInDjango2029Warning`; Django 2029 will capture the current zone (6.2) | `django/db/models/functions/datetime.py:TimezoneMixin.deconstruct` |

*The smaller changes, by name.*
