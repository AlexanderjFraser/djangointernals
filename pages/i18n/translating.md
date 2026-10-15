---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Translating a message

`django.utils.translation.gettext` looks a message up in the active language's translations, `django.utils.translation.pgettext` with a context, `django.utils.translation.ngettext` with a number that chooses a plural form, and `django.utils.translation.npgettext` with both. Each hands its call to `_trans`, which binds it at its first use to `django.utils.translation.trans_real`, the module that reads the catalogues, or, with `USE_I18N` false, to `django.utils.translation.trans_null`, whose functions give the message back.

A project imports these functions at the top of modules that may be imported before the settings are configured, and calls them without a language: they read the active language as they are called, and look the message up in its translations ([The active language](active-language.md)).

## The facade and `_trans`

The facade, `django/utils/translation/__init__.py`, translates nothing itself. Each of its eager translation functions, and each that sets, reads, checks or chooses a language other than `override`, is one line: the call of the function of the same name on `_trans` (`django/utils/translation/__init__.py:gettext`). `_trans` is the only instance of a class that defines only `__getattr__`, deleted once `_trans` is made. Python calls `__getattr__` only for an attribute an object lacks, and `_trans` starts with none, so the first call of each name reaches it. It reads `USE_I18N`, imports the real module or the null one, and stores that module's function of the name on the instance with `setattr`, where every later call finds it without `__getattr__` (`django/utils/translation/__init__.py:Trans.__getattr__`). Each name is bound at its own first use:

```text
# a run of the example
bound on _trans, before any call      nothing
after activate("nl")                  activate
after gettext("Arrivals")             activate, gettext
USE_I18N set to False, then gettext("Arrivals")  'Aankomsten'
```

The comment that opens "Here be dragons" gives two reasons: to read `USE_I18N` as late as possible, so that modules can be imported without first configuring Django; and not to break a reference that other code holds to one of these functions, as an import of `django.utils.translation.gettext` does, when the real ones are found. The facade's functions are never replaced; only what they call is. The class's docstring gives the price, which the run's last line shows: once a name is bound, a change to `USE_I18N` has no effect on it, and a test that changes the setting can delete the functions from the instance's `__dict__`.

Binding to the real module also connects, once, the autoreloader's signals `autoreload_started` and `file_changed` to the functions that watch the `.mo` files and reset the translations when one changes ([Message catalogues: `DjangoTranslation`](catalogues.md)). The lazy functions and `override` are the facade's own ([Lazy translations](lazy.md), [The active language](active-language.md)).

## When `USE_I18N` is false

`django.utils.translation.trans_null` has a function for each name the facade asks `_trans` for, none of which reads a catalogue; its opening comment says it exists purely for performance (`django/utils/translation/trans_null.py`). `gettext` gives back the message, `pgettext` the message without its context, and `ngettext` the singular for exactly 1 and the plural otherwise. `activate` does nothing and `get_language` gives `LANGUAGE_CODE`; `check_for_language` accepts every code, and `get_supported_language_variant` only `LANGUAGE_CODE`, ignoring case.

## Looking up one message

`django.utils.translation.trans_real.gettext` prepares the message, chooses a translation, and leaves the lookup to the standard library (`django/utils/translation/trans_real.py:gettext`). It first makes each `"\r\n"`, and then each remaining `"\r"`, a `"\n"`; the changed message is the one looked up, and the one given back when no catalogue has it. An empty message is not looked up: the result is an empty string of the message's own type. The comment's reason: gettext's default for an empty message is the metadata, the header that a compiled catalogue keeps as the empty message's translation.

The translation is the active one, or, with none active, `_default`, the translation of `LANGUAGE_CODE`. `gettext` makes `_default` at its first call with a message that is not empty, whether a language is active or not; `do_ntranslate` and `catalog` make it only when none is. `catalog` gives the object a lookup would use, for code that wants the whole catalogue; nothing in Django calls it (`django/utils/translation/trans_real.py:catalog`).

The lookup is the standard library's, which `DjangoTranslation` inherits: the message in the merged catalogue; then the message as the singular of a plural entry, in the form for 1; then the same in the translation's fallback, where it has one (for Dutch, the translation of `LANGUAGE_CODE`); and last the message itself ([Message catalogues: `DjangoTranslation`](catalogues.md) has the layers). A message that is `SafeData` gives a result marked safe, found or not. With Dutch active:

```text
# a run of the example
gettext("Arrivals")             'Aankomsten'
gettext("Tug alongside.\r\n")   'Tug alongside.\n'
gettext("")                     ''
catalog().gettext("")           'Content-Type: text/plain; charset=UTF-8\nPlural-Forms: nplurals=2; plural=(n != 1);\n'
```

## Messages with a context

One string may need two translations: "Free" said of a berth is "Vrij" in Dutch, and of a price "Gratis". GNU gettext keeps a message with a context under one key, the context and the message joined by `"\x04"`, which the source names `CONTEXT_SEPARATOR` (`django/utils/translation/trans_real.py:CONTEXT_SEPARATOR`). `django.utils.translation.trans_real.pgettext` builds the key and passes it to `gettext` as one message. A result that still holds the separator is the key itself, found nowhere, and `pgettext` then gives back the message, without looking it up alone. A `SafeData` message gives a safe result (`django/utils/translation/trans_real.py:pgettext`).

```text
# a run of the example, with Dutch active
pgettext("berth", "Free")     'Vrij'
pgettext("price", "Free")     'Gratis'
pgettext("tide", "Arrivals")  'Arrivals'
```

## Plural forms and the formula

Languages differ in how many plural forms they have, and in which numbers take which: Dutch gives 0 the plural, and Django's own French catalogue gives it the singular (`django/conf/locale/fr/LC_MESSAGES/django.po`). So a catalogue's plural entry holds its language's forms, numbered from 0, and the Plural-Forms line of its header says how a number chooses one: `nplurals=2; plural=(n != 1);` in the office's Dutch catalogue, an expression in C whose value is the form's index. Reading a catalogue, the standard library makes the expression a Python function, the translation's plural, and files each form under the singular and its index.

`django.utils.translation.trans_real.ngettext` passes its arguments, with the method's name `"ngettext"`, to `do_ntranslate`, which calls that method of the active translation or of `_default` (`django/utils/translation/trans_real.py:do_ntranslate`). `DjangoTranslation.ngettext` replaces the standard library's. Its catalogue, a `TranslationCatalog`, tries each catalogue merged into it with that catalogue's own formula, so a message is counted by the rule of the file it came from (`django/utils/translation/trans_real.py:TranslationCatalog.plural`). A message that none has goes to the fallback; with no fallback, as for `LANGUAGE_CODE` itself, the result is the singular for 1 and the plural otherwise, the English rule whatever the language (`django/utils/translation/trans_real.py:DjangoTranslation.ngettext`). `ngettext` does not put the number in the form; the caller does, with `%`. In German no catalogue has the message, nor does the fallback, `"en"`, so the English rule decides:

```text
# a run of the example
ngettext("%(num)d ship", "%(num)d ships", n) % {"num": n}
nl, n = 0, 1, 2:  '0 schepen'  '1 schip'  '2 schepen'
de, n = 0, 1, 2:  '0 ships'  '1 ship'  '2 ships'
nl, npgettext("tide", "%(num)d ship", "%(num)d ships", 2):  '%(num)d schepen'
```

Before any catalogue is read, `DjangoTranslation.plural` is what a comment calls the Germanic default, for a language without a catalogue: anything except one is plural (`django/utils/translation/trans_real.py:DjangoTranslation.__init__`). The first catalogue merged replaces it with its own (`django/utils/translation/trans_real.py:DjangoTranslation.merge`).

`django.utils.translation.trans_real.npgettext` joins the context to both forms and calls `ngettext`, and if the result contains the separator, calls it again with the forms alone (`django/utils/translation/trans_real.py:npgettext`). So a plural message with a context no catalogue has is translated as if it had none (the run's last line), where `pgettext` gives its message back.

## Marking without translating

`django.utils.translation.trans_real.gettext_noop` gives back its message (`django/utils/translation/trans_real.py:gettext_noop`). It only marks: makemessages passes its name to xgettext as a keyword, so the string is collected into the catalogues (`django/core/management/commands/makemessages.py:Command.process_locale_dir`; [Making catalogues: makemessages and compilemessages](commands.md)). Its docstring names the use: a string kept in the source language because it may be used outside the program, and translated later. The office keeps its log of berth requests in English, and translates an entry as it shows it:

```python
# harbour/office/berths.py
from django.utils.translation import gettext, gettext_noop

REQUESTED = gettext_noop("Berth requested.")  # stored in the log as it is


def shown(status):
    return gettext(status)  # translated as it is shown
```

In a run with Dutch active, the stored string is "Berth requested." and the shown one "Ligplaats aangevraagd.".
