---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Applications and tools
contents: sessions, session-middleware, session-backends, user-model, hashers, password-validation, authenticating, login, permissions, creating-permissions, requiring-login, user-forms, login-views, password-reset, createsuperuser, messages, message-storage
---

# Authentication, sessions and messages

Three applications of `django.contrib` give a site the memory that HTTP lacks. `django.contrib.sessions` keeps a dictionary for each browser from one request to the next; `django.contrib.auth` keeps in that dictionary which user the browser belongs to, and checks passwords and permissions; `django.contrib.messages` keeps a note written while one request is answered until a later page shows it.

HTTP has no memory. Each request arrives alone, and all a browser carries from one request to the next is what a site asked it to keep, in a cookie. A cookie is a poor place for most of what a site wants to remember: the browser can read it and change it, and it travels with every request. So by default the session keeps only a random key in the cookie, `"sessionid"` unless `SESSION_COOKIE_NAME` says otherwise, and the data under that key on the server, in a database table. Everything else in this chapter stands on that.

Authentication stands on the session. Logging in checks a password once and writes the user's id into the session; a later request of that browser that asks who the user is reads the id back and fetches the user. Messages stand on the cookie and the session: a message is kept, by default, in a signed cookie of its own, or in the session when the cookie cannot hold it, until the page that shows it has been sent. Each of the three is an application in `INSTALLED_APPS` and a middleware in `MIDDLEWARE`, and the middleware are layers of the chain that [Handlers and middleware](handlers.md) describes.

## The objects

| object | what it is | when it acts |
|---|---|---|
| `SessionMiddleware` | gives each request a **session store** for the key in its cookie; on the way out, saves a changed store and sets its cookie, or deletes the cookie | on the way in, and on the way out |
| `SessionBase` | the base of every session store: a dictionary that is loaded at its first use and knows whether it was read or changed. Each backend's store subclasses it, `django.contrib.sessions.backends.db.SessionStore` by default | whenever the request's session is used |
| `AuthenticationMiddleware` | puts on the request `HttpRequest.user`, a lazy object that finds the user from the session at its first use | on the way in |
| `authenticate` | asks each **authentication backend** named in `AUTHENTICATION_BACKENDS` whether the credentials name a user | when a login form is checked |
| `ModelBackend` | the default backend: finds a user of the user model by username and checks the password, and says which permissions a user has | when `authenticate` or a permission check asks it |
| `login`, `logout` | write the user into the session, ordinarily under a new session key; empty the session | when a view calls them |
| `django.contrib.auth.get_user` | reads the user back from the session, and checks that the user's stored password has not changed since | at the first use of `HttpRequest.user` |
| `AbstractBaseUser` | the base of a user model: the password, kept as a hash, and the methods that set and check it | when a password is set or checked |
| `make_password`, `django.contrib.auth.hashers.check_password` | turn a password into the string kept in the database, and check a password against that string, with the **hashers** of `PASSWORD_HASHERS` | the same |
| `PermissionsMixin` | a user's groups and permissions, and `PermissionsMixin.has_perm`, which asks the backends | when a view or a template asks |
| `MessageMiddleware` | gives each request a **message storage**; on the way out, stores the messages no page has shown yet | on the way in, and on the way out |
| `FallbackStorage` | the default storage: messages in a signed cookie, and in the session what the cookie cannot hold | when messages are added, read or stored |

*The objects that carry sessions, authentication and messages. The sessions are in `django/contrib/sessions/`, authentication in `django/contrib/auth/`, messages in `django/contrib/messages/`.*

## One browser through the harbour office's site

The harbour office's staff sign in to request berths for ships. The site's settings install the three applications, with contenttypes, which the permissions need, and their middleware in the order startproject writes them:

```python
# harbour/settings.py
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "harbour.fleet",
    "harbour.crew",
    "harbour.office",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
LOGIN_REDIRECT_URL = "/berths/"
```

The URLconf takes the login, logout and password views from `django.contrib.auth.urls`, and adds two views of the office's own. The first requires a login and adds a message when a berth is requested; the second requires a permission:

```python
# harbour/urls.py
from django.urls import include, path

from harbour.office import views

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),
    path("berths/", views.berths, name="berths"),
    path("ships/<int:pk>/edit/", views.edit_ship, name="edit-ship"),
]
```

```python
# harbour/office/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from harbour.fleet.models import Ship


@login_required
def berths(request):
    if request.method == "POST":
        messages.success(request, "Berth requested for %s." % request.POST["ship"])
        return redirect("berths")
    return render(request, "office/berths.html")


@permission_required("fleet.change_ship", raise_exception=True)
def edit_ship(request, pk):
    ship = get_object_or_404(Ship, pk=pk)
    return HttpResponse("Editing %s." % ship.name)
```

```html
<!-- harbour/office/templates/office/berths.html -->
{% for message in messages %}<p class="{{ message.tags }}">{{ message }}</p>
{% endfor %}<p>Signed in as {{ user.get_username }}.</p>
<form method="post">{% csrf_token %}<input name="ship"><button>Request a berth</button></form>
```

The office has three users: nora, a clerk, who is in the group Clerks, which has the permission `"fleet.change_ship"`; tomas, who has no group and no permission; and piet, a superuser. One browser, driven by Django's test client, which keeps cookies from response to response as a browser does, made these requests as nora. The table gives what each response did with the cookies and what SQL each request sent.

| request | response | cookies set | SQL sent |
|---|---|---|---|
| `"GET"` /berths/, with no cookie | 302 to /accounts/login/?next=/berths/ | none | none |
| `"POST"` /accounts/login/, nora's username and password | 302 to /berths/ | `"sessionid"`, `"csrftoken"` | the user, by username; whether a new session key is taken; the session's row inserted; the user's last login updated; the session's row updated |
| `"GET"` /berths/ | 200, "Signed in as nora." | `"csrftoken"` | the session's row; the user |
| `"POST"` /berths/, ship=Endeavour | 302 to /berths/ | `"messages"` | the session's row; the user |
| `"GET"` /berths/ | 200, with "Berth requested for Endeavour." above | `"messages"` deleted; `"csrftoken"` | the session's row; the user |
| `"GET"` /ships/1/edit/ | 200, "Editing Endeavour." | none | the session's row; the user; the user's own permissions; the permissions of the user's groups; the ship |
| `"POST"` /accounts/logout/ | 200, "Signed out." | `"sessionid"` deleted | the session's row; the user; the session's row again, by its key; its delete |

*Nora's visit. Every response also had `Vary: Cookie`, which the session middleware adds when the session was read, and whenever it sets or deletes the session's cookie. The CSRF cookie is sent again with each page that carries a token ([The CSRF secret and its token](security/csrf-token.md)).*

The first request touched the session and sent no SQL. `login_required` asked whether the user was authenticated, which made `HttpRequest.user` look in the session; the request had no session cookie, so there was no key to load and the session was an empty dictionary, and the user was an `AnonymousUser`. The decorator answered with a redirect to `LOGIN_URL`, `"/accounts/login/"` by default, with the page asked for in `"next"` (`django/contrib/auth/decorators.py:user_passes_test`).

The login did the most. `LoginView`'s form called `authenticate`, which found nora's row by the username and checked the password. Then `login` gave the browser a session: it took a key no row had, inserted an empty session under it, wrote three entries into it, and sent `user_logged_in`, whose receiver updated nora's last login. On the way out the session middleware saw a changed session and saved it, and set the cookie `"sessionid"` to the key, for two weeks and with HttpOnly (`django/contrib/auth/__init__.py:login`). The row it saved holds the three entries, signed:

```python
>>> Session.objects.get().get_decoded()
{'_auth_user_id': '1', '_auth_user_backend': 'django.contrib.auth.backends.ModelBackend', '_auth_user_hash': '87eaae5073bef1d784467f44342a527ae4afe4b180b86d67f8bc750d277a008c'}
```

Every request after that began with two queries: the session's row, found by the cookie's key, and the user, found by the id in it. A request that asks for a permission adds two more, the user's own permissions and those of the user's groups, and a superuser's adds none. The message went into a cookie of its own and came out on the next page, and that page's response deleted the cookie. Logging out deleted the session's row and the cookie.

A request is served by all four middleware, each with a part on the way in and a part on the way out. Here is the `"POST"` that added the message:

```text figure=one-request
POST /berths/ with the cookies "sessionid" and "csrftoken", and ship=Endeavour

on the way in, in the order of MIDDLEWARE
  SessionMiddleware          request.session: a SessionStore for the cookie's key, not yet loaded
  CsrfViewMiddleware         the CSRF secret read from its cookie
  AuthenticationMiddleware   request.user: a lazy object, which will call get_user
  MessageMiddleware          a FallbackStorage for the request

before the view
  CsrfViewMiddleware         the POST's token checked against the secret

the view, under login_required
  request.user.is_authenticated   get_user: the session loaded         SELECT the session's row
                                  the user id and backend read from it  SELECT the user
                                  the session's hash checked against the user's password
  messages.success(...)           the message queued in the storage

on the way out, in the reverse order
  MessageMiddleware          the queued message signed into the cookie "messages"
  AuthenticationMiddleware   nothing
  CsrfViewMiddleware         nothing: no token was asked for
  SessionMiddleware          the session was read and not changed: not saved; Vary: Cookie
```

*The four middleware on the request that added a message. Nothing is read from the database until the view asks who the user is.*

## The session

`SessionMiddleware.process_request` reads the key from the request's cookie and makes a session store for it, of the class called `SessionStore` in the module that `SESSION_ENGINE` names, `django.contrib.sessions.backends.db` unless it names another; the middleware imports that module once, when it is made (`django/contrib/sessions/middleware.py:SessionMiddleware`). The store reads nothing yet. It behaves as a dictionary, and its first read or write of a key loads the data: from storage when there is a key, or as an empty dictionary when there is none. It records that it was **accessed**, and, when a key is set or deleted, that it was **modified** ([The session store: `SessionBase`](auth/sessions.md)) (`django/contrib/sessions/backends/base.py:SessionBase._get_session`).

On the way out, `SessionMiddleware.process_response` decides from those two flags and whether the store is empty. A session that has ended up empty, when the request brought a session cookie, has its cookie deleted. A modified session that is not empty is saved, and its cookie set again, ordinarily with a fresh expiry, unless the response's status is 500 or more; `SESSION_SAVE_EVERY_REQUEST` saves it even when it was not modified. And a response whose session was accessed gets `"Cookie"` in its `"Vary"`, since what it says may depend on who asked ([`SessionMiddleware`: the cookie and the save](auth/session-middleware.md)) (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`).

A session's key is 32 random characters, lower-case letters and digits. Its data is a dictionary, serialized as JSON unless `SESSION_SERIALIZER` names another serializer; the default store keeps it signed, and compressed when that is shorter by more than one byte: a row whose data no longer matches its signature loads as an empty session (`django/contrib/sessions/backends/base.py:SessionBase.encode`, `django/contrib/sessions/backends/base.py:SessionBase.decode`). The default store keeps it in the table `"django_session"`, beside the key and the time it expires; others keep it in the cache, in the cache in front of the database, in files, or in the cookie itself, where the key is the signed data and nothing is kept on the server at all ([The session backends](auth/session-backends.md)).

## Who the user is

Logging in is two steps. `authenticate` finds the user that some credentials name, and `login` makes the session remember that user. `LoginView` does both, by way of `AuthenticationForm`.

`authenticate` goes through `AUTHENTICATION_BACKENDS` in order, passing over a backend whose `authenticate` cannot take the credentials given. The first backend that returns a user wins, and the user is marked with the backend's dotted path; a backend that raises `PermissionDenied` ends the search with no user. Whenever the search ends with no user, the `user_login_failed` signal is sent ([Authenticating: `authenticate` and the backends](auth/authenticating.md)) (`django/contrib/auth/__init__.py:authenticate`). The default backend, `ModelBackend`, looks the username up on the user model, checks the password, and refuses a user whose `is_active` is false. When no user has that username it hashes the password all the same, so that the time a refusal takes does not tell an existing username from a missing one (`django/contrib/auth/__init__.py:check_password_with_timing_attack_mitigation`).

`login` writes three entries into the session: the user's primary key, the backend's path, and a hash of the user's stored password. Before writing them it looks at what the session holds. A session with no user yet is given a new key and keeps its data, which Django's documentation gives as a defence against session fixation; a session that holds another user, or this user with another hash, is emptied instead. It then puts the user on the request, replaces the CSRF secret, and sends `user_logged_in`, whose receiver, connected when the user model has a `last_login` field, records the time there ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](auth/login.md)) (`django/contrib/auth/__init__.py:login`, `docs/topics/http/sessions.txt`).

`AuthenticationMiddleware` does not find the user. It puts on the request a `SimpleLazyObject` that calls `django.contrib.auth.get_user` the first time the user is used, and keeps the answer for the rest of the request ([Lazy objects: `LazyObject` and `SimpleLazyObject`](utils/lazy-objects.md)) (`django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request`). `get_user` reads the id and the backend's path from the session, gives up if that backend is no longer in `AUTHENTICATION_BACKENDS`, and asks the backend for the user. Then it compares the hash in the session with the hash of the user's password now. If they differ, the stored password or the secret key has changed since the login; a new password does that, and so does the old one hashed again at a login in another browser. When the hash in the session matches one made with a key of `SECRET_KEY_FALLBACKS`, the session is kept, under a new key and with the new hash; otherwise it is emptied, and the request is anonymous. So changing a password logs out every session of that user, which the documentation names as the purpose; the password change view keeps its own session with `update_session_auth_hash` (`django/contrib/auth/__init__.py:get_user`, `docs/topics/auth/default.txt`).

`logout` sends `user_logged_out` first, so that its receivers can still tell who it was, then flushes the session (the data emptied, the stored session deleted, the key dropped) and puts an `AnonymousUser` on the request (`django/contrib/auth/__init__.py:logout`).

## Passwords

A user model keeps no password, only a string from which a password can be checked. Nora's is this:

```text
pbkdf2_sha256$1800000$RVCWTsBrKg4J3kzFwrSy5d$KqCZK8R3DfgljJNA8oepLrkWFx3pyG0THfvfixWEQ7k=
```

The first part names the hasher, and the rest is the hasher's own: for PBKDF2 the number of iterations, a random salt and the derived key in base64. `make_password` makes such a string with the first hasher of `PASSWORD_HASHERS`; `check_password` finds the hasher by the string's first part, among those the setting lists, and has it compare (`django/contrib/auth/hashers.py:make_password`, `django/contrib/auth/hashers.py:verify_password`). When a user's right password is checked against a string that the first hasher would now make otherwise (another algorithm, another number of iterations, a salt too short), the password is hashed again with the first hasher and saved. The documentation gives the purpose: an old project's stored passwords move to a better algorithm as its users log in ([Password hashing: `make_password` and the hashers](auth/hashers.md)) (`django/contrib/auth/base_user.py:AbstractBaseUser.check_password`, `docs/topics/auth/passwords.txt`).

> **Changed in 6.2.** The PBKDF2 hasher's iterations went from 1,500,000 to 1,800,000. A string made with fewer is hashed again at its user's next login (`docs/releases/6.2.txt`, `django/contrib/auth/hashers.py:PBKDF2PasswordHasher.must_update`).

Whether a new password is good enough is a separate question, asked by the password forms and by the commands when they prompt for one, and not by `AbstractBaseUser.set_password`: `validate_password` runs the validators of `AUTH_PASSWORD_VALIDATORS`, an empty list unless a project's settings fill it, as the ones startproject writes do ([Password validation: `validate_password` and the validators](auth/password-validation.md)).

## Permissions

A permission is a row of the table `"auth_permission"`: a content type, which names a model, and a codename such as `"change_ship"`. Code names it by a string, the application's label and the codename, `"fleet.change_ship"`. After each migrate, `create_permissions`, a receiver of `post_migrate`, makes the missing rows for each model's actions, add, change, delete and view unless its `Meta` names others, together with any further permissions its `Meta` asks for; a many-to-many table that Django makes by itself gets none ([Making the permissions: `create_permissions`](auth/creating-permissions.md)).

`PermissionsMixin.has_perm` answers yes at once for an active superuser, without a query. For anyone else it asks each backend in turn, until one says yes or raises `PermissionDenied`, which makes the answer no (`django/contrib/auth/models.py:_user_has_perm`). `ModelBackend` builds the set of a user's permissions, the user's own and the user's groups', in two queries, keeps it on the user object, and answers from the set; an inactive user has none, and a question about one object gets an empty set from it, its permissions being by model and not by object, as `Permission`'s docstring says ([Permissions: `Permission`, groups and `has_perm`](auth/permissions.md)) (`django/contrib/auth/backends.py:ModelBackend._get_permissions`). In the example nora has `"fleet.change_ship"` through the group Clerks and tomas has nothing, so the edit page answered tomas with a 403, `permission_required` having been told to raise `PermissionDenied` rather than redirect to the login page ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](auth/requiring-login.md)).

## Messages

The view's `django.contrib.messages.api.success` is `add_message` at the level `SUCCESS`, 25 (`django/contrib/messages/constants.py`). It hands the message to the storage that `MessageMiddleware` put on the request, which queues it if its level is at least `MESSAGE_LEVEL`, `INFO` (20) unless the setting says otherwise (`django/contrib/messages/api.py:add_message`, `django/contrib/messages/storage/base.py:BaseStorage.add`).

Nothing is stored while the view runs. On the way out, `MessageMiddleware.process_response` calls the storage's `BaseStorage.update`, which stores what no page has read: the messages added during this request, and those loaded from an earlier one if nothing iterated over them. When nothing was added and nothing read, it stores nothing, and the cookie stays as it was ([Messages: `add_message`, `Message` and `MessageMiddleware`](auth/messages.md)). `FallbackStorage` puts them first in the cookie `"messages"`, signed, and gives what does not fit in 2,048 characters to `SessionStorage`, which keeps it in the session. The cookie of the example holds the message as JSON in URL-safe base64, which anyone can read; the signature only makes a change detectable ([Message storage: `CookieStorage`, `SessionStorage` and `FallbackStorage`](auth/message-storage.md)):

```text
[["__json_message",0,25,"Berth requested for Endeavour.",""]]
```

The next request's storage loads them when something first reads it. The template's loop over `messages`, the storage itself as the messages context processor gives it, read them and marked them used; on the way out nothing was left to store, so the cookie was deleted. A message that no page shows is kept for the next one.

Whatever the storage writes to the session, it writes in `MessageMiddleware.process_response`, which runs before `SessionMiddleware.process_response` saves the session, because the message middleware is inside the session middleware in the chain. In the other order there would be no session when the storage is made, and `SessionStorage` refuses to be made for a request without one, with a message that names the order (`django/contrib/messages/storage/session.py:SessionStorage.__init__`).

## Where they meet the rest of Django

The three middleware are layers of the chain in [Handlers and middleware](handlers.md), and the cookies they set and delete are a response's ([Cookies](http/cookies.md)). The default session store's data and the message cookie are signed with `django.core.signing`, and the session's hash of the password is a `salted_hmac` ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](security/signing.md), [Secret keys and `django.utils.crypto`](security/keys.md)); `login` replaces the CSRF secret with `rotate_token` ([The CSRF secret and its token](security/csrf-token.md)). The request's user is a lazy object of [The utility layer](utils.md). The login signals are sent through the dispatcher of [Signals: `Signal`, receivers and sending](services/signals.md), and the cache session backends store through [The cache API: `caches` and `BaseCache`](services/cache-api.md). The user model can be replaced by a project's own, through the setting `AUTH_USER_MODEL` and the swappable option of its `Meta` ([The options: what a model keeps as `_meta`](models/options.md), [The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`](auth/user-model.md)). The login view and the password views that take a form are generic form views ([The form views](views/editing.md)), and their forms are forms ([Forms](forms.md)). Permissions name models by their content types ([Content types: `ContentType` and its cache](contrib/content-types.md)), and are made by a receiver of `post_migrate` ([The migrate command, showmigrations and sqlmigrate](migrations/migrate.md)). The admin admits staff users and asks the same permissions ([The admin](admin.md)), and the test client logs in without a form ([Sessions and logins in the test client: `ClientMixin.login` and `force_login`](testing/client-login.md)).
