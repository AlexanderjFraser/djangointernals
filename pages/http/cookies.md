---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Cookies

Cookies come in on a request and go out on a response: `parse_cookie` reads the `"Cookie"` header into `COOKIES`, `set_cookie` and `delete_cookie` fill the response's `SimpleCookie`, each entry of which leaves as a Set-Cookie header of its own, and `set_signed_cookie` and `get_signed_cookie` sign a value and check the signature.

A cookie travels in two forms. A server sets one with a name, a value and a handful of attributes, most telling the browser how long to keep it and when to send it back, and each cookie needs a header to itself. A browser returns only names and values, with the attributes gone, in one `"Cookie"` header, or under HTTP/2 possibly in several, which an `ASGIRequest` joins into one (`django/core/handlers/asgi.py:ASGIRequest.__init__`). Django keeps the two forms in two unrelated structures: a request has a plain dictionary of strings, and a response has a collection of entries that each carry their attributes.

The figure follows two cookies out and back, and what to see in it is what does not return: the attributes.

```text figure=round-trip
Django, on the server                               the headers                                       the browser

going out
HttpResponseBase.cookies, a SimpleCookie            the handler writes one Set-Cookie line for
                                                    each entry, as it hands the response over
  theme    dark                                ->   Set-Cookie: theme=dark;                      ->   keeps each cookie with its
           path /                                     Path=/                                          attributes, most saying how long
  basket   3                                   ->   Set-Cookie: basket=3;                        ->   to keep it and when to send
           expires Mon, 21 Sep 2026 15:13:20 GMT      expires=Mon, 21 Sep 2026 15:13:20 GMT;          it back
           httponly, max-age 3600, path /             HttpOnly; Max-Age=3600; Path=/

coming back
COOKIES, a dictionary of strings                    kept in META, and read by parse_cookie            sends names and values only,
                                                    the first time COOKIES is read                    in one header: the attributes
  {'theme': 'dark', 'basket': '3'}             <-   Cookie: theme=dark; basket=3                 <-   stay behind
```

*Django's side is on the left, the browser's on the right, and the headers that cross between them are in the middle; the upper row goes out and the lower comes back. The accent marks the attributes, which leave with each cookie and do not return.*

## Coming in: `parse_cookie`

`COOKIES` is parsed the first time it is read, by `parse_cookie`, from the one `"Cookie"` header in `META`. The function is short and forgiving. It splits the header at semicolons, splits each piece at its first equals sign, strips the spaces, and undoes the quoting a server may have applied to the value. It does not validate names or reject anything, and where a name appears twice the later value replaces the earlier (`django/http/cookie.py:parse_cookie`, `django/core/handlers/wsgi.py:WSGIRequest.COOKIES`).

In the header given to `parse_cookie` below, the third piece has no equals sign, and the last has its value in quotes, with a backslash and three digits in it: the backslash and the digits are in the header itself, and they are how Python's cookie class writes a semicolon inside a value, as an octal escape.

```text recording=http
...
parse_cookie, given the header  theme=dark; basket=3; flag; note="a b\073 c"  ->  {'theme': 'dark', 'basket': '3', '': 'flag', 'note': 'a b; c'}
```

A piece with no equals sign is taken as a value with an empty name, which is how browsers treat one: the function cites Mozilla's bug report on the question (`django/http/cookie.py:parse_cookie`).

## Going out: `set_cookie` and `delete_cookie`

A response's cookies are in `HttpResponseBase.cookies`, an instance of Python's own `http.cookies.SimpleCookie`, which Django uses as it stands. `HttpResponseBase.set_cookie` adds an entry to it and sets the entry's attributes from its arguments (`django/http/response.py:HttpResponseBase.set_cookie`).

Each call below is made on a new response and followed by its Set-Cookie line. The first gives a name and a value only, and its line has the one attribute a cookie gets without asking, a path of `"/"`; the second gives an age, and its line has an `"expires"` date beside its Max-Age; the third has a semicolon in its value, and its line has the value quoted, the form `parse_cookie` undoes.

```text recording=http
response.set_cookie("theme", "dark")
  Set-Cookie: theme=dark; Path=/
response.set_cookie("basket", "3", max_age=3600, secure=True, httponly=True, samesite="Lax")
  Set-Cookie: basket=3; expires=Mon, 21 Sep 2026 15:13:20 GMT; HttpOnly; Max-Age=3600; Path=/; SameSite=Lax; Secure
response.set_cookie("note", "a b; c")
  Set-Cookie: note="a b\073 c"; Path=/
  ...
```

A cookie's lifetime is given to `set_cookie` by two arguments: expires, a `datetime` or a string, and max_age, a number of seconds or a `datetime.timedelta`. A cookie given neither lasts until the browser closes.

| the arguments | written as Max-Age | written as `"expires"` |
|---|---|---|
| expires a `datetime`, no max_age | the seconds from now until that time, or 0 if it has passed | now plus that age, as a date |
| expires a `datetime`, and a max_age | nothing: `ValueError` is raised before either is written | nothing |
| expires a string, no max_age | nothing | the string, as it stands |
| expires a string, and a max_age | max_age | the string, as it stands |
| a max_age, no expires | max_age | now plus max_age, as a date |
| neither | nothing | an empty value, which the Set-Cookie line leaves out |

*What `HttpResponseBase.set_cookie` writes for a cookie's lifetime, by its arguments expires and max_age; a max_age is written in whole seconds.*

> **Why.** The date computed from a Max-Age is for Internet Explorer, which requires `"expires"` (`django/http/response.py:HttpResponseBase.set_cookie`).

SameSite is the only attribute whose value Django itself checks: it must be `"lax"`, `"strict"` or `"none"`, in any case of letters. A name that cannot be a cookie's name is refused by `SimpleCookie`, with its own `http.cookies.CookieError`.

There is no operation in HTTP that deletes a cookie. `HttpResponseBase.delete_cookie` sets the cookie again with an empty value, an age of zero and an expiry date in 1970, and the browser discards it if the path and domain match. Of the two deletions below, the second is of a cookie whose name begins with `"__Host-"`, and its line ends in Secure, which the call did not ask for.

```text recording=http
...
response.delete_cookie("basket")
  Set-Cookie: basket=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/
response.delete_cookie("__Host-basket")
  Set-Cookie: __Host-basket=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; Secure
  ...
```

`delete_cookie` adds the `"Secure"` attribute by itself when the cookie's name begins with `"__Secure-"` or `"__Host-"`, or the caller passes a SameSite value of `"none"`, because a browser can ignore a Set-Cookie for such a cookie without it, and the deletion would silently not happen (`django/http/response.py:HttpResponseBase.delete_cookie`).

> **Trap.** A cookie set twice on one response is not replaced. The collection is a dictionary by name, and the second call changes the entry the first one made, giving it the second value. `set_cookie` writes an attribute only when asked for it, with two exceptions: the expiry date, which every call writes, empty when the call gives neither an expiry nor an age, and the path, which every call writes unless it passes `None` for it. Every other attribute stays unless the second call asks for it. A cookie set with an age of 3,600 seconds and `"HttpOnly"`, then set again with a value alone, goes out with the new value, the age and `"HttpOnly"`, and no `"expires"` date: an age with no date to go with it (`django/http/response.py:HttpResponseBase.set_cookie`).

Cookies stay out of the response's headers until the response is handed over. `WSGIHandler.__call__` builds the list of headers for the server from the response's own and then adds one Set-Cookie for each entry, and `ASGIHandler.send_response` does the same for its first message ([The response object](response.md#headers-responseheaders) says why they cannot be an ordinary header). A middleware that looks through `HttpResponseBase.headers` for cookies will find none; it has to look in `HttpResponseBase.cookies` (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.send_response`).

## Signed cookies

A cookie's value is whatever the client sends back, which need not be what the server set. A **signed cookie** carries proof that the value is the server's: `HttpResponseBase.set_signed_cookie` appends a timestamp and a signature to the value before setting it, and `HttpRequest.get_signed_cookie` checks the signature before returning it (`django/http/response.py:HttpResponseBase.set_signed_cookie`, `django/http/request.py:HttpRequest.get_signed_cookie`). The value is still there to be read in the Set-Cookie line below, in front of the last two colons.

```text recording=http
...
response.set_signed_cookie("basket", "3", salt="shop")
  Set-Cookie: basket=3:1x8elk:0hOG8UOeJ1By0rV18GiJFR5pNhH-FusCci9t0OxtUic; Path=/
the signer's salt for it: 'django.http.cookies.v2:4:shopbasket'
and when a request brings the cookie back:
  request.get_signed_cookie("basket", salt="shop")  ->  '3'
  request.get_signed_cookie("basket")  (no salt)  ->  raises BadSignature
  the same value sent back under the name "total"  ->  raises BadSignature
  the value changed from 3 to 9  ->  raises BadSignature
  the value changed, and default=None  ->  None
  request.get_signed_cookie("absent"), of a request with no such cookie  ->  raises KeyError: 'absent'
  two hours later, with max_age=3600  ->  raises SignatureExpired
  two hours later, with no max_age  ->  '3'
  ...
```

Signing does not hide anything: it makes a change detectable. The part after the value is the time of signing, and the last is an HMAC over the two before it, made by the class `settings.SIGNING_BACKEND` names, `TimestampSigner` unless a project changes it, with a key derived from `settings.SECRET_KEY` ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](../security/signing.md) has the signer itself) (`django/core/signing.py:get_cookie_signer`).

The signature covers more than the value. The signer is made with a **salt**, a string mixed into the key, and the salt for a cookie is a fixed prefix, the length of the salt the caller passed, that salt, and the cookie's name, in that order. That is why the same signed value is refused under another cookie's name, and refused when read without the salt it was written with: a value signed for one purpose cannot be replayed for another (`django/core/signing.py:_cookie_signer_salt`).

A default passed to `get_signed_cookie` is returned in place of each of the three exceptions: the method catches the `KeyError` of a missing cookie and any `BadSignature`, of which `SignatureExpired` is a subclass (`django/http/request.py:HttpRequest.get_signed_cookie`). `TimestampSigner` writes the timestamp on every value, and checks it only when the reader passes a maximum age (`django/core/signing.py:TimestampSigner.sign`, `django/core/signing.py:TimestampSigner.unsign`).

> **Changed in 6.0.6, 5.2.15 and 6.1.** The salt used to be the cookie's name followed by the caller's salt, with nothing between, so that two different pairs could produce the same string and a value signed for one cookie could verify for another. The security releases 6.0.6 and 5.2.15 introduced the present form, while still accepting cookies signed the old way. Since 6.1 those are refused unless `settings.SIGNED_COOKIE_LEGACY_SALT_FALLBACK` is true, in which case a value that fails the new check, for a reason other than age, is tried against the old one. The setting is transitional: it is false by default, and setting it at all warns with `RemovedInDjango2028Warning` (`django/core/signing.py:_unsign_cookie`, `django/conf/__init__.py:Settings.__init__`).

## The cookies Django sets

The cookies a Django site sets are mostly set by middleware on the way out: the session's by `SessionMiddleware`, the CSRF secret's by `CsrfViewMiddleware`, and the messages framework's by its storage. The first two call `set_cookie` with most attributes taken from settings of their own, and the messages cookie borrows the session cookie's domain and its Secure, HttpOnly and SameSite settings ([`SessionMiddleware`: the cookie and the save](../auth/session-middleware.md), [Message storage: `CookieStorage`, `SessionStorage` and `FallbackStorage`](../auth/message-storage.md), [The CSRF secret and its token](../security/csrf-token.md)) (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`, `django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`, `django/contrib/messages/storage/cookie.py:CookieStorage._update_cookie`).
