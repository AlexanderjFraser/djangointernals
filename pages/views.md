---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: "The view and what wraps it: callable, as-view, decorators, method-decorator, middleware-decorators, async, shortcuts; The generic views: generic, display, editing, dates, date-views; What Django answers itself: errors, debug, report-filter, static-files"
---

# Views

A view is the callable the URL resolver found for a request's path: the handler calls it with the request and the arguments the resolver found for it, and it returns a response or raises an exception. `View.as_view` makes a class into a view and decorators such as `never_cache` wrap one; the generic views are view classes of Django's own, and the error views and debug pages are Django's answers to an exception raised inside the middleware chain.

Until a view is called, the request cycle is Django's machinery. A server calls the handler, the handler sends the request down a chain of middleware, and at the centre of the chain the resolver matches the request's path against the URLconf. What the resolver finds is the code a project chose to answer that address. Django has no base class that this code must extend and no registry it must be entered in. It asks for a callable, and it makes one call.

Because the requirement is so small, what Django offers beyond it is help in meeting it, and the help comes in layers around that call, which the figure draws for one request from the handler inwards. The innermost is a **handler method**: the method of a view class named for the request's HTTP method, `get` for a `"GET"`. It has nothing to do with the handler, the object the server calls. In a generic view such as `DetailView` the handler method is itself a series of small methods that a project can replace one at a time.

```text figure=the-layers
A view's usual layers between the handler's call and its own code, outermost first:

BaseHandler._get_response        resolves the path, then calls what the URLconf holds
  the decorators' wrappers       on the view, made at import; the one written first is outermost
    the view                     a function or other callable, or the function as_view returned
      an instance of the class        made by that function, for this request alone
        View.setup                    keeps the request and the view's arguments on the instance
        View.dispatch                 picks the method named for the request's method
          get, post, ...              the project's code, or a generic view's
            get_object                in a generic view, small methods that a subclass
            get_context_data          can replace one at a time: these three are
            render_to_response        what DetailView's get calls

The response travels back out through the same layers.
A function view has only the first three.
```

*A view's usual layers between the handler and its own code, outermost first; the handler may put its own around them, a transaction or a crossing between a thread and the event loop. A function view is called directly, inside whatever wrappers its decorators made. A class-based view adds the instance that the function `as_view` returned makes for each request, with `setup`, `dispatch` and a handler method inside it; in a generic view that handler method is made of smaller methods, the innermost layer.*

The chapter follows the figure in three runs. The first is the view and what wraps it: what the handler asks of the callable, how `as_view` makes one from a class, the decorators, how one is put on a method of a class, the decorators made from a middleware class, how a view that is a coroutine function stays one, and the shortcuts. The second opens the innermost layer: how the generic views are assembled, `DetailView` and `ListView`, the form views and the date views. The third leaves the layers for what Django answers with on its own account: the error views and the debug pages, which the handler calls for an exception, and the view that serves files during development.

## What the handler calls

At the centre of the middleware chain, `BaseHandler._get_response` resolves the request's path and gets three things back: a callable, a tuple of positional arguments and a dictionary of keyword arguments. Unless a middleware's `process_view` hook answers first, it ordinarily calls the first with the request and the other two. Under ASGI the method's asynchronous twin makes the same call (`django/core/handlers/base.py:BaseHandler._get_response`).

The examples are the views of a town's newspaper, the Gazette, a small project that the chapter's recordings run. Four of its views stand for four kinds:

```python
# gazette/views.py
def front(request):
    return HttpResponse("the front page")


@require_GET
@never_cache
@vary_on_cookie
def masthead(request):
    return HttpResponse("The Gazette")


class Colophon(View):
    """Who prints the paper, and in what type."""

    type_size = 9

    def get(self, request):
        return HttpResponse(f"set in {self.type_size} point")


class ArticleDetail(DetailView):
    model = Article


# gazette/urls.py
urlpatterns = [
    path("", views.front, name="front"),
    path("masthead/", views.masthead, name="masthead"),
    path("colophon/", views.Colophon.as_view(), name="colophon"),
    path("articles/<slug:slug>/", views.ArticleDetail.as_view(), name="article"),
]
```

The callable is whatever the URLconf holds ([From a URLconf to a tree](urls/urlconf.md)). For these four patterns the resolver hands back four functions, though only two were written as functions; the other two are what `as_view` returned when the URLconf was imported. Asked about one of each kind, the resolver gives the Gazette's own function for the front page, and for the colophon a function named `"view"` that remembers which class it was made from:

```text recording=views
resolve("/").func is views.front  ->  True
resolve("/").func.__name__  ->  'front'
...
resolve("/colophon/").func.__name__  ->  'view'
resolve("/colophon/").func.__qualname__  ->  'View.as_view.<locals>.view'
resolve("/colophon/").func.view_class  ->  <class 'gazette.views.Colophon'>
...
```

A view answers in one of two ways. It returns a response, which the handler passes back out through the chain. Or it raises an exception, which ordinarily the handler offers to the middleware's `process_exception` hooks and, if none of them answers, turns into a response chosen by the exception's class: with Django's own error views, a 404 for `Http404`, a 403 for `PermissionDenied`, a 400 for a `BadRequest`, a `SuspiciousOperation` or a `MultiPartParserError`, a 500 for anything it does not recognise ([How an exception becomes a response](handlers/exceptions.md)). Of what comes back the handler checks little: `BaseHandler.check_response` refuses `None` and a coroutine nobody awaited, and tests nothing else ([What the handler asks of a view](views/callable.md)) (`django/core/handlers/base.py:BaseHandler.check_response`).

The shortcuts make answers in a line. `render` renders a template into a finished response, `redirect` makes a redirect to a URL, to a pattern's name reversed or to an object's own URL, and `get_object_or_404` fetches one object, raising `Http404` when there is none ([The shortcuts](views/shortcuts.md)) (`django/shortcuts.py`).

The callable may be a coroutine function: one written with `async def`, or a function marked as one, as `as_view` marks what it returns for a class whose handler methods are coroutines. The handler asks which kind it has before it calls, and adapts the call to suit. A plain wrapper around a function written with `async def` hides what it holds, and if it hands back what the function returns, the call returns a coroutine that nobody awaits, which `check_response` refuses ([Asynchronous views](views/async.md)).

## `View.as_view`: a class made into a function

A view class is not itself a view. Called as the handler calls a view, with a request, it would only try to construct an instance of itself. `View.as_view` bridges the two. Written in a URLconf, it is called on the class as the URLconf is imported, once for each pattern that names it, and returns a plain function, which the URLconf holds in the class's place, alone or inside a decorator's wrapper. Each time that function is called it makes a new instance of the class, stores the request and its arguments on it in `View.setup`, and calls the instance's `dispatch` (`django/views/generic/base.py:View.as_view`).

`View.dispatch` takes the request's method, lower-cases it, and calls the handler method of that name on the instance. A request whose method is not in `View.http_method_names`, or for which the instance has no attribute of that name, is answered with a 405 listing the methods it does answer (`django/views/generic/base.py:View.dispatch`, `django/views/generic/base.py:View.http_method_not_allowed`).

Each request is served by an instance of its own, so nothing a handler method stores on `self` reaches the next request, and two requests served at once do not see each other's attributes. What they do share is the class's attributes and the arguments given to `as_view`, the same objects for every request ([`View.as_view` and dispatch](views/as-view.md)).

## Decorators: functions around a view

A decorator is the plainest way to add to a view. Given a view, it returns what goes into the URLconf in the view's place. For each of the three on the Gazette's masthead that is a **wrapper**: a new function that calls the view and does something before or after. The decorator written first, at the top, makes the outermost wrapper, so it is the first to see the request and the last to see the response: the middleware chain's order again, around one view and not around every view. A wrapper that answers without calling inwards leaves everything inside it unrun, though the wrappers outside it still see its response. `require_GET`, outermost on the masthead, answers a `"POST"` with a 405, and neither the other two wrappers nor the view runs ([View decorators](views/decorators.md)) (`django/views/decorators/http.py:require_http_methods`).

Some decorators change nothing about the call. `csrf_exempt` returns a wrapper that only calls the view, with an attribute set on it: a **mark**, which `CsrfViewMiddleware` reads when the handler shows it the view (`django/views/decorators/csrf.py:csrf_exempt`). Others are a middleware class applied to one view: `csrf_protect` and `cache_page` each make an instance of their middleware, `CsrfViewMiddleware` or `CacheMiddleware`, for the view they decorate, and a wrapper that calls its hooks around the view ([A middleware as a decorator](views/middleware-decorators.md)) (`django/utils/decorators.py:make_middleware_decorator`).

A class is decorated through `method_decorator`, which turns a decorator of functions into one for a method, most often `dispatch`. It applies the decorator anew at every call, so a decorator made from a middleware class makes a middleware for every request ([Decorating a class: `method_decorator`](views/method-decorator.md)) (`django/utils/decorators.py:method_decorator`, `django/utils/decorators.py:_multi_decorate`).

## The generic views: a handler method in pieces

The last of the four views has no code of its own. *ArticleDetail* names a model and inherits everything else from `DetailView`, whose `get` is a handler method with its decisions taken out and made methods of their own: `get_object` finds the article from the slug the path captured, `get_context_data` builds the template's context, and `render_to_response` makes the response, with a template name made from the app's label and the model's name when the class names none ([`DetailView` and `ListView`](views/display.md)) (`django/views/generic/detail.py:BaseDetailView.get`).

None of those methods is declared by `DetailView`. Each belongs to a small class called a **mixin**, `get_object` and `get_context_data` to `SingleObjectMixin` and `render_to_response` to `TemplateResponseMixin`, and `DetailView` is little more than the list of classes it inherits from: Python's method resolution order decides whose method runs. A project changes one decision by overriding one method, or by setting the attribute that method reads, and inherits the rest ([The generic views](views/generic.md)). The views that show a form and act on what is posted ([The form views](views/editing.md)) and the ones that archive objects by year, month, week and day ([The date views: a date, an interval and its neighbours](views/dates.md); [The seven date views](views/date-views.md)) are assembled from mixins too.

What `render_to_response` returns is by default a `TemplateResponse` not yet rendered: it holds a list of template names and the context, and the handler renders it at the centre of the chain, after any `process_template_response` hooks have had the chance to change either ([The centre of the chain](handlers/view.md#template-responses)). The shortcut `render` is another way to use a template in a view: it renders at once and returns a finished `HttpResponse`.

## The error views and the debug pages

Here the layers end, for the views that answer an exception are found by no pattern: the handler calls them itself. A view that cannot find what was asked for raises `Http404`, as `get_object` does for an article that does not exist, and the handler turns the exception into a response. For each of the four statuses it may choose, 404, 500, 400 and 403, it has an **error view**: the one the root URLconf names (`handler404` and its three kin), or else Django's default from `django/views/defaults.py`, called with the request and, for every status but 500, the exception ([The error views](views/errors.md)). With `settings.DEBUG` on, a **debug page** ordinarily answers in place of the 404 and 500 views, and of the 400 view but for a `MultiPartParserError` ([The debug pages and `ExceptionReporter`](views/debug.md)) (`django/core/handlers/exception.py:response_for_exception`, `django/core/handlers/exception.py:handle_uncaught_exception`).

The debug page for an `Http404` ordinarily shows the patterns the resolver tried (`django/views/debug.py:technical_404_response`). The one for any other exception is the work of an `ExceptionReporter`, which walks the traceback, collects each frame's source lines and local variables, and renders them with the request and the settings. A filter, by default `SafeExceptionReporterFilter`, replaces with stars the settings, `META` entries and cookies whose names look like a secret's, and, with `settings.DEBUG` off, whatever `sensitive_variables` and `sensitive_post_parameters` have marked. A reporter also writes the report, as text, that `AdminEmailHandler` mails to a site's administrators ([What an error report hides](views/report-filter.md)) (`django/views/debug.py:ExceptionReporter`, `django/utils/log.py:AdminEmailHandler.emit`).

The last view of the chapter serves files. `django.views.static.serve` answers a request with a file from a directory; `django.conf.urls.static.static` routes a prefix to it only if `settings.DEBUG` is on when the URLconf is imported, and the static files app's own view calls it ([The static file view](views/static-files.md)) (`django/views/static.py:serve`).

## The neighbours

The handler decides when a view is called and what becomes of what it returns or raises: the `process_view` hooks before it, the transaction around it, the rendering of a template response after it ([Handlers and middleware](handlers.md)). The resolver supplies the view and its arguments, and `redirect` and `resolve_url` call `reverse` on a view's behalf ([URL routing](urls.md)). The request a view reads and the response classes it returns are the subject of [Requests and responses](http.md).

The generic views use the queryset they are given, or ask a model's manager for one ([QuerySets](querysets.md)), build and validate a form ([Forms](forms.md)), and name a template for a `TemplateResponse` to render ([Templates](templates.md)). What the decorators made from middleware do belongs to their middleware's chapters, CSRF to [Security](security.md) and the page cache and conditional requests to [Caching, files, mail, signals and tasks](services.md); the decorators and mixins that require a login are in [Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](auth/requiring-login.md).
