---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The versions Django needs: Python, databases and libraries

The oldest Python, database server and library that each release from Django 5.0 to this commit supports, and where the code at this commit holds a project to each floor: `BaseDatabaseFeatures.minimum_database_version`, checked as a connection opens; the versions of the PostgreSQL and MySQL drivers, checked as their backend is imported; and `pyproject.toml`, which only an installer reads.

The code enforces only part of what the release notes state: Python and the two libraries Django requires are held only by the package's metadata, and of GeoDjango's libraries only an old SpatiaLite is refused.

## Python

Django 5.0 supported Python 3.10, 3.11 and 3.12; 5.1 added 3.13, from 5.1.3, and 5.2 added 3.14, from 5.2.8. 6.0, 6.1 and 6.2 support 3.12, 3.13 and 3.14, the 5.2 series being the last for 3.10 and 3.11 (`docs/releases/6.0.txt`). At this commit `pyproject.toml` gives `"requires-python"` as `">= 3.12"`.

Nothing in Django refuses an interpreter older than 3.12. Under Python 3.11 every module of the package parses and `import django` succeeds; in a run, `django.setup` then raised `ValueError` as it configured the logging handler "mail_admins", from an `ImportError` for `inspect.markcoroutinefunction`, which Python added in 3.12 and the module of the generic views imports at its top (`django/views/generic/base.py`).

## Database servers

| release | PostgreSQL | MySQL | MariaDB | SQLite |
|---|---|---|---|---|
| 5.0 | 12 | 8.0.11 | 10.4 | 3.27.0 |
| 5.1 | 13 | 8.0.11 | 10.5 | 3.31.0 |
| 5.2 | 14 | 8.0.11 | 10.5 | 3.31.0 |
| 6.0 | 14 | 8.0.11 | 10.6 | 3.31.0 |
| 6.1 | 15 | 8.4 | 10.11 | 3.37.0 |
| 6.2 | 16 | 8.4 | 10.11 | 3.37.0 |

*The oldest of each server that a release supports, from its notes and those of earlier releases. Oracle Database is 19 throughout, as it has been since 4.0.*

Where the notes drop a version of PostgreSQL, MySQL or MariaDB, the reason they give is the end of its upstream support, and 6.1 also passed over MySQL 8.1 to 8.3 and MariaDB 10.7 to 10.10 as short-term releases (`docs/releases/6.1.txt`); SQLite's floor rises without a reason given. 5.0's change to MySQL removed only the pre-releases of 8.0.

At this commit each backend's `minimum_database_version` holds 6.2's floor as a tuple: `(16,)` for PostgreSQL, `(3, 37)` for SQLite, `(19,)` for Oracle, and on MySQL a cached property that answers `(10, 11)` for MariaDB and `(8, 4)` otherwise (`django/db/backends/mysql/features.py:DatabaseFeatures.minimum_database_version`). `BaseDatabaseWrapper.init_connection_state` calls `BaseDatabaseWrapper.check_database_version_supported` for each alias until it passes once in a process, and the check raises `NotSupportedError`, naming the version required and the version found, for a server older than the floor (`django/db/backends/base/base.py:BaseDatabaseWrapper.check_database_version_supported`; [What a database can do: `BaseDatabaseFeatures`](../backends/features.md)).

## Drivers and Django's own dependencies

| release | asgiref | sqlparse | oracledb | gettext |
|---|---|---|---|---|
| 5.0 | 3.7.0 | 0.3.1 | 1.3.2, or cx_Oracle 8.3 | 0.15 |
| 5.1 | 3.8.1 | 0.3.1 | 1.3.2, or cx_Oracle 8.3 | 0.15 |
| 5.2 | 3.8.1 | 0.3.1 | 2.3.0, or cx_Oracle 8.3 | 0.19 |
| 6.0 | 3.9.1 | 0.5.0 | 2.3.0 | 0.19 |
| 6.1 | 3.9.1 | 0.5.0 | 2.3.0 | 0.19 |
| 6.2 | 3.12.1 | 0.5.0 | 4.0.2 | 0.19 |

*The oldest version of each that a release supports, from its notes and those of the releases before it; sqlparse's 0.3.1 dates from 4.2. Inferred: gettext's 0.15, named only by 5.2's notes as the version they raise it from, and sqlparse's 0.5.0, named only in 6.0's list of the first releases to support Python 3.12. cx_Oracle, deprecated in 5.0 in favour of oracledb, was removed in 6.0.*

asgiref and sqlparse, the libraries Django requires, are at this commit the dependencies of `pyproject.toml`, `"asgiref>=3.12.1"` and `"sqlparse>=0.5.0"`, beside tzdata on Windows; nothing in Django checks the version of either.

Two backends check their driver as their module is imported, refusing with `ImproperlyConfigured` a psycopg2 older than 2.9.9, a psycopg 3 older than 3.1.12 (`django/db/backends/postgresql/base.py`) or a mysqlclient older than 2.2.1 (`django/db/backends/mysql/base.py`). The Oracle backend imports `oracledb` alone; its connection reads the driver's version as `oracledb_version`, and nothing at this commit compares it with 4.0.2 (`django/db/backends/oracle/base.py`). gettext's floor is a message: makemessages and compilemessages, finding one of its programs missing, ask for GNU gettext 0.19 or newer, and check the version of none they find (`django/core/management/commands/makemessages.py:check_programs`, `django/core/management/commands/compilemessages.py:Command.handle`; [Making catalogues: makemessages and compilemessages](../i18n/commands.md)).

In dropping Python 3.11, 6.0 named the first release of each library to add or confirm support for 3.12: aiosmtpd 1.4.5, argon2-cffi 23.1.0, bcrypt 4.1.1, docutils 0.22, geoip2 4.8.0, Pillow 10.1.0, mysqlclient 2.2.1, numpy 1.26.0, PyYAML 6.0.2, psycopg 3.1.12, psycopg2 2.9.9, redis-py 5.1.0, selenium 4.23.0, sqlparse 0.5.0 and tblib 3.0.0 (`docs/releases/6.0.txt`); 5.0 had raised selenium to 4.8.0, colorama to 0.4.6 and docutils to 0.19. Of these the code checks only the three drivers; argon2-cffi's and bcrypt's floors are also the extras of `pyproject.toml`.

## GeoDjango's libraries

| release | PostGIS | GDAL | GEOS | PROJ |
|---|---|---|---|---|
| 5.0 | 2.5 | 2.4 | 3.8 | 5 |
| 5.1 | 3.0 | 3.0 | 3.8 | 6 |
| 5.2 | 3.1 | 3.1 | 3.8 | 6 |
| 6.0 | 3.1 | 3.1 | 3.8 | 6 |
| 6.1 | 3.2 | 3.3 | 3.10 | 6 |
| 6.2 | 3.3 | 3.5 | 3.11 | 6 |

*The oldest version of each that a release supports. The notes name the versions each release removes, and the oldest left is inferred from them, except PROJ's, which they state as "PROJ < 5" and "< 6"; the 6.2 row is also this commit's list of supported versions (`docs/ref/contrib/gis/install/geolibs.txt`). 5.0 also added GDAL 3.7 and GEOS 3.12 to the versions supported.*

None of these floors is a check. GDAL is loaded from `GDAL_LIBRARY_PATH` or found by name, the versioned names going down to 3.5, but on POSIX the unversioned "gdal" and "GDAL" are tried first, and `GDAL_VERSION`, read from the library once loaded, is compared with no floor (`django/contrib/gis/gdal/libgdal.py`). GEOS is found under unversioned names alone, and `geos_version_tuple` is compared only with 3.12 and 3.14, for what those releases changed (`django/contrib/gis/geos/libgeos.py:geos_version_tuple`). `PostGISOperations.spatial_version` takes the setting `POSTGIS_VERSION` or asks the server, and compares the version with nothing; 3.3 appears only in the message of the `ImproperlyConfigured` it raises when it cannot read one (`django/contrib/gis/db/backends/postgis/operations.py:PostGISOperations.spatial_version`). The one refusal is SpatiaLite's: `SpatiaLiteOperations.spatial_version` raises `ImproperlyConfigured` below 4.3.0 (`django/contrib/gis/db/backends/spatialite/operations.py:SpatiaLiteOperations.spatial_version`). How the libraries are loaded is told in [Geometries in Python: GEOS and GDAL](../contrib/geometries.md), and the spatial backends in [Spatial backends: PostGIS, SpatiaLite, MySQL and Oracle](../contrib/spatial-backends.md).
