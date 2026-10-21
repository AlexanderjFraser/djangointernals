---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# When a URLconf is imported

The root URLconf, and with it every URLconf it includes, is ordinarily imported by the first read of the root resolver's `URLResolver.urlconf_module`, a property that `URLResolver.url_patterns` reads on its way to the list, and whichever part of Django reads it first decides when a mistake in a URLconf comes to light. An import that raises ordinarily leaves nothing on the resolver and is tried again by the next reader, while a root URLconf that calls `reverse` above its `"urlpatterns"` is kept half made unless `reverse` imports it, the failure `reverse_lazy` exists to avoid.

Making the root resolver imports nothing: `get_resolver` makes a `URLResolver` around the dotted name in `settings.ROOT_URLCONF`, and keeps it ([From a URLconf to a tree](urlconf.md#the-root-resolver)). The module is imported when something first asks the resolver for it, through `urlconf_module`, a property that keeps on the resolver the first value it computes; an import that raises computes none (`django/urls/resolvers.py:URLResolver.urlconf_module`). Several parts of Django can be the first to ask. The figure sets them in the order a process can meet them, and below them what the property keeps by how the import ends.

```text figure=first-read
readers, in the order a process can meet them

a management command that runs       check_url_config -> URLResolver.check   -> url_patterns ->
the system checks, before its work
runserver's autoreloader,            BaseReloader.run                                        ->
once the applications are ready
a request                            LocaleMiddleware.process_request        -> url_patterns ->
                                     URLResolver.resolve                     -> url_patterns ->
                                     URLResolver.resolve_error_handler,                      ->
                                     for an error view
the first reverse,                   reverse                                 -> url_patterns ->
to build its tables

the property                         URLResolver.urlconf_module of the root resolver

how the import ends, and what the property keeps

the module is imported         the import raises                   the URLconf calls reverse above its urlpatterns
the module, kept:              nothing:                            the module, half made, kept unless reverse imports it:
no later reader imports it     the next reader imports it again    every later read of url_patterns raises ImproperlyConfigured
```

*Readers that can make the first read of a root resolver's `urlconf_module`, grouped by when a process meets them; each arrow from a reader is a read of the one property, made directly or through `url_patterns`. Below, what the property keeps by how the import ended.*

## The first read

The first read of `URLResolver.urlconf_module` imports the root URLconf, and the import brings in every URLconf that an `include` in it names. `include` imports a module it is given by name before it returns, so each such module is imported in the middle of the root's own import, at the first `include` that names it, and an `include` that names a module already imported runs none of its code again (`django/urls/conf.py:include`). Asked for again, `get_resolver` returns the same resolver from its cache, with its list already on it, and nothing is imported or built again (`django/urls/resolvers.py:get_resolver`, `django/urls/resolvers.py:_get_cached_resolver`).

Look for three things in the import of the museum's root URLconf: the module still absent from `sys.modules` after `get_resolver` has returned; the gallery's module imported inside the root's import, at the east wing's `include`; and nothing under the west wing's `include` of the same module, or under the second `get_resolver`.

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
            ...
            include('museum.gallery.urls', namespace='east')
              import museum.gallery.urls
                ...
              -> (the module museum.gallery.urls, 'gallery', 'east')
            ...
            include('museum.gallery.urls', namespace='west')  ->  (the module museum.gallery.urls, 'gallery', 'west')
            ...
    'museum.urls' in sys.modules is True
    the script calls get_resolver() and reads url_patterns again
      get_resolver()
```

## Who reads the URLconf first

Under a production server the URLconf is first read for the first request that needs it. `get_wsgi_application` loads the settings and the applications and makes the handler, and none of that touches the URLconf (`django/core/wsgi.py:get_wsgi_application`). `URLResolver.resolve` reads `URLResolver.url_patterns` for the first path that reaches it, unless something in the request has needed the URLconf sooner: `LocaleMiddleware.process_request`, for one, has `url_patterns` read to learn whether the URLconf has a language prefix ([Language prefixes and translated routes](i18n.md)), and when an exception raised in a middleware is to be answered by an error view, `URLResolver.resolve_error_handler` reads the URLconf's module to look for one (`django/urls/resolvers.py:URLResolver.resolve`, `django/conf/urls/i18n.py:is_language_prefix_patterns_used`, `django/urls/resolvers.py:URLResolver.resolve_error_handler`).

A management command that runs the system checks gets there earlier. The check `check_url_config` asks the root resolver to check itself, and `URLResolver.check` goes through `url_patterns` to do it, so a command such as runserver imports the whole tree before it does its work ([The URL checks, and listing the patterns](checks.md), [The system checks](../commands/checks.md)) (`django/core/checks/urls.py:check_url_config`, `django/urls/resolvers.py:URLResolver.check`). Under runserver the autoreloader reads `URLResolver.urlconf_module` as well, in `BaseReloader.run`, as soon as the applications are ready, so that the URL modules are already loaded when the reloader starts; if the import raises, it stores the exception and carries on ([The autoreloader](../commands/autoreload.md)) (`django/utils/autoreload.py:BaseReloader.run`).

The first call of `reverse` reads the list too, to build its tables ([Reversing a name](reversing.md#the-tables)) (`django/urls/resolvers.py:URLResolver._populate`).

## When the import fails

A URLconf that cannot be imported, the root or one it includes, is not always one error. A property that raised has kept nothing, so the import is tried again by whatever reads it next, and in a request the next reader is ordinarily the code reporting the failure. The request below goes through a chain with no middleware; its second failure comes from the handler's search for the 500 error view, and the two lines at the end are what the request left behind.

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

The wrapper that `convert_exception_to_response` puts around the centre of the chain catches the first `ImportError`, and to answer it with a 500 asks `URLResolver.resolve_error_handler` for the error view, which reads the URLconf's module. The second `ImportError` is raised inside the wrapper's own handling of the first, and nothing in that wrapper catches it (`django/core/handlers/exception.py:convert_exception_to_response`, `django/core/handlers/exception.py:handle_uncaught_exception`). With no middleware in the chain it goes to the server. Each middleware in the chain has a wrapper of its own, made by the same function, and each wrapper the exception reaches on its way out asks for the 500 error view again (`django/core/handlers/base.py:BaseHandler.load_middleware`): with one middleware that only hands the request on, the import fails three times, the third reaching the server ([How an exception becomes a response](../handlers/exceptions.md#what-does-reach-the-server)). With `settings.DEBUG` on, the debug page takes the error view's place and fares no better: to name the view handling the request it resolves the path, and so tries the import again ([The debug pages and `ExceptionReporter`](../views/debug.md)) (`django/views/debug.py:get_caller`).

The resolver still has no module, so the next request tries the import again. And the thread keeps the current URLconf the handler set for the request, which `get_urlconf` reads: what clears it is the closing of a response, and there was none ([The script prefix, the current URLconf and the caches](state.md#the-current-urlconf)) (`django/urls/base.py:get_urlconf`, `django/core/handlers/base.py:reset_urlconf`).

One failure of the import is kept. A URLconf, or a module it imports, may call `reverse` before the root's import sets `"urlpatterns"`. That call goes to the same root resolver for its list, and the read of `URLResolver.urlconf_module` it makes, inside the import, calls `importlib.import_module`, which finds the module already in `sys.modules` and returns it: imported as far as the line that is running, with no `"urlpatterns"` yet. That read returns a value, and the property keeps it. `URLResolver.url_patterns` then has a module in place of a list, cannot iterate it, and raises `ImproperlyConfigured`; the exception ends the import, and the module leaves `sys.modules` but stays on the resolver (`django/urls/resolvers.py:URLResolver.urlconf_module`, `django/urls/resolvers.py:URLResolver.url_patterns`). The message guesses at a circular import, and does not name `reverse`:

```text recording=urls
ROOT_URLCONF = 'museum.urls_early', a URLconf that calls reverse() above its own urlpatterns
    resolve("/")  ->  raises ImproperlyConfigured: The included URLconf 'museum.urls_early' does not appear to have any patterns in it. If you see the 'urlpatterns' variable with valid patterns in the file then the issue is probably caused by a circular import.
    ...
```

Where `reverse` made the first read, the call inside the import finds `URLResolver._populate` already running on its thread and raises, keeping nothing (`django/urls/resolvers.py:URLResolver._populate`, `django/urls/resolvers.py:URLResolver.reverse_dict`).

> **Trap.** A URLconf that calls `reverse` so early fails for every request after the first as well: once the module is kept, every read of `url_patterns` raises the same `ImproperlyConfigured` without trying the import again (`django/urls/resolvers.py:URLResolver.url_patterns`). Code that runs at import time and needs a URL calls `reverse_lazy`, which returns at once and calls `reverse` only when its result is used as text ([Reversing a name](reversing.md#reverse_lazy)).
