---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# GeoDjango's forms, admin, feeds and data tools

How a geometry enters and leaves Django other than through a query: GeoDjango's geometry form fields and their map widgets, `OpenLayersWidget` and `OSMWidget`; `GISModelAdmin`; the `"geojson"` serializer; GeoRSS feeds and KML sitemaps; and ogrinspect and `LayerMapping`, which turn a file of geographic data into a model and its rows.

Each is a thin layer over the machinery it extends, most over GEOS and GDAL too ([Geometries in Python: GEOS and GDAL](geometries.md)). Several settle a question of coordinate systems: the form field, the serializer, the KML views and `LayerMapping` decide which SRID a geometry arrives in and transform it to the one wanted; the feeds write coordinates as they find them. The runs use the charts application's moorings ([Content types, static files and the other contrib apps](../contrib.md)), unsaved.

## The geometry form fields

`django.contrib.gis.forms` is all of `django.forms` and, beside it, the map widgets and a form field for each kind of geometry: `django.contrib.gis.forms.fields.GeometryField` and its subclasses, `PointField` and the rest, differing only in `geom_type` (`django/contrib/gis/forms/fields.py:GeometryField`). A model's geometry field makes its own, passing its kind, its SRID and `max_geom_collections`, a limit on nested collections that keeps hostile input from crashing GEOS (`django/contrib/gis/db/models/fields.py:GeometryField.formfield`).

`GeometryField.to_python` has the widget's `deserialize` read the text or, without one, `GEOSGeometry`, which takes WKT, EWKT, HEXEWKB and GeoJSON; text that cannot be read is "Invalid geometry value." A geometry without an SRID is given the widget's `map_srid` or, for a widget without one, the field's own SRID. `GeometryField.clean` refuses a geometry of the wrong kind, unless the field is the general `"GEOMETRY"`, and transforms one in another SRID into the field's.

The default widget, `OpenLayersWidget`, has a `map_srid` of 3857, whose units are metres, so WKT without an SRID that did not come from the map, a test's or an API's, is read as metres from the map's origin. GeoJSON goes the same way, the widget giving it the map's SRID too. Under a `Textarea`, which has no map, the field's SRID applies:

```text
# a run: forms.PointField(srid=4326).clean(value)
"POINT(14.5167 35.8989)"            -> SRID=4326;POINT (0.0001304057348498 0.0003224853055223)
"SRID=4326;POINT(14.5167 35.8989)"  -> SRID=4326;POINT (14.5167 35.8989)
# the same field with widget=Textarea
"POINT(14.5167 35.8989)"            -> SRID=4326;POINT (14.5167 35.8989)
```

`GeometryField.has_changed` transforms the submitted geometry into the initial one's SRID and compares the two with `equals_exact` at a tolerance of 0.000001: an initial value not drawn in the browser, the comment says, may come back slightly different the first time it is saved.

## The map widgets

`BaseGeometryWidget` keeps its options, `base_layer`, `geom_type`, `map_srid` and `display_raw`, as class attributes, copied into the widget's `attrs` when it is made (`django/contrib/gis/forms/widgets.py:BaseGeometryWidget`). `BaseGeometryWidget.get_context` transforms a geometry in another SRID into the map's, on an OGR copy, leaving the instance's value alone, and serializes it. `OpenLayersWidget` writes GeoJSON, has `base_layer` `"nasaWorldview"` and `map_srid` 3857, and takes as media OpenLayers 10.9, from a CDN, and "gis/js/OLMapWidget.js"; `OSMWidget` has `"osm"` and a default centre and zoom ([Widgets: `Widget` and its subclasses](../forms/widgets.md)). For the Ricasoli buoy, the widget rendered a hidden textarea of GeoJSON in metres and, for the script, its options:

```text
<script id="id_position_mapwidget_options" type="application/json">{"base_layer": "nasaWorldview", "geom_type": "POINT", "map_srid": 3857, "display_raw": false, "required": true, "id": "id_position", "geom_name": "Point"}</script>
```

Nothing there runs. The widget's script, once the document has loaded, builds every map but the empty form's, and on each `"formset:added"` event the maps of the form added, each from its options and on the base layer `base_layer` names, or OpenStreetMap. It reads the textarea as GeoJSON and writes changes back the same way, naming no projection (`django/contrib/gis/static/gis/js/OLMapWidget.js`); and `OpenLayersWidget.deserialize` reads GeoJSON in the map's SRID, where GeoJSON, its comment says, assumes 4326. Posted back unchanged, the value cleaned to within 0.000001 of the buoy's point, and `has_changed` saw no change.

> **Changed in 6.0.** The widgets render without inline JavaScript, and `BaseGeometryWidget.base_layer` is new.

## In the admin: `GISModelAdmin`

`GISModelAdmin` is `ModelAdmin` behind `GeoModelAdminMixin`, whose `formfield_for_dbfield` gives a geometry field of two dimensions, or of three if `supports_3d` allows, the model field's own form field with the widget `gis_widget`, `OSMWidget` by default, made with `gis_widget_kwargs` (`django/contrib/gis/admin/options.py:GeoModelAdminMixin.formfield_for_dbfield`). Other fields go the way of [The admin's forms: `get_form` and `formfield_for_dbfield`](../admin/admin-forms.md#one-form-field-formfield_for_dbfield), which such a geometry field skips: in a run, a `formfield_overrides` entry for `django.contrib.gis.db.models.PointField` gave a plain `ModelAdmin` a `Textarea`, and `GISModelAdmin` still an `OSMWidget`.

## GeoJSON out: the `"geojson"` serializer

`GISConfig.ready` adds the format to `BUILTIN_SERIALIZERS` (`django/contrib/gis/apps.py:GISConfig.ready`). Its serializer is the JSON one with three more options, geometry_field, id_field and srid, which is 4326 unless given. It writes a FeatureCollection, and for each instance a Feature whose `"id"` is the key or id_field's value, whose `"properties"` are the other fields, with the key as `"pk"` unless a fields list leaves it out, and whose `"geometry"` is the first geometry field's, or geometry_field's, transformed into srid (`django/contrib/gis/serializers/geojson.py:Serializer.get_dump_object`). The deserializer raises `SerializerDoesNotExist` as it is made ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](../services/serializers.md)).

In a run the transform changed the instance's own geometry: after a dump with `srid=3857`, the buoy's position was in SRID 3857. And the geometry is read only from a field that is serialized, so `fields=["name"]` gave `"geometry": null` until geometry_field named the position, which adds it to the fields.

## GeoRSS and W3C Geo feeds

`django/contrib/gis/feeds.py:Feed` is `django.contrib.syndication.views.Feed` with `GeoRSSFeed` as its generator and two more dynamic attributes, `"geometry"` for the feed and `"item_geometry"` for each item, which `Feed.feed_extra_kwargs` and `Feed.item_extra_kwargs` hand to the generator ([Feeds: `django.contrib.syndication` and the feed generator](feeds.md)). `GeoRSSFeed` and `GeoAtom1Feed` are RSS 2.0 and Atom with the GeoRSS namespace, `W3CGeoFeed` RSS 2.0 with the W3C's. `GeoFeedMixin.add_georss_element` writes the element: two numbers are a point, four or two pairs a box; a geometry may be a point, a line string or ring, or a polygon, of which only the exterior ring is written; anything else is a `ValueError`, as is a box or any geometry but a point in a W3C feed. Nothing is transformed: x is written as the longitude and y as the latitude, latitude first, whatever the SRID.

```text
# a run: a feed's box (14.50, 35.87, 14.53, 35.90) and the buoy's point, as written
<georss:box>35.870000 14.500000 35.900000 14.530000</georss:box>
<georss:point>35.897500 14.522500</georss:point>
```

## KML sitemaps and views

`KMLSitemap` lists geometry fields, not objects: triples of an application label, a model name and a field name, from the models or triples given or, by default, from every geometry field of every installed model (`django/contrib/gis/sitemaps/kml.py:KMLSitemap`). Each location is reversed from a URL pattern the project must name after the view's dotted path, `"django.contrib.gis.sitemaps.views.kml"` or its kmz twin ([Sitemaps: `Sitemap` and the sitemap views](sitemaps.md)). The view `kml` has the database write each geometry's KML when the backend has the function `AsKML`, and otherwise has it transform to 4326 where the backend can and asks each geometry for its `kml`. It renders "gis/kml/placemarks.kml" with `render_to_kml`, as "application/vnd.google-earth.kml+xml", or with `render_to_kmz`, which zips it as "doc.kml" (`django/contrib/gis/sitemaps/views.py:kml`, `django/contrib/gis/shortcuts.py:compress_kml`).

## Loading data: ogrinspect and `LayerMapping`

GDAL reads a file of geographic data, a shapefile or GeoJSON, as a `DataSource` of layers of features, each with the layer's fields and a geometry. ogrinspect writes a model for a layer, each OGR field type mapped to a model field type with the layer's widths, and a geometry field of the layer's type, with the layer's SRID, or -1 if it has none, unless that is 4326, the default (`django/contrib/gis/utils/ogrinspect.py:_ogrinspect`); `--mapping` adds the dictionary `LayerMapping` wants (`django/contrib/gis/management/commands/ogrinspect.py:Command.handle`). GDAL gave every field of the run's GeoJSON layer a width of 0, so the model is a draft:

```text
# a run: ogrinspect moorings.geojson Mooring --mapping --decimal=Depth, the model it printed
class Mooring(models.Model):
    name = models.CharField(max_length=0)
    depth = models.DecimalField(max_digits=0, decimal_places=0)
    berths = models.IntegerField()
    geom = models.PointField()
```

`LayerMapping` saves a layer's features as rows (`django/contrib/gis/utils/layermapping.py:LayerMapping`). Its mapping goes from each model field to an OGR field, to a geometry type for the geometry field, or, for a foreign key, to a dictionary that finds the related row. `LayerMapping.check_layer` checks the mapping against the layer's description before any feature is read, and raises `LayerMapError` for a field missing on either side, types `LayerMapping.FIELD_TYPES` does not pair, or geometry types that differ, unless a field of a multi type meets its single type. Unless `transform=False` or the backend cannot transform, as MySQL's cannot, it then queries the database's spatial_ref_sys for the field's coordinate system, as the object is made. `LayerMapping.feature_kwargs` turns each feature into the model's arguments, the geometry made two-dimensional if the field is, wrapped in its multi type where needed, transformed, and written as WKT: for the buoy, untransformed, `{'name': 'Ricasoli buoy', 'depth': Decimal('12.5'), 'position': 'POINT (14.5225 35.8975)'}`.

`LayerMapping.save` saves an instance of each; a feature that fails is reported, unless `silent=True`, and skipped, unless `strict=True`. In the default mode, "commit_on_success", the load is one `atomic` block of the default database, whichever database it writes to (`django/db/transaction.py:atomic`); with `step=1000`, each thousand features are one, the last taking the rest; "autocommit" uses none. Given unique fields, it adds each feature's geometry to the collection of the row they find, if any, and forces "autocommit".

`add_srs_entry` adds a coordinate system GDAL knows to the spatial_ref_sys of PostGIS or SpatiaLite, if no row has its SRID (`django/contrib/gis/utils/srs.py:add_srs_entry`); GeoDjango's inspectdb asks the backend's introspection for each geometry column's type and, except on MySQL, its SRID (`django/contrib/gis/management/commands/inspectdb.py:Command.get_field_type`) ([The commands Django ships](../commands/builtin.md)).

## Locating an address: `GeoIP2`

`GeoIP2` reads a country or city database of MaxMind's or DB-IP's with the geoip2 package (`django/contrib/gis/geoip2.py:GeoIP2`). It opens one file: the path given, or `GEOIP_PATH`, if that is a file, else the city database in that directory, else the country one; a database of an unknown kind raises `GeoIP2Exception`. `GeoIP2.country` and `GeoIP2.city`, which needs a city database, answer a dictionary for an IP address or a host name, and `GeoIP2.geos` a GEOS point in SRID 4326.

```runtime-names
GEOIP_PATH    django/contrib/gis/geoip2.py:GeoIP2.__init__    # a setting a project makes, read with getattr
```
