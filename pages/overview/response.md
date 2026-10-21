---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The response returns to the server

What an `HttpResponse` is, what each of the seven middleware of a new project does to it on the way out, how `WSGIHandler.__call__` hands it to the server, and who ends the request.

The view returned an `HttpResponse`. The response goes back out through the middleware in the reverse of the order they were entered, and what ends the request is not the handler but the server, when it closes the response.

In the figure, look for where each header comes from, one from the constructor and five from three of the seven layers, and for the line across where the handler has returned, with the request's end below it.

```text figure=the-way-out
the chain on the left, each middleware a box inside the one before it in settings.MIDDLEWARE: the response is made at the centre and leaves to the right, across the edge of every layer, to the handler
at the foot of each box, what that layer did to the response; time runs down, the innermost first and the outermost last
the handler and the server on the right, time running down
accented: the five headers the middleware add

the chain
  the view                  render makes an HttpResponse; the constructor sets Content-Type
  XFrameOptionsMiddleware   X-Frame-Options: DENY
  MessageMiddleware         nothing: no messages to store
  AuthenticationMiddleware  nothing: it has no process_response
  CsrfViewMiddleware        nothing: no token was asked for
  CommonMiddleware          Content-Length: the length of the body
  SessionMiddleware         nothing: the session was never touched
  SecurityMiddleware        X-Content-Type-Options: nosniff
                            Referrer-Policy: same-origin
                            Cross-Origin-Opener-Policy: same-origin
the handler
  BaseHandler.get_response  the request's close added to the response's closers
  WSGIHandler.__call__      start_response: the status line and the six headers
a line across: the handler has returned
the server
  sends the body
  HttpResponseBase.close    the closers, HttpRequest.close among them; then request_finished:
                              close_old_connections   closes the database connection
                              close_caches
                              reset_urlconf           clears the thread's URLconf
```

*The response's way out, time running down. In the chain the view comes first and then each middleware, the innermost first, with what it did to this response; the accented lines are the five headers the middleware added. Beside the chain are the handler's last two steps, and below the line the handler has returned and the server ends the request.*

## The response object

An `HttpResponse` is a status, a set of headers, cookies, and a body held in memory. `HttpResponseBase.__init__` makes the headers, a `ResponseHeaders` that looks a header up without regard to case. If no Content-Type was given, the constructor sets one of `"text/html"` with the response's charset, by default `settings.DEFAULT_CHARSET`. The status is the class's `status_code`, 200, unless one was passed (`django/http/response.py:HttpResponseBase.__init__`).

The `HttpResponse.content` setter encodes a string with the response's charset (`django/http/response.py:HttpResponse.content`). What `render` gave the constructor was the rendered template as a string, and from here on the body is bytes. A response that streams is a different class, `StreamingHttpResponse`, whose body is produced as the server iterates it; [The response object](../http/response.md) and [Streaming and file responses](../http/streaming.md) have the two.

## The way out

Here each layer's `process_response` is given what the layer inside it returned, and returns the response the layer outside it will see, which may be a different object (`django/middleware/__init__.py:MiddlewareMixin.__call__`). Six of the seven have one, and they run in the reverse of their order in `settings.MIDDLEWARE`; `AuthenticationMiddleware` has none:

**`XFrameOptionsMiddleware`** sets X-Frame-Options to `settings.X_FRAME_OPTIONS` in capitals, `"DENY"` by default, unless the header is already there or the response was marked exempt by `xframe_options_exempt` (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.process_response`, `django/middleware/clickjacking.py:XFrameOptionsMiddleware.get_xframe_options_value`).

**`MessageMiddleware`** asks the request's message storage to store what has not been read, into a cookie or the session, as [Messages: `add_message`, `Message` and `MessageMiddleware`](../auth/messages.md) tells; here there is nothing to store (`django/contrib/messages/middleware.py:MessageMiddleware.process_response`, `django/contrib/messages/storage/base.py:BaseStorage.update`).

**`CsrfViewMiddleware`** sets the CSRF cookie ([The CSRF secret and its token](../security/csrf-token.md#sending-it-back-process_response)) only when `HttpRequest.META` was marked with `"CSRF_COOKIE_NEEDS_UPDATE"` during the request. `get_token` marks it whenever something asks for a token, a template's `csrf_token` tag among them, and nothing in this request asked (`django/middleware/csrf.py:get_token`, `django/middleware/csrf.py:CsrfViewMiddleware.process_response`).

**`CommonMiddleware`** adds Content-Length, the length of the body, to any response that is not streaming and has none (`django/middleware/common.py:CommonMiddleware.process_response`).

> **Trap.** `CommonMiddleware` makes the redirect that `settings.APPEND_SLASH` asks for on the way out, not on the way in. A path without its trailing slash goes in, fails to resolve, and comes back out through the inner layers as a 404. `CommonMiddleware.process_response` then answers a permanent redirect to the path with the slash in place of the 404, if that path would resolve and its view allows it. This is how `"/entries/2026"` reaches `"/entries/2026/"`. The check may be expensive, so the way in makes it only when it is already sending a redirect for `settings.PREPEND_WWW` (`django/middleware/common.py:CommonMiddleware.process_response`, `django/middleware/common.py:CommonMiddleware.process_request`); [The general-purpose middleware](../handlers/general.md#commonmiddleware-on-the-way-out) tells the redirect whole.

**`SessionMiddleware`** reads whether the session was accessed or modified, and whether it is empty. It may then save the session and set its cookie, make the response vary on `"Cookie"`, or delete the cookie ([`SessionMiddleware`: the cookie and the save](../auth/session-middleware.md)). This request's session was never touched, so nothing is done (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`, `django/contrib/sessions/backends/base.py:SessionBase.is_empty`).

**`SecurityMiddleware`** adds the headers that are on by default: X-Content-Type-Options as `"nosniff"`, Referrer-Policy and Cross-Origin-Opener-Policy as `"same-origin"`, each only if the response does not already have it ([The security headers: `SecurityMiddleware` and `XFrameOptionsMiddleware`](../security/headers.md)) (`django/middleware/security.py:SecurityMiddleware.process_response`).

The outermost layer's return is what the chain returns. `BaseHandler.get_response` then registers the request's own `close` among the response's closers, so that closing the response closes any files uploaded with the request (`django/core/handlers/base.py:BaseHandler.get_response`).

## Handing it to the server

Back in `WSGIHandler.__call__`, the handler records its class on the response, so that `request_finished` can name the handler's class as its sender. It then builds the two things the WSGI interface wants: the status line, from the status code and its reason phrase, and the list of headers, which is the response's headers followed by one Set-Cookie for each cookie. It passes both to the function the server gave it, start_response, and returns this response object itself (`django/core/handlers/wsgi.py:WSGIHandler.__call__`). An `HttpResponse` is iterable, and iterating this one yields its body in one piece, which is all WSGI asks of a body (`django/http/response.py:HttpResponse.__iter__`).

## Who ends the request

The handler has returned, but the request is not over: the server still has to send the body, and when it has, the WSGI specification obliges it to call `close` on what it was given. `HttpResponseBase.close` runs each closer registered on the response, the request's among them, and then sends `request_finished`, which here has three receivers (`django/http/response.py:HttpResponseBase.close`). [The two entry points](../handlers/entry.md#who-ends-the-request) sets out the signals of the request cycle, `request_started`, `request_finished` and `got_request_exception`, and their receivers under either handler.

The recording's first request ends outside the handler's call. The call to start_response, its headers in the order they were set, is the last line inside `WSGIHandler.__call__`, whose other lines are left out. The sending of the body and `HttpResponseBase.close` stand at the margin, where the server makes them after the handler has returned, and the database connection is closed by the first of the signal's receivers.

```text recording=overview
WSGIHandler.__call__(environ, start_response)  GET /entries/2026/
  ...
  start_response("200 OK", [Content-Type, X-Frame-Options, Content-Length, X-Content-Type-Options, Referrer-Policy, Cross-Origin-Opener-Policy])
the server has sent the body: 148 bytes
HttpResponseBase.close
  HttpRequest.close
  signal request_finished -> close_old_connections, close_caches, reset_urlconf
    close_old_connections
      BaseDatabaseWrapper.close_if_unusable_or_obsolete
        DatabaseWrapper.close  (sqlite3)
    close_caches
    reset_urlconf
      set_urlconf(None)
```

The three receivers, in the order the recording shows them:

- `close_old_connections` ran at `request_started` too, and now has a connection to consider. It closes a connection whose autocommit state was not restored, one on which an error occurred and which no longer works, or one past its age. The age comes from the database's `"CONN_MAX_AGE"`, and the default is zero: the connection's `close_at` was set to the moment it was opened, so at the end of every request it is past its age and is closed. A positive age keeps it for later requests on the same thread until it is that many seconds old, as [Opening and closing a connection](../connections/opening.md) tells (`django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete`, `django/db/backends/base/base.py:BaseDatabaseWrapper.connect`).
- `close_caches` calls `close` on every cache this thread has made, which for most backends does nothing (`django/core/cache/__init__.py:close_caches`).
- `reset_urlconf` clears the URLconf set for the thread at the start of the request (`django/core/handlers/base.py:reset_urlconf`).

The settings, the app registry, the handler and its middleware chain, the resolver with its imported URLconf, and the template engine with its compiled template are all as the next request will find them. The recording's second request is that next request: the same path, with every first-use step gone.
