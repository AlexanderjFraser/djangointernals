---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Asynchronous views

A view may be a coroutine function, and the handler finds out by asking `inspect.iscoroutinefunction` of whatever the URLconf holds. `View.as_view` keeps the answer true for a class by marking the function it returns with `inspect.markcoroutinefunction` when `View.view_is_async` finds the class's handler methods are coroutines, and the decorators of `django/views/decorators/` keep a coroutine function one; a wrapper that does not hides the coroutine function, and the handler calls the wrapper as an ordinary function.

Django serves requests through a synchronous handler and an asynchronous one, and either can call either kind of view. What it must know beforehand is which kind it has, because the two are called differently: a function is called and returns a response, and a coroutine function is called, returns a coroutine, and the coroutine has to be awaited before there is a response. A coroutine function called like a function raises nothing at the call. It hands back a coroutine object where a response was wanted.

The Gazette has a wire service written both ways, and one class that is a mistake:

```python
# gazette/views.py
async def wire(request):
    return HttpResponse("from the wire")


class Wire(View):
    async def get(self, request):
        return HttpResponse("from the wire")


class Muddle(View):
    def get(self, request):
        return HttpResponse("a list")

    async def post(self, request):
        return HttpResponse("added")
```

## The handler's test: `inspect.iscoroutinefunction`

`BaseHandler._get_response` and its asynchronous twin both put one question to the view before calling it: `inspect.iscoroutinefunction`. The synchronous handler wraps a coroutine function in `async_to_sync` and then calls it as a function. The asynchronous handler wraps anything that is not a coroutine function in `sync_to_async`, so that it runs in a thread, and awaits the result either way (`django/core/handlers/base.py:BaseHandler._get_response`, `django/core/handlers/base.py:BaseHandler._get_response_async`). Which thread runs what, and what each crossing costs, is told in [Sync and async in one chain](../handlers/async.md).

The test is made on the object in the URLconf, before it is called, and never on what it returns. It is true of a function written with `async def`, and of any callable that has been marked with `inspect.markcoroutinefunction`. For a view to be treated as asynchronous, then, the outermost callable, after every decorator and after `as_view`, has to pass the test. Of the Gazette's views the `async def` function passes, and a function that `as_view` returned passes when its class says it is asynchronous, through `View.view_is_async`:

```text recording=views
iscoroutinefunction(views.front)  ->  False
iscoroutinefunction(views.wire)  ->  True
views.Colophon.view_is_async  ->  False
views.Wire.view_is_async  ->  True
iscoroutinefunction(views.Wire.as_view())  ->  True
iscoroutinefunction(views.Colophon.as_view())  ->  False
...
```

## A class whose handler methods are coroutines

A class-based view is asynchronous when its handler methods are written with `async def`. The function that `as_view` returns is not written that way: it is one `def` for every class. So `as_view` asks the class, through `View.view_is_async`, and if the answer is yes it marks the function with `inspect.markcoroutinefunction` (`django/views/generic/base.py:View.as_view`).

`View.view_is_async` is a `classproperty`: it is worked out from the class, whether it is read on the class or on an instance. It gathers the handler methods the class has, going by the names in `View.http_method_names` and leaving out the name `"options"`, whose method `View` itself supplies. With none, as for `View` itself, the answer is no. Otherwise the answer is whether the first is a coroutine function, and all the others must agree with it. A class with both kinds, like Muddle, raises `ImproperlyConfigured` whether the property is read or `as_view` asks it, and since `as_view` asks as the URLconf is imported, that is when the error appears, naming the class (`django/views/generic/base.py:View.view_is_async`):

```text recording=views
...
views.Muddle.view_is_async  ->  raises ImproperlyConfigured: Muddle HTTP handlers must either be all sync or all async.
views.Muddle.as_view()  ->  raises ImproperlyConfigured: Muddle HTTP handlers must either be all sync or all async.
...
```

The function that `as_view` marked is still an ordinary function underneath, and it runs as one: it makes the instance, calls `View.setup`, and calls `View.dispatch`, which calls the class's `get`. Calling an `async def` method runs none of its body; it returns a coroutine. Through an `ASGIHandler`, that coroutine passes up, not yet started, from `dispatch` through the function to the handler, and only the handler's await runs the body of `get`:

```text recording=views
GET /wire/class/ through an ASGIHandler: a class whose get is async def, call by call
...
      view(request)  (the function as_view returned for Wire)  [loop]
        View.__init__()  (a new Wire)  [loop]
        View.setup(request)  [loop]
        View.dispatch(request)  [loop]  ->  a coroutine of Wire.get, not yet started
        -> a coroutine of Wire.get, not yet started
      Wire.get(request): the coroutine is awaited, and its body runs  [loop]  ->  an HttpResponse, status 200
      ...
```

Under an `ASGIHandler`, then, the work a class does before its handler method, in `View.__init__`, `View.setup` and `View.dispatch` and whatever a subclass adds to them, is done in plain calls on the event loop's thread, before the handler's await, except in a `dispatch` that a subclass overrides with `async def` (`django/views/generic/base.py:View.as_view`, `django/core/handlers/base.py:BaseHandler._get_response_async`).

`View.options` and `View.http_method_not_allowed` are ordinary methods on every class, and in an asynchronous class they would hand a response to a caller that is about to await what it gets. Each therefore asks `view_is_async` and, when it is true, returns its response from inside a small coroutine (`django/views/generic/base.py:View.options`, `django/views/generic/base.py:View.http_method_not_allowed`). Requested through a `WSGIHandler`, Wire answers an `"OPTIONS"` and a `"PUT"` with those two methods' coroutines, and the client gets a 200 listing the methods allowed, and a 405:

```text recording=views
Views that are coroutine functions, requested through a WSGIHandler
...
    OPTIONS /wire/class/
    start_response("200 OK", headers), with Allow: GET, HEAD, OPTIONS
    PUT /wire/class/
    log, WARNING to django.request: Method Not Allowed (PUT): /wire/class/
    start_response("405 Method Not Allowed", headers), with Allow: GET, HEAD, OPTIONS
    ...
```

The generic views are synchronous. None of the handler methods in `django/views/generic/` is written with `async def`, so under an asynchronous handler a generic view runs in a thread, like any other function.

## What a decorator has to keep

A decorator replaces the view with its wrapper, and the handler will put its question to the wrapper. A wrapper written with `def` around a view written with `async def` does not pass the test unless it has been marked.

So the decorators in `django/views/decorators/` ask `inspect.iscoroutinefunction` of the view they are given. A decorator that wraps has two wrappers to choose from, and the one for a coroutine function is itself written with `async def` and awaits the view (`django/views/decorators/http.py:require_http_methods`). The function behind the decorators made from middleware does the same, and from its coroutine wrapper calls the middleware's hooks directly, as plain function calls ([A middleware as a decorator](middleware-decorators.md#a-coroutine-view)) (`django/utils/decorators.py:make_middleware_decorator`). `sensitive_variables` is the exception: it returns a coroutine function unchanged, with no wrapper around it ([The debug pages and `ExceptionReporter`](debug.md#sensitive_variables-and-sensitive_post_parameters)). `method_decorator` does the equivalent for a method: when the method it replaces is a coroutine function, it marks the replacement (`django/utils/decorators.py:_multi_decorate`).

> **History.** Support for a coroutine function came in 5.0 to the decorators of `django/views/decorators/` that its release notes list as ones that "now support wrapping asynchronous view functions" (`docs/releases/5.0.txt`). `method_decorator` began to mark its replacement in 5.2 (`docs/releases/5.2.txt`).

Two decorators of the Gazette's own take no such care, each making a plain `def` wrapper that calls the view and returns what it gets. The wrapper bare makes copies nothing, and so loses every mark set under it ([What the handler asks of a view](callable.md#what-other-code-reads-from-a-view)); the one counted makes differs from it in one line, the use of `functools.wraps`:

```python
# gazette/views.py
def bare(view):
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)
    return wrapper


def counted(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)
    return wrapper


@counted
async def wire_counted(request):
    return HttpResponse("from the wire")
```

The decorators of `django/views/decorators/` keep a coroutine function one; `non_atomic_requests`, which lives with the transaction code, does not keep the `async def` function one (`django/db/transaction.py:_non_atomic_requests`); and the Gazette's two wrappers answer alike around the `async def` function, and differently around the function `as_view` returned for Wire:

```text recording=views
...
iscoroutinefunction(never_cache(views.wire))  ->  True
iscoroutinefunction(csrf_exempt(views.wire))  ->  True
iscoroutinefunction(require_POST(views.wire))  ->  True
iscoroutinefunction(non_atomic_requests(views.wire))  ->  False
iscoroutinefunction(method_decorator(never_cache)(views.Wire.get))  ->  True
iscoroutinefunction(views.counted(views.wire))  ->  False
iscoroutinefunction(views.wire_counted)  ->  False
iscoroutinefunction(views.bare(views.wire))  ->  False
iscoroutinefunction(views.counted(views.Wire.as_view()))  ->  True
iscoroutinefunction(views.bare(views.Wire.as_view()))  ->  False
```

That a function was written with `async def` is a flag of its compiled code, and `functools.wraps` does not copy it, so neither of the Gazette's wrappers around the `async def` function passes the test. The function `as_view` returned for Wire is an ordinary function that `inspect.markcoroutinefunction` marked by setting an attribute on it, and `functools.wraps` copies attributes. The wrapper counted makes around that function is then treated as asynchronous: it returns the coroutine it was handed without touching it, and its caller awaits that.

> **Trap.** A decorator given to `dispatch` through `method_decorator`, on a class whose handler methods are coroutines, chooses its wrapper for an ordinary function. `View.dispatch` is written with `def`, so at each request the decorator is handed a partial around the bound `dispatch`, which is not a coroutine function, and its `def` wrapper gets back the coroutine `get` made where it expected a response (`django/utils/decorators.py:_multi_decorate`). One that works on the response fails on it: `never_cache` given so ends every request in an `AttributeError` and a 500, under either handler. The documentation's remedy is an `async def` override of `dispatch` for `method_decorator` to decorate, and the override has to await `super().dispatch()`: returned unawaited, as in the documentation's example, the coroutine `get` made reaches the decorator again (`docs/topics/async.txt`).

## When the test is fooled

Two of the Gazette's addresses serve an asynchronous view from inside counted: the function `as_view` returned for Wire, and the `async def` function. For the second, a synchronous handler asks its question of the wrapper, is told it has an ordinary function, and calls it, and what comes back is the coroutine the view made. The first is served; the second ends in a `ValueError` from `BaseHandler.check_response` and a 500, though the same handler serves the Gazette's unwrapped `async def` function without complaint:

```text recording=views
Views that are coroutine functions, requested through a WSGIHandler
...
    GET /wire/class/counted/, the function as_view returned for that class, inside a wrapper that is an ordinary function
    start_response("200 OK", headers)
    the server sends the body: 'from the wire'
    GET /wire/counted/, an async def function inside the same kind of wrapper
    signal got_request_exception, for ValueError: The view gazette.views.wire_counted didn't return an HttpResponse object. It returned an unawaited coroutine instead. You may need to add an 'await' into your view.
    log, ERROR to django.request: Internal Server Error: /wire/counted/
    start_response("500 Internal Server Error", headers)
```

> **Trap.** The `ValueError` blames the view. Its hint, "You may need to add an 'await' into your view", is aimed at a view that forgot to await something; here the view is correct and the wrapper around it is at fault. `check_response` is the method that refuses a view's `None` ([What the handler asks of a view](callable.md#what-a-view-may-return)), and the asynchronous handler makes the same check and raises the same error (`django/core/handlers/base.py:BaseHandler.check_response`).

## Around a coroutine view

A view being a coroutine does not make what it calls asynchronous. `render` and `redirect` are ordinary functions that a coroutine may call. `get_object_or_404` and `get_list_or_404` run a query, and have twins for a coroutine to await, `aget_object_or_404` and `aget_list_or_404` ([The shortcuts](shortcuts.md)).

With `"ATOMIC_REQUESTS"` on for a database that the view's `"_non_atomic_requests"` does not name, `BaseHandler.make_view_atomic` wraps an ordinary view in a transaction for that database, and for a coroutine function raises `RuntimeError` in its place, which the client receives as a 500 under either handler ([The centre of the chain](../handlers/view.md#calling-the-view)) (`django/core/handlers/base.py:BaseHandler.make_view_atomic`).

> **Trap.** `non_atomic_requests`, the decorator that takes a view out of `"ATOMIC_REQUESTS"`, hides a coroutine function written with `async def`. Its wrapper is a plain function, so the handler calls it as one and gets back the view's coroutine, not yet started, which `BaseHandler.check_response` refuses with the `ValueError` of [When the test is fooled](#when-the-test-is-fooled): the client gets a 500 under either handler, and Python warns that the coroutine was never awaited (`django/db/transaction.py:_non_atomic_requests`). The wrapper is at fault, not the setting: with `"ATOMIC_REQUESTS"` off the decorated view fails the same way. In 5.2, 6.0 and 6.1 the decorator set its mark on the view itself and returned it, still a coroutine function; at this commit it returns a new function, so that a second use leaves the first one's set as it was (`tests/handlers/tests.py:TransactionsPerRequestTests.test_non_atomic_requests_does_not_mutate_original`).
