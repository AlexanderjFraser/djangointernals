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
```
