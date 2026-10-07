---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: callable, as-view, decorators, middleware-decorators, async, shortcuts, generic, editing, dates, errors, debug, static-files
---

# Views

A view is the callable the URL resolver found for a request's path: the handler calls it with the request and the arguments the path gave, and it returns a response. Everything else that goes by the name is built around that one call: `View.as_view` turns a class into such a callable, a decorator puts another function around one, and the generic views and the error views are views that Django wrote itself.

Up to this point the request cycle is Django's machinery. A server calls the handler, the handler sends the request down a chain of middleware, and at the centre of the chain the resolver matches the request's path against the URLconf. What the resolver finds is the code a project wrote to answer that address. Django has no base class that this code must extend and no registry it must be entered in. It asks for a callable, and it makes one call.

Because the requirement is so small, what Django offers beyond it is optional help in meeting it. This chapter takes the help in layers, from the call outwards: what the handler asks of a view; how a class is made to answer that call; the decorators, which wrap a view in another function or leave a mark on it for some other part of Django to read; the shortcuts, which make the commonest responses in one line; and the generic views, which are whole views with the parts that differ between projects left as methods to replace. The last sections are about what Django answers with on its own account: the error views that are called when a view raises or no pattern matches, the debug pages, and the view that serves files during development.

The examples are the views of a town's newspaper, the Gazette. Everything recorded in this chapter was recorded from a running Django with these among its views.

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

## What the handler calls

At the centre of the middleware chain, `BaseHandler._get_response` resolves the request's path and gets three things back: a callable, a tuple of positional arguments and a dictionary of keyword arguments. It calls the first with the request and the other two. That call is the whole of the interface, and under ASGI the method's asynchronous twin makes the same one (`django/core/handlers/base.py:BaseHandler._get_response`).

The callable is whatever the URLconf was given. `path` accepts anything Python can call, and stores it without looking further ([From a URLconf to a tree](urls/urlconf.md)). For the four patterns above the resolver hands back four functions, though only two were written as functions. The other two are what `as_view` returned when the URLconf was imported. Asked about one of each kind, the resolver gives the Gazette's own function for the front page, and for the colophon a function named `"view"` that remembers which class it was made from:

```text recording=views
resolve("/").func is views.front  ->  True
resolve("/").func.__name__  ->  'front'
...
resolve("/colophon/").func.__name__  ->  'view'
resolve("/colophon/").func.__qualname__  ->  'View.as_view.<locals>.view'
resolve("/colophon/").func.view_class  ->  <class 'gazette.views.Colophon'>
```

A view may answer in two ways. It returns a response, which the handler passes back up the chain. Or it raises an exception, which the handler offers to the middleware and then turns into a response of its own choosing: a 404 for `Http404`, a 403 for `PermissionDenied`, a 500 for anything it does not recognise ([How an exception becomes a response](handlers/exceptions.md)). The handler checks little of what comes back. After the call it refuses `None` and a coroutine nobody awaited, and nothing else: there is no test that the object returned is an `HttpResponse` (`django/core/handlers/base.py:BaseHandler.check_response`).

The callable may be a coroutine function: one written with `async def`, or a function marked as one, as `as_view` marks what it returns for a class whose handler methods are coroutines. The handler asks which kind it has before it calls, and adapts the call to suit ([Asynchronous views](views/async.md)).

[What the handler asks of a view](views/callable.md) has the rest of the contract: the attributes that other parts of Django read off the callable, and how a view is named in an error message and in a `ResolverMatch`.

## Functions around a function

A decorator is the plainest way to add to a view. Given a view, it returns what will go into the URLconf in the view's place. For each of the three on the Gazette's masthead that is a **wrapper**: a new function that calls the view and does something before or after. Two of the three are a more general decorator with its argument already supplied, and the recording names the wrappers by the general one: `require_GET` is `require_http_methods` with a list of one method, and `vary_on_cookie` is `vary_on_headers` with one header's name. A request enters the wrappers from the outside in:

```text recording=views
GET /masthead/: three decorators around one function
    BaseHandler._get_response
      the wrapper require_http_methods made, for ['GET']
        the wrapper never_cache made
          the wrapper vary_on_headers made, for ('Cookie',)
            views.masthead(request)  ->  an HttpResponse, status 200
            patch_vary_headers(response, ('Cookie',))
            -> an HttpResponse, status 200
          add_never_cache_headers(response)
          -> an HttpResponse, status 200
        -> an HttpResponse, status 200
    start_response("200 OK", headers), with Vary: Cookie, Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private
    the server sends the body: 'The Gazette'
```

The outermost wrapper, the one `require_GET` made, looks at the request's method before it calls anything. The other two change the response once the view has answered: `vary_on_cookie` adds to its `"Vary"` header, and `never_cache` adds the headers that tell a cache to keep nothing. So the decorator written first, at the top, is the first to see the request and the last to see the response. It is the middleware chain's order again, for the same reason, around one view and not around every view.

A wrapper that answers by itself ends the request there. A `"POST"` to the same address is answered with a 405 by the outermost wrapper, and neither of the others runs, nor the view.

Some decorators make no difference to the call at all. `csrf_exempt` returns a wrapper that only calls the view, with an attribute set on it, and `CsrfViewMiddleware` looks for that attribute when the handler shows it the view ([View decorators](views/decorators.md)). And several of Django's decorators are a middleware class in disguise: one instance of the class is made for the view, and a wrapper calls the instance's hooks around the view. `csrf_protect` and `cache_page` are built so ([A middleware as a decorator](views/middleware-decorators.md)).

## A class, made into a function

A view class is not itself a view. Called as the handler calls a view, with a request, it would only try to construct an instance of itself. `View.as_view` bridges the two. It is called once, on the class, as the URLconf is imported, and returns a plain function. That function is the view as far as the handler is concerned. Each time it is called it makes a new instance of the class, stores the request and the arguments on it, and calls the instance's `dispatch` (`django/views/generic/base.py:View.as_view`).

```text recording=views
GET /colophon/, twice: a class-based view is a function that makes an instance for each request
    BaseHandler._get_response
      view(request)  (the function as_view returned for Colophon)
        View.__init__()  (a new Colophon)
        View.setup(request)
        View.dispatch(request)
          Colophon.get(request)  ->  an HttpResponse, status 200
          -> an HttpResponse, status 200
        -> an HttpResponse, status 200
    start_response("200 OK", headers)
    the server sends the body: 'set in 9 point'
    and the same request again
    BaseHandler._get_response
      view(request)  (the function as_view returned for Colophon)
        View.__init__()  (a new Colophon)
        View.setup(request)
        View.dispatch(request)
          Colophon.get(request)  ->  an HttpResponse, status 200
          -> an HttpResponse, status 200
        -> an HttpResponse, status 200
    start_response("200 OK", headers)
    the server sends the body: 'set in 9 point'
```

`View.dispatch` takes the request's method, lower-cases it, and calls the method of that name on the instance: `get` for a `"GET"`. This chapter calls such a method a **handler method**. It has nothing to do with the handler, the object the server calls. A class with no method for the request's method answers with a 405 that lists the ones it has (`django/views/generic/base.py:View.dispatch`, `django/views/generic/base.py:View.http_method_not_allowed`).

The two requests were served by two instances. Nothing a handler method stores on `self` reaches the next request, and two requests served at the same moment by two threads cannot see each other's attributes. That is what the indirection gives: each request has an object of its own, so a view can keep one request's working state on the instance ([`View.as_view` and dispatch](views/as-view.md)).

```text figure=the-layers
What runs between the handler's call and the project's own code, outermost first:

BaseHandler._get_response      resolves the path, then calls what the URLconf holds
  the decorators' wrappers     made at import; the one written first is outermost
    the view                   a function of the project's, or the function as_view returned
      an instance of the class      made by that function, for this request alone
        View.setup                  keeps the request and the path's arguments on the instance
        View.dispatch               picks the method named for the request's method
          get, post, ...            the project's code, or a generic view's

The response travels back out through the same layers.
A function view has only the first three.
```

*The layers between the handler and a view's own code. A function view is called directly, inside whatever wrappers its decorators made. A class-based view adds three more steps inside the function that `as_view` returned: an instance for the request, `setup`, and `dispatch`.*

## A generic view is a handler method in pieces

The last of the four views has no code of its own. ArticleDetail names a model and inherits everything else from `DetailView`, which is a `get` method with its decisions taken out and made methods of their own: which object, which queryset to look for it in, what to put in the template's context, which template. This is the request for one article:

```text recording=views
GET /articles/ferry-timetable/: a DetailView
    BaseHandler._get_response
      view(request, slug='ferry-timetable')  (the function as_view returned for ArticleDetail)
        View.__init__()  (a new ArticleDetail)
        View.setup(request, slug='ferry-timetable')
        View.dispatch(request, slug='ferry-timetable')
          BaseDetailView.get(request, slug='ferry-timetable')
            SingleObjectMixin.get_object()
              SingleObjectMixin.get_queryset  ->  a QuerySet of Article, not yet fetched
              SingleObjectMixin.get_slug_field  ->  'slug'
              SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE "gazette_article"."slug" = %s LIMIT 21 with params ('ferry-timetable',)
              -> <Article: New ferry timetable>
            SingleObjectMixin.get_context_data(object=...)
              SingleObjectMixin.get_context_object_name(obj)  ->  'article'
              ContextMixin.get_context_data(object=..., article=...)  ->  a dict with the keys article, object, view
              -> a dict with the keys article, object, view
            TemplateResponseMixin.render_to_response(context)
              SingleObjectTemplateResponseMixin.get_template_names
                TemplateResponseMixin.get_template_names  raises ImproperlyConfigured
                -> ['gazette/article_detail.html']
              -> a TemplateResponse, status 200, not rendered
            -> a TemplateResponse, status 200, not rendered
          -> a TemplateResponse, status 200, not rendered
        -> a TemplateResponse, status 200, not rendered
      SimpleTemplateResponse.render
    start_response("200 OK", headers)
    the server sends the body: 'New ferry timetable, 3 March 2026\n'
```

The outline is the one above: the function, the instance, `setup`, `dispatch`, a handler method. Inside the handler method, `get_object` finds the article from the slug the path captured, `get_context_data` builds the context, and `render_to_response` makes a `TemplateResponse`, with a template name that `get_template_names` builds from the app's label and the model's name. The exception in the trace is part of the ordinary course: it is how that method learns that the class named no template.

None of those methods is declared by `DetailView`. They belong to small classes called **mixins**, `get_object` and `get_context_data` to `SingleObjectMixin` and `render_to_response` to `TemplateResponseMixin`, and `DetailView` is little more than the list of classes it inherits from. A project changes one decision by overriding one method ([The generic views](views/generic.md)).

The view returns before any template has been rendered. A `TemplateResponse` holds the template's name and the context, and the handler renders it afterwards, once the middleware have had the chance to change either: the last line under `BaseHandler._get_response` is that rendering ([The centre of the chain](handlers/view.md#template-responses)). The shortcut `render` is another way to use a template in a view. It renders at once and returns a finished `HttpResponse` ([The shortcuts](views/shortcuts.md)).

The same construction gives the views that show a form and act on what is posted ([The form views](views/editing.md)) and the ones that list objects by year, month, week and day ([The date views](views/dates.md)).

## When a view cannot answer

A view that cannot find what was asked for raises `Http404`, and the generic views do so themselves: the request for an article that does not exist ends in `get_object` with that exception. On a site with `settings.DEBUG` off, what the client then receives is made by another view. The handler looks up an **error view** for the status, by default one of the four in `django/views/defaults.py`, and calls it with the request and, for every status but 500, the exception ([The error views](views/errors.md)).

With `settings.DEBUG` on, the answer to a 404 or to an unrecognised exception is a debug page instead. The page for an exception is the work of an `ExceptionReporter`, which walks the traceback, collects each frame's source lines and local variables, and renders them with the request and the settings. A filter stands between the reporter and the settings, headers and cookies whose names look like a secret's. The same reporter writes the report that is mailed to a site's administrators when `settings.DEBUG` is off ([The debug pages and `ExceptionReporter`](views/debug.md)).

## The neighbours

The handler decides when a view is called and what becomes of what it returns or raises: the `process_view` hooks before it, the transaction around it, the rendering of a template response after it ([Handlers and middleware](handlers.md)). The resolver supplies the view and its arguments, and the shortcuts `redirect` and `resolve_url` call `reverse` on a view's behalf ([URL routing](urls.md)). The request a view reads and the response classes it returns are the subject of [Requests and responses](http.md).

The generic views lean on three other systems and own none of them: they ask a model's manager for a queryset ([QuerySets](querysets.md)), build and validate a form ([Forms](forms.md)), and name a template for a `TemplateResponse` to render ([Templates](templates.md)).

The decorators made from middleware belong, for what they do, to the chapters of those middleware: CSRF to [Security](security.md), the page cache and the conditional-request code to [Caching, files, mail, signals and tasks](services.md). The decorators and mixins that require a login are in `django/contrib/auth/` ([Authentication, sessions and messages](auth.md)). The admin has a wrapper of its own for its views, `AdminSite.admin_view`, which applies `never_cache` and `csrf_protect` unless told not to ([The admin](admin.md)). And the static files app serves its files during development through the view of [The static file view](views/static-files.md) ([Content types, static files and the other contrib apps](contrib.md)).
