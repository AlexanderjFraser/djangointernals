---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The ORM
contents: metaclass, options, fields, field-types, inheritance, managers, constraints, checks
---

# Models and fields

A model class is put together while its class statement runs. A metaclass, `ModelBase`, hands the new class to every field in the body; each field enters itself in the class's options object and leaves a descriptor where it stood; and a relation can put an attribute on the class it points at as well.

A model has to be several things at once. It is an ordinary Python class, whose instances a view hands to a template. It is the description of a table: columns and their types, constraints, indexes, enough for a migration to be written from it. It is the vocabulary of queries: a filter on `"home__country"` has to find, from those two words, a join to another table and a column there. And it is one model among many that point at each other, some of them by the name of a class that has not been imported yet.

Django gets all four from one class statement, by taking the statement over. What the body of a model writes is not what the class ends up with. The fields are moved into an object of their own, the class is given attributes its body never mentions, and other classes are given attributes because of it. This chapter is about that construction: the metaclass, the options object, the fields, inheritance and managers, then what stands beside the fields in a model's description, its constraints and indexes, and the checks that read the whole description for mistakes. What a relation leaves on its two classes is told in [Relations](relations.md), and an instance of the finished class, as it is made, read, saved, validated and deleted, in [An instance and its row](instance.md).

The examples are the models of a shipping line, harbour, in three applications. The fleet has the ports, the ships and their voyages; the crew has the sailors, among them the officers, a child of Sailor with a table of its own, and the veterans, a proxy whose manager keeps the sailors who signed on before 2020; and the office has the paperwork: the licence that lets a sailor pilot ships into a port, the manifest of what a voyage carried, the berths of a port, and the logbooks with their lines. Here are the three `models.py` files whole, less their imports and their docstrings; *serials.next_serial*, the default of a manifest's key, is a function of the project's that returns the next of a run of numbers as text, `"M-0001"` and on.

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
class Rank(models.TextChoices):
    MASTER = "master"
    MATE = "mate", "First mate"
    ENGINEER = "engineer"


class SailorQuerySet(models.QuerySet):
    def aboard(self, ship):
        return self.filter(ship=ship)


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


class VeteranManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(signed_on__year__lt=2020)


class Veteran(Sailor):
    objects = VeteranManager()

    class Meta:
        proxy = True


# harbour/office/models.py
class Licence(models.Model):
    sailor = models.ForeignKey("crew.Sailor", on_delete=models.CASCADE)
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    granted = models.DateField()


class Manifest(models.Model):
    serial = models.CharField(max_length=8, primary_key=True, default=serials.next_serial)
    voyage = models.ForeignKey("fleet.Voyage", on_delete=models.CASCADE)
    crates = models.PositiveIntegerField()
    kilos_each = models.PositiveIntegerField()
    kilos = models.GeneratedField(expression=F("crates") * F("kilos_each"), output_field=models.PositiveIntegerField(), db_persist=True)
    stamped = models.BooleanField(db_default=False)
    scan = models.FileField(upload_to="manifests/", blank=True)


class Berth(models.Model):
    pk = models.CompositePrimaryKey("port_id", "number")
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    metres = models.PositiveSmallIntegerField()


class Logbook(models.Model):
    title = models.CharField(max_length=60)


class LogEntry(models.Model):
    book = models.ForeignKey(Logbook, on_delete=models.DB_CASCADE)
    line = models.CharField(max_length=200)
```

Three of the office's models carry a feature the others do not, and each is shown again where a section turns on it: Manifest a key with a default, a column the database computes, a column whose default the database supplies, and a file; Berth a primary key of two columns; and LogEntry a foreign key whose deletions the database carries out itself.

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

A field holds no values. One field object serves every instance of its class, and an instance's values are in the instance's own `__dict__`, under the attnames. The `DeferredAttribute` that a concrete field leaves on the class, where its class does not ask for another descriptor, acts only when the value is missing, and has it fetched; a foreign key's descriptor also acts when a value is assigned, and a file field's at every read ([A field: the base class](models/fields.md)). The classes that make up `django.db.models`' fields differ in the column they ask for and in how they convert a value, and a few differ in kind: a generated column, a primary key of several columns, a file ([The field classes](models/field-types.md), [File fields](instance/files.md)).

## A relation has two ends

A `ForeignKey` is a field with a column, like any other. What makes it a relation is a second object it carries as `Field.remote_field`: a **rel**, here a `ManyToOneRel`, which is the same relation seen from the model it points at. The rel is what stands in the other model's list of fields, as `"crew"` did above, and it is what names the attribute the other class is given (`django/db/models/fields/__init__.py:Field.__init__`, `django/db/models/fields/reverse_related.py:ForeignObjectRel`). The attributes a relation leaves on its two classes, and the ways an instance reaches the objects at the other end, are [Relations](relations.md)'s.

## Three kinds of inheritance

A model class can inherit from another in three ways, and the metaclass does a different thing for each (`django/db/models/base.py:ModelBase.__new__`). An abstract base, like Named, has no table. Its fields are copied into each class that inherits directly from it, as `"name"` was, unless the class sets the name itself. A base that is not abstract keeps its own table. The child gets a table for its own fields only, and a `OneToOneField` to the parent, which the metaclass adds, as `"sailor_ptr"` for a child of Sailor, unless the class or an abstract base of it declared one as the parent link. The link to the first such parent becomes the child's primary key if the child declares no other: an Officer is a row of each table with one key. A **proxy**, like Veteran, adds no table. It is a second class over the same rows, with its own methods and managers (`django/db/models/options.py:Options.setup_proxy`) ([Inheritance: abstract bases, parents with tables and proxies](models/inheritance.md)).

## A manager is where queries start

The attribute `"objects"` of a class is a descriptor that gives a manager bound to that class (`django/db/models/manager.py:ManagerDescriptor.__get__`). The methods a manager takes from a queryset are not the queryset's own: each is a function of the same name that calls the queryset's method on a new queryset (`django/db/models/manager.py:BaseManager._get_queryset_methods`). A model has a default manager, which is the first of its managers unless its `Meta` names another, and a base manager, through which Django saves and reloads an instance, fetches the object a foreign key points at, and finds the rows a delete must collect. The two need not be the same ([Managers](models/managers.md)).

## An instance of the class

The class statement makes a description and a class; a new instance of the class holds little: the values, in its own `__dict__` under the fields' attnames, and a `ModelState` that says whether it is still being added and which database it belongs to (`django/db/models/base.py:Model.__init__`, `django/db/models/base.py:ModelState`). Everything else it seems to have is the class's, found by ordinary attribute lookup: the descriptors the fields left, `_meta`, the methods. How an instance is made from a row, what it does when a value it lacks is read, and how it is saved, validated and deleted are [An instance and its row](instance.md)'s.

## The checks

Many mistakes in a model raise nothing when its class statement runs. A relation to a model that does not exist only leaves a function waiting in the registry. Such mistakes are found afterwards, by the system checks: `Model.check` runs a series of methods over a model class, and each field and manager checks itself, as each constraint and index does for every database the check was given (`django/db/models/base.py:Model.check`) ([The model checks](models/checks.md)).

## The neighbours

The app registry is where a model class is entered and where a relation waits for its other class; it and the import of every `models` module are part of start-up ([Settings, apps and startup](startup.md)). The checks are run by the `check` command and before several others ([Management commands](commands.md)).

An instance and its life against its row are [An instance and its row](instance.md); a manager's methods are a queryset's ([QuerySets](querysets.md)); what a relation adds to two classes, and how related objects are fetched, is [Relations](relations.md). A query reads the model through `_meta` to turn a filter's names into joins ([Building a query](query.md)), with the lookups and transforms a field registers ([Expressions, lookups and functions](expressions.md)), and the statements that a queryset or a save sends in this chapter's recordings are written by the compilers ([The SQL compiler](sql.md)). The column type a field gets and the conversion of a value on its way out of a row are the database backend's ([Database backends](backends.md)), and the schema editor that turns a model into a table is [Schemas and test databases](schema.md)'s. What `Field.deconstruct` returns for each field, and a model's options, are what a migration is written from, and migrations make model classes of their own in a registry of their own (`django/db/models/fields/__init__.py:Field.deconstruct`) ([Migrations](migrations.md), [Making migrations](makemigrations.md)).

`ModelForm` reads `_meta` for its fields and calls `Model.full_clean` ([Model forms: `ModelForm` and `fields_for_model`](forms/model-forms.md)). Signals themselves are in [Signals: `Signal`, receivers and sending](services/signals.md), and serialization in [Serialization: `serialize`, `deserialize` and `DeserializedObject`](services/serializers.md). A field that points at any model, by a content type and a key, is in [Generic foreign keys: `GenericForeignKey`](contrib/generic-foreign-key.md), and the model that a setting can swap for another is the user, in [The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`](auth/user-model.md). [A queryset becomes SQL](overview/query.md) follows one query from a manager to its rows and back.
