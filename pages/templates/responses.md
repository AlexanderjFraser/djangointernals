---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `SimpleTemplateResponse` and `TemplateResponse`

`SimpleTemplateResponse` and `TemplateResponse` are responses whose content is a template not yet rendered. They keep the template and the context, render them when `SimpleTemplateResponse.render` is called, run their post-render callbacks after it, and raise `ContentNotRenderedError` if their content is read before it.

A view that renders its template itself returns a finished response: nothing after the view can change the template or the context. A response that holds the ingredients lets the middleware's `process_template_response` hooks, and the decorators made from middleware, change the template or the context after the view has returned. The handler renders it once they have run ([The centre of the chain](../handlers/view.md#template-responses)); `django.shortcuts.render` renders at once ([The shortcuts](../views/shortcuts.md)).

## What the response holds

`SimpleTemplateResponse` is an `HttpResponse` that keeps what it will render with: the template as `SimpleTemplateResponse.template_name`, the context as `SimpleTemplateResponse.context_data`, an engine's alias as `SimpleTemplateResponse.using`, and the request as `SimpleTemplateResponse._request`, which it sets to `None`. `TemplateResponse` takes the request as its first argument and stores it there (`django/template/response.py:SimpleTemplateResponse.__init__`, `django/template/response.py:TemplateResponse`).

> **Why.** The constructor's comments explain the names: they say the test client's API reserves "template" and "context", and that the client overwrites the response's "request". The client sets "templates", "context" and "request" on the response it returns (`django/test/client.py:Client.request`).

In rendering, the request is the whole difference between the two. It goes to the template's `render`, and the Django backend makes a `RequestContext` from it, so that the engine's context processors run, or a plain `Context` when there is none (`django/template/context.py:make_context`; [The context: `Context`, `RequestContext` and context processors](context.md)). With the processor that adds the request installed, `{{ request.path }}` prints the path from a `TemplateResponse` and nothing from a `SimpleTemplateResponse`.

## Rendering late: `rendered_content`

`SimpleTemplateResponse.rendered_content` is a property that renders the template and returns the string without keeping it (`django/template/response.py:SimpleTemplateResponse.rendered_content`). It resolves both ingredients when read, so a hook that assigns `SimpleTemplateResponse.template_name` or changes `SimpleTemplateResponse.context_data` before the render changes what is rendered.

`SimpleTemplateResponse.resolve_template` gives a list or a tuple of names to `select_template` and a string to `get_template`, each with `SimpleTemplateResponse.using`, and returns anything else as it is (`django/template/response.py:SimpleTemplateResponse.resolve_template`). So a missing template is an error only at render time. Any other object should be a backend's template, whose `render` takes a dictionary and a request; a `django/template/base.py:Template` takes a context alone, and a response holding one raises `TypeError` when rendered.

`SimpleTemplateResponse.resolve_context` returns the context unchanged, for a subclass to override. The Django backend takes a dictionary or `None`, and refuses a `Context` with `TypeError: context must be a dict rather than Context.` (`django/template/response.py:SimpleTemplateResponse.resolve_context`, `django/template/context.py:make_context`)

## `render` and the post-render callbacks

`SimpleTemplateResponse.render` does its work once. On a response not yet rendered it assigns `SimpleTemplateResponse.rendered_content` to the content, then calls each callback in `SimpleTemplateResponse._post_render_callbacks`, in the order they were added. A callback that returns anything but `None` replaces the response: the callbacks after it are given the replacement, and `render` returns it, which is what the handler keeps (`django/template/response.py:SimpleTemplateResponse.render`). Called again, `render` does nothing and returns the response itself, not that replacement.

`SimpleTemplateResponse.add_post_render_callback` appends a callback, or, if the response is already rendered, calls it at once and discards what it returns (`django/template/response.py:SimpleTemplateResponse.add_post_render_callback`). Django adds callbacks in two places:

- The view's wrapper in a decorator made from a middleware registers the middleware's `process_response` as a callback on a template response, so that it sees the rendered content ([A middleware as a decorator](../views/middleware-decorators.md#a-template-response-is-finished-later)).
- `UpdateCacheMiddleware.process_response` caches a response with a callable `render` through a callback (`django/middleware/cache.py:UpdateCacheMiddleware.process_response`). It does not ask whether the response is rendered, and one from a view has been by the time a `process_response` sees it, in the chain or under `cache_page`; so the callback runs at once.

Two other places render a template response after asking `SimpleTemplateResponse.is_rendered`: `response_for_exception`, when an error view returned one, and the test case's assertions on content (`django/core/handlers/exception.py:response_for_exception`, `django/test/testcases.py:SimpleTestCase._assert_contains`).

## Content refused before a render: `ContentNotRenderedError`

`SimpleTemplateResponse._is_rendered` turns true in one place: the setter of `SimpleTemplateResponse.content`, which stores the value as `HttpResponse` does and marks the response rendered (`django/template/response.py:SimpleTemplateResponse.content`). The empty content the constructor passes to `HttpResponse.__init__` goes through that setter too, so the constructor sets the flag back to false after it. Until a render the getter of `content` and `SimpleTemplateResponse.__iter__` raise `ContentNotRenderedError`, and so does whatever reads `content`, `HttpResponse.text` and `HttpResponse.getvalue` among them.

> **Trap.** Assigning the content on an unrendered template response replaces the template, and `SimpleTemplateResponse.render` then does nothing. `HttpResponse.write` is not refused, and what it writes before the render is lost.

## Pickling: `__getstate__` and `rendering_attrs`

`SimpleTemplateResponse.__getstate__` refuses to pickle a response that is not rendered, with `ContentNotRenderedError`. From a rendered one it leaves out the attributes named in `SimpleTemplateResponse.rendering_attrs`: `template_name`, `context_data` and `_post_render_callbacks`, and for a `TemplateResponse`, whose list adds it, `_request` (`django/template/response.py:SimpleTemplateResponse.__getstate__`). Its docstring: pickle only rendered data, not the data used to construct the response. Unpickled, it is a finished response: `SimpleTemplateResponse.render` returns it unchanged, and a callback added to it runs at once. A response the cache middleware stores is pickled by the local-memory backend, for one (`django/core/cache/backends/locmem.py:LocMemCache.set`).
