---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`

`django.core.signing` makes a string that proves where it came from: `Signer` appends an HMAC of a value, `TimestampSigner` the time of signing as well, and `dumps` and `loads` sign and check any value JSON can hold. The value stays readable; what signing adds is that a changed value, or one made without the key, is refused when it comes back.

A site often hands a client something it wants back unchanged, such as a cookie or a link in an email, without keeping a copy to compare. So it appends a keyed hash that only a holder of the key can compute, and computes it again when the string returns. A signer writes the value as given, a separator, and the signature in URL-safe base64; `dumps` writes its value in URL-safe base64 as well, so that the whole is text a URL or a cookie can carry.

## `Signer`: the value, a separator, the signature

A `Signer` takes keyword arguments only (`django/core/signing.py:Signer.__init__`). Its key is the one given or else `SECRET_KEY`, its fallback keys the ones given or else `SECRET_KEY_FALLBACKS`; its separator is by default `":"`, its algorithm `"sha256"`. Given no salt, it makes one from its class's module and name: `"django.core.signing.Signer"`, and for `TimestampSigner`, `"django.core.signing.TimestampSigner"`.

`Signer.__init__` raises `ValueError` for a separator that is empty or made only of characters the expression `_SEP_UNSAFE` admits, among them letters, digits, `"-"`, `"_"` and `"="`, those of URL-safe base64 and its padding. The documentation states the rule as a separator outside the URL-safe base64 alphabet (`docs/topics/signing.txt`).

> **Trap.** The expression writes the letters as the range `A-z`, which in ASCII also holds the six characters between `"Z"` and `"a"`: a run refused `"^"` and `"["` too, and accepted `"/"` and `"."`.

`Signer.signature` calls `base64_hmac` with the signer's salt followed by `"signer"`, the value, the signer's key (or one passed to it) and the algorithm (`django/core/signing.py:Signer.signature`). `base64_hmac` takes the digest of `salted_hmac`, which hashes the salt and the key together into a key of their own and makes an HMAC of the value with it ([Secret keys and `django.utils.crypto`](keys.md)), and writes the digest in URL-safe base64. `Signer.sign` returns the value, the separator and the signature:

```python
# in a shell, with harbour's settings
>>> from django.core.signing import Signer, TimestampSigner
>>> Signer(salt="harbour.berths").sign("Endeavour")
'Endeavour:LPnFToX8POawEehjq3oPfj-e16IswWUxtoMceqq-F1o'
>>> TimestampSigner(salt="harbour.berths").sign("Endeavour")
'Endeavour:1xHQ1Q:ffXSfvIAfN2khcjQQwGYt7PBeCP08XPwY4saeDRKSNk'
```

`Signer.unsign` reverses it (`django/core/signing.py:Signer.unsign`). A string with no separator is refused with `BadSignature`. Otherwise it is split at the last separator, so the value may itself contain the separator. The signature is computed again for the value with the signer's key and then, until one matches, with each fallback key, each compared with the one sent by `constant_time_compare`. The first match returns the value; none raises `BadSignature`. The fallback keys only verify, since `sign` always uses the signer's own key: a site that changes `SECRET_KEY` and lists the old one in `SECRET_KEY_FALLBACKS` still accepts what it signed before.

## `TimestampSigner`: the time inside the signature

`TimestampSigner` is a `Signer` that writes the time of signing between the value and the signature. `TimestampSigner.timestamp` is the current time in whole seconds since the epoch, written in base 62, and `TimestampSigner.sign` appends the separator and the timestamp to the value before passing it to `Signer.sign`, so the signature covers the time as well (`django/core/signing.py:TimestampSigner.sign`). In the run, `"1xHQ1Q"` is the time.

`TimestampSigner.unsign` checks the signature first, by `Signer.unsign`, and only then reads the time. It splits off the timestamp and decodes it, and if given a maximum age, as seconds or a timedelta, raises `SignatureExpired` when more seconds than that have passed (`django/core/signing.py:TimestampSigner.unsign`). `SignatureExpired` is a subclass of `BadSignature`, so code that catches the one catches both. With no maximum age the time is not checked: it is always written, and checked only when asked. A run, the berth signed by `dumps` two hours before `loads` read it:

```text
# the berth signed by dumps, read by loads two hours later
max_age=3600                  SignatureExpired: Signature age 7200.919371843338 > 3600 seconds
max_age=timedelta(hours=1)    SignatureExpired: Signature age 7200.919414520264 > 3600.0 seconds
max_age=timedelta(hours=3)    {'berth': 4, 'ship': 'Endeavour'}
no max_age                    {'berth': 4, 'ship': 'Endeavour'}
berth 5, max_age=3600         BadSignature: Signature "D3IJ9Cn5PsiXuqkLAqCinYLL1lK-7s-w0Uaa6qm3mks" does not match
```

The last line is that string with its JSON changed to berth 5: old and forged, it was refused as forged.

## Objects: `Signer.sign_object` and `Signer.unsign_object`

`Signer.sign_object` signs a value of any type its serializer can write, not only a string (`django/core/signing.py:Signer.sign_object`). It serializes the value to bytes, with `JSONSerializer` unless given another serializer class. Asked to compress, it compresses the bytes with zlib and keeps the result only if it is shorter by more than one byte. It writes the bytes in URL-safe base64, puts a `"."` in front if they were compressed, and signs that with `sign`, which on a `TimestampSigner` adds the time. In a run, `compress=True` left the berth as it was, and shrank a dictionary holding a list of eight berths from 398 characters signed to 147, beginning `".eJy"`.

The `"."` is added before signing, so the signature covers it; the docstring gives the reason as protection against zip bombs. `Signer.unsign_object` calls `unsign` first, passing a maximum age on to a `TimestampSigner`, and only then looks for the `"."`, decodes the base64 and decompresses: nothing is decompressed that the key did not sign (`django/core/signing.py:Signer.unsign_object`).

`JSONSerializer` writes JSON with no spaces after `","` and `":"`, encoded as Latin-1, and reads it back the same way (`django/core/signing.py:JSONSerializer`). The documentation's reason for JSON: even if `SECRET_KEY` is stolen, an attacker cannot run commands through it as through the pickle format (`docs/topics/signing.txt`).

## `dumps` and `loads`

`dumps` makes a `TimestampSigner` from its key and salt and returns its `sign_object` of the value; `loads` makes one from its key, salt and fallback keys and returns its `unsign_object` of the string (`django/core/signing.py:dumps`, `django/core/signing.py:loads`). The defaults are no key, so `SECRET_KEY`; the salt `"django.core.signing"`; `JSONSerializer`; no compression; and no maximum age. The class is `TimestampSigner` whatever `SIGNING_BACKEND` names, and the algorithm is its default, `"sha256"`.

The docstring of `dumps` warns that leaving the salt at its default, or reusing one salt across different parts of an application without good cause, is a security risk. The documentation's reason: a salt is a namespace, and a string signed in one is refused by code that checks in another (`docs/topics/signing.txt`).

```text figure=a-signed-value
signing.dumps({"berth": 4, "ship": "Endeavour"}, salt="harbour.berths") returned

eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xHQ1Q:cw06NVDicoTdRLXU-PNAx10QwWOsa6ND2MLn9CkLFYA

eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9      the JSON in URL-safe base64:  {"berth":4,"ship":"Endeavour"}
:                                             the separator
1xHQ1Q                                        the time in base 62:  1792088264, 2026-10-15 18:17:44 UTC
:                                             the separator
cw06NVDicoTdRLXU-PNAx10QwWOsa6ND2MLn9CkLFYA   the signature, in URL-safe base64

the signature is an HMAC with SHA-256
  of        everything before the last ":":  eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xHQ1Q
  key       SHA-256 of "harbour.berths" + "signer" + SECRET_KEY
compressed  a "." in front of the base64, inside what is signed
```

*The string `dumps` returned for the berth, cut at its separators. The JSON and the time can be read by anyone who has the string; only the signature needs the key.*

## Base 64, base 62 and `base64_hmac`

`b64_encode` is URL-safe base64 with the trailing `"="` padding stripped, and `b64_decode` restores the padding before decoding (`django/core/signing.py:b64_decode`). `b62_encode` and `b62_decode` write and read an integer in the digits and letters of `BASE62_ALPHABET`, with a `"-"` in front of a negative one (`django/core/signing.py:b62_encode`).

> **Deprecated.** Called with no algorithm, `base64_hmac` warns with `RemovedInDjango2028Warning` and uses `"sha1"`; in Django 2028 its default becomes `"sha256"`, as does that of `salted_hmac` (`django/core/signing.py:base64_hmac`). A `Signer` always passes its own algorithm, so signing never meets the warning.

## Cookies: `get_cookie_signer` and `SIGNING_BACKEND`

`get_cookie_signer` makes the signer for cookies (`django/core/signing.py:get_cookie_signer`). Its class is the one `SIGNING_BACKEND` names, `TimestampSigner` by default; its key is `SECRET_KEY` with `"django.http.cookies"` in front, and its fallback keys likewise, so a cookie's signature differs from the one `dumps` makes with the same salt. Signed cookies use it with a salt that `_cookie_signer_salt` makes from the cookie's name and the caller's salt, and are read through `_unsign_cookie` ([Cookies](../http/cookies.md)).

## Who signs

`SessionBase.encode` makes a session's data a string with `dumps`, with `compress=True`, the salt `SessionBase.key_salt` (`"django.contrib.sessions."` followed by the store's class name) and the serializer `SESSION_SERIALIZER` names, by default the same JSON serializer; the database and file backends store that string. `SessionBase.decode` reads it with `loads` and no maximum age; on a `BadSignature` it logs the warning `"Session data corrupted"` to `"django.security.SuspiciousSession"`, and on any failure returns an empty session (`django/contrib/sessions/backends/base.py:SessionBase.encode`, `django/contrib/sessions/backends/base.py:SessionBase.decode`).

In the backend that keeps the whole session in the cookie, the session key is itself the string `dumps` makes of the session, compressed, with the salt `"django.contrib.sessions.backends.signed_cookies"` (`django/contrib/sessions/backends/signed_cookies.py:SessionStore`). `SessionStore.load` reads it with `loads`, the session cookie's age as the maximum, and starts an empty session on any failure.

The messages' `CookieStorage` signs through `get_cookie_signer` with the salt `"django.contrib.messages"`, using `sign_object` with compression and `unsign_object` with no maximum age (`django/contrib/messages/storage/cookie.py:CookieStorage.__init__`). All three are in [Authentication, sessions and messages](../auth.md).
