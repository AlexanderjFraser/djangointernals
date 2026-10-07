---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
part: The ORM
contents: chaining, filters, lookups, methods, combining, evaluation, iterables, values, deferred, prefetch, results, writing, bulk, raw, async
---

# QuerySets

A `QuerySet` is a query that has been described and not yet run, and afterwards the rows it brought back. A method that refines it ordinarily returns a clone; the first time it is iterated, or asked its length or its truth, it sends its statement and keeps what comes back in a result cache; and an iterable class decides what each row becomes: a model instance, a dictionary, a tuple or a single value.

A program rarely asks the database for rows in one step. It starts from a model's manager, narrows what it wants, orders it, perhaps hands the result to another function that narrows it further, and at last passes it to a template that loops over it. If each of those steps sent a statement, most of the statements would fetch rows that the next step throws away. The steps do not touch the database. Each one adds to a description of the statement that will be wanted, and the statement is sent at the moment something asks for the rows themselves.

The object that makes this work is the **queryset**, an instance of `QuerySet` (`django/db/models/query.py:QuerySet`). It holds little. There is the model it is for. There is a `Query`, the description of the statement, which is the subject of [From QuerySet to SQL](sql.md); this chapter calls it **the query**, and says only what the queryset's methods ask of it (`django/db/models/sql/query.py:Query`). There are a few settings for the run: which database, what to make of each row, which related objects to fetch afterwards. And there is the **result cache**, `QuerySet._result_cache`, which is `None` in a new queryset and, once its rows have been fetched to be kept, the list of what was made of them; a call of `QuerySet.update` or `QuerySet.delete` on the queryset sets it back to `None`.

```text recording=querysets
What a new queryset holds: vars(Ship.objects.all()), an attribute to a line
    model: Ship
    _db: None
    _hints: {}
    _query: a Query of Ship
    _result_cache: None
    _sticky_filter: False
    _for_write: False
    _prefetch_related_lookups: ()
    _prefetch_done: False
    _known_related_objects: {}
    _iterable_class: ModelIterable
    _fetch_mode: FETCH_ONE
    _fields: None
    _defer_next_filter: False
    _deferred_filter: None
    _cloning_enabled: True
```

That list was recorded from a running Django, like every recording in this chapter. The attributes that the paragraph above did not name are marks for particular machinery, and [Clones: how a queryset is built](querysets/chaining.md) says what each is for.

The project is the shipping line of [Models and fields](models.md): ports, ships and their voyages in one application, the sailors in a second, and the office's paperwork in a third. Here are the models of the first two, which the queries below lean on. Left out are the docstrings, the constraints and the index of a ship, the choices of an officer's rank, and Veteran, a proxy of Sailor with a manager of its own, which [Raw querysets](querysets/raw.md) lists. A model of the office is shown where a section turns on it.

```python
# harbour/fleet/models.py
class Named(models.Model):
    name = models.CharField(max_length=60)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Port(Named):
    country = models.CharField(max_length=40)


class Ship(Named):
    tonnage = models.PositiveIntegerField()
    home = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ships")
    captain = models.OneToOneField("crew.Sailor", null=True, blank=True, on_delete=models.SET_NULL, related_name="command")


class Voyage(models.Model):
    ship = models.ForeignKey(Ship, on_delete=models.CASCADE)
    sailed = models.DateField()
    calls = models.ManyToManyField(Port)


# harbour/crew/models.py
class SailorQuerySet(models.QuerySet):
    def aboard(self, ship):
        return self.filter(ship=ship)


class Sailor(models.Model):
    name = models.CharField(max_length=60)
    ship = models.ForeignKey("fleet.Ship", on_delete=models.CASCADE, related_name="crew")
    signed_on = models.DateTimeField(auto_now_add=True)
    pilots_into = models.ManyToManyField("fleet.Port", through="office.Licence", related_name="pilots")

    objects = SailorQuerySet.as_manager()

    def __str__(self):
        return self.name


class Officer(Sailor):
    rank = models.CharField(max_length=10, choices=Rank)
```

A port and a ship are ordered by name unless a queryset says otherwise, and a sailor has no ordering. Sailor's manager is made from a queryset class of the project's, so a queryset of sailors is a SailorQuerySet where one of ships is a plain `QuerySet`. The recordings were made in one run, which began with these few rows:

```text recording=querysets
The rows the recording begins with
    Port: 1 Bergen (Norway), 2 Leith (Scotland), 3 Lisbon (Portugal)
    Ship: 1 Petrel (480 tons, home Bergen, captain none), 2 Gannet (1200 tons, home Leith, captain Cora)
    Sailor: 1 Ada (ship Petrel, signed on 2011), 2 Bram (ship Petrel, signed on 2026), 3 Cora (ship Gannet, signed on 2011), 4 Dag (ship Gannet, signed on 2026)
    Officer: 3 Cora (master)
    Voyage: 1 (ship Petrel, sailed 2026-03-02, calls at Leith and Lisbon), 2 (ship Gannet, sailed 2025-10-06, calls at Bergen)
    Licence: 1 (Ada into Bergen)
    Berth: Bergen 1 (90 m), Bergen 2 (140 m)
    Logbook: 25, from 1 Log 1 to 25 Log 25
```

The recordings ran on SQLite. In a recording, a line at the left is a line of Python as it was run; where it is an expression, its value follows `->`, or the word "raises" and the exception. The lines set in under it are the calls it set going, nested as they were made, with only the calls the passage is about written down, and `->` there is what a call returned. A line that begins `SQL` is a statement as Django handed it to its cursor, with Django's `%s` for a parameter, and what such a line shows of SQL's dialect is that backend's. A line of three dots stands for lines left out.

## Building: methods that return a clone

A queryset is first made by a manager. A manager has nearly every public method of `QuerySet` under the same name: each was put on a manager class as a small method that asks the manager for a new queryset and calls the queryset's method of that name ([Managers](models/managers.md)). So a call of `filter` on Sailor's manager makes a queryset and filters it. From there on a method that refines a queryset ordinarily leaves the one it was called on as it was, and returns another; the few exceptions are in [Clones: how a queryset is built](querysets/chaining.md).

```text recording=querysets
named = Sailor.objects.filter(ship=petrel).order_by('name')
  manager_method  (the method a base of the manager's class was given under the name 'filter')
    BaseManager.get_queryset  ->  a SailorQuerySet of Sailor, no result cache
    QuerySet.filter(ship=<Ship: Petrel>)
      QuerySet._filter_or_exclude(negate=False, args=(), kwargs={'ship': <Ship: Petrel>})
        QuerySet._chain
          QuerySet._clone
            Query.chain
              Query.clone
          -> a new SailorQuerySet
        QuerySet._filter_or_exclude_inplace(negate=False, args=(), kwargs={'ship': <Ship: Petrel>})
          Query.add_q(q_object=<Q: (AND: ('ship', <Ship: Petrel>))>)
  QuerySet.order_by('name')
    QuerySet._chain
      QuerySet._clone
        Query.chain
          Query.clone
      -> a new SailorQuerySet
    Query.clear_ordering(force=True, clear_default=False)
    Query.add_ordering('name')
named._result_cache, named.ordered, named.db  ->  (None, True, 'default')
```

The copy is made by `QuerySet._clone`, which `QuerySet._chain` calls for such a method before the method changes anything: a new queryset of the same class, with a copy of the query made by `Query.chain`. The method then makes its change to the copy, most often to the copy's query, and returns it (`django/db/models/query.py:QuerySet._chain`, `django/db/models/query.py:QuerySet._clone`). So `QuerySet.filter` here did its work on the second queryset of the recording and `QuerySet.order_by` on the third, and the first two were dropped as the line finished. A queryset that a program keeps can be refined into several others, and none of them changes its query.

Nothing was sent to the database, and nothing was fetched: the last line shows the third queryset with no result cache, though it can already say that it is ordered and which database it would use. What a method does to the query, the conditions and joins behind `Query.add_q` and the ordering behind `Query.add_ordering`, belongs to [From QuerySet to SQL](sql.md). The queryset's own part is in [Clones: how a queryset is built](querysets/chaining.md): everything a queryset holds, what a clone shares with its original, the few places where Django changes a queryset in place, and how a queryset comes to know which database it will use.

## What a method leaves on the query

`QuerySet.filter` and `QuerySet.exclude` take conditions as keyword arguments and as `Q` objects, and reduce both to one thing: a `Q`, a small tree whose leaves are pairs of a name and a value, or expressions that are true or false, and whose nodes join them with `"AND"`, `"OR"` or `"XOR"` and may be negated. `exclude` negates the tree it builds. The queryset gives the tree to `Query.add_q`, as the recording above shows, and only there do the names in it meet the model ([`filter`, `exclude` and `Q` objects](querysets/filters.md)). The words of a name that follow its fields, `"year"` and `"lt"` in `"signed_on__year__lt"`, are each looked up in a registry that a field or a transform carries, and a project can add to one ([The lookup registry: `RegisterLookupMixin`](querysets/lookups.md)).

Most of the other methods that return a queryset leave something else on the clone's query: annotations, an ordering, a distinct clause, a lock, or the mark that makes it empty ([Annotations, ordering and the other methods that change the query](querysets/methods.md)). Two querysets can be joined into one: with the operators `&`, `|` and `^`, which make one query of the conditions of two querysets of one model, or with `QuerySet.union`, `QuerySet.intersection` and `QuerySet.difference`, which keep the queries side by side for the compiler to join as one compound statement ([Combining querysets: the operators and `union`](querysets/combining.md)).

## Evaluating: every row is fetched at once

A queryset is **evaluated** when its statement is sent and the result cache filled. Iterating it does that, and so do `len` and `bool` of it and pickling it. Each of these calls `QuerySet._fetch_all`, which does not run the statement again when there is a result cache already (`django/db/models/query.py:QuerySet._fetch_all`). Here a queryset of the Petrel's sailors in order of name, built as the one in the last recording was, is iterated, asked its length and iterated again:

```text recording=querysets
for sailor in named: seen(sailor)
  QuerySet.__iter__
    QuerySet._fetch_all  (there is no result cache)
      ModelIterable.__iter__
        Query.get_compiler(using='default')
        SQLCompiler.execute_sql
          SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "crew_sailor"."name" ASC with params (1,)
          the cursor's fetchmany(100)  ->  2 rows
          the cursor's fetchmany(100)  ->  0 rows
        SQLCompiler.results_iter
        Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [1, 'Ada', 1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
        Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [2, 'Bram', 1, datetime(2026, 4, 10, 9, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
len(named)
  QuerySet.__len__
    QuerySet._fetch_all  (the result cache is filled)
    -> 2
...
for hand in named: seen(hand)
  QuerySet.__iter__
    QuerySet._fetch_all  (the result cache is filled)
  the loop's body runs with <Sailor: Ada>
  the loop's body runs with <Sailor: Bram>
```

The first loop sent the statement. Both rows were read from the cursor, which is asked for a hundred at a time until it has none left, and both instances were made before the loop's body ran once; the list of them was kept. `len` and the second loop went through `_fetch_all` again, which found the cache filled, and no statement was sent. The lines left out ask the same queryset for its `bool`, for an index into it and for its `QuerySet.count`, `QuerySet.exists` and `QuerySet.contains`: with a result cache there, each was answered from the list.

`_fetch_all` fills the cache with the list of whatever the queryset's **iterable class** yields. That class is `ModelIterable` for a new queryset. Its `__iter__` is where one query is run from end to end: it asks the query for a **compiler** for the queryset's database, the object that writes the statement and runs it, has the compiler execute the statement, and turns each row the compiler gives back into an instance by calling `Model.from_db` (`django/db/models/query.py:ModelIterable.__iter__`). On the way the compiler applies **converters** to the columns that have them: functions, the backend's or a field's, that turn a value as the database's driver returned it into the one the program is to have (`django/db/models/sql/compiler.py:SQLCompiler.results_iter`). How the statement is written is [From QuerySet to SQL](sql.md), the connection and its cursor are [Database backends](backends.md), and what `from_db` does with a row is in [An instance and its state](models/instances.md). Where the queryset has **prefetch lookups** not yet followed, which say what related objects to fetch afterwards, `_fetch_all` has them followed once the list is made.

```text figure=one-evaluation
QuerySet._fetch_all, where there is no result cache yet

1  an iterable is made for the queryset
       QuerySet._iterable_class: ModelIterable for a new queryset; values() and values_list() set another
2  the iterable asks the query for a compiler, and the compiler runs the statement
       SQLCompiler.execute_sql: every row is read from the cursor before it returns
3  the compiler hands the rows on, one at a time
       SQLCompiler.results_iter: converters are applied to the values that have them
4  the iterable makes something of each row
       ModelIterable: an instance, by Model.from_db    ValuesIterable: a dictionary    the others: a tuple or one value
5  the list of what it made is kept
       QuerySet._result_cache
6  where the queryset has prefetch lookups not yet followed, they are followed, for all the instances at once
       prefetch_related_objects: further statements, where there is anything to fetch

Steps 2, 3 and 4 happen inside the iterable. Within them, running the statement and handing on the rows are the compiler's and the backend's work.
A later iteration, len, bool, index, count, exists or contains reads QuerySet._result_cache.
```

*One evaluation of a queryset. The statement and the cursor are the compiler's and the backend's; what a row becomes is decided by the queryset's iterable class; and what is kept is the finished list.*

A queryset that has not been evaluated does not always evaluate itself to answer. An index, a slice with a step, `count`, `exists` and `contains` are each answered by a statement of their own, where one is needed at all, and leave the queryset without a result cache; a plain slice sends nothing and returns another queryset with a limit on its query. `QuerySet.iterator` reads the rows without keeping them, a chunk at a time where the backend can and the connection's settings allow it. [Evaluation and the result cache](querysets/evaluation.md) has all of this, with slices, pickling and `repr`.

## What a row becomes

The iterable class is where the kinds of queryset differ. After `QuerySet.values` or `QuerySet.values_list` the clone has another class in `QuerySet._iterable_class` and a query that selects the columns named, or every concrete field of the model where none was, so the same machinery ends in dictionaries, tuples, named tuples or single values with no instance made ([`values` and `values_list`: rows as dictionaries and tuples](querysets/values.md)).

`ModelIterable` does more than call `Model.from_db`. Where `QuerySet.select_related` has made the query join a related table, a row holds the columns of two models or more, and an instance of the joined model is made from its share of them, where the row has one, and kept on the instance it was reached from, so that reading the relation later sends nothing. An annotation the query selects is set on the instance as an attribute. And in a queryset that came from the manager at the far end of a foreign key, as the crew of a ship does, each sailor made is given that very ship as its ship, where it has none already and was fetched with the key ([From rows to instances: `ModelIterable` and `select_related`](querysets/iterables.md)).

A queryset can also leave columns out. `QuerySet.defer` names fields to leave out of the statement and `QuerySet.only` names the fields to load, and an instance is then made without the others. An instance carries a **fetch mode**, new in 6.1, which the queryset passes to the instances it makes, and which is asked when such a value, or a related object that is not at hand, has to be fetched: `FETCH_ONE` fetches for that instance alone, `FETCH_PEERS` for the instances made with it that are still alive, and `FETCH_RAISE` raises instead of fetching ([Deferred fields and fetch modes in a queryset](querysets/deferred.md)).

## Related objects in a second statement

`QuerySet.select_related` widens the queryset's own statement with joins, for a foreign key or a one-to-one relation. `QuerySet.prefetch_related` does the other thing: it records prefetch lookups on the queryset, and when the queryset is evaluated, `QuerySet._fetch_all` has them followed after the result cache is filled, here with one more statement for all the instances together.

```text recording=querysets
ships = list(Ship.objects.prefetch_related('crew'))
  QuerySet.prefetch_related('crew')
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
    QuerySet._prefetch_related_objects
      prefetch_related_objects(model_instances=[<Ship: Gannet>, <Ship: Petrel>], 'crew')
...
                SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (%s, %s) with params (2, 1)
```

The second statement asks for the sailors of both ships at once. They are then sorted by ship in Python, and each ship's list is left where its related manager will look before it sends anything. `prefetch_related_objects`, which runs this, knows nothing about relations: it finds a descriptor or a manager under a name, and that object supplies the queryset and says how its results are matched to the instances ([`prefetch_related`: related objects in a second query](querysets/prefetch.md)).

## Methods that answer at once

`QuerySet.get`, `QuerySet.first`, `QuerySet.last`, `QuerySet.earliest`, `QuerySet.latest`, `QuerySet.count`, `QuerySet.exists`, `QuerySet.contains`, `QuerySet.aggregate`, `QuerySet.in_bulk` and `QuerySet.explain` do not return a queryset: each answers when it is called, with a statement shaped to its answer where it needs one. `count` asks the database to count, `exists` asks for one row of a constant, and a plain `get` filters, drops the ordering, limits the clone to twenty-one rows and evaluates it, twenty-one being enough to tell one row from several and to say how many when they are few. Where the queryset already has a result cache, `count`, `exists` and `contains` read it instead ([`get`, `first`, `count` and the other methods that run a query at once](querysets/results.md)).

## Writing

A queryset writes as well as reads. `QuerySet.create` makes an instance and saves it, and two methods are built on it: `QuerySet.get_or_create` calls `QuerySet.get` and, when that finds nothing, `create` inside an atomic block; `QuerySet.update_or_create` does that on a clone that asks for the row to be locked, and saves the instance if it was found, all inside one atomic block. `QuerySet.update` turns a copy of the queryset's query into an `"UPDATE"` over the rows it would have selected, without making an instance of any of them, and `QuerySet.delete` hands a clone of the queryset to the `Collector` of [Deleting: the `Collector`](models/deleting.md) ([Creating, updating and deleting through a queryset](querysets/writing.md)). `QuerySet.bulk_create` and `QuerySet.bulk_update` write many instances in few statements, in batches no larger than the size the caller gives or the backend's limit allows, and without a call of `Model.save` ([`bulk_create` and `bulk_update`](querysets/bulk.md)).

The methods that write set `QuerySet._for_write`, on the queryset or on the clone they make, and a queryset with no alias of its own then has its database chosen by the router's `ConnectionRouter.db_for_write` and not by `ConnectionRouter.db_for_read` (`django/db/models/query.py:QuerySet.db`); [Clones: how a queryset is built](querysets/chaining.md) lists the methods.

## Raw statements

`QuerySet.raw` takes a statement the program wrote and returns a `RawQuerySet`, which is not a `QuerySet` and has few of its methods: it runs the statement when it is iterated, matches the columns that come back to the model's fields by name, and makes an instance of each row ([Raw querysets](querysets/raw.md)).

## From a coroutine

Each public method of `QuerySet` that sends a statement when it is called has a **twin** whose name begins with an a, `QuerySet.aget`, `QuerySet.acount`, `QuerySet.abulk_create`, which is a coroutine function. The twin does no asynchronous work with the database: it hands the synchronous method to a thread through `sync_to_async` and waits (`django/db/models/query.py:QuerySet.aget`, `asgiref:asgiref/sync.py:SyncToAsync.__call__`). An `async for` over a queryset does the same with `QuerySet._fetch_all`. `QuerySet.aiterator`, the asynchronous form of `QuerySet.iterator`, is not a twin but an asynchronous generator ([The asynchronous methods of a queryset](querysets/async.md)).

## The neighbours

A queryset stands between the model layer and the SQL layer and owns little of either. It is handed out by a manager, and the related managers of [Reading and setting related objects](models/related-objects.md) and [Many-to-many relations](models/many-to-many.md) are managers whose querysets start with a filter. The statement is described by its `Query`, and everything that turns the `Query` into SQL and runs it is a compiler's ([From QuerySet to SQL](sql.md), [Database backends](backends.md)). The instances it makes of rows are made by `Model.from_db`, and where `QuerySet.create` or `QuerySet.update_or_create` saves an instance the saving is `Model.save`'s ([Saving an instance](models/saving.md)).

Much of the rest of Django is written against the queryset's laziness. A generic list view builds a queryset in one method and hands it on to a paginator or a template ([The generic views as mixins](views/generic.md)), the choices of a form field for a relation are read from a queryset each time they are gone through, as they are when the form is rendered ([Forms](forms.md)), and the admin's list of rows is one queryset refined by each filter in turn ([The admin](admin.md)).
