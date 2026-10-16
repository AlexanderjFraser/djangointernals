---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Finding static files: the finders

A **finder** finds a static file by its relative path, such as notes/base.css, and lists every file it has. `STATICFILES_FINDERS` names the finders; `django/contrib/staticfiles/finders.py` holds their base class `BaseFinder`, the two the setting names by default, `FileSystemFinder` and `AppDirectoriesFinder`, the storage finders, and `find`, which asks them in turn.

Collectstatic asks each finder to list everything it has ([Collecting static files: the collectstatic command](collectstatic.md)). Findstatic asks for a path, and so does the finders' view, which the development server goes through and which takes the first answer ([Serving static files: `StaticFilesHandler` and the development server](serving-static.md)).

## What a finder is: `BaseFinder`

`BaseFinder` declares three methods and implements none (`django/contrib/staticfiles/finders.py:BaseFinder`). `BaseFinder.find` takes a relative path and returns the absolute path of the first file it finds, or, given `find_all=True`, a list of all. `BaseFinder.list` takes patterns to ignore, collectstatic's `--ignore` and, by default, `StaticFilesConfig.ignore_patterns`, `["CVS", ".*", "*~"]`, and yields each file's relative path with the storage that holds it, through which collectstatic reaches the file. `BaseFinder.check` returns the finder's system check messages; unlike the other two, a subclass need not provide it.

Django's finders list with `get_files`, which walks a storage and skips a file whose name or relative path matches a pattern, and a directory whose name does; `matches_patterns` tests with `fnmatch.fnmatchcase`, case-sensitive everywhere (`django/contrib/staticfiles/utils.py:get_files`, `django/contrib/staticfiles/utils.py:matches_patterns`). Their `find` methods also append each directory they search, once, to the module's list `searched_locations`, so the list ends where the search stopped.

## `FileSystemFinder`: the directories of `STATICFILES_DIRS`

`FileSystemFinder` takes its directories from `STATICFILES_DIRS` when it is made. An entry is a directory, or a pair of a prefix and a directory; the finder keeps each pair once, in order, and makes a `FileSystemStorage` for each directory, setting on it an attribute `"prefix"`, which collectstatic puts before each of the directory's paths (`django/contrib/staticfiles/finders.py:FileSystemFinder.__init__`). The harbour office's, with the charts' under a prefix:

```python
# harbour/settings.py
STATICFILES_DIRS = [
    BASE_DIR / "assets",
    ("charts", BASE_DIR / "chart-assets"),
]
```

`FileSystemFinder.find` tries each directory in order with `FileSystemFinder.find_location`. With a prefix, the path must begin with the prefix and the platform's separator, `os.sep`, which are taken off; the rest is joined to the directory with `safe_join`, and the result returned if it exists, a directory included (`django/contrib/staticfiles/finders.py:FileSystemFinder.find_location`). `safe_join` raises `SuspiciousFileOperation` for a path that climbs out of the directory, uncaught: in the run, "../settings.py" raised it ([Paths and archives: `safe_join`, `safe_makedirs` and `extract`](../utils/paths.md)).

## `AppDirectoriesFinder`: each application's static directory

`AppDirectoriesFinder` looks in the directory named by its class attribute `AppDirectoriesFinder.source_dir`, `"static"`, inside each installed application. When made, it goes through the application configs in the order of `INSTALLED_APPS`, makes a storage of its `AppDirectoriesFinder.storage_class`, `FileSystemStorage`, for each one's directory, and keeps those that exist, under the application's name (`django/contrib/staticfiles/finders.py:AppDirectoriesFinder.__init__`). It accepts a list of application names to keep to; `get_finder` passes none. In the example these are `django.contrib.gis` and notes. `AppDirectoriesFinder.find` asks each storage in turn with `FileSystemStorage.exists` and answers with `FileSystemStorage.path`, which is `safe_join` again (`django/contrib/staticfiles/finders.py:AppDirectoriesFinder.find_in_app`).

## The storage finders

`BaseStorageFinder` finds files in a storage, given to it or set as its class attribute `BaseStorageFinder.storage`, and raises `ImproperlyConfigured` with none; it finds nothing in a storage with no paths on disk, where `Storage.path` raises `NotImplementedError` (`django/contrib/staticfiles/finders.py:BaseStorageFinder`). `DefaultStorageFinder` is one over `default_storage`, the `"default"` storage of `STORAGES`, and refuses one whose `base_location` is empty, as a `FileSystemStorage`'s is with no location and `MEDIA_ROOT` left empty; one with no `base_location` passes (`django/contrib/staticfiles/finders.py:DefaultStorageFinder.__init__`). The default `STATICFILES_FINDERS` has it commented out (`django/conf/global_settings.py`).

## `find`, and one instance of each finder

The module's `find` empties `searched_locations` and asks each finder in the order of `STATICFILES_FINDERS` (`django/contrib/staticfiles/finders.py:find`). Without `find_all=True` it returns the first answer, so the finders' order, then each one's order of directories, decides which file a path means: the harbour office's notes/base.css shadows the notes application's. With it, every answer goes into one list; with no match it returns `None` or an empty list.

> **Changed in 6.1.** `find` no longer takes all, deprecated in 5.2 for find_all (`docs/releases/6.1.txt`).

`get_finders` reads the setting at each call and yields `get_finder` of each path, which imports the class, refuses one that is not a subclass of `BaseFinder` with `ImproperlyConfigured`, and returns an instance. `get_finder` is wrapped in `functools.cache`, so each finder is made once in a process and keeps the directories it found then (`django/contrib/staticfiles/finders.py:get_finder`). In the run, assigning a new `STATICFILES_DIRS` to `settings` left the same `FileSystemFinder`, with the old directories. Under `override_settings`, receivers of `setting_changed` clear the cache when `STATICFILES_DIRS`, `STATIC_ROOT` or `INSTALLED_APPS` changes (`django/test/signals.py:static_finders_changed`, `django/test/signals.py:update_installed_apps`).

## The checks

`StaticFilesConfig.ready` registers two checks under the tag `Tags.staticfiles` (`django/contrib/staticfiles/apps.py:StaticFilesConfig.ready`). `check_storages` returns `"staticfiles.E005"` when `STORAGES` has no `"staticfiles"` storage; `check_finders` calls each finder's `check`, and of Django's finders only `FileSystemFinder` has one (`django/contrib/staticfiles/checks.py:check_finders`). `FileSystemFinder.check` returns `"staticfiles.E001"` alone when `STATICFILES_DIRS` is not a list or tuple; otherwise, for each entry, `"staticfiles.E003"` for a prefix that ends with a slash, `"staticfiles.E002"` for a directory that is `STATIC_ROOT`, and the warning `"staticfiles.W004"` for a directory that does not exist (`django/contrib/staticfiles/finders.py:FileSystemFinder.check`). A prefix ending in a slash would have `find_location` look for a second separator after it.

## The command findstatic

Findstatic is a `LabelCommand` whose labels are relative paths. For each it calls `find`, with `find_all=True` unless `--first` is given; at verbosity 0 it prints bare paths, and from 2 adds `searched_locations`. A path found nowhere is reported on standard error, except at verbosity 0, and the command still succeeds (`django/contrib/staticfiles/management/commands/findstatic.py:Command.handle_label`). It leaves `BaseCommand.requires_system_checks` at `"__all__"`, so the checks run first, all but the deployment and database ones ([The system checks](../commands/checks.md)). On Windows, with the project's directory written BASE_DIR and Django's DJANGO:

```text
$ python manage.py findstatic notes/base.css --verbosity 2
Found 'notes/base.css' here:
  BASE_DIR\assets\notes\base.css
  BASE_DIR\notes\static\notes\base.css
Looking in the following locations:
  BASE_DIR\assets
  BASE_DIR\chart-assets
  DJANGO\contrib\gis\static
  BASE_DIR\notes\static

$ python manage.py findstatic notes/base.css --first --verbosity 2
Found 'notes/base.css' here:
  BASE_DIR\assets\notes\base.css
Looking in the following locations:
  BASE_DIR\assets

$ python manage.py findstatic charts/legend.css --first
No matching file found for 'charts/legend.css'.

$ python manage.py findstatic "charts\legend.css" --first
Found 'charts\legend.css' here:
  BASE_DIR\chart-assets\legend.css
```

With `--first` the search stopped at the first directory, and the locations say so. The prefixed file answered only to a backslash after the prefix, `os.sep` on Windows; on Linux and macOS `os.sep` is a slash, and charts/legend.css finds it. With the prefix written "charts/" and a third directory, old-assets, that does not exist, the error stopped the command, with exit status 1:

```text
$ python manage.py findstatic notes/base.css --first
SystemCheckError: System check identified some issues:

ERRORS:
?: (staticfiles.E003) The prefix 'charts/' in the STATICFILES_DIRS setting must not end with a slash.

WARNINGS:
?: (staticfiles.W004) The directory 'BASE_DIR\old-assets' in the STATICFILES_DIRS setting does not exist.
```
