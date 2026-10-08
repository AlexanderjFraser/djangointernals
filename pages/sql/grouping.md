---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`

`Query.group_by` records that a query groups, in one of three forms, and `Query.set_group_by` fixes the grouping as a tuple of expressions; in the compiler, `SQLCompiler.get_group_by` writes the `"GROUP BY"` clause from that tuple, the select list, the ordering and the having, and `WhereNode.split_having_qualify` divides the where tree between `"WHERE"`, `"HAVING"` and the part that refers to a window.

A statement that aggregates has three things to get right. Every selected column that is not aggregated has to be grouped by, since a row of the result stands for a group and a column that varies within the group has no one value, and a backend that enforces this refuses the statement. A condition that compares an aggregate has to be tested after the grouping, in `"HAVING"`, where a condition on a column is tested on each row before it, in `"WHERE"`; and a condition that mixes the two under an `"OR"` cannot be divided. And a backend may accept a shorter list than every column: a table's primary key in place of its other columns, where it can tell that they depend on it, or the position of a selected column in place of the column. So the grouping is kept twice. The query keeps the least that must be grouped by, which a queryset's methods settle, and the compiler widens it to what the statement's other clauses need and narrows it to what the backend accepts.

## `Query.group_by`: three forms, and who sets each

`Query.group_by` is `None` on a new query, and a comment on the attribute gives its forms (`django/db/models/sql/query.py:Query.group_by`).

| form | meaning | set by |
|---|---|---|
| `None` | no `"GROUP BY"` | the class |
| `True` | every selected field of the model, and what the selected annotations add | `QuerySet._annotate`, when an annotation it adds contains an aggregate and neither `values` nor `values_list` has been called |
| a tuple of expressions | at least these; a string among them is a name to resolve | `Query.set_group_by`, called by `_annotate` after `values`, and by `Query.set_values` and `Query.exists` where the form was `True`; `Query.get_aggregation`, which sets the primary key on an inner query |

*The three forms of `Query.group_by`. A tuple is the **minimal set**: the compiler adds to it what the statement's other clauses need.*

`QuerySet._annotate` sets it as its last step, and only where an annotation added by that very call has `contains_aggregate` set: `True` where neither `values` nor `values_list` has been called, and otherwise `set_group_by`, which fixes the tuple at what the queryset selects, the columns `values` named first. `QuerySet.alias` goes through the same method and sets it the same way, and an annotation without an aggregate leaves it alone (`django/db/models/query.py:QuerySet._annotate`). The queryset's side, and the order of `values` and `annotate`, is [Annotations, ordering and the other methods that change the query](../querysets/methods.md). What follows was recorded from a running Django, on SQLite, over the models of [From QuerySet to SQL](../sql.md): a line is a question and its answer after `->`, or a call with the calls it set going nested under it and `->` what each returned. A line that asks tail of a queryset answers with its statement from the `"FROM"` clause on, the select list and its parameters left out.

```text recording=sql
Query.group_by: None where nothing aggregates, True after an annotation that does, and a tuple after values and then annotate
    Ship.objects.all().query.group_by, Ship.objects.annotate(hands=Count('crew')).query.group_by, Ship.objects.annotate(low=Lower('name')).query.group_by  ->  (None, True, None)
    Ship.objects.values('home').annotate(hands=Count('crew')).query.group_by  ->  (Col(fleet_ship, fleet.Ship.home),)
    Ship.objects.values('home', 'name').annotate(hands=Count('crew')).query.group_by  ->  (Col(fleet_ship, fleet.Ship.home), Col(fleet_ship, fleet.Ship.name))
    Ship.objects.annotate(hands=Count('crew')).values('home').query.group_by  ->  (Col(fleet_ship, fleet.Ship.id), Col(fleet_ship, fleet.Ship.name), Col(fleet_ship, fleet.Ship.tonnage), Col(fleet_ship, fleet.Ship.home), Col(fleet_ship, fleet.Ship.captain))
    Ship.objects.values(low=Lower('name')).annotate(hands=Count('crew')).query.group_by, Ship.objects.values(low=Lower('name')).annotate(hands=Count('crew')).query.annotations  ->  ((Ref(low, Lower(Col(fleet_ship, fleet.Ship.name))),), {'low': Lower(Col(fleet_ship, fleet.Ship.name)), 'hands': Count(Col(crew_sailor, crew.Sailor.id))})
    Ship.objects.alias(hands=Count('crew')).query.group_by  ->  True
    Sailor.objects.values('signed_on__year').annotate(n=Count('id')).query.group_by, Sailor.objects.values('signed_on__year').annotate(n=Count('id')).query.annotations  ->  ((Ref(signed_on__year, ExtractYear(Col(crew_sailor, crew.Sailor.signed_on))),), {'signed_on__year': ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 'n': Count(Col(crew_sailor, crew.Sailor.id))})
```

The first line shows `None` for a query that does not aggregate and for one whose annotation is a `Lower`, and `True` after a count. The tuple after `values("home")` holds the one column, and after `values("home", "name")` the two. The tuple after `annotate` and then `values` holds every column of the model: `annotate` had set `True`, and `set_values`, finding it, fixed the grouping at all the concrete fields before it narrowed the select list. The one with `Lower` holds a `Ref`, a reference to the annotation by its alias, and `alias` sets `True` as `annotate` does. In the last line a transform in a name given to `values`, the year a sailor signed on, has been moved into the annotations, and the tuple holds a `Ref` to it.

## `Query.set_group_by`

`Query.set_group_by` turns the select list and the selected annotations into the tuple (`django/db/models/sql/query.py:Query.set_group_by`). Its docstring says the result will usually be the set of all non-aggregate fields in the return data, and that where the backend can group by the primary key the optimisation is made automatically; the second half is the compiler's, told below.

With `allow_aliases=True`, which is the default and what `_annotate` passes, it first looks through the expressions `values` selected, in `Query.select` beside their names in `Query.values_select`, for one that is not a `Col`: a transform in a name given to `values`, as `"signed_on__year"` of a sailor is, which `Query.add_fields` resolves to the transform of the column. Each such expression is moved into `Query.annotations` under its name, added to the mask of selected annotations, and taken out of the select list, with `Query.selected` kept in step, so that the grouping can refer to it by alias. Then the tuple is built: every expression left in the select list, and for each selected annotation what its `get_group_by_cols` returns, which for an aggregate is nothing and for an expression without one is the expression itself ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md), [Expressions: `resolve_expression` and `as_sql`](expressions.md)); where that is not empty, an annotation without an aggregate goes in as a `Ref` to its alias, under `allow_aliases=True`, and as its columns otherwise.

`set_values` and `exists` pass `allow_aliases=False`, with a comment saying why: each is about to clear the select list, and a `Ref` into it would be orphaned. In `set_values` the call comes where `group_by` is `True`, after every concrete field of the model has been added to the select, so that the tuple holds every column and the fields the caller named only decide what is selected of each group; where `group_by` is a tuple already, `set_values` replaces a `Ref` whose alias is no longer among the selected names by the annotation's own expression (`django/db/models/sql/query.py:Query.set_values`). `Query.exists` does the same as `set_values` for `True` before it clears the select clause, which is how a grouped query keeps its `"GROUP BY"` in the statement that asks whether any row matches (`django/db/models/sql/query.py:Query.exists`).

## `SQLCompiler.get_group_by`

`SQLCompiler.get_group_by` returns the clause as a list of pairs of SQL and parameters, one for each expression grouped by (`django/db/models/sql/compiler.py:SQLCompiler.get_group_by`). Its docstring admits that what the clause contains is hard to describe in other words than that it passes the test suite; a comment under it gives examples, and then the rule that makes them one: the query's `group_by` is the minimal set, which no call of the queryset can narrow, and the columns of the `"HAVING"`, `"ORDER BY"` and `"SELECT"` clauses are added to it, so that no form of a queryset forces a chosen `"GROUP BY"`, a later annotation, ordering or filter being able to widen it. `SQLCompiler.pre_sql_setup` calls it last, after the select list is settled, after the ordering is resolved, which may join a table of its own, and after `WhereNode.split_having_qualify` has divided the where tree into **the where part**, the conditions for `"WHERE"`, **the having part**, those for `"HAVING"`, and **the qualify part**, those that refer to a window, since the having part's columns go in too ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)).

With `group_by` of `None` the clause is empty. Otherwise the method gathers expressions in four steps and then writes them. **From the query**, where `group_by` is a tuple: a string is resolved through `Query.resolve_ref`; a `Ref` puts its alias in a set of grouped aliases and, once for each alias, its source expression among the expressions rather than the `Ref` itself; anything else goes in as it is. The source is the very expression the select list holds under that alias, so it can be written as the alias's position, and the select list's own contribution of it is skipped. **From the select list**, each selected expression's position is noted where it has an alias, a member whose alias is among the grouped aliases is skipped, and the rest contribute their `get_group_by_cols`, so that a model's columns contribute themselves and an aggregate contributes nothing. **From the ordering**, each expression that is not a reference to the select list contributes its `get_group_by_cols`, a comment saying that a reference needs nothing since every selected expression is already grouped by; and none of them contributes where the ordering is the model's own, which is told below. **From the having**, each column `WhereNode.get_group_by_cols` collects from the having tree, where a lookup collects from its left side, and from its right side too where that is an expression, so that a comparison of an aggregate contributes nothing and a comparison of a column contributes the column (`django/db/models/sql/where.py:WhereNode.get_group_by_cols`, `django/db/models/lookups.py:Lookup.get_group_by_cols`).

Then `SQLCompiler.collapse_group_by` may shorten the list, and each expression is compiled. One that raises `EmptyResultSet` or `FullResultSet`, a condition that can match nothing or everything, is left out. Where the backend's `allows_group_by_select_index` is set and the expression was noted at a position of the select list, its SQL is replaced by that position; otherwise the SQL goes through the expression's `select_format`, which is what wraps a condition in `"CASE WHEN"` on a backend that cannot select a boolean. A pair already written is not written twice (`django/db/backends/base/features.py:BaseDatabaseFeatures.allows_group_by_select_index`).

```text recording=sql
tail(Ship.objects.annotate(hands=Count('crew')))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id"', ())
tail(Ship.objects.values('home').annotate(hands=Count('crew')))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1', ())
tail(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('name'))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1, "fleet_ship"."name" ORDER BY "fleet_ship"."name" ASC', ())
tail(Ship.objects.values('home').annotate(hands=Count('crew')).filter(hands__gt=1))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1 HAVING COUNT("crew_sailor"."id") > %s', (1,))
...
tail(Sailor.objects.values('signed_on__year').annotate(n=Count('id')))  ->  ('FROM "crew_sailor" GROUP BY 1', ())
...
tail(Ship.objects.annotate(hands=Count('crew')).annotate(low=Lower('name')))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", 7', ())
```

With `annotate` alone the grouping is every column of a ship, from `True`: the five columns the select list contributes, with nothing from the count; that the clause lists every column is this backend's doing, where one that allows grouping by the selected primary keys would list one. After `values("home")` it is the one column of the minimal set, written as its position; `order_by("name")` adds the column the ordering names, and the filter on the count adds nothing the minimal set lacks. The year a sailor signed on, a transform in a `values` name, is grouped by as the position of the annotation it was moved to; and a second annotation without an aggregate stands at the seventh position of the select list and is grouped by that number. Here is the assembly for one query with each source of a column:

```text recording=sql
GROUP BY and HAVING assembled: set_values and set_group_by on the query, then split_having_qualify and get_group_by in the compiler
    grouped = Ship.objects.values('home').annotate(hands=Count('crew')).filter(Q(hands__gt=1) | Q(name='Petrel')).order_by('name')
      Query.set_values(('home',))
      Query.add_annotation(annotation=Count(F(crew)), alias='hands')
      Query.set_group_by
    grouped.query.get_compiler('default').as_sql()
      SQLCompiler.as_sql
        SQLCompiler.pre_sql_setup
          SQLCompiler.get_select  ->  (2 columns, klass_info for Ship, {'home': 0, 'hands': 1})
          SQLCompiler.get_order_by  ->  ['"fleet_ship"."name" ASC']
          WhereNode.split_having_qualify
            WhereNode.split_having_qualify  ->  (None, (OR: IntegerGreaterThan(Count(Col(crew_sailor, crew.Sailor.id)), 1), Exact(Col(fleet_ship, fleet.Ship.name), 'Petrel')), None)
            -> (None, (AND: (OR: IntegerGreaterThan(Count(Col(crew_sailor, crew.Sailor.id)), 1), Exact(Col(fleet_ship, fleet.Ship.name), 'Petrel'))), None)
          SQLCompiler.get_group_by
            SQLCompiler.collapse_group_by(expressions=[Col(fleet_ship, fleet.Ship.home), Col(fleet_ship, fleet.Ship.home), Col(fleet_ship, fleet.Ship.name), Col(fleet_ship, fleet.Ship.name)], having=[Col(fleet_ship, fleet.Ship.name)])  ->  [Col(fleet_ship, fleet.Ship.home), Col(fleet_ship, fleet.Ship.home), Col(fleet_ship, fleet.Ship.name), Col(fleet_ship, fleet.Ship.name)]
            -> ['1', '"fleet_ship"."name"']
          -> (extra_select of 0, order_by of 1, group_by of 2)
        -> ('SELECT "fleet_ship"."home_id" AS "home", COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1, "fleet_ship"."name" HAVING (COUNT("crew_sailor"."id") > %s OR "fleet_ship"."name" = %s) ORDER BY "fleet_ship"."name" ASC', (1, 'Petrel'))
```

`set_values` put the home port in the select list, `add_annotation` the count among the annotations, and `set_group_by` made the tuple of the one column. In the compiler, `get_order_by` resolved the name, `split_having_qualify` sent the whole `"OR"` to the having, and `collapse_group_by` was handed the home port twice, from the minimal set and from the select list, and the name twice, from the ordering and from the having, and returned them as they were; the deduplication wrote each once, the home port as its position.

### `collapse_group_by` and the two features

`SQLCompiler.collapse_group_by` does one thing, and only where the backend's `allows_group_by_selected_pks` is set (`django/db/models/sql/compiler.py:SQLCompiler.collapse_group_by`, `django/db/backends/base/features.py:BaseDatabaseFeatures.allows_group_by_selected_pks`). It finds every expression that is the primary key column of a table, where `BaseDatabaseFeatures.allows_group_by_selected_pks_on_model` allows the model, which it does for a managed one, since a comment says an unmanaged model may stand for a view on which the reduction is not allowed; and it drops every other column of those tables, keeping any the having refers to. A comment names the reason: on such a backend the other columns are functionally dependent on the key, and grouping by the key is grouping by them. The feature is set on PostgreSQL, and on MySQL unless it is MariaDB with `"ONLY_FULL_GROUP_BY"` in its SQL mode; SQLite and Oracle have it off, and the recording switched it on for one block (`django/db/backends/mysql/features.py:DatabaseFeatures.allows_group_by_selected_pks`).

```text recording=sql
tail(Ship.objects.annotate(hands=Count('crew')))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id"', ())
tail(Ship.objects.annotate(hands=Count('crew')).order_by('home__country'))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") GROUP BY "fleet_ship"."id", "fleet_port"."country" ORDER BY "fleet_port"."country" ASC', ())
```

The five columns of a ship became one. In the second statement the ordering joined the port's table and added its country, which stays, since the port's primary key is not among the grouped columns.

`allows_group_by_select_index` is the other feature, set on every backend but Oracle, and it decides whether a selected expression is written as its position (`django/db/backends/base/features.py:BaseDatabaseFeatures.allows_group_by_select_index`, `django/db/backends/oracle/features.py:DatabaseFeatures.allows_group_by_select_index`). With it off, the expression is written out:

```text recording=sql
With allows_group_by_select_index switched off for this block: the expressions are written out where a position stood
    tail(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('home'))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."home_id" ORDER BY 1 ASC', ())
    tail(Ship.objects.values(low=Lower('name')).annotate(hands=Count('crew')))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY LOWER("fleet_ship"."name")', ())
```

## The model's ordering is dropped

A statement that groups does not take the model's default ordering, the `ordering` of its `Meta`. `SQLCompiler._order_by_pairs` decides where the ordering comes from, and where it falls back on the model's options it sets `SQLCompiler._meta_ordering` to that list ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)). `get_group_by` reads the attribute and, where it is set, adds nothing from the ordering; and `SQLCompiler.as_sql`, once it has written a `"GROUP BY"`, sets the ordering to `None` where the attribute is set, so that the `"ORDER BY"` is not written either (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`, `django/db/models/sql/compiler.py:SQLCompiler.as_sql`). That is why the first statement quoted above has no `"ORDER BY"` although a ship is ordered by name, and the statement with `order_by("name")` has one: an ordering given to the queryset is kept, and its column grouped by.

> **Why.** The documentation of aggregation gives the rule, that `"GROUP BY"` queries do not use the model's default ordering, and the reason beside it: a column the statement orders by has to be grouped by as well, so that an ordering by name would make the groups pairs of the grouped value and the name (`docs/topics/db/aggregation.txt`). The release notes of 3.1 record the change (`docs/releases/3.1.txt`).

## `split_having_qualify`

`WhereNode.split_having_qualify` returns three nodes, any of them `None`: the where part, the having part, and the qualify part, which the compiler writes as another statement around this one ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)). `pre_sql_setup` calls it with `must_group_by=True` where the query's `group_by` is not `None`; `Query.get_aggregation` calls it with nothing, to learn whether the query filters on an aggregate already (`django/db/models/sql/where.py:WhereNode.split_having_qualify`).

A tree that contains neither an aggregate nor a window is returned whole as the where part. Otherwise the method works out whether this node's children must stay together. The node's own negation is combined with the negation it was called under, by exclusive or, since a `"NOT"` outside a `"NOT"` cancels it; and the children **must remain connected**, a comment says, to keep the logic, where the node is an `"AND"` under a negation, an `"OR"` not under one, or an `"XOR"`. An `"OR"` cannot be tested half before the grouping and half after, since a row that fails the half in `"WHERE"` is gone before the half in `"HAVING"` is tested; and a negated `"AND"` is, by De Morgan's law, an `"OR"` of negations. Where the children must remain connected and the node contains an aggregate and no window, the whole node is the having part; a comment says it is much cheaper to short-circuit than to split the children.

Otherwise the children are divided: a `WhereNode` among them is split by the same method, under this node's effective negation, and its three parts go to the three lists; a leaf that contains a window goes to the qualify list, one that contains an aggregate to the having list, and any other to the where list. Then the one refusal, for a node that must remain connected and has a qualify part. Where nothing of the node belongs in `"WHERE"`, or the query does not group, the whole node goes to qualify, to be tested in the statement wrapped around this one; where the query groups and part of the node belongs in `"WHERE"`, the method raises `NotImplementedError`, for heterogeneous disjunctive predicates against window functions under conditional aggregation. A comment says the refusal is wider than it need be: it would only have to hold for a where part against a multi-valued relation, which could change what is aggregated, but that is hard to tell. Each list that is not empty becomes a node with this node's connector and negation, made by `Node.create`, and the three are returned (`django/utils/tree.py:Node.create`).

```text recording=sql
tail(Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1).filter(name='Petrel'))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") WHERE "fleet_ship"."name" = %s GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" HAVING COUNT("crew_sailor"."id") > %s', ('Petrel', 1))
tail(Ship.objects.annotate(hands=Count('crew')).filter(~Q(hands__gt=1)))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" HAVING NOT (COUNT("crew_sailor"."id") > %s)', (1,))
tail(Ship.objects.annotate(hands=Count('crew')).filter(~(Q(hands__gt=1) & Q(name='Petrel'))))  ->  ('FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" HAVING NOT (COUNT("crew_sailor"."id") > %s AND "fleet_ship"."name" = %s)', (1, 'Petrel'))
...
said(Ship.objects.annotate(hands=Count('crew')).filter(Q(hands__gt=1) | Q(name='Petrel')).query.where.split_having_qualify())  ->  (None, (AND: (OR: IntegerGreaterThan(Count(Col(crew_sailor, crew.Sailor.id)), 1), Exact(Col(fleet_ship, fleet.Ship.name), 'Petrel'))), None)
said(Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1, name='Petrel').query.where.split_having_qualify())  ->  ((AND: Exact(Col(fleet_ship, fleet.Ship.name), 'Petrel')), (AND: IntegerGreaterThan(Count(Col(crew_sailor, crew.Sailor.id)), 1)), None)
Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1).query.where.contains_aggregate, Ship.objects.annotate(hands=Count('crew')).filter(name='Petrel').query.where.contains_aggregate  ->  (True, False)
```

Two filters, which `Query.add_q` joins under `"AND"`, are divided: the name is tested in `"WHERE"` and the count in `"HAVING"`. A negated comparison of the count goes to `"HAVING"` with its `"NOT"`. A negated `"AND"` of the two goes whole, and the three lines of answers at the end are the parts themselves: the `"OR"` of a count and a name is one having node, the `"AND"` of the same two is a where node of the name and a having node of the count, and the last line is the mark the method reads first, `contains_aggregate` on the tree, true for a filter on the count and false for one on the name.

```text figure=where-having-split
filter(Q(hands__gt=1) | Q(name='Petrel'))          filter(hands__gt=1, name='Petrel')

(AND:                                              (AND:
  (OR: COUNT(...) > 1,                               COUNT(...) > 1,
       name = 'Petrel'))                             name = 'Petrel')

the OR must remain connected:                      the AND may be divided, child by child:
it goes whole

WHERE    nothing                                   WHERE    (AND: name = 'Petrel')
HAVING   (AND: (OR: COUNT(...) > 1,                HAVING   (AND: COUNT(...) > 1)
              name = 'Petrel'))
QUALIFY  nothing                                   QUALIFY  nothing
```

*The two recorded trees divided by `split_having_qualify`. On the left an `"OR"` that mixes an aggregate with a column goes whole to the having part; on the right an `"AND"` of the same two conditions is split between the where part and the having part, each a node with the connector of the one it came from.*

The marks the method reads are `WhereNode.contains_aggregate` and `WhereNode.contains_over_clause`, each a cached property computed once for a tree by walking its nodes to their leaves and asking each leaf for the attribute of the same name; a `NothingNode` and an `ExtraWhere` answer `False` to both, the second with a comment calling its SQL a black box (`django/db/models/sql/where.py:WhereNode.contains_aggregate`, `django/db/models/sql/where.py:ExtraWhere`). A leaf that is a lookup computes the mark from its left side, and from its right side where that is an expression, so that a comparison of an annotation that counts carries the mark although the annotation's alias is all the filter named ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)).

## The having part in `as_sql`

`SQLCompiler.as_sql` compiles the having part as it does the where part, with `WhereNode.as_sql`, and leaves it empty where that raises `FullResultSet` ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)). It writes the clauses in the statement's order: once the `"WHERE"` is written, the grouping; and where there is one, a `distinct` with fields is refused with `NotImplementedError`, the ordering is replaced, where the query has none, by what the backend's `force_no_ordering` returns, and the model's ordering is dropped as told above; then, where there is a having part, the backend's `force_group_by` is written where no grouping was, and `"HAVING"` with the condition (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). Both backend methods return an empty list in `BaseDatabaseOperations`. MySQL's `force_no_ordering` returns an ordering by `"NULL"`, which a docstring says keeps MySQL from ordering by the grouped columns of its own accord, and SQLite's `force_group_by` returns `"GROUP BY TRUE"` on a version before 3.39, so that a `"HAVING"` without a `"GROUP BY"` is accepted (`django/db/backends/base/operations.py:BaseDatabaseOperations.force_no_ordering`, `django/db/backends/mysql/operations.py:DatabaseOperations.force_no_ordering`, `django/db/backends/sqlite3/operations.py:DatabaseOperations.force_group_by`).

The two clauses are seen together without the select list that brought them in the narrowed query of `Query.exists`, which [Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md) tells:

```text recording=sql
Ship.objects.annotate(hands=Count('crew')).filter(hands__gt=1).exists()
...
          SQL SELECT %s AS "a" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" HAVING COUNT("crew_sailor"."id") > %s LIMIT 1 with params (1, 1)
```

The statement selects a constant and groups by every column of a ship, the tuple that `exists` had `set_group_by` fix before it cleared the select list, and the filter on the count stands in `"HAVING"`. `get_aggregation` reads the same having part to decide that a query already aggregates, and takes such a query inside a subquery rather than add its own aggregates to a statement that groups ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)).
