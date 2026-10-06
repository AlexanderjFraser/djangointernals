---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The response returns to the server

What an `HttpResponse` is, what each of the seven default middleware does to it on the way out, how `WSGIHandler.__call__` hands it to the server, and who ends the request.

The view returned an `HttpResponse`. From here the request is over in all but name, and the response travels back out through the middleware in the reverse of the order they were entered, three of them adding headers, until the handler gives it to the server. The server sends the body and then closes the response, and closing it is what ends the request.

```text recording=overview
                        HttpResponse.__init__(content)
                          response["Content-Type"] = "text/html; charset=utf-8"
                    BaseHandler.check_response
                  XFrameOptionsMiddleware.process_response  (status 200)
                    response["X-Frame-Options"] = "DENY"
                MessageMiddleware.process_response  (status 200)
                  BaseStorage.update
            CsrfViewMiddleware.process_response  (status 200)
          CommonMiddleware.process_response  (status 200)
            response["Content-Length"] = "148"
        SessionMiddleware.process_response  (status 200)
          SessionBase.is_empty
      SecurityMiddleware.process_response  (status 200)
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "same-origin"
        response["Cross-Origin-Opener-Policy"] = "same-origin"
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

The lines are indented as the recording nests them: the response is made inside the view, inside the innermost layer, and each line further out is one layer nearer the server.

## The response object

An `HttpResponse` is a status, a set of headers, cookies, and a body held in memory. `HttpResponseBase.__init__` makes the headers, a `ResponseHeaders` that keeps each as a pair and looks them up without regard to case, and if no `Content-Type` was given sets one of `"text/html"` with the charset of `settings.DEFAULT_CHARSET`; the status is the class's `status_code`, 200, unless one was passed (`django/http/response.py:HttpResponseBase.__init__`, `django/http/response.py:ResponseHeaders`). A header's name must be ASCII, a value that Latin-1 cannot hold is MIME-encoded, and neither may hold a newline: `ResponseHeaders.__setitem__` refuses one that does with `BadHeaderError`, which is what keeps a value taken from the request from injecting a header (`django/http/response.py:ResponseHeaders.__setitem__`).

The body is set by the `HttpResponse.content` setter. A string is encoded with the response's charset, bytes are kept, and an iterator is consumed into bytes at once, so that the response can be iterated more than once (`django/http/response.py:HttpResponse.content`). What `render` gave the constructor was the rendered template as a string, and from here on it is bytes. A response that streams is a different class, `StreamingHttpResponse`, whose body is produced as the server iterates it; [The response object](../http/response.md) and [Streaming and file responses](../http/streaming.md) have the two.

## The way out

Each layer's `process_response` is given the response the layer inside it returned, and returns the response the layer outside it will see, which may be a different object. Read in the order they run, which is the reverse of `settings.MIDDLEWARE`:

**`XFrameOptionsMiddleware`** sets `X-Frame-Options` to the value of `settings.X_FRAME_OPTIONS`, `"DENY"` by default, unless the header is already there or the response was marked exempt by the decorator (`django/middleware/clickjacking.py:XFrameOptionsMiddleware.process_response`).

**`MessageMiddleware`** asks the request's message storage to store what has not been read, into a cookie or the session; here there is nothing to store (`django/contrib/messages/middleware.py:MessageMiddleware.process_response`, `django/contrib/messages/storage/base.py:BaseStorage.update`).

**`AuthenticationMiddleware`** has no `process_response`.

**`CsrfViewMiddleware`** sets the CSRF cookie only when `HttpRequest.META` was marked with `"CSRF_COOKIE_NEEDS_UPDATE"` during the request, which `get_token` does whenever something asks for a token, a template's `csrf_token` tag among them, and which the replacing of a malformed cookie on the way in does too; nothing in this request asked (`django/middleware/csrf.py:get_token`) (`django/middleware/csrf.py:CsrfViewMiddleware.process_response`).

**`CommonMiddleware`** does two things. To a 404, when `settings.APPEND_SLASH` is true and the path without its trailing slash would resolve with one added, it answers a permanent redirect to the path with the slash: this is the redirect that makes `"/entries/2026"` reach `"/entries/2026/"`, and it happens here, on the way out, after the view has not been found. To any response that is not streaming and has no `Content-Length`, it adds one, the length of the body (`django/middleware/common.py:CommonMiddleware.process_response`).

**`SessionMiddleware`** reads the session's two flags and whether it is empty. A session that was modified, or any session when `settings.SESSION_SAVE_EVERY_REQUEST` is true, is saved and its cookie set, unless it is empty or the response is a server error; a session that was merely accessed makes the response vary on the `"Cookie"` header; a session that was emptied has its cookie deleted. This request's session was never touched, so nothing is done (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`, `django/contrib/sessions/backends/base.py:SessionBase.is_empty`).

**`SecurityMiddleware`** adds the headers that are on by default: `X-Content-Type-Options` as `"nosniff"`, `Referrer-Policy` and `Cross-Origin-Opener-Policy` as `"same-origin"`, each only if the response does not already have it. `Strict-Transport-Security` is added only to a secure request and only when `settings.SECURE_HSTS_SECONDS` is set (`django/middleware/security.py:SecurityMiddleware.process_response`).

The outermost layer's return is what the chain returns. `BaseHandler.get_response` then registers the request's own `close` among the response's closers, so that closing the response closes any files that were uploaded with the request, and logs the response if its status is 400 or more; a 200 is not logged (`django/core/handlers/base.py:BaseHandler.get_response`).

## Handing it to the server

Back in `WSGIHandler.__call__`, the handler stores its own class on the response, for the signal sent later to name as sender, and builds the two things the WSGI interface wants: the status line, from the status code and its standard reason phrase, and the list of headers, which is the response's headers followed by one `Set-Cookie` for each cookie. It passes both to the server's function and returns the response object itself (`django/core/handlers/wsgi.py:WSGIHandler.__call__`). An `HttpResponse` is iterable, and iterating it yields its body in one piece (`django/http/response.py:HttpResponse.__iter__`). That is all WSGI asks of a body. The recording's `start_response` line shows the six headers in the order they were set: the one the constructor set and the five the middleware added.

## Who ends the request

The handler has returned, but the request is not over: the server still has to send the body, and when it has, the WSGI specification obliges it to call `close` on what it was given. `HttpResponseBase.close` runs each closer registered on the response, the request's among them, and then sends `request_finished` (`django/http/response.py:HttpResponseBase.close`). Three receivers are connected in a serving process.

- `close_old_connections` again, which now has a connection to consider. It closes a connection whose autocommit state was not restored, one on which an error occurred and which no longer works, or one past its age. The age comes from the database's `"CONN_MAX_AGE"`, and the default is zero: the connection's `close_at` was set to the moment it was opened, so at the end of every request it is past its age and is closed. A positive age keeps it for the next request on the same thread (`django/db/backends/base/base.py:BaseDatabaseWrapper.close_if_unusable_or_obsolete`, `django/db/backends/base/base.py:BaseDatabaseWrapper.connect`).
- `close_caches` calls `close` on every cache that has been made, which for most backends does nothing (`django/core/cache/__init__.py:close_caches`).
- `reset_urlconf` clears the URLconf set for the thread at the start of the request (`django/core/handlers/base.py:reset_urlconf`).

The request has now left no trace in the process but what it was meant to leave: a log line, if any, and whatever the view wrote to the database. The settings, the registry, the handler and its chain, the resolver with its imported URLconf, the template engine with its compiled template, are all as the next request will find them, and the next request is what the recording's second request shows: the same path, with every first-use step gone.
