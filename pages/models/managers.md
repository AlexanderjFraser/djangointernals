---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Managers

A manager is the object a model class's queries start from: `Model.objects` is one, an instance of `django.db.models.Manager` or of a subclass. A manager's class gets its methods from a queryset class through `BaseManager.from_queryset`, a manager is read from its model through a `ManagerDescriptor`, and Django itself chooses between two of a model's managers, the default manager and the base manager.

A queryset describes a query against one model, and each method that narrows it returns another queryset. Something has to supply the first one. That is the whole job of a manager: it knows its model, and when asked it makes a new queryset for it. A line such as this one is a manager making a queryset and passing the call on:

```python
Ship.objects.filter(tonnage__gt=400)
```

Little is left for a manager to be. It holds a model, a name and a choice of database; `BaseManager.get_queryset` is where every query begins; and nearly every other method a manager seems to have is a few generated lines that call `get_queryset` and then the queryset's method of the same name.

The crew's models declare two managers, each written in a different way:

```python
# harbour/crew/models.py
class SailorQuerySet(models.QuerySet):
    def aboard(self, ship):
        return self.filter(ship=ship)


class Sailor(models.Model):
    # after its fields: name, ship, signed_on, pilots_into
    objects = SailorQuerySet.as_manager()


class VeteranManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(signed_on__year__lt=2020)


class Veteran(Sailor):
    objects = VeteranManager()

    class Meta:
        proxy = True
```

## What a manager holds

`BaseManager.__init__` gives a new manager four attributes besides its creation counter: `BaseManager.model` and `BaseManager.name`, both `None` until the manager joins a class; an alias, `None` unless the manager has been told to use one database; and the hints it will pass to the database router, an empty dictionary (`django/db/models/manager.py:BaseManager.__init__`). Two flags stand on the class: `BaseManager.auto_created`, which is set on a manager Django added itself, and `BaseManager.use_in_migrations`.

A manager also takes a number. `BaseManager.creation_counter` is kept on the class, and each manager made takes its current value and moves it on, so that the managers of a model can be put in the order they were created in.

And it remembers how it was made. `BaseManager.__new__` stores the positional and keyword arguments of the call that constructed the manager, before `__init__` runs, and the comment there says why: to make returning them trivial. `BaseManager.deconstruct` is what returns them, to a migration. `BaseManager.__eq__` uses them too: it answers true when the other manager is an instance of this manager's class and their stored arguments are equal.

## Where the methods come from

`django.db.models.manager.Manager` is declared with an empty body. All it has comes from its one base, and that base is written nowhere as a class statement: it is the value of an expression in `Manager`'s own, a call of `BaseManager.from_queryset` with `QuerySet` (`django/db/models/manager.py:Manager`).

`BaseManager.from_queryset` makes a class by calling `type`. The class it was called on is the new class's one base. Unless the caller gives a name, the name is that class's name, the word From and the queryset class's name run together, here `BaseManagerFromQuerySet`. The body is one attribute, `"_queryset_class"`, holding the queryset class, and a method for each method of the queryset class that `BaseManager._get_queryset_methods` picks out (`django/db/models/manager.py:BaseManager.from_queryset`).

```text recording=models
[c.__name__ for c in models.Manager.__mro__]  ->  ['Manager', 'BaseManagerFromQuerySet', 'BaseManager', 'object']
models.Manager.__mro__[1]._queryset_class  ->  <class 'django.db.models.query.QuerySet'>
'filter' in vars(models.Manager.__mro__[1]), 'filter' in vars(BaseManager), 'filter' in vars(models.Manager)  ->  (True, False, False)
models.Manager.filter.__qualname__  ->  'QuerySet.filter'
hasattr(models.Manager, 'delete'), hasattr(models.Manager, 'as_manager'), hasattr(models.Manager, '_insert'), hasattr(models.Manager, '_clone')  ->  (False, False, True, False)
models.QuerySet.delete.queryset_only, models.QuerySet._insert.queryset_only, models.QuerySet.as_manager.queryset_only  ->  (True, False, True)
```

`_get_queryset_methods` goes through every plain function that `inspect.getmembers` finds on the queryset class, inherited ones included, and passes over one for any of three reasons (`django/db/models/manager.py:BaseManager._get_queryset_methods`).

The manager class already has an attribute of that name. This is why `QuerySet.all` is not copied: `BaseManager` has a method of that name already.

The function carries an attribute `"queryset_only"` that is true. `QuerySet.delete` and its asynchronous twin `QuerySet.adelete` are marked so, and `QuerySet.resolve_expression`. `QuerySet.as_manager` carries the mark too, but as a class method it is not one of the plain functions the loop is given. The source marks `delete` and gives no reason. Django's documentation does: keeping it off the manager is a safety mechanism, so that a call on the manager alone cannot delete every row of a table.

Or it carries no such attribute and its name begins with an underscore. The mark settles the matter either way, so a private method marked false is copied all the same. `QuerySet._insert` and `QuerySet._update` are, and the insert of a save is a call of the first on a manager ([Saving an instance](saving.md)).

What is copied is not the queryset's function. For each name, a new function is made that takes the manager and any arguments, calls `get_queryset`, looks the name up on the queryset that comes back, and calls what it finds with the arguments. It is passed through `functools.wraps`, so it bears the queryset method's name and docstring, and its qualified name, as the fourth line above shows. A call through it looks like this:

```text recording=models
Sailor.objects.filter(name='Ada')
  ManagerDescriptor.__get__(None, Sailor)  ->  a ManagerFromSailorQuerySet
  manager_method  (the method the manager's class was given under the name 'filter')
    BaseManager.get_queryset  (a ManagerFromSailorQuerySet)  ->  a SailorQuerySet of Sailor, not yet fetched
    QuerySet.filter(name='Ada')
```

Two things follow. Every call through a manager begins with a new queryset, and a manager keeps nothing between one call and the next. And the method is found by name, at the moment of the call, on whatever `get_queryset` returned, so a manager that changes what `get_queryset` returns has changed all of its copied methods at once.

The methods are chosen when the manager's class is made, which for `Manager` is when its module is first imported.

### A queryset class of the project's

`BaseManager.from_queryset` serves a project's own queryset class in the same way. Given a subclass of `QuerySet` with methods of its own, it returns a manager class that has those methods beside the standard ones. `QuerySet.as_manager` is the short way to it: a class method that calls `from_queryset` on `Manager` with the class it is itself called on, makes an instance of the result, sets `"_built_with_as_manager"` on the instance, and returns it (`django/db/models/query.py:QuerySet.as_manager`). Sailor's manager is made so. Its class is a generated one, with the other generated class further down among its bases:

```text recording=models
[c.__name__ for c in type(Sailor.objects).__mro__]  ->  ['ManagerFromSailorQuerySet', 'Manager', 'BaseManagerFromQuerySet', 'BaseManager', 'object']
hasattr(Sailor.objects, 'aboard'), hasattr(Ship.objects, 'aboard')  ->  (True, False)
```

A method written once on the queryset class is then to be had in both places: on the manager, through the generated method, and on every queryset the manager makes, because `get_queryset` makes an object of `"_queryset_class"`. The second is recorded here:

```text recording=models
Sailor.objects.all().aboard(petrel)
  ManagerDescriptor.__get__(None, Sailor)  ->  a ManagerFromSailorQuerySet
  BaseManager.all
    BaseManager.get_queryset  (a ManagerFromSailorQuerySet)  ->  a SailorQuerySet of Sailor, not yet fetched
  SailorQuerySet.aboard(<Ship: Petrel>)
    QuerySet.filter(ship=<Ship: Petrel>)
    -> a SailorQuerySet of Sailor, not yet fetched
```

## `get_queryset`: where a manager narrows

`BaseManager.get_queryset` returns a new object of the manager's queryset class, made with the manager's model, its alias and its hints (`django/db/models/manager.py:BaseManager.get_queryset`). Since every copied method starts there, overriding it is the way to give a manager a narrower idea of its model's rows. VeteranManager does that, and nothing else:

```text recording=models
Veteran.objects.all()
  ManagerDescriptor.__get__(None, Veteran)  ->  a VeteranManager
  BaseManager.all
    VeteranManager.get_queryset
      BaseManager.get_queryset  (a VeteranManager)  ->  a QuerySet of Veteran, not yet fetched
      QuerySet.filter(signed_on__year__lt=2020)
      -> a QuerySet of Veteran, not yet fetched
```

The filter is then in every query that starts from one of the manager's copied methods.

`BaseManager.all` is a queryset method that `BaseManager` writes out for itself, and it returns what `get_queryset` returns. The comment on it explains why it is not left to the generated kind. `QuerySet.all` works by copying the queryset it is called on, and the copy loses any results cached by `prefetch_related`; the `get_queryset` of a related manager may hand back just such a queryset of prefetched results, and the manager's method must not throw them away (`django/db/models/manager.py:BaseManager.all`).

`EmptyManager` overrides `get_queryset` as well. It is a `Manager` for a place where there is no table to ask: it is given its model in its constructor, without joining any class, and its `get_queryset` returns the queryset that `QuerySet.none` gives, which fetches nothing (`django/db/models/manager.py:EmptyManager`). `AnonymousUser`, which is not a model, has two of them, for its groups and for its permissions (`django/contrib/auth/models.py:AnonymousUser`).

## A manager joins a class

A manager in a class body is one of the attributes the metaclass holds back and then hands the class to ([`ModelBase`: a class statement becomes a model](metaclass.md)). `BaseManager.contribute_to_class` takes the attribute's name as the manager's own, unless the manager has one already, and records the class as its model. It sets a `ManagerDescriptor` on the class under that name. And it enters the manager in the class's options with `Options.add_manager`, which appends it to `Options.local_managers` and discards what the options had cached (`django/db/models/manager.py:BaseManager.contribute_to_class`, `django/db/models/options.py:Options.add_manager`).

```text recording=models
ModelBase.add_to_class(Sailor, 'objects', a ManagerFromSailorQuerySet)
  BaseManager.contribute_to_class(Sailor, 'objects')  (a ManagerFromSailorQuerySet)
    ManagerDescriptor.__init__(a ManagerFromSailorQuerySet)
    Options.add_manager(a ManagerFromSailorQuerySet)
```

A class that declares no manager, and inherits none, is given one. `ModelBase._prepare` asks the options for the class's managers, and when there are none it makes a `Manager`, sets `auto_created` on it, and adds it under the name `"objects"` in the same way (`django/db/models/base.py:ModelBase._prepare`). This is Ship, with the part of the method that adds a primary key left out:

```text recording=models
ModelBase._prepare(Ship)
  ModelBase.add_to_class(Ship, 'objects', a Manager)
    BaseManager.contribute_to_class(Ship, 'objects')  (a Manager)
      ManagerDescriptor.__init__(a Manager)
      Options.add_manager(a Manager)
```

A model that has a field named `"objects"` and no manager cannot be given that one, and the method raises `ValueError` for it. An abstract class is never prepared, and so is given no automatic manager.

## Reading it back: `ManagerDescriptor`

What stands on the class under the manager's name is not the manager, and what comes back from reading it is not the manager the body declared either:

```text recording=models
type(vars(Sailor)['objects']).__name__, Sailor.objects is Sailor.objects  ->  ('ManagerDescriptor', True)
Sailor._meta.local_managers[0] is Sailor.objects, Sailor._meta.local_managers[0] == Sailor.objects  ->  (False, True)
```

`ManagerDescriptor.__get__` refuses three kinds of read with `AttributeError`. A manager is not to be reached through an instance: it belongs to the class. It is not to be had from an abstract class, which may declare a manager for its children and cannot use it. And it is not to be had from a model that a setting has swapped for another ([Authentication, sessions and messages](../auth.md)).

```text recording=models
Ship(name='Heron').objects  ->  raises AttributeError: Manager isn't accessible via Ship instances
Named.objects  ->  raises AttributeError: type object 'Named' has no attribute 'objects'
```

The first line is the descriptor's refusal. The second is not: Named declares no manager and was given none, so there is no descriptor and the error is Python's own.

For any other read the descriptor returns one entry of a dictionary, `Options.managers_map`, kept by the options of the class the attribute was read on: the entry under the name of the manager it was made for (`django/db/models/manager.py:ManagerDescriptor.__get__`, `django/db/models/options.py:Options.managers_map`).

## The managers of a class, and of its parents

`Options.managers` builds the list of a class's managers the first time it is asked (`django/db/models/options.py:Options.managers`). It goes through the classes in the model's method resolution order that have options, the model itself first, and takes each one's `local_managers`. A manager whose name has already been taken by a class nearer the front is passed over. Of each of the others it makes a shallow copy and sets the copy's `model` to the model that is asking. The copies are sorted by how far along the order their class stands, and within one class by creation counter. `managers_map` is the same list as a dictionary by name.

```text figure=reading-a-manager
One manager is written in Sailor's body. What is made of it, and what three reads return.

The class statement of Sailor
    the manager made by SailorQuerySet.as_manager()     kept in the options of Sailor: local_managers
    a ManagerDescriptor holding that manager            set on the class: Sailor.__dict__["objects"]

Sailor.objects is read
    Python finds the descriptor in Sailor.__dict__
    the descriptor asks the options of Sailor for managers_map["objects"]
    Options.managers goes through Sailor's method resolution order: Sailor
        -> a copy of the manager, its model Sailor (made once and kept by the options)

Officer.objects is read; Officer declares no manager
    Python finds the same descriptor, in Sailor.__dict__
    the descriptor asks the options of Officer for managers_map["objects"]
    Options.managers goes through Officer's method resolution order: Officer, Sailor
        -> another copy of the same manager, its model Officer

Veteran.objects is read; Veteran declares a manager of the same name
    Python finds Veteran's own descriptor, in Veteran.__dict__
    the descriptor asks the options of Veteran for managers_map["objects"]
    Options.managers goes through Veteran's method resolution order: Veteran, Sailor
        -> a copy of Veteran's manager, its model Veteran; Sailor's manager of that name is passed over
```

*Reading a manager from a class. The descriptor is found by Python's attribute lookup, on the class or on a parent; the manager it returns is a copy made for the class that was asked, by a walk over that class's bases.*

So even a class's own manager is handed out as a copy. The object written in the body stays in `local_managers` as the pattern, which is why it and the manager read from Sailor were recorded as two objects, and equal ones: the copy carries the same constructor's arguments. The copy is made once and kept for as long as the options keep their cached lists, so two reads give the same object. When the cache is discarded, as it is whenever a field or a manager is added to the class, the next read makes a new copy (`django/db/models/options.py:Options._expire_cache`).

A child gets its parents' managers by the same walk. Officer declares none and has no descriptor of its own. Python finds Sailor's, the descriptor asks Officer's options, and their walk reaches the manager in Sailor's `local_managers`:

```text recording=models
names(Sailor._meta.managers), names(Officer._meta.local_managers), names(Officer._meta.managers)  ->  ([objects], [], [objects])
Officer.objects.model, Officer.objects is Sailor.objects, type(Officer.objects) is type(Sailor.objects)  ->  (<class 'harbour.crew.models.Officer'>, False, True)
```

The walk does not ask what kind of base a class is. An abstract base's managers are found by it, and so are those of the model behind a proxy ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)).

And a manager is replaced by declaring another under its name. Veteran's body has a manager called `"objects"`, so Sailor's is passed over for Veteran:

```text recording=models
What the class Veteran holds in its own __dict__, in the order the names were set
    __doc__: 'The sailors who signed on before 2020. A proxy: the same table, another class.'
    _meta: an Options
    DoesNotExist: the class Veteran.DoesNotExist
    MultipleObjectsReturned: the class Veteran.MultipleObjectsReturned
    NotUpdated: the class Veteran.NotUpdated
    objects: a ManagerDescriptor
```

The replacement is whole. VeteranManager is built on `Manager`, so the querysets it makes are plain `QuerySet`s, as was recorded where its `get_queryset` ran, and `"aboard"` is not among its methods.

## The default manager and the base manager

Much of Django has to query a model without having been told which of its managers to use: to find the row a save should update, to follow a foreign key, to see whether a value is already taken. It cannot go by the name `"objects"`, which a model need not have. Each model class therefore answers to two more names, `ModelBase._default_manager` and `ModelBase._base_manager`, properties declared on the metaclass, which makes them attributes of a model class and not of its instances. They return what the options work out as `Options.default_manager` and `Options.base_manager` (`django/db/models/base.py:ModelBase._default_manager`, `django/db/models/options.py:Options.default_manager`).

Unless a model says otherwise, its **default manager** is the first of its managers, the project's own where the project wrote one, and its **base manager** is a plain `Manager` whatever the project wrote:

```text recording=models
type(Sailor._default_manager).__name__, type(Sailor._base_manager).__name__, Sailor._base_manager.name  ->  ('ManagerFromSailorQuerySet', 'Manager', '_base_manager')
type(Veteran._default_manager).__name__, type(Veteran._base_manager).__name__  ->  ('VeteranManager', 'Manager')
```

The first of its managers is the first of `Options.managers`: the first manager the class itself created, or else the first of the nearest base that has any. A class with no manager at all, as an abstract one may be, has `None` for a default manager. The plain `Manager` is made on the spot and kept with the options' other cached values, under the name `"_base_manager"` and with the class as its model. It never joins the class: it has no descriptor and is in none of the options' lists (`django/db/models/options.py:Options.base_manager`).

A model says otherwise in its `Meta`, by naming one of its managers as `"default_manager_name"` or as `"base_manager_name"`; a name that is no manager of the class raises `ValueError` when that manager is asked for. A class that names no default manager and declares no manager of its own goes by the setting in its nearest model base's options, if the `Meta` that base went by gave one. A class that names no base manager goes by the name of its nearest model base's base manager, where that is a named manager and not the plain one, and takes its own manager of that name; a name given once therefore passes down the line to every class that names none.

### Who asks which

| what Django is doing | the manager it asks | where |
|---|---|---|
| saving: the update and the insert of each table | base, of the class whose table it is | `django/db/models/base.py:Model._save_table` |
| `Model.refresh_from_db`, and through it a deferred field read for one instance | base, of the instance's class | `django/db/models/base.py:Model.refresh_from_db` |
| a deferred field fetched for several instances together | base, of the model the field belongs to | `django/db/models/query_utils.py:DeferredAttribute.fetch_many` |
| reading the object a foreign key or a one-to-one field points at | base, of the model pointed at | `django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.get_queryset` |
| reading the object at the other end of a one-to-one field | base, of the model with the field | `django/db/models/fields/related_descriptors.py:ReverseOneToOneDescriptor.get_queryset` |
| validating that the value of a foreign key has a row | base, of the model pointed at | `django/db/models/fields/related.py:ForeignKey.validate` |
| finding the rows that point at an object being deleted | base, of the model those rows belong to | `django/db/models/deletion.py:Collector.related_objects` |
| adding objects through the manager at the other end of a foreign key, with `bulk=True` | base, of the model with the foreign key | `django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager` |
| the unique checks of `Model.full_clean` | default, of the class the field belongs to, or whose options hold the `unique_together` | `django/db/models/base.py:Model._perform_unique_checks` |
| validating a `UniqueConstraint` | default, of the class whose options hold the constraint | `django/db/models/constraints.py:UniqueConstraint.validate` |
| the next or previous instance by a date field | default, of the instance's class | `django/db/models/base.py:Model._get_next_or_previous_by_FIELD` |
| the choices a foreign key offers to a form | default, of the model pointed at | `django/db/models/fields/related.py:ForeignKey.formfield` |
| adding and removing the rows of a many-to-many relation | default, of the through model | `django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager` |
| the manager at the other end of a foreign key | a subclass of the class of the default manager of the model with the foreign key | `django/db/models/fields/related_descriptors.py:ReverseManyToOneDescriptor.related_manager_cls` |
| the manager at either end of a many-to-many field | a subclass of the class of the default manager of the model at the other end | `django/db/models/fields/related_descriptors.py:ManyToManyDescriptor.related_manager_cls` |

*Which of a model's two managers the code of `django/db/models/` goes to, in the places this chapter passes through.*

Django's documentation gives a reason for the rows about a related object: it has to be retrievable even when the default manager would filter it out. For the same reason the documentation tells a project that names a base manager not to filter rows away in it.

The last two rows are of another kind. A related manager is an object of a class made at run time: a subclass of the class of the default manager of the model it gives access to, or of another of that model's managers when it is asked for by that manager's name. It has whatever methods that class has, beside its own, of which `remove` and `clear` are defined only where the foreign key can be null, as the one from Sailor to Ship cannot ([Reading and setting related objects](related-objects.md), [Many-to-many relations](many-to-many.md)):

```text recording=models
[c.__name__ for c in type(petrel.crew).__mro__]  ->  ['RelatedManager', 'ManagerFromSailorQuerySet', 'Manager', 'BaseManagerFromQuerySet', 'BaseManager', 'AltersData', 'object']
hasattr(petrel.crew, 'aboard'), hasattr(petrel.crew, 'remove'), hasattr(petrel.crew, 'clear')  ->  (True, False, False)
```

### A default manager that filters

The difference between the default manager and the base manager shows when a default manager's `get_queryset` leaves rows out, as Veteran's does. Bram signed on in 2026, so no queryset that starts from `"objects"` of Veteran will find him. The base manager of Veteran does, and the instance it gives is saved with an update of his row, here without two of the save's calls:

```text recording=models
Veteran.objects.filter(name='Bram').exists(), Veteran._base_manager.filter(name='Bram').exists()  ->  (False, True)
  SQL SELECT %s AS "a" FROM "crew_sailor" WHERE ("crew_sailor"."signed_on" < %s AND "crew_sailor"."name" = %s) LIMIT 1 with params (1, '2020-01-01 00:00:00', 'Bram')
  SQL SELECT %s AS "a" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s LIMIT 1 with params (1, 'Bram')
hidden = Veteran._base_manager.get(name='Bram'), and hidden.save()
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s LIMIT 21 with params ('Bram',)
  Model.save()  (a Veteran)
    Model.save_base()
      Model._save_table(cls=Sailor)
        Model._do_update(pk_val=2, values for [name, ship, signed_on])
          SQL UPDATE "crew_sailor" SET "name" = %s, "ship_id" = %s, "signed_on" = %s WHERE "crew_sailor"."id" = %s with params ('Bram', 1, '2026-04-10 09:00:00', 2)
          -> [()]
        -> updated: True
```

A row the default manager hides can still be saved, refreshed and reached through a foreign key, because none of those asks the default manager. The save above does not ask a manager of Veteran at all: `Model.save_base` exchanges a proxy for its concrete model, and the update goes through the base manager of Sailor (`django/db/models/base.py:Model.save_base`).

The related sets do follow the default manager. The `get_queryset` of a related manager starts from its base class's, which is the default manager's, and narrows the result to the one instance. A filter in the first is in a related set fetched that way, which leaves out one asked for by another manager's name and one prefetched with a queryset of the caller's own (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager`).

And validation follows it, with a consequence. The unique checks look for an existing row through the default manager of the class the field belongs to. A row that manager hides is not found, the check passes, and the database refuses the duplicate when it is saved ([Validating an instance](validation.md)). Veteran is not such a case, its manager notwithstanding: Veteran has no fields of its own, every unique check on a Veteran belongs to Sailor, and it is Sailor's default manager that is asked.

## Another database: `db_manager` and the hints

`BaseManager.db_manager` returns a shallow copy of the manager with an alias, or hints, or both, set on it. `get_queryset` passes both to the queryset it makes, and `BaseManager.db` answers with the alias, or without one with whatever `ConnectionRouter.db_for_read` says for the model and the hints (`django/db/models/manager.py:BaseManager.db_manager`, `django/db/utils.py:ConnectionRouter`).

The hints are keyword arguments for the database routers. `ConnectionRouter` passes them, with the model, to each router's method in turn, and where none of them chooses it answers itself: with the database of the hint called `"instance"`, if that object has one, and otherwise with the default. `Model.refresh_from_db` and the two descriptors that fetch one related object, `ForwardManyToOneDescriptor` and `ReverseOneToOneDescriptor`, make their querysets from `db_manager` with the instance as that hint.

A manager also has `QuerySet.using`, copied like the rest. That returns a queryset. `db_manager` returns a manager, and is the way to call, against another database, a method that the manager's class defines and the queryset's does not. The command that creates a superuser does so for a method of the user model's manager, which on Django's own user model is `UserManager.create_superuser` (`django/contrib/auth/management/commands/createsuperuser.py:Command.handle`).

## What a migration keeps of a manager

`BaseManager.deconstruct` describes a manager as five values from which it can be made again: whether it was made by `as_manager`, the dotted path of its class, the dotted path of its queryset class, and the positional and the keyword arguments it was constructed with. A migration that carries a manager writes it down and rebuilds it by them (`django/db/models/manager.py:BaseManager.deconstruct`, `django/db/migrations/state.py:ModelState.construct_managers`). A manager made by `as_manager` is described by the first and the third, the others being `None`, and rebuilt by calling `as_manager` on that class again:

```text recording=models
Sailor.objects.deconstruct()[:3]  ->  (True, None, 'harbour.crew.models.SailorQuerySet')
```

Any other is described by the dotted path of its own class and the arguments `__new__` stored. That requires the class to be importable under its name from its module. A class that `from_queryset` made, used directly, is not, and for one `deconstruct` raises `ValueError` with the advice to inherit from it.

Not every manager is carried. `ModelState.from_model` keeps a copy of each manager whose class sets `use_in_migrations`, and of the rest at most a plain `Manager` in place of the default manager and another in place of the base manager, each under the name of the manager it stands for. It carries none at all where the one manager kept would be such a stand-in for the default manager, called `"objects"` (`django/db/migrations/state.py:ModelState.from_model`) ([Migrations](../migrations.md)).
