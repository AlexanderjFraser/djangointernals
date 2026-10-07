---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The model checks

The model checks are the system checks that read a finished model class for mistakes its class statement could not raise. Two functions in `django/core/checks/model_checks.py` are registered for them, `check_all_models` and `check_lazy_references`. The first calls `Model.check` on the project's models, which runs a fixed series of methods over the class and asks each field and manager to check itself, and each index and constraint for every database it was given; the second reports what is still waiting in the app registry for a model that never came.

A model is assembled while its class statement runs, and the assembly has few chances to refuse anything ([`ModelBase`: a class statement becomes a model](metaclass.md)). A field is made by a call in the class body, before there is a class for it to belong to: it does not yet know its own name, and it cannot see the other fields. A relation to a model that is never declared raises nothing. It leaves a function with the app registry, to be called when the model appears, and the function goes on waiting. And `ordering`, `unique_together` and the constraints of a `Meta` are stored without being compared with the fields: an `Options.ordering` may name a field the model lacks (`django/db/models/options.py:Options.contribute_to_class`).

So a model with a mistake of this kind in it imports cleanly, and fails later, in a migration or at the first query that reaches the part that is wrong. The checks look in between: after every model has been imported, and before the project is used. Each is a function or a method that runs once the classes are finished, with their options complete and every other model at hand, and returns a list of messages. And none of them looks at a row: whether one ship's tonnage is acceptable is a question for validation, which works on an instance ([Validating an instance](validation.md)).

A message is a `CheckMessage`, and in the checks this page describes always an `Error` or a `Warning`. It has an id such as `"fields.E300"`, a text, sometimes a hint, and `CheckMessage.obj`, the thing it is about: a field, for one, or a model class. What becomes of the list, and when the checks are run at all, is the framework's affair (`django/core/checks/messages.py:CheckMessage`) ([The system checks](../commands/checks.md)).

## The two functions the core registers

`check_all_models` and `check_lazy_references` are both in `django/core/checks/model_checks.py`, and both are registered under the tag `Tags.models`. The auth and contenttypes applications register checks of their own under the same tag when they are installed, and the harbour installs neither (`django/contrib/auth/apps.py:AuthConfig.ready`, `django/contrib/contenttypes/apps.py:ContentTypesConfig.ready`). Asked of the harbour once it had started:

```text recording=models
[m.id for m in checks.run_checks()]  ->  []
sorted(c.__name__ for c in checks.registry.registry.get_checks() if checks.Tags.models in c.tags)  ->  ['check_all_models', 'check_lazy_references']
```

The first line is a run of the registered checks over the project, these two among them, and it found nothing to say.

### `check_all_models`

`check_all_models` goes through the models of the registry, or of the applications it was handed, as `Apps.get_models` gives them. That leaves out two kinds: a model Django made for a many-to-many relation that names no through model, and a model that has been **swapped out**, which is one whose `Meta` names a setting, as the user model's does, where that setting names something other than the model itself (`django/apps/config.py:AppConfig.get_models`, `django/db/models/options.py:Options.swapped`) ([The registry and its models](../startup/registry.md)). For each of the others the function calls the class's `check` with its own keyword arguments, the databases among them.

Before the call it makes sure that `check` is still a method. A model body that assigns something else to that name, a field for instance, has overwritten the class method, and the function reports `"models.E020"` for the model without calling what is there.

As it goes it notes what no single model could judge: the table of each managed model that is not a proxy, the name of each index, and the name of each constraint. Afterwards it reports a table that more than one model uses, an index name that occurs twice and a constraint name that occurs twice, the last two under one id when the repeats are within a model and under another when they are among several. Two models on one table is an error unless `settings.DATABASE_ROUTERS` is set. Then it is a warning, whose hint says to verify that the models are routed to separate databases (`django/core/checks/model_checks.py:check_all_models`).

### `check_lazy_references`

`check_lazy_references` reads the registry and no model. A relation hands the registry a function to call when its target exists, and until then the registry keeps it in `Apps._pending_operations` under the label and name of the model it is waiting for ([Relations: a field, its rel and the class at the other end](relations.md)). Once every model has been imported, whatever is still in that dictionary is waiting for a model that will not come, and `_check_lazy_references` makes a message of each (`django/core/checks/model_checks.py:_check_lazy_references`).

What waits there is not the function that was handed over but that function inside wrappers, which `Apps.lazy_model_operation` adds as it waits for one model after another. Each wrapper keeps what it wraps as an attribute named `"func"`: a `functools.partial` has one, and the registry gives its own wrapper the same. The check follows that attribute inward until it reaches an object that has none, gathering the arguments bound on the way (`django/apps/registry.py:Apps.lazy_model_operation`). What it reaches is the function first handed over, or the function inside it where that was a partial, as a relation's is, and it looks that function's module and name up in a short table.

- `"resolve_related_class"`, the function a relation field leaves: the message is `"fields.E307"`, and it is about the field, which was bound to the function as a keyword argument.
- `"connect"`, by which a signal was connected with a sender named by a string: the message is `"signals.E001"`, and it describes the receiver and names the signal.
- `"set_managed"`, which a many-to-many field leaves for the through model Django makes: no message.

A function that is none of these gets `"models.E022"`, with the function's own repr in the text; the one a many-to-many field leaves for a through model named by a string is such a function. Every message ends by saying which half of the reference failed: the application is not installed, or it is installed and has no model of that name.

The function that does the work takes the registry as an argument, and the migrations use it too. Each registry they build for a state of the project's models is checked with it as it is made, and a message there is raised as a `ValueError` (`django/db/migrations/state.py:StateApps.__init__`) ([Migrations](../migrations.md)).

## `Model.check`, in order

`Model.check` is a class method that takes keyword arguments and returns one list: it calls a series of the class's own methods, each of which returns a list of messages, and joins what they return (`django/db/models/base.py:Model.check`).

| method | what it looks for |
|---|---|
| `Model._check_swappable` | in a model that has been swapped out: a setting that does not name a model as `"app_label.ModelName"`, or names one that is not installed |
| `Model._check_model` | a proxy that declares fields |
| `Model._check_managers` | what the `check` of each manager returns |
| `Model._check_fields` | what the `check` of each of the class's own fields returns: those of `Options.local_fields` and of `Options.local_many_to_many` |
| `Model._check_m2m_through_same_relationship` | two many-to-many fields with the same target, the same through model and the same through fields |
| `Model._check_long_column_names` | a column name Django derived that is longer than a database allows, in the model's table or in the table of the through model of one of its many-to-many fields |
| `Model._check_related_fields` | relations whose action on deletion is the database's, beside relations whose action is Python's |
| `Model._check_id_field` | a field named `"id"` that is not the primary key, beside the automatic key of that name |
| `Model._check_field_name_clashes` | a name or an attname that two fields would share: between two parents with tables, between this class and such a parent, or within the class |
| `Model._check_model_name_db_lookup_clashes` | a class name that begins or ends with an underscore, or has two together |
| `Model._check_property_name_related_field_accessor_clashes` | a property with the attname of one of the model's relation fields |
| `Model._check_single_primary_key` | more than one field declared with `primary_key=True` |
| `Model._check_column_name_clashes` | two fields with one column |
| `Model._check_unique_together` | an `Options.unique_together` that is not a list or tuple of lists or tuples, or that names something other than a field of the model's own table |
| `Model._check_indexes` | what the `check` of each index returns, for each database it was given |
| `Model._check_ordering` | an `Options.ordering` together with `Options.order_with_respect_to`; an `ordering` that is not a list or tuple; a name in it that is no field, related field or lookup |
| `Model._check_constraints` | what the `check` of each constraint returns, for each database it was given |
| `Model._check_db_table_comment` | a table comment, on a database that has none |
| `Model._check_composite_pk` | a composite primary key that names something other than a column of the model's own that is neither nullable nor generated, or the same column twice |

*The methods `Model.check` calls, in the order it calls them. Those down to `_check_managers` run for every model, and the others only for one that has not been swapped out.*

Where a row says that a `check` is called, the question is handed on to a part of the model. For Ship, which has nothing wrong with it, these are the methods that handed it on:

```text recording=models
Model._check_managers(Ship)
  BaseManager.check  (a Manager)  ->  []
  -> []
Model._check_fields(Ship)
  AutoFieldMixin.check  (Ship.id)  ->  []
  CharField.check  (Ship.name)  ->  []
  IntegerField.check  (Ship.tonnage)  ->  []
  ForeignKey.check  (Ship.home)  ->  []
  ForeignKey.check  (Ship.captain)  ->  []
  -> []
...
Model._check_indexes(Ship)
  Index.check  (fleet_ship_home_id_f9b8f2_idx)
    Model._check_local_fields(Ship)  ->  []
    -> []
  -> []
Model._check_constraints(Ship)
  CheckConstraint.check  (ship_has_tonnage)
    Model._check_local_fields(Ship)  ->  []
    -> []
  UniqueConstraint.check  (one_name_to_a_port)
    Model._check_local_fields(Ship)  ->  []
    Model._check_local_fields(Ship)  ->  []
    -> []
  -> []
```

`Model._check_local_fields`, under the index and the constraints, is the model's again: it is what a part calls to ask whether the names it was given are fields of this model. The unique constraint calls it twice, once for its fields and once for whatever its condition and expressions name, which for this constraint is nothing.

**Names that collide.** If any of the methods from `_check_id_field` to `_check_single_primary_key` returns a message, `check` does not call `_check_column_name_clashes` at all. The source's comment says that where there are field name clashes, the column name clashes that follow from them are hidden. Of the rules in this group, the one for a class's name gives its reason in its message: a name that begins or ends with an underscore collides with the query lookup syntax.

**Options that name fields.** `unique_together`, the fields of a constraint, and the fields of an index that was given a name are lists of names that were stored when the class was made without being looked up. `_check_local_fields` is given such a list and the name of the option it came from. It refuses a name that is no field of the model, a many-to-many field, a composite primary key, a relation of several columns, and a field that belongs to the table of a parent and not to the model's own. It looks for the names among the model's forward fields only, and a comment gives the reason: so as not to work out before time which relations other models have to this one (`django/db/models/base.py:Model._check_local_fields`).

`Model._check_ordering` has more to allow, since a name in an `ordering` may cross relations. An expression and the random order `"?"` are passed over. A name with double underscores is followed a part at a time through the relations it names, and a part that is no field passes if the field before it has a transform or a lookup of that name. A name without them must be a field's name or attname, the query name of a relation that points at the model, or `"pk"`. The clash with `order_with_respect_to` is not found by the check but remembered for it: `Options.contribute_to_class` notes it as `Options._ordering_clash` when the class is made, and the check reports what it finds there (`django/db/models/base.py:Model._check_ordering`).

## A field checks itself

`Field.check` is a list of calls and nothing else. Each is to a method of the field that looks for one kind of mistake and returns a list (`django/db/models/fields/__init__.py:Field.check`). A subclass with more to look for overrides `check`, calls the one above it and adds its own, so that a field runs the checks of every class it descends from. The recording of Ship names each field's `check` by the class that declares it: `AutoFieldMixin.check` for the key, and `IntegerField.check` for `"tonnage"`, which is a `PositiveIntegerField`, a class that declares none.

The base class asks whether the field's name can be used: it must not end with an underscore, contain `LOOKUP_SEP`, the double underscore between the steps of a lookup, or be `"pk"`. It asks whether the arguments have the form they need: `Field.choices` that can be read as values and labels, with no string among the values longer than a `Field.max_length` the field has; a `Field.db_index` that is `None`, `True` or `False`; validators that can be called; and no `null=True` on a primary key, which it asks only where the default connection's backend does not read empty strings as nulls, since a comment says the question cannot be asked reliably of a backend that takes the two as equal. Of each database it was given it asks whether that database can take the field: an expression given as `Field.db_default`, a column comment, and whatever the backend's own validation object has to say about the field's column (`django/db/models/fields/__init__.py:Field._check_backend_specific_checks`, `django/db/backends/base/validation.py:BaseDatabaseValidation.check_field`). The last entry in the list, `Field._check_deprecation_details`, is for a class that has been withdrawn or deprecated.

Two models were written wrong on purpose, with the office's label. They were declared inside a block of `isolate_apps`, a test utility under which a model class registers with an `Apps` made for the block and not with the main registry, so the harbour's own models are left as they are (`django/test/utils.py:isolate_apps`). Neither class statement raised anything. The first has mistakes in its fields and its options:

```python
class Wreck(models.Model):
    name_ = models.CharField(max_length=40)
    depth = models.DecimalField()
    lost = models.DateField(auto_now=True, default=datetime.date(1900, 1, 1))
    pk = models.IntegerField()

    class Meta:
        app_label = "office"
        ordering = ["tide"]
        constraints = [models.CheckConstraint(condition=models.Q(fathoms__gt=0), name="deep")]
```

These are the lines of its check that returned something, and then the messages themselves:

```text recording=models
Model._check_fields(Wreck)
  AutoFieldMixin.check  (Wreck.id)  ->  []
  CharField.check  (Wreck.name_)  ->  [fields.E001]
  DecimalField.check  (Wreck.depth)  ->  []
  DateTimeCheckMixin.check  (Wreck.lost)  ->  [fields.E160]
  IntegerField.check  (Wreck.pk)  ->  [fields.E003]
  -> [fields.E001, fields.E160, fields.E003]
...
Model._check_ordering(Wreck)  ->  [models.E015]
Model._check_constraints(Wreck)
  CheckConstraint.check  (deep)
    Model._check_local_fields(Wreck)  ->  [models.E012]
    -> [models.E012]
  -> [models.E012]
```

```text recording=models
What Wreck.check returned
    fields.E001, Error, on office.Wreck.name_: Field names must not end with an underscore.
    fields.E160, Error, on office.Wreck.lost: The options auto_now, auto_now_add, and default are mutually exclusive. Only one of these options may be present.
    fields.E003, Error, on office.Wreck.pk: 'pk' is a reserved word that cannot be used as a field name.
    models.E015, Error, on office.Wreck: 'ordering' refers to the nonexistent field, related field, or lookup 'tide'.
    models.E012, Error, on office.Wreck: 'constraints' refers to the nonexistent field 'fathoms'.
```

Two of the messages come from the base class, which refused the names `"name_"` and `"pk"`. The third field message, `"fields.E160"`, shows what a class below it adds.

**`DateTimeCheckMixin`**, a base of the date and time fields, allows one of `auto_now=True`, `auto_now_add=True` and a default, and `"lost"` has two. It also looks at a default that is an actual date or time and not a callable. One that falls within ten seconds of the present moment, or for a field that keeps only a date on the same day, draws a warning. The docstring gives the reason: such a value is probably wrong, being worked out once, as the server starts. The default of `"lost"`, a day in 1900, draws none (`django/db/models/fields/__init__.py:DateTimeCheckMixin`).

**`DecimalField`** is silent about `"depth"`, which was given neither `DecimalField.max_digits` nor `DecimalField.decimal_places`. Whether that is a mistake depends on the database, and the check asks each one it was given (`django/db/models/fields/__init__.py:DecimalField.check`):

```text recording=models
connection.features.supports_no_precision_decimalfield  ->  True
```

On a backend whose `BaseDatabaseFeatures.supports_no_precision_decimalfield` is false the same field is two errors, one for each missing argument, and on any backend it is an error to give one of the two without the other. Where both are given, the check wants a positive number of digits, a number of places that is not negative, and no more places than digits (`django/db/models/fields/__init__.py:DecimalField._check_decimal_places`).

> **Changed in 6.1.** A `DecimalField` may be declared without `max_digits` and `decimal_places` on SQLite, PostgreSQL and Oracle. Before, both were required on every database.

**`CharField`** wants a `max_length` that is a positive integer. It allows none at all where the backend can make an unlimited column, a question it puts to the default connection whatever databases were given. It also asks each database whether it supports a collation on such a column, when the field names one (`django/db/models/fields/__init__.py:CharField._check_max_length_attribute`).

**The automatic keys** check that they are primary keys: `AutoFieldMixin` reports an automatic field declared without `primary_key=True`. And being integer fields they inherit a warning from `IntegerField`, for a `max_length` that will be ignored (`django/db/models/fields/__init__.py:AutoFieldMixin._check_primary_key`).

Other classes add their own in the same way. A file field refuses two of its arguments ([File fields](files.md)). A `GeneratedField` asks each database whether it has generated columns of the kind wanted, and also runs the checks of its output field, folding what they return into messages of its own, one for the errors and one for the warnings (`django/db/models/fields/generated.py:GeneratedField.check`).

The last two messages of Wreck are the model's. `"tide"` in the `ordering` is no field, and the condition of the constraint refers to `"fathoms"`, which `CheckConstraint.check` found by handing the names in its condition to `_check_local_fields`.

## The `"databases"` argument

A model check is told which databases to ask about through one keyword argument, `"databases"`. Some mistakes are mistakes only on a particular database: a column name too long for it, a kind of index it lacks, a column type it cannot make. So `Model.check` reads that argument, a list of aliases that is taken as empty when it is absent. It hands the list to its methods for long column names, indexes, constraints and the table's comment, and all of its keyword arguments to the checks of managers and fields, where the field classes look for the same key (`django/db/models/base.py:Model.check`). In a run of the registered checks the list comes from `CheckRegistry.run_checks`, which passes on the aliases it was given, and every configured alias when it was given `None`; a direct call of `check` without the argument leaves the list empty ([The system checks](../commands/checks.md)).

Each such check loops over the aliases. For each it first asks the router whether the model would be migrated to that database at all, and passes over the alias if not. Then it puts its question to that connection: to its features, or for a column's name or type to its operations and its validation object (`django/db/utils.py:ConnectionRouter.allow_migrate_model`).

With an empty list the loops have nothing to go round, and those checks return nothing. An index and a constraint are checked from inside the loop, so the names of the fields in them go unread as well when no database is given. Wreck, a model whose check constraint names a field it lacks, was checked both ways:

```text recording=models
Wreck.check() with no database named, and with one
    [message.id for message in Wreck.check()]  ->  ['fields.E001', 'fields.E160', 'fields.E003', 'models.E015']
    [message.id for message in Wreck.check(databases=['default'])]  ->  ['fields.E001', 'fields.E160', 'fields.E003', 'models.E015', 'models.E012']
```

The message missing from the first line is the constraint's, and nothing about that mistake depends on a database.

A model can say what it needs of a database. Where its `Meta` lists a feature in `Options.required_db_features`, a check that would complain of a backend without that feature says nothing. A migration, for its part, passes over such a model on a connection that lacks a feature it requires (`django/db/models/options.py:Options.can_migrate`, `django/db/migrations/operations/base.py:Operation.allow_migrate_model`).

## The relation checks

A relation is declared in one class and takes effect in two, and what `RelatedField.check` and the classes under it add to a field's checks is about the other end. A second model written wrong on purpose, Dive, has mistakes of this kind. Like Wreck, the model it points at, it has the office's label and was declared under `isolate_apps`, so it is in a registry made for the purpose and not in the main one.

```python
class Dive(models.Model):
    wreck = models.ForeignKey(Wreck, on_delete=models.SET_NULL)
    again = models.ForeignKey(Wreck, on_delete=models.CASCADE)
    chart = models.ForeignKey("office.Nowhere", on_delete=models.DB_CASCADE)
    id = models.CharField(max_length=5)

    class Meta:
        app_label = "office"
```

These are the lines of its check that returned something, and two that did not, and then the messages:

```text recording=models
Model._check_fields(Dive)
  AutoFieldMixin.check  (Dive.id)  ->  []
  ForeignKey.check  (Dive.wreck)  ->  [fields.E304, fields.E320]
  ForeignKey.check  (Dive.again)  ->  [fields.E304]
  ForeignKey.check  (Dive.chart)  ->  [fields.E300]
  CharField.check  (Dive.id)  ->  []
  -> [fields.E304, fields.E320, fields.E304, fields.E300]
...
Model._check_related_fields(Dive)  ->  [models.E050]
Model._check_id_field(Dive)  ->  [models.E004]
...
Model._check_single_primary_key(Dive)  ->  []
Model._check_unique_together(Dive)  ->  []
```

```text recording=models
What Dive.check returned
    fields.E304, Error, on office.Dive.wreck: Reverse accessor 'Wreck.dive_set' for 'office.Dive.wreck' clashes with reverse accessor for 'office.Dive.again'. Hint: Add or change a related_name argument to the definition for 'office.Dive.wreck' or 'office.Dive.again'.
    fields.E320, Error, on office.Dive.wreck: Field specifies on_delete=SET_NULL, but cannot be null. Hint: Set null=True argument on the field, or change the on_delete rule.
    fields.E304, Error, on office.Dive.again: Reverse accessor 'Wreck.dive_set' for 'office.Dive.again' clashes with reverse accessor for 'office.Dive.wreck'. Hint: Add or change a related_name argument to the definition for 'office.Dive.again' or 'office.Dive.wreck'.
    fields.E300, Error, on office.Dive.chart: Field defines a relation with model 'office.Nowhere', which is either not installed, or is abstract.
    models.E050, Error, on office.Dive: The model cannot have related fields with both database-level and Python-level on_delete variants.
    models.E004, Error, on office.Dive: 'id' can only be used as a field name if the field also sets 'primary_key=True'.
```

**The target exists.** `RelatedField.check` begins, after the base class's checks, with the names the relation will give the other class, and then asks whether there is another class. `RelatedField._check_relation_model_exists` reports a target that is still a string, or a class the registry does not list among its models, which an abstract class never is; that is `"fields.E300"` for `"chart"`. A target that has been swapped out is reported apart, with a hint naming the setting to point at (`django/db/models/fields/related.py:RelatedField.check`).

This is the mistake `check_lazy_references` reports from the registry's side, and the two do not know of each other: in the project's main registry a field like `"chart"` draws both messages. Dive is in a registry of its own, which the registered function does not read, and so only the field's message was recorded.

**What the relation adds to the target does not collide.** A relation gives the class it points at an accessor, `"dive_set"` for both of Dive's foreign keys to Wreck, and gives queries on that class a name to reach back by, here `"dive"`. `RelatedField._check_clashes` compares the two names with the names of the target's own fields and with the accessors of the other relations that point at the target, and the accessor with the names of the target's managers. Because each field checks itself, a clash between two relations is found twice, once from each side, and Dive has `"fields.E304"` for `"wreck"` and again for `"again"`. A relation whose rel is hidden, having been given a related name that ends in a plus sign, has no accessor to clash (`django/db/models/fields/related.py:RelatedField._check_clashes`).

**The target can be pointed at.** `ForeignObject.check` adds that each field the relation refers to on the target exists, that none of them is a composite primary key, and that together they are unique: one of them declared unique, or some of them making up the whole of one of the target's `Options.unique_together` or of a unique constraint of its that has no condition and no expressions, or all of them being exactly the fields of the target's primary key. A foreign key to a primary key passes at once (`django/db/models/fields/related.py:ForeignObject._check_unique_target`, `django/db/models/options.py:Options.total_unique_constraints`).

**The action fits the field.** `ForeignKey.check` adds a warning for a foreign key declared unique, which has the same effect as a `OneToOneField`; that class overrides the method to return nothing. It also adds `ForeignKey._check_on_delete`, which holds what the field's other arguments must be for its action on deletion, the rel's `ForeignObjectRel.on_delete`, to be possible. `SET_NULL` and `DB_SET_NULL` need `null=True`, which `"wreck"` lacks. `SET_DEFAULT` needs a default, and `DB_SET_DEFAULT` a default of the database's. And each of the database-level actions needs a backend that has it, which is asked of each database given (`django/db/models/fields/related.py:ForeignKey._check_on_delete`).

**The two kinds of action are not mixed.** `ForeignKey._check_on_delete` also holds half of a rule that reaches beyond one field, which its comment states: database and Python variants cannot be mixed in a chain of model references. The two kinds are carried out by different parties. A Python-level action is the `Collector`'s, done as it gathers the rows a deletion reaches, and a database-level one is the database's, on rows the collector of `Model.delete` passes over, and nothing Django does for a collected row is done for them (`django/db/models/deletion.py:Collector.collect`) ([Deleting: the `Collector`](deleting.md)). `DO_NOTHING` counts as neither. A foreign key compares its own action with those of the forward relations of the model it points at, and reports `"fields.E323"` when one is of the other kind. `ManyToManyField._check_on_delete` reports the same id for a relation whose through model Django made: the two foreign keys of that model have Python-level actions, so a database-level relation declared on the model at either end is of the other kind. And `Model._check_related_fields` looks inside one model, for forward relations of both kinds, which is `"models.E050"` (`django/db/models/base.py:Model._check_related_fields`).

Dive has `"chart"`, whose action is the database's, beside `"wreck"` and `"again"`, whose actions are Python's, and the recording has `"models.E050"` for it. It has no `"fields.E323"`. The target of `"chart"` never became a class, and a relation whose target is still a string is not compared; Wreck, which the other two point at, has no forward relations to compare with.

> **Changed in 6.1.** The database-level actions are new.

**A many-to-many relation checks its through model.** A through model has to be an installed model in which the field can tell one foreign key to each end of the relation, and `ManyToManyField.check` counts the through model's foreign keys to the model being checked, which `Model._check_fields` hands it, and to the target. Where the two are different models, none to either is an error, and so is more than one to either unless `ManyToManyRel.through_fields` says which to use; where a model is related to itself, it is more than two that needs `through_fields`. `through_fields`, when given, must name two fields of the through model that are foreign keys to the right models. A through table with the name of another model's table is reported, and arguments that do nothing on such a field, `"null"` and `"validators"` among them, draw warnings (`django/db/models/fields/related.py:ManyToManyField._check_relationship_model`).

The last message of Dive is not about a relation. Its body declares `"id"` without making it the primary key, so `Options._prepare` added an automatic key of the same name, and `Model._check_id_field` reports the pair. Two fields now have the column `"id"`, which `_check_column_name_clashes` would report as well. The recording has no line for that method between `_check_single_primary_key` and `_check_unique_together`: it was not called (`django/db/models/options.py:Options._prepare`).

## Managers, constraints and indexes

`BaseManager.check` returns an empty list. It is there to be overridden, and `Model._check_managers` calls it on every manager the model has, inherited ones included (`django/db/models/manager.py:BaseManager.check`). The one manager in Django that overrides it is the manager of the sites application, which checks that the field it filters on exists and is a foreign key or a many-to-many field (`django/contrib/sites/managers.py:CurrentSiteManager.check`).

A constraint and an index are checked one database at a time: their `check` takes the model and a connection, and `Model._check_constraints` and `Model._check_indexes` call it for each alias. The messages are about the model, which is their `CheckMessage.obj`. They are of two kinds.

**What the backend lacks.** `CheckConstraint.check` asks whether the backend has check constraints at all. `UniqueConstraint.check` asks about each thing the constraint uses: a condition, deferral, included columns, expressions, a rule for nulls. `Index.check` asks about conditions, included columns and expressions. A backend without the feature draws a warning and not an error, unless the model requires the feature, and the hints say what follows: the constraint or the index will not be created, or the part the backend lacks will be ignored (`django/db/models/constraints.py:UniqueConstraint.check`, `django/db/models/indexes.py:Index.check`).

**What it refers to.** The fields a constraint names go to `_check_local_fields`. So do the names inside its condition and its expressions, which `Model._get_expr_references` collects by walking a `Q`, an `F` and the source expressions of anything else. `BaseConstraint._check_references` first looks at each reference that has more than one part. One that begins with a relation and goes on with something that is neither a transform nor a lookup of that field would need a join, and is reported as a reference to a joined field (`django/db/models/constraints.py:BaseConstraint._check_references`). A check constraint also warns of a `RawSQL` in its condition, with a message that the constraint will not be validated by `Model.full_clean` ([Constraints and indexes](constraints.md)).

An index is checked for its name as well: it may not begin with an underscore or a digit, and may not be longer than `Index.max_name_length`. Comments beside both rules say they are there for compatibility across databases, and name Oracle.

## Fields that have been removed

The last method `Field.check` calls is `Field._check_deprecation_details`. It reads two attributes of the field's class, `Field.system_check_removed_details` and `Field.system_check_deprecated_details`, each `None` or a dictionary with a text, a hint and an id. A class with the first is an error wherever a model uses it, and a class with the second a warning (`django/db/models/fields/__init__.py:Field._check_deprecation_details`).

That is how a field class is withdrawn without being deleted. `CommaSeparatedIntegerField`, `IPAddressField` and `NullBooleanField` are still in the module, and their messages say why: each is removed except for support in historical migrations. The PostgreSQL application withdraws its case-insensitive text fields and its old JSON field in the same way (`django/contrib/postgres/fields/citext.py`, `django/contrib/postgres/fields/jsonb.py`). No class in the `django` package sets the second attribute.

## A model that has been swapped out

`Model._check_swappable` is the first method `check` calls, and it does something only for a model that has been swapped out, which the options answer as `Options.swapped` and which in Django only the auth application's user model can be ([The options: what a model keeps as `_meta`](options.md), [Authentication, sessions and messages](../auth.md)). It asks the registry for the model the setting names, and reports a value that is not of the form `"app_label.ModelName"`, or a model of that name that is not installed (`django/db/models/base.py:Model._check_swappable`). For such a model `check` then runs the check of a proxy and those of the managers, and stops. Its fields, its names and its options are not read. A swapped-out model is not migrated, and its manager refuses to be read from the class (`django/db/models/options.py:Options.can_migrate`, `django/db/models/manager.py:ManagerDescriptor.__get__`).

The registered function does not get that far: the models `check_all_models` goes through leave a swapped-out one out, so the shortened series runs only when something calls `check` on such a model itself. What points at one is still checked from the other end: a relation whose target has been swapped out is the error `"fields.E301"`, on the field.
