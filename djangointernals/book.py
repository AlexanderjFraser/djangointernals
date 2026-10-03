"""The corpus as the site sees it: every page's head, the tree of pages, the reading order.

A book is a directory of markdown. `index.md` is its contents page, and
every other page is reached from it: a page whose front matter has
`contents: a, b` is an index, and its children are `a.md` and `b.md` in the
directory named after it (for `index.md`, the book's own directory). A
page's id is its path without `.md`; the index's id is the empty string.

A page begins with its front matter, between two lines of three hyphens: a
strict subset of YAML, one `key: value` to a line.

    django      required: the release and the commit the page was verified against, in the
                page's own words; it must spell out the pinned commit, twelve hex digits or more
    status      required: outline | verified | read
    owns        optional: the names this page is the home of, each in a code span
    contents    optional: the children of an index page, in reading order

A value is plain text, or in double quotes when it begins with anything but
a letter or a digit, or holds a colon and a space, or a space and a `#`:
what a YAML reader would trip on. So `owns` is always quoted.

`load` reads a book whole and refuses it whole: it raises Refused with every
problem found, each as `file:line: what is wrong`, or returns a Book in
which every page is rendered. Beyond what render.py refuses: front matter
that is not as above; a status that is not one of the three; a `django`
line without the pinned commit; a child named in `contents` with no file,
and a markdown file no `contents` names; a written page under an index
that is still in outline; a link to an anchor its target does not have.
And what the two gates refuse (gates.py: tools/pointers.py and
tools/names.py, run on every page, the name gate binding within a section):
a pointer that does not resolve at the pin, a name that does not exist.

What it does not check is what only a reader can: that a page has earned
the status it claims, and that a pointer names the place that does what its
sentence says.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from . import gates as gating
from . import render

STATUSES = {
    "outline": ("Outlined", "Its questions are fixed; it is not yet written."),
    "verified": ("Verified", "Written from claims that were each checked against the source at this commit."),
    "read": ("Read", "Verified, then read together with the pages around it and revised after a reader's read."),
}
KEYS = ("django", "status", "owns", "contents")
ENTRY = re.compile(r"([a-z]+): (.*)")
PLAIN = re.compile(r"[A-Za-z0-9]((?!: | #).)*(?<![:\s])|[A-Za-z0-9]")
NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
RESERVED = {"index", "404"}  # at every depth: Pages serves a/index.html at /a/ and a/404.html for everything missing under /a/
RESERVED_AT_TOP = {"static"}
UNSTYLED = ("<", "url(", "@import", "expression(")  # none of these in a department's figure stylesheet
COMMIT = re.compile(r"(?<![0-9a-f])[0-9a-f]{12,40}(?![0-9a-f])")
SPAN = re.compile(r"`([^`]+)`")


class Refused(Exception):
    """A book that cannot be baked: `problems` says why, one line each."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass(eq=False)
class Page:
    id: str
    source: Path
    where: str  # the file as a message names it
    meta: dict
    body: str
    line: int  # how many lines of the file come before the body
    parent: Page | None = None
    children: list[Page] = field(default_factory=list)

    @property
    def url(self) -> str:
        return "/" + self.id

    @property
    def status(self) -> str:
        return self.meta.get("status", "")

    @property
    def published(self) -> bool:
        """An outlined page is an entry in the contents, never a page."""
        return self.status in ("verified", "read")

    @property
    def status_word(self) -> str:
        return STATUSES[self.status][0]

    @property
    def status_meaning(self) -> str:
        return STATUSES[self.status][1]

    @property
    def level(self) -> int:
        return ("outline", "verified", "read").index(self.status) + 1

    @property
    def ancestors(self) -> list[Page]:
        """From the book's index down to this page's parent."""
        out, page = [], self.parent
        while page is not None:
            out.insert(0, page)
            page = page.parent
        return out

    @property
    def department(self) -> Page | None:
        """The page directly under the book's index that this page is, or is under."""
        chain = self.ancestors + [self]
        return chain[1] if len(chain) > 1 else None

    @property
    def descendants(self) -> list[Page]:
        out = []
        for child in self.children:
            out += [child] + child.descendants
        return out

    @property
    def owns(self) -> list[str]:
        return SPAN.findall(self.meta.get("owns", ""))

    @property
    def tally(self) -> dict | None:
        """For an index: how many of the pages under it are at each status."""
        under = self.descendants
        if not under:
            return None
        count = {status: sum(1 for page in under if page.status == status) for status in STATUSES}
        return {**count, "all": len(under), "written": len(under) - count["outline"]}


@dataclass
class Book:
    root: Path
    pin: dict
    pages: dict[str, Page]
    gates: object = None  # gates.Gates: the trees at the pin, for the renderer's links

    @property
    def index(self) -> Page:
        return self.pages[""]

    @property
    def order(self) -> list[Page]:
        """Every page in reading order: an index, then what is under it."""
        return [self.index] + self.index.descendants

    def neighbours(self, page: Page) -> tuple[Page | None, Page | None]:
        """The written pages before and after this one in reading order."""
        written = [p for p in self.order if p.published]
        at = written.index(page)
        return (written[at - 1] if at else None, written[at + 1] if at + 1 < len(written) else None)


def unquoted(inner: str) -> str | None:
    """What stands between the double quotes of a quoted value, or None if it is not one."""
    out, i = [], 0
    while i < len(inner):
        if inner[i] == "\\":
            if inner[i + 1:i + 2] not in ('"', "\\"):
                return None
            out.append(inner[i + 1])
            i += 2
        elif inner[i] == '"':
            return None
        else:
            out.append(inner[i])
            i += 1
    return "".join(out)


def front_matter(text: str, where: str, problems: list[str]) -> tuple[dict, str, int]:
    """-> (the entries, the body, how many lines come before the body). An entry that was
    refused is still an entry: it is there with an empty value, and not reported as missing."""
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        problems.append(f"{where}:1: a page begins with its front matter, between two lines of three hyphens")
        return {}, text, 0
    end = lines.index("---", 1)
    meta: dict[str, str] = {}
    for number, line in enumerate(lines[1:end], start=2):
        entry = ENTRY.fullmatch(line)
        if not entry:
            problems.append(f"{where}:{number}: front matter is one `key: value` to a line")
            continue
        key, value = entry.groups()
        refused = len(problems)
        if key not in KEYS:
            problems.append(f"{where}:{number}: `{key}` is not a key of a page's front matter ({', '.join(KEYS)})")
        elif key in meta:
            problems.append(f"{where}:{number}: `{key}` is given twice")
        elif value.startswith('"'):
            inner = unquoted(value[1:-1]) if len(value) > 1 and value.endswith('"') else None
            if inner is None:
                problems.append(f"{where}:{number}: `{key}`: a quoted value is in double quotes from end to end, and inside "
                                f'it a double quote is written \\" and a backslash \\\\')
            else:
                meta[key] = inner
        elif not PLAIN.fullmatch(value):
            problems.append(f"{where}:{number}: `{key}`: write this value in double quotes (it is empty, or begins with "
                            f"something other than a letter or a digit, or holds `: ` or ` #`)")
        else:
            meta[key] = value
        if key in KEYS and len(problems) > refused:
            meta.setdefault(key, "")
    return meta, "\n".join(lines[end + 1:]), end + 1


def shown(path: Path) -> str:
    try:
        return path.relative_to(settings.BASE_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def load(root: Path | None = None) -> Book:
    root = Path(root or settings.BOOK_DIR)
    problems: list[str] = []
    pin = json.loads(Path(settings.PIN_FILE).read_text(encoding="utf-8"))
    tree = pin["trees"][pin["subject"]]
    if not (root / "index.md").is_file():
        raise Refused([f"{shown(root)}: there is no index.md here: a book begins at its contents page"])
    try:
        gates = gating.current()
    except gating.Unavailable as why:
        raise Refused([f"{shown(root)}: no pointer can be checked or linked until the pinned trees are on disk "
                       f"(`python tools/pin.py fetch`): {why}"]) from None
    book = Book(root, tree, {}, gates)

    def read(id: str, parent: Page | None) -> Page:
        source = root / f"{id or 'index'}.md"
        where = shown(source)
        text = source.read_bytes().decode("utf-8").replace("\r\n", "\n")
        meta, body, line = front_matter(text, where, problems)
        page = Page(id, source, where, meta, body, line, parent)
        book.pages[id] = page
        for key in ("django", "status"):
            if key not in meta and line:
                problems.append(f"{where}:1: the front matter has no `{key}`")
        if meta.get("status") and meta["status"] not in STATUSES:
            problems.append(f"{where}:1: the status `{meta['status']}` is not one of {', '.join(STATUSES)}")
        if meta.get("status") not in STATUSES:
            meta["status"] = "outline"
        if meta.get("django") and not any(tree["commit"].startswith(run) for run in COMMIT.findall(meta["django"])):
            problems.append(f"{where}:1: `django` does not spell out the pinned commit, twelve hex digits or more: {tree['commit']}")
        if meta.get("owns") and (SPAN.sub("", meta["owns"]).replace(",", "").strip() or not page.owns):
            problems.append(f"{where}:1: `owns` is names, each in a code span, with commas between")
        if parent is not None and page.published and not parent.published:
            problems.append(f"{where}:1: a written page under an index that is still in outline ({parent.where})")
        for name in [n.strip() for n in meta.get("contents", "").split(",") if n.strip()]:
            child = f"{id}/{name}" if id else name
            if not NAME.fullmatch(name) or name in RESERVED or (not id and name in RESERVED_AT_TOP):
                problems.append(f"{where}:1: `contents` names `{name}`: a page's name is lower-case words joined by hyphens, "
                                f"never {' or '.join(sorted(RESERVED))}, and at the top of a book not {', '.join(sorted(RESERVED_AT_TOP))}")
            elif child in book.pages:
                problems.append(f"{where}:1: `contents` names `{name}` twice")
            elif not (root / f"{child}.md").is_file():
                problems.append(f"{where}:1: `contents` names `{name}`, and there is no {shown(root / (child + '.md'))}")
            else:
                page.children.append(read(child, page))
        return page

    read("", None)
    for source in sorted(root.rglob("*.md")):
        id = source.relative_to(root).with_suffix("").as_posix()
        if id != "index" and id not in book.pages:
            problems.append(f"{shown(source)}:1: no page's `contents` names this file")
    home: dict[str, Page] = {}
    for page in book.order:
        for name in page.owns:
            if name in home:
                problems.append(f"{page.where}:1: `owns` names `{name}`, which {home[name].where} is already the home of")
            home.setdefault(name, page)
    for page in book.pages.values():
        render.render(page, book, problems)
    for department in book.index.children:
        stylesheet = root / department.id / "figures" / "figures.css"
        if stylesheet.is_file():
            text = stylesheet.read_bytes().decode("utf-8", "replace")
            held = [token for token in UNSTYLED if token in text]
            if held:
                problems.append(f"{shown(stylesheet)}:1: a department's figure stylesheet is classes and nothing else: it holds "
                                + ", ".join(f"`{token}`" for token in held))
    for page in book.pages.values():
        for where, href, target, fragment in page.fragments:
            if fragment not in target.anchors and not (fragment.startswith("figure-") and fragment[7:] in target.figures):
                problems.append(f"{where}: the link `{href}`: {target.where} has no heading or figure that comes to `#{fragment}`")
    # the two gates, on every page: a pointer that does not resolve, a name that does not exist
    problems += gates.list_problems
    for page in book.order:
        problems += gates.problems(page)
    if not book.index.published:
        problems.append(f"{book.index.where}:1: the contents page is in outline: there is nothing to publish")
    if problems:
        raise Refused(problems)
    return book


_cache: dict = {}


def current() -> Book:
    """The book at settings.BOOK_DIR, read again whenever one of its files has changed."""
    root = Path(settings.BOOK_DIR)
    stamp = tuple(sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob("*") if p.suffix in (".md", ".svg")))
    if _cache.get("key") != (root, stamp):
        _cache.update(key=(root, stamp), book=load(root))
    return _cache["book"]
