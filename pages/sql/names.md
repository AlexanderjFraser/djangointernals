---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`

`Query.names_to_path` reads the words of a filter's name against the models and returns the relations it crosses as a path; `Query.setup_joins` turns the path into joins, and `Query.trim_joins` takes back a join at the end whose only use is a key the previous table already holds; `Query.build_lookup` and `Query.try_transform` make transforms and a lookup of the words that are no fields. `Query.solve_lookup_type` puts a name to the annotations before the models, and `Query.resolve_ref` reads the name an `F` carries the same way.

A name in a filter has several things to be able to say. `"ship__home__name"` is a field of a sailor's ship's home port: two relations crossed, then a field. `"crew__name"` crosses a relation backwards, from a ship to the sailors whose foreign key points at it, and so can reach several rows for one ship; `"calls__country"` crosses a many-to-many relation through the table between. `"officer__rank"` reaches a field that a child model keeps in a table of its own, and `"name"` asked of an Officer reaches one that the parent's table holds. `"hands__gt"` names an annotation, which is a column of no table, and `"veterans__name"` a filtered relation under the alias it was given. And `"signed_on__year__lt"` ends in two words that are no fields at all: a function of the column, and a comparison. The same name is read by `filter`, by an `F`, by `order_by` and by `values`, so it is read in one place, on the query, and each caller takes from the walk what it needs.

The words are separated by `LOOKUP_SEP`, the string `"__"` (`django/db/models/constants.py:LOOKUP_SEP`). Reading them is three questions asked in turn, and a method answers each. Which words are fields, and what relations do they cross: `Query.names_to_path`, which returns a **path**, one `PathInfo` for each table the name crosses. What joins does the path need, and which of them is one too many: `Query.setup_joins`, which makes a `Join` of each `PathInfo` and hands it to the alias map, and `Query.trim_joins`, which takes back a join at the end whose only use is a key the previous table already holds. What do the words that are not fields mean: `Query.build_lookup`, which finds a transform class for each of them but the last in the registry of what stands to its left, and a lookup class for the last. For a filter, `Query.solve_lookup_type` asks the first question before anything is joined, so that `Query.build_filter` knows where the fields end; for an `F`, `Query.resolve_ref` asks all three and returns the column. The queryset's side of a filter, down to `Query.add_q`, is [`filter`, `exclude` and `Q` objects](../querysets/filters.md); what `build_filter` does with the lookup it is handed is [The where clause: `build_filter`, `add_q` and `WhereNode`](where.md); and what `Query.join` does with each join, the alias it gives it and the type it starts with, is [Tables and joins: the alias map and join promotion](joins.md).

```text figure=a-name-divided
ship__home__name__lower__exact        a filter's name, split at LOOKUP_SEP into five words

  ship     a foreign key of Sailor     PathInfo(from Sailor to Ship via Sailor.ship, direct, one)    names_to_path
  home     a foreign key of Ship       PathInfo(from Ship to Port via Ship.home, direct, one)        names_to_path
  name     a field of Port             the final field Port.name, and the target Port.name           names_to_path: the walk stops here
  lower    no field of Port            a transform: Lower(Col(fleet_port, fleet.Port.name))          build_lookup, through try_transform
  exact    the last word               a lookup: Exact(Lower(...), the value)                        build_lookup, through get_lookup

solve_lookup_type:  (['lower', 'exact'], ['ship', 'home', 'name'], False)      the words that are lookups, the words that are fields
setup_joins:        crew_sailor -> fleet_ship -> fleet_port                     one Join for each PathInfo, from the base table
trim_joins:         nothing taken back: Port.name is not a key fleet_ship holds
```

*One name divided into its words, with what each becomes and which method decides it. The first three words are fields and make the path; the last two are found in registries, the transform in the field's and the lookup in the transform's, or failing that in its output field's. The word `"lower"` presumes `Lower` registered on `CharField`, as the recording registers it: Django registers it on no field class (`django/db/models/functions/text.py:Lower`, `django/db/models/fields/__init__.py:CharField`).*

Here is the first condition of a filter, recorded from a running Django on SQLite. The lines are calls nested as they were made, with only the calls this page is about written down, and `->` is what a call returned, put into words: a step of a path as `PathInfo(from Sailor to Ship via Sailor.ship, direct, one)`, a field by its model and name, and a model's options as `the options of Port`.

```text recording=sql
Query.solve_lookup_type(lookup='ship__home__name')
  Query.names_to_path(names=['ship', 'home', 'name'])  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], Port.name, (Port.name,), [])
  -> ([], ['ship', 'home', 'name'], False)
...
Query.setup_joins(names=['ship', 'home', 'name'], alias='crew_sailor', can_reuse=set())
  Query.names_to_path(names=['ship', 'home', 'name'], fail_on_missing=True)  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], Port.name, (Port.name,), [])
  -> JoinInfo(final_field=Port.name, targets=(Port.name,), opts=the options of Port, joins=['crew_sailor', 'fleet_ship', 'fleet_port'], path=[PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)])
...
Query.trim_joins(targets=(Port.name,), joins=['crew_sailor', 'fleet_ship', 'fleet_port'], path=[PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)])  ->  ((Port.name,), 'fleet_port', ['crew_sailor', 'fleet_ship', 'fleet_port'])
Query.build_lookup(lookups=[], lhs=Col(fleet_port, fleet.Port.name), rhs='Bergen')
  Exact.__init__(lhs=Col(fleet_port, fleet.Port.name), rhs='Bergen')  (Lookup.__init__)
    Exact.get_prep_lookup  (Lookup.get_prep_lookup)  ->  'Bergen'
  -> Exact(Col(fleet_port, fleet.Port.name), 'Bergen')
```

The three questions are the three calls at the left. `solve_lookup_type` has `names_to_path` walk the whole name and reports that no word is left over and all three are fields. `setup_joins` walks it again and returns a `JoinInfo`, with the final field, its target, the aliases of the three tables and the path. `trim_joins` finds nothing to take back, since the name of a port is no key the ships' table holds, and `build_lookup`, given no words, makes an `Exact` of the column.

## The walk: `names_to_path`

`Query.names_to_path` takes a list of words and the options of the model to start from, and walks the words in order (`django/db/models/sql/query.py:Query.names_to_path`). At each word it asks the options for a field of that name through `Options.get_field`, which answers for a forward field and for the rel of a reverse one alike (`django/db/models/options.py:Options.get_field`); the word `"pk"` is first replaced by the name of the options' primary key field. Where there is no such field it looks in two more places: among the query's annotations, where the annotation's output field stands in for a field of a table, and, for the first word only, among the query's filtered relations, where the alias stands for the relation it was made of. What happens next depends on whether what it found is a relation.

A relation field, and the rel of one seen from the other side, each have `path_infos`: the way across the relation as a list of `PathInfo`, one for each table on the way (`django/db/models/fields/related.py:ForeignObject.path_infos`, `django/db/models/fields/reverse_related.py:ForeignObjectRel.path_infos`). A foreign key's path is one step to the related model; the rel's is one step back; a many-to-many field's is two in the ordinary case, a step back over one foreign key of the table between and a step forward over the other, with steps between where the two keys belong to different models of a parent chain, so that one word of the name can add two tables or more to the path (`django/db/models/fields/related.py:ManyToManyField._get_path_info`). Where the word was a filtered relation, the field is asked for its path afresh through `get_path_info` with the relation, and the last step it returns carries it, where the cached `path_infos` carries none (`django/db/models/fields/related.py:ForeignObject.get_path_info`). The walk appends the steps to the path, takes the last step's options as the model to read the next word against, and goes on. The field's side of all this, how a relation builds its path and what a rel is, is [Relations](../models/relations.md) and [Many-to-many relations](../models/many-to-many.md).

A field that is not a relation ends the walk. It is the **final field**, it is its own target, and the words after it are returned unread, for `build_lookup` to make what it can of them. Each step of a path says, as the recording writes it, which model it leaves and which it reaches, through which field or rel, whether it runs the way the field points and whether it can reach more than one row:

| field of `PathInfo` | what it holds |
|---|---|
| `"from_opts"`, `"to_opts"` | the options of the model the step leaves and of the model it reaches |
| `"join_field"` | the field or rel the join is made along; `Join` asks it for the pairs of columns to compare |
| `"target_fields"` | the fields at the far end whose columns hold the value the step reaches: a forward key's related fields, or the primary key of the model a reverse step reaches |
| `"direct"` | whether the step runs the way the field points: true for a step along a field and false for one along a rel, for the relations of `django.db.models`; a `GenericRelation` of `django.contrib.contenttypes` marks its steps false in both directions |
| `"m2m"` | whether the step can reach more than one row for one row of the model it leaves: true for a reverse step over a key that is not unique, and so for the first step of a many-to-many path |
| `"filtered_relation"` | the `FilteredRelation` whose condition the join is to carry, or `None` |

*The fields of a `PathInfo`, the named tuple of `django/db/models/query_utils.py` that a step of a path is (`django/db/models/query_utils.py:PathInfo`). The recording writes a step as `PathInfo(from Sailor to Ship via Sailor.ship, direct, one)`, with the word many where the step can reach several rows.*

What the walk returns is the path, the final field, its **targets**, the fields that hold the value the name reaches, and the words it did not read. For a relation that ends the name, the final field is the field the last step was made along and the targets are that step's target fields: the key of the related model for a forward key, and that key is what `filter(ship=petrel)` compares once the join is trimmed. Here is the walk asked directly, each line a question put to the running Django and its answer; the helper said puts the answer into the recording's words:

```text recording=sql
said(Sailor.objects.all().query.names_to_path(['name'], Sailor._meta))  ->  ([], Sailor.name, (Sailor.name,), [])
said(Sailor.objects.all().query.names_to_path(['pk'], Sailor._meta))  ->  ([], Sailor.id, (Sailor.id,), [])
said(Sailor.objects.all().query.names_to_path(['ship'], Sailor._meta))  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one)], Sailor.ship, (Ship.id,), [])
said(Sailor.objects.all().query.names_to_path(['ship', 'home', 'name'], Sailor._meta))  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], Port.name, (Port.name,), [])
```

A local field is a path of no steps. `"pk"` became the field `"id"`. The one word `"ship"` made a step whose target is the key of Ship, not the foreign key the step was made along; three words made two steps and ended at a field of Port, which is its own target.

```text recording=sql
said(Ship.objects.all().query.names_to_path(['crew', 'name'], Ship._meta))  ->  ([PathInfo(from Ship to Sailor via the rel of Sailor.ship, reverse, many)], Sailor.name, (Sailor.name,), [])
said(Voyage.objects.all().query.names_to_path(['calls', 'country'], Voyage._meta))  ->  ([PathInfo(from Voyage to Voyage_calls via the rel of Voyage_calls.voyage, reverse, many), PathInfo(from Voyage_calls to Port via Voyage_calls.port, direct, one)], Port.country, (Port.country,), [])
said(Sailor.objects.all().query.names_to_path(['pilots_into', 'country'], Sailor._meta))  ->  ([PathInfo(from Sailor to Licence via the rel of Licence.sailor, reverse, many), PathInfo(from Licence to Port via Licence.port, direct, one)], Port.country, (Port.country,), [])
```

A reverse step is made along the rel, runs against the direction of the key, and can reach many rows where the key is not unique, as these three can. The many-to-many field of a voyage made two steps of one word, the first over the table Django made for it, the second to the port; the field of a sailor whose table between is a model of the project's, Licence, made the same two steps over that table.

```text recording=sql
said(Berth.objects.all().query.names_to_path(['pk'], Berth._meta))  ->  ([], Berth.pk, (Berth.pk,), [])
said(Ship.objects.annotate(hands=Count('crew')).query.names_to_path(['hands', 'gt'], Ship._meta))  ->  ([], an unbound IntegerField, (an unbound IntegerField,), ['gt'])
```

The primary key of a Berth is a `CompositePrimaryKey`, a field of two columns, and the walk returns it as one field; what a comparison makes of it is [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](related-lookups.md). The last line is an annotation asked of the walk itself: the field it reports is the annotation's output field, an integer field that belongs to no model, and the word after it is left over, since a field that is no relation ends the walk whatever it is. A filter does not reach the walk with such a name, because `solve_lookup_type` answers it from the annotations first.

### What the walk refuses

`Query.names_to_path` sometimes refuses a step that can reach several rows: an `exclude` across such a step would, as a join, throw out a ship for the one sailor whose name matches and keep it for the others, so `build_filter` under a negation asks for the walk with `allow_many=False`. The walk then raises `MultiJoin` at the first step marked many, with the position of the word and the path travelled so far as the exception's attributes, and `build_filter` turns to `Query.split_exclude`, which builds a subquery instead; that is [The where clause: `build_filter`, `add_q` and `WhereNode`](where.md) (`django/db/models/sql/datastructures.py:MultiJoin`).

A word that is no field, no annotation and no filtered relation stops the walk, and what happens then is the caller's choice. Without `fail_on_missing=True` the walk steps back one word and returns, with the word and everything after it unread; with it, the walk raises `FieldError`, and so does a first word that nothing answers to, whatever the flag. The message lists the choices, sorted together by name: every field's name and, for a concrete field, its attname as well, which `get_field_names_from_opts` collects from the options, and the annotations and the filtered relations (`django/db/models/sql/query.py:get_field_names_from_opts`). A word that follows a field that is no relation is a different error under the flag, since a join on such a field is not possible, and the message says so.

```text recording=sql
names_to_path refusing: a multi-valued relation where none is allowed, a name that is no field, and a name after a field that is no relation
    said(Ship.objects.all().query.names_to_path(['crew', 'name'], Ship._meta, allow_many=False))  ->  raises MultiJoin
    said(Voyage.objects.all().query.names_to_path(['ship', 'name'], Voyage._meta, allow_many=False))  ->  ([PathInfo(from Voyage to Ship via Voyage.ship, direct, one)], Ship.name, (Ship.name,), [])
    said(Sailor.objects.all().query.names_to_path(['cargo'], Sailor._meta))  ->  raises FieldError: Cannot resolve keyword 'cargo' into field. Choices are: command, id, licence, name, officer, pilots_into, ship, ship_id, signed_on
    said(Sailor.objects.all().query.names_to_path(['ship', 'cargo'], Sailor._meta))  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one)], Sailor.ship, (Ship.id,), ['cargo'])
    said(Sailor.objects.all().query.names_to_path(['name', 'ship'], Sailor._meta))  ->  ([], Sailor.name, (Sailor.name,), ['ship'])
    said(Sailor.objects.all().query.names_to_path(['name', 'ship'], Sailor._meta, fail_on_missing=True))  ->  raises FieldError: Cannot resolve keyword 'ship' into field. Join on 'name' not permitted.
```

The second line shows that `allow_many=False` refuses a step marked many and nothing else: a foreign key is a step that reaches one row, and the walk across it goes through. In the last two lines the same name is asked with and without the flag. The relation field of a generic foreign key is refused wherever it stands in the name, whatever the flags: a field that is a relation but has no related model cannot be used for reverse querying, in the words of the error.

## `solve_lookup_type`: the annotations first

`Query.solve_lookup_type` is what `build_filter` asks of a name before it joins anything: which words are the lookups, and which the fields (`django/db/models/sql/query.py:Query.solve_lookup_type`). It splits the name at `LOOKUP_SEP` and, where the query has annotations, asks `refs_expression` whether the name begins with one (`django/db/models/query_utils.py:refs_expression`). That function tries each prefix of the words, shortest first, joined by `"__"` again, because an aggregate's default alias holds the separator: `Count("crew")` annotates as `"crew__count"`, and a filter on `"crew__count__gt"` must find it. Where a prefix is an annotation, `solve_lookup_type` returns the words after it as the lookups, no field words, and the annotation's expression itself, or a `Ref` to it under `summarize=True`, which is how an aggregate over an annotation refers to the inner query's column ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)). Otherwise it has `names_to_path` walk the words from the model's options, and the field words are the ones the walk read.

```text recording=sql
solve_lookup_type: the lookups, the field parts, and an annotation where the name refers to one
    Sailor.objects.all().query.solve_lookup_type('name')  ->  ([], ['name'], False)
    Sailor.objects.all().query.solve_lookup_type('ship__home__name__lower__startswith')  ->  (['lower', 'startswith'], ['ship', 'home', 'name'], False)
    Sailor.objects.all().query.solve_lookup_type('signed_on__year__lt')  ->  (['year', 'lt'], ['signed_on'], False)
    Ship.objects.annotate(hands=Count('crew')).query.solve_lookup_type('hands__gt')  ->  (['gt'], (), Count(Col(crew_sailor, crew.Sailor.id)))
    Ship.objects.annotate(hands=Count('crew')).query.solve_lookup_type('hands__gt', summarize=True)  ->  (['gt'], (), Ref(hands, Count(Col(crew_sailor, crew.Sailor.id))))
    Ship.objects.annotate(crew__count=Count('crew')).query.solve_lookup_type('crew__count__gt')  ->  (['gt'], (), Count(Col(crew_sailor, crew.Sailor.id)))
    Sailor.objects.all().query.solve_lookup_type('name__lower__upper__exact__gt')  ->  (['lower', 'upper', 'exact', 'gt'], ['name'], False)
```

The last line is the walk's limit: it stops at the first word that is no field and says nothing of the rest. Whether `"lower"`, `"upper"`, `"exact"` and `"gt"` make sense in that order is for `build_lookup` to find out, and here they do not: `"exact"` is no transform.

## `setup_joins`: a `Join` for each step

`Query.setup_joins` is given the field words, the options to start from, the alias of the table to start from and, where the caller has one, a set of aliases that a step marked many may reuse; it returns a `JoinInfo`, a named tuple of the final field, the targets, the options reached, the aliases joined, the path, and a function that makes the column (`django/db/models/sql/query.py:Query.setup_joins`, `django/db/models/sql/query.py:JoinInfo`). Two things in it are not obvious from what `names_to_path` already does.

**It tries shorter and shorter prefixes.** A caller that is not `build_filter`, an `F` or an ordering, hands it the whole name, transforms included, and has not asked `solve_lookup_type` first. So `setup_joins` calls `names_to_path` with `fail_on_missing=True` on the whole list, then on the list less its last word, and so on, until a prefix is read whole; the words after that prefix are the transforms. The error of the last prefix that failed is kept, and a prefix of one word that fails is raised as it is: the comment there says the first item cannot be a lookup.

**The transforms wait for the alias.** A transform wraps a column, and the column is not known until the joins have been trimmed, which happens after `setup_joins` returns; the comment there says the transform cannot be applied yet for that reason. So the method builds a **transform function** instead of applying the transforms: a chain of partial functions that, given a field and an alias, makes the column through `get_col` and wraps it in each transform in turn through `Query.try_transform`, marked with an attribute `"has_transforms"` where there was any, and the caller applies it once the alias is settled. Where a transform is not found and the final field is a field rather than a rel, the function raises the error that was kept from the longer prefix, so that `"ship__home__name__upper"` is refused as a join on a name rather than as an unknown transform.

```text recording=sql
setup_joins on a name with transforms: names_to_path is tried on shorter and shorter prefixes until one is all fields
    Sailor.objects.annotate(year=F('signed_on__year')).query.annotations['year']
      F.resolve_expression  (F(signed_on__year))
        Query.resolve_ref(name='signed_on__year')
          Query.setup_joins(names=['signed_on', 'year'], alias='crew_sailor')
            Query.names_to_path(names=['signed_on', 'year'], fail_on_missing=True)  raises FieldError
            Query.names_to_path(names=['signed_on'], fail_on_missing=True)  ->  ([], Sailor.signed_on, (Sailor.signed_on,), [])
            -> JoinInfo(final_field=Sailor.signed_on, targets=(Sailor.signed_on,), opts=the options of Sailor, joins=['crew_sailor'], path=[], with transforms)
          Query.try_transform(lhs=Col(crew_sailor, crew.Sailor.signed_on), name='year')  ->  ExtractYear(Col(crew_sailor, crew.Sailor.signed_on))
          -> ExtractYear(Col(crew_sailor, crew.Sailor.signed_on))
        -> ExtractYear(Col(crew_sailor, crew.Sailor.signed_on))
    Sailor.objects.annotate(port=F('ship__home__name__upper')).query.annotations['port']
      F.resolve_expression  (F(ship__home__name__upper))
        Query.resolve_ref(name='ship__home__name__upper')
          Query.setup_joins(names=['ship', 'home', 'name', 'upper'], alias='crew_sailor')
            Query.names_to_path(names=['ship', 'home', 'name', 'upper'], fail_on_missing=True)  raises FieldError
            Query.names_to_path(names=['ship', 'home', 'name'], fail_on_missing=True)  ->  ([PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], Port.name, (Port.name,), [])
            -> JoinInfo(final_field=Port.name, targets=(Port.name,), opts=the options of Port, joins=['crew_sailor', 'fleet_ship', 'fleet_port'], path=[PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)], with transforms)
          Query.try_transform(lhs=Col(fleet_port, fleet.Port.name), name='upper')  raises FieldError
    raises FieldError: Cannot resolve keyword 'upper' into field. Join on 'name' not permitted.
```

In the first line the whole name failed and the name less `"year"` was read, and the transform was applied by `resolve_ref` after the joins were settled. In the second, no transform named `"upper"` was registered on `CharField` at this point of the recording, and the error that reached the program is the one `names_to_path` had raised on the longer prefix (`django/db/models/fields/__init__.py:CharField`).

**A `Join` for each step, with its type to be decided.** For each `PathInfo` of the path the method makes a `Join` of the table reached, the alias it stands on, the step's field or rel, and whether the join is nullable: for a step that runs the way the field points, `Query.is_nullable` says so of the field, and a step that runs the other way is always nullable, since nothing promises a row on the far side (`django/db/models/sql/query.py:Query.is_nullable`). The join is made with `"INNER JOIN"` as a placeholder, and `Query.join` decides its first type, outer where the join is nullable or the join it hangs from is outer, and its alias ([Tables and joins: the alias map and join promotion](joins.md)). What `join` may reuse is the one place the set of reusable aliases matters: for a step marked many it is passed through, and for any other step the method passes `None`, which lets any equal join be reused. A step that carries a filtered relation is made with the relation's alias as the table alias, and the alias it gets is added to the set of reusable aliases where the caller gave one.

> **Trap.** `is_nullable` is true of a field with `null=True`, and also of a field that allows the empty string on a backend whose features say it stores the empty string as null, which is Oracle's (`django/db/backends/oracle/features.py`). The features consulted are the default connection's, whatever database the queryset will run on: the comment in the method says that the query has no knowledge of its connection, and should not, and that deferring the decision to the compiler would be the proper fix. The same is done in `build_lookup` for the same reason.

### `trim_joins`: the join that is one too many

`Query.trim_joins` is given the targets, the aliases joined and the path, and walks the path from its end (`django/db/models/sql/query.py:Query.trim_joins`). At each step that runs the way the field points, it asks whether every target's column is among the columns of the fields the key points at; if so, the value the name reaches is already held by the key on the near side, and the join is one too many. The targets are replaced by the key's own fields, through the pairs in `related_fields`, the alias is dropped from the list, and its reference count is lowered by `Query.unref_alias`, so that the join stays in the alias map, and is not written where nothing else refers to it ([Tables and joins: the alias map and join promotion](joins.md)). The walk stops at the first step it cannot take back: a step that runs against the field, a step that carries a filtered relation, a step whose targets are not all among the fields its key points at, or the base table. The docstring says why a reverse step is never trimmed: it is unknown whether there is anything on the other side of the join.

```text recording=sql
  Query.trim_joins(targets=(Port.id,), joins=['crew_sailor', 'fleet_ship', 'fleet_port'], path=[PathInfo(from Sailor to Ship via Sailor.ship, direct, one), PathInfo(from Ship to Port via Ship.home, direct, one)])
    Query.unref_alias(alias='fleet_port')
    -> ((Ship.home,), 'fleet_ship', ['crew_sailor', 'fleet_ship'])
alias_map['crew_sailor']: BaseTable(crew_sailor), referenced 1
alias_map['fleet_ship']: Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable), referenced 1
alias_map['fleet_port']: Join(fleet_port, from fleet_ship via Ship.home, INNER JOIN, not nullable), referenced 0
```

The name reached the key of Port through two joins, and the key of Port is what `"home_id"` on the ships' table holds, so the third table was taken back: the target became the ship's own foreign key `"home"`, the alias the ships' table, and the port's table stays in the map with no reference. The same, asked of the statements:

```text recording=sql
sql_of(Sailor.objects.filter(ship=petrel))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', (1,))
sql_of(Sailor.objects.filter(ship__home=bergen))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE "fleet_ship"."home_id" = %s', (1,))
...
sql_of(Ship.objects.filter(crew=ada))  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" INNER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") WHERE "crew_sailor"."id" = %s ORDER BY "fleet_ship"."name" ASC', (1,))
sql_of(Voyage.objects.filter(calls=leith))  ->  ('SELECT "fleet_voyage"."id", "fleet_voyage"."ship_id", "fleet_voyage"."sailed" FROM "fleet_voyage" INNER JOIN "fleet_voyage_calls" ON ("fleet_voyage"."id" = "fleet_voyage_calls"."voyage_id") WHERE "fleet_voyage_calls"."port_id" = %s', (2,))
```

A sailor's ship joins nothing, and the comparison is on `"ship_id"`; a ship's home port joins the ship and compares `"home_id"`. A ship's crew is a reverse step and keeps its join, comparing the sailor's own key; a voyage's ports of call keep the table between, a reverse step, and take back the step to the port, so that the comparison is on `"port_id"` of the table between.

## `build_lookup` and `try_transform`: the words that are no fields

`Query.build_lookup` is given the words left over, the column, and the value (`django/db/models/sql/query.py:Query.build_lookup`). Every word but the last is a **transform**: a class, registered on the column's field or on the transform before it, that makes an expression of what stands to its left, as `ExtractYear` makes the year of a datetime. The last word is a **lookup**: a class that makes a comparison of what stands to its left with the value. With no words at all the lookup is `"exact"`. Each word is found by asking the thing to its left, through `get_lookup` or `get_transform`: a column passes the question to its output field, which is its field for a column a filter makes, and a transform answers from its own registry and then from its output field's, and [The lookup registry: `RegisterLookupMixin`](../querysets/lookups.md) is where the answers come from (`django/db/models/query_utils.py:RegisterLookupMixin.get_lookup`, `django/db/models/expressions.py:BaseExpression.get_lookup`).

Each transform word goes to `Query.try_transform`, which asks the left side for a transform class of that name and, finding one, makes an instance of it with the left side as its argument (`django/db/models/sql/query.py:Query.try_transform`). The last word is first asked for as a lookup, so that a lookup takes precedence where a name is registered as both; where no lookup answers, the word is tried as a transform instead and the lookup becomes `"exact"`, which is how `filter(name__lower="ada")` compares `"LOWER"` of the column once `Lower` is registered on `CharField`, as the recording registers it. Then the lookup class is instantiated with the left side and the value, and the lookup prepares the value for its left side's type as it is made ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)). The classes a filter finds this way are those of `django/db/models/lookups.py` and of the functions registered as transforms ([Transforms and database functions: `Transform` and `Func`](functions.md)). Django registers none of `Lower`, `Length` and `Upper` on a field class; the recording had registered the three on `CharField` before these lines (`django/db/models/functions/text.py`, `django/db/models/fields/__init__.py:CharField`).

```text recording=sql
sql_of(Sailor.objects.filter(name__lower='ada'))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE LOWER("crew_sailor"."name") = %s', ('ada',))
sql_of(Sailor.objects.filter(name__lower__startswith='a'))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE LOWER("crew_sailor"."name") LIKE %s ESCAPE \'\\\'', ('a%',))
sql_of(Sailor.objects.filter(name__upper__lower__length__gt=2))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE LENGTH(LOWER(UPPER("crew_sailor"."name"))) > %s', (2,))
```

Where no transform answers either, `try_transform` raises `FieldError`, and the message is the same whichever way the word failed: a word that is neither a lookup nor a transform, a lookup written where a transform should stand, or a word after a field that is no relation, which `solve_lookup_type` leaves over as if it were a lookup. It names the class of the left side's output field, offers the closest names among the field's lookups, found by `difflib.get_close_matches`, and spells the unsupported name from the failing word to the end, so that it says `'exact__exact'` and not `'exact'`.

```text recording=sql
Sailor.objects.filter(name__exact__exact='ada')  ->  raises FieldError: Unsupported lookup 'exact__exact' for CharField or join on the field not permitted, perhaps you meant exact or iexact?
Sailor.objects.filter(signed_on__yaer=2011)  ->  raises FieldError: Unsupported lookup 'yaer' for DateTimeField or join on the field not permitted, perhaps you meant year?
Sailor.objects.filter(ship__contains=1)  ->  raises FieldError: Unsupported lookup 'contains' for ForeignKey or join on the field not permitted.
Sailor.objects.filter(name__ship='Ada')  ->  raises FieldError: Unsupported lookup 'ship' for CharField or join on the field not permitted.
```

**`None` as a value.** A lookup made with `None` on its right is refused with `ValueError` unless its class says it can take one through `can_use_none_as_rhs`, as `JSONExact` does (`django/db/models/fields/json.py:JSONExact`), with one exception: under `"exact"` and `"iexact"` the lookup is thrown away and an `"isnull"` lookup of the left side with `True` is returned in its place, which is what `filter(captain=None)` becomes. The empty string gets the same treatment on a backend whose features say it stores the empty string as null: an `"exact"` or `"iexact"` of `""` becomes that `"isnull"`, and the comment at that line says the check must be made here and not in the compiler, because join promotion cannot be done there, and that consulting the default connection is the best that can be done. A lookup on a relation's column finds a relation's `"isnull"`, `RelatedIsNull` ([Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](related-lookups.md)).

```text recording=sql
sql_of(Ship.objects.filter(captain=None)), entry(Ship.objects.filter(captain=None))  ->  (('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."captain_id" IS NULL ORDER BY "fleet_ship"."name" ASC', ()), RelatedIsNull(Col(fleet_ship, fleet.Ship.captain), True))
tail(Ship.objects.filter(captain__exact=None)), tail(Ship.objects.filter(name__iexact=None))  ->  (('FROM "fleet_ship" WHERE "fleet_ship"."captain_id" IS NULL ORDER BY "fleet_ship"."name" ASC', ()), ('FROM "fleet_ship" WHERE "fleet_ship"."name" IS NULL ORDER BY "fleet_ship"."name" ASC', ()))
Ship.objects.filter(captain__gt=None)  ->  raises ValueError: Cannot use None as a query value
...
sql_of(Ship.objects.filter(name=''))  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s ORDER BY "fleet_ship"."name" ASC', ('',))
connection.features.interprets_empty_strings_as_nulls  ->  False
```

## `resolve_ref`: what an `F` finds

`Query.resolve_ref` is what an `F` becomes when it is resolved against a query: `F.resolve_expression` hands the name it carries to the query, and gets back an expression bound to a table (`django/db/models/sql/query.py:Query.resolve_ref`, `django/db/models/expressions.py:F.resolve_expression`). The name is first tried whole against the annotations. An annotation is returned as it is, which puts the annotation's expression in the place of the `F`; under `summarize=True`, which `get_aggregation` sets when it resolves the aggregates of an `aggregate` call, a `Ref` to the annotation is returned instead, and an annotation that is not selected, one made by `alias`, is refused, with an error that says to promote it with `annotate`. Where joins are not allowed, an annotation that holds a column of a joined table is refused too. Failing the whole name, the first word is tried as an annotation and the rest as transforms of it.

Otherwise the name is a path through the models, and `resolve_ref` calls `setup_joins` and `trim_joins` as `build_filter` does: it joins from the base table, trims, refuses any join where joins are not allowed, refuses a final field of several target columns, and applies the transform function to the one target at the alias the trimming settled, which makes the `Col`, or the `ColPairs` that a composite primary key's `get_col` makes, and wraps it in the transforms (`django/db/models/fields/__init__.py:Field.get_col`, `django/db/models/fields/composite.py:CompositePrimaryKey.get_col`). The aliases joined are added to the set of reusable aliases where the caller gave one, and a later condition given the same set may reuse them. What the `F` and the `Col` are as expressions, and what `Query.resolve_lookup_value` does with an `F` on the right of a filter, is [Expressions: `resolve_expression` and `as_sql`](expressions.md).

```text recording=sql
resolve_ref: what an F finds under a name (Lower and Length being registered on CharField by this recording)
    Sailor.objects.all().query.resolve_ref('name')  ->  Col(crew_sailor, crew.Sailor.name)
    Sailor.objects.all().query.resolve_ref('ship'), Sailor.objects.all().query.resolve_ref('ship__name')  ->  (Col(crew_sailor, crew.Sailor.ship), Col(fleet_ship, fleet.Ship.name))
    Sailor.objects.all().query.resolve_ref('name__lower'), Sailor.objects.all().query.resolve_ref('name__lower__length')  ->  (Lower(Col(crew_sailor, crew.Sailor.name)), Length(Lower(Col(crew_sailor, crew.Sailor.name))))
    Sailor.objects.annotate(hands=Count('pk')).query.resolve_ref('hands')  ->  Count(Col(crew_sailor, crew.Sailor.id))
    Sailor.objects.annotate(hands=Count('pk')).query.resolve_ref('hands', summarize=True)  ->  Ref(hands, Count(Col(crew_sailor, crew.Sailor.id)))
    Sailor.objects.alias(hands=Count('pk')).query.resolve_ref('hands', summarize=True)  ->  raises FieldError: Cannot aggregate over the 'hands' alias. Use annotate() to promote it.
    Sailor.objects.all().query.resolve_ref('ship__name', allow_joins=False)  ->  raises FieldError: Joined field references are not permitted in this query
    Berth.objects.all().query.resolve_ref('pk')  ->  ColPairs('office_berth', (<django.db.models.fields.related.ForeignKey: port>, <django.db.models.fields.PositiveSmallIntegerField: number>), (<django.db.models.fields.related.ForeignKey: port>, <django.db.models.fields.PositiveSmallIntegerField: number>), <django.db.models.fields.composite.CompositePrimaryKey: pk>)
    Sailor.objects.all().query.resolve_ref('pilots_into')  ->  Col(office_licence, office.Licence.port)
```

A relation's own name resolves to the key column on the near side, after trimming, and `"pilots_into"` to the port's key on the table between, the step to the port having been taken back. The two refusals are an alias that is not selected, asked for under `summarize=True`, and a join where none is allowed.

## A field the parent holds

A child model with a table of its own keeps the fields it declares there, and inherits the rest from its parent's table. `names_to_path` notices, at each word, that the field it found belongs to a model other than the one it is reading, and asks the options for the path to that model: `Options.get_path_to_parent` returns a `PathInfo` for each parent link on the way, made along the one-to-one field that is the link, and none for a proxy, which has no table of its own (`django/db/models/options.py:Options.get_path_to_parent`). The steps go into the path ahead of whatever the field adds, and the walk goes on from the parent's options. So a filter on the name of an Officer joins the sailors' table and compares its column, and a filter on a Veteran, a proxy of Sailor, joins nothing. The other direction, from a parent to its child, is a reverse step over the same link: `"officer__rank"` asked of a sailor.

```text recording=sql
sql_of(Officer.objects.filter(name='Cora'))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "crew_officer"."sailor_ptr_id", "crew_officer"."rank" FROM "crew_officer" INNER JOIN "crew_sailor" ON ("crew_officer"."sailor_ptr_id" = "crew_sailor"."id") WHERE "crew_sailor"."name" = %s', ('Cora',))
sql_of(Sailor.objects.filter(officer__rank='master'))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "crew_officer" ON ("crew_sailor"."id" = "crew_officer"."sailor_ptr_id") WHERE "crew_officer"."rank" = %s', ('master',))
sql_of(Veteran.objects.filter(name='Ada'))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE ("crew_sailor"."signed_on" < %s AND "crew_sailor"."name" = %s)', ('2020-01-01 00:00:00', 'Ada'))
...
Officer.objects.all().query.get_meta() is Officer._meta, said(Officer._meta.get_path_to_parent(Sailor)), Officer._meta.get_base_chain(Sailor), Veteran._meta.get_path_to_parent(Sailor)  ->  (True, [PathInfo(from Officer to Sailor via Officer.sailor_ptr, direct, one)], [<class 'harbour.crew.models.Sailor'>], [])
```

`Query.join_parent_model` serves the callers that have a model and an alias rather than a name: given the options to start from, a model and the alias of the child's table, it follows `Options.get_base_chain` to the model, joins each link on the way with `setup_joins` on the link field's name, skipping a proxy, and returns the alias of the parent's table, writing each alias it joined into a dictionary the caller passes, from model to alias, which answers for a second field of the same parent without joining again (`django/db/models/sql/query.py:Query.join_parent_model`, `django/db/models/options.py:Options.get_base_chain`). The compiler's `get_default_columns` calls it for each column a parent holds, which is why the statements of an Officer in the recording select the sailor's columns through a join of the sailors' table ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)). What a parent link is, and how the base chain is kept, is [Inheritance: abstract bases, parents with tables and proxies](../models/inheritance.md).

## The walk elsewhere

`Query.names_to_path`, `Query.setup_joins` and `Query.trim_joins` read every name a queryset is given, and each caller walks the name itself because it wants something else of the column at the end: a filter a comparison of it, `values` the column selected, an ordering the column or, where the name ends at a relation, that model's own ordering in its place. `Query.add_fields`, which `Query.set_values` calls with the names `values` was given and a lookup calls with `["pk"]` when a queryset is its value, has `setup_joins` and `trim_joins` walk each name and applies the transform function to the target, so that a name with a transform in it selects the transformed column ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)); where it is asked to forbid a step marked many and the walk raises `MultiJoin`, it refuses the name (`django/db/models/sql/query.py:Query.add_fields`). The compiler's `find_ordering_name` walks an ordering's name the same way when the statement is written, and takes the related model's own ordering where the name ends at a relation to a model that declares one, is not `"pk"` or the key's attname, and carries no transform ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)). Both split the name through `Query.get_names_to_join`, which keeps a name whole where it is the alias of a filtered relation, so that an alias holding `"__"` is not read as a path (`django/db/models/sql/query.py:Query.get_names_to_join`). `Query.add_filtered_relation` uses `solve_lookup_type` to check that the names in a relation's condition stay within the relation ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)).
