---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Validating an instance

`Model.full_clean` validates one instance of a model in four steps, `Model.clean_fields`, `Model.clean`, `Model.validate_unique` and `Model.validate_constraints`, and raises a single `ValidationError` holding what all four found. It sends a query for each foreign key, each unique value and each constraint it tests, and `Model.save` does not call it.

A row has to obey rules of three kinds. Each value has to suit its field. Some values must not be those of any other row. And the conditions a model states over a whole row, its constraints, have to hold. The database enforces most of this by itself, and its answer to a statement that breaks a rule is an exception for the statement.

Validation asks the same questions before the statement is sent, in Python, so that the answers come back as messages, each filed under the name of the field it concerns and all of them together. Much of this cannot be decided from the instance alone: whether the row a foreign key points at exists and whether a value is taken are facts about tables, and Django leaves a constraint's condition to the database to evaluate. So validation sends queries of its own. They are plain reads: what `full_clean` reports was true when each of them ran, and the table's own constraints still decide when the row is written.

The steps run in a fixed order, and a set of field names runs through them: the **excluded names**. A field whose value fails a step is added to the set, and the unique checks and the constraints, which come last, leave out every rule that involves a name in it. A value that is not even a number is reported once, as not a number, and is not looked for in the table.

```text figure=the-four-steps
Model.full_clean(exclude=None, validate_unique=True, validate_constraints=True)
The set of excluded names starts as the argument, or empty. Each step but the second is handed it.

1  Model.clean_fields           each field not passed over cleans its value, and the result is put on the instance
                                a foreign key asks the database whether the row it points at exists
       errors: by field name

2  Model.clean                  does nothing unless the model overrides it; runs whether or not step 1 found errors
       errors: by field name, or under "__all__"

   every field name with an error so far is added to the set

3  Model.validate_unique        unique fields, unique_together and the checks by date: one query for each check that is made
       errors: by field name, or under "__all__" for a check of several fields

   every field name with an error so far is added to the set

4  Model.validate_constraints   each constraint of the model and of its parents is asked to test the instance, which takes one query at most, and none if a field it tests is excluded
       errors: under "__all__"; by field name where a unique constraint on one field answers with the code "unique"

If any step found an error: raise ValidationError, with the errors of all four by name.
```

*The four steps of `Model.full_clean`. Each step's errors are kept, the next step runs all the same, and a field that has failed is left out of the unique checks and the constraints that follow.*

The examples are the ships of a shipping line. A Ship has a name, which it inherits from an abstract base and prints itself as, and three fields of its own:

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

## A call of its own

`Model.save` sends what the instance holds and does not validate it first ([Saving an instance](saving.md)). A new Ship with the name and the home port of a ship that exists, and a tonnage of zero, breaks both of the model's constraints, and the insert is sent all the same:

```text recording=models
Ship(name='Petrel', tonnage=0, home=bergen).save()  ->  raises IntegrityError: CHECK constraint failed: ship_has_tonnage
  SQL INSERT INTO "fleet_ship" ("name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s) RETURNING "fleet_ship"."id" with params ('Petrel', 0, 1, None)
```

The refusal is the database's, and it names one of the two constraints the row breaks. To be told beforehand, and to be told everything, is a separate call, `Model.full_clean`, which code that wants it has to make (`django/db/models/base.py:Model.full_clean`). In Django's own code one caller does: a model form, in three calls, which the section on `BaseModelForm._post_clean` below takes apart (`django/forms/models.py:BaseModelForm._post_clean`).

Validation is not the system checks. `Model.check` examines a model class, for mistakes in its declaration, and `full_clean` examines one instance, for values that break the model's rules ([The model checks](checks.md)).

## `Model.full_clean` and the excluded names

`Model.full_clean` takes names to exclude and a switch for each of the last two steps. It copies the names into a set of its own, or starts an empty one, and calls each step inside a `try`. A `ValidationError` from a step does not end the method: its errors are merged into one dictionary, by field name, and the next step runs (`django/db/models/base.py:Model.full_clean`, `django/core/exceptions.py:ValidationError.update_error_dict`).

Before the third step, and again before the fourth, every key of that dictionary other than `"__all__"` is added to the set. The comments at those two places state the intent: the unique checks, and then the constraints, are run only for fields that passed validation. This is a Ship with no name and a tonnage below zero, with the cleaning of its home port and what its unique checks did left out:

```text recording=models
Ship(name='', tonnage=-5, home=bergen).full_clean()
  Model.full_clean()  (a Ship)
    Model.clean_fields(exclude=set())
      Field.clean('')  (Ship.name)  raises ValidationError
      Field.clean(-5)  (Ship.tonnage)  raises ValidationError
...
    Model.clean  ->  None
    Model.validate_unique(exclude={'name', 'tonnage'})
    Model.validate_constraints(exclude={'name', 'tonnage'})
      CheckConstraint.validate(Ship, <Ship: >, exclude={'name', 'tonnage'})  (ship_has_tonnage)
      UniqueConstraint.validate(Ship, <Ship: >, exclude={'name', 'tonnage'})  (one_name_to_a_port)
    raises ValidationError
  the caller catches ValidationError, whose message_dict holds
    'name': ['This field cannot be blank.']
    'tonnage': ['Ensure this value is greater than or equal to 0.']
```

Both names are in the set from the third step on. Each of the model's constraints was asked to validate the instance and sent nothing: the check constraint is a condition on the tonnage, the unique constraint has `"name"` among its fields, and each stood down on finding a field of its own excluded.

`Model.clean` is the one step that is not told. It takes no arguments.

## `Model.clean_fields`: each field cleans its own value

`Model.clean_fields` goes through `Options.fields`, the fields of the model and of its parents apart from many-to-many fields, and has each clean the value the instance holds under the field's attname (`django/db/models/base.py:Model.clean_fields`, `django/db/models/options.py:Options.fields`). It passes over a field whose name is among the excluded names, a generated field, and a value that is a placeholder for a default the database will supply: a field with `db_default=` and no `default=` gives a new instance a `DatabaseDefault` object in place of a value ([The field classes](field-types.md)). And it passes over a field that has `blank=True` when the value is among the field's empty values, `Field.empty_values`, which in the base class are `None`, the empty string and the empty list, tuple and dictionary (`django/db/models/fields/__init__.py:Field.empty_values`).

The last of these is a decision, and the source's comment owns up to it: validation is skipped for an empty value where a blank is allowed, and the developer is responsible for making sure the value is valid. The same rule covers the key of a new instance. An automatic primary key has no value before the first save, and `AutoFieldMixin.__init__` sets `blank=True` on every such field, so the key is passed over. A new Ship with no captain has three of its five fields cleaned:

```text recording=models
Model.clean_fields(exclude=set())
  Field.clean('Tern')  (Ship.name)  ->  'Tern'
  Field.clean(50)  (Ship.tonnage)  ->  50
  Field.clean(2)  (Ship.home)
    SQL SELECT %s AS "a" FROM "fleet_port" WHERE "fleet_port"."id" = %s LIMIT 1 with params (1, 2)
    -> 2
```

For every other field the method calls `Field.clean` with the value and the instance, and assigns what comes back to the instance under the same attname. So `full_clean` is not a pure test: it can change the instance. Here tern is a new Ship that was made with its tonnage given as the string `"7"`, and the statements its validation sent are left out:

```text recording=models
tern.tonnage  ->  '7'
tern.full_clean()  ->  None
tern.tonnage  ->  7
```

Every field is tried, and one `ValidationError` holding the errors by field name is raised at the end.

### `Field.clean`: convert, validate, run the validators

`Field.clean` makes three calls: `Field.to_python` on the value, then `Field.validate` and `Field.run_validators` on what that returned, which is also what `clean` returns (`django/db/models/fields/__init__.py:Field.clean`).

`Field.to_python` converts the value to the Python type the field deals in, and raises `ValidationError` for one it cannot convert. In `Field` itself it returns the value untouched; the field classes override it ([The field classes](field-types.md)).

`Field.validate` tests the converted value against what the field was declared with. A field that is not editable is not tested at all. Otherwise, if the field has choices and the value is not empty, the value must be one of them, a choice inside a named group included. Then `None` is refused unless the field has `null=True`, and any empty value is refused unless it has `blank=True` (`django/db/models/fields/__init__.py:Field.validate`). A field class may replace these tests: `AutoFieldMixin.validate` does nothing, so none of them is made for an automatic key.

`Field.run_validators` calls each of the field's validators with the value, or none of them if the value is empty, and raises the errors of all of them together. A validator's message is replaced by the field's own message for the same error code where the field has one (`django/db/models/fields/__init__.py:Field.run_validators`). The list, `Field.validators`, is the class's `Field.default_validators` followed by the ones the field was given, and some field classes add to it: an integer field the range the database backend gives for its column, a `CharField` its maximum length ([A field: the base class](fields.md)). The validators themselves, in `django/core/validators.py`, are described with [Forms](../forms.md).

The messages come from `Field.error_messages`, a dictionary built once for each field: the `default_error_messages` of every class the field's class inherits from, the most general first, and over them whatever the field was given as `error_messages=`.

These are single fields asked to clean a value, with `None` or an empty Ship where the instance is expected:

```text recording=models
Ship._meta.get_field('tonnage').clean('7', None), Ship._meta.get_field('name').clean(7, None)  ->  (7, '7')
Ship._meta.get_field('name').clean('', None)  ->  raises ValidationError: ['This field cannot be blank.']
Ship._meta.get_field('captain').clean(None, None)  ->  None
Ship._meta.get_field('home').clean(None, None)  ->  raises ValidationError: ['This field cannot be null.']
Ship._meta.get_field('home').clean(99, Ship())  ->  raises ValidationError: ['port instance with id 99 is not a valid choice.']
  SQL SELECT %s AS "a" FROM "fleet_port" WHERE "fleet_port"."id" = %s LIMIT 1 with params (1, 99)
```

The first line is conversion, by `to_python` in two field classes, and the others are `validate`.

### A foreign key asks the database

`ForeignKey.validate` sends a query, as the last of the calls above did. It runs the base tests and then, for a value that is not `None`, asks whether the row the key points at exists (`django/db/models/fields/related.py:ForeignKey.validate`). The queryset is built on the related model's base manager, on the database the router names for reading that model, filtered to the key and then by the field's `limit_choices_to`, and it is asked `exists`. A key that points at a real row which `limit_choices_to` leaves out therefore fails as well. The link from a child model to its parent's row is not tested: the method returns at once for a field that is a parent link.

So a `full_clean` sends its first queries in its first step, one for each foreign key and one-to-one field that is cleaned, has a value and is not a parent link.

## `Model.clean`: the model's own step

`Model.clean` is empty. It is the place for a model's rules about several fields at once, and does nothing until a model overrides it (`django/db/models/base.py:Model.clean`).

It runs even when fields have failed, and the comment in `full_clean` gives the reason: a form's `clean` is run even if other validation fails, and the model's is treated the same for consistency. So an override cannot assume that the values it reads have been cleaned.

Where its error is filed depends on the error's shape. A `ValidationError` made from a message is filed under `"__all__"`, as an error about no field in particular. One made from a dictionary is filed under the dictionary's keys, and each of those keys joins the excluded names for the steps that follow.

## `Model.validate_unique`: is the value taken?

`Model.validate_unique` makes a list of checks from the model's description, runs each as a query, and raises the errors together (`django/db/models/base.py:Model.validate_unique`).

### The list: `Model._get_unique_checks`

A **unique check** is a model class and a tuple of field names: among that model's rows, no other may have this instance's values for those fields. `Model._get_unique_checks` gathers them from the instance's class and from each class in `Options.all_parents`, its ancestors that are models and not abstract. A child's row is a row of each parent's table too, and a parent's checks are listed with the parent as the model to query (`django/db/models/base.py:Model._get_unique_checks`, `django/db/models/options.py:Options.all_parents`). For each of those classes it lists:

- each entry of `Options.unique_together`, as a check of several fields;
- each field declared unique, as a check of one field. A primary key counts: `Field.unique` is true for a field that was given `unique=True` or is the primary key (`django/db/models/fields/__init__.py:Field.unique`). A `OneToOneField` sets `unique=True` on itself;
- a primary key of several columns, as one check of its fields.

A check with an excluded name among its fields is dropped as the list is made, which is where the thread from the earlier steps is picked up.

One source of unique rules is absent. A `UniqueConstraint` in the model's `Meta` is added only when the method is called with `include_meta_constraints=True`, and then only if it is one of `Options.total_unique_constraints`, those with neither a condition nor expressions. `validate_unique` does not ask for them: they are tested in the fourth step, by the constraints themselves. The caller that does ask is a model formset, which uses the list to compare its own forms with each other (`django/forms/models.py:BaseModelFormSet.validate_unique`).

### The queries: `Model._perform_unique_checks`

`Model._perform_unique_checks` makes a check only when the instance has something to compare for every field of it; a check that is short of one is dropped without a query (`django/db/models/base.py:Model._perform_unique_checks`). `None` is nothing to compare. Nor is the empty string on a database that stores it as null, nor a placeholder for a database default that is not a plain value. And a field of the primary key is left out when the instance is not being added, with the comment that there is no need to check for a unique primary key when editing.

What is left becomes a filter on the default manager of the check's model, `ModelBase._default_manager`, and `exists` is called on it. When the instance is not being added and has a key, its own row is first excluded from the queryset, by the primary key of the check's model, which for a parent's check is the parent's key.

Validation's queries do not all go through one manager. A foreign key's target is looked for through the related model's base manager, and a taken value through the model's default manager, so a default manager whose queryset leaves rows out leaves them out of the unique checks ([Managers](managers.md)).

A check that finds a row yields an error, filed under the field's name for a check of one field and under `"__all__"` for a check of several. The message comes from `Model.unique_error_message`: for one field the field's own message for `"unique"`, and for several a sentence that lists the fields' labels, with the code `"unique_together"` (`django/db/models/base.py:Model.unique_error_message`).

### `unique_for_date` and its relatives: `Model._perform_date_checks`

A field may be declared unique for the date in another field, or for that date's year or month, with `unique_for_date=`, `unique_for_year=` or `unique_for_month=`. `_get_unique_checks` returns these as a second list, the **date checks**, dropping any whose field or whose date field is excluded, and `Model._perform_date_checks` runs them (`django/db/models/base.py:Model._perform_date_checks`). Each is a query on the default manager for a row with this instance's value in the field and the same day, month and year in the date field, or the same year, or the same month. An instance with no date is not checked, and a saved instance's own row is excluded, here by the instance's own key. The error is filed under the field's name, with the message `Model.date_error_message` makes.

Django reads these options where the checks are listed and in the field that stores them, and nowhere else: no rule in the table stands behind this query.

### A unique field that is taken

A new Ship is given, as its captain, a sailor who commands another ship, with the name and the home port of a ship that exists and a tonnage of zero. Its first two steps, which found nothing wrong, are left out, and so is what the two constraints did, a query and an error each:

```text recording=models
Ship(name='Petrel', tonnage=0, home=bergen, captain=cora).full_clean()
  Model.full_clean()  (a Ship)
...
    Model.validate_unique(exclude=set())
      Model._get_unique_checks(exclude=set())  ->  unique checks [(Ship, ('id',)), (Ship, ('captain',))], date checks []
      Model._perform_unique_checks
        SQL SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."captain_id" = %s LIMIT 1 with params (1, 3)
        -> errors for ['captain']
      Model._perform_date_checks  ->  no errors
      raises ValidationError
    Model.validate_constraints(exclude={'captain'})
...
  the caller catches ValidationError, whose message_dict holds
    'captain': ['Ship with this Captain already exists.']
    '__all__': ['Constraint “ship_has_tonnage” is violated.', 'Ship with this Name and Home already exists.']
```

The list for Ship has two checks, on the primary key and on the one-to-one field, and not the constraint over the name and the port. The check on the key sent nothing, the key of a new Ship being `None`. The check on the captain found a row, and the fourth step was called with `"captain"` in the set. The two errors under `"__all__"` are the constraints'.

## `Model.validate_constraints`: the constraints test the instance

`Model.validate_constraints` takes its list from `Model.get_constraints`: the constraints of the instance's class, from `Options.constraints`, and those of each parent that has any. It asks the router which database the instance would be written to, and calls `validate` on each constraint in turn with the model class the constraint belongs to, the instance, the excluded names and that database's alias (`django/db/models/base.py:Model.validate_constraints`, `django/db/models/options.py:Options.constraints`). What a constraint is, and the SQL it gives a table, are in [Constraints and indexes](constraints.md).

Every constraint is asked, and an error from one does not stop the next. The method files an error under a field's name in one case, that of a constraint over a single field whose error has the code `"unique"`, and under `"__all__"` otherwise.

### A check constraint is evaluated without a table

A `CheckConstraint` holds a condition, for Ship that the tonnage is greater than zero. `CheckConstraint.validate` does not evaluate it in Python. It has the database evaluate it, against the instance's values, in a statement that reads no table (`django/db/models/constraints.py:CheckConstraint.validate`).

The values come from `Model._get_field_expression_map`, which returns a dictionary from names to expressions. The instance's value for a field of the model class is there under the field's name and again under its attname, so a condition written with either finds it, and an excluded field is not there at all. The primary key is under `"pk"`, and a generated field stands as its own expression with every reference in it replaced by the instance's value (`django/db/models/base.py:Model._get_field_expression_map`).

Then `Q.check` builds a `Query` with no model. It adds each entry of the dictionary as an annotation, adds the constant 1 under the name `"_check"` as the one thing selected, and adds the condition as the query's filter, so that where the condition says `"tonnage"` the query finds the annotation of that name. If a row comes back the condition holds (`django/db/models/query_utils.py:Q.check`).

```text recording=models
Ship._meta.constraints[0].validate(Ship, Ship(name='Tern', tonnage=0, home=leith))  ->  raises ValidationError: ['Constraint “ship_has_tonnage” is violated.']
  SQL SELECT %s AS "_check" WHERE COALESCE((%s > %s), %s) = %s with params (1, 0, 0, True, True)
Ship._meta.constraints[0].validate(Ship, Ship(name='Tern', tonnage=0, home=leith), exclude={'tonnage'})  ->  None
...
Ship._meta.constraints[0].validate(Ship, Ship(name='Tern', tonnage=None, home=leith))  ->  None
  SQL SELECT %s AS "_check" WHERE COALESCE((NULL > %s), %s) = %s with params (1, 0, True, True)
```

The first statement has no `"FROM"`: the instance's tonnage and the constraint's limit, both zero here, are among its parameters.

The second call sent nothing. Before it sends anything, `validate` asks whether the condition refers to an excluded field, directly or through a generated field whose expression does, and returns if so (`django/db/models/constraints.py:BaseConstraint._expression_refs_exclude`).

The last call is a Ship with no tonnage, and it passes. The `"COALESCE"` round the comparison is what lets it. `validate` adds it on a backend that can compare boolean expressions, with the comment that a check constraint does not fail when its condition is unknown: in SQL a comparison with null is neither true nor false, and a table's check constraint lets such a row in.

When the statement raises a `DatabaseError`, `Q.check` logs a warning to the logger `"django.db.models"` and answers that the condition holds. Inside an `atomic` block it runs the statement in an `atomic` block of its own, a savepoint that a failed statement is rolled back to. A check constraint's condition that the database cannot evaluate away from its table therefore passes validation, and is left to the table.

A violation raises `ValidationError` with the constraint's own message and code ([Constraints and indexes](constraints.md)).

### A unique constraint looks for another row

`UniqueConstraint.validate` asks what a unique check asks, and builds the queryset itself: the default manager of the model, on the database it was told to use, filtered to this instance's values (`django/db/models/constraints.py:UniqueConstraint.validate`).

For a constraint over fields it reads each field's value from the instance, or for a generated field takes its expression from `_get_field_expression_map`. An excluded field ends the method at once. So does a value of `None`, with the comment that a constraint containing a null cannot be violated, since in SQL null does not equal null; that holds unless the constraint was declared with `nulls_distinct=False`. So do the empty string on a database that stores it as null, and a placeholder for a database default that is not a plain value. A constraint over expressions is tested by filtering for rows where each expression, computed from the row, equals the same expression computed from the instance's values, which again come from `_get_field_expression_map`. It stands down if any of its expressions refers to an excluded field.

The instance's own row is excluded as in the unique checks. Then, for a constraint without a condition, the method calls `exists`. A new Ship with a taken name and port is refused, and the saved Petrel is not refused for being itself:

```text recording=models
Ship._meta.constraints[1].validate(Ship, Ship(name='Petrel', tonnage=5, home=bergen))  ->  raises ValidationError: ['Ship with this Name and Home already exists.']
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE ("fleet_ship"."home_id" = %s AND "fleet_ship"."name" = %s) LIMIT 1 with params (1, 1, 'Petrel')
Ship._meta.constraints[1].validate(Ship, petrel)  ->  None
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE ("fleet_ship"."home_id" = %s AND "fleet_ship"."name" = %s AND NOT ("fleet_ship"."id" = %s)) LIMIT 1 with params (1, 1, 'Petrel', 1)
```

A constraint with a condition applies only to rows that meet the condition, and the instance may be one that does not. For such a constraint the method sends one statement through `Q.check`, the method a check constraint uses: it asks whether the instance's values meet the condition, and whether a row with the same values which also meets it exists. It sends nothing when the condition refers to an excluded field.

A constraint over fields, without a condition, whose message is still the default raises the error `Model.unique_error_message` makes, the one a unique field or `unique_together` would raise; the source's comment says this is kept for backward compatibility. A code given to such a constraint without a message is not used, since the test is on the message alone. Every other unique constraint raises its own message with its own code.

The borrowed error brings its code with it, and the code decides where the error is filed: `"unique"` over one field, the one case `validate_constraints` files under the field's name, and `"unique_together"` over several.

Two constraints made for the purpose, the first over the name alone and the second over the name among ships of more than a hundred tons, are each asked about a new Ship called Petrel:

```text recording=models
models.UniqueConstraint(fields=['name'], name='one_name').validate(Ship, Ship(name='Petrel', tonnage=5, home=bergen))  ->  raises ValidationError: ['Ship with this Name already exists.']
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 1 with params (1, 'Petrel')
models.UniqueConstraint(fields=['name'], condition=Q(tonnage__gt=100), name='big_names').validate(Ship, Ship(name='Petrel', tonnage=500, home=bergen))  ->  raises ValidationError: ['Constraint “big_names” is violated.']
  SQL SELECT %s AS "_check" WHERE (%s > %s AND EXISTS(SELECT %s AS "a" FROM "fleet_ship" "U0" WHERE ("U0"."name" = %s AND "U0"."tonnage" > %s) LIMIT 1)) with params (1, 500, 100, 1, 'Petrel', 100)
```

The first raised the sentence a unique field raises. The second sent the one statement of a constraint with a condition, whose `"EXISTS"` holds the search for another row, and raised the constraint's own message.

> **Changed in 5.2.** A unique constraint over fields and without a condition used to answer as a unique field does whatever message it had been given. A message given to the constraint is now used.

## The error that is raised

`Model.full_clean` raises one `ValidationError`, made from the dictionary it has been filling (`django/core/exceptions.py:ValidationError`). A `ValidationError` is made from a single message with a code and parameters, from a list of errors, or from a dictionary of names and lists of errors, and this one is of the last kind: it keeps the dictionary as `ValidationError.error_dict`. Each error in those lists is itself a `ValidationError` with a code, kept as `ValidationError.code`, so a caller can tell a value that is taken from one that is blank without reading the words. `ValidationError.message_dict` gives the same dictionary with each error rendered as its message.

The key `"__all__"` is the constant `NON_FIELD_ERRORS`, and it is where an error goes that is about the row and not about one field: from a `Model.clean` that raises a plain message, from a unique check over several fields, and from a constraint, unless it is a unique constraint over one field that answers with the code `"unique"` (`django/core/exceptions.py:NON_FIELD_ERRORS`). `Model.clean_fields`, `Model.validate_unique` and `Model.validate_constraints` each raise in the same shape when called on their own, as a model form calls the last two.

## A model form's three calls: `BaseModelForm._post_clean`

`BaseModelForm._post_clean`, the one caller of `Model.full_clean` in Django's own code, runs once the form's own fields have been cleaned ([Forms](../forms.md)). It works out a set of names to exclude, copies the form's cleaned values onto the instance, and calls `full_clean` with that set and with `validate_unique=False` and `validate_constraints=False`: the first two steps and no more. Then it calls the form's own `BaseModelForm.validate_unique` and `BaseModelForm.validate_constraints`, each of which works the set out again and calls the instance's method of the same name (`django/forms/models.py:BaseModelForm._post_clean`). Each of the later calls waits on a flag that `BaseModelForm.clean` sets, so that, as a comment in `BaseModelForm.__init__` says, a form that overrides `clean` without calling the inherited method gets neither. The set comes from `BaseModelForm._get_validation_exclusions`: every field of the model that is not on the form, that the form's `Meta` leaves out, that already has an error in the form, or whose form field is not required and came back empty while the model's field does not allow a blank. For the first call alone, each `InlineForeignKeyField` of the form, which stands for the foreign key of an inline formset, is added to it. Working the set out again before each later call is how a field that failed in `Model.clean_fields`, whose error is by then among the form's, comes to be left out of the unique checks and the constraints (`django/forms/models.py:BaseModelForm._get_validation_exclusions`).

## New or saved: `adding`, on `Model._state`

Whether another row has the same values is two questions. For an instance with no row, any such row is a conflict. For one that has a row, its own has those values too and must not count. Validation tells the two apart by an attribute of the instance's state, `ModelState.adding`, which is true from the moment an instance is made until it is saved, and false for an instance made from a row (`django/db/models/base.py:ModelState`) ([An instance and its state](instances.md)).

It is read by `Model._perform_unique_checks`, by `Model._perform_date_checks` and by `UniqueConstraint.validate`. This is the validation of a Ship that was saved earlier, from its third step on and with the check constraint left out:

```text recording=models
Model.validate_unique(exclude=set())
  Model._get_unique_checks(exclude=set())  ->  unique checks [(Ship, ('id',)), (Ship, ('captain',))], date checks []
  Model._perform_unique_checks  ->  no errors
  Model._perform_date_checks  ->  no errors
Model.validate_constraints(exclude=set())
  UniqueConstraint.validate(Ship, <Ship: Heron II>, exclude=set())  (one_name_to_a_port)
    SQL SELECT %s AS "a" FROM "fleet_ship" WHERE ("fleet_ship"."home_id" = %s AND "fleet_ship"."name" = %s AND NOT ("fleet_ship"."id" = %s)) LIMIT 1 with params (1, 1, 'Heron II', 3)
```

The unique check on the key is in the list and is not made, and the unique constraint's statement ends by leaving out the row with that key.

A key alone does not say that an instance has a row, and the comment on the attribute in the source gives that as the reason the flag exists: it is necessary for the correct validation of new instances with explicit primary keys, keys that are set by the caller and not by the database. Such an instance has its key before it has a row, and for it the unique check on the key is the one that matters. This Ship was made with the key of a row that exists:

```text recording=models
Ship(id=1, name='Zed', tonnage=5, home=bergen).full_clean()  ->  raises ValidationError: {'id': ['Ship with this ID already exists.']}
  SQL SELECT %s AS "a" FROM "fleet_port" WHERE "fleet_port"."id" = %s LIMIT 1 with params (1, 1)
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 1 with params (1, 1)
  SQL SELECT %s AS "_check" WHERE COALESCE((%s > %s), %s) = %s with params (1, 5, 0, True, True)
  SQL SELECT %s AS "a" FROM "fleet_ship" WHERE ("fleet_ship"."home_id" = %s AND "fleet_ship"."name" = %s) LIMIT 1 with params (1, 1, 'Zed')
```

Its second statement is the check on the key, the one a saved instance is spared, and it found the row. Its last, the unique constraint's, has no clause leaving out the row with that key. Both are so because the instance is being added (`django/db/models/base.py:Model._perform_unique_checks`, `django/db/models/constraints.py:UniqueConstraint.validate`).

> **A trap.** Validation and saving do not agree about that instance. `Model.save` called on it, for a model like Ship whose key has no default, tries an update first, finds the row and overwrites it ([Saving an instance](saving.md)). The comment on the attribute ends by saying that it affects validation only and has no effect on the save, which is no longer the whole truth: `Model._save_table` reads it to decide when to insert without trying an update.
