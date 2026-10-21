---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Spatial fields: the geometry fields and `RasterField`

The model fields of `django.contrib.gis.db.models`: `BaseSpatialField`, which gives every spatial field its coordinate system, column type and way into a statement; the geometry fields, which hold a `GEOSGeometry`; `RasterField`, which holds a `GDALRaster`; and `SpatialProxy`, the descriptor that lets a model's attribute take a string and give back a geometry.

A geometry column asks three things of its field: a column type that only a spatial database has, and the coordinate system its values are in; a value in Python that is an object over a C library; and a way to it from the text people write, WKT or GeoJSON. `BaseSpatialField`, a `django.db.models.Field`, and the classes built on it answer them: `GeometryField`, for vector geometries, and `RasterField`, for grids of values (`django/contrib/gis/db/models/fields.py:BaseSpatialField`).

## The column and the SRID

Where `django.db.models.Field.db_type` looks the internal type up in the backend's table of column types ([A field: the base class](../models/fields.md)), `BaseSpatialField.db_type` returns what the connection's operations object writes with `geo_db_type` (`django/contrib/gis/db/models/fields.py:BaseSpatialField.db_type`). A plain backend has no such method, so a spatial field needs a spatial backend. PostGIS's writes the field's geometry type, with `"Z"` for three dimensions, and its SRID (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.geo_db_type`). For the `"postgis"` connection, with no server behind it, and SQLite's `"default"`:

```text
PointField().db_type(postgis)  ->  'geometry(POINT,4326)'
LineStringField(geography=True).db_type(postgis)  ->  'geography(LINESTRING,4326)'
RasterField().db_type(postgis)  ->  'raster'
PointField(geography=True, srid=32633).db_type(postgis)  ->  raises NotSupportedError: PostGIS only supports geography columns with an SRID of 4326.
PointField().db_type(default)  ->  raises AttributeError: 'DatabaseOperations' object has no attribute 'geo_db_type'
```

The **SRID**, `BaseSpatialField.srid`, is the number of the field's coordinate system, usually an EPSG code, by default 4326: longitude and latitude in degrees. `BaseSpatialField.deconstruct` writes it into every migration, for "less fragility" in its comment's words, and `spatial_index` only when it is false. That argument stands in for `db_index` because a spatial index, the documentation says, is typically a variant of the R-tree (`docs/ref/contrib/gis/model-api.txt`); the backend's schema editor makes it ([Spatial backends: PostGIS, SpatiaLite, MySQL and Oracle](spatial-backends.md)).

What an SRID means is the database's to say. `BaseSpatialField.geodetic`, `BaseSpatialField.units_name` and their siblings ask `get_srid_info`, which the first time reads the SRID's row of `"spatial_ref_sys"`, or Oracle's `"CS_SRS"`, and keeps its units, its spheroid and whether it is geographic in `_srid_cache`, by alias and SRID, for the life of the process; on MySQL, whose backend has no model of such a table, GDAL's `SpatialReference` answers (`django/contrib/gis/db/models/fields.py:get_srid_info`). The cache's comment says why: so that the database is not queried each time a distance query is constructed ([Spatial lookups, functions and distances](spatial-queries.md)).

## On the instance: `SpatialProxy`

`GeometryField.contribute_to_class` puts a `SpatialProxy` on the model class under the field's attname (`django/contrib/gis/db/models/fields.py:GeometryField.contribute_to_class`). It is a `DeferredAttribute` with a `__set__`, so a data descriptor: every assignment goes through it, those of `Model.__init__` included, and every read, which fetches a deferred value through the instance's fetch mode ([Deferred fields and the fetch modes](../instance/fetching.md)).

`SpatialProxy.__set__` checks a value's type and stores it unchanged in the instance's `__dict__`. It takes `None`, a string or a `memoryview` without looking inside, and an object of the field's `geom_class`, any `GEOSGeometry` for `GeometryField` itself, to which it gives the field's SRID if it has none. Anything else raises `TypeError`. `SpatialProxy.__get__` parses a string or a `memoryview` at the first read, with `GEOSGeometry` and the field's `max_geom_collections`, and assigns the result back through `__set__`, so the string is parsed once and its type checked then (`django/contrib/gis/db/models/proxy.py:SpatialProxy`). A mooring made in Python:

```text
m = Mooring(name="Customs House", depth="7.5", position="POINT (14.5143 35.8957)")
m.__dict__["position"]  ->  'POINT (14.5143 35.8957)'
m.position.ewkt  ->  'SRID=4326;POINT (14.5143 35.8957)'
m.position = '{"type": "Point", "coordinates": [14.5196, 35.8922]}'
m.position.ewkt  ->  'SRID=4326;POINT (14.5196 35.8922)'
p = Point(14.5143, 35.8957)
m.position = p
p.srid  ->  4326
anchorage = Polygon(((14.51, 35.89), (14.53, 35.89), (14.53, 35.90), (14.51, 35.90), (14.51, 35.89)))
setattr(m, "position", anchorage)  ->  raises TypeError: Cannot set Mooring SpatialProxy (POINT) with value of type: <class 'django.contrib.gis.geos.polygon.Polygon'>
m.position = anchorage.wkt
m.position  ->  raises TypeError: Cannot set Mooring SpatialProxy (POINT) with value of type: <class 'django.contrib.gis.geos.polygon.Polygon'>
```

The SRID went to the point assigned, not to a copy. A point of another SRID keeps its own, and PostGIS transforms it when it is written.

> **Trap.** A string is checked only when it is read. The point field took the WKT of a polygon, and the read that parsed it raised the `TypeError` the polygon itself raised at once.

## Into a statement and out of a row

Of the four methods that carry a value into a statement ([A field: the base class](../models/fields.md)), a spatial field overrides the inner two. `BaseSpatialField.get_prep_value`, which a lookup calls when it is made, keeps a `GEOSGeometry` or a `GDALRaster`, makes a geometry of a string, and of bytes a raster if GDAL can read one or else a geometry; then `BaseSpatialField.get_srid` gives a value with no SRID, or with -1, the field's, and keeps any other unless the field's is -1 (`django/contrib/gis/db/models/fields.py:BaseSpatialField.get_prep_value`). `BaseSpatialField.get_db_prep_value` wraps the result in the backend's `Adapter`, on PostGIS a `PostGISAdapter`, there told `geography=True` for a geography field. `BaseSpatialField.get_placeholder_sql` hands the compiler's question, what to write where the value goes, to the backend's `get_geom_placeholder_sql`, which on PostGIS transforms a value of another SRID (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.get_geom_placeholder_sql`). Two moorings, made with a WKT string and with a point in 3857, compiled for PostGIS with no server behind it:

```text
INSERT INTO "charts_mooring" ("name", "position", "depth") VALUES (%s, %s, %s)
params: ('Customs House', a PostGISAdapter of SRID 4326, Decimal('7.5'))
INSERT INTO "charts_mooring" ("name", "position", "depth") VALUES (%s, ST_Transform(%s, %s), %s)
params: ('Fort St Angelo', a PostGISAdapter of SRID 3857, 4326, Decimal('9.0'))
```

A string could also name a raster, and GDAL opens more than files: a path beginning "/vsi" reaches its virtual file systems, URLs among them, and a dictionary makes a raster in write mode. So `GDALRaster.check_raster_lookup_value` refuses a dictionary, a string or a path with `DisallowedRasterLookup`, a `SuspiciousOperation`, which a request answers with 400 (`django/contrib/gis/gdal/raster/source.py:GDALRaster.check_raster_lookup_value`) ([How an exception becomes a response](../handlers/exceptions.md)). For a string the refusal waits while `GEOSGeometry` has its turn, so WKT still works; it is raised if that fails on a string that begins "/vsi" or looks like JSON, as a filter of moorings by "/vsicurl/https://charts.example/harbour.tif" did (`django/contrib/gis/db/models/fields.py:BaseSpatialField.get_prep_value`).

On the way out a geometry field has no `from_db_value`: the backend adds a converter for every expression whose output field is a geometry field (`django/contrib/gis/db/backends/base/operations.py:BaseSpatialOperations.get_db_converters`). PostGIS's reads the WKB and gives the result the field's `geom_class` without asking GEOS its type; for `GeometryField`, whose `geom_class` is `None`, it asks (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.get_geometry_converter`). `GeometryField.select_format` wraps the column, outside a subquery, in the backend's `select`, for the backends that must ask for WKB, SpatiaLite and Oracle among them.

> **Why.** `max_geom_collections`, 198 by default, limits the nesting of geometry collections in WKT and their number in WKB, against a crash in GEOS the release notes describe (`docs/releases/6.0.8.txt`). The proxy and `get_prep_value` apply it; the converters pass `None`.

## The geometry classes

`PointField`, `LineStringField`, `PolygonField`, `MultiPointField`, `MultiLineStringField`, `MultiPolygonField` and `GeometryCollectionField`, the subclasses of `GeometryField`, set three class attributes and a description (`django/contrib/gis/db/models/fields.py:PointField`): `GeometryField.geom_type`, the type's OpenGIS name, which PostGIS and MySQL write into the column's type; `GeometryField.geom_class`, the GEOS class the proxy demands and the converter makes; and `GeometryField.form_class`, the form field of the same name. `GeometryField` itself has `"GEOMETRY"` and no class.

Its other arguments but `max_geom_collections` are the backends': `dim`, 2 or 3; `geography`, which makes on PostGIS a column of the geography type, whose measurements, the documentation says, follow great circles and come out in linear units; `extent` and `tolerance`, which only Oracle's schema editor reads. `GeometryField.deconstruct` writes each only when it differs from its default; `GeometryField.formfield` gives the form field the type, the SRID and the limit ([GeoDjango's forms, admin, feeds and data tools](gis-extras.md)).

The lookups, and some functions that serve as transforms, are registered on `BaseSpatialField` itself when `django.contrib.gis.db.models` is imported (`django/contrib/gis/db/models/lookups.py`, `django/contrib/gis/db/models/functions.py`); `"exact"` is another name for `"same_as"`, which PostGIS writes as `~=` ([Spatial lookups, functions and distances](spatial-queries.md)).

## `RasterField`

`RasterField` holds a `GDALRaster`; its `geom_type` is `"RASTER"` (`django/contrib/gis/db/models/fields.py:RasterField`). Its `db_type` first calls `RasterField._check_connection`, which refuses a backend that is not spatial or, unlike PostGIS, lacks raster support. Its `SpatialProxy` takes `None`, a string, a dictionary or a raster and makes the raster at the first read: making every raster of a large queryset, the comment says, could be expensive. Unlike a geometry field it has a `from_db_value`, which hands the column to the backend's `parse_raster`, and `RasterField.get_transform` reads a number as a band.

`ExtentField` is no model's field but the output field of the aggregates `Extent` and `Extent3D` (`django/contrib/gis/db/models/fields.py:ExtentField`).
