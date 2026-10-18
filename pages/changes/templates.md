---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in templates

Template partials, `{% querystring %}` and `{{ forloop.length }}` are new; two dots in a variable, `takes_context=True`, `format_html` without arguments, `"alters_data"` and `|urlize`'s scheme for a bare domain make templates and their helpers stricter.

A template is compiled into a tree of nodes, and the tree renders with a context ([Templates](../templates.md)). Both halves changed. 6.0 added **template partials**: named fragments of a template, which a name with a `"#"` loads alone. They are built on a place the compiler gained in 5.1, where a tag can leave data for the compiled template. Rendering gained the loop's length (6.0) and `{% querystring %}` (5.1), for the query string a template had built with a loop.

Other changes make templates and their helpers stricter. 6.1 deprecates two dots in a variable, and refuses, as it is decorated, a custom tag declared with `takes_context=True` whose function lacks its `"context"` parameter. 6.0 refuses `format_html` with nothing to format. Since 6.0, linking a bare domain warns that its scheme will change, unless `URLIZE_ASSUME_HTTPS` is true. Since 5.2, a template does not call the queryset's and `UserManager`'s methods that create rows.

## Template partials, on the parser's extra data

Since 6.0, a template can name fragments of itself, each loaded alone by a name with a `"#"` ([Template partials: `{% partialdef %}` and `{% partial %}`](../templates/partials.md)). Partials are built on `Parser.extra_data`, new in 5.1: a dictionary in which a tag's compile function may leave data, kept as `Template.extra_data` once the parse succeeds (`django/template/base.py:Template.compile_nodelist`).

`{% partialdef row %}` … `{% endpartialdef %}` files a `PartialTemplate` in `Parser.extra_data`, under `"partials"` (`django/template/defaulttags.py:partialdef_func`). The definition renders nothing where it stands, unless the tag adds `"inline"`. `{% partial row %}` renders the fragment in the context at that point (`django/template/defaulttags.py:PartialNode.render`).

`Engine.get_template`, and so `render_to_string` and `{% include %}`, splits a name such as `"entries.html#row"` at its first `"#"`. It loads the template before it, and returns the partial filed under the rest (`django/template/engine.py:Engine.get_template`).

To 5.2.17 the `"#"` is part of a template's name; since 6.0 the name loads the fragment:

```text recording=changes
get_template("entries.html#row").render(...): one partial of a template, loaded by its name
    5.2.17       TemplateDoesNotExist: entries.html#row
    6.0.8        '<li>Harbour</li>'
    6.1.1        '<li>Harbour</li>'
    this commit  '<li>Harbour</li>'
```

## Two dots in a variable

Since 6.1, a variable tag whose variable holds two dots in a row, as `{{ entry..title }}` does, warns as the template compiles. The empty name between the dots is looked up like any other part (`django/template/base.py:Variable._resolve_lookup`), which the 6.1 notes call "normally a mistake" (`docs/releases/6.1.txt`). A comment beside the warning in `Parser.parse` says that the form becomes an error when the deprecation ends, in Django 2028 (`django/template/base.py:Parser.parse`).

The value never changes; look for the warning, which 6.1 adds:

```text recording=changes
{{ entry..title }}: two dots in a variable
    5.2.17       ''
    6.0.8        ''
    6.1.1        '', warns RemovedInDjango70Warning
    this commit  '', warns RemovedInDjango2028Warning
```

`Parser.parse` checks only a variable, by `FilterExpression.is_var`, so a literal such as `{{ "a..b" }}` does not warn. The first release of 6.1 warned for a literal too; 6.1.1 stopped it (`docs/releases/6.1.1.txt`; [Variables and filters: `FilterExpression` and `Variable`](../templates/variables.md)).

> **Trap.** Only the variable that heads a variable tag is checked. `{% if entry..title %}` compiles without a warning, and its condition is false. Nor does `Parser.parse` look at a filter's argument such as `default:entry..title`, which fails only at render (`django/template/base.py:FilterExpression.resolve`).

## Custom tags and `parse_bits`

Since 6.1, a custom tag declared with `takes_context=True` is checked as the library's module is imported: its function's first parameter must be `"context"`. Until then `parse_bits`, which matches a tag's words to the function's signature, made the check as a template using the tag compiled. Each of the decorators `Library.simple_tag`, `Library.simple_block_tag` and `Library.inclusion_tag` now makes the check, and strikes `"context"`, as it decorates the function (`django/template/library.py:Library.simple_tag`; [Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md)).

The lines of 5.2.17 and 6.0.8 are the decoration passing; since 6.1 the decorator raises:

```text recording=changes
@register.simple_tag(takes_context=True) on def page_link(number): the decoration
    5.2.17       accepted
    6.0.8        accepted
    6.1.1        TemplateSyntaxError: 'page_link' is decorated with takes_context=True so it must have a first argument of 'context'
    this commit  TemplateSyntaxError: 'page_link' is decorated with takes_context=True so it must have a first argument of 'context'
```

> **Trap.** Since 6.1, a call of `parse_bits` that passes the argument takes_context is a `TypeError`, with no warning first. The 6.1 notes say only that the undocumented function no longer accepts it (`django/template/library.py:parse_bits`, `docs/releases/6.1.txt`).

## `{% querystring %}`

`{% querystring %}`, new in 5.1, writes a link's query string from the request's parameters and the template's (`docs/releases/5.1.txt`; [The built-in tags](../templates/tags.md)). Since 6.0 its result always begins with `"?"`: on a request for `"/entries/"` with no query string, it writes `"?"`, where 5.2.17 wrote nothing. Since 6.0 it also takes several positional mappings, applied in order before the keyword arguments (`django/template/defaulttags.py:querystring`). 5.2.17 refused two mappings as the template compiled: the tag "received too many positional arguments".

## What a template does not call: `"alters_data"`

Since 5.2, a template does not call the queryset's and `UserManager`'s methods that create rows. A callable that a variable's lookup finds is not called if it carries a true `"alters_data"`; the value becomes the engine's `"string_if_invalid"` (`django/template/base.py:Variable._resolve_lookup`). 5.2 set the flag on `QuerySet.create`, `QuerySet.bulk_create`, `QuerySet.get_or_create`, `QuerySet.update_or_create`, `UserManager.create_user`, `UserManager.create_superuser` and their coroutine twins, "to prevent side effects when rendering a template context" (`docs/releases/5.2.txt`). A manager's copies of the methods, made with `functools.wraps`, carry the flag too (`django/db/models/manager.py:BaseManager._get_queryset_methods`). So `{{ entries.create }}`, with a manager as entries, renders the empty string.

## Safe HTML: `format_html` and links without a scheme

Since 6.0, `format_html` refuses a call with nothing to format, which 5.0 deprecated. The function passes each argument through `conditional_escape` and marks the result safe (`django/utils/html.py:format_html`), so such a call would mark its text safe unexamined.

5.2.17's line is the deprecated call at work; the later lines are the refusal:

```text recording=changes
format_html("<b>journal</b>"): given nothing to format
    5.2.17       <b>journal</b>, warns RemovedInDjango60Warning
    6.0.8        TypeError: args or kwargs must be provided.
    6.1.1        TypeError: args or kwargs must be provided.
    this commit  TypeError: args or kwargs must be provided.
```

Since 6.0, `urlize` warns as it links a bare domain: the scheme it gives one, `"http://"`, becomes `"https://"` in Django 2028 (`django/utils/html.py:Urlizer.handle_word`). It is the function behind the filters `|urlize` and `|urlizetrunc` ([The built-in filters](../templates/filters.md)). When the transitional setting `URLIZE_ASSUME_HTTPS` is true, it gives `"https://"` already and does not warn. Django 2028 also removes the setting (`docs/internals/deprecation.txt`). 5.2.17 has no such setting, and gives `"http://"` without a warning. The 6.0 notes call the setting deprecated, but nothing warns when it is set (`docs/releases/6.0.txt`, `django/conf/__init__.py:Settings.__init__`).

## The smaller changes

The rest, to look up by name:

| what | change | where |
|---|---|---|
| `{{ forloop.length }}` | New in 6.0: the length of the loop's sequence; 5.2.17 renders nothing for it | `django/template/defaulttags.py:ForNode.render` |
| `Library.simple_block_tag` | New in 5.2: a tag with a body, whose function is given the body rendered, as `"content"` | `django/template/library.py:Library.simple_block_tag` |
| the filter `escapeseq` | New in 5.0: `conditional_escape` on each item of a sequence | `django/template/defaultfilters.py:escapeseq` |
| `format_html_join` | Since 5.2, an item that is a mapping is passed as keyword arguments | `django/utils/html.py:format_html_join` |
| `SafeString.__add__` | Since 5.2, it returns `NotImplemented` for an operand that is not a `str`, so the operand's `__radd__` is tried | `django/utils/safestring.py:SafeString.__add__` |
| the filter length_is | Gone in 5.1: a template that uses it fails to compile, `"Invalid filter: 'length_is'"` | `django/template/base.py:Parser.find_filter` |
| `BaseEngine.check` | New in 5.1: a backend's checks, which `check_templates` runs for every engine | `django/core/checks/templates.py:check_templates` |
| the tag `{% csp_nonce_attr %}` | New in 6.1: it renders the context's Content Security Policy nonce | [What changed in security: Content Security Policy and signing](security.md) |
