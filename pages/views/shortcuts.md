---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The shortcuts

The functions of `django/shortcuts.py`: `render`, which renders a template into a response; `resolve_url`, which turns an object, a pattern's name or a URL into a URL, and `redirect`, which makes a redirect response to it; and `get_object_or_404` and `get_list_or_404`, each with an asynchronous twin, which run a query and raise `Http404` when it finds nothing.

A view sits between parts of Django that are kept apart. `render_to_string`, in the template loader, returns a string and is given no response. The ORM returns objects, or raises its own exceptions, and has no notion of a status code. A view is where they meet, and the same few lines join them in view after view. The shortcuts are those lines given names (`django/shortcuts.py`).

> **Why.** The parts are kept apart on purpose. Django's design philosophies name loose coupling and tight cohesion as "a fundamental goal of Django's stack": its layers "shouldn't 'know' about each other unless absolutely necessary" (`docs/misc/design-philosophies.txt`). The shortcuts relax that rule knowingly. The module's docstring calls them helpers that span multiple levels of MVC, and says that they "introduce controlled coupling for convenience's sake" (`django/shortcuts.py`).

## `render`

`render` loads a template, renders it with a context, and puts the result in an `HttpResponse`. It calls `render_to_string` from the template loader, giving it the request so that the engine's context processors run, and then the response's constructor, with the string, the content type and the status (`django/shortcuts.py:render`, `django/template/loader.py:render_to_string`).

The response it returns is finished. Nothing in it says a template made it, and nothing downstream can alter the context, because the context is gone. That is the difference from returning a `TemplateResponse`, which leaves the rendering to the handler. Side by side, `render` returns its response with the content already in it, and a `TemplateResponse` comes back not yet rendered. They differ again when the template does not exist: `render` raises in the view, while a `TemplateResponse` is made without complaint, since it has only been told a name, and fails later, when the handler calls its `render` ([The centre of the chain](../handlers/view.md#template-responses)) (`django/template/response.py:SimpleTemplateResponse.render`).

```text recording=views
render() returns a response already rendered; a TemplateResponse is made unrendered
    render(request(), "gazette/front.html", {"edition": 7})  ->  an HttpResponse, status 200, content 'Edition 7 of the Gazette\n'
    render(request(), "gazette/front.html", {"edition": 7}, status=203)  ->  an HttpResponse, status 203, content 'Edition 7 of the Gazette\n'
    TemplateResponse(request(), "gazette/front.html", {"edition": 7})  ->  a TemplateResponse, status 200, not rendered
    render(request(), "gazette/no-such.html")  ->  raises TemplateDoesNotExist
    TemplateResponse(request(), "gazette/no-such.html")  ->  a TemplateResponse, status 200, not rendered
```

## `redirect` and `resolve_url`

`redirect` returns a redirect response to wherever its first argument leads. It leaves working out the target to `resolve_url`, and chooses the response class: `HttpResponsePermanentRedirect` if `permanent` is true and `HttpResponseRedirect` if not, with `preserve_request` and `max_length` passed to it untouched (`django/shortcuts.py:redirect`). What status each class sends, and which targets it refuses, are the response's business ([The response object](../http/response.md#redirects)).

The two flags give four statuses: 302 by default, 301 with `permanent`, 307 with `preserve_request`, and 308 with both. The last line is a target refused before any response is made: `reverse` reads the colon in `"javascript:alert(1)"` as the end of a namespace's name and raises `NoReverseMatch`, which `resolve_url` lets pass because the string holds neither a slash nor a dot (the fourth of its steps below), so the string never reaches the response class, whose test of the scheme would have refused it (`django/urls/base.py:reverse`, `django/http/response.py:HttpResponseRedirectBase.__init__`).

```text recording=views
redirect(): the response it makes
    redirect("articles")  ->  an HttpResponseRedirect, status 302, Location '/articles/', content ''
    ...
    redirect("articles", permanent=True)  ->  an HttpResponsePermanentRedirect, status 301, Location '/articles/', content ''
    redirect("articles", preserve_request=True)  ->  an HttpResponseRedirect, status 307, Location '/articles/', content ''
    redirect("articles", permanent=True, preserve_request=True)  ->  an HttpResponsePermanentRedirect, status 308, Location '/articles/', content ''
    ...
    redirect("javascript:alert(1)")  ->  raises NoReverseMatch: 'javascript' is not a registered namespace
```

`resolve_url` takes an object, a pattern's name, a view function or a URL under one parameter, and tries them in a fixed order (`django/shortcuts.py:resolve_url`):

1. An object with a `get_absolute_url` method is asked for its URL. Any other arguments are ignored.
2. A string that begins `"./"` or `"../"` is returned as it is: a relative URL.
3. Anything else is given to `reverse`, with the remaining arguments as the pattern's arguments. A pattern's name is resolved here, and so is a view function, which `reverse` also accepts.
4. If `reverse` raises `NoReverseMatch`, a string that contains a slash or a dot is returned as it is, on the grounds that it looks like a URL. Without either, or when the argument was a callable, the exception is raised again.

A lazy string, such as `reverse_lazy` returns, is turned into text before the second step.

Each answer below comes from one of those steps. The article, with or without a keyword to ignore, answers at the first; `"./next/"` and `"../"` at the second; the names and the view function at the third. The rest reach the fourth: a path, lazy or not, a full URL, `"gazette.example"` and the made-up `"no such/name"` come back as they were given, while `"no-such-name"`, with neither a slash nor a dot, and the view function given an argument its pattern does not take are refused.

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

The order has consequences. A URL written out in full is not recognised as one: it is first tried as a pattern's name, fails, and is returned because of its slashes, so a redirect to a literal path that does not begin `"./"` or `"../"` pays for one failed `reverse`.

> **Trap.** A misspelt name is not always reported. If it holds a slash or a dot, `resolve_url` returns it as it stands, as it returns `"gazette.example"` and `"no such/name"` above, so `redirect` given a misspelt name with a dot and no namespace raises nothing and sends the client to the name as a relative URL (`django/shortcuts.py:resolve_url`).

Within Django, `resolve_url` is how the login settings come to accept either form. `settings.LOGIN_URL` and `settings.LOGIN_REDIRECT_URL` may each hold a path or a pattern's name, and the code that uses them passes them through this function first (`django/contrib/auth/decorators.py:user_passes_test`, `django/contrib/auth/views.py:LoginView.get_default_redirect_url`).

## `get_object_or_404` and `get_list_or_404`

`get_object_or_404` runs a query that should find one object and turns the ORM's failure into the HTTP one: when the query raises the model's `Model.DoesNotExist`, it raises `Http404` in its place. The view that called it need not test anything, because the handler turns an `Http404` leaving a view into a response ([What the handler asks of a view](callable.md#what-a-view-may-raise)). The generic views do not call it: `SingleObjectMixin.get_object` makes the same translation itself, with a message of its own ([The generic views](generic.md#detailview-one-object)) (`django/views/generic/detail.py:SingleObjectMixin.get_object`).

Its first argument may be a model class, a manager or a queryset. `_get_queryset` sorts them out by a test of one attribute: anything with a `_default_manager`, which a model class has, is replaced by that manager's `all()`, and anything else is used as it is. The rest of the arguments go to the queryset's `get` (`django/shortcuts.py:_get_queryset`, `django/shortcuts.py:get_object_or_404`).

Passing a queryset is how a view narrows the search: the article on the ferry timetable is found through the model, its manager and a queryset of March's articles, but a queryset of April's does not hold it, and the search ends in `Http404` although the article exists. Every `Http404` below carries the same message, which names the model and nothing about the query, and what `get_list_or_404` returns, in the last lines, is a list.

```text recording=views
get_object_or_404() and get_list_or_404()
    ...
    get_object_or_404(Article, slug="ferry-timetable")  ->  <Article: New ferry timetable>
    get_object_or_404(Article.objects, slug="ferry-timetable")  ->  <Article: New ferry timetable>
    get_object_or_404(Article.objects.filter(published__month=3), slug="ferry-timetable")  ->  <Article: New ferry timetable>
    get_object_or_404(Article.objects.filter(published__month=4), slug="ferry-timetable")  ->  raises Http404: No Article matches the given query.
    get_object_or_404(Article, slug="no-such-article")  ->  raises Http404: No Article matches the given query.
    get_object_or_404(Article, headline__contains="cat")  ->  raises MultipleObjectsReturned
    ...
    get_list_or_404(Article.objects.order_by("published"), headline__contains="cat")  ->  [<Article: Lost: a grey cat, Quay Street>, <Article: Found: a grey cat>]
    get_list_or_404(Article, headline__contains="dog")  ->  raises Http404: No Article matches the given query.
    type(get_list_or_404(Article.objects.order_by("slug"), published__month=3)).__name__  ->  'list'
```

> **Trap.** `get_object_or_404` catches `Model.DoesNotExist` and nothing else. A query that matches several objects raises `MultipleObjectsReturned`, as the search for a headline containing "cat" does above, and the handler, which does not recognise that exception, makes a 500 of it ([How an exception becomes a response](../handlers/exceptions.md#which-exception-becomes-which-response)) (`django/shortcuts.py:get_object_or_404`, `django/core/handlers/exception.py:response_for_exception`).

`get_list_or_404` calls `filter` in place of `get`, and has to find out whether anything came back. It does so by making a list of the whole result, and it returns the list. The caller gets every row in memory and no queryset to refine (`django/shortcuts.py:get_list_or_404`).

Each has a twin for a coroutine. `aget_object_or_404` awaits the queryset's `aget`, and `aget_list_or_404` builds its list by iterating the queryset asynchronously (`django/shortcuts.py:aget_object_or_404`, `django/shortcuts.py:aget_list_or_404`).
