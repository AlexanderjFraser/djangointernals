---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From a URLconf to a tree

How the calls of `path`, `re_path` and `include` in a URLconf build a tree of `URLResolver` objects and the patterns under them, how `get_resolver` makes the root resolver, and when the modules of a URLconf are imported.

A URLconf is ordinary Python, and importing it is what builds the tree. Each call of `path` returns an object, the list bound to `"urlpatterns"` holds the objects, and nothing is registered anywhere else. A resolver holds the list itself, not a copy, and goes through it afresh each time it resolves a path. The tables for reversing are another matter: they are made from the lists the first time they are needed, once for each language, and do not follow the lists afterwards ([Reversing a name](reversing.md#the-tables)).

## What `path` and `re_path` make

`path` and `re_path` are one function, `_path`, with its last argument fixed: the class of matcher to make, `RoutePattern` for the first and `RegexPattern` for the second. The function first refuses extra arguments that are not a dictionary, with a `TypeError`, and then decides what to build from the type of its second argument, the one a URLconf writes the view in (`django/urls/conf.py:_path`).

When that argument is a list or a tuple, `_path` takes it for what `include` returns, which the next heading describes: a URLconf and two namespaces. It makes a `URLResolver` from the three, with a matcher for the route and with any extra arguments kept as `URLResolver.default_kwargs`. A list or a tuple that does not hold exactly three things fails where the three are unpacked, with a `ValueError` that says nothing about URLs. The last line of the recording below is such a failure, for a list of one pattern passed without `include`.

When the argument is anything else that can be called, `_path` makes a `URLPattern`: a matcher for the route, the callable as `URLPattern.callback`, the extra arguments as `URLPattern.default_args`, and the name. An instance of `View` that cannot be called gets a `TypeError` whose message says to pass the result of `as_view`. Anything else, a string included, gets a plainer `TypeError`.

```text recording=urls
What path() makes of the argument in the view's place
    type(path("tour/", views.Tour.as_view())).__name__  ->  'URLPattern'
    type(path("tour/", views.Tour)).__name__  ->  'URLPattern'
    path("tour/", views.Tour())  ->  raises TypeError: view must be a callable, pass Tour.as_view(), not Tour().
    path("tour/", "museum.views.shop")  ->  raises TypeError: view must be a callable or a list/tuple in the case of include(), but got str.
    path("tour/", views.shop, ["guide"])  ->  raises TypeError: kwargs argument must be a dict, but got list.
    path("shop/", [path("", views.shop)])  ->  raises ValueError
```

The second line is a mistake the function cannot see. A class can be called, so a class-based view given as the class itself, without `as_view`, makes a `URLPattern` like any other; a system check reports it later ([The URL checks, and listing the patterns](checks.md)).

Either kind of entry gets a matcher of the same class, and the matcher is told which kind it serves by one argument, `is_endpoint=True` for a pattern and `is_endpoint=False` for a resolver. How the two match differently follows from that flag ([Routes, regular expressions and converters](patterns.md)).

The name is given to the `URLPattern` and to its matcher as well. The matcher's copy is the one that counts when a path is resolved: it is what a `ResolverMatch` reports as the name, and what a check's message quotes. A name written beside an `include` goes to neither object and is lost.

## What `include` returns

`include` makes no object of the tree. It returns a tuple of three things, and `path` makes the resolver from the tuple: the URLconf to include, its application namespace, and its instance namespace ([Namespaces](namespaces.md) has what the two are for) (`django/urls/conf.py:include`).

Its argument is the URLconf, which can be given in several ways. A string is taken as the dotted name of a module and imported there and then, with `importlib.import_module`. A module is used as it is. So is a list, which is how a few patterns are grouped under one route without a module to hold them, as the museum's shop is. And a tuple of two items is a URLconf, given in one of those ways, with an application namespace beside it.

The application namespace is the attribute `"app_name"` of the module, and the second item of a tuple only where the URLconf has no such attribute. The instance namespace is the one passed as `namespace=...`, or else the application namespace.

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

In the third line the module's own `"app_name"` has overruled the one in the tuple. The refusals are the last four. An instance namespace for a URLconf with no application namespace raises `ImproperlyConfigured`, and so does a tuple of any length but two. A module that cannot be imported fails as any import does. And `include` reads through the list of the URLconf it is given, whether that is a list or a module that holds one, for one thing: an entry made by `i18n_patterns`, which may stand only in a root URLconf ([Language prefixes and translated routes](i18n.md)).

Since the tuple is all that `path` wants, anything that produces such a tuple can stand where a call of `include` would. The admin's does not come from `include` at all. `AdminSite.urls` is a property that returns the list of the site's entries, the application namespace `"admin"`, and the site's name as the instance namespace, and a URLconf gives it to `path` directly (`django/contrib/admin/sites.py:AdminSite.urls`).

## The root resolver

`get_resolver` supplies the top of the tree. Given no argument it takes `settings.ROOT_URLCONF`, and it returns `_get_cached_resolver` of the argument. That function is wrapped in `functools.cache`, so it runs once for each different argument: a URLconf asked for once by its dotted name and once as the module itself gets two resolvers. What it makes is a `URLResolver` around the argument, with a matcher of its own choosing, a `RegexPattern` for the expression `"^/"` (`django/urls/resolvers.py:get_resolver`, `django/urls/resolvers.py:_get_cached_resolver`).

A `URLResolver` keeps what it was given as `URLResolver.urlconf_name`, and that may be the dotted name of a module, a module, or a list of entries. `include` turns a name into a module before it returns, so in the tree recorded below only the root resolver holds a name.

Two properties, each computed once and kept on the resolver, turn that into a list. `URLResolver.urlconf_module` imports the module when it has a name and otherwise returns what it has. `URLResolver.url_patterns` reads the attribute `"urlpatterns"` from that, or takes the thing itself when it has no such attribute, which is how a bare list serves as a URLconf (`django/urls/resolvers.py:URLResolver.urlconf_module`, `django/urls/resolvers.py:URLResolver.url_patterns`).

## What else a URLconf module may hold

Besides the list, Django reads two kinds of name from a URLconf module.

`"app_name"` is read by `include`, as above, and by nothing else.

`handler400`, `handler403`, `handler404` and `handler500` name the views that answer when a request ends in the error of that number. `URLResolver.resolve_error_handler` reads the one it is asked for from the resolver's URLconf module, and takes the default of the same name from `django/conf/urls/__init__.py` when the module has none. The handler looks these up on the root resolver of the request's current URLconf, so they count only in a root URLconf: one written in an included module is never read ([How an exception becomes a response](../handlers/exceptions.md#the-error-views)) (`django/urls/resolvers.py:URLResolver.resolve_error_handler`).

An error view may be given as the view or as its dotted name. `get_callable` is what turns the name into the view: given something callable it returns it, and given a string it splits off the last name, imports the module before it, and returns the attribute. It is wrapped in `functools.cache`, which keeps what a call returned and nothing of a call that raised: a name that leads to a view is looked up once, and one that fails is tried again at each call. The setting that names the view for a CSRF failure is read through it as well (`django/urls/utils.py:get_callable`, `django/middleware/csrf.py:_get_failure_view`).

```text recording=urls
get_callable(), and the error views used when a URLconf names none
    get_callable("museum.views.shop") is views.shop  ->  True
    get_callable(views.shop) is views.shop  ->  True
    get_callable("museum.views.nowhere")  ->  raises ViewDoesNotExist: Could not import 'museum.views.nowhere'. View does not exist in module museum.views.
    get_callable("museum.nowhere.shop")  ->  raises ViewDoesNotExist: Could not import 'museum.nowhere.shop'. Parent module museum.nowhere does not exist.
    get_callable("shop")  ->  raises ImportError: Could not import 'shop'. The path must be fully qualified.
    get_callable(404)  ->  raises ViewDoesNotExist: '404' is not a callable or a dot-notation path
    get_resolver().resolve_error_handler(404)  ->  defaults.page_not_found
    get_resolver().resolve_error_handler(500)  ->  defaults.server_error
    get_resolver().resolve_error_handler(418)  ->  raises AttributeError
```

`get_callable` raises `ViewDoesNotExist` for a module that imports but lacks the name, for a missing submodule of a package that does import, and for a value that is neither callable nor a string. A name with no dot in it raises `ImportError`, and so does one whose top-level package is missing. The check for error views catches both exceptions, which is how a mistyped error view becomes a line of a check's report and not a traceback.

A URLconf may also add to its list what a helper returns. `static` is one that Django ships, for serving uploaded files during development: it returns a list holding one pattern, made with `re_path`, that sends every path under a prefix to the view `serve`. It refuses an empty prefix with `ImproperlyConfigured`, and returns an empty list unless `settings.DEBUG` is true and the prefix is a path on this site. Since it runs as the URLconf is imported, the setting is read once, at that moment. `staticfiles_urlpatterns` wraps it for static files, and `i18n_patterns` is a helper of the same kind, described in [Language prefixes and translated routes](i18n.md) (`django/conf/urls/static.py:static`, `django/contrib/staticfiles/urls.py:staticfiles_urlpatterns`).

## The import, recorded

Making the root resolver imports nothing. The URLconf is imported by the first read of the resolver's `urlconf_module`, which `url_patterns` reads to find its list. In this recording a script asks for the resolver, reads its `url_patterns`, and then does both again. Text in a recording is written the way Python writes a string, so the one backslash in the regular expression for plans appears doubled.

```text recording=urls
The root URLconf is imported by the first read of the root resolver's url_patterns
    before anything asks: 'museum.urls' in sys.modules is False
    the script calls get_resolver()
      get_resolver()
        _get_cached_resolver('museum.urls')  ->  a URLResolver: pattern '^/', urlconf_name 'museum.urls'
    'museum.urls' in sys.modules is False
    the script reads the resolver's url_patterns
      URLResolver.url_patterns  (the root resolver)
        URLResolver.urlconf_module  (the root resolver)
          import museum.urls
            import museum.converters
            import museum.views
            register_converter(MonthConverter, 'month')
            path('', views.shop, name='shop')  ->  a URLPattern: name 'shop', default_args {}
            path('<slug:item>/', views.item, name='item')  ->  a URLPattern: name 'item', default_args {}
            path('', views.entrance, name='entrance')  ->  a URLPattern: name 'entrance', default_args {}
            path('tickets/<int:year>/', views.tickets, name='tickets')  ->  a URLPattern: name 'tickets', default_args {}
            path('tickets/<int:year>/<month:month>/', views.tickets, name='tickets')  ->  a URLPattern: name 'tickets', default_args {}
            include('museum.gallery.urls', namespace='east')
              import museum.gallery.urls
                path('<slug:track>/', views.track, name='track')  ->  a URLPattern: name 'track', default_args {}
                path('', views.wing, name='wing')  ->  a URLPattern: name 'wing', default_args {}
                path('rooms/<int:room>/', views.room, name='room')  ->  a URLPattern: name 'room', default_args {}
                include((a list of 1 entry, 'audio'))  ->  (a list of 1 entry, 'audio', 'audio')
                path('rooms/<int:room>/audio/', what include returned)  ->  a URLResolver: app_name 'audio', namespace 'audio', default_kwargs {}
              -> (the module museum.gallery.urls, 'gallery', 'east')
            path('east/', what include returned, {'wing': 'east'})  ->  a URLResolver: app_name 'gallery', namespace 'east', default_kwargs {'wing': 'east'}
            include('museum.gallery.urls', namespace='west')  ->  (the module museum.gallery.urls, 'gallery', 'west')
            path('west/', what include returned, {'wing': 'west'})  ->  a URLResolver: app_name 'gallery', namespace 'west', default_kwargs {'wing': 'west'}
            include(a list of 2 entries)  ->  (a list of 2 entries, None, None)
            path('shop/', what include returned)  ->  a URLResolver: app_name None, namespace None, default_kwargs {}
            re_path('^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$', views.plan, name='plan')  ->  a URLPattern: name 'plan', default_args {}
            path('files/<path:name>', views.download, name='download')  ->  a URLPattern: name 'download', default_args {}
    'museum.urls' in sys.modules is True
    the script calls get_resolver() and reads url_patterns again
      get_resolver()
```

The import of the root URLconf brings in every URLconf that an `include` under it names. `include` imports a module it is given by name before it returns, so the gallery's module was imported in the middle of the root URLconf's own import, at the first `include` that named it. The second `include` of the same module found it already imported and ran none of its code again.

The last call has only one line under it. The resolver came out of the cache, and its list was already on it.

That second inclusion made a second `URLResolver`, with a namespace and extra arguments of its own, around the same module. The two resolvers therefore read the same list and hold the same pattern objects (`django/urls/resolvers.py:URLResolver.url_patterns`). This is the tree the import left, read back from the root resolver:

```text recording=urls
The tree: what the root resolver holds, read from url_patterns downwards
    URLResolver '^/'; urlconf_name 'museum.urls'
      URLPattern ''; callback views.entrance; name 'entrance'
      URLPattern 'tickets/<int:year>/'; callback views.tickets; name 'tickets'
      URLPattern 'tickets/<int:year>/<month:month>/'; callback views.tickets; name 'tickets'
      URLResolver 'east/'; app_name 'gallery', namespace 'east'; default_kwargs {'wing': 'east'}; urlconf_name the module museum.gallery.urls
        URLPattern ''; callback views.wing; name 'wing'
        URLPattern 'rooms/<int:room>/'; callback views.room; name 'room'
        URLResolver 'rooms/<int:room>/audio/'; app_name 'audio', namespace 'audio'; urlconf_name a list of 1 entry
          URLPattern '<slug:track>/'; callback views.track; name 'track'
      URLResolver 'west/'; app_name 'gallery', namespace 'west'; default_kwargs {'wing': 'west'}; urlconf_name the module museum.gallery.urls
        its entries are the list under 'east/': the same objects
      URLResolver 'shop/'; urlconf_name a list of 2 entries
        URLPattern ''; callback views.shop; name 'shop'
        URLPattern '<slug:item>/'; callback views.item; name 'item'
      URLPattern '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'; callback views.plan; name 'plan'
      URLPattern 'files/<path:name>'; callback views.download; name 'download'
```

## Who reads the list first

Which code makes that first read decides when a mistake in a URLconf comes to light.

Under a production server it is the first request that needs the URLconf. `get_wsgi_application` loads the settings and the applications and makes the handler, and none of that touches the URLconf. `URLResolver.resolve` reads `url_patterns` for the first path that reaches it, unless something in the request has needed the URLconf sooner: `LocaleMiddleware.process_request` has `url_patterns` read to learn whether the URLconf has a language prefix, and when an exception raised in a middleware is to be answered by an error view, `URLResolver.resolve_error_handler` reads the URLconf's module to look for one.

A management command that runs the system checks gets there earlier. The check `check_url_config` asks the root resolver to check itself, and `URLResolver.check` goes through `url_patterns` to do it, so a command such as check or runserver imports the whole tree before it does its work ([The URL checks, and listing the patterns](checks.md), [The system checks](../commands/checks.md)). The development server's reloader reads `urlconf_module` for a purpose of its own as soon as the applications are ready, since a module that has not been imported is not among the files it watches; if the import raises, it keeps the exception and carries on ([The autoreloader](../commands/autoreload.md)) (`django/utils/autoreload.py:BaseReloader.run`).

The first call of `reverse` reads the list too, to build its tables.

## When the import fails

A URLconf that cannot be imported is not one error at startup. A property that raised has kept nothing, so the import is tried again by whatever reads it next, and the next reader is the code that is trying to report the failure. This is one request, with `settings.DEBUG` off, to a project whose root URLconf imports a module that does not exist.

```text recording=urls
GET / when ROOT_URLCONF names a module that cannot be imported, with DEBUG = False
    BaseHandler.resolve_request
      URLResolver.resolve('/')  (the root resolver)
        URLResolver.urlconf_module  (the root resolver)  raises ImportError
    response_for_exception
      handle_uncaught_exception
        URLResolver.resolve_error_handler(500)  (the root resolver)
          URLResolver.urlconf_module  (the root resolver)  raises ImportError
    the handler raises ImportError to the server
    afterwards
      "urlconf_module" in vars(get_resolver())  ->  False
      get_urlconf()  ->  'museum.urls_broken'
```

The import failed inside `resolve_request`, and `convert_exception_to_response`, the wrapper around the centre of the middleware chain, caught the exception as it catches any other. To answer with a 500 it went to find the 500 error view, which a URLconf may name: `URLResolver.resolve_error_handler` reads the URLconf module, the import was tried again, and this second exception had nothing left to catch it. With no middleware in the chain it left the handler for the server to deal with; in a longer chain the wrapper around each middleware would have made one more attempt of the same kind ([How an exception becomes a response](../handlers/exceptions.md#what-does-reach-the-server)). The two lines under afterwards are what the failed request left behind. The resolver still has no module, so the next request will try the import again. And the thread still has the current URLconf the handler set for the request, since what clears it is the closing of a response, and there was none ([The script prefix, the current URLconf and the caches](state.md#the-current-urlconf)).

Turning `settings.DEBUG` on does not rescue the request. The debug page for an exception is made without any error view, but it names the view that was handling the request, and for a request that has no match yet it resolves the path to find out:

```text recording=urls
The same request with DEBUG = True
    BaseHandler.resolve_request
      URLResolver.resolve('/')  (the root resolver)
        URLResolver.urlconf_module  (the root resolver)  raises ImportError
    response_for_exception
      handle_uncaught_exception
        technical_500_response
          get_caller
            resolve('/')
              URLResolver.resolve('/')  (the root resolver)
                URLResolver.urlconf_module  (the root resolver)  raises ImportError
    the handler raises ImportError to the server
```

`technical_500_response` asked `get_caller` which view was responsible, `get_caller` resolved the request's path, and the import failed for the second time, inside the function that was building the page (`django/views/debug.py:get_caller`).

A subtler failure has a message of its own. A module the URLconf imports, or the URLconf itself, may call `reverse` at import time, for a constant or a default argument. The call needs the list of a URLconf that is still half imported. The recording makes such a module the root URLconf: it calls `reverse` on the line above its own list. The script then asks for a path with `resolve`, the function that calls the root resolver's `URLResolver.resolve` for any caller ([Resolving a path](resolving.md)).

```text recording=urls
ROOT_URLCONF = 'museum.urls_early', a URLconf that calls reverse() above its own urlpatterns
    resolve("/")  ->  raises ImproperlyConfigured: The included URLconf 'museum.urls_early' does not appear to have any patterns in it. If you see the 'urlpatterns' variable with valid patterns in the file then the issue is probably caused by a circular import.
    afterwards
      "museum.urls_early" in sys.modules  ->  False
      "urlconf_module" in vars(get_resolver())  ->  True
      hasattr(get_resolver().urlconf_module, "urlpatterns")  ->  False
      resolve("/")  ->  raises ImproperlyConfigured
```

Resolving the path began the import; the import ran the module's call of `reverse`; that call went to the same resolver for its list, and was handed the module as it stood in `sys.modules`, imported as far as the line that was running and with no `"urlpatterns"` yet. `url_patterns` then has a module in place of a list, cannot iterate it, and raises the `ImproperlyConfigured` whose message guesses at a circular import. The exception ends the import, which is why the module is gone from `sys.modules` afterwards.

This failure is kept, where a plain failed import is not. The inner read of `urlconf_module` returned a value, the half-made module, and the property stored it. The lines under afterwards show the resolver still holding a module with no list in it, and the same error when a path is resolved again. No import is tried then, because the property has its value. `reverse_lazy` exists for code like this: it returns at once, and calls `reverse` only when its result is used as text ([Reversing a name](reversing.md#reverse_lazy)).
