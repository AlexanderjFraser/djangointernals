---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The helpers in `django/utils/http.py`

The module `django/utils/http.py` holds the small functions that read and write HTTP's own notations: dates, entity tags, header parameters, query strings, and URLs that came from a client and have to be judged before they are used. This section says what each does and which part of Django calls it.

The request and response classes know the shape of a message. Much of the syntax of what goes inside one is kept apart from them, in a module of functions with no state that the request, the response, the middleware and several contrib apps all draw on. That syntax is fiddly in ways that matter: a date has three legal spellings, a file name in a header has two encodings, and a URL that looks like a path can take a browser to another site (`django/utils/http.py`).

## URLs that came from a client

A site often redirects to a URL it was given: the page a visitor wanted before being sent to log in, passed along as a parameter. If that parameter is used as it stands, anyone can make a link to the real site that ends on a site of their own. `url_has_allowed_host_and_scheme` is the check to make first. It says yes to a URL only if the URL's scheme, when it has one, is `"http"` or `"https"`, and its host, when it has one, is in a set the caller passes (`django/utils/http.py:url_has_allowed_host_and_scheme`).

```text recording=http
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
```

A comparison of host names would not be enough, because a browser's idea of where a URL leads is more generous than a parser's. Two slashes begin a host with no scheme, so such a URL is judged by that host, and passes only when the host is allowed. A backslash is read by browsers as a slash, so the function tests the URL twice, as written and with its backslashes turned into slashes, and both must pass. Three slashes, which some browsers read as two, are refused outright, and so are a scheme with no host after it, a URL that begins with a control character once the white space around it is stripped, and one longer than `MAX_URL_LENGTH`, 2048 characters. The host is compared exactly, capitals and port included. The docstring adds that a true answer means only that the host and scheme are allowed, not that the URL is safe in every other respect.

Within Django it is called on the redirect parameter by the authentication views, which allow the request's own host and any others the view names, and by the view that sets the language (`django/contrib/auth/views.py:RedirectURLMixin.get_redirect_url`, `django/views/i18n.py:set_language`).

The same edge has smaller guards. `escape_leading_slashes` rewrites a path that begins with two slashes so that the second is percent-encoded, which keeps a path Django built itself from being read as a host; `CommonMiddleware` applies it to the URL it redirects to when appending a slash, and the URL resolver to every URL it reverses. `is_same_domain` is the comparison under `settings.ALLOWED_HOSTS`: a pattern that begins with a dot matches the domain and its subdomains, and any other pattern must be equal. The CSRF middleware uses it as well, to match the host of an `"Origin"` or a `"Referer"` header against the hosts it trusts (`django/utils/http.py:escape_leading_slashes`, `django/utils/http.py:is_same_domain`).

```text recording=http
escape_leading_slashes('//evil.example/')  ->  '/%2Fevil.example/'
is_same_domain('www.shop.example', '.shop.example')  ->  True
is_same_domain('shop.example', '.shop.example')  ->  True
is_same_domain('notshop.example', '.shop.example')  ->  False
```

## Dates and entity tags

HTTP writes a moment as text, in `Last-Modified`, `"Expires"`, `If-Modified-Since` and a cookie's expiry, while Python code holds it as seconds since 1970. `http_date` goes from the number to the text, and `parse_http_date` back (`django/utils/http.py:http_date`, `django/utils/http.py:parse_http_date`).

```text recording=http
  http_date(1790000000)  ->  'Mon, 21 Sep 2026 14:13:20 GMT'
  parse_http_date("Mon, 21 Sep 2026 14:13:20 GMT")  ->  1790000000
  parse_http_date("Monday, 21-Sep-26 14:13:20 GMT")  ->  1790000000
  parse_http_date("Mon Sep 21 14:13:20 2026")  ->  1790000000
  parse_http_date("2026-09-21 14:13:20")  ->  raises ValueError
  parse_http_date_safe("2026-09-21 14:13:20")  ->  None
entity tags
  quote_etag('abc')  ->  '"abc"'
  quote_etag('W/"abc"')  ->  'W/"abc"'
  parse_etags('"abc", W/"def", ghi')  ->  ['"abc"', 'W/"def"']
  parse_etags('*')  ->  ['*']
```

Writing always produces the first of the three forms of date. Reading accepts all three, since the standard obliges a server to, though only the first is still in general use. The second form has a two-digit year, which the function resolves as the standard says: a year that would lie more than fifty years ahead is taken to be in the past century. `parse_http_date_safe` is for a header that may be malformed: it returns `None` where the other raises `ValueError`, and its callers treat a date they cannot read as no date.

Among the writers are `HttpResponseBase.set_cookie`, the session middleware, the view that serves static files and the code that sets `"Expires"` for the cache. The readers are the code that answers conditional requests, `get_conditional_response`, `ConditionalGetMiddleware` and the static files view, and the cache middleware, which reads a stored response's `"Expires"` (`django/utils/cache.py:get_conditional_response`, `django/middleware/http.py:ConditionalGetMiddleware`, `django/views/static.py:was_modified_since`, `django/middleware/cache.py:FetchFromCacheMiddleware.process_request`).

An `"ETag"` is a quoted string that names one version of a response, with `"W/"` in front if it is a weak one, and a client sends tags back in `If-None-Match` and `If-Match`, several at a time or as a single asterisk. `quote_etag` adds the quotes to a bare string and leaves a well-formed tag alone; `parse_etags` splits a header into the tags it holds and silently drops any that are not well formed. Both serve the conditional-request code of [Caching, files, mail, signals and tasks](../services.md), which compares a request's tags and dates with the response's and answers 304, or 412 where a precondition fails (`django/utils/http.py:quote_etag`, `django/utils/http.py:parse_etags`).

## The rest of the module

| function | what it does | called by |
|---|---|---|
| `parse_header_parameters` | splits a value such as a `Content-Type` into its main part, in lower case, and a dictionary of its parameters | the request, for its content type; `MediaType`, for each item of an `"Accept"` header; the multipart parser, for the boundary and each part's headers; the commands that start a project or an app, for the name of a template they download |
| `split_header_value` | yields the items of a comma-separated header, stripped | the code in `django/utils/cache.py` that reads and patches `"Vary"` and `Cache-Control`; `parse_etags` and `split_directive_names` in this module |
| `split_directive_names` | yields only the names of the directives in such a header, in lower case | the cache middleware and `ConditionalGetMiddleware`, to see whether a directive is present |
| `content_disposition_header` | writes a `Content-Disposition` value from a flag and a file name | `FileResponse` |
| `django.utils.http.urlencode` | Python's `urllib.parse.urlencode`, extended | the admin, for its links; the test client, for query strings |
| `int_to_base36`, `base36_to_int` | write and read a whole number in digits and lower-case letters | the password-reset token, for its timestamp |
| `urlsafe_base64_encode`, `urlsafe_base64_decode` | base64 in its URL-safe alphabet, with the padding removed and restored | the password-reset link, for the user's id |

*The other functions of `django/utils/http.py`.*

```text recording=http
parse_header_parameters('Text/HTML; Charset="utf-8"')  ->  ('text/html', {'charset': 'utf-8'})
parse_header_parameters("attachment; filename*=UTF-8''caf%C3%A9.txt")  ->  ('attachment', {'filename': 'café.txt'})
list(split_header_value('Accept-Encoding,  Cookie,'))  ->  ['Accept-Encoding', 'Cookie']
list(split_directive_names('max-age=60, Private="Set-Cookie"'))  ->  ['max-age', 'private']
content_disposition_header(True, 'report 2026.txt')  ->  'attachment; filename="report 2026.txt"'
content_disposition_header(False, 'café "menu".txt')  ->  "inline; filename*=utf-8''caf%C3%A9%20%22menu%22.txt"
content_disposition_header(False, 'a "b".txt')  ->  'inline; filename="a \\"b\\".txt"'
content_disposition_header(False, '')  ->  None
...
urlencode({'tag': ['new', 'sale'], 'page': 2}, doseq=True)  ->  'tag=new&tag=sale&page=2'
urlencode(MultiValueDict({'tag': ['new', 'sale']}), doseq=True)  ->  'tag=new&tag=sale'
urlencode({'page': None})  ->  raises TypeError: Cannot encode None for key 'page' in a query string. Did you mean to pass an empty string or omit the value?
...
int_to_base36(1790000000)  ->  'tlpwu8'
base36_to_int('tlpwu8')  ->  1790000000
base36_to_int('z' * 14)  ->  raises ValueError: Base36 input too large
urlsafe_base64_encode(bytes([251, 255, 254]))  ->  '-__-'
urlsafe_base64_encode(b'42')  ->  'NDI'
urlsafe_base64_decode('NDI')  ->  b'42'
```

Some of these do more than the table has room for.

`parse_header_parameters` removes the quotes from a quoted parameter and decodes the extended form in which a parameter's value names its own character set, as the line with an accented file name shows. It refuses a value longer than `MAX_HEADER_LENGTH`, 10,000 characters, with `ValueError`, so that no caller can be made to parse an arbitrarily long header; that refusal is what makes a request with an oversized `Content-Type` fail as it is made ([Making the request](request.md#the-content-type-and-the-encoding)) (`django/utils/http.py:parse_header_parameters`).

`content_disposition_header` chooses between two ways of writing a file name. A name of printable ASCII, in which a tab is allowed, goes in quotes, with a backslash before any quote or backslash in it. Any other name is written in the extended form, as UTF-8 and percent-encoded. With no file name it writes the word alone for an attachment, and nothing at all otherwise (`django/utils/http.py:content_disposition_header`).

`urlencode` differs from Python's function in what it accepts. Asked to write sequences as repeated keys, it does so for a `MultiValueDict` and for a generator as well as for a list, and it raises `TypeError` for a value of `None`, where Python's would write the word None into the URL. `QueryDict.urlencode` is a different function with the same job for one type ([`QueryDict`](querydict.md#why-it-cannot-be-changed)) (`django/utils/http.py:urlencode`).

The base 36 reader refuses input longer than thirteen characters, which is enough for any 64-bit number. The two pairs of encodings have nothing to do with HTTP's syntax and are in this module because their output goes into URLs: the password-reset link carries a user's id in base64 and a timestamp in base 36 ([Authentication, sessions and messages](../auth.md)) (`django/contrib/auth/tokens.py:PasswordResetTokenGenerator`, `django/contrib/auth/forms.py:PasswordResetForm.save`, `django/contrib/auth/views.py:PasswordResetConfirmView.get_user`).
