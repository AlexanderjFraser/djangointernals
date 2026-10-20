---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Reversing a name

`reverse` turns a name and arguments into a path: `URLResolver._populate` reads the tree into tables, `URLResolver.reverse_dict` among them, and `URLResolver._reverse_with_prefix` takes the candidates filed under the name and returns the first that the arguments fill in and its expression accepts or, having tried them all, raises `NoReverseMatch`. `reverse_lazy` puts the call off until its result is used as text.

A regular expression recognises text. It does not produce any. Reversing needs the opposite of what a pattern's expression is for, and Django gets it by a detour: from each expression it derives one or more strings with gaps for the parameters, and keeps the strings in tables. A call of `reverse` then looks its name up, fills in a string, and uses the regular expression only to check the result.

> **History.** Reversing is older than routes. `reverse` and the `{% url %}` tag already turned names into paths in Django 1.1 (`docs/releases/1.1.txt`), when every pattern was a regular expression. Routes, and `path` to write them, came in 2.0 as a "simplified URL routing syntax", and the function that had written patterns until then was made available as `re_path` (`docs/releases/2.0.txt`). Routes were fitted to the machinery already there (`deps:final/0201-simplified-routing-syntax.rst`): a route is expanded into a regular expression as its matcher is made (`django/urls/resolvers.py:_route_to_regex`), and reversing works on expressions whichever function wrote the pattern.

`reverse` itself finds the root resolver of the current URLconf, unless it is given a URLconf, reads the script prefix, deals with any namespaces in the name, and hands the rest to `URLResolver._reverse_with_prefix`: the name, the prefix, and the arguments, which are given either as a list or as a dictionary (`django/urls/base.py:reverse`). Namespaces have a section of their own, [Namespaces](namespaces.md), and the names here have none.

## The tables

A `URLResolver` keeps three dictionaries for reversing, each read through a property of the resolver. `URLResolver.reverse_dict` maps a pattern's view, and its name if it has one, to a list of candidates. The other two, `URLResolver.namespace_dict` and `URLResolver.app_dict`, are how `reverse` finds a resolver that has a namespace. Each of the three is kept once for each language ([Language prefixes and translated routes](i18n.md#tables-for-each-language)).

`URLResolver._populate` fills all three in one pass over the resolver's entries. It runs when something needs the tables and finds none for the language in use, and it runs again, on a resolver lower down, each time a resolver above it is populated (`django/urls/resolvers.py:URLResolver._populate`).

A **candidate** stands for one pattern. It holds the pattern's **forms**, each a string to fill in with the list of the parameters it has gaps for; a route written for `path` has one form. Beside them it holds the pattern's regular expression without its leading `^`, its extra arguments, and its converters.

What `_populate` does with an entry depends on what the entry is.

A pattern becomes one candidate. `normalize` turns the pattern's regular expression into forms ([`normalize`, and the patterns that cannot be reversed](normalize.md)), and the candidate is filed under the view and, when the pattern has a name, under the name as well.

A resolver is first told to populate itself. If it has no application namespace, everything in its tables is then lifted into the tables of the resolver that holds it. Each of its candidates is filed again in the upper table under the same key, with the include's regular expression put in front of its own, its forms made afresh from the longer expression, and the include's extra arguments and converters merged with its own; where both give an extra argument of the same name, the include's is kept here (`django/urls/resolvers.py:URLResolver._populate`), though the view is called with the pattern's ([Resolving a path](resolving.md#how-the-arguments-are-merged)). The include's namespaces and applications are lifted the same way. A plain `include` thus disappears: the names under it can be reversed from above.

If the resolver has an application namespace, none of that happens. It is filed whole, under its instance namespace in `namespace_dict` with the regular expression of its route, and in `app_dict` among the instances of its application, and its names stay in its own tables ([Namespaces](namespaces.md)).

The figure follows the museum's root resolver through its entries; look at where the names under `"shop/"` go, and where those under `"east/"` go.

```text figure=the-tables
the root resolver's entries, by kind  what _populate files, and where

""                    entrance   ->   reverse_dict["entrance"]   one candidate
tickets/<int:year>/   tickets    ->   reverse_dict["tickets"]    two candidates, the pattern written last in front
tickets/<int:year>/<month:month>/
                      tickets    ->   reverse_dict["tickets"]
^plans/...$           plan       ->   reverse_dict["plan"]
files/<path:name>     download   ->   reverse_dict["download"]

shop/   a resolver with no namespace: its names are lifted, with shop/ put in front
    ""                shop       ->   reverse_dict["shop"]       shop/
    <slug:item>/      item       ->   reverse_dict["item"]       shop/%(item)s/

east/   a resolver with a namespace: filed as a whole, and its names stay in its own tables
                                 ->   namespace_dict["east"]     east/ and the resolver
                                 ->   app_dict["gallery"]        west, east
    ""                wing       ->   the reverse_dict of the resolver east/: "wing", the empty string
    rooms/<int:room>/ room       ->   the reverse_dict of the resolver east/: "room", rooms/%(room)s/
west/   is filed in the same way, and before east/

each candidate is also filed under its view, so reverse_dict has the function tickets as a key too
```

*How the museum's tree is read into tables. The entries stand at the left, a resolver's own entries inside its box, and at the right the table each is filed in.*

What else a candidate holds, the figure leaves out. In the root resolver's table as `_populate` left it, the lifted name shop has `"shop/"` in front of both its form and its expression, and the two candidates for tickets stand the month's first:

```text recording=urls
What the root resolver keeps for reversing
    reverse_dict: under each key its candidates, in the order they are tried; a candidate is its forms; its regular expression; its extra arguments; its converters
...
      'shop'
        [('shop/', [])]; 'shop/\\Z'; {}; {}
      the function views.shop  ->  the same candidates as 'shop'
      'tickets'
        [('tickets/%(year)s/%(month)s/', ['year', 'month'])]; 'tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z'; {}; {'year': IntConverter, 'month': MonthConverter}
        [('tickets/%(year)s/', ['year'])]; 'tickets/(?P<year>[0-9]+)/\\Z'; {}; {'year': IntConverter}
...
```

The pass goes through the entries last to first, and a list of candidates is built in the order they are met. So where several patterns share a name, the one written last in the URLconf is tried first. Resolving does the opposite, and takes the pattern written first. Django's documentation relies on that order: a project that wants its own view at a name an application already uses, a login page for one, is told to write its pattern after the application's include (`docs/topics/http/urls.txt`).

The pass also fills a set on the side, `URLResolver._callback_strs`, with the dotted name of every view in the tree, namespaced or not, from which `URLResolver._is_callback` answers whether a dotted name is that of a view of the URLconf; the admin's documentation asks it before it imports a view named in its address (`django/contrib/admindocs/views.py:ViewDetailView._get_view_func`).

## `_reverse_with_prefix`: choosing a candidate

`URLResolver._reverse_with_prefix` is where a name becomes a path. It refuses a call that gives both positional and keyword arguments, makes sure the tables exist, and takes the candidates filed under the name or the view. Then it tries each form of each candidate, in order, against the arguments (`django/urls/resolvers.py:URLResolver._reverse_with_prefix`).

**The arguments have to fit the parameters.** Positional arguments fit when there are as many of them as the form has parameters, and they are paired off in order, which works for named groups as well as unnamed. Keyword arguments fit when the names given and the form's parameters are the same once the names of the candidate's extra arguments are taken out of both. An extra argument that is not also a parameter may be given or left out, and if it is given, it has to have the value the candidate holds for it.

**Each argument is turned into text.** A parameter with a converter goes through the converter's `to_url`; one without is passed to `str`. If `to_url` raises `ValueError`, this form is passed over.

**The filled-in string is checked against the pattern.** The text is put into the gaps and the result is searched with the pattern's own regular expression, with the script prefix in front of both.

The first form to pass all three is the answer. Of the museum's names, given arguments that fit and arguments that do not, each `NoReverseMatch` fails one of the three tests or finds nothing filed under the name, and the two cases have different messages:

```text recording=urls
reverse(): what comes back, and what is refused
...
    reverse("tickets", args=[2026], kwargs={"month": 3})  ->  raises ValueError: Don't mix *args and **kwargs in call to reverse()!
    reverse("tickets")  ->  raises NoReverseMatch: Reverse for 'tickets' with no arguments not found. 2 pattern(s) tried: ['tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z', 'tickets/(?P<year>[0-9]+)/\\Z']
    reverse("tickets", kwargs={"year": 2026, "day": 1})  ->  raises NoReverseMatch
    reverse("tickets", kwargs={"year": 2026, "month": 13})  ->  raises NoReverseMatch
    reverse("ticket")  ->  raises NoReverseMatch: Reverse for 'ticket' not found. 'ticket' is not a valid view function or pattern name.
    reverse(views.tickets, kwargs={"year": 2026})  ->  '/tickets/2026/'
    reverse("museum.views.tickets", kwargs={"year": 2026})  ->  raises NoReverseMatch: Reverse for 'museum.views.tickets' not found. 'museum.views.tickets' is not a valid view function or pattern name.
    reverse(views.room, kwargs={"room": 12})  ->  raises NoReverseMatch: Reverse for 'museum.views.room' not found. 'museum.views.room' is not a valid view function or pattern name.
    reverse("plan", kwargs={"floor": 2})  ->  '/plans/2'
    reverse("plan", kwargs={"floor": 2, "format": "pdf"})  ->  '/plans/2.pdf'
    reverse("plan", args=[2, "svg"])  ->  '/plans/2.svg'
    reverse("plan", kwargs={"floor": 2, "format": "png"})  ->  raises NoReverseMatch
    reverse("plan", kwargs={"floor": 12})  ->  raises NoReverseMatch
    reverse("item", kwargs={"item": "poster"})  ->  '/shop/poster/'
    reverse("item", kwargs={"item": "tea towel"})  ->  raises NoReverseMatch
```

Each `NoReverseMatch` for a name that has candidates falls under one of the three tests. A year and a day fit neither candidate's parameters, and no arguments at all fit neither. A thirteenth month fits the first candidate, and the month's converter refuses it. A plan as png, a floor of two digits and a shop item with a space in its name all fit their parameters, are turned into text without complaint, and are then refused by the pattern's expression.

Where nothing was filed under the name at all, the message says the name is not a valid view function or pattern name. That is also the answer for a view's dotted name given as a string, which is not a key of the table, and for a view that sits under a namespace. Otherwise the message names the arguments and lists the regular expressions of the candidates tried.

When several candidates would do, the order of the list decides, and the extra arguments can be used to decide it on purpose. Two patterns for one view, each giving it a different kind of feed as an extra argument, show both:

```text recording=urls
Two patterns with one name, told apart by their extra arguments
    FEEDS is a URLconf of two patterns, in this order:
      path("feed/rss/", views.feed, {"kind": "rss"}, name="feed")
      path("feed/atom/", views.feed, {"kind": "atom"}, name="feed")
    resolve('/feed/rss/', urlconf=FEEDS)  ->  views.feed, args (), kwargs {'kind': 'rss'}
    reverse("feed", urlconf=FEEDS, kwargs={"kind": "rss"})  ->  '/feed/rss/'
    reverse("feed", urlconf=FEEDS, kwargs={"kind": "atom"})  ->  '/feed/atom/'
    reverse("feed", urlconf=FEEDS)  ->  '/feed/atom/'
    reverse("feed", urlconf=FEEDS, kwargs={"kind": "json"})  ->  raises NoReverseMatch
```

> **Trap.** The documentation allows an extra argument to have the name of a parameter its route captures, and the extra argument then replaces the capture (`docs/topics/http/urls.txt`). `reverse` neither requires such a parameter nor holds it to the extra argument's value: a call that gives it fits with any value, and a call by keyword that leaves it out fits too, since the extra arguments' names are not compared, but then nothing fills its gap, and `reverse` raises `KeyError`, not `NoReverseMatch` (`django/urls/resolvers.py:URLResolver._reverse_with_prefix`).

In a URLconf with such a clash at each level, an include of `"<slug:wing>/"` given wing as `"annexe"` around a pattern `"rooms/<int:room>/"` given room as 1, `"/east/rooms/12/"` resolves to the annexe and room 1, the east wing and room 12 reverse to it, and the room given alone raises:

```text recording=urls
OVERRIDES reversed: its candidate keeps both extra arguments, and reverse() does not hold a parameter the route captures to its extra argument
    OVERRIDES is path("<slug:wing>/", include([path("rooms/<int:room>/", views.room, {"room": 1}, name="room")]), {"wing": "annexe"})
      resolve('/east/rooms/12/', urlconf=OVERRIDES)  ->  views.room, args (), kwargs {'wing': 'annexe', 'room': 1}
...
      reverse("room", urlconf=OVERRIDES, kwargs={"wing": "east", "room": 12})  ->  '/east/rooms/12/'
      reverse("room", urlconf=OVERRIDES, kwargs={"room": 1})  ->  raises KeyError: 'wing'
      ...
```

Before a path is returned it is escaped for use in a URL: every character is replaced by a percent escape unless it is an ASCII letter or digit, one of the punctuation marks a path segment may hold, or the slash between segments. And a result that begins with two slashes has the second replaced by `%2F`, so that a browser cannot read the path as the name of another host (`django/utils/http.py:escape_leading_slashes`). The check against the pattern comes first, on the text with nothing escaped, and the escaping is then applied to the same text: a name with a space in it passes an expression that allows spaces and comes back with the space escaped, and the same name given already escaped is refused, since the expression allows no percent sign:

```text recording=urls
reverse(): the path is escaped once it has been checked
    reverse("download", kwargs={"name": "maps/ground floor.pdf"})  ->  '/files/maps/ground%20floor.pdf'
    reverse("download", kwargs={"name": "notes?draft#2 100%.txt"})  ->  '/files/notes%3Fdraft%232%20100%25.txt'
    reverse("download", kwargs={"name": "café.txt"})  ->  '/files/caf%C3%A9.txt'
    ANYTHING is a URLconf of one pattern: path("<path:name>", views.download, name="anything")
      reverse("anything", urlconf=ANYTHING, kwargs={"name": "/evil.example/"})  ->  '/%2Fevil.example/'
    NOTES is a URLconf of one pattern: re_path(r"^notes/(?P<name>[a-z ]+)/$", views.download, name="notes")
      reverse("notes", urlconf=NOTES, kwargs={"name": "tea towel"})  ->  '/notes/tea%20towel/'
      reverse("notes", urlconf=NOTES, kwargs={"name": "tea%20towel"})  ->  raises NoReverseMatch
```

> **Why.** The check is made on the unescaped text because that is what the resolver is matched against: "WSGI provides decoded URLs, without %xx escapes, and the URL resolver operates on such URLs," says the comment above it (`django/urls/resolvers.py:URLResolver._reverse_with_prefix`). Whether a path arrives decoded is up to the server: neither the request nor the resolver decodes it ([Resolving a path](resolving.md)).

## The query string and the fragment

`reverse` takes two keyword-only arguments for what follows a path. The query may be a dictionary, whose values may be lists, or a `QueryDict`. It is encoded, and added after a question mark if the encoding is not empty. The fragment is added after a `#` as it is given, without escaping, whenever it is not `None`, so an empty one leaves a bare `#`.

```text recording=urls
reverse(): a query string and a fragment
    reverse("entrance", query={"lang": "nl", "tag": ["new", "sale"]}, fragment="hours")  ->  '/?lang=nl&tag=new&tag=sale#hours'
    reverse("entrance", query={})  ->  '/'
    reverse("entrance", fragment="")  ->  '/#'
```

> **Changed in 5.2.** `reverse` and `reverse_lazy` gained the arguments for a query string and a fragment in that release.

## `reverse_lazy`

`reverse_lazy` is `reverse` wrapped by `lazy`: calling it returns a stand-in at once and reverses nothing, and the stand-in calls `reverse` each time it is used as a string. It is for a URL that is wanted before the URLconf can be read, which means in code that runs at import time: an attribute in the body of a class-based view, an argument to a decorator, the default of a parameter. Such code may be imported by the URLconf itself, and a plain `reverse` there asks for patterns that do not yet exist ([When a URLconf is imported](import.md#when-the-import-fails)) (`django/urls/base.py:reverse_lazy`, `django/utils/functional.py:lazy`).

The stand-in's class is a subclass of `Promise`, the base of every class that `lazy` makes, and a name that does not exist is not noticed when the stand-in is made, only when something asks it for its text:

```text recording=urls
reverse_lazy(): nothing is reversed until the text is asked for
    type(reverse_lazy("entrance")).__mro__[1].__name__  ->  'Promise'
    str(reverse_lazy("entrance"))  ->  '/'
    reverse_lazy("no-such-name") is not None  ->  True
    str(reverse_lazy("no-such-name"))  ->  raises NoReverseMatch
```
