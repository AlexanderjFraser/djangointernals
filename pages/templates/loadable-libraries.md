---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The libraries to load: static, i18n, l10n, tz and cache

The package `django.templatetags` holds the template libraries of Django's core that are not built in: a template has their tags after `{% load static %}`, `{% load i18n %}`, `{% load l10n %}`, `{% load tz %}` or `{% load cache %}`, or where an engine's `"builtins"` option names one. Each is a thin layer of nodes over a service from elsewhere in Django: `{% static %}` over the static files storage or `STATIC_URL`, `{% translate %}` and `{% blocktranslate %}` over translation, `{% localize %}` and `{% timezone %}` over formats and time zones, and `{% cache %}` over the cache.

`get_template_tag_modules` searches `django.templatetags` first, so these libraries can be loaded in every project, unless an application's module or the `"libraries"` option takes the same name ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)) (`django/template/backends/django.py:get_template_tag_modules`).

What they share is when they work. A compiled template serves every request ([Rendering: nodes and the render context](rendering.md)), so their compile functions record what the tag said, and the language of a string, the format of a number, the URL of a file and whether a fragment is cached are decided as the node renders. The language and the time zone are not in the context: each is held per thread, or per task in asynchronous code, as activated (`LocaleMiddleware`, where installed, activates the request's language; Django has no such middleware for the time zone) or else the default of `LANGUAGE_CODE` or `TIME_ZONE` (`django/utils/translation/trans_real.py:_active`, `django/utils/timezone.py:_active`, `django/middleware/locale.py:LocaleMiddleware.process_request`). `{% language %}` and `{% timezone %}` each change one for their body.

## Static files: `{% static %}`

`{% static "fleet/port.css" %}` prints the URL of a static file. `StaticNode.handle_token` compiles the path as a filter expression, so it may be a variable, and takes a final `"as"` and a name as a variable to set in place of printing (`django/templatetags/static.py:StaticNode.handle_token`).

`StaticNode.handle_simple` makes the URL at each render. With `django.contrib.staticfiles` installed it is the URL that `staticfiles_storage` gives the path; otherwise it is `STATIC_URL` joined to the path, percent-quoted: `"fleet/port map.css"` becomes `"/static/fleet/port%20map.css"`. `StaticNode.render` escapes it when autoescaping is on (`django/templatetags/static.py:StaticNode.handle_simple`, `django/templatetags/static.py:StaticNode.render`). The function `static` gives Python code the same lookup (`django/templatetags/static.py:static`).

The storage may name another file: `ManifestStaticFilesStorage`, with `settings.DEBUG` off, uses the hashed name its manifest records, and by default raises `ValueError` mid-render for a path the manifest lacks (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.stored_name`; [Content types, static files and the other contrib apps](../contrib.md)). `{% get_static_prefix %}` and `{% get_media_prefix %}` print `STATIC_URL` and `MEDIA_URL`, read from the settings, without the storage or escaping (`django/templatetags/static.py:PrefixNode.render`).

## Translation at render time: the i18n library

The tags of `{% load i18n %}` translate as the template renders: the compiled template keeps its strings in the language they were written in, and each render looks them up in the catalogue of the language then active, so one compiled template serves every language. Choosing the language and making catalogues belong to [Internationalization and time zones](../i18n.md).

### `{% translate %}` and `TranslateNode`

`{% translate %}`, or `{% trans %}`, takes a string or a variable, with filters, and the options `"noop"`, `"context"` and `"as"` (`django/templatetags/i18n.py:do_translate`). At each render its node marks the `Variable` in its filter expression for translation, unless `"noop"` was given, and `Variable.resolve` then returns a lazy translation, by `django.utils.translation.gettext_lazy`, or `django.utils.translation.pgettext_lazy` with a context (`django/template/base.py:Variable.resolve`). `render_value_in_context` makes it a string, in the language active then, and escapes it as any value (`django/templatetags/i18n.py:TranslateNode.render`).

A literal in a template is safe, and translation keeps a safe message safe, so `{% translate "<b>Ships</b>" %}` prints the translation's tags as tags, while `{% translate name %}`, holding the same string, escapes them (`django/utils/translation/trans_real.py:gettext`, [Autoescaping and safe strings](autoescape.md)).

### `{% blocktranslate %}` and `BlockTranslateNode`

`{% blocktranslate %}`, or `{% blocktrans %}`, translates a passage with values in it, and its body is never compiled. After the options (`"with"`, `"count"`, `"context"`, `"trimmed"`, `"asvar"`), the compile function takes the body's tokens from the parser one by one and keeps them: text and variables up to `{% plural %}` when there is a `"count"`, then up to the end tag. Anything else there, a comment included, is an error (`django/templatetags/i18n.py:do_block_translate`).

At render, `BlockTranslateNode.render_token_list` writes the tokens out as the message to look up: the text with each `%` doubled, and each variable as a placeholder named by the token's whole text. For this template the messages a catalogue must hold are `"One ship in %(name)s."` and `"%(counter)s ships in %(name)s."`:

```text
{# fleet/port_detail.html #}
{% load i18n %}
{% blocktranslate with name=port.name count counter=ships|length %}One ship in {{ name }}.{% plural %}{{ counter }} ships in {{ name }}.{% endblocktranslate %}
```

`BlockTranslateNode.render` pushes the values of `"with"` and, with a count, asks `django.utils.translation.ngettext`, or `npgettext` with a context, for the form the count selects. It fills each placeholder by looking its name up in the context as one key, and renders the value with `render_value_in_context` (`django/templatetags/i18n.py:BlockTranslateNode.render`). A translation whose placeholders do not fit is abandoned, and the passage rendered again with translation off.

> **Trap.** A variable in the body is a name and no more. `{{ ship.name }}` there becomes the placeholder `%(ship.name)s`, which no key of the context matches, and prints `"string_if_invalid"`, empty by default. A lookup or a filter belongs in `"with"` or `"count"`.

### `{% language %}` and the tags that read the language

`{% language "de" %}` renders its body inside `django.utils.translation.override`, which activates German and afterwards restores the previous language (`django/templatetags/i18n.py:LanguageNode.render`). Translations in the body follow it, and so do number and date formats, which `django.utils.formats` takes from the active language (`django/utils/formats.py:get_format`).

`{% get_current_language %}`, `{% get_current_language_bidi %}` and `{% get_available_languages %}` read the active language as their node renders, the last giving `LANGUAGES` with each name translated into it; `{% get_language_info %}`, `{% get_language_info_list %}` and filters such as `|language_name_local` look a code up in Django's table of languages (`django/utils/translation/__init__.py:get_language_info`). Not so the context processor `django.template.context_processors.i18n`: its `"LANGUAGE_CODE"` is computed when the template is bound to its `RequestContext` (`django/template/context_processors.py:i18n`). Inside `{% language "de" %}`, in a request served in English, `{% get_current_language as lang %}{{ lang }}` prints `"de"` and `{{ LANGUAGE_CODE }}` `"en"` ([The context: `Context`, `RequestContext` and context processors](context.md)).

## Localisation: `{% localize %}`

Whether a value is localised is a flag on the context. `render_value_in_context` formats numbers, dates and times with `django.utils.formats.localize`, passing `Context.use_l10n`, by default `None`, which means localise (`django/template/base.py:render_value_in_context`, `django/utils/formats.py:localize`). `{% localize off %}` sets the flag for its body and restores it after; `{% localize %}` or `{% localize on %}` sets it true (`django/templatetags/l10n.py:LocalizeNode.render`). The filters `|localize` and `|unlocalize` force one value and return a string, not formatted again. In German, `{{ tonnage }}` prints `"1234,5"` and `{{ tonnage|unlocalize }}` `"1234.5"`.

## Time zones: `{% localtime %}`, `{% timezone %}` and the filters

Before it localises, `render_value_in_context` converts an aware datetime to the current time zone when `Context.use_tz` is true or, while it is `None`, when `USE_TZ` is; a filter registered with `expects_localtime=True`, as `date` is, gets its value converted first (`django/utils/timezone.py:template_localtime`, `django/template/base.py:FilterExpression.resolve`). `{% localtime off %}` sets `use_tz` for its body as `{% localize %}` sets `use_l10n` (`django/templatetags/tz.py:LocalTimeNode.render`). `{% timezone "Europe/Malta" %}` changes which zone is current, rendering its body inside `django.utils.timezone.override`, and `{% get_current_timezone as TIME_ZONE %}` names it (`django/templatetags/tz.py:TimezoneNode.render`, `django/templatetags/tz.py:GetCurrentTimezoneNode.render`).

The filters `|localtime`, `|utc` and `|timezone:"Europe/Malta"` convert one value, and must keep the automatic conversion from undoing it. A `datetime.datetime` takes no new attributes, so `do_timezone` copies its result into `datetimeobject`, a subclass that exists to carry a flag telling `template_localtime` to leave it alone (`django/templatetags/tz.py:do_timezone`). A departure at 10:30 UTC in July shows 12:30 inside `{% timezone "Europe/Malta" %}`, and 10:30 there through `|utc|date:"H:i"`.

## The fragment cache: `{% cache %}`

`{% cache 600 ship_list port.pk %}` keeps the rendered output of its body in Django's cache. `do_cache` parses the body into a node list and reads a timeout, a fragment name, any values to vary on and an optional last `using=` naming a cache, compiling all but the name as filter expressions (`django/templatetags/cache.py:do_cache`).

`CacheNode.render` resolves the timeout and passes it through `int`, unless it is `None`, which means no expiry. It takes the cache `using=` named, else `"template_fragments"` when `CACHES` has it, else `"default"`, and makes the key with `make_template_fragment_key` from the fragment name and an MD5 digest of the values: `"template.cache.ship_list.6709aa7b0015b3f2257cda58f6ae8ed0"` when the port's key is 1. On a hit the body is not rendered; on a miss it is rendered and stored (`django/templatetags/cache.py:CacheNode.render`, `django/core/cache/utils.py:make_template_fragment_key`). A bad timeout or an unknown alias is a `TemplateSyntaxError`, raised as the node renders ([Caching, files, mail, signals and tasks](../services.md)).

> **Trap.** The key is the fragment name and the values, nothing else: not the template, the user or the language. Two templates that cache a fragment of the same name with the same values share one entry, and a fragment of translated text is served in the language of whichever render stored it, unless the language is one of the values.
