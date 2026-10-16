---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The session store: `SessionBase`

`SessionBase` is the base class of every session store, the object a request carries as `HttpRequest.session`. It is a dictionary that loads itself at first use and records whether it was read or changed; it owns the session key, the signed string most backends store the data as, and the expiry, and each backend adds the storage.

The session middleware makes a store for every request, used or not (`django/contrib/sessions/middleware.py:SessionMiddleware.process_request`), and a store reads nothing until its data is used. On the way out the middleware asks it whether it was read, whether it was changed and whether it is empty, and the store answers without going to storage.

## A dictionary loaded at first use

`SessionBase.__init__` keeps the key it is given, if it is valid, sets both flags false and imports the serializer `SESSION_SERIALIZER` names; it reads nothing (`django/contrib/sessions/backends/base.py:SessionBase.__init__`). Every dictionary method but `SessionBase.clear` reaches the data through the property `SessionBase._session`, whose getter, `SessionBase._get_session`, sets `SessionBase.accessed` and returns the data if the store holds it. Otherwise it fills it, once: with an empty dictionary when the store has no key or the caller passes `no_load=True`, as a backend's save does when told to create the session, and else with what the backend's `SessionBase.load` returns (`django/contrib/sessions/backends/base.py:SessionBase._get_session`).

## `accessed` and `modified`

`SessionBase.accessed` is set by every use of the data, read or write, and by `clear`. `SessionBase.modified` is set by what changes the dictionary: `__setitem__`, `SessionBase.update` and `clear` always, `__delitem__` and `SessionBase.pop` only when the key was there, `SessionBase.setdefault` only when it sets (`django/contrib/sessions/backends/base.py:SessionBase.pop`); a backend's `SessionBase.create` sets it too. The session middleware reads both: `modified` in deciding whether to save, `accessed` whether to vary the response on `"Cookie"` ([`SessionMiddleware`: the cookie and the save](session-middleware.md)). A database store used by hand:

```python
# in a shell, with harbour's settings
>>> from django.contrib.sessions.backends.db import SessionStore
>>> s = SessionStore()
>>> s.get("ship"), s.accessed, s.modified, bool(s)
(None, True, False, False)
>>> s["ship"] = "Endeavour"
>>> s.accessed, s.modified, bool(s)
(True, True, True)
>>> s.save()
>>> t = SessionStore(s.session_key)
>>> t.accessed, t.modified, bool(t)
(False, False, True)
>>> t["ship"], t.accessed, t.modified
('Endeavour', True, False)
```

Of the reads, only t's went to the database: one SELECT of the row.

> **Trap.** A change inside a value, such as appending to a list kept in the session, goes through no method of the store: in a run, `modified` stayed false. The documentation says to set it by hand (`docs/topics/http/sessions.txt`).

## Empty: `is_empty` and `__bool__`

`SessionBase.is_empty` is true when the store has no key and its data is empty or was never loaded (`django/contrib/sessions/backends/base.py:SessionBase.is_empty`). It does not load. A store made for a key is not empty before it is read, even when storage has no such session; it becomes empty when a load finds nothing and the backend drops the key, as the database backend does. `SessionBase.__bool__` answers the opposite of `is_empty`, so `if request.session:` is true, before anything is read, for any request that brought a valid key, and asks storage nothing.

> **Changed in 6.1.** `SessionBase.__bool__` is new (`docs/releases/6.1.txt`).

## The session key

`SessionBase.session_key` is a read-only property. The store's own code assigns `SessionBase._session_key`, a second property over the same value whose setter stores `None` in place of a value that `SessionBase._validate_session_key` refuses (`django/contrib/sessions/backends/base.py:SessionBase._set_session_key`). The base refuses an empty key or one shorter than 8 characters, a bound its docstring calls arbitrary, "for some minimal key security"; a cookie holding `"abc"` gives a store with no key.

A new key is 32 characters that `get_random_string` draws from `VALID_KEY_CHARS`, the lower-case letters and the digits, drawn again for as long as `SessionBase.exists` says the key is taken (`django/contrib/sessions/backends/base.py:SessionBase._get_new_session_key`). A comment gives the reason for one case: some backends may store the key on a case-insensitive file system. A backend that needs a name to store under calls `SessionBase._get_or_create_session_key`, which makes a key if there is none.

## The stored form: `encode` and `decode`

`SessionBase.encode` turns the dictionary into a string with `dumps`, the store's serializer and the salt `SessionBase.key_salt`; `SessionBase.decode` reads it back with `loads` (`django/contrib/sessions/backends/base.py:SessionBase.encode`). The string is the serialized data in URL-safe base64, compressed when that is shorter, the time of signing and the signature: anyone holding it can read the data, and only a holder of `SECRET_KEY` or of a key in `SECRET_KEY_FALLBACKS` can make one that loads ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](../security/signing.md)).

`key_salt` is `"django.contrib.sessions."` followed by the class's qualified name, which leaves out its module. Every backend Django ships gives its store class the same name, so `key_salt` is `"django.contrib.sessions.SessionStore"` for all five. Only the database, cached-database and file backends store what `encode` makes; the cache backend hands the cache the dictionary itself, and the signed-cookie backend signs with a salt of its own (`django/contrib/sessions/backends/cache.py:SessionStore.save`, `django/contrib/sessions/backends/signed_cookies.py:SessionStore._get_session_key`). A project's renamed subclass of the database or file backend's store signs with another salt and reads every session stored before it as tampered with, as a subclass called HarbourSessionStore did in a run.

`decode` gives `loads` no maximum age, so the signature never expires; a session's lifetime is the backend's to enforce. On `BadSignature` it logs `"Session data corrupted"` as a warning to `"django.security.SuspiciousSession"` and returns an empty dictionary; on any other exception it returns one silently, a comment naming `ValueError` and unpickling errors (`django/contrib/sessions/backends/base.py:SessionBase.decode`).

`SESSION_SERIALIZER` names `django.contrib.sessions.serializers.JSONSerializer` by default, the signing module's `JSONSerializer` under another name (`django/contrib/sessions/serializers.py`). An integer key comes back a string, and a `datetime.datetime` cannot be kept at all. The refusal comes from `encode`, when the session is saved and not where the value was set; the session middleware saves after the view has returned. In the same shell:

```python
# in a shell, with harbour's settings
>>> t.encode({"ship": "Endeavour"})
'eyJzaGlwIjoiRW5kZWF2b3VyIn0:1xHgIG:v4LA2I7jI-G637hZ20dNX5eis_ZFr_K7_QMDvSfGLsA'
>>> from django.utils import timezone
>>> t["sailed"] = timezone.now()
>>> t.save()
Traceback (most recent call last):
  ...
TypeError: Object of type datetime is not JSON serializable
when serializing dict item 'sailed'
```

## Expiry

`SessionBase.set_expiry` keeps the session's own expiry in its data, under `"_session_expiry"` (`django/contrib/sessions/backends/base.py:SessionBase.set_expiry`). An integer is kept as it is, seconds, and 0 means when the browser closes. A `datetime.timedelta` is added to the current time, and the resulting `datetime.datetime`, or one given, is kept as its ISO string, which JSON can hold. `None` removes the entry, and the settings decide again.

`SessionBase.get_expiry_age` answers in seconds from now and `SessionBase.get_expiry_date` as a moment: no entry, or 0, means `SESSION_COOKIE_AGE`; an integer, that many seconds; a string, the moment it names (`django/contrib/sessions/backends/base.py:SessionBase.get_expiry_age`). Both accept the expiry as a keyword argument so that, as a comment says, they need not read the session and call `load`: the cached-database and file backends call `get_expiry_age` from inside their own. `SessionBase.get_expire_at_browser_close` returns `SESSION_EXPIRE_AT_BROWSER_CLOSE` when there is no entry, and otherwise whether the entry is 0.

> **Trap.** The middleware sends a cookie with no expiry when `get_expire_at_browser_close` is true, but `get_expiry_age` and `get_expiry_date` treat 0 as no entry, so storage keeps the session for `SESSION_COOKIE_AGE`: in a run, after `set_expiry(0)` the row was due to expire in fourteen days.

## Emptying and renewing: `clear`, `flush` and `cycle_key`

`SessionBase.clear` puts an empty dictionary in place of the data without loading the old, which a comment calls wasted time, and sets both flags; the key stays, so a save writes an empty session under it (`django/contrib/sessions/backends/base.py:SessionBase.clear`). `SessionBase.flush` clears, has the backend delete the stored session, and drops the key; the store is then empty, and the middleware deletes the request's cookie. `SessionBase.cycle_key` loads the data, has the backend `create` a session under a new key, puts the data back, and deletes what was stored under the old key (`django/contrib/sessions/backends/base.py:SessionBase.cycle_key`). `logout` calls `flush`; `login` calls `cycle_key` when the session holds no user yet, and `flush` when it holds another ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)).

## What a backend supplies

`SessionBase` leaves the storage methods to a backend, each raising `NotImplementedError` in the base: `SessionBase.exists`, `SessionBase.create`, `SessionBase.save`, `SessionBase.delete`, `SessionBase.load` and the class method `SessionBase.clear_expired`. `save` with `must_create=True` must create a stored session or raise `CreateError`, which `create` catches to try another key; otherwise it must only update one or raise `UpdateError`, which the middleware raises again as `SessionInterrupted` (`django/contrib/sessions/backends/base.py:SessionBase.save`, [The session backends](session-backends.md)). The test cookie methods store `"worked"` under `"testcookie"`, for a later request to check that the browser keeps cookies (`django/contrib/sessions/backends/base.py:SessionBase.set_test_cookie`).

## The asynchronous methods

The methods that go through `SessionBase._session` have twins whose names begin with `a`, `SessionBase.aset` standing for `__setitem__`; `__getitem__`, `__contains__` and `__delitem__` have none. A twin reaches the data through `SessionBase._aget_session`: the steps of `_get_session`, with `SessionBase.aload` awaited in place of `load` (`django/contrib/sessions/backends/base.py:SessionBase._aget_session`). The base's twins of the storage methods run the synchronous one through `sync_to_async`; a backend may replace them, as the database backend's `aload` does with the asynchronous ORM.

> **Trap.** `SessionBase.adelete_test_cookie` deletes the entry from the data directly, not through `__delitem__`, and does not set `modified`, which `SessionBase.delete_test_cookie` sets: a run showed both.
