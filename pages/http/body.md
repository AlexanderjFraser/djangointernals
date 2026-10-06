---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The body: `body`, `POST` and `FILES`

How a request's body is read: the stream under `HttpRequest.read`, the `body` property that reads it whole and keeps it, `HttpRequest._load_post_and_files`, which fills `POST` and `FILES` from it, what may be read after what, and the limits on what a client may send.

Everything else a request holds is small and already in memory. The body is neither: it can be a megabyte of JSON or a gigabyte of video, and when the request object is made none of it has been looked at. A request offers three ways to read it, for three kinds of caller. It can be read as a file, a piece at a time, by a view that wants to process a large body without holding it. It can be read whole, as bytes. Or it can be read as a form, which is what `POST` and `FILES` are. All three draw on one stream, and a stream is used up by being read.

## The stream

Each request has a file-like object, `_stream`, set by the subclass that made it. A `WSGIRequest` wraps the server's input in a `LimitedStream`, which cannot seek and gives out at most the number of bytes the `Content-Length` header declared. An `ASGIRequest` is handed the temporary file into which the handler has already received the whole body, and that file can seek ([Making the request](request.md)).

`HttpRequest` is itself readable as a file: `HttpRequest.read` and `HttpRequest.readline` pass straight through to the stream, and a request can be iterated by lines. Each of them first sets a flag, `_read_started`, which is how the rest of the class knows that someone has taken bytes from the stream directly. An `OSError` from the stream is raised again as `UnreadablePostError`, which is an `OSError` too, so that code which reads a form can tell a failed read from any other failure (`django/http/request.py:HttpRequest.read`, `django/http/request.py:UnreadablePostError`).

## `body`

`HttpRequest.body` is the whole body as bytes. The first read of the property does the work, in an order that puts the cheap checks first (`django/http/request.py:HttpRequest.body`):

1. If `_read_started` is set, it raises `RawPostDataException`: part of the stream is gone, and what is left is not the body.
2. It compares the `Content-Length` header with `settings.DATA_UPLOAD_MAX_MEMORY_SIZE`, and raises `RequestDataTooBig` if the header is larger, without reading a byte.
3. If the stream can seek, it measures the stream and compares that as well. The header is the client's word; under ASGI the body is already in a file whose true size can be had, and may be larger than the header said or have come with no header at all.
4. It reads the stream to its end, closes it, and keeps the bytes as `_body`.
5. It replaces `_stream` with a `io.BytesIO` over those bytes.

The last two steps are what make `body` safe to combine with the other ways of reading. After it, `body` returns the kept bytes however often it is read, a form can be parsed from them, and the request can be read as a file once more, from the start.

## `POST` and `FILES`

`POST` and `FILES` are two views of one parse. Each is a property that looks for its stored value, `_post` or `_files`, and when it is missing calls `HttpRequest._load_post_and_files`, which sets both before it returns. What that method does depends on the method and the content type, tested in this order (`django/http/request.py:HttpRequest._load_post_and_files`):

| the request | `POST` | `FILES` | the stream |
|---|---|---|---|
| its method is not `"POST"` | empty | empty | untouched |
| something has read from the stream, and `body` was not read first | empty | empty | as the reader left it |
| its content type is `"multipart/form-data"` | the form's fields | the form's files | consumed by `MultiPartParser`; nothing is kept |
| its content type is `"application/x-www-form-urlencoded"` | the form's fields, parsed from `body` | empty | read by `body`, and kept |
| any other content type | empty | empty | untouched |

*What `HttpRequest._load_post_and_files` does, by the first row that applies.*

The table has consequences that are easy to get wrong.

Only a request whose method is `"POST"` has a `POST`. A `"PUT"` or a `"PATCH"` that carries a form is not parsed: both collections are empty and the bytes are in `body`. The same holds for JSON that is posted, whose content type is neither of the two form types.

A form of the ordinary kind must be UTF-8. If the request's `encoding` has been set, by a charset in its `Content-Type` or by code, to any name but `"utf-8"`, in either case of letters, `_load_post_and_files` raises `BadRequest`; an alias such as `"utf8"` is refused with the rest. Otherwise it parses the body as UTF-8 ([`QueryDict`](querydict.md#parsing-and-decoding) has what becomes of bytes that are not). The comment beside the check gives the reason: the specification of this content type gives it no charset parameter.

A multipart form is parsed without the body being read whole. The parser is given the request itself to read from, as a file, and takes the body off the stream in chunks, keeping the fields and passing the files on ([Multipart parsing and upload handlers](uploads.md)). If `body` was read first, it is given a `io.BytesIO` over the kept bytes.

## What can follow what

So the order in which a request is read matters. These are the orders of two reads, and two longer sequences, for a body of each form type, recorded.

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
      request.POST, then request.encoding = "utf-8", then request.POST  ->  POST is {'customer': ['Ada'], 'item': ['3']}
    a multipart form (multipart/form-data), 102 bytes
      request.body, then request.POST  ->  POST is {'customer': ['Ada']}
      request.body, then request.read()  ->  read() returns 102 bytes
      request.body, then request.read() twice  ->  read() returns 102 bytes, and then 0
      request.POST, then request.body  ->  raises RawPostDataException: You cannot access body after reading from request's data stream
      request.POST, then request.read()  ->  read() returns 0 bytes
      request.read(8), then request.body  ->  raises RawPostDataException: You cannot access body after reading from request's data stream
      request.read(8), then request.POST  ->  POST is {}
      request.POST, then request.encoding = "utf-8", then request.POST  ->  POST is {}
```

Reading `body` first never spoils a later read. Its price is that the whole body is held in memory and must pass the limit on a body's size, below, which a multipart upload read through `POST` need not. For an ordinary form `POST` reads `body` itself, so the two are interchangeable; for a multipart form they are not, because the bytes that went through the parser were not kept. After `body` the stream can be read through once more, and is then at its end. The last line of each group is the setter of the request's `encoding` at work, which discards the stored form. Here the encoding assigned was UTF-8: the ordinary form was parsed again from the kept bytes, and the multipart form, parsed from the stream, came back empty ([Making the request](request.md#the-content-type-and-the-encoding)).

The line to remember is the one that reads eight bytes and then `POST`. A read from the stream by hand makes `body` raise, which is at least loud. It makes `POST` empty without a word. A middleware that reads a few bytes of a request to inspect it leaves every view behind it with an empty form.

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

*The three things that can happen first to an unread body, and what each leaves possible. POST or FILES of an ordinary form reads body, and so takes the first branch.*

## The limits

Settings bound what a client can make Django hold in memory for one request, and each is enforced where the data is read.

| setting | default | counts |
|---|---|---|
| `settings.DATA_UPLOAD_MAX_MEMORY_SIZE` | 2,621,440 bytes | the body, when it is read through `body`; in a multipart form, the fields that are not files |
| `settings.DATA_UPLOAD_MAX_NUMBER_FIELDS` | 1000 | the parameters of a query string or an ordinary form; the fields of a multipart form |
| `settings.DATA_UPLOAD_MAX_NUMBER_FILES` | 100 | the files of a multipart form |

*The limits on a request's data, each a setting that can be `None` to switch its check off. The exceptions are `RequestDataTooBig`, `TooManyFieldsSent` and `TooManyFilesSent`, in the table's order.*

The size of a body is checked by `HttpRequest._check_data_too_big`, on behalf of `body`. The number of parameters is checked by `QueryDict.__init__`, which is why it holds for a query string as much as for a form. Everything about a multipart form is counted by the parser as it goes, in `MultiPartParser._parse` (`django/http/request.py:HttpRequest._check_data_too_big`, `django/http/multipartparser.py:MultiPartParser._parse`).

None of them limits the size of an uploaded file. Files are the part of a body that Django does not keep in memory past a threshold, so they are outside what these settings protect, and nothing in `django.http` puts a ceiling on the size of a file, or of a multipart request as it is parsed into `POST` and `FILES`.

The limits are enforced when the data is read, which means the exception is raised wherever that happens: in a view, or earlier, in the CSRF middleware's look at `POST`. All three exceptions are subclasses of `SuspiciousOperation`, and the wrapper around each layer of the middleware chain turns that into a 400 response ([How an exception becomes a response](../handlers/exceptions.md)). In the recording below, the lines of each request's construction are left out.

```text recording=http
a query string of 1001 parameters; the view reads request.GET
  WSGIRequest.GET
    raises TooManyFieldsSent
  HttpRequest._mark_post_parse_error
  logged by django.security.TooManyFieldsSent at ERROR: The number of GET/POST parameters exceeded settings.DATA_UPLOAD_MAX_NUMBER_FIELDS.
  the client gets 400 Bad Request
...
a form of 2621441 bytes; the view reads request.POST
  HttpRequest._load_post_and_files
    HttpRequest.body
      raises RequestDataTooBig
  HttpRequest._mark_post_parse_error
  logged by django.security.RequestDataTooBig at ERROR: Request body exceeded settings.DATA_UPLOAD_MAX_MEMORY_SIZE.
  the client gets 400 Bad Request
...
a multipart form with 101 files; the view reads request.POST
  HttpRequest._load_post_and_files
    MultiPartParser.__init__
    MultiPartParser.parse
      raises TooManyFilesSent
    HttpRequest._mark_post_parse_error
  HttpRequest._mark_post_parse_error
  logged by django.security.TooManyFilesSent at ERROR: The number of files exceeded settings.DATA_UPLOAD_MAX_NUMBER_FILES.
  the client gets 400 Bad Request
```

One call stands between the exception and the response. `HttpRequest._mark_post_parse_error` sets `POST` and `FILES` to empty collections, because whatever builds the error response, an error view or the debug page, is likely to read `POST`, and with nothing stored that read would start the parse again and raise the same exception from inside the error handling. `response_for_exception` calls it for these three exceptions, and `_load_post_and_files` calls it itself before it lets a `MultiPartParserError` or a `TooManyFilesSent` out, which is why the last request above shows it twice (`django/http/request.py:HttpRequest._mark_post_parse_error`, `django/core/handlers/exception.py:response_for_exception`).

Two more refusals come from the form types themselves and are not suspicious, only wrong: a multipart request the parser refuses, for want of a usable boundary for one, raises `MultiPartParserError`, and an ordinary form in a charset other than UTF-8 raises `BadRequest`. Both become a 400 as well, logged as a warning by the logger `"django.request"`, where the three above go to a logger under `"django.security"` as errors.

## Under ASGI

The rules are the same and the stream is not. The handler has received the whole body before the request exists, whatever its size and before any middleware could refuse it, into a temporary file that moves from memory to disk past `settings.FILE_UPLOAD_MAX_MEMORY_SIZE`. Nothing is waiting on a socket, and the stream can seek. `body` still compares the `Content-Length` header with the limit first, and then measures the file as well, so a body over `settings.DATA_UPLOAD_MAX_MEMORY_SIZE` is refused even when it came with no header. There is no `LimitedStream`, so a declared length does not cut the body short (`django/core/handlers/asgi.py:ASGIHandler.read_body`).

The header decides one thing more, in the multipart parser, which reads it from `META` and treats a `Content-Length` that is missing, zero or not a number as an empty form, without looking at the stream (`django/http/multipartparser.py:MultiPartParser.__init__`). The form in this recording is the one the next section follows, a field and a small file:

```text recording=http
ASGI: the multipart form of 251 bytes again, and what its Content-Length header says
    with Content-Length: 251, which is the body's length  ->  POST is {'customer': ['Ada']}, FILES is {'notes': ['InMemoryUploadedFile, 29 bytes']}
    with Content-Length: 5  ->  POST is {'customer': ['Ada']}, FILES is {'notes': ['InMemoryUploadedFile, 29 bytes']}
    with no Content-Length header  ->  POST is {}, FILES is {}
```

## The end of the request

`HttpRequest.close` closes every file in `FILES`, if the request ever parsed any, and an `ASGIRequest` closes its stream as well. Nothing in `django.http` calls it. The handler registers it on the response, and it runs when the response is closed ([Streaming and file responses](streaming.md#closing)) (`django/http/request.py:HttpRequest.close`, `django/core/handlers/asgi.py:ASGIRequest.close`).
