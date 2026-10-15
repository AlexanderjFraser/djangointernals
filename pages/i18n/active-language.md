---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2; asgiref 3.12.1
---

# The active language

The active language is the translation that every lookup reads, held for each thread or asynchronous context and set and cleared by `django.utils.translation.activate`, `deactivate`, `deactivate_all` and `override`. `get_language` and `get_language_bidi` report on it, and `get_language_info` describes a language from `django.conf.locale.LANG_INFO`.

Code that looks a message up, a model's verbose name or a month's name, is passed no language: it reads one object Django keeps beside the running code.

## Where the language is held

`_active` is an asgiref `Local` whose one attribute, value, holds a translation object, not a code: a lookup takes the object and asks it (`django/utils/translation/trans_real.py:_active`). It is in one of three states.

| state | made by | `get_language` gives | a lookup uses |
|---|---|---|---|
| nothing active | `deactivate`; a new thread | `LANGUAGE_CODE` | the translations of `LANGUAGE_CODE` |
| a language | `activate` | the translation's code | that language's `DjangoTranslation` |
| translation off | `deactivate_all` | `None` | nothing: the message as written |

*The three states of the active language.*

The `Local` keeps its value in a context variable, tagged with the thread that set it, and ignores a value tagged with another, so a thread starts with nothing active even where it inherits its starter's context (`asgiref:asgiref/local.py:_CVar._storage`). In asynchronous code the value belongs to the context: a task sees the language active where it was created, and one the task activates stays in the task. `sync_to_async` and `async_to_sync` re-tag the value for the thread they run code in, so it reaches that code, and the value the code leaves comes back to the caller (`asgiref:asgiref/sync.py:_restore_context`).

## Setting and clearing it

`django.utils.translation.activate` ignores an empty code or `None`, and passes any other to `translation`, which makes the language's `DjangoTranslation` or gives back the one it made before ([Message catalogues: `DjangoTranslation`](catalogues.md)) (`django/utils/translation/trans_real.py:activate`). It checks nothing against `LANGUAGES`: after `activate("xx")`, `get_language` gives `"xx"`, and lookups are answered by the translations of `LANGUAGE_CODE` behind it.

`deactivate` deletes the value and leaves nothing active. `deactivate_all` installs the standard library's `gettext.NullTranslations`, which gives back every message as it was asked for, its to_language made to return `None` (`django/utils/translation/trans_real.py:deactivate_all`). Its docstring gives the use: lazy translations then appear as the original string, which is how `Options.verbose_name_raw` gives a model's name untranslated, through `override(None)` (`django/db/models/options.py:Options.verbose_name_raw`). The formats follow: with no language, `get_format` uses the settings, and a run writes 29 March 2026 as "March 29, 2026" ([Locale formats: `get_format` and the format modules](formats.md)).

## Asking which language is active

`django.utils.translation.get_language` asks the active translation for its code: a `DjangoTranslation` gives the code it was made with, lower case with a hyphen (`activate("NL")` gives `"nl"`), and the one `deactivate_all` installs gives `None`. With nothing active it returns `LANGUAGE_CODE`, without making a translation (`django/utils/translation/trans_real.py:get_language`). A caller must expect `None`: `get_format` and `check_for_language` take it for no language.

`get_language_bidi` gives `False` for `None`, and otherwise whether the code's part before its first hyphen is in `LANGUAGES_BIDI` (`django/utils/translation/trans_real.py:get_language_bidi`). It does not read the `"bidi"` of `django.conf.locale.LANG_INFO`, and the two disagree for `"az"`, which `LANG_INFO` marks right to left and `LANGUAGES_BIDI` does not list.

## Overriding the language

`django.utils.translation.override` exists only in the facade, built from its functions, so with `USE_I18N` false it does nothing either (`django/utils/translation/__init__.py:override`). `override.__enter__` records the code `get_language` gives, then activates the language it was given, or for `None` calls `deactivate_all`. `override.__exit__`, however the block ends, calls `deactivate_all` again if the recorded code was `None`; `deactivate` if `deactivate=True` was passed, leaving nothing active where a language was before; and otherwise activates the recorded code. Recording a code, it cannot tell nothing active from `LANGUAGE_CODE` active, and after a block in a thread where nothing was, `LANGUAGE_CODE` is.

> **Trap.** `override` is a `contextlib.ContextDecorator`, so it also decorates a function. One `override` then serves every call, and `__enter__` keeps the language it replaces on it: a call that begins while another is running, by recursion or in another thread, overwrites that. In a run, a function decorated with `override("nl")` that called itself once, entered with German active, left Dutch active.

## Who activates a language

`LocaleMiddleware` activates each request's language ([Choosing a language: `LocaleMiddleware`](choosing.md)). `{% language %}` overrides it for its body ([The libraries to load: static, i18n, l10n, tz and cache](../templates/loadable-libraries.md)), `translate_url` to reverse an address ([Language prefixes and translated routes](../urls/i18n.md)), and a sitemap with `Sitemap.i18n` for each item's location (`django/contrib/sitemaps/__init__.py:Sitemap._location`). A command marked `no_translations` runs with translation off ([Running a command: `BaseCommand`](../commands/running.md)). A test's `override_settings` of `LANGUAGE_CODE`, `LANGUAGES` or `LOCALE_PATHS` replaces the object that holds the language, emptying it for every thread ([Overriding settings](../startup/overrides.md)) (`django/test/signals.py:language_changed`).

## Nothing deactivates at the end of a request

`LocaleMiddleware.process_response` leaves the language active, and nothing else in Django deactivates it when a request ends (`django/middleware/locale.py:LocaleMiddleware.process_response`). A thread keeps the last request's language until the next request's `LocaleMiddleware.process_request` activates another, and code that runs in the thread before then sees the old one. A run of the example, the test client making two requests in one thread, and a middleware of the project's, Peek, listed above `LocaleMiddleware`, noting `django.utils.translation.get_language` in its `process_request`:

```text
GET /arrivals/, with the cookie django_language=de
  Peek, before LocaleMiddleware: en
  Content-Language: de
after the response, in this thread: de; in a new thread: en
GET /arrivals/, with neither cookie nor Accept-Language
  Peek, before LocaleMiddleware: de
  Content-Language: en
```

## `get_language_info` and Django's table of languages

`django.conf.locale.LANG_INFO` gives, for each language code, the `"code"`, the English `"name"`, the `"name_local"` in the language itself, and `"bidi"` (`django/conf/locale/__init__.py`). The regional codes of Chinese have only a `"fallback"`, a list of codes: they do not fall back as `"fr-ca"` does to `"fr"`, the docstring says, and `"zh-tw"` goes to `"zh-hant"`.

`django.utils.translation.get_language_info` returns a code's entry, or for a fallback its first fallback's, or for a code the table lacks the entry of the part before the hyphen: `"nl-be"` gives Dutch's. Otherwise it raises `KeyError`, as for `"xx"` or the locale name `"nl_BE"` (`django/utils/translation/__init__.py:get_language_info`). It adds `"name_translated"`, `gettext_lazy` of the English name, written in the language active when it is used: German's is "Duits" with Dutch active. The dictionary it returns is the table's own entry, not a copy, so `"name_translated"` is written into `LANG_INFO` itself, and a caller that changes the dictionary changes the table for the process.
