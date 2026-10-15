---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`

The page cache keeps whole responses and answers a repeated `"GET"` or `"HEAD"` with one of them before the view runs. `FetchFromCacheMiddleware` looks a response up, `UpdateCacheMiddleware` stores one, `CacheMiddleware` is both, and `cache_page` applies `CacheMiddleware` to one view; the keys are made by `learn_cache_key` and `get_cache_key`.

A page cache must decide, before any view has run, whether it holds the answer, and the URL alone does not decide it. A response may depend on request headers, a cookie or a language, and names them in its `"Vary"` header; requests for one URL that differ in those headers must not share an entry. But at lookup there is no response yet to say which. So Django learns the list from each response it stores for a URL and keeps it in the cache under a key made from the URL; a later request reads the list first and builds from it the key of the page, "without building the response object itself", as the docstring says (`django/utils/cache.py:learn_cache_key`). The cache beneath is that of [The cache API: `caches` and `BaseCache`](cache-api.md).

## The two halves, and their order

The module's docstring puts `UpdateCacheMiddleware` first in `MIDDLEWARE` and `FetchFromCacheMiddleware` last, counterintuitive but correct, it says: the update half must run last on the way out, where the chain runs bottom-up, and the fetch half last on the way in (`django/middleware/cache.py`; [Handlers and middleware](../handlers.md#the-chain-is-an-onion)). So the fetch half makes its key after `LocaleMiddleware` has set the language, and the update half reads the `"Vary"` after `SessionMiddleware`, `GZipMiddleware` and `LocaleMiddleware` have added to it (`docs/topics/cache.txt`).

On a hit, `FetchFromCacheMiddleware.process_request` returns the stored response, and `MiddlewareMixin.__call__` does not call the layer inside it (`django/middleware/__init__.py:MiddlewareMixin.__call__`). With the fetch half last, the URL resolver, the `process_view` hooks and the view do not run. The response goes back out through the middleware above, `UpdateCacheMiddleware` last.

The halves speak through one attribute of the request, `HttpRequest._cache_update_cache`. The fetch half sets it true after a miss, and false for a hit or for a method other than `"GET"` and `"HEAD"`; the update half stores only when it is true (`django/middleware/cache.py:UpdateCacheMiddleware._should_update_cache`). A hit passing back out is not stored again, and a request answered by a middleware between the two, so that the fetch half never ran, has no attribute and stores nothing.

## A miss and a hit

The example's timetable view is decorated with `cache_page(60)`, which runs `CacheMiddleware` around it. Two requests from the test client two seconds apart, a `"HEAD"` and a `"POST"`, with the queries counted:

```text
GET /timetable/  200, 1 query
  Expires: Thu, 15 Oct 2026 21:10:51 GMT
  Cache-Control: max-age=60
the cache's keys:
  :1:views.decorators.cache.cache_header..d85587acf917224b6af36a3c98d2b75f.en-us.UTC  ->  []
  :1:views.decorators.cache.cache_page..GET.d85587acf917224b6af36a3c98d2b75f.d41d8cd98f00b204e9800998ecf8427e.en-us.UTC  ->  the response
GET /timetable/  200, 0 queries
  Expires: Thu, 15 Oct 2026 21:10:51 GMT
  Cache-Control: max-age=60
  Age: 2
HEAD /timetable/  200, 0 queries, the same headers
POST /timetable/  200, 1 query, no Expires, no Cache-Control
```

The first request missed and left two entries: the header list, empty since the response has no `"Vary"`, and the response, with the `"Expires"` and `"max-age"` put on it before it was stored. The second, and the `"HEAD"`, were answered from that entry; the `"POST"` was neither looked up nor stored.

## Two keys for one URL

```text figure=two-keys
first GET http://harbour.example/timetable/: a miss; the view runs; no "Vary"
  process_response
    learn_cache_key
      the header list, [] (the headers "Vary" names, as keys of request.META, sorted),
      under the header key, for 60 seconds:
        :1:views.decorators.cache.cache_header..d85587acf917224b6af36a3c98d2b75f.en-us.UTC
      returns the page key
    the response, under the page key, for 60 seconds:
        :1:views.decorators.cache.cache_page..GET.d85587acf917224b6af36a3c98d2b75f.d41d8cd98f00b204e9800998ecf8427e.en-us.UTC

later GET: a hit
  get_cache_key: the header key -> []; the page key built from [] and this request
  the page key -> the response, returned without the view

the parts of a key
  :1:                                the cache's KEY_PREFIX (empty) and VERSION (1)
  cache_header, cache_page           which key
  (empty)                            the page cache's key prefix
  GET                                the method, in the page key only
  d85587acf917224b6af36a3c98d2b75f   MD5 of the absolute URL
  d41d8cd98f00b204e9800998ecf8427e   MD5 of the listed headers' values as netstrings: here, of nothing
  en-us, UTC                         the language (USE_I18N), the time zone (USE_TZ)
```

*The two keys of the timetable view's page, from a run: the header key, made from the URL, holds the headers the response varies on; the page key, made also from the method and those headers' values, holds the response.*

`learn_cache_key` runs when a response is to be stored. It turns each name in the response's `"Vary"` into the request's key in `HttpRequest.META`, upper case, hyphens as underscores, with `"HTTP_"` in front, sorts the list, stores it under the header key for the timeout it is given, and returns the page key for the request's method. With `USE_I18N` on, Accept-Language is left out: a comment says the key already carries the language, and the raw header would store the same content under several keys (ticket 18191) (`django/utils/cache.py:learn_cache_key`).

`get_cache_key` runs at lookup. It reads the list under the header key, returns `None` if there is none, and otherwise builds the page key for the method it is given (`django/utils/cache.py:get_cache_key`). A header key holds one list, written again by each response stored, so the last response's `"Vary"` decides how the next request for that URL, language and zone is keyed.

Both keys hash the URL from `HttpRequest.build_absolute_uri`, host and query string included (`django/utils/cache.py:_generate_cache_header_key`). The page key also hashes each listed header's value, empty where the request lacks it, as a netstring: its length in bytes, a colon, the bytes and a comma (`django/utils/cache.py:_generate_cache_key`). Django's tests check that `"EU"` then nothing and nothing then `"EU"` get different keys (`tests/cache/tests.py:CacheUtils.test_learn_cache_key_no_header_collision`). Then `_i18n_cache_key_suffix` adds, with `USE_I18N`, the language, the request's attribute `LANGUAGE_CODE` where `LocaleMiddleware` has set it and otherwise the active language, and with `USE_TZ` the current time zone's name (`django/utils/cache.py:_i18n_cache_key_suffix`; [Choosing a language: `LocaleMiddleware`](../i18n/choosing.md), [Time zones](../i18n/time-zones.md)). The cache puts its own prefix and version in front.

> **Changed in 6.1.** The headers' values are hashed as netstrings. A page that varies on a header has a different key from the one older releases made, and its first request after an upgrade is a miss (`docs/releases/6.1.txt`).

## `FetchFromCacheMiddleware.process_request`

For a method other than `"GET"` or `"HEAD"`, `FetchFromCacheMiddleware.process_request` sets the flag, `HttpRequest._cache_update_cache`, false and returns. Otherwise it asks `get_cache_key` for the key of a `"GET"`, since the module expects a `"HEAD"` to get exactly the `"GET"`'s headers. With no key it sets the flag true and returns `None`; so it does with no entry, once a `"HEAD"` has tried the key of an earlier `"HEAD"` (`django/middleware/cache.py:FetchFromCacheMiddleware.process_request`).

On a hit, if the stored `"max-age"` and `"Expires"` both parse, it sets `"Age"`: the first less the seconds left before the second, never below 0 in case, the comment says, the clock was turned back. It sets the flag false and returns what the cache gave back.

## `UpdateCacheMiddleware.process_response`

`UpdateCacheMiddleware.process_response` returns the response untouched at the first of these that applies (`django/middleware/cache.py:UpdateCacheMiddleware.process_response`):

1. `HttpRequest._cache_update_cache` is missing or false.
2. The response is streaming, or its status is neither 200 nor 304.
3. It sets cookies and its `"Vary"` names Cookie; the comment calls such a cookie user-specific and maybe security-sensitive.
4. Its Cache-Control has `"private"`, `"no-cache"` or `"no-store"`, read in lower case by `split_directive_names`, so that `private="Set-Cookie"` counts too (`django/utils/http.py:split_directive_names`).
5. Its `"Vary"` holds `*`.
6. No page timeout is set, and its `"max-age"` is 0.

The timeout is the page timeout, which only `CacheMiddleware` sets, or else the response's `"max-age"`, or else the cache timeout, `CACHE_MIDDLEWARE_SECONDS` unless `CacheMiddleware` is given one. The middleware gives it to `patch_response_headers`, which adds `"Expires"` if absent and a `"max-age"`, keeping a smaller one already there ([Cache headers and conditional requests: `django/utils/cache.py`](http-caching.md)). If the request has an `"Authorization"` header and the Cache-Control is not `"public"`, it adds Authorization to `"Vary"`, so each credential has its own page key, to simplify the keys, the documentation says (`docs/topics/cache.txt`). Then, if the timeout is not 0 and the status is 200, it calls `learn_cache_key` and stores the response under the page key for the timeout. A 304 gets the headers and is not stored.

A response with a callable `render` is stored by a post-render callback, which runs at once if it is rendered already; a template response refuses to be pickled before it is rendered (`django/template/response.py:SimpleTemplateResponse.__getstate__`).

## `CacheMiddleware` and `cache_page`

`CacheMiddleware` subclasses both halves, and fetches on the way in and updates on the way out from one place in the list; the module's docstring keeps it for simple sites, the two halves being needed where another middleware "needs to affect the cache key", most often `LocaleMiddleware` (`django/middleware/cache.py`). `CacheMiddleware.__init__` takes a cache timeout, a page timeout, and a key prefix and a cache alias as keyword arguments, and a comment separates a value provided as the default from one not provided: `key_prefix=None` gives the prefix `""`, `cache_alias=None` the alias `DEFAULT_CACHE_ALIAS`, `"default"`, and either left out keeps the setting's value (`django/middleware/cache.py:CacheMiddleware.__init__`). A cache timeout replaces `CACHE_MIDDLEWARE_SECONDS` unless it is `None`.

`cache_page(timeout, *, cache=None, key_prefix=None)` calls `decorator_from_middleware_with_args(CacheMiddleware)` with `page_timeout=timeout` and always with the alias and the prefix (`django/views/decorators/cache.py:cache_page`). So it runs inside the whole chain, after the URL is resolved, and returns a hit without `process_response` (`django/utils/decorators.py:make_middleware_decorator`; [A middleware as a decorator](../views/middleware-decorators.md)). Its timeout, unless `None`, wins over the response's `"max-age"`, and it never takes the prefix or the alias from the settings:

| setting | default | for the middleware | for `cache_page` |
|---|---|---|---|
| `CACHE_MIDDLEWARE_SECONDS` | 600 | the timeout when the response has no `"max-age"` | the same, when its timeout is `None` |
| `CACHE_MIDDLEWARE_KEY_PREFIX` | `""` | the prefix in both keys | not used: its own prefix, or `""` |
| `CACHE_MIDDLEWARE_ALIAS` | `"default"` | the cache used | not used: its own alias, or `"default"` |

*The page cache's settings, with their defaults from `django/conf/global_settings.py`.*

> **Trap.** `cache_page` stores the response before it passes back out through `MIDDLEWARE`, so a `"Vary"` that `SessionMiddleware` or `LocaleMiddleware` adds on the way out is not in the list it learns; the documentation keeps it for content safe to reuse for any request to the URL (`docs/topics/cache.txt`).
