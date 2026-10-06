---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `QueryDict`

`QueryDict` is the type of `GET` and `POST`: a `MultiValueDict` that parses a query string or a form's body, decodes it with an encoding, counts its parameters against a limit, and, unless it was made mutable, cannot be changed.

A query string is not a dictionary. `?tag=new&tag=sale` gives one name two values, and a form does the same with a set of checkboxes or a multiple select. Yet nearly all code that reads a parameter wants a single value and would be burdened by a list. `QueryDict` is built to serve both: it keeps every value, and gives the one most code wants unless asked for all.

## A dictionary whose values are lists

The storage belongs to the base class. A `MultiValueDict` is a real `dict` in which every stored value is a list, with the reading methods changed to hide that. A subscript, `get`, `items` and `values` all give the last value of a key; `getlist` and `lists` give the whole list. The last value, not the first, is the one a subscript returns, so where a client repeats a parameter the later one wins (`django/utils/datastructures.py:MultiValueDict`, `django/utils/datastructures.py:MultiValueDict.__getitem__`).

```text recording=http
QueryDict: one key, several values, and no changing it
    q = QueryDict("tag=new&tag=sale&page=2&empty=")
    q["tag"]  ->  'sale'
    q.getlist("tag")  ->  ['new', 'sale']
    q["empty"]  ->  ''
    q.get("missing")  ->  None
    q["missing"]  ->  raises MultiValueDictKeyError: 'missing'
    dict(q.items())  ->  {'tag': 'sale', 'page': '2', 'empty': ''}
    dict(q.lists())  ->  {'tag': ['new', 'sale'], 'page': ['2'], 'empty': ['']}
    q.dict()  ->  {'tag': 'sale', 'page': '2', 'empty': ''}
    q["page"] = "3"  ->  raises AttributeError: This QueryDict instance is immutable
    c = q.copy(); c["page"] = "3"; c.appendlist("tag", "last")
    c.urlencode()  ->  'tag=new&tag=sale&tag=last&page=3&empty='
    q.urlencode()  ->  'tag=new&tag=sale&page=2&empty='
    frozen = QueryDict("page=2"); frozen |= {"extra": ["1"]}  ->  <QueryDict: {'page': ['2'], 'extra': ['1']}>, and its _mutable is still False
```

A parameter sent with no value is kept, as an empty string, and is not the same as one that was not sent: the first is a key and the second raises `MultiValueDictKeyError`, a `KeyError`. Assigning by subscript replaces a key's whole list with the one value, and `appendlist` adds to it.

## Parsing and decoding

`QueryDict.__init__` is given the text to parse, as a string or as bytes, and the splitting is Python's own: `urllib.parse.parse_qsl`, told to keep blank values. Django adds three things around it (`django/http/request.py:QueryDict.__init__`).

It chooses the encoding. A `QueryDict` has one, the one its maker passed or else `settings.DEFAULT_CHARSET`, and percent-escapes are decoded with it. An escape that is not valid in the encoding does not fail: it becomes the Unicode replacement character.

It forgives bytes that are not in the encoding. Input given as bytes is decoded with the encoding; if that fails it is decoded as ISO-8859-1 instead, which accepts any bytes. The comment beside the second attempt blames misbehaving user agents.

```text recording=http
QueryDict(b"name=caf\xe9")  (bytes that are not UTF-8)  ->  <QueryDict: {'name': ['café']}>
QueryDict("name=caf%E9")  (an escape that is not UTF-8)  ->  <QueryDict: {'name': ['caf�']}>
QueryDict("name=caf%E9", encoding="iso-8859-1")  ->  <QueryDict: {'name': ['café']}>
```

And it counts. The number of parameters is passed to `urllib.parse.parse_qsl` as a maximum, `settings.DATA_UPLOAD_MAX_NUMBER_FIELDS`, and Python's `ValueError` on exceeding it is raised again as `TooManyFieldsSent`. Parsing a string of parameters costs time and memory in proportion to their number, and the limit is what stops a request with a million of them. Because the limit is in the constructor, it holds for a query string as much as for a form ([The body](body.md#the-limits)).

## Why it cannot be changed

The constructor ends by setting `QueryDict._mutable`, false unless the caller asked otherwise, and each method of the class that would change the dictionary first calls `QueryDict._assert_mutable`, which raises `AttributeError` on an immutable one. The `GET` and `POST` a server's request makes are immutable, so a layer that reads them sees what the client sent and not what an earlier layer made of it. The guard is in those methods and nowhere else: the in-place union operator, which `dict` supplies and `QueryDict` does not override, changes an immutable one without complaint, as the last line of the recording above shows (`django/http/request.py:QueryDict._assert_mutable`).

Code that needs a changed version takes a copy. `QueryDict.copy` returns a deep copy, and the copy is mutable; `copy.copy` gives a shallow one that is mutable too. The original is untouched: in the first recording of this section the copy's page was changed and it gained a tag, and the original wrote itself out as before. On a mutable `QueryDict`, a key or a value set by subscript, `setlist`, `appendlist` or `setdefault` is decoded with the dictionary's encoding if it is bytes and stored as it is otherwise; `update`, which the class inherits, stores what it is given (`django/http/request.py:QueryDict.copy`, `django/http/request.py:bytes_to_text`).

`QueryDict.urlencode` goes the other way and writes the dictionary as a query string, every value of every key, in order. Its one argument names characters to leave unescaped (`django/http/request.py:QueryDict.urlencode`).

```text recording=http
QueryDict("next=/a%26b/").urlencode()  ->  'next=%2Fa%26b%2F'
QueryDict("next=/a%26b/").urlencode(safe="/")  ->  'next=/a%26b/'
```

## Where one is made

| made by | from | decoded with | mutable |
|---|---|---|---|
| `WSGIRequest.GET` | the query string, as bytes | the request's encoding | no |
| `ASGIRequest.GET` | the query string, as text | the default charset | no |
| `HttpRequest._load_post_and_files`, for a posted form of type `"application/x-www-form-urlencoded"` | the body | UTF-8 | no |
| `MultiPartParser`, for a posted multipart form | one field at a time, each decoded by the parser before it is appended | the request's encoding | while parsing; frozen before it is returned |
| `HttpRequest._load_post_and_files`, for a request whose method is not `"POST"` and for a body of any other type; `HttpRequest._mark_post_parse_error`, after a parse has failed or when the stream has already been read; `MultiPartParser`, for a body with no declared length or a length of zero | nothing: it is empty | | no |
| `HttpRequest.__init__`, for a request made without a server | nothing: it is empty | | yes |

*Every `QueryDict` a request makes.*

The multipart parser is the one caller that builds a `QueryDict` by hand. It makes a mutable one, appends each field as it reads it, and sets `_mutable` to false itself before handing the dictionary back (`django/http/multipartparser.py:MultiPartParser._parse`).

`MultiValueDict` is also the type of `FILES`, with uploaded files as its values, and is one of the data structures of [The utility layer](../utils.md).
