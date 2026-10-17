---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The versions Django needs: Python, databases and libraries

The oldest Python, database server and library that each release from Django 5.0 to this commit supports, and where the floors are held: `BaseDatabaseFeatures.minimum_database_version`, checked as a connection opens; the PostgreSQL and MySQL drivers and SpatiaLite, checked by their backends; and `pyproject.toml`, which only an installer reads.

6.0 dropped Python 3.10 and 3.11, and with them the releases of Django's optional libraries older than the first to support 3.12, the database drivers among them (`docs/releases/6.0.txt`). 6.1 raised MySQL from 8.0.11 to 8.4 and MariaDB to 10.11, passing over releases the notes call short-term; where they give a reason for dropping any other server, it is the end of its upstream support (`docs/releases/6.1.txt`). 6.2 takes PostgreSQL to 16 and asgiref to 3.12.1. The code enforces the servers' floors, the PostgreSQL and MySQL drivers' and SpatiaLite's; the rest are stated, in the notes or the package's metadata.

## Python

From each release's notes:

| release | Python |
|---|---|
| 5.0 | 3.10, 3.11, 3.12 |
| 5.1 | 3.10 to 3.13, 3.13 from 5.1.3 |
| 5.2 | 3.10 to 3.14, 3.14 from 5.2.8 |
| 6.0, 6.1, 6.2 | 3.12, 3.13, 3.14 |

At this commit `pyproject.toml` gives `"requires-python"` as `">= 3.12"`; 5.2.17's metadata gives `">=3.10"`, and 6.0.8's and 6.1.1's `">=3.12"` (`django:pyproject.toml`). Nothing in Django refuses an older interpreter: under Python 3.11 `import django` succeeds, and `django.setup` raises `ValueError`, from an `ImportError` for `inspect.markcoroutinefunction`, which Python added in 3.12 (`django/views/generic/base.py`).

## Database servers

From the notes; from 5.2 on, each row is also the backends' `BaseDatabaseFeatures.minimum_database_version` under 5.2.17, 6.0.8, 6.1.1 and, for 6.2, this commit:

| release | PostgreSQL | MySQL | MariaDB | SQLite |
|---|---|---|---|---|
| 5.0 | 12 | 8.0.11 | 10.4 | 3.27.0 |
| 5.1 | 13 | 8.0.11 | 10.5 | 3.31.0 |
| 5.2 | 14 | 8.0.11 | 10.5 | 3.31.0 |
| 6.0 | 14 | 8.0.11 | 10.6 | 3.31.0 |
| 6.1 | 15 | 8.4 | 10.11 | 3.37.0 |
| 6.2 | 16 | 8.4 | 10.11 | 3.37.0 |

*Oracle Database is 19 in every row, as it has been since 4.0 (`docs/releases/4.0.txt`).*

`BaseDatabaseWrapper.check_database_version_supported` compares the server's version with the backend's floor and raises `NotSupportedError` for an older one (`django/db/backends/base/base.py:BaseDatabaseWrapper.check_database_version_supported`); `BaseDatabaseWrapper.init_connection_state` calls it as a connection opens, for each alias until it passes once in a process (`django/db/backends/base/base.py:BaseDatabaseWrapper.init_connection_state`). MySQL's floor depends on whether the server is MariaDB (`django/db/backends/mysql/features.py:DatabaseFeatures.minimum_database_version`). MySQL's backend opens a connection on a stand-in for the driver, answering as MySQL 8.0.36:

```text recording=changes
connection.cursor() on MySQL's backend, the server answering as MySQL 8.0.36
    5.2.17       the connection opens
    6.0.8        the connection opens
    6.1.1        NotSupportedError: MySQL 8.4 or later is required (found 8.0.36).
    this commit  NotSupportedError: MySQL 8.4 or later is required (found 8.0.36).
```

A project on MySQL 8.0 meets 6.1's floor only as a connection opens ([What a database can do: `BaseDatabaseFeatures`](../backends/features.md)).

## The libraries Django requires, and the drivers

From the notes:

| library | 5.0 | 5.1 | 5.2 | 6.0 | 6.1 | 6.2 |
|---|---|---|---|---|---|---|
| asgiref | 3.7.0 | 3.8.1 | 3.8.1 | 3.9.1 | 3.9.1 | 3.12.1 |
| sqlparse | 0.3.1 | 0.3.1 | 0.3.1 | 0.5.0 | 0.5.0 | 0.5.0 |
| psycopg | 3.1.8 | 3.1.8 | 3.1.8 | 3.1.12 | 3.1.12 | 3.1.12 |
| psycopg2 | 2.8.4 | 2.8.4 | 2.8.4 | 2.9.9 | 2.9.9 | 2.9.9 |
| mysqlclient | 1.4.3 | 1.4.3 | 1.4.3 | 2.2.1 | 2.2.1 | 2.2.1 |
| oracledb | 1.3.2 | 1.3.2 | 2.3.0 | 2.3.0 | 2.3.0 | 4.0.2 |
| gettext | 0.15 | 0.15 | 0.19 | 0.19 | 0.19 | 0.19 |

*sqlparse's 0.3.1, psycopg's 3.1.8 and mysqlclient's 1.4.3 date from 4.2, psycopg2's 2.8.4 from 4.0; their 6.0 releases the 6.0 notes name only among the first to support Python 3.12. gettext's 0.15, under 5.0 and 5.1, is named only by the 5.2 notes, which raised it to 0.19. From 5.0 to 5.2 cx_Oracle 8.3 would also serve in oracledb's place; deprecated in 5.0, it was removed in 6.0.*

asgiref and sqlparse are, with tzdata on Windows, the dependencies of `pyproject.toml`; from 5.2 on, their columns are what the package's metadata asks for under 5.2.17, 6.0.8, 6.1.1 and this commit. Nothing in Django checks the version of either, nor the Oracle backend that of oracledb (`django/db/backends/oracle/base.py`). gettext's floor is a message: makemessages and compilemessages, finding one of its programs missing, ask for GNU gettext 0.19 or newer, and read the version of none they find (`django/core/management/commands/makemessages.py:check_programs`; [Making catalogues: makemessages and compilemessages](../i18n/commands.md)).

6.0 named, for each library of the table that follows, the first release to support Python 3.12 (`docs/releases/6.0.txt`); all but sqlparse are optional, and the code checks only the drivers:

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
| sqlparse | 0.5.0 | no |
| tblib | 3.0.0 | no |

5.0 had raised selenium to 4.8.0, colorama to 0.4.6 and docutils to 0.19. In 6.0.8's and 6.1.1's metadata, as in `pyproject.toml`, the package's extras ask for argon2-cffi 23.1.0 and bcrypt 4.1.1, where 5.2.17's asked for argon2-cffi 19.1.0 and any bcrypt.

6.0 raised the drivers' checks to the releases both tables give for it: `ImproperlyConfigured` refuses a psycopg2 older than 2.9.9 or a psycopg older than 3.1.12 (`django/db/backends/postgresql/base.py`), and is meant to refuse a mysqlclient older than 2.2.1. Under 5.2.17 the PostgreSQL backend imported with psycopg 3.1.10, which 6.0.8 refuses.

MySQL's check compares `MySQLdb.version_info` and writes its message from `MySQLdb.__version__` (`django/db/backends/mysql/base.py`), which mysqlclient 2.0.0 to 2.2.0 do not define. The installed driver is made to look as 2.1.1 does:

```text recording=changes
import django.db.backends.mysql.base, MySQLdb as mysqlclient 2.1.1 has it: version_info (2, 1, 1, "final", 0), no __version__
    5.2.17       the module is imported
    6.0.8        AttributeError: module 'MySQLdb' has no attribute '__version__'
    6.1.1        AttributeError: module 'MySQLdb' has no attribute '__version__'
    this commit  AttributeError: module 'MySQLdb' has no attribute '__version__'
```

> **Trap.** Since 6.0 a project on mysqlclient 2.1 is stopped by an `AttributeError` that does not name the floor, where 5.2.17 imported the backend; `load_backend`, which catches only an `ImportError`, passes it on (`django/db/utils.py:load_backend`).

## GeoDjango's libraries

The oldest of each GeoDjango library, by release:

| release | PostGIS | GDAL | GEOS | PROJ |
|---|---|---|---|---|
| 5.0 | 2.5 | 2.4 | 3.8 | 5 |
| 5.1 | 3.0 | 3.0 | 3.8 | 6 |
| 5.2 | 3.1 | 3.1 | 3.8 | 6 |
| 6.0 | 3.1 | 3.1 | 3.8 | 6 |
| 6.1 | 3.2 | 3.3 | 3.10 | 6 |
| 6.2 | 3.3 | 3.5 | 3.11 | 6 |

*The oldest of each, inferred from the versions the notes remove; the 6.2 row is also this commit's list of supported versions (`docs/ref/contrib/gis/install/geolibs.txt`).*

No floor of the table is checked. SpatiaLite's is: `SpatiaLiteOperations.spatial_version` raises `ImproperlyConfigured` below 4.3.0 (`django/contrib/gis/db/backends/spatialite/operations.py:SpatiaLiteOperations.spatial_version`).
