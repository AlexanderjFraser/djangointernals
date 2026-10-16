---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Lazy objects: `LazyObject` and `SimpleLazyObject`

A `LazyObject` stands in for an object that is made on its first use and then kept: it holds the object in `LazyObject._wrapped`, which starts as the marker `empty`, fills it by calling `LazyObject._setup`, and forwards attribute reads and a fixed set of special methods to it. `SimpleLazyObject` is the lazy object made from a function.

Django names some objects before it makes them: the settings and the default storage at the top of a module, a request's user as each request comes in. A **lazy object** passes for such an object, makes it at its first use and keeps it, where a lazy value calls its function at every use ([Lazy values: `lazy`, `Promise` and `keep_lazy`](lazy.md)). Python gives a proxy two ways in: an attribute it lacks can be caught in general, by `__getattr__`, but a special method, the one behind `==` or `len`, is looked up on the type and never reaches `__getattr__`, so the proxy forwards only those its class names. The example is HOME of [The utility layer](../utils.md), a `SimpleLazyObject` of a lambda that fetches the port Valletta.

## The marker, `_setup` and assignment

`empty` is a bare `object()` (`django/utils/functional.py:empty`). `LazyObject.__init__` puts it in `_wrapped`; `LazyObject._setup` raises `NotImplementedError`, and a subclass writes it to assign the object to `_wrapped` (`django/utils/functional.py:LazyObject`). The comment in `__init__` warns that a subclass overriding it will likely need its own copying methods: `LazyObject` copies an empty lazy object by calling `type(self)()`, with no arguments.

`_wrapped` is also a class attribute, `None`, so that tracing `__init__` does not recurse (ticket 19456): a tracer may read an attribute, in the ticket `__class__`, before `__init__` has set `_wrapped`, and with no `_wrapped` anywhere the read would fall to `__getattr__`, which reads `_wrapped`, and so on. With the class attribute deleted, a run raised `RecursionError`.

Assignment and deletion go through to the wrapped object. `LazyObject.__setattr__` writes `_wrapped` into the proxy's own `__dict__` and, for any other name, sets the object up and sets the attribute on it; `LazyObject.__delattr__` refuses `_wrapped` with `TypeError` and deletes anything else from the object (`django/utils/functional.py:LazyObject.__setattr__`, `django/utils/functional.py:LazyObject.__delattr__`). Assigning HOME a country sent the query and changed the Port.

## Two ways in: `__getattr__` and the special methods

`new_method_proxy` makes every forwarding method of `LazyObject` but `__setattr__` and `__delattr__`, as a function that takes the proxy, calls `_setup` if `_wrapped` is `empty`, calls the given function on the wrapped object, and is marked `_mask_wrapped = False` (`django/utils/functional.py:new_method_proxy`). `LazyObject.__getattr__` is `new_method_proxy(getattr)`, called when the ordinary lookup fails, as it does for any name the proxy does not have itself: HOME's `__module__` is the proxy's, `"django.utils.functional"`. The special methods are class attributes made the same way: `__str__`, `__bytes__`, `__bool__`, `__dir__`, `__hash__`, `__eq__`, `__ne__`, `__lt__`, `__gt__`, `__getitem__`, `__setitem__`, `__delitem__`, `__iter__`, `__len__` and `__contains__` (`django/utils/functional.py:LazyObject`).

```text figure=the-proxy
HOME, a SimpleLazyObject whose _wrapped is empty; valletta, the same row fetched directly

HOME.name                                  HOME == valletta
  LazyObject.__getattribute__("name")        Python takes __eq__ from type(HOME):
    finds nothing: AttributeError            LazyObject.__eq__,
  LazyObject.__getattr__("name"),            a new_method_proxy(operator.eq)
    a new_method_proxy(getattr)
  _wrapped is empty: _setup()                _wrapped is empty: _setup()
    the lambda runs, one query                 the lambda runs, one query
    the Port is kept in _wrapped               the Port is kept in _wrapped
  getattr(the Port, "name")  'Valletta'      operator.eq(the Port, valletta)  True

HOME.__eq__, read as an attribute, takes the left path: the proxy's __eq__
is marked _mask_wrapped = False, so __getattribute__ raises AttributeError.
Once _wrapped holds the Port, both paths skip _setup().
```

*The two ways into a lazy object, an attribute through `__getattr__` and a special method through the proxy's class, each setting the object up while `_wrapped` is `empty`.*

The special methods are also attributes of the proxy, so an ordinary read would find them, and `hasattr` would call a port iterable. `LazyObject.__getattribute__`, which every attribute read passes through, raises `AttributeError` for what the ordinary lookup finds marked `_mask_wrapped = False`, so that, as its comment says, `__getattr__` answers from the wrapped object (`django/utils/functional.py:LazyObject.__getattribute__`):

```text
hasattr(type(HOME), "__iter__")  ->  True
hasattr(HOME, "__iter__")        ->  False   (1 query: HOME is set up)
iter(HOME)                       ->  raises TypeError: 'Port' object is not iterable
HOME.__eq__                      ->  <bound method Model.__eq__ of <Port: Valletta>>
```

## What is not forwarded

A special method the class does not name falls to `object`'s, or to none. TONNAGE is a `SimpleLazyObject` of the fleet's total tonnage, 601:

```text
TONNAGE + 1       ->  602
1 + TONNAGE       ->  602
TONNAGE <= 700    ->  raises TypeError: '<=' not supported between instances of 'SimpleLazyObject' and 'int'
TONNAGE * 2       ->  raises TypeError: unsupported operand type(s) for *: 'SimpleLazyObject' and 'int'
f"{TONNAGE}"      ->  '601'
f"{TONNAGE:>5}"   ->  raises TypeError: unsupported format string passed to SimpleLazyObject.__format__
callable(SimpleLazyObject(lambda: len))  ->  False
```

Addition works because `SimpleLazyObject` adds `__add__` and `__radd__`; `__le__` and `__ge__` are not forwarded; a format with no specification falls to `str`; `callable` asks the type, which defines no `__call__`.

`__class__` is forwarded, as a property made by `new_method_proxy`, because, the comment says, objects that care about the class, in equality tests above all, must see the wrapped one (`django/utils/functional.py:LazyObject`). `isinstance` tries the type and then `__class__`, so `isinstance(HOME, Port)` is true while `type(HOME)` is `SimpleLazyObject`.

> **Trap.** Reading `__class__` sets the object up: `isinstance(HOME, Port)` on an empty HOME sent the query.

## Copying and pickling

`LazyObject.__reduce__` sets the object up and has pickle write `unpickle_lazyobject` with the wrapped object as its argument, a function that returns its argument (`django/utils/functional.py:LazyObject.__reduce__`). The comment above it, citing ticket 25389, gives the reason: the faked `__class__` confuses pickle, and a proxy acting as the wrapped object outright would still have its own identity, a distinct object with the same `__dict__`. Pickling HOME sent its query and gave back a Port; the lambda, which pickle cannot write, was never pickled; and a list of HOME and its Port came back holding one object twice. The migration serializer reads a lazy object's value from the same arguments ([Serializing values: `serializer_factory` and `deconstruct`](../migrations/serializer.md)) (`django/db/migrations/serializer.py:serializer_factory`).

`LazyObject.__copy__` and `LazyObject.__deepcopy__` copy the wrapper while it is empty, by `type(self)` (not `__class__`, which the comment notes is proxied), and after setup the wrapped object, so that copy is not lazy (`django/utils/functional.py:LazyObject.__copy__`). `SimpleLazyObject` overrides both, keeping the two cases; with HOME:

```text
copy.copy(HOME), HOME empty   ->  a new SimpleLazyObject of the same lambda
  the copy and HOME used      ->  two queries, two Port objects
copy.copy(HOME), HOME set up  ->  <Port: Valletta>, a copy of the Port
```

## `SimpleLazyObject`

`SimpleLazyObject.__init__` writes the function straight into the instance's `__dict__` as `"_setupfunc"`, where an assignment would have gone through `__setattr__` to the wrapped object; `SimpleLazyObject._setup` calls it and stores the result (`django/utils/functional.py:SimpleLazyObject`). The docstring asks that the function be safe to run more than once and return the same value, since Django may copy the proxy, and each empty copy runs it.

`SimpleLazyObject.__repr__` does not set the object up: it shows the function while the proxy is empty, and the object after.

```text
repr(HOME), empty    ->  <SimpleLazyObject: <function <lambda> at 0x000001B67121E560>>
repr(HOME), set up   ->  <SimpleLazyObject: <Port: Valletta>>
```

A function that is a bound method of the proxy is shown only by its name, to avoid recursion, as the comment says: a bound method's repr holds its object's, and with the check removed a run raised `RecursionError` (`django/utils/functional.py:SimpleLazyObject.__repr__`).

`SimpleLazyObject.__copy__` and `SimpleLazyObject.__deepcopy__`, while the proxy is empty, make a `SimpleLazyObject` of the same function, not an instance of the subclass, whose `__init__` may take other arguments. So an empty copy of an unused `Truncator` wraps its text, and its `chars` raises `AttributeError: 'str' object has no attribute 'chars'`.

## Django's lazy objects

| object, and what makes it | its first use makes | told in |
|---|---|---|
| `django.conf.settings`, `django/conf/__init__.py:LazySettings` | a `Settings` from `"DJANGO_SETTINGS_MODULE"`, unless `LazySettings.configure` came first | [The settings object](../startup/settings.md) |
| `default_storage`, `django/core/files/storage/__init__.py:DefaultStorage` | the `"default"` storage | [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md) |
| `staticfiles_storage`, `django/contrib/staticfiles/storage.py:ConfiguredStorage` | the `"staticfiles"` storage | [Content types, static files and the other contrib apps](../contrib.md) |
| the admin's `site`, `django/contrib/admin/sites.py:DefaultAdminSite` | the class `SimpleAdminConfig.default_site` names | [Registering models: `AdminSite.register` and `ModelAdmin`](../admin/registration.md) |
| a request's nonce, `django/utils/csp.py:LazyNonce` | `generate_nonce()` | [Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](../security/csp.md) |
| a `Truncator`, `django/utils/text.py:Truncator` | its text as a string | [Text helpers: `Truncator` and `django/utils/text.py`](text.md) |
| `HttpRequest.user`, `django/contrib/auth/middleware.py:AuthenticationMiddleware` | the user `get_user` finds | [The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md) |
| the context's `"csrf_token"`, `django/template/context_processors.py:csrf` | the token from `get_token`, or `"NOTPROVIDED"` | [The context: `Context`, `RequestContext` and context processors](../templates/context.md) |
| a test response's resolver_match, `django/test/client.py:Client.request` | the path resolved | [The test framework](../testing.md) |

*Django's lazy objects: the first four subclass `LazyObject`, the rest are or subclass `SimpleLazyObject`.*

Putting `empty` back in `_wrapped` makes a lazy object lazy again, which Django does to both storages when a test overrides `STORAGES`, `STATIC_ROOT` or `STATIC_URL` (`django/test/signals.py:storages_changed`).
