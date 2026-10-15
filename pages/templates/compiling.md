---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# From text to nodes: the lexer and the parser

A Django template is compiled as its `Template` is made: `Template.compile_nodelist` cuts the source into tokens with a `Lexer` and builds the tree of nodes with a `Parser`, which hands a block tag to the compile function registered under its first word (`django/template/base.py:Template.compile_nodelist`). A **compile function** is given the parser and its tag's token, may drive the parser on to its end tag, and returns a node.

The work is divided so that the parser knows no tag. The lexer knows the delimiters and, but for one tag, nothing of what stands between them. The parser makes nodes of text and variables itself, and of a block tag knows only the first word, which it looks up in a table filled from libraries; a tag's arguments and its end tags are known only to its compile function. The grammar of the tags is the sum of the compile functions a template can see, a custom tag's too.

## Making a template is compiling it

`Template.__init__` ends by calling `Template.compile_nodelist`, so a `Template` that exists has been compiled (`django/template/base.py:Template.__init__`). Given no engine, it takes `Engine.get_default`, the engine of the first `DjangoTemplates` backend; given no origin, as by `Engine.from_string`, it makes an `Origin` named `UNKNOWN_SOURCE`.

With the engine's `"debug"` option on, `compile_nodelist` uses `DebugLexer`, which also records each token's start and end as `Token.position`; otherwise `Lexer` (`django/template/base.py:Template.compile_nodelist`). It gives the `Parser` the tokens, the origin, `Engine.template_builtins`, the libraries every template has, and `Engine.template_libraries`, those a template may name in `{% load %}` ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)). On success, `Parser.extra_data`, where a compile function can leave something for the template, is kept as `Template.extra_data`. On failure, the exception is raised again, with the debug data if `"debug"` is on, and a `TemplateSyntaxError` has the origin's name, if known, put before its message ([Template errors and debug information](debugging.md)).

## The lexer: `tag_re` and the four tokens

The lexer has one regular expression, `tag_re`, which matches a `{% … %}`, a `{{ … }}` or a `{# … #}` and captures it whole (`django/template/base.py:tag_re`). Split on a pattern with a capturing group, a string gives text and matches by turns, from text to text, and any text may be empty. `Lexer.tokenize` relies on that order: it flips a flag after every piece, so it knows a tag from text without looking, and passes each non-empty piece to `Lexer.create_token` (`django/template/base.py:Lexer.tokenize`). The pattern does not let `.` match a newline, so a tag ends on the line it began on: a `{# … #}` over two lines is text, and is printed.

`Lexer.create_token` makes a `Token` with a `Token.token_type`, which is `TokenType.TEXT`, `TokenType.VAR`, `TokenType.BLOCK` or `TokenType.COMMENT`; `Token.contents`, the text as written or, for a tag, what lies between its delimiters, stripped; and `Token.lineno`, the line it starts on (`django/template/base.py:Token`).

The lexer knows one tag by name. A block token whose contents are `"verbatim"`, or begin with `"verbatim "`, sets `Lexer.verbatim` to the end tag that will close it, `"endverbatim"` and the same words; until a block token has exactly those contents, every tag becomes a text token holding the tag as written (`django/template/base.py:Lexer.create_token`). The compile function of `{% verbatim %}` then parses only text, and renders it once into a node that prints the string (`django/template/defaulttags.py:verbatim`).

A compile function usually reads `contents` through `Token.split_contents`, which splits it at white space except inside quotes, and keeps a string marked for translation, `_("…")`, in one piece (`django/template/base.py:Token.split_contents`). For `{% include "fleet/ship_row.html" with title="The fleet of Valletta" only %}`, it gives:

```text
['include', '"fleet/ship_row.html"', 'with', 'title="The fleet of Valletta"', 'only']
```

The quotes stay on: telling a string from a variable is the compile function's work, usually by `Parser.compile_filter`.

## The parser

`Parser.__init__` reverses the list of tokens, so that, a comment says, `Parser.next_token`, `Parser.prepend_token` and `Parser.delete_first_token` work at the end of the list in constant time (`django/template/base.py:Parser.__init__`). It fills `Parser.tags` and `Parser.filters` from the builtin libraries with `Parser.add_library`, and keeps the named libraries for `{% load %}`, a compile function that adds to those tables from its token on ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)).

`Parser.parse` takes tokens until it meets a block tag whose first word is one of those it was given, or, given no end words, until no tokens are left, and returns the nodes it made as a `NodeList` (`django/template/base.py:Parser.parse`). For each token:

- A text token becomes a `TextNode`.
- A variable token becomes a `VariableNode` around a `FilterExpression` from `Parser.compile_filter`, whose filters `Parser.find_filter` finds at compile time ([Variables and filters: `FilterExpression` and `Variable`](variables.md)).
- A comment token is dropped.
- A block token whose first word was given is put back with `prepend_token`, and the parse returns. Any other is pushed, with its first word, onto `Parser.command_stack`, and the compile function found under that word in `tags` is called with the parser and the token. The node it returns joins the list, and the stack is popped.

The recursion is all in the compile functions: one that compiles a body into nodes calls `Parser.parse` with its own end words. So `{% endif %}`, `{% else %}` and `{% empty %}` are registered nowhere: each is a word a compile function hands to the parser, and met anywhere else is a tag the table does not hold.

`Parser.error` makes a `TemplateSyntaxError` of a message and attaches the token unless the exception has one (`django/template/base.py:Parser.error`). The parser's own errors go through it, as does any exception from a compile function; a nested parse attaches its token first, so the innermost tag is blamed.

`Parser.invalid_block_tag` reports a word the table does not hold, with any end words the current parse was waiting for, which is how a misnested end tag shows itself (`django/template/base.py:Parser.invalid_block_tag`). Here the `{% for %}` is never closed, so its parse meets `{% endif %}`:

```text
{# fleet/port_detail.html #}
<h1>{{ port.name }}</h1>
{% if ships %}
<ul>{% for ship in ships %}<li>{{ ship.name }}</li>
{% endif %}
```

```text
TemplateSyntaxError: Template: fleet/port_detail.html, Invalid block tag on line 5: 'endif', expected 'empty' or 'endfor'. Did you forget to register or load this tag?
```

Without the last line, the tokens run out inside the parse that `{% for %}` began, which does not know who called it; `command_stack` does, since the running compile function's tag is the last pushed and not yet popped. `Parser.unclosed_block_tag` pops it and names it (`django/template/base.py:Parser.unclosed_block_tag`):

```text
TemplateSyntaxError: Template: fleet/port_detail.html, Unclosed tag on line 4: 'for'. Looking for one of: empty, endfor.
```

Every node joins its list through `Parser.extend_nodelist`, which refuses a node whose `Node.must_be_first` is true, as only `ExtendsNode`'s is, once `NodeList.contains_nontext` says the list holds anything but a `TextNode` ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](inheritance.md)). It sets on the node its token and the parser's origin, by which a rendering error finds its line; a comment says why: it cannot change a node's `__init__` (`django/template/base.py:Parser.extend_nodelist`).

## Compile functions

A compile function is given the parser and its tag's token and must return a node: `Parser.extend_nodelist` reads `Node.must_be_first` from what it returns and sets two attributes on it, so in practice a `Node` (`django/template/base.py:Node`). In between it drives the parser: `Parser.parse` to compile up to its end words, `Parser.next_token` to take the token that stopped it, `Parser.delete_first_token` to drop that token unread, `Parser.compile_filter` for its arguments, and `Parser.skip_past` to discard tokens up to a word, which is how nothing inside a `{% comment %}` is compiled.

`do_if`, the compile function of `{% if %}`, shows the pattern (`django/template/defaulttags.py:do_if`). It compiles the condition at once with `TemplateIfParser` ([The built-in tags](tags.md)), parses to `"elif"`, `"else"` or `"endif"`, and takes the token that stopped it with `next_token`. While that token begins with `"elif"` it compiles another condition and parses again; on `"else"` it parses to `"endif"` alone; and the last token must be exactly `"endif"`, or `do_if` raises an error, laid at the `{% if %}`. Its `IfNode` holds pairs of a condition and a node list.

`do_for` checks the shape of `{% for ship in ships %}`, compiles the sequence, and parses to `"empty"` or `"endfor"`; on `"empty"` it parses again to `"endfor"` and drops that token with `delete_first_token` (`django/template/defaulttags.py:do_for`). `do_extends`, by contrast, parses with no end words, and the rest of the template becomes its node's body (`django/template/loader_tags.py:do_extends`).

`{% with %}`, `{% include %}` and the tags made by `Library.simple_tag`, `Library.simple_block_tag` and `Library.inclusion_tag` read named values with `token_kwargs` (`django/template/base.py:token_kwargs`). Given the rest of a split token as a list, it takes from the front each `name=value` it can, compiling the value, and stops at the first piece that is not one, leaving the rest to the tag. With `support_legacy=True` it reads the older `port.ships as ships and port.name as name` when the first piece is not a `name=value`.

## The tree: `child_nodelists` and `get_nodes_by_type`

A node that holds others names the attributes that hold them in `Node.child_nodelists`, by default `("nodelist",)`: `TextNode` and `VariableNode` name none, `ForNode` names `"nodelist_loop"` and `"nodelist_empty"`, and `IfNode` answers the default with a property that chains its branches (`django/template/base.py:Node.child_nodelists`). `Node.get_nodes_by_type` walks the tree through them and returns every node of a class (`django/template/base.py:Node.get_nodes_by_type`). It searches the tree without knowing its tags: `do_extends` refuses a second `{% extends %}` by it, and `ExtendsNode` collects the blocks of the child and of the root template.

A node that keeps its body under another name must say so. In a child template, a custom `{% shout %}` whose node keeps its body in an attribute named `"body"` hides a `{% block title %}` inside it from `{% extends %}`, and the parent's title is rendered instead; with `child_nodelists = ("body",)` on the node's class, the block is found.
