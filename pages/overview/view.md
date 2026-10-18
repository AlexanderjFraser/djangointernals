---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The URL is resolved and the view is called

How `BaseHandler._get_response` turns a path into a call of a view: the resolver is made once and imports the URLconf on first use, a route pattern matches the path and converts its captures, and the view is called with what was captured.

The innermost layer of the chain is not a middleware but a method of the handler, `BaseHandler._get_response`. It does four things in order: resolve the path to a view, offer the view to the middleware's `process_view` hooks, call it, and check its result (`django/core/handlers/base.py:BaseHandler._get_response`). [The centre of the chain](../handlers/view.md) describes the method in full, including the branch for a template response, which this request does not take.

In the first request the URLconf is imported inside the resolver's first `resolve`, and the project's views module with it. Inside the pattern's `resolve`, `IntConverter.to_python` is where the captured year becomes a number. The match is a `ResolverMatch`, which carries the view and the arguments to call it with, and it is made twice, by the pattern and then by the resolver. Two steps stand between the match and the call of the view.

```text recording=overview
BaseHandler._get_response
  BaseHandler.resolve_request
    URLResolver.resolve('/entries/2026/')
      URLResolver.urlconf_module: the root URLconf is imported
        import journal.urls
          import journal.views
          path("entries/<int:year>/", by_year, name="entries-by-year")
      URLPattern.resolve('entries/2026/')
        RoutePattern.match('entries/2026/')
          IntConverter.to_python('2026')
        ResolverMatch(journal.views.by_year, kwargs={'year': 2026})
      ResolverMatch(journal.views.by_year, kwargs={'year': 2026})
  CsrfViewMiddleware.process_view
  BaseHandler.make_view_atomic
  journal.views.by_year(request, year=2026)
```

## One resolver per URLconf

`BaseHandler.resolve_request` asks `get_resolver` for the resolver of the current URLconf, which is `settings.ROOT_URLCONF` unless a middleware has set an attribute named `"urlconf"` on the request (`django/core/handlers/base.py:BaseHandler.resolve_request`). `get_resolver` is backed by a function wrapped in `functools.cache`, so one `URLResolver` is made for each URLconf a process ever resolves with, and kept (`django/urls/resolvers.py:get_resolver`, `django/urls/resolvers.py:_get_cached_resolver`). The root resolver's own pattern is the regular expression `"^/"`: it matches the leading slash, and hands what follows to its patterns.

Those patterns are a `cached_property`, `URLResolver.url_patterns`, and reading it for the first time reads another, `URLResolver.urlconf_module`, which imports the URLconf, here `settings.ROOT_URLCONF` (`django/urls/resolvers.py:URLResolver.url_patterns`, `django/urls/resolvers.py:URLResolver.urlconf_module`). That import is the moment in the recording where the project's own code first runs for a request. Importing the URLconf imports the views module, and each call of `path` in it makes a pattern object. The URLconf is imported once per process, here by the first request.

## What a `path` call makes

`path` and `re_path` are one function, `_path`, with the pattern class fixed to `RoutePattern` for the first and to `RegexPattern` for the second, so the two make the same objects around a different pattern (`django/urls/conf.py:_path`). For a view, `path` makes a `RoutePattern` from the route string and wraps it with the view in a `URLPattern`; for an `include`, it makes a `URLResolver` instead, which is how URLconfs nest ([From a URLconf to a tree](../urls/urlconf.md)).

A `RoutePattern` turns its route into a regular expression when it is made. `_route_to_regex` writes each parameter in angle brackets as a named group whose body is its converter's own regular expression, and for a view's pattern it anchors the end (`django/urls/resolvers.py:_route_to_regex`, `django/urls/converters.py:IntConverter`). The route `"entries/<int:year>/"` thus becomes the expression `"^entries/(?P<year>[0-9]+)/\Z"`, and the pattern remembers that the group `year` belongs to the `int` converter.

## Matching the path

`URLResolver.resolve` tries its patterns in the order of the list and returns at the first match (`django/urls/resolvers.py:URLResolver.resolve`). For a `URLPattern` that is `URLPattern.resolve`, which asks its pattern, here a `RoutePattern`, to match what is left of the path (`django/urls/resolvers.py:URLPattern.resolve`). For a route with parameters, `RoutePattern.match` runs the regular expression and passes each captured string to its converter's `to_python`. A converter that raises `ValueError` makes the pattern not match (`django/urls/resolvers.py:RoutePattern.match`). The converted captures are passed to the view as keyword arguments ([Routes, regular expressions and converters](../urls/patterns.md), [Resolving a path](../urls/resolving.md)).

A `ResolverMatch` holds the view, its positional and keyword arguments, the pattern's name, the route, and the namespaces on the way (`django/urls/resolvers.py:ResolverMatch.__init__`). The pattern makes it, and the resolver that found the pattern makes it again. The second puts the resolver's own application name and namespace before the pattern's, which is why each nested `include` with a namespace adds it. It also carries the patterns the resolver tried, up to and including the one that matched. When no pattern matches, the resolver raises `Resolver404`, which carries every pattern it tried. The `convert_exception_to_response` wrapper around the centre turns it into a 404 response, and, when `settings.DEBUG` is true, into the page that shows the patterns tried (`django/core/handlers/exception.py:response_for_exception`).

`resolve_request` keeps the match as `HttpRequest.resolver_match`, where the view and anything after it can read which pattern answered, and returns it; `_get_response` unpacks it into the three things it needs, the view, its positional arguments and its keyword arguments (`django/urls/resolvers.py:ResolverMatch.__getitem__`).

## Between the match and the call

With a view in hand, the handler runs the `process_view` hooks in the order of `settings.MIDDLEWARE` (`django/core/handlers/base.py:BaseHandler.load_middleware`). Of the project's seven middleware only `CsrfViewMiddleware` has one. It passes over a view marked exempt. For a `"GET"`, or any other method the HTTP specification calls safe, it accepts the request at once. For any other method it checks the origin if sent, or else on a secure request the referer, and then that the request's token matches the secret, by default from the cookie (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`). Each step of the check, and what answers a request it refuses, is [The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md).

> **Why.** The check waits for `process_view` because it needs the view. An exempt view is one that `csrf_exempt` has marked (`django/views/decorators/csrf.py:csrf_exempt`), and the middleware reads the mark off the view. `process_request` runs before the path is resolved and is handed only the request; `process_view` is handed the view, just before the view is called (`docs/topics/http/middleware.txt`).

`BaseHandler.make_view_atomic` then wraps the view in a transaction for each database whose settings have `"ATOMIC_REQUESTS"` true. A view marked with `non_atomic_requests` for a database is not wrapped for that one. No database has the setting by default, and the view is returned unchanged (`django/db/utils.py:ConnectionHandler.configure_settings`, `django/core/handlers/base.py:BaseHandler.make_view_atomic`). An asynchronous view would then be wrapped in `async_to_sync`, which runs it in an event loop on another thread and returns its response, because `_get_response` is synchronous and cannot await it (`django/core/handlers/base.py:BaseHandler._get_response`, `asgiref:asgiref/sync.py:AsyncToSync.__call__`). This one is an ordinary function, and it is called with the request and the keyword arguments the route captured: `year=2026`, an `int`, because the converter made it one.

## The view

A view is anything callable that takes a request and returns a response. The one in this chapter is a function of two lines: it asks the model's manager for a queryset, filtered and ordered, and it returns `render` of a template with that queryset in the context. [A queryset becomes SQL](query.md) follows the first line, and [The template is rendered](template.md) the second. A class-based view reaches the same point by another route: `View.as_view` returns a function for the URLconf, and that function makes an instance of the class for each request and dispatches on the method ([`View.as_view` and dispatch](../views/as-view.md)) (`django/views/generic/base.py:View.as_view`).

What the view returns is checked before anything else happens to it. `BaseHandler.check_response` raises `ValueError` for a view that returned `None`, with the message naming the view, and for a coroutine that was never awaited (`django/core/handlers/base.py:BaseHandler.check_response`). Here the response passes and leaves the centre, and the chain begins to unwind.
