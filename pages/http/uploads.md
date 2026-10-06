---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Multipart parsing and upload handlers

How a body of type `"multipart/form-data"` becomes `POST` and `FILES`: `MultiPartParser` takes the body off the stream a chunk at a time, and passes each file's chunks through the request's upload handlers, which decide whether the file is held in memory or written to a temporary file.

A form that has a file field is sent as a **multipart** body: a sequence of parts, one for each field and each file, separated by a line the browser chose, the **boundary**, and each beginning with a few headers of its own that give the field's name and, for a file, its file name and content type. Parsing one would be simple if the body were a string. It is not treated as one, because a part may be a file larger than the memory the process should spend on a request. So the parser has to find boundaries in a stream it reads in pieces, including a boundary that falls across two pieces, and it must have somewhere to send a file's bytes as they arrive. Where they go is not the parser's decision. A site may want small files in memory, large ones on disk, some refused, or all of them sent straight to another service, and the request carries a list of handlers that settle it.

```text figure=the-parser
the request's stream, read 64 KB at a time by ChunkIter
  LazyStream                     the same bytes, with a way to push some back
    BoundaryIter                 the bytes up to the next boundary: one part
    parse_boundary_stream        the part's kind (raw, field or file), its headers, its content
  |
MultiPartParser._parse, for each part
  a field  ->  appended to POST
  a file   ->  each chunk passes along the upload handlers, in their order

                            MemoryFileUploadHandler          TemporaryFileUploadHandler
  a body that is small:     keeps the chunk in memory,       is given nothing
                            and returns None
  a body that is large:     returns the chunk unchanged  ->  writes it to a temporary file

  At the end of the part, the first handler to return an object from file_complete has made
  the entry in FILES: an InMemoryUploadedFile or a TemporaryUploadedFile.
```

*A multipart body on its way to `POST` and `FILES`. The stream is wrapped in iterators that cut it into parts, and each file part is fed, chunk by chunk, through the upload handlers.*

## Cutting the stream into parts

The parser's lower half is a set of small classes that wrap one another: iterators over bytes, and above them an iterator over parts (`django/http/multipartparser.py`).

`ChunkIter` reads the request in chunks of a fixed size. `LazyStream` wraps any such producer and adds the one operation the rest depends on: `LazyStream.unget` puts bytes back at the front, so that code which has read too far can return the excess. `BoundaryIter` reads from a `LazyStream` and yields the bytes of one part. It looks for the boundary in what it has read; when it finds it, it yields what came before, pushes back what came after, and stops. When it does not, it yields all but the last few bytes and pushes those back, as many as a boundary line is long, so that a boundary cut in two by the end of a chunk is found whole on the next pass (`django/http/multipartparser.py:BoundaryIter.__next__`).

`InterBoundaryIter` makes one `BoundaryIter` after another over the same stream, each wrapped in a `LazyStream` of its own, and so turns the body into a sequence of sub-streams, one for each part. The module's `Parser` class passes each to `parse_boundary_stream`, which reads the part's headers and classifies it: a part with a `Content-Disposition` header is a field, or a file if the header has a file name, and a part with no such header is **raw**, which is what the text before the first boundary and after the last amounts to. The headers of one part must fit in 1024 bytes, and a part whose headers run past that raises `MultiPartParserError` (`django/http/multipartparser.py:parse_boundary_stream`).

A stream that can be pushed back into can be made to loop, by input built so that the parser keeps returning the same bytes. `LazyStream` keeps a short history of the sizes pushed back and raises `SuspiciousMultipartForm` when the same size recurs too often (`django/http/multipartparser.py:LazyStream._update_unget_history`).

## What a handler is asked

A handler is a subclass of `FileUploadHandler`. The parser calls the methods below on the request's handlers, in the handlers' order, and what a method returns or raises is how a handler steers the upload (`django/core/files/uploadhandler.py:FileUploadHandler`).

| method | called | what the answer means |
|---|---|---|
| `handle_raw_input` | before parsing, on each handler in turn | a returned pair, of `POST` and `FILES`, replaces the whole parse, and the handlers after this one are not asked |
| `new_file` | at the start of each file, on each handler in turn | raising `StopFutureHandlers` ends the round: `new_file` is not called on the handlers after this one |
| `receive_data_chunk` | for each chunk of a file, on each handler in turn | what it returns is the chunk the next handler gets; `None` ends the chunk's journey |
| `file_complete` | at the end of each file, on each handler in turn | the first object returned is the file put into `FILES`, and the handlers after it are not asked |
| `upload_complete` | after the last part, on each handler in turn | a true value keeps the handlers after this one from being called |
| `upload_interrupted` | on every handler, if the last file begun was never completed: the body ended inside it, or a handler dropped it by raising `SkipFile` | |

*The methods `MultiPartParser` calls on an upload handler.*

A handler can also refuse, by raising. Raising `SkipFile` from `new_file` or `receive_data_chunk` drops that file and goes on with the rest of the form. Raising `StopUpload` abandons the upload: the parser stops, and then reads the rest of the body and throws it away, unless the exception was made with `connection_reset=True`, in which case it leaves the body unread; the docstring of the exception's constructor warns that a browser then reports a reset connection. Neither reaches the view as an exception: the view finds `POST` and `FILES` holding whatever was parsed, without the file (`django/http/multipartparser.py:MultiPartParser._parse`, `django/core/files/uploadhandler.py:StopUpload`).

## One upload, in order

This is a form with one text field and one small file, recorded as a view read `POST`. The calls of `parse_header_parameters`, which reads each header of a part, are left out. The line that says `new_file` raises `StopFutureHandlers` records an answer from the table above, not a failure.

```text recording=http
HttpRequest.parse_file_upload
  HttpRequest._initialize_handlers
    load_handler("django.core.files.uploadhandler.MemoryFileUploadHandler", request)
    load_handler("django.core.files.uploadhandler.TemporaryFileUploadHandler", request)
  MultiPartParser.__init__(META, input_data, upload_handlers, encoding=None)
  MultiPartParser.parse
    MemoryFileUploadHandler.handle_raw_input(content_length=251)
      -> None, and activated = True
    FileUploadHandler.handle_raw_input  (TemporaryFileUploadHandler)
      -> None
    HttpRequest.read(65536)
      LimitedStream.read(65536)
        -> 251 bytes
    parse_boundary_stream
      -> raw: no headers
    parse_boundary_stream
      -> field: name="customer"
    parse_boundary_stream
      -> file: name="notes", filename="notes.txt"
    MultiPartParser.sanitize_file_name('notes.txt')
      -> 'notes.txt'
    MemoryFileUploadHandler.new_file("notes", "notes.txt", "text/plain")
      raises StopFutureHandlers
    MemoryFileUploadHandler.receive_data_chunk(29 bytes, start=0)
      -> None: the chunk is kept, and goes no further
    parse_boundary_stream
      HttpRequest.read(65536)
        LimitedStream.read(65536)
          -> 0 bytes
      -> raw: no headers
    MultiPartParser.handle_file_complete("notes")
      MemoryFileUploadHandler.file_complete(29)
        -> <InMemoryUploadedFile: notes.txt (text/plain)>
    HttpRequest.read(65536)
      LimitedStream.read(65536)
        -> 0 bytes
    FileUploadHandler.upload_complete  (MemoryFileUploadHandler)
    FileUploadHandler.upload_complete  (TemporaryFileUploadHandler)
```

**The handlers are made for the request.** `HttpRequest.upload_handlers` is empty until something asks for it, and then `HttpRequest._initialize_handlers` imports each class named in `settings.FILE_UPLOAD_HANDLERS` and instantiates it with the request. A handler belongs to one request, and can keep state between its calls (`django/http/request.py:HttpRequest._initialize_handlers`, `django/core/files/uploadhandler.py:load_handler`).

**`MultiPartParser.__init__` checks before it reads.** The content type must be multipart and plain ASCII, and must name a boundary of acceptable characters and length; the content length must not be negative. Any failure raises `MultiPartParserError`. It also settles the chunk size: the smallest `chunk_size` among the handlers, 64 KB for the two here (`django/http/multipartparser.py:MultiPartParser.__init__`).

**Each handler is offered the whole input first.** `handle_raw_input` is called on each handler in turn before any parsing. A handler that returns a pair from it has taken over: the pair is used as `POST` and `FILES` and the parser does nothing more. Neither default handler does that, but `MemoryFileUploadHandler` uses the call to look at the size of the body, and decides here whether it will take part.

**Fields go to `POST`; files go to the handlers.** For each part, `MultiPartParser._parse` decodes a field's value and appends it to a `QueryDict`. For a file it cleans the file name, tells the handlers a file is starting, and feeds them its content as the part's stream yields it. A file is known to be complete only when the next part begins, so `handle_file_complete` runs at the top of the next turn of the loop, which is why it appears above after a further `parse_boundary_stream` (`django/http/multipartparser.py:MultiPartParser._parse`).

The chain is a pipeline for chunks and a first-answer-wins vote for the result, and the two default handlers use both. In the recording `MemoryFileUploadHandler.new_file` raised `StopFutureHandlers`, its `receive_data_chunk` kept the chunk and returned `None`, and its `file_complete` returned the file. The handler behind it was told nothing between `handle_raw_input` and `upload_complete`.

## Memory or disk

The same form was sent again with a second file of three million bytes.

```text recording=http
MemoryFileUploadHandler.handle_raw_input(content_length=3000395)
  -> None, and activated = False
...
MemoryFileUploadHandler.new_file("notes", "notes.txt", "text/plain")
TemporaryFileUploadHandler.new_file("notes", "notes.txt", "text/plain")
  TemporaryUploadedFile.__init__("notes.txt", ...)
MemoryFileUploadHandler.receive_data_chunk(29 bytes, start=0)
  -> the chunk, for the next handler
TemporaryFileUploadHandler.receive_data_chunk(29 bytes, start=0)
  -> None: the chunk is written to the file
parse_boundary_stream
  -> file: name="scan", filename="../scans/receipt.bin"
MultiPartParser.handle_file_complete("notes")
  MemoryFileUploadHandler.file_complete(29)
    -> None
  TemporaryFileUploadHandler.file_complete(29)
    -> <TemporaryUploadedFile: notes.txt (text/plain)>
MultiPartParser.sanitize_file_name('../scans/receipt.bin')
  -> 'receipt.bin'
MemoryFileUploadHandler.new_file("scan", "receipt.bin", "application/octet-stream")
TemporaryFileUploadHandler.new_file("scan", "receipt.bin", "application/octet-stream")
  TemporaryUploadedFile.__init__("receipt.bin", ...)
MemoryFileUploadHandler.receive_data_chunk(65141 bytes, start=0)
  -> the chunk, for the next handler
TemporaryFileUploadHandler.receive_data_chunk(65141 bytes, start=0)
  -> None: the chunk is written to the file
... 45 more reads of the stream and 45 more chunks, each chunk through the same calls; the last is 51275 bytes at start=2948725
parse_boundary_stream
  HttpRequest.read(65536)
    LimitedStream.read(65536)
      -> 0 bytes
  -> raw: no headers
MultiPartParser.handle_file_complete("scan")
  MemoryFileUploadHandler.file_complete(3000000)
    -> None
  TemporaryFileUploadHandler.file_complete(3000000)
    -> <TemporaryUploadedFile: receipt.bin (application/octet-stream)>
HttpRequest.read(65536)
  LimitedStream.read(65536)
    -> 0 bytes
FileUploadHandler.upload_complete  (MemoryFileUploadHandler)
FileUploadHandler.upload_complete  (TemporaryFileUploadHandler)
```

`MemoryFileUploadHandler` decides once, for the request, and what it measures is the body and not a file. `handle_raw_input` sets its `activated` flag to whether the body is no larger than `settings.FILE_UPLOAD_MAX_MEMORY_SIZE`, 2,621,440 bytes by default. Here it was larger, so the handler stood aside for both files: its `new_file` raised nothing, its `receive_data_chunk` handed every chunk on, and its `file_complete` returned nothing. The note of 29 bytes went to a temporary file on disk along with the scan, because it arrived in a large request. The setting has the same default as `settings.DATA_UPLOAD_MAX_MEMORY_SIZE` and a different job: that one refuses a body, and this one chooses where a file is kept (`django/core/files/uploadhandler.py:MemoryFileUploadHandler.handle_raw_input`).

For the size it prefers a measurement to a claim. If the stream it is given can seek, which an `ASGIRequest`'s can and so can a body already read into memory, it seeks to the end and uses the true size. A `WSGIRequest`'s stream cannot, and there it uses the `Content-Length`, which the `LimitedStream` under the request enforces.

`TemporaryFileUploadHandler` is the fallback and has no conditions. Its `new_file` makes a `TemporaryUploadedFile`, which opens a named temporary file in `settings.FILE_UPLOAD_TEMP_DIR`, or the system's temporary directory when that is `None`, with a name that ends in `".upload"` and the uploaded file's own extension. Each chunk is written to it, and `file_complete` rewinds it and returns it (`django/core/files/uploadhandler.py:TemporaryFileUploadHandler`, `django/core/files/uploadedfile.py:TemporaryUploadedFile`).

The temporary file lasts as long as the request. It is deleted when it is closed, and the request closes every uploaded file when the response is closed:

```text recording=http
the uploaded files' temporary files exist: [True, True]
the server calls close() on what it was given
HttpResponseBase.close  (HttpResponse)
  HttpRequest.close
    TemporaryUploadedFile.close
    TemporaryUploadedFile.close
  signal request_finished
the uploaded files' temporary files exist: [False, False]
```

A view that wants to keep an upload therefore has to put it somewhere before it returns, which saving it through a storage does. A storage on the local file system does not read a file that offers a path: it hands the temporary file to `file_move_safe`, which renames it into place where the system allows and copies it where it does not. Where the file was renamed, the close at the end of the request finds nothing to delete, which `TemporaryUploadedFile.close` allows for (`django/core/files/storage/filesystem.py:FileSystemStorage._save`, `django/core/files/move.py:file_move_safe`, `django/core/files/uploadedfile.py:TemporaryUploadedFile.close`).

## Files that do not arrive

Some forms look as if they carry a file and leave nothing in `FILES`, without raising anything.

```text recording=http
Two multipart forms that are not what they seem
    the small form above, cut off after 204 of its 251 bytes, inside the file  ->  POST is {'customer': ['Ada']}, FILES is {}
    a form whose one part is a file input left empty: name="photo"; filename=""  ->  POST is {'photo': ['']}, FILES is {}
```

A body that ends inside a file is not an error to the parser. The handlers are told through `upload_interrupted`, the file is dropped, and the view sees the fields that came before it.

A part is a file only if it has a file name. A file input that was left empty still sends a part, with an empty file name, and `parse_boundary_stream` classes it as a field: the input's name turns up in `POST` with an empty value (`django/http/multipartparser.py:MultiPartParser._parse`, `django/http/multipartparser.py:parse_boundary_stream`).

## Changing the handlers

A view or a middleware can replace or reorder `upload_handlers`, but only before the body is parsed. The property's setter raises `AttributeError` once `FILES` exists, and `HttpRequest.parse_file_upload` turns the list into an `ImmutableList` as parsing begins, so that a later attempt to append to it fails with a message saying why (`django/http/request.py:HttpRequest.upload_handlers`, `django/http/request.py:HttpRequest.parse_file_upload`).

Before the body is parsed is earlier than it sounds. With the CSRF middleware installed, a `POST` request's form is read in that middleware's `process_view`, to find the token, and that is before the view is called (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`).

The parser itself can be replaced in the same way and under the same condition, through `HttpRequest.multipart_parser_class`.

> **Changed in 6.1.** `multipart_parser_class` was added in that release. In the same release the parser began to decode a part sent with a `"base64"` transfer encoding strictly: invalid data in a file part raises `MultiPartParserError`, where before it could be passed over.

## The file objects

What lands in `FILES` is an `UploadedFile`, a subclass of the `File` wrapper that the rest of Django's file handling uses. It adds what the part's headers said: `content_type`, `charset`, and `content_type_extra` for all the parameters of the part's content type, the charset among them. Its `size` is the number of bytes the parser counted as it passed them to the handler, not anything the client declared (`django/core/files/uploadedfile.py:UploadedFile`).

The file's name is cleaned twice. `MultiPartParser.sanitize_file_name` undoes HTML character references, keeps only what follows the last slash or backslash, strips characters that cannot be printed, and drops the part altogether if nothing usable is left; in the second recording a client's `"../scans/receipt.bin"` reached the handlers as `"receipt.bin"`. The setter of `UploadedFile.name` then takes the base name again, shortens it to 255 characters, and passes it to `validate_file_name`, which refuses an empty name, `"."` and `".."`. The docstring of `sanitize_file_name` says plainly that the result is still text chosen by the client, to be treated as untrusted (`django/http/multipartparser.py:MultiPartParser.sanitize_file_name`, `django/core/files/uploadedfile.py:UploadedFile._set_name`, `django/core/files/utils.py:validate_file_name`).

A `TemporaryUploadedFile` has a path, from `temporary_file_path`, which is what lets a storage move it. An `InMemoryUploadedFile` wraps a `io.BytesIO`, and reports that it will never come in more than one chunk. `SimpleUploadedFile` is an in-memory file made from a name and bytes, with no request behind it (`django/core/files/uploadedfile.py:InMemoryUploadedFile`, `django/core/files/uploadedfile.py:SimpleUploadedFile`).
