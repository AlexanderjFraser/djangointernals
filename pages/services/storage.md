---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# File storage: `Storage`, `FileSystemStorage` and `storages`

How Django saves a file's content under a name and finds it again: the handler `storages`, which makes one storage for each alias of `STORAGES`; the base class `Storage`, which decides the name a file is saved under; and `FileSystemStorage`, which keeps files in a directory on the server.

Writing the bytes is the easy part of saving a file; the name is the hard part. It may come from a browser, with odd characters or a path that climbs out of the storage's directory; another file may have it already; and it must fit the column that will keep it. `Storage` settles the name in methods its backends inherit; a backend stores the bytes under it, and answers for it (`django/core/files/storage/base.py:Storage`).

## `STORAGES` and the handler

`STORAGES` maps each alias to a dictionary that names a backend class under `"BACKEND"`, with any `"OPTIONS"`. Its default has two aliases, `"default"`, a `FileSystemStorage`, and `"staticfiles"`, the static files' storage ([Static file storages: `ManifestStaticFilesStorage` and hashed names](../contrib/static-storage.md)) (`django/conf/global_settings.py`).

The handler `storages` is a `StorageHandler`. It copies the setting into `StorageHandler.backends` the first time a storage is asked for, and `StorageHandler.__getitem__` makes an alias's storage with `StorageHandler.create_storage` once and keeps it, so the process has one storage for each alias, shared by every thread (`django/core/files/storage/handler.py:StorageHandler`). `create_storage` imports the class and calls it with the `"OPTIONS"` as keyword arguments, ignoring any other key. An alias the setting lacks, or a class that will not import, raises `InvalidStorageError`, an `ImproperlyConfigured`.

`django.core.files.storage.default_storage` is a `DefaultStorage`, a `LazyObject` that looks up the `"default"` alias at first use and stands for it from then on ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)); a `django.db.models.FileField` given no storage keeps it ([File fields](../models/files.md)) (`django/core/files/storage/__init__.py:DefaultStorage`). A test's override of `STORAGES` empties the handler and the lazy storages ([Overriding settings](../startup/overrides.md)) (`django/test/signals.py:storages_changed`).

## `Storage`: the name in the base class, the bytes in the backend

Two public methods of `Storage` hand the work to private ones that the base class does not define: `Storage.open` calls `_open`, and `Storage.save`, once it has settled the name, calls `_save` (`django/core/files/storage/base.py:Storage`). A comment above them says they should not be overridden unless absolutely necessary; a backend writes the private pair. The naming is the base class's: `Storage.get_valid_name`, `Storage.generate_filename`, and `Storage.get_available_name` with its two steps, `Storage.is_name_available` and `Storage.get_alternative_name`. `Storage.delete`, `Storage.exists`, `Storage.listdir`, `Storage.size`, `Storage.url`, the three times (`Storage.get_modified_time` and its siblings) and `Storage.path`, a local path for Python's `open`, raise `NotImplementedError` until a backend defines them. The documentation lets a backend leave some out (`docs/howto/custom-file-storage.txt`), but the inherited `is_name_available` calls `exists`, so `save` needs it.

## `Storage.save`

`Storage.save` takes a name, the content and, optionally, a maximum length, and returns the name it used (`django/core/files/storage/base.py:Storage.save`). Given `None` for a name, it takes the content's; content without a `chunks` method, such as a plain Python file, it wraps in a `File` ([Files: `File`, `ContentFile` and their helpers](files.md)). Then it checks the name before and after each of the two steps that may change it, `get_available_name` and `_save`, and returns what `_save` gave back.

Each check is `validate_file_name`, which raises `SuspiciousFileOperation` for a name whose last part is empty, `"."` or `".."`, or which, read with forward slashes, is absolute or has `".."` among its parts (`django/core/files/utils.py:validate_file_name`). The comment in `save` says this duplicates a check inside `get_available_name`, for a subclass that overrides it and loses the validation.

The example's Manifest.scan is a file field with `upload_to="manifests/"` over the default storage. Two new manifests were each given a scan named "scan.txt"; a run that printed the calls recorded the second save, the field's own check of the name left out:

```text figure=naming-a-file
second.scan.save("scan.txt", ContentFile(b"four crates of cod"))
  FileField.generate_filename(instance, "scan.txt")
    upload_to "manifests/" put in front              "manifests/scan.txt"
    Storage.generate_filename: get_valid_name        "scan.txt": nothing to clean
  Storage.save(name, content, max_length=100)        100: the length of the column "scan"
    validate_file_name
    get_available_name
      validate_file_name("scan.txt")                 the file name alone
      is_name_available("manifests/scan.txt")        False: the first manifest's scan has it
      get_alternative_name("scan", ".txt")           "scan_z7slDDE.txt" (over 100: the root cut, drawn again)
      is_name_available(the alternative)             True (False: another alternative)
    validate_file_name
    FileSystemStorage._save                          the file created under MEDIA_ROOT
                                                     (FileExistsError: get_available_name again, with no max_length)
    validate_file_name
    -> "manifests/scan_z7slDDE.txt"
  the name set on the instance, and the instance saved
```

*The second manifest's scan, from the name the file came with to the name in its row: the field puts its directory in front and the storage cleans the file name; `Storage.save` checks the name around `get_available_name`, which found it taken and drew another, and `_save`.*

The first save had found "manifests/scan.txt" free:

```text
Manifest.objects.values_list("serial", "scan") -> [('M-0001', 'manifests/scan.txt'), ('M-0002', 'manifests/scan_z7slDDE.txt')]
first.scan.url, second.scan.url -> ('/media/manifests/scan.txt', '/media/manifests/scan_z7slDDE.txt')
```

## A free name: `get_available_name`

`Storage.get_available_name` refuses a directory with `".."` among its parts and validates the file name (`django/core/files/storage/base.py:Storage.get_available_name`). The extension is every suffix of the file name, so "scan.2026.txt" has the root "scan" and the extension ".2026.txt". While `is_name_available` says no (`exists` finds the name, or it is over the maximum length), the method tries a name made by `get_alternative_name`: the root, an underscore, seven random letters and digits from `get_random_string`, and the extension. An alternative that is too long has its root cut by as much as it is over before another is drawn; when no root is left, a `SuspiciousFileOperation` asks for a larger maximum. Since length counts as taken, a free name that is too long gets the random characters as well as the cut. From the run (long is a free name of 91 characters):

```text
save("manifests/scan.2026.txt", ...), the name taken -> 'manifests/scan_BP7bfxi.2026.txt'
save(long, ..., max_length=60) -> 'manifests/endorsement-of-the-harbour-master-for-_U1aH7as.txt' 60
```

## A clean name: `get_valid_name` and `generate_filename`

`Storage.get_valid_name` calls `get_valid_filename`, which strips the ends, turns spaces into underscores and drops every character but letters and digits of any script, dashes, underscores and dots; a result that is empty, `"."` or `".."` raises `SuspiciousFileOperation` (`django/utils/text.py:get_valid_filename`). `Storage.generate_filename` cleans the last part of a path so, refuses `".."` in its directory, and normalizes it (`django/core/files/storage/base.py:Storage.generate_filename`); a file field calls it on the name its `upload_to` gives ([File fields](../models/files.md)). `save` cleans nothing, as a save to "scans", a second alias of the example's with `"base_url": "/scans"`, shows:

```text
get_valid_name("Harbour master's scan (2).txt") -> 'Harbour_masters_scan_2.txt'
storages["scans"].save("Endeavour 12 Oct.txt", ...) -> 'Endeavour 12 Oct.txt' ; url: /scans/Endeavour%2012%20Oct.txt
```

## `FileSystemStorage`: settings read late

The constructor of `FileSystemStorage` stores its arguments and reads no setting (`django/core/files/storage/filesystem.py:FileSystemStorage`). The storage uses cached properties, each the argument or, where that is `None`, a setting read at first use: `FileSystemStorage.location`, `MEDIA_ROOT`, made absolute either way; `FileSystemStorage.base_url`, `MEDIA_URL` (an argument gets a slash at its end); and the two modes, from `FILE_UPLOAD_PERMISSIONS` (`0o644`) and `FILE_UPLOAD_DIRECTORY_PERMISSIONS` (`None`) (`django/conf/global_settings.py`). The constructor connects `StorageSettingsMixin._clear_cached_properties` to `setting_changed`, which drops a property when its setting changes (`django/core/files/storage/mixins.py:StorageSettingsMixin`).

The class is `deconstructible`, as a storage must be for its field to go into a migration (`docs/howto/custom-file-storage.txt`), and the decorator keeps only the arguments given (`django/utils/deconstruct.py:deconstructible`): the example's default storage deconstructs to its class's path and no arguments, naming no directory ([Serializing values: `serializer_factory` and `deconstruct`](../migrations/serializer.md)).

## `FileSystemStorage._save`

`FileSystemStorage._save` finds the path with `safe_join`, which raises `SuspiciousFileOperation` for one outside the location ([Paths and archives: `safe_join`, `safe_makedirs` and `extract`](../utils/paths.md)) (`django/utils/_os.py:safe_join`), and makes the missing directories, with `safe_makedirs` when a directory mode is set, since `os.makedirs` does not give the directories between its mode (the comment cites CPython issue 86533). Content with a `temporary_file_path`, an upload streamed to disk ([Upload handlers and uploaded files](../http/uploads.md#the-temporary-file)), it moves with `file_move_safe`, which raises `FileExistsError` if the destination exists. Other content it writes chunk by chunk, under an exclusive lock (`django/core/files/locks.py`), into a file opened with `os.O_CREAT` and `os.O_EXCL`, so that the open fails if the file exists (`django/core/files/storage/filesystem.py:FileSystemStorage._save`).

The comment explains the loop around the write: two threads may be given the same name, so on `FileExistsError` the method asks `get_available_name` again and retries. That call passes no maximum length, and a name found there is not cut to the column. Given a name the storage already had, `_save` saved under another:

```text
_save("manifests/scan.txt", ...), the name taken -> 'manifests/scan_Tnirf4g.txt'
```

The file then gets the file mode, if one is set, and on POSIX the location's group where it may; the name returned is relative to the location, with forward slashes even on Windows.

With `allow_overwrite=True`, `FileSystemStorage.is_name_available` considers only the length and `FileSystemStorage.get_alternative_name` returns the name unchanged, so a long name is only cut; `_save` opens with `os.O_TRUNC` in place of `os.O_EXCL`, and lets `file_move_safe` overwrite (`django/core/files/storage/filesystem.py:FileSystemStorage.is_name_available`).

## The rest of `FileSystemStorage`

Most other methods start from `FileSystemStorage.path`, the same `safe_join`. `FileSystemStorage.exists` is `os.path.lexists`, so a broken symbolic link counts; `FileSystemStorage.delete` ignores `FileNotFoundError`, which its comment puts down to a concurrent removal; `FileSystemStorage.url` joins the name, quoted by `filepath_to_uri`, to the base URL. The times are aware, in UTC, under `USE_TZ`, and naive local ones otherwise (`django/core/files/storage/filesystem.py:FileSystemStorage._datetime_from_timestamp`).

## `InMemoryStorage`

`InMemoryStorage` keeps its files in the instance, in a tree of nodes whose files are each an `InMemoryFileNode`, a `ContentFile` that keeps its times (`django/core/files/storage/memory.py:InMemoryStorage`). It inherits the naming and, given no location or base URL, takes them from `MEDIA_ROOT` and `MEDIA_URL`, but writes nothing to disk; the documentation offers it to speed up tests (`docs/ref/files/storage.txt`).
