---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in caching, files, signals, serialization and pagination

The changes from Django 5.0 to this commit in the services beside the request cycle: the keys of cached pages and fragments; `DatabaseCache`; `File` and the storage's overwriting and settings; a signal's coroutine receivers; natural keys, JSON and XML in the serializers; and `AsyncPaginator` and orphans.

Most of what changed here since 5.2 renames nothing and warns of nothing: the same call gives another result. 6.1 made most of it. It hashed the values a cached page or fragment varies on as netstrings, so that two lists of values cannot run together, and every such key changed; it made `DatabaseCache` refuse a value that is not strict Base64, and `File` itself always true; and it ran a signal's coroutine receivers as tasks of one group, which changes what a sender meets when they fail. 6.0 and 6.2 each changed the JSON serializer's text. Only a paginator given too many orphans warns (6.0).

## The keys of cached pages and fragments

A cached page's key hashes the values of the request headers its response's `"Vary"` names, and a fragment's key, made by `make_template_fragment_key` for the `{% cache %}` tag, hashes the values it varies on. Before 6.1 the values went into the hash run together: a header the request lacked added nothing to a page's, and a fragment's were each followed by a colon. Since 6.1 each goes in as a netstring: its length in bytes, a colon, the bytes and a comma (`django/utils/cache.py:_generate_cache_key`, `django/core/cache/utils.py:make_template_fragment_key`). Here two lists of values run together into the same text, which gave them one key before 6.1:

```text recording=changes
make_template_fragment_key("sidebar", ["a:b", "c"]) == make_template_fragment_key("sidebar", ["a", "b:c"])
    5.2.17       True
    6.0.8        True
    6.1.1        False
    this commit  False
```

Under 5.2.17 and 6.0.8 a page that varies on Accept-Encoding and Cookie had one key for a request sending only Accept-Encoding "EU" and one sending only Cookie "EU"; since 6.1 it has two. The cost, the notes say: the first request for a varying page or fragment cached before the upgrade misses (`docs/releases/6.1.txt`). One that varies on nothing hashes nothing, and keeps its key ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md#two-keys-for-one-url)).

## `DatabaseCache`: strict Base64, and culling on a share of writes

`DatabaseCache` keeps each value pickled, in Base64, in a row. Since 6.1 `DatabaseCache.get_many`, through which `DatabaseCache.get` reads, decodes it strictly, refusing any character outside the alphabet (`django/core/cache/backends/db.py:DatabaseCache.get_many`). Under 6.0.8 a row with a newline put into its text still read as stored, the newline dropped; under 6.1.1 `get` raises `binascii.Error`. Values Django writes are unaffected, the notes say; a corrupted or non-standard entry may no longer read (`docs/releases/6.1.txt`).

Before 6.2 each write counted the rows, and culled when they were more than `"MAX_ENTRIES"`. Since 6.2 a write does so only when `random.random()` is at most the alias's `"CULL_PROBABILITY"`, as an optimization, the notes say (`docs/releases/6.2.txt`; `django/core/cache/backends/db.py:DatabaseCache._base_set`). `BaseDatabaseCache.__init__` reads it from `"OPTIONS"`: 0.1 when absent or refused by `float`, and 0 turns culling off (`django/core/cache/backends/db.py:BaseDatabaseCache.__init__`). The older releases ignore the option: with `"MAX_ENTRIES"` 2 and `"CULL_PROBABILITY"` 0, five writes leave three rows under 6.1.1, culled by each write that found more than two, and five at this commit ([The cache backends](../services/cache-backends.md)).

## A `File` is always true

Before 6.1 a `File` was true only when its name was not empty: under 6.0.8 `bool(File(io.BytesIO(b"Monday")))` is `False`. Since 6.1 `File.__bool__` returns `True` (`django/core/files/base.py:File.__bool__`). A `ContentFile` was already true, by a `__bool__` of its own that 6.1 removed: `bool(ContentFile(b"Monday"))` is `True` under all four releases; the change reaches a `File` or an `ImageFile` around an unnamed stream. `FieldFile` and `UploadedFile`, with the upload classes under it, keep the old test (`django/db/models/fields/files.py:FieldFile.__bool__`, `django/core/files/uploadedfile.py:UploadedFile.__bool__`), so a file field holding no file is still false ([What changed in models and fields](models.md), [Files: `File`, `ContentFile` and their helpers](../services/files.md)).

## Overwriting a stored file, and the storage settings

`FileSystemStorage` has taken allow_overwrite since 5.1: set true, it keeps a taken name, and `FileSystemStorage._save` opens the file with `os.O_TRUNC` in place of `os.O_EXCL`, so the save replaces the file (`django/core/files/storage/filesystem.py:FileSystemStorage.is_name_available`, `django/core/files/storage/filesystem.py:FileSystemStorage._save`; [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)). The 5.1 notes give it in place of the undocumented attribute OS_OPEN_FLAGS, deprecated then and removed in 6.0 (`docs/releases/5.1.txt`). A storage written to overwrite before 5.1 could set that attribute without `os.O_EXCL` and override `Storage.get_available_name` to return the name unchanged. Here such a storage saves over a file; 6.0.8 and 6.1.1 gave this commit's line and are left out:

```text recording=changes
OS_OPEN_FLAGS without os.O_EXCL and get_available_name returning the name, on a FileSystemStorage subclass: storage.save("notes.txt", ...) when notes.txt exists
    5.2.17       notes.txt holds b'second', warns RemovedInDjango60Warning
...
    this commit  save() does not return: os.open refuses notes.txt, get_available_name gives the same name again (stopped at the tenth asking)
```

> **Trap.** From 6.0 that storage's save over an existing file never returns, and nothing warns: `_save` opens the file with `os.O_EXCL` whatever the subclass sets, and asks `get_available_name` again at each refusal, which gives the same name. Only an upload kept in a temporary file, a `TemporaryUploadedFile`, is moved into place instead, and its save looped under 5.2.17 too.

The settings DEFAULT_FILE_STORAGE and STATICFILES_STORAGE, deprecated in 4.2, were removed in 5.1 with the function get_storage_class, leaving `STORAGES` alone (`docs/releases/5.1.txt`; `django/core/files/storage/handler.py:StorageHandler.backends`). Nothing reads the old settings: DEFAULT_FILE_STORAGE set to `InMemoryStorage` leaves `storages["default"]` a `FileSystemStorage` under all four releases.

## A signal's coroutine receivers, in a task group

A receiver may be a coroutine function since 5.0, which added `Signal.asend` and `Signal.asend_robust` ([Signals: `Signal`, receivers and sending](../services/signals.md)). Since 6.1 the coroutine receivers of one send run as tasks of one `asyncio.TaskGroup`, where `asyncio.gather` ran them. No release note lists it, only the topic guide (`django/dispatch/dispatcher.py:_run_parallel`; `docs/topics/signals.txt`). Here two receivers raise the same error; before 6.1 one of the two reached the sender, and since then an `ExceptionGroup` does, which `except ValueError` does not catch:

```text recording=changes
signal.send(None), two coroutine receivers raising ValueError: what reaches the sender
    5.2.17       ValueError: no berth
    6.0.8        ValueError: no berth
    6.1.1        ExceptionGroup: unhandled errors in a TaskGroup (2 sub-exceptions)
    this commit  ExceptionGroup: unhandled errors in a TaskGroup (2 sub-exceptions)
```

A lone failure is still raised as itself: `_run_parallel` unwraps a group of one. The group also cancels the receivers still running when one fails: under 6.0.8 a waiting receiver of `asend` was still waiting when the sender had its error, and at this commit it has been cancelled. `Signal.send_robust` and `asend_robust` catch any `Exception` a receiver raises, so the group sees none fail.

With the group, the coroutine receivers also share one copy of the sender's context, and what they set in it is set in the sender's when they finish (`django/dispatch/dispatcher.py:_restore_context`): two receivers of `asend` each adding 1 to a `contextvars.ContextVar` the sender set to 1 leave it at 1 under 6.0.8, and at 3 at this commit. And `asend` now awaits its synchronous receivers before it starts the coroutine ones, which before 6.1 did not wait for them to return (`django/dispatch/dispatcher.py:Signal.asend`).

## Serialization

Since 6.2 `DjangoJSONEncoder` writes a datetime or a time to the millisecond only when its milliseconds are not zero, and to the second otherwise (`django/core/serializers/json.py:DjangoJSONEncoder.default`). The notes' example is one microsecond past the second, its milliseconds zero:

```text recording=changes
DjangoJSONEncoder().encode(datetime.datetime(2000, 1, 1, 0, 0, 0, 1)): one microsecond
    5.2.17       "2000-01-01T00:00:00.000"
    6.0.8        "2000-01-01T00:00:00.000"
    6.1.1        "2000-01-01T00:00:00.000"
    this commit  "2000-01-01T00:00:00"
```

Before 6.2 any microseconds gave three digits of milliseconds, zeros included. In 6.0 the JSON serializer's text came to end in a newline even when not indented: `serialize("json", [])` is `"[]"` under 5.2.17 and `"[]\n"` since 6.0 (`django/core/serializers/json.py:Serializer.end_serialization`).

Since 6.1 a `natural_key` that returns an empty tuple counts as none. Dumped with natural primary keys, such an object is written with its primary key, which 6.0.8 left out; dumped with natural foreign keys, a relation to it is written as that key, where 6.0.8 wrote the empty tuple (`django/core/serializers/python.py:Serializer.get_dump_object`, `django/core/serializers/python.py:Serializer.handle_fk_field`). The notes give it as a subclass's opt-out from its model's natural key ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](../services/serializers.md#natural-keys)).

Since 6.1 the XML deserializer raises `SuspiciousOperation` when a field's text holds an element with content of its own, and passes over an empty one (`django/core/serializers/xml_serializer.py:check_element_type`): a title written `"<b>Valletta</b>"` read as `"Valletta"` under 6.0.8, and is refused at this commit.

Since 6.1 `DeserializedObject.save` sets each many-to-many relation with `raw=True`, so loaddata's relations send `m2m_changed` with `raw=True` (`django/core/serializers/base.py:DeserializedObject.save`; [Fixtures: dumpdata and loaddata](../services/fixtures.md)). The argument, new in 6.1, is told in [What changed in models and fields](models.md).

## The smaller changes

The rest:

| what | at this commit | release | where |
|---|---|---|---|
| `File.open` | passes the arguments after the mode to Python's open, reopening a closed file by its name | 5.0 | `django/core/files/base.py:File.open` |
| a paginator's error_messages | new, merged by key over `BasePaginator.default_error_messages` | 5.0 | `django/core/paginator.py:BasePaginator.__init__` |
| the deserializers | the Python, JSON, JSON Lines and YAML formats' each a class, where it was a function | 5.2 | `django/core/serializers/python.py:Deserializer` |
| `AsyncPaginator`, `AsyncPage` | new; over a queryset not yet fetched, an `AsyncPage`'s length and indexes raise `TypeError` until `AsyncPage.aget_object_list` has been awaited, which makes its objects a list | 6.0 | [Pagination: `Paginator` and `Page`](../services/pagination.md#asyncpaginator-and-asyncpage) |
| orphans not fewer than the page | a warning, the pages counted as before; to raise `ValueError` in Django 2028 | 6.0 | [What still warns: the deprecations and the releases that end them](deprecations.md) |
