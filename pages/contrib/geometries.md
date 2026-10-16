---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Geometries in Python: GEOS and GDAL

`GEOSGeometry` and its subclasses for points, lines, polygons and collections are Python objects over GEOS; `OGRGeometry`, `SpatialReference`, `CoordTransform`, `DataSource` and `GDALRaster` are objects over GDAL. GeoDjango reaches both C libraries through ctypes: how it loads them, how a method becomes a call into C, and who frees what C allocated.

GEOS, the Geometry Engine Open Source, is a C++ port of the Java Topology Suite that answers the predicates and operations of the OGC's Simple Features, such as whether one shape contains another. GDAL, the Geospatial Data Abstraction Library, reads and writes geographic data in many formats, vector data through its part called OGR, and transforms coordinates (`docs/ref/contrib/gis/gdal.txt`). In GeoDjango a geometry, the value of a geometry field among them, is a GEOS object ([Spatial fields: the geometry fields and `RasterField`](spatial-fields.md)); GDAL serves coordinate systems, GeoJSON, files and rasters.

Neither is reached through a compiled extension: the documentation calls the GEOS wrapper "a BSD-licensed interface to the GEOS geometry routines, implemented purely in Python using ctypes", usable with no settings or database (`docs/ref/contrib/gis/geos.txt`). Each object is a Python object holding a pointer to a C object, and its methods come down to C functions, each called through a **prototype**: a ctypes function given its argument types, its result type and often a function that checks the result.

## Loading the libraries

GDAL is loaded when `django/contrib/gis/gdal/libgdal.py` is imported. The module takes `GDAL_LIBRARY_PATH` from the settings if it can read them, or else asks ctypes for the library under its names on the platform (on Windows "gdal313" down to "gdal305"), and raises `ImproperlyConfigured` if none is found. It loads the library as `lgdal`, and on Windows also as `lwingdal`, for some OSR routines a comment says are exported with the STDCALL convention, which `std_call` picks; then it sets `GDAL_VERSION` and installs `err_handler`, which logs each error GDAL reports to the logger "django.contrib.gis" (`django/contrib/gis/gdal/libgdal.py`).

`load_geos` finds GEOS the same way, from `GEOS_LIBRARY_PATH` or the names "geos_c" and "libgeos_c-1" on Windows, "geos_c" and "GEOS" on POSIX, but raises `ImportError` when it cannot (`django/contrib/gis/geos/libgeos.py:load_geos`). Its module does not call it: `lgeos` is a `SimpleLazyObject` of it, which loads the library when first asked anything ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)). Importing `django.contrib.gis.geos` asks at once: in a run that wrapped ctypes's loader, it loaded GDAL, which `django/contrib/gis/geos/geometry.py` imports, then GEOS, from the class body of `WKBWriter`, which keeps the library's version as a class attribute (`django/contrib/gis/geos/prototypes/io.py:WKBWriter`). Importing the gdal package loaded GDAL alone.

> **Changed in 6.2.** The oldest libraries supported are GDAL 3.5 and GEOS 3.11.

## One call, from Python to C

`GEOSGeometryBase.contains` passes the two geometries' pointers to `geos_contains` (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.contains`). That is a `BinaryPredicate`, a kind of `GEOSFuncFactory`, which holds what the prototype needs: the C function's name, "GEOSContains", two geometry pointers as argument types, a byte as result and `check_predicate` as check (`django/contrib/gis/geos/prototypes/predicates.py:BinaryPredicate`, `django/contrib/gis/geos/prototypes/predicates.py:UnaryPredicate`). At its first call it makes the prototype and keeps it in `GEOSFuncFactory.func` (`django/contrib/gis/geos/libgeos.py:GEOSFuncFactory`).

What it makes is a `GEOSFunc`. GEOS's thread-safe functions end in `"_r"` and take a context handle before their other arguments (the comment in `GEOSFunc.__init__`); `GEOSFunc` takes GEOSContains_r from `lgeos`, puts the handle's type before the argument types, and at each call passes the calling thread's handle first. The handle, a `GEOSContextHandle`, is made at a thread's first call and kept in a thread-local object; it starts a context with GEOS_init_r, sets the context's notice and error handlers, and ends it with GEOS_finish_r when collected (`django/contrib/gis/geos/prototypes/threadsafe.py:GEOSFunc.__call__`, `django/contrib/gis/geos/prototypes/threadsafe.py:GEOSContextHandle`). In the run, a second thread had no handle until its first call, then its own.

```text figure=the-wrapping
harbour.contains(point)
  |
  v
GEOSGeometryBase.contains   geos_contains(self.ptr, other.ptr): each a C pointer (CPointerBase.ptr)
  |
  v
geos_contains               a BinaryPredicate, a GEOSFuncFactory for "GEOSContains":
                            two geometry pointers in, a byte out, check_predicate as the check;
                            its GEOSFunc made at the first call and kept
  |
  v
GEOSFunc                    GEOSContains_r, from lgeos (load_geos, at first use);
                            first argument: the pointer of this thread's GEOSContextHandle (GEOS_init_r, once a thread)
  |
  v
libgeos_c                   GEOSContains_r(handle, the harbour's pointer, the point's pointer)
  |  a byte
  v
check_predicate             1 -> True, 0 -> False, anything else -> GEOSException
```

*One call of `GEOSGeometryBase.contains`, down to the C function of GEOS and back.*

`check_predicate` turns 1 and 0 into `True` and `False` and raises `GEOSException` for anything else (`django/contrib/gis/geos/prototypes/errcheck.py:check_predicate`). No check learns why: GEOS reports the cause to the context's error handler, which logs it, and the exception names only the C function. Intersecting a self-crossing polygon with a square logged and raised:

```text
log: django.contrib.gis ERROR GEOS_ERROR: TopologyException: side location conflict at 1 1. This can occur if the input geometry is invalid.
raised: GEOSException: Error encountered checking Geometry returned from GEOS C function "GEOSIntersection_r".
```

The GDAL side has no factory and no handle. Its prototypes are made at import, by functions that set the types and the check on the library's own function objects (`django/contrib/gis/gdal/prototypes/generation.py`), and an OGR error code becomes `GDALException`, or `SRSException` for an unsupported coordinate system (`django/contrib/gis/gdal/error.py:check_err`).

## Pointers and who frees them

Every wrapper object that holds a C pointer descends from `CPointerBase`. `CPointerBase.ptr` hands out the pointer kept in `CPointerBase._ptr`, but raises rather than give C a NULL pointer: `GEOSException` on the GEOS side, `GDALException` on the GDAL side (`django/contrib/gis/geos/base.py:GEOSBase`, `django/contrib/gis/gdal/base.py:GDALBase`). When the object is collected, `CPointerBase.__del__` passes the pointer to `CPointerBase.destructor`, GEOSGeom_destroy for a GEOS geometry (`django/contrib/gis/ptr.py:CPointerBase`).

An object whose C object depends on another keeps the other's wrapper alive: a `Layer`, which has no destructor, holds its `DataSource` (`django/contrib/gis/gdal/layer.py:Layer.__init__`), a `Feature` its layer, and a `PreparedGeometry` its geometry, for the crash of ticket #21662 (`django/contrib/gis/geos/prepared.py:PreparedGeometry.__init__`). A ring read from a polygon or a member from a collection is a clone, and so is a copy of a geometry, since a copy sharing the pointer "may contain an invalid pointer location if the original is garbage collected" (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.__copy__`).

## `GEOSGeometry`

`GEOSGeometry` is made from a string of WKT, EWKT, HEXEWKB or GeoJSON, a memoryview of WKB, a pointer, or another geometry, which it clones (`django/contrib/gis/geos/geometry.py:GEOSGeometry.__init__`). A string is matched against regular expressions first, which a comment says keeps malicious input from the C library (`django/contrib/gis/geometry.py`). GeoJSON goes to GDAL, the other strings and WKB to GEOS's readers, one of each kind for each thread, kept in a `ThreadLocalIO`. A reader first counts the geometry collections, nested in WKT and in all in WKB, and refuses more than `MAX_GEOM_COLLECTIONS`, 198, unless `max_geom_collections=` says otherwise; the release notes of 6.0.8 give the reason, a crash in GEOS (`django/contrib/gis/geos/prototypes/io.py:_WKTReader.limit`, `docs/releases/6.0.8.txt`). Then `GEOSGeometryBase.__init__` asks GEOS for the type and sets the object's class to match.

The SRID is kept in the GEOS geometry, 0 meaning none, and an EWKT SRID that differs from the SRID passed with it raises `ValueError`. `==` asks for equal SRIDs and exact equality, coordinate for coordinate (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.__eq__`); `GEOSGeometryBase.equals` is the topological test. `GEOSGeometryBase.transform` goes through GDAL: an `OGRGeometry` made from the WKB is transformed and read back as WKB, in place or, with `clone=True`, as a new geometry (`django/contrib/gis/geos/geometry.py:GEOSGeometryBase.transform`). Measures are in the coordinate system's units, for SRID 4326 degrees:

```text
# a script, with the example's settings; GEOS 3.14.1, GDAL 3.12.4
point = GEOSGeometry("SRID=4326;POINT (14.5219 35.8975)")
harbour = Polygon(((14.51, 35.885), (14.53, 35.885), (14.53, 35.9), (14.51, 35.9), (14.51, 35.885)), srid=4326)

type(point).__name__                        Point
point.json                                  { "type": "Point", "coordinates": [ 14.5219, 35.8975 ] }
point == Point(14.5219, 35.8975)            False
harbour.contains(point)                     True
harbour.area                                0.00030000000000000496
harbour.transform(32633, clone=True).area   3003091.034020336
point.transform(32633, clone=True)          SRID=32633;POINT (456854.1344330215 3972685.35244931)
```

Points, lines and polygons can also be made from coordinates, collections from geometries, and all behave as lists, a point of its coordinates, a polygon of its rings, a collection of its members, through `ListMixin` (`django/contrib/gis/geos/mutable_list.py:ListMixin`). Setting one item of a point or a line changes its coordinates in place; a point or a line whose length changes, and a polygon or a collection on any change to its list, builds a new GEOS geometry from the new list, takes its pointer, keeps the SRID and destroys the old (`django/contrib/gis/geos/linestring.py:LineString._set_single`, `django/contrib/gis/geos/polygon.py:Polygon._set_list`).

## The GDAL side

`OGRGeometry` is GDAL's geometry; a geometry crosses between the libraries as WKB, by `GEOSGeometryBase.ogr` one way and `OGRGeometry.geos` the other (`django/contrib/gis/gdal/geometries.py:OGRGeometry`). A `SpatialReference` is a coordinate system, from an EPSG code, WKT, a PROJ string or a name such as "WGS84", and a `CoordTransform` a transformation between two (`django/contrib/gis/gdal/srs.py:SpatialReference.__init__`). Unless told otherwise, a `SpatialReference` sets GDAL's axis order to `AxisOrder.TRADITIONAL`, x first, so that SRID 4326 reads longitude then latitude; `AxisOrder.AUTHORITY` keeps the authority's order, and the same coordinates name another place:

```text
# the same script
wgs84 = SpatialReference(4326)

wgs84.axis_order                                  <AxisOrder.TRADITIONAL: 0>
the point in 32633, from wgs84                    POINT (456854.134433021 3972685.35244931)
the point in 32633, from AxisOrder.AUTHORITY      POINT (2796641.58902118 1714017.06981988)
```

`DataSource` opens a file of vector data in any format GDAL reads, a `Layer` gives its features, and a `Feature` its geometry and fields, each an instance of the class for its OGR type (`django/contrib/gis/gdal/datasource.py:DataSource`, `django/contrib/gis/gdal/field.py`); `LayerMapping` loads models from them ([GeoDjango's forms, admin, feeds and data tools](gis-extras.md)). A `GDALRaster` is opened from a path, made from a file's bytes, which it writes into GDAL's in-memory file system and removes when collected, or made new from a dictionary, in memory by default (`django/contrib/gis/gdal/raster/source.py:GDALRaster.__init__`). Its `GDALRaster.bands` are `GDALBand` objects, whose `GDALBand.data` reads and writes blocks of pixels.
