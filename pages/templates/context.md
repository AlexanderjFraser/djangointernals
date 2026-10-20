---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The context: `Context`, `RequestContext` and context processors

A template renders against a **context**, a stack of dictionaries in which a name is looked up from the top down. `BaseContext` is the stack; `Context` adds the flags a render reads and the template it is bound to; `RequestContext` adds the output of the engine's **context processors**, functions of the request, which `make_context` puts below the view's own values.

The names a render can see come from several places and live for different spans: the view's values, the CSRF token the engine supplies, a loop variable that must vanish at `{% endfor %}`. A stack holds them all and can take a name away: each source puts its names on a level of its own, the highest level holding a name answers for it, and a tag that pops its level takes its names with it.

## The stack: `BaseContext`

The levels are the list `BaseContext.dicts`, bottom first. The bottom level, made with each context, holds `"True"`, `"False"` and `"None"`: the language has no literals for them, and `{{ None }}` is a lookup that ends there unless a level above holds the name. A dictionary given to the constructor becomes the next level itself, not a copy (`django/template/context.py:BaseContext._reset_dicts`).

`BaseContext.__getitem__` and `BaseContext.get` read from the highest level that holds the name; `BaseContext.__setitem__` writes to the top level, and `BaseContext.setdefault` does so only when no level holds the name. `BaseContext.set_upward` writes to the highest level that already holds it, or else to the top: a named `{% cycle %}` uses it, so a turn of the cycle inside a `{% with %}` updates the name where it already stands, and `{% endwith %}` does not undo it (`django/template/context.py:BaseContext.set_upward`, `django/template/defaulttags.py:CycleNode.render`).

`BaseContext.push` appends a new level made from a dictionary and keyword arguments, and returns it: a `ContextDict`, a dictionary that is also a context manager, so that `with context.push(ship=ship):` pops on the way out. Its exit calls `BaseContext.pop`, which removes the top level, whichever that is, so pushes and pops inside the `with` must pair up. `pop` refuses the bottom level, with `ContextPopException` (`django/template/context.py:ContextDict`, `django/template/context.py:BaseContext.pop`).

`BaseContext.new` returns a copy that keeps the context's attributes but has a fresh stack: the bottom level and the values given. `BaseContext.flatten` merges the levels into one dictionary, the higher winning, and `BaseContext.__eq__` compares by it (`django/template/context.py:BaseContext.new`, `django/template/context.py:BaseContext.flatten`).

## `Context`: the flags and the bound template

`Context` is the stack a render uses. Beside the levels it carries `Context.autoescape`, `Context.use_l10n` and `Context.use_tz`, which say whether a value written out is escaped, localised and converted to the current time zone; `None`, the default of the last two, means localise, and convert when `USE_TZ` is true (`django/template/base.py:render_value_in_context`). They are attributes, not levels, so `push` and `pop` leave them alone: `{% autoescape %}`, `{% localize %}` and `{% localtime %}` each set one for their body and restore it after ([Autoescaping and safe strings](autoescape.md)). `Context.render_context` is a second stack, a `RenderContext`, in which nodes keep their own state ([Rendering: nodes and the render context](rendering.md)).

`Context.template` is the template the context is bound to, and `None` outside a render. `Template.render` binds the context with `Context.bind_template` only when nothing is bound yet, so the one bound is the outermost: a template it extends or includes finds the context bound (`django/template/base.py:Template.render`). The binding ends with the render. The bound template is how a node reaches its engine: `Variable._resolve_lookup` reads `"string_if_invalid"` through it, `Node.render_annotated` reads `"debug"`, and `IncludeNode.render` loads the included template. `Context.template_name` holds its name, for the log record of a failed lookup ([Variables and filters: `FilterExpression` and `Variable`](variables.md)).

`Context.update` pushes a mapping as a new level; unlike `dict.update`, it changes no level already there (`django/template/context.py:Context.update`).

## `RequestContext` and the processors' level

`RequestContext` is a `Context` made from a request, which it keeps as `RequestContext.request`, with any processors passed as `processors=`. Its constructor notes the height of the stack in `RequestContext._processors_index` and pushes two empty levels. The first holds the place of the processors' output. The second, its comment says, is for new modifications, so that context processors don't overwrite them: a name set on the context while that level is the top lands there, above the held place (`django/template/context.py:RequestContext.__init__`).

The processors run when a template is bound, not when the context is made: a `RequestContext` has no engine, and takes the processors from the bound template's engine. `RequestContext.bind_template` calls the processors of that engine's `Engine.template_context_processors`, then the context's own, each with the request; merges the dictionaries they return, a later processor's name replacing an earlier one's; and puts the result in the held place, replacing the empty level rather than pushing, so that what is already above it stays above. When the render ends it empties the place again (`django/template/context.py:RequestContext.bind_template`). So the processors run once for each render of an outermost template, and their names exist only while it lasts.

`RequestContext.new` returns a context with no held place: the stack is reset to the bottom level and the values given, and the index deleted, a comment says for backwards compatibility (`django/template/context.py:RequestContext.new`). A template included by `{% include … only %}` sees no `"csrf_token"` or `"request"`; `InclusionNode.render`, which also renders against `new`, copies `"csrf_token"` across, because, its comment says, inclusion tags are often used for forms (`django/template/library.py:InclusionNode.render`).

## `make_context`: the view's values on top

The backend's template wrapper makes its context with `make_context`, from the view's dictionary and the request, if any (`django/template/backends/django.py:Template.render`). Without a request, `make_context` makes a `Context` with the dictionary as the level above the bottom. With one, it makes a `RequestContext` with no dictionary, then pushes the view's dictionary on top, unless it is empty (`django/template/context.py:make_context`).

The order is the point; the comment there says it ensures values from the context override those from the processors. Given to the constructor, the view's dictionary would sit under the held place, where a processor's name would hide the view's. In the Jinja2 backend it is the other way round ([Template engines: `TEMPLATES` and the backends](engines.md)).

> **Trap.** Without a request, the level above the bottom is the view's own dictionary, and a name a template sets at its top level, as `{% firstof port.name as title %}` does, is written into the view's object. With a request, `push` copies it.

```text figure=the-stack
fleet/port_detail.html, rendered with a request,
while the body of {% for ship in ships %} renders;
the engine's "context_processors" lists django.template.context_processors.request

top: looked up first
  4  {"forloop": {...}, "ship": the current ship}   pushed by ForNode.render, for the loop
  3  {"port": Valletta, "ships": [...]}             the view's dictionary, pushed last by make_context
  2  {}                                             pushed by RequestContext.__init__, for names set while it is the top
  1  {"csrf_token": lazy, "request": the request}   the held place, filled by RequestContext.bind_template as the render began
  0  {"True": True, "False": False, "None": None}   made with every context by BaseContext
bottom: looked up last
```

*The stack of a `RequestContext` while the body of a loop renders. A name is found on the highest level that holds it. The loop's level goes at `{% endfor %}`, the processors' output when the render ends.*

## The engine's processors

`Engine.template_context_processors` imports the paths of the engine's `"context_processors"` option, after the one path in `_builtin_context_processors`: the CSRF processor, hard-coded, a comment says, for easier use of CSRF protection (`django/template/engine.py:Engine.template_context_processors`, `django/template/context.py:_builtin_context_processors`). It comes first whether the option names it or not, and the option's default is an empty list, so every render of a `RequestContext` has the `"csrf_token"` that `{% csrf_token %}` reads.

A processor runs whether or not the template uses its names. The CSRF processor defers its call of `get_token` with a `SimpleLazyObject`, as the docstring of `get_token` advises, since calling it makes the CSRF middleware add a cookie to the response (`django/template/context_processors.py:csrf`, `django/middleware/csrf.py:get_token`).

The processors of `django/template/context_processors.py`:

| processor | adds | from |
|---|---|---|
| `csrf` | `"csrf_token"` | `get_token`, when the token is first used |
| `debug` | `"debug"`, `"sql_queries"` | only when `settings.DEBUG` is true and the request's address is in `settings.INTERNAL_IPS`; queries read when used |
| `i18n` | `"LANGUAGES"`, `"LANGUAGE_CODE"`, `"LANGUAGE_BIDI"` | the setting and the active language |
| `tz` | `"TIME_ZONE"` | the current time zone's name |
| `static` | `"STATIC_URL"` | the setting |
| `media` | `"MEDIA_URL"` | the setting |
| `request` | `"request"` | the request itself |
| `csp` | `"csp_nonce"` | the nonce `ContentSecurityPolicyMiddleware` put on the request, or `None` |

> **Changed in 6.0.** The `csp` processor is new, with Content Security Policy support ([Content Security Policy and the nonce](../security/csp.md)).

## The tags that push a level

Among the built-in tags, these push a level for the names they give their body, and pop it when the body is done:

- `{% for %}`: `ForNode.render` pushes one level for the whole loop, holding `"forloop"` and the loop variable, which each item overwrites; the enclosing `"forloop"`, read first, becomes `"parentloop"`. An item unpacked into several names gets a level of its own.
- `{% with %}`: `WithNode.render` resolves its values, then pushes them for its body ([The built-in tags](tags.md)).
- `{% include %}` and `{% block %}`: `IncludeNode.render` pushes the values the tag names, or for `{% include … only %}` renders against `new`; `BlockNode.render` pushes a level holding `"block"`, through which `{{ block.super }}` reaches the parent's block ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](inheritance.md)).

A tag that stores a value under a name, as `{% url … as link %}` and `{% firstof … as title %}` do, sets it on the top level, so the name lasts until that level is popped: set inside a `{% with %}` or a `{% for %}`, it is gone after the end tag. A named `{% cycle %}` is the exception: it writes with `BaseContext.set_upward`.
