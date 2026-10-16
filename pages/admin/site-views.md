---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The site's own pages: the index, the login and `AdminSite.each_context`

The pages of an `AdminSite` that belong to no model: the index and each application's index, the login, the logout and the password change; `AdminSite.has_permission`, which decides who gets in; and `AdminSite.each_context`, the context every page of the admin begins with.

These pages are methods of `AdminSite`, all but the login wrapped in `AdminSite.admin_view` ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](site-urls.md)), which lets in only staff; the indexes show each user what there is for them.

## Who gets in: `AdminSite.has_permission`

`AdminSite.has_permission` is true when the request's user is active and staff: in its docstring's words, permission to view *at least one* page of the site. It asks no model's permission; the model admins do, page by page ([Permissions in the admin: `has_change_permission` and the others](admin-permissions.md)) (`django/contrib/admin/sites.py:AdminSite.has_permission`). It is asked by `admin_view` on every request but the login's, by the login, and by `each_context`, whose `"has_permission"` shows the user's links in the header (`django/contrib/admin/templates/admin/base.html`).

`staff_member_required` puts the same test on a view outside the site, sending a refused request to `"admin:login"`; admindocs uses it (`django/contrib/admin/views/decorators.py:staff_member_required`). It does not call `has_permission`, so overriding that method does not change it.

## What every page is given: `AdminSite.each_context`

Every page of the admin, the model admins' included, starts its context from `AdminSite.each_context`, all but the change list's "Database error" page and the page that closes a popup (`django/contrib/admin/sites.py:AdminSite.each_context`, `django/contrib/admin/options.py:ModelAdmin.changelist_view`, `django/contrib/admin/options.py:ModelAdmin.response_add`):

| key | value | used for |
|---|---|---|
| `"site_title"` | `AdminSite.site_title`, "Django site admin" | each page's title |
| `"site_header"` | `AdminSite.site_header`, "Django administration" | each page's header |
| `"site_url"` | `AdminSite.site_url`, `"/"`; while it is `"/"`, the request's `"SCRIPT_NAME"` if not empty | the "View site" link, none for `None` |
| `"has_permission"` | `has_permission` | the user's links |
| `"available_apps"` | `AdminSite.get_app_list` | the navigation sidebar |
| `"is_popup"` | `False`; a model admin's popup pages set their own | no header or sidebar in a popup |
| `"is_nav_sidebar_enabled"` | `AdminSite.enable_nav_sidebar`, `True` | whether the sidebar is drawn |
| `"log_entries"` | `AdminSite.get_log_entries`: a queryset of the log, content types and users joined | the index's recent actions |

`"available_apps"` is built on every page, sidebar or not, asking every registered model admin for permissions; `ModelBackend` keeps them on the user object, so nora's pages sent two queries for them and piet's, a superuser's, none ([Permissions: `Permission`, groups and `has_perm`](../auth/permissions.md)). `"log_entries"` is not evaluated until the index's `get_admin_log` tag takes the user's last ten rows (`django/contrib/admin/templatetags/log.py:AdminLogNode.render`) ([The log and the history: `LogEntry` and `history_view`](log.md)). Nora's index sent five queries: the session, the user, two for permissions and the log; the application index, the first four.

## The application list: `AdminSite.get_app_list`

`AdminSite._build_app_dict` walks the registry, or one application label's models. It passes over a model whose admin's `BaseModelAdmin.has_module_permission`, by default the user's `has_module_perms` for the label, is false, and one for which `ModelAdmin.get_model_perms` holds no true permission. A model kept gets its plural verbose name, its permissions, the change list's URL when the user may view or change, with `"view_only"` true when the user may only view, and the add page's URL when the user may add, grouped under its application config's `verbose_name` (`django/contrib/admin/sites.py:AdminSite._build_app_dict`). `get_app_list` sorts applications and models by name; the documentation suggests overriding it to reorder (`django/contrib/admin/sites.py:AdminSite.get_app_list`, `docs/ref/contrib/admin/index.txt`).

```text
# a run of the example: GET /admin/ as each user
nora   Fleet: Ports (View), Ships (Change)
piet   Authentication and Authorization: Groups (Add, Change), Users (Add, Change)
       Fleet: Ports (Add, Change), Ships (Add, Change), Voyages (Add, Change)
tomas  302, Location: /admin/login/?next=/admin/
```

Nora holds no permission in auth, so its models fail `has_module_permission`; Voyage passes it and fails `get_model_perms`.

## The index and the application index

`AdminSite.index` renders `AdminSite.index_template` or `"admin/index.html"` with the list and `AdminSite.index_title`, "Site administration" (`django/contrib/admin/sites.py:AdminSite.index`). It calls `get_app_list` itself and again through `each_context`, so the list is built twice, once for a sidebar its template leaves out.

`AdminSite.app_index` does it for one label, as "Fleet administration", from `AdminSite.app_index_template`, `"admin/fleet/app_index.html"` or `"admin/app_index.html"`. An empty list raises `Http404`, so staff with no permission in an application get a 404 for it, as nora did at /admin/auth/ (`django/contrib/admin/sites.py:AdminSite.app_index`).

## The login: `AdminSite.login`

The login is the one page not wrapped in `admin_view`, being for those not yet let in. It carries `never_cache` itself, and `login_not_required` for `LoginRequiredMiddleware` ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md)). It hands the request to `LoginView`, with `AdminSite.login_form` or `AdminAuthenticationForm` and `AdminSite.login_template` or `"admin/login.html"` ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](../auth/login-views.md)) (`django/contrib/admin/sites.py:AdminSite.login`).

It first decides where a login ends: the request's `"next"` if `RedirectURLMixin.get_redirect_url` finds it safe, else the index. A `"GET"` from a user who passes `has_permission` is redirected there at once. The same URL goes into the context as `"next"`, which the form posts back in a hidden field; a `"POST"` with no `"next"` ends at `LOGIN_REDIRECT_URL`. The context also has `"app_path"`, where the form posts, and `"username"`, for telling a signed-in user shown the form that they are not authorized.

> **Changed in 6.1.** A user who passes `has_permission` and opens the login page is sent to `"next"`, no longer always to the index (`docs/releases/6.1.txt`).

`AdminAuthenticationForm` asks for "a staff account" in its message for `"invalid_login"`, and its `confirm_login_allowed`, after the parent's, refuses a user who is not staff with that message and code ([The authentication forms: `AuthenticationForm` and the password forms](../auth/user-forms.md)) (`django/contrib/admin/forms.py:AdminAuthenticationForm.confirm_login_allowed`). So tomas, with the right password, was told what a wrong one is told:

```text
# a run of the example
GET /admin/login/, no cookie                    200, the hidden "next" holding /admin/
POST /admin/login/, tomas's right password      200, "Please enter the correct username and password for a staff account. Note that both fields may be case-sensitive."
POST /admin/login/, nora's, next=/admin/        302, Location: /admin/
POST /admin/login/, nora's, no next             302, Location: /accounts/profile/
nora signed in, GET ?next=/admin/fleet/ship/    302, Location: /admin/fleet/ship/
tomas signed in, GET /admin/login/              200, "You are authenticated as tomas, but are not authorized to access this page. Would you like to login to a different account?"
```

## Logging out and changing the password

`AdminSite.logout` is a `LogoutView`, which logs out only on a `"POST"`. Its context sets `"has_permission"` false, since, its comment says, the user is not yet logged out when the context is made. Unless a safe `"next"` or `LOGOUT_REDIRECT_URL` sends the user elsewhere, it renders `AdminSite.logout_template` or `"registration/logged_out.html"`, a template the admin ships (`django/contrib/admin/sites.py:AdminSite.logout`, `django/contrib/auth/views.py:LogoutView.post`).

`AdminSite.password_change` is a `PasswordChangeView` with `AdminSite.password_change_form` or `django/contrib/admin/forms.py:AdminPasswordChangeForm`, a `PasswordChangeForm` with a CSS class for required fields, ending at `AdminSite.password_change_done`, a `PasswordChangeDoneView`; the admin ships both templates. The session that made the change stays signed in ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md)) (`django/contrib/admin/sites.py:AdminSite.password_change`).

> **Changed in 6.0.** `AdminSite.password_change_form` (`docs/releases/6.0.txt`).

## The JavaScript catalogue and "View on site"

`AdminSite.i18n_javascript` is a `JavaScriptCatalog` of the admin package's translations ([The language views: `set_language` and `JavaScriptCatalog`](../i18n/views.md)) (`django/contrib/admin/sites.py:AdminSite.i18n_javascript`).

A change form's "View on site" link comes from `BaseModelAdmin.get_view_on_site_url`: none when `BaseModelAdmin.view_on_site` is false, a callable's URL, or, for an object with `get_absolute_url`, the site's `"view_on_site"` URL (`django/contrib/admin/options.py:BaseModelAdmin.get_view_on_site_url`). `AdminSite.shortcut_view` raises `PermissionDenied` when the content type's model is registered and its model admin's `has_view_permission` is false, before any object is looked for; else it calls the content types' `shortcut` ([Sites: `Site`, `get_current_site` and the `shortcut` view](../contrib/sites.md)) (`django/contrib/admin/sites.py:AdminSite.shortcut_view`). Nora got 403 for a voyage that exists and one that does not; piet got 404 for both, from `shortcut`.

> **Changed in 6.2.** Staff without the view or change permission now consistently get the 403 (`docs/releases/6.2.txt`).
