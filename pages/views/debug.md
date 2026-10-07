---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The debug pages and `ExceptionReporter`

The code of `django/views/debug.py`: `technical_500_response`, the page shown for an uncaught exception when `settings.DEBUG` is on, and `technical_404_response`, the page for an `Http404`. Behind the first is `ExceptionReporter`, which gathers a traceback, a request and the settings into a report, and `SafeExceptionReporterFilter`, which decides what in the report is replaced by stars. The same two classes write the error email that a production site sends.

A program that has just failed has three readers, and owes each a different account. The developer at a keyboard wants everything: each frame of the traceback with the source around it and the values of its variables, the request that caused it, the settings in force. A stranger using the live site must be told none of it, and gets the plain page of an [error view](errors.md). And the site's administrators are owed something in between, sent somewhere private.

Django serves the first and the third with one mechanism in three parts. A **reporter** collects the facts. A **filter** stands between the reporter and what should not be shown. A template lays the result out, as a page or as text. Which reader gets what is decided by who calls the reporter, and by whether `settings.DEBUG` is on.

## Who asks for a report

The handler asks, when `settings.DEBUG` is on. `response_for_exception` passes any exception it does not recognise to `handle_uncaught_exception`, which returns what `technical_500_response` makes, and it calls the same function directly, with a status of 400, for a `BadRequest` or a `SuspiciousOperation` ([How an exception becomes a response](../handlers/exceptions.md)).

The logging system asks, and under Django's default logging configuration only when `settings.DEBUG` is off. `AdminEmailHandler`, the log handler that mails errors to the site's administrators, makes a reporter for each record it is going to mail and puts the text report in the message, with the HTML report added as an alternative body if it was configured with `include_html` ([Logging](../startup/logging.md#adminemailhandler-error-email-is-a-log-handler)).

The Gazette has a view that fails. This is a request for it with `settings.DEBUG` on:

```python
# gazette/views.py
def missing(request, year):
    password = " ".join(["open", "sesame"])
    shelf = " ".join(["the", "attic"])
    raise LookupError(f"no edition for {year}")
```

```text recording=views
handle_uncaught_exception(request, resolver, exc_info)
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
          SafeExceptionReporterFilter.get_traceback_frame_variables  (the frame of inner)
            SafeExceptionReporterFilter.is_active  ->  False
            -> {'request': ..., 'exc': ..., 'get_response': ...}
          SafeExceptionReporterFilter.get_traceback_frame_variables  (the frame of _get_response)
            SafeExceptionReporterFilter.is_active  ->  False
            -> {'self': ..., 'request': ..., 'response': ..., 'callback': ..., 'callback_args': ..., 'callback_kwargs': ..., 'wrapped_callback': ...}
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
```

## `technical_500_response`

`technical_500_response` is short. It makes a reporter, asks it for one of two renderings, and wraps the result in a response with the status it was given (`django/views/debug.py:technical_500_response`).

The reporter's class is looked up for each call by `get_exception_reporter_class`: an attribute named `"exception_reporter_class"` on the request if there is one, and otherwise the class that `settings.DEFAULT_EXCEPTION_REPORTER` names. So a project can replace the reporter for the whole site, and a middleware can replace it for one request.

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

The function carries two decorators, `csp_override` and `csp_report_only_override`, each with an empty policy. An empty policy means that `ContentSecurityPolicyMiddleware` adds no header, so the debug page is exempt from the site's Content Security Policy. The page has its styles and its script written into it. `technical_404_response` and `default_urlconf` have the same pair of decorators.

## What `ExceptionReporter` gathers

A reporter is made with the request, which may be `None`, and the three values that `sys.exc_info()` returns. `ExceptionReporter.get_traceback_data` turns them into one dictionary, which is the context for both templates (`django/views/debug.py:ExceptionReporter.get_traceback_data`).

**The frames** are the bulk of it. `ExceptionReporter.get_traceback_frames` begins by following the exception back through its causes: an exception raised from another has a `__cause__`, and one raised while another was being handled has a `__context__`, which counts unless it was suppressed. It collects the whole chain, stopping with a warning if the chain loops back on itself, and then reports the frames oldest exception first (`django/views/debug.py:ExceptionReporter.get_traceback_frames`).

In the recording, a function named chained catches a `KeyError` that a function named lookup raised, and raises `LookupError` from it. The first two frames are the `KeyError`'s and have no cause. The last two are the `LookupError`'s, and each carries the `KeyError` as its cause, marked explicit.

```text recording=views
The frames of a report, when one exception was raised from another
    lookup() raises KeyError; chained() calls it, catches the KeyError and raises LookupError from it;
    frames() calls chained(), catches the LookupError, and returns what ExceptionReporter.get_traceback_frames makes of it:
    the third frame is that of frames() itself, where the LookupError was caught
      [(frame["function"], type(frame["exc_cause"]).__name__, bool(frame["exc_cause_explicit"])) for frame in frames()]  ->  [('chained', 'NoneType', False), ('lookup', 'NoneType', False), ('frames', 'KeyError', True), ('chained', 'KeyError', True)]
      [frame["type"] for frame in frames()]  ->  ['user', 'user', 'user', 'user']
      sorted(frames()[0])  ->  ['colno', 'context_line', 'exc_cause', 'exc_cause_explicit', 'filename', 'function', 'id', 'lineno', 'post_context', 'pre_context', 'pre_context_lineno', 'tb', 'tb_area_colno', 'type', 'vars']
```

The last line lists what one frame's dictionary holds. Besides the file, the function and the line, there is the source around the line, up to seven lines before and six after, read through the module's loader when that can supply source and from the file otherwise. There is the line of carets that goes under the failing expression, made from the columns the expression occupies. There are the frame's local variables, each passed through the filter. And there is a type, `"django"` for a frame whose module's name begins with `django.` and `"user"` for any other, which the HTML page puts on the frame as a class, so that the two can be styled apart (`django/views/debug.py:ExceptionReporter.get_exception_traceback_frames`).

`get_traceback_data` then formats each variable for display and cuts it short at 4096 characters. A frame is left out entirely if it has a local variable named `"__traceback_hide__"` with a true value.

**The request** contributes its method and address, its `GET` and `FILES` as they are, and three things that come by way of the filter: `POST`, the cookies and `META`. The address is built without the usual validation of the `"Host"` header: a request with a host the site does not allow would raise if asked for its host in the ordinary way ([Headers, host and scheme](../http/headers.md)) (`django/views/debug.py:ExceptionReporter._get_raw_insecure_uri`). The user is included as text, inside a `try`: a comment notes that asking for the user can itself fail, when the database is the thing that is down.

**The settings** come from the filter as well, and beside them the Python and Django versions, the path, and the time.

**The view** is named by `get_caller`, from the request's `ResolverMatch` when there is one and by resolving the path again when there is not ([What the handler asks of a view](callable.md#how-a-view-is-named)).

Some exceptions get sections of their own. For a `TemplateDoesNotExist` the report lists every place each engine looked. For an exception raised while a template was being compiled or rendered, the template engine, when its `"debug"` option is on, has attached the template's own source lines to the exception, and the report shows the failing line of the template above the Python traceback ([Templates](../templates.md)). And for a `UnicodeError` the HTML report adds a hint, the text around the place that could not be encoded or decoded.

## Two templates, read from disk each time

`ExceptionReporter.get_traceback_html` and `ExceptionReporter.get_traceback_text` render the dictionary with `django/views/templates/technical_500.html` and `django/views/templates/technical_500.txt`. Neither goes through the project's template system. The reporter opens the file itself and gives the text to `DEBUG_ENGINE`, an `Engine` made in this module for nothing else. The comment on it says why: the error templates must render whatever the project's `TEMPLATES` setting says, and are read directly from the filesystem so that the error handler works even if the template loader is broken (`django/views/debug.py:DEBUG_ENGINE`).

The two renderings are not the same report in two formats. The HTML one shows every frame's local variables. The text one has no variables in it at all. The recording looks for the password's value in each of the four reports of the Gazette's failing view, and for the other variable's in the text report made as for the email:

```text recording=views
views.missing has two local variables whose values are 'open sesame' (password) and 'the attic' (shelf), neither written out
whole in its source, and raises LookupError;
guarded is sensitive_variables("password")(views.missing), and all_guarded is sensitive_variables()(views.missing);
views.till has one local variable, posted = request.POST, and raises LookupError;
post_guarded is sensitive_post_parameters("pin")(views.till);
html(view, DEBUG) and text(view, DEBUG) are the two reports an ExceptionReporter writes for what the view raised, with the
setting DEBUG as given: with DEBUG True the reporter is made as for the debug page, and with DEBUG False as for the email
to the site's administrators (is_email=True), which by default carries the text report alone. The text report shows no
frame's variables at all, whatever the setting. The third argument of html and text is what was posted.
  "open sesame" in html(views.missing, True)  ->  True
  "open sesame" in text(views.missing, True)  ->  False
  "open sesame" in html(views.missing, False)  ->  True
  "open sesame" in text(views.missing, False)  ->  False
  "the attic" in text(views.missing, False)  ->  False
```

Both renderings carry the request's data and the settings. Since the text report is what `AdminEmailHandler` sends unless asked for more, the default error email has a traceback, the request and the settings in it, and no variable from any frame. A reporter made for an email also leaves out of the HTML the source lines around each frame, and the page's script.

A reporter subclass changes the templates by overriding two properties, `ExceptionReporter.html_template_path` and `ExceptionReporter.text_template_path`.

## The filter: `SafeExceptionReporterFilter`

The settings, the request's `META`, cookies and `POST`, and every frame's variables pass through one object before they reach a template. A reporter gets its filter from `get_exception_reporter_filter`: an attribute named `"exception_reporter_filter"` on the request, or else the site's default, an instance of the class named by `settings.DEFAULT_EXCEPTION_REPORTER_FILTER`, made once for the process and kept (`django/views/debug.py:get_default_exception_reporter_filter`).

The filter hides by name, which it does always, and by decoration, which it does only in production.

**By name, always.** `SafeExceptionReporterFilter.cleanse_setting` takes a key and a value, and returns a row of stars in place of the value when the key looks sensitive. The test is a regular expression, `SafeExceptionReporterFilter.hidden_settings`, searched for anywhere in the key without regard to case: `"API"`, `"AUTH"`, `"TOKEN"`, `"KEY"`, `"SECRET"`, `"PASS"`, `"SIGNATURE"` or `"HTTP_COOKIE"`. The name of the session cookie is treated the same. A dictionary is cleansed key by key, to any depth, and the items of a list or a tuple are gone through for dictionaries inside them (`django/views/debug.py:SafeExceptionReporterFilter.cleanse_setting`).

```text recording=views
filter is a SafeExceptionReporterFilter(), and request(...) a request with the headers given
filter.cleansed_substitute  ->  '********************'
filter.cleanse_setting("SECRET_KEY", "recording")  ->  '********************'
filter.cleanse_setting("TIME_ZONE", "UTC")  ->  'UTC'
filter.cleanse_setting("PASSENGERS", 12)  ->  '********************'
filter.cleanse_setting("API_URL", "https://api.example/")  ->  '********************'
filter.cleanse_setting("DATABASES", {"default": {"NAME": "gazette", "PASSWORD": "s3cret"}})  ->  {'default': {'NAME': 'gazette', 'PASSWORD': '********************'}}
filter.cleanse_setting("ADMINS", [{"email": "editor@gazette.example", "token": "t0ken"}])  ->  [{'email': 'editor@gazette.example', 'token': '********************'}]
filter.cleanse_setting("LOGIN_URL", len)  ->  <built-in function len>
type(filter.cleanse_setting("LOGIN_URL", len)).__name__  ->  'CallableSettingWrapper'
settings.SESSION_COOKIE_NAME  ->  'sessionid'
filter.cleanse_setting("sessionid", "abc123")  ->  '********************'
filter.get_safe_request_meta(request(HTTP_COOKIE="sessionid=abc123", HTTP_X_API_KEY="k3y"))["HTTP_COOKIE"]  ->  '********************'
filter.get_safe_request_meta(request(HTTP_COOKIE="sessionid=abc123", HTTP_X_API_KEY="k3y"))["HTTP_X_API_KEY"]  ->  '********************'
filter.get_safe_request_meta(request(HTTP_COOKIE="sessionid=abc123", HTTP_X_API_KEY="k3y"))["HTTP_HOST"]  ->  'gazette.example'
filter.get_safe_cookies(request(HTTP_COOKIE="sessionid=abc123; theme=dark"))  ->  {'sessionid': '********************', 'theme': 'dark'}
```

The match is on a fragment of the name, so it errs on the side of hiding: a setting called `"PASSENGERS"` is starred for the four letters it begins with. The same method is applied to every setting, to every entry of the request's `META`, where it catches the whole `"Cookie"` header and any header with a key or a token in its name, and to each cookie by its name. It runs whatever `settings.DEBUG` is: the secret key is starred on a developer's own debug page.

A setting whose value can be called is not left as it is. It is wrapped in a `CallableSettingWrapper`, an object whose only behaviour is to have the same `repr`. The class's docstring gives two reasons: so that the debug page does not call the setting, as a template does with a callable it is asked to print, and so that a callable that forbids setting attributes does not break the page.

**By decoration, in production.** The other kind hides what a developer has marked: the local variables named by `sensitive_variables` and the posted fields named by `sensitive_post_parameters`. It hides them only when `SafeExceptionReporterFilter.is_active` returns true, which is when `settings.DEBUG` is `False`. The method's docstring is blunt about the other case: if `settings.DEBUG` is on, the site is not safe anyway.

For the recording the Gazette's failing view is decorated in the two ways the notes above describe, and a second view, which keeps the posted data in a local variable, is decorated with `sensitive_post_parameters`:

```python
# gazette/views.py
def till(request, year):
    posted = request.POST
    raise LookupError("the till is shut")
```

```text recording=views
"open sesame" in html(guarded, False)  ->  False
"the attic" in html(guarded, False)  ->  True
"open sesame" in html(guarded, True)  ->  True
"the attic" in html(all_guarded, False)  ->  False
"fourteen-ninety-two" in text(views.till, False, {"pin": "fourteen-ninety-two", "note": "urgent"})  ->  True
"fourteen-ninety-two" in html(views.till, False, {"pin": "fourteen-ninety-two", "note": "urgent"})  ->  True
"fourteen-ninety-two" in text(post_guarded, False, {"pin": "fourteen-ninety-two", "note": "urgent"})  ->  False
"fourteen-ninety-two" in html(post_guarded, False, {"pin": "fourteen-ninety-two", "note": "urgent"})  ->  False
"urgent" in text(post_guarded, False, {"pin": "fourteen-ninety-two", "note": "urgent"})  ->  True
"fourteen-ninety-two" in text(post_guarded, True, {"pin": "fourteen-ninety-two", "note": "urgent"})  ->  True
"SECRET_KEY = '********************'" in text(views.missing, True)  ->  True
```

The marks are honoured in the reports of a production site. With `settings.DEBUG` on, the password is on the page although the view was decorated.

## `sensitive_variables` and `sensitive_post_parameters`

The two decorators only leave notes: one on the request, where the filter reads it, and one that the filter has to find from a traceback.

`sensitive_post_parameters` is the simpler. Its wrapper sets an attribute on the request naming the fields, or the word `"__ALL__"`, each time the view is called. `SafeExceptionReporterFilter.get_post_parameters` reads the attribute and returns a copy of `POST` with those values starred. A second method does the same for any `MultiValueDict` among a frame's local variables, which is how the view above was cleansed of the request's `POST` under a local name. Its docstring names the case it was written for: an exception raised by a lookup of a missing key in `POST`, whose frame holds the whole of it (`django/views/debug.py:SafeExceptionReporterFilter.get_cleansed_multivaluedict`).

`sensitive_variables` is about a function's locals, and the filter is handed frames, not functions. The decorator is found on the stack: its wrapper is a function with a fixed, distinctive name, and each time it is called it stores the names on itself and calls the function. When the filter is given a frame, it walks from that frame up through its callers looking for a frame of that name, and reads the names from the function object in that frame's locals (`django/views/debug.py:SafeExceptionReporterFilter.get_traceback_frame_variables`).

Because the walk goes up through the callers, the names cover more than the decorated function. They apply to every frame beneath the wrapper on the stack, down to the next decorated function, whose own names take over from there. And one thing is starred whatever `settings.DEBUG` is: in the wrapper's own frame, the arguments it was called with.

A coroutine cannot be found that way. The comment in the filter says that coroutines do not have a proper `"f_back"`, the link from a frame to its caller. So for a coroutine function the decorator makes no wrapper. It records the names in a module-level dictionary, keyed by the file and first line of the function, and returns the function unchanged; the filter looks a coroutine's frame up in the dictionary by the same key (`django/views/decorators/debug.py:sensitive_variables`).

Django uses both on its own code. `authenticate` in `django/contrib/auth/__init__.py` is decorated with `sensitive_variables("credentials")`, and `LoginView` has `sensitive_post_parameters()` among the decorators on its `dispatch`, which hides every posted field.

## The 404 page

`technical_404_response` answers an `Http404` when `settings.DEBUG` is on. It makes no reporter: it shows what the resolver tried (`django/views/debug.py:technical_404_response`).

```text recording=views
GET /no-such-page/ with DEBUG = True
    BaseHandler._get_response  raises Resolver404
    response_for_exception(request, Resolver404)
      technical_404_response(request, exception)
        Engine.from_string(the text of django/views/templates/technical_404.html)
        SafeExceptionReporterFilter.get_safe_settings
        get_caller  ->  ''
        -> an HttpResponseNotFound, status 404
      -> an HttpResponseNotFound, status 404
    log, WARNING to django.request: Not Found: /no-such-page/
    start_response("404 Not Found", headers), with Content-Type: text/html; charset=utf-8
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
        -> an HttpResponse, status 200
      -> an HttpResponse, status 200
    start_response("200 OK", headers), with Content-Type: text/html; charset=utf-8
```
