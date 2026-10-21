---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The database
contents: editor, alter-field, introspection, test-databases
---

# Schemas and test databases

Django changes a database's structure from the models: a schema editor writes the DDL for one database and sends it, holding some statements, ordinarily until it is left; introspection reads the structure back where the models cannot answer; and for tests a whole database is made, in which migrate builds the models' tables and the flush can empty them.

The statements that create, alter and drop tables, columns, indexes and constraints are a database's **DDL**, and databases differ in it: whether a rollback undoes it, whether a foreign key can be added by a statement of its own, whether a column can be changed without building its table again. Django writes it from the models: a migration hands the editor a model rendered from its state, and the editor works out the statements from the model's fields and options. Some statements are not sent the moment they are written, among them the indexes of a table being made and a foreign key to a table that may not exist yet: the editor holds them, ordinarily until it is left. And now and then the models cannot answer: the name the database gave a constraint, which the editor needs to drop it; the tables that exist; a whole schema Django did not make. Then the database is asked. The chapter's shape is a round trip, down from the models through the editor and up from the database's own catalog through introspection, with the test databases beside it, in which migrate builds the models' tables through the same editor.

The examples are harbour's, whose models [Models and fields](models.md) lists. The recording was made from a running Django, on SQLite. A line at the left is a line of Python as it was run; the lines set in under it are the calls it set going, nested as they were made, with only the calls the passage is about written down; `->` is the value a line gave; a backend's class written without its module, DatabaseSchemaEditor, is SQLite's; a line `SQL` is a statement as Django handed it to its cursor; full( is a helper of the recording's own that writes a value whole; and a line of three dots stands for lines of the block left out.

## The editor, a bracket

The **schema editor** is the object through which Django changes a database's schema. `BaseDatabaseSchemaEditor` turns a model created or deleted, a field added or removed, and an index or a constraint added or dropped into statements for one database, and each of the four backends subclasses it; `BaseDatabaseWrapper.schema_editor` makes one (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor`, `django/db/backends/base/base.py:BaseDatabaseWrapper.schema_editor`). It is used as a context manager, and what it does between entering and leaving is one bracket. Entering it sets up an empty list of **deferred statements** and, where the database can roll back DDL, ordinarily enters an atomic block ([Transactions: autocommit, `atomic` and savepoints](connections/atomic.md)); each method sends the statements it writes, or collects them as text where the editor was made to collect, and appends to the list what must wait; leaving it, when no exception is leaving, executes the deferred statements as it executed the others, and then leaves the atomic block (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.__enter__`, `django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.__exit__`). Here an editor made to collect is given a model of the recording's own, Buoy, with a foreign key to Port and an index of its own:

```text recording=backends
...
editor = connection.schema_editor(collect_sql=True)
editor.__enter__()
  DatabaseSchemaEditor.__enter__
...
    BaseDatabaseSchemaEditor.__enter__
      Atomic.__enter__
        SQL BEGIN
editor.create_model(Buoy)
  BaseDatabaseSchemaEditor.create_model(Buoy)
...
    BaseDatabaseSchemaEditor.execute(a str)
full([str(statement) for statement in editor.deferred_sql])  ->  ['CREATE INDEX "moorings_buoy_port_id_d16249a7" ON "moorings_buoy" ("port_id")', 'CREATE INDEX "buoy_name_idx" ON "moorings_buoy" ("name")']
...
editor.__exit__(None, None, None)
  DatabaseSchemaEditor.__exit__
...
    BaseDatabaseSchemaEditor.__exit__
      BaseDatabaseSchemaEditor.execute(a Statement)
      BaseDatabaseSchemaEditor.execute(a Statement)
      Atomic.__exit__
        BaseDatabaseWrapper.commit
...
'moorings_buoy' in connection.introspection.table_names()  ->  False
  SQL SELECT name, type FROM sqlite_master WHERE type in ('table', 'view') AND NOT name='sqlite_sequence' ORDER BY name
```

`create_model` handed the table's statement to `execute`, which, in an editor made to collect, sent nothing (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor.create_model`); the two indexes, the foreign key's and Buoy's own, waited in `deferred_sql` until the editor was left, and were executed there, before the commit. Since the editor sent none of its statements, the catalog, asked afterwards, has no such table. On SQLite the bracket is wider still: the backend's editor turns the database's checks of foreign keys off as it is entered, and as it is left checks every table before the held statements are sent and turns the checks on again last; it refuses to be entered where the switch does not take, as SQLite ignores it inside a transaction (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__enter__`, `django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor.__exit__`). Migrations are the editor's main user: the operations' database halves call its methods, ordinarily inside an editor that the executor opens for each migration (`django/db/migrations/executor.py:MigrationExecutor.apply_migration`) ([The schema editor: `BaseDatabaseSchemaEditor`](schema/editor.md)).

Changing a column is the editor's longest work. `BaseDatabaseSchemaEditor.alter_field` is handed a field's old definition and its new one, and takes the column from the first to the second in a fixed order, dropping first what depends on the column and making it again last, with the columns of other tables that must follow it (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._alter_field`) ([Altering a column, and SQLite's table remake](schema/alter-field.md)). SQLite, which can rename a column in place but change it in no other way, builds the table again: a new table made from the new definition, the rows copied into it, the old table dropped and the new one renamed (`django/db/backends/sqlite3/schema.py:DatabaseSchemaEditor._remake_table`).

## Reading the schema back

`BaseDatabaseIntrospection` is the class of a connection's **introspection**, the object that asks a database what its schema holds and answers in Django's terms: the tables and views, a table's columns, its foreign keys, primary key, constraints and indexes, and the sequences that number its new rows (`django/db/backends/base/introspection.py:BaseDatabaseIntrospection`). Each database keeps a catalog of its own schema and is asked in its own way: SQLite through its table `"sqlite_master"`, as above, and through `"PRAGMA"` statements; PostgreSQL through `"pg_catalog"`; MySQL through `"information_schema"` and `"SHOW INDEX"`; Oracle through its dictionary views. Its callers are the jobs that need what the database actually holds, among them these. The schema editor, to drop a constraint or an index that a field implies, needs the name the database knows it by, and finds it among the table's constraints by their columns and kinds (`django/db/backends/base/schema.py:BaseDatabaseSchemaEditor._constraint_names`). migrate, given `--run-syncdb`, asks which tables exist, and with `--fake-initial` whether an initial migration's tables and columns are there already. inspectdb writes models for tables Django did not make. And the flush, which empties the models' tables, asks which of them exist before it writes the statements that empty them (`django/core/management/sql.py:sql_flush`) ([Introspection: reading the schema back](schema/introspection.md)).

The figure draws the round trip: the editor's statements going down, some at once and some held, ordinarily to the end of its bracket, and introspection's questions coming up to four of the jobs that ask them.

```text figure=the-round-trip
the models, or a migration's state of them              the schema editor   for a name the database chose,
  a model class, or a historical model                                      to drop a constraint
                                                        migrate             for the tables that exist
                                                                            (--run-syncdb, --fake-initial)
                                                        inspectdb           for a schema Django did not make
                                                        the flush           for the tables to empty
                                                          asked by, among others
down: the schema editor, a bracket                      up: introspection
  entered  on SQLite, foreign key checks off;             the tables, a table's columns, keys, constraints and indexes
           where the database can roll DDL back,
           ordinarily an atomic block                   for tests
           create_model, alter_field ...                  creation makes a database
                                                            beside the one the settings name;
           a statement sent at once                       migrate builds the models' tables through the editor;
           a statement held in deferred_sql               a copy is ordinarily made for each process of a parallel run;
             ordinarily until the editor is left          the flush empties it after some tests
  left     on SQLite, every table checked;
           the held statements;
           the atomic block left;
           on SQLite, the checks on again

the database's catalog
  SQLite: sqlite_master and PRAGMA                      PostgreSQL: pg_catalog
  MySQL: information_schema                             Oracle: the dictionary views
```

*The two ways between the models and a database's catalog. The schema editor goes down from the models, holding some statements, ordinarily to the end of its bracket; introspection comes up, and only where a job needs what the database holds. migrate builds the models' tables in a test database through the same editor.*

## A database for tests

Tests write to the database, and must not write to the one the settings name. `BaseDatabaseCreation` is the class of a connection's **creation**, the object that makes the database a test run works in and destroys it afterwards (`django/db/backends/base/creation.py:BaseDatabaseCreation`). `BaseDatabaseCreation.create_test_db` ordinarily makes the database, points the alias's settings at it so that every connection to the alias reaches it, and calls migrate, which builds the models' tables through the schema editor as it would on any database (`django/db/backends/base/creation.py:BaseDatabaseCreation.create_test_db`). A run in several processes needs a copy for each, which creation ordinarily makes; and a test that empties the tables after itself takes with it the rows that migrations wrote, which creation can keep as text and load again. Which aliases need a database, and in what order, the test runner decides ([Test databases: `BaseDatabaseCreation`](schema/test-databases.md), [Which databases a test uses: `databases`](testing/test-databases.md)).

## The neighbours

The model an editor is handed is described in [Models and fields](models.md), and the column type it writes for a field is the backend's ([Column types: from a field to a column](backends/column-types.md)); the four backends' own editors are told with their databases in [Database backends](backends.md). The connection an editor works on, and its transactions, are [Connections and transactions](connections.md)'s. Migrations hand the editor historical models, and decide which migrations run against which database ([Migrations](migrations.md)); the test framework calls creation and the flush ([The test framework](testing.md)), and the commands migrate, flush and inspectdb are in [Management commands](commands.md).
