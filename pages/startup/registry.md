---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The registry and its models

The app registry, `Apps`, keeps the installed applications in `Apps.app_configs` and the model classes in `Apps.all_models`, into which a class files itself with `Apps.register_model` as its class statement ends. A reference to a model that does not exist yet waits, through `Apps.lazy_model_operation`, until the class is registered, and `Apps.get_model`, `Apps.get_models` and `Apps.get_registered_model` answer from one or the other.

Models reach the registry from the opposite direction to applications. An application is put there by `Apps.populate`, which reads a list. A model puts itself there, from inside its own class statement, whenever the module that defines it happens to be imported. The registry's part is to accept the class, to tell anything that was waiting for it, and later to answer for it.

## Two maps: `Apps.app_configs` and `Apps.all_models`

The registry keeps its applications and its models in two separate dictionaries, and the difference between them explains much of its behaviour (`django/apps/registry.py:Apps.__init__`).

`Apps.app_configs` maps a label to the `AppConfig` of an installed application. It is filled by the first phase of `populate`, and it is what "installed" means.

`Apps.all_models` maps an application's label to a dictionary of its model classes, by their names in lower case. It is filled by the model classes themselves, as each registers, and filing does not look at `app_configs`: a model is filed there whether or not its application is installed and whether or not the registry has been populated (`django/apps/registry.py:Apps.register_model`).

> **Why.** No method of `Apps` takes a model out of `all_models`, not even `Apps.set_installed_apps`, which populates the registry again with other applications for a test. A model is filed there as its module is imported, and an import cannot safely be replayed, since it could run initialization code again (`django/apps/registry.py:Apps.__init__`, `django/apps/registry.py:Apps.set_installed_apps`). Only `ManagementUtility.execute` replaces the main registry's map, with an empty one, when `django.setup` fails under runserver's reloader ([Who calls `django.setup`](callers.md#the-development-server-may-start-broken)) (`django/core/management/__init__.py:ManagementUtility.execute`).

The two are joined in the second phase of `populate`, when each `AppConfig` is given, as its `models` attribute, the inner dictionary for its label. It is the same dictionary object and not a copy, so a model registered later still appears in its application's `models` (`django/apps/config.py:AppConfig.import_models`).

So a model can be asked for by two routes. `Apps.get_model` goes through `app_configs` and the configuration's `models`, and finds only the models of installed applications; `Apps.get_registered_model` goes straight into `all_models`, and finds a model of an application that is not installed as well (`django/apps/registry.py:Apps.get_registered_model`).

The figure draws both maps for the recorded project, *library*, whose applications *loans*, *catalogue* and *members* define Loan, Book and Member, with one model added whose application is not installed. Follow each configuration's `models` into `all_models`, and the two routes below the maps, which part at that model's label.

```text figure=two-maps
Apps.app_configs                                    Apps.all_models
label -> AppConfig: what "installed" means          label -> {name in lower case: model class}
filled by phase one of Apps.populate                filled by each class, through Apps.register_model

"loans"      ->  the AppConfig of loans             "loans"      ->  {"loan": Loan}
                 models, given in phase two  ----------------------->  the same dictionary, not a copy
"catalogue"  ->  the AppConfig of catalogue         "catalogue"  ->  {"book": Book}
                 models  ------------------------------------------>  the same dictionary
"members"    ->  the AppConfig of members           "members"    ->  {"member": Member}
                 models  ------------------------------------------>  the same dictionary
no entry                                            a label whose application is not installed  ->  {its model}

Apps.get_model:             app_configs[label]  ->  the configuration's models  ->  the class
                            a label not installed: LookupError, at app_configs
Apps.get_registered_model:  all_models[label]  ->  the class
                            a label not installed: the class all the same
```

*The registry's two maps, side by side. Each arrow from a configuration's `models` ends at the very dictionary that `all_models` holds for that label, not at a copy of it; below the maps, the two lookups are drawn as routes, and only `get_model`'s, through `app_configs`, stops at an application that is not installed.*

## A model class registers itself

The class statement of a model runs the metaclass `ModelBase.__new__`, and two of its steps call the registry directly (`django/db/models/base.py:ModelBase.__new__`).

Near the start it works out which application the new class belongs to. It gives the registry the dotted name of the module the class is being defined in, and `Apps.get_containing_app_config` returns the installed application whose package contains it; where applications are nested and several match, the one with the longest name (`django/apps/registry.py:Apps.get_containing_app_config`). The application's label becomes the model's `app_label`, unless its `Meta` names one. A class in no installed application must name its label in its `Meta`, or the class statement raises `RuntimeError`; an abstract class is let through without one.

This is the step that needs `Apps.apps_ready` ([Populating the app registry](populate.md#phase-one-an-appconfig-for-each-entry)). `get_containing_app_config` first calls `Apps.check_apps_ready`, which, where there are settings to read, raises `AppRegistryNotReady` until every entry of `INSTALLED_APPS` has its configuration, and the class statement makes the call whatever its `Meta` says (`django/apps/registry.py:Apps.check_apps_ready`).

At the end, when the class's `_meta` is complete, it calls `Apps.register_model`. An abstract model returns before that and is never registered. What the metaclass does between those two steps is the subject of [`ModelBase`: a class statement becomes a model](../models/metaclass.md).

`Apps.register_model` files the class in `all_models` under its label and its lower-case name (`django/apps/registry.py:Apps.register_model`). If a class is already filed there, the registry tells two cases apart. A class with the same name from the same module is taken for a reload: the registry warns that reloading models is not advised, and replaces the old class. Any other class means two different models claim one name in one application, and that raises `RuntimeError`.

It then does two more things, both for the benefit of other code: it runs whatever was waiting for this model, and it clears the registry's caches. The method must not import anything, because it runs in the middle of a models module's import, where an import of another models module could loop.

## References that wait: `Apps.lazy_model_operation`

A `ForeignKey` may name its target as a string, `"catalogue.Book"`, and often has to, because the target may not be defined yet, or its module may import this one. The field cannot finish setting itself up without the class, and the class does not exist. Django's answer is a general one: give the registry a function and the names of the models it needs, and the registry calls it when the last of them has been registered (`django/apps/registry.py:Apps.lazy_model_operation`). What the field's function does once it is called is in [Relations: a field, its rel and the class at the other end](../relations/fields.md).

The names are pairs of an application label and a lower-case model name, and the registry works through them in order. While the model for a pair is not registered, the job waits in `Apps._pending_operations` under that pair. Each time a model is registered, `Apps.do_pending_operations` resumes whatever was waiting for it. When no pair is left, the function is called with the classes (`django/apps/registry.py:Apps.lazy_model_operation`, `django/apps/registry.py:Apps.do_pending_operations`).

In the recorded project the model Loan has two foreign keys, each naming by string a model of an application that comes later in `INSTALLED_APPS`. Each field hands the registry a function that needs two classes, Loan and the target, so each function waits twice: first for Loan, which is not registered while its own class statement is running, and then for the target. The one waiting for Book is called inside Book's class statement, as Book is registered.

```text recording=startup
django.setup() in a new process
            ...
            ModelBase.__new__  (class Loan)
              ...
              Apps.lazy_model_operation(resolve_related_class for the field book, ("loans", "loan"), ("catalogue", "book"))  loans.loan is not registered: the function is kept
              Apps.lazy_model_operation(resolve_related_class for the field member, ("loans", "loan"), ("members", "member"))  loans.loan is not registered: the function is kept
              ...
              Apps.register_model(loans.Loan)
                Apps.do_pending_operations(loans.Loan)  2 waiting
                  Apps.lazy_model_operation(resolve_related_class for the field book, ("catalogue", "book"))  catalogue.book is not registered: the function is kept
                  Apps.lazy_model_operation(resolve_related_class for the field member, ("members", "member"))  members.member is not registered: the function is kept
            ...
            ModelBase.__new__  (class Book)
              ...
              Apps.register_model(catalogue.Book)
                Apps.do_pending_operations(catalogue.Book)  1 waiting
                  Apps.lazy_model_operation(resolve_related_class for the field book)  no model left to wait for: it is called
                    resolve_related_class(model=Loan, related=Book, field=book)
                    ...
```

The function a related field hands over, `resolve_related_class`, is defined inside `RelatedField.contribute_to_class`; it puts the class on the field in place of the string and sets up the other side of the relation, the attribute on Book through which its loans are reached (`django/db/models/fields/related.py:RelatedField.contribute_to_class`). So between the moment Loan is registered and the moment Book is, there is a registered model whose field still holds a string and cannot yet be used.

Related fields are the main user, through a small wrapper that resolves a name relative to the model that uses it (`django/db/models/fields/related.py:lazy_related_operation`). The model signals are another: `ModelSignal`, the class of `pre_init`, `post_init`, `pre_save`, `post_save`, `pre_delete`, `post_delete` and `m2m_changed`, accepts a sender named by a string and connects the receiver when that model is registered (`django/db/models/signals.py:ModelSignal._lazy_method`).

Nothing ever times out. A function waiting for a model that is never registered stays in `_pending_operations` for the life of the process, since nothing takes it out but that model's registration (`django/apps/registry.py:Apps.do_pending_operations`). The project's application *wishlist*, installed beside *catalogue*, has a model with two foreign keys of that kind: one names a model *catalogue* does not have, the other a model of an application that is not installed. Look for what `django.setup` returns, and what it leaves waiting.

```text recording=startup
django.setup() with INSTALLED_APPS = ["library.catalogue", "library.wishlist"]: two references by string that never resolve wait in Apps._pending_operations, and nothing is raised
    django.setup()  -> None
    apps._pending_operations
      ("catalogue", "bok"): resolve_related_class for the field book
      ("periodicals", "issue"): resolve_related_class for the field issue
```

> **Trap.** A relation to a model that does not exist fails nothing at startup, and its field keeps the string it was given. The mistake is reported by the system checks, one of which goes through what is still waiting in `_pending_operations` and, for a relation, names the field and says whether the application is missing or only the model ([The model checks](../models/checks.md#check_lazy_references)) (`django/core/checks/model_checks.py:_check_lazy_references`).

## Asking for a model: `Apps.get_model` and `Apps.get_models`

`Apps.get_model` reaches a model through its application's configuration, which is what limits its answer to installed applications. It finds the `AppConfig` by label, raising `LookupError` if no installed application has it, and asks the configuration, which looks the name up in lower case in its `models` and raises `LookupError` if it is not there (`django/apps/registry.py:Apps.get_model`, `django/apps/config.py:AppConfig.get_model`).

`Apps.get_models` returns the models of every installed application, in the order of the applications. It leaves out two kinds unless asked for them: the models Django makes automatically for a many-to-many relation that names no intermediate model, and a model that has been swapped out for another by a setting, as the auth application's `User` is when `AUTH_USER_MODEL` names a different one (`django/apps/config.py:AppConfig.get_models`, `django/contrib/auth/models.py:User`).

`get_models` is cached with `functools.cache`, and so is `Apps.get_swappable_settings_name`, which migrations call often. `Apps.clear_cache` empties both. Once the registry is ready, it also goes to every model of an installed application, unless swapped out, and expires the caches on its `_meta`, among them the lists of fields and relations that each model computes on demand and keeps (`django/apps/registry.py:Apps.clear_cache`, `django/db/models/options.py:Options._expire_cache`).

Some of those caches are what the registry protects when `get_models` refuses to answer before the second phase is over. A model's forward fields are its own and exist as soon as its class does. Its reverse relations are a fact about every other model, and `Options` works them out for all models at once, the first time any model is asked, by going through `Apps.get_models` and collecting every field that points to a class (`django/db/models/options.py:Options._populate_directed_relation_graph`). Done too early, the result would be missing the models not yet imported, and it would be kept.

> **Why.** Asked before `models_ready` for a name that is not one of the model's own fields, `Options.get_field` raises `FieldDoesNotExist` rather than compute the reverse relations, which are unavailable until then (`django/db/models/options.py:Options.get_field`). A model that `get_model` returns with `require_ready=False` may lack reverse accessors until the registry is fully populated (`docs/ref/applications.txt`).

Because `register_model` calls `clear_cache`, a model class of an installed application made after startup is counted in the next question about relations, which is worked out afresh.

## Registries other than the main one

`django.apps.apps` is the main registry, and nearly all code means it. The class can be instantiated again, and Django does so.

An `Apps` made with a list of applications populates itself at once in its constructor. The main one is made with `None` in place of a list, because it cannot be populated yet, and the constructor refuses `None` once the main registry exists (`django/apps/registry.py:Apps.__init__`).

A model belongs to one registry: the one in its `_meta`, as `Options.apps`. That is `Options.default_apps` unless the model's `Meta` names another (`django/db/models/options.py:Options.default_apps`), and `default_apps` is the main registry, except while a test's `isolate_apps` has put a registry of its own there ([Settings for one test: `override_settings` and `TestContextDecorator`](../testing/test-decorators.md#the-other-changes)). It is the registry `ModelBase.__new__` registers the class with, and the one its lazy references wait in.

Migrations depend on this. To work out what the database should look like at some point in a project's history, they rebuild the models as they were then, as real classes, without disturbing the current ones. Those classes live in a `StateApps`, a subclass of `Apps` populated with stub configurations, one for each label, in which a model can also be unregistered and the whole registry cloned (`django/db/migrations/state.py:StateApps`). [Historical models: `StateApps` and rendering](../migrations/historical-models.md) is about how it is used.
