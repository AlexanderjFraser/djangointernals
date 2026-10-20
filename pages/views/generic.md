---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The generic views

Most of Django's generic views are assembled from two halves: a base view, which has the handler method, and a response mixin, which supplies `render_to_response`. `TemplateView`, the plainest, is written in one piece, and `RedirectView` is built without mixins.

Some views are written in every project and are nearly the same in all of them. Show one object by its slug. List the objects of a model, a page at a time. The steps do not vary: find the data, put it in a context, pick a template, render. What varies is a handful of decisions along the way, such as which model, which rows of it, what the template calls them and where the template is.

A generic view is one of those views written once, with its decisions taken out of the handler method. Some became methods of their own, whose default version reads a class attribute, so a project can settle the decision by assigning the attribute, or override the method when the answer depends on the request. Others are attributes read where they are needed. And because related decisions are useful together in more than one view, `DetailView` and `ListView` declare nothing, and `TemplateView` only its `get`: the methods their decisions became are declared on **mixins**, small classes that are never used alone, and a view is assembled by inheriting from several.

The price is that no one class shows what a generic view does. To know which `get_context_data` runs for a `DetailView`, the method resolution order has to be read, and the answer is two methods: `SingleObjectMixin.get_context_data`, which calls `ContextMixin.get_context_data`.

How `DetailView` finds one object from what the path captured, and `ListView` divides a list into pages, is the subject of [`DetailView` and `ListView`](display.md).

## The base view and the response mixin

`DetailView` inherits from `SingleObjectTemplateResponseMixin` and `BaseDetailView`, and has no body beyond a docstring (`django/views/generic/detail.py:DetailView`). Every generic view that renders a template is assembled so, from two halves, except `TemplateView`, which is written in one piece: its bases are two mixins and `View`, and its `get` is its own (`django/views/generic/base.py:TemplateView`).

The **base view** is the half that has the handler method. `BaseDetailView.get` finds the object and builds the context, and then calls `render_to_response`, a method that neither it nor any of its bases declares, so a subclass has to supply it (`django/views/generic/detail.py:BaseDetailView`).

The **response mixin** is the half that supplies that method, by turning a context into a `TemplateResponse` and working out which template to name. Putting the halves together gives a working view. Keeping them apart means the data half can be reused with a different way of answering: a class that inherits from `BaseDetailView` and declares its own `render_to_response` returns the same object in whatever form it likes.

| view | its handler method is in | which gets its data through | and answers through |
|---|---|---|---|
| `TemplateView` | `TemplateView` itself | `ContextMixin` | `TemplateResponseMixin` |
| `DetailView` | `BaseDetailView` | `SingleObjectMixin` | `SingleObjectTemplateResponseMixin` |
| `ListView` | `BaseListView` | `MultipleObjectMixin` | `MultipleObjectTemplateResponseMixin` |

*Three generic views, by where their parts are declared. The form views and the date views are assembled in the same way.*

Each line gives a view's classes in the order Python searches them for a method, its two halves one after the other, the response half first, and all three end in `ContextMixin` and `View`:

```text recording=views
TemplateView  ->  TemplateView > TemplateResponseMixin > ContextMixin > View
...
DetailView  ->  DetailView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseDetailView > SingleObjectMixin > ContextMixin > View
ListView  ->  ListView > MultipleObjectTemplateResponseMixin > TemplateResponseMixin > BaseListView > MultipleObjectMixin > ContextMixin > View
...
```

## `ContextMixin`, `TemplateResponseMixin` and `TemplateView`

`ContextMixin` and `TemplateResponseMixin` are in each of those three lists, one for each half.

`ContextMixin.get_context_data` is where every context ends up. It takes keyword arguments and returns them as the context, having added to them. It adds the view itself under the name `"view"`, unless a value of that name was passed. And it lays the view's `extra_context` over the top, when that attribute is not `None` (`django/views/generic/base.py:ContextMixin.get_context_data`).

The other mixins of `django/views/generic/` that declare a `get_context_data`, `SingleObjectMixin`, `MultipleObjectMixin` and `FormMixin`, keep to one convention: each adds what it contributes, lets a keyword argument it received, but for `MultipleObjectMixin`'s `object_list`, take the place of its own value of the same name, and passes the result to `super().get_context_data`. So a value passed in by the caller wins over a mixin's own, and `extra_context`, applied last of all in `ContextMixin`, wins over both.

`TemplateResponseMixin.render_to_response` makes the response. It calls `get_template_names`, and gives the result to `response_class`, which is `TemplateResponse` unless set otherwise, with the request, the context, and the view's `template_engine` and `content_type` (`django/views/generic/base.py:TemplateResponseMixin`). What it passes is a list of names, not a template. The response tries the names in order when it is rendered, and uses the first that exists, which is what lets a view offer a specific name and a general one behind it.

In this mixin `get_template_names` is as simple as it can be: a list holding `template_name`, or an `ImproperlyConfigured` when that is `None`. The response mixins of the detail and list views start by calling it, and treat that exception as an ordinary answer meaning that no name was given ([`DetailView` and `ListView`](display.md)).

`TemplateView` is the two mixins and `View` with a short `get` between them: the keyword arguments from the path go to `get_context_data`, and the context goes to `render_to_response` (`django/views/generic/base.py:TemplateView`). A view whose decisions are all attributes needs no subclass. The Gazette makes this one in its URLconf, by giving `as_view` the attributes:

```python
# gazette/urls.py
path("about/", TemplateView.as_view(template_name="gazette/about.html", extra_context={"founded": 1871}), name="about"),
```

The two attributes given to `as_view` reach the instance made for the request in `View.__init__`, and the context that `get` builds holds `"founded"`, laid over it from `extra_context`, beside the `"view"` that `ContextMixin` adds:

```text recording=views
GET /about/: a TemplateView made in the URLconf
...
        View.__init__(template_name='gazette/about.html', extra_context={'founded': 1871})  (a new TemplateView)
          ...
          TemplateView.get(request)
            ContextMixin.get_context_data()  ->  a dict with the keys founded, view
            TemplateResponseMixin.render_to_response(context)
              TemplateResponseMixin.get_template_names  ->  ['gazette/about.html']
              ...
```

## `RedirectView`

`RedirectView` shares a module with `TemplateView` but none of its mixins: it is `View` with a `get` that redirects (`django/views/generic/base.py:RedirectView`).

`RedirectView.get_redirect_url` finds the target from one of two attributes. A `url` is a string, and is filled in from the path's keyword arguments with Python's `%` formatting, so a parameter is written `%(slug)s`. A `pattern_name` is given to `reverse` with the path's arguments. With neither the method returns `None`. If `query_string` is true, the request's query string is added to whatever was found (`django/views/generic/base.py:RedirectView.get_redirect_url`).

> **Trap.** `RedirectView.url` goes through `%` at every request, even when the path captured nothing, so each `%` in it begins a conversion. A target holding an escaped character must double the sign, `%%20` for `%20`: written as it would be sent, the escape makes `get_redirect_url` raise a `ValueError` or a `TypeError`, or changes the URL (`docs/ref/class-based-views/base.txt`, `django/views/generic/base.py:RedirectView.get_redirect_url`).

`RedirectView.get` returns an `HttpResponsePermanentRedirect` when the `permanent` attribute is true and an `HttpResponseRedirect` when it is false, as it is unless set, and passes either one the attribute `preserve_request`, also false unless set. With it true, the response takes its class's other status, a 308 in place of a 301 and a 307 in place of a 302, which ask the client to repeat the request at the new address with its method and body (`django/http/response.py:HttpResponseRedirectBase.__init__`). When there is no target `get` answers with a 410, `HttpResponseGone`, and logs a warning (`django/views/generic/base.py:RedirectView.get`).

Two of the Gazette's old addresses are of this kind. One sends a reader on to the article of the same slug, permanently and with the query string kept. The other has nothing to redirect to:

```python
# gazette/urls.py
path("news/<slug:slug>/", RedirectView.as_view(pattern_name="article", permanent=True, query_string=True), name="news-article"),
path("weather/", RedirectView.as_view(), name="weather"),
```

The first answers with a 301 whose target keeps the query string the request brought:

```text recording=views
GET /news/ferry-timetable/?ref=front: a RedirectView that is permanent and keeps the query string
...
          RedirectView.get(request, slug='ferry-timetable')
            RedirectView.get_redirect_url(slug='ferry-timetable')  ->  '/articles/ferry-timetable/?ref=front'
            -> an HttpResponsePermanentRedirect, status 301, Location '/articles/ferry-timetable/?ref=front'
            ...
```

The second has no target: `get_redirect_url` returns `None`, and `get` logs its warning before it answers with the 410:

```text recording=views
GET /weather/: a RedirectView with nowhere to send the request
...
          RedirectView.get(request)
            RedirectView.get_redirect_url()  ->  None
            log, WARNING to django.request: Gone: /weather/
            -> an HttpResponseGone, status 410
            ...
```

The class declares a method for each of the other names in `View.http_method_names` too, except `"trace"`, and each one calls `get`. That includes `options`, which replaces the one `View` supplies. So a `RedirectView` redirects a `"POST"` or a `"DELETE"` as readily as a `"GET"`, and with the status a `"GET"` would get (`django/views/generic/base.py:RedirectView.post`).

> **New in 6.1.** `RedirectView.preserve_request`. Before it, a `RedirectView`'s redirect was a 301 or a 302, chosen by `permanent` alone, though the redirect classes had taken a `preserve_request` argument since 5.2; the view now passes its attribute to them (`docs/releases/6.1.txt`, `docs/releases/5.2.txt`).
