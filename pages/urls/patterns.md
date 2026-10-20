---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Routes, regular expressions and converters

The matcher an entry of a URLconf holds decides how much of a path the entry accepts, and what it captures. A route given to `path` gets a `RoutePattern`, which expands the route into a regular expression in which a converter supplies each parameter's part and turns what that part captures into a value, while a regular expression given to `re_path` gets a `RegexPattern`, which keeps it as written.

An entry of a URLconf, a `URLPattern` or a `URLResolver`, does not match a path itself. It holds a **matcher** as its `pattern`, and asks the matcher (`django/urls/resolvers.py:URLPattern`). The method that does the work is `match`: it is given what is left of a path, and returns `None`, or three things, the text that remains after the part it accepted, a tuple of positional arguments, and a dictionary of keyword arguments.

Django has three classes of matcher.

| class | made by | written as | matches by | captures |
|---|---|---|---|---|
| `RoutePattern` | `path` | a route, with parameters in angle brackets | comparing strings when it has no converters, and otherwise a regular expression expanded from the route | keyword arguments, each passed through its converter |
| `RegexPattern` | `re_path`; and Django itself, for the `"^/"` of a root resolver, and, when `reverse` is given a name inside a namespace that an entry not at `""` leads to, for the routes that lead to it and a `"^/"` above them ([Namespaces](namespaces.md#get_ns_resolver-a-resolver-made-for-the-namespace)) | a regular expression | the expression as written | named groups as keyword arguments, or else unnamed groups as positional ones; never converted |
| `LocalePrefixPattern` | `i18n_patterns` | nothing: its text is worked out from the active language each time it is used | comparing strings | nothing |

*The three classes of matcher. The third is described in [Language prefixes and translated routes](i18n.md).*

A `RoutePattern` or a `RegexPattern` is made knowing whether it stands for a pattern or for a resolver, by the argument `is_endpoint=True` or `is_endpoint=False`. A route obeys the flag completely: a pattern's route must account for the whole of the text it is given, and a resolver's only for the beginning. An expression given to `re_path` obeys it only in part.

The figure sets out the four ways, a row for each, with texts from the museum's recordings: the accepted part may begin only at the start of the text in the first three rows, and must run to its end in the first and the third.

```text figure=what-a-matcher-takes
a matcher is given what is left of the path; the part it accepts, accented, is in brackets

a pattern's route: all of the text
    tickets/<int:year>/, expanded to ^tickets/(?P<year>[0-9]+)/\Z      [tickets/2026/]        refuses tickets/2026/\n
    without parameters, the route must equal the text

a resolver's route: a beginning, the rest left for its list
    east/, compared with the start of the text                           [east/]rooms/12/
    with parameters, an expression that begins with ^ and has no \Z

a pattern's expression that ends in $: all of the text, by fullmatch
    cafe/$                                                                [cafe/]                refuses ground/cafe/

any other expression: wherever search finds it
    lift/                                                                 ground/[lift/]up
```

*Four ways a matcher bounds the text it is given, a row for each, with texts from the museum's recordings: the accent is the part the matcher accepted, and a text after "refuses" was not matched at all. Under each kind of route, a line says how a route without parameters, or with them, is held to the same bound.*

## A route is expanded into a regular expression

`_route_to_regex` turns a route into the text of a regular expression, and returns that text with a dictionary from each parameter's name to its converter. The function goes through the route looking for parameters, each a pair of angle brackets holding a name, or a converter's name, a colon and a name. The text between parameters is literal, and is escaped so that a dot or a plus in a route means itself. A parameter becomes a named group, and the body of the group is a regular expression the converter supplies: `<int:year>` becomes `(?P<year>[0-9]+)`. A parameter that names no converter gets `str`. The expression begins with `^`, and for a pattern it ends with `\Z` (`django/urls/resolvers.py:_route_to_regex`).

A `RoutePattern` calls `_route_to_regex` as it is made, which is as its call of `path` runs, during the import of the URLconf. The function is wrapped in `functools.lru_cache`, which keeps the 128 results most recently used, so a route is expanded as `path` is first called with it, and a later call with the same route, for the same kind of entry and in any URLconf, takes the expansion from the cache while it is kept there. The matcher keeps the dictionary of converters the cache returns, not a copy of it, so matchers made from one route for the same kind of entry while its expansion is cached share one dictionary between them, and what `URLResolver._populate` writes into it in place, for a namespaced include under a plain one, reaches them all ([Namespaces](namespaces.md#get_ns_resolver-a-resolver-made-for-the-namespace)) (`django/urls/resolvers.py:RoutePattern.__init__`, `django/urls/resolvers.py:_route_to_regex`, `django/urls/resolvers.py:URLResolver._populate`).

Two calls of `path` made by a script, one for a pattern and one for an include, show the expansion running inside the call and returning the expression with its converters, the expression written as Python writes a string, with a backslash doubled:

```text recording=urls
path() turns its route into a regular expression as it is called, and the result is kept
    ...
    the script calls path("lifts/<int:floor>/", views.plan)
      path('lifts/<int:floor>/', views.plan)
        _route_to_regex('lifts/<int:floor>/', is_endpoint=True)  ->  ('^lifts/(?P<floor>[0-9]+)/\\Z', {'floor': IntConverter})
    ...
    the script calls path("lifts/", include([]))
      path('lifts/', what include returned)
        _route_to_regex('lifts/', is_endpoint=False)  ->  ('^lifts/', {})
        ...
```

In the museum's tree each converter has put its own expression into its parameter's group, the month's two digits among them, and the one expression written for `re_path` is kept as it was written:

```text recording=urls
The matcher of each entry in the tree, and the regular expression made from its route
    ...
    RoutePattern 'tickets/<int:year>/', a view's  ->  regex '^tickets/(?P<year>[0-9]+)/\\Z', converters {'year': IntConverter}
    RoutePattern 'tickets/<int:year>/<month:month>/', a view's  ->  regex '^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z', converters {'year': IntConverter, 'month': MonthConverter}
    RoutePattern 'east/', an include's  ->  regex '^east/'
    ...
    RegexPattern '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$', a view's  ->  regex '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'
    RoutePattern 'files/<path:name>', a view's  ->  regex '^files/(?P<name>.+)\\Z', converters {'name': PathConverter}
```

The end of a pattern's expression is anchored with `\Z`, which matches only at the very end of the text, where `$` would also match just before a final newline: the museum's pattern for a year's tickets serves `"/tickets/2026/"` and refuses `"/tickets/2026/\n"`.

A resolver's expression has no anchor at its end, since it has to accept a beginning and leave the rest, and nothing requires what it accepts to stop at a slash. The slash that separates an include's part of a path from the rest is there because a route puts it there, by convention the include's own, which ends with one. An include written `"east"`, without its slash, refuses the address of room 12 of the east wing and serves the same address with the slash left out:

```text recording=urls
An include's route is matched as a prefix, and nothing puts a slash after it
    SLASHLESS is a URLconf of one entry: path("east", include("museum.gallery.urls"), {"wing": "east"})
    resolve('/east/rooms/12/', urlconf=SLASHLESS)  ->  raises Resolver404
    resolve('/eastrooms/12/', urlconf=SLASHLESS)  ->  views.room, args (), kwargs {'wing': 'east', 'room': 12}
```

`_route_to_regex` refuses three mistakes in a route, each with an `ImproperlyConfigured` that names the route and stops the import of the URLconf: a converter that is not registered, white space inside the angle brackets, and a parameter whose name is not a Python identifier. The lines below are those three refusals, without the expansions their block begins with:

```text recording=urls
What a route expands to with and without a converter named, and the routes path() refuses
    ...
    path("lifts/<floor:number>/", views.plan)  ->  raises ImproperlyConfigured: URL route 'lifts/<floor:number>/' uses invalid converter 'floor'.
    path("lifts/<int:floor number>/", views.plan)  ->  raises ImproperlyConfigured: URL route 'lifts/<int:floor number>/' cannot contain whitespace in angle brackets <…>.
    path("lifts/<int:2nd>/", views.plan)  ->  raises ImproperlyConfigured: URL route 'lifts/<int:2nd>/' uses parameter name '2nd' which isn't a valid Python identifier.
```

## `RoutePattern.match`

When a path is matched, a `RoutePattern` with no converters never reaches the regular expression. `RoutePattern.match` tests for converters first, and without any it compares strings: a pattern's route must equal the text, and a resolver's must be what the text starts with, as the museum's `"east/"` is the start of `"east/rooms/12/"`, which it takes, leaving `"rooms/12/"` for its list. Only one with converters is matched with its expression, which, since it begins with `^`, can match only from the start of the text (`django/urls/resolvers.py:RoutePattern.match`).

> **Why.** "Only use regex overhead if there are converters," says the comment above that test (`django/urls/resolvers.py:RoutePattern.match`). A route without parameters is plain text, and comparing it with the text spares the cost of running an expression; so resolving never compiles the expression of a `RoutePattern` without converters, as [When a matcher's expression is compiled](#when-a-matchers-expression-is-compiled) shows.

When the expression matches, every named group has captured a piece of text, and each piece goes to its converter's `to_python`. What comes back is the keyword argument. A converter can refuse: if `to_python` raises `ValueError`, `match` returns `None`, exactly as if the expression had not matched. A route's positional arguments are always empty.

## Converters

A **converter** is an object with three members.

- `regex` is a string: the regular expression for the text this converter accepts. It is placed inside the parameter's group.
- `to_python` is given the text the group captured and returns the value to pass on as the argument. Raising `ValueError` means the text is not, after all, acceptable to this converter, and the pattern does not match.
- `to_url` goes the other way for `reverse`: given a value, it returns the text to put in a path. Raising `ValueError` there means this pattern cannot make a URL for that value.

Five are registered to begin with (`django/urls/converters.py:DEFAULT_CONVERTERS`).

| name | class | accepts | the view is given |
|---|---|---|---|
| `"str"` | `StringConverter` | one or more characters, none of them a slash | the text |
| `"int"` | `IntConverter` | one or more of the digits 0 to 9, so no sign | an `int` |
| `"slug"` | `SlugConverter` | one or more ASCII letters, digits, hyphens and underscores | the text |
| `"uuid"` | `UUIDConverter` | a UUID written with hyphens and with its letters in lower case | a `uuid.UUID` |
| `"path"` | `PathConverter` | one or more characters of any kind but a newline, slashes among them | the text |

*The converters Django registers. `SlugConverter` and `PathConverter` are subclasses of `StringConverter` that change only its `regex`.*

A project adds its own with `register_converter`, which takes a class and a name. It makes one instance of the class, files it in `REGISTERED_CONVERTERS`, and empties the two caches that were built from the registry, the dictionary of all converters and the expansions of routes. Emptying them changes no matcher already made, which keeps the expression and the converters it was given; it lets a route expanded afterwards find the new name. A name already in use, by a default or by an earlier registration, raises `ValueError`. Since a route is expanded as its call of `path` runs, a converter has to be registered before the call of `path` for any route that uses it, as the museum's URLconf does above its patterns (`django/urls/converters.py:register_converter`).

> **Changed in 6.0.** `register_converter` refuses a name that is already registered. Overriding an existing converter by registering its name again was deprecated in 5.1, and since 6.0 it raises.

The museum's converter for the month accepts any two digits by its regular expression, and its `to_python` narrows them to twelve:

```python
class MonthConverter:
    regex = "[0-9]{2}"

    def to_python(self, value):
        month = int(value)
        if not 1 <= month <= 12:
            raise ValueError(f"{value} is not a month")
        return month

    def to_url(self, value):
        if not 1 <= int(value) <= 12:
            raise ValueError(f"{value} is not a month")
        return "%02d" % int(value)
```

To the rest of the system a refusal by a converter and a failure of the regular expression are the same event: the matcher returns `None` for either, and so does its pattern, and both end, when nothing else matches, in a 404. Asked about `"/tickets/2026/13/"` during a request, the two patterns for tickets return `None` alike, the first because its expression does not match, the second because its month's converter raises once the year has been converted:

```text recording=urls
GET /tickets/2026/13/: a converter refuses, and nothing else matches
        ...
        URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/')  ->  None
        URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/<month:month>/')
          RoutePattern.match('tickets/2026/13/')
            IntConverter.to_python('2026')  ->  2026
            MonthConverter.to_python('13')  raises ValueError
            -> None
          -> None
          ...
```

> **Trap.** A converter is written as a class, but Django uses a single instance of it: the one `register_converter` made, or for a default the one its module made as it was imported (`django/urls/converters.py:DEFAULT_CONVERTERS`). `_route_to_regex` puts that instance into the converters of every route that names it, so it serves every route, in every thread, for the life of the process (`django/urls/converters.py:get_converters`). A converter that kept anything on itself between calls would share it among them all, and so a converter is written to keep no state.

## `RegexPattern`

A `RegexPattern` keeps the expression it was given, and converts nothing: `RegexPattern.match` never looks at converters. Nor does it add an anchor to the expression, as `_route_to_regex` adds `\Z` to a pattern's route, and the flag alone does not hold an expression to the end of the text. A pattern's expression that ends in `$` is matched with `re.Pattern.fullmatch`, which requires the whole text and, unlike `$` alone, does not let a trailing newline pass; every other expression, a resolver's or a pattern's without the `$`, with `re.Pattern.search`, under which nothing but its own anchors holds it to the start of the text or to its end (`django/urls/resolvers.py:RegexPattern.match`). So a pattern's expression with a `^` and no anchor at its end serves every path that begins with it, as `"^press/"` does in the URLconf whose café and lift the figure draws:

```text recording=urls
Regular expressions written with re_path(): what holds a match to the start and to the end of the text
    ENDS is a URLconf of four patterns:
      ...
      re_path(r"^press/", views.shop, name="press")
      re_path(r"cafe/$", views.shop, name="cafe")
      re_path(r"lift/", views.shop, name="lift")
    ...
    resolve('/press/2026/release.pdf', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
    resolve('/cafe/', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
    resolve('/ground/cafe/', urlconf=ENDS)  ->  raises Resolver404
    resolve('/ground/lift/up', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
```

### Which groups become arguments

If the expression has named groups, they are the keyword arguments, and unnamed groups are ignored. A named group that took no part in the match, because it stands in an optional part of the expression, is left out, and so the view's own default, where it has one, applies. If no group is named, every group is a positional argument, and one that took no part is passed as `None`. Nothing is converted: the museum's plan pattern resolves `"/plans/2"` with the keyword arguments `{'floor': '2'}`, the floor as text and no format, since the optional group took no part, and `"/plans/2.pdf"` with both, `{'floor': '2', 'format': 'pdf'}`.

A second URLconf has the cases without names: the mixed pattern's unnamed year is lost beside its named month, and the draft's optional group, unmatched, still arrives, as `None`:

```text recording=urls
Regular expressions written with re_path(): which groups become the view's arguments
    GROUPS is a URLconf of three patterns:
      re_path(r"^archive/([0-9]{4})/([0-9]{2})/$", views.tickets, name="archive")
      re_path(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$", views.tickets, name="mixed")
      re_path(r"^draft/([0-9]+)?$", views.tickets, name="draft")
    resolve('/archive/2026/03/', urlconf=GROUPS)  ->  views.tickets, args ('2026', '03'), kwargs {}
    resolve('/mixed/2026/03/', urlconf=GROUPS)  ->  views.tickets, args (), kwargs {'month': '03'}
    resolve('/draft/', urlconf=GROUPS)  ->  views.tickets, args (None,), kwargs {}
```

## When a matcher's expression is compiled

Neither `RoutePattern` nor `RegexPattern` compiles its expression as it is made. On both classes the attribute `regex` is a descriptor, an object on the class that is run when the attribute is read (`django/urls/resolvers.py:LocaleRegexRouteDescriptor`, `django/urls/resolvers.py:LocaleRegexDescriptor`). Its first read on a matcher whose route or expression is an ordinary string compiles the expression and stores the result in the matcher's own dictionary under the same name. Neither descriptor defines `__set__` or `__delete__`, and Python looks in an instance's own dictionary before it runs such a descriptor, so every later read finds the compiled expression there. A route or an expression that is a lazily translated string is compiled instead once for each language, a route given to `_route_to_regex` again each time ([Language prefixes and translated routes](i18n.md#a-route-that-is-a-translated-string)).

For an expression given to `re_path`, that first read is also the first time anything compiles what was written. `re_path` keeps the expression as text, and one that is not valid raises `ImproperlyConfigured`, with the compiler's reason, only when its matcher is asked for `regex`: by `RegexPattern.match` as a path reaches it, or by `URLResolver._populate` as the tables for reversing are built (`django/urls/resolvers.py:LocaleRegexDescriptor._compile`).

> **Trap.** An expression that does not compile is not found out before a path or a name comes to it. The import passes it, and so do the URL checks, which read its text and never compile it ([The URL checks, and listing the patterns](checks.md)) (`django/urls/resolvers.py:RegexPattern.check`). Then every path that reaches its entry raises, one meant for an entry after it as much as one meant for it, and so does every `reverse` with the URLconf, whatever the name, since the tables are built from every entry's expression (`django/urls/resolvers.py:URLResolver._populate`). The descriptor stores nothing when the compile fails, so each raises again, every time (`django/urls/resolvers.py:LocaleRegexDescriptor`).

A matcher that is never asked for its `regex` never compiles one. Before the block below, the recording resolved a run of the museum's paths and reversed none of its names. Resolving compiled the expressions it used and no others: the routes without parameters, compared as text, have none, however often they matched.

```text recording=urls
After every path above was resolved, and before any name of museum.urls is reversed: which entries of its tree have a matcher with a compiled expression
    RoutePattern ''  ->  not compiled
    RoutePattern 'tickets/<int:year>/'  ->  compiled
    ...
    RoutePattern 'east/'  ->  not compiled
    ...
    RoutePattern 'rooms/<int:room>/audio/'  ->  compiled
    ...
    RegexPattern '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'  ->  compiled
    ...
```

Building the tables for reversing reads the expression of every entry's matcher, and after the first `reverse` with the museum's URLconf every one of them is compiled (`django/urls/resolvers.py:URLResolver._populate`).
