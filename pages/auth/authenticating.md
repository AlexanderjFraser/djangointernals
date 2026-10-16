---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Authenticating: `authenticate` and the backends

`authenticate` asks the authentication backends of `AUTHENTICATION_BACKENDS`, in order, whether some credentials name a user. `ModelBackend` answers from the user model and a password; `RemoteUserBackend`, called by `RemoteUserMiddleware`, believes a name the web server has already checked.

Django leaves open what credentials are: a username and a password, a token, a name the server vouches for. `authenticate` takes any keyword arguments and leaves their meaning to the **authentication backends**, the classes the setting names. A backend's `BaseBackend.authenticate` returns a user or `None`, and its `BaseBackend.get_user` finds a user again by primary key, which is how a later request gets its user back ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)). The setting's default is `ModelBackend` alone (`django/conf/global_settings.py`).

## Loading the backends

`django.contrib.auth.load_backend` imports the class a dotted path names and calls it, so each call makes a new instance (`django/contrib/auth/__init__.py:load_backend`). `get_backends` does that for every path of the setting, and raises `ImproperlyConfigured` when there is none (`django/contrib/auth/__init__.py:_get_backends`). Nothing is cached: every `authenticate` and permission check makes its backends anew, so what an instance keeps lasts one call.

## `authenticate` in its order

`authenticate` takes the request, `None` unless given, and the credentials as keyword arguments (`django/contrib/auth/__init__.py:authenticate`). It passes over every backend that cannot take them: `_get_compatible_backends`, a generator, reads each backend's authenticate method with `signature` as the loop reaches it and binds the request and the credentials to it, and a `TypeError` skips the backend ([Asking a callable what it accepts: `django/utils/inspect.py`](../utils/inspect.md)) (`django/contrib/auth/__init__.py:_get_compatible_backends`). The keyword arguments' names are the whole protocol. `ModelBackend.authenticate` ends in `**kwargs` and binds anything; `RemoteUserBackend.authenticate` takes remote_user alone, and is never asked about a password.

Each backend left is called in turn, and its answer decides:

- **A user.** The backend's dotted path is set on the user as the attribute `"backend"`, and the user is returned; `login` writes that path into the session.
- **`None`.** The next backend is asked.
- **`PermissionDenied`.** The loop stops; the comment says the user should not be allowed in at all.

When the loop ends without a user, by `PermissionDenied` or by running out of backends, `authenticate` sends `user_login_failed` and returns `None`. The sender is the module's name, `"django.contrib.auth"`; the receiver gets the request, and the credentials with `_clean_credentials` having masked the value of every key containing api, token, key, secret, password or signature, a list its docstring calls not comprehensive (`django/contrib/auth/__init__.py:_clean_credentials`). Both functions are decorated with `sensitive_variables("credentials")`, which marks the dictionary for the error reporter to hide ([The debug pages and `ExceptionReporter`](../views/debug.md#sensitive_variables-and-sensitive_post_parameters)).

The harbour office suspends a clerk by name, in a backend of its own put ahead of `ModelBackend`:

```python
# harbour/office/backends.py
from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import PermissionDenied

SUSPENDED = {"tomas"}


class SuspensionBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None):
        if username in SUSPENDED:
            raise PermissionDenied
        return None
```

With `AUTHENTICATION_BACKENDS` naming `"harbour.office.backends.SuspensionBackend"` and then `ModelBackend`, and a receiver of `user_login_failed` that prints what it is given:

```text
authenticate(username="nora", password="Endeavour-1768")  ->  <User: nora>
    backend: 'django.contrib.auth.backends.ModelBackend'
authenticate(username="tomas", password="Beagle-1831")  ->  None
    user_login_failed: sender='django.contrib.auth', credentials={'username': 'tomas', 'password': '********************'}, request=None
authenticate(token="7f3a")  ->  None
    user_login_failed: sender='django.contrib.auth', credentials={'token': '********************'}, request=None
POST /accounts/login/, nora with a wrong password  ->  200
    user_login_failed: sender='django.contrib.auth', credentials={'username': 'nora', 'password': '********************'}, request=<WSGIRequest: POST '/accounts/login/'>
```

Tomas's password is right, but `ModelBackend` was never asked. The token reached `ModelBackend` alone, the office's backend having no parameter for it. The login form passes its request on ([The authentication forms: `AuthenticationForm` and the password forms](user-forms.md)).

## `aauthenticate` and `BaseBackend`

`aauthenticate` is the same loop, awaiting each backend's `BaseBackend.aauthenticate` and sending the signal with `Signal.asend`; it picks the backends by their synchronous method's signature (`django/contrib/auth/__init__.py:aauthenticate`).

Every method `BaseBackend` declares answers no: `BaseBackend.authenticate` and `BaseBackend.get_user` return `None`, `BaseBackend.get_user_permissions` and `BaseBackend.get_group_permissions` an empty set, and `BaseBackend.has_perm` looks in those two (`django/contrib/auth/backends.py:BaseBackend`). Its `aauthenticate`, `BaseBackend.aget_user` and the two asynchronous getters call the synchronous methods through `sync_to_async`, so a direct subclass that defines only those serves both kinds of caller. The permission methods are looked for with `hasattr` ([Permissions: `Permission`, groups and `has_perm`](permissions.md)); the authenticate method is not, so every listed backend needs one.

## `ModelBackend`: a username and a password

`ModelBackend.authenticate` takes username and password, or, for the username, the keyword argument named after the user model's `USERNAME_FIELD`; without both it returns `None` (`django/contrib/auth/backends.py:ModelBackend.authenticate`). It finds the user with `BaseUserManager.get_by_natural_key` and hands the user, or `None` when there is no such row, to `check_password_with_timing_attack_mitigation`.

That function is why a missing username costs as much as a wrong password. Given a user, it returns `AbstractBaseUser.check_password`'s answer ([Password hashing: `make_password` and the hashers](hashers.md)). Given none, it sets the password on an unsaved instance of the user model, which runs the default hasher once for nothing; its docstring's reason is to prevent user enumeration attacks, ticket 20760 (`django/contrib/auth/__init__.py:check_password_with_timing_attack_mitigation`). In one run on one machine, nora's right password, a wrong one and an unknown username each took one query and about 0.6 seconds.

Last, `ModelBackend.user_can_authenticate` refuses a user whose `is_active` is false, and admits a user model without that attribute; asked after the password, its refusal takes as long as any other. `ModelBackend.get_user` applies the same test, so a user made inactive is not found at the next request of a session (`django/contrib/auth/backends.py:ModelBackend.get_user`). `AllowAllUsersModelBackend` overrides `user_can_authenticate` to admit everyone.

Apache's mod_wsgi can call Django's `check_password` outside the request cycle (`docs/howto/deployment/wsgi/apache-auth.txt`): `None` when no active user has the name, otherwise whether the password matches, by the same timing function and without the backends (`django/contrib/auth/handlers/modwsgi.py:check_password`).

## The server's user: `RemoteUserMiddleware` and `RemoteUserBackend`

When the web server has authenticated the browser, Django has only to believe the name it passes on (`docs/howto/auth-remote-user.txt`). `RemoteUserBackend.authenticate` returns `None` for an empty name, cleans it with `RemoteUserBackend.clean_username`, a no-op by default, and, while `RemoteUserBackend.create_unknown_user` is true, gets or creates the user of that name by `get_or_create`, for its safeguards when threads race, a comment says; otherwise it only looks the user up. `RemoteUserBackend.configure_user`, given the user and whether it was just created, returns it unchanged unless overridden; the inherited `user_can_authenticate` refuses an inactive user (`django/contrib/auth/backends.py:RemoteUserBackend.authenticate`). `AllowAllUsersRemoteUserBackend` admits everyone.

`RemoteUserMiddleware` is not built on `MiddlewareMixin`. It serves either kind of chain, running `RemoteUserMiddleware.process_request`, or in an asynchronous one `RemoteUserMiddleware.aprocess_request`, before the layer inside, and does nothing on the way out (`django/contrib/auth/middleware.py:RemoteUserMiddleware`). In its order:

1. Without the user that `AuthenticationMiddleware` puts on the request, it raises `ImproperlyConfigured`: it has to come after `AuthenticationMiddleware`.
2. It reads the name from `HttpRequest.META` under `RemoteUserMiddleware.header`. With none, it hands a logged-in user to `RemoteUserMiddleware._remove_invalid_user` if `RemoteUserMiddleware.force_logout_if_no_header` is true, and is done.
3. If the logged-in user has that name, cleaned by the session's backend's `clean_username` if it has one, it is done. A different user is handed to `_remove_invalid_user`.
4. It calls `authenticate` with the name as remote_user, and logs in with `login` the user it gets.

`RemoteUserMiddleware._remove_invalid_user` logs out only a user whose session names a `RemoteUserBackend`, or a backend that no longer imports. `PersistentRemoteUserMiddleware` sets `force_logout_if_no_header` false, for a site where, its docstring says, the server authenticates only on a logon URL and Django's session carries the user elsewhere.

With `RemoteUserMiddleware` after `AuthenticationMiddleware`, the setting naming `RemoteUserBackend` and then `ModelBackend`, and the test client putting REMOTE_USER in the WSGI environ as a server would, one browser and then another:

```text
GET /berths/, REMOTE_USER="nora"   ->  200 Signed in as nora.; sessionid set; backend RemoteUserBackend; 9 queries
GET /berths/, REMOTE_USER="nora"   ->  200 Signed in as nora.; backend RemoteUserBackend; 2 queries
GET /berths/, REMOTE_USER="ingrid" ->  200 Signed in as ingrid.; sessionid set; backend RemoteUserBackend; 16 queries
GET /berths/, no REMOTE_USER       ->  302 to /accounts/login/?next=/berths/; sessionid deleted; 4 queries

POST /accounts/login/, nora        ->  302 to /berths/; sessionid set; backend ModelBackend; 9 queries
GET /berths/, no REMOTE_USER       ->  200 Signed in as nora.; backend ModelBackend; 2 queries
GET /berths/, REMOTE_USER="tomas"  ->  200 Signed in as tomas.; sessionid set; backend RemoteUserBackend; 10 queries
```

The third request logged nora out, made a row for ingrid from the username alone, and logged ingrid in under a new key. Nora's password login outlived a request without the name, but not another name: `_remove_invalid_user` left the session alone, and `login` emptied it for holding another user.

Under WSGI no request header can reach the key `"REMOTE_USER"`, which only the server can set. Under ASGI there is no environ, and `RemoteUserMiddleware.get_username` reads `"HTTP_REMOTE_USER"`, the Remote-User header, while `header` is the default; a subclass's `header` is read as written, as `"HTTP_AUTHUSER"` (`django/contrib/auth/middleware.py:RemoteUserMiddleware.get_username`). The documentation's warning follows: under ASGI a reverse proxy must always set or strip the header (`docs/howto/auth-remote-user.txt`).

> **Changed in 6.1.** Under ASGI a custom `header` is again read without an added `"HTTP_"`, as before 5.2 (`docs/releases/6.1.txt`).
