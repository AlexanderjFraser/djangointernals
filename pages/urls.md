---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: urlconf, import, patterns, resolving, reversing, namespaces, i18n, checks, state
---

# URL routing

The URL resolver answers two questions from one description of a site's addresses: which view serves this path, and which path leads to this view. The URLconf that `ROOT_URLCONF` names is made, by its calls of `path` and `include`, into a tree of `URLResolver` objects and the patterns under them; `URLResolver.resolve` walks the tree to turn a path into a `ResolverMatch`, or raises `Resolver404`, and `reverse` turns a pattern's name and arguments back into a path, or raises `NoReverseMatch`.

A site has to know its own addresses in two directions. A request arrives carrying a path, `"/east/rooms/12/"`, and something must decide which function answers it and which parts of the path that function is handed as arguments. And nearly every page the site sends holds links to its other pages. If each link were written out as text, no address could change without every link to it being found and changed as well. So the addresses are described once, in a module called a **URLconf**, and Django reads the description both ways. **Resolving** goes from a path to a view and its arguments. **Reversing** goes from a name given to one of the addresses, with a value for each of its parameters, to a path.

## A tree of resolvers and patterns

A URLconf is a module with a list in it, bound to the name `"urlpatterns"`, or such a list by itself. The **entries** of the list are ordinarily made by calls of `path` and `re_path`, and what a call makes depends on what it is given. Given a view, it makes a **`URLPattern`**, the **pattern** of this chapter: a leaf, holding the view and the name it was given. Given what `include` returns, it makes a **`URLResolver`**, a **resolver**: a branch, holding the list of another URLconf, whose entries all share the beginning of their addresses. Either may be given a dictionary of **extra arguments** as well, for the views it leads to. Over the whole stands one more resolver, the **root resolver**, whose list is the root URLconf's (`django/urls/conf.py:_path`, `django/urls/resolvers.py:URLPattern`, `django/urls/resolvers.py:URLResolver`).

Neither class matches a path itself. Each entry holds, as its `pattern`, a third kind of object that does, which this chapter calls its **matcher**: a `RoutePattern` for a route written in the syntax of `path`, with its parameters in angle brackets, or a `RegexPattern` for a regular expression. A route has to account for what is left of the path down to its end when it belongs to a pattern, and only for the beginning of it when it belongs to a resolver; a regular expression is matched by rules of its own. The root resolver's own matcher is a `RegexPattern` that takes the slash every path begins with, and a third class of matcher, for a language at the front of a path, comes with `i18n_patterns`. A parameter of a route may name a **converter**, the `int` of `<int:room>`, which supplies the regular expression for that part of the path and turns the text it matches into a value; a parameter that names none gets `str` ([Routes, regular expressions and converters](urls/patterns.md)) (`django/urls/resolvers.py:RoutePattern`, `django/urls/resolvers.py:RegexPattern`, `django/urls/converters.py:IntConverter`).

The examples of this chapter are the addresses of a museum's site, and here are the root URLconf that `ROOT_URLCONF` names and the URLconf of the museum's galleries. Look in them for the gallery's module included twice, once for each of the museum's two wings, each time with a namespace and a dictionary of extra arguments; a converter of the project's own; and one address written as a regular expression.

```python
# museum/urls.py
register_converter(converters.MonthConverter, "month")

shop_patterns = [
    path("", views.shop, name="shop"),
    path("<slug:item>/", views.item, name="item"),
]

urlpatterns = [
    path("", views.entrance, name="entrance"),
    path("tickets/<int:year>/", views.tickets, name="tickets"),
    path("tickets/<int:year>/<month:month>/", views.tickets, name="tickets"),
    path("east/", include("museum.gallery.urls", namespace="east"), {"wing": "east"}),
    path("west/", include("museum.gallery.urls", namespace="west"), {"wing": "west"}),
    path("shop/", include(shop_patterns)),
    re_path(r"^plans/(?P<floor>[0-9])(?:\.(?P<format>pdf|svg))?$", views.plan, name="plan"),
    path("files/<path:name>", views.download, name="download"),
]

# museum/gallery/urls.py
app_name = "gallery"

audio_patterns = [
    path("<slug:track>/", views.track, name="track"),
]

urlpatterns = [
    path("", views.wing, name="wing"),
    path("rooms/<int:room>/", views.room, name="room"),
    path("rooms/<int:room>/audio/", include((audio_patterns, "audio"))),
]
```

The extra argument wing tells the gallery's views which wing they are serving. A name such as room would be ambiguous between the two wings, so the gallery's module declares an **application namespace**, gallery, and each inclusion is given an **instance namespace**, east or west; a name is then written with one of them in front, `"east:room"` ([Namespaces](urls/namespaces.md)). The converter `month`, for a month written as two digits, is the project's own, registered above its patterns.

The figure draws the tree Django makes of the two modules. Look at the resolvers of the two wings, which hold one list between them, and at the accented path: `"/east/rooms/12/"`, taken a part at a time on its way down to the pattern that serves it.

```text figure=the-tree
the root resolver: its matcher ^/, its list the urlpatterns of museum.urls
  ""                                                       a pattern: entrance
  tickets/<int:year>/                                      a pattern: tickets
  tickets/<int:year>/<month:month>/                        a pattern: tickets
  east/       a resolver: namespace east, wing="east"      ->  the urlpatterns of museum.gallery.urls
  west/       a resolver: namespace west, wing="west"      ->  the same list
  shop/       a resolver                                   ->  shop_patterns
  ^plans/(?P<floor>[0-9])(?:\.(?P<format>pdf|svg))?$       a pattern: plan, written as a regular expression
  files/<path:name>                                        a pattern: download

the urlpatterns of museum.gallery.urls, application namespace gallery
  ""                          a pattern: wing
  rooms/<int:room>/           a pattern: room
  rooms/<int:room>/audio/     a resolver                    ->  audio_patterns

shop_patterns
  ""                          a pattern: shop
  <slug:item>/                a pattern: item

audio_patterns
  <slug:track>/               a pattern: track

the path /east/rooms/12/, accented:
  the root's matcher takes /            east/rooms/12/ is left
  the resolver east/ takes east/        rooms/12/ is left
  the pattern rooms/<int:room>/ takes all of rooms/12/, and room is 12
  the view room is called with wing="east", room=12

each list is tried from the top, and the first entry that matches is taken
```

*The museum's two URLconfs as the tree Django makes of them: each resolver points to the list it holds, and the two wings' resolvers point to the same one. The accent follows one path: each resolver takes the part of it that its own matcher accepts and offers the rest to its list, from the top.*

The tree is made when it is first needed, and kept. `get_resolver` makes the root resolver the first time it is asked for one, and the root resolver imports the URLconf the first time something reads its list or its module, which under a production server happens during the first request that needs either. Importing the module runs the calls that build everything under the root ([From a URLconf to a tree](urls/urlconf.md), [When a URLconf is imported](urls/import.md)) (`django/urls/resolvers.py:_get_cached_resolver`, `django/urls/resolvers.py:URLResolver.urlconf_module`).

## A path is resolved

At the centre of the middleware chain, `BaseHandler.resolve_request` asks `get_resolver` for the root resolver and calls `URLResolver.resolve` on it with the request's `path_info` (`django/core/handlers/base.py:BaseHandler.resolve_request`). What follows is the walk the figure draws. Each resolver lets its own matcher take its part of the path and offers the rest to its entries in the order they are written, and the first entry to match ends the search: where two patterns could match one path, the one written first serves it. A resolver none of whose entries matches does not end it, and the search goes on with the next entry of the list above. The match is assembled on the way back up. The pattern makes a `ResolverMatch` holding the view and the arguments its route captured, here the room, which the `int` converter turned from the text `"12"` into a number, and each resolver above it makes a new one from that, adding its namespace and its extra arguments, here the wing. `resolve_request` keeps the last as `HttpRequest.resolver_match`, and the handler calls the view with the arguments in it (`django/urls/resolvers.py:URLResolver.resolve`, `django/urls/resolvers.py:URLPattern.resolve`).

When no entry matches, the root resolver raises `Resolver404`. That is a subclass of `Http404`, so the wrapper around the centre of the chain turns it into a 404 response as it would any other ([Resolving a path](urls/resolving.md)).

## A name is reversed

`reverse` goes the other way: given the name `"tickets"` and a year and a month, it returns the path that the pattern of that name would match. It does not search the tree. The first time a root resolver is asked to reverse, `URLResolver._populate` reads the tree into tables. The root resolver goes through its entries from the last to the first, each resolver among them going through its own as it is reached, and files a **candidate** for each pattern under the pattern's view and, when it has one, its name. The candidates of a plain include are lifted into the table above it with the include's route in front; a resolver with an application namespace keeps a table of its own, and `reverse` goes from namespace to namespace before it looks the name up ([Reversing a name](urls/reversing.md), [Namespaces](urls/namespaces.md)) (`django/urls/resolvers.py:URLResolver._populate`). The first call of `reverse` with the museum's URLconf runs `_populate` on every resolver of the tree, the last written first; the same call made again goes from `_reverse_with_prefix` straight to the converters.

```text recording=urls
reverse(): the first call for a URLconf fills its resolvers' tables, and each call reads them
    the script calls reverse("tickets", kwargs={"year": 2026, "month": 3})
      reverse('tickets', kwargs={'year': 2026, 'month': 3})
        get_resolver()
        URLResolver._reverse_with_prefix('tickets', '/', year=2026, month=3)  (the root resolver)
          URLResolver._populate  (the root resolver)
            URLResolver._populate  ('shop/')
            URLResolver._populate  ('west/')
              URLResolver._populate  ('rooms/<int:room>/audio/')
            URLResolver._populate  ('east/')
              URLResolver._populate  ('rooms/<int:room>/audio/')
...
    and calls it again
      reverse('tickets', kwargs={'year': 2026, 'month': 3})
        get_resolver()
        URLResolver._reverse_with_prefix('tickets', '/', year=2026, month=3)  (the root resolver)
          IntConverter.to_url(2026)  ->  '2026'
          MonthConverter.to_url(3)  ->  '03'
          -> '/tickets/2026/03/'
          ...
```

At the heart of a candidate is ordinarily one string with a gap where each parameter goes, `"tickets/%(year)s/%(month)s/"`, which `normalize` makes from the pattern's regular expression; beside it are the names of its parameters, the expression itself, the pattern's extra arguments and its converters (`django/utils/regex_helper.py:normalize`). With the tables there, a reverse is a lookup followed by a test. `URLResolver._reverse_with_prefix` takes the candidates filed under the name and passes over any whose parameters do not fit the arguments it was given. It turns each argument into text, with its converter's `to_url` where the parameter has a converter, fills the gaps, and checks that the pattern's own expression matches the result. The first candidate to pass gives the answer: its filled-in string, with anything unsafe in a URL escaped and, in front of it, the **script prefix**, the part of a site's addresses that belongs to wherever a server has mounted it, which is a bare slash when the site stands at the root of its host. If no candidate passes, it raises `NoReverseMatch` (`django/urls/base.py:reverse`, `django/urls/resolvers.py:URLResolver._reverse_with_prefix`). The tables hold the last entry first, so where two patterns of one name both pass, `reverse` gives the one written last, while a path that two patterns both match is resolved by the one written first.

So a route with parameters is kept twice over, as a regular expression to resolve with and as a string to reverse with, and each of its converters works in both directions. The figure follows one of the museum's routes through both.

```text figure=two-readings
the route, as written in the URLconf        tickets/<int:year>/<month:month>/
    _route_to_regex, when the URLconf is imported
to resolve a path                           ^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\Z
                                            each parameter is a named group, holding its converter's expression
    tickets/2026/03/   ->   "2026", "03"   ->   to_python   ->   year=2026, month=3
    normalize, when a name is first reversed
to reverse a name                           tickets/%(year)s/%(month)s/
                                            each parameter is a gap to fill in: year, month
    tickets/2026/03/   <-   "2026", "03"   <-   to_url   <-   year=2026, month=3
```

*One route as Django keeps it for each direction. Resolving matches the regular expression and passes each captured piece of text through its converter's `to_python`; reversing passes each argument through `to_url` and fills in the string. The slash in front of every path is left out: when a path is resolved the root resolver takes it off first, and when a name is reversed the script prefix supplies it.*

## What is kept, and for whom

The tree and its tables belong to the process. `get_resolver` keeps each root resolver it makes until something calls `clear_url_caches`, and the tables are kept per language, because a route can be a translated string and a language can stand at the front of a path ([Language prefixes and translated routes](urls/i18n.md)). Two values belong to the thread, or under ASGI the task, that serves a request. The handler sets the script prefix for each request, and `BaseHandler.get_response`, or its asynchronous twin, makes `ROOT_URLCONF` the **current URLconf**, the one that `resolve` and `reverse` use when they are given none. A middleware that sets an attribute named `"urlconf"` on the request gives it a URLconf of its own, which becomes the current one when the request is resolved ([The script prefix, the current URLconf and the caches](urls/state.md)) (`django/urls/resolvers.py:_get_cached_resolver`, `django/core/handlers/base.py:BaseHandler.get_response`).

## The neighbours

The handler calls the resolver for every request that reaches the centre of the middleware chain, and what becomes of a `Resolver404` is decided there ([Handlers and middleware](handlers.md)). The path that is resolved, `path_info`, is made with the request ([Requests and responses](http.md)). What is found is a view: [Views](views.md) has what a view is, how a class becomes one through `View.as_view`, and the shortcuts that reverse on a view's behalf, `redirect` among them. In a template the tag `{% url %}` calls `reverse` ([The built-in tags](templates/tags.md)).

The handler is not the resolver's only caller. `CommonMiddleware`, handed a 404, may ask it about the path as it came and with a slash added, and redirect to the second ([The general-purpose middleware](handlers/general.md)), and `LocaleMiddleware` asks whether the URLconf puts a language in front of its paths ([Choosing a language: `LocaleMiddleware`](i18n/choosing.md)). The system checks and the command listurls go over the whole tree ([The URL checks, and listing the patterns](urls/checks.md)). The admin's URLs, its own pages' and those of every model registered with it, stand under the application namespace `"admin"` ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](admin/site-urls.md)). And when a test overrides `ROOT_URLCONF`, the root resolvers `get_resolver` keeps are dropped as the setting changes ([Overriding settings](startup/overrides.md#the-receivers-of-setting_changed)).
