---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The template is rendered

How `render` turns a template's name and a dictionary into a string: the engine is made on first use from `settings.TEMPLATES`, its loaders find the file and compile it once, and rendering runs the context processors and then each node, which is where the queryset in the context is finally evaluated.

The view's second line is `render`, which calls `render_to_string` with the template's name, the context dictionary and the request, and wraps the string in an `HttpResponse` (`django/shortcuts.py:render`). Of the work between the name and the string, the first request makes the engine and compiles the template, and the process keeps both.

In the figure, the second request finds the compiled template at the cached loader and goes straight on to the context.

```text figure=name-to-string
time runs down; every request's steps down the left, one path; set in to the right, dashed, the first request's alone, each at the point where it does it

"journal/entries.html", from render
  -> get_template asks the engine
       | EngineHandler makes DjangoTemplates and its Engine from settings.TEMPLATES, kept for the process
       | the loaders made
  -> the cached loader looks the name up
     the second request finds the Template here
       | not found: the app-directories loader tries admin/templates, auth/templates, then reads journal's file
       | Lexer.tokenize and Parser.parse make a Template of nodes, which the cached loader stores
  -> a RequestContext, the view's dictionary on top
       | the context processors imported
  -> the context processors called: csrf, request, auth, messages
  -> the nodes rendered, the loop's values escaped; {% for %} takes the queryset's len, which sends the query
  -> a SafeString, which render makes an HttpResponse of
```

*From a template's name to the string of the response. Every request takes the steps down the left; a dashed box, set in to the right, is work the first request alone does, at the point where it does it.*

The first request's recording shows that work where it happens: the engine made inside the first `get_template`, the cached loader made, two directories raising `TemplateDoesNotExist` before journal's has the file, the compile, and the context processors imported. Last is the loop's `QuerySet.__len__`, which sends the query that [A queryset becomes SQL](query.md) follows. Other lines are left out.

```text recording=overview
render(request, "journal/entries.html", context)
  get_template('journal/entries.html')
    EngineHandler.__getitem__("django")
      DjangoTemplates.__init__
        Engine.__init__
    ...
            cached.Loader.__init__
          cached.Loader.get_template('journal/entries.html')
              filesystem.Loader.get_contents  (app_directories.Loader, in admin/templates)
                raises TemplateDoesNotExist
              filesystem.Loader.get_contents  (app_directories.Loader, in auth/templates)
                raises TemplateDoesNotExist
              filesystem.Loader.get_contents  (app_directories.Loader, in journal/templates)
              Template.__init__: the source is compiled
  Template.render(context, request)  (the backend's Template)
    ...
      Engine.template_context_processors: the context processors are imported
      ...
      ForNode.render  {% for entry in entries %}
        QuerySet.__len__
```

Two classes in it are called `Template`: the engine's is the compiled template, which renders, and the backend's is the thin wrapper around it that `get_template` returns, whose `render` makes the context (`django/template/base.py:Template`, `django/template/backends/django.py:Template`).

## The engine is made on first use

`get_template` asks each configured engine in turn for the template, and returns the first that has it (`django/template/loader.py:get_template`). The engines are held by `EngineHandler`, one object made when `django.template` is imported, which reads `settings.TEMPLATES` at its first use. `EngineHandler.__getitem__` makes an engine the first time its alias, here `"django"`, is asked for: it imports the backend class, calls it with the rest of the entry, and keeps the instance for the life of the process (`django/template/utils.py:EngineHandler.templates`, `django/template/utils.py:EngineHandler.__getitem__`).

`DjangoTemplates.__init__` fills in three options a project left out, autoescaping on among them, collects the template tag libraries, and makes the `Engine`, which holds the directories, the loaders and the libraries (`django/template/backends/django.py:DjangoTemplates.__init__`, `django/template/engine.py:Engine.__init__`).

> **Trap.** To collect the tag libraries, making the engine imports every module of Django's own `django/templatetags/` and of each installed application's package named `"templatetags"`, whether or not a template loads it. A module whose import raises `ImportError` makes `get_package_libraries` raise `InvalidTemplateLibrary`, and making the engine fails with it: a page that loads no library fails all the same (`django/template/backends/django.py:get_template_tag_modules`, `django/template/backends/django.py:get_package_libraries`).

`Engine.__init__` also decides the loaders. With none configured and `"APP_DIRS"` true, as here, a project gets the filesystem loader and the application-directories loader, both wrapped in the cached loader ([Template engines: `TEMPLATES` and the backends](../templates/engines.md)).

## Finding the file

`Engine.find_template` tries each loader until one returns a template, and here there is one, the cached loader, wrapping the other two. The loaders are made at its first call and kept, by the property `Engine.template_loaders` (`django/template/engine.py:Engine.find_template`, `django/template/engine.py:Engine.template_loaders`). The cached loader keeps a dictionary from a template's name to the compiled template, and remembers a name no loader has as a miss (`django/template/loaders/cached.py:Loader.get_template`). A name it has not seen it passes to the base loader's method, which walks the origins the child loaders offer and opens each until one exists (`django/template/loaders/base.py:Loader.get_template`).

The filesystem loader offers none here, `"DIRS"` being empty. The application-directories loader offers one per installed application with a `templates` directory, in the order of `settings.INSTALLED_APPS`: the admin's, the auth application's, then journal's. That is why the recording tries three files and reads the last (`django/template/loaders/app_directories.py:Loader.get_dirs`, `django/template/utils.py:get_app_template_dirs`, `django/template/loaders/filesystem.py:Loader.get_contents`). That order is also the order of precedence: journal, listed last here, would lose to a template of the same name in the admin's or the auth application's directory, which is why an application that overrides another's template is listed before it ([Finding a template: `Engine` and the loaders](../templates/loaders.md)).

## Compiled once

With the file's text in hand, the base loader makes a `Template` of `django/template/base.py`, whose constructor compiles it at once (`django/template/base.py:Template.__init__`). `Lexer.tokenize` splits the source into tokens, and `Parser.parse` turns them into nodes, handing each tag to the compile function registered for it (`django/template/base.py:Lexer.tokenize`, `django/template/base.py:Parser.parse`). The function for `"for"`, `do_for`, calls the parser again to collect the body up to `"endfor"` or `"empty"`, and returns a `ForNode` holding the loop variables, the sequence and the body (`django/template/defaulttags.py:do_for`). [From text to nodes: the lexer and the parser](../templates/compiling.md) has the compiling in full.

The cached loader stores the compiled template, and that is what the second request finds: its `get_template` reaches the cached loader and stops. The cache lasts as long as the process, unless the development server clears it when a file changes in a template directory outside Django's own (`django/template/autoreload.py:reset_loaders`).

## The context and its processors

The backend's `Template.render` calls `make_context`. A request was given, so it makes a `RequestContext` and pushes the view's dictionary on top of it (`django/template/backends/django.py:Template.render`, `django/template/context.py:make_context`). A context is a stack of dictionaries, looked up from the top. The view's dictionary sits above the slot `RequestContext.__init__` reserves for the context processors, so what the view passed wins over what a processor adds (`django/template/context.py:RequestContext.__init__`).

The engine's `Template.render` binds the template to the context, and binding runs the context processors (`django/template/base.py:Template.render`, `django/template/context.py:RequestContext.bind_template`). Their list, `Engine.template_context_processors`, is computed once per engine, which is the import in the recording: the builtin `csrf` first, then those the settings name, each imported by its dotted path (`django/template/engine.py:Engine.template_context_processors`). Each is called with the request, and the dictionaries they return are merged into the reserved slot.

`csrf` adds a lazy `"csrf_token"`, computed only if a template reads it (`django/template/context_processors.py:csrf`). The three a default project configures add the request, the user and `"perms"`, and the messages (`django/template/context_processors.py:request`, `django/contrib/auth/context_processors.py:auth`, `django/contrib/messages/context_processors.py:messages`). None of them looks anything up: `"user"` is still the lazy object the middleware set ([The context: `Context`, `RequestContext` and context processors](../templates/context.md)).

## Rendering the nodes

`NodeList.render` renders each node and joins the strings (`django/template/base.py:NodeList.render`). A text node returns its text. A `VariableNode` resolves its expression and then formats the value for output (`django/template/base.py:VariableNode.render`).

Resolving looks each dotted part up in turn: `"year"` is found in the view's dictionary, and `"entry.published"` is an attribute of a model instance (`django/template/base.py:Variable._resolve_lookup`). The filters are then applied in order, `date` formatting the date by its argument (`django/template/defaultfilters.py:date`). [Variables and filters: `FilterExpression` and `Variable`](../templates/variables.md) has the lookup in full.

Formatting is `render_value_in_context` (`django/template/base.py:render_value_in_context`). Autoescaping is on, so it passes the value as a string to `conditional_escape`, which escapes anything but a string that declares itself safe with an `__html__` method, as a `SafeString` does (`django/utils/html.py:conditional_escape`). Autoescaping is that test at each variable, not a pass over the output ([Autoescaping and safe strings](../templates/autoescape.md)).

`ForNode.render` is where the queryset meets the database. It resolves the sequence to the queryset and takes its length first, which decides whether the `"empty"` part renders instead and gives `"forloop"` its `"length"`, `"revcounter"` and `"last"`. That `len` is what sends the query (`django/template/defaulttags.py:ForNode.render`). For each item the node then sets the loop variable and renders the body, and iterating the queryset finds the results already fetched.

What comes out of `NodeList.render` is a `SafeString`, and `render_to_string` returns it to `render`, which makes the `HttpResponse` of it with no content type given, so the response takes the default: [The response returns to the server](response.md).
