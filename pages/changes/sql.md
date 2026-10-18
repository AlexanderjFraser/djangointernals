---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in expressions, lookups and the compiler

Parameters as a tuple, quoted aliases, an aggregate's filter and ordering as slots of its template, the aggregates and `JSONNull` new to `django.db.models`, and `None` on a JSON field.

Three changes reach code outside Django through the SQL and the parameters that each part of a statement compiles to ([From QuerySet to SQL](../sql.md)). Since 6.0 an expression or a lookup is to return its parameters as a tuple. Since 6.1 the compiler quotes the aliases that `SQLCompiler.quote_name_unless_alias` left bare. And since 6.0 an aggregate's filter is a slot of its template, which a template of one's own may lack.

## Parameters as a tuple

Since 6.0 an `as_sql`, `Lookup.process_lhs` or `Lookup.process_rhs` is to return its parameters as a tuple; until then a list would do. The 6.0 notes give the reason, "the interoperability problems that resulted" (`docs/releases/6.0.txt`). `Func.as_sql` and `Col.as_sql` now return tuples. `BuiltinLookup.as_sql` unpacks both halves into one, so a half of either kind still joins (`django/db/models/expressions.py:Func.as_sql`, `django/db/models/lookups.py:BuiltinLookup.as_sql`).

Nothing checks the type, but code that adds a list to what Django hands it fails ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../sql/lookups.md)). The custom lookup below adds `list(self.rhs)` to its left half's parameters. Under 5.2.17 the query runs; from 6.0 the left half is a tuple, and the `+` raises:

```text recording=changes
Entry.objects.filter(title__within=("Dawn", "Dusk")): a custom lookup whose as_sql returns lhs_params + list(self.rhs)
    5.2.17       ['Dawn', 'Dusk']
    6.0.8        TypeError: can only concatenate tuple (not "list") to tuple
    6.1.1        TypeError: can only concatenate tuple (not "list") to tuple
    this commit  TypeError: can only concatenate tuple (not "list") to tuple
```

## Aliases quoted

Since 6.1 the compiler quotes the aliases of tables and joins that `SQLCompiler.quote_name_unless_alias` left bare (`django/db/models/sql/datastructures.py:Join.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.quote_name`). An alias is a name the query makes, as T3 or U0, or one it is given, as `QuerySet.annotate` names a `FilteredRelation` ([Tables and joins: the alias map and join promotion](../sql/joins.md)). The 6.1 notes give the reason, collisions with special characters. They warn that raw SQL naming an alias of mixed case may need quoting, a quoted alias being case-sensitive (`docs/releases/6.1.txt`).

Below, a join is named Calm; `str` shows the parameter, mood calm, in place of its placeholder. Calm stands bare under 6.0.8 and is quoted wherever it stands from 6.1. 5.2.17 wrote 6.0.8's statement, and this commit 6.1.1's; those two lines:

```text recording=changes
str(Entry.objects.annotate(Calm=FilteredRelation("notes", condition=Q(notes__title="mood calm"))).values("Calm__title").query)
...
    6.0.8        SELECT Calm."title" AS "Calm__title" FROM "journal_entry" LEFT OUTER JOIN "journal_note" Calm ON ("journal_entry"."id" = Calm."entry_id" AND (Calm."title" = mood calm))
    6.1.1        SELECT "Calm"."title" AS "Calm__title" FROM "journal_entry" LEFT OUTER JOIN "journal_note" "Calm" ON ("journal_entry"."id" = "Calm"."entry_id" AND ("Calm"."title" = mood calm))
```

`SQLCompiler.quote_name_unless_alias` is deprecated since 6.1. It now quotes whatever it is given: a join's alias, `'T3'` until 6.0.8, comes back `'"T3"'` on SQLite (`django/db/models/sql/compiler.py:SQLCompiler.quote_name_unless_alias`; [The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)).

## Aggregates: the classes that moved, ordering and the filter

Aggregates came into `django.db.models` in two releases. 6.0 brought `StringAgg`, from the PostgreSQL application, and `AnyValue`, which no earlier release had; 6.1, the bit aggregates `BitAnd`, `BitOr` and `BitXor`, from it too (`django/db/models/aggregates.py:StringAgg`, `django/db/models/aggregates.py:BitAggregate`). The PostgreSQL classes are deprecated ([What changed in the other contrib apps](contrib.md)). On SQLite, since 6.1, `StringAgg` takes `distinct=True` with the delimiter `Value(",")` only (`django/db/models/aggregates.py:StringAgg.as_sqlite`).

Since 6.0 `Aggregate.__init__` takes `order_by=`, and refuses it with `TypeError` unless the class sets `Aggregate.allow_order_by` (`django/db/models/aggregates.py:Aggregate.__init__`). Under 5.2.17 `Max("title", order_by="published")` ignored the argument and gave the greatest title.

The ordering and the filter are slots of `Aggregate.template` since 6.0, `"%(order_by)s"` and `"%(filter)s"`, which `Aggregate.as_sql` fills. 5.2's filter_template, which wrapped any template in `" FILTER (WHERE ...)"`, is gone, and the 6.0 notes do not say so (`django/db/models/aggregates.py:Aggregate.as_sql`). An aggregate of one's own whose template lacks the slot loses its filter where `BaseDatabaseFeatures.supports_aggregate_filter_clause` is on, as on SQLite and PostgreSQL. Elsewhere the filter goes into a `Case`, as before.

Total, below, is such an aggregate, its function `"COUNT"`, given on SQLite a filter no entry passes. The right count is 0, as under 5.2.17; from 6.0 the filter, having no parameter, is dropped without a word, and every entry counted:

```text recording=changes
Entry.objects.aggregate(n=Total("id", filter=Q(published__lt=F("published")))): Total an Aggregate whose template is "%(function)s(%(expressions)s)", and a filter no entry passes
    5.2.17       {'n': 0}
    6.0.8        {'n': 3}
    6.1.1        {'n': 3}
    this commit  {'n': 3}
```

A filter with a parameter, as `Q(title="Dawn")`, leaves its parameter without a placeholder, and SQLite refuses the statement with `ProgrammingError` ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](../sql/aggregates.md)).

> **Trap.** The reference documentation still gives `Aggregate.template` as `"%(function)s(%(distinct)s%(expressions)s)"`, and its example aggregate has no slot for the filter (`docs/ref/models/expressions.txt`).

## The JSON field: `None` and `JSONNull`

Since 6.1 the top-level `None`, a `None` compared with a `JSONField`'s whole value, is deprecated for `JSONNull`, which is JSON's null both saved and compared (`django/db/models/expressions.py:JSONNull`). To the field a `None` has two meanings: saved, it is SQL's `"NULL"`; compared with the whole value, JSON's null (`django/db/models/fields/json.py:JSONField.get_db_prep_save`). `JSONExact.process_rhs` warns of a top-level `None` with `RemovedInDjango2028Warning`, and compiles it as before (`django/db/models/fields/json.py:JSONExact.process_rhs`). When the deprecation ends, the 6.1 notes say, a top-level `None` compiles to `"IS NULL"`, and a key's is unaffected (`docs/releases/6.1.txt`; [From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](../sql/names.md)).

Since 6.1 `KeyTransformIExact.as_sql` compiles `iexact=None` on a key as `exact=None`, matching a key that holds JSON's null. Until then it was `isnull=True` on the key, matching the rows without it (`django/db/models/fields/json.py:KeyTransformIExact.as_sql`).

A negative index in a key's path counts from the end of an array. SQLite has it since 6.0, where 5.2.17 wrote a path SQLite refused; Oracle 21 and later since 6.1, by the notes. `BaseDatabaseOperations.compile_json_path`, new in 6.0, refuses one where `BaseDatabaseFeatures.supports_json_negative_indexing` is off, as on MySQL (`django/db/backends/base/operations.py:BaseDatabaseOperations.compile_json_path`; [The SQL a backend writes: `BaseDatabaseOperations`](../backends/operations.md)). 5.2's function of the field's module, compile_json_path, is gone, and no note says so.

## The smaller changes

| what | change | where |
|---|---|---|
| `Now` on Oracle | Since 5.0, `"LOCALTIMESTAMP"`, not `"CURRENT_TIMESTAMP"` | `django/db/models/functions/datetime.py:Now.as_oracle` |
| `^` of conditions | Since 5.0, without a native `"XOR"`, true when an odd number are, not exactly one | `django/db/models/sql/where.py:WhereNode.as_sql` |
| An integer out of range | Since 5.0, an equality, or a bound no value passes, matches nothing, without the database | `django/db/models/lookups.py:IntegerFieldOverflow` |
| `nulls_first=False`, `nulls_last=False` | Gone in 5.0: `OrderBy` refuses either with `ValueError` | `django/db/models/expressions.py:OrderBy.__init__` |
| get_joining_columns | Deprecated in 5.0, gone in 6.0: `Join` asks only `get_joining_fields` | `django/db/models/sql/datastructures.py:Join.__init__` |
| A string given to a `JSONField` | Gone in 5.1: a string taken as JSON already encoded | `django/db/models/fields/json.py:JSONField.get_db_prep_value` |
| `RowRange` | Since 5.1, its bounds may pass the current row | `django/db/backends/base/operations.py:BaseDatabaseOperations.window_frame_rows_start_end` |
| `WindowFrameExclusion` | New in 5.1: the `exclusion=` of `RowRange` and `ValueRange`, the rows a frame leaves out | `django/db/models/expressions.py:WindowFrame` |
| `QuerySet.order_by` | Since 5.1, takes an annotation's name followed by transforms | `django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs` |
| Slicing an `F` | New in 5.1: a `Sliced`, which the output field writes | `django/db/models/expressions.py:Sliced` |
| `BaseExpression.constraint_validation_compatible` | New in 5.1: where false, validation uses the expression's source | `django/db/models/expressions.py:BaseExpression.get_expression_for_validation` |
| `BaseExpression.set_returning` | New in 5.2: where true, an aggregation over it runs on a subquery | `django/db/models/sql/query.py:Query.get_aggregation` |
| `BaseExpression.allows_composite_expressions` | New in 5.2: unless set, a composite key is refused as a source | `django/db/models/expressions.py:BaseExpression.resolve_expression` |
| `Func.arity` | Since 5.2, `Avg`, `Max`, `Min` and `Sum` refuse any number of arguments but one, with `TypeError` | `django/db/models/expressions.py:Func.__init__` |
| `Count` with two arguments | Since 6.0, a field's name as the second is taken as its filter; under 5.2.17, `AttributeError` | `django/db/models/aggregates.py:Count.__init__` |
| A composite key and a subquery | Since 6.0, on SQLite, compared by gt and the like, which 5.2.17 could not write; exact already was | [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](../sql/related-lookups.md) |
| A percent sign in an alias | Deprecated in 6.0: `Query.check_alias` warns of one, and accepts it | `django/db/models/sql/query.py:Query.check_alias` |
| `Extract`, `Trunc` without tzinfo | Deprecated in 6.2: they warn when deconstructed while `USE_TZ` is true | `django/db/models/functions/datetime.py:TimezoneMixin.deconstruct` |
