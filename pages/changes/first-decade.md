---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The first decade: from a newsroom to 1.8

The decisions of Django's first decade and the marks each left in the code at this commit: the magic-removal, newforms, databases by alias, class-based views, the swappable user model, `atomic`, the app registry, migrations and template engines.

Django was built in a newspaper's newsroom in Lawrence, Kansas, and open-sourced in the summer of 2005 (`docs/faq/general.txt`).

## The magic removed

Django 0.95, released in 2006, chiefly merged a branch called magic-removal. The branch removed constraints on how code had to be written that "were a consequence of decisions made in the early days of Django, prior to its open-source release" (`docs/releases/0.95.txt`). Until then an application's models were "magically transferred" into Django's own namespace, django.models, and saving was hooked through methods on the model called pre_save and post_save. After the merge, models stayed in the module that defined them, a model overrode `Model.save` and `Model.delete` in their place, as any class overrides a method, and custom table-level functions went on a new Manager API (`django/db/models/manager.py:BaseManager`).

Two more changes of 0.95 still stand. Pieces of the framework could be configured without an environment variable, so that the template system, for one, could be used inside other applications. `LazySettings.configure` allows it now (`django/conf/__init__.py:LazySettings.configure`). And Django no longer required a database. A project that defines none gets a `"default"` on the dummy backend, which raises when used (`django/db/utils.py:ConnectionHandler.configure_settings`). `Model._meta` dates from the days of the magic-removal, say the 1.8 notes, and became an official API only in 1.8 (`docs/releases/1.8.txt`; [The options: what a model keeps as `_meta`](../models/options.md)).

## Forms rebuilt, and the admin taken out of the model

Before 0.96, [released in 2007](https://www.djangoproject.com/weblog/2007/mar/23/096/), forms were django.forms, a framework of manipulators and validation. 0.96 shipped its replacement beside it as django.newforms, and copied the old one to django.oldforms. Its notes set the schedule: the next release would move newforms to django.forms, and the one after would remove oldforms (`docs/releases/0.96.txt`).

Django 1.0, [released in September 2008](https://www.djangoproject.com/weblog/2008/sep/03/1/), made the move and rebuilt the admin on the new forms, with admin definitions "completely decoupled from model definitions (no more class Admin declaration in models!)". The helpers form_for_model and form_for_instance gave way to `ModelForm` (`docs/releases/1.0.txt`). A model's admin options live outside it, on a `ModelAdmin` registered for the model with `AdminSite.register` (`django/contrib/admin/sites.py:AdminSite.register`; [Registering models: `AdminSite.register` and `ModelAdmin`](../admin/registration.md)).

By 1.2 a deprecation warned first with a `PendingDeprecationWarning`, then with a `DeprecationWarning`, and at this commit `RemovedInDjango2029Warning` is the first kind, `RemovedInDjango2028Warning` the second (`docs/releases/1.2.txt`, `django/utils/deprecation.py`).

## Databases and caches by alias

Until 1.2, in 2010, a project had one database, configured by settings such as DATABASE_ENGINE and DATABASE_NAME. 1.2 replaced them with `DATABASES`, connections by alias with one named `"default"` (`docs/releases/1.2.txt`). The change reached custom fields, whose methods could no longer assume the database. Preparing a value was split in two: `Field.get_prep_value` for every database, and `Field.get_db_prep_value`, given the connection and a prepared flag that says whether the first has run. Both keep those signatures (`django/db/models/fields/__init__.py:Field.get_db_prep_value`).

1.3 configured caches "in the same way", by alias in `CACHES` (`docs/releases/1.3.txt`). `ConnectionHandler` and `CacheHandler` are now both subclasses of `BaseConnectionHandler` (`django/utils/connection.py:BaseConnectionHandler`; [Connections by alias: `DATABASES` and `ConnectionHandler`](../backends/connections.md)).

## Views as classes

Django's generic views were functions, in modules such as django.views.generic.list_detail. 1.3, in 2011, added class-based views, so that a view could be composed "out of a collection of methods that can be subclassed and overridden". It deprecated the generic views that were functions, which 1.5 removed (`docs/releases/1.3.txt`, `docs/internals/deprecation.txt`).

The URLconf did not change for them. Since 0.96 a pattern could name any callable, where before it named a string (`docs/releases/0.96.txt`). A class-based view enters the URLconf as the function `View.as_view` returns (`django/views/generic/base.py:View.as_view`; [`View.as_view` and dispatch](../views/as-view.md)).

## Time zones and the project layout

Until 1.4, in 2012, Django used naive datetimes, "leaving it up to each developer to interpret what a given date/time 'really means'". 1.4 added a mode that stores datetimes in UTC, works with aware ones and converts them to the user's time zone in templates and forms. New projects made by startproject had it on (`docs/releases/1.4.txt`). The settings startproject writes still set `USE_TZ`, though it has been true by default since 5.0 (`docs/releases/5.0.txt`, `django/conf/project_template/project_name/settings.py-tpl`; [Time zones](../i18n/time-zones.md)).

1.4 also moved manage.py out of the project package, where its handling of import paths could import a module twice. It added `wsgi.py`, with an application that `WSGI_APPLICATION` names and the development server runs too (`docs/releases/1.4.txt`). Until 1.3 a WSGI script made a `WSGIHandler` itself. Since 1.7 that fails with `AppRegistryNotReady`: it is `get_wsgi_application` that calls `django.setup`, which fills the registry of the installed applications and their models (`docs/releases/1.7.txt`, `django/core/wsgi.py:get_wsgi_application`; [The two entry points](../handlers/entry.md)).

## Python 3, and a user model of one's own

1.5, in 2013, was "the first release with Python 3 support", from one codebase for both Pythons, and called that support experimental. 1.6 supported Python 3 officially (`docs/releases/1.5.txt`, `docs/releases/1.6.txt`). 2.0 dropped Python 2 in 2017, and loaddata still opens fixtures in binary mode, a choice its comment says may be revisited after dropping Python 2 (`docs/releases/2.0.txt`, `django/core/management/commands/loaddata.py:Command.compression_formats`).

1.5 also let a project replace the user model. It deprecated AUTH_PROFILE_MODULE, the setting that had named a profile model for extra data (`docs/releases/1.5.txt`). `User` declares itself swappable for `AUTH_USER_MODEL`, and code asks `get_user_model` for the model in use (`django/contrib/auth/models.py:User`, `django/contrib/auth/__init__.py:get_user_model`; [The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`](../auth/user-model.md)).

## Transactions, made explicit

Until 1.6, in 2013, the database's own autocommit was off by default. Transactions were managed through TransactionMiddleware and decorators such as commit_on_success and commit_manually. 1.6 turned autocommit on by default, which its notes say makes transaction handling more explicit. It deprecated those APIs, which 1.8 removed (`docs/releases/1.6.txt`, `docs/internals/deprecation.txt`). What stands now is `atomic`, a block that commits or rolls back and nests as savepoints (`django/db/transaction.py:Atomic`; [Transactions: autocommit, `atomic` and savepoints](../backends/transactions.md)).

Since 1.1 each of a `TestCase`'s tests had run in a transaction rolled back after it (`docs/releases/1.1.txt`). 1.8 rebuilt `TestCase` on `atomic`: one block for the class, where `TestCase.setUpTestData` runs, and one for each test (`docs/releases/1.8.txt`, `django/test/testcases.py:TestCase._enter_atomics`; [A transaction around each test: `TestCase`](../testing/test-case.md)).

## The app registry and migrations

A singleton called the app cache once held the installed applications and their models, and an application was known by its models module. 1.7, in 2014, replaced it with the app registry. An application is an `AppConfig`, which may run code at startup in `AppConfig.ready`. Every application and model is imported as Django starts, by one deterministic process that the notes expect to make import loops easier to diagnose: `Apps.populate`, which `django.setup` calls (`docs/releases/1.7.txt`, `django/apps/registry.py:Apps.populate`; [Populating the app registry](../startup/populate.md)). Before the models are ready, `Options.get_field` still says that the app cache isn't ready when it cannot find a field. Until then it can find only a model's own fields, not the reverse ones that relations to the model create (`django/db/models/options.py:Options.get_field`).

The same release built in schema migrations: syncdb gave way to migrate, and makemigrations writes migration files from the models. Every field must describe itself for those files through a new required method, `Field.deconstruct` (`docs/releases/1.7.txt`, `django/db/models/fields/__init__.py:Field.deconstruct`; [Migrations](../migrations.md)). Inside migrate, syncdb survives: with --run-syncdb, `Command.sync_apps` creates the tables of applications without migrations (`django/core/management/commands/migrate.py:Command.sync_apps`; [The migrate command, showmigrations and sqlmigrate](../migrations/migrate.md)).

The 1.7 notes do not name South, [a third-party migrations application](https://www.djangoproject.com/weblog/2014/sep/02/release-17-final/). A comment does: to skip South's, `MigrationQuestioner.ask_initial` has makemigrations write no first migration for an application whose migrations package holds a Python file other than `"__init__.py"`, unless the command names it (`django/db/migrations/questioner.py:MigrationQuestioner.ask_initial`).

## Expressions and template engines

In 2014 Django adopted a process for proposals, DEP 1, a near-copy of Python's PEPs (`deps:final/0001-dep-process.rst`; [Where Django came from, and who makes it](../introduction/origins.md#django-enhancement-proposals)). Two proposals of that year shaped 1.8, released in 2015.

### Expressions

1.1 had added aggregates, `QuerySet.aggregate` and `QuerySet.annotate`, and `F`, a reference to another field (`docs/releases/1.1.txt`). By 2014, as DEP 181 by Anssi Kääriäinen describes, an `F` expression was turned into SQL by a private, global SQLEvaluator that had to know every kind of node. Aggregates were not expressions at all, so two could not be added to each other; annotate took nothing but aggregates (`deps:final/0181-orm-expressions.rst`).

The code keeps the DEP's design. An expression is bound to a query by `BaseExpression.resolve_expression` and writes its SQL with `BaseExpression.as_sql`. An `Aggregate` is a `Func` like any database function, and `F`, as the DEP proposed, is not an expression but resolves to one (`django/db/models/aggregates.py:Aggregate`, `django/db/models/expressions.py:F.resolve_expression`; [Expressions: `resolve_expression` and `as_sql`](../sql/expressions.md)).

### Template engines

Until 1.8 the one template language was configured by global settings such as TEMPLATE_DIRS. DEP 182, by Aymeric Augustin, gave convenience and speed as reasons users were turning to other engines, Jinja2 above all. It proposed a stable API for template backends, with Jinja2 built in and the Django template language kept as the default (`deps:final/0182-multiple-template-engines.rst`). `TEMPLATES` lists the engines, and `get_template` asks them in order until one finds the template (`django/template/loader.py:get_template`; [Template engines: `TEMPLATES` and the backends](../templates/engines.md)). Since users would have to write `TEMPLATES` anyway, 1.8 also moved the context processors out of django.core, where the magic-removal had left them, to `django.template.context_processors` (`deps:final/0182-multiple-template-engines.rst`, `docs/releases/1.8.txt`).

> **Why.** DEP 182 weighed four ways of choosing an engine for a template: naming it in each call, a tag inside each template, the file's extension, and asking each engine in turn. It chose the last, keeping the first for atypical cases. So `TEMPLATES` is a list, where `DATABASES` and `CACHES` are dictionaries: its order decides which engine wins, and a project can put replacements for an application's templates first (`deps:final/0182-multiple-template-engines.rst`).

The proposals went on after 1.8: the new middleware of 1.10 was DEP 5's, and asynchronous Django is DEP 9's (`docs/releases/1.10.txt`, `deps:accepted/0009-async.rst`), both told in [The second decade: from 1.9 to 5.0](second-decade.md).
