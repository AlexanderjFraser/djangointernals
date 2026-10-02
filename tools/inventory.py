#!/usr/bin/env python3
"""The inventories: where the source cites a ticket, and where it names each deprecation
warning class -- as data, and as a table for each part of each assignment.

    python tools/inventory.py            (re)write the inventories under map/inventory/
    python tools/inventory.py --check    fail unless they are what would be written now
    python tools/inventory.py --probe    prove each inventory finds what it should and no more

Each takes `--root DIR`, the book's root. It reads what tools/map_source.py reads, refuses to
write where that tool would refuse, and takes from map/map.json:

    "inventories": {
      "tickets": [{"tracker": "django", "pattern": "(?<![&\\w])#([1-9]\\d{3,4})\\b"}, ...],
      "deprecations": "Removed(In|After)\\w+Warning"
    }

`tickets` is a list of regular expressions, each naming the tracker it recognises; group 1 is
the ticket's id. They are tried in order on every comment and every string literal of the
Python under the source packages, locale directories aside, and text one pattern has matched
is not offered to the next. `deprecations` is a regular expression for the names of the
warning classes.

It writes map/inventory/, which is this tool's alone and never edited by hand:

    README.md               the totals
    tickets.json            {"citations": [{path, line, symbol, where, tracker, id, text}]}
    deprecations.json       {"classes": [{name, path, line, bases, aliases}],
                             "sites": [{path, line, symbol, name, class, kind, via, message, code}]}
    <assignment>/<id>-<slug>.md   both inventories for one part's files

How things are found:

- A citation is a pattern's match inside a comment token or a string token (docstrings and
  the literal parts of f-strings included), found by the tokenizer, so `#1234` in code or in
  a file that is not Python is never one. `where` is `comment` or `string`; `text` is the run
  of comment lines, or the paragraph of the string, that holds it, cut to 400 characters
  around the citation. What a pattern takes for a ticket is one: a bare `#1234` is the
  subject's own tracker unless an earlier pattern claims it. A ticket cited twice on one
  line is one citation, where the first is.
- `symbol` is the innermost class or function whose lines hold the place, dotted from module
  level, and empty at module level. A decorated definition begins at its first decorator. A
  comment above a definition belongs to the scope around it; a comment after a body's last
  statement, indented more deeply than the definition, belongs to the definition.
- A deprecation class is a class whose name matches. `Alias = Class` between two matching
  names, at module level (under a module-level `if` or `try` too), is an alias, and a site
  that names the alias carries the class.
- A site is every other place a matching name appears:
    `import`    in an import statement;
    `warn`      passed to a call whose name ends in `warn` or `warn_explicit`;
    `passed`    passed to any other call, `via`: most often a helper of the source's own
                that warns in its turn, or a decorator;
    `instance`  called, to make an instance; `via` is the call the instance is passed to;
    `base`      subclassed;
    `other`     anywhere else in code: returned, assigned, compared;
    `comment`   in a comment, which is how the source marks code to remove;
    `string`    in a string literal: a docstring that says what will change, a name compared.
  A name that appears twice on a line in comments, or twice in strings, is one site there.
  `message` is the call's first argument (or its `message=`) where the file holds it as a
  string: a literal, an f-string, a literal that is formatted, or a name whose every
  binding, in the scope that binds it, is a plain assignment of one (the one written last
  before the call; or, read from a function inside that scope, the only one). For a comment
  or a string it is the comment, or the string's paragraph. `code` is the call as the syntax
  tree writes it back; for a comment, the line of code it stands on, or the next line of
  code when that is not indented less than the comment; otherwise the line. `code` is cut
  to 200 characters.

What the inventories do not see: a message held in another file's constant, in an attribute,
or put together as the code runs; which of two assignments ran, where a name is given a
string twice before a call (the one written last is taken); a name bound in a class body
(a call there is read as the function or the module around it would read it); a ticket
cited in a form no pattern describes (the patterns are written from the tree as it is
pinned and are read again at a re-pin); a ticket cited in a template, a script, a document
or a locale's Python; a warning raised through a variable that holds the class; a name the
source serves by `__getattr__`; when a deprecation ends. A citation's text is 400 characters
and the marks that say it was cut. A file whose expressions nest too deeply for the tool to
read stops the run and is named.

Vendored: the copy in a book's repository is written by a command and is not edited there.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import map_source as ms  # noqa: E402
import pin  # noqa: E402

TOOL = "tools/inventory.py"
OUT = "inventory"  # under map/
SCOPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
STRINGS = {tokenize.STRING} | {getattr(tokenize, name) for name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE")
                               if hasattr(tokenize, name)}
WIDTH = 400  # characters of context kept around a citation
CODE = 200   # characters of code kept for a site
KINDS = {"warn": "passed to a call named `warn` or `warn_explicit`",
         "passed": "passed to another call, most often a helper that warns in its turn",
         "instance": "instantiated", "base": "subclassed", "other": "elsewhere in code",
         "comment": "in comments", "string": "in strings", "import": "imported"}


def is_code(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def spans(tree: ast.Module, lines: list[str]) -> list[tuple[int, int, str, int, int]]:
    """(first line, last line, dotted name, indentation, reach) of every class and function,
    outer before inner. The reach is the last of the blank and comment lines that follow the
    definition's last statement."""
    out = []

    def walk(body: list, prefix: str) -> None:
        for node in body:
            if isinstance(node, SCOPES):
                name = f"{prefix}.{node.name}" if prefix else node.name
                reach = node.end_lineno
                while reach < len(lines) and not is_code(lines[reach]):
                    reach += 1
                first = min([node.lineno] + [d.lineno for d in node.decorator_list])
                out.append((first, node.end_lineno, name, node.col_offset, reach))
                walk(node.body, name)
            else:
                for block in ms.blocks(node):
                    walk(block, prefix)

    walk(tree.body, "")
    return out


def symbol_at(found: list, line: int, column: int | None = None) -> str:
    """The innermost definition that holds the line. A comment says where it starts: one that
    trails a definition's last statement is held by it when it is indented more deeply than
    the definition itself."""
    name = ""
    for first, last, dotted, indentation, reach in found:  # outer before inner: the last match is innermost
        if first <= line <= last or (column is not None and last < line <= reach and column > indentation):
            name = dotted
    return name


def comment_blocks(tokens: list, lines: list[str]) -> dict[int, tuple[str, str]]:
    """{line: (the text of the run of comment-only lines it belongs to, the code it marks)}.
    A run marks the next line of code, unless that is indented less than the run; a comment
    at the end of a line of code stands alone and marks that line."""
    comments = {t.start[0]: t for t in tokens if t.type == tokenize.COMMENT}
    alone = {n for n in comments if not is_code(lines[n - 1])}
    block = {}
    for n in sorted(comments):
        if n in block:
            continue
        run = [n]
        while n in alone and run[-1] + 1 in alone:
            run.append(run[-1] + 1)
        text = " ".join(comments[k].string.lstrip("#").strip() for k in run)
        if n in alone:
            after = next((s for s in lines[run[-1]:] if is_code(s)), "")
            marked = len(after) - len(after.lstrip()) >= comments[n].start[1]
            code = after.strip() if marked else ""
        else:
            code = lines[n - 1][:comments[n].start[1]].strip()
        block.update({k: (text, clip(code)) for k in run})
    return block


def clip(text: str, width: int = CODE) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def around(text: str, needle: str) -> str:
    """The text, cut to WIDTH characters around the needle if it is longer."""
    text = " ".join(text.split())
    if len(text) <= WIDTH:
        return text
    at = max(text.find(needle), 0)
    start = max(0, min(at - WIDTH // 2, len(text) - WIDTH))
    return ("… " if start else "") + text[start:start + WIDTH].strip() + (" …" if start + WIDTH < len(text) else "")


OPENING = re.compile("^[rRbBfFuUtT]{0,3}(\"\"\"|'''|\"|')")
CLOSING = re.compile("(\"\"\"|'''|\"|')$")


def paragraph(raw: str, start: int, end: int, quoted: bool) -> str:
    """The paragraph of a string token that holds raw[start:end]; a whole literal's token
    carries its prefix and quotes, which are not part of what it says."""
    a = raw.rfind("\n\n", 0, start)
    b = raw.find("\n\n", end)
    text = raw[0 if a < 0 else a + 2:len(raw) if b < 0 else b].strip()
    if quoted and a < 0:
        text = OPENING.sub("", text)
    if quoted and b < 0:
        text = CLOSING.sub("", text)
    return text.strip()


def fstring(node: ast.JoinedStr) -> str:
    """An f-string as it reads: its text, and each replacement field in braces."""
    out = []
    for part in node.values:
        if isinstance(part, ast.Constant):
            out.append(str(part.value))
        else:
            conversion = {115: "!s", 114: "!r", 97: "!a"}.get(part.conversion, "")
            spec = ":" + fstring(part.format_spec) if part.format_spec else ""
            out.append("{" + ast.unparse(part.value) + conversion + spec + "}")
    return "".join(out)


def literal(node: ast.AST | None, lookup=None) -> str | None:
    """A string argument as written, when it is one: a literal, an f-string, a literal that
    is formatted (the literal, before its values go in), or (given a lookup) a name bound to
    one of those."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return fstring(node)
    if isinstance(node, ast.Name) and lookup:
        return lookup(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return literal(node.left, lookup)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return literal(node.func.value, lookup)
    return None


def bindings(scope: ast.AST) -> dict[str, list[ast.AST]]:
    """{name: the nodes that bind it} in a module or a function, not looking into the scopes
    inside it: parameters, assignment and loop targets, `except ... as`, imports, definitions."""
    out = defaultdict(list)
    args = getattr(scope, "args", None)
    if isinstance(args, ast.arguments):
        for arg in args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]:
            out[arg.arg].append(arg)
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        if isinstance(node, SCOPES + (ast.Lambda,)):
            if hasattr(node, "name"):
                out[node.name].append(node)
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            out[node.id].append(node)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            out[node.name].append(node)
        elif isinstance(node, ast.alias):
            out[(node.asname or node.name).split(".")[0]].append(node)
        stack.extend(ast.iter_child_nodes(node))
    return out


class Scan:
    """Both inventories over the Python under the source packages."""

    def __init__(self, source: ms.Source):
        cfg = source.cfg.get("inventories", {})
        names = cfg.get("deprecations")
        for pattern in [t["pattern"] for t in cfg.get("tickets", [])] + [names or ""]:
            if any(ord(ch) < 32 for ch in pattern):  # "\b" written with one backslash is a backspace
                raise SystemExit(f"{ms.CONFIG}: the pattern {pattern!r} holds a control character: a backslash "
                                 f"was lost on its way into the file")
        self.trackers = [(t["tracker"], re.compile(t["pattern"])) for t in cfg.get("tickets", [])]
        self.name = re.compile(names) if names else None
        self.word = re.compile(rf"\b(?:{names})\b") if names else None
        self.citations, self.classes, self.sites, self.aliases = [], [], [], {}
        for rec in sorted(source.of_kind("python"), key=lambda r: r["path"]):
            data = source.read(rec["path"])
            if data.strip() and "unparsed" not in rec:
                self.file(rec["path"], data)
        known = {c["name"] for c in self.classes}
        for cls in self.classes:
            cls["aliases"] = sorted(a for a, c in self.aliases.items() if c == cls["name"])
        for site in self.sites:
            site["class"] = self.aliases.get(site["name"], site["name"] if site["name"] in known else None)
        self.citations.sort(key=lambda c: (c["path"], c["line"], c["tracker"], c["id"]))
        self.sites.sort(key=lambda s: (s["path"], s["line"], s["kind"], s["name"]))

    def file(self, path: str, data: bytes) -> None:
        try:
            self.read(path, data)
        except RecursionError:
            raise SystemExit(f"{path}: its expressions nest too deeply for the inventories to read") from None

    def read(self, path: str, data: bytes) -> None:
        tree = ast.parse(data, filename=path)
        tokens = list(tokenize.tokenize(io.BytesIO(data).readline))
        lines = data.decode(tokens[0].string).split("\n")  # the first token is the encoding
        found, blocks = spans(tree, lines), comment_blocks(tokens, lines)
        seen = set()
        for tok in tokens:
            comment = tok.type == tokenize.COMMENT
            if not comment and tok.type not in STRINGS:
                continue
            column = tok.start[1] if comment else None

            def text_at(m: re.Match) -> tuple[int, str]:
                """The line a match is on, and the comment run or the paragraph that holds it."""
                line = tok.start[0] + tok.string.count("\n", 0, m.start())
                return line, blocks[line][0] if comment else paragraph(tok.string, m.start(), m.end(),
                                                                       tok.type == tokenize.STRING)

            taken = []
            for tracker, pattern in self.trackers:
                for m in pattern.finditer(tok.string):
                    if any(a < m.end() and m.start() < b for a, b in taken):
                        continue
                    taken.append(m.span())
                    line, text = text_at(m)
                    ticket = m.group(1).rstrip(".,;:")
                    if (line, tracker, ticket) not in seen:
                        seen.add((line, tracker, ticket))
                        self.citations.append({"path": path, "line": line, "symbol": symbol_at(found, line, column),
                                               "where": "comment" if comment else "string", "tracker": tracker,
                                               "id": ticket, "text": around(text, m.group(0))})
            for m in self.word.finditer(tok.string) if self.word else ():
                line, text = text_at(m)
                kind = "comment" if comment else "string"
                if (line, kind, m.group(0)) not in seen:
                    seen.add((line, kind, m.group(0)))
                    self.sites.append({"path": path, "line": line, "symbol": symbol_at(found, line, column),
                                       "name": m.group(0), "kind": kind, "message": around(text, m.group(0)),
                                       "code": blocks[line][1] if comment else clip(lines[line - 1])})
        if self.name:
            self.deprecations(path, tree, lines, found)

    def deprecations(self, path: str, tree: ast.Module, lines: list[str], found: list) -> None:
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        bound = {}

        def scope_of(node: ast.AST) -> ast.AST:
            """The function a node is in, or the module: where a name it reads is looked up first."""
            while node is not tree:
                node = parents[node]
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    return node
            return tree

        def text_of(name: str, call: ast.Call) -> str | None:
            """The string a name holds where a call reads it, when that is certain: in the scope
            that binds the name, every binding is a plain assignment of a string. Read in that
            scope, it is the last one before the call; read from a function inside, the only one."""
            mine = scope = scope_of(call)
            while True:
                if id(scope) not in bound:
                    bound[id(scope)] = bindings(scope)
                binders = bound[id(scope)].get(name)
                if binders or scope is tree:
                    break
                scope = scope_of(scope)
            texts = []
            for binder in binders or ():
                assign = parents.get(binder)
                text = literal(assign.value) if isinstance(assign, ast.Assign) and len(assign.targets) == 1 else None
                if not isinstance(binder, ast.Name) or text is None:
                    return None
                texts.append((assign.lineno, text))
            texts.sort()
            if scope is mine:
                texts = [(at, text) for at, text in texts if at <= call.lineno][-1:]
            return texts[0][1] if len(texts) == 1 else None

        def at_module_level(node: ast.AST) -> bool:
            while node is not tree:
                node = parents[node]
                if isinstance(node, SCOPES + (ast.Lambda,)):
                    return False
            return True

        def message_of(call: ast.Call) -> str | None:
            first = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "message"), None)
            return literal(first, lambda name: text_of(name, call))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and self.name.fullmatch(node.name):
                self.classes.append({"name": node.name, "path": path, "line": node.lineno,
                                     "bases": [ast.unparse(b) for b in node.bases]})
                continue
            if isinstance(node, ast.alias):
                name = node.name.split(".")[-1]
                if self.name.fullmatch(name):
                    self.site(path, node.lineno, found, lines, name, "import")
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                name = node.id
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                name = node.attr
            else:
                continue
            if not self.name.fullmatch(name):
                continue
            parent = parents[node]
            if (isinstance(parent, ast.Assign) and parent.value is node and at_module_level(parent)
                    and all(isinstance(t, ast.Name) and self.name.fullmatch(t.id) for t in parent.targets)):
                for target in parent.targets:
                    self.aliases[target.id] = name
                continue
            line = node.lineno
            if isinstance(parent, ast.Call) and parent.func is node:  # the class is called: an instance
                outer = parents[parent]
                if isinstance(outer, ast.keyword):
                    outer = parents[outer]
                via = ast.unparse(outer.func) if isinstance(outer, ast.Call) else None
                self.site(path, line, found, lines, name, "instance", via, message_of(parent),
                          ast.unparse(outer if via else parent))
                continue
            call = parent if isinstance(parent, ast.Call) else None
            if isinstance(parent, ast.keyword) and isinstance(parents[parent], ast.Call):
                call = parents[parent]
            if call is not None:
                via = ast.unparse(call.func)
                kind = "warn" if via.split(".")[-1] in ("warn", "warn_explicit") else "passed"
                self.site(path, line, found, lines, name, kind, via, message_of(call), ast.unparse(call))
            else:
                self.site(path, line, found, lines, name, "base" if isinstance(parent, ast.ClassDef) else "other")

    def site(self, path, line, found, lines, name, kind, via=None, message=None, call=None) -> None:
        item = {"path": path, "line": line, "symbol": symbol_at(found, line), "name": name, "kind": kind}
        if via:
            item["via"] = via
        if message:
            item["message"] = " ".join(message.split())
        item["code"] = clip(call or lines[line - 1])  # the whole call, or the line
        self.sites.append(item)


# ----------------------------------------------------------------------------
# writing

def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def as_code(text: str) -> str:
    return "`" + text.replace("`", "'").replace("|", "\\|") + "`"


def says(site: dict) -> str:
    if site["kind"] in ("comment", "string"):
        marked = site["code"] if site["kind"] == "comment" else ""  # a string's line would say it twice
        return cell(site["message"]) + (" → " + as_code(marked) if marked else "")
    if site.get("message"):
        return "“" + cell(site["message"]) + "”"
    return as_code(site["code"])


def how(site: dict) -> str:
    if site["kind"] == "instance":
        return "instance" + (f", to `{site['via']}`" if site.get("via") else "")
    return f"`{site['via']}`" if site.get("via") else site["kind"]


def totals_md(source: ms.Source, scan: Scan, assignments: list) -> str:
    out = [f"# The inventories\n\n{ms.banner(source, TOOL, tilde=False)}",
           "Two lists made by reading the source's own text: every place a comment or a string cites a "
           "ticket in a form `map/map.json` describes, and every place the name of a deprecation warning "
           "class appears. Each is a lead, not a finding: the citation says a reason exists and where to "
           "look for it. The data is `tickets.json` and `deprecations.json`; how each is found, and what "
           f"is not seen, is in the head of `{TOOL}`.\n"]
    by_tracker = defaultdict(list)
    for c in scan.citations:
        by_tracker[c["tracker"]].append(c["id"])
    order = list(dict.fromkeys(t for t, _p in scan.trackers))
    out.append("## Ticket citations\n\n" + ms.table(
        ["tracker", "citations", "tickets cited"],
        [[t, ms.fmt(len(by_tracker[t])), ms.fmt(len(set(by_tracker[t])))] for t in order] +
        [["**all**", ms.fmt(len(scan.citations)), ""]], (1, 2)))
    rows = []
    for cls in scan.classes + [None]:
        count = Counter(s["kind"] for s in scan.sites if s["class"] == (cls and cls["name"]))
        if cls:
            rows.append([f"`{cls['name']}`", f"`{cls['path']}`", " ".join(f"`{b}`" for b in cls["bases"]),
                         " ".join(f"`{a}`" for a in cls["aliases"])] + [count[k] or "" for k in KINDS])
        elif count:
            rows.append(["a matching name that is no class of the tree", "", "", ""] + [count[k] or "" for k in KINDS])
    out.append("## Deprecation warning classes\n\nSites by kind: " + "; ".join(f"`{k}`, {v}" for k, v in KINDS.items())
               + ".\n\n" + ms.table(["class", "defined in", "bases", "aliases"] + list(KINDS), rows,
                                    tuple(range(4, 4 + len(KINDS)))))
    for a in assignments:
        rows = []
        for part in a.parts:
            mine = {p for p, o in a.owner.items() if o == part["id"]}
            cites = sum(1 for c in scan.citations if c["path"] in mine)
            sites = sum(1 for s in scan.sites if s["path"] in mine and s["kind"] != "import")
            if cites or sites:
                rows.append([part["id"], f"[{part['title']}]({a.name}/{part['id']}-{part['slug']}.md)",
                             ms.fmt(cites), ms.fmt(sites)])
        out.append(f"## By {a.unit}\n\n" + ms.table(
            ["#", a.unit, "ticket citations", "deprecation sites, imports aside"], rows, (2, 3)))
    return "\n".join(out)


def part_md(source: ms.Source, scan: Scan, assignment, part: dict) -> str | None:
    mine = {p for p, o in assignment.owner.items() if o == part["id"]}
    cites = [c for c in scan.citations if c["path"] in mine]
    sites = [s for s in scan.sites if s["path"] in mine and s["kind"] != "import"]
    if not cites and not sites:
        return None
    unit, page = assignment.unit, f"{part['id']}-{part['slug']}.md"
    out = [f"# {unit.capitalize()} {part['id']} · {part['title']}: the inventories\n\n"
           f"{ms.banner(source, TOOL, tilde=False)}",
           f"Read from the Python of [this {unit}](../../{ms.GENERATED}/{assignment.name}/{page}), locale "
           "directories aside. What makes a ticket and a warning class is in `map/map.json`; the totals for "
           "the tree, and where the warning classes are defined, are in [the index](../README.md). *in* is "
           "the innermost class or function that holds the line, and is empty at module level.\n"]
    out.append("## Ticket citations\n\nEvery comment and string that cites a ticket in a form `map/map.json` "
               "describes, with the comment or the paragraph that holds it.\n\n" + ms.table(
                   ["file", "line", "in", "ticket", "what it says"],
                   [[f"`{c['path']}`", c["line"], f"`{c['symbol']}`" if c["symbol"] else "",
                     c["id"] if c["tracker"] in ("other", "cve") else f"{c['tracker']} {c['id']}",
                     cell(c["text"])] for c in cites], (1,)) if cites else "## Ticket citations\n\nNone.\n")
    if sites:
        out.append("## Deprecation sites\n\nEvery place the name of a deprecation warning class appears, imports "
                   "aside. One deprecation is usually two or three rows: the comment that marks the code to "
                   "remove, and the call that warns. *how* is the call the class is passed to (a call to "
                   "`warnings.warn`, or to a helper that warns in its turn, or a decorator); or `instance`, "
                   "the class called; or `comment` or `string`, shown as what it says and, for a comment, the "
                   "line of code it stands on or above; or `base`, a class that subclasses it; or `other`, "
                   "shown as the line. Words in quotation marks are the message a call is given, where the "
                   "tool can read it from the same file; a call without them is shown as its code.\n")
        for cls in [c["name"] for c in scan.classes] + [None]:
            some = [s for s in sites if s["class"] == cls]
            if not some:
                continue
            count = Counter(s["kind"] for s in some)
            out.append((f"### `{cls}`\n\n" if cls else "### A name that matches and is no class of the tree\n\n")
                       + f"{len(some)} sites: " + "; ".join(f"{count[k]} {KINDS[k]}" for k in KINDS if count[k])
                       + ".\n\n" + ms.table(
                           ["file", "line", "in", "how", "what it says"],
                           [[f"`{s['path']}`", s["line"], f"`{s['symbol']}`" if s["symbol"] else "", how(s), says(s)]
                            for s in some], (1,)))
    return "\n".join(out)


def build(book: str | None = None) -> tuple[dict, list[str]]:
    source = ms.Source(book)
    assignments = [ms.Assignment(source, name) for name in source.cfg.get("assignments", [])]
    problems = ms.faults(source, assignments)
    scan = Scan(source)
    head = ms.header(source, TOOL)
    outputs = {
        "README.md": totals_md(source, scan, assignments),
        "tickets.json": ms.dump(head, {"citations": scan.citations}, ("citations",)),
        "deprecations.json": ms.dump(head, {"classes": scan.classes, "sites": scan.sites}, ("classes", "sites")),
    }
    for a in assignments:
        for part in a.parts:
            text = part_md(source, scan, a, part)
            if text:
                outputs[f"{a.name}/{part['id']}-{part['slug']}.md"] = text
    return outputs, problems


def run(book: str | None, check: bool) -> int:
    outputs, problems = build(book)
    return ms.settle(os.path.join(pin.root(book), ms.MAP_DIR, OUT), f"{ms.MAP_DIR}/{OUT}",
                     "the inventories", outputs, check, problems)


# ----------------------------------------------------------------------------
# the probe

PROBE_TREE = {
    "pkg/__init__.py": "",
    "pkg/dep.py": "class RemovedInPkg9Warning(DeprecationWarning):\n    pass\n\n\n"
                  "RemovedInNextVersionWarning = RemovedInPkg9Warning\n",
    "pkg/use.py": (
        "import warnings\n"                                                                # 1
        "from pkg import dep\n"
        "from pkg.dep import RemovedInPkg9Warning\n"
        "\n"
        "# See #21874 for the discussion,\n"                                               # 5
        "# and tickets #10335 and #5846.\n"
        "COLOUR = \"&#8217; #333 #1234567 a#5555 #0123\"\n"
        "\n"
        "\n"
        "class K:\n"                                                                       # 10
        "    \"\"\"A class.\n"
        "\n"
        "    Fixed in ticket 21147; see https://bugs.python.org/issue14243 and\n"
        "    https://jira.mariadb.org/browse/MDEV-12981 (MDEV-12981).\n"
        "    \"\"\"\n"                                                                     # 15
        "\n"
        "    # RemovedInPkg9Warning: remove this method.\n"
        "    def old(self):\n"
        "        warnings.warn(\"old() is deprecated.\", RemovedInPkg9Warning, stacklevel=2)\n"
        "        return f\"see #33333 {self}\"  # CVE-2019-14235\n"                        # 20
        "\n"
        "    @decorate(RemovedInPkg9Warning, [\"a\"])\n"
        "    def other(self, *, a=None):\n"
        "        warnings.warn(\"other is \" \"going away\", category=dep.RemovedInNextVersionWarning)\n"
        "        x = 1  # https://example.org/tracker/issues/77.\n"                        # 25
        "\n"
        "\n"
        "CATEGORY = RemovedInPkg9Warning\n"
        "\n"
        "\n"                                                                               # 30
        "class Local(RemovedInPkg9Warning):\n"
        "    pass\n"
        "\n"
        "\n"
        "MSG = \"from a constant: %s\"\n"                                                  # 35
        "\n"
        "\n"
        "def late(note):\n"
        "    warnings.warn(note, RemovedInPkg9Warning)\n"
        "    text = \"from a local\"\n"                                                    # 40
        "    warnings.warn(text, RemovedInPkg9Warning)\n"
        "    warnings.warn(MSG % 1, RemovedInPkg9Warning)\n"
        "\n"
        "\n"
        "def more(x):\n"                                                                   # 45
        "    \"\"\"RemovedInPkg9Warning: the default will change.\n"
        "\n"
        "    See RemovedInPkgXXWarning for the form.\n"
        "    \"\"\"\n"
        "    warnings.warn_explicit(\"explicit\", RemovedInPkg9Warning, \"f.py\", 1)\n"    # 50
        "    warnings.warn(message=\"by keyword\", category=RemovedInPkg9Warning)\n"
        "    warnings.warn(RemovedInPkg9Warning(\"an instance\"), stacklevel=2)\n"
        "    warnings.warn(f\"it's \\\"q\\\" {x}\", RemovedInPkg9Warning)\n"
        "    a = 1  # first\n"
        "    b = 2  # see #45678\n"                                                        # 55
        "    # https://github.com/python/cpython/issues/86533\n"
        "    c = r\"\"\"See #23456 here.\"\"\"\n"
        "    return a\n"
        "    # RemovedInPkg9Warning: after the last statement. See #34567.\n"
        "\n"                                                                               # 60
        "\n"
        "if True:\n"
        "    RemovedLater = None\n"
        "    RemovedInAnotherNameWarning = RemovedInPkg9Warning\n"
        "\n"                                                                               # 65
        "\n"
        "def inside():\n"
        "    RemovedInInnerWarning = RemovedInPkg9Warning\n"
        "    return RemovedInInnerWarning\n"
        "\n"                                                                               # 70
        "\n"
        "# RemovedInPkg9Warning: above the next definition (RemovedInPkg9Warning). See #56789.\n"
        "def last(MSG):\n"
        "    warnings.warn(MSG, RemovedInPkg9Warning)\n"
        "    for COLOUR in (\"a\", \"b\"):\n"                                              # 75
        "        warnings.warn(COLOUR, RemovedInPkg9Warning)\n"
        "    warnings.warn(\"{} is going\".format(1), RemovedInPkg9Warning)\n"
        "    x = \"RemovedInPkg9Warning\"  # RemovedInPkg9Warning: drop x\n"
        "    return x  # RemovedInPkg9Warning\n"
        "\n"                                                                               # 80
        "\n"
        "LATER = \"first\"\n"
        "warnings.warn(LATER, RemovedInPkg9Warning)\n"
        "LATER = \"second\"\n"
        "\n"                                                                               # 85
        "\n"
        "def uncertain():\n"
        "    warnings.warn(LATER, RemovedInPkg9Warning)\n"
        "\n"
        "\n"                                                                               # 90
        "def mixed(flag):\n"
        "    text = \"plain\"\n"
        "    if flag:\n"
        "        text = flag\n"
        "    warnings.warn(text, RemovedInPkg9Warning)\n"),                                # 95
    "pkg/page.html": "<!-- #12345 -->\n",
    "pkg/locale/xx/formats.py": "# see #55555\n",
    "other/far.py": "# #44444\n",
}
PROBE_CONFIG = {
    "source": ["pkg"], "locale_dir": "locale", "tokens": {"bytes_per_token": 3.0}, "assignments": ["parts.json"],
    "inventories": {
        "tickets": [
            {"tracker": "django", "pattern": "(?<![&\\w])#([1-9]\\d{3,4})\\b"},
            {"tracker": "django", "pattern": "\\b[Tt]ickets? ([1-9]\\d{3,4})\\b"},
            {"tracker": "cpython", "pattern": "bugs\\.python\\.org/issue(\\d+)"},
            {"tracker": "cpython", "pattern": "github\\.com/python/cpython/(?:issues|pull)/(\\d+)"},
            {"tracker": "cve", "pattern": "\\b(CVE-\\d{4}-\\d+)\\b"},
            {"tracker": "mariadb", "pattern": "\\b(MDEV-\\d+)\\b"},
            {"tracker": "other", "pattern": "(https?://[^\\s)>\\]\"'`]*(?:/issues/\\d+|[?&]id=\\d+)[^\\s)>\\]\"'`]*)"},
        ],
        "deprecations": "Removed(In|After)\\w+Warning",
    },
}
PROBE_PARTS = {"name": "parts", "unit": "part", "complete": ["pkg"], "parts": [
    {"id": "1", "slug": "use", "title": "use", "paths": ["pkg/use.py", "pkg/page.html", "pkg/__init__.py", "pkg/locale"]},
    {"id": "2", "slug": "dep", "title": "dep", "paths": ["pkg/dep.py"]}]}


def probe() -> int:
    import tempfile
    work = tempfile.mkdtemp(prefix="invprobe-")
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
        pin._write(os.path.join(book, pin.PIN_FILE), json.dumps(
            {"subject": "subject", "python": "3.12",
             "trees": {"subject": {"repository": where, "commit": made, "path": "reference/subject"}}}))
        pin._write(os.path.join(book, ms.MAP_DIR, ms.CONFIG), json.dumps(PROBE_CONFIG))
        pin._write(os.path.join(book, ms.MAP_DIR, "parts.json"), json.dumps(PROBE_PARTS))

        scan = Scan(ms.Source(book))
        me = "RemovedInPkg9Warning"
        # tickets: in comments, docstrings and f-strings; never an entity, a colour, a longer
        # number, a file that is not Python, locale data or a file outside the source; a URL two
        # patterns describe is the first's alone
        expect("the citations", [(c["line"], c["tracker"], c["id"], c["where"], c["symbol"]) for c in scan.citations], [
            (5, "django", "21874", "comment", ""), (6, "django", "10335", "comment", ""),
            (6, "django", "5846", "comment", ""), (13, "cpython", "14243", "string", "K"),
            (13, "django", "21147", "string", "K"), (14, "mariadb", "MDEV-12981", "string", "K"),
            (20, "cve", "CVE-2019-14235", "comment", "K.old"), (20, "django", "33333", "string", "K.old"),
            (25, "other", "https://example.org/tracker/issues/77", "comment", "K.other"),
            (55, "django", "45678", "comment", "more"), (56, "cpython", "86533", "comment", "more"),
            (57, "django", "23456", "string", "more"), (59, "django", "34567", "comment", "more"),
            (72, "django", "56789", "comment", "")])
        texts = {c["id"]: c["text"] for c in scan.citations}
        expect("a run of comment lines is one text", texts["21874"],
               "See #21874 for the discussion, and tickets #10335 and #5846.")
        expect("a string's paragraph", texts["14243"],
               "Fixed in ticket 21147; see https://bugs.python.org/issue14243 and "
               "https://jira.mariadb.org/browse/MDEV-12981 (MDEV-12981).")
        expect("a comment at the end of a line stands alone", texts["45678"], "see #45678")
        expect("a literal without its prefix and quotes", texts["23456"], "See #23456 here.")
        # deprecations: the class, its aliases (at module level, under a block too, never inside
        # a function), and each kind of site with its message
        expect("the classes", [(c["name"], c["path"], c["bases"], c["aliases"]) for c in scan.classes],
               [(me, "pkg/dep.py", ["DeprecationWarning"], ["RemovedInAnotherNameWarning", "RemovedInNextVersionWarning"])])
        expect("the sites", [(s["line"], s["kind"], s["name"], s["class"], s["symbol"], s.get("via"), s.get("message"))
                             for s in scan.sites], [
            (3, "import", me, me, "", None, None),
            (17, "comment", me, me, "K", None, "RemovedInPkg9Warning: remove this method."),
            (19, "warn", me, me, "K.old", "warnings.warn", "old() is deprecated."),
            (22, "passed", me, me, "K.other", "decorate", None),
            (24, "warn", "RemovedInNextVersionWarning", me, "K.other", "warnings.warn", "other is going away"),
            (28, "other", me, me, "", None, None),
            (31, "base", me, me, "Local", None, None),
            # a message held in a name: not before it is bound, then the local, then the module's
            (39, "warn", me, me, "late", "warnings.warn", None),
            (41, "warn", me, me, "late", "warnings.warn", "from a local"),
            (42, "warn", me, me, "late", "warnings.warn", "from a constant: %s"),
            (46, "string", me, me, "more", None, "RemovedInPkg9Warning: the default will change."),
            (48, "string", "RemovedInPkgXXWarning", None, "more", None, "See RemovedInPkgXXWarning for the form."),
            (50, "warn", me, me, "more", "warnings.warn_explicit", "explicit"),
            (51, "warn", me, me, "more", "warnings.warn", "by keyword"),
            (52, "instance", me, me, "more", "warnings.warn", "an instance"),
            (53, "warn", me, me, "more", "warnings.warn", "it's \"q\" {x}"),
            (59, "comment", me, me, "more", None, "RemovedInPkg9Warning: after the last statement. See #34567."),
            (68, "other", me, me, "inside", None, None),
            (69, "other", "RemovedInInnerWarning", None, "inside", None, None),
            # a comment above a definition is the module's; a name twice in it is one site
            (72, "comment", me, me, "", None,
             "RemovedInPkg9Warning: above the next definition (RemovedInPkg9Warning). See #56789."),
            # a parameter (MSG) and a loop variable (COLOUR) hide the module's constant of the same name
            (74, "warn", me, me, "last", "warnings.warn", None),
            (76, "warn", me, me, "last", "warnings.warn", None),
            (77, "warn", me, me, "last", "warnings.warn", "{} is going"),
            # a string and a comment on one line are two sites
            (78, "comment", me, me, "last", None, "RemovedInPkg9Warning: drop x"),
            (78, "string", me, me, "last", None, me),
            (79, "comment", me, me, "last", None, me),
            # at module level a name holds what it was last given before the call; read from a
            # function, a name given two strings holds neither for certain
            (83, "warn", me, me, "", "warnings.warn", "first"),
            (88, "warn", me, me, "uncertain", "warnings.warn", None),
            # every binding must be a string: one that is not leaves the name unread
            (95, "warn", me, me, "mixed", "warnings.warn", None)])
        by = {(s["line"], s["kind"]): s for s in scan.sites}

        def code(line: int, kind: str) -> str | None:
            return by.get((line, kind), {}).get("code")

        def shown(line: int, kind: str) -> str | None:
            return says(by[line, kind]) if (line, kind) in by else None

        expect("what a comment marks, what a call is, and a comment that marks nothing below it",
               [code(17, "comment"), code(22, "passed"), code(59, "comment")],
               ["def old(self):", "decorate(RemovedInPkg9Warning, ['a'])", ""])
        expect("an instance's code is the call it is passed to; a string's is its line; a comment at the "
               "end of a line marks the line",
               [code(52, "instance"), code(78, "string"), code(78, "comment"), code(79, "comment")],
               ["warnings.warn(RemovedInPkg9Warning('an instance'), stacklevel=2)",
                "x = \"RemovedInPkg9Warning\" # RemovedInPkg9Warning: drop x", "x = \"RemovedInPkg9Warning\"", "return x"])
        expect("on a page: a comment with the code it marks, a string as what it says alone, a call as its "
               "message, or as its code when it has none",
               [shown(78, "comment"), shown(78, "string"), shown(19, "warn"), shown(22, "passed")],
               ["RemovedInPkg9Warning: drop x → `x = \"RemovedInPkg9Warning\"`", "RemovedInPkg9Warning",
                "“old() is deprecated.”", "`decorate(RemovedInPkg9Warning, ['a'])`"])
        expect("code is cut and says so", (clip("x" * 300)[-2:], len(clip("x" * 300))), ("x…", CODE))
        cut = around("x " * 300 + "#12345" + " y" * 300, "#12345")
        expect("context is cut around what it is for", (len(cut) <= WIDTH + 4, "#12345" in cut, cut[:2], cut[-2:]),
               (True, True, "… ", " …"))

        # a file whose expressions nest too deeply to read stops the run and is named
        deep = "import warnings\nX = \"a\"" + " % 1" * 3000 + "\nwarnings.warn(X, RemovedInPkg9Warning)\n"
        try:
            scan.file("pkg/deep.py", deep.encode())
            failed.append("a file nested too deeply to read was read")
        except SystemExit as stop:
            expect("the file that stops the run is named", str(stop).split(":")[0], "pkg/deep.py")

        # the run: writes, passes its own check, fails it on an edited file; a part with nothing
        # has no page; nothing is written over an assignment the map refuses
        def quiet(check: bool) -> int:
            with contextlib.redirect_stdout(io.StringIO()):
                return run(book, check)
        expect("the run", quiet(False), 0)
        folder = os.path.join(book, ms.MAP_DIR, OUT)
        expect("the pages", sorted(k for k in ms.on_disk(folder) if "/" in k), ["parts/1-use.md"])
        expect("the check after the run", quiet(True), 0)
        with open(os.path.join(folder, "tickets.json"), "a", encoding="utf-8") as fh:
            fh.write("\n")
        expect("the check on an edited file", quiet(True), 1)
        quiet(False)
        broken = json.loads(json.dumps(PROBE_PARTS))
        broken["parts"][1]["paths"].append("pkg/use.py")
        pin._write(os.path.join(book, ms.MAP_DIR, "parts.json"), json.dumps(broken))
        expect("a run over a broken assignment", quiet(False), 1)
        # a pattern whose backslash was lost: "\b" arrives as a backspace and would match nothing
        lost = json.loads(json.dumps(PROBE_CONFIG))
        lost["inventories"]["tickets"][1]["pattern"] = "\bTicket ([1-9]\\d{3,4})\b"
        pin._write(os.path.join(book, ms.MAP_DIR, ms.CONFIG), json.dumps(lost))
        pin._write(os.path.join(book, ms.MAP_DIR, "parts.json"), json.dumps(PROBE_PARTS))
        try:
            Scan(ms.Source(book))
            failed.append("a pattern holding a backspace was accepted")
        except SystemExit:
            pass
    finally:
        pin.remove(work)
    if failed:
        print("PROBE FAILED:\n  " + "\n  ".join(failed))
        return 1
    print("probe ok: a ticket is found in a comment, a docstring and an f-string, once for each line and "
          "for the first pattern that describes it, and not in an entity, a colour, a longer number, a "
          "file that is not Python, locale data or a file outside the source; a symbol is the innermost "
          "definition, a decorator's line and a trailing comment included; a class, its aliases and the "
          "eight kinds of site are told apart, a string and a comment on one line being two; a message is "
          "read from a literal, an f-string, a formatted literal, a keyword, a local and a module "
          "constant, and not from a parameter, a loop variable, a name given two strings outside the "
          "function or one given something else as well; a comment carries the code it marks and a "
          "string its line; a file nested too deeply to read stops the run; the check fails an edited "
          "file, and nothing is written over a broken assignment")
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
