---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# What changed in templates

What changed in Django's template language and in the helpers that build safe HTML, from 5.0 to this commit: template partials, `{% querystring %}`, `{{ forloop.length }}`, `Library.simple_block_tag`, the deprecated two dots in a variable, the scheme `|urlize` assumes, the create methods a template no longer calls, and `format_html` without arguments.

A template is compiled once into a tree of nodes, which renders with a context ([Templates](../templates.md)), and the changes fall at both ends. The parser gained a store a tag can fill for the compiled template, on which partials are built, and a warning for two dots in a variable; rendering gained `{% querystring %}` and a loop's length, and stopped calling the methods of a queryset and of the user manager that create rows.

## Template partials and the parser's extra data

Since 6.0 a template can hold named fragments of itself. `{% partialdef ship_row %}` … `{% endpartialdef %}` defines one, which renders nothing where it stands unless the tag adds `"inline"`; `{% partial ship_row %}` renders it with the context at that point; and a name such as `"fleet/port_detail.html#ship_row"`, given to `Engine.get_template` and so to `render_to_string` and `{% include %}`, loads the fragment alone, a `PartialTemplate` (`django/template/defaulttags.py:partialdef_func`, `django/template/engine.py:Engine.get_template`). The store they rely on came in 5.1: `Parser.extra_data`, a dictionary a compile function may fill, which `Template.compile_nodelist` keeps as `Template.extra_data` once the parse succeeds; `{% partialdef %}` files each fragment there under `"partials"` (`django/template/base.py:Template.compile_nodelist`). [Template partials: `{% partialdef %}` and `{% partial %}`](../templates/partials.md) tells how a partial is made, found and rendered.

## Compiling: two dots, and tags made from functions

In `{{ port..name }}` the lookup's middle part is an empty name, tried as a key, an attribute and an index like any other (`django/template/base.py:Variable._resolve_lookup`). The release notes call this normally a mistake (`docs/releases/6.1.txt`), and since 6.1 `Parser.parse` warns with `RemovedInDjango2028Warning` as it compiles a variable tag whose variable holds two dots in a row; a comment there says the warning becomes an error when the deprecation ends (`django/template/base.py:Parser.parse`). The check is made only when the expression starts from a `Variable` (`FilterExpression.is_var`), so a string literal such as `{{ "a..b" }}`, translated or not, does not warn, since a fix in 6.1.1. The arguments of filters and tags are not checked: `{{ x|default:port..name }}` and `{% if port..name %}` compile without a warning. [Variables and filters: `FilterExpression` and `Variable`](../templates/variables.md) tells the lookup.

`Library.simple_block_tag` (5.2) makes a tag with a body from a function: the compile function parses up to the end tag, and at each render the body, rendered in the same context, is passed as the function's `"content"` argument (`django/template/library.py:Library.simple_block_tag`, `django/template/library.py:SimpleBlockNode.get_resolved_arguments`). `parse_bits`, which matches a tag's words against the function's signature, no longer takes the takes_context flag (6.1): each decorator given takes_context checks for a first parameter `"context"` as it runs, and strikes it from the list it passes (`django/template/library.py:parse_bits`, `django/template/library.py:Library.simple_tag`). [Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md) tells both.

## Rendering: `{% querystring %}`, the loop and `"alters_data"`

`{% querystring %}`, new in 5.1, writes a link's query string from the request's and the template's values, so that a link to the next page keeps the rest of the query (`django/template/defaulttags.py:querystring`). Its positional arguments must be mappings, and with none the request's `HttpRequest.GET` stands in; each mapping, then the keyword arguments, is applied in order to an empty `QueryDict`, where `None` removes a key. 6.0 made the result begin with `"?"` whatever it holds, and accepted several positional mappings: on a request for `"/ports/?q=brig&page=2"`, `{% querystring page=3 %}` renders `"?q=brig&amp;page=3"`, and `{% querystring q=None page=None %}` renders `"?"`. [The built-in tags](../templates/tags.md) has the tag, and `{{ forloop.length }}` (6.0), the sequence's length, which `ForNode.render` sets before the first item (`django/template/defaulttags.py:ForNode.render`). `{% csp_nonce_attr %}` (6.1) is told in [What changed in security: Content Security Policy and signing](security.md).

A callable a variable's lookup finds is not called if it carries a true `"alters_data"`: the value becomes the engine's `"string_if_invalid"`, unless a true `"do_not_call_in_templates"`, tested first, keeps the callable itself (`django/template/base.py:Variable._resolve_lookup`). In 5.2 the flag was set on `QuerySet.create`, `QuerySet.bulk_create`, `QuerySet.get_or_create`, `QuerySet.update_or_create`, `UserManager.create_user`, `UserManager.create_superuser` and their coroutine twins, to prevent side effects when a template is rendered, say the release notes (`django/db/models/query.py:QuerySet.create`, `django/contrib/auth/models.py:UserManager.create_user`, `docs/releases/5.2.txt`). A manager's copy of a queryset's method carries it too, being made with `functools.wraps` (`django/db/models/manager.py:BaseManager._get_queryset_methods`): given Port's manager as ports, `{{ ports.create }}` renders the empty string, and the table stays empty.

## Safe HTML and links

The function `urlize`, behind the filters `|urlize` and `|urlizetrunc`, links an address that begins `"http://"` or `"https://"`, and a name with no scheme, such as `"www.harbour.org"` or one ending in one of the seven original top-level domains (`django/utils/html.py:Urlizer`). Such a name still gets `"http://"`, with a `RemovedInDjango2028Warning` since 6.0, unless the transitional setting `URLIZE_ASSUME_HTTPS` is true, which gives it `"https://"` (`django/utils/html.py:Urlizer.handle_word`). Django 2028 gives every such name `"https://"` and removes the setting, which 6.0 deprecated with the change. Setting it raises no warning: the settings object warns for the other transitional settings, not this one (`django/conf/__init__.py:Settings.__init__`). [What still warns: the deprecations and the releases that end them](deprecations.md) lists it.

| name | what changed | release | where now |
|---|---|---|---|
| `escapeseq` | a new filter: each item through `conditional_escape`, for a list joined where autoescaping is off | 5.0 | `django/template/defaultfilters.py:escapeseq` |
| `format_html` | given no arguments, it would escape nothing and return its string marked safe; deprecated, then a `TypeError` | 5.0, 6.0 | `django/utils/html.py:format_html` |
| `format_html_join` | an item that is a mapping is passed to `format_html` as keyword arguments | 5.2 | `django/utils/html.py:format_html_join` |
| `SafeString.__add__` | returns `NotImplemented` for a right operand that is not a `str`, so the operand's `__radd__` is tried | 5.2 | `django/utils/safestring.py:SafeString.__add__` |

*The changes to the helpers of [Autoescaping and safe strings](../templates/autoescape.md).*

## Removed, and the engines' checks

The length_is filter was removed in 5.1, and a template that uses it now fails to compile with a `TemplateSyntaxError` that says `"Invalid filter: 'length_is'"` (`django/template/base.py:Parser.find_filter`, [The built-in filters](../templates/filters.md)). Since 5.1 a template backend has `BaseEngine.check`, which returns no messages unless overridden, and the check `check_templates` calls it on every engine; `DjangoTemplates.check` reports a `"string_if_invalid"` that is not a string, `"templates.E002"`, and a library name two modules use, `"templates.W003"` (`django/core/checks/templates.py:check_templates`, `django/template/backends/django.py:DjangoTemplates.check`, [Template engines: `TEMPLATES` and the backends](../templates/engines.md)).
