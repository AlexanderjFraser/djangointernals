"""The habits of the section "Security fixes: limits against denial of service", release by
release: a hostile value given to each place a security fix bounded (strip_tags and Truncator,
intcomma and floatformat, urlize and the URL checks, the redirects, the URL form field, IPv6
addresses and language codes, repeated headers and the bodies of ASGI requests). Each release
run is the newest of its series, so a fix made in it or in any patch release before it meets
the value under all four. "Under ASGI" is an ASGIRequest the habit makes over a body held as
ASGIHandler.read_body holds it, a spooled temporary file, with no server and no handler; every
setting is at its release's default, so DATA_UPLOAD_MAX_MEMORY_SIZE and
FILE_UPLOAD_MAX_MEMORY_SIZE are 2,621,440 bytes, which the bodies of 3,000,000 pass. The XML
deserializer's nested elements are caching-files-signals' habit, and the redirect measured once
encoded is request-cycle's. Run by recordings/changes.py under each release; _run.py says how a
habit is written.
"""
from _run import configure, habit, main

configure()


@habit('strip_tags("<" * 51 + "a>" * 51): a tag inside a tag, 51 deep')
def strip_tags_nested():
    from django.utils.html import strip_tags
    return repr(strip_tags("<" * 51 + "a>" * 51))


@habit('strip_tags("<a" * 50 + "x" * 950): fifty opening tags that never close')
def strip_tags_unclosed():
    from django.utils.html import strip_tags
    return repr(strip_tags("<a" * 50 + "x" * 950))


@habit('Truncator("<b><i>Monday</b> Tuesday").words(1, html=True): an end tag that does not close the last tag opened')
def truncator_unmatched_end_tag():
    from django.utils.text import Truncator
    return repr(Truncator("<b><i>Monday</b> Tuesday").words(1, html=True))


@habit("intcomma(10 ** 200): its first and last ten characters, and its length")
def intcomma_of_201_digits():
    from django.contrib.humanize.templatetags.humanize import intcomma
    written = intcomma(10**200)
    return f"{written[:10]}…{written[-10:]} ({len(written)} characters)"


@habit('floatformat("1e200"): a digit and an exponent of 200')
def floatformat_past_the_cutoff():
    from django.template.defaultfilters import floatformat
    return repr(floatformat("1e200"))


@habit('len(floatformat("1e199")): a digit and an exponent of 199')
def floatformat_at_the_cutoff():
    from django.template.defaultfilters import floatformat
    return repr(len(floatformat("1e199")))


@habit('urlize("https://journal.example.com/" + "a" * 2021): a word of 2,049 characters')
def urlize_past_max_url_length():
    from django.utils.html import urlize
    return "linked" if "<a " in urlize("https://journal.example.com/" + "a" * 2021) else "left as text"


@habit('AdminURLFieldWidget().get_context("url", "https://journal.example.com/" + "a" * 2021, {})["url_valid"]: '
       'a URL of 2,049 characters')
def admin_url_widget_past_max_url_length():
    from django.contrib.admin.widgets import AdminURLFieldWidget
    context = AdminURLFieldWidget().get_context("url", "https://journal.example.com/" + "a" * 2021, {})
    return repr(context["url_valid"])


@habit('url_has_allowed_host_and_scheme("/entries/" + "x" * 2040, allowed_hosts=None): a path of 2,049 characters')
def allowed_host_past_max_url_length():
    from django.utils.http import url_has_allowed_host_and_scheme
    return repr(url_has_allowed_host_and_scheme("/entries/" + "x" * 2040, allowed_hosts=None))


@habit('HttpResponseRedirect("/entries/" + "x" * 16384).status_code: a target past MAX_URL_REDIRECT_LENGTH')
def redirect_past_max_length():
    from django.http import HttpResponseRedirect
    return repr(HttpResponseRedirect("/entries/" + "x" * 16384).status_code)


@habit('forms.URLField(assume_scheme="https").clean("https://journal.example.com/20\\n26/"): a newline inside')
def url_field_newline_inside():
    from django import forms
    return repr(forms.URLField(assume_scheme="https").clean("https://journal.example.com/20\n26/"))


@habit('is_valid_ipv6_address("0000:0000:0000:0000:0000:ffff:192.168.100.200"): written in full, 45 characters')
def ipv6_written_in_full():
    from django.utils.ipv6 import is_valid_ipv6_address
    return repr(is_valid_ipv6_address("0000:0000:0000:0000:0000:ffff:192.168.100.200"))


@habit('get_supported_language_variant("en-" + "x" * 600): a code past LANGUAGE_CODE_MAX_LENGTH')
def language_variant_cut():
    from django.utils.translation import get_supported_language_variant
    return repr(get_supported_language_variant("en-" + "x" * 600))


@habit('get_supported_language_variant("en-" + "x" * 600, strict=True): the class of what it raises')
def language_variant_strict():
    from django.utils.translation import get_supported_language_variant
    try:
        get_supported_language_variant("en-" + "x" * 600, strict=True)
    except Exception as error:  # noqa: BLE001 - the class is what is recorded; the message is the code
        return type(error).__name__
    return "nothing raised"


@habit('check_for_language("x" * 501): the codes translation_catalog_exists holds after it, its cache emptied first')
def check_for_language_long_code():
    from django.utils.translation import check_for_language
    from django.utils.translation.trans_real import translation_catalog_exists

    translation_catalog_exists.cache_clear()
    check_for_language("x" * 501)
    return f"{translation_catalog_exists.cache_info().currsize} codes"


def asgi_request(headers, body):
    """An ASGIRequest over a body held as ASGIHandler.read_body holds it, a spooled temporary
    file, and the file, which the habit closes."""
    import tempfile

    from django.conf import settings
    from django.core.handlers.asgi import ASGIRequest

    body_file = tempfile.SpooledTemporaryFile(max_size=settings.FILE_UPLOAD_MAX_MEMORY_SIZE, mode="w+b")
    body_file.write(body)
    body_file.seek(0)
    scope = {"type": "http", "method": "POST", "path": "/entries/", "query_string": b"", "headers": headers}
    return ASGIRequest(scope, body_file), body_file


@habit('request.META["HTTP_ACCEPT"] under ASGI: three "accept" headers, text/html, application/json and */*')
def asgi_repeated_header():
    request, body_file = asgi_request(
        [(b"accept", b"text/html"), (b"accept", b"application/json"), (b"accept", b"*/*")], b""
    )
    try:
        return repr(request.META["HTTP_ACCEPT"])
    finally:
        body_file.close()


@habit('request.body under ASGI: 3,000,000 bytes sent with "content-length" 10')
def asgi_body_understated():
    request, body_file = asgi_request([(b"content-length", b"10")], b"x" * 3_000_000)
    try:
        return f"{len(request.body)} bytes"
    finally:
        body_file.close()


@habit('type(request.FILES["notes"]).__name__ under ASGI: a file of 3,000,000 bytes sent with "content-length" 10')
def asgi_upload_understated():
    body = (
        b"--journal\r\n"
        b'Content-Disposition: form-data; name="notes"; filename="notes.txt"\r\n'
        b"Content-Type: text/plain\r\n"
        b"\r\n" + b"x" * 3_000_000 + b"\r\n"
        b"--journal--\r\n"
    )
    request, body_file = asgi_request(
        [(b"content-type", b"multipart/form-data; boundary=journal"), (b"content-length", b"10")], body
    )
    try:
        upload = request.FILES["notes"]
        try:
            return type(upload).__name__
        finally:
            upload.close()
    finally:
        body_file.close()


main()
