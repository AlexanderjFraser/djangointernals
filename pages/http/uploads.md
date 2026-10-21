---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Upload handlers and uploaded files

An upload handler, a subclass of `FileUploadHandler`, decides where the bytes of an uploaded file go as `MultiPartParser` passes them on. The two that Django installs, `MemoryFileUploadHandler` and `TemporaryFileUploadHandler`, keep the files of a request no larger than `settings.FILE_UPLOAD_MAX_MEMORY_SIZE` in memory and write the others to temporary files, and what lands in `FILES` is an `UploadedFile`: an `InMemoryUploadedFile` or a `TemporaryUploadedFile`.

The multipart parser finds the files in a body and must send each one's bytes somewhere as they arrive ([Multipart parsing: `MultiPartParser`](multipart.md)). Where is not its decision. A site may want small files in memory, large ones on disk, some refused, or all of them sent straight to another service, and the request carries a list of handlers that settle it, `HttpRequest.upload_handlers`. The list works in two ways at once: for a file's chunks it is a pipeline, each handler passing on what it does not keep, and for the file that results the first handler to return one decides, and the handlers after it are not asked.

## `FileUploadHandler`: what a handler is asked

A handler is a subclass of `FileUploadHandler`. The parser calls the methods below on the request's handlers, in the handlers' order, and what a method returns or raises is how a handler steers the upload (`django/core/files/uploadhandler.py:FileUploadHandler`).

| method | called | what the answer means |
|---|---|---|
| `handle_raw_input` | before parsing, on each handler in turn | a returned pair, of `POST` and `FILES`, replaces the whole parse, and the handlers after this one are not asked |
| `new_file` | at the start of each file, on each handler in turn | raising `StopFutureHandlers` ends the round: `new_file` is not called on the handlers after this one |
| `receive_data_chunk` | for each chunk of a file, on each handler in turn | what it returns is the chunk the next handler gets; `None` ends the chunk's journey |
| `file_complete` | at the end of each file, on each handler in turn | the first object returned is the file put into `FILES`, and the handlers after it are not asked |
| `upload_complete` | at the end of the parse, on each handler in turn | a true value keeps the handlers after this one from being called |
| `upload_interrupted` | after the last part, on every handler, if the body ended inside the last file begun, or a handler dropped that file by raising `SkipFile` | nothing is done with what it returns; `TemporaryFileUploadHandler` closes and deletes its temporary file |

*The methods `MultiPartParser` calls on an upload handler.*

A handler can also refuse, by raising from `new_file` or `receive_data_chunk`. `SkipFile` drops that file: the parser reads the rest of the part, throws it away, and goes on with the parts after it. `StopUpload` abandons the upload: the parser keeps what it has parsed and stops, and then reads the rest of the body and throws it away, unless the exception was made with `connection_reset=True`, in which case it leaves the rest unread. Neither reaches the view as an exception (`django/http/multipartparser.py:MultiPartParser._parse`, `django/core/files/uploadhandler.py:StopUpload.__init__`).

The chapter's recording raised each exception from an upload handler of its own, put first, for the second of two files in a form of 200,462 bytes: a field, a note of 29 bytes, a scan of 200,000 bytes, and a second field. Compare the rows on the field that follows the scan, on the note, and on how much of the body is read.

| raised | `POST` | `FILES` | the body read |
|---|---|---|---|
| `SkipFile`, from `new_file` | both fields | the note, closed | all 200,462 bytes |
| `SkipFile`, from `receive_data_chunk` | both fields | the note, readable | all 200,462 bytes |
| `StopUpload`, from `new_file` | the first field | the note, closed | all 200,462 bytes |
| `StopUpload`, from `receive_data_chunk` | the first field | the note, readable | all 200,462 bytes |
| `StopUpload(connection_reset=True)`, from `receive_data_chunk` | the first field | the note, readable | 65,536 bytes, one chunk |

*What reached `POST` and `FILES`, and how much of the request's stream was read, when an upload handler raised for the scan, as recorded.*

> **Trap.** Raised from `new_file`, either exception can close a file already in `FILES`. The handlers Django installs keep the file they are building as their `file` attribute, set in `new_file`, and the parser answers both exceptions by closing the `file` of every handler that has one (`django/http/multipartparser.py:MultiPartParser._close_files`). A handler whose `new_file` has not yet run for the new file still holds the one before: where `new_file` raised, `MemoryFileUploadHandler` stood after the raising handler and still held the note; where `receive_data_chunk` raised, `MemoryFileUploadHandler.new_file` had already given that handler a new file.

## Memory or disk

The two handlers Django installs divide files between memory and disk, and they divide them by the request. `MemoryFileUploadHandler` decides once, in `handle_raw_input`, whether it will keep the files: it sets its `activated` flag to whether the body is no larger than `settings.FILE_UPLOAD_MAX_MEMORY_SIZE`, 2,621,440 bytes by default (`django/core/files/uploadhandler.py:MemoryFileUploadHandler.handle_raw_input`). The setting has the same default as `settings.DATA_UPLOAD_MAX_MEMORY_SIZE` and a different job: that one refuses a body read whole, or a form's fields, and this one chooses between memory and disk.

> **Why.** For the body's size the handler prefers a measurement to the header. If the stream can seek, as an `ASGIRequest`'s can under `ASGIHandler` and a body already read into memory can, it seeks to the end and uses the true size; a `WSGIRequest`'s cannot, and there it uses the Content-Length, past which its stream reads nothing. An `ASGIRequest`'s stream holds the whole body whatever the header says, and until 6.0.5 and 5.2.14 one whose header understated a large body as small had its files kept in memory (CVE-2026-5766) (`django/core/files/uploadhandler.py:MemoryFileUploadHandler.handle_raw_input`, `django/core/handlers/wsgi.py:LimitedStream.read`, `django/core/handlers/asgi.py:ASGIHandler.read_body`, `docs/releases/6.0.5.txt`).

Activated, the handler takes each file whole and tells the handler behind it nothing of it: its `new_file` raises `StopFutureHandlers`, its `receive_data_chunk` keeps each chunk in memory and returns `None`, and its `file_complete` returns an `InMemoryUploadedFile`. Not activated, it hands each chunk on unchanged and returns no file, and `TemporaryFileUploadHandler` writes the chunks to a temporary file and returns a `TemporaryUploadedFile` (`django/core/files/uploadhandler.py:MemoryFileUploadHandler`). In the figure, read each row across, as a chunk goes.

```text figure=the-handlers
                         MemoryFileUploadHandler                     TemporaryFileUploadHandler

a body no larger than    receive_data_chunk: keeps the chunk         is told nothing of the file
FILE_UPLOAD_MAX_         in memory, and returns None
MEMORY_SIZE              file_complete: returns an
(activated = True)       InMemoryUploadedFile  ---------------------------------------------->  FILES

a larger body            receive_data_chunk: hands the chunk on  ->  receive_data_chunk: writes it to a
(activated = False)      unchanged                                   temporary file, and returns None
                         file_complete: returns None                 file_complete: returns the
                                                                     TemporaryUploadedFile  ->  FILES
```

*The two handlers Django installs, for a small body and a large one. Each row reads from left to right, as a chunk goes: an arrow is the chunk handed on, or the file that `file_complete` gives to `FILES`.*

A body over the threshold gives the second row: the chapter's recorded shop is posted a field, a note of 29 bytes and a scan of 3,000,000. Follow the note under `activated = False`: both handlers hear of it, the first hands its chunk on, and the second writes it and returns the file.

```text recording=http
The same form with a second file of 3,000,000 bytes: the body, 3000395 bytes, is over FILE_UPLOAD_MAX_MEMORY_SIZE (2621440)
...
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
                  ...
                  MultiPartParser.handle_file_complete("notes")
                    MemoryFileUploadHandler.file_complete(29)
                      -> None
                    TemporaryFileUploadHandler.file_complete(29)
                      -> <TemporaryUploadedFile: notes.txt (text/plain)>
                  MultiPartParser.sanitize_file_name('../scans/receipt.bin')
                    -> 'receipt.bin'
                  ...
```

> **Trap.** `MemoryFileUploadHandler` goes by the body, not the file. The note of 29 bytes went to disk with the scan because it arrived in a large request: a file is kept in memory only when the whole body is small enough (`django/core/files/uploadhandler.py:MemoryFileUploadHandler.handle_raw_input`).

## The temporary file

`TemporaryFileUploadHandler` is the fallback and has no conditions. Its `new_file` makes a `TemporaryUploadedFile`, which opens a named temporary file in `settings.FILE_UPLOAD_TEMP_DIR`, or the system's temporary directory when that is `None`. Each chunk is written to it, and `file_complete` rewinds it and returns it (`django/core/files/uploadhandler.py:TemporaryFileUploadHandler`, `django/core/files/uploadedfile.py:TemporaryUploadedFile`).

The temporary file ordinarily lasts as long as the request: it is deleted when it is closed, and it is closed with the response ([Streaming and file responses](streaming.md#closing)). At the end of the request that posted the note and the scan, their two temporary files are on disk until the server calls `close`, and gone after it:

```text recording=http
...
the uploaded files' temporary files exist: [True, True]
the server calls close() on what it was given
HttpResponseBase.close  (HttpResponse)
  HttpRequest.close
    TemporaryUploadedFile.close
    TemporaryUploadedFile.close
  signal request_finished
the uploaded files' temporary files exist: [False, False]
```

A storage on the local file system moves into place a file that has a path, as a `TemporaryUploadedFile` has from `temporary_file_path`, and a file moved away leaves `TemporaryUploadedFile.close` nothing to delete, which that method allows for ([File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)) (`django/core/files/storage/filesystem.py:FileSystemStorage._save`, `django/core/files/uploadedfile.py:TemporaryUploadedFile.temporary_file_path`, `django/core/files/uploadedfile.py:TemporaryUploadedFile.close`).

## Changing the handlers

The handlers are made for the request. `HttpRequest.upload_handlers` is empty until something asks for it, and then `HttpRequest._initialize_handlers` imports each class named in `settings.FILE_UPLOAD_HANDLERS` and instantiates it with the request. A handler belongs to one request, and can keep state between its calls (`django/http/request.py:HttpRequest._initialize_handlers`, `django/core/files/uploadhandler.py:load_handler`).

A view or a middleware can replace or reorder `upload_handlers`, but only before the body is parsed. The property's setter raises `AttributeError` once `FILES` exists, and as parsing begins `HttpRequest.parse_file_upload` turns the list into an `ImmutableList`, whose methods that would change it raise an `AttributeError` of their own; a handler that appends to the list during the parse makes the read of `POST` raise it (`django/http/request.py:HttpRequest.upload_handlers`, `django/http/request.py:HttpRequest.parse_file_upload`, `django/utils/datastructures.py:ImmutableList`).

Before the body is parsed is earlier than it sounds. With the CSRF middleware installed, a `"POST"` request's form is read in that middleware's `process_view`, to find the token, before the view is called, unless the request is let through unchecked ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md)) (`django/middleware/csrf.py:CsrfViewMiddleware._check_token`). The parser itself can be replaced under the same condition ([Multipart parsing: `MultiPartParser`](multipart.md#replacing-the-parser-multipart_parser_class)).

## `UploadedFile` and its subclasses

What lands in `FILES` is an `UploadedFile`, a subclass of the `File` wrapper that the rest of Django's file handling uses ([Files: `File`, `ContentFile` and their helpers](../services/files.md)). It adds what the part's headers said: `content_type`, `charset`, and `content_type_extra` for all the parameters of the part's content type, the charset among them. Its `size` is the number of bytes the parser counted as it passed them to the handler, not anything the client declared (`django/core/files/uploadedfile.py:UploadedFile`, `django/http/multipartparser.py:MultiPartParser._parse`).

The file's name is cleaned twice: first by `MultiPartParser.sanitize_file_name` as the part is parsed, which in the recording above made a client's `"../scans/receipt.bin"` into `"receipt.bin"` ([Multipart parsing: `MultiPartParser`](multipart.md#files-that-do-not-arrive)). The setter of `UploadedFile.name` then takes the base name again, shortens it to 255 characters, and passes it to `validate_file_name`, which refuses an empty name, `"."` and `".."`. What comes out is still text the client chose, and is to be treated as untrusted (`django/http/multipartparser.py:MultiPartParser.sanitize_file_name`, `django/core/files/uploadedfile.py:UploadedFile._set_name`, `django/core/files/utils.py:validate_file_name`).
