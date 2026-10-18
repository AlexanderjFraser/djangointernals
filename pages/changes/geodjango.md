---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in GeoDjango

The map widgets and `BaseGeometryWidget.base_layer`; `OGRGeometry`'s Z and M dimensions and curves; the milliseconds of `DataSource`'s dates and times; `GeoIP2`'s one database; and new spatial functions and lookups.

Since 6.0 the map widgets write no JavaScript into the page, only their options, as data. 5.1 told `OGRGeometry`'s Z and M dimensions apart. 6.0 removed the old way of setting a dimension. 5.2 gave `OGRGeometry` curves, which GeoDjango's GEOS side cannot hold. Since 6.2 a `DataSource` keeps the milliseconds of dates and times. Since 5.1 `GeoIP2` opens one database.

The security fixes to `django.contrib.gis`, for rasters and for nested geometry collections, are in [Security fixes: SQL injection](security-fixes-sql.md), [Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md) and [Security fixes: limits against denial of service](security-fixes-limits.md). The oldest GDAL, GEOS and PostGIS by release are in [The versions Django needs: Python, databases and libraries](requirements.md).

## The map widgets: options as data, and `base_layer`

Since 6.0 the map widgets, `OpenLayersWidget` and `OSMWidget`, write no JavaScript into the page. Their template writes the options as JSON, and the widget's script, OLMapWidget.js, builds each map from them (`django/contrib/gis/templates/gis/openlayers.html`, `django/contrib/gis/static/gis/js/OLMapWidget.js`; [GeoDjango's forms, admin, feeds and data tools](../contrib/gis-extras.md#the-map-widgets)).

Under 5.2.17 the template gis/openlayers.html ended in a `<script>` with two blocks, base_layer and options, which made the base layer and the map's options. `OSMWidget`'s gis/openlayers-osm.html filled the two blocks. The lines give each script element's opening tag: 5.2.17's is that inline script, the later releases' the options as JSON:

```text recording=changes
OpenLayersWidget().render("position", None, attrs={"id": "id_position"}): the opening tag of each script element
    5.2.17       ['<script>']
    6.0.8        ['<script id="id_position_mapwidget_options" type="application/json">']
    6.1.1        ['<script id="id_position_mapwidget_options" type="application/json">']
    this commit  ['<script id="id_position_mapwidget_options" type="application/json">']
```

> **Trap.** Since 6.0 no widget of Django's renders a project's own gis/openlayers-osm.html. A template that extends gis/openlayers.html and fills base_layer or options renders without them: the blocks are gone, and nothing warns.

`BaseGeometryWidget.base_layer`, new in 6.0, names a layer builder in the script's MapWidget.layerBuilder: `"nasaWorldview"` for `OpenLayersWidget` and `"osm"` for `OSMWidget`, which now renders the same template. A project's own script can add a builder there. A name not there gives OpenStreetMap.

Since 6.1 `OpenLayersWidget` loads OpenLayers 10.9.0, where it loaded 7.2.2 (`docs/releases/6.1.txt`, `django/contrib/gis/forms/widgets.py:OpenLayersWidget`). 5.0 removed the admin's GeoModelAdmin, OSMGeoAdmin and django.contrib.gis.admin.OpenLayersWidget, leaving `GISModelAdmin` (`django/contrib/gis/admin/options.py:GISModelAdmin`). 5.1 removed `BaseGeometryWidget`'s map_width and map_height.

## GDAL's geometries: Z, M and curves

Since 6.0 setting `OGRGeometry.coord_dim`, a geometry's coordinate dimension, raises `AttributeError`. `OGRGeometry` is GDAL's geometry in GeoDjango, and until 5.1 it knew the dimension only as coord_dim. 5.1 told the Z and M dimensions apart: `OGRGeometry.is_3d` and `OGRGeometry.is_measured` read them, `OGRGeometry.set_3d` and `OGRGeometry.set_measured` add or drop them, and points and lines give their M coordinates (`django/contrib/gis/gdal/geometries.py:OGRGeometry.set_measured`). 5.1 also deprecated setting coord_dim. Only 5.2.17 still lets a point's third dimension be set the old way:

```text recording=changes
OGRGeometry("POINT (1 2)").coord_dim = 3
    5.2.17       coord_dim is 3, warns RemovedInDjango60Warning
    6.0.8        AttributeError: property 'coord_dim' of 'Point' object has no setter
    6.1.1        AttributeError: property 'coord_dim' of 'Point' object has no setter
    this commit  AttributeError: property 'coord_dim' of 'Point' object has no setter
```

5.2 added the curved geometries, `CircularString`, `CompoundCurve`, `CurvePolygon`, `MultiCurve` and `MultiSurface`, with `OGRGeometry.has_curve`, `OGRGeometry.get_linear_geometry` and `OGRGeometry.get_curve_geometry`. GeoDjango's GEOS classes have none for curves. The curved ones set `OGRGeometry.geos_support` false, and their `OGRGeometry.geos` raises `GEOSException` (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.__init__`, `django/contrib/gis/gdal/geometries.py:OGRGeometry.geos`).
On the GEOS side, `GEOSGeometryBase.equals_identical`, new in 5.0, compares geometries point by point. `GEOSGeometryBase.hasm`, new in 6.0, reads the M dimension. Both need GEOS 3.12 (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.hasm`; [Geometries in Python: GEOS and GDAL](../contrib/geometries.md#geosgeometry)).

## `DataSource`: dates and times keep their milliseconds

Since 6.2 a `DataSource` keeps the milliseconds of dates and times, and nothing warns. It gives date-time and time fields as `OFTDateTime` and `OFTTime`, whose values come from `Field.as_datetime`. Until 6.2 that method asked GDAL for whole seconds, into a `ctypes.c_int`. At this commit it calls GDAL's OGR_F_GetFieldAsDateTimeEx, whose seconds are a `ctypes.c_float`. `OFTDateTime.value` and `OFTTime.value` round the fraction to milliseconds (`django/contrib/gis/gdal/field.py:Field.as_datetime`, `django/contrib/gis/gdal/field.py:OFTDateTime.value`).

GDAL reads the GeoJSON property the block names as a date and time. Only this commit's line keeps the milliseconds, as 250000 microseconds:

```text recording=changes
DataSource("seen.geojson")[0][0]["seen"].value: a property written "2026-10-17T10:00:30.250"
    5.2.17       datetime.datetime(2026, 10, 17, 10, 0, 30)
    6.0.8        datetime.datetime(2026, 10, 17, 10, 0, 30)
    6.1.1        datetime.datetime(2026, 10, 17, 10, 0, 30)
    this commit  datetime.datetime(2026, 10, 17, 10, 0, 30, 250000)
```

At this commit `as_datetime` itself gives seconds of 30.25, where 6.1.1 gave 30. The 6.2 notes list that change as backwards incompatible (`docs/releases/6.2.txt`).

## `GeoIP2`: one database, and the old methods gone

Since 5.1 `GeoIP2` opens one database. Until then, given a directory, it opened both the city and the country database in it. The 5.1 notes say the country one is "a subset of the city database" (`docs/releases/5.1.txt`). Now `GeoIP2.__init__` opens the path itself if it is a file, else the city database in it, else the country one (`django/contrib/gis/geoip2.py:GeoIP2.__init__`). `GeoIP2.country` reads whichever is open.

6.0 removed the methods coords and open, which 5.1 had deprecated for `GeoIP2.lon_lat` and the constructor ([GeoDjango's forms, admin, feeds and data tools](../contrib/gis-extras.md#locating-an-address-geoip2)).

## Functions, lookups and backends

The spatial functions and lookups added since 5.0, then what each database gained ([Spatial lookups, functions and distances](../contrib/spatial-queries.md)):

| what | change | where |
|---|---|---|
| `ClosestPoint` | New in 5.0: the point of a geometry nearest another; PostGIS and SpatiaLite | `django/contrib/gis/db/models/functions.py:ClosestPoint` |
| the spatial aggregates | Since 5.0, take `filter=` | `django/contrib/gis/db/models/aggregates.py:GeoAggregate` |
| `FromWKB`, `FromWKT` | Since 5.1, take `srid=`, which Oracle ignores | `django/contrib/gis/db/models/functions.py:FromWKB` |
| the measure `Area` | Since 5.1, takes the unit `"ha"` | `django/contrib/gis/measure.py:Area` |
| `Rotate` | New in 6.0: a geometry turned about the origin or a point; PostGIS only | `django/contrib/gis/db/models/functions.py:Rotate` |
| `GeometryType`, `"geom_type"` | New in 6.0: a geometry's type; on Oracle from 23 | `django/contrib/gis/db/models/functions.py:GeometryType` |
| `NumDimensions`, `"num_dimensions"` | New in 6.1: a geometry's number of dimensions; PostGIS and SpatiaLite | `django/contrib/gis/db/models/functions.py:NumDimensions` |
| MySQL | New in 5.1: `Collect`; new in 5.2: the lookups `"coveredby"` and `"covers"` | `django/contrib/gis/db/backends/mysql/operations.py:MySQLOperations` |
| MariaDB | New in 6.0, from MariaDB 12.0.1: `Collect`, `GeoHash`, `IsValid` and the lookups `"coveredby"` and `"isvalid"` | `django/contrib/gis/db/backends/mysql/operations.py:MySQLOperations` |
| SpatiaLite | New in Django 5.1, from SpatiaLite 5.1: `BoundingCircle`; new in 6.1: `IsEmpty` and the lookup `"isempty"` | `django/contrib/gis/db/backends/spatialite/operations.py:SpatiaLiteOperations` |
| `OGRGeometry.centroid` | Since 5.1, on every type of geometry | `django/contrib/gis/gdal/geometries.py:OGRGeometry.centroid` |
