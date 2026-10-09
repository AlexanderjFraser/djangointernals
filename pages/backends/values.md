---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Values in and out: adapters, converters and time zones

A value crosses between Python and a database twice: into a statement as a parameter, and back out of a row. With `USE_TZ` on, `BaseDatabaseWrapper.timezone` says which time zone a datetime stored without one is in.

A field holds a Python object, and the databases do not agree on how to keep one. SQLite keeps a datetime as text; PostgreSQL has types of its own for a UUID, an interval and a datetime with its time zone; MySQL and Oracle keep a datetime without a time zone and a boolean as a number. What a field needs is the same on every backend: the value it hands down comes back as the same Python value.

The work is divided by what each party knows. The field knows the Python type; the **operations object**, which a connection keeps as `BaseDatabaseWrapper.ops`, knows the backend; the **driver** knows the database. On the way in, a field class's override of `Field.get_db_prep_value` gives the value to the operations object's **adapter** for its kind, `adapt_datetimefield_value` for a datetime, which returns what this backend's driver should be handed, and the driver turns that into what it binds (`django/db/models/fields/__init__.py:DateTimeField.get_db_prep_value`). On the way out the driver converts first, as it fetches the rows, and then the compiler applies to each column the **converters** the operations object names for it, followed by the field's own. What each backend does on either side depends on what its database keeps and what its driver does: PostgreSQL's operations object names no converter for any column, and SQLite's names them for datetimes, dates, times, decimals, UUIDs and booleans.

```text figure=a-value-both-ways
One DateTimeField value on SQLite, a sailor's signed_on, into an UPDATE and back out of a SELECT.

                 THE WAY IN, read downwards                        THE WAY OUT, read upwards

the field        DateTimeField.get_db_prep_value                   from_db_value, where the field has one: none here
                 an aware datetime, 18:30 in Oslo                  an aware datetime, 17:30 UTC

the operations   adapt_datetimefield_value: the value made         get_db_converters names convert_datetimefield_value,
object           naive in the connection's time zone (UTC),        which makes the value aware in the connection's time zone;
                 and written as text                               SQLCompiler.apply_converters calls it, and then the field's

the driver       binds the text as it is; the adapters Django      calls the converter Django registered for the column's
(sqlite3)        registered with it are for a date, a datetime     declared type, "datetime": parse_datetime, which makes
                 or a Decimal that reaches it as one               a naive datetime

the database     stores the text  2026-03-14 17:30:00              returns the text
```

*A value's two paths through the same four layers on SQLite, as recorded for one sailor. Going in, the field and the operations object do the work and the driver binds a string; coming out, the driver parses first and the backend's converter supplies the time zone.*

## A datetime on its way in

A datetime goes into a statement through `DateTimeField.get_db_prep_value`, which prepares the value, unless told it is prepared, and returns what the operations object's `adapt_datetimefield_value` makes of it (`django/db/models/fields/__init__.py:DateTimeField.get_db_prep_value`); what comes before that is [A field: the base class](../models/fields.md)'s.

In the recordings on this page, made on SQLite with `USE_TZ` on, a line at the left margin is Python as it ran, with the calls it set going that the passage is about nested under it as they were made, and `->` before what a line or a call returned; a line `SQL` is a statement as Django handed it to its cursor, and a line that begins sqlite the statement as SQLite ran it. Bram, a sailor of the crew, is given a new time of signing on, an aware datetime in Oslo's time zone, and saved:

```text recording=backends
bram.signed_on = datetime.datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))
bram.save(update_fields=['signed_on'])
  DateTimeField.get_db_prep_value(datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo')), prepared=False)
    DatabaseOperations.adapt_datetimefield_value(datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo')))
      make_naive(datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo')), datetime.timezone.utc)  ->  datetime(2026, 3, 14, 17, 30)
      -> '2026-03-14 17:30:00'
  SQL UPDATE "crew_sailor" SET "signed_on" = %s WHERE "crew_sailor"."id" = %s with params ('2026-03-14 17:30:00', 2)
  sqlite UPDATE "crew_sailor" SET "signed_on" = '2026-03-14 17:30:00' WHERE "crew_sailor"."id" = 2
```

SQLite's adapter makes an aware datetime naive in the connection's time zone, here UTC, so that 18:30 in Oslo became 17:30, and returns `str` of it, which the driver binds and SQLite stores (`django/db/backends/sqlite3/operations.py:DatabaseOperations.adapt_datetimefield_value`). The text in the column carries no time zone. That it is UTC is known only to the connection's `BaseDatabaseWrapper.timezone`, and the way out depends on it.

## The operations object's adapters

`BaseDatabaseOperations` has an adapter for a date, a time, a datetime, a duration, a decimal, an integer, an IP address and a JSON value, and the field class of that kind calls it from its override of `Field.get_db_prep_value`, as `DateField` does (`django/db/models/fields/__init__.py:DateField.get_db_prep_value`, `django/db/backends/base/operations.py:BaseDatabaseOperations.adapt_datefield_value`). The base class's adapters are the plain case: a date, a time and a datetime become `str` of the value, an aware time being refused; a duration becomes its whole number of microseconds; an integer passes as it is; an empty IP address becomes `None`; a JSON value becomes `json.dumps` of it with the field's encoder. `BaseDatabaseOperations.adapt_decimalfield_value` is handed the field's digits and places with the value and returns the value, and no backend overrides it (`django/db/models/fields/__init__.py:DecimalField.get_db_prep_value`). Where a driver wants something other than the plain case, its backend overrides the adapter:

| kind of value | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| a datetime | made naive in the connection's time zone; a string | the value | made naive in the connection's time zone; a string | made naive in the connection's time zone; an `Oracle_datetime` |
| a date | the base's: a string | the value | the base's: a string | the value |
| a time | a string; an aware time refused | the value | a string to the microsecond; an aware time refused | an `Oracle_datetime` on 1 January 1900; an aware time refused |
| a duration | the base's: microseconds | the value | the base's: microseconds | the value |
| an integer | the base's: the value | under psycopg 3, the value in psycopg's integer type of the field's size | the base's: the value | the base's: the value |
| an IP address | the base's | under psycopg 3 an address object of `ipaddress`, under psycopg2 the value in psycopg2's wrapper; `None` for an empty value | the base's | the base's |
| a JSON value | the base's: `json.dumps` | the value in a wrapper for JSONB, psycopg's or, under psycopg2, Django's own, dumped with the field's encoder | the base's: `json.dumps` | the base's: `json.dumps` |

*The adapters that differ between the backends, a row for each: `BaseDatabaseOperations.adapt_datetimefield_value`, `BaseDatabaseOperations.adapt_datefield_value`, `BaseDatabaseOperations.adapt_timefield_value`, `BaseDatabaseOperations.adapt_durationfield_value`, `BaseDatabaseOperations.adapt_integerfield_value`, `BaseDatabaseOperations.adapt_ipaddressfield_value` and `BaseDatabaseOperations.adapt_json_value`. "The base's" is inherited from `BaseDatabaseOperations`, and a refusal is a `ValueError`. With `USE_TZ` off, the three adapters that make a datetime naive refuse an aware one instead.*

`UUIDField.get_db_prep_value` uses no adapter: where `BaseDatabaseFeatures.has_native_uuid_field` is true, as on PostgreSQL and MariaDB, it hands down the `uuid.UUID`, and elsewhere the string of its 32 hexadecimal digits (`django/db/models/fields/__init__.py:UUIDField.get_db_prep_value`). `BinaryField.get_db_prep_value` wraps its bytes in the driver's constructor Binary, which [PEP 249](https://peps.python.org/pep-0249/) has every driver provide.

An automatic key passes through no adapter, but on a save it passes through `BaseDatabaseOperations.validate_autopk_value`, called from `AutoFieldMixin.get_db_prep_save`: the base class's returns the value, and MySQL's refuses 0 unless the server's SQL mode allows it, as [MySQL and MariaDB](mysql.md) tells (`django/db/backends/base/operations.py:BaseDatabaseOperations.validate_autopk_value`).

For a value with no field behind it there is `BaseDatabaseOperations.adapt_unknown_value`, which goes by the value's type alone: a datetime, tested before a date since it is one, a date, a time and a decimal each to its adapter, and anything else back as it is (`django/db/backends/base/operations.py:BaseDatabaseOperations.adapt_unknown_value`). Its one caller is the `RawQuery` behind `QuerySet.raw`, which passes each of its parameters through it, since the type each is meant for is not known (`django/db/models/sql/query.py:RawQuery._execute_query`); a datetime given to a raw query reaches the adapter a field's would:

```text recording=backends
signed = list(Sailor.objects.raw('SELECT id, name FROM crew_sailor WHERE signed_on > %s ORDER BY id', [datetime.datetime(2026, 1, 1, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))]))
  RawQuery._execute_query
    BaseDatabaseOperations.adapt_unknown_value(datetime(2026, 1, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo')))
      DatabaseOperations.adapt_datetimefield_value(datetime(2026, 1, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo')))
```

## What the driver does with a parameter

SQLite's backend registers adapters with the driver, through `sqlite3.register_adapter`, as `django.db.backends.sqlite3.base` is imported: `str` for a `decimal.Decimal`, `adapt_date` for a `datetime.date`, which writes its ISO form, and `adapt_datetime` for a `datetime.datetime`, which writes the ISO form with a space before the time (`django/db/backends/sqlite3/base.py`). They are registered on the module `sqlite3`, not on a connection. A field's datetime never reaches them, being a string already; one handed to Django's cursor does, for on SQLite that cursor passes it on unchanged:

```text recording=backends
with connection.cursor() as cursor: cursor.execute('SELECT %s', [datetime.datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo('Europe/Oslo'))]); row = cursor.fetchone()
  SQL SELECT %s with params [datetime.datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo'))]
  adapt_datetime(datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo')))  ->  '2026-03-14 18:30:00+01:00'
```

`adapt_datetime` knows nothing of time zones: it wrote the value with its offset, where the operations object's adapter would have made it naive in the connection's zone.

PostgreSQL's operations object hands dates, times, datetimes and durations down as they are, for psycopg to bind. Oracle's cursor, beneath Django's, wraps each parameter in an `OracleParam`, which with `USE_TZ` on makes a datetime an `Oracle_datetime`, a class whose docstring says it tells the driver to save the microseconds too, and which turns `True` and `False` into 1 and 0 on a server older than 23 (`django/db/backends/oracle/base.py:OracleParam`); [Oracle](oracle.md) has the cursor.

## A datetime on its way out

A datetime column Django made comes back from SQLite through two conversions, the driver's and the backend's; Bram's time of signing on, read back:

```text recording=backends
signed_on = Sailor.objects.values_list('signed_on', flat=True).get(name='Bram')
  SQL SELECT "crew_sailor"."signed_on" AS "signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s LIMIT 21 with params ('Bram',)
  sqlite3.Cursor.fetchmany
    decoder(parse_datetime)'s lambda(b'2026-03-14 17:30:00')
      parse_datetime('2026-03-14 17:30:00')  ->  datetime(2026, 3, 14, 17, 30)
  sqlite3.Cursor.fetchmany
  SQLCompiler.get_converters
    DatabaseOperations.get_db_converters(Col(crew_sailor, crew.Sailor.signed_on))  ->  [DatabaseOperations.convert_datetimefield_value]
    Field.get_db_converters
    -> {0: [DatabaseOperations.convert_datetimefield_value]}
  SQLCompiler.apply_converters
    DatabaseOperations.convert_datetimefield_value(datetime(2026, 3, 14, 17, 30))
      make_aware(datetime(2026, 3, 14, 17, 30), datetime.timezone.utc)  ->  datetime(2026, 3, 14, 17, 30, tzinfo=UTC)
      -> datetime(2026, 3, 14, 17, 30, tzinfo=UTC)
  SQLCompiler.apply_converters resumes
```

The first conversion is the driver's, inside `sqlite3.Cursor.fetchmany`. SQLite's backend opens each connection with `"detect_types"` set to `sqlite3.PARSE_DECLTYPES` and `sqlite3.PARSE_COLNAMES` unless the alias's `"OPTIONS"` give another value (`django/db/backends/sqlite3/base.py:DatabaseWrapper.get_connection_params`); with them, the driver calls the converter registered under the name of the type each column was declared with, with the column's raw bytes. The backend registers converters with `sqlite3.register_converter` as its module is imported: the method `__eq__` of `b"1"` under `"bool"`, true for those bytes and false for any others, and under `"date"`, `"time"`, `"datetime"` and `"timestamp"` a `decoder` around one of Django's parsers, which decodes the bytes to a string first (`django/db/backends/sqlite3/base.py:decoder`). The first four names are the types SQLite's `DatabaseWrapper.data_types` writes for a boolean, a date, a time and a datetime field ([Column types: from a field to a column](column-types.md)), so a column Django made for one of those four comes back parsed.

A column with no declared type, such as a function's, is not converted by the driver, and comes back as SQLite stores it: a datetime as text, a boolean as an integer. SQLite's converters take values of both kinds: `DatabaseOperations.convert_datetimefield_value` parses a value that is not yet a datetime and leaves one the driver parsed, and the converters for dates and times do the same (`django/db/backends/sqlite3/operations.py:DatabaseOperations.convert_datetimefield_value`).

The second conversion is the backend's. The compiler gathers, for each column, the operations object's converters and then the field's, and applies them to each row in that order; [The compiler: `as_sql`, `execute_sql` and `results_iter`](../sql/compiler.md) tells it. SQLite's `DatabaseOperations.get_db_converters` chooses by the internal type of the column's output field (`django/db/backends/sqlite3/operations.py:DatabaseOperations.get_db_converters`). Here it named `convert_datetimefield_value`, which with `USE_TZ` on made the value aware in the connection's zone and so gave back the instant that went in.

## Booleans, decimals and the other kinds of value

A boolean and a date read on SQLite, a Manifest's stamped and a Voyage's sailed:

```text recording=backends
stamped = Manifest.objects.values_list('stamped', flat=True).get()
...
  DatabaseOperations.convert_booleanfield_value(False)  ->  False
...
sailed = Voyage.objects.values_list('sailed', flat=True).get(pk=1)
  SQL SELECT "fleet_voyage"."sailed" AS "sailed" FROM "fleet_voyage" WHERE "fleet_voyage"."id" = %s LIMIT 21 with params (1,)
  decoder(parse_date)'s lambda(b'2026-03-02')
    parse_date('2026-03-02')  ->  date(2026, 3, 2)
  DatabaseOperations.convert_datefield_value(date(2026, 3, 2))  ->  date(2026, 3, 2)
```

The driver had made a `bool` and a `datetime.date` of the two columns, declared `"bool"` and `"date"`, before the backend's converters saw them. Those run all the same, and with no declared type a boolean reaches its converter as an integer: `DatabaseOperations.convert_booleanfield_value` makes `bool` of any value equal to 1 or 0, the driver's `False` among them (`django/db/backends/sqlite3/operations.py:DatabaseOperations.convert_booleanfield_value`).

A decimal takes the other road. Here one is given as a `Value` and selected:

```text recording=backends
rate = Ship.objects.annotate(rate=models.Value(Decimal('12.50'), output_field=models.DecimalField(max_digits=5, decimal_places=2))).values_list('rate', flat=True).first()
  SQL SELECT (CAST(%s AS REAL)) AS "rate" FROM "fleet_ship" ORDER BY "fleet_ship"."name" ASC LIMIT 1 with params (Decimal('12.50'),)
  DatabaseOperations.get_decimalfield_converter(Value(Decimal('12.50')))
  converter(12.5)  (the function get_decimalfield_converter made)
    DatabaseOperations._create_decimal(12.5)  ->  Decimal('12.5')
    -> Decimal('12.5')
```

`Value.as_sqlite` had cast the parameter to `"REAL"`, and the backend registers no converter with the driver for a decimal, so the driver returned a float (`django/db/models/expressions.py:Value.as_sqlite`). `DatabaseOperations.get_decimalfield_converter` makes a converter for each expression (`django/db/backends/sqlite3/operations.py:DatabaseOperations.get_decimalfield_converter`). For the column of a field with decimal places it quantizes to them in the field's context; for anything else, as here, it makes a decimal and leaves the places as they come. Either way it starts from `DatabaseOperations._create_decimal`, which makes a float a decimal through a context of 15 digits, the comment's reason being that SQLite stores only 15 significant digits and digits coming from float inaccuracy must be removed.

SQLite's `DatabaseOperations.convert_uuidfield_value` makes a `uuid.UUID` of the 32 hexadecimal digits (`django/db/backends/sqlite3/operations.py:DatabaseOperations.convert_uuidfield_value`). A duration's converter and a JSON value's are the field's. `DurationField.get_db_converters` adds `BaseDatabaseOperations.convert_durationfield_value`, which makes a `datetime.timedelta` of the microseconds, where the features lack `BaseDatabaseFeatures.has_native_duration_field` (`django/db/models/fields/__init__.py:DurationField.get_db_converters`); `JSONField.from_db_value` passes the text to `json.loads` with the field's decoder (`django/db/models/fields/json.py:JSONField.from_db_value`). The other backends divide the same work otherwise:

| kind of value | SQLite | PostgreSQL | MySQL | Oracle |
|---|---|---|---|---|
| a datetime | the driver, for a column declared `"datetime"` or `"timestamp"`; the backend's converter parses any other and, where `USE_TZ` is on, makes it aware | psycopg, with Django's loader for `"timestamptz"`, or under psycopg2 Django's time zone factory | the driver; the backend's converter makes it aware, where `USE_TZ` is on | the driver; the backend's converter makes it aware, where `USE_TZ` is on |
| a date | the driver, for `"date"`; the backend's converter for any other | psycopg | the driver | the driver gives a datetime, and the backend's converter takes its date |
| a time | the driver, for `"time"`; the backend's converter for any other | psycopg | `typecast_time`, in the driver's table | the driver gives a datetime, and the backend's converter takes its time |
| a boolean | the driver, for `"bool"`; the backend's converter for 1 and 0 | psycopg | the backend's converter, for 1 and 0 | the backend's converter, for 1 and 0 |
| a decimal | the backend's converter, from a float or an integer | psycopg | the driver | the cursor's output type handler |
| a UUID | the backend's converter, from 32 digits | psycopg | the backend's converter, from text | the backend's converter, from 32 digits |
| a duration | the field's converter, from microseconds | psycopg | the field's converter, from microseconds | the driver |
| JSON | the field's `from_db_value` | psycopg as text, then the field's | the field's | the backend's converter reads the LOB, then the field's |

*Who makes the Python value of each kind on the way out. "The backend's converter" is one that the operations object's `get_db_converters` names; "the field's" is one that the field's `get_db_converters` returns.*

Django's adapters map for psycopg 3 loads `"jsonb"` as text, the comment's reason being to avoid a round trip through `json.dumps` and `json.loads` when a `JSONField` has a decoder of its own, and `"inet"` and `"cidr"` as text rather than Python's address objects (`django/db/backends/postgresql/psycopg_any.py:get_adapters_template`); under psycopg2 the backend does the same for `"jsonb"` (`django/db/backends/postgresql/base.py:DatabaseWrapper.get_new_connection`). MySQL's `django_conversions` reads a TIME column with `typecast_time`, the comment saying that the driver returns one as a `datetime.timedelta`, those columns being signed and holding days, where Django expects a time (`django/db/backends/mysql/base.py:django_conversions`).

## Time zones


With `USE_TZ` on, Django's datetimes are aware, and a backend whose database keeps no time zone has to store them in one. That zone is `BaseDatabaseWrapper.timezone`: `datetime.UTC`, unless the alias's `"TIME_ZONE"` names a zone and then a `zoneinfo.ZoneInfo` of it, and `None` with `USE_TZ` off; its docstring says that a datetime read from the database is always returned in it (`django/db/backends/base/base.py:BaseDatabaseWrapper.timezone`). `BaseDatabaseWrapper.timezone_name` is its name, or the project's `TIME_ZONE` with `USE_TZ` off. Both are cached on the connection. The end of the block that read Bram's time back:

```text recording=backends
signed_on  ->  datetime(2026, 3, 14, 17, 30, tzinfo=UTC)
signed_on.tzinfo  ->  datetime.timezone.utc
timezone.localtime(signed_on)  ->  datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo'))
connection.timezone  ->  datetime.timezone.utc
connection.timezone_name  ->  'UTC'
connection.settings_dict['TIME_ZONE']  ->  None
```

The project's `TIME_ZONE`, Oslo's, is the default zone, the one `django.utils.timezone.localtime` moved the value into; the alias's, unset, is the zone of storage. Without `USE_TZ` neither property reads the alias's value, and `BaseDatabaseWrapper.check_settings`, the first step of `BaseDatabaseWrapper.connect`, refuses an alias's `"TIME_ZONE"` as the connection opens, before the driver's connection is made, here for an alias naming Oslo's (`django/db/backends/base/base.py:BaseDatabaseWrapper.check_settings`):

```text recording=backends
settings.USE_TZ = False
zoned = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'harbour.sqlite3', 'TIME_ZONE': 'Europe/Oslo'}})['default']
zoned.cursor()
...
        BaseDatabaseWrapper.connect
          BaseDatabaseWrapper.check_settings  raises ImproperlyConfigured
raises ImproperlyConfigured: Connection 'default' cannot set TIME_ZONE because USE_TZ is False.
zoned.connection is None  ->  True
```

### A database that stores no time zone

SQLite, MySQL and Oracle keep a datetime without a time zone, in `"datetime"`, `"datetime(6)"` and `"TIMESTAMP"` columns, and their features set `BaseDatabaseFeatures.supports_timezones` to false. Their adapters make an aware value naive in the connection's zone, and their `DatabaseOperations.convert_datetimefield_value` makes the naive value the driver returns aware in the same zone (`django/db/backends/mysql/operations.py:DatabaseOperations.convert_datetimefield_value`). MySQL's and Oracle's `DatabaseOperations.get_db_converters` name it only with `USE_TZ` on, and SQLite's checks the setting inside it (`django/db/backends/mysql/operations.py:DatabaseOperations.get_db_converters`). So on these backends the alias's `"TIME_ZONE"` changes what every stored datetime means, and the documentation says it must be set where the database holds local times that another system wrote or expects to find (`docs/ref/settings.txt`).

### PostgreSQL: the session's time zone, and Django's loader

PostgreSQL's `"timestamp with time zone"` stores an instant, and the server writes each value back in the session's time zone (`docs/topics/i18n/timezones.txt`). `DatabaseWrapper._configure_timezone` sets the session's zone to `timezone_name` where the server reports another, with the operations object's `DatabaseOperations.set_time_zone_sql` (`django/db/backends/postgresql/base.py:DatabaseWrapper._configure_timezone`, `django/db/backends/postgresql/operations.py:DatabaseOperations.set_time_zone_sql`). It runs as each connection opens, from `DatabaseWrapper.init_connection_state` or, where the alias has a pool, from the pool itself ([PostgreSQL](postgresql.md)).

Under psycopg 3 each connection's adapters map loads `"timestamptz"` with a subclass of `BaseTzLoader` that `register_tzloader` makes for the connection's `timezone`: it loads with psycopg's own loader and puts that zone on the value in place of the offset (`django/db/backends/postgresql/psycopg_any.py:BaseTzLoader`). With `USE_TZ` off the zone is `None`, which, the docstring says, chops the time zone, and the value is naive in the session's zone. `DatabaseWrapper.create_cursor` registers the loader again on a cursor where the connection's holds another zone; under psycopg2 it gives each cursor, with `USE_TZ` on, `DatabaseWrapper.tzinfo_factory`, which returns the connection's zone (`django/db/backends/postgresql/base.py:DatabaseWrapper.create_cursor`).

`BaseDatabaseWrapper.ensure_timezone`, whose one caller is the test framework's receiver of `setting_changed`, makes an open connection agree again after the settings change: the base class's does nothing, and PostgreSQL's closes the pool and runs `_configure_timezone` (`django/db/backends/postgresql/base.py:DatabaseWrapper.ensure_timezone`, `django/test/signals.py:update_connections_time_zone`).

### Time zones inside a statement

A filter on the month of a datetime, or a `Trunc` of one, is computed by the database in the time zone the function was given, or else the current one. Where the stored value is naive, the database has also to be told what zone it is in. SQLite's operations object gives Django's functions both names as parameters, the zone to compute in and the connection's (`django/db/backends/sqlite3/operations.py:DatabaseOperations._convert_tznames_to_sql`):

```text recording=backends
march = list(Sailor.objects.filter(signed_on__month=3))
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE django_datetime_extract(%s, "crew_sailor"."signed_on", %s, %s) = %s with params ('month', 'Europe/Oslo', 'UTC', 3)
...
    _sqlite_datetime_extract(lookup_type='month', dt='2026-03-14 17:30:00', tzname='Europe/Oslo', conn_tzname='UTC')
      _sqlite_datetime_parse(dt='2026-03-14 17:30:00', tzname='Europe/Oslo', conn_tzname='UTC')  ->  datetime(2026, 3, 14, 18, 30, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo'))
      -> 3
```

`_sqlite_datetime_parse` reads the stored text with `typecast_timestamp`, which keeps no time zone information, gives the result the connection's zone and moves it into the zone the SQL names, with `split_tzname_delta` for a name that carries an offset (`django/db/backends/sqlite3/_functions.py:_sqlite_datetime_parse`, `django/db/backends/utils.py:split_tzname_delta`). MySQL's operations object writes `"CONVERT_TZ"` from the connection's zone (`django/db/backends/mysql/operations.py:DatabaseOperations._convert_sql_to_tz`), which, the comment in `DatabaseWrapper.mysql_server_data` says, returns null where UTC is not loaded into the server's time zone table; the backend asks the server once whether UTC converts, and the features' `BaseDatabaseFeatures.has_zoneinfo_database` is the answer (`django/db/backends/mysql/base.py:DatabaseWrapper.mysql_server_data`). Oracle's operations object names the connection's zone in each conversion (`django/db/backends/oracle/operations.py:DatabaseOperations._convert_sql_to_tz`).

A truncated datetime has one more converter, after the backend's. A `Trunc` of Bram's time to the month comes back from SQLite as text, truncated in Oslo's time, and the backend's converter makes it aware in the connection's zone, UTC. `TruncBase.convert_value` then calls `BaseDatabaseOperations.convert_trunc_expression` (`django/db/models/functions/datetime.py:TruncBase.convert_value`), which, for a datetime output with `USE_TZ` on, drops that zone and makes the value aware in the zone the truncation was computed in, the `TruncBase.tzinfo` it was given or, where that is `None` as here, the current zone (`django/db/backends/base/operations.py:BaseDatabaseOperations.convert_trunc_expression`):

```text recording=backends
month = Sailor.objects.annotate(month=Trunc('signed_on', 'month')).values_list('month', flat=True).get(name='Bram')
  SQL SELECT django_datetime_trunc(%s, "crew_sailor"."signed_on", %s, %s) AS "month" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s LIMIT 21 with params ('month', 'Europe/Oslo', 'UTC', 'Bram')
  SQLCompiler.get_converters  ->  {0: [DatabaseOperations.convert_datetimefield_value, TruncBase.convert_value]}
...
  TruncBase.convert_value(datetime(2026, 3, 1, 0, 0, tzinfo=UTC))
    BaseDatabaseOperations.convert_trunc_expression(datetime(2026, 3, 1, 0, 0, tzinfo=UTC))
      make_aware(datetime(2026, 3, 1, 0, 0), None)  ->  datetime(2026, 3, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key='Europe/Oslo'))
```
