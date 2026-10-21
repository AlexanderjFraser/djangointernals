---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The body: `body`, `POST` and `FILES`

A request's body is read from one stream, in one of three ways: whole, through the property `HttpRequest.body`; as a form, through `POST` and `FILES`, which `HttpRequest._load_post_and_files` fills; or a piece at a time, through `HttpRequest.read`. The order of the reads decides what each finds, and settings such as `settings.DATA_UPLOAD_MAX_MEMORY_SIZE` limit what a client may send.

Everything else a request holds is small and already in memory. The body need be neither: it can be a megabyte of JSON or a gigabyte of video, and when the request object is made none of it has been looked at. It can be read in three ways, for three kinds of caller, among them a view that wants to process a large body without holding it, which reads it as a file. All three draw on one stream, and a stream is used up by being read.

## The stream

A `WSGIRequest` or an `ASGIRequest` has a file-like object, `_stream`, set by its constructor. A `WSGIRequest` wraps the server's input in a `LimitedStream`, which gives out at most the number of bytes the `Content-Length` header declared, and cannot seek: it does not override `io.IOBase.seekable`, which returns `False` (`django/core/handlers/wsgi.py:LimitedStream`). An `ASGIRequest` is handed the temporary file into which the handler has already received the whole body ([The two entry points](../handlers/entry.md#an-asgi-request)). That file can seek, and no `LimitedStream` stands in front of it, so a declared length does not cut the body short ([Making the request: `WSGIRequest` and `ASGIRequest`](request.md)) (`django/core/handlers/asgi.py:ASGIRequest.__init__`).

`HttpRequest` is itself readable as a file: `HttpRequest.read` and `HttpRequest.readline` pass straight through to the stream, and a request can be iterated by lines. Each of them first sets a flag, `_read_started`, which is how the rest of the class knows that someone has read from the stream directly. An `OSError` from the stream is raised again as `UnreadablePostError`, which is an `OSError` too (`django/http/request.py:HttpRequest.read`, `django/http/request.py:UnreadablePostError`).

## `body`

`HttpRequest.body` is the whole body as bytes. The first read of the property does the work, in an order that puts the cheap checks first (`django/http/request.py:HttpRequest.body`):

1. If `_read_started` is set, it raises `RawPostDataException`: what is left of the stream may not be the body.
2. It compares the `Content-Length` header with `settings.DATA_UPLOAD_MAX_MEMORY_SIZE`, and raises `RequestDataTooBig` if the header is larger, without reading a byte. A header that is missing or not a number counts as a length of 0.
3. If the stream can seek, it measures the stream and compares that as well. The header is the client's word, and may understate the body or be missing; under ASGI the body is already in a file whose true size can be had, so a body over the limit is refused there even when it came with no header.
4. It reads the stream to its end, closes it, keeps the bytes as `_body`, and replaces `_stream` with a `io.BytesIO` over them.

The last step is what makes `body` safe to combine with the other ways of reading: after it, `body` returns the kept bytes however often it is read, a form can be parsed from them, and the request can be read as a file once more, from the start.

## `POST` and `FILES`

`POST` and `FILES` are two views of one parse. Each is a property of `WSGIRequest` and `ASGIRequest` that looks for its stored value, `_post` or `_files`, and when it is missing calls `HttpRequest._load_post_and_files`, which sets both before it returns (`django/core/handlers/wsgi.py:WSGIRequest._get_post`, `django/core/handlers/wsgi.py:WSGIRequest.FILES`). What that method does depends on the method, the stream and the content type, tested in this order (`django/http/request.py:HttpRequest._load_post_and_files`):

| the request | `POST` | `FILES` | the stream |
|---|---|---|---|
| its method is not `"POST"` | empty | empty | untouched |
| something has read from the stream, and `body` was not read first | empty | empty | as the reader left it |
| its content type is `"multipart/form-data"` | the form's fields | the form's files | consumed by `MultiPartParser` and not kept, unless `body` was read first |
| its content type is `"application/x-www-form-urlencoded"` | the form's fields, parsed from `body` | empty | read by `body`, and kept |
| any other content type | empty | empty | untouched |

*What `HttpRequest._load_post_and_files` does, by the first row that applies. A multipart form whose declared length counts as 0 is taken for an empty one, its stream untouched.*

The table has consequences that are easy to get wrong.

Only a request whose method is `"POST"` has its form parsed. A `"PUT"` or a `"PATCH"` that carries a form is not parsed: both collections are empty and the bytes are in `body`. The same holds for JSON that is posted, whose content type is neither of the two form types.

A form of the ordinary kind must be UTF-8 (`django/http/request.py:HttpRequest._load_post_and_files`). If the request's `encoding` has been set, by a charset in its `Content-Type` or by code, to any name but `"utf-8"`, in either case of letters, `_load_post_and_files` raises `BadRequest`; an alias such as `"utf8"` is refused with the rest. Otherwise it parses the body as UTF-8 ([`QueryDict`](querydict.md#parsing-and-decoding) has what becomes of bytes that are not).

A multipart form is ordinarily parsed from the stream, without `body` being read. The parser is given the request itself to read from, as a file, and takes the body off the stream in chunks, keeping the fields and passing the files on to the upload handlers ([Multipart parsing: `MultiPartParser`](multipart.md), [Upload handlers and uploaded files](uploads.md)). If `body` was read first, it is given a `io.BytesIO` over the kept bytes. The parser reads the `Content-Length` header itself, and takes one that is missing, zero or not a number for an empty form, without looking at the stream (`django/http/multipartparser.py:MultiPartParser.__init__`, `django/http/multipartparser.py:MultiPartParser._parse`).

## The order of reads

Because the three ways of reading share the stream, the first read of a body decides what the others can still do. The figure starts from an unread body and follows each of the three first reads to what it leaves possible: only `body` leaves every other read open.

```text figure=the-stream
unread: the stream has not been touched
  |
  |-- body                 kept: the bytes are held as _body, and the stream is replaced by one
  |                        over them. body, POST and FILES work from here on, any number of
  |                        times, and the stream can be read once more.
  |
  |-- POST or FILES        parsed: the fields are held as _post and the files as _files; the bytes
  |   of a multipart form  went through the parser and are not kept. body raises
  |                        RawPostDataException, and read() returns nothing.
  |
  |-- read() or            started: _read_started is set. body raises RawPostDataException;
      readline()           POST and FILES are empty, and say nothing.
```

*The three things that can happen first to an unread body, and what each leaves possible. POST or FILES of an ordinary form reads body, and so takes the first branch; of a multipart form whose declared length counts as 0, it reads nothing.*

Each line below reads a fresh `WSGIRequest`, made by the recording's script without a handler, in two steps, for an ordinary form in the first group and a multipart form in the second. The lines to compare are those where `POST` comes before `body` or before `read()`, and those where eight bytes are read by hand before `POST`.

```text recording=http
The body's stream is read once: what can follow what
    a form (application/x-www-form-urlencoded), 19 bytes
      request.body, then request.POST  ->  POST is {'customer': ['Ada'], 'item': ['3']}
      request.body, then request.read()  ->  read() returns 19 bytes
      request.body, then request.read() twice  ->  read() returns 19 bytes, and then 0
      request.POST, then request.body  ->  body is 19 bytes
      request.POST, then request.read()  ->  read() returns 19 bytes
      request.read(8), then request.body  ->  raises RawPostDataException: You cannot access body after reading from request's data stream
      request.read(8), then request.POST  ->  POST is {}
      ...
    a multipart form (multipart/form-data), 102 bytes
      request.body, then request.POST  ->  POST is {'customer': ['Ada']}
      request.body, then request.read()  ->  read() returns 102 bytes
      request.body, then request.read() twice  ->  read() returns 102 bytes, and then 0
      request.POST, then request.body  ->  raises RawPostDataException: You cannot access body after reading from request's data stream
      request.POST, then request.read()  ->  read() returns 0 bytes
      request.read(8), then request.body  ->  raises RawPostDataException: You cannot access body after reading from request's data stream
      request.read(8), then request.POST  ->  POST is {}
      ...
```

Reading `body` first never spoils a later read. Its price is that the whole body is held in memory and must pass the limit on a body's size, below, which a multipart upload read through `POST` need not.

> **Trap.** A middleware that reads a few bytes of a request to inspect it leaves every view behind it with an empty form, and no exception says why: `_load_post_and_files` finds `_read_started` set and no kept body, and stores an empty `POST` and `FILES` (`django/http/request.py:HttpRequest._load_post_and_files`).

## The limits

Settings bound what a client can make Django hold in memory for one request, and each is enforced where the data is read.

| setting | default | counts |
|---|---|---|
| `settings.DATA_UPLOAD_MAX_MEMORY_SIZE` | 2,621,440 bytes | the body, when it is read through `body`; in a multipart form, the fields that are not files |
| `settings.DATA_UPLOAD_MAX_NUMBER_FIELDS` | 1000 | the pieces between ampersands of a query string or an ordinary form; the fields of a multipart form |
| `settings.DATA_UPLOAD_MAX_NUMBER_FILES` | 100 | the files of a multipart form |

*The limits on a request's data, each a setting that can be `None` to switch its check off. The exceptions are `RequestDataTooBig`, `TooManyFieldsSent` and `TooManyFilesSent`, in the table's order.*

The size of a body is checked by `HttpRequest._check_data_too_big`, on behalf of `body`. The number of those pieces is checked by `QueryDict.__init__`, which is why it holds for a query string as much as for a form. In a multipart form all three are checked by the parser as it goes, in `MultiPartParser._parse` (`django/http/request.py:HttpRequest._check_data_too_big`, `django/http/request.py:QueryDict.__init__`, `django/http/multipartparser.py:MultiPartParser._parse`).

None of them limits the size of an uploaded file, unless the body is read through `body`: the parser refuses a field of 3,000,000 bytes with `RequestDataTooBig`, but counts no byte of a file, and nothing else in `django.http` limits how large a multipart request read through `POST` may be (`django/http/multipartparser.py:MultiPartParser._parse`).

> **History.** Before Django 1.10 neither the size of a request's body nor the number of its parameters was limited. That release added the first two settings, to "help mitigate denial-of-service attacks via large requests", leaving file uploads out of the count, and warned that an application receiving unusually large form posts might need to tune them (`docs/releases/1.10.txt`). The number of files followed in February 2023: certain inputs to multipart forms could exhaust open files or memory (CVE-2023-24580), and the security releases 4.1.7, 4.0.10 and 3.2.18 added `settings.DATA_UPLOAD_MAX_NUMBER_FILES` (`docs/releases/4.1.7.txt`).

Because the limits are enforced when the data is read, the exception is raised wherever that happens: in a view, or earlier, in the CSRF middleware's look at `POST` (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`). All three are subclasses of `SuspiciousOperation`, which, raised inside the middleware chain with `settings.DEBUG` off, the wrapper around each of its layers turns into a 400 response, as it does a `MultiPartParserError` and the `BadRequest` of an ordinary form in a charset other than UTF-8 ([How an exception becomes a response](../handlers/exceptions.md)).

Under each refused request below, follow the view's read down to the line that raises and on to what the client got; the multipart form has `HttpRequest._mark_post_parse_error` twice, once under `_load_post_and_files` and once after it, where the others have it once.

```text recording=http
What is refused, by which exception, and what the client gets
    a query string of 1001 parameters; the view reads request.GET
      ...
      WSGIRequest.GET
        raises TooManyFieldsSent
      HttpRequest._mark_post_parse_error
      ...
      the client gets 400 Bad Request
    ...
    a form of 2621441 bytes; the view reads request.POST
      ...
      HttpRequest._load_post_and_files
        HttpRequest.body
          raises RequestDataTooBig
      HttpRequest._mark_post_parse_error
      ...
      the client gets 400 Bad Request
    ...
    a multipart form with 101 files; the view reads request.POST
      ...
      HttpRequest._load_post_and_files
        MultiPartParser.__init__
        MultiPartParser.parse
          raises TooManyFilesSent
        HttpRequest._mark_post_parse_error
      HttpRequest._mark_post_parse_error
      ...
      the client gets 400 Bad Request
    ...
```

`HttpRequest._mark_post_parse_error` sets `POST` and `FILES` to empty collections. `response_for_exception` calls it for the three exceptions of the limits, and `_load_post_and_files` calls it first, itself, before it lets a `MultiPartParserError` or a `TooManyFilesSent` out (`django/http/request.py:HttpRequest._mark_post_parse_error`, `django/core/handlers/exception.py:response_for_exception`).

> **Why.** Whatever builds the error response, an error view or the debug page, may read `POST`, and with nothing stored that read could start the parse again and raise the same exception from inside the error handling (`django/http/request.py:HttpRequest._load_post_and_files`, `django/core/handlers/exception.py:response_for_exception`, `django/views/debug.py:SafeExceptionReporterFilter.get_post_parameters`).
