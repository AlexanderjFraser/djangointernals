---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The settings object

`django.conf.settings` is a `LazySettings`: a proxy that imports the settings module on the first read of any setting, builds a `Settings` from it over the defaults of `global_settings`, and keeps each value it has returned. `LazySettings.configure` fills it by hand instead.

A project's settings are an ordinary Python module, but no part of Django imports that module by name, because no part of Django knows its name. The name arrives late: in an environment variable that the project's `manage.py` or `wsgi.py` sets, or in a `--settings` option that is parsed after much of Django has already been imported. Meanwhile modules all over the framework have written `from django.conf import settings` at their top. So `settings` cannot be the module. It is an object that exists from the moment `django.conf` is imported and becomes the settings when someone first needs one.

## A proxy with nothing behind it

`LazySettings` is built on `LazyObject`, Django's general lazy proxy (`django/utils/functional.py:LazyObject`). A `LazyObject` has one attribute of its own that matters, `LazyObject._wrapped`, which starts as a marker object called `empty`. When an attribute is asked of the proxy and nothing is wrapped yet, it calls its `_setup` method, which a subclass writes, to put something there; then it asks the wrapped object.

`LazySettings._setup` is that method for the settings. It reads the environment variable `"DJANGO_SETTINGS_MODULE"`. If the variable is unset or empty it raises `ImproperlyConfigured`, with a message that names the setting that was being read. Otherwise it makes a `Settings` from the module's name and wraps it (`django/conf/__init__.py:LazySettings._setup`).

This is a first read recorded, then a second, in a process where the variable names the settings module of the recording's project, library.settings.

```text recording=startup
A settings module: reads, and one assignment
    repr(settings)  -> <LazySettings [Unevaluated]>
    settings.DEBUG, the first read of any setting
      LazyObject.__getattribute__("DEBUG")
      LazySettings.__getattr__("DEBUG")
        LazySettings._setup("DEBUG")
          Settings.__init__("library.settings")
            import library.settings
          LazySettings.__setattr__("_wrapped", a Settings)
      -> False
    repr(settings)  -> <LazySettings "library.settings">
    settings.DEBUG, again
      LazyObject.__getattribute__("DEBUG")
      -> False
```

Three things follow from loading on the first read.

Whoever reads first, loads. In a server it is the first statement of `django.setup`; for a management command it is `ManagementUtility.execute`, which reads `settings.INSTALLED_APPS` to find out whether there are settings at all. A module that reads a setting at its top level, as it is imported, loads them earlier still.

An error in the settings module surfaces at that first read, wherever it is. If loading fails, nothing is wrapped, so the proxy is still empty and the next read tries again from the beginning.

And code that may run before there are settings has a way to ask without triggering the load: the property `LazySettings.configured` is true when something is wrapped, and reading it loads nothing (`django/conf/__init__.py:LazySettings.configured`). `Signal.connect` is an example. It validates the receiver only in debug mode, and receivers are connected as modules are imported, so it tests `settings.configured` before it reads `settings.DEBUG` (`django/dispatch/dispatcher.py:Signal.connect`).

When there is no variable and nothing has configured the settings, the failure looks like this. Importing a model in such a process fails the same way, for a reason of its own. A model's class statement asks the app registry which application it belongs to, and an unpopulated registry answers with its own exception, `AppRegistryNotReady`. Before it raises that, it reads `settings.INSTALLED_APPS`, so that where the real trouble is missing settings, the message about settings is the one that appears (`django/apps/registry.py:Apps.check_apps_ready`). Where there are settings and only `django.setup` is missing, the same import raises the registry's exception.

```text recording=startup
No settings: DJANGO_SETTINGS_MODULE is not set, and settings.configure has not been called
    settings.configured  -> False
    settings.DEBUG  -> raises ImproperlyConfigured: Requested setting DEBUG, but settings are not configured. You must either define the environment variable DJANGO_SETTINGS_MODULE or call settings.configure() before accessing settings.
    settings.configured  -> False
    import library.catalogue.models  -> raises ImproperlyConfigured: Requested setting INSTALLED_APPS, but settings are not configured. You must either define the environment variable DJANGO_SETTINGS_MODULE or call settings.configure() before accessing settings.
```

## What `Settings.__init__` does

A `Settings` is a flat object with one attribute for each setting. Its constructor fills it in two layers and then looks at a few of the results (`django/conf/__init__.py:Settings.__init__`).

First it copies every upper-case name of `django/conf/global_settings.py` onto itself. Then it imports the project's module and copies every upper-case name of that module over them, adding each name to the set `Settings._explicit_settings`. The defaults are therefore not consulted when a setting is read: by then the project's value has replaced the default on the same object. The set is what `Settings.is_overridden` answers from, for the few callers that need to know whether a value is the project's own or only the default.

A name is a setting if it is written in upper case, and nothing else is tested. A name of the module in lower or mixed case is not copied and cannot be read through `settings`. Any upper-case name is copied, whether Django knows a setting of that name or not: the name `"BASE_DIR"`, which a new project's settings module computes for its own use, becomes a setting like any other, and a misspelt setting becomes an attribute that nothing reads, with the default still in place under the right name.

While it copies, the constructor checks one thing about types. The settings named `"ALLOWED_HOSTS"`, `"INSTALLED_APPS"`, `"TEMPLATE_DIRS"`, `"LOCALE_PATHS"` and `"SECRET_KEY_FALLBACKS"` must each be a list or a tuple, and `ImproperlyConfigured` is raised if one is not. The check exists for the mistake of writing a single string where a sequence of strings is meant, which would otherwise be iterated a character at a time.

If the import fails because the settings module itself is not found, the `ImportError` is turned into `ImproperlyConfigured`. Any other `ImportError` passes through unchanged: one for a parent package that does not exist, or one raised by an import inside the settings module.

Last, the constructor moves the time zone into the process. Where the platform's `time` module has the function `"tzset"`, and `TIME_ZONE` is set, it checks the name with `zoneinfo.ZoneInfo`, raising `ValueError` for one that does not exist, puts the name in the environment variable `"TZ"`, and calls that function. From then on the C library's local time is in the project's zone, and so is everything in the process that takes its local time from there and not from Django: `datetime.datetime.now` called with no zone, and the times a `logging.Formatter` writes into log lines. Windows has no such function, and there the process's time zone is left alone.

## The defaults

`django/conf/global_settings.py` is a module of plain assignments, and it has to stay one: it is imported by `django.conf` itself, before there are settings, so it can import nothing that reads a setting. The translation functions are such a thing, which is why the module defines a function of its own, `gettext_noop`, that returns its argument, to mark the names of languages for translation.

Not every setting Django reads has a default there.

- `ROOT_URLCONF` has none. A project sets it, and code that must work without one reads it with a fallback, as the URL system checks do (`django/core/checks/urls.py:check_url_config`).
- `MAILERS` is present only as a comment, to be uncommented when the settings it replaces are removed. Its absence is meaningful: mail code tells the old configuration from the new by whether the project defined `MAILERS` (`django/core/mail/handler.py:MailersHandler._is_configured`).
- A few settings of the contrib applications get their defaults where they are read. The messages application's level and tags are two, kept out of `global_settings` so that the file needs no import.

A default that is computed from another is computed once, from the default. `MANAGERS` is assigned the very list that `ADMINS` names, so a project that sets `ADMINS` has not thereby set `MANAGERS`.

## The value is kept on the proxy

Settings are read constantly, and a read that went through to the wrapped object every time would run `LazySettings.__getattr__`, with its tests for the special cases below, on each one. The method therefore ends by storing the value it found in the proxy's own instance dictionary, under the setting's name (`django/conf/__init__.py:LazySettings.__getattr__`).

Python calls a class's `__getattr__` only when the ordinary lookup has failed, and the ordinary lookup finds what is in the instance dictionary. So the second read of a setting never reaches `LazySettings.__getattr__`, as the recording above shows. It does still pass through `LazyObject.__getattribute__`, as every attribute read of a lazy object does. That hook exists for another purpose, to do with the special methods a lazy object forwards to what it wraps, and for a setting it only finds the kept value and returns it.

```text figure=a-read
settings.DEBUG
  -> the proxy, a LazySettings
       its own attributes          a value kept from an earlier read is found here, and the read ends
       LazySettings.__getattr__    reached only when none is: loads the settings if nothing is wrapped,
                                   asks the wrapped object, keeps the answer among the proxy's attributes
  -> what it wraps, one of
       a Settings                  every default of global_settings, with the settings module's
                                   upper-case names set over them: one flat object
       a UserSettingsHolder        the names set on it; any other name is asked of the object behind it,
                                   its default_settings: global_settings, or the object that was wrapped
                                   before an override
```

*A read of a setting. The first read of each name goes through to the wrapped object and leaves the value on the proxy; every later read of that name ends at the proxy.*

Some values are changed on the way into the cache, and some reads are refused there.

`MEDIA_URL` and `STATIC_URL`, when they are relative, have the script prefix put in front of them: a value that begins with neither a slash nor `http://` or `https://` is joined to what `get_script_prefix` returns at that moment, and the joined value is what is kept (`django/conf/__init__.py:LazySettings._add_script_prefix`, `django/urls/base.py:get_script_prefix`). In the recording below, `"static/"` is assigned and `"/static/"` is read back.

`SECRET_KEY` may not be empty, and this is where that is enforced: a read of an empty one raises `ImproperlyConfigured`. A project without a secret key therefore loads its settings without complaint, and fails at the first line that needs the key.

Deprecated settings are intercepted here too. Each name in `DEPRECATED_EMAIL_SETTINGS`, the mail settings that `MAILERS` replaces, raises `AttributeError` when read in a project that defines `MAILERS`, and otherwise warns with `RemovedInDjango2028Warning`. The warning is given only when the reader is outside Django: Django's own compatibility code has to read these settings, and `_show_settings_deprecation_warning` inspects the stack to tell the two apart (`django/conf/__init__.py:_show_settings_deprecation_warning`, `django/utils/deprecation.py:warn_about_external_use`).

> **Changed in 6.1.** `MAILERS` is new in 6.1, and the settings it replaces, `EMAIL_BACKEND` and those beside it, are deprecated from then on. The settings module that `django-admin startproject` writes defines `MAILERS` (`django/conf/project_template/project_name/settings.py-tpl`).

## Writes go through the proxy too

Assigning to a setting through `settings` sets the attribute on the wrapped object and removes the kept value for that name from the proxy, so the next read fetches the new one. Assigning a new wrapped object clears every kept value at once (`django/conf/__init__.py:LazySettings.__setattr__`). Deleting a setting removes its kept value in the same way.

```text recording=startup
A settings module: reads, and one assignment
    ...
    settings.STATIC_URL = 'static/'
      LazySettings.__setattr__("STATIC_URL", 'static/')
    settings.STATIC_URL
      LazyObject.__getattribute__("STATIC_URL")
      LazySettings.__getattr__("STATIC_URL")
      -> '/static/'
    settings.NO_SUCH_SETTING
      LazyObject.__getattribute__("NO_SUCH_SETTING")
      LazySettings.__getattr__("NO_SUCH_SETTING")
      -> raises AttributeError: 'Settings' object has no attribute 'NO_SUCH_SETTING'
    settings.is_overridden('INSTALLED_APPS')
      -> True
    settings.is_overridden('USE_TZ')
      -> False
```

An assignment reaches the next reader of the setting. It does not reach anything that read the old value earlier and built something from it, and that is the subject of [Overriding settings](overrides.md).

## `settings.configure`: settings without a module

A process can supply its settings directly, with no module and no environment variable, by calling `LazySettings.configure` before anything reads a setting (`django/conf/__init__.py:LazySettings.configure`). It takes the settings as keyword arguments, refuses a name that is not upper case with `TypeError`, and wraps a `UserSettingsHolder` holding them.

A `UserSettingsHolder` is the other kind of object the proxy can wrap, and it works the opposite way from a `Settings`. It copies nothing. It keeps only the names that were set on it, and a read of any other upper-case name falls through to a second object it was given, its `default_settings`, which for `configure` is the `global_settings` module unless the caller passes another (`django/conf/__init__.py:UserSettingsHolder.__getattr__`).

```text recording=startup
No settings module: settings.configure
    settings.configure(DEBUG=True)
      LazySettings.configure
        UserSettingsHolder.__init__(global_settings)
        LazySettings.__setattr__("_wrapped", a UserSettingsHolder)
    repr(settings)  -> <LazySettings "None">
    settings.DEBUG
      LazyObject.__getattribute__("DEBUG")
      LazySettings.__getattr__("DEBUG")
      -> True
    settings.USE_TZ
      LazyObject.__getattribute__("USE_TZ")
      LazySettings.__getattr__("USE_TZ")
        UserSettingsHolder.__getattr__("USE_TZ")
      -> True
    settings.is_overridden('DEBUG')
      -> True
    settings.is_overridden('USE_TZ')
      -> False
    settings.configure(DEBUG=False), a second time
      LazySettings.configure
      -> raises RuntimeError: Settings already configured.
```

Settings can be configured once. `configure` raises `RuntimeError` when anything is already wrapped, and a first read that loaded a settings module counts: in a process where `"DJANGO_SETTINGS_MODULE"` is set, `configure` has to come before every read.

Configuring by hand also skips what `Settings.__init__` does besides copying. The list-or-tuple check is not made, and the process's time zone is not set from `TIME_ZONE`.

Django calls `configure` itself in one place, for the commands that have to run where no project exists yet ([Who calls `django.setup`](callers.md#commands-that-configure-for-themselves)).
