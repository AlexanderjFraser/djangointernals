---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Namespaces

How `reverse` finds a name inside a namespace: the application namespace and the instance namespace a resolver is given, the two dictionaries `URLResolver._populate` files them in, the part the current application plays, and the resolver `get_ns_resolver` makes to reverse a name inside a namespace.

Names are chosen by whoever writes a URLconf, and nothing keeps two URLconfs from choosing the same one: an application's author cannot know what the other applications of a project call their patterns. And one URLconf can be included more than once. The museum's gallery URLs serve the east wing and the west, and the name room alone does not say which. On a page of the east wing, a link to another room should lead to a room of the east wing, without the gallery's templates having to know where the project put them.

Django answers both with names in two parts. An **application namespace** says which application's URLs a name belongs to. An **instance namespace** says which inclusion of them is meant, and is chosen by the project. A name is written with its namespaces in front, separated by colons, and either kind may stand there: `"east:room"` names an instance, and `"gallery:room"` names an application and leaves the instance to be decided. What decides it is a hint called the **current application**. The name is Django's and is a little misleading: its value is an instance namespace, the one the code that is asking belongs to.

## Where a resolver gets its namespaces

A `URLResolver` holds the two as `URLResolver.app_name` and `URLResolver.namespace`, and `path` takes them from the three things it is given in place of a view. [From a URLconf to a tree](urlconf.md#what-include-returns) has how `include` arrives at them: the application namespace is the attribute `"app_name"` of what is included, or is given beside it in a tuple, and the instance namespace is the argument `namespace=...`, or else the application namespace again. A resolver made through `include` therefore has both or neither, since `include` refuses an instance namespace for a URLconf that has no application namespace.

The museum's root URLconf includes the gallery's module, whose application namespace is gallery, as the instances east and west. Inside it a list of one pattern is included as the application audio, with no instance named, so that resolver's instance namespace is audio too.

## How namespaces are filed

When `URLResolver._populate` meets an entry that is a resolver with an application namespace, it does not read the entry's names into its own table as it would for a plain include. It makes two notes of the entry and leaves its names where they are (`django/urls/resolvers.py:URLResolver._populate`).

In `URLResolver.namespace_dict` it files the entry under its instance namespace, with the regular expression of the entry's own route. In `URLResolver.app_dict` it adds the instance namespace to the list kept under the application namespace.

```text recording=urls
namespace_dict
  'west'  ->  ('west/', the resolver 'west/')
  'east'  ->  ('east/', the resolver 'east/')
app_dict  ->  {'gallery': ['west', 'east']}
```

```text recording=urls
What the resolver of 'east/' keeps for reversing
    reverse_dict: under each key its candidates, in the order they are tried; a candidate is its forms; its regular expression; its extra arguments; its converters
      'room'
        [('rooms/%(room)s/', ['room'])]; 'rooms/(?P<room>[0-9]+)/\\Z'; {}; {'room': IntConverter}
      the function views.room  ->  the same candidates as 'room'
      'wing'
        [('', [])]; '\\Z'; {}; {}
      the function views.wing  ->  the same candidates as 'wing'
    namespace_dict
      'audio'  ->  ('rooms/(?P<room>[0-9]+)/audio/', the resolver 'rooms/<int:room>/audio/')
    app_dict  ->  {'audio': ['audio']}
```

The root resolver knows two instances of gallery and how to reach each. It does not know the name room; the east wing's resolver does, in a table of its own, where the form for it has no `"east/"` in front. The audio namespace is one level further down, filed in the wing's resolver with an expression that has a parameter in it.

The list of instances is in the reverse of the order they were included, because `_populate` goes through a resolver's entries last to first. That order matters once, below.

`namespace_dict` holds one resolver for each instance namespace. If two includes at one level are given the same one, only one of them can be reached by that name, and a system check warns of it ([The URL checks, and listing the patterns](checks.md)).

## How `reverse` follows a qualified name

`reverse` splits the name at its colons. The last piece is the pattern's name; the pieces before it are a chain of namespaces, followed one at a time from the root resolver (`django/urls/base.py:reverse`).

For each piece it first asks whether the piece is an application namespace of the resolver it has reached, by looking in that resolver's `app_dict`. If it is, an instance has to be chosen from the list found there:

1. If the caller gave a current application and it is one of the instances, that one is used.
2. Otherwise, if one of the instances has the application's own name, that one is used. An instance included with no namespace of its own is such an instance, and is called the default.
3. Otherwise the first of the list is used, which is the instance included last.

A piece that is not an application namespace is taken as an instance namespace directly, and the current application has no say in it.

The instance is then looked up in `namespace_dict`. That gives the resolver, which becomes the one the next piece is looked up in, and the regular expression that leads to it, which is added to those collected so far. A piece found in neither dictionary raises `NoReverseMatch` with a message that names it and, unless it is the first piece, the instance namespaces the walk had settled on.

```text recording=urls
reverse() and namespaces: which wing a name leads to
    reverse("east:room", kwargs={"room": 12})  ->  '/east/rooms/12/'
    reverse("west:room", kwargs={"room": 12})  ->  '/west/rooms/12/'
    reverse("gallery:room", kwargs={"room": 12})  ->  '/west/rooms/12/'
    reverse("gallery:room", kwargs={"room": 12}, current_app="east")  ->  '/east/rooms/12/'
    reverse("gallery:room", kwargs={"room": 12}, current_app="north")  ->  '/west/rooms/12/'
    reverse("east:room", kwargs={"room": 12}, current_app="west")  ->  '/east/rooms/12/'
    reverse("room", kwargs={"room": 12})  ->  raises NoReverseMatch
    reverse("east:audio:track", kwargs={"room": 12, "track": "intro"})  ->  '/east/rooms/12/audio/intro/'
    reverse("gallery:audio:track", kwargs={"room": 12, "track": "intro"})  ->  '/west/rooms/12/audio/intro/'
    reverse("gallery:audio:track", kwargs={"room": 12, "track": "intro"}, current_app="east:audio")  ->  '/east/rooms/12/audio/intro/'
    reverse("north:room", kwargs={"room": 12})  ->  raises NoReverseMatch: 'north' is not a registered namespace
    reverse("east:shop:item", kwargs={"item": "poster"})  ->  raises NoReverseMatch: 'shop' is not a registered namespace inside 'east'
```

The first six lines are the rules at work. A name with an instance in front goes to that instance, and a current application does not change it. A name with the application in front goes to the current application's instance when that is one of the two wings. Otherwise, since the museum has no default instance, it goes to the west wing, which the URLconf includes last.

The current application is written like the front of a name, with colons, and is used up alongside the name's own pieces. In the tenth line the name is `"gallery:audio:track"` and the current application `"east:audio"`: east is offered when gallery is being settled, and audio when audio is. Once a piece of the name settles on an instance other than the one offered, the rest of the current application is ignored.

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

## A resolver made for the namespace

The walk ends with the resolver of the innermost namespace, and the expressions collected on the way down to it, joined into one. Unless that one is empty, as it is for a namespace included at `""`, the resolver's own table cannot be used as it stands. Its forms lack what stands in front of them, and that may have parameters, as the audio guide's has the room's number, for which the caller has passed arguments that the inner resolver knows nothing of.

So `reverse` asks `get_ns_resolver` for a resolver made to measure. Its matcher is a `RegexPattern` for the joined expression, carrying the converters of its parameters, and its list is the list of the namespace's resolver; around it stands one more resolver, with the root's expression `"^/"`. Populating that outer resolver does what populating any resolver does to a plain include: it lifts the inner names into its own table with the expression in front. The name can then be reversed there in the ordinary way, with the parameters of the way down among its own (`django/urls/resolvers.py:get_ns_resolver`).

```text recording=urls
reverse() of a name inside namespaces: a resolver is made for the routes that lead to the namespace, and kept
    the script calls reverse("east:audio:track", kwargs={"room": 12, "track": "intro"})
      reverse('east:audio:track', kwargs={'room': 12, 'track': 'intro'})
        get_resolver()
        get_ns_resolver('east/rooms/(?P<room>[0-9]+)/audio/', the resolver of 'rooms/<int:room>/audio/', (('room', IntConverter),))  ->  a URLResolver '^/' whose one entry is a URLResolver with the RegexPattern 'east/rooms/(?P<room>[0-9]+)/audio/' and converters {'room': IntConverter}
        URLResolver._reverse_with_prefix('track', '/', room=12, track='intro')  (a resolver made for the namespace)
          URLResolver._populate  (a resolver made for the namespace)
            URLResolver._populate  (the resolver made for 'east/rooms/(?P<room>[0-9]+)/audio/')
          IntConverter.to_url(12)  ->  '12'
          StringConverter.to_url('intro')  (SlugConverter)  ->  'intro'
          -> '/east/rooms/12/audio/intro/'
        -> '/east/rooms/12/audio/intro/'
    and calls it again
      reverse('east:audio:track', kwargs={'room': 12, 'track': 'intro'})
        get_resolver()
        URLResolver._reverse_with_prefix('track', '/', room=12, track='intro')  (a resolver made for the namespace)
          IntConverter.to_url(12)  ->  '12'
          StringConverter.to_url('intro')  (SlugConverter)  ->  'intro'
          -> '/east/rooms/12/audio/intro/'
        -> '/east/rooms/12/audio/intro/'
    the script calls reverse("east:room", kwargs={"room": 12})
      reverse('east:room', kwargs={'room': 12})
        get_resolver()
        get_ns_resolver('east/', the resolver of 'east/', ())  ->  a URLResolver '^/' whose one entry is a URLResolver with the RegexPattern 'east/' and converters {}
        URLResolver._reverse_with_prefix('room', '/', room=12)  (a resolver made for the namespace)
          URLResolver._populate  (a resolver made for the namespace)
            URLResolver._populate  (the resolver made for 'east/')
              URLResolver._populate  ('rooms/<int:room>/audio/')
          IntConverter.to_url(12)  ->  '12'
          -> '/east/rooms/12/'
        -> '/east/rooms/12/'
```

For the audio track the expression is two namespaces long and holds the room's number, with its converter. `get_ns_resolver` is wrapped in `functools.cache`, so the second call of `reverse` for the same name found the resolver already made and already populated, and went straight to filling in. One is made for each different combination of expression, resolver and converters, and kept until `clear_url_caches` is called.

The made-to-measure resolver is given the namespace's list and the expression in front of it. It is not given the extra arguments of the `include` that the namespace came from, so reversing a name inside a namespace knows nothing of them. The wing views receive an argument naming their wing when a request is resolved, and passing that same argument to `reverse` is refused:

```text recording=urls
reverse("east:wing")  ->  '/east/'
reverse("east:wing", kwargs={"wing": "east"})  ->  raises NoReverseMatch
```

## Where the current application comes from

`reverse` has no request to consult. It knows the current application only when its caller passes one, as the argument `current_app=...`.

The template tag `{% url %}` passes one without being asked. Before it calls `reverse` it looks on the request in the template's context, first for an attribute named `"current_app"` and then for the namespace of the request's `resolver_match`. On a page served from one of an application's instances, a link written with the application's namespace therefore leads to that same instance (`django/template/defaulttags.py:URLNode.render`).

```text recording=urls
views.room(request, wing='east', room=12)
  request.resolver_match.namespace  ->  'east'
  the view renders the template {% url 'gallery:room' room=13 %}
    reverse('gallery:room', kwargs={'room': 13}, current_app='east')  ->  '/east/rooms/13/'
    the template renders as '/east/rooms/13/'
  the view sets request.current_app = "west" and renders it again
    reverse('gallery:room', kwargs={'room': 13}, current_app='west')  ->  '/west/rooms/13/'
    the template renders as '/west/rooms/13/'
```

The second half of the recording is how a view overrides the request's own namespace: an attribute on the request wins. The admin's views set it to the name of their site, which is the instance namespace `AdminSite.urls` gives the site's URLs ([The admin](../admin.md)) (`django/contrib/admin/sites.py:AdminSite.index`).

## What resolving records

Resolving collects the same two kinds of namespace as it goes. Each `URLResolver` on the way to a match puts its application namespace and its instance namespace at the front of two lists on the `ResolverMatch`. `ResolverMatch.view_name` is the instance namespaces joined with colons to the pattern's name, or to the view's dotted name where the pattern has none ([Resolving a path](resolving.md#a-resolvermatch-attribute-by-attribute)).
