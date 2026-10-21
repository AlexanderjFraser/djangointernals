---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Deferred fields in a queryset: `defer` and `only`

`QuerySet.defer` and `QuerySet.only` leave columns out of a queryset's statement by recording names on its query; `QuerySet.fetch_mode` sets the fetch mode that the queryset hands to the instances it makes, which decides how one of them fetches a value it was made without.

A table's row can be wide and a use of it narrow: a page that lists a thousand sailors by name has no use for the other columns of each. So a queryset can be told which columns to leave out of its statement. That saves the columns, and it raises two questions the statement cannot answer. An instance made from a short row is an instance like any other, and code that knows nothing of how it was fetched may read any attribute of it, so something has to happen at a read of a value that is not there. And whatever happens is a statement the program did not write: in a loop over the thousand it is a thousand statements, which cost more than the columns did.

The first question has a small answer. On an instance a deferred field is a key missing from its `__dict__` and nothing more, and the descriptor the field left on the class is what Python turns to when the key is missing ([Deferred fields and the fetch modes](../instance/fetching.md#a-deferred-field-is-a-missing-key)). The queryset's part is to select fewer columns and to tell `Model.from_db` which ones it selected. The second question is answered by an object the queryset carries, its **fetch mode**, which is handed the read of a missing value. The queryset gives its mode to the instances it makes, and under one of the modes it also tells each instance which others were made with it, its **peers**, so that a value missing from one can be fetched for all of them together. The same mode decides how a related object that is not at hand is fetched, and [Deferred fields and the fetch modes](../instance/fetching.md) sets the modes side by side and says what a relation's descriptor does under each.

## `defer` and `only`: names recorded on the query

A call of `QuerySet.defer` or of `QuerySet.only` sends nothing. Each returns what `QuerySet._chain` gives it, a clone unless cloning has been turned off for the queryset ([Clones: how a queryset is built](chaining.md)), whose query holds another `Query.deferred_loading`: a pair of a set of names and a flag (`django/db/models/sql/query.py:Query`). With the flag true, the names are the fields to leave out. With it false, they are the only fields to load. A new query has an empty set and a true flag, which leaves nothing out; and a pair whose set is empty restricts nothing, whichever way its flag stands.

`QuerySet.defer` hands its names to `Query.add_deferred_loading`, and `QuerySet.only` hands its own to `Query.add_immediate_loading`. What each makes of them depends on the flag it finds (`django/db/models/sql/query.py:Query.add_deferred_loading`, `django/db/models/sql/query.py:Query.add_immediate_loading`).

| the call | where the set is of names to leave out | where the set is of the only names to load |
|---|---|---|
| `defer` | adds its names to the set | takes its names out of the set |
| `only` | makes the set its own names, less those that were to be left out, and turns the flag to false | replaces the set with its own names |

*What `defer` and `only` do to `Query.deferred_loading`, by the flag they find.*

So a second `defer` adds to the first, a second `only` replaces the first, and an `only` leaves the pair a list of what to load: the docstring of `add_immediate_loading` puts it as overriding any existing immediate values and respecting existing deferrals. One case falls outside the table: a `defer` that leaves nothing of such a list. The pair then starts again from empty, as after `only('name').defer('name')` in the recording below, and those of the `defer`'s names that were not in the list become the names to leave out.

In the recordings, made on SQLite over the rows [QuerySets](../querysets.md) lists, a line at the margin is Python that was run, with the value of an expression after `->`; the lines under it are the calls it set going, nested as they were made and only those the passage is about, with what a call returned after `->`; and a line that begins `SQL` is a statement as Django handed it to its cursor. What a question calls deferred of a queryset is the `deferred_loading` of its query, with the names in order.

```text recording=querysets
deferred(Sailor.objects.all())  ->  ([], True)
deferred(Sailor.objects.defer('name')), deferred(Sailor.objects.defer('name').defer('signed_on'))  ->  ((['name'], True), (['name', 'signed_on'], True))
deferred(Sailor.objects.only('name')), deferred(Sailor.objects.only('name').only('signed_on'))  ->  ((['name'], False), (['signed_on'], False))
deferred(Sailor.objects.only('name', 'signed_on').defer('name')), deferred(Sailor.objects.defer('name').only('name', 'signed_on'))  ->  ((['signed_on'], False), (['signed_on'], False))
deferred(Sailor.objects.defer('name').defer(None))  ->  ([], True)
Sailor.objects.only(None)  ->  raises TypeError: Cannot pass None as an argument to only().
sorted(Sailor.objects.only('name').get(pk=1).get_deferred_fields()), sorted(Sailor.objects.defer('id').get(pk=1).get_deferred_fields())  ->  (['ship_id', 'signed_on'], [])
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
deferred(Sailor.objects.only('name').defer('name')), deferred(Sailor.objects.only('pk'))  ->  (([], True), (['id'], False))
list(Sailor.objects.only('cargo'))  ->  raises FieldDoesNotExist: Sailor has no field named 'cargo'
```

`defer(None)` empties the pair, through `Query.clear_deferred_loading`. `only(None)` is refused with `TypeError`: a comment in the method says that `None` can be passed to `defer` alone, and that people will try all the same. Both methods refuse a queryset made by `union`, `intersection` or `difference` ([Combining querysets: the operators and `union`](combining.md)), and one on which `values` or `values_list` has been called, which makes no instances ([`values` and `values_list`: rows as dictionaries and tuples](values.md)). `only` refuses one thing more, a name whose first part is the alias of a `FilteredRelation` on the query, a relation joined under a condition of its own ([`filter`, `exclude` and `Q` objects](filters.md)) (`django/db/models/query.py:QuerySet.defer`, `django/db/models/query.py:QuerySet.only`).

Neither method looks a name up in the model, except that `add_immediate_loading` exchanges `"pk"` for the name of the model's primary key, which `add_deferred_loading` does not: `only('pk')` is stored as `"id"`. Any other name is stored as it was written: a field's name, or several names joined by `"__"` to reach a field of a model that `select_related` joins ([`select_related`: related objects from the same row](../relations/select-related.md)).

Turning the pair into columns is the query's work and the compiler's. The compiler asks `Query.get_select_mask` for the fields that are to be loaded, model by model, and where the pair restricts anything that method puts the model's primary key among them, whatever the names say ([The SELECT clause: `get_select`, the select mask and `klass_info`](../sql/select.md)). The question about `Model.get_deferred_fields` shows both halves: after `only` with one name the instance lacks two fields and not three, and after a `defer` of the primary key it lacks none. The name `"cargo"`, which is no field of Sailor, is refused with `FieldDoesNotExist` when the queryset is evaluated, and no statement is sent (`django/db/models/sql/query.py:Query.get_select_mask`).

## A shorter statement, and a shorter list for `from_db`

A queryset that leaves columns out sends a shorter statement, and with each row it hands `Model.from_db` the list of the names it did select. Here two sailors are fetched with `only`.

```text recording=querysets
slim = list(Sailor.objects.only('name').order_by('id')[:2])
  QuerySet.only('name')
    Query.add_immediate_loading(('name',))
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQLCompiler.execute_sql
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name" FROM "crew_sailor" ORDER BY "crew_sailor"."id" ASC LIMIT 2
      SQLCompiler.results_iter
      Model.from_db('default', ['id', 'name'], (1, 'Ada'), fetch_mode=FETCH_ONE)  (Sailor)
      Model.from_db('default', ['id', 'name'], (2, 'Bram'), fetch_mode=FETCH_ONE)  (Sailor)
```

The statement selects two columns, the one that was named and the primary key. A row of two values does not say which fields they belong to, so the iterable says it. Before it reads the first row, `ModelIterable.__iter__` makes a list of the attnames of the columns the compiler selected for the queryset's model, an attname being the name of the attribute that holds a field's value on an instance, `"ship_id"` for the foreign key ship, and it passes that list to `Model.from_db` with every row, as the second argument: here `['id', 'name']` (`django/db/models/query.py:ModelIterable.__iter__`). `from_db` compares the number of values with the number of the model's concrete fields, and where the two differ it puts a marker, `DEFERRED`, in the place of each field whose attname is not in the list; `Model.__init__` sets nothing for a marker ([Deferred fields and the fetch modes](../instance/fetching.md#a-deferred-field-is-a-missing-key)). No list of deferred fields passes from the queryset to the instance. The queryset says what was fetched, and the instance is short by the rest.

The other makers of instances do the same for their own columns: a `RelatedPopulator`, for a model that `select_related` joins, and `RawModelIterable`, from the columns a raw statement returned ([`select_related`: related objects from the same row](../relations/select-related.md), [Raw querysets](raw.md)).

## The fetch mode a queryset carries

A queryset holds its mode as `QuerySet._fetch_mode`, which `QuerySet.__init__` sets to `DEFAULT_FETCH_MODE`, a name of the module that is bound to `FETCH_ONE` (`django/db/models/query.py:DEFAULT_FETCH_MODE`). `QuerySet.fetch_mode` sets the mode it was given on what `QuerySet._chain` returns, a clone unless cloning is turned off for the queryset, and that is the whole of the method. It tests neither the query, so it is accepted after `values`, after a slice and after `union`, nor its argument (`django/db/models/query.py:QuerySet.fetch_mode`).

From there the mode travels both ways: from a queryset to the instances it makes, and from an instance to the querysets that are made on its behalf, so that what is reached from an instance has the instance's mode. `Model.from_db` stores the mode in the new instance's state, and an instance that was given none has `FETCH_ONE` from the first time its mode is read ([Deferred fields and the fetch modes](../instance/fetching.md)); a model whose own `from_db` does not take the argument is called without it ([From rows to instances: `ModelIterable`](rows.md)). In the questions below, what is written as mode of several things is the fetch mode of each, a queryset's or an instance's, by its name.

```text recording=querysets
mode(Sailor.objects.all(), Sailor.objects.fetch_mode(models.FETCH_RAISE), Sailor.objects.fetch_mode(models.FETCH_RAISE).filter(pk=1).order_by('name'))  ->  (FETCH_ONE, FETCH_RAISE, FETCH_RAISE)
mode(ada, Sailor.objects.fetch_mode(models.FETCH_PEERS).get(pk=1), Sailor.objects.fetch_mode(models.FETCH_PEERS).get(pk=1).ship)  ->  (FETCH_ONE, FETCH_PEERS, FETCH_PEERS)
...
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor'), Sailor.objects.fetch_mode(models.FETCH_PEERS).create(name='Eve', ship=petrel))  ->  (FETCH_PEERS, FETCH_PEERS)
...
mode(petrel.crew.all(), Ship.objects.fetch_mode(models.FETCH_RAISE).get(pk=1).crew.all())  ->  (FETCH_ONE, FETCH_RAISE)
```

A refined queryset keeps the mode. An instance has the mode of the queryset that made it, and so has the ship that was read from it, which the forward descriptor's queryset fetched. The `RawQuerySet` has it, and so has the sailor `create` saved. And the queryset of a ship's related manager has the ship's mode, which the manager's `_apply_rel_filters` sets on it: the default for petrel, a Ship made in the ordinary way, and `FETCH_RAISE` for the same ship fetched under that mode.

Some places do not hand the mode on. `RawQuerySet._clone` makes its copy without it, so the `RawQuerySet` that `RawQuerySet.prefetch_related` returns has the default mode (`django/db/models/query.py:RawQuerySet._clone`). `QuerySet.bulk_create` sets no mode on the instances it is given, where `create` sets the queryset's on the one it makes (`django/db/models/query.py:QuerySet.bulk_create`, `django/db/models/query.py:QuerySet.create`). And where `QuerySet.prefetch_related` has a related manager fetch the related objects of all a queryset's instances with one statement, the manager's queryset for that statement does not pass through `_apply_rel_filters`: it starts from what the class of the related model's default manager gives, and no mode is set on it. So the objects prefetched for the far end of a foreign key, or across a many-to-many relation, have the mode of that manager's querysets, which for a plain manager is the default, whatever the mode of the instances they were fetched for. A foreign key's own descriptor or a one-to-one field's builds the queryset for a prefetch with its `get_queryset`, and it has the mode of the first of the instances. Either way a queryset that the caller supplied for the prefetch, in a `Prefetch`, is used in its place and keeps the mode it came with ([`prefetch_related`: related objects in a second query](../relations/prefetch.md), `django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`, `django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.get_prefetch_querysets`).

```text recording=querysets
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor').prefetch_related('ship'))  ->  (FETCH_ONE)
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('ship')[0].ship)  ->  (FETCH_PEERS)
...
mode(Ship.objects.fetch_mode(models.FETCH_PEERS).prefetch_related('crew')[0].crew.all()[0])  ->  (FETCH_ONE)
```

The raw queryset lost `FETCH_PEERS` at `prefetch_related`. A ship prefetched for sailors of that mode has it, and a sailor prefetched for a ship of that mode has `FETCH_ONE`: what is missing from such a sailor is fetched for that sailor alone. The documentation says that Django copies the fetch mode of an instance to any related objects it fetches, so that the mode applies to a whole tree of relationships (`docs/topics/db/fetch-modes.txt`). The prefetched sailor is a related object that does not have the ship's mode: there the recording and the documentation differ.
