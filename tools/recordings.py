#!/usr/bin/env python3
"""The recording gate: a fenced block that quotes a recording quotes it as it was recorded.

    python tools/recordings.py DOC [DOC ...]     check each document, or every .md under a directory
    python tools/recordings.py --probe           prove the gate fails on what it should

A chapter's recording is a script `recordings/<name>.py` whose output is committed beside it
as `recordings/<name>.txt` (SPEC.md, *Recordings*). A page quotes that output in a fenced
block whose info string names the recording:

    ```text recording=handlers
    WSGI, GET /plain/: a view that returns a response
        signal: request_started
        A.process_request
    ```

The output is read as blocks: a line at column 0 is a title and opens a block, and the
indented lines under it, down to the next blank line, are the block's lines. For each
quoting fence the gate checks that:

- the recording exists: `recordings/<name>.txt` under the book's root;
- every quoted line is a line of one block of the recording, and the quoted lines stand in
  that block's order. Lines may be left out between them, and a line holding only `...` may
  stand where they were; but no line is altered, added or moved, and a quote does not run
  from one block into the next;
- the quote keeps the recording's nesting: an excerpt from inside a block may be shifted
  left as a whole, and the indentation of each line relative to the first quoted line is
  then the recording's.

A fenced block with no `recording=` in its info string is not read: the rule reaches only
what claims to be a recording, and a block of text that is not one says nothing. Each
command takes `--root DIR`, the book's root (default: $BOOK_ROOT, else the directory above
this file). One line per fault, `file:line: what is wrong`, and a last line: `recordings: ok,
N quotes of M recordings in D documents`, or `FAILED` with how many quotes were refused.

Vendored: the copy in a book's repository is written by a command and is not edited there.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDINGS = "recordings"
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
NAMED = re.compile(r"\brecording=(\S+)")
GAP = "..."


def root_of(given: str | None) -> str:
    return os.path.abspath(given or os.environ.get("BOOK_ROOT") or os.path.dirname(HERE))


class Recording:
    """A recording's output, as blocks of (indent, text) lines, the title first at indent 0."""

    def __init__(self, path: str):
        self.path = path
        self.blocks: list[tuple[str, list[tuple[int, str]]]] = []
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n").rstrip()
                if not line:
                    continue
                indent = len(line) - len(line.lstrip(" "))
                if indent == 0:
                    self.blocks.append((line, [(0, line)]))
                elif self.blocks:
                    self.blocks[-1][1].append((indent, line.strip()))


def quotes(path: str):
    """Each fenced block of the document that names a recording: (line of the fence, the
    recording's name, the block's lines as (indent, text), with `...` lines left out)."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    open_fence = None  # (character, length, line number, name)
    body: list[str] = []
    for number, line in enumerate(lines, 1):
        found = FENCE.match(line)
        if open_fence is None:
            if found:
                named = NAMED.search(found.group(3))
                open_fence = (found.group(2)[0], len(found.group(2)), number, named.group(1) if named else None)
                body = []
            continue
        char, length, at, name = open_fence
        if found and found.group(2)[0] == char and len(found.group(2)) >= length and not found.group(3).strip():
            if name is not None:
                yield at, name, parse(body)
            open_fence = None
            continue
        body.append(line)


def parse(body: list[str]) -> list[tuple[int, str]]:
    out = []
    for line in body:
        line = line.rstrip()
        if not line.strip() or line.strip() == GAP:
            continue
        out.append((len(line) - len(line.lstrip(" ")), line.strip()))
    return out


def find(quote: list[tuple[int, str]], block: list[tuple[int, str]]) -> tuple[bool, int, str]:
    """Whether the quote is an in-order excerpt of the block with its nesting kept; else how
    far the best attempt got (quoted lines matched) and why it stopped."""
    best, why = 0, ""
    first_indent, first_text = quote[0]
    for anchor, (indent, text) in enumerate(block):
        if text != first_text:
            continue
        shift = indent - first_indent
        matched, at = 1, anchor + 1
        stopped = ""
        for want_indent, want_text in quote[1:]:
            seen_other_indent = False
            while at < len(block) and not (block[at][1] == want_text and block[at][0] == want_indent + shift):
                if block[at][1] == want_text:
                    seen_other_indent = True
                at += 1
            if at >= len(block):
                stopped = (f"`{want_text}` is in this block, but not nested as the quote has it" if seen_other_indent
                           else f"`{want_text}` does not follow `{quote[matched - 1][1]}` in this block")
                break
            matched, at = matched + 1, at + 1
        if matched == len(quote):
            return True, matched, ""
        if matched > best:
            best, why = matched, stopped
    return False, best, why


def examine(path: str, root: str, cache: dict | None = None) -> tuple[list[str], int, set[str]]:
    """What is wrong with the document's quotes of recordings, each as `basename:line: why`;
    how many quotes it has; which recordings they name."""
    cache = cache if cache is not None else {}
    name_of = os.path.basename(path)
    problems, count, named = [], 0, set()
    for at, name, quote in quotes(path):
        count += 1
        named.add(name)
        where = f"{name_of}:{at}"
        file = os.path.join(root, RECORDINGS, name + ".txt")
        if name not in cache:
            cache[name] = Recording(file) if os.path.isfile(file) else None
        recording = cache[name]
        shown = f"{RECORDINGS}/{name}.txt"
        if recording is None:
            problems.append(f"{where}: recording={name}: there is no {shown}")
            continue
        if not quote:
            problems.append(f"{where}: a quote of {shown} with nothing in it")
            continue
        best, why = 0, ""
        for title, block in recording.blocks:
            ok, matched, stopped = find(quote, block)
            if ok:
                break
            if matched > best:
                best, why = matched, f"{stopped} ({title})"
        else:
            if best == 0:
                problems.append(f"{where}: a quote of {shown}: its first line, `{quote[0][1]}`, is in no block of it")
            else:
                problems.append(f"{where}: a quote of {shown}: {why}; a quote keeps a block's lines, order and nesting, "
                                f"and may only leave lines out")
    return problems, count, named


def documents(targets: list[str]) -> list[str]:
    out = []
    for target in targets:
        if os.path.isdir(target):
            for folder, _dirs, files in os.walk(target):
                out.extend(os.path.join(folder, f) for f in sorted(files) if f.endswith(".md"))
        else:
            out.append(target)
    return out


def run(targets: list[str], root: str) -> int:
    cache: dict = {}
    problems, quotes_seen, named, docs = [], 0, set(), 0
    for path in documents(targets):
        found, count, names = examine(path, root, cache)
        shown = os.path.relpath(path, root).replace(os.sep, "/") if path.startswith(root) else path
        problems += [shown + line[len(os.path.basename(path)):] for line in found]
        quotes_seen += count
        named |= names
        docs += 1
    for line in problems:
        print(line)
    if problems:
        print(f"recordings: FAILED, {len(problems)} of {quotes_seen} quotes refused in {docs} documents")
        return 1
    print(f"recordings: ok, {quotes_seen} quotes of {len(named)} recordings in {docs} documents")
    return 0


PROBE_RECORDING = """Django 6.2 with MIDDLEWARE = [A, B, C]

WSGI, GET /plain/: a view that returns a response
    signal: request_started
    A.process_request
    B.process_request
      inside B
        deeper
    the view
    B.process_response(200)
    A.process_response(200)
    signal: request_finished

WSGI, GET /other/: another request
    signal: request_started
    A.process_request
    the view
"""

PROBE_GOOD = """# A page

```text recording=probe
WSGI, GET /plain/: a view that returns a response
    signal: request_started
    A.process_request
    B.process_request
      inside B
        deeper
    the view
    B.process_response(200)
    A.process_response(200)
    signal: request_finished
```

A block shifted left, with lines left out and said so:

```text recording=probe
A.process_request
B.process_request
  inside B
...
the view
A.process_response(200)
```

A line that is in two blocks, anchored by what follows it:

```text recording=probe
A.process_request
the view
```

```text
A block of text that is not a recording, and says what it likes.
```

~~~text recording=probe
signal: request_finished
~~~
"""

PROBE_BAD = """# A page

```text recording=probe
WSGI, GET /plain/: a view that returns a response
    signal: request_started
    A.process_request
    C.process_request
```

```text recording=probe
A.process_request
signal: request_started
```

```text recording=probe
B.process_response(200)
signal: request_finished
signal: request_started
```

```text recording=probe
B.process_request
inside B
```

```text recording=nowhere
anything
```

```text recording=probe
```

```text recording=probe
not a line of it
```
"""

PROBE_FAULTS = {
    (3, "`C.process_request` does not follow `A.process_request` in this block (WSGI, GET /plain/: a view that returns a response)"),
    (10, "`signal: request_started` does not follow `A.process_request` in this block (WSGI, GET /plain/: a view that returns a response)"),
    (15, "`signal: request_started` does not follow `signal: request_finished` in this block (WSGI, GET /plain/: a view that returns a response)"),
    (21, "`inside B` is in this block, but not nested as the quote has it (WSGI, GET /plain/: a view that returns a response)"),
    (26, "recording=nowhere: there is no recordings/nowhere.txt"),
    (30, "a quote of recordings/probe.txt with nothing in it"),
    (33, "a quote of recordings/probe.txt: its first line, `not a line of it`, is in no block of it"),
}


def probe() -> int:
    import shutil
    import tempfile

    work = tempfile.mkdtemp(prefix="recordingsprobe-")
    failed = []

    def expect(label: str, got, want) -> None:
        if got != want:
            failed.append(f"{label}: got {got!r}, wanted {want!r}")

    def write(path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    try:
        write(os.path.join(work, RECORDINGS, "probe.txt"), PROBE_RECORDING)
        good, bad = os.path.join(work, "pages", "good.md"), os.path.join(work, "pages", "bad.md")
        write(good, PROBE_GOOD)
        write(bad, PROBE_BAD)
        problems, count, named = examine(good, work)
        expect("a page whose every quote is an excerpt in order, nesting kept, passes", problems, [])
        expect("every quoting fence is counted, a plain fence is not", (count, named), (4, {"probe"}))
        problems, count, named = examine(bad, work)
        found = set()
        for line in problems:
            name, number, why = line.split(":", 2)
            why = why.strip()
            for tail in ("; a quote keeps a block's lines, order and nesting, and may only leave lines out",):
                why = why.removesuffix(tail)
            why = why.removeprefix("a quote of recordings/probe.txt: ") if "does not follow" in why or "not nested" in why else why
            found.add((int(number), why))
        expect("the faults, and only the faults", found, PROBE_FAULTS)
        expect("every fault names the file and the fence's line", all(line.startswith("bad.md:") for line in problems), True)
        expect("seven quotes seen", count, 7)
        blocks = Recording(os.path.join(work, RECORDINGS, "probe.txt")).blocks
        expect("the output is read as blocks headed by a line at column 0", [title for title, _ in blocks],
               ["Django 6.2 with MIDDLEWARE = [A, B, C]", "WSGI, GET /plain/: a view that returns a response",
                "WSGI, GET /other/: another request"])
        expect("a block's lines keep their indentation", blocks[1][1][4], (6, "inside B"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if failed:
        print("PROBE FAILED:\n  " + "\n  ".join(failed))
        return 1
    print("probe ok: a fence that names a recording quotes one block of it, its lines in order and their nesting kept, "
          "shifted left as a whole or with lines left out; an altered, moved or added line, a quote that runs from one "
          "block into another, a quote with nothing in it and a recording that does not exist are refused, each with "
          "the file and the fence's line; a fence that names no recording is not read")
    return 0


def main(argv: list[str]) -> int:
    args = list(argv)
    root = None
    while "--root" in args:
        at = args.index("--root")
        if at + 1 >= len(args):
            raise SystemExit("--root needs a directory")
        root = args[at + 1]
        del args[at:at + 2]
    if "--probe" in args:
        return probe()
    flags = [a for a in args if a.startswith("--")]
    rest = [a for a in args if not a.startswith("--")]
    if flags or not rest:
        raise SystemExit(__doc__)
    return run(rest, root_of(root))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
