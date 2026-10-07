---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Reversing a name

How `reverse` turns a name and arguments into a path: the tables `URLResolver._populate` builds from the tree, the fill-in strings `normalize` makes from each regular expression, how `URLResolver._reverse_with_prefix` chooses among candidates, and what makes it raise `NoReverseMatch`.

A regular expression recognises text. It does not produce any. Reversing needs the opposite of what a pattern's expression is for, and Django gets it by a detour: from each expression it derives one or more strings with gaps for the parameters, and keeps the strings in tables. A call of `reverse` then looks its name up, fills in a string, and uses the regular expression only to check the result.

The detour is taken for every pattern, a route written for `path` included. `path` arrived in Django 2.0 (`docs/releases/2.0.txt`); before it every pattern was written as a regular expression, with the function that is now `re_path`. A route is expanded into an expression as its matcher is made (`django/urls/resolvers.py:_route_to_regex`), and reversing works on expressions whichever function wrote the pattern.

`reverse` itself finds the root resolver of the current URLconf, unless it is given a URLconf, reads the script prefix, deals with any namespaces in the name, and hands the rest to `URLResolver._reverse_with_prefix`: the name, the prefix, and the arguments, which are given either as a list or as a dictionary (`django/urls/base.py:reverse`). Namespaces have [a section of their own](namespaces.md), and the names here have none.

## The tables

A `URLResolver` keeps three dictionaries for reversing, each read through a property of the resolver. `URLResolver.reverse_dict` maps a pattern's view, and its name if it has one, to a list of candidates. `URLResolver.namespace_dict` maps an instance namespace to the resolver of that namespace and the regular expression that leads to it. `URLResolver.app_dict` maps an application namespace to the instance namespaces of that application. Each of the three is kept once for each language ([Language prefixes and translated routes](i18n.md)).

`URLResolver._populate` fills all three in one pass over the resolver's entries. It runs when something needs the tables and finds none for the language in use, and it runs again, on a resolver lower down, each time a resolver above it is populated (`django/urls/resolvers.py:URLResolver._populate`).

A **candidate** stands for one pattern. It holds the pattern's **forms**, each a string to fill in with the list of the parameters it has gaps for, of which a route written for `path` has one. Beside them it holds the pattern's regular expression without its leading `^`, its extra arguments, and its converters.

What `_populate` does with an entry depends on what the entry is.

A pattern becomes one candidate. `normalize` turns the pattern's regular expression into forms, and the candidate is filed under the view and, when the pattern has a name, under the name as well.

A resolver is first told to populate itself. If it has no application namespace, everything in its tables is then lifted into the tables of the resolver that holds it. Each of its candidates is filed again in the upper table under the same key, with the include's regular expression put in front of its own, its forms made afresh from the longer expression, and the include's extra arguments and converters merged with its own. Where the include and the pattern have an extra argument of the same name, the include's is the one kept here, though it is the pattern's that the view is called with when a path is resolved ([Resolving a path](resolving.md#how-the-arguments-are-merged)). The include's namespaces and applications are lifted the same way. A plain `include` thus disappears: the names under it can be reversed from above as if they had been written there.

If the resolver has an application namespace, none of that happens. It is filed in the other two dictionaries, by namespace and by application, and its names stay in its own tables.

```text figure=the-tables
the root resolver's entries, by kind  what _populate files in the root resolver's tables

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

*How the museum's tree is read into tables. The names under a plain include are lifted into the table above; a resolver with a namespace is filed whole, and its names are reached only through the namespace.*

These are the root resolver's tables as `_populate` left them.

```text recording=urls
What the root resolver keeps for reversing
    reverse_dict: under each key its candidates, in the order they are tried; a candidate is its forms; its regular expression; its extra arguments; its converters
      'download'
        [('files/%(name)s', ['name'])]; 'files/(?P<name>.+)\\Z'; {}; {'name': PathConverter}
      the function views.download  ->  the same candidates as 'download'
      'plan'
        [('plans/%(floor)s', ['floor']), ('plans/%(floor)s.%(format)s', ['floor', 'format'])]; 'plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'; {}; {}
      the function views.plan  ->  the same candidates as 'plan'
      'item'
        [('shop/%(item)s/', ['item'])]; 'shop/(?P<item>[-a-zA-Z0-9_]+)/\\Z'; {}; {'item': SlugConverter}
      the function views.item  ->  the same candidates as 'item'
      'shop'
        [('shop/', [])]; 'shop/\\Z'; {}; {}
      the function views.shop  ->  the same candidates as 'shop'
      'tickets'
        [('tickets/%(year)s/%(month)s/', ['year', 'month'])]; 'tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z'; {}; {'year': IntConverter, 'month': MonthConverter}
        [('tickets/%(year)s/', ['year'])]; 'tickets/(?P<year>[0-9]+)/\\Z'; {}; {'year': IntConverter}
      the function views.tickets  ->  the same candidates as 'tickets'
      'entrance'
        [('', [])]; '\\Z'; {}; {}
      the function views.entrance  ->  the same candidates as 'entrance'
    namespace_dict
      'west'  ->  ('west/', the resolver 'west/')
      'east'  ->  ('east/', the resolver 'east/')
    app_dict  ->  {'gallery': ['west', 'east']}
    _callback_strs, sorted  ->  ['museum.views.download', 'museum.views.entrance', 'museum.views.item', 'museum.views.plan', 'museum.views.room', 'museum.views.shop', 'museum.views.tickets', 'museum.views.track', 'museum.views.wing']
```

The pass goes through the entries last to first, and a list of candidates is built in the order they are met. So where several patterns share a name, the one written last in the URLconf is tried first. Resolving does the opposite, and takes the pattern written first. Django's documentation relies on that order: a project that wants its own view at a name an application already uses, a login page for one, is told to write its pattern after the application's include, and a `reverse` of that name whose arguments fit the project's pattern then finds the project's (`docs/topics/http/urls.txt`).

The room and wing views are absent from the table's keys, being under a namespace. The last line is a set that the pass fills on the side: the dotted name of every view in the tree, namespaced or not. `URLResolver._is_callback` answers from it whether a dotted name is that of a view of the URLconf, a question the admin's documentation pages ask.

## `normalize`: from an expression to its forms

`normalize` takes the text of a regular expression and returns its forms: a list of pairs, each a string that Python's `%` operator fills in from a dictionary, and the names of its parameters. Its module's docstring says it is not a complete decompiler of regular expressions and is meant to be good enough for a large class of URLs (`django/utils/regex_helper.py:normalize`).

It goes through the expression from the first character to the last and keeps what a matching text would have to contain.

- A literal character is kept. The anchors `^`, `\A`, `\Z`, `\b` and `\B` are dropped, and an unescaped `$` ends the reading.
- A capturing group becomes a gap. A named group gives `%(name)s` and a parameter of that name; an unnamed one gives `%(_0)s`, `%(_1)s` and so on. A reference back to a named group, `(?P=name)`, becomes a second gap for the same parameter. What is inside a group is skipped by counting brackets, so a converter's expression is passed over without being understood.
- A group that does not capture is read through, and kept together as one item for a quantifier that follows it.
- Where the expression allows a choice of characters, one is picked: the first character after the opening bracket of a class, a `0` for `\d`, an `x` for `\w`, a dot for a dot.
- A quantifier keeps the fewest repetitions it allows. Something optional is left out, unless it is or holds a capturing group: then there are two forms, one without it and one with it once.
- Lookahead and lookbehind are skipped.
- An alternation, a `|` that the reading meets outside any group it skips, makes it give up and return one empty form.
- Any other construct that begins `(?` raises `ValueError`.

```text recording=urls
normalize(): the forms a regular expression can be filled in as
    normalize('^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z')  ->  [('tickets/%(year)s/%(month)s/', ['year', 'month'])]
    normalize('^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$')  ->  [('plans/%(floor)s', ['floor']), ('plans/%(floor)s.%(format)s', ['floor', 'format'])]
    normalize('^archive/([0-9]{4})/([0-9]{2})/$')  ->  [('archive/%(_0)s/%(_1)s/', ['_0', '_1'])]
    normalize('^pair/(?P<a>[0-9]+)/(?P=a)/$')  ->  [('pair/%(a)s/%(a)s/', ['a'])]
    normalize('^rooms?/$')  ->  [('room/', [])]
    normalize('^(?:wing/)?rooms/$')  ->  [('rooms/', [])]
    normalize('^room/\\d+/\\w+/$')  ->  [('room/0/x/', [])]
    normalize('^files/.+\\.[a-z]{3}$')  ->  [('files/..aaa', [])]
    normalize('^files/[^/]+/$')  ->  [('files/^/', [])]
    normalize('^(?:east|west)/lift/$')  ->  [('', [])]
    normalize('^lift/(?P<side>east|west)/$')  ->  [('lift/%(side)s/', ['side'])]
    normalize('^sale\\-50%/\\Z')  ->  [('sale-50%/', [])]
    normalize('(?i)^cafe/$')  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
    normalize('^a{,3}/$')  ->  raises ValueError
    normalize('')  ->  [('', [])]
```

For a route written with `path` this is simple. The expression `_route_to_regex` produced is a `^`, escaped literal text, named groups and, for a pattern, a closing `\Z`, so there is one form, the route with each parameter replaced by a gap. The second line is the museum's plan pattern, a regular expression with an optional part that holds a group, and it has two.

Some of the later lines show a rule giving what the writer of the expression did not mean. A class written to exclude a slash, `"[^/]"`, yields its own `^`, a character that class accepts. An alternation outside a capturing group yields the empty form; inside one it is skipped with the rest of the group. A literal `%` is kept as it is, though `%` has a meaning in the string being built. A group that sets a flag raises `ValueError`, and so does a quantifier written without its lower bound, `{,3}`. What comes of the last four is under [Patterns that cannot be reversed](#patterns-that-cannot-be-reversed).

## Choosing a candidate

`URLResolver._reverse_with_prefix` is where a name becomes a path. It refuses a call that gives both positional and keyword arguments, makes sure the tables exist, and takes the candidates filed under the name or the view. Then it tries each form of each candidate, in order, against the arguments (`django/urls/resolvers.py:URLResolver._reverse_with_prefix`).

**The arguments have to fit the parameters.** Positional arguments fit when there are as many of them as the form has parameters, and they are paired off in order, which works for named groups as well as unnamed. Keyword arguments fit when their names are the form's parameters once the names of the candidate's extra arguments are set aside. An extra argument that is not also a parameter may be given or left out, and if it is given, it has to have the value the candidate holds for it.

**Each argument is turned into text.** A parameter with a converter goes through the converter's `to_url`; one without is passed to `str`. If `to_url` raises `ValueError`, this form is passed over.

**The filled-in string is checked against the pattern.** The text is put into the gaps and the result is searched with the pattern's own regular expression, with the script prefix in front of both.

The first form to pass all three is the answer. These are the museum's names, reversed with arguments that fit and with arguments that do not:

```text recording=urls
reverse(): what comes back, and what is refused
    reverse("entrance")  ->  '/'
    reverse("tickets", kwargs={"year": 2026})  ->  '/tickets/2026/'
    reverse("tickets", kwargs={"year": 2026, "month": 3})  ->  '/tickets/2026/03/'
    reverse("tickets", args=[2026, 3])  ->  '/tickets/2026/03/'
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

When several candidates would do, the order of the list decides, and the extra arguments can be used to decide it on purpose. A URLconf of two patterns shows both:

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

Each pattern passes a different value of the extra argument to the view. Given that argument, `reverse` returns the address of the pattern whose value it is. Given nothing, both fit, and it returns the address of the one written last.

Before a path is returned it is escaped for use in a URL: every character is replaced by a percent escape unless it is an ASCII letter or digit, one of the punctuation marks a path segment may hold, or the slash between segments. And a result that begins with two slashes has the second replaced by `%2F`, so that a browser cannot read the path as the name of another host (`django/utils/http.py:escape_leading_slashes`).

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

The check against the pattern is made before the escaping, on the text as a path arrives decoded, and the escaping is then applied to the same text. The last two lines show the order. A name with a space in it passes an expression that allows spaces and comes back with the space escaped; the same name given already escaped does not pass, because the expression allows no percent sign.

## Patterns that cannot be reversed

`normalize` is a small reader of regular expressions, written for the expressions URLs usually have, and a pattern can resolve perfectly well and still defeat it. How much is lost depends on where the failure happens.

```text recording=urls
Patterns that resolve and cannot be reversed, and how far the failure reaches
    ALTERNATIVES is path("about/", views.entrance, name="about") and re_path(r"^(?:east|west)/lift/$", views.entrance, name="lift")
      resolve("/west/lift/", urlconf=ALTERNATIVES).url_name  ->  'lift'
      reverse("lift", urlconf=ALTERNATIVES)  ->  raises NoReverseMatch
      reverse("about", urlconf=ALTERNATIVES)  ->  '/about/'
    PERCENT is path("about/", views.entrance, name="about") and path("sale-50%/", views.shop, name="sale")
      resolve("/sale-50%/", urlconf=PERCENT).url_name  ->  'sale'
      reverse("sale", urlconf=PERCENT)  ->  raises ValueError
      reverse("about", urlconf=PERCENT)  ->  '/about/'
    FLAGGED is path("about/", views.entrance, name="about") and re_path(r"(?i)^cafe/$", views.entrance, name="cafe")
      resolve("/CAFE/", urlconf=FLAGGED).url_name  ->  'cafe'
      reverse("cafe", urlconf=FLAGGED)  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
      reverse("about", urlconf=FLAGGED)  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
    CAFE is [re_path(r"(?i)^cafe/$", views.entrance, name="cafe")], and INCLUDING is path("about/", views.entrance, name="about") and path("food/", include((CAFE, "food")))
      reverse("about", urlconf=INCLUDING)  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
```

| what the pattern holds | where reversing fails | what is lost |
|---|---|---|
| an alternation outside a capturing group, as in ALTERNATIVES | `normalize` gives one empty form, which here does not pass the check against the expression | that name, with `NoReverseMatch` |
| a literal `%`, as in PERCENT, whose pattern was written with `path` | the form keeps the `%`, and Python's `%` operator tries to read it as a gap when the form is filled in | that name, here with `ValueError` |
| a construct `normalize` raises for: a group that sets a flag, as in FLAGGED, or a quantifier written `{,3}` | inside `_populate`, so the tables are never finished, and each later call tries again and fails again | every name of the URLconf, the well-formed ones included |

*Three ways a pattern that resolves can fail to reverse, by the URLconfs of the recording above.*

The last line of the recording is the third failure passing upwards. `_populate` of a resolver runs `_populate` of every resolver among its entries, so a URLconf that includes the unreadable one, plainly or under a namespace, cannot reverse its own names either.

Mixing named and unnamed groups in one expression is a trap of another kind. Resolving passes the view only the named one. `normalize` makes a gap of each, the unnamed one under the name `"_0"`, so the name can be reversed with a positional argument for each group and not with the keyword argument the view receives:

```text recording=urls
An expression with an unnamed group and a named one: what resolving passes on, and what reversing asks for
    MIXED is a URLconf of one pattern: re_path(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$", views.tickets, name="mixed")
      resolve('/mixed/2026/03/', urlconf=MIXED)  ->  views.tickets, args (), kwargs {'month': '03'}
      normalize(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$")  ->  [('mixed/%(_0)s/%(month)s/', ['_0', 'month'])]
      reverse("mixed", urlconf=MIXED, kwargs={"month": "03"})  ->  raises NoReverseMatch
      reverse("mixed", urlconf=MIXED, args=[2026, "03"])  ->  '/mixed/2026/03/'
```

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

`reverse_lazy` is `reverse` wrapped by `lazy`: calling it returns a stand-in at once and reverses nothing, and the stand-in calls `reverse` each time it is used as a string. It is for a URL that is wanted before the URLconf can be read, which means in code that runs at import time: an attribute in the body of a class-based view, an argument to a decorator, the default of a parameter. Such code is often imported by the URLconf itself, and a plain `reverse` there asks for patterns that do not yet exist ([From a URLconf to a tree](urlconf.md#when-the-import-fails)) (`django/urls/base.py:reverse_lazy`, `django/utils/functional.py:lazy`).

```text recording=urls
reverse_lazy(): nothing is reversed until the text is asked for
    type(reverse_lazy("entrance")).__mro__[1].__name__  ->  'Promise'
    str(reverse_lazy("entrance"))  ->  '/'
    reverse_lazy("no-such-name") is not None  ->  True
    str(reverse_lazy("no-such-name"))  ->  raises NoReverseMatch
```

The stand-in's class is a subclass of `Promise`, the base of every class that `lazy` makes. The price of the delay is the last two lines: a name that does not exist is not noticed when the stand-in is made, only when something asks it for its text.

## Who calls `reverse`

Among the callers of `reverse` within Django: the template tag `{% url %}` resolves its arguments in the template's context and calls `reverse` ([Templates](../templates.md)) (`django/template/defaulttags.py:URLNode.render`). The shortcut `redirect` goes through `resolve_url`. Unless its argument is an object with a `get_absolute_url` method or a path that begins `"./"` or `"../"`, that function tries the argument as a name to reverse, and when `reverse` raises `NoReverseMatch` and the argument contains a slash or a dot, it takes it to be a URL already ([The shortcuts](../views/shortcuts.md#redirect-and-resolve_url)) (`django/shortcuts.py:resolve_url`). The admin reverses the addresses of its own views ([The admin](../admin.md)).
