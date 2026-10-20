---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Overriding settings

`override_settings` changes a setting in a process that has already started: it wraps the current settings in a `UserSettingsHolder`, and sends the signal `setting_changed` so that whatever was built from the old value can be discarded or redone. For `INSTALLED_APPS`, `Apps.set_installed_apps` repopulates the app registry.

Once `django.setup` has returned, Django treats the settings as constants of the process ([Settings, apps and startup](../startup.md#settings-and-the-registry-are-constants-of-the-process)), and its documentation asks an application not to alter them at runtime (`docs/topics/settings.txt`). A test does. One test wants debug mode on, the next wants a different cache, a third wants an application installed that the project does not have. `django/conf/` builds the settings objects to be stacked, and `django/test/` stacks them.

## Why assigning is not enough

A value read from the settings can end up in three places, and an assignment to `settings` reaches only the first.

The first is the proxy's own cache of values, which `LazySettings.__setattr__` keeps correct: it drops the kept value for the name being assigned ([The settings object](settings.md#writes-go-through-the-proxy-too); `django/conf/__init__.py:LazySettings.__setattr__`).

The second is every object that was built from a setting and then kept, the template engines among them. The default time zone is computed from `TIME_ZONE` once. The list of password hashers is built from `PASSWORD_HASHERS` once. A `FileSystemStorage` given no location works one out from `MEDIA_ROOT` the first time it is asked and remembers it. None of these looks at the setting again (`django/template/utils.py:EngineHandler.templates`, `django/utils/timezone.py:get_default_timezone`, `django/contrib/auth/hashers.py:get_hashers`, `django/core/files/storage/filesystem.py:FileSystemStorage.base_location`).

Not every reader is like that. The handler reads `settings.ROOT_URLCONF` afresh for each request, and an assignment to it is seen by the next one (`django/core/handlers/base.py:BaseHandler.get_response`). Which settings are which is learned from the code that reads them.

The third is outside Python altogether: where the platform's `time` module has the function `"tzset"`, loading a settings module put `TIME_ZONE` into the process's environment and had the C library read it (`django/conf/__init__.py:Settings.__init__`).

Changing a setting properly therefore means telling everything in the second and third groups, and that needs a protocol.

## `override_settings`: entering and leaving

`override_settings` is used around a block of code, as a context manager or a decorator ([Settings for one test: `override_settings` and `TestContextDecorator`](../testing/test-decorators.md)). On the way in `override_settings.enable` does three things, four for `INSTALLED_APPS` (`django/test/utils.py:override_settings.enable`).

1. It makes a `UserSettingsHolder` whose `default_settings` is the object the proxy wraps now, and sets each overridden name on the holder.
2. It makes the holder the proxy's wrapped object. Assigning `_wrapped` clears every value kept on the proxy.
3. For each overridden name it sends `setting_changed`, with the name, the new value and `enter=True`.

On the way out, `override_settings.disable` puts the earlier wrapped object back and sends the signal again for each name, with the restored value and `enter=False` (`django/test/utils.py:override_settings.disable`).

Under `override_settings(DEBUG=True)` the holder is made over the project's `Settings`. The read of `settings.DEBUG` inside the block reaches `LazySettings.__getattr__`, though the setting was read just before the block, because assigning `_wrapped` emptied the kept values; and the signal goes out by `Signal.send` on the way in and by `Signal.send_robust` on the way out.

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

Leaving uses `send_robust` so that one failing receiver does not stop the rest from restoring their state; once all have been called, `disable` raises the first exception any of them raised.

Entering is stricter. If a receiver raises, `enable` keeps the exception as `override_settings.enable_exception` and calls `disable` there and then, which raises it, so the code the override was to wrap never runs (`django/test/utils.py:override_settings.enable`). Under the raise, `disable` stands nested in `enable` and sends the leaving signal for `APPEND_SLASH` and for `PREPEND_WWW`, whose entering signal was never sent.

```text recording=startup
A receiver of setting_changed, refuse, raises as the first of two overridden settings is entered
    with override_settings(APPEND_SLASH=False, PREPEND_WWW=True):
      override_settings.enable
        ...
        setting_changed.send(setting="APPEND_SLASH", value=False, enter=True)  to 19 receivers
          refuse(setting="APPEND_SLASH", enter=True)
            raises ValueError: APPEND_SLASH may not be overridden
        override_settings.disable
          LazySettings.__setattr__("_wrapped", a Settings)
          LazySettings.__getattr__("APPEND_SLASH")
          setting_changed.send_robust(setting="APPEND_SLASH", value=True, enter=False)  to 19 receivers
            refuse(setting="APPEND_SLASH", enter=False)
          LazySettings.__getattr__("PREPEND_WWW")
          setting_changed.send_robust(setting="PREPEND_WWW", value=False, enter=False)  to 19 receivers
            refuse(setting="PREPEND_WWW", enter=False)
          raises ValueError: APPEND_SLASH may not be overridden
      -> raises ValueError: APPEND_SLASH may not be overridden
    settings.APPEND_SLASH  -> True
    settings.PREPEND_WWW  -> False
```

## Nested overrides: a stack of holders

Overrides nest by stacking holders. A holder passes a read of a setting not set on it to its `default_settings` ([The settings object](settings.md#settingsconfigure-settings-without-a-module)), and an override's holder has for its `default_settings` whatever the proxy wrapped when it was made: the holder of the override it is nested in or, at the bottom, what the settings were loaded into, for a project with a settings module the `Settings`, that module over the defaults (`django/conf/__init__.py:UserSettingsHolder.__getattr__`). Leaving a block puts back exactly the object that was there before: the inner override, left first, puts back the outer's holder, and the outer puts back the `Settings`.

The figure stacks two overrides, `override_settings(DEBUG=True)` and inside it `override_settings(APPEND_SLASH=False)`. Follow each read down from the proxy to the layer where it stops, and see at the right the signal each override sends as its holder is pushed and popped.

```text figure=the-holders
the stack, from the proxy down     reads, from the proxy down                          setting_changed

settings, the proxy                APPEND_SLASH   DEBUG        TIME_ZONE   TIME_ZONE,
  wraps                                                                    after del
                                        |           |             |            |
the inner override's holder        stops: False     |             |      stops: AttributeError   pushed second: APPEND_SLASH, enter=True
APPEND_SLASH = False                                |             |                              popped first: APPEND_SLASH, enter=False
deleted: TIME_ZONE, after del                       |             |
  its default_settings                              |             |
the outer override's holder                    stops: True        |                              pushed first: DEBUG, enter=True
DEBUG = True                                                      |                              popped second: DEBUG, enter=False
  its default_settings                                            |
the Settings                                                stops: its value
the project's settings module
over the defaults
```

*Two overrides, one inside the other, over the `Settings`; each holder's `default_settings` is the layer below it. A column is a read of the name at its head, falling from the proxy until a layer has the name or holds it as deleted, the last after `TIME_ZONE` was deleted inside both overrides. At the right, the signal each override sends as its holder is pushed and popped.*

Each holder that a read passes through adds a line `UserSettingsHolder.__getattr__`: none for `settings.APPEND_SLASH`, which the inner holder has, one for `settings.DEBUG`, and two for `settings.TIME_ZONE`, which only the `Settings` has.

```text recording=startup
Inside both overrides: a read falls through the holders until one has the name
    settings.APPEND_SLASH
      LazySettings.__getattr__("APPEND_SLASH")
      -> False
    settings.DEBUG
      LazySettings.__getattr__("DEBUG")
        UserSettingsHolder.__getattr__("DEBUG")  on the holder of APPEND_SLASH
      -> True
    settings.TIME_ZONE
      LazySettings.__getattr__("TIME_ZONE")
        UserSettingsHolder.__getattr__("TIME_ZONE")  on the holder of APPEND_SLASH
          UserSettingsHolder.__getattr__("TIME_ZONE")  on the holder of DEBUG
      -> 'America/Chicago'
```

`del settings.TIME_ZONE` inside both overrides marks the name deleted on the inner holder alone, and a read of it then stops there with `AttributeError`, though the `Settings` below still has it (`django/conf/__init__.py:UserSettingsHolder.__delattr__`).

## The receivers of `setting_changed`

`setting_changed` is an ordinary signal, defined beside the three signals of the request cycle, `request_started`, `request_finished` and `got_request_exception` (`django/core/signals.py`). Each receiver is called whatever the setting, looks at the name, and returns unless it is one the receiver cares about. Most of them live in one file, `django/test/signals.py`.

| setting | what its receiver discards or redoes |
|---|---|
| `"CACHES"` | closes this thread's caches and resets the handler that makes cache connections |
| `"DATABASE_ROUTERS"` | the list of router instances |
| `"TEMPLATES"`, `"DEBUG"`, `"INSTALLED_APPS"` | the template engines, the default `Engine`, and the default form renderer |
| `"INSTALLED_APPS"` | also the static files finders, the table of management commands, the applications' template directories and the translation catalogs |
| `"ROOT_URLCONF"` | the URL caches, the resolver kept for each URLconf among them, and any URLconf set for the thread |
| `"TIME_ZONE"` | the cached default time zone and, where there is `"tzset"`, the environment variable `"TZ"`, which the C library is made to read again |
| `"TIME_ZONE"`, `"USE_TZ"` | the time zone of each of this thread's database connections |
| `"LANGUAGES"`, `"LANGUAGE_CODE"`, `"LOCALE_PATHS"` | the default and active translations; for the first and the last, the catalogs too |
| a format setting, `"USE_THOUSAND_SEPARATOR"` | the cache of localized formats |
| `"STORAGES"`, `"STATIC_ROOT"`, `"STATIC_URL"` | the storage handler, and the lazy default and static files storages |
| `"STATICFILES_DIRS"`, `"STATIC_ROOT"` | the static files finders |
| `"SERIALIZATION_MODULES"` | the table of serializers |
| `"FORM_RENDERER"` | the default form renderer |
| `"AUTH_PASSWORD_VALIDATORS"` | the default password validators |
| `"AUTH_USER_MODEL"` | the registry's caches, and the user model that the auth modules bound to a module-level name as they were imported |
| `"LOGGING"`, `"LOGGING_CONFIG"` | runs `configure_logging` again |
| `"DATABASES"` | nothing: on entering, it warns that overriding this setting can lead to unexpected behaviour |

*The receivers of `setting_changed` in `django/test/signals.py`, by the names of the settings each one tests for.*

Others are connected by the code that owns what they discard, among them the password hashers, the translation machinery, each `FileSystemStorage` as it is made, a swappable model's `_meta`, the task backends, and the messages application in its `ready` (`django/contrib/auth/hashers.py:reset_hashers`, `django/utils/translation/trans_real.py:reset_cache`, `django/core/files/storage/filesystem.py:FileSystemStorage.__init__`, `django/db/models/options.py:Options.setting_changed`, `django/tasks/signals.py:clear_tasks_handlers`, `django/contrib/messages/apps.py:MessagesConfig.ready`).

Two things about these lists matter more than their entries.

**Most receivers arrive with the test framework.** The receivers in `django/test/signals.py` are connected when that module is imported, and it is imported with `django.test`. The project *library* installs none of Django's contrib applications, and when its `django.setup` returned one receiver was connected, the translation machinery's; a project with the auth and messages applications has theirs too. Every other receiver in the process came with the import of `django.test`.

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

**The lists are not a guarantee.** `MIDDLEWARE` has no receiver: a handler builds its chain once, and the test client's handler builds its own at its first request, from the `MIDDLEWARE` in force then (`django/test/client.py:ClientHandler.__call__`). `DATABASES` has one that only warns, because the connections are not rebuilt (`django/utils/connection.py:BaseConnectionHandler.settings`).

## `INSTALLED_APPS`: the registry is populated again

`INSTALLED_APPS` is the one setting whose override refills the app registry, and `override_settings.enable` handles it first, before it touches the settings, so that a list that cannot be loaded leaves the settings as they were (`django/test/utils.py:override_settings.enable`).

`Apps.set_installed_apps` requires a registry that is ready. It pushes the current dictionary of application configurations onto a stack, `Apps.stored_app_configs`, empties the registry's view of what is installed, sets its three flags and `Apps.loading` back to false, and calls `Apps.populate` with the new list, so that all three phases run again ([Populating the app registry](populate.md)) (`django/apps/registry.py:Apps.set_installed_apps`); on leaving, `Apps.unset_installed_apps` pops the stack, sets the flags true again, and runs no phase (`django/apps/registry.py:Apps.unset_installed_apps`). `Apps.set_available_apps`, which a `TransactionTestCase` with `available_apps` uses, only narrows the installed applications to a subset, importing nothing and calling no `ready` ([Emptying the tables after each test: `TransactionTestCase`](../testing/transaction-test-case.md#fewer-applications-available_apps)) (`django/apps/registry.py:Apps.set_available_apps`).

In this trace an import of one of the project's modules, or a call of `Apps.register_model`, would stand as a line of its own, as it does in a trace of `django.setup`; under each `AppConfig.import_models` there is none. The line `UserSettingsHolder.__init__`, the holder made over the `Settings`, comes only after `Apps.populate` has run its three phases.

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
        UserSettingsHolder.__init__(a Settings)
        ...
```

The models modules are already imported, so `AppConfig.import_models` finds them in `sys.modules`, and `Apps.set_installed_apps` leaves the registry's record of model classes, `Apps.all_models`, as it was. A model of an application that an override removes is still in `all_models`, and is no longer returned by `Apps.get_models`, which goes through the installed applications. An override can still add models, when it installs an application whose models module was never imported, and they stay in `all_models` after `Apps.unset_installed_apps` ([The registry and its models](registry.md#two-maps-appsapp_configs-and-appsall_models)) (`django/apps/registry.py:Apps.set_installed_apps`).

New `AppConfig` objects are made for every entry, and every `ready` method runs on its new configuration.

> **Trap.** A `ready` that connects a method of its configuration connects it again under the override, bound to the new configuration, and a send inside the override calls it twice. `Signal.connect` adds a receiver only if its key is not already there, and a bound method's key is made from its object as well as its function, so the method of the new configuration is a receiver of its own; a function defined at a module's top level, or a dispatch uid, gives the same key each time (`django/dispatch/dispatcher.py:_make_id`, `django/dispatch/dispatcher.py:Signal.connect`).

The project's *notices* application connects three receivers to a signal of its own, *book_returned*, in its `ready`: *send_notice*, a function of its signals module; *count_return*, a method of its configuration; and *remind*, a function defined inside `ready`. Inside an override that installs it again, the list has a line of *count_return* for each configuration and one of *send_notice*.

```text recording=startup
The same ready run again by override_settings(INSTALLED_APPS=[...]), and what book_returned keeps inside the block and after it
    with override_settings(INSTALLED_APPS=["library.notices"]):
            ...
            NoticesConfig.ready  (notices)
              Signal.connect(send_notice)
              Signal.connect(NoticesConfig.count_return, bound to the second NoticesConfig)
              Signal.connect(NoticesConfig.ready.<locals>.remind)
      book_returned.receivers, after gc.collect()
        send_notice                                                     alive
        NoticesConfig.count_return, bound to the first NoticesConfig    alive
        NoticesConfig.count_return, bound to the second NoticesConfig   alive
        NoticesConfig.ready.<locals>.remind                             dead: its weak reference returns None
      the receivers a send would call: 3
      override_settings.disable
        Apps.unset_installed_apps
    book_returned.receivers, after gc.collect()
      send_notice                                                     alive
      NoticesConfig.count_return, bound to the first NoticesConfig    alive
      NoticesConfig.count_return, bound to the second NoticesConfig   dead: its weak reference returns None
      NoticesConfig.ready.<locals>.remind                             dead: its weak reference returns None
    the receivers a send would call: 2
```

Once the override is left and nothing holds the second configuration, its method is dead, and a send calls two receivers again. *remind* is dead from the start: a receiver is held by a weak reference unless it is connected otherwise, and nothing holds *remind* once `ready` has returned ([Signals: `Signal`, receivers and sending](../services/signals.md#connecting-a-receiver-signalconnect)).
