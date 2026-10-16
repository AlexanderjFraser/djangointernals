---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Sessions and logins in the test client: `ClientMixin.login` and `force_login`

The test client keeps its cookies in `RequestFactory.cookies`, and reads the session they name through `ClientMixin.session`. `ClientMixin.login` checks credentials with `authenticate` and `ClientMixin.force_login` does not; both write the user into a session with `django.contrib.auth.login` and set its cookie, and `ClientMixin.logout` flushes it and drops every cookie.

A test of a page behind a login needs what a browser has after signing in: a session holding the user, and the cookie naming it. These methods make both without the login form, calling the auth application's functions on a request no handler sees and setting the cookie by hand. They are `ClientMixin`'s, so `Client` and `AsyncClient` both have them (`django/test/client.py:ClientMixin`).

## The cookies

`RequestFactory.__init__` gives every factory, and so every client, a `SimpleCookie` of its own ([Cookies](../http/cookies.md)), and `RequestFactory._base_environ` sends it with each request as `"HTTP_COOKIE"`: every cookie as its name and value, whatever its path, domain, expiry or Secure flag say, unless a `"Cookie"` header given to the client or with the request replaces them all (`django/test/client.py:RequestFactory._base_environ`). The documentation says so of expiry, and offers a new client to lose every cookie (`docs/topics/testing/tools.txt`). After each request `Client.request` merges in the response's cookies, each replacing the client's cookie of that name (`django/test/client.py:Client.request`). `AsyncRequestFactory._base_scope` sends them as a `"cookie"` header of the scope.

## The session: `ClientMixin.session`

`ClientMixin.session` is a property that answers with a store of the engine `SESSION_ENGINE` names. When the client holds a cookie under `SESSION_COOKIE_NAME`, the answer is a store for that key. When it holds none, the property makes a store, saves it at once, which gives it a key, and sets that key as the client's cookie (`django/test/client.py:ClientMixin.session`). So a client with no session has an empty one after a read.

Each read makes a new store, which loads the data afresh at its first use ([The session store: `SessionBase`](../auth/sessions.md)), so a value set on the property's answer directly is set on an object nothing keeps. The documentation's advice is to keep the store in a variable, change it, and call `SessionBase.save` (`docs/topics/testing/tools.txt`). `ClientMixin.asession` is the same as a coroutine method.

## Logging in from a test

The office's new_ship is behind `login_required`. A test module beside test_ships.py ([The test framework](../testing.md)) logs nora in both ways, and puts a value in the session:

```python
# harbour/office/tests/test_logins.py
import time

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import TestCase


def rows():
    return [(s.session_key[:8], sorted(s.get_decoded())) for s in Session.objects.all()]


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.nora = User.objects.create_user("nora", password="anchor-chain-7")

    def test_force_login(self):
        start = time.perf_counter()
        self.client.force_login(self.nora)
        print("force_login: %.3f s" % (time.perf_counter() - start), rows())

    def test_login(self):
        print("new_ship:", self.client.get("/ships/new/").status_code)
        start = time.perf_counter()
        print("login:", self.client.login(username="nora", password="anchor-chain-7"),
              "%.3f s" % (time.perf_counter() - start), rows())
        print("new_ship:", self.client.get("/ships/new/").status_code,
              sorted(self.client.cookies))
        self.client.logout()
        print("logout:", sorted(self.client.cookies), rows())

    def test_session(self):
        self.client.session["berth"] = "B4"
        print("unsaved:", rows())
        session = self.client.session
        session["berth"] = "B4"
        session.save()
        request = self.client.get("/ships/").wsgi_request
        print("saved:", rows(), request.session["berth"])
```

```text
$ python manage.py test harbour.office.tests.test_logins -v 0
System check identified no issues (0 silenced).
force_login: 0.004 s [('dsxlhtzx', ['_auth_user_backend', '_auth_user_hash', '_auth_user_id'])]
new_ship: 302
login: True 0.624 s [('7jsf7d4o', ['_auth_user_backend', '_auth_user_hash', '_auth_user_id'])]
new_ship: 200 ['csrftoken', 'sessionid']
logout: [] []
unsaved: [('fs3noza0', [])]
saved: [('fs3noza0', ['berth'])] B4
----------------------------------------------------------------------
Ran 3 tests in 1.295s

OK
```

Each login left one session holding the user's three entries; checking the password took over half a second, forcing the login a few milliseconds. In test_session the first read made an empty session and lost the value; the saved store reached the next request.

## `ClientMixin.login` and `force_login`

`ClientMixin.login` passes its keyword arguments to `authenticate`, which tries the backends of `AUTHENTICATION_BACKENDS` with them, `ModelBackend` checking a password through the hashers ([Authenticating: `authenticate` and the backends](../auth/authenticating.md)). If one answers with a user, the client logs the user in and returns `True`; if none does, `False`, after `authenticate` has sent `user_login_failed` with no request (`django/test/client.py:ClientMixin.login`).

`ClientMixin.force_login` asks nothing. It sets the user's backend attribute, as `authenticate` would, to the dotted path it is given or the one `ClientMixin._get_backend` chooses, and logs the user in (`django/test/client.py:ClientMixin.force_login`). The documentation offers it where how the user logged in does not matter, and as faster (`docs/topics/testing/tools.txt`). It lets in an inactive user, whom `ModelBackend` refuses, but only into the session: `ModelBackend.get_user` refuses the user again at the next request, and in a run new_ship sent an inactive nora, forced in, to the login page ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md)).

`_get_backend` takes the first entry of `AUTHENTICATION_BACKENDS` whose class overrides `BaseBackend.get_user` or `BaseBackend.aget_user`, by which a later request finds the user (`django/test/client.py:ClientMixin._get_backend`). In a run, a backend answering only permissions, listed first, was passed over for `ModelBackend`.

> **Changed in 6.2.** Before, a backend that overrides neither method could be chosen (`docs/releases/6.2.txt`).

## The login itself: `ClientMixin._login`

`ClientMixin._login` makes a bare `HttpRequest`, gives it the client's session as the property returns it (a new store if that one has no key, as when the session cookie's value is empty), and calls `django.contrib.auth.login` on it. That writes the three entries, after giving a session without a user a new key or flushing one that holds another user ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](../auth/login.md)). `_login` saves the session (`django/test/client.py:ClientMixin._login`), and `ClientMixin._set_login_cookies` sets the client's cookie under `SESSION_COOKIE_NAME` to its key, with the path `"/"`, the domain of `SESSION_COOKIE_DOMAIN`, Secure if `SESSION_COOKIE_SECURE`, and no expiry (`django/test/client.py:ClientMixin._set_login_cookies`).

No request goes through the handler: no login view, no `AuthenticationForm`, no CSRF check, no middleware. `django.contrib.auth.login` runs whole, so `user_logged_in` is sent and its receiver records `last_login`; but what it does to the request is lost with the request. The CSRF secret that `rotate_token` replaces is the bare request's: in a run, the client's `"csrftoken"` cookie was the same after its login as before, where a login through `LoginView` replaced it.

## `ClientMixin.logout`

`ClientMixin.logout` gives a bare request the client's session and the user `django.contrib.auth.get_user` reads from it, and calls `django.contrib.auth.logout`, which sends `user_logged_out` with that user, or with `None` if no one is logged in, and flushes the session. Then it replaces the cookies with an empty `SimpleCookie`: every cookie goes, not the session's alone (`django/test/client.py:ClientMixin.logout`).

## The asynchronous methods

`ClientMixin.alogin`, `ClientMixin.aforce_login` and `ClientMixin.alogout`, added in 5.0, take the same steps through `aauthenticate`, `django.contrib.auth.alogin` and `django.contrib.auth.alogout`, with `asession`. But `ClientMixin.alogout` puts the user on the bare request as `HttpRequest.user`, and `django.contrib.auth.alogout` asks `HttpRequest.auser`, which a bare request lacks: in a run, a receiver of `user_logged_out` got nora from the client's logout and `None` from its asynchronous one (`django/test/client.py:ClientMixin.alogout`, `django/contrib/auth/__init__.py:alogout`).
