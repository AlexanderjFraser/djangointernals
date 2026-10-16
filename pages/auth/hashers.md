---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Password hashing: `make_password` and the hashers

`make_password` turns a password into the string a user model stores, and `django.contrib.auth.hashers.check_password` checks a password against such a string. Between them stand the **hashers**, the classes of `PASSWORD_HASHERS`: the first makes new strings unless another is named, and each checks the strings of its own algorithm.

A site has to check a password without being able to give it back, so it stores a one-way function of it: slow, so that a stolen table costs an attacker time for every guess, and salted with a random value, against rainbow tables. The cost must rise as computers grow faster, without breaking stored strings. So the string describes itself: it names its hasher and carries what that hasher needs to make it again, the cost included. An old string is checked by what it says while its hasher is listed, and replaced at its user's next login (`docs/topics/auth/passwords.txt`).

## The encoded string

```text figure=an-encoded-password
pbkdf2_sha256$1800000$RVCWTsBrKg4J3kzFwrSy5d$KqCZK8R3DfgljJNA8oepLrkWFx3pyG0THfvfixWEQ7k=

pbkdf2_sha256     the algorithm: identify_hasher finds the hasher by it
1800000           the iterations: must_update compares them with the hasher's
RVCWTsBrKg4J3kzFwrSy5d
                  the salt: 22 characters that salt() draws for 128 bits
KqCZK8R3DfgljJNA8oepLrkWFx3pyG0THfvfixWEQ7k=
                  the derived key: PBKDF2 with SHA-256, 32 bytes in base64,
                  which verify makes again from the password and compares
```

*Nora's password as the user's row keeps it, cut at its `"$"`. The first part chooses the hasher; the rest is all it needs.*

`PBKDF2PasswordHasher.encode` derives the key with `pbkdf2`, which calls `hashlib.pbkdf2_hmac`, and joins the four parts (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher.encode`). `PBKDF2PasswordHasher.verify` encodes the password given with the stored salt and iterations and compares the strings with `constant_time_compare` ([Secret keys and `django.utils.crypto`](../security/keys.md)): nothing is decrypted. The digest is the one parameter the string does not carry, and the class's docstring says the algorithm must be renamed if the digest changes.

## `make_password`

`make_password` takes a password, a salt and a hasher, `"default"` unless named (`django/contrib/auth/hashers.py:make_password`). `None` aside, it refuses anything but a string or bytes with a `TypeError`, takes the hasher from `get_hasher`, asks it for a salt when none was given, and returns its `encode`. `AbstractBaseUser.set_password` calls it ([The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`](user-model.md)).

`None` gives an **unusable password**, `UNUSABLE_PASSWORD_PREFIX`, `"!"`, and 40 random characters. `is_password_usable` answers false for it, and `verify_password` answers no to every password against it without asking a hasher. The docstring, citing ticket 20079, says the random part makes access to a staff or superuser account less likely.

```python
# a shell of the harbour office's site
>>> make_password(None)
'!2U81a9QevIDf3U3kwO6ouyDp9stBPJUD7FaLmKYu'
```

## Finding the hasher

`get_hashers` makes an instance of each class of `PASSWORD_HASHERS`, refusing one whose `algorithm` is empty with `ImproperlyConfigured`; `get_hashers_by_algorithm` indexes them by algorithm (`django/contrib/auth/hashers.py:get_hashers`). Both are cached with `functools.lru_cache`, and `reset_hashers`, a receiver of `setting_changed`, empties them when a test overrides `PASSWORD_HASHERS` ([Overriding settings](../startup/overrides.md)). Making a hasher loads nothing: the default list's Argon2 and bcrypt hashers need their libraries only at a string of theirs, failing then with the `ValueError` of `BasePasswordHasher._load_library`.

`get_hasher` returns a hasher it is given as it is, the first of the list for `"default"`, and otherwise the hasher of that algorithm, or a `ValueError` (`django/contrib/auth/hashers.py:get_hasher`). `identify_hasher` takes the algorithm from a stored string's part before the first `"$"` (`django/contrib/auth/hashers.py:identify_hasher`). It first recognises the unsalted forms of ancient Django by length and form as `"unsalted_md5"` and `"unsalted_sha1"`, whose hashers Django 5.1 removed, so such a string finds none unless a project supplies one (`docs/releases/5.1.txt`).

## Checking a password: `verify_password`

`verify_password` answers whether the password matches the string, and whether the string should be made again (`django/contrib/auth/hashers.py:verify_password`). In order:

1. If the password is `None`, the string unusable, or `identify_hasher` finds no hasher, it hashes 40 random characters with the default hasher and answers no to both. The comment's reason: to narrow the difference in time between a user with an unusable password and a missing user or hasher, as for ticket 20760 ([Authenticating: `authenticate` and the backends](authenticating.md)).
2. The string is due for an update if its algorithm is not the preferred hasher's, the default unless named, or if the preferred hasher's `must_update` says so.
3. The string's hasher's `verify` decides the match.
4. If the password was wrong, the algorithm the preferred one and the string due for an update, the hasher's `harden_runtime` runs, to close, by the comment, the gap in time between the string's work factor and the hasher's default.

| the stored string | password | answer | time |
|---|---|---|---|
| nora's, 1,800,000 iterations | right; wrong | `(True, False)`; `(False, False)` | 0.58 s |
| 1,500,000 iterations | right | `(True, True)` | 0.49 s |
| 1,500,000 iterations | wrong | `(False, True)` | 0.58 s |
| unusable | any | `(False, False)` | 0.57 s |
| `MD5PasswordHasher`'s | right; wrong | `(True, True)`; `(False, True)` | 0.00001 s |

*`verify_password`'s answers and times in one run, the last row's with `MD5PasswordHasher` listed after `PBKDF2PasswordHasher`. The wrong password against the older string paid 300,000 iterations more in `harden_runtime`.*

> **Trap.** The fourth step is skipped when the algorithm differs, the comment saying enumeration is not protected against then: a wrong password against an MD5 string answers at once, a missing user takes a full hash. The documentation warns of it and shows how to rehash old strings (`docs/topics/auth/passwords.txt`).

## The upgrade at a login

`django.contrib.auth.hashers.check_password` returns `verify_password`'s first answer and, when the password is right and the string due for an update, calls the setter it was given with the password (`django/contrib/auth/hashers.py:check_password`). `acheck_password` runs `verify_password` through `sync_to_async` and awaits the setter.

`AbstractBaseUser.check_password`'s setter sets the password with the default hasher and saves the `password` field alone, first clearing `AbstractBaseUser._password`, since by its comment a hash upgrade is not a password change (`django/contrib/auth/base_user.py:AbstractBaseUser.check_password`). With `PASSWORD_HASHERS` holding `PBKDF2PasswordHasher` and `MD5PasswordHasher`, tomas was given an MD5 string and logged in at the login view, whose second SQL statement updated the password column alone:

```python
# a shell of the harbour office's site
>>> User.objects.get(username="tomas").password
'md5$hCHZa3vLmm3mvN6FfAlHom$1cc3fbe1781fa9d711672b83d5f786b5'
>>> response = Client(HTTP_HOST="harbour.example").post(
...     "/accounts/login/", {"username": "tomas", "password": "Beagle-1831"})
>>> User.objects.get(username="tomas").password
'pbkdf2_sha256$1800000$Egin7tbQI1sXoIICzgsKjc$Kl7V/ePlbfF9M3mhGoDEg8V24qwLlDUsbZnon8r5VeA='
```

## `BasePasswordHasher`

A subclass of `BasePasswordHasher` names its `algorithm` and implements `encode`, `decode`, `verify` and `safe_summary`, which raise `NotImplementedError` on the base (`django/contrib/auth/hashers.py:BasePasswordHasher`). `BasePasswordHasher.must_update` answers false; `BasePasswordHasher.harden_runtime` warns, its docstring asking a hasher with no work factor to do nothing.

`BasePasswordHasher.salt` draws from `RANDOM_STRING_CHARS`, 62 letters and digits, enough characters for `BasePasswordHasher.salt_entropy`, 128 bits: 22, which hold about 131. `must_update_salt` makes the same reckoning of a stored salt, for the PBKDF2, Argon2 and MD5 hashers' `must_update`. `safe_summary` gives a string's parts for display, `mask_hash` keeping six characters of the salt (two of an MD5 salt) and of the hash and a `"*"` for each of the rest (`django/contrib/auth/hashers.py:BasePasswordHasher.salt`, `django/contrib/auth/hashers.py:mask_hash`); `UserChangeForm` shows it in place of the password ([The authentication forms: `AuthenticationForm` and the password forms](user-forms.md)).

## The hashers Django ships

| hasher | `algorithm` | after it, between `"$"` | the cost |
|---|---|---|---|
| `PBKDF2PasswordHasher` | `"pbkdf2_sha256"` | iterations, salt, key in base64 | 1,800,000 iterations |
| `PBKDF2SHA1PasswordHasher` | `"pbkdf2_sha1"` | the same, with SHA-1 | the same |
| `Argon2PasswordHasher` | `"argon2"` | argon2-cffi's: variety, version, parameters, salt, hash | time 2, memory 102,400 KiB, parallelism 8 |
| `BCryptSHA256PasswordHasher` | `"bcrypt_sha256"` | bcrypt's: an empty part, its algorithm string, rounds, then salt and checksum in one | 12 rounds |
| `BCryptPasswordHasher` | `"bcrypt"` | the same | the same |
| `ScryptPasswordHasher` | `"scrypt"` | work factor, salt, block size, parallelism, key in base64 | 16,384, 8, 5 |
| `MD5PasswordHasher` | `"md5"` | salt, MD5 of salt and password in hex | none |

*Django's hashers. `PASSWORD_HASHERS` lists all but `BCryptPasswordHasher` and `MD5PasswordHasher`, in this order (`django/conf/global_settings.py`).*

`PBKDF2PasswordHasher.must_update` asks for a new string when the stored iterations differ from `PBKDF2PasswordHasher.iterations`, fewer or more, or the salt is short; `PBKDF2PasswordHasher.harden_runtime` runs the iterations missing (`django/contrib/auth/hashers.py:PBKDF2PasswordHasher.must_update`).

> **Changed in 6.2.** The iterations went from 1,500,000 to 1,800,000 (1,200,000 in 6.0); the documentation promises a rise with each release (`docs/releases/6.2.txt`, `docs/releases/6.1.txt`, `docs/topics/auth/passwords.txt`).

`Argon2PasswordHasher` hashes with argon2-cffi's Argon2id and leaves the check to that library. `BCryptSHA256PasswordHasher` takes its salt from bcrypt, which writes the rounds into it, and hashes the password's SHA-256 digest in hex, against the truncation of ticket 20138: `BCryptPasswordHasher`, hashing the password as given, is subject to bcrypt's limit of 72 bytes, its docstring says (`django/contrib/auth/hashers.py:BCryptSHA256PasswordHasher.encode`). A round doubles bcrypt's work, so its `harden_runtime` hashes three more times for two rounds missing. That of Argon2 and of scrypt does nothing, their comments calling the runtime too complicated to harden sensibly.

`MD5PasswordHasher` is the documentation's choice for tests that authenticate many users, where the default hasher is "rather slow by design" (`docs/topics/testing/overview.txt`).
