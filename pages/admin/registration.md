---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Registering models: `AdminSite.register` and `ModelAdmin`

`AdminSite.register` is how a model comes to be in the admin: it makes an instance of a `ModelAdmin` class for the model and keeps it in the site's registry, `AdminSite._registry`. Ordinarily each application's admin module does the registering, imported by `autodiscover` as Django starts, and the model admin it makes serves every request for its model from then on.

The admin knows only the models it is told of, and must be told before its URLs are built: `AdminSite.get_urls` makes them from the registry as it then stands ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](site-urls.md)) (`django/contrib/admin/sites.py:AdminSite.get_urls`). Registration is startup code.

## The site and its registry

`AdminSite.__init__` gives a site an empty registry, a dictionary from each model class to its model admin; its `AdminSite.name`, `"admin"` unless given another, the instance namespace of its URLs; and its actions, at first only `delete_selected` ([Actions: `response_action` and `delete_selected`](actions.md)). It adds the site to `all_sites`, a weak set of sites, which the admin's system checks go through ([The admin's checks: `check_dependencies` and `ModelAdminChecks`](checks.md)) (`django/contrib/admin/sites.py:AdminSite.__init__`).

## `AdminSite.register`, in order

`AdminSite.register` takes a model or an iterable of models, a model admin class, `ModelAdmin` itself when none is given, and any keyword arguments. A single model, an instance of `ModelBase`, is made a list of one, and each model is taken in turn (`django/contrib/admin/sites.py:AdminSite.register`):

1. An abstract model is refused with `ImproperlyConfigured`.
2. So is a model with a composite primary key; the documentation calls the admin's support for such keys work still to come (`docs/topics/composite-primary-key.txt`).
3. A model already registered is refused with `AlreadyRegistered`, naming the model admin that holds it, or only the application when that model admin's class is named `ModelAdmin`: most likely, a comment says, a model registered without a subclass.
4. A swapped model is passed over in silence. The auth application's admin module registers `User` whatever `AUTH_USER_MODEL` names (`django/contrib/auth/admin.py:UserAdmin`).
5. With keyword arguments, a subclass of the class is made with `type`, named after the model plus "Admin", the arguments as its attributes.
6. The class is called with the model and the site, and the instance is stored under the model.

A refusal undoes nothing: the models before it in the iterable stay registered.

The subclass of the fifth step is given `django.contrib.admin.sites` as its module: without it, a comment says, the class "appears to 'live' in the wrong place". Made without it in a run, the class said it lived in `django.forms.widgets`, the module of its metaclass's `__new__` (`django/forms/widgets.py:MediaDefiningClass.__new__`).

With harbour's admin registered: the registry, each model admin as `ModelAdmin.__str__` writes it; the refusals of Named, the abstract base of Port and Ship, of Berth, keyed by port and number, and of two models already there; a registration with options:

```text
admin.site._registry
    Group    auth.GroupAdmin
    User     auth.UserAdmin
    Port     fleet.PortAdmin
    Ship     fleet.ShipAdmin
    Voyage   fleet.ModelAdmin

admin.site.register(Named)
    ImproperlyConfigured: The model Named is abstract, so it cannot be registered with admin.
admin.site.register(Berth)
    ImproperlyConfigured: The model Berth has a composite primary key, so it cannot be registered with admin.
admin.site.register(Ship)
    AlreadyRegistered: The model Ship is already registered with 'fleet.ShipAdmin'.
admin.site.register(Voyage)
    AlreadyRegistered: The model Voyage is already registered in app 'fleet'.

admin.site.unregister(Voyage)
admin.site.register(Voyage, list_display=["ship", "sailed"])
type(admin.site.get_model_admin(Voyage))
    <class 'django.contrib.admin.sites.VoyageAdmin'>
type(admin.site.get_model_admin(Voyage)).__bases__
    (<class 'django.contrib.admin.options.ModelAdmin'>,)
```

## Taking a model out and looking one up

`AdminSite.unregister` deletes each model it is given from the registry, raising `NotRegistered` for one that is not there; `AdminSite.is_registered` asks the registry; `AdminSite.get_model_admin` returns the model admin or raises `NotRegistered` (`django/contrib/admin/sites.py:AdminSite.unregister`, `django/contrib/admin/sites.py:AdminSite.get_model_admin`).

## Registering by decorator

`django.contrib.admin.register` takes the models and, by the keyword site, a site to use in place of the default one. Applied to a class, it refuses with `ValueError` a call that named no model, a site that is not an `AdminSite`, and a class that is not a subclass of `ModelAdmin`; then it passes the models and the class to the site's `AdminSite.register` and returns the class unchanged: in harbour's admin module ShipAdmin names the class, and the instance lives only in the registry (`django/contrib/admin/decorators.py:register`).

## Finding the admin modules: `autodiscover`

`AdminConfig` is the configuration Django picks for `"django.contrib.admin"`. `AdminConfig.ready` does what `SimpleAdminConfig.ready` does, registering the admin's system checks, then calls `autodiscover`, which imports, by `autodiscover_modules`, the module `"admin"` of every installed application that has one, with the default site as the registry to restore if an import fails ([Importing by name: `import_string` and `autodiscover_modules`](../utils/importing.md)) (`django/contrib/admin/apps.py:AdminConfig.ready`, `django/contrib/admin/__init__.py:autodiscover`). `ready` runs after every application's models are imported ([Populating the app registry](../startup/populate.md)), and the modules run in the order of `INSTALLED_APPS`: auth's registered Group and User before harbour's ran.

`SimpleAdminConfig` registers the checks and discovers nothing, for a project that registers with a site of its own and imports its admin modules itself, as the documentation says (`docs/ref/contrib/admin/index.txt`).

## The default site

`django.contrib.admin.site` is a `DefaultAdminSite`, a `LazyObject` whose `DefaultAdminSite._setup` imports the dotted path the admin application's config gives as `SimpleAdminConfig.default_site` and calls what it names ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)) (`django/contrib/admin/sites.py:DefaultAdminSite`). The admin's own config names `AdminSite`; a project names a subclass, or a function that returns a site, in a config of its own put in the admin's place.

## One model admin for every request

`ModelAdmin.__init__` keeps the model as `ModelAdmin.model`, its `_meta` as `ModelAdmin.opts` and the site as `ModelAdmin.admin_site`, then `BaseModelAdmin.__init__` merges in `BaseModelAdmin.formfield_overrides` ([The admin's forms: `get_form` and `formfield_for_dbfield`](admin-forms.md)) (`django/contrib/admin/options.py:ModelAdmin.__init__`). It is made once, and `ModelAdmin.get_urls` builds the model's URLs from its bound methods: the view that /admin/fleet/ship/ resolves to carries as its model admin the instance `get_model_admin` returns for Ship. That one object answers every request for the model's pages, for every user, and under a threaded server in several threads at once.

So nothing of a request is kept on it. The request is an argument of every method that depends on it, and what a request needs is made and returned: the inlines' instances by `ModelAdmin.get_inline_instances`, the form class by `ModelAdmin.get_form`, the `ChangeList` by `ModelAdmin.get_changelist_instance`.

`BaseModelAdmin` is made by the metaclass `MediaDefiningClass`, so that a model admin's inner `Media` class goes into its media ([The admin's templates and media](templates.md)). `ModelAdmin.__init_subclass__` warns when a subclass sets `ModelAdmin.list_select_related` to `True`, deprecated in 6.1 ([The change list: `changelist_view` and `ChangeList`](change-list.md)) (`django/contrib/admin/options.py:ModelAdmin.__init_subclass__`).

## Options and hooks

A model admin's options are class attributes, with defaults on `BaseModelAdmin`, which inlines share, and on `ModelAdmin` (`django/contrib/admin/options.py:ModelAdmin`). Many have a hook that takes the request and by default returns the option, as `ModelAdmin.get_list_display` returns `ModelAdmin.list_display`. `get_changelist_instance`, for one, builds the `ChangeList` from what `get_list_display`, `ModelAdmin.get_list_filter` and `ModelAdmin.get_search_fields` return ([The change list's columns: `list_display` and `list_editable`](list-display.md)). A project overrides a hook to decide by the request; one that also takes the object, as `BaseModelAdmin.get_readonly_fields` does, can decide object by object.

## The rows: `get_queryset` and `get_object`

`BaseModelAdmin.get_queryset` gives the model admin's pages their rows: the default manager's queryset, ordered by what `BaseModelAdmin.get_ordering` returns, by default `BaseModelAdmin.ordering`, when that is not empty, else by the model's own (`django/contrib/admin/options.py:BaseModelAdmin.get_queryset`). The change list and the autocomplete view start from it, and so does `ModelAdmin.get_object`, by which the change, delete and history views load their object. `get_object` converts the key from the URL by the `to_python` of the primary key, or of the field `"_to_field"` names, and returns the one matching row of the queryset, or `None` when the key does not convert or no row matches (`django/contrib/admin/options.py:ModelAdmin.get_object`). For ShipAdmin, the key "abc" gave `None` with no query sent, and "9" gave `None` after one.

An override of `get_queryset` narrows them all at once. With ShipAdmin's `get_queryset` overridden to keep only ships above 300 tons for users who are not superusers, nora's change list showed Endeavour alone, and Beagle's change page sent her to the index with the warning "ship with ID “2” doesn’t exist. Perhaps it was deleted?" ([The change form: `changeform_view`](change-form.md)).
