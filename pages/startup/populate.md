---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Populating the app registry

`Apps.populate` turns the list in `settings.INSTALLED_APPS` into `AppConfig` objects, imports each application's models, and calls each `AppConfig.ready`: three phases, each run over every application before the next begins, and three flags that say how far it has got.

An entry of `INSTALLED_APPS` is a string. Before Django can use an application it needs more than that: the package the string names, a short unique label to file the application's models under, the directory its templates and static files are found in, the classes of its models. `Apps.populate` gets all of it by importing, and most of what it has to be careful about comes from that. Importing runs a project's own code, in an order the project only partly controls, while the registry that code might want to consult is half built.

## Once, by one thread

`Apps.populate` is written to be called more than once and to do its work once (`django/apps/registry.py:Apps.populate`).

A call that finds `Apps.ready` true returns immediately. Otherwise it takes a lock, `Apps._lock`, and tests the flag again, because a server may start several threads before any of them has made the handler, and two can arrive together. The second waits for the first to finish and then finds nothing to do.

The lock is re-entrant, so it does not stop the same thread from arriving twice, and that case is refused outright. The method sets `Apps.loading` as it starts, and a call that finds it already set raises `RuntimeError`, saying that `populate` isn't reentrant. The purpose is to keep `ready` methods from running twice. It happens when code that is imported during the phases calls `django.setup` itself.

It also happens for a less obvious reason. `populate` sets `loading` as it starts and does not clear it when a phase raises. The registry is then left with `loading` true and `ready` false, and the next call raises the reentrancy error in place of the original one. A failed startup is not retried in the same process.

```text recording=startup
django.setup() with an entry that cannot be imported: INSTALLED_APPS = ["library.loans", "library.no_such_app"]
    django.setup()  -> raises ModuleNotFoundError: No module named 'library.no_such_app'
    apps.loading True, apps_ready False, ready False
    django.setup(), again  -> raises RuntimeError: populate() isn't reentrant
```

The first exception is the one that says what is wrong. Where a server's log shows only the second, the first was raised earlier in the same process.

## Phase one: an `AppConfig` for each entry

The first phase calls `AppConfig.create` on each entry in turn, which works out what kind of entry it is by trying to import it (`django/apps/config.py:AppConfig.create`). An entry that is already an `AppConfig` object is used as it is; the registries that migrations build are populated that way.

**The entry is a package.** If the entry can be imported as a module, it is the application's package. Django then looks inside it for a submodule named `apps`, and in that for subclasses of `AppConfig`, leaving aside any that set `default = False`. A class that is the only one there is the application's configuration without having to say so. Among several, the one whose `default` is true is chosen, and two such are an error; the attribute may be inherited, and a class that the module only imports counts like one it defines. Where that leaves no class, because there is no `apps` submodule, or nothing in it, or several classes and none marked, the application gets a plain `AppConfig`.

**The entry is the path of a class.** If importing the entry as a module fails, it is tried as the dotted path of a configuration class. The class must be a subclass of `AppConfig` and must have a `name` attribute, the dotted path of the application's package, which is then imported.

**The entry is neither.** `create` then works to raise a useful error. A dotted entry whose last part begins with a capital letter was probably meant as a class. Its module is imported, which may raise an error of its own; if it does not, an `ImportError` says the module has no such class and lists any configuration classes it does have. For any other entry the import is run again, so that its own exception is the one that is raised.

The recorded project has an entry of each kind that succeeds: a package with an `apps` module, the path of a class, and a package with no `apps` module. For each, the application's package is imported, and its `apps` module where one is involved, and then the configuration object is made. The import of library.probe is the project's own: it is the module that puts to the registry the questions shown further down.

```text recording=startup
django.setup() in a new process
    ...
      Apps.populate
        AppConfig.create("library.loans")
          import library.loans
          import library.loans.apps
            import library.probe
          AppConfig.__init__("library.loans", app_module)  (LoansConfig)
        AppConfig.create("library.catalogue.apps.CatalogueConfig")
          import library.catalogue
          import library.catalogue.apps
          AppConfig.__init__("library.catalogue", app_module)  (CatalogueConfig)
        AppConfig.create("library.members")
          import library.members
          AppConfig.__init__("library.members", app_module)  (AppConfig)
```

The admin shows why an entry may be either a package or a class. Its `apps` module defines two configuration classes, `SimpleAdminConfig` and a subclass of it, `AdminConfig`, which sets `default = True`. The entry `"django.contrib.admin"` therefore gets `AdminConfig`, whose `ready` goes looking for every application's `admin` module; a project that wants an admin without that search names the other class by its path (`django/contrib/admin/apps.py:AdminConfig`).

`AppConfig.__init__` then fixes the facts about the application that the rest of Django reads (`django/apps/config.py:AppConfig.__init__`).

| attribute | what it is | where it comes from |
|---|---|---|
| `name` | the dotted path of the package | the entry, or the class's `name` |
| `label` | the short name models and migrations are filed under | the class, or else the last part of `name`; it must be a valid identifier |
| `verbose_name` | the name shown to people | the class, or else the label in title case |
| `path` | the application's directory | the class, or else the package's one location on disk |
| `module` | the imported package | the import |
| `models_module`, `models` | the models module, and the model classes by name | nothing yet: the second phase sets them |

*The attributes of an `AppConfig`. A subclass may declare the middle three on the class; the constructor fills in each one the class does not have.*

The directory matters because the template loaders, the static files finders, the translation machinery and the search for management commands all look inside each application's `path`. A package spread over several directories has no single one, and `AppConfig._path_from_module` raises `ImproperlyConfigured` for it, asking for a configuration class that states `path`.

Back in `populate`, each configuration is filed in `Apps.app_configs` under its label and given a reference to the registry. Two applications with the same label are refused there, and after the loop two with the same name. Then `Apps.apps_ready` is set.

## Phase two: every models module is imported

The second phase calls `AppConfig.import_models` on each configuration, in the order of the setting (`django/apps/config.py:AppConfig.import_models`). The method does two small things. It points `AppConfig.models` at the registry's dictionary of model classes for the application's label. And if the application's package has a submodule called `models`, it imports it.

Importing is all that is needed, because a model registers itself. The class statement of a model runs the metaclass `ModelBase.__new__`, which ends by calling `Apps.register_model` with the new class (`django/db/models/base.py:ModelBase.__new__`). [The registry and its models](registry.md) follows that call.

The order in which models are registered is the order in which their class statements finish, which the phase controls only loosely. A models module that imports another application's models module causes those models to be registered during its own turn; when the other application's turn comes, its module is already imported and nothing happens.

A model defined in some other module of an application is registered when that module is imported, whenever that is. The phase imports `models` and nothing else, so an application whose models are spread over several files makes `models` a package and imports them all from its `__init__`.

When every application has had its turn, the registry's caches are cleared and `Apps.models_ready` is set.

## Phase three: every `ready` runs

The third phase calls `AppConfig.ready` on each configuration, in the same order. The base method does nothing (`django/apps/config.py:AppConfig.ready`). When all have returned, `Apps.ready` is set, and so is `Apps.ready_event`, a `threading.Event` that the development server's reloader waits on before it starts watching files (`django/utils/autoreload.py:BaseReloader.wait_for_apps_ready`).

`ready` is where an application connects itself to the parts of Django that keep process-wide lists. What Django's own applications do there shows the range.

| application | what its `ready` does |
|---|---|
| admin | registers system checks; `AdminConfig.ready` also runs `autodiscover`, which imports the `admin` module of every application |
| auth | connects receivers to `post_migrate` that create and rename permissions, connects the receiver that records a user's last login, registers system checks |
| contenttypes | connects receivers to `pre_migrate` and `post_migrate` that keep the table of content types in step with the models, registers system checks |
| messages | connects a receiver to `setting_changed` |
| staticfiles | registers system checks |
| sites | connects a receiver to `post_migrate` that creates the default site, registers a system check |
| postgres | among other things, registers lookups on `django.db.models.CharField` and `django.db.models.TextField`, a serializer for migrations, and the handlers that teach a new connection PostgreSQL's types |
| gis | registers the GeoJSON serializer |

*What the `ready` method of each contrib application does. The sessions application and the others not listed define none.*

Each of these needs something the earlier phases could not give: a model class from another application, or simply the assurance that it runs once, after everything is importable. The auth application's `ready` is the plainest case. It asks for the user model, which may belong to any application, to see whether it has a `last_login` field (`django/contrib/auth/apps.py:AuthConfig.ready`).

## What the registry answers, phase by phase

The three flags are not only a record of progress. The registry's methods test them, and a question asked too early is refused with `AppRegistryNotReady` and not answered wrongly from a half-filled registry (`django/apps/registry.py:Apps.check_apps_ready`, `django/apps/registry.py:Apps.check_models_ready`).

In the recorded project, four pieces of code ask the registry the same four questions, at four moments of one `django.setup`: a package being imported in phase one, a models module being imported at the start of phase two, another at the end of it, and a `ready` method. Under each moment are the registry's three flags as they stood, and then each question with its answer; an answer that is an exception is given as its class and its message.

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

Taken one question at a time, the answers give the rules.

**Which applications are installed** can be asked once phase one is over: `Apps.get_app_config`, `Apps.get_app_configs` and `Apps.is_installed` need `apps_ready`. Inside phase one even an application whose configuration has already been made cannot be fetched, because the list is not complete.

**A model** can be asked for once phase two is over: `Apps.get_model` and `Apps.get_models` need `models_ready`. At the third moment above, the class exists and is registered, and `get_model` still refuses to return it. The refusal is deliberate. Until every models module has been imported, a model's reverse relations, the fields other models point at it with, are not all known, and code handed the class would see a model that is not yet whole.

**`Apps.get_registered_model` tests no flag.** It looks in the dictionary of registered classes and raises `LookupError` if the class is not there yet. It is the one lookup that can be made at any moment, and its answer depends on import order, as the second and third moments show.

**During `ready`, `Apps.ready` is still false.** It is set after the last `ready` method returns. The registry's lookups do not test it: they test the other two flags, which are true by then. What `ready` governs is narrower. `populate` returns early on it, `Apps.clear_cache` expires the models' own caches only when it is true, `Apps.set_installed_apps` refuses to run without it, and a database cursor consults it. A query executed during startup while it is false, in a `ready` method or as a module is imported, draws a `RuntimeWarning` that says to keep away from the database during application initialization; the cursor makes an exception of the time a test has the list of applications overridden, when the flag is false for a moment too (`django/db/backends/utils.py:CursorWrapper._execute`).

`Apps.get_model` accepts an argument, `require_ready=False`, that lowers its requirement to `apps_ready`, and imports the application's models module there and then if phase two has not reached it yet. `get_user_model` uses it, which is what allows the user model to be fetched while models are still being imported (`django/contrib/auth/__init__.py:get_user_model`).

Before any of this, in a process where `django.setup` has not been called at all, the first thing to fail is usually a model's class statement: `ModelBase.__new__` asks the registry which application the model's module belongs to, and that needs `apps_ready`. [Who calls `django.setup`](callers.md#a-script) shows the error.
