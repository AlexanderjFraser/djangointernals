---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `SessionMiddleware`: the cookie and the save

`SessionMiddleware` joins a session store to the cookie that carries its key. On the way in, `SessionMiddleware.process_request` gives every request a store for the key in its cookie; on the way out, `SessionMiddleware.process_response` may save the store and set the cookie again, or delete the cookie, and add `"Cookie"` to the response's `"Vary"`.

The middleware never loads or stores session data itself: the store loads its data at its first use and knows how to save it ([The session store: `SessionBase`](sessions.md)). On the way out it decides whether the store is saved and what the browser is told, from three things the store reports, whether it was accessed (read or written), modified (written) or empty, with the request's cookie and the response's status.

## Making the store: `__init__` and `process_request`

`SessionMiddleware.__init__` imports the module that `SESSION_ENGINE` names and keeps the store class that module defines (`django/contrib/sessions/middleware.py:SessionMiddleware.__init__`). It runs once, when the handler builds the chain, so the engine is fixed for the handler's life ([Building the middleware chain](../handlers/chain.md)).

`SessionMiddleware.process_request` reads the cookie that `SESSION_COOKIE_NAME` names, `"sessionid"` by default, and sets `HttpRequest.session` to a new store made with its value, or with `None` when the request has no such cookie (`django/contrib/sessions/middleware.py:SessionMiddleware.process_request`). Nothing is read, so a request that never uses the session costs nothing unless `SESSION_SAVE_EVERY_REQUEST` is true, and every request has the store that `AuthenticationMiddleware` requires of the layers outside it.

`SessionMiddleware.async_capable` is false since 6.2: under ASGI both hooks run synchronously, on one thread, held while the layers inside run, and the save is the store's synchronous `SessionBase.save` ([Sync and async in one chain](../handlers/async.md)).

## The way out: `process_response`

`SessionMiddleware.process_response` begins by reading the store's `SessionBase.accessed` and `SessionBase.modified` and calling `SessionBase.is_empty`. If any of the three raises `AttributeError`, it returns the response untouched. `MiddlewareMixin.__call__` always runs `process_request` before the layers inside, so in the chain what trips the guard is code inside that deleted `HttpRequest.session` or replaced it with an object without these attributes, or an engine whose store lacks them; in a run whose view deleted it, the response came back with no cookie and no `"Vary"` (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`).

`is_empty` is true when the store has no key and its data, if it has loaded any, is an empty dictionary (`django/contrib/sessions/backends/base.py:SessionBase.is_empty`). A session with a key and no data is not empty: its cookie is kept, and it is saved when modified. A store is left with no key by `SessionBase.flush`, which `logout` calls; by loading, when a backend that stores sessions on the server finds nothing under the key and drops it ([The session backends](session-backends.md)); and from the start, when the cookie's value is too short to be a key. So a stale cookie is deleted at the first request that reads the session, and a cookie of three characters at once, unless the request writes to the session, which then gets a new key.

```text figure=the-way-out
SessionMiddleware.process_response(request, response)

no request.session, or one without accessed, modified, is_empty
    -> the response as it is
the request brought the session cookie, and the session is empty
    -> the cookie deleted, with SESSION_COOKIE_PATH, SESSION_COOKIE_DOMAIN, SESSION_COOKIE_SAMESITE
       Vary: Cookie
otherwise
    -> Vary: Cookie if the session was accessed
    and if it was modified, or SESSION_SAVE_EVERY_REQUEST is true, and it is not empty:
        status below 500    -> saved; an UpdateError raised again as SessionInterrupted
                               the cookie set: Max-Age and expires, or neither for a browser-length session
                               Vary: Cookie
        status 500 or more  -> not saved, no cookie
    if not                  -> not saved, no cookie
```

*`SessionMiddleware.process_response` decides from what the session reports, the request's cookie and the response's status. The cookie is deleted only when the request brought one, and a session is saved only when it was changed or the setting asks, is not empty, and the status is below 500.*

The deleted cookie gets the path, domain and SameSite that the settings give the cookie when it is set ([Cookies](../http/cookies.md)) (`django/http/response.py:HttpResponseBase.delete_cookie`). `"Cookie"` goes into `"Vary"` by `patch_vary_headers` whenever the session was accessed and whenever the cookie is set or deleted: a response made from a session depends on the `"Cookie"` header that brought its key, and `"Vary"` tells a cache so ([Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md)) (`django/utils/cache.py:patch_vary_headers`). The run adds two views of the office's: /port/ stores a posted port in the session, and /fail/ stores another and raises.

```text
# a run of the example: each response's status, Vary, and session cookie (the key cut short)
GET /berths/, no cookie                          302  Vary: Cookie
POST /port/, no cookie                           200  Vary: Cookie
    Set-Cookie: sessionid=4y6879kd...; expires=Fri, 30 Oct 2026 11:34:21 GMT; HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax
POST /accounts/login/ as nora                    302  Vary: Cookie
    Set-Cookie: sessionid=9tx1u4o3...; expires=Fri, 30 Oct 2026 11:34:21 GMT; HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax
POST /accounts/logout/                           200  Vary: Cookie
    Set-Cookie: sessionid=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax
POST /fail/, with the cookie                     500  Vary: Cookie
GET /berths/ as nora, SESSION_SAVE_EVERY_REQUEST 200  Vary: Cookie
    Set-Cookie: sessionid=q8hf5kd7...; expires=Fri, 30 Oct 2026 11:34:23 GMT; HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax
login as nora, SESSION_EXPIRE_AT_BROWSER_CLOSE   302  Vary: Cookie
    Set-Cookie: sessionid=10glwde9...; HttpOnly; Path=/; SameSite=Lax
```

## The save and the expiry

Before saving, `SessionMiddleware.process_response` works out the cookie's lifetime. When `SessionBase.get_expire_at_browser_close` is true, from `SESSION_EXPIRE_AT_BROWSER_CLOSE` when the session set no expiry of its own, or from its `set_expiry(0)`, the cookie gets neither an age nor a date and lasts as long as the browser. Otherwise `SessionBase.get_expiry_age` gives the age, `SESSION_COOKIE_AGE` (two weeks) unless the session set its own, and the date is that many seconds from now. Then the store is saved, and `HttpResponseBase.set_cookie` is given the store's key, read after the save, with `SESSION_COOKIE_DOMAIN`, `SESSION_COOKIE_PATH`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY` and `SESSION_COOKIE_SAMESITE`. The save of a session without a key makes one: at /port/ in a run, the backend asked whether a new key was taken, then inserted the row (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`).

For a status of 500 or more nothing is saved and no cookie set, so the stored session stays as it was: after the request to /fail/, the row still held the earlier port.

Each save sets the cookie again with an age counted from now, and the database backend gives the row a new expiry date. So, unless `SessionBase.set_expiry` gave the session a date, the expiry moves at each save: a session written at every visit lasts two weeks from the last write, and one only read keeps the expiry of its last save, in the cookie and in the row, as a run showed. `SESSION_SAVE_EVERY_REQUEST` makes every request with a session and a status below 500 a save, even one whose view never touched it: finding the expiry reads the session, and such a request sent the session's select, then its update. A visitor without a session gets none, the store being empty. A browser-length session's row is still stored to expire after `SESSION_COOKIE_AGE`: two weeks ahead, at a login in a run (`django/contrib/sessions/backends/base.py:SessionBase.get_expiry_date`).

## A session deleted meanwhile: `SessionInterrupted`

`SessionInterrupted` is raised when the middleware's save finds the stored session gone, deleted, say, by a logout in a concurrent request, the example its message gives. Every backend but the signed-cookie one then raises `UpdateError`, which the middleware raises again as this subclass of `BadRequest` (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`, `django/contrib/sessions/exceptions.py:SessionInterrupted`, `django/contrib/sessions/backends/db.py:SessionStore.save`). It becomes a 400 at the session middleware's own boundary, in place of the response the view made and its cookies ([How an exception becomes a response](../handlers/exceptions.md)). In a run where a view wrote to nora's session and deleted its row, the response was a 400 with no cookie and no `"Vary"`.
