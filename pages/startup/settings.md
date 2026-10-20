---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The settings object

`django.conf.settings` is a `LazySettings`: a proxy that imports the module named by `"DJANGO_SETTINGS_MODULE"` on the first read or write of any setting, builds a `Settings` from it over the defaults of `global_settings`, and keeps each value it has returned. `LazySettings.configure` fills it by hand instead, with a `UserSettingsHolder`.

A project's settings are an ordinary Python module, but no part of Django can import it by name, because the name arrives late: in an environment variable that the project's `manage.py` or `wsgi.py` sets, or in a `--settings` option that is parsed after much of Django has already been imported. Meanwhile modules all over the framework have written `from django.conf import settings` at their top. So `settings` cannot be the module. It is an object that exists from the moment `django.conf` is imported and becomes the settings when someone first needs one.

## `LazySettings._setup`: the first read loads

`LazySettings` is a `LazyObject`, Django's general lazy proxy, which holds what it stands for in `LazyObject._wrapped`, the marker `empty` until a subclass's `_setup` method puts something there ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)) (`django/utils/functional.py:LazyObject`). `LazySettings._setup`, which `LazySettings.__getattr__` calls when a setting is read and nothing is wrapped, reads the environment variable `"DJANGO_SETTINGS_MODULE"`. If the variable is unset or empty it raises `ImproperlyConfigured`, with a message that names the setting that was being read; otherwise it makes a `Settings` from the module's name and wraps it (`django/conf/__init__.py:LazySettings._setup`).

In the recording's project, *library*, which installs *loans*, *catalogue* and *members*, the first two reads of `settings.DEBUG` each begin in `LazyObject.__getattribute__`, through which every attribute read of a lazy object passes ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md#two-ways-in-__getattr__-and-the-special-methods)). Under the first, `_setup` makes a `Settings`, whose constructor imports the settings module, and assigns it to `_wrapped` through `LazySettings.__setattr__`: that assignment is how the loaded settings are put in place. The second read goes no further than `LazyObject.__getattribute__`.

```text recording=startup
...
settings.DEBUG, the first read of any setting
  LazyObject.__getattribute__("DEBUG")
  LazySettings.__getattr__("DEBUG")
    LazySettings._setup("DEBUG")
      Settings.__init__("library.settings")
        import library.settings
      LazySettings.__setattr__("_wrapped", a Settings)
  -> False
...
settings.DEBUG, again
  LazyObject.__getattribute__("DEBUG")
  -> False
...
```

Three things follow from loading on the first read.

Whoever reads or writes first, loads, and it need not be `django.setup`: a module that reads a setting at its top level loads the settings as it is imported.

An error in the settings module surfaces at that first read or write, wherever it is. If loading fails, nothing is wrapped, so the proxy is still empty and the next read tries again from the beginning.

And code that may run before there are settings can ask without loading them: the property `LazySettings.configured` is true when something is wrapped, and reading it loads nothing (`django/conf/__init__.py:LazySettings.configured`). `Signal.connect`, run as modules are imported, tests it before it reads `settings.DEBUG` to decide whether to validate the receiver (`django/dispatch/dispatcher.py:Signal.connect`).

Without the variable, `settings.configured` is false after the failed read of `settings.DEBUG` as before it, because nothing was wrapped; and the last line, the import of a models module, meets the settings' error and not the registry's.

```text recording=startup
No settings: DJANGO_SETTINGS_MODULE is not set, and settings.configure has not been called
    settings.configured  -> False
    settings.DEBUG  -> raises ImproperlyConfigured: Requested setting DEBUG, but settings are not configured. You must either define the environment variable DJANGO_SETTINGS_MODULE or call settings.configure() before accessing settings.
    settings.configured  -> False
    import library.catalogue.models  -> raises ImproperlyConfigured: Requested setting INSTALLED_APPS, but settings are not configured. You must either define the environment variable DJANGO_SETTINGS_MODULE or call settings.configure() before accessing settings.
```

A model's class statement asks the app registry which application it belongs to, and the registry reads `settings.INSTALLED_APPS` before it refuses with `AppRegistryNotReady`, so that missing settings are reported as such ([The registry and its models](registry.md#a-model-class-registers-itself)) (`django/apps/registry.py:Apps.check_apps_ready`).

## What `Settings.__init__` does

A `Settings` is a flat object with one attribute for each setting. Its constructor fills it in two layers, and refuses, warns about or acts on a few of the values (`django/conf/__init__.py:Settings.__init__`).

First it copies every upper-case name of `django/conf/global_settings.py` onto itself. Then it imports the project's module and copies every upper-case name of that module over them, adding each name to the set `Settings._explicit_settings`. The defaults are therefore not consulted when a setting is read: by then the project's value has replaced the default on the same object. From the set, `Settings.is_overridden` answers whether a value is the project's own or only the default.

A name is a setting if it is written in upper case, and nothing else is tested. A name in lower or mixed case is not copied and cannot be read through `settings`; any upper-case name is copied, whether Django knows a setting of that name or not. So `"BASE_DIR"`, which a new project's settings module computes for its own use, becomes a setting like any other, and a misspelt setting becomes an attribute that nothing reads, with the default still in place under the right name.

An `ImportError` for the settings module itself becomes `ImproperlyConfigured`; any other, such as one raised by an import inside the module, passes through unchanged. Five settings must each be a list or a tuple, or `ImproperlyConfigured` is raised: `"ALLOWED_HOSTS"`, `"INSTALLED_APPS"`, `"LOCALE_PATHS"`, `"SECRET_KEY_FALLBACKS"` and `"TEMPLATE_DIRS"`, which 1.10 removed as a setting and the constructor tests still (`docs/releases/1.10.txt`). The settings 6.1 deprecated that the module defines are each warned about with `RemovedInDjango2028Warning`, and a deprecated email setting defined beside `MAILERS` is refused instead (`django/conf/__init__.py:_check_email_settings_conflicts`).

> **Changed in 6.1.** `MAILERS` is new in 6.1, and the settings it replaces, `EMAIL_BACKEND` and the others of `DEPRECATED_EMAIL_SETTINGS`, are deprecated from then on (`django/conf/__init__.py:DEPRECATED_EMAIL_SETTINGS`). The settings module that `django-admin startproject` writes defines `MAILERS` (`django/conf/project_template/project_name/settings.py-tpl`).

Last, the constructor moves the time zone into the process. Where the platform's `time` module has the function `"tzset"`, and `TIME_ZONE` is not empty, it raises `ValueError` for a zone `zoneinfo.ZoneInfo` cannot find, puts the name in the environment variable `"TZ"`, and calls that function. From then on the C library's local time is in that zone, and so is everything in the process that takes its local time from there and not from Django: `datetime.datetime.now` called with no zone, and the times a `logging.Formatter` writes into log lines.

> **Why.** The move is made only where `time` has `"tzset"`, because, made everywhere, it breaks Windows, which has no such function (ticket 2315); there the process's time zone is left alone (`django/conf/__init__.py:Settings.__init__`, `docs/ref/settings.txt`).

## `django.conf.global_settings`, the defaults

`django/conf/global_settings.py` is a module of plain assignments, and it has to stay one: it is imported by `django.conf` itself, before there are settings, so it can import nothing that reads a setting. The translation functions are such a thing, which is why the module defines a function of its own, `gettext_noop`, that returns its argument, to mark the names of languages for translation (`django/conf/global_settings.py:gettext_noop`).

Not every setting has a default there: `ROOT_URLCONF` has none, and where the project does not set it either, reading it raises `AttributeError` (`django/conf/__init__.py:LazySettings.__getattr__`).

> **Trap.** `MANAGERS` does not follow a project's `ADMINS`. `global_settings` assigns it the very list it assigns to `ADMINS`, an empty one: it is computed from the default, once, and a project that sets `ADMINS` has not thereby set `MANAGERS` (`django/conf/global_settings.py:MANAGERS`).

## `LazySettings.__getattr__` keeps each value

Settings are read constantly, and a read that reached `LazySettings.__getattr__` every time would run its tests for the special cases below on each one. The method therefore ends by storing the value it found in the proxy's own instance dictionary, under the setting's name (`django/conf/__init__.py:LazySettings.__getattr__`).

Python calls a class's `__getattr__` only when the ordinary lookup has failed, and the ordinary lookup finds what is in the instance dictionary. So a read of a kept value never reaches `LazySettings.__getattr__`: as the first recording above shows, it ends in `LazyObject.__getattribute__`, which finds it.

The figure follows a read down from the proxy to where it stops: at the proxy's own attributes for a kept value, and otherwise at what the proxy wraps, or behind a holder.

```text figure=a-read
settings.DEBUG
  -> the proxy, a LazySettings
       its own attributes          a value kept from an earlier read is found here, and the read ends
       LazySettings.__getattr__    reached only when none is: loads the settings if nothing is wrapped,
                                   asks the wrapped object, keeps the answer among the proxy's attributes
  -> what it wraps, one of
       a Settings                  every default of global_settings, with the settings module's
                                   upper-case names set over them: one flat object
       a UserSettingsHolder        the names set on it; any other upper-case name not deleted is asked of
                                   the object behind it, its default_settings: global_settings by default,
                                   or the object wrapped before an override
```

*A read of a setting. A read that finds a value kept on the proxy ends there; any other goes through to the wrapped object and keeps on the proxy what it returns.*

Some values are changed before they are kept, and some reads are refused.

`MEDIA_URL` and `STATIC_URL`, when they are relative, have the script prefix put in front of them: a value that begins with neither a slash nor `"http://"` or `"https://"` is joined to what `get_script_prefix` returns at that moment, and the joined value is what is kept (`django/conf/__init__.py:LazySettings._add_script_prefix`, `django/urls/base.py:get_script_prefix`).

Look for `LazySettings._add_script_prefix` under the first of the two reads only, and for what the second returns after the prefix has changed.

```text recording=startup
settings.configure(STATIC_URL="static/"): a relative STATIC_URL read under two script prefixes keeps the first
    set_script_prefix("/first/")
    settings.STATIC_URL
      LazyObject.__getattribute__("STATIC_URL")
      LazySettings.__getattr__("STATIC_URL")
        LazySettings._add_script_prefix('static/')
          get_script_prefix
      -> '/first/static/'
    set_script_prefix("/second/")
    get_script_prefix()  -> '/second/'
    settings.STATIC_URL
      LazyObject.__getattribute__("STATIC_URL")
      -> '/first/static/'
```

> **Trap.** The documentation says that a relative `STATIC_URL` or `MEDIA_URL` is prefixed by the server-provided value of `"SCRIPT_NAME"` (`docs/ref/settings.txt`). It is prefixed by the script prefix in force at its first read, and kept: a later read returns that value whatever the prefix has become, until a write through the proxy drops it (`django/conf/__init__.py:LazySettings.__setattr__`, `django/conf/__init__.py:LazySettings.__delattr__`).

`SECRET_KEY` may not be empty, and this is where that is enforced: a read of an empty one raises `ImproperlyConfigured`. A project without a secret key therefore loads its settings without complaint, and fails at the first line that needs the key.

A read of a deprecated email setting is intercepted here too: it raises `AttributeError` where `MAILERS` is defined, and otherwise warns only a reader outside Django, so that Django's own compatibility code reads it in silence ([Sending email: `mailers` and the email backends](../services/mailers.md#without-mailers-the-deprecated-settings)) (`django/conf/__init__.py:_show_settings_deprecation_warning`).

## Writes go through the proxy too

Assigning to a setting through `settings` sets the attribute on the wrapped object and removes the kept value for that name from the proxy, so the next read fetches the new one. Assigning a new wrapped object clears every kept value at once (`django/conf/__init__.py:LazySettings.__setattr__`). Deleting a setting removes its kept value in the same way (`django/conf/__init__.py:LazySettings.__delattr__`).

An assignment reaches the next reader of the setting. It does not reach anything that read the old value earlier and built something from it, and that is the subject of [Overriding settings](overrides.md).

## `settings.configure`: settings without a module

A process can supply its settings directly, with no module and no environment variable, by calling `LazySettings.configure` before anything reads a setting (`django/conf/__init__.py:LazySettings.configure`). It takes the settings as keyword arguments, refuses a name that is not upper case with `TypeError`, and wraps a `UserSettingsHolder` holding them.

A `UserSettingsHolder` is the other kind of object the proxy can wrap, and it works the opposite way from a `Settings`. It copies nothing. It keeps only the names set on it, and a read of any other upper-case name not deleted falls through to a second object, its `default_settings`: for `configure` the `global_settings` module unless the caller passes another, for an override the object wrapped before it ([Overriding settings](overrides.md)) (`django/conf/__init__.py:UserSettingsHolder.__getattr__`).

After `configure(DEBUG=True)`, a read of `USE_TZ`, which the call did not set, is answered one step past `LazySettings.__getattr__`, by `UserSettingsHolder.__getattr__`.

```text recording=startup
No settings module: settings.configure
    settings.configure(DEBUG=True)
      LazySettings.configure
        UserSettingsHolder.__init__(global_settings)
        LazySettings.__setattr__("_wrapped", a UserSettingsHolder)
    ...
    settings.USE_TZ
      LazyObject.__getattribute__("USE_TZ")
      LazySettings.__getattr__("USE_TZ")
        UserSettingsHolder.__getattr__("USE_TZ")
      -> True
    ...
    settings.configure(DEBUG=False), a second time
      LazySettings.configure
      -> raises RuntimeError: Settings already configured.
    ...
```

Settings can be configured once. `configure` raises `RuntimeError` when anything is already wrapped, and a loaded settings module counts: in a process where `"DJANGO_SETTINGS_MODULE"` is set, `configure` has to come before every read or write.

Configuring by hand skips two of the things `Settings.__init__` does besides copying: the list-or-tuple check is not made, and the process's time zone is not set from `TIME_ZONE`. A deprecated email setting given beside `MAILERS` is refused all the same (`django/conf/__init__.py:LazySettings.configure`).

Django calls `configure` itself in one place, for the commands that may run where no project exists yet ([Who calls `django.setup`](callers.md#commands-that-configure-for-themselves)).
