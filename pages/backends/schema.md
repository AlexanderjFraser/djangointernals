---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The schema editor: `BaseDatabaseSchemaEditor`

The **schema editor** is the object through which Django changes a database's schema. `BaseDatabaseSchemaEditor` turns a model created or deleted, a field added or removed, and an index or a constraint added or dropped into statements for one database, sends them or collects them as text, and holds some of them back until it is left; each of the four backends subclasses it, and `BaseDatabaseWrapper.schema_editor` makes one.

The statements that create, alter and drop tables, columns, indexes and constraints are a database's **DDL**, and databases differ in it: whether a rollback undoes it, whether a foreign key can be added by a statement of its own, whether a default may be a parameter, whether a column can be dropped without building its table again. The base class writes the plain case, and each backend's editor replaces what its database does otherwise. The methods that make each kind of change are handed the model class of the table they change, which in a migration is rendered from the migration's state of the model (`django/db/migrations/operations/models.py:CreateModel.database_forwards`).

Migrations are the main user: each operation's `Operation.database_forwards` calls the editor's methods, inside an editor that `MigrationExecutor.apply_migration` opens for each migration (`django/db/migrations/executor.py:MigrationExecutor.apply_migration`) ([Migrations](../migrations.md)). Given `--run-syncdb`, the command migrate creates the tables of apps that have no migrations in one editor, which is how a test database gets its tables when the alias's `"TEST"` dictionary sets `"MIGRATE"` to false (`django/core/management/commands/migrate.py:Command.sync_apps`) ([Test databases: `BaseDatabaseCreation`](creation.md)); and `MigrationLoader.collect_sql`, behind the command sqlmigrate, uses editors that collect their statements instead of sending them. `BaseDatabaseWrapper.schema_editor` makes an instance of the class the backend names as `BaseDatabaseWrapper.SchemaEditorClass`, and raises `NotImplementedError` where it names none (`django/db/backends/base/base.py:BaseDatabaseWrapper.schema_editor`).

## The editor as a context manager

`BaseDatabaseSchemaEditor.__init__` keeps the connection and two options: `collect_sql=True` makes an editor that collects its statements as text, and `atomic=True`, the default, asks for its work to be one transaction. It sets `BaseDatabaseSchemaEditor.atomic_migration` true only where that option is true and the features also have `BaseDatabaseFeatures.can_rollback_ddl`, which says a rollback undoes DDL: SQLite's and PostgreSQL's have it, MySQL's and Oracle's do not (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.__init__`).

`BaseDatabaseSchemaEditor.__enter__` sets `BaseDatabaseSchemaEditor.deferred_sql`, the list of **deferred statements**, to an empty list, and where `atomic_migration` holds enters an atomic block on the editor's alias ([Transactions: autocommit, `atomic` and savepoints](transactions.md)). `BaseDatabaseSchemaEditor.__exit__` sends each deferred statement if nothing raised in the block, then leaves the atomic block with the exception it was given, so that everything the editor sent commits with the outermost atomic block, or rolls back (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.__exit__`). After an exception the deferred statements are never sent. On MySQL and Oracle there is no atomic block, so under autocommit each statement is its own transaction, and what was sent before an exception stays.

The recording's model for these blocks is a buoy, kept in an app registry of its own so that the project's is left alone:

```python
# the recording's own model; moorings is an Apps() of its own
class Buoy(models.Model):
    name = models.CharField(max_length=40)
    port = models.ForeignKey(Port, on_delete=models.CASCADE)

    class Meta:
        app_label = "moorings"
        apps = moorings
        indexes = [models.Index(fields=["name"], name="buoy_name_idx")]
```

In the recording, made on SQLite, a line at the left margin is Python as it ran; under it stand the calls it set going, nested, with `->` for what a call returned and a backend's class without its module being SQLite's; and a line `SQL` is a statement as Django handed it to its cursor. An editor made with `collect_sql=True`, entered by hand as a `with` statement would enter it:

```text recording=backends
editor = connection.schema_editor(collect_sql=True)
editor.__enter__()
  DatabaseSchemaEditor.__enter__
    DatabaseWrapper.disable_constraint_checking
      SQL PRAGMA foreign_keys = OFF
      SQL PRAGMA foreign_keys
      -> True
    BaseDatabaseSchemaEditor.__enter__
      Atomic.__enter__
        SQL BEGIN
```

SQLite's editor puts a step of its own first: it turns SQLite's checking of foreign keys off, which some of its changes to a table need, and reads the setting back, refusing to be entered where that did not take ([SQLite](sqlite.md)). The base class then enters the atomic block, which on SQLite begins the transaction with `"BEGIN"`. These statements are the connection's own, not the editor's, and reach the database even from an editor that collects.

> **Trap.** `__exit__` sends the deferred statements before it leaves the atomic block, with no `try` around them. A deferred statement that fails raises out of `__exit__` with the atomic block never left, and on SQLite with the foreign key checks still off, since `DatabaseSchemaEditor.__exit__` turns them on only after the base class's exit returns (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__exit__`).

## `execute`: a statement sent, or collected

`BaseDatabaseSchemaEditor.execute` is the one way out for a statement that changes the schema, and it begins with a refusal: when it is not collecting, the connection is inside an atomic block and the features lack `can_rollback_ddl`, it raises `TransactionManagementError`, saying that executing DDL statements while in a transaction on databases that can't perform a rollback is prohibited (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.execute`). The editor opens no such block on those backends, but `Migration.apply` does, around an operation that is to be atomic, as a `RunPython` is by default (`django/db/migrations/migration.py:Migration.apply`). The refusal stops the function a `RunPython` runs, which is handed the editor, from changing the schema inside that block on MySQL or Oracle (`django/db/migrations/operations/special.py:RunPython.database_forwards`).

Then `execute` makes a string of the statement, which may be a `Statement` whose text is not yet written ([Deferred statements as objects](#deferred-statements-as-objects)), logs it at the debug level on the logger `"django.db.backends.schema"`, and either appends it to `BaseDatabaseSchemaEditor.collected_sql`, ended with a semicolon and with its parameters written in by `quote_value`, or executes it on a cursor of the connection ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)). Given `None` for its parameters, as each deferred statement is, Django's cursor hands the statement to the driver with none at all, so no `"%"` in it is taken for a placeholder (`django/db/backends/utils.py:CursorWrapper._execute`). PostgreSQL's editor writes the parameters into the text itself (`django/db/backends/postgresql/schema.py:DatabaseSchemaEditor.execute`) ([PostgreSQL](postgresql.md)).

`BaseDatabaseSchemaEditor.quote_value` writes a value into the text as a literal. The base class raises `NotImplementedError`, its docstring saying the method is not safe against injection from user code and is meant for SQL scripts and defaults; each of the four backends' editors provides one, MySQL's by asking the driver's connection to escape the value (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor.quote_value`). `BaseDatabaseSchemaEditor.quote_name` is the operations object's ([The SQL a backend writes: `BaseDatabaseOperations`](operations.md)).

## `create_model`, in order

`BaseDatabaseSchemaEditor.create_model` sends the table's statement at once and defers its indexes. The buoy's table, the editor collecting:

```text recording=backends
editor.create_model(Buoy)
  BaseDatabaseSchemaEditor.create_model(Buoy)
    BaseDatabaseSchemaEditor.table_sql(Buoy)
      BaseDatabaseSchemaEditor.column_sql(Buoy, Buoy.id)  ->  ('integer NOT NULL PRIMARY KEY', [])
      BaseDatabaseSchemaEditor.column_sql(Buoy, Buoy.name)  ->  ('varchar(40) NOT NULL', [])
      BaseDatabaseSchemaEditor.column_sql(Buoy, Buoy.port)  ->  ('bigint NOT NULL', [])
      -> ('CREATE TABLE "moorings_buoy" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(40) NOT NULL, "port_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED)', [])
    BaseDatabaseSchemaEditor.execute(a str)
full([str(statement) for statement in editor.deferred_sql])  ->  ['CREATE INDEX "moorings_buoy_port_id_d16249a7" ON "moorings_buoy" ("port_id")', 'CREATE INDEX "buoy_name_idx" ON "moorings_buoy" ("name")']
type(editor.deferred_sql[0])  ->  django.db.backends.ddl_references.Statement
```

`BaseDatabaseSchemaEditor.table_sql` writes the statement (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.table_sql`). For each of the model's own fields it asks `BaseDatabaseSchemaEditor.column_sql` for the column's definition and adds what that leaves out: the check `Field.db_parameters` gives for the field's type, the suffix of the type from `Field.db_type_suffix`, here `"AUTOINCREMENT"`, and a relation's foreign key (`django/db/models/fields/__init__.py:Field.db_type_suffix`). On SQLite a `BigAutoField`, the key of the buoy and of the port, is `"integer"`, and a column pointing at one is `"bigint"` ([Column types: from a field to a column](column-types.md)). The foreign key goes into the column where the editor has a template for that, `BaseDatabaseSchemaEditor.sql_create_inline_fk`, which of the four backends only SQLite's sets; on the other three it is a statement of its own, made by `BaseDatabaseSchemaEditor._create_fk_sql` and deferred.

`table_sql` defers two more kinds of statement. One for each entry of the model's `unique_together` is deferred always, the comment says, as some fields might be created afterward, like geometry fields on some backends. And each constraint of `Meta` puts its `constraint_sql` into the table's statement, unless the columns have produced parameters, in which case its `create_sql`, with its values written in, is deferred and sent without parameters, so that no `"%"` among those values is taken for a placeholder ([Constraints and indexes](../models/constraints.md)).

`create_model` sends the statement, and, where the features have `supports_comments`, the table's comment and, unless they have `supports_comments_inline`, its columns'. It defers the model's indexes, from `BaseDatabaseSchemaEditor._model_indexes_sql`, an index for each field that should have one and each `Index` of `Meta`, under the comment that SQLite's table remake needs them deferred ([Altering a column, and SQLite's table remake](alter-field.md)). Last it calls itself for the table of each many-to-many field whose model Django made (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.create_model`).

A foreign key names another table, and two models may each have one to the other, as Ship and Sailor do. `Command.sync_apps` creates the tables of the apps without migrations that are not there yet, in a single editor, the comment after its loop saying the deferred SQL is executed when the editor's context is left: by then every table of the block exists (`django/core/management/commands/migrate.py:Command.sync_apps`). On SQLite the foreign key is in the table's statement; only the buoy's two indexes wait. The collecting editor that made the buoy's table, left:

```text recording=backends
editor.__exit__(None, None, None)
  DatabaseSchemaEditor.__exit__
    DatabaseWrapper.check_constraints
      SQL PRAGMA foreign_key_check
    BaseDatabaseSchemaEditor.__exit__
      BaseDatabaseSchemaEditor.execute(a Statement)
      BaseDatabaseSchemaEditor.execute(a Statement)
      Atomic.__exit__
        BaseDatabaseWrapper.commit
    DatabaseWrapper.enable_constraint_checking
      SQL PRAGMA foreign_keys = ON
full(editor.collected_sql)  ->  ['CREATE TABLE "moorings_buoy" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(40) NOT NULL, "port_id" bigint NOT NULL REFERENCES "fleet_port" ("id") DEFERRABLE INITIALLY DEFERRED);', 'CREATE INDEX "moorings_buoy_port_id_d16249a7" ON "moorings_buoy" ("port_id");', 'CREATE INDEX "buoy_name_idx" ON "moorings_buoy" ("name");']
'moorings_buoy' in connection.introspection.table_names()  ->  False
  SQL SELECT name, type FROM sqlite_master WHERE type in ('table', 'view') AND NOT name='sqlite_sequence' ORDER BY name
```

SQLite's editor wraps the base class's exit: every foreign key in the database is checked before the held statements are sent, and the checks are turned back on only after the commit. The DDL is in `collected_sql`, and the table was never made.

## A column's definition: `column_sql`

`BaseDatabaseSchemaEditor.column_sql` returns a column's definition and its parameters, or `None` for both where the field has no column, as a many-to-many field has none (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.column_sql`). It reads `Field.db_parameters`: the type under `"type"`, the check under `"check"`, which it leaves to its callers, and for a text field or a relation to one the collation under `"collation"` (`django/db/models/fields/__init__.py:Field.db_parameters`, `django/db/models/fields/__init__.py:CharField.db_parameters`, `django/db/models/fields/__init__.py:TextField.db_parameters`, `django/db/models/fields/related.py:ForeignKey.db_parameters`). `BaseDatabaseSchemaEditor._iter_column_sql` gives these clauses first, in this order (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._iter_column_sql`):

1. the type;
2. `"COLLATE"` and the collation, where there is one;
3. `"DEFAULT"`: the field's database default where it has one, and otherwise, where the caller asked, its effective default;
4. the null: for a generated field, `"GENERATED ALWAYS AS"`, its expression, and `"STORED"` (`"MATERIALIZED"` on Oracle) or `"VIRTUAL"` in its place; otherwise `"NOT NULL"` or `"NULL"`. A field that may hold an empty string and is not the primary key is written null where the features have `interprets_empty_strings_as_nulls`, the comment saying Oracle treats the empty string as null ([Oracle](oracle.md));
5. `"PRIMARY KEY"`, or `"UNIQUE"` for a unique field.

The primary key, the `"UNIQUE"` and the check are written without a name.

## Defaults: written once, then dropped

`BaseDatabaseSchemaEditor._effective_default` settles the value a column must hold in rows that already exist: the field's default where it has one; nothing for a generated field; the empty string, or empty bytes for a `BinaryField`, for a field that may not be null but may be blank and whose type allows the empty string; the moment of the call for a field given auto_now or auto_now_add; otherwise nothing (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._effective_default`). `BaseDatabaseSchemaEditor.effective_default` passes it through `Field.get_db_prep_save` (`django/db/models/fields/__init__.py:Field.get_db_prep_save`).

A new table has no rows to fill, and `BaseDatabaseSchemaEditor.table_sql` asks for no default. `BaseDatabaseSchemaEditor.add_field` asks for one and takes it away: the column is created with the effective default as its `"DEFAULT"`, which the database writes into every existing row, and the next statement drops it, unless the field has a database default, the backend's editor says it cannot be dropped, or there was none (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.add_field`).

Where the features have `requires_literal_defaults`, as SQLite's and Oracle's do, the value is written into the text by `BaseDatabaseSchemaEditor.prepare_default`, which those two editors make `quote_value`; elsewhere `BaseDatabaseSchemaEditor._column_default_sql` gives a placeholder and the value is a parameter. A database default is compiled as an expression, a `Value` into that placeholder and anything else in parentheses (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.db_default_sql`). MySQL's editor has rules of its own for the defaults of text, blob and JSON columns ([MySQL and MariaDB](mysql.md)); SQLite's builds the table again to add a column with an effective default, its comment saying SQLite's `"ALTER TABLE"` does not support `"DROP DEFAULT"` (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.add_field`).

## Adding and removing a field, and deleting a table

`BaseDatabaseSchemaEditor.add_field` creates the table of a many-to-many field whose model Django made, and otherwise one column: the definition with its default, suffix and check, and a relation's foreign key, written into the same statement by `BaseDatabaseSchemaEditor.sql_create_column_inline_fk`, which each of the four backends sets. It sends the column's `"ALTER TABLE ... ADD"`, drops the default, and defers the field's index. `BaseDatabaseSchemaEditor.remove_field` drops a relation's foreign key constraints first, finding their names in the database, the comment saying MySQL requires their explicit deletion; then it sends `"DROP COLUMN"` and takes off the list every deferred statement that refers to the column (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.remove_field`). On SQLite, once an editor that sends has made the buoy's table, colour, a character field that may be null, is added and removed:

```text recording=backends
with connection.schema_editor() as editor: editor.add_field(Buoy, colour)
  SQL PRAGMA foreign_keys = OFF
  SQL PRAGMA foreign_keys
  SQL BEGIN
  SQL ALTER TABLE "moorings_buoy" ADD COLUMN "colour" varchar(10) NULL
  SQL PRAGMA foreign_key_check
  SQL PRAGMA foreign_keys = ON
with connection.schema_editor() as editor: editor.remove_field(Buoy, colour)
  SQL PRAGMA foreign_keys = OFF
  SQL PRAGMA foreign_keys
  SQL BEGIN
  SQL ALTER TABLE "moorings_buoy" DROP COLUMN "colour"
  SQL PRAGMA foreign_key_check
  SQL PRAGMA foreign_keys = ON
```

SQLite's editor uses those statements only for such columns: it adds with them a column that may be null, is neither a primary key nor unique, and has no effective default and no database default other than a `Value`, drops one that is not a primary key, not unique, not indexed and not a foreign key, and for any other column builds the table again (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.add_field`, `django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.remove_field`). `BaseDatabaseSchemaEditor.alter_field`, which changes a column already there, is told in [Altering a column, and SQLite's table remake](alter-field.md).

`BaseDatabaseSchemaEditor.delete_model` drops the tables of the model's many-to-many fields whose models Django made, then its own with `BaseDatabaseSchemaEditor.sql_delete_table`, and takes off the list every deferred statement that refers to the table (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.delete_model`).

## Indexes and constraints

An `Index` or a constraint hands the editor its fields or expressions, its condition compiled with the values written in by `quote_value`, and its name (`django/db/models/indexes.py:Index.create_sql`). The editor keeps the templates, in `BaseDatabaseSchemaEditor._create_index_sql`, `BaseDatabaseSchemaEditor._create_unique_sql` and `BaseDatabaseSchemaEditor._create_check_sql`, asks the features whether a statement can be made at all, and decides whether a unique constraint is a clause of the table's statement or a statement of its own; [Constraints and indexes](../models/constraints.md) has the objects' side, with SQLite's editor building a table again to add a check constraint.

`BaseDatabaseSchemaEditor.add_index` sends an index's `create_sql`, unless the index is over expressions and the features lack `supports_expression_indexes`; `BaseDatabaseSchemaEditor.remove_index` does the same with `remove_sql`; `BaseDatabaseSchemaEditor.rename_index` renames in place where the features have `can_rename_index`, and otherwise removes and adds. `BaseDatabaseSchemaEditor.add_constraint` and `BaseDatabaseSchemaEditor.remove_constraint` send what the constraint returns, if anything (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.add_index`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.add_constraint`). When a table is made or a column added, a field gets an index of its own if `BaseDatabaseSchemaEditor._field_should_be_indexed` says so, for a field with `db_index` that is not unique. MySQL's and Oracle's editors narrow that ([MySQL and MariaDB](mysql.md), [Oracle](oracle.md)), but not for a field altered to `db_index`, which `BaseDatabaseSchemaEditor._alter_field` indexes by its own test; PostgreSQL's adds a second index to an indexed or unique text column, with an operator class for `"LIKE"` ([PostgreSQL](postgresql.md)).

`BaseDatabaseSchemaEditor.alter_unique_together` adds each new entry with `_create_unique_sql` and drops each old one through `BaseDatabaseSchemaEditor._delete_composed_index`, which takes the entry's statement off the deferred statements if it is still there, and otherwise asks the database for the constraint, taking, where the features have `allows_multiple_constraints_on_same_fields`, the one with the name the editor would have given it, and raising `ValueError` unless it is left with one (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._delete_composed_index`). `BaseDatabaseSchemaEditor.alter_index_together` does the same for indexes, without searching the deferred statements; the option is gone from `Meta`, but a historical migration's state of a model can still hold it.

## Deferred statements as objects

A deferred statement waits, and meanwhile the editor may rename the table it refers to or one of its columns, or drop the table, the column or the index it would make. So it is kept as a `Statement`, a template and its parts by name, and written out when it is sent as the template filled in with each part's text (`django/db/backends/ddl_references.py:Statement`).

A part is a plain string or one of the module's subclasses of `Reference`, each written out as its text: a `Table`, the table's name quoted; `Columns`, the quoted columns, each with a suffix such as `"DESC"`, and `IndexColumns`, which adds an operator class to each and which PostgreSQL's editor alone uses; an `IndexName`, the name a function makes of a table, its columns and a suffix, and a `ForeignKeyName`, made likewise with the target's table and column; and `Expressions`, compiled with their values written in. All but the `Table` are subclasses of `TableColumns`, a table and its columns, which writes out nothing of its own (`django/db/backends/ddl_references.py`).

Each part that is a `Reference` answers the questions `Reference` declares: whether it refers to a table, a column or an index (`Reference.references_table`, `Reference.references_column`, `Reference.references_index`), and the two renamings (`Reference.rename_table_references`, `Reference.rename_column_references`). A `Statement` asks each of its parts that has the method, and leaves a part that is a plain string as it is. A `ForeignKeyName` answers for the table it points at as well as its own; an `Expressions` takes its columns from those its expressions use, relabels the expressions when its table is renamed, and replaces them with an altered copy when a column is.

The editor asks at these changes: `BaseDatabaseSchemaEditor.delete_model` and `BaseDatabaseSchemaEditor.remove_field` take off the statements that refer to the dropped table or column, `BaseDatabaseSchemaEditor._delete_index_sql` one that would make the index being dropped, `BaseDatabaseSchemaEditor._alter_field` renames a column in each ([Altering a column, and SQLite's table remake](alter-field.md)), and `BaseDatabaseSchemaEditor.alter_db_table` renames a table. That method sends `BaseDatabaseSchemaEditor.sql_rename_table` unless the names are equal, or differ only in case where the features have `ignores_table_name_case`, records the rename where it is collecting, and tells each deferred `Statement` (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.alter_db_table`). An editor that collects, entered as above, makes the buoy's table, with a second index, `"buoy_port_name_idx"`, in its `Meta`, and renames it:

```text recording=backends
editor.create_model(Buoy)
editor.alter_db_table(Buoy, 'moorings_buoy', 'moorings_float')
  BaseDatabaseSchemaEditor.alter_db_table(Buoy, 'moorings_buoy', 'moorings_float')
    BaseDatabaseSchemaEditor.execute(a str)
full([str(statement) for statement in editor.deferred_sql])  ->  ['CREATE INDEX "moorings_float_port_id_ae0f6525" ON "moorings_float" ("port_id")', 'CREATE INDEX "buoy_name_idx" ON "moorings_float" ("name")', 'CREATE INDEX "buoy_port_name_idx" ON "moorings_float" ("port_id", "name")']
```

Every part that names the table now names the new one, the field index's name too: `"moorings_float_port_id_ae0f6525"`, where `create_model` above gave `"moorings_buoy_port_id_d16249a7"`. The function that `BaseDatabaseSchemaEditor._create_index_sql` hands to its `IndexName` makes the name the first time it is written out, here after the rename, and keeps it, so that one written out before a rename keeps the old table's (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._create_index_sql`); `_delete_index_sql` writes out the name of each deferred statement on its table, to compare with the index it drops. SQLite's table remake relies on the renaming: the indexes it defers for the new table, made under a name beginning `"new__"`, follow the table when `alter_db_table` gives it the old name back ([Altering a column, and SQLite's table remake](alter-field.md)).

## The names of indexes and constraints

`BaseDatabaseSchemaEditor._create_index_name` makes the names the editor chooses, for an index, a foreign key, a unique constraint, a check or a primary key, from the table's name, the columns' names joined with underscores, and a digest followed by a suffix (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._create_index_name`). `split_identifier` first drops any schema before the table's name, and the digest is eight hexadecimal digits of an MD5 of the whole table's name and columns' names, made by `names_digest` (`django/db/backends/utils.py:split_identifier`, `django/db/backends/utils.py:names_digest`). The longest name allowed is the operations object's `BaseDatabaseOperations.max_name_length`, or 200 where that gives no limit:

```text recording=backends
connection.ops.max_name_length()  ->  None
editor._create_index_name('fleet_ship', ['home_id', 'tonnage'])  ->  'fleet_ship_home_id_tonnage_42e042f7'
editor._create_index_name('fleet_ship', ['home_id', 'tonnage'], suffix='_fk')  ->  'fleet_ship_home_id_tonnage_42e042f7_fk'
names_digest('fleet_ship', 'home_id', 'tonnage', length=8)  ->  '42e042f7'
```

The suffix is not in the digest, so a foreign key and an index on the same columns share their digits. A name too long is shortened: the table's name and the columns' names each keep at most half of what the limit leaves after the digest and suffix, less one for an underscore, which is 95 characters under a limit of 200 and 26 under PostgreSQL's 63; with one short column's name, the names below come to 114 characters and 45. The digest of the whole names keeps a shortened name apart from others cut to the same characters; one that would then begin with an underscore or a digit gets a `"D"` in front, the comment saying such a beginning is not permitted on Oracle:

```text recording=backends
long_table = 'office_' + 'manifest_' * 25
len(long_table)  ->  232
editor._create_index_name(long_table, ['voyage_id'])  ->  'office_manifest_manifest_manifest_manifest_manifest_manifest_manifest_manifest_manifest_manifes_voyage_id_96784cd8'
len(editor._create_index_name(long_table, ['voyage_id']))  ->  114
postgresql.ops.max_name_length()  ->  63
postgresql.SchemaEditorClass(postgresql)._create_index_name(long_table, ['voyage_id'])  ->  'office_manifest_manifest_m_voyage_id_96784cd8'
```

`truncate_name`, Django's other way of shortening a name, used for the table name Django makes for a model and the names Oracle's operations object quotes, keeps the first characters and puts four digits of an MD5 of the whole name in place of the rest; Oracle's limit is 30 (`django/db/backends/utils.py:truncate_name`, `django/db/backends/oracle/operations.py:DatabaseOperations.max_name_length`):

```text recording=backends
truncate_name('office_manifest_voyage_index', oracle.ops.max_name_length())  ->  'office_manifest_voyage_index'
truncate_name('office_manifest_voyage_index_for_the_long_haul', oracle.ops.max_name_length())  ->  'office_manifest_voyage_ind69d7'
truncate_name('office_manifest_voyage_index_for_the_long_haul', connection.ops.max_name_length())  ->  'office_manifest_voyage_index_for_the_long_haul'
```

## Names the editor did not make: `_constraint_names`

A column's primary key, its `"UNIQUE"` and its check are written without a name, and so is SQLite's foreign key, so whatever name such a constraint has is the database's choice; a table made by another program has names of its own. To drop one, the editor reads the names back. `BaseDatabaseSchemaEditor._constraint_names` asks introspection's `get_constraints` for the table, a dictionary from each constraint's name to its columns and its kind, and returns the names whose columns are exactly those given, in order, or any where none are given, and whose kind is the one asked for, less any it is told to exclude (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._constraint_names`) ([Introspection: reading the schema back](introspection.md)). The docstring of `BaseDatabaseIntrospection.get_constraints` warns that a backend may return names that do not exist for constraints it does not name, as SQLite's does.

`BaseDatabaseSchemaEditor.remove_field` and `BaseDatabaseSchemaEditor._alter_field` find a foreign key's constraints this way, `_alter_field` also a column's unique constraint, index and check, excluding the names the model's `Meta` declares, and `BaseDatabaseSchemaEditor._delete_primary_key` the primary key. The column names pass first, where the features have `truncates_names`, through `truncate_name`, and then through introspection's `identifier_converter`, which on Oracle puts them in lower case; an editor that collects asks under the old name of a table renamed while collecting.

## The backends' editors

The backends' editors change the base class through its templates, class attributes such as `BaseDatabaseSchemaEditor.sql_delete_table`; through the small methods it calls, such as `BaseDatabaseSchemaEditor.prepare_default`; and by overriding whole operations where their database cannot do what it asks. SQLite's (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor`) builds a table again for most changes; PostgreSQL's (`django/db/backends/postgresql/schema.py:DatabaseSchemaEditor`) keeps identity columns and sequences right when a column's type changes; MySQL's (`django/db/backends/mysql/schema.py:DatabaseSchemaEditor`) has its own templates for altering and renaming and its own rules for defaults; and Oracle's (`django/db/backends/oracle/schema.py:DatabaseSchemaEditor`), where Oracle refuses a change of a column's type, copies the column into a new one. Each has its section: [SQLite](sqlite.md), [PostgreSQL](postgresql.md), [MySQL and MariaDB](mysql.md), [Oracle](oracle.md).
