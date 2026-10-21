---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Applications and tools
contents: registration, site-urls, site-views, admin-permissions, change-form, admin-forms, widgets, inlines, change-list, list-display, filters, actions, deleting, log, templates, checks, admindocs
---

# The admin

`django.contrib.admin` builds a working site for editing a project's rows out of the models themselves. An `AdminSite` keeps a `ModelAdmin` for each model registered with it and turns them into a URLconf; each `ModelAdmin` serves its model's list, add, change, delete and history pages, built from the model's `_meta` and the model admin's options, and asks the user's permissions before each.

What the admin has to do is easy to state. Given the models of a project and nothing else, it must give the project's staff a page that lists each model's rows and can search, filter and sort them, a form to add a row and one to change it, a way to delete a row and see what goes with it, and a record of who changed what; and it must show each user only what that user is allowed to do. A model already says most of what that takes. Its `_meta` names its fields and their types, which say what form field each needs; its verbose names give the pages their titles; its relations say what a delete would take with it; and the auth application has, by default, made four permissions for it, to add, change, delete and view. What the model does not say, which columns a list shows or which fields can be searched, a project says in a model admin's options, class attributes such as `list_display` and `search_fields`.

So the admin is mostly glue. It writes no SQL, parses no forms and checks no passwords of its own: its URLs are a URLconf, its forms are model forms and inline formsets, its lists are querysets and a `Paginator`, its pages are templates, its users and permissions are the auth application's, and its notices are messages. What it adds is the decisions: which form, which fields, which permission, which template, and in what order a save is done. Those decisions are the chapter.

## The objects

| object | what it is | when it acts |
|---|---|---|
| `AdminSite` | an **admin site**: its **registry** of model admins, its URLs, and the pages that are not about one model (the index, the login, the logout) | at registration; when its URLs are read; on every request to it |
| `site` | the default admin site, an instance of `DefaultAdminSite` that makes the real site at its first use | when anything uses it |
| `ModelAdmin` | a **model admin**: one model's options and the views that use them | made once, when its model is registered; then on every request for that model's pages |
| `InlineModelAdmin` | an **inline**: a related model's rows edited on the parent's form, as an inline formset | made for each request to a change form |
| `AdminSite.admin_view` | the wrapper around every page but the login: lets only **staff** in, active users whose `is_staff` is true; turns caching off, but for three of the site's pages, and the CSRF check on | on every request |
| `ChangeList` | the **change list**: the filtered, searched, sorted and paginated queryset of one model's list page | made by `ModelAdmin.changelist_view` for each request |
| `ModelAdmin.changeform_view` | the **change form**: the add page and the change page, which are one view | on each add or change page |
| `AdminForm`, `InlineAdminFormSet` | wrappers that walk a form or a formset in fieldsets for the templates | while a change form renders |
| `delete_selected` | the **action** the site gives every model admin, offered to users who may delete; an action is a function run on the objects selected in a change list or, since 6.1, on a change form's object | when a change list is posted with an action |
| `LogEntry` | a row of the **log**: who added, changed or deleted which object, and what changed | written after the change form saves its object or an editable list a row, and before the delete page or `delete_selected` deletes; another action logs only what it logs itself |

*The objects of the admin. All of them are in `django/contrib/admin/`; `django/contrib/admin/options.py` holds the model admins and their views, `django/contrib/admin/sites.py` the site.*

## The harbour office's admin

The harbour office keeps its ports, ships and voyages in the admin. Its settings install the admin with the applications startproject writes beside it but the static files, four of the middleware startproject writes, and a template engine that finds templates in the applications' directories, where the admin keeps its own:

```python
# harbour/settings.py
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "harbour.fleet",
    "harbour.crew",
    "harbour.office",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
```

The URLconf puts the default site under admin/:

```python
# harbour/urls.py
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
```

And the fleet application says what its models look like in the admin:

```python
# harbour/fleet/admin.py
from django.contrib import admin

from harbour.fleet.models import Port, Ship, Voyage


class ShipInline(admin.TabularInline):
    model = Ship
    fields = ["name", "tonnage"]
    extra = 1


@admin.register(Port)
class PortAdmin(admin.ModelAdmin):
    list_display = ["name", "country"]
    search_fields = ["name"]
    inlines = [ShipInline]


@admin.register(Ship)
class ShipAdmin(admin.ModelAdmin):
    list_display = ["name", "tonnage", "home", "is_large"]
    list_filter = ["home"]
    search_fields = ["name", "home__name"]
    actions = ["home_at_valletta"]

    @admin.display(boolean=True, ordering="tonnage", description="Large")
    def is_large(self, obj):
        return obj.tonnage > 300

    @admin.action(permissions=["change"], description="Home the selected ships at Valletta")
    def home_at_valletta(self, request, queryset):
        valletta = Port.objects.get(name="Valletta")
        count = queryset.update(home=valletta)
        self.message_user(request, "%d ships now home at Valletta." % count)


admin.site.register(Voyage)
```

The office has two ports, Valletta and Piraeus; two ships, Endeavour and Beagle, both of Valletta; and two voyages of Endeavour. It has three users. piet is a superuser. nora is staff, and in the group Clerks, which may view ports and ships and change ships but not add or delete either, and has no permission on voyages. tomas is not staff. One browser, driven by Django's test client, which keeps cookies as a browser does, made these requests as nora:

| request | response | SQL sent |
|---|---|---|
| `"GET"` /admin/, with no cookie | 302 to /admin/login/?next=/admin/ | none |
| `"POST"` /admin/login/?next=/admin/, nora's username and password | 302 to /admin/ | the user, by username; whether a new session key is taken; the session's row inserted; the user's last login updated; the session's row updated |
| `"GET"` /admin/ | 200, "Site administration", listing Ports with a link to view them and Ships with a link to change them | the session's row; the user; the user's own permissions; the permissions of the user's groups; the log |
| `"GET"` /admin/fleet/ship/ | 200, "Select ship to change": Beagle, Endeavour | the session's row; the user; the permissions, two queries; the ports, for the filter; the ships counted, twice; the ships, each with its port |
| `"GET"` /admin/fleet/ship/1/change/ | 200, "Change ship" | the session's row; the user; the ship; the permissions; the ship model's content type; the ports and the sailors, for the two selects |
| `"POST"` /admin/fleet/ship/1/change/, tonnage 368 | 302 to /admin/fleet/ship/ | the session's row; the user; then, in one transaction: the ship; the permissions; the port, by its key, and again that it exists; the check constraint, in a savepoint; the unique constraint; the ship updated; a row of the log inserted |
| `"GET"` /admin/fleet/ship/ | 200, with "The ship “Endeavour” was changed successfully." above the list | as before |
| `"GET"` /admin/fleet/ship/1/history/ | 200, "Change history: Endeavour", one row: nora, "Changed Tonnage." | the session's row; the user; the ship; the permissions; the log's rows for the ship, counted, then read with their users and content types |
| `"GET"` /admin/fleet/port/1/change/ | 200, "View port", the port's ships listed under it | the session's row; the user; the port; the permissions; the port's ships; the port model's content type |
| `"GET"` /admin/fleet/voyage/ | 403 | the session's row; the user; the permissions |
| `"POST"` /admin/logout/ | 200, "Logged out" | the session's row; the user; the permissions; the session's row again, and its delete |

*Nora's visit to the admin. Every response but the 403 carried headers that forbid caching it; the 403 was made from an exception after it had left the admin's wrapper ([How an exception becomes a response](handlers/exceptions.md)).*

The first request found no session, so no user, and the admin answered it, as it ordinarily answers a request for one of its pages from someone who is not staff, with a redirect to its own login page, keeping the page asked for in `"next"` ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](admin/site-urls.md) has the exceptions). The login is the auth application's `LoginView`, given the admin's own form, `AdminAuthenticationForm`, which refuses a user who is not staff ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](auth/login-views.md)) (`django/contrib/admin/sites.py:AdminSite.login`, `django/contrib/admin/forms.py:AdminAuthenticationForm.confirm_login_allowed`).

The index lists, application by application, every registered model on which the user has some permission, and nothing else: auth's users and groups, and the voyages, are registered too, and nora saw none of them. Ports came with a link to view and ships with a link to change, because nora may change ships and only view ports ([The site's own pages: the index, the login and `AdminSite.each_context`](admin/site-views.md)). The change list sent its own queries after the permissions: the ports, which the filter on home offers as its choices; the ships counted twice, once with the filters and the search applied, for the "2 ships" the page shows, and once without, for the total a search's results are given beside, "1 result (2 total)"; and the page of ships, with each ship's port joined in, because home is a column ([The change list: `changelist_view` and `ChangeList`](admin/change-list.md)).

Once the session and the user had been read, the `"POST"` that changed the tonnage did all its work in one transaction. It loaded the ship, checked that nora may change it, built a model form for it, and ran the form's validation, which looked the port up by its key and checked that it exists, then checked the two constraints of the ship model's `Meta`: a tonnage above nought, and no other ship of that name at that port. Then it saved the ship, wrote a row of the log saying that the tonnage had changed, and answered with a redirect to the change list, which showed the message. The port's change form answered with "View port", every field read-only and no button to save, because nora may view ports but not change them; and the voyages answered 403, because nora has no permission on them at all.

## The site and its registry

A model is in the admin because something registered it with a site. `AdminSite.register` takes a model, or several, and a model admin class, and keeps an instance of that class, made with the model and the site, in the site's registry; with no class it uses `ModelAdmin` itself, and with keyword arguments it first makes a subclass that has them as attributes. It refuses an abstract model, a model with a composite primary key, and a model already registered; a swapped model it passes over in silence (`django/contrib/admin/sites.py:AdminSite.register`). The decorator `django.contrib.admin.register` calls it for the class it decorates (`django/contrib/admin/decorators.py:register`).

The registering is done by the project's own modules, and the admin's default config makes sure they are imported. `AdminConfig.ready`, the admin application's `ready` unless a project installs `SimpleAdminConfig` instead, calls `autodiscover`, which imports the module `admin` of every installed application that has one, in the order of `INSTALLED_APPS` ([Importing by name: `import_string` and `autodiscover_modules`](utils/importing.md)) (`django/contrib/admin/apps.py:AdminConfig.ready`, `django/contrib/admin/__init__.py:autodiscover`). That is how harbour/fleet/admin.py ran, and how, before it, the auth application's own admin module registered users and groups. The site they register with, `site`, is a lazy object that, the first time it is used, calls what the admin application's config names in `default_site`, the class `AdminSite` unless a project's config names another (`django/contrib/admin/sites.py:DefaultAdminSite`).

A model admin is made once, at registration, and serves every request for its model from then on, for every user, in every thread. So it holds the model, the model's `_meta` and the site, and its options, and no state of a request: everything that depends on the request is passed to its methods, and many options have a **hook**, a method named after the option with "get" before it, that takes the request (`get_list_display`, `get_fieldsets`), which a project overrides to decide for each request ([Registering models: `AdminSite.register` and `ModelAdmin`](admin/registration.md)).

`AdminSite.urls` turns the registry into a URLconf. It is a triple, as `include` returns one: the site's patterns, the application namespace `"admin"`, and the site's name as the instance namespace, `"admin"` for the default site. The patterns are the site's own pages, then, for each registered model, its application label and model name with the model admin's patterns included under them, then one pattern for the index of every application with a registered model, and last, unless `AdminSite.final_catch_all_view` is false, a pattern that catches every other path (`django/contrib/admin/sites.py:AdminSite.get_urls`):

```text figure=the-site
admin.site, an AdminSite named "admin"
  its registry
    Group   ->  GroupAdmin(Group, admin.site)      the auth application's
    User    ->  UserAdmin(User, admin.site)        the auth application's
    Port    ->  PortAdmin(Port, admin.site)
    Ship    ->  ShipAdmin(Ship, admin.site)
    Voyage  ->  ModelAdmin(Voyage, admin.site)
        |
        |  AdminSite.urls
        v
path("admin/", admin.site.urls)
  ""                              AdminSite.index             admin:index
  login/, logout/, password_change/,
  password_change/done/, autocomplete/, jsi18n/,              the site's own pages
  r/<path:content_type_id>/<path:object_id>/
  auth/group/                     include(GroupAdmin.urls)
  auth/user/                      include(UserAdmin.urls)
  fleet/port/                     include(PortAdmin.urls)
  fleet/ship/                     include(ShipAdmin.urls)
    ""                            changelist_view             admin:fleet_ship_changelist
    add/                          add_view                    admin:fleet_ship_add
    <path:object_id>/history/     history_view                admin:fleet_ship_history
    <path:object_id>/delete/      delete_view                 admin:fleet_ship_delete
    <path:object_id>/change/      change_view                 admin:fleet_ship_change
    <path:object_id>/             a redirect to <path:object_id>/change/
  fleet/voyage/                   include(ModelAdmin.urls)
  ^(?P<app_label>auth|fleet)/$    AdminSite.app_index         admin:app_list
  (?P<url>.*)$                    AdminSite.catch_all_view

Every view but the login is wrapped in AdminSite.admin_view.
```

*The default site of the harbour office: the registry, and the URLconf `AdminSite.urls` makes of it. Each model admin's views are named after the model's application label and model name, under the namespace `"admin"`.*

Every view of that URLconf but the login goes through `AdminSite.admin_view`. The wrapper asks `AdminSite.has_permission`, which is true for a user who is active and staff and asks no permission of any model, and sends anyone else to the login page, or from the logout page to the index; and it adds `never_cache` unless the view was wrapped as cacheable, and `csrf_protect` unless the view is exempt from the CSRF check. The catch-all pattern is wrapped too, so that a stranger asking for any path under admin/ is sent to the login page, whether the path names a model or not; the documentation gives the purpose, which is not to let a stranger find out which models are registered ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](admin/site-urls.md)) (`django/contrib/admin/sites.py:AdminSite.admin_view`, `docs/ref/contrib/admin/index.txt`).

## A model admin's pages

Being staff only lets a user in. What a user may do once in is asked of the model admin, page by page, by four methods: `BaseModelAdmin.has_add_permission`, `has_change_permission`, `has_delete_permission` and `has_view_permission`. Each asks the user's `has_perm` for the permission the auth application made for the model, `"fleet.change_ship"`, and `has_view_permission` is true for a user who may view or may change. The last three take the object in question as well, and ignore it unless a project overrides them to decide object by object ([Permissions in the admin: `has_change_permission` and the others](admin/admin-permissions.md)) (`django/contrib/admin/options.py:BaseModelAdmin.has_change_permission`). The change list and a change page need view or change; the add page, add; saving a change, change; the delete page, delete. A user who may view and not change gets the change form with every field read-only, as nora did for Valletta.

### The change form

The add page and the change page are one view, `ModelAdmin.changeform_view`, which runs a request whose method is not safe inside a transaction on the database the router gives for writing the model (`django/contrib/admin/options.py:ModelAdmin.changeform_view`). For a change it loads the object with `ModelAdmin.get_object`, through the model admin's `get_queryset`, and, once the user's permission to view or change is confirmed, sends the user back to the index with a warning when there is none. It asks `get_fieldsets` which fields to show and in what groups, and `get_form` for a model form class with those fields, the read-only ones left out, each form field the form class does not declare made from its model field by `formfield_for_dbfield`, which is where the admin's widgets come in ([The admin's forms: `get_form` and `formfield_for_dbfield`](admin/admin-forms.md), [The admin's widgets: related objects, raw ids and autocomplete](admin/widgets.md)). Each inline the user has some permission on adds an inline formset ([Inlines: `InlineModelAdmin` and its formsets](admin/inlines.md)).

A `"POST"` is then saved in an order that a project can step into at each point: the form is validated, and `save_form` makes the object without saving it; the formsets are validated; if all are valid, `save_model` saves the object; `save_related` saves its many-to-many data and then each formset; `construct_change_message` describes what changed; `log_addition` or `log_change` writes the log; and `response_add` or `response_change` adds the message and chooses the redirect by the button that was pressed, or, in a popup, answers with a page that hands the object back to the window that opened it (`django/contrib/admin/options.py:ModelAdmin._changeform_view`). A form that does not validate is shown again with its errors, and nothing is saved ([The change form: `changeform_view`](admin/change-form.md)).

### The change list

`ModelAdmin.changelist_view` makes a `ChangeList`, which reads the query string and builds the queryset in a fixed order: every parameter that is not one of the change list's own (the page, the search, the ordering and a few more) is first put to `BaseModelAdmin.lookup_allowed`, which ordinarily refuses a lookup that follows a relation past the related model's key unless a filter or the date hierarchy offers it; each filter of `list_filter` takes the parameters it understands and, ordinarily, narrows the queryset by them; what parameters are left are applied as lookups; by default, the foreign keys named in `list_display` are joined; the ordering is set, from the model admin, the model or the column the user clicked, with the primary key added when that ordering does not pin down every row; the search of `search_fields` is applied; and the result is made distinct if a field's filter, a lookup or the search crossed a relation that can repeat a row. Then it counts the rows and takes one page of them (`django/contrib/admin/views/main.py:ChangeList.get_queryset`, `django/contrib/admin/views/main.py:ChangeList.get_results`). The columns, the filters and the search each have a section: [The change list's columns: `list_display` and `list_editable`](admin/list-display.md) and [Filters and search: `list_filter`, `search_fields` and `date_hierarchy`](admin/filters.md).

### Actions, deleting and the log

The change list is also a form. Ticking rows and choosing an action posts the selected keys and the action's name back to the change list, which calls the action with the queryset of the selected rows, or of every row the list matches when "Select all" was chosen ([Actions: `response_action` and `delete_selected`](admin/actions.md)). The site gives every model admin `delete_selected`, offered only to a user who may delete, unless the model admin sets `actions` to `None`, or the site disables it and the model admin does not name it; ShipAdmin adds home_at_valletta, which only a user who may change ships is offered, as its `permissions` asks. Deleting, by the action or from an object's own delete page, first shows what a delete would take with it, found by a subclass of the collector that a delete itself uses, and refuses when a protected relation or a missing permission stands in the way ([Deleting: `delete_view` and `get_deleted_objects`](admin/deleting.md)).

The admin's views write a `LogEntry` for each object they add, change or delete, though not for the objects an inline saves with it or a delete takes with it, nor for an action's work unless the action logs it, as `delete_selected` does: the user, the content type and key of the object, the object's text as it was, and what changed, kept as JSON with the fields' labels untranslated, and translated when it is read, where the catalogues have the label as it was kept. The history page of an object reads those rows back ([The log and the history: `LogEntry` and `history_view`](admin/log.md)). The row nora's change wrote:

```text
object_repr     Endeavour
action_flag     2   (CHANGE)
change_message  [{"changed": {"fields": ["Tonnage"]}}]
str(entry)      Changed “Endeavour” — Changed Tonnage.
```

## The pages themselves

A model admin's page is ordinarily a `TemplateResponse` of a template the view chooses from a list, unless the model admin names a template of its own: the model's, the application's, then the admin's, so that a project can change one model's change form by putting a template at `"admin/fleet/ship/change_form.html"` in its own templates, which the loaders find before the admin's. The context begins, on every page but the one that closes a popup and the change list's page for a database error, with what `AdminSite.each_context` gives: the site's titles, whether the user is staff, the applications and models the user may see, for the navigation, and the log ([The admin's templates and media](admin/templates.md)). A view sets the request's `"current_app"` to the site's name, so that the URLs its templates reverse lead into the same site when a project has several; the links of the index's recent actions, which a log entry reverses for itself, do not.

The admin needs contenttypes, auth and messages installed, a Django template engine with the messages context processor and, with the default authentication backend, the auth one, and the session, authentication and message middleware; the system checks say so when one is missing, and check the options of each model admin whose class is not `ModelAdmin` itself against its model ([The admin's checks: `check_dependencies` and `ModelAdminChecks`](admin/checks.md)). A sister application, `django.contrib.admindocs`, adds pages, which its documentation has a project include beside the admin's, that document the project's models, views, template tags and filters from their docstrings, and say which directories hold a template of a given name ([The documentation generator: `django.contrib.admindocs`](admin/admindocs.md)).

## Where it meets the rest of Django

The admin's URLs are a URLconf with a namespace ([Namespaces](urls/namespaces.md)), and its views are function views wrapped in `csrf_protect` and, most of them, `never_cache` ([View decorators](views/decorators.md)). Its users, its login, its password change and its permissions are the auth application's ([Authentication, sessions and messages](auth.md)): `AdminSite.has_permission` reads `is_staff`, and a model's pages ask `has_perm`. Its forms are model forms and inline formsets ([Model forms: `ModelForm` and `fields_for_model`](forms/model-forms.md), [Model formsets and inline formsets](forms/model-formsets.md)), with widgets and media of its own ([Form assets: `Media`](forms/media.md)). Its lists are querysets ([QuerySets](querysets.md)) cut into pages by a `Paginator` ([Pagination: `Paginator` and `Page`](services/pagination.md)), and its delete pages walk relations with a subclass of the collector that deleting uses ([Deleting: the `Collector`](instance/deleting.md)). Its pages are templates ([Templates](templates.md)), its notices messages, and its JavaScript is translated by a `JavaScriptCatalog` ([The language views: `set_language` and `JavaScriptCatalog`](i18n/views.md)). The log names objects by their content types, and the default "View on site" link goes through the content types' `shortcut`; the admin's CSS and JavaScript are static files ([Content types, static files and the other contrib apps](contrib.md)).
