---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Lookups on relations and composite keys: `RelatedIn` and the tuple lookups

`ForeignObject` registers lookup classes of its own, `RelatedExact`, `RelatedIn`, `RelatedIsNull` and four comparisons, which take an instance, a key or a queryset on the right of a relation's name and compare the column that holds the key. `CompositePrimaryKey` registers `TupleExact`, `TupleIn` and their relatives, which compare several columns at once as a row value, or as a chain of one-column comparisons where the backend has no row values.

A comparison on a relation's name, `filter(ship=petrel)`, has to take whatever a program would naturally give for the ship: the instance, its key, the key as the string a URL carried, a queryset of ships, or a list that mixes these. What reaches the database is one column, `"ship_id"`, compared with one value or one subquery. So the lookups registered on a relation field do two things that the comparisons of an ordinary field do not: they turn an instance into its key, and they prepare the value through the field the key belongs to on the far side, not through the relation field itself. A comment gives the reason for the second: a foreign key to an integer field, given `"abc"`, has no validation of its own for what is not an integer, so the validation has to be the target field's (`django/db/models/fields/related_lookups.py:RelatedLookupMixin.get_prep_lookup`).

A key may be several columns. A model with a `CompositePrimaryKey` has one, and a relation that reaches such a model compares against one. The comparison is then between tuples, and SQL has a form for it, the row value `(a, b) = (x, y)`, which not every backend accepts in every position. Each tuple lookup therefore writes the row value where the backend's features allow it and a chain of one-column comparisons where they do not. The two halves of this page are those two families: the related lookups first, then the tuple lookups that the related ones hand a multi-column key to.

## Which field a relation's name asks

A lookup class is found by the left side of the comparison, a column whose output field is the field at the end of the path the name walked ([The lookup registry: `RegisterLookupMixin`](../querysets/lookups.md)). For a name that ends at a relation, that field is the `join_field` of the path's last step: the foreign key itself for a forward name such as `"ship"`, the rel for a reverse name such as `"crew"`, and for a many-to-many name the through model's foreign key to the far model, `"port"` of Licence for `"pilots_into"` (`django/db/models/sql/query.py:Query.names_to_path`). A rel passes `get_lookup` to its field (`django/db/models/fields/reverse_related.py:ForeignObjectRel.get_lookup`), so each of these ends at a `ForeignObject`, the class `ForeignKey` and `OneToOneField` are built on. The module registers seven classes on it after the class is defined (`django/db/models/fields/related.py`), and `ForeignObject.get_class_lookups` cuts the merge of the method resolution order off at `ForeignObject`, so that a relation answers to these seven and to none of the pattern or range comparisons a plain field has (`django/db/models/fields/related.py:ForeignObject.get_class_lookups`).

What follows was recorded from a running Django, on SQLite, over the shipping line of [From QuerySet to SQL](../sql.md): each line is a question and its answer after `->`, and a line that begins `SQL` is a statement as Django handed it to its cursor.

```text recording=sql
{name: cls.__name__ for name, cls in sorted(vars(ForeignObject)['class_lookups'].items())}  ->  {'exact': 'RelatedExact', 'gt': 'RelatedGreaterThan', 'gte': 'RelatedGreaterThanOrEqual', 'in': 'RelatedIn', 'isnull': 'RelatedIsNull', 'lt': 'RelatedLessThan', 'lte': 'RelatedLessThanOrEqual'}
```

The two lookups on `"pilots_into"` and on `"calls"` end at those through-model keys, the second through the table Django made for a relation declared without a through model:

```text recording=sql
entry(Sailor.objects.filter(pilots_into=bergen)), entry(Voyage.objects.filter(calls=bergen))  ->  (RelatedExact(Col(office_licence, office.Licence.port), 1), RelatedExact(Col(fleet_voyage_calls, fleet.Voyage_calls.port), 1))
```

Six of the seven have one shape: the comparison class of `django/db/models/lookups.py` with `RelatedLookupMixin` in front of it, `RelatedExact` on `Exact`, `RelatedIsNull` on `IsNull`, and `RelatedLessThan`, `RelatedGreaterThan`, `RelatedGreaterThanOrEqual` and `RelatedLessThanOrEqual` on their four (`django/db/models/fields/related_lookups.py:RelatedLookupMixin`). The mixin changes how the right side is prepared and what happens when the left side is several columns, and leaves the SQL to the parent ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)). `RelatedIn` is built on `In` directly and has the same two changes written for a list of values and for a queryset.

## `get_normalized_value`: an instance becomes its key

`get_normalized_value` is the function both the mixin and `RelatedIn` call on a value, and it returns a tuple (`django/db/models/fields/related_lookups.py:get_normalized_value`). A value that is not a model instance goes through untouched: a tuple as it is, anything else wrapped as a tuple of one. An instance is refused with `ValueError` unless its primary key is set, which `Model._is_pk_set` decides: a key of `None`, or one still holding a `DatabaseDefault`, or a composite key any part of which is either, is not set (`django/db/models/base.py:Model._is_pk_set`). The test is on the key and not on the row, so an instance made with `pk=1` and never saved passes it.

For an instance that passes, the function takes the target fields of the relation's last path step, with a composite key opened into its fields by `unnest` (`django/db/models/fields/composite.py:unnest`), and reads from the instance the attname of each. Where the instance is not of the target field's model and the target field is itself a relation, it follows that relation to the field it points at, and reads that one's attname instead: a parent's instance, given where the target is a child's parent link, is read as the parent's own key. Where the instance has no such attribute at all, the function gives up on the walk and returns the instance's `pk` as a tuple; the comment names the case, a one-to-one field that is its model's primary key, given an instance of that model.

```text recording=sql
entry(Sailor.objects.filter(ship=petrel)), entry(Sailor.objects.filter(ship=1)), entry(Sailor.objects.filter(ship='1'))  ->  (RelatedExact(Col(crew_sailor, crew.Sailor.ship), 1), RelatedExact(Col(crew_sailor, crew.Sailor.ship), 1), RelatedExact(Col(crew_sailor, crew.Sailor.ship), 1))
entry(Sailor.objects.filter(ship=petrel)).rhs, entry(Sailor.objects.filter(ship='1')).rhs, type(entry(Sailor.objects.filter(ship='1')).rhs).__name__  ->  (1, 1, 'int')
Sailor.objects.filter(ship='x')  ->  raises ValueError: Field 'id' expected a number but got 'x'.
Sailor.objects.filter(ship=Ship(name='Skua'))  ->  raises ValueError: Model instances passed to related filters must be saved.
```

The three values, the instance, the integer and the string, left the same lookup, and all three right sides are the integer 1: the string became an integer through the target field's `get_prep_value`, which is where `"x"` was refused in the words of an integer field. The last line is `get_normalized_value` refusing an instance that was never saved, on `_is_pk_set`'s word.

```text recording=sql
tail(Ship.objects.filter(captain=cora)), tail(Ship.objects.filter(captain=ada.pk))  ->  (('FROM "fleet_ship" WHERE "fleet_ship"."captain_id" = %s ORDER BY "fleet_ship"."name" ASC', (3,)), ('FROM "fleet_ship" WHERE "fleet_ship"."captain_id" = %s ORDER BY "fleet_ship"."name" ASC', (1,)))
entry(Sailor.objects.filter(officer=cora)), tail(Sailor.objects.filter(officer=cora))  ->  (RelatedExact(Col(crew_officer, crew.Officer.sailor_ptr), 3), ('FROM "crew_sailor" INNER JOIN "crew_officer" ON ("crew_sailor"."id" = "crew_officer"."sailor_ptr_id") WHERE "crew_officer"."sailor_ptr_id" = %s', (3,)))
entry(Sailor.objects.filter(ship__home=bergen)), entry(Ship.objects.filter(crew=ada))  ->  (RelatedExact(Col(fleet_ship, fleet.Ship.home), 1), RelatedExact(Col(crew_sailor, crew.Sailor.id), 1))
```

An Officer is a Sailor, so Cora given for the captain reads as her `"id"`, and given for the reverse one-to-one name `"officer"` reads as the `"sailor_ptr_id"` the child's table holds, the target of that reverse path being the child's primary key. The last line has a foreign key reached through another and a reverse foreign key: in both the lookup is the same `RelatedExact`, and for `"crew"` the column is the far table's `"id"`, since a reverse path's target is the far model's primary key (`django/db/models/fields/related.py:ForeignObject.get_reverse_path_info`). A proxy of the right model passes the type check and `_is_pk_set` alike, an unsaved one included:

```text recording=sql
tail(Ship.objects.filter(captain=Veteran(pk=1)))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."captain_id" = %s ORDER BY "fleet_ship"."name" ASC', (1,))
```

Whether the value is of a model the relation can take at all is decided before the lookup is built, by `Query.check_related_objects`, which refuses a Port given for a ship ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)).

## `RelatedLookupMixin`: one column, or a pair of columns

`RelatedLookupMixin.get_prep_lookup` does its work for a left side that is one column and a right side that is not an expression: it normalizes the value and takes the first element of the tuple, then, unless the lookup has switched preparation off, runs the target field's `get_prep_value` on it. The target field is the last of the target fields of the relation's last path step, which the comment says can safely be assumed to be one, since several would have made the left side a pair of columns and taken the other branch. Then the parent's preparation runs, ending in `Lookup.get_prep_lookup`, which prepares a direct value through the left side's output field where that has a `get_prep_value`: a foreign key's hands on to its target field, and a rel has none, so a value on the right of a reverse name is prepared once (`django/db/models/fields/related_lookups.py:RelatedLookupMixin.get_prep_lookup`, `django/db/models/fields/related.py:ForeignKey.get_prep_value`). `RelatedIsNull` is the one of the six whose parent has `prepare_rhs` off, so the `True` or `False` it is given is kept as it is (`django/db/models/lookups.py:IsNull`). The first line of the next quote shows it as the lookup `build_lookup` makes of `captain=None` ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)):

```text recording=sql
sql_of(Ship.objects.filter(captain=None)), entry(Ship.objects.filter(captain=None))  ->  (('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."captain_id" IS NULL ORDER BY "fleet_ship"."name" ASC', ()), RelatedIsNull(Col(fleet_ship, fleet.Ship.captain), True))
```

```text recording=sql
tail(Sailor.objects.filter(ship__gt=1)), tail(Sailor.objects.filter(ship__isnull=False))  ->  (('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" > %s', (1,)), ('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IS NOT NULL', ()))
```

The SQL is the parent's: `"ship_id" > %s` from `GreaterThan`, `"ship_id" IS NOT NULL` from `IsNull`.

The left side is a `ColPairs` when the key compared is several columns, and `RelatedLookupMixin.as_sql` is where that case is handled (`django/db/models/fields/related_lookups.py:RelatedLookupMixin.as_sql`). `Query.build_filter` makes a `ColPairs` for a relation whose trimmed targets are several, and a target that is a `CompositePrimaryKey` makes one of its own accord, since its `get_col` returns a `ColPairs` and not a `Col`: a reverse name that reaches a model with a composite key, `"berth"` on Port, compares against the pair `("port_id", "number")` (`django/db/models/sql/query.py:Query.build_filter`, `django/db/models/fields/composite.py:CompositePrimaryKey.get_col`). For such a left side `as_sql` refuses a right side that is an expression, with the message that the lookup does not support multi-column subqueries, normalizes the value into its tuple, builds the tuple lookup of the same name from the table `tuple_lookups`, and compiles that instead (`django/db/models/fields/tuple_lookups.py:tuple_lookups`). `ColPairs` itself, an expression that stands for several columns of one alias and writes them joined by commas, is [Expressions: `resolve_expression` and `as_sql`](expressions.md)'s.

```text recording=sql
entry(Port.objects.filter(berth=(1, 2)))  ->  RelatedExact(ColPairs('office_berth', (<django.db.models.fields.related.ForeignKey: port>, <django.db.models.fields.PositiveSmallIntegerField: number>), (<django.db.models.fields.related.ForeignKey: port>, <django.db.models.fields.PositiveSmallIntegerField: number>), <ManyToOneRel: office.berth>), (1, 2))
tail(Port.objects.filter(berth=(1, 2)))  ->  ('FROM "fleet_port" INNER JOIN "office_berth" ON ("fleet_port"."id" = "office_berth"."port_id") WHERE ("office_berth"."port_id", "office_berth"."number") = (%s, %s) ORDER BY "fleet_port"."name" ASC', (1, 2))
tail(Port.objects.filter(berth=Berth.objects.get(number=2)))  ->  ('FROM "fleet_port" INNER JOIN "office_berth" ON ("fleet_port"."id" = "office_berth"."port_id") WHERE ("office_berth"."port_id", "office_berth"."number") = (%s, %s) ORDER BY "fleet_port"."name" ASC', (1, 2))
  SQL SELECT "office_berth"."port_id", "office_berth"."number", "office_berth"."metres" FROM "office_berth" WHERE "office_berth"."number" = %s LIMIT 21 with params (2,)
...
tail(Port.objects.filter(berth__isnull=True))  ->  ('FROM "fleet_port" LEFT OUTER JOIN "office_berth" ON ("fleet_port"."id" = "office_berth"."port_id") WHERE ("office_berth"."port_id" IS NULL OR "office_berth"."number" IS NULL) ORDER BY "fleet_port"."name" ASC', ())
tail(Port.objects.filter(berth=Berth.objects.values('pk')[:1]))  ->  raises ValueError: 'exact' doesn't support multi-column subqueries.
```

The lookup is a `RelatedExact` whose left side is the `ColPairs` of the berths' two key columns, with the rel as its output field, and the statement compares the pair with the tuple as one row value; an instance given instead is read into the same tuple, after the statement that fetched it. The `"isnull"` reached `TupleIsNull` as a tuple of one boolean and was written as an `"OR"` over the two columns, and the queryset was refused.

## `RelatedIn`

A subquery under `"in"` has to yield the column the relation compares against: the far model's key, or, where the relation points at another column, that column, and for a key of several columns one column for each. `In.get_prep_lookup` sees to the common case for every field, adding `"pk"` to a subquery that has chosen no columns, and `RelatedIn.get_prep_lookup` steps in before it where the relation's own target columns are wanted instead: a relation on several columns, and one whose target is not the far model's primary key (`django/db/models/fields/related_lookups.py:RelatedIn.get_prep_lookup`). With a `ColPairs` on the left and a queryset of the related model that has chosen nothing, it has the queryset select the key's source fields by name, with `Query.set_values`, so that the subquery yields tuples of the key's width. With one column and such a queryset, where the relation's target field is not a primary key, it narrows the queryset to that target column, or, in the case the comment describes, a one-to-one field that is its own model's primary key compared with a queryset of its own model, to the field's own name. A list of direct values it normalizes and prepares through the target field, one by one, and sets `prepare_rhs` false on the instance, so that `In`'s own preparation, which would prepare each value again through the left side's field, leaves them alone (`django/db/models/lookups.py:FieldGetDbPrepValueIterableMixin.get_prep_lookup`). Then `In.get_prep_lookup` runs: it checks that the subquery yields as many columns as the left side has, clears its ordering, and adds the primary key where nothing is selected ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)).

```text recording=sql
entry(Sailor.objects.filter(ship__in=[petrel, 2, '2'])).rhs  ->  [1, 2, 2]
entry(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000))).rhs.values_select, entry(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000))).rhs.has_select_fields  ->  ((), False)
tail(Sailor.objects.filter(ship__in=Ship.objects.filter(tonnage__gt=1000)))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (SELECT "U0"."id" FROM "fleet_ship" "U0" WHERE "U0"."tonnage" > %s)', (1000,))
tail(Sailor.objects.filter(ship__in=Ship.objects.values('home')))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (SELECT "U0"."home_id" AS "home" FROM "fleet_ship" "U0")', ())
```

The list came out as three integers. The queryset of ships was given no columns, so after preparation its `values_select` is still empty and `has_select_fields` false, and the key was added to its select list without an alias: the subquery reads `"U0"."id"`. The last line is a queryset that had chosen its column, `"home"`, which is left as it is, and the sailors' `"ship_id"` is compared with ports' keys: the lookup checks the width of the subquery and not what it selects.

`RelatedIn.as_sql` is the counterpart of the mixin's `as_sql`: a `ColPairs` on the left is handed to `TupleIn`, with each direct value normalized first and a queryset passed as it is; one column goes to `In.as_sql` (`django/db/models/fields/related_lookups.py:RelatedIn.as_sql`). On the reverse name to the berths, a list of pairs went to `TupleIn` as it was, and a queryset of berths that had chosen nothing was made to select its two source fields under their names:

```text recording=sql
tail(Port.objects.filter(berth__in=[(1, 1), (1, 2)]))  ->  ('FROM "fleet_port" INNER JOIN "office_berth" ON ("fleet_port"."id" = "office_berth"."port_id") WHERE ("office_berth"."port_id", "office_berth"."number") IN ((%s, %s), (%s, %s)) ORDER BY "fleet_port"."name" ASC', (1, 1, 1, 2))
tail(Port.objects.filter(berth__in=Berth.objects.filter(metres__gt=100)))  ->  ('FROM "fleet_port" INNER JOIN "office_berth" ON ("fleet_port"."id" = "office_berth"."port_id") WHERE ("office_berth"."port_id", "office_berth"."number") IN (SELECT "U0"."port_id" AS "port", "U0"."number" AS "number" FROM "office_berth" "U0" WHERE "U0"."metres" > %s) ORDER BY "fleet_port"."name" ASC', (100,))
```

## A key of two columns: Berth

The office knows a berth by its port and its number there, and has no key of its own:

```python
# harbour/office/models.py
class Berth(models.Model):
    pk = models.CompositePrimaryKey("port_id", "number")
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    metres = models.PositiveSmallIntegerField()
```

`CompositePrimaryKey` is a field with no column of its own: it names the fields that make the key, becomes the primary key of the model's `Model._meta` as it joins the class, and puts a descriptor on the class that reads and writes the named fields as one tuple (`django/db/models/fields/composite.py:CompositePrimaryKey`) ([The field classes](../models/field-types.md)). What matters to a query is `CompositePrimaryKey.get_col`, which returns a `ColPairs` over the key's fields where another field returns a `Col`, so that `"pk"` in a filter on Berth is the pair of columns `("port_id", "number")` (`django/db/models/fields/composite.py:CompositePrimaryKey.get_col`), and `Options.pk_fields`, which opens the key into those fields for whoever has to count a model's key columns (`django/db/models/options.py:Options.pk_fields`). The module registers the seven tuple lookups on the class after it, under the same seven words `ForeignObject` uses (`django/db/models/fields/composite.py`).

```text recording=sql
entry(Berth.objects.filter(pk=(1, 2))), tail(Berth.objects.filter(pk=(1, 2)))  ->  (TupleExact(ColPairs('office_berth', (<django.db.models.fields.related.ForeignKey: port>, <django.db.models.fields.PositiveSmallIntegerField: number>), (<django.db.models.fields.related.ForeignKey: port>, <django.db.models.fields.PositiveSmallIntegerField: number>), <django.db.models.fields.composite.CompositePrimaryKey: pk>), (1, 2)), ('FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") = (%s, %s)', (1, 2)))
```

The lookup holds the `ColPairs` on its left, with its alias, its two target fields, the same two as sources, and the composite key as its output field, and the tuple `(1, 2)` on its right; the statement compares the two columns with two placeholders as one row value.

## `Tuple` and `TupleLookupMixin`

`Tuple` is a `Func` whose function name is the empty string, so that the template of `Func` writes its arguments in parentheses with nothing in front: `(%s, %s)` for two values, and `((%s, %s), (%s, %s))` for a `Tuple` of two tuples (`django/db/models/fields/tuple_lookups.py:Tuple`). It has a length and can be iterated, like a `ColPairs`, and it allows composite expressions among its sources, which `BaseExpression.resolve_expression` refuses for a class that has not said so ([Transforms and database functions: `Transform` and `Func`](functions.md)). On SQLite older than 3.37 its `as_sqlite` writes the first row of a list of rows with `"VALUES"` in front (`django/db/models/fields/tuple_lookups.py:Tuple.as_sqlite`).

`TupleLookupMixin` is what the seven classes have in common, in front of the ordinary comparison class each is built on, and its work is to make a row value out of parts that are each one column: a left side that is a `ColPairs` or a `Tuple` of columns, a right side that is a tuple of values, a `ColPairs`, a `ResolvedOuterRef` or a `Query`, and parentheses round each half (`django/db/models/fields/tuple_lookups.py:TupleLookupMixin`). `get_prep_lookup` checks a direct value for being a tuple or a list of the left side's width, and refuses otherwise with `ValueError` naming the lookup and the field; an expression has to be one of those three classes, and then the parent's preparation runs, which for `TupleExact` is `Exact`'s checks on a subquery (`django/db/models/fields/tuple_lookups.py:TupleLookupMixin.get_prep_lookup`). `get_prep_lhs` turns a left side given as a tuple or list of columns into a `Tuple`, and `process_lhs` compiles the left side and adds the parentheses unless it is a `Tuple`, which carries its own. `process_rhs` turns a direct value into a `Tuple`, each element that is not already an expression wrapped as a `Value` typed by the column it stands against, and compiles that; a `ColPairs` is compiled and put in parentheses; a `Query` is compiled as `Lookup.process_rhs` compiles any expression; anything else is refused, since composite field lookups work with composite expressions alone (`django/db/models/fields/tuple_lookups.py:TupleLookupMixin.process_rhs`).

`TupleLookupMixin.as_sql` asks the backend's features twice (`django/db/models/fields/tuple_lookups.py:TupleLookupMixin.as_sql`). Where `supports_tuple_comparison_against_subquery` is off and the lookup is one of the four ordered comparisons with a subquery on the right, it raises `NotSupportedError`. Where `supports_tuple_lookups` is off, it returns `get_fallback_sql`, which six of the seven define for themselves (`TupleIsNull` overrides `as_sql` and never reaches it) and the mixin's own refuses with `NotImplementedError`. Otherwise the parent's `as_sql` writes the row value: `BuiltinLookup.as_sql` puts the two compiled halves either side of the operator `get_rhs_op` gives, the backend's table entry for the comparisons and `"IN"` from `In.get_rhs_op` for `TupleIn`. Both features are true in the base features class, and Oracle is the backend that answers otherwise: `supports_tuple_comparison_against_subquery` is false there, and `supports_tuple_lookups` is decided by its version (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_tuple_lookups`, `django/db/backends/oracle/features.py:DatabaseFeatures.supports_tuple_lookups`) ([Database backends](../backends.md)).

```text recording=sql
Berth.objects.filter(pk=F('pk'))  ->  <QuerySet [<Berth: Berth object ((1, 1))>, <Berth: Berth object ((1, 2))>]>
  SQL SELECT "office_berth"."port_id", "office_berth"."number", "office_berth"."metres" FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") = ("office_berth"."port_id", "office_berth"."number") LIMIT 21
tail(Berth.objects.filter(pk=Berth.objects.values('pk')[:1]))  ->  ('FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") = (SELECT "U0"."port_id", "U0"."number" FROM "office_berth" "U0" LIMIT 1)', ())
tail(Berth.objects.filter(pk__gt=Berth.objects.values('pk')[:1]))  ->  ('FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") > (SELECT "U0"."port_id", "U0"."number" FROM "office_berth" "U0" LIMIT 1)', ())
connection.features.supports_tuple_lookups, connection.features.supports_tuple_comparison_against_subquery  ->  (True, True)
```

The `F` resolved to the key's own `ColPairs`, which stands on the right in parentheses. A queryset on the right of `"exact"` is checked by `Exact.get_prep_lookup`, which counts the subquery's columns with a composite key opened out, two for `values('pk')` as for a queryset that selected nothing, and compares the count with the pair's width ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)).

> **Changed in 6.0.** A subquery that returns a composite primary key can stand on the right of lookups other than `"in"`, `"exact"` among them (`docs/releases/6.0.txt`).

## The seven tuple lookups

| word | class | the row value | the fallback |
|---|---|---|---|
| `"exact"` | `TupleExact` | `"(a, b) = (x, y)"` | `"a = x AND b = y"` |
| `"gt"` | `TupleGreaterThan` | `"(a, b) > (x, y)"` | `"a > x OR (a = x AND b > y)"` |
| `"gte"` | `TupleGreaterThanOrEqual` | `"(a, b) >= (x, y)"` | `"a > x OR (a = x AND (b > y OR b = y))"` |
| `"lt"` | `TupleLessThan` | `"(a, b) < (x, y)"` | `"a < x OR (a = x AND b < y)"` |
| `"lte"` | `TupleLessThanOrEqual` | `"(a, b) <= (x, y)"` | `"a < x OR (a = x AND (b < y OR b = y))"` |
| `"in"` | `TupleIn` | `"(a, b) IN ((x1, y1), (x2, y2))"` | `"(a = x1 AND b = y1) OR (a = x2 AND b = y2)"`, or `"EXISTS(...)"` for a subquery |
| `"isnull"` | `TupleIsNull` | `"a IS NULL OR b IS NULL"` for `True`, `"a IS NOT NULL AND b IS NOT NULL"` for `False` | the same |

*The seven lookups `CompositePrimaryKey` registers, for a key of two columns a and b against the values x and y: what each writes where the backend has `supports_tuple_lookups`, and what `get_fallback_sql` writes where it has not. The forms are the ones the classes' own comments give, with the three-column case cut to two.*

`TupleExact.get_fallback_sql` writes one `Exact` for each column and joins them under `"AND"` in a `WhereNode` of its own; with a `Query` on the right it writes the row value all the same, through `Exact.as_sql` (`django/db/models/fields/tuple_lookups.py:TupleExact.get_fallback_sql`). The four ordered comparisons build the chain the table shows as nested `WhereNode` objects, alternating the comparison with `Exact` and `"OR"` with `"AND"` column by column, the inclusive two ending with an `"OR"` on equality of the last column (`django/db/models/fields/tuple_lookups.py:TupleGreaterThan.get_fallback_sql`, `django/db/models/fields/tuple_lookups.py:TupleGreaterThanOrEqual.get_fallback_sql`).

`TupleIsNull` is the one class that does not write a row value at all: its `as_sql` writes one `IsNull` for each column and joins them with `"OR"` for `True` and `"AND"` for `False`, whatever the backend's features say (`django/db/models/fields/tuple_lookups.py:TupleIsNull.as_sql`). Its `get_prep_lookup` accepts a boolean, or a tuple or list of one boolean, which is the form `RelatedLookupMixin.as_sql` hands on after normalizing the value, and refuses anything else (`django/db/models/fields/tuple_lookups.py:TupleIsNull.get_prep_lookup`).

```text recording=sql
tail(Berth.objects.filter(pk__in=[(1, 1), (1, 2)]))  ->  ('FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") IN ((%s, %s), (%s, %s))', (1, 1, 1, 2))
tail(Berth.objects.filter(pk__gt=(1, 1))), tail(Berth.objects.filter(pk__lte=(1, 1)))  ->  (('FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") > (%s, %s)', (1, 1)), ('FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") <= (%s, %s)', (1, 1)))
tail(Berth.objects.filter(pk__isnull=False)), tail(Berth.objects.filter(pk__isnull=True))  ->  (('FROM "office_berth" WHERE ("office_berth"."port_id" IS NOT NULL AND "office_berth"."number" IS NOT NULL)', ()), ('FROM "office_berth" WHERE ("office_berth"."port_id" IS NULL OR "office_berth"."number" IS NULL)', ()))
```

`TupleIn.get_prep_lookup` has checks of its own for a direct value: that it is a tuple or a list, that each of its elements is one, and that each has the width of the left side; an expression has to be a `Query` or a `Subquery`, and then `In.get_prep_lookup` runs, which clears the subquery's ordering and adds the key where nothing is selected (`django/db/models/fields/tuple_lookups.py:TupleIn.get_prep_lookup`). `TupleIn.process_rhs` writes a direct value as a `Tuple` of tuples, each element that is not already an expression wrapped as a `Value` typed by its column, leaving out any row that holds a `None`, since a comment notes that `"NULL"` is never equal to anything; an empty list, or a list that is empty once those rows are gone, raises `EmptyResultSet`, and the statement is never sent (`django/db/models/fields/tuple_lookups.py:TupleIn.process_rhs`). `TupleIn.get_fallback_sql` writes a direct value as an `"OR"` of one `"AND"` of equalities for each row, with the same rows left out and the same `EmptyResultSet`; a `Query` on the right it turns into an `Exists`: a clone of the subquery with one `Exact` added to its where tree for each column, comparing the outer column with the inner one, the inner one taken from the subquery's own select list through a compiler of its own (`django/db/models/fields/tuple_lookups.py:TupleIn.get_fallback_sql`).

```text recording=sql
tail(Berth.objects.filter(pk__in=Berth.objects.filter(metres__gt=100)))  ->  ('FROM "office_berth" WHERE ("office_berth"."port_id", "office_berth"."number") IN (SELECT "U0"."port_id", "U0"."number" FROM "office_berth" "U0" WHERE "U0"."metres" > %s)', (100,))
sql_of(Berth.objects.filter(pk__in=[]))  ->  raises EmptyResultSet: 
sql_of(Berth.objects.filter(pk__in=[(1, None)]))  ->  raises EmptyResultSet: 
Berth.objects.filter(pk=1)  ->  raises ValueError: 'exact' lookup of 'pk' must be a tuple or a list
Berth.objects.filter(pk=(1,))  ->  raises ValueError: 'exact' lookup of 'pk' must have 2 elements
Berth.objects.filter(pk__in=[(1, 2, 3)])  ->  raises ValueError: 'in' lookup of 'pk' must have 2 elements each
Berth.objects.filter(pk__in=[1, 2])  ->  raises ValueError: 'in' lookup of 'pk' must be a collection of tuples or lists
```

The subquery selects the two key columns without aliases, as `In.get_prep_lookup` added them. The two `EmptyResultSet` lines are an empty list and a list whose one row held a `None`. The four refusals are the checks of `TupleLookupMixin.get_prep_lookup` and `TupleIn.get_prep_lookup`, each with the lookup's word and the field's name in its message.

With the feature switched off for one block of the recording, the same filters write the fallbacks:

```text recording=sql
With supports_tuple_lookups switched off for this block: the fallback SQL of the tuple lookups, written as ANDs and ORs of one-column comparisons
    connection.features.supports_tuple_lookups  ->  False
    tail(Berth.objects.filter(pk=(1, 2)))  ->  ('FROM "office_berth" WHERE ("office_berth"."port_id" = %s AND "office_berth"."number" = %s)', (1, 2))
    tail(Berth.objects.filter(pk__in=[(1, 1), (1, 2)]))  ->  ('FROM "office_berth" WHERE (("office_berth"."port_id" = %s AND "office_berth"."number" = %s) OR ("office_berth"."port_id" = %s AND "office_berth"."number" = %s))', (1, 1, 1, 2))
    tail(Berth.objects.filter(pk__gt=(1, 1)))  ->  ('FROM "office_berth" WHERE ("office_berth"."port_id" > %s OR ("office_berth"."port_id" = %s AND "office_berth"."number" > %s))', (1, 1, 1))
    tail(Berth.objects.filter(pk__gte=(1, 1)))  ->  ('FROM "office_berth" WHERE ("office_berth"."port_id" > %s OR ("office_berth"."port_id" = %s AND ("office_berth"."number" > %s OR "office_berth"."number" = %s)))', (1, 1, 1, 1))
    tail(Berth.objects.filter(pk__in=Berth.objects.filter(metres__gt=100)))  ->  ('FROM "office_berth" WHERE EXISTS(SELECT %s AS "a" FROM "office_berth" "U0" WHERE ("U0"."metres" > %s AND "office_berth"."port_id" = ("U0"."port_id") AND "office_berth"."number" = ("U0"."number")) LIMIT 1)', (1, 100))
```

The `"in"` with a subquery became an `"EXISTS"`, whose inner statement compares `"U0"."port_id"` and `"U0"."number"` with the outer berth's columns: the subquery had already been resolved against the outer query, with its aliases renamed, when the filter was built ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)).
