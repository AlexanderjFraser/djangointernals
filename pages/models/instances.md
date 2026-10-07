---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# An instance and its state

An instance of a model keeps its field values in its own `__dict__`, under the fields' attnames, and one more attribute, `Model._state`, which says where the instance came from. `Model.__init__` makes every instance that is not unpickled or copied, `Model.from_db` makes one from a row, and a field is deferred when its key is simply not in the `__dict__`.

A model class is elaborate. An instance of one is not. Nothing about a row is held anywhere but on the object that stands for it, in ordinary attributes that any code can read and assign, and most of what the class's descriptors do is step in when one of those attributes is missing.

## `Model.__init__`: two ways to give the values

`Model.__init__` takes positional and keyword arguments and has a separate path for each. The source's own comment calls the disparity rather weird and gives the reason for keeping it: the code that turns rows into instances passes its values positionally, and making an instance that way is faster by a third (`django/db/models/base.py:Model.__init__`).

With keyword arguments, which is how a project's own code makes an instance, the method goes through the model's fields in order and finds a value for each:

```text recording=models
Ship(name='Heron', tonnage=300, home=bergen): an instance is made from keyword arguments
    Model.__init__(name='Heron', tonnage=300, home=<Port: Bergen>)  (a new Ship)
      signal pre_init, sender Ship, args=(), kwargs with the keys ['home', 'name', 'tonnage']
      Field.get_default()  (Ship.id)  ->  None
      ForwardManyToOneDescriptor.__set__(<Ship: Heron>, <Port: Bergen>)  (Ship.home)
        ForeignKeyDeferredAttribute.__set__(<Ship: Heron>, 1)  (Ship.home)
      ForeignKey.get_default()  (Ship.captain)
        Field.get_default()  (Ship.captain)  ->  None
        -> None
      ForeignKeyDeferredAttribute.__set__(<Ship: Heron>, None)  (Ship.captain)
      signal post_init, sender Ship
```

Before anything is set, `pre_init` is sent with the class as sender and the arguments as given, and a new `ModelState` is bound to the instance. Then, for each field of `Options.fields`, a value is taken from the keyword arguments under the field's attname, `Field.attname`, the name its value is kept by, which for a foreign key is the field's name with `"_id"` added. Where there is none the field is asked for its default with `Field.get_default` (`django/db/models/fields/__init__.py:Field.get_default`), and asked only then: `__init__` looks the argument up and catches the failure, where handing the lookup a default would have had a default that is a function called for nothing.

A relation is looked for under two names. The keyword may be the field's name with an object, as `home=bergen` is here, or its attname with a key. An object is set through the descriptor under the field's name, which is the `__set__` in the recording: that both writes the key under the attname and keeps the object, so that reading `"home"` afterwards costs no query. A key, or the default where neither was given, is set under the attname. A foreign key's attname has a small descriptor of its own, with a `__set__` that writes the key and drops a cached object the key no longer matches, and the recording's last call before `post_init` is that descriptor being given the captain's default ([Reading and setting related objects](related-objects.md)). The name and the tonnage leave no line in the recording: setting a plain attribute runs nothing of Django's.

Two kinds of field are passed over: one with no column, such as a primary key made of several columns, and a generated one, whose value only the database can supply. A keyword argument that the loop over the fields did not take is set as an attribute afterwards, if it names a property of the class or something `Options.get_field` finds: a field the loop passed over, or a relation that points at the model. One that names neither raises `TypeError`. The last statement sends `post_init` with the finished instance.

With positional arguments the values are paired with fields by position and set under the attnames, with no lookups. When there are no keyword arguments at all they are paired with `Options.concrete_fields`, the fields that have a column, which is exactly the list a row's values correspond to. When there are keyword arguments too, they are paired with `Options.fields`, and a field given by position and again by its name is an error. Fields the positional values did not reach are then filled as above.

```text recording=models
Named(name='Nowhere')  ->  raises TypeError: Abstract models cannot be instantiated.
Ship(1, 'Petrel', 480, 1, None, 6)  ->  raises IndexError: Number of args exceeds number of fields
Ship(1, 'Petrel', name='Gull')  ->  raises TypeError: Ship() got both positional and keyword arguments for field 'name'.
Ship(name='Heron', mast=2)  ->  raises TypeError: Ship() got unexpected keyword arguments: 'mast'
```

The first line is a refusal that comes before all of this: an abstract model cannot be instantiated. The second is more positional values than the model has concrete fields, the third a field given both ways, and the fourth a keyword that names nothing the class has.

Both signals are sent by every call of `__init__`, whether or not anything listens, including the call made for each row of a query. A receiver of either is therefore called once per row fetched for that model; `ImageField` connects one to `post_init` for each model that uses it with dimension fields (`django/db/models/fields/files.py:ImageField.contribute_to_class`) ([File fields](files.md)).

## What an instance holds

A new instance holds nothing of Django's but those values and its state. This is the Ship just made:

```text recording=models
What the new Ship holds in its __dict__
    _state: a ModelState
    id: None
    name: 'Heron'
    tonnage: 300
    home_id: 1
    captain_id: None
    and its _state: adding=True, db='default', fields_cache={'home': <Port: Bergen>}
```

The keys are attnames, so the two relations are there as `"home_id"` and `"captain_id"`, each holding a key or `None`. The port that was passed in is not in the `__dict__`. It is in the state, in a dictionary of related objects that the field's descriptor reads.

A field's value has no other storage: it is the entry under the field's attname, and assigning to the attribute replaces the entry. For a field whose descriptor is a plain `DeferredAttribute`, nothing of Django's runs when that happens, because that class has no `__set__` (`django/db/models/query_utils.py:DeferredAttribute`). Nothing records what has changed since the instance was loaded, so a save does not single out what changed; which columns it writes is told in [Saving an instance](saving.md).

## The state object

`Model._state` is a small object of the class `ModelState` (`django/db/models/base.py:ModelState`). What it holds:

| attribute | what it says | it starts as | who changes it |
|---|---|---|---|
| `ModelState.adding` | the instance is new and has not been saved | `True` | `Model.from_db` and `Model.save_base` set it false, and `QuerySet.bulk_create` for an object that had its key or whose row the insert returned; a parent built from a child through its link is given the child's |
| `ModelState.db` | the alias of the database the instance was loaded from, was saved to, or would be written to | `None` | `Model.from_db`, `Model.save_base`, `Model.refresh_from_db`, `QuerySet.bulk_create` for the same objects, and a relation descriptor when an object is assigned and one of the two has no alias; a parent built from a child is given the child's |
| `ModelState.fields_cache` | related objects already at hand, by the name of the relation | an empty dictionary, made at the first read | the relation descriptors, a queryset that selects or prefetches related objects, `Model.refresh_from_db` and a save |
| `ModelState.fetch_mode` | how a missing value is to be fetched | `FETCH_ONE`, set at the first read | `Model.from_db`, when it is given one, and `QuerySet.create`; a parent built from a child is given the child's |
| `ModelState.peers` | weak references to the instances that came out of the same query, this one among them | an empty tuple | the queryset's iterable, under a fetch mode that tracks them |

*What an instance's state holds. The first, second and fifth are plain class attributes until something assigns them on the instance; the third and fourth are descriptors that create the value the first time it is read. The last column names the code this chapter passes through.*

The last two rows belong to the fetch modes, which decide how a value that is missing from an instance gets fetched. They come up again below, with deferred fields, and are told in full in [Reading and setting related objects](related-objects.md).

The recording shows the first two for a Ship just made with a port, the alias alone for the same Ship made without one, and both for a Ship made from a row:

```text recording=models
heron.pk, heron.id, heron._state.adding, heron._state.db  ->  (None, None, True, 'default')
Ship(name='Heron', tonnage=300)._state.db  ->  None
loaded.pk, loaded._state.adding, loaded._state.db  ->  (1, False, 'default')
```

The new Ship already has an alias, though it has touched no database: setting its port through the descriptor asked the database router where a Ship would be written, and noted the answer (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__set__`). The second line is the same Ship made without a port, and it has none.

`adding` is read where Django has to tell a new object from a stored one. The unique checks of validation read it to decide whether a row with the same values may be this instance's own ([Validating an instance](validation.md)). The `add` of the manager at the far end of a foreign key reads it, unless it is called with `bulk=False`, to refuse an object that has not been saved. And a save reads it to decide whether to try an `"UPDATE"` first.

> **A trap.** The comment on `ModelState.adding` in the source says that it has no effect on the actual save. The save does read it, to decide whether to insert at once (`django/db/models/base.py:Model._save_table`) ([Saving an instance](saving.md), [Validating an instance](validation.md)).

## From a row: `Model.from_db`

A queryset does not call the class directly for each row. It calls `Model.from_db`, a class method, and so a place where a model can step in for every instance a queryset makes from a row (`django/db/models/base.py:Model.from_db`).

```text recording=models
Ship.objects.get(name='Petrel'): a row becomes an instance
    SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Petrel',)
    Model.from_db('default', ['id', 'name', 'tonnage', 'home_id', 'captain_id'], (1, 'Petrel', 480, 1, None), fetch_mode=FETCH_ONE)  (Ship)
      Model.__init__(1, 'Petrel', 480, 1, None)  (a new Ship)
        signal pre_init, sender Ship, args=(1, 'Petrel', 480, 1, None), kwargs with the keys []
        ForeignKeyDeferredAttribute.__set__(<Ship: Petrel>, 1)  (Ship.home)
        ForeignKeyDeferredAttribute.__set__(<Ship: Petrel>, None)  (Ship.captain)
        signal post_init, sender Ship
```

It is given the database's alias, the attnames of the columns that were fetched, and the row's values, which it takes to be in the order of the model's concrete fields. It calls the class with the values positionally, which takes the fast path of `__init__`, and then sets the state: `adding` false, `db` the alias, and the fetch mode when one was passed. The signals are sent as for any instance.

> **Changed in 6.1.** `from_db` takes `fetch_mode=`. A model that overrides the method without accepting it still works for now: the queryset calls such an override without the argument and warns that this is deprecated (`django/db/models/query.py:_get_from_db`).

Who calls `from_db`, and with which columns, belongs to [QuerySets](../querysets.md).

## A deferred field is a missing key

A deferred field is, on the instance, nothing more than a key that is missing. One cause is a query that fetches fewer columns than the model has. `Model.from_db` is then handed fewer values than there are concrete fields, and makes up the difference itself: for each field whose attname is not among those fetched it puts a marker, `DEFERRED`, in that position, and `Model.__init__` sets nothing for a value that is the marker. Another is a generated field: `Model.__init__` passes it over, so on an instance made from keyword arguments its key is missing too.

```text recording=models
Ship.objects.only('name').get(name='Petrel'): a row with two of the model's five columns
    SQL SELECT "fleet_ship"."id", "fleet_ship"."name" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Petrel',)
    Model.from_db('default', ['id', 'name'], (1, 'Petrel'), fetch_mode=FETCH_ONE)  (Ship)
      Model.__init__(1, 'Petrel', <Deferred field>, <Deferred field>, <Deferred field>)  (a new Ship)
```

```text recording=models
What the Ship made from two columns holds in its __dict__
    _state: a ModelState
    id: 1
    name: 'Petrel'
    and its _state: adding=False, db='default', fields_cache={}
```

That is the whole representation. No list of deferred fields is kept: `Model.get_deferred_fields` works one out each time, as the attnames of the concrete fields that have no entry in the `__dict__` (`django/db/models/base.py:Model.get_deferred_fields`).

Reading such an attribute works by ordinary Python rules. The instance has no entry of that name, so the lookup goes to the class, and finds the `DeferredAttribute` that the field set there when the class was made. A descriptor without a `__set__` is consulted only in that case, which is why it costs nothing for a field that is loaded. A foreign key's attname is an exception, and so is a file field's: each has a descriptor with a `__set__`, so Python goes to it at every read. The foreign key's hands back the entry when there is one.

```text recording=models
slim.tonnage is read
  DeferredAttribute.__get__(a Ship)  (Ship.tonnage)
    DeferredAttribute._check_parent_chain  ->  None
    FetchOne.fetch(a DeferredAttribute for Ship.tonnage, <Ship: Petrel>)
      DeferredAttribute.fetch_one(a Ship)
        Model.refresh_from_db(fields=['tonnage'])  (a Ship)
          SQL SELECT "fleet_ship"."id", "fleet_ship"."tonnage" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 21 with params (1,)
          Model.from_db('default', ['id', 'tonnage'], (1, 480), fetch_mode=FETCH_ONE)  (Ship)
            Model.__init__(1, <Deferred field>, 480, <Deferred field>, <Deferred field>)  (a new Ship)
    -> 480
slim.tonnage is read again
```

`DeferredAttribute.__get__` first looks for the value somewhere it may already be: a child model that deferred its parent's primary key has the same value in its link to the parent. Failing that, it refuses an instance with no primary key, which has no row to fetch from, and hands the fetch to the instance's fetch mode. The default mode fetches for this instance alone, by calling `Model.refresh_from_db` for the one field; the value arrives in the `__dict__`, and the second read in the recording finds it there and calls nothing (`django/db/models/query_utils.py:DeferredAttribute.__get__`). Under `FETCH_PEERS` the same read, when other instances of the same query are still alive, fetches the field for all of them through `QuerySet.in_bulk`, and under `FETCH_RAISE` it raises ([Reading and setting related objects](related-objects.md) has the fetch modes).

Assigning to a deferred attribute puts a value under the key like any assignment. The field is then no longer deferred, and nothing was fetched.

## `Model.refresh_from_db`

`Model.refresh_from_db` reloads an instance in place. Unless it is handed a queryset as `from_queryset=`, it builds one on the model's base manager, with the instance as a hint for the router. It filters that to the instance's primary key, fetches one row as a second instance, and copies values across (`django/db/models/base.py:Model.refresh_from_db`).

Which fields it fetches depends on how it is called. Given `fields=`, it fetches those. Given nothing, it fetches every field the instance has loaded, and leaves the deferred ones deferred, as the last lines of the recording show:

```text recording=models
slim.refresh_from_db() is called
  Model.refresh_from_db()  (a Ship)
    SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 21 with params (1,)
    Model.from_db('default', ['id', 'name', 'tonnage'], (1, 'Petrel', 480), fetch_mode=FETCH_ONE)  (Ship)
      Model.__init__(1, 'Petrel', 480, <Deferred field>, <Deferred field>)  (a new Ship)
sorted(slim.get_deferred_fields())  ->  ['captain_id', 'home_id']
```

Copying the values is not all it does, because an instance can hold more than values. For each relation field reloaded, the related object kept in the state is replaced by the one the fresh instance has, or dropped. On a full refresh, or for a relation named in `fields=`, the cache of a relation that points at the instance is dropped too. The results of a `prefetch_related`, which an instance keeps in a dictionary of its own, are emptied by a full refresh; a name in `fields=` that is one of them drops only that one, and is not fetched. Finally the state's alias becomes that of the database the row was read from.

## The primary key, equality and hashing

`Model.pk` is a property, the same on every model whose key is one field, whatever that field is called; a key of several columns sets a descriptor of its own on the class under that name ([The field classes](field-types.md)). Reading the property returns the attribute under the attname of `Options.pk`. Writing it sets that attribute. Where the model has a link to a parent that is not its own key, the attribute that link points at is set as well; for a child whose link is its key, as Officer's is, nothing more is set, so writing `pk` on an Officer leaves the `"id"` it inherits as it was (`django/db/models/base.py:Model._get_pk_val`, `django/db/models/base.py:Model._set_pk_val`).

Whether a key counts as set is asked through `Model._is_pk_set`. `None` is not set. Nor is the placeholder that stands in for a default the database will supply. A key of several columns is a tuple, and is set only when every part is.

Two instances are equal when they are of the same concrete model and have the same key. An instance with no key is equal to itself and nothing else, and cannot be hashed (`django/db/models/base.py:Model.__eq__`, `django/db/models/base.py:Model.__hash__`):

```text recording=models
loaded == Ship.objects.get(name='Petrel'), loaded is Ship.objects.get(name='Petrel')  ->  (True, False)
hash(loaded) == hash(loaded.pk)  ->  True
heron == Ship(name='Heron', tonnage=300, home=bergen), heron == heron  ->  (False, True)
hash(heron)  ->  raises TypeError: Model instances without primary key value are unhashable
Veteran.objects.get(name='Ada') == Sailor.objects.get(name='Ada')  ->  True
Officer.objects.get(name='Cora') == Sailor.objects.get(name='Cora')  ->  False
Officer.objects.get(name='Cora').pk == Sailor.objects.get(name='Cora').pk  ->  True
```

The last three lines turn on the phrase "same concrete model". A proxy shares its model's rows and is equal to the instance it stands beside. A child with a table of its own is a different concrete model from its parent, so the Officer and the Sailor that share a row and a key are not equal ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)). The statements those questions sent are left out of the quote.

Unless a model defines `__str__`, an instance prints as its class's name, the word object and its key (`django/db/models/base.py:Model.__str__`).

## Pickling

An instance is pickled as its `__dict__`, with a copy of the state and the version of Django added. It is not unpickled through `__init__`. `Model.__reduce__` names a function, `model_unpickle`, and the model's app label and name; on loading, that function asks the registry for the class, makes an empty object of it with `__new__`, and `Model.__setstate__` fills its `__dict__` (`django/db/models/base.py:Model.__reduce__`, `django/db/models/base.py:model_unpickle`).

```text recording=models
loaded.__reduce__()[0].__name__, loaded.__reduce__()[1]  ->  ('model_unpickle', (('fleet', 'Ship'),))
sorted(loaded.__reduce__()[2])  ->  ['_django_version', '_state', 'captain_id', 'home_id', 'id', 'name', 'tonnage']
pickle.loads(pickle.dumps(loaded)) == loaded, pickle.loads(pickle.dumps(loaded)).name  ->  (True, 'Petrel')
```

So neither signal is sent for an unpickled instance, and a deferred field stays deferred, since a key missing from the pickled dictionary is missing from the new one. `__setstate__` warns when the version recorded in the pickle is not the running one, or is absent. Two things are adjusted on the way out: a `memoryview`, which cannot be pickled, is stored as bytes and turned back on loading, and the state leaves out its peers, which are weak references.

## What else every instance has

`Model.serializable_value` returns the value under a field's attname given the field's name, so a foreign key yields its key and not the object; for a name that is no field it returns the attribute.

The methods that write to the database, `save`, `delete` and their relatives, carry an attribute `"alters_data"`. The template engine will not call a method so marked (`django/template/base.py:Variable._resolve_lookup`). `Model` inherits from `AltersData`, whose one job is to copy that mark onto a subclass's override of a marked method, so that a model's own `save` is protected as well (`django/db/models/utils.py:AltersData`).

Each of `save`, `delete` and `refresh_from_db` has an asynchronous twin, `Model.asave`, `Model.adelete` and `Model.arefresh_from_db`. Each twin awaits the synchronous method wrapped in `sync_to_async`, and so runs it in a thread ([Sync and async in one chain](../handlers/async.md)).
