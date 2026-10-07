---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `View.as_view` and dispatch

How a class becomes a view: `View.as_view` returns a function that makes an instance of the class for each request, `View.setup` stores the request on the instance, and `View.dispatch` calls the method named for the request's HTTP method.

`View` is the base class of the generic views and of every view made with `as_view`, and it is small. Its docstring calls it intentionally simple: it dispatches by HTTP method and checks a few things (`django/views/generic/base.py:View`). None of the templates, the querysets or the forms of the generic views is in `View`: they are in the mixins and the base views that are combined with it. What `View` itself deals with is a mismatch. The handler wants one callable that serves every request, and `as_view` gives it one that makes an instance for each. Django's documentation states the result: each request served by a class-based view has an independent state, so that it is safe to store state on the instance (`docs/ref/class-based-views/index.txt`).

The examples are the Gazette's colophon, a class with one handler method and one attribute, routed twice:

```python
# gazette/views.py
class Colophon(View):
    """Who prints the paper, and in what type."""

    type_size = 9

    def get(self, request):
        return HttpResponse(f"set in {self.type_size} point")


# gazette/urls.py
path("colophon/", views.Colophon.as_view(), name="colophon"),
path("colophon/large/", views.Colophon.as_view(type_size=14), name="colophon-large"),
```

## Once, when the URLconf is imported

A URLconf does not hold a class. It holds what `View.as_view` returned when the module was imported. The method is a `classonlymethod`, a `classmethod` that raises `AttributeError` when it is looked up on an instance, so it can be called on the class and on nothing else (`django/utils/decorators.py:classonlymethod`).

```text recording=views
import gazette.urls
...
  Colophon.as_view()  ->  a function named 'view', with view_class Colophon and view_initkwargs {}
  Colophon.as_view(type_size=14)  ->  a function named 'view', with view_class Colophon and view_initkwargs {'type_size': 14}
```

Each of the two calls returned a function of its own, so the two patterns hold two functions made from one class.

Arguments to `as_view` are checked before anything is made, and the check is strict. An argument whose name is in the class's `http_method_names` is refused. Were it accepted, `View.__init__` would set it on each instance, over the handler method of that name. So is any name that is not already an attribute of the class, and a misspelt name therefore raises `TypeError` when the URLconf is imported (`django/views/generic/base.py:View.as_view`).

```text recording=views
views.Colophon.as_view().__doc__  ->  'Who prints the paper, and in what type.'
views.Colophon.as_view().__module__  ->  'gazette.views'
views.Colophon.as_view(type_size=14).view_initkwargs  ->  {'type_size': 14}
views.Colophon.as_view(colour="red")  ->  raises TypeError: Colophon() received an invalid keyword 'colour'. as_view only accepts arguments that are already attributes of the class.
views.Colophon.as_view(get=None)  ->  raises TypeError: The method name get is not accepted as a keyword argument to Colophon().
views.Colophon().as_view  ->  raises AttributeError: This method is available only on the class, not on instances.
```

The first two lines show the function taking its docstring and its module from the class. The third shows an accepted argument, which is kept on the function. The fourth and fifth are the two refusals, and the last is the method being asked for on an instance.

Having made the function, `as_view` dresses it. It sets two attributes that say where the function came from, `"view_class"` and `"view_initkwargs"`. It copies the class's docstring and module, and the annotations of `dispatch`. It leaves the function's name and qualified name alone, on purpose: the comment in the source says that `"view_class"` is the robust way to find out what the view is. And it copies onto the function every attribute that `dispatch` carries, which is how a mark left by a decorator on that method reaches the object the middleware will look at ([View decorators](decorators.md#decorating-a-class)). If the class's handler methods are coroutine functions, the function is marked as one too ([Asynchronous views](async.md#a-class-whose-handler-methods-are-coroutines)).

```text figure=once-and-each-request
Once, when the URLconf's module is imported:

  Colophon.as_view()              checks its arguments against the class
      returns a function, view    view.view_class = Colophon, view.view_initkwargs = {}
  path("colophon/", view)         the URLconf holds the function, not the class

Each request for /colophon/:

  the handler calls view(request)
      Colophon(**initkwargs)         a new instance, with the arguments as_view was given set on it
      View.setup(request)            the instance gets request, args, kwargs, and head if it has get and no head
      View.dispatch(request)         "GET" leads to the instance's get
          Colophon.get(request)      returns the response
```

*What happens once and what happens for each request. `as_view` runs when the URLconf is imported and leaves a function behind. The function makes an instance of the class each time it is called.*

## Each request

The function that `as_view` returns makes an instance, calls `setup` on it, and calls `dispatch`. Those are the three lines under the function's own, at the top of each recording of a request on this page.

```text recording=views
GET /colophon/large/: the arguments given to as_view() are given to each instance
    BaseHandler._get_response
      view(request)  (the function as_view returned for Colophon)
        View.__init__(type_size=14)  (a new Colophon)
        View.setup(request)
        View.dispatch(request)
          Colophon.get(request)  ->  an HttpResponse, status 200
          -> an HttpResponse, status 200
        -> an HttpResponse, status 200
    start_response("200 OK", headers)
    the server sends the body: 'set in 14 point'
```

The instance is made with the arguments that `as_view` was given, and `View.__init__` sets each as an attribute:

```text recording=views
views.Colophon.as_view()(request("/colophon/"))  ->  an HttpResponse, status 200, content 'set in 9 point'
views.Colophon(type_size=30).type_size  ->  30
```

Since the arguments were captured when the URLconf was imported, every instance receives the very same objects: a dictionary passed to `as_view` is one dictionary shared by all the requests the pattern ever serves. The same is true of anything written as a class attribute. What belongs to one request is what a method assigns on `self` (`django/views/generic/base.py:View.__init__`).

Between `setup` and `dispatch` the function checks that the instance has an attribute `request`, and raises an `AttributeError` that asks whether `setup` was overridden without a call to `super()`. What `dispatch` returns is what the function returns (`django/views/generic/base.py:View.as_view`).

Nothing outside the instance keeps it once the function has returned, unless the response does: a `TemplateResponse` from a generic view has the view in its context, under the name `"view"`, and the instance lasts as long as that response (`django/views/generic/base.py:ContextMixin.get_context_data`).

## `View.setup`

`View.setup` puts the request, the positional arguments and the keyword arguments on the instance as `View.request`, `View.args` and `View.kwargs`. Other methods read them from there: a generic view's `get_object` reads the slug from `kwargs` without being passed it (`django/views/generic/base.py:View.setup`).

It does one more thing first. If the instance has a `get` and no `head`, it sets `head` to be the `get` method. A request with the method `"HEAD"` is then dispatched like any other, finds that attribute, and runs the same code as a `"GET"`:

```text recording=views
HEAD /colophon/: a class with get and no head
    BaseHandler._get_response
      view(request)  (the function as_view returned for Colophon)
        View.__init__()  (a new Colophon)
        View.setup(request)
        View.dispatch(request)
          Colophon.get(request)  ->  an HttpResponse, status 200
          -> an HttpResponse, status 200
        -> an HttpResponse, status 200
    start_response("200 OK", headers)
    what the handler returned has a body of 14 bytes
```

What comes back is the response a `"GET"` would have had, with its body. Leaving the body out of what is sent is the server's work ([The response object](../http/response.md#the-body-of-an-httpresponse)).

A class that needs to prepare something for all of its handler methods overrides `setup`, calls `super().setup` and adds its own attributes. The method's docstring gives that as its purpose: to initialize attributes shared by all view methods.

## `View.dispatch`

`View.dispatch` chooses the handler method. It lower-cases the request's method and looks the result up in the list `View.http_method_names`: `"get"`, `"post"`, `"put"`, `"patch"`, `"delete"`, `"head"`, `"options"` and `"trace"`. If the name is in the list, the handler method is the instance's attribute of that name, when it has one. In every other case it is `View.http_method_not_allowed` (`django/views/generic/base.py:View.dispatch`).

The attribute need not be one the class wrote. `"HEAD"` found the one `setup` added, and `"OPTIONS"` finds a method that `View` supplies for every class: an empty 200 response with an `"Allow"` header and a `Content-Length` of zero (`django/views/generic/base.py:View.options`).

```text recording=views
OPTIONS /colophon/: answered by View.options
    BaseHandler._get_response
      view(request)  (the function as_view returned for Colophon)
        View.__init__()  (a new Colophon)
        View.setup(request)
        View.dispatch(request)
          View.options(request)
            View._allowed_methods  ->  ['GET', 'HEAD', 'OPTIONS']
            View.view_is_async  ->  False
            -> an HttpResponse, status 200, Allow 'GET, HEAD, OPTIONS'
          -> an HttpResponse, status 200, Allow 'GET, HEAD, OPTIONS'
        -> an HttpResponse, status 200, Allow 'GET, HEAD, OPTIONS'
    start_response("200 OK", headers), with Allow: GET, HEAD, OPTIONS
    the server sends the body: ''
```

The header's list comes from `View._allowed_methods`: every name in `http_method_names` that the instance has an attribute for, in upper case. For Colophon that is three names, of which the class wrote one.

A request's method can be turned away for either of two reasons, and the answer is the same. The class may have no method of that name, or the name may be outside the list:

```text recording=views
PUT /colophon/: the class has no method of that name
    BaseHandler._get_response
      view(request)  (the function as_view returned for Colophon)
        View.__init__()  (a new Colophon)
        View.setup(request)
        View.dispatch(request)
          View.http_method_not_allowed(request)
            View._allowed_methods  ->  ['GET', 'HEAD', 'OPTIONS']
            log, WARNING to django.request: Method Not Allowed (PUT): /colophon/
            View.view_is_async  ->  False
            -> an HttpResponseNotAllowed, status 405, Allow 'GET, HEAD, OPTIONS'
          -> an HttpResponseNotAllowed, status 405, Allow 'GET, HEAD, OPTIONS'
        -> an HttpResponseNotAllowed, status 405, Allow 'GET, HEAD, OPTIONS'
    start_response("405 Method Not Allowed", headers), with Allow: GET, HEAD, OPTIONS
    the server sends the body: ''
```

`View.http_method_not_allowed` returns an `HttpResponseNotAllowed`, a 405 with the same `"Allow"` header, and logs a warning to `"django.request"` (`django/views/generic/base.py:View.http_method_not_allowed`). A request for `"PROPFIND"`, a method that is not in the list at all, gets the same 405 with the same header.

A class narrows what it accepts by assigning a shorter `http_method_names`. A method the class does define is then unreachable if its name is not in the list, because `dispatch` tests the list before it looks at the instance.

The line `View.view_is_async` in both recordings is each of these two methods asking whether the class's handler methods are coroutine functions. When they are, a plain response is not what the caller expects, and the method returns the response wrapped in a coroutine ([Asynchronous views](async.md#a-class-whose-handler-methods-are-coroutines)).

## Why so much is hung on `dispatch`

Every request for a class-based view passes through `setup` and then `dispatch`, whatever its method, and `dispatch` is the one whose return value is the response. That makes it the place to put whatever must happen for the view as a whole.

A decorator written for function views can be applied there, through `method_decorator`, and then covers every handler method at once. Django's own `LoginView` is decorated so, with four decorators applied to its `dispatch` (`django/contrib/auth/views.py:LoginView`). And a mixin that decides whether the request may proceed overrides `dispatch`, makes its test, and calls `super().dispatch` only if the test passes. The three mixins in `django/contrib/auth/mixins.py` that are built on `AccessMixin` all work so: `LoginRequiredMixin.dispatch` answers a user who is not logged in through `AccessMixin.handle_no_permission`, which returns a redirect to the login page or raises `PermissionDenied`, and otherwise hands the request on (`django/contrib/auth/mixins.py:LoginRequiredMixin.dispatch`). Such a mixin has to come before `View` among the class's bases, so that its `dispatch` is the first one found.
