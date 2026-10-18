---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Security fixes: limits against denial of service

Since 5.0, security releases have bounded the work Django does on hostile input: in `strip_tags`, `Truncator`, `wrap`, `intcomma` and `floatformat`, URLs, redirects, IPv6 addresses, language codes, requests, the XML deserializer and GEOS geometries.

A denial of service of this kind needs no wrong answer, only an input that costs far more than it should. Some fixes bound the input: past a length or a count, it is refused, cut short, passed through untouched or sent to disk. Others make the work cheaper.

Every fix is in 5.2.17, 6.0.8 and 6.1.1, as at this commit. The fixes up to 5.2.13 and 6.0.4 also went to 4.2, all but CVE-2025-27556's; no later one did. The newest two, in `django.utils.translation.check_for_language` and in geometry collections, came in 5.2.17 and 6.0.8. 6.1 came out the next day, on 5 August 2026 (`docs/releases/6.1.txt`). The security archive gives it a patch for each (`docs/releases/security.txt`), and 6.1.1 lists no security fix. What differs among the four came later, in `intcomma`, the redirects and the XML deserializer.

## Markup and text

`strip_tags`, and with it the filter `striptags`, can now raise `SuspiciousOperation` (`django/utils/html.py:strip_tags`). It parses the text and repeats while a pass still removes a tag. Nested incomplete entities made it extremely slow (CVE-2024-53907, 5.0.10 and 5.1.4). The loop is now allowed `MAX_STRIP_TAGS_DEPTH` passes, 50, and raises if the text still holds a "<" and a ">" after them. Long unclosed opening tags made it slow too (CVE-2025-32873, 5.1.9 and 5.2.1). Before any pass, an opening tag that runs a thousand characters without a ">" and holds 50 or more "<" raises the same.

`Truncator.words` with `html=True`, behind `truncatewords_html`, used a regular expression that a crafted string could make backtrack (CVE-2024-27351, 5.0.3). Since 5.1 the HTML methods parse with `html.parser.HTMLParser` ([What changed in time zones, translation and the utilities](i18n-and-utils.md)). Built on it, they were quadratic on many unmatched end tags (CVE-2026-1285, 5.2.11 and 6.0.2). An end tag now pops the stack of open tags only when it closes the tag opened last (`django/utils/text.py:TruncateHTMLParser.handle_endtag`).

`wrap`, behind `wordwrap`, was open to very long strings (CVE-2025-26699, 5.0.13 and 5.1.7). At this commit it hands each line to `textwrap.TextWrapper` (`django/utils/text.py:wrap`; [Text helpers: `Truncator` and `django/utils/text.py`](../utils/text.md)).

## Numbers: a cutoff of 200 digits

`floatformat` now returns its input as given when the decimal's digits and its exponent's absolute value come to more than 200 (`django/template/defaultfilters.py:floatformat`; [The built-in filters](../templates/filters.md#numbers)). Before the fix it could use much memory on a number in scientific notation with a large exponent (CVE-2024-41989, 5.0.8). The number formatter writes a decimal past the same cutoff in scientific notation (`django/utils/numberformat.py:format`).

`intcomma` was open to very long strings (CVE-2024-24680, 5.0.2). Its own grouping is now one substitution over the leading digits reversed. With `use_l10n=True`, the default, a number goes to `number_format` instead. 5.2.17 hands it an `int`, unless the value is a float or a `decimal.Decimal`. 6.0.8 hands it a `decimal.Decimal`, so a string holding a float gets the locale's format too (`django/contrib/humanize/templatetags/humanize.py:intcomma`; [Humanize: `naturaltime`, `intcomma` and the other filters](../contrib/humanize.md#the-numbers)).

For an integer of 201 digits, shown by its ends and its length, 5.2.17's formatter groups the `int` in full; from 6.0.8 the decimal is past the cutoff:

```text recording=changes
intcomma(10 ** 200): its first and last ten characters, and its length
    5.2.17       100,000,00…00,000,000 (267 characters)
    6.0.8        1.00000000…00000e+200 (207 characters)
    6.1.1        1.00000000…00000e+200 (207 characters)
    this commit  1.00000000…00000e+200 (207 characters)
```

Nothing warns, and no release's notes mention the change.

## URLs and Unicode on Windows

The guards here stop a long URL before it is split, at `MAX_URL_LENGTH`, 2,048 characters (`django/utils/http.py`). Python's NFKC normalization, which `urllib.parse.urlsplit` can perform, is slow on Windows (`docs/releases/5.2.12.txt`).

`django.utils.html.urlize`, behind the `urlize` and `urlizetrunc` filters, was open to input with very many brackets (CVE-2024-38875, 5.0.7), to very large input with a particular sequence of characters (CVE-2024-41990, 5.0.8; CVE-2024-45230, 5.0.9 and 5.1.1), and, as was `AdminURLFieldWidget`, to very many Unicode characters (CVE-2024-41991, 5.0.8). At this commit a word longer than `MAX_URL_LENGTH` once its punctuation is trimmed is left as text (`django/utils/html.py:Urlizer.handle_word`). The trimming counts a word's brackets once (`django/utils/html.py:Urlizer.trim_punctuation`). By default the widget links only a value `URLValidator` accepts, so none over the bound (`django/contrib/admin/widgets.py:AdminURLFieldWidget.get_context`).

`LoginView`, `LogoutView` and `set_language` were open to very many Unicode characters on Windows (CVE-2025-27556, 5.0.14 and 5.1.8). Each judges its redirect with `url_has_allowed_host_and_scheme`, which refuses a URL over `MAX_URL_LENGTH` before splitting it (`django/utils/http.py:_url_has_allowed_host_and_scheme`; [The helpers in `django/utils/http.py`](../http/helpers.md#urls-that-came-from-a-client)).

The form field's `URLField.to_python` split the value to decide whether to put a scheme in front (CVE-2026-25673, 5.2.12 and 6.0.3). It now looks for a scheme only before the first colon (`django/forms/fields.py:URLField.to_python`). A tab or a newline inside the value now reaches `URLValidator`, which refuses it ([The built-in form fields](../forms/field-types.md#urls-and-the-assumed-scheme)).

## Redirects

`HttpResponseRedirectBase.__init__` now raises `DisallowedRedirect`, by default, for a target past `MAX_URL_REDIRECT_LENGTH`, 16,384 characters, before splitting it (`django/http/response.py:HttpResponseRedirectBase.__init__`; [The response object](../http/response.md#redirects)). `HttpResponseRedirect`, `HttpResponsePermanentRedirect` and `redirect` had been open to very many Unicode characters on Windows (CVE-2025-64458, 5.1.14 and 5.2.8). 5.2.17 and 6.0.8 measure the target as given. 6.1 measures the `"Location"` header, the target as `iri_to_uri` escapes it, where a character outside ASCII takes six or more.

A target of 3,009 characters, 3,000 of them "é", is within the limit until it is encoded: 302 is the old measure, the refusal the new:

```text recording=changes
HttpResponseRedirect("/entries/" + "é" * 3000).status_code: within the limit until it is encoded
    5.2.17       302
    6.0.8        302
    6.1.1        DisallowedRedirect: Unsafe redirect exceeding 16384 characters
    this commit  DisallowedRedirect: Unsafe redirect exceeding 16384 characters
```

> **Trap.** Since 6.1 a target wholly outside ASCII is refused past 2,730 characters or fewer, where 6.0.8 took 16,384. The 6.1 notes give the redirects a `max_length=` argument ([What changed in handlers, requests, URLs and views](request-cycle.md)), and say nothing of what is measured.

## Addresses and language codes

Since 5.0.11 and 5.1.5 (CVE-2024-56374), `is_valid_ipv6_address` and, by default, `clean_ipv6_address` refuse text longer than `MAX_IPV6_ADDRESS_LENGTH`, 39 characters, before `ipaddress` parses it (`django/utils/ipv6.py:_ipv6_address_from_str`; [Dates, durations and addresses: `parse_datetime`, `parse_duration` and `clean_ipv6_address`](../utils/parsing.md#ipv6-addresses-clean_ipv6_address)). The bound counts characters: `"0000:0000:0000:0000:0000:ffff:192.168.100.200"`, which `ipaddress` accepts, has 45, and is refused under 5.2.17 as here.

`get_supported_language_variant` was open to very long codes holding particular characters (CVE-2024-39614, 5.0.7). It now cuts a code longer than `LANGUAGE_CODE_MAX_LENGTH`, 500 characters, at its last hyphen within the limit. It refuses a code with no hyphen there, and any long code when `strict=True` (`django/utils/translation/trans_real.py:get_supported_language_variant`). The 5.0.7 notes say `ValueError`; the code raises the `LookupError` its callers catch, under 5.2.17 as here.

`check_for_language` used each code as a key of an in-memory cache, bounded in entries but not in their length (CVE-2026-15337, 5.2.17 and 6.0.8). At this commit it refuses a code over the limit before the cache sees it (`django/utils/translation/trans_real.py:check_for_language`; [Choosing a language: `LocaleMiddleware`](../i18n/choosing.md#whether-a-catalogue-exists)).

## Headers and bodies

Under ASGI, `HttpRequest.body` now measures the body as well as checking its Content-Length (`django/http/request.py:HttpRequest.body`; [The body: `body`, `POST` and `FILES`](../http/body.md#under-asgi)). A request with no Content-Length, or one smaller than the body, could take a body past `DATA_UPLOAD_MAX_MEMORY_SIZE` into `body` (CVE-2026-33034, 5.2.13 and 6.0.4). It could also keep an upload in memory past `FILE_UPLOAD_MAX_MEMORY_SIZE` (CVE-2026-5766, 5.2.14 and 6.0.5). `MemoryFileUploadHandler.handle_raw_input` now judges by the same measure, so by default an upload in a body past that limit goes to disk (`django/core/files/uploadhandler.py:MemoryFileUploadHandler.handle_raw_input`; [Multipart parsing and upload handlers](../http/uploads.md#memory-or-disk)).

Under ASGI a header sent many times was joined by repeated string concatenation (CVE-2025-14550, 5.2.11 and 6.0.2). `ASGIRequest.__init__` now joins its values once (`django/core/handlers/asgi.py:ASGIRequest.__init__`; [Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md#from-an-asgi-scope)).

A file sent in Base64 with much white space could make the multipart parser copy memory repeatedly (CVE-2026-33033, 5.2.13 and 6.0.4). At this commit the parser strips each chunk's white space and joins the pieces once before decoding them (`django/http/multipartparser.py:MultiPartParser._parse`).

## The XML deserializer

Since 6.1 `check_element_type` raises `SuspiciousOperation` where `getInnerText` meets an element with content of its own (`django/core/serializers/xml_serializer.py:check_element_type`; [What changed in caching, files, signals, serialization and pagination](caching-files-signals.md)). Under 6.0.8 that element's text still went into the value. Deserializing XML had taken quadratic time on many nested invalid elements (CVE-2025-64460, 5.1.15 and 5.2.9). The fix had `getInnerText` collect text element by element.

## Nested geometry collections

`GEOSGeometry` now counts geometry collections before GEOS reads them: in WKT how deep they nest, in WKB how many there are. The reader raises `ValueError` past 198, the constant `MAX_GEOM_COLLECTIONS` that is the default of `max_geom_collections=` (`django/contrib/gis/geos/prototypes/io.py:_WKTReader.limit`, `django/contrib/gis/geos/prototypes/io.py:_WKBReader`; [Geometries in Python: GEOS and GDAL](../contrib/geometries.md#geosgeometry)). Deeply nested collections had crashed GEOS (CVE-2026-15830, 5.2.17 and 6.0.8). The notes say GeoJSON is not limited. At this commit its WKB, from GDAL, is counted at the default, whatever `max_geom_collections=` says (`django/contrib/gis/gdal/geometries.py:OGRGeometry._geos_ptr`).

> **Trap.** `GEOSGeometry` and the model field take `max_geom_collections=`, and there `None` means no limit. In the form field `None` keeps the default. So a model field given `max_geom_collections=None` still makes a form field that refuses past 198 (`django/contrib/gis/forms/fields.py:GeometryField.__init__`).
