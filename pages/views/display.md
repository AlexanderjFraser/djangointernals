---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `DetailView` and `ListView`

The two plainest generic views that show a model's objects are `DetailView`, which finds one object by what the path captured, with the methods of `SingleObjectMixin`, and `ListView`, which lists many with those of `MultipleObjectMixin` and divides them into pages when `paginate_by` is set.

Each of these views is two halves, a base view that has the handler method and a response mixin that makes the response, and its decisions are taken by methods of mixins ([The generic views](generic.md)). By default both of these views find their objects through `get_queryset`, from the `queryset` attribute or else the `model` attribute's default manager, put what they find in the context under a name made from the model, and name a template made from the model too.

## `DetailView`: one object

The Gazette's view of one article names a model and nothing else.

```python
# gazette/views.py
class ArticleDetail(DetailView):
    model = Article

# gazette/urls.py
path("articles/<slug:slug>/", views.ArticleDetail.as_view(), name="article"),
```

`BaseDetailView.get` finds the object and keeps it as `BaseDetailView.object`, builds the context, and makes the response (`django/views/generic/detail.py:BaseDetailView.get`). Each step is a method found through the method resolution order, and the figure sets six methods of a `"GET"` against the classes `DetailView` inherits from: the two methods that run in two classes are the context's and the template names'.

```text figure=detail-view
The classes DetailView inherits from, in method resolution order, and which of them runs each of
six methods during a GET. The numbers are the order of the calls; an arrow is a call of super().

                                       1 get   2 get_object   3 get_queryset   4 get_context_data   5 render_to_response   6 get_template_names
SingleObjectTemplateResponseMixin                                                                                          runs first, calls super()
TemplateResponseMixin                                                                                runs                   raises ImproperlyConfigured: no template_name
BaseDetailView                         runs
SingleObjectMixin                               runs           runs             runs first, calls super()
ContextMixin                                                                    adds "view"
View

2 and 3: the object is looked up in the queryset by the slug or the pk the path captured.
4: the context is {"object", "article"}, then "view" is added.
6: with no template_name, the name is built from the object's model: gazette/article_detail.html.
```

*Which class runs each step of a `DetailView`'s `get`. The handler method is in one class, the lookup in a second, the response in a third, and two of the steps pass through two classes by way of `super()`.*

What the figure cannot show is the request itself: the SQL that finds the article. For `GET /articles/ferry-timetable/` the three groups under `get` are the three steps, and the `ImproperlyConfigured` near the end is an answer, not a failure, since `SingleObjectTemplateResponseMixin.get_template_names` catches it and builds the name itself:

```text recording=views
GET /articles/ferry-timetable/: a DetailView
...
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
                ...
```

**The object.** `SingleObjectMixin.get_object` starts from a queryset and narrows it with what the path captured. It reads two keyword arguments from `View.kwargs`, named by the attributes `SingleObjectMixin.pk_url_kwarg` and `SingleObjectMixin.slug_url_kwarg`, which are `"pk"` and `"slug"`. With a primary key it filters on that, and ignores a slug unless `query_pk_and_slug` is true, in which case it filters on both. With only a slug it filters on the field that `get_slug_field` names. With neither it raises `AttributeError`, whose message says the view must be called with one or the other in the URLconf (`django/views/generic/detail.py:SingleObjectMixin.get_object`).

Then it calls `get` on what is left. The `LIMIT 21` in the query is that method's own doing, not the view's (`django/db/models/query.py:QuerySet.get`). An object that does not exist raises the model's `Model.DoesNotExist`, and `get_object` raises `Http404` in its place, which the handler turns into a 404 ([How an exception becomes a response](../handlers/exceptions.md)):

```text recording=views
GET /articles/no-such-article/: the DetailView finds no object
...
            SingleObjectMixin.get_object()
              ...
              SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE "gazette_article"."slug" = %s LIMIT 21 with params ('no-such-article',)
              raises Http404
    response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
    ...
```

**The queryset.** `SingleObjectMixin.get_queryset` returns the `queryset` attribute if the class set one, and otherwise everything the `model` attribute's default manager has ([Managers](../models/managers.md)); with neither it raises `ImproperlyConfigured`. In both cases what it returns is the result of `all()`, a new queryset (`django/views/generic/detail.py:SingleObjectMixin.get_queryset`).

> **Trap.** A `queryset` written as a class attribute is one object, shared by every request the process serves. `get_queryset` gives each request a copy of it, made by `all()`, but code that evaluates the attribute itself, by iterating it or taking its length, fills the shared object's cache of rows, and every later request that evaluates it gets those rows in place of a query (`docs/ref/class-based-views/mixins-single-object.txt`, `django/db/models/query.py:QuerySet._fetch_all`).

**The context.** `SingleObjectMixin.get_context_data` puts the view's object, when it has one, in as `"object"`, and a second time under the name `get_context_object_name` returns, when it returns one: `context_object_name` if set, and otherwise, for a model instance, the model's name in lower case. So the Gazette's template can say `"article"` where a template written for any model would say `"object"` (`django/views/generic/detail.py:SingleObjectMixin.get_context_data`).

**The template.** With no `template_name`, `SingleObjectTemplateResponseMixin.get_template_names` builds a list. If `template_name_field` is set, the value of that field on the object goes first: the object names its own template. Then comes a name made from the object's model, or from the view's `model` when the object is not a model instance: the app label as a directory, and the model's name with `template_name_suffix`, which is `"_detail"`. If nothing could be built it raises `ImproperlyConfigured` again, with a message that lists what would have helped (`django/views/generic/detail.py:SingleObjectTemplateResponseMixin.get_template_names`).

## `ListView`: many objects, and pages of them

The Gazette lists its articles three to a page, newest first.

```python
# gazette/views.py
class ArticleList(ListView):
    model = Article
    paginate_by = 3
    ordering = "-published"
```

`BaseListView.get` keeps the queryset as `BaseListView.object_list`, makes the context and makes the response (`django/views/generic/list.py:BaseListView.get`). For the second page, `GET /articles/?page=2`, the rows are counted under `Paginator.page`, while the context is being made, since a page number cannot be validated without knowing how many rows there are (`django/core/paginator.py:Paginator.page`, `django/core/paginator.py:Paginator.count`). The rows themselves are fetched only under `SimpleTemplateResponse.render`, after the view has returned, by the template's own loop: what the view put in the context was a queryset limited to three rows and not yet run ([QuerySets](../querysets.md)):

```text recording=views
GET /articles/?page=2: a ListView that paginates
...
          BaseListView.get(request)
            MultipleObjectMixin.get_queryset
              MultipleObjectMixin.get_ordering  ->  '-published'
              -> a QuerySet of Article, ordered by -published, not yet fetched
            ...
            MultipleObjectMixin.get_context_data()
              MultipleObjectMixin.get_paginate_by(queryset)  ->  3
              MultipleObjectMixin.get_context_object_name(object_list)  ->  'article_list'
              MultipleObjectMixin.paginate_queryset(queryset, 3)
                ...
                Paginator.page(2)
                  SQL SELECT COUNT(*) AS "__count" FROM "gazette_article" with params ()
                  -> <Page 2 of 3>
                -> (a Paginator, <Page 2 of 3>, the page's objects: a QuerySet of Article, ordered by -published, not yet fetched, True)
              ContextMixin.get_context_data(paginator=..., page_obj=..., is_paginated=..., object_list=..., article_list=...)  ->  a dict with the keys article_list, is_paginated, object_list, page_obj, paginator, view
      ...
      SimpleTemplateResponse.render
        SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" ORDER BY "gazette_article"."published" DESC LIMIT 3 OFFSET 3 with params ()
        ...
```

**The queryset.** `MultipleObjectMixin.get_queryset` differs from the single-object one in two ways. The `queryset` attribute may be any iterable, a list for instance, and `all()` is called on it only when it is a `QuerySet`. And an ordering is applied at the end when there is one: `get_ordering` returns the `ordering` attribute, which is `None` unless it has been set to a field name or a sequence of them, and when it is set the queryset is passed through `order_by` (`django/views/generic/list.py:MultipleObjectMixin.get_queryset`).

**Pages.** `MultipleObjectMixin.get_context_data` works on the list `get` kept. A list passed to it as `object_list` takes that one's place, whereas its other keyword arguments are only laid over the context it builds. It asks `get_paginate_by` for a page size. If the answer is nothing, the whole list goes into the context as `"object_list"`, with `"paginator"` and `"page_obj"` as `None` and `"is_paginated"` false. Otherwise `paginate_queryset` takes over, and the context holds the paginator, the page as `"page_obj"`, the page's own objects as `"object_list"`, and `"is_paginated"`, which is true when there is more than one page (`django/views/generic/list.py:MultipleObjectMixin.get_context_data`). As in the detail view, the same objects are in the context a second time when `get_context_object_name` returns a name: `context_object_name` if set, and otherwise, for a list that has a model, the model's name with `"_list"` after it.

`paginate_queryset` makes a `Paginator` and looks for the page number under the name `page_kwarg`, which is `"page"`, first in the path's keyword arguments and then in the query string, taking 1 when neither gives one. A value that `int` refuses, other than the word `"last"`, is an `Http404`, and so is a number the paginator refuses (`django/views/generic/list.py:MultipleObjectMixin.paginate_queryset`). Page 9 of the Gazette's three is such a number: `Paginator.page` counts the rows and raises `EmptyPage`, and `paginate_queryset` raises `Http404` in its place:

```text recording=views
GET /articles/?page=9: a page the list does not have
...
                Paginator.page(9)
                  SQL SELECT COUNT(*) AS "__count" FROM "gazette_article" with params ()
                  raises EmptyPage
                raises Http404
    response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
    ...
```

**An empty list.** By default an empty list is rendered like any other. With `allow_empty` false, `BaseListView.get` raises `Http404` for one, and takes care how it finds out: when the view paginates and the list is a queryset, it asks `exists`, a cheap query, where otherwise it tests the list for truth, which loads a queryset whole (`django/views/generic/list.py:BaseListView.get`).

**The template.** `MultipleObjectTemplateResponseMixin.get_template_names` takes `template_name` if there is one and then, when the list has a model, adds a name built from it with the suffix `"_list"`. Unlike the detail view's, this one adds the generated name even when `template_name` was given, so the given name is tried first and the generated one stands behind it (`django/views/generic/list.py:MultipleObjectTemplateResponseMixin.get_template_names`).
