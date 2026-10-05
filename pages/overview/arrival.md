---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From the server's call to the view

What happens between the server calling `WSGIHandler.__call__` and the view being chosen: the request object is made, and the request passes inwards through the seven middleware of a default project, and what they do on the way in is mostly to leave something on it for a later layer to find.

A WSGI server calls the handler with two things, a dictionary describing the request and a function to start the response with, and expects an iterable of bytes back. The part of the call before any middleware runs is short and the same for every request (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).

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

The script prefix is the part of the path that belongs to the server's mount point and not to Django, which is empty here; it is kept for the current thread, because reversed URLs must start with it (`django/urls/base.py:set_script_prefix`). Then the `request_started` signal is sent. A **signal** is a list of receivers, and sending it calls the synchronous ones in turn, which is why a receiver's work appears nested under the send in the recording (`django/dispatch/dispatcher.py:Signal.send`). Its two receivers belong to the database layer: `reset_queries` empties each connection's log of queries, and `close_old_connections` closes any connection that is unusable or past its configured age (`django/db/__init__.py:close_old_connections`). Only then is the request object made.

## The request object

`WSGIRequest.__init__` is deliberately cheap (`django/core/handlers/wsgi.py:WSGIRequest.__init__`). It keeps the server's dictionary as `HttpRequest.META`, the same object, with the path split into the script prefix and `HttpRequest.path_info`; it upper-cases the method; it parses the `Content-Type` header into the content type and its parameters, from which the request's encoding comes; and it wraps the server's input stream in a `LimitedStream` that will not read past the declared content length. Nothing else is parsed.

What a view reads from a request is computed on first use. `WSGIRequest.GET` parses the query string into a `QueryDict` the first time it is read, and `WSGIRequest.COOKIES` parses the `"Cookie"` header the same way (`django/core/handlers/wsgi.py:WSGIRequest.GET`, `django/core/handlers/wsgi.py:WSGIRequest.COOKIES`). `WSGIRequest.POST` and `WSGIRequest.FILES` both come from one method, `HttpRequest._load_post_and_files`, which reads the body and parses it as a form if the method is `POST` and the content type is one of the two form types; for any other request both are empty (`django/http/request.py:HttpRequest._load_post_and_files`). The stream is read once: `HttpRequest.body` reads it whole, refuses a body larger than `settings.DATA_UPLOAD_MAX_MEMORY_SIZE`, and keeps the bytes (`django/http/request.py:HttpRequest.body`). The request in the recording is a `GET` with no cookies, so of all this only the cookie header is parsed, when a middleware asks for it, and the body is never read; [Requests and responses](../http.md) is the chapter on all of it.

`BaseHandler.get_response` then sets the URLconf for this thread to `settings.ROOT_URLCONF` and calls the chain (`django/core/handlers/base.py:BaseHandler.get_response`). The URLconf is kept per thread, or per task under ASGI, so that a middleware can replace it for one request, and it is cleared again when the request ends (`django/urls/base.py:set_urlconf`).

## The way in

The chain was built at startup from `settings.MIDDLEWARE`, and a default project's setting names seven middleware. Each was constructed with the layer inside it as its one argument, and each is built on `MiddlewareMixin`, so each layer's call is `MiddlewareMixin.__call__`: it runs the class's `process_request` if it has one, calls the layer inside unless that returned a response, and runs the class's `process_response` on what comes back (`django/middleware/__init__.py:MiddlewareMixin.__call__`). Around every layer stands `convert_exception_to_response`, the wrapper that turns an exception raised inside it into a response; the recording writes down only the functions the chapter names, so the wrapper is not in it ([Handlers and middleware](../handlers.md) has it). This is the way in, for a request with no cookies:

```text recording=overview
MiddlewareMixin.__call__ (SecurityMiddleware)
  SecurityMiddleware.process_request
  MiddlewareMixin.__call__ (SessionMiddleware)
    SessionMiddleware.process_request
      SessionStore.__init__(session_key=None)  (sessions.backends.db)
    MiddlewareMixin.__call__ (CommonMiddleware)
      CommonMiddleware.process_request
        HttpRequest.get_host
      MiddlewareMixin.__call__ (CsrfViewMiddleware)
        CsrfViewMiddleware.process_request
          CsrfViewMiddleware._get_secret
        MiddlewareMixin.__call__ (AuthenticationMiddleware)
          AuthenticationMiddleware.process_request
          MiddlewareMixin.__call__ (MessageMiddleware)
            MessageMiddleware.process_request
              FallbackStorage.__init__
            MiddlewareMixin.__call__ (XFrameOptionsMiddleware)
              BaseHandler._get_response
```

Most of what a middleware does on the way in is to leave a mark on the request for something further in to use: a session, a user, a secret. Read in the order of the setting:

**`SecurityMiddleware`** has one job on the way in: when `settings.SECURE_SSL_REDIRECT` is true, the request is not secure, and its path matches none of `settings.SECURE_REDIRECT_EXEMPT`, it answers with a permanent redirect to the same URL over HTTPS, on the host `settings.SECURE_SSL_HOST` names if it names one, and nothing inside it runs. The setting is false by default, so here it does nothing; its work is on the way out (`django/middleware/security.py:SecurityMiddleware.process_request`).

**`SessionMiddleware`** reads the session cookie, which is the first use of `WSGIRequest.COOKIES` and so the moment the `"Cookie"` header is parsed, and sets `HttpRequest.session` to a new session store for that key (`django/contrib/sessions/middleware.py:SessionMiddleware.process_request`). The store does not touch the database: `SessionBase.__init__` keeps the key, the serializer class `settings.SESSION_SERIALIZER` names, and two flags, `SessionBase.accessed` and `SessionBase.modified`, both false, and the session's data is loaded the first time anything reads it (`django/contrib/sessions/backends/base.py:SessionBase.__init__`, `django/contrib/sessions/backends/base.py:SessionBase._get_session`). With no cookie the key is `None`, and even a read would load nothing.

**`CommonMiddleware`** refuses the user agents in `settings.DISALLOWED_USER_AGENTS`, and then calls `HttpRequest.get_host`, which is where the `"Host"` header is checked against `settings.ALLOWED_HOSTS`. A host that is not allowed raises `DisallowedHost`, which is a `SuspiciousOperation` and becomes a 400 response at this layer's boundary. When `settings.PREPEND_WWW` is set, it redirects a host without `www.` (`django/middleware/common.py:CommonMiddleware.process_request`, `django/http/request.py:HttpRequest.get_host`). The redirect to a path with a slash appended, which this middleware is known for, is done on the way out, to a 404; on the way in it only rides along with a `"www"` redirect.

**`CsrfViewMiddleware`** reads the CSRF cookie, if the request carries one, and puts the secret it holds into `HttpRequest.META` under `"CSRF_COOKIE"` for the rest of the request to use (`django/middleware/csrf.py:CsrfViewMiddleware.process_request`, `django/middleware/csrf.py:CsrfViewMiddleware._get_secret`). It checks only the cookie's format, and replaces a malformed cookie with a new secret; the check of the request's token is in its `process_view`, once the view is known, and [the next section](view.md) says why.

**`AuthenticationMiddleware`** requires that a session middleware has run before it, and raises `ImproperlyConfigured` otherwise. It sets `HttpRequest.user` to a `SimpleLazyObject` around a function that will find the user, and `HttpRequest.auser` to its asynchronous twin (`django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request`). Nothing is looked up. The first attribute read on `HttpRequest.user` calls `get_user`, which takes the user's id and the authentication backend from the session, asks the backend for the user, which is a query, and verifies the session's hash of the password against the user's; when any of that fails the user is an `AnonymousUser` (`django/contrib/auth/__init__.py:get_user`). The view in this chapter never touches `HttpRequest.user`, so in this request no session is read and no user is queried.

**`MessageMiddleware`** sets `HttpRequest._messages` to the storage named by `settings.MESSAGE_STORAGE`. The default is `FallbackStorage`, which keeps messages in a cookie and falls back to the session for what does not fit (`django/contrib/messages/middleware.py:MessageMiddleware.process_request`, `django/contrib/messages/storage/fallback.py:FallbackStorage`).

**`XFrameOptionsMiddleware`** has no `process_request` at all. It is the innermost of the seven, and the only thing inside it is the centre of the chain, `BaseHandler._get_response`, where the URL is resolved and the view called: [the next section](view.md).

So by the time the centre is reached, a request that arrived as a dictionary has been given a session that has not been loaded, a user that has not been looked up, a place for messages, and its host has been checked. Each is lazy where it can be, so that a view which needs none of them costs none of them.
