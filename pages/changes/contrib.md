---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the other contrib apps

`GenericForeignKeyDescriptor` and `GenericPrefetch`; the static files' `find`, collectstatic and manifest; feed stylesheets; sitemaps; and the PostgreSQL aggregates that became Django's own, and the check for `django.contrib.postgres`.

6.0 and 6.1 moved the PostgreSQL application's ordering of an aggregate, its string aggregate and its bit aggregates into `django.db.models`. The application's mixin for the ordering and its classes for the string and bit aggregates now warn. Its keyword `ordering=` went in 6.1, and is now ignored without a word. In 6.1 the generic foreign key took a descriptor of its own. A project's static files finder whose `find` still takes `all=`, the argument 5.2 renamed, raises `TypeError` under all four releases, unwarned.

Authentication, sessions and messages, the admin and GeoDjango have sections of their own: [What changed in authentication, sessions and messages](auth.md), [What changed in the admin](admin.md) and [What changed in GeoDjango](geodjango.md).

## Content types: `GenericForeignKeyDescriptor` and `GenericPrefetch`

Since 6.1, code that takes a `GenericForeignKey` from its model's class gets a `GenericForeignKeyDescriptor`, which is not the field but holds it as `GenericForeignKeyDescriptor.field`. Until 6.1 the field was its own descriptor. `GenericForeignKey.contribute_to_class` sets the descriptor on the class under the field's name (`django/contrib/contenttypes/fields.py:GenericForeignKey.contribute_to_class`). A model's content_object, read on the class and asked for the field's ct_field, answers from the field in the first two lines and from the descriptor in the last two:

```text recording=changes
Note.content_object.ct_field: the generic foreign key read on its model's class
    5.2.17       'content_type'
    6.0.8        'content_type'
    6.1.1        AttributeError: 'GenericForeignKeyDescriptor' object has no attribute 'ct_field'
    this commit  AttributeError: 'GenericForeignKeyDescriptor' object has no attribute 'ct_field'
```

`GenericForeignKeyDescriptor.__get__` hands the fetching of an object not yet loaded to the instance's fetch mode, as a foreign key's descriptor does since 6.1 (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.__get__`; [What changed in querysets](querysets.md)). A **fetch mode** is 6.1's choice of what reading an unloaded field or relation does: fetch it for that instance, for the instances loaded with it, or raise ([Deferred fields and fetch modes in a queryset](../querysets/deferred.md)).

Since 5.0 `GenericPrefetch` gives `prefetch_related` a queryset for each model a generic key reaches, where a `Prefetch` holds one (`django/contrib/contenttypes/prefetch.py:GenericPrefetch`; [Generic foreign keys: `GenericForeignKey`](../contrib/generic-foreign-key.md)).

## Static files: `find`, collectstatic and the manifest

Since 6.1 the function `find` raises `TypeError` when given `all=`, the argument 5.2 renamed `find_all=`. `find` asks each finder of `STATICFILES_FINDERS` for a path, and `find_all=` asks for every match. Under 5.2.17 and 6.0.8 `find("entry.css", all=True)` still returned every match, and warned. The deprecation covered `find` and Django's own finders, not a project's. Under all four releases `find` hands each finder `find_all=` by keyword, so a finder whose own `find` still declares `all=` raises `TypeError`, unwarned (`django/contrib/staticfiles/finders.py:find`; [Finding static files: the finders](../contrib/static-finders.md)).

collectstatic collects the first file it meets at each destination path, and skips the others. Since 6.0 it names the files it skips, and those `--clear` deletes, only from verbosity 2; at verbosity 1 its summary counts them. 5.2.17 named each skipped file at verbosity 1, "Found another file with the destination path …", and counted none (`django/contrib/staticfiles/management/commands/collectstatic.py`; [Collecting static files: the collectstatic command](../contrib/collectstatic.md)).

Since 6.0 `ManifestFilesMixin.save_manifest` sorts the paths of staticfiles.json, for reproducible manifests, the notes say. 5.2.17 wrote them in the order it held them (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.save_manifest`, `docs/releases/6.0.txt`).

## Feed stylesheets

Since 5.2 a feed generator takes `stylesheets=`. The notes say every `SyndicationFeed` class writes them (`docs/releases/5.2.txt`), but only `RssFeed` and its subclasses do, through `RssFeed.add_stylesheets`. `Atom1Feed.write` never calls that hook, so under all four releases an `Atom1Feed` given a stylesheet writes none (`django/utils/feedgenerator.py:Atom1Feed.write`; [Feeds: `django.contrib.syndication` and the feed generator](../contrib/feeds.md#stylesheets)).

## PostgreSQL: the aggregates become Django's own

Since 6.1 `ArrayAgg`, `JSONBAgg` and the PostgreSQL `StringAgg` are ordered by `order_by=` alone. 6.1 removed their own keyword, `ordering=`, which under 5.2 came from `OrderableAggMixin`. 5.2 had deprecated it for `order_by=`, and 6.0 gave `order_by=` to `Aggregate` itself (`django/db/models/aggregates.py:Aggregate.__init__`; [What changed in expressions, lookups and the compiler](sql.md)). Look for the ORDER BY when `ArrayAgg` is given `ordering=` and compiled for PostgreSQL:

```text recording=changes
ArrayAgg("title", ordering="-title"), compiled for PostgreSQL
    5.2.17       ARRAY_AGG("journal_entry"."title" ORDER BY "journal_entry"."title" DESC), warns RemovedInDjango61Warning
    6.0.8        ARRAY_AGG("journal_entry"."title" ORDER BY "journal_entry"."title" DESC), warns RemovedInDjango61Warning
    6.1.1        ARRAY_AGG("journal_entry"."title")
    this commit  ARRAY_AGG("journal_entry"."title")
```

> **Trap.** Since 6.1 `ordering=` is neither refused nor warned of. `Aggregate.__init__` passes a keyword it does not know on to `Func.__init__`, which keeps it as context for a template that never reads it (`django/db/models/expressions.py:Func.__init__`).

`StringAgg` moved into `django.db.models` in 6.0, and `BitAnd`, `BitOr` and `BitXor` in 6.1. The PostgreSQL classes of those names remain, as subclasses of the general ones. Each warns when made: the PostgreSQL `StringAgg` since 6.0, with a second warning for a string `delimiter=`, and the bit aggregates since 6.1. `OrderableAggMixin` warns since 6.0 when a class is made from it. All go in Django 2028 (`django/contrib/postgres/aggregates/`; [The PostgreSQL application: `PostgresConfig`, operations and aggregates](../contrib/postgres.md#functions-and-aggregates)).

> **Trap.** A project that moves its import of `StringAgg` to `django.db.models` and keeps `delimiter=", "` meets `FieldError` as the query is built. The general `StringAgg` reads a string `delimiter=` as a field's name: `StringAgg.__init__` wraps it in a `StringAggDelimiter`, a `Func`, which makes a string an `F`. The PostgreSQL class sent the string as a parameter, and warned (`django/db/models/aggregates.py:StringAgg.__init__`).

## PostgreSQL: the application checked for

Since 6.0 the application's fields, indexes and `ExclusionConstraint` check that `django.contrib.postgres` is in `INSTALLED_APPS`. When it is not, `CheckPostgresInstalledMixin.check` adds the error `"postgres.E005"` (`django/contrib/postgres/utils.py:CheckPostgresInstalledMixin`). An error stops migrate and keeps runserver from serving. An `ArrayField` without the application passed its checks under 5.2.17, and fails them since 6.0.

## The smaller changes

The rest, by name, in sitemaps ([Sitemaps: `Sitemap` and the sitemap views](../contrib/sitemaps.md)) and the PostgreSQL application:

| what | change | where |
|---|---|---|
| ping_google | Gone in 5.0: the function, the command and the exception SitemapNotFound, since Google's ping endpoint was to close in January 2024 | `docs/releases/5.0.txt` |
| `Sitemap.get_protocol` | Since 5.0, `"https"` when neither `Sitemap.protocol` nor a request gives one, where it was `"http"` | `django/contrib/sitemaps/__init__.py:Sitemap.get_protocol` |
| the PostgreSQL aggregates over no rows | Since 5.0, `ArrayAgg`, `JSONBAgg` and `StringAgg` give `None` unless given `default=`, where they gave an empty list or string | `django/db/models/aggregates.py:Aggregate` |
| `ArrayField` of `django.db.models.JSONField` | Since 6.1, an item `None` is saved as SQL NULL, where it was JSON null; rows last saved before 6.1 keep their JSON null | `django/contrib/postgres/fields/array.py:ArrayField.get_db_prep_save` |
| the case-insensitive fields | Gone in 5.1, but kept for old migrations: `CICharField`, `CIEmailField` and `CITextField` fail the checks `"fields.E905"` to `"fields.E907"`; the mixin CIText is gone | `django/contrib/postgres/fields/citext.py` |
| `ExclusionConstraint` | Since 5.0, takes `violation_error_code=`, and `opclasses=` is gone | `django/contrib/postgres/constraints.py:ExclusionConstraint` |
| `ExclusionConstraint.index_type` | New in 6.1: `"hash"`, for one expression with `RangeOperators.EQUAL` and no `include=` | `django/contrib/postgres/constraints.py:ExclusionConstraint.__init__` |
| `BTreeIndex` | New in 5.1: `deduplicate_items=` | `django/contrib/postgres/indexes.py:BTreeIndex` |
| `Lexeme` | New in 6.0: a search term escaped into one parameter | `django/contrib/postgres/search.py:Lexeme` |
| `CreateExtension` and its subclasses | New in 6.0: `hints=`, for the router | `django/contrib/postgres/operations.py:CreateExtension` |
| inspectdb | Since 6.1, writes an hstore column as a `django.contrib.postgres.fields.HStoreField`, given psycopg 3.2 or later and `django.contrib.postgres` in `INSTALLED_APPS` | `django/db/backends/postgresql/introspection.py:DatabaseIntrospection.get_table_description` |
