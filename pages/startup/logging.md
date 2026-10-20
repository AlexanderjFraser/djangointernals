---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Logging

`configure_logging` is the first thing `django.setup` does. Where `settings.LOGGING_CONFIG` names a function, it applies Django's own configuration of Python's `logging` module, `DEFAULT_LOGGING`, and then passes that function the project's `settings.LOGGING`, if it is not empty. The same file holds `AdminEmailHandler`, the handler that emails errors to the administrators, and `log_response`, through which the request path logs a response that reports an error, by default on the logger `"django.request"`.

Django adds no logging system of its own. It uses the standard library's: its code obtains loggers by name with `logging.getLogger` and writes records to them, and where those records end up is a matter of configuration. What Django supplies is a default configuration, the moment at which configuration is applied, and a few classes that a configuration can name. All of it but the call in `django.setup` is in `django/utils/log.py`.

## `configure_logging`: Django's configuration, then the project's

`configure_logging` is called with two settings, and what it does depends on both (`django/utils/log.py:configure_logging`).

`LOGGING_CONFIG` is the dotted path of a function that takes a configuration dictionary. Its default is `"logging.config.dictConfig"`, the standard library's `logging.config.dictConfig`. If the setting is `None` or empty, `configure_logging` does nothing at all: Django's defaults are not applied either, and logging is left as the process found it.

Otherwise it imports that function, then applies Django's defaults by calling the standard library's function with `DEFAULT_LOGGING`, and then, if `LOGGING` is not empty, calls the function with `LOGGING`.

Because `django.setup` begins with this call, logging is configured before `Apps.populate` imports any application, so a record logged while a project's models are being imported is handled as the project configured.

## What `DEFAULT_LOGGING` configures

`DEFAULT_LOGGING` configures two loggers, `"django"` and `"django.server"`, and leaves the root logger alone (`django/utils/log.py:DEFAULT_LOGGING`).

Every logger Django writes to has a name beginning with `django.`, so every record climbs to the `"django"` logger and meets its two handlers, each guarded by a filter that looks at `settings.DEBUG`: `"console"` by `RequireDebugTrue` and `"mail_admins"` by `RequireDebugFalse`. The effect is a switch: with `settings.DEBUG` on, records go to the console, which writes to the standard error stream, and no mail is sent; with it off, nothing goes to the console and errors are offered to the mail handler. The filters read the setting each time a record passes, not when logging is configured (`django/utils/log.py:RequireDebugFalse`).

`"django.server"` is the exception. It is the development server's log of requests, at the level `"INFO"`. It has a handler of its own, `"django.server"`, at the same level and with no filter, which writes to the standard error stream; and the logger does not pass its records up, so those lines appear whatever the setting is. The handler's formatter, `ServerFormatter`, colours a line by the status code the server attached to its record, where the terminal supports colour (`django/utils/log.py:ServerFormatter.format`).

In the figure, follow a record up from the logger it is logged on, past loggers with no handler of their own, to `"django"`, where the two filters on `settings.DEBUG` decide which of its handlers may act, and on to the root at the top, which holds no handler; `"django.server"` keeps its records to itself.

```text figure=the-loggers
                                  the root logger
                                  no handler of its own: a record that meets no handler on its way up
                                  goes to Python's handler of last resort, which prints warnings and errors
                                ^                                                                   ^
                            "django"              handler "console"   level "INFO"              "library"
                            level "INFO"            RequireDebugTrue                            a project's logger:
                                ^                   acts only while settings.DEBUG is true      nothing from the defaults
"django.request" ---------------|                   -> the standard error stream
"django.security.*" ------------|                 handler "mail_admins"   level "ERROR"
"django.db.backends" -----------|                   RequireDebugFalse
                                                    acts only while settings.DEBUG is false
passes nothing up to "django"   x                   -> email, through AdminEmailHandler

                         "django.server"          handler "django.server"   level "INFO"
                         level "INFO"               no filter
                                                    -> the standard error stream,
                                                       formatted by ServerFormatter
```

*The loggers and handlers of `DEFAULT_LOGGING`, three more of Django's loggers, the root logger above and a project's logger beside. An arrow is a record passed up to the logger above; a handler stands beside the logger that holds it, with its level, its filter and where it writes, and the accent marks the two filters on `settings.DEBUG` that make the switch. `"django.server"`, a child of `"django"` by its name, passes nothing up. `"django.security.*"` stands for every logger whose name begins `"django.security."`.*

Most lines of the recording below follow the switch. Look for three of the records that no handler of Django's takes, each for a reason of its own: a warning on `"django.request"` while `settings.DEBUG` is off, a record on `"django.db.backends"` in either mode, and a record on a project's logger, `"library"`, that only Python's handler of last resort receives.

```text recording=startup
Where a log record goes: the handlers whose emit is called
    with settings.DEBUG False
      "django.request" ERROR                  -> mail_admins
      "django.request" WARNING                -> no handler
      "django.security.DisallowedHost" ERROR  -> mail_admins
      "django.db.backends" DEBUG              -> no handler
      "django" INFO                           -> no handler
      "django.server" INFO                    -> django.server
      "library" WARNING                       -> Python's handler of last resort
    with settings.DEBUG True
      "django.request" ERROR                  -> console
      "django.request" WARNING                -> console
      "django.security.DisallowedHost" ERROR  -> console
      "django.db.backends" DEBUG              -> no handler
      "django" INFO                           -> console
      "django.server" INFO                    -> django.server
      "library" WARNING                       -> Python's handler of last resort
```

A 404 is logged as a warning on `"django.request"`, below the mail handler's level of `"ERROR"`, so while `settings.DEBUG` is off, with the console's filter shut, nothing takes it.

A query is logged, if at all, on `"django.db.backends"` at the level `logging.DEBUG`, below the `logging.INFO` that the logger inherits from `"django"`, and a record below a logger's effective level is dropped before any handler sees it, in either mode. Giving `"django.db.backends"` a lower level in `LOGGING` is not enough to see queries on the console, because the `"console"` handler has a level of its own, also `"INFO"`: a handler that admits such records has to be on their way up as well.

A project's own logger gets nothing from Django's defaults. Django gives the root logger no handler, so a record on `"library"` meets none on its way up and falls to the standard library's handler of last resort, which prints warnings and errors to the standard error stream.

Put together: with `settings.DEBUG` on, everything Django logs at `"INFO"` or above appears on the console, and no mail is sent. With it off, as in production, Django writes only the development server's lines, and an error is passed to the mail handler, which sends nothing unless `ADMINS` names someone, as by default it does not. A project that wants a record of what its production servers did has to configure one.

## What a project's `LOGGING` does to the defaults

`settings.LOGGING` is not merged with `DEFAULT_LOGGING`. The two are applied by two separate calls, and the second is, by default, whatever the standard library makes of a second configuration over the first: a logger the project's dictionary names has its handlers replaced by the ones the dictionary gives it, and one the dictionary does not name but whose name puts it below a named one is reset, with no level, no handlers, and its records passed up (`django/utils/log.py:configure_logging`).

`"django.server"` is a child of `"django"` by its name. When a project's `LOGGING` gives `"django"` a handler of its own, `"project"`, and does not name `"django.server"`, the line of `"django.server"` below shows the reset: the level, the handler and the refusal to pass records up that `DEFAULT_LOGGING` gave it are gone. Beside it, the error on `"django.request"` reaches the project's handler and not the mail handler, which the replacement took from `"django"`.

```text recording=startup
LOGGING that names "django" and not "django.server": the server's logger is reset, and its records go to the project's handler
    ...
    "django": level INFO, handlers project, propagate True
    "django.server": level NOTSET, handlers none, propagate True
    "django.server" INFO                    -> project
    "django.request" ERROR                  -> project
```

From then on the development server's lines go to whatever handlers `"django"` and the root have, and no longer pass through the handler that formatted them with `ServerFormatter`.

A logger that exists when the project's dictionary is applied, and that the dictionary neither names nor puts below a named one, is disabled if the dictionary's `"disable_existing_loggers"` is true. `DEFAULT_LOGGING` sets it to false, and so applying it disables no logger the process already has; a project's dictionary that leaves it out gets the standard library's default, which is true. So a dictionary that leaves the key out and names no logger but the root disables every logger obtained before `django.setup` applied it, Django's own and the project's alike, and none obtained after.

A disabled logger keeps its handlers, but drops the records logged on it without passing them up. A record logged on a logger that is not disabled still reaches the handlers of the loggers above it, disabled or not, because `logging.Logger.callHandlers` climbs by each logger's handlers and whether it passes records up, and never asks whether a logger is disabled.

The records below were logged under such a dictionary, which gives only the root logger a handler, `"project"`. `"library.early"` was obtained before `django.setup` and `"library.late"` after it; `"django.security.DisallowedHost"` was first obtained at its own line, after `django.setup`.

```text recording=startup
Where a log record goes, with LOGGING that leaves out "disable_existing_loggers": the handlers whose emit is called
    "django.request" ERROR                  -> no handler
    "django.server" INFO                    -> no handler
    "django.security.DisallowedHost" ERROR  -> mail_admins, project  (the logger is made at this line, by logging.getLogger)
    "library.early" WARNING                 -> no handler
    "library.late" WARNING                  -> project
```

What is spared turns on when a logger was first obtained. `response_for_exception` obtains the logger named `"django.security."` and the exception's class name as it handles a `SuspiciousOperation`, so a logger first obtained then, after the dictionary was applied, is not disabled, and here its error reaches `"mail_admins"`, the handler of the disabled `"django"`, as well as `"project"` (`django/core/handlers/exception.py:response_for_exception`).

> **Trap.** A project's `LOGGING` that leaves out `"disable_existing_loggers"` and names none of Django's loggers turns off those already made, the error mail with them, as the documentation warns (`docs/topics/logging.txt`).

A second call of `django.setup` configures logging a second time and makes every handler anew ([Who calls `django.setup`](callers.md) has the rest of such a call). A logger obtained between the two calls exists when the second applies the project's dictionary, and so can be disabled by it: follow `"library.between"` across it. The last line asks whether the root's handler is still the one the first call made.

```text recording=startup
django.setup() twice in one process, with LOGGING that leaves out "disable_existing_loggers": a logger obtained between the two calls is disabled by the second
    ...
    django.setup()
      configure_logging
    between = logging.getLogger("library.between")
    between.disabled  -> False
    "library.between" WARNING               -> project
    django.setup(), a second time
      configure_logging
    between.disabled  -> True
    "library.between" WARNING               -> no handler
    the root logger's handler is the one the first django.setup() made: False
```

## The loggers Django writes to

| logger | what is written to it |
|---|---|
| `"django.request"` | a response with a status of 400 or above not logged on a security logger: a warning for a 4xx, an error for a 5xx |
| `"django.security."` and the exception's class name | a `SuspiciousOperation`, such as `DisallowedHost` |
| `"django.security.csrf"` | a request the CSRF middleware rejected |
| `"django.server"` | the development server's line for each request |
| `"django.db.backends"` | the statements a cursor executes, at the level `logging.DEBUG`, while the connection is recording queries |
| `"django.template"` | an exception raised while a template variable was being resolved, at the level `logging.DEBUG` |
| `"django.dispatch"` | an exception in a signal receiver that `Signal.send_robust` caught |

*Some of Django's loggers.*

A connection records queries, and logs them, when `settings.DEBUG` is true or its `force_debug_cursor` is set; otherwise its cursors are of a class that does neither (`django/db/backends/base/base.py:BaseDatabaseWrapper.queries_logged`, `django/db/backends/utils.py:CursorDebugWrapper.debug_sql`).

## `log_response`: a response is logged once

The request path seldom writes to a logger itself: it calls `log_response`, which hands the message and the response's status to `log_message`, then marks the response as logged; for a response that is already marked it returns at once (`django/utils/log.py:log_response`).

The mark is what lets two layers both try. When `response_for_exception` turns an exception of any kind but `Http404` into a response, it logs the response there, with the exception attached so that the record carries a traceback (`django/core/handlers/exception.py:response_for_exception`). Later the request handler, seeing a response with a status of 400 or more come out of the middleware chain, calls `log_response` again (`django/core/handlers/base.py:BaseHandler.get_response`).

For the 500 below, the two calls stand at two depths, and only the first reaches the logger.

```text recording=startup
log_response for one 500: called where the exception is caught and again by the handler, which finds the response marked
    GET /broken/, a view that raises
      BaseHandler.get_response
        ...
        response_for_exception(request, a ValueError)
          handle_uncaught_exception
          log_response("%s: %s", 'Internal Server Error', '/broken/', exception=ValueError)  the 500 response is not yet marked
            log_message(the logger "django.request", level=None, status_code=500)
              Logger.error  ("django.request")
        log_response("%s: %s", 'Internal Server Error', '/broken/', exception=None)  the 500 response is already marked
      ...
```

A 404, and a response that a view simply returned with such a status, are logged once, by the handler: `response_for_exception` logs nothing for an `Http404`, so the handler's call finds no mark and logs the 404, as a warning.

Not everything goes through `log_response`. When making the `ASGIRequest` raises `UnicodeDecodeError`, the ASGI handler answers with a 400 before the middleware chain is reached, and logs it itself, as a warning on `"django.request"` ([The two entry points](../handlers/entry.md#an-asgi-request)) (`django/core/handlers/asgi.py:ASGIHandler.create_request`).

`log_message`, which the development server also uses, does the logging. It chooses the level from the status unless its caller names one, error for 500 and above and warning for 400 and above, and attaches the request and the status code to the record, where a handler or a formatter can use them. Before it logs, it escapes every string argument after the message so that control characters, a line break among them, are written as escape sequences (`django/utils/log.py:log_message`).

> **History.** The escaping came with a security fix. Response logging used to write the request's path into the log as it came, so that a crafted path could put control characters, a line break or a terminal's escape sequence, into a log and forge or disguise lines in it (CVE-2025-48432). Django 5.2.2 made `log_response` escape its positional arguments, and 5.2.3 moved the response logging that did not yet go through `log_response` onto it (`docs/releases/5.2.2.txt`, `docs/releases/5.2.3.txt`). The escaping has since moved into `log_message`, which `log_response` calls.

## `AdminEmailHandler`: error email is a log handler

Django has no separate feature for mailing errors to the administrators. With `settings.DEBUG` off, an uncaught exception in a view becomes a 500 response, the response is logged as an error on `"django.request"`, the record reaches the `"mail_admins"` handler, and the handler sends the mail.

`AdminEmailHandler.emit` does nothing when `ADMINS` is empty, unless a subclass has replaced the method that sends, which it takes as a sign that the mail has somewhere else to go (`django/utils/log.py:AdminEmailHandler.emit`). Otherwise it writes a subject from the record's level and message, and a body that ends with a report, with a traceback where the record carries an exception and the request's details where it carries a request. The message goes out through `mail_admins` (`django/utils/log.py:AdminEmailHandler.send_mail`).

The report is drawn by an exception reporter, the class that also draws the debug page ([The debug pages and `ExceptionReporter`](../views/debug.md)). `"mail_admins"` imports the class named by `DEFAULT_EXCEPTION_REPORTER` when it is constructed, so that setting is read as soon as `configure_logging` applies the defaults (`django/utils/log.py:AdminEmailHandler.__init__`).

> **Changed in 6.1.** `AdminEmailHandler` takes `using=`, the alias of the mailer in `MAILERS` to send through, and `email_backend=` is deprecated: the handler refuses it beside `using=`, or once `MAILERS` is defined (`django/utils/log.py:AdminEmailHandler.__init__`). Until 6.1 the handler always sent through a connection made to fail silently, and while `MAILERS` is not defined it still does; once it is, the handler sends through the mailer and catches only `MailerDoesNotExist`, so it no longer ignores a failure to send (`django/utils/log.py:AdminEmailHandler.send_mail`, `docs/howto/mailers-migration.txt`).
