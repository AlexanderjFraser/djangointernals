---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Altering a column, and SQLite's table remake

`BaseDatabaseSchemaEditor.alter_field` is handed a field's old definition and its new one and takes the column from the first to the second, with the indexes, constraints and foreign keys that depend on it and the columns of other tables that must follow it. `BaseDatabaseSchemaEditor._alter_field` does that in a fixed order; SQLite, which can rename a column in place but change it in no other way, builds the table again in `_remake_table`.

A column carries more than its type: its null, perhaps a default, a collation and a comment, an index or a unique constraint, a check, a foreign key into another table, and perhaps the foreign keys of other tables that point at it, whose columns must be of its type. From two field objects the editor has to work out the statements that take the column, rows and all, to its new definition, with whatever depended on it in place again at the end (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.alter_field`). Its callers outside the editor are the migration operations: `AlterField` and `RenameField` hand it the model of the state before the operation, the field as it was and the field as it is to be, and `RenameModel` each field that points at the renamed model (`django/db/migrations/operations/fields.py:AlterField.database_forwards`, `django/db/migrations/operations/models.py:RenameModel.database_forwards`) ([Migrations](../migrations.md)).

## `alter_field`: what counts as a change, and what is refused

`BaseDatabaseSchemaEditor._field_should_be_altered` is asked first, and where it answers no, `BaseDatabaseSchemaEditor.alter_field` returns having sent nothing (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._field_should_be_altered`). It compares the two fields as `Field.deconstruct` describes them, the path of the class and the arguments, without the field's name, after taking out of the keyword arguments what each field lists in its `non_db_attrs`. `Field.non_db_attrs` holds `"verbose_name"`, `"help_text"`, `"choices"`, `"validators"`, `"db_column"` and others that, the comment says, do not affect a column's definition (`django/db/models/fields/__init__.py:Field.non_db_attrs`); `ForeignObject.non_db_attrs` adds `"on_delete"`, except for the database-level options that 6.1 introduced, `DB_CASCADE` and its siblings, which the comment says are part of the column definition (`django/db/models/fields/related.py:ForeignObject.non_db_attrs`). A different column name is a change at once, and so is a new name for a many-to-many field, whose table between is named after the field unless it is given a name of its own (`django/db/models/fields/related.py:ManyToManyField._get_m2m_db_table`).

Where the fields differ, `alter_field` reads each one's column type from `Field.db_parameters`, `None` for a field without a column, and the two types decide its refusals and its two ways out (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.alter_field`). A field that has no type and is not a relation, on either side, is refused with `ValueError`. Two many-to-many fields whose tables between Django made go to `BaseDatabaseSchemaEditor._alter_many_to_many`; two with through models of the project's own are left alone; and a type on one side only, a field made a many-to-many or unmade, or given a through model or relieved of one, is refused with `ValueError`. So is a change to a generated column: a field made a `GeneratedField` or unmade, a new expression, a change of `GeneratedField.db_persist`, or a new type where the features lack `BaseDatabaseFeatures.supports_alter_generated_column_data_type`, as Oracle's do; the message says to remove the field and add it again. Everything else goes to `BaseDatabaseSchemaEditor._alter_field` with both types and both fields' parameters.

## `_alter_field`, in order

`BaseDatabaseSchemaEditor._alter_field` drops what the change could break, renames the column, changes it, and makes again what it dropped together with what the new field needs that the old did not have, each step only where the two fields call for it (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_field`). What it drops it must first find: `BaseDatabaseSchemaEditor._constraint_names` asks the database, through introspection, for those of the kind wanted, on exactly the columns it is given where it is given any (the old column, for the field's own); for a unique constraint, an index or a check, `_alter_field` has the names the model declares in its options left out ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md), [Introspection: reading the schema back](introspection.md)).

```text figure=alter-field-order
BaseDatabaseSchemaEditor._alter_field: each step only where the two fields call for it

dropped first
   1  the column's own foreign key                                  made again at 15
   2  its unique constraint: it stops being unique, or becomes the primary key
   3  the foreign keys of other tables that point at it:
      it stays a key, and its type or collation changes             made again at 16
   4  its index: db_index goes, or a unique constraint takes its place
   5  its check: the check its type carries changes                 the new one at 17
renamed
   6  the column, and the column in every deferred statement
changed   a statement each; 7 and 8 in one where supports_combined_alters
   7  type, collation (and comment, on MySQL); the database default
   8  the default set on the column      (null to not null, no database default)
   9  the null rows set to the default, then NOT NULL        (with a default)
      or NOT NULL / NULL with the changes of steps 7 and 8   (otherwise)
  10  statements for after: a changed comment; what the type change asked for
the old primary key dropped; then made again, and new
  11  the primary key dropped: it stops being the primary key
  12  a unique constraint, an index: the new field needs one
  13  the primary key: it becomes the primary key
  14  the columns of other tables that point at it: altered to the new type
  15  the column's own foreign key
  16  the foreign keys of other tables
  17  the check
  18  the default of step 8 dropped again
```

*The order of `_alter_field`. Steps 8, 9 and 18, step 9 taking two, are the four steps of a column made not null with a default in Python; with a database default, step 9 uses it, and it stays.*

### What is dropped first

The column's own foreign key goes first, where the features have `BaseDatabaseFeatures.supports_foreign_keys`, the old field has `ForeignKey.db_constraint`, and more than the comment changes (`BaseDatabaseSchemaEditor._field_should_be_altered` is asked again with `"db_comment"` ignored). Then its unique constraint, where the field stops being unique or becomes the primary key, leaving alone one that the model's constraints name. Then the foreign keys of other tables that point at it, where the features have `supports_foreign_keys`, the old and new fields are both the primary key or both unique, and the type or the collation changes: each relation that `_related_non_m2m_objects` finds loses its constraint (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_field`).

Then its index, where the old field had `Field.db_index` and not `Field.unique`, which a primary key has too (`django/db/models/fields/__init__.py:Field.unique`), and the new one has no index or is unique. Only B-tree indexes, whose introspected type is `Index.suffix`, are looked for, the kind `db_index=True` makes, and the model's declared indexes and constraints are passed over by name, the comment saying the name is the only way to tell an index of `db_index=True` from an `Index` declared over the same field (`django/db/models/indexes.py:Index`). Then its check, where the check its type carries changes. `BaseDatabaseSchemaEditor._field_db_check` writes that check from `BaseDatabaseWrapper.data_type_check_constraints`, a `PositiveIntegerField`'s test that the value is not negative, with a stand-in for the column's name, the comment saying this keeps a renamed column from having its check made again (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._field_db_check`). On MySQL, though not on MariaDB, the editor writes it with the column's own name, the comment saying a renamed column there needs its check made again (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor._field_db_check`).

### The rename

Where the column's name changes, `BaseDatabaseSchemaEditor._rename_field_sql` fills in `BaseDatabaseSchemaEditor.sql_rename_column`, `"ALTER TABLE"` with `"RENAME COLUMN"`, and the statement is sent at once; then `Statement.rename_column_references` renames the column in each statement held for the editor's exit, so that an index deferred on the old column is made on the new (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_field`, `django/db/backends/ddl_references.py:Statement.rename_column_references`).

### The column changed

The base class gathers the changes before it sends any: fragments of SQL with their parameters, each to follow `"ALTER TABLE"` and the table's name in `BaseDatabaseSchemaEditor.sql_alter_column`, the change of null kept apart, and whole statements for afterwards. A new type, suffix (an auto-increment) or collation is `BaseDatabaseSchemaEditor._alter_column_type_sql`'s `"ALTER COLUMN"` and `"TYPE"`, with any statements to run once the column is altered (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_column_type_sql`). A changed comment is such a statement, `BaseDatabaseSchemaEditor._alter_column_comment_sql`'s `"COMMENT ON COLUMN"`, the comment saying PostgreSQL and Oracle cannot run it with an `"ALTER COLUMN"`; MySQL, whose features lack `BaseDatabaseFeatures.supports_independent_comment_alteration`, writes it into the `"MODIFY"` that changes the type instead, and sends one for a changed comment alone (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor._alter_column_comment_sql`). A database default is set by `BaseDatabaseSchemaEditor._alter_column_database_default_sql` where it is new or different and dropped where it goes (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_column_database_default_sql`). A change of null is `BaseDatabaseSchemaEditor._alter_column_null_sql`'s `"SET NOT NULL"` or `"DROP NOT NULL"`, or nothing where the features have `BaseDatabaseFeatures.interprets_empty_strings_as_nulls` and the field allows the empty string, the comment saying the column is nullable in the database anyway (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_column_null_sql`).

A column that allowed null and is to be `"NOT NULL"` may hold rows with null in them. A comment gives the four steps the editor takes where the new field has a default: add a default for new incoming writes, update the existing null rows with it, replace the null constraint with not null, and drop the default again. Where the new field has no `Field.db_default`, `BaseDatabaseSchemaEditor._alter_column_default_sql` sets on the column the new field's default as `BaseDatabaseSchemaEditor.effective_default` gives it, provided that is not `None`, differs from the old field's, and the backend's `BaseDatabaseSchemaEditor.skip_default_on_alter` does not decline it, as it does on MySQL for a text or blob column (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_column_default_sql`, `django/db/backends/mysql/schema.py:DatabaseSchemaEditor.skip_default_on_alter`) ([MySQL and MariaDB](mysql.md)). Where the new field has a default, a Python one or a database one, the changes are sent with the change of null held back; then `BaseDatabaseSchemaEditor.sql_update_with_default`, an `"UPDATE"` that sets the column to the default where it is null; then the change of null, which otherwise goes with the others (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_field`). The default set on the column is dropped at the end of `_alter_field`, with the comment that Django usually does not use defaults in the database; a database default serves the update and stays. A migration that gives a default for this change only, with `preserve_default=False`, gives it to the new field for the length of the call (`django/db/migrations/operations/fields.py:AlterField.database_forwards`). Where the features have `BaseDatabaseFeatures.supports_combined_alters`, which of the four backends is PostgreSQL alone, the changes sent first are joined by commas into one `"ALTER TABLE"`, and a held-back change of null is sent alone; elsewhere each change is a statement.

### What is made again, and what is new

A field that stops being the primary key loses the constraint, which `BaseDatabaseSchemaEditor._delete_primary_key` finds through introspection (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._delete_primary_key`). A unique constraint is added where `BaseDatabaseSchemaEditor._unique_should_be_added` says: the new field is unique and not the primary key, and the old was not unique or was the primary key, whose constraint has just gone (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._unique_should_be_added`). An index is added in the mirror case, where the new field has an index and is not unique and the old had none or was unique. A field that `BaseDatabaseSchemaEditor._field_became_primary_key` says has become the primary key gets `BaseDatabaseSchemaEditor._create_primary_key_sql`'s `"ADD CONSTRAINT"` and `"PRIMARY KEY"` (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._create_primary_key_sql`).

Then the columns of other tables. Where the foreign keys pointing at the column were dropped, or the field has just become the primary key, each relation that `_related_non_m2m_objects` finds has its column altered by `_alter_column_type_sql` to the type its field now writes: on PostgreSQL an `AutoField` key made a `BigAutoField` goes from `"integer"` to `"bigint"`, and every column that points at it goes too. The foreign keys come back, written by `BaseDatabaseSchemaEditor._create_fk_sql`: the column's own, where it was dropped or the old field had none, and the other tables' that were dropped, each where its field has `db_constraint` (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_field`). Then the new check is added, and the default of the four steps dropped.

### The relations that follow: `_related_non_m2m_objects`

The relations that follow an altered column are found by `_related_non_m2m_objects` with two helpers beside it. `_all_related_fields` lists the relations that point at a model, hidden ones included and its parents' left out, sorted by name, the comment asking for a deterministic order (`django/db/backends/base/schema.py:_all_related_fields`). `_is_relevant_relation` keeps one whose foreign key targets the altered field, by naming it in `ForeignObject.to_fields` or, where the field is the primary key, by naming no field; the reverse of a many-to-many is never kept. Its docstring says what it decides: whether constraints on the model from that relation must be dropped while the field is altered (`django/db/backends/base/schema.py:_is_relevant_relation`).

`_related_non_m2m_objects` takes the relevant relations of the old field's model and of the new field's model, in a migration the model before and the model after, and pairs them by position. It yields each pair and then, calling itself on the pair's two fields, the pairs that point at those, and so on down (`django/db/backends/base/schema.py:_related_non_m2m_objects`). The descent carries a change through a key that is itself a foreign key, as in multi-table inheritance. In the harbour the relations kept for Sailor's key are the ships' `"captain_id"`, the `"sailor_id"` of Licence, the table between a sailor and the ports the sailor may pilot ships into, and the `"sailor_ptr_id"` of Officer, a child of Sailor with a table of its own, which is that table's key and its foreign key to Sailor's; a change to the type of Sailor's key would reach those three columns and, through the last, any column that pointed at an Officer.

## Many-to-many: `_alter_many_to_many`

A many-to-many field has no column; it has the table between, with a foreign key to each side. `BaseDatabaseSchemaEditor._alter_many_to_many` renames that table where its name changes and alters its two foreign keys with `BaseDatabaseSchemaEditor.alter_field` on the intermediate model: the one that points at the target model, then the one that points at the model itself, which a comment says a model related to itself needs (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_many_to_many`).

## SQLite: the table made again

### Why SQLite remakes the table

SQLite's `"ALTER TABLE"` renames a table, renames a column, adds a column and drops one, and that is all: nothing changes a column's type, null, default or constraints, or adds or drops a constraint on a table that exists ([SQLite's documentation](https://www.sqlite.org/lang_altertable.html)). For any other change that page gives a procedure, and `DatabaseSchemaEditor._remake_table` follows it, its docstring citing the page and listing the steps: create a table with the new definition, named `"new__"` and the old table's name, copy the rows into it, drop the old table, rename the new one to the old name, and restore the old table's indexes (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor._remake_table`). A foreign key, too, exists on SQLite only in its column's definition (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor`) ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)).

SQLite's `DatabaseFeatures.can_rollback_ddl` is true, so the editor, unless made with `atomic=False`, works inside an atomic block, and a remake that fails at any statement, a copied row that breaks the new definition among them, is undone with all the editor did (`django/db/backends/sqlite3/features.py:DatabaseFeatures`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.__init__`).

Between the `"DROP TABLE"` and the rename, a foreign key of another table that points at this one points at a table that is not there; SQLite's editor turns the checking of foreign keys off as it is entered and checks every key before it commits (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__enter__`, `django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__exit__`) ([SQLite](sqlite.md)).

### SQLite's `_alter_field`

SQLite's editor keeps `BaseDatabaseSchemaEditor.alter_field`, with its comparison and its refusals, and replaces `DatabaseSchemaEditor._alter_field`, without calling the base class's (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor._alter_field`). It has two roads. Where the column's name changes, and `BaseDatabaseSchemaEditor.column_sql` writes the same definition for both fields, and neither is a foreign key with a constraint, it sends `BaseDatabaseSchemaEditor._rename_field_sql`'s `"RENAME COLUMN"`, which SQLite does in place. Every other change remakes the table.

Buoy's name lengthened from 40 characters to 80 takes the second road. Buoy is a model of the recording's own, shown whole in [The schema editor: `BaseDatabaseSchemaEditor`](schema.md), to which were added, in its options and on its table, a second index, `"buoy_port_name_idx"` on the port and the name, and a check constraint, `"buoy_has_name"`. In the recording, a line set in under a call is a call it made, `->` gives what a call returned, and a line beginning `SQL` is a statement as Django handed it to its cursor:

```text recording=backends
BaseDatabaseSchemaEditor.alter_field(Buoy, CharField 'name' max_length=40, CharField 'name' max_length=80)
  BaseDatabaseSchemaEditor._field_should_be_altered  ->  True
  DatabaseSchemaEditor._alter_field
    DatabaseSchemaEditor._remake_table
      SQL CREATE TABLE "new__moorings_buoy" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "port_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED, "name" varchar(80) NOT NULL, CONSTRAINT "buoy_has_name" CHECK ("name" > ''))
      SQL INSERT INTO "new__moorings_buoy" ("id", "port_id", "name") SELECT "id", "port_id", "name" FROM "moorings_buoy"
      SQL DROP TABLE "moorings_buoy"
      SQL ALTER TABLE "new__moorings_buoy" RENAME TO "moorings_buoy"
      SQL CREATE INDEX "moorings_buoy_port_id_d16249a7" ON "moorings_buoy" ("port_id")
      SQL CREATE INDEX "buoy_name_idx" ON "moorings_buoy" ("name")
      SQL CREATE INDEX "buoy_port_name_idx" ON "moorings_buoy" ("port_id", "name")
```

Renamed to title, the lengthened name takes the first road:

```text recording=backends
BaseDatabaseSchemaEditor.alter_field(Buoy, CharField 'name' max_length=80, CharField 'title' max_length=80)
  BaseDatabaseSchemaEditor._field_should_be_altered  ->  True
  DatabaseSchemaEditor._alter_field
    SQL ALTER TABLE "moorings_buoy" RENAME COLUMN "name" TO "title"
```

The remake does not ask what changed. A Python default changed and nothing else, which `BaseDatabaseSchemaEditor._field_should_be_altered` counts and for which `BaseDatabaseSchemaEditor._alter_field` sends nothing, remakes the table, copying every row, though the column it writes is the same. Here it is Pier's table; Pier, keyed by a code, and Mooring, which has a foreign key to it, are two models of the recording's own in an app labelled quays:

```text recording=backends
BaseDatabaseSchemaEditor.alter_field(Pier, CharField 'keeper' max_length=20 default='harbourmaster', CharField 'keeper' max_length=20 default='the purser')
  BaseDatabaseSchemaEditor._field_should_be_altered  ->  True
  DatabaseSchemaEditor._alter_field
    DatabaseSchemaEditor._remake_table(Pier)
```

After the remake, where the new field is unique, as a primary key is, and its type or collation changed, the tables with foreign keys to it are remade, which writes each one's foreign key column in the type it now takes from the field: those of the relations that `_related_non_m2m_objects` finds and, where the field is the primary key, the tables between of the model's many-to-many fields whose tables Django made. A relation from the very class handed to the editor to itself is passed over, the comment saying its table was already rebuilt. Pier's key lengthened from four characters to eight remakes Mooring's table too:

```text recording=backends
DatabaseSchemaEditor._remake_table(Mooring)
  SQL CREATE TABLE "new__quays_mooring" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "pier_id" varchar(8) NOT NULL REFERENCES "quays_pier" ("code") DEFERRABLE INITIALLY DEFERRED)
```

### `_remake_table`, in full

`_remake_table` is given the model and the change: a field to create, a field to delete, pairs of old and new fields to alter, or nothing, which makes the table again as the model describes it (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor._remake_table`). It works from the model, not from the table: the new table is the model's local concrete fields with the change applied, and the model's own constraints and indexes. SQLite's `DatabaseSchemaEditor.add_field`, `remove_field`, `add_constraint` and `remove_constraint` call it as well ([SQLite](sqlite.md), [Constraints and indexes](../models/constraints.md)).

It builds two dictionaries. One maps each field's name to the field, the body of the new table, into which a `CompositePrimaryKey`, having no column, is put by hand. The other maps each column to what the copy selects for it, already quoted, since it may hold a column's name or a value; it starts with every column as itself, but for generated columns, which the new table computes.

Then the change. A created field joins the body, and its column the copy with its effective default as a literal, unless it has a database default, is generated or has no column. An altered field's old entry leaves both and the new one is added; the new table's columns, after any that Django made itself such as `"id"`, are in the order their fields were made (`django/db/models/options.py:Options.add_field`), so the `"name"` lengthened under SQLite's `_alter_field`, a field made after Buoy's own, went to the end. The copy selects the old column under the new name, or, where the field goes from null to not null, `"coalesce"` of the old column and the default, the new field's database default where it has one, which does in the one copy what the four steps do elsewhere. A deleted field leaves both. Where a created or altered field is a new primary key, the old one is marked as no longer one for the length of the call, and if Django made it, as the automatic `"id"` or a child model's link to its parent, it leaves the body and the copy.

The new table needs a model to be created from. `_remake_table` makes two, in an `Apps` of their own, with the model's `unique_together` (its field names renamed), its indexes (less any that names a deleted field) and its constraints: one with the model's name and table, never made as a table, for a key from the model to itself to resolve to, so that the new table's key names the table by the name it will take; and one named `"New"` and the model's name, with the table `"new__"` and the model's.

Then the statements, in the order the remake of Buoy's table shows under SQLite's `_alter_field`. `BaseDatabaseSchemaEditor.create_model` writes the `"CREATE TABLE"` and holds back the indexes. An `"INSERT INTO"` the new table `"SELECT"` from the old copies the rows as the second dictionary says. SQLite's `DatabaseSchemaEditor.delete_model`, told to leave the tables of many-to-many fields alone, drops the old table only and forgets any held-back statement that names it (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.delete_model`). `BaseDatabaseSchemaEditor.alter_db_table` renames the new table to the old name, in the database and in every held-back statement ([The schema editor: `BaseDatabaseSchemaEditor`](schema.md)). Every held-back statement is then sent and the list emptied, the comment saying they now run on the correct table; that includes any the editor was holding from earlier in the same block.

### SQLite's `_alter_many_to_many`

SQLite's editor replaces `DatabaseSchemaEditor._alter_many_to_many` as well (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor._alter_many_to_many`). Where the table between keeps its name, it is remade with both its foreign keys altered. Where the name changes, the new table between is created, filled from the old with its `"id"` and its two columns in one `"INSERT"`, and the old table dropped.

## The other backends

The three other backends keep `BaseDatabaseSchemaEditor._alter_field` and change pieces of it. PostgreSQL's editor appends `"USING"` and a cast to the new type where the kind of type changes, as from `"varchar"` to `"text"`, or, for some fields, a relation among them, where the type changes at all, though never for a generated column (`django/db/backends/postgresql/schema.py:DatabaseSchemaEditor._using_sql`); it also adds or drops an identity where a field becomes an auto field or stops being one, and keeps the `"_like"` index of an indexed text column in step (`django/db/backends/postgresql/schema.py:DatabaseSchemaEditor._alter_column_type_sql`, `django/db/backends/postgresql/schema.py:DatabaseSchemaEditor._alter_field`) ([PostgreSQL](postgresql.md)).

MySQL's editor changes a column with `"MODIFY"`, to which `DatabaseSchemaEditor._set_field_new_type` adds the old field's null and database default, its docstring saying they are kept and, where they change, handled separately (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor._set_field_new_type`) ([MySQL and MariaDB](mysql.md)).

Oracle's `DatabaseSchemaEditor.alter_field` calls the base method and reads the error the database raises: for `"ORA-22858"` or `"ORA-22859"`, which the comment reads as a change to an unsupported type, it takes what the comment calls a SQLite-ish way round, a column added under a temporary name, the values copied into it, the old column dropped and the new one altered into its place (`django/db/backends/oracle/schema.py:DatabaseSchemaEditor.alter_field`, `django/db/backends/oracle/schema.py:DatabaseSchemaEditor._alter_field_type_workaround`) ([Oracle](oracle.md)).
