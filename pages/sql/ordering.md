---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`

A statement's `"ORDER BY"` comes from one of three places on the query, `Query.extra_order_by`, `Query.order_by` or the model's own ordering, in that precedence; `SQLCompiler._order_by_pairs` turns each item into an `OrderBy`, `SQLCompiler.find_ordering_name` follows a relation in a name to the related model's ordering, and `SQLCompiler.get_order_by` resolves, deduplicates and compiles them. `SQLCompiler.get_distinct` writes the columns of a `"DISTINCT ON"`, and `SQLCompiler.get_extra_select` adds to the select list what a plain `"DISTINCT"` needs the ordering's columns for.

An ordering reaches the query in three forms. `QuerySet.order_by` leaves names and expressions; `QuerySet.extra` may leave strings of SQL; and a model may have an ordering of its own, in its `Meta`, that holds unless something says otherwise. So the compiler has to choose among the three by a fixed rule, and then make of each item the one thing SQL takes, a column or an expression and a direction. An item that names a relation, `"-ship"`, has no column of its own to order by: the related model's ordering is to be brought in under it, with its direction, as deep as the relations go. An item that names something the statement selects under an alias is written as that column's position in the select list rather than as the column again, and a compound statement, whose parts' columns cannot be named from outside, refers to a column by its alias or adds one to every part. And there are places where an ordering would be wrong, or would change what the statement means, and it has to be dropped: a model's ordering under a `"GROUP BY"`, the ordering of a query that has become a subquery, the ordering of a query whose rows are to be counted. The source is `django/db/models/sql/compiler.py:SQLCompiler.get_order_by` and the methods around it; on the query's side, `django/db/models/sql/query.py:Query.add_ordering` and its neighbours.

The recording this section quotes was made from a running Django, on SQLite, over the models of the chapter's opening page: each line is a question put to the running Django and its answer after `->`, or the exception it raised; a line with nothing after it is Python that was run for a later line's sake; and in the one block of calls, the lines are calls nested as they were made, with only the calls the passage is about written down, and `->` what a call returned. A question that begins with tail shows the queryset's statement from its `"FROM"` on, with the select list and its parameters left out, and the parameters of the rest.

## What the query keeps

Four attributes of the query are the ordering's, and each is a class attribute until a method sets it on the instance (`django/db/models/sql/query.py:Query`). `Query.order_by` is a tuple of what `QuerySet.order_by` was given, empty on a new query. `Query.extra_order_by` is what `QuerySet.extra` was given as its `order_by`, a list of strings, stored as it was given by `Query.add_extra` where it has anything (`django/db/models/sql/query.py:Query.add_extra`). `Query.default_ordering` says whether the model's own ordering is to be used where the first two are empty, and is `True` on a new query. `Query.standard_ordering` says whether each direction is to be taken as written or reversed, `True` on a new query, and `QuerySet.reverse` flips it (`django/db/models/query.py:QuerySet.reverse`).

```text recording=sql
tail(Ship.objects.all()), Ship._meta.ordering, Ship.objects.all().query.order_by, Ship.objects.all().query.default_ordering  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()), ['name'], (), True)
tail(Ship.objects.order_by('tonnage')), Ship.objects.order_by('tonnage').query.order_by  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" ASC', ()), ('tonnage',))
tail(Ship.objects.order_by()), Ship.objects.order_by().query.order_by, Ship.objects.order_by().query.default_ordering  ->  (('FROM "fleet_ship"', ()), (), False)
```

A ship's model orders by name. The first line is a queryset that was given no ordering: `order_by` is empty, `default_ordering` holds, and the statement orders by the model's. The second was given one. The third was given `order_by()` with nothing: `order_by` is empty still, `default_ordering` is `False`, and the statement has no `"ORDER BY"`.

`QuerySet.order_by` replaces the ordering rather than adding to it: on the clone it calls `Query.clear_ordering` with `force=True` and `clear_default=False`, which empties `order_by` and `extra_order_by` whatever the query holds and leaves `default_ordering` as it was, and then `Query.add_ordering` with its arguments (`django/db/models/query.py:QuerySet.order_by`). What the method does on the queryset's side, and the two properties that report on an ordering, `QuerySet.ordered` and `QuerySet.totally_ordered`, are told in [Annotations, ordering and the other methods that change the query](../querysets/methods.md).

`Query.add_ordering` looks at each item as it takes it, and three things are refused there rather than left for the compiler (`django/db/models/sql/query.py:Query.add_ordering`). A string that is `"?"` is passed; any other string has a leading `"-"` taken off and is accepted if it names an annotation of the query or a column of `Query.extra`, and otherwise its words are handed to `Query.names_to_path`, which raises `FieldError` for a first word that is no field, with the choices, and leaves a later word it cannot read for the compiler ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). Something that is neither a string nor an expression is collected and refused at the end with `FieldError`. And an expression whose `contains_aggregate` is true is refused with `FieldError` on its own: an aggregate in an ordering has to be an annotation first. With items, the method appends them to `order_by`; with none at all, it sets `default_ordering` to `False`, and that is the whole of what `order_by()` with no arguments leaves.

```text recording=sql
Ship.objects.order_by('cargo')  ->  raises FieldError: Cannot resolve keyword 'cargo' into field. Choices are: captain, captain_id, crew, home, home_id, id, name, tonnage, voyage
Ship.objects.order_by(Count('crew'))  ->  raises FieldError: Using an aggregate in order_by() without also including it in annotate() is not allowed: Count(F(crew))
Ship.objects.order_by(5)  ->  raises FieldError: Invalid order_by arguments: [5]
```

`Query.clear_ordering` has two switches (`django/db/models/sql/query.py:Query.clear_ordering`). Unless `force=True`, it does nothing to a query that is sliced, has distinct fields or has `Query.select_for_update` set, returning without a word: the docstring says that the ordering is removed where the query allows it without side effects. Otherwise it empties `order_by` and `extra_order_by`, and sets `default_ordering` to `False` unless called with `clear_default=False`, which leaves `default_ordering` as it was. Last it calls itself on each query in `Query.combined_queries`, without force and passing its second switch on, so that a `clear_default=True` reaches the parts of a compound query; the comment says that the parts had their orderings cleared with `clear_default=False` when `union` and its relatives were called ([Two queries into one: `combine` and `get_combinator_sql`](combining.md)).

```text recording=sql
clear_ordering: refused without force where the query is sliced, as here, or has distinct fields or a lock; and clear_default decides whether Meta.ordering comes back
    sliced = Ship.objects.order_by('tonnage')[:1].query
    sliced.clear_ordering()
    sliced.order_by, sliced.default_ordering  ->  (('tonnage',), True)
    sliced.clear_ordering(force=True)
    sliced.order_by, sliced.default_ordering, tail(Ship.objects.order_by('tonnage')[:1])  ->  ((), False, ('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" ASC LIMIT 1', ()))
    kept = Ship.objects.order_by('tonnage').query
    kept.clear_ordering(clear_default=False)
    kept.order_by, kept.default_ordering  ->  ((), True)
```

The query called sliced is a sliced one: after `clear_ordering()` its ordering is as it was, and after `clear_ordering(force=True)` it is gone, `default_ordering` with it; the statement beside them is a fresh queryset's, ordered by tonnage and sliced to one row, and keeps its `"ORDER BY"` with its limit. The query called kept, unsliced, is cleared with `clear_default=False`: `order_by` emptied, and the default standing.

## The three sources and the direction

`SQLCompiler._order_by_pairs` is a generator that yields, for each item of the ordering, an `OrderBy` and a flag saying whether it refers to the select list (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`). It first chooses the source. `Query.extra_order_by` is taken where it has anything; failing that, `Query.order_by` where `Query.default_ordering` is off, whether or not it has anything; failing that, `Query.order_by` where it has anything; failing that, the model's `Options.ordering`, which the compiler notes by keeping it in `_meta_ordering`, so that the other clauses can tell that the ordering is the model's and not the query's; and failing all four, nothing (`django/db/models/options.py:Options`). The second step says that `order_by()` with no arguments beats the model's ordering by turning `default_ordering` off, not by emptying anything.

Since `QuerySet.order_by` clears `extra_order_by` on its way, the two are both set where `extra` was called after `order_by`, and then the extra ordering wins; called the other way round, `order_by` has cleared it:

```text recording=sql
tail(Ship.objects.order_by('name').extra(order_by=['tonnage'])), Ship.objects.order_by('name').extra(order_by=['tonnage']).query.extra_order_by, tail(Ship.objects.extra(order_by=['tonnage']).order_by('name'))  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" ASC', ()), ['tonnage'], ('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()))
```

Then the direction. `Query.standard_ordering` chooses between the two rows of `ORDER_DIR`, a table of `django/db/models/sql/constants.py` that gives for `"ASC"` the pair `("ASC", "DESC")` and for `"DESC"` the reverse (`django/db/models/sql/constants.py:ORDER_DIR`). The first of the pair is the direction of a name with no sign, the second of a name with `"-"`, which is what `get_order_dir`, a function of the query's module, returns for a name (`django/db/models/sql/query.py:get_order_dir`). So under `reverse` a plain name is descending and a signed one ascending, and an expression that is an `OrderBy` is copied and reversed with `OrderBy.reverse_ordering`.

```text recording=sql
tail(Ship.objects.reverse()), Ship.objects.reverse().query.standard_ordering, tail(Ship.objects.order_by('-tonnage', 'name').reverse())  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."name" DESC', ()), False, ('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" ASC, "fleet_ship"."name" DESC', ()))
```

## What each item becomes

Before the items, `_order_by_pairs` reads the select list, which `SQLCompiler.setup_query` has settled already, into a dictionary from each selected expression, and from each alias, to a `PositionRef`: a `Ref` that holds the column's position in the select list, counted from one, and writes that number as its SQL (`django/db/models/sql/compiler.py:PositionRef`). An expression selected at two positions is given the first, where the query has distinct fields: the comment says that `get_distinct` refers to such a selection by expression, and that PostgreSQL binds a reference to the first position an expression is selected at, so the ordering must refer to that position too for the two clauses to begin alike; a `RawSQL` is left out of that rule, equal SQL not being interchangeable. An annotation's alias is bound to its own position. The dictionary is built only where there is an ordering and a select list, the comment calling it relatively expensive.

| an item of the ordering | what `_order_by_pairs` yields |
|---|---|
| an expression, `Lower("name")` or `F("tonnage").desc(nulls_last=True)` | the expression as an `OrderBy`, through `asc()` where it is not one already, reversed where `standard_ordering` is off; a `Value` first wrapped in a `Cast` to its own output field |
| an expression that is selected, or an `F` of a selected alias | the same, with the `PositionRef` of its place as the expression and the flag set, apart from the two exceptions told below the table |
| `"?"` | `OrderBy(Random())`, ascending, never reversed |
| the alias of a selected column, which `values` gives, or of a selected annotation | an `OrderBy` of the `PositionRef` of its place, and the flag set |
| an annotation's alias that is not selected, or one with transforms after it, `"hands"` or `"low__length"` | the annotation's own expression, each transform applied by `Query.try_transform`; a `Value` cast as above; under a combinator an `F` of the alias instead, and transforms refused with `NotImplementedError` |
| `"table.column"` given to `extra(order_by=...)` | a `RawSQL` of the quoted table and the column, as written |
| the name of an extra select | a `Ref` to it where it is selected, with the flag set; the `RawSQL` itself where it is not |
| any other name, under a combinator | `OrderBy(F(name))`, to be resolved against each part |
| a field's name, through relations and with transforms, `"-ship__name__lower"` | what `find_ordering_name` returns, one `OrderBy` or several |

*Each form an item of the ordering can take, in the order `_order_by_pairs` tests for them, and what it yields: an `OrderBy`, and whether the `OrderBy` refers to the select list. The flag is what `get_order_by` and `get_extra_select` read to know that no column need be added for the item.*

```text recording=sql
tail(Ship.objects.order_by('-name', 'home__country'))  ->  ('FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") ORDER BY "fleet_ship"."name" DESC, "fleet_port"."country" ASC', ())
tail(Ship.objects.order_by('?'))  ->  ('FROM "fleet_ship" ORDER BY RAND() ASC', ())
tail(Ship.objects.order_by(Lower('name'))), tail(Ship.objects.order_by('name__lower'))  ->  (('FROM "fleet_ship" ORDER BY LOWER("fleet_ship"."name") ASC', ()), ('FROM "fleet_ship" ORDER BY LOWER("fleet_ship"."name") ASC', ()))
tail(Ship.objects.order_by(F('tonnage').desc(nulls_last=True))), tail(Ship.objects.order_by(F('captain').asc(nulls_first=True)))  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" DESC NULLS LAST', ()), ('FROM "fleet_ship" ORDER BY "fleet_ship"."captain_id" ASC NULLS FIRST', ()))
tail(Ship.objects.annotate(hands=Count('crew')).order_by('-hands')), tail(Ship.objects.alias(hands=Count('crew')).order_by('hands'))  ->  (('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" ORDER BY 6 DESC', ()), ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" ORDER BY COUNT("crew_sailor"."id") ASC', ()))
tail(Ship.objects.order_by(Value('x')))  ->  ('FROM "fleet_ship" ORDER BY CAST(%s AS text) ASC', ('x',))
```

The lines are, in turn: two names, one through a relation, each a column with a direction; `"?"`, which SQLite writes as `"RAND()"`, a function Django registers with it, where `Random.function` is `"RANDOM"` and MySQL and Oracle are given a name each (`django/db/models/functions/math.py:Random`); an expression, and the same transform reached by a name, which come to the same column; two expressions with a nulls modifier each; an annotation that is selected, written by its position, 6, and one that `alias` kept out of the select list, written out in full; and a `Value`, cast to its type, as the comment says a constant must be for its output field to be resolved. The `"GROUP BY"` in the line with `annotate` and `alias` is the aggregate's doing ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md)). The two names in the first of the lines are columns the model selects by default, and such a column has no alias, so a name finds no position for it and the column is written in full; a position is written for a column `values` named, or for an annotation.

The two exceptions are in the selected expression's row. An `F` is matched against the dictionary by its name as well as by itself, so that `order_by(F("name"))` finds the position of a `"name"` that `values` selected; and the position is passed over where it would break the emulation of a nulls modifier: the comment says that emulating `"NULLS FIRST"` or `"NULLS LAST"` cannot be combined with ordering by position, so where the backend lacks the modifier and the `OrderBy` asks for one the expression is kept, and under a combinator, where the expression could not be written at all, a `Ref` to the position's alias is used instead, alias collisions being impossible there. A third stands in the annotation's row: under a combinator the alias is wrapped in an `F` rather than replaced by the resolved annotation, the comment saying that another part may define the alias differently.

## `find_ordering_name`: a relation brings its model's ordering

`SQLCompiler.find_ordering_name` takes a name of the ordering, the options to start from, the alias to start from, the default direction and the set of joins seen, the alias and the set given only on a recursive call (`django/db/models/sql/compiler.py:SQLCompiler.find_ordering_name`). It reads the direction off the name with `get_order_dir`, splits the name with `Query.get_names_to_join`, which keeps a filtered relation's alias whole, and hands the words to `SQLCompiler._setup_joins`, a wrapper of `Query.setup_joins` that starts from the base table where no alias was given and answers with the last join's alias (`django/db/models/sql/compiler.py:SQLCompiler._setup_joins`). The joins are made now, during compiling, and are among the tables `get_from_clause` writes; their reference counts are put back when the statement is done ([Tables and joins: the alias map and join promotion](joins.md)).

```text recording=sql
find_ordering_name: an ordering by a relation becomes the related model's Meta.ordering, prefixed with the relation's name (Lower being registered on CharField by this recording)
    tail(Sailor.objects.order_by('ship'))  ->  ('FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") ORDER BY "fleet_ship"."name" ASC', ())
    tail(Sailor.objects.order_by('-ship'))  ->  ('FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") ORDER BY "fleet_ship"."name" DESC', ())
    tail(Sailor.objects.order_by('ship_id')), tail(Sailor.objects.order_by('ship__pk'))  ->  (('FROM "crew_sailor" ORDER BY "crew_sailor"."ship_id" ASC', ()), ('FROM "crew_sailor" ORDER BY "crew_sailor"."ship_id" ASC', ()))
    tail(Voyage.objects.order_by('ship__home'))  ->  ('FROM "fleet_voyage" INNER JOIN "fleet_ship" ON ("fleet_voyage"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") ORDER BY "fleet_port"."name" ASC', ())
    tail(Sailor.objects.order_by('ship__name__lower'))  ->  ('FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") ORDER BY LOWER("fleet_ship"."name") ASC', ())
    tail(Ship.objects.order_by('captain'))  ->  ('FROM "fleet_ship" ORDER BY "fleet_ship"."captain_id" ASC', ())
    tail(Licence.objects.order_by('port', 'sailor'))  ->  ('FROM "office_licence" INNER JOIN "fleet_port" ON ("office_licence"."port_id" = "fleet_port"."id") ORDER BY "fleet_port"."name" ASC, "office_licence"."sailor_id" ASC', ())
```

Then one test decides between two endings. The ending the comment calls the default is to order by the related model's ordering: where the final field is a relation, and the related model's options have an ordering, and the last word is not the field's attname, and the name is not `"pk"`, and no transform was applied, the method does not order by the key column at all. It takes each item of the related model's `Options.ordering` (`django/db/models/options.py:Options`): a name it calls itself with, starting from the joined alias and with its own direction as the default, so that `"-ship"` orders by the ship's name descending, as the line with `'-ship'` shows; an expression is given the direction with `asc()` or `desc()`, and one that is an `OrderBy` already is kept, and neither recurses. What comes back is prefixed: `BaseExpression.prefix_references` makes a copy in which every `F` has the relation's name and `"__"` put before its own, so that an `F("name")` in the ship's ordering becomes `F("ship__name")` and resolves from the sailor (`django/db/models/expressions.py:BaseExpression.prefix_references`). A name that reaches a relation through others ends the same way, as the voyage ordered by `"ship__home"` shows, by the port's name; and a model whose ordering names a relation whose model's ordering names one in turn is followed through as many as there are. The guard against going round in a circle is the set of joins seen: before it recurses, the method records the `join_cols` of the joins it made, and raises `FieldError` on meeting the same joins again.

The exceptions are the lines that name a column. `"ship_id"` is the attname, and `"ship__pk"` ends at the key field, which is no relation, so each orders by the key column and the statement has no join; `"ship__name__lower"` has a transform, so it orders by the transformed column; and `"pk"` is kept from the default ending by name, the comment calling it the pk shortcut.

The other ending is the plain one: `Query.trim_joins` takes back the joins a key already held, and for each target column the method yields one `OrderBy` of the column, through the transform function, with the direction (`django/db/models/sql/query.py:Query.trim_joins`). A composite key has several targets and yields several.

```text recording=sql
tail(Ship.objects.order_by('pk')), tail(Ship.objects.order_by('home_id')), tail(Ship.objects.order_by('home__pk'))  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."id" ASC', ()), ('FROM "fleet_ship" ORDER BY "fleet_ship"."home_id" ASC', ()), ('FROM "fleet_ship" ORDER BY "fleet_ship"."home_id" ASC', ()))
```

A ship's `"home"` and `"captain"` are relations too. `order_by("home__pk")` ends at the key; `order_by("captain")` would follow the relation, but a sailor's model has no ordering, so it comes to the key column, which the block above shows for a licence's `"sailor"` beside its `"port"`.

The whole, recorded for a queryset of sailors ordered by `"-ship"` and then `"name"`, is the block of calls this section has:

```text recording=sql
get_order_by for Sailor.objects.order_by('-ship', 'name'): find_ordering_name follows the relation and comes back with the ship's own ordering
    compiler = Sailor.objects.order_by('-ship', 'name').query.get_compiler('default')
    compiler.pre_sql_setup()
      SQLCompiler.compile(Col(crew_sailor, crew.Sailor.id))  ->  ('"crew_sailor"."id"', ())
      SQLCompiler.compile(Col(crew_sailor, crew.Sailor.name))  ->  ('"crew_sailor"."name"', ())
      SQLCompiler.compile(Col(crew_sailor, crew.Sailor.ship))  ->  ('"crew_sailor"."ship_id"', ())
      SQLCompiler.compile(Col(crew_sailor, crew.Sailor.signed_on))  ->  ('"crew_sailor"."signed_on"', ())
      SQLCompiler.get_order_by
        SQLCompiler.find_ordering_name(name='-ship', opts=the options of Sailor)
          Query.setup_joins(names=['ship'], alias='crew_sailor')  ->  JoinInfo(final_field=Sailor.ship, targets=(Ship.id,), opts=the options of Ship, joins=['crew_sailor', 'fleet_ship'], path=[PathInfo(from Sailor to Ship via Sailor.ship, direct, one)])
          SQLCompiler.find_ordering_name(name='name', opts=the options of Ship, alias='fleet_ship', default_order='DESC')
            Query.setup_joins(names=['name'], alias='fleet_ship')  ->  JoinInfo(final_field=Ship.name, targets=(Ship.name,), opts=the options of Ship, joins=['fleet_ship'], path=[])
            Query.trim_joins(targets=(Ship.name,), joins=['fleet_ship'], path=[])  ->  ((Ship.name,), 'fleet_ship', ['fleet_ship'])
            -> [OrderBy(Col(fleet_ship, fleet.Ship.name), descending=True)]
          -> [OrderBy(Col(fleet_ship, fleet.Ship.name), descending=True)]
        SQLCompiler.compile(OrderBy(Col(fleet_ship, fleet.Ship.name), descending=True))
          SQLCompiler.compile(Col(fleet_ship, fleet.Ship.name))  ->  ('"fleet_ship"."name"', ())
          -> ('"fleet_ship"."name" DESC', ())
        SQLCompiler.find_ordering_name(name='name', opts=the options of Sailor)
          Query.setup_joins(names=['name'], alias='crew_sailor')  ->  JoinInfo(final_field=Sailor.name, targets=(Sailor.name,), opts=the options of Sailor, joins=['crew_sailor'], path=[])
          Query.trim_joins(targets=(Sailor.name,), joins=['crew_sailor'], path=[])  ->  ((Sailor.name,), 'crew_sailor', ['crew_sailor'])
          -> [OrderBy(Col(crew_sailor, crew.Sailor.name), descending=False)]
        SQLCompiler.compile(OrderBy(Col(crew_sailor, crew.Sailor.name), descending=False))
          SQLCompiler.compile(Col(crew_sailor, crew.Sailor.name))  ->  ('"crew_sailor"."name"', ())
          -> ('"crew_sailor"."name" ASC', ())
        -> ['"fleet_ship"."name" DESC', '"crew_sailor"."name" ASC']
```

The first name made the join to the ship's table and came back with the ship's ordering under it, `"name"` descending; the second stayed on the sailor's own table.

## `get_order_by`: resolving, a compound statement and the duplicates

`SQLCompiler.get_order_by` takes what `_order_by_pairs` yields and returns a list of pairs, each the resolved `OrderBy` and a tuple of its SQL, its parameters and the flag (`django/db/models/sql/compiler.py:SQLCompiler.get_order_by`). Each `OrderBy` is resolved against the query with `allow_joins=True`, which is where an `F` becomes a column, joining tables as it goes: the docstring says that the ordering can alter the select clause, adding aliases or whole new columns, and that is what the next paragraph is about.

A compound statement cannot order by a column of one part. Where the query has a combinator and a select list, and the `OrderBy` does not refer to the select list already, `get_order_by` looks for the resolved expression among the selected ones and, finding it, makes the `OrderBy` refer to that column's alias with a `Ref`, `"col2"` for the second column of a statement whose columns were aliased for the compound, or the column's own name, with one exception the comment gives: under `values` an annotation is matched only by its exact alias, so an ordering that reached the same expression another way passes it by. Not finding it, the method adds the expression to every part as an annotation under `"__orderbycol"` and the column's number, with `Query.add_annotation`, and to the compound query with `Query.add_select_col`, and refers to that; a part that has select fields of its own, which `values` leaves, cannot be added to, and the method raises `DatabaseError` (`django/db/models/sql/query.py:Query.add_select_col`). The parts, and the `"SELECT * FROM"` some backends need round a compound statement before its `"ORDER BY"`, are [Two queries into one: `combine` and `get_combinator_sql`](combining.md).

```text recording=sql
sql_of(old.union(on_petrel).order_by('name'))  ->  ('SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."id" AS "col1", "crew_sailor"."name" AS "col2", "crew_sailor"."ship_id" AS "col3", "crew_sailor"."signed_on" AS "col4" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY "col2" ASC', ('2020-01-01 00:00:00', 1))
...
sql_of(old.values('name').union(on_petrel.values('name')).order_by('name'))  ->  ('SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s UNION SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s ORDER BY 1 ASC', ('2020-01-01 00:00:00', 1))
old.values('name').union(on_petrel.values('name')).order_by('id')  ->  raises DatabaseError: ORDER BY term does not match any column in the result set.
```

Here old and on_petrel are two querysets of sailors, the one of those who signed on before 2020 and the other of the Petrel's crew. In the first statement the union selects every column under an alias, and the ordering refers to the name's; in the second each part selects the name alone, which `_order_by_pairs` found selected and wrote by position; in the third, the parts select the name and the ordering asks for the key, which cannot be added to a part with select fields.

Then each `OrderBy` is compiled, and the duplicates are dropped. `SQLCompiler.ordering_parts` is a regular expression that takes the direction off the end of a compiled ordering; what is left, with the parameters made hashable, is kept in a set, and an item whose SQL is in the set already is skipped. The comment says what this means: the same column is not added twice, and the direction is not taken into account, so the second of `"name"` and `"-name"` is the one that goes (`django/utils/hashable.py:make_hashable`).

```text recording=sql
tail(Ship.objects.order_by('name', '-name', 'tonnage', 'tonnage'))  ->  ('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC, "fleet_ship"."tonnage" ASC', ())
```

## `OrderBy` as it is written

`OrderBy` is an expression of one source, with a direction and at most one nulls modifier, and its constructor refuses with `ValueError` both modifiers at once, either given as `False`, and a source that has no `resolve_expression` (`django/db/models/expressions.py:OrderBy`). `BaseExpression.asc` and `BaseExpression.desc`, and the same pair on `F`, make one of any expression, passing on `nulls_first=True` or `nulls_last=True`, and `OrderBy.asc` and `OrderBy.desc` set the direction of one that exists; `OrderBy.reverse_ordering` flips the direction and swaps the modifiers, and `BaseExpression.reverse_ordering` on anything else returns the expression as it is. What `OrderBy` shares with the other small expressions is told in [Expressions: `resolve_expression` and `as_sql`](expressions.md).

```text recording=sql
tail(Ship.objects.order_by(F('tonnage').desc(nulls_last=True))), tail(Ship.objects.order_by(F('captain').asc(nulls_first=True)))  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" DESC NULLS LAST', ()), ('FROM "fleet_ship" ORDER BY "fleet_ship"."captain_id" ASC NULLS FIRST', ()))
```

`OrderBy.as_sql` writes the template `"%(expression)s %(ordering)s"`, the compiled source and `"ASC"` or `"DESC"`, after it has settled the modifier by two features of the backend (`django/db/models/expressions.py:OrderBy.as_sql`). Where `supports_order_by_nulls_modifier` is on, `"NULLS LAST"` or `"NULLS FIRST"` is appended to the template, as the recorded line shows for SQLite. Where it is off, the modifier is emulated with a second ordering term put in front: `"%(expression)s IS NULL"` before the term for nulls last, so that the rows for which that test is true sort after those for which it is false, and `"IS NOT NULL"` for nulls first. The second feature, `order_by_nulls_first`, says where the backend puts nulls when nothing is said, and spares the emulation where the backend's own habit gives the answer: nulls last on a descending term where nulls come first by default, and nulls first on an ascending one. The source's parameters are repeated once for each `"%(expression)s"` in the template, since the emulation writes the expression twice (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_order_by_nulls_modifier`). Before compiling, the method has the operations object check the expression, and a source that is a `ColPairs`, a composite key, is written as one term for each of its columns, joined with commas. `OrderBy.as_oracle` has one more case: where the backend cannot select a boolean expression and the source is a condition, the condition is wrapped in a `Case` that yields true or false, the comment naming Oracle before 23c.

```text recording=sql
connection.features.allows_group_by_select_index, connection.features.supports_order_by_nulls_modifier, connection.features.order_by_nulls_first  ->  (True, True, True)
```

Of Django's own backends, MySQL alone sets `supports_order_by_nulls_modifier` off, and MySQL and SQLite set `order_by_nulls_first` on (`django/db/backends/mysql/features.py`, `django/db/backends/sqlite3/features.py`).

The block that line comes from is about ordering by position, and the rule is the dictionary's: what is selected under an alias is written as a number.

```text recording=sql
sql_of(Sailor.objects.order_by('signed_on').values_list('name'))  ->  ('SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" ORDER BY "crew_sailor"."signed_on" ASC', ())
sql_of(Sailor.objects.values_list('name').order_by('signed_on'))  ->  ('SELECT "crew_sailor"."name" AS "name" FROM "crew_sailor" ORDER BY "crew_sailor"."signed_on" ASC', ())
sql_of(Sailor.objects.values_list('name', 'signed_on').order_by('signed_on'))  ->  ('SELECT "crew_sailor"."name" AS "name", "crew_sailor"."signed_on" AS "signed_on" FROM "crew_sailor" ORDER BY 2 ASC', ())
sql_of(Sailor.objects.values_list('name').annotate(low=Lower('name')).order_by('low'))  ->  ('SELECT "crew_sailor"."name" AS "name", LOWER("crew_sailor"."name") AS "low" FROM "crew_sailor" ORDER BY 2 ASC', ())
sql_of(Sailor.objects.values_list('name').annotate(low=Lower('name')).order_by(Lower('name')))  ->  ('SELECT "crew_sailor"."name" AS "name", LOWER("crew_sailor"."name") AS "low" FROM "crew_sailor" ORDER BY 2 ASC', ())
sql_of(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('home'))  ->  ('SELECT "fleet_ship"."home_id" AS "home", COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1 ORDER BY 1 ASC', ())
```

The two statements that select the name alone and order by `"signed_on"` write the column in full, whichever way round the two methods were called; the one that selects both writes the position. The two with the annotation `"low"`, ordered by its alias and by its expression again, both find the position, since two expressions built the same way are equal whether or not one has been resolved. The grouped query ordered by `"home"` is by position in both clauses; the `"GROUP BY"`'s position is `get_group_by`'s doing, under a feature of its own, `allows_group_by_select_index`, which the block asked beside the two of `OrderBy`.

## `"DISTINCT"`: `get_distinct`, `distinct_sql` and the extra select

`QuerySet.distinct` leaves two things on the query through `Query.add_distinct_fields`: `Query.distinct` set to `True`, and `Query.distinct_fields` set to the names it was given, an empty tuple where it was given none (`django/db/models/sql/query.py:Query.add_distinct_fields`). The names are not read until the statement is written.

```text recording=sql
DISTINCT: an ordering by a column that is not selected adds the column, and DISTINCT ON is refused by SQLite's distinct_sql
    tail(Ship.objects.distinct()), Ship.objects.distinct().query.distinct, Ship.objects.distinct().query.distinct_fields  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()), True, ())
    sql_of(Ship.objects.distinct().order_by('home__country'))  ->  ('SELECT DISTINCT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "fleet_port"."country" FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") ORDER BY "fleet_port"."country" ASC', ())
    sql_of(Ship.objects.distinct().order_by('name'))  ->  ('SELECT DISTINCT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
    sql_of(Ship.objects.values('tonnage').distinct().order_by('name'))  ->  ('SELECT DISTINCT "fleet_ship"."tonnage" AS "tonnage", "fleet_ship"."name" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
    Ship.objects.distinct('name').query.distinct_fields, tail(Ship.objects.distinct('name'))  ->  raises NotSupportedError: DISTINCT ON fields is not supported by this database backend
    tail(Ship.objects.distinct().annotate(hands=Count('crew')).order_by('hands'))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" ORDER BY 6 ASC', ())
    Ship.objects.distinct().order_by('home__country').query.get_compiler('default').pre_sql_setup()[0]  ->  [(OrderBy(Col(fleet_port, fleet.Port.country), descending=False), ('"fleet_port"."country"', ()), None)]
```

`SQLCompiler.get_distinct` returns the compiled columns of `distinct_fields` and their parameters, and `as_sql` calls it in the plain branch before `get_from_clause`, the docstring saying why: the method can alter the tables of the query (`django/db/models/sql/compiler.py:SQLCompiler.get_distinct`). For each name it runs `_setup_joins` and `Query.trim_joins` as `find_ordering_name` does, the docstring of `_setup_joins` saying that the two must produce the same target columns for the same input, since the prefixes of the two clauses must match, and executing SQL where they do not is an error. Then, for each target, a name that is a selected annotation is written as its quoted alias; a name that is an annotation `alias` kept out of the select list is refused with `FieldError`, telling the caller to use `annotate` to promote it; and any other is compiled as the column through the transform function.

What the columns become is the backend's. `SQLCompiler.as_sql` hands them to `BaseDatabaseOperations.distinct_sql`, whose base form returns `["DISTINCT"]` for no fields and raises `NotSupportedError` for any, the message the question with `distinct('name')` shows; PostgreSQL's operations write `"DISTINCT ON (...)"` round the fields instead (`django/db/backends/base/operations.py:BaseDatabaseOperations.distinct_sql`, `django/db/backends/postgresql/operations.py:DatabaseOperations.distinct_sql`). The clause stands right after `"SELECT"`. And a query with distinct fields that also groups is refused by `as_sql` with `NotImplementedError`, its message saying that `annotate()` with `distinct(fields)` is not implemented (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`).

A plain `"DISTINCT"` has a cost the ordering pays. `SQLCompiler.get_extra_select` is called by `pre_sql_setup` with the ordering and the select list, and where the query is distinct and has no distinct fields it goes through the ordering and, for each `OrderBy` that does not refer to the select list and whose SQL, with the direction taken off, is not the SQL of a selected column, adds the expression to the select list with no alias (`django/db/models/sql/compiler.py:SQLCompiler.get_extra_select`). Those are the **extra select**: columns the statement selects for the ordering's sake, which `execute_sql` cuts off the rows before they are handed on, so that nothing of them reaches the queryset ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)). The question that asks `pre_sql_setup()` of a compiler, in the block above, shows such a column, returned as the first value for a distinct queryset ordered by the port's country: the ordering joined the port's table, and the country is selected beside the ship's own columns. The question that asks the whole statement of `distinct()` with `order_by('home__country')` shows the country selected last and with no alias; `distinct()` ordered by `"name"`, which the model selects already, adds nothing; `values('tonnage')` with `distinct()` ordered by the name adds the name after the one aliased column; and the ordering by `"hands"`, by position under `"DISTINCT"`, adds nothing, the flag being set.

> **Trap.** The documentation of `distinct` warns of what the extra select does to the rows: the columns of an `order_by`, or of the model's own ordering, are among those the database compares for duplicates, and an ordering by a related model can make rows distinct that would otherwise be one (`docs/ref/models/querysets.txt`).

Where such a query stands inside another, as a `Subquery` or, sliced, as the value of an `in`, the extra columns would make it return more columns than the comparison expects, and `as_sql` wraps the statement in one more `"SELECT"` of the query's own columns, the comment giving `order_by` with `distinct` as the case; [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md) has the wrap.

## Where an ordering is dropped

A model's ordering is left out of a statement that groups. `as_sql` sees `_meta_ordering` set, which `_order_by_pairs` sets only where the model's ordering was the source, and writes no `"ORDER BY"` where there is a `"GROUP BY"`; and `get_group_by` leaves the ordering's columns out of the grouping on the same sign, so that the model's ordering neither orders the groups nor adds columns to them. An ordering the query was given is kept in both (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.get_group_by`). [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md) has the grouping; the recorded query annotated with `"hands"` and ordered by it is an ordering kept.

A query that is aggregated over, counted or asked whether it has rows loses its ordering in a way that depends on what else it holds. `Query.get_aggregation` wraps the query as a subquery where it is sliced, distinct, grouped, combined or aggregated already, among other cases, and has the inner query's ordering cleared, without force, only where `Query.orderby_issubset_groupby` says it may (`django/db/models/sql/query.py:Query.orderby_issubset_groupby`, `django/db/models/sql/query.py:Query.get_aggregation`). The comment at the call says what an ordering is kept for: a query with distinct fields needs it, and a sliced one must take its slice from the ordered rows, and otherwise it is not needed; `clear_ordering` without force keeps it in those two cases by itself; the property decides the rest. It is `False` where there is an `extra_order_by`, the comment saying that raw SQL cannot reliably be compared with resolved expressions; `True` where the query does not group, or groups by all of the model's fields, or has no ordering; and otherwise resolves each item of `order_by` against a clone and answers whether the set of them is within the grouping, `"?"` making it `False` at once. An ordering within the grouping adds no column to the `"GROUP BY"`; one outside it would, since `get_group_by` takes the ordering's columns in, and it is kept. [Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md) has the rest.

```text recording=sql
orderby_issubset_groupby: whether an ordering can be dropped from the inner query of an aggregation
    Ship.objects.all().query.orderby_issubset_groupby, Ship.objects.values('home').annotate(n=Count('crew')).order_by('home').query.orderby_issubset_groupby, Ship.objects.values('home').annotate(n=Count('crew')).order_by('name').query.orderby_issubset_groupby  ->  (True, True, False)
    Ship.objects.values('home').annotate(n=Count('crew')).order_by('?').query.orderby_issubset_groupby, Ship.objects.extra(order_by=['x']).values('home').annotate(n=Count('crew')).query.orderby_issubset_groupby  ->  (False, False)
```

`Query.exists` clears the ordering by force, as `get_aggregation` does on the query it runs; a query given as the value of `in` has its ordering cleared, without force, by the lookup, so that a sliced one keeps it; and a query compiled as a subquery drops its ordering, without force, where the backend's `ignores_unnecessary_order_by_in_subqueries` is off, the comment naming Oracle, which raises an error on one, and keeps it where the feature is on, as the base features and SQLite's say, for the database to ignore ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md), `django/db/backends/base/features.py:BaseDatabaseFeatures.ignores_unnecessary_order_by_in_subqueries`). And `QuerySet._combinator_query` clears the ordering of the combined query by force, and of each other part without force, before it sets the combinator ([Combining querysets: the operators and `union`](../querysets/combining.md)).
