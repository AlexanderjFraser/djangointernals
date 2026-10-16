---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# PostgreSQL indexes and `ExclusionConstraint`

`django.contrib.postgres.indexes` gives `Index` subclasses for PostgreSQL's kinds of index, such as `GinIndex` and `BrinIndex`, and `OpClass`, an operator class for an indexed expression. `django.contrib.postgres.constraints` gives `ExclusionConstraint`, the rule that no two rows may stand in a given relation.

PostgreSQL keeps an index by one of several access methods, named after `"USING"`. Django's `Index` names none, and gets a B-tree, which the documentation finds of little help with complex types: GiST may suit a range or an hstore, it says, and GIN an array (`docs/ref/contrib/postgres/fields.txt`). An exclusion constraint forbids two rows for which every one of a list of comparisons, each with its own operator, is true; PostgreSQL implements it with an index (`docs/ref/contrib/postgres/constraints.txt`).

## `PostgresIndex`: a method and its parameters

`PostgresIndex.create_sql` writes what a subclass adds, a method and its storage parameters. It calls `PostgresIndex.check_supported`, an empty hook no class here overrides; hands `Index.create_sql` a `"USING"` clause with the class's suffix, `"btree"` for `BTreeIndex`; and puts what `PostgresIndex.get_with_params` returns in a `"WITH"` clause after any `"INCLUDE"`, before a tablespace or a condition (`django/contrib/postgres/indexes.py:PostgresIndex.create_sql`). A subclass writes only the parameters given.

| class | method | parameters |
|---|---|---|
| `BTreeIndex` | `"btree"` | fillfactor, deduplicate_items |
| `HashIndex` | `"hash"` | fillfactor |
| `GinIndex` | `"gin"` | fastupdate, gin_pending_list_limit |
| `GistIndex` | `"gist"` | buffering, fillfactor |
| `SpGistIndex` | `"spgist"` | fillfactor |
| `BrinIndex` | `"brin"` | autosummarize, pages_per_range |
| `BloomIndex` | `"bloom"` | length; columns, the bits for each field, written col1, col2 and on |

*The index classes of `django.contrib.postgres.indexes`. A true or false parameter is written on or off.*

For the sailings, a schema editor for PostgreSQL, made with no server behind it, wrote:

```text
BTreeIndex(fields=["vessel"], fillfactor=80, deduplicate_items=False, name="sailing_vessel_btree")
CREATE INDEX "sailing_vessel_btree" ON "charts_sailing" USING btree ("vessel") WITH (fillfactor = 80, deduplicate_items = off)

GistIndex(fields=["window"], include=["vessel"], condition=Q(vessel__startswith="Pilot"), fillfactor=90, name="pilot_windows")
CREATE INDEX "pilot_windows" ON "charts_sailing" USING gist ("window") INCLUDE ("vessel") WITH (fillfactor = 90) WHERE "vessel"::text LIKE 'Pilot%'
```

Only `BrinIndex` and `BloomIndex` check their parameters' values. Bloom is an extension, which the documentation says to install with `BloomExtension` (`docs/ref/contrib/postgres/indexes.txt`). Each index class, and `ExclusionConstraint`, has the check that `django.contrib.postgres` is installed ([The PostgreSQL application: `PostgresConfig`, operations and aggregates](postgres.md)).

The suffix also ends the name `Index.set_name_with_model` gives an unnamed index, which may not pass `max_name_length`, thirty on `Index` ([Constraints and indexes](../models/constraints.md)). `PostgresIndex.max_name_length` is thirty less three plus the length of the class's suffix: an unnamed `SpGistIndex` on the sailings' window is named `"charts_sail_window_95d66d_spgist"`, 32 characters (`django/contrib/postgres/indexes.py:PostgresIndex.max_name_length`).

> **Why.** The comment there says the limit of thirty, kept for compatibility across databases, does not apply to indexes only PostgreSQL has.

## `OpClass`: an operator class for an expression

On PostgreSQL an index may name an operator class for each column or expression it indexes. Over fields, an index or a unique constraint names one for each field with `opclasses=` ([Constraints and indexes](../models/constraints.md)). Over expressions, the expression is wrapped in `OpClass`, a `Func` that writes it and then the class's name (`django/contrib/postgres/indexes.py:OpClass`).

`IndexExpression` wraps each expression of an index or a unique constraint and settles where `OpClass` may stand. It lifts its wrapper classes off the top of the expression, puts the rest in parentheses unless it resolves to a column, and nests the wrappers back around it in the order of `IndexExpression.wrapper_classes`, the first outermost (`django/db/models/indexes.py:IndexExpression.resolve_expression`). `PostgresConfig.ready` makes those `OrderBy`, `OpClass` and `Collate` with `IndexExpression.register_wrappers`, so that after an index's column come its collation, its operator class and its direction, in that order (`django/contrib/postgres/apps.py:PostgresConfig.ready`).

```text
Index(OpClass(Collate("vessel", "C"), name="varchar_pattern_ops").desc(nulls_last=True), name="sailing_vessel_c")
CREATE INDEX "sailing_vessel_c" ON "charts_sailing" ("vessel" COLLATE "C" varchar_pattern_ops DESC NULLS LAST)
```

Two of one class raise `ValueError`, and so does a wrapper below the top: "OrderBy, OpClass, Collate must be topmost expressions in an indexed expression." Without the application `OpClass` is no wrapper, and its name goes inside the expression's parentheses.

In `validate`, an exclusion or a unique constraint drops an `OpClass`, whose `OpClass.constraint_validation_compatible` is false, from the top of an expression: `BaseExpression.get_expression_for_validation` returns the expression inside, one level only (`django/db/models/expressions.py:BaseExpression.get_expression_for_validation`).

## `ExclusionConstraint`

The harbour office's bookings of one berth may not overlap, cancelled ones aside:

```python
# charts/models.py
class Berthing(models.Model):
    berth = models.CharField(max_length=10)
    vessel = models.CharField(max_length=60)
    stay = DateTimeRangeField()
    cancelled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            ExclusionConstraint(
                name="one_berthing_at_a_time",
                expressions=[("stay", RangeOperators.OVERLAPS), ("berth", RangeOperators.EQUAL)],
                condition=Q(cancelled=False),
                deferrable=Deferrable.DEFERRED,
                include=["vessel"],
            ),
        ]
```

The expressions are pairs: an expression or a field's name, and an operator's text, which `RangeOperators` spells ([PostgreSQL fields: `ArrayField`, the range fields and hstore](postgres-fields.md)). The index type is `"gist"`, `"spgist"` or `"hash"` in any case, `"GIST"` by default. `ExclusionConstraint.__init__` checks the index type, the expressions' shape and the types of the condition, the deferrable and the include, and refuses a hash index with more than one pair, with an include, or with an operator other than `RangeOperators.EQUAL` (`django/contrib/postgres/constraints.py:ExclusionConstraint.__init__`).

> **Changed in 6.1.** `ExclusionConstraint` takes the hash index type (`docs/releases/6.1.txt`).

`ExclusionConstraint._get_expressions` makes each pair an `ExclusionConstraintExpression`, an `IndexExpression` whose template adds `"WITH"` and the operator, so an expression is wrapped as in an index. `ExclusionConstraint.constraint_sql` compiles them and the condition as an index's are, without table names and with values written in by the editor's `quote_value`, and asks the editor for the `"INCLUDE"` and `"DEFERRABLE"` clauses (`django/contrib/postgres/constraints.py:ExclusionConstraint.constraint_sql`). `ExclusionConstraint.create_sql` puts the clause after `"ALTER TABLE … ADD"`; `ExclusionConstraint.remove_sql` drops it with `BaseDatabaseSchemaEditor.sql_delete_check`. For the berths, with no server:

```text
ALTER TABLE "charts_berthing" ADD CONSTRAINT "one_berthing_at_a_time" EXCLUDE USING GIST ("stay" WITH &&, "berth" WITH =) INCLUDE ("vessel") WHERE (NOT "cancelled") DEFERRABLE INITIALLY DEFERRED
ALTER TABLE "charts_berthing" DROP CONSTRAINT "one_berthing_at_a_time"
```

The documentation asks for the btree_gist extension with GiST (`docs/ref/contrib/postgres/constraints.txt`). `ExclusionConstraint.check` checks the fields the expressions name: one over a berth, on the sailings, reported `"models.E012"`.

## `validate`: the rule asked of the database

`ExclusionConstraint.validate` asks whether a stored row would break the rule with the instance (`django/contrib/postgres/constraints.py:ExclusionConstraint.validate`). For each pair it makes a `PostgresOperatorLookup` with the pair's operator, the expression on the left and on the right the same expression with the instance's values, from `Model._get_field_expression_map`, in place of its fields. It filters the default manager's rows by them, leaves out a saved instance's own row, and raises `ValidationError` with the constraint's message and code if a row is found. A condition goes through `Q.check`, which tests it on the instance's values together with an `Exists` of those rows that meet it (`django/db/models/query_utils.py:Q.check`). For a new booking of berth B4, a stand-in for `SQLCompiler.execute_sql` caught the statement it would have sent:

```text
SELECT %s AS "_check" WHERE (NOT %s AND EXISTS(SELECT %s AS "a" FROM "charts_berthing" "U0" WHERE ("U0"."stay" && %s::tstzrange AND "U0"."berth" = %s AND NOT "U0"."cancelled") LIMIT 1))
params: Int4(1), False, Int4(1), <the stay>, 'B4'
```

The second parameter is the booking's cancelled: a cancelled booking finds nothing, and one that is not meets only rows that are not.

`validate` ignores the index type, the include and the deferrable. When `exclude` names a field that an expression or the condition uses, it returns without asking: with the stay excluded the stand-in caught nothing. And it works only on PostgreSQL, the one database for which `PostgresOperatorLookup` writes SQL (`django/db/models/lookups.py:PostgresOperatorLookup.as_postgresql`): on the harbour's SQLite database it raised `NotImplementedError`, "Subclasses must implement as_sql()".

> **Trap.** `Q.check` catches a `DatabaseError`, logs a warning and answers true: with a stand-in for `SQLCompiler.execute_sql` raising `DatabaseError`, the booking's `validate` raised "Constraint “one_berthing_at_a_time” is violated."
