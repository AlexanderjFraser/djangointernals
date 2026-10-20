---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What the handler asks of a view

A view is any callable that `BaseHandler._get_response` can call with a request and the arguments a path captured. The rest of the contract is what the callable may be, what it may return, which `BaseHandler.check_response` checks, and what it may raise; the attributes, such as `"csrf_exempt"` and `"view_class"`, that other code reads from it without calling it; and how it is named, by `ResolverMatch` among others, when something has to name it.

To call a view, the handler never asks whether it is a function, an object or the product of a class. `View` exists, and the generic views are built on it, but nothing on the request's path asks whether a view extends it. A view is defined by how it is used, and the use is a single line of `BaseHandler._get_response`, or of its asynchronous twin under ASGI: the callable that the resolver returned is called with the request, then the positional arguments, then the keyword arguments (`django/core/handlers/base.py:BaseHandler._get_response`).

## The arguments

The request comes first, always. What follows it comes from the `ResolverMatch`. The keyword arguments are what the path's parameters captured, together with any extra arguments written in the URLconf after the view, or after an `include` on the way to it. For a route written for `path`, each captured value has already been turned from text by its converter; the named groups of a regular expression arrive as text. A pattern supplies positional arguments only if it is a regular expression none of whose groups has a name ([Routes, regular expressions and converters](../urls/patterns.md#which-groups-become-arguments)).

The call is a plain Python call, so a view whose parameters do not fit what the path supplies fails as any function would, with a `TypeError`, and the request ends as a 500. Nothing compares an ordinary view's signature with its route beforehand. The system checks that do bind a signature are for views Django calls on its own account: the error views ([The error views](errors.md#found-through-the-urlconf-called-like-a-view)) and the view named by `settings.CSRF_FAILURE_VIEW`.

Before the call the handler may do more with the view, all of it described in [The centre of the chain](../handlers/view.md). The `process_view` hooks are shown the view and its arguments first, and one of them may answer in its place. `BaseHandler.make_view_atomic` may wrap the view in a transaction. And a view that is a coroutine function is wrapped so that a synchronous handler can call it, or the other way about ([Asynchronous views](async.md)).

## What can be a view

`path` and `re_path` take whatever is callable and keep it as `URLPattern.callback` (`django/urls/conf.py:_path`). In practice that is a function, or the function that `View.as_view` returns, which is what a class-based view is by the time it reaches a URLconf ([`View.as_view` and dispatch](as-view.md)), or some other object that can be called. The Gazette's views of the last kind are two instances of a class with a `__call__` method and a `functools.partial` that fixes one of a function's arguments.

```python
# gazette/views.py
def tide(request, port):
    return HttpResponse(f"high water at {port}: noon")


class Almanac:
    def __init__(self, text):
        self.text = text

    def __call__(self, request):
        if self.text:
            return HttpResponse(self.text)


# gazette/urls.py
path("tide/", partial(views.tide, port="the east quay"), name="tide"),
path("almanac/", views.Almanac("new moon on the 17th"), name="almanac"),
path("almanac/blank/", views.Almanac(None), name="almanac-blank"),
```

The resolver hands each back as it was given, an Almanac and a `functools.partial` (`django/urls/resolvers.py:URLPattern.resolve`). All of these are called the same way. Where they differ is in what Django can find out about them, which shows when it has to name one.

A class given to `path` without `as_view` is callable too, and `path` keeps it. For a subclass of `View` the system check `"urls.E009"` reports the mistake ([The URL checks, and listing the patterns](../urls/checks.md#the-four-checks-tagged-urls)), and a request routed to it all the same ends as a 500: the handler calls the class with the request, and `View.__init__`, which takes keyword arguments only, raises a `TypeError` (`django/urls/resolvers.py:URLPattern._check_callback`, `django/views/generic/base.py:View.__init__`). An instance of such a class cannot be called, and `path` refuses it ([From a URLconf to a tree](../urls/urlconf.md#what-path-and-re_path-make)).

## What a view may return

After the call the handler passes the result to `BaseHandler.check_response`, which refuses `None` and a coroutine that was never awaited. Each raises a `ValueError` whose message names the view (`django/core/handlers/base.py:BaseHandler.check_response`). The first is what a view returns when one of its branches falls off the end without a `return`, as the almanac above does when it has no text.

For a function the message gives its module and name, and for anything that is not a function the object's class with `.__call__` after it. The three messages below, for a function, a class-based view and the almanac with no text, name three kinds of view, and the second is misleading:

```text recording=views
A view that returns None: how the handler names the view in its complaint
    GET /nothing/, a function that returns None
    signal got_request_exception, for ValueError: The view gazette.views.nothing didn't return an HttpResponse object. It returned None instead.
    ...
    GET /blank/, a class whose get returns None
    signal got_request_exception, for ValueError: The view gazette.views.view didn't return an HttpResponse object. It returned None instead.
    ...
    GET /almanac/blank/, an object whose __call__ returns None
    signal got_request_exception, for ValueError: The view gazette.views.Almanac.__call__ didn't return an HttpResponse object. It returned None instead.
    ...
```

> **Trap.** The message for a class-based view names a function, gazette.views.view, that is in no file of the project, and does not say which class is at fault. The function that `as_view` returns is a function, so the check names it as one: by its module, which `as_view` has set to the class's, and by its own name, which is `"view"` for every class. The check does not follow `"view_class"`, which would have named the class; [`View.as_view` and dispatch](as-view.md) tells why the function's name is left alone (`django/views/generic/base.py:View.as_view`).

The check ends there. Neither this method nor any code of the handler after it tests whether the object is an `HttpResponse`, so a view that returns a string is found out only when some later code uses the string as a response, and which code that is decides what the client gets:

```text recording=views
A view that returns something that is not a response
    GET /headline/, a function that returns a string, with no middleware
    the handler raises AttributeError to the server: 'str' object has no attribute '_resource_closers'
    the same request with CommonMiddleware installed
    signal got_request_exception, for AttributeError: 'str' object has no attribute 'status_code'
    log, ERROR to django.request: Internal Server Error: /headline/
    start_response("500 Internal Server Error", headers)
```

With no middleware the first such use is in `BaseHandler.get_response`, outside the chain and its exception handling, so the `AttributeError` goes to the server. With `CommonMiddleware` installed, that middleware's `process_response` is the first to touch the object, the failure happens inside the chain, and the client gets an ordinary 500 (`django/core/handlers/base.py:BaseHandler.get_response`).

One kind of response gets more from the handler. If what the view returned has a callable `render`, as a `TemplateResponse` has, the handler passes it to the `process_template_response` hooks and then renders it ([The centre of the chain](../handlers/view.md#template-responses)).

## What a view may raise

An `Exception` raised by a view is offered to the `process_exception` hooks, and if none of them answers, `convert_exception_to_response` turns it into a response according to the exception's class, a 404 for `Http404` from Django's own error view ([How an exception becomes a response](../handlers/exceptions.md)) (`django/core/handlers/exception.py:response_for_exception`).

For a view, raising is therefore a second way of answering. The shortcuts and the generic views use it freely: `get_object_or_404` and `SingleObjectMixin.get_object` raise `Http404` when a query finds nothing, and the code that called them does not have to test for it. On a site with `settings.DEBUG` off, the page is then made by an error view ([The error views](errors.md)).

## What other code reads from a view

Parts of Django need to treat one view differently from the rest: leave out a check, skip a redirect, find out which class is behind a function. They look before the view is called, or without calling it. So the view carries an attribute, a **mark**, set by a decorator, by `as_view`, or by the admin site for its own views, which the code that needs to know looks for with `getattr` and a default, or with `hasattr` (`django/middleware/csrf.py:CsrfViewMiddleware.process_view`, `django/urls/resolvers.py:ResolverMatch.__init__`).

| the attribute | set by | read by | what it means |
|---|---|---|---|
| `"csrf_exempt"`, true | `csrf_exempt` | `CsrfViewMiddleware.process_view`, and `AdminSite.admin_view` | the middleware does not check this view's requests for a CSRF token |
| `"_non_atomic_requests"`, a set | `non_atomic_requests` in `django/db/transaction.py` | `BaseHandler.make_view_atomic` | the database aliases for which the view is not wrapped in a transaction, though `"ATOMIC_REQUESTS"` is on |
| `"should_append_slash"`, false | `no_append_slash` | `CommonMiddleware.should_redirect_with_slash`, and `AdminSite.catch_all_view` | a path that matches this view only with a slash added is not redirected to it |
| `"login_required"`, false | `login_not_required` | `LoginRequiredMiddleware.process_view` | the middleware lets a request through without a logged-in user |
| `"login_url"`, `"redirect_field_name"` | `user_passes_test`, on the wrapper it makes; the first also by `AdminSite.get_urls`, on the wrappers of the site's own views, not a model's | `LoginRequiredMiddleware.get_login_url`, `LoginRequiredMiddleware.get_redirect_field_name` | the login URL that middleware redirects to, and the name of the query parameter that carries the address to come back to |
| `"view_class"` | `View.as_view` | `ResolverMatch.__init__`, `URLPattern.lookup_str`, the command listurls, `django.contrib.admindocs` | the class behind the function |

*The marks Django reads from a view before or without calling it, each with the value that changes anything.*

The handler and the middleware it calls all look at one object: the one in the URLconf, which is the outermost wrapper when the view is decorated. A mark set by an inner decorator has to reach it. It does when each decorator outside copies the wrapped function's attributes onto its own wrapper, which `functools.wraps` does, and every wrapper made in `django/views/decorators/` is passed through it. `as_view` has the same problem with a class and solves it for one method: it copies the attributes of `dispatch` onto the function it returns ([Decorating a class: `method_decorator`](method-decorator.md)).

> **Trap.** A decorator whose wrapper does not copy the wrapped function's attributes loses every mark under it, and the code that looks for a mark then finds its default. The Gazette's decorator bare is one: its wrapper calls the view and copies nothing. Put around a view marked by `csrf_exempt`, `never_cache` passes the mark on, and bare does not.

```text recording=views
...
never_cache(csrf_exempt(views.front)).csrf_exempt  ->  True
hasattr(views.bare(csrf_exempt(views.front)), "csrf_exempt")  ->  False
...
```

## How a view is named

A function has a name. Whether a view has one depends on what kind of callable it is, and each place that needs a name works one out for itself: the message of `check_response`, above, by one rule, and `ResolverMatch` by another.

`ResolverMatch.__init__` keeps a dotted path for the view as `ResolverMatch._func_path`. If the callable has a `"view_class"` attribute, the class stands in for it. Then an object with no `__name__` is named by its class and its class's module, and anything else by its own name and module (`django/urls/resolvers.py:ResolverMatch.__init__`). Of the Gazette's views, the colophon is named by the class behind its function, and the almanac and the `functools.partial`, which have no `__name__`, by their types, so that the partial's name says nothing of the function it wraps:

```text recording=views
...
resolve("/")._func_path  ->  'gazette.views.front'
...
resolve("/colophon/")._func_path  ->  'gazette.views.Colophon'
resolve("/colophon/").view_name  ->  'colophon'
...
resolve("/almanac/")._func_path  ->  'gazette.views.Almanac'
...
resolve("/tide/")._func_path  ->  'functools.partial'
resolve("/tide/").view_name  ->  'tide'
...
```

That path is what a debug page prints as the view an exception was raised in (`django/views/debug.py:get_caller`). `ResolverMatch.view_name` is the pattern's name when it has one, as the colophon's and the tide's patterns have, and the dotted path when it has not, after any namespaces.

`URLPattern.lookup_str` is a second dotted path, worked out by other rules: it looks through a `functools.partial` to the function inside and through `"view_class"` to the class, and the resolver collects it from every pattern, which the admin's documentation consults to tell whether a dotted name is that of a view of the URLconf ([Reversing a name](../urls/reversing.md#the-tables)) (`django/urls/resolvers.py:URLPattern.lookup_str`).
