---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The URL checks, and listing the patterns

Two of the URL checks and the command listurls go over a project's whole tree of resolvers and patterns with no path or name in hand. Among the checks, `check_url_config` has every entry check itself, and listurls is built on two functions, `extract_views_from_urlpatterns` and `simplify_regex`.

Resolving looks at as much of the tree as one path needs. Other code goes over all of it, entry by entry, down the same lists `URLResolver.resolve` searches: the building of the tables for reversing ([Reversing a name](reversing.md#the-tables)), two of the checks, which look for a URLconf's mistakes when a management command runs them, and the tools that list a project's addresses.

## The four checks tagged urls

`django/core/checks/urls.py` registers four functions under the tag urls. How the system checks are registered and run is in [The system checks](../commands/checks.md). All but the one about settings do nothing in a project that has no `ROOT_URLCONF`.

- `check_url_config` asks the tree to check itself. It passes the root resolver to `check_resolver`, which calls the `check` method of whatever it is given, and `URLResolver.check` passes each of its entries back to `check_resolver`, so the walk goes down through every include, importing the project's whole URLconf ([When a URLconf is imported](import.md#who-reads-the-urlconf-first)). A `URLPattern` checks its name, has its matcher check the route, and checks its view; a matcher checks only the text of its route or expression and never compiles it, so an expression that does not compile passes ([Routes, regular expressions and converters](patterns.md#when-a-matchers-expression-is-compiled)). An entry with neither a `check` method nor a `resolve` method is not a pattern at all, and is reported as that (`django/core/checks/urls.py:check_url_config`, `django/core/checks/urls.py:check_resolver`, `django/urls/resolvers.py:URLResolver.check`, `django/urls/resolvers.py:URLPattern.check`, `django/urls/resolvers.py:RegexPattern.check`).
- `check_url_namespaces_unique` collects every chain of instance namespaces in the tree, each namespace joined to those above it with colons, and warns of any that occurs more than once (`django/core/checks/urls.py:check_url_namespaces_unique`).
- `check_url_settings` looks at `settings.STATIC_URL` and `settings.MEDIA_URL`, each of which must end in a slash if it is set (`django/core/checks/urls.py:check_url_settings`).
- `check_custom_error_handlers` tries the error views. For each of the four it asks the root resolver for the view and tests whether the view can be called with positional arguments alone: two, the request and the exception, or for the 500 view one (`django/core/checks/urls.py:check_custom_error_handlers`).

One of the museum's URLconfs has a mistake of each kind the checks look for in a URLconf. The view it names for 403 takes the request and nothing else, and the module has no view of the name it gives for 404.

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

The module imports without complaint, and the four functions, called over it one at a time, report every slip in it but one: the `$` that ends the terrace's expression.

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

Most of these slips would otherwise be silent. The route for the stairs has an opening bracket and no closing one, so it has no parameter and is matched as literal text. The route for the lifts is taken as a route, escaped, and matched as literal text too (`django/urls/resolvers.py:_route_to_regex`, `django/urls/resolvers.py:RoutePattern.match`). The view for the tour is a class, which is callable, so `path` accepted it; what would be called with a request is the class itself (`django/urls/conf.py:_path`).

Some of the messages leave something out. `"urls.W001"` does not say what the `$` does: the patterns under the include are left only the empty string, or a final newline, to match (`django/urls/resolvers.py:RegexPattern._check_include_trailing_dollar`, `django/urls/resolvers.py:RegexPattern.match`). `"urls.W002"` is not given when `settings.APPEND_SLASH` is false, nor where a regular expression, or an include's route, ends in a slash too (`django/urls/resolvers.py:CheckURLMixin._check_pattern_startswith_slash`). `"urls.E008"` says that a handler's view could not be imported even of a value that is not a view at all, which `get_callable`, the function that turns a handler into its view, refuses (`django/core/checks/urls.py:check_custom_error_handlers`, `django/urls/utils.py:get_callable`). `"urls.E009"` is given only for a subclass of `View`, and any other class passes (`django/urls/resolvers.py:URLPattern._check_callback`).

> **Trap.** A resolver's own matcher is checked only when everything under it is clean: `URLResolver.check` asks its matcher only when its entries produced no message (`django/urls/resolvers.py:URLResolver.check`). Of the two includes above whose expressions end in `$`, the café's, with one clean entry, is reported; the terrace's, whose entry has a slash in front of its route, is not, and will be once that entry is put right.

The check of error views is looser and tighter than a real call. The handler passes the exception by keyword, as an argument named exception, and the check tries positional arguments alone ([The error views](../views/errors.md)) (`django/core/handlers/exception.py:get_exception_response`). A view whose second parameter has another name can pass the check and fail when it is used, and one that takes the exception as a keyword-only argument can work and be reported.

## Listing what a project serves: listurls

A URLconf is code, and its addresses can be spread over the modules it includes. A pair of functions turns the tree back into a flat list for a person to read; the command listurls is built on them, and so is the index of views in the admin's documentation ([The documentation generator: `django.contrib.admindocs`](../admin/admindocs.md)) (`django/urls/utils.py:extract_views_from_urlpatterns`, `django/urls/utils.py:simplify_regex`, `django/contrib/admindocs/views.py:ViewIndexView`).

`extract_views_from_urlpatterns` gives back a tuple for each pattern: its view, its address, the instance namespaces above it, and its name. An address is the routes of the includes above the pattern followed by its own, so the walk carries routes and namespaces down into each include, and the audio guide's track, two includes down, has two of each.

```text recording=urls
extract_views_from_urlpatterns(get_resolver().url_patterns): a tuple for each pattern
...
    (views.track, 'east/rooms/<int:room>/audio/<slug:track>/', ['east', 'audio'], 'track')
...
    (views.plan, '^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$', None, 'plan')
    ...
```

Each address is the routes as written, joined, so one that `re_path` made is still a regular expression. `simplify_regex` rewrites such an address for a person to read (`django/urls/utils.py:simplify_regex`). In the lines below, a group written `(?:…)` is deleted with all it holds, so the museum's plan address loses its optional format; each group left becomes its name in angle brackets, as a route writes a parameter, or `<var>` if it has none, and the anchors and quantifiers go. A route as plain as the museum's gains only a slash in front.

```text recording=urls
simplify_regex(): a regular expression made into an address a person can read
    simplify_regex('^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z')  ->  '/tickets/<year>/<month>/'
    simplify_regex('^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$')  ->  '/plans/<floor>'
    simplify_regex('^archive/([0-9]{4})/([0-9]{2})/$')  ->  '/archive/<var>/<var>/'
    simplify_regex('east/rooms/<int:room>/audio/<slug:track>/')  ->  '/east/rooms/<int:room>/audio/<slug:track>/'
```

> **Trap.** `_find_groups` keeps a group only where it begins after the one before it has ended, which passes over the first group nested in another and, with it, one that begins exactly where the other ends. A named group passed over can be taken for an unnamed one: `"^(?P<year>[0-9]{4})(?P<month>[0-9]{2})/$"` comes out as `"/<year><var>/"`, and listurls and the index of views show the address so (`django/urls/utils.py:_find_groups`).

The command listurls is those two functions and some formatting. It makes a row of each tuple: the address made readable, the view named by its module and name, and the pattern's name with its instance namespaces joined in front by colons, which is the name it is reversed by; the rows are sorted unless it is told otherwise (`django/core/management/commands/listurls.py:Command.get_url_patterns`, `django/core/management/commands/listurls.py:Command.handle`). Over the museum's URLconf the gallery's patterns are listed once for each wing.

```text recording=urls
call_command("listurls"), with ROOT_URLCONF = 'museum.urls': each line as printed, without the spaces at its end
    /                                           museum.views.entrance  entrance
    /east/                                      museum.views.wing      east:wing
    /east/rooms/<int:room>/                     museum.views.room      east:room
    /east/rooms/<int:room>/audio/<slug:track>/  museum.views.track     east:audio:track
...
    /plans/<floor>                              museum.views.plan      plan
...
    /west/                                      museum.views.wing      west:wing
    /west/rooms/<int:room>/                     museum.views.room      west:room
    /west/rooms/<int:room>/audio/<slug:track>/  museum.views.track     west:audio:track
```

> **Trap.** listurls lists the module that `ROOT_URLCONF` names, which it imports itself: a URLconf that a middleware gives a request in its attribute `"urlconf"` is not listed ([The script prefix, the current URLconf and the caches](state.md#the-current-urlconf)) (`django/core/management/commands/listurls.py:Command.get_url_patterns`). And the prefix of `i18n_patterns`, a `LocalePrefixPattern`, is listed for the language active as the command runs. `BaseCommand.execute` activates none, so from the command line `get_language` falls back to `settings.LANGUAGE_CODE`, and the rows carry that language's prefix, or none under `prefix_default_language=False`; under `call_command`, the caller's (`django/core/management/base.py:BaseCommand.execute`, `django/utils/translation/trans_real.py:get_language`, `django/urls/resolvers.py:LocalePrefixPattern.language_prefix`).

> **New in 6.2.** The command listurls is new in this release (`docs/releases/6.2.txt`); portions of its code, its module says, are derived from django-extensions (`django/core/management/commands/listurls.py`). The two functions under it are older: until this release they were the admin's documentation application's, defined in its views module.
