---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the other contrib apps

The changes from Django 5.0 to this commit in the contrib applications for content types, static files, sitemaps, feeds and PostgreSQL: `GenericForeignKeyDescriptor`, the static files' `find` and collectstatic, feed stylesheets, and the PostgreSQL aggregates and checks.

Much of what changed here follows Django's core. 6.0 and 6.1 moved the PostgreSQL application's ordering of an aggregate, its string aggregate and its bit aggregates into `django.db.models`. The application's mixin for the ordering and its classes for the string and bit aggregates now warn; its keyword `ordering=` went in 6.1, and is now ignored without a word. The generic foreign key took a descriptor of its own in 6.1, which hands an object not yet loaded to the instance's fetch mode (6.1's choice of what reading an unloaded field or relation does: fetch it for that instance, for the instances loaded with it, or raise; [Deferred fields and fetch modes in a queryset](../querysets/deferred.md)), as other relations do since that release. A project's static files finder whose `find` still takes `all=`, the argument 5.2 renamed, raises `TypeError` under all four releases, unwarned. Authentication, sessions and messages, the admin and GeoDjango have sections of their own: [What changed in authentication, sessions and messages](auth.md), [What changed in the admin](admin.md) and [What changed in GeoDjango](geodjango.md).

## Content types: `GenericForeignKeyDescriptor` and `GenericPrefetch`

Until 6.1 a `GenericForeignKey` was its own descriptor. At this commit `GenericForeignKey.contribute_to_class` sets a `GenericForeignKeyDescriptor` on the model class under the field's name, so code that takes the field from the class gets the descriptor, which is not the field but holds it as `GenericForeignKeyDescriptor.field` (`django/contrib/contenttypes/fields.py:GenericForeignKey.contribute_to_class`). A model's content_object, read on the class and asked for the field's ct_field, answers from the field in the first two lines and from the descriptor in the last two:

```text recording=changes
Note.content_object.ct_field: the generic foreign key read on its model's class
    5.2.17       'content_type'
    6.0.8        'content_type'
    6.1.1        AttributeError: 'GenericForeignKeyDescriptor' object has no attribute 'ct_field'
    this commit  AttributeError: 'GenericForeignKeyDescriptor' object has no attribute 'ct_field'
```

The descriptor's `GenericForeignKeyDescriptor.__get__` hands an object not yet loaded to the instance's fetch mode (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.__get__`; [What changed in querysets](querysets.md)). Since 5.0 `GenericPrefetch` gives `prefetch_related` a queryset for each model a generic key reaches, where a `Prefetch` holds one (`django/contrib/contenttypes/prefetch.py:GenericPrefetch`; [Generic foreign keys: `GenericForeignKey`](../contrib/generic-foreign-key.md)).

## Static files: `find`, collectstatic and the manifest

The function `find` asks each finder of `STATICFILES_FINDERS` for a path. 5.2 renamed its argument `all=`, which asks for every match, to `find_all=`. Under 5.2.17 and 6.0.8 `find("entry.css", all=True)` still returned every match and warned, and since 6.1 it raises `TypeError` (`django/contrib/staticfiles/finders.py:find`; [Finding static files: the finders](../contrib/static-finders.md)).

> **Trap.** The deprecation covered `find` and Django's own finders, not a project's: under all four releases `find` hands each finder `find_all=` by keyword, so a finder whose own `find` still declares `all=` raises `TypeError`, unwarned (`django/contrib/staticfiles/finders.py:find`).

collectstatic copies the first file it meets at each destination path. At verbosity 1, 5.2.17 named each file it skipped, "Found another file with the destination path …", and counted none; since 6.0 it names them, and the files `--clear` deletes, at verbosity 2 only, and its summary counts the skipped and the deleted files (`django/contrib/staticfiles/management/commands/collectstatic.py`; [Collecting static files: the collectstatic command](../contrib/collectstatic.md)). Since 6.0 `ManifestFilesMixin.save_manifest` sorts the paths of staticfiles.json, which 5.2.17 wrote in the order it held them, for reproducible manifests, the notes say (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.save_manifest`, `docs/releases/6.0.txt`).

## Feed stylesheets

A feed generator takes `stylesheets=` since 5.2, which the 5.2 notes say every `SyndicationFeed` class writes (`docs/releases/5.2.txt`). Only `RssFeed` and its subclasses do, through `RssFeed.add_stylesheets`; `Atom1Feed.write` never calls that hook, so under all four releases an `Atom1Feed` given a stylesheet writes none (`django/utils/feedgenerator.py:Atom1Feed.write`; [Feeds: `django.contrib.syndication` and the feed generator](../contrib/feeds.md#stylesheets)).

## PostgreSQL: the aggregates become Django's own

`ArrayAgg`, `JSONBAgg` and the PostgreSQL `StringAgg` had an ordering of their own, the keyword `ordering=`, from `OrderableAggMixin`. 5.2 deprecated it for `order_by=`; 6.0 gave `order_by=` to `Aggregate` itself, allowed where `Aggregate.allow_order_by` is true, as on `ArrayAgg` and `JSONBAgg` (`django/db/models/aggregates.py:Aggregate.__init__`, `django/contrib/postgres/aggregates/general.py:ArrayAgg`; [What changed in expressions, lookups and the compiler](sql.md)); and 6.1 removed `ordering=`. Look for the ORDER BY when `ArrayAgg` is given `ordering=` and compiled for PostgreSQL:

```text recording=changes
ArrayAgg("title", ordering="-title"), compiled for PostgreSQL
    5.2.17       ARRAY_AGG("journal_entry"."title" ORDER BY "journal_entry"."title" DESC), warns RemovedInDjango61Warning
    6.0.8        ARRAY_AGG("journal_entry"."title" ORDER BY "journal_entry"."title" DESC), warns RemovedInDjango61Warning
    6.1.1        ARRAY_AGG("journal_entry"."title")
    this commit  ARRAY_AGG("journal_entry"."title")
```

> **Trap.** Since 6.1 `ordering=` is neither refused nor warned of. `Aggregate.__init__` passes a keyword it does not know on to `Func.__init__`, which keeps it as context for a template that never reads it, and the aggregate is written unordered (`django/db/models/expressions.py:Func.__init__`).

Since 5.0 `ArrayAgg`, `JSONBAgg` and the PostgreSQL `StringAgg` give `None` over no rows unless given `default=`, where they gave an empty list or string, the 5.0 notes say (`docs/releases/5.0.txt`, `django/db/models/aggregates.py:Aggregate`).

`StringAgg` moved into `django.db.models` in 6.0, and `BitAnd`, `BitOr` and `BitXor` in 6.1. The PostgreSQL classes of those names remain, as subclasses of the general ones, and warn when made: the PostgreSQL `StringAgg` since 6.0, with a second warning for a string `delimiter=`, and the bit aggregates since 6.1. `OrderableAggMixin` warns since 6.0 when a class is made from it. All go in Django 2028 (`django/contrib/postgres/aggregates/general.py`; [The PostgreSQL application: `PostgresConfig`, operations and aggregates](../contrib/postgres.md#functions-and-aggregates)).

> **Trap.** The general `StringAgg` reads a string `delimiter=` as a field's name. `StringAgg.__init__` wraps the delimiter in a `StringAggDelimiter`, a `Func`, which makes a string an `F`. So a project that moves its import to `django.db.models` and keeps `delimiter=", "` meets `FieldError` as the query is built, where the PostgreSQL class sent the string as a parameter and warned (`django/db/models/aggregates.py:StringAgg.__init__`).

## PostgreSQL: the application checked for

Since 6.0 the application's fields, indexes and `ExclusionConstraint` check that `django.contrib.postgres` is in `INSTALLED_APPS`: `CheckPostgresInstalledMixin.check` adds the error `"postgres.E005"` when it is not (`django/contrib/postgres/utils.py:CheckPostgresInstalledMixin`). An error stops runserver and migrate: an `ArrayField` without the application passed its checks under 5.2.17, and fails them since 6.0.

## The smaller changes

The smaller changes to sitemaps and to the PostgreSQL application, by name ([Sitemaps: `Sitemap` and the sitemap views](../contrib/sitemaps.md)):

| what | at this commit | release | where |
|---|---|---|---|
| ping_google, the function and the command | removed with the exception SitemapNotFound, Google's ping endpoint being due to close in January 2024, the 5.0 notes say | 5.0 | `docs/releases/5.0.txt` |
| `Sitemap.get_protocol` | `"https"` when neither `Sitemap.protocol` nor a request gives one, where it was `"http"` | 5.0 | `django/contrib/sitemaps/__init__.py:Sitemap.get_protocol` |
| `ArrayField` of `django.db.models.JSONField` | an item `None` saved as SQL NULL, where 5.2.17 and 6.0.8 saved JSON null; rows last saved before 6.1 keep their JSON null beside the newer rows' NULL | 6.1 | `django/contrib/postgres/fields/array.py:ArrayField.get_db_prep_save` |
| `CICharField`, `CIEmailField`, `CITextField` | kept for old migrations, failing the checks `"fields.E905"` to `"fields.E907"`; the mixin CIText gone | 5.1 | `django/contrib/postgres/fields/citext.py` |
| `ExclusionConstraint` | `opclasses=` gone, and `violation_error_code` new (5.0); the index type `"hash"`, for one expression with `RangeOperators.EQUAL` (6.1) | 5.0, 6.1 | `django/contrib/postgres/constraints.py:ExclusionConstraint` |
| `BTreeIndex` | takes `deduplicate_items=` | 5.1 | `django/contrib/postgres/indexes.py:BTreeIndex` |
| `Lexeme` | new: a search term escaped into one parameter | 6.0 | `django/contrib/postgres/search.py:Lexeme` |
| `CreateExtension` and its subclasses | take `hints=`, for the router | 6.0 | `django/contrib/postgres/operations.py:CreateExtension` |
| inspectdb | hstore found by the type's name, with psycopg 3.2 and the application | 6.1 | `django/db/backends/postgresql/introspection.py:DatabaseIntrospection.get_table_description` |
