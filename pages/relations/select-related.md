---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `select_related`: related objects from the same row

`QuerySet.select_related` records on the query which relations to follow; the compiler joins their tables, selects their columns beside the model's and records what it selected as a tree of `klass_info`; and `ModelIterable` has a `RelatedPopulator` make each related instance from its share of the row and store it on the instance it was reached from.

## `select_related`: what the method leaves on the query

`QuerySet.select_related` asks for a relation that leads to one object to be fetched in the queryset's own statement: the related table joined, its columns selected beside the model's, and the related instance made of the same row as the model's. Like the other methods that refine a queryset, it only records the request. It returns what `QuerySet._chain` gives it ([Clones: how a queryset is built](../querysets/chaining.md)), with `Query.select_related` changed on its query (`django/db/models/query.py:QuerySet.select_related`, `django/db/models/sql/query.py:Query.select_related`).

The attribute has three forms. It is `False` on a new query. Given names, the method calls `Query.add_select_related`, which splits each name at its double underscores and files the parts in nested dictionaries, so that `"ship__home"` and `"ship__captain"` share one entry for `"ship"` (`django/db/models/sql/query.py:Query.add_select_related`). A later call with more names adds them to the clone's own deep copy of those dictionaries, and the earlier queryset's are left as they were (`django/db/models/sql/query.py:Query.clone`). Given `None` alone, the method sets `False` again. And called with no arguments it sets `True`, which leaves the choice of relations to the compiler.

```text recording=querysets
Sailor.objects.select_related('ship').query.select_related, Sailor.objects.select_related('ship__home', 'ship__captain').query.select_related  ->  ({'ship': {}}, {'ship': {'home': {}, 'captain': {}}})
```

> **Deprecated.** Calling `select_related` with no arguments warns with `RemovedInDjango2028Warning`. The warning goes through `warn_about_external_use`, which says nothing when the caller is Django's own code, and the deprecation timeline has the call raising `TypeError` when the deprecation ends (`django/utils/deprecation.py:warn_about_external_use`, `docs/internals/deprecation.txt`).

The method refuses a queryset made by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference` ([Combining querysets: the operators and `union`](../querysets/combining.md)), and one on which `QuerySet.values` or `QuerySet.values_list` has been called, which makes no instances ([`values` and `values_list`: rows as dictionaries and tuples](../querysets/values.md)). It does not look at the names it is given. Whether `"ship"` is a relation of the model, and one that can be followed, is found out by the compiler as it composes the statement, so a mistaken name raises when the queryset is evaluated and not when the method is called.

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

The two setters are what leaves the related object where a later read of the relation finds it without a query. The compiler chooses them as it builds `klass_info`, and for a relation of the model each is either a function that does nothing or `FieldCacheMixin.set_cached_value`, which writes one entry in the cache of related objects that an instance's state holds: the field's, or that of its **rel**, the object that stands for the relation as seen from the other model ([Reading and setting related objects](related-objects.md)) (`django/db/models/fields/mixins.py:FieldCacheMixin`). `ModelState.__del__` empties that cache when the state object is finalized (`django/db/models/base.py:ModelState.__del__`).

| the relation followed | `local_setter`, on the instance the relation starts from | `remote_setter`, on the instance just made |
|---|---|---|
| forwards, by a field that is not unique: a sailor's `"ship"`, a `ForeignKey` | the field's: the Ship is cached under `"ship"` | does nothing |
| forwards, by a field that is unique: a ship's `"captain"`, a `OneToOneField` | the field's: the Sailor is cached under `"captain"` | the rel's: the Ship is cached on the Sailor under `"command"` |
| in reverse: a sailor's `"command"`, or a parent's way down to its child | the rel's: what was made is cached under the accessor's name | the field's: the starting instance is cached under the field's name |

*The two functions a `RelatedPopulator` is given, by the kind of relation (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`).*

A name given to `QuerySet.select_related` may also be that of a `FilteredRelation`, a relation given to `QuerySet.annotate` under a new name with a condition for its join ([`filter`, `exclude` and `Q` objects](../querysets/filters.md)): for it the compiler supplies two functions of its own in place of these, and the object is set as an attribute under that name.

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

Under the populator's line for the Gannet there is a `from_db`. Under its line for the Petrel there is none: the key's column held `None`, no instance was made, and `local_setter` was called with `None`, which is what the Petrel's cache then holds for `"captain"`. To the relation's descriptor an entry of `None` and no entry are different things: the first says that there is no object, the second that nobody has looked ([Reading and setting related objects](related-objects.md)). A Petrel fetched without `select_related`, by the question that calls `QuerySet.get`, has no entry.

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

The statement has the same outer join. Afterwards the sailor's cache holds `None` under `"officer"`, as the Petrel's held `None` for its captain, and reading the attribute raises with no statement sent.

## Known related objects

`QuerySet._known_related_objects` is how a queryset is told that some of the objects its instances point at are already at hand. It is a dictionary from a relation field to a dictionary of objects by key, empty on a new queryset and handed from clone to clone ([Clones: how a queryset is built](../querysets/chaining.md)).

In `django/` one piece of code puts a dictionary there: the `_apply_rel_filters` of `RelatedManager`, the manager at the other end of a foreign key. Having asked its queryset for the rows that point at its instance, it sets the attribute, unless the instance's key is null, to a dictionary of one entry, which says that for this foreign key the object with this key is the instance (`django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager.RelatedManager._apply_rel_filters`). The operators that merge two querysets pour the second queryset's entries in with the first's (`django/db/models/query.py:QuerySet._merge_known_related_objects`) ([Combining querysets: the operators and `union`](../querysets/combining.md)).

`ModelIterable.__iter__` prepares each entry before its loop: it finds the attnames on the queryset's model that hold the key, one for an ordinary foreign key (`django/db/models/query.py:ModelIterable.__iter__`). Then, for each instance, after the annotations are set, it puts each entry through three steps:

1. If the relation is already cached on the instance, the entry is skipped. The comment names the case: an object loaded by `QuerySet.select_related` is not to be overwritten.
2. If any of the attnames is missing from the instance's `__dict__`, as it is when the column was deferred, the entry is skipped. Reading the key would fetch it, and the comment calls that an unexpected query.
3. Otherwise the key is read from the instance and looked up among the entry's objects. A key that is not there is passed over, which the comment says may happen with `qs1 | qs2`: a queryset merged from a related manager's and another can have rows that point at some other object. An object that is there is assigned to the instance under the field's name, with `setattr`, which is an assignment through the relation's descriptor and stores the object in the instance's cache ([Reading and setting related objects](related-objects.md)).

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

## `select_related`: `get_related_selections` and the tree of `klass_info`

`Query.select_related` is `False`, `True`, or a dictionary of names nested at each `"__"`, which `Query.add_select_related` builds from the names given to `QuerySet.select_related` (`django/db/models/sql/query.py:Query.add_select_related`). `True` means every forward relation that cannot be null, followed to a depth of `Query.max_depth`, which is five.

> **Deprecated.** Asking for `True`, by calling `select_related` with no arguments, warns with `RemovedInDjango2028Warning` (`django/db/models/query.py:QuerySet.select_related`). The release notes of 6.1 say that calling it with no arguments to select all non-nullable related fields is deprecated, and that the related fields should be named, or the `FETCH_PEERS` fetch mode used (`docs/releases/6.1.txt`) ([Deferred fields and the fetch modes](../instance/fetching.md)).

`SQLCompiler.get_related_selections` fills in the rest of the select list and returns the `klass_info` of each related model (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`). It is called by `get_select` with the list so far and the mask, and calls itself for each model it descends into, carrying the options and the alias of that model, the depth, the part of the dictionary that is under that name, and whether the names were restricted at all. At the top it works out the last two: restricted is whether `select_related` is a dictionary, and the dictionary is what was requested. Where the names are not restricted, a depth past `max_depth` returns nothing.

The forward relations come first. `select_related_descend` decides whether to follow a field (`django/db/models/query_utils.py:select_related_descend`): not where it is no relation, nor where it is the link to a parent model, which the comment says is always joined; in an unrestricted walk, where the field cannot be null; in a restricted one, where it was named, and with `FieldError` where the mask has entries but not this field, the error that says a field cannot be both deferred and traversed. A named field that is no relation is refused with `FieldError` before that. For a field that is followed, the `klass_info` names the related model, the field, `"reverse"` as `False` and two setters, the field's `FieldCacheMixin.set_cached_value` and, where the field is unique, the rel's, so that each instance is put in the other's cache (`django/db/models/fields/mixins.py:FieldCacheMixin.set_cached_value`); `Query.setup_joins` joins the related table, `get_default_columns` makes its columns under that alias with the relation's part of the mask, each appended to the list with its position recorded in `"select_fields"`, and the method descends.

The reverse relations are taken only in a restricted walk, and only those that are one-to-one: the model's related objects whose field is unique and not many-to-many. Each is put to `select_related_descend` as well, and one that is followed is joined by its related query name. Its `klass_info` has `"reverse"` as `True`, the setters the other way round, and `"from_parent"` as whether the related model is a subclass of this one: a child reached from its parent, as an officer from a sailor. `get_default_columns` is told the model the walk came from, and for that case skips the parent's fields, which are in the list already.

A filtered relation is followed at the top level only, the comment says. Its entry is made as a reverse relation's, with `"reverse"` as `True` and the final field of the joins as its `"field"`, and its remote setter sets the related instance on the instance as an attribute under the alias, which no field of the model bears (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`). Last, a restricted walk refuses with `FieldError` any requested name it did not meet, listing the choices: the model's relation fields, the reverse one-to-one relations by their query names, and the filtered relations.

`SQLCompiler.get_select_from_parent` is the one step after the walk, a class method that goes down the tree and, for each `klass_info` reached from a parent, puts the parent's positions in front of its own, so that a child's instance can be built from the parent's columns and its own (`django/db/models/sql/compiler.py:SQLCompiler.get_select_from_parent`). A sailor with its ship, the ship's home port, and the officer the sailor may be:

```text recording=sql
get_select with select_related: the related models' columns follow the model's, and klass_info becomes a tree
    select[0]: "crew_sailor"."id"  (Col(crew_sailor, crew.Sailor.id))
    select[1]: "crew_sailor"."name"  (Col(crew_sailor, crew.Sailor.name))
    select[2]: "crew_sailor"."ship_id"  (Col(crew_sailor, crew.Sailor.ship))
    select[3]: "crew_sailor"."signed_on"  (Col(crew_sailor, crew.Sailor.signed_on))
    select[4]: "fleet_ship"."id"  (Col(fleet_ship, fleet.Ship.id))
    select[5]: "fleet_ship"."name"  (Col(fleet_ship, fleet.Ship.name))
    select[6]: "fleet_ship"."tonnage"  (Col(fleet_ship, fleet.Ship.tonnage))
    select[7]: "fleet_ship"."home_id"  (Col(fleet_ship, fleet.Ship.home))
    select[8]: "fleet_ship"."captain_id"  (Col(fleet_ship, fleet.Ship.captain))
    select[9]: "fleet_port"."id"  (Col(fleet_port, fleet.Port.id))
    select[10]: "fleet_port"."name"  (Col(fleet_port, fleet.Port.name))
    select[11]: "fleet_port"."country"  (Col(fleet_port, fleet.Port.country))
    select[12]: "crew_officer"."sailor_ptr_id"  (Col(crew_officer, crew.Officer.sailor_ptr))
    select[13]: "crew_officer"."rank"  (Col(crew_officer, crew.Officer.rank))
    annotation_col_map: {}
    klass_info: model Sailor, select_fields [0, 1, 2, 3]
      klass_info: model Ship, reached by Sailor.ship, reverse=False, from_parent=False, select_fields [4, 5, 6, 7, 8]
        klass_info: model Port, reached by Ship.home, reverse=False, from_parent=False, select_fields [9, 10, 11]
      klass_info: model Officer, reached by Officer.sailor_ptr, reverse=True, from_parent=True, select_fields [0, 1, 2, 3, 12, 13]
```

```text figure=select-list-and-klass-info
Sailor.objects.select_related('ship__home', 'officer')

position   0   1     2        3           4   5     6        7        8           9   10    11       12             13
column     id  name  ship_id  signed_on   id  name  tonnage  home_id  captain_id  id  name  country  sailor_ptr_id  rank
table      crew_sailor                    fleet_ship                               fleet_port         crew_officer

klass_info: Sailor                                            select_fields [0, 1, 2, 3]
  Ship, reached by Sailor.ship, forward                       select_fields [4, 5, 6, 7, 8]
    Port, reached by Ship.home, forward                       select_fields [9, 10, 11]
  Officer, reached by Officer.sailor_ptr, reverse, from_parent  select_fields [0, 1, 2, 3, 12, 13]
```

*The select list of a sailor with its ship, the ship's home port and the officer the sailor may be, and the tree of `klass_info` beneath it: each node names its model, the field that reached it where one did, and the positions of its columns. The officer's positions begin with the sailor's own, since a child reached from its parent is built from the parent's columns and its own.*

The iterable reads the tree. `ModelIterable.__iter__` takes the model's positions from the root and makes a `RelatedPopulator` of each related `klass_info`, which takes its slice of the row by its positions, reorders them into the order the model's constructor expects where they came through a parent, tests the primary key's column for `None` so that an outer join with no row on the far side gives no instance, and calls the two setters ([`RelatedPopulator`: an instance for each joined model](#relatedpopulator-an-instance-for-each-joined-model)). `SQLCompiler.get_select_for_update_of_arguments` reads the tree too, to find the first selected column of each model a lock's `"OF"` names (`django/db/models/sql/compiler.py:SQLCompiler.get_select_for_update_of_arguments`) ([The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)). The errors, and the two walks, unrestricted and by name:

```text recording=sql
klass_info: model Ship, select_fields [0, 1, 2, 3, 4]
  klass_info: model Port, reached by Ship.home, reverse=False, from_parent=False, select_fields [5, 6, 7]
Ship.objects.select_related().query.select_related  ->  True
  warns RemovedInDjango2028Warning: Calling select_related() with no arguments is deprecated. Specify the fields to fetch instead.
Ship.objects.select_related('crew')  ->  raises FieldError: Invalid field name(s) given in select_related: 'crew'. Choices are: home, captain
Ship.objects.select_related('name')  ->  raises FieldError: Non-relational field given in select_related: 'name'. Choices are: home, captain
Sailor.objects.select_related('ship').only('name')  ->  raises FieldError: Field Sailor.ship cannot be both deferred and traversed using select_related at the same time.
Sailor.objects.select_related('ship').defer('ship')  ->  raises FieldError: Field Sailor.ship cannot be both deferred and traversed using select_related at the same time.
[len(Ship.objects.select_related(*names).query.get_compiler('default').get_select()[0]) for names in (('home',), ('home', 'captain'), ('captain__ship__home',))]  ->  [8, 12, 17]
```

The unrestricted walk followed the ship's home port and not its captain, which may be null. The crew is refused because a reverse relation that is not one-to-one is never followed, and the choices list the two forward relations; a plain field is refused by name. The last line is the three lengths of the list: eight columns with the port, twelve with the captain as well, and seventeen through the captain's ship to its port, each model's columns added whole.
