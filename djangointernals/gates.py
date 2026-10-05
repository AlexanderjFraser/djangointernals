"""The three gates and the link gate, as the site calls them; and what the renderer makes of a pointer.

`tools/pointers.py`, `tools/names.py`, `tools/recordings.py` and `tools/links.py`
at the repository's root are a reader's to run as commands (SPEC.md, *Checking
a page*). The site imports them too: the loader refuses a book whose
pointers do not resolve at the pin, whose names do not exist or whose quotes
of a recording are not the recording's, as it refuses a page that breaks the
spec; the bake refuses what it wrote when a link in it does not resolve; and
the renderer turns each pointer into a link to the lines it lands on, at the
pinned commit, in the tree's own repository. The pointer and name gates need
the pinned trees on disk (`python tools/pin.py fetch`), so the bake does too.

One World and one name index per process: the index of Django's names takes
seconds to build, and the pin does not change while the site runs.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from django.conf import settings

TOOLS = str(Path(settings.BASE_DIR) / "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import links  # noqa: E402  (the link gate, run by the bake over what it wrote)
import names  # noqa: E402  (the name gate; it imports the pointer gate)
import pointers  # noqa: E402  (the pointer gate: the trees, the walk, what a pointer is)
import recordings  # noqa: E402  (the recording gate: a fenced block that quotes a recording quotes it as recorded)


class Unavailable(Exception):
    """The gates cannot run: a pinned tree is not on disk, or not at its pin."""


class Gates:
    def __init__(self, root: Path):
        try:
            self.gate = names.Gate(str(root))
        except SystemExit as why:  # a gate stops with one line when a tree is not at its pin
            raise Unavailable(str(why)) from None
        self.world = self.gate.world
        self.pinned = self.world.pinned
        self.recordings: dict = {}  # each recording's output, read once a process

    @property
    def list_problems(self) -> list[str]:
        """What is wrong with the book's own list of runtime-made names, shown by its path."""
        path = self.gate.list_path
        shown = Path(path).relative_to(settings.BASE_DIR).as_posix() if path else ""
        return [relabel(line, os.path.basename(path), shown) for line in self.gate.list_problems]

    def problems(self, page) -> list[str]:
        """What the three gates refuse on a page, each as `file:line: span: why`. The name gate
        runs with --sections: a name several modules define is bound within its section. The
        recording gate reads the fenced blocks that name a recording."""
        path = str(page.source)
        found = (pointers.examine(self.world, path)[1] + self.gate.examine(path, sections=True)[0]
                 + recordings.examine(path, str(settings.BASE_DIR), self.recordings)[0])
        return [relabel(line, os.path.basename(path), page.where) for line in found]

    def is_pointer(self, body: str) -> bool:
        return pointers.is_pointer(body, self.world)

    def link(self, body: str) -> tuple[str, str] | None:
        """(href, title) for a pointer: the lines it lands on, in the tree's repository at the
        pin. None for a pointer that does not resolve, which the gate refuses anyway."""
        try:
            tree, path, symbol = self.world.parse(body)
            kind, landings = self.world.resolve(tree, path, symbol)
        except pointers.Unresolved:
            return None
        entry = self.pinned["trees"][tree]
        repository, commit = entry["repository"].rstrip("/"), entry["commit"]
        where = f"{tree} at {commit[:12]}"
        if kind == "directory":
            return f"{repository}/tree/{commit}/{path.rstrip('/')}", f"The directory {path} in {where}"
        if kind == "file":
            return f"{repository}/blob/{commit}/{path}", f"The file {path} in {where}"
        # a name bound more than once (a property and its setter, overloads before a definition) links to
        # the span from its first binding to its last, so that the definition is in view and not a stub alone
        ranges = [f"{a.first}–{a.last}" if a.last != a.first else f"{a.first}" for a in landings]
        first, last = min(a.first for a in landings), max(a.last for a in landings)
        fragment = f"#L{first}" + (f"-L{last}" if last != first else "")
        lines = ("lines " if "–" in ranges[0] else "line ") + ranges[0]
        if len(ranges) > 1:
            lines += ", and " + ", ".join(ranges[1:]) + " (bound more than once: the link spans them)"
        return f"{repository}/blob/{commit}/{path}{fragment}", f"{path}, {lines}, in {where}"


def relabel(line: str, basename: str, shown: str) -> str:
    """A gate's `name.md:line: ...` with the document's path as a message names it."""
    return shown + line[len(basename):] if line.startswith(basename + ":") else line


_gates: dict = {}


def current() -> Gates:
    """The gates for this repository's pin, made once per process."""
    key = str(settings.BASE_DIR)
    if key not in _gates:
        _gates[key] = Gates(Path(settings.BASE_DIR))
    return _gates[key]
