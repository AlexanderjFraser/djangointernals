---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Reading and setting related objects

When the attribute of a `ForeignKey` or a `OneToOneField` is read or assigned on an instance, from either class of the relation, the work is done by descriptors, `ForwardManyToOneDescriptor` and its relatives, over a cache of related objects in the instance's state. A fetch mode, `FETCH_ONE`, `FETCH_PEERS` or `FETCH_RAISE`, decides how an object that is not at hand is fetched, and the other end of a foreign key is a manager, made at each read.

A row that points at another row holds a key, and so does the instance made from it: a sailor's `__dict__` has `"ship_id"` and a number. What a program wants is the ship. So a relation leaves on its two classes more than a column's worth, and each thing it leaves is a descriptor, an object on the class that Python calls when the attribute is read or assigned on an instance. How the descriptors come to be on the two classes is the subject of [Relations: a field, its rel and the class at the other end](relations.md).

The examples are two relations of the chapter's shipping line, a foreign key and a one-to-one field ([Models and fields](../models.md)).

```python
# harbour/crew/models.py, in the body of Sailor
ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE, related_name="crew")

# harbour/fleet/models.py, in the body of Ship
captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")
```

| where | for a `ForeignKey` | for a `OneToOneField` |
|---|---|---|
| on its own class, under the attname | `ForeignKeyDeferredAttribute` | `ForeignKeyDeferredAttribute` |
| on its own class, under its name | `ForwardManyToOneDescriptor` | `ForwardOneToOneDescriptor` |
| on the other class, under the accessor | `ReverseManyToOneDescriptor`, which gives a manager | `ReverseOneToOneDescriptor`, which gives an object |

*The descriptors that a relation to one object leaves. For the foreign key above they are `"ship_id"` and `"ship"` on Sailor and `"crew"` on Ship; for the one-to-one field, `"captain_id"` and `"captain"` on Ship and `"command"` on Sailor.*

A many-to-many relation has descriptors of its own, and a manager at both ends ([Many-to-many relations](many-to-many.md)).

## Where a related object is kept

A related object, once at hand, is kept on the instance: in a dictionary that belongs to the instance's state, `ModelState.fields_cache`, which is made the first time it is read (`django/db/models/base.py:ModelStateFieldsCacheDescriptor`). The methods that read and write an entry are those of `FieldCacheMixin`, which a relation field and its rel both inherit: `FieldCacheMixin.get_cached_value`, `FieldCacheMixin.is_cached`, `FieldCacheMixin.set_cached_value` and `FieldCacheMixin.delete_cached_value`, each given the instance (`django/db/models/fields/mixins.py:FieldCacheMixin`).

Each of the two names its entry, as `cache_name`. `RelatedField.cache_name` is the field's name, and `ForeignObjectRel.cache_name` is the name of the accessor. So the ship a sailor serves on is under `"ship"` in the sailor's state, and the ship a sailor commands is under `"command"`.

An entry is in one of three conditions, and the descriptors tell them apart. No entry means that nobody has looked. An object means that it is at hand. And `None` means that the question has been settled and there is no object.

## Two attributes for one foreign key

The key of a foreign key and the object it points at are one fact kept in two places: `"ship_id"` in the instance's `__dict__`, and the Ship in the state's cache. The first is what a save writes. The second is a convenience, and it must not be left contradicting the first. Each of the two descriptors that a foreign key leaves on its own class guards one way in.

`ForeignKeyDeferredAttribute` is the one under the attname. It is a `DeferredAttribute` with a `__set__` added. When the value assigned differs from the one the instance holds, and the field has an entry in the cache, the entry is dropped; then the value is stored (`django/db/models/fields/related_descriptors.py:ForeignKeyDeferredAttribute`). Having a `__set__` also changes how Python treats the descriptor on a read. A plain `DeferredAttribute` is passed over whenever the instance has the value ([An instance and its state](instances.md)). One that defines `__set__` is consulted at every read, and this one hands back the value from the `__dict__`.

`ForwardManyToOneDescriptor` is the one under the field's name, and it takes an object. Its `__set__` writes the object's key through the attname, so through the descriptor just described, and then puts the object in the cache.

```text recording=models
bram.ship = gannet
  ForwardManyToOneDescriptor.__set__(<Sailor: Bram>, <Ship: Gannet>)  (Sailor.ship)
    ForeignKeyDeferredAttribute.__set__(<Sailor: Bram>, 2)  (Sailor.ship)
    FieldCacheMixin.set_cached_value(<Sailor: Bram>, <Ship: Gannet>)  (Sailor.ship)
bram.ship_id, bram.ship is gannet  ->  (2, True)
bram.ship_id = petrel.pk
  ForeignKeyDeferredAttribute.__set__(<Sailor: Bram>, 1)  (Sailor.ship)
    FieldCacheMixin.delete_cached_value(<Sailor: Bram>)  (Sailor.ship)
```

The second assignment, of another ship's key, dropped the Gannet from the cache, so that the next read of `"ship"` fetches.

A save takes its own look at the pair, for the case of an object that was assigned before it had a key ([Saving an instance](saving.md)).

## Reading: `ForwardManyToOneDescriptor.__get__`

Reading a sailor's `"ship"` runs `ForwardManyToOneDescriptor.__get__`, which has the object fetched the first time and finds it on the instance after that:

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

Read on the class, the attribute is the descriptor itself. Read on an instance, the method tries four things in order (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__get__`):

1. **The cache.** If the state has an entry for the field, that is the answer, object or `None`. No key is compared and nothing is fetched. The second read in the recording ends here.
2. **The key.** With no entry, the descriptor reads the instance's own half of the relation, which for a foreign key is the one value under the attname. If it is `None`, there is no object to look for.
3. **An ancestor.** The object may be nearer than the database. When the instance is of a child model and the field belongs to a parent, the descriptor follows the child's cached links to its parent objects and asks whether one of them has the related object cached.
4. **The fetch.** Failing that, it hands itself and the instance to the instance's **fetch mode**, an object that decides how what is missing is fetched, and returns what is in the cache when the mode has done.

Where the second or third settled the matter, the descriptor stores what it found as the entry, `None` included, so that the next read stops at the first. And where the first or the second ended with `None`, the field decides what the caller gets: `None` where the field may be null, and where it may not, the descriptor's `RelatedObjectDoesNotExist`.

The third step is for instances reached by walking down from a parent to a child, as the source's comment puts it. An Officer is a Sailor with a second table, and `"ship"` is a field of Sailor. Here an Officer whose parent object has already been asked for is asked for its ship:

```text recording=models
master.ship is read
  ForwardManyToOneDescriptor.__get__(<Officer: Cora>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Officer: Cora>)  (Sailor.ship)  raises KeyError
    FieldCacheMixin.get_cached_value(<Officer: Cora>, default=None)  (Officer.sailor_ptr)  ->  <Sailor: Cora>
    FieldCacheMixin.get_cached_value(<Sailor: Cora>, default=None)  (Sailor.ship)  ->  None
    FetchOne.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Officer: Cora>)
```

The Officer has its Sailor cached under the link `"sailor_ptr"`, that Sailor has no ship cached, and the fetch goes ahead.

### The query that fetches one object

Under the default mode the fetch is `ForwardManyToOneDescriptor.fetch_one`, which gets the object from `ForwardManyToOneDescriptor.get_object` and that from a queryset made by `ForwardManyToOneDescriptor.get_queryset`.

The queryset starts from the related model's `ModelBase._base_manager`, not from its default manager (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.get_queryset`). The base manager is a plain manager unless the model's `Meta` names another, or the base manager of its first parent model is a named one, so a default manager that leaves rows out cannot make the object a key points at disappear ([Managers](managers.md)). The manager is copied by `BaseManager.db_manager` with the instance as a hint for the database router, and the queryset is given the instance's own fetch mode.

`get_object` calls `get` on that queryset with one condition for each pair of fields of the relation: the target's field equal to the instance's key (`django/db/models/fields/related.py:RelatedField.get_reverse_related_filter`). The `LIMIT 21` in the statement is the doing of `QuerySet.get` ([QuerySets](../querysets.md)). Where a key has no row behind it, what `get` raises is the related model's `Model.DoesNotExist`.

`fetch_one` stores the object as the cache entry. For a one-to-one field it also stores the instance on the object it fetched, as the entry of the rel: the other end of such a relation is one object, and it is now known which.

## The fetch modes

A relation's descriptor does not decide how an object that is missing is fetched. It calls `fetch` on the instance's fetch mode, `ModelState.fetch_mode`, with itself and the instance (`django/db/models/base.py:ModelState`, `django/db/models/fetch_modes.py`).

A fetch mode is an object with that one method. What it is handed is a **fetcher**: anything that can fetch its value for one instance, with a method `fetch_one`, and for a list of instances at once, with a method `fetch_many`. The forward descriptor is a fetcher. So is `ReverseOneToOneDescriptor`, and so is the `DeferredAttribute` of a deferred field, whose missing value goes through the same modes ([An instance and its state](instances.md)).

| the mode | its class | what its `fetch` does |
|---|---|---|
| `FETCH_ONE` | `FetchOne` | calls the fetcher's `fetch_one` with the instance |
| `FETCH_PEERS` | `FetchPeers` | gathers the instance's **peers**, the instances that share its list, made with it by one run of a query; with more than one it calls the fetcher's `fetch_many` with all of them, and otherwise `fetch_one` |
| `FETCH_RAISE` | `FetchRaise` | raises `FieldFetchBlocked`, with the names of the instance's class and of the field |

*The three fetch modes. Each is the one object of its class, and `django.db.models` exports the three.*

> **Changed in 6.1.** Fetch modes are new. Before them a read of a related object that was not at hand always ran one query for that one instance, which is what `FETCH_ONE` still does.

### How an instance gets its mode, and its peers

An instance has `FETCH_ONE` until something gives it another: `ModelState.fetch_mode` is a descriptor that supplies `FETCH_ONE` the first time it is read (`django/db/models/base.py:ModelStateFetchModeDescriptor`). Another mode comes from a queryset. `QuerySet.fetch_mode` returns a copy of the queryset that carries the mode, and when the queryset runs, its `ModelIterable` passes the mode to `Model.from_db` with every row, which stores it in the new instance's state (`django/db/models/query.py:QuerySet.fetch_mode`, `django/db/models/query.py:ModelIterable`).

Peers are instances made together by one run of a query. Where the mode's `track_peers` is true, which among the three it is for `FetchPeers` only, `ModelIterable` keeps one list for the instances it makes of the queryset's own model, adds a weak reference to each as it makes it, and binds that list as `ModelState.peers` of each. Every one of those holds the same list, itself in it. The references are weak, the documentation says, so that instances the program has discarded are not kept by the list (`docs/topics/db/fetch-modes.txt`), and `FetchPeers.fetch` takes from it the instances that are still alive (`django/db/models/fetch_modes.py:FetchPeers.fetch`).

Here four sailors are fetched under `FETCH_PEERS`, and the ship of the first is read, then the ship of the last:

```text recording=models
crew = list(Sailor.objects.fetch_mode(models.FETCH_PEERS).order_by('id')[:4])
...
crew[0].ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Ada>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Ada>)  (Sailor.ship)  raises KeyError
    FetchPeers.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Sailor: Ada>)
      ForwardManyToOneDescriptor.fetch_many([<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>])  (Sailor.ship)
        prefetch_related_objects([<Sailor: Ada>, <Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>], 'ship')
          SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE ("fleet_ship"."id") IN ((%s), (%s)) with params (1, 2)
...
crew[3].ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Dag>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Dag>)  (Sailor.ship)  ->  <Ship: Gannet>
```

With four peers the mode calls `ForwardManyToOneDescriptor.fetch_many`. That method sets aside the instances that already have the object cached and gives the others to `prefetch_related_objects`, the function behind `prefetch_related`, with the field's name. One statement fetches the two ships that the four keys name, and fills the cache entry of each sailor (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.fetch_many`).

```text recording=models
Asked of the four
    [type(s._state.fetch_mode).__name__ for s in crew], len(crew[0]._state.peers), bram._state.peers  ->  (['FetchPeers', 'FetchPeers', 'FetchPeers', 'FetchPeers'], 4, ())
    crew[0].ship is crew[1].ship, crew[0].ship == crew[1].ship, crew[2].ship is crew[3].ship  ->  (True, True, True)
```

Sailors of one ship are given one Ship object between them, which a fetch for each sailor would not do. The third value of the first line is the peers of an instance fetched in the ordinary way: an empty tuple.

The fourth step of the read returns what is in the cache without the test for `None`. So where a key has no row, and the prefetch that `fetch_many` runs caches `None` for it, the read that set the fetch off returns `None` even from a field that may not be null, and a later read from such a field raises (`django/db/models/query.py:prefetch_one_level`). A peer with such a key raises at its first read, since the one prefetch cached `None` for each of them.

An instance that was fetched alone is its own only peer, and for it the mode calls `fetch_one`. Of this recording the statement that fetched the sailor is left out, and the lines under `fetch_one`, which are those of any such fetch:

```text recording=models
alone = Sailor.objects.fetch_mode(models.FETCH_PEERS).get(name='Bram')
...
alone.ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Bram>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  raises KeyError
    FetchPeers.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Sailor: Bram>)
      ForwardManyToOneDescriptor.fetch_one(<Sailor: Bram>)  (Sailor.ship)
```

The queryset that fetches a related object is given the instance's mode, so the object fetched has that mode, and so has what is fetched from it in turn. Under `FETCH_PEERS` the objects that one such fetch brings back are peers of each other.

### `FETCH_RAISE`

Under `FETCH_RAISE` the read that would have fetched raises instead:

```text recording=models
strict = Sailor.objects.fetch_mode(models.FETCH_RAISE).get(name='Bram')
...
strict.ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Bram>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  raises KeyError
    FetchRaise.fetch(a ForwardManyToOneDescriptor for Sailor.ship, <Sailor: Bram>)  raises FieldFetchBlocked
  the caller catches FieldFetchBlocked: Fetching of Sailor.ship blocked.
```

`FieldFetchBlocked` is a `FieldError` (`django/core/exceptions.py:FieldFetchBlocked`). The mode is reached only when the cache has no entry and the key is set. An object that is already cached, because it was assigned or was fetched with the instance, is returned under any mode.

## Assigning: `ForwardManyToOneDescriptor.__set__`

Assigning an object to the attribute sends no statement. `ForwardManyToOneDescriptor.__set__` checks the value, copies the key, and updates the caches (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__set__`).

The value has to be `None` or an instance of the relation's target, more exactly of the target's concrete model, so that a relation to a proxy accepts an instance of the model the proxy stands for. Anything else raises `ValueError`.

For an object, the database router is consulted next. Whichever of the two instances has no database in its state yet is given the one that `ConnectionRouter.db_for_write` returns for its class, with the other instance as the hint. Then `ConnectionRouter.allow_relation` is asked about the pair, which where no router of the project answers allows it only when both are of one database, and a refusal raises `ValueError` as well (`django/db/utils.py:ConnectionRouter`). This is how an instance that has never been saved can come to have a database in its state.

Then the key is copied. For each pair of fields of the relation, the value of the object's field is set on the instance under the attname, which runs the `__set__` of `ForeignKeyDeferredAttribute`. Last, the object is put in the cache, and for a one-to-one field the instance is put in the object's cache too, as the entry of the rel.

`None` is assigned in the same way, with one step before. If an object is cached for the field, the descriptor writes `None` into that object's state as the entry of the rel. The source's comment gives the case this is for: a `OneToOneField` set to `None`, where the object once related would otherwise go on holding this instance as its other end, and deleting that object would delete this instance with it. Then the attname is set to `None`, and `None` is cached.

```text recording=models
bram.ship = None
  ForwardManyToOneDescriptor.__set__(<Sailor: Bram>, None)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>, default=None)  (Sailor.ship)  ->  <Ship: Petrel>
    FieldCacheMixin.set_cached_value(<Ship: Petrel>, None)  (the rel of Sailor.ship)
    ForeignKeyDeferredAttribute.__set__(<Sailor: Bram>, None)  (Sailor.ship)
      FieldCacheMixin.delete_cached_value(<Sailor: Bram>)  (Sailor.ship)
    FieldCacheMixin.set_cached_value(<Sailor: Bram>, None)  (Sailor.ship)
bram.ship_id  ->  None
bram.ship is read
  ForwardManyToOneDescriptor.__get__(<Sailor: Bram>)  (Sailor.ship)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (Sailor.ship)  ->  None
    raises RelatedObjectDoesNotExist
  the caller catches Sailor.ship.RelatedObjectDoesNotExist: Sailor has no ship.
```

The second and third lines under the assignment are that step, taken here for a plain foreign key: the Petrel's state gets an entry for the rel. A sailor's `"ship"` may not be null, so the read after the assignment raises, and without a query: the cached `None` settles it.

## `RelatedObjectDoesNotExist`

The exception a descriptor raises for an object that is not there is a class of the descriptor's own. `ForwardManyToOneDescriptor.RelatedObjectDoesNotExist` is made the first time it is needed, with two bases: the `Model.DoesNotExist` of the model that holds the row looked for, and `AttributeError`. `ReverseOneToOneDescriptor.RelatedObjectDoesNotExist` is made likewise. The class is not made with the descriptor, and the source's comment says why: at that moment the related model may not be resolved yet (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.RelatedObjectDoesNotExist`).

```text recording=models
Sailor.command.RelatedObjectDoesNotExist.__mro__[1:3]  ->  (<class 'harbour.fleet.models.Ship.DoesNotExist'>, <class 'django.core.exceptions.ObjectDoesNotExist'>)
issubclass(Sailor.ship.RelatedObjectDoesNotExist, Ship.DoesNotExist), issubclass(Sailor.ship.RelatedObjectDoesNotExist, AttributeError)  ->  (True, True)
hasattr(bram, 'command'), hasattr(cora, 'command')  ->  (False, True)
```

The first base lets a caller catch the exception as the model's ordinary one for a missing row. The second makes an object that is not there look like an attribute that is not there, to `hasattr`, as the last line shows, and to `getattr` with a default.

## One-to-one

A `OneToOneField` is a foreign key whose column is unique. That changes little at the end that holds the column, and everything at the other, where a manager of many objects becomes an attribute that gives one.

### The declaring side: `ForwardOneToOneDescriptor`

Whether a key is unique makes no difference to reading the object it points at, and `ForwardOneToOneDescriptor` inherits the whole of `ForwardManyToOneDescriptor`. It overrides two methods, and both overrides concern one use of the field, the link from a child model to its parent ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)).

A child instance was loaded with the parent's columns among its own, so the parent object can be made without asking the database. `ForwardOneToOneDescriptor.get_object` does that for a field that is a parent link: it calls the parent class with the values the child holds for each of the parent's concrete fields, and copies the child's state onto the result, whether it is being added, its database and its fetch mode. If any of those fields is deferred on the child it gives the idea up and fetches the parent in the ordinary way, which the comment explains as better than a query for each deferred field (`django/db/models/fields/related_descriptors.py:ForwardOneToOneDescriptor.get_object`).

```text recording=models
master.sailor_ptr is read
  ForwardManyToOneDescriptor.__get__(<Officer: Cora>)  (Officer.sailor_ptr, a ForwardOneToOneDescriptor)
    FieldCacheMixin.get_cached_value(<Officer: Cora>)  (Officer.sailor_ptr)  raises KeyError
    FetchOne.fetch(a ForwardOneToOneDescriptor for Officer.sailor_ptr, <Officer: Cora>)
      ForwardManyToOneDescriptor.fetch_one(<Officer: Cora>)  (Officer.sailor_ptr)
        ForwardOneToOneDescriptor.get_object(<Officer: Cora>)  (Officer.sailor_ptr)
          Model.__init__(id=3, name='Cora', ship_id=2, signed_on=datetime(2011, 6, 1, 8, 0, tzinfo=UTC))  (a new Sailor)
          -> <Sailor: Cora>
        FieldCacheMixin.set_cached_value(<Officer: Cora>, <Sailor: Cora>)  (Officer.sailor_ptr)
        FieldCacheMixin.set_cached_value(<Sailor: Cora>, <Officer: Cora>)  (the rel of Officer.sailor_ptr)
    FieldCacheMixin.get_cached_value(<Officer: Cora>)  (Officer.sailor_ptr)  ->  <Sailor: Cora>
```

No statement is sent. The Sailor is made by `Model.__init__` from four values that the Officer already has, and each of the two is then cached on the other.

`ForwardOneToOneDescriptor.__set__` adds one thing to the assignment of its base. When the field is a parent link and the model's primary key, assigning to it also sets the key attributes that the child inherits, to the parent's key or to `None`, so the child's `"id"` follows its link (`django/db/models/fields/related_descriptors.py:ForwardOneToOneDescriptor.__set__`).

### The other side: `ReverseOneToOneDescriptor`

At the other end of a one-to-one field there is at most one object, and the attribute gives that object. `ReverseOneToOneDescriptor.__get__` has the outline of the forward one: the cache, then the fetch mode, then the answer (`django/db/models/fields/related_descriptors.py:ReverseOneToOneDescriptor.__get__`). Its entry is the rel's, in the state of an instance of the target model.

```text recording=models
cora.command is read
  ReverseOneToOneDescriptor.__get__(<Sailor: Cora>)  (the rel of Ship.captain)
    FieldCacheMixin.get_cached_value(<Sailor: Cora>)  (the rel of Ship.captain)  raises KeyError
    FetchOne.fetch(a ReverseOneToOneDescriptor for the rel of Ship.captain, <Sailor: Cora>)
      ReverseOneToOneDescriptor.fetch_one(<Sailor: Cora>)  (the rel of Ship.captain)
        SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."captain_id" = %s LIMIT 21 with params (3,)
        FieldCacheMixin.set_cached_value(<Ship: Gannet>, <Sailor: Cora>)  (Ship.captain)
        FieldCacheMixin.set_cached_value(<Sailor: Cora>, <Ship: Gannet>)  (the rel of Ship.captain)
```

With no entry, the descriptor first asks whether the instance has a primary key, and for one that has none it settles on `None` without a query. Otherwise the fetch mode is called, and `ReverseOneToOneDescriptor.fetch_one` asks the base manager of the declaring model for the row whose key is this instance's. When there is one it caches both ways: the instance in the fetched object's entry for the field, and the object in the instance's entry for the rel. Reading the captain of that ship afterwards finds the sailor in the cache and sends no statement (`django/db/models/fields/related_descriptors.py:ReverseOneToOneDescriptor.fetch_one`).

When there is none, `fetch_one` catches the model's `Model.DoesNotExist` and caches `None`, and `__get__`, having read the entry back, stores it a second time:

```text recording=models
bram.command is read
  ReverseOneToOneDescriptor.__get__(<Sailor: Bram>)  (the rel of Ship.captain)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (the rel of Ship.captain)  raises KeyError
    FetchOne.fetch(a ReverseOneToOneDescriptor for the rel of Ship.captain, <Sailor: Bram>)
      ReverseOneToOneDescriptor.fetch_one(<Sailor: Bram>)  (the rel of Ship.captain)
        SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."captain_id" = %s LIMIT 21 with params (2,)
        FieldCacheMixin.set_cached_value(<Sailor: Bram>, None)  (the rel of Ship.captain)
    FieldCacheMixin.get_cached_value(<Sailor: Bram>)  (the rel of Ship.captain)  ->  None
    FieldCacheMixin.set_cached_value(<Sailor: Bram>, None)  (the rel of Ship.captain)
    raises RelatedObjectDoesNotExist
  the caller catches Sailor.command.RelatedObjectDoesNotExist: Sailor has no command.
```

At this end `None` is never returned. A row that nothing points at is an ordinary thing, and the descriptor raises `RelatedObjectDoesNotExist` for it each time. The cached `None` saves the query at the next read, not the exception: read again, the attribute raises from the first step.

Assigning at this end changes the other object, since the column is the other object's. `ReverseOneToOneDescriptor.__set__` checks the value and consults the router as the forward one does, sets on the object assigned the attname of its field to this instance's key, and caches each of the two on the other (`django/db/models/fields/related_descriptors.py:ReverseOneToOneDescriptor.__set__`). In this recording Cora commands the Gannet, and skua is the Ship named Skua II, fetched just before:

```text recording=models
cora.command, skua.captain_id  ->  (<Ship: Gannet>, None)
cora.command = skua
  ReverseOneToOneDescriptor.__set__(<Sailor: Cora>, <Ship: Skua II>)  (the rel of Ship.captain)
    ForeignKeyDeferredAttribute.__set__(<Ship: Skua II>, 3)  (Ship.captain)
    FieldCacheMixin.set_cached_value(<Sailor: Cora>, <Ship: Skua II>)  (the rel of Ship.captain)
    FieldCacheMixin.set_cached_value(<Ship: Skua II>, <Sailor: Cora>)  (Ship.captain)
cora.command, skua.captain_id, skua.captain is cora  ->  (<Ship: Skua II>, 3, True)
Ship.objects.get(name='Skua II').captain_id, Ship.objects.get(name='Gannet').captain_id  ->  (None, 3)
```

Nothing is saved. The last line asks the table, with its two statements left out: the Skua II has no captain there, and the Gannet still has Cora. The object whose key changed is the caller's to save.

Assigning `None` at this end takes a cached object out of the cache and assigns `None` to the field on that object. Where no object is cached it does nothing at all.

## The other end of a foreign key: a manager

From the other class a foreign key leads to many objects, and reading the attribute fetches none of them. `ReverseManyToOneDescriptor.__get__` returns a manager whose querysets are already narrowed to the rows that point at this instance, and it makes a new one at every read (`django/db/models/fields/related_descriptors.py:ReverseManyToOneDescriptor.__get__`).

```text recording=models
petrel.crew is read
  ReverseManyToOneDescriptor.__get__(<Ship: Petrel>)  (the rel of Sailor.ship)
    ReverseManyToOneDescriptor.related_manager_cls  (the rel of Sailor.ship)
      create_reverse_many_to_one_manager(ManagerFromSailorQuerySet, the rel of Sailor.ship)
      -> the class RelatedManager, whose bases are (ManagerFromSailorQuerySet, AltersData)
    -> a RelatedManager
gannet.crew is read
  ReverseManyToOneDescriptor.__get__(<Ship: Gannet>)  (the rel of Sailor.ship)  ->  a RelatedManager
```

The manager's class is made once for each descriptor, the first time the attribute is read on an instance, and is kept as `ReverseManyToOneDescriptor.related_manager_cls`. `create_reverse_many_to_one_manager` defines the class, `RelatedManager`, inside itself, with two bases: the class of the default manager of the model that declares the foreign key, and `AltersData`, which copies onto a subclass's override of a method the mark that keeps a template from calling it (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`, `django/db/models/utils.py:AltersData`).

That first base gives the manager of a ship's crew every method of the class of Sailor's default manager. Sailor's `"objects"` is made by `QuerySet.as_manager` from a queryset class of the project's, SailorQuerySet, and the class of such a manager has the methods of its queryset class:

```python
# harbour/crew/models.py
class SailorQuerySet(models.QuerySet):
    def aboard(self, ship):
        return self.filter(ship=ship)
```

```text recording=models
petrel.crew is petrel.crew, type(petrel.crew) is type(gannet.crew)  ->  (False, True)
[c.__name__ for c in type(petrel.crew).__mro__]  ->  ['RelatedManager', 'ManagerFromSailorQuerySet', 'Manager', 'BaseManagerFromQuerySet', 'BaseManager', 'AltersData', 'object']
hasattr(petrel.crew, 'aboard'), hasattr(petrel.crew, 'remove'), hasattr(petrel.crew, 'clear')  ->  (True, False, False)
```

A `RelatedManager` can be called. Called with `manager="..."`, the name of another manager of the related model, it returns a manager of the same kind for the same instance, built on that manager's class; a class is made for it at each such call. The class also sets `do_not_call_in_templates`, which keeps the template engine from calling a manager it comes upon (`django/template/base.py:Variable._resolve_lookup`) ([Templates](../templates.md)).

### The queryset, and what its instances already know

Every queryset method of a manager goes through its `get_queryset` ([Managers](managers.md)), and `RelatedManager` has one of its own. It refuses an instance that has no primary key with `ValueError`. It returns the prefetched result when the instance has one for this relation. Otherwise it takes the queryset its base would return and passes it through `_apply_rel_filters`.

`_apply_rel_filters` gives the queryset the instance as a hint for the router, the instance's fetch mode, and one filter: the foreign key equal to the instance. Where the instance's own value for the relation is `None` it returns an empty queryset instead. And it leaves a note on the queryset, `QuerySet._known_related_objects`, which says that for this field the object with this key is this instance (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`). `ModelIterable` reads the note, and assigns that object to the field on each instance it makes that has the key. The first of the Petrel's crew is quoted, and the others are dealt with in the same way:

```text recording=models
list(petrel.crew.all())
  ReverseManyToOneDescriptor.__get__(<Ship: Petrel>)  (the rel of Sailor.ship)  ->  a RelatedManager
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s with params (1,)
  ForwardManyToOneDescriptor.__set__(<Sailor: Ada>, <Ship: Petrel>)  (Sailor.ship)
    FieldCacheMixin.set_cached_value(<Sailor: Ada>, <Ship: Petrel>)  (Sailor.ship)
```

Each sailor is given the Petrel through the forward descriptor's `__set__`, and it is the very object whose attribute was read.

### Changing the set

The objects a `RelatedManager` stands for are rows of the other table, and belonging to its set is a value in a column of theirs. So each method that changes a ship's crew changes sailors.

| the method | what it sends | what it refuses |
|---|---|---|
| `add` | one `"UPDATE"` by key, through the related model's base manager, which sets the column of the objects given | an object that is not of the related model, with `TypeError`; by default, one that is not saved to the database being written, with `ValueError` |
| `create`, `get_or_create`, `update_or_create` | what the inherited method of that name sends, with this instance among its keyword arguments, under the foreign key's name | |
| `remove` | one `"UPDATE"`, which sets the column of the objects given to null | an object that is not of the related model, with `TypeError`; one that is not in the set, with the `Model.DoesNotExist` of the relation's target model |
| `clear` | one `"UPDATE"`, which sets the column of every object in the set to null | |
| `set` | a query for what is there, then a `remove` of what is not wanted and an `add` of what is not there, in one transaction; with `clear=True`, a `clear` and an `add` of everything | what `add` and `remove` refuse |

*The methods of a `RelatedManager` that change its set (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`).*

The `"UPDATE"` of `add`, `remove` and `clear` saves no object, so no save signal is sent. With `bulk=False` each of the three saves every object instead, in one transaction. `remove` and `clear` are defined only where the foreign key may be null. A sailor's `"ship"` may not be, so a ship's crew has neither and its `set` only adds. Each method refuses an instance whose own value for the relation is `None`.

`add` and `create` first assign the ship to the object, through the forward descriptor. Of `create`, the lines between the assignment and the statement are left out:

```text recording=models
petrel.crew.add(dag)
  ReverseManyToOneDescriptor.__get__(<Ship: Petrel>)  (the rel of Sailor.ship)  ->  a RelatedManager
  RelatedManager.add(<Sailor: Dag>)  (of <Ship: Petrel>)
    ForwardManyToOneDescriptor.__set__(<Sailor: Dag>, <Ship: Petrel>)  (Sailor.ship)
      FieldCacheMixin.set_cached_value(<Sailor: Dag>, <Ship: Petrel>)  (Sailor.ship)
    mark_for_rollback_on_error
    SQL UPDATE "crew_sailor" SET "ship_id" = %s WHERE "crew_sailor"."id" IN (%s) with params (1, 4)
...
  RelatedManager.create(name='Hal')  (of <Ship: Petrel>)
    ForwardManyToOneDescriptor.__set__(<Sailor: Hal>, <Ship: Petrel>)  (Sailor.ship)
      FieldCacheMixin.set_cached_value(<Sailor: Hal>, <Ship: Petrel>)  (Sailor.ship)
...
    SQL INSERT INTO "crew_sailor" ("name", "ship_id", "signed_on") VALUES (%s, %s, %s) RETURNING "crew_sailor"."id" with params ('Hal', 1, '2026-04-10 09:00:00')
```

A Ship is refused as one of a crew, and a queryset is refused to an instance with no primary key:

```text recording=models
dag.ship is petrel, petrel.crew.count()  ->  (True, 5)
  SQL SELECT COUNT(*) AS "__count" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s with params (1,)
petrel.crew.add(Ship(name='Tern'))  ->  raises TypeError: 'Sailor' instance expected, got <Ship: Tern>
Ship(name='Tern').crew.all()  ->  raises ValueError: 'Ship' instance needs to have a primary key value before this relationship can be used.
```

Assigning to the accessor is refused outright: `ReverseManyToOneDescriptor.__set__` raises `TypeError` with a message that points at the manager's `set` (`django/db/models/fields/related_descriptors.py:ReverseManyToOneDescriptor.__set__`). And each method that writes has an asynchronous twin, `aadd` and the rest, which runs the method in a thread through `sync_to_async` ([Sync and async in one chain](../handlers/async.md)).

## What the descriptors offer to `prefetch_related`

`prefetch_related_objects`, the function behind `prefetch_related` and behind a fetch for several peers under `FETCH_PEERS`, knows nothing of relations. For each name it is given it looks for an object with a method `get_prefetch_querysets`: on the class, where a descriptor may have one, and failing that on what the attribute gives for an instance (`django/db/models/query.py:get_prefetcher`). `ForwardManyToOneDescriptor` and `ReverseOneToOneDescriptor` have the method, and so have the related managers. Unless the caller named another attribute for it, what is fetched through one of the two descriptors is put in the state's cache, and what is fetched through a manager in the instance's `_prefetched_objects_cache`, which the manager's `get_queryset` looks in first ([QuerySets](../querysets.md)).
