---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The response object

`HttpResponseBase` is what every response is made of: a status and its reason phrase, the headers and the rules `ResponseHeaders` holds them to, a charset and cookies. `HttpResponse` adds a body held in memory, and the classes named for a status, the redirects `HttpResponseRedirect` and `HttpResponsePermanentRedirect`, and `JsonResponse` are `HttpResponse` with a little added.

A response leaves a server as a status line, some headers and a body, in that order and once. A view does not produce it in that order or at once. It makes an object, and the object is then passed outwards through middleware that add a header here and replace the body there, so every part has to stay separately changeable until the chain hands the response back.

The response classes descend from `HttpResponseBase`. In the figure's tree, look at the split under `HttpResponseBase`, between a body held whole and a body that is an iterator, and at how little most of the classes under `HttpResponse` add.

```text figure=the-classes
HttpResponseBase                              a status and its reason phrase, headers, a charset,
 |                                            cookies, closers; no body
 |
 |-- HttpResponse                             a body, held whole in memory as bytes
 |    |
 |    |-- HttpResponseRedirectBase            a "Location" header, escaped, and two checks
 |    |    |-- HttpResponseRedirect
 |    |    |-- HttpResponsePermanentRedirect
 |    |
 |    |-- the other classes named for a status:
 |    |     HttpResponseNotModified           each a status of its own,
 |    |     HttpResponseBadRequest            and two of them a little more
 |    |     HttpResponseForbidden
 |    |     HttpResponseNotFound
 |    |     HttpResponseNotAllowed
 |    |     HttpResponseGone
 |    |     HttpResponseServerError
 |    |
 |    |-- JsonResponse                        data serialised as JSON, as "application/json"
 |    |
 |    |-- SimpleTemplateResponse                                                 told elsewhere
 |         |
 |         |-- TemplateResponse
 |
 |-- StreamingHttpResponse                    a body that is an iterator         told elsewhere
      |-- FileResponse
```

*Django's response classes, each under the class it is made from, most with what they add beside them. Apart from the redirects, the classes named for a status stand in one box, which names them; the table of them below gives each its status and what it adds. The two branches marked told elsewhere are told on other pages, and the rest here.*

The streaming responses, `StreamingHttpResponse` and its subclass `FileResponse`, are told in [Streaming and file responses](streaming.md) (`django/http/response.py:StreamingHttpResponse`, `django/http/response.py:FileResponse`), and the template responses, `SimpleTemplateResponse`, a subclass of `HttpResponse`, and its subclass `TemplateResponse`, in [`SimpleTemplateResponse` and `TemplateResponse`](../templates/responses.md) (`django/template/response.py:SimpleTemplateResponse`, `django/template/response.py:TemplateResponse`).

## What the constructor sets

`HttpResponseBase.__init__` takes optional arguments for a content type, a status, a reason, a charset and a dictionary of headers, and sets everything about a response except its content (`django/http/response.py:HttpResponseBase.__init__`).

The **headers** come first. They are a `ResponseHeaders`, filled from the dictionary if one was given. If they then hold no `Content-Type`, one is set: the argument if it was given, and otherwise `"text/html"` with the response's charset. Every response therefore leaves this constructor with a `Content-Type`, even a 204, whose status says it has no content: nothing in the constructor looks at the status when it sets the header. An `HttpResponse` of anything but HTML has to be told so. A `content_type` argument given when the dictionary already holds a `Content-Type` raises `ValueError`.

The **status** is a class attribute, `HttpResponseBase.status_code`, which is 200, and an argument replaces it on the instance. The argument is converted with `int`, and the result must lie from 100 to 599. The **reason phrase**, the words after the number on the status line, is normally not stored at all: `HttpResponseBase.reason_phrase` is a property that looks the status code up in Python's table of standard phrases each time it is read, so a response whose status is changed after it was made gets the right words (`django/http/response.py:HttpResponseBase.reason_phrase`).

Every response these constructors made has its `Content-Type`, the 204 included; 299, a status with no standard phrase, gets a placeholder, and 600 is refused. The bodies are bytes already, the first two the same four letters in two charsets and the third an iterator's items joined.

```text recording=http
The response classes: what a constructor leaves
    HttpResponse("café")  ->  200 OK; headers: Content-Type: text/html; charset=utf-8; body b'caf\xc3\xa9'
    HttpResponse("café", content_type="text/plain; charset=iso-8859-1")  ->  200 OK; headers: Content-Type: text/plain; charset=iso-8859-1; body b'caf\xe9'
    HttpResponse(iter(["a", b"b", 3]))  ->  200 OK; headers: Content-Type: text/html; charset=utf-8; body b'ab3'
    HttpResponse(status=204)  ->  204 No Content; headers: Content-Type: text/html; charset=utf-8
    HttpResponse(status=299)  ->  299 Unknown Status Code; headers: Content-Type: text/html; charset=utf-8
    HttpResponse(status=600)  ->  raises ValueError: HTTP status code must be an integer from 100 to 599.
    ...
```

The constructor also sets up an empty `SimpleCookie` as `HttpResponseBase.cookies` ([Cookies](cookies.md)), and what the end of the response's life will need: an empty list of closers and a flag that says the response is not closed ([Streaming and file responses](streaming.md#closing)). It leaves `HttpResponseBase._handler_class` at `None`; the WSGI or ASGI handler sets it to its own class when the chain hands the response back, so that `HttpResponseBase.close` can name that class as the sender of `request_finished` (`django/core/handlers/wsgi.py:WSGIHandler.__call__`, `django/core/handlers/asgi.py:ASGIHandler.run_get_response`, `django/http/response.py:HttpResponseBase.close`).

## Headers: `ResponseHeaders`

A response's headers are a mapping from name to value in which the case of a name does not matter. `ResponseHeaders` is built on the same `CaseInsensitiveMapping` as a request's `HttpHeaders`, and adds what that read-only class lacks: assignment, deletion, `pop` and `setdefault` (`django/http/response.py:ResponseHeaders`).

The response passes some dictionary operations through to it, so each has two spellings. `response.headers["Vary"]` and `response["Vary"]` are the same entry, and a membership test, a deletion, `get`, `items` and `setdefault` on a response all mean its headers (`django/http/response.py:HttpResponseBase.__setitem__`).

There is one entry for a name. Setting a header that is already set replaces it, in whatever case the two were written, and the newer spelling of the name is the one sent. A header that should carry several values, such as `"Vary"`, has to be built up as one comma-separated string; that is what the helpers that patch such headers do (`django/utils/cache.py:patch_vary_headers`, in [Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md)). Cookies cannot be combined that way, since each needs a `Set-Cookie` line of its own, and they are kept apart from the headers, in a collection of their own.

Every value goes through `ResponseHeaders.__setitem__`, which makes it fit to be sent or refuses it (`django/http/response.py:ResponseHeaders._convert_to_charset`). A name must be ASCII. A value may be a string, bytes or anything else, which is converted with `str`, and must fit in Latin-1; one that does not is not refused but written as a MIME encoded word, the form email uses for a header that is not ASCII. A carriage return or a line feed in a value raises `BadHeaderError`.

The value with a coffee cup, which Latin-1 cannot hold, is stored as an encoded word, and the value with a line break is refused, as is the name that is not ASCII. Assigned in lower case, `"content-type"` replaces the default header and is listed in its own spelling. The last line is a reason phrase, refused.

```text recording=http
Headers on a response: what is stored, and what is refused
    response["X-Note"] = "plain"  ->  stored as 'plain'
    response["X-Note"] = 42  ->  stored as '42'
    response["X-Note"] = "café"  (Latin-1 can hold it)  ->  stored as 'café'
    response["X-Note"] = "naïve ☕"  (Latin-1 cannot)  ->  stored as '=?utf-8?b?bmHDr3ZlIOKYlQ==?='
    response["X-Note"] = "one\r\nSet-Cookie: stolen=1"  ->  raises BadHeaderError: Header values can't contain newlines (got 'one\r\nSet-Cookie: stolen=1')
    response["X-Nöte"] = "x"  (a name that is not ASCII)  ->  raises UnicodeEncodeError: 'ascii' codec can't encode character '\xf6' in position 3: ordinal not in range(128), HTTP response headers must be in ascii format
    response["content-type"] = "text/plain", then response.items()  ->  [('content-type', 'text/plain')]
    "CONTENT-TYPE" in response  ->  True
    HttpResponse(reason="Fine\r\nX: y")  ->  raises BadHeaderError: reason_phrase can't contain control characters.
```

The refusal that matters is the one with `Set-Cookie` in the value. Headers are separated by line breaks, so a value containing one would end its own header and begin another, and a view that copies part of a request into a header, as a file name or a redirect target, would be handing the client the means to write headers into its own response. The check is in the method every entry of the headers passes through, so no way of setting one avoids it. A reason phrase is held to a stricter rule by its setter, which since 6.1 refuses any control character (`django/http/response.py:HttpResponseBase.reason_phrase`).

## The charset

A response has a charset because its body is bytes and a view usually supplies text. `HttpResponseBase.charset` is a property that answers with the first of these it finds: a charset given to the constructor or assigned later, a charset parameter in the `Content-Type` header, and `settings.DEFAULT_CHARSET`. The second is read from the header every time and not stored, deliberately, so that a `Content-Type` replaced later takes its charset with it (`django/http/response.py:HttpResponseBase.charset`).

Content is encoded in one place, `HttpResponseBase.make_bytes`: bytes are kept, a string is encoded with the charset, and anything else is turned into a string first (`django/http/response.py:HttpResponseBase.make_bytes`).

## The body of an `HttpResponse`

`HttpResponse.content` is a property over a list of byte strings. Assigning to it replaces the list with a single item. If what was assigned has an `__iter__` and is not a string, bytes or a `memoryview`, it is consumed there and then, each item converted and all of them joined, and closed if it has a `close`: an `HttpResponse` always holds its whole body, which is what lets a middleware read `content`, measure it or compress it, and what makes the response safe to iterate more than once (`django/http/response.py:HttpResponse.content`). An `HttpResponse` sets no `Content-Length` of its own: `CommonMiddleware` adds one on the way out, from the length of `content`, if none is set (`django/middleware/common.py:CommonMiddleware.process_response`).

Reading the property joins the list. `HttpResponse.write` appends to it, which is why a response can be given wherever something wants a file to write to; `tell`, `flush`, `writelines` and `getvalue` fill out that pretence. Iterating the response yields the items of the list, so a WSGI server is given the constructor's content and each `write` as separate pieces.

> **Trap.** Nothing in `django.http` or in the handlers leaves out the body of a response to a `"HEAD"` request: a `WSGIHandler` gives the server the view's body as it would for a `"GET"`. Leaving the body out of what is sent is the server's work, which Django's development server does for itself; the test client does it too, in `conditional_content_removal`, before a test sees the response (`django/core/servers/basehttp.py:ServerHandler.finish_response`, `django/test/client.py:conditional_content_removal`).

`HttpResponse.text` is the body decoded with the charset.

> **Trap.** `text` is a `cached_property`. Assigning `content` clears it; `write` does not. A response whose `text` has been read and which is then written to goes on reporting the old text: made with `"one"`, read, and written to with `" two"`, a response holds `b'one two'` and its `text` is still `'one'`, until `content` is assigned again (`django/http/response.py:HttpResponse.text`, `django/http/response.py:HttpResponse.write`).

## The classes named for a status

Several of the response classes are `HttpResponse` with a different `status_code` and nothing else, a class statement with one attribute; the others add a little (`django/http/response.py:HttpResponseNotModified`, `django/http/response.py:HttpResponseNotAllowed`).

| class | status | what it adds |
|---|---|---|
| `HttpResponseRedirect` | 302, or 307 | a `"Location"` header; see below |
| `HttpResponsePermanentRedirect` | 301, or 308 | a `"Location"` header; see below |
| `HttpResponseNotModified` | 304 | removes the `Content-Type` header, and refuses any content |
| `HttpResponseBadRequest` | 400 | nothing but its status |
| `HttpResponseForbidden` | 403 | nothing but its status |
| `HttpResponseNotFound` | 404 | nothing but its status |
| `HttpResponseNotAllowed` | 405 | takes the permitted methods as its first argument and lists them in an `"Allow"` header |
| `HttpResponseGone` | 410 | nothing but its status |
| `HttpResponseServerError` | 500 | nothing but its status |

*The subclasses of `HttpResponse` that are named for a status.*

`Http404` is defined in the same module and is not one of them. It is an exception, raised by a view that wants the site's 404 page and turned into a response by the middleware chain; a view that returns `HttpResponseNotFound` is supplying the page itself ([How an exception becomes a response](../handlers/exceptions.md)).

## Redirects

A redirect is a response whose point is one header. `HttpResponseRedirectBase.__init__` takes the target first, sets it as `"Location"` after escaping it into ASCII, and then makes two checks (`django/http/response.py:HttpResponseRedirectBase.__init__`).

The scheme of the target, if it has one, must be in the class's `allowed_schemes`: `"http"`, `"https"` or `"ftp"`. This is the check that keeps a redirect built from user input from sending a browser to a URL that begins `"javascript:"`. A target with no scheme passes, whether it is a path on the same site or begins with two slashes and names another host. The `"Location"` value, as escaped, must be no longer than `MAX_URL_REDIRECT_LENGTH`, 16,384 characters, unless the caller passes `max_length`, an argument added in 6.1, with another maximum or with `None` for no check. Either failure raises `DisallowedRedirect`, a `SuspiciousOperation`, so a view that lets it escape answers with a 400.

With `preserve_request=True`, an argument added in 5.2, the two classes use 307 and 308 in place of 302 and 301. A browser may turn a redirected `POST` into a `GET` after the older pair; the newer pair tell it to repeat the request as it was, method and body.

Among these redirects, the target with accents reaches `"Location"` escaped, the two that preserve the request have 307 and 308, and the last two are refused, one for its scheme and one for its length.

```text recording=http
...
HttpResponseRedirect("/next/")  ->  302 Found; headers: Content-Type: text/html; charset=utf-8, Location: /next/
HttpResponseRedirect("/next/", preserve_request=True)  ->  307 Temporary Redirect; headers: Content-Type: text/html; charset=utf-8, Location: /next/
HttpResponsePermanentRedirect("/café/?q=é")  ->  301 Moved Permanently; headers: Content-Type: text/html; charset=utf-8, Location: /caf%C3%A9/?q=%C3%A9
HttpResponsePermanentRedirect("/next/", preserve_request=True)  ->  308 Permanent Redirect; headers: Content-Type: text/html; charset=utf-8, Location: /next/
HttpResponseRedirect("javascript:alert(1)")  ->  raises DisallowedRedirect: Unsafe redirect to URL with protocol 'javascript'
HttpResponseRedirect("/" + "x" * 16384)  ->  raises DisallowedRedirect: Unsafe redirect exceeding 16384 characters
...
```

Neither check decides whether the target's host is a safe place to send a visitor. That is a separate question with a separate function, `url_has_allowed_host_and_scheme` ([The helpers in `django/utils/http.py`](helpers.md#urls-that-came-from-a-client-url_has_allowed_host_and_scheme)). Nor is the target made into a full URL: a path stays a path.

## `JsonResponse`

`JsonResponse` is given data, not content. Its constructor serialises the data with `json.dumps`, using `DjangoJSONEncoder` unless it is given another encoder, a class that also knows dates, times, decimals and UUIDs; it sets the content type to `"application/json"` unless given a `content_type`; and it hands the result to `HttpResponse` as the body (`django/http/response.py:JsonResponse.__init__`, `django/core/serializers/json.py:DjangoJSONEncoder`).

> **Changed in 6.2.** `JsonResponse` used to refuse anything but a dictionary unless it was called with `safe=False`, as a guard against an attack on a JSON array through JavaScript's array prototype, which ECMAScript 5 closed (`docs/releases/6.2.txt`). The argument's default is now `None`, which is treated as false, so a list is serialised without comment; passing it anything but `None` warns with `RemovedInDjango2029Warning`, though `safe=True` still raises for a non-dictionary until the argument is removed.

The first of the three constructors passes no argument named safe and has its list serialised; the other two pass one, and each is warned.

```text recording=http
...
JsonResponse([1, 2])  ->  200 OK; headers: Content-Type: application/json; body b'[1, 2]'
JsonResponse({"a": 1}, safe=False)  ->  200 OK; headers: Content-Type: application/json; body b'{"a": 1}'; warns RemovedInDjango2029Warning: The safe parameter is deprecated.
JsonResponse([1, 2], safe=True)  ->  raises TypeError: In order to allow non-dict objects to be serialized set the safe parameter to False.; warns RemovedInDjango2029Warning: The safe parameter is deprecated.
```
