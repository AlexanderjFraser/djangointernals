---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The CSRF secret and its token

`CsrfViewMiddleware` gives a browser a random **CSRF secret** to keep, in a cookie or in the session, and the site's own pages carry a **CSRF token** made from it: a fresh mask, a random string drawn for each token, and the secret enciphered with it. Another site's page can make the browser send its cookies but cannot read them, nor the site's pages, so it cannot post a token that matches. `get_token` makes a token, `rotate_token` replaces the secret when a user logs in, and `CSRF_USE_SESSIONS` keeps the secret in the session.

Three constants fix the shape of the secret and the token: `CSRF_SECRET_LENGTH`, 32; `CSRF_TOKEN_LENGTH`, twice that; and `CSRF_ALLOWED_CHARS`, the 62 ASCII letters and digits in which both are written, the lower-case letters first, then the upper-case, then the digits (`django/middleware/csrf.py:CSRF_ALLOWED_CHARS`).

During a request the secret lives in `HttpRequest.META` under the key `"CSRF_COOKIE"`, whichever store it came from, beside a flag, `"CSRF_COOKIE_NEEDS_UPDATE"`, that says it is to be sent back with the response. `get_token`, `rotate_token`, `CsrfViewMiddleware.process_request` and `CsrfViewMiddleware.process_response` read and set these two keys. The CSRF check does not: it reads the secret from its store again, since by then the copy may have been replaced ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`).

## A new secret

`_get_new_csrf_string` draws 32 characters of `CSRF_ALLOWED_CHARS` with `get_random_string`, which takes each from the `secrets` module ([Secret keys and `django.utils.crypto`](keys.md)) (`django/middleware/csrf.py:_get_new_csrf_string`). `_add_new_csrf_cookie` puts such a string in `"CSRF_COOKIE"` and sets the flag. It is called by `get_token` when the request has none, by `CsrfViewMiddleware.process_request` when the cookie is malformed, and by `rotate_token` (`django/middleware/csrf.py:_add_new_csrf_cookie`).

## `get_token` and the mask

`get_token` returns a token for the request's secret. If the request has a secret, it reuses it and sets the flag all the same, so that the cookie is sent again and its expiry renewed; if not, it makes one. Either way it masks the secret anew and returns the result (`django/middleware/csrf.py:get_token`).

So a call of `get_token` makes the response carry the secret. The CSRF context processor, which every `RequestContext` runs, defers the call: it puts in the context an object that calls `get_token` only when a template reads `"csrf_token"`, so a page whose template reads no token gets no secret and no cookie from it ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)) (`django/template/context_processors.py:csrf`). For a browser that has none, the secret is made as the template renders, when `{% csrf_token %}` reads the token to write it into the hidden input `"csrfmiddlewaretoken"`, not on the way in ([The built-in tags](../templates/tags.md)) (`django/template/defaulttags.py:CsrfTokenNode.render`).

`_mask_cipher_secret` draws a **mask**, a second random string of 32 from the same characters, and enciphers the secret position by position: the index in `CSRF_ALLOWED_CHARS` of the secret's character, plus the mask's, modulo 62, is the index of the cipher's. The token is the mask followed by the cipher. `_unmask_cipher_token` splits a token at 32 and subtracts the mask's index from the cipher's; a difference below zero is used as it is, since a negative index counts from the end of the string and so comes to the same as modulo 62 (`django/middleware/csrf.py:_mask_cipher_secret`, `django/middleware/csrf.py:_unmask_cipher_token`).

The figure follows one browser's secret over two requests for the harbour's form, a day apart. Each page's token starts with a mask of its own while the secret under it stays the same, and either token, unmasked, gives back the secret that the cookie holds.

```text figure=secret-and-token
the secret, 32 characters, as the cookie "csrftoken" holds it
  Wa5HXK02yi3hnlnmwAsz2KkEba0UQOLl

get_token: a new mask of 32, then the secret enciphered with it, character by character
  index in CSRF_ALLOWED_CHARS:  secret + mask, modulo 62  ->  cipher
    W 48   +  Z 51   =  99 % 62 = 37  ->  L
    a  0   +  X 49   =  49             ->  X
    5 57   +  F 31   =  88 % 62 = 26  ->  A
    ... and so for all 32

the first page's token, 64 characters: the mask, then the cipher
  ZXFPaDbxyWpP0nBMEUVVsqFISmqZ3uLe  LXAmXd1pW4iWdyOY0kdkk0PcTmgJJ8mp

the second page's, a day later, from the same secret: another mask, another cipher
  W62ZAgGzrFZWbZD7VNRgdDEMVXuDyLTd  I6XwnQwrPNS3oaQjhd9F5dOgWXknepuo

on the way back, the first token's cipher unmasked: cipher - mask
    L 37   -  Z 51   = -14  ->  W
    X 49   -  X 49   =   0  ->  a
    A 26   -  F 31   =  -5  ->  5
  either token unmasked: Wa5HXK02yi3hnlnmwAsz2KkEba0UQOLl, the cookie's secret
```

*One secret and two of its tokens. Each token is a fresh mask and the secret enciphered with it, and unmasking either gives back the secret that the cookie holds.*

The second page's response sends the cookie again, the same secret with an expiry a day later than the first's, since `get_token` found the secret and set the flag all the same (`django/middleware/csrf.py:get_token`).

> **Why.** The mask is a defence against BREACH, an attack that recovers, from their sizes, a secret that a site's compressed HTTPS responses repeat unchanged. A token scrambled differently in every response gives it nothing to recover, and since only the secret, not the token, is compared with the cookie's, every token made from one secret is accepted (`docs/ref/csrf.txt`, `docs/ref/middleware.txt`).

## Reading the secret: `process_request`

`CsrfViewMiddleware._get_secret` reads the secret from its store, the cookie or, under [`CSRF_USE_SESSIONS`](#csrf_use_sessions), the session. From the cookie named by `CSRF_COOKIE_NAME` it gives `None` when there is none, and otherwise passes the value to `_check_token_format`, which raises `InvalidTokenFormat` for a length that is neither 32 nor 64 or a character outside `CSRF_ALLOWED_CHARS`. It unmasks a value of 64 characters, a secret masked as an older Django kept it, before returning it (`django/middleware/csrf.py:CsrfViewMiddleware._get_secret`).

`CsrfViewMiddleware.process_request` calls it on the way in. A secret it finds goes into `"CSRF_COOKIE"` with the flag left alone, so the browser's cookie is not sent again unless something asks for a token. A malformed one is replaced with a new secret, flagged, so that the response carries a good cookie whatever becomes of the request (`django/middleware/csrf.py:CsrfViewMiddleware.process_request`). A post whose cookie holds the five characters `"short"` is still refused, with "CSRF cookie has incorrect length.", since the check reads the cookie again ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)). But its 403 sets the new cookie, so the form, loaded again, carries a token of the new secret, and its post is accepted. A post with no cookie at all is refused with "CSRF cookie not set.", and its 403 sets none: there was no secret to replace, and the failure view's built-in page asks for no token, so nothing sets the flag (`django/views/csrf.py:csrf_failure`).

> **History.** From 1.10 until 4.1, `CsrfViewMiddleware` kept the secret in its cookie masked, 64 characters long, as a page's token is. 4.1 stored the secret itself, with a transitional setting, CSRF_COOKIE_MASKED, that could keep the cookie masked while several instances of a project were being upgraded, and 5.0 removed the setting (`docs/releases/1.10.txt`, `docs/releases/4.1.txt`, `docs/releases/5.0.txt`). Such a cookie is still read, and unmasked, but the browser is given the 32 characters in its place only when a response sends the cookie anyway, as one that makes a token does (`django/middleware/csrf.py:CsrfViewMiddleware.process_request`).

## Sending it back: `process_response`

`CsrfViewMiddleware.process_response` does nothing unless the flag is set. Then it calls `CsrfViewMiddleware._set_csrf_cookie` and clears the flag (`django/middleware/csrf.py:CsrfViewMiddleware.process_response`).

Unless [`CSRF_USE_SESSIONS`](#csrf_use_sessions) puts the secret in the session, `_set_csrf_cookie` sets the cookie with the secret and these settings, then adds `"Cookie"` to `"Vary"`, since the content varies with the cookie (`django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`):

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

## When a decorator and the middleware share a request

`csrf_protect` runs an instance of `CsrfViewMiddleware` of its own around the view it decorates ([A middleware as a decorator](../views/middleware-decorators.md)) (`django/views/decorators/csrf.py:csrf_protect`). Where the chain installs the middleware as well, two instances see one request, and the decorator's, nearer the view, runs its `process_response` first; clearing the flag keeps the chain's from sending the cookie again. Look for the flag in the two calls of `process_response` as such a view, asking for a token, goes out through the harbour's chain: true for the decorator's, which sets the cookie, and false for the chain's, which leaves the response as it is.

```text recording=security
GET https://harbour.example/protected/, a view under csrf_protect, through the harbour's chain: two instances of CsrfViewMiddleware, and the cookie set once
...
    protected(request)
      get_token(request)  ->  the token 'QVOqkMoRJKtIQoaijivteMfNncSxd4DwWQCCn3vMlR5GqTG3ktsjHv2HwmGwzSCT'; request.META now holds CSRF_COOKIE 'g5Ymdrh5MhM8KFGVbl70DTX4jkY9wY9x', CSRF_COOKIE_NEEDS_UPDATE True
      -> an HttpResponse, status 200
    CsrfViewMiddleware.process_response(request, response), request.META holding CSRF_COOKIE 'g5Ymdrh5MhM8KFGVbl70DTX4jkY9wY9x', CSRF_COOKIE_NEEDS_UPDATE True  (the decorator's)
      CsrfViewMiddleware._set_csrf_cookie(request, response)  (the decorator's)
      -> the response, Vary added, the cookie csrftoken set
    CsrfViewMiddleware.process_response(request, response), request.META holding CSRF_COOKIE 'g5Ymdrh5MhM8KFGVbl70DTX4jkY9wY9x', CSRF_COOKIE_NEEDS_UPDATE False  (the chain's)  ->  the response, unchanged
    start_response("200 OK", headers)
      Set-Cookie: csrftoken=g5Ymdrh5MhM8KFGVbl70DTX4jkY9wY9x; expires=Mon, 11 Oct 2027 09:00:00 GMT; Max-Age=31449600; Path=/; SameSite=Lax
```

Each instance reads the flag afresh, so a secret replaced between the two, by a middleware whose `process_response` runs between them, still reaches the browser (`django/middleware/csrf.py:CsrfViewMiddleware.process_response`).

## `rotate_token`

`rotate_token` replaces the request's secret with a new one, flagged, so the response carries it and every token made from the old secret stops matching (`django/middleware/csrf.py:rotate_token`). `login` and `alogin` in `django.contrib.auth` call it once the user is in the session ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md)) (`django/contrib/auth/__init__.py:login`).

A form rendered before a login therefore carries a token of the old secret. The harbour's form, rendered before a login and posted after it, as when the user presses the back button and posts it again, is refused: its token unmasks to the secret that `rotate_token` replaced inside `login`, after the session's key was cycled.

```text recording=security
login rotates the CSRF secret, in an interpreter of its own, with django.contrib.auth, contenttypes and sessions installed, sessions in the database, and SessionMiddleware and AuthenticationMiddleware in the chain: a form rendered before the login is refused after it
    beforehand, unrecorded, GET https://harbour.example/berths/ gave the browser the cookie csrftoken=Vj1n59c23B3ktaWiWcXg9ik4i4WzMOhZ and a page whose form holds the token PDleWQaGozDCVKrotaHUu1XCmhueviREAMcrRPcyh0wMeKdwfcu0t97wubgD7WYt
...
    log_in(request)
      login(request, the User 'harbourmaster')
        SessionBase.cycle_key()
        rotate_token(request)
          _add_new_csrf_cookie(request)
            _get_new_csrf_string()  ->  'O5GCOpxuI0YRsKaAC8FUwKZVNE0DmYqf'
            -> 'O5GCOpxuI0YRsKaAC8FUwKZVNE0DmYqf'
          -> None; request.META now holds CSRF_COOKIE 'O5GCOpxuI0YRsKaAC8FUwKZVNE0DmYqf', CSRF_COOKIE_NEEDS_UPDATE True
      -> an HttpResponse, status 200
    CsrfViewMiddleware.process_response(request, response), request.META holding CSRF_COOKIE 'O5GCOpxuI0YRsKaAC8FUwKZVNE0DmYqf', CSRF_COOKIE_NEEDS_UPDATE True  ->  the response, Vary added, the cookie csrftoken set
...
    the browser goes back to the berths page it was given before the login, as after the back button, and posts its form
...
    CsrfViewMiddleware._check_token(request)
      CsrfViewMiddleware._get_secret(request)  ->  'O5GCOpxuI0YRsKaAC8FUwKZVNE0DmYqf'
      _does_token_match('PDleWQaGozDCVKrotaHUu1XCmhueviREAMcrRPcyh0wMeKdwfcu0t97wubgD7WYt', 'O5GCOpxuI0YRsKaAC8FUwKZVNE0DmYqf')
        _unmask_cipher_token('PDleWQaGozDCVKrotaHUu1XCmhueviREAMcrRPcyh0wMeKdwfcu0t97wubgD7WYt')  ->  'Vj1n59c23B3ktaWiWcXg9ik4i4WzMOhZ'
        constant_time_compare('Vj1n59c23B3ktaWiWcXg9ik4i4WzMOhZ', 'O5GCOpxuI0YRsKaAC8FUwKZVNE0DmYqf')  ->  False
        -> False
      CsrfViewMiddleware._bad_token_message('incorrect', 'POST')  ->  'CSRF token from POST incorrect.'
      ...
```

Such a page has to be loaded again to carry a token of the new secret, and a login in one tab leaves the forms already open in the others just as stale (`docs/ref/csrf.txt`).

## `CSRF_USE_SESSIONS`

`CSRF_USE_SESSIONS`, false by default, moves the secret from its own cookie into the session's data, under the key `CSRF_SESSION_KEY`, `"_csrftoken"`. `_get_secret` then reads the request's session, without the format check a cookie gets. `_set_csrf_cookie` sets no cookie: it stores the secret in the session only when the session holds a different value, and leaves `"Vary"` to `SessionMiddleware`, which adds `"Cookie"` whenever the session was read (`django/middleware/csrf.py:CsrfViewMiddleware._get_secret`, `django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`, `django/contrib/sessions/middleware.py:SessionMiddleware.process_response`).

> **Why.** The cookie is safe, and the default by design: a secret tied to no session lets a site protect the forms of anonymous visitors, who have none, as on a pastebin (`docs/ref/csrf.txt`). The setting is there because storing the secret in the session is common practice in other frameworks, and so sometimes demanded by security auditors (`docs/ref/settings.txt`).

The setting needs a session on every request that reaches `CsrfViewMiddleware`. Without one, with `settings.DEBUG` false and Django's own 500 view, no response is made: an `ImproperlyConfigured` leaves the handler for the server. `_get_secret` raises it, with a message saying that `SessionMiddleware` must come before `CsrfViewMiddleware` in `MIDDLEWARE`. The wrapper around the middleware's layer hands the error to `response_for_exception`, which calls the 500 view ([How an exception becomes a response](../handlers/exceptions.md)). That view, `server_error`, is under `requires_csrf_token`, a decorator that, like `csrf_protect`, runs an instance of the middleware around its view, so that the view's template can have a token, but refuses nothing (`django/views/decorators/csrf.py:_EnsureCsrfToken`). That instance reads the secret in its `process_request`, and raises the error again. In the harbour's chain the error comes round once more, at the wrapper of the next layer out, `SecurityMiddleware`'s, and from there it leaves the handler:

```text recording=security
CSRF_USE_SESSIONS = True without SessionMiddleware: GET https://harbour.example/berths/, with a handler built under that setting and the harbour's MIDDLEWARE
    GET https://harbour.example/berths/, the browser sending nothing but the request
    CsrfViewMiddleware.process_request(request)
      CsrfViewMiddleware._get_secret(request)  raises ImproperlyConfigured
    response_for_exception(request, ImproperlyConfigured)
      signal got_request_exception, for ImproperlyConfigured
      handle_uncaught_exception(request, resolver, exc_info)
        CsrfViewMiddleware.process_request(request)  (on an instance of _EnsureCsrfToken, the class of requires_csrf_token)
          CsrfViewMiddleware._get_secret(request)  (on an instance of _EnsureCsrfToken, the class of requires_csrf_token)  raises ImproperlyConfigured
    response_for_exception(request, ImproperlyConfigured)
      signal got_request_exception, for ImproperlyConfigured
      handle_uncaught_exception(request, resolver, exc_info)
        CsrfViewMiddleware.process_request(request)  (on an instance of _EnsureCsrfToken, the class of requires_csrf_token)
          CsrfViewMiddleware._get_secret(request)  (on an instance of _EnsureCsrfToken, the class of requires_csrf_token)  raises ImproperlyConfigured
    the handler raises ImproperlyConfigured to the server: CSRF_USE_SESSIONS is enabled, but request.session is not set. SessionMiddleware must appear before CsrfViewMiddleware in MIDDLEWARE.
```

Nothing is logged to `"django.request"`: its record would follow the 500 view's response, which is never made (`django/core/handlers/exception.py:response_for_exception`, `django/views/defaults.py:server_error`).

## The token from a script: X-CSRFToken

A script that posts can send the token in a header, X-CSRFToken by default, in place of the form field, and may send there a page's token or the cookie's value, the secret itself ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`).

A script can read the cookie because `CSRF_COOKIE_HTTPONLY` is false by default. HttpOnly would add no practical protection: a script that can read the cookie is already on the site's own domain as far as the browser knows, and can do anything it likes there (`docs/ref/settings.txt`). With `CSRF_COOKIE_HTTPONLY` true, or under `CSRF_USE_SESSIONS`, a script finds the token in the page instead, in the hidden input `"csrfmiddlewaretoken"` that `{% csrf_token %}` writes (`docs/howto/csrf.txt`). A page that never asks for a token may set no cookie; `ensure_csrf_cookie` calls `get_token` for its view so that it does ([A middleware as a decorator](../views/middleware-decorators.md)) (`django/views/decorators/csrf.py:_EnsureCsrfCookie`).
