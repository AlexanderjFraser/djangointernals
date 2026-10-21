---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What the where tree writes: `WhereNode`

`WhereNode.as_sql` compiles the children of the where tree in order and joins what comes back, counting the children that match nothing or everything and raising `EmptyResultSet` or `FullResultSet` for the node itself as soon as the count decides it. `NothingNode` is a child that matches nothing, and `ExtraWhere` one that holds SQL written by hand.

## `WhereNode.as_sql`: what the tree writes

`WhereNode.as_sql` compiles each child through `SQLCompiler.compile` and joins what comes back with the connector (`django/db/models/sql/where.py:WhereNode.as_sql`, `django/db/models/sql/compiler.py:SQLCompiler.compile`). What makes it more than a join of strings is that a child may have no SQL to give. A child raises `EmptyResultSet` where it can match nothing, as `In` does for an empty list, and `FullResultSet` where it matches everything, as a negated empty node does; and a child whose SQL is the empty string counts as matching everything too. The node counts. Under `"AND"`, one empty child makes the node empty and every child must be full for the node to be full; under `"OR"` and `"XOR"`, one full child makes the node full and every child must be empty for it to be empty. When either count is reached the node raises the same exception for itself, the other way round if it is negated, so the news travels up the tree node by node. A node whose children all matched everything, and an empty node, raise `FullResultSet` at the end.

What the compiler does with the two is in `SQLCompiler.as_sql` (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). `FullResultSet` from the root means no `"WHERE"` clause. `EmptyResultSet` is raised on to `SQLCompiler.execute_sql`, which sends nothing and answers with no rows ([The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md)); where the compiler was made with `elide_empty=False`, as a part of a compound statement may be, the clause becomes `0 = 1` instead and the statement is sent.

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

An `"OR"` with an empty child writes its other child alone; an `"AND"` with one is empty, and `exclude(pk__in=[])` is the negation of empty, which is everything, as is an `"OR"` with such a negation in it. `Q()` makes an empty node, which `add_q` does not add, and `Q() | Q(name='Petrel')` is the one condition. The queryset `QuerySet.none` returns holds a `NothingNode`; `filter(pk__in=[])` holds an `In`, and `Query.is_empty` is true of the first alone, since it looks for the node and not for what a lookup will raise ([The query: what a `Query` holds, and how it is copied](../query/anatomy.md)). The last four lines put the question to the tree itself.

When no child raised, the SQL is the children's joined by `" AND "`, `" OR "` or `" XOR "`; a negated node writes `NOT (...)`, and a node of more than one child, or one that is a resolved expression, is put in parentheses. The comment on the negated case says some backends, Oracle at least, need the parentheses even around a single expression.

A backend that has no `"XOR"` gets a rewrite. Where `BaseDatabaseFeatures.supports_logical_xor` is false, which it is on every backend but MySQL's, an `"XOR"` node compiles itself as an `"AND"` of two things: an `"OR"` of the same children, and an `Exact` of `1` with the sum of a `Case` for each child that is `1` where the child holds and `0` otherwise, the sum taken modulo 2 through `Mod` where there are more than two children (`django/db/backends/base/features.py:BaseDatabaseFeatures.supports_logical_xor`, `django/db/models/functions/math.py:Mod`). The comment gives the rule: an n-ary `"XOR"` is true when an odd number of its operands are.

```text recording=sql
XOR on SQLite, which has no XOR of its own: an OR beside a count of the true operands
    tail(Ship.objects.filter(Q(name='Petrel') ^ Q(tonnage__gt=1000)))  ->  ('FROM "fleet_ship" WHERE (("fleet_ship"."name" = %s OR "fleet_ship"."tonnage" > %s) AND %s = (CASE WHEN "fleet_ship"."name" = %s THEN %s ELSE %s END + CASE WHEN "fleet_ship"."tonnage" > %s THEN %s ELSE %s END)) ORDER BY "fleet_ship"."name" ASC', ('Petrel', 1000, 1, 'Petrel', 1, 0, 1000, 1, 0))
    tail(Ship.objects.filter(Q(name='Petrel') ^ Q(tonnage__gt=1000) ^ Q(home__name='Leith')))  ->  ('FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE (("fleet_ship"."name" = %s OR "fleet_ship"."tonnage" > %s OR "fleet_port"."name" = %s) AND %s = (MOD(((CASE WHEN "fleet_ship"."name" = %s THEN %s ELSE %s END + CASE WHEN "fleet_ship"."tonnage" > %s THEN %s ELSE %s END) + CASE WHEN "fleet_port"."name" = %s THEN %s ELSE %s END), %s))) ORDER BY "fleet_ship"."name" ASC', ('Petrel', 1000, 'Leith', 1, 'Petrel', 1, 0, 1000, 1, 0, 'Leith', 1, 0, 2))
    connection.features.supports_logical_xor  ->  False
```

With two children the sum must be 1, so the `Mod` is left out; with three it is taken modulo 2.

Before the compiler asks the tree for SQL it divides it: `WhereNode.split_having_qualify` returns the parts of the tree that go into `"WHERE"`, those that compare an aggregate and go into `"HAVING"`, and those that refer to a window and cannot stand in either, keeping together what a negation or an `"OR"` must keep together ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](../sql/grouping.md), [Window expressions: `Window` and `WindowFrame`](windows.md)).

## The rest of `WhereNode`

The tree is copied, relabelled and resolved as the query is: `WhereNode.clone` makes a new node for each node of the tree and keeps every other child as it is, cloning only a child that has a `clone` method, which a lookup has not, so the lookups of a clone are the original's, and `WhereNode.relabel_aliases` renames aliases in place, by a map from old to new, recursing into a child node and replacing any other child with its `relabeled_clone`, which is what a query inside another and the right side of a `combine` go through (`django/db/models/sql/where.py:WhereNode.clone`, `django/db/models/sql/where.py:WhereNode.relabel_aliases`) ([The query: what a `Query` holds, and how it is copied](../query/anatomy.md), [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](../query/subqueries.md)). `WhereNode.resolve_expression`, for a tree that already stands as an expression and is resolved again, as the tree a `Q` given to `annotate` became is when a filter on the annotation compiles it as a lookup's left side, clones the tree, resolves against the query the `lhs` and the `rhs` of each leaf that has them, setting the result on the leaf itself, so that the original tree's leaves are resolved too, and marks the clone `resolved`, which is what puts a single-child node in parentheses when it is written (`django/db/models/sql/where.py:WhereNode.resolve_expression`).

## `NothingNode` and `ExtraWhere`

`NothingNode` is a child that matches nothing: it raises `EmptyResultSet` whenever its SQL is asked for (`django/db/models/sql/where.py:NothingNode`). `Query.set_empty` adds one to the tree under `"AND"`, and to the tree of each combined query, and `Query.is_empty` is whether one stands directly under the root ([The query: what a `Query` holds, and how it is copied](../query/anatomy.md)); `QuerySet.none` is what calls it.

`ExtraWhere` is SQL a program wrote, taken as it is: `QuerySet.extra` hands its `where` list and `params` to `Query.add_extra`, which puts them in one `ExtraWhere` under `"AND"` when either is given (`django/db/models/sql/where.py:ExtraWhere`, `django/db/models/sql/query.py:Query.add_extra`). Its `as_sql` wraps each string in parentheses and joins them with `" AND "`, and gives the parameters back as a list. It carries no aggregate and no window, by the comment's admission that its contents are a black box, so it is always a `"WHERE"` part.

```text recording=sql
ExtraWhere: SQL a program wrote, taken as it is
    tail(Ship.objects.extra(where=['tonnage > %s', 'home_id = 1'], params=[500]))  ->  ('FROM "fleet_ship" WHERE (tonnage > %s) AND (home_id = 1) ORDER BY "fleet_ship"."name" ASC', (500,))
    where_said(Ship.objects.extra(where=['tonnage > %s'], params=[500]))  ->  (AND: an ExtraWhere)
    Ship.objects.extra(where=['tonnage > %s'], params=[500]).query.where.children[0].as_sql()  ->  ('(tonnage > %s)', [500])
    sql_of(Ship.objects.filter(name='Petrel').extra(where=['tonnage > 0']).filter(pk__in=[]))  ->  raises EmptyResultSet: 
```

The last line is the counting at work: the extra condition, which can neither match nothing nor everything, is in an `"AND"` with an `In` that can match nothing, and the node is empty.

`Query.build_where` builds a node for one condition with no joins allowed and returns it without adding it, which is how a check constraint's condition is compiled, and `Query.clear_where` replaces the tree with an empty one (`django/db/models/sql/query.py:Query.build_where`, `django/db/models/constraints.py:CheckConstraint._get_check_sql`, `django/db/models/sql/query.py:Query.clear_where`).
