---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Permissions: `Permission`, groups and `has_perm`

A `Permission` is a row that names one action on one model, given to a user directly or through a group. `PermissionsMixin.has_perm` answers whether a user holds one by asking the authentication backends (an active superuser holds every one), and `ModelBackend` answers from the rows, read once for each user object and kept on it.

A site asks often, a view before it acts and a template for each link it shows, and a project may want answers from somewhere other than the rows. So the question is put to the user, the user puts it to each backend of `AUTHENTICATION_BACKENDS`, and the default backend reads the user's permissions in two queries the first time, then answers from a set of strings such as `"fleet.change_ship"`: an application's label and a codename. `permission_required` asks through `has_perms` ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](requiring-login.md)), and the admin asks the same questions ([Permissions in the admin: `has_change_permission` and the others](../admin/admin-permissions.md)).

## The rows: `Permission` and the group

`Permission` has three fields: `Permission.content_type`, a foreign key to the `ContentType` of a model; `Permission.codename`, such as `"change_ship"`; and `Permission.name`, the text shown to people, "Can change ship". Its `unique_together` makes a codename unique for its content type, not across the site. A permission prints as its content type and its name, `"Fleet | ship | Can change ship"`, and `Permission.user_perm_str`, new in 6.1, gives the string a check takes, `"fleet.change_ship"` (`django/contrib/auth/models.py:Permission`).

The string leaves out the model. Two models of one application that each have a permission with the same codename give the same string, and a user who holds either passes the check for both: given a permission "inspect" on fleet's port and nothing else, tomas passed `has_perm("fleet.inspect")`, which a check meant for the ship asks in the same words. The default codenames carry the model's name, so two of them never meet.

A permission's natural key is its codename, its application's label and its model's name (`django/contrib/auth/models.py:PermissionManager.get_by_natural_key`). The serialization documentation gives the reason one is wanted: migrate makes these rows, so their primary keys depend on how and when it ran (`docs/topics/serialization.txt`). `create_permissions` makes them ([Making the permissions: `create_permissions`](creating-permissions.md)). `Permission`'s docstring sets the design's limit: a permission is held for a type of object, not for one object, so no row can say that nora may change only the ships registered by nora.

The group model is a unique name and a many-to-many field of permissions, with its name as its natural key; its docstring calls it a generic way of categorizing users, for permissions or any other label (`django/contrib/auth/models.py:Group`). A user model that includes `PermissionsMixin`, as `AbstractUser` does, takes its side from it: `PermissionsMixin.is_superuser`, and the many-to-many fields `PermissionsMixin.groups` and `PermissionsMixin.user_permissions`. Both name their reverse accessor `"user_set"` and their reverse lookup `"user"`, where a model's own name would otherwise go, so a query from a group or a permission to its users, such as `ModelBackend.with_perm`'s, reads the same whatever the user model is called (`django/contrib/auth/models.py:PermissionsMixin`).

## Asking: `PermissionsMixin.has_perm`

`PermissionsMixin.has_perm` answers yes at once for a user who is active and a superuser, with no backend asked and no query, whatever the string and the object: piet passes `"fleet.fly_ship"`, which no row names. For anyone else it calls `_user_has_perm`, which goes through `get_backends` in the order of `AUTHENTICATION_BACKENDS`, passing over a backend with no `has_perm`. The first backend to answer true makes the answer yes, and one that raises `PermissionDenied` makes it no at once, the docstring's way for a backend to cut the checks short; after the last, it is no (`django/contrib/auth/models.py:PermissionsMixin.has_perm`, `django/contrib/auth/models.py:_user_has_perm`). `get_backends` makes every backend anew at each call, so nothing kept on a backend's instance outlives the check; `ModelBackend` keeps what it reads on the user ([Authenticating: `authenticate` and the backends](authenticating.md)).

`PermissionsMixin.has_perms` answers yes if every permission of a list passes. A string is itself an iterable, of its characters, and `has_perms` refuses one with `ValueError`. `PermissionsMixin.has_module_perms`, whether the user has any permission in an application, has the shape of `has_perm`. The three getters, `PermissionsMixin.get_user_permissions`, `PermissionsMixin.get_group_permissions` and `PermissionsMixin.get_all_permissions`, have no shortcut for the superuser: `_user_get_permissions` returns the union of the sets of every backend that has the method (`django/contrib/auth/models.py:_user_get_permissions`). Each has an asynchronous twin, `PermissionsMixin.ahas_perm` and the rest, calling the backends' asynchronous methods.

## `ModelBackend`'s answer

`BaseBackend` answers `BaseBackend.has_perm` by membership of the union of its two getters, which give empty sets; it has no `has_module_perms`, which is asked only of backends that have one (`django/contrib/auth/backends.py:BaseBackend`). `ModelBackend` implements the getters from the rows. `ModelBackend._get_permissions` returns an empty set for a user who is inactive or anonymous, and whenever an object is given. Otherwise, the first time, it reads the user's own permissions or those of the user's groups (for a superuser, every row of the table) as pairs of application label and codename, and keeps them on the user object as a set of strings, under `"_user_perm_cache"` or `"_group_perm_cache"`. `ModelBackend.get_all_permissions` keeps their union under `"_perm_cache"`, and `ModelBackend.has_perm` answers whether the user is active and the string is in it (`django/contrib/auth/backends.py:ModelBackend._get_permissions`, `django/contrib/auth/backends.py:ModelBackend.get_all_permissions`). `ModelBackend.has_module_perms` looks in the same set for a string whose label, before the dot, is the application's.

The groups' permissions come in one query, with the user's groups as a subquery. So the first check on a user object costs two queries and every later one none: nora's and tomas's first `has_perm` each sent two, and their second nothing. Piet's `get_all_permissions` sent the same query for the whole table twice, once for each cache. The asynchronous methods fill the two smaller caches and not `"_perm_cache"`.

### The cache lasts as long as the user object

`HttpRequest.user` is one user object for the request ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)), so a request's checks share one cache and the next request starts with a new object. That is all the invalidation there is. Given `"fleet.change_ship"` between two requests, tomas was refused edit_ship with a 403 and then let in. Within one object a permission given after a check is not seen, even after `Model.refresh_from_db`, which leaves the caches; the documentation's advice is to fetch the user again (`docs/topics/auth/default.txt`):

```python
# a shell of the harbour office's site
>>> nora = User.objects.get(username="nora")
>>> nora.has_perm("fleet.add_ship")
False
>>> nora.user_permissions.add(Permission.objects.get(codename="add_ship"))
>>> nora.has_perm("fleet.add_ship")
False
>>> nora.refresh_from_db()
>>> nora.has_perm("fleet.add_ship")
False
>>> User.objects.get(username="nora").has_perm("fleet.add_ship")
True
```

## The users who hold a permission: `with_perm`

`UserManager.with_perm` turns the question round. It asks one backend: the only one configured, or the one whose dotted path it is given, raising `ValueError` when several are configured and none is named (`django/contrib/auth/models.py:UserManager.with_perm`). `ModelBackend.with_perm` builds one query: the users who hold the permission through a group or directly, or are superusers unless `include_superusers=False`, and who are active unless told otherwise; given an object, no users (`django/contrib/auth/backends.py:ModelBackend.with_perm`). In the example `"fleet.change_ship"` gives nora and piet, and nora alone without the superusers.

## The anonymous user's permissions

`AnonymousUser` has the same methods and no superuser shortcut: its `has_perm` and getters ask the backends, and its group permissions are always an empty set (`django/contrib/auth/models.py:AnonymousUser`). `ModelBackend` gives an anonymous user nothing, without a query, so an anonymous visitor holds a permission only where a project's own backend grants one.

## Permissions in templates: `PermWrapper`

The context processor `django.contrib.auth.context_processors.auth` gives a template `"user"`, the request's user, or an `AnonymousUser` when there is none, and `"perms"`, a `PermWrapper` around that user ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)) (`django/contrib/auth/context_processors.py:auth`).

A template's lookup tries a key before an attribute ([Variables and filters: `FilterExpression` and `Variable`](../templates/variables.md)), and both classes answer to keys. `{{ perms.fleet }}` is `PermWrapper.__getitem__`, a `PermLookupDict` for the label, which as a truth value asks `has_module_perms`; `{{ perms.fleet.change_ship }}` is `PermLookupDict.__getitem__`, which asks `has_perm`. The `in` of `{% if %}` reaches `PermWrapper.__contains__`, which takes `"fleet.change_ship"` as the same check and `"fleet"` as the application's (`django/contrib/auth/context_processors.py:PermWrapper`).

Both classes raise `TypeError` when iterated. On `PermLookupDict` the comment cites ticket 18979, which reports an endless loop from `in`. Python answers `in` for an object with `__getitem__` and neither `__contains__` nor `__iter__` by calling `__getitem__` with 0, 1, 2 and on until an item equals the one sought or `IndexError` is raised, and `PermLookupDict.__getitem__` answers each with a boolean from `has_perm` and raises nothing. So in `{% if "change_ship" in perms.fleet %}` the `in` raises at once, and the tag, which turns an error in an operator into false, takes the test as false for every user (`django/contrib/auth/context_processors.py:PermLookupDict.__iter__`, `django/template/smartif.py:infix`):

```python
# a shell of the harbour office's site
>>> t = engines["django"].from_string(
...     "[{% if perms.fleet.change_ship %}edit{% endif %}]"
...     "[{% if 'fleet.change_ship' in perms %}edit{% endif %}]"
...     "[{% if perms.fleet %}fleet{% endif %}]"
...     "[{% if 'change_ship' in perms.fleet %}edit{% endif %}]"
... )
>>> request = RequestFactory().get("/berths/")
>>> request.user = User.objects.get(username="nora")
>>> t.render({}, request)
'[edit][edit][fleet][]'
```

The render sent the backend's two queries at the first question and none for the other three; for tomas, and for an `AnonymousUser`, it gives `'[][][][]'`.
