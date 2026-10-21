---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Inheritance: abstract bases, parents with tables and proxies

A model class can inherit from another model in three ways, and `ModelBase.__new__` does a different thing for each: it copies the fields of an abstract base into the child, it ties a child to a parent that has a table with a `OneToOneField`, made under a name ending in `"_ptr"` where the class statement supplies none, and it points the options of a proxy at the table of the model the proxy stands for.

Python has one kind of inheritance, and a relational database has none. A class statement with a model among its bases gives the child what Python always gives: the parent's methods and properties, and everything else in the parent's `__dict__`, found by ordinary attribute lookup. It says nothing about tables. And a model's fields are not among the things attribute lookup carries, because a field is not left on its class. It is entered in that class's options, and it records the one class it belongs to.

So for each base that is a model, the metaclass has to settle what the child's fields are and where their rows are kept. It goes by two settings of `Meta`: whether the base says `abstract = True`, and whether the child says `proxy = True`. The harbour has a model of each kind. The fleet's Ship, a second child of Named, is on the chapter's opening page, [Models and fields](../models.md).

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

```text figure=three-kinds
Three ways for one model class to inherit from another: the classes as written,
what the metaclass does for the child, the child's options afterwards, and the tables.

AN ABSTRACT BASE
    class Named            Meta: abstract = True      fields: name
    class Port(Named)                                 fields: country
  the metaclass copies name into Port
    the options of Port:
        local_fields     id, name, country
        parents          {}
        concrete_model   Port
    tables:
        (none for Named)
        fleet_port       id, name, country

A PARENT WITH A TABLE
    class Sailor                                      fields: name, ship, signed_on, pilots_into
    class Officer(Sailor)                             fields: rank
  the metaclass adds a link, sailor_ptr, to Officer, and Options._prepare makes it Officer's primary key
    the options of Officer:
        local_fields     sailor_ptr, rank
        fields           id, name, ship, signed_on (Sailor's own field objects, the many-to-many field not among them), then sailor_ptr, rank
        parents          {Sailor: sailor_ptr}
        concrete_model   Officer
    tables:
        crew_sailor      id, name, ship_id, signed_on
        crew_officer     sailor_ptr_id (the primary key, and a reference to crew_sailor.id), rank

A PROXY
    class Sailor                                      fields: name, ship, signed_on, pilots_into
    class Veteran(Sailor)  Meta: proxy = True         fields: none
  the metaclass gives the options of Veteran the table and the primary key of Sailor
    the options of Veteran:
        local_fields     (none)
        fields           id, name, ship, signed_on (Sailor's own field objects)
        parents          {Sailor: None}
        concrete_model   Sailor
    tables:
        crew_sailor      id, name, ship_id, signed_on
        (none for Veteran)
```

*The three kinds of inheritance among the harbour's models. An abstract base has no table and gives its child copies of its fields; a parent with a table keeps its fields, and the child's table holds the child's own and a link; a proxy has neither fields nor a table of its own, and is a second class over its parent's rows.*

## An abstract base: its fields are copied

An **abstract** model is one whose `Meta` says `abstract = True`. It is a model class with options and fields, and with nothing that needs a table: `ModelBase.__new__` returns it before the steps that would give it a primary key, a manager and a place in the app registry, and `Model.__init__` refuses to make an instance of it ([`ModelBase`: a class statement becomes a model](metaclass.md)).

When a class statement names an abstract model among its bases, the metaclass first installs the child's own attributes and then goes through the child's method resolution order. For each class there that is a direct base of the statement and an abstract model, it goes through the fields the base holds in `Options.local_fields` and `Options.local_many_to_many`. Each field that the child has not declined is copied with `copy.deepcopy`, and the copy is handed to `ModelBase.add_to_class` under the field's name, as the fields of the body were (`django/db/models/base.py:ModelBase.__new__`, `django/db/models/options.py:Options`). In Port's class statement that comes after the body's one field is in place:

```text recording=models
Field.__deepcopy__  (a copy of Named.name)
ModelBase.add_to_class(Port, 'name', a CharField)
  Field.contribute_to_class(Port, 'name')  (a CharField)
    Options.add_field(Port.name)
    DeferredAttribute.__init__(Port.name)
```

The copy's column is in Port's table, Named having none:

```text recording=models
editor.create_model(Port)
  SQL CREATE TABLE "fleet_port" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(60) NOT NULL, "country" varchar(40) NOT NULL)
```

Nothing in Port's options records the inheritance: an abstract base is given no entry in `Options.parents`, the dictionary of a model's parents that have tables, and passes on to a child only such entries as it has itself.

A field object belongs to one class. `Field.contribute_to_class` stores the class it is given as `Field.model`, and the field's name, its column and its place in that class's options are settled in the same call (`django/db/models/fields/__init__.py:Field.contribute_to_class`). The field of Named already belongs to Named. Each class that inherits from Named gets a field object of its own, a shallow copy that keeps the original's `Field.creation_counter`, the number a model's fields are ordered by ([A field: the base class](fields.md)).

Each copy of a relation declared on an abstract base is completed for the class it lands on, where that class is not abstract, so one declaration becomes a separate relation for each such child (`django/db/models/fields/related.py:RelatedField.contribute_to_class`) ([Relations: a field, its rel and the class at the other end](../relations/fields.md)).

### Overriding a field, and dropping one

A field of an abstract base is copied only if its name passes three tests, and the first two are how a child declines a field (`django/db/models/base.py:ModelBase.__new__`).

The name must not be the name of a field the child's own body declared. A child that declares a field under the same name keeps its own, and that is how an inherited field is overridden.

The name must not be a key of the child's own `__dict__`. A body that assigns something other than a field to the name, `None` by custom, has put an ordinary attribute there, and the field is dropped: the child has no field of that name. The same test passes over a field of a later base when a field copied from an earlier one has left a descriptor under the name.

The third test is about what stands ahead of the abstract base in the method resolution order. Take a child of Named whose bases are a mixin, a class that is not a model, and then Named, where the mixin has an attribute called `"name"`. The loop notes every name in the mixin's `__dict__` as it passes it, and does not copy a field of a later abstract base under a noted name: the child gets no field `"name"`. With the bases written the other way round, Named is reached first and the field is copied. The names of the local fields of a direct base that has a table are noted in the same way.

### Private fields

A **private field** is one that joined its class with `private_only=True` and is kept in `Options.private_fields`, apart from the others; `GenericForeignKey` and `GenericRelation` add themselves so ([Generic foreign keys: `GenericForeignKey`](../contrib/generic-foreign-key.md)). Such a field is copied from a base whether or not the base is abstract, and on a copy taken from a base with a table the metaclass sets `GenericRelation.mti_inherited`, which that class reads in order to give such a copy no reverse relation of its own (`django/db/models/base.py:ModelBase.__new__`, `django/contrib/contenttypes/fields.py:GenericRelation.contribute_to_class`).

### `Meta` travels as a class attribute

The settings in the `Meta` of an abstract base reach a child through a class attribute, not through the base's options. A class statement goes by the `Meta` of its body, or else by the attribute `Meta` that the new class inherits, and among models an abstract class is what supplies such an attribute: the metaclass keeps its `Meta` on the class, with `abstract` set back to false so that a child does not become abstract in its turn ([`ModelBase`: a class statement becomes a model](metaclass.md)). So Port, whose body has no `Meta`, goes by the `Meta` of Named, whole, and gets its ordering, while Ship, whose body has one, has Named's ordering because that `Meta` is written `class Meta(Named.Meta)` ([The options: what a model keeps as `_meta`](options.md)).

## A parent with a table: the link

When a base is a model that is not abstract, its fields stay where they are. The parent has a table; the child gets a table of its own, for its own fields; and one row of each makes up one object. Django's documentation calls this multi-table inheritance. What ties the two rows together is a **parent link**: a `OneToOneField` on the child, pointing at the parent, whose rel has `ForeignObjectRel.parent_link` set.

The metaclass records the arrangement in the child's `Options.parents`, a dictionary that leads from each parent model to the link for it (`django/db/models/base.py:ModelBase.__new__`, `django/db/models/options.py:Options`). For each direct base with a table it gets the link in one of two ways. It looks first for one that the class statement supplies: a `OneToOneField` declared with `parent_link=True`, in the child's own body or in an abstract base of the child, that points at that parent. Where there is none, the metaclass makes one. This is Officer's class statement from that point, without what the field does as it joins the class, and then the moment at which the registry completes the relation:

```text recording=models
OneToOneField.__init__(Sailor, on_delete=CASCADE, name='sailor_ptr', auto_created=True, parent_link=True)
ModelBase.add_to_class(Officer, 'sailor_ptr', a OneToOneField)
ModelBase._prepare(Officer)
  Options._prepare(Officer)
    Options.setup_pk(Officer.sailor_ptr)  ->  Options.pk is Officer.sailor_ptr
...
        resolve_related_class(Officer, Sailor, field=Officer.sailor_ptr)
          ForeignKey.contribute_to_related_class(Sailor, the rel of Officer.sailor_ptr)
            ForeignObject.contribute_to_related_class(Sailor, the rel of Officer.sailor_ptr)
              ReverseOneToOneDescriptor.__init__(the rel of Officer.sailor_ptr)
```

The field is made after the body's own fields are in place. Its target is the parent, or for a parent that is a proxy the model with a table that the proxy stands for; it is made with `on_delete=CASCADE` and `auto_created=True`, and its name is the target's model name with `"_ptr"` after it. From there it is a relation like any other: it has a column, `"sailor_ptr_id"`, and a descriptor under each of its two names; it waits in the registry for its two classes; and once Officer is registered it gives Sailor an accessor for the other end, `"officer"` ([Relations: a field, its rel and the class at the other end](../relations/fields.md)).

`Options._prepare` then makes the link the primary key. Finding that no field of the child has claimed to be one, and that the child has parents, it promotes the link to the first of them where it would otherwise have added an `"id"` (`django/db/models/options.py:Options._prepare`). The first is the first in `parents`, whose entries stand in the order in which the bases come in the method resolution order. An Officer has no key column of its own: the column that points at its Sailor is its key.

```text recording=models
editor.create_model(Officer)
  SQL CREATE TABLE "crew_officer" ("sailor_ptr_id" bigint NOT NULL PRIMARY KEY REFERENCES "crew_sailor" ("id") DEFERRABLE INITIALLY DEFERRED, "rank" varchar(10) NOT NULL)
```

```text recording=models
Officer._meta.parents  ->  {<class 'harbour.crew.models.Sailor'>: <django.db.models.fields.related.OneToOneField: sailor_ptr>}
Officer._meta.pk  ->  <django.db.models.fields.related.OneToOneField: sailor_ptr>
```

A child whose body declares a primary key of its own keeps it, and its link stays an ordinary unique column beside the key, as does the link to a second parent.

An abstract class may itself inherit from a model with a table. It is then given the link like any child, and carries it among its fields without ever having a table to put it in. A class that inherits from the abstract class gets a copy of the link along with the other fields, and the entry in its `parents` leads to the copy.

Officer is left with little in its own `__dict__`: descriptors for its own two fields, and none for `"name"`, `"ship"` or `"signed_on"`, which an Officer reads through the descriptors on Sailor.

```text recording=models
What the class Officer holds in its own __dict__, in the order the names were set
    __doc__: 'A sailor with a rank. A child with a table of its own: the rank is kept there.'
    _meta: an Options
    DoesNotExist: the class Officer.DoesNotExist
    MultipleObjectsReturned: the class Officer.MultipleObjectsReturned
    NotUpdated: the class Officer.NotUpdated
    rank: a DeferredAttribute
    get_rank_display: a partialmethod
    sailor_ptr_id: a ForeignKeyDeferredAttribute
    sailor_ptr: a ForwardOneToOneDescriptor
```

The link stands ahead of the fields of the child's body although it was made after them, a field made with `auto_created=True` being numbered from a second counter that runs below zero ([A field: the base class](fields.md)):

```text recording=models
names(Officer._meta.local_fields)  ->  [sailor_ptr, rank]
```

### What the metaclass refuses, and what it leaves to the checks

A field in the child's body raises `FieldError` while the class statement runs when it has the name of a field that a direct base with a table has among its own local fields, or of a private field of such a base; with an abstract base the same thing is an override. So does a link the metaclass has to make whose name is already the name of a field of the child.

The test on a body's field looks at the direct base's own fields and no further. A child that reuses the name of a field declared two levels up is made without complaint, and is reported afterwards, when the system checks run `Model._check_field_name_clashes`, whose docstring states the rule: field shadowing is forbidden in multi-table inheritance (`django/db/models/base.py:Model._check_field_name_clashes`) ([The model checks](checks.md)).

### What else comes from the parent

The child's three exception classes are subclasses of those of each direct base that is a model and not abstract, so code that catches the Sailor's `Model.DoesNotExist` catches the Officer's as well, and the Veteran's (`django/db/models/base.py:ModelBase.__new__`) ([`ModelBase`: a class statement becomes a model](metaclass.md)).

A class that is not abstract takes two settings from the options of the nearest model among its bases, when that one is not abstract either and the `Meta` the class goes by does not give them: `"ordering"` and `"get_latest_by"`. A proxy takes them in the same way.

The managers of a parent reach a child by a route of their own: the metaclass adds none of them to the child, and none is in the child's `Options.local_managers`. The child's managers are found by a walk over its method resolution order that takes in abstract bases, parents with tables and the model behind a proxy alike, and `ModelBase._prepare` gives a class the automatic `"objects"` only when that walk finds none, which is why Officer's class statement adds none (`django/db/models/base.py:ModelBase._prepare`) ([Managers](managers.md)).

## A proxy: another class over the same rows

A **proxy** is a model whose `Meta` says `proxy = True`. It adds nothing to the database. It is a second Python class for the rows of a model that already has a table, with methods, managers and `Meta` settings of its own. Veteran is Sailor's rows with a different default manager.

The metaclass checks a proxy's bases, and each failure is a `TypeError`. The nearest model among them must not have been swapped for another by a setting ([The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`](../auth/user-model.md)). An abstract base of the proxy must have nothing in its `Options.fields`, a list without many-to-many fields; one that has nothing there is passed over. There must be a base that is a model and not abstract. And where there are several, all of them must lead to one model with a table: that model itself, or proxies of it (`django/db/models/base.py:ModelBase.__new__`, `django/db/models/options.py:Options.fields`).

Then it sets the proxy up. `Options.setup_proxy` gives the proxy's options the primary key of the base, which is the base's own field object, and the name of the base's table, and records the base as `Options.proxy_for_model`. The metaclass adds one more thing, `Options.concrete_model`: the **concrete model** of a class that is not a proxy is the class itself, and that of a proxy is the concrete model of its base. A proxy may inherit from a proxy. Its `proxy_for_model` is then the proxy it was declared on, and its `concrete_model` the model at the end of the chain, the one whose table they all share (`django/db/models/options.py:Options.setup_proxy`). In Veteran's class statement the call is made on the options of Veteran, and Sailor in its brackets is the argument:

```text recording=models
Options.setup_proxy(Sailor)
ModelBase._prepare(Veteran)
  Options._prepare(Veteran)
  signal class_prepared, sender Veteran
Apps.register_model('crew', Veteran)
```

```text recording=models
Ship._meta.concrete_model.__name__, Veteran._meta.concrete_model.__name__, Veteran._meta.proxy_for_model.__name__  ->  ('Ship', 'Sailor', 'Sailor')
Veteran._meta.db_table, Veteran._meta.pk is Sailor._meta.pk  ->  ('crew_sailor', True)
```

The metaclass makes no link for a proxy, and puts `None` in its entry in `parents` where it would have made one. `Options._prepare` finds the key already set and adds none. Veteran's fields are those of its base, reached through `parents`:

```text recording=models
names(Veteran._meta.local_fields), names(Veteran._meta.fields)  ->  ([], [id, name, ship, signed_on])
```

The metaclass does not itself refuse a field in a proxy's body. Such a field is entered in the proxy's options like any other, and it is the system check `Model._check_model` that reports it (`django/db/models/base.py:Model._check_model`).

A proxy is registered like any model. What it does not get is a table: `Options.can_migrate` answers false for a proxy, and `Operation.allow_migrate_model`, which an operation such as `CreateModel` asks before it makes a table, rejects a model for which the answer is false (`django/db/models/options.py:Options.can_migrate`, `django/db/migrations/operations/base.py:Operation.allow_migrate_model`).

## The lists of ancestors

The options answer several questions about a model's ancestors (`django/db/models/options.py:Options`). Here an ancestor is a model with a table: an abstract base is in none of these lists, and a proxy is stood for by its concrete model.

| asked of a model's options | what it answers | among those who ask |
|---|---|---|
| `Options.parents` | the models with tables that the class inherits from directly, or through an abstract base, each with the link to it, or `None` for a proxy that declares no link | `Model._save_parents` and `Collector.collect`, which go up a level at a time by the links |
| `Options.all_parents` | every ancestor at any distance, as a tuple: the direct ones, then those of each | the unique checks of validation and `Model._check_field_name_clashes`, which go through the whole ancestry at once |
| `Options.get_parent_list` | the same, as a list; its docstring calls it a backward compatibility method | |
| `Options.get_base_chain` | given an ancestor, the models to go through to reach it, nearest first and the ancestor last; an empty list for a model that is not an ancestor | `Query.join_parent_model` |
| `Options.get_ancestor_link` | given an ancestor, the link that starts the way to it: the link to the ancestor itself, or to the parent it is reached through; `None` for a model that is not an ancestor, and for a proxy asked about the model it stands for | `Query.join_parent_model`, `DeferredAttribute._check_parent_chain` |
| `Options.get_path_to_parent` | given an ancestor, the joins from this model's table to its table, a `PathInfo` for each link on the way and none for a proxy | `Query.names_to_path` |
| `Options.get_path_from_parent` | the same joins in the other direction, from the ancestor's table down to this model's | `ManyToManyField._get_path_info` |

*What the options of a model say about its ancestors.*

For Officer and Veteran, which have one ancestor:

```text recording=models
names(Officer._meta.all_parents), Officer._meta.get_ancestor_link(Sailor)  ->  ([Sailor], <django.db.models.fields.related.OneToOneField: sailor_ptr>)
names(Sailor._meta.all_parents), names(Veteran._meta.all_parents)  ->  ([], [Sailor])
```

```text recording=models
hops(Officer._meta.get_path_to_parent(Sailor))  ->  [Officer to Sailor, join_field Officer.sailor_ptr, direct=True, m2m=False]
```
