---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Variables and filters: `FilterExpression` and `Variable`

A variable tag such as `{{ ship.name|upper }}` is compiled into a `FilterExpression`: the value it starts from, a `Variable` or a constant, and the filters to apply. At render time `Variable._resolve_lookup` finds the value in the context, as a key, an attribute or an index, calling it if it can be called, and `FilterExpression.resolve` passes it through the filters, or decides what a missing variable becomes.

A template's author writes `{{ port.name }}` without saying whether the port is a dictionary, an object or a list. The engine must find the value whichever it is, decide whether to call what it finds, and choose between failing and printing nothing. What the text settles is settled at compile time: the expression is cut into its parts, each filter's function found and its arguments counted, each literal turned into its value. Only the lookup and the calls are left to each render. The same object serves more than `{{ }}`: `Parser.compile_filter` makes one, and the compile functions of `{% if %}`, `{% for %}`, `{% url %}` and others call it for the values they take (`django/template/base.py:Parser.compile_filter`).

## The grammar

The grammar is one regular expression, `filter_re`. A **constant** is a string in double or single quotes, which may be wrapped in `_()` to mark it for translation (`constant_string`). A **variable** is a run of word characters, dots, and plus and minus signs. A **filter** is a `|`, with spaces allowed around it, a name, and optionally a `:` and one argument, a constant or a variable, with no space around the colon. `filter_re` is compiled from `filter_raw_string`, which takes the `|` and the `:` from `FILTER_SEPARATOR` and `FILTER_ARGUMENT_SEPARATOR` (`django/template/base.py:filter_raw_string`). So a filter is given the value and at most one argument.

A number has no branch of its own: `2` and `-2` match as variables, so that, says a comment at `constant_string`, numbers keep their type when passed to filters. A constant argument goes through `mark_safe` as the filter runs, which would make a number a `SafeString`.

## Compiling: `FilterExpression.__init__`

`FilterExpression.__init__` takes the matches of `filter_re` in order, each beginning where the last ended (`django/template/base.py:FilterExpression.__init__`). The first is the value: a constant is resolved at once and its value kept, a variable kept as a `Variable`, and `FilterExpression.is_var` says which. Each later match is a filter, whose name `Parser.find_filter` looks up among the builtins' filters and those of the libraries loaded so far, and the expression keeps the function itself, so a filter not loaded is an error now, not at render. `FilterExpression.args_check` compares the count with the function's signature, counting the value as one argument.

Each failure is a `TemplateSyntaxError`; from `Engine.from_string`, these gave:

```text
{{ port name }}            Could not parse the remainder: ' name' from 'port name'
{{ port.name|uper }}       Invalid filter: 'uper'
{{ port.name|default }}    default requires 2 arguments, 1 provided
```

> **Deprecated.** Two dots in a row, `{{ port..name }}`, look up an empty name between them. `Parser.parse` warns with `RemovedInDjango2028Warning` when it compiles a variable tag holding them; the arguments of tags and filters are not checked. The 6.1 release notes call it normally a mistake; Django 2028 removes it (`django/template/base.py:Parser.parse`).

## Literals and names: `Variable.__init__`

`Variable.__init__` decides from the text alone what it holds (`django/template/base.py:Variable.__init__`). Text holding a dot, an `"e"` or an `"E"` is tried as a `float`, other text as an `int`, and text ending in a dot is no number; a number is kept in `Variable.literal`. Failing that, a `_()` around the text sets `Variable.translate` and is stripped. Text in quotes is then a string literal, its escaped quotes and backslashes undone and the result marked safe. Anything else is a name, split at the dots, `VARIABLE_ATTRIBUTE_SEPARATOR`, into `Variable.lookups`. A name is refused if it holds a `+` or a `-`, which the grammar admits for numbers, or if a part begins with an underscore, as the documentation says such attributes are generally private (`docs/ref/templates/language.txt`).

> **Why.** A string literal is not escaped: the documentation says the template's author controls what goes into it and can write it escaped (`docs/ref/templates/language.txt`). So `{{ x|default:"<b>" }}` renders `"<b>"` when x is empty.

`Variable.resolve` returns the literal, or for a name what `_resolve_lookup` finds; for a variable marked for translation it returns a lazy translation of that, with `Variable.message_context` as its context if set (`django/template/base.py:Variable.resolve`). So a `_("…")` constant, resolved as the template compiles, is translated each time it renders. The `{% translate %}` tag sets `translate` on its variable at each render, and `message_context` when the tag is given a context ([The libraries to load: static, i18n, l10n, tz and cache](loadable-libraries.md)).

## The lookup: `Variable._resolve_lookup`

`Variable._resolve_lookup` starts from the context and takes the parts of the name in turn, each applied to what the one before found. For each it tries three things, in this order, and keeps the first that works (`django/template/base.py:Variable._resolve_lookup`):

1. **A key**, `current[part]`, tried only when the object's type defines `__getitem__`, so that a class whose `__class_getitem__` would answer any key is not taken for a mapping. For the first part this is the context's own lookup, from the top of its stack.
2. **An attribute**, `getattr(current, part)`. A context's own attributes are never found this way: `{{ push }}` is a missing name, not a call of `BaseContext.push`.
3. **An index**, `current[int(part)]`, which serves a list or a dictionary with integer keys.

If all three fail, it raises `VariableDoesNotExist`, with the part and the object. One failure of the second step is not a miss: if `getattr` raises `AttributeError` or `TypeError` for a name that `dir` lists, the error came from inside the attribute, as from a property's body, and is raised again (`django/template/base.py:Variable._resolve_lookup`).

> **Trap.** The key comes first. Given `{"items": "a key"}` as data, `{{ data.items }}` renders `"a key"`, not the dictionary's method.

After each step, what was found is called if it can be, unless it says otherwise:

- With a true `"do_not_call_in_templates"` it is kept as it is. The related managers set it ([Reading and setting related objects](../models/related-objects.md)).
- With a true `"alters_data"` it is not called, and the value becomes the engine's `"string_if_invalid"`. Many methods that write carry it, among them `Model.save`, `Model.delete`, `QuerySet.update` and a file field's `FieldFile.save` ([File fields](../models/files.md)).
- Otherwise it is called with no arguments. If that raises `TypeError`, `signature` is asked whether no arguments bind: if not, or if there is no signature, the call was invalid and the value becomes `"string_if_invalid"`; if they do, the error came from inside and is raised again.

The whole lookup is one `try`. An exception the steps above do not handle is logged on `"django.template"` at the debug level, naming the part that failed and the template the render began with; Django's default logging drops that level (`django/utils/log.py:DEFAULT_LOGGING`). An exception with a true `"silent_variable_failure"` then gives `"string_if_invalid"`, and any other goes on up. `ObjectDoesNotExist` sets it, so a `Model.DoesNotExist` raised in a lookup does not break the render (`django/core/exceptions.py:ObjectDoesNotExist`).

Wherever the lookup gives `"string_if_invalid"`, it is the option's string as configured, `%s` and all, and the filters run on it: with the option set to `"INVALID %s"`, `{{ ship.sink|upper }}`, its method carrying `"alters_data"`, rendered `"INVALID %S"`.

## A missing variable: `FilterExpression.resolve`

`FilterExpression.resolve` catches `VariableDoesNotExist` from its variable and decides the value (`django/template/base.py:FilterExpression.resolve`):

- With `ignore_failures=True` it is `None`, and the filters run. The tags `{% if %}`, `{% for %}`, `{% firstof %}`, `{% ifchanged %}` and `{% regroup %}` ask for this, so a missing name is false or an empty loop whatever the option holds.
- Else, if the engine's `"string_if_invalid"` is not empty, that is the result, a `%s` in it replaced by the variable as written, and no filter runs.
- Else the value is `""`, and the filters run on it.

The option's default is `""`, from `Engine.__init__`, and it is read at render time from the engine of `Context.template`. A port with no nme, rendered as `{{ port.nme }}` and as `{{ port.nme|default:"none" }}`:

| the option | alone | with `default` |
|---|---|---|
| `""` | `""` | `"none"` |
| `"INVALID %s"` | `"INVALID port.nme"` | `"INVALID port.nme"` |

> **Trap.** A filter's variable argument gets no such care: `{{ port.name|default:nothing }}`, with nothing of that name in the context, raises `VariableDoesNotExist` out of the render.

## Calling the filters

`FilterExpression.resolve` runs the filters in order, each given the value so far and its argument, a constant marked safe or a variable resolved in the context (`django/template/base.py:FilterExpression.resolve`). Three flags, which `Library.filter` sets on the function ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)), change the call or its result. With `"expects_localtime"`, an aware datetime is first put in the current time zone by `template_localtime`, as `Context.use_tz`, or else `USE_TZ`, allows. With `"needs_autoescape"`, the function is passed `Context.autoescape` as its autoescape argument, to do its own escaping. With `"is_safe"`, a result made from a safe value is marked safe in turn. What safe means is told in [Autoescaping and safe strings](autoescape.md).
