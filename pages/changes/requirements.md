---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The versions Django needs: Python, databases and libraries

The oldest Python, database, driver and library that each release from 5.0 to this commit supports, and which of these floors Django's code enforces rather than only states.

6.0 dropped Python 3.10 and 3.11, and with them the releases of Django's optional libraries older than the first to support 3.12, the database drivers among them (`docs/releases/6.0.txt`). 6.1 raised MySQL from 8.0.11 to 8.4 and MariaDB to 10.11. 6.1's notes give two reasons for dropping a server: its upstream support ends, or it is a release they call short-term (`docs/releases/6.1.txt`). 6.2 takes PostgreSQL to 16 and asgiref to 3.12.1. The code enforces the floors of the databases, of the PostgreSQL and MySQL drivers and of SpatiaLite. The rest are stated, in the notes or the package's metadata.

## Python

Since 6.0 Django needs Python 3.12 or later, and nothing in Django refuses an older interpreter. From each release's notes:

| release | Python |
|---|---|
| 5.0 | 3.10, 3.11, 3.12 |
| 5.1 | 3.10 to 3.13, 3.13 from 5.1.3 |
| 5.2 | 3.10 to 3.14, 3.14 from 5.2.8 |
| 6.0, 6.1, 6.2 | 3.12, 3.13, 3.14 |

The package's metadata, which an installer reads, asks for `">=3.10"` under 5.2.17 and `">=3.12"` under 6.0.8 and later (`django:pyproject.toml`). Under Python 3.11 `import django` succeeds. `django.setup` then raises `ValueError` as it configures logging, from an `ImportError` for `inspect.markcoroutinefunction`, which Python added in 3.12 (`django/utils/log.py:configure_logging`, `django/views/generic/base.py`).

## Databases

6.1 raised the floor of every database but Oracle Database. A database below its backend's floor is refused only as a connection opens. From the notes, and from 5.2 on also the backends' `BaseDatabaseFeatures.minimum_database_version` under 5.2.17, 6.0.8, 6.1.1 and this commit:

| release | PostgreSQL | MySQL | MariaDB | SQLite |
|---|---|---|---|---|
| 5.0 | 12 | 8.0.11 | 10.4 | 3.27.0 |
| 5.1 | 13 | 8.0.11 | 10.5 | 3.31.0 |
| 5.2 | 14 | 8.0.11 | 10.5 | 3.31.0 |
| 6.0 | 14 | 8.0.11 | 10.6 | 3.31.0 |
| 6.1 | 15 | 8.4 | 10.11 | 3.37.0 |
| 6.2 | 16 | 8.4 | 10.11 | 3.37.0 |

*Oracle Database is 19 in every row, as it has been since 4.0 (`docs/releases/4.0.txt`).*

`BaseDatabaseWrapper.check_database_version_supported` compares the database's version with the backend's floor and raises `NotSupportedError` for an older one (`django/db/backends/base/base.py:BaseDatabaseWrapper.check_database_version_supported`; [What a database can do: `BaseDatabaseFeatures`](../backends/features.md)). `BaseDatabaseWrapper.init_connection_state` calls it as a connection opens, until it has passed once for that alias in the process (`django/db/backends/base/base.py:BaseDatabaseWrapper.init_connection_state`). MySQL's floor depends on whether the server is MariaDB (`django/db/backends/mysql/features.py:DatabaseFeatures.minimum_database_version`).

A stand-in for the driver makes the server answer as MySQL 8.0.36: the old floor, 8.0.11, lets the connection open, and 6.1's refuses it:

```text recording=changes
connection.cursor() on MySQL's backend, the server answering as MySQL 8.0.36
    5.2.17       the connection opens
    6.0.8        the connection opens
    6.1.1        NotSupportedError: MySQL 8.4 or later is required (found 8.0.36).
    this commit  NotSupportedError: MySQL 8.4 or later is required (found 8.0.36).
```

## The libraries Django requires, and the drivers

Since 6.0 the PostgreSQL and MySQL backends will not import with a driver older than its first release for Python 3.12. Nothing in Django checks the version of any other library here, oracledb among them (`django/db/backends/oracle/base.py`). Each floor but gettext's 0.15, from the notes of the release that set it:

| library | 5.0 | 5.1 | 5.2 | 6.0 | 6.1 | 6.2 |
|---|---|---|---|---|---|---|
| asgiref | 3.7.0 | 3.8.1 | 3.8.1 | 3.9.1 | 3.9.1 | 3.12.1 |
| sqlparse | 0.3.1 | 0.3.1 | 0.3.1 | 0.5.0 | 0.5.0 | 0.5.0 |
| psycopg | 3.1.8 | 3.1.8 | 3.1.8 | 3.1.12 | 3.1.12 | 3.1.12 |
| psycopg2 | 2.8.4 | 2.8.4 | 2.8.4 | 2.9.9 | 2.9.9 | 2.9.9 |
| mysqlclient | 1.4.3 | 1.4.3 | 1.4.3 | 2.2.1 | 2.2.1 | 2.2.1 |
| oracledb | 1.3.2 | 1.3.2 | 2.3.0 | 2.3.0 | 2.3.0 | 4.0.2 |
| gettext | 0.15 | 0.15 | 0.19 | 0.19 | 0.19 | 0.19 |

*gettext's 0.15 is named only by the 5.2 notes.*

With tzdata on Windows, asgiref and sqlparse are the dependencies of `pyproject.toml`. From 5.2 on, their rows are also what the package's metadata asks for under 5.2.17 and later. Under 5.0 to 5.2, cx_Oracle 8.3 would also serve in oracledb's place. Deprecated in 5.0, it was removed in 6.0 (`docs/releases/6.0.txt`).

gettext's floor is only a message. When makemessages or compilemessages cannot find one of gettext's programs, it asks for GNU gettext 0.19 or newer; neither checks the version of a program it finds (`django/core/management/commands/makemessages.py:check_programs`, `django/core/management/commands/compilemessages.py:Command.handle`; [Making catalogues: makemessages and compilemessages](../i18n/commands.md)).

The PostgreSQL backend raises `ImproperlyConfigured` for a psycopg2 older than 2.9.9 or a psycopg older than 3.1.12 (`django/db/backends/postgresql/base.py`). Under 5.2.17 it imported with psycopg 3.1.10, which 6.0.8 refuses. MySQL's backend is meant to refuse a mysqlclient older than 2.2.1 in the same way. Its check compares `MySQLdb.version_info`, but writes its message from `MySQLdb.__version__`, which mysqlclient 2.0.0 to 2.2.0 do not define (`django/db/backends/mysql/base.py`).

Made to look as mysqlclient 2.1.1 does, the driver passes 5.2.17's floor of 1.4.3, and each later release fails in writing its refusal:

```text recording=changes
import django.db.backends.mysql.base, MySQLdb as mysqlclient 2.1.1 has it: version_info (2, 1, 1, "final", 0), no __version__
    5.2.17       the module is imported
    6.0.8        AttributeError: module 'MySQLdb' has no attribute '__version__'
    6.1.1        AttributeError: module 'MySQLdb' has no attribute '__version__'
    this commit  AttributeError: module 'MySQLdb' has no attribute '__version__'
```

> **Trap.** Since 6.0 a project on mysqlclient 2.1 is stopped by an `AttributeError` that does not name the floor.

## The optional libraries

Since 6.0 an optional library is supported only from its first release for Python 3.12; the 6.0 notes name these (`docs/releases/6.0.txt`):

| library | oldest from 6.0 | checked |
|---|---|---|
| aiosmtpd | 1.4.5 | no |
| argon2-cffi | 23.1.0 | no |
| bcrypt | 4.1.1 | no |
| docutils | 0.22 | no |
| geoip2 | 4.8.0 | no |
| mysqlclient | 2.2.1 | as its backend is imported |
| numpy | 1.26.0 | no |
| Pillow | 10.1.0 | no |
| psycopg | 3.1.12 | as its backend is imported |
| psycopg2 | 2.9.9 | as its backend is imported |
| PyYAML | 6.0.2 | no |
| redis-py | 5.1.0 | no |
| selenium | 4.23.0 | no |
| tblib | 3.0.0 | no |

5.0 had raised selenium to 4.8.0, colorama to 0.4.6 and docutils to 0.19 (`docs/releases/5.0.txt`). The package's extras ask for these argon2-cffi and bcrypt releases under 6.0.8 and later; 5.2.17's asked for argon2-cffi 19.1.0 and any bcrypt (`django:pyproject.toml`).

## GeoDjango's libraries

6.1 and 6.2 each raised the oldest PostGIS, GDAL and GEOS that GeoDjango supports, and no floor of this table is checked:

| release | PostGIS | GDAL | GEOS | PROJ |
|---|---|---|---|---|
| 5.0 | 2.5 | 2.4 | 3.8 | 5 |
| 5.1 | 3.0 | 3.0 | 3.8 | 6 |
| 5.2 | 3.1 | 3.1 | 3.8 | 6 |
| 6.0 | 3.1 | 3.1 | 3.8 | 6 |
| 6.1 | 3.2 | 3.3 | 3.10 | 6 |
| 6.2 | 3.3 | 3.5 | 3.11 | 6 |

*Inferred from the versions the notes remove; the 6.2 row is also this commit's list of supported versions (`docs/ref/contrib/gis/install/geolibs.txt`).*

SpatiaLite's floor is checked: `SpatiaLiteOperations.spatial_version` raises `ImproperlyConfigured` below 4.3.0 (`django/contrib/gis/db/backends/spatialite/operations.py:SpatiaLiteOperations.spatial_version`).
