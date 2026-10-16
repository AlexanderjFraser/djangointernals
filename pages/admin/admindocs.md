---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The documentation generator: `django.contrib.admindocs`

`django.contrib.admindocs` adds pages under the admin that describe a project as it runs: the tags and filters of its template engine, the views of its URLconf, its models and where its templates are looked for, with docstrings rendered from reStructuredText by docutils. Its `XViewMiddleware` tells a staff user's browser which view made a page.

The documentation gives its purpose: to make the docstrings of the installed applications' models, views, tags and filters readable from the admin (`docs/ref/contrib/admin/admindocs.txt`). A project installs it and includes `django.contrib.admindocs.urls`, by the documentation's advice at admin/doc/ and before the admin's entry, whose patterns would otherwise take those paths. The admin's base template reverses `"django-admindocs-docroot"` with `{% url … as docsroot %}`, which leaves the variable empty when the name does not exist, and shows active staff a link "Documentation" when it does (`django/contrib/admin/templates/admin/base.html`).

## The pages and `BaseAdminDocsView`

The URLconf `django.contrib.admindocs.urls` has no application namespace (`django/contrib/admindocs/urls.py`). Its index, `"django-admindocs-docroot"`, is `BaseAdminDocsView` itself rendering `"admin_doc/index.html"`. Under it are tags/, filters/, views/ and models/, the last two with a page for each view and model, templates/ and a template's name, and bookmarklets/.

Every page is a `TemplateView` built on `BaseAdminDocsView`, with a template that extends `"admin/base_site.html"`. `BaseAdminDocsView.dispatch` is wrapped in `staff_member_required`, which lets in a user who is active and staff and sends anyone else to the URL named `"admin:login"`; no model's permission is asked here. Then it reads `docutils_is_available`, set as `django/contrib/admindocs/utils.py` is imported by trying to import docutils: without docutils, every page renders `"admin_doc/missing_docutils.html"` in place of its own. `BaseAdminDocsView.get_context_data` adds the default site's `AdminSite.each_context`, for the admin's titles and navigation (`django/contrib/admindocs/views.py:BaseAdminDocsView`, `django/contrib/admin/views/decorators.py:staff_member_required`). With its URLs at admin/doc/ and no docutils:

```text
# admin/doc/ without docutils: the status, and the page's title
nobody GET /admin/doc/                    302 to /admin/login/?next=/admin/doc/
tomas  GET /admin/doc/                    302 to /admin/login/?next=/admin/doc/
nora   GET /admin/doc/                    200 "Please install docutils"
nora   GET /admin/doc/models/fleet.ship/  200 "Please install docutils"
```

## What each page reads

Each of admindocs' pages but the index and the bookmarklets walks, when it is asked for, what Django has already built: the template engine, the URL resolver or the app registry.

`TemplateTagIndexView` and `TemplateFilterIndexView` read one engine, `Engine.get_default`, the first `DjangoTemplates` backend ([Template engines: `TEMPLATES` and the backends](../templates/engines.md)); with none they list nothing, and the comment cites ticket 24125: a `TEMPLATES` setting that is not trivial is not supported. They take `Engine.template_builtins`, then `Engine.template_libraries` sorted by name ([Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md)), and parse the docstring of each function in a library's `Library.tags` or `Library.filters` (`django/contrib/admindocs/views.py:TemplateTagIndexView.get_context_data`).

`ViewIndexView` flattens the URLconf in force for the request with `extract_views_from_urlpatterns` and writes each address with `simplify_regex` ([The URL checks, and listing the patterns](../urls/checks.md)). It reads no docstring, and names each view by `get_view_name`: a view made by `View.as_view` by its class, any other callable by its module and qualified name, or its class's name when it has none (`django/contrib/admindocs/utils.py:get_view_name`). Three of its rows for the harbour office, the view called by hand as piet:

```text
# ViewIndexView.get_context_data: address, view, namespace and name
/admin/                django.contrib.admin.sites.AdminSite.index               admin:index
/admin/auth/user/add/  django.contrib.auth.admin.UserAdmin.add_view             admin:auth_user_add
/admin/fleet/ship/     django.contrib.admin.options.ModelAdmin.changelist_view  admin:fleet_ship_changelist
```

A model admin's view is a wrapper that takes the names of the bound method it wraps, and so is named by the class that defines the method: here every change list is `ModelAdmin.changelist_view`, while the user's add page is `UserAdmin.add_view`, an override (`django/contrib/admin/options.py:ModelAdmin.get_urls`). `ViewDetailView` accepts a view's name from the URL only if it is the `URLPattern.lookup_str` of some pattern; any other is a 404, and nothing is imported for it (`django/urls/resolvers.py:URLResolver._is_callback`, `django/contrib/admindocs/views.py:ViewDetailView._get_view_func`).

`ModelIndexView` lists each model of `Apps.get_models`, registered with the admin or not, that `user_has_model_view_permission` allows: it asks the user's `has_perm` for the model's view or change permission, as `BaseModelAdmin.has_view_permission` does by default, and asks no model admin. `ModelDetailView` answers 404 for an unknown application or model, and raises `PermissionDenied` without the permission (`django/contrib/admindocs/views.py:user_has_model_view_permission`). Called by hand, the index listed Port and Ship for nora and all of them for piet, Sailor, which no site registers, among them; Voyage's page refused nora.

A model's page is built from `_meta` (`django/contrib/admindocs/views.py:ModelDetailView.get_context_data`). A foreign key, one-to-one fields among them, is typed by the related model's class name and described in reStructuredText that links to that model's page; any other field, by its class's description filled in with its attributes. Each many-to-many field and reverse relation gives two rows, `".all"` and `".count"` after its accessor. The methods are the functions, properties and cached properties in the model class's own `__dict__`, less names beginning with a prefix of `MODEL_METHODS_EXCLUDE`: a property, a `cached_property` or a method that takes only `self` is shown as a field, typed by `get_return_data_type` from its name, and any other under "Methods with arguments" ([Asking a callable what it accepts: `django/utils/inspect.py`](../utils/inspect.md)). Ship's rows for nora, sorted by name as the page's template sorts them, with `parse_rst` replaced by a function that returns its text and the sailors' reverse relation left out:

```text
# ModelDetailView.get_context_data for fleet.Ship
captain           Sailor                the related `crew.Sailor` object
home              Port                  the related `fleet.Port` object
id                Big (8 byte) integer  ID
name              String (up to 60)     name
tonnage           Positive integer      tonnage
voyage_set.all    List                  all related `fleet.Voyage` objects
voyage_set.count  Integer               number of related `fleet.Voyage` objects
```

`TemplateDetailView` does not ask the engine for the template. It takes the default engine's `Engine.dirs`, then the directories of each loader that has a `get_dirs` method, each once, joins the template's name onto each with `safe_join`, and says whether each file exists (`django/contrib/admindocs/views.py:TemplateDetailView.get_context_data`).

## Docstrings: `parse_docstring` and `parse_rst`

`parse_docstring` needs no docutils. It splits a docstring at blank lines: the first part is the title; the last, if it parses as email headers (`"Context: port, berths"`), is the metadata, of which a view's page shows `"Context"` and `"Templates"`; the rest is the body (`django/contrib/admindocs/utils.py:parse_docstring`).

`parse_rst` renders each part with docutils' HTML writer and returns the fragment marked safe. It wraps the text in directives that make `"cmsreference"` the default role, so that text in single backquotes links in the context the caller names, `"model"`, `"view"`, `"tag"` or `"filter"`; it bases the roles' links on the reversed `"django-admindocs-docroot"`, and turns off raw HTML and the inclusion of files (`django/contrib/admindocs/utils.py:parse_rst`). The roles are registered with docutils as the module is imported, if docutils is there: `default_reference_role` as `"cmsreference"`, and one for each entry of `ROLES` by `create_reference_role`, which lowercases a target but a view's or a template's, names the comment says are case-sensitive (`django/contrib/admindocs/utils.py:create_reference_role`).

## `XViewMiddleware` and the bookmarklet

`XViewMiddleware` has one hook, `XViewMiddleware.process_view`. It raises `ImproperlyConfigured` when the request has no user, which `AuthenticationMiddleware` sets. For a `"HEAD"` request from an address in `INTERNAL_IPS`, or from a user who is active and staff, it returns an empty response with the header X-View, the view's name by `get_view_name`, and the view is never called ([The centre of the chain](../handlers/view.md)); any other request passes (`django/contrib/admindocs/middleware.py:XViewMiddleware.process_view`). Added after the office's four middleware:

```text
# XViewMiddleware, a request for /admin/fleet/ship/
nora   HEAD /admin/fleet/ship/  200, X-View: django.contrib.admin.options.ModelAdmin.changelist_view
nora   GET  /admin/fleet/ship/  200
tomas  HEAD /admin/fleet/ship/  302 to /admin/login/?next=/admin/fleet/ship/
nobody HEAD /admin/fleet/ship/  200, INTERNAL_IPS ['127.0.0.1'], X-View: django.contrib.admin.options.ModelAdmin.changelist_view
```

The bookmarklets page's link of JavaScript sends a `"HEAD"` request for the page the browser is on and opens the page of the view X-View names (`django/contrib/admindocs/templates/admin_doc/bookmarklets.html`).

> **Changed in 6.2.** Most of Django's middleware set `async_capable = False`; not `XViewMiddleware`, which, the release notes say, implements neither `process_request` nor `process_response` (`docs/releases/6.2.txt`).
