---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`

`login_required` and `permission_required` are made from `user_passes_test`, which tests the request's user before the view runs and answers a failure with a redirect from `redirect_to_login`, the address asked for carried in `"next"` by default. `LoginRequiredMixin`, `PermissionRequiredMixin` and `UserPassesTestMixin` test in `dispatch` and answer a logged-in user who fails with 403, not a redirect; `LoginRequiredMiddleware` requires a login of every view that `login_not_required` does not mark.

A view that serves only some users must decide before it does any work. A browser with no logged-in user is ordinarily sent to the login page with the address it asked for, for the login view to send it back ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](login-views.md)); a logged-in user who lacks a right is answered 403, or sent to log in as someone else. The decision is made around a function view by a decorator, inside `dispatch` by a mixin, or for every view by a middleware.

## `user_passes_test`

`user_passes_test` takes a test, a callable given a user that answers true or false, and returns a decorator, which picks its wrapper by whether the view is a coroutine function. Around an ordinary view the wrapper calls the test with `HttpRequest.user`, through `async_to_sync` if the test is a coroutine function; such a test runs in an event loop, where reading a user not yet loaded can query the database, which Django refuses with `SynchronousOnlyOperation` (`django/utils/asyncio.py:async_unsafe`). Around a coroutine view it awaits `HttpRequest.auser` and then the test, an ordinary test through `sync_to_async` ([Asynchronous views](../views/async.md)). A true answer calls the view, a false one returns the redirect, and an exception the test raises goes out through the wrapper (`django/contrib/auth/decorators.py:user_passes_test`).

The decorator also puts the login URL and field name it was given on the wrapper, as `"login_url"` and `"redirect_field_name"`, for `LoginRequiredMiddleware`, and the wrapper takes the view's name and attributes, so a mark left by an inner decorator survives ([What the handler asks of a view](../views/callable.md#what-other-code-reads-from-a-view)).

## The redirect: `redirect_to_login`

The login URL is the decorator's argument or `LOGIN_URL`, `"/accounts/login/"` by default, passed through `resolve_url`, so either may be a path or a URL pattern's name ([The shortcuts](../views/shortcuts.md#redirect-and-resolve_url)). The address to come back to is the request's whole URL, from `HttpRequest.build_absolute_uri`, cut to its path and query string by `HttpRequest.get_full_path` when the login URL has no scheme or the request's, and no host or the request's (`django/contrib/auth/decorators.py:user_passes_test`).

`redirect_to_login` keeps any query string the login URL has, sets the address under the field's name, `"next"` unless the decorator names another, and encodes the query with `"/"` left as it is; an empty field name, or `None`, adds nothing. It returns an `HttpResponseRedirect` (`django/contrib/auth/views.py:redirect_to_login`). The office's crew list is under `login_required(login_url="https://accounts.harbour.example/login/")`:

```text
a browser with no session
GET /berths/?ship=Beagle    302  Location: /accounts/login/?next=/berths/%3Fship%3DBeagle
GET /crew/                  302  Location: https://accounts.harbour.example/login/?next=http%3A//harbour.example/crew/
```

## `login_required` and `login_not_required`

`login_required` is `user_passes_test` with a test that reads the user's `is_authenticated`, written bare above a view or called with a login URL and a field's name; it does not look at `is_active` (`django/contrib/auth/decorators.py:login_required`).

`login_not_required` wraps nothing. It sets the view's attribute `"login_required"` to false and returns the same function (`django/contrib/auth/decorators.py:login_not_required`). Only `LoginRequiredMiddleware` reads it.

## `permission_required`

`permission_required` takes one permission's name or an iterable of names, and builds for `user_passes_test` a test of the view's kind, which asks `PermissionsMixin.has_perms`, or `PermissionsMixin.ahas_perms`, whether the user has all of them ([Permissions: `Permission`, groups and `has_perm`](permissions.md)). It asks an anonymous user too, as a comment notes. When the answer is no, the test raises `PermissionDenied` if the decorator was given `raise_exception=True`, which the handler turns into a 403 ([How an exception becomes a response](../handlers/exceptions.md)); otherwise it returns false, and the user is sent to the login page, logged in or not (`django/contrib/auth/decorators.py:permission_required`).

So a logged-in user lacking it is asked to log in again, and under `raise_exception=True` a stranger never sees the login page. The documentation's remedy is `login_required` written above the raising decorator, which also avoids a loop when `LoginView.redirect_authenticated_user` sends a logged-in user back (`docs/topics/auth/default.txt`). The office's edit_ship raises; its rename view, under `permission_required("fleet.change_ship")`, does not:

```text
GET /ships/1/edit/      permission_required("fleet.change_ship", raise_exception=True)
  tomas                 403
  no session            403
GET /ships/1/rename/    permission_required("fleet.change_ship")
  nora                  200
  tomas                 302  Location: /accounts/login/?next=/ships/1/rename/
  no session            302  Location: /accounts/login/?next=/ships/1/rename/
```

## The mixins and `AccessMixin.handle_no_permission`

Each mixin tests in `dispatch` and calls `super().dispatch` only when the test passes, so it stands before `View` among the bases ([`View.as_view` and dispatch](../views/as-view.md)). `LoginRequiredMixin.dispatch` tests `is_authenticated`. `PermissionRequiredMixin.has_permission` asks `has_perms` for the names that `PermissionRequiredMixin.get_permission_required` gives, and the latter raises `ImproperlyConfigured` when `PermissionRequiredMixin.permission_required` is left `None`. `UserPassesTestMixin.dispatch` calls, with no argument, the method `UserPassesTestMixin.get_test_func` returns, `UserPassesTestMixin.test_func` by default (`django/contrib/auth/mixins.py`).

A failure goes to `AccessMixin.handle_no_permission`, which differs from the decorators in one decision: it raises `PermissionDenied`, with `AccessMixin.get_permission_denied_message` as its message, when `AccessMixin.raise_exception` is true or the user is logged in. Only an anonymous user is redirected, to an address worked out as the decorator's is; `AccessMixin.get_login_url` raises `ImproperlyConfigured` when neither `AccessMixin.login_url` nor `LOGIN_URL` gives a URL (`django/contrib/auth/mixins.py:AccessMixin.handle_no_permission`). So tomas, whom the rename view sends to log in, gets 403 from the office's manifest, a view with `PermissionRequiredMixin` and the same permission:

```text
GET /manifest/          PermissionRequiredMixin, "fleet.change_ship"
  tomas                 403
  no session            302  Location: /accounts/login/?next=/manifest/
```

## `LoginRequiredMiddleware`

`LoginRequiredMiddleware` is a `MiddlewareMixin` with one hook, `LoginRequiredMiddleware.process_view`, which the handler calls with the view before calling it ([Building the middleware chain](../handlers/chain.md)). The hook lets the request through when the view's attribute `"login_required"` is false, or when the user is authenticated; otherwise it returns the redirect, and the view is not called. `LoginRequiredMiddleware.handle_no_permission` works the redirect out as the decorator does, from the view's `"login_url"` or `LOGIN_URL` (with neither, `LoginRequiredMiddleware.get_login_url` raises `ImproperlyConfigured`), and the view's `"redirect_field_name"` or `LoginRequiredMiddleware.redirect_field_name`, `"next"` (`django/contrib/auth/middleware.py:LoginRequiredMiddleware`).

Under the middleware, `login_required` carries its login URL and field's name to it, and a stranger is redirected before the decorator's wrapper is reached. A mixin carries nothing to it: its login URL and field's name are attributes of the class, and the middleware reads the function `View.as_view` returns. 5.1's release notes say the middleware does not support setting either through `LoginRequiredMixin` (`docs/releases/5.1.txt`). The office's roster has `LoginRequiredMixin` with a login URL of `"/crew/login/"`; its tide table has no decorator:

```text
a browser with no session, without LoginRequiredMiddleware
GET  /roster/                     302  Location: /crew/login/?next=/roster/
with LoginRequiredMiddleware after AuthenticationMiddleware
GET  /tide/                       302  Location: /accounts/login/?next=/tide/
GET  /roster/                     302  Location: /accounts/login/?next=/roster/
GET  /accounts/login/             200
GET  /accounts/password_reset/    200
POST /accounts/logout/            302  Location: /accounts/login/?next=/accounts/logout/
```

A class-based view is marked through `method_decorator` on `dispatch`, which copies onto `dispatch` the attributes its decorator sets, and `View.as_view` copies those onto the function it returns (`django/utils/decorators.py:_update_method_wrapper`, `django/views/generic/base.py:View.as_view`). So `LoginView` and the four views of the password reset are `login_not_required`; `LogoutView` is not, and the password-change views carry `login_required` (`django/contrib/auth/views.py`). The admin marks its login view, and gives the site-wide views that `AdminSite.get_urls` wraps its login page as their login URL ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](../admin/site-urls.md)) (`django/contrib/admin/sites.py:AdminSite.login`, `django/contrib/admin/sites.py:AdminSite.get_urls`).

The middleware reads `HttpRequest.user`, so it must come after `AuthenticationMiddleware`. `AuthConfig.ready` registers `check_middleware`, which reports `"auth.E013"` when `LoginRequiredMiddleware` or a subclass is in `MIDDLEWARE` and `AuthenticationMiddleware` is missing or comes after it ([The system checks](../commands/checks.md)) (`django/contrib/auth/checks.py:check_middleware`).
