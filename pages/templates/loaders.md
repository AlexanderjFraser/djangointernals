---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Finding a template: `Engine` and the loaders

`Engine` holds the configuration of the Django template language, and `Engine.get_template` turns a name such as `"fleet/port_detail.html"` into a compiled template. The engine asks its loaders in order; a loader proposes the places the template might be, reads the first that exists and compiles it; and the cached loader, which by default wraps the others, keeps what they find.

A template is asked for by a name relative to a directory: with the default loaders, the project's own in `"DIRS"`, then, with `"APP_DIRS"`, each installed application's templates directory, so that a project overrides an application's template with a file of the same name. A **loader** knows where to look: for a name it yields an **origin** for each place the template might be, and reads them until one exists.

## The options of `Engine.__init__`

`Engine.__init__` gives every option a default, so an `Engine` can be made with no arguments (`django/template/engine.py:Engine.__init__`). The `DjangoTemplates` backend makes one from an entry of `TEMPLATES`, with `"DIRS"` and `"APP_DIRS"` as its first arguments and each key of `"OPTIONS"` as the keyword of that name, after setting defaults of its own, `"debug"` from `settings.DEBUG` among them, and adding to `"libraries"` every library of `django.templatetags` and the installed applications ([Template engines: `TEMPLATES` and the backends](engines.md)).

| option | default | used for |
|---|---|---|
| `"DIRS"` | `[]` | the filesystem loader |
| `"APP_DIRS"` | `False` | the default loaders |
| `"loaders"` | `None` | the loaders |
| `"debug"` | `False` | debug data; the cached loader's misses |
| `"file_charset"` | `"utf-8"` | reading files |
| `"string_if_invalid"` | `""` | a variable that fails |
| `"autoescape"` | `True` | the contexts made for it |
| `"context_processors"` | `[]` | `RequestContext` |
| `"libraries"` | `{}` | `{% load %}` |
| `"builtins"` | `[]` | every template |

Without `"loaders"`, `Engine.__init__` writes the list: one entry, the cached loader, given as its argument the filesystem loader and, if `"APP_DIRS"` is true, the application directories loader after it. That is all `"APP_DIRS"` does in the engine, and a true `"APP_DIRS"` with `"loaders"` is refused: `ImproperlyConfigured`, `"app_dirs must not be set when loaders is defined."`.

The libraries, unlike the loaders, are imported as the engine is made: `Engine.template_builtins` holds the `Library` of each module of `Engine.default_builtins` and `"builtins"`, and `Engine.template_libraries` that of each entry of `"libraries"`, by name. A library is a module's registry of tags and filters, from which a parser takes them ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)).

## Making the loaders

`Engine.template_loaders` makes the loaders from `Engine.loaders` the first time it is read, not when the engine is made, and keeps them (`django/template/engine.py:Engine.template_loaders`). Each entry goes through `Engine.find_template_loader`. A string is the dotted path of a loader class, called with the engine; a tuple or a list is a path followed by arguments, which the class receives after the engine; anything else raises `ImproperlyConfigured` (`django/template/engine.py:Engine.find_template_loader`).

Arguments are a loader's own configuration: directories for the filesystem loader, a dictionary of templates for the locmem loader, and for the cached loader a list of loader entries, which it makes into loaders through `Engine.get_template_loaders` (`django/template/loaders/cached.py:Loader.__init__`). So the default list is no special case.

## Looking a name up

`Engine.find_template` is the search (`django/template/engine.py:Engine.find_template`). It asks each loader in turn and returns the first template found, with its origin. A loader that finds nothing raises `TemplateDoesNotExist` with `TemplateDoesNotExist.tried`, pairs of an origin and why it failed; `find_template` gathers the lists and, if every loader fails, raises a new `TemplateDoesNotExist` with the whole. Any other error ends the search: a file that exists and does not compile raises its `TemplateSyntaxError`, and no later candidate is tried. Origins to skip come from `{% extends %}`, those of the templates already in its chain, so that a template can extend another of its own name further down ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](inheritance.md)).

`Engine.get_template` is what the backend calls (`django/template/engine.py:Engine.get_template`). It splits the name at its first `"#"` and looks up what comes before; when something comes after, it returns the partial of that name instead ([Template partials: `{% partialdef %}` and `{% partial %}`](partials.md)).

`Engine.select_template` tries a list of names with `Engine.get_template` and returns the first found; if none is, its `TemplateDoesNotExist` names what was missing and its `tried` is empty (`django/template/engine.py:Engine.select_template`). `Engine.render_to_string`, which its docstring says is for use in Django's test suite, renders what either returns (`django/template/engine.py:Engine.render_to_string`).

`Engine.from_string` compiles a string with no loader: the template has no name, its origin is named `"<unknown source>"`, and nothing is cached (`django/template/engine.py:Engine.from_string`).

## The origin of a template

`django/template/base.py:Origin` holds `Origin.name`, where the source is (a path, or for the locmem loader the template name); `Origin.template_name`, the name asked for; and `Origin.loader`, the loader that proposed it, named by `Origin.loader_name`. A compiled template keeps its origin as `Template.origin`.

Two origins are equal when their names and their loaders are, whatever name each was asked for by (`django/template/base.py:Origin.__eq__`). So a file already in a chain of `{% extends %}` is skipped, but the same path proposed by another loader is another origin.

## What a loader does

`django/template/loaders/base.py:Loader.get_template` searches one loader's candidates, the origins `Loader.get_template_sources` yields, in order. An origin to skip is recorded as `"Skipped to avoid recursion"`; any other is read with `get_contents`, and a `TemplateDoesNotExist` from that is recorded as `"Source does not exist"`. The first origin read is compiled on the spot into a `django/template/base.py:Template`; if none is, the loader raises `TemplateDoesNotExist` with its records.

A loader thus supplies `get_template_sources`, which reads nothing, and `get_contents`, which reads; the base class declares only the first, raising `NotImplementedError`. Its `Loader.reset` does nothing; a loader that keeps state empties it there.

## The filesystem, application directories and locmem loaders

`django/template/loaders/filesystem.py:Loader` searches the directories it was given, or else `Engine.dirs`. It joins the name to each with `safe_join`, which raises `SuspiciousFileOperation` when the normalised path lies outside the directory, and the directory is skipped, since, a comment says, the path might lie inside another (`django/template/loaders/filesystem.py:Loader.get_template_sources`). `Loader.get_contents` opens the path with `Engine.file_charset` and turns `FileNotFoundError` into `TemplateDoesNotExist`: whether a file exists is learnt by opening it.

`django/template/loaders/app_directories.py:Loader` is the filesystem loader with another `Loader.get_dirs`: `get_app_template_dirs("templates")`, the templates directory of each installed application that has one, in the order of `INSTALLED_APPS`, cached after the first call (`django/template/utils.py:get_app_template_dirs`). So the first application with a template of a name wins, and in the default list the directories of `"DIRS"`, searched before, win over every application.

`django/template/loaders/locmem.py:Loader` takes a dictionary of sources by name, and yields one origin, named by the template name.

## The cached loader

`django/template/loaders/cached.py:Loader` is a loader of loaders. Its `Loader.get_template_sources` chains its inner loaders', and its `Loader.get_contents` hands each origin back to the loader that proposed it, so the base class's search runs over all their candidates as one sequence, and one list records them all. Its own `Loader.get_template` keeps each answer in a dictionary, `Loader.get_template_cache`, under a key made from the name (`django/template/loaders/cached.py:Loader.get_template`).

A found template is stored, and later lookups with the same key get that compiled object, from any request or thread ([Rendering: nodes and the render context](rendering.md)). A missing template is stored too, but no other failure: after a `TemplateSyntaxError` the next lookup compiles the file again.

What a miss leaves depends on `"debug"`, and the docstring gives the reason, citing ticket 26306: often many templates asked for are missing, so memory is a concern. With `"debug"` off the cache stores the class `TemplateDoesNotExist` itself, and a later miss raises a new instance, its `TemplateDoesNotExist.tried` empty. Two lookups of a missing name, with `"debug"` off and fleet the one application, gave:

```text
first miss
  django.template.loaders.filesystem.Loader       harbour/templates/fleet/ship_list.html  Source does not exist
  django.template.loaders.app_directories.Loader  fleet/templates/fleet/ship_list.html    Source does not exist
second miss
  tried is empty
```

With `"debug"` on the cache stores a copy made by `copy_exception`, which keeps `tried` and the debug data but drops `__traceback__`, `__context__` and `__cause__`: they reach up the call chain, and caching them would leak memory. A later miss raises a copy of the copy.

The key is the name alone unless there are origins to skip (`django/template/loaders/cached.py:Loader.cache_key`). Then those found under the same name are added, hashed with SHA-1, and no others. A template that ends several chains, as when x extends a, which extends another a, and y does the same, is asked for in each with the first a to skip, and so, the docstring says, is parsed and cached once.

`Loader.reset` empties the dictionary. A stored template's file is not looked at again, so an edit is read only after a reset or by a new engine.

## When a template changes

The development server's autoreloader reaches the loaders through `django/template/autoreload.py`. `get_template_directories` collects `Engine.dirs` of every `DjangoTemplates` backend and, leaving out directories inside Django, what `get_dirs` gives for each of its loaders that has it (`django/template/autoreload.py:get_template_directories`). When a file that is not Python changes under one of them, `template_changed` has `reset_loaders` reset every loader of those engines and of the default form renderer's, and answers true, so the server does not restart (`django/template/autoreload.py:template_changed`, `django/template/autoreload.py:reset_loaders`). A loader without `get_dirs`, such as the locmem loader, adds nothing to watch ([The autoreloader](../commands/autoreload.md)).
