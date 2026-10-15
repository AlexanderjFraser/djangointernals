---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Template errors and debug information

`TemplateDoesNotExist` and `TemplateSyntaxError`, the exceptions of `django/template/exceptions.py`, and the debug information the Django template language puts on an exception when the engine's `"debug"` option is on: the template, the line and the failing tag, at compile time and at render time.

An error in a template is raised by Python code, and its traceback names no template, line or tag. The template system puts what it knows on the exception. A `TemplateDoesNotExist` carries the places that were tried. With `"debug"` on, an exception from the parser or from a node carries a dictionary, in an attribute named `"template_debug"`, that places the failure in the source. The debug page lists the first and shows the second as the template's lines with the failing tag marked ([The debug pages and `ExceptionReporter`](../views/debug.md)). In a `DjangoTemplates` backend `"debug"` follows `settings.DEBUG` unless the `"OPTIONS"` set it ([Template engines: `TEMPLATES` and the backends](engines.md)).

## `TemplateDoesNotExist` and what was tried

`TemplateDoesNotExist` keeps three optional arguments as attributes: `tried`, a list of pairs of an origin and the reason it failed; `backend`, the backend that raised it; and `chain`, the exceptions of several engines. `TemplateSyntaxError` adds nothing to `Exception` (`django/template/exceptions.py:TemplateDoesNotExist`).

The list is built a level at a time. The base loader records each origin it tries as `"Source does not exist"`, or as `"Skipped to avoid recursion"` when an `{% extends %}` asked it to skip that one (`django/template/loaders/base.py:Loader.get_template`). `Engine.find_template` joins its loaders' lists (`django/template/engine.py:Engine.find_template`), and the `DjangoTemplates` backend raises a copy that names the backend (`django/template/backends/django.py:reraise`). `get_template` and `select_template` of `django/template/loader.py` ask the engines in turn and raise an exception of their own whose `chain` holds each engine's (`django/template/loader.py:get_template`). The debug page lists the chain, or the exception alone (`django/views/debug.py:ExceptionReporter.get_traceback_data`).

A list can be missing; the page then says the engine provided none. The `Jinja2` backend gives none when it turns a `jinja2.TemplateNotFound` into a `TemplateDoesNotExist` (`django/template/backends/jinja2.py:Jinja2.get_template`). `Engine.select_template`, which `{% include %}` uses, raises one holding the names alone (`django/template/engine.py:Engine.select_template`). And the cached loader with `"debug"` off keeps only the class for a missing name, and on later requests raises a new one holding the name alone; with `"debug"` on it keeps a copy, list included ([Finding a template: `Engine` and the loaders](loaders.md)) (`django/template/loaders/cached.py:Loader.get_template`).

> **Trap.** For a partial the template does not define, `Engine.get_template` gives as `tried` a list holding the template's name, a string where the page expects a pair (`django/template/engine.py:Engine.get_template`). The page takes the name's first letter for the origin and its second for the reason: for `"fleet/port_list.html#ship-row"` the text report printed `* :  (l)`.

## Positions: `DebugLexer` and the token

A failure is placed by a token. `Token.position`, the token's start and end offsets in the source, is set only by `DebugLexer`, which its docstring calls slower than the default lexer, and `Template.compile_nodelist` uses it only when `"debug"` is on (`django/template/base.py:DebugLexer.tokenize`). Both lexers count lines, in `Token.lineno`. `Parser.error` puts the token on the exception, in an attribute named `"token"`, unless one is there, so that the innermost tag is blamed (`django/template/base.py:Parser.error`); `Parser.extend_nodelist` sets the token and the origin on each node (`django/template/base.py:Parser.extend_nodelist`).

`Template.get_exception_info` turns an exception and a token into the dictionary. It cuts the line that holds the token into `"before"`, `"during"` and `"after"`. It keeps up to ten lines either side as `"source_lines"`, and adds `"line"`, `"message"` (the exception's first argument) and `"name"` (the origin's) (`django/template/base.py:Template.get_exception_info`).

## At compile time: `compile_nodelist`

`Template.compile_nodelist` catches what the parser raises and, with `"debug"` on, adds the dictionary (`django/template/base.py:Template.compile_nodelist`). Then, `"debug"` or not, it prefixes a `TemplateSyntaxError`'s message with `"Template: "`, the origin's name and a comma, unless the origin's name is `UNKNOWN_SOURCE`, as for a template made from a string. The message as raised stays in the dictionary and in an attribute named `"raw_error_message"`, which the debug page shows as the exception's value (`django/views/debug.py:ExceptionReporter.get_traceback_data`). This template misspells a filter:

```text
{# fleet/port_detail.html #}
<h1>{{ port.name }}</h1>
<ul>{% for ship in ships %}<li>{{ ship.name|uper }}</li>{% endfor %}</ul>
```

Loaded with `"debug"` on by `django.template.loaders.locmem.Loader`, which names an origin by the template's name where the filesystem loader uses the file's full path, it raised a `TemplateSyntaxError` (`django/template/loaders/locmem.py:Loader.get_template_sources`, `django/template/loaders/filesystem.py:Loader.get_template_sources`):

```text
str(exc)                         "Template: fleet/port_detail.html, Invalid filter: 'uper'"
exc.template_debug["line"]       3
exc.template_debug["during"]     '{{ ship.name|uper }}'
```

The error came while `{% for %}` parsed its body; `"during"` holds the variable, not the `for` tag.

## At render time: `render_annotated`

`NodeList.render` calls `Node.render_annotated` on each node, which calls `Node.render` and, if that raises while `"debug"` is on, annotates the exception on its way out (`django/template/base.py:Node.render_annotated`). Two templates are current in a render: `Context.template`, the one the render began with, whose engine's `"debug"` decides; and `RenderContext.template`, the one whose tree is being walked, whose source a token's offsets index ([Rendering: nodes and the render context](rendering.md)).

As the exception climbs through the nodes' `render_annotated`, the innermost records its node as the culprit, in an attribute named `"_culprit_node"`, and the first whose render context's template has the culprit's origin builds the dictionary from that template and the culprit's token. No later one replaces it.

The test of origins matters under inheritance: `ExtendsNode.render` walks the parent's tree with the parent as the render context's template, and the child's blocks render inside that walk (`django/template/loader_tags.py:ExtendsNode.render`). A child's token read against the parent's source would land on the wrong line; a failure in a child's block is passed over until the exception reaches the `ExtendsNode`, which renders under the child. An included template pushes itself as it renders, and a failure in it is placed at once ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](inheritance.md)).

`copy_exception` copies `"template_debug"` with the declared attributes: a `TemplateDoesNotExist` from an `{% include %}` of a missing template is annotated at the tag before the backend's wrapper raises a copy naming the backend (`django/template/backends/django.py:copy_exception`).

A partial rendered by `{% partial %}` or by name is a `PartialTemplate`, which holds no text. `PartialTemplate.get_exception_info` loads the whole template again through the origin's loader and asks it (`django/template/base.py:PartialTemplate.get_exception_info`, [Template partials: `{% partialdef %}` and `{% partial %}`](partials.md)). The origin of a template made from a string has no loader: with `"debug"` on, an error in one of its partials rendered by `{% partial %}` came out as an `AttributeError`, with the original as its `__context__`.

The `Jinja2` backend builds the dictionary from a Jinja2 syntax error met as it loads a template by name or renders one, and puts it on a `TemplateSyntaxError` raised from it; other errors in a Jinja2 template get none (`django/template/backends/jinja2.py:Jinja2.get_template`, `django/template/backends/jinja2.py:Template.render`, `django/template/backends/jinja2.py:get_exception_info`).

## Aids that do not need `"debug"`

The variable of a `{{ … }}` that fails to resolve takes the engine's `"string_if_invalid"`, by default the empty string. Set to another string, it shows each such failure, with the variable's text in place of a `%s` (`django/template/base.py:FilterExpression.resolve`, [Variables and filters: `FilterExpression` and `Variable`](variables.md)). And a lookup that ends in an exception, silenced later or not, is logged at the debug level on the `"django.template"` logger, with the traceback and the name of the template the render began with (`django/template/base.py:Variable._resolve_lookup`).

`{% debug %}` prints the context's dictionaries, top first, and `sys.modules`, pretty-printed and escaped. It prints nothing unless `settings.DEBUG` is on, whatever the engine's option (`django/template/defaulttags.py:DebugNode.render`).
