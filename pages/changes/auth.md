---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in authentication, sessions and messages

`LoginRequiredMiddleware`; the asynchronous functions and the backends' coroutines; `RemoteUserMiddleware` under ASGI; `login` given no user; the PBKDF2 iterations and the removed hashers; and `SessionBase.__bool__`.

6.1 ended two deprecated supports: `login` taking the request's user when given none, and `RemoteUserMiddleware`'s coroutine running a subclass's `process_request`. It also made an empty session false and let permissions follow a renamed model. Every feature release since 5.0 raised the PBKDF2 hasher's iterations, so each rewrites a user's stored string at the next login.

The 5.x changes alter more of how authentication works. 5.1's `LoginRequiredMiddleware` lets a project close every view by default. From 5.0 to 5.2 the asynchronous side of authentication became code of its own, down to the backends' own coroutines, which an asynchronous caller now reaches directly.

## A login for every view: `LoginRequiredMiddleware`

Since 5.1 `LoginRequiredMiddleware` closes every view to an anonymous request unless the decorator `login_not_required` opens it (`django/contrib/auth/middleware.py:LoginRequiredMiddleware.process_view`). Without the middleware, a view is open unless a decorator or a mixin closes it ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md#loginrequiredmiddleware)).

## The asynchronous functions, and a backend's own coroutines

5.0 added the functions `aauthenticate`, `aget_user`, `alogin`, `alogout` and `aupdate_session_auth_hash` (`django/contrib/auth/__init__.py`), with `HttpRequest.auser`. 5.1 added the session store's coroutines, such as `SessionBase.aget` ([The session store: `SessionBase`](../auth/sessions.md#the-asynchronous-methods)). 5.2 added `UserManager.acreate_user`, `PermissionsMixin.ahas_perm` and the other permission methods' coroutines, and the backends' own.

`aauthenticate` awaits the backends' `BaseBackend.aauthenticate` in turn (`django/contrib/auth/__init__.py:aauthenticate`). That method wraps `authenticate` in `sync_to_async`. Since 5.2 `ModelBackend` and `RemoteUserBackend` have their own, on the asynchronous ORM, to "reduce context-switching", the 5.2 notes say (`django/contrib/auth/backends.py:ModelBackend.aauthenticate`, `docs/releases/5.2.txt`). `PermissionsMixin.ahas_perm` asks only the backends that have an `ahas_perm` (`django/contrib/auth/models.py:_auser_has_perm`; [Authenticating: `authenticate` and the backends](../auth/authenticating.md#aauthenticate-and-basebackend)).

> **Trap.** `ModelBackend`'s two kinds of method are separate code, and nothing warns where they differ. Under all four releases, a subclass whose `authenticate` alone refuses the user olga lets `aauthenticate` return olga. A backend not built on `BaseBackend`, with no coroutines of its own, makes `aauthenticate` raise `AttributeError` on reaching it. Its yes from `has_perm` is a no from `ahas_perm`.

## `RemoteUserMiddleware` under ASGI

`RemoteUserMiddleware` logs in the user a server names. 5.2.2 deprecated support for a subclass that overrides `RemoteUserMiddleware.process_request` and not `RemoteUserMiddleware.aprocess_request`, and 6.1 removed it.

The class can run either way, and so takes the mode of the layer inside it (`django/core/handlers/base.py:BaseHandler.load_middleware`). Run asynchronously, `RemoteUserMiddleware.__call__` hands the request to `aprocess_request` alone; synchronously, to `process_request` (`django/contrib/auth/middleware.py:RemoteUserMiddleware.__call__`).

Where the documentation places the subclass, directly after `AuthenticationMiddleware`, 6.1.1's line is the removal at work. This commit's differs, though the class is the same: since 6.2 startproject's middleware inside it, `MessageMiddleware` among them, runs only synchronously, and `RemoteUserMiddleware` takes their mode ([What changed in handlers, requests, URLs and views](request-cycle.md)):

```text recording=changes
A subclass of RemoteUserMiddleware that overrides process_request alone, after AuthenticationMiddleware in startproject's MIDDLEWARE, under ASGI: is the override called
    5.2.17       the override is called, warns RemovedInDjango61Warning
    6.0.8        the override is called, warns RemovedInDjango61Warning
    6.1.1        the override is not called
    this commit  the override is called
```

Placed last in `MIDDLEWARE`, before the chain's asynchronous centre, where the view is called, the override is passed over under 6.1.1 and at this commit, and nothing warns.

Since 6.1 `RemoteUserMiddleware.get_username` adds the prefix `"HTTP_"` only to the default header of an `ASGIRequest` (`django/contrib/auth/middleware.py:RemoteUserMiddleware.get_username`). Under 5.2.17 and 6.0.8 the coroutine read `"HTTP_"` and the header's name, so a subclass whose `header` was `"HTTP_AUTHUSER"` looked up `"HTTP_HTTP_AUTHUSER"` and found no user ([Authenticating: `authenticate` and the backends](../auth/authenticating.md#the-servers-user-remoteusermiddleware-and-remoteuserbackend)).

## `login` given no user, and the request's user after a login

Since 6.1 `login` and `alogin` given `None` no longer fall back on the request's user. 5.2 had deprecated the fallback. Both now ask the user they are given for its session hash first (`django/contrib/auth/__init__.py:login`). The request's user is piet, so a line that names piet is the fallback at work, and the error is `None` asked for its hash:

```text recording=changes
login(request, None), request.user being piet: the user the session is given
    5.2.17       piet, warns RemovedInDjango61Warning
    6.0.8        piet, warns RemovedInDjango61Warning
    6.1.1        AttributeError: 'NoneType' object has no attribute 'get_session_auth_hash'
    this commit  AttributeError: 'NoneType' object has no attribute 'get_session_auth_hash'
```

Since 6.1 `login` and `logout` replace `HttpRequest.auser` as they replace `user` (`django/contrib/auth/__init__.py:_set_auth_user`). Under 5.2.17 and 6.0.8, `await request.auser()` awaited before a `login` still gave the anonymous user after it. No 6.1 note says so.

## Passwords: the iterations, and the hashers removed

`PBKDF2PasswordHasher`, first in the default `PASSWORD_HASHERS`, has had more iterations in every feature release since 5.0, 720,000 in 5.0 and 870,000 in 5.1 (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher`). A stored string carries its own count, and still checks. But a right password checked against a string of an older count is hashed again and saved (`django/contrib/auth/base_user.py:AbstractBaseUser.check_password`; [Password hashing: `make_password` and the hashers](../auth/hashers.md#the-upgrade-at-a-login)). A string stored at 5.0's count is saved again at each release's own:

```text recording=changes
user.check_password("Beagle-1831"), the password stored at 5.0's 720,000 iterations: what is stored after
    5.2.17       pbkdf2_sha256, 1,000,000 iterations
    6.0.8        pbkdf2_sha256, 1,200,000 iterations
    6.1.1        pbkdf2_sha256, 1,500,000 iterations
    this commit  pbkdf2_sha256, 1,800,000 iterations
```

The session hash is made from the stored string, so the rewrite ends the user's sessions in other browsers ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md#the-session-hash)).

CryptPasswordHasher went in 5.0, and SHA1PasswordHasher, UnsaltedSHA1PasswordHasher and UnsaltedMD5PasswordHasher in 5.1 (`docs/releases/5.0.txt`, `docs/releases/5.1.txt`). A project still naming one in `PASSWORD_HASHERS` can neither check nor make a password. `get_hashers` imports every class of the list, so under all four releases a check raises `ImportError` (`django/contrib/auth/hashers.py:get_hashers`). With the name gone from `PASSWORD_HASHERS`, a string that hasher stored finds none, and `verify_password` answers it as a wrong password, without a warning (`django/contrib/auth/hashers.py:verify_password`).

## An empty session is false: `SessionBase.__bool__`

Since 6.1 `SessionBase.__bool__` makes an empty store false. It answers the opposite of `SessionBase.is_empty`: false for a store with no key and no data, without loading (`django/contrib/sessions/backends/base.py:SessionBase.__bool__`; [The session store: `SessionBase`](../auth/sessions.md#empty-is_empty-and-__bool)). Until 6.1 a store had neither `__bool__` nor `__len__`, and was always true, a new one too:

```text recording=changes
bool(SessionStore()): a new session, with no key and no data
    5.2.17       True
    6.0.8        True
    6.1.1        False
    this commit  False
```

> **Trap.** `if request.session:` is now false for a request with no valid key and nothing stored, and nothing warns.

## The smaller changes

The rest, by name:

| what | change | where |
|---|---|---|
| `LogoutView` | Gone in 5.0: logging out by `"GET"`, which gets 405, through `logout_then_login` too | `django/contrib/auth/views.py:LogoutView` |
| `RemoteUserBackend.configure_user` | Since 5.0, always given its created argument, so an override without it raises `TypeError` | `django/contrib/auth/backends.py:RemoteUserBackend.authenticate` |
| make_random_password | Gone in 5.1, from `BaseUserManager` | `django/contrib/auth/base_user.py:BaseUserManager` |
| `ScryptPasswordHasher.parallelism` | Since 5.1, 5 where it was 1, "to follow OWASP recommendations", the notes say | `django/contrib/auth/hashers.py:ScryptPasswordHasher` |
| `AdminUserCreationForm` | New in 5.1.1: `UserAdmin.add_form`, which can save an unusable password | `django/contrib/auth/forms.py:SetUnusablePasswordMixin` |
| the validators' `get_error_message` | New in 5.2: each of Django's validators raises the message it returns | `django/contrib/auth/password_validation.py` |
| a model's default permissions | Since 6.1, follow a model renamed by a migration; under 6.0.8 the old rows stayed beside new ones | `django/contrib/auth/management/__init__.py:rename_permissions_after_model_rename` |
| `Permission.user_perm_str` | New in 6.1: the string `PermissionsMixin.has_perm` takes, such as `"journal.change_entry"` | `django/contrib/auth/models.py:Permission.user_perm_str` |
| the sessions' PickleSerializer | Gone in 5.0: with `SESSION_SERIALIZER` naming it, a store raises `ImportError` as it is made | `django/contrib/sessions/backends/base.py:SessionBase.__init__` |
| the cached database store | Since 5.1, a failure of the cache on a save is logged to `"django.contrib.sessions"`, and the row's change stands; since 6.2, on a delete too | `django/contrib/sessions/backends/cached_db.py` |
| `MessagesTestMixin.assertMessages` | New in 5.0: checks a test response's messages against a list | `django/contrib/messages/test.py:MessagesTestMixin.assertMessages` |
