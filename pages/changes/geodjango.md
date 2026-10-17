---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in GeoDjango

The changes from Django 5.0 to this commit in GeoDjango, `django.contrib.gis`: the map widgets and `BaseGeometryWidget.base_layer`, `OGRGeometry`'s Z and M dimensions and curves, `DataSource`'s milliseconds, `GeoIP2`, and new spatial functions and lookups.

Since 6.0 the map widgets write no JavaScript into the page: the script they load makes the map from options given as data. 5.1 told `OGRGeometry`'s Z and M dimensions apart and 5.2 gave it curves, which GeoDjango's GEOS side cannot hold, and 6.0 removed the old way of setting a dimension. 6.2 has a `DataSource` keep the milliseconds of dates and times, which 6.1.1 dropped. `GeoIP2` has opened one database since 5.1.

GeoDjango's security fixes, for rasters and for nested geometry collections, are in [Security fixes: SQL injection](security-fixes-sql.md), [Security fixes: disclosure, spoofing and privilege](security-fixes-exposure.md) and [Security fixes: limits against denial of service](security-fixes-limits.md); the oldest GDAL, GEOS and PostGIS by release, in [The versions Django needs: Python, databases and libraries](requirements.md).

## The map widgets: options as data, and `base_layer`

Until 6.0 the map widgets, `OpenLayersWidget` and `OSMWidget`, wrote their script into the page. Under 5.2.17 gis/openlayers.html ended in a `<script>` with two blocks, base_layer and options, which made the base layer and the map's options; the script then made the map from them. `OSMWidget`'s gis/openlayers-osm.html filled the two blocks. Since 6.0 `BaseGeometryWidget.get_context` leaves the options in the widget's attrs, which the template writes as JSON into a `<script type="application/json">`, and the widget's script, OLMapWidget.js, builds each map from them (`django/contrib/gis/forms/widgets.py:BaseGeometryWidget.get_context`, `django/contrib/gis/static/gis/js/OLMapWidget.js`; [GeoDjango's forms, admin, feeds and data tools](../contrib/gis-extras.md#the-map-widgets)). `BaseGeometryWidget.base_layer` (6.0) names a layer builder in the script's MapWidget.layerBuilder: `"nasaWorldview"` for `OpenLayersWidget`, `"osm"` for `OSMWidget`, which now renders the same template. A project's own script can add a builder there; a name not there gives OpenStreetMap. Each line lists the opening tags of the script elements a widget renders; look for their type:

```text recording=changes
OpenLayersWidget().render("position", None, attrs={"id": "id_position"}): the opening tag of each script element
    5.2.17       ['<script>']
    6.0.8        ['<script id="id_position_mapwidget_options" type="application/json">']
    6.1.1        ['<script id="id_position_mapwidget_options" type="application/json">']
    this commit  ['<script id="id_position_mapwidget_options" type="application/json">']
```

> **Trap.** Since 6.0 no widget of Django's renders a project's own gis/openlayers-osm.html, and a template that extends gis/openlayers.html and fills base_layer or options renders without them: the blocks are gone, and nothing warns.

Since 6.1 `OpenLayersWidget` loads OpenLayers 10.9.0, where it loaded 7.2.2 (`docs/releases/6.1.txt`, `django/contrib/gis/forms/widgets.py:OpenLayersWidget`). 5.0 removed the admin's GeoModelAdmin, OSMGeoAdmin and django.contrib.gis.admin.OpenLayersWidget, leaving `GISModelAdmin` (`django/contrib/gis/admin/options.py:GISModelAdmin`); 5.1 removed `BaseGeometryWidget`'s map_width and map_height.

## GDAL's geometries: Z, M and curves

`OGRGeometry`, GDAL's geometry in GeoDjango, knew a geometry's coordinate dimension only as `OGRGeometry.coord_dim`, which could be set. 5.1 told the Z and M dimensions apart: `OGRGeometry.is_3d` and `OGRGeometry.is_measured` read them, `OGRGeometry.set_3d` and `OGRGeometry.set_measured` add or drop them, and points and lines give their M coordinates (`django/contrib/gis/gdal/geometries.py:OGRGeometry.set_measured`). 5.1 deprecated setting coord_dim, and 6.0 removed the setter. The block sets a point's third dimension the old way:

```text recording=changes
OGRGeometry("POINT (1 2)").coord_dim = 3
    5.2.17       coord_dim is 3, warns RemovedInDjango60Warning
    6.0.8        AttributeError: property 'coord_dim' of 'Point' object has no setter
    6.1.1        AttributeError: property 'coord_dim' of 'Point' object has no setter
    this commit  AttributeError: property 'coord_dim' of 'Point' object has no setter
```

5.2 added the curved geometries, `CircularString`, `CompoundCurve`, `CurvePolygon`, `MultiCurve` and `MultiSurface`, with `OGRGeometry.has_curve`, `OGRGeometry.get_linear_geometry` and `OGRGeometry.get_curve_geometry`. GeoDjango's GEOS classes have none for curves: the curved ones set `OGRGeometry.geos_support` false, and their `OGRGeometry.geos` raises `GEOSException` (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.__init__`, `django/contrib/gis/gdal/geometries.py:OGRGeometry.geos`). Since 5.1 every geometry has `OGRGeometry.centroid`, the notes say. `GEOSGeometryBase.equals_identical` (5.0) compares geometries point by point and `GEOSGeometryBase.hasm` (6.0) reads the M dimension; both need GEOS 3.12 (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.hasm`; [Geometries in Python: GEOS and GDAL](../contrib/geometries.md#the-gdal-side)).

## `DataSource`: dates and times keep their milliseconds

A `DataSource` gives date-time and time fields as `OFTDateTime` and `OFTTime`, whose values come from `Field.as_datetime`, which until 6.2 asked GDAL for whole seconds, into a `ctypes.c_int`. At this commit it calls GDAL's OGR_F_GetFieldAsDateTimeEx, whose seconds are a `ctypes.c_float`, and the two properties round the fraction to milliseconds (`django/contrib/gis/gdal/field.py:Field.as_datetime`, `django/contrib/gis/gdal/field.py:OFTDateTime.value`). The block reads a GeoJSON property written "2026-10-17T10:00:30.250", which GDAL reads as a date and time; this commit's line keeps its milliseconds, as 250000 microseconds:

```text recording=changes
DataSource("seen.geojson")[0][0]["seen"].value: a property written "2026-10-17T10:00:30.250"
    5.2.17       datetime.datetime(2026, 10, 17, 10, 0, 30)
    6.0.8        datetime.datetime(2026, 10, 17, 10, 0, 30)
    6.1.1        datetime.datetime(2026, 10, 17, 10, 0, 30)
    this commit  datetime.datetime(2026, 10, 17, 10, 0, 30, 250000)
```

Nothing warns. `as_datetime` itself gives seconds of 30.25 at this commit, where 6.1.1 gave 30, which the 6.2 notes list as backwards incompatible (`docs/releases/6.2.txt`).

## `GeoIP2`: one database, and the old methods gone

Until 5.1 `GeoIP2`, given a directory, opened both its city and country databases, the 5.1 notes say, the country one being "a subset of the city database" (`docs/releases/5.1.txt`). Since then `GeoIP2.__init__` opens one: the path itself if it is a file, else the city database in it, else the country one (`django/contrib/gis/geoip2.py:GeoIP2.__init__`). `GeoIP2.country` reads whichever is open; `GeoIP2.city` refuses a country database.

The methods coords and open, deprecated in 5.1 for `GeoIP2.lon_lat` and the constructor, went in 6.0 ([GeoDjango's forms, admin, feeds and data tools](../contrib/gis-extras.md#locating-an-address-geoip2)).

## Functions, lookups and backends

Each spatial function and lookup added since 5.0, or brought to more databases, by name ([Spatial lookups, functions and distances](../contrib/spatial-queries.md)):

| what | at this commit | release | where |
|---|---|---|---|
| `ClosestPoint` | the point of a geometry nearest another; PostGIS and SpatiaLite | 5.0 | `django/contrib/gis/db/models/functions.py:ClosestPoint` |
| the spatial aggregates | take `filter=` | 5.0 | `django/contrib/gis/db/models/aggregates.py:GeoAggregate` |
| `FromWKB`, `FromWKT` | an SRID, which Oracle ignores | 5.1 | `django/contrib/gis/db/models/functions.py:FromWKB` |
| `django.contrib.gis.measure.Area` | the unit `"ha"` | 5.1 | `django/contrib/gis/measure.py:Area` |
| `Rotate` | a geometry turned about the origin or a point; PostGIS only | 6.0 | `django/contrib/gis/db/models/functions.py:Rotate` |
| `GeometryType`, `"geom_type"` | a geometry's type; on Oracle from 23 | 6.0 | `django/contrib/gis/db/models/functions.py:GeometryType` |
| `NumDimensions`, `"num_dimensions"` | a geometry's number of dimensions; PostGIS and SpatiaLite | 6.1 | `django/contrib/gis/db/models/functions.py:NumDimensions` |
| `Collect`, `"coveredby"`, `"covers"`, `GeoHash`, `IsValid`, `"isvalid"` | on MySQL `Collect` (5.1), `"coveredby"` and `"covers"` (5.2); on MariaDB from 12.0.1 all but `"covers"` (6.0) | 5.1 to 6.0 | `django/contrib/gis/db/backends/mysql/operations.py:MySQLOperations` |
| `BoundingCircle`, `IsEmpty`, `"isempty"` | on SpatiaLite: `BoundingCircle` from SpatiaLite 5.1 (Django 5.1), `IsEmpty` and `"isempty"` (6.1) | 5.1, 6.1 | `django/contrib/gis/db/backends/spatialite/operations.py:SpatiaLiteOperations` |
