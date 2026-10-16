---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Sites: `Site`, `get_current_site` and the `shortcut` view

How `django.contrib.sites` decides which `Site` a request is on: `SiteManager.get_current`, the cache `SITE_CACHE`, `get_current_site` and `RequestSite`, `CurrentSiteManager` and `CurrentSiteMiddleware`, the first site `create_default_site` makes, and the content types' `shortcut` view, which redirects to an object's page, on the domain of one of its sites where it has any.

Code that writes an absolute URL needs a domain, and the request in hand may not carry the right one: a password-reset mail must name the site's domain, and an object reached through one domain may belong to another. The sites application keeps domains as rows of `Site` and says which row is current. With `SITE_ID` a process serves one site, and the documentation's way to serve several is a settings module for each (`docs/ref/contrib/sites.txt`); without it, the request's host picks the row.

## The row: `Site`

`Site.domain` is unique, up to 100 characters, and its validator refuses one that holds whitespace ("The domain name cannot contain any spaces or tabs."); `Site.name` is the display name. The table is `"django_site"`, the default order is by domain, and a site prints as its domain. `Site.natural_key` is the domain, which `SiteManager.get_by_natural_key` matches exactly (`django/contrib/sites/models.py:Site`).

## Which site is current: `SiteManager.get_current`

When `SITE_ID` is anything true, `SiteManager.get_current` returns the row with that key and ignores any request; `None` counts as unset. Otherwise it looks for a site whose domain matches, ignoring case, the host as `HttpRequest.get_host` returns it, port and capitals included ([Headers, host and scheme](../http/headers.md)). Failing that, it looks again for the domain `split_domain_port` makes of it, lowercased and without port or trailing dot; a second miss raises `Model.DoesNotExist`. With no `SITE_ID` and no request it raises `ImproperlyConfigured` (`django/contrib/sites/models.py:SiteManager.get_current`, `django/contrib/sites/models.py:SiteManager._get_site_by_request`).

```text
# a script on the harbour office's site
SITE_ID = 1
get_current()                                       harbour.example    1 query
get_current(request), Host piraeus.harbour.example  harbour.example    0 queries
SITE_ID removed, the cache cleared
Host harbour.example:8000    harbour.example    2 queries: domain LIKE 'harbour.example:8000', then 'harbour.example'
Host harbour.example:8000    harbour.example    1 query: LIKE 'harbour.example:8000' again
Host testserver              DoesNotExist: Site matching query does not exist.
```

## The cache: `SITE_CACHE`

Every row `get_current` reads goes into `SITE_CACHE`, a dictionary of the module, under the key it was looked up by: the `SITE_ID`, the host as sent, or the domain without its port. A miss is not kept, so a host with a port, where the table holds the domain alone, costs a query at every call (`django/contrib/sites/models.py:SiteManager._get_site_by_request`).

On a site's `pre_save` and `pre_delete`, `clear_site_cache`, connected when the models module is imported, removes two entries: the one under the site's key, and the one under the domain the database holds for it, read with a query first (`django/contrib/sites/models.py:clear_site_cache`). A save in another process clears nothing here, and an entry under another spelling stays:

```text
# a script on the harbour office's site, SITE_ID removed
keys after Host harbour.example, Host Harbour.Example    ['harbour.example', 'Harbour.Example']
after the name is saved as "Valletta harbour office"     ['Harbour.Example']
Host harbour.example    'Valletta harbour office'    1 query
Host Harbour.Example    'Harbour office'             0 queries
```

`SiteManager.clear_cache` binds the module's name to a new dictionary; one imported earlier keeps its entries (`django/contrib/sites/models.py:SiteManager.clear_cache`).

## `get_current_site` and `RequestSite`

`get_current_site` is what other applications call: the manager's `get_current` for the request when the sites application is installed, a `RequestSite` otherwise. Its comment says why it imports the model inside the function: not to import `Site` when the application is not installed, where defining the model raises `RuntimeError` (`django/db/models/base.py:ModelBase.__new__`). So modules that work either way, like the content types' views, import `get_current_site` at their top (`django/contrib/sites/shortcuts.py:get_current_site`). A `RequestSite` has a domain and a name, both the host as sent, and no key; its `save` and `delete` raise `NotImplementedError` (`django/contrib/sites/requests.py:RequestSite`).

Flat pages and redirects are looked up by the current site, and the redirect middleware refuses to start without the sites application ([Flat pages and redirects: the fallback middleware](flatpages-and-redirects.md)). The sitemap views write their URLs with its domain ([Sitemaps: `Sitemap` and the sitemap views](sitemaps.md)); a feed puts it before each link that lacks one ([Feeds: `django.contrib.syndication` and the feed generator](feeds.md)); `PasswordResetForm.save`, unless given a domain to use instead, writes its domain and name into the mail ([Password reset: `PasswordResetTokenGenerator` and the reset views](../auth/password-reset.md)).

## Filtering by site: `CurrentSiteManager` and `CurrentSiteMiddleware`

`CurrentSiteManager` is a manager for a model whose rows belong to sites. Its queryset keeps the rows whose site field holds the key `SITE_ID` names: the field named when the manager is made, or else the model's field "site" if it has one, and "sites" if not. A manager has no request, so it reads the setting alone, and without `SITE_ID` asking it for a queryset raises `AttributeError` (`django/contrib/sites/managers.py:CurrentSiteManager.get_queryset`). Added to the bulletin model, it gave three bulletins under `SITE_ID = 1` and only "Customs hours" under `SITE_ID = 2`.

Its system check reports `"sites.E001"` when the model has no field of the name and `"sites.E002"` when the field is neither a foreign key nor a many-to-many field. It does not ask where the field leads: given the bulletin's port, a foreign key to ports, it passed, and would filter by a port's key (`django/contrib/sites/managers.py:CurrentSiteManager._check_field_name`).

`CurrentSiteMiddleware` sets `HttpRequest.site` on every request to what `get_current_site` returns (`django/contrib/sites/middleware.py:CurrentSiteMiddleware.process_request`).

> **Changed in 6.2.** `CurrentSiteMiddleware` sets `async_capable = False`, so under ASGI it runs in a thread, which the release notes say avoids repeated context switches in `MiddlewareMixin.__acall__` ([Sync and async in one chain](../handlers/async.md)).

```runtime-names
HttpRequest.site    django/contrib/sites/middleware.py:CurrentSiteMiddleware.process_request    # set on each request by CurrentSiteMiddleware: the current site
```

## The first site: `create_default_site`

`SitesConfig.ready` connects `create_default_site` to `post_migrate`, with the sites application's config as sender, and registers `check_site_id` under the tag `"sites"` (`django/contrib/sites/apps.py:SitesConfig.ready`). migrate sends `post_migrate` as it ends, and flush after emptying the tables ([The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md)). The receiver takes `Site` from the registry it is given and returns if the model is absent or the router keeps it off the database. If the table is empty, it saves example.com, named example.com, under the key `SITE_ID` names (1 without the setting, the database's next with `None`); then it runs the statements `BaseDatabaseOperations.sequence_reset_sql` gives for `Site` on that backend (`django/contrib/sites/management.py:create_default_site`): none on SQLite, and for PostgreSQL, with no server behind it:

```text
SELECT setval(pg_get_serial_sequence('"django_site"','id'), coalesce(max("id"), 1), max("id") IS NOT null) FROM "django_site";
```

> **Why.** The comment at the explicit key: some tests of Django's own suite rely on the key 1, which a sequence reused after a flush need not give (tickets 15573, 16353 and 15346), and a key set by hand needs the sequence reset (17415). Its claim that the default settings set `SITE_ID` to 1 does not hold: `django/conf/global_settings.py` sets none, and nor does the project template.

`check_site_id` passes the setting through the key field's `to_python` and reports `"sites.E101"` when that fails or changes the value: "The SITE_ID setting must be of type int." for "1" (`django/contrib/sites/checks.py:check_site_id`). `None` passes, and lets the host decide.

## The `shortcut` view

`shortcut` turns a content type's key and an object's key into a redirect to the object's page. The admin's "View on site" link goes through it, after a permission check, unless `BaseModelAdmin.view_on_site` is a callable ([The site's own pages: the index, the login and `AdminSite.each_context`](../admin/site-views.md)), and the harbour office serves it at r/ (`django/contrib/contenttypes/views.py:shortcut`).

First the path. A content type whose `ContentType.model_class` is `None` is a 404, "Content type 26 object has no associated model". The object is read by `ContentType.get_object_for_this_type`, through the model's base manager ([Content types: `ContentType` and its cache](content-types.md)); a content type or object that does not exist, or a key its field cannot take, is a 404, "Content type 20 object abc doesn’t exist"; an object without `get_absolute_url` is a 404 naming the content type, "ship objects don’t have a get_absolute_url() method". A URL that begins with "http://", "https://" or "//" is redirected to as it is.

Then the domain, which starts as the current site's, or none if `get_current_site` raised `ObjectDoesNotExist`. With the sites application installed, the object's many-to-many fields to `Site` come first: if the current domain is among the object's sites it stays, and if not, the first of them replaces it. The comment there calls that choice arbitrary; `QuerySet.first` keeps the queryset's ordering, and `Site`'s is by domain. Only when no such field holds a site are the foreign keys to `Site` read, and the first that holds one gives its domain, current or not. The redirect is a 302 to the request's scheme, the domain and the path, or to the path alone with no domain. Bulletin 3 is on harbour.example and piraeus.harbour.example, bulletin 1 on harbour.example; content types 20 and 21 are the bulletin and lighthouse models:

```text
# a script on the harbour office's site
SITE_ID removed, Host piraeus.harbour.example
/r/20/3/            302  http://piraeus.harbour.example/bulletins/3/    one of its sites
/r/20/1/, secure    302  https://harbour.example/bulletins/1/           its only site
/r/21/1/            302  http://piraeus.harbour.example/lighthouses/1/  no site of its own
SITE_ID removed, Host testserver, which no site has
/r/21/1/            302  /lighthouses/1/
SITE_ID = 1, a bulletin on piraeus.harbour.example and gozo.harbour.example
/r/20/4/            302  http://gozo.harbour.example/bulletins/4/
```
