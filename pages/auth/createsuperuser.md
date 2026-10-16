---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Creating a superuser: createsuperuser and changepassword

The createsuperuser command makes a user with `is_staff` and `is_superuser` set: it asks at a terminal for each field the user model requires, or with `--noinput` reads them from options and environment variables, and hands them to the manager's `create_superuser`. The changepassword command asks twice for a new password for an existing user, validates it with `validate_password`, and saves it.

A new project has no user, and the admin, where users are added, admits only an active staff user ([The admin](../admin.md)) (`django/contrib/admin/sites.py:AdminSite.has_permission`). createsuperuser makes the first from the command line, for whatever model `AUTH_USER_MODEL` names, so it knows of the fields only what the model declares: the field named by `USERNAME_FIELD`, those of `AbstractBaseUser.REQUIRED_FIELDS`, and whether there is a field called `"password"`. Each model field cleans its own value, and the model's manager makes the user. It has two kinds of caller: a person at a terminal, who can be asked again after a mistake, and a script, which cannot, and must give every answer in advance.

## The options come from the user model

createsuperuser looks up the user model in its `__init__`, before the parser is built, so that `add_arguments` can name the options after the model: one for `USERNAME_FIELD`, `--username` for `User`, and one for each field of `REQUIRED_FIELDS`, so `User` has `--email`, `AbstractUser.REQUIRED_FIELDS` being `["email"]`. A many-to-many field's option may be repeated; one with a through model of its own is refused with a `CommandError`. Beside these stand `--noinput` and `--database` (`django/contrib/auth/management/commands/createsuperuser.py:Command.add_arguments`). Its `execute` keeps a stream, standard input unless a caller in code passes the stealth option `"stdin"`; the command never reads from it, and only asks it whether it is a terminal ([`call_command`: a command called from code](../commands/call-command.md#stealth-options)). If the model has a field called `"password"`, the data starts with a password of `None`, meaning none given yet; a model without one is never asked for a password (`django/contrib/auth/management/commands/createsuperuser.py:Command.handle`).

## At a terminal

The interactive mode first checks for a terminal. When the stream is not a TTY it raises `NotRunningInTTYException`, which `handle` catches at its end: it writes that creation was skipped and ends without an error, so a script that forgets `--noinput` and runs without a terminal makes no user and does not fail (`django/contrib/auth/management/commands/createsuperuser.py:Command.handle`).

The default username is the name of the account the process runs under, from `get_system_username`, reduced to ASCII without spaces and in lower case, and offered only if `User`'s username field accepts it and no user has it. When `AUTH_USER_MODEL` names another model there is none, since, a comment says, no assumption can be made about the username then (`django/contrib/auth/management/__init__.py:get_default_username`).

The username is asked for first, unless an option gave a valid one, then each required field no option gave. `Command.get_input_data` reads an answer with `input`, puts the default in place of an empty one, and has the model field clean it; an error is written and the question asked again (`django/contrib/auth/management/commands/createsuperuser.py:Command.get_input_data`). For a unique username, `Command._validate_username` also asks the manager's `get_by_natural_key` whether it is taken. A foreign key is answered with the key of a row that must exist (`django/db/models/fields/related.py:ForeignKey.validate`).

The password comes last, typed twice with `getpass.getpass`. Two that differ, or one that is blank, are refused before any validator sees them. Then `validate_password` runs the validators of `AUTH_PASSWORD_VALIDATORS` against a user that is never saved, made from the answers, so that a validator comparing the password with the username or the email has them. When a validator refuses, the command asks whether to create the user anyway, and "y" keeps the password ([Password validation: `validate_password` and the validators](password-validation.md)).

The office's new harbour master, under a system account named Maren Visser, met each refusal in turn; the passwords typed are not echoed:

```text
Username (leave blank to use 'marenvisser'): piet
Error: That username is already taken.
Username (leave blank to use 'marenvisser'):
Email address: maren-at-harbour
Error: Enter a valid email address.
Email address: maren@harbour.example
Password:
Password (again):
Error: Your passwords didn't match.
Password:
Password (again):
Error: Blank passwords aren't allowed.
Password:
Password (again):
The password is too similar to the username.
Bypass password validation and create user anyway? [y/N]: N
Password:
Password (again):
Superuser created successfully.
```

## With `--noinput`

With `--noinput` each value comes from its option or else from an environment variable, `"DJANGO_SUPERUSER_"` and the field's name in capitals. A missing value is a `CommandError` naming the option to use; a username taken or invalid, or a value its field will not clean, is a `CommandError` with the error's message. A field that may be blank may be given empty, and is then left out (`django/contrib/auth/management/commands/createsuperuser.py:Command.handle`).

The password comes only from `"DJANGO_SUPERUSER_PASSWORD"`, and in this mode nothing calls `validate_password`. Without the variable the password stays `None`, which `make_password` turns into an unusable one, and the superuser cannot log in until given a password ([Password hashing: `make_password` and the hashers](hashers.md)). With the example's validators, which refuse "12345678":

```python
>>> os.environ["DJANGO_SUPERUSER_EMAIL"] = "joris@harbour.example"
>>> os.environ["DJANGO_SUPERUSER_PASSWORD"] = "12345678"
>>> call_command("createsuperuser", interactive=False, username="joris")
Superuser created successfully.
>>> User.objects.get(username="joris").check_password("12345678")
True
>>> del os.environ["DJANGO_SUPERUSER_PASSWORD"]
>>> call_command("createsuperuser", interactive=False, username="anna")
Superuser created successfully.
>>> User.objects.get(username="anna").has_usable_password()
False
```

## The manager makes the user

Both modes end in one call: the default manager, bound to the `--database` alias, is asked to `create_superuser` with the values as keyword arguments. `UserManager.create_superuser` sets `is_staff=True` and `is_superuser=True`, raises `ValueError` if told otherwise, and makes the user as `UserManager.create_user` does (`django/contrib/auth/models.py:UserManager.create_superuser`). A custom model's manager must accept these keywords: the username field, each required field and the password ([The user model: `AbstractBaseUser`, `User` and `AUTH_USER_MODEL`](user-model.md)). `UserManager.create_superuser` validates no password; the documentation gives two reasons: developers, not users, work at that level, and a model's validation does not run as it is created (`docs/topics/auth/passwords.txt`).

## changepassword

changepassword looks the user up by `USERNAME_FIELD`, under the name given or else the system account's from `getpass.getuser`, taken as it is; a name no user has is a `CommandError` (`django/contrib/auth/management/commands/changepassword.py:Command.handle`). It asks for the password twice, for up to three tries. An empty answer ends the command at once. Two answers that differ cost a try; two that match go to `validate_password` with the real user, and a refusal costs a try, with no way past it. After three failures the command gives up with a `CommandError`; otherwise it calls `AbstractBaseUser.set_password` and saves, and `AbstractBaseUser.save` tells the validators through `password_changed`.

Run for nora, it also ends nora's sessions on the site: each holds a hash made from the stored password, and `django.contrib.auth.get_user` empties a session whose hash no longer matches the next time a request reads its user from it ([The user of a request: `login`, `logout` and `AuthenticationMiddleware`](login.md)).
