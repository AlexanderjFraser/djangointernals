---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`

`{% extends %}` and `{% block %}` let a template be written as changes to another, and `{% include %}` renders one template inside another. All three are tags of `django.template.loader_tags`, and both kinds of composition happen as the page renders: an `ExtendsNode` renders its parent's tree with the most derived version of each block, taken from a `BlockContext`, and an `IncludeNode` renders a second template where the tag stands.

The pages of a site share a frame, and some share fragments: a port's page and a ship's page differ only in the middle, and a list of ships prints the same row for each. Inheritance gives the frame: a page names its parent and supplies only the blocks it changes. Inclusion gives the fragment. Neither joins text: each template is compiled on its own, and nodes do the joining each time a page renders (`django/template/loader_tags.py`).

## Compiling a child template

`do_extends`, the compile function of `{% extends %}`, takes one argument and compiles it as a filter expression, so the parent may be a literal or a variable. It then parses with no end tag to stop at, and everything after the tag, to the end of the file, becomes the node list of one `ExtendsNode` (`django/template/loader_tags.py:do_extends`). The node never renders that list. What it keeps from it is `ExtendsNode.blocks`, every `BlockNode` in the list by name, found when the node is made through the node lists each node names in `Node.child_nodelists`: at any depth, but not inside a `simple_block_tag`, whose node names none (`django/template/loader_tags.py:ExtendsNode.__init__`, `django/template/base.py:Node.get_nodes_by_type`).

`ExtendsNode.must_be_first` is true, and a node that must be first is refused in a node list that already holds anything but text: before `{% extends %}` may stand text and `{# … #}` comments, which make no node, but no variable and no other tag, `{% load %}` included (`django/template/base.py:Parser.extend_nodelist`). A second `{% extends %}` is refused. `do_block` keeps on the parser the block names it has met and refuses one a second time in a template; `{% endblock %}` may repeat the block's name, and any other name is an error (`django/template/loader_tags.py:do_block`).

> **Trap.** In a child template only the text before `{% extends %}` and the blocks reach the page. Text after the tag and outside every block is never written. A `{% block %}` inside an `{% if %}` that is false still replaces the parent's, and a `{% with %}` around a block gives it nothing: neither tag is ever rendered.

## `BlockContext`: a queue for each block name

`BlockContext` holds, for each block name, a list of the `BlockNode`s of that name in one chain of templates (`django/template/loader_tags.py:BlockContext`). `BlockContext.add_blocks` puts a template's blocks at the front of their lists; `BlockContext.pop` takes from the end, `BlockContext.push` puts back at the end, and `BlockContext.get_block` looks at the end. The child's blocks are added first and those of the **root**, the template at the top of the chain that extends nothing, last: the front of a list holds the root's version, and the end the most derived one, which the page shows.

## Rendering an `ExtendsNode`

When the child's tree renders, `ExtendsNode.render` does this, in order (`django/template/loader_tags.py:ExtendsNode.render`):

1. It gets the compiled parent from `ExtendsNode.get_parent`.
2. It makes a `BlockContext` in the render context, under `"block_context"`, unless one is there already, and adds its own blocks.
3. It finds the first node of the parent's list that is not text. If that is not an `ExtendsNode`, the parent is the root, and this node adds the root's blocks too.
4. It renders the parent's tree with `Template._render`, inside `RenderContext.push_state` with `isolated_context=False`.

The last step holds a chain together. `Template.render` would push a new level onto the render context, which answers from its top level only ([Rendering: nodes and the render context](rendering.md)), and the parent's nodes would find no block context (`django/template/base.py:Template.render`). Under `push_state` with `isolated_context=False` they render in the child's level, while `RenderContext.template` names the parent, against whose source an error in its nodes is reported ([Template errors and debug information](debugging.md)) (`django/template/context.py:RenderContext.push_state`).

A parent that extends in its turn adds its blocks in front of the child's, and so on to the root, whose blocks then render through their queues:

```text
{# base.html #}
<title>{% block title %}Harbour{% endblock %}</title>
{% block content %}{% endblock %}
```

```text
{# fleet/base.html #}
{% extends "base.html" %}
{% block title %}Fleet | {{ block.super }}{% endblock %}
{% block content %}<nav>ports</nav>{% block main %}{% endblock %}{% endblock %}
```

```text
{# fleet/port_detail.html #}
{% extends "fleet/base.html" %}
{% block title %}{{ port.name }} | {{ block.super }}{% endblock %}
{% block main %}<h1>{{ port.name }}</h1>{% endblock %}
```

Rendered for Valletta, the page's title is `"Valletta | Fleet | Harbour"`, and its body `"<nav>ports</nav><h1>Valletta</h1>"`.

```text figure=three-levels
fleet/port_detail.html  extends  fleet/base.html  extends  base.html, the root

the queues, front at the left and end at the right
                               title                            content             main
port_detail's ExtendsNode adds [port_detail]                                        [port_detail]
fleet/base's ExtendsNode adds  [fleet/base, port_detail]        [fleet/base]        [fleet/base, port_detail]
and then the root's            [base, fleet/base, port_detail]  [base, fleet/base]  [fleet/base, port_detail]

base.html's tree renders: a block pops the end of its queue, and pushes it back when done
block title       pops port_detail's   "Valletta | " then block.super
  block.super     pops fleet/base's    "Fleet | " then block.super
    block.super   pops base's          "Harbour"
block content     pops fleet/base's    "<nav>ports</nav>" then block main
  block main      pops port_detail's   "<h1>Valletta</h1>"
```

*A page, a section's template and the root. Each `ExtendsNode` adds its template's blocks at the front of their queues, the root's last; a block in the root's tree takes the most derived version from the end, and `{{ block.super }}` the next towards the root.*

## `BlockNode.render` and `{{ block.super }}`

`BlockNode.render` first asks the render context for a block context (`django/template/loader_tags.py:BlockNode.render`). Without one, the block is in no chain, as in a template rendered on its own or included, and renders its own contents. With one, it pops the most derived version of its name, renders that version's nodes, and pushes it back, so the queue is as it was and a block the parent renders inside a `{% for %}` gets the same version every time. If the queue is empty it renders itself.

Either way it pushes a level onto the context and sets `"block"` in it to a block node, where `{{ block.super }}` finds one. In a chain that is a fresh `BlockNode`, made from the name and nodes of the version it renders and given the context. The compiled node is shared by every render; a comment says the copy lets the context be stored without thread-safety issues.

`BlockNode.super` is what `{{ block.super }}` calls (`django/template/loader_tags.py:BlockNode.super`). If the queue holds a version still, the next towards the root, it renders its fresh block again, which pops that version, and marks the result safe, so the parent's markup is not escaped. With the queue empty it returns an empty string. The compiled node has no context, so in a block that is in no chain `{{ block.super }}` raises `TemplateSyntaxError`: "'BlockNode' object has no attribute 'context'. Did you use {{ block.super }} in a base template?".

## Finding the parent

`ExtendsNode.get_parent` resolves the tag's argument (`django/template/loader_tags.py:ExtendsNode.get_parent`). A compiled `Template` is used as it is; from a backend's template (`django/template/backends/django.py:Template`) the compiled one inside is taken. A false value, such as an empty name, is a `TemplateSyntaxError` that names the variable if there was one. Anything else is a name, for `ExtendsNode.find_template`.

That method calls `Engine.find_template` on the engine of the template the render began with, passing `skip=history`: a list of origins kept in the render context under `"extends_context"`, begun with the child's own and added to as each parent is found. Its docstring gives the purpose: extends can work recursively without extending the same template twice (`django/template/loader_tags.py:ExtendsNode.find_template`). The engine hands the list to each loader, and the base loader passes over a source whose `Origin` is in it, recording `"Skipped to avoid recursion"` in what it tried (`django/template/loaders/base.py:Loader.get_template`, `django/template/base.py:Origin`). So a project's `"fleet/base.html"`, in a directory of `"DIRS"`, may begin `{% extends "fleet/base.html" %}` and get the application's file of that name rather than itself.

The cached loader keys a template found with a skip by its name and a hash of the skipped origins of that same name, so a template is compiled once whichever chain reaches it ([Finding a template: `Engine` and the loaders](loaders.md)) (`django/template/loaders/cached.py:Loader.cache_key`).

## Relative names

`construct_relative_path` reads a name that begins `"./"` or `"../"` relative to the name the current template was loaded by, so `{% extends "./base.html" %}` in `"fleet/port_detail.html"` names `"fleet/base.html"` (`django/template/loader_tags.py:construct_relative_path`). Both tags apply it as they compile, and `{% include %}` again to a variable's value as it renders. It refuses a template with no name, as one made from a string has, a path above the top directory, and a path back to the template itself, which `do_include` allows with `allow_recursion=True`.

## `{% include %}` and `IncludeNode`

`do_include` takes a template, compiled as a filter expression, and two options, each at most once: `"with"` and pairs written `name=value`, and `"only"` (`django/template/loader_tags.py:do_include`). `IncludeNode.render` resolves the template each time (`django/template/loader_tags.py:IncludeNode.render`). A value with a callable `"render"` attribute is a template already: a compiled `Template`, a partial, or a backend's template, whose compiled one is used. Anything else is a name, or a list of names to try in order, for `Engine.select_template`, which asks `Engine.get_template`, so a name with `"#"` reaches a partial ([Template partials: `{% partialdef %}` and `{% partial %}`](partials.md)). The result is cached under the node in the bottom dictionary of the render context, which no push removes, so it lasts the whole render; the docstring names the case, an include inside a loop, whose template is then found once, not once a ship.

The `"with"` values are resolved in the including template's context, and the included template is rendered with its own `render` (`django/template/base.py:Template.render`, `django/template/base.py:PartialTemplate.render`). So it gets a level of the render context of its own: its blocks find no block context and render their own contents, and if it extends a parent it starts a chain of its own. Without `"only"`, the values are pushed onto the context, and the included template sees everything the including one sees at that point, the loop's variables among them. With `"only"`, it is rendered with a new context that holds those values and nothing else (`django/template/context.py:BaseContext.new`).

> **Trap.** `"only"` drops the context processors' names too: the included template has no `"request"` and no `"csrf_token"` unless `"with"` passes them. A comment in `RequestContext.new` puts this down to backwards compatibility (`django/template/context.py:RequestContext.new`).
