#!/usr/bin/env python3
"""The name gate: every name in a document's code spans exists in the pinned trees.

    python tools/names.py DOC [DOC ...]       check each document
    python tools/names.py --spans DOC ...     list every code span, what the gate took it for, and for
                                              a name where it was found
    python tools/names.py --tree NAME=DIR ... check against the tree at DIR in place of NAME's pinned one
    python tools/names.py --probe             prove the gate accepts and refuses as this says

A DOC is a markdown file, or a directory, which stands for every .md under it. Each command
takes `--root DIR`, the book's root. The trees are pin.json's (tools/pin.py); the code spans
are read as tools/pointers.py reads them, and resolved by the same walk of the syntax tree.

What is checked. A code span is one of four things:

    a pointer   as tools/pointers.py defines one: that gate's, not checked here
    a name      names joined by dots, with `()` after it or `@` before it allowed
    a call      a name, a parenthesis and anything after: the name before the parenthesis
                is checked and the rest is not
    other       anything else (white space, quotes, operators, a number): code or literal
                text, not checked, counted in the last line and listed by --spans. A file's
                name is other too: dotted names that end in py, pyi, toml, cfg, ini, yml,
                yaml, rst, txt or md (`settings.py`). A file the tree holds is better
                written as a pointer.

How a name is written, and where it is looked for, in this order:

1. From its module: `django.db.models.query.QuerySet.filter`. The longest run of leading
   names that is a module of a pinned tree is the module; the rest is found in it. An import
   is followed to what it imports, `import *` included (by `__all__` where that is written
   out as strings), so `django.db.models.QuerySet` is a name too.
2. Through an object the book says stands for a module or a class (map.json, below):
   `settings.MIDDLEWARE` is looked for in the file of the defaults, and `settings.configure`
   then on the class of the object. Nothing else is looked for under that first name.
3. By itself: `QuerySet`, `QuerySet.filter`, `get_resolver`, `MIDDLEWARE`. The first name is
   a class, a function or an assigned name at the module level of exactly one file of the
   indexed packages: the subject's source packages (map.json's "source", locale directories
   aside) and each pinned library's own package. (A name a file imports, with a fallback
   assigned beside the import or without, is not that file's definition; nor is one it
   deletes again with `del`.) When more than one file defines it, it
   means what it means in the file most recently named in full: by a pointer on the same
   line, else by the nearest pointer above (a name written from its module, way 1, names
   its file as a pointer does). That file may define the name or import it from a pinned
   tree: after a pointer into a file that has `from django.db import models`,
   `models.Model` is a name. Unbound, it fails, and the files that define it are listed. A
   name the index does not hold (a test's) is found the same way, in a file a pointer has
   named.
4. As Python's own: a keyword, a builtin and its members (`len`, `dict.get`,
   `type.__call__`), a special method or attribute name the language defines (`__init__`,
   `__traceback__`; the list is in this file), `self`, `cls`, `args`, `kwargs`. A bare
   builtin or special name that exactly one indexed file also defines is that file's
   (`Warning`); one that several define is Python's, unless a pointer has named a file.
5. From the standard library, with its module: `asyncio.Lock`, `threading.local`. The
   standard library is not pinned: the name is checked by importing it, in the Python that
   runs the gate, so a verdict can differ between machines and Python versions; where the
   module cannot be imported (`fcntl` on Windows) the name is counted as not checked. The
   last line of a run says which Python it was.
6. From a library the subject imports that the book does not pin: accepted on its first
   name alone, and counted as not checked.

A name the code imports only under `if TYPE_CHECKING:`, or defines and then deletes, is
refused: it is no name when the code runs. Where a name written from its module, or found
through a named file, runs into an import of something outside the pinned trees
(`django.utils.timezone.datetime.now`), the rest is the standard library's to answer for
(way 5) or an unpinned library's (way 6). Where it runs into the object that stands for a
module (`django.conf.settings.DEBUG`), the rest is looked for as in way 2.

Where the order surprises. A bare builtin's name that several files define is Python's, but
its members are not looked for (`format.__doc__` is refused as ambiguous); a builtin's name
that one file defines is that file's, members and all (`Warning.with_traceback` is refused
as Django's `Warning`). A name declared as made at runtime with no class (`ROOT_URLCONF`)
also passes after a word that stands for a module (`settings.ROOT_URLCONF`), whatever the
name is.

A member is one its class's own body declares (tools/pointers.py: a method, a class
attribute, a nested class, a slot, an attribute its methods assign on `self`). An inherited
member fails, and the message names the base that declares it where the gate can find it:
`Class.member` is written on the declaring class. A member written without its class fails
when it is a call, `.save()`; `.save` alone is read as other, like `.py`.

A name made at runtime (by a metaclass, `contribute_to_class`, `setattr`, a descriptor, a
module's `__getattr__`; or a setting the defaults do not define) exists in no syntax tree.
It is declared, with the pointer to the code that makes it, in a fenced block:

    ```runtime-names
    Model.objects    django/db/models/base.py:ModelBase._prepare
    ROOT_URLCONF     django/urls/resolvers.py:get_resolver      # read there, defined nowhere
    ```

One entry a line: the name, the pointer, and after `#` anything. A block in a document
declares for that document; the blocks of the book's list (map.json) declare for every
document. A declaration is checked: the pointer must resolve; the name's class must be a
class; a name the source itself declares is refused. Nothing can be checked after a name
made at runtime (`Model.objects.filter`): the member is written on its own class.

map/map.json:

    "source": ["django"],                the packages indexed, as tools/map_source.py maps them
    "locale_dir": "locale",
    "standard_library": ["annotationlib"],        added to what the running Python lists
    "names": {
      "runtime": "runtime-names.md",     optional: the book's list, a file beside map.json
      "stand_for": {"settings": ["django/conf/global_settings.py",
                                 "django/conf/__init__.py:LazySettings"]}
    }                                    optional: a first name that stands for a module's file
                                         or a class, or for several, looked in in that order

What the gate does not check: that a name means what its sentence takes it to mean (a bare
word passes when any indexed module defines it at its top, as `request`, `receiver` and
`signal` do in Django: `--spans` shows what each name was found to be); the arguments of a
call; a name in a fenced block or a figure; a name outside a code span; the standard library
against a pinned tree, or an unpinned library at all. It reads a document as
tools/pointers.py does, so a name in an indented code block or an HTML comment is checked
like prose. A name bound by `for`, `with`, `global`, a walrus or `import *` alone is not in
the index. A member a metaclass, a decorator or name mangling takes away again still passes
(a form's declared fields, a model's `Meta`, a dataclass field without a default,
`__private` names): the gate reads what the class body binds, not what the class ends up
with.

Vendored: the copy in a book's repository is written by a command and is not edited there.
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import importlib
import io
import json
import keyword
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pin  # noqa: E402
import pointers as pt  # noqa: E402  (the spans, the trees and the walk are that gate's)
from pointers import Unresolved  # noqa: E402

MAP_DIR, CONFIG = "map", "map.json"
NAME = re.compile(r"@?(" + pt.SYMBOL.pattern + r")(\(.*)?")
BARE_CALL = re.compile(r"\.[A-Za-z_][A-Za-z0-9_]*\(.*")
SPECIAL = set("""
    __abs__ __add__ __aenter__ __aexit__ __aiter__ __all__ __and__ __anext__ __annotations__ __await__
    __bool__ __bytes__ __call__ __class__ __class_getitem__ __complex__ __contains__ __copy__ __deepcopy__
    __del__ __delattr__ __delete__ __delitem__ __dict__ __dir__ __divmod__ __doc__ __enter__ __eq__
    __exit__ __file__ __float__ __floordiv__ __format__ __ge__ __get__ __getattr__ __getattribute__
    __getitem__ __getnewargs__ __getstate__ __gt__ __hash__ __iadd__ __iand__ __init__ __init_subclass__
    __instancecheck__ __int__ __invert__ __ior__ __isub__ __iter__ __le__ __len__ __length_hint__
    __lt__ __main__ __matmul__ __missing__ __mod__ __module__ __mro__ __mul__ __name__ __ne__ __neg__
    __new__ __next__ __or__ __path__ __pos__ __pow__ __prepare__ __qualname__ __radd__ __rand__
    __reduce__ __reduce_ex__ __repr__ __reversed__ __rmul__ __ror__ __round__ __rsub__ __set__
    __set_name__ __setattr__ __setitem__ __setstate__ __slots__ __str__ __sub__ __subclasscheck__
    __subclasses__ __truediv__ __wrapped__ __xor__
    __base__ __bases__ __builtins__ __cause__ __closure__ __code__ __context__ __defaults__ __func__
    __globals__ __ifloordiv__ __ilshift__ __imatmul__ __imod__ __imul__ __index__ __ipow__ __irshift__
    __itruediv__ __ixor__ __kwdefaults__ __loader__ __lshift__ __match_args__ __notes__ __objclass__
    __orig_bases__ __package__ __rdivmod__ __release_buffer__ __buffer__ __rfloordiv__ __rlshift__
    __rmatmul__ __rmod__ __rpow__ __rrshift__ __rshift__ __rtruediv__ __rxor__ __self__ __sizeof__
    __spec__ __static_attributes__ __subclasshook__ __suppress_context__ __traceback__ __trunc__
    __type_params__ __weakref__ __firstlineno__ __mro_entries__ __fspath__ __ceil__ __floor__""".split())
BUILTINS = set(dir(builtins))
PYTHON = set(keyword.kwlist) | set(keyword.softkwlist) | BUILTINS | SPECIAL | {"self", "cls", "args", "kwargs"}
NOT_IMPORTED = {"antigravity", "this", "idlelib", "tkinter", "turtle", "turtledemo", "__main__"}  # they do things
FILES = {"py", "pyi", "toml", "cfg", "ini", "yml", "yaml", "rst", "txt", "md"}  # no attribute is called one of these
SHOWN = 5  # how many candidate files a refusal lists


def take(body: str) -> tuple[str, str | None]:
    """What a span that is no pointer is: ("name" | "call" | "member" | "other", the name)."""
    found = NAME.fullmatch(body)
    if found and found.group(2) is None and found.group(1).rpartition(".")[2] in FILES and "." in body:
        return "other", None  # a file's name: `settings.py`
    if found and found.group(2) in (None, "()"):
        return "name", found.group(1)
    if found:
        return "call", found.group(1)
    if BARE_CALL.fullmatch(body):
        return "member", None
    return "other", None


class Index:
    """The module-level names of the indexed packages, and which classes declare which members."""

    def __init__(self, world: pt.World, cfg: dict):
        self.top: dict[str, list[tuple[str, str]]] = {}      # name -> [(tree, path)] that define it
        self.members: dict[str, list[str]] = {}              # member -> the classes that declare it
        self.foreign: set[str] = set()                       # top-level names imported from no pinned tree
        self.roots = [(world.subject, root) for root in cfg["source"]]
        self.roots += [(tree, imported) for imported, tree in sorted(world.tops.items())]
        self.packages = {root.rsplit("/", 1)[-1] for _tree, root in self.roots}
        self.standard = set(sys.stdlib_module_names) | set(cfg.get("standard_library", ()))
        locale = cfg.get("locale_dir")
        for name, root in self.roots:
            tree = world.tree(name)
            for path in sorted(tree.files):
                if not path.endswith(".py") or not (path.startswith(root + "/") or path == root + ".py"):
                    continue
                if locale and locale in path.split("/")[:-1]:
                    continue
                try:
                    module, _lines = tree.parsed(path)
                except Unresolved as why:
                    raise SystemExit(str(why))
                for bound, landings in tree.bound(path, module).items():
                    # a definition of this file: not a name it imports (with a fallback assigned
                    # beside the import or without), and not one it deletes again
                    if not any(landing.kind == "import" for landing in landings) and not all(l.deleted for l in landings):
                        self.top.setdefault(bound, []).append((name, path))
                    for landing in landings:
                        if landing.kind == "class":
                            self.classes(tree, path, landing.node, landing.node.name)
                for node in ast.walk(module):
                    if isinstance(node, ast.Import):
                        self.foreign |= {alias.name.split(".")[0] for alias in node.names}
                    elif isinstance(node, ast.ImportFrom) and not node.level:
                        self.foreign.add(node.module.split(".")[0])
        self.foreign -= self.standard | self.packages | set(world.tops) | {"__main__"}

    def classes(self, tree: pt.Tree, path: str, cls: ast.ClassDef, dotted: str) -> None:
        for member, landings in tree.bound(path, cls).items():
            self.members.setdefault(member, []).append(dotted)
            for landing in landings:
                if landing.kind == "class":
                    self.classes(tree, path, landing.node, f"{dotted}.{member}")


class Gate:
    def __init__(self, book: str | None = None, swap: dict[str, str] | None = None):
        self.world = pt.World(book, swap)
        path = os.path.join(self.world.book, MAP_DIR, CONFIG)
        with open(path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.index = Index(self.world, self.cfg)
        names = self.cfg.get("names", {})
        self.stand_for: dict[str, list[tuple[str, list[str]]]] = {}  # word -> [(file, the class in it, as parts)]
        for word, places in names.get("stand_for", {}).items():
            self.stand_for[word] = []
            for place in [places] if isinstance(places, str) else places:
                try:
                    tree, file, symbol = self.world.parse(place)
                    kind, _landings = self.world.resolve(tree, file, symbol)
                    if tree != self.world.subject or kind not in ("file", "class"):
                        raise Unresolved("it must be a file of the subject, or a class in one")
                except Unresolved as why:
                    raise SystemExit(f"{CONFIG}: names.stand_for: {word} stands for {place}: {why}")
                self.stand_for[word].append((file, symbol.split(".") if symbol else []))
        self.listed: dict[tuple, str] = {}  # the book's declarations
        self.list_problems: list[str] = []
        self.list_path = os.path.join(self.world.book, MAP_DIR, names["runtime"]) if names.get("runtime") else None
        if self.list_path:
            if not os.path.isfile(self.list_path):
                raise SystemExit(f"{CONFIG}: names.runtime: there is no {MAP_DIR}/{names['runtime']}")
            spans, _lines = pt.read(self.list_path)
            self.listed, self.list_problems = self.declarations(self.list_path, spans, self.pointed(spans))

    # -- resolving -----------------------------------------------------------

    def pointed(self, spans: list) -> list[tuple[int, str, str]]:
        """(line, tree, path) of every file a document names in full: by a pointer that
        resolves, or by a name written from its module."""
        out = []
        for span in spans:
            if pt.is_pointer(span.body, self.world):
                with contextlib.suppress(Unresolved):
                    tree, path, symbol = self.world.parse(span.body)
                    self.world.resolve(tree, path, symbol)
                    out.append((span.line, tree, path))
            elif not span.block:
                kind, name = take(span.body)
                if name and name.split(".")[0] in self.index.packages:
                    with contextlib.suppress(Unresolved):
                        found = self.from_module(name.split("."), {})
                        out += [(span.line, found[0].name, found[1])]
        return out

    def from_module(self, parts: list[str], declared: dict):
        """Way 1: -> (tree, path, scope, landings)."""
        for length in range(len(parts), 0, -1):
            home = self.world.home(".".join(parts[:length]))
            if home:
                return self.inside(home[0], home[1], parts[length:], declared)
        raise Unresolved(f"there is no module `{parts[0]}` at the root of its tree")

    def inside(self, tree: pt.Tree, path: str, parts: list[str], declared: dict):
        """The rest of a name, found in a file; a member the walk cannot find may be declared."""
        try:
            found = self.world.walk(tree, path, parts, through=True)
        except Unresolved as why:
            key = why.scope + (why.missing,) if why.scope else None
            if key not in declared and key not in self.listed:
                if why.scope and why.scope[2] and "declares it" not in str(why):
                    raise Unresolved(f"{why}; a name made at runtime is declared in a `runtime-names` block",
                                     why.scope, why.missing, why.rest) from None
                raise
            if why.rest:
                made = f"{why.scope[2]}.{why.missing}".strip(".")
                raise Unresolved(f"`{made}` is made at runtime, and nothing after it can be checked: write "
                                 f"`{why.rest[-1]}` on the class that declares it") from None
            return tree, path, why.scope[2], [pt.Landing("runtime", 0, 0)]
        if found[3] and all(landing.deleted for landing in found[3]):
            raise Unresolved(f"{found[1]} defines `{parts[-1]}` and deletes it again (`del`): it is no name when the code runs")
        return found

    def bind(self, name: str, line: int, pointed: list) -> tuple[str, str] | None:
        """The file whose module-level `name` is meant on this line: the one file of the index
        that defines it, else the nearest file named in full that binds it, by a definition or
        by an import (which the walk then follows to what it imports)."""
        files = self.index.top.get(name, [])
        if len(files) == 1:
            return files[0]
        nearest = [p for p in pointed if p[0] == line] + sorted((p for p in pointed if p[0] < line), key=lambda p: -p[0])
        for _line, tree, path in nearest:
            if path.endswith(".py") and path in self.world.tree(tree).files:
                with contextlib.suppress(Unresolved):
                    held = self.world.tree(tree)
                    landings = held.bound(path, held.parsed(path)[0]).get(name)
                    # not a name the file takes from outside the pinned trees: that answers for itself
                    if landings and not (landings[0].kind == "import" and self.world.imported(held, path, landings[0]) is None):
                        return tree, path
        if files:
            shown = ", ".join(path for _tree, path in files[:SHOWN]) + (", ..." if len(files) > SHOWN else "")
            raise Unresolved(f"{len(files)} files define `{name}` ({shown}): name one in full first, by a pointer "
                             f"on this line or above it, or by its module")
        return None

    def standard(self, parts: list[str]) -> str:
        """Way 4: "standard" when the running Python has the name, "unchecked" when it cannot say."""
        if parts[0] in NOT_IMPORTED:
            return "unchecked"
        for length in range(len(parts), 0, -1):
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    found = importlib.import_module(".".join(parts[:length]))
                break
            except Exception:  # noqa: BLE001  (a module of another platform fails in its own way)
                continue
        else:
            return "unchecked"
        for at in range(length, len(parts)):
            if not hasattr(found, parts[at]):
                version = ".".join(str(x) for x in sys.version_info[:2])
                raise Unresolved(f"the standard library's `{'.'.join(parts[:at])}` has no `{parts[at]}` (Python {version})")
            found = getattr(found, parts[at])
        return "standard"

    def declarers(self, member: str) -> str:
        """The classes that declare a member spelt this way, as the end of a refusal."""
        classes = sorted(set(self.index.members.get(member, ())))
        if not classes:
            return ""
        shown = ", ".join(f"`{c}.{member}`" for c in classes[:SHOWN]) + (", ..." if len(classes) > SHOWN else "")
        return f" (declared, by this spelling, as {shown}; that may not be the one meant)"

    @staticmethod
    def told(found: tuple) -> tuple[str, str]:
        """What a name found in a tree is, and where: for the count, and for --spans."""
        where = found[1] + (f":{found[2]}" if found[2] else "")
        return ("runtime", f"declared, on {where}") if found[3][0].kind == "runtime" else ("tree", where)

    def stands(self, word: str, rest: list[str], declared: dict) -> tuple[str, str]:
        """Way 2: the rest of a name, looked for in each place the word stands for, in order."""
        subject, refusal = self.world.tree(self.world.subject), None
        for file, symbol in self.stand_for[word]:
            try:
                return self.told(self.inside(subject, file, symbol + rest, {}))
            except Unresolved as why:
                refusal = refusal or why
        if len(rest) == 1 and ((rest[0],) in declared or (rest[0],) in self.listed):
            return "runtime", "declared"
        places = " and ".join(file + (":" + ".".join(symbol) if symbol else "") for file, symbol in self.stand_for[word])
        raise Unresolved(f"{str(refusal).split(';')[0]} (`{word}.` is looked for in {places})")

    def beyond(self, why: Unresolved, version: str) -> tuple[str, str] | None:
        """A name the walk left at an import out of the pinned trees: the standard library's
        to answer for, or an unpinned library's to pass unchecked."""
        outside = getattr(why, "outside", None)
        if not outside:
            return None
        if outside[0] in self.index.standard:
            return self.standard(outside), f"the standard library, Python {version}, through an import"
        if outside[0] in self.index.foreign:
            return "unchecked", "a library that is not pinned, through an import"
        return None

    def resolve(self, name: str, line: int, pointed: list, declared: dict) -> tuple[str, str]:
        """-> what the name is ("tree", "runtime", "standard", "python" or "unchecked") and where
        it was found. Raises Unresolved."""
        parts = name.split(".")
        first = parts[0]
        version = ".".join(str(x) for x in sys.version_info[:2])
        if first in self.index.packages:
            try:
                return self.told(self.from_module(parts, declared))
            except Unresolved as why:
                # the walk may have been left at the object that stands for a module
                # (`django.conf.settings.DEBUG`), or at an import out of the pinned trees
                for at in range(1, len(parts) - 1):
                    if parts[at] in self.stand_for:
                        try:
                            self.from_module(parts[:at + 1], {})
                        except Unresolved:
                            continue
                        return self.stands(parts[at], parts[at + 1:], declared)
                found = self.beyond(why, version)
                if found:
                    return found
                raise
        if first in self.stand_for and len(parts) > 1:
            return self.stands(first, parts[1:], declared)
        if first in ("self", "cls") and len(parts) > 1:
            raise Unresolved(f"an attribute is written on the class that declares it{self.declarers(parts[1])}")
        refusal = home = None
        try:
            home = self.bind(first, line, pointed)
            if home:
                return self.told(self.inside(self.world.tree(home[0]), home[1], parts, declared))
        except Unresolved as why:
            found = self.beyond(why, version)
            if found:
                return found
            refusal = why
        if len(parts) == 1 and first in PYTHON:
            return "python", "Python's own"  # a builtin or special name is Python's when no one module has it
        if first in BUILTINS and home is None and refusal is None:
            found = getattr(builtins, first)
            for at in range(1, len(parts)):
                if not hasattr(found, parts[at]):
                    raise Unresolved(f"Python's `{'.'.join(parts[:at])}` has no `{parts[at]}` (Python {version})")
                found = getattr(found, parts[at])
            return "python", f"a builtin's, in Python {version}"
        if first in self.index.standard and not (refusal and len(parts) == 1):
            try:
                return self.standard(parts), f"the standard library, Python {version}"
            except Unresolved as why:
                refusal = refusal or why
        if refusal:
            raise refusal
        if (name,) in declared or (name,) in self.listed:
            return "runtime", "declared"
        if first in self.index.foreign:
            return "unchecked", "a library that is not pinned"
        if len(parts) == 1 and first in self.index.members:
            raise Unresolved(f"it is no module-level name. A member is written on its class{self.declarers(first)}; "
                             f"a function inside a function is written through it, `outer.inner`")
        trees = ", ".join(sorted({tree for tree, _root in self.index.roots}))
        raise Unresolved(f"no module of {trees} defines `{first}` at its top, and it is no builtin; a standard-library "
                         f"name is written with its module (`collections.OrderedDict`), and a module from its top package")

    # -- declarations --------------------------------------------------------

    def declarations(self, path: str, spans: list, pointed: list) -> tuple[dict, list[str]]:
        """The entries of a document's runtime-names blocks, as {key: the pointer}, and what is
        wrong with them. A key is (tree, path, the class's dotted name, the member), or (name,)."""
        shown = os.path.basename(path)
        entries: dict[int, list[str]] = {}
        for span in spans:
            if span.block:
                entries.setdefault(span.line, []).append(span.body)
        out, problems = {}, []
        for line, words in sorted(entries.items()):
            name = words[0]

            def refuse(why: str) -> None:
                problems.append(f"{shown}:{line}: `{name}`: {why}")

            if len(words) != 2 or not pt.SYMBOL.fullmatch(name) or not pt.is_pointer(words[1], self.world):
                refuse("an entry is a name and the pointer to the code that makes it")
                continue
            try:
                self.world.resolve(*self.world.parse(words[1]))
            except Unresolved as why:
                refuse(f"its pointer `{words[1]}` does not resolve: {why}")
                continue
            try:
                if self.resolve(name, line, pointed, {})[0] != "runtime":  # runtime: the book's list has it already
                    refuse("it resolves without a declaration: it is not made at runtime")
                continue
            except Unresolved:
                pass
            parts = name.split(".")
            if len(parts) == 1:
                out[(name,)] = words[1]
                continue
            try:
                owner, cls = self.owner(parts[:-1], line, pointed)
            except Unresolved as why:
                refuse(f"`{'.'.join(parts[:-1])}` must be a class the trees hold: {why}")
                continue
            base = self.world.declaring(self.world.tree(owner[0]), owner[1], cls, parts[-1])
            if base:
                refuse(f"`{base[2]}` in {base[1]} declares it: it is inherited, not made at runtime")
                continue
            out[owner + (parts[-1],)] = words[1]
        return out, problems

    def owner(self, parts: list[str], line: int, pointed: list) -> tuple[tuple[str, str, str], ast.ClassDef]:
        """The class a declared member is made on: (tree, path, its dotted name in that file), and its node."""
        if parts[0] in self.index.packages:
            found = self.from_module(parts, {})
        else:
            home = self.bind(parts[0], line, pointed)
            if not home:
                raise Unresolved(f"no module defines `{parts[0]}` at its top")
            found = self.world.walk(self.world.tree(home[0]), home[1], parts, through=True)
        classes = [landing for landing in found[3] if landing.kind == "class"]
        if not classes:
            raise Unresolved("it is no class")
        return (found[0].name, found[1], f"{found[2]}.{classes[0].node.name}".strip(".")), classes[0].node

    # -- a document ----------------------------------------------------------

    def examine(self, path: str, told: list | None = None) -> tuple[list[str], dict]:
        """What is wrong with a document's names, and how many of its spans were what. `told`
        is given what each name was found to be."""
        spans, _lines = pt.read(path)
        shown = os.path.basename(path)
        pointed = self.pointed(spans)
        declared, problems = self.declarations(path, spans, pointed)
        if self.list_path and os.path.abspath(path) == os.path.abspath(self.list_path):
            declared, problems = {}, []  # the book's own list: its entries are checked once, below
        counts = dict.fromkeys(("names", "standard", "unchecked", "runtime", "pointers", "other"), 0)
        for span in spans:
            if span.block:
                continue
            if pt.is_pointer(span.body, self.world):
                counts["pointers"] += 1
                continue
            kind, name = take(span.body)
            if kind == "other":
                counts["other"] += 1
                continue
            counts["names"] += 1
            if kind == "member":
                problems.append(f"{shown}:{span.line}: `{span.body}`: a member is written on the class that declares it")
                continue
            try:
                what, where = self.resolve(name, span.line, pointed, declared)
            except Unresolved as why:
                problems.append(f"{shown}:{span.line}: `{span.body}`: {why}")
                continue
            if what in counts:
                counts[what] += 1
            if told is not None:
                told.append((span.line, span.body, what, where))
        return sorted(problems, key=lambda p: int(p.split(":")[1])), counts


def summary(counts: dict, documents: int, failed: int) -> str:
    asides = []
    if counts["standard"]:
        version = ".".join(str(x) for x in sys.version_info[:2])
        asides.append(f"{counts['standard']} of the standard library, checked against Python {version}")
    if counts["unchecked"]:
        asides.append(f"{counts['unchecked']} not checked: of a library that is not pinned, or of a module this "
                      f"Python cannot import")
    if counts["runtime"]:
        asides.append(f"{counts['runtime']} made at runtime, by declaration")
    return (f"names: {'FAILED' if failed else 'ok'}, {pt.count(counts['names'], 'name')} in "
            f"{pt.count(documents, 'document')}" + (f" ({'; '.join(asides)})" if asides else "")
            + f"; {pt.count(counts['pointers'], 'pointer')} and {pt.count(counts['other'], 'other code span')} not "
              f"checked here" + (f"; {pt.count(failed, 'name')} or declaration{'s' if failed != 1 else ''} refused" if failed else ""))


def run(book: str | None, arguments: list[str], swap: dict[str, str] | None = None) -> int:
    gate = Gate(book, swap)
    found = pt.documents(arguments)
    total = dict.fromkeys(("names", "standard", "unchecked", "runtime", "pointers", "other"), 0)
    failed = len(gate.list_problems)
    for line in gate.list_problems:
        print(line)
    for full, _relative in found:
        problems, counts = gate.examine(full)
        for line in problems:
            print(line)
        failed += len(problems)
        for key in total:
            total[key] += counts[key]
    print(summary(total, len(found), failed))
    return 1 if failed else 0


def show_spans(book: str | None, arguments: list[str], swap: dict[str, str] | None = None) -> int:
    """Every code span, what it was taken for, and for a name where it was found."""
    gate = Gate(book, swap)
    for full, _relative in pt.documents(arguments):
        told: list = []
        problems, _counts = gate.examine(full, told)
        found = {(line, body): f"{what}: {where}" for line, body, what, where in told}
        found.update({(int(p.split(":")[1]), p.split("`")[1]): "REFUSED" for p in problems})
        for span in pt.read(full)[0]:
            kind = "entry" if span.block else "pointer" if pt.is_pointer(span.body, gate.world) else take(span.body)[0]
            print(f"{os.path.basename(full)}:{span.line}: {kind:8}`{span.body}`"
                  + (f"  -> {found.get((span.line, span.body), '')}" if kind in ("name", "call", "member") else ""))
    return 0


# ----------------------------------------------------------------------------
# the probe

PROBE_MODELS = '''class ModelBase(type):
    def __new__(cls, name, bases, attrs):
        return super().__new__(cls, name, bases, attrs)


class Model(metaclass=ModelBase):
    pk = property(lambda self: 1)

    def save(self):
        self._state = 1

    class Inner:
        deep = 1


class Child(Model):
    def own(self):
        pass


def get_model():
    pass


default = Model()


class Trans:
    pass


del Trans
TWICE = 1
TWICE = 2
del TWICE
BACK = 1
del BACK
BACK = 2
import datetime
'''
PROBE_TREE = {
    "pkg/__init__.py": "from pkg.models import Model\nfrom pkg.extras import *\n",
    "pkg/models.py": PROBE_MODELS,
    "pkg/extras.py": "__all__ = ['Extra']\n\n\nclass Extra:\n    pass\n\n\nclass Hidden:\n    pass\n\n\ndef format():\n    pass\n",
    "pkg/conf/__init__.py": "class LazySettings:\n    configured = False\n    DEBUG = None\n\n    def configure(self):\n        pass\n\n\n"
                            "settings = LazySettings()\n",
    "pkg/conf/defaults.py": "DEBUG = False\nMIDDLEWARE = []\n",
    "pkg/backends/__init__.py": "",
    "pkg/backends/one/__init__.py": "",
    "pkg/backends/one/base.py": "class Wrapper:\n    def open(self):\n        pass\n",
    "pkg/backends/two/__init__.py": "",
    "pkg/backends/two/base.py": "class Wrapper:\n    def close(self):\n        pass\n",
    "pkg/messages.py": "import __main__\nimport json\n\nimport thirdparty\nfrom lib.core import Thing\n\nDEBUG = 10\nstring = 'a name the standard library has too'\n"
                       "try:\n    import jinja2\nexcept ImportError:\n    jinja2 = None\n\n\ndef format():\n    pass\n\n\n"
                       "class Warning:\n    level = 30\n",
    "pkg/locale/xx/formats.py": "ONLY_IN_LOCALE = 1\n",
    "pkg/uses.py": "from pkg import models\nfrom pkg.backends.two.base import Wrapper\nfrom .models import Model as Again\n"
                   "if TYPE_CHECKING:\n    from pkg.extras import Extra as OnlyTyped\n    from pkg.extras import Hidden as Both\n"
                   "Both = None\nimport datetime\nfrom thirdparty import client\n",
    "tests/test_models.py": "class ModelTests:\n    def test_save(self):\n        pass\n",
}
PROBE_LIBRARY = {
    "lib/__init__.py": "",
    "lib/core.py": "class Thing:\n    def go(self):\n        pass\n\n\ndef helper():\n    pass\n",
    "setup.py": "NOT_INDEXED = 1\n",
}


def probe() -> int:
    import tempfile
    work = tempfile.mkdtemp(prefix="nameprobe-")
    failed = []

    def expect(label: str, got, want) -> None:
        if got != want:
            failed.append(f"{label}: got {got!r}, wanted {want!r}")

    try:
        book = os.path.join(work, "book")
        where = os.path.join(book, "reference", "subject")
        for path, text in PROBE_TREE.items():
            pin._write(os.path.join(where, *path.split("/")), text)
        made = pin._scratch(where)
        library = os.path.join(book, "reference", "a-library")
        for path, text in PROBE_LIBRARY.items():
            pin._write(os.path.join(library, *path.split("/")), text)
        made_library = pin._scratch(library)
        single = os.path.join(book, "reference", "single")  # a library that is one module
        pin._write(os.path.join(single, "solo.py"), "def lone():\n    pass\n")
        made_single = pin._scratch(single)
        pin._write(os.path.join(book, pin.PIN_FILE), json.dumps(
            {"subject": "subject", "python": "3.12",
             "trees": {"subject": {"repository": where, "commit": made, "path": "reference/subject"},
                       "a-library": {"repository": library, "commit": made_library, "path": "reference/a-library",
                                     "imports": ["lib"]},
                       "single": {"repository": single, "commit": made_single, "path": "reference/single",
                                  "imports": ["solo"]}}}))
        config = {"source": ["pkg"], "locale_dir": "locale",
                  "names": {"runtime": "runtime-names.md",
                            "stand_for": {"settings": ["pkg/conf/defaults.py", "pkg/conf/__init__.py:LazySettings"]}}}
        pin._write(os.path.join(book, MAP_DIR, CONFIG), json.dumps(config))
        listing = os.path.join(book, MAP_DIR, "runtime-names.md")
        pin._write(listing, f"At {made}.\n\n```runtime-names\nModel.objects  pkg/models.py:ModelBase.__new__\n"
                            "ROOT  pkg/conf/__init__.py:settings  # read, and defined nowhere\n```\n")
        gate = Gate(book)
        expect("the book's list", (gate.listed, gate.list_problems),
               ({("subject", "pkg/models.py", "Model", "objects"): "pkg/models.py:ModelBase.__new__",
                 ("ROOT",): "pkg/conf/__init__.py:settings"}, []))
        expect("the index leaves out imports, locale data, tests, what is beside a library's package, a name "
               "imported with a fallback and a name deleted again; and holds a library that is one module",
               [name in gate.index.top for name in ("Model", "Thing", "json", "ONLY_IN_LOCALE", "ModelTests", "NOT_INDEXED",
                                                    "jinja2", "Trans", "Again", "lone")],
               [True, True, False, False, False, False, False, False, False, True])
        expect("libraries nobody pinned", gate.index.foreign, {"thirdparty", "jinja2"})

        doc = os.path.join(work, "doc.md")

        def refusals(text: str) -> list[str]:
            """What the gate refuses in a document, as `line: span`."""
            pin._write(doc, text)
            return [f"{p.split(': ', 2)[0].split(':')[1]}: {p.split(': ', 2)[1]}" for p in gate.examine(doc)[0]]

        def why(text: str) -> str:
            pin._write(doc, text)
            found = gate.examine(doc)[0]
            return found[0].split("`: ", 1)[1] if len(found) == 1 else f"{len(found)} refusals: {found}"

        def passes(*names: str) -> None:
            got = refusals("\n\n".join(f"`{name}`" for name in names))
            if got:
                failed.append(f"refused, and should pass: {got}")

        def refused(name: str, needle: str) -> None:
            got = why(f"`{name}`")
            if needle not in got:
                failed.append(f"`{name}`: wanted a refusal holding {needle!r}, got {got!r}")

        # by itself: a class, its own members, a function, an assigned name; a library's
        passes("Model", "Model.save", "Model.save()", "Model.pk", "Model._state", "Model.Inner.deep", "Child.own",
               "get_model", "get_model()", "default", "MIDDLEWARE", "Thing", "Thing.go", "helper", "ModelBase.__new__")
        refused("Model.sav", "`Model` in pkg/models.py binds no `sav`; it has `save`")
        refused("Child.save", "`Model` in pkg/models.py declares it")
        refused("Model.own", "binds no `own`")
        refused("default.save", "is an assignment: nothing can be named inside it")
        refused("save", "A member is written on its class (declared, by this spelling, as `Model.save`")
        refused("nothing_here", "no module of a-library, single, subject defines `nothing_here` at its top")
        refused("Model.sav", "a name made at runtime is declared in a `runtime-names` block")
        refused("self._state", "an attribute is written on the class that declares it (declared, by this spelling, as `Model._state`")
        refused("self.nope", "an attribute is written on the class that declares it")
        # a name the code deletes again, or imports only for type checking, is no name
        refused("Trans", "no module of")
        refused("pkg.models.Trans", "deletes it again")
        refused("pkg.uses.OnlyTyped", "only under `if TYPE_CHECKING`")
        refused("pkg.models.TWICE", "deletes it again")   # both of its bindings come before the del
        passes("lone", "solo.lone", "pkg.uses.Again.save", "pkg.models.BACK", "BACK",  # bound again after its del
               "pkg.uses.Both")                                                         # bound when the code runs too
        # where a name written from its module runs into an import out of the trees, or into the
        # object that stands for a module, the rest is looked for there
        passes("pkg.uses.datetime.datetime.now", "pkg.uses.client.anything", "pkg.conf.settings.DEBUG",
               "pkg.conf.settings.configure")
        refused("pkg.uses.datetime.nope", "the standard library's `datetime` has no `nope`")
        refused("pkg.conf.settings.NOPE", "`settings.` is looked for in")
        refused("__main__.x", "no module of")
        refused("kwargs.get", "no module of")
        refused("ModelTests", "no module of")
        refused("ONLY_IN_LOCALE", "no module of")
        # from its module; through an import and through import *; a module alone
        passes("pkg", "pkg.models", "pkg.models.Model.save", "pkg.Model", "pkg.Model.save", "pkg.Extra", "lib.core",
               "lib.core.helper", "lib.core.Thing.go", "pkg.messages.Thing.go", "pkg.messages.json", "pkg.conf.settings")
        refused("pkg.Hidden", "the module in pkg/__init__.py binds no `Hidden`")
        refused("pkg.models.Nope", "binds no `Nope`")
        refused("pkg.nothing.Model", "binds no `nothing`")
        refused("lib.core.nope", "binds no `nope`")
        # an object that stands for a module
        passes("settings.DEBUG", "settings.MIDDLEWARE", "settings.ROOT", "ROOT", "settings", "settings.configure",
               "settings.configured")
        refused("settings.NOPE", "binds no `NOPE` (`settings.` is looked for in pkg/conf/defaults.py and "
                                 "pkg/conf/__init__.py:LazySettings)")
        # made at runtime: the book's list, and the document's own block; nothing after such a name
        passes("Model.objects", "pkg.models.Model.objects", "pkg.Model.objects")
        refused("Model.objects.filter", "`Model.objects` is made at runtime, and nothing after it can be checked")
        refused("Child.objects", "binds no `objects`")
        own = "```runtime-names\nModel.dynamic  pkg/models.py:ModelBase.__new__\nPLAIN  pkg/models.py\n```\n"
        expect("a document's own declarations", refusals(own + "\n`Model.dynamic` and `PLAIN`"), [])
        expect("and not another document's", refusals("`Model.dynamic` and `PLAIN`"), ["1: `Model.dynamic`", "1: `PLAIN`"])
        for entry, needle in (
                ("Model.x", "an entry is a name and the pointer"),
                ("Model.x  pkg/models.py:Model  extra", "an entry is a name and the pointer"),
                ("Model.x  ModelBase", "an entry is a name and the pointer"),
                ("Model.x()  pkg/models.py:ModelBase", "an entry is a name and the pointer"),
                ("Model.x  pkg/models.py:Nope", "its pointer `pkg/models.py:Nope` does not resolve"),
                ("Model.save  pkg/models.py:ModelBase", "it resolves without a declaration"),
                ("Child.save  pkg/models.py:ModelBase", "`Model` in pkg/models.py declares it: it is inherited"),
                ("get_model.x  pkg/models.py:ModelBase", "must be a class the trees hold: it is no class"),
                ("Nope.x  pkg/models.py:ModelBase", "must be a class the trees hold: no module defines `Nope`"),
                ("len  pkg/models.py:ModelBase", "it resolves without a declaration")):
            got = why(f"```runtime-names\n{entry}\n```\n")
            if needle not in got:
                failed.append(f"the entry {entry!r}: wanted {needle!r}, got {got!r}")

        expect("an entry the book's list already has is no fault",
               refusals("```runtime-names\nModel.objects  pkg/models.py:ModelBase.__new__\n```\n\n`Model.objects`"), [])

        # defined in more than one file: bound by a pointer on the line, by the nearest above, by its module
        refused("Wrapper", "2 files define `Wrapper` (pkg/backends/one/base.py, pkg/backends/two/base.py)")
        refused("DEBUG", "2 files define `DEBUG` (pkg/conf/defaults.py, pkg/messages.py)")
        one, two = "`pkg/backends/one/base.py:Wrapper`", "`pkg/backends/two/base.py:Wrapper`"
        expect("the nearest pointer above", refusals(f"{one}\n\n`Wrapper.open`\n\n{two}\n\n`Wrapper.close`\n\n`Wrapper.open`"),
               ["9: `Wrapper.open`"])
        expect("a pointer on the same line, even after the name, before one above",
               refusals(f"{one}\n\n| `Wrapper.close` | {two} |\n\n`Wrapper.close`"), [])
        expect("a pointer below does not bind", refusals(f"`Wrapper.open`\n\n{one}"), ["1: `Wrapper.open`"])
        expect("a pointer that does not resolve names no file",
               refusals("`pkg/backends/one/base.py:Nope`\n\n`Wrapper.open`"), ["3: `Wrapper.open`"])
        expect("by its module", refusals("`pkg.backends.two.base.Wrapper`\n\n`Wrapper.close`"), [])
        expect("by a pointer to the file", refusals("`pkg/messages.py` holds `DEBUG`"), [])
        expect("by a file that imports the name: it means what that file imports",
               refusals("`pkg/uses.py` has `Wrapper.close` and `models.Model.save`\n\n`Wrapper.open`\n\n`models.Nope`"),
               ["3: `Wrapper.open`", "5: `models.Nope`"])
        expect("an alias no file named has", refusals("`models.Model.save`"), ["1: `models.Model.save`"])
        expect("a declaration bound by its own pointer",
               refusals(f"```runtime-names\nWrapper.live  pkg/backends/two/base.py:Wrapper.close\n```\n\n{two}\n\n`Wrapper.live`"
                        f"\n\n{one}\n\n`Wrapper.live`"), ["11: `Wrapper.live`"])
        # a name the index does not hold is found in a file a pointer has named
        expect("a test's name", refusals("`tests/test_models.py` has `ModelTests.test_save`\n\n`ModelTests.nope`"),
               ["3: `ModelTests.nope`"])
        # the standard library, Python's own, a library nobody pinned
        passes("asyncio.Lock", "os.path.join", "json", "json.dumps", "None", "len", "__init__", "self", "kwargs",
               "thirdparty.Client", "thirdparty", "xml.etree.ElementTree.parse", "concurrent.futures.ThreadPoolExecutor",
               "dict.get", "type.__call__", "Exception.args", "__traceback__", "__func__", "jinja2.Environment")
        refused("asyncio.Lok", "the standard library's `asyncio` has no `Lok`")
        refused("dict.nope", "Python's `dict` has no `nope`")
        refused("dict.get.nope", "Python's `dict.get` has no `nope`")
        told = []
        pin._write(doc, "`settings.DEBUG` is in both places it stands for\n")
        gate.examine(doc, told)
        expect("the first place a word stands for is looked in first", told, [(1, "settings.DEBUG", "tree", "pkg/conf/defaults.py")])
        # a builtin's name that two files define is Python's until a pointer names one; that one file defines is the file's
        told: list = []
        pin._write(doc, "`format` `format()` `Warning.level` `Model.save` `len` `asyncio.Lock`\n\n`pkg/messages.py` has `format`\n")
        expect("where each name was found", (gate.examine(doc, told)[0], [(body, what, where) for _l, body, what, where in told]),
               ([], [("format", "python", "Python's own"), ("format()", "python", "Python's own"),
                     ("Warning.level", "tree", "pkg/messages.py:Warning"), ("Model.save", "tree", "pkg/models.py:Model"),
                     ("len", "python", "Python's own"),
                     ("asyncio.Lock", "standard", f"the standard library, Python {sys.version_info[0]}.{sys.version_info[1]}"),
                     ("format", "tree", "pkg/messages.py")]))
        # a file binds a name it imports from a pinned tree, not one it takes from outside them:
        # the standard library answers for itself, and says what is wrong
        expect("the standard library's own refusal, though a named file imports the module",
               "the standard library's `json` has no `nope`" in why("`pkg/messages.py` and `json.nope`"), True)
        told = []
        pin._write(doc, "`pkg/uses.py` imports `datetime`, and `client` from a library nobody pinned; `models.datetime.date`\n")
        expect("a named file does not bind what it takes from outside the trees; a name found through it is handed on",
               (gate.examine(doc, told)[0], [(body, what) for _l, body, what, _w in told]),
               (["doc.md:1: `client`: no module of a-library, single, subject defines `client` at its top, and it is no builtin; "
                 "a standard-library name is written with its module (`collections.OrderedDict`), and a module from its top package"],
                [("datetime", "standard"), ("models.datetime.date", "standard")]))
        # a module that does things when it is imported is not imported
        imported, real = [], importlib.import_module

        def recorded(name: str, *rest):
            imported.append(name)
            if name.split(".")[0] in NOT_IMPORTED:
                raise ImportError("the probe does not let it run")
            return real(name, *rest)

        importlib.import_module = recorded
        try:
            expect("counted and not imported", (refusals("`antigravity.fly` and `this.s` and `json.dumps`"), imported), ([], ["json.dumps", "json"]))
        finally:
            importlib.import_module = real
        # a first name the trees and the standard library both have: the trees first, then the library
        passes("string", "string.ascii_letters")
        refused("string.nope", "`string` in pkg/messages.py is an assignment")
        refused("__html__", "no module of")
        refused("unknownlib.Client", "no module of")
        # calls, decorators, bare members, and what is not a name at all
        passes("Model.save(force=True)", "@get_model", "Model.save().x")
        refused("Model.sav(1)", "binds no `sav`")
        refused("@nope", "no module of")
        refused(".save()", "a member is written on the class that declares it")
        pin._write(doc, "`a b` `\"text\"` `x = 1` `--flag` `404` `.py` `pkg/models.py` `Model` `asyncio.Lock` "
                        "`thirdparty.X` `Model.objects` `len`\n\n```python\n`nope.nope`\n```\n")
        expect("what each span was", gate.examine(doc),
               ([], {"names": 5, "standard": 1, "unchecked": 1, "runtime": 1, "pointers": 1, "other": 6}))
        expect("how spans are taken", [take(b)[0] for b in ("A.b", "A.b()", "@a", "A.b(c)", ".a()", ".a", "a b", "1",
                                                            "settings.py", "a.b.txt", "settings.py()", "py", "A.json")],
               ["name", "name", "name", "call", "member", "other", "other", "other", "other", "other", "name", "name", "name"])

        # the run; the book's list is checked on every run, and as a document of its own
        def quiet(arguments: list[str], **more) -> tuple[int, str]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run(book, arguments, **more)
            return code, out.getvalue().strip()

        version = ".".join(str(x) for x in sys.version_info[:2])
        expect("a passing run", quiet([doc]),
               (0, f"names: ok, 5 names in 1 document (1 of the standard library, checked against Python {version}; 1 not "
                   "checked: of a library that is not pinned, or of a module this Python cannot import; 1 made at runtime, "
                   "by declaration); 1 pointer and 6 other code spans not checked here"))
        pin._write(doc, "`Model.sav` on line 1\n")
        code, out = quiet([doc])
        expect("a failing run", (code, out.splitlines()[0][:22], out.splitlines()[-1][:14], "1 name or declaration refused" in out),
               (1, "doc.md:1: `Model.sav`:", "names: FAILED,", True))
        expect("the list as a document", quiet([listing])[0], 0)
        pin._write(listing, "```runtime-names\nModel.objects  pkg/models.py:ModelBase.nope\n```\n")
        code, out = quiet([doc])
        expect("a wrong entry in the book's list fails every run",
               (code, "runtime-names.md:2: `Model.objects`: its pointer" in out, "2 names or declarations refused" in out), (1, True, True))
        # against a second tree, in which Model has lost a method
        second = os.path.join(work, "second")
        for path, text in PROBE_TREE.items():
            pin._write(os.path.join(second, *path.split("/")), text.replace("    def save(self):", "    def store(self):"))
        pin._scratch(second)
        pin._write(listing, "")
        pin._write(doc, "`Model.save` and `Model.store`\n")
        expect("at the pin", refusals("`Model.save` and `Model.store`"), ["1: `Model.store`"])
        code, out = quiet([doc], swap={"subject": second})
        expect("against a second tree", (code, out.splitlines()[0][:23]), (1, "doc.md:1: `Model.save`:"))

        def spans(**more) -> list[str]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                show_spans(book, [doc], **more)
            return [line.split(": ", 1)[1] for line in out.getvalue().splitlines()]

        expect("--spans says where a name was found, and that one was refused", spans(),
               ["name    `Model.save`  -> tree: pkg/models.py:Model", "name    `Model.store`  -> REFUSED"])
        expect("--spans against a second tree", spans(swap={"subject": second}),
               ["name    `Model.save`  -> REFUSED", "name    `Model.store`  -> tree: pkg/models.py:Model"])
        # a configuration that names what is not there
        pin._write(os.path.join(book, MAP_DIR, CONFIG), json.dumps({**config, "names": {"stand_for": {"settings": "pkg/nope.py"}}}))
        try:
            Gate(book)
            failed.append("a stand-in for a file the tree does not hold was accepted")
        except SystemExit:
            pass
        for place in ("pkg/models.py:get_model", "a-library:lib/core.py", "pkg/"):  # a function, a library's file, a directory
            pin._write(os.path.join(book, MAP_DIR, CONFIG), json.dumps({**config, "names": {"stand_for": {"settings": place}}}))
            try:
                Gate(book)
                failed.append(f"a word was let stand for {place}")
            except SystemExit:
                pass
        pin._write(os.path.join(book, MAP_DIR, CONFIG), json.dumps({**config, "names": {"stand_for": {"settings": "pkg/conf/defaults.py"}}}))
        try:
            expect("a stand-in written as one place", Gate(book).resolve("settings.DEBUG", 1, [], {}), ("tree", "pkg/conf/defaults.py"))
        except (SystemExit, Unresolved) as why:
            failed.append(f"a stand-in written as one place: {why}")
        pin._write(os.path.join(book, MAP_DIR, CONFIG), json.dumps({**config, "names": {"runtime": "nope.md"}}))
        try:
            Gate(book)
            failed.append("a list that is not there was accepted")
        except SystemExit:
            pass
    finally:
        pin.remove(work)
    if failed:
        print("PROBE FAILED:\n  " + "\n  ".join(failed))
        return 1
    print("probe ok: a name resolves by itself, from its module, through an import and `import *`, through an "
          "object that stands for a module or a class (written alone or from its module, its places in order), "
          "in a library, in the standard library (alone, and where a walk is left at an import of it) and as "
          "Python's own, a builtin's members included; a member is one its class declares, and an inherited one "
          "is refused with the base that declares it; a bare member, a misspelt name, a name hidden by "
          "`__all__`, a name only a test or a locale holds, one deleted again and one imported only for type "
          "checking are refused; a name two files define is refused until a pointer on its line, the nearest "
          "above, or its module binds it, to what the named file defines or imports from a pinned tree, and a "
          "builtin's name two files define is Python's until then; a name made at runtime passes only where it "
          "is declared, nothing passes after it, and a declaration without a pointer that resolves, of a name "
          "the source declares or inherits, or on what is no class is refused; a call is checked by the name "
          "before its parenthesis; what is no name is counted and not checked; --spans says where each name "
          "was found; the book's list is checked on every run; a second tree is read in the pinned one's place")
    return 0


def main(argv: list[str]) -> int:
    args = list(argv)
    book, swap = None, {}
    for flag in ("--root", "--tree"):
        while flag in args:
            at = args.index(flag)
            if at + 1 >= len(args):
                raise SystemExit(f"{flag} needs a value")
            if flag == "--tree":
                name, equals, where = args[at + 1].partition("=")
                if not equals or not where:
                    raise SystemExit("--tree takes NAME=DIR")
                swap[name] = where
            else:
                book = args[at + 1]
            del args[at:at + 2]
    pin.require_python(pinned=False)
    if "--probe" in args:
        return probe()
    pin.require_python(book)
    flags = {a for a in args if a.startswith("--")}
    docs = [a for a in args if not a.startswith("--")]
    if flags - {"--spans"} or not docs:
        raise SystemExit(__doc__)
    if flags:
        return show_spans(book, docs, swap)
    return run(book, docs, swap)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
