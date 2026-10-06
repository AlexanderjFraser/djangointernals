---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Streaming and file responses

`StreamingHttpResponse` holds an iterator where `HttpResponse` holds a body, and `FileResponse` holds an open file. This section follows each to the server under WSGI and under ASGI: who runs the iterator and when, what happens to an iterator of the wrong kind, how a file is handed to the server itself, and what `HttpResponseBase.close` closes.

An `HttpResponse` has its whole body before the view returns. For a page that is right; for a database export of a million rows, a large file, or output that is produced over minutes, it means holding everything in memory and sending nothing until the end. A **streaming response** turns the order round. The view returns at once with a response that has headers and no body, and the body is produced afterwards, a piece at a time, as the server asks for it.

## The iterator

`StreamingHttpResponse.__init__` takes an iterable where `HttpResponse` takes content, and keeps an iterator over it and not the thing itself: the content can be gone through once and no more. It tries the iterable as a synchronous one, and if that fails as an asynchronous one, and records which it got as `StreamingHttpResponse.is_async`. If the iterable has a `close` method, which a synchronous generator has, that method is added to the response's closers; an asynchronous generator has none, and adds nothing (`django/http/response.py:StreamingHttpResponse._set_streaming_content`).

Nothing is run. `StreamingHttpResponse.streaming_content` is a property that returns the iterator wrapped so that each item will pass through `make_bytes` when it is produced. A middleware that wants to change a streamed body cannot edit it; it assigns `streaming_content` a new iterator that wraps the old one, which is how `GZipMiddleware` compresses a stream piece by piece (`django/http/response.py:StreamingHttpResponse.streaming_content`, `django/middleware/gzip.py:GZipMiddleware.process_response`).

A streaming response has no `content` and no `text`, and reading either raises `AttributeError`. Code that handles responses in general is expected to look first at the class attribute `streaming`, which is true here and false on `HttpResponse`, and the middleware Django ships do. `CommonMiddleware` does not add a `Content-Length` to a streaming response, the cache middleware does not store one, and no `"ETag"` is computed for one, each because doing so would need the body (`django/middleware/common.py:CommonMiddleware.process_response`, `django/middleware/cache.py:UpdateCacheMiddleware.process_response`, `django/utils/cache.py:set_response_etag`).

## Under WSGI

The handler does nothing special for a streaming response. It returns the response object, as always, and a WSGI server iterates whatever it is given. This was recorded with a view whose generator notes each part as it makes it, and a script in the server's place that notes each part as it sends it.

```text recording=http
the handler has returned the response; the server iterates it
StreamingHttpResponse.__iter__
the generator produces part 1
the server sends 7 bytes
the generator produces part 2
the server sends 7 bytes
the generator produces part 3
the server sends 7 bytes
the generator has no more parts
the server calls close() on what it was given
HttpResponseBase.close  (StreamingHttpResponse)
  HttpRequest.close
  signal request_finished
```

The body is produced by the server's loop. Each turn of it asks `StreamingHttpResponse.__iter__`'s iterator for one more piece, which runs the view's generator as far as its next `yield`, and the piece is sent before the next is made (`django/http/response.py:StreamingHttpResponse.__iter__`).

Everything Django wraps around a view was over before the first piece existed. The view had returned, every middleware had seen the response on its way out, and `WSGIHandler.__call__` had returned to the server. Code in the generator therefore runs outside all of it: an exception raised there is not turned into an error page, since the status line has gone and no layer of the chain is on the stack to catch it; it reaches the server.

What has not happened yet is the end of the request. `request_finished` is sent by the response's `close`, which the server calls after the last piece, so the request's resources are still held while the body streams.

A client that goes away partway is the server's to notice. This is the same response with the script's loop stopped after one part:

```text recording=http
the handler has returned the response; the server iterates it
StreamingHttpResponse.__iter__
the generator produces part 1
the server sends 7 bytes
the client goes away; the server stops iterating
the server calls close() on what it was given
HttpResponseBase.close  (StreamingHttpResponse)
  the generator is closed where it stood, after a part and before the next
  HttpRequest.close
  signal request_finished
```

The server calls `close` as before, and the closer registered when the response was made closes the generator. A generator closed while suspended has `GeneratorExit` raised at the `yield` it stopped on, so a `finally` block or a `with` statement around the loop is how a streaming view releases what it holds.

## Under ASGI

An ASGI handler sends the response itself, as messages: one with the status and headers, then the body in one or more others. `ASGIHandler.send_response` cuts a body it is given whole into pieces of at most `ASGIHandler.chunk_size`, 65,536 bytes, and marks every message but the last as having more to come (`django/core/handlers/asgi.py:ASGIHandler.send_response`).

```text recording=http
ASGI: a body of 150,000 bytes goes in pieces of at most 65,536
    send: http.response.start, status 200, headers:
      Content-Type: text/html; charset=utf-8
    send: http.response.body, 65536 bytes, more_body True
    send: http.response.body, 65536 bytes, more_body True
    send: http.response.body, 18928 bytes, more_body False
```

For a streaming response it iterates the response asynchronously, and what happens next depends on the kind of iterator the view supplied. With an asynchronous one, each part is sent as it is produced, and an empty message closes the body:

```text recording=http
ASGI: a streaming response over an asynchronous iterator
    send: http.response.start, status 200, headers:
      Content-Type: text/html; charset=utf-8
    the async generator produces part 1
    send: http.response.body, 7 bytes, more_body True
    the async generator produces part 2
    send: http.response.body, 7 bytes, more_body True
    the async generator produces part 3
    send: http.response.body, 7 bytes, more_body True
    send: http.response.body, no body
```

A synchronous iterator cannot be run on the event loop without stopping every other request while it works. `StreamingHttpResponse.__aiter__` therefore hands it to a thread, runs it to the end there, collects everything it yields into a list, and only then starts to send, with a warning (`django/http/response.py:StreamingHttpResponse.__aiter__`).

```text recording=http
ASGI: a streaming response over a synchronous iterator
    send: http.response.start, status 200, headers:
      Content-Type: text/html; charset=utf-8
    warning (Warning): StreamingHttpResponse must consume synchronous iterators in order to serve them asynchronously. Use an asynchronous iterator instead.
    the generator produces part 1
    the generator produces part 2
    the generator produces part 3
    the generator has no more parts
    send: http.response.body, 7 bytes, more_body True
    send: http.response.body, 7 bytes, more_body True
    send: http.response.body, 7 bytes, more_body True
    send: http.response.body, no body
```

All three parts were made before the first was sent. Under ASGI a streaming response over a synchronous iterator does not stream: its body is built whole in memory, which is what the view was written to avoid. The same holds the other way round. Under WSGI, `StreamingHttpResponse.__iter__` consumes an asynchronous iterator whole before the server gets a byte, with the matching warning. A view streams only where its iterator is of the server's kind.

A client that leaves in the middle is noticed by the handler, which listens for a disconnection in a task of its own while the response is sent. The listener can only run while the task that is sending waits, in the view's iterator or in the server's own sending. When it hears of a disconnection, that task is cancelled where it waits, and the handler then closes the response as it would have at the end. In this recording the view's generator waits before each part, as one that fetched its data would, and the cancellation reaches it in that wait (`django/core/handlers/asgi.py:ASGIHandler.handle`, `django/core/handlers/asgi.py:ASGIHandler.listen_for_disconnect`):

```text recording=http
ASGI: a streaming response, and the client goes away after the first part
    send: http.response.start, status 200, headers:
      Content-Type: text/html; charset=utf-8
    the async generator produces part 1
    send: http.response.body, 7 bytes, more_body True
    receive: http.disconnect
    the async generator, waiting for its next part, is stopped by CancelledError
    signal request_finished
```

## `FileResponse`

`FileResponse` is a streaming response made from an open file. Given anything with a `read` method, it keeps the file as `FileResponse.file_to_stream`, adds the file's `close` to the closers, and makes its content an iterator that reads the file `FileResponse.block_size` bytes at a time, 4096 by default. Given anything else it behaves as its base class (`django/http/response.py:FileResponse._set_streaming_content`).

It then works out up to three headers from the file, in `FileResponse.set_headers`.

```text recording=http
the view makes FileResponse(open(".../report.txt", "rb"), as_attachment=True)
  FileResponse.__init__
    StreamingHttpResponse.__init__  (FileResponse)
      HttpResponseBase.__init__
        response["Content-Type"] = 'text/html; charset=utf-8'
      FileResponse._set_streaming_content
        FileResponse.set_headers
          response["Content-Length"] = 10000
            -> stored as '10000'
          response["Content-Type"] = 'text/plain'
          content_disposition_header(True, 'report.txt')
            -> 'attachment; filename="report.txt"'
          response["Content-Disposition"] = 'attachment; filename="report.txt"'
        StreamingHttpResponse._set_streaming_content  (FileResponse)
```

The `Content-Length` is the size of what is left of the file from its current position, found by seeking where the file allows it, and otherwise from an in-memory buffer or from the size of the named file on disk; a file that offers none of these gets no such header. The `Content-Type` is guessed from the file's name, unless the caller passed a content type as an argument of its own, since one given among the headers is overwritten, and is `"application/octet-stream"` when there is nothing to guess from. A name that Python recognises as a compressed file, such as `"report.csv.gz"`, is given the type of the compressed file and not of what is inside, so that a browser saves it as it is and does not unpack it. The `Content-Disposition` says whether the browser should show the file or save it, and under what name: `content_disposition_header` writes it from the `as_attachment` flag and the name, and writes nothing when there is no name and no flag. For both of these headers the name is the response's `filename` argument if one was given, and otherwise the file's own (`django/http/response.py:FileResponse.set_headers`, `django/utils/http.py:content_disposition_header`).

A WSGI server that is simply given the response iterates it and gets the file in blocks:

```text recording=http
the handler has returned the response; the server iterates it
StreamingHttpResponse.__iter__  (FileResponse)
the server sends 4096 bytes
the server sends 4096 bytes
the server sends 1808 bytes
```

Many servers can do better than be fed a file through Python a block at a time, and WSGI lets one say so by putting a callable in the environ under `"wsgi.file_wrapper"`. When the response has a file and the server offers the wrapper, `WSGIHandler.__call__` returns the server's wrapper around the file in place of the response, and the server sends the file by whatever means it has (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).

```text recording=http
  the server's file wrapper is made around the file, block size 4096
the handler has returned a ServerFileWrapper, the server's own wrapper around the file; the server iterates it
the server sends 4096 bytes
the server sends 4096 bytes
the server sends 1808 bytes
the server calls close() on what it was given
the wrapper calls the file's close, which the handler replaced with the response's
  HttpResponseBase.close  (FileResponse)
    HttpRequest.close
    signal request_finished
```

That raises a problem the handler has to solve. The server now holds its wrapper, not the response, and when it has finished it will call `close` on the wrapper, which closes the file. Nothing would close the response, so the request's uploaded files would stay open and `request_finished` would never be sent. Before returning, the handler therefore replaces the file's `close` with the response's. The recording shows the result: the wrapper closes what it thinks is the file, and the whole response is closed.

Under ASGI a `FileResponse` meets the rule of the previous section, because its iterator over the file is a synchronous one. The handler raises the block size to its own chunk size, and the file is then read to its end in a thread and held in memory before any of it is sent (`django/core/handlers/asgi.py:ASGIHandler.run_get_response`):

```text recording=http
ASGI: a FileResponse of 10,000 bytes
    send: http.response.start, status 200, headers:
      Content-Type: text/plain
      Content-Length: 10000
      Content-Disposition: attachment; filename="report.txt"
    warning (Warning): StreamingHttpResponse must consume synchronous iterators in order to serve them asynchronously. Use an asynchronous iterator instead.
    send: http.response.body, 10000 bytes, more_body True
    send: http.response.body, no body
```

The handler that serves static files under ASGI reads the whole file in a thread as well, deliberately and without the warning, by wrapping the content itself; its comment says that `FileResponse` is not async compatible (`django/contrib/staticfiles/handlers.py:ASGIStaticFilesHandler.get_response_async`).

## Closing

Every response, streaming or not, keeps a list of things to close, `_resource_closers`, and `HttpResponseBase.close` goes through it. It calls each, ignoring any exception one raises so that the rest still run, empties the list, marks the response closed, and sends `request_finished` (`django/http/response.py:HttpResponseBase.close`).

| closer | added by | when |
|---|---|---|
| the content's own `close` | `StreamingHttpResponse._set_streaming_content` | the response is given an iterable that has one |
| the file's `close` | `FileResponse._set_streaming_content` | the response is given a file |
| the request's `close` | `BaseHandler.get_response` and `BaseHandler.get_response_async`; the static files handler's own `get_response_async` | the response has come back to the handler |

*What a response closes when it is closed.*

The third is how an uploaded file's temporary copy comes to be deleted at the end of a request: the request does not know when it is over, and the response is told ([Multipart parsing and upload handlers](uploads.md#memory-or-disk)).

`close` is called from outside. A WSGI server is obliged by the interface to call it on whatever it was returned, once the body is sent or the client has gone. An ASGI handler has no server to do it and calls it itself after `send_response`. The test client calls it too: at once for an ordinary response, and for a streaming one when a test has iterated the content to its end (`django/test/client.py:ClientHandler.__call__`). Since `request_finished` is sent from here, everything hung on that signal, the closing of database connections first of all, happens after the last of the body has been handed over and not when the view returns; a generator that queries the database while it streams finds its connection still open ([The two entry points](../handlers/entry.md#who-ends-the-request)).
