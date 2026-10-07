---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From rows to instances: `ModelIterable` and `select_related`

`ModelIterable` is the iterable class of an ordinary queryset: `ModelIterable.__iter__` runs the query and makes a model instance of each row with `Model.from_db`. Where `QuerySet.select_related` has made the query join related tables, one row holds the columns of several models, and a `RelatedPopulator` for each joined model makes an instance from its share of the row, where the row has one, and has it stored on the instance it was reached from.

What a statement returns is rows, and a **row** is a sequence of values with no names in it: the fourth value means whatever the fourth item of the statement's select list said. An instance wants the opposite. It wants each value under the **attname** of a field, the name of the attribute that holds the field's value (`"ship_id"` for a sailor's foreign key to a ship); a state that says which database it came from; and, for a relation the program is about to follow, the related object already in place. The step from one to the other has to know what the compiler selected and in what order, so it is taken by an object that works with the compiler directly: an instance of the queryset's **iterable class**, which is `ModelIterable` on a new queryset; `QuerySet.values` and `QuerySet.values_list` set another, which makes no instances ([`values` and `values_list`: rows as dictionaries and tuples](values.md)). When the iterable is made, and what becomes of the instances it yields, is told in [Evaluation and the result cache](evaluation.md).

## An iterable: `BaseIterable`

The iterable classes share a small base, `BaseIterable`, and `BaseIterable.__init__` keeps three things: the queryset, whether the compiler is to be asked for a chunked fetch, and how many rows to ask the cursor for at a call, which is `GET_ITERATOR_CHUNK_SIZE`, 100, unless another number is given (`django/db/models/query.py:BaseIterable`). `QuerySet._fetch_all` makes one from the queryset alone and takes a list of all it yields; `QuerySet.iterator` has one made with the other two given as well.

The base class has no `__iter__`. Each subclass has its own, and that method is where the statement that fetches the queryset's rows is sent and each row is made into something. `BaseIterable.__aiter__` is the way in for the `async for` that `QuerySet.aiterator` runs over the iterable, and belongs to [The asynchronous methods of a queryset](async.md).

## What the compiler has ready

`ModelIterable.__iter__` starts by reading three things off its queryset: the alias of the database, from `QuerySet.db`; a compiler for that database, from the query's `Query.get_compiler`; and the queryset's **fetch mode**, the object that decides how an instance later fetches what is missing from it ([Deferred fields and fetch modes in a queryset](deferred.md)) (`django/db/models/query.py:ModelIterable.__iter__`, `django/db/models/sql/query.py:Query.get_compiler`). The alias is read once, and goes to `Model.from_db` with every row of the run.

Then the iterable calls `SQLCompiler.execute_sql`, which composes the statement and sends it, unless composing it raises `EmptyResultSet`, as it does for a queryset made by `QuerySet.none`: then nothing is sent, and the iterable is given no rows (`django/db/models/sql/compiler.py:SQLCompiler.execute_sql`).

To compose the statement the compiler had to settle what is selected, and it keeps what it settled. `SQLCompiler.setup_query` stores the three results of `SQLCompiler.get_select` on the compiler, where until then there was `None`, and the iterable reads them as soon as `execute_sql` has returned (`django/db/models/sql/compiler.py:SQLCompiler.setup_query`, `django/db/models/sql/compiler.py:SQLCompiler.get_select`).

| attribute | what it holds |
|---|---|
| `SQLCompiler.select` | what the query selects, in order, without anything the compiler adds to the statement's select list only for an ordering: for each a tuple of the expression selected, its SQL with its parameters, and its alias or `None` |
| `SQLCompiler.klass_info` | which columns are which model's: a dictionary for the queryset's model with the positions of its columns, and inside it one for each related model the query was asked to select with it |
| `SQLCompiler.annotation_col_map` | for each selected column that has an alias, the alias and the column's position |

*The three results of `SQLCompiler.get_select` that `SQLCompiler.setup_query` keeps on a compiler for the iterable to read.*

What follows was recorded from a running Django, on SQLite, over the models and rows that the chapter's opening page, [QuerySets](../querysets.md), lists. A Sailor there has a foreign key to a Ship, `"ship"`. A Ship has a foreign key to a Port, `"home"`, and a one-to-one field to a Sailor that may be null, `"captain"`, whose other end is a sailor's `"command"`. And an Officer is a child of Sailor with a table of its own. In a recording a line is a call, nested under the call that made it, or an expression that was evaluated, with what it returned after `->`, and a line that begins `SQL` is a statement as Django handed it to its cursor. Here a compiler was asked for by hand, told to compose the statement, and its `select` and `klass_info` written down, for a queryset of sailors that follows two relations: from a sailor to its ship, and from the ship to its home port.

```text recording=querysets
What the compiler hands the iterable for Sailor.objects.select_related('ship__home'): the columns, and which of them are whose
    joined = Sailor.objects.select_related('ship__home').order_by('id')[:2]
    compiler = joined.query.get_compiler('default'); compiler.as_sql()
    select[0]: crew_sailor.id
    select[1]: crew_sailor.name
    select[2]: crew_sailor.ship_id
    select[3]: crew_sailor.signed_on
    select[4]: fleet_ship.id
    select[5]: fleet_ship.name
    select[6]: fleet_ship.tonnage
    select[7]: fleet_ship.home_id
    select[8]: fleet_ship.captain_id
    select[9]: fleet_port.id
    select[10]: fleet_port.name
    select[11]: fleet_port.country
    klass_info: model Sailor, select_fields [0, 1, 2, 3]
      klass_info: model Ship, reached by Sailor.ship, reverse=False, from_parent=False, select_fields [4, 5, 6, 7, 8]
        klass_info: model Port, reached by Ship.home, reverse=False, from_parent=False, select_fields [9, 10, 11]
```

`klass_info` is a tree. Its root is the dictionary for the queryset's own model, with the model under `"model"` and the positions of its columns under `"select_fields"`. Where the query has `Query.select_related` set, the root also has `"related_klass_infos"`, a list of dictionaries of the same kind, one for each relation followed from that model. Each of those adds the field the relation belongs to, whether it was followed in reverse, whether the related model is a child of the one it was reached from, two functions that will tie the two instances together, and a list of its own for the relations followed from there. How the compiler builds the tree and the joins that go with it is told in [From QuerySet to SQL](../sql.md); the iterable only reads it.

## One instance from one row

Before its loop over the rows, `ModelIterable.__iter__` works out once what it will do to every row. From the root of `SQLCompiler.klass_info` it takes the model class and the positions of the model's columns, which it treats as one run from the first position to the last, and from `SQLCompiler.select` the attnames that go with that run. Then, for each row that `SQLCompiler.results_iter` yields, it cuts the run out of the row and calls `Model.from_db` with the alias, the names and the values (`django/db/models/query.py:ModelIterable.__iter__`, `django/db/models/sql/compiler.py:SQLCompiler.results_iter`). What `from_db` makes of them is told in [An instance and its state](../models/instances.md), and what follows from a list of names that `QuerySet.defer` or `QuerySet.only` has shortened in [Deferred fields and fetch modes in a queryset](deferred.md).

The new instance is not yielded at once. In this order, the loop adds a weak reference to it to the list of **peers**, the instances made of the rows of this one statement, if the fetch mode is one that keeps track of them ([Deferred fields and fetch modes in a queryset](deferred.md)); gives the row and the instance to each related populator; sets each annotation on it as an attribute; and looks among the queryset's known related objects for one the instance points at.

> **Deprecated.** `from_db` is called with the queryset's fetch mode as the keyword argument `"fetch_mode"`, which `Model.from_db` has accepted since 6.1. A model whose own `from_db` accepts neither that keyword nor arbitrary keywords is still served: `_get_from_db` finds this out before the loop, warns with `RemovedInDjango2028Warning`, and has the override called without the mode, so the instances are not given the queryset's (`django/db/models/query.py:_get_from_db`).

## Annotations become attributes

`SQLCompiler.annotation_col_map` gives the position in the row of every selected column that has an alias. For a queryset of instances those are the annotations the query selects and the columns added with `extra(select=...)`. For each, the loop of `ModelIterable.__iter__` sets the row's value on the instance under the alias with `setattr` (`django/db/models/query.py:ModelIterable.__iter__`). For an annotation, what results is an ordinary attribute: no field stands behind it and `Model.from_db` was not given it.

An annotation made with `QuerySet.alias` is on the query for conditions and orderings to refer to and is not selected, so it has no position in the row and nothing is set ([Annotations, ordering and the other methods that change the query](methods.md)).

```text recording=querysets
[(ship.name, ship.hands) for ship in Ship.objects.annotate(hands=Count('crew')).order_by('name')]  ->  [('Gannet', 2), ('Petrel', 2)]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" ORDER BY "fleet_ship"."name" ASC
...
[(ship.name, hasattr(ship, 'hands')) for ship in Ship.objects.alias(hands=Count('crew')).filter(hands__gt=1)]  ->  [('Petrel', False), ('Gannet', False)]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" HAVING COUNT("crew_sailor"."id") > %s with params (1,)
```

In the first statement the count is the last column of the select list, and each Ship has it as `"hands"`. In the second the count appears only in the `"HAVING"` clause, and `hasattr` finds nothing on either ship.

## `select_related`: what the method leaves on the query

`QuerySet.select_related` asks for a relation that leads to one object to be fetched in the queryset's own statement: the related table joined, its columns selected beside the model's, and the related instance made of the same row as the model's. Like the other methods that refine a queryset, it only records the request. It returns what `QuerySet._chain` gives it ([Clones: how a queryset is built](chaining.md)), with `Query.select_related` changed on its query (`django/db/models/query.py:QuerySet.select_related`, `django/db/models/sql/query.py:Query.select_related`).

The attribute has three forms. It is `False` on a new query. Given names, the method calls `Query.add_select_related`, which splits each name at its double underscores and files the parts in nested dictionaries, so that `"ship__home"` and `"ship__captain"` share one entry for `"ship"` (`django/db/models/sql/query.py:Query.add_select_related`). A later call with more names adds them to the clone's own deep copy of those dictionaries, and the earlier queryset's are left as they were (`django/db/models/sql/query.py:Query.clone`). Given `None` alone, the method sets `False` again. And called with no arguments it sets `True`, which leaves the choice of relations to the compiler.

```text recording=querysets
Sailor.objects.select_related('ship').query.select_related, Sailor.objects.select_related('ship__home', 'ship__captain').query.select_related  ->  ({'ship': {}}, {'ship': {'home': {}, 'captain': {}}})
```

> **Deprecated.** Calling `select_related` with no arguments warns with `RemovedInDjango2028Warning`. The warning goes through `warn_about_external_use`, which says nothing when the caller is Django's own code, and the deprecation timeline has the call raising `TypeError` when the deprecation ends (`django/utils/deprecation.py:warn_about_external_use`, `docs/internals/deprecation.txt`).

The method refuses a queryset made by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference` ([Combining querysets: the operators and `union`](combining.md)), and one on which `QuerySet.values` or `QuerySet.values_list` has been called, which makes no instances ([`values` and `values_list`: rows as dictionaries and tuples](values.md)). It does not look at the names it is given. Whether `"ship"` is a relation of the model, and one that can be followed, is found out by the compiler as it composes the statement, so a mistaken name raises when the queryset is evaluated and not when the method is called.

## Which relations are followed: `select_related_descend`

Composing the select list of a query that has `Query.select_related` set, the compiler walks the relations of the model in `SQLCompiler.get_related_selections`. For each relation it follows it adds a join, appends the related model's columns to the select list, makes the dictionary that goes into `SQLCompiler.klass_info`, and calls itself for the related model (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`). Which relations it follows is decided by `select_related_descend`, a function outside the compiler, which is asked about one candidate at a time (`django/db/models/query_utils.py:select_related_descend`).

| `Query.select_related` | the candidates | which of them are followed | how deep |
|---|---|---|---|
| a dictionary of names | the model's forward relations, the fields of the model that point at another, and the reverse relations whose field is unique, which lead to one object: the other end of a `OneToOneField`, a parent's way down to a child model among them | those whose name is in the dictionary at that level | as deep as the names go |
| `True` | the model's forward relations | those whose field may not be null | until the walk is more than `Query.max_depth` relations, 5, from the queryset's model |

*What the compiler follows, by the form of the request.*

Under either form a child's link to its parent is passed over: the parent's fields are the child's as well, and its table is joined to select them without being asked for (`django/db/models/sql/compiler.py:SQLCompiler.get_default_columns`). And a relation that leads to many objects is no candidate, neither a many-to-many field nor the reverse of a foreign key that is not unique. The documentation gives the reason, that joining across a relation to many objects would make a much larger result, and such relations are left to [`prefetch_related`: related objects in a second query](prefetch.md) (`docs/ref/models/querysets.txt`). Here a queryset of sailors is asked with no arguments:

```text recording=querysets
len(Sailor.objects.select_related())  ->  4
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id")
```

The statement joins the sailor's ship and the ship's home port, neither of which may be null, and does not go back to the sailors' table for the ship's captain, which may.

Where names were given, a name the compiler found no relation for raises `FieldError` with the names that would have done, and a relation that was named but that the queryset's `QuerySet.defer` or `QuerySet.only` has left out of what is selected raises `FieldError` from `select_related_descend` itself:

```text recording=querysets
list(Sailor.objects.select_related('ship').only('name'))  ->  raises FieldError: Field Sailor.ship cannot be both deferred and traversed using select_related at the same time.
...
list(Sailor.objects.select_related('pilots_into'))  ->  raises FieldError: Invalid field name(s) given in select_related: 'pilots_into'. Choices are: ship, command, officer
```

## `RelatedPopulator`: an instance for each joined model

`get_related_populators` turns the tree of `SQLCompiler.klass_info` into a tree of objects: one `RelatedPopulator` for each dictionary under `"related_klass_infos"`, each of which, as it is made, calls the function again for its own dictionary (`django/db/models/query.py:get_related_populators`). Every row is then handed down that tree. A populator makes its model's instance from its own columns of the row, hands the row and the new instance to the populators under it, and then ties the instance to the one it was handed. `ModelIterable.__iter__` has the tree made once, before its loop, so whatever can be worked out from the select list is worked out before the first row.

```text figure=one-row-three-instances
Sailor.objects.select_related("ship__home"): one row of the result

positions 0 to 3     crew_sailor.id, name, ship_id, signed_on              klass_info: Sailor
positions 4 to 8     fleet_ship.id, name, tonnage, home_id, captain_id     klass_info: Ship, reached by Sailor.ship
positions 9 to 11    fleet_port.id, name, country                          klass_info: Port, reached by Ship.home

ModelIterable.__iter__           positions 0 to 3   ->  Model.from_db  ->  a Sailor
  RelatedPopulator for Ship      positions 4 to 8   ->  Model.from_db  ->  a Ship, cached on the Sailor under "ship"
    RelatedPopulator for Port    positions 9 to 11  ->  Model.from_db  ->  a Port, cached on the Ship under "home"

Nothing is cached the other way: the Ship has no entry for its crew, and the Port none for its ships.
```

*One row of a query that follows two relations. `klass_info` says which positions are whose; the iterable makes the first instance and a populator each of the others; and each related instance is stored in the cache of the instance it was reached from.*

`RelatedPopulator.__init__` works out for its model what the iterable works out for the queryset's: where its columns are in a row, and the attnames that go with them. It also finds the position, among its own columns, of the first field of its model's primary key, `RelatedPopulator.pk_idx`, and keeps the two functions from its dictionary as `RelatedPopulator.local_setter` and `RelatedPopulator.remote_setter` (`django/db/models/query.py:RelatedPopulator.__init__`).

`RelatedPopulator.populate` is called with a row and the instance the relation starts from. It cuts its columns out of the row and looks at the one for the primary key. If that is `None`, the row has no related object. Otherwise it makes the instance with `Model.from_db` and passes the row and the new instance on to its own populators. Then it calls `local_setter` with the starting instance and what it made, object or `None`; and, where it made an object, `remote_setter` with the same two the other way round (`django/db/models/query.py:RelatedPopulator.populate`).

The two setters are what leaves the related object where a later read of the relation finds it without a query. The compiler chooses them as it builds `klass_info`, and for a relation of the model each is either a function that does nothing or `FieldCacheMixin.set_cached_value`, which writes one entry in the cache of related objects that an instance's state holds: the field's, or that of its **rel**, the object that stands for the relation as seen from the other model ([Reading and setting related objects](../models/related-objects.md)) (`django/db/models/fields/mixins.py:FieldCacheMixin`). `ModelState.__del__` empties that cache when the state object is finalized (`django/db/models/base.py:ModelState.__del__`).

| the relation followed | `local_setter`, on the instance the relation starts from | `remote_setter`, on the instance just made |
|---|---|---|
| forwards, by a field that is not unique: a sailor's `"ship"`, a `ForeignKey` | the field's: the Ship is cached under `"ship"` | does nothing |
| forwards, by a field that is unique: a ship's `"captain"`, a `OneToOneField` | the field's: the Sailor is cached under `"captain"` | the rel's: the Ship is cached on the Sailor under `"command"` |
| in reverse: a sailor's `"command"`, or a parent's way down to its child | the rel's: what was made is cached under the accessor's name | the field's: the starting instance is cached under the field's name |

*The two functions a `RelatedPopulator` is given, by the kind of relation (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`).*

A name given to `QuerySet.select_related` may also be that of a `FilteredRelation`, a relation given to `QuerySet.annotate` under a new name with a condition for its join ([`filter`, `exclude` and `Q` objects](filters.md)): for it the compiler supplies two functions of its own in place of these, and the object is set as an attribute under that name.

Here the queryset whose select list was shown, of two sailors with their ships and the ships' home ports, is evaluated:

```text recording=querysets
pair = list(joined)
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQLCompiler.execute_sql
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "fleet_port"."id", "fleet_port"."name", "fleet_port"."country" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") ORDER BY "crew_sailor"."id" ASC LIMIT 2
...
      get_related_populators
        RelatedPopulator.__init__  (for Ship, reached by Sailor.ship)
          get_related_populators
            RelatedPopulator.__init__  (for Port, reached by Ship.home)
      SQLCompiler.results_iter
      Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [1, 'Ada', 1, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      RelatedPopulator.populate  (the populator for Ship, from_obj=<Sailor: Ada>)
        Model.from_db('default', ['id', 'name', 'tonnage', 'home_id', 'captain_id'], [1, 'Petrel', 480, 1, None], fetch_mode=FETCH_ONE)  (Ship)
        RelatedPopulator.populate  (the populator for Port, from_obj=<Ship: Petrel>)
          Model.from_db('default', ['id', 'name', 'country'], [1, 'Bergen', 'Norway'], fetch_mode=FETCH_ONE)  (Port)
...
pair[0].ship is pair[1].ship, pair[0].ship == pair[1].ship, pair[0].ship.home is pair[1].ship.home  ->  (False, True, False)
Sailor.ship.is_cached(pair[0]), Ship.home.is_cached(pair[0].ship), 'crew' in pair[0].ship._state.fields_cache  ->  (True, True, False)
```

The populators were made once the statement had been sent, the one for Port inside the one for Ship. Then three calls of `from_db` shared one row: the iterable took the first four values for the Sailor, the populator for Ship the next five, and the populator for Port the last three.

The last line of the recording shows the first row of the table of the two setters: the Sailor has its Ship and the Ship its Port, and the Ship has no entry for `"crew"`; a ship's `"home"` is a `ForeignKey` too, so the Port is given none for its ships.

The line before it shows something a reader may not expect. Each call of `populate` that finds a key makes a new instance, and nothing remembers that a key was met in an earlier row. Ada and Bram serve on one ship, and each has a Ship object of its own. The two are equal, as instances of one model with one primary key are, and they are not one object; neither are their two Ports (`django/db/models/base.py:Model.__eq__`). A relation fetched by `QuerySet.prefetch_related` is fetched once for all the instances, and sailors of one ship are then given one Ship object between them ([`prefetch_related`: related objects in a second query](prefetch.md)).

### A relation that is null in a row

Where a relation followed by `select_related` is null in a row, `RelatedPopulator.populate` makes no instance, and what it hands to `local_setter` is `None`. A ship's captain may be null, and the Petrel has none. Asked to select captains with ships, the compiler joins the sailors' table with an outer join, so the Petrel's row has `None` in every one of the sailor's columns.

```text recording=querysets
ships = list(Ship.objects.select_related('captain'))
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQLCompiler.execute_sql
        SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") ORDER BY "fleet_ship"."name" ASC
...
      get_related_populators
        RelatedPopulator.__init__  (for Sailor, reached by Ship.captain)
      SQLCompiler.results_iter
      Model.from_db('default', ['id', 'name', 'tonnage', 'home_id', 'captain_id'], [2, 'Gannet', 1200, 2, 3], fetch_mode=FETCH_ONE)  (Ship)
      RelatedPopulator.populate  (the populator for Sailor, from_obj=<Ship: Gannet>)
        Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      Model.from_db('default', ['id', 'name', 'tonnage', 'home_id', 'captain_id'], [1, 'Petrel', 480, 1, None], fetch_mode=FETCH_ONE)  (Ship)
      RelatedPopulator.populate  (the populator for Sailor, from_obj=<Ship: Petrel>)
[ship.name for ship in ships], [Ship.captain.is_cached(ship) for ship in ships], ships[1]._state.fields_cache  ->  (['Gannet', 'Petrel'], [True, True], {'captain': None})
[(ship.name, ship.captain) for ship in ships]  ->  [('Gannet', <Sailor: Cora>), ('Petrel', None)]
Ship.captain.is_cached(Ship.objects.get(name='Petrel'))  ->  False
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s LIMIT 21 with params ('Petrel',)
ships[0].captain.command is ships[0]  ->  True
```

Under the populator's line for the Gannet there is a `from_db`. Under its line for the Petrel there is none: the key's column held `None`, no instance was made, and `local_setter` was called with `None`, which is what the Petrel's cache then holds for `"captain"`. To the relation's descriptor an entry of `None` and no entry are different things: the first says that there is no object, the second that nobody has looked ([Reading and setting related objects](../models/related-objects.md)). A Petrel fetched without `select_related`, by the question that calls `QuerySet.get`, has no entry.

> **Why.** `populate` tests one column, also where the primary key has several. The comment in `RelatedPopulator.__init__` gives the reason: every member of a primary key must be non-null, since a null could not be referred to through a foreign key, so one member is enough to tell whether the related object exists.

The last line of the recording is `remote_setter` at work on a one-to-one field: the Sailor made for the Gannet's captain has the Gannet cached as its `"command"`, the very object the queryset yielded.

### From a parent down to its child

An Officer is a Sailor with a second table, and `select_related` can be asked to follow the relation from a Sailor down to the Officer it may also be. An instance of the child needs the parent's columns as well as its own, and the row already has them once.

```text recording=querysets
down = Sailor.objects.select_related('officer').order_by('id')[2:3]
compiler = down.query.get_compiler('default'); compiler.as_sql()
select[0]: crew_sailor.id
select[1]: crew_sailor.name
select[2]: crew_sailor.ship_id
select[3]: crew_sailor.signed_on
select[4]: crew_officer.sailor_ptr_id
select[5]: crew_officer.rank
klass_info: model Sailor, select_fields [0, 1, 2, 3]
  klass_info: model Officer, reached by Officer.sailor_ptr, reverse=True, from_parent=True, select_fields [0, 1, 2, 3, 4, 5]
cora_row = list(down)
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQLCompiler.execute_sql
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "crew_officer"."sailor_ptr_id", "crew_officer"."rank" FROM "crew_sailor" LEFT OUTER JOIN "crew_officer" ON ("crew_sailor"."id" = "crew_officer"."sailor_ptr_id") ORDER BY "crew_sailor"."id" ASC LIMIT 1 OFFSET 2
...
      get_related_populators
        RelatedPopulator.__init__  (for Officer, reached by Officer.sailor_ptr)
      SQLCompiler.results_iter
      Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on'], [3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC)], fetch_mode=FETCH_ONE)  (Sailor)
      RelatedPopulator.populate  (the populator for Officer, from_obj=<Sailor: Cora>)
        Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on', 'sailor_ptr_id', 'rank'], (3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC), 3, 'master'), fetch_mode=FETCH_ONE)  (Officer)
type(cora_row[0]).__name__, type(cora_row[0].officer).__name__, cora_row[0].officer.sailor_ptr is cora_row[0]  ->  ('Sailor', 'Officer', True)
```

The compiler selects only the child's own two columns after the parent's four, and `SQLCompiler.get_select_from_parent` then puts the parent's positions in front of the child's in the child's `"select_fields"` (`django/db/models/sql/compiler.py:SQLCompiler.get_select_from_parent`). Positions gathered that way need not be in the order that `Model.__init__` expects them in for the child, the comment in `RelatedPopulator.__init__` says, so a populator whose dictionary has `"from_parent"` true does not cut a slice. It builds `RelatedPopulator.reorder_for_init`, a function that picks the positions out of a row in the order of the child model's concrete fields, and its list of attnames is in that order too. In the recording the values given to `from_db` for the Officer are a tuple where the Sailor's are a slice of the row: the picking function made it.

The two instances are then tied both ways, as the third row of the table of the two setters says: the Sailor has the Officer cached under `"officer"`, and the Officer has that Sailor cached as its parent, under `"sailor_ptr"`. Ada, the sailor whose key is 1, is no officer:

```text recording=querysets
no_officer = Sailor.objects.select_related('officer').get(pk=1)
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "crew_officer"."sailor_ptr_id", "crew_officer"."rank" FROM "crew_sailor" LEFT OUTER JOIN "crew_officer" ON ("crew_sailor"."id" = "crew_officer"."sailor_ptr_id") WHERE "crew_sailor"."id" = %s LIMIT 21 with params (1,)
no_officer._state.fields_cache, Sailor.officer.is_cached(no_officer)  ->  ({'officer': None}, True)
no_officer.officer  ->  raises RelatedObjectDoesNotExist: Sailor has no officer.
```

The statement has the same outer join. Afterwards her cache holds `None` under `"officer"`, as the Petrel's held `None` for its captain, and reading the attribute raises with no statement sent.

## Known related objects

`QuerySet._known_related_objects` is how a queryset is told that some of the objects its instances point at are already at hand. It is a dictionary from a relation field to a dictionary of objects by key, empty on a new queryset and handed from clone to clone ([Clones: how a queryset is built](chaining.md)).

In `django/` one piece of code puts a dictionary there: the `_apply_rel_filters` of `RelatedManager`, the manager at the other end of a foreign key. Having asked its queryset for the rows that point at its instance, it sets the attribute, unless the instance's key is null, to a dictionary of one entry, which says that for this foreign key the object with this key is the instance (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager.RelatedManager._apply_rel_filters`). The operators that merge two querysets pour the second queryset's entries in with the first's (`django/db/models/query.py:QuerySet._merge_known_related_objects`) ([Combining querysets: the operators and `union`](combining.md)).

`ModelIterable.__iter__` prepares each entry before its loop: it finds the attnames on the queryset's model that hold the key, one for an ordinary foreign key (`django/db/models/query.py:ModelIterable.__iter__`). Then, for each instance, after the annotations are set, it puts each entry through three steps:

1. If the relation is already cached on the instance, the entry is skipped. The comment names the case: an object loaded by `QuerySet.select_related` is not to be overwritten.
2. If any of the attnames is missing from the instance's `__dict__`, as it is when the column was deferred, the entry is skipped. Reading the key would fetch it, and the comment calls that an unexpected query.
3. Otherwise the key is read from the instance and looked up among the entry's objects. A key that is not there is passed over, which the comment says may happen with `qs1 | qs2`: a queryset merged from a related manager's and another can have rows that point at some other object. An object that is there is assigned to the instance under the field's name, with `setattr`, which is an assignment through the relation's descriptor and stores the object in the instance's cache ([Reading and setting related objects](../models/related-objects.md)).

Here petrel is the Ship named Petrel, which the program holds, and its crew is fetched through its manager:

```text recording=querysets
crew = list(petrel.crew.all())
  QuerySet._fetch_all
    ModelIterable.__iter__
      SQLCompiler.execute_sql
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s with params (1,)
...
crew[0].ship is petrel, crew[1].ship is petrel  ->  (True, True)
petrel.crew.select_related('ship')[0].ship is petrel  ->  False
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE "crew_sailor"."ship_id" = %s LIMIT 1 with params (1,)
Sailor.ship.is_cached(petrel.crew.only('name')[0])  ->  False
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s LIMIT 1 with params (1,)
```

One statement fetched the Petrel's two sailors, and each of them has as its ship the Petrel the program was already holding: the same object, with no statement sent to fetch it. The last two questions are the first two steps. With `select_related('ship')` added to the manager's queryset, the sailor's ship is not the Petrel the program holds. With `only('name')`, the statement does not select the key's column, and no ship is cached on the sailor.
