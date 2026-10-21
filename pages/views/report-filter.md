---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What an error report hides

An error report, the debug page or the administrators' email, replaces with stars the settings, the request's `META` entries and the cookies whose names look like a secret's, and, in production, what a developer has marked as one. The filter that does it is ordinarily the class `settings.DEFAULT_EXCEPTION_REPORTER_FILTER` names, `SafeExceptionReporterFilter` by default, and the marks are left by the decorators `sensitive_variables` and `sensitive_post_parameters`.

A report is gathered by an `ExceptionReporter`, for the debug page that `technical_500_response` returns while `settings.DEBUG` is on and for the email that `AdminEmailHandler` sends ([The debug pages and `ExceptionReporter`](debug.md)). The settings, the request's `META`, cookies and `POST`, and every frame's local variables pass through one object, the reporter's filter, before they reach a template.

The filter hides by name, which it does always, and by mark ([View decorators](decorators.md#marks)), which it does only in production: the marks are the names a developer wants hidden, recorded by two decorators for the filter to find. Each part of a report comes to this, with a last column for the text report, which has no frame's variables at all ([The text report and the error email](#the-text-report-and-the-error-email)):

| in a report | with `settings.DEBUG` on | with `settings.DEBUG` off | in the text report |
|---|---|---|---|
| a setting whose name looks like a secret's | stars | stars | yes |
| an entry of the request's `META` whose name looks like a secret's, the `"Cookie"` header's among them | stars | stars | yes |
| a cookie whose name looks like a secret's, and the session cookie | stars | stars | yes |
| a posted field named by `sensitive_post_parameters` | shown | stars | yes |
| the request's `GET` and `FILES` | shown | shown | yes |
| a frame's variable named by `sensitive_variables`, or every variable for `sensitive_variables()` | shown | stars | no |
| a field named by `sensitive_post_parameters`, in the posted data or another `MultiValueDict` a frame holds in a local variable | shown | stars | no |
| the arguments of a function `sensitive_variables` decorates, where the decorator's wrapper holds them | stars | stars | no |
| any other variable of a frame | shown | shown | no |

*What the default filter does to each part of a report: stars in place of the value, or the value shown; in the last column, whether the text report, the error email's body, has that part at all.*

## The filter: `SafeExceptionReporterFilter`

A reporter gets its filter from `get_exception_reporter_filter`: an attribute named `"exception_reporter_filter"` on the request, or else the site's default, an instance of the class named by `settings.DEFAULT_EXCEPTION_REPORTER_FILTER`, made once for the process and kept (`django/views/debug.py:get_exception_reporter_filter`, `django/views/debug.py:get_default_exception_reporter_filter`).

**By name, always.** `SafeExceptionReporterFilter.cleanse_setting` takes a key and a value, and returns a row of stars in place of the value when the key looks sensitive. The test is a regular expression, `SafeExceptionReporterFilter.hidden_settings`, searched for anywhere in the key without regard to case: `"API"`, `"AUTH"`, `"TOKEN"`, `"KEY"`, `"SECRET"`, `"PASS"`, `"SIGNATURE"` or `"HTTP_COOKIE"`. The name of the session cookie is treated the same. A dictionary is cleansed key by key, to any depth, and the items of a list or a tuple are gone through for dictionaries inside them (`django/views/debug.py:SafeExceptionReporterFilter.cleanse_setting`).

Put to a few settings, headers and cookies, the filter stars `"PASSENGERS"` beside the secret key, reaches into the database's dictionary and the administrators' list, and leaves a callable setting printing as it did:

```text recording=views
SafeExceptionReporterFilter: what is replaced by stars
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
    ...
```

The match is on a fragment of the name, so it errs on the side of hiding: a setting called `"PASSENGERS"` is starred for the four letters it begins with. The same method is applied to every setting, to every entry of the request's `META`, where it catches the whole `"Cookie"` header and any header with a key or a token in its name, and to each cookie by its name (`django/views/debug.py:SafeExceptionReporterFilter.get_safe_settings`, `django/views/debug.py:SafeExceptionReporterFilter.get_safe_request_meta`, `django/views/debug.py:SafeExceptionReporterFilter.get_safe_cookies`). It runs whatever `settings.DEBUG` is: the secret key is starred on a developer's own debug page.

A setting whose value can be called is not left as it is. It is wrapped in a `CallableSettingWrapper`, an object whose only behaviour is to have the same `repr`, so that the debug page does not call the setting, as a template does with a callable it is asked to print (`django/views/debug.py:CallableSettingWrapper`).

> **Trap.** `ExceptionReporter.get_traceback_data` puts the request's `GET` in the report as it is, without the filter, and the query string stands there as well, in the request's address and in `META`'s `"QUERY_STRING"`, a name that looks like no secret's. A token passed in a URL is in the debug page and the error email alike, and a `sensitive_post_parameters` or a `sensitive_variables` that names it hides it in none of those three places (`django/views/debug.py:ExceptionReporter.get_traceback_data`).

**By mark, in production.** The other kind hides what a developer has marked: the local variables named by `sensitive_variables` and the posted fields named by `sensitive_post_parameters`. It hides them only when `SafeExceptionReporterFilter.is_active` returns true, which is when `settings.DEBUG` is `False` (`django/views/debug.py:SafeExceptionReporterFilter.is_active`).

> **Trap.** A mark hides nothing while `settings.DEBUG` is on. A developer who decorates a view and makes it fail finds the marked value on the debug page, as though the decorator had not worked, and the page shows what the production site's reports will not (`django/views/debug.py:SafeExceptionReporterFilter.is_active`).

The Gazette's failing view holds a password, `"open sesame"`, and a shelf, `"the attic"`, in two local variables before it raises. The view *guarded* is the failing view under `sensitive_variables("password")`, and the view *all_guarded* the same under `sensitive_variables()`. A second view, *till*, keeps the posted data in a local variable, and the view *post_guarded* is *till* under `sensitive_post_parameters("pin")`:

```python
# gazette/views.py
def till(request, year):
    posted = request.POST
    raise LookupError("the till is shut")
```

Each line asks whether a value is in a report of what a view raised, *html* or *text*, made as for the debug page with `settings.DEBUG` on (True) or as for the email with it off (False), the third argument being what was posted. Look for the marks honoured with the setting off and passed over with it on: the password gone from the HTML report of the view *guarded* and back once the setting is on, the shelf gone only under the view *all_guarded*, and the pin starred in both reports of the view *post_guarded*, while the note posted beside it stays and the undecorated view *till* shows the pin in both.

```text recording=views
What a report shows of a frame's variables and of the posted data
...
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
      ...
```

## `sensitive_variables` and `sensitive_post_parameters`

`sensitive_post_parameters` and `sensitive_variables` only leave marks: one on the request, where the filter reads it, and one the filter finds from a traceback.

`sensitive_post_parameters` is the simpler. Its wrapper sets an attribute on the request naming the fields, or the word `"__ALL__"`, each time the view is called (`django/views/decorators/debug.py:sensitive_post_parameters`). `SafeExceptionReporterFilter.get_post_parameters` reads the attribute and, in production, stars those values in a copy of `POST`. A second method does the same for any `MultiValueDict` among a frame's local variables, which is how the `POST` that the view *till* keeps in a local variable was starred above. It was written for an exception raised by a lookup of a missing key in `POST`, whose frame holds the whole of it (`django/views/debug.py:SafeExceptionReporterFilter.get_cleansed_multivaluedict`).

`sensitive_variables` is about a function's locals, and the filter is handed frames, not functions. The decorator is found on the stack by its wrapper's name, `"sensitive_variables_wrapper"`. Each time the wrapper is called it stores the names on itself and calls the function. When the filter is given a frame, it walks from that frame up through its callers looking for a frame of that name, and reads the names from the function object in that frame's locals (`django/views/debug.py:SafeExceptionReporterFilter.get_traceback_frame_variables`).

Because the walk goes up through the callers, the names cover more than the decorated function. They apply to every frame beneath the wrapper on the stack, the frame of a coroutine that is not running and those beneath it aside, down to the next decorated function, whose own names take over from there. And one thing is starred whatever `settings.DEBUG` is: in the wrapper's own frame, the arguments it was called with, as a precaution, since they may be the very values that the decorated function's variables were named to hide (`django/views/debug.py:SafeExceptionReporterFilter.get_traceback_frame_variables`).

For a coroutine function the decorator makes no wrapper. It records the names in a module-level dictionary, keyed by the file and first line of the function, or, where it has a `__wrapped__`, of the innermost function that chain leads to, and returns the function unchanged; the filter looks a coroutine's frame up in the dictionary by the same key (`django/views/decorators/debug.py:sensitive_variables`).

> **Why.** In the traceback a report is made from, the frame of a coroutine that is not running has `None` for its `"f_back"`, the link from a frame to its caller that the walk follows; so the names of a coroutine function are kept where the filter can find them from the frame's own code, its file and its first line (`django/views/debug.py:SafeExceptionReporterFilter.get_traceback_frame_variables`).

Django uses both on its own code. `authenticate` in `django/contrib/auth/__init__.py` is decorated with `sensitive_variables("credentials")`, and `LoginView` has `sensitive_post_parameters()` among the decorators on its `dispatch`, which marks every posted field (`django/contrib/auth/views.py:LoginView`).

## The text report and the error email

The text report is not the HTML report in another format. The HTML one shows every frame's local variables, as the filter has left them; the text one has no place for them, and shows none whatever `settings.DEBUG` is (`django/views/templates/technical_500.txt`).

The password's value is in every HTML report of the Gazette's failing view, made with the setting on or off, and in no text report; the shelf's is missing too from the text made as for the email:

```text recording=views
What a report shows of a frame's variables and of the posted data
...
      "open sesame" in html(views.missing, True)  ->  True
      "open sesame" in text(views.missing, True)  ->  False
      "open sesame" in html(views.missing, False)  ->  True
      "open sesame" in text(views.missing, False)  ->  False
      "the attic" in text(views.missing, False)  ->  False
      ...
```

Since the text report is what `AdminEmailHandler` sends unless asked for more, the default error email has a traceback, the request and the settings in it, and no variable from any frame. A handler made with `include_html=True` adds the HTML report as an alternative body, and that one carries the frames' variables, less what the marks hide, though its reporter was made for an email as well (`django/utils/log.py:AdminEmailHandler.emit`).
