---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: verified
---

# One name, several classes

Which class does a sentence mean when it says `django/db/backends/postgresql/base.py:DatabaseWrapper`, and which others share the name?

More than one module under `django/` defines a class named `DatabaseWrapper` at its top: the PostgreSQL backend's is `django/db/backends/postgresql/base.py:DatabaseWrapper`, and the SQLite backend's is `django/db/backends/sqlite3/base.py:DatabaseWrapper`.

## Which classes are named `DatabaseWrapper`?

The PostgreSQL backend's connection class is `django/db/backends/postgresql/base.py:DatabaseWrapper`, and the SQLite backend's is `django/db/backends/sqlite3/base.py:DatabaseWrapper`. The search that finds every module with a class of that name at its top is `^class DatabaseWrapper` over `django/`: its hits are under `django/db/backends/` and under `django/contrib/gis/db/backends/`.

## What does the PostgreSQL `DatabaseWrapper` declare itself?

The PostgreSQL backend's class is `django/db/backends/postgresql/base.py:DatabaseWrapper`, and it declares `DatabaseWrapper.get_new_connection` in its own body. It declares no method named `"cursor"`: that is `BaseDatabaseWrapper.cursor`, in `django/db/backends/base/base.py`.
