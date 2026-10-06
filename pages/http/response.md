---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The response object

What an `HttpResponse` is made of: the status and its reason phrase, the headers and the rules `ResponseHeaders` holds them to, the charset, and the body; and the classes that differ from it by a status code, the redirects and `JsonResponse`.

A response leaves a server as a status line, some headers and a body, in that order and once. A view does not produce it in that order or at once. It makes an object, and the object is then passed outwards through middleware that add a header here and replace the body there, so every part has to stay separately changeable until the handler reads them all. `HttpResponseBase` is that object without a body, and `HttpResponse` adds a body held in memory.

## What the constructor sets

`HttpResponseBase.__init__` takes optional arguments for a content type, a status, a reason, a charset and a dictionary of headers, and from them sets everything about a response except its content (`django/http/response.py:HttpResponseBase.__init__`).

The **headers** come first. They are a `ResponseHeaders`, filled from the dictionary if one was given. If they then hold no `Content-Type`, one is set: the argument if it was given, and otherwise `"text/html"` with the response's charset. Every response therefore starts with a `Content-Type`, and a view that returns something other than HTML has to say so. Passing the header both ways at once raises `ValueError`.

The **status** is a class attribute, `HttpResponseBase.status_code`, which is 200, and an argument replaces it on the instance. The argument is converted with `int`, and the result must lie from 100 to 599. The **reason phrase**, the words after the number on the status line, is normally not stored at all: `HttpResponseBase.reason_phrase` is a property that looks the status code up in Python's table of standard phrases each time it is read, so a response whose status is changed after it was made gets the right words (`django/http/response.py:HttpResponseBase.reason_phrase`).

The constructor also sets up what the end of the response's life will need: an empty `SimpleCookie` as `HttpResponseBase.cookies` ([Cookies](cookies.md)), an empty list of closers, a place for the handler to leave its class, and a flag that says the response is not closed ([Streaming and file responses](streaming.md#closing)).

```text recording=http
HttpResponse("café")  ->  200 OK; headers: Content-Type: text/html; charset=utf-8; body b'caf\xc3\xa9'
HttpResponse("café", content_type="text/plain; charset=iso-8859-1")  ->  200 OK; headers: Content-Type: text/plain; charset=iso-8859-1; body b'caf\xe9'
HttpResponse(iter(["a", b"b", 3]))  ->  200 OK; headers: Content-Type: text/html; charset=utf-8; body b'ab3'
HttpResponse(status=204)  ->  204 No Content; headers: Content-Type: text/html; charset=utf-8
HttpResponse(status=299)  ->  299 Unknown Status Code; headers: Content-Type: text/html; charset=utf-8
HttpResponse(status=600)  ->  raises ValueError: HTTP status code must be an integer from 100 to 599.
```

The lines with a status are the rules above at work. A status with no response class of its own is made by passing the number, and an unassigned one gets a placeholder for a phrase. The 204 shows the default at its least useful: a response that by definition has no content still declares that it is HTML, because nothing in the constructor looks at the status when it sets the header. The line that passes an iterator belongs to the body, below.

## Headers: `ResponseHeaders`

A response's headers are a mapping from name to value in which the case of a name does not matter. `ResponseHeaders` is built on the same `CaseInsensitiveMapping` as a request's `HttpHeaders`, and adds what that read-only class lacks: assignment, deletion, `pop` and `setdefault` (`django/http/response.py:ResponseHeaders`).

The response passes the common dictionary operations through to it, so each has two spellings. `response.headers["Vary"]` and `response["Vary"]` are the same entry, and a membership test, a deletion, `get`, `items` and `setdefault` on a response all mean its headers (`django/http/response.py:HttpResponseBase.__setitem__`).

There is one entry for a name. Setting a header that is already set replaces it, in whatever case the two were written, and the newer spelling of the name is the one sent. A header that should carry several values, such as `"Vary"`, has to be built up as one comma-separated string; that is what the helpers that patch such headers do (`django/utils/cache.py:patch_vary_headers`, in [Caching, files, mail, signals and tasks](../services.md)). Cookies cannot be combined that way, since each needs a `Set-Cookie` line of its own, and they are kept apart from the headers, in a collection of their own.

Every value goes through `ResponseHeaders.__setitem__`, which makes it fit to be sent or refuses it (`django/http/response.py:ResponseHeaders._convert_to_charset`).

```text recording=http
response["X-Note"] = "plain"  ->  stored as 'plain'
response["X-Note"] = 42  ->  stored as '42'
response["X-Note"] = "café"  (Latin-1 can hold it)  ->  stored as 'café'
response["X-Note"] = "naïve ☕"  (Latin-1 cannot)  ->  stored as '=?utf-8?b?bmHDr3ZlIOKYlQ==?='
response["X-Note"] = "one\r\nSet-Cookie: stolen=1"  ->  raises BadHeaderError: Header values can't contain newlines (got 'one\r\nSet-Cookie: stolen=1')
response["X-Nöte"] = "x"  (a name that is not ASCII)  ->  raises UnicodeEncodeError: 'ascii' codec can't encode character '\xf6' in position 3: ordinal not in range(128), HTTP response headers must be in ascii format
response["content-type"] = "text/plain", then response.items()  ->  [('content-type', 'text/plain')]
"CONTENT-TYPE" in response  ->  True
```

A name must be ASCII. A value may be a string, bytes or anything else, which is converted with `str`, and must fit in Latin-1, the character set HTTP gives header values; one that does not is not refused but written as a MIME encoded word, the form email uses for a header that is not ASCII, as the line with the coffee cup shows.

The refusal that matters is the one with `Set-Cookie` in the value. A carriage return or a line feed in a value raises `BadHeaderError`. Headers are separated by line breaks, so a value containing one would end its own header and begin another, and a view that copies part of a request into a header, as a file name or a redirect target, would be handing the client the means to write headers into its own response. The check is in the method every header passes through, so no way of setting a header avoids it. A reason phrase is held to a stricter rule by its setter, which refuses any control character.

## The charset

A response has a charset because its body is bytes and a view usually supplies text. `HttpResponseBase.charset` is a property that answers with the first of these it finds: a charset given to the constructor or assigned later, a charset parameter in the `Content-Type` header, and `settings.DEFAULT_CHARSET`. The second is read from the header every time and not stored, deliberately, so that a `Content-Type` replaced later takes its charset with it (`django/http/response.py:HttpResponseBase.charset`).

Content is encoded in one place, `HttpResponseBase.make_bytes`, through which every piece of it passes: bytes are kept, a string is encoded with the charset, and anything else is turned into a string first. In the recording under the constructor above, the same four letters came out a byte longer under UTF-8 than under ISO-8859-1. The charset is read in two other places, for the default `Content-Type` and for `text`, below.

## The body of an `HttpResponse`

`HttpResponse.content` is a property over a list of byte strings. Assigning to it replaces the list with a single item. If what was assigned can be iterated and is not a string, bytes or a `memoryview`, it is consumed there and then, each item converted and all of them joined, and closed if it has a `close`: an `HttpResponse` always holds its whole body, which is what lets a middleware read `content`, measure it or compress it, and what makes the response safe to iterate more than once (`django/http/response.py:HttpResponse.content`).

Reading the property joins the list. `HttpResponse.write` appends to it, which is why a response can be given wherever something wants a file to write to; `tell`, `flush`, `writelines` and `getvalue` fill out that pretence. Iterating the response yields the items of the list, so the server is given the constructor's content and each `write` as separate pieces.

`HttpResponse.text` is the body decoded with the charset.

> **A trap.** `text` is a `cached_property`. Assigning `content` clears it; `write` does not. A response whose `text` has been read and which is then written to goes on reporting the old text.

`bytes(response)` gives the headers, a blank line and the body as one byte string. It is not what is sent: it has no status line, and no cookies (`django/http/response.py:HttpResponse.serialize`).

What sets a `Content-Length`, and what becomes of a `"HEAD"` request, are both settled elsewhere. An `HttpResponse` does not set its own `Content-Length`: `CommonMiddleware` adds one on the way out if none is set, from the length of `content`. And a `"HEAD"` request is not treated differently by anything in `django.http` or in the handlers. The view returns a response with a body, and leaving the body out of what is sent is the server's work, which Django's development server does for itself (`django/middleware/common.py:CommonMiddleware.process_response`, `django/core/servers/basehttp.py:ServerHandler.finish_response`).

## The classes named for a status

Several of the response classes are `HttpResponse` with a different `status_code` and nothing else, a class statement with one attribute; the others add a little.

| class | status | what it adds |
|---|---|---|
| `HttpResponseRedirect` | 302, or 307 | a `"Location"` header; see below |
| `HttpResponsePermanentRedirect` | 301, or 308 | the same |
| `HttpResponseNotModified` | 304 | removes the `Content-Type` header, and refuses any content |
| `HttpResponseBadRequest` | 400 | |
| `HttpResponseForbidden` | 403 | |
| `HttpResponseNotFound` | 404 | |
| `HttpResponseNotAllowed` | 405 | takes the permitted methods as its first argument and lists them in an `"Allow"` header |
| `HttpResponseGone` | 410 | |
| `HttpResponseServerError` | 500 | |

*The subclasses of `HttpResponse` that are named for a status.*

```text recording=http
HttpResponseNotAllowed(["GET", "HEAD"])  ->  405 Method Not Allowed; headers: Content-Type: text/html; charset=utf-8, Allow: GET, HEAD
HttpResponseNotModified()  ->  304 Not Modified; headers: none
HttpResponseNotModified("body")  ->  raises AttributeError: You cannot set content to a 304 (Not Modified) response
```

`Http404` is defined in the same module and is not one of them. It is an exception, raised by a view that wants the site's 404 page and turned into a response by the middleware chain; a view that returns `HttpResponseNotFound` is supplying the page itself ([How an exception becomes a response](../handlers/exceptions.md)).

## Redirects

A redirect is a response whose point is one header. `HttpResponseRedirectBase.__init__` takes the target first, sets it as `"Location"` after escaping it into ASCII, and then makes two checks (`django/http/response.py:HttpResponseRedirectBase.__init__`).

```text recording=http
HttpResponseRedirect("/next/")  ->  302 Found; headers: Content-Type: text/html; charset=utf-8, Location: /next/
HttpResponseRedirect("/next/", preserve_request=True)  ->  307 Temporary Redirect; headers: Content-Type: text/html; charset=utf-8, Location: /next/
HttpResponsePermanentRedirect("/café/?q=é")  ->  301 Moved Permanently; headers: Content-Type: text/html; charset=utf-8, Location: /caf%C3%A9/?q=%C3%A9
HttpResponsePermanentRedirect("/next/", preserve_request=True)  ->  308 Permanent Redirect; headers: Content-Type: text/html; charset=utf-8, Location: /next/
HttpResponseRedirect("javascript:alert(1)")  ->  raises DisallowedRedirect: Unsafe redirect to URL with protocol 'javascript'
HttpResponseRedirect("/" + "x" * 16384)  ->  raises DisallowedRedirect: Unsafe redirect exceeding 16384 characters
```

The scheme of the target, if it has one, must be in the class's `allowed_schemes`: `"http"`, `"https"` or `"ftp"`. This is the check that keeps a redirect built from user input from sending a browser to a URL that begins `"javascript:"`. A target with no scheme passes, whether it is a path on the same site or begins with two slashes and names another host. The `"Location"` value, as escaped, must be no longer than `MAX_URL_REDIRECT_LENGTH`, 16,384 characters, unless the caller passes another maximum, or `None` for no check. Either failure raises `DisallowedRedirect`, a `SuspiciousOperation`, so a view that lets it escape answers with a 400.

Neither check decides whether the target's host is a safe place to send a visitor. That is a separate question with a separate function, `url_has_allowed_host_and_scheme` ([The helpers in `django/utils/http.py`](helpers.md#urls-that-came-from-a-client)). The target is also sent as given: a path stays a path, and is not made into a full URL.

With `preserve_request=True` the two classes use 307 and 308 in place of 302 and 301. A browser may turn a redirected `POST` into a `GET` after the older pair; the newer pair tell it to repeat the request as it was, method and body.

> **Changed in 5.2 and 6.1.** The argument that preserves the request was added in 5.2, and the one that overrides the maximum length in 6.1.

## `JsonResponse`

`JsonResponse` is given data, not content. Its constructor serialises the data with `json.dumps`, using `DjangoJSONEncoder` unless it is given another encoder, a class that also knows dates, times, decimals and UUIDs; it sets the content type to `"application/json"` unless the caller passed one; and it hands the result to `HttpResponse` as the body (`django/http/response.py:JsonResponse.__init__`, `django/core/serializers/json.py:DjangoJSONEncoder`).

```text recording=http
JsonResponse([1, 2])  ->  200 OK; headers: Content-Type: application/json; body b'[1, 2]'
JsonResponse({"a": 1}, safe=False)  ->  200 OK; headers: Content-Type: application/json; body b'{"a": 1}'; warns RemovedInDjango2029Warning: The safe parameter is deprecated.
JsonResponse([1, 2], safe=True)  ->  raises TypeError: In order to allow non-dict objects to be serialized set the safe parameter to False.; warns RemovedInDjango2029Warning: The safe parameter is deprecated.
```

> **Changed in 6.2.** `JsonResponse` used to refuse anything but a dictionary unless it was called with `safe=False`, as a guard against an attack on a JSON array through JavaScript's array prototype, which the release notes say ECMAScript 5 closed. The argument's default is now `None`, which is treated as false, so a list is serialised without comment; passing the argument at all warns with `RemovedInDjango2029Warning`, though `safe=True` still raises for a non-dictionary until the argument is removed.

## Responses that are more than this

`StreamingHttpResponse` and `FileResponse` share the base class and not the body, and have [a section of their own](streaming.md). `TemplateResponse` is an `HttpResponse` whose content is not there yet: it holds a template and a context, and is rendered only after middleware has had the chance to change them; it belongs to [Templates](../templates.md) (`django/template/response.py:SimpleTemplateResponse`).
