---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`

The views of `django.contrib.auth.views` that `django.contrib.auth.urls` routes for signing in, signing out and changing a password, and `RedirectURLMixin`, which decides where a visitor goes next without letting the client send them off the site.

These views do little themselves. `LoginView` and `PasswordChangeView` are `FormView`s, which show a form for a `"GET"` and act and redirect on a `"POST"` that passes ([The form views](../views/editing.md)); `LogoutView` and `PasswordChangeDoneView` are `TemplateView`s. The forms check ([The authentication forms: `AuthenticationForm` and the password forms](user-forms.md)), and `login`, `logout` and `update_session_auth_hash` change the session ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)). The views own the redirect at the end, the decorators, and what their templates are given.

## The views and their URLs

| view | path and name | decorators |
|---|---|---|
| `LoginView` | login/, `"login"` | `login_not_required`, `sensitive_post_parameters`, `csrf_protect`, `never_cache` |
| `LogoutView` | logout/, `"logout"` | `csrf_protect`, `never_cache` |
| `PasswordChangeView` | password_change/, `"password_change"` | `sensitive_post_parameters`, `csrf_protect`, `login_required` |
| `PasswordChangeDoneView` | password_change/done/, `"password_change_done"` | `login_required` |

*The views of `django.contrib.auth.urls` but the password reset's ([Password reset: `PasswordResetTokenGenerator` and the reset views](password-reset.md)). The harbour office includes it under accounts/, where `LOGIN_URL`'s default, `"/accounts/login/"`, finds the login page.*

`method_decorator` puts the decorators on the class's `dispatch`, called in the order listed ([Decorating a class: `method_decorator`](../views/method-decorator.md)) (`django/contrib/auth/urls.py`, `django/contrib/auth/views.py:LoginView`, `django/utils/decorators.py:_multi_decorate`). `sensitive_post_parameters`, given no names, marks every posted value as sensitive, which the error report hides while `settings.DEBUG` is `False` (`django/views/debug.py:SafeExceptionReporterFilter.get_post_parameters`). `login_not_required` only marks the view, for `LoginRequiredMiddleware`, which lets a visitor not signed in reach the login page and no other of these four ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](requiring-login.md)).

No application of Django's ships the login view's template, `"registration/login.html"`; the documentation leaves it to the project (`docs/topics/auth/default.txt`).

## Where the visitor goes next: `RedirectURLMixin`

`login_required` sends a visitor to the login page with the page asked for in `"next"`, to return to after the login. But anyone can link to the real login page with a `"next"` of their own site, and a view that obeyed would carry a visitor who had just signed in off to it.

`RedirectURLMixin.get_redirect_url` reads the field `RedirectURLMixin.redirect_field_name` names (`REDIRECT_FIELD_NAME`, `"next"`) from the posted data or else the query string, and passes it to `url_has_allowed_host_and_scheme`. A host, if the URL names one, must be the request's own (`HttpRequest.get_host`) or one of `RedirectURLMixin.success_url_allowed_hosts`, empty unless a subclass or `View.as_view` fills it; over HTTPS the only scheme allowed is `"https"`, and a URL beginning with two slashes counts as `"http"`. A URL that fails gives an empty string, as no `"next"` does (`django/contrib/auth/views.py:RedirectURLMixin.get_redirect_url`). The check is told in [The helpers in `django/utils/http.py`](../http/helpers.md).

`RedirectURLMixin.get_success_url` returns that URL, or the default when it is empty. The mixin's default is `RedirectURLMixin.next_page` through `resolve_url`, a path or a URL pattern's name, and with no `next_page` it raises `ImproperlyConfigured`; `LoginView` and `LogoutView` replace it with their own (`django/contrib/auth/views.py:RedirectURLMixin.get_default_redirect_url`).

```text
# a run of the example: nora's username and password posted from a new browser each time
to /accounts/login/, with next=/ships/1/edit/ posted               ->  302, Location: /ships/1/edit/
to /accounts/login/, with next=https://evil.example/ships/ posted  ->  302, Location: /berths/
```

## `LoginView`

On a `"GET"`, `LoginView` renders `"registration/login.html"`, adding three entries to the form view's context (`django/contrib/auth/views.py:LoginView.get_context_data`). `"next"` holds what `get_redirect_url` returns, so a hidden field copying it passes on only a safe URL; for a `"next"` of https://evil.example/ the run rendered it empty. `"site"` and `"site_name"` come from `get_current_site`: the sites application's current site when it is installed ([Sites: `Site`, `get_current_site` and the `shortcut` view](../contrib/sites.md)), and otherwise, as here, a `RequestSite` named after the request's host, harbour.example (`django/contrib/sites/shortcuts.py:get_current_site`).

On a `"POST"`, the form is `LoginView.authentication_form` if the view was given one, else `LoginView.form_class`, `AuthenticationForm` (`django/contrib/auth/views.py:LoginView.get_form_class`); `LoginView.get_form_kwargs` adds the request, which the form passes to `authenticate` and so to each authentication backend ([Authenticating: `authenticate` and the backends](authenticating.md)). A failed form comes back with status 200. A valid one reaches `LoginView.form_valid`, which calls `login` with the form's user and redirects to `get_success_url` (`django/contrib/auth/views.py:LoginView.form_valid`). Without a safe `"next"` that is `next_page`, else `LOGIN_REDIRECT_URL`, `"/accounts/profile/"` unless the settings say otherwise, a page Django does not provide (`django/contrib/auth/views.py:LoginView.get_default_redirect_url`).

A visitor already signed in who opens the login page is shown the form, unless `LoginView.redirect_authenticated_user` is true. Then `LoginView.dispatch` sends them to `get_success_url` as if the login had just succeeded, and raises `ValueError` if that URL is the request's own path, a redirect to itself (`django/contrib/auth/views.py:LoginView.dispatch`).

```python
# harbour/urls.py, added to urlpatterns
path("signin/", LoginView.as_view(redirect_authenticated_user=True), name="signin"),
```

```text
# a run of the example: nora signed in
GET /signin/                      ->  302, Location: /berths/
GET /signin/?next=/ships/1/edit/  ->  302, Location: /ships/1/edit/
GET /signin/?next=/signin/        ->  raises ValueError: Redirection loop for authenticated user detected. Check that your LOGIN_REDIRECT_URL doesn't point to a login page.
```

The check catches only a loop of one page; the documentation warns of a longer one, through `permission_required` without `raise_exception=True` (`docs/topics/auth/default.txt`).

## `LogoutView` and `logout_then_login`

`LogoutView.http_method_names` is `["post", "options"]`: `View.dispatch` hands any other method to `View.http_method_not_allowed`, a 405 whose `"Allow"` names the two (`django/views/generic/base.py:View.http_method_not_allowed`). A logout is a form that posts, and `csrf_protect` checks a `"POST"`, where it never checks a `"GET"`.

> **Changed in 5.0.** `LogoutView` and `logout_then_login` no longer log out on a `"GET"` (`docs/releases/5.0.txt`).

`LogoutView.post` logs out first, then finds the target: a safe `"next"`, else `next_page`, else `LOGOUT_REDIRECT_URL` (`None` by default), else the request's own path. A target other than the request's full path is redirected to; when it is that path, the view answers the `"POST"` by rendering `"registration/logged_out.html"` (`django/contrib/auth/views.py:LogoutView.post`, `django/contrib/auth/views.py:LogoutView.get_default_redirect_url`).

```text
# a run of the example: nora signed in before each request
GET /accounts/logout/                                      ->  405, Allow: POST, OPTIONS
POST /accounts/logout/                                     ->  200, "Signed out."
POST /accounts/logout/, with next=/accounts/login/ posted  ->  302, Location: /accounts/login/
POST /accounts/logout/?page=2                              ->  302, Location: /accounts/logout/
```

> **Trap.** The full path includes the query string; the default target does not. With no target named, a logout form posting to a URL with a query string is redirected to the logout URL, which the browser asks for by `"GET"`: a 405.

`logout_then_login` is a function that calls a `LogoutView` whose `next_page` is the URL it is given, or `LOGIN_URL`; so it logs out only on a `"POST"`, and a safe `"next"` still wins (`django/contrib/auth/views.py:logout_then_login`).

## `PasswordChangeView`

`PasswordChangeView` requires a signed-in user and gives `PasswordChangeForm` the request's user; the form checks the old password and validates the new.

`PasswordChangeView.form_valid` saves the form, which sets and saves the new password. That alone would end this browser's session with the user's others: when a request first asks for its user, `django.contrib.auth.get_user` compares the hash kept in the session with one made from the password now. So the view calls `update_session_auth_hash`, which gives the session a new key and the new hash so that, as its docstring says, the change does not log out the session it came from; then it redirects to `PasswordChangeDoneView` (`django/contrib/auth/views.py:PasswordChangeView.form_valid`, `django/contrib/auth/__init__.py:update_session_auth_hash`). In the run, nora changed their password in one of two signed-in browsers: that one got a new session key and stayed signed in; the other was sent to the login page at its next request.

`PasswordContextMixin` gives the templates of both views, and of the reset views, `"title"` from the view's title, a `"subtitle"` of `None`, and the extra context; the admin's templates show the title, and a subtitle when one is set, and the admin's password change is these views ([The site's own pages: the index, the login and `AdminSite.each_context`](../admin/site-views.md)) (`django/contrib/auth/views.py:PasswordContextMixin.get_context_data`, `django/contrib/admin/templates/admin/base.html`, `django/contrib/admin/sites.py:AdminSite.password_change`).
