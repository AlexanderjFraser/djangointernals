---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Annotations, ordering and the other methods that change the query

`QuerySet.annotate`, `QuerySet.alias`, `QuerySet.order_by`, `QuerySet.reverse`, `QuerySet.distinct`, `QuerySet.extra`, `QuerySet.select_for_update` and `QuerySet.none` each return a queryset with something left on its query, and send nothing to the database. The properties `QuerySet.ordered` and `QuerySet.totally_ordered` report on a queryset's ordering, and `EmptyQuerySet` is how code asks whether a queryset has been made empty.

Most of what a queryset is asked to do, it does not do. It writes the request down. Each method here takes what `QuerySet._chain` gives it, leaves something on that queryset's query, and returns it ([Clones: how a queryset is built](chaining.md)). The query is a description: an ordering is a tuple of names and expressions, a lock is a flag with its options, a distinct clause is a flag and a tuple of names (`django/db/models/sql/query.py:Query`). The compiler reads them when the queryset is evaluated and writes the statement, which is the subject of [From QuerySet to SQL](../sql.md).

So the questions to put to each method are small ones: what it is for, what it leaves, where, and what it checks at the moment it is called. Some look at the names they are given at once, and some leave a mistake for the compiler to find. Some refuse a queryset that has been sliced, some a **combined queryset**, one made by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference`, and some both: the table in the last section says which.

## `annotate` and `alias`

An **annotation** is an expression that the query computes for each row and keeps under a name: a function of a column, a count of related rows, a comparison. `QuerySet.annotate` adds annotations that the statement selects. `QuerySet.alias` adds annotations that it does not select, for a later `QuerySet.filter` or `QuerySet.order_by` to refer to. Each refuses a combined queryset, and each is otherwise one call of `QuerySet._annotate`, with `select=True` from the one and `select=False` from the other (`django/db/models/query.py:QuerySet._annotate`).

### The names

`_annotate` takes expressions by keyword, under the names the caller gives, and by position, where the expression has to supply its own name. It first requires every value to be an expression, which to this check is anything that has an attribute `"resolve_expression"`, so that a `Q` passes, and a `FilteredRelation`, a relation given under a new name with a condition for its join ([`filter`, `exclude` and `Q` objects](filters.md)). Anything else raises `TypeError` from `QuerySet._validate_values_are_expressions`, with a message that names `annotate` also when the method called was `alias`.

An expression given by position is filed under its default alias, a property that `Aggregate` declares: `Aggregate.default_alias`. An aggregate of one named thing answers with that name and its own name in lower case, as a `Count` of `"crew"` is `"crew__count"`, and raises `TypeError` for anything less plain: an aggregate of an expression that has no name of its own, as `F("tonnage") + 1` has none, or one with a filter (`django/db/models/aggregates.py:Aggregate.default_alias`). `_annotate` turns that error, and the `AttributeError` of an expression that has no such property, into one `TypeError` saying that an alias is required. Where a default alias is also a keyword of the same call, it raises `ValueError`.

Then the names are checked against the model. `_annotate` gathers the name of every field that `Options.get_fields` returns, and, where it has one, its **attname**, the name of the attribute that holds its value, as `"home_id"` is for a ship's foreign key to its home port (`django/db/models/options.py:Options.get_fields`). That includes the relations that point at the model from elsewhere, under the names a filter would use for them. An annotation whose name is among them raises `ValueError`. `"pk"` is among them only where a field has that name, as the model checks require of a `CompositePrimaryKey`, so where no field has it an annotation may be named `"pk"` (`django/db/models/fields/composite.py:CompositePrimaryKey._check_field_name`).

After `QuerySet.values` or `QuerySet.values_list` the names it checks against are the queryset's `QuerySet._fields` instead, the names that call was given ([`values` and `values_list`: rows as dictionaries and tuples](values.md)).

What follows was recorded from a running Django, on SQLite, over the models and rows that the chapter's opening page, [QuerySets](../querysets.md), lists: a Ship there has a name, a tonnage and a foreign key to its home Port, and a Sailor has a foreign key to its Ship, whose other end is the ship's `"crew"`. Each line is an expression that was evaluated, with its value after `->`, or the exception it raised; a line that begins `SQL` under it is a statement it sent, as Django handed it to its cursor.

```text recording=querysets
Ship.objects.annotate(Count('crew'))[0].crew__count  ->  2
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", COUNT("crew_sailor"."id") AS "crew__count" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" LIMIT 1
Ship.objects.annotate(tonnage=Count('crew'))  ->  raises ValueError: The annotation 'tonnage' conflicts with a field on the model.
Ship.objects.annotate(Count('crew') + 1)  ->  raises TypeError: Complex annotations require an alias
```

The count given by position came back on the instance under its default alias. A count with one added to it is a combination of two expressions, which has no default alias to give.

### Selected or not

Each annotation then goes to the query. A `FilteredRelation` goes to `Query.add_filtered_relation`, which is told in [`filter`, `exclude` and `Q` objects](filters.md). Anything else goes to `Query.add_annotation`, with the flag that says whether it is selected (`django/db/models/sql/query.py:Query.add_annotation`). That method resolves the expression against the query, which is when the names inside it are looked up and the joins it needs are added, and stores the result in `Query.annotations` under the name.

Whether an annotation is selected is kept apart from the annotation, in `Query.annotation_select_mask`. The mask is `None`, which means that every annotation is selected, or it is the set of the names that are. Where there is a mask, `annotate` adds its name to it. `alias` makes the mask the names selected so far, without the new one. What the compiler selects is `Query.annotation_select`, the annotations that pass the mask. A selected annotation becomes an attribute of each instance the queryset makes, or a key of each dictionary after `values` ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)).

### Grouping

An aggregate changes the shape of the statement: a count of the sailors of each ship needs the rows grouped by ship. `_annotate` sees to that as its last step. If an annotation added by this call contains an aggregate, it sets `Query.group_by`. For a queryset of instances it sets `True`, which stands for all the model's fields that are selected. After `values` it calls `Query.set_group_by`, which makes `group_by` a tuple: the columns that `values` selected, and with them what each selected annotation's `BaseExpression.get_group_by_cols` returns, which for an aggregate is nothing and for a function of a column with no aggregate in it, such as `Lower`, is the expression itself (`django/db/models/sql/query.py:Query.set_group_by`, `django/db/models/expressions.py:BaseExpression.get_group_by_cols`). `alias` sets it as `annotate` does, and an annotation that contains no aggregate leaves it alone.

```text recording=querysets
[(ship.name, ship.hands) for ship in Ship.objects.annotate(hands=Count('crew')).order_by('name')]  ->  [('Gannet', 2), ('Petrel', 2)]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" ORDER BY "fleet_ship"."name" ASC
Ship.objects.annotate(hands=Count('crew')).query.group_by, Ship.objects.values('home').annotate(hands=Count('crew')).query.group_by  ->  (True, (Col(fleet_ship, fleet.Ship.home),))
list(Ship.objects.values('home').annotate(hands=Count('crew')).order_by('home'))  ->  [{'home': 1, 'hands': 2}, {'home': 2, 'hands': 2}]
  SQL SELECT "fleet_ship"."home_id" AS "home", COUNT("crew_sailor"."id") AS "hands" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY 1 ORDER BY 1 ASC
[(ship.name, hasattr(ship, 'hands')) for ship in Ship.objects.alias(hands=Count('crew')).filter(hands__gt=1)]  ->  [('Petrel', False), ('Gannet', False)]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."id" = "crew_sailor"."ship_id") GROUP BY "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" HAVING COUNT("crew_sailor"."id") > %s with params (1,)
```

The first statement selects the count as its last column and groups by the five columns of a ship. The question after it shows the two values that `_annotate` gives `group_by`. In the second statement, `values` named the home port before the count was added, and the statement groups by that one column, written as its position in the select list. The last statement is `alias` at work: the count is in no select list, only in the `"HAVING"` clause that the filter on it became, and neither instance has an attribute for it.

So the order of `values` and `annotate` decides the grouping. Called the other way round, `annotate` has set `True` before `values` runs, and `Query.set_values`, finding `True`, fixes the grouping at all the model's concrete fields, with what the annotations still selected add to them, before it sets the fields that were named: the statement still groups by every column of the model, and `values` only chooses what is selected of each group (`django/db/models/sql/query.py:Query.set_values`).

## Ordering: `order_by` and `reverse`

A query keeps its ordering in four attributes. `Query.order_by` is a tuple of what `QuerySet.order_by` was given: names of fields, each perhaps with a minus sign in front, `"?"` for a random order, or expressions. `Query.extra_order_by` is what `extra(order_by=...)` was given. `Query.default_ordering` says whether the model's own ordering is to be used where the other two are empty, and is true on a new query. And `Query.standard_ordering` says whether directions are as written, or reversed (`django/db/models/sql/query.py:Query`). The compiler takes the first of the three sources that applies: the extra ordering, then the explicit one, then the model's (`django/db/models/sql/compiler.py:SQLCompiler._order_by_pairs`).

`QuerySet.order_by` replaces the ordering and does not add to it. On the clone it calls `Query.clear_ordering`, forced, so that it empties both `order_by` and `extra_order_by` whatever else the query holds, and told to leave `default_ordering` as it was, and then `Query.add_ordering` with its arguments (`django/db/models/query.py:QuerySet.order_by`). `add_ordering` looks at each item as it takes it. A name has to be an annotation of the query, a column of its `Query.extra`, or a path whose first step can be resolved from the model: a name whose first step cannot raises `FieldError` there, as the method is called, and a later step that cannot is left for the compiler to find. An expression is taken as it is, unless it contains an aggregate, which raises `FieldError` as well. The items are then added to `order_by`. Called with no items at all, `add_ordering` sets `default_ordering` to `False`, and that is all that `order_by()` with no arguments leaves behind: it is how a queryset is told to have no ordering (`django/db/models/sql/query.py:Query.add_ordering`).

`QuerySet.reverse` flips `standard_ordering` on the clone and touches nothing else (`django/db/models/query.py:QuerySet.reverse`). The compiler applies the flag to each name and each expression of whichever ordering it took, and leaves `"?"` as it is. Where it took none there is nothing to apply the flag to, and reversing changes nothing.

## `ordered` and `totally_ordered`

`QuerySet.ordered` and `QuerySet.totally_ordered` are properties that report on a queryset's ordering without changing it.

`ordered` says whether the queryset counts as having an ordering, and three things make it true. Anything in the query's `Query.order_by` or `Query.extra_order_by` does. Failing those, the model's default ordering, `Options.ordering`, does, provided `Query.default_ordering` still stands and the query does not group: the compiler leaves a model's ordering out of a statement that has `"GROUP BY"`, as the statement recorded for `QuerySet.alias` shows, which has `"HAVING"` and no `"ORDER BY"` though Ship has an ordering (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). And a queryset made empty by `QuerySet.none` is ordered whatever else its query holds (`django/db/models/query.py:QuerySet.ordered`, `django/db/models/options.py:Options`).

`QuerySet.first` and `QuerySet.last` read the property to decide whether to add an ordering by primary key ([`get`, `first`, `count` and the other methods that run a query at once](results.md)), and a paginator reads it to warn when it is handed a queryset with no ordering (`django/core/paginator.py:BasePaginator._check_object_list_is_ordered`).

`totally_ordered` asks for more, an ordering that its docstring calls deterministic (`django/db/models/query.py:QuerySet.totally_ordered`). It starts from `ordered`, and what is not ordered is not totally ordered. Then it takes `Query.order_by`, or, where that is empty and the default ordering stands, the model's `Options.ordering`, and looks among the items for fields of the queryset's own model. An item gives a field when it is a name, an `F`, or an `OrderBy` around an `F`, and the name is a field of the model or an annotation that is nothing but a column of the model's own table. `"pk"` settles the matter at once. What it cannot read in this way it passes over without complaint: an expression of another kind, `"?"`, a path through a relation, and a relation named by its field's name, where a comment says that ordering by a relation's name is ordering by the related model's ordering. `extra(order_by=...)` is not read at all, as the docstring says.

With the fields gathered, the answer is yes if one of them is unique and not nullable; or if together they include every field of the primary key, which is how a composite key counts; or if they include every field of one of the model's `Options.unique_together` or `Options.total_unique_constraints`, none of whose fields is nullable.

> **Changed in 6.1.** `totally_ordered` is new in 6.1 (`docs/releases/6.1.txt`).

The admin's change list, a model formset and, for a many-to-many field, the serializers read the property, and each adds the primary key to an ordering that is not total (`django/contrib/admin/views/main.py:ChangeList.get_ordering`, `django/forms/models.py:BaseModelFormSet.get_queryset`, `django/core/serializers/python.py:Serializer.handle_m2m_field`).

```text recording=querysets
Ship._meta.get_latest_by, Sailor.objects.all().ordered, Ship.objects.all().ordered, Ship.objects.order_by().ordered  ->  (None, False, True, False)
...
Ship.objects.all().totally_ordered, Ship.objects.order_by('tonnage').totally_ordered, Ship.objects.order_by('tonnage', 'pk').totally_ordered, Ship.objects.order_by('name', 'home').totally_ordered  ->  (False, False, True, False)
Ship.objects.order_by('name', 'home_id').totally_ordered  ->  True
```

The first value of the first line is the model's `Options.get_latest_by`, what `QuerySet.latest` orders by when it is given no fields, and Ship sets none. Of the rest: a queryset of sailors is not ordered, since Sailor has no ordering of its own; a queryset of ships is, by its name, until `QuerySet.order_by` with no arguments takes the default away. A ship's name and its tonnage are neither of them unique, so the default ordering and an ordering by tonnage are not total, and adding the key makes one that is. The ordering by `"name"` and `"home"` is the instructive one. Ship has a unique constraint over its name and its home port, and still that ordering does not count, because `"home"` is the name of a relation and is passed over. Written with the attname, `"home_id"`, the two cover the constraint, and the last line says `True`.

## `distinct`

`QuerySet.distinct` asks that no row come back twice. The documentation gives the case it is for: a query that spans several tables can return a row more than once (`docs/ref/models/querysets.txt`). The method leaves two things on the clone's query, through `Query.add_distinct_fields`: `Query.distinct` set to `True`, and `Query.distinct_fields` set to the names it was given, an empty tuple when it was given none (`django/db/models/query.py:QuerySet.distinct`, `django/db/models/sql/query.py:Query.add_distinct_fields`). A later call replaces both.

For the flag the statement has `"DISTINCT"` after `"SELECT"`, and the database compares rows whole. With names it is to have `"DISTINCT ON"`, under which the database compares those columns alone. The names are not looked at until the statement is composed, when the compiler asks the backend's operations for the clause, in `BaseDatabaseOperations.distinct_sql`. As the base class has it, that method raises `NotSupportedError` when it is given fields, and SQLite's operations do not override it (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.distinct_sql`).

```text recording=querysets
list(Ship.objects.distinct('name'))  ->  raises NotSupportedError: DISTINCT ON fields is not supported by this database backend
```

## `extra`

`QuerySet.extra` puts pieces of SQL that the caller wrote into the statement, for what no other method can express: the documentation calls it an old interface and a last resort (`docs/ref/models/querysets.txt`). It passes its six arguments to `Query.add_extra`, which files them in four places (`django/db/models/query.py:QuerySet.extra`, `django/db/models/sql/query.py:Query.add_extra`):

- `select=...` and `select_params=...` go to `Query.extra`, a dictionary from a name to a piece of SQL and its parameters, for the select list. The parameters are dealt out to the pieces by counting the placeholders in each, and each name is checked by `Query.check_alias`, as an annotation's is: that method raises `ValueError` for a name with whitespace, a control character, a quotation mark, a semicolon, a hash or the mark of an SQL comment in it, and warns with `RemovedInDjango2028Warning` for a percent sign (`django/db/models/sql/query.py:Query.check_alias`).
- `where=...` and `params=...` become an `ExtraWhere` node, added to the where clause with `"AND"`.
- `tables=...` is added to `Query.extra_tables`, for the `"FROM"` clause.
- `order_by=...` becomes `Query.extra_order_by`, in place of what was there, and the compiler takes it before any other ordering.

The comment over these attributes in `Query` says that their contents are appended more or less verbatim to the appropriate clause. A column selected this way reaches an instance as an annotation does, as an attribute ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)).

```text recording=querysets
list(Ship.objects.extra(select={'heavy': 'tonnage > 1000'}, order_by=['tonnage']).values_list('name', 'heavy'))  ->  [('Petrel', 0), ('Gannet', 1)]
  SQL SELECT "fleet_ship"."name" AS "name", (tonnage > 1000) AS "heavy" FROM "fleet_ship" ORDER BY "fleet_ship"."tonnage" ASC
```

The comparison is in the statement as it was written, in parentheses, and the extra ordering by tonnage has taken the place of the model's ordering by name. SQLite gives the comparison back as 0 and 1.

## `select_for_update`

`QuerySet.select_for_update` asks that the rows the statement selects be locked until the transaction ends, so that no other transaction changes them or locks them meanwhile. Its four arguments shape the lock: `nowait=True` asks that the statement fail at once where another transaction has a row locked, and `skip_locked=True` that such rows be left out; `of=(...)` names the models whose rows are to be locked where the statement selects from several, with `"self"` for the queryset's own; and `no_key=True` asks for a weaker lock, under which other transactions may still add rows that refer to the locked ones (`docs/ref/models/querysets.txt`).

On the clone's query the method sets `Query.select_for_update` to `True` and copies the four arguments to `Query.select_for_update_nowait`, `Query.select_for_update_skip_locked`, `Query.select_for_update_of` and `Query.select_for_no_key_update`. On the clone itself it sets `QuerySet._for_write`, so that the queryset asks the router for the database it would write to ([Clones: how a queryset is built](chaining.md)). The one thing it checks is that `nowait=True` and `skip_locked=True` were not both given, which raises `ValueError` (`django/db/models/query.py:QuerySet.select_for_update`).

Whether the lock is written, and how, is the backend's. The compiler writes the clause where the backend's feature `BaseDatabaseFeatures.has_select_for_update` is true. There it also raises `TransactionManagementError` when the connection is in autocommit and the backend has transactions, since outside a transaction the rows would not be locked, and `NotSupportedError` for an option the backend lacks (`django/db/models/sql/compiler.py:SQLCompiler.as_sql`). The text of the clause is asked of the backend's operations: `BaseDatabaseOperations.for_update_sql` puts it together from the four options (`django/db/backends/base/operations.py:BaseDatabaseOperations.for_update_sql`). Where the feature is false, which is its value in the base class and on SQLite, none of that happens (`django/db/backends/base/features.py:BaseDatabaseFeatures`).

```text recording=querysets
[ship.name for ship in Ship.objects.select_for_update()]  ->  ['Gannet', 'Petrel']
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
```

The statement, sent on SQLite, has no `"FOR UPDATE"`.

## `none` and `EmptyQuerySet`

`QuerySet.none` returns a queryset that yields nothing, and that sends no statement when it is evaluated. It does it with a condition and not with a flag: `Query.set_empty` adds a `NothingNode` to the query's where clause, joined to whatever is there with `"AND"` (`django/db/models/query.py:QuerySet.none`, `django/db/models/sql/query.py:Query.set_empty`). A `NothingNode` is a condition that nothing satisfies. Asked for its SQL it raises `EmptyResultSet`, and when the queryset is evaluated the compiler's `SQLCompiler.execute_sql` catches that from the statement it is composing and returns no rows, without asking for a cursor (`django/db/models/sql/where.py:NothingNode`, `django/db/models/sql/compiler.py:SQLCompiler.execute_sql`). On a query made by `QuerySet.union`, `set_empty` marks each of the combined queries too.

Being a condition, the mark travels. It is in the where clause, which every clone copies, so a queryset made from an empty one by `QuerySet.filter`, `QuerySet.exclude`, `QuerySet.order_by`, `QuerySet.distinct`, `QuerySet.annotate` or `QuerySet.values` is empty too.

```text recording=querysets
isinstance(Sailor.objects.none(), EmptyQuerySet), isinstance(Sailor.objects.all(), EmptyQuerySet), type(Sailor.objects.none()).__name__  ->  (True, False, 'SailorQuerySet')
list(Sailor.objects.none()), Sailor.objects.none().count(), Sailor.objects.none().exists()  ->  ([], 0, False)
list(Sailor.objects.filter(pk__in=[]))  ->  []
isinstance(Sailor.objects.filter(pk__in=[]), EmptyQuerySet)  ->  False
...
Sailor.objects.none().ordered, Sailor.objects.none().filter(name='Ada').query.is_empty()  ->  (True, True)
EmptyQuerySet()  ->  raises TypeError: EmptyQuerySet can't be instantiated
```

`EmptyQuerySet` is how code asks whether a queryset is empty in this sense, and it is not a kind of queryset. In the recording `none` returned a SailorQuerySet, the class of the queryset it was called on. `EmptyQuerySet` has no instances, `EmptyQuerySet.__init__` raises `TypeError`, and `QuerySet` is not among its bases. It exists to stand on the right of `isinstance`. Its metaclass, `InstanceCheckMeta`, defines `InstanceCheckMeta.__instancecheck__`, the method Python calls for `isinstance`, to answer whether the object is a `QuerySet` whose query's `Query.is_empty` is true; and `is_empty` looks for a `NothingNode` among the children of the where clause (`django/db/models/query.py:InstanceCheckMeta`, `django/db/models/sql/query.py:Query.is_empty`).

So the test is on the query, and that cuts both ways. A queryset made empty by another road passes it: `Query.set_limits` calls `set_empty` when the two bounds of a slice meet, so such a slice is an `EmptyQuerySet` as well. Here everyone is a queryset of all the sailors:

```text recording=querysets
everyone = Sailor.objects.order_by('id')
...
isinstance(everyone[2:2], EmptyQuerySet), list(everyone[2:2])  ->  (True, [])
```

And a queryset that merely matches nothing does not pass. In the first of the two recordings above, the filter on an empty list of keys returned no rows, and sent no statement either: the lookup behind it raises `EmptyResultSet` for an empty list as the statement is composed (`django/db/models/lookups.py:In.process_rhs`). But the where clause of that queryset holds an ordinary condition and no `NothingNode`, and `isinstance` says `False`.

Under `django/` the test is made in `django/db/models/query.py` and nowhere else: by the operators and by `union`, `QuerySet.intersection` and `QuerySet.difference`, each of which treats an empty operand as a case of its own ([Combining querysets: the operators and `union`](combining.md)), and by `QuerySet.ordered`.

## Every method that returns a queryset

Three tests recur in the methods of `QuerySet` that return a queryset, which the table below sets out. `QuerySet._not_support_combined_queries` raises `NotSupportedError` for a combined queryset, whose query has `Query.combinator` set (`django/db/models/query.py:QuerySet._not_support_combined_queries`). A test of `Query.is_sliced` refuses a queryset that has been sliced, with `TypeError`, in some methods only under a condition that the table gives (`django/db/models/sql/query.py:Query.is_sliced`). And `QuerySet.select_related`, `QuerySet.defer` and `QuerySet.only` test `QuerySet._fields` and refuse a queryset after `QuerySet.values` or `QuerySet.values_list`, with `TypeError`. Why a combined queryset is refused is told in [Combining querysets: the operators and `union`](combining.md), and why a sliced one in [Evaluation and the result cache](evaluation.md). The table's last three columns are for a combined queryset, a sliced one and one after `values`, and an empty cell there means that the method does not refuse such a queryset as it is called.

| method | what it leaves | combined | sliced | after `values` |
|---|---|---|---|---|
| `QuerySet.values`, `QuerySet.values_list` | `QuerySet._fields` and `QuerySet._iterable_class`, and the query's select list, through `Query.set_values` ([`values` and `values_list`: rows as dictionaries and tuples](values.md)) | refused, by `QuerySet.annotate`, where the call is given an expression, or `values_list` a field's name twice | | |
| `QuerySet.dates`, `QuerySet.datetimes` | what `annotate`, `values_list`, `QuerySet.distinct`, `QuerySet.filter` and `QuerySet.order_by` leave, called in that order | refused, by `annotate` | refused, by `distinct` | |
| `QuerySet.none` | a `NothingNode` in the where clause | | | |
| `QuerySet.all` | nothing | | | |
| `QuerySet.filter`, `QuerySet.exclude` | a condition in the where clause, through `Query.add_q`; or, on a queryset told to defer its next filter, `QuerySet._deferred_filter` on the queryset ([`filter`, `exclude` and `Q` objects](filters.md), [Clones: how a queryset is built](chaining.md)) | refused | refused, when a condition is given | |
| `QuerySet.complex_filter`, which is there for a relation's `ForeignObjectRel.limit_choices_to` ([`filter`, `exclude` and `Q` objects](filters.md)) | from a `Q`, a condition in the where clause; from a dictionary, what `filter` leaves | | refused, for a dictionary that is not empty | |
| `QuerySet.union`, `QuerySet.intersection`, `QuerySet.difference` | `Query.combinator`, `Query.combinator_all` and `Query.combined_queries`; the clone's own ordering and limits cleared, and `Query.default_ordering` set to `True`; with nothing to combine with, or with an empty operand, one of the querysets it was given may be returned unchanged ([Combining querysets: the operators and `union`](combining.md)) | | | |
| `QuerySet.select_for_update` | `Query.select_for_update` and its four companions; `QuerySet._for_write` on the queryset | | | |
| `QuerySet.select_related` | `Query.select_related` ([From rows to instances: `ModelIterable` and `select_related`](iterables.md)) | refused | | refused |
| `QuerySet.prefetch_related` | `QuerySet._prefetch_related_lookups`, on the queryset and not on the query ([`prefetch_related`: related objects in a second query](prefetch.md)) | refused | | |
| `QuerySet.annotate`, `QuerySet.alias` | `Query.annotations` and the mask of those selected, or for a `FilteredRelation` an entry among the query's filtered relations; `Query.group_by`, for an aggregate | refused | | |
| `QuerySet.order_by` | `Query.order_by`, with `Query.extra_order_by` emptied; `Query.default_ordering`, when called with nothing | | refused | |
| `QuerySet.distinct` | `Query.distinct` and `Query.distinct_fields` | refused | refused | |
| `QuerySet.extra` | `Query.extra`, an `ExtraWhere` in the where clause, `Query.extra_tables`, `Query.extra_order_by` | refused | refused | |
| `QuerySet.reverse` | `Query.standard_ordering` | | refused | |
| `QuerySet.defer`, `QuerySet.only` | `Query.deferred_loading` ([Deferred fields and fetch modes in a queryset](deferred.md)) | refused | | refused |
| `QuerySet.using` | `QuerySet._db`, on the queryset ([Clones: how a queryset is built](chaining.md)) | | | |
| `QuerySet.fetch_mode` | `QuerySet._fetch_mode`, on the queryset ([Deferred fields and fetch modes in a queryset](deferred.md)) | | | |

*The public methods of `QuerySet` that return a `QuerySet`, in the order the class defines them: what each leaves on the queryset it returns, and which querysets it refuses as it is called.*

A call that passes these tests may still leave a query that a compiler or a backend refuses when the statement is composed, as SQLite refuses a sliced queryset as one part of a `union` ([Combining querysets: the operators and `union`](combining.md)).

Three ways of getting a queryset are not in the table: `QuerySet.raw`, which returns a `RawQuerySet` and not a `QuerySet` ([Raw querysets](raw.md)), a slice ([Evaluation and the result cache](evaluation.md)), and the operators `&`, `|` and `^` ([Combining querysets: the operators and `union`](combining.md)).
