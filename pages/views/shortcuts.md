---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The shortcuts

The functions of `django/shortcuts.py`: `render`, which renders a template into a response; `resolve_url`, which turns an object, a pattern's name or a URL into a URL, and `redirect`, which makes a redirect response to it; and `get_object_or_404` and `get_list_or_404`, each with an asynchronous twin, which run a query and raise `Http404` when it finds nothing.

A view sits between parts of Django that are kept apart. `render_to_string`, in the template loader, returns a string and is given no response. The ORM returns objects, or raises its own exceptions, and has no notion of a status code. A view is where they meet, and the same few lines join them in view after view. The shortcuts are those lines given names. The module's docstring says what that costs: it calls them helpers that span multiple levels, and says they introduce controlled coupling for convenience's sake (`django/shortcuts.py`). Each one is short enough to be read whole.

## `render`

`render` loads a template, renders it with a context, and puts the result in an `HttpResponse`. It is two lines: `render_to_string` from the template loader, given the request so that the engine's context processors run, and then the response's constructor, given the string, the content type and the status (`django/shortcuts.py:render`, `django/template/loader.py:render_to_string`).

The response it returns is finished. Nothing downstream can tell that a template made it, and nothing downstream can alter the context, because the context is gone. That is the difference from returning a `TemplateResponse`, which leaves the rendering to the handler:

```text recording=views
render() returns a response already rendered; a TemplateResponse is made unrendered
    render(request(), "gazette/front.html", {"edition": 7})  ->  an HttpResponse, status 200, content 'Edition 7 of the Gazette\n'
    render(request(), "gazette/front.html", {"edition": 7}, status=203)  ->  an HttpResponse, status 203, content 'Edition 7 of the Gazette\n'
    TemplateResponse(request(), "gazette/front.html", {"edition": 7})  ->  a TemplateResponse, status 200, not rendered
    render(request(), "gazette/no-such.html")  ->  raises TemplateDoesNotExist
    TemplateResponse(request(), "gazette/no-such.html")  ->  a TemplateResponse, status 200, not rendered
```

The last two lines show the difference when the template does not exist. `render` raises, in the view. A `TemplateResponse` is made without complaint, since it has only been told a name; the failure comes later, when the handler calls its `render` ([The centre of the chain](../handlers/view.md#template-responses)) (`django/template/response.py:SimpleTemplateResponse.render`).

## `redirect` and `resolve_url`

`redirect` returns a redirect response to wherever its first argument leads. The response class is `HttpResponsePermanentRedirect` if `permanent` is true and `HttpResponseRedirect` if not, and `preserve_request` and `max_length` are passed to it untouched (`django/shortcuts.py:redirect`). What status each combination gives, and which targets the response class refuses, are the response's business ([The response object](../http/response.md)).

```text recording=views
redirect(): the response it makes
    redirect("articles")  ->  an HttpResponseRedirect, status 302, Location '/articles/', content ''
    redirect("article", slug="ferry-timetable")  ->  an HttpResponseRedirect, status 302, Location '/articles/ferry-timetable/', content ''
    redirect(ferry)  ->  an HttpResponseRedirect, status 302, Location '/articles/ferry-timetable/', content ''
    redirect("articles", permanent=True)  ->  an HttpResponsePermanentRedirect, status 301, Location '/articles/', content ''
    redirect("articles", preserve_request=True)  ->  an HttpResponseRedirect, status 307, Location '/articles/', content ''
    redirect("articles", permanent=True, preserve_request=True)  ->  an HttpResponsePermanentRedirect, status 308, Location '/articles/', content ''
    redirect("https://example.org/")  ->  an HttpResponseRedirect, status 302, Location 'https://example.org/', content ''
    redirect("javascript:alert(1)")  ->  raises NoReverseMatch: 'javascript' is not a registered namespace
```

Working out the target is the job of `resolve_url`, and it accepts different kinds of thing under one parameter: its docstring lists a model, a view name and a URL, and a view function is taken as well. It tries them in a fixed order (`django/shortcuts.py:resolve_url`):

1. An object with a `get_absolute_url` method is asked for its URL. Any other arguments are ignored.
2. A string that begins `"./"` or `"../"` is returned as it is: a relative URL.
3. Anything else is given to `reverse`, with the remaining arguments as the pattern's arguments. A pattern's name is resolved here, and so is a view function, which `reverse` also accepts.
4. If `reverse` raises `NoReverseMatch`, a string that contains a slash or a dot is returned as it is, on the grounds that it looks like a URL. Without either, or when the argument was a callable, the exception is raised again.

A lazy string, such as `reverse_lazy` returns, is turned into text before the second step.

```text recording=views
resolve_url(): an object, a name, or a URL
    resolve_url("/articles/")  ->  '/articles/'
    resolve_url("articles")  ->  '/articles/'
    resolve_url("article", slug="ferry-timetable")  ->  '/articles/ferry-timetable/'
    resolve_url("article", "ferry-timetable")  ->  '/articles/ferry-timetable/'
    resolve_url(views.front)  ->  '/'
    resolve_url(ferry), where ferry is the Article with the slug 'ferry-timetable'  ->  '/articles/ferry-timetable/'
    resolve_url(ferry, slug="ignored")  ->  '/articles/ferry-timetable/'
    resolve_url("./next/")  ->  './next/'
    resolve_url("../")  ->  '../'
    resolve_url("https://example.org/")  ->  'https://example.org/'
    resolve_url("gazette.example")  ->  'gazette.example'
    resolve_url("no-such-name")  ->  raises NoReverseMatch
    resolve_url("no such/name")  ->  'no such/name'
    resolve_url(reverse_lazy("articles"))  ->  '/articles/'
    resolve_url(views.nothing, 7)  ->  raises NoReverseMatch
```

The order has consequences. A URL written out in full is not recognised as one: it is first tried as a pattern's name, fails, and is returned because of its slashes. So a redirect to a literal path that does not begin `"./"` or `"../"` pays for one failed `reverse`. A name that does not exist is reported as such only if it has neither a slash nor a dot in it, and with either it becomes the target as it stands, as the made-up `"no such/name"` does above. The last line of the `redirect` recording is the same rule at work. `reverse` reads a string with a colon as a name inside a namespace, and `"javascript:alert(1)"` has neither a slash nor a dot, so the `NoReverseMatch` is raised, and the string never reaches the response class that would have refused its scheme.

Within Django, `resolve_url` is how the login settings come to accept either form. `settings.LOGIN_URL` and `settings.LOGIN_REDIRECT_URL` may each hold a path or a pattern's name, and the code that uses them passes them through this function first (`django/contrib/auth/decorators.py:user_passes_test`, `django/contrib/auth/views.py:LoginView.get_default_redirect_url`).

## `get_object_or_404` and `get_list_or_404`

`get_object_or_404` runs a query that should find one object and turns the ORM's failure into the HTTP one: when the query raises the model's `Model.DoesNotExist`, it raises `Http404` in its place. The view that called it need not test anything, because an `Http404` leaving a view becomes a 404 response ([What the handler asks of a view](callable.md#what-a-view-may-raise)).

Its first argument may be a model class, a manager or a queryset. `_get_queryset` sorts them out by a test of one attribute: anything with a `_default_manager`, which a model class has, is replaced by that manager's `all()`, and anything else is used as it is. The rest of the arguments go to the queryset's `get` (`django/shortcuts.py:_get_queryset`, `django/shortcuts.py:get_object_or_404`).

```text recording=views
get_object_or_404() and get_list_or_404()
    (the queries these questions send are not written down)
    get_object_or_404(Article, slug="ferry-timetable")  ->  <Article: New ferry timetable>
    get_object_or_404(Article.objects, slug="ferry-timetable")  ->  <Article: New ferry timetable>
    get_object_or_404(Article.objects.filter(published__month=3), slug="ferry-timetable")  ->  <Article: New ferry timetable>
    get_object_or_404(Article.objects.filter(published__month=4), slug="ferry-timetable")  ->  raises Http404: No Article matches the given query.
    get_object_or_404(Article, slug="no-such-article")  ->  raises Http404: No Article matches the given query.
    get_object_or_404(Article, headline__contains="cat")  ->  raises MultipleObjectsReturned
    get_object_or_404("Article", slug="ferry-timetable")  ->  raises ValueError: First argument to get_object_or_404() must be a Model, Manager, or QuerySet, not 'str'.
    get_list_or_404(Article.objects.order_by("published"), headline__contains="cat")  ->  [<Article: Lost: a grey cat, Quay Street>, <Article: Found: a grey cat>]
    get_list_or_404(Article, headline__contains="dog")  ->  raises Http404: No Article matches the given query.
    type(get_list_or_404(Article.objects.order_by("slug"), published__month=3)).__name__  ->  'list'
```

Passing a queryset is how a view narrows the search: the fourth line fails although the article exists, because the queryset it was given holds only April's. The function catches `Model.DoesNotExist` and nothing else. A query that matches several objects raises `MultipleObjectsReturned`, which is a 500 by the time it reaches the client. The message of the `Http404` names the model and nothing about the query.

`get_list_or_404` calls `filter` in place of `get`, and has to find out whether anything came back. It does so by making a list of the whole result, and it returns the list. The caller gets every row in memory and no queryset to refine (`django/shortcuts.py:get_list_or_404`).

Each has a twin for a coroutine. `aget_object_or_404` awaits the queryset's `aget`, and `aget_list_or_404` builds its list by iterating the queryset asynchronously (`django/shortcuts.py:aget_object_or_404`, `django/shortcuts.py:aget_list_or_404`).

The generic views do not use these functions. `SingleObjectMixin.get_object` does the same translation itself, with a message of its own ([The generic views](generic.md#detailview-one-object)).
