---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Clones: how a queryset is built

A method of `QuerySet` that refines a queryset does its work on a copy: `QuerySet._chain` makes one with `QuerySet._clone`, and the copy has a `Query` of its own. A clone takes most of what its original holds and shares two dictionaries with it; in a few places of its own Django changes a queryset in place instead; and a queryset works out which database it is for each time it is asked.

A queryset is passed around as a value. A view keeps one as an attribute of its class and refines it for each request; a manager's method returns one and its caller filters it; a form holds one for the choices of a field. That only works if refining a queryset cannot change the one somebody else is holding, and so the rule of the class is that a method which would change a queryset changes a clone and returns it. The rule costs an object and a copied query for every step of a chain, and a switch that turns cloning off, used only inside Django, is there to save that cost where the queryset being changed has only just been made.

## What a queryset holds

`QuerySet.__init__` takes a model, a query, a database's alias and a dictionary of hints, each optional, and sets everything else to a fixed starting value (`django/db/models/query.py:QuerySet.__init__`). A manager supplies the model, its own alias and its own hints, and leaves the query to be made new ([Managers](../models/managers.md)).

| attribute | what it is | told in |
|---|---|---|
| `model` | the model class the queryset is for | |
| `_query` | the `Query`, read through the property `QuerySet.query`; made new for the model unless one was given | [From QuerySet to SQL](../sql.md) |
| `_db` | the alias of a database, or `None` to let the router choose | below |
| `_hints` | what the router is told beside the model | below |
| `_for_write` | whether the router is asked for a database to write to | below |
| `_result_cache` | `None`, or the list of what the statement returned | [Evaluation and the result cache](evaluation.md) |
| `_iterable_class` | the class that makes something of each row | [From rows to instances: `ModelIterable` and `select_related`](iterables.md) |
| `_fields` | `None`, or the tuple of names that `values` or `values_list` last passed to `QuerySet._values` | [`values` and `values_list`: rows as dictionaries and tuples](values.md) |
| `_fetch_mode` | the fetch mode given to the instances the queryset makes | [Deferred fields and fetch modes in a queryset](deferred.md) |
| `_known_related_objects` | for a relation field, objects already in hand, by key, to be set on the instances made | [From rows to instances: `ModelIterable` and `select_related`](iterables.md) |
| `_prefetch_related_lookups`, `_prefetch_done` | the prefetch lookups, and a flag that is set once they have been followed | [`prefetch_related`: related objects in a second query](prefetch.md) |
| `_sticky_filter` | a mark a many-to-many manager sets, so that a filter on its queryset shares the joins of the manager's own | below |
| `_defer_next_filter`, `_deferred_filter` | a mark that the next filter is to wait, and the filter that is waiting | below |
| `_cloning_enabled` | whether `_chain` makes a clone | below |

*The attributes `QuerySet.__init__` sets.*

## `_chain` and `_clone`

A method that returns a refined queryset calls `QuerySet._chain` before it changes anything, and makes its change to what comes back. `_chain` ordinarily calls `QuerySet._clone`, which makes a new object of the queryset's own class from the same model, alias and hints and from a copy of the query that `Query.chain` makes, and then copies a fixed list of attributes across by name (`django/db/models/query.py:QuerySet._chain`, `django/db/models/query.py:QuerySet._clone`). In the recordings on this page, made from a running Django over the models and rows that the chapter's opening page, [QuerySets](../querysets.md), lists, the lines set in are calls, nested as they were made, and `->` is what a call or an expression returned.

```text recording=querysets
QuerySet.order_by('name')
  QuerySet._chain
    QuerySet._clone
      Query.chain
        Query.clone
    -> a new SailorQuerySet
  Query.clear_ordering(force=True, clear_default=False)
  Query.add_ordering('name')
```

`QuerySet.all` is `_chain` and nothing else. A queryset is given the method, its docstring says, so that it can stand where a manager is expected.

The attributes `_clone` copies are `_sticky_filter`, `_for_write`, `_prefetch_related_lookups`, `_known_related_objects`, `_iterable_class`, `_fetch_mode` and `_fields`. The rest start again from what `__init__` gives them. So a clone of an evaluated queryset has no result cache, and its prefetch lookups have not been followed for it; and an attribute that a subclass of `QuerySet` sets on its instances is not carried over unless the subclass's own `_clone` carries it. Because the new object is made by calling the class with the four arguments by keyword, a subclass with an `__init__` of its own has to accept them.

What a clone has of its own and what it shares with its original can be asked of the two. Here named is the queryset of the Petrel's crew in order of name, again is the clone that `all` makes of it, and crew is the queryset that the related manager of the Petrel gives:

```text recording=querysets
What a clone shares with the queryset it was made from
    again = named.all()
    again is named, again.query is named.query, again.query.where is named.query.where, again.query.alias_map is named.query.alias_map  ->  (False, False, False, False)
    again.query.order_by is named.query.order_by, again.model is named.model, again._fetch_mode is named._fetch_mode  ->  (True, True, True)
    again._known_related_objects is named._known_related_objects  ->  True
    named._hints, again._hints is named._hints  ->  ({}, False)
    crew = petrel.crew.all()
    crew._hints, crew.all()._hints is crew._hints  ->  ({'instance': <Ship: Petrel>}, True)
    list(named)
      SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "crew_sailor"."name" ASC with params (1,)
    named._result_cache, named.all()._result_cache, named.filter(name='Ada')._result_cache  ->  ([<Sailor: Ada>, <Sailor: Bram>], None, None)
```

The query is a different object, and so are its where clause and its map of aliases: `Query.clone` copies those and most of the query's other dictionaries and sets one by one, and leaves immutable values such as the tuple of an ordering to be shared (`django/db/models/sql/query.py:Query.clone`). `Query.chain` is `clone` followed by a little housekeeping, one piece of which is the sticky filter below (`django/db/models/sql/query.py:Query.chain`).

Two dictionaries are shared between the queryset objects themselves. `_known_related_objects` is one dictionary handed from clone to clone. The hints are the same dictionary too when there are any, and a fresh empty one when there are none, since `__init__` replaces an empty dictionary by a new one. What is put into a shared dictionary through one queryset is there for the other: the operators `&`, `|` and `^` put the right side's known related objects into their clone's dictionary, and with it into that of the queryset the clone was made from ([Combining querysets: the operators and `union`](combining.md)). The last line of the recording shows the result cache staying behind: named has been evaluated, and neither its plain clone nor a filtered one has a list.

## Which database: `db`, `using` and the router

A queryset does not hold a connection. It holds at most an alias, `QuerySet._db`, which is `None` unless the queryset was made with one, as a manager that has an alias makes its querysets, or `QuerySet.using` set one on a clone. What it will use is worked out by the property `QuerySet.db` each time it is read: the alias if there is one, and otherwise the answer of the router, which is asked `db_for_write` when `QuerySet._for_write` is true and `db_for_read` when it is not, with the model and the queryset's hints (`django/db/models/query.py:QuerySet.db`).

The router is one object, `django.db.router`, in front of the routers that the setting `DATABASE_ROUTERS` names. It asks each in turn and takes the first answer that is not empty. With no answer it uses the database that the instance among the hints came from, if there is such a hint and the instance has one, and failing that `"default"` (`django/db/utils.py:ConnectionRouter`). The hints of a queryset are its manager's, and what `QuerySet._add_hints` has added since: a related manager adds the instance it belongs to.

In this recording a router that writes down each question and answers `None` to all of them was installed for the block, and its questions are written under the expression that set them going.

```text recording=querysets
Ship.objects.all().db  ->  'default'
  the router is asked db_for_read(Ship)
Ship.objects.using('default').db  ->  'default'
Ship.objects.all()._db, Ship.objects.using('default')._db  ->  (None, 'default')
petrel.crew.all().db  ->  'default'
  the router is asked db_for_read(Sailor, instance=<Ship: Petrel>)
  the router is asked db_for_read(Sailor, instance=<Ship: Petrel>)
Ship.objects.select_for_update().db  ->  'default'
  the router is asked db_for_write(Ship)
Ship.objects.all()._for_write, Ship.objects.select_for_update()._for_write, Ship.objects.select_for_update().filter(pk=1)._for_write  ->  (False, True, True)
[ship.name for ship in Ship.objects.all()]  ->  ['Gannet', 'Petrel']
  the router is asked db_for_read(Ship)
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
Ship.objects.count()  ->  2
  the router is asked db_for_read(Ship)
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_ship"
Ship.objects.get_or_create(name='Petrel', home=bergen, defaults={'tonnage': 1})  ->  (<Ship: Petrel>, False)
  the router is asked db_for_write(Ship)
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE ("fleet_ship"."home_id" = %s AND "fleet_ship"."name" = %s) LIMIT 21 with params (1, 'Petrel')
Ship.objects.filter(pk=0).update(tonnage=1)  ->  0
  the router is asked db_for_write(Ship)
  the router is asked db_for_write(Ship)
  SQL UPDATE "fleet_ship" SET "tonnage" = %s WHERE "fleet_ship"."id" = %s with params (1, 0)
Port.objects.create(name='Mull', country='Scotland').name  ->  'Mull'
  the router is asked db_for_write(Port)
  SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Mull', 'Scotland')
...
len(Logbook.objects.bulk_create([Logbook(title='Spare log')]))  ->  1
  the router is asked db_for_read(Logbook)
  the router is asked db_for_write(Logbook)
  the router is asked db_for_write(Logbook)
  SQL INSERT INTO "office_logbook" ("title") VALUES (%s) RETURNING "office_logbook"."id" with params ('Spare log',)
```

Nothing is remembered between one reading of `db` and the next, so the router is asked again each time, and a method that reads `db` twice asks twice, as `update` does here. A queryset with an alias of its own never asks. Of the two questions under the crew of the Petrel, the first is the related manager's own, put as it filtered its queryset, and the second is the queryset's.

These methods set `_for_write`: `create`, `bulk_create`, `bulk_update`, `update`, `get_or_create`, `update_or_create` and `QuerySet._insert` set it on the queryset they are called on, and `select_for_update` and `delete` set it on the clone they make. So a queryset that a program holds and calls `update` or `create` on is marked from then on, and its `db` asks the router for a database to write to. `_clone` copies the mark, so a queryset refined from one that was marked for writing reads from the database it would write to. `get_or_create` sets the mark before its `get`, and a comment there gives the reason: the `get` has to be aimed at the database that will be written to, to avoid what the comment calls potential transaction consistency problems (`django/db/models/query.py:QuerySet.get_or_create`). `bulk_create` sets it late: the last lines of the recording show its first question to the router asking for a database to read from, which is the reading of `db` in `QuerySet._check_bulk_create_options`, made before the mark is set ([`bulk_create` and `bulk_update`](bulk.md)).

## Marks on the methods

Two attributes that are set on some of `QuerySet`'s methods, as attributes of the functions, are read by code elsewhere.

```text recording=querysets
sorted(name for name, method in vars(QuerySet).items() if getattr(method, 'alters_data', False))  ->  ['_insert', '_raw_delete', '_update', 'abulk_create', 'abulk_update', 'acreate', 'adelete', 'aget_or_create', 'aupdate', 'aupdate_or_create', 'bulk_create', 'bulk_update', 'create', 'delete', 'get_or_create', 'update', 'update_or_create']
sorted(name for name, method in vars(QuerySet).items() if getattr(method, 'queryset_only', None) is True), sorted(name for name, method in vars(QuerySet).items() if getattr(method, 'queryset_only', None) is False)  ->  (['adelete', 'delete', 'resolve_expression'], ['_insert', '_update'])
```

`"alters_data"` marks a method that writes. The template engine reads it: a variable in a template that resolves to a callable with a true `"alters_data"` is not called (`django/template/base.py:Variable._resolve_lookup`). `QuerySet` inherits from `AltersData`, whose `__init_subclass__` carries the mark down, so that a subclass's own `delete`, written without the mark, takes the mark of the method it overrides (`django/db/models/utils.py:AltersData`).

`"queryset_only"`, where a method has it and the manager's class has nothing of that name, decides whether the class is given a method of the same name. `delete`, `adelete` and `resolve_expression` are kept off managers by a true mark, and the private `_insert` and `_update` are put on them by a false one; how the mark is read is in [Managers](../models/managers.md), with `QuerySet.as_manager`, which makes a manager from a queryset class.

## Changing a queryset in place

`QuerySet._chain` does not always clone. A queryset has a switch, `QuerySet._cloning_enabled`, and while it is off `_chain` returns the queryset it was called on, so that `filter`, `using` and every other method that goes through `_chain` makes its change to that queryset, and one that returns a queryset returns that one (`django/db/models/query.py:QuerySet._disable_cloning`). `QuerySet._avoid_cloning` returns a context manager, `PreventQuerySetCloning`, that turns the switch off on entry and on again on exit (`django/db/models/query.py:PreventQuerySetCloning`).

The switch is used where a queryset has just been made and nothing else can hold it. In `django/db/models/` that is the code of the relations: a related manager applying the filter for its instance to a queryset just made for it, and a descriptor or a related manager building the queryset for a prefetch when the caller supplied none (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`, `django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.get_prefetch_querysets`). Here the crew of the Petrel is asked for, through the ship's related manager ([Reading and setting related objects](../models/related-objects.md)):

```text recording=querysets
crew = petrel.crew.all()
  RelatedManager.get_queryset
    BaseManager.get_queryset  (a RelatedManager for <Ship: Petrel>)  ->  a SailorQuerySet of Sailor, no result cache
    RelatedManager._apply_rel_filters(a SailorQuerySet of Sailor, no result cache)
      QuerySet._avoid_cloning
      PreventQuerySetCloning.__enter__
      QuerySet._add_hints(instance=<Ship: Petrel>)
      QuerySet.filter(ship=<Ship: Petrel>)
        QuerySet._filter_or_exclude(negate=False, args=(), kwargs={'ship': <Ship: Petrel>})
          QuerySet._chain  ->  the queryset itself
      PreventQuerySetCloning.__exit__(exc_type=None, exc_value=None, traceback=None)
```

One queryset is made, by `BaseManager.get_queryset`, and the hint and the filter are both put on it. `_chain` under `filter` returned the queryset itself, where with the switch on it would have made a second queryset and copied the query.

## A filter that waits

The filter that a related manager in `django/db/models/` puts on its queryset for its instance is not applied to the query when `QuerySet.filter` is called: it waits. In the recording above, `filter` was called and `Query.add_q` was not. The related manager sets `QuerySet._defer_next_filter` on the queryset before it filters, and `QuerySet._filter_or_exclude`, finding the mark, clears it and stores the filter's arguments as `QuerySet._deferred_filter` in place of applying them (`django/db/models/query.py:QuerySet._filter_or_exclude`). The condition is built the first time anything reads the queryset's query. `QuerySet.query` is a property: where there is a deferred filter it applies it to the query with `QuerySet._filter_or_exclude_inplace`, forgets it, and then returns the query (`django/db/models/query.py:QuerySet.query`).

```text recording=querysets
crew._deferred_filter, bool(crew._query.where), crew._hints, crew._known_related_objects  ->  ((False, (), {'ship': <Ship: Petrel>}), False, {'instance': <Ship: Petrel>}, {<django.db.models.fields.related.ForeignKey: ship>: {1: <Ship: Petrel>}})
crew.query
  QuerySet._filter_or_exclude_inplace(negate=False, args=(), kwargs={'ship': <Ship: Petrel>})
    Query.add_q(q_object=<Q: (AND: ('ship', <Ship: Petrel>))>)
crew._deferred_filter, bool(crew._query.where)  ->  (None, True)
```

Until the read, the queryset holds the three things `_filter_or_exclude` was given, whether to negate, the positional arguments and the keyword arguments, and its query has an empty where clause. `_clone` reads the property to copy the query, and an evaluation reads it to ask for a compiler, so the filter is in place before a clone is made or a row fetched. A related manager's queryset whose query is never read never builds its condition: a prefetch makes one such queryset for each instance it fills and gives it its list ready-made ([`prefetch_related`: related objects in a second query](prefetch.md)). The last value of the recording's first line is the manager's other gift to its queryset, the Petrel itself under its key, to be set as the ship of each sailor the queryset makes ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)).

`_deferred_filter` is not among the attributes `_clone` copies, and does not need to be: `_clone` reads the property first, which leaves nothing waiting.

## The sticky filter

A many-to-many manager's queryset carries one more mark, the **sticky filter**, which lets a `filter` called on that queryset share the joins of the manager's own filter. The difference it makes is in the statement. Two conditions in one call of `filter` that cross a relation to many rows are about the same related row, and share a join; conditions in separate calls may each be met by a different related row, and each call joins the relation's table again (`docs/topics/db/queries.txt`). How the query decides which joins to share is told in [From QuerySet to SQL](../sql.md). The many-to-many manager's own filter and a `filter` the program calls on its queryset are two calls, and the mark lets the second share the joins of the first. Four querysets, which from the recording's rows return the same ports, show it. Here spring is the voyage of March 2026, which called at Leith and Lisbon, and its attribute calls is the many-to-many manager of its ports. What to look for in each statement is how often it joins `"fleet_voyage_calls"`, the table between voyages and ports: once, or a second time under the alias `"T4"`.

```text recording=querysets
What the sticky filter changes: the joins of four querysets that, from these rows, return the same ports
    list(spring.calls.filter(voyage__sailed__year=2026))  ->  [<Port: Leith>, <Port: Lisbon>]
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" INNER JOIN "fleet_voyage_calls" ON ("fleet_port"."id" = "fleet_voyage_calls"."port_id") INNER JOIN "fleet_voyage" ON ("fleet_voyage_calls"."voyage_id" = "fleet_voyage"."id") WHERE ("fleet_voyage_calls"."voyage_id" = %s AND "fleet_voyage"."sailed" BETWEEN %s AND %s) ORDER BY "fleet_port"."name" ASC with params (1, '2026-01-01', '2026-12-31')
    list(Port.objects.filter(voyage=spring).filter(voyage__sailed__year=2026))  ->  [<Port: Leith>, <Port: Lisbon>]
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" INNER JOIN "fleet_voyage_calls" ON ("fleet_port"."id" = "fleet_voyage_calls"."port_id") INNER JOIN "fleet_voyage_calls" "T4" ON ("fleet_port"."id" = "T4"."port_id") INNER JOIN "fleet_voyage" "T5" ON ("T4"."voyage_id" = "T5"."id") WHERE ("fleet_voyage_calls"."voyage_id" = %s AND "T5"."sailed" BETWEEN %s AND %s) ORDER BY "fleet_port"."name" ASC with params (1, '2026-01-01', '2026-12-31')
    list(Port.objects.filter(voyage=spring, voyage__sailed__year=2026))  ->  [<Port: Leith>, <Port: Lisbon>]
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" INNER JOIN "fleet_voyage_calls" ON ("fleet_port"."id" = "fleet_voyage_calls"."port_id") INNER JOIN "fleet_voyage" ON ("fleet_voyage_calls"."voyage_id" = "fleet_voyage"."id") WHERE ("fleet_voyage_calls"."voyage_id" = %s AND "fleet_voyage"."sailed" BETWEEN %s AND %s) ORDER BY "fleet_port"."name" ASC with params (1, '2026-01-01', '2026-12-31')
    list(spring.calls.order_by('name').filter(voyage__sailed__year=2026))  ->  [<Port: Leith>, <Port: Lisbon>]
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" INNER JOIN "fleet_voyage_calls" ON ("fleet_port"."id" = "fleet_voyage_calls"."port_id") INNER JOIN "fleet_voyage_calls" "T4" ON ("fleet_port"."id" = "T4"."port_id") INNER JOIN "fleet_voyage" "T5" ON ("T4"."voyage_id" = "T5"."id") WHERE ("fleet_voyage_calls"."voyage_id" = %s AND "T5"."sailed" BETWEEN %s AND %s) ORDER BY "fleet_port"."name" ASC with params (1, '2026-01-01', '2026-12-31')
```

The first, through the manager, joins the table between voyages and ports once, as the third does with both conditions in one call. The second, two calls of `filter` on a plain queryset, joins it a second time under the alias `"T4"`. So does the fourth, which goes through the manager with `order_by` before the `filter`, for a reason that the end of this section gives. The docstring of `QuerySet._next_is_sticky`, the method that sets the mark, gives the purpose: so that the results of a related manager can be filtered naturally.

The four return the same ports only because of the rows they were put to. In the next recording Leith has been put on the other voyage as well, the autumn one, which sailed in 2025, and the ports of the spring voyage are asked for with a condition on a voyage of that year; the statements are left out:

```text recording=querysets
list(spring.calls.filter(voyage__sailed__year=2025))  ->  []
list(Port.objects.filter(voyage=spring).filter(voyage__sailed__year=2025))  ->  [<Port: Leith>]
list(spring.calls.order_by('name').filter(voyage__sailed__year=2025))  ->  [<Port: Leith>]
```

With one join, both conditions are about the same voyage, and the spring voyage did not sail in 2025. With two, the second condition is met by any voyage that calls at the port, and Leith is now on one that did.

The mechanism has a part on the queryset and a part on the query. `_next_is_sticky` sets `QuerySet._sticky_filter` and returns the queryset itself, not a clone (`django/db/models/query.py:QuerySet._next_is_sticky`). The next `QuerySet._chain`, which in the manager returns the queryset itself because cloning is off, marks its query, as `Query.filter_is_sticky`, and clears the mark on the queryset (`django/db/models/query.py:QuerySet._chain`). The mark matters when that query is copied. A query keeps a set of table aliases, `Query.used_aliases`: the joins that the conditions added to it since it was last chained have gone through. A new condition that crosses a relation to many rows may go through one of those joins again (`django/db/models/sql/query.py:Query.build_filter`, `django/db/models/sql/query.py:Query.setup_joins`). `Query.chain` ordinarily gives the copy an empty set, so that each call of `filter` starts with none; where the query it copies is marked sticky it leaves the copy's set as it is, and unmarks the copy (`django/db/models/sql/query.py:Query.chain`).

```text recording=querysets
A many-to-many manager's queryset: the next filter is sticky
    ports = spring.calls.all()
      ManyRelatedManager.get_queryset
        BaseManager.get_queryset  (a ManyRelatedManager for <Voyage: Voyage object (1)>)  ->  a QuerySet of Port, no result cache
        ManyRelatedManager._apply_rel_filters(a QuerySet of Port, no result cache)
          QuerySet._avoid_cloning
          PreventQuerySetCloning.__enter__
          QuerySet._add_hints(instance=<Voyage: Voyage object (1)>)
          QuerySet._next_is_sticky
          QuerySet.filter(voyage__id=1)
            QuerySet._filter_or_exclude(negate=False, args=(), kwargs={'voyage__id': 1})
              QuerySet._chain  ->  the queryset itself
          PreventQuerySetCloning.__exit__(exc_type=None, exc_value=None, traceback=None)
    ports._sticky_filter, ports._query.filter_is_sticky, ports._deferred_filter  ->  (False, True, (False, (), {'voyage__id': 1}))
    in_scotland = ports.filter(country='Scotland')
      QuerySet.filter(country='Scotland')
        QuerySet._filter_or_exclude_inplace(negate=False, args=(), kwargs={'voyage__id': 1})
          Query.add_q(q_object=<Q: (AND: ('voyage__id', 1))>)
        QuerySet._filter_or_exclude(negate=False, args=(), kwargs={'country': 'Scotland'})
          QuerySet._chain
            QuerySet._clone
              Query.chain
            -> a new QuerySet
          QuerySet._filter_or_exclude_inplace(negate=False, args=(), kwargs={'country': 'Scotland'})
            Query.add_q(q_object=<Q: (AND: ('country', 'Scotland'))>)
    ports._query.filter_is_sticky, in_scotland.query.filter_is_sticky, sorted(in_scotland.query.used_aliases)  ->  (True, False, ['fleet_port', 'fleet_voyage_calls'])
```

The filter that the manager defers, on the voyage's primary key, is applied when `filter` on the result first reads the query, which it does to see whether the queryset is a combined one ([Combining querysets: the operators and `union`](combining.md)), and its joins go into `used_aliases`. The clone made for the program's own filter is copied from a sticky query, so it keeps them: the last line shows the mark gone from the clone, and among the clone's used aliases the table between voyages and ports, which only the manager's filter joined through. The same line shows the query of the manager's queryset still marked, so every copy made of it keeps the set. What shares the join, then, is a `filter` called directly on the manager's queryset. Where another method comes between, `order_by` for one, it is that method's clone whose query keeps the set, and the copy made from it for the `filter` that follows starts with an empty one.

The `_apply_rel_filters` of `ManyRelatedManager` is the one caller of `_next_is_sticky` in `django/` (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`).
