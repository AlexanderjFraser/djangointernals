#!/usr/bin/env python3
"""The pointer gate: every pointer in a document names a place the pinned tree holds.

A claim about the source carries a pointer, written in a code span:

    `django/db/models/query.py:QuerySet._fetch_all`     a symbol: the file, a colon, the symbol
    `django/db/models/query.py`                         a whole file
    `django/core/handlers/`                             a directory, with its slash
    `asgiref:asgiref/sync.py:SyncToAsync`               in another tree of pin.json: its name first
    `django:pyproject.toml`                             a file at a tree's root, which has no slash
                                                        to be known by: the tree's name first

    python tools/pointers.py DOC [DOC ...]       check each document, and write its report beside it
    python tools/pointers.py --check DOC ...     check, write nothing, and fail too on a report that is
                                                 not what would be written now
    python tools/pointers.py --report DIR ...    keep the reports under DIR, not beside the documents
    python tools/pointers.py --tree NAME=DIR ... resolve the pointers into NAME in the tree at DIR as well,
                                                 and list each that is gone there or lands on changed bytes;
                                                 it writes nothing, and takes neither --check nor --report.
                                                 DIR is a checkout with nothing uncommitted, at any commit
    python tools/pointers.py --spans DOC ...     list every code span and what the gate took it for
    python tools/pointers.py --probe             prove the gate resolves, refuses and reports as this says

A DOC is a markdown file, or a directory, which stands for every .md under it. Each command
takes `--root DIR`, the book's root (default: $BOOK_ROOT, else the directory above this file).
The trees and their commits are pin.json's (tools/pin.py); a tree that is not at its pin is
refused.

Which code spans are pointers. Any slash makes one: a span is taken for a pointer when it
has no white space and holds a slash; or holds `.py:` or `.py#`; or a backslash and `.py`;
or begins with the path of a Python file and then white space; or begins with a tree's
name, or a near miss of one in any case, and a colon before something with a dot or a slash
in it. A span that opens with a quote, or holds one and no `.py:`, is literal text and
never a pointer, and neither is one that holds `://`. A span taken for a pointer must be
one: a bracket, an `=`, a `#`, a comma, a backslash or white space in it is refused. So
literal text with a slash in it is written with its quotes inside the span: a media type
(`"text/html"`), a URL path, a route, a template's name (`"admin/base_site.html"`; the
template's file is a pointer, its name is a string); and a phrase like and/or is not put
in a code span at all. About three in a hundred of the code spans in Django's own
documentation would be refused on this rule: it is meant to be strict where the cost of a
miss is a pointer nobody checked.

How a document is read. Code spans are found by CommonMark's rule (a run of backticks closes
at the next run of the same length; a backtick after a backslash opens nothing). Spans
inside a fenced block are not read, except the entries of a block labelled `runtime-names`
(tools/names.py), each of which carries a pointer as its second word. A fence is three or
more backticks or tildes at the start of a line, however far indented (so that a fence in a
list item is one) or inside a quotation, with no backtick after a backtick fence; it closes
at a fence of the same character, at least as long, with nothing after it and indented no
more than three spaces beyond its opening, or where its quotation ends. Everything else is
prose and is read, an indented code block and an HTML comment included. So the gate
mostly reads more than a renderer shows as prose. It reads less in two cases it does not
try to tell apart, where CommonMark sees text and the gate sees a fence that then runs on:
a fence line indented four spaces at the top level (an indented code block), and a fence
line inside an HTML block (`<pre>`). Prose after either may go unread.

How a pointer resolves.

- The path is from the tree's root, with forward slashes, and is a file the commit holds
  (`git ls-files`), or with a final slash a directory that holds one. A path is one path:
  no pattern.
- The symbol is dotted from module level, and each name in it is one the scope before it
  binds, found in the syntax tree:
    a module binds     its classes and functions, the names it assigns (tuples taken apart;
                       annotated names, with a value or without; augmented assignments;
                       `type` aliases), and the names its imports bind;
    a class binds      the same in its own body; then what `__slots__` names, where it is
                       written out as strings (one, or a tuple, list, set or dict of them);
                       then the attributes its own methods assign on `self` (a first
                       parameter of that name, in a method that is not static; in `__new__`,
                       a local made by a call to some `__new__` with fewer than four
                       arguments, in a class that does not derive from `type` by name:
                       four arguments make a class, and its attributes are not the
                       metaclass's), taken from `__init__` if it assigns the name and
                       otherwise from the first method that does;
    a function binds   the classes and functions defined in it, and nothing else.
  Definitions under a block (if, try, with, for, while, match) belong to the scope around
  it. A member is one its class's own body declares: an inherited one does not resolve, and
  the message names the base that declares it where the gate can find it. An attribute a
  class only assigns on `self`, and which a base class declares, is the base's too. (A
  base is found by its name, from the class's own scope outwards and through imports into
  the pinned trees. One from the standard library, or made by a call, cannot be asked what
  it declares, and an attribute it declares is taken for the subclass's.)
- A name bound more than once in its scope (a property and its setter; a function defined
  under `if` and again under `else`) resolves to every binding, in the order of the source:
  the report gives the first as `lines` and the rest as `more`, and one fingerprint covers
  them all.
- A name the scope later deletes (`del`) still resolves: its definition is a place.
- A pointer may land on an import, which is how a re-export is pointed at. It is marked
  `import` and counted in the gate's last line: an import seldom does what a sentence says.
  A name that only `from x import *` brings in is bound by no statement and does not resolve.
- A file that is not Python takes no symbol.
- The standard library is not a pinned tree and cannot be pointed into.

The commit is not part of a pointer. Before its first pointer (on a line above it, or
earlier on its line) a document spells out the subject's pinned commit, twelve hex digits or
more, each of them the pin's; a document that does not fails. It may name other commits
too. After a re-pin that is the list of what to verify again.

The report, `<document>.pointers.json`, is written only for a document that passes, and is
removed when its document has no pointer left. Where a run is given a whole directory and
keeps its reports beside the documents, a report there with no document beside it (neither
`<name>.md` nor a file of the report's own name without the suffix) is removed too, and
fails `--check`. Under `--report DIR` no report is removed for want of a document: DIR may
hold other runs' reports, and whoever owns it clears it. Nothing but a report is removed:

    {"generated": {"tool": ..., "trees": {name: commit}},     the trees its pointers land in
     "document": "<file name>",
     "pointers": [{"pointer":     as written,
                   "line":        its line in the document,
                   "sentence":    the sentence that carries it; for a table, the row; in a
                                  `runtime-names` block, the entry,
                   "tree", "path", "symbol":   the pointer's parts (symbol null for a path),
                   "kind":        file | directory | class | function | assignment | import |
                                  attribute | slot,
                   "lines":       [first, last] in the source: from a definition's first
                                  decorator to its last line; of a file, all of it ([0, 0]
                                  when it is empty); absent for a directory,
                   "at":          the line of `class` or `def`, when decorators come first
                                  (of the first binding; later ones give their lines only),
                   "more":        [[first, last], ...] when the name is bound more than once,
                   "fingerprint": the first 16 hex digits of the SHA-256 of the bytes the
                                  pointer lands on}]}

One record for each time a pointer is written. A fingerprint is taken from the commit's own
bytes (tools/pin.py refuses a tree that is not those), so it is the same on every machine:
of a file, the file; of a symbol, its lines, each binding's in turn; of a directory, the
path and SHA-256 of every file under it. A changed comment inside a definition changes its
fingerprint. A definition that only moved keeps it.

What the gate does not check: that the place a pointer names does what its sentence says
(a verifier's work); a pointer written outside a code span, or inside a fenced block that
is not `runtime-names`; a name bound by `for`, `with`, `global`, a walrus, `setattr` or a
metaclass (tools/names.py takes such names from a declaration); an attribute assigned on a
first parameter that is not called `self`; a path that holds white space (a handful of test
fixtures); a symbol in a `.pyi` stub. An attribute a metaclass or a decorator removes from
a class still resolves: its statement is a place. A `del` marks a name deleted wherever it
stands in the scope, under a condition too; only `if TYPE_CHECKING:` written just so (bare
or as an attribute) marks an import as for type checking; the commit in a document's head is
read in lower case. A sentence is found by rule (a full stop, question or exclamation
mark, then white space and a capital, a digit, a code span, an emphasis mark or an opening
bracket; never inside a code span or after `e.g.` and its like) and is sometimes a clause
more or less than a reader would take. A pointer that stands with no word of its own, after
the sentences of its paragraph or list item, carries all of them.

Vendored: the copy in a book's repository is written by a command and is not edited there.
"""
from __future__ import annotations

import ast
import contextlib
import difflib
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pin  # noqa: E402  (the one place the trees and their commits are written)

TOOL = "tools/pointers.py"
SUFFIX = ".pointers.json"
BLOCK = "runtime-names"  # a fenced block whose entries are `Name  pointer`
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPES = (ast.ClassDef,) + DEFS
QUOTES = set("'\"`")  # a span that holds one of these is literal text, not a pointer
STOP = set(" \t\n()[]{}<>=,;|^$%#&~!")  # a pointer that holds one of these is refused
SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
HEX = re.compile(r"(?<![0-9a-f])[0-9a-f]{12,40}(?![0-9a-f])")
RUN = re.compile("`+")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
HEADING = re.compile(r"^\s*#{1,6}\s")
SECTION = re.compile(r"^ {0,3}##(?!#)\s")  # a top-level `##` heading: where a page's section begins (tools/names.py --sections)
QUOTED = re.compile(r"^\s*(?:>\s?)+")
ENDS = re.compile(r"[.!?][\"')\]*_]*\s+(?=[A-Z0-9`*_\[(])")
ABBREVIATED = re.compile(r"(?:\b(?:e\.g|i\.e|cf|vs|etc|viz|approx)|\s[A-Za-z])\.[\"')\]*_]*\s+$")
DEPTH = 12  # how far an import is followed, or a base class looked up


class Unresolved(Exception):
    """Why a pointer or a name does not resolve. `scope` and `missing` say where the walk
    stopped, when it stopped for want of a name: (tree, path, the dotted name of the scope)."""

    def __init__(self, message: str, scope: tuple | None = None, missing: str | None = None,
                 rest: tuple = ()):
        super().__init__(message)
        self.scope, self.missing, self.rest = scope, missing, rest
        self.outside: list[str] | None = None  # the dotted name the walk was left at, past an import out of the trees


class Landing:
    """One binding of a name: its kind, the lines it stands on, and its node."""

    def __init__(self, kind: str, first: int, last: int, at: int | None = None, node: ast.AST | None = None,
                 alias: ast.alias | None = None):
        self.kind, self.first, self.last, self.at, self.node, self.alias = kind, first, last, at, node, alias
        self.deleted = False       # a later `del` in the same scope removes the name
        self.typing_only = False   # an import under `if TYPE_CHECKING:`


# ----------------------------------------------------------------------------
# what a scope binds

def blocks(node: ast.AST):
    """The statement lists of a compound statement that is not a scope, in the order of the
    source: a try's body, its handlers, its else, its finally."""
    part = getattr(node, "body", None)
    if isinstance(part, list):
        yield part
    for handler in getattr(node, "handlers", ()):
        yield handler.body
    for field in ("orelse", "finalbody"):
        part = getattr(node, field, None)
        if isinstance(part, list):
            yield part
    for case in getattr(node, "cases", ()):
        yield case.body


def type_checking(test: ast.AST) -> bool:
    return (test.id if isinstance(test, ast.Name) else test.attr if isinstance(test, ast.Attribute) else "") == "TYPE_CHECKING"


def statements(body: list):
    """Every statement of a scope's body, inside its blocks and never inside a nested scope."""
    for node in body:
        yield node
        if not isinstance(node, SCOPES):
            for block in blocks(node):
                yield from statements(block)


def targets(node: ast.AST):
    """The targets an assignment statement binds, tuples taken apart."""
    if isinstance(node, ast.Assign):
        stack = list(node.targets)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        stack = [node.target]
    elif hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
        stack = [node.name]
    else:
        return
    while stack:
        target = stack.pop(0)
        if isinstance(target, (ast.Tuple, ast.List)):
            stack = list(target.elts) + stack
        elif isinstance(target, ast.Starred):
            stack.insert(0, target.value)
        else:
            yield target


def is_static(method: ast.AST) -> bool:
    return any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in method.decorator_list)


def bound(scope: ast.AST) -> dict[str, list[Landing]]:
    """{name: its bindings, in the order the head gives} for a module, a class or a function."""
    out: dict[str, list[Landing]] = {}

    def add(name: str, landing: Landing) -> None:
        out.setdefault(name, []).append(landing)

    own = list(statements(scope.body))
    unrun = set()  # the statements under `if TYPE_CHECKING:`, which do not run
    for node in own:
        if isinstance(node, ast.If) and type_checking(node.test):
            unrun |= {id(inner) for inner in statements(node.body)}
    for node in own:
        if isinstance(node, SCOPES):
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            add(node.name, Landing(kind, first, node.end_lineno, node.lineno, node))
        elif isinstance(scope, DEFS):
            continue  # a function's own variables are not pointed at
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name != "*":
                    landing = Landing("import", node.lineno, node.end_lineno, node=node, alias=alias)
                    landing.typing_only = id(node) in unrun
                    add(alias.asname or alias.name.split(".")[0], landing)
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                for landing in out.get(target.id, ()) if isinstance(target, ast.Name) else ():
                    landing.deleted = True
        else:
            for target in targets(node):
                if isinstance(target, ast.Name):
                    add(target.id, Landing("assignment", node.lineno, node.end_lineno, node=node))
    if not isinstance(scope, ast.ClassDef):
        return out
    for node in own:  # what __slots__ names
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__slots__" for t in node.targets):
            value = node.value
            items = (value.elts if isinstance(value, (ast.Tuple, ast.List, ast.Set))
                     else value.keys if isinstance(value, ast.Dict) else [value])
            for item in items:
                if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value not in out:
                    add(item.value, Landing("slot", node.lineno, node.end_lineno, node=node))
    found: dict[str, list[tuple[ast.AST, ast.AST]]] = {}  # what the methods assign on `self`
    for method in own:
        if not isinstance(method, DEFS) or is_static(method):
            continue
        parameters = method.args.posonlyargs + method.args.args
        mine = {"self"} if parameters and parameters[0].arg == "self" else set()
        if method.name == "__new__" and not any(isinstance(b, ast.Name) and b.id == "type" for b in scope.bases):
            # the instance is a local there: `made = object.__new__(cls)`. A call with four
            # arguments makes a class (a metaclass's), whose attributes are not this class's.
            for node in statements(method.body):
                if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and len(node.value.args) < 4
                        and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "__new__"):
                    mine |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        if not mine:
            continue
        stack = list(method.body)
        inside = []
        while stack:
            node = stack.pop(0)
            if isinstance(node, SCOPES + (ast.Lambda,)):
                continue
            inside.append(node)
            stack = [child for child in ast.iter_child_nodes(node) if isinstance(child, ast.stmt)
                     or isinstance(child, (ast.ExceptHandler, getattr(ast, "match_case", ast.ExceptHandler)))] + stack
        for node in sorted(inside, key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0))):
            for target in targets(node):
                if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                        and target.value.id in mine):
                    places = found.setdefault(target.attr, [])
                    if not any(stmt is node for _m, stmt in places):
                        places.append((method, node))
    for name, places in found.items():
        if name in out:
            continue  # the class's body declares it
        initial = [place for place in places if place[0].name == "__init__"]
        for _method, node in initial or [place for place in places if place[0] is places[0][0]]:
            add(name, Landing("attribute", node.lineno, node.end_lineno, node=node))
    return out


# ----------------------------------------------------------------------------
# the trees

class Tree:
    """One tree at one commit: its files, read as the commit's bytes, and parsed on demand."""

    def __init__(self, name: str, path: str, commit: str):
        self.name, self.dir, self.commit = name, path, commit
        self.files = set(pin.files(path))
        self._parsed: dict[str, tuple] = {}
        self._bound: dict[tuple, dict] = {}
        self._names: dict[str, list[str]] | None = None

    def read(self, path: str) -> bytes:
        with open(os.path.join(self.dir, *path.split("/")), "rb") as f:
            return f.read()

    def holds_directory(self, path: str) -> bool:
        return any(f.startswith(path + "/") for f in self.files)

    def parsed(self, path: str) -> tuple[ast.Module, list[bytes]]:
        """The module's syntax tree and its lines as bytes."""
        if path not in self._parsed:
            data = self.read(path)
            try:
                # lines as Python counts them: a lone carriage return ends one too
                self._parsed[path] = (ast.parse(data, filename=path), data.splitlines(keepends=True))
            except (SyntaxError, ValueError, MemoryError, RecursionError) as error:
                self._parsed[path] = (None, f"{path} does not parse ({type(error).__name__})")
        tree, lines = self._parsed[path]
        if tree is None:
            raise Unresolved(lines)
        return tree, lines

    def bound(self, path: str, scope: ast.AST) -> dict[str, list[Landing]]:
        key = (path, id(scope))
        if key not in self._bound:
            self._bound[key] = bound(scope)
        return self._bound[key]

    def module(self, dotted: str) -> str | None:
        """The file a dotted module name is, by its path from the tree's root."""
        base = dotted.replace(".", "/")
        for candidate in (base + ".py", base + "/__init__.py"):
            if candidate in self.files:
                return candidate
        return None

    def named_like(self, path: str) -> list[str]:
        """Other files of the tree with the same file name: what a wrong path probably meant."""
        if self._names is None:
            self._names = {}
            for f in sorted(self.files):
                self._names.setdefault(f.rsplit("/", 1)[-1], []).append(f)
        return self._names.get(path.rstrip("/").rsplit("/", 1)[-1], [])


class World:
    """The trees of pin.json, each checked against its pin the first time it is used. `swap`
    puts the tree at another directory in a pinned tree's place, at whatever commit it is at."""

    def __init__(self, book: str | None = None, swap: dict[str, str] | None = None):
        self.book = pin.root(book)
        self.pinned = pin.load(book)
        self.subject = self.pinned["subject"]
        self.names = list(self.pinned["trees"])
        self.swap = dict(swap or {})
        unknown = [name for name in self.swap if name not in self.pinned["trees"]]
        if unknown:
            raise SystemExit(f"--tree: {', '.join(unknown)} is not a tree of {pin.PIN_FILE} ({', '.join(self.names)})")
        self.tops = dict(pin.libraries(book))  # the name a library is imported by -> its tree
        self._trees: dict[str, Tree] = {}
        self._directories: dict[tuple, str] = {}  # a directory's fingerprint, taken once

    def tree(self, name: str) -> Tree:
        if name not in self._trees:
            entry = self.pinned["trees"][name]
            path = pin.tree(name, self.book)
            if name in self.swap:
                path = os.path.abspath(self.swap[name])
                head = pin.git(path, "rev-parse", "-q", "--verify", "HEAD", check=False) if os.path.isdir(path) else ""
                entry = {"commit": head or "no commit"}
            why = pin.problems(entry, path)
            if why:
                raise SystemExit(f"{name} at {path} is not {'a tree as its commit holds it' if name in self.swap else 'at the pin'}"
                                 f" ({'; '.join(why)})" + ("" if name in self.swap else ": `python tools/pin.py fetch`"))
            self._trees[name] = Tree(name, path, entry["commit"])
        return self._trees[name]

    def home(self, dotted: str) -> tuple[Tree, str] | None:
        """The tree and file of a dotted module name: a pinned library's by the name it is
        imported by, else the subject's."""
        top = dotted.split(".")[0]
        tree = self.tree(self.tops[top]) if top in self.tops else self.tree(self.subject)
        path = tree.module(dotted)
        return (tree, path) if path else None

    # -- pointers ------------------------------------------------------------

    def parse(self, body: str) -> tuple[str, str, str | None]:
        """A pointer as written -> (tree, path, symbol)."""
        if "@" in body:
            raise Unresolved("the commit is named once, at the head of the document, never inside a pointer")
        if "*" in body or "?" in body:
            raise Unresolved("a pointer is one path, not a pattern")
        if "\\" in body:
            raise Unresolved("the path is written with forward slashes")
        stray = sorted({ch for ch in body if ch in STOP})
        if stray:
            raise Unresolved(f"a pointer is a path, a colon and a symbol, and cannot hold {' '.join(repr(ch) for ch in stray)}; "
                             f"literal text is written with its quotes inside the span")
        parts = body.split(":")
        tree = self.subject
        if len(parts) > 1 and "/" not in parts[0]:
            if parts[0] not in self.names:
                raise Unresolved(f"no tree `{parts[0]}` in {pin.PIN_FILE} (it has {', '.join(self.names)})")
            tree = parts.pop(0)
        if len(parts) > 2:
            raise Unresolved("a pointer is `path:Symbol`, with one colon between them")
        path, symbol = parts[0], parts[1] if len(parts) == 2 else None
        if symbol is not None and not SYMBOL.fullmatch(symbol):
            raise Unresolved(f"the symbol `{symbol}` is not names joined by dots")
        if not path or path.startswith("/") or "//" in path or any(p in (".", "..") for p in path.split("/")):
            raise Unresolved("the path is written from the tree's root, with no leading slash and no `.` or `..`")
        return tree, path, symbol

    def resolve(self, name: str, path: str, symbol: str | None) -> tuple[str, list[Landing]]:
        """Where a pointer lands: its kind and its bindings. Raises Unresolved."""
        tree = self.tree(name)
        if path.endswith("/"):
            bare = path.rstrip("/")
            if symbol is not None:
                raise Unresolved("a directory takes no symbol")
            if tree.holds_directory(bare):
                return "directory", []
            raise Unresolved(f"{bare} is a file: no final slash" if bare in tree.files
                             else self.no_path(tree, bare, "directory"))
        if path not in tree.files:
            raise Unresolved(f"{path} is a directory: write `{path}/`" if tree.holds_directory(path)
                             else self.no_path(tree, path, "file"))
        if symbol is None:
            return "file", []
        if not path.endswith(".py"):
            raise Unresolved(f"{path} is not Python: it takes no symbol")
        _tree, _path, _scope, landings = self.walk(tree, path, symbol.split("."))
        return landings[0].kind, landings

    def no_path(self, tree: Tree, path: str, what: str) -> str:
        like = [f for f in tree.named_like(path) if f != path][:3]
        hint = f" (there is {', '.join(like)})" if like and what == "file" else ""
        return f"{tree.name} at {tree.commit[:12]} holds no {what} {path}{hint}"

    def walk(self, tree: Tree, path: str, segments: list[str], through: bool = False,
             depth: int = 0) -> tuple[Tree, str, str, list[Landing]]:
        """Follow dotted names from a module's top: -> (tree, path, the dotted name of the scope
        that binds the last one, its bindings). With `through`, an import is followed to what it
        imports and a name `import *` brings in is looked for where it comes from: that is how
        a name is resolved (tools/names.py). Without it every name must be bound in this file,
        which is how a pointer is."""
        module, _lines = tree.parsed(path)
        scope, dotted = module, ""
        for at, segment in enumerate(segments):
            last = at == len(segments) - 1
            names = tree.bound(path, scope)
            where = f"`{dotted}`" if dotted else "the module"
            if segment not in names:
                if through and scope is module and depth < DEPTH:
                    for star in self.starred(tree, path, module, segment):
                        try:
                            self.walk(star[0], star[1], [segment], True, depth + 1)
                        except Unresolved:
                            continue  # not from this one; what fails after the name is found is the walk's to say
                        return self.walk(star[0], star[1], segments[at:], True, depth + 1)
                hint = ""
                if isinstance(scope, ast.ClassDef):
                    base = self.declaring(tree, path, scope, segment, within=dotted.rpartition(".")[0])
                    hint = f"; `{base[2]}` in {base[1]} declares it" if base else ""
                elif any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
                         for n in statements(module.body)) and scope is module and not through:
                    hint = "; a name that only `import *` brings in is bound by no statement"
                if not hint:
                    close = difflib.get_close_matches(segment, list(names), 1)
                    hint = f"; it has `{close[0]}`" if close else ""
                raise Unresolved(f"{where} in {path} binds no `{segment}`{hint}",
                                 scope=(tree.name, path, dotted), missing=segment, rest=tuple(segments[at + 1:]))
            landings = names[segment]
            if isinstance(scope, ast.ClassDef) and all(landing.kind == "attribute" for landing in landings):
                base = self.declaring(tree, path, scope, segment, within=dotted.rpartition(".")[0])
                if base:  # assigned on self here, and a base's own body declares it: the base's member
                    raise Unresolved(f"`{dotted}` in {path} only assigns `{segment}` on self; `{base[2]}` in {base[1]} "
                                     f"declares it", scope=(tree.name, path, dotted), missing=segment,
                                     rest=tuple(segments[at + 1:]))
            if through and all(landing.typing_only for landing in landings):
                raise Unresolved(f"{path} imports `{segment}` only under `if TYPE_CHECKING`: it is no name when the code runs")
            if through and landings[0].kind == "import" and depth < DEPTH:
                target = self.imported(tree, path, landings[0])
                if target is not None:
                    onward = list(target[2]) + segments[at + 1:]
                    if onward:
                        return self.walk(target[0], target[1], onward, True, depth + 1)
                    return target[0], target[1], "", [Landing("module", 1, 1)]
            if last:
                return tree, path, dotted, landings
            inner = [landing for landing in landings if landing.kind in ("class", "function")]
            if not inner:
                why = Unresolved(f"`{segment}` in {path} is {'an ' if landings[0].kind[0] in 'ai' else 'a '}"
                                 f"{landings[0].kind}: nothing can be named inside it")
                node, alias = landings[0].node, landings[0].alias
                if isinstance(node, ast.Import):
                    why.outside = (alias.name if alias.asname else alias.name.split(".")[0]).split(".") + segments[at + 1:]
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    why.outside = node.module.split(".") + [alias.name] + segments[at + 1:]
                raise why
            if len(inner) > 1:  # defined twice: the rest must be found in one of them
                for landing in inner:
                    with contextlib.suppress(Unresolved):
                        found = self.walk_in(tree, path, landing.node, f"{dotted}.{segment}".strip("."),
                                             segments[at + 1:], through, depth)
                        return found
            scope, dotted = inner[0].node, f"{dotted}.{segment}".strip(".")
        return tree, path, dotted, [Landing("module", 1, 1)]

    def walk_in(self, tree, path, scope, dotted, segments, through, depth):
        """The rest of a walk, begun inside one definition."""
        for at, segment in enumerate(segments):
            names = tree.bound(path, scope)
            if segment not in names:
                raise Unresolved(f"`{dotted}` in {path} binds no `{segment}`",
                                 scope=(tree.name, path, dotted), missing=segment, rest=tuple(segments[at + 1:]))
            landings = names[segment]
            if at == len(segments) - 1:
                return tree, path, dotted, landings
            inner = [landing for landing in landings if landing.kind in ("class", "function")]
            if not inner:
                raise Unresolved(f"`{segment}` in {path} is no class or function: nothing can be named inside it")
            scope, dotted = inner[0].node, f"{dotted}.{segment}"
        raise Unresolved("nothing to find")

    def imported(self, tree: Tree, path: str, landing: Landing) -> tuple[Tree, str, tuple] | None:
        """What an import binding stands for: (tree, file, the names still to find in it), or
        None when it leaves the pinned trees."""
        node, alias = landing.node, landing.alias
        if isinstance(node, ast.Import):
            dotted = alias.name if alias.asname else alias.name.split(".")[0]
            found = self.home(dotted)
            return (found[0], found[1], ()) if found else None
        sub = self.origin(tree, path, node, alias.name)
        if sub:
            return sub[0], sub[1], ()
        home = self.origin(tree, path, node)
        return (home[0], home[1], (alias.name,)) if home else None

    def origin(self, tree: Tree, path: str, node: ast.ImportFrom, name: str | None = None) -> tuple[Tree, str] | None:
        """The module a `from ... import` names, or its submodule `name`: (tree, file)."""
        if not node.level:
            return self.home(node.module + (f".{name}" if name else ""))
        package = path.split("/")[:-1]
        if node.level - 1 > len(package):
            return None
        base = package[:len(package) - (node.level - 1)] + (node.module.split(".") if node.module else [])
        found = tree.module(".".join(base + ([name] if name else []))) if base else None
        return (tree, found) if found else None  # a relative import stays in its own tree

    def starred(self, tree: Tree, path: str, module: ast.Module, name: str):
        """The modules a file takes every name from by `import *`, where they may hold `name`."""
        for node in statements(module.body):
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                home = self.origin(tree, path, node)
                if home is None:
                    continue
                listed = self.exported(home[0], home[1])
                if name in listed if listed is not None else not name.startswith("_"):
                    yield home

    def exported(self, tree: Tree, path: str) -> set[str] | None:
        """What a module's `__all__` lists, when it is written out as strings."""
        try:
            module, _lines = tree.parsed(path)
        except Unresolved:
            return None
        names, seen = set(), False
        for node in statements(module.body):
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets(node)):
                value = getattr(node, "value", None)
                if not isinstance(value, (ast.List, ast.Tuple)):
                    return None
                seen = True
                names |= {e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        return names if seen else None

    def declaring(self, tree: Tree, path: str, cls: ast.ClassDef, member: str, depth: int = 0, within: str = ""):
        """The base class whose body declares the member: (tree, path, dotted name), or None.
        `within` is the dotted name of the scope the class stands in: a base's name is looked
        for there first, then in the scopes around it, then at the module's top."""
        if depth > DEPTH:
            return None
        around = within.split(".") if within else []
        for base in cls.bases:
            written = ast.unparse(base)
            if not SYMBOL.fullmatch(written):
                continue
            found = None
            for outer in range(len(around), -1, -1):
                try:
                    found = self.walk(tree, path, around[:outer] + written.split("."), through=True)
                    break
                except (Unresolved, SystemExit):
                    continue
            for landing in found[3] if found else ():
                if landing.kind == "class":
                    name = f"{found[2]}.{landing.node.name}".strip(".")
                    if member in found[0].bound(found[1], landing.node):
                        return found[0].name, found[1], name
                    higher = self.declaring(found[0], found[1], landing.node, member, depth + 1, within=found[2])
                    if higher:
                        return higher
        return None

    def fingerprint(self, name: str, path: str, kind: str, landings: list[Landing]) -> str:
        tree = self.tree(name)
        digest = hashlib.sha256()
        if kind == "directory":
            if (name, path) in self._directories:
                return self._directories[name, path]
            for f in sorted(f for f in tree.files if f.startswith(path.rstrip("/") + "/")):
                digest.update(f.encode("utf-8") + b"\0" + hashlib.sha256(tree.read(f)).hexdigest().encode() + b"\n")
            self._directories[name, path] = digest.hexdigest()[:16]
        elif kind == "file":
            digest.update(tree.read(path))
        else:
            lines = tree.parsed(path)[1]
            for i, landing in enumerate(landings):
                digest.update((b"\0" if i else b"") + b"".join(lines[landing.first - 1:landing.last]).rstrip(b"\r\n"))
        return digest.hexdigest()[:16]


# ----------------------------------------------------------------------------
# documents

class Span:
    def __init__(self, line: int, body: str, sentence: str, block: bool = False, before: str = ""):
        self.line, self.body, self.sentence, self.block = line, body, sentence, block
        self.before = before  # what its own line holds before it
        self.section = 0  # the line of the `##` heading the span stands under; 0 above the first


def code_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, body) of every code span in a run of prose, by CommonMark's rule: a run
    of backticks closes at the next run of the same length, and a backtick after a backslash
    opens nothing."""
    out, at = [], 0
    while True:
        opening = RUN.search(text, at)
        if not opening:
            return out
        escapes = len(text[:opening.start()]) - len(text[:opening.start()].rstrip("\\"))
        if escapes % 2:
            at = opening.start() + 1
            continue
        closing = next((c for c in RUN.finditer(text, opening.end()) if len(c.group()) == len(opening.group())), None)
        if closing is None:
            at = opening.end()
            continue
        body = text[opening.end():closing.start()].replace("\n", " ")
        if body[:1] == " " == body[-1:] and body.strip():
            body = body[1:-1]
        out.append((opening.start(), closing.end(), body))
        at = closing.end()


def sentence(text: str, start: int, end: int, spans: list[tuple[int, int, str]]) -> str:
    """The sentence of `text` that holds [start, end), cut where the head says."""
    cuts = [0]
    for m in ENDS.finditer(text):
        if any(a <= m.start() < b for a, b, _body in spans) or ABBREVIATED.search(text[:m.end()]):
            continue
        cuts.append(m.end())
    cuts.append(len(text))
    first = max(c for c in cuts if c <= start)
    last = min(c for c in cuts if c >= end)
    bare = text[first:last]
    for a, b, _body in sorted(spans, reverse=True):
        if first <= a and b <= last:
            bare = bare[:a - first] + bare[b - first:]
    if not any(ch.isalnum() for ch in bare):  # code spans and no word: the pointer of what came before it
        first, last = 0, len(text)
    return " ".join(text[first:last].split())


def read(path: str) -> tuple[list[Span], list[str]]:
    """Every code span of a markdown file outside its fenced blocks, and every entry of its
    `runtime-names` blocks; and the file's lines. Each span knows the line of the `##`
    heading it stands under (`section`; 0 above the first): tools/names.py --sections binds
    a name within its section. A section begins at a top-level `##`, indented three spaces
    at most: one in a quotation or a list item, or indented four spaces, begins none, as the
    site's sections are the top-level headings alone."""
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().replace("\r\n", "\n").replace("\r", "\n").split("\n")
    spans: list[Span] = []
    items: list[tuple[int, list[str], bool]] = []  # (first line, lines, is a table row)
    sections: list[int] = []  # the lines of the `##` headings outside fences
    fence, label, current, fence_quoted, fence_indent = None, "", None, False, 0
    for number, raw in enumerate(lines, 1):
        quoted = bool(QUOTED.match(raw))
        line = QUOTED.sub("", raw)
        opened = FENCE.match(line)
        indent = len(line) - len(line.lstrip())
        if fence and fence_quoted and not quoted:
            fence = None  # a fence opened in a quotation ends with it
        if fence:
            if (opened and opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence) and not opened.group(2).strip()
                    and indent <= fence_indent + 3):  # indented further, it is the block's own text
                fence = None
            elif label == BLOCK:
                for word in line.split("#")[0].split():
                    spans.append(Span(number, word, " ".join(line.split()), block=True))
            continue
        if opened and not (opened.group(1)[0] == "`" and "`" in opened.group(2)):  # a backtick fence's label holds none
            fence, label, current, fence_quoted = opened.group(1), (opened.group(2).split() or [""])[0], None, quoted
            fence_indent = indent
            continue
        if not line.strip():
            current = None
            continue
        row = line.lstrip().startswith("|")
        if current is None or row or current[2] or ITEM.match(line) or HEADING.match(line):
            current = (number, [], row)
            items.append(current)
        current[1].append(line)
        if HEADING.match(line):
            current = None
            if SECTION.match(raw):  # on the raw line: a `##` in a quotation or a list item, or indented four spaces, begins none
                sections.append(number)
    for first, held, row in items:
        text = "\n".join(held)
        found = code_spans(text)
        for start, end, body in found:
            whole = " ".join(text.split()) if row else sentence(text, start, end, found)
            whole = HEADING.sub("", ITEM.sub("", whole, 1), 1).strip()
            spans.append(Span(first + text.count("\n", 0, start), body, whole,
                              before=text[text.rfind("\n", 0, start) + 1:start]))
    spans.sort(key=lambda s: s.line)
    for span in spans:
        span.section = max((at for at in sections if at <= span.line), default=0)
    return spans, lines


def is_pointer(body: str, world: World) -> bool:
    """Is the span a pointer, well formed or not? One that is and does not parse is refused."""
    if not body or body[0] in QUOTES or "://" in body:
        return False  # it opens with a quote: literal text; or it is a URL
    if ".py:" in body or ".py#" in body:
        return True
    if any(ch in QUOTES for ch in body):
        return False
    words = body.split()
    if len(words) > 1:  # white space: a pointer only if it begins with a Python file's path
        return "/" in words[0] and words[0].rstrip(":").endswith(".py")
    if "/" in body or ("\\" in body and ".py" in body):
        return True
    left, colon, right = body.partition(":")
    if not colon or not ("." in right or "/" in right):
        return False
    known = [name.casefold() for name in world.names]
    return left in world.names or bool(difflib.get_close_matches(left.casefold(), known, 1, 0.75))


def documents(arguments: list[str], skip: str | None = None) -> list[tuple[str, str]]:
    """(the file, its name under the directory it was found through) for every document."""
    out = []
    for argument in arguments:
        if os.path.isdir(argument):
            for dp, dirs, names in os.walk(argument):
                dirs.sort()
                for name in sorted(names):
                    full = os.path.join(dp, name)
                    if name.endswith(".md") and not (skip and os.path.abspath(full).startswith(os.path.abspath(skip) + os.sep)):
                        out.append((full, os.path.relpath(full, argument).replace(os.sep, "/")))
        elif os.path.isfile(argument):
            out.append((argument, os.path.basename(argument)))
        else:
            raise SystemExit(f"{argument}: no such document")
    return out


def examine(world: World, path: str, head: bool = True, only: set | None = None) -> tuple[list[dict], list[str], int, int]:
    """A document's pointers as report records, what is wrong with them, how many of its code
    spans were not pointers, and how many were. With `only`, the pointers into those trees."""
    spans, lines = read(path)
    shown = os.path.basename(path)
    records, problems, other, seen, first = [], [], 0, 0, None
    for span in spans:
        if not is_pointer(span.body, world):
            other += not span.block
            continue
        first = first or span
        name = None
        try:
            name, file, symbol = world.parse(span.body)
            if only is not None and name not in only:
                continue
            seen += 1
            kind, landings = world.resolve(name, file, symbol)
        except Unresolved as why:
            if only is None or name in only:
                seen += name is None
                problems.append(f"{shown}:{span.line}: `{span.body}`: {why}")
            continue
        record = {"pointer": span.body, "line": span.line, "sentence": span.sentence, "tree": name,
                  "path": file, "symbol": symbol, "kind": kind}
        if kind == "file":
            data = world.tree(name).read(file)
            lines_in = len(data.splitlines())
            record["lines"] = [1, lines_in] if lines_in else [0, 0]
        elif landings:
            record["lines"] = [landings[0].first, landings[0].last]
            if landings[0].at and landings[0].at != landings[0].first:
                record["at"] = landings[0].at
            if len(landings) > 1:
                record["more"] = [[landing.first, landing.last] for landing in landings[1:]]
        record["fingerprint"] = world.fingerprint(name, file, kind, landings)
        records.append(record)
    if head and first:
        commit = world.tree(world.subject).commit
        above = "\n".join(lines[:first.line - 1] + [first.before])
        if not any(commit.startswith(run) for run in HEX.findall(above)):
            problems.insert(0, f"{shown}:{first.line}: the document does not name the commit its pointers are verified "
                               f"against, {commit[:12]}, before its first pointer")
    return records, problems, other, seen


def report(world: World, name: str, records: list[dict]) -> str:
    trees = {tree: world.tree(tree).commit for tree in sorted({r["tree"] for r in records})}
    body = {"generated": {"tool": TOOL, "trees": trees}, "document": name.rsplit("/", 1)[-1], "pointers": records}
    return json.dumps(body, indent=1, ensure_ascii=False) + "\n"


def report_path(full: str, relative: str, folder: str | None) -> str:
    stem = (os.path.join(folder, *relative.split("/")) if folder else full)
    return (stem[:-3] if stem.endswith(".md") else stem) + SUFFIX


def stale(text: str, on_disk: str) -> list[str]:
    """How a report on disk differs from the one that would be written, pointer by pointer."""
    try:
        old = {(r["pointer"], r["line"]): r for r in json.loads(on_disk)["pointers"]}
    except (ValueError, KeyError, TypeError):
        return ["its report is not one the tool wrote"]
    new = {(r["pointer"], r["line"]): r for r in json.loads(text)["pointers"]}
    out = [f"`{key[0]}` (line {key[1]}) lands on bytes that have changed since the report was written"
           for key in new if key in old and old[key].get("fingerprint") != new[key]["fingerprint"]]
    return out or ["its report is not what the tool writes now"]


def count(n: int, what: str) -> str:
    return f"{n} {what}" + ("" if n == 1 else "s")


def run(book: str | None, arguments: list[str], check: bool = False, folder: str | None = None) -> int:
    world = World(book)
    failed = pointers = imports = others = 0
    found = documents(arguments, folder)
    targets_ = [os.path.normcase(os.path.abspath(report_path(full, relative, folder))) for full, relative in found]
    twice = sorted({t for t in targets_ if targets_.count(t) > 1})
    if twice:
        raise SystemExit(f"two documents would share the report {twice[0]}")
    # a report beside no document, in a directory this run was given whole. Under --report DIR
    # nothing is looked for: a report there may be another run's.
    for base in ([] if folder else [a for a in arguments if os.path.isdir(a)]):
        for dp, _dirs, names in os.walk(base):
            for name in sorted(names):
                full = os.path.join(dp, name)
                stem = full[:-len(SUFFIX)]
                if name.endswith(SUFFIX) and not os.path.isfile(stem + ".md") and not os.path.isfile(stem):
                    if check:
                        failed += 1
                        print(f"{os.path.relpath(full, base).replace(os.sep, '/')}: a report with no document")
                    else:
                        os.remove(full)
    for full, relative in found:
        records, problems, other, seen = examine(world, full)
        pointers, others = pointers + seen, others + other
        imports += sum(r["kind"] == "import" for r in records)
        for line in problems:
            print(line)
        target = report_path(full, relative, folder)
        on_disk = None
        if os.path.isfile(target):
            with open(target, encoding="utf-8", newline="") as f:
                on_disk = f.read()
        if problems:
            failed += 1
            continue
        text = report(world, relative, records) if records else None
        if check:
            if text != on_disk:
                failed += 1
                for line in (["it has no report"] if on_disk is None else ["it has a report and no pointer"]
                             if text is None else stale(text, on_disk)):
                    print(f"{relative}: {line}")
        elif text is None:
            if on_disk is not None:
                os.remove(target)
        elif text != on_disk:
            os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    landing = f", {imports} of them landing on an import" if imports else ""
    print(f"pointers: {'FAILED' if failed else 'ok'}, {count(pointers, 'pointer')} in {count(len(found), 'document')}"
          f"{landing}; {count(others, 'other code span')}"
          + (f"; {count(failed, 'document')} or stray report{'s' if failed != 1 else ''} failed" if failed else ""))
    return 1 if failed else 0


def compare(book: str | None, arguments: list[str], swap: dict[str, str]) -> int:
    """Each pointer into a swapped tree, resolved at the pin and in the other tree: what is
    gone there, what has changed. Pointers into the other trees are not looked at."""
    here, there = World(book), World(book, swap)
    gone = changed = same = 0
    for full, _relative in documents(arguments):
        shown = os.path.basename(full)
        new, problems, _other, _seen = examine(there, full, head=False, only=set(swap))
        for line in problems:
            gone += 1
            print(line.replace(": `", ": gone: `", 1))
        old = {(r["pointer"], r["line"]): r["fingerprint"] for r in examine(here, full, head=False, only=set(swap))[0]}
        for record in new:
            key = (record["pointer"], record["line"])
            if key in old and old[key] != record["fingerprint"]:
                changed += 1
                print(f"{shown}:{record['line']}: changed: `{record['pointer']}` lands on other bytes")
            else:
                same += 1
    where = ", ".join(f"{name} at {there.tree(name).commit[:12]}" for name in swap)
    print(f"pointers against {where}: {gone} gone, {changed} changed, {same} the same")
    return 1 if gone or changed else 0


def show_spans(book: str | None, arguments: list[str]) -> int:
    world = World(book)
    for full, _relative in documents(arguments):
        for span in read(full)[0]:
            if not span.block:
                print(f"{os.path.basename(full)}:{span.line}: {'pointer' if is_pointer(span.body, world) else 'other  '}  `{span.body}`")
    return 0


# ----------------------------------------------------------------------------
# the probe

PROBE_A = '''import os
from pkg import b

LIMIT = 1


@decorated
@twice
class A(b.B):
    kind = "a"
    __slots__ = ("slotted",)

    def __init__(self):
        self.made = 1
        self.kind = "b"

    @property
    def size(self):
        return 1

    @size.setter
    def size(self, value):
        self.late = value

    def one(self):
        def inner():
            pass
        self.late = 2
        return inner

    class Meta:
        flag = True


if os.name == "nt":
    def where():
        return "here"
else:
    def where():
        return "there"


def outer():
    class Local:
        def method(self):
            pass
    x = 1
    return Local
'''
PROBE_C = '''FIRST, *REST = 1, 2, 3
A, B = 1, 2
LIMIT: int = 1
BARE: int
COUNT = 0
COUNT += 1
type Alias = int
try:
    import fcntl
except ImportError:
    def lock():
        pass
else:
    def lock():
        pass
match COUNT:
    case 1:
        def matched():
            pass
if COUNT:
    class K:
        def a(self):
            pass
else:
    class K:
        def b(self):
            pass
GONE = 1
del GONE
class S:
    __slots__ = ["in_list"]
class T:
    __slots__ = "only"
class U:
    __slots__ = {"keyed": "doc"}
class V:
    def __init__(self, /):
        if COUNT:
            self.cond = 1
        def helper():
            self.inner = 1
    def __new__(cls):
        made = object.__new__(cls)
        made.fresh = 1
        cls.on_class = 1
        return made
    @classmethod
    def build(cls):
        cls.built = 1
class W(V):
    def again(self):
        self.cond = 2
        self.own = 3
if TYPE_CHECKING:
    from pkg.b import Root
if typing.TYPE_CHECKING:
    from pkg.b import B as TypedB
else:
    from pkg.b import B as RealB
try:
    if TYPE_CHECKING:
        from pkg.b import Early as TypedEarly
except ImportError:
    pass
TWICE = 1
TWICE = 2
del TWICE
BACK = 1
del BACK
BACK = 2
class X:
    def __new__(cls, value):
        if value:
            made = tuple.__new__(cls, value)
        other = make(cls)
        other.z = 1
        made.w = 1
        return made
class Meta(type):
    def __new__(mcs, *args):
        new_class = super().__new__(mcs, *args)
        new_class.media = 1
        return new_class
class Sub(Unknown):
    def __new__(mcs, name, bases, attrs):
        new_class = super().__new__(mcs, name, bases, attrs)
        new_class.fields = 1
        return new_class
class Plain:
    hidden = 0
class Outer:
    class Plain:
        pass
    class Leaf(Plain):
        def __init__(self):
            self.hidden = 1
'''
PROBE_TREE = {
    "pkg/__init__.py": "from pkg.a import A\nfrom pkg.b import *\nfrom pkg import sub\nfrom pkg.sub.leaf import *\n"
                       "from pkg.computed import *\n",
    "pkg/a.py": PROBE_A,
    "pkg/c.py": PROBE_C,
    "pkg/cr.py": "A = 1\rB = 2\n",
    "pkg/crlf.py": "A = 1\r\nB = 2\r\n",
    "pkg/empty.py": "",
    "pkg/sub/__init__.py": "from .leaf import X\nfrom . import leaf\nimport pkg.a as m\n",
    "pkg/sub/leaf.py": "X = 1\n_hidden = 2\n",
    "pkg/computed.py": "__all__ = ['Shown'] + []\n__all__ += ['More']\nShown = 1\nAlso = 2\n",
    "pkgx/y.py": "beside = 1\n",
    "pkg/b.py": "class Root:\n    def deep(self):\n        pass\n\n\nclass B(Root):\n    def inherited(self):\n        pass\n"
                "\n\nclass Early:\n    def before(self):\n        self.when = 0\n\n    def __init__(self):\n        self.when = 1\n"
                "\n    @staticmethod\n    def apart(self):\n        self.never = 1\n",
    "pkg/broken.py": "def f(:\n",
    "docs/notes.txt": "one\ntwo\n",
    "docs/bare.txt": "no final newline",
    "top.txt": "at the root\n",
}
PROBE_LIBRARY = {"lib/core.py": "class Thing:\n    pass\n", "setup.cfg": "[metadata]\n"}


def probe() -> int:
    import tempfile
    work = tempfile.mkdtemp(prefix="pointerprobe-")
    failed = []

    def expect(label: str, got, want) -> None:
        if got != want:
            failed.append(f"{label}: got {got!r}, wanted {want!r}")

    def sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()[:16]

    try:
        book = os.path.join(work, "book")
        where = os.path.join(book, "reference", "subject")
        for path, text in PROBE_TREE.items():
            pin._write(os.path.join(where, *path.split("/")), text)
        made = pin._scratch(where)
        pin._write(os.path.join(where, "pkg", "untracked.py"), "LEFT = 1\n")  # on disk, and not the commit's
        library = os.path.join(book, "reference", "lib")
        for path, text in PROBE_LIBRARY.items():
            pin._write(os.path.join(library, *path.split("/")), text)
        made_library = pin._scratch(library)
        pin._write(os.path.join(book, pin.PIN_FILE), json.dumps(
            {"subject": "subject", "python": "3.12",
             "trees": {"subject": {"repository": where, "commit": made, "path": "reference/subject"},
                       "lib": {"repository": library, "commit": made_library, "path": "reference/lib"}}}))
        world = World(book)

        def lands(pointer: str):
            """(kind, [first, last] of each binding), or the reason it does not resolve."""
            try:
                name, path, symbol = world.parse(pointer)
                kind, landings = world.resolve(name, path, symbol)
            except Unresolved as why:
                return str(why)
            return kind, [[landing.first, landing.last] for landing in landings]

        def refused(pointer: str, needle: str) -> None:
            got = lands(pointer)
            if not isinstance(got, str) or needle not in got:
                failed.append(f"{pointer}: wanted a refusal holding {needle!r}, got {got!r}")

        # what each scope binds, with its lines worked out from PROBE_A by hand
        expect("a file", lands("pkg/a.py"), ("file", []))
        expect("a directory", lands("pkg/"), ("directory", []))
        expect("a class begins at its first decorator", lands("pkg/a.py:A"), ("class", [[7, 32]]))
        expect("a module's assignment", lands("pkg/a.py:LIMIT"), ("assignment", [[4, 4]]))
        expect("an import", lands("pkg/a.py:b"), ("import", [[2, 2]]))
        expect("a re-export", lands("pkg/__init__.py:A"), ("import", [[1, 1]]))
        expect("a property and its setter", lands("pkg/a.py:A.size"), ("function", [[17, 19], [21, 23]]))
        expect("a class's own assignment, though __init__ assigns it too", lands("pkg/a.py:A.kind"), ("assignment", [[10, 10]]))
        expect("an attribute __init__ assigns", lands("pkg/a.py:A.made"), ("attribute", [[14, 14]]))
        expect("an attribute only later methods assign: the first of them", lands("pkg/a.py:A.late"), ("attribute", [[23, 23]]))
        expect("a slot", lands("pkg/a.py:A.slotted"), ("slot", [[11, 11]]))
        expect("a nested class's assignment", lands("pkg/a.py:A.Meta.flag"), ("assignment", [[32, 32]]))
        expect("a function in a method", lands("pkg/a.py:A.one.inner"), ("function", [[26, 27]]))
        expect("defined under if and under else", lands("pkg/a.py:where"), ("function", [[36, 37], [39, 40]]))
        expect("a method of a class in a function", lands("pkg/a.py:outer.Local.method"), ("function", [[45, 46]]))
        expect("__init__'s assignment, though a method before it assigns too", lands("pkg/b.py:Early.when"), ("attribute", [[16, 16]]))
        refused("pkg/b.py:Early.never", "binds no `never`")  # a static method has no self
        # the rest of what a scope binds, with its lines worked out from PROBE_C by hand
        for symbol, want in (
                ("REST", ("assignment", [[1, 1]])), ("B", ("assignment", [[2, 2]])), ("LIMIT", ("assignment", [[3, 3]])),
                ("BARE", ("assignment", [[4, 4]])), ("COUNT", ("assignment", [[5, 5], [6, 6]])),
                ("Alias", ("assignment", [[7, 7]])), ("lock", ("function", [[11, 12], [14, 15]])),
                ("matched", ("function", [[18, 19]])), ("K.a", ("function", [[22, 23]])), ("K.b", ("function", [[26, 27]])),
                ("GONE", ("assignment", [[28, 28]])), ("S.in_list", ("slot", [[31, 31]])), ("T.only", ("slot", [[33, 33]])),
                ("U.keyed", ("slot", [[35, 35]])), ("V.cond", ("attribute", [[39, 39]])),
                ("V.fresh", ("attribute", [[44, 44]])), ("W.own", ("attribute", [[53, 53]])),
                ("Root", ("import", [[55, 55]])), ("X.w", ("attribute", [[77, 77]])),
                ("Outer.Leaf.hidden", ("attribute", [[96, 96]]))):
            expect(f"pkg/c.py:{symbol}", lands(f"pkg/c.py:{symbol}"), want)
        refused("pkg/c.py:X.z", "binds no `z`")              # in __new__, a local made by some other call
        refused("pkg/c.py:Meta.media", "binds no `media`")   # a metaclass's __new__ makes a class
        refused("pkg/c.py:Sub.fields", "binds no `fields`")  # and so does a call with four arguments
        refused("pkg/c.py:V.inner", "binds no `inner`")       # assigned in a function inside the method
        refused("pkg/c.py:V.on_class", "binds no `on_class`")  # on cls, in __new__
        refused("pkg/c.py:V.built", "binds no `built`")        # on cls, in a class method
        refused("pkg/c.py:W.cond", "`V` in pkg/c.py declares it")  # assigned on self; the base declares it
        refused("pkg/a.py:A.inner", "binds no `inner`")        # it is A.one.inner
        refused("pkg/a.py:x", "binds no `x`")                  # it is a variable of outer
        refused("pkg/untracked.py", "holds no file")
        flags = world.tree("subject").bound("pkg/c.py", world.tree("subject").parsed("pkg/c.py")[0])
        expect("a deleted name and an import for type checking are marked",
               (flags["GONE"][0].deleted, flags["COUNT"][0].deleted, flags["Root"][0].typing_only, flags["fcntl"][0].typing_only),
               (True, False, True, False))
        expect("typing.TYPE_CHECKING, its else, and one inside a try",
               [flags[name][0].typing_only for name in ("TypedB", "RealB", "TypedEarly")], [True, False, True])
        expect("del marks every binding before it, and none after",
               ([l.deleted for l in flags["TWICE"]], [l.deleted for l in flags["BACK"]]), ([True, True], [True, False]))
        try:
            world.walk(world.tree("subject"), "pkg/a.py", ["os", "path"], through=True)
            failed.append("a name was found inside an import that leaves the trees")
        except Unresolved as why:
            expect("the walk says where it was left, past an import out of the trees", why.outside, ["os", "path"])
        expect("a line ending of two bytes is no part of a fingerprint", world.fingerprint(
            "subject", "pkg/crlf.py", "assignment", world.resolve("subject", "pkg/crlf.py", "A")[1]), sha(b"A = 1"))
        expect("a lone carriage return ends a line", lands("pkg/cr.py:B"), ("assignment", [[2, 2]]))
        expect("and the fingerprint is of that line", world.fingerprint(
            "subject", "pkg/cr.py", "assignment", world.resolve("subject", "pkg/cr.py", "B")[1]), sha(b"B = 2"))
        expect("a file that is not Python", lands("docs/notes.txt"), ("file", []))
        expect("in a library", lands("lib:lib/core.py:Thing"), ("class", [[1, 2]]))
        expect("a library's root file", lands("lib:setup.cfg"), ("file", []))
        expect("the subject's root file", lands("subject:top.txt"), ("file", []))
        refused("pkg/a.py:outer.x", "binds no `x`")
        refused("pkg/a.py:A.missing", "binds no `missing`")
        refused("pkg/a.py:A.inherited", "`B` in pkg/b.py declares it")
        refused("pkg/a.py:A.deep", "`Root` in pkg/b.py declares it")
        refused("pkg/a.py:A.sized", "it has `size`")
        refused("pkg/a.py:LIMIT.x", "nothing can be named inside it")
        refused("pkg/__init__.py:B", "bound by no statement")
        refused("pkg", "is a directory: write `pkg/`")
        refused("pkg/a.py/", "is a file: no final slash")
        refused("pkg/nope/", "holds no directory pkg/nope")
        refused("pkg/zz.py", "holds no file pkg/zz.py")
        refused("other/a.py", "there is pkg/a.py")
        refused("pkg/a.py:A()", "cannot hold '('")
        refused("pkg/a.py#L9", "cannot hold '#'")
        refused("pkg/a.py:A, B", "cannot hold")
        refused("pkg\\a.py", "forward slashes")
        refused("subjec:top.txt", "no tree `subjec`")
        refused("SUBJECT:top.txt", "no tree `SUBJECT`")
        refused("pkg/a.py A", "cannot hold ' '")
        refused("pkg/a.py:'A'", "not names joined by dots")
        refused("/pkg/a.py", "no leading slash")
        refused("pkg/../pkg/a.py", "no leading slash")
        refused("pkg/a.py:A@abc", "never inside a pointer")
        refused("pkg/*.py", "not a pattern")
        refused("docs/notes.txt:Thing", "is not Python")
        refused("pkg/:A", "a directory takes no symbol")
        refused("pkg/broken.py:f", "does not parse")
        refused("nolib:x/y.py", "no tree `nolib`")
        refused("pkg/a.py:A:size", "one colon")
        refused("pkg/a.py:A.1x", "not names joined by dots")
        # a name is followed through an import only when asked: that is the name gate's reading
        def followed(*names: str, start: str = "pkg/__init__.py"):
            try:
                found = world.walk(world.tree("subject"), start, list(names), through=True)
            except Unresolved as why:
                return str(why)
            return found[1], found[2], [landing.first for landing in found[3]]

        expect("an import followed", followed("A", "size"), ("pkg/a.py", "A", [17, 21]))
        expect("import * followed", followed("B", "inherited"), ("pkg/b.py", "B", [7]))
        expect("what fails past import * is said of the class", followed("B", "nope"), "`B` in pkg/b.py binds no `nope`")
        leaf = ("pkg/sub/leaf.py", "", [1])
        expect("a relative import of a name", followed("X", start="pkg/sub/__init__.py"), leaf)
        expect("a relative import of a module", followed("leaf", "X", start="pkg/sub/__init__.py"), leaf)
        # LIMIT is pkg.a's and not pkg's, so the walk must go to the module the alias names
        expect("import a.b as c stands for a.b", followed("m", "LIMIT", start="pkg/sub/__init__.py"), ("pkg/a.py", "", [4]))
        expect("a package is its __init__", followed("sub", "X"), leaf)
        expect("import * without __all__ brings in what is public", followed("X"), leaf)
        expect("and nothing private", "binds no `_hidden`" in str(followed("_hidden")), True)
        expect("a computed __all__ is not read: what is public passes", followed("Also"), ("pkg/computed.py", "", [4]))

        # a sentence is not cut inside a code span
        text = "One `a. B` two `x/y`. Three."
        expect("a full stop inside a span", sentence(text, 15, 20, code_spans(text)), "One `a. B` two `x/y`.")
        text = "A claim. And more of it. `x/y`, `z/w`."
        expect("a pointer that stands alone carries the sentences before it", sentence(text, 25, 30, code_spans(text)), text)

        # which spans are taken for pointers: the well formed, and the malformed that must be refused
        for body, want in (("pkg/a.py", True), ("subject:top.txt", True), ("lib:setup.cfg", True), ("top.txt", False),
                           ("text/html", True), ('"text/html"', False), ("'a/b'", False), ("a b/c", False),
                           ("https://x.org/y", False), ("f(a/b)", True), ("x=a/b", True), ("<int:pk>/", True),
                           ("pkg/a.py:A, B", True), ("see a.py#L1", True), ("pkg\\a.py", True), ("\\d+", False),
                           ("subjec:top.txt", True), ("SUBJECT:top.txt", True), ("key:value", False), ("dict:a.b", False),
                           ("subject:thing", False), ("pkg.a.A", False), ("other:thing", False), ("a`b/c", False),
                           ("pkg/a.py A", True), ("pkg/a.py :A", True), ("cd pkg/sub", False), ("pkg/a.py:'A'", True),
                           ("'pkg/a.py:A'", False)):
            expect(f"is `{body}` a pointer", is_pointer(body, world), want)

        # how a document is read: fences, quotations, backticks
        scrap = os.path.join(work, "scrap.md")

        def reads(body: str) -> list[str]:
            pin._write(scrap, body)
            return [span.body for span in read(scrap)[0]]

        for label, body, want in (
                ("a fence is not closed by a fence with a label", "```\n```python\n`pkg/no.py`\n```\n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("a longer fence is not closed by a shorter", "````\n```\n`pkg/no.py`\n````\n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("a tilde fence is not closed by backticks", "~~~\n```\n`pkg/no.py`\n~~~\n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("a tilde fence is a fence", "~~~\n`pkg/no.py`\n~~~\n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("a fence in a quotation is a fence", "> ```\n> `pkg/no.py`\n> ```\n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("a fence left open in a quotation ends with it", "> ```\n> `pkg/no.py`\n\nAfter it, `pkg/a.py`.\n", ["pkg/a.py"]),
                ("a fence in a list item is a fence", "- item\n\n    ```\n    `pkg/no.py`\n    ```\n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("backticks after a backtick fence make it no fence", "```x``` and then `pkg/a.py`.\n", ["x", "pkg/a.py"]),
                ("an unmatched run opens nothing", "Unmatched `` run, then `pkg/a.py`.\n", ["pkg/a.py"]),
                ("an escaped backtick opens nothing", "An escaped \\` backtick, then `pkg/a.py`.\n", ["pkg/a.py"]),
                ("two backslashes escape each other, not the backtick", "Two \\\\`pkg/a.py` here.\n", ["pkg/a.py"]),
                ("after an escaped backtick the rest of its run still opens", "x \\``pkg/a.py` y\n", ["pkg/a.py"]),
                ("a closing fence may have spaces after it", "```\n`pkg/no.py`\n```   \n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("a fence line indented four spaces inside a fence is its text", "```\n    ```\n`pkg/no.py`\n```\n\n`pkg/a.py`\n", ["pkg/a.py"]),
                ("a block's label is the first word after the fence", "```runtime-names extra\nA.x  pkg/a.py:A.one\n```\n", ["A.x", "pkg/a.py:A.one"]),
                ("an indented block is read", "Prose.\n\n    `pkg/a.py`\n", ["pkg/a.py"]),
                ("an HTML comment is read", "<!-- `pkg/a.py` -->\n", ["pkg/a.py"]),
                ("an entry's comment is not read", "```runtime-names\nA.x  pkg/a.py:A.one  # see a/b\n```\n", ["A.x", "pkg/a.py:A.one"])):
            expect(label, reads(body), want)
        pin._write(scrap, "## A heading\nText `pkg/a.py:LIMIT`.\n")
        expect("a heading does not run into the next line", [s.sentence for s in read(scrap)[0]], ["Text `pkg/a.py:LIMIT`."])
        pin._write(scrap, "`pkg/a.py` above.\n\n## One `pkg/a.py:A`\n\n`pkg/b.py`\n\n### Deeper\n\n`pkg/a.py:LIMIT`\n\n"
                          "```\n## not a heading\n```\n\n`pkg/a.py:where`\n\n## Two\n\n```runtime-names\nA.x  pkg/a.py:A.one\n```\n\n"
                          "> ## quoted\n\n`pkg/a.py:A.size`\n\n- ## in a list\n\n`pkg/b.py:B`\n\n    ## indented four\n\n`pkg/a.py:where`\n\n"
                          "   ## Three, indented three\n\n`pkg/a.py:LIMIT`\n")
        expect("the section each span stands under: a top-level `##`, not a `###`, a fenced, quoted, listed or indented one",
               [(s.body, s.section) for s in read(scrap)[0]],
               [("pkg/a.py", 0), ("pkg/a.py:A", 3), ("pkg/b.py", 3), ("pkg/a.py:LIMIT", 3), ("pkg/a.py:where", 3),
                ("A.x", 17), ("pkg/a.py:A.one", 17), ("pkg/a.py:A.size", 17), ("pkg/b.py:B", 17), ("pkg/a.py:where", 17),
                ("pkg/a.py:LIMIT", 35)])

        # a document: its spans, their lines and sentences; fenced blocks; the head
        doc = os.path.join(work, "docs", "report.md")
        text = (f"# A report\n\nVerified against `subject` at {made[:12]}.\n\n"                       # 1-4
                "The limit is set once, in `pkg/a.py:LIMIT`. A second\nsentence names ``pkg/a.py:A``"  # 5-6
                " and e.g. `pkg/b.py:B`.\n\n"                                                          # 6-7
                "- an item with `pkg/a.py:where`\n- another. With `lib:lib/core.py:Thing` in it.\n\n"  # 8-10
                "| what | where |\n|---|---|\n| the size | `pkg/a.py:A.size` |\n\n"                    # 11-14
                "```python\n`pkg/nope.py` is not read\n```\n\n"                                        # 15-18
                "> quoted: `pkg/__init__.py:A` is a re-export, and `\"text/html\"` is text.\n\n"       # 19-20
                "```runtime-names\nA.dynamic  pkg/a.py:A.one  # made there\n```\n")                    # 21-23
        pin._write(doc, text)
        records, problems, other, seen = examine(world, doc)
        expect("the document's problems, and how many pointers it has", (problems, seen), ([], 8))
        expect("pointers and their lines", [(r["pointer"], r["line"]) for r in records],
               [("pkg/a.py:LIMIT", 5), ("pkg/a.py:A", 6), ("pkg/b.py:B", 6), ("pkg/a.py:where", 8),
                ("lib:lib/core.py:Thing", 9), ("pkg/a.py:A.size", 13), ("pkg/__init__.py:A", 19), ("pkg/a.py:A.one", 22)])
        expect("spans that are not pointers", other, 2)  # `subject`, `"text/html"`
        expect("sentences", [r["sentence"] for r in records],
               ["The limit is set once, in `pkg/a.py:LIMIT`.",
                "A second sentence names ``pkg/a.py:A`` and e.g. `pkg/b.py:B`.",
                "A second sentence names ``pkg/a.py:A`` and e.g. `pkg/b.py:B`.",
                "an item with `pkg/a.py:where`", "With `lib:lib/core.py:Thing` in it.",
                "| the size | `pkg/a.py:A.size` |",
                "quoted: `pkg/__init__.py:A` is a re-export, and `\"text/html\"` is text.",
                "A.dynamic pkg/a.py:A.one # made there"])
        by = {r["pointer"]: r for r in records}
        expect("a record", {k: by["pkg/a.py:A"].get(k) for k in ("tree", "path", "symbol", "kind", "lines", "at")},
               {"tree": "subject", "path": "pkg/a.py", "symbol": "A", "kind": "class", "lines": [7, 32], "at": 9})
        expect("more than one binding", (by["pkg/a.py:A.size"]["lines"], by["pkg/a.py:A.size"].get("more")), ([17, 19], [[21, 23]]))
        expect("no `at` without a decorator", "at" in by["pkg/a.py:where"], False)
        expect("a symbol's fingerprint", by["pkg/a.py:LIMIT"]["fingerprint"], sha(b"LIMIT = 1"))
        expect("two bindings' fingerprint", by["pkg/a.py:where"]["fingerprint"],
               sha(b'    def where():\n        return "here"\0    def where():\n        return "there"'))
        a_lines = PROBE_A.encode().split(b"\n")
        expect("a class's fingerprint is its decorators and its body", by["pkg/a.py:A"]["fingerprint"],
               sha(b"\n".join(a_lines[6:32])))
        file_record = examine(world, pin_doc(
            work, made, "`pkg/a.py` and `pkg/` and `docs/notes.txt` and `docs/bare.txt` and `pkg/empty.py`"))[0]
        expect("a file's lines and fingerprint", (file_record[0]["lines"], file_record[0]["fingerprint"]),
               ([1, 48], sha(PROBE_A.encode())))
        directory = b"".join(p.encode() + b"\0" + hashlib.sha256(PROBE_TREE[p].encode()).hexdigest().encode() + b"\n"
                             for p in sorted(PROBE_TREE) if p.startswith("pkg/"))
        expect("a directory's fingerprint, and no lines", (file_record[1]["fingerprint"], "lines" in file_record[1]),
               (sha(directory), False))
        expect("a text file's lines, one with no final newline, an empty one",
               (file_record[2]["lines"], file_record[3]["lines"], file_record[4]["lines"]), ([1, 2], [1, 1], [0, 0]))

        # the head: the commit, twelve digits or more, before the first pointer
        def head_of(body: str) -> list[str]:
            return [p for p in examine(world, pin_doc(work, None, body))[1] if "does not name the commit" in p]

        expect("no commit", len(head_of("`pkg/a.py`")), 1)
        expect("eleven digits", len(head_of(f"at {made[:11]}\n\n`pkg/a.py`")), 1)
        expect("twelve digits", head_of(f"at {made[:12]}\n\n`pkg/a.py`"), [])
        expect("the whole commit", head_of(f"at `{made}`\n\n`pkg/a.py`"), [])
        expect("another commit", len(head_of(f"at {made_library}\n\n`pkg/a.py`")), 1)
        expect("twelve right digits and then wrong ones", len(head_of(f"at {made[:12]}{'0' * 28}\n\n`pkg/a.py`")), 1)
        expect("another commit beside the pin", head_of(f"at {made}, formerly {made_library}\n\n`pkg/a.py`"), [])
        expect("the commit below the first pointer", len(head_of(f"`pkg/a.py`\n\nat {made}\n\n`pkg/b.py`")), 1)
        expect("the commit on the pointer's line, before it", head_of(f"At {made[:12]}, `pkg/a.py`."), [])
        expect("the commit on the pointer's line, after it", len(head_of(f"`pkg/a.py` at {made[:12]}.")), 1)
        expect("no pointer, no head needed", head_of("nothing here, `a.b`"), [])
        code = examine(world, pin_doc(work, None, "`pkg/a.py` and `pkg/zz.py`"))
        expect("a missing head is not counted as a pointer", (len(code[1]), code[3]), (2, 2))

        # the run: reports written beside, checked, kept elsewhere; a failing document writes none
        def quiet(*args, **kwargs) -> tuple[int, str]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run(book, *args, **kwargs)
            return code, out.getvalue()

        beside = os.path.join(work, "docs", "report" + SUFFIX)

        def kept_report() -> dict:
            if not os.path.exists(beside):
                return {}
            with open(beside, encoding="utf-8") as f:
                return json.load(f)

        expect("a check before any report", quiet([doc], check=True)[0], 1)
        expect("the check wrote nothing", os.path.exists(beside), False)
        code, out = quiet([doc])
        expect("a passing run", (code, out.strip()),
               (0, "pointers: ok, 8 pointers in 1 document, 1 of them landing on an import; 2 other code spans"))
        written = kept_report()
        expect("the report's head", (written.get("generated"), written.get("document")),
               ({"tool": TOOL, "trees": {"lib": made_library, "subject": made}}, "report.md"))
        expect("the report's records", written.get("pointers"), records)
        expect("a check after", quiet([doc], check=True)[0], 0)
        pin_doc(work, made, "`pkg/a.py`")
        code, out = quiet([os.path.join(work, "docs")], check=True)  # a directory: both documents
        expect("a document with no report", (code, "other.md: it has no report" in out, "in 2 documents" in out), (1, True, True))
        os.remove(os.path.join(work, "docs", "other.md"))
        pin._write(doc, text.replace("The limit is set once", "The limit is set"))
        code, out = quiet([doc], check=True)
        expect("a report gone stale", (code, "report.md: its report is not what the tool writes now" in out), (1, True))
        pin._write(doc, text)
        pin._write(beside, json.dumps(kept_report(), indent=1).replace(by["pkg/a.py:LIMIT"]["fingerprint"], "0" * 16))
        code, out = quiet([doc], check=True)
        expect("a report whose fingerprint is not the tree's", (code, "`pkg/a.py:LIMIT` (line 5) lands on bytes that have changed" in out), (1, True))
        quiet([doc])
        expect("written again", quiet([doc], check=True)[0], 0)
        pin._write(doc, text.replace("`pkg/a.py:where`", "`pkg/a.py:nowhere`"))
        code, out = quiet([doc])
        expect("a wrong pointer fails the run and is named with its line",
               (code, "report.md:8: `pkg/a.py:nowhere`: the module in pkg/a.py binds no `nowhere`; it has `where`" in out), (1, True))
        expect("a failing document's report is left as it was", kept_report().get("pointers"), records)
        pin._write(doc, "no pointer now\n")
        quiet([doc])
        expect("a document without pointers keeps no report", os.path.exists(beside), False)
        pin._write(doc, text)
        kept = os.path.join(work, "kept")
        expect("reports kept elsewhere", (quiet([os.path.join(work, "docs")], folder=kept)[0],
                                          os.path.exists(os.path.join(kept, "report" + SUFFIX)), os.path.exists(beside)),
               (0, True, False))
        expect("and checked there", quiet([os.path.join(work, "docs")], check=True, folder=kept)[0], 0)
        # a report beside no document: failed by a check of its directory and removed by a run of it; left
        # alone by a run that was given only a file, and wherever reports are kept apart; and only a report
        folder_of = os.path.join(work, "docs")
        orphan, other_run, data = os.path.join(folder_of, "gone" + SUFFIX), os.path.join(kept, "another" + SUFFIX), os.path.join(folder_of, "data.json")
        named = os.path.join(folder_of, "notes.markdown")  # a document of another suffix, with its report
        for path in (orphan, other_run, data, named, named + SUFFIX):
            pin._write(path, "{}\n")
        quiet([folder_of])  # the documents' reports beside them, so that only the stray one is at fault
        pin._write(orphan, "{}\n")  # (that run removed it: it is put back for the check)
        code, out = quiet([folder_of], check=True)
        expect("a stray report fails the check", (code, "gone.pointers.json: a report with no document" in out), (1, True))
        quiet([doc])
        expect("a run on one file removes no other report", os.path.exists(orphan), True)
        quiet([folder_of])
        expect("a run on the directory removes it, and nothing else",
               (os.path.exists(orphan), os.path.exists(beside), os.path.exists(data), os.path.exists(named + SUFFIX)),
               (False, True, True, True))
        expect("where reports are kept apart, another run's report is left and does not fail the check",
               (quiet([folder_of], folder=kept)[0], quiet([folder_of], check=True, folder=kept)[0], os.path.exists(other_run)),
               (0, 0, True))
        for path in (beside, data, named, named + SUFFIX):
            if os.path.exists(path):
                os.remove(path)
        try:
            quiet([doc, doc])
            failed.append("one document given twice was accepted")
        except SystemExit:
            pass

        # the same gate against a second tree: what is gone, what changed, what only moved
        second = os.path.join(work, "second")
        for path, body in PROBE_TREE.items():
            pin._write(os.path.join(second, *path.split("/")), body)
        moved = PROBE_A.replace("LIMIT = 1\n", "LIMIT = 2\n").replace("import os\n", "import os\nimport sys\n")
        moved = moved.replace('else:\n    def where():\n        return "there"\n', "")
        pin._write(os.path.join(second, "pkg", "a.py"), moved.replace("class Meta:\n        flag = True", "pass"))
        pin._write(os.path.join(second, "pkg", "__init__.py"), "from pkg.b import *\n")
        there = pin._scratch(second)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = compare(book, [doc], {"subject": second})
        lines = out.getvalue().splitlines()
        # LIMIT has another value, A lost its nested class and `where` one of its two bindings; the
        # re-export is gone; A.size, A.one and B are the same bytes, the first two a line further down;
        # the pointer into the library is not in the tree that was swapped, and is not counted
        expect("against a second tree", (code, lines[-1]),
               (1, f"pointers against subject at {there[:12]}: 1 gone, 3 changed, 3 the same"))
        expect("what is gone and what changed", sorted((l.split(": ")[1], l.split("`")[1]) for l in lines[:-1]),
               [("changed", "pkg/a.py:A"), ("changed", "pkg/a.py:LIMIT"), ("changed", "pkg/a.py:where"),
                ("gone", "pkg/__init__.py:A")])
        with contextlib.redirect_stdout(io.StringIO()):
            expect("against the same tree", compare(book, [doc], {"subject": where}), 0)
        # a pointer into a tree that was not swapped is not compared, whether or not it resolves
        aside = pin_doc(work, made, "`lib:lib/nope.py` and `pkg/a.py:LIMIT`")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            compare(book, [aside], {"subject": second})
        expect("a broken pointer into another tree is not gone", out.getvalue().splitlines()[-1].split(": ", 1)[1],
               "0 gone, 1 changed, 0 the same")
        for arguments in (["--root", book, "--tree", "subject", doc], ["--root", book, "--tree", f"subject={second}", "--check", doc],
                          ["--root", book, "--tree", f"subject={second}", "--report", kept, doc]):
            try:
                main(arguments)
                failed.append(f"accepted: {' '.join(arguments[2:5])}")
            except SystemExit:
                pass
        try:
            World(book, {"nothing": second})
            failed.append("a tree pin.json does not name was swapped")
        except SystemExit:
            pass
        # a tree that is not at its pin is refused
        with open(os.path.join(where, "pkg", "b.py"), "a", encoding="utf-8", newline="\n") as f:
            f.write("# edited\n")
        try:
            World(book).tree("subject")
            failed.append("a tree that is not at the pin was read")
        except SystemExit:
            pass
    finally:
        pin.remove(work)
    if failed:
        print("PROBE FAILED:\n  " + "\n  ".join(failed))
        return 1
    print("probe ok: a pointer resolves to a file, a directory, and what a module, a class and a function "
          "bind (tuples, annotated and augmented names, aliases, definitions under every kind of block, in "
          "the order of the source; slots; what methods assign on self, and in __new__ on the instance, and "
          "not on a class being made), with its lines from the first decorator; a name bound twice is every "
          "binding; an inherited member, one a base declares and the class only assigns, a function's "
          "variable, a name only `import *` brings in, a pattern, a commit, a path that is not the commit's, "
          "a symbol on a file that is not Python and a file that does not parse are each refused, and the "
          "refusal says what is there; a deleted name and an import for type checking are marked; an import "
          "is followed only when asked, through relative imports, aliases, packages and `import *`; a span "
          "with a slash is a pointer and a malformed one is refused, and quoted text is not one; fences, "
          "quotations and backticks are read as the head says; the head must name the pinned commit before "
          "the first pointer; the report holds each pointer's line, sentence, lines and fingerprint, is "
          "written only for a document that passes, a stale or tampered one fails the check, and only a "
          "report beside no document is removed; against a second tree a pointer into it is gone, changed, "
          "or the same though it moved; a tree that is not at its pin is refused")
    return 0


def pin_doc(work: str, commit: str | None, body: str) -> str:
    path = os.path.join(work, "docs", "other.md")
    pin._write(path, (f"At {commit}.\n\n" if commit else "") + body + "\n")
    return path


def main(argv: list[str]) -> int:
    args = list(argv)
    options = {"--root": None, "--report": None}
    swap = {}
    for flag in list(options) + ["--tree"]:
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
                options[flag] = args[at + 1]
            del args[at:at + 2]
    pin.require_python(pinned=False)
    if "--probe" in args:
        return probe()
    pin.require_python(options["--root"])
    flags = {a for a in args if a.startswith("--")}
    docs = [a for a in args if not a.startswith("--")]
    if flags - {"--check", "--spans"} or not docs:
        raise SystemExit(__doc__)
    if "--spans" in flags:
        return show_spans(options["--root"], docs)
    if swap:
        if flags or options["--report"]:
            raise SystemExit("--tree compares and writes nothing: it goes with neither --check nor --report")
        return compare(options["--root"], docs, swap)
    return run(options["--root"], docs, "--check" in flags, options["--report"])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
