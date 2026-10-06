---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Resolving a path

How `URLResolver.resolve` searches the tree for a path: the order it goes in, how the arguments found at each level are merged into one `ResolverMatch`, what a `Resolver404` carries, and what asks the resolver besides the handler.

Everything that resolves a path ends in one method, `URLResolver.resolve`, called on a root resolver. `BaseHandler.resolve_request` calls it with the request's `path_info`, for each request that reaches the centre of the middleware chain. The function `resolve` calls it for anyone else: it takes a path and, optionally, a URLconf, and without one it uses the current URLconf of the thread or task it is called in, or failing that the root one. `is_valid_path` is `resolve` with the exception turned into `False` (`django/urls/base.py:resolve`, `django/urls/base.py:is_valid_path`).

What is resolved is a path and nothing more: no host, no method, no query string. It is the path as `path_info` has it, without the script prefix and with its percent escapes already decoded ([Making the request](../http/request.md)), so a route is written for the characters themselves. Asked directly for a path with a space in it, the museum's pattern for files takes the space as a space:

```text recording=urls
resolve('/files/maps/ground floor.pdf')  ->  views.download, args (), kwargs {'name': 'maps/ground floor.pdf'}
```

## The search

`URLResolver.resolve` is the same method at every level of the tree, the root included (`django/urls/resolvers.py:URLResolver.resolve`).

It first asks its own matcher about the path. If the matcher refuses, the method raises `Resolver404` and is done. If it accepts, it has returned what is left of the path and what it captured, and the method goes through `url_patterns` in order, calling `resolve` on each entry with what is left. An entry is a pattern, whose `URLPattern.resolve` returns a match or `None`, or another resolver, whose `resolve` is this same method one level down. The first entry to produce a match ends the search.

A resolver that is an entry of another says no by raising. Its `resolve` raises `Resolver404` when its own matcher refuses and when none of its entries matches, and the resolver above catches the exception, notes what was tried, and moves to its next entry. `Resolver404` is thus used inside the tree as well as at its top: below, it is how a branch reports that the path is not under it, and from the root it is the answer for a path that matches nothing.

This request was for a month the museum's converter refuses. Every entry of the root's list is asked, and after the last the root raises.

```text recording=urls
GET /tickets/2026/13/: a converter refuses, and nothing else matches
    BaseHandler.resolve_request
      get_resolver()
      URLResolver.resolve('/tickets/2026/13/')  (the root resolver)
        RegexPattern.match('/tickets/2026/13/')  ->  ('tickets/2026/13/', (), {})
        URLPattern.resolve('tickets/2026/13/')  ('')  ->  None
        URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/')  ->  None
        URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/<month:month>/')
          RoutePattern.match('tickets/2026/13/')
            IntConverter.to_python('2026')  ->  2026
            MonthConverter.to_python('13')  raises ValueError
            -> None
          -> None
        URLResolver.resolve('tickets/2026/13/')  ('east/')  raises Resolver404
        URLResolver.resolve('tickets/2026/13/')  ('west/')  raises Resolver404
        URLResolver.resolve('tickets/2026/13/')  ('shop/')  raises Resolver404
        URLPattern.resolve('tickets/2026/13/')  ('^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$')  ->  None
        URLPattern.resolve('tickets/2026/13/')  ('files/<path:name>')  ->  None
        raises Resolver404
    response_for_exception
      get_resolver('museum.urls')
      URLResolver.resolve_error_handler(404)  (the root resolver)  ->  defaults.page_not_found
    start_response("404 Not Found", headers)
```

The three resolvers among the root's entries each raised at once, because none of their routes is the start of this path. The last lines belong to the handler. The exception left `resolve_request`, the wrapper around the centre of the middleware chain passed it to `response_for_exception`, and that function, finding an `Http404`, went back to the resolver for the 404 error view ([How an exception becomes a response](../handlers/exceptions.md)).

Getting into an include does not commit the search to it. When a resolver's own route matches and nothing in its list does, the resolver above treats that as it treats any other refusal, and carries on with the entries that follow. Here a path gets into the shop's include, fails there, and is matched by the entry after it:

```text recording=urls
A path that gets into an include, matches nothing there, and is matched by a later entry
    RETURNS is a URLconf of two entries:
      path("shop/", include([path("", views.shop, name="shop"), path("<slug:item>/", views.item, name="item")]))
      path("shop/<slug:item>/closed/", views.item, name="closed")
    the script calls resolve("/shop/poster/closed/", urlconf=RETURNS)
      resolve('/shop/poster/closed/', urlconf=a tuple of 2 entries)
        get_resolver(a tuple of 2 entries)
        URLResolver.resolve('/shop/poster/closed/')  (the root resolver of the URLconf given)
          RegexPattern.match('/shop/poster/closed/')  ->  ('shop/poster/closed/', (), {})
          URLResolver.resolve('shop/poster/closed/')  ('shop/')
            RoutePattern.match('shop/poster/closed/')  ->  ('poster/closed/', (), {})
            URLPattern.resolve('poster/closed/')  ('')  ->  None
            URLPattern.resolve('poster/closed/')  ('<slug:item>/')  ->  None
            raises Resolver404
          URLPattern.resolve('shop/poster/closed/')  ('shop/<slug:item>/closed/')
            RoutePattern.match('shop/poster/closed/')
              StringConverter.to_python('poster')  (SlugConverter)  ->  'poster'
              -> ('', (), {'item': 'poster'})
            -> ResolverMatch(views.item, kwargs={'item': 'poster'}, namespaces=[], route='shop/<slug:item>/closed/')
          -> ResolverMatch(views.item, kwargs={'item': 'poster'}, namespaces=[], route='shop/<slug:item>/closed/')
        -> ResolverMatch(views.item, kwargs={'item': 'poster'}, namespaces=[], route='shop/<slug:item>/closed/')
```

## How the arguments are merged

A match is found at a pattern and returned through every resolver above it, and each level adds what it knows. Where two levels have a keyword argument of the same name, the one applied later replaces the earlier, in this order:

1. what a resolver's own route captured;
2. the extra arguments given where that resolver was included, its `URLResolver.default_kwargs`;
3. the same two for each resolver further down, in turn;
4. what the pattern's route captured;
5. the pattern's own extra arguments, its `default_args`.

So an extra argument beats a captured one of the same name at its own level, and anything further down beats anything further up. `URLPattern.resolve` applies the last step as it makes the first `ResolverMatch`; each resolver on the way up makes a new match, starting from its own two and laying the match from below over them (`django/urls/resolvers.py:URLPattern.resolve`).

```text recording=urls
OVERRIDES is path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")]), {"wing": "annexe"})
  resolve('/east/rooms/12/', urlconf=OVERRIDES)  ->  views.room, args (), kwargs {'wing': 'annexe', 'room': 1}
NESTED is path("<slug:wing>/", include([path("<slug:wing>/", views.wing, name="wing")]))
  resolve('/east/west/', urlconf=NESTED)  ->  views.wing, args (), kwargs {'wing': 'west'}
```

In the first of these the path says east and room 12, and the view is given the annexe and room 1: at both levels the extra argument replaced the capture. In the second both levels capture a wing, and the view gets the inner one.

Positional arguments, which only a `re_path` with unnamed groups produces, are passed up as they are. What a resolver's own matcher captured by position is put in front of them when the merged keyword arguments are empty, and is dropped when they are not:

```text recording=urls
POSITIONAL is a URLconf of two entries:
  re_path(r"^a/([0-9]+)/", include([re_path(r"^b/([0-9]+)/$", views.tickets, name="b")]))
  re_path(r"^c/([0-9]+)/", include([re_path(r"^d/([0-9]+)/$", views.tickets, {"month": 12}, name="d")]))
  resolve('/a/1/b/2/', urlconf=POSITIONAL)  ->  views.tickets, args ('1', '2'), kwargs {}
  resolve('/c/1/d/2/', urlconf=POSITIONAL)  ->  views.tickets, args ('2',), kwargs {'month': 12}
```

Each resolver also puts its application namespace and its instance namespace at the front of the lists the match carries, and builds up the route. The route is assembled one level late: a resolver puts in front the route of the resolver below it that matched, not its own. That is why, in the recording on [the chapter's opening page](../urls.md#a-path-is-resolved), the east wing's match already has its namespace and still has only the pattern's route.

## A `ResolverMatch`, attribute by attribute

This is the match for the address of an audio track, three levels down: the east wing, a room's audio guide, a track.

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
      match._func_path  ->  'museum.views.track'
      match.tried  ->  a list of the chains tried, the last being the one that matched:
        ''
        'tickets/<int:year>/'
        'tickets/<int:year>/<month:month>/'
        'east/' > ''
        'east/' > 'rooms/<int:room>/'
        'east/' > 'rooms/<int:room>/audio/' > '<slug:track>/'
      view, args, kwargs = match  ->  views.track, (), {'wing': 'east', 'room': 12, 'track': 'intro'}
      pickle.dumps(match)  ->  raises PicklingError: Cannot pickle ResolverMatch.
```

The first three attributes are what the handler needs, and the rest describe how the match came about (`django/urls/resolvers.py:ResolverMatch.__init__`).

| attribute | what it is |
|---|---|
| `ResolverMatch.url_name` | the name of the pattern that matched, or `None` |
| `ResolverMatch.route` | the text of each matcher on the way down, below the root resolver's own, joined: a route as written, a regular expression as written, a language prefix as it reads at the moment. Where a resolver's text is put in front and is not empty, a `^` at the start of what follows it is taken off |
| `ResolverMatch.app_names`, `ResolverMatch.namespaces` | the application namespaces and the instance namespaces of the resolvers on the way down, outermost first, empty ones left out |
| `ResolverMatch.app_name`, `ResolverMatch.namespace` | the same two lists, each joined with colons |
| `ResolverMatch.view_name` | the instance namespaces and the pattern's name joined with colons, which is how a name is written for `reverse`; where the pattern has no name, the view's dotted name stands in its place |
| `ResolverMatch.captured_kwargs` | what the matched pattern's own route captured |
| `ResolverMatch.extra_kwargs` | the extra arguments, from the pattern and from every include above it |
| `ResolverMatch.tried` | the chains of entries tried, as in a `Resolver404`, ending with the one that matched |

*The attributes of a `ResolverMatch` beyond the view and its arguments.*

The two dictionaries do not add up to `kwargs`. In the recording the room number is in `kwargs` and in neither of the others, because it was captured by an include's route, and `captured_kwargs` holds the pattern's captures only.

The handler unpacks a match as if it were a tuple of three: `ResolverMatch.__getitem__` serves the view, the positional arguments and the keyword arguments by index. It keeps the match on the request, as `HttpRequest.resolver_match`, where the middleware's `process_view` hooks, the view and the template can read it. A `ResolverMatch` refuses to be pickled: `ResolverMatch.__reduce_ex__` raises `pickle.PicklingError`.

## What a `Resolver404` carries

The exception is made with one argument, a dictionary. A resolver whose own matcher refused puts in only `"path"`, the text it was given. A resolver whose entries all failed puts in `"path"`, the text that was left for them, and `"tried"`: a list of chains, each a list that starts with one of this resolver's entries and leads down to the pattern or the resolver that said no. An entry that is a pattern, or a resolver whose own matcher refused, adds one chain holding itself alone. An entry that is a resolver whose list failed adds each chain it reported, with itself put at the front (`django/urls/resolvers.py:URLResolver._extend_tried`).

```text recording=urls
What a Resolver404 carries: the path that was left, and each chain of entries tried
    resolve('/east/rooms/12') raises Resolver404 with {'tried': ..., 'path': 'east/rooms/12'}, where 'tried' is
      ''
      'tickets/<int:year>/'
      'tickets/<int:year>/<month:month>/'
      'east/' > ''
      'east/' > 'rooms/<int:room>/'
      'east/' > 'rooms/<int:room>/audio/'
      'west/'
      'shop/'
      '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'
      'files/<path:name>'
    resolve('east/rooms/12/') raises Resolver404 with {'path': 'east/rooms/12/'}
```

The first path got into the east wing's resolver and failed there, so that one entry of the root contributed three chains of two links. The second has no leading slash, the root's own matcher refused, and nothing was tried at all.

Within Django `"tried"` has one reader, the debug page. With `settings.DEBUG` on, the response to a 404 is made by `technical_404_response`, which takes the list out of the exception and shows each chain as a line, the entries Django tried in the order it tried them. Two lists get the welcome page of a new project instead: an empty one, and, for the path `"/"`, one whose only chain is a single entry with `"admin"` as both its application namespace and its instance namespace. When the exception carries no list, as an `Http404` raised by a view does not, the function reads the one on the request's match, which is the use Django makes of the `tried` that a successful match carries. The 404 view used in production does not look at the dictionary. It gives its template the exception's message when the exception was raised with a string, and the name of the exception's class otherwise (`django/views/debug.py:technical_404_response`, `django/views/defaults.py:page_not_found`).

## The resolver's other callers

Nothing remembers the answer for a path. Each call of `resolve` walks the tree again, and a request can cause more than one.

`CommonMiddleware` is the usual second caller. When a response comes back to it with status 404, and `settings.APPEND_SLASH` is true, and the path does not end in a slash, it asks whether the path would have matched with one. This was recorded with that middleware in front of the museum:

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
    start_response("301 Moved Permanently", headers), with Location: /east/rooms/12/
```

The resolver was asked three times for one request. The handler's attempt failed. On the way out `CommonMiddleware.should_redirect_with_slash` first checked that the path as it came does not resolve: the method is also called from `CommonMiddleware.process_request`, before anything has been resolved, and here a 404 may equally have come from a view. Then it tried the path with a slash, which matched. The response became a permanent redirect to that address. A view can opt out: before it answers, the method reads an attribute named `"should_append_slash"` from the matched view, which the decorator `no_append_slash` sets to false. And when `settings.DEBUG` is true and the request's method is `"DELETE"`, `"POST"`, `"PUT"` or `"PATCH"`, the middleware raises `RuntimeError` in place of the redirect: its message says that Django cannot redirect to the address with the slash and keep the request's data (`django/middleware/common.py:CommonMiddleware.should_redirect_with_slash`, `django/middleware/common.py:CommonMiddleware.get_full_path_with_slash`, `django/views/decorators/common.py:no_append_slash`).

`LocaleMiddleware` does much the same for a path that lacks a language's prefix ([Language prefixes and translated routes](i18n.md)). The test client resolves each path it requested once more, lazily, to give a test `resolver_match` on the response ([The test framework](../testing.md)) (`django/test/client.py:Client.request`).
