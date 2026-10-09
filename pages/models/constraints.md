---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Constraints and indexes

`CheckConstraint`, `UniqueConstraint` and `Index` are the objects a model's `Meta` lists under `"constraints"` and `"indexes"`. Each describes one rule or one index of the model's table, can give that description to a migration, and hands a schema editor its SQL; a constraint can also test an instance. A unique field, a foreign key and a positive integer put rules and indexes in the same table with no such object.

A table carries rules that the database enforces on every row, whatever program wrote the row, and indexes that let it find rows without reading them all. A model states these in two ways. Some belong to a single field, as an argument of the field or simply by its class: this field is unique, that one refers to another table. The rest involve several columns, or a condition, or an expression, and, but for the option `unique_together`, are objects of their own in the model's `Meta`.

Those objects are descriptions. Each holds the arguments it was made with. None holds a model, a table or a connection: every method that needs one is handed it. And none of the SQL methods sends a statement: each returns a clause or a statement to a schema editor, and the editor decides what is sent. The one method that sends anything itself is a constraint's `validate`.

A **schema editor** is the database backend's object that turns a model, a field, a constraint or an index into statements that change the schema, and sends them. Its statements are sent as its `with` block runs, and those it has put off are sent when the block is left without an error (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor`) ([The schema editor: `BaseDatabaseSchemaEditor`](../backends/schema.md)).

The example is the ship of a shipping line, with one constraint of each kind and one index:

```python
# harbour/fleet/models.py
class Named(models.Model):
    name = models.CharField(max_length=60)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


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

## What each can be asked

A constraint and an index answer the same few questions, each put by a different part of Django.

| what is asked for | who asks | a constraint's method | an index's method |
|---|---|---|---|
| its clause inside `"CREATE TABLE"` | `BaseDatabaseSchemaEditor.table_sql` | `constraint_sql`, which may return nothing | none: an index is not part of that statement |
| the statement that adds it to a table | `BaseDatabaseSchemaEditor.add_constraint`, `BaseDatabaseSchemaEditor.add_index`, and `BaseDatabaseSchemaEditor.create_model` for the indexes of `Meta` and, where the table's statement has parameters, the constraints | `create_sql` | `create_sql` |
| the statement that drops it | `BaseDatabaseSchemaEditor.remove_constraint` and `BaseDatabaseSchemaEditor.remove_index` | `remove_sql` | `remove_sql` |
| whether one instance obeys it | `Model.validate_constraints` | `validate` | none |
| what is wrong with its own declaration | the checks of its model | `check` | `check` |
| the arguments it was made with | migrations | `deconstruct` | `deconstruct` |
| a second object like it | the model's options as they fill in its name, and a migration's picture of the model | `clone` | `clone` |

*What a constraint and an index are asked, and by whom. The first three are answered with SQL for one model and one schema editor, both passed in.*

`validate` is how a constraint takes part in `Model.full_clean`: a `CheckConstraint` has the database evaluate its condition against the instance's values, and a `UniqueConstraint` looks for another row with the same ones ([Validating an instance](validation.md)). `check` is called by the system checks, once for each database being checked that the model is migrated on, and reports such things as a field that does not exist or a feature the database lacks ([The model checks](checks.md)).

## From `Meta` to the class

The lists a `Meta` gives as `"constraints"` and `"indexes"` reach the class through its options. `Options.contribute_to_class` copies each attribute of `Meta` that it knows onto the options object, these two among them, taking one that the `Meta` only inherits as readily as one it declares (`django/db/models/options.py:Options.contribute_to_class`) ([The options: what a model keeps as `_meta`](options.md)). For an abstract class the two lists are left as they came. For any other class both are then passed through `Options._format_names`.

That method fills in two placeholders a name may contain, `"%(app_label)s"` and `"%(class)s"`, with the app's label and the model's name, both in lower case. It does not write the new name into the object it was given. It clones each object, formats the clone's name, and returns a new list (`django/db/models/options.py:Options._format_names`):

```text recording=models
Ship._meta.original_attrs['constraints'][0].name, Ship._meta.constraints[0].name  ->  ('%(class)s_has_tonnage', 'ship_has_tonnage')
Ship._meta.original_attrs['constraints'][0] is Ship._meta.constraints[0]  ->  False
```

`Options.original_attrs` holds what the `Meta` said, and the object there still has its placeholder. A `Meta` is an ordinary class, and a class that inherits it, or inherits an abstract base that has one, is handed the very same list of the very same objects. And among the system checks is one that reports a constraint's name, or an index's, used by two models (`django/core/checks/model_checks.py:check_all_models`). The placeholders let one declaration on an abstract base give each inheriting class a name of its own, and the clone leaves the declaration unchanged for the next class.

An index is copied a second time, and this copy is made for every class, an abstract one included, which `_format_names` passed over. Near its end `ModelBase.__new__` replaces the options' list of indexes with a deep copy of each, under a comment that says this is so that index names are unique when models extend an abstract model. And the name of an index that has none is not set until `ModelBase._prepare`, the last thing done to a class before it is registered. The comment there gives the reason for the delay: it cannot be done in `Options.contribute_to_class` because the fields have not been added to the model at that point (`django/db/models/base.py:ModelBase.__new__`, `django/db/models/base.py:ModelBase._prepare`). In the class statement of Ship, with the rest of what `_prepare` did left out:

```text recording=models
ModelBase._prepare(Ship)
...
  Index.set_name_with_model(Ship)  ->  the index is named 'fleet_ship_home_id_f9b8f2_idx'
```

## The table of Ship, read line by line

A schema editor's `create_model` is handed a model class and makes its table. This is what SQLite's sent for Ship: the first statement at once, and the other two, which were put off, as the editor was left. The tables of the other models, made in between, are left out:

```text recording=models
editor.create_model(Ship)
  SQL CREATE TABLE "fleet_ship" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(60) NOT NULL, "tonnage" integer unsigned NOT NULL CHECK ("tonnage" >= 0), "home_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED, "captain_id" bigint NULL UNIQUE REFERENCES "crew_sailor" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "ship_has_tonnage" CHECK ("tonnage" > 0), CONSTRAINT "one_name_to_a_port" UNIQUE ("name", "home_id"))
...
the editor is left
...
SQL CREATE INDEX "fleet_ship_home_id_12c4d51a" ON "fleet_ship" ("home_id")
SQL CREATE INDEX "fleet_ship_home_id_f9b8f2_idx" ON "fleet_ship" ("home_id", "tonnage")
```

| in the statements | what declared it | where the editor gets it |
|---|---|---|
| `"NOT NULL"` on four columns, `"NULL"` on `"captain_id"` | each field's `null`, which is false unless the field is given `null=True` | the column's own definition |
| `"PRIMARY KEY"` on `"id"` | the key that was added to the class, a field with `primary_key=True` | the column's own definition |
| the `"CHECK"` after `"tonnage"`, that it is not below zero | nothing but the field's class, `PositiveIntegerField` | the field's `db_check`, from a table the backend keeps by the kind of field |
| `"REFERENCES"` on `"home_id"` and `"captain_id"` | the two relation fields, each with `db_constraint` true | the editor's template for a foreign key written in the column |
| `"UNIQUE"` on `"captain_id"` | `OneToOneField`, which sets `unique=True` on itself | the column's own definition |
| the constraint `"ship_has_tonnage"` | the `CheckConstraint` of `Meta` | `CheckConstraint.constraint_sql` |
| the constraint `"one_name_to_a_port"` | the `UniqueConstraint` of `Meta` | `UniqueConstraint.constraint_sql` |
| the index `"fleet_ship_home_id_12c4d51a"` | the `ForeignKey` named `"home"`, which sets `db_index=True` on itself unless told otherwise | `BaseDatabaseSchemaEditor._field_indexes_sql` |
| the index `"fleet_ship_home_id_f9b8f2_idx"` | the `Index` of `Meta` | `Index.create_sql` |

*Every rule and index in the recorded table of Ship, with what in the model declared it.*

`BaseDatabaseSchemaEditor.table_sql` writes the first statement (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.table_sql`). It goes through the model's own fields and writes a column for each, and what a field brings with it is written into its column. The first `"CHECK"` is not a constraint object's at all: `Field.db_check` looks the field's class up in the backend's `data_type_check_constraints`, where SQLite's backend has an entry for each positive integer field, and the editor adds what it finds to the column (`django/db/models/fields/__init__.py:Field.db_check`, `django/db/backends/sqlite3/base.py:DatabaseWrapper.data_type_check_constraints`).

After the columns come the constraints of `Meta`, in the order of the list: `table_sql` asks each for its `constraint_sql` and leaves out any that returned nothing. But if the statement so far has parameters, as it does where a column has a default that the backend takes as a parameter, each constraint is asked for its `create_sql` instead and that statement is put off. The comment explains: a constraint's SQL has its values written into the text, and is unfit to be mixed with SQL whose values are to be passed separately.

The indexes are never in the first statement. `create_model` collects them afterwards from `_model_indexes_sql`, first an index for each field that should have one and then each `Index` of `Meta`, and adds them to `BaseDatabaseSchemaEditor.deferred_sql`, the list the editor runs when it is left (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.create_model`).

Which fields should have an index is a short rule in the base editor, a field whose `db_index` is true and which is not unique, and the editors of MySQL and Oracle narrow it (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._field_should_be_indexed`). So `"home_id"`, a foreign key's column, has an index of its own, and `"captain_id"`, a one-to-one field's and therefore unique, has none: a unique column is indexed by the database already (`django/db/models/fields/related.py:ForeignKey.__init__`, `django/db/models/fields/related.py:OneToOneField.__init__`). A field's index is named by the editor, from the table, the column and eight digits of a digest, a different scheme from an `Index` object's.

## `BaseConstraint`: a name, a message and a code

`BaseConstraint` settles what every constraint has: a name, and the message and the code of the error raised when an instance breaks it (`django/db/models/constraints.py:BaseConstraint`). Its arguments are keywords only. The name is required. The message, when none is given, is the class's `BaseConstraint.default_violation_error_message`, a sentence with a place for the name, which `BaseConstraint.get_violation_error_message` fills in. The code, `BaseConstraint.violation_error_code`, is `None` unless one is given.

What a constraint does with a table or an instance is left to the subclass: on `BaseConstraint` the methods `constraint_sql`, `create_sql`, `remove_sql` and `validate` each raise `NotImplementedError`.

## `CheckConstraint`: a condition

`CheckConstraint` adds one argument, a condition, which must be a `Q` object or an expression whose value is true or false; anything else is refused with `TypeError` when the constraint is made (`django/db/models/constraints.py:CheckConstraint`).

Its SQL is made the way the `"WHERE"` of a query is made, by the same code ([From QuerySet to SQL](../sql.md)). `CheckConstraint._get_check_sql` builds a `Query` for the model, has it turn the condition into the node a filter would become, and compiles that node with the schema editor's connection. Two things differ from a query. The `Query` is made with `alias_cols=False`, so a column is written by its name alone and not after its table's. And each parameter is turned into a literal by the editor's `quote_value` and written into the text.

`CheckConstraint.constraint_sql` and `CheckConstraint.create_sql` put that text into the schema editor's templates, and `CheckConstraint.remove_sql` needs only the name (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._check_sql`). Each line here is a method of Ship's check constraint, called with the model and a schema editor of the SQLite backend, and what it returned:

```text recording=models
ddl(Ship, Ship._meta.constraints[0], 'constraint_sql')  ->  CONSTRAINT "ship_has_tonnage" CHECK ("tonnage" > 0)
ddl(Ship, Ship._meta.constraints[0], 'create_sql')  ->  ALTER TABLE "fleet_ship" ADD CONSTRAINT "ship_has_tonnage" CHECK ("tonnage" > 0)
ddl(Ship, Ship._meta.constraints[0], 'remove_sql')  ->  ALTER TABLE "fleet_ship" DROP CONSTRAINT "ship_has_tonnage"
```

`create_sql` and `remove_sql` return nothing on a backend whose features say it has no check constraints on tables (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._create_check_sql`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._delete_check_sql`).

> **Changed in 6.0.** The condition was once given as `check=`. That keyword has been removed, and on a constraint the name `check` now means only the method the system checks call.

## `UniqueConstraint`: fields or expressions, and what goes round them

A `UniqueConstraint` says that no two rows may agree on something (`django/db/models/constraints.py:UniqueConstraint`). The something is either a tuple of field names, given as `fields=`, or one or more expressions, given positionally, among which a string is taken for an `F` of that name. It is kept as `UniqueConstraint.fields` or as `UniqueConstraint.expressions`.

Five more arguments qualify the rule:

- `condition=`, a `Q`: the rule holds only among the rows that meet it.
- `deferrable=`, which is `Deferrable.DEFERRED` or `Deferrable.IMMEDIATE`: the constraint is declared `"DEFERRABLE INITIALLY DEFERRED"`, which is not enforced until the end of the transaction, or `"DEFERRABLE INITIALLY IMMEDIATE"`, which is enforced after every statement.
- `include=`, names of fields whose columns are stored in the index beside the key without being part of the rule.
- `opclasses=`, the name of an operator class for each field, which only PostgreSQL's schema editor writes into the statement ([Content types, static files and the other contrib apps](../contrib.md) has the rest of what is PostgreSQL's alone).
- `nulls_distinct=`, whether two nulls count as different values. Left at `None`, the database's own rule stands.

### In the table's statement or after it, as a constraint or as an index

A `UniqueConstraint` reaches the database at one of two moments, as a clause inside the table's own statement or as a statement after it, and in one of two forms, a constraint or a unique index. For a table whose statement has no parameters, the schema editor settles the two questions in two methods, whose tests differ by one argument. The moment is settled by `_unique_sql`, which `UniqueConstraint.constraint_sql` calls as the table's statement is written: it returns a clause for that statement, or has a statement made, puts that on the editor's list of statements to run later, and returns nothing for the table; the comment there says that databases support conditional, covering, functional and nulls-distinct unique constraints by way of a unique index. The form is settled by `_create_unique_sql`, which makes the statement in both cases: the one just put off, and the one `UniqueConstraint.create_sql` returns (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._unique_sql`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._create_unique_sql`).

| a unique constraint that | in the table's statement | the template of its own statement |
|---|---|---|
| has fields and nothing more, or is deferrable besides | the clause `"CONSTRAINT … UNIQUE (…)"`, with the words for a deferrable constraint after it | `BaseDatabaseSchemaEditor.sql_create_unique` |
| says something about nulls, and has nothing of the next row | nothing: its statement is put off | `sql_create_unique` |
| has a condition, included columns, operator classes or expressions | nothing: its statement is put off | `BaseDatabaseSchemaEditor.sql_create_unique_index` |
| needs a feature the backend lacks | nothing | none: no statement is made |

*What the schema editor makes of a `UniqueConstraint`: `_unique_sql` gives the second column, `_create_unique_sql` the third.*

In the base editor `sql_create_unique` is `"ALTER TABLE … ADD CONSTRAINT … UNIQUE"`. So a constraint that only says something about nulls is put off like the others, and what is put off for it is that `"ALTER TABLE"` and not an index. The four arguments that select the index are the four a deferrable constraint may not have: `UniqueConstraint.__init__` refuses each of them together with `deferrable=`.

```text recording=models
ddl(Ship, Ship._meta.constraints[1], 'constraint_sql')  ->  CONSTRAINT "one_name_to_a_port" UNIQUE ("name", "home_id")
ddl(Ship, Ship._meta.constraints[1], 'create_sql')  ->  CREATE UNIQUE INDEX "one_name_to_a_port" ON "fleet_ship" ("name", "home_id")
ddl(Ship, models.UniqueConstraint(fields=['name'], condition=Q(tonnage__gt=1000), name='big_names'), 'constraint_sql')  ->  None
ddl(Ship, models.UniqueConstraint(fields=['name'], condition=Q(tonnage__gt=1000), name='big_names'), 'create_sql')  ->  CREATE UNIQUE INDEX "big_names" ON "fleet_ship" ("name") WHERE "tonnage" > 1000
ddl(Ship, models.UniqueConstraint(models.functions.Lower('name'), name='names_whatever_the_case'), 'create_sql')  ->  CREATE UNIQUE INDEX "names_whatever_the_case" ON "fleet_ship" ((LOWER("name")))
Ship._meta.total_unique_constraints  ->  [<UniqueConstraint: fields=('name', 'home') name='one_name_to_a_port'>]
```

The first two lines are Ship's own constraint. The statement for adding it afterwards is a `"CREATE UNIQUE INDEX"` here, where the base template would have given an `"ALTER TABLE"`, because SQLite's schema editor replaces `sql_create_unique` with one of its own (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor`). The third and fourth lines are a constraint with a condition: nothing for the table's statement, and a unique index with a `"WHERE"` clause to follow it. The fifth is a constraint over an expression.

### The total unique constraints

`Options.total_unique_constraints`, the last line of that recording, is a list other code relies on. It holds the model's unique constraints that have neither a condition nor expressions: the ones that promise, as its docstring puts it, a set of fields guaranteed to be unique for all rows (`django/db/models/options.py:Options.total_unique_constraints`). A constraint with a condition makes its promise for some rows only, and one over expressions makes it about no set of fields. `QuerySet.in_bulk` accepts a field as its key when one of these constraints is over that field alone, and `QuerySet.totally_ordered` takes an ordering that includes every field of one, none of them nullable, to be an ordering in which no two rows tie (`django/db/models/query.py:QuerySet.in_bulk`, `django/db/models/query.py:QuerySet.totally_ordered`).

## `Index`

An `Index` is built like a constraint and is not one: it shares no base class with them, has no `validate`, and no clause in a table's own statement (`django/db/models/indexes.py:Index`).

It is over fields or over expressions, never both. A field name with a minus sign before it is indexed in descending order, and `Index.fields_orders` holds each name with its order. Around them an index takes a condition, which makes it an index of some rows only, `include=` and `opclasses=` with the meanings they have for a unique constraint, and `db_tablespace=`.

An index is the one object here that may go without a name, and only in the plain case. `Index.__init__` refuses an index with expressions, a condition, included fields or operator classes unless it is named, and one whose fields are not all strings.

`Index.create_sql` hands its arguments to the editor's `_create_index_sql`, and `Index.remove_sql` returns a `"DROP INDEX"` (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._create_index_sql`). The descending order is passed on only to a backend whose features say it supports ordered index columns (`django/db/models/indexes.py:Index.create_sql`). An expression, in an index or in a unique constraint, is first wrapped in an `IndexExpression`, which puts it in parentheses unless it resolves to a plain column (`django/db/models/indexes.py:IndexExpression`).

```text recording=models
ddl(Ship, Ship._meta.indexes[0], 'create_sql')  ->  CREATE INDEX "fleet_ship_home_id_f9b8f2_idx" ON "fleet_ship" ("home_id", "tonnage")
models.Index(fields=['name', '-tonnage']).fields_orders, models.Index(fields=['name', '-tonnage']).name  ->  ([('name', ''), ('tonnage', 'DESC')], '')
ddl(Ship, models.Index(fields=['name', '-tonnage'], name='by_name_and_size'), 'create_sql')  ->  CREATE INDEX "by_name_and_size" ON "fleet_ship" ("name", "tonnage" DESC)
ddl(Ship, models.Index(models.functions.Lower('name'), name='lower_names'), 'create_sql')  ->  CREATE INDEX "lower_names" ON "fleet_ship" ((LOWER("name")))
```

### The name: `Index.set_name_with_model`

An index that was given no name holds the empty string in its place, as the second line shows, until `Index.set_name_with_model` makes one from the model it turns out to belong to (`django/db/models/indexes.py:Index.set_name_with_model`). The name has three parts joined by underscores: the first eleven characters of the table's name; the first seven of the first column's name; and six hexadecimal digits followed by `Index.suffix`, which is `"idx"`. The digits are the start of an MD5 digest of the table's name, every column's name, a descending one with its minus sign, and the suffix (`django/db/backends/utils.py:names_digest`). So `"fleet_ship_home_id_f9b8f2_idx"` is the table, the column of the index's first field, the digest and the suffix.

The parts are cut so that the whole is at most thirty characters, which is `Index.max_name_length`; the comment beside that attribute says the limit is there for compatibility with Oracle. A name that would begin with an underscore or a digit has its first character replaced by a `"D"`. A name the author wrote is held to the same two rules by `Index.check`, which reports one that breaks either.

## Adding a constraint to a table that exists

What `create_sql` returns is an offer. `BaseDatabaseSchemaEditor.add_constraint` takes it: it calls `create_sql` and sends the statement, if there is one (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.add_constraint`). SQLite's editor does not. Its `add_constraint` passes a `UniqueConstraint` with a condition, expressions, included fields or a deferrable setting to the base method, which for the first two sends the `"CREATE UNIQUE INDEX"` shown earlier and for the other two, which are features SQLite's backend lacks, sends nothing. For every other constraint it makes the table again (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.add_constraint`).

A schema editor of the SQLite backend was asked to add a second check constraint to the table of Ship. For the length of the call the constraint was also put on Ship's own list, `Options.constraints`, where the model a migration hands the editor would have it (`django/db/models/options.py:Options.constraints`):

```text recording=models
editor.add_constraint(Ship, extra), where extra is a CheckConstraint named 'ship_not_too_big' that Ship._meta.constraints lists for this call
  SQL CREATE TABLE "new__fleet_ship" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(60) NOT NULL, "tonnage" integer unsigned NOT NULL CHECK ("tonnage" >= 0), "home_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED, "captain_id" bigint NULL UNIQUE REFERENCES "crew_sailor" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "ship_has_tonnage" CHECK ("tonnage" > 0), CONSTRAINT "one_name_to_a_port" UNIQUE ("name", "home_id"), CONSTRAINT "ship_not_too_big" CHECK ("tonnage" < 500000))
  SQL INSERT INTO "new__fleet_ship" ("id", "name", "tonnage", "home_id", "captain_id") SELECT "id", "name", "tonnage", "home_id", "captain_id" FROM "fleet_ship"
  SQL DROP TABLE "fleet_ship"
  SQL ALTER TABLE "new__fleet_ship" RENAME TO "fleet_ship"
  SQL CREATE INDEX "fleet_ship_home_id_12c4d51a" ON "fleet_ship" ("home_id")
  SQL CREATE INDEX "fleet_ship_home_id_f9b8f2_idx" ON "fleet_ship" ("home_id", "tonnage")
```

No `"ALTER TABLE … ADD CONSTRAINT"` was sent, though that is what the constraint's `create_sql` returns on this backend. The table was made again under another name, with the new constraint after the two the old one had, filled from the old table and renamed, and the indexes were made again (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor._remake_table`).

The third constraint is in the new table because it was on the model's list, not because it was handed to `add_constraint`. Where it remakes the table, SQLite's method has looked at the constraint it was handed only to see what kind it is, and `_remake_table` works from the model: its fields, its `unique_together`, its indexes and its constraints. That is why the constraint had to be on the list for this call. In a migration the model handed to the editor comes from the state after the operation, to which the constraint has already been added (`django/db/migrations/operations/models.py:AddConstraint.database_forwards`) ([Migrations](../migrations.md)).

## `unique_together`

The option `unique_together` of a model's `Meta` is the older way to say what a `UniqueConstraint` over fields says: a sequence of field names, or a sequence of such sequences, with no name and no other argument. `Options.contribute_to_class` normalises it to a tuple of tuples and keeps it as `Options.unique_together` (`django/db/models/options.py:normalize_together`). It makes no object. The schema editor reads the option itself: `table_sql` makes a statement for each entry with `_create_unique_sql`, under a name the editor makes up from the table and the columns, and always puts it off. Validation reads the option too, as a unique check of several fields ([Validating an instance](validation.md)).

Django uses it for a model it writes itself. A many-to-many field that names no through model has one made for it, and `create_many_to_many_intermediary_model` gives that model a `Meta` whose `unique_together` is its two foreign keys (`django/db/models/fields/related.py:create_many_to_many_intermediary_model`) ([Many-to-many relations](many-to-many.md)). The harbour's Voyage has such a field, `"calls"`. Asked of that field, which the recording has under its own name:

```text recording=models
calls.remote_field.through._meta.unique_together  ->  (('voyage', 'port'),)
```

And in the recorded tables, with the table of Voyage left out and the unique index among the statements put off:

```text recording=models
editor.create_model(Voyage)
  SQL CREATE TABLE "fleet_voyage_calls" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "voyage_id" bigint NOT NULL REFERENCES "fleet_voyage" ("id") DEFERRABLE INITIALLY DEFERRED, "port_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED)
...
SQL CREATE UNIQUE INDEX "fleet_voyage_calls_voyage_id_port_id_8c446735_uniq" ON "fleet_voyage_calls" ("voyage_id", "port_id")
```

> **Changed in 5.1.** The option `"index_together"`, the same spelling for an index over several fields, was removed. An `Index` in `"indexes"` is the way to declare one.

## A constraint a backend cannot make

A condition, a deferrable constraint, included columns and an index over expressions are each something not every database has, and the objects do not refuse to exist on one that lacks what they need. Each feature is a flag on the backend's features object, such as `BaseDatabaseFeatures.supports_partial_indexes` for a condition or `BaseDatabaseFeatures.supports_deferrable_unique_constraints` for a deferrable constraint (`django/db/backends/base/features.py:BaseDatabaseFeatures`), and the schema editor consults them.

A unique constraint that needs a missing feature is not made at all: `_unique_supported` answers no, each of the three methods that would have produced SQL returns nothing, and the base `add_constraint` sends nothing (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._unique_supported`). SQLite's features do not include deferrable unique constraints, and its editor has no statement to offer for one:

```text recording=models
ddl(Ship, models.UniqueConstraint(fields=['name'], deferrable=models.Deferrable.DEFERRED, name='later'), 'create_sql')  ->  None
```

An index over expressions is likewise skipped, by `add_index` and when a table is made, and an index with included columns is made without them (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.add_index`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._model_indexes_sql`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._index_include_sql`). None of these methods raises anything.

The place a missing feature is reported is the system checks, which warn of one unless the model's `Meta` lists the feature in `required_db_features` ([The model checks](checks.md)). The option has a second effect: `Options.can_migrate`, for a model that names no `required_db_vendor`, answers no for a connection that lacks a listed feature, and a migration operation that is told no leaves the model's table alone on that database (`django/db/models/options.py:Options.can_migrate`, `django/db/migrations/operations/base.py:Operation.allow_migrate_model`).

## What a migration compares

To a migration a constraint or an index is a value: something to write into a file, to copy, and to compare with last time's ([Migrations](../migrations.md)). `deconstruct` returns the class's path and the arguments that would make the object again. `clone` makes the object again from them, and the picture of a model that migrations keep is made of such clones, not of the model's own objects (`django/db/migrations/state.py:ModelState.from_model`). And `__eq__` is what the autodetector's test of whether an object is in the old list or the new comes down to: `Index.__eq__` compares what two indexes of the same class deconstruct to, and the constraints compare their attributes one by one (`django/db/migrations/autodetector.py:MigrationAutodetector.create_altered_constraints`).

```text recording=models
Ship._meta.constraints[0].deconstruct()  ->  ('django.db.models.CheckConstraint', (), {'name': 'ship_has_tonnage', 'condition': <Q: (AND: ('tonnage__gt', 0))>})
...
Ship._meta.indexes[0].deconstruct()  ->  ('django.db.models.Index', (), {'name': 'fleet_ship_home_id_f9b8f2_idx', 'fields': ['home', 'tonnage']})
```

The index was written without a name and deconstructs with one, the name it was given when the class was prepared: a migration records an index by name, and the operation that adds one refuses an index without (`django/db/migrations/operations/models.py:AddIndex`). A constraint's message and code, for their part, are in what it deconstructs to and are no part of the table. `BaseConstraint.non_db_attrs` names those two arguments, and the autodetector sets them aside when it decides whether a changed constraint has to be dropped and made again or only recorded as altered (`django/db/migrations/autodetector.py:MigrationAutodetector._constraint_should_be_dropped_and_recreated`).
