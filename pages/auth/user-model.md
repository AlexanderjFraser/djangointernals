---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`

The user model is the model that `AUTH_USER_MODEL` names, `User` unless a project names its own. `django.contrib.auth` builds it in layers, `AbstractBaseUser`, `PermissionsMixin` and `AbstractUser`, and `get_user_model` returns whichever class is in use.

The rest of `django.contrib.auth` works with whatever model that is, but for `BaseUserCreationForm`, `UserChangeForm` and the admin's `UserAdmin`, which name `User` itself. It asks little of the class and reads the rest from it: which field identifies a user, which holds the address, what a new superuser must be given.

| class | adds |
|---|---|
| `AbstractBaseUser` | the password, the last login, and the methods every user model answers |
| `PermissionsMixin` | the superuser flag, groups and permissions |
| `AbstractUser` | a username, names, an address, the staff and active flags, the date joined, and `UserManager` |
| `User` | only the swappable option |

*The layers of the user model, in `django/contrib/auth/base_user.py` and `django/contrib/auth/models.py`.*

## `AbstractBaseUser`

`AbstractBaseUser` is an abstract model with two fields: `password`, 128 characters for the encoded hash, and `last_login`, which may be null. `AbstractBaseUser.is_active` is a class attribute, true, so a model that does not make it a field has every user active (`django/contrib/auth/base_user.py:AbstractBaseUser`). Its module, by its docstring, can be imported without `django.contrib.auth` installed.

The class reads two names it does not declare. A subclass names the field that identifies a user, as `AbstractUser.USERNAME_FIELD` names `"username"`; `AbstractBaseUser.get_username` returns that field's value, and `__str__` and `AbstractBaseUser.natural_key` are built on it. `BaseUserManager.get_by_natural_key`, a `get` on the same field, is how `ModelBackend` finds the user a login names ([Authenticating: `authenticate` and the backends](authenticating.md)) (`django/contrib/auth/base_user.py:BaseUserManager.get_by_natural_key`). `AbstractBaseUser.get_email_field_name` returns `EMAIL_FIELD`, or `"email"` where the class sets none. `AbstractBaseUser.REQUIRED_FIELDS`, empty here, lists the fields createsuperuser also asks for ([Creating a superuser: createsuperuser and changepassword](createsuperuser.md)).

`AbstractBaseUser.clean` passes the username through `AbstractBaseUser.normalize_username`, which applies Unicode's NFKC normalization so that, as the documentation puts it, visually identical characters with different code points count as identical (`django/contrib/auth/base_user.py:AbstractBaseUser.normalize_username`, `docs/topics/auth/customizing.txt`).

`AbstractBaseUser.is_authenticated` is always true and `AbstractBaseUser.is_anonymous` always false: they tell a user from an `AnonymousUser`; by the documentation, `is_authenticated` says nothing of permissions, of `is_active` or of the session. Both are properties, and `check_user_model` refuses a model where either is a method.

## The password on the model

`AbstractBaseUser.set_password` stores what `make_password` makes of the raw password, and does not save. It keeps the raw password in `AbstractBaseUser._password` so that, a comment says, it can be passed to `password_changed` after the model is saved: `AbstractBaseUser.save` saves, then calls `password_changed` if `_password` is set, and clears it ([Password validation: `validate_password` and the validators](password-validation.md)) (`django/contrib/auth/base_user.py:AbstractBaseUser.save`). Neither method validates the password.

`AbstractBaseUser.check_password` hands the raw password and the stored string to `django.contrib.auth.hashers.check_password`, with a setter to call when the string should be made again. The setter calls `set_password`, clears `_password`, since by its comment a hash upgrade is not a password change, and saves the `password` field alone ([Password hashing: `make_password` and the hashers](hashers.md)) (`django/contrib/auth/base_user.py:AbstractBaseUser.check_password`).

`AbstractBaseUser.set_unusable_password` stores `make_password(None)`, a string beginning with `"!"` that no password matches, and `AbstractBaseUser.has_usable_password` tells it with `is_password_usable` (`django/contrib/auth/base_user.py:AbstractBaseUser.set_unusable_password`). `AbstractBaseUser.get_session_auth_hash` is an HMAC of the `password` field, which `login` keeps in the session so that a changed password ends the user's other sessions ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)).

## The managers: `BaseUserManager` and `UserManager`

`BaseUserManager.normalize_email` strips an address that has an `"@"` and lowercases what follows the last one, leaving the local part as it was; a missing address becomes `""` (`django/contrib/auth/base_user.py:BaseUserManager.normalize_email`).

`UserManager` is `AbstractUser`'s manager, and assumes its fields. `UserManager._create_user_object` refuses an empty username, normalizes the address, and normalizes the username with the class it asks the registry for by the model's label, not the manager's own model, so that, a comment says, the method can be used in migrations. It sets the password with `make_password`, not `set_password`, so no `password_changed` follows (`django/contrib/auth/models.py:UserManager._create_user_object`). `UserManager.create_user` defaults the staff and superuser flags to false; `UserManager.create_superuser` defaults them to true and refuses either set otherwise. `UserManager.with_perm` asks a backend for the users that have a permission ([Permissions: `Permission`, groups and `has_perm`](permissions.md)).

```text
User.objects.normalize_email('Nora@Harbour.EXAMPLE')  ->  'Nora@harbour.example'
User.objects.normalize_email(None)  ->  ''
User.normalize_username('ｎｏｒａ')  ->  'nora'
User.objects.create_superuser(..., is_staff=False)  ->  ValueError: Superuser must have is_staff=True.
```

## `PermissionsMixin`, `AbstractUser` and `User`

`PermissionsMixin` adds `is_superuser` and two many-to-many fields, `groups` to the group model and `user_permissions` to `Permission`, each with the related name `"user_set"` (`django/contrib/auth/models.py:PermissionsMixin`). Its methods, `PermissionsMixin.has_perm` and the rest, ask the backends, though `has_perm` and `PermissionsMixin.has_module_perms` first answer yes for an active superuser ([Permissions: `Permission`, groups and `has_perm`](permissions.md)).

`AbstractUser` inherits both and adds `username`, unique and at most 150 characters; `first_name`, `last_name` and `email`, which may be blank; `is_staff`; `is_active`, now a field; and `date_joined`. It sets `USERNAME_FIELD`, `EMAIL_FIELD` and `REQUIRED_FIELDS`, the last to `["email"]`, makes `UserManager` its `objects`, and adds the address's normalization to `AbstractUser.clean`. `AbstractUser.email_user` calls `send_mail` with the user's address (`django/contrib/auth/models.py:AbstractUser`).

The username is validated by `UnicodeUsernameValidator`, which allows word characters and `"."`, `"@"`, `"+"` and `"-"`; `ASCIIUsernameValidator` is the same pattern with the ASCII flag, and refuses "tomás" (`django/contrib/auth/validators.py`).

> **Trap.** `AbstractUser.username_validator` is read only in the class body, as `username` is made. A subclass that sets it to `ASCIIUsernameValidator` keeps the Unicode validator unless it declares `username` again.

`User` adds to `AbstractUser` only a `Meta` that sets the swappable option to `"AUTH_USER_MODEL"` (`django/contrib/auth/models.py:User`).

## `AnonymousUser`

`AnonymousUser` is not a model. Its id and primary key are `None`, its username `""`, its staff, active and superuser flags false, and its groups and permissions `EmptyManager` objects, whose querysets are empty. Saving, deleting, and setting or checking a password raise `NotImplementedError`. Any two are equal, every one hashes to 1, and `int` of one raises `TypeError`, asking whether it is being used in place of a user (`django/contrib/auth/models.py:AnonymousUser`). `AnonymousUser.has_perm` asks the backends, with no superuser's shortcut.

## Swapping the model: `AUTH_USER_MODEL` and `get_user_model`

`get_user_model` asks the registry for the model `AUTH_USER_MODEL` names with `require_ready=False` (`django/contrib/auth/__init__.py:get_user_model`), which needs only the applications loaded, not all their models, and imports the named application's models itself if they are not yet (`django/apps/registry.py:Apps.get_model`). So another application's models module can call it at import; the user model's own module cannot, before the class exists. A value that is not two names joined by a dot, and a model that is not installed, each become `ImproperlyConfigured`. `AuthConfig.ready` calls `get_user_model`, so a wrong value stops `django.setup` (`django/contrib/auth/apps.py:AuthConfig.ready`).

The backends, the forms, the views, changepassword and the mod_wsgi handler keep the class they got at import as `UserModel` (`django/contrib/auth/backends.py:UserModel`); only a receiver of `setting_changed`, which `override_settings` sends, binds the five again (`django/test/signals.py:user_model_swapped`).

The swappable option lets another model take `User`'s place. When the setting names another model, `User`'s `Options.swapped` is that name (`django/db/models/options.py:Options.swapped`): migrate makes no table for it, the registry's lists leave it out (`django/apps/config.py:AppConfig.get_models`), and its manager refuses to be read ([The options: what a model keeps as `_meta`](../models/options.md)). A relation to the user model names the setting, and its migration depends on it ([Relations: a field, its rel and the class at the other end](../models/relations.md)). The documentation asks that it be set before the first migrate (`docs/topics/auth/customizing.txt`).

The office could identify staff by address, with `"harbour.staff"` in `INSTALLED_APPS` and `AUTH_USER_MODEL = "staff.Officer"`:

```python
# harbour/staff/models.py
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class Officer(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    objects = BaseUserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]
```

After migrate, and nora saved with the address `normalize_email` made of "Nora@Harbour.EXAMPLE":

```text
get_user_model()      <class 'harbour.staff.models.Officer'>
User._meta.swapped    'staff.Officer'
User.objects          AttributeError: Manager isn't available; 'auth.User' has been swapped for 'staff.Officer'
auth_*, staff_*       auth_group, auth_group_permissions, auth_permission, staff_officer, staff_officer_groups, staff_officer_user_permissions
nora.get_username()   'Nora@harbour.example'
```

## What `check_user_model` requires

`AuthConfig.ready` registers `check_user_model` among the model checks. It makes an instance with no arguments, and requires that `REQUIRED_FIELDS` be a list or tuple (`"auth.E001"`) and not hold `USERNAME_FIELD` (`"auth.E002"`); that the username field be unique, or the only field of a unique constraint with no condition, an error (`"auth.E003"`) when `AUTHENTICATION_BACKENDS` is `ModelBackend` alone and otherwise a warning (`"auth.W004"`); and that `is_anonymous` and `is_authenticated` not be callable (`"auth.C009"`, `"auth.C010"`, critical) (`django/contrib/auth/checks.py:check_user_model`). Had the office left the address not unique, listed it in `REQUIRED_FIELDS` too, and written `is_authenticated` as a method, the check would have said:

```text
auth.E002 The field named as the 'USERNAME_FIELD' for a custom user model must not be included in 'REQUIRED_FIELDS'.
auth.E003 'Officer.email' must be unique because it is named as the 'USERNAME_FIELD'.
auth.C010 <class 'harbour.staff.models.Officer'>.is_authenticated must be an attribute or property rather than a method. Ignoring this is a security issue as anonymous users will be treated as authenticated!
```
