---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The form views

The form views are the generic views that show a form for a `"GET"` and act on what is posted: `FormView`, `CreateView`, `UpdateView` and `DeleteView`. A form that passes goes to `form_valid`, where the view does what the form is for and redirects, to `success_url` or to the object's own address; one that fails goes to `form_invalid`, and the page is shown again with its errors.

A form on a web page is a conversation of at least two requests. The first asks for the page and gets the form. The second posts what was typed. If that fails validation, the same page goes back with the input still in it and the errors beside the fields, and the conversation goes round again. When it passes, the view does what the form was for and answers with a redirect, which keeps the data from being posted twice if the reader presses the Back button (`docs/intro/tutorial04.txt`).

Every generic view that handles a form goes through that cycle. For `FormView`, `CreateView` and `UpdateView` it is written once, in `ProcessFormView`, and mixins supply the decisions, as in `DetailView` and `ListView` ([The generic views](generic.md)). `DeleteView` is put together without `ProcessFormView` and has the posting half written again for itself. Each line below is one view's method resolution order, ending at `View` because `object`, which follows it in every order, is left out. `ProcessFormView` stands just before `View` in the first three, and nowhere in the fourth:

```text recording=views
The method resolution order of each generic view, without object, the last of each
...
    FormView  ->  FormView > TemplateResponseMixin > BaseFormView > FormMixin > ContextMixin > ProcessFormView > View
    CreateView  ->  CreateView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseCreateView > ModelFormMixin > FormMixin > SingleObjectMixin > ContextMixin > ProcessFormView > View
    UpdateView  ->  UpdateView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseUpdateView > ModelFormMixin > FormMixin > SingleObjectMixin > ContextMixin > ProcessFormView > View
    DeleteView  ->  DeleteView > SingleObjectTemplateResponseMixin > TemplateResponseMixin > BaseDeleteView > DeletionMixin > FormMixin > BaseDetailView > SingleObjectMixin > ContextMixin > View
    ...
```

## The cycle: `ProcessFormView`

`ProcessFormView` is the whole cycle and nothing else. Its `get` hands a context to `render_to_response`. Its `post` makes the form, asks whether it is valid, and calls `form_valid` or `form_invalid` with it. Its `put` calls `post` (`django/views/generic/edit.py:ProcessFormView`).

Every method that its `get` and `post` call belongs to some other class. `FormView` is the smallest working assembly: `FormMixin` to make the form, `ProcessFormView` for the cycle, `TemplateResponseMixin` to answer. The figure draws the cycle through `ProcessFormView`'s `get` and `post`: where each makes its form, and the two ways out of the `"POST"`, one of them back to the page and the next `"POST"`.

```text figure=form-flow
GET
    ProcessFormView.get
        get_context_data
            get_form            a form with no data: not bound
        render_to_response      ->  200, the page, with the form

the reader fills the form in, and the browser posts it

POST
    ProcessFormView.post
        get_form                a form holding request.POST and request.FILES: bound
        is_valid ?
            no   form_invalid   ->  200, the page again, the form with its errors and what was typed
                                    the reader corrects it, and the browser posts it again: back to POST
            yes  form_valid     ->  302, to the address get_success_url gives
```

*The cycle that `ProcessFormView` holds, a `"GET"` and then as many `"POST"` requests as it takes. The way back from `form_invalid` leads to the next `"POST"`; the way on from `form_valid`, a redirect, ends the cycle.*

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

For the empty page `ProcessFormView.get` asks only for a context, and the form is made on the way, inside `FormMixin.get_context_data`: from two keyword arguments, and not bound. The context holds it under `"form"`, beside `"view"`.

```text recording=views
GET /letters/: a FormView shows its form
...
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
            ...
```

When a letter that is too short is posted, the form is made again, from four keyword arguments now, `"data"` and `"files"` among them: it is bound, it fails, and `form_invalid` hands it to `get_context_data` for the page.

```text recording=views
POST /letters/ with a letter that is too short: the form is not valid
...
          ProcessFormView.post(request)
            FormMixin.get_form()
              FormMixin.get_form_class  ->  LetterForm
              FormMixin.get_form_kwargs
                ...
                -> a dict with the keys data, files, initial, prefix
              -> a LetterForm, bound
            BaseForm.is_valid  ->  False
            FormMixin.form_invalid(form)
              FormMixin.get_context_data(form=...)
    ...
    start_response("200 OK", headers)
    the server sends the body: 'Please correct: letter\n'
```

The answer is a 200, not an error status: an invalid form is an ordinary page as far as HTTP is concerned. A letter the form accepts takes the other way out, through the view's own `form_valid`, which keeps the name, to `FormMixin.form_valid`, which makes the redirect.

```text recording=views
POST /letters/ with a letter the form accepts
...
          ProcessFormView.post(request)
            ...
            BaseForm.is_valid  ->  True
            Letters.form_valid(form)
              FormMixin.form_valid(form)
                FormMixin.get_success_url  ->  '/letters/thanks/'
                -> an HttpResponseRedirect, status 302, Location '/letters/thanks/'
    ...
    start_response("302 Found", headers), with Location: /letters/thanks/
    ...
```

## Making the form: `FormMixin`

`FormMixin.get_form` calls a form class with keyword arguments. The arguments come from `get_form_kwargs`, and the class, unless the caller passes one, from `get_form_class`; both methods can be replaced (`django/views/generic/edit.py:FormMixin`).

`FormMixin.get_form_kwargs` is where the two requests of the cycle differ. It always supplies `"initial"`, a copy of the `initial` attribute, and `"prefix"`. For a request whose method is `"POST"` or `"PUT"` it adds `"data"` and `"files"`, the request's `POST` and `FILES`, and a form given data is a bound form.

> **Trap.** A `"PUT"` posts nothing. `ProcessFormView.put` calls `post`, and `get_form_kwargs` gives the form the request's `POST` for either method; but Django parses a request's body into `POST` only when the method is `"POST"`, and for a `"PUT"` that dictionary is empty ([The body: `body`, `POST` and `FILES`](../http/body.md)). The form is bound to no data: a required field that looks for its value there finds none, and the form is invalid. Sent the body of a letter the form accepts with the method `"PUT"`, the Gazette's page binds its form to a `QueryDict` with no keys, and `form_invalid` answers 200, asking for both fields (`django/views/generic/edit.py:ProcessFormView.put`, `django/http/request.py:HttpRequest._load_post_and_files`).

`FormMixin.get_context_data` adds the form to the context under `"form"`, making it if the caller did not pass one. That is why a `"GET"` never calls `get_form` itself, and why `form_invalid`, which already has the bound form in hand, passes it along: the page is rendered with the form that failed, and not with a fresh one.

`FormMixin.form_valid` does nothing with the form. It redirects to what `get_success_url` returns, and `FormMixin.get_success_url` returns the `success_url` attribute as a string, or raises `ImproperlyConfigured` when there is none. Whatever the form was for is the subclass's to add, in a `form_valid` of its own that then calls `super()`, as the Gazette's does. `get_success_url` passes the attribute through `str` because it may be lazy: a class attribute is evaluated when the views module is imported, ordinarily too early for `reverse`, so a success URL given by a pattern's name is written with `reverse_lazy` ([Reversing a name](../urls/reversing.md#reverse_lazy)) (`django/views/generic/edit.py:FormMixin.get_success_url`).

## A model's form: `ModelFormMixin`

`CreateView` and `UpdateView` edit an object of a model through a `ModelForm`. `ModelFormMixin` inherits from both `FormMixin` and `SingleObjectMixin`, and adds to the first what the second knows: which model, and which object (`django/views/generic/edit.py:ModelFormMixin`).

**The form class** need not be written. `ModelFormMixin.get_form_class` returns `form_class` when the view has one. Otherwise it finds a model, from the `model` attribute, or the class of the object being edited, or the queryset, and calls `modelform_factory` with it and the view's `fields`. A view with neither a form class nor `fields` raises `ImproperlyConfigured`, and so does one with both. The factory makes a new class at each call, so a view that relies on it builds a form class each time it makes a form (`django/views/generic/edit.py:ModelFormMixin.get_form_class`, `django/forms/models.py:modelform_factory`).

**The object** reaches the form as `"instance"`, which `ModelFormMixin.get_form_kwargs` adds to what `FormMixin` supplied whenever the view has an attribute `object` (`django/views/generic/edit.py:ModelFormMixin.get_form_kwargs`). The two base views differ only in what they put there before the cycle starts (`django/views/generic/edit.py:BaseCreateView`, `django/views/generic/edit.py:BaseUpdateView`). `BaseCreateView` sets it to `None` in both handler methods, and the form makes a new object. `BaseUpdateView` sets it to what `get_object` finds, by the same lookup a `DetailView` uses ([`DetailView` and `ListView`](display.md#detailview-one-object)).

**A valid form** is saved. `ModelFormMixin.form_valid` calls the form's `save`, keeps what it returns as the view's `object`, and goes on to `FormMixin.form_valid` for the redirect. `ModelFormMixin.get_success_url` looks in two places for the address. A `success_url` is filled in from the object's attributes with `str.format`, so that it may be written `"/articles/{slug}/"`. Without one, the object's own `get_absolute_url` is called (`django/views/generic/edit.py:ModelFormMixin.get_success_url`).

The Gazette's two views of articles name a model and its fields, and neither a form class nor a success URL:

```python
# gazette/views.py
class ArticleCreate(CreateView):
    model = Article
    fields = ["slug", "headline", "published"]


class ArticleUpdate(UpdateView):
    model = Article
    fields = ["headline"]
```

In the create view's `"POST"`, look for the class the factory makes, `"instance"` among the form's keyword arguments, a query under `is_valid` and another under `save`, and the address that `get_absolute_url` gives.

```text recording=views
POST /articles/new/: a CreateView saves a new object
...
          BaseCreateView.post(request)
            ProcessFormView.post(request)
              FormMixin.get_form()
                ModelFormMixin.get_form_class
                  modelform_factory(Article, fields=['slug', 'headline', 'published'])  ->  the class ArticleForm
                  -> ArticleForm
                ModelFormMixin.get_form_kwargs
                  ...
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
                  ...
```

Here validation sends a query because an article's slug is unique: it checks that no other article has the slug before `save` inserts the row (`django/forms/models.py:BaseModelForm.validate_unique`, `django/db/models/base.py:Model._perform_unique_checks`). An `UpdateView`'s `"POST"` begins by finding its object, and the rest of its cycle runs the same methods with that object as the form's instance, so that `save` sends an UPDATE where the create view's sent an INSERT.

```text recording=views
POST /articles/regatta/edit/: an UpdateView saves the object
...
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
                  ...
```

Both views get their template name from `SingleObjectTemplateResponseMixin` with a suffix of `"_form"`, so one template serves for making an article and for changing it (`django/views/generic/detail.py:SingleObjectTemplateResponseMixin.get_template_names`).

## `DeleteView`

A `DeleteView` has the same shape seen from the browser: a page that asks, and a post that acts. `BaseDeleteView` builds it from three parents, `DeletionMixin`, `FormMixin` and `BaseDetailView`, without `ProcessFormView`, and sets `form_class` to `Form`, a form with no fields, which is valid whenever it is bound (`django/views/generic/edit.py:BaseDeleteView`). For deleting an article the Gazette names only a model and a `success_url`:

```python
# gazette/views.py
class ArticleDelete(DeleteView):
    model = Article
    success_url = reverse_lazy("articles")
```

A `"GET"` is answered by `BaseDetailView.get`: the object is found and a page rendered, from a template with the suffix `"_confirm_delete"`. A `"POST"` is answered by `BaseDeleteView.post`, which finds the object and then does in its own code what `ProcessFormView.post` does: it makes the form, validates it, and calls `form_valid` or `form_invalid`. `BaseDeleteView.form_valid` deletes the object; `delete` is still `DeletionMixin`'s:

```text recording=views
DeleteView: which class supplies each method
    get  ->  BaseDetailView
    post  ->  BaseDeleteView
    delete  ->  DeletionMixin
    ...
    form_valid  ->  BaseDeleteView
    ...
    get_success_url  ->  DeletionMixin
    ...
```

The `"POST"` makes the plain `Form`, which is valid as soon as it is bound, and its `form_valid` asks for the success URL before it deletes.

```text recording=views
POST /articles/lost-cat/delete/: a DeleteView deletes through its form
...
          BaseDeleteView.post(request, slug='lost-cat')
            SingleObjectMixin.get_object()
            ...
            FormMixin.get_form()
              FormMixin.get_form_class  ->  Form
              ...
              -> a Form, bound
            BaseForm.is_valid  ->  True
            BaseDeleteView.form_valid(form)
              DeletionMixin.get_success_url  ->  '/articles/'
              Model.delete
                SQL DELETE FROM "gazette_article" WHERE "gazette_article"."id" IN (%s) with params (1,)
              -> an HttpResponseRedirect, status 302, Location '/articles/'
              ...
```

`DeletionMixin.get_success_url` fills the `success_url` in from the object's attributes, as `ModelFormMixin`'s does, and it reads them while the object is still in the database. There is no falling back to `get_absolute_url` here: a view without a `success_url` raises `ImproperlyConfigured` (`django/views/generic/edit.py:DeletionMixin.get_success_url`).

> **History.** Until Django 4.0 `DeleteView` had no form, and a `"POST"` deleted the object in `delete`: `DeletionMixin.post`, which hands a `"POST"` to `delete`, is still declared, with `BaseDeleteView.post` now before it in the method resolution order. 4.0 put `FormMixin` among the view's bases, so that a project can supply a form of its own, with a checkbox for instance, to confirm the deletion, and so that the view works with `SuccessMessageMixin`, which adds its message in `form_valid`. The deleting moved to `form_valid`, and the release notes asked for any logic a project had written in `delete` to move there too, or to a helper method the two share (`docs/releases/4.0.txt`, `django/views/generic/edit.py:DeletionMixin.post`).

`DeletionMixin.delete` is still there, and `View.dispatch` still routes to it, because `"delete"` is one of the names in `http_method_names`. A request with the method `"DELETE"` goes to it directly, and no form is made between finding the object and deleting it:

```text recording=views
DELETE /articles/found-cat/delete/: the same view, by the method DELETE
...
          DeletionMixin.delete(request, slug='found-cat')
            SingleObjectMixin.get_object()
              ...
              -> <Article: Found: a grey cat>
            DeletionMixin.get_success_url  ->  '/articles/'
            Model.delete
              SQL DELETE FROM "gazette_article" WHERE "gazette_article"."id" IN (%s) with params (2,)
            -> an HttpResponseRedirect, status 302, Location '/articles/'
            ...
```

> **Trap.** A form that confirms the deletion guards the `"POST"` only. A `"DELETE"` never reaches it: `DeletionMixin.delete` deletes without making a form, so a `form_class` that asks for a box to be ticked is never consulted (`django/views/generic/edit.py:DeletionMixin.delete`, `django/views/generic/base.py:View.dispatch`).
