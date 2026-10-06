---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Cookies

How cookies cross a request and a response: `parse_cookie` reads the `"Cookie"` header into `COOKIES`, `set_cookie` and `delete_cookie` fill the response's `SimpleCookie`, each entry leaves as a `Set-Cookie` header of its own, and `set_signed_cookie` and `get_signed_cookie` add a signature a client cannot forge.

A cookie travels in two forms. A server sets one with a name, a value and a handful of attributes that tell the browser how long to keep it and when to send it back, and each cookie needs a header to itself. A browser returns only names and values, with the attributes gone, in one `"Cookie"` header, or under HTTP/2 possibly in several, which an `ASGIRequest` joins into one (`django/core/handlers/asgi.py:ASGIRequest.__init__`). Django keeps the two forms in two unrelated structures: a request has a plain dictionary of strings, and a response has a collection of entries that each carry their attributes.

## Coming in: `parse_cookie`

`COOKIES` is parsed the first time it is read, by `parse_cookie`, from the one `"Cookie"` header in `META`. The function is short and forgiving. It splits the header at semicolons, splits each piece at its first equals sign, strips the spaces, and undoes the quoting a server may have applied to the value. It does not validate names or reject anything, and where a name appears twice the later value replaces the earlier (`django/http/cookie.py:parse_cookie`, `django/core/handlers/wsgi.py:WSGIRequest.COOKIES`).

```text recording=http
parse_cookie, given the header  theme=dark; basket=3; flag; note="a b\073 c"  ->  {'theme': 'dark', 'basket': '3', '': 'flag', 'note': 'a b; c'}
```

A piece with no equals sign is taken as a value with an empty name, which is how browsers treat one; the comment in the function cites the Mozilla bug report on the question. The last cookie above shows the unquoting. The backslash and three digits are in the header itself: that is how Python's cookie class writes a semicolon inside a value, in quotes and as an octal escape, and `parse_cookie` turns it back.

## Going out: `set_cookie`

A response's cookies are in `HttpResponseBase.cookies`, an instance of Python's own `http.cookies.SimpleCookie`, which Django uses as it stands. `HttpResponseBase.set_cookie` adds an entry to it and sets the entry's attributes from its arguments (`django/http/response.py:HttpResponseBase.set_cookie`).

```text recording=http
response.set_cookie("theme", "dark")
  Set-Cookie: theme=dark; Path=/
response.set_cookie("basket", "3", max_age=3600, secure=True, httponly=True, samesite="Lax")
  Set-Cookie: basket=3; expires=Mon, 21 Sep 2026 15:13:20 GMT; HttpOnly; Max-Age=3600; Path=/; SameSite=Lax; Secure
response.set_cookie("note", "a b; c")
  Set-Cookie: note="a b\073 c"; Path=/
response.delete_cookie("basket")
  Set-Cookie: basket=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/
response.delete_cookie("__Host-basket")
  Set-Cookie: __Host-basket=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; Secure
```

A cookie set with nothing but a name and a value has one attribute, a path of `"/"`, and lasts until the browser closes. A lifetime can be given as a `datetime`, as a number of seconds or a `datetime.timedelta`, or as a string. An expiry given as a `datetime` is converted to a number of seconds from now. A number of seconds, however it arrived, is written as `Max-Age`, and an `"expires"` date is computed from the clock to go with it, for the sake of clients that read only the older attribute, unless a string expiry was given as well, which is kept. An expiry given as a string is written as it stands. Giving both a `datetime` and an age raises `ValueError`. The SameSite value is the only attribute Django itself checks: it must be `"lax"`, `"strict"` or `"none"`, in any case of letters. A name that cannot be a cookie's name is refused by `SimpleCookie`, with its own `http.cookies.CookieError`.

There is no operation in HTTP that deletes a cookie. `HttpResponseBase.delete_cookie` sets the cookie again with an empty value, an age of zero and an expiry date in 1970, and the browser discards it. It adds the `"Secure"` attribute by itself when the cookie's name begins with `"__Secure-"` or `"__Host-"`, or the caller passes a SameSite value of `"none"`, because a browser ignores a `Set-Cookie` for such a cookie without it, and the deletion would silently not happen (`django/http/response.py:HttpResponseBase.delete_cookie`).

The collection is a dictionary by name, so setting a cookie twice on one response leaves one entry. It has the second value. Its expiry date and its path are set afresh by every call, and the other attributes stay as the first call left them unless the second sets them.

Cookies stay out of the response's headers until the response is handed over. `WSGIHandler.__call__` builds the list of headers for the server from the response's own and then adds one `Set-Cookie` for each entry, and `ASGIHandler.send_response` does the same for its first message ([The response object](response.md#headers-responseheaders) says why they cannot be an ordinary header). A middleware that looks through `HttpResponseBase.headers` for cookies will find none; it has to look in `HttpResponseBase.cookies` (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.send_response`).

## Signed cookies

A cookie's value is whatever the client sends back, which need not be what the server set. A **signed cookie** carries proof that the value is the server's: `HttpResponseBase.set_signed_cookie` appends a timestamp and a signature to the value before setting it, and `HttpRequest.get_signed_cookie` checks the signature before returning it (`django/http/response.py:HttpResponseBase.set_signed_cookie`, `django/http/request.py:HttpRequest.get_signed_cookie`).

```text recording=http
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
```

The value is still there to be read, in front of the last two colons. Signing does not hide anything: it makes a change detectable. The part after the value is the time of signing, and the last is an HMAC over the two before it, made by the class `settings.SIGNING_BACKEND` names, `TimestampSigner` unless a project changes it, with a key derived from `settings.SECRET_KEY` ([Security](../security.md) has the signer itself) (`django/core/signing.py:get_cookie_signer`).

The signature covers more than the value. The signer is made with a **salt**, a string mixed into the key, and the salt for a cookie is a fixed prefix, the length of the salt the caller passed, that salt, and the cookie's name, in that order. The recording shows one, for a salt of four letters. That is why the same signed value is refused under another cookie's name, and refused when read without the salt it was written with: a value signed for one purpose cannot be replayed for another (`django/core/signing.py:_cookie_signer_salt`).

A cookie that is absent raises `KeyError` from `get_signed_cookie`; a value that does not verify raises `BadSignature`; and one signed longer ago than the maximum age the reader passes raises `SignatureExpired`, a subclass of it. Passing a default returns that instead in every one of these cases. The timestamp is always written and only checked when the reader asks: the last line of the recording reads a two-hour-old cookie without complaint, because no age was given.

> **Changed in 6.0.6, 5.2.15 and 6.1.** The salt used to be the cookie's name followed by the caller's salt, with nothing between, so that two different pairs could produce the same string and a value signed for one cookie could verify for another. The security releases 6.0.6 and 5.2.15 introduced the present form, while still accepting cookies signed the old way. Since 6.1 those are refused unless `settings.SIGNED_COOKIE_LEGACY_SALT_FALLBACK` is true, in which case a value that fails the new check, for a reason other than age, is tried against the old one. The setting is transitional: it is false by default, and setting it at all warns with `RemovedInDjango2028Warning` (`django/core/signing.py:_unsign_cookie`).

## Who sets cookies

The cookies a Django site sets are mostly set by middleware on the way out: the session's by `SessionMiddleware`, the CSRF token's by `CsrfViewMiddleware`, and those of the messages framework by its storage. The first two call `set_cookie` with attributes taken from settings of their own, and the messages cookie borrows the session cookie's domain and its Secure, HttpOnly and SameSite settings ([Authentication, sessions and messages](../auth.md), [Security](../security.md)) (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`, `django/middleware/csrf.py:CsrfViewMiddleware._set_csrf_cookie`, `django/contrib/messages/storage/cookie.py:CookieStorage._update_cookie`).
