---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The error views

The four views of `django/views/defaults.py`: `page_not_found`, `server_error`, `bad_request` and `permission_denied`. They make the page a client sees when the handler turns an exception into a 404, a 500, a 400 or a 403 and does not answer with a debug page: how the handler finds one, what it is called with, which template it renders, and what it sends when the project has no such template.

When a view raises, or no pattern matches the path, the handler has to answer all the same. It decides the kind of answer from the class of the exception ([How an exception becomes a response](../handlers/exceptions.md)). It does not write the page. For that it calls a view, and that view is the subject here. Django's four do as little as an error page should: each renders one template if the project has supplied it, and otherwise sends a page of a few lines that is built into the module.

## Found through the URLconf, called like a view

The handler asks the resolver for the error view by status. `URLResolver.resolve_error_handler` looks in the URLconf's module for a variable named `handler404`, or `handler400`, `handler403`, `handler500`, and takes the default of the same name from `django/conf/urls/__init__.py` when the module has none. The defaults are the four views of this section (`django/urls/resolvers.py:URLResolver.resolve_error_handler`).

A request for a page the Gazette does not have, with `settings.DEBUG` off:

```text recording=views
GET /no-such-page/ with DEBUG = False and no template named 404.html
    BaseHandler._get_response  raises Resolver404
    response_for_exception(request, Resolver404)
      get_exception_response(request, resolver, 404, exception)
        URLResolver.resolve_error_handler(404)  ->  django.views.defaults.page_not_found
        the wrapper made from _EnsureCsrfToken
          CsrfViewMiddleware.process_request  (_EnsureCsrfToken)
          CsrfViewMiddleware.process_view  (_EnsureCsrfToken)
          page_not_found(request, Resolver404)
            get_template('404.html')  raises TemplateDoesNotExist
            Engine.from_string(ERROR_PAGE_TEMPLATE, filled in)
            -> an HttpResponseNotFound, status 404
          CsrfViewMiddleware.process_response  (_EnsureCsrfToken)
          -> an HttpResponseNotFound, status 404
        -> an HttpResponseNotFound, status 404
      -> an HttpResponseNotFound, status 404
    log, WARNING to django.request: Not Found: /no-such-page/
    start_response("404 Not Found", headers)
    the server sends the body, 179 bytes
```

What `get_exception_response` calls is not `page_not_found` itself. Each of the four is decorated with `requires_csrf_token`, so the callable is that decorator's wrapper, and a `CsrfViewMiddleware` runs its hooks around the error view without ever refusing the request ([A middleware as a decorator](middleware-decorators.md#the-decorators-made-this-way)). A project's template for a 400, a 403 or a 404 can therefore use the CSRF token, though the request may never have reached the middleware that normally prepares it. A template for a 500 cannot, being rendered without the request.

The views for 400, 403 and 404 are called with the request and the exception, the latter as a keyword argument. The one for 500 is called with the request alone (`django/core/handlers/exception.py:get_exception_response`, `django/core/handlers/exception.py:handle_uncaught_exception`). A view of the project's own, named in the URLconf, has to accept the same. A system check binds each handler's signature to that number of positional arguments, two or one; it does not test for a parameter named exception ([The URL checks, and listing the patterns](../urls/checks.md)).

With `settings.DEBUG` on, the views for 404 and 500 are not reached: the handler answers those with [the debug pages](debug.md). The 403 view is called whatever the setting. With the setting on, the 400 view is reached only for a multipart body that could not be parsed.

## One template each

Each view takes a `template_name` parameter whose default is the name by which a project supplies its own page.

| view | template | what the template is given | response |
|---|---|---|---|
| `page_not_found` | `"404.html"` | the request; `"request_path"`, the path in quoted form; `"exception"`, a message | `HttpResponseNotFound` |
| `permission_denied` | `"403.html"` | the request; `"exception"`, the exception as text | `HttpResponseForbidden` |
| `bad_request` | `"400.html"` | the request | `HttpResponseBadRequest` |
| `server_error` | `"500.html"` | nothing | `HttpResponseServerError` |

*The four error views, the template each looks for, and what it renders it with.*

`page_not_found` gives the template two variables. `"request_path"` is the request's path passed through `quote`: the docstring says it is quoted to prevent a content injection attack, the path being text of the client's choosing that a project's template may display. `"exception"` is the message the `Http404` was raised with, when it has one that is a string, and the name of the exception's class when it has not. The second case is there for the resolver's own exception, whose argument is a dictionary, holding the path and, where the resolver got as far as trying patterns, the patterns that were tried, and not a sentence for a reader (`django/views/defaults.py:page_not_found`).

The Gazette, given a template that prints both, answers a path that matched nothing and an article that was not found:

```text recording=views
    URLResolver.resolve_error_handler(404)  ->  django.views.defaults.page_not_found
    the wrapper made from _EnsureCsrfToken
      CsrfViewMiddleware.process_request  (_EnsureCsrfToken)
      CsrfViewMiddleware.process_view  (_EnsureCsrfToken)
      page_not_found(request, Resolver404)
        get_template('404.html')
...
the server sends the body: 'Nothing is printed at /no-such-page/ (Resolver404).\n'
```

```text recording=views
    URLResolver.resolve_error_handler(404)  ->  django.views.defaults.page_not_found
    the wrapper made from _EnsureCsrfToken
      CsrfViewMiddleware.process_request  (_EnsureCsrfToken)
      CsrfViewMiddleware.process_view  (_EnsureCsrfToken)
      page_not_found(request, Http404)
        get_template('404.html')
...
the server sends the body: 'Nothing is printed at /articles/no-such-article/ (No article found matching the query).\n'
```

`bad_request` hands its template the request and deliberately nothing about what was wrong. A comment gives the reason: so as not to disclose any sensitive information. `permission_denied` passes the exception's text (`django/views/defaults.py:bad_request`, `django/views/defaults.py:permission_denied`).

`server_error` is the barest. It renders its template with no context and no request, so no context processor runs and the template has no variables to rely on. It is the view of last resort: if it fails there is nothing behind it ([How an exception becomes a response](../handlers/exceptions.md#what-does-reach-the-server)).

```text recording=views
response_for_exception(request, LookupError)
  signal got_request_exception, for LookupError: no edition for 1790
  handle_uncaught_exception(request, resolver, exc_info)
    URLResolver.resolve_error_handler(500)  ->  django.views.defaults.server_error
    the wrapper made from _EnsureCsrfToken
      CsrfViewMiddleware.process_request  (_EnsureCsrfToken)
      CsrfViewMiddleware.process_view  (_EnsureCsrfToken)
      server_error(request)
        get_template('500.html')  raises TemplateDoesNotExist
        -> an HttpResponseServerError, status 500
      CsrfViewMiddleware.process_response  (_EnsureCsrfToken)
      -> an HttpResponseServerError, status 500
    -> an HttpResponseServerError, status 500
  log, ERROR to django.request: Internal Server Error: /editions/1790/
  -> an HttpResponseServerError, status 500
start_response("500 Internal Server Error", headers)
```

## Without a template

All four look for their template with `get_template` and catch `TemplateDoesNotExist`. What happens next depends on which name the view was asked for. If it was the default name, the view answers with a page made from `ERROR_PAGE_TEMPLATE`, a short HTML document with a title, one heading and one paragraph, held as a string in the module. If the caller had asked for some other name, the exception is raised again: a project that names a template of its own is told when it is absent.

In the recording each answer is given by its class, its status and what stands between the page's body tags:

```text recording=views
The four error views, called directly
    defaults.page_not_found(request("/x y/"), Http404("no such edition"))  ->  an HttpResponseNotFound, status 404, between its body tags, white space run together: <h1>Not Found</h1><p>The requested resource was not found on this server.</p>
    defaults.page_not_found(request("/x y/"), Http404())  ->  an HttpResponseNotFound, status 404, between its body tags, white space run together: <h1>Not Found</h1><p>The requested resource was not found on this server.</p>
    defaults.page_not_found(request("/x y/"), Http404({"path": "x y/", "tried": []}))  ->  an HttpResponseNotFound, status 404, between its body tags, white space run together: <h1>Not Found</h1><p>The requested resource was not found on this server.</p>
    defaults.page_not_found(request(), Http404(), template_name="gazette/gone.html")  ->  raises TemplateDoesNotExist
    defaults.permission_denied(request(), PermissionDenied("subscribers only"))  ->  an HttpResponseForbidden, status 403, between its body tags, white space run together: <h1>403 Forbidden</h1><p></p>
    defaults.bad_request(request(), BadRequest("no"))  ->  an HttpResponseBadRequest, status 400, between its body tags, white space run together: <h1>Bad Request (400)</h1><p></p>
    defaults.server_error(request())  ->  an HttpResponseServerError, status 500, between its body tags, white space run together: <h1>Server Error (500)</h1><p></p>
    with a template named 404.html: defaults.page_not_found(request("/x y/"), Http404("no such edition"))  ->  an HttpResponseNotFound, status 404, content 'Nothing is printed at /x%20y/ (no such edition).\n'
```

The built-in 404 page says nothing of the path or the exception. `page_not_found` renders it through a template engine made on the spot, with the same two variables its template would have had, though the text uses neither; the comment says this is to allow the context to be inspected in tests. The other three put the string straight into a response.

## A custom error view

A project replaces one of these by assigning to `handler404` or its siblings in the URLconf: a view, or the dotted path to one. The replacement is called as the default is, directly by the handler, with the arguments given above. It may be a function or what `as_view` returns. If it returns a template response that has not been rendered, the handler renders it before going on. It may not be a coroutine function: the handler does not await what an error view returns.

What the replacement returns is used as it is, status included. The handler chooses which error view to ask, and never corrects the status of the answer.

A request refused by the CSRF check is answered by none of these. `CsrfViewMiddleware` has an error view of its own, named by `settings.CSRF_FAILURE_VIEW` ([Security](../security.md)).
