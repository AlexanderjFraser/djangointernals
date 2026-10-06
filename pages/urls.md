---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: urlconf, patterns, resolving, reversing, namespaces, i18n, checks, state
---

# URL routing

The URL resolver answers two questions from one description of a site's addresses: which view serves this path, and which path leads to this view. A URLconf's calls of `path` and `include` build a tree of `URLResolver` objects and the patterns under them; `URLResolver.resolve` walks the tree to turn a path into a `ResolverMatch`, and `reverse` turns a pattern's name and arguments back into a path.

A site has to know its own addresses in two directions. A request arrives carrying a path, `"/east/rooms/12/"`, and something must decide which function answers it and which parts of the path that function is handed as arguments. And nearly every page the site sends holds links to its other pages. If each link were written out as text, no address could change without every link to it being found and changed as well. So the addresses are described once, in a module called a **URLconf**, and Django reads the description both ways. **Resolving** goes from a path to a view and its arguments. **Reversing** goes from a name given to one of the addresses, with a value for each of its parameters, to a path.

The examples of this chapter are the addresses of a museum's site. Its root URLconf is the module that the setting `ROOT_URLCONF` names. Everything recorded below was recorded from a running Django with these two modules.

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

A few things in it are less common than the rest, and each comes back later. The museum has two wings, and one module of addresses serves both: the root URLconf includes the gallery's module twice, and after each inclusion it writes a dictionary of **extra arguments**, which the gallery's views are called with besides what the path gives them, and which here tells them which wing they are in. A name such as room would then be ambiguous, so the gallery's module declares an **application namespace**, gallery, and each inclusion is given an **instance namespace**, east or west; a name is written with one of them in front, `"east:room"`. The converter `month`, for a month written as two digits, is the project's own, registered in the first line. And one address is written as a regular expression where the others are routes.

## A tree of resolvers and patterns

A URLconf is a module with a list in it, bound to the name `"urlpatterns"`, or such a list by itself. The **entries** of the list are made by calls of `path` and `re_path`, and what a call makes depends on what it is given. Given a view, it makes a **`URLPattern`**, the **pattern** of this chapter: a leaf, holding the view, any extra arguments for the view, and a name. Given what `include` returns, it makes a **`URLResolver`**, a **resolver**: a branch, holding the list of another URLconf, whose entries all share the beginning of their addresses. Over the whole stands one more resolver, the **root resolver**, whose list is the root URLconf's (`django/urls/conf.py:_path`, `django/urls/resolvers.py:URLPattern`, `django/urls/resolvers.py:URLResolver`).

Neither class matches a path itself. Each entry holds, as its `pattern`, a third kind of object that does, which this chapter calls its **matcher**: a `RoutePattern` for a route written in the syntax of `path`, with its parameters in angle brackets, or a `RegexPattern` for a regular expression. A route has to account for what is left of the path down to its end when it belongs to a pattern, and only for the beginning of it when it belongs to a resolver; a regular expression is matched by rules of its own ([Routes, regular expressions and converters](urls/patterns.md#regexpattern)). The root resolver's own matcher is a `RegexPattern` that takes the slash every path begins with. A third class of matcher, for a language at the front of a path, comes with `i18n_patterns`. A parameter of a route may name a **converter**, the `int` of `<int:room>`, which supplies the regular expression for that part of the path and turns the text it matches into a value; a parameter that names none gets `str` (`django/urls/resolvers.py:RoutePattern`, `django/urls/resolvers.py:RegexPattern`, `django/urls/converters.py:IntConverter`).

```text figure=the-tree
what is left of the path     what takes the front of it
/east/rooms/12/              the root resolver's own matcher takes the slash
east/rooms/12/               the resolver east/ takes east/
rooms/12/                    the pattern rooms/<int:room>/ takes all of it, and room is 12

URLResolver ^/   urlpatterns of museum.urls            urlpatterns of museum.gallery.urls
  ""                                   entrance           ""                        wing
  tickets/<int:year>/                  tickets            rooms/<int:room>/         room     <- matches
  tickets/<int:year>/<month:month>/    tickets            rooms/<int:room>/audio/   a resolver of one pattern
  east/    a resolver: namespace east, wing="east"   ---> that list
  west/    a resolver: namespace west, wing="west"   ---> the same list
  shop/    a resolver of two patterns
  ^plans/(?P<floor>[0-9])(?:\.(?P<format>pdf|svg))?$   plan, a regular expression
  files/<path:name>                    download

each list is tried from the top, and the first entry that matches is taken
the word at the right of a pattern is its name
the result: the view room is called with wing="east", room=12
```

*The museum's URLconf as the tree Django makes of it, and one path's way through it. Each resolver takes the part of the path its own matcher accepts and offers the rest to its list, from the top; the two resolvers for the wings hold the same list.*

The tree is made when it is first needed, and kept. `get_resolver` makes the root resolver the first time it is asked for one, and the root resolver imports the URLconf the first time something reads its list or its module, which under a production server happens during the first request that needs either. Importing the module runs its calls of `path` and `include`, and those calls are what build everything under the root ([From a URLconf to a tree](urls/urlconf.md), [Routes, regular expressions and converters](urls/patterns.md)).

## A path is resolved

This was recorded as a `WSGIHandler` served `GET /east/rooms/12/`. Each line is a call, indented under the call during which it was made, or, after an arrow, what a call returned. The parenthesis after a call says what it was called on: the root resolver, or an entry, named by its route. A matcher's `match` returns `None` or three things, what is left of the text and the positional and keyword arguments it captured, and its call is written down here only where it matched.

```text recording=urls
GET /east/rooms/12/: the path is resolved, entry by entry, and the view is called
    BaseHandler.resolve_request
      get_resolver()
      URLResolver.resolve('/east/rooms/12/')  (the root resolver)
        RegexPattern.match('/east/rooms/12/')  ->  ('east/rooms/12/', (), {})
        URLPattern.resolve('east/rooms/12/')  ('')  ->  None
        URLPattern.resolve('east/rooms/12/')  ('tickets/<int:year>/')  ->  None
        URLPattern.resolve('east/rooms/12/')  ('tickets/<int:year>/<month:month>/')  ->  None
        URLResolver.resolve('east/rooms/12/')  ('east/')
          RoutePattern.match('east/rooms/12/')  ->  ('rooms/12/', (), {})
          URLPattern.resolve('rooms/12/')  ('')  ->  None
          URLPattern.resolve('rooms/12/')  ('rooms/<int:room>/')
            RoutePattern.match('rooms/12/')
              IntConverter.to_python('12')  ->  12
              -> ('', (), {'room': 12})
            -> ResolverMatch(views.room, kwargs={'room': 12}, namespaces=[], route='rooms/<int:room>/')
          -> ResolverMatch(views.room, kwargs={'wing': 'east', 'room': 12}, namespaces=['east'], route='rooms/<int:room>/')
        -> ResolverMatch(views.room, kwargs={'wing': 'east', 'room': 12}, namespaces=['east'], route='east/rooms/<int:room>/')
    views.room(request, wing='east', room=12)
```

The handler does little of this. At the centre of the middleware chain, `BaseHandler.resolve_request` asks `get_resolver` for the root resolver and calls `URLResolver.resolve` on it with the request's `path_info` (`django/core/handlers/base.py:BaseHandler.resolve_request`). Everything under that call is the tree at work.

**Each resolver takes its own part of the path and passes on the rest.** The root's matcher took the leading slash and left `"east/rooms/12/"`. The resolver for the east wing took `"east/"` and left `"rooms/12/"`. A resolver's route has only to match the beginning of what it is given. A pattern's route has to match all of it: the route `""` did not match `"rooms/12/"`, though every string begins with the empty one.

**The search goes in the order of the lists and stops at the first match.** The root offered what was left to its entries from the top. The first three returned `None`. The fourth, a resolver, searched its own list in the same way before the root looked any further, and found a match, so the entries after it were never asked. Where two patterns could match one path, the one written first in `"urlpatterns"` serves it. If the east wing's list had held no match, the search would not have ended there: the root would have gone on to its fifth entry.

**The match is assembled on the way back up.** The pattern for a room made a `ResolverMatch` holding the view and the one argument its route had captured, the room, which the `int` converter had turned from the text `"12"` into a number. The east wing's resolver made a new match from that one, adding its namespace and the extra argument given where it was included, the wing. The root made a third, the first whose route begins with `"east/"`: a resolver puts in front the route of the resolver under it that matched, never its own. `resolve_request` keeps the result on the request as `HttpRequest.resolver_match`, and the handler calls the view with the arguments in it (`django/urls/resolvers.py:URLResolver.resolve`, `django/urls/resolvers.py:URLPattern.resolve`).

When no entry matches, the root resolver raises `Resolver404`. That is a subclass of `Http404`, so the wrapper around the centre of the chain turns it into a 404 response as it would any other ([Resolving a path](urls/resolving.md)).

## A name is reversed

`reverse` goes the other way: given the name `"tickets"` and a year and a month, it returns the path that the pattern of that name would match. It does not search the tree to do it. Here the recording's script calls `reverse` for the first time with the museum's URLconf, and then makes the same call again. The `'/'` passed to `URLResolver._reverse_with_prefix` is the script prefix, which the text below the recording comes to.

```text recording=urls
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
      IntConverter.to_url(2026)  ->  '2026'
      MonthConverter.to_url(3)  ->  '03'
      -> '/tickets/2026/03/'
    -> '/tickets/2026/03/'
and calls it again
  reverse('tickets', kwargs={'year': 2026, 'month': 3})
    get_resolver()
    URLResolver._reverse_with_prefix('tickets', '/', year=2026, month=3)  (the root resolver)
      IntConverter.to_url(2026)  ->  '2026'
      MonthConverter.to_url(3)  ->  '03'
      -> '/tickets/2026/03/'
    -> '/tickets/2026/03/'
```

The first call found nothing to look the name up in, and `URLResolver._populate` built it: the root resolver read its entries into a table, last entry first, having told each resolver among them to do the same. The table is keyed by a pattern's view and, when it has one, by its name. Under each key it holds one **candidate** for each pattern. At the heart of a candidate is a string with a gap where each parameter goes, `"tickets/%(year)s/%(month)s/"`, which `normalize` makes from the pattern's regular expression in one pass over it; an expression with an optional part can give more than one such string. Beside each string are the names of its parameters, and beside those the regular expression itself, the pattern's extra arguments, and its converters (`django/urls/resolvers.py:URLResolver._populate`, `django/utils/regex_helper.py:normalize`).

With the table there, a reverse is a lookup followed by a test, and the second call in the recording is the whole of it. `URLResolver._reverse_with_prefix` takes the candidates filed under the name, of which `"tickets"` has two because two patterns share it, and passes over any whose parameters do not fit the arguments it was given. It turns each argument into text, with its converter's `to_url` where the parameter has a converter, fills the gaps, and checks that the pattern's own regular expression matches the result. The first candidate to pass gives the answer: its filled-in string, with anything unsafe in a URL escaped and, in front of it, the **script prefix**: the part of a site's addresses that belongs to wherever a server has mounted it, which is a bare slash when the site stands at the root of its host. If no candidate passes, it raises `NoReverseMatch` (`django/urls/base.py:reverse`, `django/urls/resolvers.py:URLResolver._reverse_with_prefix`).

So a route with parameters is kept twice over, as a regular expression to resolve with and as a string to reverse with, and a converter works in both directions. A route with no parameters is compared as text when a path is resolved.

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

A resolver that has an application namespace, as the museum's two wings have, is not read into the table of the resolver above it. It keeps a table of its own, and `reverse` goes from namespace to namespace before it looks the name up ([Reversing a name](urls/reversing.md), [Namespaces](urls/namespaces.md)).

## What is kept, and for whom

The tree and its tables belong to the process. `get_resolver` makes one root resolver for each value it is given, which for the root URLconf is the dotted name in the setting, and keeps it until the process ends, unless something calls `clear_url_caches`, which within Django only the test framework does. The tables are filled by the first reverse, once for each language in which something is reversed, because a route can be a translated string and a language can stand at the front of a path ([Language prefixes and translated routes](urls/i18n.md)).

Other state belongs to the thread, or under ASGI the task, that is serving a request. `WSGIHandler` and `ASGIHandler` set the script prefix as each request arrives. `BaseHandler.get_response`, or its asynchronous twin, then makes `ROOT_URLCONF` the **current URLconf**, the one that `resolve` and `reverse` use when they are given none. If a middleware has set an attribute named `"urlconf"` on the request, that URLconf takes its place at the moment the request is resolved, so that a `reverse` in the view, given no URLconf, uses the one the request was resolved with ([The script prefix, the current URLconf and the caches](urls/state.md)).

## The neighbours

The handler calls the resolver for every request that reaches the centre of the middleware chain, and what becomes of a `Resolver404` is decided there ([Handlers and middleware](handlers.md)). The path that is resolved, `path_info`, is made with the request ([Requests and responses](http.md)). What is found is a view: [Views](views.md) has what a view is, how a class becomes one through `View.as_view`, and the shortcuts that reverse on a view's behalf, `redirect` among them. In a template the tag `{% url %}` calls `reverse` ([Templates](templates.md)).

The resolver is asked by more than the handler. `CommonMiddleware` resolves a path again, with a slash added, before it redirects a request that matched nothing; `LocaleMiddleware` asks whether the URLconf puts a language in front of its paths ([Internationalization and time zones](i18n.md)). The system checks go over the whole tree when a management command runs them, the development server's among them, and the command listurls prints the tree from the root URLconf's own list ([The URL checks, and listing the patterns](urls/checks.md), [Management commands](commands.md)). The admin relies on namespaces: an `AdminSite` hands `path` the URLs of every model it has registered, under the application namespace `"admin"` ([The admin](admin.md)). And a test that overrides `ROOT_URLCONF` relies on the caches of this chapter being cleared when the setting changes ([The test framework](testing.md)).
