---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A field: the base class

A field of a model is an object of a class built on `django.db.models.fields.Field`. It describes one column, or for a few field classes none, and holds no values. The base class gives every field its place on the model class (`Field.contribute_to_class`), its column type (`Field.db_type`), the steps a value takes into a row (`Field.pre_save`, `Field.get_db_prep_save`, `Field.get_prep_value`) and out of one (`Field.get_db_converters`), and `Field.to_python`, defaults and choices.

A field is asked for many things, by parties that know nothing of each other. The schema editor wants a column type, and a migration the arguments the field was made with. A save wants the value to write, in a form the database's driver takes, and a query wants the same for the value in a condition. Validation wants a value cleaned, a form a form field, a serializer the value as text. `Field` answers each with a method or two, and a field class changes the answers it has to ([The field classes](field-types.md)).

Two facts shape the class. A field is made before its model exists: the body of a class statement runs first, and `tonnage = models.PositiveIntegerField()` is an ordinary call, which returns an object that knows neither its name nor its class. So a field comes into being in two steps, its `__init__` and then its `contribute_to_class`. And one field object serves every instance of its model, so it keeps no value: a method that deals with a value is handed the value, or the instance to read it from.

## What a field's `__init__` keeps

`Field.__init__` stores its arguments and takes a number (`django/db/models/fields/__init__.py:Field.__init__`). The base class's version checks nothing: an argument that cannot be right is found afterwards by the system checks, which look at the field once it has a model ([The model checks](checks.md)).

Most arguments become attributes of the same name: `Field.primary_key`, `Field.null`, `Field.blank`, `Field.default`, `Field.db_column`, `Field.editable` and the rest. Some are stored as they were passed, whatever is made of them later, and `Field.deconstruct` gives those back; the comments beside three of them, `verbose_name`, `validators` and `error_messages`, say that is what they are stored for. `verbose_name` is stored twice: as `Field.verbose_name`, which is filled in from the field's name when none was given, and as `Field._verbose_name`, which is left alone. `unique`, `validators`, `error_messages` and `db_tablespace` are stored once each, as `Field._unique`, `Field._validators`, `Field._error_messages` and `Field._db_tablespace`, and the public attributes of those names are worked out from them when read.

`rel=`, which a relation field's own `__init__` passes, is stored as `Field.remote_field`, and `Field.is_relation` records whether there is one ([Relations: a field, its rel and the class at the other end](relations.md)). And `choices` is assigned through a property, which puts whatever it is given into one form.

## Two counters, and the order of a model's fields

`Field.creation_counter` and `Field.auto_creation_counter` are two numbers kept on the class `Field`, and every field made in a process takes its own from one of them (`django/db/models/fields/__init__.py:Field.__init__`). A field made in the ordinary way takes the class's `creation_counter` as it stands, and steps the class's up by one. A field made with `auto_created=True`, which is how Django makes the key and the link to a parent that it adds to a model itself, takes `auto_creation_counter`, which starts at −1, and steps it down. The numbers therefore run across all the models of a process, in the order their fields were made, and such a field has a negative one.

The number is what fields are ordered by. `Field.__lt__` compares counters, and `functools.total_ordering` builds the other comparisons from it and `Field.__eq__`. The comment on `__lt__` says what the method is for: `bisect` does not take a comparison function, and `Options.add_field` uses `bisect.insort` to keep `Options.local_fields` in order as the fields arrive (`django/db/models/fields/__init__.py:Field.__lt__`, `django/db/models/options.py:Options.add_field`). So a model's own fields stand in the order they were made, those with a negative number first, whatever order they were added to the class in. `BaseDatabaseSchemaEditor.table_sql` goes through that list to write the table, which makes it the order of the columns as well (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.table_sql`).

```text recording=models
[(f.name, f.creation_counter) for f in Ship._meta.local_fields]  ->  [('id', -2), ('name', 28), ('tonnage', 30), ('home', 31), ('captain', 32)]
Named._meta.get_field('name').creation_counter == Port._meta.get_field('name').creation_counter == Ship._meta.get_field('name').creation_counter  ->  True
Port._meta.get_field('name') is Ship._meta.get_field('name'), Port._meta.get_field('name') == Ship._meta.get_field('name')  ->  (False, False)
...
hash(Port._meta.get_field('name')) == hash(Ship._meta.get_field('name'))  ->  True
```

The field `"name"` stands ahead of the three that the body of Ship wrote, though it was added to Ship after them: it was made earlier, in the body of Named, and Ship's copy of it kept the number. The key that Django added stands first.

The copies are why equality needs more than the counter. `Field.__eq__` holds two fields equal when the counter and the model are both the same, and `__lt__`, where the counters are equal, goes by the model's app label and name, which gives the copies a fixed order among themselves. `Field.__hash__` is the hash of the counter alone, so the copies hash alike. A field's model is not assigned until the field joins a class, and its counter never changes.

## Joining a class: `contribute_to_class`

`Field.contribute_to_class` is the method the metaclass calls, with the new class and the attribute's name, for each field it finds among the body's attributes (`django/db/models/fields/__init__.py:Field.contribute_to_class`) ([`ModelBase`: a class statement becomes a model](metaclass.md)). This is the first field of Ship's body joining the class:

```text recording=models
ModelBase.add_to_class(Ship, 'tonnage', a PositiveIntegerField)
  Field.contribute_to_class(Ship, 'tonnage')  (a PositiveIntegerField)
    Options.add_field(Ship.tonnage)
    DeferredAttribute.__init__(Ship.tonnage)
```

The method begins by letting the field learn its names, in `Field.set_attributes_from_name`. There are three. `Field.name` is the attribute the body assigned the field to, unless the field was made with a name of its own, which is kept. `Field.attname` is the name its value is kept under on an instance: `Field.get_attname` returns the name, and a foreign key overrides it to add `"_id"`. `Field.column` is the column, which `Field.get_attname_column` gives as the `db_column` the field was made with or else the attname. `set_attributes_from_name` also sets `Field.concrete`, true when the column is not `None`: a **concrete field** is one that has a column. A field class without one says so by overriding `get_attname_column`, as `ManyToManyField` and `CompositePrimaryKey` do.

```text recording=models
[(f.name, f.attname, f.column) for f in Ship._meta.fields]  ->  [('id', 'id', 'id'), ('name', 'name', 'name'), ('tonnage', 'tonnage', 'tonnage'), ('home', 'home_id', 'home_id'), ('captain', 'captain_id', 'captain_id')]
[(f.name, f.attname, f.column) for f in Voyage._meta.get_fields() if not f.auto_created]  ->  [('ship', 'ship_id', 'ship_id'), ('sailed', 'sailed', 'sailed'), ('calls', 'calls', None)]
```

With its names settled, the field records the class as `Field.model` and enters itself in the class's options with `Options.add_field`, which is where it takes its place in the model's lists of fields and where a field that says it is the primary key becomes one (`django/db/models/options.py:Options.add_field`) ([The options: what a model keeps as `_meta`](options.md)).

Then, if it has a column, it sets a **descriptor** on the class under its attname: an object of the class the field names as `Field.descriptor_class`, made with the field as its one argument. On the base class that is `DeferredAttribute`, which keeps the field and has a `__get__` and no `__set__` (`django/db/models/query_utils.py:DeferredAttribute`). By Python's rules an entry in an instance's own `__dict__` is found before such a descriptor, so it is not asked for a value the instance holds. It is asked when the instance has no entry under the attname, which is what it means for the field to be deferred, and it then fetches the value ([An instance and its state](instances.md)). A field class may name a descriptor of its own: `ForeignKey` and `CompositePrimaryKey` do, and the two file fields ([File fields](files.md)). A field with no column gets none from the base class, and the classes of such fields set whatever they need in their own `contribute_to_class`.

A field with choices gets one more attribute on the class: a method whose name is `"get_%s_display"` with the field's name filled in, a `functools.partialmethod` of `Model._get_FIELD_display` that carries the field (`django/db/models/base.py:Model._get_FIELD_display`). It is not set when the class's own body defines an attribute of that name. One that the class merely inherits is replaced, and the source's comment says why: to allow overriding inherited choices.

## One field, one model

A field object belongs to one model class, the one in `Field.model`, and where two classes need the same field Django makes a copy (`django/db/models/fields/__init__.py:Field.__deepcopy__`). The common case is an abstract base: for each class that inherits directly from one, the metaclass passes each field of the base that the class has not replaced to `copy.deepcopy`, and adds the copy to the new class like a field of the body (`django/db/models/base.py:ModelBase.__new__`). Ship inherits `"name"` from Named so:

```text recording=models
Field.__deepcopy__  (a copy of Named.name)
ModelBase.add_to_class(Ship, 'name', a CharField)
```

Despite its name, `__deepcopy__` copies very little, and its comment says so: most things are not intended to be altered after initial creation. It makes a shallow copy of the field, and for a relation a shallow copy of the rel, pointed at the new field. Everything else the original and its copies share, down to the list of validators. The shallow copy is `Field.__copy__`, which builds an empty object, gives it the field's class and a copy of the field's `__dict__`, and so keeps the counter. It is written by hand to keep clear of `Field.__reduce__`, which Python's own copying would go through.

A field that was entered as private, as a generic foreign key is, is copied in the same way for a subclass that has not replaced it, whether or not the base is abstract. A parent that has a table of its own is the other case, and there none of the parent's fields with columns, nor its many-to-many fields, is copied. The child's options list the parent's own field objects, each still saying that its model is the parent ([Inheritance: abstract bases, parents with tables and proxies](inheritance.md)):

```text recording=models
Officer._meta.get_field('name') is Sailor._meta.get_field('name'), Officer._meta.get_field('name').model  ->  (True, <class 'harbour.crew.models.Sailor'>)
```

`Field.deconstruct` describes a field as the call that would make it again: its name, the dotted path of its class, a list of positional arguments, which the base class leaves empty, and a dictionary of keyword arguments holding only those that differ from the defaults (`django/db/models/fields/__init__.py:Field.deconstruct`). Migrations are written from it. The autodetector compares two versions of a model field by field through their deconstructions, and the writer puts a field into a migration file as that call (`django/db/migrations/autodetector.py:MigrationAutodetector.deep_deconstruct`, `django/db/migrations/serializer.py:ModelFieldSerializer`). A field class that takes arguments of its own overrides the method to add them, and one that forces an argument takes it out again ([Migrations](../migrations.md)).

The path is shortened on purpose. A class whose module is under `django.db.models.fields` is written as if it lived in `django.db.models`: the classes of the package's own module by dropping the package's last name, and those of its modules `"related"`, `"files"`, `"generated"`, `"json"`, `"proxy"` and `"composite"` by dropping the module's name too. The docstring asks for the most portable version of the path. A migration therefore names `django.db.models.ForeignKey`, and goes on loading whichever of those modules the class is in.

```text recording=models
Ship._meta.get_field('tonnage').deconstruct()  ->  ('tonnage', 'django.db.models.PositiveIntegerField', [], {})
Ship._meta.get_field('name').deconstruct()  ->  ('name', 'django.db.models.CharField', [], {'max_length': 60})
```

`Field.clone` calls the field's class with what `deconstruct` returned. The result is a new field of the same definition and nothing else: a new counter, no name, no model. It is what `ModelState.from_model` uses to take a model's fields without taking the model (`django/db/migrations/state.py:ModelState.from_model`).

Pickling goes the other way and avoids making a second object at all. `Field.__reduce__`, for a field that has a model, reduces it to three strings, the app label, the model's name and the field's, and unpickling asks the app registry for that model and its options for that field. The docstring gives the intent: pickling should return the field the model's options hold, not a new copy of it. A field with no model, such as one made to say what type an expression has, is pickled as its `__dict__`.

```text recording=models
pickle.loads(pickle.dumps(Ship._meta.get_field('tonnage'))) is Ship._meta.get_field('tonnage')  ->  True
Ship._meta.get_field('tonnage').__reduce__()[0].__name__, Ship._meta.get_field('tonnage').__reduce__()[1]  ->  ('_load_field', ('fleet', 'Ship', 'tonnage'))
```

## The column: `db_type`

`Field.db_type` returns the column type a field wants on one database, and the field does not know it: the types are the backend's (`django/db/models/fields/__init__.py:Field.db_type`). The method asks the field for its **internal type**, a string, and looks that up in the connection's `BaseDatabaseWrapper.data_types`, a dictionary each backend fills in. The entry is a format string, filled from the field's own attributes so that `"varchar(%(max_length)s)"` gets its length, or a function called with them. An internal type the dictionary lacks gives `None`, and to the schema editor a field whose type is `None` is not a column (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.column_sql`).

`Field.get_internal_type`, in the base class, returns the name of the field's class. `CharField`, like other field classes, declares the method again, to return the string `"CharField"` whatever the class of the object, and the difference matters to a class built on it: a project's subclass of `CharField` answers `"CharField"` without doing anything, and gets the column its parent gets. The comment in `db_type` sets out the two ways a field class has of choosing its column: return, from `get_internal_type`, the name of the built-in class it most resembles, or override `db_type` and write the type out.

A check for the column is found in the same way, by the internal type in a dictionary of the backend's (`Field.db_check`, from `BaseDatabaseWrapper.data_type_check_constraints`), and the schema editor asks for the two together, through `Field.db_parameters`. So are words that follow the type (`Field.db_type_suffix`, from `BaseDatabaseWrapper.data_types_suffix`) and the type to name in a `Cast` where that differs (`Field.cast_db_type`, from `BaseDatabaseOperations.cast_data_types`). The format strings are filled from `Field.db_type_parameters`, the field's `__dict__` ([Column types: from a field to a column](../backends/column-types.md)).

`Field.rel_db_type` answers a different question, the type for a column of another table that points at this field. In the base class that is the field's own type, and an automatic key answers with the type of the plain integer class of its size (`django/db/models/fields/__init__.py:BigAutoField.rel_db_type`).

```text recording=models
Ship._meta.get_field('tonnage').get_internal_type(), Ship._meta.get_field('tonnage').db_type(connection)  ->  ('PositiveIntegerField', 'integer unsigned')
Ship._meta.get_field('tonnage').db_parameters(connection)  ->  {'type': 'integer unsigned', 'check': '"tonnage" >= 0'}
Ship._meta.pk.db_type(connection), Ship._meta.pk.rel_db_type(connection), Ship._meta.get_field('home').db_type(connection)  ->  ('integer', 'bigint', 'bigint')
```

On SQLite the key of Ship, a `BigAutoField`, has the type `"integer"` and answers `"bigint"` for a column that points at it. Ship's foreign key `"home"` points at the key of Port, another `BigAutoField`, and has `"bigint"`: it got its type by asking that key.

## The path of a value

A value takes one path into the database and another out, and the two are not mirror images. On the way in the field does the work, in four methods of `Field` that `Model._save_table` and the compilers call. On the way out the work is done by **converters**, functions gathered once for a query from the backend and from the field, and `Field.to_python` is not among them (`django/db/models/fields/__init__.py:Field`).

```text figure=the-path-of-a-value
The value of one field, into a row and out of one: each step, what does it, and who calls it.
Recorded for Sailor.signed_on, a DateTimeField, on SQLite; the condition is on Sailor.name.

INTO A ROW (an insert)
    the instance's attribute
        Field.pre_save                 called by Model._save_table, and again by SQLInsertCompiler.pre_save_val
    a Python value                     an aware datetime
        Field.get_db_prep_save         called by SQLInsertCompiler.prepare_value   (in an update, by SQLUpdateCompiler.as_sql)
          Field.get_db_prep_value      called by get_db_prep_save
            Field.get_prep_value       called by get_db_prep_value: the field's own type, no backend
            the backend's adapt_datetimefield_value, called by DateTimeField's get_db_prep_value
    a parameter of the statement       '2026-04-10 09:00:00'

INTO A CONDITION (a filter)
    the value given to filter()
        Field.get_prep_value                          called by Lookup.get_prep_lookup, when the lookup is made
        Field.get_db_prep_value, with prepared=True   called by FieldGetDbPrepValueMixin.get_db_prep_lookup, when the statement is compiled
    a parameter of the statement

OUT OF A ROW (a select)
    the column's value as the driver gives it         a naive datetime
        the backend's converters                      here DatabaseOperations.convert_datetimefield_value
        the field's converters                        from_db_value, where the field has one: here none
          both lists are gathered by SQLCompiler.get_converters, once for the query,
          and SQLCompiler.apply_converters calls them on each row
    a Python value                                    an aware datetime
        Model.from_db makes the instance from the row's values
    the instance's attribute

NOT ON THE WAY OUT
    Field.to_python      called by Field.clean, by the get_prep_value of many field classes, and by the deserializers
```

*The path of one value, in and out. The field's methods carry it in. Converters carry it out, the backend's and then the field's, and `to_python` is not on the way out of a row.*

### Into a row

`Field.pre_save`, `Field.get_db_prep_save`, `Field.get_db_prep_value` and `Field.get_prep_value` differ in what each is allowed to see.

| method | it is handed | it answers with | in the base class |
|---|---|---|---|
| `Field.pre_save` | the instance, and whether the row is being inserted | the value to write | the instance's attribute, as it stands |
| `Field.get_db_prep_save` | a value and a connection | the value as a parameter of an insert or an update | an expression is returned as it is, and any other value goes to `get_db_prep_value` |
| `Field.get_db_prep_value` | a value, a connection, and whether the value is already prepared | the value in the form this backend's driver takes | calls `get_prep_value`, unless told the value is prepared |
| `Field.get_prep_value` | a value | the value as the Python type the field stands for | a lazy object (a `Promise`) is evaluated, and anything else is returned as it is |

*The four methods of `Field` on the way into a row, outermost first. Only the first sees the instance, and only the middle two see the connection.*

`Field.pre_save` is the one step that is given the instance, and so the one step that can change what the instance holds. A field class overrides it to supply a value at the moment of saving, as a date made with `auto_now=True` does, and a file field, which writes its file ([The field classes](field-types.md), [File fields](files.md)).

Its callers are `Model._save_table` and the compiler of an insert, `SQLInsertCompiler.pre_save_val` (`django/db/models/base.py:Model._save_table`, `django/db/models/sql/compiler.py:SQLInsertCompiler.pre_save_val`). [Saving an instance](saving.md) says why an insert has both.

| what is done | calls of `pre_save` for a field |
|---|---|
| a save whose update finds its row | one, with `add=False`, for each field it sets |
| a save that goes straight to an insert | two, with `add=True`, for each field it writes: one from each caller |
| a save whose update finds no row, and which then inserts | one with `add=False` and then two with `add=True`, for each field the update would have set |
| a raw save, `Model.save_base` called with `raw=True` | none: the attribute is read |
| `QuerySet.bulk_create` | one, with `add=True`, for each field inserted, from the compiler |
| `QuerySet.update` | none |

*How many times a field's `pre_save` is called, and with what argument.*

In the base class the other three methods are nested, each calling the next. Here a Ship has been made with a string, `"300"`, for its tonnage, which is an integer field, and is saved. These are the calls for that one value, down to the one that converts it, and the statement:

```text recording=models
SQLInsertCompiler.prepare_value(Ship.tonnage, '300')
  Field.get_db_prep_save('300')  (Ship.tonnage)
    IntegerField.get_db_prep_value('300')  (Ship.tonnage)
      Field.get_db_prep_value('300')  (Ship.tonnage)
        IntegerField.get_prep_value('300')  (Ship.tonnage)
          Field.get_prep_value('300')  (Ship.tonnage)  ->  '300'
          -> 300
...
SQL INSERT INTO "fleet_ship" ("name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s) RETURNING "fleet_ship"."id" with params ('Wren', 300, 2, None)
```

`SQLInsertCompiler.prepare_value` calls the field's `get_db_prep_save`, here the base class's (`django/db/models/sql/compiler.py:SQLInsertCompiler.prepare_value`). `IntegerField` overrides the two methods under it, and each override begins by calling the method it overrides. `Field.get_prep_value` has nothing to do with a string, and it is `IntegerField`'s that makes an integer of it, which is what reaches the statement.

`get_db_prep_value` is also where a field class brings the backend in, by handing the prepared value to the connection's operations object. For the `"signed_on"` of a Sailor, a `DateTimeField`, that last step turns an aware datetime into the string SQLite stores. The calls of `get_prep_value` between these two lines are left out:

```text recording=models
DateTimeField.get_db_prep_value(datetime(2026, 4, 10, 9, 0, tzinfo=UTC))  (Sailor.signed_on)
  DatabaseOperations.adapt_datetimefield_value(datetime(2026, 4, 10, 9, 0, tzinfo=UTC))  ->  '2026-04-10 09:00:00'
```

An update takes the same road from the second step on: `SQLUpdateCompiler.as_sql` calls `get_db_prep_save` for each field it sets (`django/db/models/sql/compiler.py:SQLUpdateCompiler.as_sql`). This is the same Sailor, fetched and saved again, with the lines for its other fields and everything nested left out:

```text recording=models
Model.save()  (a Sailor)
  Field.pre_save(add=False)  (Sailor.name)  ->  'Edda'
...
  SQLUpdateCompiler.as_sql
    Field.get_db_prep_save('Edda')  (Sailor.name)
...
  SQL UPDATE "crew_sailor" SET "name" = %s, "ship_id" = %s, "signed_on" = %s WHERE "crew_sailor"."id" = %s with params ('Edda', 1, '2026-04-10 09:00:00', 5)
```

What is written need not be a value. Both compilers resolve an expression before anything else, and `get_db_prep_save` returns as it is anything that has an `as_sql` method, to be compiled into the statement where a parameter would have stood.

> **Changed in 6.1.** A compiler writes `%s` into a statement where a parameter goes, and a field class that needs other SQL in that place, its own placeholder, supplies it in a method named `get_placeholder_sql`, which returns the SQL and its parameters together. The older `"get_placeholder"` is deprecated: `Field.__init_subclass__` wraps one it finds on a new field class, and warns (`django/db/models/fields/__init__.py:Field.__init_subclass__`).

### Into a condition

A value given to a filter is prepared by the two inner methods of `Field`, `get_prep_value` and `get_db_prep_value`, at two different moments (`django/db/models/fields/__init__.py:Field.get_db_prep_value`). This is the start of a query for a Sailor by name:

```text recording=models
CharField.get_prep_value('Edda')  (Sailor.name)
  Field.get_prep_value('Edda')  (Sailor.name)  ->  'Edda'
  CharField.to_python('Edda')  (Sailor.name)  ->  'Edda'
  -> 'Edda'
Field.get_db_prep_value('Edda', prepared=True)  (Sailor.name)  ->  'Edda'
```

The first call, with the two under it, was made while the queryset was being built. `Lookup.__init__` calls `Lookup.get_prep_lookup`, which hands the value to the `get_prep_value` of the field on the lookup's left (`django/db/models/lookups.py:Lookup.get_prep_lookup`). `get_prep_value` takes no connection, and at that moment there need not be one: nothing has yet said which database the queryset will be run against. It follows that a value the field cannot take is refused when `filter` is called, and no statement is sent:

```text recording=models
Ship.objects.filter(tonnage='many')  ->  raises ValueError: Field 'tonnage' expected a number but got 'many'.
```

The last call was made as the statement was compiled for a connection. `FieldGetDbPrepValueMixin.get_db_prep_lookup` calls the field's `get_db_prep_value` with `prepared=True`, which is what that argument is for: the first step has been taken and is not to be taken again (`django/db/models/lookups.py:FieldGetDbPrepValueMixin.get_db_prep_lookup`). The mixin is on the lookups that compare a column with a value of its own type, `Exact` and the four orderings among them. A lookup may decline both steps. The pattern lookups, `Contains` and its relatives, set `Lookup.prepare_rhs` false and deal with their value themselves ([From QuerySet to SQL](../sql.md)).

### Out of a row

A row that comes back from a query is not handed to the fields. Before any row is converted, `SQLCompiler.get_converters` goes through the expressions the query selected and asks two parties about each. It asks the backend's operations object, with `get_db_converters`, and it asks the expression, which for a column of a model answers with `Field.get_db_converters` of the column's field (`django/db/models/sql/compiler.py:SQLCompiler.get_converters`, `django/db/models/expressions.py:Col.get_db_converters`). Each answer is a list of functions, and a column for which both lists are empty is left out altogether. `SQLCompiler.apply_converters` then calls the functions kept on each row in turn, the backend's before the field's, each with the value, the expression and the connection. This is what followed the statement of the query for the Sailor, which selected four columns:

```text recording=models
DatabaseOperations.get_db_converters(the column of Sailor.id)  ->  []
DatabaseOperations.get_db_converters(the column of Sailor.name)  ->  []
DatabaseOperations.get_db_converters(the column of Sailor.ship, whose values are those of Ship.id)  ->  []
DatabaseOperations.get_db_converters(the column of Sailor.signed_on)  ->  [convert_datetimefield_value]
DatabaseOperations.convert_datetimefield_value(datetime(2026, 4, 10, 9, 0))  ->  datetime(2026, 4, 10, 9, 0, tzinfo=UTC)
```

SQLite's operations object had a converter for one of the four (`django/db/backends/sqlite3/operations.py:DatabaseOperations.get_db_converters`). The expression for a foreign key's column carries the field the key points at, which is why the third line names the key of Ship (`django/db/models/fields/related.py:ForeignKey.get_col`). The value of `"signed_on"` reached it as a naive datetime, and `DatabaseOperations.convert_datetimefield_value` gave it its time zone back. The other three values went as the driver produced them to `Model.from_db`, which makes the instance from the row's values. The columns an insert or an update hands back are converted in the same way.

`Field.get_db_converters`, in the base class, returns a list holding the field's `from_db_value` when the field has a method of that name, and an empty list when it has not (`django/db/models/fields/__init__.py:Field.get_db_converters`). The base class declares no such method: the test is `hasattr`. Of the field classes in `django/db/models/fields/`, `JSONField` is the one that does (`django/db/models/fields/json.py:JSONField.from_db_value`):

```text recording=models
Sailor._meta.get_field('signed_on').get_db_converters(connection), hasattr(models.DateTimeField, 'from_db_value')  ->  ([], False)
models.JSONField().get_db_converters(connection)[0].__qualname__, hasattr(models.JSONField, 'from_db_value')  ->  ('JSONField.from_db_value', True)
```

A field class can also take part by overriding `get_db_converters`, as `DurationField` and `ForeignKey` do, each to add a function for backends that need it. The rest of the conversion on the way out is the backend's own, chosen by the field's internal type ([Values in and out: adapters, converters and time zones](../backends/values.md)).

### `Field.to_python`

`Field.to_python` converts a value to the Python type the field stands for, and raises `ValidationError` for one it cannot convert. In the base class it returns the value as it is (`django/db/models/fields/__init__.py:Field.to_python`). Nothing on the way out of a row calls it. It is called where a value arrives from somewhere other than the database. `Field.clean` calls it when an instance is validated. The `get_prep_value` of many field classes calls it, on the way in. The deserializers call it for a value read from text (`django/core/serializers/python.py`), and a form's choice field is given it as the function to coerce a submitted choice with (`django/db/models/fields/__init__.py:Field.formfield`). `django.contrib` has callers of the same kind, such as the code that reads a user's key back out of a session.

Two things follow. An instance holds what it was given: under the base class's descriptor, assigning to an attribute converts nothing, since a `DeferredAttribute` has no `__set__`. The Ship that was made with a string for its tonnage still holds the string after its save, and the row holds the number:

```text recording=models
wren.tonnage, Ship.objects.get(name='Wren').tonnage  ->  ('300', 300)
```

The attribute becomes an integer when the instance is validated, since `Model.clean_fields` stores what `clean` returns, or when the row is loaded again (`django/db/models/base.py:Model.clean_fields`). And a field class that needs to turn what a column holds into an object of its own supplies a converter, as `from_db_value` or through `get_db_converters`, or, as the file fields do, a descriptor that wraps the value when the attribute is read. Overriding `to_python` alone changes nothing about a row that is read.

### A value as text

`Field.value_from_object` returns the instance's attribute under the attname, and `Field.value_to_string` returns that value as a string, which in the base class is `str` of it (`django/db/models/fields/__init__.py:Field.value_to_string`). The serializers are what call the second: a value that is not of a plain type is written out as the string its field makes of it, and read back in through the field's `to_python`, so the two methods are a pair: what the one writes, the other has to be able to read ([Caching, files, mail, signals and tasks](../services.md)). `value_from_object` is also what `model_to_dict` reads an instance with to make a form's initial data (`django/forms/models.py:model_to_dict`).

```text recording=models
Sailor._meta.get_field('signed_on').to_python('2026-04-10 09:00:00+00:00')  ->  datetime.datetime(2026, 4, 10, 9, 0, tzinfo=datetime.timezone.utc)
Sailor._meta.get_field('signed_on').value_to_string(edda), Sailor._meta.get_field('ship').value_to_string(edda)  ->  ('2026-04-10T09:00:00+00:00', '1')
```

## Defaults

`Field.get_default` returns the value a new instance gets for a field it was given nothing for, and `Model.__init__` is what asks (`django/db/models/fields/__init__.py:Field.get_default`) ([An instance and its state](instances.md)). It calls a function that the field chooses once and keeps, as `Field._get_default`. Where the field was made with a default that is callable, the function is that callable, so it is called afresh for each instance. Where the default is a plain value, the function returns that same object each time. `Field.has_default` is true in both cases: it tests the default against the marker `NOT_PROVIDED`, so a default of `None` is a default.

With no default of any kind, the field falls back on one of two values. A field class whose `Field.empty_strings_allowed` is false, as it is for the classes of numbers, dates and booleans among others, gets `None`, and so does a nullable field on a backend that tells an empty string from a null. Any other gets the empty string:

```text recording=models
Ship._meta.get_field('tonnage').get_default(), Ship._meta.get_field('name').get_default(), Ship._meta.get_field('captain').get_default()  ->  (None, '', None)
```

A default may also be the database's. A field made with `db_default=`, and with no default of the ordinary kind, gets from `_get_default` a function that returns one `DatabaseDefault`, made once, which a new instance holds under the field's attname in the value's place (`django/db/models/expressions.py:DatabaseDefault`). [The field classes](field-types.md) follows such a field through its table and a save.

`Field.get_pk_value_on_save` is called by `_save_table` for an instance whose primary key is not set, to give the key's field a chance to make one before the choice between an update and an insert. It returns what `get_default` gives. The exception is a field whose `default` is itself a false value, such as 0: the method tests the default for truth before it calls anything, and returns `None`. An automatic key has no default and answers `None`, which leaves the key for the database to assign (`django/db/models/fields/__init__.py:Field.get_pk_value_on_save`).

## Cleaning a value: `clean`

`Field.clean` is the field's part in validating an instance, and a save does not call it: `Model.clean_fields` does, for the fields of an instance, and stores what each call returns ([Validating an instance](validation.md)). It is three calls in a row (`django/db/models/fields/__init__.py:Field.clean`). `to_python` converts the value. `Field.validate` holds it to the field's own arguments: for a field that is editable, it refuses a value that is not empty and is not among the choices, where there are choices, `None` where the field is not nullable, and an empty value where the field is not allowed to be blank. `Field.run_validators` passes over an empty value and otherwise calls each of `Field.validators`, gathering the errors, and puts the field's own message in place of a validator's where `Field.error_messages` has one for the error's code.

## Choices

The `choices` of a field are a list of permitted values, each with a label for people, and the field stores them in one form whatever form they were given in (`django/db/models/fields/__init__.py:Field.choices`). The attribute is a property, and assigning to it passes the value through `normalize_choices`. A mapping becomes a list of pairs. An enumeration class built on Django's `Choices` becomes the list it gives as its own `choices`. A callable is not called: it is wrapped in a `CallableChoiceIterator`, which calls it each time the choices are gone through. A group, a label with choices of its own under it, is put into the same form one level down (`django/utils/choices.py:normalize_choices`).

The crew's officers have a rank, declared with an enumeration:

```python
# harbour/crew/models.py
class Rank(models.TextChoices):
    MASTER = "master"
    MATE = "mate", "First mate"
    ENGINEER = "engineer"


# SailorQuerySet and Sailor are declared here


class Officer(Sailor):
    rank = models.CharField(max_length=10, choices=Rank)
```

```text recording=models
Officer._meta.get_field('rank').choices  ->  [('master', 'Master'), ('mate', 'First mate'), ('engineer', 'Engineer')]
...
Officer(rank='mate').get_rank_display(), Officer(rank='bosun').get_rank_display()  ->  ('First mate', 'bosun')
...
list(Officer._meta.get_field('rank').get_choices())  ->  [('', '- Select an option -'), ('master', 'Master'), ('mate', 'First mate'), ('engineer', 'Engineer')]
```

What the field kept is a plain list of pairs, with no trace of the class Rank. `deconstruct` gives a migration that list, so a migration does not import the enumeration.

Choices are not known to the database. They are listed in `Field.non_db_attrs`, the attributes that do not affect a column's definition, and a save writes whatever value the instance holds. `Field.validate` refuses a value outside them. `Field.formfield` makes a choice field of them. And the display method that `contribute_to_class` added looks the value up in `Field.flatchoices`, the same choices with the groups flattened away, and returns the label, or the value itself when it is not among them, as `"bosun"` is.

`Field.get_choices`, in the last line, returns the choices with a blank one in front, for a form's list to start with, and leaves the blank one out when asked to, or when the choices already hold a value that is empty or `None` (`django/db/models/fields/__init__.py:Field.get_choices`, `django/utils/choices.py:BlankChoiceIterator`). Called on a field with no choices it serves a relation: it runs a query on the related model's default manager and returns, for each object, the value a foreign key to it would hold and the object's `str`.

> **Changed in 6.1.** The blank choice's label, `BLANK_CHOICE_LABEL`, used to be a row of dashes, and `settings.USE_BLANK_CHOICE_DASH` brings the dashes back for the time being.

### The enumeration types

`Choices` is an `enum.Enum` with a metaclass of its own, `ChoicesType`, and its two subclasses add a concrete type: `IntegerChoices` is also an `enum.IntEnum`, and `TextChoices` an `enum.StrEnum` (`django/db/models/enums.py:ChoicesType`). A member of either is therefore a real integer or string, equal to its value, and can be assigned to a field and written to a row as it is.

```text recording=models
type(Rank), [c.__name__ for c in Rank.__mro__]  ->  (<class 'django.db.models.enums.ChoicesType'>, ['Rank', 'TextChoices', 'Choices', 'StrEnum', 'str', 'ReprEnum', 'Enum', 'object'])
...
Rank.MATE, Rank.MATE.value, Rank.MATE.label, Rank.ENGINEER.label  ->  (Rank.MATE, 'mate', 'First mate', 'Engineer')
Rank.MATE == 'mate', str(Rank.MATE), 'mate' in Rank, Rank('mate') is Rank.MATE  ->  (True, 'mate', True, True)
```

The metaclass adds the labels. As the class is made, `ChoicesType.__new__` goes through the members the body declared. Where a member's value is a list or a tuple of more than one element and the last is a string, that last element is taken off as the label and the rest is the value, as for the member MATE. Otherwise the label is made from the member's name, with underscores turned into spaces and each word given a capital, so that ENGINEER becomes "Engineer". The label is kept on the member and read as `Choices.label`. The finished class is passed through `enum.unique`, so two members with one value are an error.

What a field takes from the class is `ChoicesType.choices`, a property of the metaclass that pairs each member's value with its label; `ChoicesType.values`, `ChoicesType.labels` and `ChoicesType.names` list the values, the labels and the members' names alone. A class that defines `"__empty__"` gets a first entry in each: in `choices` a pair whose value is `None` and whose label is that attribute, and in `names` the string `"__empty__"`.

## A form field, and lookups

`Field.formfield` returns the form field for a model field, and a `ModelForm` gets its fields by calling it, unless it was given a callback to call in its place. The field classes override it to name their own form class (`django/db/models/fields/__init__.py:Field.formfield`) ([Forms](../forms.md)).

`Field` inherits from `RegisterLookupMixin`, which makes a field class the place where lookups and transforms are registered. A lookup registered on a class with `RegisterLookupMixin.register_lookup` is found on that class and on every class built on it, which is how the lookups registered on `Field` itself, `"exact"` among them, come to work on every field (`django/db/models/query_utils.py:RegisterLookupMixin`) ([From QuerySet to SQL](../sql.md)).
