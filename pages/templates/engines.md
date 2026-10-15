---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Template engines: `TEMPLATES` and the backends

`django.template.engines`, an `EngineHandler`, makes a template backend, a subclass of `BaseEngine`, for each entry of the `TEMPLATES` setting the first time it is asked for. `get_template`, `select_template` and `render_to_string`, of `django.template.loader`, ask the backends in turn and gather their failures into one `TemplateDoesNotExist`. Django ships three: `DjangoTemplates`, which holds an `Engine`, one for Jinja2, and `TemplateStrings`.

A project may use more than one template language, and code that renders a page has only a template's name and a dictionary. A backend is the contract between them: made from its entry of `TEMPLATES`, it returns a template for a name or raises `TemplateDoesNotExist`, and the template's `render` takes a dictionary and, optionally, the request.

```text figure=the-engines
TEMPLATES: two entries, each with "DIRS" and "APP_DIRS": True
    "BACKEND": "django.template.backends.django.DjangoTemplates"
    "BACKEND": "django.template.backends.jinja2.Jinja2"

engines: each backend made at the first request for its name
  "django"  ->  DjangoTemplates
                  engine: an Engine
                    its loaders: the cached loader, holding
                      the filesystem loader: the directories of DIRS
                      the application directories loader: each application's "templates"
  "jinja2"  ->  Jinja2
                  env: a Jinja2 Environment
                    its loader: a FileSystemLoader over DIRS and each application's "jinja2"
```

*What `engines` makes of two entries of `TEMPLATES`: under each name, a backend holding its language's own object.*

## The entries of `TEMPLATES`

`EngineHandler.templates` reads the setting at its first use and keeps a dictionary from each entry's **name** to the entry with its defaults filled in (`django/template/utils.py:EngineHandler.templates`). Only `"BACKEND"`, the dotted path of the backend's class, is required. `"DIRS"` defaults to an empty list, `"APP_DIRS"` to false, `"OPTIONS"` to an empty dictionary, and `"NAME"` to the last part of the backend's module path: `"django"` for `DjangoTemplates`. An entry whose `"BACKEND"` is missing or has no dot is refused with `ImproperlyConfigured`, as are two entries with one name, such as two `DjangoTemplates` entries without a `"NAME"`.

## `engines`, and a backend's first use

`engines["django"]` returns the backend already made under that name, or finds the entry, copies it, takes `"BACKEND"` out, imports that class and calls it with the rest, and keeps the backend (`django/template/utils.py:EngineHandler.__getitem__`). A name with no entry raises `InvalidTemplateEngineError`, an `ImproperlyConfigured`. `EngineHandler.all` returns every backend in the setting's order, making those not yet made.

> **Why.** A backend that fails to import or initialise is not kept, so the next request for its name takes `"BACKEND"` out of the same entry again: hence the copy (ticket 24265).

## `get_template`, `select_template` and `render_to_string`

`get_template` asks each backend for the name in the order of `TEMPLATES` and returns the first template it gets (`django/template/loader.py:get_template`). `select_template` does the same for a list of names, asking every backend for the first name before any for the second, and refuses a single string with a `TypeError` (`django/template/loader.py:select_template`). `render_to_string` calls `select_template` for a list or tuple and `get_template` otherwise, and renders the template with the dictionary and the request (`django/template/loader.py:render_to_string`); `django.shortcuts.render` puts the result in a response ([The shortcuts](../views/shortcuts.md)). Given `using="jinja2"`, they ask only that backend; otherwise they take `EngineHandler.all`, which makes every backend not yet made (`django/template/loader.py:_engine_list`).

## `BaseEngine`: what a backend is

`BaseEngine.__init__` keeps `"NAME"`, `"DIRS"` and `"APP_DIRS"` and refuses any other key with `ImproperlyConfigured`; Django's backends take `"OPTIONS"` out first, so what is refused is a key such as `"DIR"` for `"DIRS"` (`django/template/backends/base.py:BaseEngine.__init__`). A backend must provide `BaseEngine.get_template` and may provide `BaseEngine.from_string`. `BaseEngine.check` returns no messages; the system check `check_templates` calls it on every backend (`django/core/checks/templates.py:check_templates`) ([The system checks](../commands/checks.md)).

`BaseEngine.template_dirs` and `BaseEngine.iter_template_filenames` are there, the class's comment says, to minimize code duplication and security issues in third-party backends. The first is the directories of `"DIRS"`, then, with `"APP_DIRS"`, each installed application's subdirectory named by `BaseEngine.app_dirname` (`"templates"`, `"jinja2"` and `"template_strings"` for Django's three), which raises `ImproperlyConfigured` unless the backend overrides it (`django/template/backends/base.py:BaseEngine.template_dirs`). The second joins each directory with the name through `safe_join`, skipping a join that lands outside it, to avoid directory traversal attacks, its docstring says (`django/template/backends/base.py:BaseEngine.iter_template_filenames`). `DjangoTemplates` uses neither, and leaves the search to its `Engine`'s loaders.

## `DjangoTemplates`

`DjangoTemplates.__init__` turns an entry into an `Engine` (`django/template/backends/django.py:DjangoTemplates.__init__`). In a copy of `"OPTIONS"` it fills in `"autoescape"` as `True`, `"file_charset"` as `"utf-8"` and `"debug"` as `settings.DEBUG` is when the backend is made, where an `Engine` made directly has `debug=False`. It replaces `"libraries"` with every library of `django.templatetags` and the installed applications, the option's own added over them ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)). Each option goes to `Engine` as a keyword argument, so an unknown one is a `TypeError`, and one left out takes `Engine`'s default: for `"loaders"`, the cached loader around the filesystem loader, which searches `"DIRS"`, and, with `"APP_DIRS"`, the application directories loader, which searches each application's `"templates"` ([Finding a template: `Engine` and the loaders](loaders.md)). `DjangoTemplates.check` reports a `"string_if_invalid"` that is not a string, `"templates.E002"`, and one library name given to two modules, `"templates.W003"` (`django/template/backends/django.py:DjangoTemplates.check`).

`DjangoTemplates.get_template` wraps what `Engine.get_template` returns, a compiled `django/template/base.py:Template` or, for a name such as `"fleet/port_detail.html#ship_row"`, a `PartialTemplate`, in the backend's `django/template/backends/django.py:Template`, which keeps the backend and passes `origin` through. Its `render` has `make_context` make a `Context` of the dictionary, or a `RequestContext` given the request, with the engine's `"autoescape"`; a `Context` passed instead is refused (`django/template/backends/django.py:Template.render`, `django/template/context.py:make_context`) ([The context: `Context`, `RequestContext` and context processors](context.md)).

## `TemplateDoesNotExist` across loaders and backends

A failed lookup should show every place searched, though no one object searched them all. `TemplateDoesNotExist` carries, besides its message, `tried`, pairs of an origin and why it did not serve; `backend`; and `chain`, other such exceptions (`django/template/exceptions.py:TemplateDoesNotExist`). `Engine.find_template` raises one with every loader's `tried` (`django/template/engine.py:Engine.find_template`). `DjangoTemplates.get_template` raises it again through `reraise`, as a copy that names the backend, raised from the original, and the wrapper's `render` does the same for one raised while rendering, as by `{% include %}` (`django/template/backends/django.py:reraise`). `get_template` of `django.template.loader` then raises a last one with each backend's exception in `chain`. With the figure's entries:

```text
TemplateDoesNotExist('fleet/missing.html'), backend None, tried []
  chain[0]: backend 'django', tried:
      proj/templates/fleet/missing.html: Source does not exist
      apps/fleet/templates/fleet/missing.html: Source does not exist
  chain[1]: backend 'jinja2', tried []
```

`copy_exception` makes the copy: the same class, message, `tried` and `chain`, the backend it is given or else the original's, and any debug data, but not the original's traceback, context or cause, so that, its docstring says, it can be kept around; the cached loader keeps such copies when `"debug"` is on (`django/template/backends/django.py:copy_exception`, `django/template/loaders/cached.py:Loader.get_template`). The debug page lists `chain` by backend ([The debug pages and `ExceptionReporter`](../views/debug.md)).

## Jinja2

The Jinja2 backend keeps for itself the options `"environment"`, the dotted path of the environment's class, `"jinja2.Environment"` unless given, and `"context_processors"` (`django/template/backends/jinja2.py:Jinja2.__init__`). The rest go to the environment, with Django's defaults: `"loader"`, a FileSystemLoader over `template_dirs`; `"autoescape"`, `True`; `"auto_reload"`, `settings.DEBUG`; and `"undefined"`, Jinja2's DebugUndefined if `settings.DEBUG` is true and its Undefined if not. `Jinja2.get_template` turns Jinja2's TemplateNotFound into a `TemplateDoesNotExist` with no `tried`, and its syntax error into Django's `TemplateSyntaxError` with debug data (`django/template/backends/jinja2.py:Jinja2.get_template`) ([Template errors and debug information](debugging.md)).

Its template's origin is the module's own `Origin`, holding only the file name and the template's name (`django/template/backends/jinja2.py:Template.__init__`). Its `render` works on the dictionary it is given: with a request, it sets `"request"`, `"csrf_input"`, the hidden field for the CSRF token, marked safe, and `"csrf_token"`, the last two lazy, so the token is fetched only if used; then it updates the dictionary with each context processor's (`django/template/backends/jinja2.py:Template.render`).

> **Trap.** Where the view and a context processor give one name, the view's value wins under `DjangoTemplates` and the processor's under the Jinja2 backend, which also leaves the view's dictionary changed.

## `TemplateStrings`

`TemplateStrings` shows how little the contract asks (`django/template/backends/dummy.py:TemplateStrings`). It takes no options, reads the first file of `iter_template_filenames` that exists, and returns a template of the module's own subclass of `string.Template`, whose `render` escapes every value with `conditional_escape`, adds `"csrf_input"` and `"csrf_token"` given a request, and leaves a placeholder with no value as written (`django/template/backends/dummy.py:Template.render`).

## `Engine.get_default`

A `django/template/base.py:Template` made from a string alone asks `Engine.get_default` for an engine: the `Engine` of the first `DjangoTemplates` in `engines`, or `ImproperlyConfigured` if there is none. The answer is cached (`django/template/engine.py:Engine.get_default`). Its docstring says it exists for historical APIs that rely on an implicitly configured engine.
