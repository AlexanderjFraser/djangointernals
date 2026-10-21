---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The session backends

The session backends are Django's own modules that `SESSION_ENGINE` can name: `django.contrib.sessions.backends.db`, the default, and the cache, cached database, file and signed-cookie backends. Each keeps a session's data in a place of its own, and they differ most in what happens when that place loses a session or fails.

Each module defines a class called `SessionStore`, a subclass of `SessionBase` supplying the storage, under one contract: a save that must create raises `CreateError` when the key is taken, and one that must update raises `UpdateError` when the session has gone ([The session store: `SessionBase`](sessions.md#what-a-backend-supplies)) (`django/contrib/sessions/backends/base.py:SessionBase.save`). One login of nora's under each engine, by the test client with a `LocMemCache` as the cache, left this behind:

| engine | the session after the login | the cookie's value | the next page's queries |
|---|---|---|---|
| `django.contrib.sessions.backends.db` | a row of `"django_session"` | the key, 32 characters | the session's row; the user |
| `django.contrib.sessions.backends.cache` | an entry of the cache | the key | the user |
| `django.contrib.sessions.backends.cached_db` | the row, and an entry of the cache | the key | the user |
| `django.contrib.sessions.backends.file` | a file in `SESSION_FILE_PATH`: `"sessionid"` and the key | the key | the user |
| `django.contrib.sessions.backends.signed_cookies` | nothing on the server | the data, signed: about 225 characters | the user |

*Nora's login under each engine; the logout removed what each server-side backend had stored.*

## The database backend

`django.contrib.sessions.backends.db` stores a session as a row of `Session`, in the table `"django_session"`, with the fields of the abstract `AbstractBaseSession`: `session_key`, the primary key, of up to 40 characters; `session_data`, the string `SessionBase.encode` makes; and `expire_date`, indexed, the moment the session ends as `get_expiry_date` computed it at the last save (`django/contrib/sessions/base_session.py:AbstractBaseSession`). `SessionStore.get_model_class` imports the model inside itself, which, its comment says, avoids a circular import and lets the store be imported without `django.contrib.sessions` installed (`django/contrib/sessions/backends/db.py:SessionStore.get_model_class`).

Loading asks for the row with the key whose `expire_date` is later than now. Finding none, missing or expired, the store drops its key and returns an empty dictionary, so a later save makes a new key; a `SuspiciousOperation` met on the way is logged (`django/contrib/sessions/backends/db.py:SessionStore._get_session_from_db`). The expired row is left in the table: `SessionStore.delete` deletes one row by its key, and `clear_expired` every row whose `expire_date` has passed (`django/contrib/sessions/backends/db.py:SessionStore.clear_expired`).

`SessionStore.create` takes a key that `exists` reports free and saves at once with `must_create=True`, to be sure of a unique entry, says its comment; on `CreateError` it tries another key (`django/contrib/sessions/backends/db.py:SessionStore.create`). `SessionStore.save` writes inside `atomic`, on the database `ConnectionRouter.db_for_write` chooses, forcing an insert when creating and an update otherwise ([Transactions: autocommit, `atomic` and savepoints](../connections/atomic.md)). An `IntegrityError` on the insert, a key taken since the check, becomes `CreateError`. A forced update that finds no row raises `Model.NotUpdated`, a `DatabaseError`, which becomes `UpdateError`: the row was deleted meanwhile, by a concurrent logout, say (`django/contrib/sessions/backends/db.py:SessionStore.save`).

A project wanting more columns subclasses `AbstractBaseSession` and the database or cached database store, each naming the other, in `AbstractBaseSession.get_session_store_class` and `get_model_class` (`docs/topics/http/sessions.txt`). `AbstractBaseSession.get_decoded` decodes a row through that store; `BaseSessionManager.save`, which saves a row, or deletes it for an empty dictionary, Django never calls (`django/contrib/sessions/base_session.py:BaseSessionManager.save`).

## The cache backend

`django.contrib.sessions.backends.cache` keeps the dictionary itself, unsigned, as an entry of the cache `SESSION_CACHE_ALIAS` names, `"default"` unless set, under `KEY_PREFIX`, `"django.contrib.sessions.cache"`, and the session key (`django/contrib/sessions/backends/cache.py:SessionStore`) ([The cache API: `caches` and `BaseCache`](../services/cache-api.md)). `SessionStore.save` uses the cache's own operations: creating, it calls `add`, which stores only under an absent key, and a refusal is `CreateError`; updating, it sets the entry only if the cache still has it, and otherwise raises `UpdateError`. The timeout is `get_expiry_age`, so the cache's expiry ends the session, and `clear_expired` does nothing (`django/contrib/sessions/backends/cache.py:SessionStore.save`).

`SessionStore.load` takes any exception from the cache for a miss: some caches, its comment says, memcache among them, raise on a key they refuse (ticket 17810), and the key comes from a cookie; a miss drops the key and gives an empty session (`django/contrib/sessions/backends/cache.py:SessionStore.load`). `SessionStore.create` tries 10,000 keys before raising `RuntimeError`; a cache can fail silently, says its comment, so a refused `add` cannot tell a taken key from a missing cache (`django/contrib/sessions/backends/cache.py:SessionStore.create`).

So a session lives as long as the cache keeps its entry: one evicted from a full cache or lost at a restart is a user logged out, the documentation warns; and one lost between a load and the save makes the save raise `UpdateError`, as a store made by hand did, the cache cleared in between. The documentation advises the cached database backend unless the cache is configured to persist (`docs/topics/http/sessions.txt`) ([The cache backends](../services/cache-backends.md)).

## The cached database backend

`django.contrib.sessions.backends.cached_db` subclasses the database store and puts the cache of `SESSION_CACHE_ALIAS` before it, under `"django.contrib.sessions.cached_db"` (`django/contrib/sessions/backends/cached_db.py:SessionStore`). `SessionStore.save` writes through: the row first, then the cache entry. `SessionStore.load` reads the cache first and, on a miss or an exception, the row, and puts the row's data in the cache for the time the row has left (`django/contrib/sessions/backends/cached_db.py:SessionStore.load`).

An exception from setting the entry after a save, or from deleting it after the row, is logged to `"django.contrib.sessions"`, and the save or the delete stands (`django/contrib/sessions/backends/cached_db.py:SessionStore.save`, `django/contrib/sessions/backends/cached_db.py:SessionStore.delete`). The refill after a read is not guarded, and `SessionStore.exists` asks the cache before the row: with a cache raising on every call, stores made by hand for an existing row updated and deleted it, but a load raised, and so did a new session's save (`django/contrib/sessions/backends/cached_db.py:SessionStore.exists`).

> **Changed in 6.2.** A failed delete from the cache is caught and logged too; before, only a failed write was (`docs/topics/http/sessions.txt`).

## The file backend

`django.contrib.sessions.backends.file` keeps a session in a file named `SESSION_COOKIE_NAME` and the key, in `SESSION_FILE_PATH`, or `tempfile.gettempdir` when that is `None`, its default; a directory that does not exist raises `ImproperlyConfigured` (`django/contrib/sessions/backends/file.py:SessionStore._get_storage_path`). A key holding any character outside `VALID_KEY_CHARS`, a slash or a dot say, raises `InvalidSessionKey` first, against directory traversal, says the comment; loading takes it for no session (`django/contrib/sessions/backends/file.py:SessionStore._key_to_file`).

The file holds only the encoded data, and its modification time stands for the last save: the session expires `SESSION_COOKIE_AGE` seconds after it unless the data holds an expiry of its own (`django/contrib/sessions/backends/file.py:SessionStore._expiry_date`). Loading an expired session deletes the file and at once creates a new session under a new key. An expiry given to `set_expiry` in seconds, other than 0, is taken as the age remaining whatever the file's time: a store made by hand given 60 seconds, its file's time set back past `SESSION_COOKIE_AGE`, still loaded, and `clear_expired` kept it.

`SessionStore.save` meets the contract with the file system: creating, it opens the file with `os.O_CREAT` and `os.O_EXCL`, and a file already there is `CreateError`; updating, without them, and a missing file is `UpdateError`. It then writes a temporary file beside it and moves it onto the name, which its comment prefers to locking, rejected in part for needing a long-lived lock file for each session (ticket 8616); where `os.rename` cannot replace a file, as on Windows, the move copies and unlinks (ticket 9084), as a save on Windows did. An `OSError` in the writing is passed over (`django/contrib/sessions/backends/file.py:SessionStore.save`). `SessionStore.clear_expired` loads every file whose name begins with the cookie's name, with `create` disabled so that, as its comment says, an expired file is removed and not replaced (`django/contrib/sessions/backends/file.py:SessionStore.clear_expired`).

## The signed-cookie backend

`django.contrib.sessions.backends.signed_cookies` keeps nothing on the server: the key is the data. `SessionStore.save` makes it with `django.core.signing.dumps`, compressed, under the salt `"django.contrib.sessions.backends.signed_cookies"`, and marks the session modified, so the middleware sets the cookie (`django/contrib/sessions/backends/signed_cookies.py:SessionStore._get_session_key`) ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](../security/signing.md)). `SessionStore.load` reads it back with `loads`, accepting an age of `SESSION_COOKIE_AGE` since the signing whatever `set_expiry` said, a limit its comment admits (ticket 19201). Any failure gives an empty session marked modified, so a changed cookie made nora anonymous and was replaced by a signed empty session (`django/contrib/sessions/backends/signed_cookies.py:SessionStore.load`).

Its `exists` always answers no, `create` only marks the session modified, and `delete` empties the key and the data. The base's `cycle_key` ends by deleting the old key, which here would empty the data; this backend's `SessionStore.cycle_key` only saves, making the key again from the same data (`django/contrib/sessions/backends/signed_cookies.py:SessionStore.cycle_key`).

The documentation warns of what follows (`docs/topics/http/sessions.txt`). A logout has nothing on the server to delete: nora's cookie, copied before the logout and sent after it by another test client, still signed nora in, and such a session ends with its age, or when nora's password changes ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)). The data travels with every request, and a cookie the browser cannot keep whole fails its signature, as one cut short did; the documentation gives 4,096 bytes as a common limit. And the data is signed, not encrypted, so the client can read it:

```text
# the first part of nora's "sessionid" cookie, decoded from base64 and decompressed
{"_auth_user_id":"1","_auth_user_backend":"django.contrib.auth.backends.ModelBackend","_auth_user_hash":"8cb0ebc75bc4cfa7e0a1ea65e2fc30bed5c10404a4ca15a459d09e2a3e4c488f"}
```

## Clearing expired sessions

The clearsessions command calls `clear_expired` on the store of the module `SESSION_ENGINE` names, and turns the base's `NotImplementedError` into a `CommandError` (`django/contrib/sessions/management/commands/clearsessions.py:Command.handle`). The database backends delete expired rows and the file backend loads every file; the cache and signed-cookie backends do nothing, a cache deleting stale data itself and the browser holding the data, as the documentation says. Django provides no automatic purge, says the documentation, which recommends running the command regularly (`docs/topics/http/sessions.txt`) ([The commands Django ships](../commands/builtin.md)).
