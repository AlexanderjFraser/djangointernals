---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The static file view

During development a request for a file can be answered by a view that finds the file under a directory, its `"document_root"`, and sends it as a `FileResponse`. The view is `django.views.static.serve`; `django.conf.urls.static.static` routes to it by default in a development URLconf, and the static files app's own view calls it.

A deployed site ordinarily does not hand out its images and stylesheets through Django. A web server or a content delivery network in front of the application does that, faster and without occupying a Python process. On a developer's machine there is no such server, and something has to answer a browser's request for a file. Django has a view for the purpose.

> **Why.** Its module's docstring says in capitals what the view is not for: its views and functions "are only to be used during development, and SHOULD NOT be used in a production setting" (`django/views/static.py`). The reference gives the reason, that the view "is not hardened for production use" (`docs/ref/views.txt`), and the static files app's documentation says of that app's view, which ends in this one, that it is "grossly inefficient and probably insecure" (`docs/ref/contrib/staticfiles.txt`).

The view is an ordinary function with an ordinary signature: the request, a path, and two options that a URLconf passes as extra arguments, `"document_root"` and `"show_indexes"` (`django/views/static.py:serve`).

## From a path to a file

The path comes from the URL, so it is the client's to choose, and the view begins by not trusting it. `posixpath.normpath` collapses any `..` segments that can be collapsed and any repeated slashes, and leading slashes are stripped. Then `safe_join` joins the result to the document root and checks that the answer is still inside it. A path that would climb out makes it raise `SuspiciousFileOperation`, a `SuspiciousOperation`, which `response_for_exception` answers with a 400 (`django/utils/_os.py:safe_join`). Under `settings.DEBUG`, which is when `django.conf.urls.static.static` routes a prefix to the view at all, that 400 is the debug page that `technical_500_response` makes ([How an exception becomes a response](../handlers/exceptions.md#which-exception-becomes-which-response)) (`django/core/handlers/exception.py:response_for_exception`).

A path that is a directory, unless indexes were asked for, and a path that does not exist are each refused with an `Http404`.

A path that wanders into a directory and out again, and one with a slash in front, are answered as the plain `"masthead.txt"` is; the path that climbs out is refused; and the last call has no document root.

```text recording=views
django.views.static.serve: what it answers
    FILES is a directory that holds masthead.txt, a file named .proofs, and a directory, issues, with one file in it;
    the script has set each file's modification time to 1 January 2026, 12:00:00 UTC, and told Python's mimetypes, which
    the view asks, that .txt is text/plain
      serve(request(), "masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
      ...
      serve(request(), "issues/../masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
      serve(request(), "/masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
      serve(request(), "../views.py", document_root=FILES)  ->  raises SuspiciousFileOperation
      serve(request(), "no-such-file.txt", document_root=FILES)  ->  raises Http404
      serve(request(), "issues", document_root=FILES)  ->  raises Http404: Directory indexes are not allowed here.
      ...
      serve(request(), "masthead.txt")  ->  raises TypeError
      ...
```

Nothing checks for a missing document root: the parameter defaults to `None`, and `safe_join` hands it to `os.path.join`, which raises the `TypeError` (`django/utils/_os.py:safe_join`).

## The response: `FileResponse` and If-Modified-Since

For a file that exists, the view reads its modification time and decides between two answers.

If the request has an If-Modified-Since header, and the file has not changed since the time it names, the answer is an `HttpResponseNotModified` with no body. `was_modified_since` makes the comparison, and is generous about it. A missing header and one that does not parse as an HTTP date both count as modified, so the file is sent. The file's time is cut to whole seconds before it is compared with the header's, which `parse_http_date` returns as whole seconds (`django/views/static.py:was_modified_since`).

The 304 is the answer to a header that names the file's own time; a time one second earlier, and a date that does not parse, each get the file.

```text recording=views
...
serve(request(HTTP_IF_MODIFIED_SINCE="Thu, 01 Jan 2026 12:00:00 GMT"), "masthead.txt", document_root=FILES)  ->  an HttpResponseNotModified, status 304, content ''
serve(request(HTTP_IF_MODIFIED_SINCE="Thu, 01 Jan 2026 11:59:59 GMT"), "masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
serve(request(HTTP_IF_MODIFIED_SINCE="yesterday"), "masthead.txt", document_root=FILES)  ->  a FileResponse, status 200, Content-Type 'text/plain', Last-Modified 'Thu, 01 Jan 2026 12:00:00 GMT'
...
```

When the file is sent, the answer is a `FileResponse` around the open file. The content type is a guess from the file's name, by Python's `mimetypes`, and `"application/octet-stream"` when there is no guess. When the name also implies an encoding, as `.gz` does, the view sets Content-Encoding to match. And it sets Last-Modified from the file's time, which is what lets the browser send the header that earns a 304 next time. The rest is the response's own work: `FileResponse` adds the length and a Content-Disposition header that names the file as inline, and streams the file ([Streaming and file responses](../http/streaming.md#fileresponse)).

That is the whole of the view's support for caching. It has no `"ETag"`, and it sets no Cache-Control.

## The directory index

With `"show_indexes"` true, a path that is a directory is answered with a list of what is in it. `directory_index` looks for a template named `"static/directory_index.html"` or, failing that, `"static/directory_index"` among the project's own, and when there is neither it reads the one in `django/views/templates/` and renders it with an engine made for the occasion. The list leaves out every name that begins with a dot, and marks directories with a slash (`django/views/static.py:directory_index`).

The index of the document root leaves out the file named `".proofs"`, and each index holds `"../"`, the built-in template's own link to the directory above (`django/views/templates/directory_index.html`).

```text recording=views
...
sorted(re.findall('href="([^"]*)"', serve(request(), "issues", document_root=FILES, show_indexes=True).content.decode()))  ->  ['../', '1871-01-07.txt']
sorted(re.findall('href="([^"]*)"', serve(request(), "", document_root=FILES, show_indexes=True).content.decode()))  ->  ['../', 'issues/', 'masthead.txt']
...
```

## Who routes to it

No URL leads to this view unless a project or another part of Django arranges it.

**`static()`** is a helper for a URLconf, in `django/conf/urls/static.py`. Given a prefix and a document root it returns a list holding one pattern, a regular expression that matches the prefix and captures everything after it as the path, with `serve` as the view and the document root as an extra argument. A project adds the list to its `"urlpatterns"`; the docstring's example does so for the files a site's users upload. The helper refuses an empty prefix with `ImproperlyConfigured`. For any other it returns an empty list when `settings.DEBUG` is off, or when the prefix has a host in it, so the same URLconf can be deployed and simply has no such pattern in production (`django/conf/urls/static.py:static`).

Look for the empty list twice, with `settings.DEBUG` off and, with it on, for a prefix that is a URL; and for the one pattern's view and its extra argument.

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

> **Trap.** `static()` decides once, as the URLconf that calls it is imported, which is once in a process ([When a URLconf is imported](../urls/import.md)), and it returns its empty list without a warning. Turning `settings.DEBUG` on afterwards adds no pattern. Django's test runner turns `settings.DEBUG` off for the tests, whatever the settings module says, unless it is run with `--debug-mode`, and its system checks import the root URLconf before the first test runs; so a test that turns it on again with `override_settings` finds no pattern under the prefix (`django/conf/urls/static.py:static`, `django/test/utils.py:setup_test_environment`, `django/test/runner.py:DiscoverRunner.run_tests`).

**The static files app** has a view of its own, `django.contrib.staticfiles.views.serve`, which finds the file with the app's finders and calls this one with the file's directory as the document root (`django/contrib/staticfiles/views.py:serve`). Its runserver puts `StaticFilesHandler` in front of the project's handler, while `settings.DEBUG` is on unless told otherwise, and that handler does the same for the paths under `settings.STATIC_URL`, with no pattern in the URLconf ([Serving static files: `StaticFilesHandler` and the development server](../contrib/serving-static.md)).

**The test framework** uses the view the same way for a live server: its handlers for static and media files call `serve` directly with a directory of their own (`django/test/testcases.py:FSFilesHandler.serve`, [A server in a thread: `LiveServerTestCase`](../testing/live-server.md)).
