---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Overriding settings

How a setting is changed in a process that has already started: `override_settings` wraps the current settings in a `UserSettingsHolder`, and sends the signal `setting_changed` so that whatever was built from the old value can be thrown away. `Apps.set_installed_apps` does the same for the app registry.

Django is written on the assumption that settings do not change once they are loaded, and a production process never needs them to. A test does. One test wants debug mode on, the next wants a different cache, a third wants an application installed that the project does not have. The machinery for this lives partly in `django/conf/`, where the settings objects are built to be stacked, and partly in `django/test/`, which does the stacking.

## Why assigning is not enough

A value read from the settings can end up in three places, and an assignment to `settings` reaches only the first.

The first is the proxy's own cache of values, which `LazySettings.__setattr__` keeps correct: it drops the kept value for the name being assigned ([The settings object](settings.md#writes-go-through-the-proxy-too)).

The second is every object that was built from a setting and then kept. The template engines are built from `TEMPLATES` on first use and held by `django.template.engines`. The default time zone is computed from `TIME_ZONE` once. The list of password hashers is built from `PASSWORD_HASHERS` once. A file storage works out its location from `MEDIA_ROOT` the first time it is asked and remembers it. None of these looks at the setting again.

Not every reader is like that. The handler reads `settings.ROOT_URLCONF` afresh for each request, and an assignment to it is seen by the next one (`django/core/handlers/base.py:BaseHandler.get_response`). Which settings are which can only be learned from the code that reads them.

The third is outside Python altogether: loading the settings put `TIME_ZONE` into the process's environment and had the C library read it.

Changing a setting properly therefore means telling everything in the second and third groups, and that needs a protocol.

## What `override_settings` does

`override_settings` is used around a block of code, as a context manager or a decorator. On the way in it does three things, in `override_settings.enable` (`django/test/utils.py:override_settings.enable`).

1. It makes a `UserSettingsHolder` whose `default_settings` is the object the proxy wraps now, and sets each overridden name on the holder.
2. It makes the holder the proxy's wrapped object. Assigning `_wrapped` clears every value kept on the proxy.
3. For each overridden name it sends `setting_changed`, with the name, the new value and `enter=True`.

On the way out, `override_settings.disable` puts the earlier wrapped object back and sends the signal again for each name, with the restored value and `enter=False`.

```text recording=startup
A setting is overridden for a block, and restored
    settings.DEBUG  -> False
    with override_settings(DEBUG=True):
      override_settings.enable
        UserSettingsHolder.__init__(a Settings)
        UserSettingsHolder.__setattr__("DEBUG", True)
        LazySettings.__setattr__("_wrapped", a UserSettingsHolder)
        setting_changed.send(setting="DEBUG", value=True, enter=True)  to 18 receivers
      LazySettings.__getattr__("DEBUG")
      the block runs: settings.DEBUG is True
      override_settings.disable
        LazySettings.__setattr__("_wrapped", a Settings)
        LazySettings.__getattr__("DEBUG")
        setting_changed.send_robust(setting="DEBUG", value=False, enter=False)  to 18 receivers
    settings.DEBUG  -> False
```

The holder is what makes this cheap and exact. It keeps only the names set on it, and passes a read of any other upper-case name to the object behind it (`django/conf/__init__.py:UserSettingsHolder.__getattr__`). Overrides nest by stacking holders, each one's `default_settings` being whatever was wrapped when it was made, and leaving a block restores exactly the object that was there before. A setting deleted inside an override is recorded in the holder's set of deleted names, so that the read does not fall through to the layer below and find it again (`django/conf/__init__.py:UserSettingsHolder.__delattr__`).

The two sends differ. Entering uses `Signal.send`: if a receiver raises, `enable` undoes the override and the exception is raised from there. Leaving uses `Signal.send_robust`, so that one failing receiver does not stop the rest from restoring their state, and afterwards raises the first exception any of them raised.

## The receivers repair what was built

`setting_changed` is an ordinary signal, defined beside the three signals of the request cycle (`django/core/signals.py`). Each receiver is called for every setting that changes, looks at the name, and returns at once unless it is one the receiver cares about. Most of them live in one file, `django/test/signals.py`.

| setting | what its receiver discards or redoes |
|---|---|
| `"CACHES"` | closes the caches and resets the handler that makes cache connections |
| `"DATABASE_ROUTERS"` | the list of router instances |
| `"TEMPLATES"`, `"DEBUG"`, `"INSTALLED_APPS"` | the template engines, the default `Engine`, and the default form renderer |
| `"INSTALLED_APPS"` | also the static files finders, the table of management commands, the applications' template directories and the translation catalogs |
| `"ROOT_URLCONF"` | the URL caches, the resolver kept for each URLconf among them, and any URLconf set for the thread |
| `"TIME_ZONE"` | the environment variable `"TZ"`, which the C library is made to read again, and the cached default time zone |
| `"TIME_ZONE"`, `"USE_TZ"` | the time zone of each database connection that has been made |
| `"LANGUAGES"`, `"LANGUAGE_CODE"`, `"LOCALE_PATHS"` | the default and active translations; for the first and the last, the catalogs too |
| a format setting, `"USE_THOUSAND_SEPARATOR"` | the cache of localized formats |
| `"STORAGES"`, `"STATIC_ROOT"`, `"STATIC_URL"` | the storage handler, and the lazy default and static files storages |
| `"STATICFILES_DIRS"`, `"STATIC_ROOT"` | the static files finders |
| `"SERIALIZATION_MODULES"` | the table of serializers |
| `"FORM_RENDERER"` | the default form renderer |
| `"AUTH_PASSWORD_VALIDATORS"` | the default password validators |
| `"AUTH_USER_MODEL"` | the registry's caches, and the user model that the auth modules bound to a module-level name as they were imported |
| `"LOGGING"`, `"LOGGING_CONFIG"` | runs `configure_logging` again |
| `"DATABASES"` | nothing: it warns that overriding this setting can lead to unexpected behaviour |

*The receivers of `setting_changed` in `django/test/signals.py`, by the names they compare the changed setting's with.*

Others are connected by the code that owns the cache, and these are some of them. The password hashers clear their cached list for `PASSWORD_HASHERS` (`django/contrib/auth/hashers.py:reset_hashers`). The translation machinery clears its caches of supported languages (`django/utils/translation/trans_real.py:reset_cache`). Each `FileSystemStorage` connects a method of its own when it is made, to forget its computed location and URL (`django/core/files/storage/filesystem.py:FileSystemStorage.__init__`). The `_meta` of a swappable model connects one that forgets whether the model is swapped out (`django/db/models/options.py:Options.setting_changed`). The task backends are reset for `TASKS` (`django/tasks/signals.py:clear_tasks_handlers`). The messages application connects its receiver in its `ready` method (`django/contrib/messages/apps.py:MessagesConfig.ready`).

Two things about this list matter more than its entries.

**The receivers belong to the test framework.** The receivers in `django/test/signals.py` are connected when that module is imported, and it is imported with `django.test`. In the recorded process, one receiver was connected when `django.setup` returned, and the rest arrived with the import of `django.test`; the recording lists them all, and the first of them are these.

```text recording=startup
The receivers of setting_changed in this process, in the order they were connected
    connected when django.setup() returned: 1
      reset_cache  (django.utils.translation.trans_real)
    connected by importing django.test:
      clear_cache_handlers  (django.test.signals)
      update_installed_apps  (django.test.signals)
      update_connections_time_zone  (django.test.signals)
      ...
```

A serving process has no reason to import `django.test`, and nothing in it would send the signal if it did: every send of `setting_changed` in Django's source is in `django/test/`, and `LazySettings.__setattr__` sends nothing.

**It is a list of what Django knows to cache, not a guarantee.** A setting with no receiver is one whose readers are believed to read it afresh each time, or one that cannot safely be changed. `MIDDLEWARE` has no receiver: a handler builds its chain once, and the test client's handler builds its own at its first request (`django/test/client.py:ClientHandler.__call__`). `DATABASES` has one that only warns, because the connections are not rebuilt.

## `INSTALLED_APPS`: the registry is populated again

`INSTALLED_APPS` is the one setting whose override changes the app registry, and `override_settings.enable` handles it first, before it touches the settings, so that a list that cannot be loaded leaves the settings as they were.

`Apps.set_installed_apps` requires a registry that is ready. It pushes the current dictionary of application configurations onto a stack, `Apps.stored_app_configs`, empties the registry's view of what is installed, sets its three flags and `Apps.loading` back to false, and calls `Apps.populate` with the new list (`django/apps/registry.py:Apps.set_installed_apps`). All three phases run again.

```text recording=startup
INSTALLED_APPS is overridden for a block
    with override_settings(INSTALLED_APPS=["library.loans", "library.catalogue"]):
      override_settings.enable
        Apps.set_installed_apps
          Apps.populate
            AppConfig.create("library.loans")
            AppConfig.create("library.catalogue")
            AppConfig.import_models  (loans)
            AppConfig.import_models  (catalogue)
            LoansConfig.ready  (loans)
            AppConfig.ready  (catalogue)
```

The recording shows what does and does not happen a second time.

New `AppConfig` objects are made for every entry, and **every `ready` method runs again**. A `ready` method therefore has to be safe to run more than once in a test process. Connecting a signal receiver is: `Signal.connect` does not add a receiver whose key, the identifier it was connected with or else its own identity, is already connected for the same sender (`django/dispatch/dispatcher.py:Signal.connect`).

No model is imported or registered again. The models modules are already imported, so `AppConfig.import_models` finds them in `sys.modules`, and `Apps.set_installed_apps` leaves the registry's record of model classes, `Apps.all_models`, as it was. Its docstring gives the reason: imports cannot be replayed safely, so a model stays registered once it has been imported, even when its application is no longer installed. A model of an application that an override removes is still in `all_models`, and is no longer returned by `Apps.get_models`, which goes through the installed applications.

`Apps.unset_installed_apps` pops the stack and sets the flags true again. It runs nothing.

A lighter tool exists for a test that only wants fewer applications. `Apps.set_available_apps` replaces the dictionary of configurations with the subset whose names are given. It imports nothing and calls no `ready`; `TransactionTestCase` uses it for its `available_apps` attribute (`django/apps/registry.py:Apps.set_available_apps`).
