---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `View.as_view` and dispatch

`View.as_view` makes a view class into the callable a URLconf holds: a function that, at each request, makes an instance of the class, calls `View.setup` to store the request on it, and calls `View.dispatch`, which calls the handler method named for the request's HTTP method.

`View` is the base class of the generic views and of every view made with `as_view`, and it is small: it dispatches by HTTP method and makes a few checks (`django/views/generic/base.py:View`). None of the templates, the querysets or the forms of the generic views is in `View`: they are in the mixins and the base views that are combined with it. What `View` itself deals with is a mismatch. The handler wants one callable that serves every request, and `as_view` gives it one that makes an instance for each, so that each request has state of its own and a handler method may keep what it likes on `self` (`docs/ref/class-based-views/index.txt`).

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

The figure draws the colophon at the two moments a class-based view acts: once, as the URLconf is imported, and then at each request, inside a call of the function that `as_view` left behind.

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

## What `as_view` returns

The colophon's patterns hold what `View.as_view` returned when the URLconf was imported, and each call of `as_view` returns a function of its own: the two patterns call it twice, and hold two functions made from one class.

```text recording=views
import gazette.urls
...
  Colophon.as_view()  ->  a function named 'view', with view_class Colophon and view_initkwargs {}
  Colophon.as_view(type_size=14)  ->  a function named 'view', with view_class Colophon and view_initkwargs {'type_size': 14}
  ...
```

`as_view` is a `classonlymethod`, a `classmethod` that raises `AttributeError` when it is looked up on an instance, so it can be called on the class and on nothing else (`django/utils/decorators.py:classonlymethod`). It checks its arguments before it makes anything, and refuses two kinds with a `TypeError`. It refuses a name in the class's `View.http_method_names`, which `View.__init__` would otherwise set on each instance over the handler method of that name. It refuses any name that is not already an attribute of the class, so a misspelt name raises as the URLconf is imported (`django/views/generic/base.py:View.as_view`). Each `TypeError` names the class and the argument, and the method looked up on an instance is refused by `classonlymethod`:

```text recording=views
...
views.Colophon.as_view(colour="red")  ->  raises TypeError: Colophon() received an invalid keyword 'colour'. as_view only accepts arguments that are already attributes of the class.
views.Colophon.as_view(get=None)  ->  raises TypeError: The method name get is not accepted as a keyword argument to Colophon().
views.Colophon().as_view  ->  raises AttributeError: This method is available only on the class, not on instances.
...
```

Having made the function, `as_view` dresses it. It sets two attributes that say where the function came from, `"view_class"` and `"view_initkwargs"`, and copies onto it the class's docstring and module and the annotations of `dispatch`, but not the class's name. And it copies onto the function every attribute that `dispatch` carries, which is how a mark left by a decorator on that method reaches the object the middleware will look at ([Decorating a class: `method_decorator`](method-decorator.md)). If `View.view_is_async` finds the class's handler methods to be coroutine functions, the function is marked as one too ([Asynchronous views](async.md#a-class-whose-handler-methods-are-coroutines)) (`django/views/generic/base.py:View.as_view`).

> **Why.** The function is called `"view"` whatever class it was made from, and its qualified name is `"View.as_view.<locals>.view"`. `as_view` leaves the two names alone on purpose: they "are intentionally left unchanged as view_class should be used to robustly determine the name of the view instead", says the comment there (`django/views/generic/base.py:View.as_view`). Code that reads the function's own name gets `"view"`, as the handler's message does when a class-based view returns `None` ([What the handler asks of a view](callable.md#what-a-view-may-return)).

## What the function does for each request

The function that `as_view` returns does the same at every call. It makes an instance of the class with the arguments `as_view` was given, calls `setup` on the instance, makes sure that `setup` left the request there, and returns what the instance's `dispatch` returns. It holds the instance only in a local variable, so once it has returned, the function no longer holds the instance (`django/views/generic/base.py:View.as_view`). Requested twice, the colophon is two calls of one function, and each begins with a new *Colophon* before `setup` and `dispatch` are called on it:

```text recording=views
GET /colophon/, twice: a class-based view is a function that makes an instance for each request
    BaseHandler._get_response
      view(request)  (the function as_view returned for Colophon)
        View.__init__()  (a new Colophon)
        View.setup(request)
        View.dispatch(request)
          Colophon.get(request)  ->  an HttpResponse, status 200
    ...
    and the same request again
        ...
        View.__init__()  (a new Colophon)
        ...
```

`View.__init__` sets each argument it is given as an attribute of the instance, over the class's attribute of that name, so the colophon's second pattern, given a type size of 14, makes instances that set the page in 14 point:

```text recording=views
GET /colophon/large/: the arguments given to as_view() are given to each instance
...
        View.__init__(type_size=14)  (a new Colophon)
...
    the server sends the body: 'set in 14 point'
```

> **Trap.** The arguments given to `as_view` are captured as the URLconf is imported, and every instance the function makes is given the very same objects: a dictionary passed to `as_view` is one dictionary shared by every request the pattern serves, and a request that changes it changes it for the requests that follow. The same is true of anything written as a class attribute. Django's documentation warns against passing a list, a dictionary or any other mutable object to a view for that reason (`docs/ref/class-based-views/index.txt`). What belongs to one request is what a method assigns on `self` (`django/views/generic/base.py:View.as_view`).

## `View.setup`

`View.setup` puts the request, the positional arguments and the keyword arguments on the instance as `View.request`, `View.args` and `View.kwargs`. Other methods read them from there: `SingleObjectMixin.get_object` reads the slug from `kwargs` without being passed it (`django/views/generic/base.py:View.setup`).

It does one more thing first. If the instance has a `get` and no `head`, it sets `head` to be the `get` method, so a `"HEAD"` is dispatched like any other method and runs the same code as a `"GET"`. Under `View.dispatch` the colophon's `"HEAD"` runs its `get`, and the response the handler returns still has its body:

```text recording=views
HEAD /colophon/: a class with get and no head
...
        View.dispatch(request)
          Colophon.get(request)  ->  an HttpResponse, status 200
...
    what the handler returned has a body of 14 bytes
```

Leaving the body out of what is sent is the server's work ([The response object](../http/response.md#the-body-of-an-httpresponse)).

A class that prepares something for all of its handler methods overrides `setup`, calls `super().setup` and sets its own attributes. Between `setup` and `dispatch` the function checks that the instance has a `request`, and if it has none, raises an `AttributeError` that asks whether `setup` was overridden without a call to `super()` (`django/views/generic/base.py:View.as_view`).

> **Why.** `setup` is a hook of its own so that a class can prepare, before `dispatch` runs, what all of its handler methods share. Its docstring gives its purpose as to "initialize attributes shared by all view methods" (`django/views/generic/base.py:View.setup`), and the release that added it, Django 2.2, says that it "allows mixins to set up instance attributes for reuse in child classes" (`docs/releases/2.2.txt`).

## `View.dispatch`

`View.dispatch` chooses the handler method. It lower-cases the request's method and looks the result up in the list `View.http_method_names`: `"get"`, `"post"`, `"put"`, `"patch"`, `"delete"`, `"head"`, `"options"` and `"trace"`. If the name is in the list, the handler method is the instance's attribute of that name, when it has one. In every other case it is `View.http_method_not_allowed` (`django/views/generic/base.py:View.dispatch`).

The attribute need not be one the class wrote. `"HEAD"` found the one `setup` added, and `"OPTIONS"` finds `View.options`, which `View` supplies for every class: an empty 200 response with an `"Allow"` header and a `Content-Length` of zero (`django/views/generic/base.py:View.options`). The header's list is made by `View._allowed_methods`, every name in `http_method_names` that the instance has an attribute for, in upper case, and for the colophon it is three names, of which the class wrote one:

```text recording=views
OPTIONS /colophon/: answered by View.options
...
          View.options(request)
            View._allowed_methods  ->  ['GET', 'HEAD', 'OPTIONS']
            ...
            -> an HttpResponse, status 200, Allow 'GET, HEAD, OPTIONS'
            ...
```

A method is turned away for either of two reasons, and the answer is the same: the instance has no attribute of that name, or the name is outside the list, as `"PROPFIND"` is. `dispatch` then calls `View.http_method_not_allowed`, which logs a warning to `"django.request"` and returns an `HttpResponseNotAllowed`, a 405 with the same `"Allow"` header, from inside a coroutine if `View.view_is_async` finds the class asynchronous, as `View.options` does ([Asynchronous views](async.md#a-class-whose-handler-methods-are-coroutines)) (`django/views/generic/base.py:View.http_method_not_allowed`). The colophon defines no handler method for `"PUT"`, so the request is logged and refused:

```text recording=views
PUT /colophon/: the class has no method of that name
...
          View.http_method_not_allowed(request)
            View._allowed_methods  ->  ['GET', 'HEAD', 'OPTIONS']
            log, WARNING to django.request: Method Not Allowed (PUT): /colophon/
            View.view_is_async  ->  False
            -> an HttpResponseNotAllowed, status 405, Allow 'GET, HEAD, OPTIONS'
            ...
```

A class narrows what it accepts by assigning a shorter `http_method_names`. A handler method the class defines is then unreachable if its name is not in the list, because `dispatch` tests the list before it looks at the instance (`django/views/generic/base.py:View.dispatch`).

## Why so much is hung on `dispatch`

Every request for a class-based view passes through `setup` and then `dispatch`, whatever its method, and `dispatch` is the one whose return value the function returns. That makes it the place to put whatever must happen for the view as a whole.

A decorator written for function views, applied to `dispatch` through `method_decorator`, covers every handler method at once, which is how Django's own `LoginView` is decorated ([Decorating a class: `method_decorator`](method-decorator.md)) (`django/utils/decorators.py:method_decorator`, `django/contrib/auth/views.py:LoginView`).

A mixin that decides whether the request may proceed overrides `dispatch`, makes its test, and calls `super().dispatch` only if the test passes, as `LoginRequiredMixin` does, answering a user who is not logged in through `AccessMixin.handle_no_permission` ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md#the-mixins-and-accessmixinhandle_no_permission)) (`django/contrib/auth/mixins.py:LoginRequiredMixin.dispatch`). Such a mixin has to stand before the view class among the bases, so that its `dispatch` is found before `View.dispatch`.
