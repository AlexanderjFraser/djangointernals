---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The static file view

`django.views.static.serve` answers a request with a file from a directory. It is the view behind `django.conf.urls.static.static` in a development URLconf and behind the static files app's own view. This section follows it from a path to a file, says what it refuses, and names the callers that route to it.

A deployed site does not hand out its images and stylesheets through Django. A web server or a content delivery network in front of the application does that, faster and without occupying a Python process. On a developer's machine there is no such server, and something has to answer a browser's request for a file. Django has one view for the purpose, and its module's docstring says in capitals what it is not for: it should not be used in a production setting (`django/views/static.py`).

The view is an ordinary function with an ordinary signature: the request, a path, and two settings that a URLconf passes as extra arguments, `"document_root"` and `"show_indexes"` (`django/views/static.py:serve`).

## From a path to a file

The path comes from the URL, so it is the client's to choose, and the first two lines of the view are about not trusting it. `posixpath.normpath` collapses any `..` segments that can be collapsed and any repeated slashes, and leading slashes are stripped. Then `safe_join` joins the result to the document root and checks that the answer is still inside it. A path that would climb out raises `SuspiciousFileOperation`, which the handler answers with a 400 ([How an exception becomes a response](../handlers/exceptions.md#which-exception-becomes-which-response)) (`django/utils/_os.py:safe_join`).

A path that is a directory, unless indexes were asked for, and a path that does not exist are each refused with an `Http404`.

```text recording=views
FILES is a directory that holds masthead.txt, a file named .proofs, and a directory, issues, with one file in it;
the script has set each file's modification time to 1 January 2026, 12:00:00 UTC, and told Python's mimetypes, which
the view asks, that .txt is text/plain
  serve(request(), "masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
  b"".join(serve(request(), "masthead.txt", document_root=FILES))  ->  b'THE GAZETTE\n'
  serve(request(HTTP_IF_MODIFIED_SINCE="Thu, 01 Jan 2026 12:00:00 GMT"), "masthead.txt", document_root=FILES)  ->  an HttpResponseNotModified, status 304, content ''
  serve(request(HTTP_IF_MODIFIED_SINCE="Thu, 01 Jan 2026 11:59:59 GMT"), "masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
  serve(request(HTTP_IF_MODIFIED_SINCE="yesterday"), "masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
  serve(request(), "issues/1871-01-07.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
  serve(request(), "issues/../masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
  serve(request(), "/masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
  serve(request(), "../views.py", document_root=FILES)  ->  raises SuspiciousFileOperation
  serve(request(), "no-such-file.txt", document_root=FILES)  ->  raises Http404
  serve(request(), "issues", document_root=FILES)  ->  raises Http404: Directory indexes are not allowed here.
  serve(request(), "issues", document_root=FILES, show_indexes=True).status_code  ->  200
  sorted(re.findall('href="([^"]*)"', serve(request(), "issues", document_root=FILES, show_indexes=True).content.decode()))  ->  ['../', '1871-01-07.txt']
  sorted(re.findall('href="([^"]*)"', serve(request(), "", document_root=FILES, show_indexes=True).content.decode()))  ->  ['../', 'issues/', 'masthead.txt']
  serve(request(), "masthead.txt")  ->  raises TypeError
```

The two lines above the refused `"../views.py"` are the normalising at work: a path that wanders into a directory and out again, and one with a slash in front, both end at the same file. The last line is the view called with no document root. Nothing checks for that, and the failure is a `TypeError` from the join.

## The response

For a file that exists, the view reads its modification time and decides between two answers.

If the request has an `If-Modified-Since` header, and the file has not changed since the time it names, the answer is an `HttpResponseNotModified` with no body. `was_modified_since` makes the comparison, and is generous about it. A missing header and one that does not parse as an HTTP date both count as modified, so the file is sent. The file's time is cut to whole seconds before it is compared with the header's, which `parse_http_date` returns as whole seconds (`django/views/static.py:was_modified_since`).

Otherwise the answer is a `FileResponse` around the open file. The content type is a guess from the file's name, by Python's `mimetypes`, and `"application/octet-stream"` when there is no guess. When the name also implies an encoding, as `.gz` does, the view sets `Content-Encoding` to match. And it sets `Last-Modified` from the file's time, which is what lets the browser send the header that earns a 304 next time. The rest is the response's own work: `FileResponse` adds the length and a `Content-Disposition` header that names the file as inline, and streams the file ([Streaming and file responses](../http/streaming.md#fileresponse)).

That is the whole of the view's support for caching. It has no `"ETag"`, and it sets no `Cache-Control`.

## The directory index

With `"show_indexes"` true, a path that is a directory is answered with a list of what is in it. `directory_index` looks for a template named `"static/directory_index.html"` or, failing that, `"static/directory_index"` among the project's own, and when there is neither it reads the one in `django/views/templates/` and renders it with an engine made for the occasion. The list leaves out every name that begins with a dot, and marks directories with a slash (`django/views/static.py:directory_index`).

The recording's directory holds a file named `.proofs`, which appears in neither index.

## Who routes to it

No URL leads to this view unless a project or another part of Django arranges it.

**`static()`** is a helper for a URLconf, in `django/conf/urls/static.py`. Given a prefix and a document root it returns a list holding one pattern, a regular expression that matches the prefix and captures everything after it as the path, with `serve` as the view and the document root as an extra argument. A project adds the list to its `"urlpatterns"`; the docstring's example does so for the files a site's users upload. The helper refuses an empty prefix with `ImproperlyConfigured`. For any other it returns an empty list when `settings.DEBUG` is off, or when the prefix has a host in it, so the same URLconf can be deployed and simply has no such pattern in production (`django/conf/urls/static.py:static`).

```text recording=views
static(): the pattern that routes a prefix to the view, made only when DEBUG is true
    static("/media/", document_root=FILES)  ->  []
    static("", document_root=FILES)  ->  raises ImproperlyConfigured
    with DEBUG = True
      static("/media/", document_root=FILES)  ->  [<URLPattern '^media/(?P<path>.*)$'>]
      static("/media/", document_root=FILES)[0].callback is serve  ->  True
      static("/media/", document_root=FILES)[0].default_args == {"document_root": FILES}  ->  True
      static("https://cdn.example/media/", document_root=FILES)  ->  []
```

The helper reads `settings.DEBUG` once, when it is called, which is when the URLconf is imported.

**The static files app** has a view of its own, `django.contrib.staticfiles.views.serve`, which is a front for this one. It refuses with an `Http404` unless `settings.DEBUG` is on or it was called with `"insecure"` true, asks the app's finders where the file is, and then calls `django.views.static.serve` with the directory of the file they found as the document root and the file's name as the path (`django/contrib/staticfiles/views.py:serve`). The static files app's runserver reaches it without any pattern in the URLconf. Unless it was told not to serve static files, and when `settings.DEBUG` is on or it was told to serve them regardless, it puts `StaticFilesHandler` in front of the project's handler, and that answers the paths under `settings.STATIC_URL`, when the setting names no host, before the project's handler sees them ([The development server](../commands/runserver.md#which-application-it-serves), [Content types, static files and the other contrib apps](../contrib.md)).

**The test framework** uses the view the same way for a live server: its handlers for static and media files call `serve` directly with a directory of their own (`django/test/testcases.py:FSFilesHandler.serve`, [The test framework](../testing.md)).
