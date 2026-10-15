---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Rendering: nodes and the render context

Rendering walks a compiled template's tree of nodes with a context and returns the output as one string. Each node renders its piece and `NodeList.render` joins them; `VariableNode` makes a value into text with `render_value_in_context`; and what a node must remember during the walk it keeps, ordinarily, in the `RenderContext`.

The cached loader, the default, hands the same compiled tree to every request for a template ([Finding a template: `Engine` and the loaders](loaders.md)), so a render must leave the tree as it found it. What belongs to one render lives in two objects made for it: the context, the values the template can see ([The context: `Context`, `RequestContext` and context processors](context.md)), and the **render context**, made with every `Context`, for the nodes' own state.

## Starting a render

`Template.render` is given a `Context`, prepares it, and walks the tree (`django/template/base.py:Template.render`). It calls `RenderContext.push_state` with itself, which makes it the render context's current template and pushes an empty level for its nodes. If no template is bound to the context yet, it binds itself with `Context.bind_template`, which is when a `RequestContext` runs its context processors, and sets `Context.template_name` to its name. Then `Template._render` renders the template's `NodeList`, and the `SafeString` it returns is the output. The level and the binding are undone when the render ends, by an exception too.

So a render knows two templates. `Context.template` is the one the render began with, bound once: a template rendered from inside the render, by `{% include %}`, an inclusion tag or `{% partial %}`, finds the context bound and calls `_render` without binding. Nodes reach the engine through the bound template, for `Engine.debug` and `Engine.string_if_invalid` and to load templates, and `Context.template_name` names it in the debug log of a failed variable lookup. `RenderContext.template` is the template being rendered at the moment: the included one inside an `{% include %}`, and the parent once `{% extends %}` has handed over, even while the child's blocks render within it.

`Template._render` is the walk alone. `ExtendsNode.render` pushes a parent's state itself and calls the parent's `_render` ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](inheritance.md)). The test environment replaces it, and `PartialTemplate._render`, with `instrumented_test_render`, which sends `template_rendered` and renders, so the signal comes for each parent and included template too (`django/test/utils.py:setup_test_environment`).

## Nodes and `NodeList.render`

A **node** is an instance of a subclass of `Node` and owes the walk one method: `Node.render`, given the context, returns the node's output as a string (`django/template/base.py:Node`). The base class's method does nothing. `Parser.extend_nodelist` sets `Node.token` and the node's origin on each node it adds because, its comment says, it cannot change the nodes' `__init__`; the two tie a node to its place in the source (`django/template/base.py:Parser.extend_nodelist`).

A `NodeList` is a list of nodes, and `NodeList.render` calls `Node.render_annotated` on each and joins what they return (`django/template/base.py:NodeList.render`). `render_annotated` calls `Node.render`; when an exception escapes and the engine's `"debug"` option is on, it marks the exception with the node that raised it and, where it can, the template's lines around that node's token ([Template errors and debug information](debugging.md)). A `TextNode` returns its text from both methods, with no `try` (`django/template/base.py:TextNode.render_annotated`).

The join is returned as a `SafeString`, which autoescaping leaves alone ([Autoescaping and safe strings](autoescape.md)). Each piece is already final: a text node's text is the author's markup, a variable's value has been escaped where it was due, and a tag's node answers for its own output. Where rendered output becomes a value again, the mark keeps it from being escaped twice: the content a `Library.simple_block_tag` function is given, or a rendered template put into another's context.

## `VariableNode` and `render_value_in_context`

`VariableNode.render` asks the node's `FilterExpression` for the value, looked up in the context and passed through the filters ([Variables and filters: `FilterExpression` and `Variable`](variables.md)), and gives it to `render_value_in_context`, which makes it text in three steps (`django/template/base.py:VariableNode.render`, `django/template/base.py:render_value_in_context`):

1. `template_localtime` converts an aware `datetime` to the current time zone when `Context.use_tz` is true, or, while it is `None`, when `USE_TZ` is; one that a filter of the tz library has converted is left as it is.
2. `localize` formats a number, a date or a time for the current language, or, when `Context.use_l10n` is `False`, a number by `str` and a date or a time by the settings' format. A string passes through.
3. When `Context.autoescape` is true, a value that is not a string is made one with `str`, and `conditional_escape` escapes it unless it is safe. Otherwise it is only made a string.

`{% localtime %}` and `{% localize %}` set the first two flags for their bodies ([The libraries to load: static, i18n, l10n, tz and cache](loadable-libraries.md)), and the engine's `"autoescape"` option and `{% autoescape %}` the third. As the third step tests the string a value becomes, an object whose `__html__` returns markup is escaped all the same if its `__str__` returns a plain string.

## How a tag's node renders

Between taking the context and returning a string, a tag's node may resolve the `FilterExpression` objects its compile function made, render its own node lists, push the context for names it introduces and pop it after its body, as `ForNode`, `WithNode` and `BlockNode` do, and reach the engine through `Context.template`, as `IncludeNode` does. `NodeList.render` joins its output as it is, so a node that writes out a value has to escape it itself: `CycleNode` through `render_value_in_context`, `SimpleNode` through `conditional_escape` when autoescaping is on (`django/template/library.py:SimpleNode.render`).

A node is shared, and two threads may render it at once. Its attributes are what compiling gave it, and a render leaves them alone: what a render learns goes into the context, if the template should see it, or into the render context, if only the node needs it; an `IfChangedNode` in a loop, whose memory is to end with the loop, keeps it in the loop's `"forloop"` dictionary. The docstring of `RenderContext` calls it a safe place for state between calls of a node's render method.

`BlockNode.render` shows the rule. `{{ block.super }}` needs the context its block renders in, and `BlockNode.super` looks for it on the block. In an inheritance chain the node takes the block that is to render in its place from the block context, makes a new node of its own class with that block's name and node list, sets the context on the new one, and puts it in the context as `"block"`. The comment there gives the reason: to store the context without thread-safety issues (`django/template/loader_tags.py:BlockNode.render`).

## The render context

`RenderContext`, made by `Context.__init__`, is a `BaseContext`, a stack of dictionaries (`django/template/context.py:RenderContext`). A lookup reads only the top level, and writing, inherited from `BaseContext`, sets there too. Its docstring says why a fresh, empty level is pushed for each template: so that what is kept there is local to that template and does not affect the others.

`RenderContext.push_state` makes a template `RenderContext.template` and, unless `isolated_context=False`, pushes a level; on the way out it restores the previous template and pops. Only `ExtendsNode.render` passes `isolated_context=False`: a parent then renders on its child's level, where `{% extends %}` left the block context and the chain's history (`django/template/context.py:RenderContext.push_state`, `django/template/loader_tags.py:ExtendsNode.render`). What the built-in nodes keep there:

| node | key | what it keeps |
|---|---|---|
| `CycleNode` | the node | an iterator over its values, made at its first render; `{% resetcycle %}` replaces it |
| `IfChangedNode` | the node, outside a loop | what it compared last |
| `ExtendsNode` | `"extends_context"` | the origins of the chain so far, given to `Engine.find_template` to skip, so that none is extended twice |
| `ExtendsNode`, `BlockNode` | `"block_context"` | the `BlockContext`: for each block name, the blocks of that name from the templates of the chain |
| `IncludeNode` | the node, in the bottom level, never popped | the templates it has loaded, by name, so that an `{% include %}` in a loop loads once |
| `InclusionNode` | the node | an inclusion tag's template |

> **Trap.** An included template gets a fresh level each time, so a `{% cycle %}` in it starts again at every include. In a loop over three ships, `{% cycle "odd" "even" %}` in the loop's own template gives `"odd"`, `"even"`, `"odd"`; moved into a `"fleet/ship_row.html"` the loop includes, it gives `"odd"` three times.
