---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Historical models: `StateApps` and rendering

A historical model is a model class made from a model state: the model as it stood at some point of the project's migrations. `ProjectState.apps` makes them all at its first read and keeps them in a `StateApps`, a registry that belongs to the project state. After that, the state half of an operation makes again only the model it changed and the models related to it, through `ProjectState.reload_model` or `ProjectState.reload_models`; a model removed is only taken out.

A project state is data ([Project state: `ProjectState` and its model states](state.md)), and for the users that need classes, among them the schema editor and a function run by `RunPython`, it is **rendered**: each model state is made into a **historical model**, registered in **the state's registry** and not in the main registry, `django.apps.apps`. Rendering is costly, and it is put off: the registry is not made until something reads it, and once made it is patched after each operation.

## `ProjectState.apps`: made at the first read

`ProjectState.apps` is a `cached_property` whose body is one call: a `StateApps` made from `ProjectState.real_apps` and `ProjectState.models` (`django/db/migrations/state.py:ProjectState.apps`). A `cached_property` stores what its function returned in the instance's `__dict__` under its own name, where the next read finds it. So a state is rendered exactly when `"apps"` is a key of its `__dict__`, and that is what the source tests: `hasattr` would read the property, and render the state to learn whether it was rendered.

The recordings are of a running Django and its example project, harbour: a line of Python is written as it was run, `->` is followed by what a line or a call gave, and the other lines are calls, nested as they were made; only the lines a passage is about are written, and what ran between them is left out.

```text recording=migrations
state = MigrationLoader(None).project_state()
'apps' in state.__dict__  ->  False
registry = state.apps
  StateApps.__init__(real_apps=set(), models=<13 model states>)
    StateApps.render_multiple(<13 model states>)
      ModelState.render  [crew.Sailor]
        StateApps.register_model('crew', the historical model crew.Sailor)
        -> the historical model crew.Sailor
...
'apps' in state.__dict__  ->  True
state.apps is registry  ->  True
```

The registry is read by the database halves of operations, by `MigrationExecutor.detect_soft_applied` and by the migrate command for its two signals; makemigrations reads none. Forwards, the executor renders a state, if nothing has, just before the first migration it runs on it (`django/db/migrations/executor.py:MigrationExecutor._migrate_all_forwards`). A state cloned after that, as it is to keep a from-state for an operation, is given a clone of the registry, which shares its classes; the clone of an unrendered state has to be rendered whole on its own ([Applying a plan: `MigrationExecutor`](executor.md)).

## Rendering a model state: a class made by calling `type`

`ModelState.render` is given a registry and returns a model class (`django/db/migrations/state.py:ModelState.render`). It makes a class named `Meta` from the model state's options, less `"index_together"`, which a `Meta` may no longer have, and two attributes more: `"app_label"` and `"apps"`, the registry it was given. It resolves the bases: one kept as a string, such as `"crew.sailor"`, is looked up in the registry with `Apps.get_model`, one kept as a class is used as it is, and `typing.Generic`, which `type` refuses as a base, is passed over. The body of the class is a clone of each field under its name, the `Meta`, the managers, and `"__module__"`, set to `"__fake__"`; the fields are cloned because joining a class binds a field to it, and `ModelState.__init__` refuses a bound field. Then it calls `type` with the name, the bases and the body.

Calling `type` with a model among the bases runs `ModelBase.__new__`, as a class statement would ([`ModelBase`: a class statement becomes a model](../models/metaclass.md)). The metaclass takes the application's label from `Meta`, the options it makes take their registry from there, and it ends by registering the class with that registry ([The registry and its models](../startup/registry.md)). A base that the registry does not hold makes `get_model` raise `LookupError`, which `ModelState.render` turns into `InvalidBasesError`.

```text figure=rendering
the project state: models[("crew", "sailor")], a model state (name, fields, options, bases, managers)
  -- ModelState.render calls type; ModelBase.__new__ registers the class -->
the state's registry, a StateApps: the historical model crew.Sailor
  __module__ "__fake__"; has clones of the fields, the options, a plain Manager; lacks Sailor's __str__ and the manager's method aboard

harbour/crew/models.py: class Sailor
  -- the class statement; ModelBase.__new__ registers the class -->
the main registry, django.apps.apps: the model crew.Sailor
  __module__ "harbour.crew.models"; has the fields, the options, a __str__ of its own, a manager with the method aboard
```

*A model state rendered into a historical model, in the state's registry, beside the model that `models.py` defines, another class in the main registry.*

## What a historical model has, and what it lacks

A historical model has, of its model, what a model state carries and nothing else. In harbour, crew's Sailor defines `__str__` and has a manager made from a queryset class with a method, aboard; fleet's Ship takes its name and its `__str__` from an abstract base, Named. Below, Historical is the class the state's registry gives for crew.Sailor, HistoricalShip the one for fleet.Ship, registry that registry and apps the main one.

```text recording=migrations
Historical is Sailor  ->  False
Historical.__module__  ->  '__fake__'
Sailor.__module__  ->  'harbour.crew.models'
Historical.__name__  ->  'Sailor'
Historical._meta.apps is registry  ->  True
Sailor._meta.apps is apps  ->  True
...
Historical.__str__ is models.Model.__str__  ->  True
Sailor.__str__ is models.Model.__str__  ->  False
...
hasattr(Sailor.objects, 'aboard')  ->  True
hasattr(Historical.objects, 'aboard')  ->  False
...
Historical._meta.get_field('ship').related_model  ->  the historical model fleet.Ship
...
[klass.__name__ for klass in Ship.__mro__]  ->  ['Ship', 'Named', 'Model', 'AltersData', 'object']
[klass.__name__ for klass in HistoricalShip.__mro__]  ->  ['Ship', 'Model', 'AltersData', 'object']
```

The fields are there, and with them the relations, which join the class to other historical models of its registry; so are the options, and with them the ordering. What the class's body said that was neither field nor option is not: no method is in a model state, and the `__str__` of the historical Sailor is `Model`'s. An abstract base is not among a model state's bases, and its methods go with it, as Named has gone from the historical Ship's resolution order (`django/db/migrations/state.py:ModelState.from_model`).

A manager is carried as itself only when its class sets `BaseManager.use_in_migrations` ([Project state: `ProjectState` and its model states](state.md)); Sailor's does not, and the historical model has the plain `Manager` the metaclass gives a class with none ([Managers](../models/managers.md)). A manager the model state does hold is made again by `ModelState.construct_managers`: it says by `BaseManager.deconstruct` how it was made, and another is made the same way, by `QuerySet.as_manager` on its queryset class or by calling its class with the same arguments (`django/db/migrations/state.py:ModelState.construct_managers`).

## `StateApps`: a registry that can be changed

`StateApps` is a subclass of `Apps`, the class of the main registry, made to be changed: a model can be put in another's place in it or taken out, and the whole copied (`django/db/migrations/state.py:StateApps`).

### What `StateApps.__init__` does

`StateApps.__init__` is given the dictionary of model states and `ProjectState.real_apps`, a set of labels, which Django fills with those of the unmigrated applications: no migration creates their models, and so no model state describes them. It makes model states for them itself, from the models in the main registry, by `ModelState.from_model` with `exclude_rels=True`, which leaves out every field that is a relation and the options `"unique_together"` and `"order_with_respect_to"`, and keeps them as `StateApps.real_models`. Its comment gives the reasons: the classes of the main registry refer to that registry and so cannot be used, and their relations, for want of dependencies, go wrong in a state that holds only part of the project (`django/db/migrations/state.py:StateApps.__init__`). So a function run by `RunPython` finds these models without their foreign keys and many-to-many fields.

It then makes an `AppConfigStub`, an `AppConfig` cut down to a label and a dictionary of models, for each label of `real_apps` and of the model states, and passes them to `Apps.__init__`, which populates a registry at once when it is given configurations (`django/db/migrations/state.py:AppConfigStub`). The registry is now ready and empty, and every model state, the project state's and those of `real_models`, goes to `StateApps.render_multiple`.

Last, it runs `_check_lazy_references`, the function behind the system check of the main registry, on this one, and raises `ValueError` with the messages if anything is reported: a relation that named its target by a string is still waiting for a model that was not rendered (`django/core/checks/model_checks.py:_check_lazy_references`) ([The registry and its models](../startup/registry.md)).

### `StateApps.render_multiple` and `StateApps.bulk_update`

`StateApps.render_multiple` cannot count on an order: a model state names a base that is a model by a string, `ModelState.render` raises `InvalidBasesError` while the registry does not hold that base, and `ProjectState._reload` hands model states over in the order of a set. So it makes passes, rendering what it can and keeping what raised for the next pass, until nothing is left. A pass that renders nothing means a base that will never come, and the method raises `InvalidBasesError` itself, with the model states left over and the usual cause: inheriting, in an application with no migrations, from a model of an application that has them (`django/db/migrations/state.py:StateApps.render_multiple`).

It works inside `StateApps.bulk_update`. Each registration ends in `Apps.clear_cache`, which in a registry that is ready expires the cached lists of every model's options, and would do so once for each model rendered. `bulk_update` sets `Apps.ready` to false for its body, so that `clear_cache` passes over the models, and on leaving restores it and calls `clear_cache` once (`django/db/migrations/state.py:StateApps.bulk_update`).

### `StateApps.register_model`, `StateApps.unregister_model`, `StateApps.clone`

Where `Apps.register_model` warns of, or refuses, a second class under a name that is taken, `StateApps.register_model` puts the class in the place of whatever was there, makes a stub for a label the registry lacks, and then, like the main registry, runs what was waiting for the model and clears the caches (`django/db/migrations/state.py:StateApps.register_model`). `StateApps.unregister_model` takes a model out and leaves the caches alone; the main registry has no such method (`django/db/migrations/state.py:StateApps.unregister_model`).

`StateApps.clone` makes an empty `StateApps` with a deep copy of `Apps.all_models`, stubs of its own, and the same `real_models` (`django/db/migrations/state.py:StateApps.clone`). `copy.deepcopy` copies the dictionaries and not the classes, so a clone renders nothing and holds the classes of the registry it was made from.

## Re-rendering after an operation

An operation's state half changes the model states through a method of `ProjectState`, and each such method ends by bringing the registry into line, if there is one ([Project state: `ProjectState` and its model states](state.md)). `ProjectState.reload_model` returns at once on a state that is not rendered; on one that is, it has `ProjectState._find_reload_model` say which models are to be made again and gives the set to `ProjectState._reload` (`django/db/migrations/state.py:ProjectState.reload_model`).

The set is wider than the one model wherever the model is related to others: a relation is set up on both the classes it joins ([Relations: a field, its rel and the class at the other end](../relations/fields.md)), and a new class at one end would leave the other holding the old. `_find_reload_model` takes the class the registry has for the model, if it has one, as it was before the change, and collects the models related to it; reads the model state, as it is after the change, for the models its relations name, and collects each of those with the models related to it; and adds the model itself (`django/db/migrations/state.py:ProjectState._find_reload_model`). With `delay=True` the models further away are left as they are, to be made good when `ProjectState.clear_delayed_apps_cache` has the whole state rendered afresh. "Related" then means `get_related_models_tuples`: the model's direct subclasses, the class at the other end of each of its relations, forward and reverse, and for a proxy that a relation points at, the model it stands for (`django/db/migrations/state.py:_get_related_models`). Without it, "related" means `get_related_models_recursive`, which goes on from each model found to those related to it until no new one turns up. Here the state half of an `AddField`, run by hand on a rendered state, has given Dock a field that is not a relation, and `ProjectState.add_field` reloads the model:

```text recording=migrations
ProjectState.reload_model(app_label='yard', model_name='dock', delay=True)
  ProjectState._find_reload_model(app_label='yard', model_name='dock', delay=True)  ->  {('crew', 'sailor'), ('fleet', 'port'), ('fleet', 'ship'), ('fleet', 'voyage'), ('fleet', 'voyage_calls'), ('office', 'berth'), ('office', 'licence'), ('yard', 'dock'), ('yard', 'repair')}
...
    StateApps.render_multiple(<8 model states>)
```

Dock's foreign key names Port, so the set has Port and each model with a relation to it: Ship, Voyage and the model between that Voyage's many-to-many field makes for itself, Berth, Licence, Dock, and crew's Sailor for its many-to-many field. Repair is there for its foreign key to Dock. `_reload` takes each model of the set out of the registry and gives `StateApps.render_multiple` the model states it finds for them, among `StateApps.real_models` and the project state's (`django/db/migrations/state.py:ProjectState._reload`). Nine classes went out and eight model states were rendered: that model between has no model state, and Voyage's rendering made it again.

| method | its reload |
|---|---|
| `ProjectState.add_model` | not delayed |
| `ProjectState.add_field`, `ProjectState.remove_field` | delayed unless the field is a relation |
| `ProjectState.alter_field` | delayed unless the new field is a relation or `field_is_referenced` finds a reference to the field |
| `ProjectState.rename_field` | delayed unless `get_references` yields a reference to the field |
| `ProjectState.rename_model` | delayed; the models that pointed at the old name are reloaded in one set, by `ProjectState.reload_models` |
| the methods that change options, managers, indexes and constraints | delayed |
| `ProjectState.remove_model` | none: it unregisters the class and clears the registry's caches itself |

*The reload each method of `ProjectState` asks for (`django/db/migrations/state.py:ProjectState.alter_field`, `django/db/migrations/state.py:ProjectState.remove_model`).*

What a reference is, `field_references` decides: it counts every many-to-many field to the model as a reference to any of its fields (`django/db/migrations/utils.py:field_references`) ([The field operations, and those on indexes and constraints](field-operations.md)).

## A delayed state, and `ProjectState.clear_delayed_apps_cache`

A reload with `delay=True` can leave the registry inconsistent beyond the models it made again: a class further off still holds the classes that were replaced. When a field that is not a relation was added to yard's Dock ([Re-rendering after an operation](#re-rendering-after-an-operation)), crew's Sailor was made again and Officer, its child, was not, so Officer is left a subclass of a Sailor that the registry no longer holds. `ProjectState._find_reload_model` sets `ProjectState.is_delayed` whenever it is asked with `delay=True`.

`RunPython.database_forwards` calls `ProjectState.clear_delayed_apps_cache` on its from-state before it calls its function with that state's registry, and the migrate command calls it on the state the executor returns before it hands that state's registry to the receivers of `post_migrate`: a function or a receiver may ask the registry for any model (`django/db/migrations/operations/special.py:RunPython.database_forwards`, `django/core/management/commands/migrate.py:Command.handle`) ([The migrate command, showmigrations and sqlmigrate](migrate.md)). `clear_delayed_apps_cache` deletes the registry from the `__dict__` of a state that is delayed and rendered, and the next read renders every model afresh (`django/db/migrations/state.py:ProjectState.clear_delayed_apps_cache`). Yard's second migration changes fields that are not relations; after migrate had applied it:

```text recording=migrations
ProjectState.clear_delayed_apps_cache
StateApps.__init__(real_apps=set(), models=<13 model states>)
emit_post_migrate_signal
```

Nothing sets `is_delayed` back, not even that deletion, and `ProjectState.clone` copies it: after one delayed reload of a state, every `RunPython` that later runs its function forwards on it or on a clone of it renders every model again. And `RunPython.database_backwards` passes its function the from-state's registry without that call, so a function run backwards may be given a registry that a delayed reload left inconsistent (`django/db/migrations/operations/special.py:RunPython.database_backwards`) ([`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](special-operations.md)).
