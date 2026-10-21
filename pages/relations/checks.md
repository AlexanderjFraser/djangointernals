---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The relation checks: `RelatedField.check`

`RelatedField.check` adds to a field's own checks the ones about the relation's other end: that the related name and the related query name are valid, that the model named exists and is not swapped out, and that the names the relation gives that model clash with none of its own. `ForeignObject`, `ForeignKey` and `ManyToManyField` add theirs, among them checks on the target's fields, `on_delete` and the table between.

## The relation checks

A relation is declared in one class and takes effect in two, and what `RelatedField.check` and the classes under it add to a field's checks is about the other end. A model written wrong on purpose, Dive, has mistakes of this kind; it points at Wreck, a model written wrong for the checks of a model's own fields ([The model checks](../models/checks.md)). Like Wreck, it has the office's label and was declared under `isolate_apps`, so it is in a registry made for the purpose and not in the main one.

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

**The two kinds of action are not mixed.** `ForeignKey._check_on_delete` also holds half of a rule that reaches beyond one field, which its comment states: database and Python variants cannot be mixed in a chain of model references. The two kinds are carried out by different parties. A Python-level action is the `Collector`'s, done as it gathers the rows a deletion reaches, and a database-level one is the database's, on rows the collector of `Model.delete` passes over, and nothing Django does for a collected row is done for them (`django/db/models/deletion.py:Collector.collect`) ([Deleting: the `Collector`](../instance/deleting.md)). `DO_NOTHING` counts as neither. A foreign key compares its own action with those of the forward relations of the model it points at, and reports `"fields.E323"` when one is of the other kind. `ManyToManyField._check_on_delete` reports the same id for a relation whose through model Django made: the two foreign keys of that model have Python-level actions, so a database-level relation declared on the model at either end is of the other kind. And `Model._check_related_fields` looks inside one model, for forward relations of both kinds, which is `"models.E050"` (`django/db/models/base.py:Model._check_related_fields`).

Dive has `"chart"`, whose action is the database's, beside `"wreck"` and `"again"`, whose actions are Python's, and the recording has `"models.E050"` for it. It has no `"fields.E323"`. The target of `"chart"` never became a class, and a relation whose target is still a string is not compared; Wreck, which the other two point at, has no forward relations to compare with.

> **Changed in 6.1.** The database-level actions are new.

**A many-to-many relation checks its through model.** A through model has to be an installed model in which the field can tell one foreign key to each end of the relation, and `ManyToManyField.check` counts the through model's foreign keys to the model being checked, which `Model._check_fields` hands it, and to the target. Where the two are different models, none to either is an error, and so is more than one to either unless `ManyToManyRel.through_fields` says which to use; where a model is related to itself, it is more than two that needs `through_fields`. `through_fields`, when given, must name two fields of the through model that are foreign keys to the right models. A through table with the name of another model's table is reported, and arguments that do nothing on such a field, `"null"` and `"validators"` among them, draw warnings (`django/db/models/fields/related.py:ManyToManyField._check_relationship_model`).

The last message of Dive is not about a relation. Its body declares `"id"` without making it the primary key, so `Options._prepare` added an automatic key of the same name, and `Model._check_id_field` reports the pair. Two fields now have the column `"id"`, which `_check_column_name_clashes` would report as well. The recording has no line for that method between `_check_single_primary_key` and `_check_unique_together`: it was not called (`django/db/models/options.py:Options._prepare`).
