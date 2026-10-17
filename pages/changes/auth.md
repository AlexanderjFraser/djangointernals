---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in authentication, sessions and messages

The changes from Django 5.0 to this commit in `django.contrib.auth`, `django.contrib.sessions` and `django.contrib.messages`: `LoginRequiredMiddleware`; the asynchronous functions and the backends' coroutines; `RemoteUserMiddleware` under ASGI; the function `login` given no user; the PBKDF2 iterations and the hashers removed; `SessionBase.__bool__`; and smaller changes.

6.1 ended two supports 5.2 had deprecated: `login` taking the request's user when given none, and `RemoteUserMiddleware`'s coroutine running a subclass's `process_request`. It also made an empty session false and let permissions follow a renamed model. Every feature release raised the PBKDF2 hasher's iterations, so each rewrites a user's stored string at the next login.

The 5.x changes alter the model more. 5.1's `LoginRequiredMiddleware` lets a project close every view by default, and from 5.0 to 5.2 the asynchronous side of authentication became code of its own, down to the backends' own coroutines, which an asynchronous caller now reaches directly.

## A login for every view: `LoginRequiredMiddleware`

Without `LoginRequiredMiddleware` (5.1) a view is open unless a decorator or a mixin closes it; with it, after `AuthenticationMiddleware`, every view is closed to an anonymous request unless the decorator `login_not_required` (5.1) opens it (`django/contrib/auth/middleware.py:LoginRequiredMiddleware.process_view`). The redirect goes to the login URL `login_required` left on the view, or to `LOGIN_URL`. A `LoginRequiredMixin`'s login URL, an attribute of the class, is not read: under 5.2.17 as at this commit, a mixin's `"/journal/login/"` loses to `LOGIN_URL`. Django opens its login and password-reset views, not `LogoutView` ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md#loginrequiredmiddleware)).

## The asynchronous functions, and a backend's own coroutines

5.0 added the functions `aauthenticate`, `aget_user`, `alogin`, `alogout` and `aupdate_session_auth_hash` (`django/contrib/auth/__init__.py`) with `HttpRequest.auser`, 5.1 the session store's coroutines, such as `SessionBase.aget` ([The session store: `SessionBase`](../auth/sessions.md#the-asynchronous-methods)), and 5.2 `UserManager.acreate_user`, `PermissionsMixin.ahas_perm` and the other permission methods' coroutines, and those of the backends.

`aauthenticate` picks the backends by the signature of their synchronous `authenticate`, then awaits each one's `BaseBackend.aauthenticate` (`django/contrib/auth/__init__.py:aauthenticate`). `BaseBackend.aauthenticate` wraps `authenticate` in `sync_to_async`, but since 5.2 `ModelBackend` and `RemoteUserBackend` have their own, on the asynchronous ORM, to "reduce context-switching", the 5.2 notes say (`django/contrib/auth/backends.py:ModelBackend.aauthenticate`, `docs/releases/5.2.txt`). `PermissionsMixin.ahas_perm` asks only the backends that have an `ahas_perm` (`django/contrib/auth/models.py:_auser_has_perm`; [Authenticating: `authenticate` and the backends](../auth/authenticating.md#aauthenticate-and-basebackend)).

> **Trap.** `ModelBackend`'s two kinds of method are separate code, and nothing warns where they differ. Under 5.2.17 as at this commit, a subclass whose `authenticate` alone refuses the user olga lets `aauthenticate` return olga; a backend not built on `BaseBackend`, and with no coroutines of its own, makes `aauthenticate` raise `AttributeError` on reaching it, and its yes from `has_perm` is a no from `ahas_perm`. The documentation asks a project extending Django's backends to change both (`docs/topics/auth/customizing.txt`).

## `RemoteUserMiddleware` under ASGI

`RemoteUserMiddleware`, which logs in the user a server names, is not built on `MiddlewareMixin`; it can run either way, and so takes the mode of the layer inside it, the next in `MIDDLEWARE` (`django/core/handlers/base.py:BaseHandler.load_middleware`). In an asynchronous chain `RemoteUserMiddleware.__call__` hands the request to `RemoteUserMiddleware.aprocess_request` alone, in a synchronous one to `RemoteUserMiddleware.process_request` (`django/contrib/auth/middleware.py:RemoteUserMiddleware.__call__`). Here a subclass overriding `process_request` alone serves a GET under ASGI, directly after `AuthenticationMiddleware` in startproject's `MIDDLEWARE`, as the documentation places it. This commit's line differs from 6.1.1's though the class is the same: since 6.2 the middleware inside it, `MessageMiddleware` among them, runs only synchronously, and `RemoteUserMiddleware` takes their mode ([What changed in handlers, requests, URLs and views](request-cycle.md)):

```text recording=changes
A subclass of RemoteUserMiddleware that overrides process_request alone, after AuthenticationMiddleware in startproject's MIDDLEWARE, under ASGI: is the override called
    5.2.17       the override is called, warns RemovedInDjango61Warning
    6.0.8        the override is called, warns RemovedInDjango61Warning
    6.1.1        the override is not called
    this commit  the override is called
```

5.2 deprecated the support for such a subclass, and 6.1 removed it. 5.2.0 and 5.2.1 had lost it (`docs/releases/5.2.2.txt`). Placed last in `MIDDLEWARE`, before the asynchronous centre, the subclass is passed over under 6.1.1 and at this commit, and nothing warns.

Under 5.2.17 and 6.0.8 the coroutine read `"HTTP_"` and the header's name, so a subclass whose `header` was `"HTTP_AUTHUSER"` looked up `"HTTP_HTTP_AUTHUSER"` and found no user. Since 6.1 `RemoteUserMiddleware.get_username` serves both paths, adding the prefix only to the default header of an `ASGIRequest` (`django/contrib/auth/middleware.py:RemoteUserMiddleware.get_username`); a custom header the synchronous path always read as written ([Authenticating: `authenticate` and the backends](../auth/authenticating.md#the-servers-user-remoteusermiddleware-and-remoteuserbackend)).

## `login` given no user, and the request's user after a login

From 5.2 `login` and `alogin` warned when given `None`, and logged in the request's user; 6.1 removed the fallback, and both ask the user they are given for its session hash first (`django/contrib/auth/__init__.py:login`). Here piet is the request's user, so piet is the fallback at work:

```text recording=changes
login(request, None), request.user being piet: the user the session is given
    5.2.17       piet, warns RemovedInDjango61Warning
    6.0.8        piet, warns RemovedInDjango61Warning
    6.1.1        AttributeError: 'NoneType' object has no attribute 'get_session_auth_hash'
    this commit  AttributeError: 'NoneType' object has no attribute 'get_session_auth_hash'
```

Since 6.1 `login` and `logout` replace `HttpRequest.auser` as they replace `user` (`django/contrib/auth/__init__.py:_set_auth_user`). Under 5.2.17 and 6.0.8, `await request.auser()` awaited before a `login` still gave the anonymous user after it, which no 6.1 note says.

## Passwords: the iterations, and the hashers removed

`PBKDF2PasswordHasher`, first in the default `PASSWORD_HASHERS`, has had more iterations in every feature release, 720,000 in 5.0 and 870,000 in 5.1 (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher`). A stored string carries its own count and still checks, but `PBKDF2PasswordHasher.must_update` compares the count with the class's, and a right password checked against an older string is hashed again and saved (`django/contrib/auth/base_user.py:AbstractBaseUser.check_password`; [Password hashing: `make_password` and the hashers](../auth/hashers.md#the-upgrade-at-a-login)). Here a string stored at 5.0's count is checked:

```text recording=changes
user.check_password("Beagle-1831"), the password stored at 5.0's 720,000 iterations: what is stored after
    5.2.17       pbkdf2_sha256, 1,000,000 iterations
    6.0.8        pbkdf2_sha256, 1,200,000 iterations
    6.1.1        pbkdf2_sha256, 1,500,000 iterations
    this commit  pbkdf2_sha256, 1,800,000 iterations
```

The session hash is made from the stored string, so the rewrite ends the user's sessions in other browsers: under 5.2.17 as at this commit, a session logged in before the check is anonymous after it ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md#the-session-hash)).

CryptPasswordHasher went in 5.0, and SHA1PasswordHasher, UnsaltedSHA1PasswordHasher and UnsaltedMD5PasswordHasher in 5.1 (`docs/releases/5.0.txt`, `docs/releases/5.1.txt`). A project still naming one in `PASSWORD_HASHERS` can neither check nor make a password, since `get_hashers` imports every class of the list: under 5.2.17 as at this commit, a check raises `ImportError` (`django/contrib/auth/hashers.py:get_hashers`). With the name gone, the string finds no hasher, and `verify_password` answers it as a wrong password, without a warning (`django/contrib/auth/hashers.py:verify_password`).

## An empty session is false: `SessionBase.__bool__`

Until 6.1 a session store had neither `__bool__` nor `__len__`, and was always true. Since 6.1 `SessionBase.__bool__` answers the opposite of `SessionBase.is_empty`: false for a store with no key and no data, without loading (`django/contrib/sessions/backends/base.py:SessionBase.__bool__`; [The session store: `SessionBase`](../auth/sessions.md#empty-is_empty-and-__bool)). Here the store is new:

```text recording=changes
bool(SessionStore()): a new session, with no key and no data
    5.2.17       True
    6.0.8        True
    6.1.1        False
    this commit  False
```

> **Trap.** `if request.session:`, always true before 6.1, is now false for a request with no valid key and nothing stored, and nothing warns.

## The smaller changes

The rest, by name:

| what | at this commit | release | where |
|---|---|---|---|
| logging out by `"GET"` | `LogoutView.http_method_names` is `"post"` and `"options"`: a `"GET"`, through `logout_then_login` too, gets 405 | 5.0 | `django/contrib/auth/views.py:LogoutView` |
| `RemoteUserBackend.configure_user` | always given `created=`, so an override without it raises `TypeError` | 5.0 | `django/contrib/auth/backends.py:RemoteUserBackend.authenticate` |
| the sessions' PickleSerializer | removed; with `SESSION_SERIALIZER` naming it, a store raises `ImportError` as it is made | 5.0 | `django/contrib/sessions/backends/base.py:SessionBase.__init__` |
| make_random_password | removed from `BaseUserManager` | 5.1 | `django/contrib/auth/base_user.py:BaseUserManager` |
| `ScryptPasswordHasher.parallelism` | 5, where it was 1, "to follow OWASP recommendations" (`docs/releases/5.1.txt`) | 5.1 | `django/contrib/auth/hashers.py:ScryptPasswordHasher` |
| `AdminUserCreationForm` | `UserAdmin.add_form`; it and `AdminPasswordChangeForm` can save an unusable password | 5.1 | `django/contrib/auth/forms.py:SetUnusablePasswordMixin` |
| the validators' `get_error_message` | each of Django's raises the message it returns | 5.2 | `django/contrib/auth/password_validation.py:MinimumLengthValidator.get_error_message` |
| a model renamed by a migration | its default permissions follow it; under 6.0.8 the old rows stayed beside new ones | 6.1 | `django/contrib/auth/management/__init__.py:rename_permissions_after_model_rename` |
| `Permission.user_perm_str` | new: `"journal.change_entry"`, the string `PermissionsMixin.has_perm` takes | 6.1 | `django/contrib/auth/models.py:Permission.user_perm_str` |
| the cached database store | a failure of the cache is logged to `"django.contrib.sessions"`, and the row's change stands: after a save since 5.1, after a delete since 6.2 | 5.1, 6.2 | [The session backends](../auth/session-backends.md#the-cached-database-backend) |
| `MessagesTestMixin.assertMessages` | new: a test response's messages against a list | 5.0 | `django/contrib/messages/test.py:MessagesTestMixin.assertMessages` |
