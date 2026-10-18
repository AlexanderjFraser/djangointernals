---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The second decade: from 1.9 to 5.0

Middleware rebuilt as an onion, Python 2 dropped, routes with `path`, ASGI and asynchronous views, indexes and constraints as objects, forms drawn by templates, `zoneinfo`: decisions of 1.9 to 5.0, and what each left at this commit.

Django 1.9 came on 1 December 2015 and 5.0 on 4 December 2023 (`docs/releases/1.9.txt`, `docs/releases/5.0.txt`; [What changed](../changes.md#the-releases)). Several decisions took many releases. At this commit the old way often survives, as a shim, a name, or a class kept for old migrations. The years before are told in [The first decade: from a newsroom to 1.8](first-decade.md).

## Middleware, rebuilt as an onion

1.10 rebuilt middleware as an onion, "to solve the lack of strict request/response layering" (`docs/releases/1.10.txt`). Each middleware is wrapped round those listed after it. A response that a middleware returns early passes out only through the layers outside it. Before, a middleware was a class listed in MIDDLEWARE_CLASSES, whose hooks the handler called in turn. A response that one middleware's `process_request` returned still passed through the `process_response` of every middleware, those that never saw the request among them (`deps:final/0005-improved-middleware.rst`).

DEP 5, written by Carl Meyer in 2016, replaced the request and response hooks with factories, listed in a new setting, `MIDDLEWARE`. Each is called once with the layer inside it, to make a callable from a request to a response. 2.0 removed the old setting (`docs/releases/2.0.txt`). `BaseHandler.load_middleware` builds the nest once (`django/core/handlers/base.py:BaseHandler.load_middleware`; [Building the middleware chain](../handlers/chain.md)).

The old hooks live on in `MiddlewareMixin`, which DEP 5 offered so that one class could serve both settings. The DEP meant the mixin to "begin its own deprecation path" once the old setting was gone. The mixin never did. At this commit it is the base of all Django's middleware but `RemoteUserMiddleware` and its subclass `PersistentRemoteUserMiddleware` (`django/middleware/__init__.py:MiddlewareMixin`). It lived in `django.utils.deprecation`, the module of the deprecation warnings, until 6.2 moved it to `django.middleware` (`django/utils/deprecation.py:__getattr__`).

> **Why.** DEP 5 weighed letting an exception rise through the layers, and rejected it: each middleware that changes every response would have had to turn exceptions into responses itself, hiding them from the layers outside. Instead exceptions are converted to responses "before and after every middleware", so that a layer may raise `Http404` and count on a response from the layer inside (`deps:final/0005-improved-middleware.rst`). The conversion is `convert_exception_to_response`, wrapped around each layer as the chain is built (`django/core/handlers/exception.py:convert_exception_to_response`).

## Python 3 alone, and numbers that name the series

1.11, in 2017, was the last release to support Python 2 (`docs/releases/1.11.txt`). 2.0 supports Python 3.4 to 3.7. Its leading 2 marked no break of its own, but the start of "a loose form of semantic versioning" (`docs/releases/2.0.txt`). 3.0 removed the private helpers kept for Python 2, the vendored six among them. 4.0 removed the aliases force_text and smart_text, leaving `force_str` and `smart_str` (`docs/releases/3.0.txt`, `docs/releases/4.0.txt`, `django/utils/encoding.py:force_str`; [Text and bytes: `django/utils/encoding.py`](../utils/encoding.md)).

## Routes without regular expressions

2.0 added routes, URL patterns written with `django.urls.path`, in which each parameter has a converter that both matches and converts it. Before, a URL pattern was a regular expression given to the function url of `django.conf.urls`, and what it captured reached the view as strings. DEP 201, by Tom Christie, Sjoerd Job Postmus and Aymeric Augustin, found the expressions "unnecessarily verbose and complex for the vast majority of use-cases". It proposed a syntax after Flask's (`deps:final/0201-simplified-routing-syntax.rst`). 2.0 made the old function available as `django.urls.re_path`, and kept url as an alias until 4.0 (`docs/releases/2.0.txt`, `docs/releases/4.0.txt`).

The old function's module, `django/conf/urls/__init__.py`, now holds `include`, which it imports from `django.urls`, and the default error views a resolver falls back on (`django/urls/resolvers.py:URLResolver.resolve_error_handler`). As the DEP planned, a route is still expanded into a regular expression, as its `RoutePattern` is made (`django/urls/resolvers.py:_route_to_regex`; [Routes, regular expressions and converters](../urls/patterns.md)).

## Indexes and constraints as objects

1.11 made an index an object, `Index`, which "can be subclassed to support different index types" (`docs/releases/1.11.txt`). Before, a model asked for an index over several columns with the option index_together of its `Meta`, and for a rule over them with `Options.unique_together` alone (`django/db/models/options.py:Options`). 2.2 made rules objects too, `CheckConstraint` and `UniqueConstraint` (`docs/releases/2.2.txt`). 3.2 let an index be made on expressions, and 4.0 a unique constraint. 4.1 made model validation check the constraints (`docs/releases/3.2.txt`, `docs/releases/4.0.txt`, `docs/releases/4.1.txt`, `django/db/models/base.py:Model.validate_constraints`; [Constraints and indexes](../models/constraints.md)).

4.2 deprecated index_together, and 5.1 removed it, but not from migrations. `AlterIndexTogether` remains, supported only for migration files from before 4.2, with "no plan to deprecate or remove it" (`docs/releases/4.2.txt`, `docs/releases/5.1.txt`, `django/db/migrations/operations/models.py:AlterIndexTogether`; [The model operations: `CreateModel`, `DeleteModel`, `RenameModel` and the option operations](../migrations/model-operations.md)). `Options.unique_together` was never deprecated. The documentation recommends a `UniqueConstraint`, and says the option "may be deprecated in the future" (`docs/ref/models/options.txt`).

## Widgets and forms drawn by templates

Widgets wrote their HTML in Python until 1.11 moved their rendering to the template system "to ease customizing widgets" (`docs/releases/1.11.txt`). 4.0 did the same for forms, formsets and error lists. 4.1 added a layout in `<div>` elements, which became the default in 5.0 (`docs/releases/4.0.txt`, `docs/releases/4.1.txt`, `docs/releases/5.0.txt`). `RenderableFormMixin.as_table` and the three methods beside it each render a template (`django/forms/utils.py:RenderableFormMixin`; [Rendering a form: renderers and templates](../forms/rendering.md)).

## Asynchronous Django

DEP 9, written by Andrew Godwin in 2019, proposed to make every part of Django that could block asynchronous, while keeping every synchronous interface. Each part was to pass through stages: first its synchronous code behind an asynchronous wrapper that runs it in a thread, later asynchronous code behind a synchronous wrapper (`deps:accepted/0009-async.rst`). 3.0 began at the outermost layer: Django could be served as an ASGI application, though "internally everything remains synchronous". Code marked as unsafe, such as the ORM's, refused to run where an event loop was running (`docs/releases/3.0.txt`). `ASGIHandler` is that entry, and `async_unsafe` the mark, which raises `SynchronousOnlyOperation` (`django/core/handlers/asgi.py:ASGIHandler`, `django/utils/asyncio.py:async_unsafe`).

3.1 let views and middleware be asynchronous, under ASGI or WSGI. The handler puts an adapter wherever a layer and the one inside it differ in mode (`docs/releases/3.1.txt`, `django/core/handlers/base.py:BaseHandler.adapt_method_mode`; [Sync and async in one chain](../handlers/async.md)). The DEP had meant the core to become asynchronous, with WSGI running it in an event loop. Instead the core has two forms, `BaseHandler._get_response` and `BaseHandler._get_response_async`. A WSGI handler builds a synchronous chain, in which an asynchronous view runs in a one-off event loop (`docs/topics/async.txt`).

4.0 gave the cache asynchronous methods. 4.1 gave the queryset "an asynchronous interface for all data access operations", though "the underlying database operations remain synchronous" (`docs/releases/4.0.txt`, `docs/releases/4.1.txt`). At this commit they still do: `QuerySet.aget` runs `QuerySet.get` through `sync_to_async`, "sync-native, with an async wrapper" in DEP 9's words (`django/db/models/query.py:QuerySet.aget`; [The asynchronous methods of a queryset](../querysets/async.md)). The proposal is still filed as accepted, not final.

> **Why.** Python cannot give one name both a synchronous and an asynchronous body, so DEP 9 proposed a suffix, get_async beside get, as the easiest to check in review (`deps:accepted/0009-async.rst`). When such twins shipped, on the cache in 4.0, they took a prefix instead, `BaseCache.aget`, and the notes said this prefix "will be used for async variants of methods generally" (`docs/releases/4.0.txt`, `django/core/cache/backends/base.py:BaseCache.aget`).

## Time zones from the standard library

1.11 made pytz a required dependency "to simplify Django's timezone handling" (`docs/releases/1.11.txt`). 3.2 accepted zones that were not pytz's, such as those of `zoneinfo`, in the standard library from Python 3.9. 4.0 made `zoneinfo` the default and deprecated pytz. The transitional setting USE_DEPRECATED_PYTZ let a project keep pytz through 4.x. 5.0 removed both (`docs/releases/3.2.txt`, `docs/releases/4.0.txt`, `docs/releases/5.0.txt`). `get_default_timezone` makes a `zoneinfo.ZoneInfo` of `TIME_ZONE` (`django/utils/timezone.py:get_default_timezone`; [Time zones](../i18n/time-zones.md)).

## PostgreSQL's JSON for every database, and a second driver

1.9 added a JSON field to `django.contrib.postgres` (`docs/releases/1.9.txt`). 3.1 put one in Django's core for every supported database, with the lookups and transforms that had been PostgreSQL's alone (`docs/releases/3.1.txt`, `django/db/models/fields/json.py:JSONField`). The old field was deprecated with it and removed in 4.0, but a stub was to remain "for compatibility with historical migrations" (`docs/internals/deprecation.txt`). At this commit the stub, in `django/contrib/postgres/fields/jsonb.py`, is a subclass of the new field. Its `Field.system_check_removed_details` makes a model that uses it fail the checks. `NullBooleanField`, deprecated in 3.1, ended the same way (`django/db/models/fields/__init__.py:Field._check_deprecation_details`; [The model checks](../models/checks.md)).

4.2 added psycopg 3 beside psycopg2, under the same `"ENGINE"`. Its notes said psycopg2 was "likely to be deprecated and removed at some point in the future" (`docs/releases/4.2.txt`). At this commit it is neither. `django/db/backends/postgresql/psycopg_any.py` imports psycopg where it can and psycopg2 otherwise, and sets `is_psycopg3`, which the backend asks where the two differ ([PostgreSQL](../backends/postgresql.md)).

## Applications that find their configuration

Since 3.2 Django finds an application's configuration itself, if its apps.py defines a single `AppConfig` subclass. Before, a package could name the class in a variable, default_app_config, so that `INSTALLED_APPS` could list just the package. 3.2's notes say the variable was introduced "with the intent to switch the ecosystem" to naming the class, "but the switch didn't happen". 3.2 deprecated it, and 4.1 removed it (`docs/releases/3.2.txt`, `docs/releases/4.1.txt`). `AppConfig.create` takes an entry first as a module, and then as the path of a class (`django/apps/config.py:AppConfig.create`; [Populating the app registry](../startup/populate.md)).

## New projects ahead of the defaults

1.9 added password validation, off by default and on in the settings startproject writes (`docs/releases/1.9.txt`). 3.2 likewise wrote `BigAutoField` into new projects, while `DEFAULT_AUTO_FIELD` kept `AutoField` (`docs/releases/3.2.txt`). That default caught up in 6.0. The default of `USE_TZ`, which startproject has set since 1.4, had caught up in 5.0 (`docs/releases/6.0.txt`, `docs/releases/5.0.txt`, `docs/releases/4.0.txt`; [What changed in models and fields](models.md)). The validators have not: `django/conf/global_settings.py` leaves `AUTH_PASSWORD_VALIDATORS` empty, and `django/conf/project_template/project_name/settings.py-tpl` fills it ([Password validation: `validate_password` and the validators](../auth/password-validation.md)).

## Where 5.0 hands on

5.0's own changes, and those of every release after it to this commit, are gathered by part of Django, and [What changed](../changes.md#what-changed-in-outline) sets out their larger movements.
