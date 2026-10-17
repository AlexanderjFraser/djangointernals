"""The habits of the section "What changed in GeoDjango", release by release: what an old use of
GeoDjango's GDAL wrappers (an OGRGeometry's dimension, a DataSource's date and time), of GeoIP2
and of the map widgets returns or raises. Run by recordings/changes.py under each release;
_run.py says how a habit is written.

GeoDjango needs GDAL and GEOS, which Django loads from the paths its settings give. They are
taken from the wheel of pyogrio 0.13.0, GDAL 3.12.4 with the GEOS 3.14.1 it is built with,
which recordings/requirements.txt installs beside each release: from pyogrio.libs/ beside the
pyogrio of the Python that runs this (on Windows, as here, its DLLs), with pyogrio's proj_data
and gdal_data. The module stops if that Python has no pyogrio 0.13.0, so that every release
reads with the same GDAL. GeoJSON has no type for a date: it is GDAL's GeoJSON driver that
reads the string "2026-10-17T10:00:30.250" as a field of type OFTDateTime, under every release
alike. No geoip2 library and no database of GeoIP2's are installed, so GeoIP2 is read on its
class and never made. django.contrib.gis is among the applications, so that the widgets find
their templates. The default database is SQLite in memory, as _run.py configures it.

The module writes into a temporary directory of its own run, which no line names: seen.geojson,
a feature whose property "seen" is the string of a date and a time with milliseconds.
"""
import atexit
import glob
import importlib.metadata
import importlib.util
import os
import tempfile

from _run import BASE, configure, habit, main


def _geolibs() -> str:
    """The site-packages directory of pyogrio 0.13.0 in the Python that runs this."""
    spec = importlib.util.find_spec("pyogrio")
    root = os.path.dirname(os.path.dirname(spec.origin)) if spec and spec.origin else ""
    if (not root or importlib.metadata.version("pyogrio") != "0.13.0"
            or not glob.glob(os.path.join(root, "pyogrio.libs", "gdal-*.dll"))):
        raise SystemExit("geodjango.py: no GDAL; install pyogrio 0.13.0 (recordings/requirements.txt) "
                         "in the Python that runs this")
    return root


GEOLIBS = _geolibs()
LIBS = os.path.join(GEOLIBS, "pyogrio.libs")
DLL_DIRECTORY = os.add_dll_directory(LIBS)  # kept: the directory is searched while the handle is open
os.environ["PROJ_DATA"] = os.path.join(GEOLIBS, "pyogrio", "proj_data")
os.environ["GDAL_DATA"] = os.path.join(GEOLIBS, "pyogrio", "gdal_data")

SCRATCH = tempfile.TemporaryDirectory()
atexit.register(SCRATCH.cleanup)


def write(path, text):
    path = os.path.join(SCRATCH.name, *path.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


write("seen.geojson", '''\
{"type": "FeatureCollection", "features": [
  {"type": "Feature", "properties": {"seen": "2026-10-17T10:00:30.250"},
   "geometry": {"type": "Point", "coordinates": [14.51, 35.89]}}
]}
''')

configure(
    INSTALLED_APPS=BASE["INSTALLED_APPS"] + ["django.contrib.gis"],
    GDAL_LIBRARY_PATH=glob.glob(os.path.join(LIBS, "gdal-*.dll"))[0],
    GEOS_LIBRARY_PATH=glob.glob(os.path.join(LIBS, "geos_c-*.dll"))[0],
)


@habit("OGRGeometry(\"POINT (1 2)\").coord_dim = 3")
def coord_dim_setter():
    from django.contrib.gis.gdal import OGRGeometry

    point = OGRGeometry("POINT (1 2)")
    point.coord_dim = 3
    return f"coord_dim is {point.coord_dim}"


@habit("DataSource(\"seen.geojson\")[0][0][\"seen\"].value: a property written \"2026-10-17T10:00:30.250\"")
def datetime_field_value():
    from django.contrib.gis.gdal import DataSource

    source = DataSource(os.path.join(SCRATCH.name, "seen.geojson"))
    return repr(source[0][0]["seen"].value)


@habit("DataSource(\"seen.geojson\")[0][0][\"seen\"].as_datetime()[5].value: the seconds of \"2026-10-17T10:00:30.250\"")
def datetime_field_seconds():
    from django.contrib.gis.gdal import DataSource

    source = DataSource(os.path.join(SCRATCH.name, "seen.geojson"))
    return repr(source[0][0]["seen"].as_datetime()[5].value)


@habit("GeoIP2.coords: the method read on the class")
def geoip2_coords():
    from django.contrib.gis.geoip2 import GeoIP2

    return GeoIP2.coords.__qualname__


@habit("OpenLayersWidget().render(\"position\", None, attrs={\"id\": \"id_position\"}): the opening tag of each script element")
def widget_scripts():
    import re

    from django.contrib.gis.forms.widgets import OpenLayersWidget

    html = OpenLayersWidget().render("position", None, attrs={"id": "id_position"})
    return repr(re.findall(r"<script[^>]*>", html))


@habit("OpenLayersWidget().media.render_js(): the OpenLayers script")
def widget_openlayers():
    from django.contrib.gis.forms.widgets import OpenLayersWidget

    return next(tag for tag in OpenLayersWidget().media.render_js() if "/ol@" in tag)


main()
