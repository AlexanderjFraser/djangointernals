---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in querysets

From Django 5.0 to this commit querysets gained fetch modes and `QuerySet.fetch_mode` (6.1), and beside them 6.1 deprecated `QuerySet.select_related` given no field and `QuerySet.values_list` given `flat=True` and no field. The orderings of `QuerySet.first`, `QuerySet.last`, combined querysets and `QuerySet.values` changed (5.2, 6.1), and smaller changes run from `QuerySet.in_bulk` to prefetching.

What changed most in [QuerySets](../querysets.md) is what an instance does when it is read for a value the queryset did not load: until 6.1 it ran a query for itself, and since 6.1 the queryset's fetch mode decides whether the value is fetched for that instance, for the instances loaded with it, or refused.

The ordering changes of 6.1 remove two exceptions: `first` and `last` no longer impose an ordering on a queryset whose ordering was cleared on purpose, and a combined queryset no longer escapes its model's default ordering. Neither warns, nor did a change of 6.0 that no note lists, to the columns `values_list(flat=True)` selects with no field named.

## Fetch modes

Until 6.1, reading a deferred field, or a related object an instance had not cached, ran a query for that one instance. Since 6.1 the read is handed to the instance's **fetch mode**. `FETCH_ONE`, the default, fetches the value for the one instance, as before; `FETCH_PEERS` fetches it for the instance's **peers**, the instances of its model that the same run of the queryset made from the same columns and that are still alive, weakly referenced by the list they share, `ModelState.peers`; `FETCH_RAISE` raises `FieldFetchBlocked`, a `FieldError` (`django/db/models/fetch_modes.py`). `QuerySet.fetch_mode` sets a mode on a clone, which hands it to the instances it makes from rows through a keyword 6.1 added to `Model.from_db`, `fetch_mode=None` (`django/db/models/query.py:QuerySet.fetch_mode`, `django/db/models/base.py:Model.from_db`). [Deferred fields and fetch modes in a queryset](../querysets/deferred.md) tells the mechanism.

Four reporters, two to each of two papers, had their papers read in a loop with no fetch mode chosen: five statements under all four releases, one for the reporters and one for each read. The same loop under `FETCH_PEERS`:

```text recording=changes
[r.paper.name for r in Reporter.objects.fetch_mode(FETCH_PEERS)]: the statements it runs
    5.2.17       ImportError: cannot import name 'FETCH_PEERS' from 'django.db.models'
    6.0.8        ImportError: cannot import name 'FETCH_PEERS' from 'django.db.models'
    6.1.1        2 statements
    this commit  2 statements
```

Under the mode, the first read fetched all four reporters' papers in one statement (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.fetch_many`).

> **Why.** The notes liken `FETCH_PEERS` to "an on-demand `prefetch_related()`" that needs no list of fields, and mean `FETCH_RAISE` to prevent "unintentional queries" (`docs/releases/6.1.txt`).

The notes of 6.1.2, not yet released at this commit, list as fixed a bug of 6.1: `FETCH_PEERS` did not batch the instances `select_related` loaded (`docs/releases/6.1.2.txt`). At this commit each `RelatedPopulator`, which makes the instances of one joined relation, keeps its own list of peers (`django/db/models/query.py:RelatedPopulator`). Under `FETCH_PEERS`, reading the publisher of each reporter's paper, the papers joined by `select_related("paper")`, ran five statements under 6.1.1 and two at this commit.

## `Model.from_db` and the overrides written before 6.1

The 6.1.1 notes say that a model whose own `from_db` takes no fetch mode crashed in 6.1 when its queryset was iterated, and that 6.1.1 made it work again, though deprecated (`docs/releases/6.1.1.txt`). At this commit `_get_from_db` inspects the override before the loop and, where it takes neither the keyword fetch_mode nor arbitrary keywords, warns and has it called without the mode, so its instances keep the default mode (`django/db/models/query.py:_get_from_db`). Notice's `from_db` is such an override:

```text recording=changes
[n.title for n in Notice.objects.all()]: a model whose own from_db() takes no fetch_mode
    5.2.17       ['Closed on Monday']
    6.0.8        ['Closed on Monday']
    6.1.1        ['Closed on Monday'], warns RemovedInDjango70Warning
    this commit  ['Closed on Monday'], warns RemovedInDjango2028Warning
```

## `select_related` and `values_list` with nothing named

`QuerySet.select_related` with no arguments leaves the relations to the compiler, which follows those that cannot be null (`django/db/models/query_utils.py:select_related_descend`). 6.1 deprecated the call, the notes naming `FETCH_PEERS` as another way. It warns through `warn_about_external_use`, so not for Django's own calls (`django/db/models/query.py:QuerySet.select_related`, `django/utils/deprecation.py:warn_about_external_use`).

`QuerySet.values_list` with `flat=True` and no field name is the other, and its statement changed a release before its warning came:

```text recording=changes
Entry.objects.values_list(flat=True), with no field named
    5.2.17       SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry"
    6.0.8        SELECT "journal_entry"."id" AS "id" FROM "journal_entry"
    6.1.1        SELECT "journal_entry"."id" AS "id" FROM "journal_entry", warns RemovedInDjango70Warning
    this commit  SELECT "journal_entry"."id" AS "id" FROM "journal_entry", warns RemovedInDjango2028Warning
```

5.2.17 selected every column and kept each row's first value. 6.0.8 selected the first concrete field's column alone, with no warning and no line in the 6.0 notes. 6.1 added the warning (`django/db/models/query.py:QuerySet.values_list`). For Entry the values, its keys `[1, 2]`, were the same under all four. Both calls are to raise `TypeError` in Django 2028 (`docs/internals/deprecation.txt`; [What still warns: the deprecations and the releases that end them](deprecations.md)).

## Orderings

`QuerySet.first` and `QuerySet.last` order by primary key a queryset that has no ordering. Until 6.1 they did so also where the ordering had been cleared on purpose, by `QuerySet.order_by` with no arguments. Since 6.1 they read the mark that call leaves, `Query.default_ordering` turned off, and take the queryset as it stands (`django/db/models/query.py:QuerySet.first`; [`get`, `first`, `count` and the other methods that run a query at once](../querysets/results.md#an-ordering-cleared-on-purpose)). Entry has no ordering. 5.2.17 ran 6.0.8's statement, and this commit 6.1.1's; those two lines:

```text recording=changes
Entry.objects.order_by().first(): the statement it runs
...
    6.0.8        SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" ORDER BY "journal_entry"."id" ASC LIMIT 1
    6.1.1        SELECT "journal_entry"."id", "journal_entry"."title", "journal_entry"."published" FROM "journal_entry" LIMIT 1
```

> **Trap.** Nothing warns. From 6.1 the statement has no `ORDER BY`, and which row comes first is the database's choice.

A queryset made by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference` had no ordering until given one. Since 6.1 it has its model's default: `QuerySet._combinator_query` switches the combined query's default back on (`django/db/models/query.py:QuerySet._combinator_query`). Letter is ordered by title, and a union of its titles ends in `ORDER BY 1 ASC` from 6.1.1, where before it had none. The 6.1 notes give the consequence: where `values` or `values_list` has not selected a field of the ordering, the combined queryset raises `DatabaseError` (`docs/releases/6.1.txt`):

```text recording=changes
list(pages.union(pages)), with pages = Letter.objects.order_by().values("pages") and Letter ordered by title
    5.2.17       [{'pages': 3}, {'pages': 12}]
    6.0.8        [{'pages': 3}, {'pages': 12}]
    6.1.1        DatabaseError: ORDER BY term does not match any column in the result set.
    this commit  DatabaseError: ORDER BY term does not match any column in the result set.
```

The error is Django's, so every backend raises it: `SQLCompiler.get_order_by` cannot add the ordering's column to parts whose columns `values` fixed (`django/db/models/sql/compiler.py:SQLCompiler.get_order_by`). `order_by()` on the combined queryset switches the default off, and the union then gave its rows under all four. The parts were cleared first because on SQLite the compiler refuses a part that keeps an ordering, its model's default included (`django/db/models/sql/compiler.py:SQLCompiler.get_combinator_sql`; [Combining querysets: the operators and `union`](../querysets/combining.md#what-the-compiler-asks-of-the-backend)).

Since 5.2 the columns of `QuerySet.values` and `values_list` stand in the order the names were given, where the 5.2 notes say "a set of counterintuitive rules" had made combining such querysets unpredictable (`docs/releases/5.2.txt`). `Query.set_values` records the names in `Query.selected`, from which `SQLCompiler.get_select` writes the select list (`django/db/models/sql/query.py:Query.set_values`, `django/db/models/sql/compiler.py:SQLCompiler.get_select`).

## The smaller changes

The rest:

| the name | what changed | release | where now |
|---|---|---|---|
| `QuerySet.update_or_create` | takes create_defaults, the values for a row it makes, defaults serving for both where it is `None`; so does `QuerySet.aupdate_or_create`. A field named create_defaults is matched only as `"create_defaults__exact"` | 5.0 | `django/db/models/query.py:QuerySet.update_or_create` |
| `QuerySet.bulk_create` | with update_conflicts, sets each instance's key from the rows returned, where the backend returns rows from a bulk insert | 5.0 | `django/db/models/query.py:QuerySet._batched_insert` |
| `QuerySet.in_bulk` | can follow `values` and `values_list`; refused them with `TypeError` before | 6.1 | `django/db/models/query.py:QuerySet.in_bulk` |
| `QuerySet.totally_ordered` | new beside `QuerySet.ordered`: true only where the ordering includes a unique field, or set of fields, not nullable | 6.1 | `django/db/models/query.py:QuerySet.totally_ordered` |
| `QuerySet.iterator` | with prefetch lookups and no chunk_size, raises `ValueError` | 5.0 | `django/db/models/query.py:QuerySet.iterator` |
| `QuerySet.aiterator` | follows prefetch lookups a chunk at a time, through `aprefetch_related_objects` (5.0); with them and no chunk_size, warns with `RemovedInDjango2029Warning` and takes 2,000, where no earlier release warned (6.2) | 5.0, 6.2 | [The asynchronous methods of a queryset](../querysets/async.md#with-prefetch-lookups) |
| `Prefetch`, related managers and descriptors | get_current_queryset and get_prefetch_queryset, deprecated in 5.0, are gone; `get_prefetcher` looks for `get_prefetch_querysets` alone, and a descriptor with only the old method gets `ValueError`: the lookup "does not resolve to an item that supports prefetching" | 6.0 | `django/db/models/query.py:get_prefetcher` |
| `QuerySet.raw` | serves a model with a `CompositePrimaryKey`, every field of the key among the columns; 5.2.17 raised `FieldDoesNotExist` | 6.0 | [Raw querysets](../querysets/raw.md#a-composite-primary-key) |
| `QuerySet.explain` | on PostgreSQL, passes on generic_plan (5.1), memory and serialize (5.2); the notes ask PostgreSQL 16 and 17, the code checks no version | 5.1, 5.2 | `django/db/backends/postgresql/operations.py:DatabaseOperations.explain_query_prefix` |
| a related filter given an instance | refused with `ValueError` where `Model._is_pk_set` is false; the 5.0 notes say "unsaved", and an instance given a key and never saved is accepted | 5.0 | `django/db/models/fields/related_lookups.py:get_normalized_value` |
