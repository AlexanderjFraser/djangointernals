---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Many-to-many relations

A `ManyToManyField` is a relation with no column at either end. Its rows are in a third table, which has a model of its own, the through model. The declaring class gets a `ManyToManyDescriptor`, and so does the other unless the relation is hidden or the declaring class is abstract or swapped out, and the manager a descriptor gives reads the other model through the table between and writes that table's rows with `add`, `remove`, `set` and `clear`.

A voyage calls at several ports, and a port is called at by many voyages. No column of either table can say that, since a column holds one key. The relation needs a table of its own, with a row for each pair and a key to each side in it.

So a many-to-many field is unlike the other fields of a model. It adds nothing to its model's table, an instance holds no value for it, and saving the instance does not write it. What it gives a model is a second model, the **through model**, whose rows are the relation, and what it leaves on the two classes are managers of those rows.

The examples are two fields of the chapter's shipping line ([Models and fields](../models.md)). The first leaves the through model to Django. The second names a model of the project's.

```python
# harbour/fleet/models.py, in the body of Voyage
calls = models.ManyToManyField(Port)

# harbour/crew/models.py, in the body of Sailor
pilots_into = models.ManyToManyField("fleet.Port", through="office.Licence", related_name="pilots")
```

## A field with no column

`ManyToManyField` is a subclass of `RelatedField`, and not of `ForeignKey`. Like every relation it has a rel. From `RelatedField` it has the names the other side goes by, and the wiring through the app registry by which the class it points at gets its attribute, whichever of the two classes is made first ([Relations: a field, its rel and the class at the other end](relations.md)).

As a field it is nearly empty. `ManyToManyField.get_attname_column` returns no column, so the field is not concrete, and `ManyToManyField.db_type` returns `None` (`django/db/models/fields/related.py:ManyToManyField`). `Options.add_field` puts a field that is a many-to-many relation into `Options.local_many_to_many`, and not into `Options.local_fields` (`django/db/models/options.py:Options.add_field`). `Options.fields` leaves a many-to-many field out, so `Options.concrete_fields`, which is made from it, does not have it either. Those are the lists that `Model.__init__` goes through, and `Model._save_table`, which writes the row of a save, goes through `Options.local_concrete_fields`, which is made from `local_fields`.

```text recording=models
names(Voyage._meta.fields), names(Voyage._meta.many_to_many)  ->  ([id, ship, sailed], [calls])
```

Its rel is a `ManyToManyRel`, which holds what describes the table between: `ManyToManyRel.through`, the through model; `ManyToManyRel.through_fields`; `ManyToManyRel.db_constraint`; and whether the relation is symmetrical (`django/db/models/fields/reverse_related.py:ManyToManyRel`). In these lines calls is the field of Voyage:

```text recording=models
type(calls.remote_field).__name__, calls.remote_field.through, calls.remote_field.through._meta.auto_created  ->  ('ManyToManyRel', <class 'harbour.fleet.models.Voyage_calls'>, <class 'harbour.fleet.models.Voyage'>)
calls.column, calls.concrete, calls.many_to_many  ->  (None, False, True)
```

`ManyToManyField.__init__` takes the target as a class or a string, like any relation, and besides it the arguments that describe the table: `through=`, a model to use for it; `through_fields=`, which two of that model's foreign keys to use; `db_table="..."`, a name for the table when Django makes the model; `db_constraint=False`, to leave that table without foreign key constraints; and `symmetrical=`, for a relation of a model to itself.

## The through model

The model behind the table between is made by Django or supplied by the project. Either way it is an ordinary model with a foreign key to each side, and the field's rel comes to hold it as `through`.

### One that Django makes: `create_many_to_many_intermediary_model`

A field given no `through=` gets its model from `create_many_to_many_intermediary_model`, which `ManyToManyField.contribute_to_class` calls, so in the middle of the declaring class's own statement. It is not called for an abstract class, nor for one that has been swapped out. Each class that inherits the field from an abstract base gets a copy of it, and a through model of its own. The function calls `type` with a name, `Model` as the one base, and a dictionary. That makes an ordinary model class, by the metaclass, with everything that involves ([`ModelBase`: a class statement becomes a model](metaclass.md)). This is the statement of Voyage at its field `"calls"`, cut down to the lines that show the through model being made:

```text recording=models
ManyToManyField.contribute_to_class(Voyage, 'calls')
...
  create_many_to_many_intermediary_model(Voyage.calls, Voyage)
    lazy_related_operation(set_managed, Voyage, Port, 'Voyage_calls')
      Apps.lazy_model_operation(function, ('fleet', 'voyage'), ('fleet', 'port'), ('fleet', 'voyage_calls'))
      -> Apps._pending_operations holds 1 under ('crew', 'sailor'), 3 under ('fleet', 'voyage')
    ModelBase.__new__('Voyage_calls', (Model,))
...
      ModelBase.add_to_class(Voyage_calls, 'voyage', a ForeignKey)
      ModelBase.add_to_class(Voyage_calls, 'port', a ForeignKey)
...
      Apps.register_model('fleet', Voyage_calls)
...
  ManyToManyDescriptor.__init__(the rel of Voyage.calls, reverse=False)
    ReverseManyToOneDescriptor.__init__(the rel of Voyage.calls)  (a ManyToManyDescriptor)
```

The class is named after the declaring class and the field, with an underscore between: Voyage_calls. It is given the declaring class's module. Its body is two foreign keys and a `Meta` (`django/db/models/fields/related.py:create_many_to_many_intermediary_model`).

Each foreign key takes its name from the model it points at, in lower case: `"voyage"` and `"port"`. Both have `on_delete=CASCADE`. Both have a `related_name` made of the class's name and `"+"`, which makes their rels hidden, so that neither Voyage nor Port gets an attribute for them. Like any model with no key of its own, the class gets an `"id"`.

The `Meta` names the table. That is the field's `db_table="..."` when one was given, and otherwise the declaring model's table with an underscore and the field's name after it, cut to the longest name the backend allows (`django/db/models/fields/related.py:ManyToManyField._get_m2m_db_table`). It puts the class in the declaring model's application and registry, sets `unique_together` to the two foreign keys, which keeps a pair to one row, and sets `auto_created` to the declaring class itself.

```text recording=models
calls.m2m_db_table(), calls.m2m_column_name(), calls.m2m_reverse_name()  ->  ('fleet_voyage_calls', 'voyage_id', 'port_id')
[(f.name, f.remote_field.related_name, f.remote_field.hidden) for f in calls.remote_field.through._meta.fields if f.is_relation]  ->  [('voyage', 'Voyage_calls+', True), ('port', 'Voyage_calls+', True)]
calls.remote_field.through._meta.unique_together  ->  (('voyage', 'port'),)
```

`auto_created` is how the rest of Django knows such a model. `Apps.get_models` leaves it out unless it is asked not to. A save or a deletion of one of its rows sends no save or delete signal. And the schema editor makes its table as part of making the declaring model's. The statement for the uniqueness of the pair, and those for the indexes of its foreign keys where the backend makes them, are deferred until the editor, a context manager, is left; on SQLite, as recorded, they are a unique index and an index for each key (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.create_model`):

```text recording=models
editor.create_model(Voyage)
...
  SQL CREATE TABLE "fleet_voyage_calls" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "voyage_id" bigint NOT NULL REFERENCES "fleet_voyage" ("id") DEFERRABLE INITIALLY DEFERRED, "port_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED)
...
the editor is left
...
SQL CREATE UNIQUE INDEX "fleet_voyage_calls_voyage_id_port_id_8c446735_uniq" ON "fleet_voyage_calls" ("voyage_id", "port_id")
SQL CREATE INDEX "fleet_voyage_calls_voyage_id_abe1ea81" ON "fleet_voyage_calls" ("voyage_id")
SQL CREATE INDEX "fleet_voyage_calls_port_id_fda96d52" ON "fleet_voyage_calls" ("port_id")
```

The through model is registered before Voyage is. Its foreign key to Voyage therefore waits in the registry until Voyage's own statement ends, as any relation waits for a class that is not yet registered ([Relations: a field, its rel and the class at the other end](relations.md)). `create_many_to_many_intermediary_model` leaves a function of its own there too, `set_managed`: when the declaring model, the target and the through model are all registered, it makes the through model managed if either of the other two is. Voyage's foreign key and this field had each left a function for its target before it, which makes the three that the recording counts under Voyage's key.

### One of the project's: `through=`

A `ManyToManyField` given `through=` takes a model of the project's for its through model, which a project supplies when a pair has something to say for itself. In the harbour a sailor may pilot ships into a port from a certain date:

```python
# harbour/office/models.py
class Licence(models.Model):
    sailor = models.ForeignKey("crew.Sailor", on_delete=models.CASCADE)
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    granted = models.DateField()
```

With `through=` the field makes nothing. The argument is a class or a string, and it is resolved as the target of a relation is: `contribute_to_class` leaves a function with the registry, `resolve_through_model`, which stores the class as the rel's `through` once it and the declaring class are both registered. Sailor names its through model by a string, and the office's models are made after the crew's. These are the lines of Sailor's statement that concern the through model, and the line of Licence's that resolves it:

```text recording=models
ManyToManyField.contribute_to_class(Sailor, 'pilots_into')
...
  lazy_related_operation(resolve_through_model, Sailor, 'office.Licence')
    Apps.lazy_model_operation(function, ('crew', 'sailor'), ('office', 'licence'))
    -> Apps._pending_operations holds 4 under ('crew', 'sailor')
  ManyToManyDescriptor.__init__(the rel of Sailor.pilots_into, reverse=False)
```

```text recording=models
Apps.do_pending_operations(Licence)
  Apps.lazy_model_operation(function)
    resolve_through_model(Sailor, Licence, field=Sailor.pilots_into)
```

The four functions counted under Sailor's key are the one that Ship's `"captain"` left, those of Sailor's foreign key and of this field's target, and `resolve_through_model`. Between the two statements the rel's `through` is the string `"office.Licence"`. The descriptor was set on Sailor all the same; it reads `through` from the rel each time it needs it.

Which of the through model's foreign keys stands for which side is found by looking. The first foreign key to the declaring model is taken for that side, and the first to the target for the other; where the two are one model, the second. A through model with more than one foreign key to a side, or more than two where the sides are one model, needs `through_fields=`, a pair of field names with the declaring side's first (`django/db/models/fields/related.py:ManyToManyField._get_m2m_attr`, `django/db/models/fields/related.py:ManyToManyField._get_m2m_reverse_attr`).

A model of the project's is not `auto_created`, has the uniqueness the project gave it, which for Licence is none, and its foreign keys have accessors like any others: a Sailor has `"licence_set"` as well as `"pilots_into"`.

### A relation of a model to itself

A `ManyToManyField` may point at its own model. Where the two sides have one model name, as they do when they are one model, `create_many_to_many_intermediary_model` names the through model's foreign keys with `"from_"` and `"to_"` before that name. The `"from_"` key is the first of the two, and so the one that the manager at the declaring end takes for its instance's side.

A field whose target is written `"self"` is also symmetrical unless it says otherwise: `ManyToManyField.__init__` takes `symmetrical=` to be true for that target when the argument is not given. For such a field `contribute_to_class` gives the rel a `related_name` made from the field's name and ending in `"+"`, which hides the other end, so the model gets one attribute and not two. And each pair is kept as two rows, one each way, which the manager's `add` writes and its `remove` deletes together, so that the one attribute finds the pair from either of its objects.

## An attribute on each class: `ManyToManyDescriptor`

`ManyToManyField.contribute_to_class` sets a `ManyToManyDescriptor` on the declaring class under the field's name, made with the rel and `reverse=False` (`django/db/models/fields/related.py:ManyToManyField.contribute_to_class`). `ManyToManyField.contribute_to_related_class` runs when both classes are registered. It sets a second one on the target class, under the rel's accessor name and with `reverse=True`, unless the rel is hidden or the declaring model has been swapped for another:

```text recording=models
resolve_related_class(Voyage, Port, field=Voyage.calls)
  ManyToManyField.contribute_to_related_class(Port, the rel of Voyage.calls)
    ManyToManyDescriptor.__init__(the rel of Voyage.calls, reverse=True)
      ReverseManyToOneDescriptor.__init__(the rel of Voyage.calls)  (a ManyToManyDescriptor)
```

The same method gives the field its means of naming the columns of the table between. `ManyToManyField.m2m_column_name` and `ManyToManyField.m2m_reverse_name` return the column for the declaring side and for the other, and `ManyToManyField.m2m_field_name` and `ManyToManyField.m2m_reverse_field_name` the names of the through model's fields behind them. Each is a function set on the field, which looks into the through model at its first call and keeps the answer. They are set while the through model may still be a string, as Sailor's then is. `ManyToManyField.m2m_db_table`, recorded above, is set in `contribute_to_class`.

One descriptor class serves both ends, and the module's docstring says why: a many-to-many relation is symmetrical, and that it is declared on one of its two models is a detail of syntax (`django/db/models/fields/related_descriptors.py`). `ManyToManyDescriptor` is a subclass of `ReverseManyToOneDescriptor`, the descriptor at the far end of a foreign key, and behaves as that does: read on an instance it returns a new manager each time, and assigning to it raises `TypeError` ([Reading and setting related objects](related-objects.md)). It differs in the class of the manager.

```text recording=models
type(Voyage.calls).__name__, Voyage.calls.reverse, type(Port.voyage_set).__name__, Port.voyage_set.reverse  ->  ('ManyToManyDescriptor', False, 'ManyToManyDescriptor', True)
Voyage.calls.rel is Port.voyage_set.rel, Voyage.calls.through is Port.voyage_set.through  ->  (True, True)
[c.__name__ for c in type(spring.calls).__mro__][:3]  ->  ['ManyRelatedManager', 'Manager', 'BaseManagerFromQuerySet']
```

`ManyToManyDescriptor.related_manager_cls` is made once for each descriptor, by `create_forward_many_to_many_manager`, which serves both ends in spite of its name. The class it defines inside itself, `ManyRelatedManager`, has two bases: the class of the default manager of the model the manager will return, and `AltersData` (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`). The model returned is the target at the declaring end and the declaring model at the other. So a voyage's `"calls"` is a manager of ports, with every method that the default manager of Port has.

## The manager reads through a join

Reading the attribute of a many-to-many relation on an instance gives a `ManyRelatedManager`, and fetching its objects sends one statement with one join in it:

```text recording=models
spring.calls is read
  ReverseManyToOneDescriptor.__get__(<Voyage: Voyage object (1)>)  (Voyage.calls, a ManyToManyDescriptor)
    ManyToManyDescriptor.related_manager_cls  (Voyage.calls)
      create_forward_many_to_many_manager(Manager, the rel of Voyage.calls, reverse=False)
      -> the class ManyRelatedManager, whose bases are (Manager, AltersData)
    -> a ManyRelatedManager
list(spring.calls.all())
  ReverseManyToOneDescriptor.__get__(<Voyage: Voyage object (1)>)  (Voyage.calls, a ManyToManyDescriptor)  ->  a ManyRelatedManager
  SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" INNER JOIN "fleet_voyage_calls" ON ("fleet_port"."id" = "fleet_voyage_calls"."port_id") WHERE "fleet_voyage_calls"."voyage_id" = %s ORDER BY "fleet_port"."name" ASC with params (1,)
```

A `ManyRelatedManager` is made for one instance, and its `__init__` works out what depends on the direction: which model it returns, and which of the through model's two foreign keys is the **source**, the one that points at this instance, and which the **target** (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`). At the other end of the relation the two are exchanged, as the first line below shows.

The manager also looks at its instance. The rows of the table between hold this instance's key, and for an instance without one the manager refuses to be made. The `ValueError` comes from reading the attribute, before any method is called:

```text recording=models
spring.calls.source_field_name, spring.calls.target_field_name, lisbon.voyage_set.source_field_name, lisbon.voyage_set.target_field_name  ->  ('voyage', 'port', 'port', 'voyage')
spring.calls.count(), spring.calls.exists()  ->  (3, True)
  SQL SELECT COUNT(*) AS "__count" FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" = %s with params (1,)
  SQL SELECT %s AS "a" FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" = %s LIMIT 1 with params (1, 1)
Voyage(ship=petrel, sailed=datetime.date(2026, 5, 1)).calls  ->  raises ValueError: "<Voyage: Voyage object (None)>" needs to have a value for field "id" before this many-to-many relationship can be used.
```

The manager's `get_queryset` returns the prefetched result when the instance has one for the relation, and otherwise the queryset of its base with one filter added by `_apply_rel_filters`. The filter is on the model the manager returns and goes back over the relation: for a voyage's ports of call it asks for the ports whose voyage has this key. The statement recorded above for a voyage's ports of call joins the table between and no other: the voyage's own table is not in it ([From QuerySet to SQL](../sql.md)).

The filter is marked as sticky: a filter the caller adds straight after it, before any other method of the queryset, is treated as one with it (`django/db/models/query.py:QuerySet._next_is_sticky`). A condition in that filter which itself crosses the relation, one on the year a voyage sailed for instance, is then asked of the manager's own voyage: the ports of a voyage that sailed in another year come back empty. Given to Port's manager in a second `filter`, after one on the voyage, the same condition joins the table between again, and what comes back is each port of this voyage that some voyage of that year calls at.

`count` and `exists` do without the join where they can, as the two statements just quoted show. When the manager's base is the plain manager class, nothing is prefetched, the target foreign key has a database constraint and the backend supports foreign keys, they ask the table between alone.

A query that names the relation, from either model, crosses two tables. The field's path is two hops, the way back over one foreign key of the through model and the way forward over the other (`django/db/models/fields/related.py:ManyToManyField._get_path_info`):

```text recording=models
hops(calls.path_infos)  ->  [Voyage to Voyage_calls, join_field the rel of Voyage_calls.voyage, direct=False, m2m=True; Voyage_calls to Port, join_field Voyage_calls.port, direct=True, m2m=False]
```

## `add`

The `add` of a `ManyRelatedManager` has to end with a row in the table between for each object it was given, without a second row for a pair that is there already, and with anyone listening told which keys were added. Asking the database first which pairs exist costs a statement, and the method does without it when it can.

```text recording=models
spring.calls.add(bergen, lisbon)
  ReverseManyToOneDescriptor.__get__(<Voyage: Voyage object (1)>)  (Voyage.calls, a ManyToManyDescriptor)  ->  a ManyRelatedManager
  ManyRelatedManager.add(<Port: Bergen>, <Port: Lisbon>)  (of <Voyage: Voyage object (1)>)
    ManyRelatedManager._add_base(<Port: Bergen>, <Port: Lisbon>)  (of <Voyage: Voyage object (1)>)
      Atomic.__enter__  (savepoint=False)
        SQL BEGIN
      ManyRelatedManager._add_items('voyage', 'port', <Port: Bergen>, <Port: Lisbon>)
        ManyRelatedManager._get_target_ids  ->  {1, 3}
        ManyRelatedManager._get_add_plan  ->  can_ignore_conflicts=True, must_send_signals=False, can_fast_add=True
        SQL INSERT OR IGNORE INTO "fleet_voyage_calls" ("voyage_id", "port_id") VALUES (%s, %s), (%s, %s) with params (1, 1, 1, 3)
      Atomic.__exit__
        BaseDatabaseWrapper.commit
```

`add` drops any prefetched result for the relation, asks the router which database the through model is written to, and calls `_add_base`, which opens a transaction and calls `_add_items` with the names of the source and target fields and the objects. For a symmetrical relation `_add_base` calls `_add_items` a second time with the two names exchanged, for the rows the other way. All of these are methods of the class that `create_forward_many_to_many_manager` defines (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`).

`_add_items` begins by turning what it was given into a set of keys, in `_get_target_ids`. An instance of the model the manager returns gives its key, once the router's `allow_relation` has agreed to the pair. An instance of any other model is refused with `TypeError`. Anything that is not a model instance is taken for a key, and is prepared as a value of the target field. Being a set, the result counts an object given twice once.

Then it asks `_get_add_plan`, which returns three answers.

The first is whether a conflict can be ignored: whether an insert may be told to pass over a row the table will not take. It can when the through model was made by Django and the backend can do such a thing (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_ignore_conflicts`). The source's comment gives the reason for the first condition. In a model Django made the only possible conflict is on the pair itself, which is exactly the one to pass over. A model of the project's may have other fields, and a conflict over one of those has to be seen.

The second is whether signals must be sent: whether any receiver is connected to `m2m_changed` for this through model. For the second call of a symmetrical relation the answer is no whatever is connected, so the rows the other way are not announced.

The third is whether the fast way is open, and it is the first answer without the second. A receiver has to be told which keys were added, the comment says, and that cannot be known without looking.

On the fast way `_add_items` makes one object of the through model for every key and hands them to `bulk_create` on the through model's default manager, with conflicts ignored, and returns. That is the recording above. Lisbon was a port of that voyage already; the statement names it all the same, and the table drops the row. `INSERT OR IGNORE` is how SQLite's backend writes it.

Otherwise it looks first. `_get_missing_target_ids` asks the table between which of the keys already have a row for this instance, and takes them out. Then `_add_items`, in a transaction block of its own, makes the rows for the missing keys with `bulk_create`, and if signals must be sent, sends `m2m_changed` with the action `"pre_add"` before and `"post_add"` after. The rows carry the values given as `through_defaults=`, and a conflict is ignored in this insert only where the first answer allowed it. This is `_add_items` for the same Voyage model with a receiver connected, the lines around it left out:

```text recording=models
autumn.calls.add(lisbon, leith)
...
      ManyRelatedManager._add_items('voyage', 'port', <Port: Lisbon>, <Port: Leith>)
        ManyRelatedManager._get_target_ids  ->  {2, 3}
        ManyRelatedManager._get_add_plan  ->  can_ignore_conflicts=True, must_send_signals=True, can_fast_add=False
        ManyRelatedManager._get_missing_target_ids
          SQL SELECT "fleet_voyage_calls"."port_id" AS "port" FROM "fleet_voyage_calls" WHERE ("fleet_voyage_calls"."port_id" IN (%s, %s) AND "fleet_voyage_calls"."voyage_id" = %s) with params (2, 3, 2)
          -> {2, 3}
        Atomic.__enter__  (savepoint=False)
        signal m2m_changed, sender Voyage_calls, action='pre_add', reverse=False, model=Port, pk_set={2, 3}
        SQL INSERT OR IGNORE INTO "fleet_voyage_calls" ("voyage_id", "port_id") VALUES (%s, %s), (%s, %s) with params (2, 2, 2, 3)
        signal m2m_changed, sender Voyage_calls, action='post_add', reverse=False, model=Port, pk_set={2, 3}
```

When some of the ports are there already, the receiver hears only of the others. These lines are from the next call, which adds Lisbon again and Bergen:

```text recording=models
ManyRelatedManager._get_target_ids  ->  {1, 3}
ManyRelatedManager._get_add_plan  ->  can_ignore_conflicts=True, must_send_signals=True, can_fast_add=False
ManyRelatedManager._get_missing_target_ids
  SQL SELECT "fleet_voyage_calls"."port_id" AS "port" FROM "fleet_voyage_calls" WHERE ("fleet_voyage_calls"."port_id" IN (%s, %s) AND "fleet_voyage_calls"."voyage_id" = %s) with params (1, 3, 2)
  -> {1}
Atomic.__enter__  (savepoint=False)
signal m2m_changed, sender Voyage_calls, action='pre_add', reverse=False, model=Port, pk_set={1}
SQL INSERT OR IGNORE INTO "fleet_voyage_calls" ("voyage_id", "port_id") VALUES (%s, %s) with params (2, 1)
signal m2m_changed, sender Voyage_calls, action='post_add', reverse=False, model=Port, pk_set={1}
```

```text figure=add-plan
ManyRelatedManager.add(*objs), in one transaction:

  _get_target_ids      the keys of the objects given, as a set
  _get_add_plan        three answers
                         can a conflict be ignored?   the through model was made by Django,
                                                      and the backend can pass over a row that conflicts
                         must signals be sent?        a receiver of m2m_changed is connected for the through model,
                                                      and this is not the second call of a symmetrical relation
                         is the fast way open?        the first, and not the second

  the fast way is open:
      bulk_create: a row for every key, conflicts ignored
      nothing is read first, and no signal is sent

  it is not:
      _get_missing_target_ids    a SELECT on the table between: which of the keys have no row yet
      m2m_changed, "pre_add", pk_set = the missing keys          only if signals must be sent
      bulk_create: a row for each missing key, with through_defaults
                                 conflicts ignored only if a conflict can be ignored
      m2m_changed, "post_add", pk_set = the missing keys         only if signals must be sent

Recorded:   Voyage.calls with no receiver                    yes, no, yes    the fast way
            Voyage.calls with a receiver                     yes, yes, no    a SELECT, the signals, an INSERT
            Sailor.pilots_into, through Licence, no receiver  no, no, no      a SELECT and an INSERT
```

*What `add` sends depends on three facts it finds out first: whether Django made the through model, whether the backend can ignore a conflict, and whether anyone is listening.*

Either way the rows are made by `bulk_create`. No instance of the through model is saved, so a through model's own `save` is not called, and no save signal is sent for a row of it ([QuerySets](../querysets.md)).

## `remove`, `set` and `clear`

`remove`, `set` and `clear` of a `ManyRelatedManager` also change the relation. This is `remove`, with a receiver of `m2m_changed` connected. In this quote and the two after it the lines of the transactions are left out:

```text recording=models
autumn.calls.remove(leith)
  ReverseManyToOneDescriptor.__get__(<Voyage: Voyage object (2)>)  (Voyage.calls, a ManyToManyDescriptor)  ->  a ManyRelatedManager
  ManyRelatedManager.remove(<Port: Leith>)  (of <Voyage: Voyage object (2)>)
    ManyRelatedManager._remove_base(<Port: Leith>)  (of <Voyage: Voyage object (2)>)
      ManyRelatedManager._remove_items('voyage', 'port', <Port: Leith>)
        signal m2m_changed, sender Voyage_calls, action='pre_remove', reverse=False, model=Port, pk_set={2}
        SQL DELETE FROM "fleet_voyage_calls" WHERE ("fleet_voyage_calls"."voyage_id" = %s AND "fleet_voyage_calls"."port_id" IN (%s)) with params (2, 2)
        signal m2m_changed, sender Voyage_calls, action='post_remove', reverse=False, model=Port, pk_set={2}
```

For `remove`, `_remove_items` turns the objects into keys, and in one transaction sends `"pre_remove"`, deletes the rows that have this instance as source and one of the keys as target, and sends `"post_remove"`. It does not look at what is there, and it does not ask whether a receiver is connected: the `"pk_set"` of its signals is the keys it was asked to remove.

`set` makes the relation equal to a list, and the work is done by `set_base`. It first makes a tuple of what it was given, for a reason the comment gives: the argument may be a queryset whose rows a clearing would change. Then, in one transaction, it reads the keys that are there and compares. A key that is there and wanted is left alone. The keys that are there and not wanted go to the removal, and the objects wanted and not there go to the addition, each through the method that `remove` and `add` use. Called with `clear=True` it does not compare: it clears, and adds everything (`django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager`).

```text recording=models
autumn.calls.set([leith, lisbon])
  ReverseManyToOneDescriptor.__get__(<Voyage: Voyage object (2)>)  (Voyage.calls, a ManyToManyDescriptor)  ->  a ManyRelatedManager
  ManyRelatedManager.set([<Port: Leith>, <Port: Lisbon>])  (of <Voyage: Voyage object (2)>)
    ManyRelatedManager.set_base([<Port: Leith>, <Port: Lisbon>])  (of <Voyage: Voyage object (2)>)
      SQL SELECT "fleet_port"."id" AS "id" FROM "fleet_port" INNER JOIN "fleet_voyage_calls" ON ("fleet_port"."id" = "fleet_voyage_calls"."port_id") WHERE "fleet_voyage_calls"."voyage_id" = %s ORDER BY "fleet_port"."name" ASC with params (2,)
      ManyRelatedManager._remove_base(1)  (of <Voyage: Voyage object (2)>)
        ManyRelatedManager._remove_items('voyage', 'port', 1)
          signal m2m_changed, sender Voyage_calls, action='pre_remove', reverse=False, model=Port, pk_set={1}
          SQL DELETE FROM "fleet_voyage_calls" WHERE ("fleet_voyage_calls"."voyage_id" = %s AND "fleet_voyage_calls"."port_id" IN (%s)) with params (2, 1)
          signal m2m_changed, sender Voyage_calls, action='post_remove', reverse=False, model=Port, pk_set={1}
      ManyRelatedManager._add_base(<Port: Leith>)  (of <Voyage: Voyage object (2)>)
        ManyRelatedManager._add_items('voyage', 'port', <Port: Leith>)
```

The voyage called at Bergen and Lisbon and is set to Leith and Lisbon. Bergen is removed, Lisbon is mentioned in no statement after the first, and the addition of Leith, which the quote stops at, goes as any `add` with a receiver does.

`clear` sends `"pre_clear"`, deletes this instance's rows, and sends `"post_clear"`:

```text recording=models
autumn.calls.clear()
  ReverseManyToOneDescriptor.__get__(<Voyage: Voyage object (2)>)  (Voyage.calls, a ManyToManyDescriptor)  ->  a ManyRelatedManager
  ManyRelatedManager.clear()  (of <Voyage: Voyage object (2)>)
    ManyRelatedManager._clear_base()  (of <Voyage: Voyage object (2)>)
      signal m2m_changed, sender Voyage_calls, action='pre_clear', reverse=False, model=Port, pk_set=None
      SQL DELETE FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" = %s with params (2,)
      signal m2m_changed, sender Voyage_calls, action='post_clear', reverse=False, model=Port, pk_set=None
```

`remove` and `clear` delete by calling `delete` on a queryset of the through model, so through the collector ([Deleting: the `Collector`](deleting.md)). As recorded, with a default manager of Port that does not filter and no receiver of a delete signal, that is one statement. Had Port's default manager left some ports out, the rows that point at those ports would have been left too. Where a receiver of a delete signal is connected for the through model, the collector fetches the rows and deletes them by key, and for a through model of the project's it sends those signals.

## `create`, and `through_defaults=`

The `create` of a `ManyRelatedManager` makes an object of the model the manager returns, with the `create` its base has, and then gives it to `add`. `get_or_create` and `update_or_create` do the same, and add only an object they made.

A through model of the project's may have columns that the two keys do not fill. `add`, `set`, `create` and the two beside it take `through_defaults=`, a dictionary of values for the other fields of the rows they make. A value that can be called is called, once for each call of `_add_items` (`django/db/models/utils.py:resolve_callables`).

```text recording=models
ada.pilots_into.add(leith, through_defaults={'granted': datetime.date(2026, 1, 5)})
  ReverseManyToOneDescriptor.__get__(<Sailor: Ada>)  (Sailor.pilots_into, a ManyToManyDescriptor)  ->  a ManyRelatedManager
  ManyRelatedManager.add(<Port: Leith>, through_defaults={'granted': date(2026, 1, 5)})  (of <Sailor: Ada>)
    ManyRelatedManager._add_base(<Port: Leith>, through_defaults={'granted': date(2026, 1, 5)})  (of <Sailor: Ada>)
      ManyRelatedManager._add_items('sailor', 'port', <Port: Leith>, through_defaults={'granted': date(2026, 1, 5)})
        ManyRelatedManager._get_target_ids  ->  {2}
        ManyRelatedManager._get_add_plan  ->  can_ignore_conflicts=False, must_send_signals=False, can_fast_add=False
        ManyRelatedManager._get_missing_target_ids
          SQL SELECT "office_licence"."port_id" AS "port" FROM "office_licence" WHERE ("office_licence"."port_id" IN (%s) AND "office_licence"."sailor_id" = %s) with params (2, 1)
          -> {2}
        SQL INSERT INTO "office_licence" ("sailor_id", "port_id", "granted") VALUES (%s, %s, %s) RETURNING "office_licence"."id" with params (1, 2, '2026-01-05')
```

Licence is the project's model, so no conflict may be ignored: the method looks first, and inserts with a plain `"INSERT"`. The transaction's lines are left out of the quote. Licence's `"granted"` allows no null and has no default, so an `add` without a date has its row refused by the table, with `IntegrityError`, and the transaction is rolled back.

## `m2m_changed`

The changes that the manager of a many-to-many relation makes are announced by one signal, `m2m_changed`, a `ModelSignal` (`django/db/models/signals.py`). Its sender is the through model, and neither of the two models the relation joins. A receiver that cares about a voyage's ports of call connects for the class that the descriptor gives as `ManyToManyDescriptor.through`.

| the argument | what it tells a receiver |
|---|---|
| `"action"` | one of `"pre_add"`, `"post_add"`, `"pre_remove"`, `"post_remove"`, `"pre_clear"` and `"post_clear"` |
| `"instance"` | the instance whose manager was used |
| `"reverse"` | at which end of the relation that manager stood |
| `"model"` | the class of the objects added or removed |
| `"pk_set"` | the keys of those objects, or `None` for the two actions of a clearing |
| `"using"` | the database |

Where a conflict can be ignored, connecting a receiver changes what `add` sends to the database, as its plan shows. It does not change what `remove` and `clear` send.

> **Changed in 6.1.** A receiver of `m2m_changed` is also given `"raw"`. It is true when the relation is being set from serialized data, as the loading of a fixture does: a deserialized object sets its many-to-many relations through `set_base` with `raw=True` (`django/core/serializers/base.py:DeserializedObject.save`).

## The transaction around each change

The `add`, `remove`, `clear` and `set` of a many-to-many manager each run in a block of `atomic`, entered without a savepoint, on the database the router gives for writing the through model (`django/db/transaction.py:atomic`). `_add_base` opens one around its one or two calls of `_add_items`, which opens another around the insert and the signals of the slow way. `_remove_items` and the method behind `clear` open one each. `set_base` opens one around the whole, so the removals and the additions of a `set` are committed together or not at all.

## Saving and deleting

`Model.save` does not write a many-to-many field ([Saving an instance](saving.md)). A relation is changed by its manager, at the moment a method is called, and needs both instances to have keys. So an instance is saved first and related afterwards. A form that edits such a field follows the same order: `ManyToManyField.save_form_data` calls the manager's `set` ([Forms](../forms.md)).

Deleting an instance deletes its rows of the table between, and nothing about a many-to-many field does that. The through model's two foreign keys are ordinary foreign keys, those of a model Django made have `on_delete=CASCADE`, and the collector follows them as it follows any foreign key that points at the object, hidden or not:

```text recording=models
Collector.can_fast_delete(the class Voyage_calls, from_field=Voyage_calls.voyage)  ->  True
...
  SQL DELETE FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."voyage_id" IN (%s) with params (2,)
```

Where a receiver of a delete signal is connected for a through model Django made, the collector fetches those rows and deletes them by key, and sends no signal for them all the same ([Deleting: the `Collector`](deleting.md)). For a through model of the project's, what happens to its rows is what its own foreign keys say.
