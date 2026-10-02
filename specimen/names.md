---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: verified
contents: runtime, shared
---

# Names

Two kinds of name need more than their spelling before a reader can check them: a name Django makes only as it runs, and a name that more than one module defines.

`ModelBase.__new__` calls `ModelBase.add_to_class` with the name `"_meta"` and a new `Options`, so the attribute of that name is in no model's class body (`django/db/models/base.py:ModelBase.__new__`). More than one module under `django/` defines a class named `DatabaseWrapper` at its top: the PostgreSQL backend's is `django/db/backends/postgresql/base.py:DatabaseWrapper`, and the SQLite backend's is `django/db/backends/sqlite3/base.py:DatabaseWrapper`.

## How does a page write a name the source never declares?

A name the source never declares is declared by the page that uses it, with the pointer to the code that makes it, and is written on the class a reader knows it by. [Names made as the code runs](names/runtime.md) does so for two attributes of a model class and for one setting.

## How does a page write a name that several modules define?

A name that several modules define is given with its module first, by a pointer or by writing the name from its module, inside the section that uses it. [One name, several classes](names/shared.md) does so for `django/db/backends/postgresql/base.py:DatabaseWrapper`.
