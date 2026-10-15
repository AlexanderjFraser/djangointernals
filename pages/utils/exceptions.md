---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Django's exceptions: `django.core.exceptions`

`django/core/exceptions.py` holds the exceptions its docstring calls global, many raised in one part of Django and caught in another: the bases of each model's `Model.DoesNotExist` and `Model.MultipleObjectsReturned`, `SuspiciousOperation` and its subclasses, `PermissionDenied`, `BadRequest`, `ImproperlyConfigured`, `ValidationError` with `NON_FIELD_ERRORS`, the compiler's `EmptyResultSet` and `FullResultSet`, and `SynchronousOnlyOperation`, which `async_unsafe` raises.

The code that raises an exception and the code that catches it are often in different parts of Django: the ORM raises a model's `Model.DoesNotExist` and the template engine catches it; the request raises `DisallowedHost` and the handler answers it. The module imports nothing of Django but `make_hashable`, so any part can import it (`django/core/exceptions.py`). Most of its classes are a name, a base and a docstring.

## Who raises each, and what becomes of it

| exception | base | raised by | what becomes of it |
|---|---|---|---|
| `ObjectDoesNotExist` | `Exception` | a model's `Model.DoesNotExist`, from `QuerySet.get` (`django/db/models/query.py:QuerySet.get`) | `get_object_or_404` raises `Http404` instead (`django/shortcuts.py:get_object_or_404`); a template renders `"string_if_invalid"`, empty by default |
| `MultipleObjectsReturned` | `Exception` | a model's `Model.MultipleObjectsReturned`, from `QuerySet.get` | it goes up |
| `ObjectNotUpdated` | `Exception` | a model's `Model.NotUpdated`, from a forced update that changed no row (`django/db/models/base.py:Model._save_table`) | it goes up |
| `FieldDoesNotExist` | `Exception` | `Options.get_field` (`django/db/models/options.py:Options.get_field`) | the code that asked; a query raises `FieldError` instead |
| `FieldError` | `Exception` | a query's keyword that names no field (`django/db/models/sql/query.py:Query.names_to_path`) | it goes up |
| `FieldFetchBlocked` | `FieldError` | `FETCH_RAISE`, when a field not loaded is read (`django/db/models/fetch_modes.py:FetchRaise.fetch`) | it goes up ([Deferred fields and fetch modes in a queryset](../querysets/deferred.md)) |
| `ValidationError` | `Exception` | validators (`django/core/validators.py`) | a form's or a model's errors |
| `SuspiciousOperation` | `Exception` | its subclasses; markup `strip_tags` gives up on (`django/utils/html.py:strip_tags`) | a 400, logged under `"django.security"` (`django/core/handlers/exception.py:response_for_exception`) |
| `DisallowedHost` | `SuspiciousOperation` | a host `ALLOWED_HOSTS` refuses (`django/http/request.py:HttpRequest.get_host`) | a 400 |
| `DisallowedRedirect` | `SuspiciousOperation` | a redirect too long or to a scheme not allowed (`django/http/response.py:HttpResponseRedirectBase.__init__`) | a 400 |
| `RequestDataTooBig` | `SuspiciousOperation` | a body over `DATA_UPLOAD_MAX_MEMORY_SIZE` (`django/http/request.py:HttpRequest._check_data_too_big`) | a 400 |
| `TooManyFieldsSent` | `SuspiciousOperation` | fields over `DATA_UPLOAD_MAX_NUMBER_FIELDS` (`django/http/request.py:QueryDict.__init__`) | a 400 |
| `TooManyFilesSent` | `SuspiciousOperation` | files over `DATA_UPLOAD_MAX_NUMBER_FILES` (`django/http/multipartparser.py:MultiPartParser._parse`) | a 400 |
| `SuspiciousMultipartForm` | `SuspiciousOperation` | a multipart body on which the parser seems to loop (`django/http/multipartparser.py:LazyStream._update_unget_history`) | a 400 |
| `SuspiciousFileOperation` | `SuspiciousOperation` | a file name reaching outside its directory (`django/utils/_os.py:safe_join`) | a 400 |
| `BadRequest` | `Exception` | a urlencoded form whose encoding is not UTF-8 (`django/http/request.py:HttpRequest._load_post_and_files`) | a 400 |
| `PermissionDenied` | `Exception` | a permission check (`django/contrib/auth/mixins.py:AccessMixin.handle_no_permission`) | a 403; from a backend, `authenticate` tries no other (`django/contrib/auth/__init__.py:authenticate`) |
| `RequestAborted` | `Exception` | a client gone (`django/core/handlers/asgi.py:ASGIHandler.read_body`) | `ASGIHandler.handle` sends nothing |
| `ImproperlyConfigured` | `Exception` | a setting read before any are configured (`django/conf/__init__.py:LazySettings._setup`), and other wrong configurations | it goes up |
| `AppRegistryNotReady` | `Exception` | the registry asked before it is ready (`django/apps/registry.py:Apps.check_apps_ready`) | it goes up |
| `MiddlewareNotUsed` | `Exception` | a middleware's factory | the layer is left out ([Building the middleware chain](../handlers/chain.md)) |
| `ViewDoesNotExist` | `Exception` | a dotted path that names no view (`django/urls/utils.py:get_callable`) | the URL checks report it |
| `EmptyResultSet` | `Exception` | a condition that can match no row (`django/db/models/sql/where.py:WhereNode.as_sql`) | the compiler sends no statement, or writes a false condition |
| `FullResultSet` | `Exception` | a condition that matches every row | the compiler writes no `"WHERE"` |
| `SynchronousOnlyOperation` | `Exception` | `async_unsafe` | it goes up |

*A 400 or a 403 is the handler's answer when the exception leaves a view or a middleware. A cell that says "it goes up" means only that the handler does not name that exception: a caller may catch it, and one that leaves a view or a middleware is a 500, like any the handler does not name, unless `settings.DEBUG_PROPAGATE_EXCEPTIONS` is true ([How an exception becomes a response](../handlers/exceptions.md)); the result sets are told in [The where clause: `build_filter`, `add_q` and `WhereNode`](../sql/where.md).*

## `ValidationError`: one error, a list, or a dictionary

`ValidationError.__init__` gives the error one of three shapes, chosen by its first argument (`django/core/exceptions.py:ValidationError.__init__`):

- **a single error**: a message, a code a program can test, and params for the message, kept as `ValidationError.message`, `ValidationError.code` and `ValidationError.params`, with a list of the error itself as `ValidationError.error_list`;
- **a list**: each item made a `ValidationError` if it is not one, and the single errors of all of them kept in `error_list`; a dictionary-shaped item gives its errors without their names;
- **a dictionary** of field names: each value made a `ValidationError`, and its list kept under the name in `ValidationError.error_dict`.

Given a `ValidationError`, it takes that error's dictionary, its list, or its message, code and params, which win over a code and params passed beside it.

A single or list-shaped error iterates as its messages, each with its params put in by `%`; a dictionary-shaped one as pairs of a name and its messages (`django/core/exceptions.py:ValidationError.__iter__`). `ValidationError.messages` is a flat list of strings for any shape; `ValidationError.message_dict` is the dictionary of them, and raises `AttributeError` for the other shapes. `ValidationError.update_error_dict` adds the errors to a dictionary it is given, by name, or under `NON_FIELD_ERRORS`, `"__all__"`; `Model.full_clean` gathers its steps' errors with it, and `BaseForm.add_error` files a form's errors in the same shape ([Validation: `full_clean`, `cleaned_data` and the errors](../forms/validation.md)).

`ValidationError.__eq__` compares hashes. `ValidationError.__hash__` hashes a single error's message, code and params; a dictionary-shaped error's dictionary through `make_hashable`, which sorts the names and keeps each list's order; a list-shaped error's errors sorted by message. So a list's order does not count, the order within a dictionary's list does, and one error is not equal to a list of it.

```text
# a run: a ship's errors
small  = ValidationError("Tonnage %(tons)s is too small.", code="min_tonnage", params={"tons": 0})
both   = ValidationError([small, "A ship needs a home port."])
byname = ValidationError({"tonnage": small, "home": ["A ship needs a home port."]})
home   = both.error_list[1]

list(small)                             ['Tonnage 0 is too small.']
both.messages                           ['Tonnage 0 is too small.', 'A ship needs a home port.']
both.update_error_dict({})              {'__all__': [ValidationError(['Tonnage 0 is too small.']), ValidationError(['A ship needs a home port.'])]}
dict(byname)                            {'tonnage': ['Tonnage 0 is too small.'], 'home': ['A ship needs a home port.']}
ValidationError([byname]).messages      ['Tonnage 0 is too small.', 'A ship needs a home port.']
both == ValidationError([home, small])  True
small == ValidationError([small])       False
```

> **Trap.** A message given params is a `%` format, filled in when the error is read: in `ValidationError("100% of %(tons)s tons", params={"tons": 366})` the lone per cent sign raises `TypeError` then, not when the error is made.

## A model's exceptions and the template engine

`ModelBase` makes each model that is not abstract its own `Model.DoesNotExist`, `Model.MultipleObjectsReturned` and `Model.NotUpdated` from `ObjectDoesNotExist`, `MultipleObjectsReturned` and `ObjectNotUpdated`, or from the parent model's classes; `Model.NotUpdated` derives from `DatabaseError` too, for backward compatibility ([`ModelBase`: a class statement becomes a model](../models/metaclass.md)). An `except` can name one model's error or every model's.

`ObjectDoesNotExist.silent_variable_failure` is true. When a template variable's lookup raises an exception with that attribute true, `Variable._resolve_lookup` gives the engine's `"string_if_invalid"`, empty by default, in its place; any other exception goes on up ([Variables and filters: `FilterExpression` and `Variable`](../templates/variables.md)) (`django/template/base.py:Variable._resolve_lookup`).

```text
# a run: Valletta has two ships, Piraeus none
Port.objects.get(name="Rhodes")          raises Port.DoesNotExist: Port matching query does not exist.
  caught by except ObjectDoesNotExist    Port.DoesNotExist
[{{ port.ships.get }}], port Piraeus     '[]'
[{{ port.ships.get }}], port Valletta    raises Ship.MultipleObjectsReturned: get() returned more than one Ship -- it returned 2!
```

## `SynchronousOnlyOperation` and `async_unsafe`

The documentation says some of Django relies on thread-safety and does not work under coroutines sharing a thread (`docs/ref/exceptions.txt`); `async_unsafe` marks such code. Its wrapper asks `asyncio.get_running_loop` whether a loop runs in the calling thread; if one does, and the environment variable `"DJANGO_ALLOW_ASYNC_UNSAFE"` is empty or unset, it raises `SynchronousOnlyOperation`, and otherwise calls the function (`django/utils/asyncio.py:async_unsafe`). It asks about the thread, not the caller: a plain function called from a coroutine is refused too, and the same call through `sync_to_async`, on a thread with no loop, is not. The variable is read at each call.

Given a function, `async_unsafe` wraps it with a message of its own; given a message, it returns a decorator that raises with that one. `BaseDatabaseWrapper` marks the methods that open and close a connection, make a cursor, commit, roll back and keep savepoints, so a query run in a coroutine fails ([The asynchronous methods of a queryset](../querysets/async.md)) (`django/db/backends/base/base.py:BaseDatabaseWrapper.cursor`). A deployment check reports the variable set (`django/core/checks/async_checks.py:check_async_unsafe`).

```python
# harbour/office/notices.py
from django.utils.asyncio import async_unsafe


@async_unsafe
def post_notice(text):
    return f"posted: {text}"


@async_unsafe("The notice board is written from a thread.")
def pin_notice(text):
    return f"pinned: {text}"
```

```text
# a run of the two functions
in a coroutine:
  post_notice("Beagle sails")                  raises SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async.
  pin_notice("Beagle sails")                   raises SynchronousOnlyOperation: The notice board is written from a thread.
  the same, DJANGO_ALLOW_ASYNC_UNSAFE set       'pinned: Beagle sails'
  await sync_to_async(pin_notice)("Beagle sails")  'pinned: Beagle sails'
```
