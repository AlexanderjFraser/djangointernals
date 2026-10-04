---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
part: The request cycle
contents: entry, chain, view, exceptions, async
---

# Handlers and middleware

The handler is the one object a web server calls for every request. It builds the middleware chain once, when it is made, and from then on sends each request down that chain to a view and hands the response back.

A handler does not listen on a socket. A server does that: Gunicorn, uWSGI, Daphne, Uvicorn, or Django's own development server. The server talks to the Python application it hosts through one of two standard interfaces: WSGI, in which a request is a function call, or ASGI, in which it is a coroutine. Django's half of either contract is a single callable object, the **handler**. The server is given the handler once, when the process starts, and calls it for each request. Nearly everything Django does for a request, from parsing its headers to rendering a template, happens inside that one call.

There are two handlers, `WSGIHandler` and `ASGIHandler`, and most of what they do is inherited from one base class, `BaseHandler`. A handler turns what the server gives it into an `HttpRequest`, sends that request through the **middleware chain** to get an `HttpResponse` back, and turns the response into what the server expects. The first and the last of these differ between WSGI and ASGI. The middle one is `BaseHandler`'s, which has it in a synchronous and an asynchronous form, and it is where most of this chapter is spent.

## The chain is an onion

Middleware is configured as a flat list, `settings.MIDDLEWARE`, but it does not run as a list. When a handler is made, `BaseHandler.load_middleware` turns the list into a nest of callables, one inside the next. At the centre is `BaseHandler._get_response`, the method that finds the view for a URL and calls it (under ASGI its coroutine twin, `BaseHandler._get_response_async`). Around it is the last middleware in the setting; around that, the one before; and so on out to the first. Each layer is called with a request, may do some work, calls the layer inside it, may do more work on the response that comes back, and returns it (`django/core/handlers/base.py:BaseHandler.load_middleware`).

```text figure=the-chain
MIDDLEWARE = [A, B, C]

request   ->  A  ->  B  ->  C  ->  BaseHandler._get_response: finds the view for the URL, and calls it
response  <-  A  <-  B  <-  C  <-

A, B, C and BaseHandler._get_response are each wrapped in convert_exception_to_response:
an exception raised inside a layer becomes a response at its boundary.
```

*With `MIDDLEWARE = [A, B, C]`, a request enters at A and reaches the view through B and C, and the response returns through the same layers in the opposite order. Each boundary is where an exception raised inside is turned into a response.*

This shape explains most of how middleware behaves.

**The order in the setting is the order on the way in, and the reverse on the way out.** The first middleware listed sees the request first and the response last. A middleware that reads something another one puts on the request has to come after it in the list: `AuthenticationMiddleware` refuses to run unless the session middleware has already set the session on the request (`django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request`).

**Any layer can answer without calling the layer inside it.** A middleware that returns a response of its own, a redirect or a page from the cache, cuts the request short. Nothing inside it runs, the view included, and the response travels back out through the layers outside it only.

The nest is built once and kept on the handler as `BaseHandler._middleware_chain`. Serving a request is one call of that object, and nothing about the chain is decided per request.

## One request, in order

What follows was recorded from a running Django. Three middleware, A, B and C, write down each hook as Django calls it. A script plays the server's part: it calls a `WSGIHandler` with a request for a view that returns a plain response, reads the body, and closes the response.

```text
WSGI, GET /plain/: a view that returns a response
    signal: request_started
    A.process_request
    B.process_request
    C.process_request
    A.process_view
    B.process_view
    C.process_view
    the view
    C.process_response(200)
    B.process_response(200)
    A.process_response(200)
    start_response("200 OK", headers)
    the server closes the response
    signal: request_finished
```

Read against the code:

1. **The handler's entry.** The server calls `WSGIHandler.__call__`. It sends the `request_started` signal, builds a `WSGIRequest` from what the server passed, and gives it to `BaseHandler.get_response`, which calls the chain (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).
2. **The way in.** Each layer's `process_request` runs, outermost first. The handler never calls that method, or knows of it. What the handler calls is the middleware itself, and `process_request` is how `MiddlewareMixin`, the base class nearly all of Django's middleware use, spends its turn on the way in (`django/middleware/__init__.py:MiddlewareMixin.__call__`).
3. **The centre.** `BaseHandler._get_response` resolves the URL to a view, runs the `process_view` hooks in the same outermost-first order, and calls the view (`django/core/handlers/base.py:BaseHandler._get_response`).
4. **The way out.** Each layer's `process_response` runs, innermost first. Back in `WSGIHandler.__call__`, the status and the headers go to the server's `start_response` function, and the response object itself is returned as the body. When the server has sent the body it closes the response, and closing it is what sends `request_finished` (`django/http/response.py:HttpResponseBase.close`).

The whole request ran on the thread that called the handler, as one ordinary chain of function calls. Under ASGI the same chain runs, with the complication that some of its layers may be synchronous and others not; [Sync and async in one chain](handlers/async.md) is about that.

## Where exceptions go

An exception raised inside the chain rarely reaches the server. As the chain is built, each layer is wrapped in `convert_exception_to_response`, which catches an exception from the layer and returns a response in its place: a 404 for `Http404`, a 403 for `PermissionDenied`, a 500 for anything it does not recognise. Because each layer is wrapped separately, the layer outside receives a response, and its own work on the way out still runs. [How an exception becomes a response](handlers/exceptions.md) has the whole table, and says what does get through (`django/core/handlers/exception.py:convert_exception_to_response`).

## The neighbours

The handler is the hub of the request cycle, and each thing it touches has a chapter of its own. A handler is made by `get_wsgi_application` or `get_asgi_application`, after `django.setup` has loaded the settings and the apps ([Settings, apps and startup](startup.md)). The request it builds and the response it sends are the subject of [Requests and responses](http.md). At the centre of the chain it hands the path to the URL resolver ([URL routing](urls.md)) and calls what comes back ([Views](views.md)). And most of the middleware Django ships belong to other subjects: sessions and authentication, CSRF and the security headers, the locale, the cache. This chapter is about the machinery they all plug into.
