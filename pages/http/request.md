---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Making the request: `WSGIRequest` and `ASGIRequest`

What `WSGIRequest.__init__` and `ASGIRequest.__init__` do with what a server passes: how the path, the method, `META`, the content type and the encoding are set, what can go wrong before any middleware runs, and which of a request's attributes wait to be read.

`HttpRequest` declares nearly everything a view uses on a request: the methods that work out the host and the scheme, the property that reads the body, the code that parses a form. What it does not know is where a request comes from. Its own `__init__` makes an empty one, with no path, no method, and empty collections, which is what a test or a script makes when it needs a request and has no server. A request that came from a server is an instance of one of two subclasses, each with a constructor that fills the same attributes from a different source. Neither constructor calls the base one; a comment in the base says so of `WSGIRequest`, and warns that whatever the base assigns has to be assigned there too (`django/http/request.py:HttpRequest.__init__`).

## From a WSGI environ

A WSGI server passes one dictionary, the environ. `WSGIRequest.__init__` does not copy it: the request's `META` is that same dictionary, and the request also keeps it as `environ` (`django/core/handlers/wsgi.py:WSGIRequest.__init__`).

The path needs work before it can be used, for a reason that lies in WSGI itself. The interface has the server pass what it takes from the request as `str`, and the server makes one from the bytes of the request line by decoding them as ISO-8859-1, whatever they were. A path of UTF-8 bytes therefore arrives as the wrong characters, two for each accented letter. Django undoes the server's step and then decodes properly: `get_bytes_from_wsgi` encodes the string with ISO-8859-1, which gives back exactly the bytes the server had, and `get_path_info` decodes those as UTF-8, first percent-escaping any byte sequence that is not valid UTF-8 so that the decoding cannot fail (`django/core/handlers/wsgi.py:get_path_info`, `django/utils/encoding.py:repercent_broken_unicode`).

A request has two paths. The **script name** is the part of the URL that belongs to the place the server mounted the application, and `HttpRequest.path_info` is the rest, the part the URL resolver matches. `HttpRequest.path` is the two joined, which is the path the client asked for. `get_script_name` takes the script name from `settings.FORCE_SCRIPT_NAME` when that is not `None`; otherwise from `"SCRIPT_URL"` or `"REDIRECT_URL"`, which Apache sets when it has rewritten a URL, with the path info taken off its end; and otherwise from the environ's `"SCRIPT_NAME"`. An empty path info is treated as `"/"`. The constructor then writes the decoded script name and path info back into the environ, so `META` holds the corrected values (`django/core/handlers/wsgi.py:get_script_name`).

In this recording the environ's path is the UTF-8 for a path with one accented letter, as a WSGI server passes it:

```text recording=http
WSGI: the environ is META, and the path is decoded again
    the environ: SCRIPT_NAME '/shop', and PATH_INFO as a WSGI server passes it, '/caf\xc3\xa9/'
    request.META is environ: True
    request.path_info: '/café/'
    request.path: '/shop/café/'
    request.META["PATH_INFO"]: '/café/'
```

The rest of the constructor is short. The method is the environ's, in upper case. The `Content-Type` header is parsed, which the section below is about. And the server's input stream, the environ's `"wsgi.input"`, is wrapped in a `LimitedStream` whose limit is the `Content-Length` header as an integer, or zero when the header is missing or is not a number. The wrapper counts what has been read and returns nothing once the declared length is reached, whatever the stream under it would have done. A body sent without a `Content-Length` is therefore, to a `WSGIRequest`, an empty body, unless the server has put a length of its own into the environ (`django/core/handlers/wsgi.py:LimitedStream`).

## From an ASGI scope

An ASGI server passes a dictionary called the scope, and the body arrives separately, as messages. By the time an `ASGIRequest` is made the handler has received the whole body into a temporary file, one that is held in memory until it grows past `settings.FILE_UPLOAD_MAX_MEMORY_SIZE` and is then written to disk, and the constructor is given the scope and that file ([The two entry points](../handlers/entry.md#an-asgi-request) has the handler's side). The file becomes the request's stream as it is, with no wrapper (`django/core/handlers/asgi.py:ASGIRequest.__init__`).

The scope is not shaped like an environ, and a great deal of code reads `META` by WSGI's keys, so the constructor builds a `META` that looks like one.

```text recording=http
ASGI: META is built from the scope
    the scope's headers, in the order sent:
      host: shop.example
      accept: text/html
      accept: application/json
      cookie: theme=dark
      cookie: basket=3
      x_token: spoofed
      x-token: abc
      content-type: text/plain
      content-length: 0
    request.method: 'GET'
    request.path: '/shop/café/'
    request.path_info: '/café/'
    request.scheme: 'https'
    META['REQUEST_METHOD']: 'GET'
    META['QUERY_STRING']: 'page=2'
    META['SCRIPT_NAME']: '/shop'
    META['PATH_INFO']: '/café/'
    META['wsgi.multithread']: True
    META['wsgi.multiprocess']: True
    META['REMOTE_ADDR']: '203.0.113.9'
    META['REMOTE_HOST']: '203.0.113.9'
    META['REMOTE_PORT']: 51234
    META['SERVER_NAME']: 'shop.example'
    META['SERVER_PORT']: '443'
    META['HTTP_COOKIE']: 'theme=dark; basket=3'
    META['HTTP_HOST']: 'shop.example'
    META['HTTP_ACCEPT']: 'text/html,application/json'
    META['HTTP_X_TOKEN']: 'abc'
    META['CONTENT_TYPE']: 'text/plain'
    META['CONTENT_LENGTH']: '0'
```

The scope's path is already text, so nothing is decoded a second time. The script name is `settings.FORCE_SCRIPT_NAME` when that is set to anything but an empty value, and otherwise the scope's `"root_path"`; the path info is the path with that prefix taken off, when the path is the prefix or continues it with a slash. An empty string in the setting forces an empty script name under WSGI and is passed over under ASGI. The client's and the server's addresses become the keys WSGI uses for them, and when the scope names no server the name is `"unknown"` and the port `"0"` (`django/core/handlers/asgi.py:get_script_prefix`).

Each header becomes a key as a WSGI server would have written it: upper case, hyphens as underscores, `"HTTP_"` in front, except for the content type and the content length, which WSGI leaves without the prefix. That mapping loses something, since a header named `"x-token"` and one named `"x_token"` would land on the same key and a client could use the second to overwrite what a proxy set as the first. The constructor therefore drops every header with an underscore in its name: in the recording the value under `"HTTP_X_TOKEN"` is the hyphenated header's. Under WSGI this is the server's affair, and Django's development server does the same before it builds the environ (`django/core/servers/basehttp.py:WSGIRequestHandler.get_environ`).

A header that arrives more than once is joined into one value with commas, as HTTP allows for a header that is a list. Cookies are the exception. HTTP/2 lets a client send each cookie as a `"cookie"` header of its own, and a comma is not what separates cookies, so those values are joined with a semicolon and a space.

## The content type and the encoding

Both constructors call `HttpRequest._set_content_type_params` near their end. It splits the `Content-Type` header into `HttpRequest.content_type`, the media type in lower case, and `HttpRequest.content_params`, a dictionary of the parameters after it. The content type is what later decides how the body is read. If one of the parameters is a charset that Python has a codec for, it becomes the request's `encoding`; an unknown charset is ignored (`django/http/request.py:HttpRequest._set_content_type_params`).

The **encoding** of a request is the character set used to decode the percent-escapes in its query string and the names and values of a multipart form. It is `None` on most requests, which means `settings.DEFAULT_CHARSET`. A view or a middleware may assign it, and because the collections may already have been decoded with the old value, the setter throws away the stored form and, on a request made by a server, `GET`, so that the next read parses them again. An ordinary form can be parsed again from the kept body, though UTF-8 is the only encoding accepted for one. A multipart form that was parsed from the stream cannot be: after the encoding is assigned, the next read of `POST` comes back empty, and `FILES` with it (`django/http/request.py:HttpRequest.encoding`).

The setter decides whether there is a `GET` to throw away by testing whether the request has that attribute. On a request made by a server `GET` is a `cached_property`, and testing for it computes it. So when a `Content-Type` names a charset, the query string is parsed while the request is being made, and the result discarded:

```text recording=http
A Content-Type with a charset sets the request's encoding as the request is made
    a WSGIRequest is made, for a request line of "POST /orders/?q=caf%E9" and a Content-Type of "text/plain; charset=iso-8859-1"
      WSGIRequest.__init__(environ)
        HttpRequest._set_content_type_params
          parse_header_parameters('text/plain; charset=iso-8859-1')
            -> ('text/plain', {'charset': 'iso-8859-1'})
          HttpRequest.encoding = 'iso-8859-1'
            WSGIRequest.GET
              QueryDict.__init__(b'q=caf%E9', encoding='iso-8859-1')
        LimitedStream.__init__(stream, limit=0)
    request.encoding is 'iso-8859-1', and request.GET is <QueryDict: {'q': ['café']}>
```

The two subclasses differ here. `WSGIRequest.GET` passes the request's encoding to the `QueryDict` it makes, as the recording shows. `ASGIRequest.GET` does not, so under ASGI a query string is decoded with the default charset whatever the request's encoding is (`django/core/handlers/wsgi.py:WSGIRequest.GET`, `django/core/handlers/asgi.py:ASGIRequest.GET`).

> **A trap.** The request is made before the middleware chain is entered, so an exception raised by a constructor is not turned into a response by the chain. `_set_content_type_params` raises `BadRequest` when `parse_header_parameters` cannot parse the header, which happens, among other cases, when the header is longer than `MAX_HEADER_LENGTH` characters or has a parameter in an encoding that cannot be applied. Under WSGI that exception leaves `WSGIHandler.__call__`. Under ASGI the handler catches two exceptions as it makes the request and answers them itself: `UnicodeDecodeError`, which a query string that is not UTF-8 raises, with a 400, and `RequestDataTooBig`, which nothing in the constructor raises at this commit, with a 413. `BadRequest` is not one of the two, and leaves the handler as it does under WSGI. So does `TooManyFieldsSent`, when a `Content-Type` that names a charset arrives with a query string of too many parameters, because the setter described above parses the query string there. In these cases Django has made no response, and what the client sees is the server's doing (`django/core/handlers/asgi.py:ASGIHandler.create_request`).

A request with a `Content-Type` too long to parse was recorded reaching a `WSGIHandler`:

```text recording=http
a request whose Content-Type header is 10,014 characters long; no view is reached
  WSGIRequest.__init__(environ)
    HttpRequest._set_content_type_params
      raises BadRequest
  the handler raises BadRequest to the server, and has made no response
```

## What waits

Everything else a view reads from a request is worked out when it is read.

| attribute | made | from |
|---|---|---|
| `GET` | once, on first read; a `cached_property` of each subclass | the query string |
| `COOKIES` | once, on first read; a `cached_property` of each subclass | the `"Cookie"` header |
| `HttpRequest.headers` | once, on first read | every header in `META` |
| `HttpRequest.accepted_types` | once, on first read | the `"Accept"` header |
| `POST`, `FILES` | together, by the first read of either; a property of each subclass over `HttpRequest._load_post_and_files` | the body's stream |
| `HttpRequest.body` | on first read, and kept | the body's stream |
| `HttpRequest.upload_handlers` | when first asked for, which parsing a multipart body does | `settings.FILE_UPLOAD_HANDLERS` |
| `HttpRequest.scheme`, `HttpRequest.get_host`, `HttpRequest.get_port` | on every call | `META` and the settings; for an `ASGIRequest`'s scheme, the scope |

*What a request works out on demand. The first four are kept on the instance once made, so a change to `META` afterwards does not reach them.*

A `cached_property` stores its result under its own name on the instance, so `GET` and `COOKIES` can also simply be assigned, and `POST` has a setter for the purpose. `FILES` has none.

Other attributes of a request are not `django.http`'s at all. The handler sets `HttpRequest.resolver_match` when the URL has been resolved, and middleware add the session, the user and the rest; [From the server's call to the view](../overview/arrival.md#the-way-in) follows a request through the default set (`django/core/handlers/base.py:BaseHandler.resolve_request`).
