# Names made at runtime

Verified against Django at `4fab678a0739d54401ccee7eb587553657c9f76e`.

Some of Django's names are in no file's syntax tree: a metaclass, a
descriptor or a call to `setattr` makes them as the code runs. The name gate
(`python tools/names.py`) accepts such a name only where it is declared with
the pointer to the code that makes it. A document may declare names for
itself in a block like the one below; the entries here hold for every
document. One entry a line: the name, the pointer, and after `#` anything.
Each entry is a claim and is verified like one.

```runtime-names
ROOT_URLCONF                 django/conf/__init__.py:Settings.__init__                   # the defaults do not define it; a project's settings module does, and each of its upper-case names is set here
process_exception            django/core/handlers/base.py:BaseHandler.load_middleware    # a method the handler looks for on a middleware instance; no class in Django declares one
process_template_response    django/core/handlers/base.py:BaseHandler.load_middleware    # the same
```
