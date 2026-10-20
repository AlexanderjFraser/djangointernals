---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
part: The request cycle
contents: chain, view, exceptions, async, entry, general
---

# Handlers and middleware

The handler, a `WSGIHandler` or an `ASGIHandler`, is ordinarily the object a web server calls for each request. It builds the middleware chain from `settings.MIDDLEWARE` when it is made, and sends each request it makes into that chain, at whose centre stands the view.

A handler does not listen on a socket. A server does that (Gunicorn, uWSGI, Daphne, Uvicorn, or Django's own development server), and talks to the application it hosts through one of two standard interfaces: WSGI, in which a request is a function call, or ASGI, in which it is a coroutine. Django's half of either contract is the **handler**, a single callable object that the server is given once and calls for each request. Nearly everything Django does for a request happens inside that one call.

The two handlers share one base class, `BaseHandler`. A handler turns what the server gives it into an `HttpRequest`, sends that request through the **middleware chain** to get a response back, and turns the response into what the server expects. The first and the last of these differ between WSGI and ASGI ([The two entry points](handlers/entry.md)); the middle one is `BaseHandler`'s, and most of this chapter is spent there.

## The chain is an onion

Middleware is configured as a flat list, `settings.MIDDLEWARE`, but it does not run as a list. When the handler is made, `BaseHandler.load_middleware` turns the list into a nest of callables, one inside the next, and keeps the whole as `BaseHandler._middleware_chain`: serving a request is one call of it. At the centre is `BaseHandler._get_response`, the method that finds the view for a URL and calls it (under ASGI, `BaseHandler._get_response_async`). Around it is the last middleware in the setting; around that, the one before; and so on out to the first. Each layer is called with a request, may do some work, calls the layer inside it, may do more work on the response that comes back, and returns it (`django/core/handlers/base.py:BaseHandler.load_middleware`). The figure draws the nest for three middleware, A, B and C: follow the request in from the left to the centre, and the response out across each layer's boundary.

```text figure=the-chain
MIDDLEWARE = [A, B, C]

in, from the left:  request  ->  A  ->  B  ->  C  ->  BaseHandler._get_response: finds the view for the URL, and calls it
out, to the right:  BaseHandler._get_response  ->  C  ->  B  ->  A  ->  response

A, B, C and BaseHandler._get_response are each wrapped in convert_exception_to_response:
an exception raised inside a layer ordinarily becomes a response at its boundary.
```

*With `MIDDLEWARE = [A, B, C]`, a request enters at A and reaches the view through B and C, and the response returns through the same layers in the opposite order. Each boundary is where an exception raised inside is ordinarily turned into a response.*

This shape explains most of how middleware behaves.

**The order in the setting is the order on the way in, and the reverse on the way out.** The first middleware listed sees the request first and the response last. A middleware that reads on the way in something another one puts on the request has to come after it in the list: `AuthenticationMiddleware` refuses to run unless the session middleware has already set the session on the request (`django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request`).

**Any layer can answer without calling the layer inside it.** A layer that answers so, with a redirect or a page from the cache, cuts the request short. Nothing inside it runs, the view included. The response goes out through that layer's own way out and the layers outside it, never those inside (`django/middleware/__init__.py:MiddlewareMixin.__call__`).

**A middleware's place is part of what it does.** It sees the request as the layers outside it have left it, and the response as the layers inside it have made it. Three of Django's middleware belong to no other subject and are this chapter's, `CommonMiddleware`, `GZipMiddleware` and `BrokenLinkEmailsMiddleware`, and each is explained in part by where it stands ([The general-purpose middleware](handlers/general.md)).

## One request, in order

Three middleware, A, B and C, write down each hook as Django calls it, and a script plays the server: it calls a `WSGIHandler` for a view that returns a plain response, reads the body, and closes the response. Look for the three kinds of hook, each kind in its own order, and for the last line, which comes as the server closes the response.

```text recording=handlers
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

Three things in it carry the rest of the chapter. The `process_request` hooks run outermost first and the `process_response` hooks innermost first, yet the handler calls neither: `MiddlewareMixin`, the base class nearly all of Django's middleware use, calls them when its layer is called, one before it calls the layer inside and the other on what comes back ([Building the middleware chain](handlers/chain.md)) (`django/middleware/__init__.py:MiddlewareMixin.__call__`). The `process_view` hooks and the view are called from the centre ([The centre of the chain](handlers/view.md)) (`django/core/handlers/base.py:BaseHandler._get_response`). And under WSGI the request ends after the handler has returned: the server closes the response, which sends `request_finished` ([The two entry points](handlers/entry.md#who-ends-the-request)) (`django/http/response.py:HttpResponseBase.close`).

The whole request ran on the thread that called the handler, as one chain of function calls. Under ASGI the chain runs around an asynchronous centre, and each layer has a mode of its own. Most of Django's own middleware are synchronous only, so they run together on a thread of the request's own while the centre runs on the event loop, and each change of mode is a crossing between the loop and a thread ([Sync and async in one chain](handlers/async.md)) (`django/core/handlers/base.py:BaseHandler.load_middleware`).

## Where exceptions go

An exception raised inside the chain rarely reaches the server. As the chain is built, each layer is wrapped in `convert_exception_to_response`, which catches an exception from the layer and returns a response in its place, chosen by the exception's class: with Django's own error views, ordinarily a 404 for `Http404`, a 403 for `PermissionDenied`, a 400 for a bad request, and a 500 for anything it does not recognise (`django/core/handlers/exception.py:response_for_exception`). Because each layer is wrapped separately, the layer outside receives a response, and its own work on the way out still runs. An exception the view raises is first offered to the middleware's `process_exception` hooks, and becomes a response at the wrapper around the centre only if none of them answers with one (`django/core/handlers/base.py:BaseHandler._get_response`, `django/core/handlers/base.py:BaseHandler.process_exception_by_middleware`). [How an exception becomes a response](handlers/exceptions.md) has the whole table, and says what does get through (`django/core/handlers/exception.py:convert_exception_to_response`).

## The neighbours

A server's handler is ordinarily made by `get_wsgi_application` or `get_asgi_application`, each of which first runs `django.setup` to load the settings and the apps ([Settings, apps and startup](startup.md)). The request it builds and the response it sends are the subject of [Requests and responses](http.md). At the centre of the chain it hands the path to the URL resolver ([URL routing](urls.md)) and calls what comes back ([Views](views.md)). Most of the middleware Django ships belong to subjects of other chapters: sessions, authentication, CSRF, the security headers, the locale, the cache.
