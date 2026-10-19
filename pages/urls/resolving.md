---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Resolving a path

`URLResolver.resolve` finds the view for a path by searching a URLconf's tree, depth first and in the order its entries are written, and returns a `ResolverMatch`: the view, the arguments gathered for it from every level, and a record of how the match was found. A path that matches nothing raises `Resolver404`. The handler keeps the match as `HttpRequest.resolver_match`, and the function `resolve` and `is_valid_path` ask the same question for any other caller.

Everything that resolves a path ends in one method, `URLResolver.resolve`, called on a root resolver. `BaseHandler.resolve_request` calls it with `HttpRequest.path_info`, for each request that reaches the centre of the middleware chain. The function `resolve` calls it for anyone else: it takes a path and, optionally, a URLconf, and without one it uses the current URLconf of the thread or task it is called in, or failing that the root one. `is_valid_path` returns what `resolve` returns, the match, with `False` in place of the exception (`django/urls/base.py:resolve`, `django/urls/base.py:is_valid_path`).

What is resolved is a path and nothing more: no host, no method, no query string. It is the request's `path_info`, the path without the script prefix ([Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md)), with its percent escapes as the server left them, since neither the request nor the resolver decodes them (`django/core/handlers/wsgi.py:get_path_info`, `django/core/handlers/asgi.py:ASGIRequest.__init__`). Python's wsgiref server, on which Django's development server is built, decodes them into `"PATH_INFO"`, and from `"/files/maps/ground%20floor.pdf"` the museum's pattern for files captures `"maps/ground floor.pdf"`; behind a server that leaves the escape, it captures `"maps/ground%20floor.pdf"` (`django/core/servers/basehttp.py:WSGIRequestHandler.get_environ`).

## The order of the search

`URLResolver.resolve` is the same method at every level of the tree, the root included. It first asks its own matcher about the path. If the matcher refuses, the method raises `Resolver404` and is done. If it accepts, it has returned what is left of the path and what it captured, and the method goes through `URLResolver.url_patterns` in order, calling `resolve` on each entry with what is left. An entry is a pattern, whose `URLPattern.resolve` returns a match or `None`, or another resolver, whose `resolve` is this same method one level down. The first entry to produce a match ends the search (`django/urls/resolvers.py:URLResolver.resolve`).

A resolver that is an entry of another says no by raising: its `resolve` raises `Resolver404` when its own matcher refuses and when none of its entries matches, and the resolver above catches the exception, notes what was tried, and moves to its next entry. So getting into an include does not commit the search to it. When a resolver's own route matches and nothing in its list does, the resolver above treats that as it treats any other refusal, and carries on with the entries that follow.

The figure draws one resolve in each direction, with two small URLconfs. On the left the search goes down into an include whose route takes the start of the path, finds nothing in its list for the rest, and comes back out to the root's next entry. On the right the match comes back up from the pattern that made it, each level laying its own arguments under what came up from below.

```text figure=the-search
on the left, the way down: resolve("/shop/poster/closed/") with RETURNS
  the root resolver: its matcher takes /, and shop/poster/closed/ is left
    1  shop/                       a resolver: its route takes shop/, and poster/closed/ is left
         ""                        a pattern: no match
         <slug:item>/              a pattern: no match
                                   nothing in its list matched: Resolver404, back out to the root's list
    2  shop/<slug:item>/closed/    a pattern: it takes all of shop/poster/closed/
                                   the first match, which ends the search: views.item, item="poster"

on the right, the way up: resolve("/east/rooms/12/") with OVERRIDES, read from the bottom
  the match                        views.room, wing="annexe", room=1
  the root resolver                nothing of its own
                                   from below, laid over it: wing="annexe", room=1
  the resolver <slug:wing>/        its capture: wing="east"
                                   its extra argument, laid over it: wing="annexe"
                                   from below, laid over both: room=1
  the pattern rooms/<int:room>/    its capture: room=12
                                   its extra argument, laid over it: room=1
```

*On the left, the search: the root's entries down the side, and the path's way into the include shop/ and back out to the next entry. On the right, the match rising from the pattern at the bottom to the root at the top, each level laying what came up from below over its own; the accented boxes hold the match.*

The way back out is an exception. `Resolver404` is used inside the tree as well as at its top: below, it is how a branch reports that the path is not under it, and from the root it is the answer for a path that matches nothing. Inside the root's loop, the shop's resolver takes its part of the path, finds no match for the rest and raises; the root's next call is to its second entry, which matches.

```text recording=urls
A path that gets into an include, matches nothing there, and is matched by a later entry
    RETURNS is a URLconf of two entries:
      path("shop/", include([path("", views.shop, name="shop"), path("<slug:item>/", views.item, name="item")]))
      path("shop/<slug:item>/closed/", views.item, name="closed")
    the script calls resolve("/shop/poster/closed/", urlconf=RETURNS)
        ...
        URLResolver.resolve('/shop/poster/closed/')  (the root resolver of the URLconf given)
          RegexPattern.match('/shop/poster/closed/')  ->  ('shop/poster/closed/', (), {})
          URLResolver.resolve('shop/poster/closed/')  ('shop/')
            RoutePattern.match('shop/poster/closed/')  ->  ('poster/closed/', (), {})
            URLPattern.resolve('poster/closed/')  ('')  ->  None
            URLPattern.resolve('poster/closed/')  ('<slug:item>/')  ->  None
            raises Resolver404
          URLPattern.resolve('shop/poster/closed/')  ('shop/<slug:item>/closed/')
            ...
            -> ResolverMatch(views.item, kwargs={'item': 'poster'}, namespaces=[], route='shop/<slug:item>/closed/')
            ...
```

A path that nothing matches is refused the same way at the top. For `"/tickets/2026/13/"`, a month the museum's converter refuses, the root asks each of its entries in turn, and its three resolvers raise at once, since none of their routes is the start of this path; after the last entry the root raises, and the handler makes the exception a 404 response ([How an exception becomes a response](../handlers/exceptions.md)).

```text recording=urls
GET /tickets/2026/13/: a converter refuses, and nothing else matches
    BaseHandler.resolve_request
      get_resolver()
      URLResolver.resolve('/tickets/2026/13/')  (the root resolver)
        RegexPattern.match('/tickets/2026/13/')  ->  ('tickets/2026/13/', (), {})
        URLPattern.resolve('tickets/2026/13/')  ('')  ->  None
        URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/')  ->  None
        URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/<month:month>/')
          ...
          -> None
        URLResolver.resolve('tickets/2026/13/')  ('east/')  raises Resolver404
        URLResolver.resolve('tickets/2026/13/')  ('west/')  raises Resolver404
        URLResolver.resolve('tickets/2026/13/')  ('shop/')  raises Resolver404
        URLPattern.resolve('tickets/2026/13/')  ('^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$')  ->  None
        URLPattern.resolve('tickets/2026/13/')  ('files/<path:name>')  ->  None
        raises Resolver404
    ...
```

## How the arguments are merged

A match is found at a pattern and returned through every resolver above it, and each level adds what it knows. Where two levels have a keyword argument of the same name, the one applied later replaces the earlier, in this order:

1. what a resolver's own route captured;
2. the extra arguments given where that resolver was included, its `URLResolver.default_kwargs`;
3. the same two for each resolver further down, in turn;
4. what the pattern's route captured;
5. the pattern's own extra arguments, its `django.urls.URLPattern.default_args`.

So an extra argument beats a captured one of the same name at its own level, and anything further down beats anything further up. `URLPattern.resolve` applies the last two steps as it makes the first `ResolverMatch`; each resolver on the way up makes a new match, starting from its own two and laying the match from below over them. The root resolver, whose matcher captures nothing and which is given no extra arguments, adds none (`django/urls/resolvers.py:URLPattern.resolve`, `django/urls/resolvers.py:URLResolver.resolve`, `django/urls/resolvers.py:_get_cached_resolver`).

OVERRIDES, the URLconf on the right of the figure, gives at each level an extra argument for what that level captures, and its view is given the annexe and room 1 for a path that says east and room 12: at both levels the extra argument replaced the capture. In NESTED both levels capture a wing, and the view gets the inner one.

```text recording=urls
Arguments from several levels: which one the view gets
    OVERRIDES is path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")]), {"wing": "annexe"})
      resolve('/east/rooms/12/', urlconf=OVERRIDES)  ->  views.room, args (), kwargs {'wing': 'annexe', 'room': 1}
    NESTED is path("<slug:wing>/", include([path("<slug:wing>/", views.wing, name="wing")]))
      resolve('/east/west/', urlconf=NESTED)  ->  views.wing, args (), kwargs {'wing': 'west'}
      ...
```

> **Trap.** An extra argument given to `include` is not passed to each line of the included URLconf as if it had been written there, though the documentation calls the two forms "functionally identical" (`docs/topics/http/urls.txt`). Written on the line, an extra argument beats the pattern's capture of the same name; given to the include, it is laid under everything that comes up from below, and the capture beats it. With `{"room": 1}` given to an include whose pattern captures the room, `"/east/rooms/12/"` gives the view room 12; with the same dictionary given to the pattern's line instead, room 1. In the first case `ResolverMatch.extra_kwargs` still reports `{'room': 1}`, a value the view was not given (`django/urls/resolvers.py:URLResolver.resolve`).

Positional arguments, which only a `re_path` with unnamed groups produces, are passed up as they are.

> **Trap.** A resolver's own positional captures are dropped as soon as any keyword argument reaches its level, an extra argument as much as a named group. `URLResolver.resolve` puts them in front of the positional arguments from below only when the dictionary it has merged, of its own arguments and those from below, is empty; its comment speaks of named groups only, but the dictionary holds the extra arguments too. Under the include `r"^c/([0-9]+)/"`, the pattern `r"^d/([0-9]+)/$"` with the extra argument `{"month": 12}` gives the view `('2',)` and `month=12` for `"/c/1/d/2/"`: the include's `'1'` is lost. Without an extra argument, `r"^a/([0-9]+)/"` over `r"^b/([0-9]+)/$"` gives `('1', '2')` for `"/a/1/b/2/"` (`django/urls/resolvers.py:URLResolver.resolve`).

Each resolver also puts its application namespace and its instance namespace at the front of the lists the match carries, and builds up the route. The route is assembled one level late: a resolver puts in front the route of the resolver below it that matched, not its own. At the end of the walk of `"/east/rooms/12/"` through the museum's URLconf, the east wing's resolver has already added its namespace and its wing, while the route is still the pattern's; only the root puts `"east/"` in front.

```text recording=urls
GET /east/rooms/12/: the path is resolved, entry by entry, and the view is called
...
            -> ResolverMatch(views.room, kwargs={'room': 12}, namespaces=[], route='rooms/<int:room>/')
          -> ResolverMatch(views.room, kwargs={'wing': 'east', 'room': 12}, namespaces=['east'], route='rooms/<int:room>/')
        -> ResolverMatch(views.room, kwargs={'wing': 'east', 'room': 12}, namespaces=['east'], route='east/rooms/<int:room>/')
        ...
```

## A `ResolverMatch`, attribute by attribute

A `ResolverMatch` carries the view and its arguments, which are what the handler needs, and besides them a record of how the match came about (`django/urls/resolvers.py:ResolverMatch.__init__`). The match for the address of an audio track, three levels down (the east wing, a room's audio guide, a track), leaves only its positional arguments empty.

```text recording=urls
A ResolverMatch, attribute by attribute
    match = resolve("/east/rooms/12/audio/intro/")
      match.func  ->  views.track
      match.args  ->  ()
      match.kwargs  ->  {'wing': 'east', 'room': 12, 'track': 'intro'}
      match.url_name  ->  'track'
      match.route  ->  'east/rooms/<int:room>/audio/<slug:track>/'
      match.app_names  ->  ['gallery', 'audio']
      match.app_name  ->  'gallery:audio'
      match.namespaces  ->  ['east', 'audio']
      match.namespace  ->  'east:audio'
      match.view_name  ->  'east:audio:track'
      match.captured_kwargs  ->  {'track': 'intro'}
      match.extra_kwargs  ->  {'wing': 'east'}
      ...
      match.tried  ->  a list of the chains tried, the last being the one that matched:
        ...
        'east/' > 'rooms/<int:room>/audio/' > '<slug:track>/'
      view, args, kwargs = match  ->  views.track, (), {'wing': 'east', 'room': 12, 'track': 'intro'}
      pickle.dumps(match)  ->  raises PicklingError: Cannot pickle ResolverMatch.
```

For these attributes the value does not show the rule it was made by.

| attribute | what it is |
|---|---|
| `ResolverMatch.route` | the text of each matcher on the way down, below the root resolver's own, joined: a route as written, a regular expression as written, a language prefix as it reads at the moment. Where a resolver's text is put in front and is not empty, a `^` at the start of what follows it is taken off |
| `ResolverMatch.app_names`, `ResolverMatch.namespaces` | the application namespaces and the instance namespaces of the resolvers on the way down, outermost first, empty ones left out |
| `ResolverMatch.view_name` | the instance namespaces and the pattern's name joined with colons, which is how a name is written for `reverse`; where the pattern has no name, the view's dotted name stands in its place |
| `ResolverMatch.captured_kwargs` | what the matched pattern's own route captured |
| `ResolverMatch.extra_kwargs` | the extra arguments, from the pattern and from every include above it |

*The attributes of a `ResolverMatch` whose values do not show how they are made.*

The two dictionaries do not add up to `ResolverMatch.kwargs`. The room number is in `kwargs` and in neither of the others, because an include's route captured it, and `captured_kwargs` holds the pattern's captures only.

The handler unpacks a match as if it were a tuple of three: `ResolverMatch.__getitem__` serves the view, the positional arguments and the keyword arguments by index. `BaseHandler.resolve_request` keeps the match on the request, as `HttpRequest.resolver_match`, where the middleware's `process_view` hooks and the view can read it, and a template through the request in its context (`django/core/handlers/base.py:BaseHandler.resolve_request`). A `ResolverMatch` refuses to be pickled: `ResolverMatch.__reduce_ex__` raises `pickle.PicklingError`.

## What a `Resolver404` carries

A `Resolver404` is made with one argument, a dictionary. A resolver whose own matcher refused puts in only `"path"`, the text it was given. A resolver whose entries all failed puts in `"path"`, the text that was left for them, and `"tried"`: a list of chains, each a list that starts with one of this resolver's entries and leads down to the pattern or the resolver that said no. An entry that is a pattern, or a resolver whose own matcher refused, adds one chain holding itself alone. An entry that is a resolver whose list failed adds each chain it reported, with itself put at the front (`django/urls/resolvers.py:URLResolver._extend_tried`).

Look for the east wing's entry, which the first path got into and failed in: that one entry of the root gave three chains of two links. The second path has no leading slash, so the root's own matcher refused it and nothing was tried.

```text recording=urls
What a Resolver404 carries: the path that was left, and each chain of entries tried
    resolve('/east/rooms/12') raises Resolver404 with {'tried': ..., 'path': 'east/rooms/12'}, where 'tried' is
      ''
      ...
      'east/' > ''
      'east/' > 'rooms/<int:room>/'
      'east/' > 'rooms/<int:room>/audio/'
      'west/'
      ...
    resolve('east/rooms/12/') raises Resolver404 with {'path': 'east/rooms/12/'}
```

Outside the resolvers `"tried"` has one reader in Django, the debug page: under `settings.DEBUG`, `technical_404_response` shows each chain as a line, taking the list from the request's match when a view raised `Http404` after its path had matched ([The debug pages and `ExceptionReporter`](../views/debug.md#the-404-page)) (`django/views/debug.py:technical_404_response`).

## The resolver's other callers

The handler is not the resolver's only caller, and nothing remembers the answer for a path: each call of `resolve` walks the tree again, and one request can cause several.

`CommonMiddleware` is the usual second caller ([The general-purpose middleware](../handlers/general.md)). Handed a 404 for a path without a final slash while `settings.APPEND_SLASH` is true, its method `CommonMiddleware.should_redirect_with_slash` asks `is_valid_path` about the path as it came and, when that fails, about the path with a slash; the second answer is the match itself, whose view the method reads for the mark `"should_append_slash"` that `no_append_slash` sets (`django/middleware/common.py:CommonMiddleware.should_redirect_with_slash`). With the handler's own attempt, that is three resolves for one request:

```text recording=urls
GET /east/rooms/12, with CommonMiddleware and APPEND_SLASH: the resolver is asked three times
    BaseHandler.resolve_request
      URLResolver.resolve('/east/rooms/12')  (the root resolver)  raises Resolver404
    CommonMiddleware.process_response  (given a 404)
      CommonMiddleware.should_redirect_with_slash
        is_valid_path('/east/rooms/12', None)
          URLResolver.resolve('/east/rooms/12')  (the root resolver)  raises Resolver404
          -> False
        is_valid_path('/east/rooms/12/', None)
          URLResolver.resolve('/east/rooms/12/')  (the root resolver)  ->  ResolverMatch(views.room, kwargs={'wing': 'east', 'room': 12}, namespaces=['east'], route='east/rooms/<int:room>/')
          -> the ResolverMatch
        -> True
      -> a 301, Location '/east/rooms/12/'
    ...
```

The first of the two questions is there because the path as it came may resolve after all: on the way out, the 404 may have come from a view whose path matched, and the method is called on the way in as well. `CommonMiddleware.process_request` calls it only under `settings.PREPEND_WWW`, for a host that does not begin with `"www."`, and then answers with a redirect to the www. host before the handler has resolved anything; with that setting off, the default, `process_request` resolves nothing (`django/middleware/common.py:CommonMiddleware.process_request`).

`LocaleMiddleware` does much the same for a path that lacks a language's prefix ([Language prefixes and translated routes](i18n.md)). The test client resolves each path it requested once more, lazily, to give a test `resolver_match` on the response ([The test client: `Client` and `ClientHandler`](../testing/client.md)) (`django/test/client.py:Client.request`).
