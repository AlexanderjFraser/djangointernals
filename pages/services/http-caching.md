---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Cache headers and conditional requests: `django/utils/cache.py`

`django/utils/cache.py` holds the functions that tell browsers and proxies whether and for how long to keep a response, `patch_cache_control`, `patch_response_headers`, `add_never_cache_headers` and `patch_vary_headers`, and `get_conditional_response`, which decides from a request's preconditions whether to answer 304 Not Modified or 412 Precondition Failed instead. `ConditionalGetMiddleware` and the `condition` decorator call it.

Caches Django never sees, the browser's or a proxy's, may keep a response, and its headers say how: Cache-Control whether, by whom and for how long; `"Expires"` until when; `"Vary"` which request headers, besides the URL, it depends on. A client with a stale copy sends back the **validator** it was given, the `"ETag"` or the Last-Modified time, in If-None-Match or If-Modified-Since, and may be answered 304 Not Modified, with no body. A client changing a resource sends one in If-Match or If-Unmodified-Since, and is answered 412 Precondition Failed if the version there is not the one it means.

A decorator, a middleware and the session code may all work on one response, so the functions that write Cache-Control, `"Expires"` and `"Vary"` merge into what is there.

## Cache-Control: `patch_cache_control`

`patch_cache_control` merges the directives given as keyword arguments into those of Cache-Control. It splits each item of the header at its first `=` into a name, in lower case, and a value, `True` for a directive with none; an argument's name becomes a directive's with underscores turned into hyphens, so `max_age=60` sets `"max-age"`. On the way out only `True` itself gives the bare name; any other value gives the name, `=` and the value as text, so `private=False` writes `private=False` (`django/utils/cache.py:patch_cache_control`). Where what is given meets what is there:

- `"max-age"` becomes the smaller of the two. The comment says when this happens: a decorator and a middleware both at work on one view.
- `"public"` and `"private"` exclude each other: the one given removes the other.
- `"no-cache"` may carry a field name and appear more than once, so its values are kept as a set, each written as a `"no-cache"` of its own; a bare `"no-cache"`, there or given, absorbs them.
- Any other directive given replaces the one there, in its place; a new one goes at the end.

```text
patch_cache_control(response, max_age=60, private=True)
    before:  Cache-Control: Public, max-age=600, no-cache="Set-Cookie"
    after:   Cache-Control: max-age=60, no-cache="Set-Cookie", private
```

`get_max_age` reads `"max-age"` back as an integer, or `None` when it is missing or not a whole number (`django/utils/cache.py:get_max_age`). The page cache takes a timeout from it ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](page-cache.md)).

## Expires and never caching

`patch_response_headers` gives a response a lifetime in seconds, `CACHE_MIDDLEWARE_SECONDS` (600) when none is given and 0 for a negative one. It sets `"Expires"` that many seconds from now, written by `http_date`, unless the response has one, and passes the lifetime to `patch_cache_control` as the max-age (`django/utils/cache.py:patch_response_headers`). The docstring says each header is added only if absent; for `"max-age"` the smaller value wins instead, so a response with `max-age=30` keeps it while a call with 300 sets `"Expires"` 300 seconds ahead.

`add_never_cache_headers` calls it with -1, which sets `"Expires"`, where there is none, to the present moment and `"max-age"` to 0, then adds `"no-cache"`, `"no-store"`, `"must-revalidate"` and `"private"`, the last removing any `"public"` (`django/utils/cache.py:add_never_cache_headers`). The decorators `cache_control` and `never_cache` apply `patch_cache_control` and `add_never_cache_headers` to a view's response ([View decorators](../views/decorators.md)).

## Vary: `patch_vary_headers`

A response that depends on a request header must name it in `"Vary"`, or a cache keyed on the URL alone may give one visitor's version to another. `patch_vary_headers` adds names to the header. It keeps the names already there in their order, and a comment gives the reason: a cache may rely on the order, in computing an MD5 hash, say. It strips each new name and appends, in the order given, those not there already, comparing without regard to case. If `"*"` is among the names, old or new, the header becomes `"*"` alone (`django/utils/cache.py:patch_vary_headers`). `has_vary_header` asks whether a name is there, on the same terms (`django/utils/cache.py:has_vary_header`).

## `get_conditional_response`

`get_conditional_response` is given the request and the validators of the version the server has now: an `"ETag"` with its quotes, and a last-modified time in whole seconds since the epoch. It returns a 304 or a 412 to send instead, or else the response it was given, `None` if none (`django/utils/cache.py:get_conditional_response`). A response whose status is outside the 200s it returns at once. It reads the tags of If-Match and If-None-Match with `parse_etags`, which drops a tag without its quotes, and the dates with `parse_http_date_safe`, so a header it cannot read counts as absent. Then it tests the preconditions in the order of RFC 9110's section 13.2.2, which a comment names:

```text figure=the-preconditions
get_conditional_response(request, etag, last_modified, response)

0  a response given, its status outside 200-299  ->  that response, untouched
1  If-Match, if present:
     the current ETag does not match  ->  412
2  If-Unmodified-Since, only without If-Match:
     no last-modified time, or one later than the date  ->  412
3  If-None-Match, if present:
     the current ETag matches  ->  304 for GET or HEAD, 412 otherwise
4  If-Modified-Since, only without If-None-Match, only for GET or HEAD:
     a last-modified time no later than the date  ->  304
5  If-Range: not supported
6  otherwise  ->  the response given (None from condition)

If-Match: strong comparison; a weak ETag (W/"...") never matches; * matches any ETag
If-None-Match: weak comparison, W/ stripped from both sides; * matches any ETag
With no current ETag, neither header matches.
```

*The order in which `get_conditional_response` tests a request's preconditions, and what each failure returns. The first two answer 412; the last two answer 304 to a GET or a HEAD, and for another method If-None-Match answers 412 and If-Modified-Since is not tested.*

If-Match uses the strong comparison: the current tag must be in the list exactly, so a weak one never matches, though `"*"` matches any tag (`django/utils/cache.py:_if_match_passes`). If-None-Match uses the weak comparison, stripping `"W/"` from both sides first (`django/utils/cache.py:_if_none_match_passes`). With no current tag neither header matches: If-Match fails with a 412, and If-None-Match gives no 304. The dates are compared as integers, and with no last-modified time If-Modified-Since never gives a 304 (`django/utils/cache.py:_if_modified_since_passes`), while If-Unmodified-Since, unless an If-Match came with it, always gives a 412, to a `"GET"` as well (`django/utils/cache.py:_if_unmodified_since_passes`).

`_not_modified` makes the 304, an `HttpResponseNotModified`, which has no Content-Type and refuses a body. Given the full response, it copies over Cache-Control, Content-Location, `"Date"`, `"ETag"`, `"Expires"`, Last-Modified and `"Vary"`, the headers RFC 9110's section 15.4.5 requires and Last-Modified, as its comment says, and the cookies, which by the old cookie specification its comment quotes a proxy passes on with a 304 as with a 200 (`django/utils/cache.py:_not_modified`). `_precondition_failed` makes the 412, an `HttpResponse` with an empty body, and logs it through `log_response` as a warning to `"django.request"` (`django/utils/cache.py:_precondition_failed`).

## `ConditionalGetMiddleware`

`ConditionalGetMiddleware`'s one hook is `process_response`, so it acts on the finished response, after the view has run (`django/middleware/http.py:ConditionalGetMiddleware.process_response`). It leaves every method but `"GET"` alone, and its comment gives two reasons: for an unsafe method it is too late to refuse with a 412, and for a `"HEAD"` the body is always empty, so no accurate tag can be computed. Unless Cache-Control holds `"no-store"`, which `ConditionalGetMiddleware.needs_etag` looks for, a response without an `"ETag"` is given one by `set_response_etag`: the MD5 of the content in quotes, a strong tag, and none for a streaming or an empty response (`django/utils/cache.py:set_response_etag`). A response with an `"ETag"` or a readable Last-Modified then goes to `get_conditional_response`. The middleware saves sending the body, not making it, the comparison the documentation draws with `condition` (`docs/topics/conditional-view-processing.txt`).

## Under the `condition` decorator

The `condition` decorator calls `get_conditional_response` before the view, with what its functions return: the tag through `quote_etag`, so a bare one becomes strong, and the time, made aware in UTC if naive, in whole seconds (`django/views/decorators/http.py:condition`). It passes no response, so `None` back means the view is to run, and a 304 comes back bare; the wrapper then sets only Last-Modified and `"ETag"`, where missing, and only for `"GET"` and `"HEAD"`. So, as the documentation says, a decorator that sets `"Vary"` or Cache-Control must stand above `condition` for its headers to reach a 304 ([View decorators](../views/decorators.md)) (`docs/topics/conditional-view-processing.txt`).

The harbour office's voyages, under `condition`, tagged by their number:

```python
# notices/views.py, in part
def voyages_tag(request):
    return "voyages-%d" % Voyage.objects.count()


@condition(etag_func=voyages_tag)
def voyages(request):
    rows = Voyage.objects.select_related("ship").order_by("sailed")
    return HttpResponse("\n".join(f"{v.sailed}  {v.ship}" for v in rows), content_type="text/plain")
```

Requests from Django's test client, with one voyage in the table, counting the SQL statements sent:

```text
GET /voyages/  ->  200, 2 queries, ETag: "voyages-1"
GET /voyages/ with If-None-Match: "voyages-1"  ->  304, 1 query, ETag: "voyages-1"
GET /voyages/ with If-None-Match: W/"voyages-1"  ->  304, 1 query, ETag: "voyages-1"
GET /voyages/ with If-None-Match: "voyages-0"  ->  200, 2 queries, ETag: "voyages-1"
GET /voyages/ with If-Match: W/"voyages-1"  ->  412, 1 query, ETag: "voyages-1"
POST /voyages/ with If-Match: "voyages-0"  ->  412, 1 query
POST /voyages/ with If-Match: "voyages-1"  ->  200, 2 queries
POST /voyages/ with If-None-Match: "voyages-1"  ->  412, 1 query
```

The tag's query ran every time, the view's only when the view did. A weak tag matched in If-None-Match and failed in If-Match. The `"POST"` that named the current version reached the view, and got no `"ETag"`.
