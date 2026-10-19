---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The helpers in `django/utils/http.py`

The module `django/utils/http.py` holds `url_has_allowed_host_and_scheme`, the check to make on a URL that came from a client before it is used, and the small functions that read and write HTTP's own notations: dates (`http_date`, `parse_http_date`), entity tags (`quote_etag`, `parse_etags`), a header's parameters (`parse_header_parameters`, `content_disposition_header`) and query strings (`urlencode`).

The request and response classes know the shape of a message. Much of the syntax of what goes inside one is kept apart from them, in a module of functions with no state that the request, the response, the middleware and several contrib apps all draw on. That syntax is fiddly in ways that matter: a date has three legal spellings, a file name in a header has two encodings, and a URL that looks like a path can take a browser to another site (`django/utils/http.py`).

## URLs that came from a client: `url_has_allowed_host_and_scheme`

A site often redirects to a URL it was given: the page a visitor wanted before being sent to log in, passed along as a parameter. If that parameter is used as it stands, anyone can make a link to the real site that ends on a site of their own. `url_has_allowed_host_and_scheme` is the check to make first. It says yes to a URL only if the URL's scheme, when it has one, is `"http"` or `"https"` (`"https"` alone if the caller sets require_https), and its host, when it has one, is in a set the caller passes. An empty URL it always refuses (`django/utils/http.py:url_has_allowed_host_and_scheme`).

A comparison of host names would not be enough, because a browser's idea of where a URL leads is more generous than a parser's. Two slashes begin a host with no scheme, so such a URL is judged by that host, and counts as `"http"`. The function tests the URL twice, as written and with its backslashes turned into slashes, and both must pass. Three slashes are refused outright, and so are a scheme with no host after it, a URL that begins with a control character once the white space around it is stripped, and one longer than `MAX_URL_LENGTH`, 2048 characters. The host is compared exactly, capitals, port and credentials included (`django/utils/http.py:_url_has_allowed_host_and_scheme`).

Against shop.example, the one allowed host, look for the three slashes, the backslash and the scheme before three slashes, in which a parser finds no host, and for shop.example itself refused in capitals, with its port, and over `"http"` where `"https"` is required.

```text recording=http
...
URLs that came from a client; allowed_hosts is {'shop.example'}
  url_has_allowed_host_and_scheme('/orders/', allowed_hosts)  ->  True
  url_has_allowed_host_and_scheme('https://shop.example/orders/', allowed_hosts)  ->  True
  url_has_allowed_host_and_scheme('https://evil.example/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('//evil.example/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('///evil.example/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('/\\evil.example/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('http:///evil.example/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('javascript:alert(1)', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('ftp://shop.example/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('//shop.example/orders/', allowed_hosts)  ->  True
  url_has_allowed_host_and_scheme('https://SHOP.example/orders/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('https://shop.example:443/orders/', allowed_hosts)  ->  False
  url_has_allowed_host_and_scheme('http://shop.example/', allowed_hosts, require_https=True)  ->  False
  ...
```

> **Why.** Each guard but the limit on length answers a way in which a browser reads a URL. Chrome treats a backslash in a path as a slash, but a backslash can also belong to the credentials of basic authentication, so both readings are checked. Chrome takes a URL that begins with more than two slashes for an absolute one, and the name after a scheme and three slashes for the host, where Python's parser reads both as a path. Some browsers, Chrome among them, ignore many control characters at the start of a URL and may then read it as naming a host with no scheme. The limit on length protects the server from a denial of service: the parser does not validate its input, and Unicode normalization is very slow on Windows (`django/utils/http.py:url_has_allowed_host_and_scheme`, `django/utils/http.py:_url_has_allowed_host_and_scheme`).

> **History.** The function came in the security releases 1.4.3 and 1.3.5, as is_safe_url, for use "whenever user-supplied redirect targets are accepted", and Django's own views that accepted one, mostly the authentication system's, were changed to call it (`docs/releases/1.4.3.txt`). Django 3.0 gave it its present name "to avoid possible confusion as to effective scope": a URL with an allowed host and scheme is not on that account safe, and may still be quoted wrongly, as the function's docstring still warns (`docs/releases/3.0.txt`).

Within Django the check has two callers, and both allow the request's own host. `RedirectURLMixin.get_redirect_url`, which the login and logout views inherit, the admin's included, judges the redirect parameter and allows as well any other hosts the view names ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](../auth/login-views.md)). `set_language` judges its `"next"` parameter and, if that is refused, the `"Referer"` header ([The language views: `set_language` and `JavaScriptCatalog`](../i18n/views.md)) (`django/contrib/auth/views.py:RedirectURLMixin.get_redirect_url`, `django/contrib/admin/sites.py:AdminSite.login`, `django/views/i18n.py:set_language`).

Two smaller functions guard the same boundary, where a path or a host name that came from a client is put to use. `escape_leading_slashes` rewrites a path that begins with two slashes so that the second is percent-encoded, which keeps a path Django built itself from being read as a host; `CommonMiddleware` applies it to the URL it redirects to when appending a slash, and the URL resolver to every URL it reverses. `is_same_domain` matches a host name against a pattern, by the rule that `ALLOWED_HOSTS` follows for a leading dot ([Headers, host and scheme](headers.md#the-host)), and the CSRF middleware uses it to match the host of an `"Origin"` or a `"Referer"` header against the hosts it trusts (`django/utils/http.py:escape_leading_slashes`, `django/utils/http.py:is_same_domain`).

In the first line below only the second slash is encoded; the other three try one pattern with a leading dot on a subdomain, on the bare domain, and on a name that only ends in the same letters.

```text recording=http
...
escape_leading_slashes('//evil.example/')  ->  '/%2Fevil.example/'
is_same_domain('www.shop.example', '.shop.example')  ->  True
is_same_domain('shop.example', '.shop.example')  ->  True
is_same_domain('notshop.example', '.shop.example')  ->  False
...
```

## Dates and entity tags

HTTP writes a moment as text, in Last-Modified, `"Expires"`, If-Modified-Since and a cookie's expiry, while this module holds it as seconds since 1970. `http_date` goes from the number to the text, and `parse_http_date` back (`django/utils/http.py:http_date`, `django/utils/http.py:parse_http_date`).

HTTP allows three forms of date, which the module's patterns call `RFC1123_DATE`, `RFC850_DATE` and `ASCTIME_DATE`, and writing always produces the first. Reading accepts all three, since the standard obliges a server to, though only the first is still in general use. The second form has a two-digit year, which the function resolves as the standard says: a year that would lie more than fifty years ahead is taken to be in the past century. `parse_http_date_safe` is for a header that may be malformed: it returns `None` where the other raises `ValueError`, and its callers treat a date they cannot read as no date (`django/utils/http.py:parse_http_date_safe`).

Each of the three forms below reads back to the number `http_date` was given, and a date written year first is none of them.

```text recording=http
dates
  http_date(1790000000)  ->  'Mon, 21 Sep 2026 14:13:20 GMT'
  parse_http_date("Mon, 21 Sep 2026 14:13:20 GMT")  ->  1790000000
  parse_http_date("Monday, 21-Sep-26 14:13:20 GMT")  ->  1790000000
  parse_http_date("Mon Sep 21 14:13:20 2026")  ->  1790000000
  parse_http_date("2026-09-21 14:13:20")  ->  raises ValueError
  parse_http_date_safe("2026-09-21 14:13:20")  ->  None
  ...
```

An `"ETag"` is a quoted string that names one version of a response, with `"W/"` in front if it is a weak one, and a client sends tags back in If-None-Match and If-Match, several at a time or as a single asterisk. `quote_etag` adds the quotes to a bare string and leaves a well-formed tag alone; `parse_etags` splits a header into the tags it holds and silently drops any that are not well formed (`django/utils/http.py:quote_etag`, `django/utils/http.py:parse_etags`).

Of the tags in the header below, the bare ghi is the one dropped, and an asterisk comes back as the only tag.

```text recording=http
...
entity tags
  quote_etag('abc')  ->  '"abc"'
  quote_etag('W/"abc"')  ->  'W/"abc"'
  parse_etags('"abc", W/"def", ghi')  ->  ['"abc"', 'W/"def"']
  parse_etags('*')  ->  ['*']
  ...
```

The code that compares a request's dates and tags with a response's is in [Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md).

## Header values, query strings and compact encodings

| function | what it does | called by |
|---|---|---|
| `parse_header_parameters` | splits a value such as a Content-Type into its main part, in lower case, and a dictionary of its parameters | the request, for its content type; `MediaType`, for each item of an `"Accept"` header; the multipart parser, for the boundary and each part's headers; the commands that start a project or an app, for the name of a template they download |
| `split_header_value` | yields the items of a comma-separated header, stripped | the code in `django/utils/cache.py` that reads and patches `"Vary"` and Cache-Control; `parse_etags` and `split_directive_names` in this module |
| `split_directive_names` | yields only the names of the directives in such a header, in lower case | the cache middleware and `ConditionalGetMiddleware`, to see whether a directive is present |
| `content_disposition_header` | writes a Content-Disposition value from a flag and a file name | `FileResponse` |
| `django.utils.http.urlencode` | Python's `urllib.parse.urlencode`, extended | the admin, for its links; the test client, for query strings |
| `int_to_base36`, `base36_to_int` | write and read a whole number in digits and lower-case letters | the password-reset token, for its timestamp |
| `urlsafe_base64_encode`, `urlsafe_base64_decode` | base64 in its URL-safe alphabet, with the padding removed and restored | the password-reset link, for the user's id |

*The other functions of `django/utils/http.py`.*

Four of them do more than the table has room for, and the lines below show where: a quoted parameter and an accented file name read by `parse_header_parameters`, four file names given to `content_disposition_header`, the last of them empty, a `MultiValueDict` and a `None` given to `urlencode`, and fourteen digits refused by `base36_to_int`.

```text recording=http
...
parse_header_parameters('Text/HTML; Charset="utf-8"')  ->  ('text/html', {'charset': 'utf-8'})
parse_header_parameters("attachment; filename*=UTF-8''caf%C3%A9.txt")  ->  ('attachment', {'filename': 'café.txt'})
...
content_disposition_header(True, 'report 2026.txt')  ->  'attachment; filename="report 2026.txt"'
content_disposition_header(False, 'café "menu".txt')  ->  "inline; filename*=utf-8''caf%C3%A9%20%22menu%22.txt"
content_disposition_header(False, 'a "b".txt')  ->  'inline; filename="a \\"b\\".txt"'
content_disposition_header(False, '')  ->  None
...
urlencode(MultiValueDict({'tag': ['new', 'sale']}), doseq=True)  ->  'tag=new&tag=sale'
urlencode({'page': None})  ->  raises TypeError: Cannot encode None for key 'page' in a query string. Did you mean to pass an empty string or omit the value?
...
base36_to_int('z' * 14)  ->  raises ValueError: Base36 input too large
...
```

`parse_header_parameters` also refuses a value longer than `MAX_HEADER_LENGTH`, 10,000 characters, with `ValueError`, and that refusal is what makes a request with an oversized Content-Type fail as it is made ([Making the request: `WSGIRequest` and `ASGIRequest`](request.md#the-content-type-and-the-encoding)) (`django/utils/http.py:parse_header_parameters`).

`content_disposition_header` quotes a file name only when every character is printable ASCII or a tab, the characters a quoted string may hold, and writes any other name as UTF-8, percent-encoded; with no file name it writes the word `"attachment"` alone for an attachment (`django/utils/http.py:content_disposition_header`).

Asked to write sequences as repeated keys, `urlencode` does so for a generator too, and where it raises for `None`, Python's function would write the word None into the URL. `QueryDict.urlencode` is a different function with the same job for one type ([`QueryDict`](querydict.md#parsing-and-decoding)) (`django/utils/http.py:urlencode`).

The base 36 reader refuses more than thirteen digits, enough for any 64-bit number, so that a longer string cannot use up the server's resources (`django/utils/http.py:base36_to_int`). Both pairs of encodings are in this module because what they write goes into URLs, in Django the password-reset link ([Password reset: `PasswordResetTokenGenerator` and the reset views](../auth/password-reset.md)).
