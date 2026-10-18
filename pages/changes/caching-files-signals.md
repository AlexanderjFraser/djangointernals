---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in caching, files, signals, serialization and pagination

The keys of cached pages and fragments; `DatabaseCache`; `File`, overwriting a stored file and the storage settings; a signal's coroutine receivers; natural keys, JSON and XML in the serializers; and `AsyncPaginator` and orphans.

Most of what changed here since 5.2 renames nothing and warns of nothing: the same call gives another result. 6.1 made most of it. The key of every cached page or fragment that varies on values is new. `DatabaseCache` refuses a value that is not strict Base64, and `File` itself is always true. A signal's coroutine receivers run as one group, which changes what a sender meets when they fail. 6.0 and 6.2 each changed the JSON serializer's text. Only a paginator given too many orphans warns (6.0).

## The keys of cached pages and fragments

Since 6.1 the key of a cached page or fragment hashes each value it varies on as a netstring: its length in bytes, a colon, the bytes and a comma (`django/utils/cache.py:_generate_cache_key`, `django/core/cache/utils.py:make_template_fragment_key`). The cost, the notes say: the first request for a varying page or fragment cached before the upgrade misses (`docs/releases/6.1.txt`). One that varies on nothing hashes nothing, and keeps its key.

A page varies on the request headers its response's `"Vary"` names, bar Accept-Language while `USE_I18N` is true (`django/utils/cache.py:learn_cache_key`); a fragment of the `{% cache %}` tag, keyed by `make_template_fragment_key`, on the values it is given. Before 6.1 the values went into the hash run together: a header the request lacked added nothing to a page's, and a fragment's were each followed by a colon. So two lists that run together into the same text were given one key, the `True` of the old lines:

```text recording=changes
make_template_fragment_key("sidebar", ["a:b", "c"]) == make_template_fragment_key("sidebar", ["a", "b:c"])
    5.2.17       True
    6.0.8        True
    6.1.1        False
    this commit  False
```

Under 5.2.17 and 6.0.8 a page that varies on Accept-Encoding and Cookie had one key for a request sending only Accept-Encoding "EU" and one sending only Cookie "EU". Since 6.1 it has two ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md#two-keys-for-one-url)).

## `DatabaseCache`: strict Base64, and culling on a share of writes

Since 6.1 `DatabaseCache.get_many` decodes a row's Base64 strictly, refusing any character outside the alphabet; `DatabaseCache.get` reads through it (`django/core/cache/backends/db.py:DatabaseCache.get_many`). Under 6.0.8 a row with a newline put into its text still read as stored; under 6.1.1 `get` raises `binascii.Error`. Values Django writes are unaffected, the notes say; a corrupted or non-standard entry may no longer read (`docs/releases/6.1.txt`).

Before 6.2 each write counted the rows, and culled when they were more than `"MAX_ENTRIES"`. Since 6.2 a write does so only when `random.random()` is at most the alias's `"CULL_PROBABILITY"`, an optimization, the notes say (`docs/releases/6.2.txt`; `django/core/cache/backends/db.py:DatabaseCache._base_set`). The option is read from `"OPTIONS"`, 0.1 by default, and 0 turns culling off (`django/core/cache/backends/db.py:BaseDatabaseCache.__init__`; [The cache backends](../services/cache-backends.md)). The older releases ignore it: with `"MAX_ENTRIES"` 2 and `"CULL_PROBABILITY"` 0, five writes leave three rows under 6.1.1, and five at this commit.

## A `File` is always true

Since 6.1 `File.__bool__` returns `True` (`django/core/files/base.py:File.__bool__`). Before 6.1 a `File` was true only when its name was not empty: under 6.0.8 `bool(File(io.BytesIO(b"Monday")))` is `False`. The change reaches a `File` or an `ImageFile` around an unnamed stream. A `ContentFile` was already true: `bool(ContentFile(b"Monday"))` is `True` under all four releases.

`FieldFile` and `UploadedFile`, with the upload classes under it, keep the old test, so a file field holding no file is still false (`django/db/models/fields/files.py:FieldFile.__bool__`, `django/core/files/uploadedfile.py:UploadedFile.__bool__`; [Files: `File`, `ContentFile` and their helpers](../services/files.md)).

## Overwriting a stored file

Since 5.1 `FileSystemStorage` takes `allow_overwrite=`. Set true, it keeps a taken name, and `FileSystemStorage._save` opens the file with `os.O_TRUNC` in place of `os.O_EXCL`, so the save replaces the file (`django/core/files/storage/filesystem.py:FileSystemStorage._save`; [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)). It replaced the undocumented attribute OS_OPEN_FLAGS, which 5.1 deprecated and 6.0 removed (`docs/releases/5.1.txt`).

A storage written to overwrite before 5.1 could set that attribute without `os.O_EXCL`, and override `Storage.get_available_name` to return the name unchanged. 5.2.17's line is the overwrite such a storage was written for; 6.0.8 and 6.1.1 gave this commit's line, and are left out:

```text recording=changes
OS_OPEN_FLAGS without os.O_EXCL and get_available_name returning the name, on a FileSystemStorage subclass: storage.save("notes.txt", ...) when notes.txt exists
    5.2.17       notes.txt holds b'second', warns RemovedInDjango60Warning
...
    this commit  save() does not return: os.open refuses notes.txt, get_available_name gives the same name again (stopped at the tenth asking)
```

> **Trap.** Since 6.0 such a storage's save over an existing file never returns, and nothing warns. `_save` opens the file with `os.O_EXCL` whatever the subclass sets, and at each refusal asks `get_available_name` again, which gives the same name. An upload kept in a temporary file, a `TemporaryUploadedFile`, is moved into place rather than opened, and its save looped under 5.2.17 too.

## A signal's coroutine receivers, in a task group

Since 6.1 the coroutine receivers of one send run as tasks of one `asyncio.TaskGroup`, where `asyncio.gather` ran them. No release note lists it, only the topic guide (`django/dispatch/dispatcher.py:_run_parallel`; `docs/topics/signals.txt`). A receiver may be a coroutine function since 5.0, which added `Signal.asend` and `Signal.asend_robust` ([Signals: `Signal`, receivers and sending](../services/signals.md)).

Where two coroutine receivers raise the same error, the old lines pass one of the two to the sender; the new pass an `ExceptionGroup`, which `except ValueError` does not catch:

```text recording=changes
signal.send(None), two coroutine receivers raising ValueError: what reaches the sender
    5.2.17       ValueError: no berth
    6.0.8        ValueError: no berth
    6.1.1        ExceptionGroup: unhandled errors in a TaskGroup (2 sub-exceptions)
    this commit  ExceptionGroup: unhandled errors in a TaskGroup (2 sub-exceptions)
```

A lone failure is still raised as itself: `_run_parallel` unwraps a group of one. The group also cancels the receivers still running when one fails. Under 6.0.8 a waiting receiver of `asend` was still waiting when the sender had its error; at this commit it has been cancelled. `Signal.send_robust` and `asend_robust` catch any `Exception` a receiver raises, so the group sees none fail.

With the group, the coroutine receivers also share one copy of the sender's context, and what they set in it is set in the sender's when they finish (`django/dispatch/dispatcher.py:_restore_context`). Two receivers of `asend` each adding 1 to a `contextvars.ContextVar` the sender set to 1 leave it at 1 under 6.0.8, and at 3 at this commit.

Since 6.1 `asend` awaits its synchronous receivers before it starts the coroutine ones; before, the coroutine ones did not wait for them to return (`django/dispatch/dispatcher.py:Signal.asend`).

## Serialization

Since 6.2 `DjangoJSONEncoder` writes a datetime or a time to the millisecond only when its milliseconds are not zero, and to the second otherwise (`django/core/serializers/json.py:DjangoJSONEncoder.default`). The notes' example, one microsecond past the second, is `"2000-01-01T00:00:00.000"` under 6.1.1 and `"2000-01-01T00:00:00"` at this commit.

Since 6.0 the JSON serializer's text ends in a newline even when it is not indented: `serialize("json", [])` is `"[]"` under 5.2.17 and `"[]\n"` under 6.0.8 and later (`django/core/serializers/json.py:Serializer.end_serialization`).

Since 6.1 a `natural_key` that returns an empty tuple counts as none. Dumped with natural primary keys, such an object keeps its primary key, which 6.0.8 left out. Dumped with natural foreign keys, a relation to it is written as that key, not as the empty tuple 6.0.8 wrote (`django/core/serializers/python.py:Serializer.get_dump_object`, `django/core/serializers/python.py:Serializer.handle_fk_field`). The notes give it as a subclass's opt-out from its model's natural key ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](../services/serializers.md#natural-keys)).

Since 6.1 the XML deserializer raises `SuspiciousOperation` when a field's text holds an element with content of its own (`django/core/serializers/xml_serializer.py:check_element_type`). A title written `"<b>Valletta</b>"` read as `"Valletta"` under 6.0.8, and is refused at this commit.

Since 6.1 `DeserializedObject.save` sets each many-to-many relation with `raw=True`, so loaddata's relations send `m2m_changed` with `raw=True`, an argument new in 6.1 (`django/core/serializers/base.py:DeserializedObject.save`; [Fixtures: dumpdata and loaddata](../services/fixtures.md)).

## The smaller changes

The rest:

| what | change | where |
|---|---|---|
| `File.open` | Since 5.0, passes the arguments after the mode to Python's open when it reopens a closed file by its name | `django/core/files/base.py:File.open` |
| DEFAULT_FILE_STORAGE, STATICFILES_STORAGE | Gone in 5.1, with the function get_storage_class; nothing reads them | `django/core/files/storage/handler.py:StorageHandler.backends` |
| a format's `Deserializer` | Since 5.2, a class, where it was a function, in the Python, JSON, JSON Lines and YAML formats | `django/core/serializers/python.py:Deserializer` |
| a paginator's `error_messages=` | New in 5.0: merged by key over `BasePaginator.default_error_messages` | `django/core/paginator.py:BasePaginator.__init__` |
| `AsyncPaginator`, `AsyncPage` | New in 6.0: over a queryset not yet fetched, an `AsyncPage`'s length and indexes raise `TypeError` until `AsyncPage.aget_object_list` has been awaited | [Pagination: `Paginator` and `Page`](../services/pagination.md#asyncpaginator-and-asyncpage) |
| a paginator's `orphans=` | Deprecated in 6.0: a value of the page's size or more warns, the pages counted as before; to raise `ValueError` in Django 2028 | [What still warns: the deprecations and the releases that end them](deprecations.md) |
