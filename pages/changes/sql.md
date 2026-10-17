---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in expressions, lookups and the compiler

What changed from Django 5.0 to this commit in the layer that writes a queryset's SQL: parameters as a tuple, table and join aliases quoted, an aggregate's filter and ordering as slots of its template, the aggregates and `JSONNull` that came into `django.db.models`, and `None` on a JSON field.

Each part of a statement compiles to a pair, SQL with placeholders and the parameters that fill them, and the compiler joins the pairs ([From QuerySet to SQL](../sql.md)). Three changes since 5.0 reach code outside Django through that contract: an expression or a lookup returns its parameters as a tuple (6.0); the compiler quotes the aliases `SQLCompiler.quote_name_unless_alias` left bare (6.1); and an aggregate's filter is a slot of its template (6.0), which a template of one's own may lack. Aggregates also came into `django.db.models`, and JSON's null got an expression, `JSONNull`, a top-level `None` in a query deprecated (6.1).

## Parameters as a tuple

Until 6.0 an `as_sql`, `Lookup.process_lhs` or `Lookup.process_rhs` could return its parameters as a list or a tuple: 5.2.17's `Func.as_sql` gave `['Dawn']` for `Lower(Value("Dawn"))`, 6.0.8's `('Dawn',)`. Since 6.0 it is to be a tuple, for "the interoperability problems that resulted", the notes say (`docs/releases/6.0.txt`). At this commit `Func.as_sql` and `Col.as_sql` return tuples, and `BuiltinLookup.as_sql` unpacks both halves into one, so a half of either kind still joins (`django/db/models/expressions.py:Func.as_sql`, `django/db/models/lookups.py:BuiltinLookup.as_sql`). Nothing checks the type; what fails is code adding a list to what Django hands it, as this custom lookup does:

```text recording=changes
Entry.objects.filter(title__within=("Dawn", "Dusk")): a custom lookup whose as_sql returns lhs_params + list(self.rhs)
    5.2.17       ['Dawn', 'Dusk']
    6.0.8        TypeError: can only concatenate tuple (not "list") to tuple
    6.1.1        TypeError: can only concatenate tuple (not "list") to tuple
    this commit  TypeError: can only concatenate tuple (not "list") to tuple
```

From 6.0 the left half is a tuple, and the lookup's `+` raises ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../sql/lookups.md)).

## Aliases quoted, and the percent sign

A statement may name a table by an alias, T3, U0 and the like, or by a name the query is given, as `QuerySet.annotate` names a `FilteredRelation` ([Tables and joins: the alias map and join promotion](../sql/joins.md)). Until 6.1 `SQLCompiler.quote_name_unless_alias` left such an alias bare; since then `Col.as_sql`, `BaseTable.as_sql` and `Join.as_sql` write every name through `SQLCompiler.quote_name` (`django/db/models/sql/datastructures.py:Join.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.quote_name`). The notes give the reason, collisions with special characters, and warn that a quoted alias is case-sensitive, so raw SQL naming one of mixed case may need quoting (`docs/releases/6.1.txt`). Here a join is named Calm (`str` shows a parameter, mood calm, in place of its placeholder), and the change is in the quotation marks around it: from 6.1 Calm is quoted wherever it stands. 5.2.17 wrote 6.0.8's statement, and this commit 6.1.1's; those two lines:

```text recording=changes
str(Entry.objects.annotate(Calm=FilteredRelation("notes", condition=Q(notes__title="mood calm"))).values("Calm__title").query)
...
    6.0.8        SELECT Calm."title" AS "Calm__title" FROM "journal_entry" LEFT OUTER JOIN "journal_note" Calm ON ("journal_entry"."id" = Calm."entry_id" AND (Calm."title" = mood calm))
    6.1.1        SELECT "Calm"."title" AS "Calm__title" FROM "journal_entry" LEFT OUTER JOIN "journal_note" "Calm" ON ("journal_entry"."id" = "Calm"."entry_id" AND ("Calm"."title" = mood calm))
```

The select list's alias, `"Calm__title"`, is quoted under every release: what 6.1 quoted are the aliases of tables and joins (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`).

`SQLCompiler.quote_name_unless_alias` is deprecated since 6.1; it warns with `RemovedInDjango2028Warning` and quotes whatever it is given: a join's alias, `'T3'` until 6.0.8, comes back `'"T3"'` on SQLite (`django/db/models/sql/compiler.py:SQLCompiler.quote_name_unless_alias`; [The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)). A percent sign in an alias is deprecated since 6.0: `Query.check_alias` warns with `RemovedInDjango2028Warning` and accepts it, as 5.2.17 did without a word (`django/db/models/sql/query.py:Query.check_alias`; [The SELECT clause: `get_select`, the select mask and `klass_info`](../sql/select.md)). The alias checks of security releases are in [Security fixes: SQL injection](security-fixes-sql.md).

## Aggregates: the classes that moved, ordering and the filter

Aggregates came into `django.db.models` in two releases: `StringAgg` and the bit aggregates, `BitAnd`, `BitOr` and `BitXor`, from the PostgreSQL application, and `AnyValue`, which no earlier release had (`django/db/models/aggregates.py:StringAgg`, `django/db/models/aggregates.py:BitAggregate`). `StringAgg` and `AnyValue` came in 6.0, the rest in 6.1. `AnyValue` is refused with `NotSupportedError` where `BaseDatabaseFeatures.supports_any_value` is off, as on MariaDB, and the bit aggregates where `BaseDatabaseFeatures.supports_bit_aggregations` is off, as on Oracle before 21 (`django/db/models/aggregates.py:AnyValue.as_sql`). The PostgreSQL classes are deprecated ([What changed in the other contrib apps](contrib.md)). On SQLite 6.1 lets `StringAgg` take `distinct=True` with the delimiter `Value(",")` only (`django/db/models/aggregates.py:StringAgg.as_sqlite`).

Since 6.0 `Aggregate.__init__` takes an order_by argument, refused with `TypeError` unless the class sets `Aggregate.allow_order_by` (`django/db/models/aggregates.py:Aggregate.__init__`). Under 5.2.17 an aggregate of `django.db.models` took it as an extra argument and ignored it: `Max("title", order_by="published")` gave the greatest title.

The ordering and the filter are slots of `Aggregate.template` since 6.0, `"%(order_by)s"` and `"%(filter)s"`, filled by `Aggregate.as_sql`. 5.2's filter_template, which wrapped any template in `" FILTER (WHERE ...)"`, is gone, which the 6.0 notes do not say (`django/db/models/aggregates.py:Aggregate.as_sql`). An aggregate of one's own whose template lacks the slot loses its filter where `BaseDatabaseFeatures.supports_aggregate_filter_clause` is on, as on SQLite and PostgreSQL; elsewhere it goes into a `Case`, as before. Total is such an aggregate, its function `"COUNT"`, given a filter no entry passes, on SQLite:

```text recording=changes
Entry.objects.aggregate(n=Total("id", filter=Q(published__lt=F("published")))): Total an Aggregate whose template is "%(function)s(%(expressions)s)", and a filter no entry passes
    5.2.17       {'n': 0}
    6.0.8        {'n': 3}
    6.1.1        {'n': 3}
    this commit  {'n': 3}
```

From 6.0 a filter with no parameter, as this one, is dropped, and every entry is counted without a word; a filter with a parameter, as `Q(title="Dawn")`, leaves its parameter without a placeholder, and SQLite refuses the statement with `ProgrammingError` ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](../sql/aggregates.md)).

> **Trap.** The reference documentation at this commit still gives `Aggregate.template` as `"%(function)s(%(distinct)s%(expressions)s)"`, and its example aggregate has no slot for the filter (`docs/ref/models/expressions.txt`).

Since 5.2 `Func.__init__` refuses `Avg`, `Max`, `Min` and `Sum` any number of arguments but one with `TypeError`, through `Func.arity` (`django/db/models/expressions.py:Func.__init__`). `Count`, `StdDev` and `Variance`, which the 5.2 notes name too, take a second as the filter or as sample; `Count("title", "published")` fails under 5.2.17 with `AttributeError`, and from 6.0 takes the field published as its filter (`django/db/models/aggregates.py:Count.__init__`).

## The JSON field: `None` and `JSONNull`

To a `JSONField` a `None` saved is SQL's `"NULL"`, and a `None` compared with the whole value is JSON's null (`django/db/models/fields/json.py:JSONField.get_db_prep_save`). 6.1 added `JSONNull`, which is JSON's null in both places, and deprecated the `None` compared with the whole value, the top-level `None`: `JSONExact.process_rhs` warns with `RemovedInDjango2028Warning` and compiles it as before (`django/db/models/expressions.py:JSONNull`, `django/db/models/fields/json.py:JSONExact.process_rhs`). When it ends, the 6.1 notes say (`docs/releases/6.1.txt`), a top-level `None` compiles to `"IS NULL"` and a key's is unaffected ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](../sql/names.md)).

Until 6.1 `iexact=None` on a key was `isnull=True` on it; since 6.1 `KeyTransformIExact.as_sql` compiles it as `exact=None` (`django/db/models/fields/json.py:KeyTransformIExact.as_sql`). The rows asked are notes titled by their documents: "mood null" is `{"mood": null}`, "no mood" `{}`, "JSON null" and "SQL NULL" the two nulls:

```text recording=changes
Note.objects.filter(data__mood__iexact=None): the notes that match
    5.2.17       ['JSON null', 'SQL NULL', 'no mood']
    6.0.8        ['JSON null', 'SQL NULL', 'no mood']
    6.1.1        ['mood null']
    this commit  ['mood null']
```

Until 6.0.8 the notes without the key match; from 6.1, the one whose key holds null.

A negative index in a key's path counts from the end of an array: on SQLite since 6.0, where 5.2.17 wrote a path SQLite refused, and by the notes on Oracle 21 and later since 6.1. `BaseDatabaseOperations.compile_json_path` refuses one where `BaseDatabaseFeatures.supports_json_negative_indexing` is off, as on MySQL (`django/db/backends/base/operations.py:BaseDatabaseOperations.compile_json_path`; [The SQL a backend writes: `BaseDatabaseOperations`](../backends/operations.md)). The method is new in 6.0; 5.2's function of the field's module, compile_json_path, is gone, which no note says.

## The smaller changes

The rest, by name:

| what | the change | release | where now |
|---|---|---|---|
| `Now` on Oracle | `"LOCALTIMESTAMP"`, not `"CURRENT_TIMESTAMP"` | 5.0 | `django/db/models/functions/datetime.py:Now.as_oracle` |
| `^` of conditions | without a native `"XOR"`, true when an odd number are, not exactly one | 5.0 | `django/db/models/sql/where.py:WhereNode.as_sql` |
| An integer out of range | an equality, or a bound no value passes, matches nothing, without the database | 5.0 | `django/db/models/lookups.py:IntegerFieldOverflow` |
| `Query.annotation_select_mask` | an ordered list, the 5.0 notes say; a set under 5.2.17 and at this commit | 5.0 | `django/db/models/sql/query.py:Query.set_annotation_mask` |
| nulls_first=False, nulls_last=False | refused with `ValueError` | 5.0 | `django/db/models/expressions.py:OrderBy.__init__` |
| get_joining_columns | deprecated (5.2.17 warns), then gone; `Join` asks only `get_joining_fields` | 5.0, 6.0 | `django/db/models/sql/datastructures.py:Join.__init__` |
| A string given to a `JSONField` | a JSON string, never taken as already encoded | 5.1 | `django/db/models/fields/json.py:JSONField.get_db_prep_value` |
| `RowRange`, `ValueRange` | a row frame's bounds may pass the current row; both take a `WindowFrameExclusion` | 5.1 | `django/db/backends/base/operations.py:BaseDatabaseOperations.window_frame_rows_start_end`, `django/db/models/expressions.py:WindowFrame` |
| `QuerySet.order_by` | takes an annotation's name followed by transforms | 5.1 | `django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs` |
| Slicing an `F` | a `Sliced`, which the output field writes | 5.1 | `django/db/models/expressions.py:Sliced` |
| `BaseExpression.constraint_validation_compatible` | where false, validation uses the expression's source | 5.1 | `django/db/models/expressions.py:BaseExpression.get_expression_for_validation` |
| `BaseExpression.set_returning` | an aggregation over it runs on a subquery | 5.2 | `django/db/models/sql/query.py:Query.get_aggregation` |
| `BaseExpression.allows_composite_expressions` | unless set, a composite key is refused as a source | 5.2 | `django/db/models/expressions.py:BaseExpression.resolve_expression` |
| `JSONArray`, `UUID4`, `UUID7` | new functions | 5.2, 6.1 | `django/db/models/functions/json.py:JSONArray`, `django/db/models/functions/uuid.py` |
| A composite key against a subquery | on SQLite, comparisons such as gt, which 5.2.17 could not write; exact compiled already | 6.0 | [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](../sql/related-lookups.md) |
| `Extract`, `Trunc` without tzinfo | deconstructed while `USE_TZ` is true, warn with `RemovedInDjango2029Warning` | 6.2 | `django/db/models/functions/datetime.py:TimezoneMixin.deconstruct` |
