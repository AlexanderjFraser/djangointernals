---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The query: what a `Query` holds, and how it is copied

A `Query` is the description of one statement, kept apart from any backend: the tables it reads under their aliases, its where tree, what it selects and annotates, how it groups, orders and limits. `Query.clone` copies it cheaply enough that every method of a queryset can work on a copy, and `Query.chain` makes the copy ready for the next method, resetting what one method must not inherit from the last.

The query has three things to be. It has to be a description of a statement that knows no backend, so that the same queryset can be sent to any database a project has and the backend's part can wait until the rows are wanted. It has to be copied at every step, because a queryset's methods return clones and the queryset a program holds must not change under it ([Clones: how a queryset is built](../querysets/chaining.md)), and a copy of something that holds a tree of joins and a tree of conditions must be cheap. And its reference counts have to be put back when the compiler has finished with it, since a queryset may be evaluated more than once. The first of these is in what the query holds, the second in `clone`, and the third in the compiler's habit of counting references and putting them back ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)).

## What a new query holds

`Query.__init__` takes a model and sets up a handful of containers, all of them empty (`django/db/models/sql/query.py:Query.__init__`). Recorded from a running Django, where a line is an attribute of the instance and what it holds:

```text recording=sql
What a new Query holds: vars(Query(Sailor)), an attribute to a line
    model: Sailor
    alias_refcount: {}
    alias_map: {}
    alias_cols: True
    external_aliases: {}
    table_map: {}
    used_aliases: set()
    where: (AND: )
    annotations: {}
    extra: {}
    _filtered_relations: {}
```

Everything else a query can hold is a class attribute of `Query`, which an instance reads until a method sets its own, apart from `base_table`, a cached property worked out from the alias map the first time it is read (`django/db/models/sql/query.py:Query.base_table`). That is why a new query is small, and why most of a clone's work is copying the few containers that are an instance's own. The class attributes, recorded the same way:

```text recording=sql
The class attributes a Query falls back on until something sets one on the instance: vars(Query), an attribute to a line
    alias_prefix: 'T'
    empty_result_set_value: None
    subq_aliases: {'T'}
    compiler: 'SQLCompiler'
    base_table_class: BaseTable
    join_class: Join
    default_cols: True
    default_ordering: True
    standard_ordering: True
    filter_is_sticky: False
    subquery: False
    contains_subquery: False
    select: ()
    group_by: None
    order_by: ()
    low_mark: 0
    high_mark: None
    distinct: False
    distinct_fields: ()
    select_for_update: False
    select_for_update_nowait: False
    select_for_update_skip_locked: False
    select_for_update_of: ()
    select_for_no_key_update: False
    select_related: False
    max_depth: 5
    values_select: ()
    selected: None
    annotation_select_mask: None
    _annotation_select_cache: None
    combinator: None
    combinator_all: False
    combined_queries: ()
    extra_select_mask: None
    _extra_select_cache: None
    extra_tables: ()
    extra_order_by: ()
    deferred_loading: (set(), True)
    explain_info: None
```

Read together, the two lists and the cached `base_table` are the whole description. The table below groups them by what part of the statement each serves and says which section of this chapter tells it; a bare name is an attribute of `Query`.

| part of the statement | attributes | told in |
|---|---|---|
| the tables | `alias_map`, the aliases in the order they were made, each to a `BaseTable` or a `Join`; `alias_refcount`, how many things refer to each; `table_map`, each table's aliases; `used_aliases`, the aliases the last filter made, kept across one `chain` where `filter_is_sticky` is set; `external_aliases`, the aliases of an outer query; `alias_prefix` and `subq_aliases`, the letter new aliases take and the letters in use; `base_table`, the first alias; `extra_tables`, the tables `extra` adds | [Tables and joins: the alias map and join promotion](joins.md), [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md) |
| the conditions | `where`, a `WhereNode`; `_filtered_relations`, by alias | [The where clause: `build_filter`, `add_q` and `WhereNode`](where.md) |
| what is selected | `select` and `default_cols`, the columns asked for or the model's own; `values_select` and `selected`, what `values` named; `annotations` with `annotation_select_mask` and its cache, the annotations and which are selected; `extra` with `extra_select_mask` and its cache; `deferred_loading`, the fields to leave out or to keep; `select_related` and `max_depth` | [The SELECT clause: `get_select`, the select mask and `klass_info`](select.md) |
| grouping | `group_by`, `None`, `True` or a tuple of expressions | [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md) |
| ordering and distinct | `order_by`, `default_ordering`, `standard_ordering`, `extra_order_by`; `distinct` and `distinct_fields` | [ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md) |
| the rows wanted | `low_mark` and `high_mark`, the slice; `select_for_update` and its four companions, the lock | [below](#limits-and-a-query-that-matches-nothing), and [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md) |
| a compound statement | `combinator`, `combinator_all`, `combined_queries` | [Two queries into one: `combine` and `get_combinator_sql`](combining.md) |
| the statement's kind | `compiler`, the name of the compiler class; `explain_info`, the format and options when the statement is to be explained | below, and [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md) |
| a query inside another | `subquery` and `contains_subquery`, whether it is one and whether it holds one; `empty_result_set_value`, what it is worth as a column when it can match nothing | [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md) |
| the next method | `filter_is_sticky`, whether `used_aliases` survives the next `chain`; `alias_cols`, whether a column names its table | [below](#chain-a-copy-ready-for-the-next-method); below |

*What a `Query` holds, by the part of the statement each attribute describes.*

`Query.model` is the model class, and `Query.get_meta` returns its options, from which `names_to_path` starts walking a name; the docstring says a subclass may start elsewhere, and none in Django does (`django/db/models/sql/query.py:Query.get_meta`). `Query.compiler` is a string, the name of a compiler class that the connection's operations object turns into a class when the query asks for a compiler: `"SQLCompiler"` for a select, and `"SQLUpdateCompiler"`, `"SQLInsertCompiler"`, `"SQLDeleteCompiler"` or `"SQLAggregateCompiler"` on the subclasses of `Query` that write the other statements ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md), [Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)). A backend can put its own compilers under those names, and the name rather than the class is what lets it (`django/db/backends/base/operations.py:BaseDatabaseOperations.compiler`). `Query.alias_cols` is off only for a query made to resolve the expressions of a constraint, an index or a generated field, where a column stands without a table's alias (`django/db/models/sql/query.py:Query._get_col`).

## The query after two methods

A filter across two relations and an ordering leave the following on the query. Here q is the query of the sailors whose ship's home port is Bergen and who signed on before 2020, ordered by the most recent signing, as `filter` and `order_by` left it; each line below is a question put to the running Django and its answer, and the `alias_map` lines write out the alias map an entry to a line, with the count of references to each; the block's last two lines, quoted under [`__str__` and `sql_with_params`](#str__-and-sql_with_params), are left out:

```text recording=sql
q = Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020).order_by('-signed_on').query
brief(q.model), q.default_cols, q.select, q.order_by, q.default_ordering, q.standard_ordering, q.low_mark, q.high_mark  ->  ('Sailor', True, (), ('-signed_on',), True, True, 0, None)
where_said(Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020))  ->  (AND: Exact(Col(fleet_port, fleet.Port.name), 'Bergen'), YearLt(ExtractYear(Col(crew_sailor, crew.Sailor.signed_on)), 2020))
list(q.alias_map), q.alias_refcount, q.table_map, sorted(q.used_aliases)  ->  (['crew_sailor', 'fleet_ship', 'fleet_port'], {'crew_sailor': 2, 'fleet_ship': 1, 'fleet_port': 1}, {'crew_sailor': ['crew_sailor'], 'fleet_ship': ['fleet_ship'], 'fleet_port': ['fleet_port']}, [])
alias_map['crew_sailor']: BaseTable(crew_sailor), referenced 2
alias_map['fleet_ship']: Join(fleet_ship, from crew_sailor via Sailor.ship, INNER JOIN, not nullable), referenced 1
alias_map['fleet_port']: Join(fleet_port, from fleet_ship via Ship.home, INNER JOIN, not nullable), referenced 1
q.annotations, q.annotation_select, q.deferred_loading, q.group_by, q.combinator, q.subquery  ->  ({}, {}, (frozenset(), True), None, None, False)
```

The filter left three tables in the alias map and two lookups in the where tree, with the names of the filter gone: each lookup holds a `Col`, directly or under a transform, which names a table alias and a field, so nothing has to be looked up again when the statement is written ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)). The ordering is still the string it was given, `'-signed_on'`, since `Query.add_ordering` checks a name and keeps it, and the compiler resolves it when the statement is written ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)). The select list is empty and `default_cols` is true, which means every concrete field of the model. And `used_aliases` is empty, though the filter made three aliases: `chain` emptied it when the queryset cloned the query for `order_by`, as [`chain`: a copy ready for the next method](#chain-a-copy-ready-for-the-next-method) tells.

The reference counts say how many things hold each alias: the base table is counted once more each time a condition starts its walk there, which is the second count above, and a join whose count falls to zero stays in the map and is not written ([Tables and joins: the alias map and join promotion](joins.md) has the counting).

## `__str__` and `sql_with_params`

`Query.sql_with_params` asks for a compiler for the default database and returns what its `as_sql` returns, the statement with `%s` for each parameter and the tuple of parameters; `Query.__str__` returns the first with the second substituted into it by Python's `%` (`django/db/models/sql/query.py:Query.sql_with_params`, `django/db/models/sql/query.py:Query.__str__`). The docstring of `__str__` says what the substitution is not: the values are not quoted as the database would quote them, since quoting is the driver's work at execution. Here the query of [The query after two methods](#the-query-after-two-methods), both ways, in the last two lines of the block quoted there:

```text recording=sql
The query of Sailor.objects.filter(ship__home__name='Bergen', signed_on__year__lt=2020).order_by('-signed_on'): what the two methods left on it
    str(q)  ->  'SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE ("fleet_port"."name" = Bergen AND "crew_sailor"."signed_on" < 2020-01-01 00:00:00) ORDER BY "crew_sailor"."signed_on" DESC'
    q.sql_with_params()  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" INNER JOIN "fleet_ship" ON ("crew_sailor"."ship_id" = "fleet_ship"."id") INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") WHERE ("fleet_port"."name" = %s AND "crew_sailor"."signed_on" < %s) ORDER BY "crew_sailor"."signed_on" DESC', ('Bergen', '2020-01-01 00:00:00'))
```

So `str(queryset.query)` is for reading, and is a statement of the default database's dialect whatever database the queryset would run on; it is not a statement the database would accept as it stands, as the unquoted Bergen shows. A compiler for the connection the queryset will use is what `QuerySet.query` cannot give, and that is why the string is not the SQL that is sent ([Evaluation and the result cache](../querysets/evaluation.md)).

## `clone`: the containers are copied, and what they hold is shared

`Query.clone` is what makes a queryset's clone cheap. It makes an empty object, gives it the query's class, and copies the instance's dictionary across in one go, so that every attribute the instance has set is on the clone, shared; then it replaces, one by one, the containers that the next method will change in place, with a copy each (`django/db/models/sql/query.py:Query.clone`). Here q is the query of [The query after two methods](#the-query-after-two-methods) and c its clone; each line is a question and its answer:

```text recording=sql
Query.clone: the containers are copied, and what they hold is shared
    c = q.clone()
    c is q, type(c) is type(q), c.model is q.model  ->  (False, True, True)
    c.where is q.where, c.where.children[0] is q.where.children[0], c.where.children[1].lhs is q.where.children[1].lhs  ->  (False, True, True)
    c.alias_map is q.alias_map, c.alias_map['fleet_ship'] is q.alias_map['fleet_ship'], c.alias_refcount is q.alias_refcount, c.table_map is q.table_map  ->  (False, True, False, False)
    c.order_by is q.order_by, c.select is q.select, c.deferred_loading is q.deferred_loading, c.annotations is q.annotations, c.used_aliases is q.used_aliases  ->  (True, True, True, False, False)
    sorted(set(vars(c)) ^ set(vars(q)))  ->  ['base_table']
    d = Ship.objects.select_related('home').annotate(hands=Count('crew')).query
    e = d.clone()
    e.select_related is d.select_related, e.select_related, e.annotations is d.annotations, e.annotations['hands'] is d.annotations['hands']  ->  (False, {'home': {}}, False, True)
    e.annotation_select_mask is d.annotation_select_mask, e._annotation_select_cache, d._annotation_select_cache is not None  ->  (True, None, False)
```

The containers copied are the four dictionaries of the alias machinery, `alias_map`, `alias_refcount`, `table_map` and `external_aliases`; the where tree, through `WhereNode.clone`, which makes a new node for each node and keeps each lookup as it is, since a lookup is not changed in place once built; `annotations`, `extra`, `_filtered_relations` and `used_aliases`; and the two masks and the extra-select cache where they are set. Four things are treated specially. `select_related`, when it is a dictionary of names nested in names, is deep-copied, since a later `select_related` writes into the nesting. `combined_queries` are each cloned, so that a method on a union does not reach into the parts the union was made from. `subq_aliases` is copied only when the instance has one of its own. And the cached `base_table` is dropped from the clone, so that it is worked out again from the clone's alias map.

What is not copied is shared: the model; the tuples, since a method that changes `order_by` or `select` builds a new tuple rather than appending; the `Join` objects in the alias map, which are replaced rather than changed when a join is promoted or demoted ([Tables and joins: the alias map and join promotion](joins.md)); and the expressions, since an annotation is a resolved expression that nothing changes afterwards. The one container that is not copied at all is `_annotation_select_cache`, which `clone` sets to `None`: the comment at that line says the cache must hold the same objects as `annotations` does, and a copied cache would not, so the clone builds its own the next time `annotation_select` is read with a mask set, which is the only case in which that property caches anything. The last question of the quote above is that attribute: the mask is the same object on both because neither has one, the clone's cache is `None`, and so is the original's, since with no mask `annotation_select` returns `annotations` itself and caches nothing.

Two more things are built on `clone`. `Query.__deepcopy__` returns a clone, so that a deep copy of a queryset, which `QuerySet.__deepcopy__` makes attribute by attribute, does not walk the whole tree of expressions (`django/db/models/sql/query.py:Query.__deepcopy__`). And `Query.relabeled_clone` clones and then renames aliases throughout the clone with `change_aliases`, the relabelling every expression offers, which is reached when a tree that holds the query, as a `Subquery` or as the right side of a lookup, is relabelled (`django/db/models/sql/query.py:Query.relabeled_clone`); the renaming a query gets when it is put inside another is `bump_prefix`'s, and [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md) has it.

## `chain`: a copy ready for the next method

`QuerySet._chain` does not call `Query.clone`; through `QuerySet._clone` it calls `Query.chain`, which clones and then does three things to the clone (`django/db/models/sql/query.py:Query.chain`). It empties `used_aliases`, the set of aliases the last filter made, unless `filter_is_sticky` is set, and resets that flag either way. It changes the clone's class where it is asked to, which is how `QuerySet.update` turns a query into an `UpdateQuery` without building one from scratch ([Creating, updating and deleting through a queryset](../querysets/writing.md)). And where the clone's class has a `_setup_query`, it calls it, which is how an `UpdateQuery` comes to have its list of values to set and its related updates after a change of class, since `__init__` did not run (`django/db/models/sql/subqueries.py:UpdateQuery._setup_query`).

```text recording=sql
Query.chain: a clone ready for the next method, with used_aliases emptied unless the filter is sticky, and perhaps of another class
    sorted(sticky.used_aliases), sorted(sticky.chain().used_aliases)  ->  (['crew_sailor', 'fleet_port', 'fleet_ship'], [])
    sorted(sticky.chain().used_aliases), sticky.chain().filter_is_sticky  ->  (['crew_sailor', 'fleet_port', 'fleet_ship'], False)
    type(u).__name__, u.compiler, u.values, u.related_updates, u.related_ids, where_said(Ship.objects.filter(tonnage__gt=500))  ->  ('UpdateQuery', 'SQLUpdateCompiler', [], {}, None, (AND: IntegerGreaterThan(Col(fleet_ship, fleet.Ship.tonnage), 500)))
    type(Ship.objects.all().query.chain()).__name__, type(u.chain()).__name__, type(u.chain(klass=Query)).__name__  ->  ('Query', 'UpdateQuery', 'Query')
```

Here sticky is the query of a filter across two relations, asked before and after `filter_is_sticky` was set on it by hand, and u is a query of ships chained into an `UpdateQuery`, which the update compiler's `pre_sql_setup` chains back into a plain `Query` when it needs to select the keys to update ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md)).

The point of emptying `used_aliases` is join reuse: a join across a relation that can reach several rows may be reused by a later condition of the same `filter` call and not by a later call, which is why two calls that each cross a many-to-many relation join its table twice and one call with two conditions joins it once ([Tables and joins: the alias map and join promotion](joins.md) has the rule). `used_aliases` is where the aliases of the current call are kept, and `chain` draws the line between one call and the next. A **sticky filter**, a queryset whose query has `filter_is_sticky` set, is a related manager's way of crossing that line once: it leaves the set in place for the one method that follows, so that a filter on a voyage's ports of call shares the join the manager made ([Clones: how a queryset is built](../querysets/chaining.md)).

## Limits, and a query that matches nothing

A slice of a queryset becomes two marks on the query. `Query.set_limits` takes a low bound, a high bound or both and adds each to the query's low mark, the high bound clamped to the high mark the query already has and the low bound to the high mark it then has, so that a slice of a slice is a slice of the original rows; when the two marks meet the query is set empty (`django/db/models/sql/query.py:Query.set_limits`). `Query.clear_limits` puts the marks back to their defaults. `Query.is_sliced` is whether either mark has moved, and it is what a number of a queryset's methods test before refusing to work on a sliced queryset ([Evaluation and the result cache](../querysets/evaluation.md)); `Query.can_filter` is its negation, and `Query.has_limit_one` is whether exactly one row is asked for, which `Exact` requires of a queryset given as a value ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)). The compiler turns the marks into the backend's `"LIMIT"` and `"OFFSET"`, which SQLite writes as `LIMIT 5` for a high mark of five ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)).

`Query.set_empty` adds a `NothingNode` to the where tree, a node that raises `EmptyResultSet` when it is asked for its SQL, and does the same to every combined query; `Query.is_empty` is whether such a node stands directly under the where tree's root (`django/db/models/sql/query.py:Query.set_empty`, `django/db/models/sql/where.py:NothingNode`). That is what `QuerySet.none` leaves on the query, and what a slice whose bounds meet leaves. A query made empty some other way, by a comparison with an empty list that no `OR` or `XOR` above it can set aside, has no such node and `is_empty` says it is not, though its statement is not sent either, unless the compiler was made with `elide_empty` off, as `get_aggregation` makes it when an aggregate has no value for an empty set; [The where clause: `build_filter`, `add_q` and `WhereNode`](where.md) has what each kind of empty does when the statement is written. `Query.has_filters` is the where tree itself, true when it has any child.

## `RawQuery`: a statement with nothing to compile

A raw queryset carries a `RawQuery` where a queryset carries a `Query`, and the two have little in common but the name. A `RawQuery` holds the SQL a program wrote, its parameters and the alias of a database, and executes itself: `RawQuery._execute_query` adapts each parameter with the backend's `adapt_unknown_value`, since the type a value is meant for is not known, takes a cursor and runs the statement; iterating a `RawQuery` executes it afresh each time, and `RawQuery.get_columns` executes it where it has not been run, to read the column names from the cursor's description (`django/db/models/sql/query.py:RawQuery`). Its `__str__` substitutes the parameters as a `Query`'s does, as a tuple or a dictionary by their type.

A `RawQuery` also mirrors four attributes of a `Query`, the two marks and the two empty selections, so that, the comment beside them says, a compiler can be used to process the results: the raw iterable makes a `SQLCompiler` for the raw query all the same, to apply the converters of the backend and of the model's fields to the rows the cursor returns (`django/db/models/query.py:RawModelIterable.__iter__`). What a raw queryset does with the rows is [Raw querysets](../querysets/raw.md).

## The neighbours

A query is made by a queryset and built up through the queryset's methods, each of which is told in [QuerySets](../querysets.md) with what it leaves here. The compiler reads the query and writes the statement, and every attribute above is read somewhere in [The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md) or the sections on its clauses. A query inside another is a `Query` resolved as an expression ([Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)), and the subclasses that write an insert and an update add a few attributes each to what is here, while the one that writes a delete adds no attribute, only its compiler's name and two methods ([INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md)).
