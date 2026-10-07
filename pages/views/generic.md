---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The generic views

How the generic views of `django/views/generic/` are put together: a handler method that calls a series of small methods declared by mixins, so that `TemplateView`, `DetailView` and `ListView` are little more than lists of base classes. `RedirectView`, which is built differently, is here too.

Some views are written in every project and are nearly the same in all of them. Show one object by its slug. List the objects of a model, a page at a time. The steps do not vary: find the data, put it in a context, pick a template, render. What varies is a handful of decisions along the way, such as which model, which rows of it, what the template calls them and where the template is.

A generic view is one of those views written once, with its decisions taken out of the handler method. Some became methods of their own, whose default version reads a class attribute, so a project can settle the decision by assigning the attribute, or override the method when the answer depends on the request. Others are attributes read where they are needed. And because related decisions are useful together in more than one view, the methods those decisions became are not declared on the views: `DetailView` and `ListView` declare nothing, and `TemplateView` only its `get`. They are declared on **mixins**, small classes that are never used alone, and a view is assembled by inheriting from several.

The price is that no one class shows what a generic view does. To know which `get_context_data` runs for a `DetailView`, the method resolution order has to be read, and the answer is two methods, the first calling the second.

## Two halves

`DetailView` inherits from `SingleObjectTemplateResponseMixin` and `BaseDetailView`, and has no body beyond a docstring. Every generic view that renders a template is assembled so, from two halves, except `TemplateView`, which is written in one piece: its bases are two mixins and `View`, and its `get` is its own (`django/views/generic/detail.py:DetailView`).

The **base view** is the half that has the handler method. `BaseDetailView.get` finds the object and builds the context, and then calls `render_to_response`, a method that neither it nor any of its bases declares. Its docstring says as much: it requires subclassing to provide a response mixin (`django/views/generic/detail.py:BaseDetailView`).

The **response mixin** is the half that supplies that method, by turning a context into a `TemplateResponse` and working out which template to name. Putting the halves together gives a working view. Keeping them apart means the data half can be reused with a different way of answering: a class that inherits from `BaseDetailView` and declares its own `render_to_response` returns the same object in whatever form it likes.

| view | its handler method is in | which gets its data through | and answers through |
|---|---|---|---|
| `TemplateView` | `TemplateView` itself | `ContextMixin` | `TemplateResponseMixin` |
| `DetailView` | `BaseDetailView` | `SingleObjectMixin` | `SingleObjectTemplateResponseMixin` |
| `ListView` | `BaseListView` | `MultipleObjectMixin` | `MultipleObjectTemplateResponseMixin` |

*The three display views, by where their parts are declared. The form views and the date views are assembled in the same way from more parts.*

The response mixin is written first among the bases, so it is first in the method resolution order:

```text recording=views
TemplateView  ->  TemplateView > TemplateResponseMixin > ContextMixin > View
...
DetailView  ->  DetailView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseDetailView > SingleObjectMixin > ContextMixin > View
ListView  ->  ListView > MultipleObjectTemplateResponseMixin > TemplateResponseMixin > BaseListView > MultipleObjectMixin > ContextMixin > View
```

## `ContextMixin` and `TemplateResponseMixin`

`ContextMixin` and `TemplateResponseMixin` are in each of those three lists, one for each half.

`ContextMixin.get_context_data` is where every context ends up. It takes keyword arguments and returns them as the context, having added to them. It adds the view itself under the name `"view"`, unless a value of that name was passed. And it lays the view's `extra_context` over the top, when that attribute is not `None` (`django/views/generic/base.py:ContextMixin.get_context_data`).

Three mixins built on it, `SingleObjectMixin`, `MultipleObjectMixin` and `FormMixin`, declare a `get_context_data` of their own, to one convention: each adds what it contributes, lets a keyword argument it received take the place of its own value of the same name, and passes the result to `super().get_context_data`. So a value passed in by the caller wins over a mixin's own, and `extra_context`, applied last of all in `ContextMixin`, wins over both. `MultipleObjectMixin` keeps one argument for itself: `object_list` is a named parameter of its method, the list it is to work on, so it is not among the keyword arguments that override. Under that name the context gets the list itself when the view does not paginate, and the page's objects when it does.

`TemplateResponseMixin.render_to_response` makes the response. It calls `get_template_names`, and gives the result to `response_class`, which is `TemplateResponse` unless a subclass says otherwise, with the request, the context, and the view's `template_engine` and `content_type` (`django/views/generic/base.py:TemplateResponseMixin`). What it passes is a list of names, not a template. The response tries the names in order when it is rendered, and uses the first that exists, which is what lets a view offer a specific name and a general one behind it.

In this mixin `get_template_names` is as simple as it can be: a list holding `template_name`, or an `ImproperlyConfigured` when that is `None`. The two response mixins built on it start by calling it, and treat that exception as an ordinary answer meaning that no name was given.

`TemplateView` is the two mixins and `View` with a short `get` between them: the keyword arguments from the path go to `get_context_data`, and the context goes to `render_to_response` (`django/views/generic/base.py:TemplateView`). A view whose decisions are all attributes needs no subclass. The Gazette makes this one in its URLconf, by giving `as_view` the attributes:

```python
# gazette/urls.py
path("about/", TemplateView.as_view(template_name="gazette/about.html", extra_context={"founded": 1871}), name="about"),
```

```text recording=views
GET /about/: a TemplateView made in the URLconf
    BaseHandler._get_response
      view(request)  (the function as_view returned for TemplateView)
        View.__init__(template_name='gazette/about.html', extra_context={'founded': 1871})  (a new TemplateView)
        View.setup(request)
        View.dispatch(request)
          TemplateView.get(request)
            ContextMixin.get_context_data()  ->  a dict with the keys founded, view
            TemplateResponseMixin.render_to_response(context)
              TemplateResponseMixin.get_template_names  ->  ['gazette/about.html']
              -> a TemplateResponse, status 200, not rendered
            -> a TemplateResponse, status 200, not rendered
          -> a TemplateResponse, status 200, not rendered
        -> a TemplateResponse, status 200, not rendered
      SimpleTemplateResponse.render
    start_response("200 OK", headers)
    the server sends the body: 'The Gazette, founded 1871.\n'
```

## `DetailView`: one object

The Gazette's view of one article names a model and nothing else.

```python
# gazette/views.py
class ArticleDetail(DetailView):
    model = Article

# gazette/urls.py
path("articles/<slug:slug>/", views.ArticleDetail.as_view(), name="article"),
```

This is its `get`, for the request `GET /articles/ferry-timetable/`:

```text recording=views
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
```

`BaseDetailView.get` is three statements, and each is one of the indented groups: find the object and keep it as `BaseDetailView.object`, build the context, make the response (`django/views/generic/detail.py:BaseDetailView.get`).

```text figure=detail-view
The classes DetailView inherits from, in method resolution order, and which of them runs each of
six methods during a GET. The numbers are the order of the calls; an arrow is a call of super().

                                       1 get   2 get_object   3 get_queryset   4 get_context_data   5 render_to_response   6 get_template_names
SingleObjectTemplateResponseMixin                                                                                          runs first, calls super()
TemplateResponseMixin                                                                                runs                   raises ImproperlyConfigured: no template_name
BaseDetailView                         runs
SingleObjectMixin                               runs           runs             runs first, calls super()
ContextMixin                                                                    adds "view"
View                                   (as_view, setup and dispatch, before 1)

2 and 3: the object is looked up in the queryset by the slug or the pk the path captured.
4: the context is {"object", "article"}, then "view" is added.
6: with no template_name, the name is built from the object's model: gazette/article_detail.html.
```

*Which class runs each step of a `DetailView`'s `get`. The handler method is in one class, the lookup in a second, the response in a third, and two of the steps pass through two classes by way of `super()`.*

**The object.** `SingleObjectMixin.get_object` starts from a queryset and narrows it with what the path captured. It reads two keyword arguments from `View.kwargs`, named by the attributes `SingleObjectMixin.pk_url_kwarg` and `SingleObjectMixin.slug_url_kwarg`, which are `"pk"` and `"slug"`. With a primary key it filters on that, and ignores a slug unless `query_pk_and_slug` is true, in which case it filters on both. With only a slug it filters on the field that `get_slug_field` names. With neither it raises `AttributeError`, whose message says the view must be called with one or the other in the URLconf (`django/views/generic/detail.py:SingleObjectMixin.get_object`).

Then it calls `get` on what is left. The `LIMIT 21` in the query is that method's own doing, not the view's (`django/db/models/query.py:QuerySet.get`). An object that does not exist raises the model's `Model.DoesNotExist`, and `get_object` raises `Http404` in its place:

```text recording=views
      BaseDetailView.get(request, slug='no-such-article')
        SingleObjectMixin.get_object()
          SingleObjectMixin.get_queryset  ->  a QuerySet of Article, not yet fetched
          SingleObjectMixin.get_slug_field  ->  'slug'
          SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE "gazette_article"."slug" = %s LIMIT 21 with params ('no-such-article',)
          raises Http404
response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
log, WARNING to django.request: Not Found: /articles/no-such-article/
start_response("404 Not Found", headers)
```

**The queryset.** `SingleObjectMixin.get_queryset` returns the `queryset` attribute if the class set one, and otherwise everything the `model` attribute's default manager has ([Managers](../models/managers.md)); with neither it raises `ImproperlyConfigured`. In both cases what it returns is the result of `all()`, a new queryset. A queryset written as a class attribute is one object shared by every request the process serves, and each request works on a copy of it (`django/views/generic/detail.py:SingleObjectMixin.get_queryset`).

**The context.** `SingleObjectMixin.get_context_data` puts the view's object, when it has one, in as `"object"`, and a second time under the name `get_context_object_name` returns, when it returns one: `context_object_name` if set, and otherwise, for a model instance, the model's name in lower case. So the Gazette's template can say article where a template written for any model would say object (`django/views/generic/detail.py:SingleObjectMixin.get_context_data`).

**The template.** `SingleObjectTemplateResponseMixin.get_template_names` asks its base for `template_name` first, and when that raises it builds a list of its own. If `template_name_field` is set, the value of that field on the object goes first: the object names its own template. Then comes a name made from the object's model, or from the view's `model` when the object is not a model instance: the app label as a directory, and the model's name with `template_name_suffix`, which is `"_detail"`. If nothing could be built it raises `ImproperlyConfigured` again, with a message that lists what would have helped (`django/views/generic/detail.py:SingleObjectTemplateResponseMixin.get_template_names`).

## `ListView`: many objects, and pages of them

The Gazette lists its articles three to a page, newest first.

```python
# gazette/views.py
class ArticleList(ListView):
    model = Article
    paginate_by = 3
    ordering = "-published"
```

This is its `get` for the second page, `GET /articles/?page=2`, and what the handler does with the response afterwards:

```text recording=views
    BaseListView.get(request)
      MultipleObjectMixin.get_queryset
        MultipleObjectMixin.get_ordering  ->  '-published'
        -> a QuerySet of Article, ordered by -published, not yet fetched
      MultipleObjectMixin.get_allow_empty  ->  True
      MultipleObjectMixin.get_context_data()
        MultipleObjectMixin.get_paginate_by(queryset)  ->  3
        MultipleObjectMixin.get_context_object_name(object_list)  ->  'article_list'
        MultipleObjectMixin.paginate_queryset(queryset, 3)
          MultipleObjectMixin.get_paginate_orphans  ->  0
          MultipleObjectMixin.get_allow_empty  ->  True
          MultipleObjectMixin.get_paginator(queryset, 3, orphans=0, allow_empty_first_page=True)  ->  a Paginator
          Paginator.page(2)
            SQL SELECT COUNT(*) AS "__count" FROM "gazette_article" with params ()
            -> <Page 2 of 3>
          -> (a Paginator, <Page 2 of 3>, the page's objects: a QuerySet of Article, ordered by -published, not yet fetched, True)
        ContextMixin.get_context_data(paginator=..., page_obj=..., is_paginated=..., object_list=..., article_list=...)  ->  a dict with the keys article_list, is_paginated, object_list, page_obj, paginator, view
        -> a dict with the keys article_list, is_paginated, object_list, page_obj, paginator, view
      TemplateResponseMixin.render_to_response(context)
        MultipleObjectTemplateResponseMixin.get_template_names
          TemplateResponseMixin.get_template_names  raises ImproperlyConfigured
          -> ['gazette/article_list.html']
...
SimpleTemplateResponse.render
  SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" ORDER BY "gazette_article"."published" DESC LIMIT 3 OFFSET 3 with params ()
```

`BaseListView.get` keeps the queryset as `BaseListView.object_list`, makes the context and makes the response (`django/views/generic/list.py:BaseListView.get`).

**The queryset.** `MultipleObjectMixin.get_queryset` differs from the single-object one in two ways. The `queryset` attribute may be any iterable, a list for instance, and `all()` is called on it only when it is a `QuerySet`. And an ordering is applied at the end when there is one: `get_ordering` returns the `ordering` attribute, which is `None` unless it has been set to a field name or a sequence of them, and when it is set the queryset is passed through `order_by` (`django/views/generic/list.py:MultipleObjectMixin.get_queryset`).

**Pages.** `MultipleObjectMixin.get_context_data` asks `get_paginate_by` for a page size. If the answer is nothing, the whole list goes into the context as `"object_list"`, with `"paginator"` and `"page_obj"` as `None` and `"is_paginated"` false. Otherwise `paginate_queryset` takes over (`django/views/generic/list.py:MultipleObjectMixin.get_context_data`).

That method makes a `Paginator` and has to find the page number. It looks first in the keyword arguments from the path and then in the query string, under the name `page_kwarg`, which is `"page"`, and takes 1 when neither gives a value. The number may also be the word `"last"`. Any other value that `int` refuses is an `Http404`, and so is a number the paginator refuses (`django/views/generic/list.py:MultipleObjectMixin.paginate_queryset`):

```text recording=views
          MultipleObjectMixin.paginate_queryset(queryset, 3)
            MultipleObjectMixin.get_paginate_orphans  ->  0
            MultipleObjectMixin.get_allow_empty  ->  True
            MultipleObjectMixin.get_paginator(queryset, 3, orphans=0, allow_empty_first_page=True)  ->  a Paginator
            Paginator.page(9)
              SQL SELECT COUNT(*) AS "__count" FROM "gazette_article" with params ()
              raises EmptyPage
            raises Http404
response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
log, WARNING to django.request: Not Found: /articles/
start_response("404 Not Found", headers)
```

The context then holds the paginator, the page as `"page_obj"`, the page's own objects as `"object_list"`, and `"is_paginated"`, which is true when there is more than one page. As in the detail view, the list is in the context a second time when `get_context_object_name` returns a name: `context_object_name` if set, and otherwise, for a list that has a model, the model's name with `"_list"` after it.

**The queries.** The recording of page 2 has two lines of SQL, and neither is where a reader might look for it. The count is run by the paginator when the page is asked for, since it cannot validate a page number without knowing how many rows there are (`django/core/paginator.py:Paginator.page`, `django/core/paginator.py:Paginator.count`). The rows are fetched under `SimpleTemplateResponse.render`, by the template's own loop: what the view put in the context was a queryset limited to three rows and not yet run. The view never held an article ([QuerySets](../querysets.md)).

**An empty list.** By default an empty list is rendered like any other. With `allow_empty` false, `BaseListView.get` raises `Http404` for one, and takes care how it finds out: when the view paginates and the list is a queryset, it asks `exists`, a cheap query, where otherwise it tests the list for truth, which loads a queryset whole.

**The template.** `MultipleObjectTemplateResponseMixin.get_template_names` takes `template_name` if there is one and then, when the list has a model, adds a name built from it with the suffix `"_list"`. Unlike the detail view's, this one adds the generated name even when `template_name` was given, so the given name is tried first and the generated one stands behind it (`django/views/generic/list.py:MultipleObjectTemplateResponseMixin.get_template_names`).

## `RedirectView`

`RedirectView` shares a module with `TemplateView`, and with the views above only their last base. It has no mixins: it is `View` with a `get` that redirects (`django/views/generic/base.py:RedirectView`).

`RedirectView.get_redirect_url` finds the target from one of two attributes. A `url` is a string, and is filled in from the path's keyword arguments with Python's `%` formatting, so a parameter is written `%(slug)s` and a literal percent sign has to be doubled. A `pattern_name` is given to `reverse` with the path's arguments. With neither the method returns `None`. If `query_string` is true, the request's query string is added to whatever was found (`django/views/generic/base.py:RedirectView.get_redirect_url`).

`get` returns an `HttpResponsePermanentRedirect` when the `permanent` attribute is true and an `HttpResponseRedirect` when it is false, as it is unless set. When there is no target it answers with a 410, `HttpResponseGone`, and logs a warning (`django/views/generic/base.py:RedirectView.get`).

Two of the Gazette's old addresses are of this kind. One sends a reader on to the article of the same slug, permanently and with the query string kept. The other has nothing to redirect to:

```python
# gazette/urls.py
path("news/<slug:slug>/", RedirectView.as_view(pattern_name="article", permanent=True, query_string=True), name="news-article"),
path("weather/", RedirectView.as_view(), name="weather"),
```

```text recording=views
GET /news/ferry-timetable/?ref=front: a RedirectView that is permanent and keeps the query string
    BaseHandler._get_response
      view(request, slug='ferry-timetable')  (the function as_view returned for RedirectView)
        View.__init__(pattern_name='article', permanent=True, query_string=True)  (a new RedirectView)
        View.setup(request, slug='ferry-timetable')
        View.dispatch(request, slug='ferry-timetable')
          RedirectView.get(request, slug='ferry-timetable')
            RedirectView.get_redirect_url(slug='ferry-timetable')  ->  '/articles/ferry-timetable/?ref=front'
            -> an HttpResponsePermanentRedirect, status 301, Location '/articles/ferry-timetable/?ref=front'
          -> an HttpResponsePermanentRedirect, status 301, Location '/articles/ferry-timetable/?ref=front'
        -> an HttpResponsePermanentRedirect, status 301, Location '/articles/ferry-timetable/?ref=front'
    start_response("301 Moved Permanently", headers), with Location: /articles/ferry-timetable/?ref=front
    the server sends the body: ''
```

```text recording=views
GET /weather/: a RedirectView with nowhere to send the request
    BaseHandler._get_response
      view(request)  (the function as_view returned for RedirectView)
        View.__init__()  (a new RedirectView)
        View.setup(request)
        View.dispatch(request)
          RedirectView.get(request)
            RedirectView.get_redirect_url()  ->  None
            log, WARNING to django.request: Gone: /weather/
            -> an HttpResponseGone, status 410
          -> an HttpResponseGone, status 410
        -> an HttpResponseGone, status 410
    start_response("410 Gone", headers)
    the server sends the body: ''
```

The class declares a method for each of the other names in `http_method_names` too, except `"trace"`, and each one calls `get`. That includes `options`, which replaces the one `View` supplies. A `RedirectView` redirects a `"POST"` or a `"DELETE"` as readily as a `"GET"`.
