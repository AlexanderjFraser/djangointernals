---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# INSERT, UPDATE and DELETE: the insert, update and delete compilers

An insert, an update and a delete have a `Query` subclass each, `InsertQuery`, `UpdateQuery` and `DeleteQuery`, and a compiler each, `SQLInsertCompiler`, `SQLUpdateCompiler` and `SQLDeleteCompiler`. This page is how each statement is written: every value through the field that owns it, a key or a computed column asked back with `"RETURNING"` where the backend can, and the joins of a filter moved into a subquery on the primary key, since SQL allows an update or a delete no join (`django/db/models/sql/compiler.py:SQLInsertCompiler`, `django/db/models/sql/compiler.py:SQLUpdateCompiler`, `django/db/models/sql/compiler.py:SQLDeleteCompiler`).

A statement that reads has one shape, and the assembly of that shape is [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md). The three statements that write have less in common with it than with one another. An insert has to turn instances into rows of values, each value taken off its instance and prepared by its field before any row exists for an expression to refer to, and bring back what the database decided for the row: the key of an auto field, a default the database applied, a column it computes. An update has to set columns, to values or to expressions over the row itself, under a condition that a queryset wrote and that may join other tables, as the `"WHERE"` of an `"UPDATE"` cannot. A delete has the same difficulty with its condition, and nothing else. So each has a `Query` subclass that holds what its statement needs beyond a query's joins and where tree, and a compiler of its own, named by the subclass's `Query.compiler` and fetched, like the compiler of a select, from the connection's operations object (`django/db/models/sql/subqueries.py`, `django/db/models/sql/query.py:Query.get_compiler`). Each compiler overrides `SQLCompiler.as_sql`, and what it inherits is the compiling of an expression, the quoting of a name, the converters, and the base's `SQLCompiler.execute_sql` with its result types, which the update and delete compilers run their statements through.

What calls them is elsewhere, in a sentence each. `QuerySet._insert` makes an `InsertQuery` and runs it, for `Model.save` and for `QuerySet.bulk_create`; `QuerySet.update` and `QuerySet._update` chain the queryset's query into an `UpdateQuery`; `QuerySet._raw_delete` turns a clone of the queryset's query into a `DeleteQuery`; and `Collector.delete` uses that for the rows it never fetched and `DeleteQuery.delete_batch` and `UpdateQuery.update_batch` for the instances it holds, by key (`django/db/models/deletion.py:Collector.delete`). The pages are [Creating, updating and deleting through a queryset](../querysets/writing.md), [`bulk_create` and `bulk_update`](../querysets/bulk.md), [Saving an instance](../models/saving.md) and [Deleting: the `Collector`](../models/deleting.md).

The recordings below were made from a running Django, on SQLite, over the ports, ships and sailors of the chapter's opening page ([From QuerySet to SQL](../sql.md)) and one model of the office, shown where it comes in. A line at the left is Python as it was run, with its value after `->` where it is an expression, or the exception it raised; under it, nested as they were made, are the calls it set going that the passage is about, with `->` what each returned; and a line that begins `SQL` is a statement as Django handed it to its cursor.

## The insert: `InsertQuery` and its compiler

`InsertQuery` is made with the conflict mode, an `OnConflict`, which is `OnConflict.IGNORE`, `OnConflict.UPDATE` or `None`, and the fields to update and the unique fields that mode may need; `InsertQuery.insert_values` then gives it the fields to write, the instances, and whether the values are to be taken as they stand on the instances, which a raw save asks for (`django/db/models/sql/subqueries.py:InsertQuery.insert_values`). It has the joins and the where tree of any query, and its compiler writes neither. `QuerySet._insert` makes one and at once calls `SQLInsertCompiler.execute_sql` on its compiler with the fields whose values are to come back (`django/db/models/query.py:QuerySet._insert`, `django/db/models/sql/compiler.py:SQLInsertCompiler.execute_sql`).

### The values, field by field

`SQLInsertCompiler.as_sql` begins with the statement's first words, which the backend's operations write: `"INSERT INTO"` from `BaseDatabaseOperations.insert_statement`, or on SQLite `"INSERT OR IGNORE INTO"` and on MySQL `"INSERT IGNORE INTO"` for `OnConflict.IGNORE` (`django/db/models/sql/compiler.py:SQLInsertCompiler.as_sql`, `django/db/backends/sqlite3/operations.py:DatabaseOperations.insert_statement`). Then it goes field by field, and for each field instance by instance. `SQLInsertCompiler.pre_save_val` takes the value: the field's `Field.pre_save` with `add=True`, which is the hook by which `auto_now_add` sets the moment of signing on, or the attribute as it stands where the query is raw (`django/db/models/sql/compiler.py:SQLInsertCompiler.pre_save_val`, `django/db/models/fields/__init__.py:Field.pre_save`). Then `SQLInsertCompiler.prepare_value`, unless the value is a `DatabaseDefault`, below.

`prepare_value` resolves a value that has `resolve_expression` against the insert query, with `allow_joins=False` and `for_save=True`, and refuses three kinds of what comes back: an expression with `contains_column_references`, with `ValueError` and a message that says `F()` expressions can only be used to update, not to insert, since, as the comment puts it, a column refers to an existing row and the row of an insert does not exist yet; one with `contains_aggregate`, with `FieldError`; and one with `contains_over_clause`, with `FieldError` too. Then the field's `Field.get_db_prep_save`, with the connection, which hands an expression back as it is and prepares a plain value through the field's `get_db_prep_value` ([A field, the base class](../models/fields.md)) (`django/db/models/sql/compiler.py:SQLInsertCompiler.prepare_value`, `django/db/models/fields/__init__.py:Field.get_db_prep_save`).

```text recording=sql
Port.objects.create(name=Lower(Value('TOBERMORY')), country=Concat(Value('Scot'), Value('land'))).name  ->  'tobermory'
  SQL INSERT INTO "fleet_port" ("name", "country") VALUES (LOWER(%s), (COALESCE(%s, %s) || COALESCE(%s, %s))) RETURNING "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" with params ('TOBERMORY', 'Scot', '', 'land', '')
...
Port.objects.create(name=F('country'), country='x')  ->  raises ValueError: Failed to insert expression "Col(fleet_port, fleet.Port.country)" on fleet.Port.name. F() expressions can only be used to update, not to insert.
Port.objects.create(name=Count('ships'), country='x')  ->  raises FieldError: Joined field references are not permitted in this query
Port.objects.create(name=Window(RowNumber()), country='x')  ->  raises FieldError: Window expressions are not allowed in this query (name=<Window: RowNumber() OVER ()>).
```

The first port was given two expressions, and each was compiled into its place in the `"VALUES"` list; the statement asked both columns back with the key, because `Model._save_table` adds to the fields to return every field whose value is an expression, and the instance's name came back in lower case ([Saving an instance](../models/saving.md)). Of the three refusals, the first is `prepare_value`'s own. The second came earlier: resolving `Count("ships")` with `allow_joins=False` refused the join its name needs, in `Query.resolve_ref`, before the aggregate was tested for (`django/db/models/sql/query.py:Query.resolve_ref`). The window reached the third.

### A default the database applies, and a column it computes

A Manifest of the office is what a voyage carried. Its primary key is a serial that a function of the project supplies; its weight is a column the database computes from two others; and whether it was stamped defaults in the database, not in Python:

```python
# harbour/office/models.py
class Manifest(models.Model):
    serial = models.CharField(max_length=8, primary_key=True, default=serials.next_serial)
    voyage = models.ForeignKey("fleet.Voyage", on_delete=models.CASCADE)
    crates = models.PositiveIntegerField()
    kilos_each = models.PositiveIntegerField()
    kilos = models.GeneratedField(expression=F("crates") * F("kilos_each"), output_field=models.PositiveIntegerField(), db_persist=True)
    stamped = models.BooleanField(db_default=False)
    scan = models.FileField(upload_to="manifests/", blank=True)
```

For a field with `db_default` and no `default`, `Field.get_default` returns a `DatabaseDefault` around the default's expression, so an instance made without a value for `"stamped"` holds one; `pre_save` returns it and `as_sql` leaves it unprepared (`django/db/models/fields/__init__.py:Field._get_default`, `django/db/models/expressions.py:DatabaseDefault`). A field with a database default whose values are all such is dropped from the statement with its values, unless it is the only field left, since an insert needs one column: the comment calls the values redundant, and says they could prevent optimizations. Where the field stays, because some instance was given a value or it is the last, and the backend has `supports_default_keyword_in_bulk_insert`, each `DatabaseDefault` goes into the statement as an expression, and `DatabaseDefault.as_sql` writes `"DEFAULT"`, or compiles the default's own expression where the backend lacks `supports_default_keyword_in_insert`, as SQLite does; where the backend lacks the keyword in a bulk insert, Oracle, each is replaced by the prepared default before the statement is assembled (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_default_keyword_in_bulk_insert`, `django/db/backends/sqlite3/features.py:DatabaseFeatures.supports_default_keyword_in_insert`). Neither `Model._save_table` nor `bulk_create` sends a `GeneratedField` to the compiler: each leaves out every field with `Field.generated` (`django/db/models/fields/generated.py:GeneratedField`).

What the database decides is asked back instead. `Options.db_returning_fields` lists the fields of a model that have `db_returning`: an auto field, a field with a database default, a generated field (`django/db/models/options.py:Options.db_returning_fields`). Here spring is the Petrel's voyage:

```text recording=sql
Manifest.objects.create(voyage=spring, crates=12, kilos_each=80)
  InsertQuery.insert_values(fields=[Manifest.serial, Manifest.voyage, Manifest.crates, Manifest.kilos_each, Manifest.stamped, Manifest.scan], objs=[<Manifest: Manifest object (M-0002)>])
  SQLInsertCompiler.execute_sql(returning_fields=[Manifest.kilos, Manifest.stamped])
...
      SQLInsertCompiler.pre_save_val(Manifest.stamped, <Manifest: Manifest object (M-0002)>)  ->  DatabaseDefault(Value(False))
      SQLInsertCompiler.pre_save_val(Manifest.scan, <Manifest: Manifest object (M-0002)>)  ->  a FieldFile
      SQLInsertCompiler.prepare_value(Manifest.scan, a FieldFile)  ->  ''
      SQLInsertCompiler.assemble_as_sql(fields=[Manifest.serial, Manifest.voyage, Manifest.crates, Manifest.kilos_each, Manifest.scan], value_rows=[('M-0002', 1, 12, 80, '')])
...
      BaseDatabaseOperations.returning_columns([Manifest.kilos, Manifest.stamped])  ->  ('RETURNING "office_manifest"."kilos", "office_manifest"."stamped"', ())
      -> [('INSERT INTO "office_manifest" ("serial", "voyage_id", "crates", "kilos_each", "scan") VALUES (%s, %s, %s, %s, %s) RETURNING "office_manifest"."kilos", "office_manifest"."stamped"', ('M-0002', 1, 12, 80, ''))]
    SQL INSERT INTO "office_manifest" ("serial", "voyage_id", "crates", "kilos_each", "scan") VALUES (%s, %s, %s, %s, %s) RETURNING "office_manifest"."kilos", "office_manifest"."stamped" with params ('M-0002', 1, 12, 80, '')
    BaseDatabaseOperations.fetch_returned_rows  ->  [(960, False)]
    -> [[960, False]]
```

Six fields came in, the generated one already left out. The value of `"stamped"` was a `DatabaseDefault`, which was not prepared, and the field was dropped before the values were assembled: five columns. The two columns asked back were the computed weight, twelve crates of eighty kilos, and the default the database applied.

### Placeholders, and the shape of the statement

`SQLInsertCompiler.assemble_as_sql` turns the fields and the rows of values into rows of placeholders and rows of parameters, one value at a time through `SQLInsertCompiler.field_as_sql` (`django/db/models/sql/compiler.py:SQLInsertCompiler.assemble_as_sql`, `django/db/models/sql/compiler.py:SQLInsertCompiler.field_as_sql`). A value whose field is `None` is raw SQL and becomes the placeholder itself; a field with a `get_placeholder_sql` method writes its own, as `BinaryField.get_placeholder_sql` does, and a field class that declares the older `"get_placeholder"` instead is given a `get_placeholder_sql` by `Field.__init_subclass__`, which warns with `RemovedInDjango2028Warning` (`django/db/models/fields/__init__.py:Field.__init_subclass__`); an expression is compiled; anything else is `"%s"` with the value as its parameter. `BaseDatabaseOperations.modify_insert_params` is given each pair last, a hook the comment says is used by Oracle Spatial alone, for a ticket it cites (`django/db/backends/base/operations.py:BaseDatabaseOperations.modify_insert_params`). The one case with no field at all, which the comment says can only be a model whose primary key is a single auto field, writes one row an instance with `BaseDatabaseOperations.pk_default_value` raw in the key's column, `"DEFAULT"` in the base class and `"NULL"` on SQLite, MySQL and Oracle (`django/db/backends/base/operations.py:BaseDatabaseOperations.pk_default_value`).

The rest of the statement is the backend's. `BaseDatabaseOperations.on_conflict_suffix_sql` is given the fields, the mode and the columns to update and to match on, and writes nothing in the base class; SQLite's and PostgreSQL's write `ON CONFLICT(...) DO UPDATE SET` with each column set from `"EXCLUDED"` for `OnConflict.UPDATE`, PostgreSQL's `ON CONFLICT DO NOTHING` for `OnConflict.IGNORE`, and MySQL's `ON DUPLICATE KEY UPDATE` (`django/db/backends/base/operations.py:BaseDatabaseOperations.on_conflict_suffix_sql`, `django/db/backends/sqlite3/operations.py:DatabaseOperations.on_conflict_suffix_sql`). Then one of three shapes, by whether `execute_sql` set `SQLInsertCompiler.returning_fields` and by two features. Where columns are to come back and the backend has `can_return_columns_from_insert`, there is one statement: `BaseDatabaseOperations.bulk_insert_sql` writes one `"VALUES"` list for all the rows where the backend has `can_return_rows_from_bulk_insert`, and the first row alone otherwise; then the conflict suffix; then `BaseDatabaseOperations.returning_columns`, which writes `"RETURNING"` and the columns and may hand back parameters of its own, Oracle's binds, kept as `SQLInsertCompiler.returning_params` (`django/db/backends/base/operations.py:BaseDatabaseOperations.bulk_insert_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.returning_columns`). Where nothing is to come back and the backend has `has_bulk_insert`, there is one statement with the one list and the suffix. Otherwise there is a statement a row, each with its own `"VALUES"`. `as_sql` returns a list of statements with their parameters, one or many. The base class has the two returning features false; SQLite and PostgreSQL set both true, Oracle can return columns but not the rows of a bulk insert, and MySQL's features class answers either for MariaDB alone (`django/db/backends/base/features.py:BaseDatabaseFeatures.can_return_columns_from_insert`, `django/db/backends/mysql/features.py:DatabaseFeatures.can_return_columns_from_insert`).

```text recording=sql
SQLInsertCompiler for one row: each field's value through pre_save and prepare_value, one placeholder each, and RETURNING for the key
    oban = Port.objects.create(name='Oban', country='Scotland')
      InsertQuery.insert_values(fields=[Port.name, Port.country], objs=[<Port: Oban>])
      SQLInsertCompiler.execute_sql(returning_fields=[Port.id])
        SQLInsertCompiler.as_sql
          DatabaseOperations.insert_statement(on_conflict=None)  (sqlite3)
            BaseDatabaseOperations.insert_statement
            -> 'INSERT INTO'
          SQLInsertCompiler.pre_save_val(Port.name, <Port: Oban>)  ->  'Oban'
          SQLInsertCompiler.prepare_value(Port.name, 'Oban')  ->  'Oban'
          SQLInsertCompiler.pre_save_val(Port.country, <Port: Oban>)  ->  'Scotland'
          SQLInsertCompiler.prepare_value(Port.country, 'Scotland')  ->  'Scotland'
          SQLInsertCompiler.assemble_as_sql(fields=[Port.name, Port.country], value_rows=[('Oban', 'Scotland')])
            SQLInsertCompiler.field_as_sql(Port.name, 'Oban')  ->  ('%s', ['Oban'])
            SQLInsertCompiler.field_as_sql(Port.country, 'Scotland')  ->  ('%s', ['Scotland'])
            -> ((('%s', '%s'),), [['Oban', 'Scotland']])
          DatabaseOperations.on_conflict_suffix_sql(on_conflict=None)  (sqlite3)
            BaseDatabaseOperations.on_conflict_suffix_sql(fields=[Port.name, Port.country], on_conflict=None, update_fields=a generator, unique_fields=a generator)
            -> ''
          BaseDatabaseOperations.bulk_insert_sql(fields=[Port.name, Port.country], placeholder_rows=[['%s', '%s']])  ->  'VALUES (%s, %s)'
          BaseDatabaseOperations.returning_columns([Port.id])  ->  ('RETURNING "fleet_port"."id"', ())
          -> [('INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id"', ('Oban', 'Scotland'))]
        SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Oban', 'Scotland')
        BaseDatabaseOperations.fetch_returned_rows  ->  [(4,)]
        -> [(4,)]
    oban.pk  ->  4
```

The key was asked for, and SQLite can return it, so the first shape was taken: one statement with a `"RETURNING"`, run on a cursor, and the returned row fetched. Two ports at once, through `bulk_create`:

```text recording=sql
Port.objects.bulk_create([Port(name='Mull', country='Scotland'), Port(name='Skagen', country='Denmark')])
  InsertQuery.insert_values(fields=[Port.name, Port.country], objs=[<Port: Mull>, <Port: Skagen>])
  SQLInsertCompiler.execute_sql(returning_fields=[Port.id])
...
      BaseDatabaseOperations.bulk_insert_sql(fields=[Port.name, Port.country], placeholder_rows=[['%s', '%s'], ['%s', '%s']])  ->  'VALUES (%s, %s), (%s, %s)'
      BaseDatabaseOperations.returning_columns([Port.id])  ->  ('RETURNING "fleet_port"."id"', ())
      -> [('INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s), (%s, %s) RETURNING "fleet_port"."id"', ('Mull', 'Scotland', 'Skagen', 'Denmark'))]
    SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s), (%s, %s) RETURNING "fleet_port"."id" with params ('Mull', 'Scotland', 'Skagen', 'Denmark')
    BaseDatabaseOperations.fetch_returned_rows  ->  [(5,), (6,)]
    -> [(5,), (6,)]
```

The values were gathered field by field and so instance by instance within a field, and `assemble_as_sql` turned them back into rows. Since SQLite returns the rows of a bulk insert, `bulk_insert_sql` wrote one list for both and both keys came back. A backend that returns columns but not the rows of a bulk insert would be sent the first row alone, and on such a backend `QuerySet._batched_insert` asks for nothing back ([`bulk_create` and `bulk_update`](../querysets/bulk.md)). The two conflict modes, over a logbook whose key is already taken:

```text recording=sql
Logbook.objects.bulk_create([Logbook(pk=1, title='Log 1, again')], ignore_conflicts=True)
  InsertQuery.insert_values(fields=[Logbook.id, Logbook.title], objs=[<Logbook: Logbook object (1)>])
  SQLInsertCompiler.execute_sql(returning_fields=None)
    SQLInsertCompiler.as_sql
      DatabaseOperations.insert_statement(on_conflict=OnConflict.IGNORE)  (sqlite3)  ->  'INSERT OR IGNORE INTO'
      DatabaseOperations.on_conflict_suffix_sql(on_conflict=OnConflict.IGNORE)  (sqlite3)
        BaseDatabaseOperations.on_conflict_suffix_sql(fields=[Logbook.id, Logbook.title], on_conflict=OnConflict.IGNORE, update_fields=a generator, unique_fields=a generator)
        -> ''
      BaseDatabaseOperations.bulk_insert_sql(fields=[Logbook.id, Logbook.title], placeholder_rows=[['%s', '%s']])  ->  'VALUES (%s, %s)'
      -> [('INSERT OR IGNORE INTO "office_logbook" ("id", "title") VALUES (%s, %s)', (1, 'Log 1, again'))]
    SQL INSERT OR IGNORE INTO "office_logbook" ("id", "title") VALUES (%s, %s) with params (1, 'Log 1, again')
    -> []
...
Logbook.objects.bulk_create([Logbook(pk=1, title='Log 1, fair copy')], update_conflicts=True, update_fields=['title'], unique_fields=['pk'])
  InsertQuery.insert_values(fields=[Logbook.id, Logbook.title], objs=[<Logbook: Logbook object (1)>])
  SQLInsertCompiler.execute_sql(returning_fields=[Logbook.id])
    SQLInsertCompiler.as_sql
      DatabaseOperations.insert_statement(on_conflict=OnConflict.UPDATE)  (sqlite3)
        BaseDatabaseOperations.insert_statement(on_conflict=OnConflict.UPDATE)
        -> 'INSERT INTO'
      DatabaseOperations.on_conflict_suffix_sql(on_conflict=OnConflict.UPDATE)  (sqlite3)  ->  'ON CONFLICT("id") DO UPDATE SET "title" = EXCLUDED."title"'
      BaseDatabaseOperations.bulk_insert_sql(fields=[Logbook.id, Logbook.title], placeholder_rows=[['%s', '%s']])  ->  'VALUES (%s, %s)'
      BaseDatabaseOperations.returning_columns([Logbook.id])  ->  ('RETURNING "office_logbook"."id"', ())
      -> [('INSERT INTO "office_logbook" ("id", "title") VALUES (%s, %s) ON CONFLICT("id") DO UPDATE SET "title" = EXCLUDED."title" RETURNING "office_logbook"."id"', (1, 'Log 1, fair copy'))]
    SQL INSERT INTO "office_logbook" ("id", "title") VALUES (%s, %s) ON CONFLICT("id") DO UPDATE SET "title" = EXCLUDED."title" RETURNING "office_logbook"."id" with params (1, 'Log 1, fair copy')
    BaseDatabaseOperations.fetch_returned_rows  ->  [(1,)]
```

For the first mode SQLite's `insert_statement` wrote the conflict into the statement's first words and the suffix was empty; nothing was asked back, because `QuerySet._batched_insert` asks for the returning fields only where the mode is `None` or `OnConflict.UPDATE`. For the second the suffix carried the update and the key came back. The `"RETURNING"` is SQLite's, and so is the suffix, which its operations class writes only where its features class has `supports_update_conflicts_with_target`.

### `execute_sql`: the statements run, and the rows asked back

`SQLInsertCompiler.execute_sql` takes the fields whose columns are to come back and asserts that, where there are any and more than one instance, the backend has `can_return_rows_from_bulk_insert`. It opens a cursor, runs each statement `as_sql` returns, and with no returning fields returns an empty list. Otherwise the rows come one of two ways. Where the backend can return them, the rows of a bulk insert for several instances or the columns of an insert for one, `BaseDatabaseOperations.fetch_returned_rows` reads them from the cursor, with the kept parameters; or else, where the first returning field is an `AutoField`, one row is made of `BaseDatabaseOperations.last_insert_id`, which is the last row id the driver's cursor reports in the base class and the current value of the key's sequence on Oracle; and where neither holds, the list is empty (`django/db/models/sql/compiler.py:SQLInsertCompiler.execute_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.last_insert_id`). The rows go through the converters of the returned columns, `SQLCompiler.get_converters` and `SQLCompiler.apply_converters`, and come back as a list.

Who asks for what is the callers' choice. `Model._save_table` starts from `db_returning_fields`, adds every field whose value is an expression, and takes off a field with `db_returning` where the backend cannot return columns, unless the key is set and the field is the auto field; `QuerySet._batched_insert` asks for `db_returning_fields` where the backend can return bulk rows and the conflict mode allows (`django/db/models/base.py:Model._save_table`, `django/db/models/query.py:QuerySet._batched_insert`).

> **Changed in 6.0.** The release notes say that generated fields, and fields assigned expressions, are refreshed from the database after `Model.save` on the backends that support `"RETURNING"`, SQLite, PostgreSQL and Oracle, and are marked deferred on MySQL and MariaDB so that the next access fetches them; and that the operations methods for the clause were renamed to `returning_columns` and `fetch_returned_rows`, since they serve an update's `"RETURNING"` as well as an insert's (`docs/releases/6.0.txt`).

## The update: `UpdateQuery` and its compiler

`UpdateQuery` keeps three things beyond a query's: `UpdateQuery.values`, the triples of a field, its model and the value to set; `UpdateQuery.related_updates`, the values that belong to a parent model's table, by model; and `UpdateQuery.related_ids`, the keys for those, once fetched. `UpdateQuery._setup_query` sets the three empty, and runs both at construction and at the end of `Query.chain`, which calls it on any query class that has it, so that a queryset's query chained into an `UpdateQuery` arrives with its joins and where tree and with these three fresh; `UpdateQuery.clone` copies the related updates (`django/db/models/sql/subqueries.py:UpdateQuery._setup_query`, `django/db/models/sql/query.py:Query.chain`).

`UpdateQuery.add_update_values` is the entry from `QuerySet.update`, with the keyword arguments as a dictionary (`django/db/models/sql/subqueries.py:UpdateQuery.add_update_values`). It finds each name's field through the options and takes the concrete model of the field's model, and refuses two things with `FieldError`: `"pk"` where the key is composite, which must be updated field by field, and a field that is not concrete, a reverse relation or a many-to-many. A field whose concrete model is not the query's is a parent's, and goes to `UpdateQuery.add_related_update`, which gathers the values under the model so that, its docstring says, one update is run for each ancestor. The rest go to `UpdateQuery.add_update_fields`, which skips a generated field, resolves a value that has `resolve_expression` at once, with `allow_joins=False` and `for_save=True`, so that, the comment says, the annotations are no longer needed, and appends the triple (`django/db/models/sql/subqueries.py:UpdateQuery.add_update_fields`). `UpdateQuery.get_related_updates` makes an `UpdateQuery` for each ancestor with its values, filtered to the keys in `related_ids` where those were fetched. `UpdateQuery.update_batch` is the `Collector`'s way in for the instances whose foreign key it has to set, to null, to a default or to a value, before the row they point at goes: the values through `add_update_values`, then the keys in chunks of `GET_ITERATOR_CHUNK_SIZE`, each chunk a fresh where tree of `"pk__in"` and a statement run for `NO_RESULTS` (`django/db/models/sql/subqueries.py:UpdateQuery.update_batch`).

### `as_sql`: the `SET` list

`SQLUpdateCompiler.as_sql` calls `SQLUpdateCompiler.pre_sql_setup` first, and returns an empty statement where the query has no values; the base `execute_sql` takes an empty statement for `EmptyResultSet`, sends nothing and answers `None` (`django/db/models/sql/compiler.py:SQLUpdateCompiler.as_sql`). For each triple the value is made ready. An expression is resolved again with `for_save=True` and refused with `FieldError` where it `contains_aggregate`, where it `contains_over_clause`, and where it is a `ColPairs`, the `F("pk")` of a composite key. A model instance, anything with `prepare_database_save`, is accepted for a relation field alone and gives the key of the related row, `Model.prepare_database_save` refusing an unsaved instance; for any other field it is `TypeError` (`django/db/models/base.py:Model.prepare_database_save`). Then the field's `get_db_prep_save`, and the column's entry in the list: the field's own `get_placeholder_sql` where it has one, a compiled expression, or `"%s"` and the value. The statement is `"UPDATE"`, the base table, `"SET"` and the list; the where tree compiled, with `FullResultSet` meaning no `"WHERE"` at all; and `returning_columns` where `SQLUpdateCompiler.returning_fields` was set. One update of the Petrel, given an expression and a port, with leith the port Leith:

```text recording=sql
Ship.objects.filter(pk=1).update(tonnage=F('tonnage') + 10, home=leith)
  Query.chain  ->  a Query of Ship
  Query.chain(klass=UpdateQuery)  ->  an UpdateQuery of Ship
  UpdateQuery.add_update_values({'tonnage': <CombinedExpression: F(tonnage) + Value(10)>, 'home': <Port: Leith>})
    UpdateQuery.add_update_fields([(Ship.tonnage, <CombinedExpression: F(tonnage) + Value(10)>), (Ship.home, <Port: Leith>)])
  SQLUpdateCompiler.execute_sql('row count')
    SQLCompiler.execute_sql(result_type='row count')
      SQLUpdateCompiler.as_sql
        SQLUpdateCompiler.pre_sql_setup
          Query.count_active_tables  ->  1
        -> ('UPDATE "fleet_ship" SET "tonnage" = ("fleet_ship"."tonnage" + %s), "home_id" = %s WHERE "fleet_ship"."id" = %s', (10, 2, 1))
      SQL UPDATE "fleet_ship" SET "tonnage" = ("fleet_ship"."tonnage" + %s), "home_id" = %s WHERE "fleet_ship"."id" = %s with params (10, 2, 1)
      -> 1
    UpdateQuery.get_related_updates  ->  []
```

The first `Query.chain` is the filter's clone; the second makes the `UpdateQuery`. `add_update_values` handed both pairs to `add_update_fields`, the expression resolved there. The update compiler's `execute_sql` ran the base's, `as_sql` had `pre_sql_setup` count one active table and come straight back, and the statement set the tonnage from its own column, the home from the port's key, under the filter's condition. What `update` accepts and refuses as a value:

```text recording=sql
Sailor.objects.filter(pk=1).update(name=petrel)  ->  raises TypeError: Tried to update field crew.Sailor.name with a model instance, <Ship: Petrel>. Use a value compatible with CharField.
Ship.objects.filter(pk=1).update(tonnage=Count('crew'))  ->  raises FieldError: Joined field references are not permitted in this query
Ship.objects.filter(pk=1).update(tonnage=Window(RowNumber()))  ->  raises FieldError: Window expressions are not allowed in this query (tonnage=<Window: RowNumber() OVER ()>).
Ship.objects.filter(pk=1).update(crew=1)  ->  raises FieldError: Cannot update model field <ManyToOneRel: crew.sailor> (only concrete fields are permitted).
...
Manifest.objects.filter(serial='M-0001').update(kilos=1)  ->  0
Manifest.objects.filter(serial='M-0001').update(crates=41), Manifest.objects.get(serial='M-0001').kilos  ->  (1, 1025)
...
Berth.objects.filter(number=1).update(pk=(1, 9))  ->  raises FieldError: Composite primary key fields must be updated individually.
Ship.objects.filter(pk=1).update(tonnage=F('home__id'))  ->  1
  SQL UPDATE "fleet_ship" SET "tonnage" = "fleet_ship"."home_id" WHERE "fleet_ship"."id" = %s with params (1,)
```

An instance for a `CharField` is the `TypeError` (`django/db/models/fields/__init__.py:CharField`); the count is refused for its join, as it was in the insert; the window by `as_sql`; the reverse relation `"crew"` by `add_update_values`, as a field that is not concrete. An update of the generated column alone leaves no values, so nothing was sent and the answer was zero, and the column follows the crates it is computed from. The composite key as a whole is refused, and `F("home__id")` is allowed with no join: the name reaches the key column the ship's own table holds ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)).

### `pre_sql_setup`: the joins of the filter moved aside

`SQLUpdateCompiler.pre_sql_setup` is where a filter that joined other tables is turned into a condition on the table's own key, the docstring's "format required for (portable) SQL updates", and where, for an update that will be several statements, the keys are fetched first so that, as the docstring says, they do not change as a result of the progressive updates (`django/db/models/sql/compiler.py:SQLUpdateCompiler.pre_sql_setup`). It saves the reference counts, makes sure the base table is in the query, and asks `Query.count_active_tables` how many aliases are referred to. With one, and no related updates, it returns, and the statement is as above.

Otherwise it chains the update query into a plain `Query`, `Query.chain(klass=Query)`, which keeps the joins and the where tree, and strips what a select for keys does not want: `select_related` off, the ordering cleared by force, the extra selects and the selection emptied. The fields it will select are the primary key's name and, for each related update, the ancestor's key where the path to the ancestor is not primary keys all the way, the comment saying that this branch is reached only for an ancestor outside the primary key chain of a multi-table tree; `Query.add_fields` sets them (`django/db/models/sql/query.py:Query.add_fields`). The base `pre_sql_setup` then runs, and the update query's own where tree is cleared, `Query.clear_where`. Two roads follow. Where there are related updates, or more than one table was active and the backend lacks `update_can_self_select`, the plain query is run for `MULTI` and its rows gathered: the keys, and under each ancestor its keys, which become `UpdateQuery.related_ids`; the update query gets a `"pk__in"` filter of the list. Otherwise, the comment's fast path, the plain query itself becomes the value of `"pk__in"`, and the `"in"` lookup resolves it as a subquery, with its aliases moved to a prefix of its own ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). The reference counts are put back last. `BaseDatabaseFeatures.update_can_self_select` is true in the base class, and MySQL's features class answers true for MariaDB alone, the comment giving MySQL as the backend that cannot select from the table it updates (`django/db/backends/base/features.py:BaseDatabaseFeatures.update_can_self_select`, `django/db/backends/mysql/features.py:DatabaseFeatures.update_can_self_select`).

```text figure=two-roads-of-an-update
Sailor.objects.filter(ship__name='Petrel').update(...)        count_active_tables -> 2: the filter joined the ships

SQLUpdateCompiler.pre_sql_setup
    a plain Query chained from the UpdateQuery: the joins and the where tree kept, SELECT the primary key
    the UpdateQuery's own where tree cleared

    related updates, or update_can_self_select off         neither: update_can_self_select on
      the plain query is run first, MULTI                     the plain query becomes the value of pk__in
      SELECT "crew_sailor"."id" FROM "crew_sailor"            UPDATE "crew_sailor" SET ...
        INNER JOIN "fleet_ship" ... WHERE "fleet_ship"."name" = %s     WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0"
      -> [(1,), (2,)]                                                    INNER JOIN "fleet_ship" "U1" ... WHERE "U1"."name" = %s)
      UPDATE "crew_sailor" SET ... WHERE "crew_sailor"."id" IN (%s, %s)
```

*The two roads of `pre_sql_setup` for an update whose filter joins another table. On the left the keys are fetched by a statement of their own and the update names them; on the right the select for the keys goes into the update as a subquery. A related update, or a backend that cannot select from the table it is updating, chooses the left road.*

```text recording=sql
Sailor.objects.filter(ship__name='Petrel').update(name=Upper('name'))
  UpdateQuery.add_update_values({'name': Upper(F(name))})
    UpdateQuery.add_update_fields([(Sailor.name, Upper(F(name)))])
  SQLUpdateCompiler.execute_sql('row count')
    SQLCompiler.execute_sql(result_type='row count')
      SQLUpdateCompiler.as_sql
        SQLUpdateCompiler.pre_sql_setup
          Query.count_active_tables  ->  2
          Query.chain(klass=Query)  ->  a Query of Sailor
          Query.add_fields(field_names=['id'])
          Query.clear_where
          Query.add_filter('pk__in', a Query of Sailor)
            Query.add_fields(field_names=['pk'])
          Query.reset_refcounts({'crew_sailor': 2, 'fleet_ship': 1})
        Query.reset_refcounts({'U0': 5, 'U1': 1})
        -> ('UPDATE "crew_sailor" SET "name" = UPPER("crew_sailor"."name") WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" INNER JOIN "fleet_ship" "U1" ON ("U0"."ship_id" = "U1"."id") WHERE "U1"."name" = %s)', ('Petrel',))
      SQL UPDATE "crew_sailor" SET "name" = UPPER("crew_sailor"."name") WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" INNER JOIN "fleet_ship" "U1" ON ("U0"."ship_id" = "U1"."id") WHERE "U1"."name" = %s) with params ('Petrel',)
```

`count_active_tables` found two, the sailors and the ships. The plain query was chained, given the key to select, and became the value of the `"pk__in"` filter added to the cleared update query, whose `add_fields` of `"pk"` is the `"in"` lookup's doing; the first `reset_refcounts` is `pre_sql_setup`'s, and the second, on the `"U"` aliases, is the subquery's own `as_sql` putting its counts back. The statement updates one table, and the join stands inside the subquery. With the feature switched off, the other road:

```text recording=sql
  SQLUpdateCompiler.pre_sql_setup
    Query.count_active_tables  ->  2
    Query.chain(klass=Query)  ->  a Query of Sailor
    Query.add_fields(field_names=['id'])
    Query.clear_where
    SQLCompiler.execute_sql
      Query.reset_refcounts({'crew_sailor': 4, 'fleet_ship': 1})
      SQL SELECT "crew_sailor"."id" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE "fleet_ship"."name" = %s with params ('Petrel',)
      -> [[(1,), (2,)]]
    Query.add_filter('pk__in', [1, 2])
    Query.reset_refcounts({'crew_sailor': 2, 'fleet_ship': 1})
  -> ('UPDATE "crew_sailor" SET "signed_on" = "crew_sailor"."signed_on" WHERE "crew_sailor"."id" IN (%s, %s)', (1, 2))
SQL UPDATE "crew_sailor" SET "signed_on" = "crew_sailor"."signed_on" WHERE "crew_sailor"."id" IN (%s, %s) with params (1, 2)
```

The plain query was run first and its rows gathered, and the update names the two keys. A child model takes the same road for the sake of its parent's table. An Officer is a Sailor with a rank, kept in a table of its own; its name is the parent's:

```text recording=sql
Officer.objects.filter(rank='master').update(name='Cora C.', rank='master')
  Query.chain  ->  a Query of Officer
  Query.chain(klass=UpdateQuery)  ->  an UpdateQuery of Officer
  UpdateQuery.add_update_values({'name': 'Cora C.', 'rank': 'master'})
    UpdateQuery.add_related_update(model=Sailor, field=Sailor.name, value='Cora C.')
    UpdateQuery.add_update_fields([(Officer.rank, 'master')])
...
        SQLUpdateCompiler.pre_sql_setup
          Query.count_active_tables  ->  1
          Query.chain(klass=Query)  ->  a Query of Officer
          Query.add_fields(field_names=['sailor_ptr'])
          Query.clear_where
          SQLCompiler.execute_sql
            Query.reset_refcounts({'crew_officer': 3, 'crew_sailor': 0})
            SQL SELECT "crew_officer"."sailor_ptr_id" FROM "crew_officer" WHERE "crew_officer"."rank" = %s with params ('master',)
            -> [[(3,)]]
          Query.add_filter('pk__in', [3])
          Query.reset_refcounts({'crew_officer': 1})
        -> ('UPDATE "crew_officer" SET "rank" = %s WHERE "crew_officer"."sailor_ptr_id" IN (%s)', ('master', 3))
...
    UpdateQuery.get_related_updates
      Query.add_filter('pk__in', [3])
      -> [an UpdateQuery of Sailor]
    SQLUpdateCompiler.execute_sql('row count')
      SQLCompiler.execute_sql(result_type='row count')
        SQLUpdateCompiler.as_sql
          SQLUpdateCompiler.pre_sql_setup
            Query.count_active_tables  ->  1
          -> ('UPDATE "crew_sailor" SET "name" = %s WHERE "crew_sailor"."id" IN (%s)', ('Cora C.', 3))
        SQL UPDATE "crew_sailor" SET "name" = %s WHERE "crew_sailor"."id" IN (%s) with params ('Cora C.', 3)
...
Officer.objects.filter(rank='master').update(name='Cora')
  SQL SELECT "crew_officer"."sailor_ptr_id" FROM "crew_officer" WHERE "crew_officer"."rank" = %s with params ('master',)
  SQL UPDATE "crew_sailor" SET "name" = %s WHERE "crew_sailor"."id" IN (%s) with params ('Cora', 3)
```

`add_update_values` sent the name to a related update for Sailor and the rank to the officer's own values. With a related update to run, `pre_sql_setup` fetched the keys first, one statement for the officers' table, and here the link to the parent is the primary key itself, so the one column served both. The officers' statement ran, then `get_related_updates` made the update of the sailors' table, filtered to the key, and the update compiler ran it through a compiler of its own. In the last lines only the parent's field was given: the officer's own query had no values and sent no statement, but its `pre_sql_setup` still fetched the keys, and the parent's statement ran.

### `execute_sql` and `execute_returning_sql`

`SQLUpdateCompiler.execute_sql` runs the main statement through the base `execute_sql` and takes its row count, `None` where nothing was sent, then runs each related update through a compiler of that query's. The docstring says what it returns: the rows affected by the primary update, which is the first non-empty statement that was executed, so that where the main statement was empty and a related one touched rows, that count is the answer (`django/db/models/sql/compiler.py:SQLUpdateCompiler.execute_sql`). `SQLUpdateCompiler.execute_returning_sql` is for `Model.save`, which wants back a generated column that depends on the fields it set, and a field it set to an expression; it raises `NotImplementedError` where there are related updates, falls back to `execute_sql` and a list of empty tuples, one a row, where no fields are to come back or the backend lacks `can_return_rows_from_update`, and otherwise sets `returning_fields`, runs the one statement on a cursor, fetches the rows with `fetch_returned_rows` and applies the converters (`django/db/models/sql/compiler.py:SQLUpdateCompiler.execute_returning_sql`). The base class has the feature false; SQLite, PostgreSQL and Oracle set it true. Here compiler is the compiler of an `UpdateQuery` made by hand over the manifest, filtered to its serial and given forty crates:

```text recording=sql
compiler.execute_returning_sql([Manifest._meta.get_field('kilos')])
  SQLUpdateCompiler.execute_returning_sql([Manifest.kilos])
    UpdateQuery.get_related_updates  ->  []
    SQLUpdateCompiler.as_sql
      SQLUpdateCompiler.pre_sql_setup
        Query.count_active_tables  ->  1
      -> ('UPDATE "office_manifest" SET "crates" = %s WHERE "office_manifest"."serial" = %s RETURNING "office_manifest"."kilos"', (40, 'M-0001'))
    SQL UPDATE "office_manifest" SET "crates" = %s WHERE "office_manifest"."serial" = %s RETURNING "office_manifest"."kilos" with params (40, 'M-0001')
    -> [(1000,)]
connection.features.can_return_rows_from_update  ->  True
```

## The delete: `DeleteQuery` and its compiler

`DeleteQuery` adds two methods to `Query` and nothing to hold. `DeleteQuery.delete_batch` takes a list of keys and runs a statement for each chunk of `GET_ITERATOR_CHUNK_SIZE` of them: for each chunk it clears the where tree, adds an `"in"` filter on the key's attname, and calls `DeleteQuery.do_query`, which narrows the alias map to the one table, sets the where tree, and runs the compiler for `ROW_COUNT`; the counts are summed (`django/db/models/sql/subqueries.py:DeleteQuery.delete_batch`, `django/db/models/sql/subqueries.py:DeleteQuery.do_query`). That is the `Collector`'s way of deleting the instances it holds, model by model, and its short way for a single instance with no dependents. For the rows it never fetched it calls `QuerySet._raw_delete`, which clones the queryset's query, sets the clone's class to `DeleteQuery`, and runs the compiler for `ROW_COUNT` (`django/db/models/query.py:QuerySet._raw_delete`).

`SQLDeleteCompiler.as_sql` has one question to settle: whether the delete can be written against the table alone (`django/db/models/sql/compiler.py:SQLDeleteCompiler.as_sql`). `SQLDeleteCompiler.single_alias` is whether one alias of the query is still referred to, the base table being referred to at least, and `SQLDeleteCompiler.contains_self_reference_subquery` whether any annotation or any child of the where tree holds a query of the model being deleted from, which `SQLDeleteCompiler._expr_refs_base_model` looks for through the source expressions. With a single alias, and either the backend's `delete_can_self_reference_subquery` or no such subquery, `SQLDeleteCompiler._as_sql` writes the query as it is: `"DELETE FROM"` the base table, and the where tree compiled, with no `"WHERE"` where that raises `FullResultSet` (`django/db/models/sql/compiler.py:SQLDeleteCompiler._as_sql`). Otherwise the joins go into a subquery on the key, as in an update: the query is cloned and made a plain `Query`, its selection cleared and set to the key column of the base table; a new `Query` of the model gets it as the value of `"pk__in"`, and `_as_sql` writes that. Where the backend lacks `update_can_self_select`, the inner query is compiled first and wrapped in a `RawSQL` as `SELECT * FROM (...) subquery`, to force, the comment says, its materialization on MySQL. `BaseDatabaseFeatures.delete_can_self_reference_subquery` is true in the base class and false for MySQL (`django/db/backends/base/features.py:BaseDatabaseFeatures.delete_can_self_reference_subquery`). Where the where tree raises `EmptyResultSet`, the base `execute_sql` sends nothing and answers `None`.

```text recording=sql
Port.objects.filter(name__in=['Oban', 'Mull', 'Skagen'])._raw_delete('default')
  SQLCompiler.execute_sql(result_type='row count')
    SQLDeleteCompiler.as_sql
      SQLDeleteCompiler._as_sql(a DeleteQuery of Port)  ->  ('DELETE FROM "fleet_port" WHERE "fleet_port"."name" IN (%s, %s, %s)', ('Oban', 'Mull', 'Skagen'))
      -> ('DELETE FROM "fleet_port" WHERE "fleet_port"."name" IN (%s, %s, %s)', ('Oban', 'Mull', 'Skagen'))
    SQL DELETE FROM "fleet_port" WHERE "fleet_port"."name" IN (%s, %s, %s) with params ('Oban', 'Mull', 'Skagen')
    -> 3
...
Sailor.objects.filter(ship__name='Nobody')._raw_delete('default')
  SQLCompiler.execute_sql(result_type='row count')
    SQLDeleteCompiler.as_sql
      Query.clear_select_clause
      Query.add_filter('pk__in', a Query of Sailor)
        Query.clear_select_clause
      SQLDeleteCompiler._as_sql(a Query of Sailor)  ->  ('DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" INNER JOIN "fleet_ship" "U1" ON ("U0"."ship_id" = "U1"."id") WHERE "U1"."name" = %s)', ('Nobody',))
      -> ('DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" INNER JOIN "fleet_ship" "U1" ON ("U0"."ship_id" = "U1"."id") WHERE "U1"."name" = %s)', ('Nobody',))
    SQL DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" INNER JOIN "fleet_ship" "U1" ON ("U0"."ship_id" = "U1"."id") WHERE "U1"."name" = %s) with params ('Nobody',)
    -> 0
...
Sailor.objects.filter(pk__in=Sailor.objects.filter(name='Nobody'))._raw_delete('default')
  Query.clear_select_clause
  SQLCompiler.execute_sql(result_type='row count')
    SQLDeleteCompiler.as_sql
      SQLDeleteCompiler._as_sql(a DeleteQuery of Sailor)  ->  ('DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" WHERE "U0"."name" = %s)', ('Nobody',))
      -> ('DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" WHERE "U0"."name" = %s)', ('Nobody',))
    SQL DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" WHERE "U0"."name" = %s) with params ('Nobody',)
    -> 0
```

The first delete, on the table itself, was written as it was. The second joined the ships, so the query was cloned, its selection cleared, and put under `"pk__in"` of a new query, which `_as_sql` wrote: the `"in"` lookup's `clear_select_clause` and `add_fields` of the key are the two inner lines, and the join is inside the subquery. The third holds a query of the sailors already, as the value of a filter: SQLite can refer to the table being deleted from in a subquery, so the query was written as it was. With the feature switched off:

```text recording=sql
Sailor.objects.filter(pk__in=Sailor.objects.filter(name='Nobody'))._raw_delete('default')
  Query.clear_select_clause
  SQLCompiler.execute_sql(result_type='row count')
    SQLDeleteCompiler.as_sql
      Query.clear_select_clause
      Query.add_filter('pk__in', a Query of Sailor)
        Query.clear_select_clause
      SQLDeleteCompiler._as_sql(a Query of Sailor)  ->  ('DELETE FROM "crew_sailor" WHERE "crew_sailor"."id" IN (SELECT "V0"."id" FROM "crew_sailor" "V0" WHERE "V0"."id" IN (SELECT "U0"."id" FROM "crew_sailor" "U0" WHERE "U0"."name" = %s))', ('Nobody',))
```

With the feature off, the query's reference to its own table sent it down the second road: the sailors' table appears under a second select, aliased `"V0"`, with the original subquery inside it. The batches of `delete_batch`, with the chunk lowered to five for the block, over keys that no logbook has:

```text recording=sql
DeleteQuery(Logbook).delete_batch(list(range(100, 112)), 'default')
  DeleteQuery.delete_batch(pk_list=[100, 101, and 10 more], using='default')
    Query.clear_where
    Query.add_filter('id__in', [100, 101, 102, 103, 104])
    DeleteQuery.do_query(table='office_logbook', where=a WhereNode of 5 keys, using='default')
      SQLCompiler.execute_sql(result_type='row count')
        SQLDeleteCompiler.as_sql
          SQLDeleteCompiler._as_sql(a DeleteQuery of Logbook)  ->  ('DELETE FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s, %s, %s, %s)', (100, 101, 102, 103, 104))
          -> ('DELETE FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s, %s, %s, %s)', (100, 101, 102, 103, 104))
        SQL DELETE FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s, %s, %s, %s) with params (100, 101, 102, 103, 104)
...
    Query.add_filter('id__in', [110, 111])
    DeleteQuery.do_query(table='office_logbook', where=a WhereNode of 2 keys, using='default')
      SQLCompiler.execute_sql(result_type='row count')
        SQLDeleteCompiler.as_sql
          SQLDeleteCompiler._as_sql(a DeleteQuery of Logbook)  ->  ('DELETE FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s)', (110, 111))
          -> ('DELETE FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s)', (110, 111))
        SQL DELETE FROM "office_logbook" WHERE "office_logbook"."id" IN (%s, %s) with params (110, 111)
```

Twelve keys made three statements, each on a where tree of its own. And the two ends of the where tree:

```text recording=sql
A delete that can match nothing sends nothing, and one that matches everything has no WHERE
    Sailor.objects.filter(pk__in=[])._raw_delete('default')  ->  None
    LogEntry.objects.exclude(pk__in=[])._raw_delete('default')  ->  0
      SQL DELETE FROM "office_logentry"
```

The first delete can match nothing, by its comparison with an empty list, and no statement was sent; the second can match everything, and the statement has no `"WHERE"`.

## The constants the query and the compilers share

The module `django/db/models/sql/constants.py` holds the few constants that the query, the compilers and the queryset share (`django/db/models/sql/constants.py`).

| constant | value | read by |
|---|---|---|
| `GET_ITERATOR_CHUNK_SIZE` | 100 | the chunk of keys in `delete_batch` and `update_batch`, and the number of rows a cursor is asked for at a time in `SQLCompiler.execute_sql` and in the queryset's iterable classes |
| `MULTI` | `"multi"` | `execute_sql`: all the rows, a chunk at a time |
| `SINGLE` | `"single"` | `execute_sql`: one row |
| `NO_RESULTS` | `"no results"` | `execute_sql`: nothing; the result type of `update_batch` |
| `CURSOR` | `"cursor"` | `execute_sql`: the cursor itself, for the caller to read and close |
| `ROW_COUNT` | `"row count"` | `execute_sql`: the rows affected; the result type of `QuerySet.update`, `_raw_delete` and `do_query` |
| `ORDER_DIR` | `"ASC"` and `"DESC"`, each to the pair of itself and its opposite | `get_order_dir` and `SQLCompiler._order_by_pairs`, to read a leading `"-"` against the default direction |
| `INNER` | `"INNER JOIN"` | the type of a `Join`, in `Query.join` and the `JoinPromoter` |
| `LOUTER` | `"LEFT OUTER JOIN"` | the same |

*The module's constants, with what each is for. The five result types are the values `SQLCompiler.execute_sql` is called with, told in [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md).*
