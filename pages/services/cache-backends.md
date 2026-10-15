---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The cache backends

The cache backends Django ships in `django/core/cache/backends/`, `LocMemCache`, `FileBasedCache`, `DatabaseCache`, `PyMemcacheCache` and `PyLibMCCache`, `RedisCache` and `DummyCache`: where each keeps an entry, how an entry expires, and how a backend makes room when it is full.

Every backend is a subclass of `BaseCache`, which makes the keys and builds most methods out of a few that a backend must provide ([The cache API: `caches` and `BaseCache`](cache-api.md)). What a backend adds is a store. `CacheHandler.create_connection` makes it with the alias's `"LOCATION"` and its other keys, and a backend reads the location its own way: as the name of a store in memory, a directory, a table, or servers' addresses (`django/core/cache/__init__.py:CacheHandler.create_connection`).

## Two kinds of backend

`LocMemCache`, `FileBasedCache` and `DatabaseCache` keep their entries themselves. Beside each entry they store the time it expires, computed by `BaseCache.get_backend_timeout`, which gives `None` for never (`django/core/cache/backends/base.py:BaseCache.get_backend_timeout`). Nothing removes an entry when its time comes; `get` compares the time, and deletes an entry that has expired. Each also makes room itself when a write finds the store full by `"MAX_ENTRIES"` of the alias's `"OPTIONS"`, 300 by default: it removes one in `"CULL_FREQUENCY"` of the entries, a third by default, or all where that is 0; `DatabaseCache` checks on only a share of writes, and removes expired rows first (`docs/topics/cache.txt`).

`PyMemcacheCache`, `PyLibMCCache` and `RedisCache` are clients of a server. They pass a client library the value and a timeout converted for the server, compare no time and cull nothing themselves, and give the alias's `"OPTIONS"` to the client they make (`docs/topics/cache.txt`). `DummyCache` keeps nothing.

What each kind makes of a timeout:

```text
# a run: get_backend_timeout of the base class and of the two server backends
timeout        BaseCache        BaseMemcachedCache           RedisCache
(none given)   now + 300        300                          300
None           None             0                            None
0              now + -1         -1                           0
-5             now + -5         -5                           0
300            now + 300        300                          300
31 days        now + 2678400    now + 2678400 (a Unix time)  2678400
```

To Memcached, say the comments, 0 means never and a negative timeout expires at once, so `None` becomes 0 and 0 becomes -1; and a number above 30 days is read as a Unix time, so a longer timeout is made one (`django/core/cache/backends/memcached.py:BaseMemcachedCache.get_backend_timeout`). `RedisCacheClient` is given `None` for no expiry and 0 for anything not positive, and `RedisCacheClient.set` deletes a key it is given 0 for (`django/core/cache/backends/redis.py:RedisCache.get_backend_timeout`, `django/core/cache/backends/redis.py:RedisCacheClient.set`).

> **Trap.** `BaseCache.clear`, in every backend, ignores `"KEY_PREFIX"` and version, and empties the whole store: for Memcached it calls the client's flush_all, and for Redis flushdb on the first server of `"LOCATION"` (`django/core/cache/backends/memcached.py:BaseMemcachedCache.clear`, `django/core/cache/backends/redis.py:RedisCacheClient.clear`).

## `LocMemCache`: a dictionary for each name

`LocMemCache` keeps its entries in dictionaries at its module's level, keyed by the backend's name: one of entries, one of expiry times, one of locks (`django/core/cache/backends/locmem.py:_caches`). So the store belongs to the process: the handler makes a `LocMemCache` for each thread, and all made with one `"LOCATION"`, under any alias, share its entries and its lock (`django/core/cache/backends/locmem.py:LocMemCache.__init__`).

`LocMemCache.set` pickles the value before it takes the lock, and `LocMemCache.get` unpickles it after, so what `get` returns is a copy (`django/core/cache/backends/locmem.py:LocMemCache.get`).

The entries are a `collections.OrderedDict` kept in order of use. A write, a read that finds its entry and an increment move the key to the front; a touch and a test for the key do not. When a write finds `"MAX_ENTRIES"` entries or more, `LocMemCache._cull` pops entries from the back, the least recently used (`django/core/cache/backends/locmem.py:LocMemCache._cull`):

```text
# a run of the example: an alias "berths", a LocMemCache with "MAX_ENTRIES" 3; its keys, most recently used first
set("berth-A"), set("berth-B"), set("berth-C")       [':1:berth-C', ':1:berth-B', ':1:berth-A']
get("berth-A")                                       [':1:berth-A', ':1:berth-C', ':1:berth-B']
set("berth-D")                                       [':1:berth-D', ':1:berth-A', ':1:berth-C']
```

`LocMemCache._has_expired` counts a key with no expiry recorded as expired, so a missing key and an expired one are a single case; `get`, `LocMemCache.has_key` and `LocMemCache.incr` delete an entry they find expired (`django/core/cache/backends/locmem.py:LocMemCache._has_expired`).

## `FileBasedCache`: a file for each key

`FileBasedCache` keeps each entry in a file of the directory `"LOCATION"` names, named by the made key's MD5 with the suffix `".djcache"`: in a run, `"sailings"` was the file 69edded1a78ce377ad12a36cbce55470.djcache (`django/core/cache/backends/filebased.py:FileBasedCache._key_to_file`). The file holds the expiry pickled, then the value pickled and compressed with zlib (`django/core/cache/backends/filebased.py:FileBasedCache._write_content`). A read unpickles the expiry first; if it has passed, `FileBasedCache._is_expired` deletes the file unread.

`FileBasedCache.set` makes the directory again, which a comment says can be deleted at any time, culls, writes the entry to a temporary file in the directory and moves it onto the entry's name with `file_move_safe` ([Files: `File`, `ContentFile` and their helpers](files.md)) (`django/core/cache/backends/filebased.py:FileBasedCache.set`). The directory is made with the mode 0o700 through `safe_makedirs`, because `os.makedirs`, says a comment, does not give the mode to the directories in between (`django/core/cache/backends/filebased.py:FileBasedCache._createdir`). `FileBasedCache.add` is `FileBasedCache.has_key` and then `set`, with nothing held between them; `FileBasedCache.touch` locks the file while it rewrites it. To cull, every `set` lists the directory, and at `"MAX_ENTRIES"` files deletes a random sample of them (`django/core/cache/backends/filebased.py:FileBasedCache._cull`).

## `DatabaseCache`: a row for each key

`DatabaseCache` keeps each entry as a row of the table `"LOCATION"` names, with the key as primary key, the value, and an indexed expiry; the createcachetable command creates it (`django/core/management/commands/createcachetable.py:Command.create_table`) ([The commands Django ships](../commands/builtin.md)). There is no model: the backend runs SQL of its own on a cursor, and for the database router makes a stand-in class with the module's `Options` as its model options (`django/core/cache/backends/db.py:Options`), answering as a model CacheEntry of an application `"django_cache"` (`django/core/cache/backends/db.py:BaseDatabaseCache.__init__`). Reads go where `ConnectionRouter.db_for_read` sends that class, writes where `ConnectionRouter.db_for_write` does ([Routing between databases: `ConnectionRouter`](../backends/routers.md)).

`DatabaseCache.set`, `DatabaseCache.add` and `DatabaseCache.touch` share `DatabaseCache._base_set`. It stores `None` as `datetime.datetime.max`, and the pickle in Base64 as text, since the column, says a comment, expects a string and not bytes. Inside `atomic` it selects the key's row: `touch` updates the row's expiry, or fails if there is none; `set` updates the row or inserts one; `add` updates the row only if it has expired, and otherwise inserts. A `DatabaseError` is swallowed, and `add` or `touch` returns `False`: to be thread-safe, says the comment, updates and inserts may fail silently (`django/core/cache/backends/db.py:DatabaseCache._base_set`). An `add` over a live key fails so: run on SQLite, its INSERT hit the primary key, and it returned `False`.

`DatabaseCache.get_many`, which `DatabaseCache.get` calls with one key, sends one SELECT, converts each expiry as the ORM would, lest, says a comment, it compare aware and naive datetimes, deletes the expired rows in one DELETE, and unpickles the others, their Base64 decoded strictly since 6.1 (`django/core/cache/backends/db.py:DatabaseCache.get_many`, `docs/releases/6.1.txt`).

Only a share of writes cull: each draws a random number, and culls when it is at most `"CULL_PROBABILITY"` of the alias's `"OPTIONS"`, 0.1 by default (`django/core/cache/backends/db.py:DatabaseCache._base_set`). The cull counts the rows; past `"MAX_ENTRIES"`, it deletes the expired ones, and if still past, the rows whose keys sort first, one in `"CULL_FREQUENCY"`, finding the first key to keep with `BaseDatabaseOperations.cache_key_culling_sql` ([The SQL a backend writes: `BaseDatabaseOperations`](../backends/operations.md)) (`django/core/cache/backends/db.py:DatabaseCache._cull`). Age plays no part: in a run with `"MAX_ENTRIES"` 3 and `"CULL_PROBABILITY"` 1, of berth-D, berth-B, berth-A and berth-C, set in that order, the next write's cull removed berth-A.

> **Changed in 6.2.** Culling on a share of writes, and `"CULL_PROBABILITY"`, are new, as an optimization (`docs/releases/6.2.txt`).

## Memcached: `PyMemcacheCache` and `PyLibMCCache`

`PyMemcacheCache` makes pymemcache's HashClient, by default with pymemcache's pickling serializer; `PyLibMCCache` makes pylibmc's client (`django/core/cache/backends/memcached.py:PyMemcacheCache.__init__`). Their base, `BaseMemcachedCache`, refuses the keys the base class warns of: `BaseMemcachedCache.validate_key` raises `InvalidCacheKey` where `BaseCache.validate_key` warns with `CacheKeyWarning`, for a made key longer than `MEMCACHE_MAX_KEY_LENGTH` or holding a space or a control character (`django/core/cache/backends/memcached.py:BaseMemcachedCache.validate_key`).

`BaseMemcachedCache.set` deletes the key when the library reports a failure, so that, says the comment, the key does not keep its old value when the new one is over Memcached's limit (`django/core/cache/backends/memcached.py:BaseMemcachedCache.set`). `BaseMemcachedCache.close` disconnects the client from its servers, as many clients, its comment says, do not clean up their connections; `PyLibMCCache.close` does nothing, libmemcached managing its own (`django/core/cache/backends/memcached.py:PyLibMCCache.close`).

## Redis: `RedisCache` and `RedisCacheClient`

`RedisCache` makes the keys and the timeout and hands the rest to a `RedisCacheClient`, which takes a serializer, a pool class and a parser class out of `"OPTIONS"` and passes the others to its connection pools (`django/core/cache/backends/redis.py:RedisCacheClient.__init__`). Every write goes to the first server of `"LOCATION"`, and, if there are others, every read to one of them, chosen at random, so a read just after a write reaches a server other than the one written (`django/core/cache/backends/redis.py:RedisCacheClient._get_connection_pool_index`).

`RedisSerializer` pickles every value but an integer (a bool is pickled), which goes to the library as it is, for better atomicity of increments, its comment says: `RedisCacheClient.incr` checks that the key exists, then hands the increment to the library's incr without reading the value (`django/core/cache/backends/redis.py:RedisSerializer.dumps`, `django/core/cache/backends/redis.py:RedisCacheClient.incr`).

## `DummyCache`

`DummyCache` stores nothing. Each method given a key still makes and validates it, so the keys `BaseCache.validate_key` warns of still warn; `DummyCache.get` returns the default, `DummyCache.add` returns `True`, and the methods that report a key found return `False` (`django/core/cache/backends/dummy.py:DummyCache`). So `BaseCache.get_or_set` calls its default every time and returns what it made: with `DummyCache` as the default alias, each test-client request for sailings/ sent its query.
