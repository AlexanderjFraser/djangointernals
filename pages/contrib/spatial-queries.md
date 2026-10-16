---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Spatial lookups, functions and distances

How GeoDjango compiles a spatial filter, function or distance for a spatial backend: `GISLookup` and the lookups registered on `BaseSpatialField`, the backend's `SpatialOperator` objects, the distance lookups such as `"distance_lte"`, `GeoFunc` and the aggregates, and the measures `D` and `A`.

Whether a mooring lies in an anchorage or within two kilometres of a point is answered by the database's spatial extension, which spells its functions its own way. A filter's words are the same on every backend, and three parties make them SQL: the lookup knows the value's shape, the backend's operations name the SQL and adapt the geometry, and the field knows its SRID and whether its coordinates are degrees. The SQL here was compiled for PostGIS with no server behind it; the row of spatial_ref_sys a distance needs for SRID 4326 was put in GeoDjango's cache from GDAL's definition of it.

## The lookups and the backend's operators

Every spatial lookup is a class registered on `BaseSpatialField`, which the geometry fields and `RasterField` share, and it takes precedence over the base field's lookup of the same name: on a geometry field `"exact"` is `SameAsLookup` and `"contains"` is `ContainsLookup` (`django/contrib/gis/db/models/lookups.py:SameAsLookup`). `Query.build_lookup` finds them through `RegisterLookupMixin.get_lookup` ([The lookup registry: `RegisterLookupMixin`](../querysets/lookups.md)).

`GISLookup` splits a tuple value into the geometry and parameters, which `GISLookup.process_rhs_params` reads, after the pattern of `"relate"`, as a raster's band index, or refuses as too many. The geometry goes through `BaseSpatialField.get_prep_value`, which reads a string as a geometry and gives one without an SRID the field's ([Spatial fields: the geometry fields and `RasterField`](spatial-fields.md)). At compilation `GISLookup.process_rhs` wraps it in the backend's `Adapter` and asks the backend for a placeholder: on PostGIS `%s`, or `"ST_Transform"` to the field's SRID when the geometry's differs (`django/contrib/gis/db/models/lookups.py:GISLookup.process_rhs`, `django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.get_geom_placeholder_sql`).

`GISLookup.as_sql` leaves the SQL to the `SpatialOperator` the backend keeps under the lookup's name in its `gis_operators`, which, says the comment on `GISLookup.get_rhs_op`, may mix the left side into its SQL. It fills a template: its own, the lookup's, or a function of the two sides or the two sides around an operator (`django/contrib/gis/db/backends/utils.py:SpatialOperator.as_sql`). A `PostGISOperator` without `geography` casts a geography column to geometry; one without `raster` makes a raster a polygon (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperator.check_geography`, `django/contrib/gis/db/backends/postgis/operations.py:PostGISOperator.check_raster`).

| kind | lookups | PostGIS writes |
|---|---|---|
| operators | `"bbcontains"`, `"bboverlaps"`, `"left"` and the other comparisons of bounding boxes; `"same_as"`, also `"exact"` | an operator, such as `"&&"` |
| functions | `"contains"`, `"contains_properly"`, `"coveredby"`, `"covers"`, `"crosses"`, `"disjoint"`, `"equals"`, `"intersects"`, `"overlaps"`, `"touches"`, `"within"` | `"ST_Contains"` and the like |
| a pattern | `"relate"` | `"ST_Relate"`, the pattern a third argument |
| distances | `"dwithin"`; `"distance_gt"`, `"distance_gte"`, `"distance_lt"`, `"distance_lte"` | `"ST_DWithin"`; a distance function compared |

`RelateLookup.process_rhs` checks the pattern by the backend operator's own check where there is one (Oracle's masks), else as nine characters from `"012TF*"` (`django/contrib/gis/db/models/lookups.py:RelateLookup.process_rhs`).

```text
Mooring.objects.filter(position__intersects=harbour)
  WHERE ST_Intersects("charts_mooring"."position", %s)
  params: (PostGISAdapter(srid=4326),)
Mooring.objects.filter(position__intersects=point.transform(32633, clone=True))
  WHERE ST_Intersects("charts_mooring"."position", ST_Transform(%s, %s))
  params: (PostGISAdapter(srid=32633), 4326)
Mooring.objects.filter(position__relate=(harbour, "T*F**F***"))
  WHERE ST_Relate("charts_mooring"."position", %s, %s)
  params: (PostGISAdapter(srid=4326), 'T*F**F***')
```

## Distances

A distance lookup's value is a geometry and a distance, optionally with a band index between them and `"spheroid"` after; `DistanceLookupBase.process_rhs_params` refuses a tuple of another length, or of four whose last is not `"spheroid"`, and takes the middle of three for a band index unless the last is `"spheroid"`. The distance may be an expression, compiled; a number, passed as it is, in the field's units by the code's comment; or a `Distance` measure of `django/contrib/gis/measure.py`, which `PostGISOperations.get_distance` gives in metres for a geography or geodetic column, and for a projected one in the units its spatial_ref_sys row names (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.get_distance`).

`"dwithin"` has an operator, `"ST_DWithin"`, the distance its third argument, and `get_distance` refuses it a measure on a geodetic geometry column; the documentation says to give a geographic field's distance in its units, degrees for WGS84 (`docs/ref/contrib/gis/geoquerysets.txt`).

The distance comparisons use no operator. `DistanceLookupFromFunction.as_sql` builds the `Distance` function of the column and the geometry through the backend's `distance_expr_for_lookup`, compiles it, and compares it with the distance (`django/contrib/gis/db/models/lookups.py:DistanceLookupFromFunction.as_sql`, `django/contrib/gis/db/models/functions.py:Distance.as_postgresql`). So a lookup and an annotation write the same SQL, and the function chooses what measures:

```text figure=one-lookup
Mooring.objects.filter(position__distance_lte=(point, D(km=2)))    point: SRID 4326

when the filter is added
  Query.build_lookup: "distance_lte"
    RegisterLookupMixin.get_lookup on the PointField: DistanceLTELookup
    GISLookup.__init__: the point, and the parameters [D(km=2)]
      BaseSpatialField.get_prep_value: the point, SRID 4326
      DistanceLookupBase.process_rhs_params: a pair, no band index

when the query is compiled
  DistanceLookupFromFunction.as_sql
    PostGISOperations.distance_expr_for_lookup: Distance(position, point),
        the point a Value of GeometryField(srid=4326)
    Distance.as_postgresql
      BaseSpatialField.geodetic: the row of spatial_ref_sys for 4326 is geographic
      spatial_function_name("DistanceSphere"): "ST_DistanceSphere"
      Value.as_sql
        BaseSpatialField.get_db_prep_value: a PostGISAdapter of the point
        PostGISOperations.get_geom_placeholder_sql: the Value's field's SRID, so %s
    DistanceLookupBase.process_distance
      PostGISOperations.get_distance: geodetic, so D(km=2).m, 2000.0
    the function, "<=", the distance

ST_DistanceSphere("charts_mooring"."position", %s) <= %s
params: (PostGISAdapter(srid=4326), 2000.0)
```

*A distance lookup compiled for PostGIS: its class is found when the filter is added; the SQL function, the placeholder and the distance's units are settled at compilation.*

```text
Mooring.objects.filter(position__dwithin=(point, 0.02))
  WHERE ST_DWithin("charts_mooring"."position", %s, %s)
  params: (PostGISAdapter(srid=4326), 0.02)
Mooring.objects.filter(position__dwithin=(point, D(km=2)))
  raises ValueError: Only numeric values of degree units are allowed on geographic DWithin queries.
```

## Functions: `GeoFunc`

`GeoFunc` is `Func` with `GeoFuncMixin` in front, whose `GeoFuncMixin.geom_param_pos` says which arguments are geometries (`django/contrib/gis/db/models/functions.py:GeoFuncMixin`). A geometry given as a value must have an SRID, and becomes a `Value` with a `GeometryField` of that SRID, compiled through the field's adapter and placeholder. At resolution each geometric argument must be a geometry field, and one after the first in another SRID is wrapped in `Transform` to the first's, "so objects are comparable" (`django/contrib/gis/db/models/functions.py:GeoFuncMixin.resolve_expression`). `BaseSpatialOperations.spatial_function_name` gives the SQL name: the backend's own for the class where it has one, else its prefix, `"ST_"` on PostGIS, before the class's name; or `NotSupportedError` ([Spatial backends: PostGIS, SpatiaLite, MySQL and Oracle](spatial-backends.md)).

`Distance.as_postgresql` matches the second argument's type, geography or geometry, to the field's, takes `"ST_DistanceSphere"` for a geodetic geometry column, or with `spheroid=True` `"ST_DistanceSpheroid"` and the field's spheroid, and otherwise `"ST_Distance"` (`django/contrib/gis/db/models/functions.py:Distance.as_postgresql`). `Area` refuses a geodetic field where the backend lacks `supports_area_geodetic`; `Transform` declares a geometry field of its SRID its output (`django/contrib/gis/db/models/functions.py:Transform.__init__`).

| returns | functions |
|---|---|
| a geometry, in the first argument's SRID | `BoundingCircle`, `Centroid`, `ClosestPoint`, `Difference`, `Envelope`, `ForcePolygonCW`, `Intersection`, `MakeValid`, `PointOnSurface`, `Reverse`, `Rotate`, `Scale`, `SnapToGrid`, `SymDifference`, `Translate`, `Union` |
| a geometry in the SRID given | `Transform`, `FromWKB`, `FromWKT` |
| a measure | `Distance`, `Length`, `Perimeter`: a distance; `Area`: an area |
| text | `AsGeoJSON`, `AsGML`, `AsKML`, `AsSVG`, `AsWKT`, `GeoHash`, `GeometryType` |
| bytes | `AsWKB` |
| a number | `Azimuth`, `GeometryDistance`, `LineLocatePoint`, `MemSize`, `NumDimensions`, `NumGeometries`, `NumPoints` |
| a boolean | `IsEmpty`, `IsValid` |

*The functions of `django/contrib/gis/db/models/functions.py`, by what they return. `GeometryType`, `IsEmpty`, `IsValid` and `NumDimensions` are also transforms of the spatial fields, `"geom_type"`, `"isempty"`, `"isvalid"` and `"num_dimensions"`.*

```text
Mooring.objects.annotate(d=Distance("position", point)).order_by("d")
  SELECT ..., ST_DistanceSphere("charts_mooring"."position", %s) AS "d" FROM "charts_mooring" ORDER BY 5 ASC
Mooring.objects.annotate(d=Distance("position", point.transform(32633, clone=True)))
  SELECT ..., ST_DistanceSphere("charts_mooring"."position", ST_Transform(%s, %s)) AS "d" FROM "charts_mooring"
```

## Aggregates

`GeoAggregate` is an `Aggregate` of spatial fields only, named by the backend's `spatial_aggregate_name` once `check_expression_support` has refused any in its `disallowed_aggregates`, as Oracle refuses `Collect`, `Extent3D` and `MakeLine` (`django/contrib/gis/db/models/aggregates.py:GeoAggregate`). `Collect`, `MakeLine` and `Union` return a geometry; `Extent` and `Extent3D` a box, which `convert_extent` or `convert_extent3d` makes a tuple of four or six numbers ([Aggregates: `Aggregate`, `Count` and `get_aggregation`](../sql/aggregates.md)).

## Measures: `D` and `A`

`Distance` and `Area` of `django/contrib/gis/measure.py`, shortened `D` and `A`, need no database. Their base, `MeasureBase`, keeps one number in a standard unit, metres or square metres, and a unit to show it in. Keyword arguments are converted and summed, each unit found by its name, by an alias such as a spatial reference system's "metre", or lower-cased; an unknown one raises `AttributeError` (`django/contrib/gis/measure.py:MeasureBase.default_units`). Measures of one class add, subtract and compare, a number multiplies or divides one, a distance times a distance is an area, and a result shows the unit of its first measure (`django/contrib/gis/measure.py:Distance.__mul__`).

`DistanceField` and `AreaField`, the output fields of the measuring functions, make the database's number a measure in the unit the backend names, and leave it a number where none is named. `BaseSpatialOperations.get_distance_att_for_field` names a distance's: metres on a geodetic field if the backend measures one, the field's units on a projected one (`django/contrib/gis/db/models/sql/conversion.py:DistanceField.from_db_value`).

```text
D(km=2).m -> 2000.0
D(km=2) + D(nm=1) -> Distance(km=3.852)
D(km=2) * D(m=500) -> Area(sq_km=1.0)
D(km=2) + 5 raises TypeError: Distance must be added with Distance
```
