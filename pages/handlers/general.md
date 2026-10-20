---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The general-purpose middleware

The general-purpose middleware serve any request and response, whatever the project: `CommonMiddleware` refuses unwanted user agents and redirects an address that lacks the slash of `settings.APPEND_SLASH` or the www. of `settings.PREPEND_WWW`, `GZipMiddleware` compresses the response, and `BrokenLinkEmailsMiddleware` tells the managers about a broken link. Where each stands in `settings.MIDDLEWARE` is part of what it does.

A layer sees the response as the layers inside it have made it ([Handlers and middleware](../handlers.md#the-chain-is-an-onion)), and the documentation places each of the three (`docs/ref/middleware.txt`, `docs/howto/error-reporting.txt`). `CommonMiddleware` sets the Content-Length a response not streamed lacks: it stands outside any layer that may change the response, and a layer outside it that changes the body must reset the length, as `GZipMiddleware` does. `GZipMiddleware` changes the body: it stands outside all that reads or changes it, and inside `UpdateCacheMiddleware`, which stores the response under the headers its `"Vary"` names ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md)). `BrokenLinkEmailsMiddleware` reports the 404 it is handed: it stands outside every layer that turns a 404 into something else.

`ConditionalGetMiddleware`, the class of `django/middleware/http.py`, can answer a conditional `"GET"` with a 304 ([Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md#conditionalgetmiddleware)); the figure has it among the layers that place the three:

```text figure=where-they-stand
MIDDLEWARE, outermost first; a response climbs from the centre

UpdateCacheMiddleware: stores the response under the headers "Vary" names
  GZipMiddleware: adds Accept-Encoding to "Vary", compresses the body [outside all that reads or changes the body]
    ConditionalGetMiddleware: tags the body
      BrokenLinkEmailsMiddleware: mails about a 404 [outside all that turns a 404 into something else]
        LocaleMiddleware: may turn a 404 into a redirect
          CommonMiddleware: may turn a 404 into a redirect with a slash, measures the body [outside all that changes the response]
            the centre: the resolver's 404, or a view's Http404
```

*The three, accented, in an order the documentation allows: beside each layer, what it does to a response on the way out; in brackets, what places each.*

In the blocks below, A, B and C are middleware that only write down what they are handed: A stands outside the middleware a block is about, and B or C inside it.

## `CommonMiddleware` on the way in

`CommonMiddleware.process_request` can end a request before any layer inside it runs. A User-Agent that a pattern of `settings.DISALLOWED_USER_AGENTS` finds raises `PermissionDenied`, so that the project's 403 view answers (`docs/releases/1.9.txt`): the exception leaves `MiddlewareMixin.__call__` before C or `CommonMiddleware.process_response` can run, and the wrapper around the layer makes it the 403 that A is handed (`django/core/handlers/exception.py:convert_exception_to_response`).

For every request that check lets through, `process_request` then calls `HttpRequest.get_host`, which raises `DisallowedHost` for a host that `settings.ALLOWED_HOSTS` does not allow; the wrapper makes that a 400 ([Headers, host and scheme](../http/headers.md#the-host)). With `settings.PREPEND_WWW` true and a host not beginning with `"www."`, the layer redirects at once to the www. host, with any slash the path needs: /plain leaves, never reaching C, as one 301 to /plain/ on the www. host (`django/middleware/common.py:CommonMiddleware.process_request`, `django/http/request.py:HttpRequest.get_host`).

## `CommonMiddleware` on the way out

`CommonMiddleware.process_response` acts on any 404 it is handed: the resolver's, a view's `Http404`, a middleware's. With `settings.APPEND_SLASH` true, the default, `CommonMiddleware.should_redirect_with_slash` asks whether a path without a final slash fails to resolve, resolves with one, and leads to a view without the `"should_append_slash"` mark of `no_append_slash` ([View decorators](../views/decorators.md#marks)); if so, the 404 becomes a redirect to the path with its slash (`django/middleware/common.py:CommonMiddleware.should_redirect_with_slash`). A view's own 404 stands: its path resolves. C is handed the 404 and A the redirect ([Resolving a path](../urls/resolving.md#the-resolvers-other-callers) records the resolver's side):

```text recording=handlers
WSGI, GET /plain: CommonMiddleware turns the 404 that C saw into a redirect
...
    C.process_response(404)
    CommonMiddleware.process_response(404)
    A.process_response(301)
    A sees Location: /plain/
    ...
```

> **Why.** Checking for a slash means resolving the path, which may be somewhat costly. On the way out only a request that has already ended in a 404 pays for it, and the way in makes it only when a redirect for `settings.PREPEND_WWW` is being sent anyway; made there always, it would resolve every path without a slash before the handler did (`django/middleware/common.py:CommonMiddleware.process_request`).

`CommonMiddleware.get_full_path_with_slash` builds the address from the full path, with two guards. Under `settings.DEBUG` a `"DELETE"`, `"POST"`, `"PUT"` or `"PATCH"`, whose data the redirect cannot carry, raises `RuntimeError` instead, which A receives as a 500. A leading `"//"` becomes `"/%2F"` through `escape_leading_slashes`, lest a browser take the `"Location"` for another host's (CVE-2018-14574, `docs/releases/1.11.15.txt`; `django/middleware/common.py:CommonMiddleware.get_full_path_with_slash`, `django/utils/http.py:escape_leading_slashes`).

Then a response that is not streaming and lacks a Content-Length is given its body's length; a stream gets none (`django/middleware/common.py:CommonMiddleware.process_response`).

## `GZipMiddleware`

`GZipMiddleware.process_response` compresses a response for a client that reads gzip (`django/middleware/gzip.py:GZipMiddleware.process_response`). It first lets go a body not streamed and under 200 bytes, and a response with a Content-Encoding already, such as a page the cache stored compressed and `FetchFromCacheMiddleware` hands back. Only then does it add Accept-Encoding to `"Vary"`, before reading the client's Accept-Encoding, since from there what is sent depends on that header: 199 bytes leave with no `"Vary"` even for a client that sent gzip, and 400 bytes for a client that sent no Accept-Encoding leave uncompressed but varying on it (`django/utils/cache.py:patch_vary_headers`). A client whose Accept-Encoding lacks gzip gets the response as it is; for the rest a body is compressed by `compress_string` and kept only if shorter, and a stream is wrapped in `compress_sequence`, or `acompress_sequence`, and loses its Content-Length.

Last, a strong `"ETag"` is given `"W/"` and Content-Encoding becomes `"gzip"`. The compressed response keeps the uncompressed one's tag, and RFC 9110, section 8.8.1, which the code's comment cites, calls weak a validator sent alike for a representation with the gzip coding and for one without; the weak tag still matches an If-None-Match, which is compared weakly (`django/utils/cache.py:_if_none_match_passes`). The compressors vary the length by up to `GZipMiddleware.max_random_bytes` bytes, against the BREACH attack ([Text helpers: `Truncator` and `django/utils/text.py`](../utils/text.md#compressing-a-response)).

`ConditionalGetMiddleware`, inside it, tags the plain bytes, and the tag comes out weak; with B between, for a `"GET"` of /large/ that accepts gzip:

```text recording=handlers
MIDDLEWARE = [A, GZipMiddleware, B, ConditionalGetMiddleware]
...
ConditionalGetMiddleware.process_response(200)
B.process_response(200)
B sees ETag: "0d723d1c244281678c8cd2957f0744b2"
...
GZipMiddleware.process_response(200)
A.process_response(200)
A sees ETag: W/"0d723d1c244281678c8cd2957f0744b2"
A sees Content-Encoding: gzip
...
```

## `BrokenLinkEmailsMiddleware`

`BrokenLinkEmailsMiddleware.process_response` tells the site's managers about a 404 while `settings.DEBUG` is false (`django/middleware/common.py:BrokenLinkEmailsMiddleware.process_response`). `BrokenLinkEmailsMiddleware.is_ignorable_request` first lets the request go if (`django/middleware/common.py:BrokenLinkEmailsMiddleware.is_ignorable_request`):

- there is no `"Referer"`, as from a typed address;
- with `settings.APPEND_SLASH`, the full path ends in a slash and the `"Referer"` is that path without it, taken for an internal redirect;
- the `"Referer"` is not on this host and holds a `"?"`, taken for a search engine;
- the `"Referer"`'s path is the full path requested, and its host this one or no host at all, as some bots send to pass the first test (`docs/releases/1.9.txt`);
- the full path matches a pattern of `settings.IGNORABLE_404_URLS`.

The second test compares a `"Referer"`, which a browser sends as a whole URL, with a path, so only a bare path passes it: for /missing/, a browser's `"Referer"` of the address without its slash brings a mail.

Otherwise `mail_managers` mails `settings.MANAGERS` through the default mailer unless, with `MAILERS` defined, `BrokenLinkEmailsMiddleware.using` names another ([Sending email: `mailers` and the email backends](../services/mailers.md)) (`django/middleware/common.py:BrokenLinkEmailsMiddleware.send_mail`). The subject says "Broken INTERNAL link" when the `"Referer"` is on this host, a subdomain counting as another (`django/middleware/common.py:BrokenLinkEmailsMiddleware.is_internal_request`).

`BrokenLinkEmailsMiddleware` must stand outside every layer that turns a 404 into something else, a redirect from `LocaleMiddleware` or `CommonMiddleware`, a page from `FlatpageFallbackMiddleware` (`docs/howto/error-reporting.txt`). Inside `CommonMiddleware`, for /plain with a same-host `"Referer"`, it reports a page the client is redirected from:

```text recording=handlers
MIDDLEWARE = [A, CommonMiddleware, BrokenLinkEmailsMiddleware, C]
...
C.process_response(404)
BrokenLinkEmailsMiddleware.process_response(404)
a mail to manager@example.com: "[Django] Broken INTERNAL link on recording"
CommonMiddleware.process_response(404)
A.process_response(301)
...
```

With `BrokenLinkEmailsMiddleware` outside `CommonMiddleware`, handed the 301, it sends nothing.

> **History.** The report was once `CommonMiddleware`'s; Django 1.6 moved it into `BrokenLinkEmailsMiddleware` for what its release notes call intractable ordering problems with `LocaleMiddleware` (`docs/releases/1.6.txt`). As two classes they can stand apart, as documented: the report outside `LocaleMiddleware`, and `CommonMiddleware` inside it.

> **Changed in 6.1.** With `MAILERS` defined, `BrokenLinkEmailsMiddleware.send_mail` drops `fail_silently=True` and passes over only `MailerDoesNotExist`: a failing mailer's error leaves `process_response`, and the wrapper makes the 404 a 500 (`docs/releases/6.1.txt`, `django/middleware/common.py:BrokenLinkEmailsMiddleware.send_mail`).
