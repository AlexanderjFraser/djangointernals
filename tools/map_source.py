#!/usr/bin/env python3
"""The map of the source: what the pinned tree holds, how large each part of it is, what
defines what and what imports what -- as data, and as tables a person can read.

    python tools/map_source.py            (re)write everything under map/generated/
    python tools/map_source.py --check    fail unless map/generated/ is what would be written now
    python tools/map_source.py --probe    prove the map counts, resolves and orders as it says

Each takes `--root DIR`, the book's root (default: $BOOK_ROOT, else the directory above this
file). map/generated/ is this tool's alone: nothing in it is edited by hand, and a file there
that the tool does not write fails the check and is removed by the next run.

It reads pin.json (which tree, at which commit; tools/pin.py), map/map.json (what to map and
how to count) and every assignment map.json names. It refuses a tree that is not at the pin.

map/map.json:

    {
      "tree": "django",                 optional: a tree of pin.json; the subject by default
      "source": ["django"],             the packages mapped in full, as paths from the tree's root
      "locale_dir": "locale",           a directory of this name holds locale data, not source
      "tokens": {
        "bytes_per_token": 2.5,         the estimate's ratio; say beside it how it was measured
        "strata": [{"paths": ["django/db"], "bytes_per_token": 2.3}]
      },                                optional: sets of files, in the grammar below, each with
                                        the ratio measured on it; a file is in at most one
      "standard_library": ["tomllib"],  optional: see `third_party` below
      "assignments": ["slices.json"]    each a file beside map.json
    }

An assignment gives every file to one part, in the grammar below:

    {
      "name": "slices",                 names the outputs: generated/slices.json, slices.md, slices/
                                        (a plain name, like the ids and slugs, and none of the map's own)
      "unit": "slice",                  what one part is called in the tables
      "complete": ["django"],           every file under these must be in a part, or in "out"
      "parts": [{"id": "1", "slug": "request", "title": "...", "paths": [...],
                 "skim": {"paths": [...], "why": "..."}}],     optional: files read at the map's level only
      "out": [{"paths": [...], "reason": "..."}]               optional: out of the book, and why
    }

    "a/b"        the directory a/b and everything under it, or the one file a/b
    "a/b/."      only the files directly in a/b
    "a/b*.txt"   a pattern: `*` matches any run of characters, slashes included
    "-a/b"       not these; any of the forms above may be subtracted

Entries are read in order and the last one that matches a file decides. A file claimed by two
parts, a file under "complete" that nothing claims, an entry that matches no file (of the
tree; or, for a skim entry, of its part) each fail the run: the coverage is derived here and
nowhere counted by hand.

How things are counted:

- A file of the tree is a file the pinned commit holds (`git ls-files`), never what a
  directory walk finds.
- kind: under a source package, `python` (a .py outside locale directories), `locale`
  (anything under a directory named by "locale_dir") or `other`; elsewhere, `beside`.
- bytes: the file's size. The tree is checked out as the commit's own bytes (tools/pin.py
  refuses one that is not), so this is the repository's number on every machine; a symbolic
  link is the small file git stores for it.
- lines: newline characters, plus one if the last line has none. Not counted for a binary
  file (a NUL in its first 8,192 bytes).
- tokens: an estimate, bytes / bytes_per_token, rounded; zero for a binary file. It is the
  only number here that is not exact, and every table heads it with a tilde.
- classes and functions: those defined at module level, including under a module-level if,
  try, with, for, while or match. `line` is the line of `class` or `def`, not of a decorator.
  A class carries the number of method definitions in its own body (a nested class's are
  not counted) and the names of the classes nested in it. Functions nested in functions are
  not listed.
- imports: import statements, resolved to files of the tree. `import a.b` names the module
  a.b; `from a import b` names a/b when that is a module and a otherwise; relative imports
  are resolved from the importing file. A statement is `imports` when it runs as the module
  is imported (module level, a class body, a module-level block) and `deferred` when it does
  not: in a function body, under `if TYPE_CHECKING:`, or under `if __name__ == "__main__":`,
  written just so (another spelling of such a guard is taken to run).
  For a file, a statement counts once for each file it names; between packages or parts,
  once for each package or part it names.
- `third_party`: a module is the standard library's if the running Python lists it as its
  own or map.json names it under "standard_library" (a module a newer Python added and the
  tree imports is named there, so that every Python writes the same map). A pinned library
  is recognised by the top-level name it is imported by (pin.json).
- reading order: within a part, a file comes after the files of the part it imports as it is
  imported. Files that import each other in a cycle are one group; inside a group of sixteen
  files or fewer the order is the one with the fewest imports that point forward, from a
  file to one listed after it (the first such order by path), and inside a larger group a
  depth-first walk from its first file by path.

A pattern in a path entry is a shell pattern (`*`, `?`, `[...]`) in which `*` also matches
slashes. A Python file that does not parse fails the run and is named.

What the map does not see: an import made by a call (`import_module`, `import_string`, a
dotted path in a setting); that importing a submodule also runs its packages' `__init__`;
names bound by assignment at module level; anything inside a file that is not Python.

Vendored: the copy in a book's repository is written by a command and is not edited there.
"""
from __future__ import annotations

import ast
import contextlib
import fnmatch
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pin  # noqa: E402  (the one place the tree and its commit are written)

MAP_DIR, CONFIG, GENERATED = "map", "map.json", "generated"
PLAIN = re.compile("[A-Za-z0-9][A-Za-z0-9._-]*")  # a name that can be a file's
TOOL = "tools/map_source.py"
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPES = DEFS + (ast.Lambda,)

SHAPE = """\
## The shape of the data

Every JSON file opens with `"generated"`: the tool, the tree and the commit it was made from.
Paths are from the tree's root, with forward slashes.

**`files.json`**

- `files`: one record for every file under a source package that is not locale data.
  - every record: `path`, `kind` (`python` or `other`), `bytes`, `lines` (null for a binary
    file), `tokens` (the estimate).
  - a `python` record adds:
    - `classes`: `name`, `line` (of `class`, not of a decorator), `end`, `bases` (as
      written), `methods` (how many method definitions in its own body), `nested` (names of
      nested classes); `conditional: true` when the class is defined under a module-level
      block.
    - `functions`: `name`, `line`, `end`; `async: true`; `conditional: true`.
    - `imports`: `{path: statements}`, the files of the tree it imports as it is imported.
    - `deferred`: `{path: statements}`, the files it imports otherwise: inside a function
      body, or under a guard that is false when the module is imported.
    - `libraries`: `{tree: statements}`, imports from the library trees `pin.json` names.
    - `third_party`: top-level names it imports that are neither the tree, a pinned library
      nor the standard library.
    - `unresolved`: imports that name the tree, or reach above it, and name no file of it
      (absent when there are none; any fails the run).
- `locale`: one record for every locale directory: `path`, `files` by extension, `bytes`,
  and the `python` files in it as `{files, lines, bytes}`.

**`packages.json`**

- `packages`: one record for every directory one and two levels below a source package
  (`(top)` holds the files directly in a directory; where there is more than one source
  package, each name begins with its package's): `package`, `level` (1 or 2), `python` as
  `{files, lines, bytes, tokens, classes, functions}`, `other` and `locale` as `{files,
  bytes}`.
- `imports`: the matrix between the first-level packages, as `{importer: {imported:
  {"imports": n, "deferred": n}}}`, in statements.
- `beside`: the tree outside the source packages, by directory at the root and one level
  down: `{files, lines, bytes, tokens}` over its text files, `binary` files counted apart,
  and on a directory at the root `mostly`: the extension that holds most of its bytes, with
  the same totals.

**`<assignment>.json`** (for example `slices.json`)

- `unit`, and `parts`: for each part, `id`, `slug`, `title`, `paths` (as written),
  `python`, `other`, `locale`, `beside` (the same totals as above), `skim` (the paths read
  at the map's level, why, and their totals) when the part has one, `order` (the reading
  order: a list of groups, each a list of paths; a group of more than one path is a cycle),
  and `crosses`: `{other part: {"out": n, "out_deferred": n, "in": n, "in_deferred": n}}`
  in import statements.
- `owner`: `{path: part id}` for every file the assignment gives to a part.
- `out`: `{path: reason}` for every file it puts out of the book.
"""


# ----------------------------------------------------------------------------
# reading the tree

def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def blocks(node: ast.AST):
    """The statement lists of a compound statement that is not a scope: if, try, with, for,
    while, match. Call it on nothing that is a class or a function."""
    for field in ("body", "orelse", "finalbody"):
        part = getattr(node, field, None)
        if isinstance(part, list):
            yield part
    for handler in getattr(node, "handlers", ()):
        yield handler.body
    for case in getattr(node, "cases", ()):
        yield case.body


def definitions(body: list, conditional: bool = False):
    """(node, conditional) for each class and function a body defines, looking inside its
    blocks and never inside a scope."""
    for node in body:
        if isinstance(node, (ast.ClassDef,) + DEFS):
            yield node, conditional
        else:
            for block in blocks(node):
                yield from definitions(block, True)


def never_at_import(test: ast.AST) -> bool:
    """Is this the test of an `if` whose body does not run as the module is imported:
    `TYPE_CHECKING`, bare or as an attribute, or `__name__ == "__main__"`?"""
    if isinstance(test, (ast.Name, ast.Attribute)):
        return (test.id if isinstance(test, ast.Name) else test.attr) == "TYPE_CHECKING"
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"
            and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
            and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__")


def import_statements(tree: ast.AST):
    """(statement, deferred) for every import in the module: deferred when it sits in a
    function body, at any depth, or under a guard that is false as the module is imported."""
    stack = [(tree, False)]
    while stack:
        node, deferred = stack.pop()
        guarded = node.body if isinstance(node, ast.If) and never_at_import(node.test) else ()
        for child in ast.iter_child_nodes(node):
            later = deferred or any(child is statement for statement in guarded)
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                yield child, later
            else:
                stack.append((child, later or isinstance(child, SCOPES)))


def named(node: ast.AST, module: str, is_package: bool, modules: dict, tops: set) -> set:
    """What one import statement names, as ("tree", path), ("outside", top-level name) or
    ("unresolved", dotted name)."""
    found = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] not in tops:
                found.add(("outside", alias.name.split(".")[0]))
            elif alias.name in modules:
                found.add(("tree", modules[alias.name]))
            else:
                found.add(("unresolved", alias.name))
        return found
    if node.level:
        package = module.split(".") if is_package else module.split(".")[:-1]
        if node.level > len(package):  # above the top-level package: an ImportError when it runs
            return {("unresolved", "." * node.level + (node.module or ""))}
        base = package[:len(package) - (node.level - 1)] + (node.module.split(".") if node.module else [])
    else:
        base = node.module.split(".")
    if base[0] not in tops:
        return {("outside", base[0])}
    base_name = ".".join(base)
    for alias in node.names:
        sub = f"{base_name}.{alias.name}"
        if alias.name != "*" and sub in modules:
            found.add(("tree", modules[sub]))
        elif base_name in modules:
            found.add(("tree", modules[base_name]))
        else:
            found.add(("unresolved", sub))
    return found


class Source:
    """The pinned tree as the map sees it: every file measured, the Python under the source
    packages parsed."""

    def __init__(self, book: str | None = None):
        self.book = pin.root(book)
        pinned = pin.load(book)
        self.cfg = read_json(os.path.join(self.book, MAP_DIR, CONFIG))
        self.name = self.cfg.get("tree") or pinned["subject"]
        self.tree = pin.tree(self.name, book)
        self.commit = pinned["trees"][self.name]["commit"]
        self.where = pinned["trees"][self.name]["path"]
        why = pin.problems(pinned["trees"][self.name], self.tree)
        if why:
            raise SystemExit(f"{self.name} is not at the pin ({'; '.join(why)}): `python tools/pin.py fetch`")
        self.libraries = {imported: name for name, entry in pinned["trees"].items() if name != self.name
                          for imported in entry.get("imports", [name])}  # the name imported -> its tree
        self.stdlib = set(sys.stdlib_module_names) | set(self.cfg.get("standard_library", ())) | {"__main__"}
        self.roots = list(self.cfg["source"])
        names = [r.rsplit("/", 1)[-1] for r in self.roots]
        if len(set(names)) != len(names):  # they are imported by that name, and it must mean one of them
            raise SystemExit(f"{CONFIG}: two source packages share a name: {', '.join(self.roots)}")
        self.files = {}    # path -> record, for every file the commit holds
        self.modules = {}  # dotted module name -> path, for every .py under a source package
        self.statements = {}  # path -> [(deferred, the files of the tree one import statement names)]
        self.default_ratio = float(self.cfg["tokens"]["bytes_per_token"])
        if not self.default_ratio > 0:
            raise SystemExit(f"{CONFIG}: tokens.bytes_per_token must be more than nothing")
        self.ratio = {}    # path -> a measured ratio that overrides the default
        self._measure()
        self._parse()

    def root_of(self, path: str) -> str | None:
        return next((r for r in self.roots if path.startswith(r + "/")), None)

    def kind(self, path: str) -> str:
        if self.root_of(path) is None:
            return "beside"
        if self.cfg["locale_dir"] in path.split("/")[:-1]:
            return "locale"
        return "python" if path.endswith(".py") else "other"

    def read(self, path: str) -> bytes:
        full = os.path.join(self.tree, *path.split("/"))
        if not os.path.isfile(full):
            return b""
        with open(full, "rb") as f:
            return f.read()

    def _measure(self) -> None:
        for path in pin.files(self.tree):
            data = self.read(path)
            binary = b"\0" in data[:8192]
            lines = None if binary else data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
            self.files[path] = {"path": path, "kind": self.kind(path), "bytes": len(data), "lines": lines}

    def module_of(self, path: str) -> tuple[str, bool]:
        """django/apps/config.py -> ("django.apps.config", False); an __init__.py is its package."""
        root = self.root_of(path)
        above = root.rsplit("/", 1)[0] + "/" if "/" in root else ""
        parts = path[len(above):-3].split("/")
        is_package = parts[-1] == "__init__"
        if is_package:
            parts.pop()
        return ".".join(parts), is_package

    def _parse(self) -> None:
        tops = {r.rsplit("/", 1)[-1] for r in self.roots}
        for path, rec in self.files.items():
            if rec["kind"] in ("python", "locale") and path.endswith(".py"):
                self.modules[self.module_of(path)[0]] = path
        for path, rec in self.files.items():
            if rec["kind"] != "python":
                continue
            self.statements[path] = []
            try:
                tree = ast.parse(self.read(path), filename=path)
            except (SyntaxError, MemoryError, RecursionError) as error:  # the last two: too deep to parse
                why = f"line {error.lineno}: {error.msg}" if isinstance(error, SyntaxError) else str(error)
                rec.update(classes=[], functions=[], imports={}, deferred={}, libraries={}, third_party=[],
                           unparsed=why or type(error).__name__)
                continue
            module, is_package = self.module_of(path)
            classes, functions = [], []
            for node, conditional in definitions(tree.body):
                if isinstance(node, ast.ClassDef):
                    inner = [n for n, _c in definitions(node.body)]
                    item = {"name": node.name, "line": node.lineno, "end": node.end_lineno,
                            "bases": [ast.unparse(b) for b in node.bases],
                            "methods": sum(isinstance(n, DEFS) for n in inner),
                            "nested": [n.name for n in inner if isinstance(n, ast.ClassDef)]}
                    classes.append(item)
                else:
                    item = {"name": node.name, "line": node.lineno, "end": node.end_lineno}
                    if isinstance(node, ast.AsyncFunctionDef):
                        item["async"] = True
                    functions.append(item)
                if conditional:
                    item["conditional"] = True
            imports, deferred, libraries = Counter(), Counter(), Counter()
            third_party, unresolved = set(), set()
            for node, later in import_statements(tree):
                found = named(node, module, is_package, self.modules, tops)
                inside = frozenset(what for where, what in found if where == "tree")
                if inside:
                    self.statements[path].append((later, inside))
                for where, what in found:
                    if where == "tree":
                        (deferred if later else imports)[what] += 1
                    elif where == "unresolved":
                        unresolved.add(what)
                    elif what in self.libraries:
                        libraries[self.libraries[what]] += 1
                    elif what not in self.stdlib:
                        third_party.add(what)
            rec.update(classes=classes, functions=functions, imports=dict(sorted(imports.items())),
                       deferred=dict(sorted(deferred.items())), libraries=dict(sorted(libraries.items())),
                       third_party=sorted(third_party))
            if unresolved:
                rec["unresolved"] = sorted(unresolved)

    def tokens(self, rec: dict) -> int:
        if rec["lines"] is None:
            return 0
        return round(rec["bytes"] / self.ratio.get(rec["path"], self.default_ratio))

    def of_kind(self, kind: str) -> list[dict]:
        return [r for r in self.files.values() if r["kind"] == kind]


# ----------------------------------------------------------------------------
# assignments

def claims(path: str, spec: list[str]) -> bool:
    """Does the spec claim the file? The last entry that matches decides."""
    hit = False
    for entry in spec:
        if matches(path, entry.removeprefix("-")):
            hit = not entry.startswith("-")
    return hit


def matches(path: str, entry: str) -> bool:
    if entry == "." or entry.endswith("/."):
        return path.rpartition("/")[0] == entry[:-2].rstrip("/")
    if any(c in entry for c in "*?["):
        return fnmatch.fnmatchcase(path, entry)
    return path == entry or path.startswith(entry + "/")


class Assignment:
    """One division of the tree's files into parts, checked: each file in at most one part,
    every file under "complete" in a part or out with a reason, no entry that matches nothing."""

    def __init__(self, source: Source, filename: str):
        self.file = filename
        self.data = read_json(os.path.join(source.book, MAP_DIR, filename))
        self.name, self.unit, self.parts = self.data["name"], self.data.get("unit", "part"), self.data["parts"]
        self.owner, self.out, self.problems = {}, {}, []
        outs = self.data.get("out", [])
        for path in source.files:
            mine = [p["id"] for p in self.parts if claims(path, p["paths"])]
            gone = [o["reason"] for o in outs if claims(path, o["paths"])]
            if len(mine) + len(gone) > 1:
                self.problems.append(f"{path} is claimed more than once: {', '.join(mine + ['out'] * len(gone))}")
            elif mine:
                self.owner[path] = mine[0]
            elif gone:
                self.out[path] = gone[0]
            elif any(path.startswith(r + "/") for r in self.data.get("complete", ())):
                self.problems.append(f"{path} is in no {self.unit} and not out")
        specs = [(f"{self.unit} {p['id']}", p["paths"]) for p in self.parts]
        specs += [("out", o["paths"]) for o in outs] + [('"complete"', self.data.get("complete", []))]
        for label, spec in specs:
            for entry in spec:
                if not any(matches(path, entry.removeprefix("-")) for path in source.files):
                    self.problems.append(f"{label}: {entry!r} matches no file")
        for part in self.parts:  # a skim entry is about the part's own files
            mine = [path for path, owner in self.owner.items() if owner == part["id"]]
            for entry in part.get("skim", {}).get("paths", []):
                if not any(matches(path, entry.removeprefix("-")) for path in mine):
                    self.problems.append(f"{self.unit} {part['id']}: the skim entry {entry!r} matches no file "
                                         f"of the {self.unit}")
        ids = [str(p["id"]).casefold() for p in self.parts]  # they name files, where case may not count
        if len(set(ids)) != len(ids):
            self.problems.append("two parts share an id")
        # the name, the ids and the slugs become file names beside the map's own
        if self.name.casefold() in ("readme", "files", "packages"):
            self.problems.append(f"an assignment named {self.name!r} would be written over a file of the map's own")
        for word in [self.name] + [str(p[key]) for p in self.parts for key in ("id", "slug")]:
            if not PLAIN.fullmatch(word):
                self.problems.append(f"{word!r} is not a plain name: letters, digits, dots, hyphens, underscores")

    def files_of(self, source: Source, part: dict, kind: str | None = None) -> list[dict]:
        return [source.files[p] for p, o in self.owner.items()
                if o == part["id"] and kind in (None, source.files[p]["kind"])]

    def skimmed(self, part: dict, path: str) -> bool:
        return "skim" in part and claims(path, part["skim"]["paths"])


def set_ratios(source: Source) -> list[str]:
    """Give each file the ratio measured on the stratum that claims it, and say what is wrong
    with the strata. They are sets of files in their own right, not the parts of an
    assignment: a ratio stays on the files it was measured on when the parts are redrawn."""
    strata = source.cfg["tokens"].get("strata", [])
    problems = []
    for path in source.files:
        mine = [s for s in strata if claims(path, s["paths"])]
        if len(mine) > 1:
            problems.append(f"{CONFIG}: {path} is in two strata")
        elif mine and float(mine[0]["bytes_per_token"]) > 0:
            source.ratio[path] = float(mine[0]["bytes_per_token"])
    for stratum in strata:
        if not float(stratum["bytes_per_token"]) > 0:
            problems.append(f"{CONFIG}: a stratum's bytes_per_token must be more than nothing")
        for entry in stratum["paths"]:
            if not any(matches(path, entry.removeprefix("-")) for path in source.files):
                problems.append(f"{CONFIG}: a stratum's entry {entry!r} matches no file")
        if not any(claims(path, stratum["paths"]) for path in source.files):
            problems.append(f"{CONFIG}: a stratum claims no file")
    return problems


# ----------------------------------------------------------------------------
# the reading order

def reading_order(paths: list[str], imports: dict) -> list[list[str]]:
    """Groups of files, each after the groups it imports. A group of more than one file is a
    cycle. `imports[p]` is what p imports as it is imported; only edges inside `paths` count.

    Tarjan's strongly connected components: a component is finished only after every
    component it can reach, so the order of finishing is already imported-first."""
    inside = set(paths)
    graph = {p: sorted(q for q in imports.get(p, ()) if q in inside and q != p) for p in sorted(inside)}
    index, low, on_stack, stack, groups = {}, {}, set(), [], []
    for start in graph:
        if start in index:
            continue
        index[start] = low[start] = len(index)
        stack.append(start)
        on_stack.add(start)
        work = [(start, iter(graph[start]))]
        while work:
            node, edges = work[-1]
            for nxt in edges:
                if nxt not in index:
                    index[nxt] = low[nxt] = len(index)
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(graph[nxt])))
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        top = stack.pop()
                        on_stack.discard(top)
                        group.append(top)
                        if top == node:
                            break
                    groups.append(within_cycle(group, graph))
    return groups


EXACT = 16  # the largest cycle ordered exactly: the search is over every subset of its files


def within_cycle(group: list[str], graph: dict) -> list[str]:
    """A cycle's files in the order with the fewest imports that point forward, from a file to
    one listed after it, and among such orders the first by path. A cycle cannot have none;
    this is the least it can have. Beyond EXACT files the search is too large, and the order
    is a depth-first walk instead."""
    members = sorted(group)
    count = len(members)
    if count == 1:
        return members
    if count > EXACT:
        return depth_first(members, graph)
    at = {path: i for i, path in enumerate(members)}
    importers = [0] * count  # importers[v]: the members that import v, as a set of bits
    for path in members:
        for imported in graph[path]:
            if imported in at:
                importers[at[imported]] |= 1 << at[path]
    everything = (1 << count) - 1
    # least[placed]: the fewest forward imports still to come once the set `placed` is in order.
    # Putting v next costs one for each member already placed that imports it.
    least = [0] * (1 << count)
    for placed in range(everything - 1, -1, -1):
        least[placed] = min((importers[v] & placed).bit_count() + least[placed | 1 << v]
                            for v in range(count) if not placed >> v & 1)
    order, placed = [], 0
    while placed != everything:
        v = next(v for v in range(count) if not placed >> v & 1
                 and (importers[v] & placed).bit_count() + least[placed | 1 << v] == least[placed])
        order.append(members[v])
        placed |= 1 << v
    return order


def depth_first(members: list[str], graph: dict) -> list[str]:
    """The files in a depth-first walk from the first by path, each listed after what it
    imports, except across the edges that close a cycle."""
    inside, seen, out = set(members), set(), []
    for start in members:
        if start in seen:
            continue
        seen.add(start)
        work = [(start, iter(graph[start]))]
        while work:
            node, edges = work[-1]
            for nxt in edges:
                if nxt in inside and nxt not in seen:
                    seen.add(nxt)
                    work.append((nxt, iter(graph[nxt])))
                    break
            else:
                work.pop()
                out.append(node)
    return out


# ----------------------------------------------------------------------------
# totals

def total(source: Source, records: list[dict]) -> dict:
    """{files, lines, bytes, tokens} over text files; binary files are counted apart."""
    text = [r for r in records if r["lines"] is not None]
    out = {"files": len(text), "lines": sum(r["lines"] for r in text), "bytes": sum(r["bytes"] for r in text),
           "tokens": sum(source.tokens(r) for r in text)}
    if len(text) != len(records):
        out["binary"] = len(records) - len(text)
    return out


def python_total(source: Source, records: list[dict]) -> dict:
    out = total(source, records)
    out["classes"] = sum(len(r["classes"]) for r in records)
    out["functions"] = sum(len(r["functions"]) for r in records)
    return out


def plain_total(records: list[dict]) -> dict:
    return {"files": len(records), "bytes": sum(r["bytes"] for r in records)}


def package_of(source: Source, path: str, depth: int) -> str:
    """The directory `depth` levels below the file's source package, or (top) for a file
    that sits higher: django/db/models/query.py -> db (1), db/models (2). Where there is
    more than one source package the name begins with the package's, so that two packages'
    directories of one name stay two."""
    root = source.root_of(path)
    below = path[len(root) + 1:].split("/")[:-1]
    name = "/".join(below[:depth] if len(below) >= depth else below + ["(top)"])
    return f"{root}/{name}" if len(source.roots) > 1 else name


def package_rows(source: Source) -> list[dict]:
    groups, levels = defaultdict(list), {}
    for rec in source.files.values():
        if rec["kind"] == "beside":
            continue
        for depth in (1, 2):
            key = package_of(source, rec["path"], depth)
            if depth == 2 and key == package_of(source, rec["path"], 1):
                continue  # a file directly under the source package: one row, not two
            groups[key].append(rec)
            levels[key] = depth
    rows = []
    for key in sorted(groups, key=lambda k: (k.split("/")[0] == "(top)", k.replace("(top)", ""))):
        recs = groups[key]
        rows.append({"package": key, "level": levels[key],
                     "python": python_total(source, [r for r in recs if r["kind"] == "python"]),
                     "other": plain_total([r for r in recs if r["kind"] == "other"]),
                     "locale": plain_total([r for r in recs if r["kind"] == "locale"])})
    return rows


def import_matrix(source: Source, key) -> dict:
    """{importer: {imported: {"imports": n, "deferred": n}}} with files grouped by key(path)."""
    matrix = defaultdict(lambda: defaultdict(lambda: {"imports": 0, "deferred": 0}))
    for path, statements in source.statements.items():
        for later, targets in statements:
            for b in {key(t) for t in targets}:
                matrix[key(path)][b]["deferred" if later else "imports"] += 1
    return {a: dict(sorted(row.items())) for a, row in sorted(matrix.items())}


def beside_rows(source: Source) -> dict:
    """The tree outside the source packages: a row for each directory at the root, with the
    extension that holds most of its text, and a row for each directory one level down."""
    groups = defaultdict(list)
    for rec in source.of_kind("beside"):
        parts = rec["path"].split("/")
        groups[parts[0] if len(parts) > 1 else "(top)"].append(rec)
        if len(parts) > 2:
            groups["/".join(parts[:2])].append(rec)
    rows = {}
    for key, recs in sorted(groups.items()):
        rows[key] = total(source, recs)
        if "/" not in key:
            by_ext = defaultdict(list)
            for rec in recs:
                if rec["lines"] is not None:
                    by_ext[os.path.splitext(rec["path"])[1] or "(none)"].append(rec)
            if by_ext:
                ext = max(by_ext, key=lambda e: (sum(r["bytes"] for r in by_ext[e]), e))
                rows[key]["mostly"] = {"extension": ext, **total(source, by_ext[ext])}
    return rows


def locale_rows(source: Source) -> list[dict]:
    groups = defaultdict(list)
    name = source.cfg["locale_dir"]
    for rec in source.of_kind("locale"):
        parts = rec["path"].split("/")
        groups["/".join(parts[:parts.index(name) + 1])].append(rec)
    rows = []
    for key, recs in sorted(groups.items()):
        py = [r for r in recs if r["path"].endswith(".py")]
        rows.append({"path": key,
                     "files": dict(sorted(Counter(os.path.splitext(r["path"])[1] or "(none)" for r in recs).items())),
                     "bytes": sum(r["bytes"] for r in recs),
                     "python": {"files": len(py), "lines": sum(r["lines"] or 0 for r in py),
                                "bytes": sum(r["bytes"] for r in py)}})
    return rows


def part_data(source: Source, assignment: Assignment, part: dict) -> dict:
    python = assignment.files_of(source, part, "python")
    out = {"id": part["id"], "slug": part["slug"], "title": part["title"], "paths": part["paths"],
           "python": python_total(source, python),
           "other": plain_total(assignment.files_of(source, part, "other")),
           "locale": plain_total(assignment.files_of(source, part, "locale")),
           "beside": total(source, assignment.files_of(source, part, "beside"))}
    if "skim" in part:
        skim = [r for r in python if assignment.skimmed(part, r["path"])]
        out["skim"] = {"paths": part["skim"]["paths"], "why": part["skim"]["why"],
                       "python": python_total(source, skim)}
    out["order"] = reading_order([r["path"] for r in python], {r["path"]: r["imports"] for r in python})
    crosses = defaultdict(lambda: {"out": 0, "out_deferred": 0, "in": 0, "in_deferred": 0})
    for path, statements in source.statements.items():
        mine = assignment.owner.get(path)
        for later, targets in statements:
            suffix = "_deferred" if later else ""
            for theirs in {assignment.owner.get(t) for t in targets}:
                if mine == part["id"] and theirs not in (None, mine):
                    crosses[theirs]["out" + suffix] += 1
                if theirs == part["id"] and mine not in (None, theirs):
                    crosses[mine]["in" + suffix] += 1
    out["crosses"] = dict(sorted(crosses.items()))
    return out


# ----------------------------------------------------------------------------
# writing: JSON

def dump(header: dict, body: dict, one_per_line: tuple = ()) -> str:
    """JSON with one record to a line for the long lists, so that a re-pin's diff reads."""
    out = ['{', ' "generated": ' + json.dumps(header, ensure_ascii=False) + ","]
    items = list(body.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if key in one_per_line and value:
            if isinstance(value, dict):
                rows = [f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
                        for k, v in value.items()]
                out.append(f' {json.dumps(key)}: {{\n' + ",\n".join(rows) + "\n }" + comma)
            else:
                rows = ["  " + json.dumps(v, ensure_ascii=False) for v in value]
                out.append(f' {json.dumps(key)}: [\n' + ",\n".join(rows) + "\n ]" + comma)
        else:
            out.append(f' {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}' + comma)
    out.append("}")
    return "\n".join(out) + "\n"


def header(source: Source, tool: str = TOOL) -> dict:
    return {"by": tool, "tree": source.name, "commit": source.commit}


def files_json(source: Source) -> str:
    records = []
    for rec in source.files.values():
        if rec["kind"] in ("python", "other"):
            item = {k: rec[k] for k in ("path", "kind", "bytes", "lines")}
            item["tokens"] = source.tokens(rec)
            item.update({k: v for k, v in rec.items() if k not in item})
            records.append(item)
    return dump(header(source), {"files": records, "locale": locale_rows(source)}, ("files", "locale"))


def top_package(source: Source):
    return lambda path: package_of(source, path, 1).replace("/(top)", "")


def packages_json(source: Source) -> str:
    return dump(header(source), {"packages": package_rows(source),
                                 "imports": import_matrix(source, top_package(source)),
                                 "beside": beside_rows(source)}, ("packages", "imports", "beside"))


def assignment_json(source: Source, assignment: Assignment, parts: list[dict]) -> str:
    return dump(header(source), {"unit": assignment.unit, "parts": parts, "owner": assignment.owner,
                                 "out": assignment.out}, ("parts", "owner", "out"))


# ----------------------------------------------------------------------------
# writing: markdown

def fmt(n: int) -> str:
    return f"{n:,}"


def table(head: list[str], rows: list[list], right: tuple = ()) -> str:
    """A markdown table; `right` holds the indexes of the columns that are numbers."""
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join("---:" if i in right else "---" for i in range(len(head))) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out) + "\n"


def banner(source: Source, tool: str = TOOL, tilde: bool = True) -> str:
    text = (f"*Generated by `{tool}` from `{source.name}` at `{source.commit}`, the tree under "
            f"`{source.where}/`. Not edited by hand: the tool rewrites it.")
    if tilde:
        text += (" A number under a tilde is an estimate of tokens, at the ratio `map/map.json` gives and "
                 "explains; every other number is counted.")
    return text + "*\n"


def spec_text(spec: list[str]) -> str:
    """A part's paths as a sentence: the additions, then the subtractions after one "minus"."""
    def cell(entry: str) -> str:
        if entry == "." or entry.endswith("/."):
            return f"`{entry[:-2].rstrip('/') or '(the root)'}` (the files directly in it)"
        return f"`{entry}`"
    add = [cell(e) for e in spec if not e.startswith("-")]
    sub = [cell(e[1:]) for e in spec if e.startswith("-")]
    text = ", ".join(add)
    if sub:
        text += ", minus " + (" and ".join([", ".join(sub[:-1]), sub[-1]]) if len(sub) > 1 else sub[0])
    return text


def defines(rec: dict) -> str:
    """The classes, then after a dot the functions."""
    classes = " ".join(f"`{c['name']}`" for c in rec["classes"])
    functions = " ".join(f"`{f['name']}`" for f in rec["functions"])
    return f"{classes} · {functions}".strip() if functions else classes


def packages_md(source: Source) -> str:
    out = [f"# The source by package\n\n{banner(source)}"]
    rows = []
    for root in source.roots:
        mine = [r for r in source.files.values() if source.root_of(r["path"]) == root]
        py = total(source, [r for r in mine if r["kind"] == "python"])
        rows.append([f"`{root}/`, Python outside locale directories", fmt(py["files"]), fmt(py["lines"]),
                     fmt(py["bytes"]), fmt(py["tokens"])])
        for kind, label in (("other", "other files"), ("locale", "locale data")):
            some = [r for r in mine if r["kind"] == kind]
            rows.append([f"`{root}/`, {label}", fmt(len(some)), "", fmt(sum(r["bytes"] for r in some)), ""])
    beside = beside_rows(source)
    for key, t in beside.items():
        if "/" not in key:
            label = f"`{key}/`" if key != "(top)" else "files at the root"
            if t.get("binary"):
                label += f" (and {t['binary']} binary files)"
            m = t.get("mostly")
            rows.append([label, fmt(t["files"]), fmt(t["lines"]), fmt(t["bytes"]), fmt(t["tokens"]),
                         f"`{m['extension']}`: {fmt(m['files'])} files, {fmt(m['lines'])} lines" if m else ""])
    for row in rows:
        row += [""] * (6 - len(row))
    out.append("## The whole tree\n\nText files; *mostly* is the extension that holds most of a directory's "
               "bytes.\n\n" + table(["where", "files", "lines", "bytes", "~tokens", "mostly"], rows, (1, 2, 3, 4)))
    rows, packages = [], package_rows(source)
    second = [row["package"] for row in packages if row["level"] == 2]
    below = Counter(name.rsplit("/", 1)[0] for name in second)
    for row in packages:
        py, name = row["python"], row["package"]
        if name in second and name.endswith("/(top)") and below[name.rsplit("/", 1)[0]] == 1:
            continue  # a package with no directories in it: its (top) row would repeat its own
        label = f"&nbsp;&nbsp;&nbsp;`{name}`" if name in second else f"`{name}`"
        numbers = [fmt(py[k]) for k in ("files", "lines", "bytes", "tokens", "classes", "functions")]
        rows.append([label] + (numbers if py["files"] else [""] * 6)
                    + [fmt(row[k]["files"]) if row[k]["files"] else "" for k in ("other", "locale")])
    out.append("## The source packages\n\nPython files outside locale directories, with the classes and "
               "functions they define at module level. `(top)` is the files directly in a directory. A "
               "package's row includes the rows indented under it.\n\n"
               + table(["package", "files", "lines", "bytes", "~tokens", "classes", "functions",
                        "other files", "locale files"], rows, tuple(range(1, 9))))
    matrix = import_matrix(source, top_package(source))
    names = sorted(set(matrix) | {b for row in matrix.values() for b in row})
    rows = [[f"`{a}`"] + [(matrix.get(a, {}).get(b, {}).get("imports", 0)
                           + matrix.get(a, {}).get(b, {}).get("deferred", 0)) or "" for b in names]
            for a in names]
    out.append("## Imports between the packages\n\nImport statements: the package in the row imports from "
               "the package in the column. A statement counts once for each package it names. "
               "Statements inside function bodies are included; `packages.json` counts them apart.\n\n"
               + table(["imports →"] + [f"`{n}`" for n in names], rows, tuple(range(1, len(names) + 1))))
    biggest = sorted(source.of_kind("python"), key=lambda r: (-r["bytes"], r["path"]))[:25]
    out.append("## The largest files\n\n" + table(
        ["file", "lines", "bytes", "~tokens"],
        [[f"`{r['path']}`", fmt(r["lines"]), fmt(r["bytes"]), fmt(source.tokens(r))] for r in biggest],
        (1, 2, 3)))
    deep = Counter(key.split("/")[0] for key in beside if "/" in key)
    rows = [[f"`{key}/`", fmt(t["files"]), fmt(t["lines"]), fmt(t["bytes"]), fmt(t["tokens"])]
            for key, t in beside.items() if "/" in key and deep[key.split("/")[0]] <= 30]
    out.append("## Beside the source\n\nThe text files of the directories outside the source packages, "
               "one level down. A directory with more than thirty directories in it is not broken down "
               "here; `packages.json` has them all.\n\n"
               + table(["directory", "files", "lines", "bytes", "~tokens"], rows, (1, 2, 3, 4)))
    return "\n".join(out)


def assignment_md(source: Source, assignment: Assignment, parts: list[dict]) -> str:
    unit = assignment.unit
    out = [f"# The {unit}s\n\n{banner(source)}"]
    if assignment.data.get("about"):
        out.append(assignment.data["about"] + "\n")
    skims = any("skim" in p for p in parts)
    rows = []
    for p in parts:
        py = p["python"]
        row = [p["id"], f"[{p['title']}]({assignment.name}/{p['id']}-{p['slug']}.md)", spec_text(p["paths"]),
               fmt(py["files"]), fmt(py["lines"]), fmt(py["bytes"]), fmt(py["tokens"])]
        if skims:
            row.append(fmt(py["tokens"] - p["skim"]["python"]["tokens"]) if "skim" in p else "")
        row += [p["other"]["files"] or "", p["locale"]["files"] or "",
                f"{fmt(p['beside']['files'])} ({fmt(p['beside']['bytes'])} bytes, ~{fmt(p['beside']['tokens'])} tokens)"
                if p["beside"]["files"] else ""]
        rows.append(row)
    head = ["#", unit, "what is in it", "Python files", "lines", "bytes", "~tokens"]
    head += ["~tokens read whole"] if skims else []
    head += ["other files", "locale files", "files beside the source"]
    out.append(table(head, rows, tuple(range(3, len(head) - 1))))
    out.append("Python files are those outside locale directories; the other files and the locale data of "
               f"the same directories belong to the {unit} and are listed on its page.\n")
    ids = [p["id"] for p in parts if p["python"]["files"]]
    by_id = {p["id"]: p for p in parts}
    rows = [[a] + [(by_id[a]["crosses"].get(b, {}).get("out", 0)
                    + by_id[a]["crosses"].get(b, {}).get("out_deferred", 0)) or "" for b in ids] for a in ids]
    out.append(f"## Imports between the {unit}s\n\nImport statements: the {unit} in the row imports from the "
               f"{unit} in the column, statements inside function bodies included.\n\n"
               + table(["imports →"] + ids, rows, tuple(range(1, len(ids) + 1))))
    if assignment.out:
        reasons = defaultdict(list)
        for path, reason in assignment.out.items():
            reasons[reason].append(path)
        out.append("## Out of the book\n\n" + table(
            ["reason", "files"], [[r, " ".join(f"`{p}`" for p in ps)] for r, ps in reasons.items()]))
    return "\n".join(out)


def ab(now: int, later: int) -> str:
    """Two counts as a+b: at import time, and only inside a function."""
    return f"{now}+{later}" if later else str(now)


def ranges(numbers: list[int]) -> str:
    """1, 2, 3, 7, 9, 10 as 1–3, 7, 9–10."""
    out, start, last = [], None, None
    for n in sorted(numbers) + [None]:
        if start is None:
            start = n
        elif n != last + 1:
            out.append(str(start) if start == last else f"{start}–{last}")
            start = n
        last = n
    return ", ".join(out)


def part_md(source: Source, assignment: Assignment, part: dict, data: dict) -> str:
    unit, py, name = assignment.unit, data["python"], assignment.name
    others = {p["id"]: p for p in assignment.parts}
    out = [f"# {unit.capitalize()} {part['id']} · {part['title']}\n\n{banner(source)}",
           f"**What is in it.** {spec_text(part['paths'])}. The other {unit}s are in [the table of {unit}s]"
           f"(../{name}.md).\n"]
    rows = [["Python files, outside locale directories", fmt(py["files"]), fmt(py["lines"]), fmt(py["bytes"]),
             fmt(py["tokens"])]]
    if "skim" in data:
        sk = data["skim"]["python"]
        rows.append([f"of which read at the map's level: {spec_text(data['skim']['paths'])}", fmt(sk["files"]),
                     fmt(sk["lines"]), fmt(sk["bytes"]), fmt(sk["tokens"])])
        rows.append(["which leaves, read whole", fmt(py["files"] - sk["files"]), fmt(py["lines"] - sk["lines"]),
                     fmt(py["bytes"] - sk["bytes"]), fmt(py["tokens"] - sk["tokens"])])
    rows.append(["other files", fmt(data["other"]["files"]), "", fmt(data["other"]["bytes"]), ""])
    rows.append(["locale data", fmt(data["locale"]["files"]), "", fmt(data["locale"]["bytes"]), ""])
    b = data["beside"]
    rows.append(["files beside the source", fmt(b["files"]), fmt(b["lines"]), fmt(b["bytes"]), fmt(b["tokens"])])
    out.append(table(["", "files", "lines", "bytes", "~tokens"], [r for r in rows if r[1] != "0"], (1, 2, 3, 4)))
    mine = assignment.files_of(source, part)
    used = sorted({source.ratio.get(r["path"], source.default_ratio) for r in mine if r["lines"] is not None})
    if len(used) == 1:
        out.append(f"Tokens on this page are bytes ÷ {used[0]:g}.\n")
    if "skim" in data:
        out.append(f"Read at the map's level: {data['skim']['why']}\n")

    python = assignment.files_of(source, part, "python")
    if python:
        inside = {r["path"] for r in python}
        place = {path: n for n, path in enumerate((p for group in data["order"] for p in group), 1)}
        folders = defaultdict(list)
        for rec in python:
            folders[rec["path"].rpartition("/")[0]].append(rec)
        out.append("## By directory\n\nThe Python files by directory, with where each directory's files fall in "
                   "the reading order below.\n\n" + table(
                       ["directory", "files", "lines", "~tokens", "places in the order"],
                       [[f"`{d}/`", len(recs), fmt(sum(r["lines"] for r in recs)),
                         fmt(sum(source.tokens(r) for r in recs)), ranges([place[r["path"]] for r in recs])]
                        for d, recs in sorted(folders.items())], (1, 2, 3)))

        cycles = [g for g in data["order"] if len(g) > 1]
        text = ("## The Python files, in reading order\n\n*At import time* means as the module is imported: at "
                "module level, in a class body, or in a module-level `if` or `try`; and not inside a function "
                "or a method, nor under `if TYPE_CHECKING:` or `if __name__ == \"__main__\":`. The table is a "
                f"dependency order: a file comes after every file of this {unit} that it imports at import "
                "time. It is made by taking the files in path order and listing, before each, whatever it "
                "imports that is not yet listed. So a file is read just after what it needs, and the files "
                f"of one directory are not always together. Imports from other {unit}s, and imports that do "
                "not run at import time, do not order anything.\n\n")
        if cycles:
            text += ("Files that import each other in a cycle at import time share a letter under *cycle* and "
                     "are best read as one. No order can put every file of a cycle after what it imports; "
                     + ("a cycle is listed in the order with the fewest imports that point forward, from a "
                        "file to one listed after it.\n\n" if max(map(len, cycles)) <= EXACT else
                        f"a cycle of up to {EXACT} files is listed in the order with the fewest imports that "
                        "point forward, from a file to one listed after it, and a larger one in a "
                        "depth-first walk from its first file by path.\n\n"))
        else:
            text += f"No files of this {unit} import each other in a cycle at import time.\n\n"
        text += (f"*imports* is how many files of this {unit} the file imports, written a+b: a at import time, "
                 "b only otherwise (those are named in the next table; all of them are in "
                 "`files.json`). *defines* lists the classes defined at module level and, after the dot, the "
                 "functions; a name bound by assignment or by import is not listed, so a file of settings or "
                 "of re-exports shows nothing. *~tokens so far* is the running total.\n")
        out.append(text)
        rows, deferred_rows, so_far = [], [], 0
        for number, group in enumerate(data["order"]):
            letter = cycle_label(sum(len(g) > 1 for g in data["order"][:number])) if len(group) > 1 else ""
            for path in group:
                rec = source.files[path]
                so_far += source.tokens(rec)
                now = [t for t in rec["imports"] if t in inside and t != path]
                later = [t for t in rec["deferred"] if t in inside and t not in rec["imports"] and t != path]
                mark = " (map level)" if assignment.skimmed(part, path) else ""
                row = [place[path], f"`{path}`{mark}", fmt(rec["lines"]), fmt(source.tokens(rec)), fmt(so_far)]
                rows.append(row + ([letter] if cycles else []) + [ab(len(now), len(later)), defines(rec)])
                if later:
                    deferred_rows.append([f"`{path}`", " ".join(f"`{t}`" for t in later)])
        head = ["#", "file", "lines", "~tokens", "~tokens so far"] + (["cycle"] if cycles else []) + ["imports", "defines"]
        out.append(table(head, rows, (0, 2, 3, 4)))
        if deferred_rows:
            out.append(f"## Imports that wait\n\nThe files of this {unit} that a file imports only inside a "
                       "function or a method, or under a guard that is false at import time: the imports "
                       "that would otherwise close a cycle, or that are wanted late.\n\n"
                       + table(["file", "imports, not at import time"], deferred_rows))

        rows = []
        for other, c in data["crosses"].items():
            link = f"[{other} · {others[other]['title']}]({other}-{others[other]['slug']}.md)"
            rows.append([link, ab(c["out"], c["out_deferred"]), top_targets(source, assignment, part["id"], other),
                         ab(c["in"], c["in_deferred"]), top_targets(source, assignment, other, part["id"])])
        out.append(f"## Imports across the {unit}'s edge\n\nImport statements between this {unit} and each other "
                   "one, written a+b: a at import time, b otherwise. A statement counts once, however "
                   "many files it names. Beside each count are the files named most, each with the number of "
                   "statements that name it (one statement can name two files, so these can add up to more "
                   "than the count), and how many more files are named.\n\nThe map sees only import "
                   "statements. What crosses an edge through a registry, a signal, a dotted path in a "
                   "setting, or an object handed in and used, is not here: a zero in this table is not "
                   "independence.\n\n"
                   + table([f"other {unit}", f"this {unit} imports from it", "naming most",
                            f"it imports from this {unit}", f"naming most, of this {unit}"], rows))
        libs, third = defaultdict(dict), defaultdict(list)
        for rec in python:
            for lib, n in rec["libraries"].items():
                libs[lib][rec["path"]] = n
            for module in rec["third_party"]:
                third[module].append(rec["path"])
        if libs or third:
            lines = []
            for lib, users in sorted(libs.items()):
                lines.append(f"`{lib}`, a library pinned beside the tree in `pin.json`: {sum(users.values())} "
                             "import statements, in " + " ".join(f"`{p}` ({n})" for p, n in sorted(users.items())) + ".")
            if third:
                lines.append("Modules that are neither the tree, a pinned library nor the standard library: "
                             + "; ".join(f"`{k}` in " + ", ".join(f"`{p}`" for p in ps)
                                         for k, ps in sorted(third.items())) + ".")
            out.append("## Imports from outside the tree\n\n" + "\n\n".join(lines) + "\n")
        unresolved = [(r["path"], u) for r in python for u in r.get("unresolved", ())]
        if unresolved:
            out.append("## Imports that name no file\n\n" + table(["file", "import"],
                                                                 [[f"`{p}`", f"`{u}`"] for p, u in unresolved]))

    other = assignment.files_of(source, part, "other")
    if other:
        groups = defaultdict(list)
        for rec in other:
            groups[rec["path"].rpartition("/")[0]].append(rec)
        rows = [[f"`{d}/`", len(recs), fmt(sum(r["bytes"] for r in recs)),
                 " ".join(f"`{r['path'].rpartition('/')[2]}`" for r in recs)] for d, recs in sorted(groups.items())]
        out.append("## Files that are not Python\n\n" + table(["directory", "files", "bytes", "names"], rows, (1, 2)))
    owned = {p for p, o in assignment.owner.items() if o == part["id"]}
    locale = [row for row in locale_rows(source) if any(p.startswith(row["path"] + "/") for p in owned)]
    if locale:
        rows = [[f"`{row['path']}/`", ", ".join(f"{n} `{ext}`" for ext, n in row["files"].items()),
                 fmt(row["bytes"]), fmt(row["python"]["lines"])] for row in locale]
        out.append("## Locale data\n\nTranslations (`.po`, `.mo`) and each locale's `formats.py` and "
                   "`__init__.py`: data, counted here and not among the Python files above.\n\n"
                   + table(["directory", "files", "bytes", "lines of Python"], rows, (2, 3)))
    beside = assignment.files_of(source, part, "beside")
    if beside:
        rows = [[f"`{r['path']}`", fmt(r["lines"] or 0), fmt(r["bytes"]), fmt(source.tokens(r))]
                for r in sorted(beside, key=lambda r: natural(r["path"]))]
        out.append("## Files beside the source\n\n" + table(["file", "lines", "bytes", "~tokens"], rows, (1, 2, 3)))
    return "\n".join(out)


def cycle_label(n: int) -> str:
    """A, B, ... Z, AA, AB, ..."""
    label = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        label = chr(65 + r) + label
    return label


def natural(path: str) -> list:
    """Sort key that puts 5.2.txt before 5.10.txt, and 5.2.txt before 5.2.1.txt."""
    out, digits = [], ""
    for ch in os.path.splitext(path)[0]:
        if ch.isdigit():
            digits += ch
        else:
            if digits:
                out.append((0, int(digits), ""))
                digits = ""
            out.append((1, 0, ch))
    if digits:
        out.append((0, int(digits), ""))
    return out


def top_targets(source: Source, assignment: Assignment, importer: str, imported: str, n: int = 4) -> str:
    """The files of part `imported` that the files of part `importer` name in most statements,
    and how many more they name."""
    count = Counter()
    for rec in source.of_kind("python"):
        if assignment.owner.get(rec["path"]) == importer:
            for field in ("imports", "deferred"):
                for target, k in rec[field].items():
                    if assignment.owner.get(target) == imported:
                        count[target] += k
    ranked = sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))
    more = f" and {len(ranked) - n} more" if len(ranked) > n else ""
    return " ".join(f"`{p}` ({k})" for p, k in ranked[:n]) + more


def readme(source: Source, assignments: list[Assignment]) -> str:
    out = [f"# The map of the source\n\n{banner(source)}",
           "The map is what the tools know about the pinned tree before anyone reads it: every file with "
           "its size, what each Python file defines and imports, the totals by package, and the "
           f"division of the tree into parts. `python {TOOL}` writes this directory; "
           f"`python {TOOL} --check` fails if it is not what would be written now.\n",
           "| file | what it is |\n|---|---|\n"
           "| `packages.md`, `packages.json` | sizes by package, the imports between packages, the largest files, the tree beside the source |\n"
           "| `files.json` | every file under the source packages, with what it defines and imports; locale data by directory |\n"
           + "".join(f"| `{a.name}.md`, `{a.name}.json`, `{a.name}/` | the {a.unit}s (`map/{a.file}`): the table, "
                     f"and one page for each with its files in reading order |\n" for a in assignments),
           f"**How things are counted** is in the head of `{TOOL}`. In short: a file is a file the "
           "pinned commit holds; bytes and lines are counted from the repository's own bytes; a token "
           f"count is an estimate at {source.default_ratio:g} bytes a token"
           + (", or at the ratio `map/map.json` gives for the set of files it was measured on" if source.ratio else "")
           + "; classes and functions are those defined at module level; an import is an import "
           "statement, resolved to a file of the tree.\n",
           SHAPE]
    return "\n".join(out)


# ----------------------------------------------------------------------------
# the run

def faults(source: Source, assignments: list[Assignment]) -> list[str]:
    """Everything that stops a run: what is wrong with the strata and the assignments, a file
    that does not parse, an import that names no file. It also sets the files' ratios."""
    out = set_ratios(source) + [f"{a.file}: {p}" for a in assignments for p in a.problems]
    names = [a.name.casefold() for a in assignments]  # two of one name would write over each other
    out += [f"{a.file}: another assignment is named {a.name!r} too" for i, a in enumerate(assignments)
            if a.name.casefold() in names[:i]]
    for rec in source.of_kind("python"):
        if "unparsed" in rec:
            out.append(f"{rec['path']} does not parse ({rec['unparsed']})")
        out += [f"{rec['path']}: import of {u} names no file of the tree" for u in rec.get("unresolved", ())]
    return out


def build(book: str | None = None) -> tuple[dict, list[str]]:
    """Everything the map writes, as {path under map/generated: text}, and what is wrong."""
    source = Source(book)
    assignments = [Assignment(source, name) for name in source.cfg.get("assignments", [])]
    problems = faults(source, assignments)
    outputs ={"README.md": readme(source, assignments), "files.json": files_json(source),
               "packages.json": packages_json(source), "packages.md": packages_md(source)}
    for a in assignments:
        parts = [part_data(source, a, p) for p in a.parts]
        outputs[f"{a.name}.json"] = assignment_json(source, a, parts)
        outputs[f"{a.name}.md"] = assignment_md(source, a, parts)
        for part, data in zip(a.parts, parts):
            outputs[f"{a.name}/{part['id']}-{part['slug']}.md"] = part_md(source, a, part, data)
    return outputs, problems


def on_disk(folder: str) -> dict:
    found = {}
    for dp, _dirs, names in os.walk(folder):
        for name in names:
            full = os.path.join(dp, name)
            with open(full, encoding="utf-8", newline="") as f:
                found[os.path.relpath(full, folder).replace(os.sep, "/")] = f.read()
    return found


def settle(folder: str, shown: str, what: str, outputs: dict, check: bool, problems: list[str] = ()) -> int:
    """Make a directory hold exactly the outputs, or with `check` say how it does not. A
    generated directory has one owner: whatever else is in it is deleted, or fails the check."""
    for line in problems:
        print(line)
    disk = on_disk(folder)
    if check:
        stale = sorted(k for k in outputs if disk.get(k) != outputs[k])
        extra = sorted(set(disk) - set(outputs))
        for name in stale:
            print(f"{shown}/{name} is {'missing' if name not in disk else 'not what the tool writes now'}")
        for name in extra:
            print(f"{shown}/{name} is not written by the tool")
        bad = bool(problems or stale or extra)
        print(f"{what}: " + ("FAILED" if bad else f"ok, {len(outputs)} files current"))
        return 1 if bad else 0
    if problems:
        print(f"{what}: not written")
        return 1
    for name in sorted(set(disk) - set(outputs)):
        os.remove(os.path.join(folder, *name.split("/")))
    for name, text in outputs.items():
        full = os.path.join(folder, *name.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(f"{what}: wrote {len(outputs)} files under {shown}/")
    return 0


def run(book: str | None, check: bool) -> int:
    outputs, problems = build(book)
    return settle(os.path.join(pin.root(book), MAP_DIR, GENERATED), f"{MAP_DIR}/{GENERATED}", "the map",
                  outputs, check, problems)


# ----------------------------------------------------------------------------
# the probe

PROBE_TREE = {
    "pkg/__init__.py": "from pkg.a import A\n",
    "pkg/a.py": "import os\nimport lib.thing\nimport yaml\nimport plainlib\nfrom . import b\n\n\nclass A(b.B):\n"
                "    def one(self):\n        from pkg.sub import late\n        return late\n\n"
                "    class Meta:\n        pass\n\n    if True:\n        def two(self):\n            pass\n",
    "pkg/b.py": "from pkg import a\n\ntry:\n    from pkg.sub import deep\nexcept ImportError:\n    deep = None\n\n\n"
                "class B:\n    pass\n\n\nif deep:\n    class Sometimes:\n        pass\n\n\n"
                "async def go():\n    def inner():\n        pass\n",
    "pkg/c.py": "from pkg import NAME\nfrom pkg import a, b\nfrom pkg.sub import *\nfrom nowhere import x\n"
                "import pkg.sub.late\nfrom pkg.sub import deep, late\n",
    "pkg/blocks.py": "import contextlib\n\nfor _ in ():\n    class InFor:\n        pass\nwhile False:\n"
                     "    class InWhile:\n        pass\nwith contextlib.suppress(Exception):\n"
                     "    def in_with():\n        pass\nmatch 1:\n    case 1:\n        class InMatch:\n"
                     "            pass\n\n\n@contextlib.contextmanager\ndef decorated():\n    yield\n\n\n"
                     "class Outer:\n    def own(self):\n        from pkg import c\n\n    class Inner:\n"
                     "        def theirs(self):\n            pass\n",
    "pkg/guarded.py": "from typing import TYPE_CHECKING\nimport typing\n\nif TYPE_CHECKING:\n    from pkg import a\n"
                      "    try:\n        import pkg.blocks\n    except ImportError:\n        pass\n"
                      "else:\n    from pkg import b\nif typing.TYPE_CHECKING:\n    import pkg.c\n"
                      "if __name__ == \"__main__\":\n    from pkg.sub import late\n",
    "pkg/sub/__init__.py": "",
    "pkg/sub/deep.py": "from .. import c\nfrom . import late\nfrom .late import thing\n",
    "pkg/sub/late.py": "thing = 1",
    "pkg/sub/locale.py": "x = 1\n",
    "pkg/locale/xx/formats.py": "A = 1\n",
    "pkg/locale/xx/LC_MESSAGES/pkg.po": "msgid \"\"\n",
    "pkg/templates/page.html": "<p>hello</p>\n",
    "pkg/static/blob.bin": "\0\1\2",
    "docs/notes/1.2.txt": "one\ntwo\n",
    "docs/notes/1.2.1.txt": "a patch\n",
    "docs/notes/1.10.txt": "ten\n",
    "docs/index.txt": "index\n",
    "docs/small.rst": "x\n",
}
PROBE_PARTS = {
    "name": "parts", "unit": "part", "complete": ["pkg"],
    "parts": [
        {"id": "1", "slug": "top", "title": "top", "paths": ["pkg/.", "pkg/locale", "pkg/templates", "pkg/static"]},
        {"id": "2", "slug": "sub", "title": "sub", "paths": ["pkg/sub", "-pkg/sub/locale.py"],
         "skim": {"paths": ["pkg/sub/late.py"], "why": "probe"}},
        {"id": "3", "slug": "docs", "title": "docs", "paths": ["docs/notes/1.*.txt"]},
    ],
    "out": [{"paths": ["pkg/sub/locale.py"], "reason": "probe"}],
}


def probe() -> int:
    import tempfile
    work = tempfile.mkdtemp(prefix="mapprobe-")
    failed = []

    def expect(label: str, got, want) -> None:
        if got != want:
            failed.append(f"{label}: got {got!r}, wanted {want!r}")

    def config(**more) -> None:
        pin._write(os.path.join(book, MAP_DIR, CONFIG), json.dumps(
            {"source": ["pkg"], "locale_dir": "locale", "assignments": ["parts.json"],
             "tokens": {"bytes_per_token": 2.0, "strata": [{"paths": ["pkg/sub"], "bytes_per_token": 4.0}]}, **more}))

    def assignment_file(change=None) -> None:
        data = json.loads(json.dumps(PROBE_PARTS))
        if change:
            change(data)
        pin._write(os.path.join(book, MAP_DIR, "parts.json"), json.dumps(data))

    def statement(text: str) -> ast.AST:
        return ast.parse(text).body[0]

    try:
        book = os.path.join(work, "book")
        where = os.path.join(book, "reference", "subject")
        for path, text in PROBE_TREE.items():
            pin._write(os.path.join(where, *path.split("/")), text)
        made = pin._scratch(where)
        # another tree makes a library: it is known by the names it is said to be imported by,
        # and by its own when none is given
        pin._write(os.path.join(book, pin.PIN_FILE), json.dumps(
            {"subject": "subject", "python": "3.12",
             "trees": {"subject": {"repository": where, "commit": made, "path": "reference/subject"},
                       "a-library": {"repository": where, "commit": made, "path": "reference/a-library",
                                     "imports": ["lib", "yaml"]},
                       "plainlib": {"repository": where, "commit": made, "path": "reference/plainlib"}}}))
        config()
        assignment_file()
        # an untracked file is on disk and is not a file of the tree
        pin._write(os.path.join(where, "pkg", "stray.py"), "import pkg.zzz\n")

        source = Source(book)
        f = source.files
        expect("an untracked file", "pkg/stray.py" in f, False)
        # kinds: a module called locale is source; a directory called locale is locale data
        expect("kinds", [f[p]["kind"] for p in ("pkg/sub/locale.py", "pkg/locale/xx/formats.py",
                                               "pkg/templates/page.html", "docs/index.txt")],
               ["python", "locale", "other", "beside"])
        # counting: no final newline, an empty file, a binary file, bytes
        expect("lines without a final newline", f["pkg/sub/late.py"]["lines"], 1)
        expect("an empty file", (f["pkg/sub/__init__.py"]["lines"], f["pkg/sub/__init__.py"]["bytes"]), (0, 0))
        expect("a binary file", f["pkg/static/blob.bin"]["lines"], None)
        expect("bytes", f["pkg/sub/late.py"]["bytes"], 9)

        # definitions: at module level and under every kind of block, with their lines; a method
        # belongs to the class whose body holds it; a decorator's line is not the definition's
        a, b, blocks_ = f["pkg/a.py"], f["pkg/b.py"], f["pkg/blocks.py"]
        expect("classes of a", [(c["name"], c["methods"], c["nested"], c["bases"]) for c in a["classes"]],
               [("A", 2, ["Meta"], ["b.B"])])
        expect("classes of b", [(c["name"], c.get("conditional", False)) for c in b["classes"]],
               [("B", False), ("Sometimes", True)])
        expect("functions of b", [(x["name"], x.get("async", False), x.get("conditional", False)) for x in b["functions"]],
               [("go", True, False)])
        expect("classes under blocks", [(c["name"], c["line"], c["end"], c.get("conditional", False), c["methods"],
                                         c["nested"]) for c in blocks_["classes"]],
               [("InFor", 4, 5, True, 0, []), ("InWhile", 7, 8, True, 0, []), ("InMatch", 14, 15, True, 0, []),
                ("Outer", 23, 29, False, 1, ["Inner"])])
        expect("functions under blocks", [(x["name"], x["line"], x["end"], x.get("conditional", False))
                                          for x in blocks_["functions"]],
               [("in_with", 10, 11, True), ("decorated", 19, 20, False)])

        # imports: a module against a name of a package; `import a.b`; relative; deferred; under
        # try; star; under a guard that is false at import time; a library by the name it is
        # imported by; a third party; a module map.json calls the standard library's
        expect("imports of a", a["imports"], {"pkg/b.py": 1})
        expect("deferred imports of a", a["deferred"], {"pkg/sub/late.py": 1})
        expect("a library by either of the names it is given, and one by its own",
               (a["libraries"], a["third_party"]), ({"a-library": 2, "plainlib": 1}, []))
        expect("imports of b", b["imports"], {"pkg/a.py": 1, "pkg/sub/deep.py": 1})
        expect("imports of c", f["pkg/c.py"]["imports"],
               {"pkg/__init__.py": 1, "pkg/a.py": 1, "pkg/b.py": 1, "pkg/sub/__init__.py": 1,
                "pkg/sub/deep.py": 1, "pkg/sub/late.py": 2})
        expect("a third party", f["pkg/c.py"]["third_party"], ["nowhere"])
        expect("relative imports", f["pkg/sub/deep.py"]["imports"], {"pkg/c.py": 1, "pkg/sub/late.py": 2})
        # under a guard an import waits at any depth: the one in a `try` there too
        expect("imports under guards", (f["pkg/guarded.py"]["imports"], f["pkg/guarded.py"]["deferred"]),
               ({"pkg/b.py": 1}, {"pkg/a.py": 1, "pkg/blocks.py": 1, "pkg/c.py": 1, "pkg/sub/late.py": 1}))
        # blocks.py imports c inside a method: were that to order the files, c would come first
        expect("a deferred import of a file listed later", (blocks_["imports"], blocks_["deferred"]), ({}, {"pkg/c.py": 1}))
        expect("nothing unresolved", [r["path"] for r in f.values() if r.get("unresolved")], [])
        for text, module, is_package, want in (
                ("from .. import x", "pkg.a", False, {("unresolved", "..")}),
                ("from ..other import y", "pkg.a", False, {("unresolved", "..other")}),
                ("from .. import x", "pkg", True, {("unresolved", "..")}),
                ("from .. import c", "pkg.sub.deep", False, {("tree", "pkg/c.py")}),
                ("import pkg.sub.late", "pkg.c", False, {("tree", "pkg/sub/late.py")}),
                ("import pkg.sub.nothing", "pkg.c", False, {("unresolved", "pkg.sub.nothing")})):
            expect(f"`{text}` in {module}", named(statement(text), module, is_package, source.modules, {"pkg"}), want)
        config(standard_library=["nowhere"])
        expect("a module the configuration calls the standard library's",
               Source(book).files["pkg/c.py"]["third_party"], [])
        # what the configuration may not say: two source packages of one name, since an import
        # could mean either; a ratio of nothing
        for label, more in (("two source packages of one name", {"source": ["pkg", "docs/pkg"]}),
                            ("a ratio of nothing", {"tokens": {"bytes_per_token": 0}})):
            config(**more)
            try:
                Source(book)
                failed.append(f"{label}: mapped")
            except SystemExit:
                pass
        # two source packages, one of them below the tree's root: it keeps its row, at the first level
        config(source=["pkg", "docs/notes"])
        below = Source(book)
        expect("the rows of two source packages, one below the root",
               [(row["package"], row["level"]) for row in package_rows(below)],
               [("docs/notes/(top)", 1), ("pkg/(top)", 1), ("pkg/locale", 1), ("pkg/locale/xx", 2), ("pkg/static", 1),
                ("pkg/static/(top)", 2), ("pkg/sub", 1), ("pkg/sub/(top)", 2), ("pkg/templates", 1),
                ("pkg/templates/(top)", 2)])
        rows_md = packages_md(below).split("## The source packages")[1].split("\n## ")[0]
        expect("and their table: a second-level row indented, a lone (top) row left out",
               [line.split(" | ")[0][2:] for line in rows_md.splitlines() if line.startswith("| ")][1:],
               ["`docs/notes/(top)`", "`pkg/(top)`", "`pkg/locale`", "&nbsp;&nbsp;&nbsp;`pkg/locale/xx`", "`pkg/static`",
                "`pkg/sub`", "`pkg/templates`"])
        config()

        # the grammar, the coverage and the ratios
        parts = Assignment(source, "parts.json")
        expect("a sound assignment", parts.problems, [])
        expect("owners", [parts.owner.get(p) for p in ("pkg/a.py", "pkg/sub/deep.py", "pkg/locale/xx/formats.py",
                                                       "docs/notes/1.10.txt", "docs/index.txt", "pkg/sub/locale.py")],
               ["1", "2", "1", "3", None, None])
        expect("out", parts.out, {"pkg/sub/locale.py": "probe"})
        spec = ["pkg", "-pkg/sub", "pkg/sub/deep.py"]
        expect("the last entry that matches decides",
               [claims(p, spec) for p in ("pkg/a.py", "pkg/sub/late.py", "pkg/sub/deep.py")] + [claims("pkg/a.py", ["-pkg/a.py", "pkg"])],
               [True, False, True, True])
        expect("sound strata", set_ratios(source), [])
        # 137 bytes at the default 2, 60 bytes at the stratum's 4, a binary file; and 6 bytes at 4,
        # which rounds up, in a file the parts put out: a stratum is a set of files of its own
        expect("tokens at the default and at a stratum's ratio",
               [source.tokens(f[p]) for p in ("pkg/c.py", "pkg/sub/deep.py", "pkg/static/blob.bin", "pkg/sub/locale.py")],
               [68, 15, 0, 2])
        source.cfg["tokens"]["strata"] += [{"paths": ["pkg/sub/deep.py", "pkg/nothing"], "bytes_per_token": 9}]
        expect("a file in two strata, and an entry that matches nothing", set_ratios(source),
               ["map.json: pkg/sub/deep.py is in two strata", "map.json: a stratum's entry 'pkg/nothing' matches no file"])
        source.cfg["tokens"]["strata"].pop()
        source.cfg["tokens"]["strata"] += [{"paths": ["pkg/c.py"], "bytes_per_token": 0},
                                           {"paths": ["-pkg/a.py"], "bytes_per_token": 3}]
        expect("a stratum with a ratio of nothing, and one that claims no file", set_ratios(source),
               ["map.json: a stratum's bytes_per_token must be more than nothing", "map.json: a stratum claims no file"])
        expect("its files keep the default ratio", source.tokens(f["pkg/c.py"]), 68)
        del source.cfg["tokens"]["strata"][-2:]

        def claimed_twice(d): d["parts"][1]["paths"].append("pkg/a.py")
        def unclaimed(d): d["parts"][0]["paths"].remove("pkg/templates")
        def typo(d): d["parts"][0]["paths"].append("pkg/template")
        def typo_subtracted(d): d["parts"][1]["paths"].append("-pkg/sub/nothing.py")
        def typo_complete(d): d["complete"] = ["pkgg"]
        def skim_elsewhere(d): d["parts"][0]["skim"] = {"paths": ["pkg/sub/late.py"], "why": "probe"}
        def named_as_the_maps_own(d): d["name"] = "Files"
        def slug_that_climbs(d): d["parts"][0]["slug"] = "../../escaped"
        def ids_alike(d): d["parts"][0]["id"], d["parts"][1]["id"] = "a", "A"
        for label, change, needle in (
                ("an assignment named as a file of the map's own", named_as_the_maps_own, "written over a file of the map's own"),
                ("a slug that climbs out of its directory", slug_that_climbs, "'../../escaped' is not a plain name"),
                ("two ids alike but for their case", ids_alike, "two parts share an id"),
                ("a file in two parts", claimed_twice, "claimed more than once"),
                ("a file in no part", unclaimed, "is in no part"),
                ("an entry that matches nothing", typo, "'pkg/template' matches no file"),
                ("a subtracted entry that matches nothing", typo_subtracted, "'-pkg/sub/nothing.py' matches no file"),
                ("a \"complete\" entry that matches nothing", typo_complete, "\"complete\": 'pkgg' matches no file"),
                ("a skim entry outside its part", skim_elsewhere, "matches no file of the part")):
            assignment_file(change)
            if not any(needle in p for p in Assignment(source, "parts.json").problems):
                failed.append(f"{label} went unreported")
        assignment_file()
        expect("two assignments of one name", faults(source, [parts, parts]),
               ["parts.json: another assignment is named 'parts' too"])

        # the reading order: imported first; a cycle is one group, in the order with the fewest
        # imports that point forward; a deferred import does not order
        one = part_data(source, parts, PROBE_PARTS["parts"][0])
        expect("the order of part 1", one["order"], [["pkg/a.py", "pkg/b.py"], ["pkg/__init__.py"], ["pkg/blocks.py"],
                                                      ["pkg/c.py"], ["pkg/guarded.py"]])
        two = part_data(source, parts, PROBE_PARTS["parts"][1])
        expect("the order of part 2", two["order"], [["pkg/sub/__init__.py"], ["pkg/sub/late.py"], ["pkg/sub/deep.py"]])
        expect("the skim", two["skim"]["python"]["files"], 1)
        # a statement that names two files of another part crosses to it once
        expect("what crosses", (one["crosses"], two["crosses"]),
               ({"2": {"out": 4, "out_deferred": 2, "in": 1, "in_deferred": 0}},
                {"1": {"out": 1, "out_deferred": 0, "in": 4, "in_deferred": 2}}))
        expect("a cycle of three", reading_order(
            ["p", "q", "r", "s"], {"p": ["q"], "q": ["r"], "r": ["p", "s"], "s": []}), [["s"], ["p", "r", "q"]])
        expect("a cycle with one best order", reading_order(
            ["a", "b", "c"], {"a": ["b"], "b": ["c"], "c": ["a", "b"]}), [["b", "a", "c"]])
        # what is counted is the imports that point forward, not the files that make them: here
        # every order has three, though z first would leave one file ahead, and the first by path is given
        expect("a cycle that every order leaves with three imports forward", reading_order(
            ["a", "b", "c", "z"], {"a": ["z"], "b": ["z"], "c": ["z"], "z": ["a", "b", "c"]}), [["a", "b", "c", "z"]])
        ring = [f"n{i:02}" for i in range(EXACT + 1)]
        expect("a cycle too large to search", reading_order(ring, {p: [ring[(i + 1) % len(ring)]] for i, p in enumerate(ring)}),
               [ring[::-1]])
        expect("files beside the source, in natural order",
               [r["path"] for r in sorted(parts.files_of(source, PROBE_PARTS["parts"][2]), key=lambda r: natural(r["path"]))],
               ["docs/notes/1.2.txt", "docs/notes/1.2.1.txt", "docs/notes/1.10.txt"])

        # the totals: packages one and two levels down; between packages a statement counts
        # once, though it names two files; locale data; the tree beside the source
        rows = {row["package"]: row for row in package_rows(source)}
        expect("the package rows", list(rows), ["locale", "locale/xx", "static", "static/(top)", "sub", "sub/(top)",
                                                "templates", "templates/(top)", "(top)"])
        expect("their Python", (rows["sub"]["python"]["files"], rows["(top)"]["python"]["files"],
                                rows["(top)"]["python"]["classes"], rows["locale"]["locale"]["files"]), (4, 6, 7, 2))
        expect("the matrix", import_matrix(source, top_package(source)),
               {"(top)": {"(top)": {"imports": 6, "deferred": 4}, "sub": {"imports": 4, "deferred": 2}},
                "sub": {"(top)": {"imports": 1, "deferred": 0}, "sub": {"imports": 2, "deferred": 0}}})
        expect("locale data", locale_rows(source),
               [{"path": "pkg/locale", "files": {".po": 1, ".py": 1}, "bytes": 15,
                 "python": {"files": 1, "lines": 1, "bytes": 6}}])
        beside = beside_rows(source)
        expect("beside the source", (list(beside), beside["docs"]["files"], beside["docs"]["mostly"]["extension"]),
               (["docs", "docs/notes"], 5, ".txt"))
        source.roots = ["pkg", "docs"]
        expect("two source packages keep their names",
               [package_of(source, p, 1) for p in ("pkg/sub/deep.py", "docs/notes/1.2.txt", "pkg/a.py")],
               ["pkg/sub", "docs/notes", "pkg/(top)"])
        source.roots = ["pkg"]

        # the run: writes, passes its own check, fails the check on a stale file and a stray
        # file, refuses a tree that is not the pin, and names a file that does not parse and an
        # import that names no file
        def quiet(check: bool) -> int:
            with contextlib.redirect_stdout(io.StringIO()):
                return run(book, check)
        expect("the run", quiet(False), 0)
        expect("the check after the run", quiet(True), 0)
        folder = os.path.join(book, MAP_DIR, GENERATED)
        with open(os.path.join(folder, "packages.md"), "a", encoding="utf-8") as fh:
            fh.write("edited by hand\n")
        expect("the check on an edited file", quiet(True), 1)
        quiet(False)
        pin._write(os.path.join(folder, "parts", "stray.md"), "not the tool's\n")
        expect("the check on a file the tool does not write", quiet(True), 1)
        quiet(False)
        expect("the run removes it", os.path.exists(os.path.join(folder, "parts", "stray.md")), False)
        with open(os.path.join(where, "pkg", "c.py"), "a", encoding="utf-8", newline="\n") as fh:
            fh.write("import pkg.missing\n")
        try:
            Source(book)
            failed.append("a modified tree was mapped")
        except SystemExit:
            pass
        pin._write(os.path.join(where, "pkg", "broken.py"), "print 'python 2'\n")
        pin._write(os.path.join(where, "pkg", "toodeep.py"), "x = " + "-" * 200000 + "1\n")  # the parser gives up
        os.remove(os.path.join(where, "pkg", "stray.py"))
        made = pin._commit_all(where, "an import that names no file, and two files that do not parse")
        pin.git(where, "checkout", "-q", "--detach", made)
        pinned = read_json(os.path.join(book, pin.PIN_FILE))
        pinned["trees"]["subject"]["commit"] = made
        pin._write(os.path.join(book, pin.PIN_FILE), json.dumps(pinned))
        found = build(book)[1]
        expect("what stops a run", [line.split(" (")[0] for line in found],
               ["pkg/broken.py does not parse", "pkg/c.py: import of pkg.missing names no file of the tree",
                "pkg/toodeep.py does not parse"])
        expect("the run with them", quiet(False), 1)
    finally:
        pin.remove(work)
    if failed:
        print("PROBE FAILED:\n  " + "\n  ".join(failed))
        return 1
    print("probe ok: a file is what the commit holds; kinds, lines, bytes and tokens are counted as the "
          "head says; definitions are found at module level and under every block, with their lines, a "
          "method in its own class; imports resolve to files, relative ones included, a function's and a "
          "guarded one are deferred at any depth, one above the top package is unresolved; a library is "
          "known by the names it is given or by its own, and the standard library can be added to; the "
          "grammar claims, subtracts and matches patterns, the last entry deciding; a file in two parts "
          "or in none, an entry of any kind that matches nothing, a skim entry outside its part, a name "
          "that is not plain or is the map's own, and two assignments of one name are reported; a ratio "
          "rounds, stays on its stratum's files, and is refused when it is nothing; the order puts the "
          "imported first and orders a cycle with the fewest imports pointing forward; packages (two "
          "source packages too, wherever they sit), the matrix, locale data and the tree beside the "
          "source add up; the check fails an edited file and a stray file; a tree off the pin, a file "
          "that does not parse or is too deep to, and an unresolved import stop the run")
    return 0


def main(argv: list[str]) -> int:
    args = list(argv)
    book = None
    if "--root" in args:
        at = args.index("--root")
        book = args[at + 1]
        del args[at:at + 2]
    pin.require_python(pinned=False)
    if "--probe" in args:
        return probe()
    pin.require_python(book)
    if args and args != ["--check"]:
        raise SystemExit(__doc__)
    return run(book, check=bool(args))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
