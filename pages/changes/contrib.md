---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in the other contrib apps

The changes from Django 5.0 to this commit in the contrib applications other than authentication, sessions, messages and the admin: the generic foreign key's descriptor and `GenericPrefetch`, the static files finders and manifest, sitemaps and feeds, the aggregates and other parts of `django.contrib.postgres`, and GeoDjango's functions, its GDAL and GEOS wrappers, `GeoIP2` and the map widgets.

Two of these changes alter how a part works: the PostgreSQL aggregates handed their ordering and their string and bit aggregates to Django's own, and GDAL's geometries gained an M dimension and curves ([Content types, static files and the other contrib apps](../contrib.md)).

## Content types: `GenericForeignKeyDescriptor` and `GenericPrefetch`

Until 6.1 a `GenericForeignKey` was its own descriptor, as the field's docstring still says. At this commit `GenericForeignKey.contribute_to_class` sets on the model class, under the field's name, a `GenericForeignKeyDescriptor` (`django/contrib/contenttypes/fields.py:GenericForeignKey.contribute_to_class`). The attribute read on the class is no longer the field: in a run, a note model's content_object was a `GenericForeignKeyDescriptor`, whose `GenericForeignKeyDescriptor.field` was the `GenericForeignKey`. Its `GenericForeignKeyDescriptor.__get__` leaves a missing object to the instance's fetch mode, which calls `GenericForeignKeyDescriptor.fetch_one` or `GenericForeignKeyDescriptor.fetch_many`, as for other relations since 6.1 (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.__get__`; [What changed in querysets](querysets.md)).

A `Prefetch` holds one queryset, and a generic key's objects belong to several models. `GenericPrefetch` (5.0) holds a list, one queryset for each model (`django/contrib/contenttypes/prefetch.py:GenericPrefetch`); `GenericForeignKeyDescriptor.get_prefetch_querysets` files each under its model's content type and uses it in place of the default query for that type (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.get_prefetch_querysets`) ([Generic foreign keys: `GenericForeignKey`](../contrib/generic-foreign-key.md)).

## Static files: `find`, the manifest and collectstatic's summary

The keyword all of the function `find`, deprecated in 5.2 for find_all, was removed in 6.1. `find` and each finder's `BaseFinder.find` take `find_all=False`, and `find` passes it by keyword to each finder it asks (`django/contrib/staticfiles/finders.py:find`). In a run, a project's own finder whose `find` still took all failed when `find` called it: "OldFinder.find() got an unexpected keyword argument 'find_all'" ([Finding static files: the finders](../contrib/static-finders.md)).

Since 6.0 `ManifestFilesMixin.save_manifest` writes the manifest's paths sorted by name, so that the same files give the same staticfiles.json, the release notes say (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.save_manifest`) ([Static file storages: `ManifestStaticFilesStorage` and hashed names](../contrib/static-storage.md)), and collectstatic at verbosity 1 only counts, in its summary, the files it skipped for a clash of paths and those `--clear` deleted (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.handle`), and names each at verbosity 2 (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.collect`) ([Collecting static files: the collectstatic command](../contrib/collectstatic.md)).

## Sitemaps and feeds

5.0 removed the function and the command ping_google, because Google's ping endpoint was to close in January 2024, the release notes say (`docs/releases/5.0.txt`), and the exception SitemapNotFound with them. A sitemap built outside a request has written `"https"` URLs since 5.0, where it wrote `"http"`: `Sitemap.get_protocol` falls back to it when neither the sitemap nor its caller names a protocol (`django/contrib/sitemaps/__init__.py:Sitemap.get_protocol`). `SitemapIndexItem`, the location and date the `index` view hands its template for each sitemap, has had no __str__ of its own since 5.0 ([Sitemaps: `Sitemap` and the sitemap views](../contrib/sitemaps.md)).

The feed generator takes stylesheets since 5.2, and `SyndicationFeed.__init__` makes each string a `Stylesheet` (`django/utils/feedgenerator.py:SyndicationFeed.__init__`). The release notes say every feed class writes them; at this commit only `RssFeed.add_stylesheets` does, and `Atom1Feed.write` never calls the hook, so in a run an Atom feed given a stylesheet wrote none ([Feeds: `django.contrib.syndication` and the feed generator](../contrib/feeds.md#stylesheets)).

## PostgreSQL: the aggregates become Django's own

`ArrayAgg`, `JSONBAgg` and the PostgreSQL `StringAgg` once had an ordering of their own, the keyword ordering, which `OrderableAggMixin` gave them. 5.2 deprecated it for order_by, 6.0 gave order_by to `Aggregate` itself, allowed where `Aggregate.allow_order_by` is true, as on `ArrayAgg` and `JSONBAgg`, and 6.1 removed ordering (`django/db/models/aggregates.py:Aggregate.__init__`). Since 5.0 `ArrayAgg`, `JSONBAgg` and the PostgreSQL `StringAgg` give `None` over no rows, where they gave an empty list or string, unless given a default.

> **Trap.** ordering is not refused. `Aggregate.__init__` passes an unknown keyword on to `Func.__init__`, which keeps it as extra context for a template that never reads it (`django/db/models/expressions.py:Func.__init__`). In a run, `ArrayAgg("ships__name", ordering="-ships__name")` compiled for PostgreSQL to an `"ARRAY_AGG"` with no `"ORDER BY"`, and with `order_by="-ships__name"` to one ordered by the name, descending.

What only PostgreSQL had moved into `django.db.models`: `StringAgg` in 6.0, and `BitAnd`, `BitOr` and `BitXor` in 6.1 (`django/db/models/aggregates.py`; [What changed in expressions, lookups and the compiler](sql.md)). The PostgreSQL classes remain, subclasses of the general ones that warn when made, the old `StringAgg` with a second warning for a delimiter given as a string, which the general one would read as a field; `OrderableAggMixin` warns when a class is made from it. All go in Django 2028 (`django/contrib/postgres/aggregates/general.py`; [The PostgreSQL application: `PostgresConfig`, operations and aggregates](../contrib/postgres.md#functions-and-aggregates), [What still warns: the deprecations and the releases that end them](deprecations.md)).

| what | change | release |
|---|---|---|
| `CICharField`, `CIEmailField`, `CITextField` | kept for old migrations only, failing the checks `"fields.E905"` to `"fields.E907"`; the mixin CIText gone (`django/contrib/postgres/fields/citext.py`) | 5.1 |
| `ArrayField` of `django.db.models.JSONField` | an item `None` saved as SQL null, not JSON null ([PostgreSQL fields: `ArrayField`, the range fields and hstore](../contrib/postgres-fields.md)) | 6.1 |
| `ExclusionConstraint` | opclasses removed, `OpClass` instead, and `violation_error_code` (5.0); the index type `"hash"`, for one pair with `RangeOperators.EQUAL` and no include (6.1) ([PostgreSQL indexes and `ExclusionConstraint`](../contrib/postgres-indexes.md)) | 5.0, 6.1 |
| `BTreeIndex` | deduplicate_items (`django/contrib/postgres/indexes.py:BTreeIndex.get_with_params`) | 5.1 |
| `Lexeme` | a search term escaped into one parameter ([Full-text search: `SearchVector`, `SearchQuery` and `SearchRank`](../contrib/postgres-search.md)) | 6.0 |
| `"postgres.E005"` | the fields, indexes and constraint fail their checks without the application (`django/contrib/postgres/utils.py:CheckPostgresInstalledMixin`) | 6.0 |
| `CreateExtension` and its subclasses | take hints for the router (`django/contrib/postgres/operations.py:CreateExtension`) | 6.0 |
| inspectdb | finds hstore by the type's name, with psycopg 3.2 or later and the application installed (`django/db/backends/postgresql/introspection.py:DatabaseIntrospection.get_table_description`) | 6.1 |

*The other changes to `django.contrib.postgres`.*

## GeoDjango: GDAL's dimensions and curves

`OGRGeometry` once knew a geometry's coordinate dimension only as `OGRGeometry.coord_dim`, which could be set. Since 5.1 it reads a Z and an M dimension apart, `OGRGeometry.is_3d` and `OGRGeometry.is_measured`, changed by `OGRGeometry.set_3d` and `OGRGeometry.set_measured`, and the M coordinate as `Point.m` and `LineString.m`; the setter of `coord_dim`, deprecated then, went in 6.0. Since 5.2 it reads curved geometries, `CircularString`, `CompoundCurve`, `CurvePolygon`, `MultiCurve` and `MultiSurface`, with `OGRGeometry.has_curve`, `OGRGeometry.get_linear_geometry` and `OGRGeometry.get_curve_geometry`. These classes set `OGRGeometry.geos_support` false, and their `OGRGeometry.geos` raises `GEOSException`, saying that GEOS does not support them (`django/contrib/gis/gdal/geometries.py:OGRGeometry.geos`). `OGRGeometry.centroid` is every geometry's since 5.1.

On the GEOS side, `GEOSGeometryBase.equals_identical` (5.0) compares geometries point by point and `GEOSGeometryBase.hasm` (6.0) asks for an M dimension; both raise `GEOSException` on a GEOS older than 3.12 (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.hasm`) ([Geometries in Python: GEOS and GDAL](../contrib/geometries.md)).

A data source's time and date-time fields keep their milliseconds since 6.2. GDAL's `Field.as_datetime` asks for the seconds as a `ctypes.c_float` where it asked for a `ctypes.c_int`, and `OFTDateTime.value` and `OFTTime.value` split the fraction off (`django/contrib/gis/gdal/field.py:Field.as_datetime`).

## GeoDjango: functions, lookups, `GeoIP2` and the widgets

The functions (`django/contrib/gis/db/models/functions.py`), aggregates, lookups and units added, or given a backend, since 5.0:

| what | release | where |
|---|---|---|
| `ClosestPoint` | 5.0 | PostGIS and SpatiaLite |
| the spatial aggregates' filter | 5.0 | as on any `Aggregate` |
| `BoundingCircle` | 5.1 | SpatiaLite 5.1 or later too |
| `Collect` | 5.1 | MySQL too; MariaDB from 12.0.1 (6.0) |
| `FromWKB`, `FromWKT` | 5.1 | take an SRID, 0 by default, which Oracle ignores |
| `"ha"` | 5.1 | a unit of `django.contrib.gis.measure.Area` |
| `"coveredby"`, `"covers"` | 5.2 | MySQL too; `"coveredby"` on MariaDB from 12.0.1 (6.0) |
| `GeoHash`, `IsValid`, `"isvalid"` | 6.0 | MariaDB from 12.0.1 too |
| `Rotate` | 6.0 | PostGIS |
| `GeometryType`, `"geom_type"` | 6.0 | every backend; Oracle from 23 |
| `IsEmpty`, `"isempty"` | 6.1 | SpatiaLite too |
| `NumDimensions`, `"num_dimensions"` | 6.1 | PostGIS and SpatiaLite |

*Where each runs, from the backends' operations at this commit (`django/contrib/gis/db/backends/`). `GeometryType`, `IsEmpty`, `IsValid` and `NumDimensions` are also transforms of the spatial fields ([Spatial lookups, functions and distances](../contrib/spatial-queries.md)).*

`GeoIP2` opens one database since 5.1, where from a directory it opened both: the path given if it is a file, else the city database in that directory, else the country one; `GeoIP2.country` reads whichever is open (`django/contrib/gis/geoip2.py:GeoIP2.__init__`). It takes `ipaddress.IPv4Address` and `ipaddress.IPv6Address` as well as strings, and the answers of `GeoIP2.country` gained `"continent_code"`, `"continent_name"` and `"is_in_european_union"`, and those of `GeoIP2.city` `"accuracy_radius"`, `"region_name"`, `"metro_code"` and `"region_code"`, beside the old `"dma_code"` and `"region"`. Its coords and open went in 6.0, for `GeoIP2.lon_lat` and the constructor ([GeoDjango's forms, admin, feeds and data tools](../contrib/gis-extras.md#locating-an-address-geoip2)).

The admin's own GeoModelAdmin, OSMGeoAdmin and OpenLayersWidget went in 5.0, leaving `GISModelAdmin` and the form widgets (`django/contrib/gis/admin/__init__.py`), and `BaseGeometryWidget` lost map_width and map_height in 5.1. Since 6.0 the widgets render no inline JavaScript: their options go into the page as JSON for the widget's script, and `BaseGeometryWidget.base_layer` names the map's tiles. `OpenLayersWidget` loads OpenLayers 10.9.0 since 6.1, 7.2.2 before (`django/contrib/gis/forms/widgets.py:OpenLayersWidget`) ([GeoDjango's forms, admin, feeds and data tools](../contrib/gis-extras.md#the-map-widgets)).
