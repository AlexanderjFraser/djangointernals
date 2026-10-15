---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The built-in tags

The built-in tags of `django.template.defaulttags` are in every Django template without `{% load %}`: how `{% for %}` builds its loop variables, `{% if %}` parses a condition with `django/template/smartif.py` and `{% url %}` reverses a name, and how `{% cycle %}`, `{% ifchanged %}`, `{% regroup %}` and `{% querystring %}` work.

The module is one of the three libraries every `Engine` gives each parser before the first token (`django/template/engine.py:Engine.__init__`). Each tag in it but two is written there as a compile function and a subclass of `Node` (`django/template/base.py:Node`). The function reads the tag's words at compile time, refuses what it cannot parse, and turns each argument that stands for a value into a `FilterExpression`; the node resolves those against the context at each render. So a malformed tag fails at compile time, and a bad value at the render that meets it. The two, `{% querystring %}` and `{% csp_nonce_attr %}`, are simple tags ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md), which also has `{% load %}`). `{% autoescape %}` and the partial tags have [Autoescaping and safe strings](autoescape.md) and [Template partials: `{% partialdef %}` and `{% partial %}`](partials.md).

## The loop: `{% for %}` and `ForNode`

`do_for` reads `{% for ship in ships %}` at compile time: at least four words, an optional last word `reversed`, loop variables split on commas, the sequence as a filter expression, the body up to `{% empty %}` or `{% endfor %}` (`django/template/defaulttags.py:do_for`). `ForNode.render` then works in this order (`django/template/defaulttags.py:ForNode.render`):

1. It reads `"forloop"` from the context: inside another loop, the outer loop's dictionary, which becomes the new `"parentloop"` (else an empty one).
2. It pushes a level on the context for the rest, so the loop's names are gone after `{% endfor %}`.
3. It resolves the sequence with `ignore_failures=True`, so a missing variable is `None`, not `"string_if_invalid"`, and counts as empty. A sequence without a length, a generator, is made a list, and its length taken before the first item.
4. An empty sequence renders the `{% empty %}` branch, or nothing.
5. It puts one dictionary in the pushed level as `"forloop"`, with `"parentloop"` and `"length"`, and before each item sets `"counter"`, `"counter0"`, `"revcounter"`, `"revcounter0"`, `"first"` and `"last"` in it.
6. One loop variable is set in the pushed level. Several are unpacked from the item, which must have as many elements or the render raises `ValueError`, and pushed as a level of their own for the body.
7. It returns the output, joined and marked safe.

One dictionary, changed in place, serves the whole loop, and an inner loop's `"parentloop"` is the outer's dictionary itself.

> **Changed in 6.0.** `{{ forloop.length }}` is new (`docs/releases/6.0.txt`).

## Conditions: `{% if %}` and `IfParser`

`do_if` parses the condition of `{% if %}` and of each `{% elif %}`, and each branch up to the next clause, into an `IfNode` of pairs, a condition and a node list; `{% else %}` has `None` for its condition (`django/template/defaulttags.py:do_if`).

The condition is parsed by `django/template/smartif.py`, a top-down operator-precedence parser. Each token has a **binding power**, `lbp`, how tightly it holds what stands on its left; `TokenBase.nud` is what it does at the start of an expression and `TokenBase.led` what it does after one, and both raise by default, with the message a misplaced token gets. `OPERATORS` holds a class for each operator, made by `infix` or `prefix` from a power and a function: `"or"` at 6, `"and"` at 7, the prefix `"not"` at 8, `"in"` and `"not in"` at 9, and `"is"`, `"is not"` and the six comparisons at 10 (`django/template/smartif.py:infix`).

`IfParser.__init__` joins `is` `not` and `not` `in` into single tokens and makes each word a fresh operator or, failing that, an operand, which `TemplateIfParser` makes a `TemplateLiteral` around a compiled filter expression, so `ships|length` is one operand (`django/template/defaulttags.py:TemplateIfParser`). `IfParser.expression` is the whole algorithm: call the first token's `nud`, then, while the next token binds more tightly than the power the call was given, call that token's `led` with the expression so far. An operator's `led` parses its right side with its own power, so equal powers group to the left (`django/template/smartif.py:IfParser.expression`). A malformed condition is a `TemplateSyntaxError` at compile time, such as "Unused 'port' at end of if expression." for `{% if ships port %}`.

> **Trap.** Comparisons do not chain: `{% if 3 > 2 > 1 %}` is `(3 > 2) > 1`, `True > 1`, false.

`IfNode.render` renders the first branch whose condition holds (`django/template/defaulttags.py:IfNode.render`). An operand resolves with `ignore_failures=True`, so a missing variable is `None`. An operator evaluates its operands in its function, so `and` and `or` stop early, and turns any exception into `False`; a comment in `infix` says a template should not raise while rendering (`django/template/smartif.py:infix`). A `VariableDoesNotExist` reaching `IfNode.render`, from a filter's argument, counts as false.

> **Trap.** The `False` is the failing operator's, not the condition's. With y missing, `{% if x not in y %}` is false but `{% if not x in y %}` true, `not` turning the `False` of `in`. An operand alone has no operator to catch for it: a property that raises `ValueError` escapes from `{% if port.tides %}`, not from `{% if port.tides == 1 %}`.

## `{% url %}` and `URLNode`

`{% url %}` compiles its first argument, the name, as a filter expression, so it may be quoted or a variable; takes `as` and a name off the end; and makes each other word a keyword argument, `pk=port.pk`, or a positional one, by `kwarg_re` (`django/template/defaulttags.py:url`). `URLNode.render` resolves them and calls `reverse` ([Reversing a name](../urls/reversing.md)) with a current application from the context's request: its attribute `"current_app"`, else the namespace of `HttpRequest.resolver_match` ([Namespaces](../urls/namespaces.md#where-the-current-application-comes-from)) (`django/template/defaulttags.py:URLNode.render`). A name that does not reverse raises `NoReverseMatch`, unless the tag ends with `as`, whose name then gets an empty string. The path is escaped when autoescaping is on.

## Names a tag sets: `{% with %}` and `as`

`{% with total=port.ships|length %}` pushes a level holding its names until `{% endwith %}`; `do_with` reads the pairs, or the older `port.ships|length as total`, with `token_kwargs` (`django/template/base.py:token_kwargs`). Every value is resolved before the push, so `{% with a=1 b=a %}` gives b the a from outside, and a missing variable in one becomes `"string_if_invalid"` (`django/template/defaulttags.py:WithNode.render`).

Given `as` and a name, `{% url %}`, `{% firstof %}`, `{% now %}`, `{% widthratio %}` and the simple tags assign it in the context's top level, as `{% regroup %}` does (`django/template/context.py:BaseContext.__setitem__`): set inside `{% for %}`, `{% with %}` or `{% block %}`, it is gone after the end tag, and inside `{% if %}`, which pushes nothing, it outlasts it. `{% cycle %}` uses `BaseContext.set_upward`, which writes where the name already is, else on top.

## `{% cycle %}` and `{% resetcycle %}`

`CycleNode` keeps its place in the render context under the node itself: an iterator cycling through its compiled values, made at its first render (`django/template/defaulttags.py:CycleNode.render`). `Template.render` gives the render context a fresh level, and `{% include %}` renders its template that way each time ([Rendering: nodes and the render context](rendering.md)), so `{% cycle 'odd' 'even' %}` in a template included once for each of three ships renders `"odd"` all three times (`django/template/base.py:Template.render`).

`{% cycle 'odd' 'even' as row %}` also sets row to each value, and `"silent"` after it stops it rendering. Named nodes are kept on the parser, so a name holds within one template; `{% cycle row %}` returns the same node, and every use advances it (`django/template/defaulttags.py:cycle`). `{% resetcycle %}` gives a fresh iterator to the named node or, with no name, to the last cycle tag before it that declared values (`django/template/defaulttags.py:resetcycle`).

## `{% ifchanged %}`

`IfChangedNode` renders its body when its arguments' values, or with none its rendered body, differ from last time, and otherwise its `{% else %}` branch or nothing (`django/template/defaulttags.py:IfChangedNode.render`). It keeps the last values under the node in the loop's `"forloop"` dictionary, which is new each time the loop starts, so in a nested loop the comparison starts over on each pass of the outer one; outside a loop, in the render context (`django/template/defaulttags.py:IfChangedNode._get_context_stack_frame`).

## `{% regroup %}`

`{% regroup ships by kind as kinds %}` takes exactly those words. The key is compiled as the variable `{{ kinds.kind }}`, and each ship is put in the context under kinds while its key resolves: a hack, its comment says, for want of a getattr that works through the context (`django/template/defaulttags.py:regroup`). The standard library's groupby then joins only neighbours: ships of kinds brig, brig, bark, brig make three groups. Each is a `GroupedResult` of `"grouper"` and `"list"`; a missing list gives no groups (`django/template/defaulttags.py:RegroupNode.render`).

## `{% querystring %}`

`querystring` is a simple tag that takes the context (`django/template/defaulttags.py:querystring`). Its positional arguments, each a mapping, then its keyword arguments, are applied in order to an empty `QueryDict`. With no positional argument, the request's `HttpRequest.GET` stands in, and a plain `Context`, which has no request attribute, raises `AttributeError`. `None` removes a key, an iterable other than a string sets its values but `None`, anything else replaces. The result always begins with `"?"` and is escaped when autoescaping is on: on a request for `"/ports/?q=brig&page=2"`, `{% querystring page=3 %}` renders `"?q=brig&amp;page=3"`.

> **Changed in 6.0.** The `"?"` is always there, and several positional mappings are allowed (`docs/releases/6.0.txt`).

## The other tags

| tag | renders | where |
|---|---|---|
| `{% firstof %}` | the first true argument, escaped when autoescaping is on | `django/template/defaulttags.py:FirstOfNode` |
| `{% now %}` | the time now, through the date filter; its argument is not resolved, only stripped of its first and last characters | `django/template/defaulttags.py:now` |
| `{% spaceless %}` | the body with white space between tags, and at its ends, removed | `django/template/defaulttags.py:SpacelessNode` |
| `{% verbatim %}` | the body as text, which the lexer left unparsed | `django/template/defaulttags.py:verbatim` |
| `{% templatetag %}` | a delimiter of the syntax, by name | `django/template/defaulttags.py:TemplateTagNode` |
| `{% widthratio %}` | a value over a maximum, times a width, rounded half to even | `django/template/defaulttags.py:WidthRatioNode` |
| `{% filter %}` | the body through filters, refusing the escape and safe filters | `django/template/defaulttags.py:do_filter` |
| `{% lorem %}` | placeholder Latin | `django/template/defaulttags.py:LoremNode` |
| `{% debug %}` | the context and the loaded modules, when `settings.DEBUG` is true ([Template errors and debug information](debugging.md)) | `django/template/defaulttags.py:DebugNode` |
| `{% comment %}` | nothing: the parser skips to `{% endcomment %}` unparsed | `django/template/defaulttags.py:comment` |
| `{% csrf_token %}` | a hidden input holding the CSRF context processor's token, or nothing when the context has none | `django/template/defaulttags.py:CsrfTokenNode` |
| `{% csp_nonce_attr %}` | a simple tag: `nonce="…"` from the nonce of `django.template.context_processors.csp`, or nothing; given a form's media, its tags carrying that nonce | `django/utils/csp.py:nonce_attr` |
