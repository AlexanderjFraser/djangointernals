---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Security fixes: SQL injection

Patch releases from 5.0.8 to 6.0.2 closed SQL injection through an alias, the name of a `FilteredRelation`, the connector of a `Q`, a direct has-key lookup on Oracle and PostGIS's raster lookups.

The ORM sends a value to the database as a parameter, where nothing in it can change what the statement says. A name cannot go that way: the alias of a column or of a joined table, and the word that joins two conditions, are part of the statement's text. A backend quotes a name by wrapping it, and escapes no quotation mark inside it, so a quotation mark would end the name early (`django/db/backends/postgresql/operations.py:DatabaseOperations.quote_name`). The defence is to refuse such a name before it is written. Some names come from the caller, as the keywords of `QuerySet.annotate` and `QuerySet.filter`. A program that expands a dictionary built from a request into them lets the request choose them. Each flaw below was a path by which such a name, or on Oracle and PostGIS a value, reached the text unrefused.

Each fix also went to 4.2's patch releases 4.2.15 to 4.2.28 (`docs/releases/4.2.15.txt`, `docs/releases/4.2.28.txt`). 6.1 came out on 5 August 2026, the day after 5.2.17 and 6.0.8 (`docs/releases/6.1.txt`). 6.1.1 lists no security fix (`docs/releases/6.1.1.txt`). 5.2.17, 6.0.8 and 6.1.1 carry each fix alike, except where 6.1 changed a guard again. 6.1 quotes table aliases, which replaced PostgreSQL's refusal of a dollar sign. It carried CVE-2025-64459's guards to `Q.create` and `When`.

## What an alias may contain: `Query.check_alias`

Fixes since 5.0 widened `Query.check_alias`, which raises `ValueError` for an alias it refuses. It checks every name of a filtered relation, and every alias a caller gives to `QuerySet.annotate`, `QuerySet.alias`, `QuerySet.aggregate`, `QuerySet.values`, `QuerySet.values_list` or the `select=` of `QuerySet.extra`. It refuses a name where `FORBIDDEN_ALIAS_PATTERN` finds a quotation mark, whitespace, a control character, a semicolon, a hash or a comment marker; the quotation marks include SQLite's square brackets (`django/db/models/sql/query.py:Query.check_alias`; [The SELECT clause: `get_select`, the select mask and `klass_info`](../sql/select.md#annotations-and-extras-the-masks)).

Until 5.0.8 the names given to `values` and `values_list` as positional arguments went unchecked, and a JSON key named there (`"data__key"`) became an alias (CVE-2024-42005). `Query.set_values` now checks each. The hash came with CVE-2025-59681, a fix for MySQL and MariaDB (5.1.13, 5.2.7). The control characters, U+0000 to U+001F and U+007F to U+009F, came with CVE-2026-1287 (5.2.11, 6.0.2).

The examples use Remark, a model with a JSON field, data, and a foreign key to Entry, related name remarks. For every alias it refuses, the check gives one message, listing what an alias may not contain:

```text recording=changes
Entry.objects.annotate(**{"total\x01": Count("remarks")}): a control character in an alias
    5.2.17       ValueError: Column aliases cannot contain whitespace characters, hashes, control characters, quotation marks, semicolons, or SQL comments.
    6.0.8        ValueError: Column aliases cannot contain whitespace characters, hashes, control characters, quotation marks, semicolons, or SQL comments.
    6.1.1        ValueError: Column aliases cannot contain whitespace characters, hashes, control characters, quotation marks, semicolons, or SQL comments.
    this commit  ValueError: Column aliases cannot contain whitespace characters, hashes, control characters, quotation marks, semicolons, or SQL comments.
```

A percent sign is accepted, and warns since 6.0 ([What changed in expressions, lookups and the compiler](sql.md)).

> **Trap.** The check reads the whole name given to `values`, so it also refuses a JSON key that is no attack but holds a space, such as `values("data__first name")`. The 5.0.8 notes speak only of crafted keys.

## The name of a filtered relation

Since 5.1.12 and 5.2.6 `Query.check_alias` also checks the name of a `FilteredRelation`, the alias of the table its join brings in (CVE-2025-57833). `Join.as_sql` writes that alias after the table (`django/db/models/sql/datastructures.py:Join.as_sql`; [`filter`, `exclude` and `Q` objects](../querysets/filters.md#filteredrelation-a-condition-in-the-join)). `Query.add_filtered_relation` hands the name to the check, after refusing a name with a period (`django/db/models/sql/query.py:Query.add_filtered_relation`).

The period's refusal came with CVE-2026-1312 (5.2.11, 6.0.2). Its notes say `QuerySet.order_by` "was subject to SQL injection in column aliases containing periods" when a `FilteredRelation` used the same alias (`docs/releases/5.2.11.txt`). Until then the compiler took an ordering with a period for one given to the `order_by=` of `QuerySet.extra`, and wrote the text after the period verbatim. At this commit it does so only for one that was (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`).

CVE-2025-13372 (5.1.15, 5.2.9, 6.0's first release) was PostgreSQL's. Until 6.1 the compiler wrote a table's alias bare. The fix made PostgreSQL's compiler refuse a dollar sign in a filtered relation's name. 6.1 quotes the alias of every table and join with `SQLCompiler.quote_name`, and PostgreSQL's backend lost its own compiler for a SELECT (`django/db/backends/postgresql/compiler.py`; [What changed in expressions, lookups and the compiler](sql.md)). Compiled for PostgreSQL, the dollar sign is refused under 5.2.17 and 6.0.8 and quoted under 6.1.1 and this commit:

```text recording=changes
Entry.objects.annotate(**{"remark$": FilteredRelation("remarks")}).values("remark$__title"), compiled for PostgreSQL: a dollar sign in the name of a filtered relation
    5.2.17       ValueError: Dollar signs are not permitted in column aliases on PostgreSQL.
    6.0.8        ValueError: Dollar signs are not permitted in column aliases on PostgreSQL.
    6.1.1        SELECT "remark$"."title" AS "remark$__title" FROM "journal_entry" LEFT OUTER JOIN "journal_remark" "remark$" ON ("journal_entry"."id" = "remark$"."entry_id")
    this commit  SELECT "remark$"."title" AS "remark$__title" FROM "journal_entry" LEFT OUTER JOIN "journal_remark" "remark$" ON ("journal_entry"."id" = "remark$"."entry_id")
```

## The connector of a `Q`: `PROHIBITED_FILTER_KWARGS`

A dictionary expanded into `QuerySet.filter` could set the connector of a `Q` until CVE-2025-64459's fix (5.1.14, 5.2.8, 6.0's first release). The connector is the word `WhereNode.as_sql` writes between the conditions it joins (`django/db/models/sql/where.py:WhereNode.as_sql`). `filter`, `QuerySet.exclude` and `QuerySet.get` hand their keywords to a `Q`, and `Q.__init__` takes two keyword arguments of its own, `"_connector"` and `"_negated"`. The fix guards twice. `QuerySet._filter_or_exclude_inplace` refuses both keywords with `TypeError`, by `PROHIBITED_FILTER_KWARGS` (`django/db/models/query.py:QuerySet._filter_or_exclude_inplace`). `Q` refuses with `ValueError` any connector but `Q.AND`, `Q.OR`, `Q.XOR` and `None` ([`filter`, `exclude` and `Q` objects](../querysets/filters.md#the-two-keyword-arguments-that-are-refused)).

6.1 carried the guard further, which no note lists. `Q._check_connector` also checks the connector given to `Q.create`, a class method by which Django builds `Q` objects of its own (`django/db/models/query_utils.py:Q._check_connector`). Django's own calls give it `Q.AND`, `Q.OR`, `Q.XOR`, the connector of a `Q` it copies, or none. Under 5.2.17 and 6.0.8 the connector `"OR 1=1 OR"` stands between the two conditions; 6.1.1 and this commit refuse it:

```text recording=changes
Entry.objects.filter(Q.create([("title", "Dawn"), ("title", "Noon")], connector="OR 1=1 OR")), by the undocumented Q.create: the WHERE clause
    5.2.17       ("journal_entry"."title" = %s OR 1=1 OR "journal_entry"."title" = %s)
    6.0.8        ("journal_entry"."title" = %s OR 1=1 OR "journal_entry"."title" = %s)
    6.1.1        ValueError: connector must be one of 'AND', 'OR', 'XOR', or None.
    this commit  ValueError: connector must be one of 'AND', 'OR', 'XOR', or None.
```

Since 6.1 `When.__init__` also refuses the two keywords with `TypeError` (`django/db/models/expressions.py:When.__init__`). 5.2.17 and 6.0.8 handed them to its `Q`, which refused a bad connector but took `"_negated"`. Under those releases `When(title="Dawn", _negated=True, then=Value(1))` marked every entry but Dawn.

## Values written into the statement: Oracle's JSON paths and PostGIS's band indices

Before 5.0.10 and 5.1.4 a `HasKey` made directly on Oracle "was subject to SQL injection if untrusted data was used as a lhs value" (CVE-2024-53908; `docs/releases/5.0.10.txt`). The notes say `"has_key"` through the double-underscore syntax was not. On Oracle a JSON path cannot be a bind variable, the comment in `HasKeyLookup.as_oracle` says, so the JSON lookups write it into the statement, in a literal delimited by U+FFFF. At this commit `as_oracle` binds the left-hand side's parameters. `HasKeyLookup.compile_json_path_final_key` writes the key through `json.dumps`, which escapes U+FFFF, so a key cannot close the literal (`django/db/models/fields/json.py:HasKeyLookup.as_oracle`, `django/db/models/fields/json.py:HasKeyLookup.compile_json_path_final_key`).

Since 5.2.11 and 6.0.2 `PostGISOperator.check_raster` raises `TypeError` for a band index that is not an integer (CVE-2026-1207). A raster lookup on PostGIS may carry the index in its value, and `check_raster` writes it into the SQL (`django/contrib/gis/db/models/lookups.py:GISLookup.process_band_indices`, `django/contrib/gis/db/backends/postgis/operations.py:PostGISOperator.check_raster`; [Spatial lookups, functions and distances](../contrib/spatial-queries.md)).
