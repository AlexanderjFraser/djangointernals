---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: metaclass, options, fields, field-types, relations, related-objects, many-to-many, inheritance, managers, instances, saving, deleting, validation, constraints, files, checks
---

# Models and fields

A model class is put together while its class statement runs. A metaclass, `ModelBase`, hands the new class to every field in the body; each field enters itself in the class's options object and leaves a descriptor where it stood; and a relation can put an attribute on the class it points at as well. This chapter follows that assembly, and then an instance of the result as it is made, read, saved, validated and deleted.

A model has to be several things at once. It is an ordinary Python class, whose instances a view hands to a template. It is the description of a table: columns and their types, constraints, indexes, enough for a migration to be written from it. It is the vocabulary of queries: a filter on `"home__country"` has to find, from those two words, a join to another table and a column there. And it is one model among many that point at each other, some of them by the name of a class that has not been imported yet.

Django gets all four from one class statement, by taking the statement over. What the body of a model writes is not what the class ends up with. The fields are moved into an object of their own, the class is given attributes its body never mentions, and other classes are given attributes because of it. The first half of this chapter is about that construction: the metaclass, the options object, fields, relations, inheritance and managers. The second half is about one row: the instance, how it is saved and deleted, and how it is validated. The last sections are about what stands beside the fields in a model's description, its constraints and indexes, about the fields that keep a file, and about the checks that read the whole description for mistakes.

The examples are the models of a shipping line, in three applications. The fleet has the ports, the ships and their voyages, the crew has the sailors, and the office has the paperwork, which is brought in where a section needs it. Everything recorded in this chapter was recorded from a running Django with these among its models. The listing leaves out their docstrings and three small definitions, the choices of a rank, a queryset class and a manager class, which are shown where they are used.

```python
# harbour/fleet/models.py
class Named(models.Model):
    name = models.CharField(max_length=60)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Port(Named):
    country = models.CharField(max_length=40)


class Ship(Named):
    tonnage = models.PositiveIntegerField()
    home = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ships")
    captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")

    class Meta(Named.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(tonnage__gt=0), name="%(class)s_has_tonnage"),
            models.UniqueConstraint(fields=["name", "home"], name="one_name_to_a_port"),
        ]
        indexes = [models.Index(fields=["home", "tonnage"])]


class Voyage(models.Model):
    ship = models.ForeignKey(Ship, on_delete=models.CASCADE)
    sailed = models.DateField()
    calls = models.ManyToManyField(Port)


# harbour/crew/models.py
class Sailor(models.Model):
    name = models.CharField(max_length=60)
    ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE, related_name="crew")
    signed_on = models.DateTimeField(auto_now_add=True)
    pilots_into = models.ManyToManyField("fleet.Port", through="office.Licence", related_name="pilots")

    objects = SailorQuerySet.as_manager()

    def __str__(self):
        return self.name


class Officer(Sailor):
    rank = models.CharField(max_length=10, choices=Rank)


class Veteran(Sailor):
    objects = VeteranManager()

    class Meta:
        proxy = True
```

## A class statement is a program

Python makes a class by calling its metaclass with the class's name, its bases, and a dictionary of everything the body assigned. For a model the metaclass is `ModelBase`, and `ModelBase.__new__` does not pass that dictionary on whole. It takes `Meta` out, and sorts the rest of the body's attributes into those that are not classes and have a method named `contribute_to_class`, and the others. The others, a `__str__` or a constant, go to `type.__new__` in the ordinary way. The first are held back, and once the bare class exists each is handed the class and left to install itself (`django/db/models/base.py:ModelBase.__new__`, `django/db/models/base.py:ModelBase.add_to_class`).

A field is such an object. So is a **manager**, the object a class's queries start from, and so is the `Options` object (`django/db/models/options.py:Options`). The metaclass makes it from the body's `Meta`, or, where the body has none, from the `Meta` an abstract base left on the class if there is one. It is installed first, under the name `_meta`, because the fields that follow need somewhere to enter themselves. This is the class statement of Ship as it ran, with the lines that make its three exception classes left out, and those for its second relation. A recording reads like this throughout the chapter: each line is a call, and a line set in under it is a call made inside it; an arrow gives what a call returned; a line of three dots stands for lines left out; and a name in brackets after a call says which object it was made on. What to look for here: the fields are handed the class in the order the body wrote them, a foreign key does more than a plain field does, and the class is given a field, a key and a manager that its body never mentioned.

```text recording=models
ModelBase.__new__('Ship', (Named,))
  ModelBase.add_to_class(Ship, '_meta', an Options)
    Options.contribute_to_class(Ship, '_meta')
...
  ModelBase.add_to_class(Ship, 'tonnage', a PositiveIntegerField)
    Field.contribute_to_class(Ship, 'tonnage')  (a PositiveIntegerField)
      Options.add_field(Ship.tonnage)
      DeferredAttribute.__init__(Ship.tonnage)
  ModelBase.add_to_class(Ship, 'home', a ForeignKey)
    ForeignObject.contribute_to_class(Ship, 'home')  (a ForeignKey)
      RelatedField.contribute_to_class(Ship, 'home')  (a ForeignKey)
        Field.contribute_to_class(Ship, 'home')  (a ForeignKey)
          Options.add_field(Ship.home)
          DeferredAttribute.__init__(Ship.home)  (a ForeignKeyDeferredAttribute)
        lazy_related_operation(resolve_related_class, Ship, Port)
          Apps.lazy_model_operation(function, ('fleet', 'ship'), ('fleet', 'port'))
          -> Apps._pending_operations holds 1 under ('fleet', 'ship')
      ForwardManyToOneDescriptor.__init__(Ship.home)
...
  Field.__deepcopy__  (a copy of Named.name)
  ModelBase.add_to_class(Ship, 'name', a CharField)
    Field.contribute_to_class(Ship, 'name')  (a CharField)
      Options.add_field(Ship.name)
      DeferredAttribute.__init__(Ship.name)
  ModelBase._prepare(Ship)
    Options._prepare(Ship)
      Options._get_default_pk_class  ->  the class BigAutoField
      ModelBase.add_to_class(Ship, 'id', a BigAutoField)
        AutoFieldMixin.contribute_to_class(Ship, 'id')  (a BigAutoField)
          Field.contribute_to_class(Ship, 'id')  (a BigAutoField)
            Options.add_field(Ship.id)
              Options.setup_pk(Ship.id)  ->  Options.pk is Ship.id
            DeferredAttribute.__init__(Ship.id)
    ModelBase.add_to_class(Ship, 'objects', a Manager)
      BaseManager.contribute_to_class(Ship, 'objects')  (a Manager)
        ManagerDescriptor.__init__(a Manager)
        Options.add_manager(a Manager)
    Index.set_name_with_model(Ship)  ->  the index is named 'fleet_ship_home_id_f9b8f2_idx'
    signal class_prepared, sender Ship
  Apps.register_model('fleet', Ship)
    Apps.do_pending_operations(Ship)
      Apps.lazy_model_operation(function, ('fleet', 'port'))
        Apps.lazy_model_operation(function)
          resolve_related_class(Ship, Port, field=Ship.home)
            ForeignKey.contribute_to_related_class(Port, the rel of Ship.home)
              ForeignObject.contribute_to_related_class(Port, the rel of Ship.home)
                ReverseManyToOneDescriptor.__init__(the rel of Ship.home)
      Apps.lazy_model_operation(function, ('crew', 'sailor'))
      -> Apps._pending_operations holds 1 under ('crew', 'sailor')
    Apps.clear_cache
```

The fields install themselves in the order the body wrote them. A field's `contribute_to_class` takes its name from the attribute it was assigned to, enters the field in the options with `Options.add_field`, and, where the field has a column, sets a descriptor on the class under the name the value will be kept by (`django/db/models/fields/__init__.py:Field.contribute_to_class`). A foreign key does the same and two things more. It sets a second descriptor, under the field's own name, which is what gives a Port when `"home"` is read on a ship (`django/db/models/fields/related.py:ForeignObject.contribute_to_class`). And, unless its class is abstract, it leaves a function with the app registry, which keeps it in `Apps._pending_operations` until both classes of the relation exist. The registry takes the models a function waits for one at a time, which is why the recording shows the function filed first under Ship's own name, Ship not being registered until its statement ends, and the method calling itself for what remains (`django/db/models/fields/related.py:RelatedField.contribute_to_class`, `django/apps/registry.py:Apps.lazy_model_operation`).

Three things in the recording were not in the body. The field `"name"` comes from Named, which is **abstract**: a class with no table of its own, declared to be inherited from. A field object belongs to one class, so a field of an abstract base is copied for each class that inherits directly from it and does not set that name itself. The other two are added by `ModelBase._prepare`, the metaclass's last step before the registry. It begins by calling `Options._prepare`, which finds that no field has claimed to be the primary key and makes one, `"id"`, of the class its application names for the purpose, which is the one `settings.DEFAULT_AUTO_FIELD` names unless the app config says otherwise. And it adds the manager `"objects"`, because neither the body nor a base declared a manager (`django/db/models/base.py:ModelBase._prepare`, `django/db/models/options.py:Options._prepare`).

The last step is `Apps.register_model`, which enters the class in `Apps.all_models` under its app's label and its own name in lower case. Until that call the class is in no list of models and can be found by no name. As it is entered, the registry calls the functions that were waiting for it. The one that `"home"` left finds Port already there and runs: it puts the attribute `"ships"` on Port. The one that `"captain"` left still needs the crew's Sailor, whose module has not been imported, and goes on waiting (`django/apps/registry.py:Apps.register_model`, `django/apps/registry.py:Apps.do_pending_operations`).

What the class holds afterwards is not what was written:

```text recording=models
What the class Ship holds in its own __dict__, in the order the names were set
    __doc__: 'Ship(id, name, tonnage, home, captain)'
    _meta: an Options
    DoesNotExist: the class Ship.DoesNotExist
    MultipleObjectsReturned: the class Ship.MultipleObjectsReturned
    NotUpdated: the class Ship.NotUpdated
    tonnage: a DeferredAttribute
    home_id: a ForeignKeyDeferredAttribute
    home: a ForwardManyToOneDescriptor
    captain_id: a ForeignKeyDeferredAttribute
    captain: a ForwardOneToOneDescriptor
    name: a DeferredAttribute
    id: a DeferredAttribute
    objects: a ManagerDescriptor
    voyage_set: a ReverseManyToOneDescriptor
    crew: a ReverseManyToOneDescriptor
```

None of the three fields is there as a field. Under `"tonnage"` is a `DeferredAttribute`; the field `"home"` has become two attributes, `"home_id"` for the key and `"home"` for the object; and the last two names were put there because of the class statements of Voyage and Sailor, which ran later. The docstring at the head is the metaclass's too, the body having written none. A class made abstract stops before `_prepare`: Named has options and a field, and no key, no manager and no place in the registry ([`ModelBase`: a class statement becomes a model](models/metaclass.md)).

```text figure=the-assembly
The body of Ship, as written:
    tonnage = PositiveIntegerField()
    home = ForeignKey(Port, ...)
    captain = OneToOneField(...)
    class Meta(Named.Meta)
  not written in the body, and added by
    name          a copy of the field of Named
    id            Options._prepare
    objects       ModelBase._prepare
    DoesNotExist  ModelBase.__new__, and two more exception classes

        |
        v

The class Ship, as it is left:
    tonnage       DeferredAttribute
    home_id       ForeignKeyDeferredAttribute
    home          ForwardManyToOneDescriptor
    captain_id    ForeignKeyDeferredAttribute
    captain       ForwardOneToOneDescriptor
    name          DeferredAttribute
    id            DeferredAttribute
    objects       ManagerDescriptor
    DoesNotExist, MultipleObjectsReturned, NotUpdated
    _meta, an Options:
        local_fields     id, name, tonnage, home, captain
        pk               the field id
        local_managers   the manager objects
        and what Meta said: ordering, constraints, indexes
  Two more names are added later, by the class statements of Voyage and of Sailor: voyage_set, crew

        |
        v

The app registry: Apps.register_model enters the class
    all_models["fleet"]["ship"]               the class Ship
    _pending_operations[("crew", "sailor")]   the function that captain left, still waiting for that class
  The function that home left runs as Ship is registered:

        |
        v

The class Port:
    ships         ReverseManyToOneDescriptor
```

*What the class statement of Ship leaves behind. Each field goes to the options and leaves a descriptor on the class; a foreign key leaves two, and a third on the class it points at; what the body did not write, an inherited field, a key, a manager and three exception classes, is added.*

## `_meta` is the model as data

A model class keeps its description in one object, an `Options`, under the name `_meta`. Part of it is what the body's `Meta` said and what follows from the class's name: the table's name, the default ordering, the constraints. The rest is the fields. The object keeps the fields that were added to this class in three lists: `Options.local_fields`, sorted by a counter each field takes as it is made, with a field Django made itself put first, and beside it one for many-to-many fields and one for fields of a kind called private, such as a generic foreign key. It keeps the class's managers as `Options.local_managers`. The lists that combine these it works out when it is asked: the fields with those of parents, the fields that have a column, which Django calls **concrete**, the relations that models have to this one (`django/db/models/options.py:Options`, `django/db/models/options.py:Options.add_field`).

```text recording=models
names(Ship._meta.fields)  ->  [id, name, tonnage, home, captain]
names(Ship._meta.concrete_fields)  ->  [id, name, tonnage, home, captain]
names(Ship._meta.related_objects)  ->  [voyage, crew]
names(Ship._meta.get_fields())  ->  [voyage, crew, id, name, tonnage, home, captain]
```

The two names at the head of the last list, `"voyage"` and `"crew"`, are not fields of Ship. They are the far ends of the foreign keys that Voyage and Sailor have to it, under the names a query knows them by (the attribute on the class for the first is `"voyage_set"`), and the options find them by going through every model in the registry, which is why a list that includes them cannot be had until every model has been imported. The derived lists are kept once made, and thrown away when a field or a manager is added to the class, when a relation that was given the class itself and not its name is added to another, and, once the registry is ready, each time a model is registered.

The rest of Django reads a model through this object. A `ModelForm` takes its fields from it, a migration is written from it, and a query resolves the names in a filter against it (`django/forms/models.py:fields_for_model`, `django/db/migrations/state.py:ModelState.from_model`, `django/db/models/sql/query.py:Query.names_to_path`) ([The options: what a model keeps as `_meta`](models/options.md)).

## A field

A `Field` is one column's worth of the description, and it answers for that column to several parties (`django/db/models/fields/__init__.py:Field`). To the schema it gives a column type, through a table the database backend keeps (`django/db/models/fields/__init__.py:Field.db_type`), and to a migration the arguments it was made with (`django/db/models/fields/__init__.py:Field.deconstruct`). To a query it prepares a value for the database, and takes part in converting what comes back (`django/db/models/fields/__init__.py:Field.get_db_prep_value`, `django/db/models/fields/__init__.py:Field.get_db_converters`). To validation it cleans a value (`django/db/models/fields/__init__.py:Field.clean`), and to a form it offers a form field (`django/db/models/fields/__init__.py:Field.formfield`).

A field knows three names. `Field.name` is the attribute the body assigned it to, `Field.attname` is the key its value is kept under on an instance, and `Field.column` is the column. For most fields the three are one word. For the foreign key of Ship they are `"home"`, `"home_id"` and `"home_id"`.

A field holds no values. One field object serves every instance of its class, and an instance's values are in the instance's own `__dict__`, under the attnames. The `DeferredAttribute` that a concrete field leaves on the class, where its class does not ask for another descriptor, acts only when the value is missing, and has it fetched; a foreign key's descriptor also acts when a value is assigned, and a file field's at every read ([A field: the base class](models/fields.md)). The classes that make up `django.db.models`' fields differ in the column they ask for and in how they convert a value, and a few differ in kind: a generated column, a primary key of several columns, a file ([The field classes](models/field-types.md), [File fields](models/files.md)).

## A relation has two ends

A `ForeignKey` is a field with a column, like any other. What makes it a relation is a second object it carries as `Field.remote_field`: a **rel**, here a `ManyToOneRel`, which is the same relation seen from the model it points at. The rel is what stands in the other model's list of fields, as `"crew"` did above, and it is what names the attribute the other class is given (`django/db/models/fields/__init__.py:Field.__init__`, `django/db/models/fields/reverse_related.py:ForeignObjectRel`).

So a relation is reached from both classes, through descriptors. Reading the field's name on an instance gives the related object, fetched on the first read and kept on the instance afterwards:

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

The descriptor does not decide how to fetch. It asks the instance's **fetch mode**, which calls back the descriptor's `fetch_one` for this instance, or its `fetch_many` for the instances that one run of a query made together with this one, or raises `FieldFetchBlocked` (`django/db/models/fetch_modes.py`) ([Reading and setting related objects](models/related-objects.md)).

> **Changed in 6.1.** Fetch modes are new. Before them, reading a related object that had not been fetched always ran one query for that one instance, which is what the default mode, `FETCH_ONE`, still does.

From the other class a foreign key that is not one-to-one is a manager. The attribute `"ships"` of a port is not a list. It is a descriptor that makes, at each read, a manager whose querysets are already filtered to that port's ships (`django/db/models/fields/related_descriptors.py:ReverseManyToOneDescriptor.__get__`). A many-to-many relation has such a manager at its own end and, in the ordinary case, at the other, and no column at either: its rows are in a third table, whose model Django makes itself unless the field names one ([Relations: a field, its rel and the class at the other end](models/relations.md), [Many-to-many relations](models/many-to-many.md)).

## Three kinds of inheritance

A model class can inherit from another in three ways, and the metaclass does a different thing for each (`django/db/models/base.py:ModelBase.__new__`). An abstract base, like Named, has no table. Its fields are copied into each class that inherits directly from it, as `"name"` was, unless the class sets the name itself. A base that is not abstract keeps its own table. The child gets a table for its own fields only, and a `OneToOneField` to the parent, which the metaclass adds, as `"sailor_ptr"` for a child of Sailor, unless the class or an abstract base of it declared one as the parent link. The link to the first such parent becomes the child's primary key if the child declares no other: an Officer is a row of each table with one key. A **proxy**, like Veteran, adds no table. It is a second class over the same rows, with its own methods and managers (`django/db/models/options.py:Options.setup_proxy`) ([Inheritance: abstract bases, parents with tables and proxies](models/inheritance.md)).

## A manager is where queries start

The attribute `"objects"` of a class is a descriptor that gives a manager bound to that class (`django/db/models/manager.py:ManagerDescriptor.__get__`). The methods a manager takes from a queryset are not the queryset's own: each is a function of the same name that calls the queryset's method on a new queryset (`django/db/models/manager.py:BaseManager._get_queryset_methods`). A model has a default manager, which is the first of its managers unless its `Meta` names another, and a base manager, through which Django saves and reloads an instance, fetches the object a foreign key points at, and finds the rows a delete must collect. The two need not be the same ([Managers](models/managers.md)).

## An instance is a `__dict__` and a state

Making an instance runs `Model.__init__`, which sets an attribute for each field that has a column and is not generated, from the arguments or from the field's default, and binds a new `ModelState` as `Model._state` (`django/db/models/base.py:Model.__init__`, `django/db/models/base.py:ModelState`). That is all an instance is:

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

The values are under attnames, so a foreign key is there as a number. The port itself, having been passed in, is kept in the state's cache of related objects. The state also records whether the instance is being added, which is true until it has been saved or was made from a row, and which database it belongs to.

A row fetched by a query becomes an instance through the same `__init__`, called by `Model.from_db` with the row's values in the order of the model's concrete fields (`django/db/models/base.py:Model.from_db`). A query that fetched only some columns leaves the others out of the `__dict__` altogether, and that absence is the whole of what it means for a field to be **deferred**: reading the attribute finds nothing on the instance, falls through to the descriptor on the class, and the descriptor asks the instance's fetch mode for the value, as a relation's descriptor does ([An instance and its state](models/instances.md)).

## Saving is an update, or else an insert

`Model.save` does not ordinarily ask first whether the row exists; a model whose `Meta` sets `select_on_save`, and a table with nothing to write but its key, are the exceptions. For each table of the model, it decides from what it has in hand. If the primary key is set it tries an `"UPDATE"`, and takes a result that touched a row as success. If that touched nothing, or the key was not set, it inserts. A Ship made with a key that no row has shows both statements:

```text recording=models
Ship(id=40, name='Skua', tonnage=90, home=leith).save(): a primary key set by hand, and no such row
    Model.save()  (a Ship)
      Model._prepare_related_fields_for_save
      Model.save_base()
        signal pre_save, sender Ship, raw=False, update_fields=None
        mark_for_rollback_on_error
        Model._save_table(cls=Ship)
          Model._do_update(pk_val=40, values for [name, tonnage, home, captain])
            SQL UPDATE "fleet_ship" SET "name" = %s, "tonnage" = %s, "home_id" = %s, "captain_id" = %s WHERE "fleet_ship"."id" = %s with params ('Skua', 90, 2, None, 40)
            -> []
          Model._do_insert(fields=[id, name, tonnage, home, captain], returning_fields=[id])
            SQL INSERT INTO "fleet_ship" ("id", "name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s, %s) RETURNING "fleet_ship"."id" with params (40, 'Skua', 90, 2, None)
            -> [(40,)]
          Model._assign_returned_values((40,), [id])
          -> updated: False
        signal post_save, sender Ship, created=True, update_fields=None
```

The update is skipped when the key is not set, when the instance is being added and its key has a default (unless the save is forced either way, or is the raw save that loads a fixture), and for a child's table when its parent's row has just been inserted. The arguments `force_insert=True`, `force_update=True` and `"update_fields"` each cut the decision short. With `"update_fields"`, or with `force_update=True` for the model's own table, an update that matches no row raises instead of falling back to an insert. In a save that is not raw, each value written goes through its field's `Field.pre_save` on the way, which is where a date that sets itself on saving gets its value (`django/db/models/base.py:Model._save_table`, `django/db/models/fields/__init__.py:Field.pre_save`, `django/db/models/fields/__init__.py:DateField.pre_save`).

A save does not validate. It refuses an instance that was given a related object with no primary key; anything else the instance holds is prepared by its field and sent: a value the field cannot prepare raises there, and one the table will not take is refused by the database ([Saving an instance](models/saving.md)). Validation is a separate call, `Model.full_clean`, which a `ModelForm` makes and `save` does not (`django/db/models/base.py:Model.full_clean`). It cleans the value of each field that has one to clean, which for a foreign key means asking the database whether the row it points at exists, calls `Model.clean`, asks the database whether a value that must be unique is already taken, and then tests the model's constraints against the instance, which for the two of Ship, when their fields passed their own cleaning, is a query each ([Validating an instance](models/validation.md), [Constraints and indexes](models/constraints.md)).

## Deleting is collected first

`Model.delete` deletes nothing until it knows everything that has to go; the only statements it sends before that are the selects that find the rows. It gives the instance to a `Collector`, which follows each foreign key and one-to-one field that points at the instance's model and does what that relation's `on_delete` says: collect the related rows too, refuse, or note that the column is to be set to null (`django/db/models/base.py:Model.delete`, `django/db/models/deletion.py:Collector.collect`). Only then does it delete. Where it can, it first puts the models in an order in which a row reached through a field that cannot be null is deleted before the row it points at, which the source says is for databases that cannot put off checking a foreign key until the transaction ends (`django/db/models/deletion.py:Collector.delete`, `django/db/models/deletion.py:Collector.sort`). Two tables point at a voyage: the one Django made for its ports of call, and that of Manifest, a model of the office with a foreign key to Voyage.

```text recording=models
A Voyage is deleted, with the rows that point at it
    autumn.delete()
      Model.delete()  (a Voyage)
        Collector.collect([<Voyage: Voyage object (2)>])
          Collector.can_fast_delete([<Voyage: Voyage object (2)>])  ->  False
          Collector.add([<Voyage: Voyage object (2)>])  ->  not already collected: [<Voyage: Voyage object (2)>]
          Collector.can_fast_delete(the class Voyage_calls, from_field=Voyage_calls.voyage)  ->  True
          Collector.can_fast_delete(the class Manifest, from_field=Manifest.voyage)  ->  True
          Collector.related_objects(Voyage_calls, [Voyage_calls.voyage], [<Voyage: Voyage object (2)>])  ->  a QuerySet of Voyage_calls, not yet fetched
          Collector.related_objects(Manifest, [Manifest.voyage], [<Voyage: Voyage object (2)>])  ->  a QuerySet of Manifest, not yet fetched
        Collector.delete
          Collector.sort
          Collector.can_fast_delete(<Voyage: Voyage object (2)>)  ->  False
          Atomic.__enter__  (savepoint=False)
            SQL BEGIN
          QuerySet._raw_delete  (a QuerySet of Voyage_calls, not yet fetched)
            SQL DELETE FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" IN (%s) with params (2,)
          QuerySet._raw_delete  (a QuerySet of Manifest, not yet fetched)
            SQL DELETE FROM "office_manifest" WHERE "office_manifest"."voyage_id" IN (%s) with params (2,)
          DeleteQuery.delete_batch([2])  (Voyage)
            SQL DELETE FROM "fleet_voyage" WHERE "fleet_voyage"."id" IN (%s) with params (2,)
          Atomic.__exit__
            BaseDatabaseWrapper.commit
          -> (2, {'fleet.Voyage_calls': 1, 'fleet.Voyage': 1})
        -> (2, {'fleet.Voyage_calls': 1, 'fleet.Voyage': 1})
```

The two tables that point at a voyage are emptied of its rows with one `"DELETE"` each and nothing fetched. The collector allows itself that when it has no reason to look at the rows: no receiver is connected for the model's delete signals, and deleting them calls for nothing further to be collected. Otherwise it fetches the rows, sends `pre_delete` and `post_delete` for each unless the model is one Django made itself, and deletes them by key (`django/db/models/deletion.py:Collector.collect`, `django/db/models/deletion.py:Collector.can_fast_delete`) ([Deleting: the `Collector`](models/deleting.md)).

> **Changed in 6.1.** `on_delete` may also name an action for the database to take, `DB_CASCADE`, `DB_SET_NULL` or `DB_SET_DEFAULT`. The collector that `Model.delete` makes passes over such a relation, and the rows are dealt with by the foreign key's `ON DELETE` clause.

## The checks

Many mistakes in a model raise nothing when its class statement runs. A relation to a model that does not exist only leaves a function waiting in the registry. Such mistakes are found afterwards, by the system checks: `Model.check` runs a series of methods over a model class, and each field and manager checks itself, as each constraint and index does for every database the check was given (`django/db/models/base.py:Model.check`) ([The model checks](models/checks.md)).

## The neighbours

The app registry is where a model class is entered and where a relation waits for its other class; it and the import of every `models` module are part of start-up ([Settings, apps and startup](startup.md)). The checks are run by the `check` command and before several others ([Management commands](commands.md)).

A manager's methods are a queryset's, and a queryset is what turns rows into instances by calling `Model.from_db` ([QuerySets](querysets.md)). The selects, inserts, updates and deletes in this chapter's recordings are written by the compilers, from a `Query` that reads the model through `_meta`; the lookups and transforms a field registers, the expressions a constraint is made of, and the SQL of an insert and an update belong there ([From QuerySet to SQL](sql.md)). The column type a field gets, the conversion of a value on its way out of a row, and the schema editor that turns a model into a table are the database backend's ([Database backends](backends.md)). What `Field.deconstruct` returns for each field, and a model's options, are what a migration is written from, and migrations make model classes of their own in a registry of their own (`django/db/models/fields/__init__.py:Field.deconstruct`) ([Migrations](migrations.md)).

`ModelForm` reads `_meta` for its fields and calls `Model.full_clean` ([Forms](forms.md)). Signals themselves, the storage a file field saves to, and serialization are in [Caching, files, mail, signals and tasks](services.md). A field that points at any model, by a content type and a key, is in [Content types, static files and the other contrib apps](contrib.md), and the model that a setting can swap for another is the user, in [Authentication, sessions and messages](auth.md). The first chapter follows one query from a manager to its rows and back ([A queryset becomes SQL](overview/query.md)).
