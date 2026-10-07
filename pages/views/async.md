---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Asynchronous views

A view may be a coroutine function. The handler finds out by asking `iscoroutinefunction` of whatever the URLconf holds, and this section is about keeping the answer true: how `View.as_view` marks the function it returns, what `View.view_is_async` requires of a class, how the decorators of `django/views/decorators/` keep a coroutine function one, and what happens when a wrapper does not.

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

## One test, made on the callable

`BaseHandler._get_response` and its asynchronous twin both put one question to the view: `iscoroutinefunction`. The synchronous handler wraps a coroutine function in `async_to_sync` and then calls it as a function. The asynchronous handler wraps anything that is not a coroutine function in `sync_to_async`, so that it runs in a thread, and awaits the result either way (`django/core/handlers/base.py:BaseHandler._get_response`, `django/core/handlers/base.py:BaseHandler._get_response_async`). Which thread runs what, and what each crossing costs, is told in [Sync and async in one chain](../handlers/async.md).

The test is made on the object in the URLconf, before it is called, and never on what it returns. It is true of a function written with `async def`, and of any callable that has been marked with `inspect.markcoroutinefunction`. Everything below follows from that: for a view to be treated as asynchronous, the outermost callable, after every decorator and after `as_view`, has to pass the test.

```text recording=views
iscoroutinefunction(views.front)  ->  False
iscoroutinefunction(views.wire)  ->  True
views.Colophon.view_is_async  ->  False
views.Wire.view_is_async  ->  True
iscoroutinefunction(views.Wire.as_view())  ->  True
iscoroutinefunction(views.Colophon.as_view())  ->  False
```

## A class whose handler methods are coroutines

A class-based view is asynchronous when its handler methods are written with `async def`. The function that `as_view` returns is not written that way: it is one `def` for every class. So `as_view` asks the class, through `View.view_is_async`, and if the answer is yes it marks the function with `markcoroutinefunction` (`django/views/generic/base.py:View.as_view`).

`View.view_is_async` is a `classproperty`: it is worked out from the class, whether it is read on the class or on an instance. It gathers the handler methods the class has, going by the names in `http_method_names` and leaving out `options`, which `View` itself supplies. With none, the answer is no. Otherwise the answer is whether the first is a coroutine function, and all the others must agree with it. A class that has one of each raises `ImproperlyConfigured`, and since `as_view` asks as the URLconf is imported, that is when the error appears (`django/views/generic/base.py:View.view_is_async`).

```text recording=views
View.view_is_async  ->  False
views.Muddle.view_is_async  ->  raises ImproperlyConfigured: Muddle HTTP handlers must either be all sync or all async.
views.Muddle.as_view()  ->  raises ImproperlyConfigured: Muddle HTTP handlers must either be all sync or all async.
```

The function that `as_view` marked is still an ordinary function underneath, and it runs as one. When Django calls it, it makes the instance, calls `setup` and calls `dispatch`, all at once and without any awaiting. `dispatch` calls the class's `get`, and calling an `async def` method runs none of its body: it returns a coroutine. That coroutine is passed back up through `dispatch` and out of the function, to a caller that was told to expect one and awaits it. Only then does the code in `get` run.

`View.options` and `View.http_method_not_allowed` are ordinary methods on every class, and in an asynchronous class they would hand a response to a caller that is about to await what it gets. Each therefore asks `view_is_async` and, when it is true, returns its response from inside a small coroutine (`django/views/generic/base.py:View.options`).

All four of these were requested through a synchronous handler:

```text recording=views
GET /wire/, an async def function
start_response("200 OK", headers)
the server sends the body: 'from the wire'
GET /wire/class/, a class whose get is async def
start_response("200 OK", headers)
the server sends the body: 'from the wire'
OPTIONS /wire/class/
start_response("200 OK", headers), with Allow: GET, HEAD, OPTIONS
PUT /wire/class/
log, WARNING to django.request: Method Not Allowed (PUT): /wire/class/
start_response("405 Method Not Allowed", headers), with Allow: GET, HEAD, OPTIONS
```

The generic views are synchronous. None of the handler methods in `django/views/generic/` is written with `async def`, so under an asynchronous handler a generic view runs in a thread, like any other function.

## What a decorator has to keep

A decorator replaces the view with its wrapper, and the handler will put its question to the wrapper. A wrapper written with `def` around a view written with `async def` does not pass the test, whatever it wraps.

So the decorators in `django/views/decorators/` ask `iscoroutinefunction` of the view they are given. A decorator that wraps has two wrappers to choose from, and the one for a coroutine function is itself written with `async def` and awaits the view (`django/views/decorators/http.py:require_http_methods`). The function behind the decorators made from middleware does the same (`django/utils/decorators.py:make_middleware_decorator`). `sensitive_variables` is the exception: it returns a coroutine function unchanged, with no wrapper around it ([The debug pages and `ExceptionReporter`](debug.md#sensitive_variables-and-sensitive_post_parameters)). `method_decorator` does the equivalent for a method: when the method it replaces is a coroutine function, it marks the replacement (`django/utils/decorators.py:_multi_decorate`).

The Gazette has two decorators of its own that take no such care. Each makes a plain `def` wrapper that calls the view and returns what it gets. They differ in one line, the use of `functools.wraps`:

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

```text recording=views
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

The decorators of `django/views/decorators/` asked here keep the wire view a coroutine function, and so does `method_decorator` for the class's `get`. `non_atomic_requests`, which lives with the transaction code, does not: the wrapper it makes is a plain function (`django/db/transaction.py:non_atomic_requests`). Around the same view, neither of the Gazette's does, with `functools.wraps` or without: being a coroutine function is a property of the function's compiled code, and `functools.wraps` does not copy that. Around the function `as_view` returned for the asynchronous class, the one that uses `functools.wraps` does pass. There the property is a mark that `markcoroutinefunction` set as an attribute, and `functools.wraps` copies attributes. The wrapper is then treated as asynchronous, returns the coroutine it was handed without touching it, and its caller awaits that.

## When the test is fooled

Two of the Gazette's addresses serve an asynchronous view from inside counted: the class's function, and the function written with `async def`. For the second, a synchronous handler asks its question of the wrapper, is told it has an ordinary function, and calls it. What comes back is the coroutine the view made.

```text recording=views
GET /wire/class/counted/, the function as_view returned for that class, inside a wrapper that is an ordinary function
start_response("200 OK", headers)
the server sends the body: 'from the wire'
GET /wire/counted/, an async def function inside the same kind of wrapper
signal got_request_exception, for ValueError: The view gazette.views.wire_counted didn't return an HttpResponse object. It returned an unawaited coroutine instead. You may need to add an 'await' into your view.
log, ERROR to django.request: Internal Server Error: /wire/counted/
start_response("500 Internal Server Error", headers)
```

The message is `BaseHandler.check_response` again, the same method that refuses `None`, and its hint is aimed at a different mistake, a view that forgot to await something. Here the view is correct and the decorator is at fault. The asynchronous handler makes the same check and raises the same error (`django/core/handlers/base.py:BaseHandler.check_response`).

The same view without the wrapper is the first request of the recording further up, and it was served by the same synchronous handler without complaint.

## Around a coroutine view

A view being a coroutine does not make what it calls asynchronous. `render` and `redirect` are ordinary functions that a coroutine may call. `get_object_or_404` and `get_list_or_404` run a query, and have twins for a coroutine to await, `aget_object_or_404` and `aget_list_or_404` ([The shortcuts](shortcuts.md)).

A view that is a coroutine function cannot be wrapped in a transaction: with `"ATOMIC_REQUESTS"` on for a database that the view's `"_non_atomic_requests"` does not name, `BaseHandler.make_view_atomic` raises `RuntimeError` for it (`django/core/handlers/base.py:BaseHandler.make_view_atomic`). The decorator that sets that mark is the one whose wrapper, in the recording above, is not a coroutine function.

And a decorator made from a middleware calls the middleware's hooks directly from its coroutine wrapper, as plain function calls ([A middleware as a decorator](middleware-decorators.md#a-coroutine-view)).
