---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The script prefix, the current URLconf and the caches

The script prefix and the current URLconf are the two values the URL system keeps for the thread or task serving a request: the handler sets the first with `set_script_prefix`, from the server's mount point or `FORCE_SCRIPT_NAME`, and `django.urls.get_script_prefix` reads it; `set_urlconf` and `get_urlconf` keep the second, which `reset_urlconf` unsets when the request finishes. The resolvers and compiled expressions worked out from a URLconf are kept for the process, until `clear_url_caches` empties some of them.

`resolve` and `reverse` are called with very little: a path, or a name and some arguments. What else they need they find in state that something set earlier, and that state has two lifetimes. Some of it belongs to the request being served, and is kept apart for each thread, since a server's threads serve different requests at once. The rest is derived from the URLconf, is not made for any one request, and is kept for the life of the process.

The figure follows the two values through one request on a server's thread, from where each is set. Only the current URLconf ends with the request.

```text figure=on-the-thread
one thread under WSGI                                  the script prefix          the current URLconf
before the request                                     '/'                        None
  serving GET /museum/east/rooms/12/ with the server's SCRIPT_NAME /museum
  WSGIHandler.__call__: set_script_prefix('/museum')   '/museum/' from here
  BaseHandler.get_response: set_urlconf('museum.urls') |                          'museum.urls' from here
  a middleware may set "urlconf" on the request        |                          |  still 'museum.urls'
  BaseHandler.resolve_request                          |                          |  the request's "urlconf" from here, if it has one
  the view: reverse("entrance")  ->  '/museum/'        |                          |
  the response is closed: request_finished,            |                          |
    and reset_urlconf calls set_urlconf(None)          |                          None
after the request, on the same thread                  '/museum/'                 None
                                                       |  the prefix's line runs on past the end of the request;
                                                       |  the URLconf's stops at reset_urlconf

a thread started now                                   '/'
```

*Read downwards, one row a moment of the request on its thread, each value drawn as a line from where it is set. The prefix's line runs on past the end of the request; the URLconf's stops where `reset_urlconf` unsets it, and a URLconf a middleware names for the request takes it over only at `BaseHandler.resolve_request`.*

A request is not all that sets them. The table adds what else does, what clears each, and what each reads as when nothing has set it.

| | the script prefix | the current URLconf |
|---|---|---|
| read by | `django.urls.get_script_prefix` | `get_urlconf` |
| unset, it reads as | `"/"` | `None`, which `get_resolver` takes to mean `settings.ROOT_URLCONF` |
| set by | `WSGIHandler.__call__` and `ASGIHandler.handle`, for each request; `django.setup`, for a command; `override_script_prefix`, in a test | `BaseHandler.get_response` and its asynchronous twin, for each request; `BaseHandler.resolve_request`, when the request names one |
| cleared by | nothing in Django | `reset_urlconf`, when the request finishes; `resolve_request`, when the request's `"urlconf"` is `None`; `root_urlconf_changed`, when a test overrides `ROOT_URLCONF` |

*The two values kept for a thread or a task, and what sets and clears them.*

## The script prefix

A site is not always served from the root of its host. A server may mount a Django project under some path, `"/museum"`, and Django is then to route only the remainder of each request's path. Under WSGI the server hands over the two parts separately, the mounted part as `"SCRIPT_NAME"`. Under ASGI it hands over the whole path with the mounted part beside it, as the root path, and `ASGIRequest` takes the one off the front of the other. Either way the request's `path_info` is the remainder, and a URLconf is written as if the site stood at the root. But a path that `reverse` returns is sent to a browser, and has to carry the mounted part in front or the link will lead outside the project.

That part is the **script prefix**. It is kept in a module-level object, `_prefixes`, by `set_script_prefix`, which adds a final slash if there is none, and read by `get_script_prefix` (`django/urls/base.py:set_script_prefix`, `django/urls/base.py:get_script_prefix`).

Each of the two handlers sets it before it makes the request object: `WSGIHandler.__call__` as its first statement, from the server's environ, and `ASGIHandler.handle` from the scope's `"root_path"`, once it has read the request's body and before it sends `request_started` ([The two entry points](../handlers/entry.md)) (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.handle`). `reverse` reads the prefix on every call and passes it down to be put in front of the path (`django/urls/base.py:reverse`).

In the request the figure draws, the view's questions show the division: the request's `path` keeps the mounted part, its `path_info` has lost it, and the path that `reverse` returns has it in front again.

```text recording=urls
GET /museum/east/rooms/12/, where the server's SCRIPT_NAME is /museum: what the handler sets for the thread, and what clears it
...
        views.room(request, wing='east', room=12)
          the view asks
            request.path  ->  '/museum/east/rooms/12/'
            request.path_info  ->  '/east/rooms/12/'
            get_script_prefix()  ->  '/museum/'
            get_urlconf()  ->  'museum.urls'
            reverse("entrance")  ->  '/museum/'
...
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

> **Trap.** The script prefix outlives its request. `_prefixes` keeps it for each thread, as the comment above it says, and nothing at the end of a request unsets it: once the response is closed the thread still reads `"/museum/"`, and a `reverse` made there, outside any request, puts that in front where a thread with no prefix would put `"/"`. `clear_script_prefix` would unset it, and nothing in Django calls it (`django/urls/base.py:_prefixes`, `django/urls/base.py:clear_script_prefix`). Under ASGI it is the same: the coroutine that awaited the handler still reads `"/museum/"` afterwards. A server's next request on the thread is not harmed, since its handler sets the prefix again before it makes the request object; code that runs on the thread after a request, and reverses with no request of its own, is.

`settings.FORCE_SCRIPT_NAME`, when it is set, takes the server's place. With it set to `"/exhibits"` and a WSGI server saying `"/museum"`, the prefix is `"/exhibits/"`, and the view's `path` and the path it reverses begin with it (`django/core/handlers/wsgi.py:get_script_name`).

> **Trap.** `FORCE_SCRIPT_NAME = ""` means one thing to the WSGI handler and another to the ASGI handler. `get_script_name` takes the setting whenever it is not `None`, so under WSGI an empty one forces an empty mount: with the server mounting the project at `"/museum"`, the view's prefix is `"/"`. The ASGI handler's `get_script_prefix` takes it only when it is not empty, so under ASGI an empty one is passed over and the view's prefix is the server's, `"/museum/"` (`django/core/handlers/wsgi.py:get_script_name`, `django/core/handlers/asgi.py:get_script_prefix`). The same project, moved from one kind of server to the other, reverses to different paths.

Code that runs outside a request has no handler to set a prefix for it, and a thread started afresh reads `"/"`, as the last line of the request quoted above shows. A management command is given one by `django.setup`, which sets `FORCE_SCRIPT_NAME` or else `"/"`: a command that reverses a URL, to put a link in an email, gets the forced prefix or none. A server's own call of `setup`, from `get_wsgi_application` or `get_asgi_application`, passes `set_prefix=False` and leaves the prefix to each request ([Settings, apps and startup](../startup.md)) (`django/__init__.py:setup`, `django/core/wsgi.py:get_wsgi_application`, `django/core/asgi.py:get_asgi_application`). The test client's handlers set no prefix at all: a request made through `Client` has the script name it was given in its `path`, while `reverse` in the view uses whatever prefix the thread already had ([The test client: `Client` and `ClientHandler`](../testing/client.md)) (`django/test/client.py:ClientHandler.__call__`).

## The current URLconf

The **current URLconf** is kept the same way, in `_urlconfs`, by `set_urlconf`, and read by `get_urlconf`. `resolve` and `reverse` both begin by reading it unless they are given a URLconf, and `get_resolver` turns the `None` of an unset one into `settings.ROOT_URLCONF` (`django/urls/base.py:set_urlconf`, `django/urls/base.py:get_urlconf`, `django/urls/resolvers.py:get_resolver`).

For each request, `BaseHandler.get_response`, or `BaseHandler.get_response_async`, sets it to `settings.ROOT_URLCONF` before it calls the middleware chain, and when the response is closed, `reset_urlconf`, a receiver of `request_finished` that the handler's module connects, unsets it (`django/core/handlers/base.py:BaseHandler.get_response`, `django/core/handlers/base.py:reset_urlconf`).

The value exists so that one request can be routed by another URLconf. A middleware sets an attribute named `"urlconf"` on the request, and when the request reaches the centre of the chain `BaseHandler.resolve_request` finds the attribute, makes that URLconf the current one, and resolves with its resolver (`django/core/handlers/base.py:BaseHandler.resolve_request`). A middleware that gives a request for the members' host the members' URLconf, which has a pattern named renew and none named tickets, shows where the change happens: watch the current URLconf the middleware reads just after setting the attribute, and what the view can reverse.

```text recording=urls
GET / for the host members.museum.example: a middleware sets request.urlconf
...
      BaseHandler.get_response
        set_urlconf('museum.urls')
        HostURLconf.__call__, the recording's middleware
          request.urlconf = "museum.urls_members"
          and then, still in the middleware: get_urlconf()  ->  'museum.urls'
          BaseHandler.resolve_request
            set_urlconf('museum.urls_members')
            get_resolver('museum.urls_members')
...
          views.members(request)
            the view asks
              get_urlconf()  ->  'museum.urls_members'
              reverse("renew", kwargs={"year": 2026})  ->  '/renew/2026/'
              reverse("tickets", kwargs={"year": 2026})  ->  raises NoReverseMatch
              ...
```

> **Trap.** Setting the attribute changes nothing at once. The documentation says the URLconf it names "will be used as the root URLconf for the current request", but until `resolve_request` runs, at the centre of the chain, the current URLconf is still `ROOT_URLCONF`: a `reverse` in the middleware that set it, or in a middleware inside it on the request's way in, finds the root URLconf's names. The `process_view` hooks are called after `resolve_request`, and find the new one (`docs/ref/request-response.txt`, `django/core/handlers/base.py:BaseHandler._get_response`).

Because `resolve_request` makes the URLconf current, and does not merely resolve with it, the rest of the request agrees with it: the view reverses by the members' names, and had it raised, with `settings.DEBUG` off, the error view would have been looked for in the members' URLconf module, since the handler asks for the resolver of the current URLconf when it needs one ([From a URLconf to a tree](urlconf.md#what-else-a-urlconf-module-may-hold)) (`django/core/handlers/exception.py:response_for_exception`).

## `Local`: a value for each thread or task

`_prefixes` and `_urlconfs` are each a `Local` from asgiref, an object whose attributes hold a value for each thread (`asgiref:asgiref/local.py:Local`). A value set by a thread serving one request is not seen by another thread serving another, which is what lets a server's threads each work under a different prefix and URLconf at the same moment. Under ASGI many requests share the event loop's one thread, and a value for each thread would be shared among them all; there the `Local` keeps a value for each task. Two requests on one loop show it, each view a coroutine that waits for the other request's view before it asks its questions: the thread each view runs on is the same, and the URLconf each reads is its own request's.

```text recording=urls
Two requests at once under ASGI, with ROOT_URLCONF = 'museum.urls_async' and a middleware of the recording's own that gives the members' host its URLconf: each view, a coroutine on the event loop, asks once the other request's view has started, the two waiting on events each other sets
    the server runs GET / for museum.example and GET / for members.museum.example together, with asyncio.gather, on an event loop on the script's thread
    the museum's view, once the members' view has started
      threading.current_thread() is threading.main_thread()  ->  True
      get_urlconf()  ->  'museum.urls_async'
...
    the members' view, once the museum's view has asked
      threading.current_thread() is threading.main_thread()  ->  True
      get_urlconf()  ->  'museum.urls_members_async'
      ...
```

The `Local` keeps a value with the asynchronous context it was set in, and asgiref's docstring gives its reach: code awaited from the frame that set the value sees it, and so do tasks started from there and synchronous code that `sync_to_async` runs in a thread (`asgiref:asgiref/local.py:Local`). So a view that is a plain function, which the ASGI handler runs on a worker thread, reads its request's prefix and URLconf; and the way back is open too: `reset_urlconf`, run on the worker thread as the response is closed, leaves the URLconf unset for the coroutine that awaited the handler as well (`asgiref:asgiref/sync.py:SyncToAsync.__call__`).

## For the process: resolvers and compiled expressions

What is worked out from the URLconf is kept in these places.

| what is kept | where | until |
|---|---|---|
| the root resolver of each URLconf | `functools.cache` on `_get_cached_resolver`, by the value it was asked for | `clear_url_caches` |
| the resolver made for reversing inside a namespace, for each expression that leads to one | `functools.cache` on `get_ns_resolver` | `clear_url_caches` |
| each view or error view imported from a dotted name | `functools.cache` on `get_callable` | `clear_url_caches` |
| a resolver's module and its list of entries | `URLResolver.urlconf_module` and `URLResolver.url_patterns`, each kept on the resolver once it has been computed | the resolver is discarded |
| a resolver's tables for reversing, filled once for each language ([Language prefixes and translated routes](i18n.md#tables-for-each-language)) | three dictionaries on the resolver | the resolver is discarded |
| the compiled expression of a `RoutePattern` or a `RegexPattern` | on the matcher; a `LocalePrefixPattern` keeps none, and calls `re.compile` at every read | the matcher is discarded |
| the expression each route expands to | `functools.lru_cache` on `_route_to_regex`, which holds 128 results | `register_converter`, or newer routes push it out |
| the dictionary of converters | `functools.cache` on `get_converters` | `register_converter` |
| whether a URLconf has a language prefix | `functools.cache` on `is_language_prefix_patterns_used` | the process ends |

*What the URL system keeps for the process, and what empties it.*

`get_resolver` keeps a root resolver for each value, `None` counting as `ROOT_URLCONF`, and every call with the same value gets the same object; the fourth question asks for one URLconf by its dotted name and as the module itself, which are two values and get two resolvers.

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

`clear_url_caches` empties the first three rows of the table. Within Django it has one caller, `root_urlconf_changed`, a receiver of `setting_changed` that the test framework connects: when a test overrides `ROOT_URLCONF`, it clears the caches and unsets the current URLconf, as the override begins and again as it ends, so the root resolver found after an override is not the one there was before it ([Overriding settings](../startup/overrides.md#the-receivers-of-setting_changed)) (`django/urls/base.py:clear_url_caches`, `django/test/signals.py:root_urlconf_changed`). A server never calls it, so a serving process keeps the tree it has built, and an edited URLconf is noticed only by a new process, which the development server starts when a file changes ([The autoreloader](../commands/autoreload.md)).
