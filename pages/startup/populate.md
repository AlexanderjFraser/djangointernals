---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Populating the app registry

`Apps.populate` fills the app registry from `settings.INSTALLED_APPS` in three phases, each run over every entry before the next begins: `AppConfig.create` makes an `AppConfig` for each entry, `AppConfig.import_models` imports each application's models, and each `AppConfig.ready` is called. A flag marks the end of each phase, `Apps.apps_ready`, `Apps.models_ready` and `Apps.ready`, and a lookup that tests a flag not yet set is refused.

An entry of `INSTALLED_APPS` is a string. Before Django can use an application it needs more than that: the package the string names, a short unique label to file the application's models under, the directory its templates and static files are found in, the classes of its models. `Apps.populate` gets all of it by importing, and most of what it has to be careful about comes from that. Importing runs a project's own code, in an order the project only partly controls, while the registry that code might want to consult is half built.

The project the recording runs, *library*, enters its three applications in the order *loans*, *catalogue*, *members*. The figure draws `populate` over them as three passes, one to a row. The numbers mark the four moments at which the project's own code asks the registry the same questions, whose answers are recorded in [What the registry answers, phase by phase](#what-the-registry-answers-phase-by-phase).

```text figure=the-passes
INSTALLED_APPS = ["library.loans", "library.catalogue.apps.CatalogueConfig", "library.members"]
each phase is one pass over the whole list, left to right; its flag is set when the pass ends, and only then does the next pass begin

             loans                             catalogue                       members
phase 1      AppConfig.create              ->  AppConfig.create            ->  AppConfig.create  (1)            ->  apps_ready = True
phase 2      AppConfig.import_models  (2)  ->  AppConfig.import_models     ->  AppConfig.import_models  (3)     ->  models_ready = True
phase 3      LoansConfig.ready  (4)        ->  AppConfig.ready             ->  AppConfig.ready                  ->  ready = True

(1)  as library.members is imported: catalogue's configuration is made, and get_app_config refuses it
(2)  as library.loans.models is imported: catalogue.Book is not yet registered
(3)  as library.members.models is imported: catalogue.Book is registered, and get_model refuses it
(4)  in LoansConfig.ready: every lookup answers, and ready is still False
```

*`Apps.populate` over the project's three entries. A row is a phase, run over the whole list from left to right; the flag at its end is set before the next row begins. A call is named by the class that defines the method, so catalogue's, whose configuration class defines no `ready`, is `AppConfig.ready`.*

## `Apps.populate` runs once, by one thread

`Apps.populate` is written to be called more than once and to do its work once, unless `Apps.set_installed_apps` resets the registry (`django/apps/registry.py:Apps.populate`, `django/apps/registry.py:Apps.set_installed_apps`). A call that finds `Apps.ready` true returns immediately. Otherwise it takes a lock, `Apps._lock`, and tests the flag again, because a server may start several threads before any of them has made the handler, and two can arrive together. The second waits for the first to finish and then, if the first succeeded, finds nothing to do.

The lock is re-entrant, so it does not stop the same thread from arriving twice, and that case is refused outright. The method sets `Apps.loading` as it starts, and a call that finds it already set raises `RuntimeError`, saying that `populate` isn't reentrant; the purpose is to keep `AppConfig.ready` methods from running twice. The same thread arrives twice when code that runs during the phases calls `django.setup`: a module imported in any of them, or a `ready` method (`django/__init__.py:setup`).

The project's application *reopening*, installed on its own, has a `ready` that calls `django.setup`; what matters is how far the inner call gets before it is refused.

```text recording=startup
django.setup() with INSTALLED_APPS = ["library.reopening"], whose ready calls django.setup(): the second call configures logging and sets the prefix again, and its Apps.populate raises
          ...
          ReopeningConfig.ready  (reopening)
            setup
              configure_logging("logging.config.dictConfig", {})
              set_script_prefix("/")
              Apps.populate  (ready False, loading True)
                raises RuntimeError: populate() isn't reentrant
      -> raises RuntimeError: populate() isn't reentrant
    apps.loading True, apps_ready True, models_ready True, ready False
```

The refusal is `Apps.populate`'s alone, since `django.setup` has no guard of its own. The exception leaves the `ready` and then the outer `django.setup`, and the startup fails with `loading` still true.

`Apps.populate` never clears `loading`, so a startup that fails in a phase leaves the flag set for every later call. When an entry of `INSTALLED_APPS` cannot be imported, the second call's error is not the import's.

```text recording=startup
django.setup() with an entry that cannot be imported: INSTALLED_APPS = ["library.loans", "library.no_such_app"]
    django.setup()  -> raises ModuleNotFoundError: No module named 'library.no_such_app'
    apps.loading True, apps_ready False, ready False
    django.setup(), again  -> raises RuntimeError: populate() isn't reentrant
```

> **Trap.** Where a server's log shows only `populate() isn't reentrant`, and no code run in the phases called `django.setup`, the exception that says what is wrong was raised earlier in the same process (`django/apps/registry.py:Apps.populate`).

## Phase one: an `AppConfig` for each entry

The first phase calls `AppConfig.create` on each entry in turn, which works out what kind of entry it is by trying to import it (`django/apps/config.py:AppConfig.create`). An entry that is already an `AppConfig` object is used as it is; the registries that migrations build are populated that way.

**The entry is a package.** If the entry can be imported as a module, it is the application's package, and Django looks in its `apps` submodule, if it has one, for the configuration class: the only subclass of `AppConfig` there that does not set `default = False`, or, among several, the one that sets `default = True`. Where that finds none, the application gets a plain `AppConfig`.

**The entry is the path of a class.** If importing the entry as a module fails, it is tried as the dotted path of a configuration class. The class must be a subclass of `AppConfig` and must have a `name` attribute, the dotted path of the application's package, which is then imported.

**The entry is neither.** `create` raises the most useful error it can. For a dotted entry whose last part begins with a capital letter, probably meant as a class, it imports the rest of the path as a module and, if that succeeds, raises an `ImportError` that lists any configuration classes the module has; for any other, it runs the import again, which raises its own exception.

The project's entries are of both kinds that succeed: *loans* is a package with an `apps` module, *catalogue* is named by the path of its class, and *members* is a package with none. Under each `AppConfig.create` the package is imported first, then its `apps` module where there is one, and the configuration is made last, its class named at the end of the line.

```text recording=startup
django.setup() in a new process
...
      Apps.populate
        AppConfig.create("library.loans")
          import library.loans
          import library.loans.apps
          ...
          AppConfig.__init__("library.loans", app_module)  (LoansConfig)
        AppConfig.create("library.catalogue.apps.CatalogueConfig")
          import library.catalogue
          import library.catalogue.apps
          AppConfig.__init__("library.catalogue", app_module)  (CatalogueConfig)
        AppConfig.create("library.members")
          import library.members
          AppConfig.__init__("library.members", app_module)  (AppConfig)
          ...
```

The admin shows why an entry may be either a package or a class. Its `apps` module defines two configuration classes, `SimpleAdminConfig` and a subclass of it, `AdminConfig`, which sets `default = True`. The entry `"django.contrib.admin"` therefore gets `AdminConfig`, whose `ready` goes looking for every application's `admin` module; a project that wants an admin without that search names the other class by its path (`django/contrib/admin/apps.py:AdminConfig`).

`AppConfig.__init__` fixes the facts about the application that the rest of Django reads (`django/apps/config.py:AppConfig.__init__`).

| attribute | what it is | where it comes from |
|---|---|---|
| `name` | the dotted path of the package | the entry, or the class's `name` |
| `label` | the short name models and migrations are filed under | the class, or else the last part of `name`; it must be a valid identifier |
| `verbose_name` | the name shown to people | the class, or else the label in title case |
| `path` | the application's directory | the class, or else the package's one location on disk |
| `module` | the imported package | the import |
| `models_module`, `models` | the models module, and the model classes by name | nothing yet: the second phase sets them |

*The attributes of an `AppConfig`. A subclass may declare `label`, `verbose_name` and `path` on the class; the constructor fills in each one the class does not have.*

The directory matters because an application's templates, static files, translations and management commands are looked for inside its `path`. A namespace package spread over several directories has no single one, and `AppConfig._path_from_module` raises `ImproperlyConfigured` for it, asking for a configuration class that states `path` (`django/apps/config.py:AppConfig._path_from_module`).

Back in `populate`, each configuration is filed in `Apps.app_configs` under its label and given a reference to the registry. Two applications with the same label are refused there, and after the loop two with the same name. Then `Apps.apps_ready` is set (`django/apps/registry.py:Apps.populate`).

Until then no module can define a model. A model's class statement asks the registry which application its module belongs to (`django/db/models/base.py:ModelBase.__new__`), and `Apps.get_containing_app_config` will not answer before `apps_ready` (`django/apps/registry.py:Apps.get_containing_app_config`; [The registry and its models](registry.md#a-model-class-registers-itself)). The project's application *shelving*, entered after *catalogue*, has a package that imports *catalogue*'s models; the line that settles the matter is `Apps.check_apps_ready` under Book's class statement.

```text recording=startup
django.setup() with INSTALLED_APPS = ["library.catalogue", "library.shelving"], shelving's package importing catalogue's models: the class statement is refused in phase one, though catalogue's configuration is made
    django.setup()
      Apps.populate
        AppConfig.create("library.catalogue")
          import library.catalogue
          import library.catalogue.apps
          AppConfig.__init__("library.catalogue", app_module)  (CatalogueConfig)
        AppConfig.create("library.shelving")
          import library.shelving
            import library.catalogue.models
              ModelBase.__new__  (class Book)
                Apps.get_containing_app_config("library.catalogue.models")
                  Apps.check_apps_ready  apps_ready False, models_ready False, ready False
                    raises AppRegistryNotReady: Apps aren't loaded yet.
...
      -> raises AppRegistryNotReady: Apps aren't loaded yet.
```

> **Trap.** The documentation says that "Strictly speaking, Django allows importing models once their application configuration is loaded" (`docs/ref/applications.txt`). Django does not: a model's class statement is refused, whatever its application, until `Apps.apps_ready` is set at the end of the first phase, when every application's configuration is loaded (`django/apps/registry.py:Apps.check_apps_ready`). A package or an `apps` module that imports its own application's models is refused in the same way, and so is a script that imports a model without calling `django.setup` ([Who calls `django.setup`](callers.md#a-script)).

## Phase two: every models module is imported

The second phase calls `AppConfig.import_models` on each configuration, in the order of the setting (`django/apps/config.py:AppConfig.import_models`). The method does two things. It points `AppConfig.models` at the registry's dictionary of model classes for the application's label. And if the application's package has a submodule called `models`, it imports it.

Importing is all that is needed, because a model registers itself. The class statement of a model runs the metaclass `ModelBase.__new__`, which, unless the model is abstract, ends by calling `Apps.register_model` with the new class (`django/db/models/base.py:ModelBase.__new__`). [The registry and its models](registry.md) follows that call.

The order in which models are registered is the order in which their class statements finish, which the phase controls only loosely. A models module that imports a later application's models module causes those models to be registered during its own turn; when the other application's turn comes, its module is already imported and the turn registers nothing.

A model defined in some other module of an application is registered only when that module is imported. The phase imports `models` and nothing else, so an application whose models are spread over several files imports them all in `models`.

When every application has had its turn, `Apps.models_ready` is set.

## Phase three: every `ready` runs

The third phase calls `AppConfig.ready` on each configuration, in the same order. The base method does nothing (`django/apps/config.py:AppConfig.ready`). When all have returned, `Apps.ready` is set, and so is `Apps.ready_event`, a `threading.Event` that the development server's reloader waits on before it starts watching files (`django/utils/autoreload.py:BaseReloader.wait_for_apps_ready`).

`ready` is where an application connects itself to the parts of Django that keep process-wide lists. What some of Django's own applications do there shows the range (`django/contrib/messages/apps.py`).

| application | what its `ready` does |
|---|---|
| admin | registers system checks; `AdminConfig.ready` also runs `autodiscover`, which imports the `admin` module of every application so that each can register models with the site |
| auth | connects receivers to `post_migrate` that create and rename permissions, connects the receiver that records a user's last login if the user model has that field, registers system checks |
| messages | connects a receiver to `setting_changed` that makes the level tags anew when `"MESSAGE_TAGS"` changes |

*What the `ready` method of three contrib applications does. Of the others, some register system checks or connect receivers of their own, and some define no `ready` at all.*

Two of these need something the earlier phases could not give: a model class from another application, or simply a place to run once everything is importable (`django/contrib/admin/apps.py`). The auth application's `ready` is the plainest case. It asks for the user model, which may belong to any application, to see whether it has a `last_login` field (`django/contrib/auth/apps.py:AuthConfig.ready`). The PostgreSQL application's `ready` does the most, and [The PostgreSQL application: `PostgresConfig`, operations and aggregates](../contrib/postgres.md) follows it.

## What the registry answers, phase by phase

The three flags, `Apps.apps_ready`, `Apps.models_ready` and `Apps.ready`, are not only a record of progress. All the registry's lookups but one test the first two, and refuse a question asked too early with `AppRegistryNotReady` rather than answer it wrongly from a half-filled registry (`django/apps/registry.py:Apps.check_apps_ready`, `django/apps/registry.py:Apps.check_models_ready`).

At the four moments numbered in the figure, the project's code asks the registry the same four questions. Under each moment stand the three flags as they were, then each question with its answer, an exception given by its class and its message. The third moment shows the most: *catalogue*'s Book is registered by then, and `Apps.get_registered_model` returns it while `Apps.get_model` still refuses.

```text recording=startup
as library.members is imported, the last entry of phase 1
  apps_ready False, models_ready False, ready False
  get_app_config("catalogue")                 AppRegistryNotReady: Apps aren't loaded yet.
  get_model("catalogue", "Book")              AppRegistryNotReady: Models aren't loaded yet.
  get_registered_model("catalogue", "Book")   LookupError: Model 'catalogue.Book' not registered.
  get_models()                                AppRegistryNotReady: Models aren't loaded yet.
as library.loans.models is imported, the first models module of phase 2
  apps_ready True, models_ready False, ready False
  get_app_config("catalogue")                 <CatalogueConfig: catalogue>
  get_model("catalogue", "Book")              AppRegistryNotReady: Models aren't loaded yet.
  get_registered_model("catalogue", "Book")   LookupError: Model 'catalogue.Book' not registered.
  get_models()                                AppRegistryNotReady: Models aren't loaded yet.
as library.members.models is imported, the last models module of phase 2
  apps_ready True, models_ready False, ready False
  get_app_config("catalogue")                 <CatalogueConfig: catalogue>
  get_model("catalogue", "Book")              AppRegistryNotReady: Models aren't loaded yet.
  get_registered_model("catalogue", "Book")   the class catalogue.Book
  get_models()                                AppRegistryNotReady: Models aren't loaded yet.
in LoansConfig.ready, the first ready of phase 3
  apps_ready True, models_ready True, ready False
  get_app_config("catalogue")                 <CatalogueConfig: catalogue>
  get_model("catalogue", "Book")              the class catalogue.Book
  get_registered_model("catalogue", "Book")   the class catalogue.Book
  get_models()                                [loans.Loan, catalogue.Book, members.Member]
```

**Which applications are installed** can be asked once phase one is over: `Apps.get_app_config`, `Apps.get_app_configs` and `Apps.is_installed` need `apps_ready`. The flag waits for the whole list, so a configuration already made, as *catalogue*'s is at the first moment, is refused with the rest until every entry has one.

**A model** can be asked for once phase two is over: `Apps.get_model` and `Apps.get_models` need `models_ready`. The refusal is deliberate: until every models module has been imported, a model's reverse relations, the fields other models point at it with, are not all known ([The registry and its models](registry.md#asking-for-a-model-appsget_model-and-appsget_models)).

`Apps.get_model` accepts an argument, `require_ready=False`, that lowers its requirement to `apps_ready`, and imports the application's models module there and then if phase two has not reached it yet (`django/apps/registry.py:Apps.get_model`). In the block, *catalogue*'s `import_models` runs inside the import of *reservations*' models module, which asks for Book that way, and *catalogue*'s own turn has nothing under it.

```text recording=startup
django.setup() with INSTALLED_APPS = ["library.reservations", "library.catalogue"]: a models module asks for a later application's model with require_ready=False
...
        AppConfig.import_models  (reservations)
          import library.reservations.models
            Apps.get_model("catalogue", "Book", require_ready=False)  apps_ready True, models_ready False
              AppConfig.import_models  (catalogue)
                import library.catalogue.models
                  ModelBase.__new__  (class Book)
                    Apps.register_model(catalogue.Book)
              AppConfig.get_model("Book", require_ready=False)  (catalogue)
            ModelBase.__new__  (class Reservation)
              Apps.register_model(reservations.Reservation)
        AppConfig.import_models  (catalogue)
        AppConfig.ready  (reservations)
        ...
```

`get_user_model` asks for the user model this way, which is what allows it to be fetched while models are still being imported (`django/contrib/auth/__init__.py:get_user_model`).

**`Apps.get_registered_model` tests no flag.** It looks in the dictionary of registered classes and raises `LookupError` if the class is not there yet (`django/apps/registry.py:Apps.get_registered_model`). It is the one lookup that can be made at any moment, and what it answers depends on the order of imports.

**During `ready`, `Apps.ready` is still false.** The registry's lookups do not test it: they test the other two flags, which are true by then.

> **Trap.** A query executed before `Apps.ready` is set, in a `ready` method or as a module is imported, draws a `RuntimeWarning`, "Accessing the database during app initialization is discouraged", unless `Apps.set_installed_apps` or `Apps.set_available_apps` is in effect, as in a test that changes the installed applications (`django/db/backends/utils.py:CursorWrapper._execute`). The warning is worth heeding: a `ready` method runs during the startup of every management command, so `manage.py test` still executes its queries against the production database (`docs/ref/applications.txt`).
