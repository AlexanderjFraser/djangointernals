---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The user of a request: `login`, `logout` and `AuthenticationMiddleware`

`login` writes a user into the session store and `logout` empties it; `AuthenticationMiddleware` puts on every request a lazy `HttpRequest.user`, which `django.contrib.auth.get_user` reads back from the session at its first use, checking a hash of the user's stored password against the one written at the login.

A password is checked once, by `authenticate` ([Authenticating: `authenticate` and the backends](authenticating.md)). After that every request from the same browser has to know its user without the password, and has to stop knowing it when the user logs out, when someone else logs in in that browser, and when the user's password changes. Django keeps the answer in three entries of the session: `login` writes them, `get_user` reads them, and `logout` throws them away with the rest of the session.

## The three entries

| entry | key in the session | holds |
|---|---|---|
| `SESSION_KEY` | `"_auth_user_id"` | the user's primary key, as a string |
| `BACKEND_SESSION_KEY` | `"_auth_user_backend"` | the dotted path of an authentication backend, ordinarily the one that found the user |
| `HASH_SESSION_KEY` | `"_auth_user_hash"` | an HMAC of the user's stored password string |

*What `login` writes into the session (`django/contrib/auth/__init__.py`).*

The primary key is written by the key field's `value_to_string` and read back by `_get_user_session_key` through the field's `to_python`: the comment there says the value in the session is always a string and has to be converted whenever it is read (`django/contrib/auth/__init__.py:_get_user_session_key`). The backend's path is kept, in the documentation's words, so that the same backend can fetch the user on a later request (`docs/topics/auth/default.txt`).

## `login`

`login(request, user, backend=None)` works in this order (`django/contrib/auth/__init__.py:login`):

1. It computes the user's hash with `AbstractBaseUser.get_session_auth_hash`.
2. It looks at what the session holds. A session without a user id keeps its data under a new key: `SessionBase.cycle_key` moves the data to a new key and deletes what was stored under the old ([The session store: `SessionBase`](sessions.md)). The documentation gives the reason: it mitigates session fixation (`docs/topics/http/sessions.txt`). In that attack, someone who knows a valid session key gets a victim's browser to send it; were the key kept through the login, the attacker, sending the same key, would be logged in as the victim. A session holding another user's id, or this user's with another hash, is flushed instead: `SessionBase.flush` empties it, deletes what was stored and drops the key, so that, as the comment says, another user's session is not reused. A session that already holds this user with this hash is left as it is, key and all.
3. It settles the backend with `_get_backend_from_user`: the one given to `login`, else the path `authenticate` set on the user, else the entry of `AUTHENTICATION_BACKENDS` if it has only one. With several and neither given it raises `ValueError`, and for a backend given as anything but a string, `TypeError`; both come after the second step has changed the session.
4. It writes the three entries.
5. `_set_auth_user` puts the user on the request: `HttpRequest.user` becomes the user itself in place of the lazy object, and `HttpRequest.auser` a coroutine function that returns it, each only if the request already had one (`django/contrib/auth/__init__.py:_set_auth_user`).
6. `rotate_token` replaces the CSRF secret, so tokens made before the login stop matching ([The CSRF secret and its token](../security/csrf-token.md)).
7. It sends `user_logged_in` with the request and the user.

Django connects one receiver to `user_logged_in`, `update_last_login`, which sets `AbstractBaseUser.last_login` to the current time and saves that field alone (`django/contrib/auth/models.py:update_last_login`). `AuthConfig.ready` connects it only when the user model's `last_login` is a field, a `DeferredAttribute` on the class; a custom user model that sets it to `None` gets no receiver (`django/contrib/auth/apps.py:AuthConfig.ready`).

The harbour office lets a visitor choose a port before signing in, and keeps the choice in the session:

```python
# harbour/office/views.py, at "ports/<str:name>/" in harbour/urls.py
def port(request, name):
    request.session["port"] = name
    return HttpResponse("Your port is %s." % name)
```

One browser chose Valletta, then logged in as nora, as nora again, and as piet. After each response the session table held one row:

```text
# a run of the example: keys and hashes cut, the backend's entry left out
GET /ports/Valletta/, anonymous
    response: 200; "sessionid" set to kr4vnnvn...
    row: kr4vnnvn... {'port': 'Valletta'}
POST /accounts/login/ as nora
    response: 302 to /berths/; "sessionid" set to hv7um84a...
    row: hv7um84a... {'port': 'Valletta', '_auth_user_id': '1', '_auth_user_hash': '000cc855...'}
POST /accounts/login/ as nora again
    response: 302 to /berths/; "sessionid" set to hv7um84a...
    row: hv7um84a... {'port': 'Valletta', '_auth_user_id': '1', '_auth_user_hash': '000cc855...'}
POST /accounts/login/ as piet
    response: 302 to /berths/; "sessionid" set to vng29659...
    row: vng29659... {'_auth_user_id': '3', '_auth_user_hash': '0c2af9a8...'}
```

Nora's login moved the port to a new key; nora's second login kept the key; piet's flushed the session, port and all, and its row went with it.

`alogin` takes the same steps through the session's asynchronous methods and sends the signal with `Signal.asend` (`django/contrib/auth/__init__.py:alogin`).

> **Changed in 6.1.** `login` and `alogin` no longer fall back to the request's user when given `None` for the user (`docs/releases/6.1.txt`).

## `logout`

`logout` sends `user_logged_out` first; the comment gives the reason, that its receivers can still find out who logged out. The user it sends is the request's, or `None` when that user is anonymous or the request has none. Then it flushes the session and puts an `AnonymousUser` on the request with `_set_auth_user` (`django/contrib/auth/__init__.py:logout`). The documentation's reason for emptying the whole session: another person using the same browser should not reach the previous user's session data, and whatever is meant to outlast the logout is to be written after it (`docs/topics/auth/default.txt`). `alogout` asks `HttpRequest.auser` for the user and flushes with `SessionBase.aflush` (`django/contrib/auth/__init__.py:alogout`).

## `AuthenticationMiddleware`

`AuthenticationMiddleware.process_request` first checks that the request has a session, and without one raises `ImproperlyConfigured`, with a message that asks for `SessionMiddleware` before it in `MIDDLEWARE`. Then it puts two things on the request and looks nothing up (`django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request`). `HttpRequest.user` is a `SimpleLazyObject` over the middleware module's `get_user`, which calls `django.contrib.auth.get_user` once and keeps the answer on the request as `"_cached_user"` (`django/contrib/auth/middleware.py:get_user`). So the user is looked up at its first use, whatever uses it, and a request that never uses it never looks it up ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)).

`HttpRequest.auser` is the module's coroutine function `auser`, bound to the request, which awaits `aget_user` once and keeps the answer as `"_acached_user"`, a cache of its own (`django/contrib/auth/middleware.py:auser`). `aget_user` takes the steps of `django.contrib.auth.get_user` through `SessionBase.aget`, `SessionBase.acycle_key` and `SessionBase.aflush`, and asks the backend's `aget_user`, which `BaseBackend.aget_user` runs through `sync_to_async` and `ModelBackend.aget_user` answers with an asynchronous query (`django/contrib/auth/__init__.py:aget_user`).

The class sets `AuthenticationMiddleware.async_capable` to `False`, so under ASGI it runs synchronously ([Sync and async in one chain](../handlers/async.md)).

## Reading the user back: `django.contrib.auth.get_user`

`django.contrib.auth.get_user` takes these steps, and answers with an `AnonymousUser` wherever one fails (`django/contrib/auth/__init__.py:get_user`):

1. It reads the user id and the backend's path. A session missing either is anonymous.
2. It goes on only if the path is still in `AUTHENTICATION_BACKENDS`, makes that backend, and asks it for the user by the id. `ModelBackend.get_user` gives `None` for a user who no longer exists, and for an inactive one, which `ModelBackend.user_can_authenticate` refuses.
3. It compares the hash in the session with the user's hash now, by `constant_time_compare`, unless the user object has no `get_session_auth_hash`. A session without a hash fails the comparison.
4. When they differ and the session's hash matches one made with a key of `SECRET_KEY_FALLBACKS`, the session is kept: `cycle_key` gives it a new key and the user's hash under the current key is written in. Otherwise the session is flushed and the request is anonymous.

Only the fourth step flushes. A session that fails earlier is left as it was: in a run where nora was made inactive, or the backend of nora's login dropped from the setting, the next request was sent to the login page and the session's row and cookie stayed.

Two more browsers logged in as nora; then nora's password was changed under the first, and the secret key under the second:

```text
# a run of the example: nora signed in, in two more browsers
nora's password set and saved outside the browser
GET /berths/
    response: 302 to /accounts/login/?next=/berths/; "sessionid" deleted
    row: none
...
SECRET_KEY replaced, the old key in SECRET_KEY_FALLBACKS
GET /berths/
    response: 200; "sessionid" set to truzdrm0...
    row: truzdrm0... {'_auth_user_id': '1', '_auth_user_hash': 'ecb12b9e...'}
    page: <p>Signed in as nora.</p>
    nora's hash under the new key: ecb12b9e...
```

The session's data, signed with the old key, still loaded because signing tries the fallbacks too ([Secret keys and `django.utils.crypto`](../security/keys.md)).

## The session hash

`AbstractBaseUser.get_session_auth_hash` is `salted_hmac` of the field `AbstractBaseUser.password`, the string the hasher stored and not the password, with the salt `"django.contrib.auth.models.AbstractBaseUser.get_session_auth_hash"`, the secret key and SHA-256, in hex (`django/contrib/auth/base_user.py:AbstractBaseUser._get_session_auth_hash`). `AbstractBaseUser.get_session_auth_fallback_hash` yields the same HMAC under each key of `SECRET_KEY_FALLBACKS`. The documentation names the purpose: a user can log out every session by changing the password (`docs/topics/auth/default.txt`).

Since the hash is of the stored string, whatever rewrites the string ends every session holding a hash of the old one, whether the password changed or not. A hash upgraded at a login does: in a run that made nora's string and logged nora in with `PBKDF2PasswordHasher.iterations` set within the process to 1,500,000, 6.1's count, and then put it back to 1,800,000, nora's login in a second browser hashed the password again, and the first browser's next request was sent to the login page ([Password hashing: `make_password` and the hashers](hashers.md)).

`update_session_auth_hash` keeps the current session through a password change. It cycles the session key, and writes the new hash when the user is the request's user (`django/contrib/auth/__init__.py:update_session_auth_hash`); the documentation's reason for the new key is that a stolen session cookie stops working (`docs/topics/auth/default.txt`). `PasswordChangeView.form_valid` calls it after saving the form ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](login-views.md)), and so does the admin's view that changes a user's password ([The admin](../admin.md)). `aupdate_session_auth_hash` is its asynchronous twin.
