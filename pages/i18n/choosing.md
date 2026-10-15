---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Choosing a language: `LocaleMiddleware`

`LocaleMiddleware` chooses each request's language before the view runs. `django.utils.translation.get_language_from_request` tries the path's language prefix, the language cookie, the Accept-Language header and `LANGUAGE_CODE` in turn, `get_supported_language_variant` turns each candidate into a code the site supports, and the middleware activates the result.

A visitor's wishes reach a request in three places, and in forms the site may not support exactly: a browser in Brussels asks for `"nl-be"`, and the harbour office lists `"nl"`. The choice must be made before the URL is resolved, since a language prefix matches only the active language. And all it reads comes from the client, so it bounds what it parses and what it remembers.

## `LocaleMiddleware.process_request`

`LocaleMiddleware.process_request` works in a fixed order (`django/middleware/locale.py:LocaleMiddleware.process_request`). It asks `is_language_prefix_patterns_used` whether the request's URLconf has `i18n_patterns` at its root, and whether the default language has a prefix there ([Language prefixes and translated routes](../urls/i18n.md)). It calls `django.utils.translation.get_language_from_request`, which reads the path only if the answer was yes. If the path names no supported language, and the URLconf has prefixes but none for the default language, it sets that choice aside and takes `LANGUAGE_CODE`. It activates the language, and sets the request's attribute `LANGUAGE_CODE` to the code `get_language` then gives, the activated translation's, in lower case; the cache middleware keys a page by it (`django/utils/cache.py:_i18n_cache_key_suffix`).

The third step follows from the matcher. Where the default language has no prefix, a `LocalePrefixPattern` gives an empty prefix only while that language is active, or none is (`django/urls/resolvers.py:LocalePrefixPattern.language_prefix`): with Dutch active, `"/arrivals/"` would not resolve. In a run of the example with such a URLconf, the test client's `"/arrivals/"` came back in English for Accept-Language: nl and for the cookie `"de"`.

Nothing deactivates the language after the response, and the thread keeps it ([The active language](active-language.md)). `LocaleMiddleware.async_capable` is false, so under ASGI it runs synchronously, adapted to its neighbours ([Sync and async in one chain](../handlers/async.md)). With `USE_I18N` false it calls the functions of `django/utils/translation/trans_null.py`, which choose `LANGUAGE_CODE` for every request and activate nothing.

> **Trap.** Django's documentation places `LocaleMiddleware` after `SessionMiddleware`, saying it "makes use of session data" (`docs/topics/i18n/translation.txt`). Nothing in the middleware or in `django/utils/translation/` reads the session. Its other rule stands: before `CommonMiddleware`, which resolves the path to decide on a slash (`django/middleware/common.py:CommonMiddleware.should_redirect_with_slash`).

## The four sources

`django.utils.translation.get_language_from_request` returns the first source that yields a supported code (`django/utils/translation/trans_real.py:get_language_from_request`).

1. **The path**, only with `check_path=True`. `get_language_from_path` matches `language_code_prefix_re`, a first segment of up to three parts joined by hyphens or at signs, and passes it to `get_supported_language_variant`: `"/nl-be/arrivals/"` gives `"nl"`.
2. **The cookie** that `LANGUAGE_COOKIE_NAME` names, `"django_language"` by default, which the view `set_language` sets ([The language views: `set_language` and `JavaScriptCatalog`](views.md)). A value `get_languages` holds exactly, with a catalogue, is returned as it is; any other goes through `get_supported_language_variant`, so `"nl-be"` gives `"nl"` and `"fr"` is passed over.
3. **The Accept-Language header**, whose languages `parse_accept_lang_header` gives the most wanted first. Each is checked against `language_code_re` and offered to `get_supported_language_variant`. A `"*"` ends the search.
4. **`LANGUAGE_CODE`**, through `get_supported_language_variant`, or as it is if even that fails, which the system check `"translation.E004"` reports (`django/core/checks/translation.py:check_language_settings_consistent`).

```text figure=where-the-language-comes-from
get_language_from_request(request, check_path): the first source that yields a supported code wins
LANGUAGES = en, nl, de

1 the path's prefix  read only with check_path=True, where the root URLconf uses i18n_patterns
                     "/nl/arrivals/", cookie "de"            ->  "nl"
2 the cookie         "django_language"
                     "de", Accept-Language: nl               ->  "de"  the header is not read
                     "fr", Accept-Language: nl               ->  no answer: on to the header, "nl"
3 Accept-Language    each language, the highest q first; "*" ends the search
                     nl-BE,nl;q=0.9,en;q=0.8                 ->  "nl"
4 LANGUAGE_CODE      no cookie, no header                    ->  "en"

get_supported_language_variant(code): one code, its candidates in turn
"nl-be"  "nl-be"  not in LANGUAGES
         "nl"     in LANGUAGES, and a "django" catalogue exists  ->  "nl"
"pt-pt"  with "pt-br" added to LANGUAGES
         "pt-pt", "pt"  neither in LANGUAGES
         the first code of LANGUAGES that begins "pt-"           ->  "pt-br"
"fr-ca"  "fr-ca", "fr" not in LANGUAGES, none begins "fr-"       ->  LookupError: no answer
```

*The four sources `get_language_from_request` tries, with requests from a run of the example and the language each gave; and how `get_supported_language_variant` turns one code into candidates.*

## Supported codes

`django.utils.translation.get_supported_language_variant` makes candidates: the code; the codes of its `"fallback"` in `django.conf.locale.LANG_INFO`, which only Chinese regional codes have (`"zh-tw"` gives `"zh-hant"`); and the code cut at each hyphen from the right, `"de-at-1996"` giving `"de-at"` and `"de"`. It returns the first whose lower case `get_languages` (`LANGUAGES`, keys lower-cased) holds and that `check_for_language` passes (`django/utils/translation/trans_real.py:get_supported_language_variant`).

Failing that, it takes the first code of `LANGUAGES` that begins with the code's language and a hyphen, without asking for a catalogue, and otherwise raises `LookupError`. `strict=True` skips that last search; nothing in Django passes it.

A code longer than `LANGUAGE_CODE_MAX_LENGTH`, 500 characters, is cut at its last hyphen within that length, and refused with `LookupError` if it has none there or `strict` is true. The constant's comment gives the reason: denial of service and memory exhaustion.

## Whether a catalogue exists

`django.utils.translation.check_for_language` refuses `None`, and a code longer than 500 characters, before any cache is consulted, and asks `translation_catalog_exists` about the rest (`django/utils/translation/trans_real.py:check_for_language`). That function refuses a code `language_code_re` does not accept, such as `"nl_BE"` or `"../etc"`, before any file is looked for (its comment cites ticket 21458). Otherwise it asks the standard library's gettext module for a catalogue of the domain `"django"` for the code's locale in any of `all_locale_paths`: `django/conf/locale/`, each directory of `LOCALE_PATHS`, and each installed application's `locale` directory (`django/utils/translation/trans_real.py:translation_catalog_exists`).

The test is looser than it sounds. The standard library also tries a locale without its region, so `"nl-be"` passes on the Dutch catalogue. German passes on Django's own catalogue, though the office has none, and so does French, which `LANGUAGES` does not list: that check is the caller's. A language with only a `"djangojs"` catalogue fails.

> **Changed in 6.0.8 and 5.2.17.** These security releases added the length check before the cached lookup, "so that oversized, attacker-controlled values are not retained as cache keys", as the docstring says; the notes name the posted language of `set_language` as the way in (`docs/releases/6.0.8.txt`).

## The header: `parse_accept_lang_header`

`parse_accept_lang_header` lower-cases the header, splits it with `accept_language_re`, written after RFC 9110 and RFC 5646, and returns each language with its weight, highest weight first, equal weights in the header's order (`django/utils/translation/trans_real.py:_parse_accept_lang_header`). A header with any part the expression rejects gives an empty tuple, and is ignored whole.

```text
# a run of the example: get_language_from_request(request), the request carrying only Accept-Language
fr-CA,*;q=0.5,nl;q=0.1    (('fr-ca', 1.0), ('*', 0.5), ('nl', 0.1))    -> 'en'
fr, de;q=0.5, nl;q=0.5    (('fr', 1.0), ('de', 0.5), ('nl', 0.5))      -> 'de'
nl;q=2                    ()                                           -> 'en'
fr, de;q=0                (('fr', 1.0), ('de', 0.0))                   -> 'de'
```

> **Trap.** RFC 9110 makes a weight of 0 mean "not acceptable". Django keeps such a language, last, and chooses it if the search reaches it and it is supported.

A header longer than 500 characters is parsed up to its last comma within that length, and one with no comma there gives nothing. The docstring's reason: parses are cached, and a huge value kept as a key would use memory (`django/utils/translation/trans_real.py:parse_accept_lang_header`).

## The caches

`translation_catalog_exists`, `get_supported_language_variant` and `_parse_accept_lang_header` each keep the 1000 answers most recently used, in a `functools.lru_cache`; the docstrings of the first two give the bound as a defence against memory exhaustion attacks. `get_languages` takes no argument and keeps one answer, `is_language_prefix_patterns_used` one for each URLconf. When a test overrides `LANGUAGES` or `LANGUAGE_CODE`, `reset_cache` empties the first two and `get_languages` ([Overriding settings](../startup/overrides.md)) (`django/utils/translation/trans_real.py:reset_cache`).

## On the way out: `LocaleMiddleware.process_response`

`LocaleMiddleware.process_response` sets Content-Language to the code `django.utils.translation.get_language` gives, with `setdefault`, so a view's own header stands (`django/middleware/locale.py:LocaleMiddleware.process_response`). It adds `"Accept-Language"` to `"Vary"` unless the URLconf has prefixes and the path holds one: `"/nl/arrivals/"` gets no `"Vary"`, and an unprefixed page forced into the default language gets it, though the header did not decide that page. It adds no `"Cookie"` to the response it passes on, though the cookie may have chosen the language; the redirect it makes for a 404 whose path lacks a prefix carries both ([Language prefixes and translated routes](../urls/i18n.md)).
