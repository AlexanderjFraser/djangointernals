---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Streaming and file responses

`StreamingHttpResponse` holds an iterator, given out as `streaming_content`, where `HttpResponse` holds a body; `FileResponse` holds an open file, which a WSGI server that offers `"wsgi.file_wrapper"` may send itself. Under WSGI the server runs the iterator, and under ASGI the handler. A synchronous iterator under WSGI, or an asynchronous one under ASGI, is run a piece at a time as the body is sent; an iterator of the other kind is run to its end before any of the body is sent. `HttpResponseBase.close` then closes the content where it has a `close` method, and the request.

An `HttpResponse` has its whole body before the view returns. For a page that is right; for a database export of a million rows, a large file, or output that is produced over minutes, it means holding everything in memory and sending nothing until the end. A **streaming response** turns the order round. The view returns at once with a response that has headers and no body, and the body can be produced afterwards, a piece at a time as it is sent.

In the figure, look at when the first piece is made: under WSGI, by the server's loop once the chain is over, and under ASGI, by the handler as it sends, except from a synchronous iterator, whose parts are all made before the first is sent.

```text figure=the-loop
time runs down each column

under WSGI                                          under ASGI, ASGIHandler.send_response runs the iterator

the chain                                           an asynchronous iterator, stepped as it is sent
  the view returns the response                       part 1 made  ->  sent
  the middleware see it on their way out              part 2 made  ->  sent
  WSGIHandler.__call__ returns it to the server       part 3 made  ->  sent
                                                      a last message, with no body
then the server's loop, one turn for each piece
  the iterator runs one step, to its next yield     a synchronous iterator, consumed whole in a thread first
  the server sends the piece it gave                  in the thread: parts 1, 2 and 3 made, kept in a list
  ... until the iterator ends                         then: sent, sent, sent
then the server's close()                             a last message, with no body
  HttpResponseBase.close runs the closers
  signal request_finished
```

*The body of a streaming response, made after the chain has returned. Time runs down each column, and an arrow is a part handed on to be sent.*

## The iterator and `streaming_content`

`StreamingHttpResponse.__init__` takes an iterable where `HttpResponse` takes content, and keeps an iterator over it and not the thing itself: the content can be gone through once and no more. It tries the iterable as a synchronous one, and if that fails as an asynchronous one, and records which it got as `StreamingHttpResponse.is_async`. If the iterable has a `close` method, which a synchronous generator has, that method is added to the response's closers; an asynchronous generator has none, and adds nothing (`django/http/response.py:StreamingHttpResponse._set_streaming_content`).

Nothing is run. `StreamingHttpResponse.streaming_content` is a property that returns the iterator wrapped so that each item will pass through `HttpResponseBase.make_bytes` when it is produced. A middleware that wants to change a streamed body cannot edit it; it assigns `streaming_content` a new iterator that wraps the old one, which is how `GZipMiddleware` compresses a stream piece by piece (`django/http/response.py:StreamingHttpResponse.streaming_content`, `django/middleware/gzip.py:GZipMiddleware.process_response`).

A streaming response has no `content` and no `text`, and reading either raises `AttributeError`. Code that handles responses in general is expected to look first at the class attribute `streaming`, true here and false on `HttpResponse`, and the middleware Django ships do, leaving undone what would need the body: `CommonMiddleware` adds no `Content-Length` to a streaming response, the cache middleware does not store one, and no `"ETag"` is computed for one (`django/middleware/common.py:CommonMiddleware.process_response`, `django/middleware/cache.py:UpdateCacheMiddleware.process_response`, `django/utils/cache.py:set_response_etag`).

## Under WSGI

The WSGI handler does nothing special for a streaming response without a file. `WSGIHandler.__call__` returns the response object and a WSGI server iterates whatever it is given: each turn of its loop asks the iterator that `StreamingHttpResponse.__iter__` returned for one more piece, which runs a synchronous generator as far as its next `yield` (`django/http/response.py:StreamingHttpResponse.__iter__`).

In the chapter's recorded shop, the view's line stands inside the handler's call, and the generator's lines outside it, level with `WSGIHandler.__call__`, each just before the server sends its piece:

```text recording=http
A streaming response under WSGI: the body is produced as the server asks for it
    WSGIHandler.__call__(environ, start_response)
      ...
      BaseHandler.get_response
        the view makes StreamingHttpResponse(parts())
      ...
      start_response("200 OK", headers), the headers being:
        Content-Type: text/html; charset=utf-8
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

Everything Django wraps around a view was over before the first piece existed: the view had returned, every middleware had seen the response on its way out, and `WSGIHandler.__call__` had returned to the server. Code in the generator runs outside all of it. An exception raised there is not turned into Django's error page, since no layer of the chain is on the stack to catch it: it comes out of the iterator into the server's loop, Django logs nothing, and a server that catches it and calls `close`, as wsgiref's does, still ends the request (`django/http/response.py:StreamingHttpResponse.__iter__`).

What has not happened yet is the end of the request. `request_finished` is sent by the response's `close`, which the server calls after the last piece, so the request's resources are still held while the body streams (`django/http/response.py:HttpResponseBase.close`).

A client that goes away partway is the server's to notice. When the server stops its loop after one part, its `close` reaches the generator through the closer the response registered for it:

```text recording=http
A streaming response under WSGI, and the client goes away after the first part
    ...
    the server sends 7 bytes
    the client goes away; the server stops iterating
    the server calls close() on what it was given
    HttpResponseBase.close  (StreamingHttpResponse)
      the generator is closed where it stood, after a part and before the next
      ...
```

A generator closed while suspended has `GeneratorExit` raised at the `yield` it stopped on, so a `finally` block or a `with` statement around the loop is how a streaming view releases what it holds.

## Under ASGI

An ASGI handler sends the response itself, as messages: `ASGIHandler.send_response` sends the status and headers in one, and then the body, in messages of at most `ASGIHandler.chunk_size`, 65,536 bytes (`django/core/handlers/asgi.py:ASGIHandler.send_response`).

`send_response` iterates a streaming response asynchronously, through `StreamingHttpResponse.__aiter__`, sending each part as it comes and an empty message after the last. An asynchronous iterator is stepped as it is sent. A synchronous one cannot be run on the event loop without stopping every other request while it works, so `__aiter__` warns and hands it to a thread, which runs it to its end and collects what it yields into a list; only then are the parts sent (`django/http/response.py:StreamingHttpResponse.__aiter__`).

What tells the two kinds apart is where the body's `send` lines fall against the generator's lines: between them over an asynchronous iterator, and all after them, below the warning, over a synchronous one.

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

The same three parts, from a synchronous generator:

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

> **Trap.** An iterator of the wrong kind is consumed whole before a byte of the body is sent, and the response does not stream: its body is held whole in memory. Under ASGI that is a synchronous iterator; under WSGI it is an asynchronous one, which `StreamingHttpResponse.__iter__` runs to its end through `async_to_sync`, with the matching warning (`django/http/response.py:StreamingHttpResponse.__iter__`).

A client that leaves in the middle is noticed by the handler, which listens for a disconnection while it sends, then cancels the sending where it waits and closes the response as at the end ([The two entry points](../handlers/entry.md#an-asgi-request)) (`django/core/handlers/asgi.py:ASGIHandler.handle`). A generator waiting for its next part when the disconnection is heard is stopped in that wait by an `asyncio.CancelledError`, not by the response's `close`, which holds no closer for an asynchronous generator:

```text recording=http
ASGI: a streaming response, and the client goes away after the first part
    ...
    the async generator produces part 1
    send: http.response.body, 7 bytes, more_body True
    receive: http.disconnect
    the async generator, waiting for its next part, is stopped by CancelledError
    signal request_finished
```

## `FileResponse`

`FileResponse` is a streaming response made from an open file. Given anything with a `read` method, it keeps the file as `FileResponse.file_to_stream`, adds the file's `close`, if it has one, to the closers, and makes its content an iterator that reads the file `FileResponse.block_size` bytes at a time, 4096 by default. Given anything else it behaves as its base class (`django/http/response.py:FileResponse._set_streaming_content`).

It then works out up to three headers from the file in `FileResponse.set_headers`, inside the constructor, replacing the default `Content-Type` that `HttpResponseBase.__init__` set. A view under WSGI made this one from a text file of 10,000 bytes, as an attachment:

```text recording=http
    WSGIHandler.__call__(environ, start_response)
      ...
      BaseHandler.get_response
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
                ...
```

The `Content-Length` is the size of what is left of the file from its current position, found by seeking where the file allows it (reading to the end if it cannot tell its position), and otherwise from an in-memory buffer or from the size of the named file on disk; a file that offers none of these gets no such header.

The `Content-Type` is guessed from the file's name, and is `"application/octet-stream"` when nothing can be guessed. A `Content-Type` passed in `headers` is overwritten by the guess; only a `content_type` keyword argument stops it. The `Content-Disposition` says whether the browser should show the file or save it, and under what name: `content_disposition_header` writes it from the `as_attachment` flag and the name, and writes nothing when there is no name and no flag. For both of these headers the name is the response's `filename` argument if one was given, and otherwise the file's own (`django/http/response.py:FileResponse.set_headers`, `django/utils/http.py:content_disposition_header`).

> **Why.** A name that Python recognises as a compressed file, such as `"report.csv.gz"`, is given the compressed file's own type, here `"application/gzip"`, and no Content-Encoding, so that a browser does not uncompress the file (`django/http/response.py:FileResponse.set_headers`).

A WSGI server that is simply given the response iterates it like any other streaming response, and gets the file a block at a time, in pieces of at most 4096 bytes (`django/http/response.py:FileResponse._set_streaming_content`).

A server may do better than be fed a file through Python a block at a time, and WSGI lets it say so by putting a callable in the environ under `"wsgi.file_wrapper"`. When the response has a file and the server offers the wrapper, `WSGIHandler.__call__` replaces the file's `close` with the response's and returns, in place of the response, the server's wrapper around the file, made with the response's block size; the server sends the file by whatever means it has (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).

What the server closes at the end is its wrapper, and what is closed under it is the response:

```text recording=http
A FileResponse under WSGI, to a server that offers wsgi.file_wrapper
    WSGIHandler.__call__(environ, start_response)
      ...
      the server's file wrapper is made around the file, block size 4096
    the handler has returned a ServerFileWrapper, the server's own wrapper around the file; the server iterates it
    ...
    the server calls close() on what it was given
    the wrapper calls the file's close, which the handler replaced with the response's
      HttpResponseBase.close  (FileResponse)
        HttpRequest.close
        signal request_finished
```

> **Why.** A server that uses the wrapper calls `close` on the wrapper and not on the response, and without the replacement nothing would close the response: the request's uploaded files would stay open, and `request_finished` would never be sent (`django/core/handlers/wsgi.py:WSGIHandler.__call__`).

Under ASGI a `FileResponse` is consumed whole, since its iterator over the file is a synchronous one. `ASGIHandler.run_get_response` sets the response's block size to the handler's chunk size, and the file is read to its end in a thread and held in memory before any of it is sent (`django/core/handlers/asgi.py:ASGIHandler.run_get_response`). A file of 10,000 bytes therefore goes in one message, after the warning:

```text recording=http
ASGI: a FileResponse of 10,000 bytes
    ...
    warning (Warning): StreamingHttpResponse must consume synchronous iterators in order to serve them asynchronously. Use an asynchronous iterator instead.
    send: http.response.body, 10000 bytes, more_body True
    send: http.response.body, no body
```

## Closing

Every response, streaming or not, keeps a list of things to close, `_resource_closers`, and `HttpResponseBase.close` goes through it. It calls each, ignoring any `Exception` one raises so that the rest still run, empties the list, marks the response closed, and sends `request_finished` (`django/http/response.py:HttpResponseBase.close`).

| closer | added by | when |
|---|---|---|
| the content's own `close` | `StreamingHttpResponse._set_streaming_content` | the response is given an iterable that has one |
| the file's `close` | `FileResponse._set_streaming_content` | the response is given a file |
| the request's `close` | `BaseHandler.get_response` and `BaseHandler.get_response_async`; `ASGIStaticFilesHandler.get_response_async` | the response has come back to the handler |

*What a response closes when it is closed.*

The third is how an uploaded file's temporary copy comes to be deleted at the end of a request: the request does not know when it is over, and the response is told ([Upload handlers and uploaded files](uploads.md#the-temporary-file)).

`close` is called from outside, once the body has been sent or the client has gone: by a WSGI server, by the ASGI handler after `send_response`, and by the test client, which closes an ordinary response before its call returns and a streaming one once the test has read `streaming_content` to its end ([The two entry points](../handlers/entry.md#who-ends-the-request), [The test client: `Client` and `ClientHandler`](../testing/client.md#the-servers-part-clienthandler__call)) (`django/test/client.py:ClientHandler.__call__`, `django/test/client.py:closing_iterator_wrapper`).
