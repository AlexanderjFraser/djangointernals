---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`

Signing lets a site hand out a value, in a cookie or a link, and know when it comes back that nobody has changed it and that the site made it, without keeping a copy to compare. The site appends a signature, an HMAC: a hash of the value keyed with a secret, which only a holder of that key can compute. It computes the signature again when the value returns. In `django.core.signing`, `Signer` signs a string, `TimestampSigner` adds the time of signing, `dumps` and `loads` sign and read any value JSON can hold, and a value whose signature does not match is refused with `BadSignature`.

The value is not hidden, only signed. A signer writes it as given, then a separator and the signature in URL-safe base64; `dumps` writes its value in URL-safe base64 as well, so that the whole is text a URL or a cookie can carry.

The figure takes apart the string `dumps` made of the harbour's berth under the salt `"harbour.berths"`, a string that names the use. Since `dumps` signs with a `TimestampSigner`, the time of signing stands between the value and the signature. Both decode for anyone who has the string, and only the signature, which covers them, needs the key.

```text figure=a-signed-value
signing.dumps({"berth": 4, "ship": "Endeavour"}, salt="harbour.berths") returned

eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2:47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s

eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9      the JSON, in URL-safe base64
                                              {"berth":4,"ship":"Endeavour"}
:                                             the separator
1xGBt2                                        the time of signing, in base 62
                                              1791795600 seconds: 2026-10-12 09:00:00 UTC
:                                             the separator
47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s   the signature, in URL-safe base64

the signature is an HMAC with SHA-256
  of      everything before the last ":"   eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2
  key     from "harbour.berths" + "signer" and SECRET_KEY
compressed, the JSON would have a "." in front of its base64, inside what is signed
```

*The string cut at its separators, each part beside what it holds; below, what the signature is computed from, and where the mark of compression would stand.*

## `Signer`: the value, a separator, the signature

A `Signer` takes keyword arguments only (`django/core/signing.py:Signer.__init__`). Its key is the one given or else `SECRET_KEY`, its fallback keys the ones given or else `SECRET_KEY_FALLBACKS`; its separator is by default `":"`, its algorithm `"sha256"`. Given no salt, it makes one from its class's module and name: `"django.core.signing.Signer"`, and for `TimestampSigner`, `"django.core.signing.TimestampSigner"`.

`Signer.__init__` raises `ValueError` for a separator that is empty or made only of the characters of URL-safe base64 and its padding: letters, digits, `"-"`, `"_"` and `"="` (`django/core/signing.py:_SEP_UNSAFE`). The expression that tests it writes the letters as the range `A-z`, which in ASCII also holds `"["`, `"]"`, `"^"`, the backslash and the backtick, and these are refused too.

`Signer.sign` returns the value, the separator and the signature (`django/core/signing.py:Signer.sign`). `Signer.signature` passes the signer's salt followed by `"signer"`, the value, the signer's key (or one passed to it) and its algorithm to `base64_hmac`, which writes in URL-safe base64 the HMAC that `salted_hmac` makes of the value under a key derived from that salt and key ([Secret keys and `django.utils.crypto`](keys.md)) (`django/core/signing.py:Signer.signature`, `django/core/signing.py:base64_hmac`).

## `Signer.unsign`: the key, then the fallback keys

`Signer.unsign` reverses `Signer.sign` (`django/core/signing.py:Signer.unsign`). A string with no separator is refused with `BadSignature`. Otherwise it is split at the last separator, so the value may itself contain the separator. The signature is computed again for the value with the signer's key and then, until one matches, with each fallback key, each compared with the one sent by `constant_time_compare`. The first match returns the value; none raises `BadSignature`.

A signer made after `SECRET_KEY` changed, with the harbour's old key as its fallback, is given a value that key signed. The signature computed with the new key fails the comparison and the one computed with the fallback passes; when the same signer signs, it uses the new key alone:

```text recording=security
Signer.unsign with the old key in SECRET_KEY_FALLBACKS: the key, then the fallback key
    signed = Signer(salt="harbour.berths").sign("Endeavour")
...
    changed = override_settings(SECRET_KEY=NEW_KEY, SECRET_KEY_FALLBACKS=[HARBOUR_KEY]); changed.enable()
    rotated = Signer(salt="harbour.berths")
      Signer.__init__(salt='harbour.berths')  ->  its key the new key, its fallback keys the harbour's key, its salt 'harbour.berths'
    rotated.unsign(signed)
      Signer.unsign('Endeavour:LPnFToX8POawEehjq3oPfj-e16IswWUxtoMceqq-F1o')
        Signer.signature('Endeavour'), the key, the new key  ->  'RcArs-ivDzmXhdrLfINNYy-d1ShFxI8tbA-bZ0r_mNE'
        constant_time_compare('LPnFToX8POawEehjq3oPfj-e16IswWUxtoMceqq-F1o', 'RcArs-ivDzmXhdrLfINNYy-d1ShFxI8tbA-bZ0r_mNE')  ->  False
        Signer.signature('Endeavour'), the fallback key, the harbour's key  ->  'LPnFToX8POawEehjq3oPfj-e16IswWUxtoMceqq-F1o'
        constant_time_compare('LPnFToX8POawEehjq3oPfj-e16IswWUxtoMceqq-F1o', 'LPnFToX8POawEehjq3oPfj-e16IswWUxtoMceqq-F1o')  ->  True
        -> 'Endeavour'
    resigned = rotated.sign("Endeavour")
      Signer.sign('Endeavour')
        Signer.signature('Endeavour'), no key given, so the key, the new key  ->  'RcArs-ivDzmXhdrLfINNYy-d1ShFxI8tbA-bZ0r_mNE'
        -> 'Endeavour:RcArs-ivDzmXhdrLfINNYy-d1ShFxI8tbA-bZ0r_mNE'
        ...
```

The fallback keys only check, then, and never sign; how a site moves to a new key through them is told in [Secret keys and `django.utils.crypto`](keys.md). A signer given no keys reads both settings when it is made, not when it is used: one made before a change of `SECRET_KEY` goes on checking with the old key, and one made after the change refuses what the old key signed unless the old key is among its fallbacks (`django/core/signing.py:Signer.__init__`). `dumps`, `loads` and `get_cookie_signer` make a new signer at each call (`django/core/signing.py:dumps`, `django/core/signing.py:loads`, `django/core/signing.py:get_cookie_signer`).

## `TimestampSigner`: the time inside the signature

`TimestampSigner` is a `Signer` that writes the time of signing between the value and the signature. `TimestampSigner.timestamp` is the current time in whole seconds since the epoch, written in base 62 by `b62_encode`, with the digits and letters of `BASE62_ALPHABET` (`django/core/signing.py:TimestampSigner.timestamp`, `django/core/signing.py:b62_encode`). `TimestampSigner.sign` appends the separator and the timestamp to the value before passing it to `Signer.sign`, so the signature covers the time as well (`django/core/signing.py:TimestampSigner.sign`).

`TimestampSigner.unsign` checks the signature first, by `Signer.unsign`, and only then reads the time. It splits off the timestamp and decodes it with `b62_decode`, and if given a maximum age, as seconds or a timedelta, raises `SignatureExpired` when more seconds than that have passed (`django/core/signing.py:TimestampSigner.unsign`). With no maximum age the time is not checked. `SignatureExpired` is a subclass of `BadSignature`, so code that catches `BadSignature` catches both.

`loads` passes its maximum age on to `TimestampSigner.unsign`. Two hours after the berth was signed, a maximum age of an hour refuses it, given as seconds or as a timedelta, and one of three hours, or none, lets it through; each refusal's message gives the age and the limit as `unsign` compared them:

```text recording=security
loads two hours after dumps, the clock moved on by the script's hand: the maximum age
    s = signing.dumps({"berth": 4, "ship": "Endeavour"}, salt="harbour.berths")
    the clock moves on two hours, by the script's hand
    signing.loads(s, salt="harbour.berths", max_age=3600)
      TimestampSigner.unsign('eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2:47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s', max_age=3600)  raises SignatureExpired
      raises SignatureExpired: Signature age 7200.0 > 3600 seconds
    signing.loads(s, salt="harbour.berths", max_age=timedelta(hours=1))
      TimestampSigner.unsign('eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2:47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s', max_age=datetime.timedelta(seconds=3600))  raises SignatureExpired
      raises SignatureExpired: Signature age 7200.0 > 3600.0 seconds
    signing.loads(s, salt="harbour.berths", max_age=timedelta(hours=3))
      TimestampSigner.unsign('eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2:47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s', max_age=datetime.timedelta(seconds=10800))  ->  'eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9'
    signing.loads(s, salt="harbour.berths")
      TimestampSigner.unsign('eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2:47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s', max_age=None)  ->  'eyJiZXJ0aCI6NCwic2hpcCI6IkVuZGVhdm91ciJ9'
```

An age is counted from the whole second that `TimestampSigner.timestamp` wrote, so it runs ahead of the time since signing by the fraction of a second that `timestamp` dropped (`django/core/signing.py:TimestampSigner.timestamp`).

A value both changed and old is refused as changed, since `Signer.unsign` runs before the time is read. The berth's string with the JSON of berth 5 in place of its own, its time and signature kept, fails at the comparison, and the limit of an hour is never checked:

```text recording=security
loads of the berth with its JSON changed to berth 5, two hours on: refused as forged, not as old
...
    signing.loads(forged, salt="harbour.berths", max_age=3600)
      TimestampSigner.unsign('eyJiZXJ0aCI6NSwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2:47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s', max_age=3600)
        Signer.unsign('eyJiZXJ0aCI6NSwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2:47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s')
          Signer.signature('eyJiZXJ0aCI6NSwic2hpcCI6IkVuZGVhdm91ciJ9:1xGBt2'), the key, the harbour's key  ->  'YSbF_VgjbtGF5doByH7gSvy-a2-aj4n6kr9Paz5vDUo'
          constant_time_compare('47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s', 'YSbF_VgjbtGF5doByH7gSvy-a2-aj4n6kr9Paz5vDUo')  ->  False
          raises BadSignature
      raises BadSignature: Signature "47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s" does not match
```

## Objects: `Signer.sign_object` and `Signer.unsign_object`

`Signer.sign_object` signs a value of any type its serializer can write, not only a string (`django/core/signing.py:Signer.sign_object`). It serializes the value to bytes, with `JSONSerializer` unless given another serializer class, writes them in URL-safe base64 without the `"="` padding (`django/core/signing.py:b64_encode`), and signs that with `sign`, which on a `TimestampSigner` adds the time. Asked to compress, it first compresses the bytes with zlib and keeps the result only if it is shorter by more than one byte; compressed bytes get a `"."` in front of their base64, inside what is signed.

With `compress=True`, a `Signer` signs the harbour's berth as it is, with no `"."`, since compression would not shorten it. A dictionary of eight berths, 260 bytes of JSON, is compressed and signed in 140 characters beginning `".eJy"`, against 391 uncompressed.

`Signer.unsign_object` calls `unsign` first, passing a maximum age on to a `TimestampSigner`, and only then looks for the `"."`, decodes the base64 and decompresses: nothing unverified is ever decompressed (`django/core/signing.py:Signer.unsign_object`).

`JSONSerializer` writes JSON with no space after a comma or a colon and encodes it as Latin-1 (`django/core/signing.py:JSONSerializer`). Python's JSON encoder escapes every character outside ASCII unless told otherwise, so those bytes are ASCII whatever the value holds.

> **Why.** The default serializer is JSON so that even a stolen `SECRET_KEY` does not let an attacker run commands on the server when the data it forges is read, as forged data read with the pickle format could (`django/core/signing.py:JSONSerializer.loads`, `docs/topics/signing.txt`).

## `dumps` and `loads`

`dumps` makes a `TimestampSigner` from its key and salt and returns its `Signer.sign_object` of the value; `loads` makes one from its key, salt and fallback keys and returns its `Signer.unsign_object` of the string (`django/core/signing.py:dumps`, `django/core/signing.py:loads`). The defaults are no key, so `SECRET_KEY`; the salt `"django.core.signing"`; `JSONSerializer`; no compression; and no maximum age. The class is `TimestampSigner` whatever `SIGNING_BACKEND` names, and the algorithm is its default, `"sha256"`. Within Django the sessions call them, for a session's data and, in the backend that keeps the session in its cookie, for the session key ([The session store: `SessionBase`](../auth/sessions.md), [The session backends](../auth/session-backends.md)) (`django/contrib/sessions/backends/base.py:SessionBase.encode`, `django/contrib/sessions/backends/signed_cookies.py:SessionStore._get_session_key`).

A salt is a namespace: a string signed under one does not verify under another, so a value the site signed for one use cannot be passed to code that checks for another (`django/core/signing.py:Signer.signature`, `docs/topics/signing.txt`). Leaving the salt of `dumps` at its default, or sharing one salt between different parts of an application without good cause, is for that reason a security risk (`django/core/signing.py:dumps`).

Read back under its own salt, the harbour's berth is returned; under `"harbour.invoices"`, or under the default `"django.core.signing"` that `loads` uses when given none, it is refused as a forgery would be:

```text recording=security
dumps and loads: the berth signed under the salt "harbour.berths", read under it and under another
...
    signing.loads(s, salt="harbour.berths")  ->  {'berth': 4, 'ship': 'Endeavour'}
    signing.loads(s, salt="harbour.invoices")  ->  raises BadSignature: Signature "47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s" does not match
    signing.loads(s)  ->  raises BadSignature: Signature "47wJSFtm65vWL2pHocxqabmba8NeN5ousKdlcRR2x9s" does not match
```

## Cookies: `get_cookie_signer` and `SIGNING_BACKEND`

`get_cookie_signer` makes a signer for cookies (`django/core/signing.py:get_cookie_signer`). Its class is the one `SIGNING_BACKEND` names, `TimestampSigner` by default; its key is `SECRET_KEY` with `b"django.http.cookies"` in front, and its fallback keys likewise, so a cookie's signature differs from the one `dumps` makes with the same salt. The signed cookies of `HttpResponseBase.set_signed_cookie` use it with a salt that `_cookie_signer_salt` makes from the cookie's name and the caller's salt, and are read through `_unsign_cookie` ([Cookies](../http/cookies.md)) (`django/http/response.py:HttpResponseBase.set_signed_cookie`, `django/core/signing.py:_unsign_cookie`).

> **Trap.** `get_cookie_signer` gives its signer the fallback keys as a `map`, which can be gone through only once, and `Signer.unsign` goes through them whenever its value holds the separator. So the first such value given to `unsign` uses them up, whatever its signature, and every later call on the same signer checks the current key alone: a cookie signed with an old key is refused by a signer that has already read one such value. None of Django's own callers reads two values with one signer; code that keeps the signer `get_cookie_signer` returns and reads with it again does (`django/core/signing.py:get_cookie_signer`, `django/core/signing.py:Signer.unsign`).
