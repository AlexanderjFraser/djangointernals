---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# When a URLconf is imported

The root URLconf, and with it every URLconf it includes, is imported by the first read of the root resolver's `URLResolver.urlconf_module`, a property that `URLResolver.url_patterns` reads on its way to the list, and whichever part of Django reads it first decides when a mistake in a URLconf comes to light. An import that raises ordinarily leaves nothing on the resolver and is tried again by the next reader, while a root URLconf that calls `reverse` as it is imported is kept half made and raises `ImproperlyConfigured` at every later read of its list, the failure `reverse_lazy` exists to avoid.

Making the root resolver imports nothing: `get_resolver` makes a `URLResolver` around the dotted name in `settings.ROOT_URLCONF`, and keeps it ([From a URLconf to a tree](urlconf.md#the-root-resolver)). The module is imported when something first asks the resolver for it, through `urlconf_module`, a property that keeps on the resolver the first value it computes; an import that raises computes none (`django/urls/resolvers.py:URLResolver.urlconf_module`). Several parts of Django can be the first to ask, at different moments of a process's life. The figure sets them in the order a process can meet them, each reading the one property, and beside it what the property keeps by how the import ends.

```text figure=first-read
the readers, in the order a process can meet them             the property                   how the import ends, and what the property keeps

a management command that runs the system checks, before its work
  check_url_config -> URLResolver.check -> url_patterns    ->                                  the module is imported
runserver's autoreloader, once the applications are ready                                       the module, kept: no later reader imports it
  BaseReloader.run                                          ->
a request                                                        URLResolver.urlconf_module    the import raises
  LocaleMiddleware.process_request -> url_patterns         ->    of the root resolver          nothing: the next reader imports it again
  URLResolver.resolve -> url_patterns                       ->
  URLResolver.resolve_error_handler, for an error view      ->                                 the URLconf calls reverse as it is imported
the first reverse, to build its tables                                                          the module as far as it was imported, kept, with no list:
  reverse -> url_patterns                                   ->                                   every later read of url_patterns raises ImproperlyConfigured
```

*Readers that can make the first read of a root resolver's `urlconf_module`, grouped by when a process meets them; each arrow from a reader is a read of the one property, made directly or through `url_patterns`. At the right, what the property keeps by how the import ended.*

## The first read

The first read of `URLResolver.urlconf_module` imports the root URLconf, and the import brings in every URLconf that an `include` in it names. `include` imports a module it is given by name before it returns, so each included module is imported in the middle of the root's own import, at the first `include` that names it, and an `include` that names a module already imported runs none of its code again (`django/urls/conf.py:include`). Asked for again, `get_resolver` returns the same resolver from its cache, with its list already on it, and nothing is imported or built a second time (`django/urls/resolvers.py:get_resolver`, `django/urls/resolvers.py:_get_cached_resolver`).

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

Which part of Django first reads a root resolver's URLconf decides when a mistake in the URLconf comes to light.

Under a production server it is the first request that needs the URLconf. `get_wsgi_application` loads the settings and the applications and makes the handler, and none of that touches the URLconf (`django/core/wsgi.py:get_wsgi_application`). `URLResolver.resolve` reads `URLResolver.url_patterns` for the first path that reaches it, unless something in the request has needed the URLconf sooner: `LocaleMiddleware.process_request` has `url_patterns` read to learn whether the URLconf has a language prefix ([Language prefixes and translated routes](i18n.md)), and when an exception raised in a middleware is to be answered by an error view, `URLResolver.resolve_error_handler` reads the URLconf's module to look for one (`django/conf/urls/i18n.py:is_language_prefix_patterns_used`, `django/urls/resolvers.py:URLResolver.resolve_error_handler`).

A management command that runs the system checks gets there earlier. The check `check_url_config` asks the root resolver to check itself, and `URLResolver.check` goes through `url_patterns` to do it, so a command such as runserver imports the whole tree before it does its work ([The URL checks, and listing the patterns](checks.md), [The system checks](../commands/checks.md)) (`django/core/checks/urls.py:check_url_config`, `django/urls/resolvers.py:URLResolver.check`). Under runserver the autoreloader reads `URLResolver.urlconf_module` as well, in `BaseReloader.run`, as soon as the applications are ready, so that the URL modules are already loaded when the reloader starts; if the import raises, it stores the exception and carries on ([The autoreloader](../commands/autoreload.md)) (`django/utils/autoreload.py:BaseReloader.run`).

The first call of `reverse` reads the list too, to build its tables ([Reversing a name](reversing.md#the-tables)) (`django/urls/resolvers.py:URLResolver._populate`).

## When the import fails

A URLconf that cannot be imported is not always one error. A property that raised has kept nothing, so the import is tried again by whatever reads it next, and in a request the next reader is ordinarily the code that is trying to report the failure. The second failure below comes from the handler's search for the 500 error view, which a URLconf may name, and the two lines at the end are what the request left behind.

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

The wrapper around the centre of the middleware chain, `convert_exception_to_response`, catches the first `ImportError`, and to answer it with a 500 asks `URLResolver.resolve_error_handler` for the error view, which reads the URLconf's module. The second `ImportError` is raised inside the wrapper's own handling of the first, and nothing in that wrapper catches it (`django/core/handlers/exception.py:convert_exception_to_response`, `django/core/handlers/exception.py:handle_uncaught_exception`). With no middleware in the chain it goes to the server. The wrapper around each middleware makes one more attempt: with one middleware installed, the wrapper around it catches the second `ImportError` and asks for the 500 error view again, and the third failure of the import is the one that reaches the server ([How an exception becomes a response](../handlers/exceptions.md#what-does-reach-the-server)).

The resolver still has no module, so the next request tries the import again. And the thread keeps the current URLconf the handler set for the request, since what clears it is the closing of a response, and there was none ([The script prefix, the current URLconf and the caches](state.md#the-current-urlconf)) (`django/core/handlers/base.py:reset_urlconf`).

Turning `settings.DEBUG` on does not rescue the request. The debug page is made without any error view, but it names the view that was handling the request, and for a request that has no match yet it resolves the path to find out, so the import is tried a second time inside the code that builds the page ([The debug pages and `ExceptionReporter`](../views/debug.md)) (`django/views/debug.py:get_caller`).

One failure of the import is kept. A URLconf, or a module it imports, may call `reverse` while it is being imported, for a constant or a default argument. That call goes to the same root resolver for its list, and the read of `URLResolver.urlconf_module` it makes, inside the import, is handed the module as it stands in `sys.modules`: imported as far as the line that is running, with no `"urlpatterns"` yet. That read returns a value, and the property keeps it. `URLResolver.url_patterns` then has a module in place of a list, cannot iterate it, and raises `ImproperlyConfigured`; the exception ends the import, and the module leaves `sys.modules` but stays on the resolver (`django/urls/resolvers.py:URLResolver.urlconf_module`, `django/urls/resolvers.py:URLResolver.url_patterns`). The message guesses at a circular import, and does not name `reverse`:

```text recording=urls
ROOT_URLCONF = 'museum.urls_early', a URLconf that calls reverse() above its own urlpatterns
    resolve("/")  ->  raises ImproperlyConfigured: The included URLconf 'museum.urls_early' does not appear to have any patterns in it. If you see the 'urlpatterns' variable with valid patterns in the file then the issue is probably caused by a circular import.
    ...
```

> **Trap.** A URLconf that calls `reverse` while it is imported fails for every request after the first as well. The resolver keeps the half-made module, so every later read of `url_patterns`, for a path or for `reverse`, raises the same `ImproperlyConfigured` without trying the import again (`django/urls/resolvers.py:URLResolver.url_patterns`). Code that runs at import time and needs a URL calls `reverse_lazy`, which returns at once and calls `reverse` only when its result is used as text ([Reversing a name](reversing.md#reverse_lazy)).
