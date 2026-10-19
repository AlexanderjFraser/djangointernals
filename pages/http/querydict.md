---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `QueryDict`

`QueryDict` is the type of `GET` and `POST`: a `MultiValueDict` that parses a query string or a form's body, decodes it with an encoding, counts its parameters against a limit, and, unless it was made mutable, is guarded against change.

A query string is not a dictionary. `?tag=new&tag=sale` gives one name two values, and a form does the same with a set of checkboxes or a multiple select. Yet most forms send one value under a name, and a list for each would be a burden. `QueryDict` serves both: it keeps every value, and gives one unless asked for all.

## A dictionary whose values are lists

The storage belongs to the base class, `MultiValueDict`, which is also the type of `FILES` ([Data structures: `MultiValueDict` and its neighbours](../utils/datastructures.md)). A `MultiValueDict` is a real `dict` in which every stored value is a list, with the reading methods changed to hide that. A subscript, `get`, `items` and `values` all give the last value of a key; `getlist` and `lists` give the whole list. The last value, not the first, is the one a subscript returns, so where a client repeats a parameter the later one wins (`django/utils/datastructures.py:MultiValueDict`, `django/utils/datastructures.py:MultiValueDict.__getitem__`).

A parameter sent with no value is kept, as an empty string, and is not the same as one that was not sent: the first is a key and the second raises `MultiValueDictKeyError`, a `KeyError`. In the dictionary below, `"tag"` was sent twice, `"empty"` with no value and `"missing"` not at all.

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
    ...
```

## Parsing and decoding

`QueryDict.__init__` is given the text to parse, as a string or as bytes, and the splitting is Python's own: `urllib.parse.parse_qsl`, told to keep blank values. Django adds three things around it (`django/http/request.py:QueryDict.__init__`).

It chooses the encoding. A `QueryDict` has one, the one its maker passed or else `settings.DEFAULT_CHARSET`, and percent-escapes are decoded with it. An escape that is not valid in the encoding does not fail: it becomes the Unicode replacement character.

It forgives bytes that are not in the encoding. Input given as bytes is decoded with the encoding; if that fails it is decoded as ISO-8859-1 instead, which accepts any bytes.

> **Why.** The comments beside the two attempts give the reason: a query string "normally contains URL-encoded data, a subset of ASCII", "but some user agents are misbehaving" and send bytes outside it (`django/http/request.py:QueryDict.__init__`).

One accented letter shows both rules: as a raw byte it is taken by the second attempt, and as an escape it becomes the replacement character unless the dictionary is given the encoding it was written in.

```text recording=http
...
QueryDict(b"name=caf\xe9")  (bytes that are not UTF-8)  ->  <QueryDict: {'name': ['café']}>
QueryDict("name=caf%E9")  (an escape that is not UTF-8)  ->  <QueryDict: {'name': ['caf�']}>
QueryDict("name=caf%E9", encoding="iso-8859-1")  ->  <QueryDict: {'name': ['café']}>
```

And it counts. The number of parameters is passed to `urllib.parse.parse_qsl` as a maximum, `settings.DATA_UPLOAD_MAX_NUMBER_FIELDS`, and Python's `ValueError` on exceeding it is raised again as `TooManyFieldsSent`. Because the limit is in the constructor, it holds for a query string as much as for a form ([The body: `body`, `POST` and `FILES`](body.md#the-limits)).

`QueryDict.urlencode` goes the other way and writes the dictionary as a query string, every value of every key, in order: inside Django, `reverse` uses it for a `query` given as a `QueryDict`, and the `querystring` template tag for the parameters it has merged (`django/http/request.py:QueryDict.urlencode`, `django/urls/base.py:reverse`, `django/template/defaulttags.py:querystring`).

## Immutability and the copy

The constructor ends by setting `QueryDict._mutable`, false unless the caller asked otherwise, and each method of the class that would change the dictionary first calls `QueryDict._assert_mutable`, which raises `AttributeError` on an immutable one. The `GET` and `POST` a server's request makes are immutable. The guard is in those methods alone, and a method the class inherits meets it only by calling one of them, as `MultiValueDict.update` does through `QueryDict.setlistdefault` (`django/http/request.py:QueryDict._assert_mutable`, `django/utils/datastructures.py:MultiValueDict.update`).

Code that needs a changed version takes a copy. `QueryDict.copy` returns a deep copy, and the copy is mutable; `copy.copy` gives a shallow one that is mutable too. On a mutable `QueryDict`, assigning by subscript replaces a key's whole list with the one value, and `QueryDict.appendlist` adds to it. A key or a value set by subscript, `setlist`, `appendlist` or `setdefault` is decoded with the dictionary's encoding if it is bytes and stored as it is otherwise. Past the guard, `update` decodes no value: under a key given as text, a value given as bytes is stored as bytes (`django/http/request.py:QueryDict.copy`, `django/utils/datastructures.py:MultiValueDict.__setitem__`, `django/http/request.py:bytes_to_text`).

The dictionary parsed in the first section refuses an assignment; its copy takes a new page and a third tag, and the original still writes itself out as it was parsed.

```text recording=http
...
q["page"] = "3"  ->  raises AttributeError: This QueryDict instance is immutable
c = q.copy(); c["page"] = "3"; c.appendlist("tag", "last")
c.urlencode()  ->  'tag=new&tag=sale&tag=last&page=3&empty='
q.urlencode()  ->  'tag=new&tag=sale&page=2&empty='
frozen = QueryDict("page=2"); frozen |= {"extra": ["1"]}  ->  <QueryDict: {'page': ['2'], 'extra': ['1']}>, and its _mutable is still False
...
```

> **Trap.** The in-place union, `|=`, changes an immutable `QueryDict` without complaint. `dict` supplies it, neither `MultiValueDict` nor `QueryDict` overrides it, and it stores what it is given without calling any guarded method: in the recording above, the dictionary called frozen gained a key and stayed immutable (`django/http/request.py:QueryDict`).

## Where one is made

Who makes a `QueryDict` decides what it parses, with which encoding, and whether it may be changed (`django/core/handlers/wsgi.py:WSGIRequest.GET`, `django/core/handlers/asgi.py:ASGIRequest.GET`, `django/http/request.py:HttpRequest._load_post_and_files`, `django/http/multipartparser.py:MultiPartParser._parse`).

| made by | from | decoded with | mutable |
|---|---|---|---|
| `WSGIRequest.GET` | the query string, as bytes | the request's encoding, or else the default charset | no |
| `ASGIRequest.GET` | the query string, as text decoded from UTF-8 | the default charset | no |
| `HttpRequest._load_post_and_files`, for a posted form of type `"application/x-www-form-urlencoded"` | the body | UTF-8 | no |
| `MultiPartParser`, for a posted multipart form | one field at a time, each decoded by the parser before it is appended | the request's encoding, or else the default charset | while parsing; frozen before it is returned |
| `HttpRequest._load_post_and_files`, for a request whose method is not `"POST"`, or a body of any other type | nothing: it is empty | nothing | no |
| `HttpRequest._mark_post_parse_error`, after a `MultiPartParserError`, `TooManyFilesSent` or, in the handler, an exceeded limit, or when the stream was read but `body` was not | nothing: it is empty | nothing | no |
| `MultiPartParser`, for a multipart body whose declared length is missing, zero or not a number | nothing: it is empty | nothing | no |
| `HttpRequest.__init__`, for a request made without a server | nothing: it is empty | nothing | yes |

*Every `QueryDict` a request makes.*
