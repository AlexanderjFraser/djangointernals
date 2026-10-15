---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Autoescaping and safe strings

Django's template engine escapes the values it writes into a template's output for HTML, unless a value, made a string, is **safe**: a `SafeData`, such as the `SafeString` that `mark_safe`, `format_html` or a filter returns. The mark is made in `django/utils/safestring.py` and the escaping in `django/utils/html.py`; the engine applies them in `render_value_in_context`, in its filters, and as the `"autoescape"` option and `{% autoescape %}` direct.

A template's own text is markup, and the values put into it are not. A ship named `<Beagle>` has to reach the browser as `&lt;Beagle&gt;`, or its name becomes a tag. But some values are markup already, as a rendered form is: escaping those prints their tags as text, and escaping anything twice prints its entities. So the engine must know whether each value is HTML already; Django keeps that in its type. A string that may go into HTML as it stands is a `SafeString`; any other string is **escaped** once, as it is written out.

## The mark: `SafeData` and `SafeString`

`SafeData` is a mixin with no state and one method, `SafeData.__html__`, which returns the object itself. `__html__` is a convention shared with other libraries: an object that has it can be asked for its HTML, and the docstring says it lets other template engines understand Django's safe data (`django/utils/safestring.py:SafeData`).

`SafeString` is a `str` that is also a `SafeData`. `SafeString.__str__` returns the string itself, so `str()` keeps the mark. `SafeString.__add__` returns a `SafeString` only when the other operand is safe too: a safe string and a plain one, added in either order, give a plain `str`. Every other string method is `str`'s own, so an upper-cased, sliced or replaced safe string is plain (`django/utils/safestring.py:SafeString`). `SafeText` is another name for the class.

`mark_safe` escapes nothing: its caller vouches for the string. An object that has `__html__` is returned unchanged, so marking twice is harmless. A callable is wrapped by `_safety_decorator`, so that `mark_safe` can decorate a function and mark what it returns. Anything else becomes a `SafeString`, converted by `str`. Wrapped in `keep_lazy`, it leaves a lazy translation lazy, to become a `SafeString` when it is evaluated (`django/utils/safestring.py:mark_safe`).

## Escaping: `escape`, `conditional_escape` and `format_html`

`escape` converts its argument by `str`, replaces ampersands, angle brackets and both kinds of quote with entities by the standard library's `html.escape`, and returns a `SafeString`. It escapes even what is escaped already (`django/utils/html.py:escape`). `conditional_escape` is the one `render_value_in_context` uses: a lazy string is made a `str`, an object with `__html__` is asked for its HTML, and anything else goes to `escape` (`django/utils/html.py:conditional_escape`). Given a safe `"&amp;"`, `escape` returns `"&amp;amp;"` and `conditional_escape` returns it unchanged.

`format_html` builds a fragment of HTML in Python. It works as `str.format`, passing each argument through `conditional_escape` and marking the result safe, so `format_html("<li>{}</li>", ship)` puts a ship named `<Beagle>` in as `&lt;Beagle&gt;` and a safe argument as it stands (`django/utils/html.py:format_html`). `format_html_join` does the same for each item of an iterable and joins the results with a separator, which it also escapes conditionally.

> **Changed in 6.0.** `format_html` raises `TypeError` when it is given no arguments. Such a call would escape nothing, and return its string marked safe.

`html_safe` decorates a class whose `__str__` returns HTML. It wraps `__str__` so that its result is marked safe, and adds an `__html__` that returns `str(self)`; it refuses a class that defines `__html__` itself or does not itself define `__str__` (`django/utils/html.py:html_safe`).

Two functions escape for JavaScript. `escapejs` replaces the backslash, quotes, angle brackets, some other punctuation, the Unicode line and paragraph separators and the control characters with escapes such as `"\u003C"`, for a value inside a JavaScript string, and marks the result safe (`django/utils/html.py:escapejs`). `json_script` serialises a value, by default with `DjangoJSONEncoder`, escapes angle brackets and ampersands the same way, and wraps it in a `<script type="application/json">` element; its docstring calls the escaped JSON safe anywhere but inside a tag's attribute (`django/utils/html.py:json_script`).

The module's other helpers return plain strings, though `strip_tags` gives back a safe input still safe when it finds no tag to remove; the filters built on them do any marking.

| helper | what it does |
|---|---|
| `linebreaks` | wraps paragraphs in `<p>` and turns single newlines into `<br>`, escaping each paragraph first if asked |
| `strip_tags` | removes tags with the standard library's HTML parser |
| `strip_spaces_between_tags` | removes whitespace between tags |
| `urlize` | turns web and email addresses in text into links, by an `Urlizer` |
| `smart_urlquote` | percent-encodes a URL, unquoting each part first |
| `avoid_wrapping` | replaces spaces with no-break spaces |

## Where the engine escapes: `render_value_in_context`

A variable's value becomes output through `render_value_in_context`, which `VariableNode.render` calls, as do the nodes of `{% cycle %}`, `{% firstof %}`, `{% translate %}` and `{% blocktranslate %}`. It puts the value in local time and localises it; then, if the context's autoescaping is on, it converts anything that is not a `str` by `str` and hands it to `conditional_escape`. With autoescaping off it only converts (`django/template/base.py:render_value_in_context`).

The conversion comes first, so an object that is not a string is safe only if its `__str__` returns a safe string; its `__html__` is not consulted, and the docstring of `html_safe` gives that method to templates that are not Django's. `{{ form }}` writes a form unescaped: its `__str__` is `RenderableMixin.render`, which marks the rendering safe (`django/forms/utils.py:RenderableMixin.render`).

Nothing escapes what a node returns. `NodeList.render` joins its nodes' strings and marks the whole safe, so the template's own text, which a `TextNode` returns as it stands, goes out unescaped, and so does what a tag's node returns (`django/template/base.py:NodeList.render`). What a tag writes is escaped only if its node escapes it: the node of a `simple_tag` passes its function's result through `conditional_escape` when autoescaping is on, as `{% url %}` does its URL (`django/template/library.py:SimpleNode.render`).

A string literal in a template is marked safe like the text around it: `Variable.__init__` marks a quoted literal, and `FilterExpression.resolve` each quoted argument of a filter. So `{{ "<b>Valletta</b>" }}` writes a bold Valletta, and for a port with none, `{{ port.harbourmaster|default:"<em>vacant</em>" }}` writes `"<em>vacant</em>"` (`django/template/base.py:Variable.__init__`).

## Filters and safety

`FilterExpression.resolve` runs a variable's filters in order, and `render_value_in_context` escapes what the last returns unless it is safe or autoescaping is off ([Variables and filters: `FilterExpression` and `Variable`](variables.md)). String work on a safe input gives a plain `str`. Two flags, which `Library.filter` copies onto the function it registers, let a filter say more ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)).

A filter registered with `is_safe=True` promises to add nothing unsafe to a safe input. When its input was safe, the engine marks its result safe; when not, the engine leaves the result as it is (`django/template/base.py:FilterExpression.resolve`). The flag carries safety through a filter and never creates it. `|lower` has it and `|upper` does not, and upper-casing `&eacute;` gives `&EACUTE;`, which HTML does not define. With a safe `"<em>Valletta</em>"` as the note, `{{ note|safe|lower }}` writes `"<em>valletta</em>"` and `{{ note|safe|upper }}` writes `"&lt;EM&gt;VALLETTA&lt;/EM&gt;"`.

`stringfilter` decorates a filter that works on strings. It converts the first argument by `str`, which keeps a `SafeString` safe and turns an object whose `__str__` returns a safe string into one, then makes the engine's test on the converted value, reading `is_safe=True` from the innermost function, where `Library.filter` also sets it (`django/template/defaultfilters.py:stringfilter`).

A filter registered with `needs_autoescape=True` is called with `autoescape=context.autoescape`. It is for a filter that builds markup around its input, as `|join`, `|linebreaks` and `|unordered_list` do. The engine escapes a result whole, markup and all; such a filter escapes the pieces of its input itself, when autoescaping is on and they are not safe, and marks its whole result safe. With two ships, `{{ names|join:"<br>" }}` writes `"Endeavour<br>&lt;Beagle&gt;"`, the separator being a literal, and safe (`django/template/defaultfilters.py:join`).

## Switching it off: the `"autoescape"` option and `{% autoescape %}`

Whether to escape is a property of the context, `Context.autoescape`, an attribute beside the stack, true by default (`django/template/context.py:Context`). The engine's `"autoescape"` option, true unless `"OPTIONS"` says otherwise, reaches it through the backend's template, which makes its context with the engine's setting (`django/template/backends/django.py:Template.render`). A `Context` made by hand has its own default, and escapes under an engine whose option is false.

`{% autoescape off %}` and `{% autoescape on %}` change the setting for a stretch of template. The compile function `autoescape` accepts `"on"` or `"off"` and nothing else; its `AutoEscapeControlNode` sets the context's attribute, renders its body, and puts the old value back (`django/template/defaulttags.py:AutoEscapeControlNode.render`). The setting holds for all that renders with the context meanwhile: a filter's `autoescape` argument, a simple tag, an included template, even one included with `only`, since `BaseContext.new` copies the old context's attributes (`django/template/context.py:BaseContext.new`).

`{% filter %}` refuses `|escape` and `|safe` anywhere in its chain, naming `{% autoescape %}` instead, which its docstring calls the way to manage autoescaping for a block (`django/template/defaulttags.py:do_filter`).

## The escaping filters

These filters only escape or mark, each by a function of `django/utils/html.py` or `django/utils/safestring.py` ([The built-in filters](filters.md)).

| filter | calls | for |
|---|---|---|
| `\|safe` | `mark_safe` | a value known to be HTML |
| `\|safeseq` | `mark_safe` on each item | a list of HTML, to join |
| `\|escape` | `conditional_escape` | escaping where autoescaping is off |
| `\|force_escape` | `escape` | escaping even a safe value |
| `\|escapeseq` | `conditional_escape` on each item | a list to join where autoescaping is off |
| `\|escapejs` | `escapejs` | a value inside a JavaScript string |

*The filters of `django/template/defaultfilters.py` that only escape for HTML or JavaScript, or mark.*
