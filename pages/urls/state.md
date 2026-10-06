---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The script prefix, the current URLconf and the caches

What the URL system keeps between calls: the script prefix and the current URLconf, which `set_script_prefix` and `set_urlconf` keep for one thread or task, and the resolvers and compiled expressions, which are kept for the process until `clear_url_caches` empties some of them.

`resolve` and `reverse` are called with very little: a path, or a name and some arguments. What else they need they find in state that something set earlier, and that state has two lifetimes. Some of it belongs to the request being served, and is kept apart for each thread, since a server's threads serve different requests at once. The rest is derived from the URLconf, is not made for any one request, and is kept for the life of the process.

| | the script prefix | the current URLconf |
|---|---|---|
| read by | `django.urls.get_script_prefix` | `get_urlconf` |
| unset, it reads as | `"/"` | `None`, which `get_resolver` takes to mean `settings.ROOT_URLCONF` |
| set by | `WSGIHandler.__call__` and `ASGIHandler.handle`, for each request; `django.setup`, for a command; `override_script_prefix`, in a test | `BaseHandler.get_response` and its asynchronous twin, for each request; `BaseHandler.resolve_request`, when the request names one |
| cleared by | nothing in Django | `reset_urlconf`, when the request finishes; `root_urlconf_changed`, when a test overrides `ROOT_URLCONF` |

*The two values kept for a thread or a task, and what sets and clears them.*

## The script prefix

A site is not always served from the root of its host. A server may mount a Django project under some path, `"/museum"`, and Django is then to route only the remainder of each request's path. Under WSGI the server hands over the two parts separately, the mounted part as `"SCRIPT_NAME"`. Under ASGI it hands over the whole path with the mounted part beside it, as the root path, and `ASGIRequest` takes the one off the front of the other. Either way the request's `path_info` is the remainder, and a URLconf is written as if the site stood at the root. But a path that `reverse` returns is sent to a browser, and has to carry the mounted part in front or the link will lead outside the project.

That part is the **script prefix**. It is kept in a module-level object, `_prefixes`, by `set_script_prefix`, which adds a final slash if there is none, and read by `get_script_prefix` (`django/urls/base.py:set_script_prefix`, `django/urls/base.py:get_script_prefix`).

Each of the two handlers sets it before it makes the request object: `WSGIHandler.__call__` as its first statement, from the server's environ, and `ASGIHandler.handle` once the body has been received, from the scope's `"root_path"`. In both, `settings.FORCE_SCRIPT_NAME` takes the server's place: under WSGI whenever the setting is not `None`, and under ASGI whenever it is not empty ([The handler's entry](../handlers/entry.md)) (`django/core/handlers/wsgi.py:get_script_name`, `django/core/handlers/asgi.py:get_script_prefix`). `reverse` reads the prefix on every call and passes it down to be put in front of the path.

This request was served with the server's script name set to `"/museum"`. The lines are the calls the handler made that set or cleared something, with the resolution of the path and the call of the view between them; the view then asked a few questions, and the recording's script asked them again afterwards.

```text recording=urls
GET /museum/east/rooms/12/, where the server's SCRIPT_NAME is /museum: what the handler sets for the thread, and what clears it
    before this request
      get_script_prefix()  ->  '/'
      get_urlconf()  ->  None
    WSGIHandler.__call__(environ, start_response)
      set_script_prefix('/museum')
      signal request_started
      BaseHandler.get_response
        set_urlconf('museum.urls')
        BaseHandler.resolve_request
          get_resolver()
          URLResolver.resolve('/east/rooms/12/')  (the root resolver)  ->  ResolverMatch(views.room, kwargs={'wing': 'east', 'room': 12}, namespaces=['east'], route='east/rooms/<int:room>/')
        views.room(request, wing='east', room=12)
          the view asks
            request.path  ->  '/museum/east/rooms/12/'
            request.path_info  ->  '/east/rooms/12/'
            get_script_prefix()  ->  '/museum/'
            get_urlconf()  ->  'museum.urls'
            reverse("entrance")  ->  '/museum/'
      start_response("200 OK", headers)
    the server sends the body: 'room 12 of the east wing'
    the server calls close() on what it was given
    HttpResponseBase.close  (HttpResponse)
      signal request_finished
        reset_urlconf
          set_urlconf(None)
    after the request, on the same thread
      get_script_prefix()  ->  '/museum/'
      get_urlconf()  ->  None
      reverse("entrance")  ->  '/museum/'
    and on a thread started now
      get_script_prefix()  ->  '/'
```

Inside the view the request's `path` has the prefix and its `path_info` does not, and a reversed path has it.

Nothing takes the prefix away again. After the request the same thread still answers `"/museum/"`, and would give that prefix to anything it reversed. In a server this does no harm, because the next request on that thread sets the prefix before it does anything else. `clear_script_prefix` exists, and nothing in the `django` package calls it.

With `settings.FORCE_SCRIPT_NAME` set, here to `"/exhibits"`, the server's value is ignored. This is the same request, the server still saying `"/museum"`, with only one of the handler's calls written down, the one that sets the prefix:

```text recording=urls
The same request with FORCE_SCRIPT_NAME = '/exhibits': the prefix the handler sets, and what the view is told
    WSGIHandler.__call__(environ, start_response)
      set_script_prefix('/exhibits')
      views.room(request, wing='east', room=12)
        the view asks
          request.path  ->  '/exhibits/east/rooms/12/'
          request.path_info  ->  '/east/rooms/12/'
          get_script_prefix()  ->  '/exhibits/'
          get_urlconf()  ->  'museum.urls'
          reverse("entrance")  ->  '/exhibits/'
```

Code that runs outside a request has no handler to set a prefix for it. A new thread starts without one, as the last line of the first recording shows, and so does a management command. For commands `django.setup` sets it, to `settings.FORCE_SCRIPT_NAME` or else to `"/"`: a command that reverses a URL, to put a link in an email, gets the forced prefix or none ([What `django.setup` does](../startup.md)).

The test client is different again. Its handlers make the request from an environ, or for the asynchronous client a scope, which may carry a script name or a root path, and they do not set the prefix. Here the recording's script sets a prefix itself and then makes a request through the test client with another script name:

```text recording=urls
The test client passes SCRIPT_NAME to the request, and its handler does not set the script prefix
    the script calls set_script_prefix("/elsewhere")
    and then Client().get("/east/rooms/12/", SCRIPT_NAME="/museum")
      the view asks
        request.path  ->  '/museum/east/rooms/12/'
        request.path_info  ->  '/east/rooms/12/'
        get_script_prefix()  ->  '/elsewhere/'
        get_urlconf()  ->  'museum.urls'
        reverse("entrance")  ->  '/elsewhere/'
```

The request's own path carries the script name the client was given. The prefix the view reads, and the path it reverses, are the ones the recording's script had set beforehand.

## The current URLconf

The current URLconf is kept the same way, in `_urlconfs`, by `set_urlconf`, and read by `get_urlconf`. `resolve` and `reverse` both begin by reading it unless they are given a URLconf, and `get_resolver` turns the `None` of an unset one into `settings.ROOT_URLCONF` (`django/urls/base.py:set_urlconf`, `django/urls/base.py:get_urlconf`, `django/urls/resolvers.py:get_resolver`).

It exists so that one request can be routed by another URLconf. A middleware sets an attribute named `"urlconf"` on the request, and when the request reaches the centre of the chain `BaseHandler.resolve_request` finds the attribute, makes that URLconf the current one, and resolves with its resolver. Here the recording's own middleware gives a second URLconf, the members', to requests for the members' host. That URLconf has a pattern named renew and none named tickets.

```text recording=urls
GET / for the host members.museum.example: a middleware sets request.urlconf
    WSGIHandler.__call__(environ, start_response)
      set_script_prefix('')
      signal request_started
      BaseHandler.get_response
        set_urlconf('museum.urls')
        HostURLconf.__call__, the recording's middleware
          request.urlconf = "museum.urls_members"
          and then, still in the middleware: get_urlconf()  ->  'museum.urls'
          BaseHandler.resolve_request
            set_urlconf('museum.urls_members')
            get_resolver('museum.urls_members')
            URLResolver.resolve('/')  (the root resolver of museum.urls_members)  ->  ResolverMatch(views.members, kwargs={}, namespaces=[], route='')
          views.members(request)
            the view asks
              get_urlconf()  ->  'museum.urls_members'
              reverse("renew", kwargs={"year": 2026})  ->  '/renew/2026/'
              reverse("tickets", kwargs={"year": 2026})  ->  raises NoReverseMatch
      start_response("200 OK", headers)
    the server sends the body: "the members' entrance"
    the server calls close() on what it was given
    HttpResponseBase.close  (HttpResponse)
      signal request_finished
        reset_urlconf
          set_urlconf(None)
    after the request
      get_urlconf()  ->  None
```

The recording has the whole life of the value in one request. `BaseHandler.get_response` set it to `settings.ROOT_URLCONF` before the middleware chain was entered, as `BaseHandler.get_response_async` also does. The middleware put its attribute on the request, and the current URLconf did not change: a middleware that reverses a URL at that point is still under the root URLconf, whatever it has just put on the request. `resolve_request` then made the members' URLconf current. And when the response was closed and the signal `request_finished` was sent, a receiver the handler's module connected, `reset_urlconf`, set it back to nothing (`django/core/handlers/base.py:BaseHandler.get_response`, `django/core/handlers/base.py:reset_urlconf`).

Because the URLconf was made current and not merely used once, everything after it in the request agrees with it. The view could reverse a name that only the members' URLconf has, and could not reverse one that only the museum's has. Had the view raised, with `settings.DEBUG` off as it is here, the error view would have been looked for in the members' URLconf module, because the handler asks for the resolver of the current URLconf when it needs one ([From a URLconf to a tree](urlconf.md#what-else-a-urlconf-module-may-hold)).

## Why one thread does not see another's

`_prefixes` and `_urlconfs` are each a `Local` from `asgiref`. An attribute set on one by a thread that is serving a request is not seen by another thread serving another, which is what lets a server's threads each work under a different prefix and URLconf at the same moment. Under ASGI, where many requests share the event loop's thread, the same object keeps the value with the asynchronous context it was set in: its docstring says a value is visible to code awaited from the frame that set it, to tasks spawned from there, and to synchronous code that `sync_to_async` runs in a thread on that code's behalf (`asgiref:asgiref/local.py:Local`).

## For the process: resolvers and compiled expressions

What is worked out from the URLconf is kept in these places.

| what is kept | where | until |
|---|---|---|
| the root resolver of each URLconf | `functools.cache` on `_get_cached_resolver`, by the value it was asked for | `clear_url_caches` |
| the resolver made for reversing inside a namespace, for each expression that leads to one | `functools.cache` on `get_ns_resolver` | `clear_url_caches` |
| each view or error view imported from a dotted name | `functools.cache` on `get_callable` | `clear_url_caches` |
| a resolver's module and its list of entries | `URLResolver.urlconf_module` and `URLResolver.url_patterns`, each computed once on the resolver | the resolver is discarded |
| a resolver's tables for reversing, for each language | three dictionaries on the resolver | the resolver is discarded |
| the compiled expression of a `RoutePattern` or a `RegexPattern` | on the matcher; a `LocalePrefixPattern` keeps none, and calls `re.compile` at every read | the matcher is discarded |
| the expression each route expands to | `functools.lru_cache` on `_route_to_regex`, which holds 128 results | `register_converter`, or newer routes push it out |
| the dictionary of converters | `functools.cache` on `get_converters` | `register_converter` |
| whether a URLconf has a language prefix | `functools.cache` on `is_language_prefix_patterns_used` | the process ends |

*What the URL system keeps for the process, and what empties it.*

```text recording=urls
One root resolver for each value get_resolver() is given, kept until the caches are cleared
    get_resolver() is get_resolver()  ->  True
    get_resolver() is get_resolver("museum.urls")  ->  True
    get_resolver("museum.urls_members") is get_resolver()  ->  False
    get_resolver(sys.modules["museum.urls"]) is get_resolver("museum.urls")  ->  False
    _get_cached_resolver.cache_info().currsize > 1  ->  True
    get_ns_resolver.cache_info().currsize > 0  ->  True
    the script calls clear_url_caches()
    _get_cached_resolver.cache_info().currsize  ->  0
    get_ns_resolver.cache_info().currsize  ->  0
    get_resolver() is the root resolver there was before the call  ->  False
    the script keeps the root resolver there is now, enters override_settings(ROOT_URLCONF="museum.urls_members") and leaves it again
    inside it: reverse("renew", kwargs={"year": 2026})  ->  '/renew/2026/'
    get_resolver() is the root resolver the script kept  ->  False
```

`get_resolver` keeps a root resolver for each value it has been given, and every call with the same value gets the same object. In the fourth line one URLconf is asked for by its dotted name and as the module itself, and those are two values.

`clear_url_caches` empties the first three rows of the table. Within Django it has one caller, a receiver of the signal `setting_changed` that the test framework connects: when `ROOT_URLCONF` is overridden in a test, the receiver clears the caches and unsets the current URLconf, both as the override begins and as it ends. In the recording's last lines the script keeps the root resolver, enters such an override and leaves it, and the root resolver it gets afterwards is another object ([The test framework](../testing.md)) (`django/urls/base.py:clear_url_caches`, `django/test/signals.py:root_urlconf_changed`).

A server never calls it. A process that has resolved its first request has imported its URLconf and built its tree for good, and an edited URLconf is noticed only by a new process. The development server gets one by restarting itself when a file changes ([The autoreloader](../commands/autoreload.md)).
