---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The URL checks, and listing the patterns

What goes over the whole tree with no path or name in hand: the system checks tagged urls, in which every resolver and pattern checks itself, and the tools that list a project's addresses, `extract_views_from_urlpatterns`, `simplify_regex` and the command listurls.

Resolving looks at as much of the tree as one path needs. Other code goes over all of it, entry by entry: the building of the tables for reversing, the checks that look for mistakes in a URLconf when a management command runs them, and the tools that print what addresses a project has. This section has the checks and the tools, and both are walks down the same lists `URLResolver.resolve` searches.

## The checks

`django/core/checks/urls.py` registers four functions under the tag urls. How the system checks are registered and run, and which commands run them, is in [The system checks](../commands/checks.md). All but the one about settings do nothing in a project that has no `ROOT_URLCONF`.

- `check_url_config` asks the tree to check itself. It gets the root resolver from `get_resolver` and passes it to `check_resolver`, which calls the `check` method of whatever it is given. `URLResolver.check` passes each of its entries to `check_resolver` in turn, so the walk goes down through every include. A `URLPattern` checks its name, has its matcher check the route, and checks its view. An entry with neither a `check` method nor a `resolve` method is not a pattern at all, and is reported as that (`django/core/checks/urls.py:check_url_config`, `django/core/checks/urls.py:check_resolver`, `django/urls/resolvers.py:URLResolver.check`, `django/urls/resolvers.py:URLPattern.check`).
- `check_url_namespaces_unique` collects every chain of instance namespaces in the tree, each namespace joined to those above it with colons, and warns of any that occurs more than once (`django/core/checks/urls.py:check_url_namespaces_unique`).
- `check_url_settings` looks at `settings.STATIC_URL` and `settings.MEDIA_URL`, each of which must end in a slash if it is set (`django/core/checks/urls.py:check_url_settings`).
- `check_custom_error_handlers` tries the error views. For each of the four it asks the root resolver for the view, as the handler would when a request failed, and then tests whether the view accepts the right number of positional arguments: two, the request and the exception, or for the 500 view one (`django/core/checks/urls.py:check_custom_error_handlers`).

The recording has a URLconf with one of each mistake, and calls the four functions over it one at a time. The view it names for 403 takes the request and nothing else, and the module has no view of the name it gives for 404.

```python
# museum/urls_mistakes.py
cafe_patterns = [
    path("", views.shop, name="cafe"),
]

terrace_patterns = [
    path("/seats", views.shop, name="seats"),
]

urlpatterns = [
    path("/lost", views.entrance, name="lost"),
    path("cloakroom/", views.entrance, name="cloak:room"),
    path("^lifts/$", views.entrance, name="lifts"),
    path("stairs/<int:floor/", views.entrance, name="stairs"),
    path("tour/", views.Tour, name="tour"),
    ("garden/", "museum.views.entrance"),
    re_path(r"^cafe/$", include(cafe_patterns)),
    re_path(r"^terrace/$", include(terrace_patterns)),
    path("north/", include("museum.gallery.urls", namespace="annexe")),
    path("south/", include("museum.gallery.urls", namespace="annexe")),
]

handler403 = views.lost
handler404 = "museum.views.nowhere"
```

```text recording=urls
The four checks tagged urls, each called over museum.urls_mistakes, with STATIC_URL = 'static'
    check_url_config
      urls.W002, Warning: Your URL pattern '/lost' [name='lost'] has a route beginning with a '/'. Remove this slash as it is unnecessary. If this pattern is targeted in an include(), ensure the include() pattern has a trailing '/'.
      urls.W003, Warning: Your URL pattern 'cloakroom/' [name='cloak:room'] has a name including a ':'. Remove the colon, to avoid ambiguous namespace references.
      2_0.W001, Warning: Your URL pattern '^lifts/$' [name='lifts'] has a route that contains '(?P<', begins with a '^', or ends with a '$'. This was likely an oversight when migrating to django.urls.path().
      urls.W010, Warning: Your URL pattern 'stairs/<int:floor/' [name='stairs'] has an unmatched '<' bracket.
      urls.E009, Error: Your URL pattern 'tour/' [name='tour'] has an invalid view, pass Tour.as_view() instead of Tour.
      urls.E004, Error: Your URL pattern ('garden/', 'museum.views.entrance') is invalid. Ensure that urlpatterns is a list of path() and/or re_path() instances.
        hint: Try using path() instead of a tuple.
      urls.W001, Warning: Your URL pattern '^cafe/$' uses include with a route ending with a '$'. Remove the dollar from the route to avoid problems including URLs.
      urls.W002, Warning: Your URL pattern '/seats' [name='seats'] has a route beginning with a '/'. Remove this slash as it is unnecessary. If this pattern is targeted in an include(), ensure the include() pattern has a trailing '/'.
    check_url_namespaces_unique
      urls.W005, Warning: URL namespace 'annexe' isn't unique. You may not be able to reverse all URLs in this namespace
      urls.W005, Warning: URL namespace 'annexe:audio' isn't unique. You may not be able to reverse all URLs in this namespace
    check_url_settings
      urls.E006, Error: The STATIC_URL setting must end with a slash.
    check_custom_error_handlers
      urls.E007, Error: The custom handler403 view 'museum.views.lost' does not take the correct number of arguments (request, exception).
      urls.E008, Error: The custom handler404 view 'museum.views.nowhere' could not be imported.
        hint: Could not import 'museum.views.nowhere'. View does not exist in module museum.views.
```

Most of these are slips that would otherwise be silent, because the URLconf imports and the wrong pattern simply never matches what was meant. The route for the stairs has an opening bracket and no closing one, so it has no parameter and is matched as literal text. The route for the lifts is taken as a route, escaped, and matched as literal text too. The view for the tour is a class, which is callable, so `path` accepted it; what the handler would call with a request is the class itself.

The check of error views is looser and tighter than a real call. The handler passes the exception by keyword, as an argument named exception, and the check only counts positional arguments. A view whose second parameter has another name passes the check and fails when it is used, and one that takes the exception as a keyword-only argument works and is reported.

The recording shows one oddity of the walk. `URLResolver.check` returns the messages its entries produced, and checks its own matcher only when they produced none. The URLconf has two includes whose expressions end in `$`. The café's one entry is clean, and its `$` is reported. The terrace's entry has a warning of its own, for the slash in front of its route, and the terrace's `$` is not mentioned: it will be once the entry below it is put right.

| id | reported by | for |
|---|---|---|
| `"urls.W001"` | `RegexPattern._check_include_trailing_dollar` | an include whose regular expression ends in an unescaped `$`, which leaves the included patterns only the empty string to match |
| `"urls.W002"` | `CheckURLMixin._check_pattern_startswith_slash` | a route that begins with a slash and whose expression does not end in one, which is any such route of a pattern written with `path`; the check is skipped when `settings.APPEND_SLASH` is false |
| `"urls.W003"` | `URLPattern._check_pattern_name` | a pattern's name with a colon in it, which `reverse` would take for a namespace |
| `"urls.E004"` | `get_warning_for_invalid_pattern` | an entry of a list that is not a pattern or a resolver: a string, a tuple |
| `"urls.W005"` | `check_url_namespaces_unique` | a chain of namespaces that is not unique |
| `"urls.E006"` | `check_url_settings` | one of the two settings not ending in a slash |
| `"urls.E007"` | `check_custom_error_handlers` | an error view that cannot be called with two positional arguments, or the 500 view with one |
| `"urls.E008"` | `check_custom_error_handlers` | an error view that `get_callable` cannot produce: a dotted name that cannot be imported, or a value that is not a view |
| `"urls.E009"` | `URLPattern._check_callback` | a view that is a subclass of `View` passed as the class, without `as_view` |
| `"urls.W010"` | `RoutePattern._check_pattern_unmatched_angle_brackets` | a route with an angle bracket that has no partner |
| `"2_0.W001"` | `RoutePattern.check` | a route given to `path` that holds `(?P<`, begins with `^` or ends with `$`: a regular expression where a route was meant |

*The messages of the URL checks, and the code that makes each. The letter in an id is its level: W for a warning, E for an error.*

`check_url_config` reads `url_patterns` to do its work, which makes it one of the things that import a project's whole URLconf ([From a URLconf to a tree](urlconf.md#who-reads-the-list-first)).

## Listing what a project serves

A URLconf is code, and the addresses it serves are spread over as many modules as it includes. A pair of functions turns the tree back into a flat list for a person to read (`django/urls/utils.py:extract_views_from_urlpatterns`, `django/urls/utils.py:simplify_regex`).

`extract_views_from_urlpatterns` is given a list of entries and goes down it. For a resolver it calls itself on the resolver's list, carrying along the routes met so far, joined, and the instance namespaces met so far. For a pattern it adds a tuple to its result: the view, the joined routes with the pattern's own at the end, the namespaces, and the name. It tells the two kinds of entry apart by whether an entry has `url_patterns` or `callback`. These are some of the tuples it returns for the museum's tree:

```text recording=urls
extract_views_from_urlpatterns(get_resolver().url_patterns): a tuple for each pattern
    (views.entrance, '', None, 'entrance')
    (views.tickets, 'tickets/<int:year>/', None, 'tickets')
    (views.tickets, 'tickets/<int:year>/<month:month>/', None, 'tickets')
    (views.wing, 'east/', ['east'], 'wing')
    (views.room, 'east/rooms/<int:room>/', ['east'], 'room')
    (views.track, 'east/rooms/<int:room>/audio/<slug:track>/', ['east', 'audio'], 'track')
...
    (views.shop, 'shop/', [], 'shop')
    (views.item, 'shop/<slug:item>/', [], 'item')
    (views.plan, '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$', None, 'plan')
    (views.download, 'files/<path:name>', None, 'download')
```

The third item is `None` for a pattern in the list the walk began with, and a list, which may be empty, for a pattern under an include. Each address is the routes as written, joined: a route's parameters are still in angle brackets, and a regular expression is still a regular expression. `simplify_regex` makes the second kind readable. It deletes each group written `(?:…)`, with whatever is inside it, and replaces each named group with its name in angle brackets and each group that is left with `<var>`. It takes out the anchors `^`, `$`, `\A`, `\Z`, `\b` and `\B` and the quantifiers `?`, `*` and `+` where they stand unescaped; an escaped `^`, `$`, `?`, `*` or `+` keeps its character and loses its backslash, as an escaped dot, slash, parenthesis, underscore or hyphen does. Then it puts a slash in front if there is none.

```text recording=urls
simplify_regex(): a regular expression made into an address a person can read
    simplify_regex('^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z')  ->  '/tickets/<year>/<month>/'
    simplify_regex('^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$')  ->  '/plans/<floor>'
    simplify_regex('^archive/([0-9]{4})/([0-9]{2})/$')  ->  '/archive/<var>/<var>/'
    simplify_regex('east/rooms/<int:room>/audio/<slug:track>/')  ->  '/east/rooms/<int:room>/audio/<slug:track>/'
```

Deleting a group that does not capture deletes whatever is inside it, so the optional format of the museum's plan address is gone from the second line. The fourth is a route, and gains only the slash in front.

The command listurls is those two functions and some formatting. It imports the module `ROOT_URLCONF` names and reads the list from it directly, without the resolver. It extracts, simplifies each address, names each view by its module and its name, joins a pattern's namespaces to its name with colons, and prints the rows, sorted unless it is told otherwise (`django/core/management/commands/listurls.py:Command.get_url_patterns`, `django/core/management/commands/listurls.py:Command.handle`). The recording runs it with `call_command`:

```text recording=urls
call_command("listurls"), with ROOT_URLCONF = 'museum.urls': each line as printed, without the spaces at its end
    /                                           museum.views.entrance  entrance
    /east/                                      museum.views.wing      east:wing
    /east/rooms/<int:room>/                     museum.views.room      east:room
    /east/rooms/<int:room>/audio/<slug:track>/  museum.views.track     east:audio:track
    /files/<path:name>                          museum.views.download  download
    /plans/<floor>                              museum.views.plan      plan
    /shop/                                      museum.views.shop      shop
    /shop/<slug:item>/                          museum.views.item      item
    /tickets/<int:year>/                        museum.views.tickets   tickets
    /tickets/<int:year>/<month:month>/          museum.views.tickets   tickets
    /west/                                      museum.views.wing      west:wing
    /west/rooms/<int:room>/                     museum.views.room      west:room
    /west/rooms/<int:room>/audio/<slug:track>/  museum.views.track     west:audio:track
```

The names in the last column are the names to reverse with.

> **New in 6.2.** The command listurls was added in this release.

The admin's documentation pages list a project's views with the same two functions (`django/contrib/admindocs/views.py:ViewIndexView`).
