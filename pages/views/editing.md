---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The form views

`FormView`, `CreateView`, `UpdateView` and `DeleteView`: the generic views that show a form for a `"GET"` and act on it for a `"POST"`. They are assembled from `ProcessFormView`, which holds the cycle, `FormMixin`, which makes the form, `ModelFormMixin`, which ties a form to a model's object, and `DeletionMixin`.

A form on a web page is a conversation of at least two requests. The first asks for the page and gets an empty form. The second posts what was typed. If that fails validation, the same page goes back with the input still in it and the errors beside the fields, and the conversation goes round again. When it passes, the view does what the form was for and answers with a redirect, which in the words of Django's tutorial prevents data from being posted twice (`docs/intro/tutorial04.txt`).

Every view that handles a form goes through that cycle. For `FormView`, `CreateView` and `UpdateView` it is written once, in `ProcessFormView`, and mixins supply the decisions, as in [the display views](generic.md). `DeleteView` is put together without `ProcessFormView` and has the posting half written again for itself.

```text recording=views
FormView  ->  FormView > TemplateResponseMixin > BaseFormView > FormMixin > ContextMixin > ProcessFormView > View
CreateView  ->  CreateView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseCreateView > ModelFormMixin > FormMixin > SingleObjectMixin > ContextMixin > ProcessFormView > View
UpdateView  ->  UpdateView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseUpdateView > ModelFormMixin > FormMixin > SingleObjectMixin > ContextMixin > ProcessFormView > View
DeleteView  ->  DeleteView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseDeleteView > DeletionMixin > FormMixin > BaseDetailView > SingleObjectMixin > ContextMixin > View
```

## The cycle: `ProcessFormView`

`ProcessFormView` is the whole cycle and nothing else. Its `get` renders a context. Its `post` makes the form, asks whether it is valid, and calls `form_valid` or `form_invalid` with it. Its `put` calls `post` (`django/views/generic/edit.py:ProcessFormView`).

Every method that its `get` and `post` call belongs to some other class. `FormView` is the smallest working assembly: `FormMixin` to make the form, `ProcessFormView` for the cycle, `TemplateResponseMixin` to answer.

```text figure=form-flow
GET  /letters/
    ProcessFormView.get
        get_context_data
            get_form        a form with no data: not bound
        render_to_response  ->  200, the empty form

POST /letters/
    ProcessFormView.post
        get_form            a form holding request.POST and request.FILES: bound
        is_valid ?
            no   form_invalid   ->  200, the same page, the form with its errors and what was typed
            yes  form_valid     ->  302 to get_success_url()
```

*The two requests of a form view. A `"GET"` makes an unbound form and shows it. A `"POST"` makes a bound one and takes one of two ways out: back to the page, or on to a redirect.*

The Gazette takes letters to the editor. Its form wants a name and a letter of at least twenty characters, and its view adds one thing to what `FormView` does: it keeps the name from a valid form.

```python
# gazette/forms.py
class LetterForm(forms.Form):
    name = forms.CharField(max_length=60)
    letter = forms.CharField(min_length=20)

# gazette/views.py
class Letters(FormView):
    form_class = LetterForm
    template_name = "gazette/letters.html"
    success_url = reverse_lazy("thanks")

    def form_valid(self, form):
        RECEIVED.append(form.cleaned_data["name"])
        return super().form_valid(form)
```

This is the request that shows the form:

```text recording=views
ProcessFormView.get(request)
  FormMixin.get_context_data()
    FormMixin.get_form()
      FormMixin.get_form_class  ->  LetterForm
      FormMixin.get_form_kwargs
        FormMixin.get_initial  ->  {}
        FormMixin.get_prefix  ->  None
        -> a dict with the keys initial, prefix
      -> a LetterForm, not bound
    ContextMixin.get_context_data(form=...)  ->  a dict with the keys form, view
    -> a dict with the keys form, view
  TemplateResponseMixin.render_to_response(context)
    TemplateResponseMixin.get_template_names  ->  ['gazette/letters.html']
```

`get` asked for a context, and the form was made on the way, inside `get_context_data`. A letter that is too short goes round the cycle:

```text recording=views
      ProcessFormView.post(request)
        FormMixin.get_form()
          FormMixin.get_form_class  ->  LetterForm
          FormMixin.get_form_kwargs
            FormMixin.get_initial  ->  {}
            FormMixin.get_prefix  ->  None
            -> a dict with the keys data, files, initial, prefix
          -> a LetterForm, bound
        BaseForm.is_valid  ->  False
        FormMixin.form_invalid(form)
...
start_response("200 OK", headers)
the server sends the body: 'Please correct: letter\n'
```

The answer is a 200, not an error status: an invalid form is an ordinary page as far as HTTP is concerned. A letter the form accepts takes the other way out.

```text recording=views
        BaseForm.is_valid  ->  True
        Letters.form_valid(form)
          FormMixin.form_valid(form)
            FormMixin.get_success_url  ->  '/letters/thanks/'
            -> an HttpResponseRedirect, status 302, Location '/letters/thanks/'
          -> an HttpResponseRedirect, status 302, Location '/letters/thanks/'
        -> an HttpResponseRedirect, status 302, Location '/letters/thanks/'
      -> an HttpResponseRedirect, status 302, Location '/letters/thanks/'
    -> an HttpResponseRedirect, status 302, Location '/letters/thanks/'
start_response("302 Found", headers), with Location: /letters/thanks/
```

## Making the form: `FormMixin`

`FormMixin.get_form` calls a form class with keyword arguments. The arguments come from `get_form_kwargs`, and the class, unless the caller passes one, from `get_form_class`; both methods can be replaced (`django/views/generic/edit.py:FormMixin`).

`FormMixin.get_form_kwargs` is where the two requests of the cycle part. It always supplies `"initial"`, a copy of the `initial` attribute, and `"prefix"`. For a request whose method is `"POST"` or `"PUT"` it adds `"data"` and `"files"`, the request's `POST` and `FILES`, and a form given data is a bound form. The recordings above show it at that line: two keys for the `"GET"`, four for a `"POST"`.

> **A `"PUT"` posts nothing.** `ProcessFormView.put` runs the same code as `post`, and `get_form_kwargs` gives the form `HttpRequest.POST` for either method. But Django parses a request's body into `POST` only when the method is `"POST"`: for a `"PUT"` that dictionary is empty ([The body: `body`, `POST` and `FILES`](../http/body.md)). The form is bound to no data: a required field that looks for its value there finds none, and the form is invalid.

`FormMixin.get_context_data` adds the form to the context under `"form"`, making it if the caller did not pass one. That is why a `"GET"` never calls `get_form` itself, and why `form_invalid`, which already has the bound form in hand, passes it along: the page is rendered with the form that failed, and not with a fresh one.

`FormMixin.form_valid` does nothing with the form. It redirects to `get_success_url`, which returns the `success_url` attribute as a string, or raises `ImproperlyConfigured` when there is none. Whatever the form was for is the subclass's to add, in a `form_valid` of its own that then calls `super()`, as the Gazette's does. The attribute is passed through `str` because, in the words of the comment beside it, it may be lazy. A class attribute is evaluated when the views module is imported, too early for `reverse`, so a success URL given by a pattern's name is written with `reverse_lazy` ([Reversing a name](../urls/reversing.md#reverse_lazy)).

## A model's form: `ModelFormMixin`

`CreateView` and `UpdateView` edit an object of a model through a `ModelForm`. `ModelFormMixin` inherits from both `FormMixin` and `SingleObjectMixin`, and adds to the first what the second knows: which model, and which object (`django/views/generic/edit.py:ModelFormMixin`).

```python
# gazette/views.py
class ArticleCreate(CreateView):
    model = Article
    fields = ["slug", "headline", "published"]


class ArticleUpdate(UpdateView):
    model = Article
    fields = ["headline"]
```

**The form class** need not be written. `ModelFormMixin.get_form_class` returns `form_class` when the view has one. Otherwise it finds a model, from the `model` attribute, or the class of the object being edited, or the queryset, and calls `modelform_factory` with it and the view's `fields`. A view with neither a form class nor `fields` raises `ImproperlyConfigured`, and so does one with both. The factory makes a new class at each call, so a view that relies on it builds a form class for every request.

**The object** reaches the form as `"instance"`, which `ModelFormMixin.get_form_kwargs` adds to what `FormMixin` supplied whenever the view has an attribute `object`. The two base views differ only in what they put there before the cycle starts. `BaseCreateView` sets it to `None` in both handler methods, and the form makes a new object. `BaseUpdateView` sets it to what `get_object` finds, by the same lookup a `DetailView` uses ([The generic views](generic.md#detailview-one-object)).

**A valid form** is saved. `ModelFormMixin.form_valid` calls the form's `save`, keeps what it returns as the view's `object`, and goes on to `FormMixin.form_valid` for the redirect. `ModelFormMixin.get_success_url` looks in two places for the address. A `success_url` is filled in from the object's attributes with `str.format`, so that it may be written `"/articles/{slug}/"`. Without one, the object's own `get_absolute_url` is called.

```text recording=views
      BaseCreateView.post(request)
        ProcessFormView.post(request)
          FormMixin.get_form()
            ModelFormMixin.get_form_class
              modelform_factory(Article, fields=['slug', 'headline', 'published'])  ->  the class ArticleForm
              -> ArticleForm
            ModelFormMixin.get_form_kwargs
              FormMixin.get_form_kwargs
                FormMixin.get_initial  ->  {}
                FormMixin.get_prefix  ->  None
                -> a dict with the keys data, files, initial, prefix
              -> a dict with the keys data, files, initial, instance, prefix
            -> an ArticleForm, bound
          BaseForm.is_valid
            SQL SELECT %s AS "a" FROM "gazette_article" WHERE "gazette_article"."slug" = %s LIMIT 1 with params (1, 'regatta')
            -> True
          ModelFormMixin.form_valid(form)
            BaseModelForm.save
              SQL INSERT INTO "gazette_article" ("slug", "headline", "published") VALUES (%s, %s, %s) RETURNING "gazette_article"."id" with params ('regatta', 'Regatta results', '2026-04-05 17:00:00')
              -> <Article: Regatta results>
            FormMixin.form_valid(form)
              ModelFormMixin.get_success_url
                Article.get_absolute_url  ->  '/articles/regatta/'
                -> '/articles/regatta/'
              -> an HttpResponseRedirect, status 302, Location '/articles/regatta/'
            -> an HttpResponseRedirect, status 302, Location '/articles/regatta/'
          -> an HttpResponseRedirect, status 302, Location '/articles/regatta/'
        -> an HttpResponseRedirect, status 302, Location '/articles/regatta/'
      -> an HttpResponseRedirect, status 302, Location '/articles/regatta/'
    -> an HttpResponseRedirect, status 302, Location '/articles/regatta/'
start_response("302 Found", headers), with Location: /articles/regatta/
```

There are two queries, one for validation and one for saving. Validation checked that no other article has the slug, and `save` inserted the row. An `UpdateView` begins by finding its object, and the rest of its cycle runs the same methods with that object as the form's instance. These are two of the places where its recording differs, the beginning and the query `save` sends. The others come from the Gazette's own `fields`: its update view has only the headline, so the factory is given one field, and validation has no slug to check and runs no query.

```text recording=views
BaseUpdateView.post(request, slug='regatta')
  SingleObjectMixin.get_object()
    SingleObjectMixin.get_queryset  ->  a QuerySet of Article, not yet fetched
    SingleObjectMixin.get_slug_field  ->  'slug'
    SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE "gazette_article"."slug" = %s LIMIT 21 with params ('regatta',)
    -> <Article: Regatta results>
  ProcessFormView.post(request, slug='regatta')
...
      BaseModelForm.save
        SQL UPDATE "gazette_article" SET "slug" = %s, "headline" = %s, "published" = %s WHERE "gazette_article"."id" = %s with params ('regatta', 'Regatta results, corrected', '2026-04-05 17:00:00', 9)
        -> <Article: Regatta results, corrected>
```

Both views get their template name from `SingleObjectTemplateResponseMixin` with a suffix of `"_form"`, so one template serves for making an article and for changing it.

## `DeleteView`

Deleting has the same shape seen from the browser: a page that asks, and a post that acts. `BaseDeleteView` builds it from three parents, `DeletionMixin`, `FormMixin` and `BaseDetailView`, without `ProcessFormView`, and sets `form_class` to `Form`, a form with no fields, which is valid whenever it is bound (`django/views/generic/edit.py:BaseDeleteView`).

```python
# gazette/views.py
class ArticleDelete(DeleteView):
    model = Article
    success_url = reverse_lazy("articles")
```

```text recording=views
DeleteView: which class supplies each method
    get  ->  BaseDetailView
    post  ->  BaseDeleteView
    delete  ->  DeletionMixin
    get_object  ->  SingleObjectMixin
    get_form  ->  FormMixin
    get_form_class  ->  FormMixin
    form_valid  ->  BaseDeleteView
    form_invalid  ->  FormMixin
    get_success_url  ->  DeletionMixin
    get_context_data  ->  FormMixin
    get_template_names  ->  SingleObjectTemplateResponseMixin
```

A `"GET"` is answered by the detail view's `get`: the object is found and a page rendered, from a template with the suffix `"_confirm_delete"`. A `"POST"` is answered by `BaseDeleteView.post`, which finds the object and goes through the posting half of the cycle itself, and `BaseDeleteView.form_valid` deletes it.

```text recording=views
      BaseDeleteView.post(request, slug='lost-cat')
        SingleObjectMixin.get_object()
          SingleObjectMixin.get_queryset  ->  a QuerySet of Article, not yet fetched
          SingleObjectMixin.get_slug_field  ->  'slug'
          SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE "gazette_article"."slug" = %s LIMIT 21 with params ('lost-cat',)
          -> <Article: Lost: a grey cat, Quay Street>
        FormMixin.get_form()
          FormMixin.get_form_class  ->  Form
          FormMixin.get_form_kwargs
            FormMixin.get_initial  ->  {}
            FormMixin.get_prefix  ->  None
            -> a dict with the keys data, files, initial, prefix
          -> a Form, bound
        BaseForm.is_valid  ->  True
        BaseDeleteView.form_valid(form)
          DeletionMixin.get_success_url  ->  '/articles/'
          Model.delete
            SQL DELETE FROM "gazette_article" WHERE "gazette_article"."id" IN (%s) with params (1,)
          -> an HttpResponseRedirect, status 302, Location '/articles/'
        -> an HttpResponseRedirect, status 302, Location '/articles/'
      -> an HttpResponseRedirect, status 302, Location '/articles/'
    -> an HttpResponseRedirect, status 302, Location '/articles/'
start_response("302 Found", headers), with Location: /articles/
```

`form_valid` gets the success URL first and deletes second. `DeletionMixin.get_success_url` fills the `success_url` in from the object's attributes, as the model form's does, and it reads them while the object is still in the database. There is no falling back to `get_absolute_url` here: a view without a `success_url` raises `ImproperlyConfigured`.

> **Changed in 4.0.** `DeleteView` has used `FormMixin` since Django 4.0, whose release notes give the reasons: a project can supply a form of its own, with a checkbox for instance, to confirm the deletion, and the view works with a mixin that reports success. Before that the deleting was done in `delete`, and the notes say to move any custom logic from there to `form_valid`, or to a helper method the two share (`docs/releases/4.0.txt`).

`DeletionMixin.delete` is still there, and `View.dispatch` still routes to it, because `"delete"` is one of the names in `http_method_names`. A request with the method `"DELETE"` goes to it directly:

```text recording=views
    View.dispatch(request, slug='found-cat')
      DeletionMixin.delete(request, slug='found-cat')
        SingleObjectMixin.get_object()
          SingleObjectMixin.get_queryset  ->  a QuerySet of Article, not yet fetched
          SingleObjectMixin.get_slug_field  ->  'slug'
          SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE "gazette_article"."slug" = %s LIMIT 21 with params ('found-cat',)
          -> <Article: Found: a grey cat>
        DeletionMixin.get_success_url  ->  '/articles/'
        Model.delete
          SQL DELETE FROM "gazette_article" WHERE "gazette_article"."id" IN (%s) with params (2,)
        -> an HttpResponseRedirect, status 302, Location '/articles/'
      -> an HttpResponseRedirect, status 302, Location '/articles/'
    -> an HttpResponseRedirect, status 302, Location '/articles/'
start_response("302 Found", headers), with Location: /articles/
```

No form was made. `DeletionMixin.delete` finds the object, deletes it and redirects, so a confirmation form guards the `"POST"` and not the `"DELETE"` (`django/views/generic/edit.py:DeletionMixin.delete`).
