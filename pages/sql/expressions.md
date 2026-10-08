---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Expressions: `resolve_expression` and `as_sql`

An **expression** is any object with a `resolve_expression` method, which binds it to a query, and whose resolved form has an `as_sql` method, which writes its SQL: `F`, `Value`, `Col`, the `CombinedExpression` that `+` makes, `Case`, and everything else a `Query` holds. This page is the protocol `BaseExpression` gives them all, what the operators of `Combinable` make, how an expression learns its type and its equality, and the small classes of `django/db/models/expressions.py`.

An expression has five things to do. It must be built without a query, since `F("crates") * F("kilos_each")` is written in a model's `GeneratedField`, a `Q` in a constraint, and both in a migration file long before any queryset exists. It must then be bound to one query, so that the name `"home__name"` becomes a column of a table that query has joined. It must write SQL for one backend, with the backend's spelling of a power or a cast. It must say what type its value is, so that the compiler can convert what the driver returns and a lookup can prepare a value against it. And two of them made the same way must be equal, so that the compiler can see that an ordering names a selected column. The first two are one method, `BaseExpression.resolve_expression`, which copies; the third is `BaseExpression.as_sql`, which the compiler calls through a vendor's method where there is one; the fourth is `BaseExpression.output_field`; the fifth is `Expression.identity` (`django/db/models/expressions.py:BaseExpression`, `django/db/models/expressions.py:Expression`).

The examples are the shipping line of the chapter's opening page, [From QuerySet to SQL](../sql.md): a Ship has a name, a tonnage, a home port and perhaps a captain, a Voyage a date it sailed. In the lines quoted from the recording, q is the query of a queryset of every Ship, annotated is that of the same queryset with the annotation `hands=Count('crew')`, plus is `F('tonnage') + 1`, low is `Lower('name')`, resolved is low resolved against q, and compiler is a compiler made for q. Each line is a question put to a running Django, on SQLite, with the repr of its answer after `->` or the exception it raised, or a line of Python run to make something a later line reads.

## Built without a query, bound to one

Nothing in `Lower('name')` knows a model. Its one source is an `F`, a name and nothing more, and `F` is not even a `BaseExpression`: it has no `as_sql` and no output field, only a `resolve_expression` that asks the query what the name means (`django/db/models/expressions.py:F`). So an expression is a tree whose leaves are names and values, and binding it to a query is replacing each name by what the query finds under it.

`BaseExpression.resolve_expression` does that without touching the original. It makes a copy with `BaseExpression.copy`, sets `is_summary` on the copy to its summarize argument, resolves each of the copy's sources with the same arguments, and stores the resolved sources on the copy with `BaseExpression.set_source_expressions` (`django/db/models/expressions.py:BaseExpression.resolve_expression`). Everything the base class does to a tree it does through `BaseExpression.get_source_expressions` and `set_source_expressions`, and a subclass that keeps its parts under names of its own, as `CombinedExpression` keeps `lhs` and `rhs` and `Case` its cases and default, implements the pair so that the base class can walk it. A source may be `None`, as a `Window` without a partition has, and is skipped. Where a source resolves to a `ColPairs`, the columns of a composite primary key, the copy is refused with `ValueError` unless its class sets `allows_composite_expressions`.

```text recording=sql
low = Lower('name')
resolved = low.resolve_expression(q)
resolved is low, low.source_expressions, resolved.source_expressions, resolved.is_summary  ->  (False, [F(name)], [Col(fleet_ship, fleet.Ship.name)], False)
low.get_source_expressions(), resolved.output_field, type(resolved.output_field).__name__  ->  ([F(name)], <django.db.models.fields.CharField: name>, 'CharField')
Coalesce('tonnage', 0).resolve_expression(q).get_source_expressions()  ->  [Col(fleet_ship, fleet.Ship.tonnage), Value(0)]
```

The copy is another object, its source is now a `Col` where the original still holds `F(name)`, and its output field is the very field object of Ship, since a `Col` answers for the column's field. `Coalesce('tonnage', 0)` shows the two kinds of leaf: a string became an `F` and the integer a `Value` when the function was made, by `BaseExpression._parse_expressions`, which leaves anything that already has `resolve_expression` alone (`django/db/models/expressions.py:BaseExpression._parse_expressions`).

The arguments beyond the query are passed down the tree unchanged. `allow_joins=False` makes a name that needs a join an error, which is how an update refuses `F("ship__tonnage")`. The reuse argument is a set of aliases a many-to-many step may reuse, which `Query.resolve_ref` adds the joins it made to. `summarize=True` says the expression is a terminal aggregate, the argument of `aggregate()`, and a name then resolves to a `Ref` to the annotation instead of the annotation itself ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)). `for_save=True` says the value is for an insert or an update, and `Value`, `DatabaseDefault` and `When` read it.

```text figure=the-resolve-step
unresolved, built with no query          resolve_expression(q)        the resolved copy          q.alias_map
                                                                                                   
Lower                                     ------------------------>   Lower                        fleet_ship
  F(name)                                                               Col(fleet_ship, fleet.Ship.name)

F(home__name)                             ------------------------>   Col(fleet_port, fleet.Port.name)   fleet_ship
                                                                                                         fleet_port, joined on the way

low is left as it was: low.source_expressions is still [F(name)]
```

*An expression before and after `resolve_expression` against the query of a queryset of every Ship. The copy holds a `Col` where the original holds an `F`; a name across a relation joined the port's table into the query's alias map as it was resolved, and the original is unchanged.*

### `F` and `resolve_ref`

`F.resolve_expression` is one line: it returns `Query.resolve_ref` for its name (`django/db/models/expressions.py:F.resolve_expression`). `resolve_ref` looks for the whole name among the query's annotations first and returns the annotation itself, or, with `summarize=True`, a `Ref` to it, refusing an alias that is not selected. Otherwise it splits the name at each `"__"`: if the first word is an annotation, the rest are transforms applied to it; if not, `Query.setup_joins` walks the words as fields, joining tables, `Query.trim_joins` takes back a join whose only use is a key the previous table holds, and the function `setup_joins` built turns the final field into a `Col` through `Field.get_col` and applies any transforms that ended the name (`django/db/models/sql/query.py:Query.resolve_ref`). Any join left after `trim_joins` with `allow_joins=False`, or a final field of several columns, is `FieldError`. [From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md) has the walk.

```text recording=sql
F resolved against a query: resolve_ref returns a Col, joining tables as it goes, or the annotation the name refers to
    q = Ship.objects.all().query
    F('tonnage').resolve_expression(q)  ->  Col(fleet_ship, fleet.Ship.tonnage)
    F('home').resolve_expression(q), list(q.alias_map)  ->  (Col(fleet_ship, fleet.Ship.home), ['fleet_ship', 'fleet_port'])
    F('home__name').resolve_expression(q), list(q.alias_map)  ->  (Col(fleet_port, fleet.Port.name), ['fleet_ship', 'fleet_port'])
    F('name__lower').resolve_expression(q)  ->  raises FieldError: Cannot resolve keyword 'lower' into field. Join on 'name' not permitted.
    F('cargo').resolve_expression(q)  ->  raises FieldError: Cannot resolve keyword 'cargo' into field. Choices are: captain, captain_id, crew, home, home_id, id, name, tonnage, voyage
    F('crew').resolve_expression(q), list(q.alias_map)  ->  (Col(crew_sailor, crew.Sailor.id), ['fleet_ship', 'fleet_port', 'crew_sailor'])
    annotated = Ship.objects.annotate(hands=Count('crew')).query
    F('hands').resolve_expression(annotated)  ->  Count(Col(crew_sailor, crew.Sailor.id))
```

A field of the model is its column; a foreign key is its own column, `"home_id"`, and the join to the port that `setup_joins` made was taken back, though its alias stays in the map; a name across the relation is the port's column, and the join stays. `"lower"` had not yet been registered as a transform at this point of the recording, so the walk fails on the word ([Transforms and database functions: `Transform` and `Func`](functions.md)); a word that is nothing lists the choices. A reverse relation resolves to the related table's primary key, and an annotation's name to the annotation.

## `Combinable`: what the operators make

`Combinable` is the mixin that gives an expression Python's operators, and `F`, `Expression` and `Subquery` have it among their bases (`django/db/models/expressions.py:Combinable`). The arithmetic operators, addition, subtraction, multiplication, division, modulo and power, with their reflected forms, each call `Combinable._combine` with a connector string, and `_combine` returns a `CombinedExpression` of the two sides and the connector, with the sides swapped for a reflected call so that `1 + F("tonnage")` keeps Python's order. A side that has no `resolve_expression` is wrapped in a `Value` first. Unary minus is a multiplication by `-1`. The bitwise operations are methods, `Combinable.bitand`, `bitor`, `bitxor`, `bitleftshift` and `bitrightshift`, with the connectors `"&"`, `"|"`, `"#"`, `"<<"` and `">>"`.

`&`, `|` and `^` are kept for conditions. `Combinable.__and__` and its two fellows return `Q(self) & Q(other)`, `Q` with the operator, when both sides are conditional, and raise `NotImplementedError` otherwise, pointing at the bitwise methods; the reflected forms always raise. `~` is `Combinable.__invert__`, a `NegatedExpression` of the expression. And indexing an `F`, `F("name")[0]` or `F("name")[2:4]`, is `F.__getitem__`, which returns a `Sliced` (`django/db/models/expressions.py:Combinable.__and__`, `django/db/models/expressions.py:F.__getitem__`).

```text recording=sql
plus = F('tonnage') + 1
type(plus).__name__, plus.lhs, plus.connector, plus.rhs, plus.get_source_expressions()  ->  ('CombinedExpression', F(tonnage), '+', Value(1), [F(tonnage), Value(1)])
...
F('tonnage') & F('home')  ->  raises NotImplementedError: Use .bitand(), .bitor(), and .bitxor() for bitwise logical operations.
type(Q(tonnage__gt=1) & Exists(Sailor.objects.all())).__name__, type(Exists(Sailor.objects.all()) & Exists(Voyage.objects.all())).__name__, type(~Exists(Sailor.objects.all())).__name__  ->  ('Q', 'Q', 'NegatedExpression')
1 + F('tonnage'), (1 + F('tonnage')).lhs, F('tonnage')[2:4], F('name')[0]  ->  (<CombinedExpression: Value(1) + F(tonnage)>, Value(1), Sliced(F(tonnage), slice(2, 4, None)), Sliced(F(name), slice(0, 1, None)))
```

The connectors are the class attributes `Combinable.ADD` and its fellows, and most are the SQL operator itself. `Combinable.MOD` is `"%%"`, the percent sign doubled, because the SQL the expression writes is later put through parameter substitution, where a lone `%` would be taken for a placeholder; `Combinable.POW` is `"^"` and `Combinable.BITXOR` is `"#"`, and a backend rewrites either where its SQL has no such operator.

### `CombinedExpression`

`CombinedExpression.as_sql` compiles the two sides, has the backend join them with `BaseDatabaseOperations.combine_expression`, and wraps the result in parentheses so that the precedence of nested expressions is kept (`django/db/models/expressions.py:CombinedExpression.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.combine_expression`). The base operations join the two sides with the connector between; SQLite's write `"^"` as the function `"POWER"` and `"#"` as `"BITXOR"`, `"BITXOR"` a function Django registers with the connection and `"POWER"` one it registers where the SQLite build has no math functions of its own, and MySQL's and Oracle's each rewrite the power and several of the bitwise connectors, Oracle's the modulo as well, and Oracle's refuses `"#"` (`django/db/backends/sqlite3/operations.py:DatabaseOperations.combine_expression`).

```text recording=sql
type(plus.resolve_expression(q).output_field).__name__, type((F('tonnage') * F('tonnage')).resolve_expression(q).output_field).__name__, type((F('tonnage') + 1.5).resolve_expression(q).output_field).__name__  ->  ('IntegerField', 'PositiveIntegerField', 'FloatField')
type((F('tonnage') - 1).resolve_expression(q).output_field).__name__  ->  'IntegerField'
(F('name') + 1).resolve_expression(q).output_field  ->  raises FieldError: Cannot infer type of '+' expression involving these types: CharField, IntegerField. You must set output_field.
(F('name') + 1).resolve_expression(q)  ->  <CombinedExpression: Col(fleet_ship, fleet.Ship.name) + Value(1)>
type((F('sailed') - F('sailed')).resolve_expression(Voyage.objects.all().query)).__name__, type((F('sailed') - F('sailed')).resolve_expression(Voyage.objects.all().query).output_field).__name__  ->  ('TemporalSubtraction', 'DurationField')
type((F('sailed') + datetime.timedelta(days=7)).resolve_expression(Voyage.objects.all().query)).__name__, type((F('sailed') + datetime.timedelta(days=7)).resolve_expression(Voyage.objects.all().query).output_field).__name__  ->  ('DurationExpression', 'DateTimeField')
(F('tonnage') + 1).resolve_expression(q).as_sql(q.get_compiler('default'), connection)  ->  ('("fleet_ship"."tonnage" + %s)', (1,))
Voyage.objects.all().query.get_compiler('default').compile((F('sailed') + datetime.timedelta(days=7)).resolve_expression(Voyage.objects.all().query))  ->  ('(django_format_dtdelta(\'+\', "fleet_voyage"."sailed", %s))', (604800000000,))
Voyage.objects.all().query.get_compiler('default').compile((F('sailed') - F('sailed')).resolve_expression(Voyage.objects.all().query))  ->  ('django_timestamp_diff("fleet_voyage"."sailed", "fleet_voyage"."sailed")', ())
(F('tonnage') ** 2).resolve_expression(q).as_sql(q.get_compiler('default'), connection), (F('tonnage') % 7).resolve_expression(q).as_sql(q.get_compiler('default'), connection)  ->  (('(POWER("fleet_ship"."tonnage",%s))', (2,)), ('("fleet_ship"."tonnage" %% %s)', (7,)))
(F('tonnage').bitand(4)).resolve_expression(q).as_sql(q.get_compiler('default'), connection), (-F('tonnage')).resolve_expression(q).as_sql(q.get_compiler('default'), connection)  ->  (('("fleet_ship"."tonnage" & %s)', (4,)), ('("fleet_ship"."tonnage" * %s)', (-1,)))
```

The type of the result is looked up, not inferred from the sides as other expressions infer it. `CombinedExpression._resolve_output_field` asks `_resolve_combined_type` for the connector and the classes of the two sides' output fields, and that function walks a table of triples registered at import from `_connector_combinations`, returning the result class of the first triple whose left and right classes the sides' classes are subclasses of (`django/db/models/expressions.py:CombinedExpression._resolve_output_field`, `django/db/models/expressions.py:_resolve_combined_type`). No triple is `FieldError`, naming the connector and the two types. A project can add a triple with `register_combinable_fields`. The field classes are those of `django/db/models/fields/__init__.py`.

What `_connector_combinations` holds comes to this. Two `PositiveIntegerField` sides give a `PositiveIntegerField` for every arithmetic connector but `SUB`, a comment saying the precedence over `IntegerField` is meant to hold except in subtraction; two sides of one of `IntegerField`, `FloatField` and `DecimalField` give that type for all six arithmetic connectors; and the five bitwise connectors take two `IntegerField` sides and give one. An `IntegerField` with a `DecimalField` gives a `DecimalField` and with a `FloatField` a `FloatField`, in either order, for every arithmetic connector but `POW`; a side with no output field, a `Value(None)`, takes the other side's type where that is one of the three, for all six. For dates, a `DateField` or `DateTimeField` with a `DurationField` on either side gives a `DateTimeField` under `ADD`, and with the duration on the right under `SUB`; one `DateField` or `DateTimeField` less another gives a `DurationField`; a `TimeField` with a `DurationField` on the right gives a `TimeField` under either connector, and with the duration on the left under `ADD`; a `TimeField` less a `TimeField`, and a `DurationField` with a `DurationField` under either, give a `DurationField`. A side's class matches by `issubclass`, so a `BigIntegerField` counts as an `IntegerField`, and the first match is taken.

Two combinations are given a class of their own as they are resolved. `CombinedExpression.resolve_expression` looks at the resolved sides' internal types: where one is `DurationField` and the other is not, it returns a `DurationExpression` of the sides, and where the connector is `-` and both sides are the same one of `DateField`, `DateTimeField` and `TimeField`, a `TemporalSubtraction` (`django/db/models/expressions.py:CombinedExpression.resolve_expression`). `DurationExpression.as_sql` is the plain `as_sql` on a backend whose features have `has_native_duration_field`; elsewhere each side whose type is a duration is passed through the backend's `format_for_duration_arithmetic` and the two are joined by `combine_duration_expression`, which on SQLite writes a call of the registered function `"django_format_dtdelta"`, as the recorded line of a date plus a week shows (`django/db/models/expressions.py:DurationExpression.as_sql`). `TemporalSubtraction` has a `DurationField` for its output and hands both compiled sides to `BaseDatabaseOperations.subtract_temporals`, which refuses with `NotSupportedError` unless `supports_temporal_subtraction` is set, and which SQLite's operations write as `"django_timestamp_diff"`, or `"django_time_diff"` where the sides are times, as the line of a date less itself shows (`django/db/models/expressions.py:TemporalSubtraction.as_sql`).

## Writing SQL: `as_sql` and a vendor's method

`BaseExpression.as_sql` is the method every expression must implement, and the base class's raises `NotImplementedError` (`django/db/models/expressions.py:BaseExpression.as_sql`). It takes the compiler and the connection and returns the SQL with its parameters, compiling its own sources through `SQLCompiler.compile`, which prefers a method named for the connection's vendor where a node has one ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md), `django/db/models/sql/compiler.py:SQLCompiler.compile`). Many `as_sql` methods, `Func.as_sql`, `Value.as_sql`, `When.as_sql` and `Case.as_sql` among them, first call the backend's `check_expression_support`, which does nothing in the base operations and on SQLite refuses `Sum`, `Avg`, `StdDev` and `Variance` over a date, time or datetime column, and `"DISTINCT"` on an aggregate of several arguments (`django/db/backends/base/operations.py:BaseDatabaseOperations.check_expression_support`, `django/db/backends/sqlite3/operations.py:DatabaseOperations.check_expression_support`).

`SQLiteNumericMixin` is the pattern of a vendor's method: its `as_sqlite` calls the class's `as_sql` and wraps the result in `"CAST(... AS NUMERIC)"` where the output field is a `DecimalField` (`django/db/models/fields/__init__.py:DecimalField`), since, its docstring says, such an expression must be cast to be filtered properly on SQLite, and `CombinedExpression`, `Func`, `ExpressionWrapper`, `Case` and `Window` put it first among their bases (`django/db/models/expressions.py:SQLiteNumericMixin.as_sqlite`); [Transforms and database functions: `Transform` and `Func`](functions.md) has what a function class does with it.

A part of an expression may refuse to be written. A `WhereNode` that can match nothing raises `EmptyResultSet` from its `as_sql`, and one that matches everything `FullResultSet` ([The where clause: `build_filter`, `add_q` and `WhereNode`](where.md)); an expression that compiles such a part decides what that means for itself. `Func.as_sql` puts the part's `empty_result_set_value` in its place, or `True` for a full one; `Case.as_sql` drops the case or takes its result for the default; `NegatedExpression.as_sql` and `Exists.as_sql` write a constant.

## The output field

An expression's type is a field object, `BaseExpression.output_field`, and it comes from one of three places: declared on the class, as `Length` declares an `IntegerField` and `TemporalSubtraction` a `DurationField` (`django/db/models/functions/text.py:Length`, `django/db/models/fields/__init__.py`); given at construction, since `BaseExpression.__init__` stores an `output_field` it is handed on the instance, over the class's; or inferred from the sources by `BaseExpression._resolve_output_field` the first time the property is read, since it is a `cached_property` (`django/db/models/expressions.py:BaseExpression.output_field`, `django/db/models/expressions.py:BaseExpression._resolve_output_field`). The inference takes the output fields of the sources, through `BaseExpression.get_source_fields`, leaves out those that have none, and returns the first, after checking that it is an instance of each later one's class; a later source of another class is `FieldError`, "mixed types". So `Coalesce('tonnage', 0)` is a `PositiveIntegerField`, the tonnage's own, because that is an `IntegerField` as the `Value` is; `Coalesce('name', 0)` is refused, and so is `Coalesce(0, 'tonnage')`, whose first source is an `IntegerField` and not a `PositiveIntegerField`.

> **Why.** A comment above the inference calls the guess mostly a bad idea, kept because a lot of code, third-party `Func` subclasses especially, depends on it, and changing it would need a deprecation path (`django/db/models/expressions.py:BaseExpression._resolve_output_field`).

Where nothing gives a type, `output_field` raises `OutputFieldIsNoneError`, a `FieldError`, and `BaseExpression._output_field_or_none` is the way to ask without the exception. The inference is what asks it of each source, which is why a `Value(None)` among the arguments of a function does not decide the function's type.

```text recording=sql
Length('name').output_field, Coalesce('tonnage', 0).resolve_expression(q).output_field, type(Coalesce('tonnage', 0).resolve_expression(q).output_field).__name__  ->  (<django.db.models.fields.IntegerField>, <django.db.models.fields.PositiveIntegerField: tonnage>, 'PositiveIntegerField')
Coalesce('name', 0).resolve_expression(q).output_field  ->  raises FieldError: Expression contains mixed types: CharField, IntegerField. You must set output_field.
Coalesce(0, 'tonnage').resolve_expression(q).output_field  ->  raises FieldError: Expression contains mixed types: IntegerField, PositiveIntegerField. You must set output_field.
type(Func(F('name'), function='X').resolve_expression(q).output_field).__name__, type(Avg('tonnage').resolve_expression(q).output_field).__name__, type(Sum('tonnage').resolve_expression(q).output_field).__name__  ->  ('CharField', 'FloatField', 'PositiveIntegerField')
Func(Value(None), function='X').output_field  ->  raises OutputFieldIsNoneError: Cannot resolve expression type, unknown output_field
Func(Value(None), function='X')._output_field_or_none  ->  None
Func(Value(None), function='X').conditional  ->  raises OutputFieldIsNoneError: Cannot resolve expression type, unknown output_field
```

The type is what other members answer from. `BaseExpression.conditional` is whether the output field is a `BooleanField`, and is what `Query.build_filter` and `When` ask of an expression before they take it for a condition. `BaseExpression.get_lookup` and `get_transform` pass a word to the output field's registry ([The lookup registry: `RegisterLookupMixin`](../querysets/lookups.md)). And `BaseExpression.convert_value` is a function the compiler runs over the value the driver returned: by the output field's internal type, a `FloatField` is made a `float`, a field whose internal type ends in `IntegerField` an `int` and a `DecimalField` a `decimal.Decimal`, and for every other type it is `BaseExpression._convert_value_noop`. `BaseExpression.get_db_converters` returns that function, unless it is the noop, and then the output field's own converters after it; the compiler puts the backend's first (`django/db/models/expressions.py:BaseExpression.convert_value`, `django/db/models/sql/compiler.py:SQLCompiler.get_converters`). The docstring's reason is that an output field may be given by hand, as a type the database does not return. The line that lists four resolved expressions asks each for the names of its own converters.

```text recording=sql
ExpressionWrapper(F('tonnage') * 1.5, output_field=models.FloatField()).resolve_expression(q).convert_value(2.0, None, connection), Sum('tonnage').resolve_expression(q).convert_value is BaseExpression._convert_value_noop  ->  (2.0, False)
[(brief(e), converter_names(e)) for e in (Lower('name').resolve_expression(q), Cast('tonnage', models.FloatField()).resolve_expression(q), Cast('name', models.DateField()).resolve_expression(q), Count('crew').resolve_expression(q))]  ->  [('Lower(Col(fleet_ship, fleet.Ship.name))', []), ('Cast(Col(fleet_ship, fleet.Ship.tonnage))', ["BaseExpression.convert_value's lambda"]), ('Cast(Col(fleet_ship, fleet.Ship.name))', []), ('Count(Col(crew_sailor, crew.Sailor.id))', ["BaseExpression.convert_value's lambda"])]
```

A `Cast` to a `FloatField` carries the converter that makes a `float`; a `Cast` to a `DateField` carries none of its own, since the date is the backend's converter's to parse; a `Lower` has none. `BaseExpression.select_format` is the one place the type reaches the select list: it hands the compiled SQL to the output field's `select_format` where the field has one, and `Field.select_format` returns it unchanged, so the hook is for a field such as a geometry that must be selected through a function (`django/db/models/fields/__init__.py:Field.select_format`) ([The SELECT clause: `get_select`, the select mask and `klass_info`](select.md)).

## `Expression`: equality by construction

`Expression` is `BaseExpression` with `Combinable`, and the class on which equality is defined (`django/db/models/expressions.py:Expression`). It is decorated with `deconstructible`, which replaces the class's `__new__` with one that stores the arguments the constructor was called with on the instance, as `_constructor_args`, and adds a `deconstruct` that gives them back with the class's import path, so that a migration can write the expression down ([A field: the base class](../models/fields.md), `django/utils/deconstruct.py:deconstructible`). `Func`, `Value`, `JSONNull`, `ExpressionWrapper`, `When`, `Case` and `OrderBy` are decorated again, each with the path under `django.db.models` it is imported from, and `F`, which is no `Expression`, is decorated on its own.

`Expression.identity` is built from those arguments. It binds them to the signature of the class's `__init__` with the defaults filled in, and makes a tuple of the class followed by each parameter's name and value, the value passed through `Expression._identity`: a tuple or a dictionary is taken apart, a bound field becomes its model's label and its name and an unbound one its class, and anything else goes through `make_hashable` (`django/db/models/expressions.py:Expression.identity`, `django/utils/hashable.py:make_hashable`). `Expression.__eq__` compares identities, and only with another `Expression`; `Expression.__hash__` hashes the identity.

```text recording=sql
Identity: two expressions made the same way are equal, and hash alike
    F('name') == F('name'), F('name') == F('tonnage'), Value(1) == Value(1), Value(1) == Value('1'), Lower('name') == Lower('name'), Lower('name') == Upper('name')  ->  (True, False, True, False, True, False)
    Count('crew') == Count('crew'), Count('crew') == Count('crew', distinct=True), Count('crew').identity  ->  (True, False, (<class 'django.db.models.aggregates.Count'>, ('expression', 'crew'), ('filter', None), ('extra', ())))
    Exact(Col('fleet_ship', Ship._meta.get_field('name')), 'x') == Exact(Col('fleet_ship', Ship._meta.get_field('name')), 'x'), Exact(Col('fleet_ship', Ship._meta.get_field('name')), 'x').identity  ->  (True, (<class 'django.db.models.lookups.Exact'>, Col(fleet_ship, fleet.Ship.name), 'x'))
    len({F('name'), F('name'), Lower('name'), Lower('name'), Value(1)})  ->  3
    OrderBy(F('name')).reverse_ordering() == OrderBy(F('name')), OrderBy(F('name')).reverse_ordering().descending  ->  (True, True)
```

`Count('crew').identity` reads the constructor's parameters by name, `expression`, `filter` and the keyword arguments gathered in `extra`, with the defaults that were not given. `Value(1)` and `Value('1')` differ in the value; `Count('crew')` and `Count('crew', distinct=True)` in a keyword. Two classes define equality their own way: `F.__eq__` compares the class and the name, and `Lookup.identity` is the class, the left side and the right side (`django/db/models/expressions.py:F.__eq__`, `django/db/models/lookups.py:Lookup.identity`). The identity is what `replace_expressions` looks its dictionary up by, and what lets `SQLCompiler.get_order_by` tell that an ordering is a selected expression ([ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md)).

> **Trap.** The identity is the constructor's arguments, not the attributes, and it is cached on first use. `OrderBy.reverse_ordering` flips `descending` in place and returns the same object, which is still equal to an `OrderBy` made with the original arguments, as the question about `OrderBy(F('name')).reverse_ordering()` shows (`django/db/models/expressions.py:OrderBy.reverse_ordering`).

## The small classes

### `Value`

`Value` holds a Python value that is to go to the database as a parameter (`django/db/models/expressions.py:Value`). It infers its output field from the value's type in `Value._resolve_output_field`, among the classes of `django/db/models/fields/__init__.py`:

| the output field | the value's type |
| --- | --- |
| `CharField` | `str` |
| `BooleanField` | `bool`, tested before `int` since a `bool` is one |
| `IntegerField` | `int` |
| `FloatField` | `float` |
| `DateTimeField` | `datetime.datetime`, tested before `datetime.date` for the same reason |
| `DateField` | `datetime.date` |
| `TimeField` | `datetime.time` |
| `DurationField` | `datetime.timedelta` |
| `DecimalField` | `decimal.Decimal` |
| `BinaryField` | `bytes` |
| `UUIDField` | `uuid.UUID` |
| none | any other, `None`'s among them |

```text recording=sql
Value: the output field it infers from its value, and the placeholder it writes
    [type(Value(v).output_field).__name__ for v in ('x', True, 1, 1.5, datetime.date(2026, 4, 10), datetime.datetime(2026, 4, 10, 9), datetime.timedelta(days=1), Decimal('1.5'), b'x')]  ->  ['CharField', 'BooleanField', 'IntegerField', 'FloatField', 'DateField', 'DateTimeField', 'DurationField', 'DecimalField', 'BinaryField']
    Value(None).output_field  ->  raises OutputFieldIsNoneError: Cannot resolve expression type, unknown output_field
    Value(None)._output_field_or_none, Value([1, 2])._output_field_or_none  ->  (None, None)
    Value(480).as_sql(None, connection), Value(None).as_sql(None, connection), Value('Ada', output_field=models.CharField()).as_sql(None, connection)  ->  (('%s', (480,)), ('NULL', ()), ('%s', ('Ada',)))
    Value(480).resolve_expression(q).for_save, Value(480).resolve_expression(q, for_save=True).for_save, Value(480).for_save  ->  (False, True, False)
    Value(Decimal('1.5')).as_sqlite(None, connection), Value(1.5, output_field=models.DecimalField()).as_sqlite(None, connection)  ->  (('(CAST(%s AS REAL))', (Decimal('1.5'),)), ('(CAST(%s AS NUMERIC))', (Decimal('1.5'),)))
```

`Value.as_sql` is where the field prepares the value, and `for_save` chooses the preparation: with an output field, the value goes through the field's `get_db_prep_save` when `for_save` is set and `get_db_prep_value` otherwise, and without one it goes as it is; either way it is written as `"%s"` with the value for its parameter (`django/db/models/expressions.py:Value.as_sql`). Two values are written otherwise: a field that has a `get_placeholder_sql`, as a `BinaryField` has, writes the placeholder itself, and a `None` is written as the literal `"NULL"` rather than a parameter, a comment saying that oracledb does not always convert a `None` to the right kind of null. `Value.resolve_expression` is the base method with `for_save` recorded on the copy, and the class attribute `for_save` is `False` so that an unresolved `Value` can be compiled. `Value.as_sqlite` wraps a value whose output field is a `DecimalField` in a cast, to `"REAL"` where the value is a `decimal.Decimal` and to `"NUMERIC"` where it is not.

### `Col` and `ColPairs`

`Col` is a column of a table the query has joined: an alias and a target field, with an output field that is the target unless another is given (`django/db/models/expressions.py:Col`). `Col.as_sql` writes the alias and the column's name, each quoted through `SQLCompiler.quote_name`, or the column alone where the alias is `None`. It is made by `Field.get_col`, which returns the field's `Field.cached_col` when the alias is the table's own name and the output field is the field itself, so that the same `Col` serves every plain query of the model, and a new one otherwise (`django/db/models/fields/__init__.py:Field.get_col`). `Col.get_db_converters`, which the compiler reads for a column's converters, is the output field's converters followed by the target's where the two differ.

`ColPairs` stands for the columns of a composite primary key as one expression: an alias, the target fields, the source fields and the key as the output field (`django/db/models/expressions.py:ColPairs`). `ColPairs.get_cols` makes a `Col` for each pair, which is what it gives as its sources and what `ColPairs.as_sql` writes, joined with commas. `CompositePrimaryKey.get_col` makes one, so `F("pk")` on such a model resolves to a `ColPairs` (`django/db/models/fields/composite.py:CompositePrimaryKey.get_col`). The lookups that take it apart are in [Lookups on relations and composite keys: `RelatedIn` and the tuple lookups](related-lookups.md), and the field in [The field classes](../models/field-types.md).

### `Ref`, `Star` and `RawSQL`

`Ref` is a reference to a selected expression by its alias, `Ref("hands", Count(...))`, and `Ref.as_sql` writes the alias alone, quoted by the backend's `quote_name` (`django/db/models/expressions.py:Ref`). Its source is already resolved, which is why `Ref.resolve_expression` returns itself, and `Ref.get_refs` is the one place a name comes from in the set `BaseExpression.get_refs` collects over a tree: the query reads that set to learn which annotations an aggregate or a `"HAVING"` condition refers to ([GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md)). `Star` writes `"*"`, and is what `Count("*")` holds.

`RawSQL` is SQL a program wrote, with its parameters and an output field that is a bare `Field` unless another is given; `RawSQL.as_sql` writes it in parentheses, and it stands whole in a `GROUP BY` (`django/db/models/expressions.py:RawSQL`). `RawSQL.resolve_expression` has one task of its own: for each parent model of the query's model, it looks through the SQL for the column names of the parent's own fields and, finding one, resolves that field's name through `Query.resolve_ref`, so that the join to the parent's table is made for SQL the query cannot read (`django/db/models/expressions.py:RawSQL.resolve_expression`).

```text recording=sql
compiler.compile(RawSQL('tonnage * %s', (2,)))  ->  ('(tonnage * %s)', (2,))
compiler.compile(Ref('hands', Count('crew'))), compiler.compile(Star())  ->  (('"hands"', ()), ('*', ()))
```

### `Case` and `When`

A `When` is a condition and a result (`django/db/models/expressions.py:When`). `When.__init__` takes the condition as a `Q`, a conditional expression, or keyword arguments that it makes a `Q` of, after refusing the two keywords `Q` keeps for itself as [`filter`, `exclude` and `Q` objects](../querysets/filters.md) tells; anything else is `TypeError`, and an empty `Q` is `ValueError`. Its result is the then argument, parsed as a string into an `F` and a plain value into a `Value`. Resolving a `When` resolves both, and where it is for a save the condition is resolved again with `for_save=False`. `When.as_sql` writes `WHEN condition THEN result`, and `When.get_source_fields` gives the result's field alone, so that a `Case` infers its type from its results and not its conditions. A `When` is not conditional itself, and is not a complete expression: `When.get_group_by_cols` gives its parts' columns.

`Case.__init__` takes `When` objects and nothing else, a default parsed the same way as a result, with `None` becoming `Value(None)`, and an output field (`django/db/models/expressions.py:Case`). What `Case.as_sql` adds to filling the template is the handling of a condition whose answer is known before any SQL is written: a case whose condition raises `EmptyResultSet` is left out, and one that raises `FullResultSet` ends the loop, its result becoming the default. Where no case remains to be written the default alone is compiled, wrapped in a `Cast` to its output field where it is a `Value` that has one; a `Case` made with no cases compiles its default alone too, without the cast. Otherwise the template is filled and, where the `Case` has an output field, the whole is passed through the backend's `unification_cast_sql` for it, which is `"%s"` in the base operations and on PostgreSQL a cast for the four types that database would otherwise resolve as text (`django/db/models/expressions.py:Case.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.unification_cast_sql`).

```text recording=sql
compiler.compile(Case(When(tonnage__gt=1000, then=Value('big')), default=Value('small')).resolve_expression(q))  ->  ('CASE WHEN "fleet_ship"."tonnage" > %s THEN %s ELSE %s END', (1000, 'big', 'small'))
compiler.compile(Case(When(tonnage__gt=1000, then=Value('big')), output_field=models.CharField()).resolve_expression(q))  ->  ('CASE WHEN "fleet_ship"."tonnage" > %s THEN %s ELSE NULL END', (1000, 'big'))
compiler.compile(Case(When(Q(pk__in=[]), then=Value('never')), default=Value('always')).resolve_expression(q))  ->  ('CAST(%s AS text)', ('always',))
compiler.compile(Case(When(Q(), then=Value('x')), default=Value('y')).resolve_expression(q))  ->  raises ValueError: An empty Q() can't be used as a When() condition.
When(tonnage__gt=1)  ->  <When: WHEN <Q: (AND: ('tonnage__gt', 1))> THEN Value(None)>
When(F('tonnage'), then=1)  ->  raises TypeError: When() supports a Q object, a boolean expression, or lookups as a condition.
Case(Value(1))  ->  raises TypeError: Positional arguments must all be When objects.
```

The condition of a `When` is resolved as a `Q` is anywhere else, into a `WhereNode` through `Query._add_q`, and the condition `Q(pk__in=[])` can match nothing, so the whole `Case` became the default, cast to `text`.

### `ExpressionWrapper` and `NegatedExpression`

`ExpressionWrapper` gives an expression an output field it lacks or another than its own, and nothing else: `ExpressionWrapper.as_sql` compiles the inner expression (`django/db/models/expressions.py:ExpressionWrapper`). On SQLite the mixin adds the numeric cast where the field given is a `DecimalField`. `ExpressionWrapper.get_group_by_cols` asks a copy of the inner expression carrying the wrapper's output field, and where the inner thing is not an `Expression` at all, a where tree, answers as the base class does, with the whole wrapper unless it contains an aggregate.

`NegatedExpression` is an `ExpressionWrapper` with a `BooleanField`, made by `~` on a conditional expression (`django/db/models/expressions.py:NegatedExpression`). `NegatedExpression.resolve_expression` refuses, with `TypeError`, an inner expression that is not conditional once resolved. `NegatedExpression.as_sql` writes `"NOT"` before the inner SQL, or, where the backend's `conditional_expression_supported_in_where_clause` says the expression cannot stand alone in a `"WHERE"`, a `CASE WHEN ... = 0 THEN 1 ELSE 0 END`; an inner expression that raises `EmptyResultSet` becomes `True`, or `"1=1"` where the backend's features lack `supports_boolean_expr_in_select_clause` (`django/db/backends/base/operations.py:BaseDatabaseOperations.conditional_expression_supported_in_where_clause`). Negating it again gives back a copy of the inner expression.

```text recording=sql
compiler.compile(ExpressionWrapper(F('tonnage') * 2, output_field=models.DecimalField()).resolve_expression(q))  ->  ('(CAST(("fleet_ship"."tonnage" * %s) AS NUMERIC))', (2,))
compiler.compile(ExpressionWrapper(F('tonnage') * 2, output_field=models.IntegerField()).resolve_expression(q))  ->  ('("fleet_ship"."tonnage" * %s)', (2,))
compiler.compile(NegatedExpression(Q(tonnage__gt=1000)).resolve_expression(q))  ->  ('NOT "fleet_ship"."tonnage" > %s', [1000])
NegatedExpression(F('tonnage')).resolve_expression(q)  ->  raises TypeError: Cannot negate non-conditional expressions.
```

### `OrderBy`, `ExpressionList` and `OrderByList`

`OrderBy` is an expression with a direction, `descending`, and the two modifiers `nulls_first` and `nulls_last`, which `OrderBy.__init__` refuses together, or as `False` (`django/db/models/expressions.py:OrderBy`). `BaseExpression.asc` and `desc` make one of any expression, and `F.asc` and `desc` likewise; `OrderBy.reverse_ordering` flips the direction and swaps the modifiers in place. What `OrderBy.as_sql` writes, and the emulation of the modifiers where a backend lacks them, is in [ORDER BY and DISTINCT: `get_order_by`, `find_ordering_name` and `get_distinct`](ordering.md).

`ExpressionList` is a `Func` whose template is its expressions alone, joined by commas, for a place that wants several, such as a window's partition; it writes nothing for no expressions, and skips the numeric cast on SQLite (`django/db/models/expressions.py:ExpressionList`). `OrderByList` is one with `ORDER BY` in front, which turns a string beginning with `-` into a descending `OrderBy` of the name; `OrderByList.from_param` makes one from a string, an expression, or a list or tuple of them, gives `None` for `None` or an empty list, and refuses anything else with `ValueError` naming the parameter (`django/db/models/expressions.py:OrderByList.from_param`). A `Window` and an aggregate's `order_by` are built on them ([Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md)).

### `DatabaseDefault` and `JSONNull`

`DatabaseDefault` wraps the expression of a field's `db_default`, resolves to that expression alone unless `for_save` is set, and writes the keyword `"DEFAULT"` where the backend's features have `supports_default_keyword_in_insert` and compiles the expression where not, as SQLite's lack it (`django/db/models/expressions.py:DatabaseDefault`, `django/db/backends/sqlite3/features.py:DatabaseFeatures.supports_default_keyword_in_insert`); the insert that writes it is in [INSERT, UPDATE and DELETE: the insert, update and delete compilers](writing.md).

`JSONNull` is a `Value` of `None` with a `JSONField` for its output, the JSON scalar `null` as against SQL's `"NULL"`, written as a placeholder whose parameter the field prepares (`django/db/models/expressions.py:JSONNull`, `django/db/models/fields/json.py:JSONField`).

> **Changed in 6.1.** `JSONNull` is new in 6.1. Using `None` for a top-level JSON `null` in a query on a `JSONField` is deprecated at the same time; when the deprecation ends, a `None` at the top level compiles to `IS NULL` (`docs/releases/6.1.txt`).

### `Sliced`

`Sliced` is what indexing an `F` makes: an `F` of the same name that remembers a start and a length, the start one past the index since SQL counts from one, with a negative bound, a step or a stop before the start refused (`django/db/models/expressions.py:Sliced`). `Sliced.resolve_expression` resolves the name through `Query.resolve_ref` and hands the column, the start and the length to the output field's `slice_expression`, which `Field.slice_expression` refuses with `NotSupportedError` and `CharField`'s and `TextField`'s answer with a `Substr` (`django/db/models/fields/__init__.py:Field.slice_expression`, `django/db/models/fields/__init__.py:CharField.slice_expression`).

```text recording=sql
compiler.compile(Sliced(F('name'), slice(0, 3)).resolve_expression(q)), compiler.compile(F('name')[1].resolve_expression(q))  ->  (('SUBSTR("fleet_ship"."name", %s, %s)', (1, 3)), ('SUBSTR("fleet_ship"."name", %s, %s)', (2, 1)))
Sliced(F('name'), -1)  ->  raises ValueError: Negative indexing is not supported.
```

## What an expression says about itself

Several questions are asked of an expression by the query and the compiler before any SQL is written, and the answers are attributes. Four are computed over the sources: `BaseExpression.contains_aggregate`, `contains_over_clause`, `contains_column_references` and `contains_subquery` are each a `cached_property` that is true when any source's is, and a class that is the thing itself sets the attribute instead, so that a `Window` is a window and not an aggregate though its function is one (`django/db/models/expressions.py:BaseExpression.contains_aggregate`). The rest are class attributes a subclass may override.

| attribute | on `BaseExpression` | who reads it |
|---|---|---|
| `contains_aggregate` | any source's | the grouping, and `Aggregate.resolve_expression` |
| `contains_over_clause` | any source's | the where tree, for the `"QUALIFY"` rewrite |
| `contains_column_references` | any source's | `SQLInsertCompiler.prepare_value`, which refuses a value with a column in it (`django/db/models/sql/compiler.py:SQLInsertCompiler.prepare_value`) |
| `contains_subquery` | any source with `subquery` set, or whose own is | `Query.get_aggregation` |
| `conditional` | whether the output field is a `BooleanField` (`django/db/models/fields/__init__.py:BooleanField`) | `build_filter`, `When`, the operators of `Combinable` |
| `filterable` | true | `Query.check_filterable`, which refuses with `NotSupportedError` |
| `window_compatible` | false | `Window.__init__` |
| `allowed_default` | false | the field's check of its `db_default` |
| `set_returning` | false | `Query.get_aggregation`, which keeps such an annotation selected |
| `allows_composite_expressions` | false | `resolve_expression`, before refusing a `ColPairs` |
| `constraint_validation_compatible` | true | `get_expression_for_validation`, which then gives the one source instead |
| `empty_result_set_value` | `NotImplemented` | `Func.as_sql` and the compiler, for a part that can match nothing |
| `is_summary` | false | the aggregation |

*The marks, what each is on the base class, and the reader each is for. `filterable` is false and `set_returning` true on nothing the models package defines: the first is for an expression a project writes that may not stand in a `"WHERE"`, the second for one that returns more than one row.*

```text recording=sql
resolved.contains_aggregate, resolved.contains_over_clause, resolved.contains_column_references, resolved.conditional, resolved.filterable, resolved.window_compatible  ->  (False, False, True, False, True, False)
Count('crew').contains_aggregate, Window(RowNumber()).contains_over_clause, Window(RowNumber()).contains_aggregate, Value(1).contains_column_references, Q(tonnage__gt=1).conditional, Exists(Sailor.objects.all()).conditional  ->  (True, True, False, False, True, True)
```

## Walking and rewriting a tree

The base class gives every expression the same few ways of being walked and copied, all through its sources, so that a class that implements the pair of source methods has them for free (`django/db/models/expressions.py:BaseExpression.relabeled_clone`).

Two of them carry the chapter. `BaseExpression.relabeled_clone` makes a copy whose sources are relabeled by a map from old aliases to new, a `Col` answering by changing its alias and an `OuterRef` by returning itself: it is how a query's where tree and annotations are moved to new aliases when the query becomes a subquery or is combined with another ([Tables and joins: the alias map and join promotion](joins.md)). `BaseExpression.replace_expressions` takes a dictionary from expressions to replacements and returns the replacement for the expression itself if the dictionary has one, itself if it has no sources, and otherwise a copy with each source replaced; `F.replace_expressions` also finds `F("name")` for `F("name__lower")` and applies the transforms to the replacement (`django/db/models/expressions.py:BaseExpression.replace_expressions`). It is how a generated field's expression or a constraint's expressions are worked out for one instance, the instance's values standing where the columns were, as [`filter`, `exclude` and `Q` objects](../querysets/filters.md) tells of a `Q`. The rest are small. `BaseExpression.flatten` is a generator over the tree, the expression first and then each source's flattening, depth first, which a constraint's check reads to find a `RawSQL`; `BaseExpression.prefix_references` makes a copy in which every `F` has a prefix put before its name, for a related model's default ordering brought under a relation's name; `BaseExpression.get_refs` is the set of aliases the tree refers to through `Ref`; and `BaseExpression.copy` is a shallow copy, which `Func` and `Case` deepen by one level so that the lists of sources are not shared.

```text recording=sql
resolved.relabeled_clone({'fleet_ship': 'T9'}), resolved.replace_expressions({F('name'): Value('x')}), low.replace_expressions({F('name'): Value('x')})  ->  (Lower(Col(T9, fleet.Ship.name)), Lower(Col(fleet_ship, fleet.Ship.name)), Lower(Value('x')))
```

`BaseExpression.get_group_by_cols` is the expression's answer to what a `GROUP BY` needs of it: itself, unless it contains an aggregate, and then whatever its sources answer (`django/db/models/expressions.py:BaseExpression.get_group_by_cols`). `Value` answers nothing and so does `Random`; `Col`, `Ref` and `RawSQL` answer themselves; `When`, `OrderBy`, `ExpressionList` and a `Lookup` collect their parts', and a `Case` with no cases its default's. What the compiler does with the answers is [GROUP BY and HAVING: `set_group_by`, `get_group_by` and `split_having_qualify`](grouping.md).
