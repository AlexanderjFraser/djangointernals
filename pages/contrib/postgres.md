---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The PostgreSQL application: `PostgresConfig`, operations and aggregates

What installing `django.contrib.postgres` changes, through `PostgresConfig.ready`, `uninstall_if_needed` and `register_type_handlers`; and its migration operations, such as `CreateExtension` and `AddIndexConcurrently`, and aggregates, such as `ArrayAgg`, some deprecated for those of `django.db.models`.

Most of the application is classes to import. Installing it also changes registries the whole process shares, and prepares each PostgreSQL connection for hstore and citext, types from extensions, whose numbers (OIDs), a comment says, may vary with the installation; Django asks each database for them.

## `PostgresConfig.ready`

`PostgresConfig.ready` runs as the app registry is populated ([Populating the app registry](../startup/populate.md)), in this order (`django/contrib/postgres/apps.py:PostgresConfig.ready`):

1. It connects `uninstall_if_needed` to `setting_changed`.
2. For each PostgreSQL connection object already made, it maps the five range types, by number, and hstore, by name (an extension's numbers vary, a comment says), to fields for introspection; if the connection is open, it registers the type handlers on it.
3. It connects `register_type_handlers` to `connection_created`, for each connection opened later.
4. It registers the transform `"unaccent"` and the lookups `"search"`, `"trigram_similar"`, `"trigram_word_similar"` and `"trigram_strict_word_similar"` on `django.db.models.CharField` and `django.db.models.TextField`, and so on their subclasses.
5. It registers `RangeSerializer` with `MigrationWriter`, so that a migration can hold the driver's range values (`django/contrib/postgres/serializers.py:RangeSerializer`).
6. It lets `OpClass` wrap an index's expression, between `OrderBy` and `Collate` (`django/db/models/indexes.py:IndexExpression.register_wrappers`; [PostgreSQL indexes and `ExclusionConstraint`](postgres-indexes.md)).

Step 2 reaches only connection objects already made, opened or not (`django/utils/connection.py:BaseConnectionHandler.all`). The default alias's is made as soon as a model without its own `db_table` is defined, which asks it for the longest name its database allows, and all models are imported before any `ready` runs (`django/db/models/options.py:Options.contribute_to_class`). The dictionary updated, `DatabaseIntrospection.data_types_reverse`, is the PostgreSQL backend's class attribute, so one connection found serves all (`django/db/backends/postgresql/introspection.py:DatabaseIntrospection`). The harbour office's run, SQLite by default, ended start-up without the range types ([Introspection: reading the schema back](../backends/introspection.md)).

### `uninstall_if_needed`

`override_settings` can install the application for a while, running `ready` again (`django/test/utils.py:override_settings.enable`). `uninstall_if_needed` undoes steps 1, 3, 4 and 5 when a change of `INSTALLED_APPS` ends and the list then in force lacks the application (`django/contrib/postgres/apps.py:uninstall_if_needed`): at the end of an override that added it, and at neither end of one that removed it. In the run:

```text
after django.setup()                   "search": True
an override without the application    "search": True
  a nested override with it            "search": True
  the nested override ended            "search": False
both ended                             "search": False
```

> **Trap.** Ending the outer override restores the stored registry and runs no `ready` (`django/apps/registry.py:Apps.unset_installed_apps`): the lookups stay unregistered though the application is installed.

## Type handlers for hstore and citext

`get_type_oids` asks pg_type for the numbers of a type and of its array type, returning every row found as two tuples (`django/contrib/postgres/signals.py:get_type_oids`); `get_hstore_oids` and `get_citext_oids` call it under `functools.lru_cache`, so each alias asks once, until `CreateExtension` clears the caches.

`register_type_handlers` has a version for psycopg 3 and one for psycopg 2, chosen at import. Both return at once for another vendor and for `NO_DB_ALIAS`, the connection with no database that makes test databases (`django/db/backends/base/base.py:BaseDatabaseWrapper._nodb_cursor`). Each registers only the types pg_type returned, and of citext only the array type: under psycopg 3 on the driver's connection object; under psycopg 2 hstore globally, and citext's array type with no connection named, a comment saying a project may use the application without the extensions, and must connect before it can install one (`django/contrib/postgres/signals.py:register_type_handlers`).

## `CheckPostgresInstalledMixin`

`CheckPostgresInstalledMixin.check`, new in 6.0, adds the error `"postgres.E005"` to the parent's checks when `Apps.is_installed` says the application is missing (`django/contrib/postgres/utils.py:CheckPostgresInstalledMixin`). With the application taken out, the sailings' crew field reported "'django.contrib.postgres' must be in INSTALLED_APPS in order to use ArrayField.", and their GIN index and exclusion constraint, checked for the "postgres" alias, the same error id, against the model; a model checks those only for the databases the checks are given and the router allows (`django/db/models/base.py:Model._check_indexes`).

## The migration operations

Of the operations of `django.contrib.postgres.operations` ([Operations: the base class and its two halves](../migrations/operations.md)), those on extensions and collations leave the project state alone, and ask the router with the application's label and no model ([Routing between databases: `ConnectionRouter`](../backends/routers.md)).

### `CreateExtension`

`CreateExtension.database_forwards` returns unless the connection is PostgreSQL's and the router, given the operation's hints (6.0), allows it. Only if `CreateExtension.extension_exists` finds no row in pg_extension does it write `"CREATE EXTENSION IF NOT EXISTS"`. Either way it then clears both caches of numbers and calls `register_type_handlers` on the schema editor's connection, which a comment says must wait for the extension, for a later data migration on the same connection. Backwards, it drops the extension if it exists and clears the caches (`django/contrib/postgres/operations.py:CreateExtension`). Its subclasses, `HStoreExtension` among them, fix the name.

### `AddIndexConcurrently` and `RemoveIndexConcurrently`

These subclasses of `AddIndex` and `RemoveIndex` pass `concurrently=True` to the schema editor, whose PostgreSQL version then writes `"CREATE INDEX CONCURRENTLY"` or `"DROP INDEX CONCURRENTLY IF EXISTS"` (`django/db/backends/postgresql/schema.py:DatabaseSchemaEditor._create_index_sql`, `django/db/backends/postgresql/schema.py:DatabaseSchemaEditor._delete_index_sql`). The documentation says the option is not supported inside a transaction (`docs/ref/contrib/postgres/operations.txt`), and each database half first calls `NotInTransactionMixin._ensure_not_in_transaction`, which raises `NotSupportedError` in an atomic block. What keeps the transaction away is the migration's `atomic = False`, handed by the executor to the schema editor (`django/db/migrations/executor.py:MigrationExecutor.apply_migration`); the operation's own `AddIndexConcurrently.atomic`, `False`, keeps none away (`django/db/migrations/migration.py:Migration.apply`). Compiled for PostgreSQL, then applied on SQLite:

```text
AddIndexConcurrently("sailing", Index(fields=["vessel"], name="sailing_vessel")), atomic = False
CREATE INDEX CONCURRENTLY "sailing_vessel" ON "charts_sailing" ("vessel");
atomic = True, on SQLite:
NotSupportedError: The AddIndexConcurrently operation cannot be executed inside a transaction (set atomic = False on the migration).
```

### Collations and constraints not yet valid

`CreateCollation` and `RemoveCollation` hold a name, a locale, a provider (`"libc"` by default) and a deterministic flag. Forwards, each checks the vendor and the router; backwards, the router alone. `CreateCollation.reduce` cancels a `CreateCollation` against a following `RemoveCollation` of the same name, and the optimizer drops both ([The optimizer: `MigrationOptimizer` and `reduce`](../migrations/optimizer.md)). A non-deterministic ICU collation, as handed to PostgreSQL's schema editor (`django/contrib/postgres/operations.py:CollationOperation.create_collation`):

```text
forwards:  CREATE COLLATION "harbour_ci" (locale="und-u-ks-level2", provider="icu", deterministic=false)
backwards: DROP COLLATION "harbour_ci"
```

`AddConstraintNotValid`, an `AddConstraint` for a `CheckConstraint` only ([The field operations, and those on indexes and constraints](../migrations/field-operations.md)), adds `"NOT VALID"`, leaving existing rows unchecked (`django/contrib/postgres/operations.py:AddConstraintNotValid`); `ValidateConstraint` checks them, and backwards does nothing, as a comment says PostgreSQL cannot make a constraint invalid (`django/contrib/postgres/operations.py:ValidateConstraint`).

## Functions and aggregates

`RandomUUID` writes `"GEN_RANDOM_UUID()"` and `TransactionNow` `"CURRENT_TIMESTAMP"` (`django/contrib/postgres/functions.py`). `ArraySubquery` is a `Subquery` inside `"ARRAY(...)"`, whose output is an `ArrayField` of the inner query's field (`django/contrib/postgres/expressions.py:ArraySubquery`).

The aggregates name a function, and some turn on what it accepts ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](../sql/aggregates.md)). `ArrayAgg` and `JSONBAgg` accept `distinct=True` and `order_by=...`, and give an `ArrayField` of the argument's field and a `JSONField`; `BoolAnd` and `BoolOr` a boolean (`django/contrib/postgres/aggregates/general.py:ArrayAgg`). The statistical aggregates take two expressions, y and x, refuse with `ValueError` unless both are given, and by default give a float, but `RegrCount` an integer (`django/contrib/postgres/aggregates/statistics.py:StatAggregate`).

| deprecated | since | use instead |
|---|---|---|
| the PostgreSQL `StringAgg` | 6.0 | `django.db.models.StringAgg`, the delimiter an expression |
| `BitAnd`, `BitOr`, `BitXor` | 6.1 | those of `django.db.models` |
| `OrderableAggMixin` | 6.0 | `Aggregate` with `Aggregate.allow_order_by` |

*Kept until Django 2028, each warning with `RemovedInDjango2028Warning`: the mixin when a class is made from it.*

The general `StringAgg` reads a string as a field's name, so the old one wraps a string delimiter in `Value`, with a second warning (`django/contrib/postgres/aggregates/general.py:StringAgg`). On the harbour's ports, compiled for PostgreSQL:

```text
StringAgg("ships__name", ", ", order_by="ships__name")   # django.contrib.postgres.aggregates
RemovedInDjango2028Warning: delimiter: str will be resolved as a field reference instead of a string literal on Django 2028. Pass `delimiter=Value(', ')` to preserve the previous behavior.
RemovedInDjango2028Warning: The PostgreSQL specific StringAgg function is deprecated. Use django.db.models.aggregates.StringAgg instead.
STRING_AGG("fleet_ship"."name", %s ORDER BY "fleet_ship"."name")   params: (', ',)
```

`django.db.models.StringAgg` given the same arguments raised `FieldError`, "Cannot resolve keyword ', ' into field", and given `Value(", ")` wrote the same SQL.
