---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: read
owns: "`BaseHandler.load_middleware`, `BaseHandler._middleware_chain`"
---

# The middleware chain

When is the middleware chain of a `WSGIHandler` built, and from what?

`WSGIHandler.__init__` ends by calling the method named `"load_middleware"` on the handler being made, which on an instance of `WSGIHandler` itself is `BaseHandler.load_middleware` (`django/core/handlers/wsgi.py:WSGIHandler.__init__`). `BaseHandler.load_middleware` builds the chain from `settings.MIDDLEWARE`, taken in reverse, importing each entry with `import_string` (`django/core/handlers/base.py:BaseHandler.load_middleware`).

## What does `BaseHandler.load_middleware` build the chain from?

`BaseHandler.load_middleware` builds the chain from `settings.MIDDLEWARE`, taken in reverse, importing each entry with `import_string` (`django/core/handlers/base.py:BaseHandler.load_middleware`). What else its loop does with an entry is not this page's subject.

## Where is the chain kept?

`BaseHandler._middleware_chain` is `None` on the class (`django/core/handlers/base.py:BaseHandler._middleware_chain`). `BaseHandler.load_middleware` sets an attribute of that name on the handler in its last statement, after the loop (`django/core/handlers/base.py:BaseHandler.load_middleware`). The comment above that statement gives the reason for the place: the attribute is assigned only when initialization is complete, because it is used as the flag that says so (`django/core/handlers/base.py:BaseHandler.load_middleware`).

## When is the chain of a `WSGIHandler` built?

`WSGIHandler.__init__` ends by calling the method named `"load_middleware"` on the handler being made (`django/core/handlers/wsgi.py:WSGIHandler.__init__`). `WSGIHandler` declares no method of that name, so on an instance of `WSGIHandler` itself the call runs `BaseHandler.load_middleware`, and the chain is built when the handler object is made (`django/core/handlers/wsgi.py:WSGIHandler`). The figure puts what follows in order: the loop over `settings.MIDDLEWARE` in reverse, with `import_string` for each entry, and after the loop the last statement, which sets `BaseHandler._middleware_chain` on the handler and leaves the class's `None` as it was (`django/core/handlers/base.py:BaseHandler.load_middleware`).

```text figure=building-the-chain
WSGIHandler.__init__, when an instance of WSGIHandler itself is made
    calls BaseHandler.load_middleware
        for each entry of settings.MIDDLEWARE, in reverse:
            import_string(entry)
        after the loop, in its last statement:
            sets _middleware_chain on the handler; on the class it is None
```

*What happens when an instance of `WSGIHandler` itself is made: `BaseHandler.load_middleware` goes through the setting in reverse, and sets the chain on the handler only after its loop.*

A subclass that declares the method gets the call instead. `StaticFilesHandler` is a subclass of `WSGIHandler` whose mixin declares `StaticFilesHandlerMixin.load_middleware`, and that method does nothing: its comment says the middleware is already loaded for the application the handler wraps (`django/contrib/staticfiles/handlers.py:StaticFilesHandlerMixin.load_middleware`).

## Which test shows the chain being built?

`tests/handlers/tests.py:HandlerTests.test_middleware_initialized` makes a `WSGIHandler` and asserts that its `BaseHandler._middleware_chain` is not `None`.
