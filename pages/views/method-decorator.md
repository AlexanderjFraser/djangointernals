---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Decorating a class: `method_decorator`

`method_decorator` puts a decorator written for view functions on a method of a class, most often `View.dispatch`. It applies the decorator anew at every call, to a partial of the method bound to the request's instance, and once as the class is made, to a stand-in, so that the decorator's marks are on the method before any call; `View.as_view` then carries the marks of `dispatch` to the function a URLconf holds.

A wrapper such as the one `require_http_methods` makes takes the request as its first argument, and uses it. A method's first argument is the instance. So a decorator whose wrapper uses the request cannot be written above a handler method as it stands, and `method_decorator` exists to adapt it (`django/utils/decorators.py:method_decorator`).

It can be used in either of two ways. Applied to a method in a class body, it returns a replacement for that method. Applied to a class, with the name of a method, it sets the replacement on the class under that name and returns the class; a name that is no attribute of the class is a `ValueError`. For an inherited method such as `dispatch` the second form gives the subclass an attribute of its own and leaves the base class as it was.

## At every call, and once for the marks

The replacement is made by `_multi_decorate`, and it does not apply the decorator to the method when the class is made. A decorator of functions expects something with a view's signature, without `self`, and when the class is made there is no instance to bind. So the replacement applies the decorator at each call: it binds the original method to the instance, wraps the bound method in a `functools.partial`, applies the decorator to that, and calls the wrapper it gets back. On `dispatch` it does so where `dispatch` would run, inside the function `as_view` returned, after `View.setup` (`django/utils/decorators.py:_multi_decorate`, `django/views/generic/base.py:View.as_view`).

> **Why.** At the call the bound method is wrapped in a `functools.partial` before the decorator sees it. The comment where that is done gives the reason: new attributes cannot be set on a bound method object, only on a function. A partial takes them: those `functools.wraps` sets on it there, the method's name among them, and any the decorator sets on what it is given (`django/utils/decorators.py:_multi_decorate`).

A mark, though, has to be on the method before any call is made. So `_multi_decorate` also applies each decorator once, when the class is made, to a stand-in, a function that does nothing, and copies whatever attributes the stand-in comes back with onto the replacement (`django/utils/decorators.py:_update_method_wrapper`).

The figure sets the two moments side by side for the Gazette's decorator announced on the `dispatch` of its class Births. Look for the decorator applied in both: to the stand-in once, for its marks, and to the partial at every request, for the call.

```text figure=method-decorator
method_decorator(announced, name="dispatch") on the class Births

once, as the module that defines Births is imported      at every request, in the place of dispatch,
                                                         inside the function as_view returned, after View.setup

method_decorator(announced, name="dispatch")
_multi_decorate: makes the replacement for dispatch      the wrapper method_decorator made
  _update_method_wrapper                                   View.dispatch, bound to the instance, in a partial
    announced applied to a stand-in                        announced applied to the partial
    its attributes copied onto the replacement             the wrapper announced made, called
the replacement set on Births as dispatch                    View.dispatch(request)
                                                               Births.get(request)
```

*`method_decorator` putting announced on the `dispatch` of Births: on the left what runs once, as the class is made, and on the right what runs at every request, in the place of `dispatch`. A line indented under another runs inside it; the accent marks the two applications of announced.*

Births has the decorator announced on its `dispatch`, and announced says when it is applied, and to what, and when its wrapper is called:

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

As the module that defines Births is imported, announced is applied once, to the stand-in, under `_update_method_wrapper`:

```text recording=views
The URLconf is imported: each as_view() is called once; the decorators made from a middleware, and method_decorator, as they run
...
        method_decorator(announced, name='dispatch')
        _multi_decorate(decorators, View.dispatch)
          _update_method_wrapper
            announced is applied to _update_method_wrapper.<locals>.dummy
            ...
```

At a request it is applied again, inside the call, to a partial around the bound `dispatch` of this request's instance, and only then is its wrapper called:

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

`as_view` then finishes the job for one method. It copies what decorators left on `dispatch` onto the function it returns, so a mark on `dispatch` reaches the URLconf and a mark on `post` stays on `post`, where no middleware looks (`django/views/generic/base.py:View.as_view`). Two of the Gazette's classes differ in nothing else:

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

The function `as_view` makes from Tips, the one a URLconf holds, carries `"csrf_exempt"`; the one made from TipsMarkedOnPost does not, though its `post` has the mark:

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

Given a list of decorators, `_multi_decorate` applies them from the last to the first, so that the first in the list is outermost, as if they had been written one above another in that order (`django/utils/decorators.py:_multi_decorate`). Of two decorators that the Gazette gives a class's `dispatch` in one list, the one listed second is applied first, to its stand-in at import and to the partial at each request, and the one listed first is then applied, at a request, to the other's wrapper, so that its own is the first called. `LoginView` is decorated so: one `method_decorator`, on the class with `name="dispatch"`, gives its `dispatch` `login_not_required`, `sensitive_post_parameters()`, `csrf_protect` and `never_cache`, outermost first. Only `login_not_required` leaves a mark, `"login_required"` set false, and `as_view` copies it onto the function it returns (`django/contrib/auth/views.py:LoginView`, `django/contrib/auth/decorators.py:login_not_required`).
