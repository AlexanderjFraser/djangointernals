---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in authentication, sessions and messages

The changes from Django 5.0 to this commit in `django.contrib.auth`, `django.contrib.sessions` and `django.contrib.messages`: `LoginRequiredMiddleware`, the asynchronous twins down to the backends' coroutines, `RemoteUserMiddleware` under ASGI, the PBKDF2 iterations, the hashers removed and the old uses that now fail.

Two changes alter the model: a middleware can require a login of every view, and since 5.2 an asynchronous caller reaches a backend's own coroutines, which need not do what its synchronous methods do.

## A login for every view: `LoginRequiredMiddleware`

`LoginRequiredMiddleware` (5.1) turns the default round. Without it a view is open unless a decorator or a mixin closes it; with it, after `AuthenticationMiddleware`, `LoginRequiredMiddleware.process_view` redirects an anonymous request from every view whose attribute `"login_required"` is not false, which `login_not_required` (5.1) sets (`django/contrib/auth/middleware.py:LoginRequiredMiddleware.process_view`). The redirect goes to the login URL a decorator left on the view, else to `LOGIN_URL`, whatever login URL a view's `LoginRequiredMixin` names. Django marks its login and password-reset views, not `LogoutView` ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md#loginrequiredmiddleware)).

## The asynchronous functions and methods

The coroutine twins came in three releases. 5.0 added `aauthenticate`, `aget_user`, `alogin`, `alogout` and `aupdate_session_auth_hash` (`django/contrib/auth/__init__.py`), `HttpRequest.auser` beside `HttpRequest.user` (`django/contrib/auth/middleware.py:auser`) and `AbstractBaseUser.acheck_password`. 5.1 gave the session store and its backends asynchronous methods, such as `SessionBase.aget` ([The session store: `SessionBase`](../auth/sessions.md#the-asynchronous-methods)), and let `login_required`, `permission_required` and `user_passes_test` wrap a coroutine view; at this commit the wrapper awaits `HttpRequest.auser`, and the test of `permission_required` awaits `PermissionsMixin.ahas_perms` (`django/contrib/auth/decorators.py:user_passes_test`, `django/contrib/auth/decorators.py:permission_required`). 5.2 added `UserManager.acreate_user`, `UserManager.acreate_superuser`, `BaseUserManager.aget_by_natural_key`, `PermissionsMixin.ahas_perm` and the other permission methods, and the backends'.

The backends' twins changed what an asynchronous caller runs. `aauthenticate` picks the backends by the signature of their synchronous `authenticate`, then awaits each one's `BaseBackend.aauthenticate` (`django/contrib/auth/__init__.py:aauthenticate`). `BaseBackend.aauthenticate` runs the synchronous method through `sync_to_async`; since 5.2 `ModelBackend` and `RemoteUserBackend` have their own, which query with the asynchronous ORM, to switch less, the release notes say, between the event loop and a thread (`django/contrib/auth/backends.py:ModelBackend.aauthenticate`, `docs/releases/5.2.txt`). `aget_user` awaits the backend's `BaseBackend.aget_user` the same way, and `PermissionsMixin.ahas_perm` asks only the backends that have an `ahas_perm` (`django/contrib/auth/models.py:_auser_has_perm`).

So a backend's two kinds of method are separate code. Where a subclass of `ModelBackend` overrides `authenticate` alone, `aauthenticate` passes the override over and runs the inherited coroutine; a backend not built on `BaseBackend` that defines no coroutines makes `aauthenticate` raise when it comes to it, and has no say in `ahas_perm`. The documentation asks a project that extends Django's backends to change both versions (`docs/topics/auth/customizing.txt`).

```text
# auth_blocks.py at this commit: first a ModelBackend subclass whose authenticate alone refuses tomas,
# then PlainBackend, a class with no base whose has_perm says yes
authenticate(username="tomas", password="Beagle-1831")   None
aauthenticate(username="tomas", password="Beagle-1831")  <User: tomas>
aauthenticate(username="nora", password="x")             AttributeError: 'PlainBackend' object has no attribute 'aauthenticate'
nora.has_perm("fleet.change_ship")                       True
nora.ahas_perm("fleet.change_ship")                      False
```

## `RemoteUserMiddleware` under ASGI

`RemoteUserMiddleware.aprocess_request` serves an asynchronous chain, awaiting `HttpRequest.auser`, `aauthenticate` and `alogin` ([Authenticating: `authenticate` and the backends](../auth/authenticating.md#the-servers-user-remoteusermiddleware-and-remoteuserbackend)). A subclass that overrode `RemoteUserMiddleware.process_request` alone was still served there, a support deprecated in 5.2 and removed in 6.1. At this commit `RemoteUserMiddleware.__call__` gives the request to the coroutine alone whenever the middleware runs asynchronously, as under ASGI it does when the layer inside it does ([Sync and async in one chain](../handlers/async.md)) (`django/contrib/auth/middleware.py:RemoteUserMiddleware.__call__`). In a run, such an override ran in a synchronous chain; in an asynchronous one the base class's coroutine logged nora in instead, and nothing warned.

5.2 also made the middleware read a custom header under ASGI with `"HTTP_"` before it, and 6.1 undid that: `RemoteUserMiddleware.get_username` adds the prefix to the default `RemoteUserMiddleware.header` alone, reading `"HTTP_REMOTE_USER"` (`django/contrib/auth/middleware.py:RemoteUserMiddleware.get_username`).

## Passwords and the hashers

The PBKDF2 hasher's iterations rose in every feature release: 720,000 in 5.0, 870,000 in 5.1, 1,000,000 in 5.2, 1,200,000 in 6.0, 1,500,000 in 6.1 and 1,800,000 in 6.2 (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher`). `ScryptPasswordHasher.parallelism` went from 1 to 5 in 5.1, to follow OWASP's recommendations, the release notes say (`docs/releases/5.1.txt`). A stored string carries its own cost and still checks; but `PBKDF2PasswordHasher.must_update` and `ScryptPasswordHasher.must_update` compare that cost with the class's, so where the hasher comes first in `PASSWORD_HASHERS`, a right password checked through `AbstractBaseUser.check_password` against an older string is hashed again and saved ([Password hashing: `make_password` and the hashers](../auth/hashers.md#the-upgrade-at-a-login)). The session's hash is made from the stored string, so the upgrade ends the user's sessions in other browsers ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md#the-session-hash)).

CryptPasswordHasher was removed in 5.0, and SHA1PasswordHasher, UnsaltedSHA1PasswordHasher and UnsaltedMD5PasswordHasher in 5.1. A string they made finds no hasher of Django's: `identify_hasher` still recognises the unsalted forms by their shape, `get_hasher` raises `ValueError` for an algorithm no listed hasher has, and `verify_password` answers that as a password that does not match (`django/contrib/auth/hashers.py:verify_password`). A user whose row holds such a string cannot log in by password, and nothing warns.

## What else was removed

| removed | release | at this commit |
|---|---|---|
| logging out by `"GET"` | 5.0 | `LogoutView.http_method_names` is `"post"` and `"options"`, so a `"GET"` gets 405, and `logout_then_login` logs out only on a `"POST"` ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](../auth/login-views.md#logoutview-and-logout_then_login)) |
| `RemoteUserBackend.configure_user` without created | 5.0 | `RemoteUserBackend.authenticate` always passes `created=`, so an override without it raises `TypeError` (`django/contrib/auth/backends.py:RemoteUserBackend.authenticate`) |
| the sessions' PickleSerializer | 5.0 | `django/contrib/sessions/serializers.py` holds `JSONSerializer` alone, and `SessionBase.__init__` imports the class `SESSION_SERIALIZER` names for every store (`django/contrib/sessions/backends/base.py:SessionBase.__init__`) |
| make_random_password of `BaseUserManager` | 5.1 | no such method |
| the request's user, when `login` or `alogin` is given `None` | 5.2 to 6.1 | both ask the user they are given for its session hash first (`django/contrib/auth/__init__.py:login`) |

```text
# auth_blocks.py at this commit: OldRemoteUserBackend overrides configure_user(self, request, user);
# for the third line SESSION_SERIALIZER names "django.contrib.sessions.serializers.PickleSerializer"
login(request, None)                AttributeError: 'NoneType' object has no attribute 'get_session_auth_hash'
authenticate(remote_user="ingrid")  TypeError: OldRemoteUserBackend.configure_user() got an unexpected keyword argument 'created'
SessionStore()                      ImportError: Module "django.contrib.sessions.serializers" does not define a "PickleSerializer" attribute/class
```

## Forms, permissions, sessions and messages

| change | release | at this commit |
|---|---|---|
| `AdminUserCreationForm` | 5.1 | `UserAdmin.add_form` (`django/contrib/auth/admin.py:UserAdmin`); it, and `AdminPasswordChangeForm` for a usable password, can save an unusable one ([The authentication forms: `AuthenticationForm` and the password forms](../auth/user-forms.md#setunusablepasswordmixin-and-the-admins-forms)) |
| `ReadOnlyPasswordHashWidget` | 5.1 | draws a button to the password page, where the field's help text held a link (`django/contrib/auth/templates/auth/widgets/read_only_password_hash.html`) |
| the password validators' `get_error_message` | 5.2 | each of Django's raises the message the method returns (`django/contrib/auth/password_validation.py:MinimumLengthValidator.get_error_message`) |
| a model renamed by a migration | 6.1 | its default permissions' codenames and names follow it ([Making the permissions: `create_permissions`](../auth/creating-permissions.md#renaming-with-the-model-rename_permissions_after_model_rename)) |
| `Permission.user_perm_str` | 6.1 | the string `PermissionsMixin.has_perm` takes, `"fleet.change_ship"` (`django/contrib/auth/models.py:Permission`) |
| `SessionBase.__bool__` | 6.1 | false for a store with no key and no data, answered without loading ([The session store: `SessionBase`](../auth/sessions.md#empty-is_empty-and-__bool)) |
| the cached database store | 5.1, 6.2 | logs to `"django.contrib.sessions"` an exception from the cache on a save (5.1) or a delete (6.2), and the row's change stands ([The session backends](../auth/session-backends.md#the-cached-database-backend)) |
| the admin's debug and info messages | 6.0 | an icon and a colour of their own, where both looked like success; `ModelAdmin.message_user` adds at info unless told otherwise (`django/contrib/admin/static/admin/css/base.css`) |
| `MessagesTestMixin.assertMessages` | 5.0 | compares the messages of a test response's request with a list, in order unless `ordered=False` (`django/contrib/messages/test.py:MessagesTestMixin.assertMessages`); the other assertions are in [What changed in the test framework](testing.md) |
