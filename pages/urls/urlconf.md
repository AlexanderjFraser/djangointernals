---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From a URLconf to a tree

A URLconf's calls of `path`, `re_path` and `include` build a tree of `URLResolver` objects and the patterns under them as the module is imported, and `get_resolver` makes the root resolver that stands over the tree. Beside its list a URLconf module may name error views, `handler404` among them, which `get_callable` turns from dotted names into views.

A URLconf is ordinary Python, and importing it is what builds the tree. Each call of `path` returns an object, the list bound to `"urlpatterns"` holds the objects, and nothing is registered anywhere else. A resolver holds the list itself, not a copy, and goes through it afresh each time it resolves a path. The tables for reversing are another matter: they are made from the lists the first time they are needed, once for each language, and do not follow the lists afterwards ([Reversing a name](reversing.md#the-tables)). Which code imports the module first, and what a failed import leaves behind, are told in [When a URLconf is imported](import.md).

## What `path` and `re_path` make

`path` and `re_path` are one function, `_path`, with its last argument fixed: the class of matcher to make, `RoutePattern` for the first and `RegexPattern` for the second. The function first refuses extra arguments that are not a dictionary, with a `TypeError`, and then decides what to build from the type of its second argument, the one a URLconf writes the view in (`django/urls/conf.py:_path`).

When that argument is a list or a tuple, `_path` takes it for what `include` returns, which the next heading describes: a URLconf and two namespaces. It makes a `URLResolver` from the three, with a matcher for the route and with any extra arguments kept as `URLResolver.default_kwargs`. A list or a tuple that does not hold exactly three things fails where the three are unpacked, with a `ValueError` that says nothing about URLs.

When the argument is anything else that can be called, `_path` makes a `URLPattern`: a matcher for the route, the callable as `URLPattern.callback`, the extra arguments as `URLPattern.default_args`, and the name. An instance of `View` that cannot be called gets a `TypeError` whose message says to pass the result of `as_view`. Anything else, a string included, gets a plainer `TypeError`.

The second call below is accepted though its view is a class given without `as_view`, and the last is the `ValueError` of a list that does not hold three things, a list of one pattern passed without `include`.

```text recording=urls
What path() makes of the argument in the view's place
    type(path("tour/", views.Tour.as_view())).__name__  ->  'URLPattern'
    type(path("tour/", views.Tour)).__name__  ->  'URLPattern'
    path("tour/", views.Tour())  ->  raises TypeError: view must be a callable, pass Tour.as_view(), not Tour().
    path("tour/", "museum.views.shop")  ->  raises TypeError: view must be a callable or a list/tuple in the case of include(), but got str.
    path("tour/", views.shop, ["guide"])  ->  raises TypeError: kwargs argument must be a dict, but got list.
    path("shop/", [path("", views.shop)])  ->  raises ValueError
```

A class can be called, so `_path` does not tell that mistake from a view, and makes a `URLPattern` like any other; a system check reports it later ([The URL checks, and listing the patterns](checks.md)).

Either kind of entry gets a matcher of the same class, and the matcher is told which kind it serves by one argument, `is_endpoint=True` for a pattern and `is_endpoint=False` for a resolver. How the two match differently follows from that flag ([Routes, regular expressions and converters](patterns.md)).

The name is given to the `URLPattern` and to its matcher as well. The matcher's copy is the one that counts when a path is resolved: it is what a `ResolverMatch` reports as the name, and what a check's message quotes.

> **Trap.** A name written beside an `include` is accepted and dropped. `_path` makes the resolver without it, so the `URLResolver` has no name and its matcher's is `None`, and `reverse` of the name raises `NoReverseMatch` as for a name never written, while the names of the patterns under the include reverse as usual (`django/urls/conf.py:_path`).

## What `include` returns

`include` does not make its resolver. It returns a tuple of three things, and `path` makes the resolver from the tuple: the URLconf to include, its application namespace, and its instance namespace ([Namespaces](namespaces.md) has what the two are for) (`django/urls/conf.py:include`).

Its argument is the URLconf, which can be given in several ways. A string is taken as the dotted name of a module and imported there and then, with `importlib.import_module`. A module is used as it is. So is a list, which is how a few patterns are grouped under one route without a module to hold them, as the museum's shop is. And a tuple of two items is a URLconf, given in one of those ways, with an application namespace beside it.

The application namespace is the attribute `"app_name"` of the module, and the second item of a tuple only where the URLconf has no such attribute. The instance namespace is the one passed as `namespace=...`, or else the application namespace.

Four refusals end the calls below: an instance namespace for a URLconf with no application namespace, a tuple of any length but two, a module that cannot be imported, which fails as any import does, and a URLconf holding an entry made by `i18n_patterns`. Before them, the third call gives a tuple whose second item the module's own `"app_name"` overrules.

```text recording=urls
What include() returns: the URLconf, the application namespace and the instance namespace
    include("museum.gallery.urls")[1:]  ->  ('gallery', 'gallery')
    include("museum.gallery.urls", namespace="east")[1:]  ->  ('gallery', 'east')
    include(("museum.gallery.urls", "exhibits"))[1:]  ->  ('gallery', 'gallery')
    include(([], "audio"))  ->  ([], 'audio', 'audio')
    include(([], "audio"), namespace="guide")  ->  ([], 'audio', 'guide')
    include([])  ->  ([], None, None)
    include([], namespace="guide")  ->  raises ImproperlyConfigured
    include(([], "audio", "guide"))  ->  raises ImproperlyConfigured
    include("museum.nowhere")  ->  raises ModuleNotFoundError
    include("museum.urls_languages")  ->  raises ImproperlyConfigured: Using i18n_patterns in an included URLconf is not allowed.
```

`include` reads through the list of the URLconf it is given, whether that is a list or a module that holds one, for the last refusal and nothing else: an entry made by `i18n_patterns` may stand only in a root URLconf ([Language prefixes and translated routes](i18n.md)).

Since the tuple is all that `path` wants, anything that produces such a tuple can stand where a call of `include` would. The admin's does not come from `include` at all. `AdminSite.urls` is a property that returns the list of the site's entries, the application namespace `"admin"`, and the site's name as the instance namespace, and a URLconf gives it to `path` directly (`django/contrib/admin/sites.py:AdminSite.urls`).

## The root resolver

`get_resolver` supplies the top of the tree. Given no argument it takes `settings.ROOT_URLCONF`, and it returns `_get_cached_resolver` of the argument. That function is wrapped in `functools.cache`, so it runs once for each different argument: a URLconf asked for once by its dotted name and once as the module itself gets two resolvers. What it makes is a `URLResolver` around the argument, with a matcher of its own choosing, a `RegexPattern` for the expression `"^/"` (`django/urls/resolvers.py:get_resolver`, `django/urls/resolvers.py:_get_cached_resolver`).

A `URLResolver` keeps what it was given as `URLResolver.urlconf_name`, and that may be the dotted name of a module, a module, or a list of entries. Two properties, each kept on the resolver once computed, turn that into a list. `URLResolver.urlconf_module` imports the module when it has a name and otherwise returns what it has. `URLResolver.url_patterns` reads the attribute `"urlpatterns"` from that, or takes the thing itself when it has no such attribute, which is how a bare list serves as a URLconf (`django/urls/resolvers.py:URLResolver.urlconf_module`, `django/urls/resolvers.py:URLResolver.url_patterns`).

`include` turns a name into a module before it returns, so in the museum's tree only the root resolver holds a name. Read back from the root once the URLconf is imported, its other resolvers hold the other two kinds: each wing's resolver holds the gallery's module, and the shop's resolver and the resolver of a gallery's audio tracks each hold a bare list.

```text recording=urls
The tree: what the root resolver holds, read from url_patterns downwards
    URLResolver '^/'; urlconf_name 'museum.urls'
      ...
      URLResolver 'east/'; app_name 'gallery', namespace 'east'; default_kwargs {'wing': 'east'}; urlconf_name the module museum.gallery.urls
        ...
        URLResolver 'rooms/<int:room>/audio/'; app_name 'audio', namespace 'audio'; urlconf_name a list of 1 entry
          ...
      URLResolver 'west/'; app_name 'gallery', namespace 'west'; default_kwargs {'wing': 'west'}; urlconf_name the module museum.gallery.urls
        its entries are the list under 'east/': the same objects
      URLResolver 'shop/'; urlconf_name a list of 2 entries
      ...
```

The two wings' resolvers are two objects around one module, each with a namespace and extra arguments of its own: the west wing's `include` was given the same name, and found the module already imported. So the two read the same list and hold the same pattern objects (`django/urls/resolvers.py:URLResolver.url_patterns`).

## What else a URLconf module may hold

Besides the list, Django reads two kinds of name from a URLconf module.

`"app_name"` is read by `include`, as above, and by nothing else.

`handler400`, `handler403`, `handler404` and `handler500` name the views for the errors of those numbers. `URLResolver.resolve_error_handler` reads the one it is asked for from its resolver's URLconf module, and takes the default of the same name from `django/conf/urls/__init__.py` when the module has none (`django/urls/resolvers.py:URLResolver.resolve_error_handler`). Its callers in Django all ask a root resolver: the handler asks the root resolver of the request's current URLconf, and the check of the error views that of `settings.ROOT_URLCONF`. So the names are read from a root URLconf's module, and one written in an included module is read by neither ([The error views](../views/errors.md)) (`django/core/handlers/exception.py:response_for_exception`, `django/core/checks/urls.py:check_custom_error_handlers`).

An error view may be given as the view or as its dotted name. `get_callable` is what turns the name into the view: given something callable it returns it, and given a string it splits off the last name, imports the module before it, and returns the attribute. It is wrapped in `functools.cache`, which keeps what a call returned and nothing of a call that raised: a name that leads to a view is looked up once, and one that fails is tried again at each call. The setting that names the view for a CSRF failure is read through it as well (`django/urls/utils.py:get_callable`, `django/middleware/csrf.py:_get_failure_view`).

`get_callable` refuses with one of two exceptions, and its messages say which mistake was made: in the calls below, `ViewDoesNotExist` for a module that imports but lacks the name, for a missing submodule of a package that does import, and for a value that is neither callable nor a string, and `ImportError` for a name with no dot in it.

```text recording=urls
get_callable(), and the error views used when a URLconf names none
    ...
    get_callable("museum.views.nowhere")  ->  raises ViewDoesNotExist: Could not import 'museum.views.nowhere'. View does not exist in module museum.views.
    get_callable("museum.nowhere.shop")  ->  raises ViewDoesNotExist: Could not import 'museum.nowhere.shop'. Parent module museum.nowhere does not exist.
    get_callable("shop")  ->  raises ImportError: Could not import 'shop'. The path must be fully qualified.
    get_callable(404)  ->  raises ViewDoesNotExist: '404' is not a callable or a dot-notation path
    ...
```

The check of the error views catches both, which is how a mistyped error view becomes a line of a check's report and not a traceback (`django/core/checks/urls.py:check_custom_error_handlers`).

A URLconf may also add to its list what a helper returns, and the helper runs as the URLconf is imported. `static`, for serving files during development, returns a list of one pattern, made with `re_path`, only while `settings.DEBUG` is true, so the setting is read once, at the import ([The static file view](../views/static-files.md#who-routes-to-it)) (`django/conf/urls/static.py:static`). `i18n_patterns` is a helper of the same kind ([Language prefixes and translated routes](i18n.md)).
