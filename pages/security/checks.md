---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The security checks

The security checks are the system checks in `django/core/checks/security/`, tagged `"security"`: functions that read the settings and report one that is unsafe on a public site or cannot work, from `settings.DEBUG` left on to a `SECRET_KEY` that startproject made. Most are deployment checks, which run only when the check command is given `--deploy`.

A setting that is right on a developer's machine is often wrong on a public server: debugging on, cookies sent over plain HTTP, no Strict-Transport-Security. The checks of such settings are, in the documentation's words, "only relevant in a deployment setting", and run only when asked for (`docs/ref/django-admin.txt`). Each reads settings, and one also imports the view a setting names. A middleware counts as installed when its dotted path, as a string, is in `MIDDLEWARE` (`django/core/checks/security/base.py:_security_middleware`). A project that installs a subclass of `SecurityMiddleware` under a path of its own gets `"security.W001"`, and the checks of that middleware's settings fall silent.

## Registered for deployment

The package's modules are imported by `django/core/checks/__init__.py`, so their functions are registered as Django starts, each with `Tags.security`. All but three also have `deploy=True`, which files them among the deployment checks that only the check command given `--deploy` runs ([The system checks](../commands/checks.md)) (`django/core/checks/registry.py:CheckRegistry.register`).

The three, `check_csp_settings`, `check_csp_nonce_context_processor` and `check_csrf_failure_view`, run with the ordinary checks, `--deploy` or not. Each looks for a fault on any machine: a policy that is not a dictionary, a nonce no template is given, a failure view that cannot be imported or called (`django/core/checks/security/csrf.py:check_csrf_failure_view`).

The harbour office's settings ([Security](../security.md)), with `ALLOWED_HOSTS` naming harbour.example and a long `SECRET_KEY`, pass those three. Under `--deploy`, limited to this tag, a run gave three warnings:

```text
$ python manage.py check --deploy --tag security
System check identified some issues:

WARNINGS:
?: (security.W005) You have not set the SECURE_HSTS_INCLUDE_SUBDOMAINS setting to True. Without this, your site is potentially vulnerable to attack via an insecure connection to a subdomain. Only set this to True if you are certain that all subdomains of your domain should be served exclusively via SSL.
?: (security.W016) You have 'django.middleware.csrf.CsrfViewMiddleware' in your MIDDLEWARE, but you have not set CSRF_COOKIE_SECURE to True. Using a secure-only CSRF cookie makes it more difficult for network traffic sniffers to steal the CSRF token.
?: (security.W021) You have not set the SECURE_HSTS_PRELOAD setting to True. Without this, your site cannot be submitted to the browser preload list.

System check identified 3 issues (0 silenced).
```

Two exist only because the site sends Strict-Transport-Security: with `SECURE_HSTS_SECONDS` at 0, a run gave `"security.W004"` in their place. `CSRF_COOKIE_SECURE` is false unless a project sets it.

## The checks by identifier

Where a row says "with" a middleware, the check is silent unless that middleware is installed (`django/core/checks/security/base.py:check_sts`).

| check | reported when |
|---|---|
| `"security.W001"`, `"security.W002"`, `"security.W003"` | `SecurityMiddleware`, `XFrameOptionsMiddleware` or `CsrfViewMiddleware` is not installed |
| `"security.W004"` | `SECURE_HSTS_SECONDS` is 0 or another false value; with `SecurityMiddleware` |
| `"security.W005"`, `"security.W021"` | `SECURE_HSTS_INCLUDE_SUBDOMAINS` or `SECURE_HSTS_PRELOAD` is not `True`; with `SecurityMiddleware` and `SECURE_HSTS_SECONDS` set |
| `"security.W006"`, `"security.W008"` | `SECURE_CONTENT_TYPE_NOSNIFF` or `SECURE_SSL_REDIRECT` is not `True`; with `SecurityMiddleware` |
| `"security.W009"`, `"security.W025"` | `SECRET_KEY`, or a key in `SECRET_KEY_FALLBACKS`, fails the rule for a key |
| `"security.W010"` to `"security.W015"` | `SESSION_COOKIE_SECURE` or `SESSION_COOKIE_HTTPONLY` is not `True`; with the sessions application or `SessionMiddleware` |
| `"security.W016"` | `CSRF_COOKIE_SECURE` is not `True`; with `CsrfViewMiddleware`, unless `CSRF_USE_SESSIONS` |
| `"security.W018"`, `"security.W020"` | `settings.DEBUG` is true; `ALLOWED_HOSTS` is empty |
| `"security.W019"` | `X_FRAME_OPTIONS` is not `"DENY"`; with `XFrameOptionsMiddleware` |
| `"security.W022"`, `"security.E023"` | `SECURE_REFERRER_POLICY` is `None`, or names a policy that does not exist; with `SecurityMiddleware` |
| `"security.E024"` | `SECURE_CROSS_ORIGIN_OPENER_POLICY` is neither `None` nor a valid value; with `SecurityMiddleware` |
| `"security.E026"` | `SECURE_CSP` or `SECURE_CSP_REPORT_ONLY` is neither `None` nor a dictionary |
| `"security.W027"` | a policy uses `CSP.NONCE` and no template engine has the `csp` context processor; with `ContentSecurityPolicyMiddleware` |
| `"security.E101"`, `"security.E102"` | `CSRF_FAILURE_VIEW` cannot be called with a request and a reason, or importing it raises `ImportError` |

*The security checks. All but the last three rows are deployment checks.*

"Not `True`" is meant exactly: the checks compare with `is True`, so a run with `CSRF_COOKIE_SECURE = 1`, which sets the cookie's flag all the same, still gave `"security.W016"`.

## The rule for a key

`_check_secret_key` accepts a key of at least 50 characters, with at least 5 different ones, that does not begin with `"django-insecure-"`. `check_secret_key` applies it to `SECRET_KEY`, and warns of an empty key too, since reading one raises `ImproperlyConfigured`; `check_secret_key_fallbacks` applies it to each of `SECRET_KEY_FALLBACKS`, naming its index (`django/core/checks/security/base.py:_check_secret_key`).

The prefix marks a key startproject wrote: startproject imports `SECRET_KEY_INSECURE_PREFIX` from the checks and puts it before 50 characters from `get_random_secret_key`, so its key is long enough and fails on the prefix alone (`django/core/management/commands/startproject.py:Command.handle`). What the key is for is in [Secret keys and `django.utils.crypto`](keys.md).

## The cookies' checks

The session checks have three warnings each: one for the application in `INSTALLED_APPS`, one for `SessionMiddleware` in `MIDDLEWARE`, and one, naming neither, that replaces the two when both are found (`django/core/checks/security/sessions.py:check_session_cookie_secure`). `SESSION_COOKIE_HTTPONLY` is true by default, so left alone the two settings give only the secure flag's warning.

`"security.W016"` is silent when `CSRF_USE_SESSIONS` is true. The CSRF secret is then kept in the session ([The CSRF secret and its token](csrf-token.md)), whose cookie the session checks cover (`django/core/checks/security/csrf.py:check_csrf_cookie_secure`).

## The failure view and the nonce

`check_csrf_failure_view` imports `CSRF_FAILURE_VIEW` and binds the view's signature to one positional argument and a keyword argument named reason, as the CSRF check calls it ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware._reject`). A view that does not bind gives `"security.E101"`; it is never called (`django/core/checks/security/csrf.py:check_csrf_failure_view`).

> **Trap.** `"security.E102"` is given only for an `ImportError`. A path whose module imports but lacks the name, or names a module missing from a package that imports, makes `get_callable` raise `ViewDoesNotExist`, which the check does not catch: in a run, it passed out of `CheckRegistry.run_checks` (`django/urls/utils.py:get_callable`).

`check_csp_nonce_context_processor` looks through each policy's values for `CSP.NONCE`, and through `TEMPLATES` for an entry whose `"OPTIONS"` give `"django.template.context_processors.csp"` among their `"context_processors"`. Without the processor the templates are not given the nonce, and, the warning says, the protection does not take effect ([Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](csp.md)) (`django/core/checks/security/base.py:_csp_context_processor_configured`).

> **Changed in 6.1.** `"security.W027"` is new.
