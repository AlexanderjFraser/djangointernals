---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The request cycle
contents: request, headers, querydict, body, uploads, response, streaming, cookies, helpers
---

# Requests and responses

`HttpRequest` is the object a view is given and `HttpResponse` the object it returns. A request is made from the server's data at almost no cost, and its query string, cookies, headers and body are each parsed the first time something reads them; a response is a status, headers, cookies and a body, which the handler turns back into what the server expects.

A server and a view do not speak the same language. A WSGI server describes a request as a dictionary of strings, the **environ**, and a stream to read the body from; an ASGI server describes it as a dictionary, the **scope**, and a series of messages. A view wants neither. It wants to ask whether the method was `POST`, what the form's field called customer held, whether a file came with it. On the way back the difference is the same in reverse: the view has a page of HTML and a cookie to set, and the server wants a status line, a list of header pairs and an iterable of bytes.

The package `django.http` is the two objects that stand between them. The handler makes the first from what the server passed and gives it to the middleware chain; whatever answers, a view or a middleware, makes the second, and the handler takes it apart for the server. [Handlers and middleware](handlers.md) is about the path between the two objects. This chapter is about the objects.

```text figure=both-ways
the server                          django.http                                         the view

an environ, or a scope and      ->  HttpRequest, made as a WSGIRequest or an ASGIRequest
a body                                set as it is made:   method, path, path_info, META,
                                                           content_type, encoding
                                      parsed on first use, and kept:
                                                           GET, COOKIES, headers        <-  reads
                                      read from the body's stream, once:
                                                           body, POST, FILES            <-  reads

a status line, a list of        <-  HttpResponse, or another subclass of                <-  returns
headers, an iterable of bytes       HttpResponseBase: status_code, headers, cookies,
                                    and the body: bytes, or an iterator

close(), when the body is sent  ->  HttpResponseBase.close: closes the request's uploaded
                                    files, and sends the signal request_finished
```

*The two objects of `django.http` between a server and a view. The request is filled in as it is read; the response is an object the view returns and the middleware may still change, and closing it is what ends the request.*

## The objects

**`HttpRequest`** is the request as a view sees it: the method, the path, and four collections with upper-case names. `GET` holds the query string's parameters, `POST` a submitted form's fields, `FILES` its uploaded files, `COOKIES` the cookies. Under them is `META`, a dictionary in the shape WSGI gives a request, with a header such as `User-Agent` under the key `"HTTP_USER_AGENT"`. A handler never makes a plain `HttpRequest`. It makes a `WSGIRequest` or an `ASGIRequest`, a subclass that knows how to fill those attributes from what its kind of server passes (`django/http/request.py:HttpRequest`, `django/core/handlers/wsgi.py:WSGIRequest`, `django/core/handlers/asgi.py:ASGIRequest`).

**`QueryDict`** is the type of `GET` and `POST`: a dictionary in which a key can have several values, because a query string can repeat a parameter and a form can have several fields of one name. The ones a `WSGIRequest` or an `ASGIRequest` makes cannot be changed (`django/http/request.py:QueryDict`).

**`HttpResponseBase`** is what every response is: a status code, a set of headers, a set of cookies, and a list of things to close when the response has been sent. It has no body. Its two subclasses differ in where the body is. An **`HttpResponse`** holds its whole body in memory as bytes. A **`StreamingHttpResponse`** holds an iterator, and the body does not exist until the server asks for it, a piece at a time. Every other response class is a subclass of one of these two. The redirects, `JsonResponse` and the classes named for a status code are subclasses of `HttpResponse`; `FileResponse` is a subclass of `StreamingHttpResponse` (`django/http/response.py:HttpResponseBase`, `django/http/response.py:HttpResponse`, `django/http/response.py:StreamingHttpResponse`).

## A request is made cheaply and read lazily

Most requests use little of what they carry. A view that answers a `GET` from the database never looks at the cookies; a middleware that redirects never reads the body. So making the request does almost nothing, and each part is worked out when it is first asked for and then kept.

This was recorded from a running Django. A script plays the server and posts a form to a path with a query string; the view reads the request's attributes one after another, and each line under a read is what Django did to answer it. The lines are a selection of the calls made, nested as they were made. The view also read the headers and the host, and those two reads are left out here.

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
        the view reads request.method, request.path, request.content_type and request.encoding
          -> 'POST', '/orders/', 'application/x-www-form-urlencoded', None
        the view reads request.GET
          WSGIRequest.GET
            QueryDict.__init__(b'page=2&tag=new&tag=sale', encoding=None)
          -> <QueryDict: {'page': ['2'], 'tag': ['new', 'sale']}>
        the view reads request.GET again
        the view reads request.COOKIES
          WSGIRequest.COOKIES
            parse_cookie('theme=dark; basket=3')
              -> {'theme': 'dark', 'basket': '3'}
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
        the view reads request.FILES
          WSGIRequest.FILES
          -> <MultiValueDict: {}>
        the view reads request.body
          HttpRequest.body
            -> 26 bytes
```

**Making the request reads almost nothing.** The handler sends the signal `request_started` and then makes the request. `WSGIRequest.__init__` keeps the server's dictionary, works out the path, and parses the `Content-Type` header, because the content type and the character encoding it may name decide how everything else is read. It wraps the body's stream in a `LimitedStream` that will give out no more bytes than the `Content-Length` header declared, here 26, and reads none of them ([Making the request](http/request.md)).

**Each collection is parsed by its first read.** `WSGIRequest.GET` and `WSGIRequest.COOKIES` are each a `cached_property`: a method that runs once, on the first read, and whose result then replaces it on the instance. The second read of `GET` in the recording has nothing under it because nothing ran. The encoding of `None` that the query string was parsed with means the default, `settings.DEFAULT_CHARSET`. The headers are read from `META` in the same way, once; the host is worked out afresh each time something asks for it ([Headers, host and scheme](http/headers.md), [`QueryDict`](http/querydict.md)).

**The body is read whole, once, and kept.** The first read of `POST` called `HttpRequest._load_post_and_files`, which looked at the content type, found an ordinary form, and asked for `HttpRequest.body`. That property checked the declared length against a limit, read the stream to its end and kept the bytes; the form was then parsed out of them, as UTF-8. The later reads of `FILES` and `body` found everything already there (`django/http/request.py:HttpRequest._load_post_and_files`, `django/http/request.py:HttpRequest.body`).

## The body is a stream

The body is the part of a request that may be large, and nothing looks at it until something asks. Under WSGI Django has not read any of it: the request holds the server's input stream. Under ASGI the handler has received it already, into a temporary file that stays in memory while it is small, and the request holds that file. Either way the body is a stream, and whoever reads a stream first has consumed it. That gives the body rules the other attributes do not have. A view may read `body`, or read the stream itself as a file, or read `POST` and `FILES`, and some of these can follow one another and some cannot ([The body](http/body.md) has which, recorded).

A form that uploads files is sent as `"multipart/form-data"`, and `POST` and `FILES` are parsed from it without the body being read whole. `MultiPartParser` takes it from the stream in pieces and hands each file's pieces to a chain of **upload handlers**, which decide where the file goes. The two that are installed by default keep the files of a small request in memory and write those of a large one to temporary files on disk ([Multipart parsing and upload handlers](http/uploads.md)).

What a client may send is limited by settings: the size of a body that will be read into memory, the number of parameters, the number of files. A request over a limit raises an exception at the moment the offending part is read, which may be deep inside a view, and the exception becomes a 400 response at the nearest boundary of the middleware chain ([The body](http/body.md#the-limits)).

## A response is built, then taken apart

A view builds its response as an object and can go on changing it until it returns: setting headers by subscript, setting cookies, writing more content. The middleware on the way out do the same. Only then does the handler read the object. This is a response recorded from the view's constructor call to the server's last one.

```text recording=http
A response under WSGI, from its constructor to the server's close()
    WSGIHandler.__call__(environ, start_response)
      signal request_started
      WSGIRequest.__init__(environ)
      BaseHandler.get_response
        the view makes HttpResponse("<h1>Thanks</h1>")
          HttpResponse.__init__
            HttpResponseBase.__init__
              response["Content-Type"] = 'text/html; charset=utf-8'
            HttpResponse.content = '<h1>Thanks</h1>'
        the view sets response["X-Order"] = 1042
          response["X-Order"] = 1042
            -> stored as '1042'
        the view calls response.set_cookie("basket", "empty", max_age=3600, httponly=True)
          HttpResponseBase.set_cookie("basket", 'empty', max_age=3600, httponly=True)
        the view calls response.write("<p>Order 1042</p>")
          HttpResponse.write('<p>Order 1042</p>')
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

The constructor of the base class set a `Content-Type` before the body was looked at, because the charset in that header is what the body is encoded with: the setter of `HttpResponse.content` turned the string into bytes at once. A header set by subscript is stored as a string whatever it was given, here a number. The cookie is not a header yet. It is kept in a separate collection, `HttpResponseBase.cookies`, and becomes a `Set-Cookie` line only when `WSGIHandler.__call__` builds the header list for the server, after the headers proper ([The response object](http/response.md), [Cookies](http/cookies.md)).

The handler returns the response object itself, and the server iterates it: an `HttpResponse` yields the pieces of its body, here the constructor's content and what `write` added. A `StreamingHttpResponse` is iterated in the same way, with the difference that each step of the server's loop runs the view's iterator a step further, long after the view has returned ([Streaming and file responses](http/streaming.md)).

The last call is the server's `close`. `HttpResponseBase.close` runs every closer registered on the response, one of which is the request's own `close`, added by the handler so that uploaded files are closed with it, and then sends the signal `request_finished` (`django/http/response.py:HttpResponseBase.close`, `django/http/request.py:HttpRequest.close`).

## The neighbours

The handler makes the request and consumes the response, and [Handlers and middleware](handlers.md) has both ends: `WSGIHandler.__call__`, `ASGIHandler.handle`, and how an exception raised while a request is read becomes a response. The middleware Django ships mostly read one of these objects and mark the other. The session middleware reads a cookie and sets one, and the CSRF middleware reads `POST` or a header ([Authentication, sessions and messages](auth.md), [Security](security.md)).

The request's `path_info` is what the resolver matches ([URL routing](urls.md)), and the shortcuts and the generic views make responses on a view's behalf ([Views](views.md)). A form is bound to `POST` and `FILES` ([Forms](forms.md)), and an uploaded file is saved through a storage, which for a file already on disk is a move ([Caching, files, mail, signals and tasks](services.md)). Signed cookies use the signer described in [Security](security.md). `TemplateResponse`, a response that is not rendered until each middleware's `process_template_response` has seen it, belongs to [Templates](templates.md). And the test client never goes near a server: it builds the dictionary a server would have passed, with methods it inherits from `RequestFactory`, and its own handler makes the request from that ([The test framework](testing.md)).
