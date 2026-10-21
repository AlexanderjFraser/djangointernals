---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Project state: `ProjectState` and its model states

A **project state**, a `ProjectState`, is a project's models held as data: a dictionary of **model states**, each a `ModelState` with one model's fields, options, bases and managers and no class (`django/db/migrations/state.py:ProjectState`, `django/db/migrations/state.py:ModelState`). The state half of an operation is given one to change, the autodetector compares two, and historical models are rendered from one.

Migrations need the models as they stood at each step of a history, and need to get from one step to the next: a field added, a model renamed, an option dropped. A model class cannot be stepped like that: the docstring of `ModelState` says it is not designed to have its options changed, so a model state is mutated instead and rendered into a class as required ([Historical models: `StateApps` and rendering](historical-models.md)). The state is one for the whole project so that, as the docstring of `ProjectState` has it, relations from one application to another resolve.

A project state can begin empty and have the state halves of the migrations run on it in an order the graph gives: `MigrationGraph.make_state` makes the from-state of makemigrations so ([The migration graph: `MigrationGraph`](graph.md)). Or it can be read off the model classes: `ProjectState.from_apps` asks a registry for its models, those swapped out included and those a many-to-many field made for itself left out, and files what `ModelState.from_model` makes of each (`django/db/migrations/state.py:ProjectState.from_apps`). makemigrations makes its to-state so, from the main registry ([The makemigrations command](../makemigrations/makemigrations.md)).

## One model state: `from_model`

A model state holds a label and a name, `ModelState.app_label` and `ModelState.name`, and beside them `ModelState.fields`, a dictionary of field objects by name; `ModelState.options`, a dictionary of what the model's `Meta` held; `ModelState.bases`, a tuple; and `ModelState.managers`, a list of pairs of a name and a manager. `ModelState.name_lower` is the name in lower case. `ModelState.from_model` makes a model state from a model class (`django/db/migrations/state.py:ModelState.from_model`).

Ship, in the fleet application of harbour, the chapter's example project ([Migrations](../migrations.md)), takes a field, name, and an ordering from an abstract base, Named:

```python
# harbour/fleet/models.py
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
```

In the recordings, taken from a running Django, a line is Python as it was run or a question put to it, with the answer after `->`; set in under a line are the calls it made and, after "changed:", what then differed in the model states; only the lines a passage is about are quoted, and what ran between them is left out.

```text recording=migrations
ship = ModelState.from_model(Ship)
list(ship.fields)  ->  ['id', 'name', 'tonnage', 'home', 'captain']
...
ship.fields['name'] is Ship._meta.get_field('name')  ->  False
hasattr(ship.fields['name'], 'model')  ->  False
ship.fields['home'].remote_field.model  ->  'fleet.port'
```

`from_model` takes the model's own fields, `Options.local_fields` and then `Options.local_many_to_many`, and files `Field.clone` of each under its name (`django/db/models/options.py:Options.add_field`, `django/db/models/fields/__init__.py:Field.clone`). A clone is the field's class called again with the arguments `Field.deconstruct` read off the bound field: the primary key's include `serialize=False`, which `Options.setup_pk` set, and that is the `serialize=False` of a primary key in a migration file. The clone has no `Field.model`, and a relation in it names its target by a string, which is how a relation deconstructs (`django/db/models/fields/related.py:ForeignObject.deconstruct`, `django/db/models/fields/related.py:ManyToManyField.deconstruct`; [A field: the base class](../models/fields.md)). Passed over are the private fields, such as a generic foreign key, which are in neither list, and the `OrderWrt` field that `"order_with_respect_to"` adds, which a class rendered with that option is given again.

The options come from `Options.original_attrs`, where the options wrote down each value a `Meta` gave them ([The options: what a model keeps as `_meta`](../models/options.md)). `from_model` goes through `DEFAULT_NAMES` and takes each name that dictionary has, but for `"apps"` and `"app_label"`, and for `"order_with_respect_to"` where it names a private field: what it takes is what the `Meta` held, its own or inherited, and none of the defaults. Ship's `Meta` inherits `"abstract"` from Named's, on which the metaclass set it to `False` once it had made Named (`django/db/models/base.py:ModelBase.__new__`). `"unique_together"` becomes a set of tuples (`normalize_together`). `"indexes"` and `"constraints"` are clones of the objects in `Options.indexes` and `Options.constraints`, where a placeholder in a name has been filled in and an index given no name has had one from the metaclass (`django/db/models/base.py:ModelBase._prepare`; [Constraints and indexes](../models/constraints.md)).

The bases are the class's direct bases with each abstract model among them replaced by its own bases, and so on up, each once, in the class's method resolution order. Named disappears: its field is already one of Ship's own, copied there by the metaclass. A base that is a model is written as a string, its label in lower case; one that is not, a mixin or `Model` itself, stays a class.

Managers are carried only where their class asks. Of `Options.managers`, a manager whose class sets `BaseManager.use_in_migrations` is copied. Of the others only the model's default manager and its base manager leave a trace: a plain `Manager` under the same name stands in for each. Where the list would then be nothing but the stand-in for a default manager called `"objects"`, it is left empty, as Ship's is. A manager that is kept is made again from `BaseManager.deconstruct` when the state is rendered ([Managers](../models/managers.md)).

```text recording=migrations
ship.options['indexes']  ->  [<Index: fields=['home', 'tonnage'] name='fleet_ship_home_id_f9b8f2_idx'>]
Ship._meta.original_attrs  ->  {'ordering': ['name'], 'abstract': False, 'indexes': [<Index: fields=['home', 'tonnage']>], 'constraints': [<CheckConstraint: condition=(AND: ('tonnage__gt', 0)) name='%(class)s_has_tonnage'>, <UniqueConstraint: fields=('name', 'home') name='one_name_to_a_port'>]}
...
ship.bases  ->  (Model,)
Ship.__bases__  ->  (the model fleet.Named,)
ship.managers  ->  []
```

Of crew's models, Officer is a child of Sailor with a table of its own, its fields the link to its parent and the one it adds, and Veteran a proxy of Sailor; each has Sailor as its base, a string:

```text recording=migrations
list(ModelState.from_model(Officer).fields)  ->  ['sailor_ptr', 'rank']
ModelState.from_model(Officer).bases  ->  ('crew.sailor',)
ModelState.from_model(Veteran).bases  ->  ('crew.sailor',)
ModelState.from_model(Veteran).options  ->  {'proxy': True, 'indexes': [], 'constraints': []}
```

## What a model state's `__init__` refuses

Every model state goes through `ModelState.__init__`: those `ModelState.from_model` makes, those `CreateModel` makes from its arguments, and every clone (`django/db/migrations/state.py:ModelState.__init__`). It copies the fields into a dictionary of its own, gives the options an empty list under `"indexes"` and under `"constraints"` where they have none, and raises `ValueError` for a field that is bound to a model, for a relation that names a model class, as its target or as a many-to-many field's through model, and for an index with no name. Crane here is a model state made by hand, and Dock a model class:

```text recording=migrations
ModelState('yard', 'Crane', [('port', Dock._meta.get_field('port'))])  ->  raises ValueError: ModelState.fields cannot be bound to a model - "port" is.
ModelState('yard', 'Crane', [('dock', models.ForeignKey(Dock, models.CASCADE))])  ->  raises ValueError: Model fields in "ModelState.fields" cannot refer to a model class - "yard.Crane.dock.to" does. Use a string reference instead.
ModelState('yard', 'Crane', [], options={'indexes': [models.Index(fields=['dock'])]})  ->  raises ValueError: Indexes passed to ModelState require a name attribute. <Index: fields=['dock']> doesn't have one.
```

A bound field is a field of one class, and a state's fields are kept apart from every class, `ModelState.render` cloning each for the class it makes. A string in a relation is looked up, at rendering, in the registry the class is rendered into, and each rendered state has a registry of its own; a class belongs to one registry already. And an index is found by its name: `ProjectState.remove_index` and `ProjectState.rename_index` look for it so, and `RemoveIndex`, `RenameIndex` and `RemoveConstraint`, which hold a name and not the object, get the object for their database halves from `ModelState.get_index_by_name` and `ModelState.get_constraint_by_name`.

## The whole project: `ProjectState.models`, `real_apps` and `clone`

`ProjectState.models` is a dictionary of model states, each under the pair of its application's label and its name in lower case (`django/db/migrations/state.py:ProjectState.__init__`). `ProjectState.real_apps` is a set of labels: the applications whose models are to come from the main registry when the state is rendered. The loader passes for it the labels of its unmigrated applications, whose models are not in `models`, though a graph with no node makes a state with none of those labels (`django/db/migrations/graph.py:MigrationGraph.make_state`; [Historical models: `StateApps` and rendering](historical-models.md)). A state from `ProjectState.from_apps` has those applications' models like any others, and an empty set.

`ProjectState.__eq__` compares `models` and `real_apps` only, and `ModelState.__eq__` the label, the name, the options, the bases, the managers, and the fields pair by pair in the order of their names, each by what `Field.deconstruct` returns after the name (`django/db/migrations/state.py:ModelState.__eq__`, `django/db/models/fields/__init__.py:Field.deconstruct`).

`ProjectState.clone` makes a project state with a `ModelState.clone` of each model state, the same set of `real_apps` and, where the state has been rendered, a clone of its registry. A model state's clone has dictionaries of its own for fields and options and a list of its own for managers, and in them the same field objects and option values (`django/db/migrations/state.py:ModelState.clone`). Here state is the loader's project state from harbour's migration files, in which yard is a fourth application with the models Dock and Repair:

```text recording=migrations
state = MigrationLoader(None).project_state()
clone = state.clone()
...
clone.models['yard', 'dock'].fields is state.models['yard', 'dock'].fields  ->  False
clone.models['yard', 'dock'].fields['name'] is state.models['yard', 'dock'].fields['name']  ->  True
clone.models['fleet', 'ship'].options is state.models['fleet', 'ship'].options  ->  False
clone.models['fleet', 'ship'].options['indexes'] is state.models['fleet', 'ship'].options['indexes']  ->  True
```

The sharing sets the one rule of this data, which the docstring of `ModelState` states for fields and a comment in `clone` repeats for options: the dictionary may be changed and the objects in it may not, so that an operation such as `AddIndex` must put a new list under `"indexes"`, not append to the one there. Clones are how the state before a change is kept: `Migration.apply` clones the project state ahead of each operation's state half, and what that half changed inside a shared object would change in the from-state too (`django/db/migrations/migration.py:Migration.apply`). The sharing reaches past clones: the fields `CreateModel` gives a model state are the operation's own objects, so one loader's project states share them until an operation replaces one (`django/db/migrations/operations/models.py:CreateModel.state_forwards`).

## The methods the operations call

The state half of each operation that `django/db/migrations/operations/` has for a model, a field, an index or a constraint works by calling a method of the project state ([Operations: the base class and its two halves](operations.md)). `RunPython`'s does nothing, and those of `RunSQL` and `SeparateDatabaseAndState` run the state halves of operations given them for that ([`RunPython`, `RunSQL` and `SeparateDatabaseAndState`](special-operations.md)).

### A model or a field added, removed, altered

`ProjectState.add_model`, which `CreateModel` calls, files a model state under its key, and `ProjectState.remove_model`, for `DeleteModel`, deletes the key. For the operations named after them, `ProjectState.add_field` puts a field at the end of the model state's `fields`, `ProjectState.remove_field` takes one out, and `ProjectState.alter_field` puts a new field under a name already there. With `preserve_default=False`, `add_field` and `alter_field` file a clone of the field with its default set to `NOT_PROVIDED` (`django/db/migrations/state.py:ProjectState.add_field`; [The field operations, and those on indexes and constraints](field-operations.md)).

### A field or a model renamed

A rename mends part of what used the old name. `ProjectState.rename_field`, for `RenameField`, moves the field to its new name, or raises `FieldDoesNotExist` where the old name is not there. In the same model state it then writes the new name over the old in the names a relation or a composite primary key keeps of its own model's fields (`ForeignObject.from_fields`, `CompositePrimaryKey.field_names`) and in the tuples under `"unique_together"` (and `"index_together"`, which no `Meta` can set any more and an old migration still can). It does the same in each field that `get_references` finds, in any model state, pointing at the renamed field, where that field names its target's fields: `ForeignObject.to_fields` and, on a foreign key's rel, `ForeignObjectRel.field_name` (`django/db/migrations/state.py:ProjectState.rename_field`, `django/db/migrations/utils.py:get_references`). It mends no other option: an index, a constraint or `"order_with_respect_to"` that names the field keeps the old name, and changing it takes an operation of its own ([The autodetector: fields, indexes and constraints](../makemigrations/autodetector-fields.md)).

> **Trap.** `rename_field` breaks the rule of its data: it assigns those attributes of fields on the objects that are there, not on clones, so the state from before the rename, a clone that the rename's database half is handed, has the new name in them while its own `fields` still has the old key.

`ProjectState.rename_model`, for `RenameModel`, files a clone of the model state under the new key, with its `name` changed, puts a clone that names the new model in the place of each field `get_references` finds pointing at the old one, as its target or as a many-to-many field's through model, and then calls `remove_model` for the old key (`django/db/migrations/state.py:ProjectState.rename_model`). It mends fields only: a model state with the old model among its `bases` keeps the old name there, and `ModelState.render`, which resolves a base by that name, can no longer make its class.

Here a `RenameModel` that is in none of harbour's migrations is run on a state that began as the loader's:

```text recording=migrations
migrations.RenameModel('Dock', 'Basin').state_forwards('yard', state)
  ProjectState.rename_model(app_label='yard', old_name='Dock', new_name='Basin')
    ProjectState.remove_model(app_label='yard', model_name='dock')
...
  changed: state.models['yard', 'repair'].fields['dock']: ForeignKey(on_delete=PROTECT, to='yard.dock') became ForeignKey(on_delete=PROTECT, to='yard.basin')
```

### Options, indexes and constraints

None of the methods of `ProjectState` that change a model state's options changes a value in place: a clone has the same values. `ProjectState.alter_model_options` puts a new dictionary in place of `options`, the old entries overlaid with those it is given (`django/db/migrations/state.py:ProjectState.alter_model_options`). Given a list of keys too, as `AlterModelOptions` gives one, it drops each listed key that the new entries lack ([The model operations: `CreateModel`, `DeleteModel`, `RenameModel` and the option operations](model-operations.md)). `ProjectState.alter_model_managers` puts a new list in place of `managers`. The methods named after the operations on indexes and constraints, but for `ProjectState.rename_index`, go through `ProjectState._append_option`, `ProjectState._remove_option` and `ProjectState._alter_option`, which build a new list for `"indexes"` or `"constraints"`. `RenameIndex` calls `rename_index`, which builds its own list, with a clone of the index under the new name; made with `RenameIndex.old_fields` instead of an old name, for an index that the state knows as a tuple of fields under `"index_together"`, it adds an index of those fields under the new name and has `ProjectState.remove_model_options` take the tuple out.

Each of the methods the operations call ends by seeing to the state's registry: if the state has been rendered, the historical models the change touches are taken out of it and, but for a model removed, rendered again from their model states (`django/db/migrations/state.py:ProjectState.reload_model`; [Historical models: `StateApps` and rendering](historical-models.md)).

## `relations`: what points at a model

`ProjectState.relations` maps a model to what points at it: under a model's key, a dictionary by the key of each model with a field pointing at it, and under that the fields by name. A many-to-many field is entered under its target and, where it names a through model, under that too (`django/db/migrations/state.py:ProjectState.resolve_model_field_relations`). The map is made when the property is first read: `ProjectState.resolve_fields_and_relations` sets each field's `name` in every model state, enters every field that has a relation, and puts under the key of each proxy the very dictionary that is under its concrete model's. A relation that names such a proxy is filed under the concrete model, by the mapping that `ProjectState.get_concrete_model_key` answers from.

```text recording=migrations
state = MigrationLoader(None).project_state()
state._relations  ->  None
relations = state.relations
state._relations is relations  ->  True
...
{key: list(fields) for key, fields in relations['fleet', 'port'].items()}  ->  {('crew', 'sailor'): ['pilots_into'], ('fleet', 'ship'): ['home'], ('fleet', 'voyage'): ['calls'], ('office', 'berth'): ['port'], ('office', 'licence'): ['port'], ('yard', 'dock'): ['port']}
...
{key: list(fields) for key, fields in relations['office', 'licence'].items()}  ->  {('crew', 'sailor'): ['pilots_into']}
...
relations['crew', 'veteran'] is relations['crew', 'sailor']  ->  True
```

The map's reader is the autodetector: `MigrationAutodetector._detect_changes` calls `resolve_fields_and_relations` on both of its states before it compares anything (`django/db/migrations/autodetector.py:MigrationAutodetector._detect_changes`; [The autodetector: comparing two project states](../makemigrations/autodetector.md)).
