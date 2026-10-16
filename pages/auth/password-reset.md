---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Password reset: `PasswordResetTokenGenerator` and the reset views

A password reset lets a user who has forgotten a password set a new one through a link mailed to the account's address. `PasswordResetView` and `PasswordResetForm` send the link, `PasswordResetConfirmView` checks it and takes the new password, and `PasswordResetTokenGenerator` makes and checks the token in the link without storing anything.

The link has to prove that whoever follows it read the mail sent to the account's address. It should work once, and not for long, and the form that sends it should not tell a stranger which addresses have accounts. Django keeps no record of the links it sends: the token is an HMAC of the user's own state, the password hash among it, which the reset itself changes, and checking a token is making it again. The four views are in `django.contrib.auth.urls`: `"password_reset/"` asks for the address, `"password_reset/done/"` says a mail went out, `"reset/<uidb64>/<token>/"` is the link, and `"reset/done/"` says the password was set (`django/contrib/auth/urls.py`).

## Asking for a link: `PasswordResetView`

`PasswordResetView` is a form view over `PasswordResetForm`, marked `login_not_required` and `csrf_protect` ([The form views](../views/editing.md)). When the form is valid it calls `PasswordResetForm.save` with the view's templates and token generator, the request, and `use_https=self.request.is_secure()`, then redirects to `"password_reset_done"` (`django/contrib/auth/views.py:PasswordResetView`).

`PasswordResetForm.get_users` decides who gets a mail. It asks the default manager for the active users whose email field (`AbstractBaseUser.get_email_field_name`) matches by `"__iexact"`; then, in Python, it keeps those with a usable password whose stored address equals the typed one under `_unicode_ci_compare`: NFKC normalization and case folding, the comparison Unicode Technical Report 36 recommends, as its docstring says (`django/contrib/auth/forms.py:PasswordResetForm.get_users`, `django/contrib/auth/forms.py:_unicode_ci_compare`). The mail goes to the stored address: nora typed NORA@harbour.example, and it went to nora@harbour.example.

The visitor is told the same either way: the view redirects to the done page whether a mail was sent or not, which the documentation says keeps an attacker from learning which addresses exist; it warns that the time a mail takes to send may tell it all the same (`docs/topics/auth/default.txt`). Nor does a failed send show: it is caught and logged to `"django.contrib.auth"` (`django/contrib/auth/forms.py:PasswordResetForm.send_mail`).

## The mail: `PasswordResetForm.save`

For each user, `save` makes the context of the mail's templates: `"uid"`, the primary key as a string in URL-safe base64 by `urlsafe_base64_encode` ([The helpers in `django/utils/http.py`](../http/helpers.md)); `"token"`, from `PasswordResetTokenGenerator.make_token`; `"protocol"`, `"https"` or `"http"`; `"domain"` and `"site_name"`, from `get_current_site` unless a caller gives `save` a domain_override, as the view does not; without `django.contrib.sites` that is a `RequestSite` whose name and domain are both the request's host; `"user"` and `"email"`; and the view's `extra_email_context` over them all (`django/contrib/auth/forms.py:PasswordResetForm.save`, `django/contrib/sites/shortcuts.py:get_current_site`).

`PasswordResetForm.send_mail` renders the subject and joins its lines into one, since, its comment says, a subject must not contain newlines; it renders the body and sends an `EmailMultiAlternatives`, with an HTML alternative only when the view names an HTML template ([Email messages: `EmailMessage` and `EmailMultiAlternatives`](../services/email-messages.md), [Sending email: `mailers` and the email backends](../services/mailers.md)) (`django/contrib/auth/forms.py:PasswordResetForm.send_mail`). The subject's template, `"registration/password_reset_subject.txt"`, is the auth application's; the body's, `"registration/password_reset_email.html"`, and the templates of the views' pages are the admin's, so a site without the admin writes its own. The office's ends with `{{ protocol }}://{{ domain }}{% url 'password_reset_confirm' uidb64=uid token=token %}`. Nora's mail, subject "Password reset on harbour.example":

```text
Someone asked to reset the password of nora.
http://harbour.example/accounts/reset/MQ/dgj90m-95ce358e6d687e9859dffa3b75fa3751/
```

## The token: `PasswordResetTokenGenerator`

`PasswordResetTokenGenerator.make_token` passes to `PasswordResetTokenGenerator._make_token_with_timestamp` the seconds from the start of 2001 to now, read as local time with no zone, and the generator's secret (`django/contrib/auth/tokens.py:PasswordResetTokenGenerator._now`). The token is two parts joined by a hyphen. The first is that number in base 36, which a comment says stays six digits until about 2069. The second is `salted_hmac` of `PasswordResetTokenGenerator._make_hash_value`, salted with `PasswordResetTokenGenerator.key_salt`, the class's dotted path, with `PasswordResetTokenGenerator.algorithm`, SHA-256 unless a subclass names another, keeping every second hex digit, 32 of 64, to shorten the URL, as the comment says (`django/contrib/auth/tokens.py:PasswordResetTokenGenerator._make_token_with_timestamp`).

`PasswordResetTokenGenerator.secret` and `PasswordResetTokenGenerator.secret_fallbacks` are properties that read `SECRET_KEY` and `SECRET_KEY_FALLBACKS` at each use unless set on the instance ([Secret keys and `django.utils.crypto`](../security/keys.md)). `default_token_generator` is the module's one instance, the default of the views and of `save` (`django/contrib/auth/tokens.py:PasswordResetTokenGenerator`, `django/contrib/auth/tokens.py:default_token_generator`).

`_make_hash_value` joins as text the user's primary key, the stored password string, the last login with its microseconds and zone dropped, or nothing before the first login, the timestamp, and the user's email, or nothing (`django/contrib/auth/tokens.py:PasswordResetTokenGenerator._make_hash_value`). Its docstring says why a token works once: the password field changes at a reset, even to the same password, because of the salt; the last login usually changes soon after; failing both, the timeout ends it. The HMAC, it adds, keeps a token from helping to crack the password while the secret is safe. A changed address ends a token the same way.

`PasswordResetTokenGenerator.check_token` refuses a missing user or token, a token that is not two parts joined by one hyphen, and a first part that is not base 36. It makes the token again for that timestamp under `secret` and then each of `secret_fallbacks`, comparing with `constant_time_compare`, and refuses if none matches. Last, it refuses a timestamp more than `PASSWORD_RESET_TIMEOUT` seconds old, 259,200 (three days) by default (`django/contrib/auth/tokens.py:PasswordResetTokenGenerator.check_token`). The timestamp is inside the HMAC, so it cannot be moved without the comparison failing. The documentation says a shorter timeout makes a token no harder to guess, since tokens are designed to be safe from brute force without one (`docs/ref/settings.txt`).

```text figure=the-reset-link
http://harbour.example/accounts/reset/MQ/dgj90m-95ce358e6d687e9859dffa3b75fa3751/

http://harbour.example
    "protocol" and "domain": https if the request for the link was secure; the host it named
/accounts/reset/
    the path of PasswordResetConfirmView, "password_reset_confirm"
MQ
    uidb64: nora's primary key, "1", in URL-safe base64
    PasswordResetConfirmView.get_user decodes it to the user; none, no form
dgj90m
    the timestamp: 813832294 seconds since 2001-01-01, in base 36
    check_token: makes the HMAC again with it, then refuses it if older than PASSWORD_RESET_TIMEOUT
-
    joins the token's two parts
    check_token: splits the token there; not two parts, refused
95ce358e6d687e9859dffa3b75fa3751
    every second hex digit of salted_hmac(key_salt, value, secret), SHA-256, of the value
    "1" + the password hash + the last login ("" before the first) + "813832294" + "nora@harbour.example"
    check_token: makes it again from the user's row as stored now, under SECRET_KEY and then each
    of SECRET_KEY_FALLBACKS, and compares; no match, refused
```

*The link nora was sent, cut into its parts, with what the confirm view and `check_token` do with each. The last part changes when nora's password, last login or address does.*

## Following the link: `PasswordResetConfirmView`

`PasswordResetConfirmView.dispatch` raises `ImproperlyConfigured` unless the URL gave `"uidb64"` and `"token"`. It finds the user with `PasswordResetConfirmView.get_user`, which decodes the base64, converts it with the primary key field's `to_python`, and asks the default manager; a value that does not decode, convert or name a user gives no user, and the page for an invalid link (`django/contrib/auth/views.py:PasswordResetConfirmView.get_user`). With a user there are two cases (`django/contrib/auth/views.py:PasswordResetConfirmView.dispatch`):

- The URL holds a token. If `PasswordResetTokenGenerator.check_token` accepts it, the view stores it in the session under `INTERNAL_RESET_SESSION_TOKEN`, `"_password_reset_token"`, and redirects to the same path with the token replaced by `PasswordResetConfirmView.reset_url_token`, `"set-password"`. Its comment gives the reason: the page with the form has no token in its URL, so the token cannot leak in the `"Referer"` header of a request made from that page.
- The URL holds `"set-password"`. The view checks the session's token and shows the form if it passes.

Anything else renders the template with `"validlink"` false and no form. The session's token is checked again at every request to the form's page, the submission included.

The form is `SetPasswordForm` for the user found: two fields that must match, and the validators of `AUTH_PASSWORD_VALIDATORS` ([The authentication forms: `AuthenticationForm` and the password forms](user-forms.md)). `PasswordResetConfirmView.form_valid` saves it, which sets the password and saves the user; deletes the session's entry; logs the user in, with `PasswordResetConfirmView.post_reset_login_backend`, only if `PasswordResetConfirmView.post_reset_login` is true, which by default it is not; and redirects to `PasswordResetCompleteView` (`django/contrib/auth/views.py:PasswordResetConfirmView.form_valid`). The new password changes the hash a logged-in session keeps, so a session the user has elsewhere ends at its next request ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)).

The test client, for nora:

| request | status | what followed |
|---|---|---|
| `"POST"` /accounts/password_reset/, NORA@harbour.example | 302 | to /accounts/password_reset/done/; one mail, to nora@harbour.example |
| `"POST"` the same, nobody@harbour.example | 302 | to /accounts/password_reset/done/; no mail |
| `"GET"` the link | 302 | to /accounts/reset/MQ/set-password/; `"sessionid"` set, the token in the session |
| `"GET"` /accounts/reset/MQ/set-password/ | 200 | the form |
| `"POST"` there, the new password twice | 302 | to /accounts/reset/done/; the token gone from the session |
| `"GET"` the link again | 200 | "This link is not valid." |

*Nora's reset; the second row is another visitor's.*

A link sent to tomas stopped working, with no reset, when tomas logged in before following it: tomas's last login had changed.
