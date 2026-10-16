---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Spatial backends: PostGIS, SpatiaLite, MySQL and Oracle

A **spatial backend** is one of the database backends under `django/contrib/gis/db/backends/`, PostGIS, SpatiaLite, MySQL and Oracle: a subclass of the plain backend whose operations, a `BaseSpatialOperations`, answer what a geometry asks of the database, and whose features, schema editor and adapter know its spatial types.

A geometry needs from its database a column type, a way to travel as a parameter, a way back into Python, and names for its functions. GeoDjango keeps each database's answers in a backend, chosen by `"ENGINE"`, and the fields, lookups and functions ask the connection's operations. On the example's plain `"postgres"` alias, a schema editor asked to create the moorings' table raised `AttributeError`, "'DatabaseOperations' object has no attribute 'geo_db_type'" (`django/contrib/gis/db/models/fields.py:BaseSpatialField.db_type`).

## A subclass of the plain backend

Each backend's `base.py` defines a wrapper that subclasses the plain backend's and replaces the classes it makes its helpers from, `BaseDatabaseWrapper.ops_class`, `BaseDatabaseWrapper.features_class`, `BaseDatabaseWrapper.introspection_class` and `BaseDatabaseWrapper.SchemaEditorClass` (`django/contrib/gis/db/backends/postgis/base.py:DatabaseWrapper`) ([The connection object: `BaseDatabaseWrapper` and what a backend provides](../backends/wrapper.md)).

The operations come in two halves: `PostGISOperations` has `BaseSpatialOperations` first among its bases and PostgreSQL's operations second, and every backend's operations and features, over `BaseSpatialFeatures`, are built so (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations`). The spatial half calls `super()` into the plain half: `BaseSpatialOperations.check_expression_support` refuses an aggregate of `BaseSpatialOperations.disallowed_aggregates`, then asks the plain backend, and `BaseSpatialOperations.get_db_converters` adds a geometry's converter to the plain backend's (`django/contrib/gis/db/backends/base/operations.py:BaseSpatialOperations.check_expression_support`) ([The SQL a backend writes: `BaseDatabaseOperations`](../backends/operations.md)).

## `BaseSpatialOperations`: what a backend answers

`BaseSpatialOperations` declares what every spatial backend answers, raising `NotImplementedError` where only the backend can, and flags such as `BaseSpatialOperations.postgis` say which backend it is (`django/contrib/gis/db/backends/base/operations.py:BaseSpatialOperations`).

**The column.** `BaseSpatialOperations.geo_db_type` gives a field's column type. PostGIS writes `"geometry(POINT,4326)"`, with `"Z"` after the type for three dimensions and `"geography"` for a geography field; MySQL writes the type alone, `"POINT"`; Oracle writes `"MDSYS.SDO_GEOMETRY"` for every type; SpatiaLite writes nothing.

**The parameter.** `BaseSpatialField.get_db_prep_value` wraps a geometry in the backend's adapter class, `PostGISOperations.Adapter` and its like ([Spatial fields: the geometry fields and `RasterField`](spatial-fields.md)). `BaseSpatialOperations.get_geom_placeholder_sql`, which PostGIS replaces, writes its placeholder: the constructor from text, `BaseSpatialOperations.from_text`, with the field's SRID, or with the value's inside the transform function when the two differ. Where the features say there is no table of coordinate systems the SRID is left out, which a comment gives as compatibility with MySQL, ticket 27464 (`django/contrib/gis/db/backends/base/operations.py:BaseSpatialOperations.get_geom_placeholder_sql`).

**The way back.** `GeometryField.select_format` wraps a column selected outside a subquery in the template `BaseSpatialOperations.select`: `"ST_AsBinary(%s)"` on MySQL, `"SDO_UTIL.TO_WKBGEOMETRY(%s)"` on Oracle, the bare column on PostGIS under psycopg 3 (`django/contrib/gis/db/models/fields.py:GeometryField.select_format`). The converter from `BaseSpatialOperations.get_geometry_converter` reads the value with GEOS's WKB reader into the field's `GeometryField.geom_class`; MySQL's and Oracle's, which select plain WKB, also set the field's SRID (`django/contrib/gis/db/backends/mysql/operations.py:MySQLOperations.get_geometry_converter`).

**The names.** `BaseSpatialOperations.spatial_function_name` gives a function's name in SQL: the backend's entry in `BaseSpatialOperations.function_names`, else `BaseSpatialOperations.geom_func_prefix` before Django's name, so that on PostGIS `"AsWKT"` became `"ST_AsText"` and `"Centroid"` `"ST_Centroid"`; `BaseSpatialOperations.spatial_aggregate_name` names aggregates. A function in `BaseSpatialOperations.unsupported_functions` is refused with `NotSupportedError`; the base class lists every function there, so a backend supports none it does not claim, and PostGIS's set is empty (`django/contrib/gis/db/backends/base/operations.py:BaseSpatialOperations.spatial_function_name`). The lookups' operators and `BaseSpatialOperations.get_distance`, which turns a distance into the SQL's number, belong to [Spatial lookups, functions and distances](spatial-queries.md).

## `BaseSpatialFeatures`: what each database can do

`BaseSpatialFeatures` sets the GIS flags, among them `BaseSpatialFeatures.gis_enabled`, false on `BaseDatabaseFeatures`, which a raster field checks ([What a database can do: `BaseDatabaseFeatures`](../backends/features.md)). A flag for each function is computed on demand from the unsupported functions, `"has_Centroid_function"` true on PostGIS, and one for a name that is not a function raises `ValueError` (`django/contrib/gis/db/backends/base/features.py:BaseSpatialFeatures.__getattr__`).

| flag | PostGIS | SpatiaLite | MySQL | Oracle |
|---|---|---|---|---|
| `supports_geography` | yes | no | no | no |
| `supports_3d_storage` | yes | yes | no | no |
| `supports_raster` | yes | no | no | no |
| `supports_transform` | yes | yes | no | yes |
| `has_spatialrefsys_table` | yes | yes | no | yes |
| `can_alter_geometry_field` | yes | no | yes | yes |

## PostGIS

`PostGISOperations.spatial_version` is the setting `POSTGIS_VERSION` where it is set, `(3, 5, 2)` in the example. Otherwise it asks the server for `"version()"`, so that a failure of PostgreSQL itself is not blamed on PostGIS (ticket 24862), then for `"postgis_lib_version()"` (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.spatial_version`). `DatabaseWrapper.prepare_database`, which migrate calls, runs `"CREATE EXTENSION IF NOT EXISTS postgis"` where `"pg_extension"` lacks it (`django/contrib/gis/db/backends/postgis/base.py:DatabaseWrapper.prepare_database`) ([The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md)).

A `PostGISAdapter` holds a geometry's EWKB, its WKB with the SRID inside (`django/contrib/gis/db/backends/postgis/adapter.py:PostGISAdapter`). Under psycopg 3, `DatabaseWrapper.register_geometry_adapters` fetches on a new connection the type numbers of `"geometry"`, `"geography"` and `"raster"`, once for each alias, and registers the dumpers `postgis_adapters` makes for them, which send the value typed as one of the three (`django/contrib/gis/db/backends/postgis/base.py:postgis_adapters`). The placeholder is a bare `"%s"`, inside `"ST_Transform"` when the SRIDs differ (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.get_geom_placeholder_sql`). A point of the Grand Harbour in SRID 4326 and in UTM zone 33N, compiled with no server:

```text
Mooring.objects.filter(position__intersects=Point(14.515, 35.8925, srid=4326))
... WHERE ST_Intersects("charts_mooring"."position", %s)
params: (PostGISAdapter,)

Mooring.objects.filter(position__intersects=Point(456229, 3972134, srid=32633))
... WHERE ST_Intersects("charts_mooring"."position", ST_Transform(%s, %s))
params: (PostGISAdapter, 4326)
```

The schema editor gives a field with `BaseSpatialField.spatial_index` a GiST index, with the operator class `"GIST_GEOMETRY_OPS_ND"` for a geometry, not a geography, of three dimensions (`django/contrib/gis/db/backends/postgis/schema.py:PostGISSchemaEditor._create_spatial_index_sql`). For a depth sounding and a shipping lane it wrote, with no server and the key column left out:

```python
# charts/models.py
class Sounding(models.Model):
    position = models.PointField(dim=3)


class Lane(models.Model):
    route = models.LineStringField(geography=True)
```

```text
CREATE TABLE "charts_sounding" (..., "position" geometry(POINTZ,4326) NOT NULL);
CREATE INDEX "charts_sounding_position_0d47193e_id" ON "charts_sounding" USING GIST ("position" GIST_GEOMETRY_OPS_ND);
CREATE TABLE "charts_lane" (..., "route" geography(LINESTRING,4326) NOT NULL);
CREATE INDEX "charts_lane_route_ec6f76d6_id" ON "charts_lane" USING GIST ("route");
```

A geography field in another SRID than 4326 was refused with `NotSupportedError`, "PostGIS only supports geography columns with an SRID of 4326." (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.geo_db_type`). What the backend asks the server, the version without the setting, the extension, a row of `"spatial_ref_sys"`, the run could not ask.

## SpatiaLite

`DatabaseWrapper.get_new_connection` enables extension loading and loads the setting `SPATIALITE_LIBRARY_PATH` where it is set, or else the first that loads of `"mod_spatialite.so"`, `"mod_spatialite"` and what `ctypes.util.find_library` finds (`django/contrib/gis/db/backends/spatialite/base.py:DatabaseWrapper.get_new_connection`). Its `prepare_database` runs `"InitSpatialMetaData(1)"`, or `"InitSpatialMetaDataFull(1)"` from SpatiaLite 5, where `"geometry_columns"` is missing. `SpatialiteSchemaEditor.column_sql` returns no column for a geometry field but collects calls of `"AddGeometryColumn"` and `"CreateSpatialIndex"`, run once the table exists (`django/contrib/gis/db/backends/spatialite/schema.py:SpatialiteSchemaEditor.column_sql`) ([SQLite](../backends/sqlite.md)).

## MySQL and MariaDB

MySQL sends a geometry as WKT in a `WKTAdapter` through `"ST_GeomFromText"`. The two databases differ in operators and functions, among them `"relate"` on MariaDB only and `"covers"` on MySQL only, and MariaDB allows the operator `"coveredby"` and the aggregate `Collect` only from 12.0.1 (`django/contrib/gis/db/backends/mysql/operations.py:MySQLOperations`). A spatial index is made only for a field that is not null, and only where the table's storage engine is MyISAM, Aria or InnoDB (`django/contrib/gis/db/backends/mysql/schema.py:MySQLGISSchemaEditor._field_indexes_sql`) ([MySQL and MariaDB](../backends/mysql.md)).

## Oracle

`SDOOperator` writes most of Oracle's lookups as a function compared with `'TRUE'` (`django/contrib/gis/db/backends/oracle/operations.py:SDOOperator`). The schema editor adds a row to `"USER_SDO_GEOM_METADATA"` for each geometry column, with the field's extent and tolerance, and makes an index of type `"MDSYS.SPATIAL_INDEX"` (`django/contrib/gis/db/backends/oracle/schema.py:OracleGISSchemaEditor.column_sql`). `OracleSpatialAdapter` sends WKT, after turning a polygon's rings to the orientation its docstring says Oracle requires (`django/contrib/gis/db/backends/oracle/adapter.py:OracleSpatialAdapter.__init__`).

## The metadata models and introspection

`BaseSpatialOperations.geometry_columns` and `BaseSpatialOperations.spatial_ref_sys` return two unmanaged models of the app label `"gis"`, over `"geometry_columns"` and `"spatial_ref_sys"` on PostGIS and SpatiaLite, `"USER_SDO_GEOM_METADATA"` and `"CS_SRS"` on Oracle; MySQL has none. The second has `SpatialRefSysMixin`, which makes a GDAL `SpatialReference` from the row's WKT or, failing that, from the PROJ string of a PostGIS or SpatiaLite row, and answers units and spheroid from it (`django/contrib/gis/db/backends/base/models.py:SpatialRefSysMixin.srs`); a field reads its units there, on MySQL from GDAL (`django/contrib/gis/db/models/fields.py:get_srid_info`). Introspection tells the GIS inspectdb a geometry column's type, on Oracle only the generic geometry field, and, where the metadata keeps them, its SRID and dimensions (`django/contrib/gis/db/backends/postgis/introspection.py:PostGISIntrospection.get_geometry_type`) ([GeoDjango's forms, admin, feeds and data tools](gis-extras.md)).
