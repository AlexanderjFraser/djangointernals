---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The security checks

The security checks are the system checks in `django/core/checks/security/`, tagged `"security"`: functions that read the settings and report one that is unsafe on a public site or cannot work, from `settings.DEBUG` left on to a `SECRET_KEY` that startproject made. Most are deployment checks, which run only when the check command is given `--deploy`.

A setting that is right on a developer's machine is often wrong on a public server: debugging on, cookies sent over plain HTTP, no Strict-Transport-Security. A check of such a setting would warn on a developer's machine, and so waits for a run that asks for it; a check of a setting that cannot work on any machine does not wait. Each check reads settings, and one also imports the view a setting names.

## The deployment checks and the three others

The security checks are registered when `django.core.checks` imports the modules that define them, each with `Tags.security`, and all but three with `deploy=True` as well, which files them among the deployment checks that only the check command given `--deploy` runs ([The system checks](../commands/checks.md)) (`django/core/checks/__init__.py`, `django/core/checks/registry.py:CheckRegistry.register`).

The three others run with or without `--deploy`, since each looks for a setting that cannot work on any machine. `check_csp_settings` gives `"security.E026"` for a policy that is not a dictionary, such as `SECURE_CSP = "default-src 'self'"`, and an error is by default enough for `BaseCommand.check` to raise `SystemCheckError`, with the report as its message (`django/core/checks/security/base.py:check_csp_settings`, `django/core/management/base.py:BaseCommand.check`).

`check_csp_nonce_context_processor`, with `ContentSecurityPolicyMiddleware` installed, looks through each policy's values for `CSP.NONCE`, and through `TEMPLATES` for an entry whose `"OPTIONS"` give `"django.template.context_processors.csp"` among their `"context_processors"`. That processor puts the nonce in a template's context, and `{% csp_nonce_attr %}` writes none where the context has none ([Content Security Policy and the nonce](csp.md)) (`django/core/checks/security/base.py:check_csp_nonce_context_processor`, `django/template/context_processors.py:csp`, `django/utils/csp.py:nonce_attr`).

> **New in 6.1.** Django 6.1 added `check_csp_nonce_context_processor` and its warning, `"security.W027"`: under 6.0 a policy that names `CSP.NONCE` passes the checks whether a template is given the nonce or not (`docs/releases/6.1.txt`).

`check_csrf_failure_view` imports `CSRF_FAILURE_VIEW` and, without calling the view, tests whether its signature accepts one positional argument and a keyword argument named reason, as the CSRF check passes them ([The CSRF check: `CsrfViewMiddleware.process_view`](csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware._reject`). A view whose signature does not gives `"security.E101"` (`django/core/checks/security/csrf.py:check_csrf_failure_view`).

> **Trap.** `"security.E102"` is given only for an `ImportError`. A path whose module imports but lacks the name, or names a module missing from a package that imports, makes `get_callable` raise `ViewDoesNotExist`, which the check does not catch. The exception passes out of `CheckRegistry.run_checks` and out of the command: a `CSRF_FAILURE_VIEW` of `"django.views.csrf.no_such_view"` ends a run of the checks with it in place of a report (`django/urls/utils.py:get_callable`, `django/core/checks/security/csrf.py:check_csrf_failure_view`).

## What `--deploy` reports

The harbour's settings ([Security](../security.md)), with `ALLOWED_HOSTS` set to `["harbour.example"]` and a `SECRET_KEY` of 65 characters, pass the three that run without `--deploy`, and the deployment checks give three warnings. Two are there only because the site sends Strict-Transport-Security: once `SECURE_HSTS_SECONDS` is set, `"security.W005"` and `"security.W021"` ask for its two companions, `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD`. The third, `"security.W016"`, is the CSRF cookie, which is not marked secure unless a project sets `CSRF_COOKIE_SECURE`: the harbour's is sent with no Secure attribute (`django/core/checks/security/base.py:check_sts_include_subdomains`, `django/core/checks/security/base.py:check_sts_preload`, `django/conf/global_settings.py:CSRF_COOKIE_SECURE`).

```text recording=security
check --deploy --tag security, under the harbour's settings
    $ python manage.py check --deploy --tag security
    stderr | System check identified some issues:
    stderr |
    stderr | WARNINGS:
    stderr | ?: (security.W005) You have not set the SECURE_HSTS_INCLUDE_SUBDOMAINS setting to True. Without this, your site is potentially vulnerable to attack via an insecure connection to a subdomain. Only set this to True if you are certain that all subdomains of your domain should be served exclusively via SSL.
    stderr | ?: (security.W016) You have 'django.middleware.csrf.CsrfViewMiddleware' in your MIDDLEWARE, but you have not set CSRF_COOKIE_SECURE to True. Using a secure-only CSRF cookie makes it more difficult for network traffic sniffers to steal the CSRF token.
    stderr | ?: (security.W021) You have not set the SECURE_HSTS_PRELOAD setting to True. Without this, your site cannot be submitted to the browser preload list.
    stderr |
    stderr | System check identified 3 issues (0 silenced).
```

With `SECURE_HSTS_SECONDS` at 0, `"security.W005"` and `"security.W021"` give way to `"security.W004"`, the warning that the setting has no value (`django/core/checks/security/base.py:check_sts`).

## The checks by identifier

Every message the security checks give has an identifier, and the table lists them with the settings that make a check report each. Where a row says "with" a middleware, the check is silent unless that middleware is installed, which for the checks means that its dotted path, as a string, is in `MIDDLEWARE` (`django/core/checks/security/base.py:_security_middleware`, `django/core/checks/security/base.py:check_sts`).

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

> **Trap.** The checks test less than their warnings suggest. A middleware is installed, for them, only when `MIDDLEWARE` names it by Django's dotted path: a subclass of `SecurityMiddleware`, listed by the path of the project's module, gives `"security.W001"`, the warning that the middleware's settings will have no effect, and every check "with" `SecurityMiddleware` passes whatever those settings are, so that under the harbour's settings `"security.W005"` and `"security.W021"` are no longer given (`django/core/checks/security/base.py:_security_middleware`). And "not `True`" is meant exactly: the checks compare with `is True`, so `CSRF_COOKIE_SECURE = 1`, which marks the cookie secure all the same, still gives `"security.W016"` (`django/core/checks/security/csrf.py:check_csrf_cookie_secure`, `django/http/response.py:HttpResponseBase.set_cookie`).

## The rule for a key

`_check_secret_key` accepts a key of at least 50 characters, with at least 5 different ones, that does not begin with `"django-insecure-"`. `check_secret_key` applies it to `SECRET_KEY`, and warns of an empty key too, since reading one raises `ImproperlyConfigured`; `check_secret_key_fallbacks` applies it to each of `SECRET_KEY_FALLBACKS`, naming its index (`django/core/checks/security/base.py:_check_secret_key`, `django/conf/__init__.py:LazySettings.__getattr__`).

The prefix marks a key that startproject wrote: the command puts the checks' own constant, `SECRET_KEY_INSECURE_PREFIX`, before 50 random characters, and the key fails on the prefix alone ([Secret keys and `django.utils.crypto`](keys.md)) (`django/core/management/commands/startproject.py:Command.handle`).

## The cookies' checks

The session checks have three warnings each: two name what the check found, the application in `INSTALLED_APPS` or `SessionMiddleware` in `MIDDLEWARE`, and the third, given in their place when both are found, names neither (`django/core/checks/security/sessions.py:check_session_cookie_secure`, `django/core/checks/security/sessions.py:check_session_cookie_httponly`). `SESSION_COOKIE_HTTPONLY` is true by default, so left alone the two settings give only the secure flag's warning.

`"security.W016"` is silent when `CSRF_USE_SESSIONS` is true. The CSRF secret is then kept in the session ([The CSRF secret and its token](csrf-token.md)), whose cookie the session checks cover (`django/core/checks/security/csrf.py:check_csrf_cookie_secure`).
