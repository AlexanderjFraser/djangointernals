---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The URL is resolved and the view is called

How `BaseHandler._get_response` turns a path into a call of a view: the resolver is made once and imports the URLconf on first use, a route pattern matches the path and converts its captures, and the view is called with what was captured.

The innermost layer of the chain is not a middleware but a method of the handler, `BaseHandler._get_response`. It does four things in order: resolve the path to a view, offer the view to the view middleware, call it, and refuse what is not a response (`django/core/handlers/base.py:BaseHandler._get_response`). [The centre of the chain](../handlers/view.md) describes the method in full, including the branch for a template response that has not been rendered, which this request does not take. This is the recording's first request, where the resolver's first use shows:

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

## One resolver per process

`BaseHandler.resolve_request` asks `get_resolver` for the resolver of the current URLconf, which is `settings.ROOT_URLCONF` unless a middleware has set an attribute named `"urlconf"` on the request (`django/core/handlers/base.py:BaseHandler.resolve_request`). `get_resolver` is backed by a function wrapped in `functools.cache`, so one `URLResolver` is made for each URLconf a process ever resolves with, and kept (`django/urls/resolvers.py:get_resolver`, `django/urls/resolvers.py:_get_cached_resolver`). The root resolver's own pattern is the regular expression `"^/"`: it matches the leading slash, and hands what follows to its patterns.

Those patterns are a `cached_property`, `URLResolver.url_patterns`, and reading it for the first time reads another, `URLResolver.urlconf_module`, which imports the module `settings.ROOT_URLCONF` names (`django/urls/resolvers.py:URLResolver.url_patterns`, `django/urls/resolvers.py:URLResolver.urlconf_module`). That import is the moment in the recording where the project's own code first runs for a request: importing the URLconf imports the views module, and each call of `path` in it makes a pattern object. The URLconf is imported once per process, here by the first request, and under the development server earlier, by the system checks ([Before the first request](startup.md)).

## What a `path` call makes

`path` is `_path` with the pattern class fixed to `RoutePattern` (`django/urls/conf.py:_path`). For a view, it makes a `RoutePattern` from the route string and wraps it with the view in a `URLPattern`; for an `include`, it makes a `URLResolver` instead, which is how URLconfs nest ([From a URLconf to a tree](../urls/urlconf.md)).

A `RoutePattern` turns its route into a regular expression when it is made. `_route_to_regex` walks the route for angle-bracketed parameters, and for each one looks up the converter named before the colon, `int` here, in the registered converters, escapes the literal text between parameters, and writes the parameter as a named group whose body is the converter's own regular expression; for a view's pattern it anchors the end (`django/urls/resolvers.py:_route_to_regex`, `django/urls/converters.py:IntConverter`). The route `"entries/<int:year>/"` thus becomes the expression `"^entries/(?P<year>[0-9]+)/\Z"`, and the pattern remembers that the group `year` belongs to the `int` converter.

## Matching the path

`URLResolver.resolve` tries its patterns in the order of the list and returns at the first match (`django/urls/resolvers.py:URLResolver.resolve`). For a `URLPattern` that is `URLPattern.resolve`, which asks its `RoutePattern` to match what is left of the path (`django/urls/resolvers.py:URLPattern.resolve`). `RoutePattern.match` has a fast path for a route with no parameters, a string comparison; with parameters it runs the regular expression, and passes each captured string to its converter's `to_python`. A converter that raises `ValueError` makes the pattern not match, which is how a route with `<int:year>` declines a path whose year is not a number (`django/urls/resolvers.py:RoutePattern.match`). The converted captures are the view's keyword arguments ([Routes, regular expressions and converters](../urls/patterns.md), [Resolving a path](../urls/resolving.md)).

A match is a `ResolverMatch`: the view, its positional and keyword arguments, the pattern's name, the route, and the namespaces on the way (`django/urls/resolvers.py:ResolverMatch.__init__`). The recording shows it made twice. The pattern makes it, and the resolver that found the pattern makes it again with its own application name and namespace put before the pattern's and the list of patterns tried, which is why a nested `include` adds a namespace at each level. When no pattern matches, the resolver raises `Resolver404` with that list of what was tried, which becomes a 404 response at the wrapper around the centre, and when `settings.DEBUG` is true the page that shows the patterns tried.

`resolve_request` keeps the match as `HttpRequest.resolver_match`, where the view and anything after it can read which pattern answered, and returns it; `_get_response` unpacks it into the three things it needs, the view, its positional arguments and its keyword arguments (`django/urls/resolvers.py:ResolverMatch.__getitem__`).

## Between the match and the call

With a view in hand, the handler runs the `process_view` hooks in the order of `settings.MIDDLEWARE`. Of the seven default middleware only `CsrfViewMiddleware` has one. For a `GET`, or any other method the HTTP specification calls safe, it accepts the request at once; for any other method it checks the origin or the referer, and then that the token sent with the request matches the secret from the cookie (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`). A view marked exempt is passed over, and this is the reason the check lives in `process_view` and not in `process_request`: the view has to be known.

`BaseHandler.make_view_atomic` then wraps the view in a transaction for each database whose settings have `"ATOMIC_REQUESTS"` true; none has by default, and the view is returned unchanged (`django/core/handlers/base.py:BaseHandler.make_view_atomic`). An asynchronous view would be wrapped so that it can be called as a function. This one is an ordinary function, and it is called with the request and the keyword arguments the route captured: `year=2026`, an `int`, because the converter made it one.

## The view

A view is anything callable that takes a request and returns a response. The one in this chapter is a function of two lines, and they are the two things most views do: it asks the model's manager for a queryset, filtered and ordered, and it returns `render` of a template with that queryset in the context. [A queryset becomes SQL](query.md) follows the first line, and [The template is rendered](template.md) the second. A class-based view reaches the same point by another route: `View.as_view` returns a function for the URLconf, and that function makes an instance of the class for each request and dispatches on the method ([`View.as_view` and dispatch](../views/as-view.md)).

What the view returns is checked before anything else happens to it. `BaseHandler.check_response` raises `ValueError` for a view that returned `None`, with the message naming the view, and for a coroutine that was never awaited (`django/core/handlers/base.py:BaseHandler.check_response`). A response that passes leaves the centre, and the chain begins to unwind.
