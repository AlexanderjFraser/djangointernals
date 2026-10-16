---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Security fixes: SQL injection

The SQL injection flaws fixed in the patch releases from 5.0.8 to 6.0.2, and what closes each at this commit: `Query.check_alias` and its `FORBIDDEN_ALIAS_PATTERN`, the refusal of a period in the name of a `FilteredRelation`, the quoting of a join's alias, `Q._check_connector`, and what Oracle's JSON lookups and PostGIS's raster lookups write into a statement.

The ORM sends a value to the database as a parameter, beside the statement, where nothing in it can change what the statement says. A name cannot go that way: the alias of a column, the alias of a table in a join and the word that joins two conditions are part of the statement's text. Some names come from the caller: the keywords of `QuerySet.annotate`, `QuerySet.alias` and `QuerySet.aggregate`, the keys of the select of `QuerySet.extra`, the names given to `QuerySet.values` and `QuerySet.values_list`, the keywords of a `Q`. A program that expands a dictionary built from a request into them lets the request choose them. Each flaw was a path by which such a name, or on Oracle and PostGIS a value, reached the text without a check that refused it.

```text
# guards.py at this commit, on SQLite: a queryset's SQL and its parameters
Ship.objects.annotate(aboard=FilteredRelation("crew", condition=Q(crew__name="Ada")), heavy=F("tonnage")).filter(aboard__isnull=False).values("name", "heavy")
('SELECT "fleet_ship"."name" AS "name", "fleet_ship"."tonnage" AS "heavy" FROM "fleet_ship" INNER JOIN "crew_sailor" "aboard" ON ("fleet_ship"."id" = "aboard"."ship_id" AND ("aboard"."name" = %s)) WHERE "aboard"."id" IS NOT NULL ORDER BY 1 ASC', ('Ada',))
```

The sailor's name is a parameter; `"aboard"` and `"heavy"` are in the text, quoted.

## What an alias may contain: `Query.check_alias`

The aliases a caller gives pass through `Query.check_alias`, called by `Query.add_annotation` for `annotate` and `alias`, `Query.get_aggregation` for `aggregate`, `Query.add_extra` for `extra`, `Query.set_values` for each name given to `values` and `values_list`, and `Query.add_filtered_relation`. It raises `ValueError` where `FORBIDDEN_ALIAS_PATTERN` finds a quotation mark (single, double, a backtick or a square bracket), whitespace, a control character, a semicolon, a hash, or a comment marker, `"--"`, `"/*"` or `"*/"` (`django/db/models/sql/query.py:Query.check_alias`). The compiler writes the alias in quotation marks with the backend's `quote_name`, which on PostgreSQL, SQLite and MySQL wraps a name not already wrapped and escapes nothing inside it (`django/db/backends/postgresql/operations.py:DatabaseOperations.quote_name`). [The SELECT clause: `get_select`, the select mask and `klass_info`](../sql/select.md) places the check in the query; the percent sign, which warns in an alias since 6.0, is in [What changed in expressions, lookups and the compiler](sql.md).

| fix | what was open | releases |
|---|---|---|
| CVE-2024-42005 | The positional names given to `values` and `values_list` were unchecked, and a JSON field's key named there (`"data__key"`) went into an alias. `set_values` now checks each. | 5.0.8 |
| CVE-2025-57833 | The name of a `FilteredRelation` was unchecked. `add_filtered_relation` now checks it. | 5.1.12, 5.2.6 |
| CVE-2025-59681 | The pattern let a hash through; the fix, made for MySQL and MariaDB, added it. | 5.1.13, 5.2.7 |
| CVE-2026-1287 | The pattern let most control characters through. It now refuses U+0000 to U+001F and U+007F to U+009F. | 5.2.11, 6.0.2 |

```text
# guards.py at this commit, on SQLite
Ship.objects.values("name\x01")
     ValueError: Column aliases cannot contain whitespace characters, hashes, control characters, quotation marks, semicolons, or SQL comments.
```

## The name of a filtered relation in the join

The name of a `FilteredRelation` becomes the alias of the table its join brings in, where that table is not yet in the query (`django/db/models/sql/query.py:Query.table_alias`); `Join.as_sql` writes the alias after the table (`django/db/models/sql/datastructures.py:Join.as_sql`).

Until 6.1 the compiler wrote a table's alias without quotation marks, so a filtered relation's name reached the statement bare; the fix of CVE-2025-13372 (5.1.15, 5.2.9) refused a dollar sign in one, in PostgreSQL's compiler. At this commit no such refusal exists: since 6.1 `Join.as_sql` quotes the alias with `SQLCompiler.quote_name` ([What changed in expressions, lookups and the compiler](sql.md)).

Before 5.2.11 and 6.0.2 the compiler wrote a name with a period in an ordering as a table and a column, the column as it stood, a form meant for `extra`; a filtered relation's name could be such a name (CVE-2026-1312). At this commit `add_filtered_relation` refuses a name with a period, and the compiler writes a dotted name that way only when it was given to `extra` as its order_by (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`).

```text
# guards.py at this commit, on SQLite
Ship.objects.annotate(**{"crew.name": FilteredRelation("crew")})
     ValueError: FilteredRelation doesn't support aliases with periods (got 'crew.name').
```

## The connector of a `Q`: `Q._check_connector`

`Q.__init__` takes two keyword arguments of its own beside the conditions, `"_connector"` and `"_negated"`, and the connector is the word that `WhereNode.as_sql` writes between the conditions it joins (`django/db/models/sql/where.py:WhereNode.as_sql`). `QuerySet.filter`, `QuerySet.exclude` and `QuerySet.get` pass their keyword arguments on to a `Q`, so a dictionary expanded into them could set it (CVE-2025-64459; 5.1.14, 5.2.8). The fix checks in two places. `Q._check_connector` refuses with `ValueError` any connector but `Q.AND`, `Q.OR`, `Q.XOR` and `None`, in the constructor and, at this commit, in `Q.create` (`django/db/models/query_utils.py:Q._check_connector`). `QuerySet._filter_or_exclude_inplace` refuses both with `TypeError`, by the set `PROHIBITED_FILTER_KWARGS`, and at this commit `When.__init__` does the same (`django/db/models/query.py:QuerySet._filter_or_exclude_inplace`; [`filter`, `exclude` and `Q` objects](../querysets/filters.md)).

```text
# guards.py at this commit, on SQLite
Ship.objects.filter(name="Petrel", _connector="OR")
     TypeError: The following kwargs are invalid: '_connector'
Q(name="Petrel", _connector="NAND")
     ValueError: connector must be one of 'AND', 'OR', 'XOR', or None.
```

## Values written into the statement: Oracle's JSON paths and PostGIS's band indices

On Oracle a JSON path cannot be a bind variable, the comments in the JSON lookups say, so the lookups write it into the statement (`django/db/models/fields/json.py:HasKeyLookup`). Before 5.0.10 and 5.1.4 `HasKey` on Oracle wrote all its parameters there, those of its left-hand side among them, which a `HasKey` made directly could take from the caller (CVE-2024-53908); `"has_key"` used through the double-underscore syntax was unaffected, the notes say. At this commit `HasKeyLookup.as_oracle` writes only the path and passes the left-hand side's parameters as bind variables (`django/db/models/fields/json.py:HasKeyLookup.as_oracle`). A comment says that each key of the path passes through `json.dumps`, which writes U+FFFF as an escape, and the path stands in an Oracle literal delimited by U+FFFF, so that the delimiter is never in it (`django/db/models/fields/json.py:ProcessJSONLHSMixin._process_as_oracle`; [The SQL a backend writes: `BaseDatabaseOperations`](../backends/operations.md)).

A raster lookup on PostGIS may carry a band index in its value (`django/contrib/gis/db/models/lookups.py:GISLookup.process_band_indices`), and `PostGISOperator.check_raster` writes the index into the SQL beside its operand. Since 5.2.11 and 6.0.2 (CVE-2026-1207) it raises `TypeError` for an index that is not an integer (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperator.check_raster`; [Spatial lookups, functions and distances](../contrib/spatial-queries.md)).
