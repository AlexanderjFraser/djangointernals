---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Password validation: `validate_password` and the validators

`validate_password` decides whether a new password is good enough: it runs every validator that `AUTH_PASSWORD_VALIDATORS` lists and gathers their refusals into one `ValidationError`. Beside it, `django/contrib/auth/password_validation.py` holds the four validators Django ships, their help texts, and `password_changed`, which tells them a password was set.

A **password validator** is an object of any class with two methods, `validate(password, user=None)`, which raises `ValidationError` to refuse, and `get_help_text()`, which states the rule; it may have a third, `password_changed(password, user=None)` (`docs/topics/auth/passwords.txt`). Validation is asked where a person chooses a password, never by the user model.

## The validators of a process

`AUTH_PASSWORD_VALIDATORS` is a list of dictionaries, each naming a class by its dotted path under `"NAME"`, with keyword arguments under `"OPTIONS"`. It is empty by default, so a project that leaves it validates nothing (`django/conf/global_settings.py`). The settings startproject writes list Django's four without options: `UserAttributeSimilarityValidator`, `MinimumLengthValidator`, `CommonPasswordValidator`, `NumericPasswordValidator` (`django/conf/project_template/project_name/settings.py-tpl`).

`get_password_validators` imports each class with `import_string` and calls it with the options. A failed import, a class missing from its module included, becomes `ImproperlyConfigured`, as does a name that is not callable (`django/contrib/auth/password_validation.py:get_password_validators`). `get_default_password_validators` calls it with the setting under `functools.cache`, once in a process. In Django only the test framework empties the cache, when a test overrides the setting ([Overriding settings](../startup/overrides.md)) (`django/test/signals.py:auth_password_validators_changed`). So the setting's `CommonPasswordValidator` reads its file once.

## `validate_password`

`validate_password` asks every validator of the setting, or of a list it is given, in order, with the password and the user. A `ValidationError` from one is kept and the next is asked; any other exception passes up. If any refused, it raises one `ValidationError` of the list, so every reason comes at once, each with its code ([Django's exceptions: `django.core.exceptions`](../utils/exceptions.md)) (`django/contrib/auth/password_validation.py:validate_password`). With startproject's four, for nora (nora@harbour.example) and for no user:

```text
# a run: validate_password, and the messages of the error it raised
"Endeavour-1768", nora: accepted
"Nora-17", nora:
    The password is too similar to the username.
    This password is too short. It must contain at least 8 characters.
"Harbour-Nora", nora:
    The password is too similar to the email address.
"  LIGHTHOUSE  ", nora:
    This password is too common.
"17681768", nora:
    This password is entirely numeric.
"Harbour-Nora", no user: accepted
```

Without a user, the similarity validator accepts anything.

## The four validators

`MinimumLengthValidator` refuses a password shorter than `min_length=8` or the options' length, with the code `"password_too_short"` (`django/contrib/auth/password_validation.py:MinimumLengthValidator`). `NumericPasswordValidator` refuses one made only of digits, `"password_entirely_numeric"`; it asks `str.isdigit`, which is true of other scripts' digits too (`django/contrib/auth/password_validation.py:NumericPasswordValidator`).

`CommonPasswordValidator` refuses a password found in a list, `"password_too_common"`. Django's, `"common-passwords.txt.gz"` beside the module, is lowercased and deduplicated, and the class's docstring credits it to Royce Williams. The validator reads the whole file into a set when it is made, as gzip or else as plain text, and compares the password lowercased and stripped of surrounding white space, as "  LIGHTHOUSE  " shows (`django/contrib/auth/password_validation.py:CommonPasswordValidator`).

`UserAttributeSimilarityValidator` refuses a password too like the user's own details: the attributes of `UserAttributeSimilarityValidator.DEFAULT_USER_ATTRIBUTES`, `"username"`, `"first_name"`, `"last_name"` and `"email"`, unless the options name others, skipping one missing, empty or not a string. Each value is compared whole and in its parts split at non-word characters, so "Harbour-Nora" fell to the harbour of nora@harbour.example. The measure is `difflib.SequenceMatcher.quick_ratio` of the two lowercased, which counts the characters they share in any order: harbour-nora against harbour scores 0.74, an anagram of a username 1.0. At `max_similarity=0.7` or above, or the options' limit (at least 0.1), the password is refused with `"password_too_similar"` and the field's verbose name, or the attribute's name (`django/contrib/auth/password_validation.py:UserAttributeSimilarityValidator.validate`). A part a tenth of the password's length or less, too short to reach the limit, is not measured (at a limit of 0.2 or below, only a shorter part), which the docstring of `exceeds_maximum_length_ratio` says avoids the potentially expensive sequence matching (`django/contrib/auth/password_validation.py:exceeds_maximum_length_ratio`).

## The help texts

`password_validators_help_texts` returns each validator's `get_help_text()` in the setting's order, sentences such as "Your password must contain at least 8 characters." `password_validators_help_text_html` puts them, escaped, in an HTML list. It is wrapped by `lazy`: the password forms take it as a help text as their classes are defined, and it is built at each rendering ([Lazy values: `lazy`, `Promise` and `keep_lazy`](../utils/lazy.md)) (`django/contrib/auth/password_validation.py:password_validators_help_text_html`, `django/contrib/auth/forms.py:SetPasswordMixin.create_password_fields`).

## `password_changed`

`AbstractBaseUser.set_password` keeps the raw password on the instance as `AbstractBaseUser._password`. `AbstractBaseUser.save`, once the row is written, hands it to `password_changed` with the user and forgets it, so the hook runs once, at the first save after a password is set, even a save that does not write the password (`django/contrib/auth/base_user.py:AbstractBaseUser.save`). `password_changed` calls the method of that name on each validator that has one; none of Django's four has (`django/contrib/auth/password_validation.py:password_changed`). The documentation's example is a validator refusing a password used before (`docs/topics/auth/passwords.txt`).

Two hashes are stored without it. `AbstractBaseUser.check_password`, upgrading a hash, clears the raw password before it saves, its comment saying an upgrade is not a password change; `UserManager.create_user` hashes with `make_password`, not `set_password` (`django/contrib/auth/base_user.py:AbstractBaseUser.check_password`, `django/contrib/auth/models.py:UserManager._create_user_object`).

## Who asks

The forms ask through `SetPasswordMixin.validate_password_for_user`, which puts the refusals on the second password field. `BaseUserCreationForm._post_clean` asks once the form's values are on the new user, so the username being chosen is compared; `SetPasswordForm.clean` (and so `PasswordChangeForm`) and `AdminPasswordChangeForm.clean` ask too, the admin's forms only when the password is to be usable ([The authentication forms: `AuthenticationForm` and the password forms](user-forms.md)) (`django/contrib/auth/forms.py:SetPasswordMixin.validate_password_for_user`, `django/contrib/auth/forms.py:SetUnusablePasswordMixin.validate_password_for_user`). createsuperuser asks only when it prompts, against an unsaved user made from the answers, and offers to go on anyway; changepassword asks whenever the two entries match, for three tries at most ([Creating a superuser: createsuperuser and changepassword](createsuperuser.md)).

`AbstractBaseUser.set_password`, `UserManager.create_user` and `UserManager.create_superuser` never ask, nor does createsuperuser when it takes `"DJANGO_SUPERUSER_PASSWORD"` without prompting. The documentation gives two reasons: developers, not users, work at that level, and a model's validation does not run as it is created (`docs/topics/auth/passwords.txt`).
