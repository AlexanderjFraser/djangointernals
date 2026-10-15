---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Message catalogues: `DjangoTranslation`

`DjangoTranslation` holds one language's translations: every catalogue Django finds for the language, in its own locale directory, in each installed application's and in each directory of `LOCALE_PATHS`, layered in a `TranslationCatalog` that is searched top first, with the translations of `LANGUAGE_CODE` behind them as a fallback, unless the language is that one or its code begins `"en"`. In the domain `"django"`, a process makes one for each language the first time the language is asked for, and keeps it.

A lookup has to find a message in whichever of many files has it, and the files are ranked: a project can replace an application's translation of a message, and an application Django's. So Django reads all of a language's catalogues once, into one object, with the files that should win on top. The lookup itself is told in [Translating a message](translating.md).

## One object for each language

`django.utils.translation.trans_real.translation` keeps a dictionary, `_translations`, from a language's code as it was given to its `DjangoTranslation`, and makes the object the first time the code is asked for (`django/utils/translation/trans_real.py:translation`). `activate` takes its object from there, as do the default translation, which answers when no language is active, and the fallbacks of the domain `"django"`. All threads share the objects; a thread holds for itself only which one is active ([The active language](active-language.md)).

`DjangoTranslation` subclasses the standard library's `gettext.GNUTranslations` and keeps its two parts: a catalogue, the dictionary a lookup searches, and a fallback, another translation asked for what the catalogue lacks. Unlike its parent, it reads many files into one catalogue (`django/utils/translation/trans_real.py:DjangoTranslation`).

## Building a language's translations

`DjangoTranslation.__init__` builds the object in this order (`django/utils/translation/trans_real.py:DjangoTranslation.__init__`):

1. It starts with no catalogue and the Germanic plural formula, plural for every number but one, until the first catalogue found brings its own.
2. In the domain `"django"`, the default, it ignores any directories passed as localedirs, warning "localedirs is ignored when domain is 'django'."; the comment says the `"django"` translations are cached at module level. Then `DjangoTranslation._init_translation_catalog` reads Django's own catalogue from the `locale` directory beside the module the settings object's `__module__` names: `"django.conf"`, where `LazySettings` is defined, not the project's settings module; so `django/conf/locale/`.
3. Given localedirs, it reads those directories. Otherwise `DjangoTranslation._add_installed_apps_translations` reads the `locale` directory of each application that has one, in the reverse of `INSTALLED_APPS`. Until the application registry has imported every application's configuration, it raises `AppRegistryNotReady`, "The translation infrastructure cannot be initialized before the apps registry is ready. Check that you don't make non-lazy gettext calls at import time." ([Lazy translations](lazy.md)) (`django/apps/registry.py:Apps.check_apps_ready`).
4. `DjangoTranslation._add_local_translations` reads each directory of `LOCALE_PATHS`, also in reverse.
5. If the language is `LANGUAGE_CODE`, the domain `"django"`, and nothing was found, it raises `OSError`: with `LANGUAGE_CODE = "xx"`, "No translation files found for default language xx.". Any language that falls back to it fails too.
6. `DjangoTranslation._add_fallback` puts the translations of `LANGUAGE_CODE` behind.
7. If no file was found, the catalogue is an empty `TranslationCatalog`, and every lookup goes to the fallback, if there is one.

Each catalogue read lands on top of those read before it, so the reversed orders put the first application listed above the later ones and the first directory of `LOCALE_PATHS` above everything.

### Reading one directory

`DjangoTranslation._new_gnu_trans` hands a directory to the standard library's `gettext.translation`, with the domain, the language's locale name from `to_locale`, and `fallback=True`, so that a directory without the file gives a `gettext.NullTranslations` rather than an error (`django/utils/translation/trans_real.py:DjangoTranslation._new_gnu_trans`). The file is `"<dir>/<locale>/LC_MESSAGES/<domain>.mo"`, but the standard library first normalizes the locale with `locale.normalize` and widens it: for `"pt_BR"` it tries `"pt_BR.ISO8859-1"`, `"pt_BR"`, `"pt.ISO8859-1"` and `"pt"`. It returns the first file found, with any other it found chained behind it as fallbacks. It parses each file once and keeps it, by its path, in a dictionary of its own.

### Merging: `DjangoTranslation.merge` and `TranslationCatalog`

`DjangoTranslation.merge` passes over a result with no catalogue (`django/utils/translation/trans_real.py:DjangoTranslation.merge`). The first catalogue found gives the object its plural formula and its header's information, and becomes the bottom of a new `TranslationCatalog`; each later one goes to `TranslationCatalog.update`. Fallbacks the standard library chained behind a file go behind the object: for `"pt-br"`, Django's `"pt_BR"` catalogue is the catalogue, and its `"pt"` catalogue stands behind it, before the translations of `LANGUAGE_CODE`.

`TranslationCatalog` is a stack of dictionaries that answers as one, top first. Its docstring gives its purpose: to keep catalogues whose plural equations differ apart (`django/utils/translation/trans_real.py:TranslationCatalog`). A catalogue stores a plural message's forms under the message and the form's index, and an index means something only under its own file's formula. So each dictionary keeps its formula beside it, and `TranslationCatalog.plural` asks each for the form its own formula picks, raising `KeyError` when none has it.

The comment in `TranslationCatalog.update` says it merges a catalogue into the top dictionary when their plural functions are the same, and otherwise puts it on top as a dictionary of its own. At the pin the condition compares the new catalogue's formula's code object with the top dictionary's formula, a function, and the two are never equal: every catalogue after the first goes on top as its own dictionary. The example's Dutch translations hold two, the office's above Django's, though both files have the formula `"nplurals=2; plural=(n != 1);"` (`django/utils/translation/trans_real.py:TranslationCatalog.update`). A lookup gives what a merge would have given, since the later catalogue wins either way; it tries one dictionary for each file.

### The fallback

`DjangoTranslation._add_fallback` sets none for `LANGUAGE_CODE` itself, nor for a code beginning `"en"`; the comment's reason for the second is that an English catalogue is empty, so an English lookup would always fall through to the default language (`django/utils/translation/trans_real.py:DjangoTranslation._add_fallback`). Django's English catalogue holds nothing but its header. For the domain `"django"` the fallback is the cached translation of `LANGUAGE_CODE`; for another, a new `DjangoTranslation` of `LANGUAGE_CODE` in that domain, made each time. `JavaScriptCatalog` makes one of the domain `"djangojs"` for each request, with the locale directories of the packages it is asked for as localedirs ([The language views: `set_language` and `JavaScriptCatalog`](views.md)).

In a run with `LANGUAGE_CODE = "de"` and, in `LOCALE_PATHS`, a German catalogue that translates "Tide table" as "Gezeitentafel", the Dutch translations gave "Gezeitentafel" from their fallback. In the example the fallback, `"en"`, has nothing to give, and `translation("nl")` gave "Arrivals" as "Aankomsten" from the office's catalogue, "January" as "januari" from Django's own, and "Tide table" as it was:

```text figure=the-catalogue
translation("nl") in the example: its catalogues, searched top first

LOCALE_PATHS, first listed on top      the example has none
INSTALLED_APPS, first listed on top    office/locale/nl/LC_MESSAGES/django.mo
                                         "Arrivals"   -> "Aankomsten"   stops here
Django's own                           django/conf/locale/nl/LC_MESSAGES/django.mo
                                         "January"    -> "januari"      stops here
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
behind them, the fallback              the translations of LANGUAGE_CODE, "en"
in none of them                          "Tide table" -> "Tide table"   given back as it was
```

*The translations of `"nl"` in the example, top first. A lookup stops at the first catalogue that has the message; a message that none of them has, nor the translations of `LANGUAGE_CODE` behind them, comes back as it was given.*

## Language codes and locale names

A directory of catalogues is named by a locale, `"nl_BE"`, not a language code, `"nl-be"`. `django.utils.translation.to_locale` turns one into the other: the language in lower case, an underscore, then a region of two letters in capitals or a longer part with its first letter capital (`"sr-latn"` becomes `"sr_Latn"`), and any third part after a hyphen. `to_language` goes back, in lower case with a hyphen (`django/utils/translation/__init__.py:to_locale`, `django/utils/translation/__init__.py:to_language`).

`django.utils.translation.trans_real.all_locale_paths` lists where a catalogue may be: Django's own directory, those of `LOCALE_PATHS`, and the `locale` directory of each application that has one (`django/utils/translation/trans_real.py:all_locale_paths`). `check_for_language` searches them to tell whether a language has a catalogue at all ([Choosing a language: `LocaleMiddleware`](choosing.md)).

## When the translations are thrown away

The facade connects two receivers of the autoreloader the first time a translation function is used with `USE_I18N` true ([Translating a message](translating.md)). `django.utils.translation.reloader.watch_for_translation_changes` has the reloader watch every `.mo` file under the `locale` directory where the process runs, under each application's that is not Django's own, and under each directory of `LOCALE_PATHS` (`django/utils/translation/reloader.py:watch_for_translation_changes`). When one changes, `translation_file_changed` empties the standard library's dictionary of parsed files and `_translations`, forgets the default translation, and replaces the holder of the active language, so that no thread has one active. It returns true, so the server goes on in the same process ([The autoreloader](../commands/autoreload.md)) (`django/utils/translation/reloader.py:translation_file_changed`).

When a test overrides `INSTALLED_APPS`, `LANGUAGES` or `LOCALE_PATHS`, receivers of `setting_changed` empty `_translations`. An override of `LANGUAGE_CODE` leaves it, and forgets only the default translation and the active one, so a language built before keeps the old default behind it ([Overriding settings](../startup/overrides.md)) (`django/test/signals.py:language_changed`, `django/test/signals.py:update_installed_apps`).
