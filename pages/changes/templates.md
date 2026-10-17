---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in templates

What changed in Django's template language and its safe-HTML helpers from 5.0 to this commit: template partials, `{% querystring %}`, `{{ forloop.length }}`, two dots in a variable, `parse_bits`, the queryset's and `UserManager`'s methods that create rows, which a template no longer calls, `format_html` without arguments, and the scheme `django.utils.html.urlize` gives a bare domain.

A template is compiled, by default once, into a tree of nodes, which renders with a context ([Templates](../templates.md)), and both halves changed. The compiler gained a place where a tag can leave data for the compiled template (5.1), on which 6.0 built **template partials**: named fragments of a template, which a name with a `"#"` loads alone. Rendering gained `{% querystring %}` (5.1), for the query string a template had built with a loop, and the loop's length (6.0).

Other changes make templates and their helpers stricter. 6.1 deprecates two dots in a variable, and refuses, as it is decorated, a custom tag that is declared to take the context and lacks its `"context"` parameter; 6.0 refuses `format_html` with nothing to format; since 6.0 linking a bare domain warns, unless `URLIZE_ASSUME_HTTPS` is true, that its scheme will change; and since 5.2 a template does not call the queryset's and `UserManager`'s methods that create rows.

## Template partials, on the parser's extra data

In 5.1 the parser gained `Parser.extra_data`, a dictionary in which a tag's compile function may leave data, kept as `Template.extra_data` once the parse succeeds (`django/template/base.py:Template.compile_nodelist`); partials (6.0) are built on it. `{% partialdef row %}` … `{% endpartialdef %}` files a `PartialTemplate` there under `"partials"`, and renders nothing where it stands unless the tag adds `"inline"` (`django/template/defaulttags.py:partialdef_func`); `{% partial row %}` renders the fragment in the context at that point (`django/template/defaulttags.py:PartialNode.render`). A name such as `"entries.html#row"`, given to `Engine.get_template` and so to `render_to_string` and `{% include %}`, is split at its first `"#"`: the template before it is loaded, and the partial filed under the rest returned (`django/template/engine.py:Engine.get_template`). The 6.0 notes give the purpose, "to encapsulate and reuse small named fragments within a template file", and a guide for users of django-template-partials (`docs/releases/6.0.txt`).

The recording loads one fragment by name:

```text recording=changes
get_template("entries.html#row").render(...): one partial of a template, loaded by its name
    5.2.17       TemplateDoesNotExist: entries.html#row
    6.0.8        '<li>Harbour</li>'
    6.1.1        '<li>Harbour</li>'
    this commit  '<li>Harbour</li>'
```

5.2.17 looks for a template named `"entries.html#row"`, `"#"` and all; from 6.0.8 the fragment renders alone ([Template partials: `{% partialdef %}` and `{% partial %}`](../templates/partials.md)).

## Two dots in a variable

In `{{ entry..title }}` the empty name between the dots is looked up like any other part (`django/template/base.py:Variable._resolve_lookup`). 6.1 deprecated the form, "normally a mistake" in its notes (`docs/releases/6.1.txt`): `Parser.parse` warns as it compiles a variable tag whose variable holds two dots in a row, and a comment there says it becomes an error when the deprecation ends, in Django 2028 (`django/template/base.py:Parser.parse`).

```text recording=changes
{{ entry..title }}: two dots in a variable
    5.2.17       ''
    6.0.8        ''
    6.1.1        '', warns RemovedInDjango70Warning
    this commit  '', warns RemovedInDjango2028Warning
```

A literal is not checked (`FilterExpression.is_var`): `{{ "a..b" }}` warns under neither 6.1.1 nor this commit, 6.1.1 having stopped 6.1's warning for them (`docs/releases/6.1.1.txt`; [Variables and filters: `FilterExpression` and `Variable`](../templates/variables.md)).

> **Trap.** Only the variable that heads a variable tag is checked. `{% if entry..title %}` compiles without a warning under 5.2.17 and every release since, its condition false, and `Parser.parse` does not look at a filter's argument such as `default:entry..title`, which fails only at render (`django/template/base.py:FilterExpression.resolve`).

## Custom tags and `parse_bits`

6.1 changed where `takes_context=True` is checked. Until then `parse_bits`, which matches a tag's words to the function's signature as a template compiles, was given that flag; the 6.1 notes say only that the undocumented function no longer accepts it (`docs/releases/6.1.txt`), and an old call with it is a `TypeError` from 6.1.1, with no warning before. Each of the decorators `Library.simple_tag`, `Library.simple_block_tag` and `Library.inclusion_tag` now checks that the function's first parameter is `"context"`, and strikes it, as it decorates the function (`django/template/library.py:Library.simple_tag`):

```text recording=changes
@register.simple_tag(takes_context=True) on def page_link(number): the decoration
    5.2.17       accepted
    6.0.8        accepted
    6.1.1        TemplateSyntaxError: 'page_link' is decorated with takes_context=True so it must have a first argument of 'context'
    this commit  TemplateSyntaxError: 'page_link' is decorated with takes_context=True so it must have a first argument of 'context'
```

Until 6.1 the error came from `parse_bits`, as a template using the tag compiled; now it comes as the library's module is imported ([Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md)).

## `{% querystring %}`

`{% querystring %}`, new in 5.1, writes a link's query string from the request's parameters and the template's, where a template had looped over them (`docs/releases/5.1.txt`). 6.0 let it take several positional mappings, applied in order before the keyword arguments, and made the result always begin with `"?"` (`django/template/defaulttags.py:querystring`): on a request for `"/entries/"`, `{% querystring %}` wrote nothing under 5.2.17 and `"?"` from 6.0.8, and two mappings, which 5.2.17 refused at compile time ("received too many positional arguments"), make one query string from 6.0.8 ([The built-in tags](../templates/tags.md)).

## What a template does not call: `"alters_data"`

A callable that a variable's lookup finds is not called if it carries a true `"alters_data"`; the value becomes the engine's `"string_if_invalid"` (`django/template/base.py:Variable._resolve_lookup`). 5.2 set the flag on `QuerySet.create`, `QuerySet.bulk_create`, `QuerySet.get_or_create`, `QuerySet.update_or_create`, `UserManager.create_user`, `UserManager.create_superuser` and their coroutine twins, "to prevent side effects when rendering a template context" (`docs/releases/5.2.txt`). A manager's copies, made with `functools.wraps`, carry it too (`django/db/models/manager.py:BaseManager._get_queryset_methods`): with a manager as entries, `{{ entries.create }}` renders the empty string under 5.2.17, which already carries 5.2's change, and every release since.

## Safe HTML: `format_html` and links without a scheme

`format_html` passes each argument through `conditional_escape` and marks the result safe (`django/utils/html.py:format_html`), so a call with nothing to format would mark its text safe unexamined. 5.0 deprecated such a call, and 6.0 refuses it:

```text recording=changes
format_html("<b>journal</b>"): given nothing to format
    5.2.17       <b>journal</b>, warns RemovedInDjango60Warning
    6.0.8        TypeError: args or kwargs must be provided.
    6.1.1        TypeError: args or kwargs must be provided.
    this commit  TypeError: args or kwargs must be provided.
```

`urlize`, behind the filters `|urlize` and `|urlizetrunc`, links a name without a scheme that begins `"www."` or whose domain ends in one of the seven original top-level domains, and gives it `"http://"`, or `"https://"` when the transitional setting `URLIZE_ASSUME_HTTPS` is true (`django/utils/html.py:Urlizer.handle_word`). 6.0 deprecated the default, which Django 2028 makes `"https://"`, removing the setting (`docs/internals/deprecation.txt`). A bare domain gets `"http://"` under 5.2.17 and every release since, warning from 6.0.8, and, with the setting made true by `override_settings`, `"https://"` and no warning from 6.0.8 (5.2.17 has no such setting). The 6.0 notes call the setting deprecated, but nothing warns when it is set (`docs/releases/6.0.txt`, `django/conf/__init__.py:Settings.__init__`).

## The smaller changes

The rest, to look up by name:

| name | what changed | release | where now |
|---|---|---|---|
| `{{ forloop.length }}` | new: the sequence's length; 5.2.17 renders nothing for it | 6.0 | `django/template/defaulttags.py:ForNode.render` |
| `Library.simple_block_tag` | new: a tag with a body, passed rendered as `"content"` | 5.2 | `django/template/library.py:Library.simple_block_tag` |
| `escapeseq` | a new filter: `conditional_escape` on each item of a sequence | 5.0 | `django/template/defaultfilters.py:escapeseq` |
| `format_html_join` | an item that is a mapping is passed as keyword arguments | 5.2 | `django/utils/html.py:format_html_join` |
| `SafeString.__add__` | `NotImplemented` for an operand not a `str`, so its `__radd__` is tried | 5.2 | `django/utils/safestring.py:SafeString.__add__` |
| the filter length_is | removed: a template that uses it fails to compile, `"Invalid filter: 'length_is'"` | 5.1 | `django/template/base.py:Parser.find_filter` |
| `BaseEngine.check` | new: a backend's checks, which `check_templates` runs for every engine | 5.1 | `django/core/checks/templates.py:check_templates` |
| `{% csp_nonce_attr %}` | a new tag, for a Content Security Policy nonce | 6.1 | [What changed in security: Content Security Policy and signing](security.md) |
