---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Creating, updating and deleting through a queryset

`QuerySet.create`, `QuerySet.get_or_create` and `QuerySet.update_or_create` write through an instance of the model, and `QuerySet.update` and `QuerySet.delete` write to the rows a queryset describes. A save, and the collector of a delete, come back to the queryset to send statements, through the private `QuerySet._insert`, `QuerySet._update` and `QuerySet._raw_delete`. The two methods that write many instances at once are in [`bulk_create` and `bulk_update`](bulk.md).

The five reach a statement by two roads. Where a method writes through an instance, the statement is `Model.save`'s, so a `save` that the model overrides is the one that runs ([Saving an instance](../models/saving.md)). Where it writes to rows, no save is called: `update` makes no instance of any row, and `delete` hands a clone of the queryset to a `Collector`, which works out what the delete reaches, rows of other models among it, and sends the statements (`django/db/models/deletion.py:Collector`) ([Deleting: the `Collector`](../models/deleting.md)).

```text figure=two-roads-to-a-write
Five methods of a queryset that write, and what sends the statement for each.

Through an instance: the model layer decides what to send, and comes back to a queryset to send it.
    QuerySet.create            ->  Model.save(force_insert=True)  ->  QuerySet._insert  ->  an InsertQuery
    QuerySet.get_or_create     ->  QuerySet.get; where that finds no row, QuerySet.create
    QuerySet.update_or_create  ->  QuerySet.get_or_create; where that found a row, Model.save  ->  QuerySet._update  ->  an UpdateQuery

To the rows the query describes: no Model.save is called.
    QuerySet.update            ->  an UpdateQuery, made from a copy of the queryset's query
    QuerySet.delete            ->  a Collector  ->  QuerySet._raw_delete  ->  a DeleteQuery      for rows the collector never fetched
                                               ->  DeleteQuery.delete_batch                     for instances the collector holds, by key
```

*The two roads from a queryset to a statement that writes. On the first the statement is a save's, and the save sends it through a queryset's private methods; on the second a copy of the queryset's query becomes the statement, or a collector makes the statements.*

The examples are the shipping line of the chapter's opening page ([QuerySets](../querysets.md)): a Port has a name and a country; a Ship has a name, a tonnage, a home port and perhaps a captain, and no two ships of one port may share a name; a Sailor has a name and a ship. Like every recording in this chapter, those below were made from a running Django, on SQLite. Under a line of Python are the calls it set going, nested as they were made and only those the passage is about; `->` is what a call, or the line itself, returned, and where one raised, the exception is named in its place; and a line that begins `SQL` is a statement as Django handed it to its cursor.

## `create`: an instance and a forced insert

`QuerySet.create` takes keyword arguments, calls the model class with them, and saves what the class returns (`django/db/models/query.py:QuerySet.create`).

```text recording=querysets
create: an instance is made and saved with force_insert
    oban = Port.objects.create(name='Oban', country='Scotland')
      QuerySet.create(name='Oban', country='Scotland')
        Model.save(force_insert=True, using='default')  (a Port)
          mark_for_rollback_on_error  (a context manager, entered here)
          QuerySet._insert(objs=[<Port: Oban>], fields=[Port.name, Port.country], returning_fields=[Port.id])
            SQL INSERT INTO "fleet_port" ("name", "country") VALUES (%s, %s) RETURNING "fleet_port"."id" with params ('Oban', 'Scotland')
            -> [(5,)]
        -> <Port: Oban>
    oban.pk, oban._state.adding, oban._state.db  ->  (5, False, 'default')
```

Three things in a `create` are the queryset's doing. It sets `QuerySet._for_write` before it reads `QuerySet.db`, so that the alias it gives the save is the one for a write: the alias the queryset was given, or else the router's answer for a write ([Clones: how a queryset is built](chaining.md)). It passes `force_insert=True`, which makes the save insert into the model's own table with no update tried first. For a model of one table, then, a `create` given the key of a row that exists is an insert that the database refuses. And when the save is done it stores the queryset's fetch mode, `QuerySet._fetch_mode`, in the new instance's state, as `ModelState.fetch_mode` (`django/db/models/base.py:ModelState`) ([Deferred fields and fetch modes in a queryset](deferred.md)).

The save ran inside `mark_for_rollback_on_error`, which opens no transaction and, where an exception passes through it inside a block of `atomic`, marks the connection as needing a rollback (`django/db/transaction.py:mark_for_rollback_on_error`) ([Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#mark_for_rollback_on_error)). Under it the statement was sent by `QuerySet._insert`, and the key the database chose came back with it and was set on the instance. The last line shows the key there, with the state a save leaves behind it.

Nothing else of the queryset takes part. Its query is not read, so a condition on the queryset puts no value on the new instance. The manager at the far end of a foreign key does put its own instance among the values, by overriding `create` to add it to the arguments (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager.RelatedManager.create`) ([Reading and setting related objects](../models/related-objects.md)).

Before any of this, `create` refuses one kind of name.

```text recording=querysets
Sailor.objects.create(name='Eve', ship=petrel, command=gannet)  ->  raises ValueError: The following fields do not exist in this model: command
...
sorted(Sailor._meta._reverse_one_to_one_field_names)  ->  ['command', 'officer']
```

`"command"` is no field of Sailor. It is the name of the relation that Ship's one-to-one field `"captain"` makes at Sailor's end, and `"officer"` is the link from the child model Officer. `Options._reverse_one_to_one_field_names` holds such names for a model: it takes the one-to-one relations among `Options.related_objects`, each by the name a query knows it by (`django/db/models/options.py:Options._reverse_one_to_one_field_names`, `django/db/models/fields/reverse_related.py:ForeignObjectRel.name`). `create` raises `ValueError` when a keyword is in the set, and here it sent no statement.

The model class would not have refused. Beside the names of its fields, `Model.__init__` takes a keyword that `Options.get_field` can find, a relation's far end included, and sets it as an attribute (`django/db/models/base.py:Model.__init__`). Assigning at that end of a one-to-one relation sets the key on the other object, and `create` saves the new instance and not that one (`django/db/models/fields/related_descriptors.py:ReverseOneToOneDescriptor.__set__`) ([Reading and setting related objects](../models/related-objects.md)).

## `get_or_create`: a search, and a `create` when it finds nothing

`QuerySet.get_or_create` is for a need that two statements cannot meet safely: fetch the row that matches, or make it if there is none. Between a `"SELECT"` that finds nothing and the `"INSERT"` that follows, another process can insert the same row. The method does not close that gap. It leans on the database: where a unique constraint guards the row, the second insert fails, and the method catches the failure and looks again (`django/db/models/query.py:QuerySet.get_or_create`).

It begins by setting `QuerySet._for_write`, though its first statement is a read. A comment gives the reason: the `QuerySet.get` that follows has to be aimed at the database that will be written to, to avoid problems of transaction consistency. The `get` is given the method's keyword arguments and those only, for `"defaults"` is not a condition ([`get`, `first`, `count` and the other methods that run a query at once](results.md)). A row that is found ends the method, which returns the instance and `False`.

When `get` raises the model's `Model.DoesNotExist`, the method works out the values for a new instance, opens a block of `atomic`, and inside the block calls `QuerySet.create`. The save under the `create` is left out of this quote:

```text recording=querysets
Port.objects.get_or_create(name='Skagen', defaults={'country': lambda: 'Denmark'})
  QuerySet.get_or_create(defaults={'country': the function <lambda>}, name='Skagen')
    QuerySet.get(name='Skagen')
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."name" = %s LIMIT 21 with params ('Skagen',)
      raises DoesNotExist
    QuerySet._extract_model_params(defaults={'country': the function <lambda>}, name='Skagen')  ->  {'name': 'Skagen', 'country': the function <lambda>}
    Atomic.__enter__
      SQL BEGIN
    resolve_callables
    QuerySet.create(name='Skagen', country='Denmark')
      -> <Port: Skagen>
    Atomic.__exit__
      BaseDatabaseWrapper.commit
    -> (<Port: Skagen>, True)
```

`atomic` begins a transaction where none is open, as here, and makes a savepoint inside one that is (`django/db/transaction.py:Atomic.__enter__`) ([Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md#entering-a-block-atomic__enter)). On SQLite the `"BEGIN"` passes through Django's cursor and so is written as a statement, where the commit is written as a call.

### The values for the new instance: `_extract_model_params`

`QuerySet._extract_model_params` turns the arguments of the search into the arguments of the model (`django/db/models/query.py:QuerySet._extract_model_params`). It keeps each keyword argument whose name has no `LOOKUP_SEP`, the double underscore, in it: `name='Skagen'` says what the row's name is, where `name__iexact='skagen'` is a condition and gives no value to store. Then it lays `"defaults"` over what it kept. Each name that results has to be one `Options.get_field` finds, or a property of the model class that has a setter, the names of the class's properties being `Options._property_names` (`django/db/models/options.py:Options._property_names`). The others are gathered into one `FieldError`.

```text recording=querysets
Port.objects.get_or_create(name='Mull', defaults={'county': 'Argyll'})  ->  raises FieldError: Invalid field name(s) for model Port: 'county'.
  SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."name" = %s LIMIT 21 with params ('Mull',)
...
Port.objects.get_or_create(name='Bergen', defaults={'county': 'Hordaland'})  ->  (<Port: Bergen>, False)
  SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."name" = %s LIMIT 21 with params ('Bergen',)
```

`"county"` is no field of Port. The first call raised, after its `get` had found no port called Mull. The second found Bergen and returned it, and the wrong name in its `"defaults"` went unremarked: the method reaches `_extract_model_params` on the way to a `create` and not otherwise.

A value may be a callable. Inside the block, `resolve_callables` replaces each value that can be called by what calling it returns, which is how the lambda given for Skagen's country became `'Denmark'` (`django/db/models/utils.py:resolve_callables`). For a row that is found, `get_or_create` calls none.

### When the insert fails

If the `create` that `QuerySet.get_or_create` calls raises `IntegrityError`, the exception leaves the method's block of `atomic`, and the block undoes what was done inside it: it rolls back the transaction if it began one, and rolls back to its savepoint if it made one (`django/db/utils.py:IntegrityError`, `django/db/transaction.py:Atomic.__exit__`). The method then calls `get` a second time with the same arguments. If that finds a row, one that matches has appeared since the first look, as it does when another transaction inserts it, and the method returns it with `False`. If it finds nothing, the `IntegrityError` is raised again.

> **Why.** Django's documentation states the condition this rests on: the method is atomic on the assumption that the database enforces the uniqueness of the keyword arguments, and where the fields have no such constraint, concurrent calls may insert several rows with the same values (`docs/ref/models/querysets.txt`).

An insert can break a constraint with no race at all, and then the second `get` is no help. There is a Petrel of Bergen, of 480 tons, and no two ships of a port may share a name. This call looks for a Petrel of Bergen of 900 tons:

```text recording=querysets
Ship.objects.get_or_create(name='Petrel', home=bergen, tonnage=900)
...
    Atomic.__exit__  (with IntegrityError)
      BaseDatabaseWrapper.rollback
    QuerySet.get(name='Petrel', home=<Port: Bergen>, tonnage=900)
      SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE ("fleet_ship"."home_id" = %s AND "fleet_ship"."name" = %s AND "fleet_ship"."tonnage" = %s) LIMIT 21 with params (1, 'Petrel', 900)
      raises DoesNotExist
raises IntegrityError: UNIQUE constraint failed: fleet_ship.name, fleet_ship.home_id
```

The lines left out are the method's own, the first `get`, which found no such ship, `_extract_model_params`, and the opening of the block with the `create` inside it. The quote begins where the `IntegrityError` left the block: the transaction was rolled back, the second `get` found nothing either, and the caller was given the database's error.

## `update_or_create`

`QuerySet.update_or_create` is `QuerySet.get_or_create` with one duty more: where the row exists, bring it up to date. It takes the conditions; `"defaults"`, the values to set on a row that is found; and `"create_defaults"`, the values for a row that has to be made, for which `"defaults"` serves where `"create_defaults"` is `None` (`django/db/models/query.py:QuerySet.update_or_create`).

The search and the save run inside one block of `atomic`, and the search is made on a clone from `QuerySet.select_for_update`. A comment says what the lock is for: so that a concurrent update is blocked until `update_or_create` has performed its save. What `select_for_update` leaves on the query is in [Annotations, ordering and the other methods that change the query](methods.md). The statement recorded here has no `"FOR UPDATE"` in it, which is SQLite's doing.

```text recording=querysets
Port.objects.update_or_create(name='Skagen', defaults={'country': 'Danmark'})
  QuerySet.update_or_create(defaults={'country': 'Danmark'}, name='Skagen')
    Atomic.__enter__
      SQL BEGIN
    QuerySet.select_for_update
    QuerySet.get_or_create(defaults={'country': 'Danmark'}, name='Skagen')
      QuerySet.get(name='Skagen')
        SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."name" = %s LIMIT 21 with params ('Skagen',)
        -> <Port: Skagen>
      -> (<Port: Skagen>, False)
    resolve_callables
    Model.save(using='default', update_fields={'country'})  (a Port)
      mark_for_rollback_on_error  (a context manager, entered here)
      QuerySet._update(values=[(Port.country, 'Danmark')], returning_fields=[])
        UpdateQuery.add_update_fields
        SQL UPDATE "fleet_port" SET "country" = %s WHERE "fleet_port"."id" = %s with params ('Danmark', 6)
        -> [()]
    Atomic.__exit__
      BaseDatabaseWrapper.commit
    -> (<Port: Skagen>, False)
```

The search is `get_or_create` itself, given the values for a new row as its `"defaults"`. It found the port and made nothing, and `update_or_create` went on to set the country on the instance, with `setattr`, after `resolve_callables` had called the value if it could be called, and to save the instance with `Model.save`.

Where the search finds nothing, `get_or_create` makes the row, and `update_or_create` returns what it returned with no save of its own. In the next call the two dictionaries differ, and the row is made from `"create_defaults"`. Only `QuerySet._extract_model_params` and the inner block are quoted, without the save under `QuerySet.create`, and the recording writes the number of the thread, which a savepoint's name holds, as `(the thread)`:

```text recording=querysets
Port.objects.update_or_create(name='Tromso', defaults={'country': 'Norge'}, create_defaults={'country': 'Norway'})
...
      QuerySet._extract_model_params(defaults={'country': 'Norway'}, name='Tromso')  ->  {'name': 'Tromso', 'country': 'Norway'}
      Atomic.__enter__
        SQL SAVEPOINT "s(the thread)_x1"
      resolve_callables
      QuerySet.create(name='Tromso', country='Norway')
        -> <Port: Tromso>
      Atomic.__exit__
        BaseDatabaseWrapper.savepoint_commit
          SQL RELEASE SAVEPOINT "s(the thread)_x1"
```

The `atomic` of `get_or_create` found the method's transaction open, made a savepoint in it, and released the savepoint when the insert had succeeded.

### Which fields the save writes

For a row that was found, `QuerySet.update_or_create` chooses between two saves. If every name in `"defaults"` is in `Options._non_pk_concrete_field_names`, it calls `save` with `"update_fields"`. That set has, for each concrete field that is in neither the model's primary key nor a parent's, its name and its **attname**, the name of the attribute that holds the field's value on an instance, which is `"ship_id"` for Sailor's `"ship"`. If some name is anything else, a property with a setter for one, it calls `save` with no `"update_fields"`, and the save writes what a plain save of that instance writes; the comment at that test notes that `"update_fields"` does not support fields that are not concrete (`django/db/models/options.py:Options._non_pk_concrete_field_names`).

In the first case the set of names is widened before the save. A save with `"update_fields"` calls the `pre_save` of the fields it names and of no others, so a field that sets itself at every save, a date with `auto_now=True`, would be left as it was ([Saving an instance](../models/saving.md)). The method therefore adds, by name and by attname, each concrete field of the model's own, outside the key, whose class has a `pre_save` other than the base class's, `Field.pre_save` (`django/db/models/fields/__init__.py:Field.pre_save`). Among Django's own fields those are the dates, the times and the file fields. A comment there gives fields with `auto_now=True` as its example, and backward compatibility as the purpose.

The test is of the field's class, not of what its `pre_save` would do. Sailor's `"signed_on"` is a `DateTimeField` declared with `auto_now_add=True`, and `DateTimeField.pre_save` sets the present moment where the field has `auto_now=True`, or has `auto_now_add=True` and the row is being added, and otherwise returns what the instance holds (`django/db/models/fields/__init__.py:DateTimeField.pre_save`). On an update it changes nothing, and the field is added all the same:

```text recording=querysets
Sailor.objects.update_or_create(name='Ada', defaults={'ship': petrel})
...
    Model.save(using='default', update_fields={'ship', 'signed_on'})  (a Sailor)
...
      QuerySet._update(values=[(Sailor.ship, 1), (Sailor.signed_on, datetime(2011, 6, 1, 8, 0, tzinfo=UTC))], returning_fields=[])
        UpdateQuery.add_update_fields
        SQL UPDATE "crew_sailor" SET "ship_id" = %s, "signed_on" = %s WHERE "crew_sailor"."id" = %s with params (1, '2011-06-01 08:00:00', 1)
        -> [()]
```

`"defaults"` named the ship, and the statement set two columns: naming one field had the other written back, with the value the instance was fetched with.

## `update`: the rows the query matches, and no instance

`QuerySet.update` takes field names and values as keyword arguments, and sets those columns in every row the queryset's query matches, making no instance of any row (`django/db/models/query.py:QuerySet.update`). In the cases recorded here that is at most one statement, and no row is read. Here aboard is a queryset of the Gannet's crew that has been evaluated, so that what becomes of its result cache can be seen:

```text recording=querysets
len(aboard._result_cache)  ->  2
aboard.update(ship=gannet)
  QuerySet.update(ship=<Ship: Gannet>)
    Query.chain(klass=UpdateQuery)
    UpdateQuery.add_update_values
      UpdateQuery.add_update_fields
    mark_for_rollback_on_error  (a context manager, entered here)
    SQL UPDATE "crew_sailor" SET "ship_id" = %s WHERE "crew_sailor"."ship_id" = %s with params (2, 2)
    -> 2
aboard._result_cache  ->  None
```

The statement gave each of the two sailors the ship it already had, and the method returned 2. The number is the cursor's count of rows for the statement, which the documentation describes as the rows matched, whether or not their values changed (`docs/ref/models/querysets.txt`).

The method begins by refusing what it cannot make an update of: a queryset combined by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference`, with `NotSupportedError`; a sliced one, with `TypeError` ([Evaluation and the result cache](evaluation.md)); and one that is distinct on named fields, with `TypeError`. Then it sets `QuerySet._for_write`.

It does not change the queryset's query. `Query.chain`, given a class, clones the query and assigns that class as the clone's class, and `UpdateQuery._setup_query` gives the clone an empty list of values to set (`django/db/models/sql/query.py:Query.chain`, `django/db/models/sql/subqueries.py:UpdateQuery`). The copy still has the queryset's where clause and its joins, which is how an update comes to apply to the rows the queryset would have fetched.

The copy is compiled and run inside `mark_for_rollback_on_error`, and last, the queryset's result cache is set back to `None` ([Evaluation and the result cache](evaluation.md)).

### What can be set

`UpdateQuery.add_update_values` is given the keyword arguments of `QuerySet.update` as a dictionary (`django/db/models/sql/subqueries.py:UpdateQuery.add_update_values`). It looks each name up with `Options.get_field` (`django/db/models/options.py:Options.get_field`), as one name: nothing is followed across a relation. It refuses with `FieldError` a field that is not concrete, a many-to-many field for one, and `"pk"` on a model whose key is of several columns. A value may be an expression, which `UpdateQuery.add_update_fields` resolves against the update's own query with joins not allowed, so it can name columns of the row being updated.

```text recording=querysets
Sailor.objects.filter(ship=gannet).update(name=Lower('name'))  ->  2
  SQL UPDATE "crew_sailor" SET "name" = LOWER("crew_sailor"."name") WHERE "crew_sailor"."ship_id" = %s with params (2,)
Sailor.objects.filter(ship=gannet).update(name=F('name'), ship__name='x')  ->  raises FieldDoesNotExist: Sailor has no field named 'ship__name'
```

`Lower('name')` went into the statement, and the database worked out each sailor's new name from the old one. In the last line `"ship__name"` was looked up whole, and Sailor has no field of that name. The documentation gives the rule behind it: an update sets columns of the model's own table, not of related models (`docs/ref/models/querysets.txt`).

One case reaches a second table. Where the model is a child with a table of its own, a name may be a field of a parent. `add_update_values` keeps such a value apart from the others, with `UpdateQuery.add_related_update` (`django/db/models/sql/subqueries.py:UpdateQuery.add_related_update`), and the update compiler then selects the keys of the rows the queryset matches and sends a statement to the parent's table for those keys ([From QuerySet to SQL](../sql.md)).

### The ordering, and a condition across a join

Whether the queryset's ordering reaches the statement of `QuerySet.update` is the backend's affair. The documentation says that `QuerySet.order_by` before `update` is supported on MariaDB and MySQL and ignored elsewhere, and MySQL's update compiler is the one that writes it (`docs/ref/models/querysets.txt`, `django/db/backends/mysql/compiler.py:SQLUpdateCompiler.as_sql`).

Before the statement is compiled, `update` replaces each name in the ordering that is the name of an annotation by the annotation's expression, refusing with `FieldError` one that contains an aggregate, and then `Query.clear_select_clause` empties what the query would select, its annotations among the rest (`django/db/models/sql/query.py:Query.clear_select_clause`).

An `"UPDATE"` names one table. Where the queryset's conditions need another, the update compiler moves them into a query that selects the keys of the rows, here a subquery of the statement, and the statement updates the rows that have those keys (`django/db/models/sql/compiler.py:SQLUpdateCompiler.pre_sql_setup`) ([From QuerySet to SQL](../sql.md)):

```text recording=querysets
Ship.objects.filter(crew__name='Ada').update(tonnage=480)  ->  1
  SQL UPDATE "fleet_ship" SET "tonnage" = %s WHERE "fleet_ship"."id" IN (SELECT "U0"."id" FROM "fleet_ship" "U0" INNER JOIN "crew_sailor" "U1" ON ("U0"."id" = "U1"."ship_id") WHERE "U1"."name" = %s) with params (480, 'Ada')
```

### What `update` leaves undone

`QuerySet.update` makes no instance, so nothing that happens on an instance happens. `Model.save` is not called, and `pre_save` and `post_save` are not sent; the documentation says both (`docs/ref/models/querysets.txt`). No field's `pre_save` runs either, since nothing on this path calls one, so a date with `auto_now=True` keeps the value it had.

## `_update` and `_insert`: what a save calls

`QuerySet._insert` and `QuerySet._update` are a save's way to a statement. Each carries `"queryset_only"` set to false, which puts it on a manager although its name begins with an underscore ([Managers](../models/managers.md)): a save calls `_insert` on the model's base manager, and `_update` on a queryset from it.

`_update` is `QuerySet.update` for a caller that already holds field objects (`django/db/models/query.py:QuerySet._update`). `Model._do_update` calls it on a queryset filtered to the instance's key, with the fields to write, each with its value, and a list of the fields whose new values the save wants back from the statement, the result of an expression for one (`django/db/models/base.py:Model._do_update`) ([Saving an instance](../models/saving.md)). It makes the `UpdateQuery` as `update` does and hands the fields straight to `UpdateQuery.add_update_fields`, where `update` went through names first; and it drops the result cache as `update` does.

With that list, which a save always gives it, `_update` returns a list with an entry for each row updated: the columns asked back where there are any and the backend's `BaseDatabaseFeatures.can_return_rows_from_update` is true, and an empty tuple otherwise (`django/db/models/sql/compiler.py:SQLUpdateCompiler.execute_returning_sql`). That is the `[()]` under `QuerySet._update` in the recording of `QuerySet.update_or_create`: one row updated, nothing asked back.

`_update` refuses a sliced query and nothing else. It does not set `QuerySet._for_write`, and it has no `mark_for_rollback_on_error` of its own: a save has one around it, or a transaction.

`_insert` makes no use of the queryset's query. It builds a new `InsertQuery` for the model, gives it the fields and the instances with `InsertQuery.insert_values`, and returns what the insert compiler returns: the rows of the columns asked back, or an empty list (`django/db/models/query.py:QuerySet._insert`, `django/db/models/sql/subqueries.py:InsertQuery`) ([From QuerySet to SQL](../sql.md)). It sets `_for_write`, and uses the alias it was given or, given none, `QuerySet.db`. It has two callers. `Model._do_insert` gives it one instance (`django/db/models/base.py:Model._do_insert`), and `QuerySet._batched_insert` gives it a batch of them on behalf of `QuerySet.bulk_create`, which is also what its three arguments about conflicts are for ([`bulk_create` and `bulk_update`](bulk.md)).

## `delete`

`QuerySet.delete` deletes the rows the queryset describes, and with them whatever the relations that point at those rows require. It sends no statement of its own. It prepares a queryset for a `Collector`, calls two of the collector's methods, `Collector.collect` and `Collector.delete`, and returns what the second returns (`django/db/models/query.py:QuerySet.delete`, `django/db/models/deletion.py:Collector`).

The queryset it prepares is a clone, from `QuerySet._chain`. The clone is marked with `QuerySet._for_write`: a comment explains that a delete is two queries, one to find related objects and one to delete, and that the finding has to be done on the database the deleting will use. And the query's `Query.select_for_update` and `Query.select_related` are turned off and its ordering is cleared with `Query.clear_ordering` (`django/db/models/sql/query.py:Query.clear_ordering`).

The `Collector` is made for the clone's database, with the queryset the method was called on as its `Collector.origin`, which is what receivers of the delete signals are told the delete began from. When the collector has done, the method sets its own result cache back to `None`, under a comment that says the queryset may be reused, and returns the collector's pair: the number of rows deleted, and a dictionary of that number by model.

```text recording=querysets
skagen = Port.objects.filter(name__in=['Skagen', 'Tromso']); list(skagen)
  SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."name" IN (%s, %s) ORDER BY "fleet_port"."name" ASC with params ('Skagen', 'Tromso')
skagen.delete()
  QuerySet.delete
    QuerySet._chain  ->  a new QuerySet
    Query.clear_ordering(force=True)
    Collector.collect
      SQL SELECT "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "fleet_port" WHERE "fleet_port"."name" IN (%s, %s) with params ('Skagen', 'Tromso')
      SQL SELECT "fleet_ship"."id" FROM "fleet_ship" WHERE "fleet_ship"."home_id" IN (%s, %s) ORDER BY "fleet_ship"."name" ASC with params (6, 7)
    Collector.delete
      Atomic.__enter__  (an Atomic made with savepoint=False)
        SQL BEGIN
      QuerySet._raw_delete('default')
        SQL DELETE FROM "fleet_voyage_calls" WHERE "fleet_voyage_calls"."port_id" IN (%s, %s) with params (6, 7)
        -> 0
...
      SQL DELETE FROM "fleet_port" WHERE "fleet_port"."id" IN (%s, %s) with params (7, 6)
      Atomic.__exit__
        BaseDatabaseWrapper.commit
      -> (2, {'fleet.Port': 2})
    -> (2, {'fleet.Port': 2})
skagen._result_cache  ->  None
```

The queryset had been evaluated, in its model's ordering by name. The clone had not: the first statement under `Collector.collect` fetched the two ports again, and without an `"ORDER BY"`. The collector takes a queryset as it stands, unfetched, only for a model with no cascades, no parents and no listeners for the delete signals (`django/db/models/deletion.py:Collector.can_fast_delete`); otherwise it needs the instances, to send the signals for and to find by their keys the rows that point at them, as the second statement does for ships whose home is one of the two. Under `Collector.delete` everything is in one transaction: a call of `QuerySet._raw_delete` for each model whose foreign key to a port cascades, of which the quote keeps the first, and then the ports themselves, by key, which the collector does with `DeleteQuery.delete_batch` (`django/db/models/sql/subqueries.py:DeleteQuery.delete_batch`). The block of `atomic` around them was made with `savepoint=False`, so inside a transaction already open it would have made no savepoint (`django/db/transaction.py:Atomic.__enter__`).

All of that is the collector's work, and [Deleting: the `Collector`](../models/deleting.md) tells it, with the delete that a protected relation refuses and the case of a queryset that the collector accepts as it stands, whose rows are never fetched.

### What `delete` refuses

Before it makes the clone, `delete` turns away four kinds of queryset: one combined by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference`, with `NotSupportedError`; a sliced one, with `TypeError` ([Evaluation and the result cache](evaluation.md)); one that is distinct on named fields, with `TypeError`; and one that has been through `QuerySet.values` or `QuerySet.values_list`, which it knows by `QuerySet._fields`, with `TypeError`.

A manager has no `delete` at all: the method carries `"queryset_only"` set to true, which keeps it off managers ([Managers](../models/managers.md)).

```text recording=querysets
Sailor.objects.delete()  ->  raises AttributeError: 'ManagerFromSailorQuerySet' object has no attribute 'delete'
```

A queryset that matches nothing is deleted like any other:

```text recording=querysets
Sailor.objects.select_related('ship').order_by('name').filter(pk=0).delete()  ->  (0, {})
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s with params (0,)
  SQL BEGIN
```

The statement has neither the join that `QuerySet.select_related` would have added nor an ordering. No sailor has the key 0, and the method returned a count of 0 and an empty dictionary; the collector began its transaction all the same.

## `_raw_delete`

`QuerySet._raw_delete` clones the queryset's query, assigns `DeleteQuery` as the clone's class, asks it for a compiler for the alias it was given, and returns the row count (`django/db/models/query.py:QuerySet._raw_delete`, `django/db/models/sql/subqueries.py:DeleteQuery`). Its docstring says what is missing: no signals are sent, and there is no protection for cascades. Whether a set of rows needs neither is for the collector to decide, and `Collector.delete` is the method's one caller in Django: it calls it for each queryset it holds whose rows it did not fetch (`django/db/models/deletion.py:Collector.delete`). The line `QuerySet._raw_delete('default')` in the recording of a delete is such a call, returning 0 for a table that had no row to lose.

## The methods side by side

| method | sets `_for_write` | calls `Model.save` | signals | drops the cache |
|---|---|---|---|---|
| `QuerySet.create` | on the queryset | yes, with `force_insert=True` | those of a save | no |
| `QuerySet.get_or_create` | on the queryset | when it creates | those of a save, when it creates | no |
| `QuerySet.update_or_create` | on the queryset | when it creates, and for a row it found | those of a save; none where the save is given no field to write | no |
| `QuerySet.update` | on the queryset | no | none | yes |
| `QuerySet.delete` | on a clone | no | `pre_delete` and `post_delete`, for the instances the collector holds, except those of an auto-created model, the one a many-to-many field makes for its own table | yes |
| `QuerySet._insert` | on the queryset | no: a save calls it | none of its own | no |
| `QuerySet._update` | no | no: a save calls it | none of its own | yes |
| `QuerySet._raw_delete` | no | no | none | no |

*What these methods of `QuerySet` do about the database to write to, which `QuerySet._for_write` decides, the instance, the signals of a save or a delete, and the queryset's result cache. `QuerySet.bulk_create` and `QuerySet.bulk_update`, which write too, are in [`bulk_create` and `bulk_update`](bulk.md).*

Every method in the table carries `"alters_data"`, which keeps a template from calling it ([Clones: how a queryset is built](chaining.md)). Each of the five public ones has a twin for a coroutine, `QuerySet.acreate` and the rest, which runs the method on a thread ([The asynchronous methods of a queryset](async.md)).
