---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The error views

The error views write the page a client sees when the handler answers an exception with a 404, a 500, a 400 or a 403 and not with a debug page. Django's own, for a page not found, a server error, a bad request and a permission denied, are in `django/views/defaults.py`, and send a page built from `ERROR_PAGE_TEMPLATE` when the project has no template of its own; the root URLconf replaces any of them through `handler404` and its kin.

When a view raises, or no pattern matches the path, the handler has to answer all the same. It decides the kind of answer from the class of the exception ([How an exception becomes a response](../handlers/exceptions.md)). It does not write the page. Outside the debug pages, an **error view** does. Django's four do as little as an error page should: each renders one template if the project has supplied it, and otherwise sends a page of a few lines that is built into the module.

## Found through the URLconf, called like a view

The handler asks the resolver for the error view by status. `URLResolver.resolve_error_handler` looks in the URLconf's module for a variable named `handler404`, or `handler400`, `handler403`, `handler500`, and takes the default of the same name from `django/conf/urls/__init__.py` when the module has none. The defaults are Django's four (`django/urls/resolvers.py:URLResolver.resolve_error_handler`).

When the Gazette is asked for a page it does not have, `get_exception_response`, the handler's function that finds an error view and calls it, is handed a wrapper around `page_not_found`. The wrapper runs a `CsrfViewMiddleware`'s hooks either side of the view, and between them the view finds no template and fills in a page of its own:

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
          ...
```

Each of the four is decorated with `requires_csrf_token`: the callable is that decorator's wrapper, and the `CsrfViewMiddleware` it runs never refuses the request ([A middleware as a decorator](middleware-decorators.md#the-decorators-made-this-way)) (`django/views/decorators/csrf.py:requires_csrf_token`).

> **Why.** An error view can be called for a request that `CsrfViewMiddleware.process_view` never saw: a path that matches no pattern raises before any `process_view` hook runs (`django/core/handlers/base.py:BaseHandler._get_response`). The comment above the four views gives that as the reason for the decorator, in case a template needs `{% csrf_token %}` (`django/views/defaults.py`). A project's template for a 400, a 403 or a 404 can therefore use the token. The 500 view is called through the same wrapper, but renders its template without the request, so its template cannot use it (`django/views/defaults.py:server_error`).

The views for 400, 403 and 404 are called with the request and the exception, the latter as a keyword argument named exception. The one for 500 is called with the request alone (`django/core/handlers/exception.py:get_exception_response`, `django/core/handlers/exception.py:handle_uncaught_exception`).

With `settings.DEBUG` on, the views for 404 and 500 are not reached: the handler answers those with the debug pages ([The debug pages and `ExceptionReporter`](debug.md)). The 403 view is called whatever the setting. With the setting on, the 400 view is reached only for a multipart body that could not be parsed, since `response_for_exception` sends a `MultiPartParserError` to it without asking `settings.DEBUG`, which it asks for a `BadRequest` or a `SuspiciousOperation` (`django/core/handlers/exception.py:response_for_exception`). A request refused by the CSRF check is answered by none of these: `CsrfViewMiddleware` has an error view of its own, named by `settings.CSRF_FAILURE_VIEW` ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md)).

## One template each

Each view takes a `template_name` parameter whose default is the name by which a project supplies its own page.

| view | template | what the template is given | response |
|---|---|---|---|
| `page_not_found` | `"404.html"` | the request; `"request_path"`, the path in quoted form; `"exception"`, a message or class name | `HttpResponseNotFound` |
| `permission_denied` | `"403.html"` | the request; `"exception"`, the exception as text | `HttpResponseForbidden` |
| `bad_request` | `"400.html"` | the request | `HttpResponseBadRequest` |
| `server_error` | `"500.html"` | nothing | `HttpResponseServerError` |

*The four error views, the template each looks for, and what it renders it with.*

`page_not_found` gives the template two variables. `"request_path"` is the request's path passed through `quote`. `"exception"` is the message the `Http404` was raised with, when it has one that is a string, and the name of the exception's class when it has not. The test for a string is there for the resolver's own exception, whose argument is a dictionary and not a sentence for a reader: it holds the path and, where the resolver got as far as trying patterns, the patterns that were tried (`django/views/defaults.py:page_not_found`).

Given a 404.html that prints both, `page_not_found` names the resolver's own exception, for a path that matched nothing, by its class:

```text recording=views
GET /no-such-page/ with DEBUG = False and a template named 404.html
...
          page_not_found(request, Resolver404)
            get_template('404.html')
...
    the server sends the body: 'Nothing is printed at /no-such-page/ (Resolver404).\n'
```

An `Http404` with a message is named by it instead, here the one `SingleObjectMixin.get_object` raises for an article that does not exist (`django/views/generic/detail.py:SingleObjectMixin.get_object`):

```text recording=views
GET /articles/no-such-article/ with a template named 404.html: the message of the Http404 a view raised
...
          page_not_found(request, Http404)
            get_template('404.html')
...
    the server sends the body: 'Nothing is printed at /articles/no-such-article/ (No article found matching the query).\n'
```

`bad_request` hands its template the request and nothing about what was wrong; `permission_denied` passes the exception's text (`django/views/defaults.py:bad_request`, `django/views/defaults.py:permission_denied`).

> **Why.** Two of the views are careful with what they give a template. `page_not_found` quotes the path "to prevent a content injection attack", in its docstring's words: the path is text of the client's choosing, and a project's template may display it. `bad_request` passes nothing of the exception, as the comment above its last line says, "to not disclose any sensitive information" (`django/views/defaults.py:page_not_found`, `django/views/defaults.py:bad_request`).

`server_error` is the barest. It renders its template with no context and no request, so no context processor runs and the template has no variables to rely on. It is the view of last resort: if it fails there is nothing behind it ([How an exception becomes a response](../handlers/exceptions.md#what-does-reach-the-server)) (`django/views/defaults.py:server_error`). A `LookupError` raised by a view, which the handler does not recognise, ends there, and `server_error` is called with the request alone:

```text recording=views
GET /editions/1790/ with DEBUG = False: the view raises LookupError
...
          server_error(request)
            get_template('500.html')  raises TemplateDoesNotExist
            -> an HttpResponseServerError, status 500
            ...
```

## Without a template

All four look for their template with `get_template` and catch `TemplateDoesNotExist`. What happens next depends on which name the view was asked for. If it was the default name, the view answers with a page made from `ERROR_PAGE_TEMPLATE`, a short HTML document with a title, one heading and one paragraph, held as a string in the module. If the caller had asked for some other name, the exception is raised again: a project that names a template of its own is told when it is absent (`django/views/defaults.py`).

No built-in page prints anything of the exception: each view writes the title and the paragraph itself, the paragraph empty but for the 404's, so the 403 page has none of the text a project's 403.html is given. Called directly, `page_not_found` sends the same page whether its exception holds a message, nothing, or the resolver's dictionary, and raises when it is asked for a template of another name that is missing:

```text recording=views
The four error views, called directly
    defaults.page_not_found(request("/x y/"), Http404("no such edition"))  ->  an HttpResponseNotFound, status 404, between its body tags, white space run together: <h1>Not Found</h1><p>The requested resource was not found on this server.</p>
    defaults.page_not_found(request("/x y/"), Http404())  ->  an HttpResponseNotFound, status 404, between its body tags, white space run together: <h1>Not Found</h1><p>The requested resource was not found on this server.</p>
    defaults.page_not_found(request("/x y/"), Http404({"path": "x y/", "tried": []}))  ->  an HttpResponseNotFound, status 404, between its body tags, white space run together: <h1>Not Found</h1><p>The requested resource was not found on this server.</p>
    defaults.page_not_found(request(), Http404(), template_name="gazette/gone.html")  ->  raises TemplateDoesNotExist
    defaults.permission_denied(request(), PermissionDenied("subscribers only"))  ->  an HttpResponseForbidden, status 403, between its body tags, white space run together: <h1>403 Forbidden</h1><p></p>
    defaults.bad_request(request(), BadRequest("no"))  ->  an HttpResponseBadRequest, status 400, between its body tags, white space run together: <h1>Bad Request (400)</h1><p></p>
    defaults.server_error(request())  ->  an HttpResponseServerError, status 500, between its body tags, white space run together: <h1>Server Error (500)</h1><p></p>
    ...
```

`page_not_found` still renders its page through a template engine made on the spot, with the two variables its template would have had, so that a test can inspect the context. The other three put the string straight into a response (`django/views/defaults.py:page_not_found`).

## A custom error view: `handler404` and its kin

A project replaces one of these by assigning to `handler404` or its kin in the root URLconf: a view, or the dotted path to one. The replacement is called as the default is, directly by the handler, with the same arguments. It may be a function or what `as_view` returns, but not a coroutine function: under either handler nothing awaits what an error view returns, so a coroutine takes the response's place. The request then fails where the coroutine is first used as a response, and ends in a 500 or in an exception that leaves the handler ([What the handler asks of a view](callable.md#what-a-view-may-return)) (`django/core/handlers/exception.py:get_exception_response`, `django/core/handlers/exception.py:response_for_exception`, `django/core/handlers/base.py:BaseHandler.get_response`).

> **Trap.** The system check of the error views binds each one's signature to positional arguments, two for 400, 403 and 404 and one for 500, and does not ask for a parameter named exception ([The URL checks, and listing the patterns](../urls/checks.md#the-four-checks-tagged-urls)) (`django/core/checks/urls.py:check_custom_error_handlers`). The handler passes the exception by keyword (`django/core/handlers/exception.py:get_exception_response`). So a `handler404` whose second parameter is named *exc* passes the checks, and at the first 404 its call raises `TypeError`; `handle_uncaught_exception` answers, and the 404 becomes a 500 ([How an exception becomes a response](../handlers/exceptions.md#the-error-views)). With `settings.DEBUG` on, the 404 view is never called, so the failure first shows where the setting is off.

What the replacement returns is kept as it is, status included: the handler chooses which error view to ask and never corrects the status of the answer, and `response_for_exception` renders a template response that has not been rendered ([How an exception becomes a response](../handlers/exceptions.md#which-exception-becomes-which-response)) (`django/core/handlers/exception.py:response_for_exception`). A `handler404` that answers 200 is sent as a 200, and the handler logs nothing: `response_for_exception` logs no `Http404`, and `BaseHandler.get_response` logs only a status of 400 or more (`django/core/handlers/base.py:BaseHandler.get_response`).
