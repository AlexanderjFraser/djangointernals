---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Lazy translations

A **lazy translation** is the object `django.utils.translation.gettext_lazy` returns: it keeps a message and translates it each time it is made a string, in the language active at that moment. `pgettext_lazy`, `ngettext_lazy` and `npgettext_lazy` make the same kind of object for a message with a context or a plural, and the plural ones can wait for their number as well (`django/utils/translation/__init__.py:lazy_number`).

Code that runs as a module is imported runs once for the whole process, not once for each request: a constant, a class body, the verbose names and help texts of a model's fields and options, a form's labels. Called there, `django.utils.translation.gettext` would translate once, into whatever language was active, usually none and so `LANGUAGE_CODE`'s, and every request after would get that result. With `USE_I18N` on, before the application registry is ready it cannot translate at all: making the translations of `LANGUAGE_CODE` asks the registry for the installed applications, and raises `AppRegistryNotReady`, whose message asks the reader to check for non-lazy gettext calls at import time ([Message catalogues: `DjangoTranslation`](catalogues.md)) (`django/utils/translation/trans_real.py:DjangoTranslation._add_installed_apps_translations`). Making a lazy translation looks nothing up and reads neither the settings nor the registry, so it can be made in a module imported before Django is configured.

## The proxy

`gettext_lazy` is `lazy(gettext, str)` and `pgettext_lazy` is `lazy(pgettext, str)`, each wrapping the facade's function, which is itself bound to its implementation only when first called ([Translating a message](translating.md)) (`django/utils/translation/__init__.py:gettext_lazy`). Calling one makes a proxy that keeps the arguments. Its class, made by `lazy`, has the methods of `str`, the comparisons, the hash and the operators among them, and each first calls the function with the kept arguments, then acts on the string it got (`django/utils/functional.py:lazy`). The result is not kept: the docstring of `lazy` says results are not memoized, so each use looks the message up again. `lazy` itself, and `Promise`, the class every such proxy derives from, belong to [Lazy values: `lazy`, `Promise` and `keep_lazy`](../utils/lazy.md).

## Plurals and their number

A plural message needs a number to choose its form, and a message made at import has no number yet. `django.utils.translation.ngettext_lazy` and `npgettext_lazy` pass their arguments to `lazy_number`, which looks at the number (`django/utils/translation/__init__.py:lazy_number`). Given an `int`, it makes an ordinary proxy of `ngettext` or `npgettext` with the number among the kept arguments. Given the name of a key, or nothing, it leaves the number to be supplied when the message is formatted.

For that, `lazy_number` makes a subclass of `str` inside itself, and a proxy whose function returns an empty instance of it (`django/utils/translation/__init__.py:lazy_number.NumberAwareString`). The subclass's `__mod__` is where the number arrives. With a dictionary, where the number was named by a key, the number is the dictionary's value under that key, and a dictionary without it raises a `KeyError` that says so. With anything else the operand is itself the number, as in `% 3` for a message whose one placeholder is the count. The message is then translated with that number and formatted with the operand, and a `TypeError` from formatting a form with no placeholder for the number is passed over. Its `format` finds the number the same way, among the keyword arguments by the key, or else as the first positional argument.

The office keeps one such message, and its Dutch catalogue translates both forms:

```python
# harbour/office/views.py
from django.utils.translation import ngettext_lazy

SHIP_COUNT = ngettext_lazy("%(num)d ship", "%(num)d ships", "num")
```

```text
# a run of the example: SHIP_COUNT in English and in Dutch
                                   en           nl
SHIP_COUNT % {"num": 1}            '1 ship'     '1 schip'
SHIP_COUNT % {"num": 3}            '3 ships'    '3 schepen'
pickled, unpickled, % {"num": 3}   '3 ships'    '3 schepen'
str(SHIP_COUNT)                    ''           ''
<p>{{ count }}</p>                 '<p></p>'    '<p></p>'

SHIP_COUNT % {"count": 3}
KeyError: "Your dictionary lacks key 'num'. Please provide it, because it is required to determine whether string is singular or plural."
```

Made a string any other way, such a message is the empty instance its proxy's function returns, so a template given it unformatted writes nothing. Its `__bool__` answers with the truth of the singular instead.

A proxy is pickled as its function and its arguments (`django/utils/functional.py:lazy.__proxy__.__reduce__`). This one's function is a lambda made inside `lazy_number`, and pickle refuses a local object; so `lazy_number` gives the proxy a `__reduce__` of its own, which names `_lazy_number_unpickle` and the original arguments, and unpickling calls `lazy_number` again (`django/utils/translation/__init__.py:_lazy_number_unpickle`).

## Where a lazy translation becomes text

The string is made where the value is written out. A template writes each value through `render_value_in_context`: the conversion to the current time zone and `localize` leave a lazy translation as it is, and, being no `str`, it is made one, and escaped where autoescaping is on, as the template renders ([Rendering: nodes and the render context](../templates/rendering.md)) (`django/template/base.py:render_value_in_context`). `DjangoJSONEncoder` writes any `Promise` as its string (`django/core/serializers/json.py:DjangoJSONEncoder.default`). `django.utils.text.format_lazy` is `lazy` of a call of `str.format`: its format string and its arguments may be lazy translations, and all are translated when the result is made a string (`django/utils/text.py:format_lazy`).

makemigrations writes a lazy translation in the source language. `serializer_factory` makes a `Promise` its string ([Serializing values: `serializer_factory` and `deconstruct`](../migrations/serializer.md)) (`django/db/migrations/serializer.py:serializer_factory`), and makemigrations runs under `no_translations`, which calls `django.utils.translation.deactivate_all`: the active translation is then a `gettext.NullTranslations`, which gives each message back as it is, the use its docstring names ([Running a command: `BaseCommand`](../commands/running.md)) (`django/utils/translation/trans_real.py:deactivate_all`).

Two other lazy values serve the formats. `get_format_lazy` is `lazy(get_format, str, list, tuple)`, a format of the locale read when it is used ([Locale formats: `get_format` and the format modules](formats.md)) (`django/utils/formats.py:get_format_lazy`). The names of the days and the months in `django/utils/dates.py` are lazy translations made at import, so one dictionary serves every language ([Writing numbers, dates and durations](writing-values.md)).

## Two traps

A lazy translation is not a `str`: `isinstance` with `str` is false for it, and code that tests for `str` may pass it by or refuse it. The standard library's JSON encoder refuses it ("Object of type __proxy__ is not JSON serializable"). `conditional_escape` is one of the places in Django that test for `Promise` and make a string of it (`django/utils/html.py:conditional_escape`); code that tests only for `str` should be given `str` of it.

An operator or a method used on a lazy translation translates it there and then, and returns a plain value: `+` and `%` give a `str`. A title written `django.utils.translation.gettext_lazy("Arrivals") + ":"` at import is made then, and is still "Arrivals:" in a Dutch request; a message formatted with `%` at import is fixed the same way. To combine lazy translations and keep the result lazy, `format_lazy` does the combining when the result is used.
