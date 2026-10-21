---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The design philosophies, in the code

Django's design philosophies are a page of its documentation naming the principles it is built by: loose coupling, less code, quick development, don't repeat yourself, explicit over implicit, consistency, and principles of their own for the models, the database API, URLs, templates, views and the cache (`docs/misc/design-philosophies.txt`). Most are kept by a mechanism in the source, and in places the code bends one.

## Model, template and view

Django's names for its parts are not those of the pattern called MVC, and its FAQ says why. In Django's reading a "view" describes "which data you see, not how you see it", so a view is the Python function called for a URL; how the data looks is the template's; and the controller is "probably the framework itself: the machinery that sends a request to the appropriate view, according to the Django URL configuration". So model, template and view: "MTV" (`docs/faq/general.txt`). In the code that machinery is the handler, whose centre resolves the path and calls the view (`django/core/handlers/base.py:BaseHandler._get_response`; [Handlers and middleware](../handlers.md)).

## Loose coupling, read in the imports

The design philosophies want the layers not to "know" about each other "unless absolutely necessary", and give three examples. The imports bear each out, and each has its exception.

"The template system knows nothing about web requests." The engine, the lexer, the parser and the context import nothing from `django/http/`; the bridge does, `SimpleTemplateResponse`, an `HttpResponse` that renders a template (`django/template/response.py:SimpleTemplateResponse`), as does the `querystring` tag (`django/template/defaulttags.py:querystring`). A request reaches templates all the same, without an import: `RequestContext` holds one and hands it to every context processor, a callable that returns variables for the template from the request (`django/template/context.py:RequestContext`).

"The database layer knows nothing about data display." `django/db/` imports nothing from the template system, `django/http/` or the views, but its model fields import `django.forms`, so that each can make its own form field (`django/db/models/fields/__init__.py:Field.formfield`).

"The view system doesn't care which template system a programmer uses." The `render` shortcut and `TemplateResponse` ask each engine in `TEMPLATES` in turn unless given one, so a view works the same over a Jinja2 backend (`django/template/loader.py:get_template`). Some of Django's own pages are the exception, among them the debug pages and the fallback when no `"404.html"` is found: each is rendered by an `Engine` made in the code, in the Django template language whatever `TEMPLATES` names (`django/views/debug.py:DEBUG_ENGINE`, `django/views/defaults.py:page_not_found`).

Which part imports which is [The parts of Django, and what each leans on](parts.md).

## The model as the one place

"Don't repeat yourself" asks that "every distinct concept and/or piece of data should live in one, and only one, place", and "less code" that Django use "Python's dynamic capabilities, such as introspection". A model is a class statement, and `ModelBase.__new__` reads it: it collects the fields, reads the inner `Meta`, and builds the `Options` kept as `Model._meta` (`django/db/models/base.py:ModelBase.__new__`). What else needs the model derives from `_meta`. A `ModelForm` gets its fields by asking each model field it takes for its form field (`django/forms/models.py:fields_for_model`), and the admin does the same through a hook of its own (`django/contrib/admin/options.py:BaseModelAdmin.formfield_for_dbfield`): a registered model has an editing interface without a line of form code, which is "quick development".

The schema is written twice, which bends "don't repeat yourself", but the second time by a program: makemigrations compares the models with the state the existing migration files describe and writes the difference as new files (`django/db/migrations/autodetector.py:MigrationAutodetector`), so the second copy is a history of the models' changes.

The design philosophies' models section adds Active Record, Martin Fowler's pattern of an object that wraps a row: a model "should encapsulate every aspect of an 'object'". An instance holds its row's values as attributes and writes itself with `Model.save`; its class holds the human-readable name and the default ordering in `Meta` (`django/db/models/options.py:Options`; [Models and fields](../models.md)).

## Explicit, and the names Django supplies

"Explicit is better than implicit" is Python's, and the design philosophies read it as "Django shouldn't do too much 'magic.'" For models they say a field should not assume behaviours "based solely on the name of the field". Nor does a field: whether a field is the primary key, may be null or must be unique is given to it as an argument (`django/db/models/fields/__init__.py:Field.__init__`).

Explicitness is held less strictly the other way: Django gives a model names it did not declare. A model that declares no primary key, and has no parent to take one from, is given a field called `"id"`, of the class `DEFAULT_AUTO_FIELD` names unless its application's `AppConfig.default_auto_field` names another (`django/db/models/options.py:Options._prepare`). One that has no manager, its own or inherited, is given a manager called `"objects"` (`django/db/models/base.py:ModelBase._prepare`). A field with choices gives its model a method named after the field, get_status_display for a field called status (`django/db/models/fields/__init__.py:Field.contribute_to_class`). A foreign key puts on the model at its other end an accessor named after the first model, with "_set" after it (`django/db/models/fields/reverse_related.py:ForeignObjectRel.get_accessor_name`). Each gives way to a declaration: a primary key, a manager, a method of that name, a `related_name`.

The documentation calls one mechanism "black magic": to record which templates a view rendered, the test environment replaces `Template._render` with a function that sends `template_rendered` (`django/test/utils.py:setup_test_environment`), a patching that "only happens during test running" (`docs/topics/testing/tools.txt`).

> **History.** Django 0.95, released in July 2006, merged a branch called magic-removal, "a major refactoring of both the internals and public APIs of Django's object-relational mapper" (`docs/internals/git.txt`). With 0.95, an application's models stayed in the module that defined them, where before they were "magically transferred" into one namespace of Django's, and a model overrode `Model.save` and `Model.delete` where before it hooked into methods called pre_save and post_save (`docs/releases/0.95.txt`). [The first decade: from a newsroom to 1.8](../changes/first-decade.md) tells the story.

## The database API

"SQL efficiency" asks that statements run "as few times as possible". Setting an attribute changes only the instance; nothing is written until `Model.save` is called, "rather than the framework saving things behind the scenes silently" (`django/db/models/base.py:Model.save`). A queryset sends nothing while it is built, runs its query when its results are first needed, and keeps them (`django/db/models/query.py:QuerySet._fetch_all`; [QuerySets](../querysets.md)).

Reading a foreign key whose object is not loaded sends a query for that one object, so a loop that reads it from many instances sends a query for each (`django/db/models/fields/related_descriptors.py:ForwardManyToOneDescriptor.__get__`). That is `FETCH_ONE`, the default **fetch mode**: the rule a queryset gives its instances for reading a field they have not loaded. Another, `FETCH_PEERS`, the "optional performance booster" of "SQL efficiency", fetches the object for every instance the same queryset produced, in one query; an object that `QuerySet.select_related` or `QuerySet.prefetch_related` has loaded needs no fetch (`django/db/models/fetch_modes.py`; [Deferred fields and the fetch modes](../instance/fetching.md)).

"Terse, powerful syntax": the double underscores of a keyword argument name a path through relations, as groups__name in a filter of `User` runs through a user's groups to their names, and `Query.setup_joins` turns the path into joins (`django/db/models/sql/query.py:Query.setup_joins`). The API should also "not rely on importing other modules or helper objects", and keyword arguments need none; but `Q`, for conditions joined by OR in one filter, and `F`, for one column compared with another, are helper objects imported from `django.db.models`.

The "option to drop into raw SQL easily" is a call away: `QuerySet.raw` maps the rows of an SQL query onto instances (`django/db/models/query.py:QuerySet.raw`), `RawSQL` puts a fragment in an expression, and the connection's cursor runs anything (`django/db/backends/base/base.py:BaseDatabaseWrapper.cursor`).

## URLs

URLs should not be "coupled to the underlying Python code". A URLconf maps a route to a callable, and code that needs a URL can ask for it by the pattern's name: `reverse` walks the resolver back from the name to a path (`django/urls/base.py:reverse`; [URL routing](../urls.md)). `include` lets a pattern mount an application's patterns under any prefix (`django/urls/conf.py:_path`).

"Definitive URLs" asks Django to "normalize" URLs, since search-engine robots would treat a path with and without a trailing slash as separate pages. Its answer is the `APPEND_SLASH` setting: when a path without a trailing slash matches no pattern and has produced a 404, and the path with one would resolve to a view not marked `no_append_slash`, `CommonMiddleware` redirects to it (`django/middleware/common.py:CommonMiddleware.should_redirect_with_slash`).

## The template system

"Separate logic from presentation": a template is not Python and cannot run it. The lexer splits it into text, variables, tags and comments (`django/template/base.py:Lexer.tokenize`; [Templates](../templates.md)); a tag is a name looked up among the registered libraries; a variable is a dotted path, and a callable met on the path is never given arguments: a template can call `BaseManager.all` (`django/template/base.py:Variable._resolve_lookup`).

"Safety and security" asks that a template be unable to run "commands that delete database records". The guard is in the same method: a callable whose attribute `"alters_data"` is true is not called, and renders as the engine's `string_if_invalid`. The database layer sets the flag on its own writes, among them `Model.save`, `QuerySet.delete`, `QuerySet.update` and the related managers', and the mixin `AltersData` carries it onto a subclass's override (`django/db/models/utils.py:AltersData`). Reading is allowed: a `{% for %}` over a queryset takes its length, which runs the query (`django/template/defaulttags.py:ForNode.render`).

Inheritance, against redundancy, is `{% extends %}` (`django/template/loader_tags.py:ExtendsNode`). Custom tags and filters, the "extensibility", are Python registered in a `Library` (`django/template/library.py:Library`). "Be decoupled from HTML" is half kept: the engine renders any text, but its autoescaping, on by default, is HTML's, so a `"<"` in a value comes out as an entity unless the value is marked safe or autoescaping is turned off (`django/template/base.py:render_value_in_context`).

## Views and the request

"Writing a view should be as simple as writing a Python function", and a view is any callable that takes a request and returns a response. A class-based view enters the URLconf as the function `View.as_view` returns, which makes an instance for each request and calls `View.dispatch` (`django/views/generic/base.py:View.as_view`; [Views](../views.md)). The request is an argument, not a global, so a test can build one with `RequestFactory` and call a view directly (`django/test/client.py:RequestFactory`). What Django sets for each request is another matter: the active language if `MIDDLEWARE` has `LocaleMiddleware`, the URLconf and the **script prefix**, the path at which the project is mounted, are kept in state local to the thread or task serving it and read by `gettext` and `reverse` without the request (`django/urls/base.py:set_urlconf`, `django/utils/translation/trans_real.py:activate`).

"GET and POST are distinct." `GET` is the parsed query string, whatever the method; `POST` is the parsed form body of a "POST" request and empty for any other method (`django/http/request.py:HttpRequest._load_post_and_files`). `View.dispatch` sends each method in `View.http_method_names` to the view's method of that name in lower case, and `require_http_methods` answers a method not listed with a 405 (`django/views/decorators/http.py:require_http_methods`).

## The cache

The cache's "less code" asks that the framework's code around a backend be kept "to the absolute minimum, especially for `get()` operations". `cache` is a proxy that hands each attribute to the backend of the default alias, so its `get` is the backend's own method, not a wrapper (`django/utils/connection.py:ConnectionProxy`). Nor does the base class wrap it: `BaseCache.get` only raises `NotImplementedError`, and the local-memory backend's makes the key and reads its store (`django/core/cache/backends/locmem.py:LocMemCache.get`; [Caching, files, mail, signals and tasks](../services.md)). Consistency is that every backend Django ships is a `BaseCache` (`django/core/cache/backends/base.py:BaseCache`); extensibility, that `"KEY_FUNCTION"` replaces the function that makes a key (`django/core/cache/backends/base.py:get_key_func`). The same consistency, a base class and a backend named in a setting, runs through the database, mail, storage and sessions: [How Django is extended](extension-points.md).
