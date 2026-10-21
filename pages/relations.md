---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: fields, related-objects, many-to-many, select-related, prefetch, checks
---

# Relations

A relation is one fact written in one class and needed in two: a `ForeignKey`, a `OneToOneField` or a `ManyToManyField` on one model, and its rel, the same relation seen from the other. Each end ordinarily leaves an attribute on its class, and the related objects read through them may be kept in caches on the instance, filled by assignment, by a read, by a join in the same row or by a second statement.

The body of Sailor says that each sailor has a ship. A program then wants a sailor's ship, a ship's crew, and the crews of every ship in a list; a query wants sailors filtered by their ship's home port. The field that states the fact stands in one class statement, and the class at the other end may not have been imported when it runs, or may be named only by a string. So Django has to put attributes on two classes from one declaration, some of them long after the first class is made. It has to keep a related object on an instance once it is fetched, so that the next read sends nothing. And it has to offer more than one way of fetching related objects for many instances at once, since otherwise a loop that reads a relation sends, unseen, a statement for each instance.

The examples are harbour's, whose models [Models and fields](models.md) lists: a sailor's *ship*, a foreign key to Ship whose far end is called `"crew"`, a ship's *home* and *captain*, and the ports of call of a Voyage, a many-to-many relation. The recordings were made from a running Django, on SQLite. A line at the left is a line of Python as it was run, or a title saying what was done; the lines set in under it are the calls it set going, nested as they were made, with only those the passage is about written down; `->` gives what a call returned; a name in parentheses after a call is the field whose descriptor or cache it was; a line beginning `SQL` is a statement as Django handed it to its cursor; and a line of three dots stands for lines left out.

## A field and its rel

A `ForeignKey` is a field with a column, like any other. What makes it a relation is a second object it carries as `Field.remote_field`: a **rel**, here a `ManyToOneRel`, which is the same relation seen from the model it points at. The rel is what stands in the other model's list of fields, and it is what names the attribute the other class is given (`django/db/models/fields/__init__.py:Field.__init__`, `django/db/models/fields/reverse_related.py:ForeignObjectRel`). Both are made by the field's own class statement, and the far end of the relation is wired in when both classes are registered: as the field's own class is registered at the end of its statement, if the class it points at is registered already, or else when that class is registered. Until then the field leaves a function waiting in the app registry, and registering a class runs whatever was waiting for it; Ship's *captain* waits so for the crew's Sailor, whose module is imported after the fleet's ([The registry and its models](startup/registry.md)). [Relations: a field, its rel and the class at the other end](relations/fields.md) has what the function does when it runs, the names each end goes by, the column of a foreign key, and the path a query follows across a relation.

## Three kinds of attribute, on two classes

A foreign key leaves three kinds of attribute. On its own class it leaves the key under the field's attname, `"ship_id"` for a sailor, and the related object under the field's name, `"ship"`, each a descriptor (`django/db/models/fields/__init__.py:Field.contribute_to_class`, `django/db/models/fields/related.py:ForeignObject.contribute_to_class`). On the class at the far end it ordinarily leaves one more, named by the rel: for a foreign key a manager, so that the attribute `"crew"` of a ship is not a list but a descriptor that makes, at each read, a manager whose querysets are already filtered to that ship's sailors (`django/db/models/fields/related_descriptors.py:ReverseManyToOneDescriptor.__get__`); for a one-to-one field an object, read through a descriptor of its own. A many-to-many relation has a manager at its own end and, in the ordinary case, at the other, and no column at either: its rows are in a third table, whose model Django makes itself unless the field names one with `through=`, as Sailor's *pilots_into* names the office's Licence. [Reading and setting related objects](relations/related-objects.md) has the descriptors of a foreign key and of a one-to-one field, at both ends, and the manager at the far end of a foreign key; [Many-to-many relations](relations/many-to-many.md) has the field, the table between and its manager.

## Two caches on an instance

The related objects these attributes reach are kept, where they are kept at all, in one of two caches on an instance. An object, the ship of a sailor or the captain of a ship, is kept in the instance's `ModelState.fields_cache` under the relation's name; a set, the crew of a ship, is kept in the instance's `_prefetched_objects_cache`, which the related manager looks in before it sends anything (`django/db/models/base.py:ModelState`, `django/db/models/fields/mixins.py:FieldCacheMixin.set_cached_value`, `django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`). What differs is how a cache is filled, and the figure sets ways side by side for the two ends of one relation.

```text figure=two-ends-two-caches
one relation, declared on Sailor: ship, a ForeignKey to Ship whose far end is called "crew"

the class Sailor                                         the class Ship
  ship_id   a descriptor: the key                          crew   a ReverseManyToOneDescriptor:
  ship      a ForwardManyToOneDescriptor: the object              a related manager, made at each read
  in _meta: the field ship, a ForeignKey   <-- remote_field -->  in _meta: its rel, a ManyToOneRel

an instance of Sailor                                    an instance of Ship
  _state.fields_cache["ship"]: one Ship                    _prefetched_objects_cache["crew"]: the ship's sailors
  filled by                                                filled by
    assignment                  sailor.ship = a ship
    a read that finds nothing                                a read that finds nothing   nothing is kept: the manager's
                                  FETCH_ONE    one statement                              queryset sends its own statement
                                  FETCH_PEERS  may fetch for other sailors too
    select_related("ship")      the same row, by a join
    prefetch_related("ship")    a second statement           prefetch_related("crew")    a second statement, for every ship at once
```

*The two ends of Sailor's foreign key to Ship. Above, what the relation left on each class; below, the cache on an instance of each class where the related objects are kept, and ways that cache is filled.*

**By assignment.** Setting `"ship"` on a sailor sets the key under `"ship_id"` and keeps the ship in the cache; for a one-to-one relation the descriptor also keeps the instance in the cache of the object it was given, so that the relation is known from both ends (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__set__`).

**By a read.** Reading the field's name on an instance gives the related object, fetched on the first read and kept on the instance afterwards:

```text recording=models
A sailor's ship is read twice
    bram.ship is read
      ForwardManyToOneDescriptor.__get__(<Sailor: Bram>)  (Sailor.ship)
        FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  raises KeyError
        FetchOne.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Sailor: Bram>)
          ForwardManyToOneDescriptor.fetch_one(<Sailor: Bram>)  (Sailor.ship)
            ForwardManyToOneDescriptor.get_object(<Sailor: Bram>)  (Sailor.ship)
              SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 21 with params (1,)
              -> <Ship: Petrel>
            FieldCacheMixin.set_cached_value(<Sailor: Bram>, <Ship: Petrel>)  (Sailor.ship)
        FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  ->  <Ship: Petrel>
        -> <Ship: Petrel>
    bram.ship is read again
      ForwardManyToOneDescriptor.__get__(<Sailor: Bram>)  (Sailor.ship)
        FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  ->  <Ship: Petrel>
        -> <Ship: Petrel>
```

The descriptor looked in the cache, found nothing, and did not decide for itself how to fetch: it asked the sailor's **fetch mode**, an object kept in its state that decides whether and how a missing value is fetched, here `FETCH_ONE`, whose `FetchOne.fetch` called back the descriptor's `fetch_one` for this sailor alone. Under `FETCH_PEERS` the mode may call the descriptor's `fetch_many` instead, which fetches, by way of `prefetch_related_objects`, the ships of those sailors made by the same run of a query that are still alive and have none in their cache; under `FETCH_RAISE` it raises `FieldFetchBlocked` (`django/db/models/fetch_modes.py`, `django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.fetch_many`). The fetch modes are [Deferred fields and the fetch modes](instance/fetching.md)'s, since a deferred field asks the same mode. The manager at the far end does not fetch through the mode, and what it fetches is not kept on the ship. Its `get_queryset` returns the set from `_prefetched_objects_cache` where a prefetch left one there, and otherwise a new queryset narrowed to the ship, to which it hands the ship's fetch mode for the sailors that queryset makes (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`).

**By a join in the same row.** `QuerySet.select_related` makes the queryset's own statement join the related table and select its columns beside the model's; as each row is turned into an instance, the related instance is made from its share of the same row and put into the cache. It serves a relation that leads to one object, a foreign key or a one-to-one field ([`select_related`: related objects from the same row](relations/select-related.md)).

**By a second statement.** `QuerySet.prefetch_related` records names of relations on a queryset, and when the queryset is evaluated has them followed once the result cache is filled, here with one more statement for all the instances together:

```text recording=querysets
ships = list(Ship.objects.prefetch_related('crew'))
  QuerySet.prefetch_related('crew')
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
    QuerySet._prefetch_related_objects
      prefetch_related_objects(model_instances=[<Ship: Gannet>, <Ship: Petrel>], 'crew')
...
                SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (%s, %s) with params (2, 1)
                ...
```

The second statement asks for the sailors of both ships at once. They are then sorted by ship in Python, and each ship's list is left in its `_prefetched_objects_cache`, where its related manager will look before it sends anything. `prefetch_related_objects`, which runs this, knows nothing about relations: it finds a descriptor or a manager under a name, and that object supplies the queryset and says how its results are matched to the instances ([`prefetch_related`: related objects in a second query](relations/prefetch.md)).

## Checked afterwards

A relation's mistakes, a target that is not installed or a name that clashes with one the other class already has, are not refused by the class statement, where a target that is never registered only leaves the field's function waiting. They are found by the system checks, which a relation field extends with its own about the other end ([The relation checks: `RelatedField.check`](relations/checks.md)).

## The neighbours

A relation field is a field, and what it shares with the others, its place in `_meta` and its column, is [Models and fields](models.md)'s; the waiting list in which it leaves its function is the app registry's ([The registry and its models](startup/registry.md)). The instance whose cache it fills, and the fetch modes, are [An instance and its row](instance.md)'s; the queryset on which `select_related` and `prefetch_related` record what to fetch, and its evaluation, are [QuerySets](querysets.md)'s. A filter across a relation is walked through its path into joins ([Building a query](query.md)), and the comparisons registered on a relation are among the lookups ([Expressions, lookups and functions](expressions.md)). A relation to any model at all, by a content type and a key, is in [Generic foreign keys: `GenericForeignKey`](contrib/generic-foreign-key.md), and `m2m_changed`, which a many-to-many manager sends as its rows change, in [The signals Django sends](services/builtin-signals.md).
