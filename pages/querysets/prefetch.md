---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `prefetch_related`: related objects in a second query

`QuerySet.prefetch_related` records prefetch lookups on a queryset, and when the queryset is evaluated `prefetch_related_objects` follows each of them one level at a time: it has a prefetcher, a relation's descriptor or a related manager, make one queryset for the related objects of all the instances that lack them, evaluates it once, and leaves each instance's share where a read of the relation will find it. A `Prefetch` is a lookup with a queryset or a destination of its own.

A program that lists ships and the crew of each sends one statement for the ships and then, left to itself, one more for each ship as its loop reaches it. `select_related` is no help: its join would repeat every ship once for each of its sailors. What suits a relation to many is a second statement that asks for the related objects of all the instances at once, by a condition that lists the instances' keys, and a pass in Python that deals the results out. `prefetch_related` asks a queryset for that.

The work is divided between two parties. `prefetch_related_objects` knows the lookups, the order they are taken in and the places a result can be put, and nothing of foreign keys or of the table between two models. What to ask the database, and by what value a related object is matched to its instance, is the answer of a **prefetcher**: any object with a method `get_prefetch_querysets`. In `django/db/models/` the prefetchers are the relation descriptors and related managers of [Reading and setting related objects](../models/related-objects.md) and [Many-to-many relations](../models/many-to-many.md).

## `prefetch_related` records, and `_fetch_all` follows

`QuerySet.prefetch_related` returns a clone whose tuple of **prefetch lookups**, `QuerySet._prefetch_related_lookups`, has the arguments added at its end as they were given: each a string, the name of a relation or several names joined by `"__"`, or a `Prefetch` object. Called with `None` alone, it empties the tuple. Whether a name means anything on the model is not asked until the lookups are followed. The method refuses a queryset made by `union`, `intersection` or `difference` ([Combining querysets: the operators and `union`](combining.md)), and a lookup whose path begins with the alias of a `FilteredRelation` on the query, a relation joined under a condition of its own ([`filter`, `exclude` and `Q` objects](filters.md)); for a `Prefetch` the path tested is the one its result is to be kept under, `Prefetch.prefetch_to` (`django/db/models/query.py:QuerySet.prefetch_related`).

The lookups are followed by `QuerySet._fetch_all`, once it has filled the result cache: where the queryset has lookups and `QuerySet._prefetch_done` is false, it calls `QuerySet._prefetch_related_objects`, which hands the result cache and the lookups to `prefetch_related_objects` and sets `_prefetch_done` (`django/db/models/query.py:QuerySet._fetch_all`, `django/db/models/query.py:QuerySet._prefetch_related_objects`). So `_fetch_all` follows a queryset's lookups once, for all its instances together, and nothing sets `_prefetch_done` back.

In the recordings, made on SQLite over the rows [QuerySets](../querysets.md) lists, a line at the margin is Python that was run, with the value of an expression after `->`; the lines under it are the calls it set going, nested as they were made and only those the passage is about, with what a call returned after `->`; and a line that begins `SQL` is a statement as Django handed it to its cursor. The questions here ask an instance for `_prefetched_objects_cache`, the dictionary an instance is given when a lookup is followed for it; the statements of the first line and of the last are left out.

```text recording=querysets
ships = Ship.objects.prefetch_related('crew'); list(ships); ships.update(tonnage=F('tonnage'))
...
ships._result_cache, ships._prefetch_done  ->  (None, True)
[hasattr(ship, '_prefetched_objects_cache') for ship in ships]  ->  [False, False]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
[hasattr(found, '_prefetched_objects_cache') for found in (Ship.objects.prefetch_related('crew').get(pk=1), Ship.objects.prefetch_related('crew').first(), Ship.objects.prefetch_related('crew')[0])]  ->  [True, True, True]
```

> **Trap.** `QuerySet.update` emptied the result cache and left `_prefetch_done` set, and evaluated again the queryset sent its one statement and prefetched nothing.

A clone carries the tuple and starts with `_prefetch_done` false (`django/db/models/query.py:QuerySet._clone`). So a method that evaluates a clone, as `get` does, and as `first` and an index do on an unevaluated queryset, follows the lookups for the clone's instances, as the last question shows.

## One lookup, level by level

Each part of a prefetch lookup's path is a **level**, counted from nought, and a level is followed once for the objects the level before it hands on, not once for each of them. Here the ports are fetched with the ships of each and the crew of each ship.

```text recording=querysets
ports = list(Port.objects.prefetch_related('ships__crew'))
...
      prefetch_related_objects(model_instances=[<Port: Bergen>, <Port: Leith>, <Port: Lisbon>], 'ships__crew')
        prefetch_one_level(instances=[<Port: Bergen>, <Port: Leith>, <Port: Lisbon>], prefetcher=a RelatedManager for <Port: Bergen>, lookup=Prefetch('ships__crew'), level=0)
          RelatedManager.get_prefetch_querysets(instances=[<Port: Bergen>, <Port: Leith>, <Port: Lisbon>])
            QuerySet._fetch_all
              ModelIterable.__iter__
                SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."home_id" IN (%s, %s, %s) ORDER BY "fleet_ship"."name" ASC with params (1, 2, 3)
          -> ([<Ship: Gannet>, <Ship: Petrel>], [])
        prefetch_one_level(instances=[<Ship: Gannet>, <Ship: Petrel>], prefetcher=a RelatedManager for <Ship: Gannet>, lookup=Prefetch('ships__crew'), level=1)
          RelatedManager.get_prefetch_querysets(instances=[<Ship: Gannet>, <Ship: Petrel>])
            QuerySet._fetch_all
              ModelIterable.__iter__
                SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (%s, %s) with params (2, 1)
            -> (a SailorQuerySet of Sailor, a result cache of 4, the method ForeignObject.get_local_related_value of Sailor.ship, the method ForeignObject.get_foreign_related_value of Sailor.ship, False, 'crew', False)
          -> ([<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], [])
```

At level 0 each port is given its share, the ships whose `"home_id"` is its key: a queryset, kept in the port's `_prefetched_objects_cache` under `"ships"`, whose result cache is that port's ships, the Petrel for Bergen, the Gannet for Leith and an empty list for Lisbon. `prefetch_related_objects` records the two ships under the path `"ships"`, and they are the instances of level 1. There the sailors are dealt out by `"ship_id"` in the same way, Cora and Dag to the Gannet and Ada and Bram to the Petrel under `"crew"`, and the four are recorded under `"ships__crew"`. The manager's answer, the long line under the second statement, is the six things set out under `prefetch_one_level` below. With the queryset's own, three statements were sent, and the number does not grow with the ports, ships or sailors: it is three wherever there is a port with a ship.

```text figure=two-levels
Port.objects.prefetch_related("ships__crew"), evaluated: three statements

the queryset's own statement
    SELECT ... FROM fleet_port ORDER BY name
    3 ports: the queryset's result cache

level 0, "ships": the instances are the 3 ports
    prefetcher: the related manager of the first port
    SELECT ... FROM fleet_ship WHERE home_id IN (1, 2, 3) ORDER BY name
    2 ships, dealt out by home_id:
        each port's _prefetched_objects_cache["ships"] is a queryset whose result cache is that port's ships
        (Bergen: Petrel; Leith: Gannet; Lisbon: an empty list)
    the 2 ships are recorded under the path "ships", and are the instances of the next level

level 1, "crew": the instances are the 2 ships
    prefetcher: the related manager of the first ship, the Gannet
    SELECT ... FROM crew_sailor WHERE ship_id IN (2, 1)
    4 sailors, dealt out by ship_id:
        each ship's _prefetched_objects_cache["crew"] is a queryset whose result cache is that ship's crew
        (Gannet: Cora, Dag; Petrel: Ada, Bram)
    the 4 sailors are recorded under the path "ships__crew"
```

*A prefetch lookup of two parts. Each level here sends one statement for all the objects of the level before, and leaves each object its share.*

## `Prefetch`: a lookup with a queryset or a destination

A prefetch lookup given as a string says which relation to follow. A `Prefetch` may add `queryset=`, the queryset to fetch the related objects with in place of the one the prefetcher would make, and `to_attr=`, the name of an attribute that is to receive the result as a plain list or a plain object.

`Prefetch.__init__` keeps two paths. `Prefetch.prefetch_through` is the path to follow, the lookup as it was given. `Prefetch.prefetch_to` is the path the result is kept under: the same, unless there is a `to_attr`, which replaces its last part. A queryset that is a `RawQuerySet`, or whose iterable class is not `ModelIterable` or a subclass of it, is refused with `ValueError`. Two `Prefetch` objects are equal when their `prefetch_to` is, whatever their querysets (`django/db/models/query.py:Prefetch`).

```text recording=querysets
Prefetch('crew', queryset=Sailor.objects.values('name'))  ->  raises ValueError: Prefetch querysets cannot use raw(), values(), and values_list().
Prefetch('ships__crew', to_attr='hands').prefetch_through, Prefetch('ships__crew', to_attr='hands').prefetch_to  ->  ('ships__crew', 'ships__hands')
Prefetch('crew') == Prefetch('crew', queryset=Sailor.objects.all()), Prefetch('crew') == Prefetch('crew', to_attr='hands')  ->  (True, False)
```

A `to_attr` and a queryset count at the last level of the lookup alone, and a string is wrapped in a `Prefetch` before it is followed (`Prefetch.get_current_to_attr`, `Prefetch.get_current_querysets`, `django/db/models/query.py:normalize_prefetch_lookups`).

A queryset is pickled with its lookups, and pickling evaluates it ([Evaluation and the result cache](evaluation.md)). So that the queryset inside a `Prefetch` is not evaluated too, as its comment says, `Prefetch.__getstate__` puts in its place a clone whose result cache is an empty list and whose `QuerySet._prefetch_done` is set.

```text recording=querysets
pickle.loads(pickle.dumps(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.filter(name='Ada')))))._prefetch_related_lookups[0].queryset._result_cache  ->  []
```

## `prefetch_related_objects`: a stack of lookups and a dictionary of paths

`prefetch_related_objects` takes a list of instances and any number of lookups, and `django.db.models` exports it for a program that has instances already. `aprefetch_related_objects` runs it in a thread ([The asynchronous methods of a queryset](async.md)), and `ForwardManyToOneDescriptor.fetch_many` and `ReverseOneToOneDescriptor.fetch_many` call it under the fetch mode `FETCH_PEERS`, for those of an instance's peers, the instances made with it by one run of a query, that have not got the relation ([Deferred fields and fetch modes in a queryset](deferred.md)).

With no instances it returns at once. Otherwise it keeps a stack of lookups and a dictionary. The stack starts as the lookups it was given, with the first of them on top; lookups the function finds on its way are pushed on top of those, and so are taken before the rest of the caller's. The dictionary maps a path that has been followed to the list of the objects fetched at its end (`django/db/models/query.py:prefetch_related_objects`).

Each lookup taken from the stack is looked for in the dictionary by its `Prefetch.prefetch_to`. One whose path is there is taken to have had its work done by an earlier lookup and is dropped, unless its `Prefetch.queryset` is set: then the function raises `ValueError`. The test is that the `Prefetch` has a queryset, not that it has a different one. Here the string `"crew"` is given first and a `Prefetch` of `"crew"` with a queryset after it, and then the two the other way round. In the other order they raise nothing: the `Prefetch` is followed with its queryset, and the string after it is dropped.

```text recording=querysets
list(Ship.objects.prefetch_related('crew', Prefetch('crew', queryset=Sailor.objects.all())))  ->  raises ValueError: 'crew' lookup was already seen with a different queryset. You may need to adjust the ordering of your lookups.
...
len(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.all()), 'crew'))  ->  2
```

A lookup that is followed is walked a level at a time, with the instances the function was given as the objects of level 0. A level whose path is in the dictionary is not followed again: the objects recorded there are taken up, and the walk goes on. Otherwise each object is first given an empty dictionary as its `_prefetched_objects_cache`, unless it has one. An object that cannot take the attribute ends the lookup without an error, which is why `prefetch_related` after `values` raises nothing and does nothing:

```text recording=querysets
list(Ship.objects.values('name').prefetch_related('crew'))  ->  [{'name': 'Gannet'}, {'name': 'Petrel'}]
  SQL SELECT "fleet_ship"."name" AS "name" FROM "fleet_ship" ORDER BY 1 ASC
```

Then `get_prefetcher` is asked about the name at this level, for the first object alone: the comment says the objects are assumed to be all of one kind. The objects that have not got what the lookup would fetch are picked out, and `prefetch_one_level` fetches for those alone. The related objects it returns are recorded in the dictionary under the path so far, and they, and no others, are the objects of the next level. Where no object needs fetching, the function reads through what is already there.

### `get_prefetcher`: where the prefetcher is found

`get_prefetcher` is given an instance, the name to follow and the name the result is to be kept under, and returns four things: the prefetcher, or `None`; whatever it found on the class under the name, or `None`; whether the name was found at all; and a function that says of an instance whether it already has what the lookup would fetch (`django/db/models/query.py:get_prefetcher`).

It looks on the instance's class first: for a relation to one object, a comment says, reading the attribute on the instance would run the very query the prefetch is there to replace. Where what the class has under the name has a method `get_prefetch_querysets`, that is the prefetcher, as `ForwardManyToOneDescriptor` and `ReverseOneToOneDescriptor` are. Where it has not, the attribute is read on the instance, and what that gives is the prefetcher if it has the method: for a relation to many, the related manager of the first instance, which serves for all. Where the class has nothing under the name, the name counts as found if the instance has such an attribute, and there is no prefetcher.

The last of the four is the test of whether an instance already has the result. Where the two names differ, which is where the result is to go to a `to_attr` of another name than the relation's, as `"crew"` kept as `"veterans"`, the test asks `hasattr` of the instance for the name the result is to be kept under: an instance counts as having the result if it has any attribute of that name. (Where the class has a `cached_property` of the name, the test looks in the instance's `__dict__` instead.) Where the two names are the same and the descriptor is the prefetcher, as for `"ship"` of a sailor, the test is the descriptor's `is_cached`, which looks in the state's cache of related objects. Where they are the same and the class's attribute is not the prefetcher, as for `"crew"` of a ship, the test looks for the name in the instance's `_prefetched_objects_cache`.

Two errors come out of these answers, both raised while the lookups are followed, after the queryset's own statement:

```text recording=querysets
list(Ship.objects.prefetch_related('cargo'))  ->  raises AttributeError: Cannot find 'cargo' on Ship object, 'cargo' is an invalid parameter to prefetch_related()
...
list(Ship.objects.prefetch_related('home__name'))  ->  raises ValueError: 'home__name' does not resolve to an item that supports prefetching - this is an invalid parameter to prefetch_related().
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
  SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE ("fleet_port"."id") IN ((%s), (%s)) with params (2, 1)
```

A name that is not found raises `AttributeError`. A name that is found and has no prefetcher raises `ValueError` where it is the last part of its lookup: the developer who asked for it, the comment says, has made a mistake. In the second question the first part was followed, with its statement, before the second was found wanting. A part that is not the last may be without a prefetcher, and the function reads through it.

### Reading through what is already there

Where no object of a level needs fetching, because there is no prefetcher or because every object has the relation already, `prefetch_related_objects` gets its next list by reading. For each object it takes the list of the queryset in `_prefetched_objects_cache` under the name, if there is one, and otherwise the attribute itself, passing over an `ObjectDoesNotExist` and a `None`. The comment names the cases it has in mind: a relation to one object that `select_related` has already fetched, and a property that cannot be prefetched but has to be passed through (`django/db/models/query.py:prefetch_related_objects`).

Where some objects of a level have the relation and some have not, the objects of the next level are what was fetched for the second kind, and the related objects of the first kind are not among them. Here hands is the list of the four sailors, fetched plainly; Ada, the first, has had her ship read, and `prefetch_related_objects` is then called on the list twice.

```text recording=querysets
prefetch_related_objects(hands, 'ship__home')
  prefetch_related_objects(model_instances=[<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], 'ship__home')
    prefetch_one_level(instances=[<Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], prefetcher=a ForwardManyToOneDescriptor for Sailor.ship, lookup=Prefetch('ship__home'), level=0)
      -> ([<Ship: Petrel>, <Ship: Gannet>], [])
    prefetch_one_level(instances=[<Ship: Petrel>, <Ship: Gannet>], prefetcher=a ForwardManyToOneDescriptor for Ship.home, lookup=Prefetch('ship__home'), level=1)
      -> ([<Port: Bergen>, <Port: Leith>], [])
Sailor.ship.is_cached(hands[3]), hands[1].ship is hands[0].ship, hands[2].ship is hands[3].ship  ->  (True, False, True)
Ship.home.is_cached(hands[0].ship), Ship.home.is_cached(hands[1].ship)  ->  (False, True)
prefetch_related_objects(hands, 'ship__home')
  prefetch_related_objects(model_instances=[<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], 'ship__home')
    prefetch_one_level(instances=[<Ship: Petrel>], prefetcher=a ForwardManyToOneDescriptor for Ship.home, lookup=Prefetch('ship__home'), level=1)
      -> ([<Port: Bergen>], [])
```

In the first call Ada was left out at level 0, since her ship was cached, and ships were fetched for the other three. Those two ships were the objects of level 1, and their home ports were fetched. Ada's own Ship, another object than the Petrel that Bram was given, was not among them, and its home was still not cached. In the second call nobody needed fetching at level 0, so the function read through, and its list for level 1 was the ship of every sailor. Ada's alone lacked its home, and it was fetched.

## `prefetch_one_level`: one queryset, shared out

`prefetch_one_level` is given the instances that need fetching, the prefetcher, the lookup and the level. It calls the prefetcher's `get_prefetch_querysets` with the instances and, at the last level of a lookup that has a queryset of its own, with that queryset in a list, and gets six things back (`django/db/models/query.py:prefetch_one_level`).

| what is returned | for `"crew"` of ships | for `"ship"` of sailors | for `"calls"` of voyages |
|---|---|---|---|
| a queryset for the related objects of all the instances | of Sailor, already evaluated | of Ship, not evaluated | of Port, not evaluated |
| a function that gives, for a related object, the value it is matched by | `ForeignObject.get_local_related_value` of the field: the sailor's `"ship_id"` | `ForeignObject.get_foreign_related_value` of the field: the ship's `"id"` | a function that reads the voyage's key from a column added to the statement |
| a function that gives the same value for an instance | `get_foreign_related_value`: the ship's `"id"` | `get_local_related_value`: the sailor's `"ship_id"` | a function that gives the voyage's own key |
| whether an instance has at most one related object | `False` | `True` | `False` |
| the name the result is kept under | `"crew"` | `"ship"` | `"calls"` |
| whether that name is an attribute to assign to, and not a key of a cache | `False` | `False` | `False` |

*The six things `get_prefetch_querysets` returns, as recorded for three relations of the example: the crew of ships, asked of the manager at the far end of a foreign key; the ship of sailors, asked of a foreign key's descriptor; and the calls of voyages, asked of a many-to-many manager. The values to match by are tuples.*

The function then makes a list of the queryset, which is the one evaluation unless the prefetcher has evaluated it already, and builds a dictionary from the value of each related object to the list of the objects that have that value. For each instance it looks up the instance's value and stores what it finds; an instance with nothing under its value gets `None` where the relation is to one object, and an empty list where it is to many. It returns the list of all the related objects, with any lookups it found on the queryset.

Here the four sailors are fetched with the ship of each.

```text recording=querysets
sailors = list(Sailor.objects.order_by('id').prefetch_related('ship'))
...
        prefetch_one_level(instances=[<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], prefetcher=a ForwardManyToOneDescriptor for Sailor.ship, lookup=Prefetch('ship'), level=0)
          QuerySet._fetch_all
            ModelIterable.__iter__
              SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE ("fleet_ship"."id") IN ((%s), (%s)) with params (1, 2)
          -> ([<Ship: Petrel>, <Ship: Gannet>], [])
sailors[0].ship is sailors[1].ship, Sailor.ship.is_cached(sailors[0]), hasattr(sailors[0], '_prefetched_objects_cache'), sailors[0]._prefetched_objects_cache  ->  (True, True, True, {})
```

Through a foreign key the descriptor is the prefetcher, and the statement was sent by `prefetch_one_level`, not by the descriptor. It asks for two ships, since the four sailors have two keys between them. Each sailor is given the object the dictionary holds for its key, so the sailors of one ship have one Ship object between them. `select_related` does otherwise: it makes a Ship of every row, so two sailors of one ship get two objects that are equal and not the same ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)).

Across a many-to-many relation a port's own columns do not say which voyage it was fetched for. So the manager's queryset adds to its statement the column of the table between the two models, and the function it returns for a related object reads that off the Port ([Many-to-many relations](../models/many-to-many.md), `django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`). Its answer, for two voyages:

```text recording=querysets
ManyRelatedManager.get_prefetch_querysets(instances=[<Voyage: Voyage object (1)>, <Voyage: Voyage object (2)>])  ->  (a QuerySet of Port, no result cache, the function <lambda>, the function <lambda>, False, 'calls', False)
```

### Where a result is put

Where `prefetch_one_level` puts an instance's share depends on the lookup and on the relation. At the last level of a lookup with a `to_attr`, the share is set as an attribute of that name with `setattr`, whatever the relation: the object or `None`, or the list. Otherwise the share of a relation to one, as `"ship"` of a sailor, goes into the state's cache of related objects, `ModelState.fields_cache`, with the name the prefetcher gave as its key (`django/db/models/base.py:ModelState`). That cache is where a relation's descriptor looks before anything else ([Reading and setting related objects](../models/related-objects.md)). And otherwise the share of a relation to many, as `"crew"` of a ship, goes into the instance's `_prefetched_objects_cache` with that name as its key, as a queryset whose result cache has been set to the list.

A prefetcher that said the name was an attribute to assign to, the last row of the table, would have the share of a relation to one set with `setattr` in place of the cache. At this commit every `get_prefetch_querysets` in `django/` says it is not.

For a relation to many, `prefetch_one_level` reads the related manager off the instance and asks it for `get_queryset`: the queryset the manager would give anyway, with the filter for this instance waiting on it ([Clones: how a queryset is built](chaining.md)). At the last level of a lookup that has a queryset of its own, it has the manager's `_apply_rel_filters` narrow a clone of that queryset instead. Either way it sets the result cache to the instance's list by hand, sets `_prefetch_done`, and stores the queryset; the prefetch does not send the statement it stands for. A related manager's `get_queryset` looks in `_prefetched_objects_cache` before it builds anything. Here ships is `list(Ship.objects.prefetch_related('crew'))`, the two ships.

```text recording=querysets
ships[0]._prefetched_objects_cache  ->  {'crew': <SailorQuerySet [<Sailor: Cora>, <Sailor: Dag>]>}
list(ships[0].crew.all()), ships[0].crew.all() is ships[0].crew.all()  ->  ([<Sailor: Cora>, <Sailor: Dag>], True)
...
ships[0].crew.count(), ships[0].crew.exists()  ->  (2, True)
list(ships[0].crew.filter(name='Cora'))  ->  [<Sailor: Cora>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE ("crew_sailor"."ship_id" = %s AND "crew_sailor"."name" = %s) with params (2, 'Cora')
```

`BaseManager.all` returns what `get_queryset` returns and not a clone of it, and a comment there gives this as the reason: a clone would have lost the prefetched list (`django/db/models/manager.py:BaseManager.all`). So `all` of the manager is the stored queryset, the same object at each call, and iterating it, its `count` and its `exists` read the list. `filter` makes a clone, which has the instance's filter and no list, and it sent a statement.

Here each ship is given, as `"veterans"`, those of its crew who signed on before 2020.

```text recording=querysets
ships = list(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.filter(signed_on__year__lt=2020), to_attr='veterans')))
...
        get_prefetcher(instance=<Ship: Gannet>, through_attr='crew', to_attr='veterans')  ->  (a RelatedManager for <Ship: Gannet>, a ReverseManyToOneDescriptor, True, the function has_to_attr_attribute)
...
[(ship.name, ship.veterans) for ship in ships], hasattr(ships[0], '_prefetched_objects_cache'), ships[0]._prefetched_objects_cache  ->  ([('Gannet', [<Sailor: Cora>]), ('Petrel', [<Sailor: Ada>])], True, {})
```

Each ship has a plain list under `"veterans"`, of the sailors the queryset of the `Prefetch` lets through, and nothing in its `_prefetched_objects_cache`: its related manager has no stored queryset to return.

The test `get_prefetcher` gave here is `hasattr` of the ship for `"veterans"`, and it is made before a check that `prefetch_one_level` makes: that a `to_attr` is not the name of a field of the model, with `ValueError` if it is. `prefetch_one_level` is called only for the instances the test found without, so the check never sees a name that every instance already has:

```text recording=querysets
list(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.all(), to_attr='tonnage')))  ->  [<Ship: Gannet>, <Ship: Petrel>]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
...
list(Ship.objects.prefetch_related(Prefetch('crew', queryset=Sailor.objects.all(), to_attr='crew')))  ->  raises ValueError: to_attr=crew conflicts with a field on the Ship model.
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (%s, %s) with params (2, 1)
```

> **Trap.** For `"tonnage"` one statement was sent, for the ships. Every ship has an attribute of that name, so every ship counted as fetched: nothing was prefetched and nothing was raised.

For `"crew"`, whose statement for the ships is left out, the two names are the same, so the test looks in `_prefetched_objects_cache`; the ships are found without, their crews are fetched, and then the check finds the field, `"crew"` being the relation's name as a field as well as its accessor.

The fetch mode of the objects a prefetch brings is that of the queryset they were fetched with, which is not always the mode of the instances ([Deferred fields and fetch modes in a queryset](deferred.md)).

## Lookups found on a prefetcher's queryset

The queryset a prefetcher returns may carry prefetch lookups of its own: because a `Prefetch` supplied a queryset that has them, or because the manager the prefetcher started from gives querysets that have them. `prefetch_one_level` prefers to merge them into the work in hand, as its comment says, to having the queryset follow them when it is evaluated: it copies the lookups it finds on the queryset, empties the queryset's tuple in place, and returns the copies beside the related objects, and `prefetch_related_objects` puts the path so far in front of each and pushes them on its stack.

Here the sailors are fetched with the ship of each, by a queryset of ships that itself prefetches `"crew"`.

```text recording=querysets
sailors = list(Sailor.objects.order_by('id').prefetch_related(Prefetch('ship', queryset=Ship.objects.prefetch_related('crew'))))
...
        prefetch_one_level(instances=[<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], prefetcher=a ForwardManyToOneDescriptor for Sailor.ship, lookup=Prefetch('ship', queryset=a QuerySet of Ship, no result cache), level=0)
          ForwardManyToOneDescriptor.get_prefetch_querysets(instances=[<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], querysets=[a QuerySet of Ship, no result cache])  ->  (a QuerySet of Ship, no result cache, the method ForeignObject.get_foreign_related_value of Sailor.ship, the method ForeignObject.get_local_related_value of Sailor.ship, True, 'ship', False)
          -> ([<Ship: Petrel>, <Ship: Gannet>], ['crew'])
...
        prefetch_one_level(instances=[<Ship: Petrel>, <Ship: Gannet>], prefetcher=a RelatedManager for <Ship: Petrel>, lookup=Prefetch('ship__crew'), level=1)
```

The queryset of ships came back from the descriptor unevaluated, with its lookup on it. `prefetch_one_level` took the lookup off, fetched the ships, and returned the lookup with them. The next thing taken from the stack was `Prefetch('ship__crew')`, whose first level was answered from the dictionary and whose second fetched the crews, at level 1 of the same call.

In `django/db/models/`, the manager at the far end of a foreign key iterates its queryset before returning it, and so do `ReverseOneToOneDescriptor` and, for a one-to-one field, `ForwardManyToOneDescriptor`. That evaluates the queryset with its lookups still on it, so `QuerySet._fetch_all` follows them there, in a call of `prefetch_related_objects` nested inside the first (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`, `django/db/models/fields/related_descriptors.py:ReverseOneToOneDescriptor.get_prefetch_querysets`). A foreign key's descriptor and the many-to-many manager return theirs unevaluated (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.get_prefetch_querysets`).

### The guard against lookups without end

A manager's querysets may prefetch a relation whose own manager's querysets prefetch the first one back, and then every level would find a lookup for the next. `prefetch_related_objects` keeps two sets, of the lookups it has pushed itself and of the descriptors it has prefetched through. After each call of `prefetch_one_level` it records the path and pushes the lookups found, unless three things are true together: the path is in the dictionary already, the lookup is one it pushed itself, and the descriptor has been followed before (`django/db/models/query.py:prefetch_related_objects`).

> **Trap.** At this commit the guard cannot act: the first of the three is never true where it is tested. For two models joined by a many-to-many relation, each with a default manager whose querysets prefetch the other, the levels go on until one of them fetches no objects; with one row of each model, linked to the other, none does, and the evaluation does not return (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`).

## `iterator` with prefetch lookups

`QuerySet.iterator` keeps no result cache and does not go through `QuerySet._fetch_all`. `QuerySet._iterator` takes instances from the iterable in lists of the chunk size, calls `prefetch_related_objects` on each list with the queryset's lookups, and then yields the instances of the list (`django/db/models/query.py:QuerySet._iterator`).

```text recording=querysets
for ship in Ship.objects.prefetch_related('crew').iterator(chunk_size=1): seen(ship)
  QuerySet.prefetch_related('crew')
  QuerySet.iterator(chunk_size=1)  ->  a generator
  QuerySet._iterator(use_chunked_fetch=True, chunk_size=1)
    ModelIterable.__iter__
      SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
    prefetch_related_objects(model_instances=[<Ship: Gannet>], 'crew')
  the loop's body runs with <Ship: Gannet>
    prefetch_related_objects(model_instances=[<Ship: Petrel>], 'crew')
  the loop's body runs with <Ship: Petrel>
```

With a chunk of one, each ship's crew was fetched just before the loop's body ran with the ship. The number given as `chunk_size=` is at once the number of rows asked of the cursor at a call and the number of instances the lookups are followed for at a time. With lookups and no number, `iterator` raises:

```text recording=querysets
list(Ship.objects.prefetch_related('crew').iterator())  ->  raises ValueError: chunk_size must be provided when using QuerySet.iterator() after prefetch_related().
```
