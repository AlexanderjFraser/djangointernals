---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The CSRF secret and its token

The **CSRF secret** is the random string `CsrfViewMiddleware` keeps for each browser, in the cookie `"csrftoken"` or in the session, and its token is a fresh mask followed by the secret enciphered with it, made by `get_token`. Where the secret is made, how it is masked, how `CsrfViewMiddleware.process_request` reads it and `CsrfViewMiddleware.process_response` sends it back, and what `rotate_token` and `CSRF_USE_SESSIONS` change.

The CSRF check compares what the browser holds, which another site's page can make it send but cannot read, with what the site's own page carries. Both come from one secret. Three constants fix their shape: `CSRF_SECRET_LENGTH`, 32; `CSRF_TOKEN_LENGTH`, twice that; and `CSRF_ALLOWED_CHARS`, the ASCII letters and digits, 62 characters in which both are written. A fourth, `CSRF_SESSION_KEY`, `"_csrftoken"`, is the key the secret is kept under in a session (`django/middleware/csrf.py:CSRF_ALLOWED_CHARS`).

During a request the secret lives in `HttpRequest.META` under the key `"CSRF_COOKIE"`, whichever store it came from, beside a flag, `"CSRF_COOKIE_NEEDS_UPDATE"`, that says it is to be sent back with the response. `get_token`, `rotate_token`, `process_request` and `process_response` read and set these two keys; the CSRF check does not, and reads the secret from its store again.

## A new secret

`_get_new_csrf_string` draws 32 characters of `CSRF_ALLOWED_CHARS` with `get_random_string`, which takes each from the `secrets` module ([Secret keys and `django.utils.crypto`](keys.md)). `_add_new_csrf_cookie` puts such a string in `"CSRF_COOKIE"` and sets the flag. It is called in three places: by `get_token` when the request has none, by `process_request` when the cookie is malformed, and by `rotate_token` (`django/middleware/csrf.py:_add_new_csrf_cookie`).

## `get_token` and the mask

`get_token` returns a token for the request's secret. If the request has a secret, it reuses it and sets the flag all the same, so that, a comment says, the cookie is sent again and its expiry renewed; if not, it makes one. Either way it masks the secret anew and returns the result (`django/middleware/csrf.py:get_token`).

So a call of `get_token` makes the response carry the secret. Its docstring names the side effect, the cookie and `"Cookie"` in `"Vary"`, and advises calling it lazily, as the CSRF context processor does: that processor is in every `RequestContext` and calls `get_token` only when a template uses `"csrf_token"` ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)). `{% csrf_token %}` writes the token into the hidden input `"csrfmiddlewaretoken"` ([The built-in tags](../templates/tags.md)).

`_mask_cipher_secret` draws a **mask**, a second random string of 32 from the same characters, and enciphers the secret position by position: the index in `CSRF_ALLOWED_CHARS` of the secret's character, plus the mask's, modulo 62, is the index of the cipher's. The token is the mask followed by the cipher. `_unmask_cipher_token` splits a token at 32 and subtracts the mask's index from the cipher's; a difference below zero is used as it is, which a comment there calls fine: a negative index counts from the end of the string, and so comes to the same as modulo 62 (`django/middleware/csrf.py:_mask_cipher_secret`, `django/middleware/csrf.py:_unmask_cipher_token`).

A run of the example, with the test client making the requests, shows one browser's secret and the tokens of two pages:

```text figure=secret-and-token
the secret, 32 characters, as the cookie "csrftoken" holds it
  jHEM6ZJGBXWNDhtKs8o0B3aPSl8RkMbM

get_token: a new mask of 32, then the secret enciphered with it, character by character
  index in CSRF_ALLOWED_CHARS:  secret + mask, modulo 62  ->  cipher
    j  9   +  1 53   =  62 % 62 =  0  ->  a
    H 33   +  N 39   =  72 % 62 = 10  ->  k
    E 30   +  m 12   =  42             ->  Q
    ... and so for all 32

the token, 64 characters, which the page carries: the mask, then the cipher
  1NmcViBOKVbkf6i9stwgax435vdf56cH  akQOR7akbIXXIdBJKrK6Bq4INGbWfIdj

a second page, the same secret: another mask, another token
  3z0Y2ZsH86iPp2DJjYfaZZbjG6c5dXJ4  c6uAYO1dzT4sS9WjBWt0qSbYohaMnzKG

on the way back, the cipher unmasked: cipher - mask
    a  0   -  1 53   = -53  ->  j
    k 10   -  N 39   = -29  ->  H
    Q 42   -  m 12   =  30  ->  E
  jHEM6ZJGBXWNDhtKs8o0B3aPSl8RkMbM, compared with the cookie's secret: equal
```

*One secret and two of its tokens. Each token is a fresh mask and the secret enciphered with it, and unmasking either gives back the secret that the cookie holds.*

> **Why.** Django's documentation gives the mask as protection against the BREACH attack: the field is scrambled differently in each response, and only the secret, not the token, is compared with the cookie's, so every token made from one secret is accepted (`docs/ref/csrf.txt`).

## Reading the secret: `process_request`

`CsrfViewMiddleware._get_secret` reads the secret from its store. From the cookie named by `CSRF_COOKIE_NAME` it gives `None` when there is none, and otherwise passes the value to `_check_token_format`, which raises `InvalidTokenFormat` for a length that is neither 32 nor 64 or a character outside `CSRF_ALLOWED_CHARS`. With `CSRF_USE_SESSIONS` it reads the request's session under `CSRF_SESSION_KEY`, without that check, and raises `ImproperlyConfigured` if the request has no session: the message says `SessionMiddleware` must come before `CsrfViewMiddleware` in `MIDDLEWARE`. A value of 64 characters is unmasked, since, a comment says, Django before 4.0 masked the secret before storing it (`django/middleware/csrf.py:CsrfViewMiddleware._get_secret`).

`CsrfViewMiddleware.process_request` calls it on the way in. A secret it finds goes into `"CSRF_COOKIE"` with the flag left alone, so the browser's cookie is not sent again unless something asks for a token. A malformed one is replaced with a new secret, flagged, and so the response carries a good cookie whatever the view does. In a run, a post carrying the cookie `"short"` was still refused, since the check reads the cookie again ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)), but its 403 set a new cookie, and the next page's token was accepted. A masked secret from before 4.0 is replaced only when the cookie is being sent anyway, as the comment there says: a post with such a cookie was accepted and set none, and the next page of the form set the 32 characters (`django/middleware/csrf.py:CsrfViewMiddleware.process_request`).

## Sending it back: `process_response`

`CsrfViewMiddleware.process_response` does nothing unless the flag is set. Then it calls `_set_csrf_cookie` and clears the flag. The comment gives the reason: other instances of `CsrfViewMiddleware`, as when a decorator and the middleware are both used, would otherwise set the cookie again; a `rotate_token` called after it, in another middleware's `process_response`, sets the flag again, and a later instance still honours it (`django/middleware/csrf.py:CsrfViewMiddleware.process_response`).

`CsrfViewMiddleware._set_csrf_cookie` sets the cookie with the secret and these settings, then adds `"Cookie"` to `"Vary"`, since, its comment says, the content varies with the cookie (`django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`):

| setting | default | attribute |
|---|---|---|
| `CSRF_COOKIE_NAME` | `"csrftoken"` | the cookie's name |
| `CSRF_COOKIE_AGE` | 52 weeks, in seconds | Max-Age, and Expires from it |
| `CSRF_COOKIE_DOMAIN` | `None`: the host that set it | Domain |
| `CSRF_COOKIE_PATH` | `"/"` | Path |
| `CSRF_COOKIE_SECURE` | `False` | Secure |
| `CSRF_COOKIE_HTTPONLY` | `False` | HttpOnly |
| `CSRF_COOKIE_SAMESITE` | `"Lax"` | SameSite |

*The settings of the CSRF cookie, with their defaults from `django/conf/global_settings.py`.*

With `CSRF_USE_SESSIONS` it sets no cookie and leaves `"Vary"` to `SessionMiddleware`, which adds `"Cookie"` when the session was read; it stores the secret in the session under `CSRF_SESSION_KEY` only when the session holds a different value, so a page that reuses the secret leaves the session unmodified. In a run of the example with `CSRF_USE_SESSIONS` true and the sessions kept in signed cookies, the first page set only the session's cookie, and later pages, whose tokens came from the same secret, set none.

## `CSRF_USE_SESSIONS`

`CSRF_USE_SESSIONS`, false by default, moves the secret from its own cookie into the session: `_get_secret` reads it there, `_set_csrf_cookie` writes it there, and `SessionMiddleware` must stand before `CsrfViewMiddleware`. The secret is then part of the session's data, not a cookie of its own. Django's documentation calls the cookie safe and the session common practice in other frameworks, and so sometimes demanded by auditors (`docs/ref/settings.txt`); keeping it out of the session by default lets a site protect the forms of visitors who have no session (`docs/ref/csrf.txt`).

## The token from a script: X-CSRFToken

A script that posts can send the token in the header X-CSRFToken in place of the form field, which the check reads from `HttpRequest.META` under `CSRF_HEADER_NAME`, `"HTTP_X_CSRFTOKEN"` by default. It can take the value from the cookie, which holds the secret itself, or from a page's hidden input, which holds a token: `_check_token_format` admits both lengths, and in a run a post with either was accepted. The documentation calls the cookie the recommended source, and in a note recommends a masked token, against BREACH (`docs/howto/csrf.txt`).

A script can read the cookie because `CSRF_COOKIE_HTTPONLY` is false by default. The documentation says HttpOnly would give no practical protection: a script that can read the cookie already runs on the site's own domain (`docs/ref/settings.txt`). With it true, or with `CSRF_USE_SESSIONS`, the token must come from the page. A page that never asks for a token may set no cookie; `ensure_csrf_cookie` calls `get_token` for its view so that it does, and `requires_csrf_token` makes a token available to a view's template without refusing anything ([A middleware as a decorator](../views/middleware-decorators.md)).

## `rotate_token`

`rotate_token` replaces the request's secret with a new one, flagged, so the response carries it and every token made from the old secret stops matching (`django/middleware/csrf.py:rotate_token`). `login` and `alogin` in `django.contrib.auth` call it once the user is in the session ([Authentication, sessions and messages](../auth.md)) (`django/contrib/auth/__init__.py:login`). The documentation names the consequence: a form rendered before the login carries a token of the old secret and is refused, as after the back button or a login in another tab (`docs/ref/csrf.txt`).
