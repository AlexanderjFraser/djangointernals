---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Multipart parsing: `MultiPartParser`

`MultiPartParser` turns a body of type `"multipart/form-data"` into `POST` and `FILES`. It reads the body from the request's stream a chunk at a time, cuts it into parts at the boundary, appends each field to `POST`, and passes each file's chunks to the request's upload handlers.

A form that has a file field is sent as a **multipart** body: a sequence of parts, one for each field and each file, separated by a line the browser chose, the **boundary**, and each beginning with a few headers of its own that give the field's name and, for a file, its file name and content type. Parsing one would be simple if the body were a string. It is not treated as one, because a part may be a file larger than the memory the process should spend on a request. So the parser has to find boundaries in a stream it reads in pieces, including a boundary that falls across two pieces, and it must have somewhere to send a file's bytes as they arrive. Where they go is not the parser's decision: the request carries a list of **upload handlers** that settle it, by default `MemoryFileUploadHandler` and then `TemporaryFileUploadHandler` ([Upload handlers and uploaded files](uploads.md)).

In the figure, follow a part down through the nest at the top, which cuts it out of the request's stream, and into the loop of `MultiPartParser._parse` below, which sends it where it belongs.

```text figure=the-parser
the request's stream
  ChunkIter                      reads it a chunk at a time: 64 KB with the handlers Django installs
    LazyStream                   the same bytes, with a way to push some back: unget
      BoundaryIter               the bytes up to the next boundary: one part
        parse_boundary_stream    the part's headers, and its kind: raw, field or file
        |
MultiPartParser._parse, for each part
  a field  ->  its value, decoded and appended to POST
  a file   ->  its chunks, one at a time  ->  the request's upload handlers, in their order,
                                              which decide where the file goes
```

*`MultiPartParser` over a request's stream. Each object of the nest reads from the one that encloses it, so that a part reaches `MultiPartParser._parse` already cut out of the stream; the box on the right is the request's upload handlers, drawn as one.*

## Cutting the stream into parts

`ChunkIter` reads the request in chunks; `LazyStream` wraps it and adds `LazyStream.unget`, which puts bytes back at the front; and `BoundaryIter` reads from the `LazyStream` the bytes of one part. Cutting the stream into parts has one difficulty: a boundary that the end of a chunk cuts in two, so that neither chunk holds it whole. `BoundaryIter` looks for the boundary in what it has read. When it finds it, it yields what came before, pushes back what came after, and stops. When it does not, it yields all but the last few bytes and pushes those back, as many as a boundary line is long, so that a boundary begun at the end of one chunk is found whole on the next pass (`django/http/multipartparser.py:BoundaryIter.__next__`).

A part is classed by its headers. A part with a Content-Disposition header is a field, or a file if the header has a file name, and a part with no such header is **raw**, which is what the text before the first boundary and after the last amounts to. The headers of one part must fit in 1024 bytes, and a part whose headers run past that raises `MultiPartParserError` (`django/http/multipartparser.py:parse_boundary_stream`).

## One upload, in order

`MultiPartParser.parse` offers each handler the whole input first, through `FileUploadHandler.handle_raw_input`, and a handler that returns a `POST` and a `FILES` of its own ends the parse there. Otherwise fields go to `POST` and files to the handlers, and at the end the handlers are told through `FileUploadHandler.upload_complete` (`django/http/multipartparser.py:MultiPartParser._parse`).

A view of the chapter's recorded shop reads `POST` for a form of one text field and one small file. The body is no larger than `settings.FILE_UPLOAD_MAX_MEMORY_SIZE`, so `MemoryFileUploadHandler.handle_raw_input` sets the handler's `activated` flag, which has it keep the request's files in memory ([Upload handlers and uploaded files](uploads.md#memory-or-disk)) (`django/core/files/uploadhandler.py:MemoryFileUploadHandler.handle_raw_input`). The parts come out in the body's order, raw, field, file and raw again; look at where `MultiPartParser.handle_file_complete` stands, after the last `parse_boundary_stream` and not after the file's one chunk.

```text recording=http
A multipart form with a small file: the body, 251 bytes, is under FILE_UPLOAD_MAX_MEMORY_SIZE (2621440)
...
                MultiPartParser.parse
                  MemoryFileUploadHandler.handle_raw_input(content_length=251)
                    -> None, and activated = True
                  ...
                  parse_boundary_stream
                    -> raw: no headers
                  parse_boundary_stream
                    ...
                    -> field: name="customer"
                  parse_boundary_stream
                    ...
                    -> file: name="notes", filename="notes.txt"
                  MultiPartParser.sanitize_file_name('notes.txt')
                    -> 'notes.txt'
                  MemoryFileUploadHandler.new_file("notes", "notes.txt", "text/plain")
                    raises StopFutureHandlers
                  MemoryFileUploadHandler.receive_data_chunk(29 bytes, start=0)
                    -> None: the chunk is kept, and goes no further
                  parse_boundary_stream
                    ...
                    -> raw: no headers
                  MultiPartParser.handle_file_complete("notes")
                    MemoryFileUploadHandler.file_complete(29)
                      -> <InMemoryUploadedFile: notes.txt (text/plain)>
                  ...
                  FileUploadHandler.upload_complete  (MemoryFileUploadHandler)
                  FileUploadHandler.upload_complete  (TemporaryFileUploadHandler)
                  ...
```

The parser decides what each part is, and nothing about where a file goes. A field's value is decoded and appended to `POST`. A file's name is cleaned, the handlers are told a file is starting, and its chunks go through them in their order; the `StopFutureHandlers` raised here is a handler's answer, not a failure ([Upload handlers and uploaded files](uploads.md#fileuploadhandler-what-a-handler-is-asked)). A file is known to be complete only when the next part begins, so `handle_file_complete` runs at the top of the next turn of the loop, and the first handler whose `FileUploadHandler.file_complete` returns a file makes the entry in `FILES` (`django/http/multipartparser.py:MultiPartParser._parse`, `django/http/multipartparser.py:MultiPartParser.handle_file_complete`).

## What `MultiPartParser.__init__` checks

`MultiPartParser.__init__` checks the request before it reads a byte of the body. The content type must be multipart and plain ASCII, and must name a boundary of acceptable characters and length. A request that fails raises `MultiPartParserError`, which becomes a 400 response ([How an exception becomes a response](../handlers/exceptions.md)) (`django/core/handlers/exception.py:response_for_exception`). The method also settles the chunk size: the smallest `FileUploadHandler.chunk_size` among the handlers, 64 KB for the two Django installs (`django/http/multipartparser.py:MultiPartParser.__init__`).

The parser goes by the Content-Length header, read from `META`. A header that is missing or not a number counts as zero, and a form of length zero is empty: `MultiPartParser._parse` returns an empty `POST` and `FILES` without reading the stream. A negative length raises `MultiPartParserError`. Otherwise the parser does not hold the body to the number: under WSGI the request's `LimitedStream` stops the body at the declared length, and under ASGI nothing does, so the parser reads the body's file to its end ([The body: `body`, `POST` and `FILES`](body.md)) (`django/http/multipartparser.py:MultiPartParser._parse`, `django/core/handlers/wsgi.py:LimitedStream`).

The form of one field and one small file above, made into an `ASGIRequest` around its body, shows both rules: a declared length of 5 cuts nothing short, and no header at all empties the form.

```text recording=http
ASGI: the multipart form of 251 bytes again, and what its Content-Length header says
    with Content-Length: 251, which is the body's length  ->  POST is {'customer': ['Ada']}, FILES is {'notes': ['InMemoryUploadedFile, 29 bytes']}
    with Content-Length: 5  ->  POST is {'customer': ['Ada']}, FILES is {'notes': ['InMemoryUploadedFile, 29 bytes']}
    with no Content-Length header  ->  POST is {}, FILES is {}
```

## Files that do not arrive

Some forms look as if they carry a file and leave nothing in `FILES`, without raising anything. The two below are a body cut off inside its file and a file input left empty, and the end of each line is what reading `POST` and `FILES` gave.

```text recording=http
Two multipart forms that are not what they seem
    the small form above, cut off after 204 of its 251 bytes, inside the file  ->  POST is {'customer': ['Ada']}, FILES is {}
    a form whose one part is a file input left empty: name="photo"; filename=""  ->  POST is {'photo': ['']}, FILES is {}
```

A body that ends inside a file is not an error to the parser. No next part begins, so the file is never completed: the handlers are told through `FileUploadHandler.upload_interrupted`, the file is dropped, and the view sees the fields that came before it (`django/http/multipartparser.py:MultiPartParser._parse`).

A part is a file only if it has a file name. A file input that was left empty still sends a part, with an empty file name, and `parse_boundary_stream` classes it as a field: the input's name turns up in `POST` with an empty value (`django/http/multipartparser.py:MultiPartParser._parse`, `django/http/multipartparser.py:parse_boundary_stream`).

A file name that cleans to nothing loses the part. `MultiPartParser.sanitize_file_name` undoes HTML character references, keeps only what follows the last slash or backslash, and strips the characters that cannot be printed. When it is left with an empty name, `"."` or `".."`, it returns `None`, and the parser goes on without reading the rest of the part: a part sent with the file name `"../"` between two fields leaves both fields in `POST` and nothing of itself in `POST` or `FILES` (`django/http/multipartparser.py:MultiPartParser.sanitize_file_name`, `django/http/multipartparser.py:MultiPartParser._parse`). An upload handler can drop a file too, by raising ([Upload handlers and uploaded files](uploads.md#fileuploadhandler-what-a-handler-is-asked)).

## Replacing the parser: `multipart_parser_class`

`HttpRequest.parse_file_upload` makes the parser from `HttpRequest.multipart_parser_class`, which is `MultiPartParser` unless a view or a middleware has set another. Like the upload handlers, it can be changed only before the body is parsed: its setter raises `RuntimeError` once `FILES` exists (`django/http/request.py:HttpRequest.parse_file_upload`, `django/http/request.py:HttpRequest.multipart_parser_class`).

> **New in 6.1.** `multipart_parser_class` was added in that release (`docs/releases/6.1.txt`).
