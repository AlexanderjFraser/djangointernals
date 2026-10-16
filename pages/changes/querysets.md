---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in querysets

The changes to querysets from Django 5.0 to this commit: fetch modes and `QuerySet.fetch_mode` (6.1), beside which `QuerySet.select_related` with no arguments is deprecated; the orderings of `QuerySet.first`, `QuerySet.last` and combined querysets (6.1) and of the columns of `QuerySet.values` (5.2); and smaller changes to `QuerySet.update_or_create`, `QuerySet.bulk_create`, `QuerySet.in_bulk`, `QuerySet.values_list`, the iterators, prefetching, `QuerySet.raw` and `QuerySet.explain`.

A queryset still builds its query and makes instances from the rows as [QuerySets](../querysets.md) tells. What changed most is what an instance does when it is read for a value the queryset did not load, which since 6.1 the queryset decides. Of the others, some alter a default in silence and some remove what an earlier release deprecated.

## Fetch modes

Until 6.1, reading a deferred field, or a related object that an instance had not cached, ran a query for that one instance. Since 6.1 the read is handed to the instance's **fetch mode**, an object that decides how the value is fetched. `FETCH_ONE`, the default, fetches it for the one instance, which the release notes call Django's existing behaviour. `FETCH_PEERS` fetches it at once for every instance that the same run of the queryset made, the instance's **peers**. `FETCH_RAISE` refuses, with `FieldFetchBlocked`, a `FieldError` (`django/db/models/fetch_modes.py`, `django/core/exceptions.py:FieldFetchBlocked`). The notes give the new modes their purposes: the peers bring most cases of the "N+1 queries problem" down to two queries, and the refusal keeps unintended queries out of code where they would cost (`docs/releases/6.1.txt`).

`QuerySet.fetch_mode` sets a mode on a clone of the queryset, which hands it to each instance made from a row through a keyword argument that 6.1 added to `Model.from_db`, `fetch_mode=None` (`django/db/models/query.py:QuerySet.fetch_mode`, `django/db/models/base.py:Model.from_db`). [Deferred fields and fetch modes in a queryset](../querysets/deferred.md) tells the mechanism, and [Reading and setting related objects](../models/related-objects.md) what a relation's descriptor does under each mode. Here four sailors, two to a ship, have their ships read in a loop:

```text
# fetch_modes.py at this commit: [s.ship.name for s in Sailor.objects.fetch_mode(mode).order_by("id")]
FETCH_ONE     5 statements   ['Petrel', 'Petrel', 'Gannet', 'Gannet']
FETCH_PEERS   2 statements   ['Petrel', 'Petrel', 'Gannet', 'Gannet']
FETCH_RAISE   1 statement    FieldFetchBlocked: Fetching of Sailor.ship blocked.
```

Under the default each sailor's ship was fetched for that sailor, Petrel twice; under the peers the first read fetched the four sailors' ships, by a prefetch of one statement (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.fetch_many`).

In 6.1 a queryset of a model whose own `from_db` accepts neither `fetch_mode=` nor arbitrary keywords crashed when iterated; 6.1.1 made such overrides work again, and deprecated them (`docs/releases/6.1.1.txt`). At this commit `_get_from_db` inspects the override, warns with `RemovedInDjango2028Warning`, and calls it without the mode, so its instances are not given the queryset's (`django/db/models/query.py:_get_from_db`).

Beside fetch modes, 6.1 deprecated `select_related` with no arguments, which has the compiler follow the relations that cannot be null. The call warns with `RemovedInDjango2028Warning`, the notes name `FETCH_PEERS` as the other way to the related objects, and the deprecation timeline has the call raise `TypeError` in Django 2028 (`django/db/models/query.py:QuerySet.select_related`, `docs/internals/deprecation.txt`). [What still warns: the deprecations and the releases that end them](deprecations.md) lists both deprecations.

The notes of 6.1.2, a release expected and not yet made at this commit, list as fixed a bug of 6.1 in which `FETCH_PEERS` did not batch the instances that `select_related` loaded (`docs/releases/6.1.2.txt`). At this commit each `RelatedPopulator`, which makes the instances of one joined model, keeps a list of peers of its own under a mode that tracks them, so the ships joined to one run of sailors are each other's peers (`django/db/models/query.py:RelatedPopulator`).

## Orderings

`QuerySet.first` and `QuerySet.last` give a queryset with no ordering one by primary key. Until 6.1 they did so also for a queryset whose ordering had been cleared on purpose, by `QuerySet.order_by` with no arguments. Since 6.1 they read the mark that call leaves, `Query.default_ordering` turned off, and use the queryset as it stands (`django/db/models/query.py:QuerySet.first`; [`get`, `first`, `count` and the other methods that run a query at once](../querysets/results.md)).

A queryset made by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference` has the model's default ordering since 6.1: `QuerySet._combinator_query` clears the ordering of the combined query and turns its default back on (`django/db/models/query.py:QuerySet._combinator_query`). The notes give the consequence: where `values` or `values_list` has not selected a field of that ordering, the statement fails with `DatabaseError`, and `order_by()` with no arguments on the combined queryset clears the default (`docs/releases/6.1.txt`). Ship is ordered by name:

```text
# combined.py at this commit, on SQLite; left and right are each Ship.objects.order_by().values("tonnage")
list(left.union(right))              DatabaseError: ORDER BY term does not match any column in the result set.
list(left.union(right).order_by())   [{'tonnage': 480}, {'tonnage': 1200}]
```

The parts were cleared first: each keeps a default ordering of its own, which `order_by()` on the combined queryset leaves in place, and a backend that cannot order the parts of a compound statement, as SQLite cannot, refuses that with another `DatabaseError` (`django/db/models/sql/compiler.py:SQLCompiler.get_combinator_sql`; [Combining querysets: the operators and `union`](../querysets/combining.md)).

`QuerySet.totally_ordered` (6.1) is a property beside `QuerySet.ordered`, true only where the ordering is deterministic (`django/db/models/query.py:QuerySet.totally_ordered`; [Annotations, ordering and the other methods that change the query](../querysets/methods.md)).

Since 5.2 the columns of the statement of `QuerySet.values` and `QuerySet.values_list` stand in the order the names were given; the notes say the order had followed counterintuitive rules that made combining such querysets with `union` unpredictable (`docs/releases/5.2.txt`). `Query.set_values` records each name, with where its column comes from, in `Query.selected`, and `SQLCompiler.get_select` writes the select list from it (`django/db/models/sql/query.py:Query.set_values`, `django/db/models/sql/compiler.py:SQLCompiler.get_select`). Given no names, `values` leaves `selected` as `None`, and the compiler's own order stands: the extra columns, the model's fields, the annotations ([`values` and `values_list`: rows as dictionaries and tuples](../querysets/values.md)).

## The smaller changes

| the subject | what changed | release | where now |
|---|---|---|---|
| `QuerySet.update_or_create` | takes `create_defaults=`, the values for a row it has to make, `defaults=` serving for both where that is `None`; so does `QuerySet.aupdate_or_create`. A condition on a field named create_defaults is now taken for the argument unless written `"create_defaults__exact"` | 5.0 | [Creating, updating and deleting through a queryset](../querysets/writing.md) |
| `QuerySet.bulk_create` | with `update_conflicts=True`, sets each instance's primary key from the rows the statement returns, where the backend can return rows from a bulk insert | 5.0 | `django/db/models/query.py:QuerySet._batched_insert`; [`bulk_create` and `bulk_update`](../querysets/bulk.md) |
| `QuerySet.in_bulk` | can follow `values` and `values_list`, and selects the key's field where they did not | 6.1 | `django/db/models/query.py:QuerySet.in_bulk` |
| `QuerySet.values_list` | `flat=True` with no field name warns with `RemovedInDjango2028Warning` and takes the attname of the model's first concrete field; the timeline has it raise `TypeError` | 6.1 | `django/db/models/query.py:QuerySet.values_list` |
| `QuerySet.iterator` | with prefetch lookups and no `chunk_size=`, raises `ValueError` | 5.0 | [`prefetch_related`: related objects in a second query](../querysets/prefetch.md) |
| `QuerySet.aiterator` | follows prefetch lookups a chunk at a time, through `aprefetch_related_objects`, new beside it (5.0); with them and no `chunk_size=`, warns with `RemovedInDjango2029Warning` and takes 2,000 (6.2) | 5.0, 6.2 | [The asynchronous methods of a queryset](../querysets/async.md) |
| the prefetcher's methods | get_prefetch_queryset of the related managers and descriptors, and the method get_current_queryset of `Prefetch`, deprecated in 5.0, are gone: `get_prefetcher` looks for `get_prefetch_querysets` alone | 6.0 | `django/db/models/query.py:get_prefetcher`; [`prefetch_related`: related objects in a second query](../querysets/prefetch.md) |
| `QuerySet.raw` | serves a model with a `CompositePrimaryKey`, whose every field has to be among the columns | 6.0 | [Raw querysets](../querysets/raw.md) |
| `QuerySet.explain` | on PostgreSQL, passes on `generic_plan=True` (5.1), `memory=True` and `serialize="text"` (5.2); the notes ask PostgreSQL 17 for the last two, and the code checks no version | 5.1, 5.2 | `django/db/backends/postgresql/operations.py:DatabaseOperations.explain_query_prefix` |
| a filter across a relation | an instance whose primary key is not set, `Model._is_pk_set` false, is refused with `ValueError`; one given a key and never saved is not | 5.0 | `django/db/models/fields/related_lookups.py:get_normalized_value` |
