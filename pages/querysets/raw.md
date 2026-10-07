---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Raw querysets

`QuerySet.raw` takes a statement the program wrote and returns a `RawQuerySet`, which sends the statement when it is iterated, matches the columns that come back to the model's fields by name, and makes an instance of each row. The statement and its parameters are kept by a `RawQuery`, and the rows are turned into instances by `RawModelIterable`.

Now and then a program has a statement that the methods of a queryset will not say, and still wants what a queryset gives: instances of a model, ready to be saved or handed to a template. `raw` is for that, and what it returns is a **raw queryset**, an instance of `RawQuerySet`. Its difficulty is that Django does not read the statement. A `Query` knows which columns it selects because it chose them. Of a statement handed over as text Django knows nothing until the database has run it and the cursor can say what came back.

What is particular to a raw queryset follows from that. It cannot be refined, counted or limited in the database, since there is no description of the statement to change. It learns its columns from the cursor. And what a row becomes is settled by comparing names: a column named as a field's column is that field's value, a field whose column did not come back is left deferred, and a column that matches no field becomes a plain attribute.

The examples are the shipping line of the chapter's opening page, [QuerySets](../querysets.md), where the table of sailors has the columns `"id"`, `"name"`, `"ship_id"` and `"signed_on"`.

## What `raw` returns

`QuerySet.raw` makes a `RawQuerySet` from the statement, the parameters, a dictionary of translations if one is given, and four things of the queryset it was called on: the model, an alias for a database, the fetch mode its instances are to be given ([Deferred fields and fetch modes in a queryset](deferred.md)), and the prefetch lookups ([`prefetch_related`: related objects in a second query](prefetch.md)) (`django/db/models/query.py:QuerySet.raw`). The alias is the one given as `using=...`, and failing that the queryset's own `QuerySet.db` as it is at that moment ([Clones: how a queryset is built](chaining.md)). The queryset's query is not among the four, so a condition already on the queryset, a manager's own filter included, has no part in the statement that is sent. Veteran is a proxy of Sailor whose manager filters every queryset it hands out:

```python
# harbour/crew/models.py
class VeteranManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(signed_on__year__lt=2020)


class Veteran(Sailor):
    objects = VeteranManager()

    class Meta:
        proxy = True
```

What follows was recorded from a running Django, on SQLite: a line at the left is Python that was run, with its value or the exception it raised after `->` where it is an expression; under it are the calls it set going, nested as they were made, with only the calls the passage is about written down and what a call returned after `->`; and a line that begins `SQL` is a statement as Django handed it to its cursor.

```text recording=querysets
len(Veteran.objects.raw('SELECT * FROM crew_sailor')), len(Sailor.objects.filter(name='Ada').raw('SELECT * FROM crew_sailor'))  ->  (4, 4)
  SQL SELECT * FROM crew_sailor
  SQL SELECT * FROM crew_sailor
```

Each raw queryset returned all four sailors: the manager's filter in the first and the queryset's in the second went unused.

On a manager, `raw` is one of the methods a manager class is given from `QuerySet`: it calls `raw` on the queryset that the manager's `BaseManager.get_queryset` returns ([Managers](../models/managers.md)).

`RawQuerySet` is not a subclass of `QuerySet`. `RawQuerySet.__init__` keeps the statement and the parameters, the model, the alias as `RawQuerySet._db`, a dictionary of hints for the router, the translations and the fetch mode, and it starts with no result cache ([Evaluation and the result cache](evaluation.md)) (`django/db/models/query.py:RawQuerySet.__init__`). In `RawQuerySet.query` it keeps a `RawQuery`, which it makes from the statement, the parameters and its `RawQuerySet.db` unless it was passed one. A `RawQuery` is what a raw queryset has where a queryset has a `Query`: it holds the text, runs it, and holds the cursor afterwards (`django/db/models/sql/query.py:RawQuery`).

```text recording=querysets
hands = Sailor.objects.raw('SELECT id, name, upper(name) AS shout FROM crew_sailor WHERE ship_id = %s ORDER BY id', [1])
  QuerySet.raw('SELECT id, name, upper(name) AS shout FROM crew_sailor WHERE ship_id = %s ORDER BY id', params=[1])  ->  a RawQuerySet of Sailor, no result cache
type(hands).__name__, isinstance(hands, QuerySet), hands._result_cache, repr(hands)  ->  ('RawQuerySet', False, None, '<RawQuerySet: SELECT id, name, upper(name) AS shout FROM crew_sailor WHERE ship_id = 1 ORDER BY id>')
```

No statement was sent, for the call or for `repr`. `RawQuerySet.__repr__` prints the `RawQuery`, whose text is the statement with the parameters put into it by Python's `%`: text for reading, and not what will be sent (`django/db/models/sql/query.py:RawQuery.__str__`).

## When a raw queryset is iterated

Making a raw queryset sends nothing and examines nothing: the statement is not parsed. `RawQuerySet.__iter__` calls `RawQuerySet._fetch_all`, which has the two steps of a queryset's ([Evaluation and the result cache](evaluation.md)). Where there is no result cache it makes the list of everything that `RawQuerySet.iterator` yields, and keeps it; then it follows any prefetch lookups that have not been followed. `iterator` is a generator over a `RawModelIterable` made for the raw queryset (`django/db/models/query.py:RawQuerySet._fetch_all`, `django/db/models/query.py:RawQuerySet.iterator`).

```text recording=querysets
for sailor in hands: seen(sailor)
  RawQuerySet.__iter__
    RawQuerySet._fetch_all
      RawQuerySet.iterator
        RawModelIterable.__iter__
          RawQuery.__iter__
            RawQuery._execute_query
              SQL SELECT id, name, upper(name) AS shout FROM crew_sailor WHERE ship_id = %s ORDER BY id with params (1,)
          RawQuerySet.resolve_model_init_order
            RawQuery.get_columns  ->  ['id', 'name', 'shout']
            -> (['id', 'name'], [0, 1], [('shout', 2)])
          Model.from_db('default', ['id', 'name'], [1, 'Ada'], fetch_mode=FETCH_ONE)  (Sailor)
          Model.from_db('default', ['id', 'name'], [2, 'Bram'], fetch_mode=FETCH_ONE)  (Sailor)
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
```

The statement went to the cursor as the program wrote it, with its placeholder and the parameter beside it. The three lists that `RawQuerySet.resolve_model_init_order` returned are the fields of Sailor that the statement gave a column for, the place of each in a row, and the one column that is no field's, with its place. Both rows were made into instances before the loop's body ran once, and the list of them is now the result cache.

A statement that is wrong is not found out where `QuerySet.raw` is called:

```text recording=querysets
Sailor.objects.raw('SELEKT nothing')  ->  <RawQuerySet: SELEKT nothing>
list(Sailor.objects.raw('SELEKT nothing'))  ->  raises OperationalError
  SQL SELEKT nothing
```

The error is raised when the list is asked for, and it is the database's: on SQLite an `OperationalError`, for text that cannot be parsed.

## `RawQuery`: the statement and its cursor

A `RawQuery` holds the text, the parameters and one cursor, that of its latest execution, and keeps no rows. `RawQuery._execute_query` is the execution: it adapts the parameters, takes an ordinary cursor from the connection, keeps it as `RawQuery.cursor`, and has it execute the statement (`django/db/models/sql/query.py:RawQuery._execute_query`). Two methods call it. `RawQuery.__iter__` executes anew each time it is called, and returns an iterator over the cursor. `RawQuery.get_columns` executes only where there is no cursor yet, and returns the names of the columns of the result, from the cursor's description (`django/db/models/sql/query.py:RawQuery.__iter__`, `django/db/models/sql/query.py:RawQuery.get_columns`).

```text recording=querysets
names = Sailor.objects.raw('SELECT id, name FROM crew_sailor WHERE name = %s', ['Ada'])
names.columns  ->  ['id', 'name']
  SQL SELECT id, name FROM crew_sailor WHERE name = %s with params ('Ada',)
len(names), repr(names)  ->  (1, '<RawQuerySet: SELECT id, name FROM crew_sailor WHERE name = Ada>')
  SQL SELECT id, name FROM crew_sailor WHERE name = %s with params ('Ada',)
```

Asked for its columns before anything else, the raw queryset had the statement run for the names alone, and `len` then had it run again for the rows. The `repr` in the last answer is the text with a parameter that is a string put into it, which stands there with no quotes round it.

The parameters may be a sequence, a mapping, for placeholders written with names, or `None`, which is passed on as it is. Each parameter of a sequence or a mapping is first adapted by the backend's `BaseDatabaseOperations.adapt_unknown_value`, which goes by the Python type of the value alone: a datetime, a date, a time or a `decimal.Decimal` is given to the method of the backend's operations that adapts a value of a field of that kind, and anything else is left as it is (`django/db/backends/base/operations.py:BaseDatabaseOperations.adapt_unknown_value`). How the placeholders and the parameters reach the driver is in [Database backends](../backends.md).

## Which column is whose

`RawQuerySet.columns` is the list that `RawQuery.get_columns` returns, with the translations applied. The dictionary given to `QuerySet.raw` as `translations=...` goes from the name of a column in the result to the name it is to be taken as, and a key that names no column of the result is passed over. `columns` is a cached property: read on a raw queryset whose `RawQuery` has not yet run the statement, it has the statement run to learn the names, as the recording above shows (`django/db/models/query.py:RawQuerySet.columns`).

`RawQuerySet.model_fields` is a dictionary from column names to fields: each field of the model that has a column, in the model's order, under the name of that column as the backend's `BaseDatabaseIntrospection.identifier_converter` gives it (`django/db/models/query.py:RawQuerySet.model_fields`). `RawQuery.get_columns` passes each name through the same function, which puts a name into lower case on Oracle and changes nothing in the base class. The match is by column and not by the field's name: the foreign key ship is found under `"ship_id"`, and a translation that is to make a column that field's has to say `"ship_id"` too.

`RawQuerySet.resolve_model_init_order` puts the two together and returns the three lists: the attnames of the fields whose columns the statement returned, in the model's order, the place of each of those in a row, and the columns that match no field, each with its place (`django/db/models/query.py:RawQuerySet.resolve_model_init_order`). A field's **attname** is the name of the attribute that holds its value on an instance.

```text figure=columns-to-fields
Sailor.objects.raw('SELECT id, name, upper(name) AS shout FROM crew_sailor WHERE ship_id = %s ORDER BY id', [1])

RawQuerySet.columns: what the statement returned, in its order
    id          name        shout

RawQuerySet.model_fields: Sailor's fields that have a column, in the model's order
    id          name        ship_id     signed_on

id, name        returned, and a field's column: their values are given to Model.from_db, in the model's order
ship_id         a field's column, not returned: the field is left deferred
signed_on       a field's column, not returned: the field is left deferred
shout           returned, and no field's column: set on the instance afterwards as the attribute "shout"

RawQuerySet.resolve_model_init_order  ->  (['id', 'name'], [0, 1], [('shout', 2)])
```

*How the columns of the recorded statement are shared out between the model's fields. The three lists at the foot are the attnames given to `Model.from_db`, the place of each in a row, and the columns left over with theirs.*

Asked afterwards, the raw queryset of the loop and its first instance say the same:

```text recording=querysets
hands.columns, sorted(hands.model_fields), hands[0].shout, sorted(hands[0].get_deferred_fields())  ->  (['id', 'name', 'shout'], ['id', 'name', 'ship_id', 'signed_on'], 'ADA', ['ship_id', 'signed_on'])
```

Because the match is by name alone, a translation can make a column a field's, and nothing ties the statement to the model's table:

```text recording=querysets
[sailor.name for sailor in Sailor.objects.raw('SELECT id, name AS label FROM crew_sailor ORDER BY id LIMIT 2', translations={'label': 'name'})]  ->  ['Ada', 'Bram']
  SQL SELECT id, name AS label FROM crew_sailor ORDER BY id LIMIT 2
...
[type(ship).__name__ for ship in Sailor.objects.raw('SELECT * FROM fleet_ship')]  ->  ['Sailor', 'Sailor']
  SQL SELECT * FROM fleet_ship
```

The second question made Sailors of the rows of the table of ships. That table has an `"id"` and a `"name"`, which were taken for a sailor's.

## From a row to an instance: `RawModelIterable`

`RawModelIterable.__iter__` is the generator that runs the statement and makes an instance of each row; the lines nested under it in the recording of the loop are its doing (`django/db/models/query.py:RawModelIterable.__iter__`).

It begins by making a compiler, the backend's `SQLCompiler`, round the `RawQuery`. Nothing is compiled: the compiler is wanted for the conversion of the driver's values into Python's after a statement has run, and a comment in the constructor of `RawQuery` says that it mirrors a few attributes of a normal query so that a compiler can be used on its results. Then the iterable asks the `RawQuery` for an iterator, which sends the statement.

`RawQuerySet.resolve_model_init_order` is called, and the first use of its answer is a test: every field of the model's primary key has to be among the fields the statement returned, the documentation's reason being that Django identifies an instance by its primary key (`docs/topics/db/sql.txt`). Where one is missing the iterable raises `FieldDoesNotExist`. The statement has been sent by then:

```text recording=querysets
list(Sailor.objects.raw('SELECT name FROM crew_sailor'))  ->  raises FieldDoesNotExist: Raw query must include the primary key
  SQL SELECT name FROM crew_sailor
```

The values of a column that matches a field are passed through the converters of the backend and of that field, the functions that turn a value as the driver returned it into the one Python is to have, as a queryset's are; a value in a column that matches none is left as the driver returned it (`django/db/models/sql/compiler.py:SQLCompiler.get_converters`, `django/db/models/sql/compiler.py:SQLCompiler.apply_converters`).

From each row the iterable picks the values at the places that `resolve_model_init_order` gave, and calls `Model.from_db` with the alias, the list of attnames and those values, the raw queryset's fetch mode being bound to the call by `_get_from_db` ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)). Given fewer names than the model has concrete fields, `from_db` leaves the other fields deferred ([An instance and its state](../models/instances.md)). Where the fetch mode tracks peers, the instances that one iteration makes, the instance is added to the list of them and given the list ([Deferred fields and fetch modes in a queryset](deferred.md)). Each column left over is set on the instance with `setattr`, under the column's name. When the iteration ends, however it ends, the iterable closes the cursor of the `RawQuery`.

## A composite primary key

A `CompositePrimaryKey` has no column of its own, so a raw queryset has to find the key of such a model in the columns of the fields the key is made of. A Berth, in the shipping line's office, is known by its port and its number there:

```python
# harbour/office/models.py
class Berth(models.Model):
    pk = models.CompositePrimaryKey("port_id", "number")
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    metres = models.PositiveSmallIntegerField()
```

`RawQuerySet.model_fields` leaves out a field without a column, so no column of a result is ever matched to `"pk"`. The test for the primary key is made on `Options.pk_fields`, which for such a key are the fields it is made of: both `"port_id"` and `"number"` have to come back (`django/db/models/options.py:Options.pk_fields`).

```text recording=querysets
[(berth.port_id, berth.number, berth.pk) for berth in Berth.objects.raw('SELECT * FROM office_berth ORDER BY number')]  ->  [(1, 1, (1, 1)), (1, 2, (1, 2))]
  SQL SELECT * FROM office_berth ORDER BY number
list(Berth.objects.raw('SELECT port_id, metres FROM office_berth'))  ->  raises FieldDoesNotExist: Raw query must include the primary key
  SQL SELECT port_id, metres FROM office_berth
```

The key of each Berth in the first answer was not read from a row. It is worked out from the two attributes each time `"pk"` is read, by the descriptor of the key ([The field classes](../models/field-types.md)).

## What else a raw queryset answers

`RawQuerySet.__len__` and `RawQuerySet.__bool__` call `RawQuerySet._fetch_all` and answer from the list, and `RawQuerySet.__getitem__` makes a list of the whole raw queryset and indexes that. So an index or a slice evaluates everything, is never made a limit in the statement, and may be negative, which a `QuerySet` refuses (`django/db/models/query.py:RawQuerySet.__len__`, `django/db/models/query.py:RawQuerySet.__getitem__`).

`RawQuerySet.iterator`, called by a program, runs the statement and yields each instance without keeping it, and does not follow prefetch lookups (`django/db/models/query.py:RawQuerySet.iterator`). `RawQuerySet.__aiter__` hands `_fetch_all` to a thread and then yields from the list (`django/db/models/query.py:RawQuerySet.__aiter__`) ([The asynchronous methods of a queryset](async.md)).

In these lines names is the raw queryset whose columns were asked for above: it selects the `"id"` and the `"name"` of Ada, and has been evaluated.

```text recording=querysets
names[-1].name, names[0].signed_on.year  ->  ('Ada', 2011)
  SQL SELECT "crew_sailor"."id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
len(list(names.iterator())), len(names._result_cache)  ->  (1, 1)
  SQL SELECT id, name FROM crew_sailor WHERE name = %s with params ('Ada',)
unkept = Sailor.objects.raw('SELECT id, name FROM crew_sailor')
len(list(unkept.iterator())), unkept._result_cache  ->  (4, None)
  SQL SELECT id, name FROM crew_sailor
```

A negative index was answered from the list. Reading `"signed_on"`, a column the statement did not return, sent one statement for that field of that instance. `iterator` on names ran the raw statement again, and the result cache still held its one instance; on a raw queryset that had not been evaluated it ran the statement and left no result cache.

The methods of a `QuerySet` that refine or count are not there:

```text recording=querysets
Sailor.objects.raw('SELECT * FROM crew_sailor').filter(name='Ada')  ->  raises AttributeError
```

## Prefetch lookups, copies and the database

`RawQuerySet.prefetch_related` adds prefetch lookups to a copy of the raw queryset, and given `None` alone it empties the list, as a queryset's does (`django/db/models/query.py:RawQuerySet.prefetch_related`). `RawQuerySet._fetch_all` follows them after the list is made, by the same `prefetch_related_objects` ([`prefetch_related`: related objects in a second query](prefetch.md)).

```text recording=querysets
[len(s.crew.all()) for s in Ship.objects.raw('SELECT * FROM fleet_ship ORDER BY id').prefetch_related('crew')]  ->  [2, 2]
  SQL SELECT * FROM fleet_ship ORDER BY id
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (%s, %s) with params (1, 2)
```

The other way round is refused: a `Prefetch` raises `ValueError` when it is given a raw queryset as its queryset (`django/db/models/query.py:Prefetch.__init__`).

A raw queryset is made by `QuerySet.raw`, by `RawQuerySet._clone` and by `RawQuerySet.using`, and the three do not carry the same things over.

| what it has | made by `QuerySet.raw` | made by `_clone`, which `prefetch_related` calls | made by `using` |
|---|---|---|---|
| the `RawQuery` | a new one | the same object | a new one for the alias, from `RawQuery.chain` |
| the alias | the one given, or the queryset's `QuerySet.db` | the same | the one given |
| the hints | none | the same | none |
| the fetch mode | the queryset's | `FETCH_ONE`, whatever the original has | the same |
| the prefetch lookups | the queryset's | the original's | none |

*What a new `RawQuerySet` is given by each of the three (`django/db/models/query.py:RawQuerySet._clone`, `django/db/models/query.py:RawQuerySet.using`).*

```text recording=querysets
mode(Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor'), Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor').prefetch_related('ship'), Sailor.objects.fetch_mode(models.FETCH_PEERS).raw('SELECT * FROM crew_sailor').using('default'))  ->  (FETCH_PEERS, FETCH_ONE, FETCH_PEERS)
Sailor.objects.raw('SELECT * FROM crew_sailor').prefetch_related('ship').using('default')._prefetch_related_lookups  ->  ()
```

In the first line `mode(...)` stands for the fetch mode of each of three raw querysets, by its name: one that `raw` made from a queryset with `FETCH_PEERS`, and one each that `prefetch_related` and `using` made of such a raw queryset. `_clone` does not pass the fetch mode on, so any call of `prefetch_related` on a raw queryset returns one whose fetch mode is `FETCH_ONE`, and that is the mode its instances are given. `using` does not copy the prefetch lookups, so called after `prefetch_related` it drops them, as the second line shows. Neither copy has the result cache of its original.

`RawQuerySet.db` returns the alias the raw queryset was made with, and with none it asks the router's `ConnectionRouter.db_for_read` with the model and the hints (`django/db/models/query.py:RawQuerySet.db`). The class has no mark for writing, so by itself it does not ask `ConnectionRouter.db_for_write`. A raw queryset from `QuerySet.raw` has an alias in every case, the one that method passed.
