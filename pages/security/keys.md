---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Secret keys and `django.utils.crypto`

`SECRET_KEY` is the one secret from which Django makes every key that tells its own values from forged ones, and `SECRET_KEY_FALLBACKS` lists old keys it still accepts. `salted_hmac`, in `django.utils.crypto`, derives from the key a key for one use and makes an HMAC with that; the module also holds `constant_time_compare`, `get_random_string` and `pbkdf2`.

Django hands out values that come back to it: a signed cookie, a session kept in a cookie, the link in a password-reset email. To know such a value for its own when it returns, it attaches an HMAC, a hash of the value that only a holder of the key can compute. One key serves every use, so each use mixes in a **salt**, a string naming the use, and an HMAC made for one use does not verify for another. The salt, unlike the key, need not be secret, as Django's documentation says (`docs/topics/signing.txt`).

## Who uses the key

`SECRET_KEY` defaults to an empty string, and reading an empty one raises `ImproperlyConfigured`, so a project without a key fails at the first thing that needs it ([The settings object](../startup/settings.md)). What needs it:

| user | the key | the old keys |
|---|---|---|
| a `Signer` made with no key; so `dumps`, `loads` and the signed-cookie session backend | `SECRET_KEY` | `SECRET_KEY_FALLBACKS`, unless given others |
| `get_cookie_signer`: signed cookies, and the messages' `CookieStorage` | `SECRET_KEY` with `b"django.http.cookies"` in front | each fallback, with the same prefix |
| `SessionBase.encode` and `SessionBase.decode`: a session's data in the database, file and cached-database backends | through `dumps` | through `loads` |
| `AbstractBaseUser.get_session_auth_hash`: the HMAC of the user's password hash that a session keeps | through `salted_hmac` | through `AbstractBaseUser.get_session_auth_fallback_hash` |
| `PasswordResetTokenGenerator` | `PasswordResetTokenGenerator.secret`, `SECRET_KEY` unless set | `PasswordResetTokenGenerator.secret_fallbacks`, `SECRET_KEY_FALLBACKS` unless set |

*What Django derives from `SECRET_KEY`, and whether it also tries the old keys (`django/core/signing.py:Signer.__init__`, `django/core/signing.py:get_cookie_signer`, `django/contrib/sessions/backends/base.py:SessionBase.encode`, `django/contrib/auth/base_user.py:AbstractBaseUser._get_session_auth_hash`, `django/contrib/auth/tokens.py:PasswordResetTokenGenerator`).*

The key signs and the fallbacks only check. `Signer.sign` uses the signer's key alone; `Signer.unsign` tries the key and then each fallback in turn, and `PasswordResetTokenGenerator.check_token` does the same with its secrets (`django/core/signing.py:Signer.unsign`, `django/contrib/auth/tokens.py:PasswordResetTokenGenerator.check_token`). So a value made under an old key stays good while that key is a fallback, and whatever is signed meanwhile is signed with the new one. The documentation's way of rotating a key follows: the new key in `SECRET_KEY`, the old one at the front of `SECRET_KEY_FALLBACKS`, removed when what was made with it may expire (`docs/ref/settings.txt`).

Changing the key with no fallback refuses everything made with the old one, each user in its own way. `loads` raises `BadSignature`, and so does `HttpRequest.get_signed_cookie` unless it was given a default to return. A session's data stored in the database or a file that does not verify is logged to `"django.security.SuspiciousSession"` and read as an empty session (`django/contrib/sessions/backends/base.py:SessionBase.decode`). A user whose session hash was made under neither the key nor a fallback has the session flushed and is anonymous; one whose hash was made under a fallback keeps the session, under a new session key, with the hash made again under the new key (`django/contrib/auth/__init__.py:get_user`). A reset link no longer checks, and messages kept in a cookie are dropped.

Two things do not depend on the key. Passwords are hashed with salts of their own, and the documentation says a change of key does not affect them (`docs/ref/settings.txt`). The CSRF secret is a random string, made and compared without the key; in its cookie it outlasts a change of key, in the session as long as the session's data does ([The CSRF secret and its token](csrf-token.md)).

## `salted_hmac`

`salted_hmac` takes a salt, a value and a secret, which is `settings.SECRET_KEY` unless one is given. It hashes the salt followed by the secret, and uses that digest as the key of an HMAC of the value, made with the same hash; it returns Python's `hmac.HMAC`, from which the caller takes the digest in bytes or in hex. Salt, secret and value may each be a string or bytes: `force_bytes` makes them bytes (`django/utils/crypto.py:salted_hmac`).

A run with the harbour office's key gave two unrelated HMACs for one value under two salts:

```python
# salted_hmac, with the harbour office's SECRET_KEY
>>> from django.utils.crypto import salted_hmac
>>> salted_hmac("harbour.invoices", "invoice 112", algorithm="sha256").hexdigest()
'64145cd7b8dfa6a130c4c046574fd0d4a7b638e1257a6e7536fc540afec793a0'
>>> salted_hmac("harbour.berths", "invoice 112", algorithm="sha256").hexdigest()
'b2b68731c91bdd1e4a097074341035c2be5f32f4e1fd53e2798c027f27235890'
```

The comments on the derivation call it passing the salt and the base key through a pseudo-random function to get a derived key. They note that when the two together are longer than the hash's block size the step is redundant, since `hmac` hashes so long a key itself, and that Django does it always all the same.

Callers pass the secret to check against old keys: the session hash passes each fallback in turn, and the token generator each of its secrets. `Signer` reaches `salted_hmac` through `base64_hmac`, with its own key ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](signing.md)).

The algorithm is a keyword argument naming a constructor of `hashlib`, which `salted_hmac` looks up by that name. A name `hashlib` lacks raises `InvalidAlgorithm`, a `ValueError`: "'sha257' is not an algorithm accepted by the hashlib module." Given none, it uses SHA-1 and warns.

> **Deprecated.** Since 6.1 a call that names no algorithm warns with `RemovedInDjango2028Warning`, and in Django 2028 the default becomes `"sha256"` (`docs/releases/6.1.txt`). The warning skips Django's own files, so it is reported at the innermost line outside Django that led to the call. Django's own callers name one: `Signer` and `PasswordResetTokenGenerator` default to `"sha256"`, and the session hash passes it. `base64_hmac` has the same deprecation.

## `constant_time_compare`

`constant_time_compare` makes both values bytes and returns what `secrets.compare_digest` says of them (`django/utils/crypto.py:constant_time_compare`). It is what `Signer.unsign`, `PasswordResetTokenGenerator.check_token`, the loading of a request's user, the CSRF check ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)) and every password hasher but `Argon2PasswordHasher` compare with. The reason is Python's: the function's docstring says it "uses an approach designed to prevent timing analysis, making it appropriate for cryptography", and adds that values of different lengths may reveal their types and lengths, though not their values.

## `get_random_string`

`get_random_string` makes a string of the length asked for, each character chosen by `secrets.choice` from the characters it is given: `RANDOM_STRING_CHARS`, the letters of both cases and the digits, unless it is given others (`django/utils/crypto.py:get_random_string`). Its docstring measures the result as the base-2 logarithm of the number of characters raised to the length: with the default characters, about 71 bits for 12 and 131 for 22. Among its users are the CSRF secret, 32 letters and digits; a session's key, 32 of `VALID_KEY_CHARS`, lower-case letters and digits; the salts of the password hashers but the bcrypt ones (`django/contrib/auth/hashers.py:BasePasswordHasher.salt`); and a new project's key.

## `pbkdf2`

`pbkdf2` is `hashlib.pbkdf2_hmac` with SHA-256 unless another digest is given, and a derived key as long as the digest's output unless a length is given (`django/utils/crypto.py:pbkdf2`). Its users are the PBKDF2 password hashers, `PBKDF2PasswordHasher` first among the defaults of `PASSWORD_HASHERS` ([Password hashing: `make_password` and the hashers](../auth/hashers.md)).

## The key a new project gets

The startproject command ([The commands Django ships](../commands/builtin.md)) writes into the new project's settings a key of `"django-insecure-"` followed by 50 characters from `get_random_secret_key`, drawn by `get_random_string` from lower-case letters, digits and punctuation (`django/core/management/commands/startproject.py:Command.handle`, `django/core/management/utils.py:get_random_secret_key`). The prefix, in the words of the check that looks for it, indicates "that it was generated automatically by Django", and the deployment check of the key warns while it is there ([The security checks](checks.md)).
