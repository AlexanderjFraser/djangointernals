---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Infrastructure
contents: lazy, lazy-objects, cached-property, importing, inspect, datastructures, choices, encoding, text, parsing, paths, exceptions, deprecation, version
---

# The utility layer

The modules of `django/utils/` that serve every part of Django and belong to none, with `django.core.exceptions`: the lazy values, lazy objects and cached properties by which code puts off work until it is needed, the importing of code named by a dotted path, the data structures and the helpers for text, values and paths that the request cycle and the ORM share, the exceptions they raise, and the tools with which Django deprecates its own API and names its versions.

Some problems come up in every part of a framework of Django's size. Much of its code is written at the top of a module and runs once, as the module is imported, but what that code describes exists only later: the settings, which are read when something first asks for one; the language a message is to be shown in, which belongs to a request; a URL, which needs the URLconf loaded. Classes are named in settings by dotted paths, as strings, and have to be found from them. A form may post several values under one name, and a header's name has no case. Text arrives as bytes and leaves as bytes, and in between it is `str`. And the framework changes from release to release, so its API has to warn the code that uses an old form of it before that form is removed.

`django/utils/` is where Django keeps its answers, and `django/core/exceptions.py` holds many of the exceptions that its parts share. Some modules of `django/utils/` belong to one subsystem, `django/utils/translation/` to internationalization, `django/utils/html.py` to the template engine, `django/utils/http.py` to requests and responses, and are described with it ([Where the other modules of `django/utils/` are told](#where-the-other-modules-of-djangoutils-are-told)). The rest forms no system and has no main flow. Each module is small, the rest of Django imports it, and it imports little of Django in its turn. One idea runs through the first part of the chapter, and it is the one to have before the rest: how Django's code waits.

## Three ways to wait

`django/utils/functional.py` gives Django three ways to put off work, each with its own object, and they differ in when the work is done and whether its result is kept.

A **lazy value** is the proxy that a function made by `lazy` returns. `lazy(func, str)` returns a function that does not call func: it keeps func's arguments in a new instance of a class that `lazy` built, a subclass of `Promise`, and returns that. The class has the methods of the result classes it was given, `str` here, and each of them calls func with the kept arguments and then acts on the result. The result is not kept, and the docstring of `lazy` says so: each use calls the function again (`django/utils/functional.py:lazy`). This is how `django.utils.translation.gettext_lazy` and `reverse_lazy` are made: a message translated in the language active when it is used, and a URL reversed when the URLconf can be read.

A **lazy object** stands in for an object that is made on its first use and then kept. A `LazyObject` holds the object in `LazyObject._wrapped`, which starts as a marker called `empty`; the first time an attribute is read, set or deleted on it, or one of the special methods it forwards is used, it calls `LazyObject._setup`, which a subclass writes to put the object there, and from then on it passes those straight to that object (`django/utils/functional.py:LazyObject`). `SimpleLazyObject` is a `LazyObject` made from a function that returns the object. `django.conf.settings` is a lazy object ([The settings object](startup/settings.md)), as are the default storage and, under the authentication middleware, the user that a request carries.

A **cached property** is computed once for each instance. `cached_property` is a descriptor that a class holds in place of a method. The first read of the attribute on an instance calls the method and writes the result into the instance's own `__dict__`, under the attribute's name; and since the descriptor defines neither `__set__` nor `__delete__`, Python looks in the instance's dictionary before it asks the descriptor, so every later read finds the value there and never reaches the method (`django/utils/functional.py:cached_property.__get__`). Deleting the attribute from the instance makes the next read compute it again.

The harbour office's notice board, a module of the example project, has one of each. FLEET says how many ships the harbour has, HOME is the home port's row, and a Harbour has a list of the ships:

```python
# harbour/office/board.py
from django.utils.functional import SimpleLazyObject, cached_property, lazy

from harbour.fleet.models import Port, Ship


def fleet_size():
    return f"{Ship.objects.count()} ships in harbour"


FLEET = lazy(fleet_size, str)()
HOME = SimpleLazyObject(lambda: Port.objects.get(name="Valletta"))


class Harbour:
    @cached_property
    def ships(self):
        return list(Ship.objects.order_by("name"))
```

A run of the example, with the database holding the ports Valletta and Piraeus and two ships, and the number of SQL statements each line sent beside it:

```text
import harbour.office.board                             0 queries
str(FLEET)                   '2 ships in harbour'       1 query
str(FLEET)                   '2 ships in harbour'       1 query
(a third ship is saved)
str(FLEET)                   '3 ships in harbour'       1 query
HOME.name                    'Valletta'                 1 query
HOME.country                 'Malta'                    0 queries
isinstance(HOME, Port)       True                       0 queries
type(HOME).__name__          'SimpleLazyObject'         0 queries
harbour.ships                a list of 3 ships          1 query
harbour.ships                the same list              0 queries
"ships" in vars(harbour)     True                       0 queries
del harbour.ships
harbour.ships                a new list of 3 ships      1 query
```

Importing the module sent nothing: each of the three was made without its function being called. FLEET counted the ships every time it was made a string, and so saw the third ship once it was saved. HOME fetched its row on the first attribute read and kept it, and it passes for a Port: `LazyObject` answers `__class__` from the wrapped object, so `isinstance` sees the row, while `type`, which does not ask the object, sees the proxy. The harbour's list lived in the instance's dictionary until it was deleted from there.

```text figure=three-deferrals
FLEET = lazy(fleet_size, str)()                  a lazy value: keeps fleet_size and its arguments
  str(FLEET)     calls fleet_size()  ->  '2 ships in harbour'          the result is not kept
  str(FLEET)     calls fleet_size()  ->  '2 ships in harbour'          called again at every use

HOME = SimpleLazyObject(lambda: ...)             a lazy object: its _wrapped is empty
  HOME.name      _wrapped is empty: _setup() calls the lambda, keeps the Port in _wrapped,
                 then reads name from it  ->  'Valletta'
  HOME.country   reads country from the Port in _wrapped  ->  'Malta'

class Harbour: ships = cached_property(ships)    a cached property: a descriptor on the class
  harbour.ships  not in vars(harbour): the descriptor calls ships(harbour)
                 and stores the list in vars(harbour)["ships"]
  harbour.ships  found in vars(harbour): the descriptor is not asked
```

*The three ways to wait, from the example: a lazy value calls its function at every use, a lazy object calls its function once and keeps what it made, and a cached property stores its value on the instance, where Python finds it before the descriptor.*

Lazy values, `keep_lazy` (which lets a function given a lazy argument return a lazy result) and the helpers built on `lazy` are in [Lazy values: `lazy`, `Promise` and `keep_lazy`](utils/lazy.md); the proxy's machinery, its copying and its pickling in [Lazy objects: `LazyObject` and `SimpleLazyObject`](utils/lazy-objects.md); and the descriptor, with `classproperty` and `classonlymethod`, in [`cached_property`, `classproperty` and `classonlymethod`](utils/cached-property.md).

## Code named by a string

A project's settings name code by its dotted path, as text: each entry of `MIDDLEWARE`, the `"BACKEND"` of each cache, storage and task backend, the authentication backends, the password hashers. `import_string` turns such a path into the object. It first tries to import the whole path as a module; then it imports the module up to the path's last dot and returns that module's attribute of the last name, raising `ImportError` if there is none, so that a path naming a module returns the module, and a submodule wins over an attribute of the same name (`django/utils/module_loading.py:import_string`). Both are new in 6.2. The middleware chain is built by calling it on each entry of `MIDDLEWARE` ([Building the middleware chain](handlers/chain.md)).

`autodiscover_modules` imports a module of a given name from every installed application, as the admin does for each application's admin.py, and passes over an application that has no such module; an error raised inside a module that does exist is raised again (`django/utils/module_loading.py:autodiscover_modules`). Django also asks a callable what it accepts before it calls it, through `django/utils/inspect.py`: in debug mode `Signal.connect` refuses a receiver that has no parameter for arbitrary keyword arguments (`django/dispatch/dispatcher.py:Signal.connect`), and `Paginator.count` calls an object list's `count` only if it is a method, not a built-in one, that takes no arguments, and otherwise takes the list's length (`django/core/paginator.py:Paginator.count`). Both modules have their sections: [Importing by name: `import_string` and `autodiscover_modules`](utils/importing.md) and [Asking a callable what it accepts: `django/utils/inspect.py`](utils/inspect.md).

## The shapes of data

A query string or a posted form may give one name several values, though most forms give each name one. A `MultiValueDict` is a `dict` whose values are lists: indexing it gives the last value under a key, and `MultiValueDict.getlist` gives them all (`django/utils/datastructures.py:MultiValueDict`). The request's `QueryDict` is one ([`QueryDict`](http/querydict.md)). Beside it in `django/utils/datastructures.py` are `CaseInsensitiveMapping`, a mapping whose keys are looked up whatever their case, on which a request's and a response's headers are built; `OrderedSet`, which keeps distinct items in the order in which they were added; and `ImmutableList`, a tuple that answers most of a list's methods for changing it with an `AttributeError` and a message of its maker's choosing ([Data structures: `MultiValueDict` and its neighbours](utils/datastructures.md)). The choices of a model field and of a form field, which may be given as pairs, groups, a mapping, an enumeration or a callable, are made into one shape by `normalize_choices` ([Choices: `normalize_choices` and the choice iterators](utils/choices.md)).

`Node`, the tree of `django/utils/tree.py`, is what a `Q` and a query's where clause are built from: a list of children, a connector that joins them, and a mark that negates the whole ([`filter`, `exclude` and `Q` objects](querysets/filters.md)) (`django/utils/tree.py:Node`).

## Text, values and paths

`force_str` makes anything a `str`, decoding bytes as UTF-8 unless told otherwise, and `force_bytes` makes anything bytes; `smart_str` and `smart_bytes` do the same but return a lazy value unchanged, so that a lazy translation stays lazy (`django/utils/encoding.py:smart_str`). The same module turns an internationalized resource identifier into a URI and back, and a file's path into the path of a URL ([Text and bytes: `django/utils/encoding.py`](utils/encoding.md)). `django/utils/text.py` has the helpers that the template filters and the model and storage code call for text: `Truncator`, `slugify`, `get_valid_filename`, `capfirst` and others ([Text helpers: `Truncator` and `django/utils/text.py`](utils/text.md)).

Values arrive as text, from a database that stores dates as text, as SQLite does, or from a serialized fixture, and Django reads them with `django/utils/dateparse.py`. `parse_datetime` tries the standard library's `datetime.datetime.fromisoformat` first, and Django's own pattern only where that fails; for text in neither form it returns `None`, and for text that Django's pattern reads but that names an impossible date it raises `ValueError` (`django/utils/dateparse.py:parse_datetime`). `parse_duration` reads three forms of a duration ([Dates, durations and addresses: `parse_datetime`, `parse_duration` and `clean_ipv6_address`](utils/parsing.md)). `safe_join` joins paths and refuses a result outside the first of them, which is how a storage and a template loader keep a name from reaching outside their directory ([Paths and archives: `safe_join`, `safe_makedirs` and `extract`](utils/paths.md)) (`django/utils/_os.py:safe_join`).

## The exceptions

`django/core/exceptions.py` defines the exceptions its docstring calls global, many of them raised in one part of Django and caught in another. The exception classes that each model that is not abstract is given, raised when a lookup finds no row or more than one, derive from `ObjectDoesNotExist` and `MultipleObjectsReturned` ([`ModelBase`: a class statement becomes a model](models/metaclass.md)). `SuspiciousOperation` and its subclasses, `DisallowedHost` and `RequestDataTooBig` among them, mark what may be an attack. Raised inside the middleware chain, one of them becomes a 400 and is logged under `"django.security"`; `PermissionDenied` becomes a 403 and `BadRequest` a 400 ([How an exception becomes a response](handlers/exceptions.md)). `ImproperlyConfigured` says that a setting or the code is configured wrongly. `ValidationError` carries one error, a list of them, or a dictionary of lists by field name, each error with a message and a code ([Validation: `full_clean`, `cleaned_data` and the errors](forms/validation.md)). `EmptyResultSet` and `FullResultSet` are raised while a query is compiled, when a condition can match no row or every row ([The where clause: `build_filter`, `add_q` and `WhereNode`](sql/where.md)). `SynchronousOnlyOperation` is raised by a function marked with `async_unsafe`, such as `BaseDatabaseWrapper.connect`, when it is called in a thread where an event loop is running, unless the environment variable `"DJANGO_ALLOW_ASYNC_UNSAFE"` is set (`django/utils/asyncio.py:async_unsafe`). Each is in [Django's exceptions: `django.core.exceptions`](utils/exceptions.md).

## Deprecations and versions

Django removes a feature in two steps. A release deprecates it: the feature still works, and its use raises a warning whose class names the release in which it will be removed. A later release removes it (`docs/internals/release-process.txt`). At the pin there are two such classes, `RemovedInDjango2028Warning`, a `DeprecationWarning`, and `RemovedInDjango2029Warning`, a `PendingDeprecationWarning` (`django/utils/deprecation.py`). Python's default filters hide a `PendingDeprecationWarning` wherever it is raised, and a `DeprecationWarning` unless it is attributed to the module run as the main program; otherwise a warning of either class is seen only where a filter, such as the interpreter's `-W` option, shows it.

> **Changed in 6.2.** Following DEP 20, the releases that were to be Django 7.0 and 7.1 are Django 2028 and 2029, and the warning classes are renamed with them: RemovedInDjango70Warning became `RemovedInDjango2028Warning`, and RemovedInDjango71Warning became `RemovedInDjango2029Warning` (`docs/releases/6.2.txt`).

Two of the module's helpers decide how a deprecated feature warns. `warn_about_external_use` warns only when the code that used the feature is outside Django: it walks up the stack to that caller, and stays silent when the caller is Django's own code, so that one deprecated feature built on another does not set off a second warning (`django/utils/deprecation.py:warn_about_external_use`). `deprecate_posargs` lets a function make arguments keyword-only while still accepting them by position for a time, with a warning ([Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`](utils/deprecation.md)).

`django.VERSION` is a `VersionTuple`, at the pin `(6, 2, 0, "alpha", 0)`, and `django.__version__` the string `get_version` makes from it, here `"6.2.dev20260926051415"`: for an alpha of iteration 0 whose `django` package is in a git repository, `".dev"` and the time, in UTC, of the commit checked out there follow the number (`django/utils/version.py:get_version`). From Django 2028 a version has no minor number, and `VERSION` four parts, `(2028, 1, "final", 0)` for 2028.1; the attributes `VersionTuple.feature`, `VersionTuple.patch`, `VersionTuple.status` and `VersionTuple.iteration` count from the end, where the two forms agree, and reading the tuple by index past its second part is deprecated ([Django's version: `VersionTuple` and `get_version`](utils/version.md)).

## Where the other modules of `django/utils/` are told

| module | what it is for | told in |
|---|---|---|
| `django/utils/translation/`, `formats.py`, `dateformat.py`, `numberformat.py`, `timezone.py`, `timesince.py`, `dates.py` | translation, locale formats and time zones | [Internationalization and time zones](i18n.md) |
| `django/utils/html.py`, `safestring.py` | escaping and safe strings | [Autoescaping and safe strings](templates/autoescape.md) |
| `django/utils/http.py` | dates, ETags and URLs in HTTP | [The helpers in `django/utils/http.py`](http/helpers.md) |
| `django/utils/regex_helper.py` | reversing a regular expression | [Reversing a name](urls/reversing.md) |
| `django/utils/crypto.py` | secret keys, hashes and random strings | [Secret keys and `django.utils.crypto`](security/keys.md) |
| `django/utils/csp.py` | the Content Security Policy and its nonce | [Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](security/csp.md) |
| `django/utils/cache.py` | cache headers and conditional requests | [Cache headers and conditional requests: `django/utils/cache.py`](services/http-caching.md) |
| `django/utils/connection.py` | handlers of backends by alias | [Connections by alias: `DATABASES` and `ConnectionHandler`](backends/connections.md) |
| `django/utils/deconstruct.py` | `deconstructible`, by which a migration can write an object | [Serializing values: `serializer_factory` and `deconstruct`](migrations/serializer.md) |
| `django/utils/decorators.py` | `method_decorator` and middleware as decorators | [View decorators](views/decorators.md), [A middleware as a decorator](views/middleware-decorators.md) |
| `django/utils/log.py` | the logging configuration and its handlers | [Logging](startup/logging.md) |
| `django/utils/autoreload.py` | the development server's reloader | [The autoreloader](commands/autoreload.md) |
| `django/utils/termcolors.py` | a command's coloured output | [Running a command: `BaseCommand`](commands/running.md) |
| `django/utils/feedgenerator.py` | RSS and Atom feeds | [Feeds: `django.contrib.syndication` and the feed generator](contrib/feeds.md) |

*The modules of `django/utils/` that belong to another subsystem, and where each is told.*
