---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in querysets

Since 6.1, reading a field or related object a queryset did not load follows a fetch mode; `first` and `last` after `order_by()`, and combined querysets, are ordered differently; and `select_related()` and `values_list(flat=True)` with no field named are deprecated.

## Fetch modes

Since 6.1, reading a deferred field, or a related object an instance has not cached, is handed to the instance's **fetch mode**. `FETCH_ONE`, the default, fetches the value for that one instance, as before. `FETCH_PEERS` fetches it for the instance's **peers**, the instances of its model that the same run of the queryset made from the same columns and that are still alive. The same columns are those of the queryset's model, or of one relation that `select_related` joined. The list of peers holds weak references, so an instance that Python has collected is passed over (`django/db/models/query.py:ModelIterable.__iter__`). `FETCH_RAISE` refuses the read with `FieldFetchBlocked`, a `FieldError` (`django/db/models/fetch_modes.py`).

`QuerySet.fetch_mode` sets a mode on a clone. The clone hands the mode to each instance it makes from a row, through the argument `fetch_mode=` that 6.1 added to `Model.from_db` (`django/db/models/query.py:QuerySet.fetch_mode`, `django/db/models/base.py:Model.from_db`; [Deferred fields and fetch modes in a queryset](../querysets/deferred.md)). No setting or model option chooses a mode for many querysets at once. A manager that overrides `BaseManager.get_queryset` to return such a clone gives its mode to every queryset made from the manager (`django/db/models/manager.py:BaseManager.get_queryset`).

Four reporters, two to each of two papers, have their papers read in a loop. With no fetch mode chosen, 5.2.17, 6.0.8, 6.1.1 and this commit each run five statements: one for the reporters and one for each read. Under `FETCH_PEERS`, 6.1.1 and this commit run two: the first read fetches the papers of all four in one statement (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.fetch_many`). The figure sets the three modes one above another: look for how many reads become a statement.

```text figure=fetch-modes
One statement has loaded four reporters, two to each of two papers, without their papers.
A loop then reads each reporter's paper in turn.

FETCH_ONE, the default
  read 1  ->  a statement for its paper
  read 2  ->  a statement for its paper
  read 3  ->  a statement for its paper
  read 4  ->  a statement for its paper

FETCH_PEERS
  read 1  ->  one statement for the papers of all four
  reads 2 to 4: the papers are loaded

FETCH_RAISE
  read 1  ->  FieldFetchBlocked
```

*An arrow is what a read does with a paper not loaded; an accented box is a statement a read runs.*

> **Why.** The notes liken `FETCH_PEERS` to "an on-demand `prefetch_related()`" that needs no list of fields, and mean `FETCH_RAISE` to prevent "unintentional queries" (`docs/releases/6.1.txt`).

The notes of 6.1.2, not yet released at this commit, list as fixed a bug of 6.1: `FETCH_PEERS` did not batch the instances `select_related` loaded (`docs/releases/6.1.2.txt`). At this commit each `RelatedPopulator`, which makes them, keeps a list of its own (`django/db/models/query.py:RelatedPopulator`).

## `Model.from_db` and the overrides written before 6.1

A model whose own `from_db` takes no fetch mode works again since 6.1.1, and warns. The 6.1.1 notes say that such a model crashed in 6.1 when its queryset was iterated (`docs/releases/6.1.1.txt`). At this commit an override that takes neither `fetch_mode=` nor arbitrary keyword arguments is called without the mode, with a `RemovedInDjango2028Warning`. Its instances keep the default mode (`django/db/models/query.py:_get_from_db`).

## `select_related` and `values_list` with nothing named

6.1 deprecated two calls that name no field: `QuerySet.select_related` with no arguments, and `QuerySet.values_list` with `flat=True` and no field name. Both are to raise `TypeError` in Django 2028 (`docs/internals/deprecation.txt`; [What still warns: the deprecations and the releases that end them](deprecations.md)).

With no arguments, `select_related` leaves the relations to the compiler, which follows those that cannot be null (`django/db/models/query_utils.py:select_related_descend`). The notes say to name the relations to fetch instead, or to use `FETCH_PEERS`. The call warns only where it comes from outside Django (`django/db/models/query.py:QuerySet.select_related`, `django/utils/deprecation.py:warn_about_external_use`).

`values_list(flat=True)` with no field changed its statement in 6.0, a release before its warning came. 5.2.17's line is the old statement: it selects every column, and each row's first value is kept. 6.0.8's selects the first concrete field's column alone, with no warning (`django/db/models/query.py:QuerySet.values_list`):

```text recording=changes
Entry.objects.values_list(flat=True), with no field named
    5.2.17       SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry"
    6.0.8        SELECT "journal_entry"."id" AS "id" FROM "journal_entry"
    6.1.1        SELECT "journal_entry"."id" AS "id" FROM "journal_entry", warns RemovedInDjango70Warning
    this commit  SELECT "journal_entry"."id" AS "id" FROM "journal_entry", warns RemovedInDjango2028Warning
```

Entry's values, its keys `[1, 2]`, are the same under all four releases; no note of 6.0 lists the change.

## Orderings

Since 6.1, `QuerySet.first` and `QuerySet.last` leave unordered a queryset whose ordering was cleared on purpose, by `QuerySet.order_by` with no arguments. Until 6.1 they ordered it by primary key, as they still order a queryset that has no ordering. They read the mark that `order_by()` leaves, `Query.default_ordering` turned off (`django/db/models/query.py:QuerySet.first`; [`get`, `first`, `count` and the other methods that run a query at once](../querysets/results.md#an-ordering-cleared-on-purpose)).

Entry has no ordering, so the `ORDER BY` of 6.0.8's statement is `first`'s own: look for it, gone from 6.1.1's. 5.2.17 ran 6.0.8's statement, and this commit 6.1.1's; those two lines:

```text recording=changes
Entry.objects.order_by().first(): the statement it runs
...
    6.0.8        SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" ORDER BY "journal_entry"."id" ASC LIMIT 1
    6.1.1        SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" LIMIT 1
```

> **Trap.** Nothing warns, and since 6.1, which row `first` returns after `order_by()` is the database's choice.

Since 6.1, a queryset made by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference` has its model's default ordering, and nothing warns. `QuerySet._combinator_query` still clears the combined query's ordering, the default with it, and then switches the default back on (`django/db/models/query.py:QuerySet._combinator_query`). The 6.1 notes give the consequence. A combined queryset raises `DatabaseError` where `values` or `values_list` has not selected a field of the ordering (`docs/releases/6.1.txt`).

Letter is ordered by title. The queryset in the block selects only the field pages, outside that ordering. Its union with itself gives its rows under 5.2.17 and 6.0.8, and the error under 6.1.1 and this commit:

```text recording=changes
list(pages.union(pages)), with pages = Letter.objects.order_by().values("pages") and Letter ordered by title
    5.2.17       [{'pages': 3}, {'pages': 12}]
    6.0.8        [{'pages': 3}, {'pages': 12}]
    6.1.1        DatabaseError: ORDER BY term does not match any column in the result set.
    this commit  DatabaseError: ORDER BY term does not match any column in the result set.
```

The error is Django's, so every backend raises it. `SQLCompiler.get_order_by` cannot add the ordering's column to parts whose columns `values` fixed (`django/db/models/sql/compiler.py:SQLCompiler.get_order_by`). Calling `order_by()` on the combined queryset switches the default off, and the union then gives its rows under all four releases.

## The smaller changes

| what | change | where |
|---|---|---|
| `QuerySet.update_or_create` | New in 5.0: `create_defaults=`, the values for a row it makes; left `None`, `defaults=` serves for both. A field named create_defaults is matched only as `"create_defaults__exact"` | `django/db/models/query.py:QuerySet.update_or_create` |
| `QuerySet.bulk_create` | Since 5.0, with `update_conflicts=True`, it sets each instance's key from the rows returned, where the backend returns rows from a bulk insert | `django/db/models/query.py:QuerySet._batched_insert` |
| `QuerySet.in_bulk` | Since 6.1, it can follow `values` and `values_list`, which it refused before with `TypeError` | `django/db/models/query.py:QuerySet.in_bulk` |
| `QuerySet.values` | Since 5.2, its columns and those of `values_list` stand in the order the names were given; the 5.2 notes say that before, "a set of counterintuitive rules" made combining such querysets unpredictable | `django/db/models/sql/query.py:Query.set_values` |
| `QuerySet.totally_ordered` | New in 6.1: beside `QuerySet.ordered`, true only where the ordering includes a unique field, or set of fields, not nullable | `django/db/models/query.py:QuerySet.totally_ordered` |
| `QuerySet.iterator` | Since 5.0, with prefetch lookups and no `chunk_size=`, it raises `ValueError` | `django/db/models/query.py:QuerySet.iterator` |
| `QuerySet.aiterator` | Since 5.0, it follows prefetch lookups a chunk at a time, through `aprefetch_related_objects`. Deprecated in 6.2: with them and no `chunk_size=`, it warns with `RemovedInDjango2029Warning` and takes chunks of 2,000 | [The asynchronous methods of a queryset](../querysets/async.md#with-prefetch-lookups) |
| get_prefetch_queryset and get_current_queryset | Gone in 6.0, deprecated in 5.0: `get_prefetcher` looks for `get_prefetch_querysets` alone, and a descriptor with only the old method gets `ValueError` | `django/db/models/query.py:get_prefetcher` |
| `QuerySet.raw` | Since 6.0, it serves a model with a `CompositePrimaryKey`, every field of the key among the columns; 5.2.17 raised `FieldDoesNotExist` | [Raw querysets](../querysets/raw.md#a-composite-primary-key) |
| `QuerySet.explain` | New in 5.1, on PostgreSQL: `generic_plan=`; new in 5.2, `memory=` and `serialize=`. The notes ask PostgreSQL 16 and 17; the code checks no version | `django/db/backends/postgresql/operations.py:DatabaseOperations.explain_query_prefix` |
| a related filter given an instance | Since 5.0, refused with `ValueError` where `Model._is_pk_set` is false. The 5.0 notes say "unsaved", but an instance given a key and never saved is accepted | `django/db/models/fields/related_lookups.py:get_normalized_value` |
