---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`

`AdminSite.get_urls` makes an admin site's URL patterns from its registry, and `AdminSite.urls` gives them to a URLconf under the namespace `"admin"`. `AdminSite.admin_view` wraps every view but the login: only staff get through, under the CSRF check, and uncached unless the view is wrapped as cacheable. A catch-all sends a stranger to log in whatever the path, and `quote` puts a primary key into a path.

The admin's URLs depend on which models a project registers, so they are made from the registry. Its templates must reverse them by fixed names wherever the site is mounted and however many there are, and they must not tell a stranger which models are registered.

## The patterns: `AdminSite.get_urls`

`AdminSite.get_urls` makes the patterns in four groups, in an order that matters, as the resolver tries them in turn (`django/contrib/admin/sites.py:AdminSite.get_urls`): the site's own pages; for each model in the registry, in the order of registration, its application label and model name with the model admin's patterns included under them; one pattern for the applications' indexes, a regular expression of the labels that have a registered model, left out when there are none; and last, a pattern that matches any path. For the harbour office's default site:

```text
the patterns of admin.site, and their names
""                                          index
login/                                      login
logout/                                     logout
password_change/                            password_change
password_change/done/                       password_change_done
autocomplete/                               autocomplete
jsi18n/                                     jsi18n
r/<path:content_type_id>/<path:object_id>/  view_on_site
auth/group/                                 include(GroupAdmin.urls)
auth/user/                                  include(UserAdmin.urls)
fleet/port/                                 include(PortAdmin.urls)
fleet/ship/                                 include(ShipAdmin.urls)
fleet/voyage/                               include(ModelAdmin.urls)
^(?P<app_label>auth|fleet)/$                app_list
(?P<url>.*)$                                (no name)
```

The list is made when the URLconf reads `AdminSite.urls`, from the registry as it is then, and the resolver keeps it: a model registered after the URLconf was imported answered staff with 404 until the URLconf was built again. The admin modules that register are imported as Django starts ([Registering models: `AdminSite.register` and `ModelAdmin`](registration.md)).

## `AdminSite.urls` and the namespace

`AdminSite.urls` returns a triple: the patterns, the application namespace `"admin"`, and the site's `name` as the instance namespace (`django/contrib/admin/sites.py:AdminSite.urls`). That is the shape `include` returns, which `path` takes in place of a view (`django/urls/conf.py:_path`); `include` itself refuses a triple with `ImproperlyConfigured`. A model admin's patterns are included as a plain list, so their names stand directly in the site's namespace, as `"admin:fleet_ship_change"`. The default site's name, `"admin"`, is also the application namespace, making it the default instance among several ([Namespaces](../urls/namespaces.md)).

## A model admin's patterns: `ModelAdmin.get_urls`

`ModelAdmin.get_urls` gives five views, named from the model's application label and model name by strings such as `"%s_%s_changelist"`: `ModelAdmin.changelist_view` at the empty path, `ModelAdmin.add_view` at add/, and `ModelAdmin.history_view`, `ModelAdmin.delete_view` and `ModelAdmin.change_view` at the object's key followed by history/, delete/ and change/ (`django/contrib/admin/options.py:ModelAdmin.get_urls`). The key is matched by the converter path, which takes slashes, and a sixth pattern, the key alone, which would match every path before it but the empty one, comes last. It is a `RedirectView` to the change page, kept, its comment says, because it was the change page's address before Django 1.9; it answers 302 and drops the query string. `ModelAdmin.urls` calls `get_urls`.

## The wrappers

`AdminSite.get_urls` and `ModelAdmin.get_urls` each have a local function, wrap, that every view in their patterns but the login goes through. The URLconf holds what it returns: a function that, at each call, passes the view through `AdminSite.admin_view` and calls the result. It carries the view's attributes, copied, and marks of its own: the site's sets `"admin_site"`, and `"login_url"`, the login page reversed lazily in the site's namespace; the model admin's sets only `"model_admin"` (`django/contrib/admin/sites.py:AdminSite.get_urls`, `django/contrib/admin/options.py:ModelAdmin.get_urls`).

`"login_url"` is for `LoginRequiredMiddleware`, which sends a stranger to the view's login URL, or to `LOGIN_URL` when the view has none ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md)) (`django/contrib/auth/middleware.py:LoginRequiredMiddleware.get_login_url`). So under that middleware a model admin's pages send a stranger to `LOGIN_URL`:

```text
a stranger, with LoginRequiredMiddleware added to the settings
GET  /admin/              302  /admin/login/?next=/admin/
GET  /admin/fleet/ship/   302  /accounts/login/?next=/admin/fleet/ship/
```

## `AdminSite.admin_view`

`AdminSite.admin_view` returns a function that first asks `AdminSite.has_permission`, true for a user who is active and staff ([The site's own pages: the index, the login and `AdminSite.each_context`](site-views.md)) (`django/contrib/admin/sites.py:AdminSite.admin_view`). Anyone else gets `redirect_to_login`, to the site's login page with the path asked for in `"next"`; but a request for the site's logout page is redirected to the index, which then sends the user to log in with the index as `"next"`.

Unless the view was passed with `cacheable=True`, `never_cache` goes around that function; unless the view is marked by `csrf_exempt`, `csrf_protect` does too, added here, a comment says, so that any view can be wrapped without repeating it ([View decorators](../views/decorators.md)). The result takes the view's name and attributes. The site wraps three views as cacheable, the password change, its done page and the JavaScript catalogue, and a model admin none: nora's index came with headers forbidding caching, the password change page without them.

## The catch-all: `AdminSite.catch_all_view`

The last pattern matches whatever nothing before it did, and is wrapped like the rest, so a stranger asking for any path under the site is sent to log in before the path is looked at. The documentation warns against dropping it with `AdminSite.final_catch_all_view`, as it "protects against a potential model enumeration privacy issue" (`docs/ref/contrib/admin/index.txt`): without it, a stranger would get 404 for an unregistered model and the login redirect for a registered one.

Staff reach `AdminSite.catch_all_view`, which does the work of `APPEND_SLASH` (`django/contrib/admin/sites.py:AdminSite.catch_all_view`). `CommonMiddleware` cannot: it adds a slash only to a path that does not resolve, and under the site every path resolves, to the catch-all (`django/middleware/common.py:CommonMiddleware.should_redirect_with_slash`). With `APPEND_SLASH` true and no final slash, the view resolves the path with one, and if that finds a view not marked by `no_append_slash`, redirects there permanently, keeping the query string; otherwise it raises `Http404`. `catch_all_view` is itself so marked, so a path whose slashed form reaches only the catch-all gets 404.

```text
the catch-all, for a stranger and for nora
stranger  GET  /admin/nothing/here/      302  /admin/login/?next=/admin/nothing/here/
nora      GET  /admin/nothing/here/      404
nora      GET  /admin/fleet/ship?q=end   301  /admin/fleet/ship/?q=end
nora      GET  /admin/nothing            404
```

## Keys in paths: `quote` and `unquote`

A primary key may hold characters that mean something in a path. The admin writes a key into a URL with `quote` and reads it with `unquote` (`django/contrib/admin/utils.py:quote`, `django/contrib/admin/utils.py:unquote`). `quote` replaces each of `'":/_#?;@&=+$,[]<>%'`, the newline and the backslash with an underscore and the character's code in two hexadecimal digits, and returns a key that is not a string unchanged; the underscore is among them, so a key's own `"_2F"` comes back from `unquote` as it was. Its docstring says it differs from percent-encoding so that the browser does not undo it. Templates quote with the filter `admin_urlquote` (`django/contrib/admin/templatetags/admin_urls.py:admin_urlquote`); the views unquote the key from the path. With the office's manifests, keyed by serial number, registered:

```text
a manifest whose key is "M/26_7", as piet
quote('M/26_7')  ->  'M_2F26_5F7'
GET /admin/office/manifest/M_2F26_5F7/change/   200  "Change manifest"
```

## `"current_app"`, and two sites

The admin's templates link with `{% url %}` and names in the namespace `"admin"`, leaving the instance to the current application. The admin's views set the request's `"current_app"` to the site's name before rendering most of their pages, and `URLNode.render` passes it to `reverse` ([Namespaces](../urls/namespaces.md#where-the-current-application-comes-from)) (`django/template/defaulttags.py:URLNode.render`); where the admin reverses in Python, it passes the site's name itself, except in `LogEntry.get_admin_url`, which passes none (`django/contrib/admin/models.py:LogEntry.get_admin_url`).

So a project can mount a second site. `AdminSite(name="office")` has its own registry, and so its own model admins, patterns, login page and instance namespace. With Ship alone registered on it, at office/:

```text
a second site, AdminSite(name="office"), with Ship
reverse("admin:fleet_ship_change", args=(1,))                        ->  /admin/fleet/ship/1/change/
reverse("admin:fleet_ship_change", args=(1,), current_app="office")  ->  /office/fleet/ship/1/change/
stranger  GET  /office/fleet/ship/   302  /office/login/?next=/office/fleet/ship/
```
