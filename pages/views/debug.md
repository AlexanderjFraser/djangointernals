---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The debug pages and `ExceptionReporter`

The debug page is the report Django shows a developer for an uncaught exception while `settings.DEBUG` is on, and the same report, as text, goes into the error email a site sends its administrators while the setting is off. `technical_500_response` and `AdminEmailHandler` each make an `ExceptionReporter` for it, and `technical_404_response` makes the page for an `Http404`.

A program that has just failed has three readers, and owes each a different account. The developer at a keyboard wants everything: each frame of the traceback with the source around it and the values of its variables, the request that caused it, the settings in force. A stranger using the live site must be told none of it, and gets the plain page of an error view ([The error views](errors.md)). And the site's administrators are owed something in between, sent somewhere private.

Django serves the first and the third with one mechanism in three parts. A **reporter** collects the facts. A **filter** stands between the reporter and what should not be shown ([What an error report hides](report-filter.md)). A template lays the result out, as a page or as text. Which reader gets what is decided by who calls the reporter, and by whether `settings.DEBUG` is on.

The figure sets the callers side by side, and below them what they share: by default the same class of reporter, made with one flag set otherwise, the filter, and the dictionary both templates render.

```text figure=one-reporter
with settings.DEBUG on                                  with settings.DEBUG off
technical_500_response                                  AdminEmailHandler.emit
  called by the handler, for the response                called by the logging, for a record of ERROR or above
  ExceptionReporter(request, ..., is_email=False)        ExceptionReporter(request, ..., is_email=True)

                        ExceptionReporter
                          made with the request, and the exception's type, value and traceback
                          SafeExceptionReporterFilter, between it and the settings,
                            the request's META, cookies and POST, and each frame's variables
                          ExceptionReporter.get_traceback_data  ->  a dictionary

technical_500.html, rendered by get_traceback_html      technical_500.txt, rendered by get_traceback_text
  the page, for a client that prefers HTML;              the page, for any other client;
  the mail's HTML alternative, with include_html          in the mail; no frame's variables
```

*Read from the top: the two callers, each making an `ExceptionReporter` of its own, the second as for an email; the class they share, with the filter between it and what it reads; and at the foot the two templates that render its dictionary, each with the reports it makes.*

## Who asks for a report

The handler asks, when `settings.DEBUG` is on. `response_for_exception` passes any exception it does not recognise to `handle_uncaught_exception`, which returns what `technical_500_response` makes unless `settings.DEBUG_PROPAGATE_EXCEPTIONS` is on, and it calls the same function directly, with a status of 400, for a `BadRequest` or a `SuspiciousOperation` ([How an exception becomes a response](../handlers/exceptions.md)) (`django/core/handlers/exception.py:response_for_exception`).

The logging system asks, and under Django's default logging configuration only when `settings.DEBUG` is off: the configuration gives the logger `"django"` an `AdminEmailHandler` for records of level ERROR and above, behind a filter that passes them only while the setting is off ([Logging](../startup/logging.md#adminemailhandler-error-email-is-a-log-handler)) (`django/utils/log.py:DEFAULT_LOGGING`). For each record it mails, the handler makes a reporter as for an email, with `is_email=True`, puts the text report in the message, and adds the HTML report as an alternative body if it was made with `include_html=True` (`django/utils/log.py:AdminEmailHandler.emit`).

With `settings.DEBUG` off, `ADMINS` set, and `MAILERS`, the setting that names a project's mail backends, set to one that keeps each message in memory, a request for the Gazette's failing view shows the mail made inside the logging call (`django/core/mail/handler.py:MailersHandler.create_connection`, `django/core/mail/backends/locmem.py:EmailBackend`). Once the error view has made the 500, `log_response` gives the record, and `AdminEmailHandler.emit`, called with that record, makes the reporter, asks it for the text report and sends the mail before `log_response` returns.

```text recording=views
GET /editions/1790/ with DEBUG = False, and ADMINS and MAILERS set for this block: the error email
...
      handle_uncaught_exception(request, resolver, exc_info)  ->  an HttpResponseServerError, status 500
      log_response
        log, ERROR to django.request: Internal Server Error: /editions/1790/
        AdminEmailHandler.emit
          ExceptionReporter.__init__(request, LookupError, ..., is_email=True)
          ExceptionReporter.get_traceback_text
          AdminEmailHandler.send_mail
            mail_admins
              EmailBackend.send_messages  (django.core.mail.backends.locmem)
              ...
```

## `technical_500_response`

`technical_500_response` is short. It makes a reporter, asks it for one of two renderings, and wraps the result in a response with the status it was given (`django/views/debug.py:technical_500_response`).

The Gazette's view of an edition sets two local variables and then raises:

```python
# gazette/views.py
def missing(request, year):
    password = " ".join(["open", "sesame"])
    shelf = " ".join(["the", "attic"])
    raise LookupError(f"no edition for {year}")
```

Requested with `settings.DEBUG` on by a client that asks for HTML, it is answered by `technical_500_response`, which makes the reporter, and the reporter its filter, before it asks the request which rendering it prefers. Only then is the template read and the dictionary built, each frame's variables passing through a filter that is not active, as it never is while `settings.DEBUG` is on ([What an error report hides](report-filter.md#the-filter-safeexceptionreporterfilter)).

```text recording=views
GET /editions/1790/ with DEBUG = True and Accept: text/html
...
        technical_500_response(request, LookupError, ..., status_code=500)
          get_exception_reporter_class  ->  the class ExceptionReporter
          ExceptionReporter.__init__(request, LookupError, ..., is_email=False)
            get_exception_reporter_filter
              get_default_exception_reporter_filter  ->  a SafeExceptionReporterFilter
              -> a SafeExceptionReporterFilter
          HttpRequest.get_preferred_type(['text/html', 'text/plain'])  ->  'text/html'
          ExceptionReporter.get_traceback_html
            Engine.from_string(the text of django/views/templates/technical_500.html)
            ExceptionReporter.get_traceback_data
              ExceptionReporter.get_traceback_frames
                ...
                SafeExceptionReporterFilter.get_traceback_frame_variables  (the frame of missing)
                  SafeExceptionReporterFilter.is_active  ->  False
                  -> {'request': ..., 'year': ..., 'password': ..., 'shelf': ...}
              SafeExceptionReporterFilter.get_safe_request_meta
              SafeExceptionReporterFilter.get_safe_cookies
              SafeExceptionReporterFilter.get_post_parameters
                SafeExceptionReporterFilter.is_active  ->  False
              SafeExceptionReporterFilter.get_safe_settings
              get_caller  ->  'gazette.views.missing'
          -> an HttpResponse, status 500, Content-Type 'text/html'
          ...
```

The reporter's class is looked up for each call by `get_exception_reporter_class`: an attribute named `"exception_reporter_class"` on the request if there is one, and otherwise the class that `settings.DEFAULT_EXCEPTION_REPORTER` names. So a project can replace the reporter for the whole site, and a middleware can replace it for one request's debug page (`django/views/debug.py:get_exception_reporter_class`).

The rendering depends on the client. The function asks the request which of `"text/html"` and `"text/plain"` it prefers, and sends the HTML page only when the answer is the first. A browser gets the page, as does a client that names no preference. A client that asked for JSON or for plain text gets the text rendering.

```text recording=views
technical_500_response: HTML or plain text, by the request's Accept header
    page_type(...) is the Content-Type of what technical_500_response returns for a request with the headers given
      page_type()  ->  'text/html'
      page_type(HTTP_ACCEPT="*/*")  ->  'text/html'
      page_type(HTTP_ACCEPT="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")  ->  'text/html'
      page_type(HTTP_ACCEPT="text/plain")  ->  'text/plain; charset=utf-8'
      page_type(HTTP_ACCEPT="application/json")  ->  'text/plain; charset=utf-8'
      page_type(HTTP_ACCEPT="text/plain, text/html")  ->  'text/plain; charset=utf-8'
```

The function carries two decorators, `csp_override` and `csp_report_only_override`, each with an empty policy. An empty policy means that `ContentSecurityPolicyMiddleware` adds no header, so the debug page is exempt from the site's Content Security Policy (`django/middleware/csp.py:ContentSecurityPolicyMiddleware.process_response`). The page has its styles and its script written into it. `technical_404_response` and `default_urlconf` have the same pair of decorators.

## What `ExceptionReporter` gathers

A reporter is made with the request, which may be `None`, and the three values that `sys.exc_info()` returns, the exception's type, value and traceback. `ExceptionReporter.get_traceback_data` turns them into one dictionary, which is the context for both templates (`django/views/debug.py:ExceptionReporter.get_traceback_data`).

**The frames** are the bulk of it. `ExceptionReporter.get_traceback_frames` begins by following the exception back through its causes: an exception raised from another has a `__cause__`, and one raised while another was being handled has a `__context__`, which counts unless it was suppressed. It collects the whole chain, stopping with a warning if the chain loops back on itself, and then reports the frames oldest exception first (`django/views/debug.py:ExceptionReporter.get_traceback_frames`).

Given a `LookupError` raised from a `KeyError`, the reporter lists the `KeyError`'s two frames first, with no cause, and then the `LookupError`'s, each carrying the `KeyError` as its cause, marked explicit:

```text recording=views
The frames of a report, when one exception was raised from another
    lookup() raises KeyError; chained() calls it, catches the KeyError and raises LookupError from it;
    frames() calls chained(), catches the LookupError, and returns what ExceptionReporter.get_traceback_frames makes of it:
    the third frame is that of frames() itself, where the LookupError was caught
      [(frame["function"], type(frame["exc_cause"]).__name__, bool(frame["exc_cause_explicit"])) for frame in frames()]  ->  [('chained', 'NoneType', False), ('lookup', 'NoneType', False), ('frames', 'KeyError', True), ('chained', 'KeyError', True)]
      [frame["type"] for frame in frames()]  ->  ['user', 'user', 'user', 'user']
      ...
```

Besides the file, the function and the line, one frame's dictionary holds the source around the line, up to seven lines before and six after, read through the module's loader when that can supply source and from the file otherwise. There is the line of carets that goes under the failing expression, made from the columns the expression occupies. There are the frame's local variables, each passed through the filter. And there is a type, `"django"` for a frame whose module's name begins with `django.` and `"user"` for any other, which the HTML page puts on the frame as a class, so that the two can be styled apart (`django/views/debug.py:ExceptionReporter.get_exception_traceback_frames`). A frame with a true local variable named `"__traceback_hide__"` is left out, a convention a few libraries use to hide their internal frames.

**The request** contributes its method and address, its `GET` and `FILES` as they are, and three things that come by way of the filter: `POST`, the cookies and `META`. The address is built without the usual validation of the `"Host"` header: a request with a host the site does not allow would raise if asked for its host in the ordinary way ([Headers, host and scheme](../http/headers.md)) (`django/views/debug.py:ExceptionReporter._get_raw_insecure_uri`). The user is included as text, inside a `try`, since asking for the user can itself fail when the database is the thing that is down (`django/views/debug.py:ExceptionReporter.get_traceback_data`).

**The settings** come from the filter as well, and beside them the Python and Django versions, the path, and the time.

**The view** is named by `get_caller`, from the request's `ResolverMatch` when there is one and by resolving the path when there is not ([What the handler asks of a view](callable.md#how-a-view-is-named)).

Some exceptions get sections of their own. For a `TemplateDoesNotExist` the report lists what each engine says it tried. For an exception raised while a template was being compiled or rendered, the template engine, when its `"debug"` option is on, has attached the template's own source lines to the exception, and the report shows the failing line of the template above the Python traceback ([Template errors and debug information](../templates/debugging.md)). And for a `UnicodeEncodeError` or a `UnicodeDecodeError` the HTML report adds a hint, the text around the place that could not be encoded or decoded.

## The two templates and `DEBUG_ENGINE`

`ExceptionReporter.get_traceback_html` and `ExceptionReporter.get_traceback_text` render the dictionary with `django/views/templates/technical_500.html` and `django/views/templates/technical_500.txt`. Neither goes through the project's template system. At each call the reporter opens the file itself and gives the text to `DEBUG_ENGINE`, an `Engine` made in this module for nothing else (`django/views/debug.py:ExceptionReporter.get_traceback_html`).

> **Why.** The error templates have an engine of their own so that they render however the project has set `TEMPLATES`, and they are read from the filesystem directly, in the words of the comment above `DEBUG_ENGINE`, "so that the error handler works even if the template loader is broken" (`django/views/debug.py:DEBUG_ENGINE`).

Only the HTML rendering shows the frames' local variables; the text one has none ([What an error report hides](report-filter.md#the-text-report-and-the-error-email)). A reporter made for an email also leaves out of the HTML the source lines around each frame, and the page's script (`django/views/templates/technical_500.html`).

A reporter subclass changes the templates by overriding two properties, `ExceptionReporter.html_template_path` and `ExceptionReporter.text_template_path`.

## The 404 page: `technical_404_response`

`technical_404_response` answers an `Http404` when `settings.DEBUG` is on. It makes no reporter: it shows what the resolver tried (`django/views/debug.py:technical_404_response`).

For a path the Gazette does not route, the template is read as the reporter's are, and the settings come from the site's default filter, but no `ExceptionReporter` is made:

```text recording=views
GET /no-such-page/ with DEBUG = True
    BaseHandler._get_response  raises Resolver404
    response_for_exception(request, Resolver404)
      technical_404_response(request, exception)
        Engine.from_string(the text of django/views/templates/technical_404.html)
        SafeExceptionReporterFilter.get_safe_settings
        get_caller  ->  ''
        -> an HttpResponseNotFound, status 404
        ...
```

The list of patterns comes out of the exception when the resolver raised it, and from the request's `ResolverMatch` when a view raised `Http404` after the path had matched. The page words the two cases differently: the path didn't match any of the patterns, or it matched the last one shown ([Resolving a path](../urls/resolving.md)).

One case is not a 404 at all. When the URLconf has no patterns, whatever the path, or when the request is for the root and the only pattern tried is the admin's, the function returns `default_urlconf` in its place: the page that congratulates a new project on being installed, with a status of 200.

```text recording=views
GET / with DEBUG = True and a URLconf that has no patterns
    BaseHandler._get_response  raises Resolver404
    response_for_exception(request, Resolver404)
      technical_404_response(request, exception)
        default_urlconf(request)
          Engine.from_string(the text of django/views/templates/default_urlconf.html)
          -> an HttpResponse, status 200
          ...
```
