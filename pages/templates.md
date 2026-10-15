---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: Templates and forms
contents: engines, loaders, compiling, variables, context, rendering, autoescape, inheritance, partials, libraries, tags, filters, loadable-libraries, responses, debugging
---

# Templates

Django's template system turns the name of a template and a dictionary of values into a string. It compiles a template's text into a tree of nodes, by default once, and renders the tree against a fresh context each time it is asked, escaping for HTML as it goes. Around that language sits a thin layer of pluggable template engines, configured by `TEMPLATES`, through which a view asks for a template by name.

A view that answers with a page has a template's name, `"fleet/port_detail.html"`, and some values: a port and its ships. Something has to find the file, which may be in a directory of the project or in the `templates` directory of any installed application; make sense of its text, in which `{{ port.name }}` stands for a value and `{% for ship in ships %}` for a loop; and write out a string with the values put in, each escaped so that a ship named `<Beagle>` prints as text and not as markup.

Reading and parsing the file for every request would waste most of the work, since the text does not change between requests and the values do. So the system does the work in two stages. **Compiling** reads the text and builds a tree of objects from its pieces of text, its variables and its tags. With the default loaders it is done once for each template, and the result is kept. **Rendering** walks that tree with a **context**, the values for this one response, and is done every time. Nearly everything in the chapter belongs to one stage or the other.

## Two layers in one package

`django.template` holds two systems that its own docstring calls independent (`django/template/__init__.py`). The first is a set of **template engines**. Each entry of the `TEMPLATES` setting names a **backend**, a subclass of `BaseEngine`, and the object `engines`, an `EngineHandler` made when `django.template` is imported, holds one backend for each entry, made at its first use. Django ships `django/template/backends/django.py:DjangoTemplates`, for its own language; `django/template/backends/jinja2.py:Jinja2`, for Jinja2; and `django/template/backends/dummy.py:TemplateStrings`, which fills in plain text with the standard library's `string.Template`. The functions of `django/template/loader.py` (`get_template`, `select_template`, `render_to_string`) ask each backend in turn for a template by name, and whatever template comes back is rendered by a method that takes a plain dictionary and, optionally, the request (`django/template/utils.py:EngineHandler`, `django/template/loader.py:get_template`).

The second is the **Django template language**, Django's own engine. Its centre is `Engine`, which holds the configuration: the directories, the loaders, the libraries of tags and filters, and options such as `"debug"` and `"string_if_invalid"`. A `DjangoTemplates` backend makes one `Engine` from its entry of `TEMPLATES`, asks it for every template it is asked for, and wraps each compiled template it returns in a small object that adapts the language's `Template.render`, which takes a `Context`, to the engine layer's, which takes a dictionary (`django/template/backends/django.py:DjangoTemplates.__init__`, `django/template/engine.py:Engine`, `django/template/backends/django.py:Template`).

The objects of the language, in the order a request meets them:

| object | what it is | made |
|---|---|---|
| `Engine` | the language's configuration and the entry to it | with its backend |
| a loader | finds a template's source by name and returns it compiled | at the engine's first use of its loaders |
| `Template` | a compiled template: its source, where it came from, and its tree of nodes | once for each template, kept by the cached loader |
| the lexer and the parser | cut the text into tokens and build the tree from them | for each compile |
| `Library` | a module's registry of tags and filters, which the parser draws on | when its module is first imported, at the latest as an engine that uses it is made |
| a node | one piece of the tree: a run of text, a variable, or a tag | when the template is compiled |
| `Context` | the values a render can see, as a stack of dictionaries | for each render |
| `RenderContext` | a second stack, for the nodes' own state | with each context |

*The objects of the Django template language. `Template` here is `django/template/base.py:Template`; the backend's wrapper of the same name is a different class.*

## Compiling: from text to a tree of nodes

A template is compiled when its `Template` is made: the constructor calls `Template.compile_nodelist`, which runs a lexer and then a parser over the source (`django/template/base.py:Template.compile_nodelist`). Take this template:

```text
{# fleet/port_detail.html #}
<h1>{{ port.name }}</h1>
{% if ships %}<ul>{% for ship in ships %}<li>{{ ship.name|upper }}</li>{% endfor %}</ul>{% endif %}
```

The **lexer** knows the delimiters and, of the tags, only `{% verbatim %}`, inside which it turns everything up to the matching end tag into text. It splits the text with one regular expression that matches `{% … %}`, `{{ … }}` and `{# … #}`, and makes a **token** of each piece: a text token for what lies between tags, a variable token for `{{ … }}`, a block token for `{% … %}`, and a comment token for `{# … #}`, each holding its contents with the delimiters stripped (`django/template/base.py:Lexer.tokenize`, `django/template/base.py:Lexer.create_token`).

The **parser** turns the flat list into a tree (`django/template/base.py:Parser.parse`). It takes the tokens in order. A text token becomes a `TextNode`. A variable token becomes a `VariableNode`, holding a `FilterExpression` that has already parsed `ship.name|upper` into a variable and a list of filters. A comment token becomes nothing. A block token's first word names a tag, and the parser looks that word up in its table of **compile functions** and calls the function with itself and the token. The function returns a node, and on the way it may ask the parser to go on parsing until one of the end tags it expects: the function for `if` calls `Parser.parse` with `"elif"`, `"else"` and `"endif"`, and gets back the nodes in between. That recursion is how the tree gets its depth, and it is why an end tag leaves no node of its own. A tag the table does not hold is an error at compile time, with the template's line.

```text figure=text-to-tree
the text
  <h1>{{ port.name }}</h1>
  {% if ships %}<ul>{% for ship in ships %}<li>{{ ship.name|upper }}</li>{% endfor %}</ul>{% endif %}

Lexer.tokenize: a flat list of tokens
  TEXT "<h1>"     VAR "port.name"     TEXT "</h1>\n"
  BLOCK "if ships"     TEXT "<ul>"     BLOCK "for ship in ships"
  TEXT "<li>"     VAR "ship.name|upper"     TEXT "</li>"
  BLOCK "endfor"     TEXT "</ul>"     BLOCK "endif"

Parser.parse: a tree of nodes
  TextNode "<h1>"
  VariableNode  port.name
  TextNode "</h1>\n"
  IfNode  if ships
      TextNode "<ul>"
      ForNode  for ship in ships
          TextNode "<li>"
          VariableNode  ship.name|upper
          TextNode "</li>"
      TextNode "</ul>"
```

*The lexer cuts the text at every tag into a flat list of tokens. The parser builds the tree: the compile functions of `if` and `for` each parse the tokens up to their end tag and keep the nodes they get back, so the end tags leave no node. (The comment's line and the file's last newline are left out.)*

The table of compile functions is filled from **libraries**. Every `Engine` has three built in, the modules `django.template.defaulttags`, `django.template.defaultfilters` and `django.template.loader_tags`, and any library it is given as a builtin; their tags and filters are in every template. Other libraries, such as those in the templatetags package of an application, are known to the engine by name and reach a template's parser only through `{% load %}` (`django/template/engine.py:Engine.__init__`, `django/template/base.py:Parser.add_library`).

## Finding a template, once

`Engine.get_template` asks the engine's loaders for the name, in order, and the first that finds it wins (`django/template/engine.py:Engine.find_template`). Unless `"OPTIONS"` names loaders of its own, an engine has one: the **cached loader**, wrapped around the filesystem loader, which looks in the directories of `"DIRS"`, and, when `"APP_DIRS"` is true, the application directories loader, which looks in each installed application's `templates` directory. The source is read and the `Template` made, and so compiled, as soon as the name is found (`django/template/loaders/base.py:Loader.get_template`). The cached loader keeps the compiled template under a key made from its name, and the next request for that name gets the same object without reading or parsing anything (`django/template/loaders/cached.py:Loader.get_template`). A compiled template is therefore shared by every request for it that the process serves, which is why a node must keep what it learns during a render out of itself, in the context or the render context.

## Rendering: walking the tree with a context

The backend's template is given a dictionary and the request. It makes a `Context` with the dictionary on top, or, when there is a request, a `RequestContext`, and calls the compiled template's `render` (`django/template/backends/django.py:Template.render`, `django/template/context.py:make_context`).

A context is a stack of dictionaries. A name is looked up from the top down, and a tag that introduces names for its body, as `for` and `with` do, pushes a dictionary for them and pops it when its body is done, so that they vanish at its end tag. A `RequestContext` also runs the engine's **context processors**, functions of the request that each return a dictionary of names (the CSRF token, the user, the request itself), when the template starts to render, and puts their names below the view's (`django/template/context.py:BaseContext`, `django/template/context.py:RequestContext.bind_template`).

`Template.render` then renders its `NodeList`: each node renders itself to a string, and the strings are joined (`django/template/base.py:Template.render`, `django/template/base.py:NodeList.render`). A `TextNode` returns its text. A `VariableNode` asks its `FilterExpression` for a value, which looks the variable up in the context (each part of its dotted name tried as a key, then as an attribute, then as a number used as an index, and what it finds called if it can be called, unless it is marked not to be) and passes it through the filters; it then turns the value into a string, localised, and escaped for HTML unless the context has autoescaping off or the value is already marked safe (`django/template/base.py:VariableNode.render`, `django/template/base.py:render_value_in_context`). A tag's node does what the tag means: the `IfNode` renders the nodes of the first condition that holds, the `ForNode` renders its body once for each ship. With two ships named Endeavour and `<Beagle>`, `"fleet/port_detail.html"` renders as `"\n<h1>Valletta</h1>\n<ul><li>ENDEAVOUR</li><li>&lt;BEAGLE&gt;</li></ul>\n"`: the comment leaves only its line's newline, and the second name has gone through `upper` and then been escaped.

What the nodes need to remember while one template renders, such as the position of a `{% cycle %}` or the blocks of an inheritance chain, they ordinarily keep in the context's `render_context` ([Rendering: nodes and the render context](templates/rendering.md)), a second stack that `Template.render` pushes as it starts and pops as it ends, so that each template rendered through it starts with an empty level of its own (`django/template/context.py:RenderContext`). Inheritance itself is a matter of rendering: in a template that begins with `{% extends %}`, everything after the tag is parsed into one `ExtendsNode`, which at render time finds the parent template and renders the parent's tree in its place, with the child's blocks put where the parent's stand ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](templates/inheritance.md)) (`django/template/loader_tags.py:ExtendsNode.render`).

## Where templates meet the rest of Django

A view usually reaches templates through `django.shortcuts.render`, which calls `render_to_string` and puts the string in a response ([The shortcuts](views/shortcuts.md)), or by returning a `TemplateResponse`, which holds a template, or its name, and a context, and is rendered by the handler after the template-response middleware have seen it ([The centre of the chain](handlers/view.md#template-responses)). The development server's autoreloader watches the template directories and empties the loaders' caches when a template changes ([The autoreloader](commands/autoreload.md)), and the system checks ask each engine for its own ([The system checks](commands/checks.md)). When the engine's `"debug"` option is on, an error in a template carries the template's lines to the debug page ([The debug pages and `ExceptionReporter`](views/debug.md)). Forms and their widgets render through templates by way of a form renderer ([Forms](forms.md)). The tags for translation, static files and the cache are libraries of `django.templatetags`, each loaded by name, and the machinery behind them belongs to [Internationalization and time zones](i18n.md), [Content types, static files and the other contrib apps](contrib.md) and [Caching, files, mail, signals and tasks](services.md).
