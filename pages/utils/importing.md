---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Importing by name: `import_string` and `autodiscover_modules`

`django/utils/module_loading.py` is how Django reaches code it knows only by name: `import_string` turns a dotted path written as text into the class, function or module it names, `module_has_submodule` asks whether a package has a submodule without running it, and `autodiscover_modules` imports a module of one name from every installed application.

A setting names code by its dotted path, as a string: each entry of `MIDDLEWARE`, the `"BACKEND"` of each entry of `CACHES`, `STORAGES`, `TASKS` and `TEMPLATES`, `AUTHENTICATION_BACKENDS`, `PASSWORD_HASHERS` and others. The code that reads the setting imports the path: `BaseHandler.load_middleware` for each middleware ([Building the middleware chain](../handlers/chain.md)), `get_hashers` for the password hashers (`django/core/handlers/base.py:BaseHandler.load_middleware`, `django/contrib/auth/hashers.py:get_hashers`).

## `import_string`

`import_string` takes a path and returns what it names (`django/utils/module_loading.py:import_string`). A path with no dot names a top-level module, which is imported and returned. Any other path is tried three ways, in order:

1. The whole path is imported as a module, and an `ImportError` is passed over. For a path that names a class this fails, having imported the modules along the path.
2. The path is split at its last dot, the part before it is imported, and the attribute named by the part after it is returned if the module has one.
3. Failing that, the whole path is imported as a module again. If this fails too, `import_string` raises `ImportError` with the message `Module "…" does not define a "…" attribute/class`, the failed import as its cause.

The first step keeps the answer from depending on what was imported before. Importing a submodule sets it on its package under its name, replacing what the package held there; so where a package defines a function and has a submodule of the same name that nothing has imported yet, the first step puts the submodule in the function's place and the second returns it.

> **Changed in 6.2.** `import_string` accepts a module's path, a top-level one included, where a top-level module failed and a submodule worked only if already imported; and it favours a submodule over a same-named attribute of its package, where the answer used to depend on what had been imported before (`docs/releases/6.2.txt`).

Where a path fails decides what the caller sees. A missing module along it gives the second step's `ModuleNotFoundError`, as it is; a module without the attribute or the submodule, the third step's message. An error other than `ImportError` from a module's code passes out of the first step. An `ImportError` from a module's code is passed over by the first step and raised when a later step imports the module again, so that code runs twice: by the second step as it is, or, where the path names that module itself, by the third, as that step's message with the module's error as its cause.

A run, harbour/office/board.py not yet imported ([The utility layer](../utils.md) shows it):

```text
import_string("harbour.office.board.Harbour")     the class harbour.office.board.Harbour
import_string("harbour.office.board")             the module harbour.office.board
import_string("harbour")                          the module harbour
import_string("harbour.office.board.Lighthouse")
    ImportError: Module "harbour.office.board" does not define a "Lighthouse" attribute/class
```

## A module still being imported

Each import in `import_string` goes through `cached_import`, which returns the module in `sys.modules` if it is there with a spec not marked as still initializing, and otherwise calls `importlib.import_module` (`django/utils/module_loading.py:cached_import`). The standard library marks a module's spec so while the module's code runs, and `importlib.import_module` takes the module's lock only for a module that is absent or so marked; one present and unmarked it returns at once. The mark matters when another thread is part way through the import: the module is in `sys.modules` without the names its code has not reached, and `importlib.import_module` waits on the module's lock until that thread is done. In a run with a module that paused before defining a name, a second thread's `import_string` of the name waited for the first thread's import to finish and returned the name's value; reading the name from the module in `sys.modules` raised `AttributeError`.

## `module_has_submodule`

`module_has_submodule` says whether a package has a submodule of a given name, without running it (`django/utils/module_loading.py:module_has_submodule`). A module with no `__path__` is not a package and has none. Otherwise `importlib.util.find_spec` is asked for the full name and returns a spec, or `None`, without executing the module. A dotted name with a part before its last that is missing or not a package raises `ModuleNotFoundError` there, and the answer is `False`.

`AppConfig.create` asks it whether an application has an apps submodule to look in for its configuration class and `AppConfig.import_models` whether it has a models submodule ([Populating the app registry](../startup/populate.md)), and the migrate command whether it has a management module (`django/apps/config.py:AppConfig.create`, `django/apps/config.py:AppConfig.import_models`, `django/core/management/commands/migrate.py:Command.handle`).

## `autodiscover_modules`

`autodiscover_modules` imports each module name it is given from every installed application, in the order of `INSTALLED_APPS` (`django/utils/module_loading.py:autodiscover_modules`). Its user in Django is the admin: `django.contrib.admin.autodiscover` calls it for `"admin"` with the default site as the registry, and `AdminConfig.ready` calls that as Django starts ([Registering models: `AdminSite.register` and `ModelAdmin`](../admin/registration.md)) (`django/contrib/admin/__init__.py:autodiscover`).

When an import raises, a registry given as the register_to argument gets back the copy of its `_registry` taken before the import, undoing what the failed module registered; the comment's reason is that the import will have to happen again, and what was left registered could then raise `AlreadyRegistered` and `NotRegistered` (ticket 8245). Then the error is raised again only if the application has the module, by `module_has_submodule`. The test is on the application, not the error: an application without the module is passed over, and any error from a module that exists reaches the caller, a `ModuleNotFoundError` for a package it imports among them.

Two of harbour's applications have a notices module that posts on the office's notice board, an object with a `_registry` dictionary; the crew's fails after posting:

```python
# harbour/crew/notices.py
from harbour.crew.models import Sailor
from harbour.office.noticeboard import noticeboard

noticeboard.post(Sailor, "Shore leave ends at dusk")

from harbour.crew.models import Watch  # there is no such model
```

```text
module_has_submodule(harbour.fleet, "notices")            True
module_has_submodule(harbour.crew, "notices")             True
module_has_submodule(harbour.office, "notices")           False
autodiscover_modules("notices", register_to=noticeboard)  raised ImportError
noticeboard._registry                                     {<class 'harbour.fleet.models.Ship'>: 'Ships sail at high tide'}
```

The fleet's notice stays; the crew's was taken off before its `ImportError` was raised again.

## `qualname` and `module_dir`

`qualname` goes the other way: it returns a module's name, or a class's or a function's `__module__` and `__qualname__` joined by a dot (`django/utils/module_loading.py:qualname`). It raises `ValueError` for an object without them, and for one whose qualified name holds `"<"`, as a lambda's and a function's local objects do: such an object has no path to be imported by. A task is pickled as its function's path ([Background tasks: `Task`, `TaskResult` and the task backends](../services/tasks.md)) (`django/tasks/base.py:Task.__reduce__`, `django/tasks/base.py:Task.module_path`), the migration serializer writes functions and classes by it ([Serializing values: `serializer_factory` and `deconstruct`](../makemigrations/serializer.md)), and a URL pattern names its view by it (`django/urls/resolvers.py:URLPattern.lookup_str`). For a class defined inside another, `import_string` cannot read the path back, since it splits only at the last dot:

```text
qualname(Port.DoesNotExist)                       'harbour.fleet.models.Port.DoesNotExist'
import_string("harbour.fleet.models.Port.DoesNotExist")
    ModuleNotFoundError: No module named 'harbour.fleet.models.Port'; 'harbour.fleet.models' is not a package
```

`module_dir` returns a package's only entry of `__path__`, or else the directory of the module's file, and raises `ValueError` for a namespace package spread over several directories, which has neither (`django/utils/module_loading.py:module_dir`). `MigrationWriter.basedir` calls it to place a new migration file ([Writing a migration file: `MigrationWriter`](../makemigrations/writer.md)).
