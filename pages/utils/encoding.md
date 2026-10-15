---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Text and bytes: `django/utils/encoding.py`

`django/utils/encoding.py` converts between text and bytes, with `force_str`, `smart_str`, `force_bytes` and `smart_bytes`, and between the forms a URL takes, with `iri_to_uri`, `uri_to_iri`, `escape_uri_path`, `filepath_to_uri` and `punycode`.

Inside Django text is `str`, but it arrives and leaves as bytes: a request's path and body, a value to be hashed, what an external program prints. The first four functions convert a value of any type either way: UTF-8 unless the caller names another encoding, and a lazy value either kept or made a string at once. The rest write into the ASCII a URL may hold one kind of string each, a whole URL, a decoded path, a file's name or a domain, and `uri_to_iri` takes the first back in part.

## `force_str` and `smart_str`

`force_str` makes its argument a `str` (`django/utils/encoding.py:force_str`). An object whose type is `str` or a subclass is returned at once, so a `SafeString` stays safe. With `strings_only=True` a value of a protected type is returned as it is too: `None`, an integer or a boolean, a float, a decimal, a date, a time or a datetime (`django/utils/encoding.py:is_protected_type`). Bytes are decoded with the encoding and error handler given, `"utf-8"` and `"strict"` by default; anything else goes to `str`, which makes a lazy value call its function. A `UnicodeDecodeError` is raised again as `DjangoUnicodeDecodeError`, a subclass whose message adds the object and its type.

```text
# a run: a port's name, Málaga, and the example's FLEET
force_str(b"M\xc3\xa1laga")                 'Málaga'
force_str(b"M\xe1laga", "latin-1")          'Málaga'
force_str(b"M\xe1laga")                     raises DjangoUnicodeDecodeError: 'utf-8' codec can't decode byte 0xe1 in position 1: invalid continuation byte. You passed in b'M\xe1laga' (<class 'bytes'>)
force_str(None)                             'None'
force_str(None, strings_only=True)          None
force_str(FLEET)                            '2 ships in harbour'
smart_str(FLEET) is FLEET                   True
```

`smart_str` returns a `Promise` unchanged and passes anything else to `force_str` (`django/utils/encoding.py:smart_str`). The difference is when the text is fixed: a lazy translation from `django.utils.translation.gettext_lazy` translates at each use ([Lazy values: `lazy`, `Promise` and `keep_lazy`](lazy.md)), `smart_str` leaves it so, and `force_str` translates it now, into the language active at the call.

## `force_bytes` and `smart_bytes`

`force_bytes` makes its argument bytes, and takes bytes it is given to be UTF-8 (`django/utils/encoding.py:force_bytes`). Asked for `"utf-8"`, it returns them unchecked; asked for another encoding, it decodes them from UTF-8 and encodes them again, so, under the default error handler, bytes in that encoding that are not also UTF-8 fail with the standard library's `UnicodeDecodeError`. A protected type under `strings_only=True` is returned as it is, a `memoryview` copied into bytes, and anything else made a `str` and encoded.

```text
# a run
force_bytes(b"M\xc3\xa1laga", "latin-1")    b'M\xe1laga'
force_bytes(b"M\xe1laga", "latin-1")        raises UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe1 in position 1: invalid continuation byte
force_bytes(b"M\xe1laga")                   b'M\xe1laga'
smart_bytes(FLEET) is FLEET                 True
```

> **Trap.** `smart_bytes` returns a `Promise` unchanged, as `smart_str` does: a lazy value whose result class is `str` comes back as itself, not bytes (`django/utils/encoding.py:smart_bytes`).

`django/utils/crypto.py` makes each salt, secret and value bytes with `force_bytes` before hashing ([Secret keys and `django.utils.crypto`](../security/keys.md)) (`django/utils/crypto.py:salted_hmac`). `HttpResponseBase.make_bytes` does not use it for a response's body: its comment says `force_bytes` would re-encode bytes when the charset is not UTF-8 (`django/http/response.py:HttpResponseBase.make_bytes`).

## `iri_to_uri` and `uri_to_iri`

A URI is written in ASCII; an **IRI**, an Internationalized Resource Identifier (RFC 3987), may also hold characters outside ASCII. `iri_to_uri` turns the second into the first with `urllib.parse.quote`, writing each other character as the escaped bytes of its UTF-8. It leaves alone the reserved and unreserved characters of RFC 3986, which its comment lists, and `"%"`, which the end of RFC 3987's section 3.1 says must not be converted (`django/utils/encoding.py:iri_to_uri`). So an escape passes through, and the function can be given a whole URL quoted in part, or its own result: Django's documentation calls it idempotent (`docs/ref/unicode.txt`). `None` is returned as it is and a `Promise` made a string first. With it Django escapes a redirect's target into the `"Location"` header in `HttpResponseRedirectBase.__init__` ([The response object](../http/response.md#redirects)), the URL `HttpRequest.build_absolute_uri` returns ([Headers, host and scheme](../http/headers.md)), the prefixes of the static tags (`django/templatetags/static.py:PrefixNode.handle_simple`), a feed's links, and the `iriencode` filter's value ([The built-in filters](../templates/filters.md)).

`uri_to_iri` goes back only part of the way. It decodes an escape only where it stands for a letter, `"-"`, `"."`, `"_"` or `"~"`, RFC 3986's unreserved characters less the digits, or a byte from 128 up, part of a character of several bytes; an escaped reserved character such as `"%2F"`, or a space, stays escaped. `repercent_broken_unicode` then escapes again any byte that is not part of valid UTF-8, so the result always decodes (`django/utils/encoding.py:uri_to_iri`).

```text
# a run: links to the port Málaga
iri_to_uri("/ports/Málaga/?q=a%2Fb&name=Cap Ferrat")    '/ports/M%C3%A1laga/?q=a%2Fb&name=Cap%20Ferrat'
iri_to_uri(that result)                                 '/ports/M%C3%A1laga/?q=a%2Fb&name=Cap%20Ferrat'
uri_to_iri("/ports/M%C3%A1laga/%41%31%7E%2F%3F%20")     '/ports/Málaga/A%31~%2F%3F%20'
uri_to_iri("/ports/M%e1laga/")                          '/ports/M%E1laga/'
```

`repercent_broken_unicode` works in a loop, not by recursion, which its comment says is not to be used since the exception handling takes massive amounts of memory (CVE-2019-14235) (`django/utils/encoding.py:repercent_broken_unicode`). The WSGI handler passes a request's path through it before decoding the path ([Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md)) (`django/core/handlers/wsgi.py:get_path_info`). Nothing in Django calls `uri_to_iri`.

## `escape_uri_path` and `filepath_to_uri`

`escape_uri_path` escapes a path, and unlike `iri_to_uri` it escapes `"%"`, `"?"`, `"#"`, `";"`, `"="`, `"["` and `"]"`. Its comment builds the safe characters from lists it calls RFC 3986's (whose reserved lack the `"#"`, `"["` and `"]"` of `iri_to_uri`'s), less `";"`, `"="` and `"?"`, after the RFC's section 3.3, keeping `"/"` because the whole path is escaped, not a segment (`django/utils/encoding.py:escape_uri_path`). `HttpRequest._get_full_path`, behind `HttpRequest.get_full_path` and `HttpRequest.get_full_path_info`, escapes the request's path with it, and the query string with `iri_to_uri`, which leaves its escapes alone (`django/http/request.py:HttpRequest._get_full_path`). The WSGI handler takes PATH_INFO to be unescaped already, as CGI defines it, and decodes only its UTF-8 (`django/core/handlers/wsgi.py:get_path_info`), and takes QUERY_STRING as it was sent, leaving its escapes to `QueryDict` (`django/core/handlers/wsgi.py:WSGIRequest.GET`):

```text
# a run: a WSGIRequest, decoded path "/ports/Málaga/100% full/", query string "name=Cap%20Ferrat"
path               '/ports/Málaga/100% full/'
get_full_path()    '/ports/M%C3%A1laga/100%25%20full/?name=Cap%20Ferrat'
```

`filepath_to_uri` makes a stored file's name the path of a URL (`django/utils/encoding.py:filepath_to_uri`). It turns backslashes into slashes and escapes every character but `"/"` and those that JavaScript's encodeURIComponent keeps, to which its docstring points: a `"%"`, `"#"` or `"?"` in a file's name is escaped, and none is read as part of the URL. `FileSystemStorage.url` and `InMemoryStorage.url` join what it gives to the base URL: under /media/, the file charts/Málaga harbour.pdf has the URL /media/charts/M%C3%A1laga%20harbour.pdf ([File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)).

## `punycode` and the system's encoding

`punycode` writes a domain in the ASCII form of internationalized domain names, with the standard library's `"idna"` codec: málaga.example becomes `"xn--mlaga-xqa.example"`, and an ASCII domain comes back unchanged (`django/utils/encoding.py:punycode`). The mail code calls it on the domains of addresses and on the machine's name ([Email messages: `EmailMessage` and `EmailMultiAlternatives`](../services/email-messages.md)).

`get_system_encoding` returns the locale's encoding, from `locale.getlocale`, if Python has a codec for it, and `"ascii"` otherwise; its docstring cites tickets 10335 and 5846 (`django/utils/encoding.py:get_system_encoding`). It runs once, at import, for `DEFAULT_LOCALE_ENCODING`, with which the management commands' `popen_wrapper` decodes an external program's error output (`django/core/management/utils.py:popen_wrapper`).
