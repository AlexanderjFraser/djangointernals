---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Files: `File`, `ContentFile` and their helpers

`File` is the type Django uses for a file, whatever holds its bytes: it wraps a Python file object and gives it a name, a size, and reading in chunks and by lines; `ContentFile` does the same for bytes or a string held in memory. Beside them in `django.core.files` stand `ImageFile` and `get_image_dimensions`, `validate_file_name`, and the helpers that lock files, move them and make temporary ones.

A file reaches Django in many forms: an upload in memory or in a temporary file, a file opened from disk, bytes just made, a name in a storage. A storage or a file field needs the same of each: a name, a size, and the bytes in pieces small enough that a large file is never held whole. `File` is that common shape. The uploaded files are subclasses of it ([Upload handlers and uploaded files](../http/uploads.md#uploadedfile-and-its-subclasses)), and so is a file field's `FieldFile` ([File fields](../instance/files.md)) (`django/core/files/base.py:File`).

## What a `File` wraps

`File.__init__` keeps the object it is given, which may be `None`, takes the name from that object's `name` when none is passed, and copies its `mode` if it has one. The file methods come from `FileProxyMixin`: `read`, `seek`, `write` and the rest are properties that return the wrapped object's method of that name when they are looked up, so when `File.open` replaces a closed file with a newly opened one, they follow it. The mixin also gives `closed`, true when there is no wrapped object or it is closed, and `readable`, `writable` and `seekable`, with an answer for an object that lacks them (`django/core/files/utils.py:FileProxyMixin`).

A `File` is true in a boolean context, with a name or without one (`django/core/files/base.py:File.__bool__`). `FieldFile` and `UploadedFile`, with the upload classes under it, keep the older test, true only when the name is not empty: an instance whose file field is empty still has a `FieldFile`, which `FieldFile._require_file` tests before the file is used (`django/db/models/fields/files.py:FieldFile.__bool__`).

```python
# a shell in the harbour project
>>> from django.core.files import File
>>> from harbour.office.models import Manifest
>>> bool(File(None)), bool(Manifest().scan)
(True, False)
```

> **Changed in 6.1.** A `File` used to be true only when its name was not empty (`docs/releases/6.1.txt`).

## The size

`File.size` is found the first time it is asked for, in three ways tried in order: the wrapped object's own `size`; the size on disk of the path in its `name`, an `OSError` or a `TypeError` passing on to the next way; and, for an object that can seek, a seek to the end and back to where it was. With none of them it raises `AttributeError` with the message `"Unable to determine the file's size."`. The size is a `cached_property`, so writing through the wrapped object's `write` does not change it (`django/core/files/base.py:File.size`).

## Reading in chunks and by lines

`File.chunks` is a generator that rewinds the file with `seek(0)` where it can, then reads it `File.DEFAULT_CHUNK_SIZE` bytes at a time, 64 KiB unless a size is passed, until a read returns nothing, so a file that has been partly read is still read whole (`django/core/files/base.py:File.chunks`). `FileSystemStorage` writes a file from its chunks when it has no temporary file to move (`django/core/files/storage/filesystem.py:FileSystemStorage._save`). `File.multiple_chunks` answers whether the size exceeds one chunk; no code in Django calls it, and `InMemoryUploadedFile` answers false whatever its size (`django/core/files/uploadedfile.py:InMemoryUploadedFile.multiple_chunks`).

Iterating over a `File` gives lines, which `File.__iter__` assembles from the chunks: each chunk is split after its line endings, and a piece without one is held until the next chunk completes it. A line ends in `"\n"`, `"\r\n"` or a lone `"\r"`, and a `"\r"` at the end of a chunk is held too, until the next chunk shows whether a `"\n"` follows it (`django/core/files/base.py:File.__iter__`). Here a manifest written on Windows is read with the chunk size set on the instance to 20 bytes, so that the first chunk ends between a `"\r"` and its `"\n"`:

```python
# a shell in the harbour project
>>> from django.core.files.base import ContentFile
>>> scan = ContentFile(b"Endeavour  366 tons\r\nBeagle  235 tons\r\n", name="endeavour.txt")
>>> scan.size, scan.multiple_chunks()
(39, False)
>>> scan.DEFAULT_CHUNK_SIZE = 20
>>> list(scan.chunks())
[b'Endeavour  366 tons\r', b'\nBeagle  235 tons\r\n']
>>> list(scan)
[b'Endeavour  366 tons\r\n', b'Beagle  235 tons\r\n']
```

## Opening and closing

`File.open`, on a file that is still open, only rewinds it and ignores the mode it is given. On a closed file whose name is a path that exists, it opens the path again with the built-in `open`, in the mode given or else the file's own, and puts the new file object in place of the old. Otherwise it raises `ValueError`: a closed file without a name, or whose name is no path that exists, cannot be reopened. It returns the `File`; leaving a with statement on it calls `File.close`, which closes the wrapped object (`django/core/files/base.py:File.open`).

## `ContentFile`

`ContentFile` wraps a string in an `io.StringIO` and anything else in an `io.BytesIO`, and sets the size at once to the content's length: for a string, in characters, not encoded bytes. `ContentFile.close` does nothing and `ContentFile.open` only rewinds, so a `ContentFile` can be read again after any code has closed it. `ContentFile.write` writes at the stream's current position, the start for a new one, and drops the size, so that the next request for it seeks to the end (`django/core/files/base.py:ContentFile`).

## Images: `ImageFile` and `get_image_dimensions`

`ImageFile` is a `File` with `ImageFile.width` and `ImageFile.height`, read together once and kept; to read them it opens the file, and closes it again if it was closed before (`django/core/files/images.py:ImageFile._get_image_dimensions`). The `ImageFieldFile` of a `django.db.models.ImageField` is built on it ([File fields](../instance/files.md)). `get_image_dimensions` takes an open file or a path, imports Pillow only when it is called, and feeds Pillow's incremental parser chunks of 1,024 bytes, doubling each time, until the parser knows the image's size. Three errors that more data may cure are passed over and more is fed: a truncated zlib stream (ticket 19457), a buffer too short to unpack (ticket 24544), and any `RuntimeError`, such as a WebP decoder's. A file that runs out first, or a path that will not open, gives `(None, None)`, and an open file is put back where it was, or closed when close is true (`django/core/files/images.py:get_image_dimensions`).

## Names, locks, moves and temporary files

`validate_file_name` raises `SuspiciousFileOperation` for a name whose last part is empty, `"."` or `".."`, and, unless relative paths are allowed, for any name with a directory in it; when they are, for an absolute path or one that climbs with `".."` (`django/core/files/utils.py:validate_file_name`). The storages, the file fields and the uploaded files call it; [File storage: `Storage`, `FileSystemStorage` and `storages`](storage.md) tells where.

The module `django.core.files.locks` gives `lock`, with `LOCK_EX` or `LOCK_SH`, and `LOCK_NB` added for a lock that does not wait, and `unlock`, each taking a file object or a descriptor (`django/core/files/locks.py`). On Windows they call the system's LockFileEx and UnlockFileEx through ctypes; elsewhere flock from fcntl, `lock` returning false when a non-blocking lock is refused; where fcntl cannot be imported, the flags are 0 and the functions do nothing. `FileSystemStorage` holds an exclusive lock while it writes a file, and `FileBasedCache` while it rewrites an entry's expiry ([The cache backends](cache-backends.md)).

`file_move_safe` moves a file: nothing if the two paths are one file, `FileExistsError` if the destination exists and overwriting is not allowed, else a rename. When the rename fails, as it does across file systems, it copies in chunks into a destination opened exclusively, unless overwriting is allowed, and locked, then gives it the source's permissions and times and removes the source (`django/core/files/move.py:file_move_safe`). `FileSystemStorage` moves an upload's temporary file into place with it, and `FileBasedCache` each entry it sets.

`NamedTemporaryFile` in `django.core.files.temp` is the standard library's everywhere but Windows, where it is a class of Django's own, made with mkstemp and deleting its file when it is closed (`django/core/files/temp.py`). An upload kept on disk is written into one, a `TemporaryUploadedFile` ([Upload handlers and uploaded files](../http/uploads.md#the-temporary-file)).

> **Why.** The module's docstring: on Windows the standard library's class opens the file with the flag O_TEMPORARY, and the file cannot then be opened again by its name without the same flag; Django's can be reopened in the same process.
