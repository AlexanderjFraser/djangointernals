---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The options: what a model keeps as `_meta`

A model class keeps its description in one object, a `django.db.models.options.Options`, under the name `_meta`. The object stores what the class's `Meta` said and the fields and managers that were added to the class, and from those, and from the same in the options of other models, it derives the other lists of fields that the rest of Django reads, each the first time it is asked for: `Options.fields`, `Options.concrete_fields`, `Options.related_objects`, `Options.get_fields`.

Code that deals with models in general has no class body to read. It has a model class in hand and questions to put to it: which fields it has and which of them have a column, what its table is called, which field is its key, which other models point at it. All of them are put to one object, the class's options (`django/db/models/options.py:Options`).

What the object stores is small: the settings the `Meta` gave, or their defaults; four lists that grow as the class is made, of the fields added to this class, its many-to-many fields, its fields of a kind called private, and its managers; and a few things set on it as the class is made, its parents and its primary key among them. What it derives it keeps, and keeping is the delicate part, because a model's description is not finished when its class statement ends: a field can still be added to the class, and a relation to the model may be declared by another class, whose module may not have been imported yet. So the object knows exactly which of its attributes are kept answers, and a field or a manager added to a class throws kept answers away: in that class's options, and for a relation also in the options of the class it points at, where the relation was given that class and not its name.

Port, one of the models of the fleet ([Models and fields](../models.md)), adds a field, `"country"`, to the field `"name"` and the ordering that it inherits from an abstract base, Named. Its options are installed first, are told of each field as it is added, are asked for the primary key that no field has claimed, and are told last of the manager. These are the calls into them as the class statement ran, with the calls that led there. The making of Port's exception classes and descriptors, the `class_prepared` signal and the registry's look for waiting functions are left out.

```text recording=models
ModelBase.__new__('Port', (Named,))
  ModelBase.add_to_class(Port, '_meta', an Options)
    Options.contribute_to_class(Port, '_meta')
  ModelBase.add_to_class(Port, 'country', a CharField)
    Field.contribute_to_class(Port, 'country')  (a CharField)
      Options.add_field(Port.country)
  Field.__deepcopy__  (a copy of Named.name)
  ModelBase.add_to_class(Port, 'name', a CharField)
    Field.contribute_to_class(Port, 'name')  (a CharField)
      Options.add_field(Port.name)
  ModelBase._prepare(Port)
    Options._prepare(Port)
      Options._get_default_pk_class  ->  the class BigAutoField
      ModelBase.add_to_class(Port, 'id', a BigAutoField)
        AutoFieldMixin.contribute_to_class(Port, 'id')  (a BigAutoField)
          Field.contribute_to_class(Port, 'id')  (a BigAutoField)
            Options.add_field(Port.id)
              Options.setup_pk(Port.id)  ->  Options.pk is Port.id
    ModelBase.add_to_class(Port, 'objects', a Manager)
      BaseManager.contribute_to_class(Port, 'objects')  (a Manager)
        Options.add_manager(a Manager)
  Apps.register_model('fleet', Port)
    Apps.clear_cache
```

## Made first, and bound to the class

`ModelBase.__new__` makes a model's `Options` and adds it to the class as `_meta`, before any field ([`ModelBase`: a class statement becomes a model](metaclass.md)). `Options.__init__` only lays the object out: each setting at its default, the `Meta` kept aside as it was handed over, four empty lists for what will be added to the class, an empty dictionary for the lists that will be derived, and the app registry the model will belong to, which is the global one unless the `Meta` names another (`django/db/models/options.py:Options.__init__`).

`Options.contribute_to_class` does the binding. It sets the object on the class as `_meta` and the class on the object as `Options.model`, and then fills the object in, beginning with three names taken from the class's name (`django/db/models/options.py:Options.contribute_to_class`).

```text recording=models
Ship._meta.app_label, Ship._meta.object_name, Ship._meta.model_name  ->  ('fleet', 'Ship', 'ship')
Ship._meta.label, Ship._meta.label_lower, Ship._meta.db_table  ->  ('fleet.Ship', 'fleet.ship', 'fleet_ship')
Ship._meta.verbose_name, str(Ship._meta.verbose_name_plural)  ->  ('ship', 'ships')
```

`Options.object_name` is the class's `__name__`, `Options.model_name` is the same in lower case, and `Options.verbose_name` is the class's name passed through `camel_case_to_spaces`, which for the class LogEntry gives log entry (`django/utils/text.py:camel_case_to_spaces`). A `Meta` can replace the third and not the other two, which are not among the names it may set.

`Options.label` and `Options.label_lower` are properties that join the app label to each of the first two names with a dot. The second is what `str` gives for the options, and its two halves are the key the registry files the class under (`django/apps/registry.py:Apps.register_model`). Where the `Meta` gives no plural, `Options.verbose_name_plural` is the verbose name with an s after it, as a lazy string that is joined only when it is read (`django/utils/text.py:format_lazy`).

## What it takes from `Meta`

The names a `Meta` may set are listed in the tuple `DEFAULT_NAMES`, and `Options.contribute_to_class` goes through that tuple looking for each name in two places (`django/db/models/options.py:DEFAULT_NAMES`, `django/db/models/options.py:Options.contribute_to_class`). The first is the `Meta`'s own `__dict__`. The second, tried when the first has nothing, is the `Meta` as a whole, by ordinary attribute lookup, which finds a name that the `Meta` only inherits from a base of its own. A value found in either place is set on the options, over the default.

The fleet's models show both. The `Meta` of Named sets `"abstract"` and `"ordering"`. That of Ship inherits from it and sets `"constraints"` and `"indexes"` itself, so Ship's ordering is found in the second place. Port writes no `Meta`, and its options are handed the one it inherits from Named. Voyage has none, and keeps the default.

```text recording=models
Named._meta.ordering, Port._meta.ordering, Ship._meta.ordering, Voyage._meta.ordering  ->  (['name'], ['name'], ['name'], [])
sorted(Ship._meta.original_attrs)  ->  ['abstract', 'constraints', 'indexes', 'ordering']
sorted(Port._meta.original_attrs)  ->  ['abstract', 'ordering']
```

The first place also catches mistakes. The method works on a copy of the `Meta`'s `__dict__`, less the names that begin with an underscore, and takes each name out of the copy as it uses it. Whatever is left when the tuple has been gone through is a name the options do not know, and the method raises `TypeError` with the names in its message. An unknown name that the `Meta` only inherits is never looked at, and raises nothing.

Each value taken is recorded a second time, in the dictionary `Options.original_attrs`, under its name. The options go on to change some of what they were given: the names of constraints and indexes are filled in, `"unique_together"` is put into one form, an `"order_with_respect_to"` that was the name of a field becomes the field. The dictionary keeps what the `Meta` said. Its reader is the code that describes a model for a migration, which goes through `DEFAULT_NAMES` and takes up only the options this dictionary has an entry for, so that a migration carries what a model's `Meta` set and none of the defaults (`django/db/migrations/state.py:ModelState.from_model`) ([Migrations](../migrations.md)). The `"abstract"` in both lists above comes from Named, whose `Meta` still has the attribute, set to false by the metaclass ([`ModelBase`: a class statement becomes a model](metaclass.md)).

## The table's name

`Options.contribute_to_class` settles the table's name once the `Meta` has been read (`django/db/models/options.py:Options.contribute_to_class`). A `Meta` that sets `"db_table"` has its name used as it was written. Otherwise `Options.db_table` is the app label and the model name joined by an underscore, cut to the longest name that the default database allows, whichever database the model's rows will be kept in (`django/db/backends/base/operations.py:BaseDatabaseOperations.max_name_length`). The cut keeps the front of the name and puts four characters of a digest of the whole name in place of the rest, which the function's docstring calls a repeatable mangled version (`django/db/backends/utils.py:truncate_name`). A proxy, a second class over another model's rows ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)), keeps neither name: `Options.setup_proxy`, which the metaclass calls afterwards, gives it the table of the model it stands for (`django/db/models/options.py:Options.setup_proxy`).

## Names of constraints and indexes

The name of a constraint or an index may contain `"%(app_label)s"` and `"%(class)s"`. For a class that is not abstract, `Options.contribute_to_class` passes the `Meta`'s constraints and indexes through `Options._format_names`, which fills in the app label and the model name, both in lower case (`django/db/models/options.py:Options._format_names`). The first constraint of Ship was written with the name `"%(class)s_has_tonnage"`:

```text recording=models
[c.name for c in Ship._meta.constraints]  ->  ['ship_has_tonnage', 'one_name_to_a_port']
```

Django's documentation says what the placeholders are for: a constraint written on an abstract base is inherited by each subclass with exactly the same values, the name among them, and a constraint's name has to be unique (`docs/ref/models/constraints.txt`).

Each object is cloned before its name is filled in, and the options are given the clones in place of the `Meta`'s objects (`django/db/models/constraints.py:BaseConstraint.clone`, `django/db/models/indexes.py:Index.clone`). A constraint in the `Meta` of an abstract base is a single object, read by every class that inherits that `Meta`. With a clone, each class has an object of its own carrying its own name, and the `Meta` goes on holding the placeholder for the next class. An abstract class is passed over by `_format_names`, and the names in its options keep their placeholders.

An index declared without a name keeps its empty name here. On a class that is not abstract it is named at the end of the class statement, when the fields it names are on the class (`django/db/models/base.py:ModelBase._prepare`) ([Constraints and indexes](constraints.md)).

## The lists it stores and the lists it derives

Fields reach a model's `Options` one at a time. `Field.contribute_to_class` hands the field to `Options.add_field`, which puts it in one of three lists (`django/db/models/fields/__init__.py:Field.contribute_to_class`, `django/db/models/options.py:Options.add_field`). A field added as private goes at the end of `Options.private_fields`. A many-to-many field goes into `Options.local_many_to_many`. Any other goes into `Options.local_fields`, and is then offered to `Options.setup_pk` in case it is the primary key. A manager reports in the same way to `Options.add_manager`, which appends it to `Options.local_managers` ([Managers](managers.md)).

A **private field** is a field of which each subclass is to have a copy of its own, with that subclass as the copy's model; the source's example is `GenericForeignKey`. It is added by `Field.contribute_to_class` called with `private_only=True`, which that method hands to `Options.add_field` as `private=True`. A subclass that does not override the field is given its copy even where the parent has a table of its own and so shares its ordinary fields with its children (`django/db/models/base.py:ModelBase.__new__`). The two fields in Django that are added so are `GenericForeignKey` and `GenericRelation` ([Content types, static files and the other contrib apps](../contrib.md)).

Those four are the stored lists, and each is **local**: it holds what was added to this very class. The other lists are derived from them and from the same lists of other models. A **forward** field is one that the model or one of its parents has. The **reverse** side is the relations that models have to the model, each stood for by its **rel**, the object a relation field carries as `Field.remote_field` ([Relations: a field, its rel and the class at the other end](relations.md)).

| list | what it holds | stored or derived |
|---|---|---|
| `Options.local_fields` | the fields added to this class that are neither many-to-many nor private, sorted by creation counter | stored, by `add_field` |
| `Options.local_many_to_many` | the many-to-many fields added to this class, sorted by creation counter | stored, by `add_field` |
| `Options.private_fields` | the fields added to this class as private, in the order they were added | stored, by `add_field` |
| `Options.local_managers` | the managers added to this class, in the order they were added | stored, by `add_manager` |
| `Options.fields` | the forward fields of the model and its parents, less the many-to-many fields and the two generic ones | derived, from `Options._get_fields(reverse=False)` |
| `Options.concrete_fields` | the members of `fields` that have a column | derived, from `fields` |
| `Options.local_concrete_fields` | the members of `local_fields` that have a column | derived, from `local_fields` |
| `Options.many_to_many` | the many-to-many fields of the model and its parents | derived, from `_get_fields(reverse=False)` |
| `Options.related_objects` | the rels of the relations that point at the model or at a parent; a rel whose `"related_name"` ends in `"+"` only if its field is many-to-many | derived, from `_get_fields(forward=False, reverse=True, include_hidden=True)` |
| `Options.get_fields` | both sides: the rels, the fields, the many-to-many fields and the private ones, with those of parents | derived, from `_get_fields` with the caller's two arguments, `include_parents=False` handed on as `PROXY_PARENTS` |

*The lists of fields and managers that a model's options give. The first four are added to as the class is made; each of the others is computed the first time it is asked for, and kept.*

In the recorded lines, names(…) stands for the name of each member of a list, in the list's order.

```text recording=models
names(Ship._meta.local_fields)  ->  [id, name, tonnage, home, captain]
names(Ship._meta.local_many_to_many), names(Ship._meta.private_fields)  ->  ([], [])
...
names(Voyage._meta.fields), names(Voyage._meta.many_to_many)  ->  ([id, ship, sailed], [calls])
...
names(Officer._meta.local_fields)  ->  [sailor_ptr, rank]
names(Officer._meta.fields)  ->  [id, name, ship, signed_on, sailor_ptr, rank]
names(Officer._meta.get_fields(include_parents=False))  ->  [sailor_ptr, rank]
names(Veteran._meta.local_fields), names(Veteran._meta.fields)  ->  ([], [id, name, ship, signed_on])
```

The `local_fields` of Ship include `"name"`, because the copy of Named's field was added to Ship itself. Those of Officer have nothing of Sailor's: a parent with a table keeps its fields, and they reach Officer through `fields`, the parent's first. The proxy Veteran has no local fields at all ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)).

`local_fields` is not in the order the fields were added: `add_field` inserts each field at its sorted place, and fields sort by `Field.creation_counter`, a number each field takes as it is constructed (`django/db/models/fields/__init__.py:Field.__lt__`) ([A field: the base class](fields.md)). `concrete_fields` takes that order over, and a row fetched by a query is turned into an instance by handing its values to `Model.from_db` in the order of `concrete_fields` ([An instance and its state](instances.md)).

Each derived list except `get_fields`, which is a method, is a `cached_property`: a method that runs at the first read, and whose result is then stored in the object's own `__dict__` under the method's name, where later reads find it and call nothing (`django/utils/functional.py:cached_property`).

`fields` leaves out three kinds of forward field: a many-to-many relation; a relation that is one-to-many, which among Django's fields is `GenericRelation`; and a many-to-one relation with no model at its other end, which is `GenericForeignKey` (`django/db/models/options.py:Options.fields`). Any other field without a column is in `fields` all the same, and is what `concrete_fields` then leaves out.

## `_get_fields`: the method that assembles a list

`Options._get_fields` is the method from which each derived list of the table above is cut, except `Options.local_concrete_fields`, which is cut from `Options.local_fields`. It assembles a list from the stored lists of this model, of its parents and of the models that point at it, according to five arguments (`django/db/models/options.py:Options._get_fields`):

- `forward=True` includes the model's own fields: `Options.local_fields`, then `Options.local_many_to_many`, then `Options.private_fields`.
- `reverse=True` includes the rels of the relations that point at the model. A proxy adds none here: it gets them from the model it stands for, as a parent's.
- `include_parents=True` includes what each parent's own `_get_fields` gives for the same arguments. It has a third value besides true and false, the marker `PROXY_PARENTS`.
- `include_hidden=True` includes the rels that are hidden, those of relations whose `"related_name"` ends in `"+"`.
- `topmost_call=True` marks the call a caller made, as against the calls the method makes on parents, which pass false. Private fields are added at the topmost call only, since each class has copies of its own.

All but the fourth are true unless given. The list is put together in a fixed order: what the parents give, then this model's rels, then its own fields. Two things are dropped from what a parent gives. One is an object already taken from another parent, which happens where two parents share an ancestor. The other is the rel of a child's link to that parent, which only a proxy of the parent is handed. Sailor's list has the rel of Officer's link to it, `"officer"`, and Officer's own list has not (`"licence"` is the rel of a foreign key in Licence, a model of the office):

```text recording=models
names(Sailor._meta.get_fields())  ->  [command, officer, licence, id, name, ship, signed_on, pilots_into]
...
names(Officer._meta.get_fields())  ->  [command, licence, id, name, ship, signed_on, pilots_into, sailor_ptr, rank]
```

Each answer is kept in `Options._get_fields_cache`, a dictionary whose key is the five arguments together, and is returned from there when the same five are asked again. So there are two layers of keeping: `Options.fields` is a kept selection from a list that `_get_fields` has kept as well.

What comes back is the kept object itself, and every caller with the same arguments gets that same object, so that a caller who sorted it or appended to it would change it for all the others. The method returns an `ImmutableList`, a tuple on which each method that would change a list raises `AttributeError`, with a message that names the list and says to make a copy first (`django/utils/datastructures.py:ImmutableList`, `django/db/models/options.py:make_immutable_fields_list`). The derived lists of the table above are wrapped in the same way. The four stored lists are plain lists.

### What hidden means

`include_hidden=True` concerns the reverse side only. A rel is **hidden** when the `"related_name"` of its relation ends in `"+"`, which is how a relation says that it wants no attribute on the class it points at (`django/db/models/fields/reverse_related.py:ForeignObjectRel.hidden`). `_get_fields` leaves such a rel out unless it is asked for, and no forward field is left out as hidden. The two foreign keys of the model that Django makes for the table of a many-to-many relation are given names of that kind ([Many-to-many relations](many-to-many.md)). Voyage has such a relation to Port, `"calls"`, and the rel of the key that its automatic model, Voyage_calls, has to Port is in Port's list only on request. `Options.related_objects` leaves a hidden rel out unless its field is many-to-many, so that key's rel is not in it either (`django/db/models/options.py:Options.related_objects`). In Port's lists `"berth"`, like `"licence"`, is the rel of a foreign key in a model of the office:

```text recording=models
names(Port._meta.get_fields())  ->  [ships, voyage, pilots, licence, berth, id, name, country]
names(Port._meta.get_fields(include_hidden=True))  ->  [ships, Voyage_calls+, voyage, pilots, licence, berth, id, name, country]
...
names(Port._meta.related_objects)  ->  [ships, voyage, pilots, licence, berth]
```

The docstring of `Options.get_fields` describes a hidden name as one that starts with a `"+"`. The test is on the last character.

### `get_fields`, the public face

`Options.get_fields` passes two of the five arguments on, the ones about parents and about hidden rels, and leaves both sides in. It turns `include_parents=False` into `PROXY_PARENTS`, under which `_get_fields` still goes up through the parents, but passes over any parent whose concrete model is not this model's own (`django/db/models/options.py:Options.get_fields`). A model's **concrete model** is the model itself, or for a proxy that of the model it stands for ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)). A parent with a table is a different concrete model, which is why Officer was given only its two local fields above. The model a proxy stands for is the same concrete model, and Veteran, whose own lists of fields are empty, is given everything of Sailor's:

```text recording=models
names(Veteran._meta.get_fields(include_parents=False))  ->  [command, officer, licence, id, name, ship, signed_on, pilots_into]
```

## The reverse side: `_relation_tree`

`Options._relation_tree` is, for one model, the list of the fields that are relations to it, on that model or on another in the registry's list (`django/db/models/options.py:Options._relation_tree`). The rels in a model's lists are made from it, and it cannot be had from the model's own options: nothing in the options of Ship says that Sailor has a foreign key to it. That fact is in Sailor's `Options.local_fields`. To list the relations that point at one model, something has to go through the fields of every model and pick out the ones aimed at it, and the tree is the kept result of that search. As `Options._get_fields` builds a list it turns each field of the tree into its rel, the object the field carries as `Field.remote_field` (`django/db/models/fields/__init__.py:Field.__init__`).

The property's body is one call, to `Options._populate_directed_relation_graph`, and that method does not work on one model (`django/db/models/options.py:Options._populate_directed_relation_graph`). It asks the registry for its list of models, the automatically made ones included. From each it takes the model's own forward fields that are relations to a class, and sorts them into a dictionary by the model they point at. Then it goes through the models again and writes each one's list straight into the `__dict__` of that model's options, under `"_relation_tree"`, which is exactly where the property would have stored a result of its own. So the first read of the tree on any model fills it on every model in the registry's list, and each later read, on any of them, finds a value already there and computes nothing. The method's docstring gives the reason: the search is very expensive, looking up every field of every model in every app, and its result is wanted often.

A relation is filed under the concrete model of its target, and each model is given the list of its own concrete model. A relation to a proxy is therefore found on the model the proxy stands for, and the proxy has the same list ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)).

The search is right only when every model has been imported: a model whose module has not run yet has no fields to contribute. The code does not make a short list. `Apps.get_models`, which the search begins with, raises `AppRegistryNotReady` until the registry has imported the models of every application (`django/apps/registry.py:Apps.get_models`) ([Settings, apps and startup](../startup.md)). So `Options.related_objects`, `Options.get_fields` with its defaults, and every other question that takes in the reverse side cannot be worked out while models are still being imported. The forward lists can be: `ModelBase._prepare` itself reads `Options.fields`, to write the docstring of a class that has none, before the class is even registered (`django/db/models/base.py:ModelBase._prepare`).

## What throws the kept answers away

A model's `Options` keeps the lists it derives, and knows which of its attributes are such kept answers from two sets of names on the class (`django/db/models/options.py:Options`). Between them, `Options.FORWARD_PROPERTIES` and `Options.REVERSE_PROPERTIES` name every `cached_property` the class declares. The reverse set has the tree and the two answers built from it through `Options._get_fields`, `Options.related_objects` and `Options.fields_map`. The forward set has all the others, the managers among them ([Managers](managers.md)). One of its names, `Options._reverse_one_to_one_field_names`, is made from `related_objects`, and a call that expires the reverse side alone leaves it (`django/db/models/options.py:Options._reverse_one_to_one_field_names`). Another, `Options._property_names`, is the names that are properties on the class, which `Model.__init__` consults for a keyword argument that names no field (`django/db/models/options.py:Options._property_names`).

`Options._expire_cache` takes two arguments, both true unless given. With `forward=True` it deletes from the object's `__dict__` each name of the forward set that is there. With `reverse=True`, and for a model that is not abstract, it does the same for the reverse set. And whatever its arguments, it replaces `Options._get_fields_cache` with an empty dictionary (`django/db/models/options.py:Options._expire_cache`).

Three methods call it. `Options.add_field` expires the forward answers of its own class for a field that is not a relation to a model. For a relation it expires the reverse answers of the class the relation points at, where the relation was given that class and not its name, and then both sides of its own class. `Options.add_manager` expires both sides of its own class. And the registry's `Apps.clear_cache`, when the registry is ready, expires both sides for the models of each installed application, the automatically made ones included and not the ones a setting has swapped for another model. In each case the `_get_fields_cache` of the options concerned is emptied whole, and the reverse answers of an abstract class are left in place.

`Apps.clear_cache`, which `Apps.register_model` ends with, reaches into the options only once the registry is ready, and not while the applications are still being loaded (`django/apps/registry.py:Apps.clear_cache`). At start-up, while the models are imported for the first time, no options hold a reverse answer for it to delete: none can be made until every model is loaded.

The office's logbooks show the keeping and the expiring. Each line that begins cached(…) says which names of the two sets a model's options hold at that moment, and how many lists are in its `_get_fields_cache`.

```python
# harbour/office/models.py
class Logbook(models.Model):
    title = models.CharField(max_length=60)


class LogEntry(models.Model):
    book = models.ForeignKey(Logbook, on_delete=models.DB_CASCADE)
    line = models.CharField(max_length=200)
```

```text recording=models
cached(Logbook)  ->  [] and 0 in _get_fields_cache
cached(LogEntry)  ->  [swapped] and 0 in _get_fields_cache
names(Logbook._meta.fields)  ->  [id, title]
cached(Logbook)  ->  [fields] and 1 in _get_fields_cache
names(Logbook._meta.related_objects)  ->  [logentry]
cached(Logbook)  ->  [_relation_tree, fields, related_objects, swapped] and 3 in _get_fields_cache
cached(LogEntry)  ->  [_relation_tree, swapped] and 1 in _get_fields_cache
Logbook._meta._expire_cache(forward=False)  ->  None
cached(Logbook)  ->  [fields, swapped] and 0 in _get_fields_cache
cached(LogEntry)  ->  [_relation_tree, swapped] and 1 in _get_fields_cache
Logbook._meta.get_field('logentry')  ->  <ManyToOneRel: office.logentry>
cached(Logbook)  ->  [_forward_fields_map, _relation_tree, fields, fields_map, swapped] and 3 in _get_fields_cache
```

Reading `Options.related_objects` on Logbook left an `Options._relation_tree` in the options of LogEntry, of which nothing had been asked: the tree is made for all the models at once. Expiring Logbook's reverse side removed its two reverse answers and emptied its `_get_fields_cache`, the two forward lists in it included, but left `Options.fields` where it was and LogEntry's tree alone. The next question to need the tree, an `Options.get_field` for a name that is no forward field, had it made again. The counts are of lists that `_get_fields` has kept: each list or dictionary made for Logbook asked it for one, and the making of the tree asks every model for its own forward fields, which is the one in LogEntry's.

`Options.swapped`, which says whether a setting has replaced the model with another, is in these lines because other code read it on the way. A foreign key reads it on its own model before it gives the other class an attribute, which is why LogEntry had it from the start (`django/db/models/fields/related.py:ForeignObject.contribute_to_related_class`). And the registry reads it on each model as it makes its list, which leaves out a swapped one.

## `get_field`: one field by its name

`Options.get_field` returns a field for a name, and it looks in two dictionaries in an order that the source's comment explains: the forward side first, to avoid loading the relation tree, which is expensive, before it is needed (`django/db/models/options.py:Options.get_field`).

The first is `Options._forward_fields_map`. It holds every forward field of the model and its parents, the many-to-many and private ones included, under its name and also under its **attname**, the name its value is kept under on an instance, so that `"home_id"` finds the foreign key of Ship as `"home"` does. It needs this model and its parents and nothing else, and can be asked at any time.

```text recording=models
Ship._meta.get_field('home')  ->  <django.db.models.fields.related.ForeignKey: home>
Ship._meta.get_field('home_id') is Ship._meta.get_field('home')  ->  True
Ship._meta.get_field('crew')  ->  <ManyToOneRel: crew.sailor>
...
Ship._meta.get_field('mast')  ->  raises FieldDoesNotExist: Ship has no field named 'mast'
Port._meta.get_field('Voyage_calls+')  ->  <ManyToOneRel: fleet.voyage_calls>
```

A name that is not in the first may be a rel's. The second dictionary, `Options.fields_map`, holds the rels of the reverse side, the hidden ones included, each under the name the relation goes by when a query follows it from this model; of two rels with one name, such as two foreign keys that each give `"+"` as their `"related_name"`, it holds one ([Relations: a field, its rel and the class at the other end](relations.md)). That is not always the name of the attribute the relation put on the class: the many-to-many field of Voyage is among Port's rels as `"voyage"`, and the attribute it gave Port is `"voyage_set"`.

The second dictionary needs the tree, and so every model. If the registry has not finished importing models, `get_field` does not try: a miss in the first dictionary raises `FieldDoesNotExist` at once, with a message that adds that the app cache is not ready and that a related field made by another model would not be available yet. Once the models are loaded, a name in neither dictionary raises the same exception with the plain message that `"mast"` got above.

> **A trap.** Django's documentation of `get_field` says that a hidden field cannot be retrieved by name (`docs/ref/models/meta.txt`). `fields_map` is built with the hidden rels in it, by a call of `Options._get_fields` with `include_hidden=True`, and the last line above is a hidden rel found under its name, the `"+"` included (`django/db/models/options.py:Options.fields_map`).

A query that resolves the words of a filter asks `get_field` for one word after another, until a word is neither a field, an annotation nor a filtered relation, or the field found is not a relation (`django/db/models/sql/query.py:Query.names_to_path`) ([From QuerySet to SQL](../sql.md)).

## The primary key

`Options.pk` is the model's primary key, and is `None` when the object is made (`django/db/models/options.py:Options.__init__`).

A field declared with `primary_key=True` claims the place as it is added. `Options.add_field` offers every field it puts in `Options.local_fields` to `Options.setup_pk`, which takes the field as the key if the options have none yet and the field says it is one (`django/db/models/options.py:Options.setup_pk`). The first such field to arrive is the key, and a second is left as an ordinary member of the list for the checks to find ([The model checks](checks.md)). A `CompositePrimaryKey`, a key made of several columns, assigns itself to `Options.pk` as well, whether or not another field got there first (`django/db/models/fields/composite.py:CompositePrimaryKey.contribute_to_class`) ([The field classes](field-types.md)).

`Options._prepare`, which the metaclass calls when everything declared and inherited is on the class, does nothing about the key unless it is still missing (`django/db/models/options.py:Options._prepare`). If the model has a parent with a table, the link to the first such parent is made the key: the method sets `Field.primary_key` on that field and hands it to `setup_pk`, as it did for Officer:

```text recording=models
Options._prepare(Officer)
  Options.setup_pk(Officer.sailor_ptr)  ->  Options.pk is Officer.sailor_ptr
```

With no parent either, `_prepare` makes a field of the class that `Options._get_default_pk_class` returns, with `primary_key=True` and `auto_created=True`, and adds it under the name `"id"` like any field, so that it reaches `setup_pk` by the ordinary route, as the class statement of Port showed (`django/db/models/options.py:Options._get_default_pk_class`) ([The field classes](field-types.md)). A proxy takes none of these routes: `Options.setup_proxy` has already given it the key of the model it stands for ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)).

`_prepare` has one other job, which it does before the key. For a model whose `Meta` gave `"order_with_respect_to"`, it replaces the name with the field, found among the forward fields by its name or its attname, sets the ordering to `"_order"`, and adds a field of that name, an `OrderWrt`, unless the class already has one.

## Swapped models, and models that are not managed

A `Meta` may set `"swappable"` to the name of a setting. It says that a project may put a model of its own in this one's place, by naming that model in the setting. The one model in Django that sets it is the user, to `"AUTH_USER_MODEL"` (`django/contrib/auth/models.py:User`) ([Authentication, sessions and messages](../auth.md)).

`Options.swapped` says whether that has happened: it is `None` for a model that has not been replaced, and otherwise the setting's value, which names the model put in its place (`django/db/models/options.py:Options.swapped`). A model has not been replaced when it is not swappable, when the setting is empty or missing, and when the setting names this very model, in a comparison that ignores the case of the model's name. A model whose `swapped` is not `None` is left out of the registry's lists of models unless they are asked to include it, and reading a manager on it raises `AttributeError` (`django/apps/config.py:AppConfig.get_models`, `django/db/models/manager.py:ManagerDescriptor.__get__`).

`swapped` is a kept answer like the lists. For a swappable model, `Options.contribute_to_class` connects the method `Options.setting_changed` to the signal of the same name, which `override_settings` sends, and the receiver deletes the kept `swapped` when the signal names its setting (`django/db/models/options.py:Options.setting_changed`) ([The test framework](../testing.md)).

`Options.managed` is a flag, true unless the `Meta` sets it false; on the model Django makes for a many-to-many table it is set from the two models joined ([Many-to-many relations](many-to-many.md)). Given a connection, or the alias of one, `Options.can_migrate` answers whether the model's table may be made and altered there (`django/db/models/options.py:Options.can_migrate`). The answer is no for a proxy, for a swapped model and for a model that is not managed. Any other model is refused only where its `Meta` has tied it to certain databases: if `"required_db_vendor"` is set, the answer is whether that is the connection's vendor, and otherwise every feature named in `"required_db_features"` must be true on the connection ([Migrations](../migrations.md)).
