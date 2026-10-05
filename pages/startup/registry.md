---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The registry and its models

What the app registry, `Apps`, keeps about models: how a model class finds its application and registers itself with `Apps.register_model`, how a reference to a model that does not exist yet waits in `Apps.lazy_model_operation`, and what `Apps.get_model` and `Apps.get_models` answer from.

Models reach the registry from the opposite direction to applications. An application is put there by `Apps.populate`, which reads a list. A model puts itself there, from inside its own class statement, whenever the module that defines it happens to be imported. The registry's part is to accept the class, to tell anything that was waiting for it, and later to answer for it.

## Two maps

The registry keeps its applications and its models in two separate dictionaries, and the difference between them explains most of its behaviour (`django/apps/registry.py:Apps.__init__`).

`Apps.app_configs` maps a label to the `AppConfig` of an installed application. It is filled by the first phase of `populate`, and it is what "installed" means.

`Apps.all_models` maps an application's label to a dictionary of its model classes, by their names in lower case. It is filled by the model classes themselves, and it does not depend on `app_configs` at all: a comment on it says that every imported model is registered, whether or not its application is installed and whether or not the registry has been populated, and that the dictionary is never reset, because a module cannot safely be imported twice.

The two are joined in the second phase of `populate`, when each `AppConfig` is given, as its `models` attribute, the inner dictionary for its label. It is the same dictionary object and not a copy, so a model registered later still appears in its application's `models`.

## A model class registers itself

The class statement of a model is run by the metaclass `ModelBase.__new__`, and two of its steps involve the registry (`django/db/models/base.py:ModelBase.__new__`).

Near the start it works out which application the new class belongs to. It gives the registry the dotted name of the module the class is being defined in, and `Apps.get_containing_app_config` returns the installed application whose name is a prefix of it; where applications are nested and several match, the one with the longest name (`django/apps/registry.py:Apps.get_containing_app_config`). The application's label becomes the model's `app_label`. A class in no installed application must name its label itself, in its `Meta`, or the class statement raises `RuntimeError`; an abstract class is let through without one. This is the step that needs `Apps.apps_ready`, and the reason a models module cannot be imported before `django.setup` has run.

At the end, when the class's `_meta` is complete, it calls `Apps.register_model`. An abstract model returns before that and is never registered.

`Apps.register_model` files the class in `all_models` under its label and its lower-case name (`django/apps/registry.py:Apps.register_model`). If a class is already filed there, one of two things is happening. A class with the same name from the same module means the module is being executed a second time; the registry warns that reloading models is not advised, and replaces the old class. Any other class means two different models claim one name in one application, and that raises `RuntimeError`.

It then does two more things, both for the benefit of other code: it runs whatever was waiting for this model, and it clears the registry's caches. The method must not import anything, because it runs in the middle of a models module's import, where an import of another models module could loop.

## References that wait: `Apps.lazy_model_operation`

A `ForeignKey` may name its target as a string, `"catalogue.Book"`, and often has to, because the target's module may not be importable yet, or may import this one. The field cannot finish setting itself up without the class, and the class does not exist. Django's answer is a general one: give the registry a function and the names of the models it needs, and the registry calls it when the last of them has been registered (`django/apps/registry.py:Apps.lazy_model_operation`).

The names are pairs of an application label and a lower-case model name, and the registry works through them in order. While the model for a pair is not registered, the job waits in `Apps._pending_operations` under that pair. Each time a model is registered, `Apps.do_pending_operations` resumes whatever was waiting for it. When no pair is left, the function is called with the classes.

In the recorded project the model Loan has two foreign keys, each naming by string a model of an application that comes later in `INSTALLED_APPS`. The recording shows both waiting twice: first for Loan itself, which is not registered while its own class statement is running, and then for the target.

```text recording=startup
AppConfig.import_models  (loans)
  import library.loans.models
    ModelBase.__new__  (class Loan)
      Apps.get_containing_app_config("library.loans.models")
      ...
      Apps.lazy_model_operation(resolve_related_class for the field book, ("loans", "loan"), ("catalogue", "book"))  loans.loan is not registered: the function is kept
      Apps.lazy_model_operation(resolve_related_class for the field member, ("loans", "loan"), ("members", "member"))  loans.loan is not registered: the function is kept
      ...
      Apps.register_model(loans.Loan)
        Apps.do_pending_operations(loans.Loan)  2 waiting
          Apps.lazy_model_operation(resolve_related_class for the field book, ("catalogue", "book"))  catalogue.book is not registered: the function is kept
          Apps.lazy_model_operation(resolve_related_class for the field member, ("members", "member"))  members.member is not registered: the function is kept
        Apps.clear_cache
AppConfig.import_models  (catalogue)
  import library.catalogue.models
    ModelBase.__new__  (class Book)
      Apps.get_containing_app_config("library.catalogue.models")
      Apps.register_model(catalogue.Book)
        Apps.do_pending_operations(catalogue.Book)  1 waiting
          Apps.lazy_model_operation(resolve_related_class for the field book)  no model left to wait for: it is called
            resolve_related_class(model=Loan, related=Book, field=book)
        Apps.clear_cache
```

The function a related field hands over is the one the recording calls resolve_related_class, defined inside the method that hands it over. When it finally runs, it replaces the string on the field with the class and sets up the other side of the relation, the attribute on Book through which its loans are reached (`django/db/models/fields/related.py:RelatedField.contribute_to_class`). Until then the field holds a string. So between the moment Loan is registered and the moment Book is, there is a registered model with a field that cannot yet be used.

Related fields are the main user, through a small wrapper that resolves a name relative to the model that uses it (`django/db/models/fields/related.py:lazy_related_operation`). The model signals are another: `ModelSignal`, the class of `pre_init`, `post_init`, `pre_save`, `post_save`, `pre_delete`, `post_delete` and `m2m_changed`, accepts a sender named by a string and connects the receiver when that model is registered (`django/db/models/signals.py:ModelSignal._lazy_method`).

Nothing ever times out. A function waiting for a model that is never registered, because its name was misspelt or its application is not installed, stays in `_pending_operations` for the life of the process, and nothing fails at startup. A system check reports it. `_check_lazy_references` goes through what is still pending and reports an error for a related field that names the field, and one for a signal receiver that names the receiver; each says whether the application is missing or only the model (`django/core/checks/model_checks.py:_check_lazy_references`).

## Asking for a model

`Apps.get_model` does not look in `all_models` directly. It finds the application's `AppConfig` by label, raising `LookupError` if no installed application has it, and asks the configuration, which looks the name up in lower case in its `models` and raises `LookupError` if it is not there (`django/apps/registry.py:Apps.get_model`, `django/apps/config.py:AppConfig.get_model`). The route through the configuration is what limits the answer to installed applications. A model of an application that is not installed is in `all_models`, and `Apps.get_registered_model` will return it, but `get_model` will not.

`Apps.get_models` returns the models of every installed application, in the order of the applications. It leaves out two kinds unless asked for them: the models Django makes automatically for a many-to-many relation that names no intermediate model, and a model that has been swapped out for another by a setting, as the auth application's `User` is when `AUTH_USER_MODEL` names a different one (`django/apps/config.py:AppConfig.get_models`, `django/contrib/auth/models.py:User`).

`get_models` is cached with `functools.cache`, and so is `Apps.get_swappable_settings_name`, which migrations call often. `Apps.clear_cache` empties both. Once the registry is ready, it also goes to every model and expires the caches on its `_meta`, the lists of fields and relations that each model computes on demand and keeps (`django/apps/registry.py:Apps.clear_cache`, `django/db/models/options.py:Options._expire_cache`).

Those per-model caches are what the registry protects when it refuses to hand out a model before the second phase is over. A model's forward fields are its own and exist as soon as its class does. Its reverse relations are a fact about every other model, and `Options` works them out for all models at once, the first time any model is asked, by going through `Apps.get_models` and collecting every field that points somewhere (`django/db/models/options.py:Options._populate_directed_relation_graph`). Done too early, the result would be missing the models not yet imported, and it would be kept. `Options.get_field` shows the care taken: asked before `models_ready` for a name that is not one of the model's own fields, it raises `FieldDoesNotExist` with a message saying the registry is not ready, without computing the reverse relations at all (`django/db/models/options.py:Options.get_field`).

Because `register_model` clears the caches, a model class made after startup is safe: the next question about relations is answered afresh, with the new model included.

## Registries other than the main one

`django.apps.apps` is the main registry, and nearly all code means it. The class can be instantiated again, and Django does so.

An `Apps` made with a list of applications populates itself at once in its constructor. The main one is made with `None` in place of a list, because at import time there is nothing to populate it with, and the constructor refuses to make a second registry that way (`django/apps/registry.py:Apps.__init__`).

A model belongs to one registry: the one in its `_meta`, as `Options.apps`. That is the main registry unless the model's `Meta` names another, and it is the registry `ModelBase.__new__` registers the class with and the one its lazy references wait in (`django/db/models/options.py:Options.default_apps`).

Migrations are why this exists. To work out what the database should look like at some point in a project's history, they rebuild the models as they were then, as real classes, without disturbing the current ones. Those classes live in a `StateApps`, a subclass of `Apps` populated with stub configurations, one for each label, in which a model can also be unregistered and the whole registry cloned (`django/db/migrations/state.py:StateApps`). [Migrations](../migrations.md) is about how it is used.
