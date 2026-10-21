---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The cache API: `caches` and `BaseCache`

`django.core.cache.caches`, a `CacheHandler`, makes a backend for each alias of `CACHES`, and `cache` stands for the backend of `"default"`. Every backend Django ships is a subclass of `BaseCache`, which reads the alias's options, makes the key the backend uses, turns a timeout into a moment of expiry, and builds the rest of the API, asynchronous half included, on the few methods each backend writes.

Code that caches gives a key, a value, perhaps a timeout and a version, and expects the same calls to work whatever the store. So a backend writes the methods that touch its store ([The cache backends](cache-backends.md)), and `BaseCache` does what is the same for all (`django/core/cache/backends/base.py:BaseCache`).

## `caches`, `cache` and the handler

`CacheHandler` is a `BaseConnectionHandler`, as the database's handler is ([Connections by alias: `DATABASES` and `ConnectionHandler`](../connections/aliases.md)). `CacheHandler.create_connection` copies the alias's dictionary, pops `"BACKEND"` and `"LOCATION"`, the location defaulting to the empty string, imports the class and calls it with the location and the rest of the dictionary (`django/core/cache/__init__.py:CacheHandler.create_connection`). The location is a name, a directory, a table or servers, by backend. A class that will not import, and an alias `CACHES` lacks, are refused with `InvalidCacheBackendError`, the second as `CacheHandler.exception_class` (`django/utils/connection.py:BaseConnectionHandler.__getitem__`).

The handler leaves `BaseConnectionHandler.thread_critical` false, where the database's handler sets it, so its asgiref `Local` is a context variable (`asgiref:asgiref/local.py:Local`): each thread still makes its own backends, but code run through `sync_to_async` or `async_to_sync` sees its caller's.

`cache` is a `ConnectionProxy` of the handler and `DEFAULT_CACHE_ALIAS`: each read of an attribute the proxy lacks, each attribute set or deleted on it, and `in` and `==`, go to `caches["default"]`, looked up again each time (`django/utils/connection.py:ConnectionProxy`). The example's settings, with a second alias:

```python
# harbour/settings.py, in part
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "harbour"},
    "berths": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "berths",
        "TIMEOUT": 60, "KEY_PREFIX": "office", "VERSION": 2,
    },
}
```

```text
cache is caches["default"]  ->  False
cache == caches["default"]  ->  True
caches["nosuch"]  ->  raises InvalidCacheBackendError: The connection 'nosuch' doesn't exist.
```

`close_caches`, a receiver of `request_finished`, closes the backends the current thread or context has made (`django/core/cache/__init__.py:close_caches`). `BaseCache.close` does nothing; of Django's backends only `PyMemcacheCache` acts on closing.

## The options: `BaseCache.__init__`

`BaseCache.__init__` reads the rest of the dictionary (`django/core/cache/backends/base.py:BaseCache.__init__`):

| option | default | kept as |
|---|---|---|
| `"TIMEOUT"` | 300 | `BaseCache.default_timeout` |
| `"MAX_ENTRIES"`, in `"OPTIONS"` | 300 | `BaseCache._max_entries` |
| `"CULL_FREQUENCY"`, in `"OPTIONS"` | 3 | `BaseCache._cull_frequency` |
| `"KEY_PREFIX"` | `""` | `BaseCache.key_prefix` |
| `"VERSION"` | 1 | `BaseCache.version` |
| `"KEY_FUNCTION"` | `default_key_func` | `BaseCache.key_func` |

The first three go through `int`, a timeout of `None` excepted, and a value `int` refuses, such as `"five minutes"`, silently gives way to the default. Only the backends that cull, in memory, in files and in a table, use the culling options.

## Keys: `make_key` and `validate_key`

A backend works with the **made key**, made from the key the code gave. `BaseCache.make_key` passes the key, the prefix and a version, the call's or else the cache's, to the key function, and `default_key_func` joins the three with colons (`django/core/cache/backends/base.py:BaseCache.make_key`). In Django's documentation, a prefix keeps apart the Django instances that share one cache, and a version retires old values without clearing the rest (`docs/topics/cache.txt`). `get_key_func` uses a callable `"KEY_FUNCTION"` as it is and imports a dotted path (`django/core/cache/backends/base.py:get_key_func`).

```text
cache.make_key("sailings")  ->  ':1:sailings'
caches["berths"].make_key("sailings")  ->  'office:2:sailings'
caches["berths"].make_key("sailings", version=3)  ->  'office:3:sailings'
cache.set("berth list", [3, 7])  ->  None
  warns CacheKeyWarning: Cache key contains characters that will cause errors if used with memcached: ':1:berth list'
```

`BaseCache.validate_key` issues a `CacheKeyWarning` for each message of `memcache_key_warnings`: a key longer than `MEMCACHE_MAX_KEY_LENGTH`, 250, or holding a control character or a space (`django/core/cache/backends/base.py:memcache_key_warnings`). It is given the made key, so the prefix counts towards the length. It only warns, and the value is stored: its docstring says it encourages, but does not force, code that would run on Memcached, whose backends raise `InvalidCacheKey` instead.

`BaseCache.make_and_validate_key` does both, and is what a backend's own methods call on the key they are given; the methods `BaseCache` builds on them make no key, and pass the caller's down. The keys of `{% cache %}`, from `make_template_fragment_key`, are ordinary keys here ([The libraries to load: static, i18n, l10n, tz and cache](../templates/loadable-libraries.md)).

## Timeouts: `get_backend_timeout`

The methods that take a timeout default it to `DEFAULT_TIMEOUT`, a sentinel meaning none given, which leaves `None` to mean never. `BaseCache.get_backend_timeout` makes the sentinel the cache's default, keeps `None`, and adds a number of seconds to `time.time()`, giving the moment of expiry (`django/core/cache/backends/base.py:BaseCache.get_backend_timeout`). A timeout of 0 given in a call keeps nothing: it is made -1, so the expiry is already past, the comment citing ticket 21147 and the precision of `time.time()`. Memcached's and Redis's backends replace it.

## The methods built on a backend's own

`BaseCache` raises `NotImplementedError` from `BaseCache.add`, `BaseCache.get`, `BaseCache.set`, `BaseCache.touch`, `BaseCache.delete` and `BaseCache.clear`. Their docstrings fix their returns: `add`, whether it stored the value, which it does only for an absent key; `touch`, whether the key was there; `delete`, whether it succeeded (`django/core/cache/backends/base.py:BaseCache.add`). The rest, but for `BaseCache.close`, have defaults built on these, which a backend may replace.

`BaseCache.get_many` and `BaseCache.has_key` call `get` with the sentinel `BaseCache._missing_key` as the default, so a stored `None` is told from an absent key. `BaseCache.__contains__` calls `has_key`, its comment says, so that `in` follows any override of it (`django/core/cache/backends/base.py:BaseCache.__contains__`). `BaseCache.set_many` and `BaseCache.delete_many` loop over `set` and `delete`; `set_many` returns an empty list of failed keys, which the Memcached backends fill.

`BaseCache.get_or_set` gets the key; on a miss it calls the default if callable, `add`s the result and gets the key again (`django/core/cache/backends/base.py:BaseCache.get_or_set`). The comment's reason for the second `get`: another caller may have added a value meanwhile, which `add` left in place. The computed value, as that `get`'s default, is returned even when nothing was kept:

```text
cache.add("tide", "high", 0)  ->  True
cache.get("tide")  ->  None
cache.get_or_set("tide", "high", 0)  ->  'high'
cache.get("tide")  ->  None
```

`BaseCache.incr` gets the value, raising `ValueError` if it is missing, and sets the sum; `BaseCache.decr` adds the negative. `BaseCache.incr_version` gets the value at a version, the cache's by default, sets it at the version plus the delta, deletes the old entry and returns the new version (`django/core/cache/backends/base.py:BaseCache.incr_version`). The base's error names the key given, `LocMemCache.incr`'s the made key:

```text
cache.set("berths", ["north", "south"])  ->  None
cache.incr_version("berths")  ->  2
cache.get("berths")  ->  None
cache.get("berths", version=2)  ->  ['north', 'south']
cache.incr_version("nosuch")  ->  raises ValueError: Key 'nosuch' not found
cache.incr("nosuch")  ->  raises ValueError: Key ':1:nosuch' not found
```

> **Trap.** The base's `incr` and `incr_version` read and then write, and another caller can come between; and the write is a `set` with no timeout, which gives the entry the cache's default. A key set for ten seconds and incremented had 300 left on `FileBasedCache`, which inherits the base's `incr`, and ten on `LocMemCache`, whose own leaves the expiry alone (`django/core/cache/backends/locmem.py:LocMemCache.incr`).

## The asynchronous twins

Each method of the API, but `in` and the helpers for keys and timeouts, has a twin with an `a` in front, such as `BaseCache.aget`, and every twin is `BaseCache`'s: no backend Django ships writes one, and its documentation says Django does not yet support asynchronous caching (`docs/topics/cache.txt`).

The twins of the methods a backend must write, and `BaseCache.aclose`, call the method through `sync_to_async` with `thread_sensitive=True`, on the thread kept for such work, under ASGI the request's own ([Sync and async in one chain](../handlers/async.md)) (`django/core/cache/backends/base.py:BaseCache.aget`). The twins of the defaults, but for `BaseCache.adecr` and `BaseCache.adecr_version`, which call `aincr` and `aincr_version`, run the backend's replacement, if it has one, in one such call, and otherwise repeat the default's steps through the other twins, each a crossing of its own (`django/core/cache/backends/base.py:BaseCache.aget_or_set`). On `LocMemCache`, `BaseCache.aget_or_set` crosses three times on a miss and `BaseCache.aincr` once, to `LocMemCache.incr`.
