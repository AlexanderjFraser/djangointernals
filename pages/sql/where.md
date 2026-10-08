---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The where clause: `build_filter`, `add_q` and `WhereNode`

`Query.add_q` turns a `Q` into the query's where tree: a `WhereNode` for each node of the `Q`, and for each pair of a name and a value a lookup built by `Query.build_filter`. `WhereNode.as_sql` writes the tree, counting the children that can match nothing or everything; `Query.split_exclude` turns an exclude across a relation that can reach several rows into a subquery under `"NOT EXISTS"`; and `Query.add_filtered_relation` is the query's side of a condition that goes into a join.

The where clause has four things to do. It has to hold the conditions in the shape the `Q` gave them, nested under `"AND"`, `"OR"` and `"XOR"` with the negations where they were written, since the shape is the meaning. It has to say, of each condition, whether it needs a row on the far side of a join, because that is what decides whether the join is written inner or outer ([Tables and joins: the alias map and join promotion](joins.md)). It has to know when it can match nothing or everything, so that a comparison with an empty list sends no statement and the negation of one writes no `"WHERE"`. And it has to write SQL whose `"NOT"` means what Python's `not` means. SQL's does not: where a column is null, `NOT (col = 1)` is neither true nor false and the row is dropped, and a negated condition across a relation that can reach several rows, joined, would keep a ship for every sailor whose name is not the one excluded. The tree adds an `"IS NOT NULL"` for the first and writes a subquery for the second.

**The where tree** is `Query.where`, a `WhereNode`, which a new query makes empty (`django/db/models/sql/query.py:Query.__init__`). `WhereNode` is built on `Node` of `django/utils/tree.py`, as a `Q` is, and has the same three parts: a list of children, a connector, and a mark that negates the whole (`django/utils/tree.py:Node`, `django/db/models/sql/where.py:WhereNode`). A child is usually a lookup, an expression that is true or false of a row. The class's docstring admits any object with an `as_sql`, a `contains_aggregate` mark and either a `relabeled_clone` or a `relabel_aliases` with a `clone`, and three others stand there: a nested `WhereNode`, a `NothingNode` and an `ExtraWhere`. The tree holds no SQL. Its leaves are lookups whose left sides are columns bound to aliases and whose right sides are prepared values, and nothing is written until a compiler asks ([The query: what a `Query` holds, and how it is copied](query.md)).

What follows is recorded from a running Django, on SQLite, over the shipping line of the chapter's opening page ([From QuerySet to SQL](../sql.md)): a line at the left margin is Python as it was run, with its value after `->` where it is an expression; under it are the calls it set going, nested as they were made, with only the calls the passage is about written down, and `->` there is what a call returned; a line that begins `SQL` is a statement as Django handed it to its cursor.

## `add_q`: a node for each `Q`

`Query.add_q` is the one entry: `QuerySet.filter` and `QuerySet.exclude` reach it with one `Q` ([`filter`, `exclude` and `Q` objects](../querysets/filters.md)), and `Query.add_filter` wraps a single pair in a `Q` for it (`django/db/models/sql/query.py:Query.add_q`, `django/db/models/sql/query.py:Query.add_filter`). It notes which joins are inner before it starts, has `Query._add_q` build a node from the `Q`, adds that node to the where tree under `"AND"` when it has anything in it, and then demotes to inner again every join that was inner before. The comment at that line gives the reason: the new condition is joined to the existing ones by `"AND"`, so an inner join the existing conditions required is still required, while an outer join may be demoted, since a condition on a row the join did not produce cannot hold. The joins a condition may reuse are `Query.used_aliases`, the aliases the current call of `filter` has made, unless `add_q` is called with `reuse_all=True`, when every alias in the map may be; the one caller that does so is the prefetch of related objects, whose comment says every existing join must be reused so that a relation reaching several rows is not crossed twice (`django/db/models/fields/related_descriptors.py:_filter_prefetch_queryset`).

`Query._add_q` walks one `Q` (`django/db/models/sql/query.py:Query._add_q`). It makes a `WhereNode` with the `Q`'s connector and negation, flips the negation it is carrying if the `Q` is negated and marks the branch as negated from then on, and makes a `JoinPromoter` for the node from the connector, the number of children and the negation as it now stands. For each child it calls `build_filter`, which returns a node and the set of joins that child needs to be inner. The set goes to the promoter as the child's votes; the node is added to the one being built, under the `Q`'s connector. When every child is in, `JoinPromoter.update_join_types` promotes and demotes the query's joins by the votes, and `_add_q` returns its node with the joins the whole `Q` needs inner, which the `Q` above counts as one vote; the rules of the voting are [Tables and joins: the alias map and join promotion](joins.md). Among the flags that pass through to each `build_filter` unchanged are `allow_joins=False`, where a condition may not cross a relation, and `split_subq=False` where an exclude across a relation that can reach several rows is to be joined rather than written as a subquery, which is what `Q.resolve_expression` and `FilteredRelation.resolve_expression` ask for.

The tree does not come out one node deep for each `Q`. `Node.add` squashes a child node that is not negated and that has the parent's connector or only one child, moving its children up (`django/utils/tree.py:Node.add`). `build_filter` returns each pair's lookup as a node of one child under `"AND"`, so the lookup lands in its `Q`'s node directly, and a `Q` of one condition inside another disappears into it. A negated node is never squashed, which is how a negation keeps its place.

Here is a filter of two `Q` objects, an `"OR"` of two conditions and a negated condition. The walk of each name and the building of each lookup are left out; [From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md) has them.

```text recording=sql
      Query.add_q(q_object=<Q: (AND: (OR: ('home__name', 'Bergen'), ('tonnage__gt', 1000)), (NOT (AND: ('name', 'Skua'))))>)
        Query._add_q(<Q: (AND: (OR: ('home__name', 'Bergen'), ('tonnage__gt', 1000)), (NOT (AND: ('name', 'Skua'))))>, used_aliases=set())
          JoinPromoter.__init__(connector='AND', num_children=2, negated=False)
          Query.build_filter(<Q: (OR: ('home__name', 'Bergen'), ('tonnage__gt', 1000))>, can_reuse=set())
            Query._add_q(<Q: (OR: ('home__name', 'Bergen'), ('tonnage__gt', 1000))>, used_aliases=set())
              JoinPromoter.__init__(connector='OR', num_children=2, negated=False)
              Query.build_filter(('home__name', 'Bergen'), can_reuse=set())
                -> ((AND: Exact(Col(fleet_port, fleet.Port.name), 'Bergen')), {'fleet_port', 'fleet_ship'})
              JoinPromoter.add_votes({'fleet_port', 'fleet_ship'})
              Query.build_filter(('tonnage__gt', 1000), can_reuse={'fleet_port', 'fleet_ship'})
                -> ((AND: IntegerGreaterThan(Col(fleet_ship, fleet.Ship.tonnage), 1000)), {'fleet_ship'})
              JoinPromoter.add_votes({'fleet_ship'})
              JoinPromoter.update_join_types(a Query of Ship)
                Query.promote_joins({'fleet_port'})
                Query.demote_joins({'fleet_ship'})
                -> {'fleet_ship'}
              -> ((OR: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), IntegerGreaterThan(Col(fleet_ship, fleet.Ship.tonnage), 1000)), {'fleet_ship'})
            -> ((OR: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), IntegerGreaterThan(Col(fleet_ship, fleet.Ship.tonnage), 1000)), {'fleet_ship'})
          JoinPromoter.add_votes({'fleet_ship'})
          Query.build_filter(<Q: (NOT (AND: ('name', 'Skua')))>, can_reuse={'fleet_port', 'fleet_ship'})
            Query._add_q(<Q: (NOT (AND: ('name', 'Skua')))>, used_aliases={'fleet_port', 'fleet_ship'})
              JoinPromoter.__init__(connector='AND', num_children=1, negated=True)
              Query.build_filter(('name', 'Skua'), can_reuse={'fleet_port', 'fleet_ship'}, branch_negated=True, current_negated=True)
                -> ((AND: Exact(Col(fleet_ship, fleet.Ship.name), 'Skua')), ())
              JoinPromoter.add_votes(())
              JoinPromoter.update_join_types(a Query of Ship)
                Query.promote_joins(set())
                Query.demote_joins(set())
                -> set()
              -> ((NOT (AND: Exact(Col(fleet_ship, fleet.Ship.name), 'Skua'))), set())
            -> ((NOT (AND: Exact(Col(fleet_ship, fleet.Ship.name), 'Skua'))), set())
          JoinPromoter.add_votes(set())
          JoinPromoter.update_join_types(a Query of Ship)
            Query.promote_joins(set())
            Query.demote_joins({'fleet_ship'})
            -> {'fleet_ship'}
          -> ((AND: (OR: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), IntegerGreaterThan(Col(fleet_ship, fleet.Ship.tonnage), 1000)), (NOT (AND: Exact(Col(fleet_ship, fleet.Ship.name), 'Skua')))), {'fleet_ship'})
        Query.demote_joins(set())
    -> a QuerySet of Ship, no result cache
where_said(mixed)  ->  (AND: (OR: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), IntegerGreaterThan(Col(fleet_ship, fleet.Ship.tonnage), 1000)), (NOT (AND: Exact(Col(fleet_ship, fleet.Ship.name), 'Skua'))))
sql_of(mixed)  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE (("fleet_port"."name" = %s OR "fleet_ship"."tonnage" > %s) AND NOT ("fleet_ship"."name" = %s)) ORDER BY "fleet_ship"."name" ASC', ('Bergen', 1000, 'Skua'))
```

The `"OR"` was handed to `build_filter` as a `Q` and came back from `_add_q` as a node of two lookups, with the one join both of its children voted for; the negated `Q` came back as a negated node of one lookup, with no votes, which the next section explains. Each node was added to the `"AND"` node above it whole, since neither could be squashed: one has the other connector, the other is negated.

```text figure=the-where-tree
WhereNode AND                                               (... AND ...)
|
+-- WhereNode OR                                            ("fleet_port"."name" = %s OR "fleet_ship"."tonnage" > %s)
|   +-- Exact(Col(fleet_port, Port.name), 'Bergen')         "fleet_port"."name" = %s
|   +-- IntegerGreaterThan(Col(fleet_ship, Ship.tonnage), 1000)   "fleet_ship"."tonnage" > %s
|
+-- WhereNode AND, negated                                  NOT ("fleet_ship"."name" = %s)
    +-- Exact(Col(fleet_ship, Ship.name), 'Skua')           "fleet_ship"."name" = %s

the whole:  (("fleet_port"."name" = %s OR "fleet_ship"."tonnage" > %s) AND NOT ("fleet_ship"."name" = %s))
```

*The where tree of `filter(Q(home__name='Bergen') | Q(tonnage__gt=1000), ~Q(name='Skua'))` as the recording above left it, each node and lookup beside the SQL it wrote. A node writes its children joined by its connector, in parentheses where it has more than one, and `NOT (...)` where it is negated.*

## `build_filter`: one condition

`Query.build_filter` builds the node for one child of a `Q` and returns it with the joins the child needs inner, without adding anything to the where tree; the docstring says the caller is responsible for unreferencing the joins if it does not add the node (`django/db/models/sql/query.py:Query.build_filter`). A child is one of three things. A dictionary is refused with `FieldError`, which is how `filter({"name": "x"})` fails. A `Q` goes to `_add_q`, with the branch's negation and the reusable joins passed along, and the node it returns is the child's. Anything with a `resolve_expression` is an expression, and is refused with `TypeError` unless it is marked `conditional`, the mark a `Q`, a `WhereNode`, a lookup and an expression whose output field is a boolean field carry ([Expressions: `resolve_expression` and `as_sql`](expressions.md)). A conditional expression is resolved against the query and, unless it is a lookup already, compared with `True` through `build_lookup(["exact"], condition, True)`:

```text recording=sql
tail(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk'), name='Ada'))))  ->  ('FROM "fleet_ship" WHERE EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U0" WHERE ("U0"."name" = %s AND "U0"."ship_id" = ("fleet_ship"."id")) LIMIT 1) ORDER BY "fleet_ship"."name" ASC', (1, 'Ada'))
tail(Ship.objects.filter(Q(tonnage__gt=1) & Exists(Sailor.objects.filter(ship=OuterRef('pk')))))  ->  ('FROM "fleet_ship" WHERE ("fleet_ship"."tonnage" > %s AND EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = ("fleet_ship"."id") LIMIT 1)) ORDER BY "fleet_ship"."name" ASC', (1, 1))
tail(Ship.objects.filter(~Exists(Sailor.objects.filter(ship=OuterRef('pk')))))  ->  ('FROM "fleet_ship" WHERE NOT EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U0" WHERE "U0"."ship_id" = ("fleet_ship"."id") LIMIT 1) ORDER BY "fleet_ship"."name" ASC', (1,))
tail(Ship.objects.filter(Value(True)))  ->  ('FROM "fleet_ship" WHERE %s = %s ORDER BY "fleet_ship"."name" ASC', (True, True))
tail(Ship.objects.filter(Q(name='Petrel') & Value(True)))  ->  ('FROM "fleet_ship" WHERE ("fleet_ship"."name" = %s AND %s = %s) ORDER BY "fleet_ship"."name" ASC', ('Petrel', True, True))
Ship.objects.filter(F('tonnage'))  ->  raises TypeError: Cannot filter against a non-conditional expression.
Ship.objects.filter(Lower('name'))  ->  raises TypeError: Cannot filter against a non-conditional expression.
tail(Ship.objects.filter(ExpressionWrapper(Q(tonnage__gt=1000), output_field=models.BooleanField())))  ->  ('FROM "fleet_ship" WHERE ("fleet_ship"."tonnage" > %s) ORDER BY "fleet_ship"."name" ASC', (1000,))
where_said(Ship.objects.filter(Exists(Sailor.objects.filter(ship=OuterRef('pk')))))  ->  (AND: Exact(Exists(a Query of Sailor), True))
```

The last line is the tree: an `Exact` of the `Exists` and `True`. The statement shows no `= %s`, because `Exact.as_sql` writes a conditional left side alone, or under `"NOT"`, where the backend accepts a condition standing by itself in a `"WHERE"`, and `Exists` is accepted everywhere ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)). `Value(True)` is conditional too, by its output field, and is written `%s = %s`; an `F` and a `Lower` are not. A `Q` on the left of `&` or `|` takes an `Exists` as its other operand through `Q._combine`, which accepts anything conditional; an `Exists` on the left goes through `Combinable.__and__` and its fellow, which make a `Q` of two conditional operands (`django/db/models/expressions.py:Combinable.__and__`). The `~` is `Combinable.__invert__`, and a `NegatedExpression` of an `Exists` writes `"NOT EXISTS"`.

Everything else is unpacked as a pair, a name and a value, and the name is refused with `FieldError` when it is empty. From here `build_filter` works in a fixed order.

**The name is divided.** `Query.solve_lookup_type` splits it at each `"__"` and returns the words that name fields, the words left over for transforms and a lookup, and, where the first words name an annotation, that annotation's expression ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). With `allow_joins=False` a name of more than one field word is refused with `FieldError`.

**The value is resolved.** `Query.resolve_lookup_value` resolves an expression against the query, with the reusable joins and the same leave to join; a list or a tuple is rebuilt with each item resolved, a named tuple through its own constructor; anything else is returned as it is (`django/db/models/sql/query.py:Query.resolve_lookup_value`). `build_filter` copies the reference counts of the aliases before this step and compares them after it, so that a join the value made, an `F` across a relation, counts among the joins the condition needs inner. `Query.check_filterable` is asked of the annotation's expression and of the value: it raises `NotSupportedError` for an expression whose `filterable` is false, or that holds one among its sources (`django/db/models/sql/query.py:Query.check_filterable`). No class in Django sets the mark; `BaseExpression.filterable` is true, and the check is for an expression a project marks.

**An annotation needs no join.** Where the name referred to an annotation, the lookup is built on the annotation's expression and the node is returned at once, with no joins.

**The joins are made.** Otherwise `Query.setup_joins` walks the field words from the base table's alias and `Query.trim_joins` takes back the joins at the end that a key already held makes unnecessary ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)); the joins are added to the condition's inner votes before the trimming, with the comment that the untrimmed set is what later decides which joins can be made inner, and those left after it are added to the reusable set. Between the two, an iterator given as the value is read into a list, and `Query.check_related_objects` checks the value against the field. A relation that can reach several rows is walked with `allow_many=False` where the branch is negated and `split_subq=True`, and `names_to_path` then raises `MultiJoin` at the first such step; `build_filter` catches it and hands the whole pair to `split_exclude`, below.

**The lookup is built.** The column is `Col` of the target field on the last alias, or a `ColPairs` where the relation's key is several columns ([Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](related-lookups.md)); `Query.build_lookup` makes the transforms and the lookup of the words left over ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)), and the lookup goes into a `WhereNode` of one child.

### What a filter on a relation accepts

`Query.check_related_objects` is asked when the final field is a relation (`django/db/models/sql/query.py:Query.check_related_objects`). A `Query` as the value, one with nothing selected, must be of a compatible model, or `ValueError` says which queryset to use instead. An instance, or each instance of an iterable, goes to `Query.check_query_object_type`, which refuses with `ValueError` an instance whose model is not compatible. Compatible is `check_rel_lookup_compatibility`: the same concrete model, so that a proxy stands for its model, or a parent of the other's model in either direction; and, for a primary key, the field's own model as well, which its comment explains by a one-to-one primary key to another model, where the field's target options are the other model's and `"pk__in"` with a queryset of the model itself must still be allowed (`django/db/models/query_utils.py:check_rel_lookup_compatibility`).

```text recording=sql
Sailor.objects.filter(ship=bergen)  ->  raises ValueError: Cannot query "Bergen": Must be "Ship" instance.
Sailor.objects.filter(ship__in=[petrel, bergen])  ->  raises ValueError: Cannot query "Bergen": Must be "Ship" instance.
Sailor.objects.filter(ship__in=Port.objects.all())  ->  raises ValueError: Cannot use QuerySet for "Port": Use a QuerySet for "Ship".
tail(Sailor.objects.filter(ship__in=Port.objects.values('id')))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" IN (SELECT "U0"."id" AS "id" FROM "fleet_port" "U0")', ())
tail(Sailor.objects.filter(ship=Veteran.objects.get(pk=1).ship))  ->  ('FROM "crew_sailor" WHERE "crew_sailor"."ship_id" = %s', (1,))
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE ("crew_sailor"."signed_on" < %s AND "crew_sailor"."id" = %s) LIMIT 21 with params ('2020-01-01 00:00:00', 1)
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."id" = %s LIMIT 21 with params (1,)
tail(Ship.objects.filter(captain=Veteran(pk=1)))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."captain_id" = %s ORDER BY "fleet_ship"."name" ASC', (1,))
```

A port is not a ship, in a list no more than alone; a queryset of ports is refused while a queryset of their keys, which has selected fields, is not checked and becomes a subquery; and a Veteran, a proxy of Sailor, is a sailor. The two statements under the fifth line were sent by `get` and by the attribute that fetched the ship, not by the filter.

### The negation, and the `"IS NOT NULL"` it adds

The last thing `build_filter` does is decide what the condition means for the joins, and whether it needs a companion (`django/db/models/sql/query.py:Query.build_filter`). It returns its inner votes only where the condition requires a row on the far side; it returns none, so that the joins stay outer, where the condition is `isnull=True` in a branch that is not negated, and in a negated branch wherever the lookup is not `isnull=True` and the value is not `None`, since a negated condition is met by a row the join did not produce.

In a negated branch a lookup other than `"isnull"` gets a companion. The comment at that line gives the reason: the SQL wanted for `~Q(col=val)` is `col IS NULL OR col != val`, which is what Python's `not` gives for a null, and that is `NOT (col IS NOT NULL AND col = val)`, the outer `"NOT"` being the node's. So where the column is nullable, or the last join is an outer join, `build_filter` adds `col IS NOT NULL` beside the lookup under `"AND"`; for an `in` whose values include `None` it adds `col IS NULL` under `"OR"` instead, since a null is among the things matched. And where the value is a `Col` of a nullable column, `value IS NOT NULL` is added as well. Nullable is `Query.is_nullable`: the field allows null, or the backend treats the empty string as null and the field allows one (`django/db/models/sql/query.py:Query.is_nullable`).

```text recording=sql
build_filter under a negation: an IS NOT NULL is added for a nullable column, so that NOT behaves as Python's not
    tail(Ship.objects.exclude(tonnage=480))  ->  ('FROM "fleet_ship" WHERE NOT ("fleet_ship"."tonnage" = %s) ORDER BY "fleet_ship"."name" ASC', (480,))
    tail(Ship.objects.exclude(captain=None))  ->  ('FROM "fleet_ship" WHERE NOT ("fleet_ship"."captain_id" IS NULL) ORDER BY "fleet_ship"."name" ASC', ())
    tail(Ship.objects.exclude(captain__name='Cora'))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") WHERE NOT ("crew_sailor"."name" = %s AND "crew_sailor"."name" IS NOT NULL) ORDER BY "fleet_ship"."name" ASC', ('Cora',))
    tail(Ship.objects.exclude(captain__name__in=['Cora', None]))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") WHERE NOT (("crew_sailor"."name" IN (%s) OR "crew_sailor"."name" IS NULL)) ORDER BY "fleet_ship"."name" ASC', ('Cora',))
    tail(Sailor.objects.exclude(ship__captain=None))  ->  ('FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") WHERE NOT ("fleet_ship"."captain_id" IS NULL)', ())
    tail(Ship.objects.exclude(tonnage=F('home__id')))  ->  ('FROM "fleet_ship" WHERE NOT ("fleet_ship"."tonnage" = ("fleet_ship"."home_id")) ORDER BY "fleet_ship"."name" ASC', ())
    tail(Ship.objects.exclude(captain=F('home')))  ->  ('FROM "fleet_ship" WHERE NOT ("fleet_ship"."captain_id" = ("fleet_ship"."home_id") AND "fleet_ship"."captain_id" IS NOT NULL) ORDER BY "fleet_ship"."name" ASC', ())
```

The first line adds nothing, tonnage being a column that cannot be null. The second is `exclude(captain=None)`: `build_lookup` turned the `None` into `isnull=True`, and an `"isnull"` lookup gets no companion. The third and fourth cross the nullable key to the captain, and the join is written outer because the negated condition voted for nothing; the fourth has `None` among its values, so the companion is `"IS NULL"` under `"OR"`. In the last two the value is a column, the home port's key, which cannot be null and gets no companion of its own; in the last the left side is the nullable key to the captain, and that is what the `"IS NOT NULL"` is for.

## `split_exclude`: a negated relation becomes a subquery

An exclude across a relation that can reach several rows cannot be a join. `exclude(crew__name='Ada')` joined would produce a row for each sailor of each ship and keep every row whose sailor is not Ada, so the Petrel, whose crew is Ada and Bram, would be kept for Bram. What is wanted is the ships for which no sailor named Ada exists, and `Query.split_exclude` writes that (`django/db/models/sql/query.py:Query.split_exclude`). The docstring gives the shape: `WHERE NOT EXISTS(SELECT 1 FROM child WHERE name = 'foo' AND child.parent_id = parent.id LIMIT 1)`.

```text recording=sql
        Query.build_filter(('crew__name', 'Ada'), can_reuse=set(), branch_negated=True, current_negated=True)
          Query.setup_joins(names=['crew', 'name'], alias='fleet_ship', can_reuse=set(), allow_many=False)  raises MultiJoin
          Query.split_exclude(filter_expr=('crew__name', 'Ada'), can_reuse=set(), names_with_path=[('crew', [PathInfo(from Ship to Sailor via the rel of Sailor.ship, reverse, many)])])
            Query.add_filter(filter_lhs='crew__name', filter_rhs='Ada')
            Query.trim_start(names_with_path=[('crew', [PathInfo(from Ship to Sailor via the rel of Sailor.ship, reverse, many)])])  ->  ('id', False)
            Query.build_filter(Exists(a Query of Ship))
              Query.bump_prefix(a Query of Ship)
              Query.setup_joins(names=['id'], alias='fleet_ship')  ->  JoinInfo(final_field=Ship.id, targets=(Ship.id,), opts=the options of Ship, joins=['fleet_ship'], path=[])
              Query.build_lookup(lookups=['exact'], lhs=Exists(a Query of Ship), rhs=True)  ->  Exact(Exists(a Query of Ship), True)
              -> ((AND: Exact(Exists(a Query of Ship), True)), [])
            -> ((AND: Exact(Exists(a Query of Ship), True)), [])
          -> ((AND: Exact(Exists(a Query of Ship), True)), [])
        -> ((NOT (AND: Exact(Exists(a Query of Ship), True))), set())
sql_of(no_ada)  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE NOT (EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U1" WHERE ("U1"."name" = %s AND "U1"."ship_id" = ("fleet_ship"."id")) LIMIT 1)) ORDER BY "fleet_ship"."name" ASC', (1, 'Ada'))
```

`setup_joins` raised `MultiJoin` at the reverse relation to the crew, and `split_exclude` was given the pair and the path up to that step. It made a new `Query` of the same model, sharing the outer query's filtered relations, and added the pair to it with `add_filter`, as a plain filter, not negated, with a value that is an `F` turned into an `OuterRef` of the same name and an `OuterRef` wrapped in another, so that each refers one query further out ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). It cleared the inner query's ordering. Then `Query.trim_start` cut the inner query down (`django/db/models/sql/query.py:Query.trim_start`): it unreferences the tables walked before the first step that can reach several rows; where the join of that step is inner and carries no filtered relation it unreferences the table the join hangs from as well and selects the joining columns on the join's own table, and otherwise, with the comment that an outer join would lose the rows with nothing on its far side and a filtered relation its filter, it keeps that table and selects the key columns there; and it makes whichever alias is left first the inner query's base table. It returns the name the outer query is to be compared on, `"id"` here, the key the relation's field points at, and whether any of the trimmed joins was an outer join. The inner query selects the sailors' `"ship_id"`, and a lookup `"ship_id" = ResolvedOuterRef("id")` is added to its where tree.

The inner query is then wrapped in an `Exists` and given to `build_filter` as a conditional expression; resolving it against the outer query is what renamed the inner aliases to `"U1"` and turned the `ResolvedOuterRef` into the outer table's column. The node comes back as `Exact(Exists(...), True)` with no inner votes, and the `"NOT"` is the negated node's above it. One more thing happens where the trimmed joins held an outer join: the inner query's starting column may then be null in the outer query, and `NOT EXISTS` alone would drop such rows, so `split_exclude` adds `outercol IS NULL` under `"OR"`, with the comment that this might look crazy and seems to be correct. `exclude(captain__pilots_into=None)` is such a case: the key to the captain is nullable, and an `"isnull"` condition in the inner query votes for no join, so the join is still outer when `trim_start` looks at it.

Where the inner query's first alias is among the joins the outer query may reuse, the inner query is tied to the outer query's row of that table rather than to its base table: `split_exclude` renames the inner aliases first and adds `inner.pk = outer.pk` on that alias, marking the outer alias as external, with the comment that the outer query's filters must hold for the subquery too.

```text recording=sql
tail(Port.objects.exclude(voyage__sailed__year=2026))  ->  ('FROM "fleet_port" WHERE NOT (EXISTS(SELECT %s AS "a" FROM "fleet_voyage_calls" "U1" INNER JOIN "fleet_voyage" "U2" ON ("U1"."voyage_id" = "U2"."id") WHERE ("U2"."sailed" BETWEEN %s AND %s AND "U1"."port_id" = ("fleet_port"."id")) LIMIT 1)) ORDER BY "fleet_port"."name" ASC', (1, '2026-01-01', '2026-12-31'))
tail(Ship.objects.exclude(captain__pilots_into__name='Bergen'))  ->  ('FROM "fleet_ship" WHERE NOT (EXISTS(SELECT %s AS "a" FROM "office_licence" "U2" INNER JOIN "fleet_port" "U3" ON ("U2"."port_id" = "U3"."id") WHERE ("U3"."name" = %s AND "U2"."sailor_id" = ("fleet_ship"."captain_id")) LIMIT 1)) ORDER BY "fleet_ship"."name" ASC', (1, 'Bergen'))
```

```text recording=sql
tail(Ship.objects.exclude(crew__name='Ada', crew__signed_on__year=2011))  ->  ('FROM "fleet_ship" WHERE NOT (EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U1" WHERE ("U1"."name" = %s AND "U1"."ship_id" = ("fleet_ship"."id")) LIMIT 1) AND EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U1" WHERE ("U1"."signed_on" BETWEEN %s AND %s AND "U1"."ship_id" = ("fleet_ship"."id")) LIMIT 1)) ORDER BY "fleet_ship"."name" ASC', (1, 'Ada', 1, '2011-01-01 00:00:00', '2011-12-31 23:59:59.999999'))
tail(Ship.objects.exclude(crew__name='Ada').exclude(crew__name='Bram'))  ->  ('FROM "fleet_ship" WHERE (NOT (EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U1" WHERE ("U1"."name" = %s AND "U1"."ship_id" = ("fleet_ship"."id")) LIMIT 1)) AND NOT (EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U1" WHERE ("U1"."name" = %s AND "U1"."ship_id" = ("fleet_ship"."id")) LIMIT 1))) ORDER BY "fleet_ship"."name" ASC', (1, 'Ada', 1, 'Bram'))
tail(Ship.objects.filter(crew__name='Ada').exclude(crew__name='Bram'))  ->  ('FROM "fleet_ship" INNER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") WHERE ("crew_sailor"."name" = %s AND NOT (EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U1" WHERE ("U1"."name" = %s AND "U1"."ship_id" = ("fleet_ship"."id")) LIMIT 1))) ORDER BY "fleet_ship"."name" ASC', ('Ada', 1, 'Bram'))
```

The first two statements are the trimming: a many-to-many relation's subquery starts at the table between, and the key to the captain is read on the outer ship, the join to the sailor having been cut. The third is two conditions in one `exclude`, each with a subquery of its own under one `"NOT"`, so that a ship is excluded when both hold of it, whether of one sailor or of two: the Petrel has Ada, who signed on in 2011, and is excluded, and a ship with a sailor named Ada and another who signed on in 2011 would be excluded too. The last is a filter and an exclude on the same relation: the filter joined the crew, and the exclude, in a later call with nothing to reuse, wrote its subquery against the ship.

## `WhereNode.as_sql`: what the tree writes

`WhereNode.as_sql` compiles each child through `SQLCompiler.compile` and joins what comes back with the connector (`django/db/models/sql/where.py:WhereNode.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.compile`). What makes it more than a join of strings is that a child may have no SQL to give. A child raises `EmptyResultSet` where it can match nothing, as `In` does for an empty list, and `FullResultSet` where it matches everything, as a negated empty node does; and a child whose SQL is the empty string counts as matching everything too. The node counts. Under `"AND"`, one empty child makes the node empty and every child must be full for the node to be full; under `"OR"` and `"XOR"`, one full child makes the node full and every child must be empty for it to be empty. When either count is reached the node raises the same exception for itself, the other way round if it is negated, so the news travels up the tree node by node. A node whose children all matched everything, and an empty node, raise `FullResultSet` at the end.

What the compiler does with the two is in `SQLCompiler.as_sql` (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). `FullResultSet` from the root means no `"WHERE"` clause. `EmptyResultSet` is raised on to `SQLCompiler.execute_sql`, which sends nothing and answers with no rows ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)); where the compiler was made with `elide_empty=False`, as a part of a compound statement may be, the clause becomes `0 = 1` instead and the statement is sent.

```text recording=sql
sql_of(Ship.objects.filter(pk__in=[]))  ->  raises EmptyResultSet: 
list(Ship.objects.filter(pk__in=[]))  ->  []
tail(Ship.objects.filter(Q(pk__in=[]) | Q(name='Petrel')))  ->  ('FROM "fleet_ship" WHERE "fleet_ship"."name" = %s ORDER BY "fleet_ship"."name" ASC', ('Petrel',))
sql_of(Ship.objects.filter(Q(pk__in=[]) & Q(name='Petrel')))  ->  raises EmptyResultSet: 
sql_of(Ship.objects.exclude(pk__in=[]))  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
sql_of(Ship.objects.filter(~Q(pk__in=[]) | Q(name='Petrel')))  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ())
tail(Ship.objects.filter(Q())), tail(Ship.objects.filter(Q() | Q(name='Petrel')))  ->  (('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()), ('FROM "fleet_ship" WHERE "fleet_ship"."name" = %s ORDER BY "fleet_ship"."name" ASC', ('Petrel',)))
sql_of(Ship.objects.none())  ->  raises EmptyResultSet: 
where_said(Ship.objects.none()), Ship.objects.none().query.is_empty(), where_said(Ship.objects.filter(pk__in=[])), Ship.objects.filter(pk__in=[]).query.is_empty()  ->  ((AND: a NothingNode), True, (AND: In(Col(fleet_ship, fleet.Ship.id), [])), False)
Ship.objects.none().query.where.as_sql(Ship.objects.all().query.get_compiler('default'), connection)  ->  raises EmptyResultSet: 
Ship.objects.filter(pk__in=[]).query.where.as_sql(Ship.objects.all().query.get_compiler('default'), connection)  ->  raises EmptyResultSet: 
Ship.objects.exclude(pk__in=[]).query.where.as_sql(Ship.objects.all().query.get_compiler('default'), connection)  ->  raises FullResultSet: 
WhereNode().as_sql(None, connection)  ->  raises FullResultSet: 
```

An `"OR"` with an empty child writes its other child alone; an `"AND"` with one is empty, and `exclude(pk__in=[])` is the negation of empty, which is everything, as is an `"OR"` with such a negation in it. `Q()` makes an empty node, which `add_q` does not add, and `Q() | Q(name='Petrel')` is the one condition. The queryset `QuerySet.none` returns holds a `NothingNode`; `filter(pk__in=[])` holds an `In`, and `Query.is_empty` is true of the first alone, since it looks for the node and not for what a lookup will raise ([The query: what a `Query` holds, and how it is copied](query.md)). The last four lines put the question to the tree itself.

When no child raised, the SQL is the children's joined by `" AND "`, `" OR "` or `" XOR "`; a negated node writes `NOT (...)`, and a node of more than one child, or one that is a resolved expression, is put in parentheses. The comment on the negated case says some backends, Oracle at least, need the parentheses even around a single expression.

A backend that has no `"XOR"` gets a rewrite. Where `BaseDatabaseFeatures.supports_logical_xor` is false, which it is on every backend but MySQL's, an `"XOR"` node compiles itself as an `"AND"` of two things: an `"OR"` of the same children, and an `Exact` of `1` with the sum of a `Case` for each child that is `1` where the child holds and `0` otherwise, the sum taken modulo 2 through `Mod` where there are more than two children (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_logical_xor`, `django/db/models/functions/math.py:Mod`). The comment gives the rule: an n-ary `"XOR"` is true when an odd number of its operands are.

```text recording=sql
XOR on SQLite, which has no XOR of its own: an OR beside a count of the true operands
    tail(Ship.objects.filter(Q(name='Petrel') ^ Q(tonnage__gt=1000)))  ->  ('FROM "fleet_ship" WHERE (("fleet_ship"."name" = %s OR "fleet_ship"."tonnage" > %s) AND %s = (CASE WHEN "fleet_ship"."name" = %s THEN %s ELSE %s END + CASE WHEN "fleet_ship"."tonnage" > %s THEN %s ELSE %s END)) ORDER BY "fleet_ship"."name" ASC', ('Petrel', 1000, 1, 'Petrel', 1, 0, 1000, 1, 0))
    tail(Ship.objects.filter(Q(name='Petrel') ^ Q(tonnage__gt=1000) ^ Q(home__name='Leith')))  ->  ('FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE (("fleet_ship"."name" = %s OR "fleet_ship"."tonnage" > %s OR "fleet_port"."name" = %s) AND %s = (MOD(((CASE WHEN "fleet_ship"."name" = %s THEN %s ELSE %s END + CASE WHEN "fleet_ship"."tonnage" > %s THEN %s ELSE %s END) + CASE WHEN "fleet_port"."name" = %s THEN %s ELSE %s END), %s))) ORDER BY "fleet_ship"."name" ASC', ('Petrel', 1000, 'Leith', 1, 'Petrel', 1, 0, 1000, 1, 0, 'Leith', 1, 0, 2))
    connection.features.supports_logical_xor  ->  False
```

With two children the sum must be 1, so the `Mod` is left out; with three it is taken modulo 2.

Before the compiler asks the tree for SQL it divides it: `WhereNode.split_having_qualify` returns the parts of the tree that go into `"WHERE"`, those that compare an aggregate and go into `"HAVING"`, and those that refer to a window and cannot stand in either, keeping together what a negation or an `"OR"` must keep together ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md), [Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)).

## The rest of `WhereNode`

The tree is copied, relabelled and resolved as the query is. `WhereNode.clone` makes a new node for each node of the tree and keeps every other child as it is, cloning only a child that has a `clone` method, which a lookup has not, so the lookups of a clone are the original's (`django/db/models/sql/where.py:WhereNode.clone`); `Query.clone` copies the where tree this way for every method of a queryset ([The query: what a `Query` holds, and how it is copied](query.md)). `WhereNode.relabel_aliases` renames aliases in place, by a map from old to new, recursing into a child node and replacing any other child with its `relabeled_clone`; `WhereNode.relabeled_clone` clones first (`django/db/models/sql/where.py:WhereNode.relabel_aliases`). That is what a query inside another, and the right side of a `combine`, go through ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md), [Two queries into one: `combine` and `get_combinator_sql`](combining.md)).

`WhereNode.resolve_expression` is for a tree that already stands as an expression and is resolved again, as the tree a `Q` given to `annotate` became is when a filter on the annotation compiles it as a lookup's left side: it clones the tree, resolves against the query the `lhs` and the `rhs` of each leaf that has them, setting the result on the leaf itself, and marks the clone `resolved`, which is what puts a single-child node in parentheses when it is written (`django/db/models/sql/where.py:WhereNode.resolve_expression`). Since `clone` kept the leaves, the leaves resolved are the original tree's too. The tree answers as an expression in the other ways a compiler needs: `WhereNode.output_field` is a `django.db.models.fields.BooleanField`, `WhereNode.select_format` wraps the SQL in `CASE WHEN ... THEN 1 ELSE 0 END` where the backend cannot select a condition as a column, and `WhereNode.get_db_converters` and `WhereNode.get_lookup` hand on to that field; `WhereNode.conditional` is true. `WhereNode.replace_expressions` returns the replacement for the whole tree if the map has one, and otherwise a new tree with each child replaced; `WhereNode.get_refs` gathers the annotation names the children refer to; `WhereNode.get_group_by_cols` gathers the children's columns, which is how a condition selected as a column reaches the `"GROUP BY"`. `WhereNode.contains_aggregate` and `WhereNode.contains_over_clause` are cached and walk the nodes, asking each leaf; `WhereNode.is_summary` is whether any child is. `WhereNode.leaves` yields every leaf of the tree, through the nodes, and `WhereNode.get_source_expressions` returns a copy of the children, which `set_source_expressions` replaces one for one.

## `NothingNode` and `ExtraWhere`

`NothingNode` is a child that matches nothing: it raises `EmptyResultSet` whenever its SQL is asked for (`django/db/models/sql/where.py:NothingNode`). `Query.set_empty` adds one to the tree under `"AND"`, and to the tree of each combined query, and `Query.is_empty` is whether one stands directly under the root ([The query: what a `Query` holds, and how it is copied](query.md)); `QuerySet.none` is what calls it.

`ExtraWhere` is SQL a program wrote, taken as it is: `QuerySet.extra` hands its `where` list and `params` to `Query.add_extra`, which puts them in one `ExtraWhere` under `"AND"` when either is given (`django/db/models/sql/where.py:ExtraWhere`, `django/db/models/sql/query.py:Query.add_extra`). Its `as_sql` wraps each string in parentheses and joins them with `" AND "`, and gives the parameters back as a list. It carries no aggregate and no window, by the comment's admission that its contents are a black box, so it is always a `"WHERE"` part.

```text recording=sql
ExtraWhere: SQL a program wrote, taken as it is
    tail(Ship.objects.extra(where=['tonnage > %s', 'home_id = 1'], params=[500]))  ->  ('FROM "fleet_ship" WHERE (tonnage > %s) AND (home_id = 1) ORDER BY "fleet_ship"."name" ASC', (500,))
    where_said(Ship.objects.extra(where=['tonnage > %s'], params=[500]))  ->  (AND: an ExtraWhere)
    Ship.objects.extra(where=['tonnage > %s'], params=[500]).query.where.children[0].as_sql()  ->  ('(tonnage > %s)', [500])
    sql_of(Ship.objects.filter(name='Petrel').extra(where=['tonnage > 0']).filter(pk__in=[]))  ->  raises EmptyResultSet: 
```

The last line is the counting at work: the extra condition, which can neither match nothing nor everything, is in an `"AND"` with an `In` that can match nothing, and the node is empty.

`Query.build_where` builds a node for one condition with no joins allowed and returns the node without adding it; a check constraint and a conditional index compile their condition through it (`django/db/models/sql/query.py:Query.build_where`, `django/db/models/constraints.py:CheckConstraint._get_check_sql`). `Query.clear_where` replaces the tree with an empty one (`django/db/models/sql/query.py:Query.clear_where`).

## `add_filtered_relation`: a condition that goes into the join

A `FilteredRelation` is a relation's name and a `Q`, given to `annotate` under an alias; the object, and the queryset's side, are in [`filter`, `exclude` and `Q` objects](../querysets/filters.md). `Query.add_filtered_relation` checks it and stores it (`django/db/models/sql/query.py:Query.add_filtered_relation`). An alias with a period is refused with `ValueError`, and `Query.check_alias` refuses the characters an alias may not hold ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)). The relation's name is divided by `solve_lookup_type` and may hold no lookup. Every name in the condition, found by `get_children_from_q`, which walks the `Q` and any expression in it for names and `F` references, must start with the relation's own path and reach at most one field beyond it, so `"crew__ship__name"` for `"crew"` is refused with `ValueError` (`django/db/models/sql/query.py:get_children_from_q`). Then a clone is stored in `Query._filtered_relations` under the alias, its condition rewritten by `rename_prefix_from_q` so that each name that starts with the relation's name starts with the alias instead; a `QuerySet` inside the condition is refused there, with the comment that an `OuterRef` in it could not be pointed at the join (`django/db/models/sql/query.py:rename_prefix_from_q`, `django/db/models/sql/query.py:get_child_with_renamed_prefix`).

Nothing is joined until a name goes through the alias. `names_to_path` finds the alias among the filtered relations, walks the relation's own name, and marks the last step of the path with the object, so that `setup_joins` gives the last `Join` it makes a filtered relation and the alias as its name ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). As `Query.join` adds that join to the map it has the object resolve itself: `FilteredRelation.resolve_expression` returns a clone whose `resolved_condition` is what `build_filter` makes of the `Q`, built with the join itself among the reusable aliases, joins allowed, no subquery for a negated multi-valued relation, and no change to the join types (`django/db/models/sql/query.py:Query.join`, `django/db/models/query_utils.py:FilteredRelation.resolve_expression`). A join the condition made along the way is moved ahead of the join that carries it in the alias map, since it must be written first. `Join.as_sql` compiles the resolved condition into the `"ON"` after the join's own columns, in parentheses, and leaves it out where it raises `FullResultSet` (`django/db/models/sql/datastructures.py:Join.as_sql`).

```text recording=sql
veterans.query._filtered_relations['veterans'].relation_name, veterans.query._filtered_relations['veterans'].alias, veterans.query._filtered_relations['veterans'].condition, veterans.query._filtered_relations['veterans'].resolved_condition  ->  ('crew', 'veterans', <Q: (AND: ('veterans__signed_on__year__lt', 2020))>, None)
list(veterans.query.alias_map), tail(veterans)  ->  ([], ('FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', ()))
alias_map['fleet_ship']: BaseTable(fleet_ship), referenced 2
alias_map['veterans']: Join(crew_sailor, from fleet_ship via the rel of Sailor.ship, INNER JOIN, nullable, filtered), referenced 2
```

```text recording=sql
said(named_veterans.query.alias_map['veterans'].filtered_relation.resolved_condition)  ->  (AND: YearLt(ExtractYear(Col(veterans, crew.Sailor.signed_on)), 2020))
tail(named_veterans)  ->  ('FROM "fleet_ship" INNER JOIN "crew_sailor" "veterans" ON ("fleet_ship"."id" = "veterans"."ship_id" AND ("veterans"."signed_on" < %s)) WHERE "veterans"."name" = %s ORDER BY "fleet_ship"."name" ASC', ('2020-01-01 00:00:00', 'Ada'))
tail(veterans.values('name', 'veterans__name'))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" "veterans" ON ("fleet_ship"."id" = "veterans"."ship_id" AND ("veterans"."signed_on" < %s)) ORDER BY 1 ASC', ('2020-01-01 00:00:00',))
```

Here veterans is the queryset of ships annotated, under the name veterans, with `FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020))`, and named_veterans is that queryset filtered by `veterans__name='Ada'`. After `annotate` the object is stored with its condition rewritten and nothing resolved, and the alias map is empty; after the filter the map holds a join under the alias, nullable because the relation is a reverse one, and the join's object holds the resolved condition, a tree whose column is on the alias. The join is written inner in the second statement, the filter on `"veterans"."name"` having voted for it, and outer in the third, where `values` alone asks for the alias and nothing votes.

```text recording=sql
Ship.objects.annotate(v=FilteredRelation('crew', condition=Q(crew__ship__name='Petrel')))  ->  raises ValueError: FilteredRelation's condition doesn't support nested relations deeper than the relation_name (got 'crew__ship__name' for 'crew').
tail(Ship.objects.annotate(v=FilteredRelation('crew__pilots_into', condition=Q(crew__name='Ada'))).filter(v__name='Bergen'))  ->  ('FROM "fleet_ship" INNER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") INNER JOIN "office_licence" ON ("crew_sailor"."id" = "office_licence"."sailor_id") INNER JOIN "fleet_port" "v" ON ("office_licence"."port_id" = "v"."id" AND ("crew_sailor"."name" = %s)) WHERE "v"."name" = %s ORDER BY "fleet_ship"."name" ASC', ('Ada', 'Bergen'))
Ship.objects.annotate(v=FilteredRelation('crew__name')).filter(v='Ada')  ->  <QuerySet []>
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" WHERE "fleet_ship"."name" = %s ORDER BY "fleet_ship"."name" ASC LIMIT 21 with params ('Ada',)
```

A relation's name may itself cross relations: for `"crew__pilots_into"` the joins to the crew and to the table between are plain, and the last join, to the port under the alias, carries the condition, written against the table the condition names.

> **Trap.** A relation's name that ends in a field that is no relation is not refused. The last line above annotates `FilteredRelation('crew__name')` and filters on the alias, and the statement compares the ship's own `"name"` column: `names_to_path`, walking the relation's name for the alias, keeps every step of the path but the last, expecting the last word to be a relation whose join will carry the condition; where the last word is a plain field there is no such join, the one step walked is dropped with it, and the field is read on the table the walk started from (`django/db/models/sql/query.py:Query.names_to_path`).
