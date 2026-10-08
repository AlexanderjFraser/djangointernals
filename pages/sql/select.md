---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The SELECT clause: `get_select`, the select mask and `klass_info`

`SQLCompiler.get_select` decides which columns a statement selects and under what alias, from the query's `Query.select` and `Query.selected`, its annotations and extras, and the select mask that `defer` and `only` leave; with the list it builds `klass_info`, the map by which a row is cut into an instance of the model and of each related model that `select_related` asked for.

The select list has five things to do. Where nothing narrows it, it selects every concrete field of the model, and a child model's parent fields through the join to the parent's table. Where `values` named columns, it selects those and no others, in the order they were named. It selects every annotation that is still selected, under its alias, and every extra select at the front. Where `select_related` asked for related models, it selects their columns after the model's own, each model's together. And it leaves a map behind, since the rows come back as flat tuples and the iterable has to know which positions are the model's, which are a related model's and which an annotation's: that map is **`klass_info`**, a dictionary that names a model, the positions of its columns and, under it, the same for each related model.

Two things on the query decide which way the list is made. `Query.default_cols`, true on a new query, means the model's own columns, narrowed by the mask; `Query.select`, a tuple of resolved columns, is the other way, and `Query.selected` is the order and the names that `values` gave. The recordings below ran on SQLite. A line `select[n]` writes down what the compiler holds after its `as_sql`, in order: the SQL of the column, `as` and its alias where it has one, and the expression in parentheses; `annotation_col_map` and `klass_info` are written the same way, a nested `klass_info` set in under its parent; where a line is a question, its answer follows `->`, and a line beginning `SQL` is a statement as Django handed it to its cursor.

## What `get_select` returns

`SQLCompiler.get_select` returns three things: a list with, for each column, the expression, its SQL with its parameters, and its alias or `None`; the `klass_info`; and a dictionary from each alias to the position of its column, which the compiler keeps as `SQLCompiler.annotation_col_map` (`django/db/models/sql/compiler.py:SQLCompiler.get_select`). It begins with an assertion that the query does not have both `select` and `default_cols`, asks the query for the select mask, and takes the columns: `get_default_columns` with the mask where `default_cols` holds, and `Query.select` otherwise. Then it makes a list of pairs of alias and expression, one of two ways. Where `Query.selected` is `None`, the list is each extra select as a `RawSQL` under its alias, then each column with no alias, then each selected annotation under its alias, and the positions of the columns are the model's own. Where `selected` is a dictionary, each entry is taken in its order: a string is the alias of an annotation, which is looked up in `Query.annotations`; an integer is the position of a column in the columns just taken, and that entry's position is one of the model's; and a `ColPairs`, the columns of a composite key, is given no alias, since the comment says it cannot be aliased. Where any position is the model's, `klass_info` is made, with the model under `"model"` and the positions under `"select_fields"`. Where the query has `Query.select_related`, `get_related_selections` appends the related models' columns and returns their `klass_info` entries, which go under `"related_klass_infos"`.

Last, each expression is compiled. One that raises `EmptyResultSet` is written as its `empty_result_set_value` where it has one and as the constant `0` otherwise; one that raises `FullResultSet` is written as `Value(True)`; and any other has its SQL passed through its `select_format`, which is where an expression that cannot stand bare in a select list on some backend is wrapped ([Expressions: `resolve_expression` and `as_sql`](expressions.md)). Where `with_col_aliases=True` was asked, each column without an alias is given `"col1"`, `"col2"` and so on, which a statement standing inside another needs ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)). The plainest case, every column of a ship:

```text recording=sql
get_select for Ship.objects.all(): every concrete field as a Col, no alias, the klass_info of the model, and no annotations
    select[0]: "fleet_ship"."id"  (Col(fleet_ship, fleet.Ship.id))
    select[1]: "fleet_ship"."name"  (Col(fleet_ship, fleet.Ship.name))
    select[2]: "fleet_ship"."tonnage"  (Col(fleet_ship, fleet.Ship.tonnage))
    select[3]: "fleet_ship"."home_id"  (Col(fleet_ship, fleet.Ship.home))
    select[4]: "fleet_ship"."captain_id"  (Col(fleet_ship, fleet.Ship.captain))
    annotation_col_map: {}
    klass_info: model Ship, select_fields [0, 1, 2, 3, 4]
```

`as_sql` writes each column as its SQL and, where there is an alias, `"AS"` and the alias quoted; here none has one, and the model's positions are the five.

## The model's own columns: `get_default_columns`

`SQLCompiler.get_default_columns` returns a `Col` for each concrete field of a model, under the alias of the table it is read from (`django/db/models/sql/compiler.py:SQLCompiler.get_default_columns`). It takes the mask, and optionally an alias to start from and the options of a model other than the query's, which is how `get_related_selections` reuses it for a related model. Without those it starts from `Query.get_meta`, which is `None` for a query with no model, and then there are no columns at all, and from `Query.get_initial_alias`. It keeps a dictionary of the models it has joined, seeded with `None` for the starting alias, and unnests the mask into a set of fields, so that a composite primary key in the mask counts as each of its columns (`django/db/models/fields/composite.py:unnest`).

For each field of the options' `concrete_fields`, it takes the concrete model the field belongs to, and takes it as `None` where that is the model itself; the comment says a proxy has a model and a concrete model that differ, and a proxy's fields, which belong to the model it stands for, keep the start alias because `join_parent_model` finds no link field to join through. A field whose model is a parent of the model the walk came from is skipped where the walk was given one: that is the case of `select_related` reaching a child through its parent, where, the comment says, the parent's data is in the select list already and would be loaded twice. A field not in the mask is skipped where there is a mask. What is left is given an alias by `Query.join_parent_model`, the start alias for the model's own fields and the alias of a join to the parent's table for an inherited one, which it makes through `setup_joins` the first time it meets each parent ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)); and the field's `get_col` makes the column, which is the field's own cached `Col` where the alias is the table's name and a new one otherwise (`django/db/models/fields/__init__.py:Field.get_col`). An officer is a sailor with a table of its own, and its columns come from two tables:

```text recording=sql
select[0]: "crew_sailor"."id"  (Col(crew_sailor, crew.Sailor.id))
select[1]: "crew_sailor"."name"  (Col(crew_sailor, crew.Sailor.name))
select[2]: "crew_sailor"."ship_id"  (Col(crew_sailor, crew.Sailor.ship))
select[3]: "crew_sailor"."signed_on"  (Col(crew_sailor, crew.Sailor.signed_on))
select[4]: "crew_officer"."sailor_ptr_id"  (Col(crew_officer, crew.Officer.sailor_ptr))
select[5]: "crew_officer"."rank"  (Col(crew_officer, crew.Officer.rank))
annotation_col_map: {}
klass_info: model Officer, select_fields [0, 1, 2, 3, 4, 5]
...
tail(Officer.objects.all())  ->  ('FROM "crew_officer" INNER JOIN "crew_sailor" ON ("crew_officer"."sailor_ptr_id" = "crew_sailor"."id")', ())
said(Officer.objects.all().query.get_compiler('default').get_default_columns({}))  ->  [Col(crew_sailor, crew.Sailor.id), Col(crew_sailor, crew.Sailor.name), Col(crew_sailor, crew.Sailor.ship), Col(crew_sailor, crew.Sailor.signed_on), Col(crew_officer, crew.Officer.sailor_ptr), Col(crew_officer, crew.Officer.rank)]
said(Sailor.objects.all().query.get_compiler('default').get_default_columns({}, start_alias='T9'))  ->  [Col(T9, crew.Sailor.id), Col(T9, crew.Sailor.name), Col(T9, crew.Sailor.ship), Col(T9, crew.Sailor.signed_on)]
```

The parent's four columns come first, since the options list a parent's fields before the child's own ([The options: what a model keeps as `_meta`](../models/options.md)), and the join that reads them is in the statement though no filter made it. The last line is the method asked for a sailor's columns under another alias, which is what it does for a related model.

## `values`: `set_values`, `add_fields` and `Query.selected`

`Query.set_values` is what `QuerySet.values` and `QuerySet.values_list` leave on the query, and it decides the select list in full (`django/db/models/sql/query.py:Query.set_values`) ([`values` and `values_list`: rows as dictionaries and tuples](../querysets/values.md)). It first clears what `values` replaces: `select_related` is turned off, the deferred loading cleared and, through `Query.clear_select_fields`, the select tuple, `Query.values_select` and `selected`. Then, given names, it checks each with `check_alias` and goes through them. Where the query has no extras and no annotations, the comment calls it a shortcut: every name is a field's, and `selected` maps each to its index. Otherwise `default_cols` is turned off and each name is one of three kinds. A name in `Query.extra_select` becomes a `RawSQL` of the extra's SQL and parameters. A name in `Query.annotation_select` becomes the name itself, a string. A name in `annotations` but not selected is refused with `FieldError`: the message says the alias was excluded by a previous `values` call where some annotation is still selected, and that `annotate` should be used to promote it where none is, which is what `QuerySet.alias` leaves. Any other name is a field's, and `selected` maps it to its index among the field names; where an annotation is selected, `names_to_path` is run on the name first so that, the comment says, a name that resolves to nothing gets an error listing the annotations about to be masked among its choices. The extra mask and the annotation mask are then set to the names found, so that `values` narrows the extras and the annotations to those it named. Given no names, every concrete field's attname is a field name and `selected` ends as `None`.

Before the columns are resolved, the grouping is attended to, since, the comment says, the selected annotations must be known before the `"GROUP BY"` is set: where `Query.group_by` is `True`, every concrete field is added to the select and `Query.set_group_by` pins the grouping to those columns with aliases disallowed, before the select is cleared again; where it is a tuple, a `Ref` to an annotation no longer selected is replaced by the annotation itself ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md)). Then `values_select` is set to the field names, `Query.add_fields` resolves them into columns, and `selected` is set.

`Query.add_fields` turns names into the select tuple (`django/db/models/sql/query.py:Query.add_fields`). It takes the initial alias and the model's options, and for each name has `Query.get_names_to_join` split it at each `"__"`, unless the whole name is a filtered relation's alias, then `setup_joins` and `trim_joins` ([From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md)); a many-to-many step is allowed unless the caller said otherwise, which the grouping path does. A name that ends in more than one target column, a composite key, becomes a `ColPairs`; any other becomes the column the join's transform function makes of its one target and the final alias. The columns go to `Query.set_select`, which sets the tuple and turns `default_cols` off. A name refused by `setup_joins` for crossing a multi-valued relation where none was allowed becomes `FieldError` with the name; a `FieldError` on a name with `"__"` in it is raised as it came, from the model where it failed; and one on a plain name becomes the message that cannot resolve the keyword, listing the model's field names, the extras, the selected annotations and the filtered relations as choices.

| the value under a name in `selected` | what it is | where `get_select` finds the column |
|---|---|---|
| an `int` | the position of a column in `Query.select` | that column, and the position goes into `klass_info` |
| a `str` | the alias of an annotation, which is the name itself | `Query.annotations` under the alias |
| a `RawSQL` | the SQL and parameters of an extra select | the `RawSQL` itself |

*The three kinds of value `Query.selected` maps a name to, and what `get_select` does with each.*

```text recording=sql
get_select after values: the named columns from Query.selected, each under its name, and a klass_info whose select_fields are their positions
    select[0]: "fleet_ship"."name"  as name  (Col(fleet_ship, fleet.Ship.name))
    select[1]: "fleet_port"."country"  as home__country  (Col(fleet_port, fleet.Port.country))
    annotation_col_map: {'name': 0, 'home__country': 1}
    klass_info: model Ship, select_fields [0, 1]
    Ship.objects.values('name', 'home__country').query.selected, Ship.objects.values('name', 'home__country').query.values_select, Ship.objects.values('name', 'home__country').query.select, Ship.objects.values('name', 'home__country').query.default_cols  ->  ({'name': 0, 'home__country': 1}, ('name', 'home__country'), (Col(fleet_ship, fleet.Ship.name), Col(fleet_port, fleet.Port.country)), False)
```

The two columns are under their names, which is the alias `as_sql` writes after each, and `klass_info` says both positions are the model's: `values` selects columns of the model, and the iterable that makes dictionaries of the rows takes their names from `selected` ([`values` and `values_list`: rows as dictionaries and tuples](../querysets/values.md)). The last line is the four attributes after the call. Where the names are of the three kinds, the dictionary shows them:

```text recording=sql
select[0]: COUNT("crew_sailor"."id")  as hands  (Count(Col(crew_sailor, crew.Sailor.id)))
select[1]: "fleet_ship"."name"  as name  (Col(fleet_ship, fleet.Ship.name))
annotation_col_map: {'hands': 0, 'name': 1}
klass_info: model Ship, select_fields [1]
Ship.objects.values('name').annotate(hands=Count('crew')).values('hands', 'name').query.selected  ->  {'hands': 'hands', 'name': 0}
Ship.objects.values('name', low=Lower('name')).query.selected, Ship.objects.values('name', low=Lower('name')).query.annotations, Ship.objects.values('name', low=Lower('name')).query.values_select  ->  ({'name': 0, 'low': 'low'}, {'low': Lower(Col(fleet_ship, fleet.Ship.name))}, ('name',))
Ship.objects.values_list('name', Lower('name')).query.selected  ->  {'name': 0, 'lower1': 'lower1'}
...
Ship.objects.extra(select={'heavy': 'tonnage > 1000'}).values('name', 'heavy').query.selected, Ship.objects.extra(select={'heavy': 'tonnage > 1000'}).values('name', 'heavy').query.extra_select_mask  ->  ({'name': 0, 'heavy': RawSQL(tonnage > 1000, [])}, {'heavy'})
Ship.objects.values('cargo')  ->  raises FieldError: Cannot resolve keyword 'cargo' into field. Choices are: captain, captain_id, crew, home, home_id, id, name, tonnage, voyage
Ship.objects.alias(low=Lower('name')).values('low')  ->  raises FieldError: Cannot select the 'low' alias. Use annotate() to promote it.
Ship.objects.annotate(low=Lower('name')).values('name').values('low')  ->  raises FieldError: Cannot select the 'low' alias. Use annotate() to promote it.
```

In the first list the aggregate stands first because it was named first, and only the second position is the model's. A keyword given to `values` is an annotation made on the way, so its name is a string in `selected`; an expression given to `values_list` is named by its class, `"lower1"`, and so is a string too. The extra is a `RawSQL`. The three errors are `add_fields` refusing an unknown name, with the choices, and `set_values` refusing an alias twice: once because `alias` never selected it, and once because the first `values` masked it.

Three more methods change the select tuple. `Query.add_select_col` appends one column under a name, to the tuple, to `values_select` and to `selected`, which is how an ordering column that a compound statement's parts did not select is added to each ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)). `Query.clear_select_clause` empties everything: the tuple, `default_cols`, `select_related`, both masks and `selected`, and is what `Query.exists`, `QuerySet.update`, a query given as the value of a lookup and the delete compiler for its inner query call before selecting one thing of their own ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md), [Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md), [INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md)). `Query.clear_select_fields` empties the tuple, `values_select` and `selected` and, its docstring says, not the extras. `Query.has_select_fields` is whether `selected` is set (`django/db/models/sql/query.py:Query.clear_select_clause`, `django/db/models/sql/query.py:Query.has_select_fields`).

## Annotations and extras: the masks

`Query.annotations` is every annotation, under its alias, and `Query.annotation_select` is those that are selected: a property that returns the whole dictionary where `Query.annotation_select_mask` is `None`, and otherwise the entries whose alias is in the mask, kept in `Query._annotation_select_cache` until the mask changes (`django/db/models/sql/query.py:Query.annotation_select`). `Query.set_annotation_mask` sets the mask to a set of the names, or to `None`, and clears the cache; where `selected` is set, it also prunes from `selected` each reference to an annotation now masked and appends a reference for each name, so that an annotation selected after `values` takes its place at the end (`django/db/models/sql/query.py:Query.set_annotation_mask`). `Query.append_annotation_mask` adds names to a mask that exists and does nothing where there is none, since no mask means that all are selected.

`Query.add_annotation` is what `QuerySet.annotate` and `QuerySet.alias` call for each expression (`django/db/models/sql/query.py:Query.add_annotation`) ([Annotations, ordering and the other methods that change the query](../querysets/methods.md)). It checks the alias, resolves the expression against the query with joins allowed, and then goes by whether the annotation is to be selected: where it is, the alias is appended to the mask; where it is not, the mask is set to the selected annotations without this alias, which is how the first `alias` call brings a mask into being. The annotation is stored, and where it is selected and `selected` is set, a reference is added there as well. Recorded for the ships annotated with a count of their crew and their name in lower case:

```text recording=sql
get_select with annotations: the model's columns, then each selected annotation under its alias, and annotation_col_map says where
    select[0]: "fleet_ship"."id"  (Col(fleet_ship, fleet.Ship.id))
    select[1]: "fleet_ship"."name"  (Col(fleet_ship, fleet.Ship.name))
    select[2]: "fleet_ship"."tonnage"  (Col(fleet_ship, fleet.Ship.tonnage))
    select[3]: "fleet_ship"."home_id"  (Col(fleet_ship, fleet.Ship.home))
    select[4]: "fleet_ship"."captain_id"  (Col(fleet_ship, fleet.Ship.captain))
    select[5]: COUNT("crew_sailor"."id")  as hands  (Count(Col(crew_sailor, crew.Sailor.id)))
    select[6]: LOWER("fleet_ship"."name")  as low  (Lower(Col(fleet_ship, fleet.Ship.name)))
    annotation_col_map: {'hands': 5, 'low': 6}
    klass_info: model Ship, select_fields [0, 1, 2, 3, 4]
    Ship.objects.annotate(hands=Count('crew'), low=Lower('name')).query.annotation_select_mask, Ship.objects.annotate(hands=Count('crew')).alias(low=Lower('name')).query.annotation_select_mask, list(Ship.objects.annotate(hands=Count('crew')).alias(low=Lower('name')).query.annotation_select)  ->  (None, {'hands'}, ['hands'])
```

The annotations follow the five columns, under their aliases, and `annotation_col_map` is where the iterable finds them to set each on the instance by its alias ([From rows to instances: `ModelIterable` and `select_related`](../querysets/iterables.md)). The last line is the mask in three states: `None` after two `annotate` calls, a set of one after `alias`, and `annotation_select` holding that one.

An **extra select** is SQL a program wrote, given to `QuerySet.extra` under a name. The select half of `Query.add_extra` checks each name with `check_alias`, makes the SQL a string, and pairs it with its parameters by counting the `%s` placeholders in it, a `%%s` not counting, so that each entry keeps the parameters that are its own; the pairs go into `Query.extra` (`django/db/models/sql/query.py:Query.add_extra`). `Query.extra_select` is the entries, or those in `Query.extra_select_mask`, cached as `annotation_select` is; `Query.set_extra_mask` sets the mask without removing anything from `extra`, since, its docstring says, the entries might be used later. In the select list an extra is a `RawSQL`, whose `as_sql` writes the SQL in parentheses with its parameters, and the extras come first: the comment in the iterable that reads them says the extra columns are always at the start of the row ([Expressions: `resolve_expression` and `as_sql`](expressions.md)).

`Query.check_alias` guards every alias that reaches the statement, from `add_annotation`, `set_values` and `add_extra`. It refuses with `ValueError` an alias that matches `FORBIDDEN_ALIAS_PATTERN`: quotation marks, among which the comment counts square brackets, whitespace, control characters, a semicolon, a hash and the comment markers `"--"`, `"/*"` and `"*/"` (`django/db/models/sql/query.py:Query.check_alias`, `django/db/models/sql/query.py:FORBIDDEN_ALIAS_PATTERN`). An alias reaches the statement after `"AS"`, through the backend's `quote_name` and nothing else.

```text recording=sql
check_alias: what an alias may not contain, and the percent sign that is deprecated
    Ship.objects.annotate(**{'bad name': F('tonnage')})  ->  raises ValueError: Column aliases cannot contain whitespace characters, hashes, control characters, quotation marks, semicolons, or SQL comments.
    Ship.objects.annotate(**{'pct%': F('tonnage')}).query.annotations  ->  {'pct%': Col(fleet_ship, fleet.Ship.tonnage)}
      warns RemovedInDjango2028Warning: Using percent signs in a column alias is deprecated.
    Ship.objects.values(**{'a-b': F('tonnage')}).query.selected, Ship.objects.extra(select={'x y': '1'})  ->  raises ValueError: Column aliases cannot contain whitespace characters, hashes, control characters, quotation marks, semicolons, or SQL comments.
```

> **Deprecated.** A percent sign in an alias warns with `RemovedInDjango2028Warning` and is otherwise accepted, as the second line shows. The release notes of 6.0 say that using a percent sign in a column alias or annotation is deprecated (`docs/releases/6.0.txt`), and the comment in `check_alias` says that when the deprecation ends the pattern will refuse it and the message will name percent signs.

## The select mask: `defer` and `only`

`Query.deferred_loading` is a pair: a frozenset of field names and a flag. With the flag `True` the names are the fields to leave out, and with it `False` they are the only fields to load; a new query has an empty set and `True`, which is nothing deferred (`django/db/models/sql/query.py:Query.deferred_loading`). A field of a related model is kept as a name with `"__"` in it, `"ship__name"`, and the comment says the splitting waits until the columns are computed. `Query.add_deferred_loading` is what `QuerySet.defer` calls: in the deferring mode it adds the names; in the only mode it removes them from the set to load, and where nothing is left of that set it goes back to deferring, with the names that were not in it, so that `only("name")` followed by `defer("name", "ship")` ends deferring the ship alone (`django/db/models/sql/query.py:Query.add_deferred_loading`). `Query.add_immediate_loading` is what `QuerySet.only` calls: it replaces `"pk"` with the primary key's name, and in the deferring mode keeps the names less those already deferred, which the docstring puts as immediate loading overriding earlier immediate loading but respecting earlier deferrals; in the only mode the names replace the set (`django/db/models/sql/query.py:Query.add_immediate_loading`). `Query.clear_deferred_loading` puts the pair back to its default, which `defer(None)` asks for ([Deferred fields and fetch modes in a queryset](../querysets/deferred.md)).

`Query.get_select_mask` turns the pair into the **select mask**: a dictionary from each field that will be loaded to a mask of the same shape for the model it leads to, with `{}` for a field that leads nowhere or to a model loaded whole (`django/db/models/sql/query.py:Query.get_select_mask`). With no names the mask is `{}`, and `get_default_columns` takes an empty mask for no restriction. Otherwise the names are nested at each `"__"` into a tree of dictionaries, and one of two methods walks it with the model's options. `Query._get_defer_select_mask` begins with the primary key, which is always loaded, and then takes every concrete field and every related object of the model: one named neither by its name nor by its attname is loaded; one named with nothing under it is left out; and one named with more under it must be a relation, else `FieldError` with the word under it, and is descended into by the related model's concrete model, except that a many-to-many field is skipped, since, the comment says, a virtual field cannot be effectively deferred and was historically allowed to be passed. A name left over after that must be a filtered relation's alias, which is descended into under the key of the alias and its relation; any other is put to the options' `get_field`, which raises `FieldDoesNotExist` (`django/db/models/sql/query.py:Query._get_defer_select_mask`). `Query._get_only_select_mask` begins with the primary key as well and then takes only the names: each is a field of the options, with the same error for a wrong one, and one with more under it must be a relation and is descended into the same way (`django/db/models/sql/query.py:Query._get_only_select_mask`). The only mask has no branch for a filtered relation; `QuerySet.only` refuses one before the query is reached.

```text recording=sql
get_select_mask: deferred_loading turned into the fields that will be loaded, model by model, with the primary key always among them
    select[0]: "fleet_ship"."id"  (Col(fleet_ship, fleet.Ship.id))
    select[1]: "fleet_ship"."name"  (Col(fleet_ship, fleet.Ship.name))
    annotation_col_map: {}
    klass_info: model Ship, select_fields [0, 1]
    select[0]: "crew_sailor"."id"  (Col(crew_sailor, crew.Sailor.id))
    select[1]: "crew_sailor"."signed_on"  (Col(crew_sailor, crew.Sailor.signed_on))
    annotation_col_map: {}
    klass_info: model Sailor, select_fields [0, 1]
    Sailor.objects.only('name').query.deferred_loading, mask_said(Sailor.objects.only('name').query.get_select_mask())  ->  (({'name'}, False), {Sailor.id: {}, Sailor.name: {}})
    mask_said(Sailor.objects.defer('name').query.get_select_mask())  ->  {Sailor.id: {}, Sailor.ship: {}, Sailor.signed_on: {}, the rel of Licence.sailor: {}, the rel of Officer.sailor_ptr: {}, the rel of Ship.captain: {}}
    mask_said(Sailor.objects.only('ship__name').query.get_select_mask())  ->  {Sailor.id: {}, Sailor.ship: {Ship.id: {}, Ship.name: {}}}
    mask_said(Sailor.objects.select_related('ship').only('name', 'ship__name').query.get_select_mask())  ->  {Sailor.id: {}, Sailor.name: {}, Sailor.ship: {Ship.id: {}, Ship.name: {}}}
    mask_said(Sailor.objects.select_related('ship').defer('ship__tonnage').query.get_select_mask())  ->  {Sailor.id: {}, Sailor.name: {}, Sailor.ship: {Ship.captain: {}, Ship.home: {}, Ship.id: {}, Ship.name: {}, the rel of Sailor.ship: {}, the rel of Voyage.ship: {}}, Sailor.signed_on: {}, the rel of Licence.sailor: {}, the rel of Officer.sailor_ptr: {}, the rel of Ship.captain: {}}
    mask_said(Sailor.objects.defer('pilots_into').query.get_select_mask()), tail(Sailor.objects.defer('pilots_into'))  ->  ({Sailor.id: {}, Sailor.name: {}, Sailor.ship: {}, Sailor.signed_on: {}, the rel of Licence.sailor: {}, the rel of Officer.sailor_ptr: {}, the rel of Ship.captain: {}}, ('FROM "crew_sailor"', ()))
    Sailor.objects.only('name__x').query.get_select_mask()  ->  raises FieldError: x
    Sailor.objects.defer('cargo').query.get_select_mask()  ->  raises FieldDoesNotExist: Sailor has no field named 'cargo'
    mask_said(Officer.objects.only('rank').query.get_select_mask())  ->  {Officer.rank: {}, Officer.sailor_ptr: {}}
```

The two lists are the ships with their name only and the sailors without name or ship: in each the primary key is there unasked. The mask lines show the shape: `only("name")` is the key and the name; `defer("name")` is every other field, the reverse relations among them, each with an empty mask; `only("ship__name")` descends into the ship, where again the key is added. Deferring a many-to-many field changes nothing, and the statement reads the one table as before. The wrong names are the two errors, and an officer's key is its link to the sailor.

Three things read the mask. `get_default_columns` skips a field that is not in it, as above. `get_related_selections` takes from it the mask for each relation it descends, and `select_related_descend` refuses a relation that is both deferred and traversed. And the queryset's iterable, finding fewer columns than the model has fields, makes a deferred instance of what was selected ([Deferred fields and fetch modes in a queryset](../querysets/deferred.md)).

## `select_related`: `get_related_selections` and the tree of `klass_info`

`Query.select_related` is `False`, `True`, or a dictionary of names nested at each `"__"`, which `Query.add_select_related` builds from the names given to `QuerySet.select_related` (`django/db/models/sql/query.py:Query.add_select_related`). `True` means every forward relation that cannot be null, followed to a depth of `Query.max_depth`, which is five; the comment at the attribute calls it an arbitrary limit against infinite recursion.

> **Deprecated.** Asking for `True`, by calling `select_related` with no arguments, warns with `RemovedInDjango2028Warning` (`django/db/models/query.py:QuerySet.select_related`). The release notes of 6.1 say that calling it with no arguments to select all non-nullable related fields is deprecated, and that the related fields should be named, or the `FETCH_PEERS` fetch mode used (`docs/releases/6.1.txt`) ([Deferred fields and fetch modes in a queryset](../querysets/deferred.md)).

`SQLCompiler.get_related_selections` fills in the rest of the select list and returns the `klass_info` of each related model (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`). It is called by `get_select` with the list so far and the mask, and calls itself for each model it descends into, carrying the options and the alias of that model, the depth, the part of the dictionary that is under that name, and whether the names were restricted at all. At the top it works out the last two: restricted is whether `select_related` is a dictionary, and the dictionary is what was requested. Where the names are not restricted, a depth past `max_depth` returns nothing.

The forward relations come first. For each field of the model, in a restricted walk, a field that is not a relation but was named is refused with `FieldError`, the one that says a non-relational field was given. Then `select_related_descend` decides whether to follow the field (`django/db/models/query_utils.py:select_related_descend`): not where it is no relation; not where it is the link to a parent model, which the comment says is always joined and need not be followed; in an unrestricted walk, only where the field cannot be null; in a restricted one, only where the field was named, and then with `FieldError` where the mask has entries but not this field, the error that says a field cannot be both deferred and traversed. For a field that is followed, a `klass_info` is made with the related model, the field, `"reverse"` as `False`, and two setters: `"local_setter"` is the field's `FieldCacheMixin.set_cached_value`, which puts the related instance in the instance's cache, and `"remote_setter"` is the rel's, which puts the instance in the related instance's cache, where the field is unique, and a function that does nothing otherwise (`django/db/models/fields/mixins.py:FieldCacheMixin.set_cached_value`). `Query.setup_joins` joins the related table, `get_default_columns` makes its columns under that alias with the relation's part of the mask, each column is appended to the list with its position recorded in `"select_fields"`, and the method descends with the depth raised by one.

The reverse relations are taken only in a restricted walk, and only those that are one-to-one: the model's related objects whose field is unique and not many-to-many. Each is put to `select_related_descend` as well, and one that is followed is joined by its related query name. Its `klass_info` has `"reverse"` as `True`, the setters the other way round, and `"from_parent"` as whether the related model is a subclass of this one: a child reached from its parent, as an officer from a sailor. For that case `get_default_columns` is told the model the walk came from, and skips the parent's fields, which are in the list already.

A filtered relation is followed at the top level only; the comment says they work only on the topmost level, and the loop stops at any depth past one. For each requested name that is a filtered relation's alias, `setup_joins` resolves the alias, the model is the one the joins end at, and the `klass_info` is made as for a reverse relation: `"local_setter"` is a function the method defines that sets the reverse cache when there is a related instance, where the alias is reached in two joins or fewer, and a function that does nothing otherwise, and `"remote_setter"` is a function that sets the instance on the related one as an attribute under the alias (`django/db/models/sql/compiler.py:SQLCompiler.get_related_selections`). Last, a restricted walk refuses with `FieldError` any requested name it did not meet, listing the choices: the model's relation fields, the reverse one-to-one relations by their query names, and the filtered relations.

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

*The select list of a sailor with its ship, the ship's home port and the officer the sailor may be, and the tree of `klass_info` over it: each node names its model, the field that reached it and the positions of its columns. The officer's positions begin with the sailor's own, since a child reached from its parent is built from the parent's columns and its own.*

The iterable reads the tree. `ModelIterable.__iter__` takes the model's positions from the root and makes a `RelatedPopulator` of each related `klass_info`, which takes its slice of the row by its positions, reorders them into the order the model's constructor expects where they came through a parent, tests the primary key's column for `None` so that an outer join with no row on the far side gives no instance, and calls the two setters ([From rows to instances: `ModelIterable` and `select_related`](../querysets/iterables.md)). The errors, and the two walks, unrestricted and by name:

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

## A condition as a column

A `Q` given to `annotate` resolves to a `WhereNode`, and an `Exists` is an expression already; either is selected as a column. `WhereNode.output_field` is a boolean field, and its `select_format`, like that of `Exists`, wraps the SQL as `CASE WHEN ... THEN 1 ELSE 0 END` where the features object lacks `supports_boolean_expr_in_select_clause`, which the comment says is Oracle's case; on SQLite the condition stands as it is (`django/db/models/sql/where.py:WhereNode.select_format`, `django/db/models/expressions.py:Exists.select_format`). A condition that can match nothing raises `EmptyResultSet` when compiled, and `get_select` catches it: a `WhereNode` has no `empty_result_set_value`, so it is written as the constant `0`, and an `Exists` has `False` for one, so it is written as a parameter; a condition that every row meets raises `FullResultSet` and is written as `True` ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md), [Subqueries: `Subquery`, `Exists`, `OuterRef` and a query inside another](subqueries.md)). Here c is a compiler for the ships annotated with whether each is over a thousand tons, whether a sailor named Ada is aboard, a comparison with an empty list, an `Exists` of no sailors, and the negation of the comparison with the empty list:

```text recording=sql
c.as_sql()  ->  ('SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "fleet_ship"."tonnage" > %s AS "big", EXISTS(SELECT %s AS "a" FROM "crew_sailor" "U0" WHERE ("U0"."name" = %s AND "U0"."ship_id" = ("fleet_ship"."id")) LIMIT 1) AS "has_ada", 0 AS "nothing", %s AS "nobody", %s AS "all" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC', (1000, 1, 'Ada', False, True))
...
connection.features.supports_boolean_expr_in_select_clause  ->  True
```

The five annotations are the last five columns: the comparison, the `"EXISTS"`, the constant `0`, the parameter `False`, and the parameter `True`.

## `get_select_for_update_of_arguments`

`SQLCompiler.get_select_for_update_of_arguments` is the one other reader of `klass_info` in the compiler: for each name in `Query.select_for_update_of`, `"self"` or a path of relation names, it walks the tree, the parents of each model included, to the model the name reaches, takes the first selected column of that model, and returns the column compiled where the features object has `select_for_update_of_column` and the table's alias quoted otherwise; a name that reaches no model is refused with `FieldError` listing every path the tree offers (`django/db/models/sql/compiler.py:SQLCompiler.get_select_for_update_of_arguments`). What `as_sql` does with the list is told with the lock ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md)).
