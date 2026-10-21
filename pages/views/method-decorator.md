---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Decorating a class: `method_decorator`

`method_decorator` lets a decorator written for view functions stand on a method of a class, most often `View.dispatch`, through which one decorator covers every handler method of a class-based view.

A wrapper such as the one `require_http_methods` makes takes the request as its first argument, and uses it. A method's first argument is the instance. So a decorator whose wrapper uses the request cannot be written above a handler method as it stands, and `method_decorator` exists to adapt it (`django/utils/decorators.py:method_decorator`). `never_cache` and `cache_control` catch the mistake when the method is first called: the wrapper of each tests that its first argument has a `META` attribute, as a request does, and raises a `TypeError` that recommends `method_decorator` when it has none (`django/views/decorators/cache.py:_check_request`).

`method_decorator` can be used in either of two ways. Applied to a method in a class body, it returns a replacement for that method. Applied to a class, with the name of a method, it sets the replacement on the class under that name and returns the class; a name that is no attribute of the class is a `ValueError`. For an inherited method such as `dispatch` the second form gives the subclass an attribute of its own and leaves the base class as it was.

## At every call, and once for the marks

The replacement is made by `_multi_decorate`, and it does not apply the decorator to the method when the class is made. A decorator of functions expects something with a view's signature, without `self`, and when the class is made there is no instance to bind. So the replacement applies the decorator at each call: it binds the original method to the instance, wraps the bound method in a `functools.partial`, applies the decorator to that, and calls the wrapper it gets back. On `dispatch` it does so where `dispatch` would run, inside the function `View.as_view` returned, after `View.setup` (`django/utils/decorators.py:_multi_decorate`, `django/views/generic/base.py:View.as_view`).

> **Why.** At the call the bound method is wrapped in a `functools.partial` before the decorator sees it. A bound method object refuses a new attribute and a partial takes one, so `functools.wraps` can give the partial the method's name, docstring and attributes, and the decorator can set its own on it (`django/utils/decorators.py:_multi_decorate`).

A mark, though, an attribute set for some other code to find, has to be on the method before any call is made. So `_multi_decorate` also applies each decorator once, when the class is made, to a stand-in, a function that does nothing, and copies whatever attributes the stand-in comes back with onto the replacement (`django/utils/decorators.py:_update_method_wrapper`).

The Gazette's class *Births* has the decorator *announced* on its `dispatch`, and the decorator says, as it runs, when it is applied, to what, and when its wrapper is called:

```python
# gazette/stamp.py, and the class in gazette/views.py
def announced(view):
    # called(view) is the view's name, and says so when the view is a partial around a bound method
    say(f"announced is applied to {called(view)}")

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        say("the wrapper that announced made is called")
        return view(request, *args, **kwargs)

    return wrapper


@method_decorator(announced, name="dispatch")
class Births(View):
    def get(self, request):
        return HttpResponse("births, marriages and deaths")
```

The figure sets the two moments side by side, the import on the left and a request on the right. Look for *announced* applied in both: to the stand-in once, for its marks, and to the partial at every request, for the call.

```text figure=method-decorator
method_decorator(announced, name="dispatch") on the class Births

once, as the module that defines Births is imported  |  at every request, in the place of dispatch,
                                                     |  inside the function as_view returned, after View.setup
                                                     |
method_decorator(announced, name="dispatch")         |
_multi_decorate: makes the replacement for dispatch  |  the wrapper method_decorator made
  _update_method_wrapper                             |    View.dispatch, bound to the instance, in a partial
    announced applied to a stand-in                  |    announced applied to the partial
    its attributes copied onto the replacement       |    the wrapper announced made, called
the replacement set on Births as dispatch            |      View.dispatch(request)
                                                     |        Births.get(request)
```

*`method_decorator` putting a decorator on a class's `dispatch`: on the left what runs once, as the class is made, and on the right what runs at every request, in the place of `dispatch`. A line indented under another runs inside it; the accent marks the decorator's two applications.*

As the module that defines *Births* is imported, *announced* is applied once, to the stand-in, a function defined inside `_update_method_wrapper`:

```text recording=views
The URLconf is imported: each as_view() is called once; the decorators made from a middleware, and method_decorator, as they run
...
        method_decorator(announced, name='dispatch')
        _multi_decorate(decorators, View.dispatch)
          _update_method_wrapper
            announced is applied to _update_method_wrapper.<locals>.dummy
            ...
```

At a request, *announced* is applied again, to the partial, before its wrapper is called, and both happen inside the wrapper `method_decorator` made:

```text recording=views
GET /births/, twice: a decorator on dispatch is applied again at every call
...
        the wrapper method_decorator made
          announced is applied to a partial around the bound method View.dispatch
          the wrapper that announced made is called
          View.dispatch(request)
            Births.get(request)  ->  an HttpResponse, status 200
            ...
```

A second request does all of it again. For a decorator that merely wraps, the cost is a few small objects made and thrown away, the decorator's wrapper among them. For one that builds something when it is applied, it is that thing built for each request ([A middleware as a decorator](middleware-decorators.md#on-a-method-a-middleware-for-every-request)).

## What `as_view` carries to the URLconf

`as_view` then finishes the job for one method. It copies what decorators left on `dispatch` onto the function it returns, so a mark on `dispatch` reaches the URLconf and a mark on `post` stays on `post`, where none of Django's middleware looks (`django/views/generic/base.py:View.as_view`). Two of the Gazette's classes differ in nothing else:

```python
# gazette/views.py
@method_decorator(csrf_exempt, name="dispatch")
class Tips(View):
    def post(self, request):
        return HttpResponse("thank you")


class TipsMarkedOnPost(View):
    @method_decorator(csrf_exempt)
    def post(self, request):
        return HttpResponse("thank you")
```

The function `as_view` makes from *Tips*, the one a URLconf holds, carries `"csrf_exempt"`; the one made from *TipsMarkedOnPost* does not, though its `post` has the mark:

```text recording=views
views.Tips.as_view().csrf_exempt  ->  True
views.Tips.dispatch.csrf_exempt  ->  True
hasattr(views.TipsMarkedOnPost.as_view(), "csrf_exempt")  ->  False
views.TipsMarkedOnPost.post.csrf_exempt  ->  True
...
```

With `CsrfViewMiddleware` installed, a form posted to each of the two without a token gets two different answers:

```text recording=views
POST /tips/ and POST /tips/marked/ with CsrfViewMiddleware installed and no token sent
    POST /tips/, whose class has csrf_exempt on dispatch
    start_response("200 OK", headers)
    POST /tips/marked/, whose class has csrf_exempt on post
    log, WARNING to django.security.csrf: Forbidden (CSRF cookie not set.): /tips/marked/
    start_response("403 Forbidden", headers)
```

## A list of decorators

Given a list of decorators, `_multi_decorate` applies them from the last to the first, so that the first in the list is outermost, as if they had been written one above another in that order (`django/utils/decorators.py:_multi_decorate`). `LoginView` is decorated so: one `method_decorator`, on the class with `name="dispatch"`, gives its `dispatch` `login_not_required`, `sensitive_post_parameters()`, `csrf_protect` and `never_cache`, outermost first. Only `login_not_required` leaves a mark on the method, `"login_required"` set false, and `as_view` copies it onto the function it returns (`django/contrib/auth/views.py:LoginView`, `django/contrib/auth/decorators.py:login_not_required`).
