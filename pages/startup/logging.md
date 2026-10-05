---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Logging

`configure_logging` is the first thing `django.setup` does. It applies Django's own configuration of Python's `logging` module, `DEFAULT_LOGGING`, and then the project's `settings.LOGGING`. The same file holds `AdminEmailHandler`, the handler that emails errors to the administrators, and `log_response`, through which the request path logs a response that reports an error.

Django adds no logging system of its own. It uses the standard library's: its code obtains loggers by name with `logging.getLogger` and writes records to them, and where those records end up is a matter of configuration. What Django supplies is a default configuration, the moment at which configuration is applied, and a few classes that a configuration can name. All of it is in `django/utils/log.py`.

## Two configurations, one after the other

`configure_logging` is called with two settings, and what it does depends on both (`django/utils/log.py:configure_logging`).

`LOGGING_CONFIG` is the dotted path of a function that takes a configuration dictionary. Its default is `"logging.config.dictConfig"`, the standard library's `logging.config.dictConfig`. If the setting is empty, `configure_logging` does nothing at all: Django's defaults are not applied either, and logging is left as the process found it.

Otherwise it imports that function, then applies Django's defaults by calling the standard library's function with `DEFAULT_LOGGING`, and then, if `LOGGING` is not empty, calls the function with `LOGGING`.

The two dictionaries are not merged. They are two separate calls, and the second is whatever the standard library makes of a second configuration. `DEFAULT_LOGGING` sets `"disable_existing_loggers"` to false, so that applying it does not disable loggers the process already has. A project's dictionary that leaves the key out gets the standard library's default for it, which is true. A logger the first call configured is then disabled unless the project's dictionary names it or a parent of it. Neither case keeps what the first call set up. A logger the dictionary names has its handlers replaced by the ones the dictionary gives it, and one that is only the child of a named logger is reset: no level, no handlers, and its records passed up.

Because `django.setup` begins with this call, logging is configured before `Apps.populate` imports any application, so a record logged while a project's models are being imported is handled as the project configured. A second call of `django.setup` configures logging a second time, and makes every handler anew.

## What the default configures

`DEFAULT_LOGGING` configures two loggers and leaves the root logger alone (`django/utils/log.py:DEFAULT_LOGGING`).

| logger | level | handlers | passes records up |
|---|---|---|---|
| `"django"` | `"INFO"` | `"console"`, `"mail_admins"` | yes |
| `"django.server"` | `"INFO"` | `"django.server"` | no |

*The loggers `DEFAULT_LOGGING` configures.*

| handler | level | filter | writes to |
|---|---|---|---|
| `"console"` | `"INFO"` | `RequireDebugTrue` | the standard error stream |
| `"mail_admins"` | `"ERROR"` | `RequireDebugFalse` | email, through `AdminEmailHandler` |
| `"django.server"` | `"INFO"` | none | the standard error stream, formatted by `ServerFormatter` |

*The handlers it gives them.*

Every logger Django writes to has a name beginning with `django.`, so every record climbs to the `"django"` logger and meets its two handlers, each guarded by a filter that looks at `settings.DEBUG`. The effect is a switch: with `settings.DEBUG` on, records go to the console and no mail is sent; with it off, nothing goes to the console and errors are offered to the mail handler. The filters read the setting each time a record passes, not when logging is configured (`django/utils/log.py:RequireDebugFalse`).

`"django.server"` is the exception. It is the development server's log of requests. It has a handler of its own with no filter, and it does not pass its records up, so those lines appear whatever the setting is. Its formatter, `ServerFormatter`, colours each line by the status code the server attached to the record (`django/utils/log.py:ServerFormatter.format`).

This was recorded by logging a record to each of several loggers, first with `settings.DEBUG` false and then with it true, and noting which handlers had their `emit` method called.

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

Three lines of it deserve a second look.

With `settings.DEBUG` off, a warning on `"django.request"`, which is what a 404 produces, reaches no handler. It is below the level of the mail handler, and the console is filtered out.

A record of the level `logging.DEBUG` on `"django.db.backends"`, which is what each SQL query produces, reaches no handler in either mode. The `"django"` logger's level is `logging.INFO`, and a record below a logger's effective level is dropped before any handler sees it. Giving `"django.db.backends"` a lower level in `LOGGING` is not enough to see queries on the console, because the `"console"` handler has a level of its own, also `"INFO"`: the entry has to bring a handler that admits such records as well.

A record on a logger outside the `django` namespace, here one named `"library"`, gets nothing from Django's defaults. Django gives the root logger no handler, so the record falls to the standard library's handler of last resort, which prints warnings and errors to the standard error stream. A project's own loggers are configured by the project or not at all.

Put together, the defaults come to this. In development, everything Django logs at `"INFO"` or above appears on the console, and no mail is sent. In production nothing is written anywhere. An error is passed to the handler that mails the administrators, and that handler sends nothing unless `ADMINS` names someone, which by default it does not. A project that wants a record of what its production servers did has to configure one.

## The loggers Django writes to

| logger | what is written to it |
|---|---|
| `"django.request"` | a response with a status of 400 or above: a warning for a 4xx, an error for a 5xx |
| `"django.security."` and the exception's class name | a `SuspiciousOperation` that became a 400 response, such as `DisallowedHost` |
| `"django.security.csrf"` | a request the CSRF middleware rejected |
| `"django.server"` | the development server's line for each request |
| `"django.db.backends"` | each statement a cursor executes, at the level `logging.DEBUG`, while the connection is recording queries |
| `"django.template"` | an exception raised while a template variable was being resolved, at the level `logging.DEBUG` |
| `"django.dispatch"` | an exception in a signal receiver that `Signal.send_robust` caught |

*The loggers most often met. Each is obtained by name in the module that writes to it.*

A connection records queries, and logs them, when `settings.DEBUG` is true or its `force_debug_cursor` is set; otherwise its cursors are of a class that does neither (`django/db/backends/base/base.py:BaseDatabaseWrapper.queries_logged`, `django/db/backends/utils.py:CursorDebugWrapper.debug_sql`).

## `log_response`: a response is logged once

The request path seldom writes to a logger itself. It calls `log_response`, which hands the message and the response's status to `log_message`, then marks the response as logged; for a response that is already marked it returns at once (`django/utils/log.py:log_response`). The mark is what lets two layers both try. When an exception of any kind but `Http404` becomes a response, the code that catches it logs the response there, with the exception attached so that the record carries a traceback (`django/core/handlers/exception.py:response_for_exception`). Later the request handler, seeing a response with a status of 400 or more come out of the middleware chain, calls `log_response` again (`django/core/handlers/base.py:BaseHandler.get_response`). The first call wins, and the second finds the mark. A 404, and a response that a view simply returned with such a status, are logged by the second call alone.

Not everything goes through it. The ASGI handler answers a request it could not build before the middleware chain is reached, and it logs one such answer with a call of its own and the other not at all ([The two entry points](../handlers/entry.md#an-asgi-request)).

`log_message`, which the development server also uses, does the logging. It chooses the level from the status, error for 500 and above and warning for 400 and above, and attaches the request and the status code to the record, where a handler or a formatter can use them. Before it logs, it escapes every string argument so that control characters, a line break among them, are written as escape sequences. A path taken from a request is text an attacker controls, and without this a crafted path could forge lines in a log (`django/utils/log.py:log_message`).

## `AdminEmailHandler`: error email is a log handler

Django has no separate feature for mailing errors to the administrators. With `settings.DEBUG` off, an uncaught exception in a view becomes a 500 response, the response is logged as an error on `"django.request"`, the record reaches the `"mail_admins"` handler, and the handler sends the mail.

`AdminEmailHandler.emit` does nothing when `ADMINS` is empty, unless a subclass has replaced the method that sends, which it takes as a sign that the mail has somewhere else to go (`django/utils/log.py:AdminEmailHandler.emit`). Otherwise it writes a subject from the record's level and message, and a body that ends with a traceback and, where the record carries a request, the details of the request. The message goes out through `mail_admins` (`django/utils/log.py:AdminEmailHandler.send_mail`).

The traceback is drawn by an exception reporter, the class that also draws the debug page. The handler imports the class named by `DEFAULT_EXCEPTION_REPORTER` when it is constructed, which is why the recording of `django.setup` shows that setting being read inside `configure_logging`: the default configuration has just made the handler.
