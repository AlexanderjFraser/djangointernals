---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Transforms and database functions: `Transform` and `Func`

`Func` is a function call as an expression: a function's name, a template, and the arguments compiled into it. `Transform` is a `Func` of one argument that the word of a filter's name can reach, `"lower"` in `"name__lower"`, and that carries a registry of its own for the word after it (`django/db/models/expressions.py:Func`, `django/db/models/lookups.py:Transform`). This page is the two classes and the functions Django ships in `django/db/models/functions/`: the comparisons and casts, the parts and truncations of a date, the text and the mathematical functions, JSON, UUIDs, and the window functions.

A function call has to hold any number of arguments, each of which may be a field's name, a plain value or another expression, and write `"LOWER(...)"` with the arguments inside for one backend, where the function's name or the whole shape of the call may differ by vendor, `"MAX"` for `Greatest` on SQLite and `"(...)::double precision"` for a cast to a float on PostgreSQL. It has to say its type. And where it is a transform it has to be found by a word, applied to a column, and asked for the next word, so that `"name__lower__startswith"` is a lookup on a function of a column. The first is `Func.__init__` and `Func.as_sql`, the second the methods named for a vendor that `SQLCompiler.compile` prefers, the third `BaseExpression.output_field`, and the fourth is what `Transform` adds.

The examples are the shipping line of the chapter's opening page, [From QuerySet to SQL](../sql.md): a Ship has a name, a tonnage and a home port, a Voyage a date it sailed, a Sailor a name and a moment it signed on. Three text transforms, named where registration is told, were registered on `CharField` early in the recording and stay registered through the blocks quoted here, and compiler, where a line names it, is a compiler made for the query of a queryset of every Ship. In what is quoted, a line at the left is a question put to a running Django on SQLite, with its answer after `->`, or a line of Python as it was run, with the calls it set going nested under it as they were made, only the calls the passage is about written down, and `->` what each returned; a line that begins `SQL` is a statement as Django handed it to its cursor, and the dialect in it is SQLite's.

## `Func`: a call as an expression

A `Func` subclass declares what the call looks like, in four class attributes. `function` is the name written before the parentheses, and is `None` on `Func` itself. `template` is the shape of the whole, `"%(function)s(%(expressions)s)"` unless the class says otherwise. `arg_joiner` is what stands between the arguments, a comma and a space. And `arity` is how many arguments the function takes, or `None` for any number (`django/db/models/expressions.py:Func`). `Func.__init__` refuses, with `TypeError`, a number of arguments that is not the arity where one is declared, turns each argument into an expression through `BaseExpression._parse_expressions`, a string into an `F` and a plain value into a `Value`, and keeps them as `Func.source_expressions`; an `output_field` keyword goes to the base class, and every other keyword is kept in `Func.extra`, for the template to use.

```text recording=sql
Func.template, Func.arg_joiner, Func.arity, Lower.function, Lower.lookup_name, Transform.arity, Transform.bilateral  ->  ('%(function)s(%(expressions)s)', ', ', None, 'LOWER', 'lower', 1, False)
Lower('name', 'tonnage')  ->  raises TypeError: 'Lower' takes exactly 1 argument (2 given)
Round('tonnage', 2), Round.arity  ->  (Round(F(tonnage), Value(2)), None)
Concat('name')  ->  raises ValueError: Concat must take at least two expressions
Func('name', function='UPPER').resolve_expression(Ship.objects.all().query).get_source_expressions(), Func('name', 'tonnage', function='X').extra  ->  ([Col(fleet_ship, fleet.Ship.name)], {'function': 'X'})
Func(F('name'), function='X', template='%(function)s[%(expressions)s]').resolve_expression(Ship.objects.all().query).as_sql(compiler, connection)  ->  ('X["fleet_ship"."name"]', ())
Func(F('name'), function='X').resolve_expression(Ship.objects.all().query).as_sql(compiler, connection, function='Y', template='%(function)s<%(expressions)s>')  ->  ('Y<"fleet_ship"."name">', ())
```

`Func.as_sql` fills the template from the compiled sources, and what matters in it is the order in which the function's name, the template and the joiner are taken: a keyword argument of the call first, then `extra` from the constructor, then the class attribute, which is how a vendor method and a caller can each override what the class declares, and how a project passes a template of its own to a plain `Func` (`django/db/models/expressions.py:Func.as_sql`). After the backend's `check_expression_support`, the method compiles each source through `SQLCompiler.compile`, gathering the SQL and the parameters in order; a source that raises `EmptyResultSet` is replaced by its `empty_result_set_value` compiled as a `Value`, or the exception goes on up where the source has none, and one that raises `FullResultSet` by `True`. The joined arguments go into the template under two keys, `"expressions"` and `"field"`, beside everything in `extra`. `Func.copy` copies the list of sources and the dictionary, so that a resolved copy shares neither with its original. An `Aggregate` is a `Func` too, with a template that has room for `"DISTINCT"`, a filter and an ordering, and [Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md) has it.

```text recording=sql
compile: a vendor method is preferred to as_sql, and Func.as_sql fills a template from the compiled sources
    compiler = Ship.objects.all().query.get_compiler('default')
    biggest = Greatest('tonnage', 1000)
      Greatest.__init__(('tonnage', 1000))  (Func.__init__)
    compiler.compile(biggest.resolve_expression(Ship.objects.all().query))
      SQLCompiler.compile(Greatest(Col(fleet_ship, fleet.Ship.tonnage), Value(1000)))
        Greatest.as_sqlite
          Greatest.as_sqlite  (SQLiteNumericMixin.as_sqlite)
            Greatest.as_sql  (Func.as_sql, function='MAX')
              DatabaseOperations.check_expression_support(Greatest(Col(fleet_ship, fleet.Ship.tonnage), Value(1000)))  (sqlite3)
              SQLCompiler.compile(Col(fleet_ship, fleet.Ship.tonnage))  ->  ('"fleet_ship"."tonnage"', ())
              SQLCompiler.compile(Value(1000))
                Value.as_sqlite
                  Value.as_sql  (Value(1000))
                    DatabaseOperations.check_expression_support(Value(1000))  (sqlite3)
                    -> ('%s', (1000,))
                  -> ('%s', (1000,))
                -> ('%s', (1000,))
              -> ('MAX("fleet_ship"."tonnage", %s)', (1000,))
            -> ('MAX("fleet_ship"."tonnage", %s)', (1000,))
          -> ('MAX("fleet_ship"."tonnage", %s)', (1000,))
        -> ('MAX("fleet_ship"."tonnage", %s)', (1000,))
    compiler.compile(Lower('name').resolve_expression(Ship.objects.all().query))
      Lower.__init__(('name',))  (Func.__init__)
      SQLCompiler.compile(Lower(Col(fleet_ship, fleet.Ship.name)))
        Lower.as_sqlite  (SQLiteNumericMixin.as_sqlite)
          Lower.as_sql  (Func.as_sql)
            DatabaseOperations.check_expression_support(Lower(Col(fleet_ship, fleet.Ship.name)))  (sqlite3)
            SQLCompiler.compile(Col(fleet_ship, fleet.Ship.name))  ->  ('"fleet_ship"."name"', ())
            -> ('LOWER("fleet_ship"."name")', ())
          -> ('LOWER("fleet_ship"."name")', ())
        -> ('LOWER("fleet_ship"."name")', ())
```

The first call went through three methods of the one object before the template was filled: the class's own `as_sqlite`, the mixin's, and `Func.as_sql`, with the function's name changed on the way. Each source was compiled through the compiler, the `Value` through its own `as_sqlite`, and the parameters came back in the order of the arguments. `Lower`, which has no `as_sqlite` of its own, went through the mixin's and `Func.as_sql` with the name the class declares.

## A vendor's method

`SQLCompiler.compile` looks on a node for a method named `"as_"` and the connection's vendor, `as_sqlite`, `as_postgresql`, `as_mysql` or `as_oracle`, and calls it instead of `as_sql` where it finds one ([The compiler: `as_sql`, `execute_sql` and `results_iter`](compiler.md), `django/db/models/sql/compiler.py:SQLCompiler.compile`). The pattern of such a method on a `Func` is to call `as_sql` with another `function=`, `template=` or `arg_joiner=`, and nothing else: `Greatest.as_sqlite` asks for `"MAX"`, `Substr.as_sqlite` for `"SUBSTR"`, `Cast.as_postgresql` for the template with `::`, `Now.as_sqlite` for a template that is a call of `"STRFTIME"` (`django/db/models/functions/comparison.py:Greatest.as_sqlite`, `django/db/models/functions/datetime.py:Now`). A few rewrite the sources instead, as `ConcatPair.as_postgresql` casts each argument that is not text to a `TextField`, and a few refuse, as `SHA224.as_oracle` does with `NotSupportedError`.

Two things stand between a class's `as_sqlite` and `Func.as_sql` on SQLite. `SQLiteNumericMixin` is first among the bases of `Func`, and its `as_sqlite` wraps the result in a cast to `"NUMERIC"` where the output field is a `DecimalField`; a class's own `as_sqlite` that reaches the mixin's through `super()` rather than calling the class's `as_sql` directly keeps the cast, as `Greatest.as_sqlite` does ([Expressions: `resolve_expression` and `as_sql`](expressions.md)). And the mixins of `django/db/models/functions/mixins.py` are the vendor methods several classes share: `FixDecimalInputMixin.as_postgresql` casts a `FloatField` argument to a `DecimalField`, since PostgreSQL has no `"LOG"` or `"MOD"` of two doubles; `FixDurationInputMixin` gives `Sum` and `Avg` over a duration a cast on MySQL and, on an Oracle whose features lack `supports_aggregation_over_interval_types`, a conversion through seconds; and `NumericOutputFieldMixin` is not a vendor method but an inference, `_resolve_output_field` answering `DecimalField` where any source is one, `FloatField` where any is an `IntegerField`, the base inference otherwise, and `FloatField` for a function with no sources (`django/db/models/functions/mixins.py:NumericOutputFieldMixin`, `django/db/models/functions/mixins.py:FixDecimalInputMixin`).

## `Transform`: a function of one argument with a registry

`Transform` is `Func` with `arity` set to one, a property `Transform.lhs` for that one source, and `RegisterLookupMixin` put first among its bases (`django/db/models/lookups.py:Transform`). Its docstring gives the reason for the order: `get_lookup` and `get_transform` examine the transform itself first and its output field after. So `Length('name')`, whose registry is empty, answers `"gt"` with the `IntegerGreaterThan` of its `IntegerField`, and a transform may register a lookup of its own that takes precedence, as `ExtractYear` registers the five year lookups ([The lookup registry: `RegisterLookupMixin`](../querysets/lookups.md), `django/db/models/functions/text.py:Length`, `django/db/models/lookups.py:IntegerGreaterThan`).

What makes a word in a filter's name a transform is `Query.build_lookup`: every word but the last is handed to `Query.try_transform`, which asks the left side's `get_transform` for the class and applies it to the left side, and the last word is a lookup, or, where no lookup answers to it, a transform followed by `"exact"` (`django/db/models/sql/query.py:Query.build_lookup`). [From a name to a column: `names_to_path`, `setup_joins` and `build_lookup`](names.md) has the walk and its errors; here is what it leaves:

```text recording=sql
sql_of(Sailor.objects.filter(name__lower__startswith='a'))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE LOWER("crew_sailor"."name") LIKE %s ESCAPE \'\\\'', ('a%',))
sql_of(Sailor.objects.filter(name__upper__lower__length__gt=2))  ->  ('SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE LENGTH(LOWER(UPPER("crew_sailor"."name"))) > %s', (2,))
```

Each transform wrapped the one before, inside out as the words were read, and the last word found its lookup on the outermost transform's output field: `"startswith"` on the `CharField` that `Lower` infers from its argument, `"gt"` on the `IntegerField` that `Length` declares. An `F` with transforms in its name goes the same way through `Query.resolve_ref` ([Expressions: `resolve_expression` and `as_sql`](expressions.md)).

### A bilateral transform

A transform in a filter's name is applied to the left side of the comparison, and the value on the right is compared as it was given, unless the transform is bilateral. `Transform.bilateral`, `False` on the class, says that the transform is to be applied to the right side too. `Transform.get_bilateral_transforms` collects the classes marked so along the chain of transforms, the inner ones first and this one after them where it is bilateral, and `Lookup.__init__` keeps the list as `Lookup.bilateral_transforms` (`django/db/models/lookups.py:Transform.get_bilateral_transforms`, `django/db/models/lookups.py:Lookup.__init__`). `Lookup.process_rhs` then wraps a plain value in a `Value` with the left side's output field, applies each transform class to it, resolves it and compiles it, so that the right side is compiled as an expression, the transforms' SQL around the parameter, instead of being prepared by `Lookup.get_db_prep_lookup`; `Lookup.batch_process_rhs` does the same for each of a list; and a `Query` on the right is refused in the constructor with `NotImplementedError`, since the transforms cannot be applied to a subquery ([Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](lookups.md)). The recording defines a transform of its own, Shout, an `"UPPER"` with `bilateral` set, and registers it on `CharField` for one block:

```text recording=sql
models.CharField.register_lookup(Shout)
Shout.get_lookups(), Length.get_lookups(), Length('name').resolve_expression(Sailor.objects.all().query).get_lookup('gt').__name__, Shout('name').resolve_expression(Sailor.objects.all().query).get_lookup('exact').__name__  ->  ({}, {}, 'IntegerGreaterThan', 'Exact')
tail(Sailor.objects.filter(name__upper='ADA'))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") = %s', ('ADA',))
tail(Sailor.objects.filter(name__shout='ada'))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") = (UPPER(%s))', ('ada',))
tail(Sailor.objects.filter(name__shout__in=['ada', 'bram']))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") IN (UPPER(%s), UPPER(%s))', ('ada', 'bram'))
tail(Sailor.objects.filter(name__shout__startswith='a'))  ->  ('FROM "crew_sailor" WHERE UPPER("crew_sailor"."name") LIKE REPLACE(REPLACE(REPLACE((UPPER(%s)), \'\\\', \'\\\\\'), \'%%\', \'\\%%\'), \'_\', \'\\_\') || \'%%\' ESCAPE \'\\\'', ('a',))
tail(Sailor.objects.filter(name__lower__shout__exact='ada'))  ->  ('FROM "crew_sailor" WHERE UPPER(LOWER("crew_sailor"."name")) = (UPPER(%s))', ('ada',))
Sailor.objects.filter(name__shout__in=Sailor.objects.values('name'))  ->  raises NotImplementedError: Bilateral transformations on nested querysets are not implemented.
entry(Sailor.objects.filter(name__shout='ada')).bilateral_transforms, entry(Sailor.objects.filter(name__shout='ada')).lhs.get_bilateral_transforms(), entry(Sailor.objects.filter(name__upper='ADA')).bilateral_transforms  ->  ([<class '__main__.Shout'>], [<class '__main__.Shout'>], [])
```

`Upper`, not bilateral, left the parameter `'ADA'` as it was; Shout wrote `"UPPER(%s)"` around it, around each member of the list, and around the pattern of `"startswith"`, which the lookup's escaping then wrapped in turn. The transforms under Shout were not applied to the right side: `"name__lower__shout__exact"` wrote the `"LOWER"` on the left alone.

### Which transforms a field class has at import

Registering a transform is `RegisterLookupMixin.register_lookup` on a field class, a single field or another transform, and chapter 9 has the registry. What matters here is which of Django's own transforms are registered when `django.db.models` is imported, since a word that is not finds nothing. The datetime module registers its classes as it is imported: the parts of a date on `DateField`, the parts of a time on `TimeField` and `DateTimeField`, the five year lookups on `ExtractYear` and `ExtractIsoYear`, and `TruncDate` and `TruncTime` on `DateTimeField`, which inherits `DateField`'s as well (`django/db/models/functions/datetime.py`). Of the text and the mathematical transforms none is registered on any field class at import: `Lower`, `Length` and `Upper` are classes with a `lookup_name`, and nothing more until something registers them (`django/db/models/functions/text.py:Lower`). `django.contrib.postgres` registers lookups and transforms of its own on `CharField` and `TextField` when its application is ready, and a project does the same.

```text recording=sql
Lower, Length and Upper registered on CharField for the rest of the recording: the text functions are transforms, but none is registered on a field class at import
    models.CharField.get_lookups().get('lower'), models.CharField.get_lookups().get('length')  ->  (None, None)
    models.CharField.register_lookup(Lower); models.CharField.register_lookup(Length); models.CharField.register_lookup(Upper)
    models.CharField.get_lookups().get('lower').__name__  ->  'Lower'
```

That line is why `"name__lower"` works in every block after it, and why `F('name__lower')` failed in a block before it.

## The comparison and conversion functions

`django/db/models/functions/comparison.py` holds the comparisons and the casts. `Cast` takes one expression and an output field, which is its type and its target: `Cast.as_sql` adds the field's `cast_db_type` to the template as `"db_type"`, and `Field.cast_db_type` is the backend's `cast_data_types` entry for the field's internal type, filled with the field's parameters, or the field's `db_type` where there is none; a `CharField` with no `max_length` answers, through `CharField.cast_db_type`, the backend's `cast_char_field_without_max_length` (`django/db/models/functions/comparison.py:Cast`, `django/db/models/fields/__init__.py:Field.cast_db_type`, `django/db/models/fields/__init__.py:CharField.cast_db_type`). `Cast.as_sqlite` writes a datetime or a time as a call of `"strftime"` with a format, since SQLite's cast to those types keeps no fractional seconds, and a date as `"date(...)"`; `Cast.as_postgresql` writes the `::` form; `Cast.as_mysql` adds `0.0` for a float, which MySQL cannot cast to, and uses `"JSON_EXTRACT"` for JSON on MariaDB; `Cast.as_oracle` uses `"JSON_QUERY"` for JSON.

`Coalesce` takes two expressions at least, refusing fewer with `ValueError`, and is `"COALESCE"` everywhere, with the arguments converted to `NCLOB` on Oracle where the output is text or JSON; its `empty_result_set_value` is the first source's that is not `None`, `NotImplemented` counted, so that a `Coalesce` over an aggregate that has one can answer for no rows ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](aggregates.md)). `Greatest` and `Least` take two at least and are `"GREATEST"` and `"LEAST"`, or `"MAX"` and `"MIN"` on SQLite; their docstrings say that a null among the arguments gives the greatest or least of the others on PostgreSQL and null on MySQL, Oracle and SQLite. `NullIf` takes exactly two, and on Oracle refuses a `Value(None)` as the first. `Collate` takes an expression and a collation's name, which it checks against a pattern of word characters and hyphens, and writes `expression COLLATE name`, the name quoted by the backend; it is not allowed as a database default (`django/db/models/functions/comparison.py:Collate`).

```text recording=sql
list(Ship.objects.annotate(x=Coalesce('captain__name', Value('nobody'))).values_list('x', flat=True))  ->  ['Cora', 'nobody']
  SQL SELECT COALESCE("crew_sailor"."name", %s) AS "x" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") ORDER BY "fleet_ship"."name" ASC with params ('nobody',)
list(Ship.objects.annotate(x=Cast('tonnage', models.FloatField()) / 1000).values_list('x', flat=True))  ->  [1.2, 0.48]
  SQL SELECT (CAST("fleet_ship"."tonnage" AS real) / %s) AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC with params (1000,)
list(Ship.objects.annotate(x=Round(Cast('tonnage', models.FloatField()) / 7, 2)).values_list('x', flat=True))  ->  [171.43, 68.57]
  SQL SELECT ROUND((CAST("fleet_ship"."tonnage" AS real) / %s), %s) AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC with params (7, 2)
```

## The datetime functions: `Extract` and `TruncBase`

An `Extract` is a transform that takes one part of a date, a time or a datetime, as an integer; a `TruncBase` is one that cuts a datetime down to a part, keeping its type or taking a narrower one. Neither writes SQL of its own: each compiles its argument and hands the SQL to a method of the backend's operations, `Extract` choosing the method by the argument's field and `TruncBase` by its output field, and the backend writes the function it has for that (`django/db/models/functions/datetime.py:Extract`, `django/db/models/functions/datetime.py:TruncBase`).

Both have `TimezoneMixin` among their bases, which holds a `tzinfo` and answers `TimezoneMixin.get_tzname`: `None` where `settings.USE_TZ` is off, the name of the current time zone where no `tzinfo` was given, and the name of the given one otherwise (`django/db/models/functions/datetime.py:TimezoneMixin.get_tzname`). A comment at the method says why the name is passed to the database: the conversion to that time zone has to happen before the part is taken, since a moment stored in UTC can fall on another day in the zone the program thinks in. On SQLite the operations pass two names, the one asked for and the connection's own `timezone_name`, and `None` for both where there is no name to pass, as parameters of the functions `"django_datetime_extract"`, `"django_datetime_trunc"` and their relatives, which Django registers with the connection (`django/db/backends/sqlite3/operations.py:DatabaseOperations.datetime_extract_sql`).

`Extract` takes the part's name from the class, `ExtractYear` has `"year"`, or as an argument of the plain class, refusing to go without one, and declares an `IntegerField` for its output (`django/db/models/fields/__init__.py:IntegerField`). `Extract.resolve_expression` checks the argument's field once it is resolved: it must be a `DateField`, `DateTimeField`, `TimeField` or `DurationField`, a time's part may not be taken from a `DateField`, and a calendar's part may not be taken from a `DurationField`, each a `ValueError`. `Extract.as_sql` then goes by the class of that field: a `DateTimeField` gives `datetime_extract_sql` with the time zone's name, a `DateField` `date_extract_sql`, a `TimeField` `time_extract_sql`, and a `DurationField` the same where the backend has a native duration type and `ValueError` where not; a `tzinfo` given for anything but a `DateTimeField` is refused there too (`django/db/models/functions/datetime.py:Extract.as_sql`, `django/db/backends/base/operations.py:BaseDatabaseOperations.datetime_extract_sql`).

```text recording=sql
list(Voyage.objects.annotate(x=ExtractYear('sailed')).values_list('x', flat=True))  ->  [2026, 2025]
  SQL SELECT django_date_extract(%s, "fleet_voyage"."sailed") AS "x" FROM "fleet_voyage" with params ('year',)
list(Voyage.objects.annotate(x=Extract('sailed', 'month')).values_list('x', flat=True))  ->  [3, 10]
  SQL SELECT django_date_extract(%s, "fleet_voyage"."sailed") AS "x" FROM "fleet_voyage" with params ('month',)
list(Sailor.objects.annotate(x=ExtractHour('signed_on')).values_list('x', flat=True))  ->  [8, 9, 8, 9]
  SQL SELECT django_datetime_extract(%s, "crew_sailor"."signed_on", %s, %s) AS "x" FROM "crew_sailor" with params ('hour', 'UTC', 'UTC')
list(Sailor.objects.annotate(x=ExtractHour('signed_on', tzinfo=datetime.timezone(datetime.timedelta(hours=2)))).values_list('x', flat=True))  ->  [10, 11, 10, 11]
  SQL SELECT django_datetime_extract(%s, "crew_sailor"."signed_on", %s, %s) AS "x" FROM "crew_sailor" with params ('hour', 'UTC+02:00', 'UTC')
```

The date of a voyage went to `"django_date_extract"` with the part's name as a parameter, and the moment a sailor signed on to `"django_datetime_extract"` with two names after it; given a zone two hours east, the hours came back two greater.

`TruncBase` carries `kind`, the part to cut to, on each of its subclasses, and takes an `output_field` and a `tzinfo` (`django/db/models/functions/datetime.py:TruncBase`). `TruncBase.resolve_expression` requires the argument's field to be a `DateField` or `TimeField`, a `DateTimeField` being the first, and the output field to be one of the three; where none was given the base inference makes the output field the argument's own, a comment saying so. Then it refuses what cannot be: a `DateField` cut to a `DateTimeField` or to a time's part, and a `TimeField` cut to a `DateTimeField` or to a calendar's part. `TruncBase.as_sql` takes the time zone's name where the argument is a `DateTimeField`, refuses a `tzinfo` where it is not, and chooses the backend's method by the output field this time: `datetime_trunc_sql`, `date_trunc_sql` or `time_trunc_sql`. The value that comes back goes through `TruncBase.convert_value`, which is the backend's `convert_trunc_expression`: a datetime is made aware in the expression's `tzinfo`, or the current time zone where none was given, where `USE_TZ` is on, and a datetime that came back for a date or a time output is cut to that (`django/db/backends/base/operations.py:BaseDatabaseOperations.convert_trunc_expression`).

`Trunc` is the plain class, with the kind given as an argument. `TruncYear`, `TruncQuarter`, `TruncMonth`, `TruncWeek`, `TruncDay`, `TruncHour`, `TruncMinute` and `TruncSecond` each fix the kind. `TruncDate` and `TruncTime` are the two with a `lookup_name`, `"date"` and `"time"`, and an output field of their own, and each overrides `as_sql` to ask for a cast rather than a truncation, `datetime_cast_date_sql` and `datetime_cast_time_sql`, a comment saying so (`django/db/models/functions/datetime.py:TruncDate`).

```text recording=sql
list(Voyage.objects.annotate(x=TruncMonth('sailed')).values_list('x', flat=True))  ->  [datetime.date(2026, 3, 1), datetime.date(2025, 10, 1)]
  SQL SELECT django_date_trunc(%s, "fleet_voyage"."sailed", %s, %s) AS "x" FROM "fleet_voyage" with params ('month', None, None)
list(Sailor.objects.annotate(x=TruncMonth('signed_on')).values_list('x', flat=True))  ->  [datetime.datetime(2011, 6, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), datetime.datetime(2026, 4, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), datetime.datetime(2011, 6, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')), datetime.datetime(2026, 4, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC'))]
  SQL SELECT django_datetime_trunc(%s, "crew_sailor"."signed_on", %s, %s) AS "x" FROM "crew_sailor" with params ('month', 'UTC', 'UTC')
list(Sailor.objects.annotate(x=TruncDate('signed_on')).values_list('x', flat=True))  ->  [datetime.date(2011, 6, 1), datetime.date(2026, 4, 10), datetime.date(2011, 6, 1), datetime.date(2026, 4, 10)]
  SQL SELECT django_datetime_cast_date("crew_sailor"."signed_on", %s, %s) AS "x" FROM "crew_sailor" with params ('UTC', 'UTC')
list(Sailor.objects.annotate(x=Trunc('signed_on', 'year', output_field=models.DateField())).values_list('x', flat=True))  ->  [datetime.date(2011, 1, 1), datetime.date(2026, 1, 1), datetime.date(2011, 1, 1), datetime.date(2026, 1, 1)]
  SQL SELECT django_date_trunc(%s, "crew_sailor"."signed_on", %s, %s) AS "x" FROM "crew_sailor" with params ('year', 'UTC', 'UTC')
```

The month of a date went to `"django_date_trunc"` with no time zone, since the argument is a `DateField`, and came back a date; the month of a datetime to `"django_datetime_trunc"` with the two names, and came back aware in UTC; `TruncDate` to the cast; and a `Trunc` of a datetime with a `DateField` for its output to the date function, with the names, since the argument is a datetime and the output a date.

```text recording=sql
Voyage.objects.annotate(x=Extract('sailed', 'hour'))  ->  raises ValueError: Cannot extract time component 'hour' from DateField 'sailed'.
Voyage.objects.annotate(x=Trunc('sailed', 'hour'))  ->  raises ValueError: Cannot truncate DateField 'sailed' to DateTimeField.
Voyage.objects.annotate(x=ExtractYear('ship'))  ->  raises ValueError: Extract input expression must be DateField, DateTimeField, TimeField, or DurationField.
Voyage.objects.annotate(x=ExtractYear('sailed', tzinfo=datetime.UTC))  ->  raises ValueError: tzinfo can only be used with DateTimeField.
type(TruncMonth('sailed').resolve_expression(Voyage.objects.all().query).output_field).__name__, type(TruncMonth('signed_on').resolve_expression(Sailor.objects.all().query).output_field).__name__, type(ExtractYear('sailed').output_field).__name__  ->  ('DateField', 'DateTimeField', 'IntegerField')
ExtractYear('signed_on').get_tzname(), ExtractYear('signed_on', tzinfo=datetime.timezone(datetime.timedelta(hours=2))).get_tzname()  ->  ('UTC', 'UTC+02:00')
```

The first three refusals came as the annotation was resolved; the fourth, of a `tzinfo` on a date, came as the statement was written. `Now` is a `Func` with no arguments whose template is `"CURRENT_TIMESTAMP"` and whose output is a `DateTimeField`, with a template of its own for each of the four backends: `"STATEMENT_TIMESTAMP()"` on PostgreSQL, where a comment says `"CURRENT_TIMESTAMP"` is the start of the transaction, `"CURRENT_TIMESTAMP(6)"` on MySQL, `"STRFTIME"` of the moment on SQLite, and `"LOCALTIMESTAMP"` on Oracle (`django/db/models/functions/datetime.py:Now`).

> **Deprecated.** Writing an `Extract` or a `Trunc` into a migration without a `tzinfo`, as a `db_default` is, while `USE_TZ` is on, warns with `RemovedInDjango2029Warning` from `TimezoneMixin.deconstruct`: the time zone is not captured in the migration, and a change of `TIME_ZONE` would change what the column means. In Django 2029 the current time zone will be captured when `tzinfo` is omitted (`django/db/models/functions/datetime.py:TimezoneMixin.deconstruct`, `docs/releases/6.2.txt`).

## The text functions

`django/db/models/functions/text.py` holds the functions over strings, most of them transforms (`django/db/models/functions/text.py:Length`). `Concat` is the one that writes no function of its own: `Concat.__init__` takes two expressions at least and pairs them from the right, `ConcatPair(a, ConcatPair(b, c))`, since, the docstring of `ConcatPair` says, not every backend takes more than two arguments, and its template is the pair alone (`django/db/models/functions/text.py:Concat`). `ConcatPair` is `"CONCAT"`; on SQLite and PostgreSQL it is written as the two sides joined by `||`, each wrapped in a `Coalesce` with the empty string, since a null on either side would make the whole null, and on PostgreSQL a side that is not a `CharField` or `TextField` is cast to text first; on MySQL it is `"CONCAT_WS"` with an empty separator, which ignores nulls of itself (`django/db/models/functions/text.py:ConcatPair`).

```text recording=sql
list(Ship.objects.annotate(x=Lower('name')).values_list('x', flat=True))  ->  ['gannet', 'petrel']
  SQL SELECT LOWER("fleet_ship"."name") AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
list(Ship.objects.annotate(x=Length('name')).values_list('x', flat=True))  ->  [6, 6]
  SQL SELECT LENGTH("fleet_ship"."name") AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
list(Ship.objects.annotate(x=Concat('name', Value(' of '), 'home__name')).values_list('x', flat=True))  ->  ['Gannet of Leith', 'Petrel of Bergen']
  SQL SELECT (COALESCE("fleet_ship"."name", %s) || COALESCE((COALESCE(%s, %s) || COALESCE("fleet_port"."name", %s)), %s)) AS "x" FROM "fleet_ship" INNER JOIN "fleet_port" ON ("fleet_ship"."home_id" = "fleet_port"."id") ORDER BY "fleet_ship"."name" ASC with params ('', ' of ', '', '', '')
list(Ship.objects.annotate(x=Substr('name', 2, 3)).values_list('x', flat=True))  ->  ['ann', 'etr']
  SQL SELECT SUBSTR("fleet_ship"."name", %s, %s) AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC with params (2, 3)
```

`Substr` takes an expression, a position counted from one, refusing a smaller plain number, and a length; `Left` and `Right` take an expression and a length, and on SQLite and Oracle each turns itself into a `Substr`, `Right` with a negative position (`django/db/models/functions/text.py:Substr`, `django/db/models/functions/text.py:Right`). The hashes are transforms whose function is the hash's name, with three mixins for the backends that spell it otherwise: `MySQLSHA2Mixin` writes `"SHA2"` with the bit length, `OracleHashMixin` a `"STANDARD_HASH"` of the raw bytes, and `PostgreSQLSHAMixin` an `"ENCODE"` of `"DIGEST"`; `SHA224` is refused on Oracle (`django/db/models/functions/text.py:MySQLSHA2Mixin`).

| class | function | output field | a transform under |
|---|---|---|---|
| `Chr` | `"CHR"`; `"CHAR"` on SQLite and MySQL | `CharField` | `"chr"` |
| `Concat` | none: a chain of `ConcatPair` | inferred, or as given | no |
| `ConcatPair` | `"CONCAT"`; `\|\|` on SQLite and PostgreSQL; `"CONCAT_WS"` on MySQL | inferred, or as given | no |
| `Left` | `"LEFT"`; a `Substr` on SQLite and Oracle | `CharField` | no |
| `Length` | `"LENGTH"`; `"CHAR_LENGTH"` on MySQL | `IntegerField` | `"length"` |
| `Lower` | `"LOWER"` | the argument's | `"lower"` |
| `LPad`, `RPad` | `"LPAD"`, `"RPAD"` | `CharField` | no |
| `LTrim`, `RTrim`, `Trim` | `"LTRIM"`, `"RTRIM"`, `"TRIM"` | the argument's | `"ltrim"`, `"rtrim"`, `"trim"` |
| `MD5` | `"MD5"`; `"STANDARD_HASH"` on Oracle | the argument's | `"md5"` |
| `Ord` | `"ASCII"`; `"ORD"` on MySQL, `"UNICODE"` on SQLite | `IntegerField` | `"ord"` |
| `Repeat` | `"REPEAT"`; an `RPad` on Oracle | `CharField` | no |
| `Replace` | `"REPLACE"` | the argument's | no |
| `Reverse` | `"REVERSE"`; a subquery on Oracle | the argument's | `"reverse"` |
| `Right` | `"RIGHT"`; a `Substr` on SQLite and Oracle | `CharField` | no |
| `SHA1` | `"SHA1"`; `"DIGEST"` on PostgreSQL, `"STANDARD_HASH"` on Oracle | the argument's | `"sha1"` |
| `SHA224` | `"SHA224"`; `"SHA2"` on MySQL, `"DIGEST"` on PostgreSQL; refused on Oracle | the argument's | `"sha224"` |
| `SHA256`, `SHA384`, `SHA512` | the name; `"SHA2"` on MySQL, `"DIGEST"` on PostgreSQL, `"STANDARD_HASH"` on Oracle | the argument's | `"sha256"`, `"sha384"`, `"sha512"` |
| `StrIndex` | `"INSTR"`; `"STRPOS"` on PostgreSQL | `IntegerField` | no |
| `Substr` | `"SUBSTRING"`; `"SUBSTR"` on SQLite and Oracle | `CharField` | no |
| `Upper` | `"UPPER"` | the argument's | `"upper"` |

*The classes of `django/db/models/functions/text.py`: the function each writes and where a backend writes another, its output field, and the word it is a transform under, which no field class registers at import. "The argument's" is the base inference: the output field of the sources, which for a transform is the one argument.*

## The mathematical functions

`django/db/models/functions/math.py` holds the mathematical functions, every one of them a `Transform` but those that take two arguments or none, and most of them with `NumericOutputFieldMixin` for their type (`django/db/models/functions/math.py:Round`). `Round` is a transform that takes a precision as a second argument, setting `arity` back to `None` for it, with a comment saying so; its output is the argument's own, and on SQLite a negative precision is refused. `Random` takes no argument, writes `"RANDOM"`, `"RAND"` on MySQL and on SQLite, where it is a function Django registers with the connection because, a comment there says, SQLite's own `"RANDOM"` returns a 64-bit integer and not a value from zero to one (`django/db/backends/sqlite3/_functions.py`), and `"DBMS_RANDOM.VALUE"` on Oracle, and contributes nothing to a `"GROUP BY"` (`django/db/models/functions/math.py:Random`). `Log` swaps its two arguments on SpatiaLite, and `ATan2` on SpatiaLite before 5.0.0, whose functions take them the other way round, and `ATan2` casts an integer argument to a float there.

| class | function | output field | arguments |
|---|---|---|---|
| `Abs`, `Floor`, `Sign` | `"ABS"`, `"FLOOR"`, `"SIGN"` | the argument's | one, a transform |
| `Ceil` | `"CEILING"`; `"CEIL"` on Oracle | the argument's | one, a transform |
| `Round` | `"ROUND"` | the argument's | one and a precision, a transform |
| `ACos`, `ASin`, `ATan`, `Cos`, `Exp`, `Ln`, `Sin`, `Sqrt`, `Tan` | the name in capitals | numeric | one, a transform |
| `Cot` | `"COT"`; `1 / TAN` on Oracle | numeric | one, a transform |
| `Degrees`, `Radians` | `"DEGREES"`, `"RADIANS"`; arithmetic with pi on Oracle | numeric | one, a transform |
| `ATan2` | `"ATAN2"`; the arguments swapped on SpatiaLite before 5 | numeric | two |
| `Log` | `"LOG"`; the arguments swapped on SpatiaLite | numeric | two, floats cast on PostgreSQL |
| `Mod` | `"MOD"` | numeric | two, floats cast on PostgreSQL |
| `Power` | `"POWER"` | numeric | two |
| `Pi` | `"PI"`; the number written out on Oracle | numeric, so `FloatField` | none |
| `Random` | `"RANDOM"`; `"RAND"` on MySQL and SQLite, `"DBMS_RANDOM.VALUE"` on Oracle | `FloatField` | none |

*The classes of `django/db/models/functions/math.py`. "Numeric" is `NumericOutputFieldMixin`: a `DecimalField` (`django/db/models/fields/__init__.py:DecimalField`) where any argument is one, a `FloatField` where any is an `IntegerField`, and `FloatField` for no arguments. Each transform's word is its class's name in lower case.*

## JSON, UUIDs and the window functions

`JSONObject` and `JSONArray` build a JSON value, with a `JSONField` for their output (`django/db/models/functions/json.py:JSONObject`, `django/db/models/fields/json.py:JSONField`). `JSONObject.__init__` takes keyword arguments and lays them out as alternating sources, each key as a `Value` before its value, and its `as_sql` refuses with `NotSupportedError` where the backend's features lack `has_json_object_function`. On PostgreSQL and Oracle it writes the native form with a `"RETURNING"` type, `"JSONB"` or `"CLOB"`, and for that it joins the sources through `JSONObject.join`, pairing them as `"(key) VALUE value"`: the object itself is passed as the `arg_joiner`, and `Func.as_sql` calls its `join`, which shows that a joiner is anything with a `join` method, not only a string. `JSONArray` writes `"JSON_ARRAY"`, refusing where `supports_json_field` is off, and on PostgreSQL and Oracle adds `"NULL ON NULL"` so that a null among the values is kept as a JSON null, as SQLite keeps it.

`UUID4` and `UUID7` are functions of no argument with a `UUIDField` for their output, `"UUIDV4"` and `"UUIDV7"` (`django/db/models/functions/uuid.py:UUID4`, `django/db/models/functions/uuid.py:UUID7`). Each refuses with `NotSupportedError` where the backend's features lack `supports_uuid4_function` or `supports_uuid7_function`, and each has a vendor method with the backend's own name for the function, or its own refusal naming the version wanted; `UUID7` takes a shift as an optional argument, dropped from the sources when it is `None` by `UUID7._parse_expressions`, and refused where `supports_uuid7_function_shift` is off. On SQLite both are functions Django registers with the connection, `"UUIDV7"` only on Python 3.14 and later, which is what SQLite's `supports_uuid7_function` tests.

```text recording=sql
[type(v).__name__ for v in Ship.objects.annotate(x=UUID4()).values_list('x', flat=True)]  ->  ['UUID', 'UUID']
  SQL SELECT UUIDV4() AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
list(Ship.objects.annotate(x=UUID7()).values_list('x', flat=True))[0].version  ->  7
  SQL SELECT UUIDV7() AS "x" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC
```

> **Changed in 6.1.** `UUID4` and `UUID7` are new in 6.1 (`docs/releases/6.1.txt`).

The window functions of `django/db/models/functions/window.py` are `Func` subclasses with `window_compatible` set and nothing else that a function needs: `CumeDist`, `DenseRank`, `FirstValue`, `Lag`, `LastValue`, `Lead`, `NthValue`, `Ntile`, `PercentRank`, `Rank` and `RowNumber`. Each is given to a `Window`, which writes the `"OVER"` clause, and [Window expressions: `Window`, `WindowFrame` and the QUALIFY rewrite](windows.md) has what each writes and what the two with an offset and a default check (`django/db/models/functions/window.py:LagLeadFunction`).
