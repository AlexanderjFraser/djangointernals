---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The authentication forms: `AuthenticationForm` and the password forms

`django/contrib/auth/forms.py` holds the forms under the login and password views and the admin: `AuthenticationForm`, which checks a username and a password with `authenticate`; `SetPasswordMixin`, which checks a new password typed twice and sets it, and the forms built on it; and `UserChangeForm`, which shows the stored hash and never a password.

A new password is typed twice and must agree with itself, is judged by the validators of `AUTH_PASSWORD_VALIDATORS` with its user in hand, and reaches the database only as a hash, through `AbstractBaseUser.set_password`. The forms check in `clean` and `_post_clean`, hooks of [Validation: `full_clean`, `cleaned_data` and the errors](../forms/validation.md), and set the password in `save`. `AuthenticationForm` takes its user model from `get_user_model` when the module is imported, and the password forms are handed their user, so these serve any subclass of `AbstractBaseUser`; the creation and change forms are model forms of `User`, which a project with its own user model rewrites or extends (`docs/topics/auth/customizing.txt`).

## `UsernameField`

`UsernameField`, the username's field in the login, creation and change forms, normalizes it to Unicode's NFKC form, as `AbstractBaseUser.normalize_username` does a stored username. A value longer than the field's `max_length` is left alone: normalizing, says the comment, can lengthen a string but never shorten it, so such a value fails anyway, and it is slow enough on Windows to serve a denial of service (`django/contrib/auth/forms.py:UsernameField.to_python`).

## `AuthenticationForm`

`AuthenticationForm` takes the request as its first argument, so the data comes by keyword, `data=`. It passes the request to `authenticate`, for the backends; `LoginView` gives it its own ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](login-views.md)). Its username field is called `"username"` whatever the user model calls its own: `AuthenticationForm.__init__` gives it the `max_length` of the field that `USERNAME_FIELD` names, or 254 where that has none, and its verbose name as the label if none is set (`django/contrib/auth/forms.py:AuthenticationForm.__init__`).

`AuthenticationForm.clean` acts only when both fields passed. It calls `authenticate` with the request, `username=` and `password=`. `None` raises the error that `AuthenticationForm.get_invalid_login_error` makes, code `"invalid_login"`, filed under `"__all__"`; a user goes to `AuthenticationForm.confirm_login_allowed`. `AuthenticationForm.get_user` returns the user kept, or `None`, and `LoginView` passes it to `login` (`django/contrib/auth/forms.py:AuthenticationForm.clean`).

```python
# a shell, with the harbour office's users
>>> from django.contrib.auth.forms import AuthenticationForm
>>> form = AuthenticationForm(data={"username": "nora", "password": "Beagle-1831"})
>>> form.is_valid(), form.get_user()
(False, None)
>>> form.errors.as_data()
{'__all__': [ValidationError(['Please enter a correct username and password. Note that both fields may be case-sensitive.'])]}
```

One message serves a username no user has and a wrong password. `confirm_login_allowed` refuses a user whose `is_active` is false, code `"inactive"`, but under the default backend it never meets one: `ModelBackend.user_can_authenticate` refuses such a user first, and the inactive user with the right password is told what everyone is told (`django/contrib/auth/backends.py:ModelBackend.user_can_authenticate`). The method decides only under a backend that lets inactive users through, such as `AllowAllUsersModelBackend`, as the documentation says, and then only for a right password (`docs/topics/auth/default.txt`):

```python
# a shell, with tomas made inactive
>>> tomas = {"username": "tomas", "password": "Beagle-1831"}
>>> AuthenticationForm(data=tomas).non_field_errors().as_data()[0].code
'invalid_login'
>>> settings.AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.AllowAllUsersModelBackend"]
>>> AuthenticationForm(data=tomas).errors.as_data()
{'__all__': [ValidationError(['This account is inactive.'])]}
```

The admin's `AdminAuthenticationForm` extends `confirm_login_allowed` to refuse a user who is not staff (`django/contrib/admin/forms.py:AdminAuthenticationForm.confirm_login_allowed`) ([The admin](../admin.md)).

## Setting a password: `SetPasswordMixin`

`SetPasswordMixin.create_password_fields` makes the two fields, which keep spaces. The mixin's three steps are called by the form that uses it, at the hooks it chooses (`django/contrib/auth/forms.py:SetPasswordMixin`):

1. `SetPasswordMixin.validate_passwords` files `"password_mismatch"` under the second field when both passed and differ.
2. `SetPasswordMixin.validate_password_for_user` runs `validate_password` on the second field's value with the user, and files what it raises under that field ([Password validation: `validate_password` and the validators](password-validation.md)).
3. `SetPasswordMixin.set_password_and_save` sets the password from the first field and saves the user, unless `commit=False`.

An error takes its field out of `cleaned_data`, so after a mismatch the second step finds nothing: a pair that does not agree is never shown to the validators, and either complaint stands under the confirmation.

```python
# a shell, with nora
>>> from django.contrib.auth.forms import SetPasswordForm
>>> SetPasswordForm(nora, {"new_password1": "password1", "new_password2": "password2"}).errors.as_data()
{'new_password2': [ValidationError(['The two password fields didn’t match.'])]}
>>> SetPasswordForm(nora, {"new_password1": "password1", "new_password2": "password1"}).errors.as_data()
{'new_password2': [ValidationError(['This password is too common.'])]}
```

`SetPasswordForm`, handed the user before the data, runs the first two steps in `clean` and the third in `save`. `PasswordResetConfirmView` uses it at the end of a reset, whose first form, `PasswordResetForm`, mails the link ([Password reset: `PasswordResetTokenGenerator` and the reset views](password-reset.md)). `PasswordChangeForm`, for `PasswordChangeView`, adds `"old_password"`, checked by `PasswordChangeForm.clean_old_password` with `AbstractBaseUser.check_password`: a wrong one is refused under its field with "Your old password was entered incorrectly. Please enter it again.", and the new pair is checked all the same (`django/contrib/auth/forms.py:PasswordChangeForm.clean_old_password`).

## Creating a user: `BaseUserCreationForm` and `UserCreationForm`

`BaseUserCreationForm` is a model form of `User` with the username and the two password fields. It checks the match in `clean` and runs the validators in `_post_clean`, after `BaseModelForm._post_clean` has copied the cleaned values onto the new user, as its comment says; so `UserAttributeSimilarityValidator` compares the password with the username being chosen (`django/contrib/auth/forms.py:BaseUserCreationForm._post_clean`). `BaseUserCreationForm.save` sets the password, then saves the user and its many-to-many values.

The username's uniqueness is the model's: its field is `unique`, and `BaseModelForm.validate_unique` asks the database for a row with that value ([Model forms: `ModelForm` and `fields_for_model`](../forms/model-forms.md)). `UserCreationForm.clean_username` adds a match that ignores case (`"username__iexact"`), and files the model's message for a duplicate, from `Model.unique_error_message`, through `BaseModelForm._update_errors`; it then returns nothing, so `cleaned_data` holds `None` for the username, and the model's own check passes over a field with an error (`django/contrib/auth/forms.py:UserCreationForm.clean_username`). The documentation's reason is confusion between similar usernames (`docs/topics/auth/default.txt`). The base form has only the model's check, an exact match, which on the example's SQLite database finds no "Nora" (`django/db/models/base.py:Model._perform_unique_checks`):

```python
# a shell, with the harbour office's users
>>> from django.contrib.auth.forms import BaseUserCreationForm, UserCreationForm
>>> taken = {"username": "Nora", "password1": "Galley-Proof-77", "password2": "Galley-Proof-77"}
>>> UserCreationForm(taken).errors.as_data()
{'username': [ValidationError(['A user with that username already exists.'])]}
>>> BaseUserCreationForm(taken).is_valid()
True
```

## `SetUnusablePasswordMixin` and the admin's forms

`SetUnusablePasswordMixin` lets a form set an unusable password instead, so that the user cannot log in by password but, says its help text, may through another backend. Its radio choice, `"true"` at first or `"false"`, is replaced in `cleaned_data` by `"set_usable_password"`. False, nothing is checked and saving calls `AbstractBaseUser.set_unusable_password`; true, an empty password field is refused as `"required"`, the fields being optional where the radio is offered, and `SetPasswordMixin` does the rest (`django/contrib/auth/forms.py:SetUnusablePasswordMixin.validate_passwords`). Those forms are the admin's: `AdminUserCreationForm`, a `UserCreationForm` with the radio, and the `AdminPasswordChangeForm` of `django/contrib/auth/forms.py`, which offers it only for a user whose password is usable (`django/contrib/auth/forms.py:AdminPasswordChangeForm.__init__`) ([The admin](../admin.md)).

## `UserChangeForm` and the read-only hash

`UserChangeForm` is a model form of every field of `User`, with the password replaced by a `ReadOnlyPasswordHashField`, which is not required and is disabled. A disabled field cleans its initial value whatever was posted, so the form writes the stored hash back as it was ([A form field: the base class](../forms/fields.md)) (`django/contrib/auth/forms.py:ReadOnlyPasswordHashField`).

Its widget, `ReadOnlyPasswordHashWidget`, draws `"auth/widgets/read_only_password_hash.html"`, which calls the tag `render_password_as_hash`: "No password set." for an empty or unusable string, "Invalid password format or unknown hashing algorithm." where finding the hasher or reading the string raises `ValueError`, otherwise what `BasePasswordHasher.safe_summary` gives for the hasher `identify_hasher` finds, for PBKDF2 the salt and the hash starred after six characters (`django/contrib/auth/templatetags/auth.py:render_password_as_hash`). A button follows, "Reset password", or "Set password" with no usable password, linking to `"../password/"`, which from a user's change page in the admin is the password page that `UserAdmin.get_urls` adds (`django/contrib/auth/admin.py:UserAdmin.get_urls`):

```python
# a shell, with nora's password as the opening page shows it
>>> from django.contrib.auth.forms import UserChangeForm
>>> print(UserChangeForm(instance=nora)["password"])
<div disabled aria-describedby="id_password_helptext" id="id_password">
  <p><strong>algorithm</strong>: <bdi>pbkdf2_sha256</bdi> <strong>iterations</strong>: <bdi>1800000</bdi> <strong>salt</strong>: <bdi>RVCWTs****************</bdi> <strong>hash</strong>: <bdi>KqCZK8**************************************</bdi></p>
  <p><a role="button" class="button" href="../password/">Reset password</a></p>
</div>
```
