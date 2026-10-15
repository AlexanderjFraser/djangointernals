---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Template partials: `{% partialdef %}` and `{% partial %}`

A template partial is a named fragment of a template. `{% partialdef %}` defines it while the template is compiled, `{% partial %}` renders it wherever the template asks, and a name such as `"fleet/port_detail.html#ship_row"`, given to `Engine.get_template` or anything that loads through it, stands for the fragment alone, a `PartialTemplate`.

A page often repeats one fragment, a row for each ship, and a view sometimes needs the fragment alone, to replace one row. Without partials it is a file of its own, which the page includes and the view loads; a partial keeps it in the page's file, under a name:

```text
{# fleet/port_detail.html #}
<h1>{{ port.name }}</h1>
<ul>{% for ship in ships %}{% partial ship_row %}{% endfor %}</ul>
{% partialdef ship_row %}<li>{{ ship.name }} ({{ ship.tonnage }} t)</li>{% endpartialdef %}
```

Rendered with Valletta and two ships, the list comes out as `"<ul><li>Endeavour (368 t)</li><li>&lt;Beagle&gt; (235 t)</li></ul>"` and the definition as nothing. Given `"fleet/port_detail.html#ship_row"` and the second ship, `render_to_string` returns the one row, `"<li>&lt;Beagle&gt; (235 t)</li>"`.

> **Changed in 6.0.** Template partials are new; the release notes link to a migration guide from the third-party django-template-partials.

## `{% partialdef %}`: a partial made at compile time

`partialdef_func`, the compile function of `{% partialdef %}`, reads a name and, optionally, `"inline"`, parses the nodes up to `{% endpartialdef %}`, and wraps them in a `PartialTemplate` with the parser's origin (`django/template/defaulttags.py:partialdef_func`). It files the partial under its name in a dictionary at `"partials"` in `Parser.extra_data`, which the parser keeps for whatever a compile function wants the compiled template to hold; a second definition of the name in one template is refused. When the parse succeeds, `Template.compile_nodelist` keeps the parser's `extra_data` whole as `Template.extra_data` (`django/template/base.py:Template.compile_nodelist`).

What stays in the tree is a `PartialDefNode` holding the same node list. It renders nothing unless the tag said `"inline"`, and then renders the fragment in place (`django/template/defaulttags.py:PartialDefNode`). The parser makes the partial, so it exists even when its definition stands inside an `{% if %}` whose condition is false.

## `{% partial %}`: the name looked up at render time

`partial_func` does not look the name up when it compiles `{% partial ship_row %}`. It gives the `PartialNode` a `DeferredSubDict` over the parser's extra data and the key `"partials"`, which looks up both keys only when it is indexed, so that, as its docstring says, later updates are seen (`django/template/defaulttags.py:partial_func`, `django/utils/datastructures.py:DeferredSubDict`). That lets a template use a partial above its definition, before any dictionary of partials exists.

At render time `PartialNode.render` renders the `PartialTemplate` with the context as it stands, so the fragment sees what is in scope at the tag, the loop's ship included. The tag takes the name alone: a `{% with %}` around it names a value. A name the template does not define is a `TemplateSyntaxError`, raised at render: the partial "is not defined in the current template" (`django/template/defaulttags.py:PartialNode.render`). The current template is the one whose parser compiled the tag, so a child of `{% extends %}` reaches its own partials and not its parent's.

## `PartialTemplate`

A `PartialTemplate` gives a partial the shape of a compiled template (`django/template/base.py:PartialTemplate`), so that, its docstring says, it can bind a context. It holds the node list, the origin of the template that defines it, the partial's name, and, when the engine's `"debug"` option is on, where its definition starts and ends in that template's source, from the positions `DebugLexer` gives tokens. `PartialTemplate.render` repeats `Template.render`: it pushes a level onto the render context and, if the context is bound to no template, binds it to the partial (`django/template/base.py:PartialTemplate.render`, [Rendering: nodes and the render context](rendering.md)).

> **Trap.** So each `{% partial %}` renders on a fresh level of the render context, and what a node keeps there does not outlast it. A `{% cycle "odd" "even" %}` in a partial rendered for each ship gives `"odd"` every time; written in the loop's body, it alternates.

A partial keeps no source of its own. `PartialTemplate.source`, and `PartialTemplate.get_exception_info`, which gives an error raised during `PartialTemplate.render` its excerpt for the debug page, fetch the whole template again from the origin's loader and work on its source (`django/template/base.py:PartialTemplate.get_exception_info`, [Template errors and debug information](debugging.md)). The source is the text from `{% partialdef %}` to the end of `{% endpartialdef %}`, and is empty, with a `RuntimeWarning`, when `"debug"` is off. The origin's loader is the one that read the file: under the cached loader, the loader inside it, which reads and compiles the file again.

> **Trap.** A template made from a string has an origin with no loader. With `"debug"` on, an error raised while `{% partial %}` renders one of its partials ends as an `AttributeError`, raised as the partial looks for that loader, in place of the error itself.

## Loading a partial by name

`Engine.get_template` splits a name at its first `"#"`. It finds and compiles the part before as any template, and if there is a part after, returns the `PartialTemplate` filed under it in `Template.extra_data` in place of the template (`django/template/engine.py:Engine.get_template`). A partial the template does not define is a `TemplateDoesNotExist` with the partial's name for its message and the template's as all it tried. Before returning a partial the method sets the engine on it: the parser gives it none, and rendering reads the engine from the template a context is bound to, for, among other things, the context processors and the `"debug"` option (`django/template/context.py:RequestContext.bind_template`, `django/template/base.py:Node.render_annotated`).

The form works wherever a name reaches `Engine.get_template`: in `Engine.select_template`, which calls it on the names in turn until one loads and is what `{% include %}` loads through (`django/template/loader_tags.py:IncludeNode.render`); and in the `DjangoTemplates` backend, which wraps a partial as it wraps a template (`django/template/backends/django.py:DjangoTemplates.get_template`), and with it `render_to_string`, the `render` shortcut and `TemplateResponse`. `{% extends %}` does not: it calls `Engine.find_template`, which looks for a file named with the whole name, `"#"` and all (`django/template/loader_tags.py:ExtendsNode.find_template`). The cached loader keeps a template under the part before `"#"`, so a template loaded whole and its partials loaded by name share one compiled template (`django/template/loaders/cached.py:Loader.get_template`).
