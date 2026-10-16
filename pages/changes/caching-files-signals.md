---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in caching, files, signals, serialization and pagination

The changes from Django 5.0 to this commit in the services beside the request cycle: the keys of cached pages and fragments, and how `DatabaseCache` reads and culls; `File`, `FileSystemStorage` and the storage settings; coroutine receivers, `Signal.asend` and the task group; the serializers' classes, natural keys and output; and `AsyncPaginator` and a paginator's orphans.

Several of these changes are silent: a cached page or fragment that varies is stored under a new key (6.1), a `File` without a name became true (6.1), and the JSON serializer's text changed twice (6.0, 6.2).

## The keys of cached pages and fragments

A cached page's key hashes the values of the request headers that its response's `"Vary"` names, all but Accept-Language while `USE_I18N` is true (`django/utils/cache.py:learn_cache_key`), and a fragment's key, made by `make_template_fragment_key` for the `{% cache %}` tag, hashes the values it varies on. Since 6.1 each value goes into the hash as a netstring: its length in bytes, a colon, the bytes and a comma (`django/utils/cache.py:_generate_cache_key`, `django/core/cache/utils.py:make_template_fragment_key`).

So two lists of values get different keys even where joining them, run together or with colons between, would give one string. Django's tests check the headers `"EU"` then nothing against nothing then `"EU"`, and the fragment's values `"a:b"` then `"c"` against `"a"` then `"b:c"` (`tests/cache/tests.py:CacheUtils.test_learn_cache_key_no_header_collision`, `tests/cache/tests.py:TestMakeTemplateFragmentKey.test_collision_vary_on`). The release notes give the cost: after the upgrade, the first request for a page or fragment stored so is a miss (`docs/releases/6.1.txt`). A page or fragment that varies on nothing hashes nothing, and keeps its key ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md#two-keys-for-one-url)).

## `DatabaseCache`: strict Base64 and culling by chance

`DatabaseCache.get_many`, which `DatabaseCache.get` calls, has decoded each unexpired value with strict Base64 since 6.1, so a value with a character outside the alphabet raises `binascii.Error` where, in the release notes' words, it was silently ignored (`django/core/cache/backends/db.py:DatabaseCache.get_many`). In a run, a newline put into a row made `get` raise `binascii.Error: Only base64 data is allowed`.

Until 6.2 every write counted the table's rows to see whether to cull. Now a write counts and culls only when a random draw is at most `"CULL_PROBABILITY"` of the alias's `"OPTIONS"`, an optimisation in the release notes' words (`django/core/cache/backends/db.py:DatabaseCache._base_set`). `BaseDatabaseCache.__init__` reads the option: 0.1 when it is absent or `float` refuses it, and 0 turns culling off (`django/core/cache/backends/db.py:BaseDatabaseCache.__init__`; [The cache backends](../services/cache-backends.md)).

## Files and storage

`File.__bool__` returns `True` since 6.1; a `File` used to be true only when its name was not empty. The release notes list the subclasses that keep that test, `FieldFile` and `UploadedFile` with the upload classes under it (`django/core/files/base.py:File.__bool__`, `django/db/models/fields/files.py:FieldFile.__bool__`, `django/core/files/uploadedfile.py:UploadedFile.__bool__`). So a file field's value is still false when it holds no file ([File fields](../models/files.md)), while a `File` or a `ContentFile` made without a name is now true ([Files: `File`, `ContentFile` and their helpers](../services/files.md)).

`File.open` gives the arguments after the mode to the built-in `open` since 5.0, when it reopens a closed file whose name is a path that exists; a file still open is only rewound (`django/core/files/base.py:File.open`).

`FileSystemStorage` has taken `allow_overwrite=True` since 5.1. The 5.1 notes give it in place of the undocumented attribute OS_OPEN_FLAGS, deprecated then and removed in 6.0. With `allow_overwrite=True`, `FileSystemStorage._save` opens the content it streams with `os.O_TRUNC` in place of `os.O_EXCL` and moves a temporary file over an existing one (`django/core/files/move.py:file_move_safe`), `FileSystemStorage.is_name_available` looks only at the length, and `FileSystemStorage.get_alternative_name` returns the name unchanged, so a file saved under a taken name replaces the one there (`django/core/files/storage/filesystem.py:FileSystemStorage._save`; [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)).

The settings DEFAULT_FILE_STORAGE and STATICFILES_STORAGE were removed in 5.1, and the function get_storage_class with them. The default storages come from `STORAGES` alone: `default_storage` stands for its `"default"` alias and `staticfiles_storage` for its `"staticfiles"` alias (`django/core/files/storage/__init__.py:DefaultStorage`, `django/contrib/staticfiles/storage.py:ConfiguredStorage`). Nothing reads the old settings or warns of them: in a run that set DEFAULT_FILE_STORAGE to the path of `InMemoryStorage`, configuring gave no warning and the default storage was a `FileSystemStorage`.

## Signals: coroutine receivers and the task group

A receiver may be a coroutine function since 5.0. `Signal.send` calls the synchronous receivers in order and then runs the coroutine functions through one `async_to_sync`; `Signal.asend` and `Signal.asend_robust`, new in 5.0, run the synchronous receivers through one `sync_to_async` and then the coroutine functions on the caller's loop (`django/dispatch/dispatcher.py:Signal.send`, `django/dispatch/dispatcher.py:Signal.asend`; [Signals: `Signal`, receivers and sending](../services/signals.md)).

Since 6.1 the coroutine receivers of one send run as tasks of one `asyncio.TaskGroup`, where they used to be run with asyncio's gather (`django/dispatch/dispatcher.py:_run_parallel`; `docs/topics/signals.txt`). When one raises, the group cancels those still running; a lone exception reaches the sender as itself, two or more as an `ExceptionGroup`. In a run, a coroutine receiver raising `ValueError` at once had another, asleep, cancelled, and `Signal.send` raised the `ValueError`; with a third raising at once, it raised an `ExceptionGroup` of two. `Signal.send_robust` and `asend_robust` catch each coroutine receiver's exception, and the group sees no failure.

## Serialization

The deserializers of the Python, JSON, JSON Lines and YAML formats have been classes since 5.2, where they were functions, for extensibility in a project's own formats, the release notes say (`docs/releases/5.2.txt`). The last three subclass the Python format's `Deserializer` and hand it their parsed text; it builds each object in `_handle_object`, calling `_handle_fk_field_node`, `_handle_m2m_field_node` and `_get_model_from_node`, which a subclass may override (`django/core/serializers/python.py:Deserializer`).

The JSON serializer's output has ended in a newline since 6.0, indented or not (`django/core/serializers/json.py:Serializer.end_serialization`). Since 6.2 `DjangoJSONEncoder` writes a datetime or a time to the millisecond only when its milliseconds are not zero, and otherwise to the second; the release notes' example, a datetime with one microsecond, was written with `".000"` before (`django/core/serializers/json.py:DjangoJSONEncoder.default`).

```text
# a run at this commit: DjangoJSONEncoder().encode(value), and serialize("json", [])
datetime.datetime(2000, 1, 1, 0, 0, 0, 1)       "2000-01-01T00:00:00"
datetime.datetime(2000, 1, 1, 0, 0, 0, 1500)    "2000-01-01T00:00:00.001"
serialize("json", [])                           '[]\n'
```

A `natural_key` that returns an empty tuple counts as none since 6.1: under `use_natural_primary_keys=True` the object is written with its primary key, and under `use_natural_foreign_keys=True` a relation to it as it is written without natural keys (`django/core/serializers/python.py:Serializer.get_dump_object`, `django/core/serializers/python.py:Serializer.handle_fk_field`, `django/core/serializers/python.py:Serializer.handle_m2m_field`). The release notes give it as the way for a subclass of a model with `natural_key` to opt out ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](../services/serializers.md#natural-keys)).

The XML deserializer raises `SuspiciousOperation` since 6.1 when a field's text holds an element with content of its own, and passes over an empty one (`django/core/serializers/xml_serializer.py:check_element_type`). In a run, a port's name written as `"<b>Valletta</b>"` raised `SuspiciousOperation: Unexpected element: 'b'`. The fix of 5.1.15 and 5.2.9 to the time `getInnerText` took over nested elements is told in [Security fixes: limits against denial of service](security-fixes-limits.md).

`DeserializedObject.save` has set each many-to-many relation with `raw=True` since 6.1, so the relations loaddata sets send `m2m_changed` with raw true, as `pre_save` and `post_save` already were (`django/core/serializers/base.py:DeserializedObject.save`; [Fixtures: dumpdata and loaddata](../services/fixtures.md)). The signal's new argument is told in [What changed in models and fields](models.md).

## Pagination

A paginator has taken `error_messages=` since 5.0, merged by key over `BasePaginator.default_error_messages`, the messages that `BasePaginator._validate_number` raises with (`django/core/paginator.py:BasePaginator.__init__`).

`AsyncPaginator` and `AsyncPage` came in 6.0, and what `AsyncPaginator` shares with `Paginator` is in their base class, `BasePaginator` (`django/core/paginator.py:BasePaginator`). `AsyncPage` is not a sequence: its length and indexes raise `TypeError` while its objects are not a list, until `AsyncPage.aget_object_list` makes them one (`django/core/paginator.py:AsyncPage`; [Pagination: `Paginator` and `Page`](../services/pagination.md#asyncpaginator-and-asyncpage)).

Since 6.0 `BasePaginator.__init__` warns with `RemovedInDjango2028Warning` when the orphans are not fewer than the page size, and a comment there gives the `ValueError` it is to raise in Django 2028 (`django/core/paginator.py:BasePaginator.__init__`; [What still warns: the deprecations and the releases that end them](deprecations.md)).
