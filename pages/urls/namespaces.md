---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Namespaces

Namespaces are the parts of a name that `reverse` reads before the name itself: an application namespace, an included URLconf's `app_name`, and an instance namespace, which an inclusion of it may be given as `namespace=...`. `reverse` follows a name's namespaces down the tree one at a time, choosing among an application's instances first by the current application, `current_app=...`, and ordinarily reverses the name itself in a resolver that `get_ns_resolver` makes for the way down.

Names are chosen by whoever writes a URLconf, and nothing keeps two URLconfs from choosing the same one: an application's author cannot know what the other applications of a project call their patterns. And one URLconf can be included more than once, as the museum's gallery is, once for each of its two wings: a name alone then does not say which inclusion is meant, and a link on a page that one inclusion serves should lead within that inclusion, without the application's templates having to know where the project put it.

Django answers both with two kinds of namespace. An **application namespace** says which application's URLs a name belongs to. An **instance namespace** says which inclusion of them is meant, and is chosen by whoever includes them. A name is written with its namespaces in front, separated by colons, and either kind may stand there: `"east:room"` names an instance, and `"gallery:room"` names an application and leaves the instance to be decided. What may decide it is a hint called the **current application**. Its value names instance namespaces, those the code that is asking belongs to.

## Where a resolver gets its namespaces

A `URLResolver` holds its namespaces as `URLResolver.app_name` and `URLResolver.namespace`, which `path` takes from the triple given in place of a view ([From a URLconf to a tree](urlconf.md#what-include-returns)) (`django/urls/conf.py:_path`). A resolver made through `include` has both or neither, since `include` refuses an instance namespace without an application namespace, and where none is given takes the application's (`django/urls/conf.py:include`). In the museum's tree the gallery's module is included as the instances east and west, and the audio guide's list inside it as the application audio, with no instance named, so that its instance namespace is audio too.

Resolving records the same two as it goes: each resolver on the way to a match adds its own to the `ResolverMatch`, whose `ResolverMatch.view_name`, for a named pattern, is the name as `reverse` takes it, the instance namespaces in front ([Resolving a path](resolving.md#a-resolvermatch-attribute-by-attribute)) (`django/urls/resolvers.py:URLResolver.resolve`, `django/urls/resolvers.py:ResolverMatch.__init__`).

## How namespaces are filed

When `URLResolver._populate` meets an entry that is a resolver with an application namespace, it leaves the entry's names in the entry's own table, rather than lifting them into its own as it does those of a **plain include**, one with none, and makes two notes of the entry. In `URLResolver.namespace_dict` it files the entry under its instance namespace, with the regular expression of the entry's own route; in `URLResolver.app_dict` it adds the instance namespace to the list kept under the application namespace. A plain include's own two dictionaries are lifted into the resolver above it, each namespace's expression with the include's in front (`django/urls/resolvers.py:URLResolver._populate`).

In the root resolver the wings are listed under gallery in the reverse of the order they were included, since `_populate` goes through a resolver's entries last to first, an order that matters below.

```text recording=urls
What the root resolver keeps for reversing
    ...
    namespace_dict
      'west'  ->  ('west/', the resolver 'west/')
      'east'  ->  ('east/', the resolver 'east/')
    app_dict  ->  {'gallery': ['west', 'east']}
    ...
```

The root resolver does not know the name room. The east wing's resolver does, in a table of its own where the form for it has no `"east/"` in front, and it files the audio guide's namespace one level further down, with an expression that has a parameter in it:

```text recording=urls
What the resolver of 'east/' keeps for reversing
    reverse_dict: under each key its candidates, in the order they are tried; a candidate is its forms; its regular expression; its extra arguments; its converters
      'room'
        [('rooms/%(room)s/', ['room'])]; 'rooms/(?P<room>[0-9]+)/\\Z'; {}; {'room': IntConverter}
    ...
    namespace_dict
      'audio'  ->  ('rooms/(?P<room>[0-9]+)/audio/', the resolver 'rooms/<int:room>/audio/')
    app_dict  ->  {'audio': ['audio']}
```

`namespace_dict` holds one resolver for each instance namespace. Where two includes filed in one resolver, directly or lifted through plain includes, have the same one, each filing replaces the one before, so the one whose entry is written first is kept and no `reverse` reaches the other (`django/urls/resolvers.py:URLResolver._populate`). The system check `check_url_namespaces_unique` warns of every chain of instance namespaces, joined from the root with colons, that occurs more than once in the tree, and so of those under a repeated one too, as for the gallery included twice as annexe ([The URL checks, and listing the patterns](checks.md)) (`django/core/checks/urls.py:check_url_namespaces_unique`, `django/core/checks/urls.py:_load_all_namespaces`).

## How `reverse` follows a qualified name

`reverse` splits the name at its colons. The last piece is the pattern's name; the pieces before it are a chain of namespaces, followed one at a time from the root resolver (`django/urls/base.py:reverse`).

For each piece it first asks whether the piece is an application namespace of the resolver it has reached, by looking in that resolver's `app_dict`. If it is, an instance has to be chosen from the list found there (`django/urls/base.py:reverse`):

1. If the current application offers one of the instances, that one is used; one that is none of them is passed over, with no error.
2. Otherwise, if one of the instances has the application's own name, that one is used. An instance included with no namespace of its own is such an instance, and is called the default.
3. Otherwise the first of the list is used, which is the instance included last.

A piece that is not an application namespace is taken as an instance namespace directly, and the current application has no say in it.

The instance is then looked up in `namespace_dict`. That gives the resolver, which becomes the one the next piece is looked up in, and the regular expression that leads to it, which is added to those collected so far. A piece found in neither dictionary raises `NoReverseMatch` with a message that names it and, unless it is the first piece, the instance namespaces the walk had settled on.

A current application may have several pieces, separated by colons as a name's are, and they are offered in order, one to each piece of the name: its first when the name's first is settled, its second with the name's second. Once a piece of the name settles on an instance other than the one offered, nothing more is offered (`django/urls/base.py:reverse`). So for the name `"gallery:audio:track"` and the current application `"east:audio"`, gallery settles on east and audio on audio, and the address is the east wing's.

In the figure, look for where the two kinds of name meet: one with the application in front is first turned into an instance, and both then go through `namespace_dict`.

```text figure=two-wings
a name with an application in front              a name with an instance in front
"gallery:room"                                   "east:room"
      |                                                |
the root resolver's app_dict:  "gallery" -> west, east |
  one instance is chosen: the current application      |
  if it is one of them; else an instance named         |
  gallery, the default; else the first of the list,    |
  which is the one included last                       |
      |                                                |
      +------ here the current application is east ----+
                                                       |
the root resolver's namespace_dict                     v
  "west" -> west/, and a resolver                 "east" -> east/, and a resolver
                         \                             /
both resolvers hold one list of patterns, and in each one's own reverse_dict "room" is rooms/%(room)s/

get_ns_resolver puts east/ in front: east/rooms/%(room)s/   and room=12 fills the gap: /east/rooms/12/
```

*The lookups that come before a name's own. An application namespace is turned into one of its instances, and an instance namespace into a resolver and the expression that leads to it. Both wings' resolvers hold the same patterns, and only what is put in front tells their addresses apart.*

The museum has no default instance, so a name with the application in front goes to the current application's wing when that is one of the two, and otherwise to the west wing, which the URLconf includes last; a name with an instance in front goes to that instance, whatever the current application:

```text recording=urls
reverse() and namespaces: which wing a name leads to
    ...
    reverse("gallery:room", kwargs={"room": 12})  ->  '/west/rooms/12/'
    reverse("gallery:room", kwargs={"room": 12}, current_app="east")  ->  '/east/rooms/12/'
    reverse("gallery:room", kwargs={"room": 12}, current_app="north")  ->  '/west/rooms/12/'
    reverse("east:room", kwargs={"room": 12}, current_app="west")  ->  '/east/rooms/12/'
    ...
    reverse("gallery:audio:track", kwargs={"room": 12, "track": "intro"})  ->  '/west/rooms/12/audio/intro/'
    reverse("gallery:audio:track", kwargs={"room": 12, "track": "intro"}, current_app="east:audio")  ->  '/east/rooms/12/audio/intro/'
    reverse("north:room", kwargs={"room": 12})  ->  raises NoReverseMatch: 'north' is not a registered namespace
    reverse("east:shop:item", kwargs={"item": "poster"})  ->  raises NoReverseMatch: 'shop' is not a registered namespace inside 'east'
    ...
```

A URLconf with a default instance behaves differently where no current application applies:

```text recording=urls
An instance whose namespace is the application's own is the default
    DEFAULT is a URLconf of three entries, in this order:
      path("east/", include("museum.gallery.urls", namespace="east"))
      path("main/", include("museum.gallery.urls"))
      path("west/", include("museum.gallery.urls", namespace="west"))
    get_resolver(DEFAULT).app_dict  ->  {'gallery': ['west', 'gallery', 'east']}
    reverse("gallery:wing", urlconf=DEFAULT)  ->  '/main/'
    reverse("gallery:wing", urlconf=DEFAULT, current_app="east")  ->  '/east/'
    reverse("gallery:wing", urlconf=DEFAULT, current_app="north")  ->  '/main/'
```

## `get_ns_resolver`: a resolver made for the namespace

`get_ns_resolver` makes a resolver in which a name inside a namespace can be reversed in the ordinary way: populating it lifts the namespace's names into its own table with the expression of the way down in front, as populating any resolver does a plain include's, so that the parameters of the way down are among the name's own. At the end of its walk `reverse` has the resolver of the innermost namespace and the expressions collected on the way down to it, joined into one, and unless that one is empty, as it is when each route on the way down is `""`, it hands both to `get_ns_resolver` (`django/urls/base.py:reverse`). The resolver made has the root's expression `"^/"`, and its one entry is a resolver with no namespace, whose matcher is a `RegexPattern` for the joined expression, carrying the converters of its parameters, and whose list is the namespace's resolver's (`django/urls/resolvers.py:get_ns_resolver`).

> **Why.** A namespace's own table cannot be used as it stands: its forms lack what stands in front of them, which may have parameters, as the audio guide's has the room's number, for which the caller passes arguments the inner resolver knows nothing of (`django/urls/resolvers.py:get_ns_resolver`).

The first `reverse` of the audio track makes its resolver, for an expression two namespaces long that holds the room's number with its converter, and populates it. `get_ns_resolver` is wrapped in `functools.cache`, so the same call made again in the same language finds the resolver populated and goes straight to filling in; one is made, and kept until `clear_url_caches` is called, for each different combination of expression, resolver and converters (`django/urls/base.py:clear_url_caches`).

```text recording=urls
reverse() of a name inside namespaces: a resolver is made for the routes that lead to the namespace, and kept
    the script calls reverse("east:audio:track", kwargs={"room": 12, "track": "intro"})
      reverse('east:audio:track', kwargs={'room': 12, 'track': 'intro'})
        get_resolver()
        get_ns_resolver('east/rooms/(?P<room>[0-9]+)/audio/', the resolver of 'rooms/<int:room>/audio/', (('room', IntConverter),))  ->  a URLResolver '^/' whose one entry is a URLResolver with the RegexPattern 'east/rooms/(?P<room>[0-9]+)/audio/' and converters {'room': IntConverter}
        URLResolver._reverse_with_prefix('track', '/', room=12, track='intro')  (a resolver made for the namespace)
          URLResolver._populate  (a resolver made for the namespace)
            URLResolver._populate  (the resolver made for 'east/rooms/(?P<room>[0-9]+)/audio/')
    ...
    and calls it again
      reverse('east:audio:track', kwargs={'room': 12, 'track': 'intro'})
        get_resolver()
        URLResolver._reverse_with_prefix('track', '/', room=12, track='intro')  (a resolver made for the namespace)
          IntConverter.to_url(12)  ->  '12'
    ...
```

> **Trap.** A name inside a namespace is reversed without the extra arguments of the `include` it came from, which neither the namespace's table nor the resolver `get_ns_resolver` makes holds (`django/urls/resolvers.py:URLResolver._populate`, `django/urls/resolvers.py:get_ns_resolver`). The wing views are called with an argument naming their wing, and reversing with it is refused: `reverse("east:wing")` gives `'/east/'`, and with `kwargs={"wing": "east"}` raises `NoReverseMatch`.

The converters come from the walk: `reverse` gathers those of each namespace's resolver's matcher, the audio guide's `IntConverter` for the room among them (`django/urls/base.py:reverse`). A namespace lifted through a plain include has that include's route in front of it as well, whose parameters its own matcher does not capture; so `URLResolver._populate`, lifting it, copies the plain include's converters into the namespaced matcher for the walk to gather, and such a parameter is made text by its converter's `to_url` rather than by `str` (`django/urls/resolvers.py:URLResolver._populate`, `django/urls/resolvers.py:URLResolver._reverse_with_prefix`).

> **Trap.** The copy is made in place, and a route's matcher shares its dictionary: every matcher made from the same route text for the same kind of entry, while `_route_to_regex`'s cache holds the expansion, holds one dictionary of converters ([Routes, regular expressions and converters](patterns.md#a-route-is-expanded-into-a-regular-expression)). So where an include and a namespaced one under it give a parameter of the same name different converters, a `reverse` leaves the inner one converting it with the outer one's: where the outer is plain with no namespace between, the first with the URLconf, and otherwise the first of a name in the nearest namespace above the inner one, through `get_ns_resolver`. The namespaced include's expression is unchanged, so a path it matches is refused where that converter cannot take the text, and otherwise reaches the view converted by it (`django/urls/resolvers.py:URLResolver._populate`, `django/urls/resolvers.py:get_ns_resolver`, `django/urls/resolvers.py:_route_to_regex`, `django/urls/resolvers.py:RoutePattern.match`).

SMALL, the URLconf below, has for its second entry a plain include of `"floors/<int:wing>/"` around a namespaced include of `"<slug:wing>/"`, so that the parameter wing stands at both levels with two converters; the recording writes the namespaced matcher's dictionary with each converter by its class. Before a `reverse` of the entrance, a name under neither include, that dictionary holds `SlugConverter` for wing, and after it `IntConverter`: the wing east is then refused, and the wing 3 reaches the view as a number.

```text recording=urls
The same with one parameter's name at both levels: after a reverse(), the namespaced include's matcher converts with the plain include's converter
    SMALL is a URLconf of two entries:
      path("", views.entrance, name="entrance")
      path("floors/<int:wing>/", include([path("<slug:wing>/", include(([path("", views.wing, name="wing")], "tour")))]))
    inner is the matcher of the include with the namespace tour
    converters_of(inner.converters)  ->  {'wing': SlugConverter}
    resolve('/floors/2/east/', urlconf=SMALL)  ->  views.wing, args (), kwargs {'wing': 'east'}
    reverse("entrance", urlconf=SMALL)  ->  '/'
    converters_of(inner.converters)  ->  {'wing': IntConverter}
    resolve('/floors/2/east/', urlconf=SMALL)  ->  raises Resolver404
    resolve('/floors/2/3/', urlconf=SMALL)  ->  views.wing, args (), kwargs {'wing': 3}
```

The change reaches every include holding that dictionary, in any URLconf: one made earlier, plain or namespaced, now converts as the namespaced one does, and one made afterwards gets the changed dictionary from the cache; `clear_url_caches` leaves that cache alone and puts nothing back (`django/urls/resolvers.py:_route_to_regex`, `django/urls/base.py:clear_url_caches`).

## Where the current application comes from

`reverse` has no request to consult, and knows the current application only when its caller passes one, as the argument `current_app=...`.

The template tag `{% url %}` can pass one without being asked. Before it calls `reverse` it looks on the request in the template's context, first for an attribute named `"current_app"` and then for the namespace of the request's `resolver_match`. On a page served from one of an application's instances, a link written with the application's namespace therefore leads to that same instance (`django/template/defaulttags.py:URLNode.render`).

A view of the east wing that renders the tag twice, the second time after setting the attribute to `"west"`, finds the attribute winning over the request's own namespace:

```text recording=urls
GET /east/rooms/12/: the template tag {% url %} reverses for the wing the request is in
    views.room(request, wing='east', room=12)
      request.resolver_match.namespace  ->  'east'
      the view renders the template {% url 'gallery:room' room=13 %}
        reverse('gallery:room', kwargs={'room': 13}, current_app='east')  ->  '/east/rooms/13/'
        the template renders as '/east/rooms/13/'
      the view sets request.current_app = "west" and renders it again
        reverse('gallery:room', kwargs={'room': 13}, current_app='west')  ->  '/west/rooms/13/'
        the template renders as '/west/rooms/13/'
        ...
```

The admin's views set the attribute to the name of their site, which is the instance namespace `AdminSite.urls` gives the site's URLs ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](../admin/site-urls.md)) (`django/contrib/admin/sites.py:AdminSite.index`).
