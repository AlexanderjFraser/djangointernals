---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The template is rendered

How `render` turns a template's name and a dictionary into a string: the engine is made on first use from `settings.TEMPLATES`, its loaders find the file and compile it once, and rendering runs the context processors and then each node, which is where the queryset in the context is finally evaluated.

The view's second line is `render`, a shortcut of two lines itself: it calls `render_to_string` with the template's name, the context dictionary and the request, and wraps the string it gets in an `HttpResponse` (`django/shortcuts.py:render`). Everything between is the template system. This is the recording's first request, where the engine and its loaders are made and the template compiled; the lines of the query the loop runs are left out, and [A queryset becomes SQL](query.md) has them.

```text recording=overview
render(request, "journal/entries.html", context)
  get_template('journal/entries.html')
    EngineHandler.__getitem__("django")
      DjangoTemplates.__init__
        get_installed_libraries
        Engine.__init__
    DjangoTemplates.get_template('journal/entries.html')
      Engine.get_template('journal/entries.html')
        Engine.find_template('journal/entries.html')
          Engine.get_template_loaders
            cached.Loader.__init__
              Engine.get_template_loaders
                filesystem.Loader.__init__
                filesystem.Loader.__init__  (app_directories.Loader)
          cached.Loader.get_template('journal/entries.html')
            base.Loader.get_template('journal/entries.html')  (cached.Loader)
              filesystem.Loader.get_contents  (app_directories.Loader, in admin/templates)
                raises TemplateDoesNotExist
              filesystem.Loader.get_contents  (app_directories.Loader, in auth/templates)
                raises TemplateDoesNotExist
              filesystem.Loader.get_contents  (app_directories.Loader, in journal/templates)
              Template.__init__: the source is compiled
                Lexer.tokenize
                Parser.parse
                  do_for: {% for %} becomes a ForNode
                    Parser.parse
  Template.render(context, request)  (the backend's Template)
    make_context
      RequestContext.__init__
    Template.render(context)  (the engine's Template)
      Engine.template_context_processors: the context processors are imported
      context_processors.csrf
      context_processors.request
      auth.context_processors.auth
      messages.context_processors.messages
      VariableNode.render  {{ year }}
        conditional_escape
      VariableNode.render  {{ year }}
        conditional_escape
      ForNode.render  {% for entry in entries %}
        QuerySet.__len__
          QuerySet._fetch_all
        ...
        QuerySet.__iter__
          QuerySet._fetch_all
        VariableNode.render  {{ entry.published|date:"j F" }}
          defaultfilters.date(value, "j F")
          conditional_escape
        VariableNode.render  {{ entry.title }}
          conditional_escape
        VariableNode.render  {{ entry.published|date:"j F" }}
          defaultfilters.date(value, "j F")
          conditional_escape
        VariableNode.render  {{ entry.title }}
          conditional_escape
  HttpResponse.__init__(content)
    response["Content-Type"] = "text/html; charset=utf-8"
```

Two classes in the recording are called `Template`. The engine's, in `django/template/base.py`, is the compiled template, which renders; the backend's, in `django/template/backends/django.py`, is a thin wrapper around it that `get_template` returns and whose `render` makes the context (`django/template/base.py:Template`, `django/template/backends/django.py:Template`).

## The engine is made on first use

`get_template` asks each configured engine in turn for the template, and returns the first that has it; an engine that does not raises `TemplateDoesNotExist`, and the exceptions are chained onto the one raised when none has it (`django/template/loader.py:get_template`). The engines are held by `EngineHandler`, one object made when `django.template` is imported and empty until then. Its first use reads `settings.TEMPLATES`, gives each entry an alias, by default the second-last part of its backend's dotted path, `django` for Django's own, and then makes each engine on demand: `EngineHandler.__getitem__` imports the backend class and instantiates it with the rest of the entry, and keeps the instance for the life of the process (`django/template/utils.py:EngineHandler.templates`, `django/template/utils.py:EngineHandler.__getitem__`).

Making the Django backend is the costliest single step of this request. `DjangoTemplates.__init__` fills in the options a project left out, autoescaping on and debugging as `settings.DEBUG` has it, and then collects the template tag libraries: `get_installed_libraries` imports Django's own `django/templatetags/` and the package named `"templatetags"` of every installed application, with every module in them, and keeps the modules that have a `"register"`, which is why making the engine imports the admin's tag libraries, for a page that uses none of them (`django/template/backends/django.py:DjangoTemplates.__init__`, `django/template/backends/django.py:get_installed_libraries`). It then makes the `Engine`, the object that holds the directories, the loaders, the libraries and the three builtin libraries every template may use without loading them (`django/template/engine.py:Engine.__init__`).

The loaders are decided in `Engine.__init__` too. A project that configures none gets the filesystem loader for its `"DIRS"`, the application-directories loader as well when `"APP_DIRS"` is true, and both wrapped in the cached loader. That wrapping does not depend on `settings.DEBUG`: the cache is there in development too, and what the debug setting changes is the lexer used to compile, what a miss is cached as, and how much an exception raised while compiling or rendering is annotated with.

## Finding the file

`Engine.get_template` asks `Engine.find_template`, which tries each loader until one returns a template; the loaders themselves are made at the first call, by `Engine.template_loaders`, a property computed once by calling `Engine.get_template_loaders`; the cached loader's constructor calls the same method for its children, which is the nesting the recording shows (`django/template/engine.py:Engine.find_template`, `django/template/engine.py:Engine.template_loaders`).

The cached loader keeps a dictionary from a template's name, with the origins to skip when there are any, to the compiled template, or, for a template that does not exist, to the bare exception class when debugging is off and a copy of the exception when it is on; a name it has not seen it looks up with the method it inherits from the base loader (`django/template/loaders/cached.py:Loader.get_template`). That lookup walks the origins the child loaders offer and opens each until one exists (`django/template/loaders/base.py:Loader.get_template`). The filesystem loader offers one origin per directory in `"DIRS"`, none here. The application-directories loader offers one per installed application that has a `templates` directory, in the order of `settings.INSTALLED_APPS`: the admin's, the auth application's, and then journal's, which is why the recording tries three files and raises `TemplateDoesNotExist` twice before it reads one (`django/template/loaders/app_directories.py:Loader.get_dirs`, `django/template/utils.py:get_app_template_dirs`, `django/template/loaders/filesystem.py:Loader.get_contents`). The order of the applications is the order of precedence between templates of the same name, which is the mechanism by which a project overrides an application's template: the project's application comes first in the setting.

## Compiled once

With the file's text in hand, the base loader makes a `Template` of `django/template/base.py`, and the constructor compiles it at once (`django/template/base.py:Template.__init__`). `Template.compile_nodelist` runs two passes. `Lexer.tokenize` splits the source at every `{% %}`, `{{ }}` and `{# #}` into tokens of four kinds, text, variable, block and comment (`django/template/base.py:Lexer.tokenize`). `Parser.parse` then turns the tokens into a list of nodes: a text token becomes a `TextNode`; a variable token is compiled into a `FilterExpression`, which resolves the filter names to their functions now and keeps a constant argument like `"j F"` as a value, and is held by a `VariableNode`; a block token's first word names a tag, and the compile function registered for that tag is called with the parser (`django/template/base.py:Parser.parse`, `django/template/base.py:FilterExpression.__init__`). The function for `"for"`, `do_for`, parses the tag's words, then calls the parser again to collect the body up to `"endfor"` or `"empty"`, which is the inner `Parser.parse` in the recording, and returns a `ForNode` holding the loop variables, the sequence expression and the body (`django/template/defaulttags.py:do_for`).

The cached loader stores the compiled template, and the second request's recording shows what that buys: `get_template` reaches the cached loader and stops. No directory is walked, no file is opened, nothing is compiled. The cache lasts as long as the process. Under the development server a change to a template file clears it instead of restarting the process (`django/template/autoreload.py:reset_loaders`).

## The context and its processors

The engine's template is handed back inside the backend's `Template`, whose `render` is what `render_to_string` calls. It makes the context and renders (`django/template/backends/django.py:Template.render`). `make_context` makes a `RequestContext` because a request was given, and pushes the view's dictionary on top of it (`django/template/context.py:make_context`). A context is a stack of dictionaries, looked up from the top: the builtins `True`, `False` and `None` at the bottom, then an empty slot reserved for the context processors, then an empty dictionary for whatever is added later, then the view's dictionary, so that what the view passed wins over what a processor adds (`django/template/context.py:RequestContext.__init__`).

The engine's `Template.render` binds the template to the context, and binding is when the context processors run (`django/template/base.py:Template.render`, `django/template/context.py:RequestContext.bind_template`). The list is the engine's `Engine.template_context_processors`, computed once per engine: a builtin one first, then those the settings name, each imported by its dotted path (`django/template/engine.py:Engine.template_context_processors`). Each is called with the request and returns a dictionary, and the dictionaries are merged into the reserved slot. The builtin processor, `csrf`, adds a lazy `"csrf_token"` that is computed only if a template reads it (`django/template/context_processors.py:csrf`). Of the three a default project configures, `request` adds the request; `auth` adds the request's user as `"user"`, which is still the lazy object the middleware set, and `"perms"`; `messages` adds the request's messages and the level constants (`django/template/context_processors.py:request`, `django/contrib/auth/context_processors.py:auth`, `django/contrib/messages/context_processors.py:messages`). None of them looks anything up: a template that reads `"user"` is what would.

## Rendering the nodes

`NodeList.render` renders each node and joins the strings (`django/template/base.py:NodeList.render`). A text node returns its text. A `VariableNode` resolves its expression and then formats the value for output (`django/template/base.py:VariableNode.render`).

Resolving is `Variable._resolve_lookup`: for each dotted part it tries a dictionary key, then an attribute, then an integer index, and if what it finds is callable it calls it, unless the callable is marked `"do_not_call_in_templates"` or `"alters_data"`, which is how a model's `Model.delete` cannot be called from a template (`django/template/base.py:Variable._resolve_lookup`). So `"year"` is found in the view's dictionary, and `"entry.published"` is an attribute of a model instance. A name that resolves to nothing becomes the engine's `Engine.string_if_invalid`, which is empty by default: a template does not fail on a missing variable. The filters are then applied in order, `date` formatting the date by its argument (`django/template/defaultfilters.py:date`).

Formatting for output is `render_value_in_context`: a datetime is moved to the current time zone, a number is localised, which turns the year into the string `"2026"`, and then, because autoescaping is on, the value passes through `conditional_escape` (`django/template/base.py:render_value_in_context`, `django/utils/html.py:conditional_escape`). That function escapes anything except a value that declares itself safe by having an `__html__` method; a `SafeString`, which `mark_safe` makes and which the template system's own output is, passes through untouched. This is autoescaping: not a pass over the output, but a test at each variable, with the filters consulted on the way, since a filter may declare its output safe, and with the `{% autoescape %}` tag able to turn the test off for a block.

`ForNode.render` is where the queryset meets the database. It pushes a dictionary onto the context, resolves the sequence expression to the queryset, and takes its length, because the `"forloop"` variables it maintains include `"revcounter"` and `"last"`, which need the total before the first iteration; that `len` call is what sends the query, and [A queryset becomes SQL](query.md) follows it from there (`django/template/defaulttags.py:ForNode.render`). For each item it then sets the loop variable in the pushed dictionary and renders the body's nodes, and it pops the dictionary when the loop ends. The `QuerySet.__iter__` in the recording, after the `QuerySet.__len__`, is the loop itself beginning, and it finds the results already fetched.

What comes out of `NodeList.render` is a `SafeString`, and that is what `render_to_string` returns to `render`, which makes the `HttpResponse` of it, with no content type given, so the response takes the default: [The response returns to the server](response.md).
