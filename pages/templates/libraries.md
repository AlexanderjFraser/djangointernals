---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Libraries: `Library`, custom tags and `{% load %}`

A **library** is a `Library`, a dictionary of tags and one of filters, kept in a module's variable `"register"`. The `DjangoTemplates` backend imports every such module of `django.templatetags` and of the installed applications when it is made, `{% load %}` copies a library into the parser of the one template being compiled, and `simple_tag`, `simple_block_tag` and `inclusion_tag` make a tag of an ordinary function.

The parser knows a tag or a filter only by the function its tables hold under that name ([From text to nodes: the lexer and the parser](compiling.md)). Libraries fill those tables, in one of two ways. A **builtin** library is added to every parser as it is made, so its tags and filters are in every template. Every other library the engine knows by a name, and it reaches a template only when that template says `{% load %}` with the name.

## Registering tags and filters on a `Library`

`Library` holds two dictionaries, `Library.tags` and `Library.filters`, and its methods are ways of filling them (`django/template/library.py:Library`). A module becomes a library by keeping one in a variable named `"register"`, the one name Django looks for: `import_library` imports a dotted path and returns the module's `"register"`, and raises `InvalidTemplateLibrary` when the import raises an `ImportError` or the variable is missing (`django/template/library.py:import_library`).

```python
# fleet/templatetags/fleet_tags.py
from django import template

register = template.Library()


@register.filter
def knots(value):
    return f"{value} kn"


@register.simple_tag
def berth(port, number):
    return f"{port.name}, berth {number}"
```

`Library.tag` registers a compile function as it is, under the name it is given or the function's own (`django/template/library.py:Library.tag`). `Library.filter` does the same for a filter, and copies the flags it is given, `is_safe=True`, `needs_autoescape=True` or `expects_localtime=True`, onto the function, where `FilterExpression.resolve` reads them ([Variables and filters: `FilterExpression` and `Variable`](variables.md)). It sets each twice, on the function registered and on the innermost function under its decorators, and the comment there says why: a decorator such as `stringfilter`, which turns a filter's first argument into a string, reads the flag from the innermost function (`django/template/library.py:Library.filter`, `django/template/defaultfilters.py:stringfilter`).

## How an engine finds its libraries

`DjangoTemplates.__init__` gathers the libraries before it makes its `Engine` (`django/template/backends/django.py:DjangoTemplates.__init__`). `get_template_tag_modules` looks in `django.templatetags` and then in the templatetags package of each installed application, in the order of `INSTALLED_APPS`. In each package it imports every module, subpackages included, and keeps those with a `"register"`; a module that cannot be imported stops the backend from being made, an import error raised again as `InvalidTemplateLibrary` (`django/template/backends/django.py:get_package_libraries`). A library's name is its module's path after the package: `"fleet_tags"` for the module above, `"charts.maps"` for a module in a subpackage (`django/template/backends/django.py:get_template_tag_modules`). `get_installed_libraries` makes a dictionary of the names and paths, and `DjangoTemplates.get_templatetag_libraries` updates it with the `"libraries"` option, so a name given there replaces an installed module's (`django/template/backends/django.py:DjangoTemplates.get_templatetag_libraries`).

> **Trap.** Two applications with a library of the same name do not settle it as their templates do. The dictionary is built in the order of `INSTALLED_APPS` and a later entry replaces an earlier one, so `{% load %}` finds the library of the application listed last, where of two templates of one name the first application's is found (`django/template/backends/django.py:get_installed_libraries`). The check `"templates.W003"` warns of a name several modules use ([Template engines: `TEMPLATES` and the backends](engines.md)).

`Engine.__init__` then imports them all, whether a template ever loads them or not: `Engine.template_libraries` maps each name to its `Library`, and `Engine.template_builtins` lists the three of `Engine.default_builtins` and then those of the `"builtins"` option (`django/template/engine.py:Engine.__init__`). An `Engine` made outside a backend knows by name only the libraries it is handed.

## `{% load %}`: a library enters one parser

A parser is made for each compile with the engine's libraries and builtins. It copies each builtin into its tables at once, in order, with `Parser.add_library`, a dictionary update, so a later library replaces an earlier one's tag or filter of the same name; the others it keeps by name, as `Parser.libraries` (`django/template/base.py:Parser.__init__`, `django/template/base.py:Parser.add_library`).

`{% load %}` does all its work in its compile function, `load` (`django/template/defaulttags.py:load`). It splits the tag on white space, so the names in it are words, never variables, looks each up with `find_library`, and hands the library to `Parser.add_library`; an unknown name is a `TemplateSyntaxError` that lists every name the engine knows (`django/template/defaulttags.py:find_library`). In the form `{% load berth knots from fleet_tags %}`, `load_from_library` first builds a new `Library` of only the tags and filters named (`django/template/defaulttags.py:load_from_library`). The `LoadNode` that `load` returns renders the empty string: by then the tag has done all it does.

The tables are read as each token is compiled, so what `{% load %}` brings is in force from that token to the end of the text, and nowhere else:

- **Not before it.** `{% berth port 4 %}{% load fleet_tags %}` fails with `"Invalid block tag on line 1: 'berth'. Did you forget to register or load this tag?"`, and a filter used early fails too, with `"Invalid filter: 'knots'"`, since a `FilterExpression` finds its filters as it is compiled.
- **Not by the tree.** A `{% load %}` inside `{% if %}` holds after `{% endif %}`, whatever the condition: the tables are the parser's, not a node's.
- **Not in another template.** Each template has a parser of its own, so a library that `"base.html"` loads is not loaded in a template that extends it or one it includes. A template that extends loads after its `{% extends %}`, which must be its first tag ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](inheritance.md)).
- **Over what came before.** A library loaded later replaces, for the rest of the template, a tag or filter of the same name, a builtin's included.

## Tags made from functions

A tag written by hand is a compile function and a node. `simple_tag`, `simple_block_tag` and `inclusion_tag` write both for a function that only computes something, and return the function unchanged, so Python can still call it (`django/template/library.py:Library.simple_tag`).

When the decorator runs, as its module is imported, it reads the function's signature. With `takes_context=True` the first parameter must be `"context"`, and it is struck from the list the template will fill; a function without one is refused there with a `TemplateSyntaxError`.

When a template is compiled, that compile function splits the token, takes off a final `"as"` and a name where the tag allows one, and matches the rest against the signature with `parse_bits` (`django/template/library.py:parse_bits`). A word `name=value` is a keyword argument, read by `token_kwargs`, and any other word a positional one. Each value is compiled as `{{ }}` compiles one, filters included. The arguments are checked here, once, and an argument the signature does not admit, or a required one left out, is a `TemplateSyntaxError`: `{% berth port %}` fails with `"'berth' did not receive value(s) for the argument(s): 'number'"`.

> **Changed in 6.1.** `parse_bits` no longer takes a flag for `takes_context=True`; the decorators strike `"context"` from the parameters they give it.

When the template renders, the node resolves each argument in the context and calls the function, with the context itself first under `takes_context=True` (`django/template/library.py:TagHelperNode.get_resolved_arguments`).

### `simple_tag`

`SimpleNode.render` returns what the function returned, passed through `conditional_escape` when the context autoescapes: with a ship named `<Beagle>`, `{% berth ship 4 %}` renders `"&lt;Beagle&gt;, berth 4"`, so markup must come back safe, from `format_html` for instance ([Autoescaping and safe strings](autoescape.md)). With `"as"` and a name, the value is set, unescaped, in the context's top dictionary, and the tag renders the empty string (`django/template/library.py:SimpleNode.render`); set inside `{% for %}`, it is gone after `{% endfor %}`.

### `simple_block_tag`

`simple_block_tag` makes a tag with a body. The function's first parameter must be `"content"`, or its second after `"context"`. The compile function parses the body up to the end tag, `{% endnotice %}` for `{% notice %}` unless `end_name=` names another, and keeps its nodes (`django/template/library.py:Library.simple_block_tag`). At each render the body is rendered in the same context and passed as the content; the rest is `SimpleNode.render`, escaping included (`django/template/library.py:SimpleBlockNode.get_resolved_arguments`).

> **Trap.** The content is a safe string, but a string formatted from it, by an f-string for instance, is not, and the whole output is then escaped: the body's markup, and its values a second time. With `return f"[{level}] {content}"`, `{% notice level="warn" %}Gale <b>{{ ship.name }}</b>{% endnotice %}` renders `"[warn] Gale &lt;b&gt;&amp;lt;Beagle&amp;gt;&lt;/b&gt;"`; with `return format_html("[{}] {}", level, content)`, `"[warn] Gale <b>&lt;Beagle&gt;</b>"`.

### `inclusion_tag`

`inclusion_tag` takes a template as well as the function, which returns a dictionary for it (`django/template/library.py:Library.inclusion_tag`). `InclusionNode.render` calls the function, fetches a template given by name or by a list of names from the engine of the template being rendered, and keeps it in the render context under the node, so that inside `{% for %}` it is fetched once for each render of the template around it, not once a turn (`django/template/library.py:InclusionNode.render`).

It renders in a context made by `BaseContext.new`, holding only the returned dictionary: none of the variables around the tag, and none of the context processors' values ([The context: `Context`, `RequestContext` and context processors](context.md)). The one exception is `"csrf_token"`, copied across when the outer context has it, because, the comment there says, inclusion tags are often used for forms and CSRF protection should be as simple as possible to use.
