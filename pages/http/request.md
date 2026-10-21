---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Making the request: `WSGIRequest` and `ASGIRequest`

`WSGIRequest.__init__` and `ASGIRequest.__init__` make a request from what a server passes, the environ or the scope: they set the path, the method, `META`, the content type and the encoding, and leave the collections and the body to be worked out when they are first read. An exception they raise is raised before any middleware runs.

`HttpRequest` declares nearly everything a view uses on a request: the methods that work out the host and the scheme, the property that reads the body, the code that parses a form. What it does not know is where a request comes from. Its own `__init__` makes an empty one, with no path, no method, and empty collections, which a test or a script can make when it needs a request and has no server. A request that came from a server is an instance of one of two subclasses, each with a constructor that fills the same attributes from a different source. Neither constructor calls the base one, and a comment in the base's `__init__` warns that each assignment made there should be made in `WSGIRequest.__init__` as well: the two are kept in step by hand (`django/http/request.py:HttpRequest.__init__`).

In the figure the two columns differ in what `META` is, whether the path is decoded a second time, and what the body's stream is.

```text figure=two-sources
the environ, from a WSGI server                  the scope, from an ASGI server,
                                                 and the body file the handler has received
    ->  WSGIRequest.__init__                         ->  ASGIRequest.__init__

the same attributes on either request:
  META                the environ itself                 built from the scope, in WSGI's keys
  path, path_info     decoded a second time              the scope's, already text
  the body's stream   a LimitedStream over "wsgi.input"  the body file, as it is
  content_type,                  both constructors, near their end:
  content_params,               HttpRequest._set_content_type_params
  encoding
```

*The two constructors side by side. Each column runs from what a server passes, through its constructor, to what that constructor puts in each attribute; a row is an attribute both set, and the foot is the method both call.*

## From a WSGI environ

A WSGI server passes one dictionary, the environ. `WSGIRequest.__init__` does not copy it: the request's `META` is that same dictionary, and the request also keeps it as `environ` (`django/core/handlers/wsgi.py:WSGIRequest.__init__`).

The path needs work before it can be used, for a reason that lies in WSGI itself. The interface has the server pass what it takes from the request as `str`, and the server makes one from the bytes of the request line by decoding them as ISO-8859-1, whatever they were. A path of UTF-8 bytes therefore arrives as the wrong characters, two or more for each accented letter. Django undoes the server's step and then decodes properly: `get_bytes_from_wsgi` encodes the string with ISO-8859-1, which gives back exactly the bytes the server had, and `get_path_info` decodes those as UTF-8, first percent-escaping any byte sequence that is not valid UTF-8 so that the decoding cannot fail (`django/core/handlers/wsgi.py:get_bytes_from_wsgi`, `django/core/handlers/wsgi.py:get_path_info`, `django/utils/encoding.py:repercent_broken_unicode`).

A request has two paths. The **script name** is the part of the URL that belongs to the place the server mounted the application, and `HttpRequest.path_info` is the rest, the part the URL resolver matches. `HttpRequest.path` is the two joined, ordinarily the path the client asked for. `get_script_name` takes the script name from `settings.FORCE_SCRIPT_NAME` when that is not `None`; otherwise from `"SCRIPT_URL"` or `"REDIRECT_URL"`, in which Apache's mod_rewrite leaves the URL as it was before rewriting, with the path info taken off its end, so that the script name is the one the client saw; and otherwise from the environ's `"SCRIPT_NAME"` (`django/core/handlers/wsgi.py:get_script_name`). An empty path info is treated as `"/"`. The constructor then writes the decoded script name and path info back into the environ, so `META` holds the corrected values (`django/core/handlers/wsgi.py:WSGIRequest.__init__`).

The environ mounts the chapter's recorded shop at `"/shop"` and passes a path with one accented letter as a WSGI server would, the letter's two bytes of UTF-8 as two characters. After the constructor, `path_info` is the decoded path, and so is `"PATH_INFO"` in `META`, where the constructor wrote it back.

```text recording=http
WSGI: the environ is META, and the path is decoded again
    the environ: SCRIPT_NAME '/shop', and PATH_INFO as a WSGI server passes it, '/caf\xc3\xa9/'
    request.META is environ: True
    request.path_info: '/café/'
    request.path: '/shop/café/'
    request.META["PATH_INFO"]: '/café/'
    ...
```

The rest of the constructor is short. The method is the environ's, in upper case. The `Content-Type` header is parsed, which the section below is about. And the server's input stream, the environ's `"wsgi.input"`, is wrapped in a `LimitedStream` whose limit is the `Content-Length` header as an integer, or zero when the header is missing or is not a number. The wrapper counts what has been read and returns nothing once the declared length is reached, whatever the stream under it would have done. A `WSGIRequest` whose environ has no `"CONTENT_LENGTH"` therefore has an empty body (`django/core/handlers/wsgi.py:WSGIRequest.__init__`, `django/core/handlers/wsgi.py:LimitedStream`).

## From an ASGI scope

An ASGI server passes a dictionary called the scope, and the body arrives separately, as messages. By the time an `ASGIRequest` is made the handler has received the whole body into a temporary file, one that is held in memory until it grows past `settings.FILE_UPLOAD_MAX_MEMORY_SIZE` and is then written to disk (`django/core/handlers/asgi.py:ASGIHandler.read_body`), and the constructor is given the scope and that file ([The two entry points](../handlers/entry.md#an-asgi-request) has the handler's side). The file becomes the request's stream as it is, with no wrapper (`django/core/handlers/asgi.py:ASGIRequest.__init__`).

The scope is not shaped like an environ, and a great deal of code reads `META` by WSGI's keys, so the constructor builds a `META` that looks like one.

The scope's path is already text, so nothing is decoded a second time. The script name is `settings.FORCE_SCRIPT_NAME` when that is set to anything but an empty value, and otherwise the scope's `"root_path"`; the path info is the path with that prefix taken off, when the path is the prefix or continues it with a slash, and otherwise the whole path. WSGI's test is only that the setting is not `None`, so a setting of `""` forces an empty script name under WSGI and is passed over under ASGI (`django/core/handlers/asgi.py:get_script_prefix`, `django/core/handlers/asgi.py:ASGIRequest.__init__`).

Each header becomes a key as a WSGI server would have written it: upper case, hyphens as underscores, `"HTTP_"` in front, except for the content type and the content length, which WSGI leaves without the prefix. That mapping loses something: a header named `"x-token"` and one named `"x_token"` land on the same key, so that one can be passed off as the other. The constructor therefore drops every header with an underscore in its name (`django/core/handlers/asgi.py:ASGIRequest.__init__`). Under WSGI this is the server's affair, and Django's development server does the same before it builds the environ (`django/core/servers/basehttp.py:WSGIRequestHandler.get_environ`).

> **Changed in 6.0.4 and 5.2.13.** Until these security releases, and 4.2.30, `ASGIRequest` kept a header named with underscores under the key of its hyphenated twin, so that a client could spoof a header a reverse proxy strips (CVE-2026-3902). It now ignores such headers, as Daphne, the reference ASGI server, does (`docs/releases/6.0.4.txt`).

A header that arrives more than once is joined into one value with commas. Cookies are the exception. HTTP/2 lets a client send each cookie as a `"cookie"` header of its own, and a comma is not what separates cookies, so those values are joined with a semicolon and a space (`django/core/handlers/asgi.py:ASGIRequest.__init__`).

The recorded scope sends `"accept"` and `"cookie"` twice each, and `"x_token"` just before `"x-token"`. In the last lines of `META` each repeated header has become one value, the accepts joined by a comma and the cookies by a semicolon, and `"HTTP_X_TOKEN"` holds the hyphenated header's value alone.

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
    ...
    META['HTTP_COOKIE']: 'theme=dark; basket=3'
    ...
    META['HTTP_ACCEPT']: 'text/html,application/json'
    META['HTTP_X_TOKEN']: 'abc'
    META['CONTENT_TYPE']: 'text/plain'
    META['CONTENT_LENGTH']: '0'
```

## The content type and the encoding

Both constructors call `HttpRequest._set_content_type_params` near their end. It splits the `Content-Type` header into `HttpRequest.content_type`, the media type in lower case, and `HttpRequest.content_params`, a dictionary of the parameters after it. The content type is what later decides how the body is read. If one of the parameters is a charset that Python has a codec for, it becomes the request's `encoding` (`django/http/request.py:HttpRequest._set_content_type_params`).

The **encoding** of a request is the character set used to decode the percent-escapes in a `WSGIRequest`'s query string and the names and values of a multipart form. It is `None` on most requests, which means `settings.DEFAULT_CHARSET`. A view or a middleware may assign it, and because the collections may already have been decoded with the old value, the setter deletes `GET` and the parsed `POST`, so that the next read parses them again (`django/http/request.py:HttpRequest.encoding`). On a `WSGIRequest` or an `ASGIRequest` the next read of `GET` does parse it again, since there `GET` is a `cached_property`. A plain `HttpRequest` keeps `GET` as an ordinary attribute, set by its `__init__`: the setter deletes that too, and nothing makes it again, so a read of `GET` afterwards raises `AttributeError`.

An ordinary form, of `"application/x-www-form-urlencoded"`, is always decoded as UTF-8. While the encoding is `None` or `"utf-8"`, whatever the case of its letters, the next read of `POST` parses the form again from the body the first read kept; set to anything else, by a view or by the `Content-Type`'s charset, the encoding makes a read of `POST` raise `BadRequest` instead. A multipart form that was parsed from the stream cannot be parsed again, since a read of `POST` after the stream has been read with nothing kept gives an empty form ([The body: `body`, `POST` and `FILES`](body.md)). The setter leaves `FILES` alone, so it still holds the files of the first parse until `POST` is read again; that read comes back empty, and empties `FILES` with it (`django/http/request.py:HttpRequest._load_post_and_files`).

The two subclasses differ in what `GET` does with the encoding. `WSGIRequest.GET` passes it to the `QueryDict` it makes. `ASGIRequest.GET` does not: its constructor has decoded the scope's query string as UTF-8 to put it in `META`, and the `QueryDict` decodes the percent-escapes in it with the default charset, whatever the request's encoding is (`django/core/handlers/wsgi.py:WSGIRequest.GET`, `django/core/handlers/asgi.py:ASGIRequest.__init__`, `django/core/handlers/asgi.py:ASGIRequest.GET`).

> **Trap.** The setter of `HttpRequest.encoding` is meant, by its docstring, to throw away a `GET` already made. It stores the new encoding, then asks whether the request has `GET`, and deletes it if so (`django/http/request.py:HttpRequest.encoding`). On a `WSGIRequest` or an `ASGIRequest`, where `GET` is a `cached_property`, asking computes a `GET` not yet read, and the deletion throws away what was just computed. So a `Content-Type` that names a known charset has the query string parsed while the request is being made, for nothing, and parsed again at the next read of `GET`.

Under `WSGIRequest.__init__`, the line that assigns the encoding has a read of `WSGIRequest.GET` nested under it, and the `QueryDict` made there is given the new charset before the constructor has reached the stream. The last line reads `GET` once the request is made.

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

> **Trap.** A request is made before the middleware chain is entered, so an exception its constructor raises is not turned into a response by the chain. `_set_content_type_params` raises `BadRequest` when `parse_header_parameters` cannot parse the header, which happens, among other cases, when the header is longer than `MAX_HEADER_LENGTH`, 10,000 characters, or has a parameter in an encoding that cannot be applied (`django/utils/http.py:parse_header_parameters`). The setter's parse of the query string raises `TooManyFieldsSent` from the constructor in the same way, when the query string has more pieces between ampersands than `settings.DATA_UPLOAD_MAX_NUMBER_FIELDS` allows (`django/http/request.py:QueryDict.__init__`). `ASGIHandler.create_request` answers a `UnicodeDecodeError`, raised by a query string that is not UTF-8, with a 400 of its own, but catches neither of these ([The two entry points](../handlers/entry.md#an-asgi-request)). Under either handler, then, the exception reaches the server with no response made, and what the client sees is the server's doing (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.create_request`).

A `Content-Type` of 10,014 characters stops `WSGIRequest.__init__` in `_set_content_type_params`, and the last line is the handler's: it raises the exception to the server and has made no response.

```text recording=http
...
a request whose Content-Type header is 10,014 characters long; no view is reached
  WSGIRequest.__init__(environ)
    HttpRequest._set_content_type_params
      raises BadRequest
  the handler raises BadRequest to the server, and has made no response
```

## What a request works out when it is read

On a `WSGIRequest` or an `ASGIRequest`, the attributes in the table are worked out when they are read.

| attribute | made | from |
|---|---|---|
| `GET` | on first read; a `cached_property` of each subclass | the query string |
| `COOKIES` | once, on first read; a `cached_property` of each subclass | the `"Cookie"` header |
| `HttpRequest.headers` | once, on first read | every header in `META` |
| `HttpRequest.accepted_types` | once, on first read | the `"Accept"` header |
| `POST`, `FILES` | together, by the first read of either; a property of each subclass over `HttpRequest._load_post_and_files` | the body's stream |
| `HttpRequest.body` | on first read, and kept | the body's stream |
| `HttpRequest.upload_handlers` | when first asked for, which parsing a multipart body does | `settings.FILE_UPLOAD_HANDLERS` |
| `HttpRequest.scheme`, `HttpRequest.get_host`, `HttpRequest.get_port` | on every call | `META`, an `ASGIRequest`'s scope, and the settings ([Headers, host and scheme](headers.md)) |

*What a request works out on demand. The first four are kept on the instance, `GET` until the encoding is set, so a change to `META` afterwards does not reach them.*
