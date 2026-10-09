---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Inserts: returned keys, conflicts and batch sizes

Writing rows asks more of a database than reading them. A save wants back the key the database made and the columns it filled in itself; a `bulk_create` wants as few statements as the database's limit on parameters allows, and every new row's key; and a row that collides with one already there may be meant to be passed over, or to update it.

The databases answer each of these their own way, and MySQL, unlike MariaDB, has no `"RETURNING"` and hands back only an auto-incremented key. [INSERT, UPDATE and DELETE: the insert, update and delete compilers](../sql/writing.md) has the compiler that asks, and [`bulk_create` and `bulk_update`](../querysets/bulk.md) the method that sorts the instances and cuts them into batches.

## How many rows to a statement: `bulk_batch_size`

`QuerySet._batched_insert` asks `BaseDatabaseOperations.bulk_batch_size`, before it writes any of its batches, how many instances one statement may carry, given the fields and the instances, and takes the smaller of the answer and the caller's batch size, and never less than one (`django/db/models/query.py:QuerySet._batched_insert`). No backend of Django's overrides `bulk_batch_size`. Where the features give no `BaseDatabaseFeatures.max_query_params`, or there are no fields, it answers with the number of instances; otherwise it divides the limit by the number of columns, a `CompositePrimaryKey` counting as its columns, and rounds down, one parameter to each value of each row (`django/db/backends/base/operations.py:BaseDatabaseOperations.bulk_batch_size`).

SQLite's limit is 32766 in this build, asked of the driver's connection at each read ([What a database can do: `BaseDatabaseFeatures`](features.md)), and Oracle's 65535; PostgreSQL's is `None`, or 65535 where parameters are bound on the server under psycopg 3 ([PostgreSQL](postgresql.md)), and MySQL's `None`. Without a limit, and without a batch size from the caller, each of the two groups `bulk_create` sorts its instances into, those with a key and those without, goes in one statement. In the recording below, made from a running Django on SQLite, a line at the left margin is Python as it was run, with `->` before its value; the lines under it are the calls it set going, nested, with `->` before what each returned; and `SQL` begins a statement as Django handed it to its cursor. Five ports, with `batch_size=2`:

```text recording=backends
made = Port.objects.bulk_create([Port(name=f'Skerry {n}', country='Faroe') for n in range(1, 6)], batch_size=2)
  QuerySet.bulk_create([5 of Port], batch_size=2)
    QuerySet._batched_insert([5 of Port], batch_size=2)
      BaseDatabaseOperations.bulk_batch_size(fields=[name, country], objs=[5 of Port])
        DatabaseFeatures.max_query_params  ->  32766
        DatabaseFeatures.max_query_params  ->  32766
        -> 16383
      Atomic.__enter__  (an Atomic made with savepoint=False)
        SQL BEGIN
      QuerySet._insert([2 of Port])
        SQLInsertCompiler.execute_sql
          SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s), (%s, %s) RETURNING "fleet_port"."id" with params ('Skerry 1', 'Faroe', 'Skerry 2', 'Faroe')
...
[port.pk for port in made]  ->  [13, 14, 15, 16, 17]
```

`bulk_batch_size` read the limit twice, to see that there is one and to divide it, and each read asked the driver's connection again: two columns to a row make 16383 rows to a statement, and the caller's two was the smaller. The same method sizes the batches of `QuerySet.bulk_update` ([`bulk_create` and `bulk_update`](../querysets/bulk.md)), of `QuerySet.in_bulk` (`django/db/models/query.py:QuerySet.in_bulk`) and of the collector of a delete (`django/db/models/deletion.py:Collector.get_del_batches`). The five ports made three batches, and `_batched_insert` writes more than one batch inside an atomic block, so that they commit together.

## The statement's words and rows: `insert_statement` and `bulk_insert_sql`

`SQLInsertCompiler.as_sql` asks first for the opening words, `BaseDatabaseOperations.insert_statement`, given the conflict mode: `"INSERT INTO"` in the base class, which SQLite's and MySQL's change only where a conflict is to be ignored (`django/db/models/sql/compiler.py:SQLInsertCompiler.as_sql`). Then, by whether columns are to come back and by the returning features and `BaseDatabaseFeatures.has_bulk_insert`, it writes one statement for all the rows or one for each row; that choice is the compiler's, and [INSERT, UPDATE and DELETE: the insert, update and delete compilers](../sql/writing.md) has it.

Where the rows go in one statement, `BaseDatabaseOperations.bulk_insert_sql` writes them, given the fields and the rows of placeholders: `"VALUES"` and each row in parentheses, in the base class (`django/db/backends/base/operations.py:BaseDatabaseOperations.bulk_insert_sql`). PostgreSQL's `DatabaseOperations.bulk_insert_sql` writes `"SELECT * FROM"` and an array for each column where its own compiler has sent an `InsertUnnest`, and the base class's rows otherwise (`django/db/backends/postgresql/operations.py:DatabaseOperations.bulk_insert_sql`). Oracle's writes each row as a `"SELECT"` of its placeholders (followed by `" FROM DUAL"` before Oracle 23), wrapped where the field's type calls for it in a conversion from `BulkInsertMapper`, and selects from the rows joined by `"UNION ALL"`; its comments say that the union stands in a subquery because Oracle adds a sequence's next value to an insert into a table with an identity column, and a sequence's next value cannot be used with `"UNION"` (`django/db/backends/oracle/operations.py:DatabaseOperations.bulk_insert_sql`) ([Oracle](oracle.md)).

Here two ports are compiled by each backend's own compiler through insert_sql, a helper of the recording's own, with the fields to return set as `QuerySet._batched_insert` sets them, where the backend can return the rows of a bulk insert. PostgreSQL 17, MySQL 8.4 and Oracle 23 were assumed, with the drivers and no server, and nothing was sent:

```text recording=backends
ports = [Port(name='Hull', country='England'), Port(name='Whitby', country='England')]
insert_sql(sqlite, ports)  ->  [('INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s), (%s, %s) RETURNING "fleet_port"."id"', ('Hull', 'England', 'Whitby', 'England'))]
insert_sql(postgresql, ports)  ->  [('INSERT INTO "fleet_port" ("name", "country") SELECT * FROM UNNEST((%s)::varchar[], (%s)::varchar[]) RETURNING "fleet_port"."id"', (['Hull', 'Whitby'], ['England', 'England']))]
insert_sql(mysql, ports)  ->  [('INSERT INTO `fleet_port` (`name`, `country`) VALUES (%s, %s), (%s, %s)', ('Hull', 'England', 'Whitby', 'England'))]
insert_sql(oracle, ports)  ->  [('INSERT INTO "FLEET_PORT" ("NAME", "COUNTRY") SELECT * FROM (SELECT %s col_0, %s col_1 UNION ALL SELECT %s, %s)', ('Hull', 'England', 'Whitby', 'England'))]
```

SQLite's is the base class's rows with `"RETURNING"` after them. PostgreSQL's carries four values in two parameters, each a list of one column's values. MySQL's asks for nothing back, and the instances get no keys. Oracle's is its union, and asks for nothing back either: its features let it return the columns of one row, not the rows of a bulk insert. Two voyages due to sail, compiled for Oracle 19 with no server by two more of the recording's helpers, show both the conversions and `" FROM DUAL"`:

```text recording=backends
full(inserts_for(oracle19, due, ['ship', 'sailed']))  ->  [('INSERT INTO "FLEET_VOYAGE" ("SHIP_ID", "SAILED") SELECT * FROM (SELECT TO_NUMBER(%s) col_0, TO_DATE(%s) col_1 FROM DUAL UNION ALL SELECT TO_NUMBER(%s), TO_DATE(%s) FROM DUAL)', (1, datetime.date(2026, 5, 1), 2, datetime.date(2026, 5, 9)))]
```

## Conflicts: `insert_statement` and `on_conflict_suffix_sql`

Three features say what a backend can do with a new row that collides with an old one: `BaseDatabaseFeatures.supports_ignore_conflicts`, pass over the new row; `BaseDatabaseFeatures.supports_update_conflicts`, update the old row from the new; and `BaseDatabaseFeatures.supports_update_conflicts_with_target`, name in that update the columns whose collision sets it off, the conflict's target (`django/db/backends/base/features.py:BaseDatabaseFeatures`). The base class has the first true and the others false. `QuerySet._check_bulk_create_options` reads them before anything is written, refuses what the backend cannot do, and answers with the mode, `OnConflict.IGNORE` or `OnConflict.UPDATE` ([`bulk_create` and `bulk_update`](../querysets/bulk.md)). The compiler gives the mode to `insert_statement` and to `BaseDatabaseOperations.on_conflict_suffix_sql`, the second with the columns to update and the target's; the base class's suffix is empty (`django/db/backends/base/operations.py:BaseDatabaseOperations.on_conflict_suffix_sql`).

| | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| a conflict passed over | `"INSERT OR IGNORE INTO"`, the first words | `"ON CONFLICT DO NOTHING"`, after the rows | `"INSERT IGNORE INTO"`, the first words | refused |
| a conflict updated | `"ON CONFLICT"` and the target, `"DO UPDATE SET"` each column from `"EXCLUDED"` | the same | `"ON DUPLICATE KEY UPDATE"`, no target | refused |

*The SQL of a conflict on each backend (`django/db/backends/sqlite3/operations.py:DatabaseOperations.insert_statement`, `django/db/backends/sqlite3/operations.py:DatabaseOperations.on_conflict_suffix_sql`, `django/db/backends/postgresql/operations.py:DatabaseOperations.on_conflict_suffix_sql`, `django/db/backends/mysql/operations.py:DatabaseOperations.insert_statement`). Oracle's features class has neither conflict feature, and `bulk_create` refuses both before the compiler is reached.*

On SQLite, over the ships, whose name and home port are unique together:

```text recording=backends
Ship.objects.bulk_create([Ship(name='Petrel', tonnage=480, home_id=1), Ship(name='Fulmar', tonnage=650, home_id=1)], ignore_conflicts=True)
  DatabaseOperations.insert_statement(on_conflict=OnConflict.IGNORE)  ->  'INSERT OR IGNORE INTO'
  DatabaseOperations.on_conflict_suffix_sql(on_conflict=OnConflict.IGNORE)  ->  ''
  SQL INSERT OR IGNORE INTO "fleet_ship" ("name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s), (%s, %s, %s, %s) with params ('Petrel', 480, 1, None, 'Fulmar', 650, 1, None)
Ship.objects.bulk_create([Ship(name='Petrel', tonnage=480, home_id=1)], update_conflicts=True, unique_fields=['name', 'home'], update_fields=['tonnage'])
  DatabaseOperations.insert_statement(on_conflict=OnConflict.UPDATE)  ->  'INSERT INTO'
  DatabaseOperations.on_conflict_suffix_sql(on_conflict=OnConflict.UPDATE)  ->  'ON CONFLICT("name", "home_id") DO UPDATE SET "tonnage" = EXCLUDED."tonnage"'
  SQL INSERT INTO "fleet_ship" ("name", "tonnage", "home_id", "captain_id") VALUES (%s, %s, %s, %s) ON CONFLICT("name", "home_id") DO UPDATE SET "tonnage" = EXCLUDED."tonnage" RETURNING "fleet_ship"."id" with params ('Petrel', 480, 1, None)
list(Ship.objects.order_by('pk').values_list('name', 'tonnage'))  ->  [('Petrel', 480), ('Gannet', 1200), ('Fulmar', 650)]
  SQL SELECT "fleet_ship"."name" AS "name", "fleet_ship"."tonnage" AS "tonnage" FROM "fleet_ship" ORDER BY "fleet_ship"."id" ASC
```

The first statement passed over the Petrel, a ship of 480 tons with home port 1 already in the table, and added the Fulmar. It asked for nothing back, since `QuerySet._batched_insert` asks for the returning fields only where conflicts are not being ignored (`django/db/models/query.py:QuerySet._batched_insert`). The second, which wrote the Petrel's own tonnage back, named its target and asked for the key, as an insert with no conflict does.

MySQL's `DatabaseOperations.on_conflict_suffix_sql` gives the new row an alias on MySQL, the comment saying that MySQL does not support `"VALUES()"` there, and uses `"VALUE()"` on MariaDB (`django/db/backends/mysql/operations.py:DatabaseOperations.on_conflict_suffix_sql`). The Petrel's update, pair[:1] being the Petrel alone of the two ships above, compiled for MySQL 8.4 and for MariaDB 11.4 with no server; only MariaDB's asks for the key back:

```text recording=backends
full(inserts_for(mysql, pair[:1], ['name', 'tonnage', 'home', 'captain'], on_conflict=OnConflict.UPDATE, update_fields=['tonnage'], unique_fields=['name', 'home']))  ->  [('INSERT INTO `fleet_ship` (`name`, `tonnage`, `home_id`, `captain_id`) VALUES (%s, %s, %s, %s) AS new ON DUPLICATE KEY UPDATE `tonnage` = new.`tonnage`', ('Petrel', 480, 1, None))]
full(inserts_for(mariadb, pair[:1], ['name', 'tonnage', 'home', 'captain'], on_conflict=OnConflict.UPDATE, update_fields=['tonnage'], unique_fields=['name', 'home']))  ->  [('INSERT INTO `fleet_ship` (`name`, `tonnage`, `home_id`, `captain_id`) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE `tonnage` = VALUE(`tonnage`) RETURNING `fleet_ship`.`id`', ('Petrel', 480, 1, None))]
```

> **Trap.** On MySQL and MariaDB `"INSERT IGNORE"` passes over more than a duplicate key: the documentation of `bulk_create` warns that it turns certain other errors into warnings, invalid values and violations of a column's not-null among them, even in strict mode (`docs/ref/models/querysets.txt`).

## What comes back: `returning_columns`, `fetch_returned_rows` and `last_insert_id`

On SQLite, PostgreSQL and MariaDB a save, and a `bulk_create` that does not ignore conflicts, can bring back the keys and the columns the database filled. On MySQL and Oracle a `bulk_create` brings back nothing. A save on MySQL gets its key from `BaseDatabaseOperations.last_insert_id` where the key is an `AutoField`; a save on Oracle brings its columns back unless the alias's `"OPTIONS"` turn `"use_returning_into"` off. `Model._save_table` and `QuerySet._batched_insert` choose what to ask for by the returning features ([Saving an instance](../models/saving.md)). Once the statements have run, `SQLInsertCompiler.execute_sql` has `BaseDatabaseOperations.fetch_returned_rows` read the rows from the cursor where the backend can return them, by `BaseDatabaseFeatures.can_return_rows_from_bulk_insert` for several rows and `BaseDatabaseFeatures.can_return_columns_from_insert` for one; otherwise, where the first field to return is an `AutoField`, it makes one row of what `last_insert_id` returns, and where it is not, returns nothing (`django/db/models/sql/compiler.py:SQLInsertCompiler.execute_sql`). What comes back goes through the returned columns' converters ([The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)).

`BaseDatabaseOperations.returning_columns` writes `"RETURNING"` and each column qualified by its table, with no parameters, and `fetch_returned_rows` asks the cursor for all its rows (`django/db/backends/base/operations.py:BaseDatabaseOperations.returning_columns`). Oracle's `DatabaseOperations.returning_columns` adds `"INTO"` and a variable for each column, for the database to fill, and its `DatabaseOperations.fetch_returned_rows` reads them back (`django/db/backends/oracle/operations.py:DatabaseOperations.returning_columns`) ([Oracle](oracle.md)).

The base class's `last_insert_id` is the driver's cursor's last row id, which every backend but Oracle's keeps (`django/db/backends/base/operations.py:BaseDatabaseOperations.last_insert_id`); Oracle's asks the database for the sequence behind the key's column and then for its current value (`django/db/backends/oracle/operations.py:DatabaseOperations.last_insert_id`). Here SQLite's feature was switched off on the connection for one save, so that SQLite took MySQL's road:

```text recording=backends
connection.features.can_return_columns_from_insert = False
stromness = Port.objects.create(name='Stromness', country='Scotland')
  SQLInsertCompiler.execute_sql
    SQLInsertCompiler.as_sql
    SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) with params ['Stromness', 'Scotland']
    BaseDatabaseOperations.last_insert_id(cursor, table_name='fleet_port', pk_name='id')
      CursorWrapper.__getattr__('lastrowid')
      -> 18
    CursorWrapper.__getattr__('close')
stromness.pk  ->  18
del connection.features.can_return_columns_from_insert
connection.features.can_return_columns_from_insert  ->  True
```

The statement has no `"RETURNING"`, and the last row id was read through Django's cursor, which hands an attribute it does not have to the driver's ([Cursors: executing a statement, the query log and execute wrappers](cursors.md)). Where a key comes back this way and other fields were asked for too, they cannot come with it: `Model._assign_returned_values` sets the key and takes the others out of the instance's dictionary, which its comment calls stale, so that each is fetched when next read (`django/db/models/base.py:Model._assign_returned_values`).

`BaseDatabaseOperations.returning_columns` and `BaseDatabaseOperations.fetch_returned_rows` serve an update's `"RETURNING"` too, which `SQLUpdateCompiler.as_sql` writes and `SQLUpdateCompiler.execute_returning_sql` reads back for `Model.save` where the backend has `BaseDatabaseFeatures.can_return_rows_from_update`: SQLite and PostgreSQL do, Oracle does unless `"use_returning_into"` is off, and MySQL's features class, for MariaDB too, does not (`django/db/models/sql/compiler.py:SQLUpdateCompiler.as_sql`, `django/db/models/sql/compiler.py:SQLUpdateCompiler.execute_returning_sql`) ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](../sql/writing.md)).

## A value's placeholder: `binary_placeholder_sql` and `modify_insert_params`

`SQLInsertCompiler.field_as_sql` writes each value's placeholder: a field with a placeholder method writes its own, an expression is compiled, and anything else is `"%s"` with the value as its parameter (`django/db/models/sql/compiler.py:SQLInsertCompiler.field_as_sql`). `BinaryField.get_placeholder_sql` asks `BaseDatabaseOperations.binary_placeholder_sql`, given the value and the compiler, which compiles an expression and writes `"%s"` for anything else; MySQL's writes `"_binary %s"`, its syntax for binary content, for a value that is neither `None` nor an expression (`django/db/backends/base/operations.py:BaseDatabaseOperations.binary_placeholder_sql`, `django/db/backends/mysql/operations.py:DatabaseOperations.binary_placeholder_sql`). The update compiler asks a field for its placeholder the same way.

`BaseDatabaseOperations.modify_insert_params` is given each placeholder and its parameters last, and returns the parameters as they are; only Oracle's spatial backend overrides it (`django/db/backends/base/operations.py:BaseDatabaseOperations.modify_insert_params`, `django/contrib/gis/db/backends/oracle/operations.py:OracleOperations.modify_insert_params`) ([Content types, static files and the other contrib apps](../contrib.md)).

## A key the database makes: `pk_default_value` and `autoinc_sql`

`BaseDatabaseOperations.pk_default_value` is the value of an insert with no field to write, which the compiler's comment says can only be a model whose primary key is a single auto field: the statement names the key's column, and each instance's row holds this value, `"DEFAULT"` in the base class and so on PostgreSQL, `"NULL"` on SQLite, MySQL and Oracle (`django/db/backends/base/operations.py:BaseDatabaseOperations.pk_default_value`). `BaseDatabaseOperations.autoinc_sql` is a hook for a backend that needs statements after a table is made to give an auto field its values; no backend of Django's overrides it, their auto fields' column types being identity columns on PostgreSQL and Oracle, `"AUTO_INCREMENT"` on MySQL and `"AUTOINCREMENT"` on SQLite (`django/db/backends/base/operations.py:BaseDatabaseOperations.autoinc_sql`) ([Column types: from a field to a column](column-types.md)).

## The backends' own compilers

A query names its compiler's class, and the operations object takes it by that name from the module `BaseDatabaseOperations.compiler_module` names, `django.db.models.sql.compiler` in the base class ([The SQL a backend writes: `BaseDatabaseOperations`](operations.md)). PostgreSQL's and MySQL's name modules of their own, and each module imports the base's compilers that it does not change and lists them beside its own, so that every name a query may ask for is there (`django/db/backends/postgresql/compiler.py`, `django/db/backends/mysql/compiler.py`).

### PostgreSQL: `InsertUnnest` and the insert compiler

PostgreSQL's `SQLInsertCompiler` overrides `assemble_as_sql` alone, to send the rows of a bulk insert as arrays through `"UNNEST"`, one parameter to a column, which the comment says reduces the time spent planning the query (`django/db/backends/postgresql/compiler.py:SQLInsertCompiler.assemble_as_sql`). In place of the rows of placeholders it returns an `InsertUnnest`, a list of one placeholder for each column, each cast to an array of the column's type, which writes itself as `"UNNEST"` of them; and in place of the rows of parameters a single row, of a list of values for each column (`django/db/backends/postgresql/compiler.py:InsertUnnest`). The type is the field's `db_type` cut at its first parenthesis, so that, the comment says, no value is truncated: an array of `"varchar"`, not of `"varchar(60)"`. `BaseDatabaseOperations.bulk_batch_size` knows nothing of this, and counts a parameter for each value all the same.

The comments name the cases that keep the base class's rows: a single row, which needs as many placeholders either way; a field of `None`, the mark of a row inserted with the key's default alone; a field with a placeholder method, whose placeholder may depend on the value where an array needs one for all; a field whose internal type, or its target's for a relation, has no entry in the connection's `data_types`, arrays and geometries being known trouble; and any value that is an expression, which cannot stand in an array of literal values.

### MySQL: the delete and update compilers

MySQL's `SQLDeleteCompiler.as_sql` writes a delete over joined tables in MySQL's own syntax, which its comment prefers to the base class's subquery on the key since MySQL and MariaDB plan it better (`django/db/backends/mysql/compiler.py:SQLDeleteCompiler.as_sql`). It hands the delete to the base class where the query has one alias, or where the condition compares an aggregate or a window function, which the syntax cannot carry, the comment says, having no `"GROUP BY"`, no `"HAVING"` and no room for the subquery that stands in for `"QUALIFY"`.

MySQL's `SQLUpdateCompiler.as_sql` adds `"ORDER BY"` to the base class's statement where the queryset was given an ordering with `order_by` (`django/db/backends/mysql/compiler.py:SQLUpdateCompiler.as_sql`). The documentation gives the use, updating a unique field in an order that avoids a conflict on the way, and says the ordering is ignored on other databases (`docs/ref/models/querysets.txt`). Where a column of the ordering belongs to a joined table, or compiling it raises `FieldError`, the ordering is dropped and the statement sent without it. A delete of the Petrel's crew across a join, and an update of every ship heaviest first, compiled for MySQL 8.4 with no server:

```text recording=backends
delete_sql(petrels_crew, mysql)  ->  ('DELETE `crew_sailor` FROM `crew_sailor` INNER JOIN `fleet_ship` ON (`crew_sailor`.`ship_id` = `fleet_ship`.`id`) WHERE `fleet_ship`.`name` = %s', ('Petrel',))
...
update_sql(heaviest_first, mysql, tonnage=models.F('tonnage') + 1)  ->  ('UPDATE `fleet_ship` SET `tonnage` = (`fleet_ship`.`tonnage` + %s) ORDER BY `fleet_ship`.`tonnage` DESC', (1,))
```
