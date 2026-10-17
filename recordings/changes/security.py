"""The habits of the section "What changed in security: Content Security Policy and signing",
release by release: the check 6.1 added for a nonce no template receives, and the nonce on the
CSRF failure page; the salt of a signed cookie, the transitional setting that reads a cookie
signed before the fix of 5.2.15 and 6.0.6, its default, and its warning; the default algorithm
of `base64_hmac` and a `Signer` that names its own; and two removals, positional arguments to
`Signer` and the setting CSRF_COOKIE_MASKED. Run by recordings/changes.py under each release;
_run.py says how a habit is written.

The checks are run as `manage.py check --tag security` runs them, without the deployment
checks. TEMPLATES is left at its default, empty, so the CSRF failure page is Django's own. Its
nonce, new for every request, is shown as an ellipsis once the habit has found it in the
response's Content-Security-Policy header. The two habits that read a cookie with
SIGNED_COOKIE_LEGACY_SALT_FALLBACK = True set it with override_settings and silence the
warning that setting it raises under 6.1.1 and this commit: that warning is the line of the
habit that sets it in a settings module.
"""
from _run import configure, habit, main

configure()


def nonce_policy_settings(policy_name):
    """The settings of a policy that names the nonce, with the middleware that writes it."""
    from django.utils.csp import CSP  # an ImportError under a release without CSP

    return {
        "MIDDLEWARE": ["django.middleware.csp.ContentSecurityPolicyMiddleware"],
        policy_name: {"style-src": [CSP.SELF, CSP.NONCE]},
    }


@habit('MIDDLEWARE = [ContentSecurityPolicyMiddleware], SECURE_CSP with CSP.NONCE, no "csp" '
       'processor in TEMPLATES: the messages of check --tag security, without --deploy')
def nonce_without_processor_check():
    from django.core import checks
    from django.test.utils import override_settings

    with override_settings(**nonce_policy_settings("SECURE_CSP")):
        found = checks.run_checks(tags=["security"])
    return ", ".join(sorted(message.id for message in found)) or "no message"


@habit("csrf_failure(request) through ContentSecurityPolicyMiddleware, SECURE_CSP with CSP.NONCE: "
       "the page's <style>")
def csrf_failure_page_nonce():
    import re

    from django.middleware.csp import ContentSecurityPolicyMiddleware
    from django.test import RequestFactory
    from django.test.utils import override_settings
    from django.views.csrf import csrf_failure

    with override_settings(**nonce_policy_settings("SECURE_CSP")):
        response = ContentSecurityPolicyMiddleware(csrf_failure)(RequestFactory().post("/entries/"))
    style = re.search(r"<style[^>]*>", response.content.decode()).group(0)
    nonce = re.search(r'nonce="([^"]+)"', style)
    if nonce:  # the nonce is new for every request: shown as an ellipsis, once it is the header's
        assert f"'nonce-{nonce.group(1)}'" in response.headers["Content-Security-Policy"]
        style = style.replace(nonce.group(1), "…")
    return style


@habit("settings.SIGNED_COOKIE_LEGACY_SALT_FALLBACK, when the settings do not set it")
def legacy_salt_fallback_default():
    from django.conf import settings
    return repr(settings.SIGNED_COOKIE_LEGACY_SALT_FALLBACK)


def request_with_cookie(name, value):
    from django.test import RequestFactory

    request = RequestFactory().get("/entries/")
    request.COOKIES[name] = value
    return request


def signed_before_the_fix(name, value, salt=""):
    """The value set_signed_cookie(name, value, salt) wrote before 5.2.15 and 6.0.6, which signed
    with the cookie's signer given the name and the salt run together as its salt, as
    _cookie_signer_legacy_salt still makes it."""
    from django.core import signing
    return signing.get_cookie_signer(salt=name + salt).sign(value)


def read_with_fallback(request):
    """get_signed_cookie("draft", salt="s") with SIGNED_COOKIE_LEGACY_SALT_FALLBACK set true; the
    warning that setting it raises is the line of another habit, and is not recorded here."""
    import warnings

    from django.test.utils import override_settings

    override = override_settings(SIGNED_COOKIE_LEGACY_SALT_FALLBACK=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        override.enable()
    try:
        return repr(request.get_signed_cookie("draft", default=None, salt="s"))
    finally:
        override.disable()


@habit('request.get_signed_cookie("draft", default=None, salt="s"): the value '
       'set_signed_cookie("drafts", "4") wrote before 5.2.15 and 6.0.6')
def colliding_cookie_signed_before_the_fix():
    request = request_with_cookie("draft", signed_before_the_fix("drafts", "4"))
    return repr(request.get_signed_cookie("draft", default=None, salt="s"))


@habit('request.get_signed_cookie("draft", default=None, salt="s"): the value '
       'set_signed_cookie("drafts", "4") wrote before 5.2.15 and 6.0.6, '
       'SIGNED_COOKIE_LEGACY_SALT_FALLBACK = True')
def colliding_cookie_signed_before_the_fix_fallback_set():
    return read_with_fallback(request_with_cookie("draft", signed_before_the_fix("drafts", "4")))


@habit('request.get_signed_cookie("draft", default=None, salt="s"): the value '
       'set_signed_cookie("drafts", "4") writes, SIGNED_COOKIE_LEGACY_SALT_FALLBACK = True')
def colliding_cookie_signed_now():
    from django.http import HttpResponse

    response = HttpResponse()
    response.set_signed_cookie("drafts", "4")
    return read_with_fallback(request_with_cookie("draft", response.cookies["drafts"].value))


@habit("SIGNED_COOKIE_LEGACY_SALT_FALLBACK = True in a project's settings module")
def legacy_salt_fallback_set():
    import sys
    import types

    from django.conf import Settings

    module = types.ModuleType("journal_legacy_salt")
    module.SIGNED_COOKIE_LEGACY_SALT_FALLBACK = True
    sys.modules["journal_legacy_salt"] = module
    return repr(Settings("journal_legacy_salt").SIGNED_COOKIE_LEGACY_SALT_FALLBACK)


@habit('base64_hmac("journal", "entry", "journal-key")')
def base64_hmac_default():
    from django.core.signing import base64_hmac
    return repr(base64_hmac("journal", "entry", "journal-key"))


@habit('Signer(key="journal-key").sign("entry")')
def signer_names_its_algorithm():
    from django.core.signing import Signer
    return repr(Signer(key="journal-key").sign("entry"))


@habit('Signer("journal-key")')
def signer_positional_key():
    from django.core.signing import Signer
    Signer("journal-key")
    return "the signer is made"


@habit("CSRF_COOKIE_MASKED = True: the length of the cookie CsrfViewMiddleware sets")
def csrf_cookie_masked():
    from django.http import HttpResponse
    from django.middleware.csrf import CsrfViewMiddleware, get_token
    from django.test import RequestFactory
    from django.test.utils import override_settings

    def view(request):
        get_token(request)
        return HttpResponse()

    with override_settings(CSRF_COOKIE_MASKED=True):
        response = CsrfViewMiddleware(view)(RequestFactory().get("/entries/"))
    return repr(len(response.cookies["csrftoken"].value))


main()
