---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The language views: `set_language` and `JavaScriptCatalog`

`django/views/i18n.py` holds the views a project routes to for its languages: `set_language`, which stores the language a visitor chose in the language cookie and redirects, and `JavaScriptCatalog` and `JSONCatalog`, which send the browser the active language's catalogue of the `"djangojs"` domain, with its plural formula and its formats.

They serve a visitor picking a language, and a script in the browser with messages of its own. Neither chooses the language of the request it answers: `set_language` writes what `LocaleMiddleware` reads on the next request, and `JavaScriptCatalog` reads the language already active for this one.

## `set_language`

`set_language` first decides where to send the visitor, and then, for a `"POST"`, records the choice (`django/views/i18n.py:set_language`).

The address is the field `"next"`, of the posted form or else of the query string. It is used only if `url_has_allowed_host_and_scheme` accepts it for the request's own host, an `"http"` address being refused when the request came over HTTPS ([The helpers in `django/utils/http.py`](../http/helpers.md)). Otherwise the view tries the Referer header under the same test, and then `"/"`. A request that sent no `"next"` and whose Accept header does not admit `"text/html"` skips that search and is answered with a 204; a request with no Accept header admits everything (`django/http/request.py:HttpRequest.accepted_types`).

On a `"POST"` only, the view reads the field `"language"` and checks it with `django.utils.translation.check_for_language`, which asks whether Django, `LOCALE_PATHS` or an application has a catalogue of the `"django"` domain for the code (`django/utils/translation/trans_real.py:check_for_language`). A code that fails is ignored. For one that passes, the address is put through `translate_url`, which resolves it in the language active for this request and finds its address in the new one, and the code is set as the cookie ([Language prefixes and translated routes](../urls/i18n.md)). The cookie is made from these settings (`django/http/response.py:HttpResponseBase.set_cookie`):

| setting | default | sets the cookie's |
|---|---|---|
| `LANGUAGE_COOKIE_NAME` | `"django_language"` | name |
| `LANGUAGE_COOKIE_AGE` | `None`: neither attribute, and the cookie expires at browser close, as `docs/ref/settings.txt` says | Max-Age and Expires |
| `LANGUAGE_COOKIE_PATH` | `"/"` | Path |
| `LANGUAGE_COOKIE_DOMAIN` | `None`: no attribute | Domain |
| `LANGUAGE_COOKIE_SECURE` | `False` | Secure |
| `LANGUAGE_COOKIE_HTTPONLY` | `False`: a script can read it | HttpOnly |
| `LANGUAGE_COOKIE_SAMESITE` | `None`: no attribute | SameSite |

A `"GET"` gets the same redirect, or 204, and nothing more. The docstring gives the reason: the view changes how the visitor will see the rest of the site, so only a `"POST"` may do it.

`django/conf/urls/i18n.py` is a URLconf of one pattern for a project to include, `"setlang/"`, named `"set_language"` (`django/conf/urls/i18n.py:urlpatterns`). The example includes it under `"i18n/"`. A run, with the test client making the requests:

```text
POST /i18n/setlang/ with language=nl, next=/arrivals/
302 Found
Location: /arrivals/
Set-Cookie: django_language=nl; Path=/
Content-Language: en

GET /arrivals/, with that cookie
200 OK
Content-Language: nl

POST /i18n/setlang/ with language=fr, next=/arrivals/
302 Found
Location: /arrivals/
Set-Cookie: django_language=fr; Path=/
Content-Language: en

GET /arrivals/, with that cookie and Accept-Language: nl
200 OK
Content-Language: nl
```

The response that sets the cookie is still in English: the choice takes effect when `LocaleMiddleware` reads the cookie on the next request. The last two show that the view's check is not the middleware's. `check_for_language` does not consult `LANGUAGES`, and Django has a French catalogue, so `"fr"` is stored; `django.utils.translation.get_language_from_request` takes a cookie only where it or a variant of it is in `LANGUAGES`, so it passes over this one and reads the header ([Choosing a language: `LocaleMiddleware`](choosing.md)) (`django/utils/translation/trans_real.py:get_language_from_request`).

## `JavaScriptCatalog`

A script in the browser shows messages too, and Django's translation functions do not run there. `JavaScriptCatalog` sends it a script holding the active language's messages of the `"djangojs"` domain, which makemessages fills from JavaScript files ([Making catalogues: makemessages and compilemessages](commands.md)), and functions that look them up (`django/views/i18n.py:JavaScriptCatalog.get`).

The language is the active one, as `django.utils.translation.get_language` gives it. The domain is the URL's keyword argument `domain=`, or else `JavaScriptCatalog.domain`. The packages come from the keyword argument `packages=`, names joined by `"+"`, or else from `JavaScriptCatalog.packages`, which `as_view` can set; with neither, every installed application is searched. `JavaScriptCatalog.get_paths` turns each name into its application's `"locale"` directory, and raises `ValueError` for a name that is no installed application's (`django/views/i18n.py:JavaScriptCatalog.get_paths`). The admin's catalogue is served so: `AdminSite.i18n_javascript` calls the view with `packages=["django.contrib.admin"]` ([The site's own pages: the index, the login and `AdminSite.each_context`](../admin/site-views.md)) (`django/contrib/admin/sites.py:AdminSite.i18n_javascript`).

> **Trap.** The class's docstring names `'django.conf'` as the default package; the default is every installed application, and `"django.conf"`, given as a package, is refused.

On every request the view makes a new `DjangoTranslation` of that language and domain, with those directories as its argument localedirs. It is never the cached translation of the language, and in a domain other than `"django"` it is made otherwise ([Message catalogues: `DjangoTranslation`](catalogues.md)) (`django/utils/translation/trans_real.py:DjangoTranslation.__init__`):

- Django's own catalogue is not read (Django's locale directory has no `"djangojs"` one; the admin's has).
- The directories given replace the installed applications and are merged in the order listed, so where two packages translate one message the one listed last wins, where `INSTALLED_APPS` lets the first win.
- `LOCALE_PATHS` are merged above them all the same.
- The default language may lack a catalogue, and the fallback to it is made afresh, in the same domain from the same directories.

`JavaScriptCatalog.get_catalog` walks the translation's catalogue and then each fallback behind it, keeping the first value found for each key, so the language's own translations hide those of `LANGUAGE_CODE`. It leaves out the header. A plural message becomes a list of its forms in order, as many as the header's nplurals says (`JavaScriptCatalog._num_plurals`, two without one), with an empty string for a form the catalogue lacks. A message with a context keeps its key, context and message joined by `"\x04"`. `JavaScriptCatalog.get_plural` takes the expression after `plural=` in the header's Plural-Forms line, or `None` without one, and `django.views.i18n.get_formats` reads the active language's formats with `get_format` ([Locale formats: `get_format` and the format modules](formats.md)) (`django/views/i18n.py:JavaScriptCatalog.get_catalog`).

`JavaScriptCatalog.render_to_response` writes the catalogue and the formats as JSON into the template `"i18n_catalog.js"`, rendered by a `django.template.Engine` made with no options, not by the project's `TEMPLATES` (`django/views/i18n.py:JavaScriptCatalog.render_to_response`). In the browser the script keeps everything on an object named django on the global object (`django/views/templates/i18n_catalog.js`). Its function pluralidx is the plural expression, written into the script as it stands, with true or false made 1 or 0; without one, only a count of one is singular. Its messages are added key by key to django.catalog, so two catalogues loaded on one page combine. Only the first script loaded defines the formats and the functions gettext, ngettext, gettext_noop, pgettext, npgettext, interpolate and get_format, and puts each on the global object as well. Two parts of it, from a run in Dutch:

```text
GET /jsi18n/, with Accept-Language: nl
  django.pluralidx = function(n) {
    const v = (n != 1);
  ...
  const newcatalog = {
    "%s ship": [
      "%s schip",
      "%s schepen"
    ],
    "Arrivals": "Aankomsten"
  };
```

## `JSONCatalog`

`JSONCatalog` is the same view with `JSONCatalog.render_to_response` replaced: it returns the catalogue, the formats and the plural expression as a `JsonResponse`, the data without the script (`django/views/i18n.py:JSONCatalog`). Routed at `"jsoni18n/"` in a run of the example, it gives this, its formats left out; the office has no German catalogue, and English, the fallback, has none either:

```text
GET /jsoni18n/, with Accept-Language: nl
{"catalog": {"Arrivals": "Aankomsten", "%s ship": ["%s schip", "%s schepen"]}, "plural": "(n != 1)"}
GET /jsoni18n/, with Accept-Language: de
{"catalog": {}, "plural": null}
```
