---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From the server's call to the view

What happens between the server calling `WSGIHandler.__call__` and the view being chosen: the request object is made, and the request passes inwards through the seven middleware of a default project, and what they do on the way in is mostly to leave something on it for a later layer to find.

What the middleware leave on the request is lazy where it can be: a view which needs none of it costs none of it. The request object is made the same way: it parses its query string and its cookies, and reads its body, only when they are asked for.

A WSGI server calls the handler with two things, a dictionary describing the request and a function to start the response with, and expects an iterable of bytes back. Before any middleware runs, the handler does the same four things for every request, in this order: it keeps the script prefix, sends the `request_started` signal, makes the request object, and calls `BaseHandler.get_response`, which sets the URLconf and calls the chain (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/base.py:BaseHandler.get_response`). The script prefix and the URLconf are both kept for the current thread: the URLconf is `settings.ROOT_URLCONF`, and the prefix is the part of the path the server mounted Django under, with a slash at its end, here `"/"` alone; every URL that `reverse` builds begins with it (`django/urls/base.py:set_script_prefix`, `django/urls/base.py:set_urlconf`).

A signal is a list of receivers, and sending it calls the synchronous receivers in turn and then any asynchronous ones concurrently (`django/dispatch/dispatcher.py:Signal.send`). The two receivers of `request_started` belong to the database layer: `reset_queries` empties each connection's log of queries, and `close_old_connections` closes any connection that is unusable or past its configured age (`django/db/__init__.py:close_old_connections`). Because the receivers run inside the send, their work is nested under it, and the request object is made only once they have returned; the first request and the second open with the same lines:

```text recording=overview
The first request: GET /entries/2026/
    WSGIHandler.__call__(environ, start_response)  GET /entries/2026/
      set_script_prefix('')
      signal request_started -> reset_queries, close_old_connections
        reset_queries
        close_old_connections
          BaseDatabaseWrapper.close_if_unusable_or_obsolete
      WSGIRequest.__init__(environ)
      BaseHandler.get_response
        set_urlconf('journal.urls')
```

## The request object

`WSGIRequest.__init__` is cheap. It keeps the server's dictionary as `HttpRequest.META`, the same object, and reads from it the path, split into the script prefix and `HttpRequest.path_info`; the method, upper-cased; and the content type with its parameters, from which the request's encoding comes. It wraps the server's input stream in a `LimitedStream` that will not read past the declared content length, and parses nothing else (`django/core/handlers/wsgi.py:WSGIRequest.__init__`).

`WSGIRequest.GET` parses the query string and `WSGIRequest.COOKIES` the `"Cookie"` header, each the first time it is read (`django/core/handlers/wsgi.py:WSGIRequest.GET`, `django/core/handlers/wsgi.py:WSGIRequest.COOKIES`). `WSGIRequest.POST` and `WSGIRequest.FILES` both come from one method, which reads the body only for a `"POST"` of one of the two form types, and otherwise leaves both empty (`django/http/request.py:HttpRequest._load_post_and_files`). This request is a `"GET"` with no cookies. Of all this only `WSGIRequest.COOKIES` is computed, when a middleware asks for it, and it is empty; the body is never read. [Requests and responses](../http.md) is the chapter on all of it, and [The body: `body`, `POST` and `FILES`](../http/body.md) on what may be read after what.

## The way in

A default project's `settings.MIDDLEWARE` names seven middleware. The chain built from it at startup, which [Before the first request](startup.md#the-handler-is-made-and-the-chain-with-it) follows, has the first listed outermost, so a request meets them in the setting's order. Each is built on `MiddlewareMixin`, so each layer's call is `MiddlewareMixin.__call__`: it runs the class's `process_request` if it has one, calls the layer inside unless that returned a response, and runs the class's `process_response` on what comes back (`django/middleware/__init__.py:MiddlewareMixin.__call__`). Around every layer stands `convert_exception_to_response`, the wrapper that turns an exception raised inside it into a response ([Handlers and middleware](../handlers.md) has it).

In the first request, as in the second, a layer's `process_request` comes first under its `MiddlewareMixin.__call__`, and beside it the call of the next layer in, whose own lines stand one step deeper; `XFrameOptionsMiddleware`, which has no `process_request`, goes straight to `BaseHandler._get_response`, the centre of the chain. Lines are left out, and the dots stand for the four layers between:

```text recording=overview
MiddlewareMixin.__call__ (SecurityMiddleware)
  SecurityMiddleware.process_request
  MiddlewareMixin.__call__ (SessionMiddleware)
    SessionMiddleware.process_request
      SessionStore.__init__(session_key=None)  (sessions.backends.db)
    ...
            MiddlewareMixin.__call__ (XFrameOptionsMiddleware)
              BaseHandler._get_response
```

> **History.** Before 1.10 the layers were not strict: a response that one middleware's `process_request` returned still passed through the `process_response` of every middleware, even those that never saw the request. DEP 5 introduced a new setting, `MIDDLEWARE`, listing factories, each called once with what lies inside it, so that a response returned early passes out only through the middleware listed before it, like an onion. Django 1.10 shipped the new style "to solve the lack of strict request/response layering" (`deps:final/0005-improved-middleware.rst`, `docs/releases/1.10.txt`). The old hooks live on in `MiddlewareMixin`, which DEP 5 offered so that one class could serve both styles: [The second decade: from 1.9 to 5.0](../changes/second-decade.md#middleware-rebuilt-as-an-onion).

The thing to see in the figure is that nothing on the way in reaches the database: the two things that might, the session and the user, are left until something reads them.

```text figure=the-way-in
the request comes in from the left, across the edge of every layer to the centre; each middleware a box inside the one before it in settings.MIDDLEWARE
beside each name, what its process_request leaves on the request or checks

SecurityMiddleware                checks SECURE_SSL_REDIRECT: false by default, so no redirect to HTTPS
  SessionMiddleware               leaves HttpRequest.session: a session store, not loaded
    CommonMiddleware              checks the user agent, and the "Host" header against ALLOWED_HOSTS
      CsrfViewMiddleware          leaves META["CSRF_COOKIE"]: the cookie's secret, if the request has one
        AuthenticationMiddleware  leaves HttpRequest.user: a user not looked up
          MessageMiddleware       leaves HttpRequest._messages: a FallbackStorage
            XFrameOptionsMiddleware   nothing: it has no process_request
              the centre, accented: BaseHandler._get_response, where the URL is resolved and the view called
```

*The way in for this chapter's request. Each box is a middleware, drawn inside the one listed before it in the setting, so that the request crosses them from the outside in; beside each is what its `process_request` leaves on the request or checks. The accented box is the centre of the chain.*

**`SecurityMiddleware`** would answer a request that is not secure with a permanent redirect to HTTPS, but only when `settings.SECURE_SSL_REDIRECT` is true, which by default it is not; its work is on the way out (`django/middleware/security.py:SecurityMiddleware.process_request`).

**`SessionMiddleware`** reads the session cookie, which is the first use of `WSGIRequest.COOKIES` and so the moment the `"Cookie"` header is parsed. It sets `HttpRequest.session` to a new session store for that key (`django/contrib/sessions/middleware.py:SessionMiddleware.process_request`). The store does not touch the database: it keeps the key, and the session's data is loaded the first time anything reads it (`django/contrib/sessions/backends/base.py:SessionBase.__init__`, `django/contrib/sessions/backends/base.py:SessionBase._get_session`). What the store holds, and when it loads, is [The session store: `SessionBase`](../auth/sessions.md).

**`CommonMiddleware`** refuses the user agents in `settings.DISALLOWED_USER_AGENTS`, and then calls `HttpRequest.get_host`, which is where the `"Host"` header is checked against `settings.ALLOWED_HOSTS`. A host that is not allowed raises `DisallowedHost`, a `SuspiciousOperation`, which the `convert_exception_to_response` wrapper around this layer turns into a 400 response (`django/core/handlers/exception.py:response_for_exception`). When `settings.PREPEND_WWW` is set, it redirects a host without `www.` (`django/middleware/common.py:CommonMiddleware.process_request`, `django/http/request.py:HttpRequest.get_host`).

**`CsrfViewMiddleware`** reads the CSRF cookie, if the request carries one, and puts the secret it holds into `HttpRequest.META` under `"CSRF_COOKIE"` for the rest of the request to use (`django/middleware/csrf.py:CsrfViewMiddleware.process_request`, `django/middleware/csrf.py:CsrfViewMiddleware._get_secret`). It checks only the cookie's format, and replaces a malformed cookie with a new secret. The check of the request's token is in its `process_view`, once the view is known, and [The URL is resolved and the view is called](view.md) says why; how a page's token is made from the secret is [The CSRF secret and its token](../security/csrf-token.md).

**`AuthenticationMiddleware`** requires that a session middleware has run before it, and raises `ImproperlyConfigured` otherwise. It sets `HttpRequest.user` to a `SimpleLazyObject` around a function that will find the user, and `HttpRequest.auser` to its asynchronous twin (`django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request`). Nothing is looked up until the lazy object is first used: then `get_user` takes the user's id and backend from the session and asks that backend for the user, which is a query (`django/contrib/auth/__init__.py:get_user`). Nothing in this request uses the lazy object, so no session is read and no user is queried. How a login puts the user into the session is [The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md).

**`MessageMiddleware`** sets `HttpRequest._messages` to the storage named by `settings.MESSAGE_STORAGE`. The default is `FallbackStorage`, which keeps messages in a cookie and falls back to the session for what does not fit, as [Message storage: `CookieStorage`, `SessionStorage` and `FallbackStorage`](../auth/message-storage.md) tells (`django/contrib/messages/middleware.py:MessageMiddleware.process_request`, `django/contrib/messages/storage/fallback.py:FallbackStorage`).

**`XFrameOptionsMiddleware`** has no `process_request` at all. It is the innermost of the seven, and the only thing inside it is the centre of the chain, `BaseHandler._get_response`, where the URL is resolved and the view called ([The URL is resolved and the view is called](view.md)).

So a request that arrived as a dictionary reaches the centre with a session that has not been loaded, a user that has not been looked up, a place for messages, and a host that has been checked.
