---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Relations: a field, its rel and the class at the other end

A relation field, a `ForeignKey` or a `OneToOneField`, is a field with a column that also carries a second object, its rel, a `ForeignObjectRel`, and that has to put an attribute on a class other than its own. It does that through a function that it leaves with the app registry, by `lazy_related_operation` and `Apps.lazy_model_operation`, and that the registry calls when both classes of the relation are registered, whichever of them is declared first.

A relation is one fact about two classes, and it is written in one of them. The line `home = models.ForeignKey(Port, ...)` in the body of Ship says something about Port as much as about Ship: a port has ships. So the field has work to do in two places. On its own class it is a field like any other, with a column, and it leaves the means of reading a Port where the body wrote `"home"`. On Port it has to leave an attribute to come back by, and a name that a query starting from Port can follow.

The second half cannot be done where the field is declared. The class the field is declared in is still being put together at that moment, and the class it points at may not exist at all: a model can name its target by a string, and has to where the target's module has not been imported yet.

Django's answer has two parts. A relation is two objects from the moment the field is made: the field, and a **rel** that holds what the relation looks like from the other model. And the half of the work that concerns the other class is a function, left with the app registry, which the registry calls when both classes are in it.

The examples are three relations of the chapter's shipping line ([Models and fields](../models.md)):

```python
# harbour/fleet/models.py, in the body of Ship
home = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ships")
captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")

# harbour/fleet/models.py, in the body of Voyage
ship = models.ForeignKey(Ship, on_delete=models.CASCADE)
```

## The classes, and what each adds

The relation fields are built in layers, each a subclass of the one before (`django/db/models/fields/related.py`).

| class | its rel is a | what it adds to the class above |
|---|---|---|
| `RelatedField` | | It keeps the arguments that name the other side, resolves those names, and leaves the wiring with the registry. `RelatedField.db_type` returns `None`: of itself a relation has no column |
| `ForeignObject` | `ForeignObjectRel` | A relation to one object, over one or more pairs of fields. It still has no column of its own |
| `ForeignKey` | `ManyToOneRel` | One column of its own: an attname that ends `"_id"`, a type taken from the field it points at, an index, a constraint |
| `OneToOneField` | `OneToOneRel` | `unique=True`, always. With that, the other end is one object where a foreign key has many, so it names other descriptor classes |

*The relation fields that point at one object. From `ForeignObject` down, each has the class of its rel as `ForeignObject.rel_class`, and the classes of its two descriptors as `ForeignObject.forward_related_accessor_class` and `ForeignObject.related_accessor_class`.*

`ManyToManyField` is the other subclass of `RelatedField`. It has no column at all, and its rel is a `ManyToManyRel` ([Many-to-many relations](many-to-many.md)). The link from a child model to a parent that has a table is a `OneToOneField` that the metaclass makes when neither the body nor an abstract base of the class declares one ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)).

## The rel: the same relation seen from the other model

A relation field makes its rel in its own `__init__`. `ForeignKey.__init__` builds an object of the class named by `rel_class`, giving it the field itself and the target, and passes it up to `Field.__init__`, which stores it as `Field.remote_field` and sets `Field.is_relation` according to whether there is one (`django/db/models/fields/related.py:ForeignKey.__init__`, `django/db/models/fields/__init__.py:Field.__init__`). From then on each of the two holds the other, the field as the rel's `ForeignObjectRel.field`. In the recorded lines, home is the field that Ship declares under that name:

```text recording=models
home.remote_field  ->  <ManyToOneRel: fleet.ship>
type(home.remote_field).__name__, home.remote_field.field is home  ->  ('ManyToOneRel', True)
home.remote_field.model, home.related_model, home.remote_field.related_model  ->  (<class 'harbour.fleet.models.Port'>, <class 'harbour.fleet.models.Port'>, <class 'harbour.fleet.models.Ship'>)
home.many_to_one, home.remote_field.one_to_many, home.remote_field.multiple  ->  (True, True, True)
```

The rel holds what belongs to the relation and not to the column: the target, as `ForeignObjectRel.model`; the names the other side goes by, `related_name` and `related_query_name`; `on_delete`, which the collector of a deletion reads from it ([Deleting: the `Collector`](deleting.md)); `limit_choices_to`, a condition, or a function that returns one, which narrows the rows a form field offers for the relation and the rows `ForeignKey.validate` accepts; whether the relation is the link to a parent, `parent_link`; and `ForeignObjectRel.multiple`, which says whether the other end may hold several objects and which `OneToOneRel` alone sets false. A `ManyToOneRel` also gives a value to `ForeignObjectRel.field_name`, which the base class only ever sets to `None`: the name of the field in the target that the column points at (`django/db/models/fields/reverse_related.py:ForeignObjectRel`).

The rel is also made to answer what a field answers, with the two models exchanged. Seen from the field, the related model is Port. Seen from the rel it is Ship: `ForeignObjectRel.related_model` is the model that declares the field, which is also why the rel prints with Ship's label. Its `remote_field` is the field, it has a `name`, and it carries as class attributes the flags that code which walks a model's fields reads: `auto_created`, `concrete`, `editable`, `is_relation` and `null`. Its four flags of kind, `many_to_many`, `many_to_one`, `one_to_many` and `one_to_one`, are read from the field's, with `many_to_one` and `one_to_many` exchanged: the rel of a field that is `many_to_one` is `one_to_many`, as the last recorded line shows.

That is so the rel can stand in the other model's lists of fields. The options of Ship return the rels of the relations that point at Ship, and the options of either model find one by name:

```text recording=models
names(Ship._meta.related_objects)  ->  [voyage, crew]
...
Ship._meta.get_field('crew')  ->  <ManyToOneRel: crew.sailor>
Port._meta.get_field('ships')  ->  <ManyToOneRel: fleet.ship>
```

Nothing the relation did put the rel into those lists: no list of fields in the options of Port is added to when Ship is declared. `Options.get_fields`, asked about Port, works the answer out: it goes through every model in the registry, takes each relation field whose target is Port, and returns that field's rel (`django/db/models/options.py:Options._populate_directed_relation_graph`, `django/db/models/options.py:Options._get_fields`). The answer is kept until a field is added or, once the registry is ready, a model is registered ([The options: what a model keeps as `_meta`](options.md)).

The module's docstring says that rel objects act as reverse fields for the purposes of the options because they are the closest concept available, and the docstring of `ManyToOneRel` says that rels are somewhat abused in being used so, which gives the odd result that a `ManyToOneRel` is not `many_to_one` but `one_to_many`.

## The target: a class, a string or `"self"`

`ForeignKey.__init__` takes its target as a model class or as a string, and raises `TypeError` for anything else. A string is one of three things: `"self"`, for a relation of a model to itself; the name of a model, which is taken to be in the declaring model's own application; or an application's label and a model's name with a dot between.

The target is not resolved in `__init__`. A field does not yet know which class it will be on, and two of the three forms mean nothing without that. `resolve_relation` is given the declaring class as well: a class comes back as it is, `"self"` becomes the declaring class, and a bare name gets the label of the declaring model's application in front (`django/db/models/fields/related.py:resolve_relation`). Neither a class nor a string is looked up here. `make_model_tuple` then turns either into the pair the registry keeps models under, the application's label and the model's name in lower case, so the model's name in a string is matched without regard to case (`django/db/models/utils.py:make_model_tuple`).

Until the wiring is done the rel's `model` is whatever was written: for `"captain"`, the string `"crew.Sailor"`.

## The wiring: two class statements and a waiting list

A relation is wired when both of its classes are in the app registry, and which class statement that happens in depends on their order.

The harbour's models are made in the order of its three applications: Port, Ship and Voyage of the fleet (the first two after Named, their abstract base, and with the model Django makes for Voyage's calls inside Voyage's statement), then Sailor and its two subclasses in the crew, then the models of the office ([`ModelBase`: a class statement becomes a model](metaclass.md) has the recording). So when the statement of Ship runs, Port exists and Sailor does not. Ship's two relations are wired at different moments for that reason, and by the same code.

### What the field does in its own class statement

The metaclass hands each field of the body to the class. For a relation, three methods named `contribute_to_class` run, each calling the one beneath it before doing its own part. This is the statement of Ship at `"home"`, and after it the three lines of `"captain"` that concern its target:

```text recording=models
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
      lazy_related_operation(resolve_related_class, Ship, 'crew.Sailor')
        Apps.lazy_model_operation(function, ('fleet', 'ship'), ('crew', 'sailor'))
        -> Apps._pending_operations holds 2 under ('fleet', 'ship')
```

The innermost, `Field.contribute_to_class`, does what it does for any field. It enters the field in the options of Ship, in `Options.local_fields`, records Ship as the field's `Field.model`, and sets a descriptor on Ship under the attname, `"home_id"`. The descriptor's class is the field's `Field.descriptor_class`, which `ForeignKey` sets to `ForeignKeyDeferredAttribute` (`django/db/models/fields/__init__.py:Field.contribute_to_class`, `django/db/models/options.py:Options.add_field`).

The outermost, `ForeignObject.contribute_to_class`, sets a second descriptor on Ship, under the field's own name: an object of `forward_related_accessor_class`, made with the field. That is the attribute which gives a Port (`django/db/models/fields/related.py:ForeignObject.contribute_to_class`).

Between them, `RelatedField.contribute_to_class` does the part that makes a relation. It settles the names the other side will go by. Then it defines a function, `resolve_related_class`, and does not call it. It gives the function to `lazy_related_operation`, with the declaring class, the target as it was written, and the field (`django/db/models/fields/related.py:RelatedField.contribute_to_class`). `lazy_related_operation` passes the target through `resolve_relation`, makes a key of the declaring class and a key of the target, and hands the function and the keys to the registry that the declaring class's options name (`django/db/models/fields/related.py:lazy_related_operation`).

For a class that is abstract the method does neither: no name is settled and nothing is left with the registry. A class that has the abstract class among its bases gets a copy of it, unless its own body, or a class before that base in its method resolution order, has already given it an attribute of the field's name (`django/db/models/base.py:ModelBase.__new__`). `Field.__deepcopy__` makes the copy, with a copy of the rel that points back at the new field. Where that class is not abstract, the copy does this work for it (`django/db/models/fields/__init__.py:Field.__deepcopy__`).

### `Apps.lazy_model_operation`: one key at a time

`Apps.lazy_model_operation` takes a function and any number of keys, and deals with the first key only. If a model is registered under it, the method binds that class as the function's next argument and calls itself with the keys that remain. If none is, it puts into `Apps._pending_operations`, under that key, a function that will do the same once it is handed the class. With no key left, it calls the function (`django/apps/registry.py:Apps.lazy_model_operation`).

The declaring model's key is always the first, and while its statement runs nothing is registered under that key, unless the model has been declared before, which the registry warns of: registering is the last thing `ModelBase.__new__` does. So, that case apart, a function that a field leaves during the class statement does not run while the field is being added, whatever the target is: the earliest it can run is as the declaring class is registered, at the end of the statement. The counts in the recording show it. After `"home"`, whose target has been registered for some time, one function waits under `("fleet", "ship")`, and after `"captain"` there are two.

### When both classes are registered

`Apps.register_model`, once it has stored the class, calls `Apps.do_pending_operations`, which takes whatever waits under the new class's key and calls each function with the class (`django/apps/registry.py:Apps.do_pending_operations`). This is the end of the statement of Ship:

```text recording=models
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

Of the two functions that waited, the one of `"home"` finds Port registered and runs, and the one of `"captain"` goes back onto the list under `("crew", "sailor")`.

`resolve_related_class` does two things. It stores the target class as the rel's `model`, in place of whatever was written. And it calls `RelatedField.do_related_class`, which first settles the rel's `field_name`. `ForeignKey.__init__` gave the rel the name written as `to_field="..."` or, with none written and a class for the target, the name of that class's primary key. With none written and a string for the target it gave `None`, and `ManyToOneRel.set_field_name` now puts the name of the target's primary key in its place. `do_related_class` then calls the field's `contribute_to_related_class` with the target class and the rel (`django/db/models/fields/related.py:RelatedField.do_related_class`, `django/db/models/fields/reverse_related.py:ManyToOneRel.set_field_name`).

`ForeignObject.contribute_to_related_class` is where the other class is changed. It makes an object of `related_accessor_class` with the rel and sets it on the target under the rel's `ForeignObjectRel.accessor_name`: on Port, a `ReverseManyToOneDescriptor` under `"ships"`. It sets it on the concrete model of the target, so a relation that points at a proxy puts its attribute on the model the proxy stands for. It sets nothing when the rel is hidden, or when the model that declares the field has been swapped for another (`django/db/models/fields/related.py:ForeignObject.contribute_to_related_class`). `ForeignKey.contribute_to_related_class` calls it, and afterwards sets the rel's `field_name` to the name of the target's primary key if it is `None`, which for a `ManyToOneRel` it no longer is once `set_field_name` has run.

The function that `"captain"` left waits through the rest of the fleet's module. It runs in another module, at the beginning of what the registering of Sailor sets off:

```text recording=models
Apps.register_model('crew', Sailor)
  Apps.do_pending_operations(Sailor)
    Apps.lazy_model_operation(function)
      resolve_related_class(Ship, Sailor, field=Ship.captain)
        ForeignKey.contribute_to_related_class(Sailor, the rel of Ship.captain)
          ForeignObject.contribute_to_related_class(Sailor, the rel of Ship.captain)
            ReverseOneToOneDescriptor.__init__(the rel of Ship.captain)
```

The attribute `"command"` of Sailor is set as Sailor's own statement ends, by a field of another class in another application. Sailor's own foreign key to Ship, written with the string `"fleet.Ship"` though Ship existed, is wired next, in lines not quoted: a string and a class take the same road.

```text figure=one-relation
Two relations that the body of Ship declares, after every class statement has run.

home = ForeignKey(Port, related_name="ships")

    the class Ship                                          the class Port
      home_id   ForeignKeyDeferredAttribute                   ships   ReverseManyToOneDescriptor
      home      ForwardManyToOneDescriptor
      _meta.local_fields holds the field                      _meta.get_fields() finds the rel

      the field, a ForeignKey     remote_field ->  <- field     the rel, a ManyToOneRel
        name "home", attname "home_id"                          model Port, related_model Ship
        model Ship                                              related_name "ships", field_name "id"

    set while the body of Ship is dealt with:   home_id, home, the entry in local_fields
    set as Ship is registered, Port being there already:   ships, on Port

captain = OneToOneField("crew.Sailor", related_name="command")

    the class Ship                                          the class Sailor
      captain_id   ForeignKeyDeferredAttribute                command   ReverseOneToOneDescriptor
      captain      ForwardOneToOneDescriptor

    set while the body of Ship is dealt with:   captain_id, captain, the entry in local_fields
    set as Sailor is registered, in the crew's module:   command, on Sailor
    between the two, the rel's model is the string "crew.Sailor"
```

*One relation is two objects, and three attributes on two classes. The declaring class gets its two attributes during its own statement; the other class gets its one when both classes are in the registry, which for a target not yet imported is during a later statement.*

### What follows from the waiting

Two models may point at each other, across modules and applications: each relation is completed when the second of its classes is registered.

Until then the relation is half made. Where the target was written as a string, the rel's `model` is still that string, and the parts of the field that need the class say so if they are asked: `ForeignObject.resolve_related_fields` raises `ValueError` with the message that the related model cannot be resolved, and `ForeignKey.formfield` raises one saying that the related model has not been loaded yet.

A relation to a model that is never registered raises nothing. Its function stays in `Apps._pending_operations`, the rel's `model` stays as it was written, and no class statement fails. The mistake is found by a system check that reads what is left on that list ([The model checks](checks.md)).

A many-to-many field leaves a second function on the same list, for its through model ([Many-to-many relations](many-to-many.md)), and a model signal connected to a sender named by a string waits on it too.

## The names each side goes by

Each side of a relation needs a word for the other, and needs it for two uses: as an attribute of an instance, and as a word in a query. On the declaring side both are the field's name. On the other side the two words can differ, and the rel answers for both. Here ship is the foreign key of Voyage, which was given no `related_name`:

```text recording=models
home.remote_field.related_name, home.remote_field.get_accessor_name(), home.related_query_name()  ->  ('ships', 'ships', 'ships')
ship.remote_field.related_name, ship.remote_field.get_accessor_name(), ship.related_query_name()  ->  (None, 'voyage_set', 'voyage')
```

The **accessor** is the attribute on the other class. For the rel of a foreign key or a one-to-one field, `ForeignObjectRel.get_accessor_name` returns the rel's `related_name` when it has one. Otherwise it is the declaring model's name in lower case, with `"_set"` after it when the rel's `multiple` is true: a ship's voyages are `"voyage_set"`, and the one Officer that a Sailor may be is `"officer"` (`django/db/models/fields/reverse_related.py:ForeignObjectRel.get_accessor_name`).

The name for queries is `RelatedField.related_query_name`: the rel's `related_query_name` if one was given, else its `related_name`, else the declaring model's name in lower case, with nothing after it (`django/db/models/fields/related.py:RelatedField.related_query_name`). This is also the rel's `name`, the one the options know it by. So the far end of Voyage's foreign key is the attribute `"voyage_set"` of a ship, and it is the field `"voyage"` in the options of Ship and in a filter on ships.

A `related_name` that ends in `"+"` asks for no way back: `ForeignObjectRel.hidden` is true for such a rel, `contribute_to_related_class` sets no attribute for it, and the options leave it out of a model's fields unless they are asked to include hidden ones ([The options: what a model keeps as `_meta`](options.md)).

The names are settled by `RelatedField.contribute_to_class`, for a class that is not abstract (`django/db/models/fields/related.py:RelatedField.contribute_to_class`). A field with no `related_name` takes the `Options.default_related_name` of its model, if `Meta` gave one (`django/db/models/options.py:Options.contribute_to_class`). The name is then filled in from the declaring class, which for a copy of an abstract class's field is the class that got the copy: `"%(class)s"` becomes the class's name in lower case, `"%(model_name)s"` the model's name and `"%(app_label)s"` the application's label. A `related_query_name` is filled in with the first and the last of those. The results are stored on the rel. The field keeps the argument as it was written, and that is what `RelatedField.deconstruct` returns.

Two relations whose names collide on one class, or a name that collides with a field, raise nothing here either. They are reported by the checks ([The model checks](checks.md)).

## The column of a foreign key

`ForeignKey.get_attname` returns the field's name with `"_id"` after it, and `ForeignKey.get_attname_column` gives the column the same name unless `db_column="..."` was given (`django/db/models/fields/related.py:ForeignKey.get_attname`). The options know the field by both of its names, so `"home_id"` is as good as `"home"` wherever a field is looked up by name (`django/db/models/options.py:Options._forward_fields_map`).

The column points at one field of the target, `ForeignKey.target_field`. That is the target's primary key, unless the field was made with `to_field="..."` naming another, which the checks expect to be unique ([The model checks](checks.md)). The column's type and the handling of its values are borrowed from that field.

The type is. `ForeignKey.db_type` returns the target field's `Field.rel_db_type`, the type that a column pointing at it should have: for a `BigAutoField`, the type of a `BigIntegerField` (`django/db/models/fields/__init__.py:Field.rel_db_type`) ([A field: the base class](fields.md)).

The values are. `ForeignKey.get_prep_value`, `ForeignKey.get_db_prep_value` and `ForeignKey.get_db_prep_save` each hand the value to the same method of the target field, so a key on its way to the database is prepared as the target's own column would prepare it. `get_db_prep_save` first turns `None` into a null, and also an empty string, where the target field does not allow empty strings or the backend reads them as null. `ForeignKey.to_python` is the target's as well (`django/db/models/fields/related.py:ForeignKey.get_db_prep_save`).

The reference and the index are the foreign key's own doing, and the tables the harbour's models were given show both:

```text recording=models
editor.create_model(Ship)
  SQL CREATE TABLE "fleet_ship" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(60) NOT NULL, "tonnage" integer unsigned NOT NULL CHECK ("tonnage" >= 0), "home_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED, "captain_id" bigint NULL UNIQUE REFERENCES "crew_sailor" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "ship_has_tonnage" CHECK ("tonnage" > 0), CONSTRAINT "one_name_to_a_port" UNIQUE ("name", "home_id"))
...
SQL CREATE INDEX "fleet_ship_home_id_12c4d51a" ON "fleet_ship" ("home_id")
```

The constraint is there because `ForeignKey.db_constraint` is true unless the field was made with `db_constraint=False`: the schema editor writes the reference to the other table only for a relation field that has it true (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.table_sql`). And the index is there because `ForeignKey.__init__` asks for one, setting `db_index=True` where the caller said nothing. The base schema editor makes an index for a field that asks for one and is not unique, which is why `"home_id"` has one and `"captain_id"`, unique already, has none (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._field_should_be_indexed`). A backend's editor may decide otherwise ([The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md#the-backends-editors)).

A foreign key also validates against the other table. `ForeignKey.validate` runs a query: it looks, through the target's base manager, for a row with that value, and raises `ValidationError` when there is none (`django/db/models/fields/related.py:ForeignKey.validate`) ([Validating an instance](validation.md)).

## Several columns: `ForeignObject`

A `ForeignKey` is the special case of a more general field, which its docstring calls an abstraction of the foreign key to support relations of several columns. Besides `ForeignKey`, one other class in Django has it as a base, `GenericRelation`, the reverse of a generic foreign key, in what its source calls somewhat of an abuse of `ForeignObject`: it leads to many objects and resolves its pair of fields itself (`django/contrib/contenttypes/fields.py:GenericRelation`). Of itself a `ForeignObject` relates two rows by one or more pairs of fields, named in `ForeignObject.from_fields` and `ForeignObject.to_fields`. The names are resolved into `ForeignObject.related_fields`, a list of pairs, each a field of the declaring model and a field of the target (`django/db/models/fields/related.py:ForeignObject.resolve_related_fields`).

A `ForeignObject` has no column of its own. `ForeignObject.get_attname_column` returns no column, so the field is not concrete and gets no descriptor under an attname. The fields it relates through are other fields of its model (`django/db/models/fields/related.py:ForeignObject.get_attname_column`).

`ForeignKey.__init__` fixes the two lists to one entry each. `from_fields` is `["self"]`, which in this list means the field itself. `to_fields` holds the one name of the field pointed at, or `None`, which stands for the target's primary key. So a foreign key's `related_fields` is a single pair, for `"home"` the field itself and the `"id"` of Port, and `ForeignKey.target_field` is the second member of it (`django/db/models/fields/related.py:ForeignKey.__init__`).

The descriptors are written against the pairs and not against one column. They read `ForeignObject.get_local_related_value` and `ForeignObject.get_foreign_related_value`, each a tuple with a value for every pair, and a join takes all the pairs from `ForeignObject.get_joining_fields` (`django/db/models/sql/datastructures.py:Join.__init__`). A `ForeignKey` goes through the same code with a list of one.

## `PathInfo`: what a query follows

A query that crosses a relation needs to know which table to join and on what. A relation field answers with `ForeignObject.path_infos`, a list of `PathInfo` tuples, one for each join. A tuple holds, among other things, the options of the model the hop leaves and of the one it reaches, the field to join on and two flags (`django/db/models/query_utils.py:PathInfo`, `django/db/models/fields/related.py:ForeignObject.get_path_info`). `ForeignObject.reverse_path_infos` is the same relation crossed the other way, and it is what the rel gives as its own path.

```text recording=models
hops(home.path_infos)  ->  [Ship to Port, join_field Ship.home, direct=True, m2m=False]
hops(home.reverse_path_infos)  ->  [Port to Ship, join_field the rel of Ship.home, direct=False, m2m=True]
```

The hop from the declaring model is made with `direct=True` and `m2m=False`, and the hop back with `direct=False`, and with `m2m=True` unless the field is unique: so for a foreign key that is not unique, and not for a one-to-one field (`django/db/models/fields/related.py:ForeignObject.get_reverse_path_info`). `Query.names_to_path` strings the hops of each name in a filter together, and `Query.setup_joins` makes a join of each (`django/db/models/sql/query.py:Query.setup_joins`) ([From QuerySet to SQL](../sql.md)).

## A target that a setting can replace

The target of a relation may be a model that a setting can replace with another, as the user model can be ([Authentication, sessions and messages](../auth.md)). `ForeignObject.swappable` is true unless the field was made with `swappable=False`. `RelatedField.swappable_setting` then asks the registry whether the target is a model that can be swapped, or the model that has been swapped in for one, and gets the setting's name if it is (`django/apps/registry.py:Apps.get_swappable_settings_name`). `ForeignObject.deconstruct` uses the answer. For such a target the `"to"` it returns is a `SettingsReference`, a subclass of `str` that carries the setting's name beside the label; its docstring says that it is treated as the value in memory and serializes to a reference to the setting (`django/conf/__init__.py:SettingsReference`). For any other target that has been resolved, `"to"` is the label in lower case. `ForeignKey.deconstruct` trims what its base returned to what a caller would have written (`django/db/models/fields/related.py:ForeignKey.deconstruct`).
