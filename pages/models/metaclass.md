---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `ModelBase`: a class statement becomes a model

`ModelBase` is the metaclass of every model, and its `__new__` is where a class statement is turned into a model class. By the time that one method returns, a class that is not abstract has an options object, a descriptor for each field, three exception classes, a primary key and a manager whether or not its body declared them, and a place in the app registry.

A class statement in Python ends with a call. The body runs first, as a function whose local variables are collected in a dictionary, and then the metaclass is called with the class's name, its bases and that dictionary. For most classes the metaclass is `type`, which makes a class of exactly what it was given. `Model` is declared with `metaclass=ModelBase`, so every class that has a model among its bases is made by `ModelBase.__new__` instead (`django/db/models/base.py:Model`, `django/db/models/base.py:ModelBase.__new__`).

That method does its work in a fixed order, and later steps rely on what earlier ones left, so they are told here in that order.

```text figure=the-stages
ModelBase.__new__, for a class with a model among its bases. Each stage, and what the class has after it.

1  the bare class             type.__new__, with the attributes that are not held back
2  the options                an Options, made from Meta and the app's label, installed as _meta
3  the exception classes      DoesNotExist, MultipleObjectsReturned, NotUpdated     (not for an abstract class)
4  the body's attributes      each field and manager is handed the class, in the order the body wrote them
5  the bases                  a proxy is set up; a link is made to a parent that is not abstract; an abstract base's fields are copied

   an abstract class is returned here

6  ModelBase._prepare         a primary key if none was declared, a manager if none was declared, and the signal class_prepared
7  Apps.register_model        the class is entered in the registry, and what was waiting for it runs

An abstract class has no third stage, and none after the fifth.
```

*The stages of `ModelBase.__new__`. An abstract class leaves after the fifth: it is never prepared and never registered.*

## What runs `ModelBase.__new__`, and when

Every class statement with a model among its bases runs `ModelBase.__new__`, at the moment Python reaches the statement. For a project that is while its `models` modules are imported during start-up, each in the order of `settings.INSTALLED_APPS` unless a module imported earlier has already imported it ([Settings, apps and startup](../startup.md)). The harbour's three modules give this:

```text recording=models
django.setup(): the model classes, in the order their class statements ran
    ModelBase.__new__('Named', (Model,))
    ModelBase.__new__('Port', (Named,))
      Apps.register_model('fleet', Port)
    ModelBase.__new__('Ship', (Named,))
      Apps.register_model('fleet', Ship)
    ModelBase.__new__('Voyage', (Model,))
            ModelBase.__new__('Voyage_calls', (Model,))
              Apps.register_model('fleet', Voyage_calls)
      Apps.register_model('fleet', Voyage)
    ModelBase.__new__('Sailor', (Model,))
      Apps.register_model('crew', Sailor)
    ModelBase.__new__('Officer', (Sailor,))
      Apps.register_model('crew', Officer)
    ModelBase.__new__('Veteran', (Sailor,))
      Apps.register_model('crew', Veteran)
    ModelBase.__new__('Licence', (Model,))
      Apps.register_model('office', Licence)
    ModelBase.__new__('Manifest', (Model,))
      Apps.register_model('office', Manifest)
    ModelBase.__new__('Berth', (Model,))
      Apps.register_model('office', Berth)
    ModelBase.__new__('Logbook', (Model,))
      Apps.register_model('office', Logbook)
    ModelBase.__new__('LogEntry', (Model,))
      Apps.register_model('office', LogEntry)
```

Each line at the left is one class statement, and the line under it is that class entering the registry. Named has no such line, because it is abstract. One class has no statement at all: Voyage_calls is made in the middle of Voyage's, by a field, and is registered before Voyage is.

The class `Model` itself goes through the method too, and is let straight out of it. The first thing `ModelBase.__new__` does is look among the bases for an instance of `ModelBase`. Finding none, as it does for `Model` alone, it returns what `type.__new__` makes and does nothing else.

A model class cannot be made before the registry has its app configs. The method asks the registry which application the class's module belongs to, and `Apps.get_containing_app_config` begins by checking that the app configs are loaded, raising `AppRegistryNotReady` when they are not, or `ImproperlyConfigured` where the settings themselves are not configured (`django/apps/registry.py:Apps.get_containing_app_config`). So a module that declares models cannot be imported before the app configs are loaded: its first class statement would raise.

## The bare class

`ModelBase.__new__` does not hand the body's dictionary to `type.__new__` whole. Three entries are taken out by name: `"__module__"`, which is put straight back; `"__classcell__"`, which Python adds when a method of the body uses `super()` without arguments and which is passed on if present; and `"Meta"`, which is kept aside and is not set on the class. Every other entry is tested by `_has_contribute_to_class`, and only the ones that fail the test go into the class now (`django/db/models/base.py:_has_contribute_to_class`).

The test asks two things of a value: that it is not itself a class, and that it has an attribute named `contribute_to_class`. A field passes, and a manager. The first part is there because of what the method would be on a class: the source's comment says the method is to be called only when it is bound, and a method reached through a class and not through an instance is not bound. A field class assigned in a body without the parentheses that would make a field of it is therefore left as an ordinary attribute.

The reason for splitting before the class exists is in the source's own comment. `type.__new__` initialises the attributes it is given, which includes calling `__set_name__` on any descriptor among them. An attribute added to a class afterwards gets no such call. So everything that Django will not install itself is given to Python to install properly, and only the objects that know how to install themselves are held back.

Keyword arguments of the class statement are passed through to `type.__new__` as well, which hands them to `__init_subclass__`.

## The application, and the options

Before it installs anything on the new class, `ModelBase.__new__` reads three values: whether the body's `Meta` says `abstract = True`; the `Meta` to go by, which is the body's or else the attribute `Meta` that the new class inherits; and the options of a parent, found as the attribute `_meta` that the new class so far only inherits, from which a child of a parent with a table takes two settings a little later.

Then the class is given its application. The registry is asked for the app config whose package contains the class's module. If `Meta` supplies an `"app_label"`, that is the label and the registry's answer is not used. If it does not, the label is the config's, and a class whose module is in no installed application is refused, unless it is abstract:

```text recording=models
type('Tug', (models.Model,), {'__module__': 'elsewhere'})  ->  raises RuntimeError: Model class elsewhere.Tug doesn't declare an explicit app_label and isn't in an application in INSTALLED_APPS.
type('Tug', (models.Model,), {'__module__': 'elsewhere', 'Meta': type('Meta', (), {'abstract': True})}).__name__  ->  'Tug'
```

With the label settled, an `Options` is made from the `Meta` and the label and given to `ModelBase.add_to_class` under the name `"_meta"`. That method is short, and `ModelBase.__new__` uses it for what it adds from here on, the options, the exception classes, the attributes it held back and the fields it makes or copies: a value that passes `_has_contribute_to_class` has its `contribute_to_class` called with the class and the name, and any other value is set with `setattr` (`django/db/models/base.py:ModelBase.add_to_class`). The options object is of the first kind. Its own `contribute_to_class` binds it to the class, reads the `Meta`, and refuses a `Meta` with an attribute it does not know ([The options: what a model keeps as `_meta`](options.md)). Here a model named Wherry is declared in the fleet, with a `Meta` that sets an attribute named colour:

```text recording=models
declare('Wherry', colour='red')  ->  raises TypeError: 'class Meta' got invalid attribute(s): colour
```

The options come first because the fields need them. A field's `contribute_to_class` enters the field in the class's options, and there have to be options to enter it in.

## Three exception classes

A class that is not abstract is next given three exception classes of its own. Each is made by `subclass_exception` and added under its name (`django/db/models/base.py:subclass_exception`).

Their bases depend on the model's. Where the class has no direct base that is a model and not abstract, they are Django's general exceptions: `ObjectDoesNotExist`, `MultipleObjectsReturned`, and for the third both `ObjectNotUpdated` and `DatabaseError`. Where it has one or more, they are the corresponding classes of each of them:

```text recording=models
subclass_exception('DoesNotExist', (Sailor.DoesNotExist,))
ModelBase.add_to_class(Officer, 'DoesNotExist', the class Officer.DoesNotExist)
subclass_exception('MultipleObjectsReturned', (Sailor.MultipleObjectsReturned,))
ModelBase.add_to_class(Officer, 'MultipleObjectsReturned', the class Officer.MultipleObjectsReturned)
subclass_exception('NotUpdated', (Sailor.NotUpdated,))
ModelBase.add_to_class(Officer, 'NotUpdated', the class Officer.NotUpdated)
```

So catching the exception of a parent that is a direct base also catches the child's. Asked afterwards:

```text recording=models
[c.__name__ for c in Ship.DoesNotExist.__mro__]  ->  ['DoesNotExist', 'ObjectDoesNotExist', 'Exception', 'BaseException', 'object']
Ship.DoesNotExist.__module__, Ship.DoesNotExist.__qualname__  ->  ('harbour.fleet.models', 'Ship.DoesNotExist')
[c.__name__ for c in Ship.NotUpdated.__mro__]  ->  ['NotUpdated', 'ObjectNotUpdated', 'DatabaseError', 'Error', 'Exception', 'BaseException', 'object']
Officer.DoesNotExist.__bases__ == (Sailor.DoesNotExist,)  ->  True
```

The module and the qualified name in the second line are set on purpose. `subclass_exception` gives each class the model's module and a qualified name that begins with the model's, and its docstring gives the reason: an instance can then be pickled, the class being found again as an attribute of the model.

> **Changed in 6.0.** `Model.NotUpdated` is new. A save that was told to update and matched no row used to raise a plain `DatabaseError`; it now raises the model's own class, which still has `DatabaseError` among its bases so that code written to catch the old exception goes on working ([Saving an instance](saving.md)).

At the same point a class that is not abstract takes two settings from the options of the nearest model in its resolution order, if that model is not abstract, where the `Meta` it goes by does not give them: `"ordering"` and `"get_latest_by"`. This is how a child comes by the ordering of a parent that has a table. A child of an abstract base gets it by another route, with the base's `Meta`, as Port gets its ordering from Named.

## The body's attributes install themselves

The attributes that `ModelBase.__new__` held back are handed to `ModelBase.add_to_class`, one at a time, in the order the body assigned them. For Sailor, whose body declares a manager as well as four fields, the calls at this level are these, with everything nested under each left out:

```text recording=models
ModelBase.add_to_class(Sailor, 'name', a CharField)
...
ModelBase.add_to_class(Sailor, 'ship', a ForeignKey)
...
ModelBase.add_to_class(Sailor, 'signed_on', a DateTimeField)
...
ModelBase.add_to_class(Sailor, 'pilots_into', a ManyToManyField)
...
ModelBase.add_to_class(Sailor, 'objects', a ManagerFromSailorQuerySet)
...
ModelBase._prepare(Sailor)
```

What each object does with the class is its own affair: the loop that hands them over only calls `add_to_class`, and has no code about columns or descriptors. A field enters itself in the options and sets a descriptor (`django/db/models/fields/__init__.py:Field.contribute_to_class`) ([A field: the base class](fields.md)). A relation on a class that is not abstract also arranges to be told when the class it points at exists ([Relations: a field, its rel and the class at the other end](relations.md)). A manager sets a descriptor under its name and enters itself in the options' list of managers ([Managers](managers.md)). Anything else with a `contribute_to_class` method, of a project's or a library's making, is called in the same way and may do what it likes.

## The bases

With its own fields in place, a class is fitted by `ModelBase.__new__` to what it inherits from. A proxy is checked, since it needs a base that is not abstract, may not have two such bases of different concrete models, and may not have an abstract base with fields other than many-to-many ones, and is then pointed at the model it stands for. For each direct base that is a model and not abstract, a class that is not a proxy gets a link to it, or to the model it stands for where that base is a proxy: a `OneToOneField` that the metaclass makes when neither the body nor an abstract base declared one. For each base that is abstract, the fields the class does not already have are copied into it, each copy handed to `add_to_class` like a field of the body. Last, the indexes the options hold are copied, so that an index declared on an abstract base is a separate object, with a name of its own, on each class that inherits it. [Inheritance: abstract bases, parents with tables and proxies](inheritance.md) follows this part of the method closely.

## Where an abstract class stops

An abstract class is returned from `ModelBase.__new__` once its own fields and its bases have been dealt with. It is the shortest statement in the recording:

```text recording=models
The class statement of Named
    ModelBase.__new__('Named', (Model,))
      ModelBase.add_to_class(Named, '_meta', an Options)
        Options.contribute_to_class(Named, '_meta')
      ModelBase.add_to_class(Named, 'name', a CharField)
        Field.contribute_to_class(Named, 'name')  (a CharField)
          Options.add_field(Named.name)
          DeferredAttribute.__init__(Named.name)
```

It has options, with its field in them, and a descriptor for the field. It was given no exception classes, and it will get no primary key, no manager, no `class_prepared` signal and no entry in the registry.

Before returning it, the method does one thing to the body's `Meta`: it sets `abstract` on it to false, and puts it on the class as the attribute `Meta`. For an ordinary model the `Meta` was taken out of the body and discarded once read; for an abstract one it is kept. A class that inherits from Named and writes no `Meta` of its own therefore finds Named's by ordinary attribute lookup, as described above, and gets its ordering from it. It does not also become abstract, because that one attribute has been reset:

```text recording=models
hasattr(Named, 'DoesNotExist'), hasattr(Named, 'objects'), hasattr(Named, '_meta')  ->  (False, False, True)
Named.Meta.abstract, Named._meta.abstract  ->  (False, True)
Port.Meta is Named.Meta  ->  True
```

Being abstract is thus never inherited from a model. It is said in the body of each class it applies to, and recorded in that class's options.

## `_prepare`: what every model that is not abstract is given

A class that is not abstract goes on to `ModelBase._prepare`, a proxy included (`django/db/models/base.py:ModelBase._prepare`). This is the recording for Ship, whose body declared neither a key nor a manager:

```text recording=models
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
```

**A primary key.** `Options._prepare` looks at whether any field has claimed to be the primary key. If none has, and the model has a parent with a table, the link to the first such parent is promoted to primary key. Otherwise a field is made and added under the name `"id"`. Its class is found from a dotted path: the `AppConfig.default_auto_field` of the model's app config if the config sets one, and `settings.DEFAULT_AUTO_FIELD` otherwise (`django/db/models/options.py:Options._prepare`, `django/db/models/options.py:Options._get_default_pk_class`).

**A manager.** If the options hold no manager after all that, neither one of the body's nor one inherited, a `Manager` is made, marked `auto_created=True`, and added under the name `"objects"`. A model with a field of that name cannot be given it, and for such a model with no manager, its own or inherited, the method raises `ValueError` instead.

Between and after those two, the method does some smaller things. A model whose `Meta` gives `"order_with_respect_to"` gets two methods for stepping through its siblings, and the model it is ordered against gets a pair of methods for reading and setting the order, added through the registry since that class may not exist yet (`django/db/models/base.py:make_foreign_order_accessors`). A class with no docstring is given one made of its name and the names of its fields. A model whose label in lower case, `"fleet.ship"` for Ship, is a key of `settings.ABSOLUTE_URL_OVERRIDES` is given the function found there as its `get_absolute_url`. And each index that was declared without a name is named now, from the table and the fields, which could not be done earlier because the fields were not yet on the class (`django/db/models/indexes.py:Index.set_name_with_model`).

The last statement of `_prepare` sends `class_prepared`, with the class as sender. A receiver of that signal is handed a class that is complete in itself and not yet in the registry.

## Into the registry

The last thing `ModelBase.__new__` does before it returns the class is give it to the registry named in its options, which is the global one unless `Meta` said otherwise. `Apps.register_model` stores the class under its app's label and its own name in lower case, and then does two things for the rest of the system (`django/apps/registry.py:Apps.register_model`).

It calls every function that was waiting for this class. Functions come to be waiting through `Apps.lazy_model_operation`, which a relation uses to say: call this when these models exist (`django/apps/registry.py:Apps.lazy_model_operation`, `django/apps/registry.py:Apps.do_pending_operations`). The method takes a function and a list of models. It peels the first model off the list and calls itself with the rest once that model is registered, so in the recording it appears nested in itself, and a call of it with no model left is the function being run. This is the registration of Sailor:

```text recording=models
Apps.register_model('crew', Sailor)
  Apps.do_pending_operations(Sailor)
    Apps.lazy_model_operation(function)
      resolve_related_class(Ship, Sailor, field=Ship.captain)
        ForeignKey.contribute_to_related_class(Sailor, the rel of Ship.captain)
          ForeignObject.contribute_to_related_class(Sailor, the rel of Ship.captain)
            ReverseOneToOneDescriptor.__init__(the rel of Ship.captain)
    Apps.lazy_model_operation(function, ('fleet', 'ship'))
      Apps.lazy_model_operation(function)
        resolve_related_class(Sailor, Ship, field=Sailor.ship)
          ForeignKey.contribute_to_related_class(Ship, the rel of Sailor.ship)
            ForeignObject.contribute_to_related_class(Ship, the rel of Sailor.ship)
              ReverseManyToOneDescriptor.__init__(the rel of Sailor.ship)
    Apps.lazy_model_operation(function, ('fleet', 'port'))
      Apps.lazy_model_operation(function)
        resolve_related_class(Sailor, Port, field=Sailor.pilots_into)
          ManyToManyField.contribute_to_related_class(Port, the rel of Sailor.pilots_into)
            ManyToManyDescriptor.__init__(the rel of Sailor.pilots_into, reverse=True)
              ReverseManyToOneDescriptor.__init__(the rel of Sailor.pilots_into)  (a ManyToManyDescriptor)
    Apps.lazy_model_operation(function, ('office', 'licence'))
    -> Apps._pending_operations holds 1 under ('office', 'licence')
  Apps.clear_cache
```

The first function to run has been waiting since the class statement of Ship, in another application, whose field `"captain"` names the Sailor by a string: only now can it run, and it makes the descriptor that Sailor has under `"command"`. The next two were left by Sailor's own fields a moment ago and find their targets, Ship and Port, already registered. The last needs the office's Licence, which is not yet imported, and goes back to waiting under that model's key. Which class statement completes a relation therefore depends on the order in which the two classes are made, and a relation whose other class never appears stays in `Apps._pending_operations` without raising anything ([The model checks](checks.md)).

And it clears what the registry has cached, which includes its list of models. Once the registry is ready, which it is not while the applications are still being loaded, the same call also throws away the cached lists in the options of each installed application's models, apart from any that a setting has replaced with another model (`django/apps/registry.py:Apps.clear_cache`).

If the registry already holds a model of that label and name, the outcome depends on whether it looks like the same class. One with the same name from the same module replaces the old with a `RuntimeWarning` that says reloading models is not advised. Any other is a conflict and raises `RuntimeError`.

## A class made without a class statement

`ModelBase.__new__` does not depend on the keyword `class`. Calling `type` with a name, bases that include a model, and a dictionary that has an entry `"__module__"`, which a class statement supplies, runs it just the same, since Python picks the metaclass from the bases. Django does this itself for the table between the two sides of a many-to-many relation whose field names no model for it (`django/db/models/fields/related.py:create_many_to_many_intermediary_model`). Inside the class statement of Voyage, the field `"calls"` makes a whole model class and has it registered before Voyage's own statement is over:

```text recording=models
create_many_to_many_intermediary_model(Voyage.calls, Voyage)
  lazy_related_operation(set_managed, Voyage, Port, 'Voyage_calls')
    Apps.lazy_model_operation(function, ('fleet', 'voyage'), ('fleet', 'port'), ('fleet', 'voyage_calls'))
    -> Apps._pending_operations holds 1 under ('crew', 'sailor'), 3 under ('fleet', 'voyage')
  ModelBase.__new__('Voyage_calls', (Model,))
...
    ModelBase._prepare(Voyage_calls)
...
    Apps.register_model('fleet', Voyage_calls)
```

The first lines are a function the field leaves with the registry on its own account, `set_managed`, which waits for Voyage, Port and the new model before it settles whether the new model is managed. With it, three functions are waiting under Voyage's name: the other two were left by `"ship"` and by `"calls"` as each joined the class. The one under Sailor's is still the function of Ship's `"captain"`.

The same route serves anything that needs model classes it did not write. The dictionary passed to `type` can carry a `Meta` whose `"apps"` names a registry other than the global one, and the class is then registered there and nowhere else. Migrations rebuild the models of each point in a project's history in registries of their own in this way (`django/db/migrations/state.py:ModelState.render`) ([Migrations](../migrations.md)).

## Signals that name a model by a string

`ModelSignal` is the class of the model signals, among them `pre_save`, `post_delete` and `m2m_changed`; `class_prepared` is an ordinary signal. A `ModelSignal` differs from a plain signal in one respect: the sender given to `connect` or `disconnect` may be a string of the form `"app_label.ModelName"`. Such a connection is handed to `Apps.lazy_model_operation`, the same waiting list the relations use. If the model is registered it is made at once, and otherwise when the model is (`django/db/models/signals.py:ModelSignal._lazy_method`).
