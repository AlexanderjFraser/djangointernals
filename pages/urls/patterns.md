---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Routes, regular expressions and converters

How a piece of a path is matched. `RoutePattern` expands the route given to `path` into a regular expression with `_route_to_regex`, a converter supplies each parameter's part of the expression and converts what it captures, and `RegexPattern` matches an expression written by hand.

An entry of a URLconf, a `URLPattern` or a `URLResolver`, does not match a path itself. It holds a **matcher** as its `pattern`, and asks the matcher (`django/urls/resolvers.py:URLPattern`). The method that does the work is `match`: it is given what is left of a path, and returns `None`, or three things, the text that remains after the part it accepted, a tuple of positional arguments, and a dictionary of keyword arguments.

Django has three classes of matcher. They have no base class in common; the two that `path` and `re_path` make share one mixin, `CheckURLMixin`, for the system checks.

| class | made by | written as | matches by | captures |
|---|---|---|---|---|
| `RoutePattern` | `path` | a route, with parameters in angle brackets | comparing strings when the route has no parameters, and otherwise a regular expression expanded from the route | keyword arguments, each passed through its converter |
| `RegexPattern` | `re_path`; Django itself, for the `"^/"` of a root resolver and for the resolver it makes to reverse a name inside a namespace ([Namespaces](namespaces.md)) | a regular expression | the expression as written | named groups as keyword arguments, or else unnamed groups as positional ones; never converted |
| `LocalePrefixPattern` | `i18n_patterns` | nothing: its text is worked out from the active language each time it is used | comparing strings | nothing |

*The three classes of matcher. The third is described in [Language prefixes and translated routes](i18n.md).*

A `RoutePattern` or a `RegexPattern` is made knowing whether it stands for a pattern or for a resolver, by the argument `is_endpoint=True` or `is_endpoint=False`. A route obeys the flag completely: a pattern's route must account for the whole of the text it is given, and a resolver's only for the beginning. An expression written by hand is treated differently, as its own heading says below.

## A route is expanded into a regular expression

`_route_to_regex` turns a route into the text of a regular expression, and returns that text with a dictionary from each parameter's name to its converter. A `RoutePattern` calls it as it is made, which is as its call of `path` runs, during the import of the URLconf (`django/urls/resolvers.py:RoutePattern.__init__`, `django/urls/resolvers.py:_route_to_regex`).

The function goes through the route looking for parameters, each a pair of angle brackets holding a name, or a converter's name, a colon and a name. The text between parameters is literal, and is escaped so that a dot or a plus in a route means itself. A parameter becomes a named group, and the body of the group is a regular expression the converter supplies: `<int:year>` becomes `(?P<year>[0-9]+)`. A parameter that names no converter gets `str`. The expression begins with `^`, and for a pattern it ends with `\Z`.

This recording watches `path` being called four times. In it, and wherever the recording shows an expression, the text is written the way Python writes a string, so a backslash appears doubled: the `\\Z` that ends an expression is `\Z`.

```text recording=urls
path() turns its route into a regular expression as it is called, and the result is kept
    after the import of the URLconf: _route_to_regex.cache_info()  ->  CacheInfo(hits=2, misses=11, maxsize=128, currsize=11)
    the script calls path("lifts/<int:floor>/", views.plan)
      path('lifts/<int:floor>/', views.plan)
        _route_to_regex('lifts/<int:floor>/', is_endpoint=True)  ->  ('^lifts/(?P<floor>[0-9]+)/\\Z', {'floor': IntConverter})
        -> a URLPattern: name None, default_args {}
    and calls it again
      path('lifts/<int:floor>/', views.plan)  ->  a URLPattern: name None, default_args {}
    the script calls path("", views.entrance), a route the URLconf has already used
      path('', views.entrance)  ->  a URLPattern: name None, default_args {}
    the script calls path("lifts/", include([]))
      path('lifts/', what include returned)
        _route_to_regex('lifts/', is_endpoint=False)  ->  ('^lifts/', {})
        -> a URLResolver: app_name None, namespace None, default_kwargs {}
```

`_route_to_regex` is wrapped in `functools.lru_cache`, which keeps the 128 results most recently used, and its body ran under the first and the last of the four calls only. The second repeated a route, and the third used the empty route, which the museum's URLconf had expanded as it was imported. The first line under the title is the cache's count after that import: eleven expansions, and two calls answered from the cache. The last call is for an include, and its expression has no `\Z`.

These are the matchers of the museum's entries, each with the expression made from its route, read back from the tree:

```text recording=urls
The matcher of each entry in the tree, and the regular expression made from its route
    RoutePattern '', a view's  ->  regex '^\\Z'
    RoutePattern 'tickets/<int:year>/', a view's  ->  regex '^tickets/(?P<year>[0-9]+)/\\Z', converters {'year': IntConverter}
    RoutePattern 'tickets/<int:year>/<month:month>/', a view's  ->  regex '^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z', converters {'year': IntConverter, 'month': MonthConverter}
    RoutePattern 'east/', an include's  ->  regex '^east/'
    RoutePattern '', a view's  ->  regex '^\\Z'
    RoutePattern 'rooms/<int:room>/', a view's  ->  regex '^rooms/(?P<room>[0-9]+)/\\Z', converters {'room': IntConverter}
    RoutePattern 'rooms/<int:room>/audio/', an include's  ->  regex '^rooms/(?P<room>[0-9]+)/audio/', converters {'room': IntConverter}
    RoutePattern '<slug:track>/', a view's  ->  regex '^(?P<track>[-a-zA-Z0-9_]+)/\\Z', converters {'track': SlugConverter}
    RoutePattern 'west/', an include's  ->  regex '^west/'
    RoutePattern 'shop/', an include's  ->  regex '^shop/'
    RoutePattern '', a view's  ->  regex '^\\Z'
    RoutePattern '<slug:item>/', a view's  ->  regex '^(?P<item>[-a-zA-Z0-9_]+)/\\Z', converters {'item': SlugConverter}
    RegexPattern '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$', a view's  ->  regex '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'
    RoutePattern 'files/<path:name>', a view's  ->  regex '^files/(?P<name>.+)\\Z', converters {'name': PathConverter}
```

The end is anchored with `\Z`, which matches only at the very end of the text, where `$` would also match just before a final newline. A path that ends in a newline does not match a route that lacks one:

```text recording=urls
resolve('/tickets/2026/')  ->  views.tickets, args (), kwargs {'year': 2026}
...
resolve('/tickets/2026/\n')  ->  raises Resolver404
```

A resolver's expression has no anchor at its end, since it has to accept a beginning and leave the rest. Nothing requires what it accepts to stop at a slash. The slash that separates an include's part of a path from the rest is there because a route puts it there, by convention the include's own, which ends with one:

```text recording=urls
An include's route is matched as a prefix, and nothing puts a slash after it
    SLASHLESS is a URLconf of one entry: path("east", include("museum.gallery.urls"), {"wing": "east"})
    resolve('/east/rooms/12/', urlconf=SLASHLESS)  ->  raises Resolver404
    resolve('/eastrooms/12/', urlconf=SLASHLESS)  ->  views.room, args (), kwargs {'wing': 'east', 'room': 12}
```

The first lines of the next recording are one route expanded with a converter named and with none, where the parameter gets `str`. The rest are the mistakes `_route_to_regex` refuses, each with an `ImproperlyConfigured` that stops the import of the URLconf: a converter that is not registered, white space inside the angle brackets, and a parameter whose name is not a Python identifier.

```text recording=urls
What a route expands to with and without a converter named, and the routes path() refuses
    path("lifts/<int:floor>/", views.plan).pattern.regex.pattern  ->  '^lifts/(?P<floor>[0-9]+)/\\Z'
    path("lifts/<floor>/", views.plan).pattern.regex.pattern  ->  '^lifts/(?P<floor>[^/]+)/\\Z'
    type(path("lifts/<floor>/", views.plan).pattern.converters["floor"]).__name__  ->  'StringConverter'
    path("lifts/<floor:number>/", views.plan)  ->  raises ImproperlyConfigured: URL route 'lifts/<floor:number>/' uses invalid converter 'floor'.
    path("lifts/<int:floor number>/", views.plan)  ->  raises ImproperlyConfigured: URL route 'lifts/<int:floor number>/' cannot contain whitespace in angle brackets <…>.
    path("lifts/<int:2nd>/", views.plan)  ->  raises ImproperlyConfigured: URL route 'lifts/<int:2nd>/' uses parameter name '2nd' which isn't a valid Python identifier.
```

One kind of route is expanded more than once. A route may be a lazily translated string, whose text depends on the language in use, and such a route is expanded again the first time its compiled expression is asked for under each language ([Language prefixes and translated routes](i18n.md#a-route-that-is-a-translated-string)).

## `RoutePattern.match`

When a path is matched, a route with no parameters never reaches the regular expression. `RoutePattern.match` tests for converters first, and without any it compares strings: a pattern's route must equal the text, and a resolver's must be what the text starts with. Only a route with parameters is matched with the expression, searched for at the start of the text (`django/urls/resolvers.py:RoutePattern.match`).

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

A project adds its own with `register_converter`, which takes a class and a name. It makes one instance of the class, files it in `REGISTERED_CONVERTERS`, and empties the two caches that were built from the registry, the dictionary of all converters and the expansions of routes. A name already in use, by a default or by an earlier registration, raises `ValueError`. Since a route is expanded as its call of `path` runs, a converter has to be registered before the call of `path` for any route that uses it, as the museum's URLconf does in its first line (`django/urls/converters.py:register_converter`).

One instance serves every route that names the converter, in every thread, for the life of the process. The dictionary that `get_converters` returns holds instances, and `_route_to_regex` hands the same instance to each matcher. A converter is therefore written to keep no state (`django/urls/converters.py:get_converters`).

> **Changed in 6.0.** `register_converter` refuses a name that is already registered. Overriding an existing converter by registering its name again was deprecated in 5.1, and since 6.0 it raises.

The museum registers one converter, for a month written as two digits:

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

Its regular expression accepts any two digits, and `to_python` narrows that to twelve of them. These lines are from a recorded request for `"/tickets/2026/13/"`, at the point where the root resolver tries its two patterns for tickets. A matcher's call is written down only where it matched or where a converter refused, so the first pattern, whose expression did not match, is one line.

```text recording=urls
URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/')  ->  None
URLPattern.resolve('tickets/2026/13/')  ('tickets/<int:year>/<month:month>/')
  RoutePattern.match('tickets/2026/13/')
    IntConverter.to_python('2026')  ->  2026
    MonthConverter.to_python('13')  raises ValueError
    -> None
  -> None
```

In the second pattern the expression matched, the year was converted, and the month's converter raised. The matcher returned `None`, and so did the pattern. To the rest of the system a refusal by a converter and a failure of the regular expression are the same event, and both end, when nothing else matches, in a 404.

## `RegexPattern`

A `RegexPattern` keeps the expression it was given, and converts nothing: `RegexPattern.match` never looks at converters (`django/urls/resolvers.py:RegexPattern.match`).

### Only one kind of expression is anchored for you

A pattern's expression that ends in `$` is matched with `re.Pattern.fullmatch`, which requires the whole text and, unlike `$` alone, does not let a trailing newline pass. Every other expression, a resolver's or a pattern's without the `$`, is matched with `re.Pattern.search`, which looks for it anywhere in the text. So nothing but the expression's own `^` holds such a match to the start of what is left of the path, and nothing but its own `$` holds it to the end.

```text recording=urls
Regular expressions written with re_path(): what holds a match to the start and to the end of the text
    ENDS is a URLconf of four patterns:
      re_path(r"^tower/$", views.shop, name="tower")
      re_path(r"^press/", views.shop, name="press")
      re_path(r"cafe/$", views.shop, name="cafe")
      re_path(r"lift/", views.shop, name="lift")
    resolve('/tower/', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
    resolve('/tower/\n', urlconf=ENDS)  ->  raises Resolver404
    resolve('/press/', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
    resolve('/press/2026/release.pdf', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
    resolve('/cafe/', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
    resolve('/ground/cafe/', urlconf=ENDS)  ->  raises Resolver404
    resolve('/ground/lift/up', urlconf=ENDS)  ->  views.shop, args (), kwargs {}
```

The tower's expression ends in `$`, so it is matched whole, and the path with a newline after it is refused. The pattern for the press has a `^` and no `$`, and serves whatever begins with its expression. The café's has a `$` and no `^`, and matching the whole text holds it at both ends all the same. The lift's has neither, and matches in the middle of a path.

### Groups decide the arguments

If the expression has named groups, they are the keyword arguments, and unnamed groups are ignored. A named group that took no part in the match, because it stands in an optional part of the expression, is left out, and so the view's own default, where it has one, applies. If no group is named, every group is a positional argument, and one that took no part is passed as `None`. Nothing is converted: the museum's plan view gets its floor as the text `'2'`.

```text recording=urls
resolve('/plans/2')  ->  views.plan, args (), kwargs {'floor': '2'}
resolve('/plans/2.pdf')  ->  views.plan, args (), kwargs {'floor': '2', 'format': 'pdf'}
resolve('/plans/2.png')  ->  raises Resolver404
```

A second URLconf has the other cases: unnamed groups alone, a named group beside an unnamed one, and an unnamed group that takes no part in the match.

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

## Compiled on first use

Neither `RoutePattern` nor `RegexPattern` compiles its expression as it is made. On both classes the attribute `regex` is a descriptor, an object on the class that is run when the attribute is read (`django/urls/resolvers.py:LocaleRegexRouteDescriptor`, `django/urls/resolvers.py:LocaleRegexDescriptor`). Its first read on a matcher whose route is an ordinary string compiles the expression and stores the result in the matcher's own dictionary under the same name. Python looks there before it consults a descriptor of this kind, so every later read finds the compiled expression directly.

For an expression given to `re_path`, that first read is also the first time anything compiles what was written. `re_path` keeps the expression as text, and one that is not valid raises `ImproperlyConfigured` when its matcher is first asked for `regex`, as it is when a path is matched against it or the tables for reversing are built, and not when the URLconf is imported.

A matcher that is never asked for its `regex` never compiles one. The recording looked at the matcher of each entry in the museum's tree twice: once after every path it had resolved up to that point, and again after the first call of `reverse` for the museum's URLconf.

```text recording=urls
After every path above was resolved, and before any name of museum.urls is reversed: which entries of its tree have a matcher with a compiled expression
    RoutePattern ''  ->  not compiled
    RoutePattern 'tickets/<int:year>/'  ->  compiled
    RoutePattern 'tickets/<int:year>/<month:month>/'  ->  compiled
    RoutePattern 'east/'  ->  not compiled
    RoutePattern ''  ->  not compiled
    RoutePattern 'rooms/<int:room>/'  ->  compiled
    RoutePattern 'rooms/<int:room>/audio/'  ->  compiled
    RoutePattern '<slug:track>/'  ->  compiled
    RoutePattern 'west/'  ->  not compiled
    RoutePattern 'shop/'  ->  not compiled
    RoutePattern ''  ->  not compiled
    RoutePattern '<slug:item>/'  ->  compiled
    RegexPattern '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'  ->  compiled
    RoutePattern 'files/<path:name>'  ->  compiled
```

```text recording=urls
After that first reverse with museum.urls: which entries of its tree have a matcher with a compiled expression
    RoutePattern ''  ->  compiled
    RoutePattern 'tickets/<int:year>/'  ->  compiled
    RoutePattern 'tickets/<int:year>/<month:month>/'  ->  compiled
    RoutePattern 'east/'  ->  compiled
    RoutePattern ''  ->  compiled
    RoutePattern 'rooms/<int:room>/'  ->  compiled
    RoutePattern 'rooms/<int:room>/audio/'  ->  compiled
    RoutePattern '<slug:track>/'  ->  compiled
    RoutePattern 'west/'  ->  compiled
    RoutePattern 'shop/'  ->  compiled
    RoutePattern ''  ->  compiled
    RoutePattern '<slug:item>/'  ->  compiled
    RegexPattern '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$'  ->  compiled
    RoutePattern 'files/<path:name>'  ->  compiled
```

Resolving had compiled only the expressions it used. The routes without parameters, which `RoutePattern.match` compares as text, had none, however often they had matched. Building the tables for reversing reads the expression of every entry's matcher, and after it all fourteen are compiled. For a route that is a lazily translated string the descriptor compiles for the language in use at that moment and keeps the result by language code, which [Language prefixes and translated routes](i18n.md#a-route-that-is-a-translated-string) describes (`django/urls/resolvers.py:LocaleRegexRouteDescriptor`).
