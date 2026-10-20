---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: request, headers, querydict, body, multipart, uploads, response, streaming, cookies, helpers
---

# Requests and responses

`HttpRequest` is the object a view is given and `HttpResponse` the object it returns. The handler makes a `WSGIRequest` or an `ASGIRequest` from what the server passed, at almost no cost, and each of the request's collections is parsed the first time something reads it: `GET`, `COOKIES`, `headers`, and, from the body, `POST` and `FILES`. A response, an `HttpResponse` or a `StreamingHttpResponse`, is a status, headers, cookies and a body, which the handler takes apart for the server.

A server and a view do not speak the same language. A WSGI server describes a request as one dictionary, the **environ**, which holds its method, path and headers as strings and its body as a stream; an ASGI server describes it as a dictionary, the **scope**, and a series of messages. A view wants neither. It wants to ask whether the method was `"POST"`, what the form's field called customer held, whether a file came with it. On the way back the difference is the same in reverse: the view has a page of HTML and a cookie to set, and the server wants a status, a list of header pairs and the body's bytes.

The package `django.http` is the two objects that stand between them. The request goes from the handler into the middleware chain, and whatever answers, a view or a middleware, makes the response: [Handlers and middleware](handlers.md) is about that path, and this chapter about the objects. In the figure, look at the three ways the request is filled in, by its constructor, by the first read of a collection and by the first read of the body, and at the response, which the view hands back as an object and the server receives as a status, headers and bytes.

```text figure=both-ways
the server                          django.http                                         the view

an environ, or a scope and      ->  HttpRequest, made as a WSGIRequest or an ASGIRequest
a body                                set as it is made:   method, path, path_info, META,
                                                           content_type, encoding
                                      parsed on first use:
                                                           GET, COOKIES, headers        <-  reads
                                      read from the body's stream, once:
                                                           body, POST, FILES            <-  reads

a status, a list of headers,    <-  HttpResponse, or another subclass of                <-  returns
the body's bytes                    HttpResponseBase: status_code, headers, cookies,
                                    and the body: bytes, or an iterator

close(), when sending ends      ->  HttpResponseBase.close: closes the request's uploaded
                                    files, and sends the signal request_finished
```

*The two objects of `django.http` between a server and a view. The request is filled in as it is read; the response is an object the view returns and the middleware may still change, and closing it, which under ASGI the handler does, ends the request.*

## The objects

**`HttpRequest`** is the request as a view sees it: the method, the path, and four collections with upper-case names. `GET` holds the query string's parameters, `POST` a submitted form's fields, `FILES` its uploaded files, `COOKIES` the cookies. Under them is `META`, a dictionary in the shape WSGI gives a request, with a header such as User-Agent under the key `"HTTP_USER_AGENT"`. A handler never makes a plain `HttpRequest`: it makes a `WSGIRequest` or an `ASGIRequest`, a subclass that knows how to fill those attributes from what its kind of server passes (`django/http/request.py:HttpRequest`, `django/core/handlers/wsgi.py:WSGIRequest`, `django/core/handlers/asgi.py:ASGIRequest`).

**`QueryDict`** is the type of `GET` and `POST`: a dictionary in which a key can have several values, because a query string can repeat a parameter and a form can have several fields of one name. The ones a `WSGIRequest` or an `ASGIRequest` makes are immutable, and refuse an assignment ([`QueryDict`](http/querydict.md)) (`django/http/request.py:QueryDict`).

**`HttpResponseBase`** is what every response is: a status code, a set of headers, a set of cookies, and a list of things to close at the end of the request. It has no body. An **`HttpResponse`** holds its whole body in memory as bytes; a **`StreamingHttpResponse`** holds an iterator, and its body is ordinarily made as it is sent, a piece at a time ([Streaming and file responses](http/streaming.md)). Every other response class is a subclass of one of these two: the redirects, `JsonResponse` and the classes named for a status code are subclasses of `HttpResponse`, and `FileResponse` of `StreamingHttpResponse` ([The response object](http/response.md)) (`django/http/response.py:HttpResponseBase`).

## A request is made cheaply and read lazily

Much of a request may go unused: a view that answers a `"GET"` from the database never looks at the cookies, and a middleware that redirects never reads the body. Making the request does almost nothing, and the collections are worked out when first asked for.

The chapter's recording runs a small shop with no middleware, and a script in the server's place. Here the script posts a form to a path with a query string and a cookie. Under the request's constructor, look for what is missing: nothing touches the body, the query string or the cookies.

```text recording=http
A form is posted: what making the request does, and what each first read does
    WSGIHandler.__call__(environ, start_response)
      signal request_started
      WSGIRequest.__init__(environ)
        HttpRequest._set_content_type_params
          parse_header_parameters('application/x-www-form-urlencoded')
            -> ('application/x-www-form-urlencoded', {})
        LimitedStream.__init__(stream, limit=26)
      BaseHandler.get_response
      ...
```

`WSGIRequest.__init__` keeps the server's dictionary as `META`, works out the path, and parses the Content-Type header, whose content type and charset decide how the body is read and the query string decoded; it wraps the body's stream in a `LimitedStream` that will give out no more than the 26 bytes Content-Length declared, and reads none of them ([Making the request: `WSGIRequest` and `ASGIRequest`](http/request.md)). The view then reads the collections, and under each read is what Django did to answer it: the second read of `GET` has nothing under it, and the first read of `POST` reaches down to the stream.

```text recording=http
...
the view reads request.GET
  WSGIRequest.GET
    QueryDict.__init__(b'page=2&tag=new&tag=sale', encoding=None)
  -> <QueryDict: {'page': ['2'], 'tag': ['new', 'sale']}>
the view reads request.GET again
the view reads request.COOKIES
  WSGIRequest.COOKIES
    parse_cookie('theme=dark; basket=3')
      -> {'theme': 'dark', 'basket': '3'}
...
the view reads request.POST
  WSGIRequest._get_post
    HttpRequest._load_post_and_files
      HttpRequest.body
        HttpRequest._check_data_too_big(26)
        HttpRequest.read()
          LimitedStream.read(-1)
            -> 26 bytes
        -> 26 bytes
      QueryDict.__init__(b'customer=Ada&item=3&item=7', encoding='utf-8')
  -> <QueryDict: {'customer': ['Ada'], 'item': ['3', '7']}>
...
the view reads request.body
  HttpRequest.body
    -> 26 bytes
    ...
```

`WSGIRequest.GET` and `WSGIRequest.COOKIES` are each a **`cached_property`**: a method that runs on the first read, and whose result then replaces it on the instance, so that every later read is an attribute lookup until setting `HttpRequest.encoding` deletes `GET`. The headers, `HttpRequest.headers`, are made from `META` the same way; the host, a matter of which header to believe, is worked out afresh each time it is asked for ([Headers, host and scheme](http/headers.md)). The query string was parsed with the request's encoding, `None` here, which means the default charset, and the form with UTF-8, the one encoding an ordinary form is read in ([`QueryDict`](http/querydict.md)) (`django/core/handlers/wsgi.py:WSGIRequest.GET`, `django/http/request.py:HttpRequest._load_post_and_files`).

## The body is a stream

The body is the one part of a request that may be large, and it is read from a stream, which reading uses up. Under WSGI the request holds the server's input stream, unread; under ASGI the handler has received the body already, into a temporary file that stays in memory while it is small, and the request holds that file. The first read of `POST` above found an ordinary form, whose fields are parsed from the body's bytes, and so asked for `HttpRequest.body`, which checked the declared length against a limit, read the stream to its end and kept the bytes, where the later read of `body` found them. A view may read `body`, read the stream itself as a file, or read `POST` and `FILES`, and some of these can follow one another and some cannot ([The body: `body`, `POST` and `FILES`](http/body.md)) (`django/http/request.py:HttpRequest._load_post_and_files`, `django/http/request.py:HttpRequest.body`).

A form that uploads files is sent as `"multipart/form-data"`, and its `POST` and `FILES` are parsed without the body being read whole. `MultiPartParser` takes the body from the stream in pieces ([Multipart parsing: `MultiPartParser`](http/multipart.md)) and hands each file's pieces to a chain of **upload handlers**, which decide where the file goes; the two installed by default keep the files of a small request in memory and write those of a large one to temporary files on disk ([Upload handlers and uploaded files](http/uploads.md)) (`django/http/multipartparser.py:MultiPartParser._parse`, `django/core/files/uploadhandler.py:MemoryFileUploadHandler.handle_raw_input`).

Settings limit what a client may send: the size of a body read into memory, the number of parameters, the number of files. A request over a limit raises a `SuspiciousOperation` at the moment the offending part is read, which may be deep inside a view, and raised inside the middleware chain the exception becomes a 400 response at the nearest boundary ([The body: `body`, `POST` and `FILES`](http/body.md#the-limits)) (`django/core/handlers/exception.py:response_for_exception`).

## A response is built, then taken apart

A view builds its response as an object and can go on changing it until it returns, and the middleware on the way out do the same; only then does the handler read it. In the recording the view made `HttpResponse("<h1>Thanks</h1>")`, set a header by subscript, set a cookie and wrote a second piece of content. What the server was then given comes in this order: the headers with the cookie last, as a Set-Cookie line, the body in two pieces, and the call that ends the request.

```text recording=http
...
      start_response("200 OK", headers), the headers being:
        Content-Type: text/html; charset=utf-8
        X-Order: 1042
        Set-Cookie: basket=empty; expires=Mon, 21 Sep 2026 15:13:20 GMT; HttpOnly; Max-Age=3600; Path=/
    the handler has returned the response; the server iterates it
    HttpResponse.__iter__
    the server sends 15 bytes
    the server sends 17 bytes
    the server calls close() on what it was given
    HttpResponseBase.close  (HttpResponse)
      HttpRequest.close
      signal request_finished
```

The cookie was not a header until the handler built the header list: it is kept in `HttpResponseBase.cookies`, a collection of its own ([Cookies](http/cookies.md)) (`django/core/handlers/wsgi.py:WSGIHandler.__call__`). The WSGI handler ordinarily returns the response object itself and the server iterates it: an `HttpResponse` yields the pieces of its body, and a `StreamingHttpResponse` over an ordinary, synchronous iterator runs the iterator a step for each step of the server's loop, after the view has returned ([Streaming and file responses](http/streaming.md)). Under ASGI the handler sends the response itself, as messages, and closes it itself ([The two entry points](handlers/entry.md)) (`django/core/handlers/asgi.py:ASGIHandler.handle`). The server's `close` is the last call: `HttpResponseBase.close` ends the request ([The two entry points](handlers/entry.md#who-ends-the-request)), and closes the request's uploaded files with it ([Streaming and file responses](http/streaming.md#closing)) (`django/http/response.py:HttpResponseBase.close`).

## The neighbours

The handler makes the request and consumes the response ([Handlers and middleware](handlers.md)), and many of the middleware Django ships read one of the two objects and mark the other, as the session middleware reads a cookie and sets one ([`SessionMiddleware`: the cookie and the save](auth/session-middleware.md)). The resolver matches the request's `path_info` ([URL routing](urls.md)); the shortcuts and the generic views make responses on a view's behalf ([Views](views.md)); a form is bound to `POST` and `FILES` ([Forms](forms.md)); a `TemplateResponse` is ordinarily rendered after the `process_template_response` hooks ([`SimpleTemplateResponse` and `TemplateResponse`](templates/responses.md)); and the test client builds the dictionary a server would have passed and makes its requests from it with a handler of its own ([The test client: `Client` and `ClientHandler`](testing/client.md)).
